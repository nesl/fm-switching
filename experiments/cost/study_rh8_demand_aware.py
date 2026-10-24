#!/usr/bin/env python3
"""StudyRH8 — does demand-aware partial warm state beat all-eager and all-lazy? (vLLM venv; H100 GPU 3).
Pre-registered in research/EXPERIMENTS.md (StudyRH8). Systems only.

Everything is RH7's (study_rh7_eager_lazy.py): server (RH6 GPU+host server, native offload 256 GiB,
--mm-processor-cache-gb 128, restarted per cell), RH2 plans/seeds, per-device headers, D2 history, uuid reference path,
1x real time, 15-min window, greedy, max_tokens 1 append / 4 escalation, 2,400-s drain cap, cache-miss fallback
(re-send once with every frame's bytes; TTFT from the original submit). What changes is per-device:
  DEMAND  high-demand devices = random.Random(0).sample(range(D), D // 4) (escalate every question, rate 1.0); every
          other device escalates a fixed random 20 % of its plan's questions (random.Random(0), devices in index
          order, int(round(0.2 n)) of each device's plan questions — RH2's esc_subset convention). The subset depends
          only on D, so it is the same in every policy.
  POLICY  per device: eager = EAGER-DELTA (warm-up uploads the history once; append every 10 s with new frames'
          bytes + uuid refs); lazy = LAZY-DELTA (no appends; each escalation sends bytes only for frames not sent at
          the device-session's previous escalation).
          ALL-EAGER: every device eager.  ALL-LAZY: every device lazy-delta.
          MIX-RANDOM: random.Random(1).sample(range(D), D // 4) eager (independent of demand).
          MIX-DEMAND: exactly the high-demand devices eager.
  REP     ALL-EAGER / ALL-LAZY at D=64 with RH7's demand (every device rate 1.0) — RH7 EAGER_D64 / LAZYD_D64 repeats.
  --stage estimate  runtime estimate from RH7's measured per-cell wall times (no GPU); STOP if > 8 h
  --stage smoke     D=8, 60-s window, MIX-DEMAND and MIX-RANDOM (code path only; not a result)
  --stage fleet     8 policy cells (D in {64, 96}) then the 2 repeats; STOP on host-hit verification failure or
                    cache-miss fallbacks > 3 % of a cell's requests
"""
import argparse
import asyncio
import json
import random
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import study_rh7_eager_lazy as R7  # noqa: E402

R6, X, F, H, R5 = R7.R6, R7.X, R7.F, R7.H, R7.R5
OUT = Path("results/cost/study_rh8")
REQ = OUT / f"study_rh8_requests_{X.DEV}.jsonl"
MET = OUT / f"study_rh8_metrics_{X.DEV}.jsonl"
CPU = OUT / f"study_rh8_cpu_{X.DEV}.jsonl"
X.META_PATH = OUT / f"study_rh8_run_meta_{X.DEV}.json"
X.CURRENT = Path("logs/study_rh8_current.json")
R7.X.META_PATH = X.META_PATH
DS = (64, 96)
POLICIES = ("ALL-EAGER", "ALL-LAZY", "MIX-RANDOM", "MIX-DEMAND")
HIGH_FRAC, LOW_RATE = 0.25, 0.20
FALLBACK_STOP = 0.03
BUDGET_S = 8 * 3600


# ------------------------------------------------------------------------------------------------ design
def high_demand(D):
    return sorted(random.Random(0).sample(range(D), int(D * HIGH_FRAC)))


def esc_subset(D, plans):
    """None = every question. Else the set of (device, qid) escalated: all of a high-demand device's questions, a fixed
    int(round(0.2 n)) of each other device's plan questions (random.Random(0), devices in index order)."""
    hi = set(high_demand(D))
    rng = random.Random(0)
    sub = set()
    for d, p in enumerate(plans):
        qs = [q["qid"] for s in p for q in s["questions"]]
        pick = qs if d in hi else rng.sample(qs, int(round(LOW_RATE * len(qs))))
        sub |= {(d, q) for q in pick}
    return sub


def eager_set(policy, D):
    return {"ALL-EAGER": list(range(D)), "ALL-LAZY": [], "MIX-RANDOM": sorted(random.Random(1).sample(range(D), D // 4)),
            "MIX-DEMAND": high_demand(D), "REP-EAGER": list(range(D)), "REP-LAZYD": []}[policy]


def spec(policy, D, tag=None, demand="hetero"):
    eg = eager_set(policy, D)
    return dict(tag=tag or f"RH8_{policy}_D{D}", part=policy, policy=policy, D=D, fmt="D2", cadence=10,
                lazy=not eg, offload=256, eager_devices=eg, demand=demand,
                high_demand_devices=high_demand(D) if demand == "hetero" else list(range(D)))


def cells():
    return [spec(p, D) for D in DS for p in POLICIES] + \
        [spec("REP-EAGER", 64, demand="rate1"), spec("REP-LAZYD", 64, demand="rate1")]


# ------------------------------------------------------------------------------------------------ cell
class Cell(R7.Cell):
    def __init__(self, sp, seed=0):
        super().__init__(sp, seed)
        self.eager = set(sp["eager_devices"])
        self.high = set(sp["high_demand_devices"])

    async def post(self, kind, dev, sess_i, sess, upto_s, question=None, qid=None, in_window=True, t_sched=None):
        # every RH8 device uses the delta/uuid body (EAGER-DELTA or LAZY-DELTA); R7.Cell picks it for policy != "LAZY"
        rec = await super().post(kind, dev, sess_i, sess, upto_s, question, qid, in_window, t_sched)
        rec.update(device_policy="EAGER" if dev in self.eager else "LAZYD", high_demand=dev in self.high,
                   warm_device=dev in self.eager, demand=self.spec["demand"])
        return rec


async def device(cell, dev, plan_d, offset, window_end, subset):
    """R6.device with a per-device warm flag and a per-device escalation subset."""
    s_i, sess, start_s = 0, plan_d[0], offset
    t_start = time.time()
    warm, cad = dev in cell.eager, cell.spec["cadence"]
    while True:
        ev = []
        if warm:
            k0 = int(start_s // cad) + 1
            ev += [(k * cad, "append", None) for k in range(k0, int(sess["duration"] // cad) + 1)]
        ev += [(q["qt"], "escalation", q) for q in sess["questions"] if q["qt"] > start_s + 1e-6
               and (subset is None or (dev, q["qid"]) in subset)]
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


def window_plan(sp, seed=0):
    """Scheduled in-window escalations per device and eager-device appends (deterministic; for the trace/estimate)."""
    D = sp["D"]
    plans, offs = H.plan(D, seed)
    sub = esc_subset(D, plans) if sp["demand"] == "hetero" else None
    eg = set(sp["eager_devices"])
    esc = [(d, st) for k, d, st, s in R6.window_events(plans, offs, None, True)
           if sub is None or any((d, q["qid"]) in sub for q in s["questions"] if abs(q["qt"] - st) < 1e-6)]
    app = [e for e in R6.window_events(plans, offs, sp["cadence"], False) if e[0] == "append" and e[1] in eg]
    hi = set(sp["high_demand_devices"])
    return dict(escalations=len(esc), escalations_high=sum(d in hi for d, _ in esc),
                escalations_low=sum(d not in hi for d, _ in esc),
                escalations_on_eager=sum(d in eg for d, _ in esc), appends=len(app), eager_devices=len(eg),
                eager_and_high=len(eg & hi))


async def run_cell(sp, srv_pid, seed=0):
    """R7.run_cell with per-device policy, the demand subset and RH8 output files."""
    t, D = sp["tag"], sp["D"]
    plans, offsets = H.plan(D, seed)
    subset = esc_subset(D, plans) if sp["demand"] == "hetero" else None
    cell = Cell(sp, seed)
    cell.t0 = time.time()
    cell.mem = []
    mem0 = R5.host_mem(srv_pid)
    stop = asyncio.Event()
    sampler = R6.Sampler(srv_pid)
    scr = asyncio.create_task(cell.scrape(stop))
    smp = asyncio.create_task(sampler.run(cell, stop))
    msm = asyncio.create_task(R7.mem_sampler(cell, srv_pid, stop))
    m_start = await R5.scrape_once(cell.client)
    if cell.eager:
        await asyncio.gather(*(cell.post("warmup", d, 0, plans[d][0], offsets[d], in_window=False)
                               for d in sorted(cell.eager)))
    t_w0 = time.time()
    X.log(f"{t}: warm-up {t_w0 - cell.t0:.1f}s ({len(cell.eager)} eager devices); window starts")
    m_w0 = await R5.scrape_once(cell.client)
    window_end = t_w0 + F.WINDOW_S
    await asyncio.gather(*(device(cell, d, plans[d], offsets[d], window_end, subset) for d in range(D)))
    await asyncio.sleep(max(0.0, window_end - time.time()))
    n_inflight = len(cell.inflight)
    m_w1 = await R5.scrape_once(cell.client)
    mem1 = R5.host_mem(srv_pid)
    t_d0 = time.time()
    censored = 0
    if cell.inflight:
        done, pend = await asyncio.wait(list(cell.inflight), timeout=R7.DRAIN_CAP_S)
        censored = len(pend)
        for p in pend:
            p.cancel()
        if pend:
            await asyncio.gather(*pend, return_exceptions=True)
            X.log(f"{t}: DRAIN CAP {R7.DRAIN_CAP_S}s reached; {censored} requests censored")
    drain = time.time() - t_d0
    await asyncio.sleep(1.5)
    m_end = await R5.scrape_once(cell.client)
    stop.set()
    await scr
    await smp
    await msm
    await cell.client.aclose()
    meta = dict(spec=sp, seed=seed, window_s=F.WINDOW_S, window_start=round(t_w0 - cell.t0, 2),
                warmup_s=round(t_w0 - cell.t0, 2), inflight_at_window_end=n_inflight, drain_s=round(drain, 1),
                drain_capped=censored > 0, censored=censored,
                elapsed_window_plus_drain_s=round(time.time() - t_w0, 1), coverage=R6.plan_coverage(D, seed),
                window_plan=window_plan(sp, seed),
                host_mem_start=mem0, host_mem_window_end=mem1, host_mem_end=R5.host_mem(srv_pid), mem_timeline=cell.mem,
                counters=dict(start=m_start, window_start=m_w0, window_end=m_w1, end=m_end))
    with open(REQ, "a") as f:
        for r in cell.records:
            f.write(json.dumps(r) + "\n")
    with open(MET, "a") as f:
        f.write(json.dumps(dict(cell=t, timeline=cell.timeline)) + "\n")
    with open(CPU, "a") as f:
        f.write(json.dumps(dict(cell=t, samples=cell.cpu)) + "\n")
    summ = R6.summarise(cell.records, meta)
    summ["fallbacks"] = sum(r["fallback"] for r in cell.records)
    summ["fallback_frac"] = summ["fallbacks"] / max(1, len(cell.records))
    summ["engine_rss_peak_gib"] = max((x["engine_rss_gib"] or 0 for x in cell.mem), default=None)
    summ["api_rss_peak_gib"] = max((x["api_rss_gib"] or 0 for x in cell.mem), default=None)
    if summ["fallback_frac"] > 0.01:
        X.log(f"{t}: FLAG — cache-miss fallbacks {summ['fallbacks']} = {summ['fallback_frac']:.1%} of requests (> 1 %)")
    ver = R6.verify_host(meta, sp)
    X.log(f"{t}: {len(cell.records)} requests; {summ}; inflight at end {n_inflight}; drain {drain:.0f}s; "
          f"host verification {ver}")
    X.mark_done(t, **meta, summary=summ, host_verification=ver)
    return summ, ver


# ------------------------------------------------------------------------------------------------ estimate
RH7_META = Path("results/cost/study_rh7/study_rh7_run_meta_h100nvl.json")
SMOKE_S = 900


def rh7_wall():
    """RH7's measured wall time per cell (server start of the cell -> server start of the next; last cell: + its
    window, drain and 120-s teardown)."""
    m = json.loads(RH7_META.read_text())
    srv = [(s["stage"], datetime.fromisoformat(s["started"])) for s in m["servers"] if s["stage"].startswith("RH7_")]
    out = {}
    for (a, ta), (_, tb) in zip(srv, srv[1:]):
        out[a] = (tb - ta).total_seconds() + 115           # 'started' is logged after the ~115-s server start
    last = m["experiments"][srv[-1][0]]
    out[srv[-1][0]] = 115 + last["warmup_s"] + last["elapsed_window_plus_drain_s"] + 120
    return out


def estimate():
    w = rh7_wall()
    analog = {"ALL-EAGER": ["EAGER"], "ALL-LAZY": ["LAZYD"], "MIX-RANDOM": ["EAGER", "LAZYD"],
              "MIX-DEMAND": ["EAGER", "LAZYD"], "REP-EAGER": ["EAGER"], "REP-LAZYD": ["LAZYD"]}
    cs = {}
    for c in cells():
        # upper bound: the slower of the RH7 analogues at the same D (RH8 offers <= RH7's escalation load; MIX cells
        # carry 25 % of ALL-EAGER's appends)
        cs[c["tag"]] = round(max(w[f"RH7_{a}_D{c['D']}"] for a in analog[c["policy"]]))
    rep = sum(v for k, v in cs.items() if "REP" in k)
    tot = sum(cs.values()) + SMOKE_S
    return dict(cells_s=cs, total_s=round(tot), total_without_repeats_s=round(tot - rep), rh7_wall_s=w,
                basis="RH7 measured per-cell wall time of the slower analogue policy at the same D; smoke 900 s")


# ------------------------------------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["estimate", "smoke", "fleet"], required=True)
    ap.add_argument("--smoke-dir", help="smoke stage: output directory (not results/)")
    ap.add_argument("--no-repeats", action="store_true", help="drop the D=64 variance repeats (estimate > 8 h)")
    args = ap.parse_args()
    global REQ, MET, CPU
    if args.stage == "smoke":
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
        X.log(f"RUNTIME ESTIMATE: {est['total_s'] / 3600:.2f} h (without repeats "
              f"{est['total_without_repeats_s'] / 3600:.2f} h); cells {est['cells_s']}")
        if est["total_s"] > BUDGET_S:
            if est["total_without_repeats_s"] > BUDGET_S:
                raise SystemExit("RH8 estimate > 8 h even without the repeats — STOP")
            raise SystemExit(2)                       # chain re-runs the fleet with --no-repeats
        return
    S = F.sessions()
    if args.stage == "smoke":
        specs = [spec(p, 8, tag=f"RH8_SMOKE_{p}_D8") for p in ("MIX-DEMAND", "MIX-RANDOM")]
    else:
        specs = [c for c in cells() if not (args.no_repeats and "REP" in c["policy"])]
    specs = [s for s in specs if not X.is_done(s["tag"])]
    if not specs:
        return
    R6.preencode("D2", S)
    for sp in specs:
        srv = R7.start_server(sp["tag"])
        try:
            X.CURRENT.write_text(json.dumps(dict(cell=sp["tag"])))
            summ, ver = asyncio.run(run_cell(sp, srv.proc.pid))
        finally:
            srv.stop()
        if args.stage != "smoke":
            if ver["verified"] is False and ver["external_hit_tokens"]:     # pre-registered: cells with host hits
                raise SystemExit(f"{sp['tag']}: offload host-hit verification FAILED {ver} — STOP")
            if summ["fallback_frac"] > FALLBACK_STOP:
                raise SystemExit(f"{sp['tag']}: cache-miss fallbacks {summ['fallback_frac']:.2%} > 3 % — STOP")
    from _provenance import stamp
    m = X.meta_load()
    m.setdefault("_provenance", []).append(stamp(script="study_rh8_demand_aware.py", model="qwen3vl-32b-instruct",
                                                 device=X.DEV, args=args))
    X.meta_save(m)


if __name__ == "__main__":
    main()
