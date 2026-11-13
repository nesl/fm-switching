#!/usr/bin/env python3
"""StudyE10b-mixed — mixed episodic + recall load on one 32B-I replica, EXCLUSIVE (vLLM venv; h100nvl GPU 2).
Pre-registered in research/EXPERIMENTS.md (StudyE10b-mixed). Existing harnesses, combined in one asyncio loop:
  episodic    StudyD7's open loop (Poisson, numpy default_rng(level index), latency from the SCHEDULED arrival,
              dispatch lateness recorded) over DISTINCT D14 requests (d3_infer_vllm.body, PNG, N = 1 or 3, greedy,
              max_tokens 8, seed 0, streamed). One global cursor per server load over the D14 manifest in its order,
              so no episodic request repeats within a server load (prefix caching is ON).
  warm recall StudyRH7's EAGER-DELTA path (study_rh7_eager_lazy.Cell: image bytes once, uuid references after) with
              StudyRH6's device loop (study_rh6_offload_knee.device): RH2 plans H.plan(k, 0), per-device headers,
              warm-up upload of each device's history up to its offset (before the window; not measured), an append
              every 10 s of session time carrying the new 2-s-stride D2 frames (RH7's cadence), every question
              escalated at its real offset (rate 1.0), 1x real time. Escalation max_tokens 4, append 1 (RH7).
  cold recall R1's K1 request (RICH video, R1 transport + media_io_kwargs, seed 42, temperature 0, max_tokens 4;
              per-request mm_processor_kwargs = the video processor's default size, so the engine-level image size
              does not shrink the video) as Poisson arrivals at r req/s (default_rng(1000 + level index)); questions
              in random.Random(0) order.
Server (one config per cell; restarted per cell except the k = 0, r = 0 baseline levels, which share one load per KV
config as D7's levels did): 32B-I @0cfaf481, vLLM 0.31.0 (study_x_vllm.Server), prefix caching ON, prompt-token
details, --mm-processor-cache-gb 128 (RH7), images <= 640 + video 1, engine mm kwargs = RH3's image size + R1's
fps 1.0 / do_sample_frames false, --trust-request-mm-kwargs, localhost.  KV-GPU: GPU-only.  KV-HOST: + native
OffloadingConnector, --kv-offloading-backend native --kv-offloading-size 256 (RH5 / RH6).
Cell: warm-up uploads, then 270 s of arrivals from window start (the first 30 s are run but discarded), then a drain
of up to 300 s (unfinished counted). Per cell: every request row, the 1-s /metrics timeline (KV usage, running /
waiting, preemptions, prefix-cache and offload counters), 1-s CPU / GPU-util samples, host memory.
Exclusivity: monitor at start / every 30 s / end (GPU processes + owners, GPU-2 SM clock, CPU per user, processes of
ours outside this job's tree) -> VOID and STOP on overlap or a foreign process on GPU 2.
  --stage parity   token-parity gate only (KV-GPU server)
  --stage run      parity gate, then the pre-registered grid (resumable per cell)
Rows -> results/cost/study_e10/e10b_requests_h100nvl.jsonl; metrics / cpu / monitor / meta alongside.
"""
import argparse
import asyncio
import gzip
import json
import os
import random
import re
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import httpx
import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "dashcam"))
sys.path.insert(0, str(HERE.parent / "sember"))
sys.path.insert(0, str(HERE.parent / "lib"))
import study_r1_vllm as R  # noqa: E402
R1_BODY = R.body            # R1's own body; study_rh3_warmable (imported by the RH chain below) rebinds R.body
import study_rh7_eager_lazy as R7  # noqa: E402  (-> RH6, RH5, RH2, R5 fleet)
import d3_infer_vllm as D3  # noqa: E402
import study_f_common as F  # noqa: E402  (last: port 8031, GPU from F_GPU_UUID)

X, R6, H, R5, FL = F.X, R7.R6, R7.H, R7.R5, R7.F
GPU_SHORT = F.GPU_UUID[:12]
R6.GPU3 = GPU_SHORT                         # RH6 Sampler: GPU util of OUR GPU (GPU 2)
D3.MAN = REPO / "results/dashcam/study_d14_trace/d14_requests_manifest.jsonl.gz"
D3.FR = Path.home() / "data/dashcam/d14_frames/small"
OUT = REPO / "results/cost/study_e10"
REQ = OUT / "e10b_requests_h100nvl.jsonl"
MET = OUT / "e10b_metrics_h100nvl.jsonl"
CPU = OUT / "e10b_cpu_h100nvl.jsonl"
MON = OUT / "e10b_monitor_h100nvl.jsonl"
X.META_PATH = OUT / "e10b_run_meta_h100nvl.json"
X.CURRENT = REPO / "logs/e10b_current.json"
PEAK = {1: 15.10, 3: 5.38}                  # D7b / D7 32B-I closed-loop peak (req/s)
FRACS = (0.25, 0.50, 0.75, 0.90)
BUDGET = {1: 0.45, 3: 1.21}                 # episodic p99 TTFT budget (s)
EXPECT_TOK = {1: 378, 3: 1062}
DUR, DISCARD, DRAIN_CAP = 270.0, 30.0, 300.0
VIDEO_SIZE = {"longest_edge": 25165824, "shortest_edge": 4096}     # 32B-I video_preprocessor_config.json default
COMMON = ["--limit-mm-per-prompt", json.dumps({"image": 640, "video": 1}),
          "--mm-processor-kwargs", json.dumps({"size": R7.R6.B3.PROC_SIZE, "fps": 1.0, "do_sample_frames": False}),
          "--trust-request-mm-kwargs", "--host", "127.0.0.1",
          "--enable-prefix-caching", "--enable-prompt-tokens-details", "--mm-processor-cache-gb", "128"]
KV = {"KVGPU": COMMON, "KVHOST": COMMON + ["--kv-offloading-backend", "native", "--kv-offloading-size", "256"]}
GEN_EP = dict(temperature=0.0, max_tokens=8, seed=0)
OURS_PAT = ("python", "vllm", "ffmpeg", "torch")
SAFE_CMDS = ("claude", "node", "sshd", "bash", "tmux", "systemd", "sd-pam", "pipewire", "dbus", "ps ", "nvidia-smi",
             "sleep", "sh ", "code-server", "/bin/sh", "tail", "grep", "awk", "cat")
VOID = threading.Event()
STOP_MON = threading.Event()


# ------------------------------------------------------------------------------------------------ grid
def conditions():
    """(kv, k, r) conditions after the baseline, in run order (grouped by KV config)."""
    c = [("KVGPU", k, 0.0) for k in (2, 4, 8, 16)]
    c += [("KVGPU", 0, r) for r in (0.05, 0.1)]
    c += [("KVGPU", 8, 0.1)]
    c += [("KVHOST", k, 0.0) for k in (8, 16)]
    c += [("KVHOST", 8, 0.1)]
    return [(kv, k, r, n) for kv, k, r in c for n in (1, 3)]


def tag(kv, k, r, n, frac):
    return f"E10B_{kv}_k{k}_r{r:g}_N{n}_L{int(frac * 100)}"


# ------------------------------------------------------------------------------------------------ monitor
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


def snapshot(tg):
    procs = subprocess.run(["nvidia-smi", "--query-compute-apps=gpu_uuid,pid,used_memory", "--format=csv,noheader"],
                           capture_output=True, text=True).stdout.strip().splitlines()
    gpu = []
    for l in procs:
        u, pid, mem = l.split(", ")
        user = subprocess.run(["ps", "-o", "user=", "-p", pid], capture_output=True, text=True).stdout.strip() or "?"
        gpu.append(dict(gpu_uuid=u, pid=int(pid), user=user, mem=mem))
    ps = subprocess.run(["ps", "-eo", "user=,pid=,pcpu=,args="], capture_output=True, text=True).stdout.splitlines()
    cpu_by_user, ours = {}, []
    mine = tree(os.getpid())
    for l in ps:
        parts = l.split(None, 3)
        if len(parts) < 4:
            continue
        user, pid, pcpu, args = parts[0], int(parts[1]), float(parts[2]), parts[3]
        cpu_by_user[user] = round(cpu_by_user.get(user, 0.0) + pcpu, 1)
        if user == F.ME and pid not in mine and "<defunct>" not in args:   # zombies use no CPU (pcpu = lifetime avg)
            low = args.lower()
            if (any(k in low for k in OURS_PAT) or pcpu > 20) and not any(low.startswith(s) or f"/{s}" in low.split()[0]
                                                                          for s in SAFE_CMDS):
                ours.append(dict(pid=pid, pcpu=pcpu, args=args[:160]))
    rec = dict(tag=tg, at=F.now(), gpu_uuid=F.GPU_UUID, gpu_sm_util_mem=F.sm_clock(), gpu_procs=gpu,
               cpu_pct_by_user=dict(sorted(cpu_by_user.items(), key=lambda kv: -kv[1])[:8]),
               ours_outside_job=ours, foreign_on_gpu=F.foreign())
    with open(MON, "a") as f:
        f.write(json.dumps(rec) + "\n")
    return rec


def monitor():
    while not STOP_MON.wait(30):
        rec = snapshot("30s")
        if rec["ours_outside_job"]:
            X.log(f"!!! process of ours outside the job: {rec['ours_outside_job'][:3]} — VOID")
            VOID.set()
        if rec["foreign_on_gpu"]:
            X.log(f"!!! foreign process on GPU 2: {rec['foreign_on_gpu']} — STOP")
            VOID.set()


# ------------------------------------------------------------------------------------------------ requests
class Episodic:
    """D14 requests for one N in manifest order; one cursor per server load (no repeats within a load)."""

    def __init__(self, n):
        self.reqs = [r for r in map(json.loads, gzip.open(D3.MAN, "rt")) if r["n"] == n]
        self.i = 0

    def take(self, m):
        out = []
        for _ in range(m):
            if self.i >= len(self.reqs):
                raise SystemExit("episodic manifest exhausted within one server load — STOP (would repeat prompts)")
            r = self.reqs[self.i]
            self.i += 1
            b, _, _ = D3.body(r, "32BI")
            b = dict(b, stream=True, stream_options={"include_usage": True}, **GEN_EP)
            for k in ("logprobs", "top_logprobs"):
                b.pop(k, None)
            out.append((r["request_id"], json.dumps(b).encode()))
        return out


R1ROWS = None
WARM_DEVICE = None          # StudySLICE1 Part C hook: replaces R6.device for warm sessions when set; None = R6.device


def k1_body(q):
    b, _, nf = R1_BODY(R1ROWS[(q, "RICH")], "K1", "32BI", dict(temperature=0.0, max_tokens=4), stream=True)
    b["mm_processor_kwargs"] = {"size": VIDEO_SIZE}
    return json.dumps(b).encode(), nf


async def timed_post(client, kind, rid, body, sched, t0, extra):
    sent = time.time()
    first, usage, err = None, None, None
    try:
        async with client.stream("POST", f"{X.BASE}/v1/chat/completions", content=body,
                                 headers={"Content-Type": "application/json"}) as r:
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
                        if (ch.get("delta") or {}).get("content") and first is None:
                            first = time.time()
    except asyncio.CancelledError:
        err = "unfinished after drain cap"
    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {e}"
    end = time.time()
    u = usage or {}
    return dict(kind=kind, request_id=rid, t_sched=round(sched - t0, 3), dispatch_late_s=round(sent - sched, 4),
                ttft_s=round(first - sched, 4) if first else None, service_ttft_s=round(first - sent, 4) if first else None,
                total_s=round(end - sched, 4), prompt_tokens=u.get("prompt_tokens"),
                cached_tokens=(u.get("prompt_tokens_details") or {}).get("cached_tokens"),
                completion_tokens=u.get("completion_tokens"), body_mb=round(len(body) / 1e6, 3), error=err, **extra)


def schedule(rate, seed):
    """D7's open-loop arrival times (s from window start) over DUR."""
    if rate <= 0:
        return []
    rng = np.random.default_rng(seed)
    times = np.cumsum(rng.exponential(1.0 / rate, size=int(rate * DUR * 3) + 10))
    return [float(t) for t in times[times < DUR]]


async def dispatch(client, kind, times, items, t_w0, t0, tasks, extra):
    for (rid, body, ex), t in zip(items, times):
        sched = t_w0 + t
        d = sched - time.time()
        if d > 0:
            await asyncio.sleep(d)
        tasks.append(asyncio.create_task(timed_post(client, kind, rid, body, sched, t0, dict(extra, **ex))))


# ------------------------------------------------------------------------------------------------ cell
async def run_cell(kv, k, r, n, frac, srv_pid, ep, cold_cursor):
    tg = tag(kv, k, r, n, frac)
    lvl = FRACS.index(frac)
    rate = frac * PEAK[n]
    sp = R7.spec("EAGER", max(k, 1), tag=tg)
    sp["offload"] = 256 if kv == "KVHOST" else 0
    cell = R7.Cell(sp, 0)
    cell.t0 = time.time()
    cell.mem = []
    stop = asyncio.Event()
    sampler = R6.Sampler(srv_pid)
    scr = asyncio.create_task(cell.scrape(stop))
    smp = asyncio.create_task(sampler.run(cell, stop))
    msm = asyncio.create_task(R7.mem_sampler(cell, srv_pid, stop))
    m_start = await R5.scrape_once(cell.client)
    plans, offsets = H.plan(k, 0) if k else ([], [])
    t_wu = time.time()
    if k:
        await asyncio.gather(*(cell.post("warmup", d, 0, plans[d][0], offsets[d], in_window=False) for d in range(k)))
    warmup_s = time.time() - t_wu
    ep_times, cold_times = schedule(rate, lvl), schedule(r, 1000 + lvl)

    def make_cold(m):
        out = []
        for _ in range(m):
            q = cold_cursor["order"][cold_cursor["i"] % len(cold_cursor["order"])]
            cold_cursor["i"] += 1
            body, nf = k1_body(q)
            out.append((q, body, dict(n_frames=nf, expected_prompt_tokens=R1ROWS[(q, "RICH")]["n_input_instruct"])))
        return out

    ep_items = [(rid, b, {}) for rid, b in await asyncio.to_thread(ep.take, len(ep_times))]   # built before the window
    cold_items = await asyncio.to_thread(make_cold, len(cold_times))
    used = [x[0] for x in ep_items]
    t_w0 = time.time() + 1.0
    window_end = t_w0 + DUR
    m_w0 = await R5.scrape_once(cell.client)
    tasks = []
    client = httpx.AsyncClient(timeout=None, limits=httpx.Limits(max_connections=None, max_keepalive_connections=None))
    X.log(f"{tg}: warm-up {warmup_s:.1f}s; window starts (episodic {rate:.2f} req/s, k {k}, cold {r} req/s)")
    await asyncio.gather(dispatch(client, "episodic", ep_times, ep_items, t_w0, cell.t0, tasks, dict(n=n)),
                         dispatch(client, "cold_recall", cold_times, cold_items, t_w0, cell.t0, tasks, {}),
                         *((WARM_DEVICE or R6.device)(cell, d, plans[d], offsets[d], window_end) for d in range(k)))
    await asyncio.sleep(max(0.0, window_end - time.time()))
    m_w1 = await R5.scrape_once(cell.client)
    inflight_end = sum(not t.done() for t in tasks) + len(cell.inflight)
    t_d = time.time()
    pend = [t for t in tasks if not t.done()] + list(cell.inflight)
    if pend:
        _, still = await asyncio.wait(pend, timeout=DRAIN_CAP)
        for t in still:
            t.cancel()
        if still:
            await asyncio.gather(*still, return_exceptions=True)
    drain = time.time() - t_d
    await asyncio.sleep(1.5)
    m_end = await R5.scrape_once(cell.client)
    stop.set()
    await scr
    await smp
    await msm
    await cell.client.aclose()
    await client.aclose()
    rows = [dict(t.result(), cell=tg, kv=kv, k=k, r=r, N=n, frac=frac, rate=rate,
                 in_window=t.result()["t_sched"] - (t_w0 - cell.t0) >= DISCARD) for t in tasks if not t.cancelled()]
    w0 = t_w0 - cell.t0
    for x in cell.records:
        rows.append(dict(x, kind="recall_" + x["kind"], cell=tg, kv=kv, k=k, r=r, N=n, frac=frac, rate=rate,
                         in_window=x["in_window"] and x["t_sched"] is not None and x["t_sched"] - w0 >= DISCARD))
    with open(REQ, "a") as f:
        for x in rows:
            f.write(json.dumps(x) + "\n")
    with open(MET, "a") as f:
        f.write(json.dumps(dict(cell=tg, window_start=round(w0, 2), timeline=cell.timeline)) + "\n")
    with open(CPU, "a") as f:
        f.write(json.dumps(dict(cell=tg, window_start=round(w0, 2), samples=cell.cpu, mem=cell.mem)) + "\n")
    ep_w = [x for x in rows if x["kind"] == "episodic" and x["in_window"]]
    tt = [x["ttft_s"] for x in ep_w if x["ttft_s"] is not None]
    bad = sum(bool(x["error"]) for x in ep_w)
    p99 = float(np.percentile(tt, 99)) if tt else None
    meets = p99 is not None and p99 <= BUDGET[n] and bad == 0 and len(tt) == len(ep_w)
    summ = dict(episodic_n=len(ep_w), episodic_p50=float(np.median(tt)) if tt else None,
                episodic_p99=p99, episodic_errors=bad, meets_budget=meets, warmup_s=round(warmup_s, 1),
                inflight_at_window_end=inflight_end, drain_s=round(drain, 1),
                recall_escalations=sum(x["kind"] == "recall_escalation" and x["in_window"] for x in rows),
                cold_recall=sum(x["kind"] == "cold_recall" and x["in_window"] for x in rows),
                errors=sum(bool(x["error"]) for x in rows))
    X.mark_done(tg, kv=kv, k=k, r=r, N=n, frac=frac, rate=rate, window_start=round(w0, 2), summary=summ,
                counters=dict(start=m_start, window_start=m_w0, window_end=m_w1, end=m_end),
                episodic_ids=[used[0], used[-1]] if used else None, void_at_end=VOID.is_set())
    X.log(f"{tg}: {summ}")
    return summ


# ------------------------------------------------------------------------------------------------ parity
async def parity(ep, srv_pid):
    """Token-parity gate on the fresh KV-GPU server: D14 N=1 / N=3, K1 video, D2 warm-up -> append -> escalation."""
    out, ok = [], True
    async with httpx.AsyncClient(timeout=None) as c:
        for n in (1, 3):
            for rid, body in ep[n].take(2):
                rec = await timed_post(c, "parity_episodic", rid, body, time.time(), 0.0, dict(n=n))
                good = rec["prompt_tokens"] == EXPECT_TOK[n] and not rec["error"]
                ok &= good
                out.append(dict(rec, expected=EXPECT_TOK[n], match=good))
        for q in sorted({q for q, _ in R1ROWS})[:2]:
            body, nf = k1_body(q)
            rec = await timed_post(c, "parity_k1", q, body, time.time(), 0.0, dict(n_frames=nf))
            exp = R1ROWS[(q, "RICH")]["n_input_instruct"]
            good = rec["prompt_tokens"] == exp and not rec["error"]
            ok &= good
            out.append(dict(rec, expected=exp, match=good))
    sp = R7.spec("EAGER", 1, tag="E10B_PARITY")
    cell = R7.Cell(sp, 0)
    cell.t0 = time.time()
    plans, offs = H.plan(2, 0)
    sess, off = plans[0][0], offs[0]
    t1 = (int(off // 10) + 1) * 10
    w = await cell.post("warmup", 0, 0, sess, off, in_window=False)
    a = await cell.post("append", 0, 0, sess, t1, in_window=False)
    await cell.client.aclose()
    added = (a["prompt_tokens"] - w["prompt_tokens"]) if a["prompt_tokens"] and w["prompt_tokens"] else None
    frames_added = a["n_frames"] - w["n_frames"]
    d2_ok = (added is not None and frames_added > 0 and added == 90 * frames_added and
             (a["cached_tokens"] or 0) >= 0.9 * w["prompt_tokens"] and not a["fallback"])
    out.append(dict(kind="parity_d2", warmup=w, append=a, tokens_added=added,
                    frames_added=frames_added, tokens_per_frame=None if not frames_added else added / frames_added,
                    append_cached=a["cached_tokens"], match=d2_ok))
    ok &= d2_ok
    return ok, out


# ------------------------------------------------------------------------------------------------ main
def start_server(kv, label):
    F.require_idle()
    srv = X.Server("32BI", KV[kv])
    info = srv.start()
    info.update(prefix_caching=True, kv_config=kv, kv_offloading_gib=256 if kv == "KVHOST" else 0,
                mm_processor_cache_gb=128, host_mem=R5.host_mem(srv.proc.pid))
    m = X.meta_load()
    m.setdefault("servers", []).append(dict(label=label, started=F.now(), flags=KV[kv], **info))
    X.meta_save(m)
    X.log(f"[{label}] {kv}: KV {info.get('kv_cache_tokens')} tokens")
    snapshot(f"server_up_{label}")
    return srv


def baseline_pass(kv, n):
    """Levels (descending) that met the budget at k = 0, r = 0 for this KV config and N; at least [25 %]."""
    m = X.meta_load()
    ok = [f for f in FRACS if (m.get("experiments", {}).get(tag(kv, 0, 0.0, n, f)) or {}).get("summary", {}).get("meets_budget")]
    return sorted(ok, reverse=True) or [0.25]


def main():
    global R1ROWS
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["parity", "run"], required=True)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    R1ROWS = {(r["question_id"], r["construction"]): r for r in map(json.loads, gzip.open(
        REPO / "results/sember/study_r1/study_r1_inputs_manifest.jsonl.gz", "rt"))}
    order = sorted({q for q, _ in R1ROWS})
    random.Random(0).shuffle(order)
    start = snapshot("start")
    if start["ours_outside_job"]:
        raise SystemExit(f"not exclusive at start: {start['ours_outside_job']} — STOP")
    import torch
    import vllm
    m = X.meta_load()
    m["stack"] = dict(venv=sys.prefix, vllm=vllm.__version__, torch=torch.__version__, gpu=F.GPU_LABEL,
                      gpu_uuid=F.GPU_UUID, kv_flags=KV, peak=PEAK, fracs=FRACS, budget=BUDGET, dur=DUR,
                      discard=DISCARD, drain_cap=DRAIN_CAP)
    m["conditions"] = conditions()
    X.meta_save(m)
    th = threading.Thread(target=monitor, daemon=True)
    th.start()
    try:
        S = FL.sessions()
        R6.preencode("D2", S)
        # parity gate (fresh KV-GPU server)
        if not X.meta_load().get("parity", {}).get("passed"):
            srv = start_server("KVGPU", "parity")
            try:
                ok, recs = asyncio.run(parity({1: Episodic(1), 3: Episodic(3)}, srv.proc.pid))
            finally:
                srv.stop()
            m = X.meta_load()
            m["parity"] = dict(passed=ok, rows=recs)
            X.meta_save(m)
            X.log(f"PARITY {'PASSED' if ok else 'FAILED'}: " + json.dumps([(r.get("kind"), r.get("prompt_tokens"), r.get("expected"),
                                                                          r.get("tokens_per_frame"), r["match"]) for r in recs]))
            if not ok:
                raise SystemExit("E10b token-parity gate FAILED — STOP")
        if a.stage == "parity":
            return
        for kv in ("KVGPU", "KVHOST"):
            # (a) baseline: k = 0, r = 0, all four levels per N on one server load (D7 style; one cursor per N)
            todo = [(n, f) for n in (1, 3) for f in FRACS if not X.is_done(tag(kv, 0, 0.0, n, f))]
            if todo:
                srv = start_server(kv, f"{kv}_baseline")
                try:
                    ep = {1: Episodic(1), 3: Episodic(3)}
                    for n, f in todo:
                        asyncio.run(run_cell(kv, 0, 0.0, n, f, srv.proc.pid, ep[n], dict(order=order, i=0)))
                        if VOID.is_set():
                            raise SystemExit("run VOID — STOP")
                finally:
                    srv.stop()
            # (b)-(e): per condition, levels top-down from the baseline-passing ones; stop at the first that meets
            for ckv, k, r, n in conditions():
                if ckv != kv:
                    continue
                for f in baseline_pass(kv, n):
                    tg = tag(kv, k, r, n, f)
                    if X.is_done(tg):
                        if X.meta_load()["experiments"][tg]["summary"]["meets_budget"]:
                            break
                        continue
                    srv = start_server(kv, tg)
                    try:
                        s = asyncio.run(run_cell(kv, k, r, n, f, srv.proc.pid, Episodic(n), dict(order=order, i=0)))
                    finally:
                        srv.stop()
                    if VOID.is_set():
                        raise SystemExit("run VOID — STOP")
                    if s["meets_budget"]:
                        break
    finally:
        STOP_MON.set()
        snapshot("end")
        m = X.meta_load()
        m["void"] = VOID.is_set()
        X.meta_save(m)
    from _provenance import stamp
    m = X.meta_load()
    m.setdefault("_provenance", []).append(stamp(script="study_e10b_mixed.py", model="qwen3vl-32b-instruct",
                                                 device="h100nvl_gpu2", args=a))
    X.meta_save(m)


if __name__ == "__main__":
    main()
