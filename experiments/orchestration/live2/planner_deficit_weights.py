#!/usr/bin/env python3
"""THE ONE ADAPTER that hands the v5 STATE PLANNER a rung's live per-device deficit weight.

Extracted from `arms_v6cfr3.py` (where D206 first built it) into its own module for ONE REASON:
rung 3 of the final ladder reads it too, and rung 3 importing rung 4's module would invert the
ladder's layering. There is exactly ONE copy of this class, and `arms_v6cfr3` re-exports it so no
committed caller changes.

D206 item 1b, and the point is ONE SOURCE AND NOT TWO. A rung's two counterfactual legs read
`self._feed.weight_device` through `arms_v6cfr3._weight_of`; this hands the STATE PLANNER the SAME
OBJECT, so the limb and the legs cannot disagree about a device's weight at a given instant. They
are equal BY CONSTRUCTION rather than by agreement, and a proof that compares them is an IDENTITY
and must say so: n reads of one object, maximum absolute difference exactly 0.

THE DEVICE RESOLVER IS THE ARM'S OWN, `_fairfeed_resolve_device`, which is what rung 3's ordering
consumer uses, so the planner weight and the ordering weight cannot disagree about WHICH DEVICE a
decision is about either. An id that does not resolve takes the floor and is COUNTED, because the
device set is the roster's and an unresolved id means the resolver failed.

FAIL-LOUD, AND DELIBERATELY NOT PER READ (D206 item 3). A source that is supposed to be fed must
raise rather than return a neutral value. The condition that let the original defect live is
"never fed across a whole run", NOT "holds no data at this instant": at the first decision the feed
legitimately has no observations, which is why `W_WIRED_PROOF` records that 1.0 at construction is
correct and not a failure. So the raises are at CONSTRUCTION when the feed object is absent, and at
REPORT TIME when reads happened and the feed received zero observations all run. A per-read raise
would fire on decision one of a correct run.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


class WeightWiringError(RuntimeError):
    """The deficit weight did not reach the object under test as the live accessor."""


class DeficitSourceNeverFed(RuntimeError):
    """A weight source that is SUPPOSED to be fed received nothing for a whole run (D206 item 3)."""


class PlannerDeficitWeights:
    """The rung's live `DeficitFeed`, adapted to the v5 planner's weight interface."""

    IS_DECLARED_CONSTANT = False

    def __init__(self, arm: Any) -> None:
        if getattr(arm, "_feed", None) is None:
            raise WeightWiringError(
                "PlannerDeficitWeights was built with no live feed on the arm; _fairfeed_init has "
                "not run, so the planner limb would have silently priced every device at 1.0")
        self._arm = arm
        self.reads = 0
        self.unresolved = 0
        self.reads_above_floor = 0

    def _resolve(self, device_id: Any) -> Optional[str]:
        return self._arm._fairfeed_resolve_device(device_id, None)

    def weight(self, device_id: Any) -> float:
        self.reads += 1
        did = self._resolve(device_id)
        if did is None:
            self.unresolved += 1
            self._arm.stats["planner_w_device_unresolved"] += 1
            return 1.0
        w = float(self._arm._feed.weight_device(did))
        if not (w == w) or w < 1.0:
            # the D178 (2) floor RESTATED AT THE POINT OF USE: the bar is w_R * MARGIN_CF and a
            # weight under 1 would lower it below the committed margin by another route.
            self._arm.stats["planner_w_below_floor_clamped"] += 1
            return 1.0
        if w > 1.0:
            self.reads_above_floor += 1
        return w

    def shortfall(self, device_id: Any) -> float:
        did = self._resolve(device_id)
        return 0.0 if did is None else float(self._arm._feed.shortfall_device(did))

    def starving(self, device_id: Any, threshold: float = 0.10) -> bool:
        return self.shortfall(device_id) >= float(threshold)

    def _n_observations(self) -> int:
        f = self._arm._feed
        return int(getattr(f, "n_offers", 0)) + int(getattr(f, "n_completions", 0))

    def as_dict(self) -> Dict[str, Any]:
        n_obs = self._n_observations()
        if self.reads and n_obs == 0:
            raise DeficitSourceNeverFed(
                "the planner deficit source was READ %d times and the feed received ZERO "
                "observations for the whole run, so every weight it returned was the floor. That "
                "is the condition that let the D200 (1) defect survive, and D206 item 3 requires "
                "it to raise rather than report a neutral default." % (self.reads,))
        return {"source": ("live2/deficit_feed.DeficitFeed.weight_device, THE SAME FEED OBJECT "
                           "the counterfactual legs read (D206 item 1b)"),
                "is_declared_constant": False,
                "gain": float(getattr(self._arm, "_feed_gain", float("nan"))),
                "reads": self.reads, "unresolved": self.unresolved,
                "reads_above_the_w1_floor": self.reads_above_floor,
                "feed_observations": n_obs,
                "identity_note": ("the legs and this limb read ONE object, so an equality proof "
                                  "between them is an IDENTITY with maximum absolute difference "
                                  "exactly 0, not a measurement of agreement")}


def wire_planner(arm: Any, cf: Any) -> Any:
    """Swap the engine's declared constant for this arm's live feed, and READ IT BACK.

    Shared by rung 3 and rung 4 of the final ladder so the swap cannot be done two ways. The
    read-back RAISES if the swap did not take, because a construction that silently kept the
    constant is exactly the shape of the defect this repairs: it would produce a plausible null
    rather than a crash.
    """
    if getattr(cf, "_planner_deficit_wired", False):
        return cf
    src = PlannerDeficitWeights(arm)
    cf.counters = src
    cf._planner_deficit_wired = True
    arm._planner_w_source = src
    if getattr(cf.counters, "IS_DECLARED_CONSTANT", True):                 # pragma: no cover
        raise WeightWiringError(
            "the planner weight source did not take: the engine still holds %r, a declared "
            "constant, so plan_state would price every device at 1.0"
            % (type(cf.counters).__name__,))
    if cf.counters._arm._feed is not arm._feed:                            # pragma: no cover
        raise WeightWiringError(
            "the planner source is not reading THE SAME feed object as the legs, so the limb and "
            "the legs could disagree (D206 item 1b)")
    return cf
