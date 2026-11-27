#!/usr/bin/env python3
"""STEP 3 OF THE DEPLOYMENT-REGIME PROGRAM: COUNTERFACTUAL ADMISSION AND WORKING-SET PROTECTION.

    "protect a resident subset that fits and defer the rest rather than thrash"
    (research/study_deployment_regime_program.md, the CF line)

THIS MODULE IS THE MECHANISM AND NOTHING ELSE. No harness coupling, no roster read, no action
constructed: `arms_v6cfstep3.py` is the arm that wires it, and every quantity arrives as an
argument so each can be driven to a chosen value in a test. DEFAULT OFF, behind two arm-scoped
INSTANCE switches (a truthy CLASS attribute RAISES, the pattern of `cf_protect_defer`).

TWO PARTS, EACH BEHIND ITS OWN SWITCH, SO EACH CAN BE ATTRIBUTED.

(1) FORFEIT-VALUED ADMISSION (`live2_cf_forfeit_admit`). Load-aware arrival admission (B) rejects a
    robot question whose first token cannot beat its slack. A rejection is valued by B at its
    own cost only. It also FORFEITS state: the prefix this question would have built is what
    that robot's NEXT question finds warm or cold (the opp 4451 cascade: rung 3 sent 4175 and
    built the 25k prefix, la-er rejected it, so 4451 later found nothing cached). The committed
    request-leg rule of `cf_protect_defer` already prices a deviation as

        deviate  iff  value_deviation - value_base  >  w_d x MARGIN_CF          (D151 (1), D171 (1))

    and admits no term for the future. The ONE added term is that future, in the SAME units
    (D177 on-time units, per-device weight w_d, no cross-type exchange rate):

        ADMIT  iff   w_R x p_self  +  FUTURE  -  HARM   >   w_R x MARGIN_CF_ON_TIME

        p_self   this question's own P(on time) at the committed on-time curve, from the arm's own
                 load-aware estimate (the number B compared to the slack)
        FUTURE   w_R x ( p_on(engine_s(u_cold), L) - p_on(engine_s(0), L) ), the on-time
                 probability the same robot's NEXT question gains if the state is kept resident
                 (u_cold = this question's own uncached tokens, because a rejection builds
                 nothing; 0 = the whole prompt resident), L = that question's own deadline
                 duration, taken from THIS question's own fields, and the next question's time
                 is the rules arm's own causal point prediction (`_last_q_t + _gap_ewma`)
                 inside the committed `HORIZON_WARM_CAP_S`
        HARM     the on-time answers OTHERS lose from the u uncached tokens, the committed D162
                 queued-ahead term through `cf_objective.harm_warm_from_queue_delay`, summed over
                 (a) the robot and single-shot questions already PENDING and (b) (D320, switch
                 `live2_cf_harm_arrivals`) the questions EXPECTED TO ARRIVE while the admitted
                 request is served: per other device, window / gap_ewma arrivals, window = this
                 request's current queue wait plus its own service time, the two components of B's
                 est_loadaware (D324), capped at HORIZON_WARM_CAP_S, each priced at B's estimator under the current queue and then
                 delayed by the admission (dashcam stays with C5 and the rung 4 request leg)
        bar      `cf_protect_defer.bar(...)`, the committed MARGIN_CF_ON_TIME scaled by the
                 deficit weight of the device the decision is about

    NO CONSTANT IS INTRODUCED. p_on, engine_s, PER_QUEUE_S, MARGIN_CF, HORIZON_WARM_CAP_S and w_d
    are each read from the module that owns them.

(2) DEFICIT-ROTATED RESIDENT SET (`live2_cf_resident_set`). The sessions whose state may be
    PROTECTED are a subset that FITS the cache: robot sessions with a question estimate, ordered
    by (deficit weight w_d descending, predicted next question earliest, session id), taken
    greedily while the sum of their prompt tokens fits the cache the engine was configured with
    (GPU KV pool + host tier tokens, both configured inputs, less the part of the engine's own
    KV gauge that the robot sessions do not account for). As deficits move, the set ROTATES.
    Two uses, both counted: only a member earns the FUTURE credit in (1) (state is promised only
    to a session that will not be evicted by a larger set), and a state-planner TOUCH of a robot
    session OUTSIDE the set is dropped, because the set already fills the cache, so that touch
    could only evict a member: the thrash this step exists to stop.

WHAT THIS MODULE DOES NOT DECIDE: whether the FUTURE term is ever large enough, live, to cross the
bar; the dry has no engine latency. That is measured by the replay and then by the live cell.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Sequence

# D328: ONE shared definition of the future horizon (the group C S2 gate and this step use the same
# functions, so sync and the counterfactual agree on a robot's future). Moved, not rewritten: the
# bodies are byte-for-byte the ones this file defined first (see future_horizon.py).
from future_horizon import (WINDOW_MODES, arrival_rows, arrival_window,    # noqa: E402,F401
                            expected_questions, forfeited_future)

CF_FORFEIT_VERSION = "cf-forfeit-1.0"

ADMIT_SWITCH = "live2_cf_forfeit_admit"
RESIDENT_SWITCH = "live2_cf_resident_set"
HARM_ARRIVALS_SWITCH = "live2_cf_harm_arrivals"
NET_SWITCH = "live2_cf_s2_netting"


class CfForfeitSwitchError(RuntimeError):
    """A switch of this module was declared in a shape it forbids."""


def _strict(arm: Any, attr: str) -> bool:
    """Instance dict only. A truthy CLASS attribute RAISES (it would turn the step on for every arm
    that inherits it); a non-bool instance value RAISES (a coerced 2 is the plumbing fault the
    CLAUDE.md Step 2b names)."""
    try:
        own = vars(arm)
    except TypeError:                                                       # pragma: no cover
        own = {}
    if attr not in own:
        for klass in type(arm).__mro__:
            if bool(klass.__dict__.get(attr, False)):
                raise CfForfeitSwitchError(
                    "%s is ON as a CLASS attribute of %s and the instance declares nothing; "
                    "it requires an arm-scoped INSTANCE attribute" % (attr, klass.__name__))
        return False
    v = own[attr]
    if not isinstance(v, bool):
        raise CfForfeitSwitchError("%s must be a bool, got %r" % (attr, type(v).__name__))
    return v


def admit_enabled(arm: Any) -> bool:
    """READ SITE: `arms_v6cfstep3._Step3Mixin.decide` (the forfeit-valued admission)."""
    return _strict(arm, ADMIT_SWITCH)


def harm_arrivals_enabled(arm: Any) -> bool:
    """READ SITE: `arms_v6cfstep3._Step3Mixin._cf3_admit` (D320: HARM also prices the questions
    expected to ARRIVE while the admitted request is served). Default OFF."""
    return _strict(arm, HARM_ARRIVALS_SWITCH)


def net_enabled(arm: Any) -> bool:
    """READ SITE: `arms_v6cfstep3._Step3Mixin._cf3_net_claim` (D331 netting ruling: when the
    counterfactual admission and S2's catch-up release would BOTH act on the same robot in the same
    epoch, execute only the action with the higher net value and log the other). Default OFF."""
    return _strict(arm, NET_SWITCH)


def s2_claim_blocks(net_on: bool, held: bool, since: Optional[float], now: float) -> bool:
    """D333 EXTENDED NETTING: S2's claim on a robot's future, opened in an EARLIER epoch than `now`
    and not yet completed, bars F1 from crediting that future (its admission rests on FUTURE > 0);
    a claim opened in THIS epoch goes to the joint evaluation `net_winner` instead."""
    return bool(net_on and held and since is not None and float(since) < float(now))


def net_winner(adm_acc: float, s2_acc: float) -> str:
    """The joint evaluation of one robot in one epoch. Both nets are DEFICIT-WEIGHTED EXPECTED
    ON-TIME-ANSWER GAINS IN FAIR ACCURACY UNITS, each net of its OWN committed firing threshold:
    S2 (`catchup_value.evaluate`): gain_acc - harm_acc, fires iff > 0; F1's admission
    (`arms_v6cfstep3._cf3_net_claim`): (w_R p_self + FUTURE - w_R MARGIN_CF_ON_TIME) x (ACC_QF -
    ACC_DEVICE) - the per-type harm in the same units, fires iff > 0. The higher net executes; a
    tie keeps the action already in the plan (S2's release): no new constant."""
    return "admit" if float(adm_acc) > float(s2_acc) else "s2"


def resident_enabled(arm: Any) -> bool:
    """READ SITES: `arms_v6cfstep3._Step3Mixin.decide` (touch filter, membership credit)."""
    return _strict(arm, RESIDENT_SWITCH)


# ---------------------------------------------------------------------------------------------
# the resident set


def resident_set(cands: Sequence[Dict[str, Any]], capacity_tokens: float) -> Dict[str, Any]:
    """The deficit-rotated resident set that FITS `capacity_tokens`.

    `cands` rows: session_id, device_id, tokens (the session's prompt tokens: its whole history
    resident), w (the device's deficit weight, floored at 1 by the feed), next_q_s (the predicted
    next question time). Order (-w, next_q_s, session_id): the most behind device first, the
    soonest question first among equals, the id last so the order is total and replayable. GREEDY
    WITH SKIP: a member is added if it still fits; one that does not fit is excluded and a later,
    smaller one may still be added. The set is therefore a pure function of its inputs.
    """
    order = sorted(cands, key=lambda c: (-float(c["w"]), float(c["next_q_s"]), str(c["session_id"])))
    cap = max(float(capacity_tokens), 0.0)
    used = 0.0
    members: List[str] = []
    excluded: List[str] = []
    for c in order:
        tok = max(float(c["tokens"]), 0.0)
        if used + tok <= cap:
            members.append(str(c["session_id"]))
            used += tok
        else:
            excluded.append(str(c["session_id"]))
    return {"members": members, "excluded": excluded, "used_tokens": used, "capacity_tokens": cap,
            "n_candidates": len(order), "order": [str(c["session_id"]) for c in order]}


# ---------------------------------------------------------------------------------------------
# D320: the questions expected to ARRIVE while the admitted request is served








# ---------------------------------------------------------------------------------------------
# the forfeited future






# ---------------------------------------------------------------------------------------------
# the decision


ADMIT = "ADMIT"
KEEP_REJECT = "KEEP_REJECT"


def admit_decision(*, in_resident_set: bool, has_estimate: bool, dt_next_s: Optional[float],
                   horizon_cap_s: float, w_r: float, p_self: float, harm: float, bar_value: float,
                   future: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """ADMIT a base-rejected robot question iff  w_R p_self + FUTURE - HARM > bar.

    Every gate that stops it is named, in the order it is checked, and every term is recorded on
    EVERY row, firing or not, so the distribution of the terms is observable on the decisions that
    did not fire.
    """
    out: Dict[str, Any] = {"version": CF_FORFEIT_VERSION, "action": KEEP_REJECT, "gate": None,
                           "in_resident_set": bool(in_resident_set),
                           "has_estimate": bool(has_estimate), "dt_next_s": dt_next_s,
                           "horizon_cap_s": float(horizon_cap_s), "w_r": float(w_r),
                           "p_self": float(p_self), "harm": float(harm),
                           "bar": float(bar_value)}
    if not has_estimate:
        out["gate"] = "no_question_estimate"
        return out
    if dt_next_s is None or float(dt_next_s) > float(horizon_cap_s):
        out["gate"] = "next_question_beyond_horizon"
        return out
    if not in_resident_set:
        out["gate"] = "not_in_resident_set"
        return out
    if future is None:
        out["gate"] = "future_not_priced"
        return out
    fg = float(future["future_gain"])
    own = float(w_r) * float(p_self)
    net = own + fg - float(harm)
    out.update({"future_gain": fg, "own_gain": own, "net": net, "future": future,
                "crosses": bool(net > float(bar_value))})
    if fg <= 0.0:
        out["gate"] = "no_future_gain"
        return out
    if not out["crosses"]:
        out["gate"] = "net_does_not_exceed_the_bar"
        return out
    out["action"] = ADMIT
    out["gate"] = "admit_forfeit_valued"
    return out


def as_dict() -> Dict[str, Any]:
    return {"version": CF_FORFEIT_VERSION, "admit_switch": ADMIT_SWITCH,
            "resident_switch": RESIDENT_SWITCH,
            "rule": "ADMIT iff w_R p_self + FUTURE - HARM > w_R MARGIN_CF_ON_TIME",
            "constants_introduced": []}
