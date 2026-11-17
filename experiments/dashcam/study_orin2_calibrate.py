#!/usr/bin/env python3
"""
StudyORIN2-stack Part 1 — Orin 4B score calibration (design log D61).

StudyORIN1-dense found the Orin llama.cpp F16 4B scores sit about 1 log unit
from the H100 vLLM BF16 4B scores, so the H100-fitted Platt map (StudyCTRL1c)
cannot be reused on the device. Here we score the 6,010 StudyD3 DEV N=1 requests
(601 clips x 10 event-anchored offsets) on the Orin with the StudyD15 contract
(byte-identical prompt: header "The following is 1 dashcam frame.", one SMALL
768x432 PNG, the Nexar query; 378 prompt tokens), then fit ONE Platt map for the
Orin 4B (log_odds = a * log(p_yes) + b, clip-level label) on the 601 DEV clips.

STACK (identical to StudyORIN1-dense; reused by import, not edited):
  llama.cpp c0fd786; Qwen3-VL-4B-Instruct-F16 GGUF + mmproj-F16 (sha256 verified
  in dfl.GGUF); server -ngl 99 -fa on -c 57344 --jinja --reasoning-format deepseek
  -np 1 (one request at a time); MAXN mode 0; GPU pinned 1.3005 GHz, logged/row;
  greedy, seed 0, cache_prompt FALSE (cold). Scoring reuses d15.build_nexar_content
  and d15.score_request unchanged.

Subcommands:
  --gate     sha256-verify every required DEV frame against the D3 frame manifest.
  --score    score all 6,010 (resumable by request_id, clip+offset order), clock/row.
  --analyse  H100 agreement gate, Platt fit (validated by refitting the H100 map and
             recovering a=0.114603,b=1.140751), apply to the 42,014 Orin dense scores,
             residual tier offset vs calibrated 32B, write orin2_calibration.json.

Outputs under results/dashcam/study_orin2/.
"""
import argparse, csv, gzip, hashlib, json, math, os, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import experiments.device.study_d15_orin_nexar as d15
import experiments.device.study_e8_device_warm as e8
import experiments.device.dev_fast_latency as dfl
from experiments.lib._provenance import stamp

ROOT = Path(__file__).resolve().parent.parent.parent
OUTD = ROOT / "results/dashcam/study_orin2"
D3DIR = ROOT / "results/dashcam/study_d3_nexar"
D3_REQMAN = D3DIR / "d3_requests_manifest.jsonl"
D3_FRAMEMAN = D3DIR / "frames_sha256_manifest.jsonl.gz"
D3_H100 = D3DIR / "d3_requests_h100nvl.jsonl.gz"
SPLIT = ROOT / "results/dashcam/study_d2_nexar/nexar_train_split_seed0.csv"
ORIN1_DENSE = ROOT / "results/dashcam/study_orin1/orin1_dense_scores.jsonl.gz"

SCORES = OUTD / "orin2_d3dev_scores.jsonl"
GATE = OUTD / "orin2_part1_frame_gate.json"
PINNED_HZ = d15.PINNED_HZ
STOP_TJ = d15.STOP_TJ

# H100-fitted maps for comparison (from StudyCTRL1c, stated in the brief)
H100_4B_MAP = {"a": 0.114603, "b": 1.140751}
H100_32B_MAP = {"a": 0.129472, "b": 1.848187}


# ── inputs ───────────────────────────────────────────────────────────────────
def dev_clips():
    dev = set()
    with open(SPLIT) as f:
        for row in csv.DictReader(f):
            if row["split"] == "dev":
                dev.add(row["file_name"].replace(".mp4", ""))
    return dev


def load_d3_dev_n1():
    """The 6,010 D3 N=1 DEV requests, clip+offset ordered."""
    dev = dev_clips()
    reqs = []
    with open(D3_REQMAN) as f:
        for line in f:
            r = json.loads(line)
            if r.get("n") != 1:
                continue
            if r["file_name"].replace(".mp4", "") not in dev:
                continue
            reqs.append(r)
    reqs.sort(key=lambda r: (r["file_name"], float(r["offset"])))
    return reqs


def frame_path(req):
    clip = req["file_name"].replace(".mp4", "")
    return d15.D14DIR / clip / f"{req['frame_keys'][0]}.png"


# ── gate ─────────────────────────────────────────────────────────────────────
def gate(reqs):
    man = {}
    with gzip.open(D3_FRAMEMAN, "rt") as f:
        for line in f:
            r = json.loads(line)
            man[(r["file_name"], r["key"])] = r["small_sha256"]
    missing, mismatch, n = [], [], 0
    seen = {}
    for r in reqs:
        key = r["frame_keys"][0]
        want = man.get((r["file_name"], key)) or r["small_sha256"][0]
        p = frame_path(r)
        if not p.exists():
            missing.append(r["request_id"]); continue
        h = seen.get(p)
        if h is None:
            h = hashlib.sha256(p.read_bytes()).hexdigest(); seen[p] = h
        n += 1
        if h != want:
            mismatch.append(r["request_id"])
    ok = not missing and not mismatch
    clips = sorted(set(r["file_name"].replace(".mp4", "") for r in reqs))
    res = {"ok": ok, "checked": n, "n_reqs": len(reqs), "n_clips": len(clips),
           "missing": len(missing), "mismatch": len(mismatch),
           "missing_ex": missing[:5], "mismatch_ex": mismatch[:5],
           "manifest": str(D3_FRAMEMAN.relative_to(ROOT))}
    OUTD.mkdir(parents=True, exist_ok=True)
    json.dump(res, open(GATE, "w"), indent=1)
    print(f"[gate] ok={ok} checked={n}/{len(reqs)} clips={len(clips)} "
          f"missing={len(missing)} mismatch={len(mismatch)}", flush=True)
    return ok


# ── score ────────────────────────────────────────────────────────────────────
def score(reqs, sampler, resume=True):
    done = set()
    if resume and SCORES.exists():
        for line in open(SCORES):
            try:
                done.add(json.loads(line)["request_id"])
            except Exception:
                pass
    mode = "a" if (resume and SCORES.exists()) else "w"
    f = open(SCORES, mode)
    t0 = time.time(); n = 0; last_clip = None
    todo = len(reqs) - len(done)
    for r in reqs:
        if r["request_id"] in done:
            continue
        clip = r["file_name"].replace(".mp4", "")
        if clip != last_clip:
            tj = e8.recent_tj(sampler)
            if tj and tj >= STOP_TJ:
                print(f"[score] THROTTLE STOP tj={tj} at clip {clip}", flush=True)
                break
            last_clip = clip
        content, _ = d15.build_nexar_content(r, verify=False)  # frames pre-verified in the gate
        rec = d15.score_request(content, cache_prompt=False)
        row = {"request_id": r["request_id"], "file_name": r["file_name"], "clip": clip,
               "offset": float(r["offset"]), "label": r.get("label"), "gt": r.get("gt"),
               "p_yes": rec["p_yes"], "score": rec["score"], "first_token": rec["first_token"],
               "yes_seen": rec["yes_seen"], "no_seen": rec["no_seen"], "neither": rec["neither"],
               "prompt_tokens": rec["prompt_tokens"], "cache_n": rec["cache_n"],
               "ttft_s": rec["ttft_s"], "total_s": rec["total_s"], "clock_ok": rec["clock_ok"]}
        f.write(json.dumps(row) + "\n"); f.flush()
        n += 1
        if n % 500 == 0:
            rate = n / max(1e-9, time.time() - t0)
            eta = (todo - n) / max(1e-9, rate) / 60
            print(f"[score] {n}/{todo} new (clip {clip} off={r['offset']}) {rate:.2f} req/s "
                  f"ETA {eta:.0f} min score={rec['score']}", flush=True)
    f.close()
    print(f"[score] done: {n} new rows this run", flush=True)
    return n


# ── small stats ──────────────────────────────────────────────────────────────
def pearson(xs, ys):
    n = len(xs)
    if n < 2:
        return None
    mx = sum(xs) / n; my = sum(ys) / n
    sx = sum((x - mx) ** 2 for x in xs); sy = sum((y - my) ** 2 for y in ys)
    if sx == 0 or sy == 0:
        return None
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    return cov / math.sqrt(sx * sy)


def platt_fit(logp, y):
    """One-feature Platt map: sigmoid(a*log(p_yes) + b), fit with
    sklearn LogisticRegression at its default settings (C=1.0, lbfgs). This is
    the routine StudyCTRL1c used: refitting it on the H100 4B D3 DEV scores
    reproduces the published H100 4B map (a=0.114603, b=1.140751) to < 1e-4
    (see platt_validation in the analysis). The Orin map is fit identically.
    The data is near-separable, so the default L2 (C=1.0) is what keeps the fit
    finite; an unregularized MLE diverges. Returns (a, b)."""
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    X = np.asarray(logp, dtype=float).reshape(-1, 1)
    yy = np.asarray(y, dtype=int)
    lr = LogisticRegression(C=1.0, solver="lbfgs", max_iter=10000)
    lr.fit(X, yy)
    return float(lr.coef_[0][0]), float(lr.intercept_[0])


# ── analyse ──────────────────────────────────────────────────────────────────
def load_scores(path):
    if path.suffix == ".gz":
        with gzip.open(path, "rt") as g:
            return [json.loads(l) for l in g]
    return [json.loads(l) for l in open(path)]


def analyse():
    scores_path = SCORES if SCORES.exists() else SCORES.with_suffix(SCORES.suffix + ".gz")
    orin = load_scores(scores_path)
    by_id = {r["request_id"]: r for r in orin}
    # sanity
    n_null = sum(1 for r in orin if r["score"] is None)
    n_neither = sum(1 for r in orin if r["neither"])
    clock_all = all(r["clock_ok"] for r in orin)
    # H100 4B D3 scores for the same requests. The H100 file stores p_yes, not score;
    # recompute score = log(max(p_yes,1e-12)) exactly as d15.score_request does, and
    # drop the 100 grey controls (grey==True) so the ids line up with the 6,010.
    def h100_score(hr):
        p = hr.get("p_yes")
        return math.log(max(p, 1e-12)) if p is not None else None
    h = {}
    with gzip.open(D3_H100, "rt") as g:
        for line in g:
            r = json.loads(line)
            if str(r.get("model")) == "4BI" and str(r.get("n")) == "1" and not r.get("grey"):
                h[r["request_id"]] = r
    # agreement on matched requests
    co, ch = [], []
    for rid, r in by_id.items():
        hr = h.get(rid)
        hs = h100_score(hr) if hr else None
        if hs is not None and r["score"] is not None:
            co.append(r["score"]); ch.append(hs)
    agree = {"n_matched": len(co),
             "pearson": round(pearson(co, ch), 4) if co else None,
             "mean_orin_minus_h100": round(sum(a - b for a, b in zip(co, ch)) / len(co), 4) if co else None}
    # clip labels (1 positive / 0 negative)
    def clip_label(r):
        lab = r.get("label") or r.get("gt")
        return 1 if str(lab).lower() == "positive" else 0
    # validate the Platt routine: refit on H100 4B scores, must recover the stated map
    hv_logp, hv_y = [], []
    for rid, hr in h.items():
        s = h100_score(hr)
        if s is None:
            continue
        hv_logp.append(s); hv_y.append(1 if str(hr.get("label") or hr.get("gt")).lower() == "positive" else 0)
    ha, hb = platt_fit(hv_logp, hv_y)
    a_err = abs(ha - H100_4B_MAP["a"]); b_err = abs(hb - H100_4B_MAP["b"])
    valid = {"refit_a": round(ha, 6), "refit_b": round(hb, 6),
             "target_a": H100_4B_MAP["a"], "target_b": H100_4B_MAP["b"],
             "a_abs_err": round(a_err, 6), "b_abs_err": round(b_err, 6),
             "n_h100_fit": len(hv_logp),
             "reproduces_ctrl1c_map": bool(a_err < 1e-3 and b_err < 1e-3),
             "routine": "sklearn LogisticRegression(C=1.0, lbfgs) on log(p_yes), clip-level label"}
    # fit the Orin map on the 601 DEV clips (clip-level label, per-request feature)
    o_logp, o_y = [], []
    for r in orin:
        if r["score"] is None:
            continue
        o_logp.append(r["score"]); o_y.append(clip_label(r))
    oa, ob = platt_fit(o_logp, o_y)
    raw_at_half = (-ob / oa) if oa else None  # log(p_yes) where calibrated prob = 0.5
    orin_map = {"a": round(oa, 6), "b": round(ob, 6), "feature": "log_pyes",
                "form": "log_odds = a*log(p_yes) + b", "raw_logpyes_at_p0.5": round(raw_at_half, 6) if raw_at_half else None,
                "n_fit": len(o_logp), "n_clips": len(set(r["clip"] for r in orin))}
    # apply to the 42,014 Orin dense scores; residual tier offset vs calibrated 32B
    dense = load_scores(ORIN1_DENSE)
    dense_clips = set(r["clip"] for r in dense)
    dev_clip_set = set(r["clip"] for r in orin)
    overlap = len(dev_clip_set & dense_clips)
    cal = [oa * r["score"] + ob for r in dense if r["score"] is not None]
    mean_cal = sum(cal) / len(cal) if cal else None
    applied = {"n_dense": len(dense), "n_applied": len(cal),
               "mean_calibrated_logodds": round(mean_cal, 6) if mean_cal else None,
               "dev_eval_clip_overlap": overlap,
               "h100_4b_residual_vs_32B_ref": -0.1197}
    # residual tier offset: calibrated Orin-4B minus calibrated 32B, on the only set
    # where both tiers exist (D3 DEV). Parallels StudyCTRL1c's H100-4B residual (-0.1197).
    # The 42,014 dense requests have no 32B scores (32B was never run on D14b), so the
    # tier residual is necessarily measured on D3 DEV, not the dense set.
    h32 = {}
    with gzip.open(D3_H100, "rt") as g:
        for line in g:
            r = json.loads(line)
            if str(r.get("model")) == "32BI" and str(r.get("n")) == "1" and not r.get("grey"):
                p = r.get("p_yes")
                if p is not None:
                    h32[r["request_id"]] = math.log(max(p, 1e-12))
    a32, b32 = H100_32B_MAP["a"], H100_32B_MAP["b"]
    resid = []
    for r in orin:
        s = r["score"]; s32 = h32.get(r["request_id"])
        if s is not None and s32 is not None:
            resid.append((oa * s + ob) - (a32 * s32 + b32))
    tier_residual = {"set": "D3 DEV (both tiers present)", "n": len(resid),
                     "orin4b_minus_cal32b_logodds": round(sum(resid) / len(resid), 6) if resid else None,
                     "h100_4b_minus_cal32b_ref_ctrl1c": -0.1197,
                     "note": "dense set has no 32B scores; tier residual measured where both tiers exist"}
    applied["tier_residual"] = tier_residual
    res = {"status": "COMPLETE", "n_scores": len(orin),
           "sanity": {"n_null": n_null, "n_neither": n_neither, "clock_pinned_all": clock_all},
           "h100_agreement": agree, "platt_validation": valid,
           "orin_4b_map": orin_map, "h100_4b_map": H100_4B_MAP, "h100_32b_map": H100_32B_MAP,
           "apply_to_dense": applied}
    OUTD.mkdir(parents=True, exist_ok=True)
    json.dump(res, open(OUTD / "study_orin2_part1_analysis.json", "w"), indent=1)
    # the calibration map file, same shape as StudyCTRL1c maps
    prov = stamp(script="study_orin2_calibrate.py", model="qwenvl4b", device="jetson_orin",
                 n=len(o_logp), args={"part": 1})
    cmap = {"model": "4bi_f16_orin", "stack": "llama.cpp c0fd786 F16 GGUF",
            "feature": "log_pyes", "form": "log_odds = a*log(p_yes) + b",
            "a": round(oa, 6), "b": round(ob, 6), "raw_logpyes_at_p0.5": round(raw_at_half, 6) if raw_at_half else None,
            "fit_split": "StudyD3 DEV (601 clips x 10 offsets = 6010 N=1 requests)",
            "clip_level_label": True, "seed": 0,
            "compare": {"h100_4b": H100_4B_MAP, "h100_32b": H100_32B_MAP},
            "_provenance": prov}
    json.dump(cmap, open(OUTD / "orin2_calibration.json", "w"), indent=1)
    print(json.dumps(res, indent=1))
    print("wrote", OUTD / "orin2_calibration.json")
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gate", action="store_true")
    ap.add_argument("--score", action="store_true")
    ap.add_argument("--analyse", action="store_true")
    ap.add_argument("--no-resume", action="store_true")
    args = ap.parse_args()
    OUTD.mkdir(parents=True, exist_ok=True)

    if args.gate or args.score:
        reqs = load_d3_dev_n1()
        print(f"[1] D3 DEV N=1 requests: {len(reqs)} "
              f"({len(set(r['file_name'] for r in reqs))} clips)", flush=True)
        ok = gate(reqs)
        if not ok:
            print("[1] GATE FAILED - stopping before scoring.", flush=True)
            sys.exit(2)
        if args.score:
            gz = OUTD / "orin2_tegrastats.jsonl.gz"
            sampler = dfl.Sampler(str(gz))
            proc = e8.launch_server_e8(str(OUTD / "orin2_server.log"), n_ctx=e8.N_CTX)
            try:
                score(reqs, sampler, resume=not args.no_resume)
            finally:
                dfl.stop_server(proc)
                sampler.stop()
            meta = {"llama_cpp": "c0fd786", "model_tag": d15.MODEL_TAG, "n_ctx": e8.N_CTX,
                    "pinned_hz": PINNED_HZ, "seed": 0, "cache_prompt": False,
                    "server_flags": "-ngl 99 -fa on -c 57344 --jinja --reasoning-format deepseek -np 1",
                    "weights_sha256": "4a6fb1ed053e162887bfc372bd7ffaaa9b8e4049ac6e9b9398ae7277162ec761",
                    "mmproj_sha256": "256f3a43bd4205ffef48d6b92715e1e70b5b0e9aef06522584967513a9985331"}
            json.dump(meta, open(OUTD / "orin2_meta.json", "w"), indent=1)
    if args.analyse:
        analyse()


if __name__ == "__main__":
    main()
