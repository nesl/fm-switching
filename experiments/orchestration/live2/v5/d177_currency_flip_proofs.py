#!/usr/bin/env python3
"""PROOFS for the D177 (1) CURRENCY FLIP: every value the v5 counterfactual compares is a count of
expected ON-TIME CLOUD ANSWERS. CPU only.

WHAT THIS SCRIPT IS FOR, AND WHY IT IS NOT A DIGEST. A dry fleet cell CANNOT show this flip's
effect: the committed dry counters price `harm_warm` 2,297 times and make it non-zero 1,596 times,
and 1,595 of those are below 5e-4 against a bar of 0.65824, so the arm-level decision digests come
back byte-identical with the flip in. That identity is UNEXERCISED IN MAGNITUDE (CLAUDE.md Rule 2)
and is NOT evidence that the flip is decision-neutral. The flip's effect is shown here instead, on
a DECLARED GRID, by running the SAME grid through two trees and diffing the decision logs
(CLAUDE.md Step 2b), which is the comparison a digest cannot make.

THE THREE THINGS IT PRODUCES, each a subcommand so one process does one job:

  --reach            every registered arm CONSTRUCTED, and which of them can reach the converted
                     functions at all, by what path, and whether that path can change a decision.
                     A construction fact, not a reading of the code.
  --log --kind K     the decision log of the declared grid for K in {state, request}, as JSON.
                     Run once per tree, with `--root <tree>`, so the two logs come from two
                     different builds of the same grid and nothing is shared between them.
  --diff A B         how many decisions differ between two such logs, and the FIRST one in full.

THE DELIVERY CURVE IN THE STATE GRID IS DECLARED AND LINEAR, and that is the one methodological
choice here. `arms_v6state._harm_warm` prices displacement through the fitted D162 curve, which on
a dry cell yields the 1,595 tiny harms above; a step curve (the shape `tests/test_cf_objective_
d191.py` uses) yields only whole displaced answers, which clear the bar on BOTH sides of the flip.
Neither reaches the band where the flip changes a decision, so neither can test it. A linear curve
puts PARTIAL displacements on the grid, which is where the band is. The grid is therefore a
constructed instrument for the comparison and NOT a workload: no number in it is a result about
the policy, and every decision it reports carries `scorable: True` only in the sense that the real
MARGIN_CF was used as the bar.

THE BAND, FROM THE ARITHMETIC AND NOT FROM THE GRID. The flip multiplies `plan_state`'s gain and
the margin by 1 / 0.250 = 4.0, and a harm priced with the committed table's device fallback by
1 / (0.250 - 0.071429) = 5.6. A comparison with harm = 0 is exactly scale invariant. For
HOLD_BACK, whose value IS the harm, the bar moves from `harm_old > 0.16456` to
`harm_old > 0.16456 / 1.4 = 0.11754`, so the band of decisions that can move is a harm of 0.11754
to 0.16456 in the old units, at w = 1.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

HERE = Path(__file__).resolve().parent


def setup(root: Optional[str]) -> Path:
    repo = Path(root).resolve() if root else HERE.parents[3]
    for p in (str(repo / "experiments/orchestration/live2/v5"),
              str(repo / "experiments/orchestration/live2"),
              str(repo / "experiments/orchestration/live2/fleet"),
              str(repo / "experiments/orchestration/live2/hybrid"),
              str(repo / "experiments/orchestration/baselines"),
              str(repo / "experiments/lib")):
        if p in sys.path:
            sys.path.remove(p)
        sys.path.insert(0, p)
    return repo


ROBOT_DEADLINE_S = 3.0
# the committed accuracy table's two entries, passed to the harm call exactly as
# `arms_v6state._harm_warm` passes them, so the grid prices harm the way rung 2 does
ACC_CLOUD = 0.25
ACC_DEVICE = 0.071429


def linear_curve(eng: float, slack: float) -> float:
    """A DECLARED delivery curve: the fraction of the service that fits in the slack.

    Nothing is fitted and nothing is read from the committed model. It exists so the grid contains
    PARTIAL displacements, which is where the flip's band is; see the module docstring.
    """
    e = max(float(eng), 1e-9)
    return max(min(float(slack) / e, 1.0), 0.0)


def state_grid() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for p_question in (0.02, 0.1, 0.5, 1.0):
        for p_warm, p_cold in ((0.9, 0.85), (0.9, 0.3), (0.6, 0.0), (0.35, 0.3)):
            for tokens in (200, 1000, 4000):
                for slack in (50.0, 0.35, 0.2, 0.12, 0.05, 0.0001):
                    out.append({"p_question": p_question, "p_warm": p_warm, "p_cold": p_cold,
                                "uncached_tokens": tokens, "slack_s": slack})
    return out


def state_log(repo: Path) -> Dict[str, Any]:
    """The state-decision log of the declared grid, with the harm priced the way rung 2 prices it.

    The harm is NOT passed as a literal: it is computed by `cf_objective.harm_warm_from_queue_delay`
    with the committed table's accuracy arguments, which is the call `arms_v6state._harm_warm`
    makes. That is the whole point of running this on two trees: on the pre-flip tree the harm
    comes back in correctness units and the gain carries `acc = 0.250`, and on the post-flip tree
    both are on-time counts. Neither side is told which it is.
    """
    import cf_margin as CM
    import cf_objective as CO
    import cf_planner as CP

    cf = CP.Counterfactual(counters=CO.DeficitCounters())
    rows: List[Dict[str, Any]] = []
    for i, g in enumerate(state_grid()):
        others = [{"req_id": "o1", "device_id": "robo101", "engine_s": 0.5,
                   "slack_s": g["slack_s"], "weight": 1.0, "p_device_on_time": 1.0}]
        h = CO.harm_warm_from_queue_delay(int(g["uncached_tokens"]), others,
                                          p_on_time=linear_curve,
                                          acc_cloud=ACC_CLOUD, acc_device=ACC_DEVICE)
        d = cf.plan_state(decision_id="s%04d" % i, device_id="robo000", now_s=0.0,
                          p_question=g["p_question"], next_question_s=2.0,
                          p_on_time_warm=g["p_warm"], p_on_time_cold=g["p_cold"],
                          harm_warm=float(h.total), harm_touch=float(h.total),
                          host_warm=True, warm_expressible=True)
        rows.append({"grid": g, "harm_warm": h.total, "decision": d.as_dict()})
    return {"_kind": "state", "_root": str(repo), "_n": len(rows),
            "_margin_cf_declared": CM.MARGIN_CF,
            "_margin_used_by_the_planner": cf._margin().value,
            "_margin_source": cf._margin().source,
            "_objective": CO.OBJECTIVE_STATEMENT,
            "_currency_flip_status_head": CO.CURRENCY_FLIP_STATUS.split(".")[0],
            "_option_value_of_w1_p1": CO.option_value(1.0, 1.0, ACC_CLOUD, 1.0, ACC_DEVICE),
            "_device_only_value_of_w1": CO.device_only_value(1.0, 1.0, ACC_DEVICE),
            "rows": rows}


def request_grid() -> List[Dict[str, Any]]:
    out = []
    for tokens in (467, 3000, 7051, 11000, 13193, 17000, 21000):
        for n_others in (0, 2, 6, 14):
            for readiness in ("COLD", "GPU-WARM"):
                out.append({"tokens": tokens, "n_others": n_others, "readiness": readiness})
    return out


def request_log(repo: Path) -> Dict[str, Any]:
    """The request-decision log of the D171 (1) grid, unchanged from `v5/d171_proofs.py::_grid`.

    `plan_request` is reached only by the `v5-full` family (arms_v5full.py:219), which is in no
    committed rung, so this log is the only place the flip's effect on the four request candidates
    is visible at all. It is the grid D171 already used, so the two sets of numbers are comparable.
    """
    import cf_cost as CC
    import cf_margin as CM
    import cf_objective as CO
    import cf_planner as CP

    CO.DEVLAT._tables()
    rob = sorted(CO.DEVLAT._robot or {})
    res = CC.load_residuals()
    cf = CP.Counterfactual(residuals=res, counters=CO.DeficitCounters())

    def others(n: int) -> List[Any]:
        return [CC.PendingRequest(req_id="o%02d" % i, device_id="robo%03d" % (100 + i),
                                  start_s=0.0, tokens=7051,
                                  deadline_abs_s=ROBOT_DEADLINE_S, accuracy=ACC_CLOUD,
                                  kind="robot", question_id=rob[(i + 7) % len(rob)])
                for i in range(n)]

    rows = []
    for i, g in enumerate(request_grid()):
        d = cf.plan_request(decision_id="r%04d" % i, device_id="robo000", now_s=0.0,
                            deadline_abs_s=ROBOT_DEADLINE_S, history_tokens=g["tokens"],
                            readiness=g["readiness"], others=others(g["n_others"]),
                            coarse_overlap_forecast=float(g["n_others"]),
                            question_id=rob[i % len(rob)], kind="robot")
        rows.append({"grid": g, "decision": d.as_dict()})
    return {"_kind": "request", "_root": str(repo), "_n": len(rows),
            "_margin_cf_declared": CM.MARGIN_CF,
            "_margin_used_by_the_planner": cf._margin().value,
            "_objective": CO.OBJECTIVE_STATEMENT, "rows": rows}


# fields that exist to REPORT the change and would make a decision diff trivially non-empty while
# saying nothing about a decision. Named so the exclusion is auditable, the way
# `d171_proofs._strip` names `margin_effective`.
REPORTING_FIELDS = ("margin", "margin_effective", "margin_source", "value_base", "value_cf",
                    "delta", "elapsed_ms", "candidates")
DECIDING_FIELDS = ("chosen", "base_choice", "cf_choice", "deviated")


def diff(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    """How many of the grid's decisions DIFFER, counted on the fields that decide.

    Two counts are reported and they answer different questions. `n_deciding_differ` is the Step 2b
    number: the decisions that came out differently. `n_any_field_differ` includes the reported
    values, which MUST move (they are in new units), so a zero there would mean the two logs came
    from the same tree and the comparison never ran.
    """
    ra, rb = a["rows"], b["rows"]
    if len(ra) != len(rb):
        return {"error": "grids differ in length: %d vs %d" % (len(ra), len(rb))}
    deciding, anyf, first = [], [], None
    for i, (x, y) in enumerate(zip(ra, rb)):
        dx, dy = x["decision"], y["decision"]
        dd = [k for k in DECIDING_FIELDS if dx.get(k) != dy.get(k)]
        af = [k for k in set(dx) | set(dy)
              if k not in ("candidates", "elapsed_ms") and dx.get(k) != dy.get(k)]
        if dd:
            deciding.append(i)
            if first is None:
                first = {"index": i, "grid": x["grid"],
                         "harm_warm_before": x.get("harm_warm"),
                         "harm_warm_after": y.get("harm_warm"),
                         "fields": dd,
                         "before": {k: dx.get(k) for k in DECIDING_FIELDS + REPORTING_FIELDS
                                    if k != "candidates"},
                         "after": {k: dy.get(k) for k in DECIDING_FIELDS + REPORTING_FIELDS
                                   if k != "candidates"}}
        if af:
            anyf.append(i)
    return {"n": len(ra), "n_deciding_differ": len(deciding),
            "n_any_field_differ": len(anyf),
            "deciding_differ_indices": deciding[:200],
            "first_deciding_difference": first,
            "deciding_fields_compared": list(DECIDING_FIELDS),
            "reporting_fields_excluded_from_the_deciding_count": list(REPORTING_FIELDS),
            "margin_before": a.get("_margin_used_by_the_planner"),
            "margin_after": b.get("_margin_used_by_the_planner"),
            "note": ("n_deciding_differ is the Step 2b number. n_any_field_differ counts the "
                     "REPORTED values too, which are in new units and must move: if it were 0 "
                     "the two logs would have come from one tree and nothing was compared.")}


def reach(repo: Path) -> Dict[str, Any]:
    """Every registered arm, CONSTRUCTED, and whether it can reach the converted functions.

    REACH IS A CONSTRUCTION FACT. An arm that holds a counterfactual engine can reach the
    valuation; one that does not cannot. The two arm-side entry points into the planner are
    `arms_v6state.py:430` (plan_state) and `arms_v5full.py:219` (plan_request), and they are the
    only two in the tree, so an arm's path is decided by which base it is built on and by whether
    its own `plan_state` capability is on.

    WHETHER A REACHING ARM'S DECISIONS CHANGE is then a second question and is answered per arm:
      state_priced   plan_state with a harm priced from the committed table: gain and bar x4.0,
                     harm x5.6, so a decision moves only inside the band (see module docstring)
      state_unpriced plan_state with harm 0 (the arm prices nothing): the comparison is EXACTLY
                     scale invariant, so no decision can move
      request        plan_request: `device_only_value` goes to 0.0, which can move any decision
                     where the device candidate used to win on value
      pd_rd_only     reaches only `harm_warm_from_queue_delay` through `cf_protect_defer` /
                     `cf_request_defer`, which pass acc 1.0 / 0.0: 1.0x, nothing moves
      off            holds the engine but its counterfactual capability is OFF, so it makes no
                     counterfactual decision at all
    """
    import arms as A
    pre = sorted(A.ARMS)
    added = []
    for modname in ("arms_v6state", "arms_v6fair", "arm_names_v6"):
        try:
            mod = __import__(modname)
        except Exception:                                                      # noqa: BLE001
            continue
        fn = getattr(mod, "register", None)
        if fn is not None:
            fn()
    added = sorted(set(A.ARMS) - set(pre))

    rows, refused = [], []
    for name in sorted(A.ARMS):
        try:
            arm = A.ARMS[name]()
        except Exception as e:                                                 # noqa: BLE001
            refused.append({"arm": name, "error": type(e).__name__})
            continue
        inner = getattr(arm, "_rules", None)
        marks = []
        for obj, label in ((arm, ""), (inner, "_rules.")):
            if obj is None:
                continue
            if hasattr(obj, "_cf_engine"):
                marks.append(label + "_cf_engine")
        for attr in ("_pd", "_protect_defer", "_rd", "_request_defer", "_cf"):
            if hasattr(arm, attr):
                marks.append(attr)
        if not marks:
            continue
        plan_state_on = bool(getattr(arm, "plan_state", False)
                             or getattr(inner, "plan_state", False))
        has_pd_rd = any(m in ("_pd", "_protect_defer", "_rd", "_request_defer") for m in marks)
        cls = type(arm).__module__
        if "v5full" in cls or any("v5full" in type(o).__module__
                                  for o in (inner,) if o is not None):
            kind = "request"
        elif plan_state_on:
            kind = "state_priced"
        elif has_pd_rd:
            kind = "pd_rd_only"
        else:
            kind = "off"
        rows.append({"arm": name, "marks": sorted(set(marks)), "class_module": cls,
                     "plan_state_capability": plan_state_on, "path": kind})
    by = {}
    for r in rows:
        by.setdefault(r["path"], []).append(r["arm"])
    return {"n_registered": len(A.ARMS), "n_at_import": len(pre),
            "added_by_register": added,
            "n_can_reach": len(rows), "n_cannot_reach": len(A.ARMS) - len(rows) - len(refused),
            "refused_to_construct": refused,
            "by_path": {k: sorted(v) for k, v in sorted(by.items())},
            "counts_by_path": {k: len(v) for k, v in sorted(by.items())},
            "arms": rows,
            "entry_points": ["arms_v6state.py:430 -> cf_planner.plan_state",
                             "arms_v5full.py:219 -> cf_planner.plan_request"],
            "note": ("plan_sync has NO caller anywhere in the tree; `cf_protect_defer` and "
                     "`cf_request_defer` call cf_objective.harm_warm_from_queue_delay directly "
                     "with acc_cloud=1.0 and acc_device=0.0, which the flip leaves unchanged")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=None, help="the tree to import from; default this file's")
    ap.add_argument("--reach", action="store_true")
    ap.add_argument("--log", action="store_true")
    ap.add_argument("--kind", default="state", choices=("state", "request"))
    ap.add_argument("--diff", nargs=2, default=None, metavar=("BEFORE", "AFTER"))
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    if a.diff:
        doc = diff(json.loads(Path(a.diff[0]).read_text()),
                   json.loads(Path(a.diff[1]).read_text()))
    else:
        repo = setup(a.root)
        if a.reach:
            doc = reach(repo)
        elif a.log:
            doc = state_log(repo) if a.kind == "state" else request_log(repo)
        else:
            ap.error("one of --reach, --log, --diff is required")
    text = json.dumps(doc, indent=1, default=float)
    if a.out:
        Path(a.out).write_text(text + "\n")
        print("wrote %s" % a.out)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
