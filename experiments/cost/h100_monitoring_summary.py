#!/usr/bin/env python3
"""H100 monitoring summary for the latency/accuracy studies run on GPU 3 (R1, R5, RH2, RH3; RH4–RH8, R9 added; StudyClean on GPU 1). CPU only, any venv.

Source: the gitignored logs/ written by the chains (not committed). Per run:
  windows   START/END pairs of the run's steps in logs/queueN_chain.log
  GPU 3     logs/queueN_gpu3_monitor.csv (10-s nvidia-smi samples: util, memory, power, SM clock, memory clock, temp)
  foreign   logs/queueN_gpu_procs.csv rows on GPU 3 (UUID b3c6399e) whose pid is not one of the run's own vLLM
            processes (every `pid=NNN` in the vLLM server logs started inside the run's windows), plus any watchdog
            'FOREIGN PROCESS' line in the chain log
  files     every log used, with size and sha256
Writes results/cost/h100_monitoring_summary.json. A run whose monitor/procs logs are missing is reported as such.
"""
import csv
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from _provenance import stamp  # noqa: E402

LOGS = Path("logs")
OUT = Path("results/cost/h100_monitoring_summary.json")
GPU3 = "GPU-b3c6399e"
RUNS = {"StudyR1": ("queue4", r"^r1_"), "StudyR5": ("queue4", r"^r5_"), "StudyRH2": ("queue5", r"^rh2$"),
        "StudyRH3": ("queue6", r"^rh3_(part0|cells)$"), "StudyRH4": ("queue7", r"^rh4_(part0|cells)$"),
        "StudyRH5": ("queue8", r"^rh5_(partA|fleet)_(host|gpu)$"),
        "StudyRH6": ("queue9", r"^rh6_(smoke|partA|partB|partC)$"),
        "StudyRH7": ("queue10", r"^rh7_(step0|smoke|fleet)$"),
        "StudyRH8": ("queue11", r"^rh8_(smoke|fleet)$"), "StudyR9": ("queue11", r"^r9$")}
F = "%Y-%m-%d %H:%M:%S"


def sha(p):
    return dict(file=str(p), bytes=p.stat().st_size, sha256=hashlib.sha256(p.read_bytes()).hexdigest())


def windows(chain, pat):
    out, open_ = [], {}
    for line in chain.read_text(errors="replace").splitlines():
        m = re.match(r"=== QUEUE\d+ (\S+ \S+) (START|END) (\S+)(?: rc=(\d+))?", line)
        if not m or not re.match(pat, m.group(3)):
            continue
        t = datetime.strptime(m.group(1), F)
        if m.group(2) == "START":
            open_[m.group(3)] = t
        elif m.group(3) in open_:
            out.append(dict(step=m.group(3), start=open_.pop(m.group(3)), end=t, rc=int(m.group(4) or -1)))
    for s, t in open_.items():          # started, never ended (killed / restarted)
        nxt = [w["start"] for w in out if w["start"] > t]
        out.append(dict(step=s, start=t, end=min(nxt) if nxt else None, rc=None, note="no END line (killed)"))
    return sorted(out, key=lambda w: w["start"])


def inside(t, ws):
    return any(w["start"] <= t <= (w["end"] or t) for w in ws)


def stats(x):
    x = np.array(x, float)
    return None if not len(x) else dict(min=float(x.min()), median=float(np.median(x)), max=float(x.max()), n=len(x))


def num(s):
    return float(re.sub(r"[^\d.]", "", s) or "nan")


def summarise(name, q, pat):
    chain = LOGS / f"{q}_chain.log"
    res = dict(run=name, chain_log=str(chain))
    if not chain.exists():
        return dict(res, missing="chain log missing; no windows recoverable")
    ws = windows(chain, pat)
    res["windows"] = [dict(step=w["step"], start=w["start"].strftime(F), end=w["end"] and w["end"].strftime(F),
                           rc=w["rc"], **({"note": w["note"]} if "note" in w else {})) for w in ws]
    files = [chain] + sorted(p for w in ws for p in [LOGS / f"{q}_{w['step']}.log"] if p.exists())
    files = list(dict.fromkeys(files))
    # vLLM server logs started inside the windows -> own pids
    own, srv = set(), []
    for p in sorted(LOGS.glob("study_x_server_*.log")):
        m = re.search(r"_(\d{4})_(\d{6})\.log$", p.name)
        t = datetime.strptime(f"2026{m.group(1)}{m.group(2)}", "%Y%m%d%H%M%S")
        if inside(t, ws):
            srv.append(p)
            own |= {int(x) for x in re.findall(r"pid=(\d+)", p.read_text(errors="replace"))}
    res["server_logs"] = [p.name for p in srv]
    res["own_vllm_pids"] = sorted(own)
    files += srv
    mon, procs = LOGS / f"{q}_gpu3_monitor.csv", LOGS / f"{q}_gpu_procs.csv"
    if mon.exists():
        rows = [r for r in csv.reader(open(mon)) if len(r) >= 7]
        rows = [(datetime.strptime(r[0].strip(), F), [num(v) for v in r[1:7]]) for r in rows]
        rows = [v for t, v in rows if inside(t, ws)]
        busy = [v for v in rows if v[0] > 0]
        res["gpu3_monitor"] = dict(
            samples=len(rows), interval_s=10, util_pct=stats([v[0] for v in rows]),
            util_pct_busy_only=stats([v[0] for v in busy]), memory_used_mib=stats([v[1] for v in rows]),
            power_w=stats([v[2] for v in rows]), sm_clock_mhz=stats([v[3] for v in rows]),
            sm_clock_mhz_busy_only=stats([v[3] for v in busy]), mem_clock_mhz=stats([v[4] for v in rows]),
            temp_c=stats([v[5] for v in rows]))
        files.append(mon)
    else:
        res["gpu3_monitor"] = f"MISSING: {mon} was not written for this run (chain launched no monitor)"
    if procs.exists():
        seen, foreign = 0, {}
        for r in csv.reader(open(procs)):
            if len(r) < 3 or GPU3 not in r[1]:
                continue
            t = datetime.strptime(r[0].strip(), F)
            if not inside(t, ws):
                continue
            seen += 1
            pid = int(r[2])
            if pid not in own:
                foreign.setdefault(pid, []).append(t.strftime(F))
        res["foreign_processes"] = dict(gpu3_process_samples=seen, count=len(foreign),
                                        pids={str(k): dict(first=v[0], last=v[-1], samples=len(v))
                                              for k, v in foreign.items()})
        files.append(procs)
    else:
        res["foreign_processes"] = f"MISSING: {procs} was not written for this run"
    res["watchdog_foreign_lines"] = [ln for ln in chain.read_text(errors="replace").splitlines()
                                     if "FOREIGN" in ln and inside(datetime.strptime(
                                         re.search(r"(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)", ln).group(1), F), ws)]
    res["files"] = [sha(p) for p in files]
    return res


GPU1 = "GPU-235c6d2d"


def summarise_clean():
    """StudyClean (GPU 1; GPU 3 was held by another user): logs/clean_chain.log '=== CLEAN <ts> START|END <cmd>' windows,
    logs/clean_gpus.csv (1-s samples, all GPUs: ts, index, util, mem, power, SM, temp), logs/clean_gpu_procs.csv
    (10-s), and the watchdog's FOREIGN lines (the 12:50:04 kill during the pass-1/pass-2 gap is expected here)."""
    chain = LOGS / "clean_chain.log"
    res = dict(run="StudyClean", gpu="h100nvl GPU 1 (UUID GPU-235c6d2d…)", chain_log=str(chain))
    if not chain.exists():
        return dict(res, missing="chain log missing")
    ws, open_ = [], None
    for line in chain.read_text(errors="replace").splitlines():
        m = re.match(r"=== CLEAN (\S+ \S+) (START|END)(?: rc=(\d+))? (.*)", line)
        if not m:
            continue
        t = datetime.strptime(m.group(1)[:19], F)
        step = re.sub(r"^\S*python3? ", "", m.group(4)).strip()
        if m.group(2) == "START":
            open_ = (step, t)
        elif open_:
            ws.append(dict(step=step, start=open_[1], end=t, rc=int(m.group(3))))
            open_ = None
    res["windows"] = [dict(step=w["step"], start=w["start"].strftime(F), end=w["end"].strftime(F), rc=w["rc"]) for w in ws]
    files = [chain]
    own, srv = set(), []
    for p in sorted(LOGS.glob("study_x_server_*.log")):
        m = re.search(r"_(\d{4})_(\d{6})\.log$", p.name)
        t = datetime.strptime(f"2026{m.group(1)}{m.group(2)}", "%Y%m%d%H%M%S")
        if inside(t, ws):
            srv.append(p)
            own |= {int(x) for x in re.findall(r"pid=(\d+)", p.read_text(errors="replace"))}
    res["server_logs"] = [p.name for p in srv]
    files += srv
    mon = LOGS / "clean_gpus.csv"
    if mon.exists():
        per = {}
        for r in csv.reader(open(mon)):
            if len(r) < 7:
                continue
            t = datetime.strptime(r[0].strip(), F)
            if inside(t, ws):
                per.setdefault(r[1].strip(), []).append([num(v) for v in r[2:7]])
        g1 = per.get("1", [])
        busy = [v for v in g1 if v[0] > 0]
        res["gpu1_monitor"] = dict(samples=len(g1), interval_s=1, util_pct=stats([v[0] for v in g1]),
                                   memory_used_mib=stats([v[1] for v in g1]), power_w=stats([v[2] for v in g1]),
                                   sm_clock_mhz_busy_only=stats([v[3] for v in busy]),
                                   power_w_busy_only=stats([v[2] for v in busy]), temp_c=stats([v[4] for v in g1]))
        res["neighbour_gpus_util_pct"] = {f"GPU {k}": stats([v[0] for v in vs]) for k, vs in per.items() if k != "1"}
        files.append(mon)
    procs = LOGS / "clean_gpu_procs.csv"
    if procs.exists():
        seen, foreign = 0, {}
        for r in csv.reader(open(procs)):
            if len(r) < 3 or GPU1 not in r[1]:
                continue
            t = datetime.strptime(r[0].strip(), F)
            if not inside(t, ws):
                continue
            seen += 1
            if int(r[2]) not in own:
                foreign.setdefault(int(r[2]), []).append(t.strftime(F))
        res["foreign_processes_in_windows"] = dict(gpu1_process_samples=seen, count=len(foreign),
                                                   pids={str(k): dict(first=v[0], last=v[-1], samples=len(v))
                                                         for k, v in foreign.items()})
        files.append(procs)
    res["watchdog_foreign_lines"] = [ln for ln in chain.read_text(errors="replace").splitlines() if "FOREIGN" in ln]
    res["note"] = ("Own-pid detection reads vLLM server logs only, so H4's HF process (pid 3095566, 9.0-9.6 GiB = the 4B "
                   "model, 12:24:40-12:25:39 inside the H4 window; the session watchdog did not fire) is listed as "
                   "'foreign in windows' but was ours. Watchdog lines: 12:50:04 liying during the pass-1/pass-2 gap "
                   "(chain killed, nothing of ours on the GPU); 13:39:16 liying after the chain completed (13:32:20).")
    res["files"] = [sha(p) for p in files + [p for p in (LOGS / "clean_dmon.log", LOGS / "clean_loadavg.log") if p.exists()]]
    return res


def main():
    out = dict(note="Summary of gitignored logs/ on h100nvl; GPU 3 = UUID b3c6399e. Clocks/util are 10-s samples "
                    "inside the run's chain-step windows. 'Foreign' = a GPU-3 compute process not started by the "
                    "run's own vLLM servers.",
               runs={n: summarise(n, q, p) for n, (q, p) in RUNS.items()})
    out["runs"]["StudyClean"] = summarise_clean()
    out["_provenance"] = stamp(script="h100_monitoring_summary.py", model="n/a", device="h100nvl",
                               n=len(out["runs"]))
    OUT.write_text(json.dumps(out, indent=1))
    for n, r in out["runs"].items():
        if n == "StudyClean":
            m, fp = r.get("gpu1_monitor"), r.get("foreign_processes_in_windows")
            print(n, len(r.get("windows", [])), "windows; GPU 1:", m and f"{m['samples']} samples, SM busy "
                  f"{m['sm_clock_mhz_busy_only']}", "| foreign in windows:", fp and fp["count"], "| watchdog lines",
                  len(r["watchdog_foreign_lines"]), "| files", len(r.get("files", [])))
            continue
        m = r.get("gpu3_monitor")
        fp = r.get("foreign_processes")
        print(n, len(r.get("windows", [])), "windows;", "monitor:", m if isinstance(m, str) else
              f"{m['samples']} samples, SM busy {m['sm_clock_mhz_busy_only']}, util {m['util_pct']}",
              "| foreign:", fp if isinstance(fp, str) else fp["count"], "| watchdog lines",
              len(r.get("watchdog_foreign_lines", [])), "| files", len(r.get("files", [])))


if __name__ == "__main__":
    main()
