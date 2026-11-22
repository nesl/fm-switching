#!/usr/bin/env python3
"""D178 (2): THE ONE DECLARED DEFICIT GAIN, pre-registered BEFORE any covex-v6-fair cell runs.

D178 (2) requires "one value declared before any covex-v6-fair / covex-v6 cell, swept later as
sensitivity (0.5x, 2x)". This module is that declaration. It is committed and pushed BEFORE the
first cell of the deficit feed is run, so the value cannot be chosen after seeing a result. It
holds the value and nothing else: no reader of it may compute a different gain, and the sweep
values are recorded here so that a later sensitivity run cannot be mistaken for the declared one.

    w_t = 1 + GAIN * shortfall_t,   floored at 1,   per query type t

    GAIN = 2.0

WHY 2.0, AS THE USER'S JUSTIFICATION RECORDS IT. At gain 2.0 a type sitting at HALF its target
carries weight 2, so it counts double. The weight range is bounded at 1 to 3, because a shortfall
is at most 1 (it is a clipped difference of two rates in [0, 1], `max(target - attainment, 0)`,
and every target is below 1). A 3x range cannot let one type monopolise the accelerator, because
D179's floors already guarantee every other type a minimum share: the weights split the FLEXIBLE
pool only (1,802.6 of 4,323.3 uncached tokens, 41.7 percent, `share_capacity.FLEXIBLE_TOKENS`),
and the floors (0.30 / 0.30 / 0.15 of W_max as tokens) are not weighted at all.

THE FLOOR AT 1 IS PART OF THE DECLARATION, not an implementation detail. A type ahead of its
target is not worth LESS than a type at its target; it is simply not worth more. Letting w fall
below 1 would make the split trade an on-time answer for a fairness statistic, which D149 (1)
forbids and which `cf_objective.DeficitCounters.weight` already records in the same words.

WHAT IS AND IS NOT SWEPT. D178 (2) sets the sweep AFTER the core grid: 0.5x and 2x of the declared
value, so 1.0 and 4.0. Those are SENSITIVITY values and carry their own names; neither may be used
for a headline. A run at any gain other than GAIN must say so in its own cell name, which is why
the arm takes the gain as a constructor argument and defaults it to this constant rather than
reading a module global that any path could move (the failure `d162_price.arm_charge_mode` records).

GAIN 0.0 IS NOT A SWEEP VALUE. It is CLAUDE.md Step 4's negative control: at gain 0 every weight is
exactly 1.0, the flexible pool splits equally, and the arm must collapse to its rung-2 base
byte-identically. It is listed separately for that reason and must never be reported as a
sensitivity point.
"""
from __future__ import annotations

from typing import Dict

# ---- THE DECLARED VALUE (D178 (2)). One number, one place, never recomputed.
GAIN = 2.0

GAIN_DECLARED_ON = "2026-11-22"
GAIN_RULING = "D178 (2)"
GAIN_SOURCE = (
    "user's flash addendum 9 item B1, 2026-11-22, pre-registered: at gain 2.0 a type at HALF its "
    "target carries weight 2 and so counts double; the weight range is bounded at 1 to 3 because "
    "a shortfall is at most 1; a 3x range cannot let one type monopolise, because D179's floors "
    "already guarantee the other types a minimum and only the FLEXIBLE pool is weighted")

# The weight range the declaration claims, as an assertion rather than a sentence.
WEIGHT_MIN = 1.0
WEIGHT_MAX = 1.0 + GAIN * 1.0          # shortfall <= 1 by construction

# D178 (2) sensitivity, AFTER the core grid. Not headline values.
SWEEP_LATER: Dict[str, float] = {"0.5x": 0.5 * GAIN, "2x": 2.0 * GAIN}
# CLAUDE.md Step 4 negative control, not a sweep point.
NEGATIVE_CONTROL_GAIN = 0.0

assert WEIGHT_MAX == 3.0, "the declared justification claims a 1 to 3 weight range"


def weight(shortfall: float, gain: float = GAIN) -> float:
    """`w = 1 + gain * shortfall`, floored at 1. The ONE implementation of the declared form."""
    s = float(shortfall)
    if s < 0.0:
        s = 0.0
    elif s > 1.0:
        s = 1.0
    return 1.0 + float(gain) * s


def as_dict() -> Dict[str, object]:
    return {"gain": GAIN, "ruling": GAIN_RULING, "declared_on": GAIN_DECLARED_ON,
            "source": GAIN_SOURCE, "form": "w_t = 1 + gain * shortfall_t, floored at 1",
            "weight_range": [WEIGHT_MIN, WEIGHT_MAX],
            "sweep_later": dict(SWEEP_LATER),
            "negative_control_gain": NEGATIVE_CONTROL_GAIN,
            "weighted_quantity": ("the FLEXIBLE pool of D179 share admission only "
                                  "(share_capacity.FLEXIBLE_TOKENS = 1802.6 uncached tokens, "
                                  "41.7 percent of W_max); the floors are NOT weighted")}


if __name__ == "__main__":
    import json
    print(json.dumps(as_dict(), indent=1))
