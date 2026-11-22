#!/usr/bin/env python3
"""covex-v6-state-uo-c5attr: covex-v6-state-uo plus ONE attribution rule on C5's AIMD cap.

CANDIDATE, DEFAULT OFF, NOT ADOPTED. Built under the user ruling of 2026-11-22 (addendum) as one
of two candidate fixes for rung 1's dashcam loss. Nothing here changes any committed arm, and
whether this rule is adopted is a user decision, not this module's.

WHAT THE RULE IS. C5's in-flight cap starts at 8, HALVES (floor 4) whenever the EWMA of monitor
first-token time exceeds 0.8 s (80 percent of the 1.0 s alert deadline), and recovers +1 per 5 s.
The cap exists to back off from ENGINE OVERLOAD. This arm does not halve for a slow monitor whose
wait overlapped a robot prefill THE COORDINATOR ITSELF RELEASED (a build, touch or recall with
uncached >= 200 tokens, the threshold c5_loss_split.py's ruling fixed): work our own policy chose
to release is not evidence of overload, it is evidence of our own scheduling. When every slow
monitor seen since the last cap adjustment is of that kind, the halving is suppressed and the cap
is HELD - neither halved nor stepped up, and the recovery timer is not restarted, so the rule can
only WITHHOLD a back-off, never grant the cap anything the AIMD rule would not have granted it.

WHY THE LOSS SPLIT POINTS HERE. results/orchestration/live2/frozen_test/c5_loss_split.json, read
only: at rung 1, monitor opportunities NEVER SUBMITTED are 52 to 58 percent of all opportunities
against 13 to 17 for the base arm, and the dominant bucket is "the cap is shut AND a robot prefill
is in flight" at 37.5 to 43.0 percent against 3.7 to 7.9. The cap sits at its floor in about 65
percent of epochs against about 20 for the base.

WHERE EACH HALF LIVES, and the split is the honest one. The OVERLAP TEST is the coordinator's
(coordinator.py `_self_released_overlap`), because only the coordinator knows what it released and
when; it reports the answer on the completion hook that also feeds the EWMA. The DECISION is the
arm's (hybrid/hybrid_arm.py `_attr_suppresses`, read at `_aimd`). The arm is given nothing it could
not have causally at that moment: one boolean per monitor completion, computed from releases that
had already happened.

THE SWITCH IS AN INSTANCE ATTRIBUTE on the HybridArm object that owns `self.cap`, set here and
nowhere else. Not a class attribute (which left a "negative control" un-collapsed in this project
before) and not a module global (one that defaulted ON once cost a whole live cell).

covex-v6-state-uo itself is defined in arms_v6state.py, which another session owns, so this arm
SUBCLASSES it and is registered here.
"""
from __future__ import annotations

from typing import Any, Dict

import arms_v6state as VS

C5ATTR_VERSION = "covex-v6-state-uo-c5attr-1.0"


class V6StateUoC5AttrArm(VS.V6StateArm):
    """covex-v6-state-uo in every respect except the C5 attribution rule."""

    def __init__(self, name: str = "covex-v6-state-uo-c5attr", **kw: Any) -> None:
        # IDENTICAL to the registered covex-v6-state-uo in everything the pricing ruling fixed:
        # D174 (1)'s per-uncached charge, declared BY THE ARM, in the ruled uncached-only mode.
        kw.setdefault("d162_pricing", True)
        kw.setdefault("charge_mode", "uncached-only")
        super().__init__(name=name, **kw)
        self.arm_version = C5ATTR_VERSION
        self.c5_attr_self_released = True
        # Set on EVERY object the decide path can bind `self` to. `V5Rules2Arm.__call__` runs
        # `HybridArm.__call__(self, obs)` with `self` being the wrapper, and `V5Rules2Arm.decide`
        # then calls `self._base.decide`, so the cap lives on the HybridArm and the flag has to
        # read True from whichever of the three the method ran against. The same reason
        # arms_v5rules2 sets `over_limit_infeasible` on both itself and its base; leaving one
        # unset is how a switch reads as live and is not.
        for obj in self._attr_targets():
            obj.c5_attr_self_released = True

    def _attr_targets(self):
        out = []
        o: Any = self
        seen = set()
        while o is not None and id(o) not in seen:
            seen.add(id(o))
            out.append(o)
            o = o.__dict__.get("_rules") or o.__dict__.get("_base")
        return out

    def hybrid_core(self):
        """The object that owns `self.cap` and `_attr_mon`, for the proofs to read."""
        return self._attr_targets()[-1]

    def live2_describe(self) -> Dict[str, Any]:
        d = dict(super().live2_describe())
        d.update(arm=self.name, arm_version=C5ATTR_VERSION,
                 c5_attribution=dict(
                     rule=("C5 does not halve its cap for a slow monitor whose wait overlapped a "
                           "robot prefill the coordinator itself released (uncached >= 200 "
                           "tokens); on suppression the cap is HELD and the recovery timer is "
                           "not restarted"),
                     enabled=bool(getattr(self.hybrid_core(), "c5_attr_self_released", False)),
                     overlap_source=("coordinator._self_released_overlap, reported on "
                                     "live2_completed as self_released_prefill_overlap"),
                     uncached_definition=("the uncached count the COORDINATOR CHARGED at release "
                                          "(its own prediction), not the engine's later "
                                          "prompt - cached"),
                     counters=["c5_attr_suppressed_decrease", "c5_attr_slow_all_self_released",
                               "c5_attr_slow_mixed", "c5_attr_trip_without_slow_evidence"],
                     status="CANDIDATE, default off, adopted only by a user ruling"))
        return d


V6C5_ARMS = {
    "covex-v6-state-uo-c5attr": lambda **kw: V6StateUoC5AttrArm(
        name="covex-v6-state-uo-c5attr", **kw),
}


def register() -> None:
    import arms as A
    A.ARMS.update(V6C5_ARMS)
