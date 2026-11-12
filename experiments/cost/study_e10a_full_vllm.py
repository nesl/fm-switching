#!/usr/bin/env python3
"""StudyE10a-full — JPEG parity on all 845 S-EMBER questions (vLLM venv; h100nvl GPU 2; batched, no latency claim).

32B-I @0cfaf481, cells K3 (R1 RECENT) and K1 (R1 RICH), all 845 questions each. Exactly E10a's sember32 request:
R1's body (video transport, media_io_kwargs, seed 42, temperature 0, max_tokens 512) with every final-size npz frame
JPEG q88-encoded on the client (study_e10a_parity_vllm.jpeg_b64) instead of PNG. Server: R1's flags (R.MM_LIMIT) +
--mm-processor-cache-gb 0 + prompt-token details; prefix caching OFF (study_x_vllm default). Prompt tokens must equal
R1's processor count (manifest n_input_instruct), STOP otherwise. Transport errors retried twice (F.post); STOP if
> 1 % remain failed, on a server-log error or a foreign process on GPU 2. Resumable.
Rows -> results/cost/study_e10/e10a_full_requests_h100nvl.jsonl
"""
import asyncio
import gzip
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import study_e10a_parity_vllm as A  # noqa: E402  (imports R, F, X; F pins port / GPU)

R, F, X = A.R, A.F, A.X
REPO = A.REPO
OUT = A.OUT
REQ = OUT / "e10a_full_requests_h100nvl.jsonl"
META = OUT / "e10a_full_run_meta_h100nvl.json"
X.META_PATH = META
X.CURRENT = REPO / "logs/e10a_full_current.json"
CELLS = {"K3": "RECENT", "K1": "RICH"}
SRV = None


def body(row, cell):
    b, _, n = R.body(row, cell, "32BI", dict(temperature=0.0, max_tokens=512), stream=False)
    z = np.load(R.INP / row["construction"] / f"{row['question_id']}.npz")
    url = "data:video/jpeg;base64," + ",".join(A.jpeg_b64(f) for f in z["frames"])
    b["messages"][0]["content"][0]["video_url"]["url"] = url
    return b, n, len(url)


async def one(c, row, cell, sem):
    async with sem:
        b, n, nb = await asyncio.to_thread(body, row, cell)
        t0 = time.time()
        j, err, attempts, seen = await F.post(c, b)
        text, u, fin = "", {}, None
        if not err:
            ch = j["choices"][0]
            text = ch["message"].get("content") or ""
            u = j.get("usage") or {}
            fin = ch.get("finish_reason")
        pred = F.parse_letter(text) if not err else None
        rec = dict(model="32BI", cell=cell, enc="jpeg88", construction=row["construction"],
                   question_id=row["question_id"], video_id=row["video_id"], n_frames=n, text=text, pred=pred,
                   correct_letter=row["correct_letter"], correct=(pred == row["correct_letter"]) if pred else None,
                   prompt_tokens=u.get("prompt_tokens"), expected_prompt_tokens=row["n_input_instruct"],
                   prompt_tokens_match=u.get("prompt_tokens") == row["n_input_instruct"] if u else None,
                   cached_tokens=(u.get("prompt_tokens_details") or {}).get("cached_tokens"), finish_reason=fin,
                   video_url_chars=nb, error=err, attempts=attempts, transport_errors=seen,
                   wall_s=round(time.time() - t0, 3), at=F.now())
        with open(REQ, "a") as f:
            f.write(json.dumps(rec) + "\n")
        return rec


def check():
    fo = F.foreign()
    if fo:
        raise SystemExit(f"foreign process on GPU 2 — STOP: {fo}")
    se = F.server_errors(SRV)
    if se:
        raise SystemExit(f"server log error — STOP: {se[0]}")


async def run():
    rows = {(r["question_id"], r["construction"]): r for r in map(json.loads, gzip.open(
        REPO / "results/sember/study_r1/study_r1_inputs_manifest.jsonl.gz", "rt"))}
    qids = sorted({q for q, _ in rows})
    assert len(qids) == 845, len(qids)
    have = set()
    if REQ.exists():
        have = {(r["cell"], r["question_id"]) for r in map(json.loads, open(REQ)) if not r["error"]}
    sem = asyncio.Semaphore(A.CONC)
    async with httpx.AsyncClient(timeout=None) as c:
        for cell, cons in CELLS.items():
            todo = [rows[(q, cons)] for q in qids if (cell, q) not in have]
            X.log(f"E10a-full {cell}: {len(todo)} to run")
            for i in range(0, len(todo), 80):
                check()
                recs = await asyncio.gather(*(one(c, r, cell, sem) for r in todo[i:i + 80]))
                bad = [r["question_id"][:10] for r in recs if not r["error"] and not r["prompt_tokens_match"]]
                if bad:
                    raise SystemExit(f"{cell}: prompt tokens differ from R1's on {len(bad)} — STOP: {bad[:5]}")
                X.log(f"E10a-full {cell}: {min(i + 80, len(todo))}/{len(todo)}")


def main():
    global SRV
    OUT.mkdir(parents=True, exist_ok=True)
    F.require_idle()
    flags = A.SEM_FLAGS
    srv = X.Server("32BI", flags)
    SRV = A.SRV = srv
    try:
        info = srv.start()
        import torch
        import vllm
        m = X.meta_load()
        m["stack"] = dict(venv=sys.prefix, vllm=vllm.__version__, torch=torch.__version__, gpu="h100nvl GPU 2",
                          gpu_uuid=F.GPU_UUID, prefix_caching=False, processor_cache_gb=0)
        m.setdefault("servers", []).append(dict(model="32BI", flags=flags, started=datetime.now().isoformat(), **info))
        X.meta_save(m)
        asyncio.run(run())
        check()
    finally:
        srv.stop()
    allr = [json.loads(l) for l in open(REQ)]
    keys = {(r["cell"], r["question_id"]) for r in allr}
    ok = {(r["cell"], r["question_id"]) for r in allr if not r["error"]}
    failed = len(keys - ok)
    from _provenance import stamp
    m = X.meta_load()
    m.setdefault("_provenance", []).append(stamp(script="study_e10a_full_vllm.py", model="32BI",
                                                 device="h100nvl_gpu2", n=len(ok)))
    m["summary"] = dict(ok=len(ok), still_failed=failed, error_rows=sum(1 for r in allr if r["error"]))
    X.meta_save(m)
    X.log(f"E10a-full: ok {len(ok)}, still failed {failed}")
    if failed > 0.01 * max(1, len(keys)):
        raise SystemExit(f"E10a-full: {failed} still failed > 1 % — STOP")
    if len(ok) < 2 * 845:
        raise SystemExit(f"E10a-full: incomplete ({len(ok)}/1690) — rerun to resume")


if __name__ == "__main__":
    main()
