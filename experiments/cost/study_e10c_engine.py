#!/usr/bin/env python3
"""StudyE10c-engine — do vLLM engine settings remove the recall interference? EXCLUSIVE (vLLM venv; h100nvl GPU 2).
Pre-registered in research/EXPERIMENTS.md (StudyE10c-engine; grid trimmed by the user 2026-11-11).

Harness: StudyE10b's study_e10b_mixed.py, imported and used UNCHANGED (Episodic, k1_body, run_cell, parity, monitor,
snapshot, D7 open loop, RH7 EAGER-DELTA warm sessions, R1 K1 cold recall, 30-s discard, 240-s window, 300-s drain
cap, exclusivity monitor ignoring <defunct>, VOID on overlap). Only these change:
  engine flags   E0 = E10b's server (vLLM 0.31.0 defaults: chunked prefill on, max_num_batched_tokens 8192, fcfs)
                 E1 = + --scheduling-policy priority      E2 = + --max-num-batched-tokens 2048      E4 = E1 + E2
                 (E3 = 512 dropped by the user's trim)
  priority       under E1 / E4 every request body carries vLLM's `priority` (lower = sooner): episodic 0, warm
                 warm-up / appends / escalations 1 (RH7 body7, incl. cache-miss fallbacks), cold recall 2. Under
                 E0 / E2 no priority field is sent (vLLM rejects non-zero priority under fcfs).
  conditions     C0 none (KV-GPU, k 0 r 0) | C1 cold only (KV-GPU, k 0 r 0.05) | C2 KV-HOST k 8 r 0 |
                 C3 KV-HOST k 16 r 0 | C4 KV-HOST k 8 r 0.1
  levels         N = 1: 10/20/25/30/40/50 % of 15.1 req/s; N = 3: 10/20/25/35/50 % of 5.38 req/s; bottom-up per
                 (engine, condition, N), stop at the first failing level. Fresh server for EVERY cell.
  seeds          Poisson seed = E10b's level index for 25 % (0) and 50 % (1), so those cells reproduce E10b's
                 arrival sequences; new levels use indices 4-8 (10 % 4, 20 % 5, 30 % 6, 40 % 7, 35 % 8). Cold seed
                 1000 + the same index (E10b's rule).
  token parity   E10b's parity gate (D14 N1/N3, K1 video, D2 append) on a fresh server of EACH engine config before
                 its first cell — this is also the check that the config serves all three request types.
Rows -> results/cost/study_e10/e10c_{requests,metrics,cpu,monitor}_h100nvl.jsonl, meta e10c_run_meta_h100nvl.json.
"""
import argparse
import asyncio
import gzip
import json
import random
import re
import sys
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import study_e10b_mixed as E  # noqa: E402

X, F, R7 = E.X, E.F, E.R7
OUT = E.OUT
E.REQ = OUT / "e10c_requests_h100nvl.jsonl"
E.MET = OUT / "e10c_metrics_h100nvl.jsonl"
E.CPU = OUT / "e10c_cpu_h100nvl.jsonl"
E.MON = OUT / "e10c_monitor_h100nvl.jsonl"
X.META_PATH = OUT / "e10c_run_meta_h100nvl.json"
X.CURRENT = E.REPO / "logs/e10c_current.json"

# level -> seed index: E10b's indices for 25 / 50 % (0, 1); 0.75 / 0.9 keep 2 / 3 (unused); new levels 4..8
E.FRACS = (0.25, 0.50, 0.75, 0.90, 0.10, 0.20, 0.30, 0.40, 0.35)
LEVELS = {1: (0.10, 0.20, 0.25, 0.30, 0.40, 0.50), 3: (0.10, 0.20, 0.25, 0.35, 0.50)}
ENGINE = {"E0": [], "E1": ["--scheduling-policy", "priority"], "E2": ["--max-num-batched-tokens", "2048"],
          "E4": ["--scheduling-policy", "priority", "--max-num-batched-tokens", "2048"]}
PRIO = {"E1", "E4"}
COND = {"C0": ("KVGPU", 0, 0.0), "C1": ("KVGPU", 0, 0.05), "C2": ("KVHOST", 8, 0.0), "C3": ("KVHOST", 16, 0.0),
        "C4": ("KVHOST", 8, 0.1)}
GRID = ([("E0", "C0", 1), ("E0", "C0", 3)] + [("E0", c, 1) for c in ("C1", "C2", "C3", "C4")] +
        [(e, c, n) for e in ("E1", "E2", "E4")
         for c, n in (("C0", 1), ("C0", 3), ("C1", 1), ("C1", 3), ("C2", 1), ("C3", 1), ("C4", 1))])
CUR = {"engine": "E0", "cond": "C0", "prio": False}


def tag(kv, k, r, n, frac):
    return f"E10C_{CUR['engine']}_{CUR['cond']}_N{n}_L{int(round(frac * 100))}"


E.tag = tag


def with_prio(data, p):
    """Insert vLLM's request priority into a pre-serialised JSON body (bytes starting with '{')."""
    if not CUR["prio"]:
        return data
    assert data[:1] == b"{"
    return b'{"priority": %d, ' % p + data[1:]


_take = E.Episodic.take
E.Episodic.take = lambda self, m: [(rid, with_prio(b, 0)) for rid, b in _take(self, m)]
_k1 = E.k1_body
E.k1_body = lambda q: (lambda bn: (with_prio(bn[0], 2), bn[1]))(_k1(q))
_body7 = R7.body7
R7.body7 = lambda *a, **kw: (lambda o: (with_prio(o[0], 1),) + tuple(o[1:]))(_body7(*a, **kw))


def start_server(eng, kv, label):
    F.require_idle()
    flags = E.KV[kv] + ENGINE[eng]
    srv = X.Server("32BI", flags)
    info = srv.start()
    txt = Path(srv.logpath).read_text(errors="replace")
    mnbt = re.findall(r"max_num_batched_tokens=(\d+)", txt)
    chunk = re.findall(r"enable_chunked_prefill=(\w+)", txt)
    pol = re.findall(r"scheduling_policy=['\"]?(\w+)", txt) or re.findall(r"policy=['\"]?(fcfs|priority)", txt)
    info.update(prefix_caching=True, kv_config=kv, kv_offloading_gib=256 if kv == "KVHOST" else 0,
                mm_processor_cache_gb=128, engine=eng, engine_flags=ENGINE[eng],
                log_max_num_batched_tokens=mnbt[-1] if mnbt else None, log_chunked_prefill=chunk[-1] if chunk else None,
                log_scheduling_policy=pol[-1] if pol else None, host_mem=E.R5.host_mem(srv.proc.pid))
    m = X.meta_load()
    m.setdefault("servers", []).append(dict(label=label, started=F.now(), flags=flags, **info))
    X.meta_save(m)
    X.log(f"[{label}] {eng} {kv}: KV {info.get('kv_cache_tokens')} tokens; max_num_batched_tokens "
          f"{info['log_max_num_batched_tokens']}, chunked prefill {info['log_chunked_prefill']}, policy "
          f"{info['log_scheduling_policy']}")
    E.snapshot(f"server_up_{label}")
    return srv


def set_cur(eng, cond):
    CUR.update(engine=eng, cond=cond, prio=eng in PRIO)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["parity", "run"], required=True)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    E.R1ROWS = {(r["question_id"], r["construction"]): r for r in map(json.loads, gzip.open(
        E.REPO / "results/sember/study_r1/study_r1_inputs_manifest.jsonl.gz", "rt"))}
    order = sorted({q for q, _ in E.R1ROWS})
    random.Random(0).shuffle(order)
    start = E.snapshot("start")
    if start["ours_outside_job"]:
        raise SystemExit(f"not exclusive at start: {start['ours_outside_job']} — STOP")
    import torch
    import vllm
    m = X.meta_load()
    m["stack"] = dict(venv=sys.prefix, vllm=vllm.__version__, torch=torch.__version__, gpu="h100nvl GPU 2",
                      gpu_uuid=F.GPU_UUID, kv_flags=E.KV, engine=ENGINE, priority_classes=dict(
                          episodic=0, warm=1, cold=2), peak=E.PEAK, levels=LEVELS, seed_index=list(E.FRACS),
                      budget=E.BUDGET, dur=E.DUR, discard=E.DISCARD, drain_cap=E.DRAIN_CAP)
    m["grid"] = GRID
    m["conditions"] = COND
    X.meta_save(m)
    th = threading.Thread(target=E.monitor, daemon=True)
    th.start()
    try:
        S = E.FL.sessions()
        E.R6.preencode("D2", S)
        engines = [e for e in ENGINE if any(g[0] == e for g in GRID)]
        for eng in engines:
            par = X.meta_load().get("parity", {})
            if not par.get(eng, {}).get("passed"):
                set_cur(eng, "PARITY")
                srv = start_server(eng, "KVGPU", f"{eng}_parity")
                try:
                    ok, recs = asyncio.run(E.parity({1: E.Episodic(1), 3: E.Episodic(3)}, srv.proc.pid))
                finally:
                    srv.stop()
                m = X.meta_load()
                m.setdefault("parity", {})[eng] = dict(passed=ok, rows=recs)
                X.meta_save(m)
                X.log(f"{eng} PARITY {'PASSED' if ok else 'FAILED'}: " + json.dumps(
                    [(r.get("kind"), r.get("prompt_tokens"), r.get("expected"), r.get("tokens_per_frame"), r["match"],
                      (r.get("error") or "")[:120]) for r in recs]))
                if not ok:
                    raise SystemExit(f"E10c {eng}: token-parity / feasibility gate FAILED — STOP")
            if E.VOID.is_set():
                raise SystemExit("run VOID — STOP")
        if a.stage == "parity":
            return
        for eng, cond, n in GRID:
            set_cur(eng, cond)
            kv, k, r = COND[cond]
            for f in LEVELS[n]:
                tg = tag(kv, k, r, n, f)
                if X.is_done(tg):
                    if X.meta_load()["experiments"][tg]["summary"]["meets_budget"]:
                        continue
                    break
                srv = start_server(eng, kv, tg)
                try:
                    s = asyncio.run(E.run_cell(kv, k, r, n, f, srv.proc.pid, E.Episodic(n), dict(order=order, i=0)))
                finally:
                    srv.stop()
                m = X.meta_load()
                m["experiments"][tg].update(engine=eng, cond=cond)
                X.meta_save(m)
                if E.VOID.is_set():
                    raise SystemExit("run VOID — STOP")
                if not s["meets_budget"]:
                    break
    finally:
        E.STOP_MON.set()
        E.snapshot("end")
        m = X.meta_load()
        m["void"] = E.VOID.is_set()
        X.meta_save(m)
    from _provenance import stamp
    m = X.meta_load()
    m.setdefault("_provenance", []).append(stamp(script="study_e10c_engine.py", model="qwen3vl-32b-instruct",
                                                 device="h100nvl_gpu2", args=a))
    X.meta_save(m)


if __name__ == "__main__":
    main()
