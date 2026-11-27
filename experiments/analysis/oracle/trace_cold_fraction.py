#!/usr/bin/env python3
"""Policy-independent cold-tier infeasible fraction, per condition, from the TRACE population.

For every robot recall question in the trace (trace history_tokens, the population of oracle_feasible_pop.py),
apply the cold-tier test of oracle_feasible.reason_recall (cold first token + RTT + upload > 3.0 s).
Fraction = infeasible / robot questions. Does not read any policy cell, so it does not depend on the policy's
own context choice. Writes a NEW key "trace_based" into cold_tier_fractions.json; the existing
"conditions" entries are left unchanged.
Device mix: n16 uses 40:40:20 (committed default); n20 and n32 use 3:11:2 (tag c3-11-2, run_meta ratio).
"""
from __future__ import annotations
import json, sys
from pathlib import Path

REPO = Path("/home/nesl/fm-switching")
for p in ("experiments/analysis/oracle", "experiments/orchestration/live2/fleet"):
    sys.path.insert(0, str(REPO / p))
import oracle_feasible as OF  # noqa: E402
import trace as TR  # noqa: E402

OUT = REPO / "results/orchestration/live2/oracle/cold_tier_fractions.json"


def trace_fraction(n_devices, ratio, seeds):
    bad = tot = 0
    per = {}
    for s in seeds:
        recs = TR.generate_trace(seed=s, n_devices=n_devices, ratio=ratio, run_s=1200.0, mode="A",
                                 robot_question_set="lh_req", ss_question_set="ss2", dashcam_format="epg",
                                 robot_upload="per-frame", robot_reask_mean_s=30.0)["records"]
        hs = [int(r["history_tokens"]) for r in recs
              if r["kind"] == "recall_question" and str(r["device_id"]).startswith("robo")]
        b = sum(1 for h in hs if h and not OF.reason_recall(h)["ok_cold"])
        per[f"s{s}"] = {"robot_questions": len(hs), "cold_infeasible": b,
                        "fraction": round(b / len(hs), 4) if hs else None}
        bad += b; tot += len(hs)
    return {"robot_questions": tot, "cold_infeasible": bad,
            "fraction": round(bad / tot, 4) if tot else None, "per_seed": per}


def main():
    conds = {
        "n16 1x s4": (16, "40:40:20", [4]),
        "n16 1x s4 to s7": (16, "40:40:20", [4, 5, 6, 7]),
        "h0.5 s4": (16, "40:40:20", [4]),          # memory level does not change the trace population
        "n20 s4 (c3-11-2)": (20, "3:11:2", [4]),
        "n32 s4 (c3-11-2)": (32, "3:11:2", [4]),
    }
    doc = json.load(open(OUT))
    out = {}
    for name, (n, ratio, seeds) in conds.items():
        out[name] = trace_fraction(n, ratio, seeds)
    doc["trace_based"] = {"_what": "Policy-independent: trace robot questions (history_tokens) through the cold-tier "
                                   "test (first token + RTT + upload > 3.0 s). Not dependent on any policy's context.",
                          "conditions": out}
    OUT.write_text(json.dumps(doc, indent=1, default=float))
    for k, v in out.items():
        print(f"{k:20s} trace {v['cold_infeasible']}/{v['robot_questions']} = {v['fraction']}")


if __name__ == "__main__":
    main()
