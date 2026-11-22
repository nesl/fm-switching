#!/usr/bin/env python3
"""The C5 decision, read-only: SPLIT rung 1's dashcam loss into engine vs cap vs other.

USER RULING 2026-11-22, for the C5 attribution decision. No new cells, no code changes.

  (a) SUBMITTED BUT LATE, BEHIND A ROBOT PREFILL. The monitor was released, missed its 1.0 s
      deadline, and its wait OVERLAPPED a robot prefill the coordinator had released (a warm build,
      or a recall, with uncached >= 200 tokens). This is ENGINE-LEVEL head-of-line blocking and is
      what engine priority (layer 1) would address.
  (b) NOT SUBMITTED WITH NO PREFILL IN FLIGHT. The monitor was never released while C5's AIMD cap
      sat at or near its floor AND no robot prefill was in flight at all. The cap was closed by
      the MEMORY of past lateness, not by work present now, which is what a C5 attribution rule
      (layer 2) would address.
  (c) everything else, named rather than left as a remainder.

THE CAP TRAJECTORY IS RECONSTRUCTED, and the reconstruction is CONTROLLED: it must reproduce the
base arm's own `c5_increase` and `c5_decrease` counters, which survive in its `arm_stats`. Without
that control the cap series would be a model output compared against nothing. v5-rules-2's own
counters do NOT survive (its wrapper reports a different Counter), which is why rung 1 needs the
reconstruction at all.
"""
from __future__ import annotations

import gzip
import json
import statistics
from pathlib import Path
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
RUNS = REPO / "results/orchestration/live2/frozen_test/runs"

PERIOD_S = 0.1
RUN_S = 1200.0
DASH_L_S = 1.0
AIMD_TRIP_S = 0.8 * DASH_L_S
EWMA_A = 0.3
CAP_FLOOR = 4
CAP_CEIL = 8
NEAR_FLOOR = 5                 # floor plus one AIMD step up
ROBOT_PREFILL_UNCACHED = 200    # the ruling's threshold
ARMS = ["hybrid-F-lhreq-noc3", "v5-rules-2"]
SEEDS = [4, 5, 6, 7]
TAG = "_n16_s%d_1200s_h27_3t_L3_epg_rq30"


def _rows(p: Path) -> List[Dict[str, Any]]:
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

    kind_of_opp = {o["opportunity_id"]: o["kind"] for o in out if o.get("opportunity_id")}

    # ---- classify every submitted request, and find the ROBOT PREFILLS -------------------
    robot_prefills: List[Dict[str, Any]] = []
    monitors_by_opp: Dict[str, Dict[str, Any]] = {}
    mon_ttft: List[float] = []
    for r in req:
        opp = r.get("opportunity_id")
        kind = kind_of_opp.get(opp) if opp else "build"
        t0 = float(r["t_submit"])
        t1 = float(r.get("t_done") or r["t_submit"])
        unc = max(int(r.get("prompt_tokens") or 0) - int(r.get("cached_tokens") or 0), 0)
        if kind == "monitor":
            monitors_by_opp[opp] = {"t_submit": t0, "t_done": t1, "uncached": unc}
            if r.get("t_first_token"):
                mon_ttft.append(float(r["t_first_token"]) - t0)
        elif kind in ("build", "recall") and unc >= ROBOT_PREFILL_UNCACHED:
            robot_prefills.append({"t0": t0, "t1": t1, "uncached": unc, "kind": kind})

    # per-epoch: is a robot prefill in flight?
    prefill_in_flight = [0] * n_ep
    for pf in robot_prefills:
        a, b = int(pf["t0"] / PERIOD_S), int(pf["t1"] / PERIOD_S)
        for e in range(max(a, 0), min(b + 1, n_ep)):
            prefill_in_flight[e] += 1

    # ---- the AIMD cap, reconstructed on the arm's own rule, and the episodic in-flight ----
    upd = sorted((m["t_done"], t) for m, t in
                 ((m, m["t_done"] - m["t_submit"]) for m in monitors_by_opp.values()))
    ttft_upd = sorted((float(r["t_done"]), float(r["t_first_token"]) - float(r["t_submit"]))
                      for r in req
                      if r.get("opportunity_id") in monitors_by_opp
                      and r.get("t_first_token") and r.get("t_done"))
    lat_at: List[Optional[float]] = [None] * n_ep
    lat, j = 0.0, 0
    for e in range(n_ep):
        t = e * PERIOD_S
        while j < len(ttft_upd) and ttft_upd[j][0] <= t:
            v = ttft_upd[j][1]
            lat = v if lat <= 0 else EWMA_A * v + (1 - EWMA_A) * lat
            j += 1
        lat_at[e] = lat if lat > 0 else None
    cap, last_adj = CAP_CEIL, None
    caps = [CAP_CEIL] * n_ep
    n_dec = n_inc = 0
    for e in range(n_ep):
        t = e * PERIOD_S
        la = lat_at[e]
        if la is not None and la > AIMD_TRIP_S:
            if last_adj is None or t - last_adj >= 1.0:
                cap = max(CAP_FLOOR, cap // 2)
                n_dec += 1
                last_adj = t
        elif last_adj is None or t - last_adj >= 5.0:
            if cap < CAP_CEIL:
                cap += 1
                n_inc += 1
            last_adj = t
        caps[e] = cap
    epi = [0] * n_ep
    for m in monitors_by_opp.values():
        a, b = int(m["t_submit"] / PERIOD_S), int(m["t_done"] / PERIOD_S)
        for e in range(max(a, 0), min(b + 1, n_ep)):
            epi[e] += 1

    # ---- the split -----------------------------------------------------------------------
    a_late_behind_prefill = 0
    a_late_not_behind = 0
    on_time = 0
    not_submitted_cap_no_prefill = 0
    not_submitted_cap_with_prefill = 0
    not_submitted_cap_open = 0
    n_off = 0
    late_overlap_tokens: List[int] = []
    for o in out:
        if o["kind"] != "monitor":
            continue
        n_off += 1
        opp = o.get("opportunity_id")
        t_opp = float(o["t_opportunity"])
        e = min(max(int(t_opp / PERIOD_S), 0), n_ep - 1)
        cp = o.get("cloud_payload") or {}
        rid = cp.get("request_id")
        if rid and opp in monitors_by_opp:
            td = o.get("t_delivered")
            late = not (td is not None and float(td) - t_opp <= DASH_L_S + 1e-9)
            if not late:
                on_time += 1
                continue
            m = monitors_by_opp[opp]
            hit = [pf for pf in robot_prefills
                   if pf["t0"] < m["t_done"] and pf["t1"] > m["t_submit"]]
            if hit:
                a_late_behind_prefill += 1
                late_overlap_tokens.append(max(p["uncached"] for p in hit))
            else:
                a_late_not_behind += 1
            continue
        # never submitted
        near_floor = caps[e] <= NEAR_FLOOR
        closed = near_floor or (caps[e] - epi[e]) <= 0
        if closed and prefill_in_flight[e] == 0:
            not_submitted_cap_no_prefill += 1
        elif closed:
            not_submitted_cap_with_prefill += 1
        else:
            not_submitted_cap_open += 1

    def _q(xs, q):
        xs = sorted(xs)
        return round(xs[min(int(q * len(xs)), len(xs) - 1)], 1) if xs else None

    tot = n_off
    def sh(x):
        return round(x / tot, 4) if tot else None
    return {
        "cell": arm + TAG % seed,
        "monitor_opportunities": tot,
        "on_time": on_time, "on_time_share": sh(on_time),
        "a_submitted_late_behind_a_robot_prefill": a_late_behind_prefill,
        "a_share": sh(a_late_behind_prefill),
        "a_overlapping_prefill_uncached_p50": _q(late_overlap_tokens, 0.5),
        "a_overlapping_prefill_uncached_p90": _q(late_overlap_tokens, 0.9),
        "a2_submitted_late_no_prefill_overlap": a_late_not_behind,
        "a2_share": sh(a_late_not_behind),
        "b_not_submitted_cap_closed_no_prefill_in_flight": not_submitted_cap_no_prefill,
        "b_share": sh(not_submitted_cap_no_prefill),
        "b2_not_submitted_cap_closed_prefill_in_flight": not_submitted_cap_with_prefill,
        "b2_share": sh(not_submitted_cap_with_prefill),
        "c_not_submitted_cap_open": not_submitted_cap_open,
        "c_share": sh(not_submitted_cap_open),
        "robot_prefills_released": len(robot_prefills),
        "robot_prefill_uncached_p50": _q([p["uncached"] for p in robot_prefills], 0.5),
        "monitor_ttft_p50": (round(statistics.median(mon_ttft), 3) if mon_ttft else None),
        "epochs_at_cap_floor": sum(1 for c in caps if c == CAP_FLOOR),
        "control_reconstructed_decreases": n_dec,
        "control_reconstructed_increases": n_inc,
        "control_arm_recorded_decreases": (cr.get("arm_stats") or {}).get("c5_decrease"),
        "control_arm_recorded_increases": (cr.get("arm_stats") or {}).get("c5_increase"),
    }


def main() -> int:
    out: Dict[str, Any] = {
        "_what": ("D174 (2) follow-up for the C5 decision: rung 1's dashcam loss split into "
                  "engine blocking (a), a cap closed with no work in flight (b), and other (c)"),
        "_definitions": {
            "robot_prefill": ("a build or recall request the coordinator released with uncached "
                              ">= %d tokens, uncached = prompt_tokens - cached_tokens"
                              % ROBOT_PREFILL_UNCACHED),
            "a": ("submitted, delivered later than the 1.0 s deadline, and its [submit, done] "
                  "interval OVERLAPS a robot prefill's"),
            "b": ("never submitted, in an epoch where the reconstructed cap was at or near its "
                  "floor (<= %d) or fully occupied, AND no robot prefill was in flight"
                  % NEAR_FLOOR),
            "near_floor": "cap <= %d, the floor %d plus one AIMD step" % (NEAR_FLOOR, CAP_FLOOR),
        },
        "cells": [], }
    for arm in ARMS:
        for s in SEEDS:
            c = _cell(arm, s)
            out["cells"].append(c or {"cell": arm + TAG % s, "missing": True})
    live = [c for c in out["cells"] if not c.get("missing")]
    ctl = [c for c in live if c["control_arm_recorded_decreases"] is not None]
    # TOLERANCE OF ONE COUNT, STATED RATHER THAN WIDENED. The reconstruction is exact on 2 of the
    # 4 base cells and one DECREMENT high on the other two (112 against 111, 118 against 117),
    # out of 92 to 154 adjustments. The residual is a boundary effect at the first adjustment (the
    # EWMA's `lat <= 0` initialisation) or the last one at the run edge. An earlier version of
    # this check used a 2x band, which would have passed a real break just as happily; the band
    # is 1 COUNT so that a break shows.
    ctl_ok = all(abs(c["control_reconstructed_decreases"]
                     - c["control_arm_recorded_decreases"]) <= 1
                 and abs(c["control_reconstructed_increases"]
                         - c["control_arm_recorded_increases"]) <= 1
                 for c in ctl)
    out["control"] = {
        "_claim": ("the reconstructed AIMD trajectory reproduces the base arm's own counters; "
                   "v5-rules-2 does not report them, which is why the reconstruction exists"),
        "rows": [{"cell": c["cell"],
                  "decreases": [c["control_reconstructed_decreases"],
                                c["control_arm_recorded_decreases"]],
                  "increases": [c["control_reconstructed_increases"],
                                c["control_arm_recorded_increases"]]} for c in ctl],
        "tolerance": "1 count on each counter, stated; exact on 2 of 4, one decrement high on 2",
        "verdict": ("PASS: within one count on all %d cells that record them, exact on %d"
                    % (len(ctl), sum(1 for c in ctl
                                     if c["control_reconstructed_decreases"]
                                     == c["control_arm_recorded_decreases"]))
                    if ctl and ctl_ok
                    else "FAIL: the reconstruction does not reproduce the arm's own counters")}
    base = [c for c in live if c["cell"].startswith("hybrid-F")]
    rung = [c for c in live if c["cell"].startswith("v5-rules-2")]

    def rng(rows, k):
        v = [r[k] for r in rows if r.get(k) is not None]
        return [min(v), max(v)] if v else None

    out["verdict"] = {
        "on_time_share": {"base": rng(base, "on_time_share"), "rung1": rng(rung, "on_time_share")},
        "a_engine_blocking": {
            "base": rng(base, "a_share"), "rung1": rng(rung, "a_share"),
            "reading": ("submitted, late, and overlapping a robot prefill. Rung 1 is only "
                        "modestly worse than the base here, so head-of-line blocking is real but "
                        "is NOT where the loss is")},
        "a2_late_with_no_prefill_overlap": {
            "base": rng(base, "a2_share"), "rung1": rng(rung, "a2_share"),
            "reading": ("late behind something OTHER than a robot prefill, chiefly other "
                        "monitors. Essentially unchanged between the two arms")},
        "b_cap_closed_with_nothing_in_flight": {
            "base": rng(base, "b_share"), "rung1": rng(rung, "b_share"),
            "reading": ("the cap was shut by the MEMORY of past lateness while no robot prefill "
                        "was running. This is the part only a C5 rule can reach, and rung 1 is 2 "
                        "to 3 times the base")},
        "b2_cap_closed_with_a_prefill_in_flight": {
            "base": rng(base, "b2_share"), "rung1": rng(rung, "b2_share"),
            "reading": ("THE DOMINANT BUCKET AND JOINTLY CAUSED: 37.5 to 43.0 percent of all "
                        "opportunities at rung 1 against 3.7 to 7.9 percent at the base, a 5 to "
                        "10 fold increase. The cap is shut AND real prefill work is in flight, so "
                        "neither cause can be assigned it alone")},
        "c_cap_open_and_still_not_submitted": {
            "base": rng(base, "c_share"), "rung1": rng(rung, "c_share"),
            "reading": "small and smaller at rung 1; not a channel"},
        "what_each_layer_could_reach": (
            "NOT SUBMITTED (b + b2 + c) is 52 to 58 percent of all opportunities at rung 1 "
            "against 13 to 17 percent at the base, and SUBMITTED-BUT-LATE (a + a2) is 31 to 35 "
            "percent against 25 to 38. So the loss is overwhelmingly a RELEASE decision, not a "
            "delivery failure, and a C5 attribution rule (layer 2) is the only thing that reaches "
            "it directly. But the cap closes BECAUSE monitor first-token times cross C5's 0.8 s "
            "trip, and engine priority (layer 1) acts on exactly that, so layer 1 is upstream of "
            "layer 2's symptom: it would shrink a directly and b and b2 indirectly by keeping the "
            "cap open. The two are not alternatives on the same quantity"),
        "a_caveat_on_the_blocking_population": (
            "the prefills that late monitors overlap have median uncached 1,395 to 1,398 tokens "
            "with p90 11,822 to 13,781, and the released robot prefills have median 1,375 to "
            "1,377. So the overlap is dominated by MANY SMALL prefills rather than by the few "
            "3,071-token warm builds, which the >= 200-token definition includes recalls in, as "
            "the ruling specified. Rung 1 releases 570 to 601 such prefills against the base's "
            "385 to 408"),
    }
    dest = REPO / "results/orchestration/live2/frozen_test/c5_loss_split.json"
    dest.write_text(json.dumps(out, indent=1) + "\n")
    print("%-58s %7s %6s %6s %6s %6s %6s" % ("cell", "opps", "ontime", "a", "a2", "b", "b2/c"))
    for c in live:
        print("%-58s %7d %6d %6d %6d %6d %4d/%d" % (
            c["cell"][:58], c["monitor_opportunities"], c["on_time"],
            c["a_submitted_late_behind_a_robot_prefill"],
            c["a2_submitted_late_no_prefill_overlap"],
            c["b_not_submitted_cap_closed_no_prefill_in_flight"],
            c["b2_not_submitted_cap_closed_prefill_in_flight"], c["c_not_submitted_cap_open"]))
    print(out["control"]["verdict"])
    print("wrote", dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
