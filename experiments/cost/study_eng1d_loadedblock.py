#!/usr/bin/env python3
"""StudyENG1d-loadedblock: how long a request arriving during a long prefill waits for it WHEN THE SERVER IS ALREADY
UNDER EPISODIC LOAD. EXCLUSIVE (vLLM venv; h100nvl GPU 2). Pre-registered in research/EXPERIMENTS.md
(StudyENG1d-loadedblock; design answers by the user 2026-11-17, points 1 to 6 plus the host-CPU monitor requirement).

Stack: StudyENG1 Part C E0 exactly (32B-I @0cfaf481, vLLM 0.31.0, StudySLICE1 E0 flags, prefix caching ON,
--enable-log-requests, --enable-logging-iteration-details, the fixed ENG1 stat-logger plugin). No host tier. The flag
list is diffed against the ENG1 server C_P40_E0 (from eng1_run_meta_h100nvl.json) at every start and must be empty.
Reuses by import (unchanged) study_eng1_steptime.py: start_server / stop_server, request builders (Hist, build,
ep_body, post, post_at), metrics, sessions, the episodic clip pool, pair_check, the exclusivity monitor and the user's
non-GPU exemption. COPIED here and changed (as allowed): ENG1 arrivals / trial_plan (seeds offset by SEED_OFF, so the
traces are new; generator, rates, sizes and image counts unchanged), run_once (only the three actions of this study,
no warm traffic), part_b (reduced to the unloaded control: mono11k and piece2048 at 25 / 50 / 75 %, 5 repetitions)
and StudyENG1c's machine monitor (extended with load average and per-core CPU utilization).
Loaded cells: loads P25 / P40 / S2 / S4 x actions mono11k / piece2048 / piece1024, 20 paired with / without trials
per cell, an independent repeat of the without run on the first 3 FIT trials; HOLDOUT 5 of 20 per cell, written
before any run. Every request's rows, the per-step plugin rows and the front-end log rows are kept; the per-request
blocking fraction, the step composition (DERIVED) and the gates are computed by study_eng1d_analyse.py.
Inline gates (harness arithmetic on its own rows, the ENG1 pattern): the unloaded control's median rho per offset
(ENG1 Part B definition) must fall within ENG1 Part B's p10 to p90 widened by 0.05 (mono11k at 25 / 50 / 75 %,
piece2048 at 25 %); after the P40 block, the median total imposed delay of the P40 mono11k FIT pairs must fall within
ENG1 Part C FIT's p10 to p90 (22.5 to 64.4 s). Either failure stops the run.
Rows -> results/cost/study_eng1d/eng1d[_smoke]_{partC,partB,frontend}_requests_h100nvl.jsonl, steps
eng1d[_smoke]_steps/<label>.jsonl.gz, machine eng1d[_smoke]_machine_h100nvl.jsonl, exclusivity monitor
eng1d[_smoke]_monitor_h100nvl.jsonl, meta eng1d[_smoke]_run_meta_h100nvl.json, split eng1d_holdout_split.json.
"""
import argparse
import asyncio
import json
import os
import random
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import study_eng1_steptime as M  # noqa: E402  (StudyENG1 harness, unchanged)

E, X, F, R7 = M.E, M.X, M.F, M.R7
OUT = M.REPO / "results/cost/study_eng1d"
SPLIT = OUT / "eng1d_holdout_split.json"
ENG1_META = M.REPO / "results/cost/study_eng1/eng1_run_meta_h100nvl.json"
ENG1_REF_SERVER = "C_P40_E0"

# ------------------------------------------------------------------------------------------------ design constants
LOADS = ("P40", "S4", "P25", "S2")            # run order (user: T0's error concentrated at P40 and S4)
ACTIONS = ("mono11k", "piece2048", "piece1024")
LOAD_I = {"P25": 0, "P40": 1, "S2": 2, "S4": 3}
ACT_I = {a: i for i, a in enumerate(ACTIONS)}
NTR, NHOLD, NREP = 20, 5, 3
SEED_OFF = 900000                             # added to every ENG1 Part C trace seed
CTRL_LONG = ("mono11k", "piece2048")
CTRL_OFFS = (0.25, 0.50, 0.75)
CTRL_REPS, CTRL_SOLO = 5, 5
HOST_MARGIN_GIB = 192                         # MemAvailable before each start (128 GiB processor cache + 64 GiB)
CPU_FLAG = 80.0                               # host CPU utilization flag (% of all cores, trial mean)
# ENG1 Part B E0 rho p10 / p90 (results/cost/study_eng1/eng1_results.json, B.E0.cells), widened by 0.05
ENG1_B = {("mono11k", 0.25): (0.9556, 1.0167), ("mono11k", 0.50): (0.9590, 1.0770),
          ("mono11k", 0.75): (0.9194, 1.0723), ("piece2048", 0.25): (0.8413, 0.9078),
          ("piece2048", 0.50): (0.7794, 0.8731), ("piece2048", 0.75): (0.5900, 0.7893)}
CTRL_GATE = (("mono11k", 0.25), ("mono11k", 0.50), ("mono11k", 0.75), ("piece2048", 0.25))
WIDEN = 0.05
XCHECK = ("P40", "mono11k", 22.5, 64.4)       # ENG1 Part C FIT p10 / p90 of total imposed delay (s)

ST = dict(smoke=False, t0=None, mismatch=0, compared=0, label=None, totals={})
P = M.P


def set_paths(smoke):
    pre = "eng1d_smoke" if smoke else "eng1d"
    OUT.mkdir(parents=True, exist_ok=True)
    for k in ("partB", "partC", "frontend"):
        P[k] = OUT / f"{pre}_{k}_requests_h100nvl.jsonl"
    P["steps"] = OUT / f"{pre}_steps"
    P["steps"].mkdir(exist_ok=True)
    P["machine"] = OUT / f"{pre}_machine_h100nvl.jsonl"
    E.MON = OUT / f"{pre}_monitor_h100nvl.jsonl"
    X.META_PATH = OUT / f"{pre}_run_meta_h100nvl.json"
    X.CURRENT = M.REPO / "logs/eng1d_current.json"
    M.G.X.META_PATH = X.META_PATH


def write(key, rows):
    M.write(key, rows)


# ------------------------------------------------------------------------------------------------ HOLDOUT split
def make_split():
    cells = [(l, a) for l in ("P25", "P40", "S2", "S4") for a in ACTIONS]
    rng = random.Random(20261120)
    hold = {f"{l}|{a}": sorted(rng.sample(range(NTR), NHOLD)) for l, a in cells}
    rng2 = random.Random(20261121)
    order = {f"{l}|{a}": ["with_first" if rng2.random() < 0.5 else "without_first" for _ in range(NTR)]
             for l, a in cells}
    rep = {k: [t for t in range(NTR) if t not in v][:NREP] for k, v in hold.items()}
    return dict(study="StudyENG1d-loadedblock", reserved_for="fresh HOLDOUT for StudyT0b; recorded, NOT analysed",
                rule="random.Random(20261120).sample(range(20), 5) per (load, action), stratified by cell, in the "
                     "order loads (P25, P40, S2, S4) x actions (mono11k, piece2048, piece1024)", holdout=hold,
                order_rule="random.Random(20261121): one draw per (cell, trial) in cell order; < 0.5 -> with first",
                order=order, noise_repeat_rule="the first 3 FIT trials of each cell get an independent repeat of the "
                                               "without run", noise_repeat=rep,
                seeds=f"ENG1 Part C trace / injection-time / clip seeds + {SEED_OFF}")


def ensure_split():
    sp = make_split()
    if SPLIT.exists():
        old = json.loads(SPLIT.read_text())
        if old["holdout"] != sp["holdout"] or old["order"] != sp["order"]:
            raise SystemExit("HOLDOUT split file differs from the seeded rule: STOP")
        return old
    sp["written"] = F.now()
    SPLIT.write_text(json.dumps(sp, indent=1))
    X.log(f"HOLDOUT split written: {SPLIT}")
    return sp


# ------------------------------------------------------------------------------------------------ machine monitor
MSTOP = threading.Event()
_CPU_PREV = {}


def cpu_sample():
    """Per-core and total busy % since the previous sample, from /proc/stat (busy = all but idle + iowait)."""
    cur = {}
    for line in open("/proc/stat"):
        if not line.startswith("cpu"):
            break
        p = line.split()
        v = [int(x) for x in p[1:]]
        idle = v[3] + (v[4] if len(v) > 4 else 0)
        cur[p[0]] = (sum(v), idle)
    out = {}
    for k, (tot, idle) in cur.items():
        if k in _CPU_PREV:
            dt, di = tot - _CPU_PREV[k][0], idle - _CPU_PREV[k][1]
            out[k] = round(100.0 * (dt - di) / dt, 1) if dt > 0 else 0.0
    _CPU_PREV.clear()
    _CPU_PREV.update(cur)
    return out


def machine_snapshot():
    q = subprocess.run(["nvidia-smi", "--query-gpu=index,uuid,utilization.gpu,memory.used,power.draw",
                        "--format=csv,noheader,nounits"], capture_output=True, text=True).stdout.strip().splitlines()
    gpus = []
    for line in q:
        p = [x.strip() for x in line.split(",")]
        try:
            gpus.append(dict(index=int(p[0]), uuid=p[1], util=float(p[2]), mem_mib=float(p[3]),
                             power_w=float(p[4]) if p[4] not in ("[N/A]", "N/A") else None))
        except (ValueError, IndexError):
            pass
    mem = {}
    for line in open("/proc/meminfo"):
        k, v = line.split(":")
        if k in ("MemAvailable", "MemFree", "Cached", "Shmem"):
            mem[k] = round(int(v.split()[0]) / 2 ** 20, 2)
    la = os.getloadavg()
    cpu = cpu_sample()
    cores = [cpu[k] for k in sorted((k for k in cpu if k != "cpu"), key=lambda s: int(s[3:]))]
    return dict(t=round(time.time(), 3), gpus=gpus, mem_gib=mem, load=[round(x, 2) for x in la],
                cpu_total=cpu.get("cpu"), cpu_cores=cores, stage=ST.get("label"))


def machine_monitor():
    with open(P["machine"], "a") as f:
        while not MSTOP.is_set():
            try:
                f.write(json.dumps(machine_snapshot()) + "\n")
                f.flush()
            except Exception as e:  # noqa: BLE001
                f.write(json.dumps(dict(t=time.time(), error=str(e))) + "\n")
            MSTOP.wait(5.0)


# ------------------------------------------------------------------------------------------------ exclusivity monitor
# Copy of study_e10b_mixed.monitor with ONE narrow exemption (implementation fix, 2026-11-17 smoke VOID at 07:56:23):
# the shared snapshot lists processes BEFORE it builds our process tree, so a short-lived child of our own server that
# exits in between appears "outside the job". The only process exempted is py-cpuinfo's probe from OUR vLLM venv
# ('<venv>/site-packages/cpuinfo/cpuinfo.py --json', run by vLLM / torch at start-up) and only if it is no longer
# running when re-checked; every other entry, and any probe still running outside our tree, still VOIDs. A foreign
# process on GPU 2 always VOIDs.
PROBE = "site-packages/cpuinfo/cpuinfo.py --json"


def pid_alive(pid):
    return Path(f"/proc/{pid}").exists()


def exclusivity_monitor():
    while not E.STOP_MON.wait(30):
        rec = E.snapshot("30s")
        bad = []
        for p in rec["ours_outside_job"]:
            if PROBE in p["args"] and sys.prefix in p["args"] and (not pid_alive(p["pid"]) or
                                                                  p["pid"] in E.tree(os.getpid())):
                X.log(f"exclusivity: transient cpuinfo probe pid {p['pid']} of our own stack exempt (not VOID)")
                m = X.meta_load()
                m.setdefault("monitor_exempt_events", []).append(dict(at=F.now(), proc=p))
                X.meta_save(m)
            else:
                bad.append(p)
        if bad:
            X.log(f"!!! process of ours outside the job: {bad[:3]} - VOID")
            E.VOID.set()
        if rec["foreign_on_gpu"]:
            X.log(f"!!! foreign process on GPU 2: {rec['foreign_on_gpu']} - STOP")
            E.VOID.set()


# ------------------------------------------------------------------------------------------------ server
def ref_flags():
    m = json.loads(ENG1_META.read_text())
    return next(s["flags"] for s in m["servers"] if s["label"] == ENG1_REF_SERVER)


def start_server(label):
    """M.start_server (KVGPU, E0, plugin + iteration details) after a host-memory check; then the flag list must be
    identical to ENG1's C_P40_E0 server."""
    ms = machine_snapshot()
    avail = ms["mem_gib"].get("MemAvailable", 0)
    if avail < HOST_MARGIN_GIB:
        raise SystemExit(f"{label}: host MemAvailable {avail} GiB < {HOST_MARGIN_GIB} GiB: STOP")
    srv = M.start_server(label, "KVGPU", "E0", True, False)
    m = X.meta_load()
    flags = m["servers"][-1]["flags"]
    ref = ref_flags()
    diff = [(a, b) for a, b in zip(ref, flags) if a != b] + ([("len", len(ref), len(flags))] if len(ref) != len(flags)
                                                            else [])
    m["servers"][-1].update(flags_diff_vs_eng1_e0=diff, eng1_ref_server=ENG1_REF_SERVER, machine_at_start=ms)
    X.meta_save(m)
    if diff:
        M.stop_server(srv)
        raise SystemExit(f"{label}: flag diff vs ENG1 {ENG1_REF_SERVER} not empty: {diff}: STOP AND ASK")
    X.log(f"[{label}] flags identical to ENG1 {ENG1_REF_SERVER}; MemAvailable {avail} GiB; load {ms['load']}")
    ST["label"] = label
    return srv


# ------------------------------------------------------------------------------------------------ traces (copied)
def arrivals(load, trial):
    """Copy of M.arrivals with SEED_OFF added to both seeds."""
    if load in ("P25", "P40"):
        frac = 0.40 if load == "P40" else 0.25
        rate = frac * M.PEAK1
        rng = np.random.default_rng(M.SEED_IDX[frac] + 100 * trial + SEED_OFF)
        t = np.cumsum(rng.exponential(1.0 / rate, size=int(rate * M.TRACE_S * 3) + 10))
        return [(float(x), None) for x in t[t < M.TRACE_S]]
    S = int(load[1])
    rng = np.random.default_rng(5000 + 100 * S + 10 * trial + SEED_OFF)
    sigma = M.JIT_P90 / 1.6448536269514722
    phases = rng.uniform(0.0, M.CADENCE, size=S)
    out = []
    for s in range(S):
        k = 0
        while phases[s] + k * M.CADENCE < M.TRACE_S:
            out.append((float(phases[s] + k * M.CADENCE + abs(rng.normal(0.0, sigma))), s))
            k += 1
    return sorted(out)


def trial_plan(load, action, trial):
    arr = arrivals(load, trial)
    li, ai = LOAD_I[load], ACT_I[action]
    tinj = M.TINJ0 + float(np.random.default_rng(70000 + 1000 * li + 100 * ai + trial + SEED_OFF).uniform())
    pool = M.ep_pool()
    clips = np.random.default_rng(80000 + 1000 * li + 100 * ai + trial + SEED_OFF).choice(len(pool), size=len(arr),
                                                                                            replace=False)
    return dict(arr=arr, tinj=round(tinj, 4), clips=[pool[int(i)] for i in clips])


async def run_once(c, load, action, trial, mode, pair, holdout):
    """Copy of M.run_once for mono11k / piece2048 / piece1024 only (no warm traffic): setup (identical in every mode),
    1 s idle, the 10-s trace, drain."""
    pl = trial_plan(load, action, trial)
    ns = M.new_ns("D")
    base = dict(load=load, action=action, trial=trial, mode=mode, pair=pair, holdout=holdout, run_ns=ns,
                t_inj_rel=pl["tinj"], server=ST["label"])
    rows = []
    p, q = M.SESS["p11"][trial % 20], M.SESS["p11"][(trial + 1) % 20]
    t_setup = time.time()
    if action in ("piece1024", "piece2048"):
        h = M.Hist(p["frames"], f"{ns}h")
        await M.build(c, h, "partC", **base, role="setup_prefix")
        nfr = M.LONG_FR[action]
        inj = lambda: (h.body(q["frames"][:nfr], rid=f"{ns}-inj", extra_tag=f"{ns}i"), h.prompt_tokens)
    else:
        h = M.Hist(p["frames"], f"{ns}h")
        inj = lambda: (h.body(question=p["question"], max_tokens=R7.F.ESC_MAX_TOKENS, rid=f"{ns}-inj"), None)
    await asyncio.sleep(M.RUN_GAP)
    bodies = [(M.ep_body(r, ns, f"{ns}-bg{i}"), f"{ns}-bg{i}", r) for i, r in enumerate(pl["clips"])]
    injb = []
    if mode == "with":
        b, prev = inj()
        injb = [(b, f"{ns}-inj", prev)]
    m0 = await M.metrics(c)
    t0 = time.time() + 0.3
    tasks = [M.post_at(c, t0 + a, b, rid, "episodic", idx=i, stream=s, arrival_rel=round(a, 4), clip=r["request_id"])
             for i, ((a, s), (b, rid, r)) in enumerate(zip(pl["arr"], bodies))]
    tasks += [M.post_at(c, t0 + pl["tinj"], b, rid, "inject", idx=i, prev_prompt=prev) for i, (b, rid, prev) in
              enumerate(injb)]
    res = await asyncio.gather(*tasks)
    m1 = await M.metrics(c)
    for r in res:
        r.update(base, t0_trace=round(t0, 6))
        if r["kind"] == "inject" and r["prev_prompt"] is not None:
            r["prefix_gap"] = M.gap_of(r, r["prev_prompt"])
        rows.append(r)
    rows.append(dict(kind="run_summary", **base, t0_trace=round(t0, 6), t_setup=round(t_setup, 6),
                     t_end=round(time.time(), 6), metrics_delta=M.mdelta(m0, m1), n_bg=len(pl["arr"]),
                     n_inj=len(injb)))
    write("partC", rows)
    return rows


def imposed(a, b):
    """Total imposed delay: sum over background requests (matched by index) of TTFT(with) - TTFT(without)."""
    ta = {r["idx"]: r["ttft_s"] for r in a if r.get("kind") == "episodic" and r.get("ttft_s") is not None}
    tb = {r["idx"]: r["ttft_s"] for r in b if r.get("kind") == "episodic" and r.get("ttft_s") is not None}
    return round(sum(ta[i] - tb[i] for i in ta if i in tb), 4)


async def load_block(c, load, split, smoke):
    rng = random.Random(40000 + LOAD_I[load])
    trials = [(a, t) for a in ACTIONS for t in range(NTR)]
    rng.shuffle(trials)
    if smoke:
        trials = [next(x for x in trials if x[0] == a and x[1] not in split["holdout"][f"{load}|{a}"])
                  for a in ACTIONS]
    for a, t in trials:
        key = f"{load}|{a}"
        hold = t in split["holdout"][key]
        order = ["with", "without"] if split["order"][key][t] == "with_first" else ["without", "with"]
        pair = M.new_ns("pair")
        runs = {}
        for mode in order:
            runs[mode] = await run_once(c, load, a, t, mode, pair, hold)
        bad, n, _ = M.pair_check(runs["with"], runs["without"])
        ST["mismatch"] += bad
        ST["compared"] += n
        inj = next((r for r in runs["with"] if r["kind"] == "inject"), {})
        rep = None
        if t in split["noise_repeat"][key] or smoke:
            rep = await run_once(c, load, a, t, "repeat", pair, hold)
        tot = imposed(runs["with"], runs["without"])
        if not hold:                                  # HOLDOUT totals are not looked at, even inline
            ST["totals"].setdefault(key, []).append(tot)
        X.log(f"D {load} {a} t{t}{' H' if hold else ''}: mismatches {bad}/{n}; inject ttft {inj.get('ttft_s')} "
              f"cached {inj.get('cached_tokens')}{'' if hold else f'; imposed {tot:.2f} s'}"
              f"{' + repeat' if rep else ''}")
        write("partC", [dict(kind="pair_check", load=load, action=a, trial=t, pair=pair, holdout=hold,
                             mismatches=bad, n=n)])
        if bad:
            raise SystemExit(f"pair {key} t{t}: {bad} cached-token mismatches (0 required): STOP AND ASK")
        if inj.get("error") or (a == "mono11k" and (inj.get("cached_tokens") or 0) > 16):
            raise SystemExit(f"pair {key} t{t}: action error {inj.get('error')} / not cold: STOP")
        M.check_void()
    if load == XCHECK[0] and not smoke:
        v = ST["totals"].get(f"{XCHECK[0]}|{XCHECK[1]}", [])
        med = float(np.median(v)) if v else None
        ok = med is not None and XCHECK[2] <= med <= XCHECK[3]
        m = X.meta_load()
        m["gate_xcheck"] = dict(cell=f"{XCHECK[0]}|{XCHECK[1]}", n_fit=len(v), median_total_imposed_s=med,
                                band=XCHECK[2:], passed=ok, at=F.now())
        X.meta_save(m)
        X.log(f"GATE ENG1 Part C cross-check {XCHECK[0]} {XCHECK[1]}: median {med} s over {len(v)} FIT pairs, band "
              f"{XCHECK[2]} to {XCHECK[3]}: {'PASS' if ok else 'FAIL'}")
        if not ok:
            raise SystemExit("ENG1 Part C cross-check FAILED: STOP AND ASK")


# ------------------------------------------------------------------------------------------------ unloaded control
async def control(c, smoke):
    """ENG1 Part B (E0) reduced: solo episodic reference, solo long D_L, then each long request with one episodic
    injected at offset x D_L after the long request's submission. rho (ENG1 B) = (TTFT - solo_ep) / (D_L (1 - off))."""
    cur = M.Cursor(1)
    cur.i = 9000                                  # clips beyond the ENG1 Part B / C ranges
    rng = random.Random(909)
    nsolo = 2 if smoke else CTRL_SOLO
    reps = 1 if smoke else CTRL_REPS
    rows = []
    for i in range(nsolo):
        ns = M.new_ns("Ks")
        r0 = cur.take(1)[0]
        r = await M.post(c, M.ep_body(r0, ns, f"{ns}-0"), f"{ns}-0", "episodic", clip=r0["request_id"])
        rows.append(dict(r, sub="solo_ep", rep=i, server=ST["label"]))
        await asyncio.sleep(M.GAP)
    write("partB", rows)
    solo_ep = float(np.median([r["ttft_s"] for r in rows if r["ttft_s"]]))
    k_sess = iter(range(10 ** 6))

    async def make_long(L):
        k = next(k_sess)
        p, q = M.SESS["p11"][k % 20], M.SESS["p11"][(k + 1) % 20]
        if L == "mono11k":
            h = M.Hist(p["frames"], M.new_ns("Km"))
            rid = M.new_ns("L")
            return h, (lambda: (h.body(question=p["question"], max_tokens=R7.F.ESC_MAX_TOKENS, rid=rid), rid))
        h = M.Hist(p["frames"], M.new_ns("Kp"))
        await M.build(c, h, "partB", role="prefix", long=L, server=ST["label"])

        def mk():
            t = M.new_ns("p")
            return h.body(q["frames"][:M.LONG_FR[L]], rid=f"{t}-piece", extra_tag=t), f"{t}-piece"
        return h, mk

    dur = {}
    for L in CTRL_LONG:
        recs = []
        for i in range(nsolo):
            h, mk = await make_long(L)
            body, rid = mk()
            r = await M.post(c, body, rid, L)
            recs.append(dict(r, sub="solo_long", long=L, rep=i, server=ST["label"],
                             prefix_gap=M.gap_of(r, getattr(h, "prompt_tokens", None))))
            await asyncio.sleep(M.GAP)
        write("partB", recs)
        dur[L] = float(np.median([r["ttft_s"] for r in recs if r["ttft_s"]]))
    X.log(f"control: solo episodic {solo_ep:.3f} s, D_L {dur}")
    rho = {}
    for rep in range(reps):
        ls = list(CTRL_LONG)
        rng.shuffle(ls)
        for L in ls:
            offs = list(CTRL_OFFS)
            rng.shuffle(offs)
            h = mk = None
            if L != "mono11k":
                h, mk = await make_long(L)
            for off in offs:
                if L == "mono11k":
                    h, mk = await make_long(L)
                body, rid = mk()
                ns = M.new_ns("Ke")
                r0 = cur.take(1)[0]
                t0 = time.time() + 0.05
                recs = await asyncio.gather(M.post_at(c, t0, body, rid, L),
                                            M.post_at(c, t0 + off * dur[L], M.ep_body(r0, ns, f"{ns}-0"), f"{ns}-0",
                                                      "episodic", clip=r0["request_id"]))
                ep = recs[1]
                if ep["ttft_s"] is not None:
                    rho.setdefault((L, off), []).append((ep["ttft_s"] - solo_ep) / (dur[L] * (1 - off)))
                write("partB", [dict(r, sub="inject", long=L, offset=off, D_L=dur[L], solo_ep=solo_ep, rep=rep,
                                     server=ST["label"], prefix_gap=M.gap_of(recs[0], getattr(h, "prompt_tokens",
                                                                                                 None))
                                     if r is recs[0] else None) for r in recs])
                await asyncio.sleep(M.GAP)
        M.check_void()
    res, ok = {}, True
    for (L, off), v in sorted(rho.items()):
        lo, hi = ENG1_B[(L, off)]
        med = float(np.median(v))
        inb = lo - WIDEN <= med <= hi + WIDEN
        gate = (L, off) in CTRL_GATE
        ok &= inb or not gate
        res[f"{L}_off{int(off * 100)}"] = dict(n=len(v), rho_median=round(med, 4), band=[round(lo - WIDEN, 4),
                                               round(hi + WIDEN, 4)], within=inb, gated=gate)
    m = X.meta_load()
    m["gate_control" + ("_smoke" if smoke else "")] = dict(solo_ep=solo_ep, D_L=dur, cells=res, passed=ok, at=F.now())
    X.meta_save(m)
    X.log(f"GATE unloaded control: {res}: {'PASS' if ok else 'FAIL'}")
    if not ok and not smoke:
        raise SystemExit("unloaded control FAILED the ENG1 Part B gate: STOP AND ASK (check the host CPU monitor first)")


# ------------------------------------------------------------------------------------------------ main
def stage(label, fns):
    srv = start_server(label)
    if ST["t0"] is None and not ST["smoke"]:
        ST["t0"] = time.time()
        m = X.meta_load()
        m["run_start"] = F.now()
        X.meta_save(m)
    try:
        for fn, a in fns:
            asyncio.run(M.with_client(fn, *a))
    finally:
        M.stop_server(srv)
        ST["label"] = None
        m = X.meta_load()
        m.setdefault("stages_done", []).append(dict(label=label, at=F.now(),
                                                    elapsed_h=round((time.time() - (ST["t0"] or time.time())) / 3600, 2)))
        X.meta_save(m)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--split-only", action="store_true")
    ap.add_argument("--only", default=None, help="comma list: K (control), P40, S4, P25, S2")
    a = ap.parse_args()
    ST["smoke"] = M.ST["smoke"] = a.smoke
    set_paths(a.smoke)
    split = ensure_split()
    if a.split_only:
        return
    start = E.snapshot("start")
    if start["ours_outside_job"] or start["foreign_on_gpu"]:
        raise SystemExit(f"not exclusive at start: {start['ours_outside_job']} {start['foreign_on_gpu']}: STOP")
    import torch
    import vllm
    if vllm.__version__ != "0.31.0":
        raise SystemExit(f"vLLM {vllm.__version__} != 0.31.0: STOP")
    m = X.meta_load()
    m["stack"] = dict(venv=sys.prefix, vllm=vllm.__version__, torch=torch.__version__, gpu="h100nvl GPU 2",
                      gpu_uuid=F.GPU_UUID, kv_flags=E.KV["KVGPU"], log_flags=M.D.LOGFLAGS, plugin=str(M.PLUGIN_DIR),
                      eng1_ref_server=ENG1_REF_SERVER,
                      design=dict(LOADS=LOADS, ACTIONS=ACTIONS, NTR=NTR, NHOLD=NHOLD, NREP=NREP, SEED_OFF=SEED_OFF,
                                  CTRL_LONG=CTRL_LONG, CTRL_OFFS=CTRL_OFFS, CTRL_REPS=CTRL_REPS, CTRL_SOLO=CTRL_SOLO,
                                  TRACE_S=M.TRACE_S, TINJ0=M.TINJ0, RUN_GAP=M.RUN_GAP, ENG1_B=str(ENG1_B),
                                  WIDEN=WIDEN, XCHECK=XCHECK, CPU_FLAG=CPU_FLAG, HOST_MARGIN_GIB=HOST_MARGIN_GIB),
                      monitor_user_exempt=M.USER_EXEMPT,
                      caching="prefix caching ON (ENG1 E0); every background image and every mono11k history carries "
                              "a per-run uuid namespace, so background requests and mono11k are cold; pieces run on "
                              "their own prefix built in the setup of the same run (GPU-cached)")
    m["smoke"] = a.smoke
    X.meta_save(m)
    th = threading.Thread(target=exclusivity_monitor, daemon=True)
    th.start()
    mth = threading.Thread(target=machine_monitor, daemon=True)
    mth.start()
    try:
        M.load_sessions(warm=False)
        if a.smoke:
            stage("SMK_E0", [(control, (True,)), (load_block, ("P40", split, True))])
        else:
            only = (a.only or "K," + ",".join(LOADS)).split(",")
            plan = ([("K_E0", [(control, (False,))])] if "K" in only else []) + \
                   [(f"L_{ld}_E0", [(load_block, (ld, split, False))]) for ld in LOADS if ld in only]
            m = X.meta_load()
            m["plan"] = [p[0] for p in plan]
            X.meta_save(m)
            for label, fns in plan:
                if ST["t0"] and (time.time() - ST["t0"]) / 3600 > 8.0:
                    X.log(f"8 h elapsed before {label}: stopping (unfinished reported, no cell shrunk)")
                    m = X.meta_load()
                    m["unfinished"] = [p[0] for p in plan[plan.index((label, fns)):]]
                    X.meta_save(m)
                    break
                stage(label, fns)
    finally:
        E.STOP_MON.set()
        MSTOP.set()
        E.snapshot("end")
        m = X.meta_load()
        m["void"] = E.VOID.is_set()
        m["pair_cached_mismatch"] = dict(mismatch=ST["mismatch"], compared=ST["compared"])
        m["ended"] = F.now()
        X.meta_save(m)
    from _provenance import stamp
    m = X.meta_load()
    m.setdefault("_provenance", []).append(stamp(script="study_eng1d_loadedblock.py", model="qwen3vl-32b-instruct",
                                                 device="h100nvl_gpu2", args=a))
    X.meta_save(m)
    X.log(f"ENG1d {'smoke' if a.smoke else 'full'} finished")


if __name__ == "__main__":
    main()
