#!/usr/bin/env python3
"""Per-arm cold-tier infeasibility fraction, per condition (read-only, CPU, committed cells).

For rung 3 (covex-v6-fair-final): robot rows whose cold-tier first token + RTT + upload exceeds the 3 s
recall deadline, divided by the robot rows of the cell. Uses the same test as oracle_feasible.py
(feasible_recall / reason_recall) and the same per-row context (request prompt_tokens). Writes a NEW file
results/orchestration/live2/oracle/cold_tier_fractions.json. Does not change any committed number.
"""
from __future__ import annotations
import json, sys
from pathlib import Path

REPO = Path("/home/nesl/fm-switching")
sys.path.insert(0, str(REPO / "experiments/analysis/oracle"))
sys.path.insert(0, str(REPO / "experiments/analysis/episodic"))
import oracle_feasible as OF  # noqa: E402
import oracle_bootstrap as OB  # noqa: E402
import episodic_lib as E  # noqa: E402
from _provenance import stamp  # noqa: E402

ARM = "covex-v6-fair-final"


def fraction_for_cell(path):
    cell = E.load_cell(path)
    pt = OB.req_pt(path)
    rows = (((cell.get("score") or {}).get("score") or {}).get("robot_rows")) or []
    robot = [r for r in rows if str(r.get("device_id", "")).startswith("robo")]
    cold_bad = 0
    best_bad = 0
    for r in robot:
        t = pt.get(r.get("opportunity_id"), 0)
        if not t:
            continue
        rs = OF.reason_recall(t)
        cold_bad += 0 if rs["ok_cold"] else 1
        best_bad += 0 if rs["ok_best"] else 1
    return {"robot_rows": len(robot), "cold_tier_infeasible": cold_bad, "best_tier_infeasible": best_bad,
            "cold_fraction": round(cold_bad / len(robot), 4) if robot else None}


def main():
    conds = {
        "n16 1x s4": [("1x", s) for s in (4,)],
        "n16 1x s4 to s7": [("1x", s) for s in (4, 5, 6, 7)],
        "h0.5 s4": [("h0.5", 4)],
        "n20 s4 (c3-11-2)": [("n20", 4)],
        "n32 s4 (c3-11-2)": [("n32", 4)],
    }
    paths = {}
    runs = REPO / "results/orchestration/live2/frozen_test/runs"
    def cellpath(kind, s):
        if kind == "1x":
            return Path(OB._cell(ARM, s, ""))          # same resolver as the bound (prefers _rerun)
        if kind == "h0.5":
            return Path(OB._cell(ARM, s, "_kv0.5r_h0.5"))
        if kind == "n20":
            return runs / f"{ARM}_n20_s{s}_1200s_h27_3t_c3-11-2_L3_epg_rq30"
        if kind == "n32":
            return runs / f"{ARM}_n32_s{s}_1200s_h27_3t_c3-11-2_L3_epg_rq30"
    out = {"_what": "Rung 3 cold-tier infeasible robot rows / robot rows, per condition. Per-row test as in "
                    "oracle_feasible.py. Cells resolved by oracle_bootstrap._cell (the bound's resolver, _rerun first).", "arm": ARM, "conditions": {}}
    for name, items in conds.items():
        tot_bad = tot_rows = 0
        per = {}
        for kind, s in items:
            p = cellpath(kind, s)
            if not (p / "cell.json").exists():
                per[f"s{s}"] = "MISSING"
                continue
            f = fraction_for_cell(str(p))
            per[f"s{s}"] = f
            tot_bad += f["cold_tier_infeasible"]
            tot_rows += f["robot_rows"]
        out["conditions"][name] = {"per_seed": per, "pooled_cold_fraction":
                                   round(tot_bad / tot_rows, 4) if tot_rows else None,
                                   "pooled_robot_rows": tot_rows, "pooled_cold_infeasible": tot_bad}
    out["_provenance"] = stamp(script="cold_tier_fraction.py", model="none", device="jetson_orin")
    (REPO / "results/orchestration/live2/oracle/cold_tier_fractions.json").write_text(
        json.dumps(out, indent=1, default=float))
    for k, v in out["conditions"].items():
        print(f"{k:20s} pooled {v['pooled_cold_infeasible']}/{v['pooled_robot_rows']} = {v['pooled_cold_fraction']}")


if __name__ == "__main__":
    main()
