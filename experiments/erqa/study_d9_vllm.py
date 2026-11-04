#!/usr/bin/env python3
"""StudyD9 — 32B image Thinking vs Instruct on one matched vLLM stack (ERQA 400 + MV-RoboBench 401).

Stack: StudyClean's server (study_x_vllm.Server: vLLM 0.31.0, FA3, max_model_len 32768, gmu 0.90, prefix caching OFF)
+ --mm-processor-cache-gb 0. Inputs: study_d9_inputs.py (earlier arms' prompts, images pre-resized exactly as the HF
arms did; prompt length checked per request against the HF processor count).
Arms:  --arm I           Qwen3-VL-32B-Instruct @0cfaf481, greedy, max_tokens 512 (one run)
       --arm T --seed s  Qwen3-VL-32B-Thinking @7edd10ff, model-card VL sampling (temperature 1.0, top_p 0.95,
                         top_k 20, repetition 1.0, presence 0.0, min_p 0), max_tokens 16384; request seed = s for
                         every request (R1's per-request seed convention); s in {0, 1}
Concurrency 8, closed loop. Scoring: the earlier arms' rules (answer = text after </think> if closed else the full
text; study_r_erqa.extract_letter A–D for ERQA, study_s2 extract_letter A–E for MV-RoboBench).
Resumable (rows without error are skipped). STOP: > 1 % errors in a run.
"""
import argparse
import asyncio
import base64
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

OUT = Path("results/erqa/study_d9")
MAN = OUT / "study_d9_inputs_manifest.jsonl"
REQ = OUT / f"study_d9_requests_{X.DEV}.jsonl"
META = OUT / f"study_d9_run_meta_{X.DEV}.json"
X.META_PATH = META
X.CURRENT = Path("logs/study_d9_current.json")
GPU_UUID = os.environ.get("CLEAN_GPU_UUID", "GPU-4f1d7e47-e769-a289-4860-e71c0d97267c")
CONC = 8
INSTRUCT = dict(temperature=0.0, max_tokens=512)
THINKING = dict(temperature=1.0, top_p=0.95, top_k=20, repetition_penalty=1.0, presence_penalty=0.0, min_p=0.0,
                max_tokens=16384)
END = "</think>"


def gpu_pids():
    import subprocess
    out = subprocess.run(["nvidia-smi", "--query-compute-apps=gpu_uuid,pid", "--format=csv,noheader"],
                         capture_output=True, text=True).stdout
    return [int(l.split(", ")[1]) for l in out.strip().splitlines() if l.startswith(GPU_UUID)]


X.gpu3_pids = gpu_pids


def extract_letter(text, letters):
    """study_r_erqa.extract_letter (letters A–D) / study_s2 extract_letter (A–E), verbatim logic."""
    t = text.strip()
    if t and t[0] in letters and (len(t) == 1 or t[1] in '.\n ):,'):
        return t[0], "direct"
    m = re.search(rf'(?:answer is|answer:|the answer)\s*[:\s]*([{letters}])\b', t, re.IGNORECASE)
    if m:
        return m.group(1).upper(), "extracted"
    m = re.search(rf'\b([{letters}])\b', t[-80:])
    if m:
        return m.group(1).upper(), "last_found"
    return None, "no_letter"


def build(row, model, params, seed):
    content = []
    for c in row["content"]:
        if c["type"] == "text":
            content.append({"type": "text", "text": c["text"]})
        else:
            b64 = base64.b64encode(Path(c["path"]).read_bytes()).decode()
            content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}})
    b = dict(model=model, messages=[{"role": "user", "content": content}], stream=True,
             stream_options={"include_usage": True}, **params)
    if seed is not None:
        b["seed"] = seed
    return b


async def send(client, row, arm, seed, model, params, sem):
    async with sem:
        b = await asyncio.to_thread(build, row, model, params, seed)
        X.CURRENT.write_text(json.dumps(dict(arm=arm, seed=seed, bench=row["bench"], qid=row["qid"])))
        t0 = time.time()
        first, chunks, usage, finish, err = None, [], None, None, None
        try:
            async with client.stream("POST", f"{X.BASE}/v1/chat/completions", json=b) as r:
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
        full = "".join(chunks)
        thinking = arm == "T"
        closed = (END in full) if thinking else None
        answer = full.split(END, 1)[1].strip() if closed else full.strip()
        pred, status = extract_letter(answer, row["letters"])
        u = usage or {}
        rec = dict(arm=arm, seed=seed, bench=row["bench"], qid=row["qid"], category=row["category"],
                   correct_letter=row["correct_letter"], pred=pred, parse_status=status,
                   correct=pred == row["correct_letter"], think_closed=closed, answer_text=answer, raw_output=full,
                   empty_answer=not answer.strip(), finish_reason=finish,
                   runaway=bool(thinking and (finish == "length" or not closed)),
                   prompt_tokens=u.get("prompt_tokens"), expected_prompt_tokens=row["expected_prompt_tokens"],
                   completion_tokens=u.get("completion_tokens"), ttft_s=round(first - t0, 3) if first else None,
                   latency_s=round(t1 - t0, 3), params={k: v for k, v in params.items()}, error=err,
                   at=datetime.now().isoformat())
        with open(REQ, "a") as f:
            f.write(json.dumps(rec) + "\n")
        return rec


async def run(arm, seed, model, params, rows):
    have = set()
    if REQ.exists():
        have = {(r["bench"], r["qid"]) for r in map(json.loads, open(REQ))
                if r["arm"] == arm and r["seed"] == seed and not r["error"]}
    todo = [r for r in rows if (r["bench"], r["qid"]) not in have]
    X.log(f"D9 arm {arm} seed {seed}: {len(todo)} to run (conc {CONC})")
    sem = asyncio.Semaphore(CONC)
    t0, out = time.time(), []
    async with httpx.AsyncClient(timeout=None) as c:
        tasks = [asyncio.create_task(send(c, r, arm, seed, model, params, sem)) for r in todo]
        for k, t in enumerate(asyncio.as_completed(tasks), 1):
            out.append(await t)
            if k % 50 == 0:
                X.log(f"D9 arm {arm} seed {seed}: {k}/{len(todo)} in {(time.time() - t0) / 60:.1f} min; "
                      f"errors {sum(bool(o['error']) for o in out)}")
    return out


def check(arm, seed):
    rs = {}
    errs = 0
    for r in map(json.loads, open(REQ)):
        if r["arm"] == arm and r["seed"] == seed:
            if r["error"]:
                errs += 1
            else:
                rs[(r["bench"], r["qid"])] = r
    tok = sum(r["prompt_tokens"] == r["expected_prompt_tokens"] for r in rs.values())
    res = dict(arm=arm, seed=seed, n=len(rs), errors_logged=errs, prompt_tokens_equal_hf=tok,
               acc=sum(r["correct"] for r in rs.values()) / max(1, len(rs)),
               runaways=sum(r["runaway"] for r in rs.values()), empty=sum(r["empty_answer"] for r in rs.values()))
    m = X.meta_load()
    m.setdefault("checks", {})[f"{arm}_s{seed}"] = res
    X.meta_save(m)
    X.log(f"D9 CHECK {res}")
    if errs > 0.01 * 801:
        raise SystemExit(f"D9 {arm} s{seed}: {errs} errors > 1 % — STOP")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", choices=["I", "T"], required=True)
    ap.add_argument("--seeds", default="")
    a = ap.parse_args()
    rows = [json.loads(l) for l in open(MAN)]
    assert len(rows) == 801
    nimg = max(sum(c["type"] == "image" for c in r["content"]) for r in rows)
    key = "32BI" if a.arm == "I" else "32BT"
    flags = ["--limit-mm-per-prompt", json.dumps({"image": nimg, "video": 0}), "--mm-processor-cache-gb", "0",
             "--host", "127.0.0.1"]
    seeds = [None] if a.arm == "I" else [int(s) for s in a.seeds.split(",")]
    params = INSTRUCT if a.arm == "I" else THINKING
    srv = X.Server(key, flags)
    try:
        info = srv.start()
        import torch
        import vllm
        m = X.meta_load()
        m["stack"] = dict(venv=sys.prefix, vllm=vllm.__version__, torch=torch.__version__, cuda=torch.version.cuda,
                          gpu_uuid=GPU_UUID)
        m.setdefault("servers", []).append(dict(arm=a.arm, seeds=seeds, started=datetime.now().isoformat(), **info))
        X.meta_save(m)
        for s in seeds:
            asyncio.run(run(a.arm, s, key, params, rows))
            check(a.arm, s)
    finally:
        srv.stop()
    from _provenance import stamp
    m = X.meta_load()
    m.setdefault("_provenance", []).append(stamp(script="study_d9_vllm.py", model=key, device=f"{X.DEV}_gpu2",
                                                 n=801, args=a))
    X.meta_save(m)


if __name__ == "__main__":
    main()
