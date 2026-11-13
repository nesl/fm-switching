#!/usr/bin/env python3
"""StudySLICE1 Part A (gate) — can an append-only D2 history be materialized as a chain of prefix-chained slices with
small per-slice overhead? EXCLUSIVE (vLLM venv; h100nvl GPU 2). Pre-registered in research/EXPERIMENTS.md (StudySLICE1).

Server: 32B-Instruct, vLLM 0.31.0 defaults (E10c E0: chunked prefill, 8,192-token steps, fcfs, async scheduling),
prefix caching ON, multimodal processor cache 128 GiB, `--enable-log-requests` (study_e10d_blocking.start_server, E0).
Image-by-reference protocol = RH7's DELTA (study_rh7_eager_lazy.body7): every image part carries a client uuid
'{ns}|{frame path}'; the first request that contains a frame sends its PNG bytes + uuid, later requests send
{"type": "image_url", "image_url": null, "uuid": U}, taken from the processor cache (HTTP 400 on a miss, never silent).
Prefix-cache block keys use that uuid as the item hash, so the KV of earlier slices is reused.
"Cache cleared" = a fresh namespace per monolithic repeat and per chain: a new header tag (first text token differs)
and new uuids, so neither the prefix cache nor the processor cache can serve anything; checked (cached tokens of the
first request <= 16).
Sessions: RH4 / RH7 D2 histories (one 352x256 frame every 2 s, ~90 tokens / frame, RH6 PNG fragments) up to a question
time qt: the 20 distinct sessions whose question history is closest to 11,000 tokens and the 20 closest to 28,000
(user decision 2026-11-12: 2A, 25.9-27.1k).
Per session: monolithic (one cold request: header + all frames + question, max_tokens 4) x 5; then for n in
512 / 1024 / 2048 / 4096: a chain of requests, slice j = cached prefix + the next floor(n / 90) frames (max_tokens 1),
the last slice carries the remaining frames + the question (max_tokens 4). Requests strictly sequential, 0.2 s apart,
with /metrics histogram deltas per request (queue, prefill = scheduled -> first token, engine TTFT, inference).
Rows -> results/cost/study_slice1/slice1_gate_requests_h100nvl.jsonl, meta slice1_gate_run_meta_h100nvl.json.
"""
import argparse
import asyncio
import json
import re
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import study_e10d_blocking as D  # noqa: E402  (logging config + start_server + metrics)

E, X, F = D.E, D.X, D.F
R6, R7 = E.R6, E.R7
OUT = E.REPO / "results/cost/study_slice1"
REQ = OUT / "slice1_gate_requests_h100nvl.jsonl"
E.MON = OUT / "slice1_gate_monitor_h100nvl.jsonl"
X.META_PATH = OUT / "slice1_gate_run_meta_h100nvl.json"
X.CURRENT = E.REPO / "logs/slice1_current.json"
TARGETS = (11000, 28000)
NSESS = 20
REPEATS = 5
NS_SLICE = (512, 1024, 2048, 4096)
TOK_PER_FRAME = 90
HDR_TOK = 31
PAUSE = 0.2
LETTER = re.compile(r"\b([A-E])\b")


def pick_sessions(S):
    out = []
    for tgt in TARGETS:
        best = {}
        for i, s in enumerate(S):
            for q in s["questions"]:
                tok = HDR_TOK + TOK_PER_FRAME * len(R6.frames(s, float(q["qt"])))
                d = abs(tok - tgt)
                if s["video_id"] not in best or d < best[s["video_id"]][0]:
                    best[s["video_id"]] = (d, tok, i, q)
        for d, tok, i, q in sorted(best.values(), key=lambda x: (x[0], x[2]))[:NSESS]:
            out.append(dict(target=tgt, sess_i=i, video_id=S[i]["video_id"], qid=q["qid"], qt=float(q["qt"]),
                            est_tokens=tok, question=q["text"]))
    return out


async def post(c, data):
    t0 = time.time()
    first, usage, text, err = None, None, "", None
    async with c.stream("POST", f"{X.BASE}/v1/chat/completions", content=data,
                        headers={"Content-Type": "application/json"}) as r:
        if r.status_code != 200:
            err = f"HTTP {r.status_code}: {(await r.aread())[:300]!r}"
        else:
            async for line in r.aiter_lines():
                if not line.startswith("data: ") or line == "data: [DONE]":
                    continue
                j = json.loads(line[6:])
                if j.get("usage"):
                    usage = j["usage"]
                for ch in j.get("choices", []):
                    dl = (ch.get("delta") or {}).get("content")
                    if dl:
                        if first is None:
                            first = time.time()
                        text += dl
    t1 = time.time()
    return dict(t_send=t0, ttft_s=round(first - t0, 4) if first else None, latency_s=round(t1 - t0, 4),
                prompt_tokens=usage and usage["prompt_tokens"],
                cached_tokens=((usage or {}).get("prompt_tokens_details") or {}).get("cached_tokens"),
                completion_tokens=usage and usage["completion_tokens"], output=text, error=err)


async def one(c, data, extra):
    m0 = await D.metrics(c)
    rec = await post(c, data)
    await asyncio.sleep(PAUSE)
    m1 = await D.metrics(c)
    d = {k: m1.get(k, 0) - m0.get(k, 0) for k in m1}
    for h in ("request_queue_time_seconds", "request_prefill_time_seconds", "time_to_first_token_seconds",
              "request_inference_time_seconds"):
        rec[h.replace("_seconds", "_s")] = round(d[h + "_sum"], 4) if d.get(h + "_count") == 1 else None
    rec["engine_s"] = (round((rec["request_queue_time_s"] or 0) + rec["request_prefill_time_s"], 4)
                       if rec["request_prefill_time_s"] is not None else None)
    rec["computed_tokens"] = (rec["prompt_tokens"] - (rec["cached_tokens"] or 0)) if rec["prompt_tokens"] else None
    rec["body_bytes"] = len(data)
    m = LETTER.search(rec["output"] or "")
    rec["letter"] = m.group(1) if m else None
    rec.update(extra)
    with open(REQ, "a") as f:
        f.write(json.dumps(rec) + "\n")
    return rec


async def run_session(c, S, ps, chain_seq):
    sess = S[ps["sess_i"]]
    fr = R6.frames(sess, ps["qt"])
    base = dict(target=ps["target"], sess_i=ps["sess_i"], video_id=ps["video_id"], qid=ps["qid"], qt=ps["qt"],
                n_frames_total=len(fr))
    mono = []
    for rep in range(REPEATS):
        tag = f"S1M{next(chain_seq)}"
        ns = f"{tag}|{ps['sess_i']}"
        hdr = R6.header(tag, 0, ps["sess_i"])
        data = R7.body7("D2", hdr, sess, ps["qt"], ps["question"], R7.F.ESC_MAX_TOKENS, "fullu", ns, -1.0)[0]
        r = await one(c, data, dict(base, mode="mono", n=None, rep=rep, chain=tag, slice=0, n_slices=1,
                                    slice_frames=len(fr), final=True))
        mono.append(r)
        X.log(f"{ps['video_id'][:16]} mono {rep}: prompt {r['prompt_tokens']} cached {r['cached_tokens']} "
              f"engine {r['engine_s']} ttft {r['ttft_s']} letter {r['letter']} {r['error'] or ''}")
    for n in NS_SLICE:
        k = max(1, n // TOK_PER_FRAME)
        chunks = [fr[i:i + k] for i in range(0, len(fr), k)]
        tag = f"S1C{next(chain_seq)}"
        ns = f"{tag}|{ps['sess_i']}"
        hdr = R6.header(tag, 0, ps["sess_i"])
        prev_prompt, sent = None, -1.0
        t_chain = time.time()
        recs = []
        for j, ch in enumerate(chunks):
            last = j == len(chunks) - 1
            upto = ch[-1][0]
            data = R7.body7("D2", hdr, sess, upto, ps["question"] if last else None,
                            R7.F.ESC_MAX_TOKENS if last else 1, "delta", ns, sent)[0]
            r = await one(c, data, dict(base, mode="chain", n=n, frames_per_slice=k, rep=None, chain=tag, slice=j,
                                        n_slices=len(chunks), slice_frames=len(ch), final=last,
                                        prev_prompt_tokens=prev_prompt))
            r_gap = (prev_prompt - (r["cached_tokens"] or 0)) if prev_prompt is not None else None
            recs.append(r)
            if r["error"]:
                X.log(f"chain {tag} slice {j}: ERROR {r['error']}")
                break
            if j == 0 and (r["cached_tokens"] or 0) > 16:
                raise SystemExit(f"{tag}: first slice served {r['cached_tokens']} cached tokens — cache not cleared, STOP")
            if r_gap is not None and r_gap > 32:
                raise SystemExit(f"{tag} slice {j}: cached {r['cached_tokens']} vs previous prompt {prev_prompt} "
                                 f"(gap {r_gap} > 32) — cached tokens do not equal the previous prefix, STOP")
            prev_prompt, sent = r["prompt_tokens"], upto
        wall = time.time() - t_chain
        eng = sum(x["engine_s"] or 0 for x in recs)
        X.log(f"{ps['video_id'][:16]} n {n}: {len(recs)} slices, wall {wall:.2f}s engine {eng:.2f}s computed "
              f"{sum(x['computed_tokens'] or 0 for x in recs)} letter {recs[-1]['letter']} (mono {mono[0]['letter']}) "
              f"gaps {[ (recs[i-1]['prompt_tokens'] - (recs[i]['cached_tokens'] or 0)) for i in range(1, len(recs))][:6]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="smoke: first k sessions per target")
    a = ap.parse_args()
    global REQ
    OUT.mkdir(parents=True, exist_ok=True)
    if a.limit:
        REQ = OUT / "slice1_gate_smoke_requests_h100nvl.jsonl"
        X.META_PATH = OUT / "slice1_gate_smoke_run_meta_h100nvl.json"
        E.MON = OUT / "slice1_gate_smoke_monitor_h100nvl.jsonl"
    S = E.FL.sessions()
    picks = pick_sessions(S)
    if a.limit:
        picks = [p for t in TARGETS for p in [x for x in picks if x["target"] == t][:a.limit]]
    start = E.snapshot("start")
    if start["ours_outside_job"]:
        raise SystemExit(f"not exclusive at start: {start['ours_outside_job']} — STOP")
    import torch
    import vllm
    m = X.meta_load()
    m["stack"] = dict(venv=sys.prefix, vllm=vllm.__version__, torch=torch.__version__, gpu="h100nvl GPU 2",
                      gpu_uuid=F.GPU_UUID, kv_flags=E.KV["KVGPU"], log_flags=D.LOGFLAGS, repeats=REPEATS,
                      ns_slice=NS_SLICE, tok_per_frame=TOK_PER_FRAME, pause=PAUSE, esc_max_tokens=R7.F.ESC_MAX_TOKENS)
    m["sessions"] = [{k: v for k, v in p.items() if k != "question"} for p in picks]
    m["limit"] = a.limit
    X.meta_save(m)
    th = threading.Thread(target=E.monitor, daemon=True)
    th.start()
    import itertools
    seq = itertools.count()
    try:
        R6.preencode("D2", [S[p["sess_i"]] for p in picks])
        srv = D.start_server("E0", "SLICE1_A" + ("_smoke" if a.limit else ""))
        try:
            async def go():
                import httpx
                async with httpx.AsyncClient(timeout=None) as c:
                    for p in picks:
                        await run_session(c, S, p, seq)
                        if E.VOID.is_set():
                            raise SystemExit("run VOID — STOP")
            asyncio.run(go())
        finally:
            srv.stop()
    finally:
        E.STOP_MON.set()
        E.snapshot("end")
        m = X.meta_load()
        m["void"] = E.VOID.is_set()
        X.meta_save(m)
    from _provenance import stamp
    m = X.meta_load()
    m.setdefault("_provenance", []).append(stamp(script="study_slice1_gate.py", model="qwen3vl-32b-instruct",
                                                 device="h100nvl_gpu2", args=a))
    X.meta_save(m)


if __name__ == "__main__":
    main()
