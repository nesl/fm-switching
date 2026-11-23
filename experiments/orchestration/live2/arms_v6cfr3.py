#!/usr/bin/env python3
"""RUNG 4 OF THE SPEC v6 LADDER, ON THE RUNG-3 BASE. `covex-v6-cf-c5attr` (D190 (3)).

    rung 2   covex-v6-state-uo-c5attr        the C5 attribution rule
    rung 3   covex-v6-fair-c5attr            + the D178 (2) deficit feed (ordering consumer)
    rung 4   covex-v6-cf-c5attr              + spec v6 section 7's TWO counterfactual decisions:
                                               PROTECT-AND-DEFER (a cold rebuild) and
                                               QUESTION-DEFERRAL (a recall query), D191 item 2

TWO COMPOUNDS, NOT ONE, AND THE SECOND IS WHY THE FIRST ALONE WOULD HAVE BEEN A NULL. Measured
here at 1x on the rung-3 base, protect-and-defer moved ZERO decisions and not one of its decisions
reached the harm computation: every one stopped at "no active alert episode" or "the rebuild fits
without evicting". The user's diagnosis is the one the gate mix supports - large non-urgent
rebuilds rarely occur while histories stay warm - and it is a statement about the TRAFFIC, not
about the policy: the remaining loss, the late alert frames, sits behind recall QUESTION prefills.
So D191 item 2 scopes the counterfactual REQUEST decision into rung 4, `cf_request_defer` is it,
and the two legs are reported SEPARATELY throughout. Protect-and-defer is not loosened, not
re-thresholded and not re-run to make it fire; it is left exactly as it is and reported as
UNEXERCISED at 1x (Rule 2), with its own memory-pressure result at 0.25x kept separate.

THE LADDER IS CUMULATIVE AND THAT IS THE WHOLE POINT OF THIS MODULE. `arms_v6cf.py` already
builds protect-and-defer over a RUNG-2 base, and `covex-v6-cf-pd-c5attr` is that arm; its own
proofs record, in its own words, that `w_source` there is "the CONSTANT 1.0: covex-v6-fair's
deficit weight is NOT wired into this compound, so rung 4 on a rung-3 base is a separate question
and is not what these cells test". This module is that separate question. It is NOT c5attr plus
protect-and-defer; it is rung 3 plus protect-and-defer, and the difference is not cosmetic:

  * the deficit weight becomes LIVE in the inequality that decides. `w_j` (inside the harm sum)
    and `w_R` (on the bar) stop being 1.0 and start being `1 + 2.0 * shortfall`, so an alert type
    behind its target raises harm and defers MORE, and a recall device behind its own target
    raises the bar and defers LESS. On the rung-2 base both are identically 1, the ratio that
    decides is `harm / MARGIN_CF`, and the deficit counters cannot move a single deferral. That
    is the exact shape CLAUDE.md Rule 2 calls `cancelled by geometry`, and running rung 4 on the
    rung-2 base and calling it rung 4 would have left it in place by construction.
  * rung 3's ordering consumer is live underneath, so the pending-work ORDER protect-and-defer
    computes its harm against is rung 3's order and not rung 2's.

WHERE EACH PIECE COMES FROM, AND WHAT THIS FILE ADDS. Nothing here re-implements a mechanism.

    the first compound     `arms_v6cf._ProtectDeferMixin`, unchanged and not copied
    its mechanism          `cf_protect_defer`, unchanged
    the second compound    `cf_request_defer`, which imports `cf_protect_defer`'s harm, bar,
                           kappa and latest-safe-start rather than restating any of them
    the rung-3 base        `arms_v6fairfeed.make_class("covex-v6-state-uo-c5attr")`, unchanged
    ADDED HERE             the w_d WIRING (`w_of = lambda did: feed.weight_device(did)`) and the
                           enactment of the question-deferral leg

`arms_v6cf` declares that injection point and names the adapter in its own docstring
("THE DEFICIT WEIGHT IS INJECTED AND IS NOT BUILT HERE"); `arms_v6fairfeed` publishes
`DeficitFeed.weight_device`. This module connects the two and does nothing else, which is why it
is 200 lines and not 600.

MRO AND WHY IT IS IN THIS ORDER. `(_ProtectDeferMixin, V6FairFeed_covex_v6_state_uo_c5attr)`, so
`_ProtectDeferMixin.decide` runs FIRST, calls `super().decide` into the deficit feed's `decide`,
which calls `super().decide` into the rung-2 base. Both rungs therefore fire on every epoch, and
protect-and-defer sees the action the rung-3 arm actually produced. Reversing the order would
make the compound revise an action rung 3 had not yet ordered.

TWO-PHASE CONSTRUCTION, BECAUSE THE WEIGHT DOES NOT EXIST YET AT `__init__` TIME.
`_ProtectDeferMixin.__init__` captures `w_of` and runs BEFORE `_fairfeed_init` has built
`self._feed`, so a closure over `self._feed` taken at that moment would close over nothing. The
weight is therefore wired AFTER `_fairfeed_init`, and the wiring is then READ BACK and asserted
to be the live accessor rather than the default, so a construction that silently kept the
constant 1.0 raises here instead of producing a plausible null. `W_WIRED_PROOF` on each arm
records the value the accessor returns for a known device at construction time.

THE OFF ARM IS THE RUNG-3 ARM, NOT THE RUNG-2 ARM. `covex-v6-cf-c5attr-off` is this class with
the protect-and-defer switch off, and CLAUDE.md Step 4 requires it to be byte-identical to the
COMMITTED `covex-v6-fair-c5attr`. That is the off-switch identity proof for this rung, and it is
a different bar from `covex-v6-cf-pd-c5attr-off`, whose bar is the rung-2 digest.

WHAT IS ALREADY KNOWN AND IS NOT RE-ASKED HERE. At 1x GPU KV the compound moved ZERO decisions on
the rung-2 base (measured twice, `cf_pd_proofs.json` and `d187_cfpd_c5attr_proofs.json`: the ON
digest is byte-identical to OFF and to the base). That is Rule 2's UNEXERCISED, an ABSENT LINK
and not a negative. Whether the live weight changes that at 1x is the first thing this module's
proofs measure, because it is the one input that is different here; the answer is in
`d190_rung4_r3_proofs.json` and it is reported before any cell is posted.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve().parent
for _p in (str(HERE), str(HERE / "v5"), str(HERE / "fleet"), str(HERE / "hybrid"),
           str(HERE.parent / "baselines")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import arms_v6cf as VCF                                                       # noqa: E402
import arms_v6fairfeed as FF                                                  # noqa: E402
import cf_protect_defer as PD                                                  # noqa: E402
import cf_request_defer as RD                                                  # noqa: E402
import deficit_gain_d178 as GAIND                                              # noqa: E402
from interface import Action, Observation                                      # noqa: E402,F401

sys.path.insert(0, str(HERE / "v5"))
import cf_cost as CC                                                           # noqa: E402

R3_VERSION = "covex-v6-cf-r3-1.0"

# The rung-3 base, by the rung-2 base it is itself built over. ONE entry, not a contingency map:
# rung 2 was SETTLED as the c5attr base (the shares arm failed a D179 (6) check and the override
# is logged), and rung 3 ran to completion on it at seeds 4 to 7. A second speculative key would
# be a name for an arm nobody chose, which `arm_names_v6.py` rule 3 forbids.
RUNG2_BASE = "covex-v6-state-uo-c5attr"
RUNG3_ARM = "covex-v6-fair-c5attr"
BASE_KEY = "fair_c5attr"

# Registered into `arms_v6cf.BASES` rather than duplicated, because `_ProtectDeferMixin
# .live2_describe` reads `BASES[self.pd_base_key]`. ADDITIVE: it adds a third key and changes
# neither of the two that are there, so `covex-v6-cf-pd-shares` and `covex-v6-cf-pd-c5attr` are
# untouched and their digests cannot move.
VCF.BASES.setdefault(BASE_KEY, {
    "module": __name__,
    "cls": "V6CfRung4C5Attr",
    "base_arm": RUNG3_ARM,
    "why": ("rung 3 (the D178 (2) deficit feed over the c5attr rung-2 base), so the deficit "
            "weight is LIVE in both w_j and w_R"),
})


class WeightWiringError(RuntimeError):
    """The deficit weight did not reach the compound as the live accessor."""


class _Rung4Mixin:
    """The QUESTION-DEFERRAL leg plus the w_d wiring. Every other decision rule is inherited.

    `decide` runs AFTER `_ProtectDeferMixin.decide` and therefore after rung 3 and rung 2, which
    is the order the ladder requires: the question-deferral revises the action the rung-3 arm
    actually produced, and it sees any request protect-and-defer has already turned into a DEFER
    (and leaves it alone, because it is no longer a CLOUD admission).
    """

    def _rd_u(self, session_id: str, tokens: int) -> Dict[str, Any]:
        """`u`, THE UNCACHED PREFILL, BY THE D186 / r1 CORRECTION AND NOT BY built_tokens ALONE.

            u = tokens                                    if readiness is COLD
              = max(tokens - max(built, telemetry), 0)     otherwise

        THE SAME THREE LINES THE COORDINATOR'S OWN RECALL RELEASE PATH USES, on the same three
        inputs, now carried on the roster as `uncached_inputs_by_session`. Why it matters here and
        not only there: `built_tokens` ALONE priced recall 15.6x TOO HIGH under shares (predicted
        median u 14,712 at s4 against the engine's own 1,050 on the same opportunity), and 15.6x
        too high is not a harmless conservatism in THIS module - `u` multiplies the queued-ahead
        price, so it OVER-PRICES THE HARM OF SENDING NOW and therefore OVER-DEFERS. That failure
        would look exactly like the mechanism working: more deferrals, each justified by a harm
        that was never there.

        `last_telemetry_cached_tokens` is the engine's own report and is trusted ONLY while the
        session is NOT believed COLD, because it is never reset on eviction (the e9569009 guard).
        MAX of the two, not replacement: both are lower bounds on the true prefix and each exists
        when the other may not.

        BOTH FORMS ARE RETURNED, so the dry report can show the one in force against the one that
        was wrong instead of asserting they agree.
        """
        roster = getattr(self._rules, "_roster", None) or {}
        inp = (roster.get("uncached_inputs_by_session") or {}).get(str(session_id))
        built_map = roster.get("built_tokens_by_session") or {}
        built_only = max(int(tokens) - int(built_map.get(str(session_id), 0) or 0), 0)
        if inp is None:
            # The roster field is absent, so this is an older coordinator. FALL BACK and COUNT it,
            # rather than silently pricing by the quantity the correction exists to replace.
            self.stats["rd_u_no_roster_inputs"] += 1
            return {"u": built_only, "rule": "FALLBACK built_tokens only (roster field absent)",
                    "u_built_only": built_only, "readiness": None,
                    "built_tokens": int(built_map.get(str(session_id), 0) or 0),
                    "telemetry_cached_tokens": None}
        built = int(inp.get("built_tokens", 0) or 0)
        tel = int(inp.get("telemetry_cached_tokens", 0) or 0)
        readiness = str(inp.get("readiness"))
        if readiness == "COLD":
            u = int(tokens)
            rule = "COLD: u = tokens, nothing subtracted (the e9569009 guard)"
            self.stats["rd_u_cold"] += 1
        else:
            u = max(int(tokens) - max(built, tel), 0)
            rule = "NOT COLD: u = tokens - max(built, telemetry)"
            self.stats["rd_u_not_cold"] += 1
            if tel > built:
                self.stats["rd_u_telemetry_won"] += 1
            elif built > tel:
                self.stats["rd_u_built_won"] += 1
        if u != built_only:
            self.stats["rd_u_differs_from_built_only"] += 1
            self.stats["rd_u_built_only_minus_u_sum"] += int(built_only - u)
        return {"u": int(u), "rule": rule, "u_built_only": built_only,
                "readiness": readiness, "built_tokens": built,
                "telemetry_cached_tokens": tel, "prompt_tokens": int(tokens)}

    def _rd_one(self, obs: Observation, *, decider_device_id: str, session_id: str,
                u_request: int, deadline_abs_s: float,
                u_detail: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        cf = self._cf_engine()
        others = self._pd_others(obs, session_id)
        pred = CC.predict(cf.model, int(u_request), 0, 0, 0)
        res = cf.residuals
        n_alert = sum(1 for r in others if r["qtype"] == "alert")
        d = RD.decide(decider_device_id=str(decider_device_id), now_s=float(obs.now_s),
                      alert_active=bool(n_alert > 0), n_alert_pending=n_alert,
                      u_request=int(u_request), others=others,
                      deadline_abs_s=float(deadline_abs_s), pred=pred,
                      p_on_time=(lambda eng, slack: float(CC.p_on_time(res, eng, slack))),
                      w_of=self._pd_w_of, w_source=self._pd_w_source,
                      bar_reading=self._pd_bar_reading,
                      # The SAME two Step 4 controls as the protect-and-defer leg, so one control
                      # arm disables the mechanism on both legs and a control cell is one cell.
                      harm_scale=(0.0 if self._pd_control_harm_zero else 1.0),
                      margin_scale=(self.MARGIN_CONTROL_SCALE
                                    if self._pd_control_margin_huge else 1.0))
        d["session_id"] = str(session_id)
        d["u_detail"] = dict(u_detail or {})
        self._rd_record(d)
        return d

    def _rd_record(self, d: Dict[str, Any]) -> None:
        st = self.stats
        st["rd_decisions"] += 1
        st["rd_gate_" + str(d.get("gate"))] += 1
        if "harm_now" in d:
            st["rd_reached_harm"] += 1
            st["rd_harm_now_micro_sum"] += int(round(float(d["harm_now"]) * 1e6))
            st["rd_harm_saved_micro_sum"] += int(round(float(d.get("harm_saved", 0.0)) * 1e6))
            st["rd_own_loss_micro_sum"] += int(round(float(d.get("own_loss", 0.0)) * 1e6))
            st["rd_net_micro_max"] = max(int(st.get("rd_net_micro_max", -10 ** 12)),
                                         int(round(float(d.get("net_gain", 0.0)) * 1e6)))
            self.rd_nets.append(float(d.get("net_gain", 0.0)))
            self.rd_bars.append(float(d.get("bar_value", 0.0)))
            if float(d.get("w_decider", 1.0)) > 1.0:
                st["rd_decider_weight_above_floor"] += 1
        if len(self.rd_decisions) < 4000:
            self.rd_decisions.append({
                "t": d.get("now_s"), "gate": d.get("gate"), "action": d.get("action"),
                "u": d.get("u_request"), "harm_now": d.get("harm_now"),
                "harm_saved": d.get("harm_saved"), "harm_saved_alert": d.get("harm_saved_alert"),
                "own_loss": d.get("own_loss"), "net": d.get("net_gain"),
                "bar": d.get("bar_value"), "w_decider": d.get("w_decider"),
                "deferral_s": d.get("deferral_s"), "crosses": d.get("crosses_bar"),
                "n_rows_saved": d.get("n_rows_saved"),
                "n_rows_still_harmed": d.get("n_rows_still_harmed"),
                "own_p_before": d.get("own_p_before"), "own_p_after": d.get("own_p_after"),
                "n_alert_pending": d.get("n_alert_pending"),
                "u_detail": d.get("u_detail"),
                "would_miss_under_measured_bias":
                    d.get("would_miss_deadline_under_measured_bias")})
        if self.rd_trace_kept is None and str(d.get("action")) != "BASE":
            self.rd_trace_kept = d
        if self.rd_trace_crossed is None and bool(d.get("crosses_bar")):
            self.rd_trace_crossed = d

    def decide(self, obs: Observation) -> Action:
        act = super().decide(obs)                                          # type: ignore[misc]
        if not RD.arm_enables(self):
            return act
        g = self._rules.guard_state(obs)
        if g["active"]:
            # Spec v6 section 7, "healthy regime only". The same obligation every rung carries.
            self.stats["rd_deferred_to_guard_epochs"] += 1
            return act
        roster = getattr(self._rules, "_roster", None) or {}
        sdev = roster.get("session_device") or {}
        devs = roster.get("devices") or {}
        built = roster.get("built_tokens_by_session") or {}
        for ra in list(act.recall or ()):
            if str(getattr(ra, "decision", "")) != "CLOUD":
                # Already DEFERred (possibly by the protect-and-defer leg this epoch), or not a
                # cloud admission at all. Counted, so the two legs' interaction is visible.
                if str(getattr(ra, "decision", "")) == "DEFER":
                    self.stats["rd_skipped_already_deferred"] += 1
                continue
            qy = next((q for q in (obs.recall or ()) if str(q.query_id) == str(ra.query_id)), None)
            if qy is None:
                continue
            sid = str(qy.session_id)
            did = sdev.get(sid)
            if did is None or str((devs.get(did) or {}).get("type")) != "robot":
                continue
            tok = int(getattr(qy, "readiness_tokens", 0) or 0)
            if tok > VCF.CONTEXT_LIMIT_TOKENS:
                # The base REJECTS it, so it never reaches the engine and deferring it changes
                # nothing. D175 (1): only a DELIVERED cloud answer replaces the device's.
                self.stats["rd_skipped_over_limit"] += 1
                continue
            ud = self._rd_u(sid, tok)
            d = self._rd_one(obs, decider_device_id=str(did), session_id=sid,
                             u_request=int(ud["u"]), deadline_abs_s=float(qy.deadline_s),
                             u_detail=ud)
            if d["action"] != "DEFER_TO_LATEST_SAFE_START":
                continue
            # THE CHANNEL, and it is the one the coordinator reads: `defer_s` at
            # coordinator.py:785 becomes `o.defer_until = t + defer_s`, which withholds the
            # opportunity and OFFERS IT AGAIN. That re-offer is D151 (3)'s re-plan on slip:
            # nothing is stored, so nothing can go stale.
            ra.decision = "DEFER"
            ra.defer_s = float(d["deferral_s"])
            self.stats["rd_question_defers"] += 1
            self.stats["rd_defer_slack_used_ms_sum"] += int(round(float(d["deferral_s"]) * 1000))
            # THE COLUMN D191 SAYS MAY NOT BE OMITTED, in the only form a DRY cell can give it:
            # a deferral whose own post-deferral on-time probability has gone to zero is one this
            # arm has predicted it will make late. The LIVE column is the scorer's, and these two
            # are reported side by side and never substituted for one another.
            if float(d.get("own_p_after", 1.0)) <= 0.0:
                self.stats["rd_defer_own_p_after_zero"] += 1
            # THE COLUMN D191 REQUIRES: how many deferred questions would have missed their own
            # deadline under the MEASURED D162 bias. Counted at the measured WORST bias, which is
            # the bias the safety factor is set to, and separately at the committed kappa this
            # path no longer uses, so the two can be compared rather than argued about.
            m = d.get("would_miss_deadline_under_measured_bias") or {}
            if (m.get("at_measured_worst_bias") or {}).get("would_miss"):
                self.stats["rd_defer_would_miss_at_measured_worst_bias"] += 1
            if (m.get("at_committed_kappa") or {}).get("would_miss"):
                self.stats["rd_defer_would_miss_under_committed_kappa"] += 1
            if not bool(d.get("lss_feasible", True)):
                self.stats["rd_defer_latest_start_infeasible"] += 1
        return act

    def _cf_engine(self) -> Any:
        """RUNG 4'S STATE PLANNER READS THE LIVE DEFICIT FEED (D206 item 1b).

        The base builds the engine with `cf_objective.NoPlannerDeficitFeed`, which is the correct
        DECLARATION for rungs 2 and 3 and is wrong for rung 4: spec v6 section 7 deficit-weights
        the counterfactual's state decisions, and D185 (4) says rung 4 uses the same per-device
        w_d in harm and in `w_d * MARGIN_CF`. The source is swapped HERE, in rung 4's own module,
        the only place that knows both that the feed exists and that this rung may read it.

        THE SWAP IS READ BACK AND ASSERTED, so a construction that silently kept the constant
        RAISES instead of producing a plausible null, which is the shape of the defect this rung
        is being repaired for.
        """
        cf = super()._cf_engine()                                       # type: ignore[misc]
        if not getattr(cf, "_rung4_planner_wired", False):
            src = PlannerDeficitWeights(self)
            cf.counters = src
            cf._rung4_planner_wired = True
            self._planner_w_source = src
            if getattr(cf.counters, "IS_DECLARED_CONSTANT", True):
                raise WeightWiringError(
                    "the rung-4 planner weight source did not take: the engine still holds %r, a "
                    "declared constant, so plan_state would price every device at 1.0"
                    % (type(cf.counters).__name__,))
            if cf.counters._arm._feed is not self._feed:                # pragma: no cover
                raise WeightWiringError(
                    "the rung-4 planner source is not reading THE SAME feed object as the two "
                    "legs, so the limb and the legs could disagree (D206 item 1b)")
        return cf

    def planner_weight_report(self) -> Dict[str, Any]:
        """The planner limb's own source, so a cell can show it is live and not constant."""
        src = getattr(self, "_planner_w_source", None)
        return src.as_dict() if src is not None else {"source": None, "wired": False}

    def rd_report(self) -> Dict[str, Any]:
        """The question-deferral leg's own distributions, so the bar is checkable as a spread."""
        n = sorted(float(x) for x in self.rd_nets)
        b = sorted(float(x) for x in self.rd_bars)

        def q(v: List[float], p: float) -> Optional[float]:
            return v[min(int(p * (len(v) - 1)), len(v) - 1)] if v else None
        return {"switch": {"attr": RD.SWITCH_ATTR, "on": RD.arm_enables(self),
                           "chain": [{"class": type(o).__name__,
                                      "declared_on_instance": RD.SWITCH_ATTR in vars(o),
                                      "value": vars(o).get(RD.SWITCH_ATTR),
                                      "type": type(vars(o).get(RD.SWITCH_ATTR)).__name__}
                                     for o in self._pd_targets()]},
                "net_gain": {"n": len(n), "min": q(n, 0.0), "median": q(n, 0.5),
                             "p90": q(n, 0.9), "max": (n[-1] if n else None),
                             "n_distinct": len(set(round(x, 9) for x in n))},
                # THE BAR AS A DISTRIBUTION, which is the only evidence that the live w_d is
                # doing anything: a bar with ONE distinct value is a bar at the w = 1 floor
                # everywhere, and that is CONSTANT in Rule 2's sense however the arm is wired.
                "bar": {"n": len(b), "min": q(b, 0.0), "median": q(b, 0.5),
                        "max": (b[-1] if b else None),
                        "n_distinct": len(set(round(x, 9) for x in b)),
                        "at_w1": PD.MARGIN_CF_ON_TIME,
                        "n_above_w1_floor": sum(1 for x in b if x > PD.MARGIN_CF_ON_TIME + 1e-12)},
                "traced_decision": RD.trace_lines(self.rd_trace_kept),
                "traced_decision_record": self.rd_trace_kept,
                "traced_bar_crossing": RD.trace_lines(self.rd_trace_crossed),
                "traced_bar_crossing_record": self.rd_trace_crossed}

    def live2_describe(self) -> Dict[str, Any]:
        d = dict(super().live2_describe())                                 # type: ignore[misc]
        d.update(arm=self.name, arm_version=R3_VERSION,
                 covex_v6_rung4=dict(
                     rung=4, cumulative_over=[RUNG2_BASE, RUNG3_ARM],
                     compounds=dict(
                         protect_and_defer=dict(
                             on=PD.arm_enables(self), switch=PD.SWITCH_ATTR,
                             spec="spec v6 section 7, D165 (D)",
                             aims_at="a large non-urgent COLD REBUILD that would evict a warm "
                                     "history before its question"),
                         question_deferral=dict(
                             on=RD.arm_enables(self), switch=RD.SWITCH_ATTR,
                             spec="spec v6 section 7, D151 (3), scoped in by D191 item 2",
                             aims_at="a cloud-admitted recall QUESTION whose prefill delays an "
                                     "active alert episode's first token; no eviction gate")),
                     units=("counts of expected on-time cloud answers, per-device w_d weighted; "
                            "no division by the number served (D191 item 1)"),
                     added_here="the two legs' w_d wiring and the question-deferral decision",
                     w_source=getattr(self, "_pd_w_source", None),
                     planner_limb_w_source=self.planner_weight_report(),
                     w_wired_proof=getattr(self, "W_WIRED_PROOF", None),
                     bar_reading=getattr(self, "_pd_bar_reading", None),
                     bar_at_w1=PD.MARGIN_CF_ON_TIME,
                     bar_source=PD.MARGIN_CF_ON_TIME_SOURCE,
                     margin_path=getattr(PD, "MARGIN_CF_ON_TIME_PATH", None),
                     gain=getattr(self, "_feed_gain", None),
                     gain_declared=GAIND.GAIN))
        return d


class DeficitSourceNeverFed(RuntimeError):
    """A weight source that is SUPPOSED to be fed received nothing for a whole run (D206 item 3)."""


class PlannerDeficitWeights:
    """THE SAME per-device `w_d` the two legs read, adapted to the v5 planner's interface.

    D206 item 1b, and the point is ONE SOURCE AND NOT TWO. The two counterfactual legs already read
    `self._feed.weight_device` through `_weight_of` below; this hands the STATE PLANNER the same
    object, so the limb and the legs cannot disagree about a device's weight at a given instant.
    They are equal BY CONSTRUCTION rather than by agreement, and a proof that compares them is an
    IDENTITY and must say so: n reads of one object, maximum absolute difference exactly 0.

    THE DEVICE RESOLVER IS THE ARM'S OWN, `_fairfeed_resolve_device`, which is what rung 3's
    ordering consumer uses, so the planner weight and the ordering weight cannot disagree about
    WHICH DEVICE a decision is about either. An id that does not resolve takes the floor and is
    COUNTED, because the device set is the roster's and an unresolved id means the resolver failed.

    FAIL-LOUD, AND DELIBERATELY NOT PER READ. D206 item 3 says a source supposed to be fed must
    raise rather than return a neutral value. The condition that let the original defect live is
    "never fed across a whole run", NOT "holds no data at this instant": at the first decision the
    feed legitimately has no observations, which is why `W_WIRED_PROOF` records that 1.0 at
    construction is correct and not a failure. So the raises are at CONSTRUCTION when the feed
    object is absent, and at REPORT TIME when reads happened and the feed received zero
    observations all run. A per-read raise would fire on decision one of a correct run.
    """

    IS_DECLARED_CONSTANT = False

    def __init__(self, arm: Any) -> None:
        if getattr(arm, "_feed", None) is None:
            raise WeightWiringError(
                "PlannerDeficitWeights was built with no live feed on the arm; _fairfeed_init has "
                "not run, so the rung-4 planner limb would have silently priced every device at "
                "1.0 (D206 item 1b)")
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
                "the rung-4 planner deficit source was READ %d times and the feed received ZERO "
                "observations for the whole run, so every weight it returned was the floor. That "
                "is the condition that let the D200 (1) defect survive, and D206 item 3 requires "
                "it to raise rather than report a neutral default." % (self.reads,))
        return {"source": ("live2/deficit_feed.DeficitFeed.weight_device, THE SAME FEED OBJECT "
                           "the two counterfactual legs read (D206 item 1b)"),
                "is_declared_constant": False,
                "gain": float(getattr(self._arm, "_feed_gain", float("nan"))),
                "reads": self.reads, "unresolved": self.unresolved,
                "reads_above_the_w1_floor": self.reads_above_floor,
                "feed_observations": n_obs,
                "identity_note": ("the legs and this limb read ONE object, so an equality proof "
                                  "between them is an IDENTITY with maximum absolute difference "
                                  "exactly 0, not a measurement of agreement")}


def _weight_of(arm: Any, device_id: str) -> float:
    """`w_d` for one device, READ OFF THE LIVE FEED at the moment the decision is made.

    FLOORED AT 1.0 HERE AS WELL AS IN THE FEED, deliberately and not defensively: the bar is
    `w_R * MARGIN_CF` and a weight below 1 would LOWER the bar below the committed margin, which
    is a change to MARGIN_CF by another route. D178 (2) floors the weight at 1; this re-states
    that floor at the point of use so no path can quietly go under it.

    An unknown device returns the floor, counted. The alternative is a guess, and the device set
    is the roster's, so an unknown id means the resolver failed and that must be visible.
    """
    feed = getattr(arm, "_feed", None)
    if feed is None:                                                       # pragma: no cover
        raise WeightWiringError("the deficit feed is not built; _fairfeed_init has not run")
    try:
        w = float(feed.weight_device(str(device_id)))
    except Exception:                                                      # noqa: BLE001
        arm.stats["pd_w_device_unresolved"] += 1
        return 1.0
    if not (w == w) or w < 1.0:
        arm.stats["pd_w_below_floor_clamped"] += 1
        return 1.0
    return w


W_SOURCE_LIVE = ("covex-v6-fair's deficit weight, LIVE: deficit_feed.DeficitFeed.weight_device, "
                 "w = 1 + %g * shortfall floored at 1 (D178 (2)), read per decision off the "
                 "rung-3 feed this arm IS" % (GAIND.GAIN,))
W_SOURCE_CONST1 = ("the CONSTANT 1.0, on a rung-3 base: the ABLATION that isolates the weight "
                   "from the ordering consumer, so a difference against the live-weight arm is "
                   "the weight's and nothing else's")


def make(name: str, *, protect_defer: bool = True, request_defer: bool = True,
         live_weight: bool = True,
         deficit_feed: bool = True, gain: float = GAIND.GAIN,
         ordering: bool = True, split: bool = True,
         control_harm_zero: bool = False, control_margin_huge: bool = False,
         **kw: Any) -> Any:
    """Build one rung-4 arm. The three phases are here and not in the caller."""
    arm = V6CfRung4C5Attr(name=name, protect_defer=protect_defer,
                          control_harm_zero=control_harm_zero,
                          control_margin_huge=control_margin_huge, **kw)
    arm._fairfeed_init(deficit_feed=deficit_feed, gain=gain, ordering=ordering, split=split)
    # ---- the question-deferral leg's own state and its own arm-scoped switch ---------------
    # On EVERY object the decide path can bind `self` to, exactly as the other two switches are
    # set, and read back through the strict reader so a construction that did not take raises.
    arm.rd_decisions: List[Dict[str, Any]] = []
    arm.rd_nets: List[float] = []
    arm.rd_bars: List[float] = []
    arm.rd_trace_kept = None
    arm.rd_trace_crossed = None
    for obj in arm._pd_targets():
        object.__setattr__(obj, RD.SWITCH_ATTR, bool(request_defer))
    if RD.arm_enables(arm) != bool(request_defer):                         # pragma: no cover
        raise RD.RequestDeferSwitchError(
            "%s did not take on the instance of %s" % (RD.SWITCH_ATTR, type(arm).__name__))
    # ---- phase two: the ONE thing this module adds ----------------------------------------
    if live_weight:
        arm._pd_w_of = lambda did, _a=arm: _weight_of(_a, did)
        arm._pd_w_source = W_SOURCE_LIVE
    else:
        arm._pd_w_of = PD.default_w_of
        arm._pd_w_source = W_SOURCE_CONST1
    # ---- and the read-back, so a wiring that did not take RAISES rather than nulls ---------
    probe = "robo000"
    got = float(arm._pd_w_of(probe))
    arm.W_WIRED_PROOF = {
        "accessor": getattr(arm._pd_w_of, "__qualname__", repr(arm._pd_w_of)),
        "live_weight": bool(live_weight),
        "probe_device": probe,
        "probe_value_at_construction": got,
        "bar_at_probe": got * PD.MARGIN_CF_ON_TIME,
        "feed_present": hasattr(arm, "_feed"),
        "feed_gain": float(getattr(arm, "_feed_gain", float("nan"))),
        "note": ("1.0 at construction is CORRECT and is not a failure: no opportunity has been "
                 "offered yet, so every shortfall is 0 and every weight is at the D178 (2) "
                 "floor. What must be true at construction is that the ACCESSOR is the live one; "
                 "that the VALUE moves is a run-time property and is measured by "
                 "pd_bar_distinct_values and the bar distribution in the proofs."),
    }
    if live_weight and not hasattr(arm, "_feed"):                          # pragma: no cover
        raise WeightWiringError("live_weight was asked for and no feed is present")
    if live_weight and arm._pd_w_source != W_SOURCE_LIVE:                  # pragma: no cover
        raise WeightWiringError("the w_source did not take: %r" % (arm._pd_w_source,))
    return arm


def _build_class() -> Any:
    rung3 = FF.make_class(RUNG2_BASE)
    return type("V6CfRung4C5Attr",
                (_Rung4Mixin, VCF._ProtectDeferMixin, rung3),
                {"_pd_base_key": BASE_KEY,
                 "__doc__": "rung 4: protect-and-defer over %s" % (RUNG3_ARM,)})


V6CfRung4C5Attr = _build_class()

_N = "covex-v6-cf-c5attr"
V6CFR3_ARMS: Dict[str, Any] = {
    # THE ARM. FULL RUNG 4: rung 3 + BOTH counterfactual compounds (D191 item 2).
    _N: (lambda **kw: make(_N, **kw)),
    # CLAUDE.md Step 4, part one, and the off-switch identity bar: BOTH compounds off must
    # collapse to the COMMITTED RUNG-3 ARM byte-identically. Not to rung 2 - that is the other
    # family's bar, and confusing the two is how a rung gets credited with the rung below it.
    _N + "-off": (lambda **kw: make(_N + "-off", protect_defer=False, request_defer=False, **kw)),
    # THE TWO ONE-FACTOR ARMS. Addendum 12 item 5: "a combined count that cannot be attributed is
    # not a pass", so each compound must be runnable ALONE. `-pdonly` is also the exact treatment
    # of D191 step (a), the protect-and-defer Step 2b on the rung-3 base.
    _N + "-pdonly": (lambda **kw: make(_N + "-pdonly", request_defer=False, **kw)),
    _N + "-rqonly": (lambda **kw: make(_N + "-rqonly", protect_defer=False, **kw)),
    # THE WEIGHT ABLATION. Both compounds ON over the rung-3 base with w_d pinned at 1.0. It is
    # the only arm that separates "rung 3 is underneath" from "the live weight is in the
    # inequality", and without it a difference against the rung-2 family attributes to neither.
    _N + "-w1": (lambda **kw: make(_N + "-w1", live_weight=False, **kw)),
    # CLAUDE.md Step 4, the two mechanism controls, as NAMED ARMS so each control is a cell and
    # not a code edit. harm0 zeroes the harm at its source on BOTH legs; margin-huge scales THE
    # BAR AND ONLY THE BAR. Each must collapse to the -off digest.
    _N + "-harm0": (lambda **kw: make(_N + "-harm0", control_harm_zero=True, **kw)),
    _N + "-margin-huge": (lambda **kw: make(_N + "-margin-huge",
                                            control_margin_huge=True, **kw)),
    # The gain-0 control of the rung underneath, WITH both compounds on: every weight is exactly
    # 1.0 while every feed hook and counter stays live, so it must reproduce the -w1 arm. It is
    # the stronger of the two weight controls, for the reason arms_v6fairfeed records.
    _N + "-gain0": (lambda **kw: make(_N + "-gain0", gain=GAIND.NEGATIVE_CONTROL_GAIN, **kw)),
}


def register() -> List[str]:
    """Additive registration into the shared `arms.ARMS`, the pattern every v6 family uses."""
    import arms as A
    A.ARMS.update(V6CFR3_ARMS)
    return sorted(V6CFR3_ARMS)


ARMS = V6CFR3_ARMS
