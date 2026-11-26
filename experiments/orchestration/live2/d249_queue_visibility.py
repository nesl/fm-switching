#!/usr/bin/env python3
"""D249: QUEUE AND HARM VISIBILITY IN THE STATE PLANNER. The switch, and the unit guard.

STATUS: FIRST DEV BUILD on user ruling D249 (2026-11-25 09:29, PROVISIONAL). DEFAULT OFF on every
arm. The only arm that turns it on is `covex-v6-fair-final-q` (rung 3 plus D249).

WHAT IT DOES. The coordinator publishes its in-flight work into the `Observation`
(`interface.InFlightWork`), and `arms_v6state` uses those rows as the harm row source and as the
queued-ahead token count in the state planner's pricing. The authority is
`research/FORMULATION.md`, section "D249 DRAFT: QUEUE AND HARM VISIBILITY IN THE STATE PLANNER":

    harm = SUM over delayed requests of  w_type x ( P(on time now) - P(on time | + queued-ahead
    tokens) ), the delay from the D162 model at per_queue_token seconds per queued-ahead token,
    measured against EACH REQUEST'S OWN DEADLINE SLACK.

*** THE UNIT GUARD, AND WHY IT IS A MODULE AND NOT A COMMENT. ***
`cf_cost.predict`'s `overlap_ft` argument is multiplied by `model.first_token.per_overlap`
= 0.038004811772727576 seconds PER OVERLAPPING REQUEST. D162's queue coefficient is
`per_queue_token` = 0.0001535807289338535 seconds PER TOKEN. The two differ by a factor of about
247.5 AND are in different units, so passing a TOKEN COUNT into `overlap_ft` is wrong by that
factor: it predicted 165.6 s against 0.818 s observed, which drives every `p_on_time` to zero and
produces a large, internally consistent, arm-differentiating shift that is a pure unit error
(`research/study_fix102_prepared.md` section 3 and the D245 estimate record both).

*** THE HARD ZERO IS LOAD-BEARING AND THIS BUILD KEEPS IT. *** `arms_v6state` continues to call
`CC.predict(..., 0, 0)` at every site: `overlap_ft` and `overlap_decode` stay literally zero. The
queue is priced by ADDING `per_queue_token x queued_ahead_tokens` SECONDS to the predicted service,
which is the D162 model's own arithmetic in the D162 model's own unit, so the 247.5x error is not
merely avoided here, it is unreachable from these call sites. `assert_queue_unit` is called on
every conversion and raises rather than returning a number.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import d162_price as DP

D249_SWITCH = "live2_d249_queue_visibility"

# The two committed coefficients, by name, with the measured factor between them.
PER_QUEUE_TOKEN_S = float(DP.PER_QUEUE_S)            # seconds per queued-ahead UNCACHED TOKEN
PER_QUEUE_TOKEN_EXPECTED = 0.0001535807289338535
PER_OVERLAP_S_EXPECTED = 0.038004811772727576        # seconds per overlapping REQUEST
UNIT_FACTOR_EXPECTED = PER_OVERLAP_S_EXPECTED / PER_QUEUE_TOKEN_EXPECTED      # about 247.46


class D249UnitError(RuntimeError):
    """The coefficient applied to a queued-ahead TOKEN count is not `per_queue_token`."""


Q2_SWITCH = "live2_q2_inflight_exclusion"


class D249SwitchError(RuntimeError):
    """The switch was declared as a truthy CLASS attribute, which this build forbids."""


def arm_enables(arm: Any) -> bool:
    """Is D249 on for THIS ARM INSTANCE? Default False.

    INSTANCE-DICT LOOKUP ONLY, and a truthy CLASS attribute RAISES: the same shape, and for the
    same reason, as `arms_v6state.qcache_key_fix_enabled`, `release_recheck.arm_enables` and
    `share_admission.arm_enables`. A class attribute would switch D249 on for every arm that
    inherits from the same base in one run and would make the cells incomparable.
    """
    try:
        own = vars(arm)
    except TypeError:                                                          # pragma: no cover
        own = {}
    if D249_SWITCH not in own:
        for klass in type(arm).__mro__:
            if bool(klass.__dict__.get(D249_SWITCH, False)):
                raise D249SwitchError(
                    "%s is ON as a CLASS attribute of %s and the instance declares nothing; "
                    "D249 requires an arm-scoped INSTANCE attribute"
                    % (D249_SWITCH, klass.__name__))
    return bool(own.get(D249_SWITCH, False))


def q2_arm_enables(arm: Any) -> bool:
    """Is the q2 in-flight exclusion on for THIS ARM INSTANCE? Default False.

    Same shape as `arm_enables`: instance-dict lookup only, and a truthy CLASS attribute RAISES.
    It is a SEPARATE switch from D249_SWITCH. It excludes the in-flight rows from the HOLD_BACK and
    WARM harm only (read at `arms_v6state._queued_behind`); it does nothing unless D249 is also on.
    """
    try:
        own = vars(arm)
    except TypeError:                                                          # pragma: no cover
        own = {}
    if Q2_SWITCH not in own:
        for klass in type(arm).__mro__:
            if bool(klass.__dict__.get(Q2_SWITCH, False)):
                raise D249SwitchError(
                    "%s is ON as a CLASS attribute of %s and the instance declares nothing; "
                    "q2 requires an arm-scoped INSTANCE attribute" % (Q2_SWITCH, klass.__name__))
    v = own.get(Q2_SWITCH, False)
    if not isinstance(v, bool):
        raise D249SwitchError("%s must be a bool, got %r" % (Q2_SWITCH, type(v).__name__))
    return v


def assert_queue_unit(coefficient_s_per_token: float,
                      predict_model: Optional[Dict[str, Any]] = None) -> float:
    """FAIL LOUD unless the coefficient about to be applied to a TOKEN count is `per_queue_token`.

    Three checks, each of which the 247.5x error fails:
      1. the value is D162's committed `per_queue_token`;
      2. it is NOT `cf_cost`'s `per_overlap`, the per-REQUEST coefficient;
      3. where the `predict` model is available, the ratio between the two is the measured 247.46,
         so a future re-fit that silently moved one of them is caught here and not in a result.
    """
    c = float(coefficient_s_per_token)
    if abs(c - PER_QUEUE_TOKEN_EXPECTED) > 1e-15:
        raise D249UnitError(
            "the coefficient applied per queued-ahead TOKEN is %r, not the committed D162 "
            "per_queue_token %r (source %s)" % (c, PER_QUEUE_TOKEN_EXPECTED, DP.SOURCE))
    if abs(c - PER_OVERLAP_S_EXPECTED) < 1e-12:                                # pragma: no cover
        raise D249UnitError(
            "the coefficient applied per queued-ahead TOKEN is cf_cost's per_overlap, which is "
            "seconds per overlapping REQUEST: a token count priced with it is wrong by %.2fx"
            % (UNIT_FACTOR_EXPECTED,))
    if predict_model is not None:
        try:
            po = float(predict_model["first_token"]["per_overlap"])
        except Exception:                                                      # noqa: BLE001
            po = float("nan")
        if po == po:                                                           # not NaN
            if abs(po - PER_OVERLAP_S_EXPECTED) > 1e-12:
                raise D249UnitError(
                    "cf_cost's per_overlap has moved to %r from the committed %r; the 247.5x unit "
                    "relation this guard checks is no longer the measured one"
                    % (po, PER_OVERLAP_S_EXPECTED))
            if abs((po / c) - UNIT_FACTOR_EXPECTED) > 1e-6:                    # pragma: no cover
                raise D249UnitError("per_overlap / per_queue_token = %r, expected %r"
                                    % (po / c, UNIT_FACTOR_EXPECTED))
    return c


def queue_delay_s(queued_ahead_tokens: int,
                  predict_model: Optional[Dict[str, Any]] = None) -> float:
    """Seconds of extra first token from `queued_ahead_tokens` UNCACHED PROMPT TOKENS ahead.

    THE NAME CARRIES THE UNIT, as `cf_cost.predict_d162`'s arguments do and for the same reason.
    The coefficient is asserted on every call: this function is the only place in the D249 path
    where a token count becomes seconds.
    """
    c = assert_queue_unit(PER_QUEUE_TOKEN_S, predict_model)
    return c * max(int(queued_ahead_tokens), 0)


def describe() -> Dict[str, Any]:
    return {"switch": D249_SWITCH,
            "per_queue_token_s": PER_QUEUE_TOKEN_S,
            "per_queue_token_source": DP.SOURCE,
            "per_overlap_s_not_used": PER_OVERLAP_S_EXPECTED,
            "unit_factor": round(UNIT_FACTOR_EXPECTED, 4),
            "overlap_ft_stays_zero": True,
            "authority": ("research/FORMULATION.md :: D249 DRAFT: QUEUE AND HARM VISIBILITY IN "
                          "THE STATE PLANNER")}
