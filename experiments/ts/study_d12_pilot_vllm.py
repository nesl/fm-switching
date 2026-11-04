#!/usr/bin/env python3
"""StudyD12-pilot (GPU runner, vLLM venv) — 50-item time-series pilot on the D-series vLLM stack, h100nvl GPU 2.

Pre-registered in research/EXPERIMENTS.md (StudyD12-pilot). Replaces the flash pilot of StudyD12-prep.
Stack: study_x_vllm.Server (vLLM 0.31.0, FA3, max_model_len 32768, gmu 0.90, prefix caching OFF) +
--mm-processor-cache-gb 0, images <= 1. Models (pinned): 4BI Qwen3-VL-4B-Instruct @ebb281ec, 32BI @0cfaf481.
Greedy, max_tokens 512, concurrency 8, request seed 0.
Items / prompts: results/ts/study_d12_prep/manifest.json, verbatim (`prompt_text`, `prompt_plot`); PLOT arm sends the
committed PNG (plots/<dataset>/<item>.png) as the first content part, then the prompt (the prep's token-count layout).
Arms: wisdm/text, wisdm/plot, mitdb/text, mitdb/plot, stark/text (no STARK plot). Resumable; STOP on > 1 % errors.
Usage: study_d12_pilot_vllm.py --model 4BI|32BI
"""
import argparse
import asyncio
import base64
import json
import os
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
PREP = Path("results/ts/study_d12_prep")
OUT = Path("results/ts/study_d12_pilot")
REQ = OUT / "study_d12_pilot_requests_h100nvl.jsonl"
META = OUT / "study_d12_pilot_run_meta_h100nvl.json"
X.META_PATH = META
X.CURRENT = Path("logs/study_d12_pilot_current.json")
GPU_UUID = os.environ.get("CLEAN_GPU_UUID", "GPU-4f1d7e47-e769-a289-4860-e71c0d97267c")
FLAGS = ["--limit-mm-per-prompt", json.dumps({"image": 1, "video": 0}), "--mm-processor-cache-gb", "0",
         "--host", "127.0.0.1"]
GEN = dict(temperature=0.0, max_tokens=512, seed=0)
ARMS = [("wisdm", "text"), ("wisdm", "plot"), ("mitdb", "text"), ("mitdb", "plot"), ("stark", "text")]
CONC = 8


def gpu_pids():
    import subprocess
    out = subprocess.run(["nvidia-smi", "--query-compute-apps=gpu_uuid,pid", "--format=csv,noheader"],
                         capture_output=True, text=True).stdout
    return [int(l.split(", ")[1]) for l in out.strip().splitlines() if l.startswith(GPU_UUID)]


X.gpu3_pids = gpu_pids


def body(it, arm, model):
    prompt = it["prompt_plot"] if arm == "plot" else it["prompt_text"]
    content = []
    if arm == "plot":
        b64 = base64.b64encode((PREP / it["plot_png"]).read_bytes()).decode()
        content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}})
    content.append({"type": "text", "text": prompt})
    return dict(model=model, messages=[{"role": "user", "content": content}], stream=True,
                stream_options={"include_usage": True}, **GEN)


async def send(c, it, ds, arm, model, sem):
    async with sem:
        b = body(it, arm, model)
        t0 = time.time()
        first, chunks, usage, finish, err = None, [], None, None, None
        try:
            async with c.stream("POST", f"{X.BASE}/v1/chat/completions", json=b) as r:
                if r.status_code != 200:
                    err = f"HTTP {r.status_code}: {(await r.aread())[:300]!r}"
                else:
                    async for line in r.aiter_lines():
                        if not line.startswith("data: ") or line == "data: [DONE]":
                            continue
                        j = json.loads(line[6:])
                        if j.get("usage"):
                            usage = j["usage"]
                        for ch in j.get("choices", []):
                            d = (ch.get("delta") or {}).get("content")
                            if d:
                                first = first or time.time()
                                chunks.append(d)
                            if ch.get("finish_reason"):
                                finish = ch["finish_reason"]
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {e}"
        u = usage or {}
        rec = dict(model=model, dataset=ds, arm=arm, item_id=it["item_id"], text="".join(chunks), error=err,
                   finish_reason=finish, prompt_tokens=u.get("prompt_tokens"),
                   completion_tokens=u.get("completion_tokens"),
                   prep_prompt_tokens_4b=(it.get("prompt_tokens") or {}).get(arm),
                   latency_s=round(time.time() - t0, 3), ttft_s=round(first - t0, 3) if first else None,
                   at=datetime.now().isoformat())
        with open(REQ, "a") as f:
            f.write(json.dumps(rec) + "\n")
        return rec


async def run(model, man):
    have = set()
    if REQ.exists():
        have = {(r["model"], r["dataset"], r["arm"], r["item_id"]) for r in map(json.loads, open(REQ)) if not r["error"]}
    jobs = [(it, ds, arm) for ds, arm in ARMS for it in man[ds] if (model, ds, arm, it["item_id"]) not in have]
    X.log(f"D12 pilot {model}: {len(jobs)} requests to run (conc {CONC})")
    sem = asyncio.Semaphore(CONC)
    async with httpx.AsyncClient(timeout=None) as c:
        out = await asyncio.gather(*(send(c, it, ds, arm, model, sem) for it, ds, arm in jobs))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", choices=["4BI", "32BI"], required=True)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    man = json.load(open(PREP / "manifest.json"))
    assert all(len(man[d]) == 50 for d in ("wisdm", "mitdb", "stark"))
    srv = X.Server(a.model, FLAGS)
    try:
        info = srv.start()
        import torch
        import vllm
        m = X.meta_load()
        m["stack"] = dict(venv=sys.prefix, vllm=vllm.__version__, torch=torch.__version__, gpu_uuid=GPU_UUID,
                          flags=FLAGS, gen=GEN)
        m.setdefault("servers", []).append(dict(model=a.model, started=datetime.now().isoformat(), **info))
        X.meta_save(m)
        asyncio.run(run(a.model, man))
    finally:
        srv.stop()
    rs = [json.loads(l) for l in open(REQ)]
    rs = [r for r in rs if r["model"] == a.model]
    err = sum(bool(r["error"]) for r in rs)
    X.log(f"D12 pilot {a.model}: {len(rs)} rows, {err} errors")
    from _provenance import stamp
    m = X.meta_load()
    m.setdefault("_provenance", []).append(stamp(script="study_d12_pilot_vllm.py", model=a.model,
                                                 device=f"{X.DEV}_gpu2", n=len(rs), args=a))
    X.meta_save(m)
    if err > 0.01 * len(rs):
        raise SystemExit(f"D12 pilot {a.model}: {err} errors > 1 % — STOP")


if __name__ == "__main__":
    main()
