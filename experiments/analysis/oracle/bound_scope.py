#!/usr/bin/env python3
"""Recompute the pooled oracle share over ROBOT (recall) and SINGLE-SHOT only, 1x seeds 4-7, and write it
into oracle_results.json beside the existing (dashcam-including) pooled block, with the scope stated.
Dashcam is dropped from the pooled share (ruling after 82f5d019). Uses the verified per-unit bound
machinery in oracle_bootstrap (same units, same D268 valuation, per-arm bootstrap RNG seed 0)."""
from __future__ import annotations
import json, sys, collections
from pathlib import Path
import numpy as np

REPO = Path("/home/nesl/fm-switching")
sys.path.insert(0, str(REPO / "experiments/analysis/oracle"))
import oracle_bootstrap as OB  # noqa: E402
import oracle_lp_run as R  # noqa: E402
import dashcam_episodic as DC  # noqa: E402

SEEDS = [4, 5, 6, 7]
SCOPE = ("Pooled share covers ROBOT (recall) and SINGLE-SHOT questions only. Dashcam is EXCLUDED from this "
         "block: the all-cloud ceiling is not a bound for challenge mAP (dashcam_share_headline.json) and "
         "the dashcam episode measure is under review (reports/study_dashcam_diagnosis.md). 1x seeds 4-7, "
         "per-unit D268 valuation, clip-cluster bootstrap 2000 seed 0.")


def main():
    labels = DC.nexar_labels()
    dash_by_seed = {s: OB.dash_precompute(s, R.simplestream_cloud(s, ""), labels) for s in SEEDS}
    dta = OB.dash_tier_acc(dash_by_seed)
    pooled = collections.defaultdict(list)
    for s in SEEDS:
        rc = R.recall_correctness(s, "")
        for disp, raw in OB.ARMS:
            units = OB.arm_units(raw, s, "", rc, dash_by_seed[s], dta)
            if units is None:
                continue
            pooled[disp].extend([u for u in units if u[1] in ("recall", "single_shot")])
    block = {}
    for disp, units in pooled.items():
        rng = np.random.default_rng(OB.BSEED)
        pf, lf, hf = OB.share_ci(units, "F", rng)
        rng = np.random.default_rng(OB.BSEED)
        ph, lh, hh = OB.share_ci(units, "H", rng)
        block[disp] = {"FAIR": {"share": pf, "ci95": [lf, hf]}, "HINDSIGHT": {"share": ph, "ci95": [lh, hh]}}
    path = REPO / "results/orchestration/live2/oracle/oracle_results.json"
    out = json.load(open(path))
    out["scope"] = SCOPE
    out["pooled_over_seeds_robot_single_shot_1x"] = block
    path.write_text(json.dumps(out, indent=1, default=float))
    bad = [d for d, b in block.items() for w in ("FAIR", "HINDSIGHT")
           if b[w]["share"] is not None and b[w]["share"] > 1 + 1e-6]
    print("arms:", len(block), "| share>1:", bad)
    for d in ("fair-final-rung3", "base", "state-uo", "simplestream"):
        if d in block:
            print(f"  {d:18s} FAIR {block[d]['FAIR']['share']} {block[d]['FAIR']['ci95']} | HIND {block[d]['HINDSIGHT']['share']} {block[d]['HINDSIGHT']['ci95']}")


if __name__ == "__main__":
    main()
