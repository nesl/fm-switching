#!/usr/bin/env python3
"""StudyENG1b-prefix-survival: how long does an already-built, UNREFERENCED history prefix survive on the GPU between
reconstruction pieces, and what happens to it when evicted? EXCLUSIVE (vLLM venv; h100nvl GPU 2). Pre-registered in
research/EXPERIMENTS.md (StudyENG1b-prefix-survival; design answers by the user 2026-11-15, points 1 to 4).

Reuses StudyENG1 (experiments/cost/study_eng1_steptime.py) UNCHANGED for servers (flags checked exactly, ENG1
stat-logger plugin, front-end log rows), request builders (uuid-fresh D14 episodic bodies, D2 histories in fresh
namespaces, prefix-chained pieces), metrics scraping, warm sessions (W25) and the monitor exemption for the user's own
non-GPU file activity (ENG1 amendment 3).
Trial: fresh namespace; 5 prefix-chained pieces of 23 frames (~2,048 tokens) or 11 frames (~1,024) on a ~28k
StudySLICE1 session (piece 1 cold, later pieces gap <= 32 tokens); then a gap G with background demand; at the gap
end the resume piece (6th piece) is issued regardless of background state. Loads: P25 / P40 episodic (a); the same
plus filler history builds of f x (KV capacity - prefix tokens) tokens, f in {0.25, 0.5, 1.0, 1.5}, issued one after
the other from the gap start until the target is issued or the resume piece completes (b); W25 (Poisson 25 % + 8 warm
sessions; on E0 the 'W25-E0 variant' without a host tier) (c).
Rows -> results/cost/study_eng1b/eng1b_{trials,requests,frontend}_h100nvl.jsonl, steps eng1b_steps/<label>.jsonl.gz,
monitor, meta eng1b_run_meta_h100nvl.json. Smoke: eng1b_smoke_*.
"""
import argparse
import asyncio
import itertools
import json
import random
import sys
import threading
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import study_eng1_steptime as M  # noqa: E402  (StudyENG1 harness, unchanged)

E, X, F, R6, R7, H = M.E, M.X, M.F, M.R6, M.R7, M.H
OUT = M.REPO / "results/cost/study_eng1b"
SIZES = {2048: 23, 1024: 11}
NPIECES = 5
GAPS = {2048: (0.5, 2.0, 5.0, 10.0, 20.0), 1024: (2.0, 10.0)}
FILLS = (0.25, 0.5, 1.0, 1.5)
LOADS_A = ("P25", "P40")
LOADS_B = tuple(f"{p}_f{f:g}" for p in LOADS_A for f in FILLS)
LOADS_C = ("W25",)
REPS = 6
EP_TAIL = 2.0          # episodic arrivals continue 2 s past the gap end (the resume piece runs under load)
GUARD_H = 6.0
ST = dict(t_guard0=None, smoke=False, cap=None)


def set_paths(smoke):
    pre = "eng1b_smoke" if smoke else "eng1b"
    OUT.mkdir(parents=True, exist_ok=True)
    for k in ("trials", "requests", "frontend"):
        M.P[k] = OUT / f"{pre}_{k}_h100nvl.jsonl"
    M.P["partC"] = M.P["requests"]                 # warm Cell rows are written by our code only
    M.P["steps"] = OUT / f"{pre}_steps"
    M.P["steps"].mkdir(exist_ok=True)
    E.MON = OUT / f"{pre}_monitor_h100nvl.jsonl"
    X.META_PATH = OUT / f"{pre}_run_meta_h100nvl.json"
    X.CURRENT = M.REPO / "logs/eng1b_current.json"
    M.G.X.META_PATH = X.META_PATH


def guard_ok():
    if ST["smoke"] or ST["t_guard0"] is None:
        return True
    return (time.time() - ST["t_guard0"]) / 3600 < GUARD_H


class GuardStop(Exception):
    pass


def cells(server):
    """(size, load, gap, rep) in the pre-registered order for one server type: 2,048 non-W25 (seeded order), then
    2,048 W25; the 1,024 cells form their own server loads (see main)."""
    rng = random.Random(20261116 + (0 if server == "E0" else 1))
    main_ = [(2048, ld, g, r) for ld in LOADS_A + LOADS_B for g in GAPS[2048] for r in range(REPS)]
    rng.shuffle(main_)
    w = [(2048, ld, g, r) for ld in LOADS_C for g in GAPS[2048] for r in range(REPS)]
    rng.shuffle(w)
    small = [(1024, ld, g, r) for ld in LOADS_B for g in GAPS[1024] for r in range(REPS)]
    rng.shuffle(small)
    return main_ + w, small


def ep_seed(load, rep, gi):
    frac = 0.40 if load.startswith("P40") else 0.25
    return M.SEED_IDX[frac] + 100 * rep + 10 * gi, frac


def poisson(rate, dur, seed):
    rng = np.random.default_rng(seed)
    t = np.cumsum(rng.exponential(1.0 / rate, size=int(rate * dur * 3) + 10))
    return [float(x) for x in t[t < dur]]


async def filler_runner(c, target, k0, ns, rows, stop_ev):
    """Other devices' history builds: fresh ~26k histories (truncated to the remaining target), one after another."""
    issued = 0
    k = 0
    while issued < target and not stop_ev.is_set():
        p = M.SESS["p28"][(k0 + k) % 20]
        nfr = min(len(p["frames"]), max(1, int(round((target - issued - 31) / 90))))
        h = M.Hist(p["frames"][:nfr], f"{ns}F{k}")
        rid = f"{ns}-fill{k}"
        issued += 31 + 90 * nfr
        r = await M.post(c, h.body(rid=rid), rid, "filler", n_frames=nfr, issued_cum=issued)
        rows.append(r)
        k += 1


async def trial(c, server, size, load, gap, rep, tag, extra=None):
    nfr = SIZES[size]
    gi = GAPS[size].index(gap) if gap in GAPS[size] else 0
    ns = M.new_ns("S")
    p = M.SESS["p28"][(rep * 7 + gi + (0 if size == 2048 else 3)) % 20]
    frames = p["frames"]
    base = dict(server=server, size=size, load=load, gap=gap, rep=rep, ns=ns, tag=tag, **(extra or {}))
    rows = []
    cell = plans = offsets = None
    warm = load.startswith("W25")
    if warm:                                                   # warm-up BEFORE the build (unscored)
        sp = R7.spec("EAGER", 8, tag=f"{ns}w")
        sp["offload"] = 256 if server == "KVHOST" else 0
        cell = R7.Cell(sp, 0)
        cell.t0 = time.time()
        plans, offsets = H.plan(8, 100 + rep)
        await asyncio.gather(*(cell.post("warmup", d, 0, plans[d][0], offsets[d], in_window=False) for d in range(8)))
        await asyncio.sleep(1.0)
    # build: 5 prefix-chained pieces
    h = M.Hist(frames[:nfr], ns)
    r = await M.build(c, h, "requests", **base, role="piece1")
    builds = [r]
    for k in range(1, NPIECES):
        new = frames[k * nfr:(k + 1) * nfr]
        rid = f"{ns}-b{k}"
        prev = h.prompt_tokens
        r = await M.post(c, h.body(new, rid=rid), rid, "piece", **base, role=f"piece{k + 1}")
        g = M.gap_of(r, prev)
        r["prefix_gap"] = g
        rows.append(r)
        builds.append(r)
        if r["error"] or g is None or g > 32:
            M.write("requests", rows)
            raise SystemExit(f"{ns} piece {k + 1}: prefix gap {g} ({r['error']}): chaining failed, STOP")
        h.frames += new
        h.sent.update(new)
        h.prompt_tokens = r["prompt_tokens"]
    prefix_tok = h.prompt_tokens
    m_build = await M.metrics(c)
    # gap with background demand
    stop_ev = asyncio.Event()
    bg = []
    fill_rows = []
    t_g0 = time.time()
    target = 0
    if load != "none":
        seed, frac = ep_seed(load, rep, gi)
        arr = poisson(frac * M.PEAK1, gap + EP_TAIL, seed)
        pool = M.ep_pool()
        idx = np.random.default_rng(seed + 50000).choice(len(pool), size=len(arr), replace=False)
        for i, (a, j) in enumerate(zip(arr, idx)):
            rid = f"{ns}-ep{i}"
            bg.append(asyncio.create_task(M.post_at(c, t_g0 + a, M.ep_body(pool[int(j)], ns, rid), rid, "episodic",
                                                    idx=i, arrival_rel=round(a, 4))))
    if "_f" in load:
        f = float(load.split("_f")[1])
        target = int(f * (ST["cap"] - prefix_tok))
        bg.append(asyncio.create_task(filler_runner(c, target, rep + gi, ns, fill_rows, stop_ev)))
    if warm:
        async def devs():
            await asyncio.gather(*(R6.device(cell, d, plans[d], offsets[d], t_g0 + gap + EP_TAIL) for d in range(8)))
        bg.append(asyncio.create_task(devs()))
    # resume at the gap end, regardless of background state
    await asyncio.sleep(max(0.0, t_g0 + gap - time.time()))
    m_res = await M.metrics(c)
    new = frames[NPIECES * nfr:(NPIECES + 1) * nfr]
    rid = f"{ns}-resume"
    t_issue = time.time()
    fill_done_before = sum(1 for x in fill_rows if x["t_end"] <= t_issue)
    fill_tok_done = sum((x["prompt_tokens"] or 0) for x in fill_rows if x["t_end"] <= t_issue)
    res = await M.post(c, h.body(new, rid=rid), rid, "resume", **base, role="resume")
    m_after = await M.metrics(c)
    stop_ev.set()
    await asyncio.gather(*bg, return_exceptions=True)
    if warm:
        if cell.inflight:
            await asyncio.wait(list(cell.inflight), timeout=300)
        for x in cell.records:
            if x["kind"] != "warmup":
                rows.append(dict(x, **base, kind="warm_" + x["kind"]))
        await cell.client.aclose()
    for t in bg:
        if not t.cancelled() and isinstance(t.result(), dict):
            rows.append(dict(t.result(), **base))
    rows += [dict(x, **base) for x in fill_rows]
    rows.append(dict(res, prefix_tokens=prefix_tok))
    M.write("requests", rows)
    fill_started = len(fill_rows)
    trow = dict(base, prefix_tokens=prefix_tok, t_gap_start=round(t_g0, 6), t_resume_issue=round(t_issue, 6),
                resume_rid=rid, resume_prompt=res["prompt_tokens"], resume_cached=res["cached_tokens"],
                resume_ttft=res["ttft_s"], resume_error=res["error"],
                prefix_cached_frac=((res["cached_tokens"] or 0) / prefix_tok) if prefix_tok else None,
                filler_target=target, filler_requests=fill_started, filler_done_before_resume=fill_done_before,
                filler_tokens_done_before_resume=fill_tok_done,
                filler_finished_before_resume=bool(target) and fill_done_before == fill_started and
                sum((x["prompt_tokens"] or 0) for x in fill_rows) >= 0.98 * target,
                kv_usage_after_build=m_build.get("kv_cache_usage_perc"), kv_usage_at_resume=m_res.get("kv_cache_usage_perc"),
                running_at_resume=m_res.get("num_requests_running"), waiting_at_resume=m_res.get("num_requests_waiting"),
                resume_window_delta=M.mdelta(m_res, m_after), gap_window_delta=M.mdelta(m_build, m_res),
                build_ttfts=[b["ttft_s"] for b in builds], kv_capacity_tokens=ST["cap"])
    M.write("trials", [trow])
    X.log(f"{tag} {server} s{size} {load} G{gap:g} r{rep}: prefix {prefix_tok} cached {res['cached_tokens']} "
          f"({trow['prefix_cached_frac']:.2f}) ttft {res['ttft_s']} filler {fill_tok_done}/{target}"
          f"{' ' + res['error'] if res['error'] else ''}")
    await asyncio.sleep(1.0)
    M.check_void()
    return trow


async def block(c, server, lst, tag):
    for size, load, gap, rep in lst:
        if not guard_ok():
            raise GuardStop(f"{tag}: {server} s{size} {load} G{gap} r{rep}")
        await trial(c, server, size, load, gap, rep, tag)


async def smoke_e0(c):
    for r in range(2):            # concurrency-1 attribution: resume with no background (expect a full LOCAL hit)
        await trial(c, "E0", 2048, "none", 2.0, r, "smoke_conc1")
    for r in range(2):            # the smoke cell
        await trial(c, "E0", 2048, "P40_f1", 5.0, r, "smoke_cell")


async def smoke_kvhost(c):
    for r in range(2):            # concurrency-1 attribution on KV-HOST: forced eviction, then resume alone
        await forced_evict(c, r)
    await trial(c, "KVHOST", 2048, "W25", 5.0, 0, "smoke_w25")


async def forced_evict(c, rep):
    """Build, then a filler of 1.5 x (capacity - prefix) run to completion with no other load, then resume alone:
    expect the evicted prefix as an EXTERNAL hit on KV-HOST (attribution check at concurrency 1)."""
    ns = M.new_ns("SF")
    p = M.SESS["p28"][(rep + 11) % 20]
    frames = p["frames"]
    nfr = SIZES[2048]
    base = dict(server="KVHOST", size=2048, load="forced_evict", gap=None, rep=rep, ns=ns, tag="smoke_conc1_evict")
    h = M.Hist(frames[:nfr], ns)
    await M.build(c, h, "requests", **base, role="piece1")
    for k in range(1, NPIECES):
        new = frames[k * nfr:(k + 1) * nfr]
        rid = f"{ns}-b{k}"
        prev = h.prompt_tokens
        r = await M.post(c, h.body(new, rid=rid), rid, "piece", **base, role=f"piece{k + 1}")
        r["prefix_gap"] = M.gap_of(r, prev)
        M.write("requests", [r])
        h.frames += new
        h.sent.update(new)
        h.prompt_tokens = r["prompt_tokens"]
    fill = []
    await filler_runner(c, int(1.5 * (ST["cap"] - h.prompt_tokens)), rep + 5, ns, fill, asyncio.Event())
    M.write("requests", [dict(x, **base) for x in fill])
    await asyncio.sleep(1.0)
    m0 = await M.metrics(c)
    rid = f"{ns}-resume"
    res = await M.post(c, h.body(frames[NPIECES * nfr:(NPIECES + 1) * nfr], rid=rid), rid, "resume", **base,
                       role="resume")
    await asyncio.sleep(0.2)
    d = M.mdelta(m0, await M.metrics(c))
    M.write("requests", [dict(res, prefix_tokens=h.prompt_tokens)])
    M.write("trials", [dict(base, prefix_tokens=h.prompt_tokens, resume_rid=rid, resume_prompt=res["prompt_tokens"],
                            resume_cached=res["cached_tokens"], resume_ttft=res["ttft_s"], resume_window_delta=d,
                            filler_tokens_done_before_resume=sum(x["prompt_tokens"] or 0 for x in fill),
                            kv_capacity_tokens=ST["cap"])])
    X.log(f"forced evict r{rep}: prefix {h.prompt_tokens} cached {res['cached_tokens']} delta "
          f"{ {k: v for k, v in d.items() if 'hits' in k or 'source' in k} }")


def stage(label, kv, fns):
    srv = M.start_server(label, kv, "E0", True, False)
    ST["cap"] = srv.info.get("kv_cache_tokens")
    m = X.meta_load()
    m.setdefault("kv_capacity_tokens", {})[label] = ST["cap"]
    X.meta_save(m)
    if ST["t_guard0"] is None and not ST["smoke"]:
        ST["t_guard0"] = time.time()
        m = X.meta_load()
        m["guard_start"] = F.now()
        X.meta_save(m)
    try:
        for fn, a in fns:
            asyncio.run(M.with_client(fn, *a))
    finally:
        M.stop_server(srv)
        m = X.meta_load()
        m.setdefault("stages_done", []).append(dict(label=label, at=F.now()))
        X.meta_save(m)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    a = ap.parse_args()
    ST["smoke"] = M.ST["smoke"] = a.smoke
    set_paths(a.smoke)
    start = E.snapshot("start")
    if start["ours_outside_job"] or start["foreign_on_gpu"]:
        raise SystemExit(f"not exclusive at start: {start['ours_outside_job']} {start['foreign_on_gpu']}: STOP")
    import torch
    import vllm
    if vllm.__version__ != "0.31.0":
        raise SystemExit(f"vLLM {vllm.__version__} != 0.31.0: STOP")
    m = X.meta_load()
    m["stack"] = dict(venv=sys.prefix, vllm=vllm.__version__, torch=torch.__version__, gpu="h100nvl GPU 2",
                      gpu_uuid=F.GPU_UUID, kv_flags=E.KV, log_flags=M.D.LOGFLAGS, plugin=str(M.PLUGIN_DIR),
                      design=dict(SIZES=SIZES, NPIECES=NPIECES, GAPS=GAPS, FILLS=FILLS, REPS=REPS, EP_TAIL=EP_TAIL,
                                  GUARD_H=GUARD_H),
                      monitor_user_exempt=M.USER_EXEMPT)
    m["smoke"] = a.smoke
    X.meta_save(m)
    th = threading.Thread(target=E.monitor, daemon=True)
    th.start()
    remaining = []
    try:
        M.load_sessions(warm=True)
        if a.smoke:
            stage("SMK_E0", "KVGPU", [(smoke_e0, ())])
            stage("SMK_KVHOST", "KVHOST", [(smoke_kvhost, ())])
        else:
            e0_main, e0_small = cells("E0")
            kh_main, kh_small = cells("KVHOST")
            plan = [("E0_2048", "KVGPU", "E0", e0_main), ("KVHOST_2048", "KVHOST", "KVHOST", kh_main),
                    ("E0_1024", "KVGPU", "E0", e0_small), ("KVHOST_1024", "KVHOST", "KVHOST", kh_small)]
            m = X.meta_load()
            m["plan"] = {lab: [list(x) for x in lst] for lab, _, _, lst in plan}
            X.meta_save(m)
            for i, (label, kv, server, lst) in enumerate(plan):
                if not guard_ok():
                    remaining = [p[0] for p in plan[i:]]
                    break
                try:
                    stage(label, kv, [(block, (server, lst, label))])
                except GuardStop as g:
                    remaining = [f"{label} (stopped at {g})"] + [p[0] for p in plan[i + 1:]]
                    X.log(f"6-h guard reached in {label}: stopping")
                    break
    finally:
        E.STOP_MON.set()
        E.snapshot("end")
        m = X.meta_load()
        m["void"] = E.VOID.is_set()
        m["remaining_at_guard"] = remaining
        m["ended"] = F.now()
        X.meta_save(m)
    from _provenance import stamp
    m = X.meta_load()
    m.setdefault("_provenance", []).append(stamp(script="study_eng1b_survival.py", model="qwen3vl-32b-instruct",
                                                 device="h100nvl_gpu2", args=a))
    X.meta_save(m)
    X.log(f"ENG1b {'smoke' if a.smoke else 'full'} finished; remaining {remaining}")


if __name__ == "__main__":
    main()
