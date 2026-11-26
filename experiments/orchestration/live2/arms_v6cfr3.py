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
import d222_measured_safety as MS2                                             # noqa: E402
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

    # ITEM 5: ONE declaration of the cap, read by `_rd_record` below and by
    # `coordinator.write_rd_decisions`, so the committed log can say whether it is truncated
    # without either side holding its own copy of the number.
    RD_DECISIONS_CAP = 4000

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
        # ---- D222 (1) ITEM 1: THE REAL QUEUED-AHEAD WORK, AND THE MODEL THAT PRICES IT ---------
        #
        # This line read `CC.predict(cf.model, int(u_request), 0, 0, 0)`. Two things were wrong
        # with it and they compounded:
        #
        #   1. THE QUEUE TERM WAS A LITERAL ZERO on a gate that is only reached when other
        #      requests ARE pending, so the deferral planned its restart as if the engine were
        #      empty. On the traced s5 loss `opp0001513` the arm predicted 0.4156 s of engine
        #      service against an observed 0.818 s first token.
        #   2. `cf.model` IS THE OLD `cost_model_gate.json` by-arm split, whose GATE_STATUS says it
        #      FAILS and whose queue feature is a COUNT OF OVERLAPPING REQUESTS at 0.0380 s each.
        #      D162 replaced that count with WORK at 0.0001535807289338535 s per uncached token -
        #      a 247.46x difference in units - and D162 is the model that PASSED its gate (D168).
        #      Passing the real token count into the old model's argument would have predicted
        #      165.6 s on that same unit and collapsed every deferral to "must start now".
        #
        # So this path now prices with `predict_d162`, whose argument NAMES carry their units, on
        # the rows the arm already enumerates for the harm sum. No new observation is read: the
        # uncached tokens are each row's own `u_tokens`, published by `_pd_others` from the very
        # quantity that row's `engine_s` was predicted from, and the decode tokens are the measured
        # per-type output counts in `d222_measured_safety` (every request on this workload emits
        # exactly 2, chased to its source). The third positional argument of the old call was
        # `cached_tokens` and was CORRECT at zero, because `u_request` is already an uncached
        # count; `predict_d162` keeps that default and the docstring says why it must stay there.
        qa_tokens = sum(max(int(r.get("u_tokens", 0) or 0), 0) for r in others)
        qd_tokens = sum(MS2.DECODE_TOKENS_BY_QTYPE.get(str(r.get("qtype")),
                                                       MS2.DECODE_TOKENS_DEFAULT)
                        for r in others)
        pred = CC.predict_d162(cf.model_d162, int(u_request), 0, qa_tokens, qd_tokens)
        # THE PROOF THAT THE QUANTITY REACHING `predict` IS THE INTENDED ONE, on every decision and
        # not in a one-off check: the arguments as passed, the rows they were summed from, and the
        # coefficient each was multiplied by. A reader can re-add the per-row numbers by hand and
        # can see that a TOKEN count met a PER-TOKEN coefficient.
        queue_proof = {
            "overlap_ft_tokens_passed": int(qa_tokens),
            "overlap_decode_tokens_passed": int(qd_tokens),
            "n_rows_summed": len(others),
            "per_row": [{"req_id": str(r.get("req_id")), "qtype": str(r.get("qtype")),
                         "u_tokens": int(r.get("u_tokens", 0) or 0),
                         "decode_tokens": MS2.DECODE_TOKENS_BY_QTYPE.get(
                             str(r.get("qtype")), MS2.DECODE_TOKENS_DEFAULT)}
                        for r in others[:12]],
            "units": "UNCACHED PROMPT TOKENS queued ahead, and OUTPUT TOKENS queued ahead",
            "coefficients": {
                "per_uncached_token_s": float(cf.model_d162["first_token"]["per_uncached_token"]),
                "per_queue_token_s": float(cf.model_d162["first_token"]["per_queue_token"]),
                "per_queue_decode_token_s": float(
                    cf.model_d162["decode"]["per_queue_decode_token"])},
            "model_source": cf.model_d162.get("_source"),
            "model_verdict": cf.model_d162.get("_verdict"),
            "superseded_model": {
                "source": "cost_model_gate.json by_arm, which cf.model still is for every other "
                          "caller",
                "per_overlap_s_per_REQUEST": 0.038004811772727576,
                "ratio_to_per_queue_token": 247.4582067460825,
                "gate_status": "FAILS (spec v5 section 12)"},
            "predicted": {"first_token_s": round(pred.first_token_s, 6),
                          "decode_s": round(pred.decode_s, 6),
                          "engine_s": round(pred.engine_s, 6),
                          "total_s": round(pred.total_s, 6),
                          "at_queue_zero_engine_s": round(
                              CC.predict_d162(cf.model_d162, int(u_request), 0, 0, 0).engine_s, 6)},
        }
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
        d["queue_proof"] = queue_proof
        # ---- D222 (1) ITEM 5b: FILL `decision.predicted.*`, WHICH IS NULL ON EVERY RUNG-4 ROW --
        #
        # `coordinator.py:858` reads `self.arm.last_predictions` ONCE per epoch and threads it into
        # `_log_decision`, which at `:2131` does `(preds.get("by_target") or {}).get(key)`. For a
        # recall release the key is `"rc:" + session_id` (`coordinator.py:1474`). NOTHING in the
        # covex family published `by_target` - only `arms_policy.py:984` does - so the block was
        # the schema default on all 15,505 rows of the committed s4 cell and all 11,641 of s5, and
        # the s5 diagnosis had to RECONSTRUCT the arm's own prediction from the committed formula.
        # It is published here, where the prediction is actually made, so the recorded number is
        # the one that decided and not a re-derivation of it.
        #
        # COVERAGE IS PARTIAL BY CONSTRUCTION AND IS COUNTED RATHER THAN HIDDEN: this leg evaluates
        # robot, cloud-admitted, under-limit recall questions only, so a release the leg never
        # looked at still logs the default. `rd_predictions_published` is the numerator a cell can
        # read against its own `release_recall` count.
        lp = getattr(self, "last_predictions", None)
        if not isinstance(lp, dict):
            lp = {}
        bt = lp.get("by_target")
        if not isinstance(bt, dict):
            bt = {}
        bt["rc:" + str(session_id)] = {
            "ttft_s": round(float(pred.first_token_s), 6),
            "completion_s": round(float(pred.engine_s), 6),
            "imposed_delay_s_by_request": {},
        }
        lp["by_target"] = bt
        lp["cost_model_id"] = str(cf.model_d162.get("_source"))
        self.last_predictions = lp
        self.stats["rd_predictions_published"] += 1
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
        if len(self.rd_decisions) < self.RD_DECISIONS_CAP:
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
                    d.get("would_miss_deadline_under_measured_bias"),
                # D222 (1) item 5 names "the chosen candidate and its kind". The candidate is the
                # ACTION and the kind is the leg that produced it, so both travel and a reader
                # never has to infer which leg a row came from.
                "chosen_candidate": d.get("action"),
                "candidate_kind": "question_deferral",
                "session_id": d.get("session_id"),
                "decider_device_id": d.get("decider_device_id"),
                "deferral_s_before_epoch_debit": d.get("deferral_s_before_epoch_debit"),
                "epoch_debit_s": d.get("epoch_debit_s"),
                "queue_proof": d.get("queue_proof")})
        if self.rd_trace_kept is None and str(d.get("action")) != "BASE":
            self.rd_trace_kept = d
        if self.rd_trace_crossed is None and bool(d.get("crosses_bar")):
            self.rd_trace_crossed = d

    def decide(self, obs: Observation) -> Action:
        act = super().decide(obs)                                          # type: ignore[misc]
        # ITEM 5: the prediction channel is PER EPOCH. Cleared here, filled by `_rd_one` below for
        # every candidate it prices, and read by the coordinator later in this same epoch. A
        # channel that accumulated would attach an old epoch's prediction to a new release.
        self.last_predictions = {"by_target": {}}
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
            if tok > VCF.CL.limit_tokens():                    # D223 (2): the run's limit, read here
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
        if getattr(cf, "model_d162", None) is None:
            # D222 (1) item 1: the D162 model is attached HERE, in rung 4's own module, because
            # rung 4's question-deferral is its only reader. `cf.model` is left exactly as it is -
            # `cf_planner`'s plan_queue/plan_state/plan_sync and `cf_protect_defer` price with it
            # and their arms have committed cells - so the tree holds two models on purpose and
            # each caller says which it reads. The two cannot be confused by accident: their key
            # names differ, so handing one to the other's predictor is a KeyError.
            cf.model_d162 = CC.load_d162_model()
            if "per_queue_token" not in cf.model_d162["first_token"]:        # pragma: no cover
                raise WeightWiringError(
                    "the D162 model did not take: first_token carries %r and not per_queue_token, "
                    "so the queued-ahead term would be priced in the wrong units"
                    % (sorted(cf.model_d162["first_token"]),))
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


# D208: the planner adapter MOVED to `planner_deficit_weights.py`, which rung 3 of the final
# ladder also reads. ONE COPY: rung 3 importing rung 4's module would invert the ladder's layering,
# and two copies of a weight adapter is how the limb and the legs stop agreeing. Re-exported here
# under its original names so every committed caller and proof keeps working unchanged.
import planner_deficit_weights as _PDW                                         # noqa: E402

DeficitSourceNeverFed = _PDW.DeficitSourceNeverFed
PlannerDeficitWeights = _PDW.PlannerDeficitWeights


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


# ---------------------------------------------------------------------------------------------
# D208: THE FINAL LADDER'S NAMES, ON THE NORMAL IMPORT PATH.
#
# THE PROBLEM THIS SOLVES, and it is a hard one rather than a tidiness point. `arms.py` imports
# every v6 family EXCEPT `arms_final_ladder`, and `arms_final_ladder.register()` has no production
# caller: its only callers are per-study wrappers that each call it themselves because nothing else
# does. So `arms.make_arm("covex-v6-fair-final")` RAISES "unknown arm" on the normal path, and
# `run_live2_real.py:264` reaches the arm through exactly that call. A POSTED cell list would
# therefore have died at launch on the H100, which is the same registration gap that made all
# eleven `covex-v6-cf-pd` arms invisible to the harness.
#
# WHY THE FACTORIES ARE LAZY, which is the whole trick. `arms_final_ladder` imports THIS module
# (`arms_v6cfr3 as R4`), so a module-level `import arms_final_ladder` here would be a CIRCULAR
# import and would fail. The import therefore happens INSIDE each factory, at CALL time, when this
# module is already fully initialised. Nothing is imported at registration time, so the cost of
# adding these three keys to a tree that never builds them is three dict entries.
#
# WHY HERE AND NOT IN `arms.py`: `arms.py` belongs to another session. This module is rung 4's own,
# it is already imported by `arms.py` (`from arms_v6cfr3 import V6CFR3_ARMS`), and the final ladder
# is built on rung 4's machinery, so the names arrive on the normal path without reaching into a
# file this session does not own.
#
# THE GUARD IS NOT BYPASSED. `arms_final_ladder.make_rung*` are the same constructors
# `arms_final_ladder.register()` registers, and each reads its switches back and raises if one did
# not take. The protected-name check still holds by construction: the three keys below are the only
# ones added, and none of them is a committed arm name.


def _final_ladder_lazy() -> Dict[str, Any]:
    """The three final-rung factories, each importing `arms_final_ladder` at CALL time."""
    def r2(**kw: Any) -> Any:
        import arms_final_ladder as FL                                     # noqa: PLC0415
        return FL.make_rung2(FL.RUNG2, **kw)

    def r3(**kw: Any) -> Any:
        import arms_final_ladder as FL                                     # noqa: PLC0415
        return FL.make_rung3(FL.RUNG3, **kw)

    def r4(**kw: Any) -> Any:
        import arms_final_ladder as FL                                     # noqa: PLC0415
        return FL.make_rung4(FL.RUNG4, **kw)
    def r3ptg(**kw: Any) -> Any:
        import arms_final_ladder as FL                                     # noqa: PLC0415
        return FL.make_rung3(FL.RUNG3_PTG, per_type_guard=True, **kw)

    def r3ptg_ctl20(**kw: Any) -> Any:
        import arms_final_ladder as FL                                     # noqa: PLC0415
        return FL.make_rung3(FL.RUNG3_PTG + "-ctl20", per_type_guard=True, hysteresis=False,
                             guard_lag_s_by_class={"episodic": 2.0, "recall": 2.0,
                                                   "assistance": 2.0}, **kw)

    def r3ptg_nohyst(**kw: Any) -> Any:
        import arms_final_ladder as FL                                     # noqa: PLC0415
        return FL.make_rung3(FL.RUNG3_PTG + "-nohyst", per_type_guard=True,
                             hysteresis=False, **kw)

    def r3ptg_hystonly(**kw: Any) -> Any:
        import arms_final_ladder as FL                                     # noqa: PLC0415
        return FL.make_rung3(FL.RUNG3_PTG + "-hystonly", per_type_guard=True,
                             hysteresis=True,
                             guard_lag_s_by_class={"episodic": 2.0, "recall": 2.0,
                                                   "assistance": 2.0}, **kw)

    def r3ptg_nolog(**kw: Any) -> Any:
        import arms_final_ladder as FL                                     # noqa: PLC0415
        return FL.make_rung3(FL.RUNG3_PTG + "-nolog", per_type_guard=True,
                             guard_log=False, **kw)

    def r3d249(**kw: Any) -> Any:
        import arms_final_ladder as FL                                     # noqa: PLC0415
        return FL.make_rung3(FL.RUNG3_D249, d249_queue_visibility=True, **kw)

    def r3q2(**kw: Any) -> Any:
        import arms_final_ladder as FL                                     # noqa: PLC0415
        return FL.make_rung3(FL.RUNG3_Q2, d249_queue_visibility=True,
                             q2_inflight_exclusion=True, **kw)

    def r3q2m(**kw: Any) -> Any:
        import arms_final_ladder as FL                                     # noqa: PLC0415
        return FL.make_rung3(FL.RUNG3_Q2M, d249_queue_visibility=True,
                             q2_inflight_exclusion=True, q2m_margin=True, **kw)

    def r3q4(**kw: Any) -> Any:
        import arms_final_ladder as FL                                     # noqa: PLC0415
        return FL.make_rung3(FL.RUNG3_Q4, d249_queue_visibility=True,
                             q2_inflight_exclusion=True, q2m_margin=True, q4_credit=True, **kw)

    def r3q4b(**kw: Any) -> Any:
        import arms_final_ladder as FL                                     # noqa: PLC0415
        return FL.make_rung3(FL.RUNG3_Q4B, d249_queue_visibility=True,
                             q2_inflight_exclusion=True, q2m_margin=True, q4_credit=True,
                             q4b_basis=True, **kw)

    def r3q5(**kw: Any) -> Any:
        import arms_final_ladder as FL                                     # noqa: PLC0415
        return FL.make_rung3(FL.RUNG3_Q5, q5_holdback=True, **kw)

    def r3q5b(**kw: Any) -> Any:
        import arms_final_ladder as FL                                     # noqa: PLC0415
        return FL.make_rung3(FL.RUNG3_Q5B, q5_holdback=True, q5b_piece=True, **kw)

    def r3q5c(**kw: Any) -> Any:
        import arms_final_ladder as FL                                     # noqa: PLC0415
        return FL.make_rung3(FL.RUNG3_Q5C, q5_holdback=True, q5b_piece=True, cold_unlatch=True, **kw)

    def r3unlatch(**kw: Any) -> Any:
        import arms_final_ladder as FL                                     # noqa: PLC0415
        return FL.make_rung3(FL.RUNG3_UNLATCH, cold_unlatch=True, **kw)

    def r3link(**kw: Any) -> Any:
        import arms_final_ladder as FL                                     # noqa: PLC0415
        return FL.make_rung3(FL.RUNG3_LINK, d249_queue_visibility=True, link_read=True, **kw)

    def r3sync(**kw: Any) -> Any:
        import arms_final_ladder as FL                                     # noqa: PLC0415
        return FL.make_rung3(FL.RUNG3_SYNC, d249_queue_visibility=True, link_sync="ours",
                             link_currency="acc", **kw)

    def r3syncd177(**kw: Any) -> Any:
        import arms_final_ladder as FL                                     # noqa: PLC0415
        return FL.make_rung3(FL.RUNG3_SYNC_D177, d249_queue_visibility=True, link_sync="ours",
                             link_currency="d177", **kw)

    def r3syncfree(**kw: Any) -> Any:
        import arms_final_ladder as FL                                     # noqa: PLC0415
        return FL.make_rung3(FL.RUNG3_SYNC_FREE, d249_queue_visibility=True, link_sync="ours",
                             link_currency="d177", link_tiebreak="free", **kw)

    def r3syncctl(**kw: Any) -> Any:
        import arms_final_ladder as FL                                     # noqa: PLC0415
        return FL.make_rung3(FL.RUNG3_SYNC_CTL, d249_queue_visibility=True, link_sync="fifo",
                             link_currency="acc", gain=0.0, **kw)

    def r3glog(**kw: Any) -> Any:
        import arms_final_ladder as FL                                     # noqa: PLC0415
        return FL.make_rung3(FL.RUNG3 + "-glog", guard_log=True, **kw)

    # D230 (2): the per-type-guard variant and its three controls reach the harness on the
    # SAME lazy path as the three rungs, for the same reason the block below gives: a POSTED
    # cell naming an arm that `arms.make_arm` cannot resolve dies at launch on the H100.
    return {"covex-v6-state-final": r2, "covex-v6-fair-final": r3, "covex-v6-final": r4,
            "covex-v6-fair-final-ptg": r3ptg,
            # D249 (2026-11-25, PROVISIONAL), on the SAME lazy path and for the same reason: a
            # POSTED cell naming an arm `arms.make_arm` cannot resolve dies at launch.
            "covex-v6-fair-final-q": r3d249,
            "covex-v6-fair-final-q2": r3q2,
            "covex-v6-fair-final-q2m": r3q2m,
            "covex-v6-fair-final-q4": r3q4,
            "covex-v6-fair-final-q5": r3q5,
            "covex-v6-fair-final-q5b": r3q5b,
            "covex-v6-fair-final-q5c": r3q5c,
            "covex-v6-fair-final-unlatch": r3unlatch,
            "covex-v6-fair-final-q4b": r3q4b,
            "covex-v6-fair-final-q-link": r3link,
            "covex-v6-fair-final-q-sync": r3sync,
            "covex-v6-fair-final-q-sync-free": r3syncfree,
            "covex-v6-fair-final-q-sync-d177": r3syncd177,
            "covex-v6-fair-final-q-sync-ctl": r3syncctl,
            "covex-v6-fair-final-ptg-ctl20": r3ptg_ctl20,
            "covex-v6-fair-final-ptg-nohyst": r3ptg_nohyst,
            "covex-v6-fair-final-ptg-hystonly": r3ptg_hystonly,
            "covex-v6-fair-final-ptg-nolog": r3ptg_nolog,
            "covex-v6-fair-final-glog": r3glog}


for _k, _v in _final_ladder_lazy().items():
    if _k in V6CFR3_ARMS:                                                  # pragma: no cover
        raise RuntimeError("the final ladder would shadow a rung-4 name: %r" % (_k,))
    V6CFR3_ARMS[_k] = _v

ARMS = V6CFR3_ARMS
