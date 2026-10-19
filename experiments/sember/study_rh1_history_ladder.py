#!/usr/bin/env python3
"""StudyRH1 — 32B-Instruct accuracy vs history size, plus FP8 KV parity, on S-EMBER under vLLM (vLLM venv).

R1's server, settings and request code are reused unchanged (study_r1_vllm: vLLM 0.31.0, 32B-I @0cfaf481, prefix
caching OFF, FA3, CUDA graphs, gmu 0.90, max_model_len 32768, the R1 video-input flags; greedy, max_tokens 512,
seed 42, closed loop at concurrency 8, R1's answer parsing).
Cells (845 questions each, R1 order):
  H1a  RICH_HALF     R1's RICH frames uniformly subsampled to 50% (study_rh1_inputs.py), bf16 KV
  H1b  RICH_QUARTER  ... to 25%, bf16 KV
  H1c  RICH          R1's full RICH input (identical to K1), --kv-cache-dtype fp8
Stages (in order; the chain runs bf16 then fp8):
  parity   10 questions per construction on this server, max_tokens 1, return_token_ids: prompt ids vs the builder's
           expected ids (exact). For RICH on the FP8 server the gate also requires prompt_tokens == R1's logged K1
           prompt_tokens for the same questions. H1c's gate failing is a pre-registered STOP.
  timing   5 questions per cell, sequential -> runtime estimate (STOP if the estimate for all cells exceeds 4 h).
  H1a / H1b / H1c   batched cells.
"""
import argparse
import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cost"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
import study_r1_vllm as R  # noqa: E402
import study_x_vllm as X  # noqa: E402
from rawio import read_jsonl  # noqa: E402

OUT = Path("results/sember/study_rh1")
H1_MANIFEST = OUT / "study_rh1_inputs_manifest.jsonl"
H1_INP = Path.home() / ".cache/fm-switching/rh1_inputs"
R1_REQ = Path("results/sember/study_r1/study_r1_requests_h100nvl.jsonl")
GREEDY = dict(temperature=0.0, max_tokens=512)
CELLS = {"H1a": ("32BI", "RICH_HALF", GREEDY), "H1b": ("32BI", "RICH_QUARTER", GREEDY),
         "H1c": ("32BI", "RICH", GREEDY)}
CONS_DIR = {"RICH_HALF": "HALF", "RICH_QUARTER": "QUARTER"}
KV = {"bf16": [], "fp8": ["--kv-cache-dtype", "fp8"]}
BUDGET_S = 4 * 3600

# R1 module state redirected to H1 outputs (R1's own files are never written)
R.OUT = OUT
R.REQ = OUT / f"study_rh1_requests_{X.DEV}.jsonl"
R.META = X.META_PATH = OUT / f"study_rh1_run_meta_{X.DEV}.json"
X.CURRENT = Path("logs/study_rh1_current.json")
R.CELLS = CELLS


def manifest():
    rows = {}
    for r in read_jsonl(R.MANIFEST):
        if r["construction"] == "RICH":
            rows[(r["question_id"], "RICH")] = r
    for r in read_jsonl(H1_MANIFEST):
        rows[(r["question_id"], "RICH_" + r["construction"])] = dict(r, construction="RICH_" + r["construction"])
    order = sorted({(r["video_id"], r["question_id"]) for r in rows.values()})
    return rows, [q for _, q in order]


_r1_body = R.body


def body(row, cell, model, params, max_tokens=None, stream=True, token_ids=False):
    """R1's body for RICH; for the subsets, R1's RICH frames indexed by the builder's `keep`."""
    if row["construction"] == "RICH":
        return _r1_body(row, cell, model, params, max_tokens, stream, token_ids)
    z1 = np.load(R.INP / "RICH" / f"{row['question_id']}.npz")
    zs = np.load(H1_INP / CONS_DIR[row["construction"]] / f"{row['question_id']}.npz")
    fr, fidx = z1["frames"][zs["keep"]], [int(i) for i in zs["frames_indices"]]
    url = "data:video/jpeg;base64," + ",".join(R.png_b64(f) for f in fr)
    p = dict(params)
    if max_tokens is not None:
        p["max_tokens"] = max_tokens
    b = dict(model=model, stream=stream, seed=R.SEED,
             messages=[{"role": "user", "content": [{"type": "video_url", "video_url": {"url": url}},
                                                     {"type": "text", "text": row["text"]}]}],
             media_io_kwargs={"video": dict(num_frames=-1, fps=1.0, frames_indices=fidx, do_sample_frames=False,
                                            total_num_frames=max(row["total_num_frames"], len(fidx)))},
             **p)
    if stream:
        b["stream_options"] = {"include_usage": True}
    if token_ids:
        b["return_token_ids"] = True
    return b, zs["ids_instruct"], len(fr)


R.body = body


async def parity(rows, order, constructions, kv):
    r1 = {r["question_id"]: r["prompt_tokens"] for r in read_jsonl(R1_REQ) if r["cell"] == "K1"
          and r["mode"] == "batched" and not r["error"]}
    out = []
    async with httpx.AsyncClient(timeout=None) as c:
        for cons in constructions:
            for q in order[:10]:
                row = rows[(q, cons)]
                b, expect, nfr = body(row, "parity", "32BI", dict(temperature=0.0), max_tokens=1, stream=False,
                                      token_ids=True)
                r = (await c.post(f"{X.BASE}/v1/chat/completions", json=b)).json()
                if "error" in r or "usage" not in r:
                    out.append(dict(question_id=q, construction=cons, kv=kv, error=str(r)[:500]))
                    continue
                ids = r.get("prompt_token_ids")
                pt = r["usage"]["prompt_tokens"]
                o = dict(question_id=q, construction=cons, kv=kv, vllm_prompt_tokens=pt,
                         expected_prompt_tokens=int(len(expect)), frames_sent=nfr, n_frames=row["n_frames"],
                         ids_exact_match_builder=(ids == expect.tolist()) if ids is not None else None)
                if cons == "RICH":
                    o["r1_k1_prompt_tokens"] = r1.get(q)
                out.append(o)
                X.log(f"parity {kv} {cons} {q[:10]} vllm {pt} expected {len(expect)} ids_exact "
                      f"{o['ids_exact_match_builder']}" + (f" R1-K1 {o['r1_k1_prompt_tokens']}" if cons == "RICH"
                                                            else ""))
    ok = all("error" not in o and o["ids_exact_match_builder"] and o["vllm_prompt_tokens"] == o["expected_prompt_tokens"]
             and (o["construction"] != "RICH" or o["vllm_prompt_tokens"] == o["r1_k1_prompt_tokens"]) for o in out)
    res = dict(at=datetime.now().isoformat(), kv=kv, gate_passed=ok, n=len(out), rows=out)
    (OUT / f"study_rh1_parity_{kv}_{X.DEV}.json").write_text(json.dumps(res, indent=1))
    X.log(f"PARITY GATE ({kv}: {','.join(constructions)}) {'PASSED' if ok else 'FAILED'}")
    return ok


async def timing(rows, order, cells):
    res = {}
    for cell in cells:
        d = await R.run_cell(cell, rows, order, "timing5", limit=5, conc=1)
        recs = [r for r in read_jsonl(R.REQ) if r["cell"] == cell and r["mode"] == "timing5"]
        res[cell] = dict(wall_s=round(d, 1), latency_s=[r["latency_s"] for r in recs],
                         prompt_tokens=[r["prompt_tokens"] for r in recs])
        X.log(f"timing {cell}: {res[cell]}")
    m = X.meta_load()
    m.setdefault("timing5", {}).update(res)
    X.meta_save(m)
    return res


def estimate(timing5):
    """All-cell runtime estimate: 845 x per-request sequential latency / R1's measured batched speed-up."""
    r1m = json.loads(Path("results/sember/study_r1/study_r1_run_meta_h100nvl.json").read_text())
    seq = float(np.mean(r1m["timing5"]["K1"]["latency_s"]))
    k1_batched = 34.3 * 60      # R1 K1 batched: 845 requests in 34.3 min at concurrency 8 (logs/queue4_r1_I.log)
    speedup = 845 * seq / k1_batched
    per = {c: 845 * float(np.mean(t["latency_s"])) / speedup for c, t in timing5.items()}
    if "H1c" not in per:
        per["H1c"] = k1_batched           # same input as K1; fp8 timing replaces this when measured
    tot = sum(per.values()) + 2 * 300    # two server starts + parity/timing
    return dict(batched_speedup_from_r1=round(speedup, 2), per_cell_s=per, total_s=tot)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kv", choices=["bf16", "fp8"], required=True)
    ap.add_argument("--stages", required=True, help="comma list: parity,timing,H1a,H1b,H1c")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    rows, order = manifest()
    assert len(order) == 845 and len(rows) == 3 * 845, (len(order), len(rows))
    cells = ["H1a", "H1b"] if args.kv == "bf16" else ["H1c"]
    cons = [CELLS[c][1] for c in cells]
    srv = X.Server("32BI", R.MM_LIMIT + KV[args.kv])
    try:
        info = srv.start()
        m = X.meta_load()
        m.setdefault("servers", []).append(dict(kv=args.kv, stages=args.stages, started=datetime.now().isoformat(),
                                                **info))
        import torch
        import vllm
        m["stack"] = dict(venv=sys.prefix, vllm=vllm.__version__, torch=torch.__version__, cuda=torch.version.cuda)
        X.meta_save(m)
        X.log(f"KV cache capacity: {info.get('kv_cache_tokens')} tokens ({args.kv})")
        for st in args.stages.split(","):
            if st == "parity":
                ok = asyncio.run(parity(rows, order, cons, args.kv))
                if not ok and args.kv == "fp8":
                    raise SystemExit("H1c PARITY GATE FAILED — STOP (see study_rh1_parity_fp8_h100nvl.json)")
                if not ok:
                    raise SystemExit("H1a/H1b parity failed — stopping this server (see parity json)")
            elif st == "timing":
                t5 = asyncio.run(timing(rows, order, cells))
                est = estimate({**X.meta_load().get("timing5", {}), **t5})
                m = X.meta_load()
                m.setdefault("estimate", {})[args.kv] = est
                X.meta_save(m)
                X.log(f"RUNTIME ESTIMATE (all H1 cells): {est['total_s'] / 3600:.2f} h {est}")
                if est["total_s"] > BUDGET_S:
                    raise SystemExit(f"H1 estimate {est['total_s'] / 3600:.2f} h > 4 h — STOP")
            elif st in CELLS:
                asyncio.run(R.run_cell(st, rows, order, "batched"))
            else:
                raise SystemExit(f"unknown stage {st}")
    finally:
        srv.stop()
    from _provenance import stamp  # noqa: E402
    m = X.meta_load()
    m.setdefault("_provenance", []).append(stamp(script="study_rh1_history_ladder.py", model="qwen3vl-32b-instruct",
                                                 device=X.DEV, args=args))
    X.meta_save(m)


if __name__ == "__main__":
    main()
