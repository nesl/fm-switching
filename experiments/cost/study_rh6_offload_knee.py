#!/usr/bin/env python3
"""StudyRH6 — knee of the GPU+host-offload configuration and the controller's levers (vLLM venv). Systems only.
Pre-registered in research/EXPERIMENTS.md (StudyRH6).

Server: exactly RH5's GPU+host server (study_rh5_host_offload.SERVER_BASE + native offload; --kv-offloading-size 256,
or 64 for Part C). Harness: RH5's (RH2 plans/seeds via study_rh2_knee_surface.plan, per-device headers, 1x real time,
15-min window, warm-up upload, P-WARM, escalation rate 1.0, greedy, max_tokens 1 append / 4 escalation).
  --stage estimate                     runtime estimate (no GPU); STOP if > 8 h
  --stage partA                        A_D32, A_D48, A_D64, A_D96 (D2, append every 10 s)
  --stage partB                        at D* (from Part A): B1 cadence 30 s, B2 format D1, B3 lazy (no appends)
  --stage partC                        at D*: offload 64 GiB (D2, 10 s) — separate server
Implementation differences from RH5 (request content and schedule unchanged):
  * frames are base64-encoded once per process before the first cell (process pool), and the JSON body is assembled
    from pre-serialised per-image fragments (RH5 built and json.dumps'd up to 54-MB bodies in the event loop);
  * httpx connection limit 16384 (RH5: 1024; RH5's GPU-only D24 queued >1024 requests client-side);
  * each request records its scheduled time and the client submit lag;
  * a 1-s sampler records CPU cores of the API-server process (and its busiest thread), the engine-core process tree,
    and this harness, plus GPU-3 SM utilisation (NVML), next to RH5's 1-s /metrics scrape.
"""
import argparse
import asyncio
import base64
import io
import json
import os
import re
import sys
import time
from datetime import datetime
from multiprocessing import Pool
from pathlib import Path

import httpx
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sember"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
import study_r5_fleet as F  # noqa: E402
import study_rh2_knee_surface as H  # noqa: E402
import study_rh3_inputs as B3  # noqa: E402
import study_rh5_host_offload as R5  # noqa: E402
import study_x_vllm as X  # noqa: E402

OUT = Path("results/cost/study_rh6")
REQ = OUT / f"study_rh6_requests_{X.DEV}.jsonl"
MET = OUT / f"study_rh6_metrics_{X.DEV}.jsonl"
CPU = OUT / f"study_rh6_cpu_{X.DEV}.jsonl"
X.META_PATH = OUT / f"study_rh6_run_meta_{X.DEV}.json"
X.CURRENT = Path("logs/study_rh6_current.json")
STRIDE_S = 2
SIZES = {"D2": (352, 256), "D1": (288, 224)}
TOK_IMG = {"D2": 92, "D1": 65}           # (w//32)*(h//32) + 2 + row/vision tokens as measured in RH4/RH5 prompts
KV_TOKENS = 62944
BYTES_PER_TOKEN = 262144
GPU3 = "GPU-b3c6399e"
BUDGET_S = 8 * 3600
PART_A_DS = (32, 48, 64, 96)
BREACH_MEDIAN_S, BREACH_P99_S = 1.5, 10.0


def cells_a():
    return [dict(tag=f"RH6_A_D{D}", part="A", D=D, fmt="D2", cadence=10, lazy=False, offload=256) for D in PART_A_DS]


def cells_b(Ds):
    return [dict(tag=f"RH6_B1_D{Ds}", part="B1", D=Ds, fmt="D2", cadence=30, lazy=False, offload=256),
            dict(tag=f"RH6_B2_D{Ds}", part="B2", D=Ds, fmt="D1", cadence=10, lazy=False, offload=256),
            dict(tag=f"RH6_B3_D{Ds}", part="B3", D=Ds, fmt="D2", cadence=None, lazy=True, offload=256)]


def cell_c(Ds):
    return dict(tag=f"RH6_C_D{Ds}", part="C", D=Ds, fmt="D2", cadence=10, lazy=False, offload=64)


# ------------------------------------------------------------------------------------------------ frames
_FRAG = {}          # (fmt, path) -> bytes: '{"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}'


def _enc(job):
    fmt, path = job
    im = B3.load(path, SIZES[fmt])
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    url = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    return fmt, path, json.dumps({"type": "image_url", "image_url": {"url": url}}).encode()


def frames(sess, upto_s):
    return [(t, p) for t, p in sess["frames"] if t <= upto_s + 1e-6 and t % STRIDE_S == 0]


def preencode(fmt, sessions, procs=32):
    jobs = [(fmt, p) for s in sessions for t, p in s["frames"] if t % STRIDE_S == 0 and (fmt, p) not in _FRAG]
    t = time.time()
    with Pool(procs) as pool:
        for f, p, b in pool.imap_unordered(_enc, jobs, chunksize=64):
            _FRAG[(f, p)] = b
    X.log(f"pre-encoded {len(jobs)} {fmt} frames in {time.time() - t:.0f}s "
          f"({sum(len(v) for k, v in _FRAG.items() if k[0] == fmt) / 2 ** 30:.1f} GiB)")


def header(tag, dev, sess_i):
    return R5.header(tag, dev, sess_i)          # identical wording to RH5 (stride 2 s for both D1 and D2)


def body(fmt, hdr, sess, upto_s, question, max_tokens):
    parts = [json.dumps({"type": "text", "text": hdr}).encode()]
    parts += [_FRAG[(fmt, p)] for _, p in frames(sess, upto_s)]
    if question:
        parts.append(json.dumps({"type": "text", "text": question}).encode())
    head = json.dumps(dict(model="32BI", temperature=0.0, max_tokens=max_tokens, stream=True,
                           stream_options={"include_usage": True}))[:-1].encode()
    return head + b', "messages": [{"role": "user", "content": [' + b", ".join(parts) + b"]}]}"


# ------------------------------------------------------------------------------------------------ cell
class Cell(F.Cell):
    def __init__(self, spec, seed=0):
        super().__init__(spec["tag"], "LAZY" if spec["lazy"] else "WARM", spec["D"], 1.0, seed)
        self.spec = spec
        self.client = httpx.AsyncClient(timeout=None, limits=httpx.Limits(max_connections=16384,
                                                                           max_keepalive_connections=16384))
        self.cpu = []

    async def post(self, kind, dev, sess_i, sess, upto_s, question=None, qid=None, in_window=True, t_sched=None):
        fmt = self.spec["fmt"]
        mt = F.ESC_MAX_TOKENS if kind == "escalation" else 1
        data = await asyncio.to_thread(body, fmt, header(self.tag, dev, sess_i), sess, upto_s, question, mt)
        n_frames = len(frames(sess, upto_s))
        t_sub = time.time()
        first, usage, err = None, None, None
        try:
            async with self.client.stream("POST", f"{X.BASE}/v1/chat/completions", content=data,
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
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {e}"
        t_end = time.time()
        rec = dict(cell=self.tag, part=self.spec["part"], fmt=fmt, cadence=self.spec["cadence"],
                   lazy=self.spec["lazy"], offload_gib=self.spec["offload"], D=self.D, kind=kind, device=dev,
                   session=sess_i, video_id=sess["video_id"], session_t=round(upto_s, 1), n_frames=n_frames,
                   body_mb=round(len(data) / 1e6, 2), question_id=qid, in_window=in_window,
                   t_sched=None if t_sched is None else round(t_sched - self.t0, 3),
                   t_submit=round(t_sub - self.t0, 3),
                   submit_lag_s=None if t_sched is None else round(t_sub - t_sched, 3),
                   ttft_s=round(first - t_sub, 3) if first else None, latency_s=round(t_end - t_sub, 3),
                   t_end=round(t_end - self.t0, 3), prompt_tokens=usage and usage["prompt_tokens"],
                   cached_tokens=((usage or {}).get("prompt_tokens_details") or {}).get("cached_tokens"),
                   completion_tokens=usage and usage["completion_tokens"], error=err,
                   warm_device=not self.spec["lazy"])
        self.records.append(rec)
        return rec

    async def scrape(self, stop):
        while not stop.is_set():
            try:
                row = await R5.scrape_once(self.client)
                row["t"] = round(time.time() - self.t0, 2)
                self.timeline.append(row)
            except httpx.HTTPError:
                pass
            await asyncio.sleep(1.0)


class Sampler:
    """1-s CPU cores of API server / its busiest thread / engine tree / harness, and GPU-3 SM util (NVML)."""
    def __init__(self, api_pid):
        import psutil
        import pynvml
        self.ps = psutil
        self.api = psutil.Process(api_pid)
        self.me = psutil.Process(os.getpid())
        pynvml.nvmlInit()
        self.nv = pynvml
        self.h = next(pynvml.nvmlDeviceGetHandleByIndex(i) for i in range(pynvml.nvmlDeviceGetCount())
                      if GPU3 in str(pynvml.nvmlDeviceGetUUID(pynvml.nvmlDeviceGetHandleByIndex(i))))

    def snap(self):
        def tot(p):
            try:
                c = p.cpu_times()
                return c.user + c.system
            except self.ps.Error:
                return 0.0
        kids = self.api.children(recursive=True)
        try:
            threads = {t.id: t.user_time + t.system_time for t in self.api.threads()}
        except self.ps.Error:
            threads = {}
        return dict(t=time.time(), api=tot(self.api), engine=sum(tot(k) for k in kids), harness=tot(self.me),
                    threads=threads)

    async def run(self, cell, stop):
        prev = self.snap()
        while not stop.is_set():
            await asyncio.sleep(1.0)
            cur = self.snap()
            dt = cur["t"] - prev["t"]
            thr = [(v - prev["threads"].get(k, v)) / dt for k, v in cur["threads"].items()]
            try:
                u = self.nv.nvmlDeviceGetUtilizationRates(self.h).gpu
            except self.nv.NVMLError:
                u = None
            cell.cpu.append(dict(t=round(cur["t"] - cell.t0, 2), api_cores=round((cur["api"] - prev["api"]) / dt, 3),
                                 api_max_thread_cores=round(max(thr), 3) if thr else None,
                                 engine_cores=round((cur["engine"] - prev["engine"]) / dt, 3),
                                 harness_cores=round((cur["harness"] - prev["harness"]) / dt, 3), gpu_util=u))
            prev = cur


async def device(cell, dev, plan_d, offset, window_end):
    """H.device (P-WARM, rate 1.0) with the append cadence as a parameter; lazy = escalations only."""
    s_i, sess, start_s = 0, plan_d[0], offset
    t_start = time.time()
    cad = cell.spec["cadence"]
    while True:
        ev = []
        if not cell.spec["lazy"]:
            k0 = int(start_s // cad) + 1
            ev += [(k * cad, "append", None) for k in range(k0, int(sess["duration"] // cad) + 1)]
        ev += [(q["qt"], "escalation", q) for q in sess["questions"] if q["qt"] > start_s + 1e-6]
        ev.sort(key=lambda e: (e[0], e[1] != "append"))
        for st, kind, q in ev:
            wall = t_start + (st - start_s)
            if wall > window_end:
                return
            await asyncio.sleep(max(0.0, wall - time.time()))
            cell.spawn(cell.post(kind, dev, s_i, sess, st, question=q and q["text"], qid=q and q["qid"],
                                 t_sched=wall))
        t_start = t_start + (sess["duration"] - start_s)
        s_i += 1
        if s_i >= len(plan_d) or t_start > window_end:
            return
        sess, start_s = plan_d[s_i], 0.0
        await asyncio.sleep(max(0.0, t_start - time.time()))


def plan_coverage(D, seed=0):
    """Devices with no session in the window, and devices whose plan ends before the window does."""
    plans, offs = H.plan(D, seed)
    empty = sum(1 for p in plans if not p)
    early = sum(1 for p, o in zip(plans, offs) if p and sum(s["duration"] for s in p) - o < F.WINDOW_S)
    return dict(devices=D, devices_without_sessions=empty, devices_plan_ends_before_window_end=early,
                sessions_per_device=sorted({len(p) for p in plans}))


async def run_cell(spec, srv_pid, seed=0):
    t = spec["tag"]
    D = spec["D"]
    plans, offsets = H.plan(D, seed)
    cell = Cell(spec, seed)
    cell.t0 = time.time()
    mem0 = R5.host_mem(srv_pid)
    stop = asyncio.Event()
    sampler = Sampler(srv_pid)
    scr = asyncio.create_task(cell.scrape(stop))
    smp = asyncio.create_task(sampler.run(cell, stop))
    m_start = await R5.scrape_once(cell.client)
    if not spec["lazy"]:
        await asyncio.gather(*(cell.post("warmup", d, 0, plans[d][0], offsets[d], in_window=False)
                               for d in range(D)))
    t_w0 = time.time()
    X.log(f"{t}: warm-up {t_w0 - cell.t0:.1f}s; window starts")
    m_w0 = await R5.scrape_once(cell.client)
    window_end = t_w0 + F.WINDOW_S
    await asyncio.gather(*(device(cell, d, plans[d], offsets[d], window_end) for d in range(D)))
    await asyncio.sleep(max(0.0, window_end - time.time()))
    n_inflight = len(cell.inflight)
    m_w1 = await R5.scrape_once(cell.client)
    mem1 = R5.host_mem(srv_pid)
    t_d0 = time.time()
    if cell.inflight:
        await asyncio.gather(*list(cell.inflight))
    drain = time.time() - t_d0
    await asyncio.sleep(1.5)
    m_end = await R5.scrape_once(cell.client)
    stop.set()
    await scr
    await smp
    await cell.client.aclose()
    meta = dict(spec=spec, seed=seed, window_s=F.WINDOW_S, window_start=round(t_w0 - cell.t0, 2),
                warmup_s=round(t_w0 - cell.t0, 2), inflight_at_window_end=n_inflight, drain_s=round(drain, 1),
                elapsed_window_plus_drain_s=round(time.time() - t_w0, 1), coverage=plan_coverage(D, seed),
                host_mem_start=mem0, host_mem_window_end=mem1, host_mem_end=R5.host_mem(srv_pid),
                counters=dict(start=m_start, window_start=m_w0, window_end=m_w1, end=m_end))
    with open(REQ, "a") as f:
        for r in cell.records:
            f.write(json.dumps(r) + "\n")
    with open(MET, "a") as f:
        f.write(json.dumps(dict(cell=t, timeline=cell.timeline)) + "\n")
    with open(CPU, "a") as f:
        f.write(json.dumps(dict(cell=t, samples=cell.cpu)) + "\n")
    summ = summarise(cell.records, meta)
    ver = verify_host(meta, spec)
    X.log(f"{t}: {len(cell.records)} requests; {summ}; inflight at end {n_inflight}; drain {drain:.0f}s; "
          f"host verification {ver}")
    X.mark_done(t, **meta, summary=summ, host_verification=ver)
    return summ, ver


def esc_stats(records):
    esc = [r for r in records if r["kind"] == "escalation" and r["in_window"] and not r["error"]]
    tt = [r["ttft_s"] for r in esc if r["ttft_s"] is not None]
    return dict(n=len(esc), ttft_median=float(np.median(tt)) if tt else None,
                ttft_p99=float(np.percentile(tt, 99)) if tt else None, ttft_max=float(max(tt)) if tt else None)


def summarise(records, meta):
    s = esc_stats(records)
    ap = [r["ttft_s"] for r in records if r["kind"] == "append" and r["in_window"] and r["ttft_s"] is not None]
    lag = [r["submit_lag_s"] for r in records if r.get("submit_lag_s") is not None]
    s.update(append_median=float(np.median(ap)) if ap else None,
             append_p99=float(np.percentile(ap, 99)) if ap else None,
             submit_lag_p99=float(np.percentile(lag, 99)) if lag else None,
             errors=sum(bool(r["error"]) for r in records),
             errors_400=sum(bool(r["error"]) and r["error"].startswith("HTTP 400") for r in records))
    return s


def _d(a, b, *names):
    return sum(v for k, v in b.items() if any(k.startswith(n) for n in names)) - \
        sum(v for k, v in a.items() if any(k.startswith(n) for n in names))


def verify_host(meta, spec):
    """Pre-registered: whole-cell counter deltas (start -> end); load bytes / external hit tokens = 262,144 +- 5 %;
    external hits > 0 in every append cell (B3 lazy: ratio only if hits > 0, else 'not exercised')."""
    c = meta["counters"]
    ext = _d(c["start"], c["end"], "external_prefix_cache_hits")
    load = _d(c["start"], c["end"], "kv_offload_load_bytes")
    ratio = load / ext if ext else None
    if not ext:
        ok = None if spec["lazy"] else False
    else:
        ok = abs(ratio / BYTES_PER_TOKEN - 1) <= 0.05
    return dict(external_hit_tokens=ext, load_bytes=load, bytes_per_hit_token=ratio,
                verified=ok, note="not exercised (no host hits)" if ok is None else "")


def breach(s):
    return s["ttft_median"] is not None and (s["ttft_median"] > BREACH_MEDIAN_S or s["ttft_p99"] > BREACH_P99_S)


def d_star():
    m = X.meta_load()
    done = m.get("experiments", {})
    for D in PART_A_DS:
        r = done.get(f"RH6_A_D{D}")
        if r is None:
            raise SystemExit(f"Part A cell D{D} missing — cannot determine D*")
        if breach(r["summary"]):
            return D, True
    return 96, False


# ------------------------------------------------------------------------------------------------ estimate
def window_events(plans, offsets, cadence, lazy):
    out = []
    for d, plan_d in enumerate(plans):
        t_rel, s_i, sess, st0 = 0.0, 0, plan_d[0], offsets[d]
        while True:
            if not lazy:
                for k in range(int(st0 // cadence) + 1, int(sess["duration"] // cadence) + 1):
                    if t_rel + (k * cadence - st0) <= F.WINDOW_S:
                        out.append(("append", d, k * cadence, sess))
            for q in sess["questions"]:
                if q["qt"] > st0 + 1e-6 and t_rel + (q["qt"] - st0) <= F.WINDOW_S:
                    out.append(("escalation", d, q["qt"], sess))
            t_rel += sess["duration"] - st0
            s_i += 1
            if s_i >= len(plan_d) or t_rel > F.WINDOW_S:
                break
            sess, st0 = plan_d[s_i], 0.0
    return out


SERVICE_S = 0.275       # RH5 GPU+host D24: M/M/1 fit S/(1 - lambda S) = 0.81 s at lambda = 2.37 req/s
ACHIEVED_TOK_S = 5000   # RH5 GPU-only collapse: achieved computed tok/s
PREFILL_TOK_S = 4500    # RH5 Part A COLD 11k


def live_resident(plans, offsets, tok):
    """Peak / mean over the window (5-s grid) of the summed current history of every device still in a session —
    the KV the live set must keep (older sessions' blocks are LRU-evictable)."""
    grid = np.arange(0, F.WINDOW_S + 1, 5.0)
    tot = np.zeros_like(grid)
    for p, o in zip(plans, offsets):
        t_rel, st0 = 0.0, o
        for s in p:
            dur = s["duration"] - st0
            m = (grid >= t_rel) & (grid < t_rel + dur)
            tot[m] += (np.floor((st0 + grid[m] - t_rel) / STRIDE_S) + 1) * tok
            t_rel += dur
            st0 = 0.0
            if t_rel > F.WINDOW_S:
                break
    return float(tot.max()), float(tot.mean())


def est_cell(spec, saturates=True):
    """saturates=False: the scenario assumes this offload cell is below the knee (no drain)."""
    D, fmt = spec["D"], spec["fmt"]
    plans, offs = H.plan(D)
    ev = window_events(plans, offs, spec["cadence"], spec["lazy"])
    tok = TOK_IMG[fmt]
    hist = np.array([len(frames(s, st)) * tok for _, _, st, s in ev], float)
    lam = len(ev) / F.WINDOW_S
    warm = 0 if spec["lazy"] else sum(len(frames(p[0], o)) * tok for p, o in zip(plans, offs)) / PREFILL_TOK_S
    peak, mean = live_resident(plans, offs, tok) if not spec["lazy"] else (0.0, 0.0)
    cap = (spec["offload"] * 2 ** 30) / BYTES_PER_TOKEN + KV_TOKENS
    thrash = peak > cap
    if spec["lazy"]:
        demand = hist.sum() * 0.7                       # cold by design; ~30 % from a previous escalation
        drain = max(0.0, demand / ACHIEVED_TOK_S - F.WINDOW_S)
        mode = "lazy (cold escalations)"
    elif thrash:
        miss = min(1.0, 0.35 + max(0.0, mean / cap - 0.5))
        demand = hist.sum() * miss
        drain = max(0.0, demand / ACHIEVED_TOK_S - F.WINDOW_S)
        mode = f"host thrash (recompute, miss {miss:.2f})"
    else:
        mu = 1 / SERVICE_S
        drain = max(0.0, (lam - mu) * F.WINDOW_S / mu) if saturates else 0.0
        mode = "offload (service-rate model)" if saturates else "offload (below knee in this scenario)"
    return dict(events=len(ev), req_per_s=round(lam, 2), mean_history=round(hist.mean()),
                live_peak_tokens=round(peak), live_mean_tokens=round(mean),
                live_peak_over_capacity=round(peak / cap, 2), warmup_s=round(warm), drain_s=round(drain),
                s=round(warm + F.WINDOW_S + drain + 30), mode=mode)


def estimate():
    """One scenario per possible D*: Part A cells below D* do not saturate (that is what D* means); cells >= D*
    and the B/C cells at D* use the service-rate model (offload), or the recompute model where the live set exceeds
    GPU+host capacity. STOP compares the scenario the model itself predicts (its own first breach) with 8 h, and
    reports every scenario."""
    scen = {}
    for Ds in PART_A_DS + (None,):
        a = {c["tag"]: est_cell(c, saturates=Ds is not None and c["D"] >= Ds) for c in cells_a()}
        Db = Ds or 96
        b = {c["tag"]: est_cell(c) for c in cells_b(Db) + [cell_c(Db)]}
        tot = sum(v["s"] for v in a.values()) + sum(v["s"] for v in b.values()) + 2 * 240 + 3 * 120
        scen[f"D*={Ds or 'none (96)'}"] = dict(part_a=a, cells=b, total_s=round(tot))
    mu = 1 / SERVICE_S
    predicted = next((D for D in PART_A_DS if est_cell(cells_a()[PART_A_DS.index(D)])["req_per_s"] * SERVICE_S
                      > 0.9 or est_cell(cells_a()[PART_A_DS.index(D)])["live_peak_over_capacity"] > 1), None)
    return dict(scenarios=scen, predicted_d_star=predicted, service_capacity_req_s=round(mu, 2),
                overhead="2 server starts x 240 s + 3 frame pre-encodes x 120 s",
                coverage={D: plan_coverage(D) for D in PART_A_DS},
                model=dict(service_s=SERVICE_S, achieved_tok_s=ACHIEVED_TOK_S, prefill_tok_s=PREFILL_TOK_S))


# ------------------------------------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["estimate", "smoke", "partA", "partB", "partC"], required=True)
    ap.add_argument("--smoke-dir", help="smoke stage: output directory (not results/)")
    args = ap.parse_args()
    global REQ, MET, CPU
    if args.stage == "smoke":           # code-path check: D=4, 60-s window, A + lazy cell; not a result
        d = Path(args.smoke_dir)
        d.mkdir(parents=True, exist_ok=True)
        REQ, MET, CPU = d / "req.jsonl", d / "met.jsonl", d / "cpu.jsonl"
        X.META_PATH = d / "meta.json"
        F.WINDOW_S = 60
    OUT.mkdir(parents=True, exist_ok=True)
    if args.stage == "estimate":
        est = estimate()
        m = X.meta_load()
        m["estimate"] = est
        X.meta_save(m)
        key = f"D*={est['predicted_d_star'] or 'none (96)'}"
        tot = est["scenarios"][key]["total_s"]
        X.log("RUNTIME ESTIMATE (h): " + json.dumps({k: round(v["total_s"] / 3600, 2)
                                                     for k, v in est["scenarios"].items()}) +
              f"; model-predicted {key}: {tot / 3600:.2f} h")
        if tot > BUDGET_S:
            raise SystemExit(f"RH6 estimate {tot / 3600:.2f} h > 8 h — STOP")
        return
    if args.stage == "smoke":
        specs = [dict(tag="RH6_SMOKE_D4", part="smoke", D=4, fmt="D2", cadence=10, lazy=False, offload=256),
                 dict(tag="RH6_SMOKE_LAZY_D4", part="smoke", D=4, fmt="D2", cadence=None, lazy=True, offload=256)]
    elif args.stage == "partA":
        specs = cells_a()
    else:
        Ds, breached = d_star()
        m = X.meta_load()
        m["d_star"] = dict(D=Ds, breached=breached, rule=f"smallest Part A D with warm escalation median > "
                                                         f"{BREACH_MEDIAN_S} s or p99 > {BREACH_P99_S} s; else 96")
        X.meta_save(m)
        X.log(f"D* = {Ds} ({'breach' if breached else 'NO Part A cell breached; D = 96 used'})")
        specs = cells_b(Ds) if args.stage == "partB" else [cell_c(Ds)]
    specs = [s for s in specs if not X.is_done(s["tag"])]
    if not specs:
        return
    S = F.sessions()
    for fmt in sorted({s["fmt"] for s in specs}):
        preencode(fmt, S)
    gib = specs[0]["offload"]
    srv = X.Server("32BI", R5.SERVER_BASE + ["--kv-offloading-backend", "native", "--kv-offloading-size", str(gib)])
    try:
        info = srv.start()
        info["prefix_caching"] = True
        info["kv_offloading_gib"] = gib
        txt = Path(info["log"]).read_text(errors="replace")
        info["offload_log_lines"] = sorted(set(re.findall(r"[^\n]*(?:OffloadingConnector|CPUOffloadingSpec|"
                                                          r"kv_offloading_size)[^\n]*", txt)))[:6]
        info["host_mem"] = R5.host_mem(srv.proc.pid)
        m = X.meta_load()
        m.setdefault("servers", []).append(dict(stage=args.stage, started=datetime.now().isoformat(), **info))
        import torch
        import vllm
        m["stack"] = dict(venv=sys.prefix, vllm=vllm.__version__, torch=torch.__version__, cuda=torch.version.cuda)
        X.meta_save(m)
        X.log(f"[{args.stage}] KV {info.get('kv_cache_tokens')} tokens; offload {gib} GiB; mem {info['host_mem']}")
        for spec in specs:
            X.CURRENT.write_text(json.dumps(dict(cell=spec["tag"])))
            summ, ver = asyncio.run(run_cell(spec, srv.proc.pid))
            if ver["verified"] is False and args.stage != "smoke":    # smoke D=4 fits in GPU KV: no host hits
                raise SystemExit(f"{spec['tag']}: offload host-hit verification FAILED {ver} — STOP")
    finally:
        srv.stop()
    from _provenance import stamp  # noqa: E402
    m = X.meta_load()
    m.setdefault("_provenance", []).append(stamp(script="study_rh6_offload_knee.py", model="qwen3vl-32b-instruct",
                                                 device=X.DEV, args=args))
    X.meta_save(m)


if __name__ == "__main__":
    main()
