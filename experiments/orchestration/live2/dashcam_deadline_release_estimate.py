#!/usr/bin/env python3
"""OFFLINE ESTIMATE of a third C5 candidate, DEADLINE-AWARE RELEASE. Read-only, no cells run.

USER RULING 2026-11-22, C5 PLAN item 2. NOTHING IS IMPLEMENTED. This script reads committed logs
and estimates what the rule could have reached had it been in the arm. It runs no cell, starts no
server and touches no policy code.

THE RULE BEING ESTIMATED. Do not release a dashcam monitor whose hold-so-far plus its predicted
first-token time already exceeds its 1.0 s deadline; the device answers it instead. Such a release
is DEAD ON ARRIVAL (DOA): it cannot meet its deadline at the moment it is sent, yet it occupies a
C5 in-flight slot for as long as the engine keeps it, so timely frames queue behind dead ones.

WHAT IS ALREADY ANSWERED AND IS NOT REDONE HERE (item 1, carried as context). The base's b7
feasibility rule does not stop these releases BECAUSE IT IS NEVER APPLIED TO MONITORS. In
`experiments/orchestration/live2/hybrid/hybrid_arm.py` the dashcam loop (lines 347 to 356)
computes `slack = dl - now - epi_s` at line 351 and then appends the item UNCONDITIONALLY at line
355. `it["slack"]` is read in exactly ONE place, line 443, inside the utility-per-cost ordering
index `idx(it)`, so it is an ORDERING TERM and never an admission test. The explicit feasibility
branch (`if est <= qs: CLOUD elif est <= qs + defer_s: DEFER else REJECT`) exists only in the
RECALL loop. Two further facts from that pass: `epi_s` at line 345 is
`C.episodic_cloud_latency_s("32BI", 1, 25)`, computed once per decision with FIXED arguments, so
it is a constant that cannot reflect live engine time or the episode's actual frame count; and
episode continuity (D149 (3)) is not implemented in that file at all, so it cannot be overriding
anything.

THE UNIT AND THE POPULATION, stated before any number.
  * The unit of (a) is one RELEASED MONITOR: a `kind == "monitor"` row of `outcomes.jsonl.gz`
    whose `cloud_payload.request_id` is set, is not in `score.refused_request_ids()`, and whose
    request row is present in `request.jsonl.gz`. That population is EXACTLY the one
    `dashcam_ontime_reconcile.json` sums as its four released buckets
    (on_time + late_at_release + late_at_first_token + late_at_forward_only), and this script
    asserts that equality per cell rather than assuming it.
  * HOLD AT RELEASE is `t_submit - t_opportunity`, the release delay that file already reports.
    It is the whole elapsed share of the deadline, which runs from `t_opportunity`.
  * The deadline is read per row from `outcomes.deadline_s` and asserted equal to 1.0 s.

TWO PREDICTORS OF "PREDICTED FIRST-TOKEN TIME", BOTH REPORTED, BECAUSE THE CHOICE IS LOAD-BEARING.
  (i) CONSTANT: the cell's own median monitor first-token time, which is what the user's 0.56 s
      threshold does (0.56 = 1.0 - 0.44, the base's measured median). DECLARED LIMITATION: a
      constant CANNOT DISTINGUISH REQUESTS. Under it the rule degenerates into a pure hold
      threshold, so it ranks nothing and will cut a 120-token frame released at 0.55 s on the
      same evidence as a 13,000-token one. Both the user's fixed 0.56 and each cell's own median
      are reported, because the base median (0.436 to 0.449) and the rung-2 median (0.482 to
      0.485) differ and the threshold moves with them.
 (ii) D162 MODEL: `first_token_s(uncached, uncached_queued_ahead)`, coefficients IMPORTED from
      `d162_price.py` (never retyped), which is the same one-price source the planner and the
      coordinator already read. It VARIES PER REQUEST, which (i) cannot, but IT IS A MODEL and
      not a measurement, and its two inputs are reconstructed (see PROXIES).
(iii) ORACLE, reported only as the consistency anchor and NOT as a candidate predictor: the
      request's OWN measured engine first-token time. No arm could have this at release. Its only
      job here is check 7: the DOA count under the oracle must equal the reconcile file's
      late_at_release + late_at_first_token exactly, and this script asserts it.

PROXIES, EVERY ONE DECLARED (consistency check 6).
  * `uncached = prompt_tokens - cached_tokens` is the ENGINE'S OBSERVED uncached count. The
    coordinator charges a PREDICTED uncached (`B.epg_prompt_tokens(n_new)`, or 378 off-EP-G,
    coordinator.py lines 821 to 828). Using the observed count gives the model its most
    favourable input and therefore makes predictor (ii) OPTIMISTIC about its own accuracy. It is
    not what a live rule would have had.
  * `uncached_queued_ahead` is reconstructed as the sum of observed `uncached` over every request
    (monitor and otherwise) with `t_submit <= t` and `t_done > t` at this request's own
    `t_submit`. The coordinator's live counter `_uncached_in_flight` has the same shape
    (coordinator.py lines 836, 970, 1035, 1082, decremented at 1386) but is accumulated on
    PREDICTED uncached. So this is an analogue of that counter, not the counter.
  * SLOT OCCUPANCY is `t_done - t_submit`. That is the right interval for the C5 cap and not a
    free choice: C5's budget is `max(self.cap - in_flight, 0)` (hybrid_arm.py line 456) where
    `in_flight` sums `obs.cloud.running_by_class`, which cstate builds from
    `self.in_flight["monitor"]` (cstate.py line 629); the coordinator INCREMENTS that at submit
    (coordinator.py line 1184) and DECREMENTS it only in `_collect` when the future is done
    (line 1300), i.e. at `t_done`. The first-token interval `t_cloud_done - t_submit` is reported
    beside it as `occupancy_to_first_token_s`, labelled as the ALTERNATIVE that the cap does NOT
    use, because a monitor is DELIVERED at its first token even though its slot is held to
    completion.
  * The mean cap per cell is NOT recomputed here. It is read from
    `dashcam_ontime_reconcile.json :: cells[*].cap_trajectory.mean_cap`, whose reconstruction was
    controlled there against each arm's own `c5_decrease` / `c5_increase` counters.

CACHING, a methodological parameter (CLAUDE.md). vLLM PREFIX CACHING WAS ENABLED in every cell
read, as the reconcile file records per cell from `vllm:prefix_cache_hits_total`. Every latency
here is a WARM-SERVER number under an arm-dependent hit pattern and none is a cold prefill. The
D162 coefficients were fitted on the same warm regime, so predictor (ii) is applied in the regime
it was fitted in.

THE EP-G CAVEAT, which the user states and which the arithmetic below honours (item 2d). A SKIPPED
FRAME IS STILL PREFILLED BY THE EPISODE'S NEXT REQUEST, because the episode context is append-only
under EP-G. SO THE SAVING IS SLOTS AND SCHEDULING, NOT THE FRAME'S PREFILL WORK. Nothing in (b) or
(c) claims prefill tokens saved: (b) is reported in SLOT-SECONDS of in-flight occupancy and is
explicitly NOT converted to GPU-seconds or to tokens, and (c) converts slot-seconds only into
further SLOT-SECONDS of a live monitor. The deferred tokens are reported separately, as a DEBT
that returns to the engine later rather than a saving.

WHAT (c) IS AND IS NOT. It is a CONSTRUCTED BOUND, not a prediction. Two reasons, written out:
  1. Releasing fewer monitors CHANGES THE QUEUE the remaining ones are served in, so the measured
     first-token times of the survivors would not be preserved. Every one of them was measured
     with the DOA requests in front of it.
  2. The C5 cap ITSELF would trip differently once the first-token distribution changes, because
     its AIMD input is an EWMA of exactly that distribution. That is a feedback loop this
     estimate cannot follow.
Both make the bound an upper bound in the direction of OPTIMISM about the rule.
"""
from __future__ import annotations

import argparse
import bisect
import gzip
import json
import os
import statistics
import subprocess
import sys

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
RUNS = REPO / "results/orchestration/live2/frozen_test/runs"
RECONCILE = REPO / "results/orchestration/live2/frozen_test/dashcam_ontime_reconcile.json"
OUT = REPO / "results/orchestration/live2/frozen_test/dashcam_deadline_release_estimate.json"
# Same convention as dashcam_ontime_reconcile.py and for the same reason: this analysis runs in a
# shared worktree whose detached HEAD another session parked off origin/main, so the
# covex-v6-state-uo directories are present on origin and not on disk. They were extracted from
# origin/main and every file read is blob-identical to origin/main's (verified, and the check is
# recorded in the output under `_run_provenance.runs_blob_check`). On a checkout of origin/main
# the variable is unnecessary.
RUNS_EXTRA = [Path(x) for x in os.environ.get("LIVE2_RUNS_EXTRA", "").split(":") if x]

sys.path.insert(0, str(HERE / "scorer"))
sys.path.insert(0, str(REPO / "experiments/lib"))
from score import refused_request_ids                                      # noqa: E402
from _provenance import stamp                                              # noqa: E402
import d162_price as DP                                                    # noqa: E402

DASH_L_S = 1.0
RUN_S = 1200.0
USER_MEDIAN_FT_S = 0.44        # the user's constant, from the BASE's measured median
USER_THRESHOLD_S = DASH_L_S - USER_MEDIAN_FT_S          # 0.56
TAG = "_n16_s%d_1200s_h27_3t_L3_epg_rq30"

RUNG2 = ["covex-v6-state-uo" + TAG % s for s in (4, 5, 6)]
BASE = ["hybrid-F-lhreq-noc3" + TAG % s for s in (4, 5, 6)]
CELLS = RUNG2 + BASE


def cell_dir(cell: str) -> Optional[Path]:
    for base in [RUNS] + RUNS_EXTRA:
        if (base / cell / "outcomes.jsonl.gz").exists():
            return base / cell
    return None


def _rows(p: Path) -> List[Dict[str, Any]]:
    with gzip.open(p, "rt") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def _q(xs: Sequence[float], p: float) -> Optional[float]:
    if not xs:
        return None
    s = sorted(xs)
    return round(s[min(int(p * len(s)), len(s) - 1)], 4)


def _spread(xs: Sequence[float], nd: int = 4) -> Dict[str, Any]:
    """Check 3: never a bare median. A constant advertises breakage, so distinct_values is shown
    on every distribution in this file."""
    if not xs:
        return {"n": 0}
    return {"n": len(xs), "min": round(min(xs), nd), "p25": _q(xs, .25), "p50": _q(xs, .5),
            "p75": _q(xs, .75), "p90": _q(xs, .9), "p99": _q(xs, .99),
            "max": round(max(xs), nd), "mean": round(statistics.fmean(xs), nd),
            "distinct_values": len({round(x, 6) for x in xs})}


def _blob_check(cell: str, d: Path) -> Dict[str, Any]:
    """Every run file read is checked blob-identical to origin/main. A run read from outside
    `runs/` is a provenance question and is answered rather than left implicit."""
    res: Dict[str, Any] = {}
    rel = "results/orchestration/live2/frozen_test/runs/%s" % cell
    for f in ("request.jsonl.gz", "outcomes.jsonl.gz", "coordinator_result.json"):
        try:
            a = subprocess.run(["git", "-C", str(REPO), "rev-parse",
                                "origin/main:%s/%s" % (rel, f)],
                               capture_output=True, text=True).stdout.strip()
            b = subprocess.run(["git", "-C", str(REPO), "hash-object", str(d / f)],
                               capture_output=True, text=True).stdout.strip()
            res[f] = {"origin_main": a or None, "read": b or None, "identical": bool(a) and a == b}
        except Exception as e:                                                   # noqa: BLE001
            res[f] = {"error": str(e)}
    return res


def _reconcile_cell(rec: Dict[str, Any], cell: str) -> Optional[Dict[str, Any]]:
    for c in rec.get("cells", []):
        if c.get("cell") == cell:
            return c
    return None


def analyse(cell: str, rec: Dict[str, Any]) -> Dict[str, Any]:
    d = cell_dir(cell)
    if d is None:
        return {"cell": cell, "missing": True,
                "note": "absent from runs/ and from LIVE2_RUNS_EXTRA; not waited for"}
    out = _rows(d / "outcomes.jsonl.gz")
    req = _rows(d / "request.jsonl.gz")
    cr = json.loads((d / "coordinator_result.json").read_text())
    refused = refused_request_ids(req)
    rc = _reconcile_cell(rec, cell) or {}

    by_rid = {r["request_id"]: r for r in req}
    by_opp: Dict[str, Dict[str, Any]] = {}
    for r in req:
        o = r.get("opportunity_id")
        if o is not None and o not in by_opp:
            by_opp[o] = r

    def _unc(r: Dict[str, Any]) -> int:
        return max(int(r.get("prompt_tokens") or 0) - int(r.get("cached_tokens") or 0), 0)

    # ---- the queued-ahead reconstruction, over EVERY request, as an event sweep -----------
    ev: List[Tuple[float, int]] = []
    for r in req:
        if r.get("t_submit") is None or r.get("t_done") is None:
            continue
        u = _unc(r)
        ev.append((float(r["t_submit"]), +u))
        ev.append((float(r["t_done"]), -u))
    ev.sort()

    def _queued_ahead_at(t: float) -> int:
        """pref[i] is the cumulative uncached in flight AFTER event i, so the value at t is the
        last event at or before t. Requests submitted at exactly t are counted, which is the
        conservative reading: the coordinator increments before it submits."""
        i = bisect.bisect_right(ev_t, t) - 1
        return pref[i] if i >= 0 else 0

    ev_t = [t for t, _ in ev]
    pref: List[int] = []
    acc = 0
    for _, dv in ev:
        acc += dv
        pref.append(acc)

    mon_opps = {o["opportunity_id"] for o in out if o.get("kind") == "monitor"}
    n_monitor_opportunities = len(mon_opps)

    rows: List[Dict[str, Any]] = []
    deadlines = set()
    not_released: List[Dict[str, Any]] = []
    for o in out:
        if o.get("kind") != "monitor":
            continue
        t0 = float(o["t_opportunity"])
        # `deadline_s` is RELATIVE to t_opportunity in this trace and is asserted equal to
        # DASH_L_S rather than assumed: a per-row deadline of anything else would make every
        # threshold in this file wrong.
        deadlines.add(round(float(o["deadline_s"]), 3))
        cp = o.get("cloud_payload") or {}
        rid = cp.get("request_id")
        if rid is None or rid in refused:
            if rid is None and o["opportunity_id"] not in by_opp:
                not_released.append({"opp": o["opportunity_id"], "t0": t0,
                                     "dev": o.get("device_id")})
            continue
        rr = by_rid.get(rid) or by_opp.get(o["opportunity_id"])
        if rr is None:
            continue
        t_sub = float(rr["t_submit"])
        t_done = float(rr["t_done"]) if rr.get("t_done") is not None else None
        tcd = float(o["t_cloud_done"]) if o.get("t_cloud_done") is not None else None
        tft = (float(rr["t_first_token"]) - t_sub) if rr.get("t_first_token") is not None else None
        u = _unc(rr)
        qa = _queued_ahead_at(t_sub)
        rows.append({
            "opp": o["opportunity_id"], "dev": o.get("device_id"),
            "t0": t0, "t_submit": t_sub, "t_done": t_done,
            "hold": t_sub - t0,
            "uncached": u, "queued_ahead": qa,
            "pred_d162": DP.first_token_s(u, qa),
            "ttft_measured": tft,
            "engine_ft_oracle": (tcd - t_sub) if tcd is not None else None,
            "t_delivered": float(o["t_delivered"]) if o.get("t_delivered") is not None else None,
            "occ_done": (t_done - t_sub) if t_done is not None else None,
            "occ_first_token": (tcd - t_sub) if tcd is not None else None,
        })

    n_rel = len(rows)
    med_ft = statistics.median([r["ttft_measured"] for r in rows
                                if r["ttft_measured"] is not None])

    # ---- (e) the control FIRST: the released population must be the reconcile file's -------
    b = rc.get("buckets") or {}
    rec_released = (b.get("on_time", 0) + b.get("late_at_release", 0)
                    + b.get("late_at_first_token", 0) + b.get("late_at_forward_only", 0))
    oracle_doa = sum(1 for r in rows
                     if r["engine_ft_oracle"] is not None
                     and r["hold"] + r["engine_ft_oracle"] > DASH_L_S + 1e-9)
    rec_oracle = b.get("late_at_release", 0) + b.get("late_at_first_token", 0)

    def _share(n: int) -> float:
        return round(n / n_rel, 4) if n_rel else 0.0

    tot_slot_seconds = sum(r["occ_done"] for r in rows if r["occ_done"] is not None)
    mean_cap = ((rc.get("cap_trajectory") or {}).get("mean_cap"))

    variants: Dict[str, Any] = {}

    def _variant(name: str, pred, note: str, hop: float = 0.0) -> None:
        doa = [r for r in rows if r["hold"] + pred(r) + hop > DASH_L_S + 1e-9]
        live = [r for r in rows if r["hold"] + pred(r) + hop <= DASH_L_S + 1e-9]
        # confusion against the ORACLE outcome (would this monitor in fact have missed?)
        tp = fp = fn = tn = 0
        for r in rows:
            flagged = r["hold"] + pred(r) + hop > DASH_L_S + 1e-9
            o = r["engine_ft_oracle"]
            missed = o is not None and r["hold"] + o > DASH_L_S + 1e-9
            if flagged and missed:
                tp += 1
            elif flagged and not missed:
                fp += 1
            elif (not flagged) and missed:
                fn += 1
            else:
                tn += 1
        occ = [r["occ_done"] for r in doa if r["occ_done"] is not None]
        occ_live = [r["occ_done"] for r in live if r["occ_done"] is not None]
        occ_ft = [r["occ_first_token"] for r in doa if r["occ_first_token"] is not None]
        variants[name] = {
            "_note": note,
            "doa": len(doa), "live": len(live),
            "doa_share_of_released": _share(len(doa)),
            "confusion_against_oracle_outcome": {
                "flagged_and_would_have_missed_TP": tp,
                "flagged_but_would_have_MET_FP": fp,
                "not_flagged_and_missed_FN": fn,
                "not_flagged_and_met_TN": tn,
                "precision": round(tp / (tp + fp), 4) if (tp + fp) else None,
                "recall": round(tp / (tp + fn), 4) if (tp + fn) else None,
                "_reading": ("FP counts monitors the rule would have CUT that in fact arrived on "
                             "time. They are the cost of the rule and are NOT netted off any "
                             "number in this file."),
            },
            "cap_slot_seconds_freed": round(sum(occ), 3),
            "cap_slot_seconds_freed_share_of_all_monitor_slot_seconds": (
                round(sum(occ) / tot_slot_seconds, 4) if tot_slot_seconds else None),
            "cap_slot_seconds_freed_share_of_wall_times_mean_cap": (
                round(sum(occ) / (RUN_S * mean_cap), 4) if mean_cap else None),
            "_share_denominators": ("the first denominator is the slot-seconds ALL released "
                                    "monitors occupied in this cell; the second is wall clock "
                                    "(1200 s) times the mean reconstructed C5 cap, which is the "
                                    "run's whole in-flight capacity and is shared with recall and "
                                    "warming work, so the second share is not a share of a "
                                    "dashcam-only resource"),
            "slot_seconds_doa": _spread(occ, 3),
            "slot_seconds_live": _spread(occ_live, 3),
            "occupancy_to_first_token_s_doa_ALTERNATIVE_NOT_USED": _spread(occ_ft, 3),
            "mean_live_occupancy_s": round(statistics.fmean(occ_live), 4) if occ_live else None,
            "deferred_uncached_tokens_A_DEBT_NOT_A_SAVING": sum(r["uncached"] for r in doa),
        }
        variants[name]["_doa_rows"] = [(r["t_done"], r["hold"]) for r in doa
                                       if r["t_done"] is not None]

    _variant("const_user_0.44", lambda r: USER_MEDIAN_FT_S,
             "predictor (i) with the USER'S constant 0.44 s, i.e. the hold threshold 0.56 s. A "
             "CONSTANT: it cannot distinguish requests.")
    _variant("const_cell_own_median", lambda r: med_ft,
             "predictor (i) with THIS CELL'S own median monitor first-token time (%.4f s), "
             "threshold %.4f s. Still a constant." % (med_ft, DASH_L_S - med_ft))
    _variant("d162_model", lambda r: r["pred_d162"],
             "predictor (ii), the committed D162 model on this request's own observed uncached "
             "and the reconstructed queued-ahead. VARIES per request but IS A MODEL.")
    _variant("oracle_measured_engine_first_token",
             lambda r: (r["engine_ft_oracle"] if r["engine_ft_oracle"] is not None else 0.0),
             "NOT A CANDIDATE PREDICTOR. The request's own measured engine first token, which no "
             "arm has at release. Reported only as the consistency anchor for check 7.")
    _variant("const_user_0.44_plus_forward_hop", lambda r: USER_MEDIAN_FT_S,
             "SENSITIVITY: the committed scorer delivers at first token PLUS a 0.0222 s forward "
             "hop, so a rule that ignores the hop is slightly lenient. Same constant, deadline "
             "effectively 0.9778 s.", hop=0.0222)

    # ---- (c) the CONSTRUCTED BOUND ---------------------------------------------------------
    nr = sorted(not_released, key=lambda x: x["t0"])
    bounds: Dict[str, Any] = {}
    for vname in ("const_user_0.44", "const_cell_own_median", "d162_model"):
        v = variants[vname]
        freed = v["cap_slot_seconds_freed"]
        mlo = v["mean_live_occupancy_s"]
        term1 = (freed / mlo) if mlo else None
        # term 2: a one-to-one greedy match of each FREED SLOT INSTANT (a DOA request's t_done)
        # to a not-released opportunity that was STILL INSIDE ITS DEADLINE at that instant, under
        # the SAME predictor. A slot can take at most one, and an opportunity at most one slot.
        frees = sorted(t for t, _h in v["_doa_rows"])
        pred_const = (USER_MEDIAN_FT_S if vname == "const_user_0.44"
                      else med_ft if vname == "const_cell_own_median" else None)
        used = [False] * len(nr)
        matched = 0
        t0s = [x["t0"] for x in nr]
        for tf in frees:
            if pred_const is not None:
                pr = pred_const
            else:
                # the D162 variant prices the HYPOTHETICAL release at the cell's median monitor
                # uncached count and the queue actually in flight at tf. DECLARED: a model applied
                # to a request that did not happen, which is one reason the whole quantity is a
                # bound and not a prediction.
                pr = DP.first_token_s(int(round(med_unc)), _queued_ahead_at(tf))
            # an opportunity is eligible at tf if it has already arisen (t0 <= tf) and a release
            # at tf would still land a first token inside its deadline (tf + pr <= t0 + 1.0)
            hi = bisect.bisect_right(t0s, tf)
            lo = bisect.bisect_left(t0s, tf + pr - DASH_L_S)
            for i in range(max(lo, 0), hi):
                if not used[i] and tf + pr <= nr[i]["t0"] + DASH_L_S:
                    used[i] = True
                    matched += 1
                    break
        fp = v["confusion_against_oracle_outcome"]["flagged_but_would_have_MET_FP"]
        bounds[vname] = {
            "_register": "CONSTRUCTED BOUND, not a prediction",
            "freed_slot_seconds": freed,
            "offset_on_time_instants_the_rule_WOULD_ITSELF_DESTROY": fp,
            "_offset_note": ("these are monitors the predictor flags as DOA that in fact arrived "
                             "inside the deadline. They are a DIRECT LOSS the rule causes and are "
                             "reported here rather than netted off the bound, because the bound "
                             "and the offset are different registers: the bound is constructed "
                             "and the offset is an OBSERVED COUNT. A reader who wants one number "
                             "should subtract it and keep the bound label."),
            "bound_minus_offset_STILL_A_BOUND": (int(min(term1, matched)) - fp
                                                 if term1 is not None else None),
            "mean_live_monitor_occupancy_s": mlo,
            "term1_freed_slot_seconds_over_mean_live_occupancy": (round(term1, 1)
                                                                  if term1 else None),
            "term2_not_released_opportunities_still_inside_deadline_at_a_freed_slot": matched,
            "not_released_total": len(nr),
            "upper_bound_on_time_instants_recoverable": (int(min(term1, matched))
                                                         if term1 is not None else None),
            "as_share_of_monitor_opportunities": (
                round(min(term1, matched) / n_monitor_opportunities, 4)
                if term1 is not None and n_monitor_opportunities else None),
            "committed_on_time": b.get("on_time"),
            "bound_as_share_of_committed_on_time": (
                round(min(term1, matched) / b["on_time"], 4)
                if term1 is not None and b.get("on_time") else None),
            "_arithmetic": ("upper bound = min( freed_slot_seconds / mean_live_occupancy_s , "
                            "one-to-one greedy matches of freed-slot instants to not-released "
                            "opportunities still inside their deadline ). Both terms are upper "
                            "bounds in the direction of optimism about the rule."),
            "_why_not_a_prediction": [
                "releasing fewer monitors changes the queue the survivors are served in, so their "
                "measured first-token times would NOT be preserved; every one was measured with "
                "the DOA requests in front of it",
                "the C5 cap's own AIMD input is an EWMA of that same first-token distribution, so "
                "the cap would trip differently once the distribution changes: a feedback loop "
                "this estimate cannot follow",
                "term 2 prices a counterfactual release with a model (predictor ii) or a constant "
                "(predictor i), never with a measurement, because the release did not happen",
                "EP-G: the skipped frame is still prefilled by the episode's next request, so no "
                "prefill work is freed and the freed slot-seconds overstate the GPU time freed",
                "the C5 budget is `cap - in_flight` where in_flight sums ALL classes "
                "(running_by_class recall + episodic, cstate.py:626), so a freed slot is not "
                "reserved for dashcam: it could be taken by recall or warming work instead. This "
                "construction assigns every freed slot to dashcam, which is optimistic for the "
                "dashcam axis, and it OMITS any robot-side gain, so it is not a bound on the "
                "run's total improvement in either direction",
                "term 2 allows at most ONE recovered opportunity per freed-slot instant even "
                "though the DOA request held its slot for a whole interval. That makes term 2 "
                "tighter than term 1 but it is still a matching on a frozen timeline, not a "
                "schedule",
            ],
        }

    for v in variants.values():
        v.pop("_doa_rows", None)

    # ---- one traced unit, readable by a person checking the arithmetic by hand -------------
    doa_rows = sorted([r for r in rows
                       if r["hold"] + USER_MEDIAN_FT_S > DASH_L_S and r["occ_done"] is not None],
                      key=lambda r: r["hold"])
    tr = doa_rows[len(doa_rows) // 2] if doa_rows else None
    traced = None
    if tr is not None:
        traced = {
            "_what": ("one DOA monitor at the MEDIAN hold of this cell's DOA population. Every "
                      "quantity the rule and the estimate use, with the arithmetic shown."),
            "opportunity_id": tr["opp"], "device_id": tr["dev"],
            "t_opportunity": round(tr["t0"], 6), "deadline_s": DASH_L_S,
            "t_submit": round(tr["t_submit"], 6),
            "hold_at_release_s": round(tr["hold"], 4),
            "deadline_remaining_at_release_s": round(DASH_L_S - tr["hold"], 4),
            "prompt_minus_cached_uncached_tokens": tr["uncached"],
            "queued_ahead_uncached_tokens_RECONSTRUCTED": tr["queued_ahead"],
            "predictor_i_constant_user_s": USER_MEDIAN_FT_S,
            "predictor_i_constant_cell_median_s": round(med_ft, 4),
            "predictor_ii_d162_s": round(tr["pred_d162"], 4),
            "predictor_ii_arithmetic": ("%.6f + %.10f * %d + %.10f * %d = %.4f"
                                        % (DP.INTERCEPT_S, DP.PER_UNCACHED_S, tr["uncached"],
                                           DP.PER_QUEUE_S, tr["queued_ahead"], tr["pred_d162"])),
            "measured_engine_first_token_s": (round(tr["ttft_measured"], 4)
                                              if tr["ttft_measured"] is not None else None),
            "doa_under_i_user": tr["hold"] + USER_MEDIAN_FT_S > DASH_L_S,
            "doa_under_ii_d162": tr["hold"] + tr["pred_d162"] > DASH_L_S,
            "doa_under_oracle": (tr["engine_ft_oracle"] is not None
                                 and tr["hold"] + tr["engine_ft_oracle"] > DASH_L_S),
            "t_done": round(tr["t_done"], 6) if tr["t_done"] is not None else None,
            "slot_seconds_this_request_occupied": round(tr["occ_done"], 4),
            "slot_seconds_to_first_token_ALTERNATIVE_NOT_USED": (
                round(tr["occ_first_token"], 4) if tr["occ_first_token"] is not None else None),
            "t_delivered_age_s": (round(tr["t_delivered"] - tr["t0"], 4)
                                  if tr["t_delivered"] is not None else None),
            "outcome": ("latency_miss: delivered age %.4f s against a 1.0 s deadline"
                        % (tr["t_delivered"] - tr["t0"])
                        if tr["t_delivered"] is not None and tr["t_delivered"] - tr["t0"] > DASH_L_S
                        else "both_met"),
            "what_bound_it": ("RELEASE DELAY: %.0f percent of the deadline was already spent "
                              "before the engine saw the request, and the engine's own first "
                              "token then needed %.4f s more. Neither the KV budget nor the "
                              "accelerator budget refused it: this cell's "
                              "budget_refusal_monitor is %s."
                              % (100.0 * tr["hold"] / DASH_L_S,
                                 tr["ttft_measured"] if tr["ttft_measured"] is not None else -1,
                                 ((cr.get("counts") or {}).get("budget_refusal_monitor")
                                  if "budget_refusal_monitor" in (cr.get("counts") or {})
                                  else "ABSENT, and an absent Counter key is zero"))),
            "what_the_rule_would_have_done": ("not released it; the device answers. The slot it "
                                              "held for %.4f s is freed, and under EP-G its "
                                              "%d uncached tokens are STILL prefilled by the "
                                              "episode's next request, so no prefill work is "
                                              "saved."
                                              % (tr["occ_done"], tr["uncached"])),
        }

    wall = RUN_S

    return {
        "cell": cell,
        "arm": cell.split("_n16_")[0],
        "seed": int(cell.split("_s")[1].split("_")[0]),
        "is_base": cell in BASE,
        "monitor_opportunities": n_monitor_opportunities,
        "released_monitors_with_a_request_row": n_rel,
        "deadline_s_distinct": sorted(deadlines)[:4],
        "measured_monitor_first_token_s": _spread([r["ttft_measured"] for r in rows
                                                   if r["ttft_measured"] is not None]),
        "hold_at_release_s": _spread([r["hold"] for r in rows]),
        "monitor_uncached_tokens": _spread([float(r["uncached"]) for r in rows], 1),
        "queued_ahead_uncached_tokens_RECONSTRUCTED": _spread(
            [float(r["queued_ahead"]) for r in rows], 1),
        "d162_predicted_first_token_s": _spread([r["pred_d162"] for r in rows]),
        "variants": variants,
        "traced_unit": traced,
        "constructed_bounds": bounds,
        "slot_seconds": {
            "_which_interval": ("t_done - t_submit. The C5 cap counts in_flight['monitor'], "
                                "incremented at submit (coordinator.py:1184) and decremented in "
                                "_collect when the future completes (coordinator.py:1300), so the "
                                "slot is held to t_done and not to the first token."),
            "all_released_monitors_total_slot_seconds": round(tot_slot_seconds, 3),
            "mean_cap_from_reconcile_cap_trajectory": mean_cap,
            "wall_clock_s": wall,
            "run_slot_second_capacity_wall_times_mean_cap": (round(wall * mean_cap, 1)
                                                             if mean_cap else None),
            "monitor_share_of_that_capacity": (round(tot_slot_seconds / (wall * mean_cap), 4)
                                               if mean_cap else None),
        },
        "control_e": {
            "_claim_1": ("the released population must equal dashcam_ontime_reconcile.json's four "
                         "released buckets, zero tolerance"),
            "reconcile_released": rec_released,
            "this_run_released": n_rel,
            "pass_1": rec_released == n_rel,
            "_claim_2": ("the DOA count under the ORACLE predictor must equal that file's "
                         "late_at_release + late_at_first_token, zero tolerance: a monitor whose "
                         "hold plus its own measured engine first token exceeds 1.0 s is exactly "
                         "one that missed at or before its first token"),
            "reconcile_late_at_release_plus_late_at_first_token": rec_oracle,
            "this_run_oracle_doa": oracle_doa,
            "pass_2": rec_oracle == oracle_doa,
            "_claim_3": ("hold > 1.0 s must equal that file's late_at_release bucket: the user's "
                         "'released after the whole deadline had already passed' figure"),
            "reconcile_late_at_release": b.get("late_at_release"),
            "this_run_hold_over_deadline": sum(1 for r in rows if r["hold"] > DASH_L_S),
            "pass_3": b.get("late_at_release") == sum(1 for r in rows if r["hold"] > DASH_L_S),
            "_claim_4": ("every monitor row's own deadline_s must be 1.0 s, read not assumed: a "
                         "per-row deadline of anything else makes every threshold here wrong"),
            "deadline_s_distinct": sorted(deadlines),
            "pass_4": sorted(deadlines) == [DASH_L_S],
        },
        "user_figures": {
            "share_held_over_0.56_s_at_release": _share(
                sum(1 for r in rows if r["hold"] > USER_THRESHOLD_S)),
            "share_held_over_the_whole_1.0_s_deadline": _share(
                sum(1 for r in rows if r["hold"] > DASH_L_S)),
        },
        "prefix_caching": (rc.get("prefix_caching") or {}),
        "runs_blob_check": _blob_check(cell, d),
        "coordinator_counts_monitor": {
            "submitted_monitor": (cr.get("counts") or {}).get("submitted_monitor"),
            "budget_refusal_monitor": (cr.get("counts") or {}).get("budget_refusal_monitor"),
            "c5_dash_held": (cr.get("arm_stats") or {}).get("c5_dash_held"),
            "c5_decrease": (cr.get("arm_stats") or {}).get("c5_decrease"),
        },
    }


med_unc = 376.0     # set per cell inside main(); the module-level value is the measured median
                    # monitor uncached count and is overwritten before any bound is computed


def main() -> None:
    global med_unc
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()
    rec = json.loads(RECONCILE.read_text())

    cells = []
    for c in CELLS:
        d = cell_dir(c)
        if d is not None:
            req = _rows(d / "request.jsonl.gz")
            mo = {o["opportunity_id"] for o in _rows(d / "outcomes.jsonl.gz")
                  if o.get("kind") == "monitor"}
            us = [max(int(r.get("prompt_tokens") or 0) - int(r.get("cached_tokens") or 0), 0)
                  for r in req if r.get("opportunity_id") in mo]
            med_unc = statistics.median(us) if us else 376.0
        cells.append(analyse(c, rec))

    ok = [c for c in cells if not c.get("missing")]
    res: Dict[str, Any] = {
        "_what": ("OFFLINE ESTIMATE of the third C5 candidate, DEADLINE-AWARE RELEASE (user "
                  "ruling 2026-11-22, item 2). NOTHING IS IMPLEMENTED. No cell was run, no "
                  "server started, no policy code touched."),
        "_register": ("ESTIMATE from committed logs. Item (c) is a CONSTRUCTED BOUND and is "
                      "labelled as such at every point of use, never a prediction."),
        "_the_rule": ("do not release a dashcam monitor whose hold-so-far (t_submit - "
                      "t_opportunity) plus its predicted first-token time already exceeds its "
                      "1.0 s deadline; the device answers it instead"),
        "_item_1_carried_as_context_not_redone": {
            "finding": ("the base's b7 feasibility rule never fires on monitors: hybrid_arm.py "
                        "line 351 computes slack and line 355 appends unconditionally; "
                        "it['slack'] is read only at line 443 inside the utility-per-cost "
                        "ordering index, so it is an ORDERING term and never an admission test. "
                        "The CLOUD / DEFER / REJECT feasibility branch exists only in the recall "
                        "loop."),
            "epi_s": ("hybrid_arm.py line 345: C.episodic_cloud_latency_s('32BI', 1, 25), FIXED "
                      "arguments once per decision, so it is a constant that cannot reflect live "
                      "engine time or the episode's frame count"),
            "episode_continuity_D149_3": "not implemented in hybrid_arm.py, so it overrides nothing",
        },
        "_proxies_declared": {
            "uncached": ("prompt_tokens - cached_tokens, the ENGINE'S OBSERVED count. The "
                         "coordinator charges a PREDICTED count, so predictor (ii) is given its "
                         "most favourable input and is optimistic about its own accuracy."),
            "uncached_queued_ahead": ("reconstructed as the sum of observed uncached over all "
                                      "requests in flight at this request's t_submit. An "
                                      "analogue of the coordinator's _uncached_in_flight, which "
                                      "accumulates PREDICTED uncached, not that counter."),
            "slot_occupancy": ("t_done - t_submit, because the C5 cap's in_flight['monitor'] is "
                               "decremented in _collect at future completion. The first-token "
                               "interval is reported beside it and is NOT what the cap uses."),
            "mean_cap": ("read from dashcam_ontime_reconcile.json's cap_trajectory, whose "
                         "reconstruction was controlled there against each arm's own c5_decrease "
                         "and c5_increase counters. Not recomputed here."),
            "term2_of_the_bound": ("prices a counterfactual release with the same predictor and "
                                   "the cell's median monitor uncached count. A model on a "
                                   "request that did not happen."),
        },
        "_predictors": {
            "i_constant": ("the cell's own median monitor first-token time, or the user's 0.44 s. "
                           "A CONSTANT, so it CANNOT DISTINGUISH REQUESTS: the rule degenerates "
                           "to a pure hold threshold and treats a 120-token frame and a "
                           "13,000-token one identically."),
            "ii_d162_model": ("first_token_s = %.17f + %.19f * uncached + %.19f * "
                              "uncached_queued_ahead, IMPORTED from d162_price.py (%s). It VARIES "
                              "PER REQUEST, which (i) cannot, but IT IS A MODEL, fitted on warm "
                              "prefix-cached cells, and its inputs here are reconstructed."
                              % (DP.INTERCEPT_S, DP.PER_UNCACHED_S, DP.PER_QUEUE_S, DP.SOURCE)),
            "iii_oracle": ("the request's own measured engine first token. NOT a candidate: no "
                           "arm has it at release. Its only role is the check-7 anchor."),
            "d162_drift_check_at_import": DP._check_against_gate(),
        },
        "_epg_caveat_item_d": (
            "A SKIPPED FRAME IS STILL PREFILLED BY THE EPISODE'S NEXT REQUEST, because the "
            "episode context is append-only under EP-G. THE SAVING IS SLOTS AND SCHEDULING, NOT "
            "THE FRAME'S PREFILL WORK. Accordingly: (b) is reported in SLOT-SECONDS of in-flight "
            "occupancy and is never converted to GPU-seconds or to tokens; (c) converts "
            "slot-seconds only into further slot-seconds of a live monitor; and the DOA requests' "
            "uncached tokens are reported as "
            "`deferred_uncached_tokens_A_DEBT_NOT_A_SAVING`, which returns to the engine on the "
            "episode's next request rather than being saved. No claim of prefill tokens saved is "
            "made anywhere in this file."),
        "_caching": ("vLLM PREFIX CACHING WAS ENABLED in every cell read, per each cell's own "
                     "prefix_caching block. Every latency is a WARM-SERVER number; none is a cold "
                     "prefill. The D162 coefficients were fitted in the same warm regime."),
        "cells": cells,
    }

    # ---------- the four user figures, reproduced or not ----------------------------------
    def _get(cell: str, path: Sequence[str]) -> Any:
        for c in ok:
            if c["cell"] == cell:
                v: Any = c
                for k in path:
                    v = v[k]
                return v
        return None

    uo4, b4 = RUNG2[0], BASE[0]
    res["user_figures_verification"] = {
        "_what": ("the four figures in the user's own measurement, verified from the logs rather "
                  "than trusted. The denominator is RELEASED monitors, which is what reproduces "
                  "them; over all monitor opportunities they would be smaller."),
        "rows": [
            {"figure": "rung-2 uo s4: share of SENT rung-2 monitors already unable to meet the "
                       "deadline at release (held > 0.56 s)",
             "user": 0.68, "this_run": _get(uo4, ["user_figures",
                                                  "share_held_over_0.56_s_at_release"])},
            {"figure": "base s4: same quantity", "user": 0.34,
             "this_run": _get(b4, ["user_figures", "share_held_over_0.56_s_at_release"])},
            {"figure": "rung-2 uo s4: released after the whole 1.0 s deadline had passed",
             "user": 0.03, "this_run": _get(uo4, ["user_figures",
                                                  "share_held_over_the_whole_1.0_s_deadline"])},
            {"figure": "base s4: same quantity", "user": 0.01,
             "this_run": _get(b4, ["user_figures",
                                   "share_held_over_the_whole_1.0_s_deadline"])},
        ],
        "median_engine_first_token_s_per_cell": {c["cell"]: c["measured_monitor_first_token_s"]
                                                 ["p50"] for c in ok},
        "note_on_0.44": ("the user's constant 0.44 s is the BASE's median monitor first-token "
                         "time (0.4385 to 0.4485 measured here). The rung-2 cells' own median is "
                         "0.4825 to 0.4847, so applying 0.56 s to a rung-2 cell uses a threshold "
                         "0.017 s to 0.020 s more lenient than that cell's own median implies. "
                         "Both are reported per cell."),
    }

    # ---------- the three-candidate comparison, measured quantities only -------------------
    res["three_candidate_comparison"] = {
        "_what": ("item 3: what each candidate addresses and what it cannot, using only measured "
                  "quantities. NO RECOMMENDATION IS MADE; the user rules."),
        "_no_recommendation": True,
        "rows": [
            {"candidate": "A. c5attr, the C5 attribution rule",
             "what_it_addresses": ("suppresses a C5 halving whose slow-monitor evidence overlaps "
                                   "work the coordinator itself released"),
             "measured_reach": ("63.4 and 63.7 percent of rung-2 halvings fire on evidence "
                                "attributable to our own released work (uo s4 / s5), against "
                                "50.7 to 54.7 percent at rung 1"),
             "what_it_cannot_do": ("19.2 and 16.3 percent of rung-2 halvings are trips where the "
                                   "EWMA exceeded 0.8 s while NO individual pending monitor did, "
                                   "which the rule does not suppress by design; 17 to 19 "
                                   "halvings per cell fire on monitors that overlapped nothing "
                                   "of ours"),
             "measured_fragility": ("the attributable share falls to 14.3 and 19.0 percent if the "
                                    "overlap threshold moves from 200 to 2,000 uncached tokens, "
                                    "so most of what it attributes is many small prefills "
                                    "(median uncached 1,372 to 1,398), not the few 3,071-token "
                                    "warm builds"),
             "register": "its own analysis, static share plus a cap-trajectory replay; NO OUTCOME",
             "source": "reports/study_c5_candidates.md, c5attr_trip_attribution.json"},
            {"candidate": "B. deadline-aware release",
             "what_it_addresses": ("the slot a monitor occupies when it was already infeasible at "
                                   "release: the held -> dead -> slot -> held cycle"),
             "measured_reach": "see `headline` in this file",
             "what_it_cannot_do": ([
                 "it does not reduce PREFILL WORK: under EP-G the skipped frame is prefilled by "
                 "the episode's next request anyway",
                 "it cannot reach the NOT-RELEASED bucket, which is 30.6 / 29.1 / 26.3 percent of "
                 "rung-2 monitor opportunities and the larger loss; it only stops bad releases",
                 "under predictor (i) it cannot distinguish requests at all, so it is a hold "
                 "threshold and its false positives are monitors that in fact arrived on time",
                 "it cannot be scored as an outcome offline: the queue the survivors are served "
                 "in, and the cap's own AIMD trajectory, both change under it"]),
             "measured_fragility": ("the DOA share moves with the predictor and with the "
                                    "threshold constant; both are reported per cell"),
             "register": "OFFLINE ESTIMATE, with a CONSTRUCTED BOUND for the recoverable instants",
             "source": "this file"},
            {"candidate": "C. a deadline-derived C5 set point",
             "what_it_addresses": ("the trip threshold itself: C5 halves on an EWMA crossing of "
                                   "0.8 s, and 0.8 s sits almost exactly at the p90 of its own "
                                   "input"),
             "measured_reach": ("monitor first-token p90 is 0.8374 / 0.8063 / 0.7956 at uo s4 / "
                                "s5 / s6, straddling the 0.8 s trip, while p50 is flat at 0.483 "
                                "(0.4831 / 0.4825 / 0.4847). So the trip is set where its input's "
                                "tail is, and a 0.0374 s move in the tail moves the arm across it"),
             "what_it_cannot_do": ("it changes WHEN the cap reacts, not what the cap reacts to: "
                                   "the loss that the reconcile file attributes to release delay "
                                   "inside the coordinator (hold p50 0.742 / 0.724 / 0.572 "
                                   "against the base's 0.201 to 0.362) is upstream of the trip. "
                                   "No set point was measured here and no arm was built."),
             "measured_fragility": ("the p90 straddles the trip across seeds, so any set point "
                                    "derived from one seed's tail is a one-seed quantity"),
             "register": ("MOTIVATED BY A MEASUREMENT ONLY. No candidate rule, no arm, no "
                          "estimate; it is the weakest-specified of the three"),
             "source": "dashcam_ontime_reconcile.json latency_components_s per cell"},
        ],
    }

    # ---------- headline, per predictor, per cell ------------------------------------------
    res["headline"] = {
        "_register": ("DOA shares are OBSERVED COUNTS over released monitors. The recoverable "
                      "instants are a CONSTRUCTED BOUND and carry that label at every use."),
        "doa_share_of_released": {
            v: {c["cell"]: c["variants"][v]["doa_share_of_released"] for c in ok}
            for v in ("const_user_0.44", "const_cell_own_median", "d162_model",
                      "oracle_measured_engine_first_token")},
        "cap_slot_seconds_freed": {
            v: {c["cell"]: c["variants"][v]["cap_slot_seconds_freed"] for c in ok}
            for v in ("const_user_0.44", "const_cell_own_median", "d162_model")},
        "upper_bound_on_time_instants_recoverable_CONSTRUCTED_BOUND": {
            v: {c["cell"]: c["constructed_bounds"][v]
                ["upper_bound_on_time_instants_recoverable"] for c in ok}
            for v in ("const_user_0.44", "const_cell_own_median", "d162_model")},
        "offset_on_time_instants_the_rule_would_itself_destroy_OBSERVED_COUNT": {
            v: {c["cell"]: c["constructed_bounds"][v]
                ["offset_on_time_instants_the_rule_WOULD_ITSELF_DESTROY"] for c in ok}
            for v in ("const_user_0.44", "const_cell_own_median", "d162_model")},
        "control_e_all_pass": all(c["control_e"]["pass_1"] and c["control_e"]["pass_2"]
                                  and c["control_e"]["pass_3"] and c["control_e"]["pass_4"]
                                  for c in ok),
    }

    res["consistency_check"] = {
        "1_cross_check_against_committed": {
            "rows": [{"quantity": "released monitors", "cell": c["cell"],
                      "this_run": c["released_monitors_with_a_request_row"],
                      "prior": c["control_e"]["reconcile_released"],
                      "source_of_prior": "dashcam_ontime_reconcile.json four released buckets",
                      "ratio": 1.0, "agree": c["control_e"]["pass_1"]} for c in ok]
                    + [{"quantity": "late_at_release count", "cell": c["cell"],
                        "this_run": c["control_e"]["this_run_hold_over_deadline"],
                        "prior": c["control_e"]["reconcile_late_at_release"],
                        "source_of_prior": "dashcam_ontime_reconcile.json",
                        "ratio": 1.0, "agree": c["control_e"]["pass_3"]} for c in ok]
                    + [{"quantity": "DOA under the oracle predictor", "cell": c["cell"],
                        "this_run": c["control_e"]["this_run_oracle_doa"],
                        "prior": c["control_e"]
                        ["reconcile_late_at_release_plus_late_at_first_token"],
                        "source_of_prior": ("dashcam_ontime_reconcile.json late_at_release + "
                                            "late_at_first_token"),
                        "ratio": 1.0, "agree": c["control_e"]["pass_2"]} for c in ok],
            "verdict": ("every quantity this run measures that was measured before is EXACT "
                        "against the prior committed value, zero tolerance, on all 6 cells"
                        if res["headline"]["control_e_all_pass"] else
                        "A CHECK FAILED; see control_e per cell. The classifier is wrong and the "
                        "rung-2 numbers may not be read."),
        },
        "2_physical_plausibility": {
            "_what": ("every rate implied here is checked against the committed curves rather "
                      "than left as a latency"),
            "d162_per_uncached_rate_tok_s": round(1.0 / DP.PER_UNCACHED_S, 0),
            "committed_cold_prefill_tok_s": 5600,
            "ratio": round((1.0 / DP.PER_UNCACHED_S) / 5600.0, 3),
            "verdict": ("the D162 per-uncached term implies 5,482 tok/s against the committed "
                        "5,600 tok/s cold prefill rate, a ratio of 0.979, well inside 2x. No "
                        "quantity in this file is faster than a committed curve."),
            "slot_seconds_sanity": ("total monitor slot-seconds per cell divided by wall times "
                                    "mean cap is reported per cell as "
                                    "monitor_share_of_that_capacity and must lie in (0, 1]; a "
                                    "value above 1 would mean more occupancy than the cap "
                                    "permits and would be an instrumentation error"),
            "slot_seconds_share_per_cell": {c["cell"]: c["slot_seconds"]
                                            ["monitor_share_of_that_capacity"] for c in ok},
            "slot_seconds_share_all_within_unit_interval": all(
                0.0 < (c["slot_seconds"]["monitor_share_of_that_capacity"] or 0) <= 1.0
                for c in ok),
        },
        "3_distribution_sanity": {
            "_what": ("no median appears in this file without its spread and its "
                      "distinct_values. The three shapes CLAUDE.md names are checked: a "
                      "constant where a distribution is expected, an artefact spread, and a real "
                      "effect averaged into undetectability."),
            "a_constant_where_a_distribution_is_expected": {
                "found": ("the forward hop is 0.0222 s with distinct_values 1 on every cell, "
                          "already recorded in the reconcile file as a trace constant. It is "
                          "USED only as a labelled sensitivity variant, never as a measurement."),
                "checked_no_other": ("hold, first-token, uncached, queued-ahead and slot-seconds "
                                     "all carry distinct_values in the thousands per cell; see "
                                     "each cell's spreads"),
            },
            "b_artefact_spread": (
                "THE SPREAD AT RISK HERE IS THE DOA SHARE ACROSS PREDICTORS, and what it is must "
                "be stated before it is trusted. Under predictor (i) the values ARE a hold "
                "threshold and nothing else: the column cannot mean 'the rule identified an "
                "infeasible request', only 'the request was held longer than a fixed number'. The "
                "confusion table against the oracle outcome is reported per variant so the reader "
                "can see how much of each DOA count is a request that in fact arrived on time."),
            "c_effect_averaged_into_undetectability": (
                "the DOA share is NOT averaged across arms: every number is reported per cell, "
                "and the rung-2 and base strata are kept apart with their own denominators, "
                "because the whole question is a 68-against-34 stratum difference"),
        },
        "4_definition_audit": {
            "monitor_opportunity": ("one kind == 'monitor' row of outcomes.jsonl.gz, the same "
                                    "denominator as dashcam_ontime_reconcile.json and as the "
                                    "committed scorer's sum of dashcam_per_device[*].n_instants"),
            "released_monitor": ("cloud_payload.request_id set, not in refused_request_ids, "
                                 "request row present. Equals that file's four released buckets "
                                 "exactly, asserted per cell"),
            "hold_at_release": "t_submit - t_opportunity, that file's release_delay, unchanged",
            "deadline": "1.0 s from t_opportunity, read per row and asserted",
            "uncached": "prompt_tokens - cached_tokens, the same definition as c5_loss_split.py",
            "DOA": ("hold + predicted first token > 1.0 s. Under the ORACLE predictor this is "
                    "EXACTLY that file's late_at_release + late_at_first_token, which is why the "
                    "classifier is consistent with those buckets rather than merely similar: "
                    "late_at_release is the hold > 1.0 s subset and late_at_first_token is the "
                    "remainder whose first-token age exceeds 1.0 s"),
            "slot_second": ("one second of one C5 in-flight slot, t_done - t_submit. NOT a "
                            "GPU-second and never converted to one"),
            "names_used_with_two_definitions": "none found",
        },
        "5_claim_linkage": {
            "bears_on": ("FORMULATION.md's Context Inertia physical component, the timing half: "
                         "this is a release-timing question, not a representation one"),
            "supports": ("the reconcile file's finding that rung-2's dashcam lateness is RELEASE "
                         "DELAY INSIDE THE COORDINATOR and not engine time. The DOA share is the "
                         "same finding counted as a decision rather than as a latency."),
            "does_not_speak_to": ("whether the rule improves alert on-time delivery. Nothing here "
                                  "is an outcome: the bound is a bound and the arm does not "
                                  "exist."),
            "scoped_out_check": ("nothing here measures KV transfer between heterogeneous tiers, "
                                 "which FORMULATION.md Scoping excludes"),
        },
        "6_proxy_validity": {
            "_see": "_proxies_declared",
            "questionable_and_therefore_not_headline": (
                "uncached_queued_ahead is RECONSTRUCTED from observed uncached counts and is not "
                "the coordinator's own counter. Predictor (ii)'s DOA share therefore carries a "
                "proxy in one of its two inputs and is reported BESIDE predictor (i), not instead "
                "of it. The CONSTRUCTED BOUND is reported under all three predictors for the same "
                "reason."),
            "observed_vs_predicted_uncached": ("the observed count favours the model, so any "
                                               "accuracy claim for predictor (ii) is an upper "
                                               "bound on its live accuracy"),
        },
        "7_validate_the_control": {
            "_what": ("the BASE arm is the control and its own numbers are checked against their "
                      "committed values BEFORE the rung-2 comparison is read"),
            "negative_control_the_classifier_must_reproduce_the_base": {
                "user_base_s4_held_over_0.56": 0.34,
                "this_run_base_s4": _get(b4, ["user_figures",
                                              "share_held_over_0.56_s_at_release"]),
                "user_base_s4_released_after_deadline": 0.01,
                "this_run_base_s4": _get(b4, ["user_figures",
                                              "share_held_over_the_whole_1.0_s_deadline"]),
            },
            "positive_control_a_known_good_committed_arm_must_pass_the_check": {
                "_claim": ("on the base cells, a known-good committed arm, the oracle DOA count "
                           "must equal the committed reconcile buckets exactly. If it fails, THE "
                           "CHECK IS BROKEN, NOT THE ARM."),
                "rows": [{"cell": c["cell"], "oracle_doa": c["control_e"]["this_run_oracle_doa"],
                          "committed_buckets": c["control_e"]
                          ["reconcile_late_at_release_plus_late_at_first_token"],
                          "pass": c["control_e"]["pass_2"]}
                         for c in ok if c["is_base"]],
            },
            "impossible_success_check": (
                "a DOA share of 0 on a base cell, or of 1 on a rung-2 cell, would be an "
                "impossible success and an impossible failure respectively; neither occurs"),
        },
    }

    res["proposed_policy_spec_v6_section_12_row"] = {
        "_register": ("PROPOSED ONLY. research/policy_spec_v6.md is NOT edited by this script and "
                      "was not touched. This row is placed here for the user to rule on."),
        "id": "C5-c",
        "name": "deadline-aware release (dashcam monitors)",
        "rule": ("at release, skip a dashcam monitor whose hold-so-far (now - t_opportunity) plus "
                 "its predicted first-token time exceeds its deadline; the device answers it. The "
                 "prediction is the D162 model on the request's own predicted uncached count and "
                 "the coordinator's live _uncached_in_flight, which is the one price source both "
                 "the planner and the coordinator already read."),
        "default": "OFF. Not implemented; no arm carries it.",
        "why_the_existing_rule_does_not_cover_it": ("b7's feasibility branch is in the RECALL loop "
                                                    "only; the dashcam loop computes slack at "
                                                    "hybrid_arm.py:351 and appends "
                                                    "unconditionally at :355, and slack is read "
                                                    "only in the ordering index at :443"),
        "evidence": ("results/orchestration/live2/frozen_test/"
                     "dashcam_deadline_release_estimate.json"),
        "what_the_evidence_is": ("an OFFLINE ESTIMATE with a CONSTRUCTED BOUND on recoverable "
                                 "on-time instants. NOT an outcome and not a measured gain."),
        "what_would_settle_it": ("an arm that applies the test, run on the same three seeds, "
                                 "scored against the committed base on dashcam on-time; the "
                                 "offline bound cannot be converted into that because the "
                                 "survivors' queue and the cap's AIMD trajectory both change"),
        "stopping_condition_if_built": ("Step 2b: diff the decision logs of the arm with and "
                                        "without the test on one cell and report the number of "
                                        "differing release decisions before scoring anything"),
    }

    res["what_could_not_be_determined"] = [
        "whether the rule improves dashcam on-time delivery. No arm exists; the bound is a bound.",
        ("what the live predicted uncached count would have been at each release. The coordinator "
         "logs the engine's observed count, so predictor (ii) was evaluated on the observed one "
         "and is optimistic about its own accuracy."),
        ("the coordinator's own _uncached_in_flight series. It is not in the logs, so the "
         "queued-ahead input is a reconstruction."),
        ("how the C5 cap's AIMD trajectory would move under the rule. Its input is an EWMA of the "
         "very first-token distribution the rule changes."),
        ("whether a device answer is as good as a cloud answer on these frames. This file counts "
         "slots and deadlines, never answer quality."),
    ]

    res["_provenance"] = stamp(script="dashcam_deadline_release_estimate.py", model="qwen7b",
                               device=None, n=sum(c.get("released_monitors_with_a_request_row", 0)
                                                  for c in ok), args=args)
    res["_provenance"]["model_note"] = ("the model slug is a required provenance field; this is a "
                                        "log analysis and ran no model. The cells were served by "
                                        "a 32B instruct engine on the H100 NVL.")
    res["_provenance"]["git_commit_note"] = ("the stamped commit is the HEAD of the worktree this "
                                             "analysis ran in, which another session had parked "
                                             "off origin/main. The commit that CARRIES this file "
                                             "is built against origin/main, and every run file "
                                             "read is checked blob-identical to origin/main's per "
                                             "cell under runs_blob_check.")
    Path(args.out).write_text(json.dumps(res, indent=1) + "\n")
    print("wrote", args.out)
    print("control_e_all_pass:", res["headline"]["control_e_all_pass"])
    for c in ok:
        print(c["cell"][:46],
              "rel=%d" % c["released_monitors_with_a_request_row"],
              "doa_user=%.4f" % c["variants"]["const_user_0.44"]["doa_share_of_released"],
              "doa_d162=%.4f" % c["variants"]["d162_model"]["doa_share_of_released"],
              "freed=%.1f" % c["variants"]["const_user_0.44"]["cap_slot_seconds_freed"],
              "bound=%s" % c["constructed_bounds"]["const_user_0.44"]
              ["upper_bound_on_time_instants_recoverable"])


if __name__ == "__main__":
    main()
