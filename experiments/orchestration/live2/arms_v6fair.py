#!/usr/bin/env python3
"""covex-v6-fair, rung 3 of the spec v6 ladder (D172).

    covex-v6-state
      + DEFICIT FEED    `DeficitCounters.observe()` called from the coordinator's completion hook
      + VALUE READER    on

WHY THE FEED IS THE WHOLE POINT OF THIS RUNG. `cf_objective.DeficitCounters.weight()` returns
`1 + gain * shortfall`, and a counter that is never fed has `served == 0`, so `shortfall()` returns
0.0 and `weight()` returns EXACTLY 1.0 for every device, forever. Every deficit-weighted quantity
in the objective has therefore been multiplied by one in every run to date: the weighting is
declared, implemented, read, and inert. That is CLAUDE.md Step 2's stopping condition, reached by
a quantity that is correctly and consistently 1.

AND IT IS WHAT MAKES D171 (1) BITE. The margin comparison is `delta > w_d * MARGIN_CF`. With every
weight at 1 that is the bare margin and the weighting cannot change a single decision. The moment
this feed runs, a device in deficit faces a HIGHER model-error bar, which is the direction D171 (1)
chose deliberately: deficit weighting must steer ranking and harm, and must not loosen the check
that stops the counterfactual acting inside its own prediction error.

ON-TIME FROM EITHER SOURCE, AND THE TWO SOURCES ARE COMBINED HERE. D155 (3) counts an answer that
arrives by the deadline from the cloud OR from the device. The coordinator reports
`cloud_on_time` and `device_on_time` separately, because combining them is a policy choice; this
arm takes the OR, which is the committed headline, and counts the three cases apart so a report
can say which source carried a device.

WHAT THIS FEED CANNOT SEE, stated rather than discovered later. `live2_completed` fires for
requests the cloud SERVED. An opportunity the policy DECLINED never reaches it, and those are
exactly the opportunities where the device answers alone. So the counters see the served
population, not the offered one, and `deficit_feed_unseen_declines` counts the gap. A shortfall
computed over served requests only is an UNDERCOUNT of a device's true shortfall whenever that
device's requests are being declined, which is the case the weighting exists to catch. Reported,
not smoothed.
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path as _Path
from typing import Any, Dict, Optional

for _p in (str(_Path(__file__).resolve().parents[1] / "baselines"),
           str(_Path(__file__).resolve().parent),
           str(_Path(__file__).resolve().parent / "v5"),
           str(_Path(__file__).resolve().parent / "fleet")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from interface import Action, Observation                                      # noqa: E402

import arms_v6state as VS                                                      # noqa: E402

V6FAIR_VERSION = "covex-v6-fair-1.0"
V6FAIR_RULES_BASE = "covex-v6-state"


class V6FairArm(VS.V6StateArm):
    """covex-v6-state plus the deficit feed and the value reader."""

    def __init__(self, name: str = "covex-v6-fair", *,
                 deficit_feed: bool = True, value_reader: bool = True,
                 over_limit_infeasible: bool = True,
                 **kw: Any) -> None:
        # D170 is ON from this rung up, and only from this rung up. covex-v6-fair and covex-v6
        # have NO committed cells, so switching it on costs no provenance. Rungs 0 to 2 keep it
        # OFF because turning it on there would put the rule behind a version label whose cells
        # are already committed, and that is the user's call, not mine: the rule provably changes
        # nothing on any committed cell (18 over-limit questions exist, all at seed 7, and no arm
        # of ours sent one), so the choice is about the label and not about the numbers.
        VS.V6StateArm.__init__(self, name=name,
                               over_limit_infeasible=over_limit_infeasible, **kw)
        self.arm_version = V6FAIR_VERSION
        self.deficit_feed = bool(deficit_feed)
        self.value_reader = bool(value_reader)
        self.live2_source = (self.live2_source
                             + "; plus the deficit feed (cf_objective.DeficitCounters.observe "
                               "from the coordinator's completion hook) and the value reader")

    def live2_describe(self) -> Dict[str, Any]:
        import arm_names_v6 as V6N
        d = dict(VS.V6StateArm.live2_describe(self))
        d.update(arm=self.name, arm_version=V6FAIR_VERSION,
                 rung=V6N.describe("covex-v6-fair"),
                 covex_v6_fair=dict(
                     rules_base=V6FAIR_RULES_BASE,
                     deficit_feed=self.deficit_feed,
                     value_reader=self.value_reader,
                     over_limit_infeasible=dict(
                         on=bool(getattr(self._rules, "over_limit_infeasible", False)),
                         limit_tokens=32768, ruling="D170",
                         counter="over_limit_infeasible, over_limit_tokens_max"),
                     on_time_rule="cloud_on_time OR device_on_time (D155 (3))",
                     feed_blind_spot=("declined opportunities never reach live2_completed, so "
                                      "the counters see the SERVED population and a device "
                                      "whose requests are declined has its shortfall "
                                      "UNDERCOUNTED; see deficit_feed_unseen_declines")))
        return d

    # ---- the feed ----------------------------------------------------------------------------
    def live2_completed(self, rec: Dict[str, Any]) -> None:
        inner = getattr(self._rules, "live2_completed", None)
        if callable(inner):
            inner(rec)
        if not self.deficit_feed:
            return
        if str(rec.get("kind")) in ("piece", "whole"):
            # a build is not an answer and has no deadline of its own
            self.stats["deficit_feed_skipped_build"] += 1
            return
        did = rec.get("device_id")
        if did is None:
            self.stats["deficit_feed_skipped_no_device"] += 1
            return
        cloud = rec.get("cloud_on_time")
        dev = rec.get("device_on_time")
        if cloud is None and dev is None:
            # no deadline was recoverable for this completion: COUNTED, never guessed on-time
            self.stats["deficit_feed_skipped_no_deadline"] += 1
            return
        on_time = bool(cloud) or bool(dev)
        self.stats["deficit_feed_observations"] += 1
        self.stats["deficit_feed_on_time" if on_time else "deficit_feed_late"] += 1
        if cloud and not dev:
            self.stats["deficit_feed_carried_by_cloud"] += 1
        elif dev and not cloud:
            self.stats["deficit_feed_carried_by_device"] += 1
        elif cloud and dev:
            self.stats["deficit_feed_carried_by_both"] += 1
        kind = {"monitor": "dashcam"}.get(str(rec.get("kind")), "robot")
        try:
            self._cf_engine().counters.observe(str(did), on_time=on_time, kind=kind)
        except Exception:                                                      # noqa: BLE001
            self.stats["deficit_feed_observe_failed"] += 1

    def decide(self, obs: Observation) -> Action:
        act = VS.V6StateArm.decide(self, obs)
        if self.deficit_feed:
            # THE FEED'S BLIND SPOT, COUNTED AT THE ONLY PLACE IT IS VISIBLE. A declined
            # opportunity is never submitted, so it never reaches `live2_completed` and never
            # reaches the counters. It is visible HERE, in the action this arm just produced, and
            # nowhere later. Without this count the shortfall of a device whose requests are being
            # declined reads as zero, which is the exact case the deficit weighting exists to
            # catch, and the counters would look complete while missing it.
            for ra in (act.recall or ()):
                if str(getattr(ra, "decision", "")).upper() != "CLOUD":
                    self.stats["deficit_feed_unseen_declines"] += 1
            # the weights the feed is producing, so a run can show the mechanism is no longer
            # multiplying everything by one
            try:
                c = self._cf_engine().counters
                ws = [c.weight(d) for d in c.devices]
                if ws:
                    self.stats["deficit_weight_max_milli"] = max(
                        int(self.stats.get("deficit_weight_max_milli", 0)),
                        int(round(max(ws) * 1000.0)))
                    self.stats["deficit_devices_above_1"] = sum(1 for w in ws if w > 1.0)
            except Exception:                                                  # noqa: BLE001
                pass
        return act


V6FAIR_ARMS = {
    "covex-v6-fair": lambda **kw: V6FairArm(name="covex-v6-fair", **kw),
    # Step 4 negative control: both added channels off must collapse to covex-v6-state
    "covex-v6-fair-off": lambda **kw: V6FairArm(name="covex-v6-fair-off", deficit_feed=False,
                                                value_reader=False, **kw),
    "covex-v6-fair-nofeed": lambda **kw: V6FairArm(name="covex-v6-fair-nofeed",
                                                   deficit_feed=False, **kw),
    "covex-v6-fair-novalue": lambda **kw: V6FairArm(name="covex-v6-fair-novalue",
                                                    value_reader=False, **kw),
    # one-factor ablation of the D170 rule, so "with the rule" has a comparator
    "covex-v6-fair-nolimit": lambda **kw: V6FairArm(name="covex-v6-fair-nolimit",
                                                    over_limit_infeasible=False, **kw),
}


def register() -> None:
    import arms as A
    VS.register()
    A.ARMS.update(V6FAIR_ARMS)
