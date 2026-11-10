"""Shared plumbing for StudyF1-shortwin / StudyF2-summary / StudyF3-latency (vLLM venv; h100nvl GPU 1).

Stack = StudyClean / D-series: study_x_vllm.Server (vLLM 0.31.0, FA3, max_model_len 32768, gmu 0.90, bf16, seed 0,
prefix caching OFF unless a caller adds --enable-prefix-caching, PyTorch-native sampler), pinned 4BI @ebb281ec /
32BI @0cfaf481, --mm-processor-cache-gb 0, --enable-prompt-tokens-details, localhost only, port 8031.
GPU: h100nvl GPU 1 (user decision 2026-11-10). The chain exports CUDA_VISIBLE_DEVICES=<GPU 1 UUID>.
Guards: GPU 1 must hold no process before a server starts; during a run, any GPU-1 process owned by another user is
a STOP (the server is stopped, the job exits non-zero and resumes later from its rows).
"""
import asyncio
import math
import os
import pwd
import re
import subprocess
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
X.PORT = 8031
X.BASE = f"http://127.0.0.1:{X.PORT}"
GPU_UUID = os.environ.get("F_GPU_UUID", "GPU-235c6d2d-40df-9060-e2f8-6524c4928d2d")
GPU_LABEL = "h100nvl GPU 1"
ME = pwd.getpwuid(os.getuid()).pw_name
TRANSPORT = ("ReadError", "RemoteProtocolError", "ConnectError", "WriteError", "ReadTimeout", "ConnectTimeout",
             "PoolTimeout", "WriteTimeout", "CloseError")
SRV_ERR = ("ERROR", "Traceback", "out of memory", "CUDA error", "OutOfMemory")
LETTER = re.compile(r"\b([A-E])\b")
ATTEMPTS = 3          # 1 + 2 retries for client transport errors


def gpu_procs():
    out = subprocess.run(["nvidia-smi", "--query-compute-apps=gpu_uuid,pid,used_memory", "--format=csv,noheader"],
                         capture_output=True, text=True).stdout
    rows = []
    for l in out.strip().splitlines():
        if not l.startswith(GPU_UUID):
            continue
        pid = int(l.split(", ")[1])
        try:
            user = pwd.getpwuid(os.stat(f"/proc/{pid}").st_uid).pw_name
        except (FileNotFoundError, KeyError):
            user = "?"
        rows.append(dict(pid=pid, user=user, mem=l.split(", ")[2]))
    return rows


def gpu_pids():
    return [r["pid"] for r in gpu_procs()]


X.gpu3_pids = gpu_pids            # Server.stop / session_check watch GPU 1


def foreign():
    return [r for r in gpu_procs() if r["user"] != ME]


def require_idle():
    p = gpu_procs()
    if p:
        raise SystemExit(f"GPU 1 not idle before server start: {p} — STOP")


def sm_clock():
    out = subprocess.run(["nvidia-smi", "--id=" + GPU_UUID, "--query-gpu=clocks.sm,utilization.gpu,memory.used",
                          "--format=csv,noheader,nounits"], capture_output=True, text=True).stdout.strip()
    return out


def server_errors(srv):
    if srv is None or not srv.logpath.exists():
        return []
    return [l.strip()[:300] for l in srv.logpath.read_text(errors="replace").splitlines()
            if any(k in l for k in SRV_ERR)]


def parse_letter(text):
    """StudyR1's parser: last standalone A-E in the final 300 characters, else 'X'."""
    hits = LETTER.findall((text or "")[-300:])
    return hits[-1] if hits else "X"


def letter_probs(lp):
    """First generated token's top-20: probability mass per letter A-E (token stripped), renormalised share."""
    if not lp:
        return None
    top = lp[0].get("top_logprobs") or []
    mass = {k: 0.0 for k in "ABCDE"}
    for t in top:
        s = t["token"].strip()
        if s in mass:
            mass[s] += math.exp(t["logprob"])
    return dict(mass=mass, total=sum(mass.values()), first_token=lp[0].get("token"))


async def post(c, body):
    """One non-streaming request with up to 2 retries on client transport errors. Returns (json|None, err, attempts,
    errors_seen)."""
    seen = []
    for attempt in range(1, ATTEMPTS + 1):
        err, j = None, None
        try:
            r = await c.post(f"{X.BASE}/v1/chat/completions", json=body)
            j = r.json()
            if r.status_code != 200 or "choices" not in j:
                err = f"HTTP {r.status_code}: {str(j)[:300]}"
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {e}"
        if err and err.split(":")[0] in TRANSPORT and attempt < ATTEMPTS:
            seen.append(err[:200])
            X.log(f"transport error attempt {attempt} — retry: {err[:120]}")
            continue
        return j, err, attempt, seen


def now():
    return datetime.now().isoformat()


def wait_s(s):
    time.sleep(s)
