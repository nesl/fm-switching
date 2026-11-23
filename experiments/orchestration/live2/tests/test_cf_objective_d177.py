#!/usr/bin/env python3
"""Unit tests for the D177 (1) CURRENCY FLIP: the converted path, both of its halves.

A PLAIN SCRIPT, because pytest is NOT installed in the fmtk env; the shape
`tests/test_cf_objective_d191.py` and `d179_share_tests.py` both use. Explicit pass/fail summary
and a NON-ZERO EXIT on any failure, which a caller must check: a wrapper that reads a PASS line
out of the output and not the exit code will report a pass on a crash.

WHAT THESE TESTS ARE FOR, and it is the thing no digest can see. The flip's effect on a dry fleet
cell is nil in magnitude (`cf_objective.CURRENCY_FLIP_STATUS`: 1,595 of 1,596 non-zero harms below
5e-4 against a bar of 0.65824), so arm-level digests come back byte-identical. The arithmetic that
moved is checked here instead, and the two halves are checked TOGETHER, because the failure the
flip exists to prevent is a half-converted comparison: an on-time-unit harm subtracted from a
correctness-unit gain. Every quantity below is a COUNT of expected on-time cloud answers, so the
cases are exact equalities and are asserted with `==` and not with a tolerance. Where a factor is
a power of two (the 4.0 of `1 / 0.250`) the ratio is exact in floating point too, and that is
asserted with `==` deliberately rather than loosened.

THE THREE NUMBERS THAT MUST NOT APPEAR are pinned as what the result must NOT be, the way the
d191 tests pin the window-normalised reading:

    option_value's superseded value      p * 0.25 + (1 - p) * p_dev * 0.071429
    device_only_value's superseded value w * p_dev * 0.071429
    plan_state's superseded gain         w * p_question * 0.250 * (p_warm - p_cold)
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIVE2 = HERE.parent
for p in (str(LIVE2), str(LIVE2 / "fleet"), str(LIVE2 / "v5"), str(LIVE2 / "hybrid"),
          str(LIVE2.parent / "baselines")):
    if p not in sys.path:
        sys.path.insert(0, p)

import cf_margin as CM             # noqa: E402
import cf_objective as CO          # noqa: E402
import cf_planner as CP            # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), str(detail)))
    print(("PASS " if ok else "FAIL ") + name + ((" | " + str(detail)) if detail else ""),
          flush=True)


def close(a, b, tol=1e-12):
    return abs(float(a) - float(b)) <= tol


W_D = 2.75            # a deficit weight that is not 1, so a dropped w would show
ACC_CLOUD = 0.25      # the committed table's cloud_D2
ACC_DEV = 0.071429    # the committed table's device entry
A_FACTOR = 0.25 - 0.071429            # the superseded valuation factor on a difference
GAIN_SCALE = 1.0 / 0.250              # 4.0, exact in binary
HARM_SCALE = 1.0 / A_FACTOR           # 5.6

# ------------------------------------------------------------------ option_value
check("option_value is EXACTLY w * p, a COUNT of on-time cloud answers (==)",
      CO.option_value(W_D, 0.37) == W_D * 0.37
      and CO.option_value(1.0, 0.0) == 0.0
      and CO.option_value(W_D, 1.0) == W_D,
      "%.17g" % CO.option_value(W_D, 0.37))

_grid = [(ac, ad, pd) for ac in (0.0, 0.25, 1.0, 0.9)
         for ad in (0.0, 0.071429, 0.5, 1.0) for pd in (0.0, 0.5, 1.0)]
_vals = {CO.option_value(W_D, 0.37, ac, pd, ad) for ac, ad, pd in _grid}
check("the accuracy and device arguments CANNOT MOVE IT: %d combinations of "
      "(acc_cloud, acc_device, p_device) give ONE value, exactly (==)" % len(_grid),
      len(_vals) == 1 and _vals == {W_D * 0.37},
      "distinct values: %s" % sorted("%.17g" % v for v in _vals))
check("and that is NOT the superseded D155 (3) reading, which is pinned here as the number this "
      "must not produce",
      CO.option_value(W_D, 0.37, ACC_CLOUD, 1.0, ACC_DEV)
      != W_D * (0.37 * ACC_CLOUD + 0.63 * 1.0 * ACC_DEV),
      "superseded would be %.6f, this is %.6f"
      % (W_D * (0.37 * ACC_CLOUD + 0.63 * ACC_DEV), CO.option_value(W_D, 0.37)))
check("the clamp on p survives the flip, so a prediction outside [0, 1] cannot buy or lose value",
      CO.option_value(1.0, 1.7) == 1.0 and CO.option_value(1.0, -0.3) == 0.0)
check("the accuracy arguments are OPTIONAL and DEFAULTED, so a caller that stops passing them "
      "gets the same number rather than a TypeError",
      CO.option_value(W_D, 0.37) == CO.option_value(W_D, 0.37, 1.0, 1.0, 0.0)
      and list(inspect.signature(CO.option_value).parameters) ==
      ["weight", "p_cloud_on_time", "acc_cloud", "p_dev_on_time", "acc_dev"])

# ------------------------------------------------------------------ device_only_value
_dvals = {CO.device_only_value(w, pd, ad) for w in (1.0, W_D)
          for pd in (0.0, 0.5, 1.0) for ad in (0.0, ACC_DEV, 1.0)}
check("device_only_value is EXACTLY 0.0 for every argument: a device answer is not a CLOUD "
      "answer (==, 18 combinations)",
      _dvals == {0.0}, "distinct values: %s" % sorted(_dvals))
check("and it is NOT the superseded w * p_dev * 0.071429, pinned as what it must not produce",
      CO.device_only_value(W_D, 1.0, ACC_DEV) != W_D * ACC_DEV,
      "superseded would be %.6f" % (W_D * ACC_DEV))

# ------------------------------------------------------------------ the harm, one currency
def linear(eng, slack):
    """The DECLARED delivery curve `v5/d177_currency_flip_proofs.py` uses: the fraction of the
    service that fits in the slack. Nothing fitted; it exists so a PARTIAL displacement can be
    constructed, which is where the flip's band is."""
    return max(min(float(slack) / max(float(eng), 1e-9), 1.0), 0.0)


def harm(slack, tokens=1000, acc_cloud=ACC_CLOUD, acc_device=ACC_DEV, eng=0.5):
    return CO.harm_warm_from_queue_delay(
        tokens, [{"req_id": "r1", "device_id": "d1", "engine_s": eng, "slack_s": slack,
                  "weight": W_D, "p_device_on_time": 1.0}],
        p_on_time=linear, acc_cloud=acc_cloud, acc_device=acc_device)


# ONE WHOLE displaced answer needs the added delay to exhaust the whole slack: with the declared
# linear curve that is `slack <= dt`, and `dt = QUEUE_TOKEN_S * 1000 = 0.1536 s`, so a 0.1 s
# service with 0.1 s of slack goes from p = 1.0 to p = 0.0. A 0.0001 s slack would instead give a
# p_before of 0.0002 and a harm of 0.00055, which is a PARTIAL displacement, not a whole one.
h_rung2 = harm(0.1, eng=0.1)
h_rung4 = harm(0.1, eng=0.1, acc_cloud=1.0, acc_device=0.0)
check("ONE DISPLACED ANSWER is EXACTLY w_d under rung 2's accuracy arguments AND under rung 4's: "
      "the currency is the module's, not the caller's (==)",
      h_rung2.total == W_D and h_rung4.total == W_D and h_rung2.total == h_rung4.total,
      "rung2 %.17g rung4 %.17g" % (h_rung2.total, h_rung4.total))
check("which is the 5.6x the flip multiplied rung 2's harm by, and the 1.0x it multiplied "
      "rung 4's by: both measured from the committed table, not declared",
      close(h_rung2.total / (W_D * A_FACTOR), HARM_SCALE, 1e-9)
      and h_rung4.total == W_D * 1.0,
      "5.6x check: %.6f" % (h_rung2.total / (W_D * A_FACTOR)))
h_part = harm(0.35)
_pb, _pa = linear(0.5, 0.35), linear(0.5, 0.35 - h_part.delta_t_s)
check("a PARTIAL displacement is EXACTLY the difference of two option_values, w_d * p_before "
      "minus w_d * p_after (==, in the module's own order of operations: `w * (pb - pa)` is the "
      "same number only to 1e-16, and asserting THAT with == would be asserting a rounding)",
      h_part.total == W_D * _pb - W_D * _pa
      and close(h_part.total, -CO.attainment_delta(W_D, _pa, _pb), 1e-15),
      "%.17g, p %.6f -> %.6f" % (h_part.total, _pb, _pa))
check("NO DISPLACEMENT is still EXACTLY 0.0 and the delay is still charged and reported",
      harm(50.0).total == 0.0 and harm(50.0).n_affected == 0 and harm(50.0).delta_t_s > 0.0)

# ------------------------------------------------------------------ the margin, in on-time units
cf = CP.Counterfactual(counters=CO.DeficitCounters())
m = cf._margin()
check("the planner's bar is MARGIN_CF / A_D2_DEV = 0.65824, EXACTLY (both are committed "
      "constants and the division is by a power of two, so `==` is the right assertion)",
      m.value == float(CM.MARGIN_CF) / CO.A_D2_DEV
      and m.value == CO.attainment_margin(float(CM.MARGIN_CF))
      and round(m.value, 4) == 0.6582,
      "%.17g" % m.value)
check("MARGIN_CF ITSELF IS UNCHANGED by the flip: 0.16456, set once at 2cb2d5c1 (D154 (2)), and "
      "cf_margin.resolve_margin is still its only read",
      float(CM.MARGIN_CF) == 0.16456 and m.source.startswith("cf_margin.MARGIN_CF"),
      m.source)
check("the bar's source NAMES the conversion at the point of use, so a reader cannot mistake "
      "which units the bar is in", "A_D2_DEV" in m.source and "on-time" in m.source, m.source)
_dec = CO.a_d2_dev_declarations()
check("A_D2_DEV is 0.250 and EVERY declaration in the tree agrees, and the audit is NOT vacuous "
      "(at least two declarations found, by a filesystem walk on a git-archive tree)",
      CO.A_D2_DEV == 0.250 and _dec["agree"] is True and _dec["n"] >= 2
      and _dec["distinct_values"] == [0.250],
      "n=%d via %s" % (_dec["n"], _dec["found_how"]))

# ------------------------------------------------------------------ plan_state's gain
def state(harm_warm=0.0, p_question=0.5, p_warm=0.8, p_cold=0.3, accuracy=None, engine=None):
    c = engine or cf
    return c.plan_state(decision_id="t", device_id="robo000", now_s=0.0,
                        p_question=p_question, next_question_s=2.0,
                        p_on_time_warm=p_warm, p_on_time_cold=p_cold,
                        harm_warm=harm_warm, harm_touch=harm_warm, accuracy=accuracy,
                        warm_expressible=True, host_warm=True)


d = state()
_warm = next(c for c in d.candidates if c.name == "WARM")
check("plan_state's gain is EXACTLY w * p_question * (p_warm - p_cold), with NO accuracy factor "
      "(==): 1.0 * 0.5 * (0.8 - 0.3) = 0.25",
      _warm.gain == 1.0 * 0.5 * (0.8 - 0.3) and _warm.gain == 0.25,
      "%.17g" % _warm.gain)
check("and it is NOT the superseded gain, which carried acc = 0.250 inline and is pinned here as "
      "the number this must not produce",
      _warm.gain != 1.0 * 0.5 * 0.250 * (0.8 - 0.3),
      "superseded would be %.17g" % (1.0 * 0.5 * 0.250 * (0.8 - 0.3)))
_g2 = next(c for c in state(accuracy=0.9).candidates if c.name == "WARM").gain
check("passing a DIFFERENT accuracy gives the SAME gain, so the quality table is reporting only "
      "(D177 (2)) and not a decision input (==)",
      _g2 == _warm.gain, "%.17g vs %.17g" % (_g2, _warm.gain))
check("the accuracy is still REPORTED on the candidate, and marked as not entering the value, so "
      "its removal from the arithmetic is visible rather than silent",
      _warm.detail.get("accuracy") == 0.25
      and _warm.detail.get("accuracy_enters_value") is False
      and "on-time" in str(_warm.detail.get("value_units")),
      str({k: _warm.detail.get(k) for k in
           ("accuracy", "accuracy_enters_value", "value_units")}))

# ------------------------------------------------------------------ what moves and what cannot
check("WITH harm = 0 THE COMPARISON IS EXACTLY SCALE INVARIANT, so no decision can move: the "
      "gain and the bar are both 4.0x their superseded values and 4.0 is exact in binary (==)",
      _warm.gain == GAIN_SCALE * (1.0 * 0.5 * 0.250 * (0.8 - 0.3))
      and m.value == GAIN_SCALE * float(CM.MARGIN_CF)
      and (_warm.gain / m.value) == ((1.0 * 0.5 * 0.250 * (0.8 - 0.3)) / float(CM.MARGIN_CF)),
      "ratio %.17g" % (_warm.gain / m.value))

# the band, and the grid's first moved decision reproduced as a unit test. harm_new = 0.7 is one
# partial displacement of 0.7 of an answer at w = 1; before the flip the same displacement was
# priced 0.7 * 0.178571 = 0.125, which is BELOW 0.16456, so HOLD_BACK did not clear the bar.
_harm_new = 0.7
_harm_old = _harm_new * A_FACTOR
d_band = state(harm_warm=_harm_new, p_question=0.02, p_warm=0.9, p_cold=0.85)
check("THE BAND MOVES A DECISION: at a harm of 0.7 on-time answers HOLD_BACK clears the 0.65824 "
      "bar and is CHOSEN, while the same displacement priced the old way (0.125) did not clear "
      "0.16456 - the grid's first moved decision, reproduced here",
      d_band.chosen == "HOLD_BACK" and d_band.deviated is True
      and _harm_old < float(CM.MARGIN_CF) and _harm_new > m.value,
      "new %.5f > %.5f, old %.5f < %.5f" % (_harm_new, m.value, _harm_old, float(CM.MARGIN_CF)))
check("and the band's lower edge is MARGIN_CF / 1.4 = 0.11754 in old units: the harm-to-bar "
      "ratio moves by exactly 5.6 / 4.0",
      close(HARM_SCALE / GAIN_SCALE, 1.4, 1e-4)
      and close(float(CM.MARGIN_CF) / (HARM_SCALE / GAIN_SCALE), 0.11754, 1e-5),
      "1.4 = %.6f, lower edge %.6f"
      % (HARM_SCALE / GAIN_SCALE, float(CM.MARGIN_CF) / (HARM_SCALE / GAIN_SCALE)))
d_below = state(harm_warm=0.5, p_question=0.02, p_warm=0.9, p_cold=0.85)
check("BELOW the bar HOLD_BACK is still refused, so the bar is a bar and not a rubber stamp",
      d_below.chosen == "KEEP" and d_below.deviated is False, d_below.chosen)

# ------------------------------------------------------------------ NEGATIVE CONTROL (Step 4)
cf_inf = CP.Counterfactual(counters=CO.DeficitCounters(), dry=True, dry_margin=1e9)
cf_zero = CP.Counterfactual(counters=CO.DeficitCounters(), dry=True, dry_margin=0.0)
d_inf = state(harm_warm=_harm_new, p_question=0.02, p_warm=0.9, p_cold=0.85, engine=cf_inf)
d_zero = state(harm_warm=0.0001, p_question=0.02, p_warm=0.9, p_cold=0.85, engine=cf_zero)
check("CONTROL: with the bar at infinity the SAME inputs choose KEEP, and with the bar at zero a "
      "tiny gain deviates; so the bar is what decides and the moved decision above is not an "
      "artefact of the inputs",
      d_inf.chosen == "KEEP" and d_inf.deviated is False and d_zero.deviated is True,
      "inf -> %s, zero -> %s (deviated %s)" % (d_inf.chosen, d_zero.chosen, d_zero.deviated))
check("CONTROL: the dry bar is CONVERTED too, so a dry proof tests the comparison a cell makes "
      "and not one a quarter of its size",
      cf_inf._margin().value == 1e9 / CO.A_D2_DEV
      and cf_inf._margin().scorable is False,
      "%.17g" % cf_inf._margin().value)

# ------------------------------------------------------------------ the statements of record
check("CURRENCY_FLIP_STATUS says CLOSED and still names plan_state, so the module records that "
      "the two halves landed together",
      CO.CURRENCY_FLIP_STATUS.startswith("CLOSED") and "plan_state" in CO.CURRENCY_FLIP_STATUS
      and "UNEXERCISED IN MAGNITUDE" in CO.CURRENCY_FLIP_STATUS)
check("the objective of record is ON-TIME CLOUD ANSWERS and names correctness as the OUTCOME",
      "ON-TIME CLOUD ANSWERS" in CO.OBJECTIVE_STATEMENT
      and "correctness is the OUTCOME" in CO.OBJECTIVE_STATEMENT, CO.OBJECTIVE_STATEMENT)
check("the planner declares its units at module level, so a later reader does not have to infer "
      "them from the arithmetic",
      "on-time cloud answers" in CP.VALUE_UNITS and "0.65824" in CP.MARGIN_UNITS)
check("gap G14 is recorded as CLOSED where it was recorded as open: the counters steer on the "
      "same quantity the objective scores",
      "CLOSED" in CO.DeficitCounters().as_dict()["mismatch"]
      and CO.DeficitCounters().as_dict()["objective_scores"] == "on-time cloud answers (D177 (1))")

# ------------------------------------------------------------------ POSITIVE CONTROL (check 7)
check("POSITIVE CONTROL: this instrument CAN see a decision move. Two plan_state calls that "
      "differ only in a harm above and below the bar give different chosen candidates; if they "
      "did not, every equality above would be meaningless",
      state(harm_warm=0.7, p_question=0.02, p_warm=0.9, p_cold=0.85).chosen
      != state(harm_warm=0.5, p_question=0.02, p_warm=0.9, p_cold=0.85).chosen)

nfail = sum(1 for _, ok, _ in RESULTS if not ok)
print("")
print("%d checks, %d PASS, %d FAIL" % (len(RESULTS), len(RESULTS) - nfail, nfail))
if nfail:
    for n, ok, dd in RESULTS:
        if not ok:
            print("  FAIL: %s | %s" % (n, dd))
raise SystemExit(1 if nfail else 0)
