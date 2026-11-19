#!/usr/bin/env python3
"""StudyCOVEX-harden Part 3: run every arm on the same dry-run traces and compare.

**THIS IS A SCREEN, NOT EVIDENCE.** The dry run prices the engine from the SAME committed cost
curves COVEX's own model uses, so the comparison is OPTIMISTIC FOR COVEX: its predictions and the
simulated world cannot disagree. A baseline that does not model the engine at all is not given
the same advantage. Nothing here may be cited as a result.

Development data only (D124): seed 0, 600 s, tight memory, 50 : 50.
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

HERE = Path(__file__).resolve().parent
AUDIT = HERE.parents[1] / "policy/audit"
sys.path.insert(0, str(AUDIT))

import _harness as H                                                   # noqa: E402

DASH_P, ROB_P = 0.25, 0.90          # D71 targets, as the committed scorer states them
ROB_POOL_MIN = 20                   # D82: a pooled robot result needs at least 20 questions


def run_arm(tmp: Path, n: int, arm: str, switches: Dict[str, bool], run_s: float,
            label: str) -> Dict[str, Any]:
    t0 = time.time()
    res = H.run_fleet_cell(tmp / ("%s_n%d" % (label, n)), n, run_s=run_s, seed=0,
                           arm_name=arm, switches=switches)
    info = H.trace_questions(n, run_s, seed=0)
    rob = H.released_before_deadline(res["decisions"], info["questions"])
    mon_rel = sum(1 for d in res["decisions"] if d["kind"] == "release_monitor")
    offered = info["monitor_opportunities"]
    out = dict(
        n_devices=n, arm=arm, label=label, switches=sorted(switches),
        robot_total=rob["total"], robot_released=rob["released"],
        robot_released_before_deadline=rob["released_before_deadline"],
        robot_pooled_fraction=(round(rob["released_before_deadline"] / rob["total"], 4)
                               if rob["total"] else None),
        robot_pool_measurable=bool(rob["total"] >= ROB_POOL_MIN),
        dashcam_instants_offered=offered, dashcam_released=mon_rel,
        dashcam_released_fraction=(round(mon_rel / offered, 4) if offered else None),
        n_decisions=len(res["decisions"]), wall_s=round(time.time() - t0, 2),
        scorer=try_score(res, arm))
    print(json.dumps({k: v for k, v in out.items() if k != "scorer"}), flush=True)
    return out


def try_score(res: Dict[str, Any], arm: str) -> Dict[str, Any]:
    """Attempt the committed scorer; record its refusal verbatim if it declines.

    A dry run records no cloud answer or score, so the scorer is expected to refuse. That
    refusal is reported rather than worked around, and the release-based proxies above are
    labelled as proxies.
    """
    H.setup_paths()
    try:
        import score as SC
    except Exception as e:                                             # noqa: BLE001
        return dict(ran=False, reason="scorer import failed: %s" % e)
    cal = (H.ROOT / "results/orchestration/live2/calibration"
           / "live2_calibration_dense_jpeg.json")
    if not cal.exists():
        return dict(ran=False, reason="calibration %s not present" % cal.name)
    try:
        out = SC.score_run(Path(res["outdir"]) / "trace", Path(res["outdir"]) / "run", cal, arm)
        return dict(ran=True, keys=sorted(out)[:12])
    except Exception as e:                                             # noqa: BLE001
        return dict(ran=False, refused=True, reason="%s: %s" % (type(e).__name__, str(e)[:300]))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--sizes", default="4,8,16,32")
    ap.add_argument("--run-s", type=float, default=600.0)
    ap.add_argument("--v11-switches", default="")
    a = ap.parse_args(argv)
    sizes = [int(x) for x in a.sizes.split(",") if x.strip()]
    v11 = {s: True for s in a.v11_switches.split(",") if s.strip()}
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(H.ROOT),
                           capture_output=True, text=True).stdout.strip()
    tmp = Path(tempfile.mkdtemp(prefix="covex_cmp_"))
    arms: List[Any] = [("policy-core", {}, "policy-core v1.0")]
    if v11:
        arms.append(("policy-core", v11, "policy-core v1.1"))
    arms += [("edf", {}, "edf"), ("llf", {}, "llf"),
             ("always-cloud-fcfs", {}, "always-cloud-fcfs"), ("device-only", {}, "device-only")]
    rows = []
    for n in sizes:
        for arm, sw, label in arms:
            try:
                rows.append(run_arm(tmp, n, arm, sw, a.run_s, label))
            except Exception as e:                                     # noqa: BLE001
                rows.append(dict(n_devices=n, arm=arm, label=label,
                                 error="%s: %s" % (type(e).__name__, str(e)[:200])))
                print("ERROR n=%d %s: %s" % (n, label, e), flush=True)
    out = dict(
        check="covex_harden_offline_compare", is_measurement=False,
        label="SCREEN, NOT EVIDENCE. The dry run prices the engine from the SAME committed cost "
              "curves COVEX's own model uses, so the comparison is OPTIMISTIC FOR COVEX: its "
              "predictions and the simulated world cannot disagree, an advantage no baseline "
              "that does not model the engine is given. Nothing here may be cited as a result.",
        git_commit=head, seed=0, run_s=a.run_s, ratio="50:50", memory="tight (D76)",
        d71_targets=dict(dashcam_p=DASH_P, robot_p=ROB_P),
        d82_pool_min=ROB_POOL_MIN, v11_switches=sorted(v11),
        unsupported_switches=H.unsupported_switches(v11), rows=rows,
        metric_note="robot_released_before_deadline and dashcam_released are RELEASE counts, a "
                    "proxy for service, not scored outcomes. The committed scorer's verdict per "
                    "row is under `scorer`, including its refusal reason where it declined.",
        _provenance=dict(git_commit=head, script="live2/offline_compare/compare.py",
                         model="none (pol4 cost curve, frozen)", device="flash CPU only",
                         n="seed 0 at %s devices for %.0f s" % (a.sizes, a.run_s),
                         timestamp="2026-11-18T00:00:00"))
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=1, default=str) + "\n")
    print("wrote %s" % a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
