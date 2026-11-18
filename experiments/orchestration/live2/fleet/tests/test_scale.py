#!/usr/bin/env python3
"""Check (g): can the emulator keep run-clock time at 64 devices, in both upload modes?

StudyLIVE2-fleet, part 6, check (g). Real time, so it takes about 2 x (run_s + drain) of wall
clock. Stub coordinator only, CPU only, flash.

NOT A MEASUREMENT OF THE SYSTEM. It measures the HARNESS on this host: scheduling lateness and
the emulator's own CPU use. A run is marked INVALID when p99 lateness exceeds 50 ms, which says
the emulator could not keep time, not that any policy failed. This is the D77 pilot question
"minutes per run and emulator CPU use", asked of the emulator alone.

Run:  python3 test_scale.py [--devices 64] [--run-s 180]
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

HERE = Path(__file__).resolve().parent
FLEET = HERE.parent
for p in (str(FLEET),):
    if p not in sys.path:
        sys.path.insert(0, p)

import emulator as EM       # noqa: E402
import trace as TR          # noqa: E402


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--devices", type=int, default=64)
    ap.add_argument("--run-s", type=float, default=180.0)
    ap.add_argument("--ratio", default="50:50")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    tmp = Path(a.out) if a.out else Path(tempfile.mkdtemp(prefix="live2_scale_"))
    tmp.mkdir(parents=True, exist_ok=True)
    print(f"scratch: {tmp}")
    b = TR.generate_trace(a.seed, a.devices, a.ratio, a.run_s, "A")
    meta = TR.write_trace(tmp / "trace", b)
    print(json.dumps(dict(n_records=meta["n_records"],
                          opportunities=meta["n_device_answers"],
                          stats={k: meta["stats"][k] for k in
                                 ("dashcam_meeting_200", "robot_questions_total",
                                  "dashcam_plays_completed", "clip_repeats",
                                  "session_repeats")}), indent=2, sort_keys=True))
    rows: List[Dict[str, Any]] = []
    for mode in ("A", "B"):
        em = EM.FleetEmulator(tmp / "trace", EM.StubCoordinator(capacity_per_s=32.0),
                              mode, realtime=True)
        rm = em.run(tmp / f"run_{mode}")
        lat = rm["lateness"]
        rows.append(dict(mode=mode, devices=a.devices, run_s=a.run_s,
                         n_opportunities=rm["n_opportunities"], n_served=rm["n_served"],
                         lateness_p50_ms=lat["p50_ms"], lateness_p90_ms=lat["p90_ms"],
                         lateness_p99_ms=lat["p99_ms"], lateness_max_ms=lat["max_ms"],
                         n_scheduled_actions=lat["n"], cpu_s=rm["cpu_s"],
                         cpu_fraction=rm["cpu_fraction"], wall_s=rm["wall_s"],
                         maxrss_kb=rm["maxrss_kb"],
                         uplink_queue_p99_s_median=rm["uplink_queue_p99_s_median"],
                         digests_equal=rm["digests_equal"], run_valid=rm["run_valid"]))
        print(json.dumps(rows[-1], indent=2, sort_keys=True))
    out = dict(rows=rows, limit_p99_ms=EM.MAX_P99_LATENESS_MS,
               all_valid=all(r["run_valid"] for r in rows),
               all_digests_equal=all(r["digests_equal"] for r in rows),
               note="HARNESS check only. Stub coordinator, CPU only, flash. Not a measurement.")
    (tmp / "scale_summary.json").write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print(json.dumps(out, indent=2, sort_keys=True))
    if not a.out:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0 if out["all_valid"] and out["all_digests_equal"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
