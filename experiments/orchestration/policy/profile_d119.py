#!/usr/bin/env python3
"""D119 Step 1: run ONE policy-core cell so a SAMPLING profiler can be attached to it.

Why a separate driver. cProfile inflated an earlier speed figure in this study badly enough that
a 5.05x claim had to be withdrawn (StudyLIVE2-perf), so D119 requires a sampling profiler. This
script does nothing but run the committed `fix_checks` cell, with no instrumentation of its own,
so `py-spy record` can sample it from outside the process.

Usage:
    py-spy record -f raw -o stacks.txt -- python3 profile_d119.py --devices 64 --window-s 180
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
LIVE2 = ROOT / "experiments/orchestration/live2"
# `policy/coordinator.py` would shadow `live2/coordinator.py`, so this directory is kept OFF the
# path and every import below resolves to the live2 tree.
sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != HERE]
for _p in (str(LIVE2), str(LIVE2 / "fleet"), str(LIVE2 / "scorer"), str(LIVE2 / "data"),
           str(ROOT / "experiments/orchestration"),
           str(ROOT / "experiments/orchestration/live"),
           str(ROOT / "experiments/orchestration/baselines"),
           str(ROOT / "experiments/orchestration/sim"), str(ROOT / "experiments/lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import fix_checks as FX                                                 # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--devices", type=int, default=64)
    ap.add_argument("--window-s", type=float, default=180.0)
    ap.add_argument("--out", default=None)
    ap.add_argument("--summary", default=None)
    a = ap.parse_args(argv)
    n = a.devices
    out = Path(a.out) if a.out else Path("/tmp/claude-1001/d119_profile_n%d" % n)
    t0 = time.time()
    res = FX._cell(n_dashcam=n // 2, n_robot=n - n // 2, window_s=a.window_s, seed=1, h=1.0,
                   out=out)
    wall = time.time() - t0
    s = dict(n_devices=n, window_s=a.window_s, wall_s=round(wall, 3),
             n_decisions=res["n_decisions"], decision_latency_ms=res["decision_latency_ms"],
             cpu_s=res.get("cpu_s"), scoring_calls=res["arm_stats"].get("scoring_calls"))
    print(json.dumps(s, sort_keys=True))
    if a.summary:
        Path(a.summary).write_text(json.dumps(s, indent=1, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
