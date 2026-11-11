#!/usr/bin/env python3
"""StudyE7-d2-4b Job A — 4B-Instruct on RH4's D2 append-only history (vLLM venv; h100nvl GPU 2). ACCURACY ONLY.

Request = RH4's own body for cell D2, unchanged: [RH4 D2 header] + 352x256 separate images at t = 0, 2, 4, ... <= qt
(RH4/RH3 builder, img_url PNG encoding) + [R1 question text]; request seed R1's (42); greedy. Only the generation
length and logprobs differ from RH4 (max_tokens 64, logprobs top 20, per the job spec). Non-streaming, concurrency 8.
Server: study_f_common stack (vLLM 0.31.0, pinned 4BI @ebb281ec, prefix caching OFF) + RH3/RH4 IMAGE_FLAGS (images
<= 640, processor size = PROC_SIZE so the builder's sizes are not rescaled) + processor cache off + prompt-token details.
Over-context questions (RH4 manifest over_context) are sent as built; their HTTP 400 is recorded as INFEASIBLE (never
truncated, never retried). Parity gate: the first 5 feasible questions' vLLM prompt tokens must equal RH4's processor
count (n_input_instruct) — STOP otherwise; every row records the match.
Each row stores body_sha256 = SHA-256 of the canonical JSON of the request's messages (Job C re-derives it from the
archive). Grey control: 100 feasible questions (seed 0), every image replaced by a uniform RGB(128) PNG of the same size.
STOP: > 1 % of feasible requests failed after 2 transport retries; server-log error; a foreign process on GPU 2.
Resumable: rows without error (or infeasible rows) are skipped. Rows -> results/sember/study_e7/e7_requests_h100nvl.jsonl.
"""
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
import study_rh4_fixed_stride as RH  # noqa: E402
import study_f_common as F  # noqa: E402  (imported after RH so its X settings win: port 8031, GPU from F_GPU_UUID)

X, R, W3, B = F.X, RH.R, RH.W3, RH.B
F.GPU_LABEL = "h100nvl GPU 2"
OUT = Path("results/sember/study_e7")
REQ = OUT / "e7_requests_h100nvl.jsonl"
META = OUT / "e7_run_meta_h100nvl.json"
X.META_PATH = META
X.CURRENT = Path("logs/e7_current.json")
MODEL = "4BI"
GEN = dict(temperature=0.0, logprobs=True, top_logprobs=20)
MAX_TOKENS = 64
FLAGS = W3.IMAGE_FLAGS + ["--mm-processor-cache-gb", "0", "--enable-prompt-tokens-details"]
CONC, N_GREY = 8, 100
SRV = None
_GREY = {}


def grey_url(url):
    """Uniform RGB(128) PNG with the same pixel size as the real image."""
    from PIL import Image
    im = Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1])))
    if im.size not in _GREY:
        buf = io.BytesIO()
        Image.new("RGB", im.size, (128, 128, 128)).save(buf, format="PNG")
        _GREY[im.size] = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    return _GREY[im.size]


def messages_sha(msgs):
    return hashlib.sha256(json.dumps(msgs, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def body(row, grey=False):
    b, _, n = RH.body(dict(row), "D2", MODEL, GEN, max_tokens=MAX_TOKENS, stream=False)
    if grey:
        for part in b["messages"][0]["content"]:
            if part["type"] == "image_url":
                part["image_url"]["url"] = grey_url(part["image_url"]["url"])
    return b, n


def infeasible(err):
    return bool(err) and err.startswith("HTTP 400") and ("context" in err or "too long" in err or "exceeds" in err)


async def one(c, row, sem, grey=False):
    async with sem:
        b, n = await asyncio.to_thread(body, row, grey)
        sha = messages_sha(b["messages"])
        t0 = time.time()
        j, err, attempts, seen = await F.post(c, b)   # over-context: sent as built; an HTTP 400 is not retried
        text, lp, u, fin = "", None, {}, None
        if not err:
            ch = j["choices"][0]
            text = ch["message"].get("content") or ""
            lp = (ch.get("logprobs") or {}).get("content")
            u = j.get("usage") or {}
            fin = ch.get("finish_reason")
        pred = F.parse_letter(text) if not err else None
        rec = dict(model=MODEL, cell="D2", question_id=row["question_id"], video_id=row["video_id"], grey=grey,
                   question_time=row["question_time"], question_category=row["question_category"], n_images=n,
                   over_context_manifest=row["over_context"], infeasible=infeasible(err),
                   expected_prompt_tokens=row["n_input_instruct"], text=text, pred=pred,
                   correct_letter=row["correct_letter"], correct=(pred == row["correct_letter"]) if pred else None,
                   letter_probs=F.letter_probs(lp), prompt_tokens=u.get("prompt_tokens"),
                   prompt_tokens_match=(u.get("prompt_tokens") == row["n_input_instruct"]) if u else None,
                   completion_tokens=u.get("completion_tokens"),
                   cached_tokens=((u.get("prompt_tokens_details") or {}).get("cached_tokens")), finish_reason=fin,
                   body_sha256=sha, seed=b["seed"], error=err, attempts=attempts, transport_errors=seen,
                   wall_s=round(time.time() - t0, 3), at=F.now())
        with open(REQ, "a") as f:
            f.write(json.dumps(rec) + "\n")
        return rec


def check_gpu():
    fo = F.foreign()
    if fo:
        raise SystemExit(f"foreign process on GPU 2 — STOP: {fo}")


def done_keys():
    if not REQ.exists():
        return set()
    return {(r["question_id"], r["grey"]) for r in map(json.loads, open(REQ)) if not r["error"] or r["infeasible"]}


async def run(rows, order):
    have = done_keys()
    sem = asyncio.Semaphore(CONC)
    feasible = [q for q in order if not rows[q]["over_context"]]
    grey_q = sorted(random.Random(0).sample(feasible, N_GREY))
    m = X.meta_load()
    m["grey_questions"] = grey_q
    X.meta_save(m)
    async with httpx.AsyncClient(timeout=None) as c:
        if "parity" not in X.meta_load():
            par = []
            for q in feasible[:5]:
                b, n = body(rows[q])
                b = dict(b, max_tokens=1)
                r = (await c.post(f"{X.BASE}/v1/chat/completions", json=b)).json()
                pt = (r.get("usage") or {}).get("prompt_tokens")
                par.append(dict(question_id=q, n_images=n, vllm_prompt_tokens=pt,
                                rh4_processor_tokens=rows[q]["n_input_instruct"], match=pt == rows[q]["n_input_instruct"]))
                X.log(f"parity {q[:10]} images {n} vllm {pt} rh4 {rows[q]['n_input_instruct']}")
            m = X.meta_load()
            m["parity"] = dict(gate_passed=all(p["match"] for p in par), rows=par)
            X.meta_save(m)
            if not m["parity"]["gate_passed"]:
                raise SystemExit("E7 parity gate FAILED (4B prompt tokens != RH4 processor count) — STOP")
        for grey, pool in ((False, order), (True, grey_q)):
            todo = [rows[q] for q in pool if (q, grey) not in have]
            X.log(f"E7 4BI D2 grey={grey}: {len(todo)} to run")
            for i in range(0, len(todo), 200):
                check_gpu()
                await asyncio.gather(*(one(c, r, sem, grey) for r in todo[i:i + 200]))
                X.log(f"E7 4BI D2 grey={grey}: {min(i + 200, len(todo))}/{len(todo)}  sm {F.sm_clock()}")
                se = [s for s in F.server_errors(SRV) if "exceeds" not in s and "context length" not in s
                      and "maximum" not in s]
                if se:
                    raise SystemExit(f"server log error — STOP: {se[0]}")


def main():
    global SRV
    OUT.mkdir(parents=True, exist_ok=True)
    allrows, _ = RH.manifest()
    rows = {q: r for (q, cell), r in allrows.items() if cell == "D2"}
    order = sorted(rows, key=lambda q: (rows[q]["video_id"], q))
    assert len(rows) == 845
    F.require_idle()
    srv = X.Server(MODEL, FLAGS)
    SRV = srv
    try:
        info = srv.start()
        import torch
        import vllm
        m = X.meta_load()
        m["stack"] = dict(venv=sys.prefix, vllm=vllm.__version__, torch=torch.__version__, gpu=F.GPU_LABEL,
                          gpu_uuid=F.GPU_UUID, flags=FLAGS, gen=dict(GEN, max_tokens=MAX_TOKENS, seed=R.SEED),
                          concurrency=CONC, body="study_rh4_fixed_stride.body (cell D2), unchanged")
        m.setdefault("servers", []).append(dict(model=MODEL, started=datetime.now().isoformat(), **info))
        X.meta_save(m)
        asyncio.run(run(rows, order))
    finally:
        srv.stop()
    allr = [json.loads(l) for l in open(REQ)]
    keys = {(r["question_id"], r["grey"]) for r in allr}
    ok = {(r["question_id"], r["grey"]) for r in allr if not r["error"]}
    inf = {(r["question_id"], r["grey"]) for r in allr if r["infeasible"]}
    failed = len(keys - ok - inf)
    from _provenance import stamp
    m = X.meta_load()
    m.setdefault("_provenance", []).append(stamp(script="study_e7_infer_vllm.py", model=MODEL, device="h100nvl_gpu2",
                                                 n=len(ok)))
    m["summary"] = dict(ok=len(ok), infeasible=len(inf), still_failed=failed,
                        error_rows=sum(1 for r in allr if r["error"]))
    X.meta_save(m)
    X.log(f"E7 4BI: ok {len(ok)}, infeasible {len(inf)}, still failed {failed}")
    if failed > 0.01 * max(1, len(keys) - len(inf)):
        raise SystemExit(f"E7: {failed} still failed > 1 % — STOP")
    if len(ok) + len(inf) < 845 + N_GREY:
        raise SystemExit(f"E7: incomplete ({len(ok)} + {len(inf)}) — rerun to resume")


if __name__ == "__main__":
    main()
