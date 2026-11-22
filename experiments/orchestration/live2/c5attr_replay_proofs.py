#!/usr/bin/env python3
"""C5 attribution candidate: does the rule CHANGE THE CAP TRAJECTORY on the committed live cells?

READ-ONLY. No cells are run. The committed request and outcome logs of the four rung-1 cells and
the four base cells are replayed through C5's own AIMD rule twice: as committed, and with the
candidate attribution rule. Nothing downstream is predicted.

REGISTER, and it is the whole honesty of this file. A replay holds the TRACE FIXED. A cap held
open would have released monitors that were never released, which would have changed every later
monitor first-token time, so this file reports a CAP TRAJECTORY under the rule and NOT a
submission count, an on-time share or any other outcome. The only claim is the Step 2b one: the
rule reaches the cap and is not inert. The live cells in runs/C5DIAG_CELLS are the only thing
that can carry an outcome.

CONTROLS, all three, because a replay that cannot fail proves nothing:
  positive  the committed trajectory must reproduce the base arm's OWN c5_increase / c5_decrease
            counters (the same control c5_loss_split.py established, within one count), and an
            ALWAYS-SUPPRESS variant must move the trajectory by a large margin, so the comparison
            is known to be able to see a difference at all;
  negative  a NEVER-SUPPRESS variant (the uncached threshold raised past any observed value) must
            reproduce the committed trajectory EXACTLY, so a difference under the real rule is
            the rule and not the replay;
  port      the count of suppressed halvings, the arm's characteristic decision. Zero means the
            rule is INERT on this workload and must be reported as such.

THE RULE replayed here is the one implemented in hybrid/hybrid_arm.py `_attr_suppresses`: on a
trip, if every monitor completion seen since the last cap adjustment that was itself slow
(first-token time > 0.8 s) overlapped a robot prefill the coordinator released with uncached >=
200 tokens, the halving is suppressed and the cap is HELD (the recovery timer is not restarted).

DEFINITION DIFFERENCE, DECLARED. The live arm reads the uncached count the COORDINATOR CHARGED at
release; this replay has only the engine's reported `prompt_tokens - cached_tokens` from the
request log. They are the same quantity measured on two sides of the release, and the committed
c5_loss_split.json ruling defines the bucket with the logged one, so the replay uses it and the
difference is stated rather than hidden.
"""
from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
RUNS = REPO / "results/orchestration/live2/frozen_test/runs"

PERIOD_S = 0.1
RUN_S = 1200.0
DASH_L_S = 1.0
AIMD_TRIP_S = 0.8 * DASH_L_S
EWMA_A = 0.3
CAP_FLOOR, CAP_CEIL = 4, 8
UNCACHED_MIN = 200
ARMS = ["hybrid-F-lhreq-noc3", "v5-rules-2"]
SEEDS = [4, 5, 6, 7]
TAG = "_n16_s%d_1200s_h27_3t_L3_epg_rq30"


def _rows(p: Path) -> List[Dict[str, Any]]:
    if not p.exists():
        return []
    with gzip.open(p, "rt") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def _trace(arm: str, seed: int) -> Optional[Dict[str, Any]]:
    d = RUNS / (arm + TAG % seed)
    if not d.exists():
        return None
    req = _rows(d / "request.jsonl.gz")
    out = _rows(d / "outcomes.jsonl.gz")
    cr = json.loads((d / "coordinator_result.json").read_text())
    kind_of = {o["opportunity_id"]: o["kind"] for o in out if o.get("opportunity_id")}
    prefills: List[Tuple[float, float, int]] = []
    upd: List[Tuple[float, float, float, float]] = []      # (t_done, ttft, t_submit, t_first)
    for r in req:
        opp = r.get("opportunity_id")
        k = kind_of.get(opp) if opp else "build"
        t0 = float(r["t_submit"])
        t1 = float(r.get("t_done") or t0)
        unc = max(int(r.get("prompt_tokens") or 0) - int(r.get("cached_tokens") or 0), 0)
        if k == "monitor":
            if r.get("t_first_token") and r.get("t_done"):
                tf = float(r["t_first_token"])
                upd.append((t1, tf - t0, t0, tf))
        elif unc >= UNCACHED_MIN:
            prefills.append((t0, t1, unc))
    upd.sort()
    prefills.sort()
    return {"cell": arm + TAG % seed, "updates": upd, "prefills": prefills,
            "recorded_decreases": (cr.get("arm_stats") or {}).get("c5_decrease"),
            "recorded_increases": (cr.get("arm_stats") or {}).get("c5_increase")}


def _overlaps(t0: float, t1: float, prefills) -> bool:
    for a, b, _u in prefills:
        if a > t1:
            break
        if b >= t0:
            return True
    return False


def _run(tr: Dict[str, Any], mode: str) -> Dict[str, Any]:
    """Replay the AIMD rule over this cell. mode: committed | attr | always | never."""
    n_ep = int(RUN_S / PERIOD_S)
    upd, pref = tr["updates"], tr["prefills"]
    cap, last_adj = CAP_CEIL, None
    caps = [CAP_CEIL] * n_ep
    lat, j = 0.0, 0
    pending: List[Tuple[float, bool]] = []
    n_dec = n_inc = n_sup = n_mixed = n_noev = 0
    for e in range(n_ep):
        t = e * PERIOD_S
        while j < len(upd) and upd[j][0] <= t:
            _td, v, m0, m1 = upd[j]
            lat = v if lat <= 0 else EWMA_A * v + (1 - EWMA_A) * lat
            if mode == "committed":
                pass
            elif mode == "always":
                pending.append((v, True))
            elif mode == "never":
                pending.append((v, False))
            else:
                pending.append((v, _overlaps(m0, m1, pref)))
            j += 1
        if lat > 0 and lat > AIMD_TRIP_S:
            if last_adj is None or t - last_adj >= 1.0:
                slow = [ov for v, ov in pending if v > AIMD_TRIP_S]
                if mode != "committed" and slow and all(slow):
                    n_sup += 1
                    caps[e] = cap
                    continue
                if mode != "committed":
                    if not slow:
                        n_noev += 1
                    else:
                        n_mixed += 1
                cap = max(CAP_FLOOR, cap // 2)
                n_dec += 1
                last_adj = t
                pending.clear()
        elif last_adj is None or t - last_adj >= 5.0:
            if cap < CAP_CEIL:
                cap += 1
                n_inc += 1
            last_adj = t
            pending.clear()
        caps[e] = cap
    return {"mode": mode, "decreases": n_dec, "increases": n_inc,
            "suppressed": n_sup, "trips_with_mixed_evidence": n_mixed,
            "trips_without_slow_evidence": n_noev,
            "epochs_at_floor": sum(1 for c in caps if c == CAP_FLOOR),
            "mean_cap": round(sum(caps) / len(caps), 4), "caps": caps}


def _compare(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    diff = [e for e, (x, y) in enumerate(zip(a["caps"], b["caps"])) if x != y]
    return {"epochs_with_a_different_cap": len(diff),
            "first_differing_epoch": (None if not diff else
                                      {"epoch": diff[0], "t_s": round(diff[0] * PERIOD_S, 2),
                                       "committed_cap": a["caps"][diff[0]],
                                       "candidate_cap": b["caps"][diff[0]]}),
            "epochs_at_floor": [a["epochs_at_floor"], b["epochs_at_floor"]],
            "mean_cap": [a["mean_cap"], b["mean_cap"]],
            "decreases": [a["decreases"], b["decreases"]],
            "increases": [a["increases"], b["increases"]]}


def main() -> int:
    out: Dict[str, Any] = {
        "_what": ("C5 attribution candidate (covex-v6-state-uo-c5attr): the rule's effect on the "
                  "AIMD cap trajectory, replayed on the committed live traces"),
        "_register": ("a CAP TRAJECTORY under the rule, on a FIXED trace. NOT an outcome, NOT a "
                      "submission count, NOT a headline. The trace cannot react to a cap that was "
                      "never applied"),
        "_rule": ("suppress the halving when every slow monitor (first token > 0.8 s) seen since "
                  "the last cap adjustment overlapped a robot prefill the coordinator released "
                  "with uncached >= 200 tokens; on suppression the cap is HELD"),
        "cells": [], }
    for arm in ARMS:
        for s in SEEDS:
            tr = _trace(arm, s)
            if tr is None:
                out["cells"].append({"cell": arm + TAG % s, "missing": True})
                continue
            com = _run(tr, "committed")
            att = _run(tr, "attr")
            alw = _run(tr, "always")
            nev = _run(tr, "never")
            row = {
                "cell": tr["cell"],
                "control_positive_reconstruction": {
                    "_claim": "the committed replay reproduces the arm's own AIMD counters",
                    "reconstructed": [com["decreases"], com["increases"]],
                    "arm_recorded": [tr["recorded_decreases"], tr["recorded_increases"]],
                    "within_one_count": (
                        None if tr["recorded_decreases"] is None else
                        bool(abs(com["decreases"] - tr["recorded_decreases"]) <= 1
                             and abs(com["increases"] - tr["recorded_increases"]) <= 1))},
                "control_negative_never_suppress": dict(
                    _claim=("with the rule present but never able to fire, the trajectory must be "
                            "the committed one exactly"),
                    identical=bool(nev["caps"] == com["caps"]),
                    **{k: v for k, v in _compare(com, nev).items()
                       if k in ("epochs_with_a_different_cap", "decreases")}),
                "control_positive_always_suppress": dict(
                    _claim="the check can see a difference at all",
                    **_compare(com, alw)),
                "candidate": {k: v for k, v in att.items() if k != "caps"},
                "committed": {k: v for k, v in com.items() if k != "caps"},
                "step2b_cap_trajectory": _compare(com, att),
            }
            out["cells"].append(row)
    live = [c for c in out["cells"] if not c.get("missing")]
    ctl_ok = all(c["control_positive_reconstruction"]["within_one_count"] in (True, None)
                 for c in live)
    neg_ok = all(c["control_negative_never_suppress"]["identical"] for c in live)
    pos_ok = all(c["control_positive_always_suppress"]["epochs_with_a_different_cap"] > 0
                 for c in live)
    rung = [c for c in live if c["cell"].startswith("v5-rules-2")]
    sup = [c["candidate"]["suppressed"] for c in rung]
    moved = [c["step2b_cap_trajectory"]["epochs_with_a_different_cap"] for c in rung]
    out["summary"] = {
        "controls": {"reconstruction_within_one_count": ctl_ok,
                     "never_suppress_identical": neg_ok,
                     "always_suppress_moves_the_trajectory": pos_ok},
        "rung1_cells": [c["cell"] for c in rung],
        "rung1_suppressed_halvings": sup,
        "rung1_epochs_with_a_different_cap": moved,
        "rung1_decreases_committed_vs_candidate": [
            c["step2b_cap_trajectory"]["decreases"] for c in rung],
        "rung1_epochs_at_floor_committed_vs_candidate": [
            c["step2b_cap_trajectory"]["epochs_at_floor"] for c in rung],
        "port_rule": ("the characteristic decision is a SUPPRESSED HALVING; it occurs %s times "
                      "per rung-1 cell" % sup if all(x > 0 for x in sup) else
                      "INERT on at least one rung-1 cell: %s" % sup),
    }
    out["verdict"] = (
        "PASS: controls hold and the rule moves the cap trajectory on every rung-1 cell"
        if (ctl_ok and neg_ok and pos_ok and all(x > 0 for x in sup) and all(x > 0 for x in moved))
        else "SEE summary.controls and summary.port_rule: a control failed or the rule is inert")
    dest = REPO / "results/orchestration/live2/frozen_test/c5attr_replay_proofs.json"
    dest.write_text(json.dumps(out, indent=1) + "\n")
    for c in live:
        print("%-58s sup=%-6d moved=%-6d dec %s->%s floor %s->%s" % (
            c["cell"][:58], c["candidate"]["suppressed"],
            c["step2b_cap_trajectory"]["epochs_with_a_different_cap"],
            c["committed"]["decreases"], c["candidate"]["decreases"],
            c["committed"]["epochs_at_floor"], c["candidate"]["epochs_at_floor"]))
    print(json.dumps(out["summary"]["controls"]))
    print(out["verdict"])
    print("wrote", dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
