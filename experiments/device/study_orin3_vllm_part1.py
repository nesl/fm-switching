#!/usr/bin/env python3
"""StudyORIN3-vllm Part 1 - monitoring scores and latency under vLLM on the Jetson Orin.

Measures the device tier with vLLM 0.20.0+cu126 (same engine family as the H100 cloud),
so the device baseline does not depend on choosing llama.cpp. Same model, inputs and device
as StudyORIN1-dense / StudyORIN2-stack; only the serving stack changes.

Request contract is BYTE-IDENTICAL to StudyD15 (and d3_infer_vllm.body):
  header (from manifest) -> one SMALL 768x432 PNG (data URI) -> the Nexar collision QUERY.
Greedy, seed 0, max_tokens 8, logprobs top 20. Serial: the server runs max-num-seqs 1 and
this client sends ONE request at a time. Prefix caching is ON (stack setting); per request we
record prompt_tokens and cached_tokens, and Part 1 latency is labelled "warm header" because
only the shared header prefix before the image can be cached (image and question tokens are
always computed). A separate --coldcheck pass (prefix caching OFF server) re-times a seeded
200-request subsample.

Two request sets:
  d3dev : the 6,010 StudyD3 DEV N=1 requests (601 clips x 10 offsets), identical to the set
          StudyORIN2 scored (verified against orin2_d3dev_scores.jsonl.gz request_ids).
  d14b  : a 2,000-request sample of the StudyORIN1 D14b evaluation requests (300 val clips),
          stratified by clip-level label, seed 0 (sampling stated in the gate/meta output).

Subcommands: --gate / --score / --analyse (+ --set d3dev|d14b, --coldcheck).
Server launched separately by orin3_serve.sh; this script only talks to 127.0.0.1:8000.
"""
import argparse, base64, csv, gzip, hashlib, json, math, os, random, statistics as st, sys, time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent.parent
OUTD = ROOT / "results/dashcam/study_orin3"
COSTD = ROOT / "results/cost/study_orin3"
D3DIR = ROOT / "results/dashcam/study_d3_nexar"
D3_REQMAN = D3DIR / "d3_requests_manifest.jsonl"
D3_FRAMEMAN = D3DIR / "frames_sha256_manifest.jsonl.gz"
D3_H100 = D3DIR / "d3_requests_h100nvl.jsonl.gz"
SPLIT = ROOT / "results/dashcam/study_d2_nexar/nexar_train_split_seed0.csv"
D14DIR = Path("/home/nesl/data/d14_n1")
D14B = ROOT / "results/dashcam/study_d14b"
D14_REQMAN = D14B / "d14b_requests_manifest.jsonl.gz"   # dense 0.25-s grid, the set ORIN1 scored
D14_FRAMEMAN = D14B / "frames_sha256_manifest.jsonl.gz"
ORIN1_DENSE = ROOT / "results/dashcam/study_orin1/orin1_dense_scores.jsonl.gz"
D14B_H100 = ROOT / "results/dashcam/study_d14b/d14b_trace_h100nvl.jsonl.gz"
ORIN2_SCORES = ROOT / "results/dashcam/study_orin2/orin2_d3dev_scores.jsonl.gz"

# committed comparison maps (StudyCTRL1c / StudyORIN2)
H100_4B_MAP = {"a": 0.114603, "b": 1.140751}
H100_32B_MAP = {"a": 0.129472, "b": 1.848187}
ORIN_LLAMACPP_MAP = {"a": 0.114932, "b": 1.174287}

BASE = "http://127.0.0.1:8000"
MODEL = "qwen3vl4b"
QUERY = ("Is a collision or near-collision involving the camera vehicle happening or about to happen? "
         "Answer only Yes or No.")
GEN = dict(temperature=0.0, max_tokens=8, seed=0, logprobs=True, top_logprobs=20)
SAMPLE_N = 2000
SAMPLE_SEED = 0
COLDCHECK_N = 200
COLDCHECK_SEED = 0
ATTEMPTS = 3
TRANSPORT = ("ReadError", "RemoteProtocolError", "ConnectError", "WriteError", "ReadTimeout",
             "ConnectTimeout", "PoolTimeout", "WriteTimeout", "CloseError")


def scores_path(setname, cold=False):
    tag = f"orin3_{setname}_scores"
    if cold:
        tag = f"orin3_{setname}_coldcheck_scores"
    return OUTD / (tag + ".jsonl")


# ---------------------------------------------------------------- request sets
def dev_clips():
    dev = set()
    with open(SPLIT) as f:
        for row in csv.DictReader(f):
            if row["split"] == "dev":
                dev.add(row["file_name"].replace(".mp4", ""))
    return dev


def load_d3_dev_n1():
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


def _d14_manifest():
    man = {}
    with gzip.open(D14_REQMAN, "rt") as f:
        for line in f:
            r = json.loads(line)
            man[r["request_id"]] = r
    return man


def load_d14b_sample(n=SAMPLE_N, seed=SAMPLE_SEED):
    """Stratified sample of the StudyD14b evaluation requests that StudyORIN1 scored.

    ORIN1 scored all 42,014 N=1 requests on the 0.25-s dense grid, but only the 10,660
    integer-second frames are resident on the Orin (the fractional-second frames were cleaned
    up after ORIN1). Per the brief's 'frames as available' rule, the sample is drawn from the
    ORIN1-scored requests whose frame is present on disk (the integer-second subset). Strata =
    clip-level label (positive/negative), drawn proportionally to the AVAILABLE pool with a fixed
    seed. Each sampled request carries its ORIN1 llama.cpp score/latency for the paired comparison.
    Exact counts and the availability restriction are returned in meta."""
    orin1 = {}
    with gzip.open(ORIN1_DENSE, "rt") as g:
        for line in g:
            d = json.loads(line)
            orin1[d["request_id"]] = d
    # dense manifest, N=1, that ORIN1 scored and whose frame is on disk
    avail = []
    with gzip.open(D14_REQMAN, "rt") as f:
        for line in f:
            r = json.loads(line)
            if r.get("n") != 1 or r["request_id"] not in orin1:
                continue
            if not frame_path(r).exists():
                continue
            avail.append(r)
    pos = [r for r in avail if str(r.get("label")).lower() == "positive"]
    neg = [r for r in avail if str(r.get("label")).lower() != "positive"]
    n = min(n, len(avail))
    frac = n / len(avail)
    n_pos = round(len(pos) * frac)
    n_neg = n - n_pos
    rng = random.Random(seed)
    samp = rng.sample(pos, n_pos) + rng.sample(neg, n_neg)
    samp.sort(key=lambda r: (r["file_name"], float(r["t"])))
    reqs = []
    for r in samp:
        d = orin1[r["request_id"]]
        req = dict(r)
        req["_orin1_score"] = d.get("score")
        req["_orin1_p_yes"] = d.get("p_yes")
        req["_orin1_ttft_s"] = d.get("ttft_s")
        req["_orin1_total_s"] = d.get("total_s")
        req["_dense_request_id"] = r["request_id"]
        reqs.append(req)
    meta = dict(n_orin1_scored=len(orin1), n_available_on_disk=len(avail),
                n_available_pos=len(pos), n_available_neg=len(neg),
                n_requested=SAMPLE_N, n_sampled=len(reqs), n_pos=n_pos, n_neg=n_neg,
                base_rate_available=round(len(pos) / len(avail), 4),
                base_rate_sample=round(sum(1 for r in reqs if str(r["label"]).lower() == "positive")
                                       / max(1, len(reqs)), 4),
                seed=seed,
                strata="clip-level label (positive/negative), proportional to the available pool",
                availability_note=("only the 10,660 integer-second frames are resident on the Orin; "
                                   "the 0.25-s fractional frames were cleaned up after StudyORIN1, so "
                                   "the sample is the integer-second subset of the ORIN1-scored grid"))
    return reqs, meta


def load_set(setname):
    if setname == "d3dev":
        reqs = load_d3_dev_n1()
        meta = dict(n=len(reqs), n_clips=len(set(r["file_name"] for r in reqs)))
        # verify identical to the set StudyORIN2 scored
        if ORIN2_SCORES.exists():
            with gzip.open(ORIN2_SCORES, "rt") as g:
                o2 = {json.loads(l)["request_id"] for l in g}
            mine = {r["request_id"] for r in reqs}
            meta["matches_orin2_set"] = (mine == o2)
            meta["orin2_set_n"] = len(o2)
            assert mine == o2, ("d3dev set differs from StudyORIN2: "
                                f"+{len(mine - o2)} -{len(o2 - mine)}")
        return reqs, meta
    if setname == "d14b":
        return load_d14b_sample()
    raise SystemExit("unknown set " + setname)


def frame_path(req):
    clip = req["file_name"].replace(".mp4", "")
    return D14DIR / clip / f"{req['frame_keys'][0]}.png"


# ---------------------------------------------------------------- frame gate
def gate(reqs, setname):
    frameman = D3_FRAMEMAN if setname == "d3dev" else D14_FRAMEMAN
    man = {}
    if frameman.exists():
        with gzip.open(frameman, "rt") as f:
            for line in f:
                r = json.loads(line)
                man[(r["file_name"], r["key"])] = r.get("small_sha256") or r.get("sha256")
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
    res = {"set": setname, "ok": ok, "checked": n, "n_reqs": len(reqs),
           "n_clips": len(set(r["file_name"] for r in reqs)),
           "missing": len(missing), "mismatch": len(mismatch),
           "missing_ex": missing[:5], "mismatch_ex": mismatch[:5],
           "frame_manifest": (str(frameman) if frameman.exists() else "manifest-absent-used-req-sha256")}
    OUTD.mkdir(parents=True, exist_ok=True)
    json.dump(res, open(OUTD / f"orin3_part1_{setname}_frame_gate.json", "w"), indent=1)
    print(f"[gate:{setname}] ok={ok} checked={n}/{len(reqs)} "
          f"missing={len(missing)} mismatch={len(mismatch)}", flush=True)
    return ok


# ---------------------------------------------------------------- scoring (streaming for TTFT)
def build_content(req):
    hdr = req["header"]
    b = frame_path(req).read_bytes()
    content = [{"type": "text", "text": hdr},
               {"type": "image_url",
                "image_url": {"url": "data:image/png;base64," + base64.b64encode(b).decode()}},
               {"type": "text", "text": QUERY}]
    return content


def yes_no(top):
    if not top:
        return None, None, None
    y = sum(math.exp(t["logprob"]) for t in top if t["token"].strip().lower() == "yes")
    n = sum(math.exp(t["logprob"]) for t in top if t["token"].strip().lower() == "no")
    return (None if y + n == 0 else y / (y + n)), y, n


def score_one(client, req):
    body = dict(model=MODEL, messages=[{"role": "user", "content": build_content(req)}],
                stream=True, stream_options={"include_usage": True}, **GEN)
    t0 = time.time()
    ttft = None
    first_top = None
    first_token = None
    text = ""
    usage = {}
    err = None
    try:
        with client.stream("POST", f"{BASE}/v1/chat/completions", json=body) as r:
            if r.status_code != 200:
                return {"error": f"HTTP {r.status_code}: {r.read()[:300]}"}
            for line in r.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    break
                j = json.loads(data)
                if j.get("usage"):
                    usage = j["usage"]
                ch = j.get("choices") or []
                if not ch:
                    continue
                delta = ch[0].get("delta") or {}
                piece = delta.get("content") or ""
                lp = (ch[0].get("logprobs") or {}).get("content") or []
                if piece and ttft is None:
                    ttft = time.time() - t0
                if lp and first_top is None:
                    first_top = lp[0].get("top_logprobs")
                    first_token = lp[0].get("token")
                text += piece
    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {e}"
    total = time.time() - t0
    p, y, n = yes_no(first_top)
    details = (usage.get("prompt_tokens_details") or {})
    cached = details.get("cached_tokens")
    return {"error": err, "text": text.strip(), "first_token": first_token,
            "p_yes": p, "mass_yes": y, "mass_no": n,
            "neither": (p is None and not err),
            "prompt_tokens": usage.get("prompt_tokens"), "cached_tokens": cached,
            "completion_tokens": usage.get("completion_tokens"),
            "ttft_s": round(ttft, 4) if ttft is not None else None,
            "total_s": round(total, 4), "top_k": len(first_top) if first_top else 0}


def read_clock_hz():
    for p in ("/sys/devices/gpu.0/devfreq/17000000.gpu/cur_freq",
              "/sys/class/devfreq/17000000.gpu/cur_freq"):
        try:
            return int(Path(p).read_text().strip())
        except Exception:
            continue
    return None


def score(reqs, setname, cold=False, resume=True):
    sp = scores_path(setname, cold)
    OUTD.mkdir(parents=True, exist_ok=True)
    done = set()
    if resume and sp.exists():
        for line in open(sp):
            try:
                done.add(json.loads(line)["request_id"])
            except Exception:
                pass
    mode = "a" if (resume and sp.exists()) else "w"
    f = open(sp, mode)
    todo = [r for r in reqs if r["request_id"] not in done]
    print(f"[score:{setname}{' COLD' if cold else ''}] {len(todo)} to run "
          f"({len(done)} already done)", flush=True)
    t0 = time.time()
    n = 0
    with httpx.Client(timeout=httpx.Timeout(180.0)) as client:
        for req in todo:
            rec = None
            for attempt in range(1, ATTEMPTS + 1):
                rec = score_one(client, req)
                e = rec.get("error")
                if e and e.split(":")[0] in TRANSPORT and attempt < ATTEMPTS:
                    time.sleep(0.5)
                    continue
                break
            row = {"request_id": req["request_id"],
                   "file_name": req["file_name"],
                   "clip": req["file_name"].replace(".mp4", ""),
                   "offset": float(req["offset"]) if "offset" in req else None,
                   "t": req.get("t"),
                   "label": req.get("label"), "gt": req.get("gt"),
                   "score": (math.log(max(rec["p_yes"], 1e-12)) if rec.get("p_yes") is not None else None),
                   "clock_hz": read_clock_hz(), **rec}
            if setname == "d14b":
                row["orin1_score"] = req.get("_orin1_score")
                row["orin1_ttft_s"] = req.get("_orin1_ttft_s")
                row["orin1_total_s"] = req.get("_orin1_total_s")
                row["dense_request_id"] = req.get("_dense_request_id")
            f.write(json.dumps(row) + "\n"); f.flush()
            n += 1
            if n % 250 == 0:
                rate = n / max(1e-9, time.time() - t0)
                eta = (len(todo) - n) / max(1e-9, rate) / 60
                print(f"[score:{setname}{' COLD' if cold else ''}] {n}/{len(todo)} "
                      f"{rate:.2f} req/s ETA {eta:.0f} min last_score={row['score']}", flush=True)
    f.close()
    print(f"[score:{setname}{' COLD' if cold else ''}] done: {n} new rows", flush=True)
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", choices=["d3dev", "d14b"], default="d3dev")
    ap.add_argument("--gate", action="store_true")
    ap.add_argument("--score", action="store_true")
    ap.add_argument("--coldcheck", action="store_true",
                    help="score a seeded 200-request subsample (run against a prefix-caching-OFF server)")
    ap.add_argument("--analyse", action="store_true")
    ap.add_argument("--no-resume", action="store_true")
    args = ap.parse_args()
    OUTD.mkdir(parents=True, exist_ok=True); COSTD.mkdir(parents=True, exist_ok=True)

    if args.gate or args.score or args.coldcheck:
        reqs, meta = load_set(args.set)
        print(f"[load:{args.set}] {len(reqs)} requests; meta={json.dumps(meta)}", flush=True)
        json.dump(meta, open(OUTD / f"orin3_part1_{args.set}_setmeta.json", "w"), indent=1)
        ok = gate(reqs, args.set)
        if not ok:
            print(f"[{args.set}] GATE FAILED - stopping before scoring.", flush=True)
            sys.exit(2)
        if args.coldcheck:
            rng = random.Random(COLDCHECK_SEED)
            sub = rng.sample(reqs, min(COLDCHECK_N, len(reqs)))
            json.dump({"n": len(sub), "seed": COLDCHECK_SEED,
                       "request_ids": [r["request_id"] for r in sub]},
                      open(OUTD / f"orin3_part1_{args.set}_coldcheck_ids.json", "w"), indent=1)
            score(sub, args.set, cold=True, resume=not args.no_resume)
        elif args.score:
            score(reqs, args.set, cold=False, resume=not args.no_resume)
    if args.analyse:
        import study_orin3_analyse as A  # separate analysis module
        A.analyse(args.set)


if __name__ == "__main__":
    main()
