#!/usr/bin/env python3
"""
StudyD15-orin-nexar (Part A) + StudyD15b-device-overhead (Part B) — Jetson Orin.

Part A: validate the H100 4B-I N=1 Nexar scores (used as the Orin stand-in in
  E9/E9b/E12) by rescoring all 10,660 D14 N=1 requests on the Orin.
  Requests rebuilt byte-identically to D14/D3 (d3_infer_vllm.body contract):
  header (from manifest) + one SMALL 768x432 PNG (data URI) + the D3 query.
  Score exactly as D14: P(Yes) = Yes/(Yes+No) first-token top-k mass;
  score = log P(Yes) floored at 1e-12. Yes/No missing from top-k recorded
  (not imputed). 100 grey-frame control. cache_prompt FALSE (cold), greedy,
  seed 0, max_tokens 8, top_logprobs 20. One request at a time, clip+time order.

Part B: diagnose E8's per-request TTFT growth. One StudyE7 D2 session, warm
  (cache_prompt true); at history sizes 50/150/300/480 frames, 10 appends each;
  log client build+serialize time, body bytes, server-log slice, TTFT. Plus a
  base64+PNG-decode microbench (one 352x256 frame, median of 200).

STACK (as StudyF4/E8): llama.cpp c0fd786, Qwen3VL-4B-Instruct-F16 (+mmproj-F16),
  sha256 verified; MAXN mode 0, GPU pinned 1.3005 GHz; greedy; seed 0.

Outputs under results/device/study_d15/.
"""
import argparse, base64, gzip, hashlib, io, json, math, os, re, statistics as st, sys, time, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import experiments.device.dev_fast_latency as dfl
import experiments.device.study_e8_device_warm as e8
from experiments.lib._provenance import stamp

ROOT = Path(__file__).resolve().parent.parent.parent
OUTDIR = ROOT / "results/device/study_d15"
D14DIR = Path("/home/nesl/data/d14_n1")
REQMAN = D14DIR / "d14_requests_manifest.jsonl.gz"
FRAMEMAN = D14DIR / "frames_sha256_manifest.jsonl.gz"
H100TRACE = ROOT / "results/dashcam/study_d14_trace/d14_trace_h100nvl.jsonl.gz"

MODEL_TAG = "4bi_f16"
PINNED_HZ = 1300500000
N_CTX = 57344                # Part A needs ~386; Part B D2 history up to session max (~52k tok) must fit
SEED = 0
TOP_LOGPROBS = 20
MAX_TOKENS = 8
STOP_TJ = 90.0
QUERY = ("Is a collision or near-collision involving the camera vehicle happening or about to happen? "
         "Answer only Yes or No.")
GREY_SIZE = (768, 432)
N_GREY = 100


# ── inputs ───────────────────────────────────────────────────────────────────
def load_n1_requests():
    """All N=1 requests from the D14 manifest, clip+time ordered."""
    reqs = []
    with gzip.open(REQMAN, "rt") as f:
        for line in f:
            r = json.loads(line)
            if int(r["n"]) == 1:
                reqs.append(r)
    reqs.sort(key=lambda r: (r["file_name"], int(r["t"])))
    return reqs


def frame_path(req):
    clip = req["file_name"].replace(".mp4", "")
    return D14DIR / clip / f"{req['frame_keys'][0]}.png"


def verify_frames(reqs):
    bad = []; miss = []; n = 0
    seen = {}
    for r in reqs:
        p = frame_path(r); exp = r["small_sha256"][0]
        if not p.exists():
            miss.append(r["request_id"]); continue
        h = seen.get(p)
        if h is None:
            h = hashlib.sha256(p.read_bytes()).hexdigest(); seen[p] = h
        n += 1
        if h != exp:
            bad.append(r["request_id"])
    ok = (not bad and not miss)
    print(f"frame sha256: ok={n}/{len(reqs)} bad={len(bad)} missing={len(miss)}", flush=True)
    if not ok:
        print("BAD:", bad[:5], "MISSING:", miss[:5], flush=True)
    return ok


def b64_bytes(b):
    return base64.b64encode(b).decode()


def build_nexar_content(req, frame_bytes=None, verify=True):
    """D3/D14 contract: header text -> one image -> query text. Byte-identical to d3_infer_vllm.body."""
    hdr = req["header"]
    content = [{"type": "text", "text": hdr}]
    if frame_bytes is None:
        b = frame_path(req).read_bytes()
        if verify:
            h = hashlib.sha256(b).hexdigest()
            assert h == req["small_sha256"][0], (req["request_id"], h, req["small_sha256"][0])
    else:
        b = frame_bytes
    content.append({"type": "image_url", "image_url": {"url": "data:image/png;base64," + b64_bytes(b)}})
    content.append({"type": "text", "text": QUERY})
    return content, hdr


def grey_png():
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", GREY_SIZE, (128, 128, 128)).save(buf, format="PNG")
    return buf.getvalue()


# ── scoring request (first-token Yes/No mass) ────────────────────────────────
def score_request(content, cache_prompt=False, timeout=120):
    """Stream a chat completion; capture the FIRST generated token's top_logprobs,
    TTFT, total, usage, timings, clock. Returns a record dict."""
    payload = {"model": "m", "messages": [{"role": "user", "content": content}],
               "stream": True, "stream_options": {"include_usage": True},
               "temperature": 0.0, "max_tokens": MAX_TOKENS, "seed": SEED,
               "cache_prompt": cache_prompt, "logprobs": True, "top_logprobs": TOP_LOGPROBS}
    data = json.dumps(payload).encode()
    body_bytes = len(data)
    req = urllib.request.Request(f"{dfl.BASE}/v1/chat/completions", data=data,
                                 headers={"Content-Type": "application/json"})
    clk0 = dfl.gpu_freq()
    first_top = None; first_token = None
    lp_seen = []
    usage = None; timings = None
    ttft = None; text = ""
    t0 = time.perf_counter(); wall_start = time.time()
    resp = urllib.request.urlopen(req, timeout=timeout)
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
        if o.get("usage"):
            usage = o["usage"]
        ch = (o.get("choices") or [{}])
        c0 = ch[0] if ch else {}
        delta = c0.get("delta", {}) if c0 else {}
        lp = c0.get("logprobs") if c0 else None
        if lp and lp.get("content"):
            for item in lp["content"]:
                lp_seen.append(item)
                if first_top is None:
                    first_top = item.get("top_logprobs") or []
                    first_token = item.get("token")
        if delta.get("content"):
            if ttft is None:
                ttft = time.perf_counter() - t0
            text += delta["content"]
    total = time.perf_counter() - t0
    wall_end = time.time()
    clk1 = dfl.gpu_freq()
    # Yes/No mass from the first token's top_logprobs
    y = n = 0.0; yes_seen = no_seen = False
    for t in (first_top or []):
        s = (t.get("token") or "").strip().lower()
        if s == "yes":
            y += math.exp(t["logprob"]); yes_seen = True
        elif s == "no":
            n += math.exp(t["logprob"]); no_seen = True
    p_yes = None if (y + n) == 0 else y / (y + n)
    score = math.log(max(p_yes, 1e-12)) if p_yes is not None else None
    tim = timings or {}; usg = usage or {}
    return {
        "p_yes": p_yes, "score": score, "mass_yes": y, "mass_no": n,
        "yes_seen": yes_seen, "no_seen": no_seen, "neither": (not yes_seen and not no_seen),
        "first_token": (first_token or "").strip(), "answer_text": text[:40],
        "n_top": len(first_top or []),
        "prompt_tokens": usg.get("prompt_tokens"), "evaluated": tim.get("prompt_n"),
        "cache_n": tim.get("cache_n"), "n_gen": tim.get("predicted_n"),
        "prompt_ms": tim.get("prompt_ms"),
        "ttft_s": round(ttft, 4) if ttft else None, "total_s": round(total, 4),
        "body_bytes": body_bytes,
        "gpu_clock_before": clk0, "gpu_clock_after": clk1,
        "clock_ok": (clk0 == PINNED_HZ and clk1 == PINNED_HZ),
        "wall_start": wall_start, "wall_end": wall_end,
    }


# ── PART A ───────────────────────────────────────────────────────────────────
def part_a(reqs, sampler, out_jsonl, resume=True, limit=None):
    done = set()
    if resume and out_jsonl.exists():
        for l in open(out_jsonl):
            try:
                done.add(json.loads(l)["request_id"])
            except Exception:
                pass
    f = open(out_jsonl, "a")
    todo = [r for r in reqs if r["request_id"] not in done]
    if limit:
        todo = todo[:limit]
    print(f"[A] {len(todo)} to run ({len(done)} already done)", flush=True)
    t_start = time.time()
    for i, req in enumerate(todo):
        content, hdr = build_nexar_content(req)
        r = score_request(content, cache_prompt=False)
        row = {"request_id": req["request_id"], "file_name": req["file_name"],
               "t": int(req["t"]), "label": req["label"],
               "time_of_event": req.get("time_of_event"), "time_of_alert": req.get("time_of_alert"),
               "duration_s": req.get("duration_s"), "scene": req.get("scene"),
               "light": req.get("light"), "weather": req.get("weather"),
               "header": hdr, "grey": False, **r}
        f.write(json.dumps(row) + "\n")
        if (i + 1) % 50 == 0:
            f.flush()
            el = time.time() - t_start
            rate = (i + 1) / el
            eta = (len(todo) - i - 1) / rate / 60.0
            print(f"  [A] {i+1}/{len(todo)} rid={req['request_id']} tok={r['prompt_tokens']} "
                  f"p_yes={None if r['p_yes'] is None else round(r['p_yes'],3)} ttft={r['ttft_s']}s "
                  f"({rate:.2f} req/s, ETA {eta:.0f} min)", flush=True)
        tj = e8.recent_tj(sampler)
        if tj and tj >= STOP_TJ:
            print(f"STOP: tj={tj} >= {STOP_TJ}", flush=True); f.close(); return False
        if not r["clock_ok"]:
            print(f"WARN clock not pinned at {req['request_id']}: {r['gpu_clock_before']}/{r['gpu_clock_after']}", flush=True)
    f.close()
    return True


def part_a_grey(reqs, out_jsonl, n=N_GREY):
    """100 grey-frame controls (header of an N=1 request, uniform RGB 128 frame)."""
    done = 0
    if out_jsonl.exists():
        done = sum(1 for _ in open(out_jsonl))
    f = open(out_jsonl, "a")
    g = grey_png()
    ref = reqs[0]
    print(f"[A] grey control: {n - done} to run", flush=True)
    for k in range(done, n):
        content, hdr = build_nexar_content(ref, frame_bytes=g, verify=False)
        r = score_request(content, cache_prompt=False)
        row = {"request_id": f"GREY_N1_{k:03d}", "file_name": None, "t": None, "label": None,
               "grey": True, "header": hdr, **r}
        f.write(json.dumps(row) + "\n"); f.flush()
    f.close()


def determinism_a(reqs, n=10):
    """10 repeated identical requests -> identical scores."""
    ref = reqs[len(reqs) // 2]
    content, _ = build_nexar_content(ref)
    scores = []
    for _ in range(n):
        r = score_request(content, cache_prompt=False)
        scores.append(r["score"])
    ident = len(set(None if s is None else round(s, 12) for s in scores)) == 1
    print(f"[A] determinism rid={ref['request_id']}: identical={ident} scores[0]={scores[0]}", flush=True)
    return {"request_id": ref["request_id"], "scores": scores, "identical": ident, "n": n}


# ── PART B: overhead diagnostic ──────────────────────────────────────────────
def microbench_decode(frame_rel, n=200):
    """Median wall time of base64-decode + PNG-decode of one frame on the Orin CPU."""
    from PIL import Image
    raw = (e8.E7DIR / frame_rel).read_bytes()
    enc = base64.b64encode(raw).decode()
    ts = []
    for _ in range(n):
        t0 = time.perf_counter()
        b = base64.b64decode(enc)
        img = Image.open(io.BytesIO(b)); img.load()
        ts.append(time.perf_counter() - t0)
    ts.sort()
    return {"frame": frame_rel, "n": n, "median_s": round(ts[n // 2], 6),
            "p10_s": round(ts[n // 10], 6), "p90_s": round(ts[9 * n // 10], 6),
            "img_size": img.size}


def part_b(reqs_e7, vids_e7, out_jsonl, hist_sizes=(50, 150, 300, 480), reps=10):
    """One E7 D2 session, warm; at each history size send `reps` appends, logging
    client build/serialize, body bytes, server-log slice, TTFT, timings."""
    # pick the longest session so 480 frames is reachable
    longest = max(vids_e7["videos"], key=lambda v: v["n_frames"])
    vid = longest["video_id"]
    frames = e8.frames_for_video(vid)
    header = e8.reqs_header(reqs_e7, vid)
    maxf = len(frames)
    sizes = [h for h in hist_sizes if h <= maxf]
    if maxf not in sizes:
        sizes = sizes + [maxf] if sizes and sizes[-1] != maxf else sizes
    print(f"[B] session {vid} max_frames={maxf} sizes={sizes}", flush=True)

    srv_log = OUTDIR / "server.log"
    e8.erase_slot()
    f = open(out_jsonl, "w")
    # warm the cache to the largest size incrementally first (so each size is a warm append)
    for h in sizes:
        # ensure cache holds the first (h-1) frames: send a priming append of h-1 frames (warm)
        prime = e8.build_append_content(header, frames[:max(1, h - 1)])
        score_request(prime, cache_prompt=True)  # warm prime (not logged)
        for rep in range(reps):
            # append request = header + first h frames (resends all h images; cache reuses h-1)
            t_b0 = time.perf_counter()
            content = e8.build_append_content(header, frames[:h])
            payload = {"model": "m", "messages": [{"role": "user", "content": content}],
                       "stream": True, "stream_options": {"include_usage": True},
                       "temperature": 0.0, "max_tokens": 1, "seed": SEED, "cache_prompt": True}
            data = json.dumps(payload).encode()
            build_serialize_s = time.perf_counter() - t_b0
            body_bytes = len(data)
            log_off = srv_log.stat().st_size if srv_log.exists() else 0
            # send
            req = urllib.request.Request(f"{dfl.BASE}/v1/chat/completions", data=data,
                                         headers={"Content-Type": "application/json"})
            clk0 = dfl.gpu_freq()
            ttft = None; timings = None; usage = None
            t0 = time.perf_counter(); wall_start = time.time()
            resp = urllib.request.urlopen(req, timeout=120)
            for raw in resp:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data: "):
                    continue
                dd = line[6:]
                if dd == "[DONE]":
                    break
                o = json.loads(dd)
                if o.get("timings"):
                    timings = o["timings"]
                if o.get("usage"):
                    usage = o["usage"]
                ch = (o.get("choices") or [{}]); c0 = ch[0] if ch else {}
                delta = c0.get("delta", {}) if c0 else {}
                if delta.get("content") and ttft is None:
                    ttft = time.perf_counter() - t0
            total = time.perf_counter() - t0
            wall_end = time.time()
            # server log slice for this request
            slice_txt = ""
            try:
                with open(srv_log, "r", errors="replace") as lf:
                    lf.seek(log_off)
                    slice_txt = lf.read()[:4000]
            except Exception:
                pass
            tim = timings or {}; usg = usage or {}
            row = {"video_id": vid, "hist_frames": h, "rep": rep,
                   "build_serialize_s": round(build_serialize_s, 5), "body_bytes": body_bytes,
                   "prompt_tokens": usg.get("prompt_tokens"), "evaluated": tim.get("prompt_n"),
                   "cache_n": tim.get("cache_n"), "prompt_ms": tim.get("prompt_ms"),
                   "ttft_s": round(ttft, 4) if ttft else None, "total_s": round(total, 4),
                   "wall_start": wall_start, "wall_end": wall_end,
                   "clock_ok": (clk0 == PINNED_HZ), "server_log_slice": slice_txt}
            f.write(json.dumps(row) + "\n"); f.flush()
        print(f"  [B] hist={h}: {reps} appends, last ttft={row['ttft_s']}s "
              f"eval={row['evaluated']} cache_n={row['cache_n']} bytes={row['body_bytes']}", flush=True)
    f.close()
    # microbench: a 352x256 D2 frame
    mb = microbench_decode(frames[0])
    print(f"[B] microbench decode: {mb}", flush=True)
    return {"session": vid, "sizes": sizes, "reps": reps, "microbench": mb}


# ── main ─────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--parts", default="AB")
    ap.add_argument("--smoke", type=int, default=0, help="Part A: run only N requests (smoke)")
    ap.add_argument("--no-verify", action="store_true")
    args = ap.parse_args()
    OUTDIR.mkdir(parents=True, exist_ok=True)

    clk = dfl.gpu_freq()
    print(f"preflight clock={clk} pinned={PINNED_HZ} ok={clk == PINNED_HZ}", flush=True)

    summary = {"stack": {"llama_cpp": "c0fd786", "model": MODEL_TAG, "n_ctx": N_CTX,
                         "seed": SEED, "top_logprobs": TOP_LOGPROBS, "max_tokens": MAX_TOKENS,
                         "cache_prompt": False, "query": QUERY}, "parts_run": args.parts}

    reqs = None
    if "A" in args.parts:
        reqs = load_n1_requests()
        print(f"loaded {len(reqs)} N=1 requests", flush=True)
        if not args.no_verify:
            if not verify_frames(reqs):
                print("ABORT: frame sha256 mismatch", flush=True); sys.exit(1)

    log_path = OUTDIR / "server.log"
    proc = e8.launch_server_e8(log_path, n_ctx=N_CTX)
    summary["kv_mem"] = e8.parse_kv_mem(log_path)
    summary["kv_mem"]["server_rss_mib_postload"] = e8.server_rss_mib(proc)

    base_gz = OUTDIR / "tegrastats.jsonl.gz"
    sampler = dfl.Sampler(str(base_gz))
    time.sleep(2)

    try:
        if "A" in args.parts:
            if args.smoke:
                summary["smoke"] = part_a(reqs, sampler, OUTDIR / "partA_smoke.jsonl",
                                          resume=False, limit=args.smoke)
                summary["smoke_rows"] = [json.loads(l) for l in open(OUTDIR / "partA_smoke.jsonl")]
                summary["determinism_A"] = determinism_a(reqs, n=10)
            else:
                ok = part_a(reqs, sampler, OUTDIR / "partA_scores.jsonl")
                summary["partA_complete"] = ok
                if ok:
                    part_a_grey(reqs, OUTDIR / "partA_grey.jsonl")
                    summary["determinism_A"] = determinism_a(reqs, n=10)
        if "B" in args.parts and not args.smoke:
            reqs_e7, vids_e7 = e8.load_requests()
            summary["partB"] = part_b(reqs_e7, vids_e7, OUTDIR / "partB_overhead.jsonl")
    finally:
        snap = sampler.snapshot()
        summary["kv_mem"]["server_rss_mib_peak"] = e8.server_rss_mib(proc)
        summary["kv_mem"]["tegrastats_peak_ram_mib"] = max((r["ram_mb"] for r in snap if r.get("ram_mb")), default=None)
        sampler.stop()
        dfl.stop_server(proc)
        summary["_provenance"] = stamp(script="study_d15_orin_nexar.py", model=MODEL_TAG,
                                       device="jetson_orin", n=(len(reqs) if reqs else 0), args=args)
        json.dump(summary, open(OUTDIR / "study_d15_summary.json", "w"), indent=2)
        print("StudyD15 run complete.", flush=True)


if __name__ == "__main__":
    main()
