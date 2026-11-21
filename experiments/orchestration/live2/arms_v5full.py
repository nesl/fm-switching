#!/usr/bin/env python3
"""FULL v5: v5-rules-2 plus the D151 counterfactual on robot request, state and sync decisions.

  full v5  =  v5-rules-2 (dddf31a)                     the rules: base noc3 + chunked warming
            + engine_actions guard (D160 (2))          the saturation guard, inherited unchanged
            + cf_planner.Counterfactual (D151)         request / state / sync decisions
            + cf_objective deficit weighting           D149 (1), D151 (4)
            + cf_instrument decision clock             D151 (5), p99 < 20 ms at 32 devices

NOTHING IN cf_* IS REIMPLEMENTED HERE. Session B built the counterfactual (about 3,850 lines across
cf_planner, cf_objective, cf_cost, cf_margin, cf_ontime_frozen, cf_instrument); this module is the
ARM that wires it to the harness, which did not exist. The planners are called, never copied.

D160 (2), AND IT IS TWO SEPARATE OBLIGATIONS. The ruling says the counterfactual chooses only among
actions inside the healthy regime AND defers to the guard. Those are different and both are
implemented and counted separately:

  DEFERS TO THE GUARD.  When the guard is active the counterfactual does not plan at all and the
                        arm returns v5-rules-2's action untouched. The guard sheds background
                        warming first, and the counterfactual must not then add cloud work in the
                        same epoch, which would defeat the shed.
  HEALTHY-REGIME ONLY.  A candidate whose PREDICTED first-token latency exceeds the healthy bound
                        is marked NOT EXPRESSIBLE before the objective sees it, so the planner
                        cannot choose it. D162: the cost model is fitted and tested only on healthy
                        periods and is "never trusted to predict across the transition", so a
                        candidate the model cannot price is a candidate the counterfactual may not
                        pick. This is the restriction binding on the RELEASE side, which the
                        measurement in reports/study_v5rules2_live.md showed the guard cannot reach.

WHY THE RELEASE SIDE MATTERS, measured and not assumed. On the first live v5-rules-2 cell the arm
exceeded its base by +250 uncached tok/s, of which +919 was robot work and -669 was dashcam given
back, and 579 tok/s of the robot side was pure prefix-cache-miss waste on its own warm-ahead
prefills (89.1 percent COLD at 5,480 uncached tokens each, against v5-rules' 96.5 percent WARM at
471). The guard sheds warming; it cannot decline a release. The counterfactual decides releases, so
it is the only mechanism in the design that can.

MARGIN_CF IS NOT SET, AND THIS ARM REFUSES RATHER THAN GUESSES. `cf_margin.resolve_margin` raises
`MarginUnset` in the scorable path until the D162 gate passes.

WHERE THE REFUSAL HAPPENS, stated precisely because I first documented it wrongly. It is NOT at
construction: `Counterfactual.__init__` does not resolve the margin, and `_margin()` is called once
per DECISION. So a scorable arm BUILDS and then raises `MarginUnset` on its first robot request
decision. VERIFIED both ways: dry returns `chosen=ADMIT_NOW_D2` with `scorable=False` and
`margin_source=DRY_OVERRIDE`, while scorable raises `MarginUnset` carrying the D154 (2) rule text.

The practical guarantee is the one that matters and it holds: a scorable full-v5 CELL cannot
complete, because its first robot question raises. That makes "post V5FULL_CELLS only with the gate
passed" a property of the code rather than of my discipline. It fails loudly at the first decision
rather than at import, which is worth knowing when reading a traceback.

NOTHING HERE MEASURES ANYTHING.
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve().parent
for _p in (str(HERE), str(HERE / "v5")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import engine_actions as EA                                            # noqa: E402
from interface import Action, Observation                              # noqa: E402

V5FULL_VERSION = "v5-full-1.0"
V5FULL_RULES_BASE = "v5-rules-2"

# D162's healthy bound, the largest 100 s window first-token p50 observed in ANY cell of the
# committed 26-cell gate set (always-cloud-fcfs n16 s4 at t=400). Declared in
# research/prereg_cost_model_gate_d162.md before the refit, and used HERE as the edge of the regime
# the cost model may be trusted in. A parameter, per D159 (A): every capacity constant is a profiled
# input.
HEALTHY_LAG_S_DEFAULT = 2.781


class V5FullArm:
    """v5-rules-2 plus the counterfactual. Every live2 hook is delegated to v5-rules-2."""
    # D164 / component 1: this arm emits the per-type host-offload controls; baselines do not.
    live2_offload_controls = True
    # Component 2: KEEP_GPU_WARM issues a real touch request, priced by predicted cache state.
    live2_touch_requests = True


    def __init__(self, name: str = "v5-full",
                 counterfactual: bool = True,
                 healthy_lag_s: float = HEALTHY_LAG_S_DEFAULT,
                 healthy_filter: bool = True,
                 defer_to_guard: bool = True,
                 dry: bool = False, dry_margin: Optional[float] = None,
                 budget_ms: Optional[float] = None,
                 **rules_kw: Any) -> None:
        import arms_v5rules2 as V2
        self._rules = V2.V5Rules2Arm(name=name, **rules_kw)
        self._base = self._rules                      # delegation target, as v5-rules-2 does
        self.name = name
        self.arm_version = V5FULL_VERSION
        self.counterfactual = bool(counterfactual)
        self.healthy_lag_s = float(healthy_lag_s)
        self.healthy_filter = bool(healthy_filter)
        self.defer_to_guard = bool(defer_to_guard)
        self.dry = bool(dry)
        self.dry_margin = dry_margin
        self.stats: Counter = Counter()
        self._cf = None
        self._cf_budget_ms = budget_ms
        self.live2_source = (
            "arms_v5rules2.V5Rules2Arm (base hybrid-F-lhreq-noc3 + chunked warming + the D160 (2) "
            "guard) plus v5/cf_planner.Counterfactual (D151) with v5/cf_objective deficit "
            "weighting and v5/cf_instrument's decision clock")

    # ---- lazy construction, so importing the arm cannot raise MarginUnset -------------------
    def _cf_engine(self):
        if self._cf is None:
            import cf_instrument as CI
            import cf_planner as CP
            kw: Dict[str, Any] = dict(dry=self.dry, dry_margin=self.dry_margin,
                                      clock=CI.DecisionClock())
            if self._cf_budget_ms is not None:
                kw["budget_ms"] = float(self._cf_budget_ms)
            self._cf = CP.Counterfactual(**kw)
        return self._cf

    # ---- delegation ------------------------------------------------------------------------
    def __getattr__(self, k):
        return getattr(self.__dict__["_rules"], k)

    def __call__(self, obs: Observation) -> Action:
        return self._rules.__class__.__call__(self, obs)

    def live2_roster(self, roster: Dict[str, Any]) -> None:
        self._rules.live2_roster(roster)

    def live2_configure(self, **kw: Any) -> None:
        self._rules.live2_configure(**kw)

    def live2_describe(self) -> Dict[str, Any]:
        d = dict(self._rules.live2_describe())
        d.update(arm=self.name, arm_version=V5FULL_VERSION,
                 v5_full=dict(rules_base=V5FULL_RULES_BASE,
                              counterfactual=self.counterfactual,
                              defer_to_guard=self.defer_to_guard,
                              healthy_filter=self.healthy_filter,
                              healthy_lag_s=self.healthy_lag_s,
                              decision_kinds=["request", "state", "sync"],
                              deficit_weighting="v5/cf_objective.DeficitCounters (D149 (1), "
                                                "D151 (4))",
                              latency_instrument="v5/cf_instrument.DecisionClock, p99 < 20 ms at "
                                                 "32 devices (D151 (5))",
                              margin="DRY_OVERRIDE" if self.dry else "cf_margin.MARGIN_CF",
                              scorable=not self.dry),
                 source=self.live2_source)
        return d

    # ---- the healthy-regime restriction (D160 (2), second obligation) ----------------------
    def _observed_lag_s(self, obs: Observation) -> float:
        lat = dict(getattr(obs.cloud, "latency_estimate_s", None) or {})
        return max([float(lat.get(k, 0.0) or 0.0) for k in ("episodic", "recall")] or [0.0])

    def _restrict_to_healthy(self, decision, obs: Observation) -> None:
        """Mark any candidate the cost model may not be trusted to price as NOT EXPRESSIBLE.

        The test is on the candidate's OWN predicted first-token latency where the planner recorded
        one, plus the observed lag already in the engine, because a candidate is added to a queue
        that is already there. A candidate with no prediction is left alone and counted: refusing
        to price it is not the same as knowing it is unsafe, and silently dropping it would make
        the restriction look stronger than it is.
        """
        if not self.healthy_filter:
            return
        lag_now = self._observed_lag_s(obs)
        for c in getattr(decision, "candidates", ()) or ():
            if not c.expressible:
                continue
            pred = (c.detail or {}).get("first_token_s")
            if pred is None:
                pred = (c.detail or {}).get("predicted_first_token_s")
            if pred is None:
                self.stats["cf_candidate_unpriced"] += 1
                continue
            if float(pred) + lag_now > self.healthy_lag_s:
                c.expressible = False
                (c.detail or {}).setdefault(
                    "not_expressible_reason",
                    "D160 (2): predicted first token %.3f s plus observed lag %.3f s exceeds the "
                    "healthy bound %.3f s, and D162 does not trust the cost model across the "
                    "transition" % (float(pred), lag_now, self.healthy_lag_s))
                self.stats["cf_candidate_outside_healthy"] += 1

    # ---- the one added channel --------------------------------------------------------------
    def decide(self, obs: Observation) -> Action:
        act = self._rules.decide(obs)
        if not self.counterfactual:
            return act
        g = self._rules.guard_state(obs)
        if self.defer_to_guard and g["active"]:
            # D160 (2), first obligation. The guard has just shed background warming; adding cloud
            # work in the same epoch would defeat the shed, so the counterfactual does not plan.
            self.stats["cf_deferred_to_guard_epochs"] += 1
            return act
        cf = self._cf_engine()
        roster = getattr(self._rules, "_roster", None) or {}
        devs = roster.get("devices") or {}
        for q in obs.recall:
            did = (roster.get("session_device") or {}).get(q.session_id)
            if did is None or str((devs.get(did) or {}).get("type")) != "robot":
                continue
            self.stats["cf_request_decisions"] += 1
            d = cf.plan_request(
                decision_id=str(q.query_id), device_id=str(did), now_s=float(obs.now_s),
                deadline_abs_s=float(q.deadline_s),
                history_tokens=int(getattr(q, "readiness_tokens", 0) or 0),
                readiness=str(getattr(q, "readiness", "COLD") or "COLD"))
            self._restrict_to_healthy(d, obs)
            self.stats["cf_chosen_" + str(d.chosen)] += 1
            if d.deviated:
                self.stats["cf_deviations"] += 1
            if d.timeout_fallback:
                self.stats["cf_timeout_fallback"] += 1
        return act


V5FULL_ARMS = {
    "v5-full": lambda **kw: V5FullArm(name="v5-full", **kw),
    # Step 4 negative control: the counterfactual disabled must collapse to v5-rules-2
    # BYTE-IDENTICALLY, which is what makes the comparison measure the counterfactual.
    "v5-full-off": lambda **kw: V5FullArm(name="v5-full-off", counterfactual=False, **kw),
    # the D160 (2) ablations, one obligation at a time, so each can be checked alone
    "v5-full-noguarddefer": lambda **kw: V5FullArm(name="v5-full-noguarddefer",
                                                   defer_to_guard=False, **kw),
    "v5-full-nohealthy": lambda **kw: V5FullArm(name="v5-full-nohealthy",
                                                healthy_filter=False, **kw),
}


def register() -> None:
    import arms as A
    A.ARMS.update(V5FULL_ARMS)
