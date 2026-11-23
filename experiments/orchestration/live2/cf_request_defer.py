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

sys.path.insert(0, str(HERE / "v5"))
import cf_cost as CC                                                           # noqa: E402

RD_VERSION = "cf-request-defer-1.0"

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

    # ---- the latest safe start, through the committed arithmetic ------------------------------
    lss = PD.latest_safe_start(float(now_s), float(deadline_abs_s), pred)
    out["latest_safe_start"] = lss
    # `cf_cost.LatestSafeStart.deferral_s` IS the quantity, already floored at 0 and already
    # `latest_start_s - now`. It is read, not re-derived from the absolute start: deriving it
    # again here would be a second arithmetic for one number, which is the thing this module's
    # docstring forbids. The KeyError is deliberate - a renamed field must break loudly rather
    # than silently become a zero deferral, which would read as "the mechanism never fires".
    defer_s = float(lss["deferral_s"])
    out["deferral_s"] = defer_s
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
