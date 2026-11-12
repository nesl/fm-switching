#!/usr/bin/env python3
"""StudyD14b-dense inference (vLLM venv; h100nvl GPU 2). SCORES ONLY — batched; no latency is measured.

StudyD14's request form and stack, reused unchanged through d3_infer_vllm (body, send with 2 transport retries, grey,
prompt trace, server-error check): vLLM 0.31.0, prefix caching off, --mm-processor-cache-gb 0, images <= 9, pinned
4BI @ebb281ec / 32BI @0cfaf481, greedy, max_tokens 8, logprobs top 20, seed 0, concurrency 8.
Per arm the INTEGER-t requests (byte-identical to D14's) run first; their P(Yes) must equal D14's committed value
exactly on >= 99 % (determinism control) or the run STOPs before the sub-second requests. Then the rest, then 100 grey.
STOP if > 1 % remain failed, on a server-log error, if > 1 % lack both Yes and No, or a foreign process on GPU 2.
Resumable. Usage: d14b_infer_vllm.py --model 4BI|32BI --ns 1[,3]
Rows -> results/dashcam/study_d14b/d14b_requests_h100nvl.jsonl
"""
import argparse
import asyncio
import gzip
import json
import math
import sys
from datetime import datetime
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import d3_infer_vllm as D3  # noqa: E402

X = D3.X
OUT = Path("results/dashcam/study_d14b")
D3.OUT = OUT
D3.MAN = OUT / "d14b_requests_manifest.jsonl.gz"
D3.FR = Path.home() / "data/dashcam/d14b_frames/small"
D3.REQ = OUT / "d14b_requests_h100nvl.jsonl"
D3.META = OUT / "d14b_run_meta_h100nvl.json"
X.META_PATH = D3.META
X.CURRENT = Path("logs/d14b_current.json")
D14_TRACE = Path("results/dashcam/study_d14_trace/d14_trace_h100nvl.jsonl.gz")
N_DECISIONS = 42014


def stop_checks():
    import getpass
    import subprocess
    pids = D3.gpu_pids()
    if pids:
        users = subprocess.run(["ps", "-o", "user=", "-p", ",".join(map(str, pids))], capture_output=True,
                               text=True).stdout.split()
        foreign = [u for u in users if u != getpass.getuser()]
        if foreign:
            raise SystemExit(f"foreign process on GPU 2: {pids} {users} — STOP")
    se = D3.server_errors()
    if se:
        raise SystemExit(f"server log error before requests completed — STOP: {se[0]}")


def determinism(model, n):
    d14 = {(r["model"], r["n"], r["request_id"]): r["p_yes"] for r in map(json.loads, gzip.open(D14_TRACE, "rt"))
           if r["model"] == model and r["n"] == n}
    mine = {}
    for r in map(json.loads, open(D3.REQ)):
        if r["model"] == model and r["n"] == n and not r["error"] and not r["grey"] and r.get("gt"):
            mine[r["gt"]] = r["p_yes"]   # gt carries d14_request_id
    keys = [k for k in mine if (model, n, k) in d14]
    same = sum(mine[k] == d14[(model, n, k)] for k in keys)
    return same, len(keys)


async def run(model, ns, allreqs):
    have = set()
    if D3.REQ.exists():
        have = {(r["model"], r["n"], r["request_id"]) for r in map(json.loads, open(D3.REQ)) if not r["error"]}
    sem = asyncio.Semaphore(D3.CONC)
    g = D3.grey_png()
    m = X.meta_load()
    async with httpx.AsyncClient(timeout=None) as c:
        for n in ns:
            reqs = [r for r in allreqs if r["n"] == n]
            if f"N{n}" not in m.get("prompt_trace", {}):
                await D3.trace(model, reqs, n)
                m = X.meta_load()
            ints = [q for q in reqs if q["d14_request_id"] and (model, n, q["request_id"]) not in have]
            rest = [q for q in reqs if not q["d14_request_id"] and (model, n, q["request_id"]) not in have]
            for phase, todo in (("integer-t", ints), ("sub-second", rest)):
                X.log(f"D14b {model} N{n} {phase}: {len(todo)} to run")
                for i in range(0, len(todo), 400):
                    await asyncio.gather(*(D3.send(c, q, model, n, sem) for q in todo[i:i + 400]))
                    X.log(f"D14b {model} N{n} {phase}: {min(i + 400, len(todo))}/{len(todo)}")
                    stop_checks()
                if phase == "integer-t":
                    same, tot = determinism(model, n)
                    m = X.meta_load()
                    m.setdefault("determinism", {})[f"{model}_N{n}"] = dict(identical=same, compared=tot)
                    X.meta_save(m)
                    X.log(f"D14b {model} N{n} determinism: {same}/{tot} identical to D14")
                    if tot == 0 or same < 0.99 * tot:
                        raise SystemExit(f"D14b {model} N{n}: determinism {same}/{tot} < 99 % — STOP")
            gt = [k for k in range(D3.N_GREY) if (model, n, f"GREY_N{n}_{k:03d}") not in have]
            await asyncio.gather(*(D3.send(c, reqs[0], model, n, sem, grey=g, rep=k) for k in gt))
            stop_checks()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", choices=["4BI", "32BI"], required=True)
    ap.add_argument("--ns", required=True)
    a = ap.parse_args()
    ns = [int(x) for x in a.ns.split(",")]
    reqs = [json.loads(l) for l in gzip.open(D3.MAN, "rt")]
    assert len(reqs) == 2 * N_DECISIONS and all(r["last_pts_le_end"] for r in reqs), len(reqs)
    for r in reqs:
        r.setdefault("offset", None)
        r.setdefault("gt", None)
    # D3's row writer does not know d14_request_id / t; stash them in the D3-only 'gt' / 'offset' fields
    for r in reqs:
        r["gt"] = r["d14_request_id"]
        r["offset"] = r["t"]
    if D3.gpu_pids():
        raise SystemExit(f"GPU 2 not idle before server start: {D3.gpu_pids()} — STOP")
    srv = X.Server(a.model, D3.FLAGS)
    D3.SRV = srv
    try:
        info = srv.start()
        import torch
        import vllm
        m = X.meta_load()
        m["stack"] = dict(venv=sys.prefix, vllm=vllm.__version__, torch=torch.__version__, gpu="h100nvl GPU 2",
                          gpu_uuid=D3.GPU_UUID, flags=D3.FLAGS, gen=D3.GEN, query=D3.QUERY, concurrency=D3.CONC,
                          prefix_caching=False, processor_cache_gb=0)
        m.setdefault("servers", []).append(dict(model=a.model, ns=ns, started=datetime.now().isoformat(), **info))
        X.meta_save(m)
        asyncio.run(run(a.model, ns, reqs))
    finally:
        srv.stop()
    allr = [json.loads(l) for l in open(D3.REQ) if f'"model": "{a.model}"' in l]
    allr = [r for r in allr if r["n"] in ns]
    keys = {(r["n"], r["request_id"]) for r in allr}
    ok = {(r["n"], r["request_id"]) for r in allr if not r["error"]}
    failed = len(keys - ok)
    rs = [r for r in allr if not r["error"]]
    nei = sum(bool(r["neither"]) for r in rs)
    err_rows = sum(1 for r in allr if r["error"])
    X.log(f"D14b {a.model} N{ns}: {len(rs)} ok rows, {err_rows} error rows (retried), {failed} still failed, neither {nei}")
    from _provenance import stamp
    m = X.meta_load()
    m.setdefault("_provenance", []).append(stamp(script="d14b_infer_vllm.py", model=a.model, device=f"{X.DEV}_gpu2",
                                                 n=len(rs), args=a))
    m.setdefault("summary", {})[f"{a.model}_N{a.ns}"] = dict(ok_rows=len(rs), error_rows=err_rows,
                                                             still_failed=failed, neither=nei)
    X.meta_save(m)
    if failed > 0.01 * len(keys):
        raise SystemExit(f"D14b {a.model}: {failed} still failed > 1 % — STOP")
    if nei > 0.01 * len(rs):
        raise SystemExit(f"D14b {a.model}: neither Yes nor No in {nei}/{len(rs)} > 1 % — STOP")
    need = len(ns) * (N_DECISIONS + D3.N_GREY)
    if len(ok) < need:
        raise SystemExit(f"D14b {a.model}: incomplete {len(ok)}/{need} — rerun to resume")


if __name__ == "__main__":
    main()
