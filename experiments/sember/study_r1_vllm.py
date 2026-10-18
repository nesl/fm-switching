#!/usr/bin/env python3
"""StudyR1 — Qwen3-VL-32B on S-EMBER under vLLM (vLLM venv). Accuracy (batched) + clean single-request latency.

Inputs come from study_r1_inputs.py (StudyO's exact preprocessing; final-size uint8 frames + expected prompt ids).
Each request sends its frames as ONE video (`data:video/jpeg;base64,<png>,<png>,...` — PIL decodes PNG regardless of
the declared type, so frames arrive losslessly) with per-request media_io_kwargs carrying StudyO's VideoMetadata
(fps 1.0, frames_indices = round(t), total_num_frames = round(qt), do_sample_frames False) and num_frames = -1
(vLLM's video/jpeg loader otherwise keeps only the first 32 frames).

Server: StudyX's (vLLM 0.31.0, FA3, CUDA graphs, gmu 0.90, max_model_len 32768, prefix caching OFF, PyTorch-native
sampler) + --limit-mm-per-prompt {"image": 0, "video": 1}.

Stages (run in order by the chain):
  parity     10 RICH + 10 RECENT on 32B-I, max_tokens 1, return_token_ids: compare prompt ids with the builder's
             expected ids (exact) and prompt_tokens / n_frames with StudyO's logged n_input / n_frames (gate: <= 2%).
  timing     5 questions per cell, sequential -> runtime estimate.
  K1 / K3    32B-I x RICH / RECENT, greedy, max_tokens 512, closed loop at concurrency CONC.
  lat        first 50 questions of K1 and K3, ONE request at a time (request body built before the clock starts).
  K2         32B-T x RICH, model-card VL sampling, max_tokens 16384, seed 42 for every request, full text stored.
"""
import argparse
import asyncio
import base64
import io
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cost"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
import study_x_vllm as X  # noqa: E402

INP = Path.home() / ".cache/fm-switching/r1_inputs"
OUT = Path("results/sember/study_r1")
MANIFEST = OUT / "study_r1_inputs_manifest.jsonl"
REQ = OUT / f"study_r1_requests_{X.DEV}.jsonl"
META = OUT / f"study_r1_run_meta_{X.DEV}.json"
STUDYO = Path("results/sember/study_o/study_o_q4_trials_fa2.jsonl")
X.META_PATH = META
X.CURRENT = Path("logs/study_r1_current.json")
# StudyO processor kwargs (fps 1.0, do_sample_frames False) set ENGINE-level: vLLM 0.31 rejects per-request
# mm_processor_kwargs unless --trust-request-mm-kwargs (first parity attempt 12:35: all 20 requests HTTP 400).
MM_LIMIT = ["--limit-mm-per-prompt", json.dumps({"image": 0, "video": 1}),
            "--mm-processor-kwargs", json.dumps({"fps": 1.0, "do_sample_frames": False}),
            # per-request media_io_kwargs (StudyO's frames_indices / total_num_frames differ per question) need
            # --trust-request-mm-kwargs (second attempt 12:38: all HTTP 400). The server is bound to localhost so
            # only this client can reach it.
            "--trust-request-mm-kwargs", "--host", "127.0.0.1"]
CONC = 8
CARD_VL = dict(top_p=0.95, top_k=20, repetition_penalty=1.0, presence_penalty=0.0, temperature=1.0)
CELLS = {"K1": ("32BI", "RICH", dict(temperature=0.0, max_tokens=512)),
         "K3": ("32BI", "RECENT", dict(temperature=0.0, max_tokens=512)),
         "K2": ("32BT", "RICH", dict(CARD_VL, min_p=0.0, max_tokens=16384))}
SEED = 42
LETTER = re.compile(r"\b([A-E])\b")
END = "</think>"


def manifest():
    rows = {}
    for r in map(json.loads, open(MANIFEST)):
        rows[(r["question_id"], r["construction"])] = r
    order = sorted({(r["video_id"], r["question_id"]) for r in rows.values()})
    return rows, [q for _, q in order]


def png_b64(fr):
    buf = io.BytesIO()
    Image.fromarray(np.ascontiguousarray(fr.transpose(1, 2, 0))).save(buf, format="PNG", compress_level=1)
    return base64.b64encode(buf.getvalue()).decode()


def body(row, cell, model, params, max_tokens=None, stream=True, token_ids=False):
    z = np.load(INP / row["construction"] / f"{row['question_id']}.npz")
    fr, fidx = z["frames"], [int(i) for i in z["frames_indices"]]
    url = "data:video/jpeg;base64," + ",".join(png_b64(f) for f in fr)
    p = dict(params)
    if max_tokens is not None:
        p["max_tokens"] = max_tokens
    b = dict(model=model, stream=stream, seed=SEED,
             messages=[{"role": "user", "content": [{"type": "video_url", "video_url": {"url": url}},
                                                     {"type": "text", "text": row["text"]}]}],
             media_io_kwargs={"video": dict(num_frames=-1, fps=1.0, frames_indices=fidx, do_sample_frames=False,
                                            total_num_frames=max(row["total_num_frames"], len(fidx)))},
             **p)
    if stream:
        b["stream_options"] = {"include_usage": True}
    if token_ids:
        b["return_token_ids"] = True
    expect = z["ids_thinking"] if model == "32BT" else z["ids_instruct"]
    return b, expect, len(fr)


def score(text, thinking):
    if thinking:
        if END in text:
            closed, ans = True, text[text.index(END) + len(END):]
        else:
            closed, ans = False, text
    else:
        closed, ans = None, text
    hits = LETTER.findall(ans[-300:])
    return closed, (hits[-1] if hits else "X")


async def send(client, b, row, cell, mode):
    t0 = time.time()
    first, chunks, usage, finish, err = None, [], None, None, None
    try:
        async with client.stream("POST", f"{X.BASE}/v1/chat/completions", json=b) as r:
            if r.status_code != 200:
                err = f"HTTP {r.status_code}: {(await r.aread())[:400]!r}"
            else:
                async for line in r.aiter_lines():
                    if not line.startswith("data: ") or line == "data: [DONE]":
                        continue
                    j = json.loads(line[6:])
                    if j.get("usage"):
                        usage = j["usage"]
                    for ch in j.get("choices", []):
                        d = ch.get("delta") or {}
                        c = d.get("content") or d.get("reasoning_content") or d.get("reasoning")
                        if c:
                            first = first or time.time()
                            chunks.append(c)
                        if ch.get("finish_reason"):
                            finish = ch["finish_reason"]
    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {e}"
    t1 = time.time()
    text = "".join(chunks)
    thinking = cell == "K2"
    closed, pred = score(text, thinking)
    correct = bool(pred == row["correct_letter"] and closed is not False)
    return dict(cell=cell, mode=mode, question_id=row["question_id"], video_id=row["video_id"],
                construction=row["construction"], question_category=row["question_category"],
                question_time=row["question_time"], evidence_covered=row["evidence_covered"],
                n_frames=row["n_frames"], prompt_tokens=usage and usage["prompt_tokens"],
                expected_prompt_tokens=row["n_input_thinking" if thinking else "n_input_instruct"],
                completion_tokens=usage and usage["completion_tokens"], finish_reason=finish,
                think_closed=closed, pred=pred, correct_letter=row["correct_letter"], correct=correct,
                ttft_s=round(first - t0, 3) if first else None, latency_s=round(t1 - t0, 3),
                seed=SEED, params={k: v for k, v in b.items() if k in ("temperature", "top_p", "top_k", "min_p",
                                                                          "presence_penalty", "repetition_penalty",
                                                                          "max_tokens")},
                text=text, error=err, at=datetime.now().isoformat())


def append(rec):
    with open(REQ, "a") as f:
        f.write(json.dumps(rec) + "\n")


def done(cell, mode):
    if not REQ.exists():
        return set()
    return {r["question_id"] for r in map(json.loads, open(REQ)) if r["cell"] == cell and r["mode"] == mode
            and not r["error"]}


async def parity(rows, order):
    T = {(t["question_id"], t["state_arm"]): t for t in map(json.loads, open(STUDYO))}
    out = []
    async with httpx.AsyncClient(timeout=None) as c:
        for cons in ("RICH", "RECENT"):
            for q in order[:10]:
                row = rows[(q, cons)]
                b, expect, nfr = body(row, "parity", "32BI", dict(temperature=0.0), max_tokens=1, stream=False,
                                      token_ids=True)
                r = (await c.post(f"{X.BASE}/v1/chat/completions", json=b)).json()
                if "error" in r or "usage" not in r:
                    out.append(dict(question_id=q, construction=cons, error=str(r)[:500]))
                    continue
                ids = r.get("prompt_token_ids")
                so = T[(q, cons)]
                pt = r["usage"]["prompt_tokens"]
                out.append(dict(question_id=q, construction=cons, studyo_model_arm=so["model_arm"],
                                vllm_prompt_tokens=pt, studyo_n_input=so["n_input"],
                                rel_diff=round((pt - so["n_input"]) / so["n_input"], 5),
                                frames_sent=nfr, n_frames=row["n_frames"], studyo_n_frames=so["n_frames"],
                                ids_returned=ids is not None,
                                ids_exact_match_builder=(ids == expect.tolist()) if ids is not None else None))
                X.log(f"parity {cons} {q[:10]} vllm {pt} studyo {so['n_input']} frames {row['n_frames']}/"
                      f"{so['n_frames']} ids_exact {out[-1]['ids_exact_match_builder']}")
    ok = all("error" not in o and abs(o["rel_diff"]) <= 0.02 and o["n_frames"] == o["studyo_n_frames"] for o in out)
    res = dict(at=datetime.now().isoformat(), gate_passed=ok, n=len(out), rows=out)
    (OUT / f"study_r1_parity_{X.DEV}.json").write_text(json.dumps(res, indent=1))
    X.log(f"PARITY GATE {'PASSED' if ok else 'FAILED'}")
    return ok


async def run_cell(cell, rows, order, mode, limit=None, conc=CONC):
    model, cons, params = CELLS[cell]
    have = done(cell, mode)
    qs = [q for q in (order[:limit] if limit else order) if q not in have]
    X.log(f"{cell}/{mode}: {len(qs)} to run (concurrency {conc})")
    t0 = time.time()
    n = 0
    async with httpx.AsyncClient(timeout=None) as c:
        if conc == 1:
            for q in qs:
                b, _, _ = body(rows[(q, cons)], cell, model, params)   # built before the clock starts
                X.CURRENT.write_text(json.dumps(dict(cell=cell, mode=mode, q=q)))
                rec = await send(c, b, rows[(q, cons)], cell, mode)
                append(rec)
                n += 1
        else:
            sem = asyncio.Semaphore(conc)

            async def one(q):
                nonlocal n
                async with sem:
                    b, _, _ = await asyncio.to_thread(body, rows[(q, cons)], cell, model, params)
                    X.CURRENT.write_text(json.dumps(dict(cell=cell, mode=mode, q=q)))
                    rec = await send(c, b, rows[(q, cons)], cell, mode)
                    append(rec)
                    n += 1
                    if n % 50 == 0:
                        X.log(f"{cell}/{mode}: {n}/{len(qs)} in {(time.time() - t0) / 60:.1f} min")
            await asyncio.gather(*(one(q) for q in qs))
    dur = time.time() - t0
    X.log(f"{cell}/{mode}: done {n} in {dur / 60:.1f} min")
    return dur


async def timing(rows, order, model):
    res = {}
    for cell, (m, _, _) in CELLS.items():
        if m != model:
            continue
        d = await run_cell(cell, rows, order, "timing5", limit=5, conc=1)
        recs = [r for r in map(json.loads, open(REQ)) if r["cell"] == cell and r["mode"] == "timing5"]
        res[cell] = dict(wall_s=round(d, 1), latency_s=[r["latency_s"] for r in recs],
                         completion_tokens=[r["completion_tokens"] for r in recs],
                         prompt_tokens=[r["prompt_tokens"] for r in recs],
                         prompt_ids_expected=[r["expected_prompt_tokens"] for r in recs])
        X.log(f"timing {cell}: {res[cell]}")
    m = X.meta_load()
    m.setdefault("timing5", {}).update(res)
    X.meta_save(m)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", choices=["32BI", "32BT"], required=True)
    ap.add_argument("--stages", required=True, help="comma list: parity,timing,K1,K3,lat,K2")
    ap.add_argument("--partial", action="store_true", help="allow an incomplete manifest (parity/timing only)")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    rows, order = manifest()
    assert args.partial or len(order) == 845, len(order)
    srv = X.Server(args.model, MM_LIMIT)
    try:
        info = srv.start()
        m = X.meta_load()
        m.setdefault("servers", []).append(dict(stages=args.stages, started=datetime.now().isoformat(), **info))
        import torch
        import vllm
        m["stack"] = dict(venv=sys.prefix, vllm=vllm.__version__, torch=torch.__version__, cuda=torch.version.cuda)
        X.meta_save(m)
        for st in args.stages.split(","):
            if st == "parity":
                if not asyncio.run(parity(rows, order)):
                    raise SystemExit("PARITY GATE FAILED — stopping (see study_r1_parity_h100nvl.json)")
            elif st == "timing":
                asyncio.run(timing(rows, order, args.model))
            elif st in ("K1", "K3", "K2"):
                asyncio.run(run_cell(st, rows, order, "batched"))
            elif st == "lat":
                for cell in ("K1", "K3"):
                    asyncio.run(run_cell(cell, rows, order, "single", limit=50, conc=1))
            else:
                raise SystemExit(f"unknown stage {st}")
    finally:
        srv.stop()
    from _provenance import stamp  # noqa: E402
    m = X.meta_load()
    m.setdefault("_provenance", []).append(stamp(script="study_r1_vllm.py", model=args.model, device=X.DEV,
                                                 args=args))
    X.meta_save(m)


if __name__ == "__main__":
    main()
