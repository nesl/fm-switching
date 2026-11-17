#!/usr/bin/env python3
"""
StudyORIN2-stack Part 2 — warm recall latency WITHOUT image re-send (design D61).

StudyORIN1-dense Part 3 measured the Orin's warm recall on the llama.cpp OpenAI
server: TTFT 1.41 s (11k) / 3.43 s (28k), of which server prompt_ms was only
0.13-0.19 s. The rest is the API re-sending and re-parsing every history image on
every call -- an API artifact, not the device's real cost. Using it as the device
baseline would flatter the cloud.

This driver measures the SAME StudyORIN1 Part 3 design (same longest E7 D2 session
warmed to ~11k and ~28k tokens, the same 20 DEV questions, TTFT/total, clock
pinned, one at a time) on TWO paths and compares them same-day:
  (A) the in-process harness (experiments/device/orin2_harness/warm_recall): the
      history is evaluated ONCE and kept in the KV; each question evaluates only
      the question tokens over the cached context. No image bytes re-sent.
  (B) the server warm path (cache_prompt=true), which re-sends all history images
      each call -- the StudyORIN1 Part 3 path, re-run here for a side-by-side.

EQUIVALENCE GATE (before any timing is reported): on 3 DEV questions at 11k, the
harness must produce the same answer token and first-token top-20 logprobs as the
server (tolerance LOGPROB_TOL). If not, STOP and report. The two engines never run
concurrently (exclusive GPU): the harness runs alone, then the server runs alone.

STACK: identical to StudyORIN1-dense. llama.cpp c0fd786, Qwen3-VL-4B-Instruct-F16
GGUF + mmproj-F16, -c 57344, flash attention on, greedy seed 0, GPU pinned, MAXN.

Outputs under results/cost/study_orin2/.
"""
import argparse, json, math, os, statistics as st, subprocess, sys, time, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "experiments/orchestration/baselines"))
import experiments.device.dev_fast_latency as dfl
import experiments.device.study_e8_device_warm as e8
import sember_split as ss
from experiments.lib._provenance import stamp

ROOT = Path(__file__).resolve().parent.parent.parent
OUTC = ROOT / "results/cost/study_orin2"
HARNESS = ROOT / "experiments/device/orin2_harness/warm_recall"
SCRATCH = Path("/tmp/claude-1000/-home-nesl-fm-switching/9d6d4966-962f-4dd3-bb26-a868cceb7ec7/scratchpad")
GPU_FREQ_PATH = dfl.GPU_FREQ_PATH
PINNED_HZ = 1300500000
TARGETS = (11000, 28000)
GATE_SIZE = 11000
N_GATE = 3
# Equivalence tolerance on first-token top-20 logprobs. POST-HOC, NOT pre-registered:
# the gate was set to LOGPROB_TOL_PRE = 0.05 nats BEFORE any data. It failed at
# 0.064-0.100 nats on the 3 gate questions. After seeing that result it was replaced
# (user-approved) by 0.15 nats. Reason: the server is bit-deterministic (measured
# self-jitter 0.0 over two fresh re-encodes), prompts are token-identical
# (history_tokens + suffix_tokens == server prompt_tokens, verified per question),
# and the answer token and full top-20 token set are identical; the residual gap is
# the harness batching the IMAGE ENCODE differently from the server. Image encoding
# is part of building the warm history, which is EXCLUDED from the timed path, so it
# does not affect the latency this experiment measures. Reported as a post-hoc
# tolerance change, not a pre-registered pass.
LOGPROB_TOL_PRE = 0.05    # nats; set before data
LOGPROB_TOL = 0.15        # nats; post-hoc, user-approved (see above)
MAX_TOKENS = 64
TOP_LOGPROBS = 20


# ── substrate (same as StudyORIN1 Part 3) ────────────────────────────────────
def substrate():
    reqs, vids = e8.load_requests()
    sp = ss.split()
    dev = {q: reqs[q] for q in reqs if q in sp["dev_questions"]}
    longest = max(vids["videos"], key=lambda v: v["n_frames"])
    vid = longest["video_id"]
    rels = e8.frames_for_video(vid)
    header = e8.reqs_header(reqs, vid)
    dev_ids = sorted(dev)
    return reqs, dev, dev_ids, vid, rels, header


def est_frames_for(target, maxf):
    return min(maxf, int(round(target / e8.FRAME_TOK_EST)))


# ── harness path ─────────────────────────────────────────────────────────────
def run_harness(header, abs_frames, questions, tag):
    cfg = {"model": str(dfl.GGUF["4bi_f16"][0]), "mmproj": str(dfl.GGUF["4bi_f16"][1]),
           "n_ctx": e8.N_CTX, "n_gpu_layers": 99, "seed": 0, "n_predict": MAX_TOKENS,
           "header": header, "frames": abs_frames,
           "questions": questions, "gpu_freq_path": GPU_FREQ_PATH,
           "out": str(SCRATCH / f"orin2_harness_{tag}.jsonl")}
    cfgp = SCRATCH / f"orin2_harness_cfg_{tag}.json"
    json.dump(cfg, open(cfgp, "w"))
    log = open(SCRATCH / f"orin2_harness_{tag}.log", "w")
    t0 = time.time()
    rc = subprocess.call([str(HARNESS), str(cfgp)], stdout=log, stderr=subprocess.STDOUT)
    log.close()
    if rc != 0:
        raise RuntimeError(f"harness rc={rc}; see {SCRATCH}/orin2_harness_{tag}.log")
    rows = [json.loads(l) for l in open(cfg["out"])]
    meta = next((r for r in rows if r.get("type") == "meta"), None)
    data = {r["question_id"]: r for r in rows if r.get("type") != "meta"}
    print(f"[harness {tag}] {len(data)} questions in {time.time()-t0:.0f}s "
          f"history_n_past={meta['history_n_past'] if meta else '?'}", flush=True)
    return meta, data


# ── server path (warm, re-sends images) ──────────────────────────────────────
def server_chat(content, cache_prompt=True, max_tokens=MAX_TOKENS, timeout=180):
    payload = {"model": "m", "messages": [{"role": "user", "content": content}],
               "stream": True, "stream_options": {"include_usage": True},
               "temperature": 0.0, "max_tokens": max_tokens, "seed": 0,
               "cache_prompt": cache_prompt, "logprobs": True, "top_logprobs": TOP_LOGPROBS}
    data = json.dumps(payload).encode()
    req = urllib.request.Request(f"{dfl.BASE}/v1/chat/completions", data=data,
                                 headers={"Content-Type": "application/json"})
    clk0 = dfl.gpu_freq()
    first_top = None; first_token = None; usage = None; timings = None
    ttft = None; text = ""
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
        if o.get("timings"): timings = o["timings"]
        if o.get("usage"): usage = o["usage"]
        ch = (o.get("choices") or [{}]); c0 = ch[0] if ch else {}
        delta = c0.get("delta", {}) if c0 else {}
        lp = c0.get("logprobs") if c0 else None
        if lp and lp.get("content"):
            for item in lp["content"]:
                if first_top is None:
                    first_top = item.get("top_logprobs") or []
                    first_token = item.get("token")
        if delta.get("content"):
            if ttft is None:
                ttft = time.perf_counter() - t0
            text += delta["content"]
    total = time.perf_counter() - t0
    clk1 = dfl.gpu_freq()
    tim = timings or {}; usg = usage or {}
    return {"first_token": first_token, "first_top": first_top, "answer_text": text[:80],
            "ttft_s": round(ttft, 4) if ttft else None, "total_s": round(total, 4),
            "prompt_tokens": usg.get("prompt_tokens"), "cache_n": tim.get("cache_n"),
            "evaluated": tim.get("prompt_n"), "n_gen": tim.get("predicted_n"),
            "prompt_ms": tim.get("prompt_ms"),
            "clock_ok": (clk0 == PINNED_HZ and clk1 == PINNED_HZ)}


def run_server(header, rels, est_frames, dev, qids, sampler, tag):
    """Warm the history (cache_prompt) then answer each question (image re-send)."""
    e8.erase_slot()
    prime = e8.build_append_content(header, rels[:est_frames])
    pr = server_chat(prime, cache_prompt=True, max_tokens=1)
    out = {}
    for qid in qids:
        content = e8.build_append_content(header, rels[:est_frames])
        content.append({"type": "text", "text": dev[qid]["text"]})
        rec = server_chat(content, cache_prompt=True, max_tokens=MAX_TOKENS)
        out[qid] = rec
    print(f"[server {tag}] {len(out)} questions, history prompt_tokens={pr['prompt_tokens']}", flush=True)
    return pr, out


# ── equivalence ──────────────────────────────────────────────────────────────
def compare_top(h_top20, s_top):
    """h_top20: [[tok,lp],...] from harness; s_top: [{token,logprob},...] from server.
    Returns (argmax_match, max_abs_diff_on_shared, n_shared)."""
    h = {t: lp for t, lp in h_top20}
    s = {d["token"]: d["logprob"] for d in (s_top or [])}
    h_arg = max(h, key=h.get) if h else None
    s_arg = max(s, key=s.get) if s else None
    shared = set(h) & set(s)
    md = max((abs(h[k] - s[k]) for k in shared), default=None)
    return (h_arg == s_arg), md, len(shared), h_arg, s_arg


def pct(xs, q):
    xs = sorted(v for v in xs if v is not None)
    if not xs:
        return None
    i = q / 100 * (len(xs) - 1); lo = int(i); hi = min(lo + 1, len(xs) - 1)
    return round(xs[lo] + (xs[hi] - xs[lo]) * (i - lo), 4)


def summarize(path_rows, key_ttft="ttft_s", key_total="total_s"):
    tt = [r[key_ttft] for r in path_rows if r.get(key_ttft) is not None]
    to = [r[key_total] for r in path_rows if r.get(key_total) is not None]
    return {"n": len(path_rows),
            "ttft_s": {"p50": pct(tt, 50), "p90": pct(tt, 90),
                       "min": round(min(tt), 4) if tt else None, "max": round(max(tt), 4) if tt else None},
            "total_s": {"p50": pct(to, 50), "p90": pct(to, 90),
                        "min": round(min(to), 4) if to else None, "max": round(max(to), 4) if to else None}}


def check_exclusive():
    """Record the process list and flag any frame-transfer or Part-1-scoring
    process that would violate the exclusive-GPU / same-day rule during a timed
    batch. Our own llama-server is allowed; it is recorded, not flagged."""
    import re
    try:
        ps = subprocess.check_output(["ps", "-eo", "pid,args"], text=True)
    except Exception:
        ps = ""
    def hits(pat):
        return [l.strip() for l in ps.splitlines() if re.search(pat, l) and "grep" not in l and "ps -eo" not in l]
    frame_transfer = hits(r"\brsync\b|\bscp\b|\bsftp\b")
    part1_scoring = hits(r"study_orin2_calibrate\.py.*--score|study_orin1_dense\.py|study_d15_orin_nexar\.py")
    gpu_procs = hits(r"llama-server|vllm")
    disallowed = []
    if frame_transfer: disallowed.append("frame_transfer")
    if part1_scoring: disallowed.append("part1_scoring")
    return {"frame_transfer": frame_transfer, "part1_scoring": part1_scoring,
            "gpu_procs": gpu_procs, "disallowed_found": disallowed}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gate-only", action="store_true", help="run only the 11k 3-question equivalence gate")
    args = ap.parse_args()
    OUTC.mkdir(parents=True, exist_ok=True)
    SCRATCH.mkdir(parents=True, exist_ok=True)

    reqs, dev, dev_ids, vid, rels, header = substrate()
    maxf = len(rels)
    abs_rels = [str(e8.E7DIR / r) for r in rels]
    gate_ids = dev_ids[:N_GATE]
    print(f"[2] substrate {vid}: {maxf} frames; {len(dev_ids)} DEV questions; gate={gate_ids}", flush=True)
    sizes = {t: est_frames_for(t, maxf) for t in TARGETS}
    print(f"[2] est_frames: {sizes}", flush=True)

    # ---------- EQUIVALENCE GATE (3 Q @ 11k), harness then server, never concurrent ----------
    ef = sizes[GATE_SIZE]
    gate_qs = [{"id": q, "text": dev[q]["text"]} for q in gate_ids]
    h_meta_g, h_g = run_harness(header, abs_rels[:ef], gate_qs, f"gate{GATE_SIZE}")

    sampler = dfl.Sampler(str(SCRATCH / "orin2_warm_tegrastats.jsonl.gz"))
    proc = e8.launch_server_e8(str(OUTC / "orin2_server.log"), n_ctx=e8.N_CTX)
    s_g, s_g2 = {}, {}
    try:
        # run each gate question on the server TWICE, each with a fresh re-encode
        # (erase slot -> prime -> ask). s_g is the reference; s_g vs s_g2 is the
        # server's own run-to-run jitter from re-encoding the history -- the
        # natural yardstick for how close "the same computation" can be on this
        # FP16/flash-attn stack, independent of the harness.
        for pass_store in (s_g, s_g2):
            for q in gate_ids:
                e8.erase_slot()
                prime = e8.build_append_content(header, rels[:ef])
                server_chat(prime, cache_prompt=True, max_tokens=1)
                content = e8.build_append_content(header, rels[:ef])
                content.append({"type": "text", "text": dev[q]["text"]})
                pass_store[q] = server_chat(content, cache_prompt=True, max_tokens=MAX_TOKENS)
    finally:
        dfl.stop_server(proc)

    h_hist_tok = h_meta_g["history_tokens"] if h_meta_g else None
    gate = []
    for q in gate_ids:
        ok, md, nsh, ha, sa = compare_top(h_g[q]["top20"], s_g[q]["first_top"])
        # server self-jitter (run A vs run B), same top-20 comparison
        _, jit, _, _, _ = compare_top([[d["token"], d["logprob"]] for d in (s_g[q]["first_top"] or [])],
                                      s_g2[q]["first_top"])
        h_ptok = (h_hist_tok + h_g[q]["n_suffix_tokens"]) if h_hist_tok is not None else None
        s_ptok = s_g[q].get("prompt_tokens")
        gate.append({"question_id": q, "argmax_match": ok, "max_abs_logprob_diff": md,
                     "server_self_jitter_logprob": jit, "n_shared_top": nsh,
                     "harness_argmax": ha, "server_argmax": sa,
                     "harness_prompt_tokens": h_ptok, "server_prompt_tokens": s_ptok,
                     "prompt_tokens_match": (h_ptok == s_ptok),
                     "harness_answer": h_g[q]["answer_text"][:40], "server_answer": s_g[q]["answer_text"][:40]})
    worst = max((g["max_abs_logprob_diff"] for g in gate if g["max_abs_logprob_diff"] is not None), default=None)
    worst_jitter = max((g["server_self_jitter_logprob"] for g in gate if g["server_self_jitter_logprob"] is not None), default=None)
    all_argmax = all(g["argmax_match"] for g in gate)
    all_tokmatch = all(g["prompt_tokens_match"] for g in gate)
    gate_pass = bool(all_argmax and all_tokmatch and worst is not None and worst <= LOGPROB_TOL)
    gate_res = {"tolerance_nats": LOGPROB_TOL, "size": GATE_SIZE, "n_questions": N_GATE,
                "history_n_past_harness": h_meta_g["history_n_past"] if h_meta_g else None,
                "history_tokens_harness": h_hist_tok,
                "all_argmax_match": all_argmax, "all_prompt_tokens_match": all_tokmatch,
                "worst_max_abs_logprob_diff": worst, "worst_server_self_jitter": worst_jitter,
                "pass": gate_pass, "per_question": gate,
                "tolerance_provenance": {
                    "pre_registered_tol_nats": LOGPROB_TOL_PRE,
                    "pre_registered_outcome": "FAIL (observed 0.064-0.100 nats > 0.05)",
                    "post_hoc_tol_nats": LOGPROB_TOL,
                    "post_hoc": True, "pre_registered_pass": False,
                    "reason": ("server bit-deterministic (self-jitter 0.0); prompts token-identical "
                               "(history+suffix == server prompt_tokens); answer token and full top-20 set "
                               "identical; residual gap is the harness batching the image ENCODE differently "
                               "from the server; image encoding is part of building the warm history, which is "
                               "EXCLUDED from the timed path, so it does not affect the measured latency"),
                    "criteria": "token-identical prompt AND identical answer token AND identical top-20 set AND logprob diff <= 0.15 nats"}}
    json.dump(gate_res, open(OUTC / "orin2_equivalence_gate.json", "w"), indent=1)
    sampler.stop()
    print(json.dumps(gate_res, indent=1), flush=True)
    if not gate_pass:
        print("[2] EQUIVALENCE GATE FAILED - stopping before timing.", flush=True)
        sys.exit(3)
    if args.gate_only:
        return

    # ---------- full timing, both paths, both sizes (harness alone, then server alone) ----------
    all_qs = [{"id": q, "text": dev[q]["text"]} for q in dev_ids]
    exclusivity = {}

    # harness batch (exclusive): record the process list; stop if anything disallowed runs
    exclusivity["harness_batch"] = check_exclusive()
    if exclusivity["harness_batch"]["disallowed_found"]:
        print("[2] NON-EXCLUSIVE during harness batch:", exclusivity["harness_batch"]["disallowed_found"], flush=True)
        json.dump(exclusivity, open(OUTC / "orin2_exclusivity.json", "w"), indent=1)
        sys.exit(5)
    harness = {}
    for t in TARGETS:
        ef = sizes[t]
        hm, hd = run_harness(header, abs_rels[:ef], all_qs, f"full{t}")
        harness[t] = {"meta": hm, "data": hd}

    sampler = dfl.Sampler(str(SCRATCH / "orin2_warm_tegrastats_full.jsonl.gz"))
    proc = e8.launch_server_e8(str(OUTC / "orin2_server.log"), n_ctx=e8.N_CTX)
    server = {}
    try:
        # server batch (exclusive, our server allowed): record + stop if disallowed
        exclusivity["server_batch"] = check_exclusive()
        if exclusivity["server_batch"]["disallowed_found"]:
            print("[2] NON-EXCLUSIVE during server batch:", exclusivity["server_batch"]["disallowed_found"], flush=True)
            raise SystemExit(5)
        for t in TARGETS:
            pr, sd = run_server(header, rels, sizes[t], dev, dev_ids, sampler, f"full{t}")
            server[t] = {"prime": pr, "data": sd}
    finally:
        dfl.stop_server(proc)
    sampler.stop()
    json.dump(exclusivity, open(OUTC / "orin2_exclusivity.json", "w"), indent=1)

    # ---------- persist raw rows FIRST (so a failed check never loses data) ----------
    def ftok(x):
        return (x or "").strip()
    rows = []
    for t in TARGETS:
        hist_tok = harness[t]["meta"]["history_tokens"] if harness[t]["meta"] else None
        for q in dev_ids:
            h = harness[t]["data"].get(q, {}); s = server[t]["data"].get(q, {})
            rows.append({"target_tok": t, "frames": sizes[t], "question_id": q,
                         "harness_first_token": h.get("first_token"), "server_first_token": s.get("first_token"),
                         "answer_match": ftok(h.get("first_token")) == ftok(s.get("first_token")),
                         "harness_ttft_s": h.get("ttft_s"), "harness_total_s": h.get("total_s"),
                         "harness_question_tokens": h.get("n_suffix_tokens"), "harness_n_gen": h.get("n_gen"),
                         "harness_history_tokens": hist_tok, "harness_history_n_past": h.get("history_n_past"),
                         "harness_clock_ok": (h.get("gpu_freq_before") == PINNED_HZ and h.get("gpu_freq_after") == PINNED_HZ),
                         "server_ttft_s": s.get("ttft_s"), "server_total_s": s.get("total_s"),
                         "server_question_evaluated": s.get("evaluated"), "server_cache_n": s.get("cache_n"),
                         "server_prompt_ms": s.get("prompt_ms"), "server_n_gen": s.get("n_gen"),
                         "server_prompt_tokens": s.get("prompt_tokens"), "server_clock_ok": s.get("clock_ok"),
                         "boundary_offset_tokens": ((h.get("n_suffix_tokens") - s.get("evaluated"))
                                                    if h.get("n_suffix_tokens") is not None and s.get("evaluated") is not None else None),
                         # decomposition: server TTFT = model question-eval (prompt_ms) + everything else
                         "server_model_work_ms": s.get("prompt_ms"),
                         "server_everything_else_ms": (round(s["ttft_s"] * 1000 - s["prompt_ms"], 1)
                                                       if s.get("ttft_s") is not None and s.get("prompt_ms") is not None else None)})
    with open(OUTC / "orin2_warm_recall.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")

    # ---------- cross-path verification on all 40 (condition 2, redefined per user) ----------
    # Pass requires: (a) total prompt tokens identical, (b) answer token identical, and
    # (c) harness question-tokens-evaluated >= server question-tokens-evaluated (the
    # harness never does LESS work than the server). The ~15-token cache/eval boundary
    # offset (server's prefix cache extends past the last image; totals conserved) is
    # allowed because it biases AGAINST the device (harness evaluates a superset).
    mism_total, mism_answer, harness_fewer, offsets = [], [], [], []
    for t in TARGETS:
        hist_tok = harness[t]["meta"]["history_tokens"] if harness[t]["meta"] else None
        for q in dev_ids:
            h = harness[t]["data"].get(q, {}); s = server[t]["data"].get(q, {})
            h_total = (hist_tok + h["n_suffix_tokens"]) if (hist_tok is not None and h.get("n_suffix_tokens") is not None) else None
            s_total = s.get("prompt_tokens")
            if h_total != s_total:
                mism_total.append({"size": t, "q": q, "harness_total": h_total, "server_total": s_total})
            if ftok(h.get("first_token")) != ftok(s.get("first_token")):
                mism_answer.append({"size": t, "q": q, "harness": h.get("first_token"), "server": s.get("first_token")})
            if h.get("n_suffix_tokens") is not None and s.get("evaluated") is not None:
                off = h["n_suffix_tokens"] - s["evaluated"]
                offsets.append(off)
                if off < 0:
                    harness_fewer.append({"size": t, "q": q, "harness_qtok": h["n_suffix_tokens"], "server_evaluated": s["evaluated"]})
    from collections import Counter
    crosscheck = {"n_measurements": 2 * len(dev_ids),
                  "criteria": "total prompt tokens identical AND answer token identical AND harness_qtok >= server_evaluated",
                  "n_total_mismatch": len(mism_total), "n_answer_mismatch": len(mism_answer),
                  "n_harness_fewer_tokens": len(harness_fewer),
                  "boundary_offset_distribution": dict(Counter(offsets)),
                  "boundary_offset_median": int(st.median(offsets)) if offsets else None,
                  "boundary_offset_cause": ("server prefix cache extends ~15 template/vision-wrapper tokens past "
                                            "the last image into the cached region; totals conserved; harness "
                                            "evaluates that superset, biasing against the device (conservative)"),
                  "total_mismatches": mism_total[:10], "answer_mismatches": mism_answer[:10],
                  "harness_fewer_token_cases": harness_fewer[:10],
                  "pass": not (mism_total or mism_answer or harness_fewer)}
    json.dump(crosscheck, open(OUTC / "orin2_warm_crosscheck.json", "w"), indent=1)
    if not crosscheck["pass"]:
        print("[2] CROSS-PATH CHECK FAILED - stopping before reporting latencies.", flush=True)
        print(json.dumps({k: crosscheck[k] for k in ("n_total_mismatch", "n_answer_mismatch", "n_harness_fewer_tokens",
              "total_mismatches", "answer_mismatches", "harness_fewer_token_cases")}, indent=1), flush=True)
        sys.exit(4)
    print(f"[2] cross-path check PASS: totals identical, 0 answer mismatch, harness >= server on all "
          f"{2*len(dev_ids)}; boundary offset median {crosscheck['boundary_offset_median']} tokens", flush=True)

    summary = {"substrate": {"video": vid, "max_frames": maxf, "dev_questions": len(dev_ids)},
               "gate": gate_res, "crosscheck": crosscheck, "exclusivity": exclusivity, "sizes": {}}
    for t in TARGETS:
        hrows = [harness[t]["data"][q] for q in dev_ids if q in harness[t]["data"]]
        srows = [server[t]["data"][q] for q in dev_ids if q in server[t]["data"]]
        hist_np = harness[t]["meta"]["history_n_past"] if harness[t]["meta"] else None
        hist_tk = harness[t]["meta"]["history_tokens"] if harness[t]["meta"] else None
        s_prompt_ms = [s["prompt_ms"] for s in srows if s.get("prompt_ms")]
        h_suffix = [h["n_suffix_tokens"] for h in hrows if h.get("n_suffix_tokens")]
        h_ttft = [h["ttft_s"] for h in hrows if h.get("ttft_s")]
        s_ttft = [s["ttft_s"] for s in srows if s.get("ttft_s")]
        s_total = [s["total_s"] for s in srows if s.get("total_s")]
        h_total = [h["total_s"] for h in hrows if h.get("total_s")]
        s_else = [s["ttft_s"] * 1000 - s["prompt_ms"] for s in srows
                  if s.get("ttft_s") is not None and s.get("prompt_ms") is not None]
        s_eval = [s["evaluated"] for s in srows if s.get("evaluated")]
        off_t = [h["n_suffix_tokens"] - s["evaluated"] for h, s in zip(hrows, srows)
                 if h.get("n_suffix_tokens") is not None and s.get("evaluated") is not None]
        off_med = st.median(off_t) if off_t else 0
        # per-token question-eval rate on each path, and the cost of the boundary-offset tokens
        h_ms_per_tok = (st.median(h_ttft) * 1000 / st.median(h_suffix)) if h_suffix and h_ttft else None
        s_ms_per_tok = (st.median(s_prompt_ms) / st.median(s_eval)) if s_prompt_ms and s_eval else None
        bias = {"offset_tokens_median": off_med,
                "harness_ms_per_question_token": round(h_ms_per_tok, 3) if h_ms_per_tok else None,
                "server_ms_per_question_token": round(s_ms_per_tok, 3) if s_ms_per_tok else None,
                "bias_ms_at_harness_rate": round(off_med * h_ms_per_tok, 2) if h_ms_per_tok else None,
                "bias_ms_at_server_rate": round(off_med * s_ms_per_tok, 2) if s_ms_per_tok else None,
                "note": ("the harness evaluates off_med extra tokens; at the harness question-eval rate this "
                         "adds bias_ms_at_harness_rate to harness TTFT, making it SLOWER than the true device "
                         "cost (conservative toward the device)")}
        ratio = {"ttft_p50_server_over_harness": (round(pct(s_ttft, 50) / pct(h_ttft, 50), 1)
                                                  if pct(h_ttft, 50) else None),
                 "total_p50_server_over_harness": (round(pct(s_total, 50) / pct(h_total, 50), 1)
                                                   if pct(h_total, 50) else None)}
        summary["sizes"][str(t)] = {
            "frames": sizes[t], "harness_history_n_past": hist_np, "harness_history_tokens": hist_tk,
            "server_prompt_tokens_median": int(st.median([s["prompt_tokens"] for s in srows if s.get("prompt_tokens")])) if srows else None,
            "server_cache_n_median": int(st.median([s["cache_n"] for s in srows if s.get("cache_n")])) if srows else None,
            "harness": summarize(hrows), "server": summarize(srows),
            "harness_question_tokens_median": int(st.median(h_suffix)) if h_suffix else None,
            "server_question_evaluated_median": int(st.median([s["evaluated"] for s in srows if s.get("evaluated")])) if srows else None,
            "harness_tok_per_s_question": (round(st.median(h_suffix) / st.median(h_ttft), 1)
                                           if h_suffix and h_ttft and st.median(h_ttft) > 0 else None),
            # decomposition: model question-eval work vs everything else, both paths
            "decomposition": {
                "server_ttft_p50_s": pct(s_ttft, 50),
                "server_model_work_p50_ms": round(st.median(s_prompt_ms), 1) if s_prompt_ms else None,
                "server_everything_else_p50_ms": round(st.median(s_else), 1) if s_else else None,
                "harness_ttft_p50_s": pct(h_ttft, 50),
                "harness_model_work_p50_ms": round(st.median(h_ttft) * 1000, 1) if h_ttft else None,
                "note": ("harness TTFT is in-process question-eval over the cached KV (no image re-send); "
                         "server everything_else = TTFT - prompt_ms is the API image re-send+re-parse the "
                         "harness removes")},
            "boundary_offset_median_tokens": off_med,
            "bias_from_boundary_offset": bias,
            "ratio_server_over_harness": ratio,
            "harness_clock_pinned_all": all((h.get("gpu_freq_before") == PINNED_HZ and h.get("gpu_freq_after") == PINNED_HZ) for h in hrows),
            "server_clock_pinned_all": all(s.get("clock_ok") for s in srows)}
    # scaling: does harness TTFT grow with history? (should, only via attention over cached ctx)
    if len(TARGETS) == 2:
        a, b = TARGETS
        ha = st.median([harness[a]["data"][q]["ttft_s"] for q in dev_ids if q in harness[a]["data"]])
        hb = st.median([harness[b]["data"][q]["ttft_s"] for q in dev_ids if q in harness[b]["data"]])
        hna = harness[a]["meta"]["history_n_past"]; hnb = harness[b]["meta"]["history_n_past"]
        summary["harness_ttft_slope_ms_per_history_token"] = (
            round(1000 * (hb - ha) / (hnb - hna), 5) if hnb != hna else None)
    summary["_provenance"] = stamp(script="study_orin2_warm.py", model="4bi_f16",
                                   device="jetson_orin", n=len(rows), args={"part": 2})
    json.dump(summary, open(OUTC / "orin2_warm_recall_summary.json", "w"), indent=1)
    print(json.dumps({k: summary[k] for k in ("sizes", "harness_ttft_slope_ms_per_history_token")
                      if k in summary}, indent=1), flush=True)
    print("wrote", OUTC / "orin2_warm_recall_summary.json")


if __name__ == "__main__":
    main()
