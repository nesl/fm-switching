#!/usr/bin/env python3
"""Unit tests for the four D165 (A) functions landed under D191 (1), and for the UNITS of the
margin they are compared against.

A PLAIN SCRIPT, because pytest is NOT installed in the fmtk env. Explicit pass/fail summary and a
non-zero exit on any failure, the shape `tests/test_deficit_feed.py` and `d179_share_tests.py`
both use.

WHAT THESE TESTS ARE FOR, and it is the units and not the policy. The gate D190 asks for and
D191 (1) RULES is

    deviate iff (weighted gain - weighted harm) > w_d * MARGIN_CF,  MARGIN_CF = 0.6582

with gain and harm BOTH counts of expected on-time cloud answers, each device weighted by its own
w_d (D185: `w_d = 1 + 2.0 * shortfall_d / target_d`), and NO division by the number served -
because the target normalisation already lives inside w_d, and dividing again would put the
left-hand side three orders of magnitude below the bar. A gate that never opens is CLAUDE.md
Rule 2's `unscorable`; it produces a believable null rather than a crash, and NO BYTE-IDENTITY
DIGEST CAN SEE IT. These tests are the only check that can.

HOW THE ON-TIME UNITS ARE OBTAINED, UPDATED BY THE D177 (1) CURRENCY FLIP. When these tests were
written the flip was not in any commit and the units came from the CALL:
`harm_warm_from_queue_delay` with `acc_cloud=1.0, acc_device=0.0` evaluated the then-committed
`option_value` to `w * (p * 1.0 + (1 - p) * p_dev * 0.0)` = `w * p`, which is the on-time form,
and that is what `cf_protect_defer.harm_on_time` passes. SINCE THE FLIP the units come from
`option_value` ITSELF, which is `w * p` for every caller and reads no accuracy at all, so rung 4's
numbers are unchanged (1.0x) and rungs 2 and 3 moved onto the same currency (5.6x on a harm priced
with the device fallback). Three checks below were rewritten with the flip and say so where they
stand; everything else in this file passed before and after it, unchanged.

Because the units are COUNTS, the two cases the user named are exact equalities and are asserted
with `==` rather than a tolerance:

    NO DISPLACEMENT          -> harm exactly 0.0
    ONE DISPLACED ANSWER     -> harm exactly w_d        (p_before 1.0 -> p_after 0.0)

Accuracy-weighted the second would be `w_d * (a_c - a_d)`; window-normalised it would be
`w_d / served`. It is neither. Both wrong readings are pinned below as numbers the test must NOT
produce, so a regression to either fails loudly instead of quietly.

The exact-primary / margin-primary question is SETTLED AND DISSOLVED by D191 (1): one comparison
decides, a secondary key breaks EXACT ties only, and no reading switch exists to be chosen. That
absence is itself asserted.
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

import cf_margin as CM                # noqa: E402
import cf_objective as CO             # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), str(detail)))
    print(("PASS " if ok else "FAIL ") + name + ((" | " + str(detail)) if detail else ""),
          flush=True)


def close(a, b, tol=1e-12):
    return abs(float(a) - float(b)) <= tol


W_D = 2.75          # a deficit weight that is not 1, so a dropped w would show


def p_step(_eng, slack):
    """A driven on-time curve: on time iff any slack is left. Nothing fitted is involved."""
    return 1.0 if float(slack) > 0.0 else 0.0


def others(slack):
    return [{"req_id": "r1", "device_id": "d1", "engine_s": 0.1, "slack_s": slack,
             "weight": W_D, "p_device_on_time": 1.0}]


def harm_on_time(slack, tokens=1000):
    """The harm EXACTLY as `cf_protect_defer.harm_on_time` computes it: acc 1.0 / 0.0."""
    return CO.harm_warm_from_queue_delay(tokens, others(slack), p_on_time=p_step,
                                         acc_cloud=1.0, acc_device=0.0)


# ------------------------------------------------- the two constructed cases the user named
h0 = harm_on_time(50.0)
check("NO DISPLACEMENT -> harm is EXACTLY 0.0 and no row is emitted (asserted with ==, not a "
      "tolerance: the units are COUNTS, so the case is an exact equality)",
      h0.total == 0.0 and h0.n_affected == 0 and h0.rows == (),
      "total=%r rows=%d" % (h0.total, h0.n_affected))
check("and the delay was still CHARGED and is reported, so a zero harm is not a silent refusal "
      "to price", h0.delta_t_s > 0.0, "dt=%.6f s" % h0.delta_t_s)

h1 = harm_on_time(0.0001)
check("ONE DISPLACED ON-TIME ANSWER -> harm is EXACTLY w_d, a COUNT of answers (==)",
      h1.total == W_D and h1.n_affected == 1,
      "total=%.17g want %.17g" % (h1.total, W_D))
check("and it is NOT either wrong reading: not accuracy-weighted, not window-normalised",
      not close(h1.total, W_D * (0.25 - 0.071429), 1e-9)
      and not close(h1.total, W_D / 1200.0, 1e-9),
      "accuracy-weighted would be %.6f, window-normalised %.6f"
      % (W_D * (0.25 - 0.071429), W_D / 1200.0))
check("the delay is the IMPORTED queued-ahead price times the tokens, not a local literal",
      close(h1.delta_t_s, CO.QUEUE_TOKEN_S * 1000) and "d162_price" in CO.QUEUE_TOKEN_S_SOURCE,
      CO.QUEUE_TOKEN_S_SOURCE)
check("a delay beyond the D160 (2) healthy bound is CAPPED and the cap is COUNTED, not silent",
      CO.harm_warm_from_queue_delay(10 ** 9, others(0.0001), p_on_time=p_step, acc_cloud=1.0,
                                    acc_device=0.0).capped is True)

# REWRITTEN BY THE D177 (1) FLIP, and the superseded reading is kept in the text because it is
# what these three checks asserted before it. The unit used to be obtained FROM THE CALL: the same
# displacement under rung 2's accuracy arguments returned `w_d * (0.25 - 0.071429) = 0.491070`, the
# correctness currency, and that 5.6x gap was the measured reason the flip could not land on one
# side alone. It now returns `w_d` whatever accuracy is passed, which is the flip.
h1_corr = CO.harm_warm_from_queue_delay(1000, others(0.0001), p_on_time=p_step,
                                        acc_cloud=0.25, acc_device=0.071429)
check("SINCE D177 (1) the SAME displacement under rung 2/3's accuracy arguments is EXACTLY w_d "
      "too: the currency is the module's, not the caller's (==, the units are counts)",
      h1_corr.total == W_D and h1_corr.total == h1.total,
      "rung-2 args %.17g, rung-4 args %.17g, superseded correctness reading %.6f"
      % (h1_corr.total, h1.total, W_D * (0.25 - 0.071429)))
check("and the 5.6x that USED to separate them is exactly what the flip multiplied rung 2/3's "
      "harm by, which CURRENCY_FLIP_STATUS records as CLOSED together with plan_state's gain",
      close(h1_corr.total / (W_D * (0.25 - 0.071429)), 1.0 / (0.25 - 0.071429), 1e-6)
      and "plan_state" in CO.CURRENCY_FLIP_STATUS
      and CO.CURRENCY_FLIP_STATUS.startswith("CLOSED"),
      "%.4f" % (h1_corr.total / (W_D * (0.25 - 0.071429))))
check("option_value returns w * p, the on-time form, which it did under acc 1.0 / 0.0 before the "
      "flip and now does for EVERY accuracy argument (asserted exhaustively in "
      "test_cf_objective_d177.py)",
      close(CO.option_value(W_D, 0.37, 1.0, 1.0, 0.0), W_D * 0.37)
      and close(CO.option_value(1.0, 0.0, 1.0, 1.0, 0.0), 0.0))

# ---------------------------------------------------------- the margin: D177 (3)'s arithmetic
m = CO.attainment_margin(float(CM.MARGIN_CF))
check("attainment_margin(MARGIN_CF) = 0.16456 / 0.250 = 0.65824, D177 (3)'s 0.6582",
      close(m, 0.16456 / 0.250) and round(m, 4) == 0.6582, "%.17g" % m)
check("MARGIN_CF itself is UNCHANGED by this work: 0.16456, set once at 2cb2d5c1 (D154 (2))",
      close(float(CM.MARGIN_CF), 0.16456))
_dec = CO.a_d2_dev_declarations()
check("A_D2_DEV is 0.250, EVERY declaration in the tree is parsed and they agree - and the audit "
      "is NOT vacuous: at least two declarations were found",
      close(CO.A_D2_DEV, 0.250) and _dec["agree"] is True and _dec["n"] >= 2
      and _dec["distinct_values"] == [0.250],
      "n=%d via %s: %s" % (_dec["n"], _dec["found_how"], sorted(_dec["declarations"])))
check("zero declarations would NOT be reported as agreement (an impossible success)",
      "EXACTLY ONE distinct value" in _dec["note"])
check("the margin's source names margin_cf_d169, the script that COMPUTED MARGIN_CF",
      "margin_cf_d169" in CO.A_D2_DEV_SOURCE)

# THE DIMENSIONAL CHECK THE GATE TURNS ON. One whole displaced answer at w = 1 must be ABOVE the
# bar at w = 1, and a thousandth of an answer BELOW it: a bar that fails either way is a bar in
# the wrong units, and it is this test and not a digest that would catch it.
def harm_w1(pb, pa):
    return CO.attainment_delta(1.0, pb, pa)


check("ONE displaced answer at w = 1 CLEARS the w = 1 bar, so the gate CAN open",
      harm_w1(1.0, 0.0) > m, "%.5f > %.5f" % (harm_w1(1.0, 0.0), m))
check("a THOUSANDTH of an answer does NOT clear it, so the bar is a bar and not a rubber stamp",
      harm_w1(0.001, 0.0) < m)
check("the bar is NOT in rate units: one instant of a 1,200-instant window moves an attainment "
      "RATE by 1/1200, which is 1.27e-3 of this bar - three orders down, so a rate-unit "
      "comparison could never fire",
      (1.0 / 1200.0) / m < 2e-3,
      "ratio=%.3g (1/1200 = %.3g vs bar %.5f)" % ((1.0 / 1200.0) / m, 1.0 / 1200.0, m))

# ------------------------------------------------- D191 (1): attainment_delta and lex_better
check("attainment_delta takes NO `served` argument, so the twice-normalised rate is "
      "UNCONSTRUCTIBLE rather than merely discouraged",
      "served" not in inspect.signature(CO.attainment_delta).parameters,
      str(inspect.signature(CO.attainment_delta)))
check("attainment_delta is w * (p_cf - p_base), a COUNT, and EQUALS the difference of two "
      "option_values taken in on-time units: one currency, not two",
      CO.attainment_delta(W_D, 0.9, 0.5)
      == CO.option_value(W_D, 0.9, 1.0, 1.0, 0.0) - CO.option_value(W_D, 0.5, 1.0, 1.0, 0.0)
      and close(CO.attainment_delta(W_D, 0.9, 0.5), W_D * 0.4),
      "%.17g" % CO.attainment_delta(W_D, 0.9, 0.5))
check("attainment_delta is EXACTLY the harm arithmetic with the sign reversed, so gain and harm "
      "are the same currency by construction and not by agreement",
      close(CO.attainment_delta(W_D, 0.0, 1.0), -h1.total, 1e-12),
      "delta=%.6f harm=%.6f" % (CO.attainment_delta(W_D, 0.0, 1.0), h1.total))
check("the twice-normalised form would NOT clear the bar even for a whole answer, which is the "
      "inert gate D191 (1) removed",
      (CO.attainment_delta(1.0, 1.0, 0.0) / 1200.0) < m)


class _Dev:
    def __init__(self, served):
        self.served = served


class _Counters:
    def __init__(self, **kw):
        self.devices = {k: _Dev(v) for k, v in kw.items()}


check("served_in_window returns the window denominator and FLOORS AT 1, the correct limit for a "
      "device with nothing served yet",
      CO.served_in_window(_Counters(d1=1200, d2=4), "d1") == 1200
      and CO.served_in_window(_Counters(d1=1200, d2=4), "d2") == 4
      and CO.served_in_window(_Counters(d1=1200), "unseen") == 1
      and CO.served_in_window(None, "d1") == 1)
check("served_in_window's docstring MARKS ITS REGISTER: no production read, D122 (B)'s window "
      "for reporting, and explicitly NOT a divisor on the gate",
      "NOTHING IN THE DECISION PATH READS IT" in (CO.served_in_window.__doc__ or "")
      and "NOT A DIVISOR ON THE GATE" in (CO.served_in_window.__doc__ or ""))

check("lex_better decides on the ON-TIME COUNT alone when the counts differ",
      CO.lex_better((2.0, 0.0), (1.0, 99.0)) is True
      and CO.lex_better((1.0, 99.0), (2.0, 0.0)) is False)
check("the secondary key breaks EXACT ties ONLY, and a tie is not 'better than' itself",
      CO.lex_better((1.0, 0.9), (1.0, 0.4)) is True
      and CO.lex_better((1.0, 0.4), (1.0, 0.9)) is False
      and CO.lex_better((1.0, 0.4), (1.0, 0.4)) is False)
check("a count difference BELOW the margin still decides this ordering: the margin gates the "
      "DEVIATION, not the comparison (D191 (1): one comparison decides)",
      CO.lex_better((1e-9, 0.0), (0.0, 99.0)) is True)
check("NO reading switch is offered for a settled question, and the superseded concern is "
      "RECORDED AS RESOLVED rather than deleted (D191 (1))",
      not hasattr(CO, "LEX_READINGS") and not hasattr(CO, "LEX_READING_DEFAULT")
      and "D191 (1)" in CO.LEX_READING
      and "RESOLVED, not deleted" in CO.LEX_READING_SUPERSEDED_CONCERN)
check("lex_better accepts NO margin argument, so margin-primary is unconstructible",
      list(inspect.signature(CO.lex_better).parameters) == ["cand", "incumbent"],
      str(inspect.signature(CO.lex_better)))

# --------------------------------------- NEGATIVE CONTROL (CLAUDE.md Step 4), on THIS mechanism
# The mechanism this commit adds is the BAR. Disable it by driving the margin to zero and to
# infinity and confirm the comparison it gates collapses both ways; if the verdict did not move,
# the bar would not be the thing deciding.
_one = CO.attainment_delta(1.0, 1.0, 0.0)
check("CONTROL: with the bar at 0 the deviation always clears; with the bar at infinity it never "
      "does; so the bar is what decides and is not decorative",
      (_one > CO.attainment_margin(0.0)) and not (_one > CO.attainment_margin(float("inf"))),
      "one answer = %.5f, bar(0) = %.5f, bar(inf) = %s"
      % (_one, CO.attainment_margin(0.0), CO.attainment_margin(float("inf"))))
check("CONTROL: attainment_margin is LINEAR in MARGIN_CF, so a bar quoted in correctness units "
      "cannot accidentally reproduce the on-time one unless a_D2_DEV is 1",
      close(CO.attainment_margin(2 * float(CM.MARGIN_CF)), 2 * m)
      and not close(m, float(CM.MARGIN_CF)))

# --------------------------------------------------------------------- summary
nfail = sum(1 for _, ok, _ in RESULTS if not ok)
print("")
print("%d checks, %d PASS, %d FAIL" % (len(RESULTS), len(RESULTS) - nfail, nfail))
if nfail:
    for n, ok, d in RESULTS:
        if not ok:
            print("  FAIL: %s | %s" % (n, d))
raise SystemExit(1 if nfail else 0)
