#!/usr/bin/env python3
"""StudyCOVEX-harden definition audit: DISPATCH against DELIVERY for robot questions.

Two readings of "robot on time" disagreed between the two sessions. This computes BOTH from the
SAME run so the difference cannot be a fixture, a mix or a HEAD difference, and reports them side
by side with their definitions.

  dispatch  a RELEASE decision carries the question's opportunity_id before its own deadline.
            This is what `_harness.released_before_deadline` counts and what my offline
            comparison reported. It says work was DISPATCHED in time, not that an answer arrived.
  delivered `outcomes.jsonl`: `t_delivered` is set and `t_delivered <= t_opportunity +
            deadline_s`. This is SERVICE: an answer reached the application by the deadline.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _harness as H                                                   # noqa: E402


def read_outcomes(run_dir: Path) -> Dict[str, Any]:
    p = Path(run_dir) / "outcomes.jsonl"
    if not p.exists():
        return dict(present=False)
    rows = [json.loads(l) for l in open(p)]
    rc = [r for r in rows if r.get("kind") == "recall"]
    def _dl(r):
        return float(r["t_opportunity"]) + float(r["deadline_s"])
    delivered_any = [r for r in rc if r.get("t_delivered") is not None]
    on_time = [r for r in delivered_any if float(r["t_delivered"]) <= _dl(r)]
    cloud_done_on_time = [r for r in rc if r.get("t_cloud_done") is not None
                          and float(r["t_cloud_done"]) <= _dl(r)]
    return dict(present=True, recall_outcomes=len(rc),
                answered_any=len(delivered_any), answered_on_time=len(on_time),
                cloud_done_on_time=len(cloud_done_on_time),
                kinds=sorted({r.get("kind") for r in rows}))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--sizes", default="4,8,16")
    ap.add_argument("--run-s", type=float, default=600.0)
    ap.add_argument("--v11-switches", default="")
    a = ap.parse_args(argv)
    sw = {s: True for s in a.v11_switches.split(",") if s.strip()}
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(H.ROOT),
                           capture_output=True, text=True).stdout.strip()
    tmp = Path(tempfile.mkdtemp(prefix="covex_defaudit_"))
    rows = []
    for n in [int(x) for x in a.sizes.split(",") if x.strip()]:
        info = H.trace_questions(n, a.run_s, seed=0)
        for arm, label, s in (("policy-core", "policy-core", sw), ("edf", "edf", {}),
                              ("llf", "llf", {})):
            res = H.run_fleet_cell(tmp / ("%s_n%d" % (label, n)), n, run_s=a.run_s, seed=0,
                                   arm_name=arm, switches=s)
            disp = H.released_before_deadline(res["decisions"], info["questions"])
            deliv = read_outcomes(Path(res["outdir"]) / "run")
            row = dict(n_devices=n, arm=label, total=disp["total"],
                       dispatch_released=disp["released"],
                       dispatch_before_deadline=disp["released_before_deadline"],
                       dispatch_fraction=(round(disp["released_before_deadline"] / disp["total"], 4)
                                          if disp["total"] else None),
                       **{("delivery_" + k): v for k, v in deliv.items()})
            if deliv.get("present") and disp["total"]:
                row["delivery_fraction"] = round(deliv["answered_on_time"] / disp["total"], 4)
            rows.append(row)
            print(json.dumps(row), flush=True)
    out = dict(check="covex_harden_definition_audit", is_measurement=False,
               label="DEFINITION AUDIT. Both readings computed from the SAME dry run, so the "
                     "difference cannot be a fixture, device mix or HEAD difference.",
               git_commit=head, seed=0, run_s=a.run_s, v11_switches=sorted(sw),
               definitions=dict(
                   dispatch="a release decision carries the question's opportunity_id before its "
                            "own deadline; work DISPATCHED in time, not an answer delivered",
                   delivery="outcomes.jsonl: t_delivered set and t_delivered <= t_opportunity + "
                            "deadline_s; SERVICE, an answer reached the application in time"),
               rows=rows,
               _provenance=dict(git_commit=head, script="policy/audit/definition_audit.py",
                                model="none (pol4 frozen)", device="flash CPU only",
                                n="seed 0 at %s devices for %.0f s" % (a.sizes, a.run_s),
                                timestamp="2026-11-18T00:00:00"))
    Path(a.out).write_text(json.dumps(out, indent=1, default=str) + "\n")
    print("wrote %s" % a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
