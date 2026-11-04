#!/usr/bin/env python3
"""StudyD13 (GPU part) — rerun StudyClean H1 (4B-I on K3's exact 845 RECENT requests) with answer-letter logprobs.

Stack = StudyClean's (study_clean_vllm imports: vLLM 0.31.0 venv, Qwen3-VL-4B-Instruct @ebb281ec, R1's video request
via study_r1_vllm.body, server flags R.MM_LIMIT, prefix caching off, conc 8, greedy, max_tokens 512, seed 42).
Only difference from H1: the request is non-streaming and asks for logprobs=True, top_logprobs=20 (the vLLM maximum
by default). Logprobs are computed after sampling, so greedy letters should not change; the gate checks it.

GPU: CUDA_VISIBLE_DEVICES / CLEAN_GPU_UUID = GPU 2's UUID (set by the chain). Resumable: rows already present
without error are skipped. STOP: > 1 % errors; letter match with H1 < 99 %.
"""
import asyncio
import json
import math
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import study_clean_vllm as C  # noqa: E402  (sets R.manifest, R.body, X.gpu3_pids -> CLEAN_GPU_UUID)

X, R = C.X, C.R
OUT = Path("results/cost/study_d13")
REQ = OUT / f"study_d13_requests_{X.DEV}.jsonl"
META = OUT / f"study_d13_run_meta_{X.DEV}.json"
H1_REQ = Path("results/cost/study_clean/study_clean_requests_h100nvl.jsonl.gz")
X.META_PATH = META
X.CURRENT = Path("logs/study_d13_current.json")
LETTERS = "ABCDE"
TOPK = 20
GATE = 0.99


def letter_logprobs(lp_content, pred):
    """Find the first generated token whose stripped text is a single A–E letter; return its top-k distribution."""
    for i, tok in enumerate(lp_content or []):
        if tok["token"].strip() in LETTERS and len(tok["token"].strip()) == 1:
            # keep the max over tokenizations of the same letter (e.g. "A" and " A")
            dist = {}
            for t in tok["top_logprobs"]:
                s = t["token"].strip()
                if len(s) == 1 and s in LETTERS:
                    dist[s] = max(dist.get(s, -1e9), t["logprob"])
            mass = sum(math.exp(v) for v in dist.values())
            return dict(position=i, token=tok["token"], token_logprob=tok["logprob"], letter_logprobs=dist,
                        letter_mass_in_topk=mass, matches_pred=tok["token"].strip() == pred)
    return None


async def one(client, row, sem, out):
    async with sem:
        b, _, nfr = await asyncio.to_thread(R.body, row, "D13", "4BI", dict(C.GREEDY), None, False)
        b["logprobs"] = True
        b["top_logprobs"] = TOPK
        t0 = time.time()
        err, j = None, None
        try:
            r = await client.post(f"{X.BASE}/v1/chat/completions", json=b)
            j = r.json()
            if r.status_code != 200 or "choices" not in j:
                err = f"HTTP {r.status_code}: {str(j)[:300]}"
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {e}"
        text, usage, lp, finish = "", {}, None, None
        if not err:
            ch = j["choices"][0]
            text = ch["message"].get("content") or ""
            usage = j.get("usage") or {}
            finish = ch.get("finish_reason")
            lp = (ch.get("logprobs") or {}).get("content")
        _, pred = R.score(text, False)
        ll = letter_logprobs(lp, pred) if lp else None
        rec = dict(cell="D13", mode="batched", question_id=row["question_id"], video_id=row["video_id"],
                   question_time=row["question_time"], question_category=row["question_category"],
                   evidence_covered=row["evidence_covered"], n_frames=row["n_frames"],
                   prompt_tokens=usage.get("prompt_tokens"), completion_tokens=usage.get("completion_tokens"),
                   finish_reason=finish, pred=pred, correct_letter=row["correct_letter"],
                   correct=pred == row["correct_letter"], text=text, letter=ll, n_logprob_tokens=len(lp or []),
                   latency_s=round(time.time() - t0, 3), error=err, at=datetime.now().isoformat())
        out.append(rec)
        with open(REQ, "a") as f:
            f.write(json.dumps(rec) + "\n")


async def run(rows, order):
    have = set()
    if REQ.exists():
        have = {r["question_id"] for r in map(json.loads, open(REQ)) if not r["error"]}
    qs = [q for q in order if q not in have]
    X.log(f"D13: {len(qs)} to run (conc {R.CONC})")
    sem = asyncio.Semaphore(R.CONC)
    out = []
    async with httpx.AsyncClient(timeout=None) as c:
        await asyncio.gather(*(one(c, rows[(q, "RECENT")], sem, out) for q in qs))
    return out


def gate():
    from rawio import read_jsonl
    H1 = {r["question_id"]: r for r in read_jsonl(H1_REQ) if r["cell"] == "H1" and r["mode"] == "batched"}
    rows = {}
    for r in map(json.loads, open(REQ)):
        if not r["error"]:
            rows[r["question_id"]] = r
    errs = sum(1 for r in map(json.loads, open(REQ)) if r["error"])
    same = [rows[q]["pred"] == H1[q]["pred"] for q in rows]
    tok = [rows[q]["prompt_tokens"] == H1[q]["prompt_tokens"] for q in rows]
    res = dict(n=len(rows), n_h1=len(H1), errors_logged=errs, letters_match=int(sum(same)),
               match_rate=sum(same) / max(1, len(same)), prompt_tokens_equal=int(sum(tok)),
               letter_found=int(sum(r["letter"] is not None for r in rows.values())),
               letter_token_is_pred=int(sum(bool(r["letter"] and r["letter"]["matches_pred"]) for r in rows.values())),
               mismatches=[dict(question_id=q, pred=rows[q]["pred"], h1_pred=H1[q]["pred"]) for q, s in
                           zip(rows, same) if not s], gate=GATE)
    res["passed"] = len(rows) == 845 and res["match_rate"] >= GATE
    m = X.meta_load()
    m["h1_match_gate"] = res
    X.meta_save(m)
    X.log(f"D13 GATE: {res['letters_match']}/{res['n']} = {res['match_rate']:.4f} (need >= {GATE}); "
          f"tokens equal {res['prompt_tokens_equal']}; letter found {res['letter_found']}")
    if errs > 0.01 * 845:
        raise SystemExit(f"D13: {errs} errors > 1 % — STOP")
    if not res["passed"]:
        raise SystemExit("D13 letter match with H1 < 99 % (or incomplete) — STOP")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    srv = X.Server("4BI", R.MM_LIMIT)
    try:
        info = srv.start()
        import torch
        import vllm
        m = X.meta_load()
        m["stack"] = dict(venv=sys.prefix, vllm=vllm.__version__, torch=torch.__version__, cuda=torch.version.cuda,
                          gpu_uuid=C.GPU_UUID, request="non-streaming, logprobs=True, top_logprobs=20")
        m.setdefault("servers", []).append(dict(started=datetime.now().isoformat(), **info))
        X.meta_save(m)
        rows, order = R.manifest()
        assert len(order) == 845
        asyncio.run(run(rows, order))
    finally:
        srv.stop()
    gate()
    from _provenance import stamp
    m = X.meta_load()
    m.setdefault("_provenance", []).append(stamp(script="study_d13_vllm.py", model="4BI", device=f"{X.DEV}_gpu2",
                                                 n=845))
    X.meta_save(m)


if __name__ == "__main__":
    main()
