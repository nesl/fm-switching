#!/usr/bin/env python3
"""StudyRH5 — host-memory KV offload for warm D2 histories (vLLM venv). Systems construction; no accuracy.
Pre-registered in research/EXPERIMENTS.md (StudyRH5).

Server: RH4's image server (W3.IMAGE_FLAGS) + prefix caching + prompt-token details; config "host" adds vLLM's native
CPU KV offloading (--kv-offloading-backend native --kv-offloading-size 256 GiB -> OffloadingConnector).
History = D2 (RH4): frames at t = 0, 2, 4, ... <= upto at 352x256 as separate PNG images after a header line.

  --stage partA --cfg host|gpu   isolated reload cost (GPU-WARM / HOST-WARM on host; GPU-WARM / COLD on gpu)
  --stage fleet --cfg host|gpu   RH2's P-WARM replay (plans, seeds, timing) at D in {4, 8, 16, 24}
  --stage estimate               runtime estimate (no GPU)
Per-request GPU-vs-host split is not in the API (cached_tokens = local + host-loaded); Part A reads it from /metrics
deltas with one request in flight; the fleet reports window deltas of the local and external prefix-cache counters.
"""
import argparse
import asyncio
import base64
import io
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sember"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
import study_r5_fleet as F  # noqa: E402
import study_rh2_knee_surface as H  # noqa: E402
import study_rh3_inputs as B3  # noqa: E402
import study_rh3_warmable as W3  # noqa: E402
import study_x_vllm as X  # noqa: E402
from rawio import read_jsonl  # noqa: E402

OUT = Path("results/cost/study_rh5")
REQ = OUT / f"study_rh5_requests_{X.DEV}.jsonl"
MET = OUT / f"study_rh5_metrics_{X.DEV}.jsonl"
PARTA = OUT / f"study_rh5_partA_{X.DEV}.jsonl"
X.META_PATH = OUT / f"study_rh5_run_meta_{X.DEV}.json"
X.CURRENT = Path("logs/study_rh5_current.json")
STRIDE_S, SIZE = 2, (352, 256)
OFFLOAD_GIB = 256
CFG_FLAGS = {"gpu": [], "host": ["--kv-offloading-backend", "native", "--kv-offloading-size", str(OFFLOAD_GIB)]}
SERVER_BASE = W3.IMAGE_FLAGS + ["--enable-prefix-caching", "--enable-prompt-tokens-details"]
DS = (4, 8, 16, 24)
BUDGET_S = 6 * 3600
METRIC_PAT = re.compile(r"^(vllm:(?:[a-z_]*prefix_cache[a-z_]*|kv_offload[a-z_]*|num_preemptions[a-z_]*|"
                        r"kv_cache_usage_perc|num_requests_running|num_requests_waiting|prompt_tokens_total|"
                        r"generation_tokens_total|external[a-z_]*))(?:\{[^}]*\})? ([0-9.eE+-]+)$")
PART_A_SIZES = {"11k": 240.0, "28k": 618.0}
PART_A_REPS = 3
FILL_FACTOR = 1.5

_B64 = {}


def img(path):
    if path not in _B64:
        im = B3.load(path, SIZE)
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        _B64[path] = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    return _B64[path]


def d2_frames(sess, upto_s):
    return [(t, p) for t, p in sess["frames"] if t <= upto_s + 1e-6 and t % STRIDE_S == 0]


def content(header, sess, upto_s, question=None):
    c = [{"type": "text", "text": header}] + [{"type": "image_url", "image_url": {"url": img(p)}}
                                              for _, p in d2_frames(sess, upto_s)]
    return c + ([{"type": "text", "text": question}] if question else [])


def header(tag, dev, sess_i):
    return (f"[{tag}] device {dev:02d} session {sess_i}: egocentric camera history, one frame every {STRIDE_S} s "
            f"from the session start.")


async def scrape_once(client):
    txt = (await client.get(f"{X.BASE}/metrics")).text
    row = {}
    for line in txt.splitlines():
        m = METRIC_PAT.match(line)
        if m:
            k = m.group(1).split(":", 1)[1]
            row[k] = row.get(k, 0.0) + float(m.group(2))
    return row


def host_mem(pid):
    """RSS of the server process tree (GiB) + host MemAvailable (GiB)."""
    try:
        import psutil
        p = psutil.Process(pid)
        rss = sum(c.memory_info().rss for c in [p] + p.children(recursive=True)) / 2 ** 30
    except Exception:  # noqa: BLE001
        rss = None
    avail = None
    for line in open("/proc/meminfo"):
        if line.startswith("MemAvailable"):
            avail = int(line.split()[1]) / 2 ** 20
    return dict(server_tree_rss_gib=rss, host_mem_available_gib=avail)


class Cell(F.Cell):
    """F.Cell with the D2 history and a scrape of every prefix-cache / offload counter."""
    async def post(self, kind, dev, sess_i, sess, upto_s, question=None, qid=None, in_window=True):
        body = dict(model="32BI", temperature=0.0, max_tokens=1 if kind not in ("escalation", "probe_esc") else
                    F.ESC_MAX_TOKENS, stream=True, stream_options={"include_usage": True},
                    messages=[{"role": "user", "content": await asyncio.to_thread(
                        content, header(self.tag, dev, sess_i), sess, upto_s, question)}])
        n_frames = len(d2_frames(sess, upto_s))
        t_sub = time.time()
        first, usage, err = None, None, None
        try:
            async with self.client.stream("POST", f"{X.BASE}/v1/chat/completions", json=body) as r:
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
        rec = dict(cell=self.tag, policy=self.policy, D=self.D, esc_frac=self.esc_frac, kind=kind, device=dev,
                   session=sess_i, video_id=sess["video_id"], session_t=round(upto_s, 1), n_frames=n_frames,
                   question_id=qid, in_window=in_window, t_submit=round(t_sub - self.t0, 3),
                   ttft_s=round(first - t_sub, 3) if first else None, latency_s=round(t_end - t_sub, 3),
                   prompt_tokens=usage and usage["prompt_tokens"],
                   cached_tokens=((usage or {}).get("prompt_tokens_details") or {}).get("cached_tokens"),
                   completion_tokens=usage and usage["completion_tokens"], error=err, warm_device=True)
        self.records.append(rec)
        return rec

    async def scrape(self, stop):
        while not stop.is_set():
            try:
                row = await scrape_once(self.client)
                row["t"] = round(time.time() - self.t0, 2)
                self.timeline.append(row)
            except httpx.HTTPError:
                pass
            await asyncio.sleep(1.0)


# ------------------------------------------------------------------------------------------------ Part A
async def part_a(cfg, srv_pid):
    S = F.sessions()
    pools = {"11k": [s for s in S if s["duration"] >= PART_A_SIZES["11k"]][:4],
             "28k": [s for s in S if s["duration"] >= PART_A_SIZES["28k"]]}
    used = {s["video_id"] for v in pools.values() for s in v}
    fillers = [s for s in S if s["video_id"] not in used and s["duration"] >= 440][:12]
    kv = X.meta_load()["servers"][-1].get("kv_cache_tokens") or 62944
    cell = Cell(f"RH5A_{cfg}", "WARM", 1, 1.0)
    cell.t0 = time.time()
    rows = []
    second = "HOST-WARM" if cfg == "host" else "COLD"

    async def measured(state, size, s, rep, tag, dev, upto, question):
        m0 = await scrape_once(cell.client)
        cell.tag = tag
        r = await cell.post("escalation", dev, 0, s, upto, question=question)
        await asyncio.sleep(1.5)                      # let the 1-s-updated counters settle
        m1 = await scrape_once(cell.client)
        d = {k: m1.get(k, 0.0) - m0.get(k, 0.0) for k in set(m0) | set(m1) if not k.startswith("kv_cache_usage")
             and not k.startswith("num_requests")}
        row = dict(cfg=cfg, state=state, size=size, video_id=s["video_id"], rep=rep, upto_s=upto,
                   n_frames=r["n_frames"], prompt_tokens=r["prompt_tokens"], cached_tokens=r["cached_tokens"],
                   ttft_s=r["ttft_s"], latency_s=r["latency_s"], error=r["error"], metric_deltas=d,
                   **host_mem(srv_pid))
        rows.append(row)
        X.log(f"partA {cfg} {state} {size} {s['video_id'][:12]} rep{rep}: prompt {r['prompt_tokens']} cached "
              f"{r['cached_tokens']} ttft {r['ttft_s']} | " + ", ".join(f"{k} {v:.0f}" for k, v in sorted(d.items())
                                                                        if v and ("hit" in k or "load" in k
                                                                                  or "store" in k)))
        return row

    fi = 0
    for size, pool in pools.items():
        upto = PART_A_SIZES[size]
        for rep in range(PART_A_REPS):
            for si, s in enumerate(pool):
                tag = f"RH5A_{cfg}_{size}_r{rep}"
                cell.tag = tag
                q = s["questions"][-1]["text"]
                a = await cell.post("append", si, 0, s, upto)                   # history resident on GPU
                await measured("GPU-WARM", size, s, rep, tag, si, upto, q)
                # evict: other sessions' histories through the cache until >= FILL_FACTOR x GPU KV
                filled = 0
                while filled < FILL_FACTOR * kv:
                    f = fillers[fi % len(fillers)]
                    fi += 1
                    cell.tag = f"RH5A_{cfg}_fill{fi}"
                    fr = await cell.post("filler", 0, 0, f, min(f["duration"], 440.0))
                    filled += fr["prompt_tokens"] or 0
                await measured(second, size, s, rep, tag, si, upto, q)
                rows[-1]["append_prompt_tokens"] = a["prompt_tokens"]
                rows[-1]["filler_tokens"] = filled
    await cell.client.aclose()
    with open(PARTA, "a") as fo:
        for r in rows:
            fo.write(json.dumps(r) + "\n")
    return rows


def verify_a(rows):
    """Pre-registered verification. Returns (ok, per-row verdicts)."""
    out, ok = [], True

    def g(d, *names):
        return sum(v for k, v in d.items() if any(k.startswith(n) for n in names))
    for r in rows:
        d, hist = r["metric_deltas"], r["prompt_tokens"] or 0
        local = g(d, "prefix_cache_hits")
        ext = g(d, "external_prefix_cache_hits")
        load = g(d, "kv_offload_load_bytes")
        need = 0.9 * (hist - 300)          # the history part of the prompt (question + template ~150-300 tokens)
        if r["state"] == "GPU-WARM":
            v = local >= need and ext <= 64
        elif r["state"] == "HOST-WARM":
            v = local <= 64 and ext >= need and load > 0
            ok &= bool(v) and not r["error"]
        else:
            v = (r["cached_tokens"] or 0) <= 64
        out.append(dict(state=r["state"], size=r["size"], video_id=r["video_id"], rep=r["rep"], local_hits=local,
                        external_hits=ext, load_bytes=load, verified=bool(v)))
    return ok, out


# ------------------------------------------------------------------------------------------------ fleet
async def run_cell(cfg, D, srv_pid, seed=0):
    t = f"RH5_{cfg.upper()}_D{D}"
    plans, offsets = H.plan(D, seed)
    cell = Cell(t, "WARM", D, 1.0, seed)
    cell.t0 = time.time()
    mem0 = host_mem(srv_pid)
    stop = asyncio.Event()
    scr = asyncio.create_task(cell.scrape(stop))
    await asyncio.gather(*(cell.post("warmup", d, 0, plans[d][0], offsets[d], in_window=False) for d in range(D)))
    t_w0 = time.time()
    X.log(f"{t}: warm-up {t_w0 - cell.t0:.1f}s; window starts")
    window_end = t_w0 + F.WINDOW_S
    await asyncio.gather(*(H.device(cell, d, plans[d], offsets[d], window_end, None) for d in range(D)))
    n_inflight = len(cell.inflight)
    mem1 = host_mem(srv_pid)
    t_d0 = time.time()
    if cell.inflight:
        await asyncio.gather(*list(cell.inflight))
    drain = time.time() - t_d0
    stop.set()
    await scr
    await cell.client.aclose()
    meta = dict(cfg=cfg, policy="WARM", D=D, esc_frac=1.0, seed=seed, window_s=F.WINDOW_S,
                window_start=round(t_w0 - cell.t0, 2), warmup_s=round(t_w0 - cell.t0, 2),
                inflight_at_window_end=n_inflight, drain_s=round(drain, 1), host_mem_start=mem0,
                host_mem_window_end=mem1, host_mem_end=host_mem(srv_pid))
    with open(REQ, "a") as f:
        for r in cell.records:
            f.write(json.dumps(r) + "\n")
    with open(MET, "a") as f:
        f.write(json.dumps(dict(cell=t, timeline=cell.timeline)) + "\n")
    esc = [r for r in cell.records if r["kind"] == "escalation" and r["in_window"] and not r["error"]]
    tt = [r["ttft_s"] for r in esc if r["ttft_s"] is not None]
    summ = dict(n=len(esc), ttft_median=float(np.median(tt)) if tt else None,
                ttft_p99=float(np.percentile(tt, 99)) if tt else None,
                hit=round(sum(r["cached_tokens"] or 0 for r in esc) / max(1, sum(r["prompt_tokens"] or 0
                                                                                 for r in esc)), 4))
    X.log(f"{t}: {len(cell.records)} requests; {summ}; errors {sum(bool(r['error']) for r in cell.records)}; "
          f"inflight at end {n_inflight}; drain {drain:.0f}s; mem {meta['host_mem_end']}")
    X.mark_done(t, **meta, summary=summ)
    _B64.clear()
    return summ


def window_appends(plans, offsets):
    """(device, session_t) of every in-window append, exactly as H.device schedules them (rate 1.0, P-WARM)."""
    out = []
    for d, plan_d in enumerate(plans):
        t_rel, s_i, sess, st0 = 0.0, 0, plan_d[0], offsets[d]
        while True:
            for k in range(int(st0 // F.APPEND_EVERY_S) + 1, int(sess["duration"] // F.APPEND_EVERY_S) + 1):
                if t_rel + (k * F.APPEND_EVERY_S - st0) <= F.WINDOW_S:
                    out.append((d, k * F.APPEND_EVERY_S, sess))
            t_rel += sess["duration"] - st0
            s_i += 1
            if s_i >= len(plan_d) or t_rel > F.WINDOW_S:
                break
            sess, st0 = plan_d[s_i], 0.0
    return out


def estimate():
    """Fluid model on RH2's measured loaded throughput (WARM D24: 10.8k computed tok/s): per cell warm-up (60 s) +
    900 s + drain, drain = max(0, computed demand / 11k tok/s - 900). Demand per in-window append = its whole D2
    history if the warm set misses (gpu config with mean footprint > 0.85x KV), else only the 5 new frames.
    Footprint = mean over appends of (D x that append's history tokens) / KV."""
    kv, thr, tok = 62944, 11000.0, 92
    per = {}
    for cfg in ("host", "gpu"):
        for D in DS:
            plans, offs = H.plan(D)
            ev = window_appends(plans, offs)
            h = np.array([len(d2_frames(s, st)) * tok for _, st, s in ev], float)
            foot = D * h.mean() / kv
            miss = cfg == "gpu" and foot > 0.85
            demand = h.sum() if miss else len(ev) * (5 * 90 + 60)
            drain = max(0.0, demand / thr - F.WINDOW_S)
            per[f"RH5_{cfg.upper()}_D{D}"] = dict(s=round(60 + F.WINDOW_S + drain), appends=len(ev),
                                                  mean_history=round(h.mean()), footprint=round(foot, 2),
                                                  drain_s=round(drain))
    part_a = 2 * 30 * 60
    servers = 2 * 180
    tot = sum(v["s"] for v in per.values()) + part_a + servers
    return dict(per_cell=per, part_a_s=part_a, servers_s=servers, total_s=tot)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["estimate", "partA", "fleet"], required=True)
    ap.add_argument("--cfg", choices=["host", "gpu"])
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if args.stage == "estimate":
        est = estimate()
        m = X.meta_load()
        m["estimate"] = est
        X.meta_save(m)
        X.log(f"RUNTIME ESTIMATE: {est['total_s'] / 3600:.2f} h {json.dumps(est['per_cell'])}")
        if est["total_s"] > BUDGET_S:
            raise SystemExit(f"RH5 estimate {est['total_s'] / 3600:.2f} h > 6 h — STOP")
        return
    srv = X.Server("32BI", SERVER_BASE + CFG_FLAGS[args.cfg])
    try:
        info = srv.start()
        info["prefix_caching"] = True
        info["kv_offloading"] = args.cfg == "host"
        txt = Path(info["log"]).read_text(errors="replace")
        info["offload_log_lines"] = sorted(set(re.findall(r"[^\n]*(?:[Oo]ffload|OffloadingConnector|CPU blocks|"
                                                          r"pinned)[^\n]*", txt)))[:20]
        info["host_mem"] = host_mem(srv.proc.pid)
        m = X.meta_load()
        m.setdefault("servers", []).append(dict(cfg=args.cfg, stage=args.stage, started=datetime.now().isoformat(),
                                                **info))
        import torch
        import vllm
        m["stack"] = dict(venv=sys.prefix, vllm=vllm.__version__, torch=torch.__version__, cuda=torch.version.cuda)
        X.meta_save(m)
        X.log(f"[{args.cfg}] KV cache capacity: {info.get('kv_cache_tokens')} tokens; offload lines "
              f"{info['offload_log_lines'][:4]}; mem {info['host_mem']}")
        if args.stage == "partA":
            rows = asyncio.run(part_a(args.cfg, srv.proc.pid))
            ok, ver = verify_a(rows)
            m = X.meta_load()
            m.setdefault("partA_verification", {})[args.cfg] = dict(host_warm_all_verified=ok, rows=ver)
            X.meta_save(m)
            X.log(f"PART A {args.cfg} verification: {sum(v['verified'] for v in ver)}/{len(ver)} rows verified; "
                  f"HOST-WARM all verified: {ok}")
            if args.cfg == "host" and not ok:
                raise SystemExit("PART A: HOST-WARM not confirmed as host-served — STOP")
        else:
            for D in DS:
                t = f"RH5_{args.cfg.upper()}_D{D}"
                if X.is_done(t):
                    continue
                X.CURRENT.write_text(json.dumps(dict(cell=t)))
                asyncio.run(run_cell(args.cfg, D, srv.proc.pid))
    finally:
        srv.stop()
    from _provenance import stamp  # noqa: E402
    m = X.meta_load()
    m.setdefault("_provenance", []).append(stamp(script="study_rh5_host_offload.py", model="qwen3vl-32b-instruct",
                                                 device=X.DEV, args=args))
    X.meta_save(m)


if __name__ == "__main__":
    main()
