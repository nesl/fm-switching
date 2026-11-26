#!/usr/bin/env python3
"""T-constrained oracle LP under the D270 valuation (CPU, read-only, no images).

Units come from oracle_lp_run.build_units (the arm-independent trace population). Revalued to D270:
- recall: FAIR gain = acc[recall, cloud, WITH_HISTORY] - acc[recall, device] for every unit (the
  oracle serves with history, the best context); FAIR floor = acc[recall, device] per unit.
  HINDSIGHT unchanged (realised [cloud right] - [device right]).
- single_shot: FAIR gain unchanged (acc_cloud - acc_device = 0.073896), HINDSIGHT realised.
- dashcam: episode units and floor from build_units under the thresholds of DASH_THRESH
  (instant = committed score_cell; live_dev = recalibrated on DEV clips, D6).
Capacity T per condition: 1x 17945.2 (D230 12), h0.5 11619.8 (measured here). kv0.5r is retired.
Output: per seed, per type and pooled, LP value at T and 1.10T, the capacity_binds flag, and the
uncapacitated sum of positive unit values (the gap is the cost of the capacity constraint).
"""
from __future__ import annotations
import json, os, sys, collections
from pathlib import Path

REPO = Path("/home/nesl/fm-switching")
for p in ("experiments/analysis/oracle", "experiments/analysis/episodic", "experiments/analysis/early1",
          "experiments/analysis/canon", "experiments/lib", "experiments/orchestration/live2/fleet"):
    sys.path.insert(0, str(REPO / p))
import oracle_lp_run as LR  # noqa: E402
import oracle_bootstrap as OB  # noqa: E402
from oracle_lp import Unit  # noqa: E402
from _provenance import stamp  # noqa: E402

MODE = os.environ.get("DASH_THRESH", "instant")
CONDS = [("", "1x", 17945.2, [4, 5, 6, 7]), ("_kv0.5r_h0.5", "h0.5", 11619.8, [4])]
A_RC_H, A_RD = OB.A_RC_H, OB.A_RD


def revalue(units, floor):
    rec = []
    for (u, _vF, vH) in units["recall"]:
        vf = A_RC_H - A_RD
        rec.append((Unit(u.uid, vf, u.work, u.release, u.deadline), vf, vH))
    units["recall"] = rec
    floor["recall"]["FAIR"] = len(rec) * A_RD
    return units, floor


def main():
    tier, _, _ = LR.dev_tier()
    if MODE == "live_dev":
        t = json.load(open(REPO / "results/orchestration/live2/oracle/dashcam_thresholds_live_dev.json"))["tiers"]
        th_dev, th_cloud = t["device"]["theta"], t["cloud"]["theta"]
    else:
        th_dev, th_cloud = OB.TH_DEV, OB.TH_CLOUD
    ssbox = LR.ss_box()
    out = {"_what": "T-constrained oracle LP under the D270 valuation. Capacity binds if capacity_binds; "
                    "if not, the T-constrained oracle equals the uncapacitated per-unit oracle.",
           "dash_mode": MODE, "dash_thresholds": {"device": th_dev, "cloud": th_cloud}, "conds": {}}
    for tag, mem, T, seeds in CONDS:
        cres = {"T": T, "seeds": {}}
        for s in seeds:
            rc = LR.recall_correctness(s, tag)
            ac, ad = LR.acc_cloud_device(s, tag)
            cloud = LR.simplestream_cloud(s, tag)
            recall_unc = LR.min_recall_uncached(s, tag)
            units, floor = LR.build_units(s, tag, mem, rc, ac, ad, ssbox, cloud, tier, th_dev, th_cloud, recall_unc)
            units, floor = revalue(units, floor)
            seedres = {"n_units": {k: len(v) for k, v in units.items()}, "floor": floor, "scales": {}}
            for scale, Tc in (("T", T), ("1.10T", 1.10 * T)):
                sc = {}
                for which in ("FAIR", "HINDSIGHT"):
                    per = {}
                    pooled_units = []
                    for typ in ("recall", "single_shot", "dashcam"):
                        r, g = LR.run_lp(units[typ], Tc, which)
                        vals = [(x[1] if which == "FAIR" else x[2]) for x in units[typ]]
                        per[typ] = {"lp_value": r["lp_value"], "capacity_binds": r["capacity_binds"],
                                    "uncapacitated_positive_sum": round(sum(v for v in vals if v and v > 0), 6)}
                        pooled_units += units[typ]
                    rp, _ = LR.run_lp(pooled_units, Tc, which)
                    per["pooled"] = {"lp_value": rp["lp_value"], "capacity_binds": rp["capacity_binds"]}
                    sc[which] = per
                seedres["scales"][scale] = sc
            cres["seeds"][f"s{s}"] = seedres
            print(mem, f"s{s}", {k: v for k, v in seedres["scales"]["T"]["FAIR"]["pooled"].items()})
        out["conds"][mem] = cres
    out["_provenance"] = stamp(script="oracle_lp_d270.py", model="none", device="jetson_orin")
    name = "oracle_lp_d270" + ("" if MODE == "instant" else "_" + MODE) + ".json"
    (REPO / "results/orchestration/live2/oracle" / name).write_text(json.dumps(out, indent=1, default=float))
    print("wrote", name)


if __name__ == "__main__":
    main()
