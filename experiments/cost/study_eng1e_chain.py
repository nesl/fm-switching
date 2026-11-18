#!/usr/bin/env python3
"""StudyENG1e-chain: how CHAINED piece rebuilds of a cold history interact with other requests under load, at the level
of which requests the engine serves in each step. EXCLUSIVE (vLLM venv; h100nvl GPU 2). Pre-registered in
research/EXPERIMENTS.md (StudyENG1e-chain; design answers by the user 2026-11-17, points 1 to 8).

Stack: StudyENG1c KV-HOST exactly (32B-I @0cfaf481, vLLM 0.31.0, StudySLICE1 E0 flags, native offloading connector,
--kv-offloading-size 38, --enable-logging-iteration-details, the fixed ENG1 stat-logger plugin, prefix caching ON).
The flag list is diffed against StudyENG1c's DE_c38 server at every start and must be empty. The only addition is the
observe-only per-step membership add-on experiments/cost/eng1e_steplog (a vllm.general_plugins entry point on
PYTHONPATH; no flag), present on every server except the overhead gate's OFF servers.
Injection modes (user decision 8, both, B first, never pooled):
  B  ENG1c-exact: per-run setup identical in every arm: (i) the history once with image bytes under the SAME image
     uuids but a DIFFERENT header text (images enter the 128 GiB processor cache; the history's own KV prefix stays
     cold because its first block differs), (ii) an encoder-cache flush: a fresh-image request of FLUSH_FR frames
     (> the 16,384-token encoder cache budget). Mono and chain pieces then carry uuid references only (ENG1c d_job).
  A  bytes: fresh namespace, no setup; every piece sends its new frames as bytes, mono sends all 120 (ENG1d mono11k).
Actions: mono (one request, question, ESC_MAX_TOKENS), chain2048 (23 frames per piece: 6 pieces on the 120-frame 11k
sessions), chain1024 (11 frames per piece: 11 pieces); pieces prefix-chained (piece j = frames[:cut_j]), max_tokens 1
except the last (question, ESC_MAX_TOKENS), each released when the previous one completes (ENG1c d_job).
Reuses by import (unchanged): study_eng1_steptime.py (requests, sessions, clip pool, metrics, pair_check,
stop_server, exclusivity snapshot, user exemption) and study_eng1d_loadedblock.py (machine monitor with per-core CPU,
exclusivity monitor with the cpuinfo-probe exemption). COPIED and changed: StudyENG1c start_server (cap fixed at 38,
add-on switch, diff vs DE_c38), StudyENG1d arrivals / trial_plan (SEED_OFF 1,000,000).
Rows -> results/cost/study_eng1e/eng1e[_smoke]_{requests,gate,fill,frontend}_h100nvl.jsonl, ENG1 plugin rows
eng1e[_smoke]_statlog/<server>.jsonl.gz, add-on rows eng1e[_smoke]_steps_<server>.jsonl.gz, machine / exclusivity
monitors, meta eng1e[_smoke]_run_meta_h100nvl.json, gate eng1e[_smoke]_gate.json, split eng1e_holdout_split.json.
"""
import argparse
import ast
import asyncio
import gzip
import json
import os
import random
import re
import shutil
import sys
import threading
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import study_eng1_steptime as M  # noqa: E402  (StudyENG1 harness, unchanged)
import study_eng1d_loadedblock as DD  # noqa: E402  (StudyENG1d monitors, unchanged)

E, X, F, R6, R7 = M.E, M.X, M.F, M.R6, M.R7
OUT = M.REPO / "results/cost/study_eng1e"
SPLIT = OUT / "eng1e_holdout_split.json"
STEPLOG_DIR = HERE / "eng1e_steplog"
ENG1C_META = M.REPO / "results/cost/study_eng1c/eng1c_run_meta_h100nvl.json"
ENG1C_REF = "DE_c38"

# ------------------------------------------------------------------------------------------------ design constants
MODES = ("B", "A")                              # run order (user decision 8)
LOADS = ("P40", "S4", "P25", "S2")              # run order within each mode
ACTIONS = ("mono", "chain2048", "chain1024")
NFR = {"chain2048": 23, "chain1024": 11}
LOAD_I = {"P25": 0, "P40": 1, "S2": 2, "S4": 3}
ACT_I = {a: i for i, a in enumerate(ACTIONS)}
NTR, NHOLD, NREP = 20, 5, 3
SEED_OFF = 1000000                              # sweep traces (ENG1 Part C seeds + this)
GATE_OFF, WARM_OFF = 1100000, 1200000           # overhead-gate and warm-up traces (never used in the sweep)
CAP, TOK_PER_GIB, GPU_POOL = 38, 4096, 62944
FILL_X = 1.5                                    # host fill at every server start: 1.5 x cap tokens
FLUSH_FR, FLUSH_MIN_TOK = 200, 17500            # encoder-cache flush (budget 16,384 encoder tokens)
HOST_MARGIN_GIB = 192
GATE_N, GATE_WARM, GATE_TOL = 10, 5, 0.01
GUARD_H = 6.0                                   # A stages are not started after 6 h (B always completes)
# mono cross-check bands: median FIT TTFT sum (s), p10 x 0.75 to p90 x 1.25 (user decisions 1 and 8)
XB = {"P25": (4.87, 18.17), "S2": (11.36, 13.29)}                       # ENG1c Part D 38 GiB cold mono FIT
XA = {"P25": (6.2503, 30.095), "P40": (32.1206, 71.5958), "S2": (19.0082, 22.2732), "S4": (63.8359, 76.449)}  # ENG1d
WID = 0.25

ST = dict(smoke=False, t0=None, mismatch=0, compared=0, label=None, totals={}, steplog=None, addon=False)
P = M.P


def band(b):
    return (round(b[0] * (1 - WID), 4), round(b[1] * (1 + WID), 4))


def set_paths(smoke):
    pre = "eng1e_smoke" if smoke else "eng1e"
    OUT.mkdir(parents=True, exist_ok=True)
    for k in ("requests", "gate", "fill", "frontend"):
        P[k] = OUT / f"{pre}_{k}_h100nvl.jsonl"
    P["steps"] = OUT / f"{pre}_statlog"
    P["steps"].mkdir(exist_ok=True)
    P["machine"] = OUT / f"{pre}_machine_h100nvl.jsonl"
    P["pre"] = pre
    E.MON = OUT / f"{pre}_monitor_h100nvl.jsonl"
    X.META_PATH = OUT / f"{pre}_run_meta_h100nvl.json"
    X.CURRENT = M.REPO / "logs/eng1e_current.json"
    M.G.X.META_PATH = X.META_PATH


GATE_LABEL = "add-on failed unloaded overhead gate; passed at P40"   # user ruling 2026-11-17 (option 1)


def write(key, rows):
    if key in ("requests", "fill") and not ST["smoke"]:
        rows = [dict(r, addon_gate=GATE_LABEL) for r in rows]
    M.write(key, rows)


# ------------------------------------------------------------------------------------------------ HOLDOUT split
def make_split():
    cells = [(l, a) for l in ("P25", "P40", "S2", "S4") for a in ACTIONS]
    rng = random.Random(20261122)
    hold = {f"{l}|{a}": sorted(rng.sample(range(NTR), NHOLD)) for l, a in cells}
    rng2 = random.Random(20261123)
    order = {f"{l}|{a}": ["with_first" if rng2.random() < 0.5 else "without_first" for _ in range(NTR)]
             for l, a in cells}
    rep = {k: [t for t in range(NTR) if t not in v][:NREP] for k, v in hold.items()}
    return dict(study="StudyENG1e-chain", reserved_for="later T0 extension; recorded, NOT analysed",
                rule="random.Random(20261122).sample(range(20), 5) per (load, action), stratified by cell, in the order "
                     "loads (P25, P40, S2, S4) x actions (mono, chain2048, chain1024)",
                modes="the same split, order and repeats apply to BOTH injection modes (B and A), so every cell has a "
                      "25 % HOLDOUT in each mode and a trace is never FIT in one mode and HOLDOUT in the other; the "
                      "background trace of (load, action, trial) is identical in the two modes",
                holdout=hold, holdout_by_mode={m: {f"{m}|{k}": v for k, v in hold.items()} for m in MODES},
                order_rule="random.Random(20261123): one draw per (cell, trial) in cell order; < 0.5 -> with first",
                order=order, noise_repeat_rule="the first 3 FIT trials of each cell get an independent repeat of the "
                                               "without run (each mode)", noise_repeat=rep,
                seeds=f"ENG1 Part C trace / injection-time / clip seeds + {SEED_OFF}; overhead gate + {GATE_OFF}; "
                      f"warm-up + {WARM_OFF}")


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


# ------------------------------------------------------------------------------------------------ server (copied)
MMAP_RE = re.compile(r"Created mmap file \S+ \(([\d.]+) GB\)")


def ref_flags():
    m = json.loads(ENG1C_META.read_text())
    return next(s["flags"] for s in m["servers"] if s["label"] == ENG1C_REF)


def start_server(label, addon=True):
    """Copy of StudyENG1c start_server at cap 38 with the add-on switch. Checks: GPU 2 idle; MemAvailable > cap +
    margin; flag list identical to ENG1c DE_c38; ENG1 plugin loaded; add-on installed iff addon; GPU pool 62,944
    tokens; cap enforced (mmap size)."""
    F.require_idle()
    ms = DD.machine_snapshot()
    avail = ms["mem_gib"].get("MemAvailable", 0)
    if avail < CAP + HOST_MARGIN_GIB:
        raise SystemExit(f"{label}: host MemAvailable {avail} GiB < {CAP} + {HOST_MARGIN_GIB} GiB: STOP")
    flags = M.E.COMMON + ["--kv-offloading-backend", "native", "--kv-offloading-size", f"{CAP:g}"] + M.D.LOGFLAGS + \
        ["--enable-logging-iteration-details"]
    ref = ref_flags()
    diff = [(a, b) for a, b in zip(ref, flags) if a != b] + ([("len", len(ref), len(flags))] if len(ref) != len(flags)
                                                            else [])
    steps = P["steps"] / f"{label}.jsonl"
    slog = OUT / f"{P['pre']}_steps_{label}.jsonl"
    os.environ["PYTHONPATH"] = str(M.PLUGIN_DIR) + ((os.pathsep + str(STEPLOG_DIR)) if addon else "")
    os.environ["ENG1_STATLOG_PATH"] = str(steps)
    if addon:
        os.environ["ENG1E_STEPLOG_PATH"] = str(slog)
    else:
        os.environ.pop("ENG1E_STEPLOG_PATH", None)
    srv = X.Server("32BI", flags)
    info = srv.start()
    os.environ.pop("PYTHONPATH", None)
    os.environ.pop("ENG1E_STEPLOG_PATH", None)
    txt = Path(srv.logpath).read_text(errors="replace")
    nd = re.findall(r"non-default args: (.*)", txt)
    nd = nd[-1] if nd else ""
    try:
        d = ast.literal_eval(nd)
    except Exception:  # noqa: BLE001
        d = {}
    want = set(M.BASE_KEYS) | {"kv_offloading_size", "enable_logging_iteration_details"}
    got = set(d) - {"kv_offloading_backend"}
    ok = got == want and d.get("enable_logging_iteration_details") is True and \
        abs(float(d.get("kv_offloading_size", -1)) - CAP) < 1e-9
    plugin_ok = "eng1_statlog" in txt
    addon_seen = "eng1e_steplog installed" in txt
    mm = MMAP_RE.findall(txt)
    mmap_gb = float(mm[-1]) if mm else None
    cap_ok = mmap_gb is not None and abs(mmap_gb - CAP * 2 ** 30 / 1e9) <= 0.005 * CAP * 2 ** 30 / 1e9
    kvt = info.get("kv_cache_tokens")
    enc = re.findall(r"Encoder cache will be initialized with a budget of (\d+) tokens", txt)
    info.update(kv_config=f"KVHOST_{CAP}", cap_gib=CAP, flags_diff_vs_eng1c=diff, eng1c_ref_server=ENG1C_REF,
                non_default_args=nd, flags_verified=bool(ok), plugin_loaded=plugin_ok, addon=addon,
                addon_installed_in_log=addon_seen, steplog=str(slog) + ".gz" if addon else None, mmap_gb=mmap_gb,
                cap_enforced=cap_ok, encoder_cache_budget=int(enc[-1]) if enc else None,
                host_mem=E.R5.host_mem(srv.proc.pid), machine_at_start=ms)
    m = X.meta_load()
    m.setdefault("servers", []).append(dict(label=label, started=F.now(), flags=flags, **info))
    X.meta_save(m)
    bad = None
    if not ok or not plugin_ok or diff:
        bad = f"non-default args {sorted(got)} vs {sorted(want)}; flag diff vs {ENG1C_REF} {diff}; plugin {plugin_ok}"
    elif addon_seen != addon:
        bad = f"add-on installed {addon_seen} but requested {addon}"
    elif not cap_ok:
        bad = f"cap NOT enforced: mmap {mmap_gb} GB"
    elif kvt != GPU_POOL:
        bad = f"GPU pool {kvt} tokens != {GPU_POOL}"
    elif enc and int(enc[-1]) >= FLUSH_MIN_TOK:
        bad = f"encoder cache budget {enc[-1]} >= flush size {FLUSH_MIN_TOK}"
    if bad:
        srv.stop()
        raise SystemExit(f"{label}: {bad}: STOP AND ASK")
    E.snapshot(f"server_up_{label}")
    X.log(f"[{label}] up: KV-HOST {CAP} GiB, flags identical to ENG1c {ENG1C_REF}, add-on {addon}, mmap {mmap_gb} GB, "
          f"encoder budget {info['encoder_cache_budget']}, MemAvailable {avail} GiB")
    srv.eng1_label, srv.eng1_steps = label, steps
    srv.eng1e_slog = slog if addon else None
    ST["label"] = DD.ST["label"] = label
    ST["steplog"] = StepTail(slog) if addon else None
    ST["addon"] = addon
    return srv


def stop_server(srv):
    time.sleep(2.0)                             # idle 2 s so the add-on flushes its last rows (re-gate fix)
    M.stop_server(srv)                          # frontend rows + ENG1 plugin rows gzipped
    sl = getattr(srv, "eng1e_slog", None)
    if sl and sl.exists():
        with open(sl, "rb") as fi, gzip.open(str(sl) + ".gz", "wb") as fo:
            shutil.copyfileobj(fi, fo)
        sl.unlink()
    ST["steplog"] = None


class StepTail:
    """Harness-side reader of the add-on's plain jsonl while the server is up (complete lines only): encoder inputs per
    client request id (injection requests only)."""

    def __init__(self, path):
        self.path, self.off, self.enc, self.steps = Path(path), 0, {}, 0

    def poll(self):
        if not self.path.exists():
            return
        with open(self.path, "rb") as f:
            f.seek(self.off)
            data = f.read()
        k = data.rfind(b"\n")
        if k < 0:
            return
        self.off += k + 1
        for line in data[:k + 1].splitlines():
            r = json.loads(line)
            if "r" not in r:
                continue
            self.steps += 1
            for rid, n, ph, c0, ne in r["r"]:
                if "-inj" in rid and ne:
                    cid = rid[len("chatcmpl-"):-9]
                    self.enc[cid] = self.enc.get(cid, 0) + ne


# ------------------------------------------------------------------------------------------------ traces (copied)
def arrivals(load, trial, off):
    """Copy of M.arrivals (ENG1 generator, rates, sizes, image counts unchanged) with `off` added to both seeds."""
    if load in ("P25", "P40"):
        frac = 0.40 if load == "P40" else 0.25
        rate = frac * M.PEAK1
        rng = np.random.default_rng(M.SEED_IDX[frac] + 100 * trial + off)
        t = np.cumsum(rng.exponential(1.0 / rate, size=int(rate * M.TRACE_S * 3) + 10))
        return [(float(x), None) for x in t[t < M.TRACE_S]]
    S = int(load[1])
    rng = np.random.default_rng(5000 + 100 * S + 10 * trial + off)
    sigma = M.JIT_P90 / 1.6448536269514722
    phases = rng.uniform(0.0, M.CADENCE, size=S)
    out = []
    for s in range(S):
        k = 0
        while phases[s] + k * M.CADENCE < M.TRACE_S:
            out.append((float(phases[s] + k * M.CADENCE + abs(rng.normal(0.0, sigma))), s))
            k += 1
    return sorted(out)


def trial_plan(load, action, trial, off=SEED_OFF):
    arr = arrivals(load, trial, off)
    li, ai = LOAD_I[load], ACT_I[action]
    tinj = M.TINJ0 + float(np.random.default_rng(70000 + 1000 * li + 100 * ai + trial + off).uniform())
    pool = M.ep_pool()
    clips = np.random.default_rng(80000 + 1000 * li + 100 * ai + trial + off).choice(len(pool), size=len(arr),
                                                                                       replace=False)
    return dict(arr=arr, tinj=round(tinj, 4), clips=[pool[int(i)] for i in clips])


# ------------------------------------------------------------------------------------------------ fill, setup, action
async def fill(c):
    """Host steady state: fresh p28 histories (cold builds, max_tokens 1) until FILL_X x cap tokens were written."""
    target = int(FILL_X * CAP * TOK_PER_GIB)
    done, k = 0, 0
    m0 = await M.metrics(c)
    while done < target:
        p = M.SESS["p28"][k % len(M.SESS["p28"])]
        h = M.Hist(p["frames"], M.new_ns("F"))
        r = await M.build(c, h, "fill", role="fill", server=ST["label"])
        done += r["prompt_tokens"] or 0
        k += 1
    m1 = await M.metrics(c)
    occ = min(done, CAP * TOK_PER_GIB)
    write("fill", [dict(kind="fill_summary", server=ST["label"], tokens_written=done, n_hist=k, cap_tokens=CAP * TOK_PER_GIB,
                        host_occupancy_tokens_derived=occ, host_occupancy_frac_derived=round(occ / (CAP * TOK_PER_GIB), 4),
                        metrics_delta=M.mdelta(m0, m1), t=round(time.time(), 6))])
    X.log(f"[{ST['label']}] host fill: {done} tokens in {k} fresh histories (cap {CAP * TOK_PER_GIB}; occupancy "
          f"derived {occ / (CAP * TOK_PER_GIB):.2f})")


async def setup_b(c, ns, p, trial, base, part):
    """Mode B per-run setup (identical in every arm): history with bytes under the same uuids and another header,
    then the encoder-cache flush. Returns the uuid-reference Hist."""
    rows = []
    hs = M.Hist(p["frames"], f"{ns}h")
    hs.hdr = R6.header(f"{ns}w", 0, 0)
    rid = f"{ns}-sh"
    r = await M.post(c, hs.body(rid=rid), rid, "setup_hist", **base)
    rows.append(r)
    q = M.SESS["p28"][(trial + 3) % len(M.SESS["p28"])]
    fl = M.Hist(q["frames"][:FLUSH_FR], f"{ns}f")
    rid = f"{ns}-sf"
    r2 = await M.post(c, fl.body(rid=rid), rid, "setup_flush", **base)
    rows.append(r2)
    write(part, rows)
    for x in rows:
        if x["error"] or (x["cached_tokens"] or 0) > 16:
            raise SystemExit(f"setup {x['rid']}: error {x['error']} / cached {x['cached_tokens']}: STOP")
    if (r2["prompt_tokens"] or 0) < FLUSH_MIN_TOK:
        raise SystemExit(f"flush {r2['prompt_tokens']} tokens < {FLUSH_MIN_TOK}: STOP")
    h = M.Hist(p["frames"], f"{ns}h")
    h.sent = set(p["frames"])
    return h, rows


async def action_job(c, h, question, action, ns, t_at, **extra):
    """mono: one request (question, ESC_MAX_TOKENS); chainN: prefix-chained pieces, the next released when the previous
    one completes (ENG1c d_job). Frames not yet sent carry bytes (mode A); sent frames are uuid references."""
    if t_at - time.time() > 0:
        await asyncio.sleep(t_at - time.time())
    t0 = time.time()
    rows = []
    fr = h.frames
    cuts = [len(fr)] if action == "mono" else list(range(NFR[action], len(fr), NFR[action])) + [len(fr)]
    sub = M.Hist([], h.ns)
    sub.hdr, sub.sent = h.hdr, h.sent
    prev = 0
    for j, e in enumerate(cuts):
        sub.frames = fr[:e]
        last = j == len(cuts) - 1
        rid = f"{ns}-inj{j}"
        bytes_frames = sum(1 for x in fr[prev:e] if x not in sub.sent)
        r = await M.post(c, sub.body(question=question if last else None,
                                     max_tokens=R7.F.ESC_MAX_TOKENS if last else 1, rid=rid), rid, "inject",
                         part_i=j, n_parts=len(cuts), new_frames=e - prev, bytes_frames=bytes_frames, cut=e, **extra)
        h.sent.update(fr[prev:e])
        rows.append(r)
        prev = e
    t1 = time.time()
    job = dict(kind="job", t_sched=round(t_at, 6), t_start=round(t0, 6), t_end=round(t1, 6),
               dispatch_late_s=round(t0 - t_at, 5), n_parts=len(cuts),
               job_ttft_s=round(rows[-1]["t_first"] - t0, 5) if rows[-1]["t_first"] else None,
               job_completion_s=round(t1 - t0, 5), first_cached=rows[0]["cached_tokens"],
               cached_sum=sum(r["cached_tokens"] or 0 for r in rows), prompt_sum=sum(r["prompt_tokens"] or 0 for r in rows),
               errors=[r["error"] for r in rows if r["error"]], **extra)
    return rows, job


# ------------------------------------------------------------------------------------------------ one run
async def run_once(c, mode, load, action, trial, arm, pair, hold, off=SEED_OFF, part="requests", bg=True, extra=None):
    pl = trial_plan(load, action, trial, off)
    ns = M.new_ns("D")
    base = dict(mode=mode, load=load, action=action, trial=trial, arm=arm, pair=pair, holdout=hold, run_ns=ns,
                t_inj_rel=pl["tinj"], server=ST["label"], seed_off=off, **(extra or {}))
    p = M.SESS["p11"][trial % 20]
    t_setup = time.time()
    setup_rows = []
    if mode == "B":
        h, setup_rows = await setup_b(c, ns, p, trial, base, part)
    else:
        h = M.Hist(p["frames"], f"{ns}h")
    t_setup_end = time.time()
    await asyncio.sleep(M.RUN_GAP)
    arr = pl["arr"] if bg else []
    bodies = [(M.ep_body(r, ns, f"{ns}-bg{i}"), f"{ns}-bg{i}", r) for i, r in enumerate(pl["clips"][:len(arr)])]
    m0 = await M.metrics(c)
    t0 = time.time() + 0.3
    tasks = [M.post_at(c, t0 + a, b, rid, "episodic", idx=i, stream=s, arrival_rel=round(a, 4), clip=r["request_id"])
             for i, ((a, s), (b, rid, r)) in enumerate(zip(arr, bodies))]
    if arm == "with":
        tasks.append(action_job(c, h, p["question"], action, ns, t0 + (pl["tinj"] if bg else 0.0)))
    res = await asyncio.gather(*tasks)
    m1 = await M.metrics(c)
    rows = []
    for r in res:
        if isinstance(r, tuple):
            jr, job = r
            rows += [dict(x, **base, t0_trace=round(t0, 6)) for x in jr]
            rows.append(dict(job, **base, t0_trace=round(t0, 6)))
        else:
            rows.append(dict(r, **base, t0_trace=round(t0, 6)))
    rows.append(dict(kind="run_summary", **base, t0_trace=round(t0, 6), t_setup=round(t_setup, 6),
                     t_setup_end=round(t_setup_end, 6), setup_s=round(t_setup_end - t_setup, 5),
                     setup_lat=[x["latency_s"] for x in setup_rows], t_end=round(time.time(), 6),
                     metrics_delta=M.mdelta(m0, m1), n_bg=len(arr)))
    write(part, rows)
    return rows


async def enc_check(rows):
    """Every piece (and mono) ran its new frames through the vision encoder (no encoder-cache hit): step-log encoder
    inputs >= new frames. Waits for the add-on's 1 s flush."""
    tail = ST["steplog"]
    if tail is None:
        return None
    inj = [r for r in rows if r.get("kind") == "inject"]
    out = []
    for _ in range(6):
        await asyncio.sleep(0.6)
        tail.poll()
        out = [(r["rid"], r["new_frames"], tail.enc.get(r["rid"], 0)) for r in inj]
        if all(e >= n for _, n, e in out):
            return dict(ok=True, pieces=out)
    return dict(ok=False, pieces=out)


def imposed(a, b, key="ttft_s"):
    ta = {r["idx"]: r[key] for r in a if r.get("kind") == "episodic" and r.get(key) is not None and not r.get("error")}
    tb = {r["idx"]: r[key] for r in b if r.get("kind") == "episodic" and r.get(key) is not None and not r.get("error")}
    return round(sum(ta[i] - tb[i] for i in ta if i in tb), 4)


# ------------------------------------------------------------------------------------------------ loaded block
async def load_block(c, mode, load, split, smoke):
    await fill(c)
    rng = random.Random(40000 + LOAD_I[load] + 100 * MODES.index(mode))
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
        for arm in order:
            runs[arm] = await run_once(c, mode, load, a, t, arm, pair, hold)
        bad, n, _ = M.pair_check(runs["with"], runs["without"])
        ST["mismatch"] += bad
        ST["compared"] += n
        rep = None
        if t in split["noise_repeat"][key] or smoke:
            rep = await run_once(c, mode, load, a, t, "repeat", pair, hold)
        inj = [r for r in runs["with"] if r["kind"] == "inject"]
        job = next((r for r in runs["with"] if r["kind"] == "job"), {})
        ec = await enc_check(runs["with"])
        tot = imposed(runs["with"], runs["without"])
        totl = imposed(runs["with"], runs["without"], "latency_s")
        if not hold:
            ST["totals"].setdefault(f"{mode}|{key}", []).append(tot)
        su = {arm: next(r for r in runs[arm] if r["kind"] == "run_summary")["setup_lat"] for arm in runs}
        write("requests", [dict(kind="pair_check", mode=mode, load=load, action=a, trial=t, pair=pair, holdout=hold,
                                mismatches=bad, n=n, enc_check=ec, setup_lat_by_arm=su)])
        X.log(f"{mode} {load} {a} t{t}{' H' if hold else ''}: mism {bad}/{n}; pieces {len(inj)} first cached "
              f"{inj[0]['cached_tokens'] if inj else None}; job compl {job.get('job_completion_s')}; enc "
              f"{'ok' if (ec or {}).get('ok') else ec}"
              f"{'' if hold else f'; imposed ttft {tot:.2f} lat {totl:.2f} s'}{' + repeat' if rep else ''}")
        if bad:
            raise SystemExit(f"{mode} {key} t{t}: {bad} cached-token mismatches (0 required): STOP AND ASK")
        if job.get("errors") or not inj or (inj[0]["cached_tokens"] or 0) > 16:
            raise SystemExit(f"{mode} {key} t{t}: action errors {job.get('errors')} / first piece not cold: STOP")
        if ec is not None and not ec["ok"]:
            raise SystemExit(f"{mode} {key} t{t}: encoder check failed {ec}: STOP AND ASK")
        M.check_void()
    if smoke:
        return
    ref = XB if mode == "B" else XA
    if load in ref:
        v = ST["totals"].get(f"{mode}|{load}|mono", [])
        med = float(np.median(v)) if v else None
        lo, hi = band(ref[load])
        ok = med is not None and lo <= med <= hi
        m = X.meta_load()
        m.setdefault("gate_mono", []).append(dict(mode=mode, load=load, n_fit=len(v), median_ttft_sum_s=med,
                                                  band=[lo, hi], ref="ENG1c Part D 38 GiB cold mono FIT" if mode == "B"
                                                  else "ENG1d mono11k FIT", passed=ok, at=F.now()))
        X.meta_save(m)
        X.log(f"GATE mono {mode} {load}: median TTFT sum {med} s ({len(v)} FIT) band {lo} to {hi}: "
              f"{'PASS' if ok else 'FAIL'}")
        if not ok:
            raise SystemExit(f"mono cross-check {mode} {load} FAILED: STOP AND REPORT (not void)")


# ------------------------------------------------------------------------------------------------ overhead gate
async def gate_server(c, cond, inst, traces, smoke):
    await fill(c)
    for w in range(1 if smoke else GATE_WARM):
        await run_once(c, "B", "P40", "chain1024", w, "with", f"warm{w}", False, off=WARM_OFF, part="gate",
                       extra=dict(gate="warmup", cond=cond, inst=inst, trace=w))
    for t in traces:
        for a in ACTIONS:
            await run_once(c, "B", "P40", a, t, "with", f"g{t}", False, off=GATE_OFF, part="gate", bg=False,
                           extra=dict(gate="unloaded", cond=cond, inst=inst, trace=t))
        await run_once(c, "B", "P40", "chain1024", t, "with", f"g{t}", False, off=GATE_OFF, part="gate",
                       extra=dict(gate="P40", cond=cond, inst=inst, trace=t))
        M.check_void()
    X.log(f"[{ST['label']}] gate {cond}{inst} traces {list(traces)} done")


def _rows(path):
    op = gzip.open if str(path).endswith(".gz") else open
    with op(path, "rt") as f:
        return [json.loads(x) for x in f if x.strip()]


def gate_eval(labels, smoke, out_name="gate"):
    """Overhead gate (no server up), corrected rule (user, 2026-11-17, fixed before the re-gate data): every server
    ran the IDENTICAL trace set. Per kind (unloaded, P40): ON / OFF ratio of the median ENG1 step elapsed_ms (steps in
    the gate runs' windows) and of the median TTFT (gate runs' requests except setup), pooled over both instances of a
    condition, 95 % paired bootstrap over traces; same-condition instance variation inst2 / inst1 on the identical
    traces (OFF and ON). Pass: (a) |step ratio - 1| <= 1 % at both kinds; (b) TTFT ratio CI includes 1.0 AND
    |TTFT ratio - 1| <= max(1 %, the larger same-condition TTFT instance deviation of that kind); (c) membership sums
    equal the plugin rows on 100 % of joined steps."""
    G = [r for r in _rows(P["gate"]) if r.get("gate") in ("unloaded", "P40") and r.get("server") in labels]
    steps = {lb: [r for r in _rows(P["steps"] / f"{lb}.jsonl.gz") if "it" in r] for lb in labels}
    out = dict(labels=labels, rule="corrected (user 2026-11-17)", kinds={})
    rng = np.random.default_rng(7)
    for kind in (() if smoke else ("unloaded", "P40")):
        per = {}                                       # (cond, inst, trace) -> dict(st, tt)
        for s in [r for r in G if r["kind"] == "run_summary" and r["gate"] == kind]:
            st = [x["it"][5] for x in steps[s["server"]] if s["t0_trace"] - 0.05 <= x["t"] <= s["t_end"]]
            rq = [r for r in G if r["run_ns"] == s["run_ns"] and r["kind"] in ("episodic", "inject") and r["ttft_s"]]
            d = per.setdefault((s["cond"], s["inst"], s["trace"]), dict(st=[], tt=[]))
            d["st"] += st
            d["tt"] += [r["ttft_s"] for r in rq]
        tr = sorted({t for (_, _, t) in per})
        tr = [t for t in tr if all((c, i, t) in per for c in ("ON", "OFF") for i in (1, 2))]

        def med(cond, insts, idx, key):
            return float(np.median(np.concatenate([per[(cond, i, t)][key] for t in idx for i in insts])))

        res = {}
        for key, name in (("st", "median_step_ms"), ("tt", "median_ttft_s")):
            pt = med("ON", (1, 2), tr, key) / med("OFF", (1, 2), tr, key)
            bs = []
            for _ in range(2000):
                idx = list(rng.choice(tr, size=len(tr)))
                bs.append(med("ON", (1, 2), idx, key) / med("OFF", (1, 2), idx, key))
            inst = {c: med(c, (2,), tr, key) / med(c, (1,), tr, key) for c in ("OFF", "ON")}
            res[name] = dict(ratio_on_off=round(pt, 5), ci95=[round(float(np.percentile(bs, 2.5)), 5),
                                                               round(float(np.percentile(bs, 97.5)), 5)],
                             on=med("ON", (1, 2), tr, key), off=med("OFF", (1, 2), tr, key), n_traces=len(tr),
                             instance_ratio={c: round(v, 5) for c, v in inst.items()},
                             medians={f"{c}{i}": med(c, (i,), tr, key) for c in ("OFF", "ON") for i in (1, 2)})
        st, tt = res["median_step_ms"], res["median_ttft_s"]
        st["passed"] = abs(st["ratio_on_off"] - 1) <= GATE_TOL
        tol = max(GATE_TOL, max(abs(v - 1) for v in tt["instance_ratio"].values()))
        tt["tolerance"] = round(tol, 5)
        tt["ci_includes_1"] = tt["ci95"][0] <= 1.0 <= tt["ci95"][1]
        tt["passed"] = tt["ci_includes_1"] and abs(tt["ratio_on_off"] - 1) <= tol
        out["kinds"][kind] = res
    mem = {}
    for lb in labels:
        sl = OUT / f"{P['pre']}_steps_{lb}.jsonl.gz"
        if not sl.exists():
            continue
        it = {x["it"][0]: x["it"] for x in steps[lb]}
        n = ok = 0
        badx = []
        sr = [r for r in _rows(sl) if "r" in r]
        for r in sr:
            if r["i"] not in it:
                continue
            n += 1
            a = it[r["i"]]
            pr = [x for x in r["r"] if x[2] == "p"]
            dc = [x for x in r["r"] if x[2] == "d"]
            got = (len(pr), sum(x[1] for x in pr), len(dc), sum(x[1] for x in dc))
            if got == (a[1], a[2], a[3], a[4]) and abs(r["el"] - a[5]) < 0.002:
                ok += 1
            elif len(badx) < 5:
                badx.append(dict(i=r["i"], addon=got, plugin=a[1:6], el=r["el"]))
        have = {r["i"] for r in sr}
        mem[lb] = dict(joined=n, equal=ok, addon_rows=len(sr), with_dispatch_ts=sum(1 for r in sr if r.get("ts")),
                       plugin_it_rows=len(it), plugin_rows_without_addon_row=sorted(i for i in it if i not in have),
                       examples_bad=badx, passed=n > 0 and ok == n)
    out["membership"] = mem
    checks = [v["passed"] for k in out["kinds"].values() for v in (k["median_step_ms"], k["median_ttft_s"])]
    checks += [m["passed"] for m in mem.values()]
    out["passed"] = all(checks) and bool(mem)
    out["at"] = F.now()
    (OUT / f"{P['pre']}_{out_name}.json").write_text(json.dumps(out, indent=1, default=float))
    return out


# ------------------------------------------------------------------------------------------------ main
def stage(label, fns, addon=True):
    srv = start_server(label, addon)
    try:
        for fn, a in fns:
            asyncio.run(M.with_client(fn, *a))
    finally:
        stop_server(srv)
        ST["label"] = DD.ST["label"] = None
        m = X.meta_load()
        m.setdefault("stages_done", []).append(dict(label=label, at=F.now(),
                                                    elapsed_h=round((time.time() - (ST["t0"] or time.time())) / 3600, 2)))
        X.meta_save(m)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--split-only", action="store_true")
    ap.add_argument("--only", default=None, help="comma list: G (gate), B_P40, ..., A_S2")
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
                      gpu_uuid=F.GPU_UUID, eng1c_ref_server=ENG1C_REF, log_flags=M.D.LOGFLAGS, plugin=str(M.PLUGIN_DIR),
                      addon=str(STEPLOG_DIR),
                      design=dict(MODES=MODES, LOADS=LOADS, ACTIONS=ACTIONS, NFR=NFR, NTR=NTR, NHOLD=NHOLD, NREP=NREP,
                                  SEED_OFF=SEED_OFF, GATE_OFF=GATE_OFF, WARM_OFF=WARM_OFF, CAP=CAP, FILL_X=FILL_X,
                                  FLUSH_FR=FLUSH_FR, FLUSH_MIN_TOK=FLUSH_MIN_TOK, GATE_N=GATE_N, GATE_WARM=GATE_WARM,
                                  GATE_TOL=GATE_TOL, GUARD_H=GUARD_H, XB={k: band(v) for k, v in XB.items()},
                                  XA={k: band(v) for k, v in XA.items()}, TRACE_S=M.TRACE_S, TINJ0=M.TINJ0,
                                  RUN_GAP=M.RUN_GAP, ESC_MAX_TOKENS=R7.F.ESC_MAX_TOKENS),
                      monitor_user_exempt=M.USER_EXEMPT,
                      caching="prefix caching ON; native offloading to a 38 GiB host tier, filled to 1.5 x cap with "
                              "fresh histories at every server start; every background image and every action history "
                              "carries a per-run uuid namespace, so background requests and the action's KV are cold "
                              "(first piece / mono cached <= 16 checked). Mode B: the history's IMAGES are in the "
                              "processor cache (setup), the encoder cache is flushed (checked per piece); mode A: "
                              "nothing of the history is cached anywhere")
    m["smoke"] = a.smoke
    X.meta_save(m)
    threading.Thread(target=DD.exclusivity_monitor, daemon=True).start()
    threading.Thread(target=DD.machine_monitor, daemon=True).start()
    try:
        M.load_sessions(warm=False)
        if a.smoke:
            async def smk(c):
                await gate_server(c, "ON", 1, [0], True)
                for md in MODES:
                    await load_block(c, md, "P40", split, True)
            stage("SMK_ON", [(smk, ())], addon=True)
            g = gate_eval(["SMK_ON"], True)
            X.log(f"smoke membership: {[(k, v['equal'], v['joined'], v['addon_rows'], v['with_dispatch_ts']) for k, v in g['membership'].items()]}")
        else:
            only = (a.only or "G2," + ",".join(f"{md}_{ld}" for md in MODES for ld in LOADS)).split(",")
            ST["t0"] = time.time()
            m = X.meta_load()
            m["run_start"] = F.now()
            m["plan"] = only
            X.meta_save(m)
            if "G2" in only:
                # re-gate (user 2026-11-17): first gate G_* (5 / 5 trace split) failed an under-powered TTFT rule;
                # every server now runs the identical 10 + 10 traces; corrected pass rule in gate_eval
                seq = [("G2_OFF1", "OFF", 1), ("G2_ON1", "ON", 1), ("G2_ON2", "ON", 2), ("G2_OFF2", "OFF", 2)]
                for label, cond, inst in seq:
                    stage(label, [(gate_server, (cond, inst, list(range(GATE_N)), False))], addon=(cond == "ON"))
                g = gate_eval([s[0] for s in seq], False, "gate2")
                m = X.meta_load()
                m["gate2"] = dict(passed=g["passed"], at=F.now())
                X.meta_save(m)
                X.log(f"OVERHEAD RE-GATE: {'PASS' if g['passed'] else 'FAIL'}; "
                      + "; ".join(f"{k} step {v['median_step_ms']['ratio_on_off']} {v['median_step_ms']['ci95']} "
                                  f"inst {v['median_step_ms']['instance_ratio']} | ttft "
                                  f"{v['median_ttft_s']['ratio_on_off']} {v['median_ttft_s']['ci95']} tol "
                                  f"{v['median_ttft_s']['tolerance']} inst {v['median_ttft_s']['instance_ratio']}"
                                  for k, v in g["kinds"].items())
                      + f"; membership {[(k, v['equal'], v['joined'], v['plugin_it_rows']) for k, v in g['membership'].items()]}")
                if not g["passed"]:
                    raise SystemExit("overhead re-gate FAILED: STOP AND REPORT")
            ST["t0"] = time.time()                      # 6 h guard counts from the sweep start (after the gate)
            m = X.meta_load()
            m["sweep_start"] = F.now()
            m["addon_gate"] = GATE_LABEL
            X.meta_save(m)
            for md in MODES:
                for ld in LOADS:
                    lb = f"{md}_{ld}"
                    if lb not in only:
                        continue
                    if md == "A" and (time.time() - ST["t0"]) / 3600 > GUARD_H:
                        X.log(f"{GUARD_H} h elapsed before {lb}: A stages not started (B complete)")
                        m = X.meta_load()
                        m.setdefault("unfinished", []).append(lb)
                        X.meta_save(m)
                        continue
                    stage(lb, [(load_block, (md, ld, split, False))], addon=True)
    finally:
        E.STOP_MON.set()
        DD.MSTOP.set()
        E.snapshot("end")
        m = X.meta_load()
        m["void"] = E.VOID.is_set()
        m["pair_cached_mismatch"] = dict(mismatch=ST["mismatch"], compared=ST["compared"])
        m["ended"] = F.now()
        X.meta_save(m)
    from _provenance import stamp
    m = X.meta_load()
    m.setdefault("_provenance", []).append(stamp(script="study_eng1e_chain.py", model="qwen3vl-32b-instruct",
                                                 device="h100nvl_gpu2", args=a))
    X.meta_save(m)
    X.log(f"ENG1e {'smoke' if a.smoke else 'full'} finished")


if __name__ == "__main__":
    main()
