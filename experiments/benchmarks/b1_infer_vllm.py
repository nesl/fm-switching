#!/usr/bin/env python3
"""StudyB1-h100 inference (vLLM venv; h100nvl GPU 2). ACCURACY ONLY — batched, concurrency 8; no latency is reported.

Stack: D-series vLLM 0.31.0 via study_x_vllm.Server (FA3, max_model_len 32768, gmu 0.90, TP 1, prefix caching OFF,
bf16, server seed 0) + --mm-processor-cache-gb 0, --limit-mm-per-prompt {"image": 37, "video": 0} (checked in the
server log and by the first 37-image request; failure stops the arm). Pinned snapshots: 4BI @ebb281ec, 32BI @0cfaf481,
32BT @7edd10ff.
Arms / plans:
  --plan bridge   --model 4BI : greedy, max_tokens 64, logprobs top 20; first 300 requests of each dataset's fixed order
                  per input (RECENT, HISTORY) + 100 grey per input (first 50 of each dataset's order).
  --plan mv       --model 32BI: mechanism verification BEFORE any sweep: 18 smoke requests (3 per part x input; trace) + 4
                  grey, then the repeat control (first 10 RECENT items of each part, run twice) -> b1_mv_32BI.jsonl.gz.
  --plan instruct --model 32BI: same decoding; RECENT: OVO forward, OVO other, RTV (fixed order) + 100 grey; then
                  HISTORY likewise.
  --plan thinking --model 32BT: temperature 1.0, top_p 0.95, top_k 20, max_tokens 16384, seed 0, whole response saved;
                  batches of 200 alternating (RECENT: OVO forward, OVO other, RTV; HISTORY: same) in fixed order; the
                  100 grey per input after the first full cycle.
Requests are dispatched strictly in plan order; bodies are rendered ahead by a process pool (bounded window), never
reordered. Rows -> results/benchmarks/study_b1_h100/b1_rows_<model>.jsonl.gz (one gzip member per row; resumable).
Transport errors (no HTTP status) retried up to 2 more times, every attempt logged; an arm stops if > 1 % of its
requests remain failed, or if the server log shows an error. No retry on non-termination (truncation is recorded).
--deadline: no NEW request after this local time (default 2026-11-06T09:00); in-flight requests finish (timeout 1800 s).
"""
import argparse
import asyncio
import gzip
import json
import os
import sys
import time
import zlib
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "cost"))
sys.path.insert(0, str(HERE.parent / "lib"))
import b1_common as B  # noqa: E402
import study_x_vllm as X  # noqa: E402

X.REPO["4BI"] = ("Qwen/Qwen3-VL-4B-Instruct", "ebb281ec70b05090aa6165b016eac8ec08e71b17")
OUT = Path("results/benchmarks/study_b1_h100")
X.META_PATH = OUT / "b1_run_meta_h100nvl.json"
X.CURRENT = Path("logs/b1_current.json")
GPU_UUID = os.environ.get("CLEAN_GPU_UUID", "GPU-4f1d7e47-e769-a289-4860-e71c0d97267c")
FLAGS = ["--limit-mm-per-prompt", json.dumps({"image": 37, "video": 0}), "--mm-processor-cache-gb", "0",
         "--host", "127.0.0.1"]
GEN = {"instruct": dict(temperature=0.0, max_tokens=64, seed=0, logprobs=True, top_logprobs=20),
       "thinking": dict(temperature=1.0, top_p=0.95, top_k=20, max_tokens=16384, seed=0)}
CONC, ATTEMPTS, AHEAD, BATCH = 8, 3, 48, 200
TRANSPORT = ("ReadError", "RemoteProtocolError", "ConnectError", "WriteError", "ReadTimeout", "ConnectTimeout",
             "PoolTimeout", "WriteTimeout", "CloseError")
SRV_ERR = ("ERROR", "Traceback", "out of memory", "CUDA error", "OutOfMemory")
PARTS = ("ovo_forward", "ovo_other", "rtv")


def gpu_pids():
    import subprocess
    out = subprocess.run(["nvidia-smi", "--query-compute-apps=gpu_uuid,pid", "--format=csv,noheader"],
                         capture_output=True, text=True).stdout
    return [int(l.split(", ")[1]) for l in out.strip().splitlines() if l.startswith(GPU_UUID)]


X.gpu3_pids = lambda: gpu_pids()  # the wrapper's session check must look at GPU 2, not its default GPU 3


def plan(kind, order):
    """Ordered list of (tag, item_id, input, grey)."""
    by_part = {p: [it for ds in order for it in order[ds] if it["part"] == p] for p in PARTS}
    grey = [it for ds in ("ovo_bench", "rtv_bench") for it in order[ds][:50]]
    reqs = []
    if kind == "bridge":
        for inp in ("RECENT", "HISTORY"):
            for ds in ("ovo_bench", "rtv_bench"):
                reqs += [("main", it["item_id"], inp, False) for it in order[ds][:300]]
            reqs += [("grey", it["item_id"], inp, True) for it in grey]
    elif kind == "instruct":
        for inp in ("RECENT", "HISTORY"):
            for p in PARTS:
                reqs += [("main", it["item_id"], inp, False) for it in by_part[p]]
            reqs += [("grey", it["item_id"], inp, True) for it in grey]
    elif kind in ("smoke", "mv"):
        for inp in ("RECENT", "HISTORY"):
            for p in PARTS:
                reqs += [("smoke", it["item_id"], inp, False) for it in by_part[p][:3]]
            reqs += [("smoke_grey", it["item_id"], inp, True) for it in grey[:2]]
        if kind == "mv":  # negative control for the arm mechanism: the same arm twice on identical input
            for rep in (1, 2):
                reqs += [(f"mv_repeat{rep}", it["item_id"], "RECENT", False) for p in PARTS for it in by_part[p][:10]]
    elif kind == "thinking":
        cur = {(inp, p): 0 for inp in ("RECENT", "HISTORY") for p in PARTS}
        cycle = 0
        while any(cur[(inp, p)] < len(by_part[p]) for inp, p in cur):
            for inp in ("RECENT", "HISTORY"):
                for p in PARTS:
                    a = cur[(inp, p)]
                    reqs += [("main", it["item_id"], inp, False) for it in by_part[p][a:a + BATCH]]
                    cur[(inp, p)] = a + BATCH
            if cycle == 0:
                for inp in ("RECENT", "HISTORY"):
                    reqs += [("grey", it["item_id"], inp, True) for it in grey]
            cycle += 1
    return reqs


def read_rows(path):
    rows = []
    if not path.exists():
        return rows
    data = path.read_bytes()
    while data:  # tolerate a truncated last member after a crash
        d = zlib.decompressobj(16 + zlib.MAX_WBITS)
        try:
            chunk = d.decompress(data)
        except zlib.error:
            break
        for l in chunk.decode(errors="replace").splitlines():
            try:
                rows.append(json.loads(l))
            except json.JSONDecodeError:
                pass
        if not d.eof:
            break
        data = d.unused_data
    return rows


_ITEMS = None


def _worker_init():
    global _ITEMS
    _ITEMS = {it["item_id"]: it for it in B.build_items()}


def _build(args):
    item_id, inp, grey = args
    it = _ITEMS[item_id]
    content, fmeta = B.build_content(it, inp, grey=grey)
    return content, fmeta


async def run(args, reqs, items, rows_path, srv, deadline):
    done = {(r["tag"], r["item_id"], r["input"]) for r in read_rows(rows_path) if not r["error"]}
    todo = [q for q in reqs if (q[0], q[1], q[2]) not in done]
    X.log(f"B1 {args.model} {args.plan}: {len(reqs)} planned, {len(done)} done, {len(todo)} to run")
    thinking = args.model == "32BT"
    gen = GEN["thinking" if thinking else "instruct"]
    sem = asyncio.Semaphore(CONC)
    loop = asyncio.get_running_loop()
    pool = ProcessPoolExecutor(16, initializer=_worker_init)
    futs = {}
    state = dict(sent=0, stopped_at=None, first_history_ok=None)
    lock = asyncio.Lock()

    def submit(k):
        if k < len(todo) and k not in futs:
            tag, iid, inp, grey = todo[k]
            futs[k] = loop.run_in_executor(pool, _build, (iid, inp, grey))

    for k in range(min(AHEAD, len(todo))):
        submit(k)

    async def one(k, c):
        tag, iid, inp, grey = todo[k]
        it = items[iid]
        submit(k)
        content, fmeta = await futs.pop(k)
        submit(k + AHEAD)
        body = dict(model=args.model, messages=[{"role": "user", "content": content}], stream=False, **gen)
        for attempt in range(1, ATTEMPTS + 1):
            t0 = time.time()
            err, j = None, None
            try:
                r = await c.post(f"{X.BASE}/v1/chat/completions", json=body)
                j = r.json()
                if r.status_code != 200 or "choices" not in j:
                    err = f"HTTP {r.status_code}: {str(j)[:300]}"
            except Exception as e:  # noqa: BLE001
                err = f"{type(e).__name__}: {e}"
            text, fin, u, lp = None, None, {}, None
            if not err:
                ch = j["choices"][0]
                text = ch["message"].get("content")
                fin = ch.get("finish_reason")
                u = j.get("usage") or {}
                lpc = (ch.get("logprobs") or {}).get("content")
                if lpc:
                    lp = dict(first_token=lpc[0]["token"],
                              top20=[(t["token"], round(t["logprob"], 4)) for t in lpc[0]["top_logprobs"]],
                              chosen=[(t["token"], round(t["logprob"], 4)) for t in lpc])
            region = B.answer_region(text, thinking)
            sp, status = (None, "error") if err else B.strict_parse(it, region)
            rec = dict(arm=args.model, plan=args.plan, tag=tag, item_id=iid, dataset=it["dataset"], part=it["part"],
                       task=it["task"], input=inp, grey=grey, t=it["t"], video_key=it["video_key"], **fmeta,
                       prompt_tokens=u.get("prompt_tokens"), completion_tokens=u.get("completion_tokens"),
                       finish_reason=fin, text=text,
                       think_closed=("</think>" in text) if (thinking and text) else None, logprobs=lp,
                       correct_upstream=None if err else bool(B.upstream_correct(it, region)),
                       strict_answer=sp, strict_status=status, gt=it["gt"], error=err, attempt=attempt,
                       wall_s=round(time.time() - t0, 2), at=datetime.now().isoformat())
            async with lock:
                with gzip.open(rows_path, "at") as f:
                    f.write(json.dumps(rec) + "\n")
            if inp == "HISTORY" and not grey and state["first_history_ok"] is None:
                state["first_history_ok"] = err is None
                if err:
                    raise SystemExit(f"B1 {args.model}: first 37-image request failed: {err[:200]} — expected server "
                                     f"setting not in effect; STOP this arm")
            if err and err.split(":")[0] in TRANSPORT and attempt < ATTEMPTS:
                X.log(f"B1 transport error {iid} {inp} attempt {attempt} — retry")
                continue
            return rec

    async def worker(c, idx):
        while True:
            async with lock:
                k = state["sent"]
                if k >= len(todo):
                    return
                if datetime.now() >= deadline:
                    state["stopped_at"] = state["stopped_at"] or datetime.now().isoformat()
                    return
                state["sent"] = k + 1
            await one(k, c)
            if (k + 1) % 200 == 0:
                X.log(f"B1 {args.model} {args.plan}: {k + 1}/{len(todo)}")
                se = server_errors(srv)
                if se:
                    raise SystemExit(f"B1 {args.model}: server log error — STOP: {se[0]}")

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(1800.0, connect=30.0)) as c:
            await asyncio.gather(*(worker(c, i) for i in range(CONC)))
    finally:
        pool.shutdown(cancel_futures=True)
    return state


def server_errors(srv):
    if srv is None or not srv.logpath.exists():
        return []
    return [l.strip()[:300] for l in srv.logpath.read_text(errors="replace").splitlines()
            if any(k in l for k in SRV_ERR)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", choices=["4BI", "32BI", "32BT"], required=True)
    ap.add_argument("--plan", choices=["bridge", "instruct", "thinking", "smoke", "mv"], required=True)
    ap.add_argument("--deadline", default="2026-11-06T09:00")
    ap.add_argument("--limit", type=int, default=0, help="smoke: first K requests of the plan only")
    a = ap.parse_args()
    deadline = datetime.fromisoformat(a.deadline)
    OUT.mkdir(parents=True, exist_ok=True)
    items = {it["item_id"]: it for it in B.build_items()}
    order = B.fixed_order(list(items.values()))
    reqs = plan(a.plan, order)
    if a.limit:
        reqs = reqs[:a.limit]
    rows_path = OUT / (f"b1_rows_{a.model}.jsonl.gz" if not (a.limit or a.plan in ("smoke", "mv")) else f"b1_{a.plan}_{a.model}.jsonl.gz")
    if datetime.now() >= deadline:
        X.log(f"B1 {a.model} {a.plan}: past the deadline {deadline}; nothing started")
        return
    if gpu_pids():
        raise SystemExit(f"GPU 2 not idle before server start: {gpu_pids()} — STOP")
    snap = Path.home() / f".cache/huggingface/hub/models--{X.REPO[a.model][0].replace('/', '--')}/snapshots/{X.REPO[a.model][1]}"
    if not snap.exists():
        raise SystemExit(f"B1 {a.model}: pinned snapshot missing ({snap}) — STOP this arm")
    srv = X.Server(a.model, FLAGS)
    try:
        info = srv.start()
        log = srv.logpath.read_text(errors="replace")
        lim_ok = ("'image': 37" in log) or ('"image": 37' in log) or ("image': 37" in log)
        import torch
        import vllm
        import av
        import PIL
        m = X.meta_load()
        m.setdefault("runs", []).append(dict(model=a.model, plan=a.plan, started=datetime.now().isoformat(),
                                             server=info, flags=FLAGS, gen=GEN["thinking" if a.model == "32BT" else "instruct"],
                                             concurrency=CONC, limit_mm_37_in_log=lim_ok, vllm=vllm.__version__,
                                             torch=torch.__version__, pyav=av.__version__,
                                             libavcodec=list(av.library_versions.get("libavcodec", ())),
                                             libavformat=list(av.library_versions.get("libavformat", ())),
                                             pil=PIL.__version__, n_planned=len(reqs), deadline=a.deadline,
                                             ovo_constant_sha256=B.OVO_CONSTANT_SHA256))
        X.meta_save(m)
        if not lim_ok:
            X.log(f"B1 {a.model}: image-37 limit not found in server log text; relying on the first 37-image request check")
        state = asyncio.run(run(a, reqs, items, rows_path, srv, deadline))
    finally:
        srv.stop()
    rows = read_rows(rows_path)
    keys = {(r["tag"], r["item_id"], r["input"]) for r in rows}
    ok = {(r["tag"], r["item_id"], r["input"]) for r in rows if not r["error"]}
    failed = len(keys - ok)
    m = X.meta_load()
    from _provenance import stamp
    m["runs"][-1].update(ended=datetime.now().isoformat(), stopped_at_deadline=state["stopped_at"],
                         rows=len(rows), ok=len(ok), still_failed=failed, error_rows=sum(bool(r["error"]) for r in rows),
                         first_history_ok=state["first_history_ok"])
    m.setdefault("_provenance", []).append(stamp(script="b1_infer_vllm.py", model=a.model, device=f"{X.DEV}_gpu2",
                                                 n=len(ok), args=a))
    X.meta_save(m)
    X.log(f"B1 {a.model} {a.plan}: {len(ok)} ok, {failed} still failed, deadline stop {state['stopped_at']}")
    if keys and failed > 0.01 * len(keys):
        raise SystemExit(f"B1 {a.model}: {failed} still failed > 1 % — STOP this arm")


if __name__ == "__main__":
    main()
