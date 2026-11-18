#!/usr/bin/env python3
"""StudyORIN3-vllm Part 2 - warm recall latency under vLLM (StudyORIN2 design).

Same StudyE7 D2 longest session warmed to ~11k and ~28k tokens, the same 20 DEV questions,
TTFT/total one at a time, clock pinned, exclusive GPU. Two request paths, both through vLLM's
OpenAI-compatible server:

  (a) EFFICIENT: prefix caching ON. The header + history frames are an identical prefix across
      all 20 questions; a priming request populates the KV + multimodal-processor cache, then
      each question is served with the history prefix as a cache hit (cached_tokens reported) so
      only the question suffix is computed. History images carry stable per-image uuids
      (vLLM 0.20.0 chat_utils ChatCompletionContentPart*.uuid + --mm-processor-cache) so the
      multimodal items are cache-keyed. This is the device's real warm-recall cost.
  (b) RE-SEND: prefix caching OFF server. Each question re-sends AND re-processes the full
      history (a stateless client / the StudyORIN1 Part 3 path), so cached_tokens ~ 0.

EQUIVALENCE GATE (before timing): on N_GATE DEV questions at 11k, path (a) and (b) must produce
the same answer token and first-token top-20 logprob SET within LOGPROB_TOL. Both are the same
vLLM engine (prefix caching is numerically exact), so this is expected to pass at ~0; the gate is
pre-registered at 0.05 nats. The two server configs never run concurrently (exclusive GPU): path
(a) runs against the caching-ON server, then the caching-OFF server is started for path (b).

Run order (driver prints what to do; server lifecycle handled by the caller / orin3_serve.sh):
  --path efficient   (against caching-ON server)   -> writes efficient rows + gate-a logprobs
  --path resend      (against caching-OFF server)  -> writes resend rows + gate-b logprobs
  --analyse                                         -> equivalence gate + timing + side-by-side

Outputs under results/cost/study_orin3/.
"""
import argparse, base64, json, math, os, statistics as st, subprocess, sys, time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "experiments/orchestration/baselines"))
import experiments.device.study_e8_device_warm as e8  # substrate only (no llama.cpp calls)
import sember_split as ssp

OUTC = ROOT / "results/cost/study_orin3"
BASE = "http://127.0.0.1:8000"
MODEL = "qwen3vl4b"
TARGETS = (11000, 28000)
N_GATE = 3
LOGPROB_TOL = 0.05          # nats; pre-registered (same engine -> expected ~0)
MAX_TOKENS = 64
TOP_LOGPROBS = 20
GPU_FREQ_PATHS = ("/sys/devices/gpu.0/devfreq/17000000.gpu/cur_freq",
                  "/sys/class/devfreq/17000000.gpu/cur_freq")


def gpu_hz():
    for p in GPU_FREQ_PATHS:
        try:
            return int(Path(p).read_text().strip())
        except Exception:
            continue
    return None


def read_cache_counters(client):
    """vLLM 0.20.0 does not populate usage.prompt_tokens_details.cached_tokens in the OpenAI API
    (null in both streaming and non-streaming), so the per-request prefix-cache hit is read from
    the /metrics counters instead: the delta of vllm:prefix_cache_hits / _queries across the
    request is the number of prompt tokens served from cache / queried."""
    try:
        txt = client.get(f"{BASE}/metrics", timeout=30).text
    except Exception:
        return None, None
    hits = queries = 0.0
    for l in txt.splitlines():
        if l.startswith("#"):
            continue
        if l.startswith("vllm:prefix_cache_hits"):
            hits += float(l.split()[-1])
        elif l.startswith("vllm:prefix_cache_queries"):
            queries += float(l.split()[-1])
    return hits, queries


def b64_png(abs_path):
    return base64.b64encode(Path(abs_path).read_bytes()).decode()


# ---------------------------------------------------------------- substrate
def substrate():
    reqs, vids = e8.load_requests()
    sp = ssp.split()
    dev_ids = sorted(q for q in reqs if q in sp["dev_questions"])
    longest = max(vids["videos"], key=lambda v: v["n_frames"])
    vid = longest["video_id"]
    rels = e8.frames_for_video(vid)
    abs_frames = [str(e8.FRAMES / r) for r in rels]
    header = e8.reqs_header(reqs, vid)
    questions = [reqs[q]["text"] for q in dev_ids]  # layout: header + images + question text
    return header, abs_frames, dev_ids, questions, vid


def content_for(header, frame_b64s, question, with_uuids=False, vid=""):
    content = [{"type": "text", "text": header}]
    for i, b in enumerate(frame_b64s):
        part = {"type": "image_url", "image_url": {"url": "data:image/png;base64," + b}}
        if with_uuids:
            part["uuid"] = f"{vid}_f{i}"
        content.append(part)
    content.append({"type": "text", "text": question})
    return content


def call(client, content, max_tokens=MAX_TOKENS):
    body = dict(model=MODEL, messages=[{"role": "user", "content": content}], stream=True,
                stream_options={"include_usage": True}, temperature=0.0, max_tokens=max_tokens,
                seed=0, logprobs=True, top_logprobs=TOP_LOGPROBS)
    clk0 = gpu_hz()
    h0, q0 = read_cache_counters(client)
    t0 = time.perf_counter()
    ttft = None; first_top = None; first_token = None; text = ""; usage = {}
    with client.stream("POST", f"{BASE}/v1/chat/completions", json=body) as r:
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}: {r.read()[:300]}")
        for line in r.iter_lines():
            if not line or not line.startswith("data: "):
                continue
            d = line[6:]
            if d == "[DONE]":
                break
            j = json.loads(d)
            if j.get("usage"):
                usage = j["usage"]
            ch = j.get("choices") or []
            if not ch:
                continue
            delta = ch[0].get("delta") or {}
            piece = delta.get("content") or ""
            lp = (ch[0].get("logprobs") or {}).get("content") or []
            if piece and ttft is None:
                ttft = time.perf_counter() - t0
            if lp and first_top is None:
                first_top = lp[0].get("top_logprobs"); first_token = lp[0].get("token")
            text += piece
    total = time.perf_counter() - t0
    h1, q1 = read_cache_counters(client)
    det = usage.get("prompt_tokens_details") or {}
    cache_hit_delta = round(h1 - h0) if (h0 is not None and h1 is not None) else None
    cache_query_delta = round(q1 - q0) if (q0 is not None and q1 is not None) else None
    return {"ttft_s": round(ttft, 4) if ttft else None, "total_s": round(total, 4),
            "first_token": first_token, "text": text.strip(),
            "top": [(t["token"], round(t["logprob"], 4)) for t in (first_top or [])],
            "prompt_tokens": usage.get("prompt_tokens"),
            "cached_tokens": det.get("cached_tokens"),
            "prefix_cache_hit_tokens": cache_hit_delta,
            "prefix_cache_query_tokens": cache_query_delta,
            "completion_tokens": usage.get("completion_tokens"),
            "clock_hz": clk0, "clock_ok": clk0 == 1300500000}


def calibrate_frames(client, header, abs_frames, vid):
    """Find frame counts whose prompt_tokens land nearest each target. Measure tokens/frame from a
    small probe, extrapolate, then verify the chosen counts with a real request."""
    probe_n = 20
    b = [b64_png(p) for p in abs_frames[:probe_n]]
    r = call(client, content_for(header, b, "Describe the scene.", vid=vid), max_tokens=1)
    base_overhead = 1  # question+template folded into measurement below via two points
    # second point for a clean per-frame slope
    b2 = [b64_png(p) for p in abs_frames[:probe_n * 2]]
    r2 = call(client, content_for(header, b2, "Describe the scene.", vid=vid), max_tokens=1)
    per_frame = (r2["prompt_tokens"] - r["prompt_tokens"]) / probe_n
    fixed = r["prompt_tokens"] - per_frame * probe_n
    counts = {}
    for tgt in TARGETS:
        n = max(1, min(len(abs_frames), round((tgt - fixed) / per_frame)))
        counts[tgt] = n
    return {"per_frame_tokens": round(per_frame, 2), "fixed_tokens": round(fixed, 2),
            "max_frames": len(abs_frames), "counts": counts,
            "probe_prompt_tokens": {probe_n: r["prompt_tokens"], probe_n * 2: r2["prompt_tokens"]}}


# ---------------------------------------------------------------- run one path
def run_path(path):
    assert path in ("efficient", "resend")
    OUTC.mkdir(parents=True, exist_ok=True)
    header, abs_frames, dev_ids, questions, vid = substrate()
    dev_ids = dev_ids[:20]; questions = questions[:20]
    with httpx.Client(timeout=httpx.Timeout(300.0)) as client:
        cal = calibrate_frames(client, header, abs_frames, vid)
        print(f"[{path}] calibration: {json.dumps(cal)}", flush=True)
        json.dump({"path": path, "vid": vid, "n_dev": len(dev_ids), "calibration": cal,
                   "exclusivity": exclusivity()},
                  open(OUTC / f"orin3_warm_{path}_meta.json", "w"), indent=1)
        out = open(OUTC / f"orin3_warm_{path}.jsonl", "w")
        with_uuids = (path == "efficient")
        for tgt in TARGETS:
            n = cal["counts"][tgt]
            fb = [b64_png(p) for p in abs_frames[:n]]
            # prime the cache once (efficient) with a throwaway question; for resend this is just
            # the first (cold) call and is recorded with prime=True but excluded from stats.
            prime = call(client, content_for(header, fb, questions[0], with_uuids, vid))
            out.write(json.dumps({"type": "prime", "target": tgt, "n_frames": n,
                                  "prompt_tokens": prime["prompt_tokens"],
                                  "cached_tokens": prime["cached_tokens"],
                                  "ttft_s": prime["ttft_s"], "total_s": prime["total_s"]}) + "\n")
            out.flush()
            for qid, q in zip(dev_ids, questions):
                r = call(client, content_for(header, fb, q, with_uuids, vid))
                r.update({"type": "q", "path": path, "target": tgt, "n_frames": n,
                          "question_id": qid})
                out.write(json.dumps(r) + "\n"); out.flush()
            print(f"[{path}] target {tgt}: {n} frames, prime prompt_tokens={prime['prompt_tokens']} "
                  f"cached={prime['cached_tokens']}; 20 questions done", flush=True)
        out.close()
    print(f"[{path}] done -> {OUTC / ('orin3_warm_'+path+'.jsonl')}", flush=True)


def exclusivity():
    try:
        out = subprocess.run(["bash", "-lc",
                              "pgrep -af 'llama|python|vllm' | grep -v pgrep || true"],
                             capture_output=True, text=True).stdout
    except Exception:
        out = ""
    gpu = [l for l in out.splitlines() if "vllm" in l or "llama" in l]
    return {"gpu_processes": gpu, "n": len(gpu)}


# ---------------------------------------------------------------- analyse
def pctl(vals, q):
    vals = sorted(v for v in vals if v is not None)
    if not vals:
        return None
    k = (len(vals) - 1) * q
    lo, hi = int(math.floor(k)), int(math.ceil(k))
    return vals[lo] if lo == hi else vals[lo] + (vals[hi] - vals[lo]) * (k - lo)


def stats(vals):
    vals = [v for v in vals if v is not None]
    if not vals:
        return {}
    return {"n": len(vals), "p50": round(pctl(vals, 0.5), 4), "p90": round(pctl(vals, 0.9), 4),
            "min": round(min(vals), 4), "max": round(max(vals), 4),
            "mean": round(sum(vals) / len(vals), 4)}


def analyse():
    eff = [json.loads(l) for l in open(OUTC / "orin3_warm_efficient.jsonl")]
    res = [json.loads(l) for l in open(OUTC / "orin3_warm_resend.jsonl")]
    effq = [r for r in eff if r.get("type") == "q"]
    resq = [r for r in res if r.get("type") == "q"]
    out = {"paths": ["efficient (prefix caching ON)", "resend (prefix caching OFF)"],
           "logprob_tol_nats": LOGPROB_TOL, "by_target": {}}
    # equivalence gate on first N_GATE questions at 11k
    e11 = {r["question_id"]: r for r in effq if r["target"] == 11000}
    r11 = {r["question_id"]: r for r in resq if r["target"] == 11000}
    gate = []
    for qid in list(e11)[:N_GATE]:
        a, b = e11[qid], r11.get(qid)
        if not b:
            continue
        ta = {t: lp for t, lp in a["top"]}; tb = {t: lp for t, lp in b["top"]}
        same_ans = a["first_token"] == b["first_token"]
        same_set = set(ta) == set(tb)
        maxd = max((abs(ta[t] - tb[t]) for t in ta if t in tb), default=None)
        gate.append({"question_id": qid, "ans_eff": a["first_token"], "ans_resend": b["first_token"],
                     "same_answer": same_ans, "same_top20_set": same_set,
                     "max_logprob_diff": round(maxd, 4) if maxd is not None else None})
    out["equivalence_gate"] = {
        "n": len(gate), "rows": gate,
        "passed": all(g["same_answer"] and g["same_top20_set"]
                      and (g["max_logprob_diff"] is None or g["max_logprob_diff"] <= LOGPROB_TOL)
                      for g in gate)}
    # timing + cache verification per target/path
    for tgt in TARGETS:
        e = [r for r in effq if r["target"] == tgt]
        rr = [r for r in resq if r["target"] == tgt]
        eff_cached = [r.get("prefix_cache_hit_tokens") for r in e]
        res_cached = [r.get("prefix_cache_hit_tokens") for r in rr]
        ans_mismatch = sum(1 for a in e for b in [next((x for x in rr if x["question_id"] == a["question_id"]), None)]
                           if b and a["first_token"] != b["first_token"])
        out["by_target"][str(tgt)] = {
            "n_frames": e[0]["n_frames"] if e else None,
            "prompt_tokens": e[0]["prompt_tokens"] if e else None,
            "efficient": {"ttft_s": stats([r["ttft_s"] for r in e]),
                          "total_s": stats([r["total_s"] for r in e]),
                          "prefix_cache_hit_tokens_min": min([c for c in eff_cached if c is not None], default=None),
                          "prefix_cache_hit_tokens_median": (st.median([c for c in eff_cached if c is not None])
                                                             if any(c is not None for c in eff_cached) else None)},
            "resend": {"ttft_s": stats([r["ttft_s"] for r in rr]),
                       "total_s": stats([r["total_s"] for r in rr]),
                       "prefix_cache_hit_tokens_median": (st.median([c for c in res_cached if c is not None])
                                                         if any(c is not None for c in res_cached) else None)},
            "ttft_p50_ratio_resend_over_efficient": None,
            "answer_mismatch_eff_vs_resend": ans_mismatch,
            "clock_pinned_all": all(r.get("clock_ok") for r in e + rr)}
        ep = out["by_target"][str(tgt)]["efficient"]["ttft_s"].get("p50")
        rp = out["by_target"][str(tgt)]["resend"]["ttft_s"].get("p50")
        if ep and rp:
            out["by_target"][str(tgt)]["ttft_p50_ratio_resend_over_efficient"] = round(rp / ep, 2)
    # side-by-side with StudyORIN2 (llama.cpp harness + server)
    out["studyorin2_llamacpp"] = {
        "harness_ttft_p50_s": {"11000": 0.146, "28000": 0.225},
        "server_ttft_p50_s": {"11000": 1.416, "28000": 3.433},
        "note": "ORIN2 in-process harness vs llama.cpp server (image re-send); design D61"}
    json.dump(out, open(OUTC / "orin3_warm_analysis.json", "w"), indent=1)
    print(json.dumps(out, indent=1))
    print("wrote", OUTC / "orin3_warm_analysis.json")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", choices=["efficient", "resend"])
    ap.add_argument("--analyse", action="store_true")
    a = ap.parse_args()
    if a.path:
        run_path(a.path)
    if a.analyse:
        analyse()


if __name__ == "__main__":
    main()
