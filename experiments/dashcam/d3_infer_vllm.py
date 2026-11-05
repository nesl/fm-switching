#!/usr/bin/env python3
"""StudyD3-nexar inference (vLLM venv; h100nvl GPU 2). ACCURACY ONLY — batched; no latency is reported.

Same stack and request form as StudyD2 (d2_infer_vllm): D-series vLLM 0.31.0 server, prefix caching off,
--mm-processor-cache-gb 0, images <= 9; pinned 4BI @ebb281ec / 32BI @0cfaf481; greedy, max_tokens 8, logprobs top 20,
request seed 0, non-streaming, concurrency 8. One user turn = [header] + N SMALL PNGs oldest first (sha256
re-checked) + [D2's query]. Header per request from the manifest (states N and the span; d3_prepare.header).
Grey control: 100 identical requests per model x N (uniform RGB 128, full-span header). Before the first sweep of a
model, a traced prompt per N (return_token_ids) checks that no digit other than the header's appears.
Transport errors (no HTTP status) retried up to 2 more times, every attempt logged; STOP if > 1 % of requests remain
failed, if the server log shows an error before the requests complete, or if > 1 % lack both Yes and No.
GPU 2 must be idle before the server starts. Resumable.
Usage: d3_infer_vllm.py --model 4BI|32BI [--ns 9,3,1]
"""
import argparse
import asyncio
import base64
import hashlib
import io
import json
import math
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
OUT = Path("results/dashcam/study_d3_nexar")
MAN = OUT / "d3_requests_manifest.jsonl"
FR = Path.home() / "data/dashcam/d3_frames/small"
REQ = OUT / "d3_requests_h100nvl.jsonl"
META = OUT / "d3_run_meta_h100nvl.json"
X.META_PATH = META
X.CURRENT = Path("logs/d3_current.json")
GPU_UUID = os.environ.get("CLEAN_GPU_UUID", "GPU-4f1d7e47-e769-a289-4860-e71c0d97267c")
QUERY = ("Is a collision or near-collision involving the camera vehicle happening or about to happen? "
         "Answer only Yes or No.")
GEN = dict(temperature=0.0, max_tokens=8, seed=0, logprobs=True, top_logprobs=20)
FLAGS = ["--limit-mm-per-prompt", json.dumps({"image": 9, "video": 0}), "--mm-processor-cache-gb", "0",
         "--host", "127.0.0.1"]
CONC, N_GREY, ATTEMPTS = 8, 100, 3
TRANSPORT = ("ReadError", "RemoteProtocolError", "ConnectError", "WriteError", "ReadTimeout", "ConnectTimeout",
             "PoolTimeout", "WriteTimeout", "CloseError")
SRV_ERR = ("ERROR", "Traceback", "Exception", "out of memory", "CUDA error", "OutOfMemory")
SRV = None


def gpu_pids():
    import subprocess
    out = subprocess.run(["nvidia-smi", "--query-compute-apps=gpu_uuid,pid", "--format=csv,noheader"],
                         capture_output=True, text=True).stdout
    return [int(l.split(", ")[1]) for l in out.strip().splitlines() if l.startswith(GPU_UUID)]


X.gpu3_pids = gpu_pids


def grey_png():
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (768, 432), (128, 128, 128)).save(buf, format="PNG")
    return buf.getvalue()


def grey_header(n):
    return ("The following is 1 dashcam frame." if n == 1 else
            f"The following are {n} consecutive dashcam frames covering 3 seconds, oldest first.")


def body(req, model, grey=None, n=None, token_ids=False):
    hdr = req["header"] if grey is None else grey_header(n)
    content = [{"type": "text", "text": hdr}]
    hashes = []
    keys = req["frame_keys"] if grey is None else range(n)
    for k, key in enumerate(keys):
        if grey is None:
            b = (FR / req["file_name"].replace(".mp4", "") / f"{key}.png").read_bytes()
            h = hashlib.sha256(b).hexdigest()
            assert h == req["small_sha256"][k], (req["request_id"], k)
        else:
            b, h = grey, hashlib.sha256(grey).hexdigest()
        hashes.append(h)
        content.append({"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(b).decode()}})
    content.append({"type": "text", "text": QUERY})
    bd = dict(model=model, messages=[{"role": "user", "content": content}], stream=False, **GEN)
    if token_ids:
        bd["return_token_ids"] = True
    return bd, hashes, hdr


def yes_no(lp):
    if not lp:
        return None, None, None
    top = lp[0]["top_logprobs"]
    y = sum(math.exp(t["logprob"]) for t in top if t["token"].strip().lower() == "yes")
    n = sum(math.exp(t["logprob"]) for t in top if t["token"].strip().lower() == "no")
    return (None if y + n == 0 else y / (y + n)), y, n


async def send_once(c, b, hashes, hdr, req, model, n, grey, rep, attempt):
    rid = req["request_id"] if grey is None else f"GREY_N{n}_{rep:03d}"
    err, j = None, None
    t0 = time.time()
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
    p, y, nn = yes_no(lp)
    rec = dict(model=model, n=n, request_id=rid, grey=grey is not None, attempt=attempt,
               file_name=None if grey is not None else req["file_name"],
               offset=None if grey is not None else req["offset"], gt=None if grey is not None else req["gt"],
               label=None if grey is not None else req["label"], header=hdr, text=text,
               first_token=lp[0]["token"] if lp else None, p_yes=p, mass_yes=y, mass_no=nn,
               neither=p is None and not err, prompt_tokens=u.get("prompt_tokens"),
               completion_tokens=u.get("completion_tokens"), finish_reason=fin, frame_sha256=hashes, error=err,
               wall_s=round(time.time() - t0, 3), at=datetime.now().isoformat())
    with open(REQ, "a") as f:
        f.write(json.dumps(rec) + "\n")
    return rec


async def send(c, req, model, n, sem, grey=None, rep=None):
    async with sem:
        b, hashes, hdr = await asyncio.to_thread(body, req, model, grey, n)
        for attempt in range(1, ATTEMPTS + 1):
            rec = await send_once(c, b, hashes, hdr, req, model, n, grey, rep, attempt)
            if rec["error"] and rec["error"].split(":")[0] in TRANSPORT and attempt < ATTEMPTS:
                X.log(f"D3 transport error {rec['request_id']} attempt {attempt} — retry")
                continue
            return rec


async def trace(model, reqs, n):
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(X.snapshot(model))
    req = next(r for r in reqs if not r["short_span"])
    b, _, hdr = body(req, model, token_ids=True)
    async with httpx.AsyncClient(timeout=None) as c:
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
    nonimg = re.sub(r"<\|image_pad\|>×\d+", "", text).replace(hdr, "")
    digits = sorted(set(re.findall(r"\d", nonimg)))
    ok = not digits and req["file_name"].replace(".mp4", "") not in text
    p = OUT / f"prompt_trace_N{n}.txt"
    p.write_text(f"# StudyD3-nexar: one complete prompt as tokenised by the server (model {model}, N {n}, request "
                 f"{req['request_id']}; image pads collapsed)\n# prompt_tokens {r['usage']['prompt_tokens']}; "
                 f"digits outside the header: {digits}; no-absolute-time check {'PASSED' if ok else 'FAILED'}\n\n{text}")
    m = X.meta_load()
    m.setdefault("prompt_trace", {})[f"N{n}"] = dict(request_id=req["request_id"], header=hdr,
                                                    prompt_tokens=r["usage"]["prompt_tokens"],
                                                    digits_outside_header=digits, passed=ok)
    X.meta_save(m)
    if not ok:
        raise SystemExit(f"N{n} prompt contains time / name information — STOP")


def server_errors():
    if SRV is None or not SRV.logpath.exists():
        return []
    return [l.strip()[:300] for l in SRV.logpath.read_text(errors="replace").splitlines() if any(k in l for k in SRV_ERR)]


async def run(model, ns, allreqs):
    have = set()
    if REQ.exists():
        have = {(r["model"], r["n"], r["request_id"]) for r in map(json.loads, open(REQ)) if not r["error"]}
    sem = asyncio.Semaphore(CONC)
    g = grey_png()
    m = X.meta_load()
    async with httpx.AsyncClient(timeout=None) as c:
        for n in ns:
            reqs = [r for r in allreqs if r["n"] == n]
            if f"N{n}" not in m.get("prompt_trace", {}):
                await trace(model, reqs, n)
            todo = [q for q in reqs if (model, n, q["request_id"]) not in have]
            X.log(f"D3 {model} N{n}: {len(todo)} to run")
            done_n = 0
            for i in range(0, len(todo), 400):
                await asyncio.gather(*(send(c, q, model, n, sem) for q in todo[i:i + 400]))
                done_n += len(todo[i:i + 400])
                X.log(f"D3 {model} N{n}: {done_n}/{len(todo)}")
                se = server_errors()
                if se:
                    raise SystemExit(f"D3 {model} N{n}: server log error before requests completed — STOP: {se[0]}")
            gt = [k for k in range(N_GREY) if (model, n, f"GREY_N{n}_{k:03d}") not in have]
            await asyncio.gather(*(send(c, reqs[0], model, n, sem, grey=g, rep=k) for k in gt))
            se = server_errors()
            if se:
                raise SystemExit(f"D3 {model} N{n}: server log error before requests completed — STOP: {se[0]}")


def main():
    global SRV
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", choices=["4BI", "32BI"], required=True)
    ap.add_argument("--ns", default="9,3,1")
    a = ap.parse_args()
    ns = [int(x) for x in a.ns.split(",")]
    reqs = [json.loads(l) for l in open(MAN)]
    assert len(reqs) == 18030 and all(r["last_pts_le_end"] for r in reqs)
    if gpu_pids():
        raise SystemExit(f"GPU 2 not idle before server start: {gpu_pids()} — STOP")
    srv = X.Server(a.model, FLAGS)
    SRV = srv
    try:
        info = srv.start()
        import torch
        import vllm
        m = X.meta_load()
        m["stack"] = dict(venv=sys.prefix, vllm=vllm.__version__, torch=torch.__version__, gpu_uuid=GPU_UUID,
                          flags=FLAGS, gen=GEN, query=QUERY, concurrency=CONC)
        m.setdefault("servers", []).append(dict(model=a.model, started=datetime.now().isoformat(), **info))
        X.meta_save(m)
        asyncio.run(run(a.model, ns, reqs))
    finally:
        srv.stop()
    allr = [json.loads(l) for l in open(REQ) if f'"model": "{a.model}"' in l]
    keys = {(r["n"], r["request_id"]) for r in allr}
    ok = {(r["n"], r["request_id"]) for r in allr if not r["error"]}
    failed = len(keys - ok)
    rs = [r for r in allr if not r["error"]]
    nei = sum(bool(r["neither"]) for r in rs)
    retried = sum(1 for r in allr if r["error"])
    X.log(f"D3 {a.model}: {len(rs)} ok rows, {retried} error rows (retried), {failed} still failed, neither {nei}")
    from _provenance import stamp
    m = X.meta_load()
    m.setdefault("_provenance", []).append(stamp(script="d3_infer_vllm.py", model=a.model, device=f"{X.DEV}_gpu2",
                                                 n=len(rs), args=a))
    m.setdefault("summary", {})[a.model] = dict(ok_rows=len(rs), error_rows=retried, still_failed=failed, neither=nei)
    X.meta_save(m)
    if failed > 0.01 * len(keys):
        raise SystemExit(f"D3 {a.model}: {failed} still failed > 1 % — STOP")
    if nei > 0.01 * len(rs):
        raise SystemExit(f"D3 {a.model}: neither Yes nor No in {nei}/{len(rs)} > 1 % — STOP")


if __name__ == "__main__":
    main()
