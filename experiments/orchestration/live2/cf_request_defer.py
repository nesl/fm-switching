#!/usr/bin/env python3
"""DEFER THE QUESTION, the counterfactual REQUEST decision of spec v6 section 7 / D151 (3).

    "defer a recall QUESTION to its latest safe start, when an alert episode is active and the
     deferral's predicted harm saving exceeds the margin"                    (D191 item 2)

WHY THIS EXISTS AND WHY PROTECT-AND-DEFER WAS NOT ENOUGH. `cf_protect_defer` aims at a COLD
REBUILD: its gate 3 requires that the allocation not fit the free KV pool and that there be a warm
victim with a question inside the state horizon. Measured at 1x on the rung-3 base, every decision
stopped at gate 2 or gate 3 and NOT ONE reached the harm computation, because large non-urgent
rebuilds rarely occur while histories stay warm. The remaining loss - the late alert frames - sits
behind recall QUESTION prefills, which are neither rebuilds nor evictions: a 6,000-token recall
prompt delays an alert instant's first token by exactly the same D162 queued-ahead term whether or
not anything is evicted. So the eviction gate is not a safety check here, it is the wrong question,
and this module asks the right one. THAT IS A SCOPE RULING (D191 item 2), NOT A TUNING: nothing in
`cf_protect_defer` is loosened, re-thresholded or re-run; a second, differently-gated decision is
added beside it and both are reported separately.

THE INEQUALITY, IN D191 ITEM 1'S RULED UNITS. Gain and harm are both COUNTS of expected on-time
cloud answers, each device weighted by its own `w_d`. THERE IS NO DIVISION BY THE NUMBER SERVED:
the target normalisation already lives inside `w_d`. One comparison decides.

    defer iff   ( HARM SAVED for others  -  OWN LOSS )  >   w_R * MARGIN_CF

  HARM SAVED   The prefill of `u` uncached tokens, sent NOW, adds `PER_QUEUE_S * u` seconds to
               every pending deadline request's first token (the D162 term, imported from
               `d162_price` and never retyped) and destroys `sum_j w_j * (p_j before - p_j after)`
               on-time cloud answers. Sent at the latest safe start instead, it can no longer
               reach the requests whose own deadline has already passed by then. The saving is
               therefore the harm of exactly those rows, PER ROW and not in aggregate: a row with
               `slack_s <= deferral_s` is saved, a row still ahead of the deferred prefill is not,
               and `n_rows_saved` against `n_rows_still_harmed` is recorded on every decision. An
               aggregate "all the harm goes away" would be the optimistic lie that makes a
               deferral look free.

  OWN LOSS     THE COLUMN THAT CAN TURN A PASS INTO A SELF-INFLICTED LOSS, so it is inside the
               inequality and not a footnote. Deferring to `deadline - kappa * service` leaves
               `kappa * service` of slack instead of the slack it has now, so the decider's own
               on-time probability FALLS, by `w_R * (p(engine, slack_now) - p(engine,
               kappa*service))`, on the same committed on-time curve as every harm row. It is
               charged against the saving before the bar is consulted, and `own_p_before`,
               `own_p_after` and `own_loss` travel on every decision so a reader can see what the
               deferral cost the device that did it.

  w_R          the DECIDER's deficit weight, on the BAR. `w_j` is the HARMED device's weight and
               it sits inside the saving sum, one weight per row. Putting the harmed type's weight
               on the bar is the sign error `cf_protect_defer` documents at length: harm and bar
               would scale together, the ratio that decides would not move, and the deficit weight
               would be INERT - Rule 2's `cancelled by geometry`, a believable null rather than a
               crash. The reading is `cf_protect_defer.bar`, imported, so there is ONE bar in the
               tree and not two.

NOTHING HERE IS NEW ARITHMETIC. `harm_on_time`, `bar`, `KAPPA`, `latest_safe_start`,
`MARGIN_CF_ON_TIME` and the per-queue price are all `cf_protect_defer`'s and are imported. What is
new is the GATE SET and the saving/own-loss decomposition. If a number in this module disagrees
with one in `cf_protect_defer`, that is a bug in this module and not a second opinion.

RE-PLAN ON SLIP IS THE CHANNEL AND NOT AN EXTRA MECHANISM. The deferral is enacted as
`decision = "DEFER"` with `defer_s`, which `coordinator.py:785` reads as `o.defer_until = t +
defer_s`; the opportunity is WITHHELD until then and then OFFERED AGAIN, so it is decided afresh
against the state that actually obtains. That re-offer IS the re-plan, and it is why this module
never stores a plan: there is nothing to invalidate.

THE RESIDENCY INPUT THE PREDICTION CONSUMES, STATED BECAUSE IT HAS JUST BEEN MEASURED TO MATTER.
The latest safe start is `deadline - kappa * predicted service`, so what feeds "predicted service"
decides whether a deferral is safe or is a self-inflicted loss. This module's caller predicts from
`u_request`, which is `readiness_tokens - built_tokens_by_session[session]`: a RESIDENT-TOKEN
COUNT, not a tier label. Every harm row does the same. That is deliberate and it is the input
D190 (5) track C found the hybrid gate does NOT use:

  * `hybrid_arm.py:401`, branching at `:421-426`, prices on the three-label
    `residency_readiness()` from `cstate.py:138`, so GPU-WARM at 44 percent resident and GPU-WARM
    at 28 percent resident price IDENTICALLY. On one partially-resident history that label
    collapse made the estimator predict 0.6506 s against an OBSERVED 5.3166 s - 8.17x optimistic -
    because the label said GPU-WARM while 71.3 percent of a 20,356-token prompt was uncached.
  * The quantity that fixes it already exists and does not reach that gate
    (`hybrid_arm.py:526-534`, `_unbuilt_rebuild_s`, feeding only the C2 risk flag at `:404-409`).
    That is a read-that-never-reaches-a-decision, CLAUDE.md Step 2's concern.

So this module does not inherit the label collapse: at 71.3 percent uncached it would predict on
about 14,500 uncached tokens, not on a label. WHAT IT DOES INHERIT, and no safety factor is
invented to cover it: `built_tokens_by_session` is the COORDINATOR'S BELIEF, not engine telemetry
(D44, D47 - residency cannot be commanded), so an overstated belief understates `u` and the latest
safe start is computed too late by exactly that much. And on the five recall questions actually
SENT in the committed rung-3 cells, D162 UNDER-PREDICTS first token by 1.39x to 1.87x. The
committed kappa is 1.5775, so it COVERS 1.39x AND DOES NOT COVER 1.87x.

THE CONSEQUENCE IS REPORTED, NOT ENGINEERED AWAY. "Any recall made late by a deferral" is
therefore expected to be non-zero rather than a formality, and it is the column D191 says may not
be omitted. MARGIN_CF is not widened, kappa is not replaced and no factor is fitted to the cells
being diagnosed: D191 item 2 says the safety factor comes from COMMITTED FIT DATA, and a parameter
derived from a cell under diagnosis would be tuning. Every decision records `residency_input` so a
reader can see which input priced it without taking this paragraph's word for it.

WHAT THIS MODULE DOES NOT DECIDE. Whether the saving is ever large enough to clear the bar in a
live regime, and whether a deferred recall then misses its own deadline. Both are measured, the
second as `recall_made_late_by_a_deferral`, which is the column D191 says may not be omitted.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

HERE = Path(__file__).resolve().parent
for _p in (str(HERE), str(HERE / "v5"), str(HERE / "fleet"), str(HERE.parent / "baselines")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import cf_protect_defer as PD                                                  # noqa: E402
import d222_measured_safety as MS                                              # noqa: E402
import d190_measured_safety as MS_SUPERSEDED                                   # noqa: E402

sys.path.insert(0, str(HERE / "v5"))
import cf_cost as CC                                                           # noqa: E402

RD_VERSION = "cf-request-defer-1.1"

# ---------------------------------------------------------------------------
# THE SAFETY FACTOR, MEASURED AND NOT CHOSEN (D191, revised ruling).
#
# `cf_protect_defer.KAPPA` is 1.5775406165458339, the committed q90 of actual over predicted
# SERVICE on a held-out-by-arm split of cf_service_residuals.json. The user's revised ruling is
# that the latest safe start on THIS path must instead carry the MEASURED D162 UNDER-PREDICTION,
# derived from committed RUNG-3 data, with the quantile and source stated. `d190_measured_safety`
# reads it: q90 by nearest rank over the five recall questions actually SENT in the two committed
# covex-v6-fair-c5attr cells, which is 1.8721.
#
# NOT TUNING, AND THE REASON IS THE PROVENANCE OF THE DATA: those are the cells of the BASE rung 4
# is built on, not rung 4's own cells, which is the practice D180 to D182 used to derive the D179
# floors from committed covex-v6-base cells. The committed kappa COVERS the 1.3856 low end of the
# measured range and DOES NOT COVER the 1.8721 high end; the measured factor closes that gap, and
# only in the safe direction, because a LARGER factor puts the latest safe start EARLIER.
#
# `cf_protect_defer.KAPPA` IS LEFT ALONE. Its arms have a posted cell list owned by another
# session, so changing their safety factor would change what those cells measure. The tree holds
# two factors on purpose and each one says which it is.
# D222 (1) item 4, user ruling 2026-11-24. The factor is now the q90 of ENGINE COMPLETION over
# D162 PREDICTED ENGINE service on the committed rung-3 cells, healthy windows only, network
# OUTSIDE the factor: 1.767170 on n = 255, replacing 1.8721 on n = 5. `d190_measured_safety` is
# imported beside it ONLY so a cell can report what was superseded and by how much; nothing
# decides on it any more, and `MS_SUPERSEDED_FACTOR` is never used in an inequality.
SAFETY_FACTOR: float = float(MS.SAFETY_FACTOR)
SAFETY_FACTOR_INFO = MS.INFO
MS_SUPERSEDED_FACTOR: float = float(MS_SUPERSEDED.SAFETY_FACTOR)

# The three deadline types' own bounds are the harness's; THE RECALL DEADLINE IS 3.0 s ON THIS
# WORKLOAD and that is what the self-inflicted-loss column is measured against. It is read from
# the question's own absolute deadline on every decision, so this constant is used only to LABEL
# the column and never to decide anything.
RECALL_DEADLINE_S_LABEL = 3.0

# The one switch, arm-scoped on the INSTANCE, default False, truthy CLASS attribute RAISES. Same
# pattern and same reason as `cf_protect_defer.SWITCH_ATTR`: a class-level switch turns the rung
# on for every arm in the run and makes the cells incomparable.
SWITCH_ATTR = "live2_cf_request_defer"


class RequestDeferSwitchError(RuntimeError):
    """The switch was declared in a shape this component forbids."""


def arm_enables(arm: Any) -> bool:
    """Is question-deferral on for THIS ARM INSTANCE? Default False."""
    try:
        own = vars(arm)
    except TypeError:                                                       # pragma: no cover
        own = {}
    if SWITCH_ATTR not in own:
        for klass in type(arm).__mro__:
            if bool(klass.__dict__.get(SWITCH_ATTR, False)):
                raise RequestDeferSwitchError(
                    "%s is ON as a CLASS attribute of %s and the instance declares nothing. "
                    "This component requires an arm-scoped INSTANCE attribute."
                    % (SWITCH_ATTR, klass.__name__))
        return False
    return bool(own[SWITCH_ATTR])


# A deferral shorter than one decision period cannot be enacted: the next epoch is when the
# opportunity comes back. Imported, not restated.
MIN_DEFERRAL_S = PD.DECISION_PERIOD_S

ACTIONS = ("BASE", "DEFER_TO_LATEST_SAFE_START")

# ON EVERY DECISION, so the exposure is in the data and not only in the docstring above.
RESIDENCY_INPUT = {
    "kind": "RESIDENT_TOKEN_COUNT",
    "quantity": "u_request = readiness_tokens - built_tokens_by_session[session]",
    "is_a_tier_label": False,
    "why_it_matters": ("D190 (5) track C: the hybrid gate prices on the three-label "
                       "residency_readiness(), so GPU-WARM at 44 percent resident and at 28 "
                       "percent resident price identically; on one history that collapse was "
                       "8.17x optimistic (0.6506 s predicted, 5.3166 s observed)"),
    "exposure_this_module_does_inherit": (
        "built_tokens_by_session is the coordinator's BELIEF, not engine telemetry (D44, D47), so "
        "an overstated belief understates u and puts the latest safe start too late by that much"),
    "measured_predictor_bias": ("D162 under-predicts first token by 1.39x to 1.87x on the five "
                                "recall questions SENT in the committed rung-3 cells "
                                "(d190_recall_lag_diagnosis.json)"),
    "kappa_coverage": ("kappa = %.6f covers 1.39x and DOES NOT cover 1.87x. Not widened: D191 "
                       "item 2 fixes the safety factor to committed FIT data, and a factor fitted "
                       "to the cells under diagnosis would be tuning. The consequence is reported "
                       "as 'any recall made late by a deferral' and is expected to be non-zero."
                       % PD.KAPPA),
}

GATES = (
    "no_uncached_prefill",            # u <= 0: nothing to queue ahead of anything
    "no_active_alert_episode",        # the compound is defined while an alert episode is active
    "no_deadline",                    # no absolute deadline, so no latest safe start exists
    "must_start_now_no_slack",        # latest safe start is already here (or within one period)
    "no_other_pending_request",       # nobody to save; the harm population is empty
    "saving_does_not_exceed_margin",  # the inequality was evaluated and did not clear the bar
)


def decide(*, decider_device_id: str, now_s: float,
           alert_active: bool, n_alert_pending: int,
           u_request: int,
           others: Sequence[Dict[str, Any]],
           deadline_abs_s: Optional[float], pred: Any,
           p_on_time: Callable[[float, float], float],
           w_of: Callable[[str], float] = PD.default_w_of,
           w_source: str = PD.W_SOURCE_DEFAULT,
           bar_reading: str = PD.WEIGHT_ON_BAR_DEFAULT,
           harm_scale: float = 1.0,
           margin_scale: float = 1.0) -> Dict[str, Any]:
    """Defer ONE cloud-admitted recall question, or leave it to the base, with the whole trace.

    `others` rows are `cf_protect_defer.harm_on_time`'s rows: `req_id`, `device_id`, `qtype`,
    `engine_s`, `slack_s`, `p_device_on_time`. Nothing is enacted here; the arm enacts.
    """
    out: Dict[str, Any] = {
        "version": RD_VERSION, "decider_device_id": str(decider_device_id),
        "now_s": float(now_s), "alert_active": bool(alert_active),
        "n_alert_pending": int(n_alert_pending),
        "u_request": max(int(u_request), 0),
        "w_source": w_source, "action": "BASE", "gate": None,
        "harm_scale": float(harm_scale), "margin_scale": float(margin_scale),
    }
    if int(u_request) <= 0:
        out["gate"] = "no_uncached_prefill"
        return out
    if not alert_active:
        out["gate"] = "no_active_alert_episode"
        return out
    if deadline_abs_s is None:
        out["gate"] = "no_deadline"
        return out

    # ---- the latest safe start, through the COMMITTED ARITHMETIC with the MEASURED factor -----
    # `cf_cost.latest_safe_start` is the one definition of the quantity in the tree (the same
    # function v5/cf_planner.py:357 calls); only the FACTOR differs here, and it is the measured
    # D162 under-prediction rather than the committed service-residual kappa. Both are recorded.
    # NETWORK OUTSIDE THE FACTOR (the ruled form): `need = safety * engine_s + link`, not
    # `safety * total_s`. `latest_safe_start` is left for `cf_planner` and `cf_protect_defer`.
    _l = CC.latest_safe_start_network_outside(float(now_s), float(deadline_abs_s), pred,
                                              SAFETY_FACTOR)
    lss = dict(_l.as_dict())
    lss["safety_factor_source"] = SAFETY_FACTOR_INFO["source"]
    lss["safety_factor_quantile"] = "%s q%g over n=%d" % (
        SAFETY_FACTOR_INFO["quantile_method"], SAFETY_FACTOR_INFO["quantile"] * 100,
        SAFETY_FACTOR_INFO["n"])
    lss["safety_factor_measured_range"] = [SAFETY_FACTOR_INFO["min"], SAFETY_FACTOR_INFO["max"]]
    lss["safety_factor_superseded"] = MS_SUPERSEDED_FACTOR
    lss["safety_factor_applied_as"] = "safety * engine_s + link (network outside the factor)"
    lss["committed_kappa_not_used_here"] = PD.KAPPA
    out["latest_safe_start"] = lss
    # `cf_cost.LatestSafeStart.deferral_s` IS the quantity, already floored at 0 and already
    # `latest_start_s - now`. It is read, not re-derived from the absolute start: deriving it
    # again here would be a second arithmetic for one number, which is the thing this module's
    # docstring forbids. The KeyError is deliberate - a renamed field must break loudly rather
    # than silently become a zero deferral, which would read as "the mechanism never fires".
    # ---- ITEM 2 (D222 (1)): DEBIT ONE DECISION PERIOD -----------------------------------------
    # The deferral is computed to land EXACTLY on the latest safe start, and the opportunity can
    # only be re-offered at an epoch boundary, which is strictly later. `cf_request_defer` already
    # acknowledged the grid as a FLOOR on the deferral (`MIN_DEFERRAL_S` below) and nowhere as a
    # DEBIT against it. On a constructed shift that quantization alone accounts for 2 of the 4
    # "deferred and late" losses at s5 and 1 of 4 at s4, every one inside 0.035 s of its deadline.
    # One period earlier is the safe direction and costs at most 100 ms of harm saved.
    defer_s_at_latest_start = float(lss["deferral_s"])
    defer_s = max(defer_s_at_latest_start - PD.DECISION_PERIOD_S, 0.0)
    out["deferral_s"] = defer_s
    out["deferral_s_before_epoch_debit"] = defer_s_at_latest_start
    out["epoch_debit_s"] = PD.DECISION_PERIOD_S
    out["must_start_now"] = bool(lss["must_start_now"])
    out["lss_feasible"] = bool(lss["feasible"])
    if defer_s < MIN_DEFERRAL_S:
        out["gate"] = "must_start_now_no_slack"
        return out

    rows = [r for r in others]
    if not rows:
        out["gate"] = "no_other_pending_request"
        return out

    # ---- HARM NOW, the whole population, on the committed valuation ---------------------------
    h = PD.harm_on_time(int(u_request), rows, p_on_time=p_on_time, w_of=w_of,
                        harm_scale=1.0)
    out["harm_now"] = float(h["harm"])
    out["harm_by_type_now"] = dict(h["harm_by_type"])
    out["delta_first_token_s"] = float(h["delta_first_token_s"])
    out["per_queue_s"] = h["per_queue_s"]
    out["price_source"] = h["price_source"]
    out["n_others_considered"] = int(h["n_others_considered"])
    out["n_others_moved"] = int(h["n_others_moved"])

    # ---- HARM SAVED, PER ROW. A row is saved only if its own deadline has passed by the time
    # the deferred prefill starts. Rows still ahead of it keep their loss, and both counts are
    # recorded, because "the deferral saves everything" is the optimistic reading that makes a
    # deferral look free.
    slack_by_req = {str(r.get("req_id")): float(r.get("slack_s", 0.0)) for r in rows}
    type_by_req = {str(r.get("req_id")): str(r.get("qtype", "?")) for r in rows}
    saved = 0.0
    saved_alert = 0.0
    still = 0.0
    n_saved = 0
    n_still = 0
    saved_rows: List[Dict[str, Any]] = []
    for r in h["rows"]:
        rid = str(r.get("req_id"))
        lost = float(r.get("value_lost", 0.0))
        if slack_by_req.get(rid, 0.0) <= defer_s:
            saved += lost
            n_saved += 1
            if type_by_req.get(rid) == "alert":
                saved_alert += lost
            if lost > 0.0 and len(saved_rows) < 8:
                saved_rows.append({"req_id": rid, "qtype": type_by_req.get(rid),
                                   "slack_s": slack_by_req.get(rid), "value_lost": lost})
        else:
            still += lost
            n_still += 1
    sc = float(harm_scale)
    out["harm_saved_unscaled"] = saved
    out["harm_saved"] = saved * sc
    out["harm_saved_alert"] = saved_alert * sc
    out["harm_still_inflicted"] = still
    out["n_rows_saved"] = n_saved
    out["n_rows_still_harmed"] = n_still
    out["saved_rows_sample"] = saved_rows

    # ---- OWN LOSS. The deferral leaves kappa x service of slack instead of the slack it has
    # now, so the decider's own on-time probability falls. Same curve as every harm row.
    eng = float(getattr(pred, "engine_s", 0.0) or 0.0)
    slack_now = float(deadline_abs_s) - float(now_s)
    slack_after = float(deadline_abs_s) - (float(now_s) + defer_s)
    p_before = float(p_on_time(eng, slack_now))
    p_after = float(p_on_time(eng, slack_after))
    w_r = float(w_of(str(decider_device_id)))
    own_loss = w_r * max(p_before - p_after, 0.0)
    out.update(own_engine_s=eng, own_slack_now_s=slack_now, own_slack_after_s=slack_after,
               own_p_before=p_before, own_p_after=p_after, own_loss=own_loss, w_decider=w_r)

    # ---- THE ONE COMPARISON (D191 item 1). No division by anything served.
    net = out["harm_saved"] - own_loss
    b = PD.bar(w_of, str(decider_device_id),
               harmed_device_ids=[str(r.get("device_id")) for r in rows],
               reading=bar_reading, margin_scale=float(margin_scale))
    out["net_gain"] = net
    out["bar"] = b
    out["bar_value"] = float(b["bar"])
    out["crosses_bar"] = bool(net > float(b["bar"]))
    out["units"] = ("counts of expected on-time cloud answers, per-device w_d weighted; "
                    "MARGIN_CF = %.5f on-time answers (D191 item 1)" % PD.MARGIN_CF_ON_TIME)
    out["residency_input"] = RESIDENCY_INPUT
    # ---- THE SELF-INFLICTED-LOSS COLUMN, computed on every candidate and not only the ones
    # that fire, so the exposure of the ones that DID fire can be read against the ones that did
    # not. "Would this deferred question have missed its own deadline under the MEASURED D162
    # bias?" The deferral starts at `now + deferral_s`; under a bias b the service actually takes
    # `b * predicted`, so the finish is `now + deferral_s + b * predicted` and it misses iff that
    # exceeds the absolute deadline. Since `deferral_s = deadline - now - SAFETY_FACTOR *
    # predicted`, the overrun is exactly `(b - SAFETY_FACTOR) * predicted`: NEGATIVE for every b
    # at or below the factor, which is the whole reason the factor is the q90 and not the median.
    # Reported at the measured WORST bias and at the measured MINIMUM, so the column is a range
    # and not a single reassuring number.
    # THE REGISTER CHANGED WITH THE FACTOR AND THE COLUMN FOLLOWS IT. The factor is now a ratio
    # of ENGINE completion to PREDICTED ENGINE service, so the bias it bounds multiplies
    # `engine_s`, not `total_s`; and the overrun is measured against the DEBITED deferral, which is
    # the one actually enacted. With the epoch debit the overrun is
    # `(b - SAFETY_FACTOR) * engine_s - DECISION_PERIOD_S`, so one period of slack now sits on the
    # safe side of every bias at or below the factor.
    total = float(getattr(pred, "total_s", 0.0) or 0.0)
    engine = float(getattr(pred, "engine_s", 0.0) or 0.0)
    miss: Dict[str, Any] = {"recall_deadline_s_label": RECALL_DEADLINE_S_LABEL,
                            "predicted_total_service_s": total,
                            "predicted_engine_service_s": engine,
                            "deferral_s": defer_s,
                            "epoch_debit_s": PD.DECISION_PERIOD_S,
                            "safety_factor_used": SAFETY_FACTOR,
                            "safety_factor_superseded": MS_SUPERSEDED_FACTOR}
    for tag, b in (("at_measured_worst_bias", float(SAFETY_FACTOR_INFO["max"])),
                   ("at_measured_best_bias", float(SAFETY_FACTOR_INFO["min"])),
                   ("at_superseded_factor", MS_SUPERSEDED_FACTOR),
                   ("at_committed_kappa", float(PD.KAPPA))):
        overrun = (float(b) - SAFETY_FACTOR) * engine - PD.DECISION_PERIOD_S
        miss[tag] = {"bias": float(b), "overrun_s": overrun, "would_miss": bool(overrun > 0.0)}
    out["would_miss_deadline_under_measured_bias"] = miss

    if not out["crosses_bar"]:
        out["gate"] = "saving_does_not_exceed_margin"
        return out
    out["action"] = "DEFER_TO_LATEST_SAFE_START"
    out["gate"] = "defer_to_latest_safe_start"
    return out


def trace_lines(d: Dict[str, Any]) -> List[str]:
    """One decision, readable by a person checking the arithmetic by hand (CLAUDE.md Step 3)."""
    if not d:
        return []
    L = ["request-deferral decision, %s at t = %.1f s" % (d.get("decider_device_id"),
                                                          float(d.get("now_s", 0.0))),
         "  uncached prefill u          = %d tokens" % int(d.get("u_request", 0)),
         "  alert instants pending      = %d" % int(d.get("n_alert_pending", 0))]
    if "harm_now" in d:
        L += ["  added first-token delay     = %.6f s  (%s x u)"
              % (float(d.get("delta_first_token_s", 0.0)), d.get("per_queue_s")),
              "  harm if sent now            = %.6f on-time answers over %d rows"
              % (float(d.get("harm_now", 0.0)), int(d.get("n_others_considered", 0))),
              "  deferral                    = %.6f s to the latest safe start"
              % float(d.get("deferral_s", 0.0)),
              "  harm SAVED                  = %.6f over %d rows (alert %.6f); %d rows still "
              "harmed, %.6f" % (float(d.get("harm_saved", 0.0)), int(d.get("n_rows_saved", 0)),
                                float(d.get("harm_saved_alert", 0.0)),
                                int(d.get("n_rows_still_harmed", 0)),
                                float(d.get("harm_still_inflicted", 0.0))),
              "  OWN loss                    = %.6f  (w_R %.4f x (p %.6f -> %.6f), slack %.3f "
              "-> %.3f s)" % (float(d.get("own_loss", 0.0)), float(d.get("w_decider", 1.0)),
                              float(d.get("own_p_before", 0.0)), float(d.get("own_p_after", 0.0)),
                              float(d.get("own_slack_now_s", 0.0)),
                              float(d.get("own_slack_after_s", 0.0))),
              "  NET                         = %.6f  against bar %.6f  (w_R x MARGIN_CF, %s)"
              % (float(d.get("net_gain", 0.0)), float(d.get("bar_value", 0.0)),
                 (d.get("bar") or {}).get("bar_weight_source")),
              "  crosses the bar             = %s" % d.get("crosses_bar")]
    L.append("  gate / action               = %s / %s" % (d.get("gate"), d.get("action")))
    return L
