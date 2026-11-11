#!/usr/bin/env python3
"""StudyE7-d2-4b Job B — 4B single-request latency on RH4 D2, EXCLUSIVE (vLLM venv; h100nvl GPU 2). F3's protocol.

Runs only when nothing else of ours runs on the host. A monitor logs, at start, every 30 s and at end: every GPU
process on the host with owner and memory, GPU 2's UUID / SM clock / utilisation, CPU use per user, and any process of
ours outside this job's process tree (python / vllm / ffmpeg / torch, or > 20 % CPU) -> VOID and STOP.
One request at a time, localhost, streaming with usage; the body is serialised to bytes BEFORE the clock starts;
TTFT = first streamed content chunk; total = last byte; max_tokens 8, greedy (RH4 body, seed 42).
After each server load the first request (outside the cell's sample) is sent and discarded.
  b1  4B D2 COLD (RH4 image flags, prefix caching OFF, processor cache off): F3 cell c's 60 questions (6 equal-width
      bins of RH4 D2 prompt tokens x 10, seed 0) -> paired with F3's 32B c_D2 rows. cached_tokens must be 0 (STOP).
  b2  4B D2 WARM (same + --enable-prefix-caching): F3 cell d's 10 sessions (videos, seed 0), each session's
      questions in time order (append-only: each request's images extend the previous one's), same warm-up session
      -> paired with F3's 32B d_D2_WARM rows. Labelled WARM.
Rows -> results/sember/study_e7/e7_latency_requests_h100nvl.jsonl; monitor -> e7_latency_monitor_h100nvl.jsonl.
Resumable per group (a partly run group is re-run from its start; its old rows are marked superseded).
"""
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
import study_e7_infer_vllm as A  # noqa: E402  (RH4 + study_f_common stack; GPU from F_GPU_UUID)

F, X, RH, W3 = A.F, A.X, A.RH, A.W3
OUT = REPO / "results/sember/study_e7"
REQ = OUT / "e7_latency_requests_h100nvl.jsonl"
MON = OUT / "e7_latency_monitor_h100nvl.jsonl"
META = OUT / "e7_latency_run_meta_h100nvl.json"
X.META_PATH = META
X.CURRENT = REPO / "logs/e7_latency_current.json"
GEN = dict(temperature=0.0, max_tokens=8)
CACHE_OFF = ["--mm-processor-cache-gb", "0", "--enable-prompt-tokens-details"]
COLD_FLAGS = W3.IMAGE_FLAGS + CACHE_OFF
WARM_FLAGS = COLD_FLAGS + ["--enable-prefix-caching"]
GROUPS = [("b1_4BI", COLD_FLAGS), ("b2_4BI", WARM_FLAGS)]
OURS_PAT = ("python", "vllm", "ffmpeg", "torch")
SAFE_CMDS = ("claude", "node", "sshd", "bash", "tmux", "systemd", "sd-pam", "pipewire", "dbus", "ps ", "nvidia-smi",
             "sleep", "sh ", "code-server", "/bin/sh", "tail", "grep", "awk", "cat")
VOID = threading.Event()
STOP = threading.Event()


def tree(root):
    out = subprocess.run(["ps", "-eo", "pid=,ppid="], capture_output=True, text=True).stdout.split("\n")
    kids = {}
    for l in out:
        if l.strip():
            p, pp = map(int, l.split())
            kids.setdefault(pp, []).append(p)
    seen, st = set(), [root]
    while st:
        p = st.pop()
        if p not in seen:
            seen.add(p)
            st += kids.get(p, [])
    return seen


def snapshot(tag):
    procs = subprocess.run(["nvidia-smi", "--query-compute-apps=gpu_uuid,pid,used_memory", "--format=csv,noheader"],
                           capture_output=True, text=True).stdout.strip().splitlines()
    gpu = []
    for l in procs:
        u, pid, mem = l.split(", ")
        user = subprocess.run(["ps", "-o", "user=", "-p", pid], capture_output=True, text=True).stdout.strip() or "?"
        gpu.append(dict(gpu_uuid=u, pid=int(pid), user=user, mem=mem))
    ps = subprocess.run(["ps", "-eo", "user=,pid=,pcpu=,args="], capture_output=True, text=True).stdout.splitlines()
    cpu_by_user, ours_outside = {}, []
    mine = tree(os.getpid())
    for l in ps:
        parts = l.split(None, 3)
        if len(parts) < 4:
            continue
        user, pid, pcpu, args = parts[0], int(parts[1]), float(parts[2]), parts[3]
        cpu_by_user[user] = round(cpu_by_user.get(user, 0.0) + pcpu, 1)
        if user == F.ME and pid not in mine:
            low = args.lower()
            if (any(k in low for k in OURS_PAT) or pcpu > 20) and not any(low.startswith(s) or f"/{s}" in low.split()[0]
                                                                          for s in SAFE_CMDS):
                ours_outside.append(dict(pid=pid, pcpu=pcpu, args=args[:160]))
    rec = dict(tag=tag, at=F.now(), gpu_uuid=F.GPU_UUID, gpu_sm_util_mem=F.sm_clock(), gpu_procs=gpu,
               cpu_pct_by_user=dict(sorted(cpu_by_user.items(), key=lambda kv: -kv[1])[:8]),
               ours_outside_job=ours_outside, foreign_on_gpu=F.foreign())
    with open(MON, "a") as f:
        f.write(json.dumps(rec) + "\n")
    return rec


def monitor():
    while not STOP.wait(30):
        rec = snapshot("30s")
        if rec["ours_outside_job"]:
            X.log(f"!!! process of ours outside the job: {rec['ours_outside_job'][:3]} — VOID")
            VOID.set()
        if rec["foreign_on_gpu"]:
            X.log(f"!!! foreign process on GPU 2: {rec['foreign_on_gpu']} — STOP")
            VOID.set()


def timed(body, meta):
    if VOID.is_set():
        raise SystemExit("run VOID (overlap or foreign GPU process) — STOP")
    body = dict(body, stream=True, stream_options={"include_usage": True}, **GEN)
    body.pop("logprobs", None)
    body.pop("top_logprobs", None)
    bb = json.dumps(body).encode()
    sm0 = F.sm_clock()
    err, ttft, usage, text, fin = None, None, {}, "", None
    t0 = time.perf_counter()
    try:
        with httpx.Client(timeout=None) as c:
            with c.stream("POST", f"{X.BASE}/v1/chat/completions", content=bb,
                          headers={"content-type": "application/json"}) as r:
                if r.status_code != 200:
                    err = f"HTTP {r.status_code}: {r.read()[:300]!r}"
                else:
                    for line in r.iter_lines():
                        if not line.startswith("data: ") or line == "data: [DONE]":
                            continue
                        j = json.loads(line[6:])
                        if j.get("usage"):
                            usage = j["usage"]
                        for ch in j.get("choices", []):
                            d = (ch.get("delta") or {}).get("content")
                            if d:
                                if ttft is None:
                                    ttft = time.perf_counter() - t0
                                text += d
                            if ch.get("finish_reason"):
                                fin = ch["finish_reason"]
    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {e}"
    total = time.perf_counter() - t0
    rec = dict(meta, ttft_s=None if ttft is None else round(ttft, 5), total_s=round(total, 5),
               prompt_tokens=usage.get("prompt_tokens"), completion_tokens=usage.get("completion_tokens"),
               cached_tokens=(usage.get("prompt_tokens_details") or {}).get("cached_tokens"), text=text,
               finish_reason=fin, body_bytes=len(bb), sm_at_send=sm0, error=err, at=F.now())
    with open(REQ, "a") as f:
        f.write(json.dumps(rec) + "\n")
    return rec


def items(group, p, rh4):
    def cb(q):
        b, _, n = RH.body(dict(rh4[q]), "D2", "4BI", dict(temperature=0.0))
        return b, dict(n_images=n)
    out = []
    if group.startswith("b1"):
        sel = {q for q, _ in p["c"]}
        wq = next(q for q in sorted(rh4) if q not in sel and not rh4[q]["over_context"])
        out.append(("b1", "discard", wq, {}, lambda q=wq: cb(q)))
        out += [("b1_D2", "cold", q, dict(bin=i), lambda q=q: cb(q)) for q, i in p["c"]]
    else:
        wv = p["d_warmup_session"]
        wq = min((q for q in rh4 if rh4[q]["video_id"] == wv), key=lambda q: float(rh4[q]["question_time"]))
        out.append(("b2", "discard", wq, {}, lambda q=wq: cb(q)))
        for si, (v, qs) in enumerate(p["d"]):
            for j, q in enumerate(qs):
                out.append(("b2_D2_WARM", "WARM", q, dict(session=si, video_id=v, pos=j), lambda q=q: cb(q)))
    return out


def run_group(g, flags, p, rh4):
    tag = f"group_{g}"
    if X.is_done(tag):
        X.log(f"{g}: done — skip")
        return
    if REQ.exists():
        rows = [json.loads(l) for l in open(REQ)]
        if any(r["group"] == g for r in rows):
            with open(REQ, "w") as f:
                for r in rows:
                    if r["group"] == g:
                        r["superseded"] = True
                    f.write(json.dumps(r) + "\n")
    F.require_idle()
    srv = X.Server("4BI", flags)
    try:
        info = srv.start()
        m = X.meta_load()
        m.setdefault("servers", []).append(dict(group=g, started=F.now(), **info))
        X.meta_save(m)
        snapshot(f"server_up_{g}")
        its = items(g, p, rh4)
        for k, (cell, label, q, extra, fn) in enumerate(its):
            b, bmeta = fn()
            rec = timed(b, dict(group=g, model="4BI", cell=cell, label=label, discarded=label == "discard",
                                question_id=q, prefix_caching="--enable-prefix-caching" in flags, fmt="images",
                                **extra, **bmeta))
            if rec["error"]:
                X.log(f"{g} {cell} {q[:10]}: ERROR {rec['error'][:200]}")
            if label == "cold" and rec["cached_tokens"]:
                raise SystemExit(f"{g}: cold request served {rec['cached_tokens']} cached tokens — STOP")
            if k % 10 == 0:
                X.log(f"{g}: {k + 1}/{len(its)} {cell} ttft {rec['ttft_s']} tok {rec['prompt_tokens']} "
                      f"cached {rec['cached_tokens']}")
        se = F.server_errors(srv)
        if se:
            raise SystemExit(f"{g}: server log error — STOP: {se[0]}")
    finally:
        srv.stop()
    rows = [json.loads(l) for l in open(REQ)]
    rows = [r for r in rows if r["group"] == g and not r.get("superseded")]
    err = sum(bool(r["error"]) for r in rows)
    if err > 0.01 * len(rows):
        raise SystemExit(f"{g}: {err}/{len(rows)} errors > 1 % — STOP")
    X.mark_done(tag, rows=len(rows), errors=err)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    p = json.loads((REPO / "results/cost/study_f3/f3_plan.json").read_text())
    allrows, _ = RH.manifest()
    rh4 = {q: r for (q, cell), r in allrows.items() if cell == "D2"}
    start = snapshot("start")
    if start["ours_outside_job"]:
        raise SystemExit(f"not exclusive at start: {start['ours_outside_job']} — STOP")
    m = X.meta_load()
    import torch
    import vllm
    m["stack"] = dict(venv=sys.prefix, vllm=vllm.__version__, torch=torch.__version__, gpu=F.GPU_LABEL,
                      gpu_uuid=F.GPU_UUID, gen=GEN, plan="results/cost/study_f3/f3_plan.json cells c and d",
                      protocol="one request at a time, localhost, streaming, bodies serialised before the clock, "
                               "first request after each load discarded")
    X.meta_save(m)
    th = threading.Thread(target=monitor, daemon=True)
    th.start()
    try:
        for g, flags in GROUPS:
            run_group(g, flags, p, rh4)
            if VOID.is_set():
                raise SystemExit("run VOID — STOP")
    finally:
        STOP.set()
        snapshot("end")
        m = X.meta_load()
        m["void"] = VOID.is_set()
        X.meta_save(m)
    from _provenance import stamp
    m = X.meta_load()
    m.setdefault("_provenance", []).append(stamp(script="study_e7_latency.py", model="4BI", device="h100nvl_gpu2",
                                                 n=sum(1 for _ in open(REQ))))
    X.meta_save(m)


if __name__ == "__main__":
    main()
