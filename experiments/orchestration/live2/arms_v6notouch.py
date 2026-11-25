#!/usr/bin/env python3
"""`covex-v6-fair-final-notouch`: rung 3 with the planner ON and its TOUCHES NOT ENACTED (D234 (2)).

THE ARM, AND WHY IT IS THE ONE-FACTOR COMPANION. `arms_final_ladder.make_rung3` with
`plan_state=True` and `touch_requests=False`, and nothing else changed. `covex-v6-fair-final-stateoff`
(`arms_v6stateoff.py`, built at 2b72b463) sets `plan_state=False`, which its own module docstring
records as moving FIVE things at once, because `V6StateArm.__init__` routes four further capability
flags through `_d`, and `_d(None)` returns `self.plan_state`. This arm moves ONE: the planner limb
still runs, still scores WARM / TOUCH / HOLD_BACK, still deviates and still emits, and only the
ENACTMENT of a TOUCH is withheld. A delta against `covex-v6-fair-final` is therefore attributable
to TOUCH being enacted and to nothing else.

WHY `touch_requests` MUST BE PASSED EXPLICITLY AND MAY NOT BE LEFT TO A DEFAULT. Its declared
default is `touch_requests: Optional[bool] = None` (`arms_v6state.py:139`) and `_d` turns that
`None` into `self.plan_state`, which on this arm is True. Leaving it unset therefore builds the
TOUCH channel back ON under the `-notouch` name. The `-stateoff` build is where that behaviour of
`_d` was established; this arm is the one for which it is load-bearing.

THE CHAIN THE TWO SWITCHES TRAVEL, AND WHY BOTH ARE READ BACK OFF THE INSTANCE.
`make_rung3(name, **kw)` -> `V6FairFinal(name=name, **kw)` -> ... -> `V6StateArm.__init__`, which
takes both `plan_state` (`:137`) and `touch_requests` (`:139`). A `**kw` chain that silently drops a
kwarg is this project's most repeated plumbing fault (`make_arm` discarding `c_inflight=8`; an
`int` field coerced to `bool` turning 2 into 1), so `plan_state is True` and
`live2_touch_requests is False` are both read out of the built instance's `__dict__` and both
type-checked as `bool`, not merely passed.

WHERE THE ONE FACTOR ACTS, AND WHERE IT DOES NOT. `live2_touch_requests` is NOT read anywhere in
`V6StateArm.decide`. It is read once in the tree, by `touch_policy.arm_enables`
(`touch_policy.py:204`), which the coordinator calls once at `coordinator.py:271` into
`self._touch_requests`, and consults at `coordinator.py:966`:

        elif xa.action == "KEEP_GPU_WARM":
            s.desired_tier = "gpu"
            if self._touch_requests:
                self._submit_touch(s, t, dt_ms, preds, mix)

So with the switch off the planner's chosen TOUCH still becomes a `KEEP_GPU_WARM` session action
and still sets `desired_tier`, and `_submit_touch` is never called. `desired_tier` is the project's
canonical WRITE-ONLY field (CLAUDE.md, Step 2; three references, one declaration and two writes, no
read), so the touch request IS the whole live channel of a TOUCH, and withholding it withholds the
enactment entirely. That is what makes this a clean one-factor ablation rather than a partial one.

*** THE DELIVERABLE COUNTER: `state_touch_chosen_not_enacted`. ***
The H100 asked for this by name, at 0 when none, so that its check can tell "none occurred" from
"not wired". It is the count of TOUCHes the planner CHOSE while the enactment path was closed. It
is maintained from the arm's own `state_chosen_TOUCH`, which `V6StateArm.decide` increments at
`arms_v6state.py:449` (`self.stats["state_chosen_" + str(d.chosen)] += 1`) for every candidate the
planner selects, including the ones that are chosen while a rebuild is already in flight and are
therefore not even emitted as a session action.

IT IS KEPT IN SYNC BY A POST-DECISION HOOK ON THE INSTANCE, AND THAT HOOK DECIDES NOTHING. `stats`
is a `collections.Counter` and cannot hold a derived key, so the value is copied across after each
`decide` returns, by a wrapper installed on the INSTANCE (`arm.decide = ...`), which is the
established in-tree idiom for exactly this (`d178_deficit_feed_proofs.py:143,152`;
`d184_r3_c5attr_proofs.py:218,227`), and which works because `Policy.__call__` dispatches through
`self.decide(scrub(obs))` (`baselines/interface.py:486`) and an instance `__dict__` entry wins that
lookup. The wrapper reads the returned action and the counter and writes one key; it cannot change
a decision, and the non-zero value of the counter on a dry cell is itself the proof the wrapper ran.

THE OTHER THREE KEYS, AND THE SEEDING DISCIPLINE. `state_decisions`, `state_deviations` and
`submitted_touch` stay published, the same four-key discipline the `-stateoff` build used. All four
are SEEDED AT 0 at construction, because `stats` is a `Counter`: a key never incremented is ABSENT
from it, not zero, and "absent" would then be indistinguishable from a counter that was renamed or
lost. The contrast the `-stateoff` build demonstrated holds here too: the old rung-2
`covex-v6-state-off` reports `state_decisions` as ABSENT on a dry cell where these arms report a
number.

`submitted_touch` IS NOT AN ARM COUNTER and is seeded on a different ground. It is written in one
place in the whole tree, `coordinator.py:1679` (`self.counts["submitted_" + kind] += 1`), into the
COORDINATOR's `counts`, and it reaches the arm only because `coordinator._mirror_d179_stats`
(`:1704`) copies every `submitted_`-prefixed key across with `_as[_ks] = _v`. What is seeded here is
the arm-side MIRROR SLOT, and the seed cannot mask a real count in either direction, because the
mirror ASSIGNS over it. On this arm the coordinator never submits a touch, so the key is never
created and the published 0 is the seed; that is precisely the reading the proof needs.

`coordinator.py` is NOT edited. It belongs to another session's bundle, and the mirror makes editing
it unnecessary.

THE PROOF THIS ARM EXISTS TO CARRY: `state_touch_chosen_not_enacted > 0` AND `submitted_touch == 0`
ON THE SAME DRY CELL. That pair is the whole content of the arm -- the planner still choosing while
nothing is enacted -- and either number alone is consistent with a dead arm.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Tuple

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

NOTOUCH = "covex-v6-fair-final-notouch"
BASE_ARM = "covex-v6-fair-final"

# the named deliverable, and the arm counter it is derived from
CHOSEN_NOT_ENACTED = "state_touch_chosen_not_enacted"
CHOSEN_SOURCE = "state_chosen_TOUCH"

# the arm's OWN counters, seeded so they read 0 and not absent
PUBLISHED_AT_ZERO: Tuple[str, ...] = ("state_decisions", "state_deviations", CHOSEN_NOT_ENACTED)

# the coordinator-side counter mirrored onto the arm; see the module docstring for why seeding the
# mirror slot is safe and why it is not grouped with the three above
PUBLISHED_AT_ZERO_MIRRORED: Tuple[str, ...] = ("submitted_touch",)

# the three flags `_d` must still derive TRUE from `plan_state=True`, i.e. the four-flag group
# MINUS the one this arm turns off. Asserted so a one-factor arm that silently became a
# two-factor arm is a construction failure and not a quiet attribution error in the report.
DERIVED_STILL_ON: Tuple[str, ...] = ("live2_offload_controls", "live2_state_priced_costs",
                                     "live2_belief_apply")


class NoTouchSwitchError(RuntimeError):
    """Raised when either of the two switches did not arrive, or did not arrive typed."""


def _install_counter_hook(arm: Any) -> None:
    """Keep `state_touch_chosen_not_enacted` in step with the arm's own `state_chosen_TOUCH`.

    Installed on the INSTANCE, runs AFTER the real `decide`, reads two values and writes one key.
    It returns the action object unchanged and by identity, so it cannot move a decision.
    """
    inner = arm.decide
    st = arm.stats

    def decide(obs: Any) -> Any:
        act = inner(obs)
        st[CHOSEN_NOT_ENACTED] = int(st.get(CHOSEN_SOURCE, 0) or 0)
        return act

    decide._is_notouch_counter_hook = True                                 # type: ignore[attr-defined]
    decide._inner = inner                                                  # type: ignore[attr-defined]
    arm.decide = decide
    if getattr(arm.decide, "_is_notouch_counter_hook", False) is not True:  # pragma: no cover
        raise NoTouchSwitchError(
            "the counter hook did not take on the instance of %s; an instance __dict__ entry "
            "should win the lookup that Policy.__call__ makes" % (type(arm).__name__,))


def make_notouch(name: str = NOTOUCH, **kw: Any) -> Any:
    """Build rung 3 with `plan_state=True, touch_requests=False`, read both switches back, publish.

    `arms_final_ladder` is imported at CALL time, not at module import time, so that registering
    this name costs one dict entry and cannot create an import cycle through the ladder.
    """
    for bad in ("plan_state", "touch_requests"):
        if bad in kw:                                                      # pragma: no cover
            raise NoTouchSwitchError(
                "%s sets %s itself; passing %s=%r would let a caller silently build the TOUCH "
                "channel back ON, or the planner OFF, under the -notouch name"
                % (NOTOUCH, bad, bad, kw[bad]))

    import arms_final_ladder as FL                                         # noqa: PLC0415

    arm = FL.make_rung3(name, plan_state=True, touch_requests=False, **kw)

    # ---- the TWO switches, read off the INSTANCE and type-checked ----------------------------
    own = vars(arm)
    for field, want in (("plan_state", True), ("live2_touch_requests", False)):
        if field not in own:
            raise NoTouchSwitchError(
                "%s is not in the instance __dict__ of %s, so the kwarg did not survive the "
                "make_rung3 -> V6FairFinal -> V6StateArm chain" % (field, type(arm).__name__))
        v = own[field]
        if type(v) is not bool or v is not want:
            raise NoTouchSwitchError(
                "%s arrived as %r of type %s, not the bool %r. A field coerced to a different "
                "type is how 2 became 1 in this project" % (field, v, type(v).__name__, want))

    # the one factor must be the ONLY factor: `_d(None)` returns plan_state, which is True here,
    # so the other three flags of the group must read True
    for f in DERIVED_STILL_ON:
        if f not in own:
            raise NoTouchSwitchError("%s is absent from the instance, so `_d` did not run" % (f,))
        if own[f] is not True:
            raise NoTouchSwitchError(
                "%s read %r with plan_state True; this arm would then be a MULTI-factor ablation "
                "and its delta would not be attributable to TOUCH enactment" % (f, own[f]))

    # the rung-3 prerequisite that must SURVIVE the ablation
    if not bool(own.get("live2_d162_pricing")):
        raise NoTouchSwitchError(
            "live2_d162_pricing is False on %s; make_rung3 requires it for release_recheck and "
            "the ablation must not have taken it" % (name,))

    # ---- the four counters, published at 0 ---------------------------------------------------
    stt = getattr(arm, "stats", None)
    if not isinstance(stt, dict):
        raise NoTouchSwitchError(
            "arm.stats is %s, not a dict/Counter, so the counters cannot be published"
            % (type(stt).__name__,))
    for k in PUBLISHED_AT_ZERO + PUBLISHED_AT_ZERO_MIRRORED:
        if k in stt:
            raise NoTouchSwitchError(
                "%r is ALREADY in stats at construction (value %r). Seeding it to 0 would "
                "overwrite a real count" % (k, stt[k]))
        stt[k] = 0
        if stt.get(k) != 0 or not isinstance(stt[k], int) or isinstance(stt[k], bool):
            raise NoTouchSwitchError("%r did not take as the int 0; reads %r" % (k, stt.get(k)))

    _install_counter_hook(arm)
    return arm


def published_zero_report(arm: Any) -> Dict[str, Any]:
    """Per-counter: is it PRESENT, and at what value. The report the H100 reads.

    Presence and value are never collapsed, because a published 0 and an absent key are different
    claims and telling them apart is the point of the seeding.
    """
    st = dict(getattr(arm, "stats", {}) or {})
    own = vars(arm)
    out: Dict[str, Any] = {"arm": getattr(arm, "name", None),
                           "plan_state": own.get("plan_state"),
                           "plan_state_type": type(own.get("plan_state")).__name__,
                           "live2_touch_requests": own.get("live2_touch_requests"),
                           "live2_touch_requests_type": type(own.get("live2_touch_requests")).__name__}
    for k in PUBLISHED_AT_ZERO + PUBLISHED_AT_ZERO_MIRRORED:
        out[k] = {"present": k in st, "value": st.get(k),
                  "kind": ("arm_counter" if k in PUBLISHED_AT_ZERO else "coordinator_mirror_slot")}
    # the source counter and the emitted subset, beside the derived key, so the derivation is
    # auditable rather than asserted
    out["source_counters"] = {CHOSEN_SOURCE: st.get(CHOSEN_SOURCE),
                              "state_touch_emitted": st.get("state_touch_emitted"),
                              "state_chosen_WARM": st.get("state_chosen_WARM"),
                              "state_chosen_HOLD_BACK": st.get("state_chosen_HOLD_BACK")}
    out["derived_still_on"] = {f: own.get(f) for f in DERIVED_STILL_ON}
    out["live2_d162_pricing"] = own.get("live2_d162_pricing")
    return out


NOTOUCH_ARMS: Dict[str, Any] = {NOTOUCH: (lambda **kw: make_notouch(NOTOUCH, **kw))}


def register() -> Any:
    """Additive registration into `arms.ARMS`, refusing to shadow any existing name."""
    import arms as A                                                       # noqa: PLC0415
    import arms_final_ladder as FL                                         # noqa: PLC0415
    if NOTOUCH in FL.PROTECTED_NAMES or NOTOUCH in FL.FINAL_LADDER_ARMS:   # pragma: no cover
        raise NoTouchSwitchError("%s collides with a ladder name" % (NOTOUCH,))
    before = A.ARMS.get(NOTOUCH)
    if before is not None and getattr(before, "_is_notouch_factory", False) is False:
        raise NoTouchSwitchError(
            "%s is already registered to %r; this module must never replace an existing factory"
            % (NOTOUCH, before))
    A.ARMS.update(NOTOUCH_ARMS)
    return sorted(NOTOUCH_ARMS)


ARMS = NOTOUCH_ARMS
