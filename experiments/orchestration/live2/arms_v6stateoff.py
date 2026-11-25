#!/usr/bin/env python3
"""`covex-v6-fair-final-stateoff`: rung 3 with the STATE PLANNER OFF (D233).

THE ARM. `arms_final_ladder.make_rung3` with `plan_state=False` and nothing else changed. The
switch is not new: `arms_v6state.V6StateArm.__init__` has taken `plan_state: bool = True` since the
rung-2 negative control `covex-v6-state-off` was built, and it arrives here through
`make_rung3(**kw) -> V6FairFinal(name=name, **kw) -> ... -> V6StateArm.__init__`. It is READ BACK
off the built instance below rather than assumed to have arrived, because a `**kw` chain that
silently drops a kwarg is this project's most repeated plumbing fault.

WHAT `plan_state=False` ACTUALLY ABLATES, AND IT IS NOT ONE THING. This matters for how the
result may be attributed, so it is recorded at the arm and not only in the report.
`V6StateArm.__init__` routes FOUR capability flags through `_d`, which returns `self.plan_state`
when the flag is left at `None`, and no class between `V6StateArm` and rung 3 passes any of them.
So `plan_state=False` turns off FIVE things at once:

    1. the planner limb itself   -- `V6StateArm.decide` returns at `if not self.plan_state`
                                    before any TOUCH / WARM / HOLD_BACK candidate is scored
    2. live2_offload_controls    -- read at coordinator.py:267, used at :1623 (kv_transfer_params)
    3. live2_touch_requests      -- read at coordinator.py:271, used at :927
    4. live2_state_priced_costs  -- read at coordinator.py:273, used at :1331 (the BUDGET CHARGE)
    5. live2_belief_apply        -- read at coordinator.py:364, used at :1909

`live2_d162_pricing` is NOT affected: `arms_v6c5.V6StateUoC5AttrArm` sets it by `setdefault` and
not through `_d`, so it stays True and rung 3's `release_recheck` prerequisite still holds.

THE CONSEQUENCE FOR ATTRIBUTION. A delta measured against `covex-v6-fair-final` is the delta of the
WHOLE rung-2 state channel, not of the planner's deviations alone. In particular (4) changes what
the budget is charged, which is the mechanism the `covex-v6-state-off` comment in `arms_v6state.py`
records as having moved 4,376 rows of decisions on its own. Anyone wanting the one-factor planner
ablation wants `touch_requests=False` with `plan_state=True`, which the rung-2 family already
registers as `covex-v6-state-notouch`. This arm is the five-factor channel ablation, and its
pre-registration says so.

THE THREE COUNTERS, PUBLISHED AT 0 RATHER THAN DROPPED. `state_decisions` (written at
`arms_v6state.py:433`) and `state_deviations` (at `:476`) are written AFTER the `plan_state`
early return, and they live in a `collections.Counter`, so with the planner off they would be
ABSENT from the arm's stats and not zero. "Absent" would then be indistinguishable from a counter
that was renamed or lost -- the `device_answers_enabled` lesson. They are therefore seeded to 0 on
the instance, so a reader sees a PUBLISHED ZERO.

`submitted_touch` is a different animal and is seeded on a different ground. It is NOT an arm
counter: it is written once in the whole tree, at `coordinator.py:1640`
(`self.counts["submitted_" + kind] += 1`), into the COORDINATOR's `counts`, and it reaches the
arm's stats only because `coordinator._mirror_d179_stats` copies every `submitted_`-prefixed key
across with `_as[_ks] = _v`. Seeding the arm-side MIRROR SLOT at 0 therefore cannot mask a real
count in either direction: the coordinator's own value, if it ever has one, is ASSIGNED over this 0
by the mirror, and with `live2_touch_requests` False it never submits a touch and never creates the
key. Publishing it here is what lets the H100 tell an off planner from a missing counter WITHOUT
editing `coordinator.py`, which belongs to another session's bundle.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Tuple

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

STATEOFF = "covex-v6-fair-final-stateoff"
BASE_ARM = "covex-v6-fair-final"

# the four flags `_d` derives from `plan_state`, each asserted False on the built instance
DERIVED_OFF: Tuple[str, ...] = ("live2_offload_controls", "live2_touch_requests",
                                "live2_state_priced_costs", "live2_belief_apply")

# the arm's OWN counters, written after the early return, seeded so they read 0 and not absent
PUBLISHED_AT_ZERO: Tuple[str, ...] = ("state_decisions", "state_deviations")

# the coordinator-side counter mirrored onto the arm; see the module docstring for why seeding the
# mirror slot is safe and why it is not grouped with the two above
PUBLISHED_AT_ZERO_MIRRORED: Tuple[str, ...] = ("submitted_touch",)


class StateOffSwitchError(RuntimeError):
    """Raised when the one switch this arm exists to set did not arrive, or did not arrive typed."""


def make_stateoff(name: str = STATEOFF, **kw: Any) -> Any:
    """Build rung 3 with `plan_state=False`, read the switch back, and publish the three counters.

    `arms_final_ladder` is imported at CALL time, not at module import time, so that registering
    this name costs one dict entry and cannot create an import cycle through the ladder.
    """
    if "plan_state" in kw:                                                 # pragma: no cover
        raise StateOffSwitchError(
            "%s sets plan_state itself; passing plan_state=%r would let a caller silently build "
            "the planner back ON under the -stateoff name" % (STATEOFF, kw["plan_state"]))

    import arms_final_ladder as FL                                         # noqa: PLC0415

    arm = FL.make_rung3(name, plan_state=False, **kw)

    # ---- the switch, read off the INSTANCE and type-checked ---------------------------------
    own = vars(arm)
    if "plan_state" not in own:
        raise StateOffSwitchError(
            "plan_state is not in the instance __dict__ of %s, so the kwarg did not survive the "
            "make_rung3 -> V6FairFinal -> V6StateArm chain" % (type(arm).__name__,))
    v = own["plan_state"]
    if type(v) is not bool or v is not False:
        raise StateOffSwitchError(
            "plan_state arrived as %r of type %s, not the bool False. A field coerced to a "
            "different type is how 2 became 1 in this project" % (v, type(v).__name__))

    for f in DERIVED_OFF:
        if f not in own:
            raise StateOffSwitchError("%s is absent from the instance, so `_d` did not run" % (f,))
        if own[f] is not False:
            raise StateOffSwitchError(
                "%s read %r with plan_state False; `_d` should have derived False from it" % (f, own[f]))

    # the rung-3 prerequisite that must SURVIVE the ablation, asserted so a silent loss of it
    # cannot be mistaken for part of the state channel
    if not bool(own.get("live2_d162_pricing")):
        raise StateOffSwitchError(
            "live2_d162_pricing is False on %s; make_rung3 requires it for release_recheck and "
            "the ablation must not have taken it with the state channel" % (name,))

    # ---- the three counters, published at 0 --------------------------------------------------
    st = getattr(arm, "stats", None)
    if not isinstance(st, dict):
        raise StateOffSwitchError(
            "arm.stats is %s, not a dict/Counter, so the three counters cannot be published"
            % (type(st).__name__,))
    for k in PUBLISHED_AT_ZERO + PUBLISHED_AT_ZERO_MIRRORED:
        if k in st:
            raise StateOffSwitchError(
                "%r is ALREADY in stats at construction (value %r). Seeding it to 0 would "
                "overwrite a real count" % (k, st[k]))
        st[k] = 0
        if k not in st or st[k] != 0 or not isinstance(st[k], int) or isinstance(st[k], bool):
            raise StateOffSwitchError("%r did not take as the int 0; reads %r" % (k, st.get(k)))

    return arm


def published_zero_report(arm: Any) -> Dict[str, Any]:
    """Per-counter: is it PRESENT, and at what value. The report the H100 reads.

    Reports presence and value separately and never collapses the two, because a published 0 and
    an absent key are different claims and the point of the seeding is that they be told apart.
    """
    st = dict(getattr(arm, "stats", {}) or {})
    out: Dict[str, Any] = {"arm": getattr(arm, "name", None),
                           "plan_state": vars(arm).get("plan_state"),
                           "plan_state_type": type(vars(arm).get("plan_state")).__name__}
    for k in PUBLISHED_AT_ZERO + PUBLISHED_AT_ZERO_MIRRORED:
        out[k] = {"present": k in st, "value": st.get(k),
                  "kind": ("arm_counter" if k in PUBLISHED_AT_ZERO else "coordinator_mirror_slot")}
    out["derived_off"] = {f: vars(arm).get(f) for f in DERIVED_OFF}
    out["live2_d162_pricing"] = vars(arm).get("live2_d162_pricing")
    return out


STATEOFF_ARMS: Dict[str, Any] = {STATEOFF: (lambda **kw: make_stateoff(STATEOFF, **kw))}


def register() -> Any:
    """Additive registration into `arms.ARMS`, refusing to shadow any existing name."""
    import arms as A                                                       # noqa: PLC0415
    import arms_final_ladder as FL                                         # noqa: PLC0415
    if STATEOFF in FL.PROTECTED_NAMES or STATEOFF in FL.FINAL_LADDER_ARMS:  # pragma: no cover
        raise StateOffSwitchError("%s collides with a ladder name" % (STATEOFF,))
    before = A.ARMS.get(STATEOFF)
    if before is not None and getattr(before, "_is_stateoff_factory", False) is False:
        raise StateOffSwitchError(
            "%s is already registered to %r; this module must never replace an existing factory"
            % (STATEOFF, before))
    A.ARMS.update(STATEOFF_ARMS)
    return sorted(STATEOFF_ARMS)


ARMS = STATEOFF_ARMS
