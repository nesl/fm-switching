#!/usr/bin/env python3
"""StudyD7-capacity — how many standing-query streams can one H100 (GPU 2) carry? Pre-registered (StudyD7-capacity).

Server: D-series vLLM 0.31.0 (study_x_vllm.Server: FA3, max_model_len 32768, gmu 0.90, prefix caching OFF, CUDA graphs)
+ --mm-processor-cache-gb 0, images <= 9, --enable-prompt-tokens-details. Models: 32BI, then 4BI (pinned).
Requests: StudyD3 SMALL requests at N = 3 and N = 9, cycling over the D3 manifest in its fixed order (distinct prompts;
no request repeats within a level), greedy, max_tokens 8, streamed. Bodies are built ahead of time by a producer
thread (bounded prefetch) so the client never delays a send.
Part A (closed loop): concurrency 1, 2, 4, 8, 16, 32; 300 s per level; requests STARTED in the first 30 s discarded.
Part B (open loop): Poisson arrivals (numpy default_rng(seed = 0 + level index)) at 25 / 50 / 75 / 90 / 100 / 110 % of
Part A's peak throughput for that model x N; 300 s of arrivals per level, first 30 s discarded; latency measured from
the SCHEDULED arrival time; dispatch lateness (actual send − scheduled) recorded; no client-side connection limit
(httpx limits None); in-flight requests after the window get up to 120 s to finish, then are counted unfinished.
Per request: scheduled / sent / first-token / end times, TTFT, total, tokens, error. Per level: GPU-2 utilisation and
memory (pynvml, 200 ms). Isolation (study_d10_latency.isolation): waits until no other work of ours runs; VOID on any
in-run overlap. Raw rows -> results/cost/study_d7/study_d7_requests_h100nvl.jsonl.gz (written per level).
"""
import argparse
import asyncio
import gzip
import json
import queue
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import httpx
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "dashcam"))
import study_d10_latency as L  # noqa: E402
import d3_infer_vllm as D3  # noqa: E402
import study_d4_latency as D4  # noqa: E402

C, X = L.C, L.X
OUT = Path("results/cost/study_d7")
REQ = OUT / "study_d7_requests_h100nvl.jsonl.gz"
LEVELS = OUT / "study_d7_levels_h100nvl.jsonl"
META = OUT / "study_d7_run_meta_h100nvl.json"
L.ISO = OUT / "study_d7_isolation_h100nvl.jsonl"
L.DMON = Path("logs/study_d7_dmon.log")
X.META_PATH = META
X.CURRENT = Path("logs/study_d7_current.json")
FLAGS = D4.FLAGS
GEN = dict(temperature=0.0, max_tokens=8, seed=0)
CONCS = (1, 2, 4, 8, 16, 32)
FRACS = (0.25, 0.50, 0.75, 0.90, 1.00, 1.10)
DUR, WARM, DRAIN = 300.0, 30.0, 120.0


class Bodies:
    """Producer thread cycling over the D3 manifest for one N in fixed order; bounded prefetch."""

    def __init__(self, model, n, start=0):
        self.reqs = [r for r in map(json.loads, open(D3.MAN)) if r["n"] == n]
        self.model, self.i = model, start
        self.q = queue.Queue(maxsize=256)
        self.stop = threading.Event()
        self.th = threading.Thread(target=self.loop, daemon=True)
        self.th.start()

    def loop(self):
        while not self.stop.is_set():
            r = self.reqs[self.i % len(self.reqs)]
            self.i += 1
            b, _, _ = D3.body(r, self.model)
            b = dict(b, stream=True, stream_options={"include_usage": True}, **GEN)
            for k in ("logprobs", "top_logprobs"):
                b.pop(k, None)
            while not self.stop.is_set():
                try:
                    self.q.put((r["request_id"], json.dumps(b).encode()), timeout=0.5)
                    break
                except queue.Full:
                    continue

    def get(self):
        return self.q.get()

    def close(self):
        self.stop.set()


class GpuMon:
    def __init__(self):
        import pynvml
        self.nv = pynvml
        pynvml.nvmlInit()
        self.h = pynvml.nvmlDeviceGetHandleByUUID(C.GPU_UUID)
        self.buf, self.ev = [], threading.Event()
        threading.Thread(target=self.loop, daemon=True).start()

    def loop(self):
        while not self.ev.is_set():
            try:
                u = self.nv.nvmlDeviceGetUtilizationRates(self.h).gpu
                mem = self.nv.nvmlDeviceGetMemoryInfo(self.h).used / 2 ** 30
                self.buf.append((time.time(), u, mem, self.nv.nvmlDeviceGetClockInfo(self.h, self.nv.NVML_CLOCK_SM)))
            except self.nv.NVMLError:
                pass
            time.sleep(0.2)

    def window(self, a, b):
        s = [x for x in self.buf if a <= x[0] <= b]
        if not s:
            return {}
        return dict(util_mean=float(np.mean([x[1] for x in s])), util_p50=float(np.median([x[1] for x in s])),
                    mem_gib_max=float(max(x[2] for x in s)), sm_mhz_median=float(np.median([x[3] for x in s])))

    def close(self):
        self.ev.set()


async def one(client, rid, body, sched):
    sent = time.time()
    first, usage, err = None, None, None
    try:
        async with client.stream("POST", f"{X.BASE}/v1/chat/completions", content=body,
                                 headers={"Content-Type": "application/json"}) as r:
            if r.status_code != 200:
                err = f"HTTP {r.status_code}"
                await r.aread()
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
    end = time.time()
    u = usage or {}
    t0 = sched if sched is not None else sent
    return dict(request_id=rid, scheduled=sched, sent=sent, first=first, end=end,
                ttft_s=(first - t0) if first else None, total_s=end - t0, dispatch_late_s=(sent - sched) if sched else 0.0,
                service_ttft_s=(first - sent) if first else None, prompt_tokens=u.get("prompt_tokens"),
                completion_tokens=u.get("completion_tokens"), error=err)


def summarise(rows, t_start, gm, extra):
    keep = [r for r in rows if (r["scheduled"] or r["sent"]) >= t_start + WARM]
    ok = [r for r in keep if not r["error"] and r["ttft_s"] is not None]
    span = DUR - WARM
    tt = np.array([r["ttft_s"] for r in ok]) if ok else np.array([np.nan])
    out = dict(extra, n_started_after_warmup=len(keep), n_ok=len(ok), errors=sum(bool(r["error"]) for r in keep),
               unfinished=sum(1 for r in keep if r.get("unfinished")),
               throughput_rps=len([r for r in ok if r["end"] <= t_start + DUR + DRAIN]) / span,
               ttft_p50=float(np.nanpercentile(tt, 50)), ttft_p90=float(np.nanpercentile(tt, 90)),
               ttft_p99=float(np.nanpercentile(tt, 99)), ttft_max=float(np.nanmax(tt)),
               total_p50=float(np.median([r["total_s"] for r in ok])) if ok else None,
               service_ttft_p50=float(np.median([r["service_ttft_s"] for r in ok])) if ok else None,
               dispatch_late_p99=float(np.percentile([r["dispatch_late_s"] for r in keep], 99)) if keep else None,
               queue_delay_p50=float(np.median([r["ttft_s"] - (r["service_ttft_s"] or 0) for r in ok])) if ok else None,
               prompt_tokens_median=float(np.median([r["prompt_tokens"] for r in ok if r["prompt_tokens"]])) if ok else None,
               gpu=gm.window(t_start + WARM, t_start + DUR))
    return out


async def closed_loop(bodies, conc, gm):
    rows, t_start = [], time.time()
    async with httpx.AsyncClient(timeout=None, limits=httpx.Limits(max_connections=None,
                                                                    max_keepalive_connections=None)) as c:
        async def worker():
            while time.time() < t_start + DUR:
                rid, body = await asyncio.to_thread(bodies.get)
                rows.append(await one(c, rid, body, None))
        await asyncio.gather(*(worker() for _ in range(conc)))
    return rows, t_start


async def open_loop(bodies, rate, seed, gm):
    rng = np.random.default_rng(seed)
    gaps = rng.exponential(1.0 / rate, size=int(rate * DUR * 3) + 10)
    times = np.cumsum(gaps)
    times = times[times < DUR]
    pre = [bodies.get() for _ in range(min(len(times), 64))]
    rows, tasks = [], []
    t_start = time.time() + 1.0
    async with httpx.AsyncClient(timeout=None, limits=httpx.Limits(max_connections=None,
                                                                    max_keepalive_connections=None)) as c:
        for k, t in enumerate(times):
            sched = t_start + float(t)
            if k < len(pre):
                rid, body = pre[k]
            else:
                rid, body = await asyncio.to_thread(bodies.get)
            d = sched - time.time()
            if d > 0:
                await asyncio.sleep(d)
            tasks.append(asyncio.create_task(one(c, rid, body, sched)))
        done, pending = await asyncio.wait(tasks, timeout=DRAIN)
        for t in pending:
            t.cancel()
        for t in done:
            rows.append(t.result())
        rows += [dict(request_id=None, scheduled=None, sent=time.time(), first=None, end=time.time(), ttft_s=None,
                      total_s=None, dispatch_late_s=0.0, service_ttft_s=None, prompt_tokens=None,
                      completion_tokens=None, error="unfinished after drain", unfinished=True) for _ in pending]
    return rows, t_start


def write(rows, tag):
    with gzip.open(REQ, "at") as f:
        for r in rows:
            f.write(json.dumps(dict(r, level=tag)) + "\n")


def done_levels():
    if not LEVELS.exists():
        return {}
    return {(l["model"], l["n"], l["part"], l["level"]): l for l in map(json.loads, open(LEVELS))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wait-clear-h", type=float, default=10.0)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    t_end, clear = time.time() + 3600 * a.wait_clear_h, 0
    while clear < 2:
        clear = 0 if L.isolation("pre-start wait")["overlap"] else clear + 1
        if clear < 2:
            if time.time() > t_end:
                raise SystemExit(3)
            time.sleep(60)
    L.isolation("run start")
    D4.OUT = OUT
    D4.others("run start")
    wt = L.IsoWatch()
    wt.start()
    try:
        for model in ("32BI", "4BI"):
            if D3.gpu_pids():
                raise SystemExit(f"GPU 2 not idle before {model} server start — STOP")
            srv = X.Server(model, FLAGS)
            gm = None
            try:
                info = srv.start()
                m = X.meta_load()
                m.setdefault("servers", []).append(dict(model=model, started=datetime.now().isoformat(), **info,
                                                        flags=FLAGS))
                X.meta_save(m)
                gm = GpuMon()
                for n in (3, 9):
                    done = done_levels()
                    bodies = Bodies(model, n)
                    try:
                        for conc in CONCS:
                            key = (model, n, "A_closed", conc)
                            if key in done:
                                continue
                            X.log(f"D7 {model} N{n} closed conc {conc}")
                            rows, t0 = asyncio.run(closed_loop(bodies, conc, gm))
                            write(rows, f"{model}/N{n}/A/{conc}")
                            s = summarise(rows, t0, gm, dict(model=model, n=n, part="A_closed", level=conc))
                            with open(LEVELS, "a") as f:
                                f.write(json.dumps(s) + "\n")
                            X.log(f"D7 {model} N{n} conc {conc}: {s['throughput_rps']:.2f} rps, p99 TTFT "
                                  f"{s['ttft_p99']:.3f}s, errors {s['errors']}")
                        done = done_levels()
                        peak = max(v["throughput_rps"] for k, v in done.items() if k[:3] == (model, n, "A_closed"))
                        for i, fr in enumerate(FRACS):
                            key = (model, n, "B_open", fr)
                            if key in done:
                                continue
                            rate = fr * peak
                            X.log(f"D7 {model} N{n} open {fr:.2f} x peak {peak:.2f} = {rate:.2f} rps")
                            rows, t0 = asyncio.run(open_loop(bodies, rate, i, gm))
                            write(rows, f"{model}/N{n}/B/{fr}")
                            s = summarise(rows, t0, gm, dict(model=model, n=n, part="B_open", level=fr, rate_rps=rate,
                                                             peak_closed_rps=peak, seed=i))
                            with open(LEVELS, "a") as f:
                                f.write(json.dumps(s) + "\n")
                            X.log(f"D7 {model} N{n} open {fr}: {s['throughput_rps']:.2f} rps, p99 TTFT "
                                  f"{s['ttft_p99']:.3f}s, errors {s['errors']}, unfinished {s['unfinished']}")
                    finally:
                        bodies.close()
                se = [l for l in srv.logpath.read_text(errors="replace").splitlines() if any(k in l for k in D3.SRV_ERR)]
                if se:
                    m = X.meta_load()
                    m.setdefault("server_log_errors", {})[model] = se[:10]
                    X.meta_save(m)
                    raise SystemExit(f"D7 {model}: server log error — STOP: {se[0][:200]}")
            finally:
                if gm:
                    gm.close()
                srv.stop()
    finally:
        wt.stop_ev.set()
    L.isolation("run end")
    D4.others("run end")
    seen = [json.loads(l) for l in open(L.ISO)]
    run = [s for s in seen if s["tag"] != "pre-start wait"]
    m = X.meta_load()
    m["isolation"] = dict(void=any(s["overlap"] for s in run), n_checks=len(run))
    m["settings"] = dict(flags=FLAGS, gen=GEN, server_cfg=X.SERVER_CFG, concs=CONCS, fracs=FRACS, dur_s=DUR,
                         warmup_s=WARM, drain_s=DRAIN)
    from _provenance import stamp
    m.setdefault("_provenance", []).append(stamp(script="study_d7_capacity.py", model="32BI,4BI",
                                                 device=f"{X.DEV}_gpu2", n=0, args=a))
    X.meta_save(m)
    X.log(f"D7 done; VOID={m['isolation']['void']}")


if __name__ == "__main__":
    main()
