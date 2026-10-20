#!/usr/bin/env python3
"""H100 monitoring summary for the latency/accuracy studies run on GPU 3 (R1, R5, RH2, RH3; RH4 and RH5 added). CPU only, any venv.

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
        "StudyRH5": ("queue8", r"^rh5_(partA|fleet)_(host|gpu)$")}
F = "%Y-%m-%d %H:%M:%S"


def sha(p):
    return dict(file=str(p), bytes=p.stat().st_size, sha256=hashlib.sha256(p.read_bytes()).hexdigest())


def windows(chain, pat):
    out, open_ = [], {}
    for line in chain.read_text(errors="replace").splitlines():
        m = re.match(r"=== QUEUE\d (\S+ \S+) (START|END) (\S+)(?: rc=(\d+))?", line)
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


def main():
    out = dict(note="Summary of gitignored logs/ on h100nvl; GPU 3 = UUID b3c6399e. Clocks/util are 10-s samples "
                    "inside the run's chain-step windows. 'Foreign' = a GPU-3 compute process not started by the "
                    "run's own vLLM servers.",
               runs={n: summarise(n, q, p) for n, (q, p) in RUNS.items()})
    out["_provenance"] = stamp(script="h100_monitoring_summary.py", model="n/a", device="h100nvl",
                               n=len(out["runs"]))
    OUT.write_text(json.dumps(out, indent=1))
    for n, r in out["runs"].items():
        m = r.get("gpu3_monitor")
        fp = r.get("foreign_processes")
        print(n, len(r.get("windows", [])), "windows;", "monitor:", m if isinstance(m, str) else
              f"{m['samples']} samples, SM busy {m['sm_clock_mhz_busy_only']}, util {m['util_pct']}",
              "| foreign:", fp if isinstance(fp, str) else fp["count"], "| watchdog lines",
              len(r.get("watchdog_foreign_lines", [])), "| files", len(r.get("files", [])))


if __name__ == "__main__":
    main()
