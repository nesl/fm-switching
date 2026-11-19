#!/usr/bin/env python3
"""D119 Step 3: the H100-host decision-speed benchmark. READY TO RUN, NOT RUN BY FLASH.

Nothing here touches a GPU or a model server: it replays the committed dry-run fixture and times
the policy's decisions, so it can run on the H100 host CPU after the pilot without disturbing it.

It sweeps every D119 switch and, for any switch that takes a worker count, every worker count
given. At the time of writing the only implemented switch is `memo_u_sh_grid`; parallel candidate
evaluation is NOT implemented, because candidate DeltaJ is sequentially dependent
(`policy/coordinator.py:279` mutates the fleet on admit), so `--workers` is accepted and recorded
for forward compatibility and currently changes nothing. Exact pruning is not implemented either;
see the report section "D120 item 0".

Usage on the H100 host, after the pilot:
    python3 bench_d119.py --sizes 32,64,128 --out /path/to/out.json
    python3 bench_d119.py --sizes 64 --repeats 3            # for a spread, not one sample
"""
from __future__ import annotations

import argparse
import json
import platform
import socket
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
LIVE2 = ROOT / "experiments/orchestration/live2"
# `policy/coordinator.py` would shadow `live2/coordinator.py`.
sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != HERE]
for _p in (str(LIVE2), str(LIVE2 / "fleet"), str(LIVE2 / "scorer"), str(LIVE2 / "data"),
           str(ROOT / "experiments/orchestration"),
           str(ROOT / "experiments/orchestration/live"),
           str(ROOT / "experiments/orchestration/baselines"),
           str(ROOT / "experiments/orchestration/sim"), str(ROOT / "experiments/lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import fix_checks as FX                                                 # noqa: E402

SWITCHES = ("memo_u_sh_grid",)


def _cpu_model() -> str:
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or "unknown"


def _run_cell(n: int, window_s: float, switches: dict, tag: str) -> dict:
    pp = sys.modules["policy.profiles"]
    orig = pp.load_profiles

    def patched(path=None):
        pf = orig(path)
        for k, v in switches.items():
            if hasattr(pf, k):
                setattr(pf, k, bool(v))
        return pf

    pp.load_profiles = patched
    try:
        t0, c0 = time.time(), time.process_time()
        res = FX._cell(n_dashcam=n // 2, n_robot=n - n // 2, window_s=window_s, seed=1, h=1.0,
                       out=Path("/tmp/d119_bench_%s_n%d" % (tag, n)))
        dl = res["decision_latency_ms"]
        return dict(n_devices=n, switches=dict(switches),
                    p50_ms=dl["p50"], p99_ms=dl["p99"], max_ms=dl.get("max"),
                    samples=dl["n"], wall_s=round(time.time() - t0, 3),
                    thread_cpu_s=round(time.process_time() - c0, 3),
                    process_cpu_s=res.get("cpu_s"),
                    scoring_calls=res["arm_stats"].get("scoring_calls"),
                    epoch_overruns=res.get("epoch_overruns"))
    finally:
        pp.load_profiles = orig


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sizes", default="32,64,128")
    ap.add_argument("--window-s", type=float, default=180.0)
    ap.add_argument("--repeats", type=int, default=1,
                    help="run each cell this many times, so the report can carry a spread "
                         "rather than a single sample")
    ap.add_argument("--workers", default="1",
                    help="recorded for forward compatibility; parallel candidate evaluation is "
                         "not implemented, see the module docstring")
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    sizes = [int(x) for x in a.sizes.split(",") if x.strip()]
    workers = [int(x) for x in a.workers.split(",") if x.strip()]

    settings = [dict()]                                   # baseline, every switch off
    for s in SWITCHES:
        settings.append({s: True})
    if len(SWITCHES) > 1:
        settings.append({s: True for s in SWITCHES})      # all combined

    rows = []
    for st in settings:
        tag = "base" if not st else "+".join(sorted(st))
        for n in sizes:
            for rep in range(max(1, a.repeats)):
                r = _run_cell(n, a.window_s, st, tag)
                r["repeat"] = rep
                r["workers_recorded"] = workers
                rows.append(r)
                print(json.dumps(r, sort_keys=True), flush=True)

    out = dict(check="d119_bench", is_measurement=False,
               label="DECISION SPEED ONLY. Dry run on the committed cost curve; no GPU, no "
                     "model server, no engine. Safe to run on a shared host.",
               fixture="fix_checks._cell: synthetic 50:50, mode A, tight memory, seed 1, "
                       "H = 1.0 s, dry run, pol4 frozen",
               window_s=a.window_s, sizes=sizes, switches=list(SWITCHES),
               parallel_candidates_implemented=False,
               parallel_blocked_because="candidate DeltaJ is sequentially dependent: "
                                        "live2/arms_policy.py:479 calls co.escalate(self.fleet, "
                                        "req) per candidate and policy/coordinator.py:279 does "
                                        "fleet.pending += items on admit, so candidate k+1 is "
                                        "scored against candidate k's admission (D108)",
               host=dict(hostname=socket.gethostname(), cpu=_cpu_model(),
                         python=platform.python_version()),
               rows=rows)
    try:
        out["git_commit"] = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(ROOT),
                                           capture_output=True, text=True).stdout.strip()
    except OSError:
        out["git_commit"] = "unknown"
    if a.out:
        Path(a.out).write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
        print("wrote %s" % a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
