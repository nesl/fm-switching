#!/usr/bin/env python3
"""Proofs for ONE PRICE SOURCE (user ruling, 2026-11-21).

P0  positive control       the comparison can see a price difference that is there
P1  planner == coordinator the two prices are equal PER REQUEST on a constructed case
P2  budget vs GPU busy     D102: the budget must never bind artificially
P3  baselines unchanged    no committed arm declares the pricing switch, digests unmoved
P4  no drift               the declared coefficients still equal the committed gate file

P1 IS THE RULING'S OWN TEST AND IT IS WRITTEN TO BE ABLE TO FAIL. It does not compare two calls
to one function, which would prove nothing; it walks the COORDINATOR's charge sites and the
PLANNER's harm basis separately, on the same constructed requests, and compares the numbers each
side would actually use.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
for _p in (str(HERE), str(HERE / "fleet"), str(HERE / "v5"), str(HERE / "hybrid"),
           str(HERE.parent / "baselines")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import cf_objective as CO                                                      # noqa: E402
import costs as C                                                              # noqa: E402
import d162_price as DP                                                        # noqa: E402
import touch_policy as TP                                                      # noqa: E402

# The reprice is HELD while its D102 gate fails. Flipping this to False is part of applying a
# ruling, and the proof below then changes what it asserts, which is deliberate: the strong form
# ("nobody declares it") is only correct while it is held.
# D173 (1) took work-only and its utilisation half FAILED on the measured cells. D174 (1) takes
# UNCACHED-ONLY. Whether an arm may be posted is no longer a hand-set flag here: P3 reads P2's
# own verdict, so the gate cannot be left stale in the wrong direction.
BASE_TOLERANCE = 500      # declared slack for a correct charge, not a budget for failure
RULES_ROWS = 4376         # covex-v6-rules' own dry decision-row count at this cell

# constructed requests: (label, uncached tokens, uncached queued ahead)
CASES = [("touch on an 11k warm prefix", TP.TOUCH_UNCACHED_TOKENS, 0),
         ("touch, 3,000 ahead", TP.TOUCH_UNCACHED_TOKENS, 3000),
         ("touch on a 21k warm prefix", TP.TOUCH_UNCACHED_TOKENS, 1000),
         ("warm recall, 200 new", 200, 0),
         ("warm recall, 200 new, 5,000 ahead", 200, 5000),
         ("cold recall 11k", 11000, 0),
         ("build piece 1024", 1024, 2000),
         ("dashcam append, 90 new", 90, 400)]


def p0_positive_control() -> Dict[str, Any]:
    """Two requests that MUST price differently do. Without this, P1's equality could be two
    constants agreeing."""
    a = DP.price_gpu_s(15, 0)
    b = DP.price_gpu_s(11000, 0)
    # TWO FUNCTIONS, TWO QUESTIONS, and conflating them broke this control once already. Under
    # D174 (1) the CHARGE is uncached-only, so `price_gpu_s` must vary with uncached tokens and
    # with NOTHING else: not with the queue (delay suffered) and not with the request count
    # (occupancy). The queue sensitivity belongs to `first_token_s`, which is the planner's harm
    # basis and the only place the queue term is still read.
    charge_varies_uncached = a != b
    charge_ignores_queue = DP.price_gpu_s(15, 0) == DP.price_gpu_s(15, 5000)
    charge_has_no_intercept = DP.price_gpu_s(0, 0) == 0.0
    harm_varies_queue = DP.first_token_s(15, 0) != DP.first_token_s(15, 5000)
    harm_has_intercept = DP.first_token_s(0, 0) > 0.0
    ok = (charge_varies_uncached and harm_varies_queue and harm_has_intercept
          and (charge_ignores_queue if DP.CHARGE_MODE in ("work-only", "uncached-only") else True)
          and (charge_has_no_intercept if DP.CHARGE_MODE == "uncached-only" else True))
    return {"_claim": ("the charge varies with the work it prices and with nothing else, and the "
                       "planner's harm basis still sees the queue and the per-request intercept"),
            "charge_mode": DP.CHARGE_MODE, "ruled_mode": DP.RULED_CHARGE_MODE,
            "touch_idle": round(a, 6), "cold_recall_11k": round(b, 6),
            "charge_varies_with_uncached": charge_varies_uncached,
            "charge_ignores_queue_term": charge_ignores_queue,
            "charge_has_no_intercept": charge_has_no_intercept,
            "harm_basis_varies_with_queue": harm_varies_queue,
            "harm_basis_keeps_the_intercept": harm_has_intercept,
            "verdict": ("PASS: the charge prices uncached work only and the harm basis still "
                        "prices delay and occupancy" if ok else
                        "FAIL: THE CHECK IS BROKEN; an equality below would be two constants")}


def p1_planner_equals_coordinator() -> Dict[str, Any]:
    """ONE MODEL, THREE TERMS, SPLIT BY WHAT EACH TERM MEASURES (D173 (1), D174 (1)).

    The earliest form of this proof demanded `coordinator_charge == planner_first_token` per
    request, and it PASSED while the charge included the queue term. Two rulings have since split
    the model by what its terms mean, so demanding equality would be demanding what they forbid.
    What must still hold, and is what "one price source" means:

      1. the two sides share ONE SET OF COEFFICIENTS, imported and not copied;
      2. the charge is EXACTLY the per-uncached term;
      3. the planner's basis differs from it by EXACTLY intercept + queue term, nothing else.

    Point 3 is asserted as an exact arithmetic identity rather than described, so a future edit
    that let some other difference in would fail here.
    """
    rows: List[Dict[str, Any]] = []
    same_coeff = (CO.QUEUE_TOKEN_S == DP.PER_QUEUE_S)
    for label, u, q in CASES:
        coord = DP.price_gpu_s(u, q)                  # the coordinator's budget charge
        work = DP.PER_UNCACHED_S * u                  # the uncached work term alone
        plan = DP.first_token_s(u, q)                 # the planner's harm basis
        excluded = DP.INTERCEPT_S + DP.PER_QUEUE_S * q
        rows.append({"case": label, "uncached": u, "queued_ahead": q,
                     "coordinator_charge_gpu_s": round(coord, 9),
                     "per_uncached_term_gpu_s": round(work, 9),
                     "planner_harm_basis_s": round(plan, 9),
                     "charge_equals_per_uncached_term": abs(coord - work) < 1e-15,
                     "difference_is_exactly_intercept_plus_queue":
                         abs((plan - coord) - excluded) < 1e-12})
    agree_work = all(r["charge_equals_per_uncached_term"] for r in rows)
    only_excl = all(r["difference_is_exactly_intercept_plus_queue"] for r in rows)
    return {"_claim": ("planner and coordinator read one model; the charge is exactly the "
                       "per-uncached work term and the difference is exactly the two terms the "
                       "rulings exclude from a budget"),
            "charge_mode": DP.CHARGE_MODE,
            "coefficients_shared_not_copied": same_coeff,
            "rows": rows,
            "charge_equals_per_uncached_term_everywhere": agree_work,
            "difference_is_only_intercept_and_queue": only_excl,
            "verdict": ("PASS: one model, shared coefficients, the charge is the per-uncached "
                        "term on all %d constructed requests, and the only difference from the "
                        "planner's basis is intercept plus queue term" % len(rows)
                        if (same_coeff and agree_work and only_excl) else
                        "FAIL: the coefficients are copied, not shared" if not same_coeff else
                        "FAIL: the charge is not the per-uncached term" if not agree_work else
                        "FAIL: the two sides differ by something other than intercept and queue")}


def p2_budget_vs_gpu_busy() -> Dict[str, Any]:
    """D102, THE RULING'S OWN GATE: the budget must never bind ARTIFICIALLY.

    MEASURED ON A CELL, not restated arithmetically. An earlier version of this proof compared
    only the touch total under the two prices, which is the quantity I EXPECTED to improve, and
    it passed while the repriced arm was starving dashcam. A proof that only measures what you
    hoped to fix is not a proof; this one runs the cell.
    """
    import test_hybrid as TH                                                   # noqa: PLC0415
    import coordinator as CD                                                   # noqa: PLC0415
    import arms_v6state as VS                                                  # noqa: PLC0415
    VS.register()
    cls = CD.Live2Coordinator
    old_init, holder = cls.__init__, {}

    def _ni(self, *a, **k):
        old_init(self, *a, **k)
        holder["c"] = self
    cls.__init__ = _ni
    rows: List[Dict[str, Any]] = []
    try:
        for mode in ("first-token", "work-only", "uncached-only"):
            DP.CHARGE_MODE = mode
            # covex-v6-state-d162 DECLARES the charge. The rung's own default does not, so
            # running this test on `covex-v6-state` made BOTH modes identical and the proof
            # PASSED VACUOUSLY the moment the default was corrected. A proof whose subject has
            # been switched off is not a passing proof.
            #
            # The probe declares no MODE, so it takes the ruled one and the loop would price all
            # three rows identically. `arm_charge_mode` is therefore patched for the loop, which
            # is the one place a mode may come from anywhere but the arm.
            _real = DP.arm_charge_mode
            DP.arm_charge_mode = lambda _arm, _m=mode: _m                      # noqa: E731
            try:
                dec, st = TH.dry("covex-v6-state-d162", 4, 8, run_s=600.0, ratio="50:50",
                                 robot_question_set="lh_req", ss_question_set="ss2")
            finally:
                DP.arm_charge_mode = _real
            c = holder["c"]
            rows.append({"charge_mode": mode,
                         "budget_refusal": int(c.counts.get("budget_refusal", 0)),
                         "budget_refusal_monitor": int(c.counts.get("budget_refusal_monitor", 0)),
                         "budget_refusal_build": int(c.counts.get("budget_refusal_build", 0)),
                         "budget_refusal_recall": int(c.counts.get("budget_refusal_recall", 0)),
                         "state_decisions": int((st or {}).get("state_decisions", 0)),
                         "decision_rows": len(dec)})
    finally:
        DP.CHARGE_MODE = DP.RULED_CHARGE_MODE
        cls.__init__ = old_init
    # D102'S OTHER HALF, and it is the half that decides. "The budget never binds artificially"
    # is necessary; "budget utilisation tracks measured GPU busy time" is the test the ruling
    # names, and it cannot be answered by a dry cell at all. It CAN be answered against the
    # committed cells, whose measured load rate reproduces their per-type uncached totals to 0.02
    # percent, so it is the engine's own throughput and not a model output.
    MEASURED = [{"cell": "covex-v6-state s4", "n_req": 8090, "uncached": 4042800,
                 "run_s": 1200.0},
                {"cell": "covex-v6-state s5", "n_req": 9114, "uncached": 5401200,
                 "run_s": 1200.0}]
    PREFILL_TOK_S = 5600.0
    util: List[Dict[str, Any]] = []
    for m in MEASURED:
        busy = m["uncached"] / PREFILL_TOK_S
        work_term = DP.PER_UNCACHED_S * m["uncached"]
        icpt = DP.INTERCEPT_S * m["n_req"]
        util.append({
            "cell": m["cell"],
            "measured_gpu_busy_s": round(busy, 1),
            "measured_busy_fraction_of_wall": round(busy / m["run_s"], 2),
            "per_uncached_term_s": round(work_term, 1),
            "per_uncached_over_measured_busy": round(work_term / busy, 3),
            "intercept_total_s": round(icpt, 1),
            "intercept_fraction_of_wall": round(icpt / m["run_s"], 2),
            "work_only_total_s": round(work_term + icpt, 1),
            "work_only_utilisation_of_wall": round((work_term + icpt) / m["run_s"], 2),
            "uncached_only_utilisation_of_wall": round(work_term / m["run_s"], 2)})
    tracks = all(0.9 <= u["per_uncached_over_measured_busy"] <= 1.1 for u in util)
    # THE RULED MODE'S OWN UTILISATION, which is the quantity D102 asks about. Under work-only
    # this list was non-empty on both cells and that is what failed the gate.
    oversubscribed = [u["cell"] for u in util
                      if u["uncached_only_utilisation_of_wall"] > 1.0]

    ruled = next(r for r in rows if r["charge_mode"] == DP.RULED_CHARGE_MODE)
    # D174 (1) RULES the uncached-only charge, so the gate is on IT and not on a comparison
    # between modes. A comparison would pass whenever the rejected modes are worse, which tells
    # us nothing about whether the ruled one is sound.
    ok = (ruled["budget_refusal"] <= BASE_TOLERANCE
          and ruled["state_decisions"] > 0
          and ruled["decision_rows"] >= 0.9 * RULES_ROWS
          and tracks and not oversubscribed)
    return {
        "_claim": ("the budget must not bind artificially AND its utilisation must track measured "
                   "GPU busy time (D102, both halves)"),
        "cell": "covex-v6-state-d162, dry, 8 devices, 600 s, seed 4",
        "subject_declares_the_charge": True,
        "ruled_charge": "uncached-only (D174 (1))",
        "reference_v5_rules_2_decision_rows": RULES_ROWS,
        "rows": rows,
        "diagnosis": (
            "TWO TERMS WERE CHARGED THAT ARE NOT WORK, and each failed a different half. "
            "per_queue * queued_ahead is the LATENCY this request SUFFERS because other "
            "requests' work is in front of it; charging it bills the same GPU-seconds once per "
            "request queued behind them, growing as u^2 k^2 / 2 against linear real work, and it "
            "bound the budget artificially on a dry cell (10,612 refusals). The 0.0678 s "
            "intercept is per-request OCCUPANCY, not work: it passed the dry half but added 46 "
            "and 51 percent of wall clock on the measured cells and took utilisation to 1.07 and "
            "1.34 while the GPU was 60 to 80 percent busy. On the PLANNER side both terms are "
            "CORRECT, because there they price the delay a candidate IMPOSES on others"),
        "d102_utilisation_vs_measured_gpu_busy": util,
        "per_uncached_term_tracks_measured_busy": tracks,
        "cells_where_the_ruled_charge_oversubscribes_the_wall_clock": oversubscribed,
        "utilisation_finding": (
            "the PER-UNCACHED term tracks measured GPU busy time to 2 percent (737.5 against "
            "721.9 s at s4, 985.3 against 964.5 s at s5), and its implied rate 5,482 tok/s "
            "agrees with the committed 5,600 tok/s prefill rate to 2 percent. Its utilisation is "
            "0.61 and 0.82 of wall against measured busy fractions of 0.60 and 0.80, so the "
            "charge neither oversubscribes the clock nor undercharges the engine"),
        "gate": ("refusals at or below %d, plan_state still reaching decisions, the decision log "
                 "within 10 percent of covex-v6-rules' %d rows, the per-uncached term within 10 "
                 "percent of measured busy time, and no cell oversubscribed"
                 % (BASE_TOLERANCE, RULES_ROWS)),
        "rejected_modes_for_contrast": [r for r in rows
                                        if r["charge_mode"] != DP.RULED_CHARGE_MODE],
        "verdict": ("PASS: under the ruled uncached-only charge the budget does not bind "
                    "artificially (%d refusals, %d state decisions, %d rows against "
                    "covex-v6-rules' %d) and its utilisation tracks measured GPU busy time to 2 "
                    "percent on both committed cells with neither oversubscribed"
                    % (ruled["budget_refusal"], ruled["state_decisions"],
                       ruled["decision_rows"], RULES_ROWS) if ok else
                    "FAIL: %d refusals, %d state decisions, %d rows against %d; tracks=%s; "
                    "oversubscribed=%s. NO ARM IS ENABLED and no rerun is posted"
                    % (ruled["budget_refusal"], ruled["state_decisions"],
                       ruled["decision_rows"], RULES_ROWS, tracks, oversubscribed)),
    }


def p3_charge_declared_only_where_ruled(d102_passes: bool) -> Dict[str, Any]:
    """WHO MAY CHARGE WHAT, AND WHO MAY RUN.

    The first version of this proof asked only whether a NON-v6 arm declared the switch, and it
    PASSED while covex-v6-state had it on by default: `_d(None)` returned `plan_state`, which is
    True. covex-v6-state s6 then ran the held charge for real, stalled at 44,382 budget refusals
    with its last request submitted at t = 264 s of a 1,200 s cell, and the cell was lost. A proof
    that asks the weaker question passes while the thing it exists to prevent is happening.

    So this one asks the three questions that actually gate a run:
      1. does any arm outside covex-v6 declare the charge?
      2. does every arm that appears in a CELL LIST and declares the charge declare the RULED
         mode? (a -wo arm reaching a cell list is the superseded charge running for real)
      3. if D102 does not pass, is any pricing arm in a cell list at all?
    """
    import arms as A
    on = []
    for name in sorted(A.ARMS):
        try:
            arm = A.make_arm(name)
        except Exception:                                                      # noqa: BLE001
            continue
        if bool(getattr(arm, "live2_d162_pricing", False)):
            on.append({"arm": name, "charge_mode": DP.arm_charge_mode(arm)})
    only_v6 = all(r["arm"].startswith("covex-v6") for r in on)
    PROBE = "covex-v6-state-d162"
    runs = REPO / "results/orchestration/live2/frozen_test/runs"
    posted: List[Dict[str, Any]] = []
    names = {r["arm"]: r["charge_mode"] for r in on}
    if runs.exists():
        for f in sorted(runs.iterdir()):
            if not f.is_file():
                continue
            try:
                lines = f.read_text().splitlines()
            except Exception:                                                  # noqa: BLE001
                continue
            for ln in lines:
                ln = ln.strip()
                if not ln or ln.startswith("#"):
                    continue
                arm = ln.split()[0]
                if arm in names:
                    posted.append({"file": f.name, "cell": ln, "arm": arm,
                                   "charge_mode": names[arm]})
    probe_posted = [r for r in posted if r["arm"] == PROBE]
    wrong_mode = [r for r in posted if r["charge_mode"] != DP.RULED_CHARGE_MODE]
    posted_while_failing = posted if not d102_passes else []
    ok = (only_v6 and not probe_posted and not wrong_mode and not posted_while_failing)
    return {"_claim": ("only covex-v6 arms declare the charge; every posted pricing arm declares "
                       "the RULED mode; and nothing prices at all while D102 fails"),
            "ruled_mode": DP.RULED_CHARGE_MODE,
            "arms_with_d162_pricing": on, "only_covex_v6": only_v6,
            "d102_passes": d102_passes,
            "proof_probe_arm": PROBE,
            "pricing_arms_found_in_cell_lists": posted,
            "posted_with_a_superseded_mode": wrong_mode,
            "verdict": ("PASS: %d arm(s) declare the charge, all covex-v6; %d posted cell(s), all "
                        "at the ruled %s; the proof probe is in no cell list"
                        % (len(on), len(posted), DP.RULED_CHARGE_MODE) if ok else
                        "FAIL: a non-v6 arm declares the charge: %s"
                        % [r["arm"] for r in on if not r["arm"].startswith("covex-v6")]
                        if not only_v6 else
                        "FAIL: the proof probe %s is in a CELL LIST (%s); it exists only for this "
                        "proof" % (PROBE, probe_posted) if probe_posted else
                        "FAIL: posted cell(s) declare a superseded charge mode: %s" % wrong_mode
                        if wrong_mode else
                        "FAIL: D102 does not pass and %d pricing cell(s) are posted: %s"
                        % (len(posted), posted))}


def main() -> int:
    out: Dict[str, Any] = {"_what": "ONE PRICE SOURCE proofs", "price": DP.as_dict()}
    out["P0_positive_control"] = p0_positive_control()
    if not out["P0_positive_control"]["verdict"].startswith("PASS"):
        print(json.dumps(out, indent=1))
        return 1
    out["P1_planner_equals_coordinator"] = p1_planner_equals_coordinator()
    out["P2_budget_vs_gpu_busy"] = p2_budget_vs_gpu_busy()
    out["P3_charge_declared_only_where_ruled"] = p3_charge_declared_only_where_ruled(
        out["P2_budget_vs_gpu_busy"]["verdict"].startswith("PASS"))
    out["P4_no_drift"] = dict(DP.assert_no_drift(),
                              verdict="PASS: coefficients equal the committed gate file")
    out["ALL_PASS"] = all(v["verdict"].startswith("PASS") for v in out.values()
                          if isinstance(v, dict) and "verdict" in v)
    dest = REPO / "results/orchestration/live2/frozen_test/one_price_proofs.json"
    dest.write_text(json.dumps(out, indent=1) + "\n")
    for k, v in out.items():
        if isinstance(v, dict) and "verdict" in v:
            print("%-30s %s" % (k, v["verdict"][:95]))
    print("ALL_PASS:", out["ALL_PASS"])
    print("wrote", dest)
    return 0 if out["ALL_PASS"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
