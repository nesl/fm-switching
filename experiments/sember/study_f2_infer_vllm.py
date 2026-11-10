#!/usr/bin/env python3
"""StudyF2-summary, stage 2: answers with [summary] + K3's RECENT video unchanged (vLLM venv; h100nvl GPU 1).

Request = StudyR1's own K3 body (study_r1_vllm.body: K3's npz frames as ONE video in R1's jpeg-sequence transport,
R1's media_io_kwargs, R1's question text, request seed 42) with ONE change: when the question has a non-empty summary,
a text block is inserted BEFORE the video:
  "Summary of earlier video:\n[0–30 s] <caption>\n[30–60 s] <caption>..."
built from every chunk caption (f2_captions_h100nvl.jsonl) whose chunk ends at or before qt - 120 s, in time order.
At qt <= 120 nothing is inserted, so the request equals K3's (negative control: letters must equal K3 (32B) and
H1 (4B) on every qt <= 120 question — STOP on any mismatch, before the analysis).
Decoding: greedy, max_tokens 64 (R1: 512), non-streaming, logprobs top 20. Server: R1's flags (R.MM_LIMIT) +
--mm-processor-cache-gb 0 + --enable-prompt-tokens-details; prefix caching off.
Length: summary tokens (tokenizer) + K3's expected prompt tokens + 64 must be <= 32,768 for every question, checked
before the server starts — STOP rather than truncate. Rows -> results/sember/study_f2/f2_requests_h100nvl.jsonl.
Usage: study_f2_infer_vllm.py --model 32BI|4BI
"""
import argparse
import asyncio
import gzip
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import study_f_common as F  # noqa: E402
import study_r1_vllm as R  # noqa: E402

R1BODY = R.body     # R1's own builder, captured at import (other modules rebind R.body; study_f3 resets this)

X = F.X
OUT = Path("results/sember/study_f2")
CAP = OUT / "f2_captions_h100nvl.jsonl"
REQ = OUT / "f2_requests_h100nvl.jsonl"
META = OUT / "f2_run_meta_h100nvl.json"
X.META_PATH = META
X.CURRENT = Path("logs/f2_current.json")
R1MAN = Path("results/sember/study_r1/study_r1_inputs_manifest.jsonl.gz")
GEN = dict(temperature=0.0, max_tokens=64, logprobs=True, top_logprobs=20)
FLAGS = R.MM_LIMIT + ["--mm-processor-cache-gb", "0", "--enable-prompt-tokens-details"]
MAXLEN, CONC, GAP = 32768, 8, 120
REF = {"32BI": ("results/sember/study_r1/study_r1_requests_h100nvl.jsonl.gz", "K3"),
       "4BI": ("results/cost/study_clean/study_clean_requests_h100nvl.jsonl.gz", "H1")}
SRV = None


def summaries():
    caps = {}
    for r in map(json.loads, open(CAP)):
        if not r["error"]:
            caps.setdefault(r["video_id"], {})[r["k"]] = r
    rows = {}
    for l in gzip.open(R1MAN, "rt"):
        r = json.loads(l)
        if r["construction"] != "RECENT":
            continue
        qt = float(r["question_time"])
        cs = sorted((c for c in caps.get(r["video_id"], {}).values() if c["end_s"] <= qt - GAP + 1e-9),
                    key=lambda c: c["k"])
        need = int((qt - GAP) // 30) if qt > GAP else 0
        assert len(cs) == need, (r["question_id"], len(cs), need)        # every reachable chunk captioned
        text = ("Summary of earlier video:\n" + "\n".join(f"[{c['start_s']}–{c['end_s']} s] {c['caption']}" for c in cs)
                if cs else "")
        rows[r["question_id"]] = dict(r, summary=text, n_chunks=len(cs), chunk_ids=[c["chunk_id"] for c in cs])
    assert len(rows) == 845
    return rows


def length_check(rows, model):
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(X.snapshot(model))
    worst = 0
    for q, r in rows.items():
        st = len(tok(r["summary"])["input_ids"]) if r["summary"] else 0
        r["summary_tokens_est"] = st
        tot = st + r["n_input_instruct"] + GEN["max_tokens"] + 4
        worst = max(worst, tot)
        if tot > MAXLEN:
            raise SystemExit(f"{q}: {tot} tokens > {MAXLEN} — STOP (no truncation)")
    return worst


def body(r, model):
    b, _, nf = R1BODY(r, "F2", model, dict(temperature=0.0), max_tokens=GEN["max_tokens"], stream=False)
    b.update(GEN)
    if r["summary"]:
        b["messages"][0]["content"].insert(0, {"type": "text", "text": r["summary"]})
    return b, nf


async def one(c, r, model, sem):
    async with sem:
        b, nf = await asyncio.to_thread(body, r, model)
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
        rec = dict(model=model, question_id=r["question_id"], video_id=r["video_id"], question_time=r["question_time"],
                   question_category=r["question_category"], n_chunks=r["n_chunks"], chunk_ids=r["chunk_ids"],
                   summary_chars=len(r["summary"]), summary_tokens_est=r.get("summary_tokens_est"), n_frames=nf,
                   k3_expected_prompt_tokens=r["n_input_instruct"], text=text, pred=pred,
                   correct_letter=r["correct_letter"], correct=(pred == r["correct_letter"]) if pred else None,
                   letter_probs=F.letter_probs(lp), prompt_tokens=u.get("prompt_tokens"),
                   completion_tokens=u.get("completion_tokens"),
                   cached_tokens=(u.get("prompt_tokens_details") or {}).get("cached_tokens"), finish_reason=fin,
                   error=err, attempts=attempts, transport_errors=seen, wall_s=round(time.time() - t0, 3), at=F.now())
        with open(REQ, "a") as f:
            f.write(json.dumps(rec) + "\n")
        return rec


async def run(model, rows):
    have = set()
    if REQ.exists():
        have = {(r["model"], r["question_id"]) for r in map(json.loads, open(REQ)) if not r["error"]}
    order = sorted(rows.values(), key=lambda r: (r["video_id"], r["question_time"], r["question_id"]))
    todo = [r for r in order if (model, r["question_id"]) not in have]
    X.log(f"F2 {model}: {len(todo)} to run")
    sem = asyncio.Semaphore(CONC)
    async with httpx.AsyncClient(timeout=None) as c:
        for i in range(0, len(todo), 120):
            fo = F.foreign()
            if fo:
                raise SystemExit(f"foreign process on GPU 1 — STOP: {fo}")
            await asyncio.gather(*(one(c, r, model, sem) for r in todo[i:i + 120]))
            X.log(f"F2 {model}: {min(i + 120, len(todo))}/{len(todo)}  sm {F.sm_clock()}")
            se = F.server_errors(SRV)
            if se:
                raise SystemExit(f"server log error — STOP: {se[0]}")


def negative_control(model):
    p, cell = REF[model]
    ref = {}
    for l in gzip.open(p, "rt"):
        r = json.loads(l)
        if r["cell"] == cell and r.get("mode", "batched") == "batched" and not r["error"]:
            ref[r["question_id"]] = r
    mine = {r["question_id"]: r for r in map(json.loads, open(REQ)) if r["model"] == model and not r["error"]}
    qs = [q for q, r in mine.items() if float(r["question_time"]) <= GAP]
    mism = [q for q in qs if mine[q]["pred"] != ref[q]["pred"]]
    tokd = [q for q in qs if mine[q]["prompt_tokens"] != ref[q]["prompt_tokens"]]
    res = dict(reference=cell, n=len(qs), letter_mismatch=len(mism), prompt_token_mismatch=len(tokd),
               mismatched=mism[:20])
    m = X.meta_load()
    m.setdefault("negative_control", {})[model] = res
    X.meta_save(m)
    X.log(f"negative control {model} vs {cell}: {res}")
    if mism or tokd:
        raise SystemExit(f"negative control FAILED for {model}: {res} — STOP")


def main():
    global SRV
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", choices=["4BI", "32BI"], required=True)
    a = ap.parse_args()
    rows = summaries()
    worst = length_check(rows, a.model)
    m = X.meta_load()
    m.setdefault("length_check", {})[a.model] = dict(worst_estimated_total=worst, max_model_len=MAXLEN)
    X.meta_save(m)
    X.log(f"length check passed: worst estimated {worst} <= {MAXLEN}")
    F.require_idle()
    srv = X.Server(a.model, FLAGS)
    SRV = srv
    try:
        info = srv.start()
        import torch
        import vllm
        m = X.meta_load()
        m["stack_answers"] = dict(venv=sys.prefix, vllm=vllm.__version__, torch=torch.__version__, gpu=F.GPU_LABEL,
                                  gpu_uuid=F.GPU_UUID, flags=FLAGS, gen=GEN, seed=R.SEED, concurrency=CONC)
        m.setdefault("servers", []).append(dict(stage=f"answers_{a.model}", started=datetime.now().isoformat(), **info))
        X.meta_save(m)
        asyncio.run(run(a.model, rows))
    finally:
        srv.stop()
    allr = [json.loads(l) for l in open(REQ) if json.loads(l)["model"] == a.model]
    ok = {r["question_id"] for r in allr if not r["error"]}
    failed = 845 - len(ok)
    from _provenance import stamp
    m = X.meta_load()
    m.setdefault("_provenance", []).append(stamp(script="study_f2_infer_vllm.py", model=a.model,
                                                 device="h100nvl_gpu1", n=len(ok), args=a))
    m.setdefault("summary", {})[a.model] = dict(ok=len(ok), still_failed=failed,
                                                error_rows=sum(1 for r in allr if r["error"]))
    X.meta_save(m)
    if failed > 0.01 * 845:
        raise SystemExit(f"F2 {a.model}: {failed} still failed > 1 % — STOP")
    if failed:
        raise SystemExit(f"F2 {a.model}: {failed} missing — rerun to resume")
    negative_control(a.model)


if __name__ == "__main__":
    main()
