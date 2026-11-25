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

WHERE `harm_warm` COMES FROM, AND WHAT IT IS AND IS NOT. `plan_state`'s candidate set is WARM,
TOUCH, KEEP, RELOAD, HOLD_BACK and SLICE. HOLD_BACK's value IS `harm_warm` and SLICE's is half of
it. This arm COMPUTES that number: `_harm_warm` calls `cf_objective.harm_warm_from_queue_delay`,
which takes the warm's uncached tokens through the committed D162 `per_queue_token` coefficient
to a per-request delay, through the same `p_on_time` curve every other v5 prediction uses, and
values the rows with `option_value`, the same function `harm_to_others` uses, so this term and
the request-decision harm stay in one currency under D171 (2). Pre-registered in
`research/prereg_harm_warm_d172.md` BEFORE any grid was rerun under it. Capped at the
healthy-regime bound with `harm_warm_capped` counted, never silent.

IT IS STILL A PREDICTION, which is a different sentence from the one this docstring used to make.
NO COMMITTED MEASUREMENT of a warm's realised cost exists, because StudySLICE1 has not run, so a
HOLD_BACK or SLICE result off this arm is a statement about the D162 COST MODEL and must say so.
What it is no longer is a declared grid value read back out as if it were a model output, which
is what `harm_warm = 0.0` made it until `a353cb0c`.

AND THE WARMING CANDIDATES ARE SCORED ONLY WHERE THERE IS A REBUILD TO ACT ON. `harm_warm` is the
harm a warm WOULD do, so scoring it for a session nobody is warming decides against a rebuild
that was never going to happen. Before `f63aea35` this arm did exactly that and chose HOLD_BACK
897 times on a 16-device cell, every one clearing the margin, while emitting nothing for any of
them: UNEXPRESSIBLE under Rule 2, and it would have been reported as 897 deviations. WARM,
HOLD_BACK and SLICE are now scored only where the rules arm has asked to MATERIALIZE this session
this epoch, `tokens_to_build` is that ask's own target, and HOLD_BACK and SLICE act by REMOVING
that ask from the action, which is the channel that makes them expressible at all.

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
import d162_price as DP                                                        # noqa: E402
import cf_planner as CP                                                        # noqa: E402
from touch_policy import TOUCH_UNCACHED_TOKENS as TP_TOUCH_UNCACHED            # noqa: E402

V6STATE_VERSION = "covex-v6-state-1.0"
V6STATE_RULES_BASE = "v5-rules-2"

ROBOT_DEADLINE_S = 3.0          # D147, the committed robot deadline
# `plan_state`'s horizon cap already bounds the look-ahead; this is the minimum believed-GPU mass
# at which a session is treated as warm for pricing. Declared, not swept.
WARM_BELIEF_MIN = 0.5

# --- D188 (2): the `_queued_behind` cache-key fix, BEHIND AN OFF-BY-DEFAULT ARM-SCOPED SWITCH ---
#
# THE DEFECT. `cstate.observation(self, now: float, epoch: str, ...)` (cstate.py:579) always passes
# a STR epoch, so the `isinstance(obs.epoch, int)` test in `_queued_behind` has never once been
# true and the cache key has always been `id(obs)`, a MEMORY ADDRESS. CPython reuses addresses, so
# a fresh Observation allocated where a freed one sat hits the entry written in a PREVIOUS decision
# period, and `_harm_warm` is then priced against a queue whose `slack_s` was computed from the
# previous period's `now_s`. The cached value is read into a decision: `_harm_warm` ->
# `cf_objective.harm_warm_from_queue_delay` -> `hw` / `harm_touch` -> `cf.plan_state`, whose
# `d.chosen` emits a KEEP_GPU_WARM SessionAction or removes a MATERIALIZE ask.
#
# THE FIX keys on the decision period itself, `(epoch, now_s)`, which cannot alias.
#
# IT IS OFF BY DEFAULT AND MUST STAY OFF until the final rung-2 arm and its comparators are rerun
# TOGETHER with it ON (user ruling D188 (2)). With the switch off, `key` is the exact expression
# this module has always used, so no cell running under today's arms can be affected.
QCACHE_KEY_FIX_SWITCH = "live2_qcache_key_fix"


class QCacheKeyFixSwitchError(RuntimeError):
    """The switch was declared as a truthy CLASS attribute, which D188 (2) forbids."""


def qcache_key_fix_enabled(arm: Any) -> bool:
    """Is the D188 key fix on for THIS ARM INSTANCE? Default False.

    INSTANCE-DICT LOOKUP ONLY, and a truthy CLASS attribute RAISES: the same shape as
    `release_recheck.arm_enables` and `share_admission.arm_enables`, and for the same reason. A
    class attribute would switch the fix on for every arm that inherits from this one in the same
    run and would make the cells incomparable. A class default of False is harmless and passes.
    """
    try:
        own = vars(arm)
    except TypeError:                                                          # pragma: no cover
        own = {}
    if QCACHE_KEY_FIX_SWITCH not in own:
        for klass in type(arm).__mro__:
            if bool(klass.__dict__.get(QCACHE_KEY_FIX_SWITCH, False)):
                raise QCacheKeyFixSwitchError(
                    "%s is ON as a CLASS attribute of %s and the instance declares nothing. "
                    "D188 (2) requires an arm-scoped INSTANCE attribute: a class-level switch "
                    "turns the fix on for every arm in the run."
                    % (QCACHE_KEY_FIX_SWITCH, klass.__name__))
        return False
    return bool(own[QCACHE_KEY_FIX_SWITCH])


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
                 d162_pricing: Optional[bool] = None,
                 charge_mode: Optional[str] = None,
                 # D175 (2): ON at EVERY covex-v6 rung, base included, as D170 specified. The
                 # committed cells of rungs 0 to 2 stay reusable only if their decision digests
                 # are unchanged, which is what d170_rule_proofs checks; none of our arms sent an
                 # over-limit request, so the rule has nothing to change there.
                 over_limit_infeasible: bool = True,
                 dry: bool = False, dry_margin: Optional[float] = None,
                 budget_ms: Optional[float] = None,
                 **rules_kw: Any) -> None:
        self._rules = V2.V5Rules2Arm(name=name,
                                     over_limit_infeasible=bool(over_limit_infeasible),
                                     **rules_kw)
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
        # DEFAULT FALSE, AND NOT THROUGH `_d`. `_d(None)` returns `self.plan_state`, which is
        # True for covex-v6-state, so routing this switch through it DECLARED the D162 charge on
        # every cell of the rung. The charge's own D102 proof FAILS and the reprice is HELD
        # pending a ruling, so the arm must not declare it until one turns it on.
        #
        # THIS IS WHAT I GOT WRONG AND IT COST A CELL. I said "the default charge is unchanged"
        # having checked the two MODE literals, `TOUCH_PRICE_MODE` and `CHARGE_MODE`, which are
        # indeed unchanged. Neither of them gates anything: `d162_price.arm_enables` reads THIS
        # attribute, and this attribute was True. covex-v6-state s6 ran the held charge, stalled
        # at 44,382 budget refusals with its last request submitted at t = 264 s of a 1,200 s
        # cell, and robot fell to 12 of 121. The same shape as the name check: I verified the
        # thing I was thinking about instead of the thing that decides the behaviour.
        self.live2_d162_pricing = (False if d162_pricing is None else bool(d162_pricing))
        # D174 (1): the charge MODE is the arm's, read by the coordinator through
        # d162_price.arm_charge_mode. An arm that declares none charges the ruled uncached-only.
        if charge_mode is not None and charge_mode not in DP.MODES:
            raise ValueError("unknown charge mode %r" % (charge_mode,))
        self.live2_charge_mode = charge_mode or DP.RULED_CHARGE_MODE
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
            import cf_objective as _CO
            # D206 item 1a: the weight source is DECLARED at the construction site, never
            # defaulted. Rung 4 does not come through here: `arms_v6cfr3` overrides `_cf_engine`
            # and injects the live feed, so this line is the rung-2 and rung-3 declaration only.
            kw: Dict[str, Any] = dict(dry=self.dry, dry_margin=self.dry_margin,
                                      clock=CI.DecisionClock(),
                                      counters=_CO.NoPlannerDeficitFeed(
                                          rung=getattr(self, "name", "covex-v6-state")))
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
                     d162_pricing=self.live2_d162_pricing,
                     budget_charge_mode=self.live2_charge_mode,
                     one_price_source=("D162 predicted first token, read identically by the "
                                       "planner's TOUCH harm and the coordinator's budget "
                                       "charge (user ruling, 2026-11-21)"),
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
        is evaluated once per session and the pending set does not change inside an epoch.

        THE KEY IS SWITCHED (D188 (2)). The OFF branch is the expression this method has always
        used and is the default; see QCACHE_KEY_FIX_SWITCH above for why it is wrong and why it
        stays the default tonight. The switch is RESOLVED ONCE PER ARM INSTANCE and memoised,
        because the OFF path runs inside the planner's wall-clock budget and an MRO scan per call
        would charge the budget for a switch that is off; setting the switch after this method has
        first run therefore does nothing, and every caller sets it at construction."""
        fix = self.__dict__.get("_qcache_key_fix_resolved")
        if fix is None:
            fix = qcache_key_fix_enabled(self)
            self.__dict__["_qcache_key_fix_resolved"] = fix
        if fix:
            key = (str(getattr(obs, "epoch", "")), float(obs.now_s))
        else:
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
        already = {sa.session_id: sa for sa in (act.sessions or ())}
        drop: set = set()
        extra: List[Any] = []
        for sid in (obs.live_sessions or ()):
            did = sdev.get(sid)
            if did is None or str((devs.get(did) or {}).get("type")) != "robot":
                continue
            b = int(built.get(sid, 0) or 0)
            if b <= 0:
                self.stats["state_skipped_nothing_built"] += 1
                continue
            act_now = already.get(sid)
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
            # HOLD_BACK ONLY MEANS SOMETHING WHERE THERE IS A REBUILD TO HOLD BACK. Its value is
            # the harm a warm WOULD do, so planning it for a session nobody is warming decides
            # against a rebuild that was never going to happen: the choice is made, nothing is
            # emitted, and under Rule 2 the result is UNEXPRESSIBLE, not a policy finding. So the
            # warming candidates are scored only where the rules arm has actually asked to
            # MATERIALIZE this session this epoch, and HOLD_BACK then REMOVES that ask.
            warming = (act_now is not None and str(getattr(act_now, "action", "")) == "MATERIALIZE")
            u = max(int(est.get(sid, b) or b) - b, 0)
            if warming:
                u = int(getattr(act_now, "target_tokens", 0) or u) - b
                u = max(u, 0)
            hw = self._harm_warm(obs, sid, u) if warming else 0.0
            if not warming and act_now is not None:
                # some other session action this epoch; a second one is not expressible
                self.stats["state_skipped_rules_acting"] += 1
                continue
            self.stats["state_decisions"] += 1
            self.stats["state_decisions_with_a_rebuild" if warming
                       else "state_decisions_without_a_rebuild"] += 1
            d = cf.plan_state(
                decision_id="st:%s:%d" % (sid, self.stats["state_decisions"]),
                device_id=str(did),
                now_s=float(obs.now_s), p_question=float(q["p_question"]),
                next_question_s=float(q["next_question_s"]),
                p_on_time_warm=float(p["warm"]), p_on_time_cold=float(p["cold"]),
                harm_warm=hw,
                # the touch's OWN harm, from the same price source the coordinator charges
                harm_touch=self._harm_warm(obs, sid, TP_TOUCH_UNCACHED),
                warm_expressible=bool(warming), host_warm=host_warm,
                tokens_to_build=u,
                slice_tokens=getattr(self._rules, "slice_tokens", None))
            CP.note_abandon(self.stats, d, float(getattr(cf, "budget_ms", 0.0)))
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
            if d.chosen == "TOUCH" and act_now is None:
                extra.append(SessionAction(session_id=sid, action="KEEP_GPU_WARM"))
                self.stats["state_touch_emitted"] += 1
            elif d.chosen in ("HOLD_BACK", "SLICE") and warming:
                # the channel HOLD_BACK acts through: the rebuild does not go out this epoch
                drop.add(sid)
                self.stats["state_%s_enacted" % d.chosen.lower()] += 1
            elif d.chosen in ("HOLD_BACK", "SLICE"):
                self.stats["state_%s_unexpressible" % d.chosen.lower()] += 1
        if drop:
            act.sessions = [sa for sa in (act.sessions or ())
                            if not (sa.session_id in drop
                                    and str(getattr(sa, "action", "")) == "MATERIALIZE")]
        if extra:
            act.sessions = list(act.sessions or ()) + extra
        return act


class V6RulesWorkOnlyArm(V2.V5Rules2Arm):
    """covex-v6-rules-wo: rung 1 with CORRECT BUDGET CHARGING and nothing else (D173 (2)).

    D173 (2) separates two things that had been one. Charging a request what the engine will
    actually do is a HARNESS correctness property and belongs at EVERY rung; pricing a DECISION by
    its predicted cache state is a POLICY component and stays covex-v6-state's.

    So this arm is `v5-rules-2` with the D162 work-only charge and NO state-aware decision
    pricing, no touch, no plan_state, no per-type retention, no belief-apply. It exists because
    v5-rules-2 charged every warm build `recall_gpu_s(piece, "COLD")` whatever the session's
    predicted state was, which overcharges a build onto a warm prefix and is what the "warming
    fails dashcam" finding was measured under. Those cells are labelled budget-mispriced.

    IT IS A NEW ARM AND NOT AN ALIAS. `covex-v6-rules` remains byte-identical to `v5-rules-2` by
    decision digest, because a committed cell must keep meaning what it meant. This is the
    repriced sibling, under its own name, so the two are comparable rather than confusable.
    """

    live2_d162_pricing = True
    live2_charge_mode = "work-only"

    def __init__(self, name: str = "covex-v6-rules-wo", *,
                 charge_mode: str = "work-only",
                 over_limit_infeasible: bool = True, **kw: Any) -> None:
        V2.V5Rules2Arm.__init__(self, name=name,
                                over_limit_infeasible=over_limit_infeasible, **kw)
        self.arm_version = "covex-v6-rules-%s-1.0" % ("wo" if charge_mode == "work-only"
                                                      else "uo")
        self.live2_d162_pricing = True
        # D174 (1) SUPERSEDES work-only. This arm keeps its name and its mode together: the
        # module default moved to uncached-only and an arm named -wo must not quietly follow it.
        self.live2_charge_mode = charge_mode
        self.live2_source = (self.live2_source
                             + "; budget charged by live2/d162_price %s (D173 (2), D174 (1))"
                             % self.live2_charge_mode)

    def live2_describe(self) -> Dict[str, Any]:
        d = dict(V2.V5Rules2Arm.live2_describe(self))
        d.update(arm=self.name, arm_version=self.arm_version,
                 rung="covex-v6-rules with corrected budget charging (D173 (2))",
                 budget_charge=("live2/d162_price %s; the queue term is used only in the "
                                "planner's harm (D173 (1)), and under the ruled uncached-only "
                                "mode the intercept is excluded too (D174 (1))"
                                % self.live2_charge_mode),
                 budget_charge_mode=self.live2_charge_mode,
                 state_aware_decision_pricing=False,
                 source=self.live2_source)
        return d


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
    # The ONE PRICE SOURCE charge, explicitly ON. It exists so the D102 proof can exercise the
    # charge it is testing without the rung's default declaring it, and so a ruled rerun has a
    # name to run. It must NOT be put in a cell list until the reprice is ruled.
    "covex-v6-state-d162": lambda **kw: V6StateArm(name="covex-v6-state-d162",
                                                   d162_pricing=True, **kw),
    # D173 (2) rerun arms. DISTINCT NAMES, because the driver never reruns a cell whose name
    # already exists valid, and because the charge must be enabled BY THE ARM: a tag suffix
    # carries no flags.
    # SUPERSEDED BY D174 (1), kept so the two charges stay separable by name rather than by
    # whatever the module default happens to be. Neither -wo arm is posted.
    "covex-v6-state-wo": lambda **kw: V6StateArm(name="covex-v6-state-wo", d162_pricing=True,
                                                 charge_mode="work-only", **kw),
    "covex-v6-rules-wo": lambda **kw: V6RulesWorkOnlyArm(name="covex-v6-rules-wo",
                                                         charge_mode="work-only", **kw),
    # D174 (1) THE RULED RERUN ARM: uncached tokens only, no intercept, no queue term.
    "covex-v6-state-uo": lambda **kw: V6StateArm(name="covex-v6-state-uo", d162_pricing=True,
                                                 charge_mode="uncached-only", **kw),
    # built for symmetry and NOT posted: D174 (1) skips the rung-1 rerun because the budget never
    # bound there (zero refusals in every committed v5-rules-2 cell).
    "covex-v6-rules-uo": lambda **kw: V6RulesWorkOnlyArm(name="covex-v6-rules-uo",
                                                         charge_mode="uncached-only", **kw),
}


def register() -> None:
    import arms as A
    import arms_v5rules2 as R2
    R2.register()
    A.ARMS.update(V6STATE_ARMS)


# ---------------------------------------------------------------------------------------------
# D233: `covex-v6-fair-final-stateoff` ON THE NORMAL IMPORT PATH.
#
# `run_live2_real.py` reaches an arm through `arms.make_arm`, and `arms.py` does
# `ARMS.update(V6STATE_ARMS)` at import, so a key added to this dict exists in the harness's
# process and a posted cell list resolves at launch. A name registered only in the new module's
# own `register()` would NOT, which is the registration gap that made eleven `covex-v6-cf-pd`
# arms invisible and that D208 and D232 (2) each had to fix after the fact.
#
# THE FACTORY IS LAZY. `arms_v6stateoff` imports `arms_final_ladder`, which imports THIS module,
# so a module-level import here would be a circular import and would fail. The import happens
# inside the factory at CALL time. Nothing is imported at registration time, so the cost of this
# key in a tree that never builds it is one dict entry.
#
# NOTHING ABOVE THIS LINE CHANGED. The eleven rung-2 keys, their factories and every byte of
# `V6StateArm` are untouched, so no committed rung-2 digest can move.
def _stateoff_lazy(**kw: Any) -> Any:
    import arms_v6stateoff as SO                                           # noqa: PLC0415
    return SO.make_stateoff(SO.STATEOFF, **kw)


_stateoff_lazy._is_stateoff_factory = True                                 # type: ignore[attr-defined]

if "covex-v6-fair-final-stateoff" in V6STATE_ARMS:                         # pragma: no cover
    raise RuntimeError("covex-v6-fair-final-stateoff is already registered in V6STATE_ARMS")
V6STATE_ARMS["covex-v6-fair-final-stateoff"] = _stateoff_lazy


# ---------------------------------------------------------------------------------------------
# D234 (2): `covex-v6-fair-final-notouch` ON THE NORMAL IMPORT PATH.
#
# The SAME two-file pattern the `-stateoff` append above uses, and for the same reason:
# `run_live2_real.py` reaches an arm through `arms.make_arm`, and `arms.py` does
# `ARMS.update(V6STATE_ARMS)` at import, so a key added to this dict exists in the harness's
# process and a posted cell list resolves at launch. A name registered only in the new module's
# own `register()` would NOT, which is the registration gap that made eleven `covex-v6-cf-pd`
# arms invisible and that D208 and D232 (2) each had to fix after the fact. The two ablations
# live together here, in the file that owns `plan_state` and `touch_requests`.
#
# THE FACTORY IS LAZY. `arms_v6notouch` imports `arms_final_ladder`, which imports THIS module,
# so a module-level import here would be a circular import and would fail. The import happens
# inside the factory at CALL time. Nothing is imported at registration time, so the cost of this
# key in a tree that never builds it is one dict entry.
#
# NOTHING ABOVE THIS LINE CHANGED, INCLUDING THE `-stateoff` APPEND. The eleven rung-2 keys,
# their factories, every byte of `V6StateArm` and `_stateoff_lazy` are untouched, so no committed
# digest can move. This is a NEW module-level function and a NEW module-level statement; no
# pre-existing block is extended.
def _notouch_lazy(**kw: Any) -> Any:
    import arms_v6notouch as NT                                            # noqa: PLC0415
    return NT.make_notouch(NT.NOTOUCH, **kw)


_notouch_lazy._is_notouch_factory = True                                   # type: ignore[attr-defined]

if "covex-v6-fair-final-notouch" in V6STATE_ARMS:                          # pragma: no cover
    raise RuntimeError("covex-v6-fair-final-notouch is already registered in V6STATE_ARMS")
V6STATE_ARMS["covex-v6-fair-final-notouch"] = _notouch_lazy
