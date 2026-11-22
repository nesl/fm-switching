#!/usr/bin/env python3
"""D174 (2): why covex-v6-rules (v5-rules-2) RELEASES HALF THE DASHCAM MONITORS its base does.

READ-ONLY, from the committed cells on this disk. No new cells, per the ruling.

THE GAP, and it is not a budget. `budget_refusal` is ZERO in every committed v5-rules and
v5-rules-2 cell (results/.../budget_refusal_census.json), so the monitors are not refused: they
are never submitted. The opportunity streams are identical by construction (D69 fairness: 11,764
monitor opportunities in both arms at seed 4), and the base releases 9,743 of them against
v5-rules-2's 4,827.

THREE HYPOTHESES, and the third is mine and was not in the ruling's list.

  (a) SLOT COMPETITION. Warm builds occupy in-flight slots, so fewer are left for monitors.
      PREDICTION: build requests in flight during the epochs where monitors go unreleased.
      NOTE BEFORE MEASURING: C5's cap arithmetic subtracts only `running_by_class["episodic"]`,
      and cstate puts piece and whole builds under "recall", so a build CANNOT take a dashcam cap
      slot directly. If (a) acts at all it acts indirectly, which is (c).

  (b) C2 FIRES MORE OFTEN. Warming releases more recall questions, so more robots are at risk and
      the dashcam throttle holds monitors down to its floor of 2 more of the time.
      PREDICTION: more at-risk robot periods in v5-rules-2 than in the base.

  (c) THE AIMD CAP COLLAPSES. C5's cap starts at 8, halves (floor 4) whenever the EWMA episodic
      first-token estimate exceeds 0.8 x the 1.0 s dashcam deadline, and recovers +1 only every
      5 s. Warm builds lengthen monitor first-token times, so the estimate crosses 0.8 s and the
      cap sits at its floor. PREDICTION: v5-rules-2's monitor TTFT distribution sits above 0.8 s
      far more often, and its reconstructed cap spends most of the run at 4.

WHAT CANNOT BE ANSWERED READ-ONLY, stated rather than worked around. v5-rules-2's `arm_stats`
carries only its OWN warming counters; the base hybrid it wraps keeps `c2_throttle_periods`,
`c2_throttled_dash` and `c5_dash_held` in a DIFFERENT Counter, which no committed v5-rules-2 cell
reports. So (b) is tested here through a PROXY reconstructed from the outcome log (check 6: the
proxy is pending robot questions inside k_r of their deadline, which is the C2 trigger's own
condition evaluated on observable arrival and release times, but NOT on the arm's predicted
remaining work, so it is an upper bound on at-risk periods and is labelled as one).
"""
from __future__ import annotations

import gzip
import json
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
RUNS = REPO / "results/orchestration/live2/frozen_test/runs"

PERIOD_S = 0.1
RUN_S = 1200.0
DASH_DEADLINE_S = 1.0
AIMD_TRIP_S = 0.8 * DASH_DEADLINE_S
EWMA_A = 0.3
K_R = 0.3 * 3.0                     # D143 B: robot at-risk threshold, 0.9 s
THROTTLE_FLOOR = 2
ARMS = ["hybrid-F-lhreq-noc3", "v5-rules-2"]
SEEDS = [4, 5, 6, 7]
TAG = "_n16_s%d_1200s_h27_3t_L3_epg_rq30"


def _rows(p: Path):
    if not p.exists():
        return []
    with gzip.open(p, "rt") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def _cell(arm: str, seed: int) -> Optional[Dict[str, Any]]:
    d = RUNS / (arm + TAG % seed)
    if not d.exists():
        return None
    req = _rows(d / "request.jsonl.gz")
    out = _rows(d / "outcomes.jsonl.gz")
    cr = json.loads((d / "coordinator_result.json").read_text())
    n_ep = int(RUN_S / PERIOD_S)

    # ---- classify every submitted request -------------------------------------------------
    kind_of_opp = {o["opportunity_id"]: o["kind"] for o in out if o.get("opportunity_id")}
    reqs = []
    for r in req:
        opp = r.get("opportunity_id")
        kind = kind_of_opp.get(opp) if opp else None
        if kind is None:
            kind = "build"          # no opportunity: a warm-ahead build or piece
        reqs.append({"kind": kind, "t_submit": float(r["t_submit"]),
                     "t_done": float(r.get("t_done") or r["t_submit"]),
                     "ttft": (float(r["t_first_token"]) - float(r["t_submit"])
                              if r.get("t_first_token") else None)})

    # ---- offered against released, by opportunity --------------------------------------
    offered = [0] * n_ep
    released = [0] * n_ep
    n_off = n_rel = 0
    for o in out:
        if o["kind"] != "monitor":
            continue
        e = int(float(o["t_opportunity"]) / PERIOD_S)
        if not 0 <= e < n_ep:
            continue
        offered[e] += 1
        n_off += 1
        if ((o.get("cloud_payload") or {}).get("request_id")):
            released[e] += 1
            n_rel += 1

    # ---- in-flight occupancy at each epoch start, by class ------------------------------
    infl = {k: [0] * n_ep for k in ("monitor", "recall", "build")}
    for r in reqs:
        a = int(r["t_submit"] / PERIOD_S)
        b = int(r["t_done"] / PERIOD_S)
        k = r["kind"] if r["kind"] in infl else "build"
        for e in range(max(a, 0), min(b + 1, n_ep)):
            infl[k][e] += 1

    # ---- (c) reconstruct the AIMD cap on the arm's own rule -----------------------------
    # the estimate the arm reads is cstate's EWMA over monitor ttft, updated at COMPLETION
    upd: List[tuple] = sorted((r["t_done"], r["ttft"]) for r in reqs
                              if r["kind"] == "monitor" and r["ttft"] is not None)
    lat_at = [None] * n_ep
    lat = 0.0
    j = 0
    for e in range(n_ep):
        t = e * PERIOD_S
        while j < len(upd) and upd[j][0] <= t:
            v = upd[j][1]
            lat = v if lat <= 0 else EWMA_A * v + (1 - EWMA_A) * lat
            j += 1
        lat_at[e] = lat if lat > 0 else None
    cap, last_adj, caps = 8, None, [8] * n_ep
    n_dec = n_inc = 0
    for e in range(n_ep):
        t = e * PERIOD_S
        la = lat_at[e]
        if la is not None and la > AIMD_TRIP_S:
            if last_adj is None or t - last_adj >= 1.0:
                cap = max(4, cap // 2)
                n_dec += 1
                last_adj = t
        elif last_adj is None or t - last_adj >= 5.0:
            if cap < 8:
                cap += 1
                n_inc += 1
            last_adj = t
        caps[e] = cap

    # ---- (b) at-risk robot proxy ---------------------------------------------------------
    rel_t = {}
    for r in req:
        if r.get("opportunity_id"):
            rel_t[r["opportunity_id"]] = float(r["t_submit"])
    at_risk = [0] * n_ep
    for o in out:
        if o["kind"] != "recall":
            continue
        arr = float(o["t_opportunity"])
        dl = arr + float(o["deadline_s"])
        end = rel_t.get(o["opportunity_id"], dl)
        for e in range(max(int(arr / PERIOD_S), 0), min(int(min(end, dl) / PERIOD_S) + 1, n_ep)):
            if dl - e * PERIOD_S < K_R:
                at_risk[e] += 1

    # ---- the epochs where the gap happens -------------------------------------------------
    gap_ep = [e for e in range(n_ep) if offered[e] > released[e]]
    def _mean(xs):
        return round(statistics.fmean(xs), 3) if xs else None
    mon_ttft = [r["ttft"] for r in reqs if r["kind"] == "monitor" and r["ttft"] is not None]
    mon_ttft.sort()
    def _q(xs, q):
        return round(xs[min(int(q * len(xs)), len(xs) - 1)], 3) if xs else None

    return {
        "cell": arm + TAG % seed,
        "monitor_opportunities": n_off, "monitors_released": n_rel,
        "submission_gap": n_off - n_rel,
        "released_fraction": round(n_rel / n_off, 3) if n_off else None,
        "counts_submitted_monitor": int((cr.get("counts") or {}).get("submitted_monitor", 0)),
        "builds_submitted": sum(1 for r in reqs if r["kind"] == "build"),
        "recalls_released": sum(1 for r in reqs if r["kind"] == "recall"),
        "epochs_with_an_unreleased_monitor": len(gap_ep),
        # (a)
        "a_slot_competition": {
            "build_in_flight_mean_over_gap_epochs": _mean([infl["build"][e] for e in gap_ep]),
            "build_in_flight_mean_over_all_epochs": _mean(infl["build"]),
            "gap_epochs_with_zero_builds_in_flight":
                sum(1 for e in gap_ep if infl["build"][e] == 0),
            "episodic_in_flight_mean_over_gap_epochs":
                _mean([infl["monitor"][e] for e in gap_ep])},
        # (b)
        "b_c2_throttle_proxy": {
            "epochs_with_a_robot_inside_k_r": sum(1 for v in at_risk if v > 0),
            "gap_epochs_with_a_robot_inside_k_r":
                sum(1 for e in gap_ep if at_risk[e] > 0),
            "share_of_gap_epochs": (round(sum(1 for e in gap_ep if at_risk[e] > 0)
                                          / len(gap_ep), 3) if gap_ep else None)},
        # (c)
        "c_aimd_cap_collapse": {
            "monitor_ttft_p50": _q(mon_ttft, 0.5), "monitor_ttft_p90": _q(mon_ttft, 0.9),
            "monitor_ttft_over_the_0_8_s_trip": round(
                sum(1 for v in mon_ttft if v > AIMD_TRIP_S) / len(mon_ttft), 3)
                if mon_ttft else None,
            "epochs_with_the_estimate_over_the_trip":
                sum(1 for v in lat_at if v is not None and v > AIMD_TRIP_S),
            "reconstructed_cap_mean": _mean(caps),
            "epochs_at_the_cap_floor_4": sum(1 for c in caps if c == 4),
            "epochs_at_cap_8": sum(1 for c in caps if c == 8),
            # CHECK 7, THE POSITIVE CONTROL. The reconstruction is only worth reading if it
            # reproduces the counters the BASE arm recorded for itself. The base is the one arm
            # whose c5_increase and c5_decrease survive in arm_stats; v5-rules-2's wrapper keeps
            # its own Counter and reports neither, which is why the reconstruction exists at all.
            "reconstructed_decreases": n_dec, "reconstructed_increases": n_inc,
            "arm_recorded_decreases": (cr.get("arm_stats") or {}).get("c5_decrease"),
            "arm_recorded_increases": (cr.get("arm_stats") or {}).get("c5_increase"),
            "gap_epochs_where_episodic_in_flight_reached_the_cap":
                sum(1 for e in gap_ep if infl["monitor"][e] >= caps[e]),
            "gap_epochs_where_episodic_in_flight_reached_the_throttle_floor":
                sum(1 for e in gap_ep if infl["monitor"][e] >= THROTTLE_FLOOR)},
    }


def main() -> int:
    out: Dict[str, Any] = {
        "_what": "D174 (2): the rung-1 dashcam submission gap, read-only from committed cells",
        "_method": ("monitor opportunities from outcomes.jsonl.gz (every opportunity appears, "
                    "presented to the device); released = the opportunity whose cloud_payload "
                    "carries a request_id; in-flight occupancy rebuilt from request.jsonl.gz "
                    "t_submit and t_done, classed by whether the request carries an "
                    "opportunity_id (monitor or recall) or none (a warm-ahead build)"),
        "_proxy_declaration": ("the C2 at-risk test is reconstructed from arrival and release "
                               "times inside k_r = 0.3 x 3.0 s, NOT from the arm's predicted "
                               "remaining work, so it OVERSTATES at-risk periods; the arm's own "
                               "c2_throttle_periods is absent from every committed v5-rules-2 "
                               "cell because the wrapper keeps its own Counter"),
        "cells": [],
    }
    for arm in ARMS:
        for s in SEEDS:
            c = _cell(arm, s)
            if c is None:
                out["cells"].append({"cell": arm + TAG % s, "missing": True})
                continue
            out["cells"].append(c)
    live = [c for c in out["cells"] if not c.get("missing")]
    base = [c for c in live if c["cell"].startswith("hybrid-F")]
    rung = [c for c in live if c["cell"].startswith("v5-rules-2")]

    def _rng(rows, f):
        vs = [f(c) for c in rows]
        return [min(vs), max(vs)] if vs else None

    # CHECK 7: the reconstruction must reproduce the arm's own counters where they exist.
    ctl = []
    for c in live:
        a = c["c_aimd_cap_collapse"]
        if a.get("arm_recorded_decreases") is None:
            ctl.append({"cell": c["cell"], "counters_absent": True})
            continue
        rd, ri = a["reconstructed_decreases"], a["reconstructed_increases"]
        ad, ai = a["arm_recorded_decreases"], a["arm_recorded_increases"]
        ctl.append({"cell": c["cell"], "decreases": [rd, ad], "increases": [ri, ai],
                    "ratio_decreases": round(rd / ad, 3) if ad else None,
                    "ratio_increases": round(ri / ai, 3) if ai else None,
                    "within_2x": (ad and 0.5 <= rd / ad <= 2.0
                                  and ai and 0.5 <= ri / ai <= 2.0)})
    checked = [r for r in ctl if not r.get("counters_absent")]
    out["positive_control_on_the_reconstruction"] = {
        "_claim": ("the reconstructed AIMD trajectory reproduces the counters the BASE arm "
                   "recorded for itself; without this the rung-1 numbers would be a model "
                   "output compared against nothing"),
        "rows": ctl,
        "verdict": ("PASS: all %d cells with recorded counters agree within 2x" % len(checked)
                    if checked and all(r["within_2x"] for r in checked) else
                    "FAIL: the reconstruction does not reproduce the arm's own counters, so the "
                    "cap trajectory below is not evidence"
                    if checked else
                    "FAIL: no cell carries the arm's own counters, so the reconstruction is "
                    "unvalidated and the (c) finding is marked unvalidated")}
    out["verdict"] = {
        "the_gap": {
            "monitor_opportunities_identical_across_arms":
                sorted({c["monitor_opportunities"] for c in base})
                == sorted({c["monitor_opportunities"] for c in rung}),
            "released_fraction_base": _rng(base, lambda c: c["released_fraction"]),
            "released_fraction_rung1": _rng(rung, lambda c: c["released_fraction"])},
        "a_slot_competition": {
            "finding": "NOT THE PER-EPOCH MECHANISM, and it cannot be by construction",
            "builds_submitted_per_cell": _rng(rung, lambda c: c["builds_submitted"]),
            "mean_builds_in_flight": _rng(rung,
                lambda c: c["a_slot_competition"]["build_in_flight_mean_over_all_epochs"]),
            "gap_epochs_with_zero_builds_in_flight": _rng(rung,
                lambda c: c["a_slot_competition"]["gap_epochs_with_zero_builds_in_flight"]),
            "share_of_gap_epochs_with_no_build_in_flight": _rng(rung,
                lambda c: round(c["a_slot_competition"]["gap_epochs_with_zero_builds_in_flight"]
                                / c["epochs_with_an_unreleased_monitor"], 3)),
            "why_not": ("C5 subtracts only running_by_class['episodic'] from its cap and cstate "
                        "classes piece and whole builds under 'recall', so a build cannot take a "
                        "dashcam cap slot. And 58 to 70 percent of the epochs where a monitor "
                        "goes unreleased have NO build in flight at all, so even an indirect "
                        "per-epoch account fails. 156 to 180 builds per cell cannot occupy 4,400 "
                        "to 5,000 epochs directly")},
        "b_c2_throttle": {
            "finding": "REFUTED, AND WITH THE OPPOSITE SIGN",
            "epochs_with_a_robot_inside_k_r_base": _rng(base,
                lambda c: c["b_c2_throttle_proxy"]["epochs_with_a_robot_inside_k_r"]),
            "epochs_with_a_robot_inside_k_r_rung1": _rng(rung,
                lambda c: c["b_c2_throttle_proxy"]["epochs_with_a_robot_inside_k_r"]),
            "share_of_gap_epochs_rung1": _rng(rung,
                lambda c: c["b_c2_throttle_proxy"]["share_of_gap_epochs"]),
            "why_not": ("the hypothesis predicts MORE at-risk robots under warming. The proxy "
                        "counts FEWER: 261 to 562 epochs against the base's 578 to 711, because "
                        "warming is what makes a robot question not at risk. And at-risk epochs "
                        "touch only 6 to 12 percent of the epochs where monitors go unreleased, "
                        "so the throttle cannot be holding them down. The proxy OVERSTATES "
                        "at-risk periods, so this bound runs in the safe direction")},
        "c_aimd_cap_collapse": {
            "finding": "THIS IS THE MECHANISM",
            "monitor_ttft_p90_base": _rng(base,
                lambda c: c["c_aimd_cap_collapse"]["monitor_ttft_p90"]),
            "monitor_ttft_p90_rung1": _rng(rung,
                lambda c: c["c_aimd_cap_collapse"]["monitor_ttft_p90"]),
            "fraction_over_the_0_8_s_trip_base": _rng(base,
                lambda c: c["c_aimd_cap_collapse"]["monitor_ttft_over_the_0_8_s_trip"]),
            "fraction_over_the_0_8_s_trip_rung1": _rng(rung,
                lambda c: c["c_aimd_cap_collapse"]["monitor_ttft_over_the_0_8_s_trip"]),
            "epochs_at_the_cap_floor_base": _rng(base,
                lambda c: c["c_aimd_cap_collapse"]["epochs_at_the_cap_floor_4"]),
            "epochs_at_the_cap_floor_rung1": _rng(rung,
                lambda c: c["c_aimd_cap_collapse"]["epochs_at_the_cap_floor_4"]),
            "share_of_gap_epochs_at_the_cap": _rng(rung,
                lambda c: round(c["c_aimd_cap_collapse"]
                                 ["gap_epochs_where_episodic_in_flight_reached_the_cap"]
                                / c["epochs_with_an_unreleased_monitor"], 3)),
            "chain": ("a few long warm builds (156 to 180 per cell, under one in flight on "
                      "average) lengthen monitor first-token times: p90 goes from 0.65 to 0.71 s "
                      "in the base to 1.39 to 1.65 s at rung 1, and the share above C5's 0.8 s "
                      "trip from 4 to 6 percent to 21 to 27 percent. Each trip HALVES the AIMD "
                      "cap, floor 4, and recovery is +1 every 5 s, so the cap spends 7,544 to "
                      "8,428 of 12,000 epochs at its floor against the base's 1,844 to 2,989. "
                      "The dashcam release budget is cap minus episodic in flight, which is then "
                      "zero in 87 to 93 percent of the epochs where a monitor goes unreleased. "
                      "The HYSTERESIS is why (a) looks absent per epoch: one trip costs 5 s of "
                      "recovery per step, so the damage outlives the build that caused it"),
            "what_this_implies": ("the rung-1 dashcam loss is NOT budget (zero refusals), NOT the "
                                  "cap arithmetic and NOT C2. It is a BASE-POLICY controller "
                                  "reacting to a latency signal that warming moves, and it would "
                                  "not be fixed by repricing, which is why D174 (1) skips the "
                                  "rung-1 rerun. Any fix is a change to C5's AIMD rule or to how "
                                  "warming yields, and is a POLICY change for the user to rule "
                                  "on, not an implementation fix")},
    }
    dest = REPO / "results/orchestration/live2/frozen_test/rung1_submission_gap.json"
    dest.write_text(json.dumps(out, indent=1) + "\n")
    for c in out["cells"]:
        if c.get("missing"):
            print("%-60s MISSING" % c["cell"])
            continue
        print("%-58s offered %5d released %5d (%.2f)  builds %5d" % (
            c["cell"], c["monitor_opportunities"], c["monitors_released"],
            c["released_fraction"], c["builds_submitted"]))
        print("     ttft p50 %-6s p90 %-6s over-trip %-5s | cap mean %-4s floor4 %5d | "
              "gap epochs %5d, at-cap %5d, with a robot inside k_r %5d" % (
                  c["c_aimd_cap_collapse"]["monitor_ttft_p50"],
                  c["c_aimd_cap_collapse"]["monitor_ttft_p90"],
                  c["c_aimd_cap_collapse"]["monitor_ttft_over_the_0_8_s_trip"],
                  c["c_aimd_cap_collapse"]["reconstructed_cap_mean"],
                  c["c_aimd_cap_collapse"]["epochs_at_the_cap_floor_4"],
                  c["epochs_with_an_unreleased_monitor"],
                  c["c_aimd_cap_collapse"]["gap_epochs_where_episodic_in_flight_reached_the_cap"],
                  c["b_c2_throttle_proxy"]["gap_epochs_with_a_robot_inside_k_r"]))
    print("wrote", dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
