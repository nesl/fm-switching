#!/usr/bin/env python3
"""CHECK 1 of StudyD216-KV025: does an eviction reach a decision through the residency belief?

THE QUESTION, IN THE FORM THE 2026-11-23 RULING MAKES IT. Rungs 2 and 3 do not trade memory off by
design (that is rung 4's counterfactual, D151 / D163), so their capacity-blindness FOR DECISIONS is
not a defect. The sentence that replaces it is "rungs 2 and 3 adapt to memory pressure only
REACTIVELY, through engine telemetry". That sentence is only true if the reactive path reaches a
decision, and this script measures whether it does, from the COMMITTED live cells and from the code.

THE PATH, with every link named.

  WRITE     `engine_actions.belief_update_from_cached_tokens` (engine_actions.py:315) turns the
            engine's own per-request `prompt_tokens_details.cached_tokens` into a one-hot
            `SessionRec.belief` (engine_actions.py:387-388). ct > 0 promotes to `gpu`; ct == 0 on a
            request that offered a built prefix demotes to `cold`; ct is None is NO evidence.
  GATE      `coordinator._collect` (coordinator.py:1796) calls it on every completed request and
            then RESTORES THE SNAPSHOT unless `self._belief_apply` (coordinator.py:364) is true,
            which needs `LIVE2_BELIEF_CORRECTION=apply` in the environment or the ARM to declare
            `live2_belief_apply`. Only `V6StateArm` and its descendants declare it
            (arms_v6state.py:165, defaulting to `plan_state`), so rungs 2, 3 and 4 APPLY the
            correction and every other arm - rung 0, rung 1 and all fourteen paper baselines,
            b7-edf-feasibility among them - COUNTS IT AND THROWS IT AWAY.
  READ      rung 2 and rung 3 pricing: `coordinator.py:1161` (`TP.should_touch(belief=...)`, which
            refuses or prices the touch), `coordinator.py:1238` (`TP.build_price_gpu_s(..., belief)`
            feeding `budget.can_spend`), `coordinator.py:1294` and `:1331`
            (`s.residency_readiness()`, the recall charge and the D179 (4) release re-check's
            uncached count), and `arms_v6state.py:416` (`host_warm` from
            `roster["belief_by_session"]`, coordinator.py:757, which gates the RELOAD candidate).
            b7: `cstate.py:636/648` puts `s.readiness()` on every `RecallQuery`, and
            `baselines/constructed.py:184` reads `q.readiness` in
            `C.recall_ttft_s(...)` to admit, defer or reject. Those are READS that change a
            decision, not writes.

WHAT THIS SCRIPT PRODUCES. Per committed live cell: the number of corrections offered, the number
that CHANGED the belief, the number REVERTED by the observe-only gate, and the destination of each
change. The three cases the brief requires are then decided from the counts, per arm family:

  ABSENT                 the correction never reaches a decision (changed == observed_only)
  CONSTANT-FOR-HOST      it fires and varies but can never say `host`, so host-warm and cold are
                         indistinguishable to it
  FIRES AND VARIES       changed > 0 and observed_only == 0 and more than one destination is seen

READ-ONLY. It runs no cell and builds no arm; it reads `coordinator_result.json` out of a git
object at a named sha, so the local checkout's state cannot affect it.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import subprocess
from typing import Any, Dict, List

KEYS = ("belief_corrections", "belief_corrections_changed",
        "belief_corrections_observed_only")
APPLY_FAMILIES = ("covex-v6-state", "covex-v6-fair", "covex-v6-cf", "covex-v6-final")


def cells_at(sha: str, repo: str) -> List[Dict[str, Any]]:
    names = subprocess.check_output(
        ["git", "-C", repo, "ls-tree", "-r", "--name-only", sha, "--",
         "results/orchestration/live2"], text=True).split()
    out = []
    for f in names:
        if not f.endswith("coordinator_result.json"):
            continue
        try:
            d = json.loads(subprocess.check_output(
                ["git", "-C", repo, "show", "%s:%s" % (sha, f)], text=True))
        except Exception:                                                  # noqa: BLE001
            continue
        if not isinstance(d, dict):
            continue
        c = dict(d.get("counts") or {})
        k = {x: int(c.get(x, 0) or 0) for x in KEYS}
        k.update({x: int(v) for x, v in c.items() if str(x).startswith("belief_to_")})
        if not k.get("belief_corrections"):
            continue
        out.append({"cell": os.path.basename(os.path.dirname(f)),
                    "arm": d.get("arm"), "path": f, "counts": k})
    return out


def verdict(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    corr = sum(r["counts"]["belief_corrections"] for r in rows)
    chg = sum(r["counts"]["belief_corrections_changed"] for r in rows)
    obs = sum(r["counts"]["belief_corrections_observed_only"] for r in rows)
    dest = collections.Counter()
    for r in rows:
        for k, v in r["counts"].items():
            if k.startswith("belief_to_"):
                dest[k] += v
    applied = chg - obs
    if corr == 0:
        v = ("ABSENT: the corrector was never called, so no eviction can reach a decision "
             "through it")
    elif chg == 0:
        v = ("ABSENT IN THE DECISION REGISTER: the corrector fired and never changed a belief, "
             "so nothing it produced could reach a read. Rule 2 UNEXERCISED, not a negative")
    elif applied == 0:
        v = ("ABSENT IN THE DECISION REGISTER: every correction was computed, counted and then "
             "REVERTED by the observe-only gate (coordinator.py:1803). The belief these arms "
             "price and admit from never saw it. Rule 2 UNEXPRESSIBLE: the mechanism fires and "
             "the harness discards the channel it acts through")
    elif len([k for k, n in dest.items() if n > 0]) <= 1:
        v = ("CONSTANT IN THE SENSE THAT MATTERS: the correction is applied but reaches only one "
             "destination (%s), so it cannot represent the state the decision turns on"
             % sorted(k for k, n in dest.items() if n > 0))
    else:
        v = "FIRES AND VARIES: applied, and reaching more than one destination"
    return {"cells": len(rows), "corrections_offered": corr, "corrections_changed": chg,
            "reverted_observe_only": obs, "corrections_applied_to_the_belief": applied,
            "destinations": dict(sorted(dest.items())),
            "host_reachable": bool(dest.get("belief_to_host", 0) > 0),
            "VERDICT": v}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sha", required=True, help="the LITERAL sha to read the repo at")
    ap.add_argument("--repo", default=".")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    rows = cells_at(a.sha, a.repo)
    by_arm: Dict[str, List[Dict[str, Any]]] = collections.defaultdict(list)
    for r in rows:
        by_arm[str(r["arm"])].append(r)

    res: Dict[str, Any] = {
        "_what": ("StudyD216-KV025 check 1: the per-cell count of residency-belief corrections "
                  "from engine-reported cached_tokens, and whether an eviction reaches a "
                  "decision through them"),
        "_register": ("OBSERVED. Every number is a counter written by coordinator.py:1799-1806 "
                      "into a committed LIVE cell's coordinator_result.json, read out of the git "
                      "object at the sha named below. Nothing here is constructed or predicted."),
        "_measured_at_sha": a.sha,
        "_the_gate": {
            "default": "LIVE2_BELIEF_CORRECTION=observe (coordinator.py:141)",
            "apply_when": ("the env var is 'apply' OR the arm declares live2_belief_apply "
                           "(coordinator.py:364-365). Only V6StateArm and its descendants do "
                           "(arms_v6state.py:165)"),
            "observe_semantics": ("the correction is computed and counted, then the belief and "
                                  "last_touch_s are RESTORED from a snapshot "
                                  "(coordinator.py:1803-1806). Nothing downstream sees it."),
        },
        "_the_reads_that_consume_it": {
            "rung2_and_rung3_pricing": [
                "coordinator.py:1161  TP.should_touch(belief=...) -> refuse or price the touch",
                "coordinator.py:1238  TP.build_price_gpu_s(..., belief) -> budget.can_spend",
                "coordinator.py:1294  C.recall_gpu_s(tokens, s.residency_readiness())",
                "coordinator.py:1331  the D179 (4) release re-check's uncached count",
                "arms_v6state.py:416  host_warm from roster['belief_by_session'] "
                "(coordinator.py:757) -> gates the RELOAD candidate in plan_state",
            ],
            "b7_feasibility": [
                "cstate.py:636/648    ready = s.readiness() -> RecallQuery.readiness",
                "baselines/constructed.py:184  est = C.recall_ttft_s(q.readiness_tokens, "
                "q.readiness); est <= slack admits, <= slack + defer_s defers, else REJECT",
            ],
        },
        "_host_is_unreachable_and_why": (
            "the `host` branch (engine_actions.py:381-383) requires `external_tokens`, and "
            "D209 (4) measured that vLLM 0.31.0's per-request usage schema has no field that "
            "distinguishes a host hit from a GPU hit: 26 percent of prompt tokens came from the "
            "host tier and all of them are folded into cached_tokens. So this corrector can say "
            "gpu or cold and never host, which is D211's finding reached from the counter side."),
        "per_cell": sorted(rows, key=lambda r: (str(r["arm"]), r["cell"])),
        "per_arm": {k: verdict(v) for k, v in sorted(by_arm.items())},
    }
    res["per_family"] = {
        "arms_that_APPLY_the_correction_rungs_2_and_above":
            verdict([r for r in rows
                     if any(str(r["arm"]).startswith(p) for p in APPLY_FAMILIES)]),
        "arms_that_do_NOT_rung_0_rung_1_and_every_paper_baseline":
            verdict([r for r in rows
                     if not any(str(r["arm"]).startswith(p) for p in APPLY_FAMILIES)]),
        "b7_edf_feasibility_alone": verdict(by_arm.get("b7-edf-feasibility", [])),
    }
    res["reduced_pool_cells"] = {
        "_why_this_table_exists": ("the ruling's sentence is about MEMORY PRESSURE, so the cells "
                                   "that matter are the ones at a reduced pool. This lists every "
                                   "committed live cell whose name carries a _kv suffix, with "
                                   "whether its arm applies the correction at all."),
        "cells": [{"cell": r["cell"], "arm": r["arm"],
                   "applies": bool(r["counts"]["belief_corrections_changed"]
                                   > r["counts"]["belief_corrections_observed_only"]),
                   "counts": r["counts"]}
                  for r in sorted(rows, key=lambda x: x["cell"]) if "_kv0." in r["cell"]],
    }
    with open(a.out, "w") as fh:
        json.dump(res, fh, indent=1)
    print("wrote %s: %d live cells" % (a.out, len(rows)))
    for k, v in res["per_family"].items():
        print("%-62s %s" % (k, v["VERDICT"][:110]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
