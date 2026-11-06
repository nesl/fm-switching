#!/usr/bin/env python3
"""StudyD14-trace inference (vLLM venv; h100nvl GPU 2). ACCURACY / SCORES ONLY — batched; no latency is reported.

Exactly StudyD3's request form and stack (d3_infer_vllm, reused unchanged): D-series vLLM 0.31.0 server, prefix caching
off, --mm-processor-cache-gb 0, images <= 9; pinned 4BI @ebb281ec / 32BI @0cfaf481; greedy, max_tokens 8, logprobs
top 20, request seed 0, non-streaming, concurrency 8; one user turn = [header] + N SMALL PNGs oldest first (sha256
re-checked) + [D3's query]; grey control 100 requests per arm; prompt trace per N (no digit other than the header's,
no file name). Transport errors retried up to 2 more times (logged); STOP if > 1 % remain failed, if the server log
shows an error before the arm's requests complete, or if > 1 % lack both Yes and No. GPU 2 must be idle before the
server starts. Resumable (rows without error are skipped).
Arms: --model 4BI --ns 1,3 ; --model 32BI --ns 1,3,9 (run in that order by the queue).
Rows -> results/dashcam/study_d14_trace/d14_requests_h100nvl.jsonl (gzipped by d14_analyse.py at the end).
"""
import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import d3_infer_vllm as D3  # noqa: E402

X = D3.X
OUT = Path("results/dashcam/study_d14_trace")
D3.OUT = OUT
D3.MAN = OUT / "d14_requests_manifest.jsonl"
D3.FR = Path.home() / "data/dashcam/d14_frames/small"
D3.REQ = OUT / "d14_requests_h100nvl.jsonl"
D3.META = OUT / "d14_run_meta_h100nvl.json"
X.META_PATH = D3.META
X.CURRENT = Path("logs/d14_current.json")
N_DECISIONS = 10660


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", choices=["4BI", "32BI"], required=True)
    ap.add_argument("--ns", required=True)
    a = ap.parse_args()
    ns = [int(x) for x in a.ns.split(",")]
    reqs = [json.loads(l) for l in (open(D3.MAN) if D3.MAN.exists() else __import__("gzip").open(str(D3.MAN) + ".gz", "rt"))]
    assert len(reqs) == 3 * N_DECISIONS and all(r["last_pts_le_end"] for r in reqs), len(reqs)
    for r in reqs:  # D3's row writer reads these D3-only fields; D14 rows are joined to t / labels by request_id
        r.setdefault("offset", None)
        r.setdefault("gt", None)
    if D3.gpu_pids():
        raise SystemExit(f"GPU 2 not idle before server start: {D3.gpu_pids()} — STOP")
    srv = X.Server(a.model, D3.FLAGS)
    D3.SRV = srv
    try:
        info = srv.start()
        import torch
        import vllm
        m = X.meta_load()
        m["stack"] = dict(venv=sys.prefix, vllm=vllm.__version__, torch=torch.__version__, gpu_uuid=D3.GPU_UUID,
                          flags=D3.FLAGS, gen=D3.GEN, query=D3.QUERY, concurrency=D3.CONC)
        m.setdefault("servers", []).append(dict(model=a.model, ns=ns, started=datetime.now().isoformat(), **info))
        X.meta_save(m)
        asyncio.run(D3.run(a.model, ns, reqs))
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
    X.log(f"D14 {a.model} N{ns}: {len(rs)} ok rows, {err_rows} error rows (retried), {failed} still failed, neither {nei}")
    from _provenance import stamp
    m = X.meta_load()
    m.setdefault("_provenance", []).append(stamp(script="d14_infer_vllm.py", model=a.model, device=f"{X.DEV}_gpu2",
                                                 n=len(rs), args=a))
    m.setdefault("summary", {})[f"{a.model}_N{a.ns}"] = dict(ok_rows=len(rs), error_rows=err_rows,
                                                             still_failed=failed, neither=nei)
    X.meta_save(m)
    if failed > 0.01 * len(keys):
        raise SystemExit(f"D14 {a.model}: {failed} still failed > 1 % — STOP")
    if nei > 0.01 * len(rs):
        raise SystemExit(f"D14 {a.model}: neither Yes nor No in {nei}/{len(rs)} > 1 % — STOP")


if __name__ == "__main__":
    main()
