#!/usr/bin/env python3
"""
StudyORIN1-dense (Jetson AGX Orin). Three parts, reusing StudyD15/StudyD15b and
StudyE8 scripts, prompt, scoring, quantization and server settings verbatim.

Stack (as StudyD15/F4/E8): llama.cpp c0fd786, Qwen3-VL-4B-Instruct-F16
  (+ mmproj-F16), sha256 verified; MAXN mode 0; GPU pinned 1.3005 GHz; greedy;
  seed 0. Scoring is continuous log P(Yes): log of the first-token Yes/(Yes+No)
  top-20 probability mass, floored at 1e-12. Literal Yes/No strings are never
  used as the score. cache_prompt is FALSE for Part 1 scoring (cold prompt).

PART 1 (dense scores; HELD until the D14b dense frames land on the Orin):
  rescore every StudyD14b N=1 request (42,014, 0.25-s grid, 300 clips) on the
  Orin. Byte-identical request contract to StudyD15/D14/D3 (header + one SMALL
  768x432 PNG + the Nexar query). Resumable by clip. Verify every required frame
  against results/dashcam/study_d14b/frames_sha256_manifest.jsonl.gz first; STOP
  on any missing or mismatch.

PART 2 (controller overhead): plain-Python device controller signals over the
  device's own recent window (window median, IQR, a robust relative score,
  rise = score(t) - score(t-2s) per StudyE1, and an instability measure). CPU
  time per update at 4 Hz for window sizes 20/60/240; mean and p99.

PART 3 (device recall latency on a WARM D2 history): StudyE7 4B-on-D2-history
  setup, append-only. The 20 S-EMBER DEV questions (StudyB amendment-2 split)
  among the 74 E7 D2 questions on disk, each answered on a warm D2 history sized
  to about 11k and 28k tokens (20 x 2 = 40). Warm = the image history is already
  cached (cache_prompt true); only the question text is evaluated. TTFT + total.

Outputs: results/dashcam/study_orin1/ (Part 1 + meta); results/cost/study_orin1/
  (Parts 2 and 3).
"""
import argparse, json, math, os, statistics as st, sys, time, gzip, hashlib, urllib.request
from collections import deque, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "experiments/orchestration/baselines"))
import experiments.device.dev_fast_latency as dfl
import experiments.device.study_e8_device_warm as e8
import experiments.device.study_d15_orin_nexar as d15
from experiments.lib._provenance import stamp
import sember_split as ss

OUTD = ROOT / "results/dashcam/study_orin1"   # dense scores + meta
OUTC = ROOT / "results/cost/study_orin1"       # controller overhead + recall latency
D14B = ROOT / "results/dashcam/study_d14b"
D14B_REQMAN = D14B / "d14b_requests_manifest.jsonl.gz"
D14B_FRAMEMAN = D14B / "frames_sha256_manifest.jsonl.gz"
D14B_H100 = D14B / "d14b_trace_h100nvl.jsonl.gz"
D15_SCORES = ROOT / "results/device/study_d15/partA_scores.jsonl"

PINNED_HZ = d15.PINNED_HZ
STOP_TJ = 90.0


# ============================ PART 1: dense scores ============================
def load_d14b_n1():
    reqs = []
    with gzip.open(D14B_REQMAN, "rt") as f:
        for line in f:
            r = json.loads(line)
            if int(r["n"]) == 1:
                reqs.append(r)
    # clip + time order (t is a float grid point)
    reqs.sort(key=lambda r: (r["file_name"], float(r["t"])))
    return reqs


def verify_part1_frames(reqs):
    """Verify EVERY required N=1 frame against the D14b frame sha256 manifest.
    Returns (ok, n_checked, missing[], mismatch[])."""
    man = {}
    with gzip.open(D14B_FRAMEMAN, "rt") as f:
        for line in f:
            r = json.loads(line)
            man[(r["file_name"], r["key"])] = r["small_sha256"]
    missing, mismatch, n = [], [], 0
    cache = {}
    for r in reqs:
        clip = r["file_name"].replace(".mp4", "")
        key = r["frame_keys"][0]
        want = man.get((r["file_name"], key)) or r["small_sha256"][0]
        p = d15.D14DIR / clip / f"{key}.png"
        if not p.exists():
            missing.append(f"{clip}/{key}")
            continue
        h = cache.get(p)
        if h is None:
            h = hashlib.sha256(p.read_bytes()).hexdigest()
            cache[p] = h
        n += 1
        if h != want:
            mismatch.append(f"{clip}/{key}")
    ok = (not missing and not mismatch)
    print(f"[1] frame verify: checked={n}/{len(reqs)} missing={len(missing)} mismatch={len(mismatch)}",
          flush=True)
    if not ok:
        print("  MISSING:", missing[:8], "\n  MISMATCH:", mismatch[:8], flush=True)
    return ok, n, missing, mismatch


def part1(reqs, sampler, out_jsonl, resume=True):
    done = set()
    if resume and out_jsonl.exists():
        for line in open(out_jsonl):
            try:
                done.add(json.loads(line)["request_id"])
            except Exception:
                pass
    mode = "a" if (resume and out_jsonl.exists()) else "w"
    f = open(out_jsonl, mode)
    t0 = time.time(); n = 0
    last_clip = None
    for r in reqs:
        if r["request_id"] in done:
            continue
        clip = r["file_name"].replace(".mp4", "")
        if clip != last_clip:
            tj = e8.recent_tj(sampler)
            if tj and tj >= STOP_TJ:
                print(f"[1] THROTTLE STOP tj={tj} at clip {clip}", flush=True)
                break
            last_clip = clip
        content, _ = d15.build_nexar_content(r, verify=False)   # frames pre-verified in the gate
        rec = d15.score_request(content, cache_prompt=False)
        row = {"request_id": r["request_id"], "d14_request_id": r.get("d14_request_id"),
               "file_name": r["file_name"], "clip": clip, "t": float(r["t"]), "label": r.get("label"),
               "time_of_event": r.get("time_of_event"), "duration_s": r.get("duration_s"),
               "p_yes": rec["p_yes"], "score": rec["score"], "first_token": rec["first_token"],
               "yes_seen": rec["yes_seen"], "no_seen": rec["no_seen"], "neither": rec["neither"],
               "prompt_tokens": rec["prompt_tokens"], "cache_n": rec["cache_n"],
               "ttft_s": rec["ttft_s"], "total_s": rec["total_s"], "clock_ok": rec["clock_ok"]}
        f.write(json.dumps(row) + "\n"); f.flush()
        n += 1
        if n % 500 == 0:
            rate = n / max(1e-9, time.time() - t0)
            eta = (len(reqs) - len(done) - n) / max(1e-9, rate) / 60
            print(f"[1] {n} new (clip {clip} t={r['t']}) {rate:.2f} req/s ETA {eta:.0f} min "
                  f"score={rec['score']}", flush=True)
    f.close()
    print(f"[1] done: {n} new rows this run", flush=True)
    return n


# ======================= PART 2: controller overhead =========================
RISE_LAG_S = 2.0        # StudyE1: rise = score(t) - score(t-2s)
HZ = 4.0                 # controller update rate


def controller_update(win, hist):
    """One controller update over the trailing window `win` (a list of recent
    scores, newest last) and the rise-lag buffer `hist` (newest last, length
    >= RISE_LAG_S*HZ+1). Returns the signal dict. Plain Python + statistics.

    Signals (device controller spec; relative to the device's OWN recent window):
      median      : window median of log P(Yes)
      iqr         : window p75 - p25
      rel_score   : (current - median) / (iqr + eps)   robust relative score
      rise        : current - score 2 s ago (StudyE1 definition)
      instability : median absolute successive difference across the window
    """
    cur = win[-1]
    med = st.median(win)
    qs = st.quantiles(win, n=4, method="exclusive") if len(win) >= 2 else [cur, cur, cur]
    iqr = qs[2] - qs[0]
    rel = (cur - med) / (iqr + 1e-9)
    lag = int(round(RISE_LAG_S * HZ))
    prev = hist[-(lag + 1)] if len(hist) > lag else hist[0]
    rise = cur - prev
    if len(win) >= 2:
        diffs = [abs(win[i] - win[i - 1]) for i in range(1, len(win))]
        instab = st.median(diffs)
    else:
        instab = 0.0
    return {"median": med, "iqr": iqr, "rel_score": rel, "rise": rise, "instability": instab}


def part2(windows=(20, 60, 240), updates=5000):
    # real device score stream: committed StudyD15 Orin Nexar scores
    stream = []
    for line in open(D15_SCORES):
        d = json.loads(line)
        if d.get("score") is not None:
            stream.append(float(d["score"]))
    if len(stream) < updates + max(windows) + 16:
        reps = (updates + max(windows) + 16) // len(stream) + 1
        stream = stream * reps
    out = {"n_stream": len(stream), "rise_lag_s": RISE_LAG_S, "hz": HZ, "updates": updates,
           "stream_source": "results/device/study_d15/partA_scores.jsonl (real Orin scores)",
           "windows": {}}
    lag = int(round(RISE_LAG_S * HZ))
    for w in windows:
        win = deque(maxlen=w)
        hist = deque(maxlen=lag + 1)
        # warm the buffers
        for i in range(max(w, lag + 1)):
            win.append(stream[i]); hist.append(stream[i])
        times = []
        for i in range(max(w, lag + 1), max(w, lag + 1) + updates):
            s = stream[i % len(stream)]
            win.append(s); hist.append(s)
            wl = list(win); hl = list(hist)
            t0 = time.perf_counter()
            controller_update(wl, hl)
            times.append((time.perf_counter() - t0) * 1e6)   # microseconds
        times.sort()
        out["windows"][str(w)] = {
            "n_updates": len(times),
            "mean_us": round(sum(times) / len(times), 3),
            "p50_us": round(times[len(times) // 2], 3),
            "p99_us": round(times[min(len(times) - 1, int(0.99 * len(times)))], 3),
            "max_us": round(times[-1], 3),
            "implied_budget_per_update_us_at_4hz": round(1e6 / HZ, 1)}
        print(f"[2] window={w}: mean={out['windows'][str(w)]['mean_us']}us "
              f"p99={out['windows'][str(w)]['p99_us']}us", flush=True)
    OUTC.mkdir(parents=True, exist_ok=True)
    out["_provenance"] = stamp(script="study_orin1_dense.py", model="4bi_f16",
                               device="jetson_orin", n=updates, args=None)
    json.dump(out, open(OUTC / "orin1_controller_overhead.json", "w"), indent=1)
    return out


# ===================== PART 3: device recall latency =========================
def _stream_chat(content, cache_prompt, max_tokens, timeout=600):
    payload = {"model": "m", "messages": [{"role": "user", "content": content}],
               "stream": True, "stream_options": {"include_usage": True},
               "temperature": 0.0, "max_tokens": max_tokens, "seed": 0,
               "cache_prompt": cache_prompt}
    data = json.dumps(payload).encode()
    req = urllib.request.Request(f"{dfl.BASE}/v1/chat/completions", data=data,
                                 headers={"Content-Type": "application/json"})
    clk0 = dfl.gpu_freq()
    ttft = None; timings = None; usage = None; text = ""
    t0 = time.perf_counter()
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
        ch = (o.get("choices") or [{}]); c0 = ch[0] if ch else {}
        delta = c0.get("delta", {}) if c0 else {}
        if delta.get("content"):
            if ttft is None:
                ttft = time.perf_counter() - t0
            text += delta["content"]
    total = time.perf_counter() - t0
    clk1 = dfl.gpu_freq()
    tim = timings or {}; usg = usage or {}
    return {"ttft_s": round(ttft, 4) if ttft else None, "total_s": round(total, 4),
            "prompt_tokens": usg.get("prompt_tokens"), "evaluated": tim.get("prompt_n"),
            "cache_n": tim.get("cache_n"), "n_gen": tim.get("predicted_n"),
            "prompt_ms": tim.get("prompt_ms"), "answer_text": text[:60],
            "clock_ok": (clk0 == PINNED_HZ and clk1 == PINNED_HZ)}


def _dev_questions():
    reqs, vids = e8.load_requests()
    sp = ss.split()
    dev = {q: reqs[q] for q in reqs if q in sp["dev_questions"]}
    return reqs, vids, dev


def part3(sampler, out_jsonl, targets=(11000, 28000), max_tokens=64):
    reqs, vids, dev = _dev_questions()
    dev_ids = sorted(dev)
    print(f"[3] DEV questions on disk: {len(dev_ids)} of {len(reqs)}", flush=True)
    # representative warm D2 history: the longest E7 session
    longest = max(vids["videos"], key=lambda v: v["n_frames"])
    vid = longest["video_id"]
    frames = e8.frames_for_video(vid)
    header = e8.reqs_header(reqs, vid)
    maxf = len(frames)
    print(f"[3] history substrate {vid}: {maxf} frames", flush=True)

    f = open(out_jsonl, "w")
    meta = {"history_video": vid, "history_max_frames": maxf, "targets_tok": list(targets),
            "n_dev_questions": len(dev_ids), "dev_question_ids": dev_ids, "sizes": {}}
    for target in targets:
        # choose a frame count whose warm history is about `target` tokens, then verify on-server
        est_frames = min(maxf, int(round(target / e8.FRAME_TOK_EST)))
        # prime the history warm (images only, no question) and read achieved history tokens
        e8.erase_slot()
        prime = e8.build_append_content(header, frames[:est_frames])
        pr = _stream_chat(prime, cache_prompt=True, max_tokens=1)
        hist_tok = pr["prompt_tokens"]
        held = (hist_tok is not None)
        print(f"[3] target~{target}: {est_frames} frames -> history prompt_tokens={hist_tok} "
              f"(held={held})", flush=True)
        if hist_tok is None or (target >= 28000 and est_frames >= maxf and hist_tok < target * 0.9):
            # device could not reach 28k with the available frames: report max and stop this size
            meta["sizes"][str(target)] = {"frames": est_frames, "history_tokens": hist_tok,
                                          "held": False,
                                          "note": "device/session could not reach target; max reported"}
            # still record the max-size measurements we can at this frame count
        else:
            meta["sizes"][str(target)] = {"frames": est_frames, "history_tokens": hist_tok, "held": True}
        tj = e8.recent_tj(sampler)
        if tj and tj >= STOP_TJ:
            print(f"[3] THROTTLE STOP tj={tj}", flush=True); break
        for qi, qid in enumerate(dev_ids):
            req = dev[qid]
            # warm recall answer: history (cached) + the DEV question text
            content = e8.build_append_content(header, frames[:est_frames])
            content.append({"type": "text", "text": req["text"]})
            rec = _stream_chat(content, cache_prompt=True, max_tokens=max_tokens)
            row = {"target_tok": target, "history_video": vid, "history_frames": est_frames,
                   "question_id": qid, "question_category": None,
                   "ttft_s": rec["ttft_s"], "total_s": rec["total_s"],
                   "prompt_tokens": rec["prompt_tokens"], "history_tokens_cached": rec["cache_n"],
                   "evaluated": rec["evaluated"], "n_gen": rec["n_gen"],
                   "prompt_ms": rec["prompt_ms"], "clock_ok": rec["clock_ok"]}
            f.write(json.dumps(row) + "\n"); f.flush()
        last = row
        print(f"[3] target~{target}: {len(dev_ids)} DEV questions, last ttft={last['ttft_s']}s "
              f"total={last['total_s']}s cache_n={last['history_tokens_cached']} "
              f"eval={last['evaluated']}", flush=True)
    f.close()
    OUTC.mkdir(parents=True, exist_ok=True)
    meta["_provenance"] = stamp(script="study_orin1_dense.py", model="4bi_f16",
                                device="jetson_orin", n=len(dev_ids), args=None)
    json.dump(meta, open(OUTC / "orin1_recall_latency_meta.json", "w"), indent=1)
    return meta


# ================================ main =======================================
def model_sha_meta():
    weights, mmproj, fmt, gen = dfl.GGUF[d15.MODEL_TAG]
    def sha(p):
        try:
            return hashlib.sha256(Path(p).read_bytes()).hexdigest()
        except Exception:
            return None
    return {"llama_cpp": "c0fd786", "model_tag": d15.MODEL_TAG,
            "weights": str(weights), "mmproj": str(mmproj),
            "weights_sha256": sha(weights), "mmproj_sha256": sha(mmproj),
            "pinned_hz": PINNED_HZ, "n_ctx": e8.N_CTX,
            "server_flags": "-ngl 99 -fa on -c 57344 --jinja --reasoning-format deepseek -np 1"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--parts", default="23", help="subset of 1/2/3, e.g. 23")
    ap.add_argument("--gate-only", action="store_true", help="Part 1: run the frame-verify gate and stop")
    ap.add_argument("--clips-file", default=None,
                    help="Part 1: restrict to the clip ids listed (one per line); used for batched "
                         "dense-frame scoring where a half of the clips lands at a time")
    args = ap.parse_args()
    OUTD.mkdir(parents=True, exist_ok=True)
    OUTC.mkdir(parents=True, exist_ok=True)

    meta = {"stack": model_sha_meta(), "parts": args.parts, "started": time.time()}
    json.dump(meta, open(OUTD / "orin1_meta.json", "w"), indent=1)

    needs_server = ("1" in args.parts) or ("3" in args.parts)
    needs_sampler = needs_server

    # Part 2 needs no server
    if "2" in args.parts:
        print("=== PART 2: controller overhead ===", flush=True)
        part2()

    if "1" in args.parts:
        print("=== PART 1: dense scores (gate first) ===", flush=True)
        reqs = load_d14b_n1()
        batch_clips = None
        if args.clips_file:
            batch_clips = sorted(l.strip() for l in open(args.clips_file) if l.strip())
            cset = set(batch_clips)
            reqs = [r for r in reqs if r["file_name"].replace(".mp4", "") in cset]
            print(f"[1] batch restricted to {len(cset)} clips "
                  f"({batch_clips[0]} to {batch_clips[-1]}): {len(reqs)} N=1 requests", flush=True)
        ok, nchk, missing, mismatch = verify_part1_frames(reqs)
        json.dump({"checked": nchk, "n_required": len(reqs), "missing": missing[:200],
                   "mismatch": mismatch[:200], "n_missing": len(missing), "n_mismatch": len(mismatch),
                   "ok": ok, "batch_n_clips": (len(batch_clips) if batch_clips else None),
                   "batch_clip_range": ([batch_clips[0], batch_clips[-1]] if batch_clips else None)},
                  open(OUTD / "orin1_part1_frame_gate.json", "w"), indent=1)
        if not ok:
            print(f"[1] GATE FAILED: missing={len(missing)} mismatch={len(mismatch)}. STOP.", flush=True)
            return
        if args.gate_only:
            print("[1] gate passed; --gate-only set, stopping before scoring.", flush=True)
            return

    proc = sampler = None
    if needs_server:
        gz = OUTD / "tegrastats.jsonl.gz"
        sampler = dfl.Sampler(str(gz))   # tegrastats thread auto-starts in __init__
        proc = e8.launch_server_e8(str(OUTD / "server.log"), n_ctx=e8.N_CTX)
        time.sleep(2)

    try:
        if "1" in args.parts:
            part1(reqs, sampler, OUTD / "orin1_dense_scores.jsonl", resume=True)
        if "3" in args.parts:
            print("=== PART 3: device recall latency (warm D2 history) ===", flush=True)
            part3(sampler, OUTC / "orin1_recall_latency.jsonl")
    finally:
        if proc is not None:
            dfl.stop_server(proc)
        if sampler is not None:
            sampler.stop()
    print("StudyORIN1 run complete.", flush=True)


if __name__ == "__main__":
    main()
