#!/usr/bin/env python3
"""D115: a 1 s host-load sampler for one live2 run. CPU only, harness instrumentation.

Every `period_s` it records the 1-minute load average, the whole host's CPU busy fraction (from /proc/stat), and the
CPU used by processes that do NOT belong to this run, in cores (from /proc/<pid>/stat utime + stime deltas). A process
belongs to the run when it is the runner itself or any descendant of it (the coordinator process, the vLLM server and
its workers that `--start-server` launches). Other users' processes are never named: the sample keeps only their total
and the top three as (anonymous user index, cores). Nothing here touches the run's decisions or requests; it reads
/proc only.
"""
from __future__ import annotations

import gzip
import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

_CLK = os.sysconf("SC_CLK_TCK")


def _proc_table() -> Dict[int, tuple]:
    """pid -> (ppid, uid, cpu_ticks) for every live process."""
    out = {}
    for d in os.listdir("/proc"):
        if not d.isdigit():
            continue
        try:
            with open(f"/proc/{d}/stat") as f:
                s = f.read()
            rest = s[s.rindex(")") + 2:].split()
            ppid, ut, st = int(rest[1]), int(rest[11]), int(rest[12])
            uid = os.stat(f"/proc/{d}").st_uid
            out[int(d)] = (ppid, uid, ut + st)
        except (OSError, ValueError, IndexError):
            continue
    return out


def _cpu_total() -> tuple:
    with open("/proc/stat") as f:
        v = [int(x) for x in f.readline().split()[1:]]
    idle = v[3] + v[4]
    return sum(v), idle


def _descendants(tab: Dict[int, tuple], root: int) -> set:
    kids: Dict[int, List[int]] = {}
    for pid, (pp, _u, _t) in tab.items():
        kids.setdefault(pp, []).append(pid)
    seen, stack = set(), [root]
    while stack:
        p = stack.pop()
        if p in seen:
            continue
        seen.add(p)
        stack.extend(kids.get(p, ()))
    return seen


class HostLoadSampler:
    def __init__(self, out_path: Path, root_pid: Optional[int] = None, period_s: float = 1.0) -> None:
        self.out_path = Path(out_path)
        self.root = int(root_pid or os.getpid())
        self.period_s = float(period_s)
        self.samples: List[Dict[str, Any]] = []
        self._stop = threading.Event()
        self._th = threading.Thread(target=self._loop, name="live2-hostload", daemon=True)
        self._uid_index: Dict[int, int] = {}
        self.my_uid = os.getuid()

    def start(self) -> "HostLoadSampler":
        self._th.start()
        return self

    def _anon(self, uid: int) -> str:
        if uid == self.my_uid:
            return "this-user"
        if uid == 0:
            return "root"
        if uid not in self._uid_index:
            self._uid_index[uid] = len(self._uid_index) + 1
        return f"other-user-{self._uid_index[uid]}"

    def _loop(self) -> None:
        prev_tab = _proc_table()
        prev_tot = _cpu_total()
        prev_t = time.monotonic()
        while not self._stop.wait(self.period_s):
            tab = _proc_table()
            tot = _cpu_total()
            now = time.monotonic()
            dt = max(now - prev_t, 1e-6)
            mine = _descendants(tab, self.root)
            other_by_uid: Dict[int, float] = {}
            other = 0.0
            for pid, (_pp, uid, ticks) in tab.items():
                if pid in mine or pid not in prev_tab:
                    continue
                d = (ticks - prev_tab[pid][2]) / _CLK / dt
                if d <= 0:
                    continue
                other += d
                other_by_uid[uid] = other_by_uid.get(uid, 0.0) + d
            dtot, didle = tot[0] - prev_tot[0], tot[1] - prev_tot[1]
            with open("/proc/loadavg") as f:
                la1 = float(f.read().split()[0])
            top = sorted(other_by_uid.items(), key=lambda x: -x[1])[:3]
            self.samples.append(dict(
                t=round(time.time(), 3), loadavg_1m=la1,
                host_busy_frac=round(1.0 - didle / dtot, 4) if dtot > 0 else None,
                other_cpu_cores=round(other, 3), run_pids=len(mine),
                other_top=[(self._anon(u), round(c, 3)) for u, c in top]))
            prev_tab, prev_tot, prev_t = tab, tot, now

    def stop(self) -> Dict[str, Any]:
        self._stop.set()
        self._th.join(5.0)
        with gzip.open(self.out_path, "wt") as f:
            for s in self.samples:
                f.write(json.dumps(s) + "\n")
        return self.summary()

    def summary(self) -> Dict[str, Any]:
        def pct(xs):
            v = sorted(x for x in xs if x is not None)
            if not v:
                return dict(n=0)
            g = lambda p: round(v[min(len(v) - 1, int(p * len(v)))], 4)
            return dict(n=len(v), p50=g(0.5), p90=g(0.9), p99=g(0.99), max=round(v[-1], 4))
        s = self.samples
        return dict(period_s=self.period_s, n=len(s),
                    loadavg_1m=pct([x["loadavg_1m"] for x in s]),
                    host_busy_frac=pct([x["host_busy_frac"] for x in s]),
                    other_cpu_cores=pct([x["other_cpu_cores"] for x in s]),
                    note="other_cpu_cores: CPU used by processes not in this run's process tree, in cores; "
                         "other users anonymised")
