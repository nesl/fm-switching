#!/usr/bin/env python3
"""StudyRH4 — fixed-stride (append-only) separate-image histories: warmability check + accuracy (vLLM venv).
Pre-registered in research/EXPERIMENTS.md (StudyRH4). Inputs: study_rh4_inputs.py.

PART 0 (--stage part0): RH3's image server with prefix caching ON (+ --enable-prompt-tokens-details). For the first 5
questions in R1 order with qt > 300 s whose D2 prompt fits the context: D2 history up to t = qt - 30 s (FIRST), then up
to qt (SECOND; same text; the 15 new frames appended after the unchanged prefix). PASS iff SECOND's cached_tokens >=
0.95 x FIRST's prompt_tokens on all 5. Failing it is a STOP (the format would not be warmable).

CELLS (--stage parity,timing,D1,D2): RH3's image server and R1's request settings/code (prefix caching OFF; 32B-I
@0cfaf481, greedy, max_tokens 512, seed 42, concurrency 8, R1 parsing, 845 questions in R1 order). Over-context
questions are sent as built and their HTTP 400 is recorded (never truncated).
  parity  5 questions per cell (first 5 in R1 order that fit), max_tokens 1: vLLM prompt_tokens == HF count (STOP).
  timing  5 questions per cell sequentially -> estimate (R1's batched speed-up). STOP if > 3 h.
"""
import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cost"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
import study_r1_vllm as R  # noqa: E402
import study_rh3_warmable as W3  # noqa: E402  (RH3 image server flags, img_url, timing/estimate helpers)
import study_rh4_inputs as B  # noqa: E402
import study_x_vllm as X  # noqa: E402
from rawio import read_jsonl  # noqa: E402

OUT = Path("results/sember/study_rh4")
GREEDY = dict(temperature=0.0, max_tokens=512)
CELLS = {c: ("32BI", c, GREEDY) for c in B.SIZES}
IMAGE_FLAGS = W3.IMAGE_FLAGS
PART0_FLAGS = IMAGE_FLAGS + ["--enable-prefix-caching", "--enable-prompt-tokens-details"]
BUDGET_S = 3 * 3600
PART0_MIN_FRAC = 0.95

R.OUT = OUT
R.REQ = OUT / f"study_rh4_requests_{X.DEV}.jsonl"
R.META = X.META_PATH = OUT / f"study_rh4_run_meta_{X.DEV}.json"
X.CURRENT = Path("logs/study_rh4_current.json")
R.CELLS = CELLS


def manifest():
    rows = {}
    for r in read_jsonl(B.MANIFEST):
        rows[(r["question_id"], r["cell"])] = dict(r, construction=r["cell"], n_frames=r["n_images"])
    order = sorted({(r["video_id"], r["question_id"]) for r in rows.values()})
    return rows, [q for _, q in order]


def content(cell, video_id, t_now, text):
    c = [{"type": "text", "text": B.HEADERS[cell]}]
    c += [{"type": "image_url", "image_url": {"url": W3.img_url(p, hw)}} for _, p, hw in B.select(cell, video_id, t_now)]
    return c + [{"type": "text", "text": text}]


def body(row, cell, model, params, max_tokens=None, stream=True, token_ids=False):
    p = dict(params)
    if max_tokens is not None:
        p["max_tokens"] = max_tokens
    b = dict(model=model, stream=stream, seed=R.SEED, **p,
             messages=[{"role": "user", "content": content(row["cell"], row["video_id"],
                                                           float(row["question_time"]), row["text"])}])
    if stream:
        b["stream_options"] = {"include_usage": True}
    return b, None, row["n_images"]


R.body = body


async def parity(rows, order):
    out = []
    async with httpx.AsyncClient(timeout=None) as c:
        for cell in CELLS:
            for q in [q for q in order if not rows[(q, cell)]["over_context"]][:5]:
                row = rows[(q, cell)]
                b, _, n = await asyncio.to_thread(body, row, "parity", "32BI", dict(temperature=0.0), 1, False)
                r = (await c.post(f"{X.BASE}/v1/chat/completions", json=b)).json()
                if "usage" not in r:
                    out.append(dict(question_id=q, cell=cell, error=str(r)[:500]))
                    continue
                pt = r["usage"]["prompt_tokens"]
                out.append(dict(question_id=q, cell=cell, n_images=n, vllm_prompt_tokens=pt,
                                hf_expected_prompt_tokens=row["n_input_instruct"], match=pt == row["n_input_instruct"]))
                X.log(f"parity {cell} {q[:10]} images {n} vllm {pt} hf {row['n_input_instruct']}")
    ok = all(o.get("match") for o in out)
    (OUT / f"study_rh4_parity_{X.DEV}.json").write_text(json.dumps(dict(at=datetime.now().isoformat(),
                                                                         gate_passed=ok, n=len(out), rows=out), indent=1))
    X.log(f"PARITY GATE (D1,D2) {'PASSED' if ok else 'FAILED'}")
    return ok


async def timing(rows, order):
    res = {}
    for cell in CELLS:
        d = await R.run_cell(cell, rows, order, "timing5", limit=5, conc=1)
        recs = [r for r in read_jsonl(R.REQ) if r["cell"] == cell and r["mode"] == "timing5"]
        res[cell] = dict(wall_s=round(d, 1), latency_s=[r["latency_s"] for r in recs],
                         prompt_tokens=[r["prompt_tokens"] for r in recs])
        X.log(f"timing {cell}: {res[cell]}")
    return res


async def part0(rows, order):
    pick = [q for q in order if float(rows[(q, "D2")]["question_time"]) > 300 and not rows[(q, "D2")]["over_context"]][:5]
    out = []
    async with httpx.AsyncClient(timeout=None) as c:
        async def post(row, t_now):
            b = dict(model="32BI", stream=False, seed=R.SEED, temperature=0.0, max_tokens=1,
                     messages=[{"role": "user", "content": await asyncio.to_thread(
                         content, "D2", row["video_id"], t_now, row["text"])}])
            j = (await c.post(f"{X.BASE}/v1/chat/completions", json=b)).json()
            if "usage" not in j:
                return dict(error=str(j)[:400])
            u = j["usage"]
            return dict(prompt_tokens=u["prompt_tokens"],
                        cached_tokens=(u.get("prompt_tokens_details") or {}).get("cached_tokens") or 0)
        for q in pick:
            row = rows[(q, "D2")]
            qt = float(row["question_time"])
            first, second = await post(row, qt - 30), await post(row, qt)
            frac = second.get("cached_tokens", 0) / first["prompt_tokens"] if "prompt_tokens" in first else None
            o = dict(question_id=q, video_id=row["video_id"], qt=qt, t_first=qt - 30,
                     frames_first=len(B.select("D2", row["video_id"], qt - 30)), frames_second=row["n_images"],
                     first=first, second=second, cached_over_first_prompt=frac,
                     passed=frac is not None and frac >= PART0_MIN_FRAC)
            out.append(o)
            X.log(f"part0 {q[:10]} qt {qt}: first {first} second {second} frac {frac}")
    ok = len(out) == 5 and all(o["passed"] for o in out)
    (OUT / f"study_rh4_part0_{X.DEV}.json").write_text(json.dumps(dict(at=datetime.now().isoformat(), passed=ok,
                                                                        threshold=PART0_MIN_FRAC, rows=out), indent=1))
    X.log(f"PART 0 {'PASSED' if ok else 'FAILED'}")
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True, help="part0 | comma list of parity,timing,D1,D2")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    stages = args.stage.split(",")
    rows, order = manifest()
    assert len(order) == 845 and len(rows) == 2 * 845, (len(order), len(rows))
    srv = X.Server("32BI", PART0_FLAGS if stages == ["part0"] else IMAGE_FLAGS)
    try:
        info = srv.start()
        info["prefix_caching"] = stages == ["part0"]
        m = X.meta_load()
        m.setdefault("servers", []).append(dict(stages=args.stage, started=datetime.now().isoformat(), **info))
        import torch
        import vllm
        m["stack"] = dict(venv=sys.prefix, vllm=vllm.__version__, torch=torch.__version__, cuda=torch.version.cuda)
        X.meta_save(m)
        X.log(f"KV cache capacity: {info.get('kv_cache_tokens')} tokens")
        if stages == ["part0"]:
            if not asyncio.run(part0(rows, order)):
                raise SystemExit("RH4 PART 0 FAILED — STOP (see study_rh4_part0_h100nvl.json)")
        else:
            for st in stages:
                if st == "parity":
                    if not asyncio.run(parity(rows, order)):
                        raise SystemExit("RH4 PARITY GATE FAILED — STOP")
                elif st == "timing":
                    t5 = asyncio.run(timing(rows, order))
                    est = W3.estimate(t5)
                    m = X.meta_load()
                    m["timing5"], m["estimate"] = t5, est
                    X.meta_save(m)
                    X.log(f"RUNTIME ESTIMATE (D1+D2): {est['total_s'] / 3600:.2f} h {est}")
                    if est["total_s"] > BUDGET_S:
                        raise SystemExit(f"RH4 estimate {est['total_s'] / 3600:.2f} h > 3 h — STOP")
                elif st in CELLS:
                    asyncio.run(R.run_cell(st, rows, order, "batched"))
                else:
                    raise SystemExit(f"unknown stage {st}")
    finally:
        srv.stop()
    from _provenance import stamp  # noqa: E402
    m = X.meta_load()
    m.setdefault("_provenance", []).append(stamp(script="study_rh4_fixed_stride.py", model="qwen3vl-32b-instruct",
                                                 device=X.DEV, args=args))
    X.meta_save(m)


if __name__ == "__main__":
    main()
