#!/usr/bin/env python3
"""StudyF1-shortwin inference (vLLM venv; h100nvl GPU 1). ACCURACY ONLY — batched at concurrency 8; no latency claim.

Request: one user turn = [header] + N 560x560 PNGs oldest first (sha256 re-checked against the manifest) + [R1's
question text]. Greedy, max_tokens 64, request seed 0, logprobs top 20, non-streaming. Server: study_f_common stack
(prefix + processor caches off), --limit-mm-per-prompt {"image": 9, "video": 0}.
Grey control: per model x N, 100 real questions (seed-0 sample of the 845) with every frame replaced by a uniform
RGB(128) 560x560 PNG; header and question text unchanged.
Before a model's sweep: one traced prompt per N (return_token_ids) — the decoded prompt must not contain the video id
or any frame pts; it is written to results/sember/study_f1/prompt_trace_<model>_N<n>.txt.
STOP: > 1 % of a cell's requests failed after 2 transport retries; server-log error; a foreign process on GPU 1.
Resumable: rows without error are skipped. Rows -> results/sember/study_f1/f1_requests_h100nvl.jsonl.
Usage: study_f1_infer_vllm.py --model 4BI|32BI [--ns 1,3,9]
"""
import argparse
import asyncio
import base64
import hashlib
import io
import json
import random
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import study_f_common as F  # noqa: E402

X = F.X
OUT = Path("results/sember/study_f1")
MAN = OUT / "f1_inputs_manifest.jsonl"
FR = Path.home() / ".cache/fm-switching/f1_frames"
REQ = OUT / "f1_requests_h100nvl.jsonl"
META = OUT / "f1_run_meta_h100nvl.json"
X.META_PATH = META
X.CURRENT = Path("logs/f1_current.json")
GEN = dict(temperature=0.0, max_tokens=64, seed=0, logprobs=True, top_logprobs=20)
FLAGS = ["--limit-mm-per-prompt", json.dumps({"image": 9, "video": 0}), "--mm-processor-cache-gb", "0",
         "--enable-prompt-tokens-details", "--host", "127.0.0.1"]
CONC, N_GREY = 8, 100
SRV = None


def grey_png():
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (560, 560), (128, 128, 128)).save(buf, format="PNG")
    return buf.getvalue()


GREY = None


def body(row, model, grey=False, token_ids=False):
    content = [{"type": "text", "text": row["header"]}]
    hashes = []
    for f, h in zip(row["frame_files"], row["frame_sha256"]):
        if grey:
            b = GREY
        else:
            b = (FR / f).read_bytes()
            assert hashlib.sha256(b).hexdigest() == h, (row["question_id"], f)
        hashes.append(hashlib.sha256(b).hexdigest())
        content.append({"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(b).decode()}})
    content.append({"type": "text", "text": row["text"]})
    bd = dict(model=model, messages=[{"role": "user", "content": content}], stream=False, **GEN)
    if token_ids:
        bd["return_token_ids"] = True
    return bd, hashes


async def one(c, row, model, sem, grey=False):
    async with sem:
        b, hashes = await asyncio.to_thread(body, row, model, grey)
        t0 = time.time()
        j, err, attempts, seen = await F.post(c, b)
        text, lp, u, fin = "", None, {}, None
        if not err:
            ch = j["choices"][0]
            text = ch["message"].get("content") or ""
            lp = (ch.get("logprobs") or {}).get("content")
            u = j.get("usage") or {}
            fin = ch.get("finish_reason")
        pred = F.parse_letter(text) if not err else None
        rec = dict(model=model, n=row["n"], question_id=row["question_id"], video_id=row["video_id"], grey=grey,
                   n_frames=row["n_frames"], text=text, pred=pred, correct_letter=row["correct_letter"],
                   correct=(pred == row["correct_letter"]) if pred else None, letter_probs=F.letter_probs(lp),
                   prompt_tokens=u.get("prompt_tokens"), completion_tokens=u.get("completion_tokens"),
                   cached_tokens=((u.get("prompt_tokens_details") or {}).get("cached_tokens")),
                   finish_reason=fin, frame_sha256=hashes, error=err, attempts=attempts, transport_errors=seen,
                   wall_s=round(time.time() - t0, 3), at=F.now())
        with open(REQ, "a") as f:
            f.write(json.dumps(rec) + "\n")
        return rec


async def trace(c, model, row):
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(X.snapshot(model))
    b, _ = body(row, model, token_ids=True)
    r = (await c.post(f"{X.BASE}/v1/chat/completions", json=b)).json()
    pieces, prev, k = [], None, 0
    for t in r["prompt_token_ids"]:
        s = tok.decode([t])
        if s == "<|image_pad|>" and s == prev:
            k += 1
            continue
        if prev is not None:
            pieces.append(prev if k == 1 else f"{prev}×{k}")
        prev, k = s, 1
    pieces.append(prev if k == 1 else f"{prev}×{k}")
    text = "".join(pieces)
    vid_num = row["video_id"].split("_")[0]
    rest = __import__("re").sub(r"<\|image_pad\|>×\d+", "", text).replace(row["text"], "")
    bad = [s for s in [vid_num, row["video_id"]] + [f"{p:g}" for p in row["frame_pts"] if p >= 10] if s in rest]
    pads = [int(x) for x in __import__("re").findall(r"<\|image_pad\|>×(\d+)", text)]
    n = row["n"]
    (OUT / f"prompt_trace_{model}_N{n}.txt").write_text(
        f"# StudyF1: one complete prompt as tokenised by the server (model {model}, N {n}, question {row['question_id']};"
        f" image pads collapsed)\n# prompt_tokens {r['usage']['prompt_tokens']}; image pads per frame {pads}; "
        f"forbidden strings found outside the question text: {bad}\n\n{text}")
    m = X.meta_load()
    m.setdefault("prompt_trace", {})[f"{model}_N{n}"] = dict(question_id=row["question_id"],
                                                             prompt_tokens=r["usage"]["prompt_tokens"],
                                                             image_pads_per_frame=pads, forbidden_found=bad)
    X.meta_save(m)
    if bad:
        raise SystemExit(f"N{n} prompt contains a video id / pts — STOP: {bad}")


def check_gpu():
    fo = F.foreign()
    if fo:
        raise SystemExit(f"foreign process on GPU 1 — STOP: {fo}")


async def run(model, ns, rows):
    global GREY
    GREY = grey_png()
    have = set()
    if REQ.exists():
        have = {(r["model"], r["n"], r["question_id"], r["grey"]) for r in map(json.loads, open(REQ)) if not r["error"]}
    sem = asyncio.Semaphore(CONC)
    rng = random.Random(0)
    qids = sorted({r["question_id"] for r in rows})
    grey_q = set(rng.sample(qids, N_GREY))
    m = X.meta_load()
    m["grey_questions"] = sorted(grey_q)
    X.meta_save(m)
    async with httpx.AsyncClient(timeout=None) as c:
        for n in ns:
            rs = [r for r in rows if r["n"] == n]
            if f"{model}_N{n}" not in X.meta_load().get("prompt_trace", {}):
                await trace(c, model, rs[0])
            for grey, pool in ((False, rs), (True, [r for r in rs if r["question_id"] in grey_q])):
                todo = [r for r in pool if (model, n, r["question_id"], grey) not in have]
                X.log(f"F1 {model} N{n} grey={grey}: {len(todo)} to run")
                for i in range(0, len(todo), 200):
                    check_gpu()
                    await asyncio.gather(*(one(c, r, model, sem, grey) for r in todo[i:i + 200]))
                    X.log(f"F1 {model} N{n} grey={grey}: {min(i + 200, len(todo))}/{len(todo)}  sm {F.sm_clock()}")
                    se = F.server_errors(SRV)
                    if se:
                        raise SystemExit(f"server log error — STOP: {se[0]}")


def main():
    global SRV
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", choices=["4BI", "32BI"], required=True)
    ap.add_argument("--ns", default="1,3,9")
    a = ap.parse_args()
    ns = [int(x) for x in a.ns.split(",")]
    rows = [json.loads(l) for l in open(MAN)]
    assert len(rows) == 845 * 3
    F.require_idle()
    srv = X.Server(a.model, FLAGS)
    SRV = srv
    try:
        info = srv.start()
        import torch
        import vllm
        m = X.meta_load()
        m["stack"] = dict(venv=sys.prefix, vllm=vllm.__version__, torch=torch.__version__, gpu=F.GPU_LABEL,
                          gpu_uuid=F.GPU_UUID, flags=FLAGS, gen=GEN, concurrency=CONC)
        m.setdefault("servers", []).append(dict(model=a.model, ns=ns, started=datetime.now().isoformat(), **info))
        X.meta_save(m)
        asyncio.run(run(a.model, ns, rows))
    finally:
        srv.stop()
    allr = [json.loads(l) for l in open(REQ)]
    allr = [r for r in allr if r["model"] == a.model and r["n"] in ns]
    keys = {(r["n"], r["question_id"], r["grey"]) for r in allr}
    ok = {(r["n"], r["question_id"], r["grey"]) for r in allr if not r["error"]}
    failed = len(keys - ok)
    from _provenance import stamp
    m = X.meta_load()
    m.setdefault("_provenance", []).append(stamp(script="study_f1_infer_vllm.py", model=a.model,
                                                 device="h100nvl_gpu1", n=len(ok), args=a))
    m.setdefault("summary", {})[f"{a.model}_N{a.ns}"] = dict(ok=len(ok), still_failed=failed,
                                                             error_rows=sum(1 for r in allr if r["error"]))
    X.meta_save(m)
    X.log(f"F1 {a.model}: ok {len(ok)}, still failed {failed}")
    if failed > 0.01 * max(1, len(keys)):
        raise SystemExit(f"F1 {a.model}: {failed} still failed > 1 % — STOP")
    if len(ok) < len(ns) * (845 + N_GREY):
        raise SystemExit(f"F1 {a.model}: incomplete ({len(ok)}) — rerun to resume")


if __name__ == "__main__":
    main()
