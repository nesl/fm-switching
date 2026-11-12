#!/usr/bin/env python3
"""StudyE10a-jpeg Job B — JPEG vs PNG accuracy parity (vLLM venv; h100nvl GPU 2; batched, no latency claim).

Nexar (stages nexar4, nexar32): 400 D14 decisions (random.Random(0): 200 positive-clip (clip, t) with
abs(t - time_of_event) <= 3 s, 200 negative-clip (clip, t)), each at N = 1 and N = 3. D14's request form exactly
(d3_infer_vllm.body: header + N SMALL PNGs (sha256 re-checked) + D3 query; greedy, max_tokens 8, seed 0, logprobs top
20, non-streaming) on D14's stack (prefix caching off, --mm-processor-cache-gb 0, images <= 9), sent twice per arm:
  png   the stored PNG bytes (= D14's request)
  jpeg  every frame decoded from those PNG bytes and re-encoded JPEG q90 (PIL, 4:2:0), data:image/jpeg
Score = D14's: P(Yes) = Yes / (Yes + No) first-token mass; score = log P(Yes) floored at 1e-12.
S-EMBER (stage sember32): 100 questions (random.Random(0) over the 845), 32B K3 = R1's RECENT request (R1 body, video
transport, media_io_kwargs, seed 42, temperature 0, max_tokens 512) with each final-size npz frame JPEG q88-encoded
on the client instead of PNG; R1's server flags (R1 MM_LIMIT) + processor cache off + prompt-token details.
Prompt tokens must equal R1's processor count (manifest n_input_instruct) — recorded per row, STOP if any differ.
Transport errors retried twice (F.post); STOP if > 1 % fail, on a server-log error, or a foreign process on GPU 2.
Resumable. Rows -> results/cost/study_e10/e10a_{nexar,sember}_requests_h100nvl.jsonl.
"""
import argparse
import asyncio
import base64
import gzip
import hashlib
import io
import json
import math
import random
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx
import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "dashcam"))
sys.path.insert(0, str(HERE.parent / "sember"))
import d3_infer_vllm as D3  # noqa: E402
import study_r1_vllm as R  # noqa: E402
import study_f_common as F  # noqa: E402  (last: port 8031, pinned 4BI, GPU from F_GPU_UUID)

X = F.X
F.GPU_LABEL = "h100nvl GPU 2"
D3.MAN = REPO / "results/dashcam/study_d14_trace/d14_requests_manifest.jsonl.gz"
D3.FR = Path.home() / "data/dashcam/d14_frames/small"
OUT = REPO / "results/cost/study_e10"
NREQ = OUT / "e10a_nexar_requests_h100nvl.jsonl"
SREQ = OUT / "e10a_sember_requests_h100nvl.jsonl"
META = OUT / "e10a_run_meta_h100nvl.json"
X.META_PATH = META
X.CURRENT = REPO / "logs/e10a_current.json"
NEX_FLAGS = D3.FLAGS + ["--enable-prompt-tokens-details"]
SEM_FLAGS = R.MM_LIMIT + ["--mm-processor-cache-gb", "0", "--enable-prompt-tokens-details"]
CONC = 8
SRV = None


# ------------------------------------------------------------------------------------------------ Nexar
def nexar_plan():
    rows = [json.loads(l) for l in gzip.open(D3.MAN, "rt")]
    by = {(r["file_name"], r["t"], r["n"]): r for r in rows}
    dec = sorted({(r["file_name"], r["t"], r["label"], r["time_of_event"]) for r in rows})
    pos = [(f, t) for f, t, lab, te in dec if lab == "positive" and te is not None and abs(t - te) <= 3]
    neg = [(f, t) for f, t, lab, te in dec if lab == "negative"]
    rng = random.Random(0)
    pick = sorted(rng.sample(pos, 200)) + sorted(rng.sample(neg, 200))
    return pick, by


def jpeg_bytes(png_bytes, q):
    im = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=q)
    return buf.getvalue()


def nexar_body(req, model, enc):
    b, hashes, hdr = D3.body(req, model)
    if enc == "jpeg":
        for part, key in zip(b["messages"][0]["content"][1:-1], req["frame_keys"]):
            png = (D3.FR / req["file_name"].replace(".mp4", "") / f"{key}.png").read_bytes()
            part["image_url"]["url"] = "data:image/jpeg;base64," + base64.b64encode(jpeg_bytes(png, 90)).decode()
    nbytes = sum(len(p["image_url"]["url"]) for p in b["messages"][0]["content"][1:-1])
    return b, hashes, nbytes


async def nexar_one(c, req, model, enc, sem):
    async with sem:
        b, hashes, nb = await asyncio.to_thread(nexar_body, req, model, enc)
        t0 = time.time()
        j, err, attempts, seen = await F.post(c, b)
        lp, u = None, {}
        if not err:
            ch = j["choices"][0]
            lp = (ch.get("logprobs") or {}).get("content")
            u = j.get("usage") or {}
        p, y, n = D3.yes_no(lp)
        rec = dict(model=model, n=req["n"], enc=enc, request_id=req["request_id"], file_name=req["file_name"],
                   t=req["t"], label=req["label"], time_of_event=req["time_of_event"], p_yes=p,
                   score=None if p is None else math.log(max(p, 1e-12)), mass_yes=y, mass_no=n,
                   first_token=lp[0]["token"] if lp else None, prompt_tokens=u.get("prompt_tokens"),
                   cached_tokens=(u.get("prompt_tokens_details") or {}).get("cached_tokens"),
                   image_url_chars=nb, frame_sha256=hashes, error=err, attempts=attempts, transport_errors=seen,
                   wall_s=round(time.time() - t0, 3), at=F.now())
        with open(NREQ, "a") as f:
            f.write(json.dumps(rec) + "\n")
        return rec


async def run_nexar(model):
    pick, by = nexar_plan()
    m = X.meta_load()
    m["nexar_decisions"] = [list(x) for x in pick]
    X.meta_save(m)
    have = set()
    if NREQ.exists():
        have = {(r["model"], r["n"], r["enc"], r["request_id"]) for r in map(json.loads, open(NREQ)) if not r["error"]}
    todo = [(by[(f, t, n)], enc) for enc in ("png", "jpeg") for n in (1, 3) for f, t in pick
            if (model, n, enc, by[(f, t, n)]["request_id"]) not in have]
    X.log(f"E10a nexar {model}: {len(todo)} to run")
    sem = asyncio.Semaphore(CONC)
    async with httpx.AsyncClient(timeout=None) as c:
        for i in range(0, len(todo), 200):
            check()
            await asyncio.gather(*(nexar_one(c, r, model, e, sem) for r, e in todo[i:i + 200]))
            X.log(f"E10a nexar {model}: {min(i + 200, len(todo))}/{len(todo)}")


# ------------------------------------------------------------------------------------------------ S-EMBER
def jpeg_b64(fr, q=88):
    buf = io.BytesIO()
    Image.fromarray(np.ascontiguousarray(fr.transpose(1, 2, 0))).save(buf, format="JPEG", quality=q)
    return base64.b64encode(buf.getvalue()).decode()


def sember_body(row):
    b, _, n = R.body(row, "K3", "32BI", dict(temperature=0.0, max_tokens=512), stream=False)
    z = np.load(R.INP / row["construction"] / f"{row['question_id']}.npz")
    url = "data:video/jpeg;base64," + ",".join(jpeg_b64(f) for f in z["frames"])
    b["messages"][0]["content"][0]["video_url"]["url"] = url
    return b, n, len(url)


async def sember_one(c, row, sem):
    async with sem:
        b, n, nb = await asyncio.to_thread(sember_body, row)
        t0 = time.time()
        j, err, attempts, seen = await F.post(c, b)
        text, u, fin = "", {}, None
        if not err:
            ch = j["choices"][0]
            text = ch["message"].get("content") or ""
            u = j.get("usage") or {}
            fin = ch.get("finish_reason")
        pred = F.parse_letter(text) if not err else None
        rec = dict(model="32BI", cell="K3_JPEG88", question_id=row["question_id"], video_id=row["video_id"],
                   n_frames=n, text=text, pred=pred, correct_letter=row["correct_letter"],
                   correct=(pred == row["correct_letter"]) if pred else None, prompt_tokens=u.get("prompt_tokens"),
                   expected_prompt_tokens=row["n_input_instruct"],
                   prompt_tokens_match=u.get("prompt_tokens") == row["n_input_instruct"] if u else None,
                   cached_tokens=(u.get("prompt_tokens_details") or {}).get("cached_tokens"), finish_reason=fin,
                   video_url_chars=nb, error=err, attempts=attempts, transport_errors=seen,
                   wall_s=round(time.time() - t0, 3), at=F.now())
        with open(SREQ, "a") as f:
            f.write(json.dumps(rec) + "\n")
        return rec


async def run_sember():
    rows = {(r["question_id"], r["construction"]): r for r in map(json.loads, gzip.open(
        REPO / "results/sember/study_r1/study_r1_inputs_manifest.jsonl.gz", "rt"))}
    qids = sorted({q for q, _ in rows})
    pick = sorted(random.Random(0).sample(qids, 100))
    m = X.meta_load()
    m["sember_questions"] = pick
    X.meta_save(m)
    have = set()
    if SREQ.exists():
        have = {r["question_id"] for r in map(json.loads, open(SREQ)) if not r["error"]}
    todo = [rows[(q, "RECENT")] for q in pick if q not in have]
    X.log(f"E10a sember32: {len(todo)} to run")
    sem = asyncio.Semaphore(CONC)
    check()
    async with httpx.AsyncClient(timeout=None) as c:
        recs = await asyncio.gather(*(sember_one(c, r, sem) for r in todo))
    bad = [r["question_id"][:10] for r in recs if not r["error"] and not r["prompt_tokens_match"]]
    if bad:
        raise SystemExit(f"S-EMBER JPEG prompt tokens differ from R1's on {len(bad)} questions — STOP: {bad[:5]}")


# ------------------------------------------------------------------------------------------------ main
def check():
    fo = F.foreign()
    if fo:
        raise SystemExit(f"foreign process on GPU 2 — STOP: {fo}")
    se = F.server_errors(SRV)
    if se:
        raise SystemExit(f"server log error — STOP: {se[0]}")


def main():
    global SRV
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["nexar4", "nexar32", "sember32"], required=True)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    model = "4BI" if a.stage == "nexar4" else "32BI"
    flags = SEM_FLAGS if a.stage == "sember32" else NEX_FLAGS
    F.require_idle()
    srv = X.Server(model, flags)
    SRV = srv
    try:
        info = srv.start()
        import torch
        import vllm
        m = X.meta_load()
        m["stack"] = dict(venv=sys.prefix, vllm=vllm.__version__, torch=torch.__version__, gpu=F.GPU_LABEL,
                          gpu_uuid=F.GPU_UUID)
        m.setdefault("servers", []).append(dict(stage=a.stage, model=model, flags=flags,
                                                started=datetime.now().isoformat(), **info))
        X.meta_save(m)
        asyncio.run(run_sember() if a.stage == "sember32" else run_nexar(model))
        check()
    finally:
        srv.stop()
    path = SREQ if a.stage == "sember32" else NREQ
    allr = [json.loads(l) for l in open(path)]
    if a.stage != "sember32":
        allr = [r for r in allr if r["model"] == model]
        keys = {(r["n"], r["enc"], r["request_id"]) for r in allr}
        ok = {(r["n"], r["enc"], r["request_id"]) for r in allr if not r["error"]}
        need = 1600
    else:
        keys = {r["question_id"] for r in allr}
        ok = {r["question_id"] for r in allr if not r["error"]}
        need = 100
    failed = len(keys - ok)
    from _provenance import stamp
    m = X.meta_load()
    m.setdefault("_provenance", []).append(stamp(script="study_e10a_parity_vllm.py", model=model,
                                                 device="h100nvl_gpu2", n=len(ok), args=a))
    m.setdefault("summary", {})[a.stage] = dict(ok=len(ok), still_failed=failed,
                                                error_rows=sum(1 for r in allr if r["error"]))
    X.meta_save(m)
    X.log(f"E10a {a.stage}: ok {len(ok)}, still failed {failed}")
    if failed > 0.01 * max(1, len(keys)):
        raise SystemExit(f"E10a {a.stage}: {failed} still failed > 1 % — STOP")
    if len(ok) < need:
        raise SystemExit(f"E10a {a.stage}: incomplete ({len(ok)}/{need}) — rerun to resume")


if __name__ == "__main__":
    main()
