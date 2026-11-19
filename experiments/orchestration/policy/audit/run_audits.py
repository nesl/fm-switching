#!/usr/bin/env python3
"""Driver for the StudyCOVEX-harden audits. Writes one JSON with provenance.

Usage: python3 run_audits.py --out <json>
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _harness as H                                                   # noqa: E402
import blindspot                                                       # noqa: E402
import wiring                                                          # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--fleet-sizes", default="4,8,16")
    ap.add_argument("--run-s", type=float, default=600.0)
    ap.add_argument("--synthetic", type=int, default=32)
    ap.add_argument("--switches", default="",
                    help="comma-separated v1.1 switches to turn on, e.g. rc_tail,deficit_update")
    a = ap.parse_args(argv)
    sw = {s: True for s in a.switches.split(",") if s.strip()}
    unsupported = H.unsupported_switches(sw)

    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(H.ROOT),
                           capture_output=True, text=True).stdout.strip()
    cells = {}
    tmp = Path(tempfile.mkdtemp(prefix="covex_audit_"))
    for n in [int(x) for x in a.fleet_sizes.split(",") if x.strip()]:
        col = []
        with H.capture_delta_j(col):
            res = H.run_fleet_cell(tmp / ("fleet_n%d" % n), n, run_s=a.run_s, seed=0,
                                   switches=sw)
        info = H.trace_questions(n, a.run_s, seed=0)
        cells["fleet_n%d" % n] = dict(
            n_devices=n, seed=0, run_s=a.run_s, kind="fleet trace (pilot settings)",
            robot=H.released_before_deadline(res["decisions"], info["questions"]),
            monitor_opportunities=info["monitor_opportunities"],
            n_decisions=len(res["decisions"]),
            blindspot=blindspot.summarise(col),
            scale=wiring.scale_table(col),
            arm_stats=res["arm_stats"])
        print("fleet n=%d: %d candidates, robot %s" % (
            n, len(col), cells["fleet_n%d" % n]["robot"]), flush=True)

    col = []
    with H.capture_delta_j(col):
        H.run_synthetic_cell(tmp / "synth", a.synthetic, window_s=180.0, switches=sw)
    cells["synthetic_n%d" % a.synthetic] = dict(
        n_devices=a.synthetic, kind="synthetic fixture (fix_checks), 180 s",
        blindspot=blindspot.summarise(col), scale=wiring.scale_table(col))
    print("synthetic n=%d: %d candidates" % (a.synthetic, len(col)), flush=True)

    flags = {k: blindspot.blind_spots(v["blindspot"]) for k, v in cells.items()}
    out = dict(
        check="covex_harden_audits", is_measurement=False,
        label="AUDIT of a DRY RUN. Development data only (seed 0 fleet traces and the committed "
              "synthetic fixture). No GPU, no model server. Screening, not a result.",
        git_commit=head, switches_on=sorted(sw), unsupported_switches=unsupported,
        cells=cells, blind_spot_flags=flags,
        wiring=dict(fields=wiring.field_usage(), dead_writers=wiring.dead_writers()),
        _provenance=dict(
            git_commit=head, script="policy/audit/run_audits.py",
            model="none (pol4 cost curve, frozen)", device="flash CPU only",
            n="seed 0 fleet traces at %s devices for %.0f s, plus the %d-device synthetic "
              "fixture" % (a.fleet_sizes, a.run_s, a.synthetic),
            timestamp="2026-11-18T00:00:00"))
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=1, default=str) + "\n")
    print("wrote %s" % a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
