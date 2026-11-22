#!/usr/bin/env python3
"""covex-v6-state, rung 2 of the spec v6 ladder (D172).

    covex-v6-rules  (chunked just-in-time warming + saturation guard)
      + per-type HOST RETENTION        `max_offload_tokens = 0` for alert and single-shot
      + TOUCH chosen by `plan_state`   not by a rule
      + BELIEF corrected from engine telemetry, including host hits
      + STATE-BASED PRICING            a warm costs what its predicted cache state says

WHAT THIS RUNG ADDS IS FOUR SWITCHES AND ONE DECISION, and only the decision is new code. The
three capability flags were built in earlier components and sat unused because no arm declared
them; this arm declares them. The decision is `plan_state`, which until now had no caller outside
`cf_proofs.py` and therefore implemented no causal link in any run (CLAUDE.md Step 2: a quantity
that is written and never read is ABSENT).

THE ONE PLACE THIS ARM IS PARAMETRIC AND A READER MUST NOT MISS IT. `plan_state`'s candidate set
is WARM, TOUCH, KEEP, RELOAD, HOLD_BACK and SLICE. HOLD_BACK's value IS `harm_warm` and SLICE's
is half of it, and NO COMMITTED MEASUREMENT OF `harm_warm` EXISTS: StudySLICE1 has not run. So
this arm passes `harm_warm = 0.0` and the two candidates whose entire value is that number are
scored at zero and can never win. The live comparison at this rung is WARM and TOUCH against
KEEP, which is the comparison the rung is named for. Reporting a HOLD_BACK or SLICE result off
this arm would be reporting a declared input as a finding.

RELOAD is offered only at `belief == host` and no committed cell has ever observed a host-warm
session (cold 14,472 / gpu 1,442 / host never, over 39 committed 16-device cells). It stays in
the candidate set, unscored, so a run that DOES reach host-warm records it rather than silently
not offering it. Under Rule 2 a null there is UNEXERCISED, not a negative.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional

import sys
from pathlib import Path as _Path

# `interface` lives in `baselines/`, which the live2 entry points put on the path. This module can
# also be imported directly by a proof, so it does not assume someone else did it first.
for _p in (str(_Path(__file__).resolve().parents[1] / "baselines"),
           str(_Path(__file__).resolve().parent),
           str(_Path(__file__).resolve().parent / "v5"),
           str(_Path(__file__).resolve().parent / "fleet")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from interface import Action, Observation, SessionAction                       # noqa: E402

import arms_v5rules2 as V2                                                     # noqa: E402

V6STATE_VERSION = "covex-v6-state-1.0"
V6STATE_RULES_BASE = "v5-rules-2"

ROBOT_DEADLINE_S = 3.0          # D147, the committed robot deadline
# `plan_state`'s horizon cap already bounds the look-ahead; this is the minimum believed-GPU mass
# at which a session is treated as warm for pricing. Declared, not swept.
WARM_BELIEF_MIN = 0.5


class V6StateArm:
    """covex-v6-rules plus per-type state, touch chosen by plan_state, and state pricing."""

    decides = ("streams", "recall", "sessions")

    # The four capability flags the coordinator reads are INSTANCE attributes, not class
    # attributes, because `covex-v6-state-off` has to turn OFF EVERYTHING THIS RUNG ADDS. As class
    # attributes they stayed on under `-off`, state pricing kept changing the budget charge, and
    # the "negative control" differed from covex-v6-rules by 4,376 rows of decisions while
    # claiming to be the rung with its channel disabled. A control that does not collapse is not
    # a control.
    def __init__(self, name: str = "covex-v6-state", *,
                 plan_state: bool = True,
                 offload_controls: Optional[bool] = None,
                 touch_requests: Optional[bool] = None,
                 state_priced_costs: Optional[bool] = None,
                 belief_apply: Optional[bool] = None,
                 dry: bool = False, dry_margin: Optional[float] = None,
                 budget_ms: Optional[float] = None,
                 **rules_kw: Any) -> None:
        self._rules = V2.V5Rules2Arm(name=name, **rules_kw)
        self._base = self._rules
        self.name = name
        self.arm_version = V6STATE_VERSION
        self.plan_state = bool(plan_state)
        # each capability defaults to the rung's setting and can be ablated one at a time
        def _d(v: Optional[bool]) -> bool:
            return self.plan_state if v is None else bool(v)
        self.live2_offload_controls = _d(offload_controls)
        self.live2_touch_requests = _d(touch_requests)
        self.live2_state_priced_costs = _d(state_priced_costs)
        self.live2_belief_apply = _d(belief_apply)
        self.dry = bool(dry)
        self.dry_margin = dry_margin
        self._cf = None
        self._cf_budget_ms = budget_ms
        self.stats: Counter = Counter()
        # D172: the predicted gain of every state decision, kept so the rung can report its own
        # distribution against MARGIN_CF instead of only the count of decisions it made.
        self.state_deltas: List[float] = []
        self._q_cache_key: Any = None
        self._q_cache: List[Dict[str, Any]] = []
        self.live2_source = (
            "arms_v5rules2.V5Rules2Arm (covex-v6-rules) plus v5/cf_planner.plan_state for the "
            "TOUCH / KEEP decision, offload_policy per-type host retention, touch_policy state "
            "pricing, and coordinator belief-apply from engine telemetry")

    # ---- lazy, so importing the arm cannot raise MarginUnset ---------------------------------
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

    # ---- delegation, named statically (the v5-full recursion, D172) --------------------------
    def __getattr__(self, k):
        return getattr(self.__dict__["_rules"], k)

    def __call__(self, obs: Observation) -> Action:
        return V2.V5Rules2Arm.__call__(self, obs)

    def live2_roster(self, roster: Dict[str, Any]) -> None:
        self._rules.live2_roster(roster)

    def live2_configure(self, **kw: Any) -> None:
        self._rules.live2_configure(**kw)

    def live2_describe(self) -> Dict[str, Any]:
        import arm_names_v6 as V6N
        d = dict(self._rules.live2_describe())
        d.update(arm=self.name, arm_version=V6STATE_VERSION,
                 rung=V6N.describe("covex-v6-state"),
                 covex_v6_state=dict(
                     rules_base=V6STATE_RULES_BASE,
                     plan_state=self.plan_state,
                     per_type_host_retention="offload_policy.RULE (alert and single-shot: "
                                             "max_offload_tokens = 0; robot: retained)",
                     touch="touch_policy.should_touch with the M6 mixed-tier guard; the CHOICE "
                           "is plan_state's, the guard is the coordinator's",
                     belief_correction="apply (engine telemetry, including host hits)",
                     state_priced_costs=self.live2_state_priced_costs,
                     offload_controls=self.live2_offload_controls,
                     touch_requests=self.live2_touch_requests,
                     belief_apply=self.live2_belief_apply,
                     harm_warm=("COMPUTED from the D162 model's per_queue_token "
                                "coefficient per research/prereg_harm_warm_d172.md; never a "
                                "declared grid value. Capped at the healthy-regime bound with "
                                "harm_warm_capped counted"),
                     margin="DRY_OVERRIDE" if self.dry else "cf_margin.MARGIN_CF",
                     scorable=not self.dry),
                 source=self.live2_source)
        return d

    # ---- the warm / cold delivery pair plan_state is scored on -------------------------------
    def _p_warm_cold(self, est_tokens: int, built_tokens: int) -> Optional[Dict[str, float]]:
        """P(this session's next question is answered on time) warm against cold.

        The SAME cost model and the SAME delivery curve the request counterfactual uses, so the
        two kinds are priced in one currency. Warm means the built prefix is cached; cold means
        none of it is. Returns None when the model cannot price the session, and the caller counts
        that rather than substituting a number.
        """
        try:
            import cf_cost as CC
            cf = self._cf_engine()
            warm = CC.predict(cf.model, int(est_tokens), int(built_tokens), 0, 0)
            cold = CC.predict(cf.model, int(est_tokens), 0, 0, 0)
            return {
                "warm": CC.p_on_time(cf.residuals, warm.engine_s,
                                     ROBOT_DEADLINE_S - CC.LINK_RTT_S),
                "cold": CC.p_on_time(cf.residuals, cold.engine_s,
                                     ROBOT_DEADLINE_S - CC.LINK_RTT_S),
            }
        except Exception:                                                      # noqa: BLE001
            return None

    def _queued_behind(self, obs: Observation, session_id: str) -> List[Dict[str, Any]]:
        """The requests a background warm would sit in front of, with their own predicted service
        time and slack. One `predict` per pending request per epoch, cached, because the harm term
        is evaluated once per session and the pending set does not change inside an epoch."""
        key = (int(obs.epoch) if isinstance(obs.epoch, int) else id(obs))
        if self._q_cache_key != key:
            self._q_cache_key = key
            self._q_cache = []
            try:
                import cf_cost as CC
                cf = self._cf_engine()
                sdev = (getattr(self._rules, "_roster", None) or {}).get("session_device") or {}
                for qy in (obs.recall or ()):
                    tok = int(getattr(qy, "readiness_tokens", 0) or 0)
                    pr = CC.predict(cf.model, tok, 0, 0, 0)
                    self._q_cache.append({
                        "req_id": str(qy.query_id), "session_id": str(qy.session_id),
                        "device_id": str(sdev.get(qy.session_id, "")),
                        "engine_s": float(pr.engine_s),
                        "slack_s": float(qy.deadline_s) - float(obs.now_s) - CC.LINK_RTT_S,
                        "p_device_on_time": 1.0, "weight": 1.0})
            except Exception:                                                  # noqa: BLE001
                self._q_cache = []
        return [r for r in self._q_cache if r["session_id"] != session_id]

    def _harm_warm(self, obs: Observation, session_id: str, uncached_tokens: int) -> float:
        """`harm_warm`, COMPUTED from the D162 model and never declared.

        Pre-registered in `research/prereg_harm_warm_d172.md` before any grid was rerun under it.
        Returns 0.0 only when nothing is queued behind the warm, which is a real zero and is
        counted separately from a refusal to price.
        """
        others = self._queued_behind(obs, session_id)
        if not others:
            self.stats["harm_warm_no_queue"] += 1
            return 0.0
        try:
            import cf_cost as CC
            import cf_objective as CO
            cf = self._cf_engine()
            tab = cf.table
            h = CO.harm_warm_from_queue_delay(
                int(uncached_tokens), others,
                p_on_time=(lambda eng, slack: CC.p_on_time(cf.residuals, eng, slack)),
                acc_cloud=float(tab["cloud_D2"]), acc_device=float(tab["device"]),
                counters=cf.counters)
        except Exception:                                                      # noqa: BLE001
            self.stats["harm_warm_unpriced"] += 1
            return 0.0
        self.stats["harm_warm_priced"] += 1
        if h.capped:
            self.stats["harm_warm_capped"] += 1
        if h.total > 0.0:
            self.stats["harm_warm_nonzero"] += 1
            self.stats["harm_warm_milli_sum"] += int(round(h.total * 1000.0))
            self.stats["harm_warm_max_milli"] = max(
                int(self.stats.get("harm_warm_max_milli", 0)), int(round(h.total * 1000.0)))
        return float(h.total)

    def _p_question(self, device_id: str, now_s: float) -> Dict[str, float]:
        """The causal per-session question-rate estimate the rules arm already keeps (D11, D48).

        Never the trace's future: it is an EWMA over gaps between questions ALREADY SEEN.
        """
        # KEYED BY DEVICE. `_gap_ewma` and `_last_q_t` are the rules arm's own dicts and they
        # are keyed on device_id, not session_id (`arms_v5rules2.py:207-213`). Keying this lookup
        # on the session instead returned a miss for every session, every epoch, and the whole
        # rung silently planned nothing while every other sign said it was wired.
        gap = float((getattr(self._rules, "_gap_ewma", None) or {}).get(device_id, 0.0) or 0.0)
        last = float((getattr(self._rules, "_last_q_t", None) or {}).get(device_id, now_s)
                     or now_s)
        if gap <= 0.0:
            return {"p_question": 0.0, "next_question_s": float(now_s), "has_estimate": 0.0}
        nxt = last + gap
        # P(a question falls inside the warm horizon), as the fraction of the gap already elapsed.
        elapsed = max(float(now_s) - last, 0.0)
        return {"p_question": max(min(elapsed / gap, 1.0), 0.0),
                "next_question_s": max(nxt, float(now_s)), "has_estimate": 1.0}

    # ---- the one added channel ---------------------------------------------------------------
    def decide(self, obs: Observation) -> Action:
        act = self._rules.decide(obs)
        if not self.plan_state:
            return act
        g = self._rules.guard_state(obs)
        if g["active"]:
            # Same obligation as v5-full's: the guard has just shed background warming, so this
            # rung does not add state work in the same epoch.
            self.stats["state_deferred_to_guard_epochs"] += 1
            return act
        cf = self._cf_engine()
        roster = getattr(self._rules, "_roster", None) or {}
        devs = roster.get("devices") or {}
        sdev = roster.get("session_device") or {}
        built = roster.get("built_tokens_by_session") or {}
        est = roster.get("est_tokens_by_session") or {}
        belief = roster.get("belief_by_session") or {}
        already = {sa.session_id for sa in (act.sessions or ())}
        extra: List[Any] = []
        for sid in (obs.live_sessions or ()):
            did = sdev.get(sid)
            if did is None or str((devs.get(did) or {}).get("type")) != "robot":
                continue
            b = int(built.get(sid, 0) or 0)
            if b <= 0:
                self.stats["state_skipped_nothing_built"] += 1
                continue
            if sid in already:
                # the rules arm is already acting on this session this epoch; a second action for
                # the same session in one epoch is not expressible, so the rung does not plan it
                self.stats["state_skipped_rules_acting"] += 1
                continue
            q = self._p_question(str(did), float(obs.now_s))
            if not q["has_estimate"]:
                self.stats["state_skipped_no_question_estimate"] += 1
                continue
            p = self._p_warm_cold(int(est.get(sid, b) or b), b)
            if p is None:
                self.stats["state_skipped_unpriced"] += 1
                continue
            bb = dict(belief.get(sid) or {})
            host_warm = float(bb.get("host", 0.0) or 0.0) >= WARM_BELIEF_MIN
            self.stats["state_decisions"] += 1
            d = cf.plan_state(
                decision_id="st:%s:%d" % (sid, self.stats["state_decisions"]),
                device_id=str(did),
                now_s=float(obs.now_s), p_question=float(q["p_question"]),
                next_question_s=float(q["next_question_s"]),
                p_on_time_warm=float(p["warm"]), p_on_time_cold=float(p["cold"]),
                harm_warm=self._harm_warm(obs, sid, max(int(est.get(sid, b) or b) - b, 0)),
                warm_expressible=True, host_warm=host_warm,
                tokens_to_build=max(int(est.get(sid, b) or b) - b, 0),
                slice_tokens=getattr(self._rules, "slice_tokens", None))
            self.stats["state_chosen_" + str(d.chosen)] += 1
            if d.delta is not None:
                self.state_deltas.append(float(d.delta))
                if d.margin_effective is not None and d.delta > d.margin_effective:
                    self.stats["state_delta_over_margin"] += 1
                # the gain distribution, as counters, so a dry runner that returns only `stats`
                # still carries it (D172 requires the per-kind distribution against MARGIN_CF)
                self.stats["state_delta_max_milli"] = max(
                    int(self.stats.get("state_delta_max_milli", 0)),
                    int(round(float(d.delta) * 1000.0)))
                for lo in (0.0, 0.01, 0.05, 0.10, 0.12, 0.14, 0.16, 0.16456, 0.18, 0.20, 0.25):
                    if float(d.delta) > lo:
                        self.stats["state_delta_gt_%s" % ("%g" % lo).replace(".", "p")] += 1
                self.stats["state_delta_milli_sum"] += int(round(float(d.delta) * 1000.0))
                self.stats["state_delta_n"] += 1
            # HOLD_BACK, WARM and TOUCH gains SEPARATELY against the margin, per the ruling
            for c in (d.candidates or ()):
                if c.name not in ("HOLD_BACK", "WARM", "TOUCH") or c.value is None:
                    continue
                self.stats["gain_%s_n" % c.name] += 1
                self.stats["gain_%s_milli_sum" % c.name] += int(round(float(c.value) * 1000.0))
                self.stats["gain_%s_max_milli" % c.name] = max(
                    int(self.stats.get("gain_%s_max_milli" % c.name, 0)),
                    int(round(float(c.value) * 1000.0)))
                if d.margin_effective is not None and float(c.value) > d.margin_effective:
                    self.stats["gain_%s_over_margin" % c.name] += 1
            if d.deviated:
                self.stats["state_deviations"] += 1
            if d.chosen == "TOUCH":
                extra.append(SessionAction(session_id=sid, action="KEEP_GPU_WARM"))
                self.stats["state_touch_emitted"] += 1
        if extra:
            act.sessions = list(act.sessions or ()) + extra
        return act


V6STATE_ARMS = {
    "covex-v6-state": lambda **kw: V6StateArm(name="covex-v6-state", **kw),
    # CLAUDE.md Step 4 negative control: the added channel off must collapse to covex-v6-rules
    # BYTE-IDENTICALLY, which is stronger than converging.
    "covex-v6-state-off": lambda **kw: V6StateArm(name="covex-v6-state-off", plan_state=False,
                                                  **kw),
    # one-factor ablations, so each of the rung's four additions is checkable alone
    "covex-v6-state-noretain": lambda **kw: V6StateArm(name="covex-v6-state-noretain",
                                                       offload_controls=False, **kw),
    "covex-v6-state-notouch": lambda **kw: V6StateArm(name="covex-v6-state-notouch",
                                                      touch_requests=False, **kw),
    "covex-v6-state-noprice": lambda **kw: V6StateArm(name="covex-v6-state-noprice",
                                                      state_priced_costs=False, **kw),
    "covex-v6-state-nobelief": lambda **kw: V6StateArm(name="covex-v6-state-nobelief",
                                                       belief_apply=False, **kw),
}


def register() -> None:
    import arms as A
    import arms_v5rules2 as R2
    R2.register()
    A.ARMS.update(V6STATE_ARMS)
