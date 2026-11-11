#!/usr/bin/env python3
"""
StudyF4-device-shortwin — StudyF1 short-window (last-3-second) S-EMBER on the Jetson Orin.

Jetson Orin only. Same stack as StudyD8 / StudyD4-orin: llama.cpp c0fd786,
Qwen3VL-4B-Instruct-F16 (+mmproj-F16), sha256 verified; MAXN mode 0, GPU pinned
1.3005 GHz (verified + logged per request); cache_prompt=FALSE (cold); greedy
(temperature 0), seed 0, MAX_TOKENS=64; answer logprobs requested if the server
provides them.

Inputs: the StudyF1-shortwin frame archive copied from the H100 —
  /home/nesl/data/study_f1_frames/f1/
    f1_inputs_manifest.jsonl   2,535 rows (845 questions x N in {1,3,9})
    f1_frames_sha256.json      per-frame sha256 for all 7,605 frames
    frames/<video>/<idx>.png   560x560 PNG (PIL LANCZOS)
Each manifest row carries StudyF1's exact prompt: `header` (frame preamble) and
`text` (the MCQ). The request is assembled as header -> N images -> MCQ text, which
is StudyF1's template (NO DEV-RECENT "[t=Xs]" markers). Letter = first \b[A-E]\b.
These are the SAME BYTES the H100 StudyF1 4B used (short window), not DEV-RECENT.

Part A  accuracy: all 845 q at N=1, then 3, then 9 (one at a time). Video-bootstrap
        CIs (resample 234 videos), per-stratum accuracy, per-question agreement with
        H100 4B (StudyF1) if its predictions are supplied (< 90% flagged).
Part B  latency: 50 req per N, first-after-load discarded. TTFT + total p50/p90/p99
        + rail energy/req (3 INA3221 rails, no VDD_IN; 100 ms tegrastats, trapezoid).
        Compared with StudyD8/D4-orin TTFT (N=1 0.513 s, N=3 1.34 s, N=9 3.84 s).

Outputs under results/device/study_f4/.
"""
import argparse, base64, hashlib, json, math, random, re, statistics as st, sys, time, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import experiments.device.dev_fast_latency as dfl
from experiments.lib._provenance import stamp

ROOT = Path(__file__).resolve().parent.parent.parent
OUTDIR = ROOT / "results/device/study_f4"
F1DIR = Path("/home/nesl/data/study_f1_frames/f1")
MANIFEST = F1DIR / "f1_inputs_manifest.jsonl"
SHA_JSON = F1DIR / "f1_frames_sha256.json"
FRAMES = F1DIR / "frames"

PINNED_HZ = 1300500000
MAX_TOKENS = 64
GEN = dict(temperature=0.0, max_tokens=MAX_TOKENS, seed=0)
STOP_TJ = 90.0
SETTLE = 0.15
D_REF = {1: 0.513, 3: 1.34, 9: 3.84}       # StudyD8 / StudyD4-orin TTFT p50 references
N_BOOT = 2000
RANDOM_BASELINE = 0.20                       # 5 options


def pct(xs, q):
    xs = sorted(v for v in xs if v is not None)
    if not xs:
        return None
    if len(xs) == 1:
        return xs[0]
    i = q / 100 * (len(xs) - 1)
    lo = int(i); hi = min(lo + 1, len(xs) - 1)
    return round(xs[lo] + (xs[hi] - xs[lo]) * (i - lo), 4)


def recent_tj(sampler, n=30):
    rows = sampler.snapshot()[-n:]
    tjs = [r["tj"] for r in rows if r.get("tj")]
    return max(tjs) if tjs else None


# ── inputs ───────────────────────────────────────────────────────────────────
def load_manifest():
    """Return {(qid, N): entry} and ordered lists of qids (manifest order)."""
    by_key = {}
    qid_order = []
    seen = set()
    for l in open(MANIFEST):
        d = json.loads(l)
        by_key[(d["question_id"], d["n"])] = d
        if d["question_id"] not in seen:
            seen.add(d["question_id"]); qid_order.append(d["question_id"])
    return by_key, qid_order


def verify_inputs():
    """Re-verify EVERY frame's sha256 against f1_frames_sha256.json. Hard gate."""
    sha = json.load(open(SHA_JSON))
    files = sha["files"]
    bad = []; ok = 0
    for rel, expect in files.items():
        p = FRAMES / rel
        if not p.exists():
            bad.append({"file": rel, "why": "missing"}); continue
        h = hashlib.sha256(p.read_bytes()).hexdigest()
        if h == expect:
            ok += 1
        else:
            bad.append({"file": rel, "why": "mismatch"})
        if len(bad) > 20:
            break
    return {"checked": len(files), "ok": ok, "n_bad": len(bad), "bad": bad[:10],
            "resolution": sha.get("size"), "format": sha.get("format"),
            "resize": sha.get("resize")}


# ── one request (StudyF1 template; cold; clock + logprob logged) ──────────────
def build_content(entry):
    """StudyF1 assembly: header text -> N images -> MCQ text. No per-frame markers."""
    content = [{"type": "text", "text": entry["header"]}]
    for rel in entry["frame_files"]:
        b64 = base64.b64encode((FRAMES / rel).read_bytes()).decode()
        content.append({"type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64}"}})
    content.append({"type": "text", "text": entry["text"]})
    return content


def run_req(entry, cache_prompt=False, want_logprobs=True):
    qid = entry["question_id"]; N = entry["n"]
    content = build_content(entry)
    payload = {"model": "m", "messages": [{"role": "user", "content": content}],
               "stream": True, "stream_options": {"include_usage": True}, **GEN}
    if cache_prompt is not None:
        payload["cache_prompt"] = cache_prompt
    if want_logprobs:
        payload["logprobs"] = True
        payload["top_logprobs"] = 5
    req = urllib.request.Request(f"{dfl.BASE}/v1/chat/completions",
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    clk0 = dfl.gpu_freq()
    toks = []; lp_content = []; wall_start = time.time(); t0 = time.perf_counter()
    ttft = None; timings = None
    resp = urllib.request.urlopen(req)
    for raw in resp:
        line = raw.decode("utf-8", "replace").strip()
        if not line.startswith("data: "):
            continue
        d = line[6:]
        if d == "[DONE]":
            break
        o = json.loads(d)
        if o.get("timings"):
            timings = o["timings"]
        ch = o.get("choices") or [{}]
        c0 = ch[0] if ch else {}
        delta = c0.get("delta", {}) if c0 else {}
        lp = c0.get("logprobs") if c0 else None
        if lp and lp.get("content"):
            lp_content.extend(lp["content"])
        now = time.perf_counter()
        for lab, key in (("reason", "reasoning_content"), ("answer", "content")):
            if delta.get(key):
                if ttft is None:
                    ttft = now - t0
                toks.append((lab, delta[key]))
    total = time.perf_counter() - t0
    wall_end = time.time()
    clk1 = dfl.gpu_freq()
    ans = "".join(t for l, t in toks if l == "answer")
    rea = "".join(t for l, t in toks if l == "reason")
    m = re.search(r"\b([A-E])\b", ans) or re.search(r"\b([A-E])\b", rea[-50:] if rea else "")
    pred = m.group(1) if m else None
    # logprob of the first answer-letter token (and top alternatives), if provided
    ans_lp = None
    for tk in lp_content:
        tokstr = (tk.get("token") or "").strip()
        if re.fullmatch(r"[A-E]", tokstr):
            ans_lp = {"token": tokstr, "logprob": tk.get("logprob"),
                      "top": [{"token": (a.get("token") or "").strip(), "logprob": a.get("logprob")}
                              for a in (tk.get("top_logprobs") or [])][:5]}
            break
    tim = timings or {}
    return {
        "question_id": qid, "N": N, "n_frames": len(entry["frame_files"]),
        "video_id": entry["video_id"], "question_category": entry["question_category"],
        "cache_prompt": cache_prompt,
        "input_tokens": tim.get("prompt_n"), "prefill_ms": tim.get("prompt_ms"),
        "cached_n": tim.get("cache_n"),
        "ttft_s": round(ttft, 4) if ttft else None,
        "total_latency_s": round(total, 4),
        "n_gen": tim.get("predicted_n"),
        "answer_text": ans[:64],
        "pred": pred, "correct_letter": entry.get("correct_letter"),
        "correct": (pred == entry.get("correct_letter")) if pred else False,
        "answer_logprob": ans_lp,
        "gpu_clock_before": clk0, "gpu_clock_after": clk1,
        "clock_ok": (clk0 == PINNED_HZ and clk1 == PINNED_HZ),
        "wall_start": wall_start, "wall_end": wall_end,
    }


# ── bootstrap / accuracy ──────────────────────────────────────────────────────
def video_bootstrap_ci(rows, nboot=N_BOOT, seed=0):
    """Resample videos (clusters) with replacement; return point acc + 95% CI."""
    by_vid = {}
    for r in rows:
        if r["pred"] is None:
            by_vid.setdefault(r["video_id"], []).append(0)
        else:
            by_vid.setdefault(r["video_id"], []).append(1 if r["correct"] else 0)
    vids = list(by_vid.keys())
    allv = [v for vs in by_vid.values() for v in vs]
    point = sum(allv) / len(allv) if allv else None
    rng = random.Random(seed)
    accs = []
    for _ in range(nboot):
        samp = rng.choices(vids, k=len(vids))
        num = 0; den = 0
        for v in samp:
            vs = by_vid[v]; num += sum(vs); den += len(vs)
        if den:
            accs.append(num / den)
    accs.sort()
    lo = accs[int(0.025 * len(accs))] if accs else None
    hi = accs[int(0.975 * len(accs)) - 1] if accs else None
    return {"accuracy": round(point, 4) if point is not None else None,
            "ci95": [round(lo, 4), round(hi, 4)] if accs else None,
            "n_questions": len(allv), "n_videos": len(vids)}


def per_stratum(rows):
    out = {}
    by_s = {}
    for r in rows:
        by_s.setdefault(r["question_category"], []).append(r)
    for s, rs in sorted(by_s.items()):
        ci = video_bootstrap_ci(rs)
        out[s] = {"n": len(rs), "accuracy": ci["accuracy"], "ci95": ci["ci95"]}
    return out


def summarise_accuracy(rows):
    overall = video_bootstrap_ci(rows)
    preds = [r for r in rows if r["pred"] is not None]
    cached = [r["cached_n"] for r in rows]
    return {
        "n": len(rows), "n_parsed": len(preds),
        "unparsed_rate": round(1 - len(preds) / len(rows), 4) if rows else None,
        "accuracy": overall["accuracy"], "ci95": overall["ci95"],
        "n_videos": overall["n_videos"], "random_baseline": RANDOM_BASELINE,
        "input_tokens_p50": int(st.median([r["input_tokens"] for r in rows if r["input_tokens"]])) if rows else None,
        "cached_n_min": min(cached) if cached else None, "cached_n_max": max(cached) if cached else None,
        "clock_bad_rows": sum(0 if r["clock_ok"] else 1 for r in rows),
        "per_stratum": per_stratum(rows),
    }


# ── Part A: accuracy over all 845 q at each N ─────────────────────────────────
def phase_A(by_key, qid_order, Ns=(1, 3, 9)):
    outp = OUTDIR / "partA_accuracy.jsonl"
    done = set()
    if outp.exists():
        for l in open(outp):
            try:
                r = json.loads(l); done.add((r["question_id"], r["N"]))
            except Exception:
                pass
    fout = open(outp, "a")
    rows_by_n = {N: [] for N in Ns}
    # pre-load any existing rows for resume
    if done:
        for l in open(outp):
            r = json.loads(l)
            if r["N"] in rows_by_n:
                rows_by_n[r["N"]].append(r)
    throttled = None
    for N in Ns:
        todo = [q for q in qid_order if (q, N) not in done]
        print(f"Part A N={N}: {len(todo)} to run ({len(qid_order)-len(todo)} already done)", flush=True)
        t_start = time.time()
        for i, qid in enumerate(todo, 1):
            # throttle guard (cheap read of the gpu clock trend is not enough; read tj via a short tegrastats? skip — use thermal zone)
            r = run_req(by_key[(qid, N)])
            r["part"] = "A"
            fout.write(json.dumps(r) + "\n"); fout.flush()
            rows_by_n[N].append(r)
            if i % 100 == 0 or i == len(todo):
                acc = sum(1 for x in rows_by_n[N] if x["correct"]) / len(rows_by_n[N])
                el = time.time() - t_start
                rate = el / i if i else 0
                print(f"  [A N={N}] {i}/{len(todo)} acc_so_far={acc:.3f} "
                      f"ttft={r['ttft_s']}s cached_n={r['cached_n']} clk_ok={r['clock_ok']} "
                      f"{el:.0f}s ({rate:.2f}s/req, eta {rate*(len(todo)-i):.0f}s)", flush=True)
    fout.close()
    out = {"by_N": {}}
    for N in Ns:
        out["by_N"][str(N)] = summarise_accuracy(rows_by_n[N])
        s = out["by_N"][str(N)]
        print(f"  Part A N={N}: acc={s['accuracy']} CI{s['ci95']} "
              f"(n={s['n']}, {s['n_videos']} videos, unparsed={s['unparsed_rate']}, "
              f"cached_n<= {s['cached_n_max']}, clk_bad={s['clock_bad_rows']})", flush=True)
    out["throttled"] = throttled
    return out, rows_by_n


# ── repeat determinism control ────────────────────────────────────────────────
def repeat_control(by_key, qid_order, N=9, k=15):
    qids = qid_order[:k]
    pairs = []
    for qid in qids:
        a = run_req(by_key[(qid, N)]); b = run_req(by_key[(qid, N)])
        pairs.append({"question_id": qid, "N": N, "pred_a": a["pred"], "pred_b": b["pred"],
                      "same": a["pred"] == b["pred"], "cached_n_a": a["cached_n"], "cached_n_b": b["cached_n"]})
    json.dump(pairs, open(OUTDIR / "repeat_control.json", "w"), indent=2)
    same = sum(1 for p in pairs if p["same"])
    return {"n": len(pairs), "identical": same, "match_rate": round(same / len(pairs), 4) if pairs else None,
            "cached_n_max": max([p["cached_n_a"] for p in pairs] + [p["cached_n_b"] for p in pairs] + [0])}


# ── Part B: latency (50 req / N, first-after-load discarded, energy) ──────────
def latency_stats(rows, N):
    ttfts = [r["ttft_s"] for r in rows]
    lats = [r["total_latency_s"] for r in rows]
    ej = [r["energy"]["energy_j"] for r in rows if r.get("energy")]
    rail = {k: [r["energy"][k] for r in rows if r.get("energy") and r["energy"].get(k) is not None]
            for k in ("gpu_j", "cpu_j", "sys_j")}
    toks = [r["input_tokens"] for r in rows if r["input_tokens"] is not None]
    cached = [r["cached_n"] for r in rows]
    out = {
        "N": N, "n": len(rows),
        "input_tokens_p50": int(st.median(toks)) if toks else None,
        "ttft_s": {"p50": pct(ttfts, 50), "p90": pct(ttfts, 90), "p99": pct(ttfts, 99)},
        "total_latency_s": {"p50": pct(lats, 50), "p90": pct(lats, 90), "p99": pct(lats, 99),
                            "max": round(max(lats), 4) if lats else None},
        "energy_j_per_req": {"p50": pct(ej, 50), "p90": pct(ej, 90)},
        "rail_energy_j_p50": {k: pct(v, 50) for k, v in rail.items()},
        "cached_n_min": min(cached) if cached else None, "cached_n_max": max(cached) if cached else None,
        "clock_bad_rows": sum(0 if r["clock_ok"] else 1 for r in rows),
    }
    ref = D_REF.get(N)
    if ref and out["ttft_s"]["p50"]:
        out["vs_d_ref_ttft_p50"] = {"ref_s": ref, "ratio": round(out["ttft_s"]["p50"] / ref, 4)}
    return out


def phase_B(by_key, qid_order, sampler, Ns=(1, 3, 9), per_n=50):
    fout = open(OUTDIR / "partB_latency.jsonl", "w")
    out = {}
    throttled = None
    for N in Ns:
        # warm-up: first-after-load discarded
        warm = run_req(by_key[(qid_order[0], N)])
        time.sleep(1.0)
        rows = []
        for i in range(per_n):
            qid = qid_order[i % len(qid_order)]
            tj = recent_tj(sampler)
            if tj is not None and tj >= STOP_TJ:
                throttled = {"tj": tj, "N": N, "after": len(rows)}; break
            r = run_req(by_key[(qid, N)])
            r["part"] = "B"
            time.sleep(SETTLE)
            r["energy"] = dfl.integrate(sampler.snapshot(), r["wall_start"], r["wall_end"])
            rows.append(r); fout.write(json.dumps(r) + "\n"); fout.flush()
            time.sleep(0.5)
        out[str(N)] = latency_stats(rows, N)
        s = out[str(N)]
        print(f"  Part B N={N}: TTFT p50/p90/p99={s['ttft_s']['p50']}/{s['ttft_s']['p90']}/"
              f"{s['ttft_s']['p99']}s total p50/p99={s['total_latency_s']['p50']}/"
              f"{s['total_latency_s']['p99']}s E/req p50={s['energy_j_per_req']['p50']}J "
              f"vs_ref={s.get('vs_d_ref_ttft_p50')}", flush=True)
    fout.close()
    out["throttled"] = throttled
    return out


# ── agreement with H100 4B (StudyF1), if predictions supplied ─────────────────
def load_h100_preds(path):
    """Accept jsonl or json. Return {(qid, N): letter}. Tolerant of field names."""
    p = Path(path)
    preds = {}
    def letter_of(d):
        for k in ("pred", "prediction", "pred_letter", "answer_letter", "letter", "model_letter"):
            if d.get(k):
                m = re.search(r"\b([A-E])\b", str(d[k]))
                if m:
                    return m.group(1)
        return None
    def nof(d):
        for k in ("N", "n", "n_frames"):
            if d.get(k) is not None:
                return int(d[k])
        return None
    if p.suffix == ".jsonl" or p.suffix == ".gz":
        import gzip
        op = gzip.open if p.suffix == ".gz" else open
        for l in op(p, "rt"):
            l = l.strip()
            if not l:
                continue
            d = json.loads(l)
            q = d.get("question_id") or d.get("qid"); N = nof(d); lt = letter_of(d)
            if q and N is not None:
                preds[(q, N)] = lt
    else:
        data = json.load(open(p))
        rows = data if isinstance(data, list) else data.get("rows", [])
        for d in rows:
            q = d.get("question_id") or d.get("qid"); N = nof(d); lt = letter_of(d)
            if q and N is not None:
                preds[(q, N)] = lt
    return preds


def agreement(rows_by_n, h100_path):
    preds = load_h100_preds(h100_path)
    out = {"h100_predictions_file": str(h100_path), "n_h100_preds": len(preds), "by_N": {}}
    for N, rows in rows_by_n.items():
        matched = 0; agree = 0; both_parsed = 0
        for r in rows:
            key = (r["question_id"], N)
            if key in preds:
                matched += 1
                hp = preds[key]
                if hp is not None and r["pred"] is not None:
                    both_parsed += 1
                    if hp == r["pred"]:
                        agree += 1
        rate = (agree / both_parsed) if both_parsed else None
        out["by_N"][str(N)] = {"matched_questions": matched, "both_parsed": both_parsed,
                               "agree": agree, "agreement_rate": round(rate, 4) if rate is not None else None,
                               "below_90pct_FLAG": (rate is not None and rate < 0.90)}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--parts", default="AB")
    ap.add_argument("--h100-preds", default=None, help="path to StudyF1 H100 4B per-question predictions")
    a = ap.parse_args()
    OUTDIR.mkdir(parents=True, exist_ok=True)

    clk = dfl.gpu_freq()
    print(f"preflight clock={clk} pinned={PINNED_HZ} ok={clk == PINNED_HZ}", flush=True)
    if clk != PINNED_HZ:
        print("STOP: clock wrong", flush=True); return
    vin = verify_inputs()
    print(f"input sha256: ok={vin['ok']}/{vin['checked']} bad={vin['n_bad']} res={vin['resolution']}", flush=True)
    if vin["n_bad"]:
        print(f"STOP: input hash mismatch {vin['bad']}", flush=True); return

    by_key, qid_order = load_manifest()
    if a.smoke:
        qid_order = qid_order[:8]
    print(f"manifest: {len(qid_order)} questions x N{{1,3,9}}", flush=True)

    summary = {"config": {"model": "Qwen3VL-4B-Instruct-F16", "commit": "c0fd786",
                          "server_build": "0.7.0-dev build 1 commit c0fd786",
                          "cache_prompt": False, "gen": GEN, "max_tokens": MAX_TOKENS,
                          "pinned_hz": PINNED_HZ, "logprobs": True,
                          "prompt": "StudyF1 template from f1_inputs_manifest.jsonl (header -> images -> MCQ text; no [t=Xs] markers)",
                          "frames": "StudyF1-shortwin archive (same bytes as H100 StudyF1 4B), 560x560",
                          "input_sha256_verify": vin,
                          "n_questions": len(qid_order), "n_videos_total": 234,
                          "d_series_ttft_ref": D_REF}, "parts": {}}
    json.dump(summary, open(OUTDIR / "study_f4_summary.json", "w"), indent=2)

    rows_by_n = None
    server = None
    try:
        print("launching server (4bi_f16)...", flush=True)
        server = dfl.launch_server("4bi_f16", dfl.SCRATCH / "study_f4_server.log")

        if "A" in a.parts:
            Ns = (1, 3, 9)
            partA, rows_by_n = phase_A(by_key, qid_order, Ns=Ns)
            summary["parts"]["A"] = partA
            # determinism control (greedy repeat)
            print("repeat determinism control (N=9) ...", flush=True)
            summary["parts"]["A"]["repeat_control"] = repeat_control(by_key, qid_order, N=9,
                                                                     k=3 if a.smoke else 15)
            print(f"  repeat control: {summary['parts']['A']['repeat_control']}", flush=True)
            json.dump(summary, open(OUTDIR / "study_f4_summary.json", "w"), indent=2)

        if "B" in a.parts:
            bgz = OUTDIR / "partB_baseline_tegrastats.jsonl.gz"
            bsamp = dfl.Sampler(bgz)
            bsec = 10 if a.smoke else 120
            print(f"Part B baseline: {bsec}s loaded-idle ...", flush=True)
            b0 = time.time(); time.sleep(bsec); b1 = time.time()
            summary["parts"].setdefault("B", {})["baseline"] = dfl.idle_stats(bsamp.snapshot(), b0, b1)
            bsamp.stop()
            print(f"  baseline: {summary['parts']['B']['baseline']}", flush=True)
            samp = dfl.Sampler(OUTDIR / "partB_latency_tegrastats.jsonl.gz")
            try:
                bres = phase_B(by_key, qid_order, samp, Ns=(1, 3, 9), per_n=5 if a.smoke else 50)
            finally:
                samp.stop()
            summary["parts"]["B"].update(bres)
            json.dump(summary, open(OUTDIR / "study_f4_summary.json", "w"), indent=2)
    finally:
        if server is not None:
            dfl.stop_server(server)
            print("server stopped", flush=True)

    # agreement (post-hoc, no GPU)
    if a.h100_preds and rows_by_n is not None:
        print(f"agreement vs H100 4B: {a.h100_preds}", flush=True)
        summary["parts"].setdefault("A", {})["agreement_h100_4b"] = agreement(rows_by_n, a.h100_preds)
        print(f"  agreement: {summary['parts']['A']['agreement_h100_4b']['by_N']}", flush=True)
    else:
        summary["parts"].setdefault("A", {})["agreement_h100_4b"] = {
            "status": "PENDING — StudyF1 H100 4B per-question predictions not supplied; rerun with --h100-preds <path>"}

    summary["_provenance"] = stamp(script="study_f4_device_shortwin.py", model="4bi_f16",
                                   device="jetson_orin", n=len(qid_order), seed=0)
    json.dump(summary, open(OUTDIR / "study_f4_summary.json", "w"), indent=2)
    print("StudyF4-device-shortwin complete.", flush=True)


if __name__ == "__main__":
    main()
