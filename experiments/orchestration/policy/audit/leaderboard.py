#!/usr/bin/env python3
"""D129 leaderboard: candidates against the baselines, on DELIVERY, across seeds and sizes.

Delivery, not dispatch: `t_delivered` set and `t_delivered <= t_opportunity + deadline_s`.
`always-cloud-fcfs` is REPORTED and NOT GATING (D127). Gating baselines are edf and llf.

Development seeds only; the harness refuses seeds 1, 2 and 3, which are reserved for round 1.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _harness as H                                                   # noqa: E402


def _digest(outdir: Path) -> Any:
    for name in ("run_meta.json", "header.json"):
        p = Path(outdir) / "run" / name
        if p.exists():
            try:
                return json.loads(p.read_text()).get("fairness_digest")
            except Exception:                                          # noqa: BLE001
                return None
    return None


def delivery(run_dir: Path) -> Dict[str, Any]:
    p = Path(run_dir) / "outcomes.jsonl"
    if not p.exists():
        return dict(present=False)
    rows = [json.loads(l) for l in open(p)]
    out: Dict[str, Any] = dict(present=True)
    for kind in ("monitor", "recall"):
        k = [r for r in rows if r.get("kind") == kind]
        if not k:
            out[kind] = dict(offered=0, on_time=0, fraction=None)
            continue
        ot = [r for r in k if r.get("t_delivered") is not None
              and float(r["t_delivered"]) <= float(r["t_opportunity"]) + float(r["deadline_s"])]
        out[kind] = dict(offered=len(k), on_time=len(ot), fraction=round(len(ot)/len(k), 4))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--seeds", default="4,5,6")
    ap.add_argument("--sizes", default="8,16")
    ap.add_argument("--run-s", type=float, default=600.0)
    ap.add_argument("--candidate", default="planner_rc,plan_latest,replan,deficit_update,"
                                            "write_staleness,realistic_competing")
    ap.add_argument("--candidate-name", default="v1.2")
    ap.add_argument("--published", default="",
                    help="comma-separated PUBLISHED arm names from session 3 to add as an "
                         "additional, clearly-labelled field. They are NOT gating under D127.")
    a = ap.parse_args(argv)
    cand = {s: True for s in a.candidate.split(",") if s.strip()}
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(H.ROOT),
                           capture_output=True, text=True).stdout.strip()
    tmp = Path(tempfile.mkdtemp(prefix="covex_lb_"))
    arms = [("policy-core", cand, a.candidate_name),
            ("edf@8", {}, "edf C=8"), ("edf@4", {}, "edf C=4"), ("llf", {}, "llf")]
    # D130: session 3's ported published systems are an ADDITIONAL comparison field, reported and
    # not gating, since D127 defines the gate against edf and llf. An explicit list is passed
    # rather than iterating ARM_NAMES, so 24 new arms do not slow this cycle.
    for pub in [x.strip() for x in a.published.split(",") if x.strip()]:
        arms.append((pub, {}, "published:" + pub))
    rows: List[Dict[str, Any]] = []
    for seed in [int(x) for x in a.seeds.split(",") if x.strip()]:
        H.assert_dev_seed(seed)
        for n in [int(x) for x in a.sizes.split(",") if x.strip()]:
            for arm, sw, label in arms:
                t0 = time.time()
                try:
                    res = H.run_fleet_cell(tmp / ("s%d_%s_n%d" % (seed, label.replace(" ", ""), n)),
                                           n, run_s=a.run_s, seed=seed, arm_name=arm, switches=sw)
                    d = delivery(Path(res["outdir"]) / "run")
                    row = dict(seed=seed, n_devices=n, arm=label,
                               dashcam_delivered=d.get("monitor", {}).get("fraction"),
                               dashcam_offered=d.get("monitor", {}).get("offered"),
                               robot_delivered_on_time=d.get("recall", {}).get("on_time"),
                               robot_total=d.get("recall", {}).get("offered"),
                               robot_fraction=d.get("recall", {}).get("fraction"),
                               wall_s=round(time.time()-t0, 1),
                               # D130: the fairness digest is a property of the TRACE, so it must
                               # be identical across arms on the same trace. A ported arm with a
                               # DIFFERENT digest is a porting defect, not a result, and is
                               # flagged to session 3 rather than scored.
                               fairness_digest=_digest(Path(res["outdir"])),
                               gating=bool(not label.startswith("published:")))
                except Exception as e:                                  # noqa: BLE001
                    row = dict(seed=seed, n_devices=n, arm=label,
                               error="%s: %s" % (type(e).__name__, str(e)[:160]))
                rows.append(row)
                print(json.dumps(row), flush=True)
    out = dict(check="covex_harden_leaderboard", is_measurement=False,
               label="SCREEN on DELIVERY. Read with the live calibration in section 10: at 8 "
                     "devices the dry dashcam axis cannot rank COVEX against edf.",
               git_commit=head, candidate=a.candidate_name, candidate_switches=sorted(cand),
               gating_baselines=["edf", "llf"], non_gating=["always-cloud-fcfs"],
               seeds=a.seeds, sizes=a.sizes, rows=rows,
               _provenance=dict(git_commit=head, script="policy/audit/leaderboard.py",
                                model="none (pol4 frozen)", device="flash CPU only",
                                n="seeds %s at %s devices for %.0f s" % (a.seeds, a.sizes, a.run_s),
                                timestamp="2026-11-18T00:00:00"))
    Path(a.out).write_text(json.dumps(out, indent=1, default=str) + "\n")
    print("wrote %s" % a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
