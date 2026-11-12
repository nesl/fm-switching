#!/usr/bin/env python3
"""StudyE10e-partial-prefill — does vLLM's long-prefill cap remove the cold-recall interference? EXCLUSIVE (vLLM venv;
h100nvl GPU 2). Pre-registered in research/EXPERIMENTS.md (StudyE10e-partial-prefill; design decisions by the user
2026-11-12: P1/P2 without the partial-prefill counters, which do not exist in vLLM 0.31.0; P1-P3 C0 at 25/40 % only).

Harness: study_e10b_mixed.py (run_cell, Episodic, monitor, D7 open loop, RH7 warm sessions, 30-s discard, 240-s
window, 300-s drain cap, VOID on overlap) and study_e10d_blocking.py (cold V1 / V3 bodies with request_id, the
millisecond vLLM logging config + --enable-log-requests, server-log phase times, write_cold_phases), both imported
UNCHANGED. Only the engine flags change:
  P0  E0 defaults (control: must reproduce E10c E0 C0 N1 25 % and E10c / E10d C1 N1 10 % within 2x, else STOP)
  P1  --long-prefill-token-threshold 1024
  P2  --long-prefill-token-threshold 512
  P3  P1 + --scheduling-policy priority (episodic 0, warm 1, cold 2, as E10c)
  Each server's 'non-default args' log line is checked for exactly these settings (else STOP).
Conditions: C0 (KV-GPU k 0 r 0), C1 (KV-GPU k 0 r 0.05), C4 (KV-HOST k 8 r 0.1). Episodic N = 1, budget 0.45 s, levels
10/20/25/30/40 % of 15.1 req/s, bottom-up, stop at first failure (P1-P3 C0: 25 % and 40 % only). Cold request V1 (PNG
video, = E10c / E10d); V3 (E10d's token-matched text) at C1 10 % and 25 % for every config. E10c seeds (level index map
FRACS, cold seed 1000 + index). Fresh server per cell. Stops before a new cell once 6 h have elapsed.
Rows -> results/cost/study_e10/e10e_{requests,metrics,cpu,monitor,cold_phases}_h100nvl.jsonl, meta
e10e_run_meta_h100nvl.json.
"""
import argparse
import asyncio
import gzip
import json
import random
import re
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import study_e10d_blocking as D  # noqa: E402  (sets the logging config env var and wraps E.k1_body / E.timed_post)

E, X, F, R7 = D.E, D.X, D.F, D.E.R7
OUT = E.OUT
E.REQ = OUT / "e10e_requests_h100nvl.jsonl"
E.MET = OUT / "e10e_metrics_h100nvl.jsonl"
E.CPU = OUT / "e10e_cpu_h100nvl.jsonl"
E.MON = OUT / "e10e_monitor_h100nvl.jsonl"
D.COLD = OUT / "e10e_cold_phases_h100nvl.jsonl"
X.META_PATH = OUT / "e10e_run_meta_h100nvl.json"
X.CURRENT = E.REPO / "logs/e10e_current.json"

E.FRACS = (0.25, 0.50, 0.75, 0.90, 0.10, 0.20, 0.30, 0.40, 0.35)     # E10c's level -> seed-index map
LADDER = (0.10, 0.20, 0.25, 0.30, 0.40)
CONFIG = {"P0": [], "P1": ["--long-prefill-token-threshold", "1024"], "P2": ["--long-prefill-token-threshold", "512"],
          "P3": ["--long-prefill-token-threshold", "1024", "--scheduling-policy", "priority"]}
EXPECT = {"P0": (0, "fcfs"), "P1": (1024, "fcfs"), "P2": (512, "fcfs"), "P3": (1024, "priority")}
PRIO = {"P3"}
COND = {"C0": ("KVGPU", 0, 0.0), "C1": ("KVGPU", 0, 0.05), "C4": ("KVHOST", 8, 0.1)}
CONTROL = {"E10E_P0_C0_V1_N1_L25": [("E10c E0 C0 N1 25 %", 0.2785350000000001)],
           "E10E_P0_C1_V1_N1_L10": [("E10c E0 C1 N1 10 %", 2.739087), ("E10d E0 V1 10 %", 2.974018)]}
MAX_H = 6.0
CUR = {"cfg": "P0", "cond": "C0", "prio": False}


def tag(kv, k, r, n, frac):
    return f"E10E_{CUR['cfg']}_{CUR['cond']}_{D.CUR['variant']}_N{n}_L{int(round(frac * 100))}"


E.tag = tag


def with_prio(data, p):
    """Insert vLLM's request priority into a pre-serialised JSON body (as E10c)."""
    if not CUR["prio"]:
        return data
    assert data[:1] == b"{"
    return b'{"priority": %d, ' % p + data[1:]


_take = E.Episodic.take
E.Episodic.take = lambda self, m: [(rid, with_prio(b, 0)) for rid, b in _take(self, m)]
_cold = E.k1_body                                   # = D.cold_body (request_id + variant)
E.k1_body = lambda q: (lambda bn: (with_prio(bn[0], 2), bn[1]))(_cold(q))
_body7 = R7.body7
R7.body7 = lambda *a, **kw: (lambda o: (with_prio(o[0], 1),) + tuple(o[1:]))(_body7(*a, **kw))


def start_server(cfg, kv, label):
    F.require_idle()
    flags = E.KV[kv] + CONFIG[cfg] + D.LOGFLAGS
    srv = X.Server("32BI", flags)
    info = srv.start()
    txt = Path(srv.logpath).read_text(errors="replace")
    nd = re.findall(r"non-default args: (.*)", txt)
    nd = nd[-1] if nd else ""
    thr = re.findall(r"'long_prefill_token_threshold': (\d+)", nd)
    pol = re.findall(r"'scheduling_policy': '(\w+)'", nd)
    got = (int(thr[-1]) if thr else 0, pol[-1] if pol else "fcfs")
    mnbt = re.findall(r"max_num_batched_tokens[=': ]+(\d+)", txt)
    chunk = re.findall(r"enable_chunked_prefill[=': ]+(\w+)", txt)
    info.update(prefix_caching=True, kv_config=kv, kv_offloading_gib=256 if kv == "KVHOST" else 0, config=cfg,
                config_flags=CONFIG[cfg], log_flags=D.LOGFLAGS, log_long_prefill_token_threshold=got[0],
                log_scheduling_policy=got[1], log_max_num_batched_tokens=mnbt[-1] if mnbt else None,
                log_chunked_prefill=chunk[-1] if chunk else None, flags_verified=got == EXPECT[cfg],
                host_mem=E.R5.host_mem(srv.proc.pid))
    m = X.meta_load()
    m.setdefault("servers", []).append(dict(label=label, started=F.now(), flags=flags, **info))
    X.meta_save(m)
    X.log(f"[{label}] {cfg} {kv}: threshold {got[0]}, policy {got[1]}, max_num_batched_tokens "
          f"{info['log_max_num_batched_tokens']}, chunked prefill {info['log_chunked_prefill']}, verified "
          f"{info['flags_verified']}")
    if got != EXPECT[cfg]:
        srv.stop()
        raise SystemExit(f"{label}: server log shows {got}, expected {EXPECT[cfg]} — STOP")
    E.snapshot(f"server_up_{label}")
    return srv


def plan():
    """[(cfg, cond, variant, levels, ladder?)] in run order."""
    out = []
    for cfg in CONFIG:
        out.append((cfg, "C0", "V1", LADDER if cfg == "P0" else (0.25, 0.40), cfg == "P0"))
        out.append((cfg, "C1", "V1", LADDER, True))
        out.append((cfg, "C4", "V1", LADDER, True))
        out.append((cfg, "C1", "V3", (0.10, 0.25), False))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="print the plan and exit")
    a = ap.parse_args()
    if a.dry:
        for p in plan():
            print(p)
        return
    OUT.mkdir(parents=True, exist_ok=True)
    E.R1ROWS = {(r["question_id"], r["construction"]): r for r in map(json.loads, gzip.open(
        E.REPO / "results/sember/study_r1/study_r1_inputs_manifest.jsonl.gz", "rt"))}
    order = sorted({q for q, _ in E.R1ROWS})
    random.Random(0).shuffle(order)
    D.load_v3()
    assert list(D.V3) == order[:len(D.V3)], "E10d V3 prompts are not E10c's cold order"
    start = E.snapshot("start")
    if start["ours_outside_job"]:
        raise SystemExit(f"not exclusive at start: {start['ours_outside_job']} — STOP")
    import torch
    import vllm
    m = X.meta_load()
    t_start = m.setdefault("t_start", time.time())
    m["stack"] = dict(venv=sys.prefix, vllm=vllm.__version__, torch=torch.__version__, gpu="h100nvl GPU 2",
                      gpu_uuid=F.GPU_UUID, kv_flags=E.KV, config=CONFIG, expect=EXPECT, log_flags=D.LOGFLAGS,
                      priority_classes=dict(episodic=0, warm=1, cold=2), peak=E.PEAK, ladder=LADDER,
                      seed_index=list(E.FRACS), budget=E.BUDGET, dur=E.DUR, discard=E.DISCARD,
                      drain_cap=E.DRAIN_CAP, unsupported_flags=["--max-num-partial-prefills",
                                                                "--max-long-partial-prefills"])
    m["plan"] = plan()
    m["conditions"] = COND
    X.meta_save(m)
    th = threading.Thread(target=E.monitor, daemon=True)
    th.start()
    try:
        S = E.FL.sessions()
        E.R6.preencode("D2", S)
        for cfg, cond, var, levels, ladder in plan():
            CUR.update(cfg=cfg, cond=cond, prio=cfg in PRIO)
            D.CUR.update(engine=cfg, variant=var)
            kv, k, r = COND[cond]
            for f in levels:
                tg = tag(kv, k, r, 1, f)
                if X.is_done(tg):
                    if ladder and not X.meta_load()["experiments"][tg]["summary"]["meets_budget"]:
                        break
                    continue
                el = (time.time() - t_start) / 3600
                if el > MAX_H:
                    raise SystemExit(f"{el:.2f} h elapsed > {MAX_H} h before {tg} — STOP and ask")
                srv = start_server(cfg, kv, tg)
                try:
                    s = asyncio.run(E.run_cell(kv, k, r, 1, f, srv.proc.pid, E.Episodic(1), dict(order=order, i=0)))
                    ph = D.write_cold_phases(tg, srv, cfg, var)
                finally:
                    srv.stop()
                m = X.meta_load()
                m["experiments"][tg].update(config=cfg, cond=cond, variant=var, cold_n=len(ph),
                                            cold_logged=sum(bool(p["t_added_abs"]) for p in ph))
                X.meta_save(m)
                X.log(f"{tg}: cold logged {sum(bool(p['t_added_abs']) for p in ph)}/{len(ph)}")
                if E.VOID.is_set():
                    raise SystemExit("run VOID — STOP")
                bad = [p for p in ph if p["prompt_tokens"] is None or abs(
                    p["prompt_tokens"] - p["expected_prompt_tokens"]) > 0.01 * p["expected_prompt_tokens"]]
                if bad:
                    raise SystemExit(f"{tg}: cold prompt tokens off by > 1 % ({len(bad)}) — STOP")
                for name, ref in CONTROL.get(tg, []):
                    ratio = s["episodic_p99"] / ref
                    X.log(f"CONTROL {tg}: p99 {s['episodic_p99']:.3f} vs {name} {ref:.3f} (ratio {ratio:.2f})")
                    m = X.meta_load()
                    m.setdefault("control", {}).setdefault(tg, []).append(dict(
                        p99=s["episodic_p99"], ref=ref, ref_name=name, ratio=ratio, within_2x=0.5 <= ratio <= 2.0))
                    X.meta_save(m)
                    if not 0.5 <= ratio <= 2.0:
                        raise SystemExit(f"P0 does not reproduce {name} within 2x — STOP")
                if ladder and not s["meets_budget"]:
                    break
    finally:
        E.STOP_MON.set()
        E.snapshot("end")
        m = X.meta_load()
        m["void"] = E.VOID.is_set()
        X.meta_save(m)
    from _provenance import stamp
    m = X.meta_load()
    m.setdefault("_provenance", []).append(stamp(script="study_e10e_partial_prefill.py",
                                                 model="qwen3vl-32b-instruct", device="h100nvl_gpu2", args=a))
    X.meta_save(m)


if __name__ == "__main__":
    main()
