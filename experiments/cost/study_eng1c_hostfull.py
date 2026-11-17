#!/usr/bin/env python3
"""StudyENG1c-hostfull: serving-stack behaviour when the HOST KV tier is full (design decision D56, measurement M6).
EXCLUSIVE (vLLM venv; h100nvl GPU 2). Pre-registered in research/EXPERIMENTS.md (StudyENG1c-hostfull; design answers
by the user 2026-11-16, points 1 to 5 and the machine-monitor requirement).

Servers: StudyENG1 KV-HOST exactly (32B-I @0cfaf481, vLLM 0.31.0, StudySLICE1 E0 flags + native offloading +
--enable-logging-iteration-details + the fixed ENG1 stat-logger plugin) with ONLY --kv-offloading-size changed:
CAPS_GIB = 12 (demonstration: host smaller than the GPU pool), 27, 38, 60, and 256 (reference). One host chunk = one
16-token GPU block (blocks_per_chunk = 1) = 4 MiB, so a cap of C GiB holds C x 4,096 tokens.
Reuses (import, not edit) study_eng1_steptime.py (servers, request builders, posting, metrics, sessions, monitor,
user exemption) and study_eng1b_survival.py (Poisson arrivals). Copied and changed here, as allowed: start_server
(the cap is a parameter instead of the fixed 256; the cap is verified from the mmap size in the server log) and the
ENG1b trial (occupancy histories added, filler fixed at 1.5 x the free GPU pool).
Harness LRU simulator (Sim): replays every completed request (chunk keys = namespace + block index) under four
candidate host eviction rules; writes per-rule predictions BEFORE each Part A probe and gives the write-order
ground truth (tier at arrival) for Parts C and D.
Parts: A (eviction rule; touch), B (P_host vs host occupancy), C (telemetry host vs cold at concurrency 1/4/8),
D (paired churn with/without, HOLDOUT split), E (host-full tax; run on the Part D servers: E_empty on the fresh 256 GiB
server before its population is built, E_full after Part D at 27/38/60).
Rows -> results/cost/study_eng1c/eng1c[_smoke]_{partA..partE,frontend,pred}_h100nvl.jsonl, steps
eng1c[_smoke]_steps/<label>.jsonl.gz, machine monitor eng1c[_smoke]_machine_h100nvl.jsonl, exclusivity monitor
eng1c[_smoke]_monitor_h100nvl.jsonl, meta eng1c[_smoke]_run_meta_h100nvl.json, split eng1c_holdout_split.json.
"""
import argparse
import ast
import asyncio
import copy
import json
import os
import random
import re
import subprocess
import sys
import threading
import time
import zlib
from collections import OrderedDict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import study_eng1_steptime as M  # noqa: E402  (StudyENG1 harness, unchanged)
import study_eng1b_survival as B  # noqa: E402  (StudyENG1b harness, unchanged; poisson())

E, X, F, R7 = M.E, M.X, M.F, M.R7
OUT = M.REPO / "results/cost/study_eng1c"
SPLIT = OUT / "eng1c_holdout_split.json"

# ------------------------------------------------------------------------------------------------ design constants
TOK_PER_GIB = 4096                     # 2^30 B / (16 tokens x 256 KiB per token) x 16
GPU_POOL = 62944                       # ENG1 / ENG1b KV-HOST GPU pool (tokens); checked at every server start
S_HIST = 11184                         # nominal history (D56); measured per build
CAPS = (27, 38, 60)
DEMO_CAP, REF_CAP = 12, 256
BLK = 16
MARGIN = 10000                         # token margin of every constructed A / C state
RULES = ("FIFO", "LRU_any", "LRU_host", "R4_code")
A_PATTERNS = ("PF", "P0a", "P0b", "PG", "PH", "PM")
A_REPS = 5
B_OCC = (0.0, 0.5, 0.9, 1.1)
B_REPS = 20
B_GAP = 30.0
B_FILL = 1.5
C_CONC = {1: 30, 4: 15, 8: 10}         # concurrency -> rounds
D_LOADS = ("P25", "S2")
D_VARIANTS = ("mono", "piece2048", "piece1024")
D_NTR, D_NHOLD, D_NREP = 20, 5, 3
D_POP = {27: 20, 38: 28, 60: 44, 256: 44}     # 2 x cap in histories (Hc / 11,184 rounded x 2); 256 uses 60's
E_TRACES = 20
HOST_MARGIN_GIB = 192                  # MemAvailable must exceed cap + this (128 GiB processor cache + 64 GiB)

ST = dict(smoke=False, seq=0, t0=None, mismatch=0, compared=0, cap=None, label=None)
P = M.P
SIMS = {}                              # rule -> Sim, per server stage


def hc_tokens(cap):
    return int(cap * TOK_PER_GIB)


def set_paths(smoke):
    pre = "eng1c_smoke" if smoke else "eng1c"
    OUT.mkdir(parents=True, exist_ok=True)
    for k in ("partA", "partB", "partC", "partD", "partE", "frontend", "pred", "trials"):
        P[k] = OUT / f"{pre}_{k}_h100nvl.jsonl"
    P["requests"] = P["partB"]
    P["steps"] = OUT / f"{pre}_steps"
    P["steps"].mkdir(exist_ok=True)
    E.MON = OUT / f"{pre}_monitor_h100nvl.jsonl"
    P["machine"] = OUT / f"{pre}_machine_h100nvl.jsonl"
    X.META_PATH = OUT / f"{pre}_run_meta_h100nvl.json"
    X.CURRENT = M.REPO / "logs/eng1c_current.json"
    M.G.X.META_PATH = X.META_PATH


def write(key, rows):
    M.write(key, rows)


def nns(p):
    ST["seq"] += 1
    return f"{p}{ST['seq']}x{os.getpid() % 1000}c"


# ------------------------------------------------------------------------------------------------ HOLDOUT split (D)
def d_cells():
    return [(c, l, v) for c in CAPS + (REF_CAP,) for l in D_LOADS for v in D_VARIANTS]


def make_split():
    rng = random.Random(20261116)
    hold = {f"{c}|{l}|{v}": sorted(rng.sample(range(D_NTR), D_NHOLD)) for c, l, v in d_cells()}
    rng2 = random.Random(20261118)
    order = {f"{c}|{l}|{v}": ["with_first" if rng2.random() < 0.5 else "without_first" for _ in range(D_NTR)]
             for c, l, v in d_cells()}
    rep = {k: [t for t in range(D_NTR) if t not in v][:D_NREP] for k, v in hold.items()}
    return dict(study="StudyENG1c-hostfull Part D", reserved_for="later T0 extension; recorded, NOT analysed",
                rule="random.Random(20261116).sample(range(20), 5) per (cap, load, variant) in the order caps (27, 38, "
                     "60, 256) x loads (P25, S2) x variants (mono, piece2048, piece1024)", holdout=hold,
                order_rule="random.Random(20261118): one draw per (cell, trial) in cell order; < 0.5 -> with first",
                order=order, noise_repeat_rule="the first 3 FIT trials of each cell get an independent repeat of the "
                                               "without run", noise_repeat=rep,
                target_rule="history index = random.Random(20261119 + 1000 * cell index + trial).randrange(population)",
                population=D_POP)


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


# ------------------------------------------------------------------------------------------------ simulator
class Sim:
    """Chunk-level two-tier model (GPU and host both LRU-ordered OrderedDicts, oldest first). A request on prompt
    chunk keys k_0..k_n-1: GPU hit = leading run on GPU; host hit = following run on host (the connector looks up
    from the GPU boundary); the rest is computed and written through to host (insert order head -> tail). At finish:
      FIFO      no refresh;
      LRU_any   every chunk of the prompt that is on host is refreshed;
      LRU_host  only chunks loaded from host (and computed ones) are refreshed;
      R4_code   vLLM 0.31.0 reading: a request with NO host load re-offers its whole prompt (missing chunks re-stored,
                all refreshed); a request WITH a host load refreshes only loaded + computed chunks.
    Refresh order puts the head newest (tail evicted first); GPU likewise (freed tail first)."""

    def __init__(self, rule, host_tok, gpu_tok=GPU_POOL):
        self.rule, self.hcap, self.gcap = rule, host_tok // BLK, gpu_tok // BLK
        self.host, self.gpu = OrderedDict(), OrderedDict()

    def lookup(self, keys):
        g = 0
        while g < len(keys) and keys[g] in self.gpu:
            g += 1
        h = 0
        while g + h < len(keys) and keys[g + h] in self.host:
            h += 1
        return g, h

    def request(self, keys):
        g, h = self.lookup(keys)
        comp, loaded = keys[g + h:], keys[g:g + h]
        own = set(keys)
        for k in comp:
            if k not in self.host:
                self.host[k] = None
        if self.rule == "LRU_any":
            ref = [k for k in keys if k in self.host]
        elif self.rule == "LRU_host":
            ref = loaded + comp
        elif self.rule == "R4_code":
            if h == 0:
                for k in keys[:g]:
                    if k not in self.host:
                        self.host[k] = None
                ref = list(keys)
            else:
                ref = loaded + comp
        else:
            ref = []
        for k in reversed(ref):
            self.host.move_to_end(k)
        self._evict(self.host, self.hcap, own)
        for k in reversed(keys):
            self.gpu[k] = None
            self.gpu.move_to_end(k)
        self._evict(self.gpu, self.gcap, own)
        return g * BLK, h * BLK, len(comp) * BLK

    @staticmethod
    def _evict(od, cap, own):
        skipped = []
        while len(od) > cap and od:
            k, _ = od.popitem(last=False)
            if k in own:
                skipped.append(k)
        for k in reversed(skipped):
            od[k] = None
            od.move_to_end(k, last=False)

    def resident(self, keys):
        g, h = self.lookup(keys)
        return dict(gpu=g * BLK, host=h * BLK, n=len(keys) * BLK, host_any=sum(k in self.host for k in keys) * BLK)


def keys_of(ns, prompt_tokens, tail_unique=None):
    """Chunk keys of a prompt in history namespace ns; the last `tail_unique` chunks (template tokens after a piece)
    are request-unique."""
    n = (prompt_tokens or 0) // BLK
    if tail_unique:
        u = min(n, 2)
        return [(ns, i) for i in range(n - u)] + [(tail_unique, i) for i in range(u)]
    return [(ns, i) for i in range(n)]


def sim_reset(cap):
    SIMS.clear()
    for r in RULES:
        SIMS[r] = Sim(r, hc_tokens(cap))


def sim_feed(keys):
    out = {}
    for r, s in SIMS.items():
        out[r] = s.request(keys)
    return out


def sim_feed_row(r, ns, tail_unique=False):
    if r.get("prompt_tokens") and not r.get("error"):
        sim_feed(keys_of(ns, r["prompt_tokens"], r["rid"] if tail_unique else None))


# ------------------------------------------------------------------------------------------------ machine monitor
MSTOP = threading.Event()


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
    load = os.getloadavg()
    return dict(t=round(time.time(), 3), gpus=gpus, mem_gib=mem, load1=round(load[0], 2), stage=ST.get("label"))


def machine_monitor():
    with open(P["machine"], "a") as f:
        while not MSTOP.is_set():
            try:
                f.write(json.dumps(machine_snapshot()) + "\n")
                f.flush()
            except Exception as e:  # noqa: BLE001
                f.write(json.dumps(dict(t=time.time(), error=str(e))) + "\n")
            MSTOP.wait(5.0)


# ------------------------------------------------------------------------------------------------ server (copied)
MMAP_RE = re.compile(r"Created mmap file \S+ \(([\d.]+) GB\)")


def start_server(label, cap):
    """Copy of study_eng1_steptime.start_server (instr=True, kv=KVHOST, eng=E0, kvm=False) with the host cap as a
    parameter. Checks: GPU 2 idle; host MemAvailable > cap + HOST_MARGIN_GIB; non-default args == ENG1 KV-HOST set and
    kv_offloading_size == cap (the only difference from ENG1 KV-HOST); plugin loaded; GPU pool == 62,944 tokens;
    cap enforced (mmap size in the server log == cap bytes, within 0.5 %)."""
    F.require_idle()
    ms = machine_snapshot()
    avail = ms["mem_gib"].get("MemAvailable", 0)
    if avail < cap + HOST_MARGIN_GIB:
        raise SystemExit(f"{label}: host MemAvailable {avail} GiB < cap {cap} + {HOST_MARGIN_GIB} GiB margin: STOP")
    flags = M.E.COMMON + ["--kv-offloading-backend", "native", "--kv-offloading-size", f"{cap:g}"] + M.D.LOGFLAGS + \
        ["--enable-logging-iteration-details"]
    ref = M.E.KV["KVHOST"] + M.D.LOGFLAGS + ["--enable-logging-iteration-details"]
    diff = [(a, b) for a, b in zip(ref, flags) if a != b] + ([("len", len(ref), len(flags))] if len(ref) != len(flags)
                                                            else [])
    steps = P["steps"] / f"{label}.jsonl"
    os.environ["PYTHONPATH"] = str(M.PLUGIN_DIR)
    os.environ["ENG1_STATLOG_PATH"] = str(steps)
    srv = X.Server("32BI", flags)
    info = srv.start()
    os.environ.pop("PYTHONPATH", None)
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
        abs(float(d.get("kv_offloading_size", -1)) - cap) < 1e-9
    plugin_ok = "eng1_statlog" in txt
    mm = MMAP_RE.findall(txt)
    mmap_gb = float(mm[-1]) if mm else None
    cap_ok = mmap_gb is not None and abs(mmap_gb - cap * 2 ** 30 / 1e9) <= 0.005 * cap * 2 ** 30 / 1e9
    kvt = info.get("kv_cache_tokens")
    hm = E.R5.host_mem(srv.proc.pid)
    info.update(kv_config=f"KVHOST_{cap:g}", cap_gib=cap, cap_tokens=hc_tokens(cap),
                beyond_gpu_tokens=hc_tokens(cap) - GPU_POOL, flags_diff_vs_eng1_kvhost=diff, non_default_args=nd,
                flags_verified=bool(ok), unexpected=sorted(got - want), missing=sorted(want - got),
                plugin_loaded=plugin_ok, steps_file=str(steps) + ".gz", mmap_gb=mmap_gb, cap_enforced=cap_ok,
                host_mem=hm, machine_at_start=ms)
    m = X.meta_load()
    m.setdefault("servers", []).append(dict(label=label, started=F.now(), flags=flags, **info))
    X.meta_save(m)
    bad = None
    diff_ok = (diff == []) if cap == REF_CAP else (len(diff) == 1 and diff[0][0] == "256")
    if not ok or not plugin_ok or not diff_ok:
        bad = f"non-default args {sorted(got)} vs declared {sorted(want)}; flag diff {diff}; plugin {plugin_ok}"
    elif not cap_ok:
        bad = f"cap NOT enforced: mmap {mmap_gb} GB vs cap {cap} GiB = {cap * 2 ** 30 / 1e9:.2f} GB: STOP AND ASK"
    elif kvt != GPU_POOL:
        bad = f"GPU pool {kvt} tokens != {GPU_POOL} (the cap design is relative to it): STOP AND ASK"
    if bad:
        srv.stop()
        raise SystemExit(f"{label}: {bad}")
    E.snapshot(f"server_up_{label}")
    X.log(f"[{label}] up: cap {cap} GiB ({hc_tokens(cap)} tokens, beyond GPU {hc_tokens(cap) - GPU_POOL}); mmap "
          f"{mmap_gb} GB; RSS {hm.get('server_tree_rss_gib')} GiB; flags verified (diff {diff})")
    srv.eng1_label, srv.eng1_steps = label, steps
    ST["cap"], ST["label"] = cap, label
    sim_reset(cap)
    return srv


# ------------------------------------------------------------------------------------------------ request helpers
def p11(i):
    return M.SESS["p11"][i % len(M.SESS["p11"])]


def p28(i):
    return M.SESS["p28"][i % len(M.SESS["p28"])]


async def build_hist(c, part, frames, ns, **extra):
    """Cold build (max_tokens 1) of a fresh-namespace history; fed to the simulator."""
    h = M.Hist(frames, ns)
    rid = nns("b")
    r = await M.post(c, h.body(rid=rid), rid, "build", **extra)
    h.sent.update(h.frames)
    h.prompt_tokens = r["prompt_tokens"]
    r.update(ns=ns, n_frames=len(frames), cold_ok=(r["cached_tokens"] or 0) <= 16)
    sim_feed_row(r, ns)
    write(part, [r])
    if r["error"]:
        raise SystemExit(f"build {ns} failed: {r['error']}")
    if not r["cold_ok"]:
        raise SystemExit(f"build {ns}: {r['cached_tokens']} cached tokens on a fresh namespace: STOP")
    return h, r


async def fill(c, part, target, k0, **extra):
    """Fresh ~26k (p28) histories, truncated to the remaining target, one after another; returns (tokens, hists)."""
    done, hs, k = 0, [], 0
    while done < target:
        p = p28(k0 + k)
        nfr = min(len(p["frames"]), max(1, int(round((target - done - 31) / 90))))
        h, r = await build_hist(c, part, p["frames"][:nfr], nns("F"), role="filler", **extra)
        done += r["prompt_tokens"] or 0
        hs.append(h)
        k += 1
    return done, hs


async def touch(c, part, h, role, **extra):
    """Full-prefix request (uuid references only, tiny body), max_tokens 1; metrics delta at concurrency 1."""
    rid = nns("t")
    m0 = await M.metrics(c)
    r = await M.post(c, h.body(rid=rid), rid, role, **extra)
    await asyncio.sleep(0.15)
    d = M.mdelta(m0, await M.metrics(c))
    r.update(ns=h.ns, metrics_delta=d, **src(d))
    sim_feed_row(r, h.ns)
    write(part, [r])
    return r


def src(d):
    return dict(m_local=d.get("prompt_tokens_by_source_total|local_cache_hit", 0.0),
                m_external=d.get("prompt_tokens_by_source_total|external_kv_transfer", 0.0),
                m_compute=d.get("prompt_tokens_by_source_total|local_compute", 0.0))


def classify(loc, ext, n):
    if n <= 0:
        return None
    if loc >= 0.5 * n:
        return "gpu"
    if ext >= 0.9 * (n - loc) and ext > 0:
        return "host"
    if ext > 64:
        return "partial_host"
    return "cold"


# ------------------------------------------------------------------------------------------------ Part A
def a_plan(pattern, cap, S):
    Hc = hc_tokens(cap)
    if pattern == "PF":
        return dict(D=GPU_POOL + MARGIN)
    if pattern == "P0a":
        return dict(D=Hc - S - MARGIN)
    if pattern == "P0b":
        return dict(D=Hc + MARGIN)
    if pattern == "PG":
        return dict(D1=int(0.6 * (GPU_POOL - S)), D2=Hc - S - MARGIN)
    if pattern == "PH":
        return dict(D1=GPU_POOL + MARGIN, D2=Hc - S - MARGIN)
    if pattern == "PM":
        return dict(D1=GPU_POOL - S // 2, D2=Hc - S - MARGIN)
    raise ValueError(pattern)


async def a_trial(c, cap, pattern, rep, k0):
    base = dict(sub="A", cap=cap, pattern=pattern, rep=rep)
    t = nns("AT")
    T, rb = await build_hist(c, "partA", p11(k0)["frames"], t, role="target", **base)
    S = rb["prompt_tokens"]
    pl = a_plan(pattern, cap, S)
    wit = None
    if "D" in pl:
        n, hs = await fill(c, "partA", pl["D"], k0, seg="D", **base)
        wit = hs[0]
        segs = dict(D=n)
    else:
        n1, _ = await fill(c, "partA", pl["D1"], k0, seg="D1", **base)
        tr = await touch(c, "partA", T, "touch", **base)
        n2, hs = await fill(c, "partA", pl["D2"], k0 + 5, seg="D2", **base)
        wit = hs[0]
        segs = dict(D1=n1, D2=n2, touch_local=tr["m_local"], touch_external=tr["m_external"],
                    touch_compute=tr["m_compute"])
    # probes: target and witness in a seeded random order; per-rule predictions written BEFORE the probes
    order = [("target", T), ("witness", wit)]
    random.Random(zlib.crc32(f"{cap}|{pattern}|{rep}".encode())).shuffle(order)
    pred = {}
    for r in RULES:
        s2 = copy.deepcopy(SIMS[r])
        pred[r] = []
        for role, h in order:
            g, hh, cc = s2.request(keys_of(h.ns, h.prompt_tokens))
            pred[r].append(dict(role=role, gpu=g, host=hh, compute=cc))
    write("pred", [dict(base, t=time.time(), S=S, segments=segs, order=[o[0] for o in order], predictions=pred)])
    out = []
    for i, (role, h) in enumerate(order):
        r = await touch(c, "partA", h, "probe", probe_role=role, probe_pos=i, **base)
        r["observed"] = classify(r["m_local"], r["m_external"], h.prompt_tokens)
        out.append(r)
    X.log(f"A cap {cap} {pattern} r{rep}: S {S} segs {segs} -> " +
          ", ".join(f"{o['probe_role']}: L{o['m_local']:.0f} X{o['m_external']:.0f} C{o['m_compute']:.0f}"
                    for o in out) + " | pred " +
          "; ".join(f"{r}: {pred[r][[o[0] for o in order].index('target')]['host']}" for r in RULES))
    write("partA", [dict(base, kind="a_summary", S=S, segments=segs, order=[o[0] for o in order],
                         probes=[{k: o[k] for k in ("probe_role", "m_local", "m_external", "m_compute", "observed",
                                                    "ttft_s", "cached_tokens", "prompt_tokens")} for o in out],
                         predictions=pred)])
    M.check_void()


async def part_a(c, cap, patterns, reps):
    trials = [(p, r) for p in patterns for r in range(reps)]
    random.Random(1000 + cap).shuffle(trials)
    for i, (p, r) in enumerate(trials):
        await a_trial(c, cap, p, r, 3 * i + cap)


# ------------------------------------------------------------------------------------------------ Part B
async def b_trial(c, cap, occ, rep, older=False, load="P25_f1.5", tag="B"):
    """ENG1b trial (2,048-token pieces, 5 pieces on a ~28k session, resume = 6th piece) with occupancy histories
    (p11, fresh namespaces) of occ x (Hc - prefix) tokens built AFTER the target's pieces (other devices served during
    the pause) or BEFORE them (older control); then the gap: P25 episodic + filler of 1.5 x (GPU pool - prefix),
    resume issued at the gap end regardless."""
    nfr = B.SIZES[2048]
    ns = nns("S")
    p = p28(rep * 7 + int(occ * 10) + cap)
    frames = p["frames"]
    base = dict(sub="B", cap=cap, occ=occ, older=older, load=load, rep=rep, ns=ns, tag=tag, gap=B_GAP)
    Hc = hc_tokens(cap)
    rows = []

    async def occupy(prefix_est):
        tgt = int(occ * (Hc - prefix_est))
        done, k = 0, 0
        while done < tgt:
            q = p11(rep + k + cap)
            nf = min(len(q["frames"]), max(1, int(round((tgt - done - 31) / 90))))
            _, r = await build_hist(c, "partB", q["frames"][:nf], nns("O"), role="occupancy", target_ns=ns,
                                     **{k_: v_ for k_, v_ in base.items() if k_ != "ns"})
            done += r["prompt_tokens"] or 0
            k += 1
        return tgt, done

    occ_t = occ_done = 0
    t_o0 = time.time()
    if older and occ:
        occ_t, occ_done = await occupy(10400)
    h = M.Hist(frames[:nfr], ns)
    rid = nns("b")
    r = await M.post(c, h.body(rid=rid), rid, "piece", **base, role="piece1")
    h.sent.update(h.frames)
    h.prompt_tokens = r["prompt_tokens"]
    if (r["cached_tokens"] or 0) > 16 or r["error"]:
        raise SystemExit(f"{ns} piece 1 not cold ({r['cached_tokens']}, {r['error']}): STOP")
    rows.append(r)
    sim_feed_row(r, ns, tail_unique=True)
    for k in range(1, B.NPIECES):
        new = frames[k * nfr:(k + 1) * nfr]
        rid = f"{ns}-b{k}"
        prev = h.prompt_tokens
        r = await M.post(c, h.body(new, rid=rid), rid, "piece", **base, role=f"piece{k + 1}")
        g = M.gap_of(r, prev)
        r["prefix_gap"] = g
        rows.append(r)
        sim_feed_row(r, ns, tail_unique=True)
        if r["error"] or g is None or g > 32:
            write("partB", rows)
            raise SystemExit(f"{ns} piece {k + 1}: prefix gap {g} ({r['error']}): chaining failed, STOP")
        h.frames += new
        h.sent.update(new)
        h.prompt_tokens = r["prompt_tokens"]
    P_ = h.prompt_tokens
    if not older and occ:
        occ_t, occ_done = await occupy(P_)
    t_occ = time.time() - t_o0
    m_build = await M.metrics(c)
    stop_ev = asyncio.Event()
    bg, fill_rows = [], []
    t_g0 = time.time()
    target = 0
    if load != "none":
        seed, frac = B.ep_seed(load, rep, cap)
        arr = B.poisson(frac * M.PEAK1, B_GAP + B.EP_TAIL, seed)
        pool = M.ep_pool()
        idx = np.random.default_rng(seed + 50000).choice(len(pool), size=len(arr), replace=False)
        for i, (a, j) in enumerate(zip(arr, idx)):
            rid_e = f"{ns}-ep{i}"
            bg.append(asyncio.create_task(M.post_at(c, t_g0 + a, M.ep_body(pool[int(j)], ns, rid_e), rid_e,
                                                    "episodic", idx=i, arrival_rel=round(a, 4))))
        target = int(B_FILL * (GPU_POOL - P_))
        bg.append(asyncio.create_task(B.filler_runner(c, target, rep + cap, ns, fill_rows, stop_ev)))
    await asyncio.sleep(max(0.0, t_g0 + (B_GAP if load != "none" else 2.0) - time.time()))
    m_res = await M.metrics(c)
    fed = set()
    done_now = [t.result() for t in bg if t.done() and not t.cancelled() and isinstance(t.result(), dict)]
    done_now += [x for x in fill_rows if x["t_end"] <= time.time()]
    for x in sorted(done_now, key=lambda x: x["t_end"]):
        sim_feed_row(x, x["rid"])
        fed.add(x["rid"])
    pred = {r_: SIMS[r_].resident(keys_of(ns, P_ - 32)) for r_ in RULES}
    new = frames[B.NPIECES * nfr:(B.NPIECES + 1) * nfr]
    rid = f"{ns}-resume"
    t_issue = time.time()
    fill_done_before = sum(1 for x in fill_rows if x["t_end"] <= t_issue)
    fill_tok_done = sum((x["prompt_tokens"] or 0) for x in fill_rows if x["t_end"] <= t_issue)
    res = await M.post(c, h.body(new, rid=rid), rid, "resume", **base, role="resume")
    m_after = await M.metrics(c)
    stop_ev.set()
    await asyncio.gather(*bg, return_exceptions=True)
    for t in bg:
        if not t.cancelled() and isinstance(t.result(), dict):
            rows.append(dict(t.result(), **base))
    rows += [dict(x, **base) for x in fill_rows]
    rows.append(dict(res, prefix_tokens=P_))
    write("partB", rows)
    for x in sorted([x for x in rows if x.get("kind") in ("episodic", "filler") and x["rid"] not in fed],
                    key=lambda x: x["t_end"]):
        sim_feed_row(x, x["rid"])
    sim_feed_row(res, ns, tail_unique=True)
    fill_started = len(fill_rows)
    trow = dict(base, prefix_tokens=P_, occ_target=occ_t, occ_tokens=occ_done, t_occupancy_s=round(t_occ, 2),
                t_gap_start=round(t_g0, 6), t_resume_issue=round(t_issue, 6), resume_rid=rid,
                resume_prompt=res["prompt_tokens"], resume_cached=res["cached_tokens"], resume_ttft=res["ttft_s"],
                resume_error=res["error"], filler_target=target, filler_requests=fill_started,
                filler_done_before_resume=fill_done_before, filler_tokens_done_before_resume=fill_tok_done,
                filler_finished_before_resume=bool(target) and fill_done_before == fill_started and
                sum((x["prompt_tokens"] or 0) for x in fill_rows) >= 0.98 * target,
                kv_usage_at_resume=m_res.get("kv_cache_usage_perc"),
                host_usage_at_resume=m_res.get("kv_offload_cpu_cache_usage_perc"),
                resume_window_delta=M.mdelta(m_res, m_after), gap_window_delta=M.mdelta(m_build, m_res),
                sim_pred_at_resume=pred, kv_capacity_tokens=GPU_POOL, host_capacity_tokens=Hc)
    write("trials", [trow])
    d = trow["resume_window_delta"]
    X.log(f"B cap {cap} occ {occ}{' older' if older else ''} r{rep}: prefix {P_} occ {occ_done} cached "
          f"{res['cached_tokens']} ext {d.get('prompt_tokens_by_source_total|external_kv_transfer', 0):.0f} ttft "
          f"{res['ttft_s']} filler {fill_tok_done}/{target} | R4 pred host {pred['R4_code']['host']}")
    await asyncio.sleep(1.0)
    M.check_void()
    return trow


async def part_b(c, cap, cells):
    """cells: list of (occ, older, load, n)."""
    trials = [(o, old, ld, r) for o, old, ld, n in cells for r in range(n)]
    random.Random(2000 + cap).shuffle(trials)
    for o, old, ld, r in trials:
        await b_trial(c, cap, o, r, older=old, load=ld)


# ------------------------------------------------------------------------------------------------ Part C
def c_max_host(cap):
    return max(0, int((hc_tokens(cap) - GPU_POOL - 2 * MARGIN) // S_HIST))


async def part_c(c, cap, plan):
    """plan: {concurrency: rounds}. Ground truth by construction (and simulator check):
    cold = histories built >= 1 round earlier and never touched, with >= Hc + MARGIN tokens written since (evicted
    from host under every candidate rule; checked with the simulator), else a never-built history (cold_fresh);
    host = built this round, then a GPU flush filler of GPU pool + MARGIN tokens; gpu = built after the flush."""
    Hc = hc_tokens(cap)
    rng = random.Random(3000 + cap)
    aging = []                       # (hist, written_counter_at_build)
    W = {"tok": 0}
    k = 0

    async def bld(frames, role, **kw):
        kw.setdefault("cap", cap)
        h, r = await build_hist(c, "partC", frames, nns("C"), role=role, **kw)
        W["tok"] += r["prompt_tokens"] or 0
        return h

    for conc, rounds in plan.items():
        # prime the aging pool with conc histories, then push them out of host
        for _ in range(2 * conc):
            aging.append((await bld(p11(k)["frames"], "future_cold", conc=conc), W["tok"]))
            k += 1
        n, _ = await fill(c, "partC", Hc + MARGIN, k, role_fill="prime", cap=cap, conc=conc)
        W["tok"] += n
        for rnd in range(rounds):
            states = [rng.choice(("gpu", "host", "cold")) for _ in range(conc)]
            mh = c_max_host(cap)
            redrawn = 0
            while states.count("host") > mh:
                states[states.index("host")] = rng.choice(("gpu", "cold"))
                redrawn += 1
            base = dict(sub="C", cap=cap, conc=conc, round=rnd)
            slots = [None] * conc
            for i, s in enumerate(states):
                if s == "cold":
                    el = [a for a in aging if W["tok"] - a[1] >= Hc + MARGIN and
                          all(SIMS[r_].resident(keys_of(a[0].ns, a[0].prompt_tokens))["host_any"] == 0 and
                              SIMS[r_].resident(keys_of(a[0].ns, a[0].prompt_tokens))["gpu"] == 0 for r_ in RULES)]
                    if el:
                        a = el[0]
                        aging.remove(a)
                        slots[i] = ("cold", a[0])
                    else:
                        h = M.Hist(p11(k)["frames"], nns("Cf"))
                        k += 1
                        slots[i] = ("cold_fresh", h)
            for i, s in enumerate(states):
                if s == "host":
                    slots[i] = ("host", await bld(p11(k)["frames"], "setup_host", **base))
                    k += 1
            if "host" in states:
                n, _ = await fill(c, "partC", GPU_POOL + MARGIN, k, role_fill="gpu_flush", **base)
                W["tok"] += n
            for i, s in enumerate(states):
                if s == "gpu":
                    slots[i] = ("gpu", await bld(p11(k)["frames"], "setup_gpu", **base))
                    k += 1
            truth_sim = {}
            for i, (s, h) in enumerate(slots):
                truth_sim[i] = {r_: SIMS[r_].resident(keys_of(h.ns, getattr(h, "prompt_tokens", None) or 0))
                                for r_ in RULES}
            order = list(range(conc))
            rng.shuffle(order)
            m0 = await M.metrics(c)

            async def one(i):
                s, h = slots[i]
                rid = nns("Cq")
                q = p11(i)["question"]
                r = await M.post(c, h.body(question=q, max_tokens=R7.F.ESC_MAX_TOKENS, rid=rid), rid, "query")
                m1 = await M.metrics(c)
                d = M.mdelta(m0, m1)
                return dict(r, **base, slot=i, state=s, ns=h.ns, hist_tokens=getattr(h, "prompt_tokens", None),
                            metrics_delta_since_round=d, inferred_eng1=M.infer_state(d, r["prompt_tokens"]),
                            truth_sim={r_: v for r_, v in truth_sim[i].items()}, redrawn=redrawn)
            recs = await asyncio.gather(*(one(i) for i in order))
            await asyncio.sleep(0.2)
            dround = M.mdelta(m0, await M.metrics(c))
            write("partC", recs + [dict(kind="c_round", **base, states=[s for s, _ in slots], round_delta=dround)])
            for r in sorted(recs, key=lambda x: x["t_end"]):
                sim_feed_row(r, r["ns"])
                W["tok"] += max(0, (r["prompt_tokens"] or 0) - (r["cached_tokens"] or 0))
            X.log(f"C cap {cap} c{conc} r{rnd}: " + " ".join(
                f"{x['state']}:{x['cached_tokens']}/{x['prompt_tokens']}" for x in sorted(recs, key=lambda x: x['slot'])))
            # future cold histories for later rounds
            for _ in range(sum(1 for s in states if s == "cold")):
                aging.append((await bld(p11(k)["frames"], "future_cold", **base), W["tok"]))
                k += 1
            M.check_void()


# ------------------------------------------------------------------------------------------------ Part D
def d_plan(load, cell_i, trial):
    arr = M.arrivals(load, 500 + trial)
    tinj = M.TINJ0 + float(np.random.default_rng(90000 + 100 * cell_i + trial).uniform())
    pool = M.ep_pool()
    clips = np.random.default_rng(91000 + 100 * cell_i + trial).choice(len(pool), size=len(arr), replace=False)
    return dict(arr=arr, tinj=round(tinj, 4), clips=[pool[int(i)] for i in clips])


class Pop:
    def __init__(self, n):
        self.h = []
        self.n = n


async def d_population(c, pop, part="partD"):
    for i in range(pop.n):
        p = p11(i)
        h, r = await build_hist(c, part, p["frames"], nns("H"), role="population", member=i)
        h.question = p["question"]
        h.full_prompt = None
        pop.h.append(h)
    X.log(f"population of {pop.n} histories built")


def tier_of(h):
    keys = keys_of(h.ns, h.prompt_tokens)
    out = {}
    for r_ in RULES:
        res = SIMS[r_].resident(keys)
        out[r_] = "gpu" if res["gpu"] >= 0.5 * res["n"] else ("host" if res["gpu"] + res["host"] >= 0.9 * res["n"]
                                                             else ("partial" if res["gpu"] + res["host"] > 64 else "cold"))
    return out


async def d_job(c, h, variant, tier, ns_run, t_at):
    """The device's next history request: resident (gpu / host by the R4 prediction) -> one request (history +
    question); cold -> rebuild per variant: mono (one request), or prefix-chained pieces of 23 / 11 frames over the
    history frames, the last carrying the question."""
    if t_at - time.time() > 0:
        await asyncio.sleep(t_at - time.time())
    t0 = time.time()
    late = t0 - t_at
    rows = []
    if tier in ("gpu", "host") or variant == "mono":
        rid = f"{ns_run}-inj"
        r = await M.post(c, h.body(question=h.question, max_tokens=R7.F.ESC_MAX_TOKENS, rid=rid), rid, "inject",
                         part_i=0, n_parts=1)
        rows.append(r)
    else:
        nfr = 23 if variant == "piece2048" else 11
        fr = h.frames
        cuts = list(range(nfr, len(fr), nfr)) + [len(fr)]
        sub = M.Hist([], h.ns)
        sub.hdr, sub.sent = h.hdr, h.sent          # uuid references (frames held by the cloud), as mono
        for j, e in enumerate(cuts):
            sub.frames = fr[:e]
            last = j == len(cuts) - 1
            rid = f"{ns_run}-inj{j}"
            r = await M.post(c, sub.body(question=h.question if last else None,
                                         max_tokens=R7.F.ESC_MAX_TOKENS if last else 1, rid=rid), rid, "inject",
                             part_i=j, n_parts=len(cuts))
            rows.append(r)
    t1 = time.time()
    job = dict(kind="job", t_sched=round(t_at, 6), t_start=round(t0, 6), t_first_final=rows[-1]["t_first"],
               t_end=round(t1, 6), job_ttft_s=round(rows[-1]["t_first"] - t0, 5) if rows[-1]["t_first"] else None,
               job_completion_s=round(t1 - t0, 5), n_requests=len(rows), dispatch_late_s=round(late, 5),
               cached_sum=sum(r["cached_tokens"] or 0 for r in rows), first_cached=rows[0]["cached_tokens"],
               first_prompt=rows[0]["prompt_tokens"],
               prompt_sum=sum(r["prompt_tokens"] or 0 for r in rows), errors=[r["error"] for r in rows if r["error"]])
    return rows, job


async def d_run(c, cap, load, variant, cell_i, trial, mode, pair, hold, pop, target):
    pl = d_plan(load, cell_i, trial)
    ns = nns("D")
    base = dict(sub="D", cap=cap, load=load, variant=variant, trial=trial, mode=mode, pair=pair, holdout=hold,
                run_ns=ns, t_inj_rel=pl["tinj"], target=target)
    await asyncio.sleep(M.RUN_GAP)
    h = pop.h[target]
    tiers = tier_of(h)
    bodies = [(M.ep_body(r, ns, f"{ns}-bg{i}"), f"{ns}-bg{i}", r) for i, r in enumerate(pl["clips"])]
    m0 = await M.metrics(c)
    t0 = time.time() + 0.3
    tasks = [M.post_at(c, t0 + a, b, rid, "episodic", idx=i, stream=s, arrival_rel=round(a, 4), clip=r["request_id"])
             for i, ((a, s), (b, rid, r)) in enumerate(zip(pl["arr"], bodies))]
    if mode == "with":
        tasks.append(d_job(c, h, variant, tiers["R4_code"], ns, t0 + pl["tinj"]))
    res = await asyncio.gather(*tasks)
    m1 = await M.metrics(c)
    rows = []
    job = None
    for r in res:
        if isinstance(r, tuple):
            jr, job = r
            for x in jr:
                rows.append(dict(x, **base))
            job.update(base, tier_at_arrival=tiers, hist_tokens=h.prompt_tokens)
            rows.append(job)
        else:
            rows.append(dict(r, **base, t0_trace=round(t0, 6)))
    rows.append(dict(kind="run_summary", **base, t0_trace=round(t0, 6), metrics_delta=M.mdelta(m0, m1),
                     n_bg=len(pl["arr"]), tier_at_arrival=tiers))
    write("partD", rows)
    for x in sorted([x for x in rows if x.get("kind") == "episodic"], key=lambda x: x["t_end"]):
        sim_feed_row(x, x["rid"])
    for x in rows:
        if x.get("kind") == "inject":
            sim_feed_row(x, h.ns, tail_unique=x.get("n_parts", 1) > 1 and x.get("part_i", 0) < x["n_parts"] - 1)
    return rows, job


async def churn(c, pop, rng, cap):
    i = rng.randrange(pop.n)
    h = pop.h[i]
    tiers = tier_of(h)
    rid = nns("ch")
    r = await M.post(c, h.body(question=h.question, max_tokens=1, rid=rid), rid, "churn")
    sim_feed_row(r, h.ns)
    write("partD", [dict(r, sub="D", cap=cap, member=i, tier_at_arrival=tiers)])


async def part_d(c, cap, split, pop, loads=D_LOADS, variants=D_VARIANTS, ntr=D_NTR):
    cells = d_cells()
    trials = [(l, v, t) for l in loads for v in variants for t in range(ntr)]
    random.Random(4000 + cap).shuffle(trials)
    crng = random.Random(4500 + cap)
    for l, v, t in trials:
        ci = cells.index((cap, l, v))
        key = f"{cap}|{l}|{v}"
        hold = t in split["holdout"][key]
        target = random.Random(20261119 + 1000 * ci + t).randrange(pop.n)
        order = ["with", "without"] if split["order"][key][t] == "with_first" else ["without", "with"]
        pair = nns("pair")
        runs = {}
        for mode in order:
            runs[mode] = (await d_run(c, cap, l, v, ci, t, mode, pair, hold, pop, target))[0]
        bad, n, _ = M.pair_check(runs["with"], runs["without"])
        ST["mismatch"] += bad
        ST["compared"] += n
        rep = None
        if t in split["noise_repeat"][key] or ST["smoke"]:
            rep = await d_run(c, cap, l, v, ci, t, "repeat", pair, hold, pop, target)
        job = next((x for x in runs["with"] if x.get("kind") == "job"), {})
        write("partD", [dict(kind="pair_check", sub="D", cap=cap, load=l, variant=v, trial=t, pair=pair,
                             holdout=hold, mismatches=bad, n=n)])
        X.log(f"D cap {cap} {l} {v} t{t}{' H' if hold else ''}: target {target} tier {job.get('tier_at_arrival', {}).get('R4_code')} "
              f"cached {job.get('cached_sum')}/{job.get('prompt_sum')} job ttft {job.get('job_ttft_s')} "
              f"compl {job.get('job_completion_s')}; pair mismatches {bad}/{n}{' + repeat' if rep else ''}")
        if bad:
            X.log(f"!!! D pair cached-token mismatch {bad}/{n}")
        await churn(c, pop, crng, cap)
        M.check_void()


# ------------------------------------------------------------------------------------------------ Part E
async def part_e(c, cap, cond, ntr=E_TRACES):
    """Same P25 episodic traces (identical arrivals and clips; fresh uuids) on every server."""
    for t in range(ntr):
        pl = d_plan("P25", 99, t)
        ns = nns("E")
        base = dict(sub="E", cap=cap, cond=cond, trial=t, run_ns=ns)
        await asyncio.sleep(M.RUN_GAP)
        bodies = [(M.ep_body(r, ns, f"{ns}-bg{i}"), f"{ns}-bg{i}", r) for i, r in enumerate(pl["clips"])]
        m0 = await M.metrics(c)
        t0 = time.time() + 0.3
        res = await asyncio.gather(*(M.post_at(c, t0 + a, b, rid, "episodic", idx=i, arrival_rel=round(a, 4),
                                               clip=r["request_id"])
                                     for i, ((a, s), (b, rid, r)) in enumerate(zip(pl["arr"], bodies))))
        m1 = await M.metrics(c)
        write("partE", [dict(r, **base, t0_trace=round(t0, 6)) for r in res] +
              [dict(kind="run_summary", **base, t0_trace=round(t0, 6), t_end_trace=round(time.time(), 6),
                    metrics_delta=M.mdelta(m0, m1), n_bg=len(pl["arr"]))])
        for x in sorted(res, key=lambda x: x["t_end"]):
            sim_feed_row(x, x["rid"])
        M.check_void()
    X.log(f"E cap {cap} {cond}: {ntr} traces done")


# ------------------------------------------------------------------------------------------------ smoke helpers
async def smoke_12(c):
    await a_trial(c, DEMO_CAP, "PF", 0, 1)
    for r in range(2):
        await b_trial(c, DEMO_CAP, 0.0, r, tag="smoke_rebuild")


async def smoke_27(c, split):
    await a_trial(c, 27, "PF", 0, 2)
    await a_trial(c, 27, "PG", 0, 3)
    await b_trial(c, 27, 0.5, 0, tag="smoke_occ")
    await part_c(c, 27, {4: 1})
    pop = Pop(D_POP[27])
    await d_population(c, pop)
    await part_d(c, 27, split, pop, loads=("P25",), variants=D_VARIANTS, ntr=1)
    await part_e(c, 27, "full", ntr=2)


async def smoke_256(c):
    for r in range(3):
        await b_trial(c, REF_CAP, 0.0, r, load="none", tag="smoke_resident")
    for r in range(3):
        await b_trial(c, REF_CAP, 0.0, r, tag="smoke_reload")


# ------------------------------------------------------------------------------------------------ main
def stage(label, cap, fns):
    srv = start_server(label, cap)
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
        m = X.meta_load()
        m.setdefault("stages_done", []).append(dict(label=label, at=F.now(),
                                                    elapsed_h=round((time.time() - (ST["t0"] or time.time())) / 3600, 2)))
        X.meta_save(m)


def full_plan(split, only):
    plan = []
    if "A" in only:
        for cap in CAPS:
            plan.append((f"A_c{cap}", cap, [(part_a, (cap, A_PATTERNS, A_REPS))]))
        plan.append((f"A_c{DEMO_CAP}", DEMO_CAP, [(part_a, (DEMO_CAP, ("PF",), A_REPS))]))
    if "B" in only:
        plan.append((f"B_c{REF_CAP}", REF_CAP, [(part_b, (REF_CAP, [(0.0, False, "P25_f1.5", B_REPS),
                                                                     (0.0, False, "none", 10)]))]))
        plan.append((f"B_c{DEMO_CAP}", DEMO_CAP, [(part_b, (DEMO_CAP, [(0.0, False, "P25_f1.5", B_REPS)]))]))
        for cap in CAPS:
            cells = [(o, False, "P25_f1.5", B_REPS) for o in B_OCC]
            if cap == 38:
                cells.append((0.9, True, "P25_f1.5", B_REPS))
            plan.append((f"B_c{cap}", cap, [(part_b, (cap, cells))]))
    if "C" in only:
        for cap in CAPS:
            plan.append((f"C_c{cap}", cap, [(part_c, (cap, dict(C_CONC)))]))
    if "D" in only:
        def de(cap):
            pop = Pop(D_POP[cap])

            async def run(c):
                if cap == REF_CAP and "E" in only:
                    await part_e(c, cap, "empty")
                await d_population(c, pop)
                await part_d(c, cap, split, pop)
                if cap != REF_CAP and "E" in only:
                    await part_e(c, cap, "full")
            return run
        for cap in (REF_CAP,) + CAPS:
            plan.append((f"DE_c{cap}", cap, [(de(cap), ())]))
    return plan


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--split-only", action="store_true")
    ap.add_argument("--only", default=None, help="comma list: A,B,C,D,E (smoke: 12,27,256)")
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
                      gpu_uuid=F.GPU_UUID, kv_flags_ref=E.KV["KVHOST"], log_flags=M.D.LOGFLAGS, plugin=str(M.PLUGIN_DIR),
                      design=dict(TOK_PER_GIB=TOK_PER_GIB, GPU_POOL=GPU_POOL, S_HIST=S_HIST, CAPS=CAPS,
                                  DEMO_CAP=DEMO_CAP, REF_CAP=REF_CAP, MARGIN=MARGIN, RULES=RULES,
                                  A_PATTERNS=A_PATTERNS, A_REPS=A_REPS, B_OCC=B_OCC, B_REPS=B_REPS, B_GAP=B_GAP,
                                  B_FILL=B_FILL, C_CONC=C_CONC, D_LOADS=D_LOADS, D_VARIANTS=D_VARIANTS, D_NTR=D_NTR,
                                  D_POP=D_POP, E_TRACES=E_TRACES, HOST_MARGIN_GIB=HOST_MARGIN_GIB),
                      monitor_user_exempt=M.USER_EXEMPT)
    m["smoke"] = a.smoke
    X.meta_save(m)
    th = threading.Thread(target=E.monitor, daemon=True)
    th.start()
    mth = threading.Thread(target=machine_monitor, daemon=True)
    mth.start()
    try:
        M.load_sessions(warm=False)
        if a.smoke:
            only = set((a.only or "12,27,256").split(","))
            if "12" in only:
                stage("SMK_c12", DEMO_CAP, [(smoke_12, ())])
            if "27" in only:
                stage("SMK_c27", 27, [(smoke_27, (split,))])
            if "256" in only:
                stage("SMK_c256", REF_CAP, [(smoke_256, ())])
        else:
            only = set((a.only or "A,B,C,D,E").split(","))
            plan = full_plan(split, only)
            m = X.meta_load()
            m["plan"] = [p[0] for p in plan]
            X.meta_save(m)
            for label, cap, fns in plan:
                if ST["t0"] and (time.time() - ST["t0"]) / 3600 > 10.0:
                    X.log(f"10 h elapsed before {label} (no hard stop, user decision 4a): continuing")
                stage(label, cap, fns)
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
    m.setdefault("_provenance", []).append(stamp(script="study_eng1c_hostfull.py", model="qwen3vl-32b-instruct",
                                                 device="h100nvl_gpu2", args=a))
    X.meta_save(m)
    X.log(f"ENG1c {'smoke' if a.smoke else 'full'} finished")


if __name__ == "__main__":
    main()
