#!/usr/bin/env python3
"""The H100 run plan for the ported arms, in priority order, with a GPU-hour estimate.

StudyLIVE1-port, part 5. **THE PLAN IS NOT RUN.** CPU only: this file computes an estimate from
committed StudySLICE1 Part C timings and prints the order.

The cost model, from committed numbers only:
  * one cell = 30 s discard + 270 s window + a drain of up to 300 s, plus a server start, which
    StudySLICE1 Part C measured end to end at 22 cells in 2 h 44 min = 7.45 min per cell;
  * a capacity ladder for one (arm, condition) stops at the first failing level, which Part C
    measured at 2.44 cells per (policy, condition) pair.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
import classify as CL            # noqa: E402

PARTC = ROOT / "results/cost/study_slice1/slice1_partc_results.json"
MIN_PER_CELL = 164.0 / 22.0           # StudySLICE1 Part C, measured end to end
CELLS_PER_PAIR = 2.44                 # StudySLICE1 Part C, 22 cells over 9 (policy, condition)
CONDITIONS = ("C1a", "C4a", "C1b", "C2")
STREAM_LADDER = (1, 2, 3, 4, 5)       # StudySLICE1 Part D-b's cadence-model ladder

TIER0 = ["always-cloud-fcfs", "device-only", "B10-blocking-aware-admission",
         "B11-naive-slicing"]
TIER1 = ["B9-best-of-breed", "eco-llm", "inar-vl", "B6-latency-aware-routing",
         "videostorm", "B8-utility-per-gpu-second", "B7-edf-feasibility"]
WHY = {
    "always-cloud-fcfs": "the live reference; every other arm is read against it",
    "device-only": "the floor; it sends nothing, so it bounds what routing can win",
    "B10-blocking-aware-admission": "it IS StudySLICE1's P2, already measured in Part B, so it "
                                    "is the port's own validation cell: the live port must "
                                    "reproduce Part B's P2 numbers",
    "B11-naive-slicing": "it IS StudySLICE1's P3_2048, same validation argument, and live it can "
                         "align each link, which the simulator could not express",
    "B9-best-of-breed": "the primary competitor, and live it runs FULL with the real host tier "
                        "rather than the no-host variant the simulator was restricted to",
    "eco-llm": "the strongest joint routing arm in the simulator (challenge mAP 0.5263 on the "
               "audit cell)",
    "inar-vl": "the other strongest routing arm, same level",
    "B6-latency-aware-routing": "the constructed routing arm at the same level, and it reads the "
                                "MEASURED latency estimate, which only exists live",
    "videostorm": "both objectives; after amendment 2 it routes to the cloud, so the live cell "
                  "is the first that tests its allocation rather than its adapter",
    "B8-utility-per-gpu-second": "the admission arm the task names",
    "B7-edf-feasibility": "the deadline arm the task names; its self-fulfilling DEFER dynamic "
                          "needs a live service time to be judged",
}


def plan() -> Dict[str, object]:
    cls = CL.classify()
    live = [r["arm"] for r in cls["arms"] if r["runs_live"]]
    tier0 = [a for a in TIER0 if a in live]
    tier1 = [a for a in TIER1 if a in live]
    tier2 = [a for a in live if a not in tier0 and a not in tier1]
    rows, order = [], 0
    for tier, arms in ((0, tier0), (1, tier1), (2, tier2)):
        for arm in arms:
            order += 1
            cells = len(CONDITIONS) * CELLS_PER_PAIR
            rows.append(dict(order=order, tier=tier, arm=arm,
                             conditions=list(CONDITIONS),
                             expected_cells=round(cells, 1),
                             gpu_hours=round(cells * MIN_PER_CELL / 60.0, 2),
                             why=WHY.get(arm, "the remaining ported arms, in registry order")))
    cum = 0.0
    for r in rows:
        cum += r["gpu_hours"]
        r["cumulative_gpu_hours"] = round(cum, 2)
    by_tier = {}
    for t in (0, 1, 2):
        sel = [r for r in rows if r["tier"] == t]
        by_tier[f"tier{t}"] = dict(n_arms=len(sel),
                                   gpu_hours=round(sum(r["gpu_hours"] for r in sel), 1))
    return dict(
        label="StudyLIVE1-port: the H100 run plan. NOT RUN.",
        cost_model=dict(minutes_per_cell=round(MIN_PER_CELL, 2),
                        cells_per_arm_condition=CELLS_PER_PAIR,
                        source="StudySLICE1 Part C: 22 cells in 2 h 44 min over 9 (policy, "
                               "condition) pairs, each cell 30 s discard + 270 s window + a "
                               "drain of up to 300 s plus a server start"),
        conditions=dict(C1a="KV-GPU, k = 0 warm sessions, cold recall r = 0.05",
                        C4a="KV-HOST, k = 8 warm sessions, cold recall r = 0.05",
                        C1b="KV-GPU, k = 0, cold recall r = 0.1",
                        C2="KV-HOST, k = 8, no cold recall (warm only)"),
        stream_ladder=list(STREAM_LADDER),
        ladder_note="StudySLICE1 Part D-b's cadence model: the ladder is the number of episodic "
                    "streams, 1 to 5, and the capacity walk stops at the first level whose "
                    "episodic p99 misses the budget",
        fairness="every arm gets the same per-cell arrival trace (sha256 asserted), the same E0 "
                 "server configuration unless the arm IS a configuration, the same budget, and "
                 "the same cold sessions and warm plan",
        totals=dict(by_tier=by_tier,
                    n_arms=len(rows),
                    total_cells=round(sum(r["expected_cells"] for r in rows), 1),
                    total_gpu_hours=round(sum(r["gpu_hours"] for r in rows), 1),
                    tier0_plus_tier1_gpu_hours=round(by_tier["tier0"]["gpu_hours"]
                                                     + by_tier["tier1"]["gpu_hours"], 1)),
        excluded=[dict(arm=r["arm"], level=r["level"], reason=r["reason"])
                  for r in cls["arms"] if not r["runs_live"]],
        arms=rows)


if __name__ == "__main__":
    p = plan()
    print(json.dumps(p, indent=1))
