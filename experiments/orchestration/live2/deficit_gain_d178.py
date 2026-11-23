#!/usr/bin/env python3
"""D178 (2): THE ONE DECLARED DEFICIT GAIN, pre-registered BEFORE any covex-v6-fair cell runs.

D178 (2) requires "one value declared before any covex-v6-fair / covex-v6 cell, swept later as
sensitivity (0.5x, 2x)". This module is that declaration. It is committed and pushed BEFORE the
first cell of the deficit feed is run, so the value cannot be chosen after seeing a result. It
holds the value and nothing else: no reader of it may compute a different gain, and the sweep
values are recorded here so that a later sensitivity run cannot be mistaken for the declared one.

    w_d = 1 + GAIN * (shortfall_d / target_d),   floored at 1,   PER DEVICE d

    GAIN = 2.0

===============================================================================================
CORRECTION IN PLACE, 2026-11-22, flash addendum 12 item 2, BEFORE ANY RUNG-3 CELL RAN.

THE ORIGINAL WORDING OF THIS DECLARATION, QUOTED EXACTLY as commit 95aed198 recorded it:

    "w_t = 1 + GAIN * shortfall_t,   floored at 1,   per query type t"

    "WHY 2.0, AS THE USER'S JUSTIFICATION RECORDS IT. At gain 2.0 a type sitting at HALF its
    target carries weight 2, so it counts double. The weight range is bounded at 1 to 3, because
    a shortfall is at most 1 (it is a clipped difference of two rates in [0, 1],
    `max(target - attainment, 0)`, and every target is below 1)."

THE ERROR. The quoted justification and the quoted formula do not describe the same thing, and the
parenthesis contains the contradiction in its own words: a shortfall is bounded by its TARGET, not
by 1, precisely BECAUSE "every target is below 1". So under the RAW form the reachable range is
`1` to `1 + GAIN * target`, which is 1 to 1.5 for alert (target 0.25) and 1 to 2.8 for recall and
assistance (target 0.90). The promised 1-to-3 range is reachable only by a type whose target is 1,
and "a type at HALF its target counts double" is false for every type: at half its target a type
carries `1 + GAIN * target/2`, so 1.25 for alert and 1.9 for recall, not 2.

THE DIRECTION OF THE ERROR, which is the part that matters. The raw form UNDER-WEIGHTS every unit
whose target is below 1, and it under-weights MOST the unit with the TIGHTEST target. That is
alert, at 0.25, and alert is also the type carrying the largest measured per-unit deficit. On the
committed `covex-v6-state_n16_s5` cell the raw form gives alert 1.2917 against recall 1.2095, so
alert leads by 0.08 while being 58 percent of the way to its own ceiling and recall only 12 percent
of the way to its; the normalised form on the same numbers gives alert 2.1664 against recall
1.2329. The raw form was therefore biased AGAINST the alert type and in favour of recall and
assistance, by a factor that was an artefact of the targets rather than of any deficit.

THE CORRECTION. The form is NORMALISED by the unit's own target, which is what spec v6 section 1
already requires of the objective ("normalised by the device's own target window so sparse and
dense devices are comparable", D122 B2), and the gain is UNCHANGED at 2.0:

    w_d = 1 + 2.0 * (shortfall_d / target_d)

Now the justification is true as written: a unit at HALF its target has
`shortfall/target = 0.5` and carries weight exactly 2, and the range is 1 to 3 for EVERY type,
because `shortfall_d / target_d` is in [0, 1] by construction.

THE RAW FORM IS NOT RUN AT ALL. No cell of it exists and none will be produced: it is corrected
here before the first rung-3 cell rather than reported as a sensitivity point, so there is no raw
number anywhere that a reader could mistake for a result. The three raw per-type weights quoted
above come from a read-only replay of an already-committed rung-2 cell
(`d178_deficit_feed_proofs.json`, section f) and are DIAGNOSTICS, not a cell of this rung.

ALSO CHANGED BY ADDENDUM 12, item 1: the unit is the DEVICE (D3, D122 B), not the query type.
Alert is per device per EPISODE, recall and assistance per device over OFFERED questions, and the
per-type figures the original build reported are kept as DIAGNOSTICS only.
===============================================================================================

THE FLOOR AT 1 IS PART OF THE DECLARATION, not an implementation detail. A unit ahead of its
target is not worth LESS than one at its target; it is simply not worth more. Letting w fall
below 1 would make the split trade an on-time answer for a fairness statistic, which D149 (1)
forbids and which `cf_objective.DeficitCounters.weight` already records in the same words.

WHAT THE WEIGHTS DRIVE (addendum 12 item 3), because the bound matters only against what it moves.
Two consumers, and the user calls the first the PRIMARY one: ORDERING, where deadline requests
competing for admission or release within a period are ordered by `w_d` descending then deadline;
and the FLEXIBLE SPLIT, where each type's cut of D179's flexible pool is scaled by the maximum
`w_d` over that type's devices with pending work. Floors, W_max and the oversize rule are
UNCHANGED, so D179 is intact and a 3x range cannot let one unit monopolise the accelerator: the
weights never touch the floors (0.30 / 0.30 / 0.15 of W_max as tokens) and the flexible pool is
1,802.6 of 4,323.3 uncached tokens, 41.7 percent (`share_capacity.FLEXIBLE_TOKENS`).

WHAT IS AND IS NOT SWEPT. The sweep comes AFTER the core grid: gain 1.0 and 4.0, NORMALISED
(addendum 12 item 2). Those are SENSITIVITY values and carry their own names; neither may be used
for a headline. A run at any gain other than GAIN must say so in its own cell name, which is why
the arm takes the gain as a constructor argument and defaults it to this constant rather than
reading a module global that any path could move (the failure `d162_price.arm_charge_mode` records).
The RAW, unnormalised form is not in the sweep and is not run at any gain.

GAIN 0.0 IS NOT A SWEEP VALUE. It is CLAUDE.md Step 4's negative control: at gain 0 every weight is
exactly 1.0, both consumers stay live and fully instrumented, the ordering key is a constant and
the flexible pool splits equally, and the arm must collapse to its rung-2 base byte-identically. It
is the pre-registered comparator for the addendum 12 item 5 pass condition (gain 2.0 against gain
0) and must never be reported as a sensitivity point.
"""
from __future__ import annotations

from typing import Dict

# ---- THE DECLARED VALUE (D178 (2)). One number, one place, never recomputed.
GAIN = 2.0

GAIN_DECLARED_ON = "2026-11-22"
GAIN_CORRECTED_ON = "2026-11-22"
GAIN_RULING = "D178 (2), corrected by flash addendum 12 item 2"
GAIN_SOURCE = (
    "user's flash addendum 9 item B1, 2026-11-22, pre-registered: at gain 2.0 a unit at HALF its "
    "target carries weight 2 and so counts double; the weight range is bounded at 1 to 3; a 3x "
    "range cannot let one unit monopolise, because D179's floors already guarantee the other "
    "types a minimum and only the FLEXIBLE pool and the ORDERING are weighted")

# ---- the form, and the superseded one, both named so no reader has to guess which ran
FORM = "w_d = 1 + gain * (shortfall_d / target_d), floored at 1, PER DEVICE"
FORM_SUPERSEDED = "w_t = 1 + gain * shortfall_t, floored at 1, per TYPE (NOT RUN, see docstring)"
NORMALISED_BY_TARGET = True

# The weight range the declaration claims, as an assertion rather than a sentence. Under the
# NORMALISED form this is true for every type, which is the whole point of the correction.
WEIGHT_MIN = 1.0
WEIGHT_MAX = 1.0 + GAIN * 1.0          # shortfall_d / target_d <= 1 by construction

# addendum 12 item 2 sensitivity, AFTER the core grid, NORMALISED. Not headline values.
SWEEP_LATER: Dict[str, float] = {"0.5x": 0.5 * GAIN, "2x": 2.0 * GAIN}
# CLAUDE.md Step 4 negative control, not a sweep point.
NEGATIVE_CONTROL_GAIN = 0.0

assert WEIGHT_MAX == 3.0, "the declared justification claims a 1 to 3 weight range"


def weight(shortfall: float, target: float, gain: float = GAIN) -> float:
    """`w = 1 + gain * (shortfall / target)`, floored at 1. The ONE implementation of the form.

    `target` is REQUIRED and has no default, deliberately. The superseded raw form is this
    function with the normalisation dropped, and a default target of 1.0 would have let a caller
    reproduce it silently by omitting one argument. A missing target is a TypeError instead.
    """
    t = float(target)
    if t <= 0.0:
        raise ValueError("target must be positive; got %r" % (target,))
    r = float(shortfall) / t
    if r < 0.0:
        r = 0.0
    elif r > 1.0:
        r = 1.0
    return 1.0 + float(gain) * r


def as_dict() -> Dict[str, object]:
    return {"gain": GAIN, "ruling": GAIN_RULING, "declared_on": GAIN_DECLARED_ON,
            "corrected_on": GAIN_CORRECTED_ON, "source": GAIN_SOURCE,
            "form": FORM, "form_superseded_and_never_run": FORM_SUPERSEDED,
            "normalised_by_target": NORMALISED_BY_TARGET,
            "weight_range": [WEIGHT_MIN, WEIGHT_MAX],
            "weight_range_holds_for_every_type": True,
            "weight_range_under_the_superseded_form": {"alert": [1.0, 1.5],
                                                       "recall": [1.0, 2.8],
                                                       "assistance": [1.0, 2.8]},
            "sweep_later": dict(SWEEP_LATER),
            "negative_control_gain": NEGATIVE_CONTROL_GAIN,
            "weighted_quantity": ("the ORDERING of competing deadline requests (the PRIMARY "
                                  "consumer) and the FLEXIBLE pool of D179 share admission "
                                  "(share_capacity.FLEXIBLE_TOKENS = 1802.6 uncached tokens, "
                                  "41.7 percent of W_max); the floors, W_max and the oversize "
                                  "rule are UNCHANGED and are NOT weighted")}


if __name__ == "__main__":
    import json
    print(json.dumps(as_dict(), indent=1))
