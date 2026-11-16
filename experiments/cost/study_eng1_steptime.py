#!/usr/bin/env python3
"""StudyENG1-steptime: engine step-time model, admission behaviour, paired single-action ground truth (T0) and
residency telemetry. EXCLUSIVE (vLLM venv; h100nvl GPU 2). Pre-registered in research/EXPERIMENTS.md
(StudyENG1-steptime; design decisions by the user 2026-11-15: options 1a-10 as recommended, additions (i) and (ii)).

Harness: StudySLICE1's servers and request builders, imported UNCHANGED: study_e10b_mixed (KV configs, D14 bodies via
d3_infer_vllm, exclusivity monitor, VOID), study_e10d_blocking (ms logging config, --enable-log-requests),
study_slice1_gate (the 20 ~11k and 20 ~28k D2 sessions), study_rh7_eager_lazy (uuid frame fragments, warm Cell) and
study_rh6_offload_knee (frame encoding, warm device driver). Everything new lives in this file; no shared file changes.
Servers: 32B-I @0cfaf481, vLLM 0.31.0, StudySLICE1 E0 (defaults, prefix caching ON, processor cache 128 GiB,
--enable-log-requests) + --enable-logging-iteration-details; KV-HOST adds the native offloading connector (256 GiB);
T1 adds --long-prefill-token-threshold 1024; the Part D server adds --kv-cache-metrics. Instrumented servers load the
ENG1 stat-logger plugin (experiments/cost/eng1_statlog, via PYTHONPATH; one row per engine output batch).
The overhead gate's plain server has neither the iteration-details flag nor the plugin.
Request content: every D14 image carries bytes + a per-run client uuid ('fullu'); D2 histories use fresh namespaces.
Parts: A (A1 episodic batches, A2 pieces on cached prefixes + monolithic control, A3 warm residents), B (admission:
episodic injected into a long request at 0/25/50/75 % of its solo duration; E0 and T1), C (paired with / without
single-action injection over 10-s traces; HOLDOUT split written before any run), D (residency telemetry),
W (addition (ii): Poisson 25 % + 8 warm sessions on KV-HOST, run last if the guard allows).
Rows -> results/cost/study_eng1/eng1_{partA,partB,partC,partD,overhead}_requests_h100nvl.jsonl, per-server step
rows eng1_steps/<label>.jsonl.gz, eng1_metrics_h100nvl.jsonl, eng1_monitor_h100nvl.jsonl, meta
eng1_run_meta_h100nvl.json, split eng1_holdout_split.json. Smoke: the same names with eng1_smoke_.
"""
import argparse
import ast
import asyncio
import gzip
import itertools
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
import study_e10d_blocking as D  # noqa: E402  (ms logging config + LOGFLAGS; imports study_e10b_mixed)
import study_slice1_gate as G  # noqa: E402  (pick_sessions)

import httpx  # noqa: E402

E, X, F = D.E, D.X, D.F
R6, R7, H = E.R6, E.R7, E.H
REPO = E.REPO
OUT = REPO / "results/cost/study_eng1"
PLUGIN_DIR = HERE / "eng1_statlog"
SPLIT = OUT / "eng1_holdout_split.json"

# ------------------------------------------------------------------------------------------------ design constants
KS = (1, 2, 4, 8, 16)
S_TOK = (256, 512, 1024, 2048, 4096, 8192)
S_FR = {s: round(s / 90) for s in S_TOK}                      # 3 / 6 / 11 / 23 / 46 / 91 frames
C_LBL = ("c0", "c4k", "c11k", "c26k")
JS = (0, 1, 4)
LONG = ("mono11k", "piece2048", "piece1024")
LONG_FR = {"piece2048": 23, "piece1024": 11}
OFFSETS = (0.0, 0.25, 0.50, 0.75)
LOADS = ("P25", "P40", "S2", "S4")
ACTIONS = ("piece1024", "piece2048", "mono11k", "append5", "hostreload", "burst4")
E0_ACTIONS = ("piece1024", "piece2048", "mono11k", "append5", "burst4")
W_ACTIONS = E0_ACTIONS
LOAD_I = {"P25": 0, "P40": 1, "S2": 2, "S4": 3, "W25": 4}
ACT_I = {a: i for i, a in enumerate(ACTIONS)}
SEED_IDX = {0.25: 0, 0.40: 7}                                 # StudySLICE1 / E10c level -> seed index
PEAK1 = E.PEAK[1]
CADENCE, JIT_P90 = 0.5, 0.044
TRACE_S, TINJ0 = 10.0, 3.0
NTRIALS, NHOLD, NREPEAT = 20, 6, 3
GAP = 0.3                    # idle between Part A / B / D trials (s)
RUN_GAP = 1.0                # idle between Part C runs and between setup and trace (s)
CTX_APPEND = 99              # ~9k context for the Part C append (99 frames)
APPEND_FR = 5
FILLER_N = 3                 # 3 fresh ~26k histories (~78k tokens > 62,944-token pool) -> natural eviction
GUARD_H = 10.0
EP_POOL = 3000               # Part C clips: the first 3,000 N=1 manifest requests (bodies cached)

BASE_KEYS = {"model_tag", "trust_request_mm_kwargs", "enable_prompt_tokens_details", "host", "port", "model", "dtype",
             "max_model_len", "served_model_name", "gpu_memory_utilization", "enable_prefix_caching",
             "limit_mm_per_prompt", "mm_processor_kwargs", "mm_processor_cache_gb", "enable_log_requests"}

ST = dict(t_guard0=None, smoke=False, seq=itertools.count(), mismatch=0, compared=0)

# User exception (2026-11-15, after the 15:17 VOID): the user's own non-GPU file activity on this host (archiving and
# transfer tools) does not void ENG1 runs. ENG1 only: the shared monitor's safe-command list is extended for this
# process; our own python / vllm / torch / ffmpeg processes outside the job and any foreign process on GPU 2 still
# void / stop the run. The monitor still records every process's CPU in each snapshot.
USER_EXEMPT = ("sftp-server", "sftp", "scp", "rsync", "tar ", "split ", "gzip", "pigz", "zstd", "xz ", "cp ", "mv ",
               "rm ", "cat ")
E.SAFE_CMDS = tuple(E.SAFE_CMDS) + tuple(x for x in USER_EXEMPT if x not in E.SAFE_CMDS)
P = {}


def set_paths(smoke, gate=False):
    pre = "eng1_gate" if gate else ("eng1_smoke" if smoke else "eng1")
    OUT.mkdir(parents=True, exist_ok=True)
    for k in ("partA", "partB", "partC", "partD", "overhead", "frontend", "validate"):
        P[k] = OUT / f"{pre}_{k}_requests_h100nvl.jsonl"
    P["metrics"] = OUT / f"{pre}_metrics_h100nvl.jsonl"
    P["steps"] = OUT / f"{pre}_steps"
    P["steps"].mkdir(exist_ok=True)
    E.MON = OUT / f"{pre}_monitor_h100nvl.jsonl"
    X.META_PATH = OUT / f"{pre}_run_meta_h100nvl.json"
    X.CURRENT = REPO / "logs/eng1_current.json"
    G.X.META_PATH = X.META_PATH


def write(key, rows):
    with open(P[key], "a") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def new_ns(p="E1"):
    return f"{p}{next(ST['seq'])}x{os.getpid() % 1000}"


# ------------------------------------------------------------------------------------------------ HOLDOUT split
def make_split():
    cells = [(l, a) for l in LOADS for a in ACTIONS] + [("W25", a) for a in W_ACTIONS]
    rng = random.Random(20261115)
    hold = {f"{l}|{a}": sorted(rng.sample(range(NTRIALS), NHOLD)) for l, a in cells}
    rng2 = random.Random(20261117)
    order = {f"{l}|{a}": ["with_first" if rng2.random() < 0.5 else "without_first" for _ in range(NTRIALS)]
             for l, a in cells}
    rep = {k: [t for t in range(NTRIALS) if t not in v][:NREPEAT] for k, v in hold.items()}
    return dict(rule="random.Random(20261115).sample(range(20), 6) per (load, action) in the order (P25, P40, S2, "
                     "S4) x (piece1024, piece2048, mono11k, append5, hostreload, burst4), then W25 x (piece1024, "
                     "piece2048, mono11k, append5, burst4)", holdout=hold,
                order_rule="random.Random(20261117): one draw per (cell, trial) in cell order; < 0.5 -> with first",
                order=order, noise_repeat_rule="the first 3 FIT trials of each cell get an independent repeat of "
                                               "the without run", noise_repeat=rep)


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


# ------------------------------------------------------------------------------------------------ guard
def guard_ok():
    if ST["smoke"] or ST["t_guard0"] is None or ST.get("exempt"):
        return True
    return (time.time() - ST["t_guard0"]) / 3600 < GUARD_H


class GuardStop(Exception):
    pass


def check_void():
    if E.VOID.is_set():
        raise SystemExit("run VOID (exclusivity) - STOP")


# ------------------------------------------------------------------------------------------------ server
INSTR = {True: (True, True), False: (False, False), "plugin": (True, False), "iter": (False, True)}


def start_server(label, kv="KVGPU", eng="E0", instr=True, kvm=False):
    """instr: True = plugin + iteration details; False = neither; 'plugin' / 'iter' = that component only."""
    F.require_idle()
    use_plugin, use_iter = INSTR[instr]
    extra = (["--enable-logging-iteration-details"] if use_iter else []) + \
            (["--long-prefill-token-threshold", "1024"] if eng == "T1" else []) + (["--kv-cache-metrics"] if kvm else [])
    flags = E.KV[kv] + D.LOGFLAGS + extra
    steps = P["steps"] / f"{label}.jsonl"
    if use_plugin:
        os.environ["PYTHONPATH"] = str(PLUGIN_DIR)
        os.environ["ENG1_STATLOG_PATH"] = str(steps)
    else:
        os.environ.pop("PYTHONPATH", None)
        os.environ.pop("ENG1_STATLOG_PATH", None)
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
    want = set(BASE_KEYS)
    if kv == "KVHOST":
        want.add("kv_offloading_size")
    if use_iter:
        want.add("enable_logging_iteration_details")
    if eng == "T1":
        want.add("long_prefill_token_threshold")
    if kvm:
        want.add("kv_cache_metrics")
    got = set(d) - {"kv_offloading_backend"}
    ok = (got == want and (not use_iter or d.get("enable_logging_iteration_details") is True)
          and (eng != "T1" or d.get("long_prefill_token_threshold") == 1024)
          and (not kvm or d.get("kv_cache_metrics") is True)
          and (kv != "KVHOST" or float(d.get("kv_offloading_size", 0)) == 256.0))
    plugin_ok = ("eng1_statlog" in txt) == use_plugin
    async_sched = re.findall(r"async_scheduling[=': ]+(\w+)", txt)
    info.update(kv_config=kv, engine=eng, instrumented=instr, kv_cache_metrics=kvm, extra_flags=extra,
                non_default_args=nd, flags_verified=bool(ok), unexpected=sorted(got - want), missing=sorted(want - got),
                plugin_loaded="eng1_statlog" in txt, steps_file=str(steps) + ".gz" if use_plugin else None,
                async_scheduling_log=async_sched[-1] if async_sched else None, host_mem=E.R5.host_mem(srv.proc.pid))
    m = X.meta_load()
    m.setdefault("servers", []).append(dict(label=label, started=F.now(), flags=flags, **info))
    X.meta_save(m)
    if not ok or not plugin_ok:
        srv.stop()
        raise SystemExit(f"{label}: non-default args {sorted(got)} vs declared {sorted(want)} (plugin {plugin_ok}): STOP")
    E.snapshot(f"server_up_{label}")
    X.log(f"[{label}] up: {kv} {eng} instr {instr} kvm {kvm}; flags verified; plugin {plugin_ok}")
    srv.eng1_label, srv.eng1_steps = label, steps if use_plugin else None
    return srv


FE_RE = re.compile(r"INFO (\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\.(\d{3}) \[[^\]]+\] (Received|Added) request chatcmpl-(\S+?)[:.]?(?:\s|$)")


def frontend_rows(srv):
    """API-server 'Received request' (body parsed and rendered) and 'Added request' (handed to the engine core)
    times per request id, from the --enable-log-requests server log (ms resolution, local time)."""
    out = {}
    for line in Path(srv.logpath).read_text(errors="replace").splitlines():
        if "request chatcmpl-" not in line:
            continue
        m = FE_RE.search(line)
        if not m:
            continue
        t = time.mktime(time.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")) + int(m.group(2)) / 1000
        rid = m.group(4)
        if m.group(3) == "Added":
            rid = rid.rsplit("-", 1)[0]          # vLLM appends an 8-hex suffix to the engine request id
        out.setdefault(rid, {})["received_t" if m.group(3) == "Received" else "added_t"] = round(t, 3)
    return [dict(server=srv.eng1_label, rid=k, **v) for k, v in out.items()]


def stop_server(srv):
    srv.stop()
    write("frontend", frontend_rows(srv))
    st = getattr(srv, "eng1_steps", None)
    if st and st.exists():
        with open(st, "rb") as fi, gzip.open(str(st) + ".gz", "wb") as fo:
            shutil.copyfileobj(fi, fo)
        st.unlink()


# ------------------------------------------------------------------------------------------------ metrics
MET_KEEP = ("prefix_cache_", "external_prefix_cache_", "prompt_tokens_by_source", "prompt_tokens_cached",
            "num_preemptions", "request_queue_time_seconds_", "request_prefill_time_seconds_",
            "time_to_first_token_seconds_", "request_inference_time_seconds_", "kv_block_", "num_requests_",
            "kv_cache_usage", "mm_cache_", "iteration_tokens_total_", "offload", "connector", "kv_transfer")


async def metrics(c):
    txt = (await c.get(f"{X.BASE}/metrics")).text
    out = {"_t": round(time.time(), 6)}
    for line in txt.splitlines():
        if line.startswith("#") or not line.startswith("vllm:"):
            continue
        name, _, val = line.rpartition(" ")
        base = name.split("{")[0][5:]
        if not any(k in base for k in MET_KEEP) or base.endswith("_bucket"):
            continue
        lab = ""
        if "source=" in name:
            lab = "|" + re.search(r'source="([^"]+)"', name).group(1)
        try:
            out[base + lab] = out.get(base + lab, 0.0) + float(val)
        except ValueError:
            pass
    return out


def mdelta(m0, m1):
    return {k: round(m1[k] - m0.get(k, 0.0), 6) for k in m1 if k != "_t" and abs(m1[k] - m0.get(k, 0.0)) > 0}


# ------------------------------------------------------------------------------------------------ requests
class Cursor:
    """D14 requests for one N in manifest order; one cursor per server load (distinct requests)."""

    def __init__(self, n):
        self.reqs = [r for r in map(json.loads, gzip.open(E.D3.MAN, "rt")) if int(r["n"]) == n]
        self.i = 0

    def take(self, m):
        if self.i + m > len(self.reqs):
            raise SystemExit("episodic manifest exhausted within one server load: STOP")
        out = self.reqs[self.i:self.i + m]
        self.i += m
        return out


_EPB = {}


def ep_body(r, ns, rid):
    """D14 body (StudySLICE1 episodic: greedy, max_tokens 8, seed 0, streamed) with a per-run uuid on every image."""
    key = r["request_id"]
    if len(_EPB) > 3500:                       # memory cap (bodies are ~0.44 MB); Part C's pool is 3,000
        _EPB.clear()
    if key not in _EPB:
        b, _, _ = E.D3.body(r, "32BI")
        b = dict(b, stream=True, stream_options={"include_usage": True}, **E.GEN_EP)
        for k in ("logprobs", "top_logprobs"):
            b.pop(k, None)
        _EPB[key] = b
    b = _EPB[key]
    msgs = []
    for m in b["messages"]:
        cont, k = [], 0
        for part in m["content"]:
            if part.get("type") == "image_url":
                part = dict(part, uuid=f"{ns}|{key}|{k}")
                k += 1
            cont.append(part)
        msgs.append(dict(m, content=cont))
    return json.dumps(dict(b, messages=msgs, request_id=rid)).encode()


def d2_body(hdr, items, question, max_tokens, rid):
    """items: [(frame path, uuid, send bytes?)]; bytes + uuid ('fullu') or uuid-only reference (processor cache)."""
    parts = [json.dumps({"type": "text", "text": hdr}).encode()]
    for path, uid, send in items:
        parts.append(R7.frag_bytes("D2", path, uid) if send else R7.frag_ref(uid))
    if question:
        parts.append(json.dumps({"type": "text", "text": question}).encode())
    hd = dict(model="32BI", temperature=0.0, max_tokens=max_tokens, stream=True,
              stream_options={"include_usage": True}, request_id=rid)
    head = json.dumps(hd)[:-1].encode()
    return head + b', "messages": [{"role": "user", "content": [' + b", ".join(parts) + b"]}]}"


class Hist:
    """A D2 history in one namespace: prefix frames (sent once with bytes) + appended frames."""

    def __init__(self, frames, tag):
        self.ns, self.tag = tag, tag
        self.hdr = R6.header(tag, 0, 0)
        self.frames = list(frames)
        self.sent = set()

    def body(self, extra_frames=(), question=None, max_tokens=1, rid=None, extra_tag=""):
        items = [(p, f"{self.ns}|{p}", p not in self.sent) for p in self.frames]
        items += [(p, f"{self.ns}|{extra_tag}|{p}" if extra_tag else f"{self.ns}|{p}", True) for p in extra_frames]
        return d2_body(self.hdr, items, question, max_tokens, rid or new_ns("r"))


async def post(c, body, rid, kind, **extra):
    t_sub = time.time()
    first, usage, err, text = None, None, None, ""
    try:
        async with c.stream("POST", f"{X.BASE}/v1/chat/completions", content=body,
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
                        dl = (ch.get("delta") or {}).get("content")
                        if dl:
                            if first is None:
                                first = time.time()
                            text += dl
    except asyncio.CancelledError:
        err = "cancelled"
    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {e}"
    t_end = time.time()
    u = usage or {}
    return dict(kind=kind, rid=rid, t_submit=round(t_sub, 6), t_first=round(first, 6) if first else None,
                t_end=round(t_end, 6), ttft_s=round(first - t_sub, 5) if first else None,
                latency_s=round(t_end - t_sub, 5), prompt_tokens=u.get("prompt_tokens"),
                cached_tokens=(u.get("prompt_tokens_details") or {}).get("cached_tokens"),
                completion_tokens=u.get("completion_tokens"), output=text[:16], body_mb=round(len(body) / 1e6, 4),
                error=err, **extra)


async def post_at(c, t_at, body, rid, kind, **extra):
    d = t_at - time.time()
    if d > 0:
        await asyncio.sleep(d)
    r = await post(c, body, rid, kind, **extra)
    r["t_sched"] = round(t_at, 6)
    r["dispatch_late_s"] = round(r["t_submit"] - t_at, 5)
    return r


async def build(c, hist, part, **extra):
    """Materialise a history (max_tokens 1); cold check: cached tokens <= 16."""
    rid = new_ns("b")
    r = await post(c, hist.body(rid=rid), rid, "build", **extra)
    hist.sent.update(hist.frames)
    r["cold_ok"] = (r["cached_tokens"] or 0) <= 16
    r["n_frames"] = len(hist.frames)
    write(part, [dict(r, ns=hist.ns)])
    if r["error"]:
        raise SystemExit(f"build failed: {r['error']}")
    if not r["cold_ok"]:
        raise SystemExit(f"build {hist.ns}: {r['cached_tokens']} cached tokens on a fresh namespace: cache not cold, STOP")
    hist.prompt_tokens = r["prompt_tokens"]
    return r


async def filler(c, k0, part, **extra):
    rows = []
    for k in range(FILLER_N):
        p = SESS["p28"][(k0 + 7 + k) % len(SESS["p28"])]
        h = Hist(p["frames"], new_ns("F"))
        rows.append(await build(c, h, part, role="filler", **extra))
    return sum(r["prompt_tokens"] or 0 for r in rows)


SESS = {}


def load_sessions(warm=False):
    S = E.FL.sessions()
    picks = G.pick_sessions(S)
    for p in picks:
        p["frames"] = [path for _, path in R6.frames(S[p["sess_i"]], p["qt"])]
    SESS["S"] = S
    SESS["p11"] = [p for p in picks if p["target"] == 11000]
    SESS["p28"] = [p for p in picks if p["target"] == 28000]
    SESS["F28"] = min(len(p["frames"]) for p in SESS["p28"])
    SESS["C_FR"] = {"c0": 0, "c4k": 44, "c11k": 121, "c26k": SESS["F28"]}
    R6.preencode("D2", [S[p["sess_i"]] for p in picks])
    if warm:                                   # W25 warm sessions draw from every D2 session (E10c / RH7 plans)
        R6.preencode("D2", S)
    X.log(f"sessions: 11k frames {sorted(len(p['frames']) for p in SESS['p11'])[:3]}.., 28k min frames {SESS['F28']}")


def gap_of(r, prev_prompt):
    return None if prev_prompt is None or r["prompt_tokens"] is None else prev_prompt - (r["cached_tokens"] or 0)


# ------------------------------------------------------------------------------------------------ overhead gate (i)
async def overhead(c, label, reps, ks=(1, 8)):
    cur = Cursor(1)
    trials = [k for k in ks for _ in range(reps)]
    random.Random(11).shuffle(trials)
    rows = []
    for i, k in enumerate(trials):
        ns = new_ns("O")
        bodies = [(ep_body(r, ns, f"{ns}-{j}"), f"{ns}-{j}", r) for j, r in enumerate(cur.take(k))]
        recs = await asyncio.gather(*(post(c, b, rid, "episodic", clip=r["request_id"]) for b, rid, r in bodies))
        for r in recs:
            rows.append(dict(r, server=label, k=k, trial=i))
        await asyncio.sleep(GAP)
    write("overhead", rows)
    return rows


# ------------------------------------------------------------------------------------------------ Part A
async def part_a(c, smoke, skip=()):
    """skip: sub-blocks already measured in an earlier server load and kept ('A1', 'c0', ...): user decision
    2026-11-15 after the 15:17 VOID (A1 and A2 c0 of load A_E0_part1 kept)."""
    reps = 2 if smoke else 30
    cur = {1: Cursor(1), 3: Cursor(3)}
    rng = random.Random(101)
    # A1
    ks = (1, 16) if smoke else KS
    trials = [(n, k, r) for n in (1, 3) for k in ks for r in range(reps)]
    rng.shuffle(trials)
    if "A1" in skip:
        trials = []
    for i, (n, k, rep) in enumerate(trials):
        if not guard_ok():
            raise GuardStop("A1")
        ns = new_ns("A1")
        bodies = [(ep_body(r, ns, f"{ns}-{j}"), f"{ns}-{j}", r) for j, r in enumerate(cur[n].take(k))]
        m0 = await metrics(c) if k == 1 else None
        recs = await asyncio.gather(*(post(c, b, rid, "episodic", clip=r["request_id"]) for b, rid, r in bodies))
        hist = None
        if k == 1:
            await asyncio.sleep(0.15)
            hist = mdelta(m0, await metrics(c))
        write("partA", [dict(r, sub="A1", N=n, k=k, rep=rep, trial=i, hist_delta=hist) for r in recs])
        check_void()
        await asyncio.sleep(GAP)
    X.log(f"A1 done ({len(trials)} batches)")
    # A2
    cl = ("c11k",) if smoke else C_LBL
    sl = (1024, 8192) if smoke else S_TOK
    jl = (0, 4) if smoke else JS
    reps2 = 1 if smoke else reps
    for c_l in cl:
        if c_l in skip:
            continue
        cf = SESS["C_FR"][c_l]
        for rep in range(reps2):
            if not guard_ok():
                raise GuardStop("A2")
            p, q = SESS["p28"][rep % 20], SESS["p28"][(rep + 1) % 20]
            hist = Hist(p["frames"][:cf], new_ns("A2"))
            if cf:
                await build(c, hist, "partA", sub="A2", c_lbl=c_l, rep=rep, role="prefix")
            combos = [(s, j) for s in sl for j in jl if not (c_l == "c26k" and s == 8192)]
            rng.shuffle(combos)
            for s, j in combos:
                for attempt in (0, 1):
                    if not cf:
                        hist = Hist([], new_ns("A2"))
                    ptag = new_ns("p")
                    rid = f"{ptag}-piece"
                    body = hist.body(q["frames"][:S_FR[s]], rid=rid, extra_tag=ptag)
                    ns = new_ns("A2e")
                    eps = [(ep_body(r, ns, f"{ns}-{x}"), f"{ns}-{x}", r) for x, r in enumerate(cur[1].take(j))]
                    m0 = await metrics(c) if j == 0 else None
                    recs = await asyncio.gather(post(c, body, rid, "piece", s_tok=s, s_frames=S_FR[s]),
                                                *(post(c, b, r_, "episodic", clip=r["request_id"]) for b, r_, r in eps))
                    hd = None
                    if j == 0:
                        await asyncio.sleep(0.15)
                        hd = mdelta(m0, await metrics(c))
                    pc = recs[0]
                    g = gap_of(pc, getattr(hist, "prompt_tokens", None)) if cf else None
                    ok = (g is not None and g <= 32) if cf else (pc["cached_tokens"] or 0) <= 16
                    write("partA", [dict(r, sub="A2", c_lbl=c_l, c_frames=cf, s_tok=s, j=j, rep=rep, prefix_gap=g,
                                         prefix_ok=ok, attempt=attempt, hist_delta=hd if r is pc else None)
                                    for r in recs])
                    await asyncio.sleep(GAP)
                    if ok or attempt:
                        break
                    X.log(f"A2 {c_l} rep {rep} s {s}: prefix gap {g}: rebuilding prefix")
                    hist = Hist(p["frames"][:cf], new_ns("A2"))
                    await build(c, hist, "partA", sub="A2", c_lbl=c_l, rep=rep, role="prefix_rebuild")
            check_void()
        X.log(f"A2 {c_l} done")
    # monolithic control
    mono = [(c_l, s, r) for c_l in cl if c_l != "c0" for s in sl if not (c_l == "c26k" and s == 8192)
            for r in range(1 if smoke else 10)]
    rng.shuffle(mono)
    for c_l, s, rep in mono:
        if not guard_ok():
            raise GuardStop("A2mono")
        cf = SESS["C_FR"][c_l]
        p, q = SESS["p28"][rep % 20], SESS["p28"][(rep + 1) % 20]
        hist = Hist(p["frames"][:cf] + q["frames"][:S_FR[s]], new_ns("A2m"))
        rid = new_ns("m")
        r = await post(c, hist.body(rid=rid), rid, "mono", s_tok=s)
        write("partA", [dict(r, sub="A2mono", c_lbl=c_l, c_frames=cf, s_tok=s, rep=rep,
                             cold_ok=(r["cached_tokens"] or 0) <= 16)])
        await asyncio.sleep(GAP)
    X.log("A2 monolithic control done")
    # A3 warm residents
    ctxs = ("c11k",) if smoke else ("c4k", "c11k", "c26k")
    for c_l in ctxs:
        cf = SESS["C_FR"][c_l]
        for rep in range(reps2):
            if not guard_ok():
                raise GuardStop("A3")
            p, q = SESS["p28"][rep % 20], SESS["p28"][(rep + 1) % 20]
            hist = Hist(p["frames"][:cf], new_ns("A3"))
            await build(c, hist, "partA", sub="A3", c_lbl=c_l, rep=rep, role="context")
            order = list(jl)
            rng.shuffle(order)
            app = 0
            for j in order:
                for kind in ("append", "escalation"):
                    new = q["frames"][app:app + APPEND_FR] if kind == "append" else []
                    rid = new_ns(kind[:3])
                    body = hist.body(new, question=p["question"] if kind == "escalation" else None,
                                     max_tokens=R7.F.ESC_MAX_TOKENS if kind == "escalation" else 1, rid=rid)
                    ns = new_ns("A3e")
                    eps = [(ep_body(r, ns, f"{ns}-{x}"), f"{ns}-{x}", r) for x, r in enumerate(cur[1].take(j))]
                    prev = hist.prompt_tokens
                    recs = await asyncio.gather(post(c, body, rid, kind, ctx_frames=cf + app),
                                                *(post(c, b, r_, "episodic", clip=r["request_id"]) for b, r_, r in eps))
                    g = gap_of(recs[0], prev)
                    write("partA", [dict(r, sub="A3", c_lbl=c_l, c_frames=cf, j=j, rep=rep, resident=kind,
                                         prefix_gap=g, prefix_ok=g is not None and g <= 32)
                                    for r in recs])
                    if kind == "append":
                        # appended frames join the history under the history namespace (sent with bytes once)
                        hist.frames += new
                        hist.sent.update(new)
                        hist.prompt_tokens = recs[0]["prompt_tokens"]
                        app += APPEND_FR
                    await asyncio.sleep(GAP)
            check_void()
        X.log(f"A3 {c_l} done")


# ------------------------------------------------------------------------------------------------ Part B
async def part_b(c, eng, smoke):
    cur = Cursor(1)
    rng = random.Random(202 if eng == "E0" else 203)
    nsolo = 3 if smoke else 10
    reps = 2 if smoke else 30
    longs = ("mono11k", "piece2048") if smoke else LONG
    rows = []
    # solo episodic reference
    for i in range(nsolo):
        ns = new_ns("Bs")
        r0 = cur.take(1)[0]
        r = await post(c, ep_body(r0, ns, f"{ns}-0"), f"{ns}-0", "episodic", clip=r0["request_id"])
        rows.append(dict(r, sub="solo_ep", engine=eng, rep=i))
        await asyncio.sleep(GAP)
    write("partB", rows)
    solo_ep = float(np.median([r["ttft_s"] for r in rows if r["ttft_s"]]))
    sess_i = itertools.count()

    async def make_long(L):
        k = next(sess_i)
        p, q = SESS["p11"][k % 20], SESS["p11"][(k + 1) % 20]
        if L == "mono11k":
            h = Hist(p["frames"], new_ns("Bm"))
            rid = new_ns("L")
            return h, (lambda: (h.body(question=p["question"], max_tokens=R7.F.ESC_MAX_TOKENS, rid=rid), rid))
        h = Hist(p["frames"], new_ns("Bp"))
        await build(c, h, "partB", engine=eng, role="prefix", long=L)

        def mk():
            t = new_ns("p")
            return h.body(q["frames"][:LONG_FR[L]], rid=f"{t}-piece", extra_tag=t), f"{t}-piece"
        return h, mk

    dur = {}
    for L in longs:
        recs = []
        for i in range(nsolo):
            h, mk = await make_long(L)
            body, rid = mk()
            r = await post(c, body, rid, L)
            recs.append(dict(r, sub="solo_long", engine=eng, long=L, rep=i,
                             prefix_gap=gap_of(r, getattr(h, "prompt_tokens", None))))
            await asyncio.sleep(GAP)
        write("partB", recs)
        dur[L] = float(np.median([r["ttft_s"] for r in recs if r["ttft_s"]]))
    X.log(f"B {eng}: solo episodic {solo_ep:.3f}s, D_L {dur}")
    m = X.meta_load()
    m.setdefault("partB_ref", {})[eng] = dict(solo_ep=solo_ep, D_L=dur)
    X.meta_save(m)
    for rep in range(reps):
        if not guard_ok():
            raise GuardStop(f"B {eng}")
        ls = list(longs)
        rng.shuffle(ls)
        for L in ls:
            offs = list(OFFSETS)
            rng.shuffle(offs)
            h = mk = None
            if L != "mono11k":
                h, mk = await make_long(L)
            for off in offs:
                if L == "mono11k":
                    h, mk = await make_long(L)
                body, rid = mk()
                ns = new_ns("Be")
                r0 = cur.take(1)[0]
                t0 = time.time() + 0.05
                recs = await asyncio.gather(post_at(c, t0, body, rid, L),
                                            post_at(c, t0 + off * dur[L], ep_body(r0, ns, f"{ns}-0"), f"{ns}-0",
                                                    "episodic", clip=r0["request_id"]))
                write("partB", [dict(r, sub="inject", engine=eng, long=L, offset=off, D_L=dur[L], solo_ep=solo_ep,
                                     rep=rep, prefix_gap=gap_of(recs[0], getattr(h, "prompt_tokens", None))
                                     if r is recs[0] else None) for r in recs])
                await asyncio.sleep(GAP)
        check_void()
    X.log(f"B {eng} done")


# ------------------------------------------------------------------------------------------------ Part C
_EPPOOL = []


def ep_pool():
    if not _EPPOOL:
        _EPPOOL.extend(r for r in map(json.loads, gzip.open(E.D3.MAN, "rt")) if int(r["n"]) == 1)
        del _EPPOOL[EP_POOL:]
    return _EPPOOL


def arrivals(load, trial):
    if load in ("P25", "P40", "W25"):
        frac = 0.40 if load == "P40" else 0.25
        rate = frac * PEAK1
        rng = np.random.default_rng(SEED_IDX[frac] + 100 * trial)
        t = np.cumsum(rng.exponential(1.0 / rate, size=int(rate * TRACE_S * 3) + 10))
        return [(float(x), None) for x in t[t < TRACE_S]]
    S = int(load[1])
    rng = np.random.default_rng(5000 + 100 * S + 10 * trial)
    sigma = JIT_P90 / 1.6448536269514722
    phases = rng.uniform(0.0, CADENCE, size=S)
    out = []
    for s in range(S):
        k = 0
        while phases[s] + k * CADENCE < TRACE_S:
            out.append((float(phases[s] + k * CADENCE + abs(rng.normal(0.0, sigma))), s))
            k += 1
    return sorted(out)


def trial_plan(load, action, trial):
    arr = arrivals(load, trial)
    li, ai = LOAD_I[load], ACT_I[action]
    tinj = TINJ0 + float(np.random.default_rng(70000 + 1000 * li + 100 * ai + trial).uniform())
    pool = ep_pool()
    clips = np.random.default_rng(80000 + 1000 * li + 100 * ai + trial).choice(len(pool), size=len(arr) + 4,
                                                                                 replace=False)
    return dict(arr=arr, tinj=round(tinj, 4), clips=[pool[int(i)] for i in clips[:len(arr)]],
                burst=[pool[int(i)] for i in clips[len(arr):]])


async def run_once(c, load, action, trial, mode, pair, holdout, warm=False):
    """One run of a triple: setup (identical in every mode), 1 s idle, the 10-s trace, drain."""
    pl = trial_plan(load, action, trial)
    ns = new_ns("C")
    base = dict(load=load, action=action, trial=trial, mode=mode, pair=pair, holdout=holdout, run_ns=ns,
                t_inj_rel=pl["tinj"])
    rows = []
    p, q = SESS["p11"][trial % 20], SESS["p11"][(trial + 1) % 20]
    inj = None
    if action in ("piece1024", "piece2048"):
        h = Hist(p["frames"], f"{ns}h")
        await build(c, h, "partC", **base, role="setup_prefix")
        nfr = 11 if action == "piece1024" else 23
        inj = lambda: (h.body(q["frames"][:nfr], rid=f"{ns}-inj", extra_tag=f"{ns}i"), h.prompt_tokens)
    elif action == "append5":
        h = Hist(p["frames"][:CTX_APPEND], f"{ns}h")
        await build(c, h, "partC", **base, role="setup_context")
        inj = lambda: (h.body(p["frames"][CTX_APPEND:CTX_APPEND + APPEND_FR], rid=f"{ns}-inj", extra_tag=f"{ns}i"),
                       h.prompt_tokens)
    elif action == "hostreload":
        h = Hist(p["frames"], f"{ns}h")
        await build(c, h, "partC", **base, role="setup_history")
        await filler(c, trial, "partC", **base)
        inj = lambda: (h.body(question=p["question"], max_tokens=R7.F.ESC_MAX_TOKENS, rid=f"{ns}-inj"), h.prompt_tokens)
    elif action == "mono11k":
        h = Hist(p["frames"], f"{ns}h")
        inj = lambda: (h.body(question=p["question"], max_tokens=R7.F.ESC_MAX_TOKENS, rid=f"{ns}-inj"), None)
    cell = plans = None
    if warm:
        sp = R7.spec("EAGER", 8, tag=f"{ns}w")
        sp["offload"] = 256
        cell = R7.Cell(sp, 0)
        cell.t0 = time.time()
        plans, offsets = H.plan(8, trial)
        await asyncio.gather(*(cell.post("warmup", d, 0, plans[d][0], offsets[d], in_window=False) for d in range(8)))
    await asyncio.sleep(RUN_GAP)
    bodies = [(ep_body(r, ns, f"{ns}-bg{i}"), f"{ns}-bg{i}", r) for i, r in enumerate(pl["clips"])]
    injb = []
    if mode == "with":
        if action == "burst4":
            injb = [(ep_body(r, ns, f"{ns}-inj{i}"), f"{ns}-inj{i}", None) for i, r in enumerate(pl["burst"])]
        else:
            b, prev = inj()
            injb = [(b, f"{ns}-inj", prev)]
    m0 = await metrics(c)
    t0 = time.time() + 0.3
    tasks = [post_at(c, t0 + a, b, rid, "episodic", idx=i, stream=s, arrival_rel=round(a, 4), clip=r["request_id"])
             for i, ((a, s), (b, rid, r)) in enumerate(zip(pl["arr"], bodies))]
    tasks += [post_at(c, t0 + pl["tinj"], b, rid, "inject", idx=i, prev_prompt=prev) for i, (b, rid, prev) in
              enumerate(injb)]
    dev = []
    if warm:
        async def devs():
            await asyncio.sleep(max(0.0, t0 - time.time()))
            await asyncio.gather(*(R6.device(cell, d, plans[d], offsets[d], t0 + TRACE_S) for d in range(8)))
        dev = [devs()]
    res = await asyncio.gather(*tasks, *dev)
    if warm:
        if cell.inflight:
            await asyncio.wait(list(cell.inflight), timeout=300)
        for x in cell.records:
            if x["kind"] != "warmup":
                rows.append(dict(x, **base, kind="warm_" + x["kind"], t0_trace=round(t0, 6)))
        await cell.client.aclose()
    m1 = await metrics(c)
    for r in res[:len(tasks)]:
        r.update(base, t0_trace=round(t0, 6))
        if r["kind"] == "inject" and r["prev_prompt"] is not None:
            r["prefix_gap"] = gap_of(r, r["prev_prompt"])
        rows.append(r)
    rows.append(dict(kind="run_summary", **base, t0_trace=round(t0, 6), metrics_delta=mdelta(m0, m1),
                     n_bg=len(pl["arr"]), n_inj=len(injb)))
    write("partC", rows)
    return rows


def pair_check(a, b):
    """Per background request: cached tokens equal across the two runs and cold (<= 16)."""
    ca = {r["idx"]: r["cached_tokens"] for r in a if r.get("kind") == "episodic"}
    cb = {r["idx"]: r["cached_tokens"] for r in b if r.get("kind") == "episodic"}
    bad = sum(1 for i in ca if ca[i] != cb.get(i) or (ca[i] or 0) > 16)
    def wk(rows):
        return sorted((r["device"], r["session"], r["session_t"], r["kind"], r.get("cached_tokens") or 0)
                      for r in rows if str(r.get("kind", "")).startswith("warm_"))
    wa, wb = wk(a), wk(b)
    return bad, len(ca), (wa == wb) if (wa or wb) else None


async def part_c_block(c, load, actions, split, smoke, warm=False):
    rng = random.Random(30000 + LOAD_I[load])
    trials = [(a, t) for a in actions for t in range(NTRIALS)]
    rng.shuffle(trials)
    if smoke:
        trials = [next(x for x in trials if x[0] == a) for a in actions]
    for a, t in trials:
        if not guard_ok():
            raise GuardStop(f"C {load}")
        key = f"{load}|{a}"
        hold = t in split["holdout"][key]
        order = ["with", "without"] if split["order"][key][t] == "with_first" else ["without", "with"]
        pair = new_ns("pair")
        runs = {}
        for mode in order:
            runs[mode] = await run_once(c, load, a, t, mode, pair, hold, warm)
        bad, n, wok = pair_check(runs["with"], runs["without"])
        ST["mismatch"] += bad
        ST["compared"] += n
        rep_rows = None
        if t in split["noise_repeat"][key] or smoke:
            rep_rows = await run_once(c, load, a, t, "repeat", pair, hold, warm)
        X.log(f"C {load} {a} t{t}{' H' if hold else ''}: pair cached mismatches {bad}/{n}, warm equal {wok}"
              f"{' + repeat' if rep_rows else ''}")
        write("partC", [dict(kind="pair_check", load=load, action=a, trial=t, pair=pair, holdout=hold,
                             mismatches=bad, n=n, warm_cached_equal=wok)])
        if ST["compared"] >= (50 if smoke else 400) and ST["mismatch"] > 0.01 * ST["compared"]:
            raise SystemExit(f"paired runs not identical: {ST['mismatch']}/{ST['compared']} cached-token mismatches: "
                             "STOP AND ASK")
        check_void()


# ------------------------------------------------------------------------------------------------ Part D
def infer_state(d, prompt):
    ext = d.get("external_prefix_cache_hits_total", d.get("external_prefix_cache_hits", 0.0))
    loc = d.get("prefix_cache_hits_total", d.get("prefix_cache_hits", 0.0))
    if prompt and ext >= 0.5 * prompt:
        return "host"
    if prompt and loc >= 0.5 * prompt:
        return "gpu"
    return "cold"


async def part_d(c, smoke):
    rng = random.Random(404)
    n1 = 2 if smoke else 30
    seq = [s for s in ("gpu", "host", "cold") for _ in range(n1)]
    rng.shuffle(seq)
    k = itertools.count()
    for i, state in enumerate(seq):
        if not guard_ok():
            raise GuardStop("D1")
        p = SESS["p11"][next(k) % 20]
        h = Hist(p["frames"], new_ns("D"))
        if state in ("gpu", "host"):
            await build(c, h, "partD", conc=1, role="setup", state=state)
        if state == "host":
            await filler(c, i, "partD", conc=1)
        rid = new_ns("Dq")
        m0 = await metrics(c)
        r = await post(c, h.body(question=p["question"], max_tokens=R7.F.ESC_MAX_TOKENS, rid=rid), rid, "query")
        await asyncio.sleep(0.1)
        d = mdelta(m0, await metrics(c))
        write("partD", [dict(r, conc=1, trial=i, state=state, metrics_delta=d,
                             inferred=infer_state(d, r["prompt_tokens"]))])
        await asyncio.sleep(GAP)
        check_void()
    X.log("D concurrency 1 done")
    for rnd in range(1 if smoke else 30):
        if not guard_ok():
            raise GuardStop("D4")
        states = [rng.choice(("gpu", "host", "cold")) for _ in range(4)]
        hs = [(s, SESS["p11"][next(k) % 20]) for s in states]
        hs = [(s, p, Hist(p["frames"], new_ns("D"))) for s, p in hs]
        for s, p, h in hs:
            if s == "host":
                await build(c, h, "partD", conc=4, role="setup", state=s, round=rnd)
        if "host" in states:
            await filler(c, 100 + rnd, "partD", conc=4, round=rnd)
        for s, p, h in hs:
            if s == "gpu":
                await build(c, h, "partD", conc=4, role="setup", state=s, round=rnd)
        m0 = await metrics(c)

        async def one(s, p, h, slot):
            rid = new_ns("Dq")
            r = await post(c, h.body(question=p["question"], max_tokens=R7.F.ESC_MAX_TOKENS, rid=rid), rid, "query")
            m1 = await metrics(c)
            d = mdelta(m0, m1)
            return dict(r, conc=4, round=rnd, slot=slot, state=s, metrics_delta=d,
                        inferred=infer_state(d, r["prompt_tokens"]))
        recs = await asyncio.gather(*(one(s, p, h, i) for i, (s, p, h) in enumerate(hs)))
        write("partD", recs)
        await asyncio.sleep(GAP)
        check_void()
    X.log("D concurrency 4 done")


# ------------------------------------------------------------------------------------------------ elapsed check
async def elapsed_check(c, n):
    """Lone requests for the async-scheduling elapsed_ms check: N=1 episodic and a 91-frame piece at c = 0."""
    cur = Cursor(1)
    cur.i = 5000
    rows = []
    for i in range(n):
        ns = new_ns("L")
        r0 = cur.take(1)[0]
        rows.append(dict(await post(c, ep_body(r0, ns, f"{ns}-0"), f"{ns}-0", "episodic"), sub="lone_ep", rep=i))
        await asyncio.sleep(0.5)
        h = Hist(SESS["p28"][i % 20]["frames"][:S_FR[8192]], new_ns("L"))
        rid = new_ns("l")
        rows.append(dict(await post(c, h.body(rid=rid), rid, "piece"), sub="lone_piece8192", rep=i))
        await asyncio.sleep(0.5)
    write("partA", rows)


# ------------------------------------------------------------------------------------------------ interval validation
async def validate_interval(c, reps):
    """User decision 2 (2026-11-15): validate the inter-output-interval step duration against the engine's per-request
    prefill time. A test request arriving at an idle engine has no preceding output, so each test request is submitted
    while a decode-only pacer (an N=1 episodic request with max_tokens 160 and ignore_eos) keeps the engine busy; the
    test request's prefill steps (steps with context tokens between its submit and first token) then all have measured
    intervals, whose sum is compared with its engine prefill time (scheduled -> first token)."""
    cur = Cursor(1)
    cur.i = 7000
    kinds = [("ep1", None), ("piece23", 23), ("piece91", 91)]
    order = [k for k in kinds for _ in range(reps)]
    random.Random(55).shuffle(order)
    rows = []
    for i, (kind, nfr) in enumerate(order):
        ns = new_ns("V")
        pr = cur.take(1)[0]
        pb = json.loads(ep_body(pr, ns, f"{ns}-pacer"))
        pb.update(max_tokens=160, min_tokens=160, ignore_eos=True)
        pacer = asyncio.create_task(post(c, json.dumps(pb).encode(), f"{ns}-pacer", "pacer"))
        await asyncio.sleep(0.45)
        if kind == "ep1":
            r0 = cur.take(1)[0]
            body, rid = ep_body(r0, ns, f"{ns}-test"), f"{ns}-test"
        else:
            h = Hist(SESS["p28"][i % 20]["frames"][:nfr], new_ns("V"))
            rid = f"{ns}-test"
            body = h.body(rid=rid)
        t = await post(c, body, rid, "test", test=kind)
        pc = await pacer
        rows += [dict(t, rep=i), dict(pc, rep=i, test=kind)]
        await asyncio.sleep(GAP)
    write("validate", rows)


# ------------------------------------------------------------------------------------------------ main
async def with_client(fn, *a, **kw):
    async with httpx.AsyncClient(timeout=None, limits=httpx.Limits(max_connections=None,
                                                                   max_keepalive_connections=None)) as c:
        return await fn(c, *a, **kw)


def stage(label, kv, eng, instr, kvm, fns):
    srv = start_server(label, kv, eng, instr, kvm)
    if ST["t_guard0"] is None and not ST["smoke"]:
        ST["t_guard0"] = time.time()
        m = X.meta_load()
        m["guard_start"] = F.now()
        X.meta_save(m)
    try:
        for fn, a, kw in fns:
            asyncio.run(with_client(fn, *a, **kw))
    finally:
        stop_server(srv)
        m = X.meta_load()
        m.setdefault("stages_done", []).append(dict(label=label, at=F.now()))
        X.meta_save(m)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--split-only", action="store_true")
    ap.add_argument("--gate", action="store_true", help="overhead gate re-run (30 reps) + interval-method validation")
    ap.add_argument("--gate2", action="store_true", help="component isolation: plugin only, iteration details only")
    ap.add_argument("--gate2r", action="store_true", help="clean repeat of the plugin-only isolation server")
    ap.add_argument("--a-skip", default="", help="Part A sub-blocks to skip (kept from an earlier load), e.g. A1,c0")
    ap.add_argument("--only", default=None, help="comma list of stages to run: A,B,C,D,W (smoke: P,E,K,M)")
    a = ap.parse_args()
    ST["smoke"] = a.smoke or a.gate or a.gate2 or a.gate2r
    set_paths(a.smoke, gate=a.gate or a.gate2 or a.gate2r)
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
                      gpu_uuid=F.GPU_UUID, kv_flags=E.KV, log_flags=D.LOGFLAGS, plugin=str(PLUGIN_DIR),
                      design=dict(KS=KS, S_TOK=S_TOK, S_FR=S_FR, JS=JS, LONG=LONG, OFFSETS=OFFSETS, LOADS=LOADS,
                                  ACTIONS=ACTIONS, TRACE_S=TRACE_S, TINJ0=TINJ0, GAP=GAP, RUN_GAP=RUN_GAP,
                                  CTX_APPEND=CTX_APPEND, FILLER_N=FILLER_N, GUARD_H=GUARD_H, EP_POOL=EP_POOL))
    m["smoke"] = a.smoke
    m["monitor_user_exempt"] = dict(cmds=USER_EXEMPT, decided="2026-11-15 by the user after the 15:17 VOID: the "
                                    "user's other non-GPU activity on the host is an exception to the VOID rule")
    X.meta_save(m)
    th = threading.Thread(target=E.monitor, daemon=True)
    th.start()
    remaining = []
    try:
        only = set((a.only or ("P,E,K,M" if a.smoke else "A,B,C,D,W")).split(","))
        load_sessions(warm=False if (a.gate or a.gate2 or a.gate2r) else (("K" in only) if a.smoke else ("W" in only)))
        m = X.meta_load()
        m["sessions"] = dict(p11=[{k: v for k, v in p.items() if k not in ("question", "frames")} |
                                  dict(n_frames=len(p["frames"])) for p in SESS["p11"]],
                             p28=[{k: v for k, v in p.items() if k not in ("question", "frames")} |
                                  dict(n_frames=len(p["frames"])) for p in SESS["p28"]], C_FR=SESS["C_FR"])
        X.meta_save(m)
        if a.gate2r:
            # plugin-only repeat: a sub-second edit process of ours ran during GATE_pluginonly's repetitions (not
            # flagged by the 30-s monitor); this clean repeat is the primary plugin-only result
            stage("GATE_pluginonly_r2", "KVGPU", "E0", "plugin", False, [(overhead, ("plugin_only_r2", 30, (8,)), {})])
        elif a.gate2:
            stage("GATE_pluginonly", "KVGPU", "E0", "plugin", False, [(overhead, ("plugin_only", 30, (8,)), {})])
            stage("GATE_iteronly", "KVGPU", "E0", "iter", False, [(overhead, ("iter_only", 30, (8,)), {})])
        elif a.gate:
            stage("GATE_plain", "KVGPU", "E0", False, False, [(overhead, ("plain", 30), {})])
            stage("GATE_E0", "KVGPU", "E0", True, False, [(overhead, ("instrumented", 30), {}),
                                                          (validate_interval, (10,), {})])
        elif a.smoke:
            reps = 10
            if "P" in only:
                stage("SMK_plain", "KVGPU", "E0", False, False, [(overhead, ("plain", reps), {})])
            if "E" in only:
                stage("SMK_E0", "KVGPU", "E0", True, False,
                      [(overhead, ("instrumented", reps), {}), (elapsed_check, (3,), {}), (part_a, (True,), {}),
                       (part_b, ("E0", True), {}), (part_c_block, ("P40", ("piece2048", "burst4"), split, True), {}),
                       (part_c_block, ("S2", ("mono11k",), split, True), {})])
            if "K" in only:
                stage("SMK_KVHOST" + ("_2" if "E" not in only else ""), "KVHOST", "E0", True, False,
                      ([(part_c_block, ("P25", ("hostreload",), split, True), {})] if "E" in only else []) +
                      [(part_c_block, ("W25", ("append5",), split, True, True), {})])
            if "M" in only:
                stage("SMK_KVHOSTm", "KVHOST", "E0", True, True, [(part_d, (True,), {})])
        else:
            plan = []
            if "A" in only:
                plan.append(("A_E0", "KVGPU", "E0", False,
                             [(part_a, (False,), dict(skip=tuple(x for x in a.a_skip.split(",") if x)))]))
            if "B" in only:
                plan.append(("B_E0", "KVGPU", "E0", False, [(part_b, ("E0", False), {})]))
                plan.append(("B_T1", "KVGPU", "T1", False, [(part_b, ("T1", False), {})]))
            if "C" in only:
                for ld in LOADS:
                    plan.append((f"C_{ld}_E0", "KVGPU", "E0", False,
                                 [(part_c_block, (ld, E0_ACTIONS, split, False), {})]))
                for ld in LOADS:
                    plan.append((f"C_{ld}_KVHOST", "KVHOST", "E0", False,
                                 [(part_c_block, (ld, ("hostreload",), split, False), {})]))
            if "D" in only:
                plan.append(("D_KVHOST", "KVHOST", "E0", True, [(part_d, (False,), {})]))
            if "W" in only:
                plan.append(("W25_KVHOST", "KVHOST", "E0", False,
                             [(part_c_block, ("W25", W_ACTIONS, split, False, True), {})]))
            for i, (label, kv, eng, kvm, fns) in enumerate(plan):
                # user decision 2026-11-15 (3b): the 10-h guard does not apply to W25, which runs all its paired
                # trials (total budget 12 h); every other stage keeps the 10-h guard
                ST["exempt"] = label.startswith("W25")
                if not guard_ok():
                    remaining = [p[0] for p in plan[i:] if not p[0].startswith("W25")]
                    if any(p[0].startswith("W25") for p in plan[i:]):
                        plan = [p for p in plan[i:] if p[0].startswith("W25")]
                        X.log(f"10-h guard reached before {label}: skipping {remaining}, running W25 (exempt)")
                        ST["exempt"] = True
                        for label2, kv2, eng2, kvm2, fns2 in plan:
                            stage(label2, kv2, eng2, True, kvm2, fns2)
                    break
                if ST["exempt"] and ST["t_guard0"] and (time.time() - ST["t_guard0"]) / 3600 > 12.0:
                    X.log("W25 starts after the 12-h total budget (user: W25 must complete all pairs): running it")
                try:
                    stage(label, kv, eng, True, kvm, fns)
                except GuardStop as g:
                    remaining = [f"{label} (stopped inside: {g})"] + [p[0] for p in plan[i + 1:]]
                    X.log(f"10-h guard reached in {label}: stopping")
                    break
    finally:
        E.STOP_MON.set()
        E.snapshot("end")
        m = X.meta_load()
        m["void"] = E.VOID.is_set()
        m["remaining_at_guard"] = remaining
        m["pair_cached_mismatch"] = dict(mismatch=ST["mismatch"], compared=ST["compared"])
        m["ended"] = F.now()
        X.meta_save(m)
    from _provenance import stamp
    m = X.meta_load()
    m.setdefault("_provenance", []).append(stamp(script="study_eng1_steptime.py", model="qwen3vl-32b-instruct",
                                                 device="h100nvl_gpu2", args=a))
    X.meta_save(m)
    X.log(f"ENG1 {'smoke' if a.smoke else 'full'} finished; remaining {remaining}")


if __name__ == "__main__":
    main()
