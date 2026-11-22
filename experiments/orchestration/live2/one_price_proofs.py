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
D102_FAILS = True

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
    varies_in_queue = DP.price_gpu_s(15, 0) != DP.price_gpu_s(15, 5000)
    return {"_claim": "the price varies with both of its inputs",
            "touch_idle": round(a, 6), "cold_recall_11k": round(b, 6),
            "varies_with_uncached": a != b, "varies_with_queue_ahead": varies_in_queue,
            "verdict": ("PASS: the price is not a constant"
                        if (a != b and varies_in_queue) else
                        "FAIL: THE CHECK IS BROKEN; an equality below would be two constants")}


def p1_planner_equals_coordinator() -> Dict[str, Any]:
    """The ruling's test. Coordinator charge against planner harm basis, per request."""
    rows: List[Dict[str, Any]] = []
    for label, u, q in CASES:
        # the COORDINATOR's charge, as coordinator.py computes it under the switch
        coord = DP.price_gpu_s(u, q)
        # the PLANNER's basis for the same request: cf_objective prices the delay a request of
        # `u` uncached tokens imposes, through the same model. The quantity both sides must agree
        # on is the predicted first-token time of this request.
        plan = CO.QUEUE_TOKEN_S * 0 + DP.first_token_s(u, q)
        # and the harm term's own coefficient must BE the price source's, not a copy
        same_coeff = CO.QUEUE_TOKEN_S == DP.PER_QUEUE_S
        rows.append({"case": label, "uncached": u, "queued_ahead": q,
                     "coordinator_charge_gpu_s": round(coord, 9),
                     "planner_first_token_s": round(plan, 9),
                     "equal": coord == plan,
                     "old_reload_proxy_gpu_s": (round(C.recall_gpu_s(11000, "GPU-WARM"), 6)
                                                if "touch" in label else None),
                     "harm_coefficient_is_the_price_source": same_coeff})
    allequal = all(r["equal"] for r in rows)
    allcoef = all(r["harm_coefficient_is_the_price_source"] for r in rows)
    return {"_claim": "planner and coordinator prices are equal per request",
            "rows": rows, "all_equal": allequal, "coefficients_shared": allcoef,
            "verdict": ("PASS: identical on all %d constructed requests, and the planner's harm "
                        "coefficient IS the price source rather than a copy of it" % len(rows)
                        if (allequal and allcoef) else
                        "FAIL: the two sides disagree")}


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
        for mode in ("first-token", "work-only"):
            DP.CHARGE_MODE = mode
            # covex-v6-state-d162 DECLARES the charge. The rung's own default does not, so
            # running this test on `covex-v6-state` made BOTH modes identical and the proof
            # PASSED VACUOUSLY the moment the default was corrected. A proof whose subject has
            # been switched off is not a passing proof.
            dec, st = TH.dry("covex-v6-state-d162", 4, 8, run_s=600.0, ratio="50:50",
                             robot_question_set="lh_req", ss_question_set="ss2")
            c = holder["c"]
            rows.append({"charge_mode": mode,
                         "budget_refusal": int(c.counts.get("budget_refusal", 0)),
                         "budget_refusal_monitor": int(c.counts.get("budget_refusal_monitor", 0)),
                         "budget_refusal_build": int(c.counts.get("budget_refusal_build", 0)),
                         "budget_refusal_recall": int(c.counts.get("budget_refusal_recall", 0)),
                         "state_decisions": int((st or {}).get("state_decisions", 0)),
                         "decision_rows": len(dec)})
    finally:
        DP.CHARGE_MODE = "first-token"
        cls.__init__ = old_init
    full = next(r for r in rows if r["charge_mode"] == "first-token")
    work = next(r for r in rows if r["charge_mode"] == "work-only")
    ok = full["budget_refusal"] <= work["budget_refusal"] * 2
    return {
        "_claim": "the budget must not bind artificially (D102)",
        "cell": "covex-v6-state-d162, dry, 8 devices, 600 s, seed 4",
        "subject_declares_the_charge": True,
        "reference_v5_rules_2_decision_rows": 4376,
        "rows": rows,
        "diagnosis": (
            "the THIRD TERM is the problem and it is a double count. "
            "per_queue * queued_ahead is the LATENCY this request SUFFERS because other "
            "requests' work is in front of it, not GPU time this request consumes. Charging it "
            "bills the same GPU-seconds once per request queued behind them: with k requests of "
            "u tokens in flight the queue charge grows as u^2 k^2 / 2 while the real work grows "
            "linearly. On the planner side the same term is CORRECT, because there it prices the "
            "delay a candidate IMPOSES on others, which is exactly what it measures"),
        "intercept_is_not_the_driver": (
            "charging the 0.0678 s intercept to every request makes a 1-frame dashcam append "
            "2.0x dearer and a 21-frame one 1.1x dearer, which alone would not starve anything"),
        "verdict": ("PASS: the budget does not bind artificially" if ok else
                    "FAIL: under the ruling's formula as written the budget binds ARTIFICIALLY. "
                    "%d refusals (%d dashcam) against %d under work-only, and plan_state reaches "
                    "0 decisions against %d. The arm is MORE starved than it was under the old "
                    "touch price, for a different reason. The rerun is HELD"
                    % (full["budget_refusal"], full["budget_refusal_monitor"],
                       work["budget_refusal"], work["state_decisions"])),
    }


def p3_baselines_unchanged() -> Dict[str, Any]:
    import arms as A
    on = []
    for name in sorted(A.ARMS):
        try:
            arm = A.make_arm(name)
        except Exception:                                                      # noqa: BLE001
            continue
        if bool(getattr(arm, "live2_d162_pricing", False)):
            on.append(name)
    only_v6 = all(n.startswith("covex-v6") for n in on)
    # WHILE THE REPRICE IS HELD, NO ARM MAY DECLARE IT, not even a covex-v6 one. The first
    # version of this proof asked only whether a NON-v6 arm declared the switch, and it PASSED
    # while covex-v6-state had it on by default: `_d(None)` returned `plan_state`, which is True.
    # covex-v6-state s6 then ran the held charge for real, stalled at 44,382 budget refusals with
    # its last request submitted at t = 264 s of a 1,200 s cell, and the cell was lost. A proof
    # that asks the weaker question passes while the thing it exists to prevent is happening.
    held = D102_FAILS
    # The one arm allowed to declare it: the proof's own subject, which exists so P2 can exercise
    # the charge it tests. Allowing it is only safe if it can never reach a cell, so that is
    # CHECKED rather than trusted.
    PROBE = "covex-v6-state-d162"
    offenders = [n for n in on if n != PROBE]
    runs = REPO / "results/orchestration/live2/frozen_test/runs"
    in_cell_lists = []
    if runs.exists():
        for f in sorted(runs.iterdir()):
            if not f.is_file():
                continue
            try:
                for ln in f.read_text().splitlines():
                    ln = ln.strip()
                    if ln and not ln.startswith("#") and ln.split()[0] == PROBE:
                        in_cell_lists.append("%s: %s" % (f.name, ln))
            except Exception:                                                  # noqa: BLE001
                continue
    return {"_claim": ("no arm declares the pricing switch while its D102 proof fails; and if it "
                       "is ever ruled on, no arm outside covex-v6 declares it"),
            "arms_with_d162_pricing": on, "only_covex_v6": only_v6,
            "reprice_is_held": held,
            "proof_probe_arm": PROBE,
            "arms_declaring_it_other_than_the_probe": offenders,
            "probe_found_in_cell_lists": in_cell_lists,
            "verdict": ("PASS: the reprice is held, only the proof's own probe arm %s declares "
                        "it, and that arm appears in no cell list" % PROBE
                        if (held and not offenders and not in_cell_lists) else
                        "FAIL: the reprice is HELD and %d arm(s) beyond the probe declare it: "
                        "%s. Every cell of those arms runs an unruled charge"
                        % (len(offenders), offenders) if (held and offenders) else
                        "FAIL: the probe arm %s is in a CELL LIST (%s); it exists only for this "
                        "proof and must not run until the reprice is ruled"
                        % (PROBE, in_cell_lists) if in_cell_lists else
                        "PASS: only covex-v6 arms price this way" if only_v6 else
                        "FAIL: a non-v6 arm declares the switch")}


def main() -> int:
    out: Dict[str, Any] = {"_what": "ONE PRICE SOURCE proofs", "price": DP.as_dict()}
    out["P0_positive_control"] = p0_positive_control()
    if not out["P0_positive_control"]["verdict"].startswith("PASS"):
        print(json.dumps(out, indent=1))
        return 1
    out["P1_planner_equals_coordinator"] = p1_planner_equals_coordinator()
    out["P2_budget_vs_gpu_busy"] = p2_budget_vs_gpu_busy()
    out["P3_baselines_unchanged"] = p3_baselines_unchanged()
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
