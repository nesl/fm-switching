#!/usr/bin/env python3
"""StudyD2-nexar pilot inference (vLLM venv; h100nvl GPU 2). ACCURACY ONLY — batched; no latency is reported.

Stack: study_x_vllm.Server (vLLM 0.31.0, FA3, max_model_len 32768, gmu 0.90, prefix caching OFF) +
--mm-processor-cache-gb 0, images <= 9. Pinned: 4BI Qwen3-VL-4B-Instruct @ebb281ec, 32BI @0cfaf481.
Greedy, max_tokens 8, logprobs (top 20) at every generated position, request seed 0, non-streaming, conc 8.
Request: one user turn = [HEADER text] + 9 PNG images (oldest first, lossless files from d2_prepare.py, sha256
re-checked when the body is built) + [QUERY text]. No times, file names or elapsed time appear in the prompt.
Arms per model: native (1280x720) and small (768x432) for all 1,050 pilot requests, then the grey control
(9 uniform RGB(128,128,128) frames at that resolution, 100 identical requests per resolution).
Before the sweep (first model only): one traced prompt (return_token_ids, decoded) -> prompt_trace.txt, with an
assertion that the only digits in the non-image text are the header's '9' and '3'.
GPU 2 must be idle or ours before the server starts (else STOP). Resumable; STOP on > 1 % errors.
Usage: d2_infer_vllm.py --model 4BI|32BI
"""
import argparse
import asyncio
import base64
import hashlib
import io
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "cost"))
sys.path.insert(0, str(HERE.parent / "lib"))
import study_x_vllm as X  # noqa: E402

X.REPO["4BI"] = ("Qwen/Qwen3-VL-4B-Instruct", "ebb281ec70b05090aa6165b016eac8ec08e71b17")
OUT = Path("results/dashcam/study_d2_nexar")
MAN = OUT / "pilot_requests.jsonl"
FR = Path.home() / "data/dashcam/d2_frames"
REQ = OUT / "d2_requests_h100nvl.jsonl"
META = OUT / "d2_run_meta_h100nvl.json"
TRACE = OUT / "prompt_trace.txt"
X.META_PATH = META
X.CURRENT = Path("logs/d2_current.json")
GPU_UUID = os.environ.get("CLEAN_GPU_UUID", "GPU-4f1d7e47-e769-a289-4860-e71c0d97267c")
HEADER = "The following are 9 consecutive dashcam frames covering 3 seconds, oldest first."
QUERY = ("Is a collision or near-collision involving the camera vehicle happening or about to happen? "
         "Answer only Yes or No.")
GEN = dict(temperature=0.0, max_tokens=8, seed=0, logprobs=True, top_logprobs=20)
FLAGS = ["--limit-mm-per-prompt", json.dumps({"image": 9, "video": 0}), "--mm-processor-cache-gb", "0",
         "--host", "127.0.0.1"]
SIZES = {"native": (1280, 720), "small": (768, 432)}
N_GREY = 100
CONC = 8
ATTEMPTS = 3        # first try + up to 2 automatic retries on client transport errors (user rule 2026-11-04)
TRANSPORT = ("ReadError", "RemoteProtocolError", "ConnectError", "WriteError", "ReadTimeout", "ConnectTimeout", "PoolTimeout", "WriteTimeout", "CloseError")
SRV_ERR = ("ERROR", "Traceback", "Exception", "out of memory", "CUDA error", "OutOfMemory")


def gpu_pids():
    import subprocess
    out = subprocess.run(["nvidia-smi", "--query-compute-apps=gpu_uuid,pid", "--format=csv,noheader"],
                         capture_output=True, text=True).stdout
    return [int(l.split(", ")[1]) for l in out.strip().splitlines() if l.startswith(GPU_UUID)]


X.gpu3_pids = gpu_pids


def grey_png(res):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", SIZES[res], (128, 128, 128)).save(buf, format="PNG")
    return buf.getvalue()


def body(req, res, model, grey=None, token_ids=False):
    content = [{"type": "text", "text": HEADER}]
    hashes = []
    for k, key in enumerate(req["frame_keys"] if grey is None else range(9)):
        if grey is None:
            b = (FR / res / req["file_name"].replace(".mp4", "") / f"{key}.png").read_bytes()
            h = hashlib.sha256(b).hexdigest()
            assert h == req[f"{res}_sha256"][k], (req["request_id"], res, k)
        else:
            b, h = grey, hashlib.sha256(grey).hexdigest()
        hashes.append(h)
        content.append({"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(b).decode()}})
    content.append({"type": "text", "text": QUERY})
    bd = dict(model=model, messages=[{"role": "user", "content": content}], stream=False, **GEN)
    if token_ids:
        bd["return_token_ids"] = True
    return bd, hashes


def yes_no(lp_content):
    """P(Yes) normalised over Yes/No variants (case-insensitive, whitespace-stripped) at the first generated token."""
    if not lp_content:
        return None, None, None
    top = lp_content[0]["top_logprobs"]
    import math
    y = sum(math.exp(t["logprob"]) for t in top if t["token"].strip().lower() == "yes")
    n = sum(math.exp(t["logprob"]) for t in top if t["token"].strip().lower() == "no")
    if y + n == 0:
        return None, y, n
    return y / (y + n), y, n


async def send(c, req, res, model, sem, grey=None, rep=None):
    async with sem:
        b, hashes = await asyncio.to_thread(body, req, res, model, grey)
        for attempt in range(1, ATTEMPTS + 1):
            rec = await send_once(c, b, hashes, req, res, model, grey, rep, attempt)
            if rec["error"] and rec["error"].split(":")[0] in TRANSPORT and attempt < ATTEMPTS:
                X.log(f"D2 transport error {rec['request_id']} {res} attempt {attempt} — retry")
                continue
            return rec


async def send_once(c, b, hashes, req, res, model, grey, rep, attempt):
    if True:
        rid = req["request_id"] if grey is None else f"GREY_{res}_{rep:03d}"
        t0 = time.time()
        err, j = None, None
        try:
            r = await c.post(f"{X.BASE}/v1/chat/completions", json=b)
            j = r.json()
            if r.status_code != 200 or "choices" not in j:
                err = f"HTTP {r.status_code}: {str(j)[:300]}"
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {e}"
        text, lp, u, fin = "", None, {}, None
        if not err:
            ch = j["choices"][0]
            text = ch["message"].get("content") or ""
            lp = (ch.get("logprobs") or {}).get("content")
            u = j.get("usage") or {}
            fin = ch.get("finish_reason")
        p, y, n = yes_no(lp)
        rec = dict(model=model, res=res, request_id=rid, grey=grey is not None,
                   file_name=None if grey is not None else req["file_name"],
                   offset=None if grey is not None else req["offset"], gt=None if grey is not None else req["gt"],
                   label=None if grey is not None else req["label"], scene=None if grey is not None else req["scene"],
                   text=text, first_token=lp[0]["token"] if lp else None, p_yes=p, mass_yes=y, mass_no=n,
                   neither=p is None and not err, said_yes=text.strip().lower().startswith("yes"),
                   prompt_tokens=u.get("prompt_tokens"), completion_tokens=u.get("completion_tokens"),
                   finish_reason=fin, frame_sha256=hashes, error=err, attempt=attempt, at=datetime.now().isoformat(),
                   wall_s=round(time.time() - t0, 3))
        with open(REQ, "a") as f:
            f.write(json.dumps(rec) + "\n")
        return rec


async def trace(model, reqs):
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(X.snapshot(model))
    req = reqs[0]
    b, _ = body(req, "small", model, token_ids=True)
    async with httpx.AsyncClient(timeout=None) as c:
        r = (await c.post(f"{X.BASE}/v1/chat/completions", json=b)).json()
    ids = r["prompt_token_ids"]
    pieces, prev, n = [], None, 0
    for t in ids:
        s = tok.decode([t])
        is_pad = s in ("<|image_pad|>",)
        if is_pad and s == prev:
            n += 1
            continue
        if prev is not None:
            pieces.append(prev if n == 1 else f"{prev}×{n}")
        prev, n = s, 1
    pieces.append(prev if n == 1 else f"{prev}×{n}")
    text = "".join(pieces)
    nonimg = re.sub(r"<\|image_pad\|>×\d+", "", text)
    digits = sorted(set(re.findall(r"\d", nonimg.replace(HEADER, ""))))
    ok = not digits and req["file_name"].replace(".mp4", "") not in text
    TRACE.write_text(f"# StudyD2-nexar: one complete prompt as tokenised by the server (model {model}, SMALL, "
                     f"request {req['request_id']}; image pads collapsed as <|image_pad|>×N)\n"
                     f"# prompt_tokens {r['usage']['prompt_tokens']}; digits outside the header: {digits}; "
                     f"no-absolute-time check {'PASSED' if ok else 'FAILED'}\n\n{text}")
    m = X.meta_load()
    m["prompt_trace"] = dict(request_id=req["request_id"], prompt_tokens=r["usage"]["prompt_tokens"],
                             digits_outside_header=digits, passed=ok)
    X.meta_save(m)
    X.log(f"prompt trace: {'PASSED' if ok else 'FAILED'} digits {digits}")
    if not ok:
        raise SystemExit("prompt contains time / name information — STOP")


async def run(model, reqs):
    have = set()
    if REQ.exists():
        have = {(r["model"], r["res"], r["request_id"]) for r in map(json.loads, open(REQ)) if not r["error"]}
    sem = asyncio.Semaphore(CONC)
    async with httpx.AsyncClient(timeout=None) as c:
        for res in ("small", "native"):
            todo = [q for q in reqs if (model, res, q["request_id"]) not in have]
            X.log(f"D2 {model} {res}: {len(todo)} to run")
            await asyncio.gather(*(send(c, q, res, model, sem) for q in todo))
            g = grey_png(res)
            gt = [k for k in range(N_GREY) if (model, res, f"GREY_{res}_{k:03d}") not in have]
            await asyncio.gather(*(send(c, reqs[0], res, model, sem, grey=g, rep=k) for k in gt))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", choices=["4BI", "32BI"], required=True)
    a = ap.parse_args()
    reqs = [json.loads(l) for l in open(MAN)]
    assert len(reqs) == 1050 and all(r["last_pts_le_end"] for r in reqs)
    busy = gpu_pids()
    if busy:
        raise SystemExit(f"GPU 2 not idle before server start: pids {busy} — STOP")
    srv = X.Server(a.model, FLAGS)
    try:
        info = srv.start()
        import torch
        import vllm
        m = X.meta_load()
        m["stack"] = dict(venv=sys.prefix, vllm=vllm.__version__, torch=torch.__version__, gpu_uuid=GPU_UUID,
                          flags=FLAGS, gen=GEN, header=HEADER, query=QUERY)
        m.setdefault("servers", []).append(dict(model=a.model, started=datetime.now().isoformat(), **info))
        X.meta_save(m)
        if not X.meta_load().get("prompt_trace"):
            asyncio.run(trace(a.model, reqs))
        asyncio.run(run(a.model, reqs))
    finally:
        srv.stop()
    allr = [json.loads(l) for l in open(REQ) if f'"model": "{a.model}"' in l]
    okk = {(r["res"], r["request_id"]) for r in allr if not r["error"]}
    err = len({(r["res"], r["request_id"]) for r in allr} - okk)
    rs = [r for r in allr if not r["error"]]
    se = [l.strip()[:300] for l in srv.logpath.read_text(errors="replace").splitlines() if any(k in l for k in SRV_ERR)]
    if se:
        raise SystemExit(f"D2 {a.model}: server log error lines ({len(se)}) — STOP: {se[0]}")
    nei = sum(bool(r["neither"]) for r in rs)
    X.log(f"D2 {a.model}: {len(rs)} rows, {err} errors, neither-yes-nor-no {nei}")
    from _provenance import stamp
    m = X.meta_load()
    m.setdefault("_provenance", []).append(stamp(script="d2_infer_vllm.py", model=a.model, device=f"{X.DEV}_gpu2",
                                                 n=len(rs), args=a))
    m.setdefault("neither_rate", {})[a.model] = nei / max(1, len(rs))
    X.meta_save(m)
    if err > 0.01 * len(rs):
        raise SystemExit(f"D2 {a.model}: {err} errors > 1 % — STOP")
    if nei > 0.01 * len(rs):
        raise SystemExit(f"D2 {a.model}: neither Yes nor No in {nei}/{len(rs)} > 1 % — STOP")


if __name__ == "__main__":
    main()
