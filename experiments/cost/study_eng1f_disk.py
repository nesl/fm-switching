#!/usr/bin/env python3
"""StudyENG1f-disk: is a disk tier for computed KV blocks feasible on this stack, and what does it cost (open question
Q12: reload a history pushed out of GPU and host from disk-saved KV blocks, or recompute it from raw frames)?
EXCLUSIVE (vLLM venv; h100nvl GPU 2). Pre-registered in research/EXPERIMENTS.md (StudyENG1f-disk), overnight protocol.

Stack: StudyENG1c KV-HOST at 38 GiB (flags of ENG1c's DE_c38) with the in-tree vLLM 0.31.0 disk tier: the native
`--kv-offloading-backend native --kv-offloading-size 38` pair is replaced by the equivalent `--kv-transfer-config` for
the same OffloadingConnector (vllm/config/vllm.py:1124-1157 builds exactly {"cpu_bytes_to_use": size x 2^30}) with
spec_name TieringOffloadingSpec (a CPUOffloadingSpec subclass; CPU primary tier with the same LRU policy) and one
secondary tier {"type": "fs", "root_dir": KVROOT} (vllm/v1/kv_offload/tiering/fs/manager.py: write-through cascade of
every stored chunk, O_DIRECT when the filesystem supports it, no eviction). The "off" servers of Part 4 use the native
pair, i.e. ENG1c's command exactly. ENG1 stat-logger plugin loaded (observe-only); no per-step add-on (F6).

States of a target history (11k: D2 ~11k sessions, 120 frames; 28k: ~28k sessions):
  cold       fresh namespace, image bytes, no KV anywhere (recompute)
  host       built, then pushed out of GPU by about 1.25 x the GPU pool of fresh filler (ENG1c PF), still in host
  disk       built, then pushed out of GPU AND host by fresh filler of about 1.4 x host capacity, present on disk; the
             filler's own files are deleted as it goes (study KV files only); fincore 0 % on the targets' files
For host and disk the recall uses uuid references (the images stay in the 128 GiB processor cache, as for a history
evicted while the server keeps running); cold sends bytes. Every recall carries the question (ESC_MAX_TOKENS).
Disk guard: the study's KV directory <= 100 GB and >= 150 GB free on the filesystem before every step (hard stop).
"""
import argparse
import asyncio
import gzip
import json
import os
import random
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import study_eng1_steptime as M  # noqa: E402  (StudyENG1 harness, unchanged)
import study_eng1d_loadedblock as DD  # noqa: E402  (StudyENG1d monitors, unchanged)

E, X, F, R7 = M.E, M.X, M.F, M.R7
OUT = M.REPO / "results/cost/study_eng1f"
KVROOT = Path.home() / "data/eng1f_kv/fs"
ENG1C_META = M.REPO / "results/cost/study_eng1c/eng1c_run_meta_h100nvl.json"
CAP_GIB, GPU_POOL, TOK_PER_GIB = 38, 62944, 4096
KV_DIR_CAP_GB, FREE_FLOOR_GB = 100.0, 150.0
NREP = 20
EQUIV_N, EQUIV_TOL, EQUIV_TOPK, EQUIV_MAXTOK = 10, 0.02, 20, 32
ST = dict(label=None, protected=set(), seq=0)
P = M.P


def set_paths(tag):
    OUT.mkdir(parents=True, exist_ok=True)
    pre = f"eng1f_{tag}"
    for k in ("requests", "frontend", "fill"):
        P[k] = OUT / f"{pre}_{k}_h100nvl.jsonl"
    P["steps"] = OUT / f"{pre}_statlog"
    P["steps"].mkdir(exist_ok=True)
    P["machine"] = OUT / f"{pre}_machine_h100nvl.jsonl"
    P["pre"] = pre
    E.MON = OUT / f"{pre}_monitor_h100nvl.jsonl"
    X.META_PATH = OUT / f"{pre}_run_meta_h100nvl.json"
    X.CURRENT = M.REPO / "logs/eng1f_current.json"
    M.G.X.META_PATH = X.META_PATH


def write(rows):
    M.write("requests", rows)


# ------------------------------------------------------------------------------------------------ disk guard / files
def kv_files():
    out = subprocess.run(["find", str(KVROOT), "-type", "f", "-name", "*.bin"], capture_output=True, text=True).stdout
    return set(out.split())


def disk_state():
    du = subprocess.run(["du", "-sb", str(KVROOT)], capture_output=True, text=True).stdout.split()
    st = os.statvfs(str(KVROOT))
    return dict(kv_dir_gb=round(int(du[0]) / 1e9, 2) if du else 0.0, free_gb=round(st.f_bavail * st.f_frsize / 1e9, 1))


def guard(where):
    d = disk_state()
    if d["kv_dir_gb"] > KV_DIR_CAP_GB or d["free_gb"] < FREE_FLOOR_GB:
        raise SystemExit(f"DISK GUARD at {where}: {d} (cap {KV_DIR_CAP_GB} GB, floor {FREE_FLOOR_GB} GB): STOP")
    return d


def prune(keep=None):
    """Delete this study's KV files that are not protected (filler, background, finished targets)."""
    keep = ST["protected"] if keep is None else keep
    files = kv_files()
    dead = sorted(files - keep)
    for i in range(0, len(dead), 2000):
        subprocess.run(["rm", "-f"] + dead[i:i + 2000])
    return len(dead)


def residency(paths):
    """fincore over the given files: total resident bytes (page cache)."""
    paths = sorted(paths)
    res = 0
    for i in range(0, len(paths), 500):
        out = subprocess.run(["fincore", "-b", "-n", "-o", "RES"] + paths[i:i + 500], capture_output=True,
                             text=True).stdout.split()
        res += sum(int(x) for x in out if x.isdigit())
    return res


# ------------------------------------------------------------------------------------------------ exclusivity monitor
# Copy of study_eng1d_loadedblock.exclusivity_monitor (itself a copy of the e10b monitor) with its narrow exemption
# extended by ONE more transient child of our own server. OVERNIGHT DECISION (2026-11-17 22:25, recorded in the
# report): the disk-tier server's start compiles Triton kernels, and the shared snapshot listed our own vLLM venv's
# `triton/backends/nvidia/bin/ptxas` as "ours outside the job" (the same list-before-tree race ENG1d fixed for the
# cpuinfo probe), which VOIDed the first EQ_P1 start before any measurement. Exempt only these binaries from OUR venv,
# only when the process has exited or is inside our tree; anything else still VOIDs; a foreign process on GPU 2 always
# VOIDs.
PROBES = ("site-packages/cpuinfo/cpuinfo.py --json", "site-packages/triton/backends/nvidia/bin/ptxas")


def exclusivity_monitor():
    while not E.STOP_MON.wait(30):
        rec = E.snapshot("30s")
        bad = []
        for p in rec["ours_outside_job"]:
            own_probe = any(x in p["args"] for x in PROBES) and sys.prefix in p["args"]
            # OVERNIGHT DECISION 2026-11-18 01:13: this harness's own disk-guard / prune / page-cache calls on the
            # study's KV directory (find, du, rm, fincore) hit the same list-before-tree race and VOIDed P2 P25
            own_tool = str(KVROOT) in p["args"] and p["args"].split()[0].rsplit("/", 1)[-1] in ("find", "du", "rm", "fincore")
            if (own_probe or own_tool) and (not DD.pid_alive(p["pid"]) or p["pid"] in E.tree(os.getpid())):
                X.log(f"exclusivity: transient child of our own stack exempt (not VOID): pid {p['pid']} {p['args'][:80]}")
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
    return next(s["flags"] for s in json.loads(ENG1C_META.read_text())["servers"] if s["label"] == "DE_c38")


def disk_tier_config():
    return json.dumps(dict(kv_connector="OffloadingConnector", kv_role="kv_both", kv_connector_extra_config=dict(
        spec_name="TieringOffloadingSpec", cpu_bytes_to_use=CAP_GIB * (1 << 30),
        secondary_tiers=[dict(type="fs", root_dir=str(KVROOT))])))


def start_server(label, disk=True):
    F.require_idle()
    ms = DD.machine_snapshot()
    ref = ref_flags()
    if disk:
        i = ref.index("--kv-offloading-backend")
        assert ref[i:i + 4] == ["--kv-offloading-backend", "native", "--kv-offloading-size", "38"], ref[i:i + 4]
        flags = ref[:i] + ["--kv-transfer-config", disk_tier_config()] + ref[i + 4:]
        KVROOT.mkdir(parents=True, exist_ok=True)
    else:
        flags = list(ref)
    steps = P["steps"] / f"{label}.jsonl"
    os.environ["PYTHONPATH"] = str(M.PLUGIN_DIR)
    os.environ["ENG1_STATLOG_PATH"] = str(steps)
    srv = X.Server("32BI", flags)
    info = srv.start()
    os.environ.pop("PYTHONPATH", None)
    txt = Path(srv.logpath).read_text(errors="replace")
    mm = re.findall(r"Created mmap file \S+ \(([\d.]+) GB\)", txt)
    odirect_fallback = "O_DIRECT is not supported" in txt
    tier_seen = "TieringOffloadingSpec" in txt or "FileSystemTierManager" in txt or "fs" in txt and disk
    diff = dict(removed=[x for x in ref if x not in flags], added=[x for x in flags if x not in ref])
    meta = dict(label=label, disk=disk, flags=flags, flag_diff_vs_eng1c_DE_c38=diff, kv_cache_tokens=info.get("kv_cache_tokens"),
                mmap_gb=float(mm[-1]) if mm else None, plugin_loaded="eng1_statlog" in txt, odirect_fallback=odirect_fallback,
                log=str(srv.logpath), machine_at_start=ms, disk_state=disk_state() if disk else None, started=F.now())
    m = X.meta_load()
    m.setdefault("servers", []).append(meta)
    X.meta_save(m)
    bad = None
    if info.get("kv_cache_tokens") != GPU_POOL:
        bad = f"GPU pool {info.get('kv_cache_tokens')} != {GPU_POOL}"
    elif not meta["mmap_gb"] or abs(meta["mmap_gb"] - CAP_GIB * 2 ** 30 / 1e9) > 0.005 * CAP_GIB * 2 ** 30 / 1e9:
        bad = f"host cap not 38 GiB (mmap {meta['mmap_gb']} GB)"
    elif disk and odirect_fallback:
        bad = "disk tier fell back to buffered I/O (O_DIRECT unsupported): page cache cannot be kept out (F3): STOP AND ASK"
    elif not meta["plugin_loaded"]:
        bad = "ENG1 plugin not loaded"
    if bad:
        srv.stop()
        raise SystemExit(f"{label}: {bad}")
    E.snapshot(f"server_up_{label}")
    X.log(f"[{label}] up: disk tier {disk}, flag diff {diff if disk else 'none'}, pool {meta['kv_cache_tokens']}, "
          f"mmap {meta['mmap_gb']} GB, O_DIRECT fallback {odirect_fallback}")
    srv.eng1_label, srv.eng1_steps = label, steps
    ST["label"] = DD.ST["label"] = label
    return srv


def stop_server(srv):
    time.sleep(1.0)
    M.stop_server(srv)
    ST["label"] = DD.ST["label"] = None


# ------------------------------------------------------------------------------------------------ requests
def nns(p):
    ST["seq"] += 1
    return f"{p}{ST['seq']}x{os.getpid() % 1000}f"


def sess(size, i):
    return M.SESS["p11" if size == "11k" else "p28"][i % 20]


async def build(c, size, i, role, **extra):
    """Cold build of a fresh-namespace history (max_tokens 1); returns the Hist (frames now in the processor cache)."""
    p = sess(size, i)
    h = M.Hist(p["frames"], nns("T"))
    h.question = p["question"]
    rid = nns("b")
    r = await M.post(c, h.body(rid=rid), rid, "build", role=role, size=size, member=i, ns=h.ns, **extra)
    h.sent.update(h.frames)
    h.prompt_tokens = r["prompt_tokens"]
    write([r])
    if r["error"] or (r["cached_tokens"] or 0) > 16:
        raise SystemExit(f"build {h.ns}: error {r['error']} cached {r['cached_tokens']}: STOP")
    return h


async def filler(c, tokens, protect_every=True):
    """Fresh ~26k (p28) histories, max_tokens 1, until `tokens` were computed; deletes this study's unprotected KV
    files after each one so the disk tier stays under its cap."""
    done, k = 0, 0
    while done < tokens:
        p = M.SESS["p28"][(k + 7) % len(M.SESS["p28"])]
        h = M.Hist(p["frames"], nns("F"))
        rid = nns("f")
        r = await M.post(c, h.body(rid=rid), rid, "filler")
        if r["error"]:
            raise SystemExit(f"filler error {r['error']}: STOP")
        done += r["prompt_tokens"] or 0
        k += 1
        if protect_every:
            await asyncio.sleep(1.0)
            prune()
            guard("filler")
    return done


def recall_body(h, rid, mode, logprobs=False, max_tokens=None):
    """mode 'refs': uuid references (images in the processor cache); 'bytes': image bytes (cold)."""
    if mode == "bytes":
        h2 = M.Hist(h.frames, h.ns)
        h2.hdr = h.hdr
        b = h2.body(question=h.question, max_tokens=max_tokens or R7.F.ESC_MAX_TOKENS, rid=rid)
    else:
        b = h.body(question=h.question, max_tokens=max_tokens or R7.F.ESC_MAX_TOKENS, rid=rid)
    if logprobs:
        j = json.loads(b)
        j.update(logprobs=True, top_logprobs=EQUIV_TOPK, stream=False)
        j.pop("stream_options", None)
        b = json.dumps(j).encode()
    return b


async def recall(c, h, state, mode, **extra):
    m0 = await M.metrics(c)
    rid = nns("q")
    r = await M.post(c, recall_body(h, rid, mode), rid, "recall", state=state, ns=h.ns, **extra)
    await asyncio.sleep(0.3)
    d = M.mdelta(m0, await M.metrics(c))
    rb = sum(v for k, v in d.items() if "offload" in k and "read" in k and "bytes" in k)
    rt = sum(v for k, v in d.items() if "offload" in k and "read" in k and "time" in k)
    r.update(state=state, metrics_delta=d, secondary_read_bytes=rb, secondary_read_s=rt,
             m_local=d.get("prompt_tokens_by_source_total|local_cache_hit", 0.0),
             m_external=d.get("prompt_tokens_by_source_total|external_kv_transfer", 0.0),
             m_compute=d.get("prompt_tokens_by_source_total|local_compute", 0.0))
    write([r])
    return r


async def post_json(c, body):
    t0 = time.time()
    r = await c.post(f"{X.BASE}/v1/chat/completions", content=body, headers={"Content-Type": "application/json"})
    j = r.json()
    t1 = time.time()
    ch = j["choices"][0]
    lp = (ch.get("logprobs") or {}).get("content") or []
    return dict(status=r.status_code, text=ch["message"]["content"], tokens=[x["token"] for x in lp],
                first_top=[(x["token"], x["logprob"]) for x in (lp[0]["top_logprobs"] if lp else [])],
                usage=j.get("usage"), latency_s=round(t1 - t0, 4))


# ------------------------------------------------------------------------------------------------ pre-flight item 1 + equivalence gate
async def mech_and_equiv(c):
    """Mechanism check (does the disk tier write and reload on 0.31.0) and the F4 equivalence gate."""
    prune(set())
    hs = [await build(c, "11k", i, "equiv_target") for i in range(EQUIV_N)]
    await asyncio.sleep(2.0)
    files_after_build = kv_files()
    ST["protected"] = set(files_after_build)
    X.log(f"equiv: {EQUIV_N} targets built; KV files on disk {len(files_after_build)}; {disk_state()}")
    R1, R2 = [], []
    for h in hs:
        rid = nns("e")
        R1.append(await post_json(c, recall_body(h, rid, "refs", logprobs=True, max_tokens=EQUIV_MAXTOK)))
        rid = nns("e")
        R2.append(await post_json(c, recall_body(h, rid, "refs", logprobs=True, max_tokens=EQUIV_MAXTOK)))
    # push the targets out of GPU and host (natural eviction), keeping their disk files
    n = await filler(c, int(1.4 * (CAP_GIB * TOK_PER_GIB + GPU_POOL)))
    await asyncio.sleep(2.0)
    prune()
    res = residency(ST["protected"])
    X.log(f"equiv: filler {n} tokens; target files resident bytes {res}; {disk_state()}")
    if res:
        raise SystemExit(f"F3: {res} bytes of the target KV files are in the page cache: STOP AND ASK")
    D, met = [], []
    for h in hs:
        m0 = await M.metrics(c)
        rid = nns("e")
        D.append(await post_json(c, recall_body(h, rid, "refs", logprobs=True, max_tokens=EQUIV_MAXTOK)))
        await asyncio.sleep(0.3)
        d = M.mdelta(m0, await M.metrics(c))
        met.append(dict(read_bytes=sum(v for k, v in d.items() if "offload" in k and "read" in k and "bytes" in k),
                        external=d.get("prompt_tokens_by_source_total|external_kv_transfer", 0.0),
                        local=d.get("prompt_tokens_by_source_total|local_cache_hit", 0.0),
                        compute=d.get("prompt_tokens_by_source_total|local_compute", 0.0)))

    def cmp(a, b):
        da = dict(a["first_top"])
        db = dict(b["first_top"])
        common = set(da) & set(db)
        return dict(tokens_equal=a["tokens"] == b["tokens"], top1_equal=(a["first_top"][:1] == b["first_top"][:1]
                                                                         if a["first_top"] and b["first_top"] else None),
                    max_abs_logprob_diff=max((abs(da[t] - db[t]) for t in common), default=None), n_common=len(common))
    rows = []
    for i in range(EQUIV_N):
        rows.append(dict(i=i, ns=hs[i].ns, disk_vs_resident=cmp(R1[i], D[i]), resident_repeat=cmp(R1[i], R2[i]),
                         disk_metrics=met[i], disk_usage=D[i]["usage"], resident_usage=R1[i]["usage"],
                         text_resident=R1[i]["text"], text_disk=D[i]["text"]))
    disk_loaded = sum(1 for m in met if m["read_bytes"] > 0)
    ok_tok = sum(1 for r in rows if r["disk_vs_resident"]["tokens_equal"])
    worst = max((r["disk_vs_resident"]["max_abs_logprob_diff"] or 0.0) for r in rows)
    worst_noise = max((r["resident_repeat"]["max_abs_logprob_diff"] or 0.0) for r in rows)
    passed = ok_tok == EQUIV_N and worst <= EQUIV_TOL and disk_loaded == EQUIV_N
    out = dict(n=EQUIV_N, tol=EQUIV_TOL, topk=EQUIV_TOPK, max_tokens=EQUIV_MAXTOK, tokens_identical=ok_tok,
               worst_disk_logprob_diff=worst, worst_resident_repeat_diff=worst_noise, n_loaded_from_disk=disk_loaded,
               passed=passed, rows=rows, at=F.now())
    (OUT / "eng1f_equivalence.json").write_text(json.dumps(out, indent=1, default=str))
    X.log(f"EQUIVALENCE GATE {'PASS' if passed else 'FAIL'}: tokens identical {ok_tok}/{EQUIV_N}, worst |dlogprob| "
          f"{worst:.4f} (resident repeat {worst_noise:.4f}), loaded from disk {disk_loaded}/{EQUIV_N}")
    ST["protected"] = set()
    prune()
    if not passed:
        raise SystemExit("equivalence gate FAILED: STOP")


# ------------------------------------------------------------------------------------------------ Part 1
async def part1(c, sizes=("11k", "28k"), nrep=NREP):
    for size in sizes:
        # cold
        for i in range(nrep):
            p = sess(size, i)
            h = M.Hist(p["frames"], nns("C"))
            h.question = p["question"]
            r = await recall(c, h, "cold", "bytes", part="P1", size=size, rep=i)
            await asyncio.sleep(1.0)
            prune()
            guard("P1 cold")
        X.log(f"P1 {size} cold done")
        # host-warm: build, push out of GPU only (about 1.25 x the GPU pool of filler, inside the host cap)
        for i in range(nrep):
            h = await build(c, size, i, "P1_host_target", part="P1", rep=i)
            await filler(c, int(1.25 * GPU_POOL), protect_every=True)
            r = await recall(c, h, "host", "refs", part="P1", size=size, rep=i)
            if r["secondary_read_bytes"]:
                X.log(f"!!! P1 host rep {i}: secondary read {r['secondary_read_bytes']} (expected 0)")
            await asyncio.sleep(1.0)
            prune()
            guard("P1 host")
        X.log(f"P1 {size} host done")
        # disk-only: batches of targets, pushed out of GPU and host together
        per_batch = 20 if size == "11k" else 10
        done = 0
        while done < nrep:
            k = min(per_batch, nrep - done)
            hs = [await build(c, size, done + j, "P1_disk_target", part="P1", rep=done + j) for j in range(k)]
            await asyncio.sleep(5.0)
            ST["protected"] = kv_files()
            guard("P1 disk targets")
            await filler(c, int(1.4 * (CAP_GIB * TOK_PER_GIB + GPU_POOL)))
            await asyncio.sleep(2.0)
            prune()
            res = residency(ST["protected"])
            X.log(f"P1 {size} disk batch: {k} targets, target files resident bytes {res}, {disk_state()}")
            if res:
                raise SystemExit(f"F3: {res} target KV bytes in the page cache: STOP AND ASK")
            for j, h in enumerate(hs):
                r = await recall(c, h, "disk", "refs", part="P1", size=size, rep=done + j, page_cache_resident=res)
                if not r["secondary_read_bytes"]:
                    X.log(f"!!! P1 disk rep {done + j}: no secondary read (target not loaded from disk)")
            ST["protected"] = set()
            await asyncio.sleep(1.0)
            prune()
            done += k
        X.log(f"P1 {size} disk done")


# ------------------------------------------------------------------------------------------------ Part 2 (imposed delay)
SPLIT = OUT / "eng1f_holdout_split.json"
P2_LOADS, P2_STATES = ("P25", "P40"), ("cold", "host", "disk")
P2_NTR, P2_NHOLD, P2_NREP = 20, 5, 3
SEED_OFF = 1300000
LOAD_I = {"P25": 0, "P40": 1, "S2": 2, "S4": 3}


def make_split():
    cells = [(l, s) for l in P2_LOADS for s in P2_STATES]
    rng = random.Random(20261124)
    hold = {f"{l}|{s}": sorted(rng.sample(range(P2_NTR), P2_NHOLD)) for l, s in cells}
    rng2 = random.Random(20261125)
    order = {f"{l}|{s}": ["with_first" if rng2.random() < 0.5 else "without_first" for _ in range(P2_NTR)] for l, s in cells}
    rep = {k: [t for t in range(P2_NTR) if t not in v][:P2_NREP] for k, v in hold.items()}
    return dict(study="StudyENG1f-disk Part 2", reserved_for="later T0 extension; recorded, NOT analysed",
                rule="random.Random(20261124).sample(range(20), 5) per (load, state) in the order loads (P25, P40) x "
                     "states (cold, host, disk)", holdout=hold,
                order_rule="random.Random(20261125): one draw per (cell, trial); < 0.5 -> with first", order=order,
                noise_repeat=rep, seeds=f"ENG1 Part C trace / injection / clip seeds + {SEED_OFF}")


def ensure_split():
    sp = make_split()
    if SPLIT.exists():
        old = json.loads(SPLIT.read_text())
        if old["holdout"] != sp["holdout"] or old["order"] != sp["order"]:
            raise SystemExit("HOLDOUT split differs from the seeded rule: STOP")
        return old
    sp["written"] = F.now()
    SPLIT.write_text(json.dumps(sp, indent=1))
    X.log(f"HOLDOUT split written: {SPLIT}")
    return sp


def arrivals(load, trial):
    if load in ("P25", "P40"):
        frac = 0.40 if load == "P40" else 0.25
        rate = frac * M.PEAK1
        rng = np.random.default_rng(M.SEED_IDX[frac] + 100 * trial + SEED_OFF)
        t = np.cumsum(rng.exponential(1.0 / rate, size=int(rate * M.TRACE_S * 3) + 10))
        return [(float(x), None) for x in t[t < M.TRACE_S]]
    raise ValueError(load)


def trial_plan(load, state, trial):
    arr = arrivals(load, trial)
    si = P2_STATES.index(state)
    tinj = M.TINJ0 + float(np.random.default_rng(70000 + 1000 * LOAD_I[load] + 100 * si + trial + SEED_OFF).uniform())
    pool = M.ep_pool()
    clips = np.random.default_rng(80000 + 1000 * LOAD_I[load] + 100 * si + trial + SEED_OFF).choice(
        len(pool), size=len(arr), replace=False)
    return dict(arr=arr, tinj=round(tinj, 4), clips=[pool[int(i)] for i in clips])


async def p2_run(c, load, state, trial, arm, pair, hold, target=None):
    pl = trial_plan(load, state, trial)
    ns = nns("D")
    base = dict(part="P2", load=load, state=state, trial=trial, arm=arm, pair=pair, holdout=hold, run_ns=ns,
                t_inj_rel=pl["tinj"], server=ST["label"])
    t_setup = time.time()
    if state == "host":                                   # identical setup in every arm
        p = sess("11k", trial)
        h = await build(c, "11k", trial, "P2_host_target", **base)
        await filler(c, int(1.25 * GPU_POOL))
    elif state == "cold":
        p = sess("11k", trial)
        h = M.Hist(p["frames"], nns("C"))
        h.question = p["question"]
    else:
        h = target
    t_setup_end = time.time()
    await asyncio.sleep(M.RUN_GAP)
    bodies = [(M.ep_body(r, ns, f"{ns}-bg{i}"), f"{ns}-bg{i}", r) for i, r in enumerate(pl["clips"])]
    m0 = await M.metrics(c)
    t0 = time.time() + 0.3
    tasks = [M.post_at(c, t0 + a, b, rid, "episodic", idx=i, arrival_rel=round(a, 4), clip=r["request_id"])
             for i, ((a, s), (b, rid, r)) in enumerate(zip(pl["arr"], bodies))]
    if arm == "with":
        rid = f"{ns}-inj"
        tasks.append(M.post_at(c, t0 + pl["tinj"], recall_body(h, rid, "bytes" if state == "cold" else "refs"), rid,
                               "inject"))
    res = await asyncio.gather(*tasks)
    m1 = await M.metrics(c)
    d = M.mdelta(m0, m1)
    rows = [dict(r, **base, t0_trace=round(t0, 6)) for r in res]
    rows.append(dict(kind="run_summary", **base, t0_trace=round(t0, 6), t_setup=round(t_setup, 6),
                     setup_s=round(t_setup_end - t_setup, 4), t_end=round(time.time(), 6), metrics_delta=d,
                     secondary_read_bytes=sum(v for k, v in d.items() if "offload" in k and "read" in k and "bytes" in k),
                     n_bg=len(pl["arr"])))
    write(rows)
    await asyncio.sleep(1.0)
    prune()
    guard("P2 run")
    return rows


def imposed(a, b, key):
    ta = {r["idx"]: r[key] for r in a if r.get("kind") == "episodic" and r.get(key) is not None and not r.get("error")}
    tb = {r["idx"]: r[key] for r in b if r.get("kind") == "episodic" and r.get(key) is not None and not r.get("error")}
    return round(sum(ta[i] - tb[i] for i in ta if i in tb), 4)


async def part2_load(c, load, split):
    for state in P2_STATES:
        key = f"{load}|{state}"
        trials = list(range(P2_NTR))
        random.Random(41000 + LOAD_I[load] + 10 * P2_STATES.index(state)).shuffle(trials)
        targets, tfiles = {}, {}
        if state == "disk":
            prune(set())
            for t in trials:
                before = kv_files()
                targets[t] = await build(c, "11k", t, "P2_disk_target", part="P2", load=load, trial=t)
                await asyncio.sleep(1.5)
                tfiles[t] = kv_files() - before
            await asyncio.sleep(5.0)                       # let the last targets' write-through land
            ST["protected"] = kv_files()                   # only targets were written since prune(set())
            guard("P2 disk targets")
            await filler(c, int(1.4 * (CAP_GIB * TOK_PER_GIB + GPU_POOL)))
            await asyncio.sleep(2.0)
            prune()
            X.log(f"P2 {key}: {len(targets)} disk targets ready, {len(ST['protected'])} files, resident bytes "
                  f"{residency(ST['protected'])}, {disk_state()}")
        for t in trials:
            hold = t in split["holdout"][key]
            order = ["with", "without"] if split["order"][key][t] == "with_first" else ["without", "with"]
            pair = nns("pair")
            runs = {}
            res_b = residency(tfiles[t]) if state == "disk" else None
            if res_b:
                raise SystemExit(f"F3: target {t} KV bytes resident in the page cache ({res_b}): STOP AND ASK")
            for arm in order:
                runs[arm] = await p2_run(c, load, state, t, arm, pair, hold, targets.get(t))
            bad, n, _ = M.pair_check(runs["with"], runs["without"])
            rep = None
            if t in split["noise_repeat"][key]:
                rep = await p2_run(c, load, state, t, "repeat", pair, hold, targets.get(t))
            inj = next((r for r in runs["with"] if r.get("kind") == "inject"), {})
            summ = next(r for r in runs["with"] if r.get("kind") == "run_summary")
            write([dict(kind="pair_check", part="P2", load=load, state=state, trial=t, pair=pair, holdout=hold,
                        mismatches=bad, n=n, target_page_cache_bytes=res_b)])
            X.log(f"P2 {key} t{t}{' H' if hold else ''}: mism {bad}/{n}; inject ttft {inj.get('ttft_s')} cached "
                  f"{inj.get('cached_tokens')}/{inj.get('prompt_tokens')} secondary read {summ['secondary_read_bytes']:.3g}"
                  f"{'' if hold else '; imposed lat %.2f s' % imposed(runs['with'], runs['without'], 'latency_s')}"
                  f"{' + repeat' if rep else ''}")
            if bad:
                raise SystemExit(f"P2 {key} t{t}: {bad} cached-token mismatches: STOP AND ASK")
            if inj.get("error"):
                raise SystemExit(f"P2 {key} t{t}: recall error {inj.get('error')}: STOP")
            M.check_void()
        ST["protected"] = set()
        prune()


# ------------------------------------------------------------------------------------------------ Part 3 (concurrency)
P3_K, P3_REPS = (1, 2, 4), 10


async def part3(c, loaded=False):
    """k simultaneous disk loads of different histories; unloaded, or under P25 with paired without-runs."""
    jobs = [(k, r) for k in P3_K for r in range(P3_REPS)]
    need = sum(k for k, _ in jobs)
    used, i = 0, 0
    while used < need:
        prune(set())
        batch = min(20, need - used)
        hs = [await build(c, "11k", (i + j) % 20, "P3_target", part="P3") for j in range(batch)]
        i += batch
        await asyncio.sleep(5.0)
        ST["protected"] = kv_files()
        await filler(c, int(1.4 * (CAP_GIB * TOK_PER_GIB + GPU_POOL)))
        await asyncio.sleep(2.0)
        prune()
        res = residency(ST["protected"])
        if res:
            raise SystemExit(f"F3: {res} target bytes resident: STOP AND ASK")
        pool = list(hs)
        while pool and jobs:
            k, rep = jobs[0]
            if len(pool) < k:
                break
            jobs.pop(0)
            grp, pool = pool[:k], pool[k:]
            used += k
            if not loaded:
                m0 = await M.metrics(c)
                rs = await asyncio.gather(*(recall(c, h, "disk", "refs", part="P3", k=k, rep=rep, loaded=False)
                                            for h in grp))
                X.log(f"P3 unloaded k={k} rep {rep}: ttft {[r['ttft_s'] for r in rs]}")
            else:
                pl = trial_plan("P25", "disk", 100 + rep)
                rr = {}
                for arm in ("with", "without"):
                    ns = nns("D3")
                    bodies = [(M.ep_body(r, ns, f"{ns}-bg{q}"), f"{ns}-bg{q}", r) for q, r in enumerate(pl["clips"])]
                    t0 = time.time() + 0.3
                    tasks = [M.post_at(c, t0 + a, b, rid, "episodic", idx=q, arrival_rel=round(a, 4))
                             for q, ((a, s), (b, rid, r)) in enumerate(zip(pl["arr"], bodies))]
                    if arm == "with":
                        tasks += [M.post_at(c, t0 + pl["tinj"], recall_body(h, f"{ns}-inj{j}", "refs"), f"{ns}-inj{j}",
                                            "inject", j=j) for j, h in enumerate(grp)]
                    res_ = await asyncio.gather(*tasks)
                    rr[arm] = [dict(r, part="P3", loaded=True, k=k, rep=rep, arm=arm, run_ns=ns) for r in res_]
                    write(rr[arm])
                    await asyncio.sleep(1.0)
                    prune()
                X.log(f"P3 P25 k={k} rep {rep}: imposed lat {imposed(rr['with'], rr['without'], 'latency_s'):.2f} s; "
                      f"inject ttft {[r['ttft_s'] for r in rr['with'] if r['kind'] == 'inject']}")
            guard("P3")
        ST["protected"] = set()
        prune()


# ------------------------------------------------------------------------------------------------ Part 4 (write cost)
P4_WARM, P4_N = 5, 10


async def part4_server(c, cond, inst):
    for w in range(P4_WARM):
        await p4_trace(c, "P40", 900 + w, cond, inst, warm=True)
    for t in range(P4_N):
        for load in ("P40", "P25"):
            await p4_trace(c, load, 800 + t, cond, inst, warm=False)
        M.check_void()
    X.log(f"[{ST['label']}] P4 {cond}{inst} done")


async def p4_trace(c, load, trial, cond, inst, warm):
    pl = trial_plan(load, "cold", trial)
    ns = nns("W")
    bodies = [(M.ep_body(r, ns, f"{ns}-bg{q}"), f"{ns}-bg{q}", r) for q, r in enumerate(pl["clips"])]
    t0 = time.time() + 0.3
    res = await asyncio.gather(*(M.post_at(c, t0 + a, b, rid, "episodic", idx=q, arrival_rel=round(a, 4))
                                 for q, ((a, s), (b, rid, r)) in enumerate(zip(pl["arr"], bodies))))
    base = dict(part="P4", load=load, trial=trial, cond=cond, inst=inst, warm=warm, run_ns=ns, server=ST["label"])
    write([dict(r, **base, t0_trace=round(t0, 6)) for r in res] +
          [dict(kind="run_summary", **base, t0_trace=round(t0, 6), t_end=round(time.time(), 6))])
    await asyncio.sleep(1.0)
    if cond == "ON":
        prune(set())
        guard("P4")


# ------------------------------------------------------------------------------------------------ main
def stage(label, fns, disk=True):
    srv = start_server(label, disk)
    try:
        for fn, a in fns:
            asyncio.run(M.with_client(fn, *a))
    finally:
        stop_server(srv)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("part", choices=("equiv_p1", "p2_P25", "p2_P40", "p3_unloaded", "p3_P25", "p4"))
    a = ap.parse_args()
    set_paths(a.part)
    start = E.snapshot("start")
    if start["ours_outside_job"] or start["foreign_on_gpu"]:
        raise SystemExit(f"not exclusive at start: {start['foreign_on_gpu']}: STOP")
    import vllm
    import torch
    m = X.meta_load()
    m["stack"] = dict(vllm=vllm.__version__, torch=torch.__version__, gpu="h100nvl GPU 2", kvroot=str(KVROOT),
                      disk_tier=json.loads(disk_tier_config()), caps=dict(kv_dir_gb=KV_DIR_CAP_GB, free_floor_gb=FREE_FLOOR_GB))
    X.meta_save(m)
    threading.Thread(target=exclusivity_monitor, daemon=True).start()
    threading.Thread(target=DD.machine_monitor, daemon=True).start()
    try:
        M.load_sessions(warm=False)
        KVROOT.mkdir(parents=True, exist_ok=True)
        guard("start")
        if a.part == "equiv_p1":
            stage("EQ_P1", [(mech_and_equiv, ()), (part1, ())])
        elif a.part.startswith("p2_"):
            load = a.part[3:]
            split = ensure_split()
            stage(f"P2_{load}", [(part2_load, (load, split))])
        elif a.part == "p3_unloaded":
            stage("P3_U", [(part3, (False,))])
        elif a.part == "p3_P25":
            stage("P3_P25", [(part3, (True,))])
        elif a.part == "p4":
            for label, cond, inst in (("P4_OFF1", "OFF", 1), ("P4_ON1", "ON", 1), ("P4_ON2", "ON", 2),
                                      ("P4_OFF2", "OFF", 2)):
                stage(label, [(part4_server, (cond, inst))], disk=(cond == "ON"))
    finally:
        E.STOP_MON.set()
        DD.MSTOP.set()
        E.snapshot("end")
        m = X.meta_load()
        m["void"] = E.VOID.is_set()
        m["ended"] = F.now()
        X.meta_save(m)
    X.log(f"ENG1f {a.part} finished")


if __name__ == "__main__":
    main()
