#!/usr/bin/env python3
"""PROTECT AND DEFER, the first of spec v6 section 7's three compound counterfactual candidates.

    "warm or touch recall history H AND defer cold rebuild R to its latest safe start, when R's
     allocation would evict H before H's expected question"   (spec v6 section 7, D165 (D))

THIS MODULE IS THE MECHANISM AND NOTHING ELSE. It holds no harness coupling, reads no roster and
constructs no action; `arms_v6cf.py` is the arm that wires it, and every quantity below arrives
as an argument so each one can be driven to a chosen value in a test. The three compounds are
built one at a time: `keep-ready set` and `admit with protected victim` are NOT here, and neither
is `plan_sync`.

D218 (1) ADDS ONE THING AND ONLY ONE: spec v6 section 7's THIRD REQUEST CANDIDATE, `leave to the
device`, inside the request leg's one branch that measurably reached a decision and had no channel
to express it in. It is behind its OWN arm-scoped switch (`DEVICE_ANSWERS_SWITCH_ATTR`), default
off, because `covex-v6-final` is posted and its behaviour may not move in place.

THE THREE QUANTITIES, AND WHERE EACH ONE COMES FROM. None of them is declared in this file.

  HARM     on-time cloud answers LOST BY OTHERS (D177 (1), D178 (5)). A rebuild of `u` uncached
           tokens placed in front of the pending deadline requests adds `PER_QUEUE_S * u` seconds
           to each of their first tokens - the D162 QUEUED-AHEAD term, which exists to carry
           exactly "one request's prefill pushes another's first token out" - and the harm is the
           on-time probability that delay destroys, weighted per device. The coefficients are
           IMPORTED from `d162_price` and never retyped (the one-price-source ruling of
           2026-11-21); the valuation is `cf_objective.harm_warm_from_queue_delay`, so this term
           and rung 2's `harm_warm` and the planner's request-decision harm are ONE arithmetic on
           ONE price source rather than three modules agreeing by eye.

  MARGIN   `MARGIN_CF` in D177's on-time units, DERIVED here and never retyped: it is
           `cf_objective.attainment_margin(cf_margin.MARGIN_CF)`, which is the committed 0.16456
           divided by the committed `A_D2_DEV = 0.250` that used to scale both gain and margin.
           0.65824. NOT TUNED, NOT SWEPT, and not a parameter of any function below.

  w_d      the deficit weight. ANOTHER SESSION OWNS IT (covex-v6-fair, `w = 1 + 2.0 * shortfall`,
           floored at 1, gain pre-registered at 2.0). It arrives as an injected callable
           `w_of(device_id) -> float`, defaulting to the constant 1.0, so this module works and is
           testable before that lands. Every output records `w_source` so a number computed at the
           default can never be read as a number computed against live deficits.

THE SIDE w_d IS ON, which is the question that decides whether a lagging type defers MORE or LESS.

  There are TWO deficit weights in one inequality and they are not the same weight. Reading them
  as one is the sign error, and it is the kind that yields a plausible null rather than a crash.

    harm  =  sum over OTHER devices j of  w_j * (p_j before - p_j after)
    bar   =  w_R * MARGIN_CF                       R is the device the DECISION IS ABOUT
    defer iff harm > bar

  `w_j` is the weight of the device SUFFERING the harm and it is INSIDE the harm sum, one weight
  per row, which is what `cf_objective.harm_to_others` and `harm_warm_from_queue_delay` already
  do. `w_R` is the weight of the device whose own action is being changed, and it scales the BAR,
  which is what D171 (1), D178 (5) and spec v6 section 7 say in the same words: "MARGIN_CF scaled
  by the deficit weight of the device the decision is about". Both directions are then the ones
  the user's test asks for:

    an alert type further behind its target raises w_j, raises harm, and defers MORE;
    a recall device further behind its own target raises w_R, raises the bar, and defers LESS,
      which is correct: a lagging recall device's rebuild is not postponed lightly.

  PUTTING THE HARMED TYPE'S WEIGHT ON THE BAR IS THE SIGN ERROR, and what it actually does is
  worse than a reversal and much harder to see. Every harm row already carries that same weight,
  so harm and bar scale together and the RATIO that decides is unchanged: the deficit weight
  becomes INERT. That is CLAUDE.md Rule 2's `cancelled by geometry`, and it is exactly the shape
  that yields a believable null rather than a crash, because the weight moves, the counters move
  and the decision does not. MEASURED, not argued: `cf_pd_tests.py::t_sign` drives the harmed
  weight through 1, 2 and 50 and reports the harm-to-bar ratio under both readings - rising under
  the ruled one, constant to 1e-9 under the wrong one - and it also shows that under the wrong
  reading the DECIDER's own deficit is ignored entirely, so a lagging recall device loses the
  protection the ruled bar gives it. `bar_weight_source` records which device the bar's weight
  came from on every decision, and `WEIGHT_ON_BAR_READINGS` keeps the wrong reading reachable so
  that comparison can be run. The default is "decider", the ruled one.

THE LATEST SAFE START IS NOT INVENTED HERE EITHER. D125 defines kappa as the q90 of measured over
predicted completion. A FITTED kappa is committed:
`cf_margin.safety_factor(cf_cost.load_residuals())["safety_factor"]` = 1.5775406165458339, the
q90 of actual-over-predicted service on the held-out-by-arm split of
`results/orchestration/live2/v5/cf_service_residuals.json`, and it is the same factor the
committed v5 planner uses (`v5/cf_planner.py:357`). It is READ, not re-derived, and the
arithmetic is `cf_cost.latest_safe_start`, so there is one definition of the latest safe start in
the tree and not two. TWO CAVEATS TRAVEL WITH IT, on every output:
  * its split is "fit on the non-hybrid arms, test on the hybrids", which is a held-out-by-arm
    split and not D125's words "FIT/DEV", so the register is a committed measured quantile of the
    right kind rather than the pre-registration D125 names;
  * the residual summary itself carries `gate_status: FAILS` and `widened_because_the_gate_fails`.
A reader may therefore not quote a latest-start time as calibrated without that caveat, and
`kappa_register` says so in the data.

WHAT THIS MODULE DOES NOT DECIDE. Whether the harm it computes is ever LARGE ENOUGH to cross the
bar in a live regime. A dry cell does not exercise price: `covex-v6-rules` and `covex-v6-rules-wo`
are byte-identical dry, so the charge mode is unexercised dry, and D174 part B3 found the same.
The harm here is computed from the committed model and the observed slacks, so its ARITHMETIC is
exercised dry; its MAGNITUDE against a real engine is not.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

HERE = Path(__file__).resolve().parent
for _p in (str(HERE), str(HERE / "v5"), str(HERE / "fleet"), str(HERE.parent / "baselines")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import d162_price as DP                                                        # noqa: E402
import share_capacity as SC                                                    # noqa: E402

sys.path.insert(0, str(HERE / "v5"))
import cf_cost as CC                                                           # noqa: E402
import cf_margin as CM                                                         # noqa: E402
import cf_objective as CO                                                      # noqa: E402
import cf_ontime_frozen as OTF                                                # noqa: E402

PD_VERSION = "cf-protect-defer-1.0"

# ---------------------------------------------------------------------------
# THE SWITCH. Arm-scoped INSTANCE attribute, default FALSE, and a truthy CLASS attribute RAISES.
# The pattern is copied from `release_recheck.arm_enables` and `share_admission.arm_enables`, and
# the reason is theirs: a module global that defaulted ON cost a whole live cell here, and a
# class-level switch turns a rung on for every instance in the same run and makes the cells
# incomparable (the D172 rung-2 note on `live2_belief_apply`).
SWITCH_ATTR = "live2_cf_protect_defer"


class ProtectDeferSwitchError(RuntimeError):
    """The switch was declared in a shape this component forbids."""


def arm_enables(arm: Any) -> bool:
    """Is protect-and-defer on for THIS ARM INSTANCE? Default False.

    PLAIN DICT LOOKUP ON THE INSTANCE, deliberately. `getattr` would read a class attribute as
    though the instance had declared it. A class default of False is harmless and is allowed
    through, because it cannot turn anything on.
    """
    try:
        own = vars(arm)
    except TypeError:                                                       # pragma: no cover
        own = {}
    if SWITCH_ATTR not in own:
        for klass in type(arm).__mro__:
            if bool(klass.__dict__.get(SWITCH_ATTR, False)):
                raise ProtectDeferSwitchError(
                    "%s is ON as a CLASS attribute of %s and the instance declares nothing. "
                    "This component requires an arm-scoped INSTANCE attribute: a class-level "
                    "switch turns the compound on for every arm in the run."
                    % (SWITCH_ATTR, klass.__name__))
        return False
    return bool(own[SWITCH_ATTR])


# ---------------------------------------------------------------------------
# D218 (1): THE THIRD REQUEST CANDIDATE, DEVICE_ANSWERS, BEHIND ITS OWN SWITCH.
#
# WHAT IT IS AND WHY IT IS NOT A NEW CANDIDATE. Spec v6 section 7's request row lists THREE
# candidates - "admit now with full history; defer to the latest safe start; leave to the device" -
# and the third was specified and never built here. `v5/cf_planner.py:167` already names it
# DEVICE_ANSWERS in `REQUEST_CANDIDATES` and scores it at `:549`. This is that candidate inside the
# protect-and-defer compound's REQUEST leg, in the one branch that measurably reached a decision
# and had nowhere to put it.
#
# THE MEASURED GAP IT CLOSES. StudyD216-KV025 section 3.5:
# `pd_request_crossed_bar_unexpressible` is 2 at 1x and 27 at 0.25x, and all 27 arrive at the ONE
# gate below (`a request has no slice channel`). The mechanism reached "harm crosses the bar", had
# no channel, fell back to the BASE and admitted the harmful cold rebuild. The latest safe start
# was already now, so it could not defer; a recall query is one prompt, so it could not be sliced.
#
# A SEPARATE SWITCH, NOT A WIDENING OF `SWITCH_ATTR`. `covex-v6-final` is POSTED and running, so
# its behaviour may not move in place (the user's ruling, and D209 (1) on superseding). The
# candidate is therefore off unless an arm declares this second switch on its own instance, with
# the same strict reader shape: a truthy CLASS attribute RAISES, for the reason `arm_enables`
# gives.
DEVICE_ANSWERS_SWITCH_ATTR = "live2_cf_device_answers"


class DeviceAnswersSwitchError(RuntimeError):
    """The DEVICE_ANSWERS switch was declared in a shape this component forbids."""


def device_answers_enabled(arm: Any) -> bool:
    """Is the DEVICE_ANSWERS request candidate on for THIS ARM INSTANCE? Default False."""
    try:
        own = vars(arm)
    except TypeError:                                                       # pragma: no cover
        own = {}
    if DEVICE_ANSWERS_SWITCH_ATTR not in own:
        for klass in type(arm).__mro__:
            if bool(klass.__dict__.get(DEVICE_ANSWERS_SWITCH_ATTR, False)):
                raise DeviceAnswersSwitchError(
                    "%s is ON as a CLASS attribute of %s and the instance declares nothing. "
                    "This candidate requires an arm-scoped INSTANCE attribute: a class-level "
                    "switch turns it on for every arm in the run and would move covex-v6-final, "
                    "which is posted." % (DEVICE_ANSWERS_SWITCH_ATTR, klass.__name__))
        return False
    return bool(own[DEVICE_ANSWERS_SWITCH_ATTR])


# THE RULE, ITS UNITS AND ABOVE ALL ITS SIGN, written down where the arithmetic is.
#
#     deviate to the device IFF   harm_others - w_d * p_self  >  w_d * MARGIN_CF
#
# UNITS (D191 (2)): gain and harm are both COUNTS of expected on-time cloud answers, each device
# weighted by its per-device `w_d` (D185). There is NO division by the number served - the target
# normalisation lives inside `w_d` (D171, D177).
#
# WHY THE OWN TERM IS SUBTRACTED, which is the sign this component has to get right. Replacement
# semantics (D165 (B), D177 (1)): a cloud answer delivered by the deadline REPLACES the device's.
# Leaving the question to the device therefore FORFEITS this question's own expected on-time cloud
# answer. That forfeit is a cost of the deviation, so it is SUBTRACTED from the harm the deviation
# saves, and only what is left is compared against the bar.
#
# THE SIGN IS NOT ASSERTED, IT IS DERIVED FROM COMMITTED CODE. `v5/cf_planner.py` scores request
# candidates as `value = gain - harm`:
#
#     ADMIT_NOW_D2    value = option_value(w, p_self) - harm_to_others = w * p_self - harm
#     DEVICE_ANSWERS  value = device_only_value(...)                   = 0.0 EXACTLY
#                     (`v5/cf_objective.py:683`, D177 (1): a device answer delivers no on-time
#                      CLOUD answers, so it is the reference option and not a competitor on value)
#
# The committed deviation rule (D151 (1), D171 (1)) is `value_cf - value_base > w_d * MARGIN_CF`,
# which for exactly these two candidates is
#
#     (0 - (w * p_self - harm)) > w_d * MARGIN_CF   <=>   harm - w * p_self > w_d * MARGIN_CF
#
# the rule above. So this branch is the committed planner's own arithmetic for the same two
# candidates, and a reader can check the sign without trusting this comment.
DEVICE_ANSWERS_RULE = (
    "deviate to the device iff (weighted harm to others MINUS this question's own weighted "
    "P(on time)) > w_d x MARGIN_CF; D191 (2) units (counts of expected on-time cloud answers, "
    "weighted per device, no division by the number served); the own term is SUBTRACTED because "
    "replacement semantics (D165 B, D177 (1)) mean leaving the question to the device forfeits "
    "this question's own expected on-time cloud answer")
DEVICE_ANSWERS_SIGN_SOURCE = (
    "v5/cf_planner.py:549 scores DEVICE_ANSWERS at value 0.0 (cf_objective.device_only_value) "
    "against ADMIT_NOW_D2 at w*p_self - harm, so value_cf - value_base > w_d x MARGIN_CF is "
    "harm - w*p_self > w_d x MARGIN_CF. Derived from committed code, not asserted here.")

# The three deadline types of spec v6 section 2, fixed so a type that saved NOTHING appears as an
# explicit zero. A type that is never the one saved is a finding about where the mechanism acts,
# and a missing key reads as an omission rather than as a zero.
HARM_TYPES: Tuple[str, ...] = ("alert", "recall", "assistance")


# ---------------------------------------------------------------------------
# THE BAR. Derived from two committed constants by a committed function; never retyped.

# IMPORT-TIME DEPENDENCY, AND WHY IT IS NOW RESOLVED AND NOT ASSUMED. This line read
# `CO.attainment_margin(...)` unconditionally. `cf_objective.attainment_margin` and
# `cf_objective.A_D2_DEV` are being landed by ANOTHER SESSION and exist in no commit yet, so on a
# clean checkout this module raised `AttributeError` AT IMPORT. That is not a local inconvenience:
# `arms_v6cf` imports this module, `arms.py` imports `arms_v6cf` and `run_live2_real.py` imports
# `arms`, so one missing attribute made EVERY ARM IN THE HARNESS unresolvable. It happened
# (2026-11-22 22:46): five gated rung-3 cells died at launch and the driver had to be stopped.
#
# THE FALLBACK IS NOT A SECOND DEFINITION OF THE NUMBER. `attainment_margin(m)` is `m / A_D2_DEV`,
# and both inputs are already committed constants with single owners: `cf_margin.MARGIN_CF`
# (0.16456, declared there and nowhere else in `cf_*`) and `A_D2_DEV = 0.250`, declared in
# `v5/cf_ontime_frozen.py` and `v5/cf_ontime_d162.py`. The fallback READS those two; it retypes
# neither, and it records WHICH path produced the number. When the canonical function lands it is
# PREFERRED, so one definition is in force at a time and the register travels in the data.
_MARGIN_PATH: str
if hasattr(CO, "attainment_margin"):
    MARGIN_CF_ON_TIME: float = float(CO.attainment_margin(float(CM.MARGIN_CF)))
    _A_D2_DEV = float(getattr(CO, "A_D2_DEV", OTF.A_D2_DEV))
    _MARGIN_PATH = "cf_objective.attainment_margin (the canonical function)"
else:
    _A_D2_DEV = float(OTF.A_D2_DEV)
    MARGIN_CF_ON_TIME = float(CM.MARGIN_CF) / _A_D2_DEV
    _MARGIN_PATH = ("FALLBACK cf_margin.MARGIN_CF / cf_ontime_frozen.A_D2_DEV, because "
                    "cf_objective.attainment_margin is not in this tree yet: same arithmetic, "
                    "same two committed constants, no new number.")
MARGIN_CF_ON_TIME_SOURCE = (
    "MARGIN_CF / A_D2_DEV = %.5f / %.3f = %.17g; D177 (3) states it as 0.6582 in on-time units. "
    "Path: %s" % (float(CM.MARGIN_CF), _A_D2_DEV, MARGIN_CF_ON_TIME, _MARGIN_PATH))
MARGIN_CF_ON_TIME_PATH = _MARGIN_PATH
assert round(MARGIN_CF_ON_TIME, 4) == 0.6582, (
    "the derived on-time margin %r does not round to D177 (3)'s 0.6582 (path: %s)"
    % (MARGIN_CF_ON_TIME, _MARGIN_PATH))

WEIGHT_ON_BAR_READINGS: Tuple[str, ...] = ("decider", "max_harmed")
WEIGHT_ON_BAR_DEFAULT = "decider"
WEIGHT_ON_BAR_NOTE = (
    "'decider' is the ruled reading (D171 (1), D178 (5), spec v6 section 7): the bar is "
    "MARGIN_CF scaled by the deficit weight of the device the DECISION IS ABOUT. 'max_harmed' is "
    "the WRONG reading, kept reachable only so what it does can be measured: under it the harmed "
    "type's weight scales harm and bar together, so the ratio that decides is unchanged and the "
    "deficit weight is INERT (cancelled by geometry), while the DECIDING device's own deficit is "
    "ignored entirely. Measured in cf_pd_tests.py::t_sign.")


try:                                                                           # pragma: no cover
    import deficit_gain_d178 as _DG
    DECLARED_GAIN: Optional[float] = float(_DG.GAIN)
    DECLARED_GAIN_SOURCE = "deficit_gain_d178.GAIN (D178 (2), pre-registered 2026-11-22)"
except Exception:                                                              # noqa: BLE001
    _DG = None
    DECLARED_GAIN = None
    DECLARED_GAIN_SOURCE = ("deficit_gain_d178 is not importable from this tree; the declared "
                            "gain is 2.0 per D178 (2) and item B1 owns it")

# WHAT THE INJECTED CALLABLE WILL BE WIRED TO, so the adapter is written down before it is needed.
# D178 (2) declares the weight PER QUERY TYPE - `w_t = 1 + 2.0 * shortfall_t`, floored at 1 - and
# this module's injection point is keyed by DEVICE, because a harm row is one device's request and
# the decider is one device. The adapter is therefore
#
#     w_of = lambda did: deficit_gain_d178.weight(shortfall_of(type_of(did)))
#
# and it makes the two weights of the inequality even plainer than the per-device reading does:
# the bar carries the RECALL type's weight and the harm rows carry the ALERT type's.
W_ADAPTER_NOTE = ("D178 (2)'s weight is per query TYPE; this injection point is per DEVICE, so "
                  "the adapter maps a device to its type's weight. One device has one type "
                  "(spec v6 section 2, D148), so the map is total and unambiguous.")


def default_w_of(_device_id: str) -> float:
    """The injected deficit weight BEFORE covex-v6-fair lands: the constant 1.0 (D178 (2) floor).

    With every w = 1 the bar is exactly MARGIN_CF_ON_TIME, which is the register every number
    produced at this default must be read in.
    """
    return 1.0


W_SOURCE_DEFAULT = ("constant 1.0 (covex-v6-fair's deficit weight is NOT wired here; "
                    "w = 1 + 2.0 x shortfall floored at 1 is another session's component)")


def bar(w_of: Callable[[str], float], decider_device_id: str, *,
        harmed_device_ids: Sequence[str] = (),
        reading: str = WEIGHT_ON_BAR_DEFAULT,
        margin_scale: float = 1.0) -> Dict[str, Any]:
    """`w_d x MARGIN_CF`, with the device the weight came from recorded beside the number.

    `margin_scale` is CLAUDE.md Step 4's SECOND direction and nothing else: it multiplies THE BAR
    AND ONLY THE BAR, and it is 1.0 on every scorable path.

    THE FIRST VERSION OF THAT CONTROL WAS BROKEN AND ITS OWN NUMBERS SAID SO, which is worth the
    four lines it takes to record. It scaled the deficit WEIGHT by 1e9 instead, on the reasoning
    that MARGIN_CF must never be tuned and the weight is the only other factor of the bar. But
    every harm row carries that same weight, so harm and bar scaled TOGETHER, the ratio that
    decides was unchanged, and the "control" reproduced the treatment's digest exactly - 17
    request deferrals and 2 chunks with a bar of 6.6e8. It is the identical cancellation this
    module's sign analysis names for the harmed-type weight, walked into by the control itself,
    and the tell was in the harm column: 5.99e9 on-time answers lost, which is more answers than
    the run contains. Scaling the bar alone cannot cancel, because nothing else reads it.
    """
    if reading not in WEIGHT_ON_BAR_READINGS:
        raise ValueError("unknown weight-on-bar reading %r" % (reading,))
    if reading == "decider":
        did, w = str(decider_device_id), float(w_of(str(decider_device_id)))
    else:
        pairs = [(str(d), float(w_of(str(d)))) for d in harmed_device_ids] or \
                [(str(decider_device_id), float(w_of(str(decider_device_id))))]
        did, w = max(pairs, key=lambda p: p[1])
    return {"bar": w * MARGIN_CF_ON_TIME * float(margin_scale), "w_d": w,
            "bar_weight_source": did, "margin_scale": float(margin_scale),
            "reading": reading, "margin_cf_on_time": MARGIN_CF_ON_TIME}


# ---------------------------------------------------------------------------
# KAPPA, the latest-safe-start safety factor (D125). READ, with its register attached.

def _load_kappa() -> Dict[str, Any]:
    try:
        res = CC.load_residuals()
        sf = CM.safety_factor(res)
    except Exception as exc:                                                   # noqa: BLE001
        return {"kappa": 1.0, "calibrated": False,
                "register": "UNCALIBRATED: no fitted kappa was readable (%s), so the latest-start "
                            "arithmetic below uses kappa = 1.0 and is NOT calibrated" % (exc,),
                "source": None, "quantile": None}
    return {"kappa": float(sf["safety_factor"]), "calibrated": True,
            "quantile": sf.get("quantile"),
            "source": ("v5/cf_margin.safety_factor(cf_cost.load_residuals()); residuals "
                       "%s, split %r" % (res.get("_source"), res.get("split"))),
            "register": ("FITTED and committed: q90 of actual over predicted service, the same "
                         "factor v5/cf_planner.py:357 uses. TWO CAVEATS: its split is "
                         "held-out-BY-ARM ('fit on the non-hybrid arms, test on the hybrids'), "
                         "not D125's words 'FIT/DEV'; and the residual summary itself carries "
                         "gate_status %r. A latest-start time quoted from it must carry both."
                         % (sf.get("gate_status"),))}


KAPPA_INFO = _load_kappa()
KAPPA: float = float(KAPPA_INFO["kappa"])

# One decision period (spec v6 section 4: 100 ms for every arm). A deferral shorter than one
# period cannot be enacted, because the next epoch is when the opportunity is re-offered.
DECISION_PERIOD_S = 0.1

# Spec v6 section 7: the state horizon is "until the history's next likely question (capped 60 to
# 120 s)". The LOWER bound of the stated cap is taken, declared, never swept here.
STATE_HORIZON_S = 60.0

# THE SLICE LADDER, AND WHY IT IS NOT A NEW CONSTANT. Spec v6 section 6 lists "hold back / slice:
# limit what enters the GPU so a large cold rebuild does not evict a history whose question is
# due", and section 5's chunked just-in-time warming already fixes the chunk at 2,048 tokens
# (D160 (1)). A compound that could only offer the SAME 2,048 would offer nothing, which is
# exactly what the first run of this component measured: the base already chunks at 2,048, so
# `u <= 2048` on every state leg and "chunk instead" was a no-op in 2 of 2 decisions that crossed
# the bar. The ladder is therefore the committed chunk HALVED repeatedly - the same halving C5's
# AIMD already uses - and the chosen rung is the LARGEST one whose predicted harm does not exceed
# the bar. The size is thus derived from the bar, not tuned: there is no value here a sweep could
# move.
SLICE_LADDER: Tuple[int, ...] = (2048, 1024, 512, 256, 128, 64, 32, 16)
SLICE_LADDER_NOTE = ("the committed 2,048-token chunk (D160 (1), spec v6 section 5) halved "
                     "repeatedly; the rung is chosen as the largest whose harm is at or below "
                     "the bar, so the slice size is a consequence of the bar and not a knob")

# ---------------------------------------------------------------------------
# HARM: on-time cloud answers lost by others

# The MEASURED per-type medians, imported from the frozen D179 capacity module (committed
# covex-v6-base cells, seeds 4 to 7, healthy windows). Used for the ALERT rows only, because an
# alert instant's own token count is not in the scrubbed Observation; see PROXIES below.
ALERT_UNCACHED_TOKENS = float(SC.FACTORS["alert"]["median_uncached"])
PROXIES = {
    "alert_uncached_tokens": {
        "proxy": ("share_capacity.FACTORS['alert']['median_uncached'] = %.1f"
                  % ALERT_UNCACHED_TOKENS),
        "what_it_actually_measures": ("the median uncached tokens of an EP-G dashcam request over "
                                      "39,949 sent requests in the four committed covex-v6-base "
                                      "cells; it is 374 in each cell separately"),
        "valid_for": ("sizing the SERVICE TIME of a pending alert instant, which is what the "
                      "on-time curve needs. It is a population median, so a single instant's own "
                      "episode length is not represented and a long episode's harm is "
                      "understated"),
        "not_valid_for": "any claim about one named instant's tokens"},
}

HARM_FORMS = ("on-time-cloud", "device-discounted")
HARM_FORM_DEFAULT = "on-time-cloud"
HARM_FORM_NOTE = (
    "'on-time-cloud' is D177's currency and the unit MARGIN_CF_ON_TIME is expressed in: a "
    "displaced request's loss is w_j x (p_before - p_after) on-time CLOUD answers, and a refused "
    "request contributes nothing because p = 0 on both sides (D175 (1): only a DELIVERED cloud "
    "answer replaces the device's). 'device-discounted' multiplies each row by "
    "(1 - p_device_on_time_j), which is the literal reading of D165 (B)'s sentence 'a question "
    "whose device answer was already on time loses nothing when the cloud answer is late'. THE "
    "TWO ARE NOT INTERCHANGEABLE AND THE DIFFERENCE IS NOT COSMETIC: the measured Orin tables "
    "give p_device_on_time = 1.0 for EVERY robot question and for dashcam at EVERY episode "
    "position (v5/cf_objective.py, the DeviceLatency note), so under 'device-discounted' the harm "
    "of displacing an alert or a recall request is EXACTLY ZERO and this compound could only ever "
    "fire on assistance. Both are computed and reported; the default is the one whose units match "
    "the bar, and the choice is a user ruling, not this module's.")


def harm_on_time(u_rebuild: int, others: Sequence[Dict[str, Any]], *,
                 p_on_time: Callable[[float, float], float],
                 w_of: Callable[[str], float] = default_w_of,
                 harm_scale: float = 1.0) -> Dict[str, Any]:
    """HARM: the on-time cloud answers OTHERS lose if `u_rebuild` uncached tokens go out now.

    Each `others` row is one PENDING DEADLINE REQUEST of another device, as a dict with `req_id`,
    `device_id`, `qtype`, `engine_s` (its own predicted service), `slack_s` (deadline minus now)
    and `p_device_on_time`. The rebuild adds `PER_QUEUE_S * u_rebuild` seconds to each one's first
    token; that is the whole of the D162 queued-ahead term and it is IMPORTED, never retyped.

    The valuation is `cf_objective.harm_warm_from_queue_delay`, which under D177's
    `ON_TIME_UNITS` returns `sum_j w_j * (p_before - p_after)` - on-time cloud answers, the unit
    the bar is in. The accuracy arguments are passed as 0.0 and 1.0 and are IGNORED in that mode;
    they are in the signature only so the pre-D177 form stays reachable for a byte-identity proof.

    `harm_scale` is CLAUDE.md Step 4's first direction and nothing else: 0.0 forces the harm to
    zero AT ITS SOURCE, which is how the negative control disables the mechanism under test rather
    than switching the whole component off. It is 1.0 on every scorable path and the value is
    reported on every decision.
    """
    rows = [dict(r, weight=float(w_of(str(r.get("device_id"))))) for r in others]
    wh = CO.harm_warm_from_queue_delay(
        int(u_rebuild), rows, p_on_time=p_on_time,
        acc_cloud=1.0, acc_device=0.0, counters=None)
    by_type: Dict[str, float] = {}
    n_by_type: Dict[str, int] = {}
    discounted = 0.0
    pdev = {str(r.get("req_id")): float(r.get("p_device_on_time", 1.0)) for r in rows}
    qtype = {str(r.get("req_id")): str(r.get("qtype", "?")) for r in rows}
    for r in wh.rows:
        rid = str(r.get("req_id"))
        qt = qtype.get(rid, "?")
        by_type[qt] = by_type.get(qt, 0.0) + float(r["value_lost"])
        # COUNTED HERE AND NOT AT THE CALLER, because the TYPE lives here. A harm row as
        # `cf_objective.harm_warm_from_queue_delay` returns it carries req_id, device_id, weight,
        # the two probabilities and value_lost, and NO qtype: the type is on the INPUT row and is
        # recovered through the `qtype` map above. A caller that counted `r.get("qtype")` on the
        # returned rows would read "?" on every one and report a column of zeros beside a non-zero
        # by-type value - which is exactly what the first version of the D218 trade record did,
        # and the two columns contradicting each other is what caught it.
        n_by_type[qt] = n_by_type.get(qt, 0) + 1
        discounted += float(r["value_lost"]) * (1.0 - pdev.get(rid, 1.0))
    sc = float(harm_scale)
    return {"form": HARM_FORM_DEFAULT,
            "harm": float(wh.total) * sc,
            "harm_unscaled": float(wh.total),
            "harm_scale": sc,
            "harm_device_discounted": float(discounted) * sc,
            "delta_first_token_s": float(wh.delta_t_s),
            "delta_capped_at_healthy_bound": bool(wh.capped),
            "u_rebuild": max(int(u_rebuild), 0),
            "per_queue_s": DP.PER_QUEUE_S,
            "price_source": DP.SOURCE,
            "n_others_considered": len(rows),
            "n_others_moved": int(wh.n_affected),
            "harm_by_type": {k: float(v) for k, v in sorted(by_type.items())},
            "n_moved_by_type": {k: int(v) for k, v in sorted(n_by_type.items())},
            "rows": [dict(r) for r in wh.rows],
            # REPORTING ONLY, and `getattr` for the same reason the bar above is resolved:
            # `cf_objective.ON_TIME_UNITS` is the D177 flag another session is landing and it is
            # in no commit, so reading it as an attribute raised AttributeError here AT RUN TIME,
            # on the first decision that reached the harm - not at import, which is why the
            # import fix alone did not surface it.
            #
            # THE ARITHMETIC IS NOT AFFECTED EITHER WAY, and that is checked rather than hoped.
            # The call above passes `acc_cloud=1.0, acc_device=0.0`, so the committed
            # `option_value` evaluates to `w * (p * 1.0 + (1 - p) * p_dev * 0.0)` = `w * p`, which
            # is exactly what D177's `ON_TIME_UNITS` branch returns. The two forms coincide ON
            # THIS CALL by construction, which is what this module's own docstring means by
            # keeping the accuracy arguments in the signature. So the flag's absence changes a
            # reported field and nothing that decides.
            "on_time_units": bool(getattr(CO, "ON_TIME_UNITS", True)),
            "on_time_units_source": (
                "cf_objective.ON_TIME_UNITS" if hasattr(CO, "ON_TIME_UNITS") else
                "the flag is not in this tree; on-time units are obtained on this call by "
                "acc_cloud=1.0 and acc_device=0.0, under which the committed option_value is "
                "w * p, identical to the D177 branch")}


# ---------------------------------------------------------------------------
# The compound


def latest_safe_start(now_s: float, deadline_abs_s: float, pred: Any) -> Dict[str, Any]:
    """`deadline - kappa x service`, through the committed `cf_cost.latest_safe_start`."""
    lss = CC.latest_safe_start(float(now_s), float(deadline_abs_s), pred, KAPPA)
    d = dict(lss.as_dict())
    d["kappa"] = KAPPA
    d["kappa_calibrated"] = bool(KAPPA_INFO["calibrated"])
    d["kappa_register"] = KAPPA_INFO["register"]
    return d


def device_answers_trade(h: Dict[str, Any], b: Dict[str, Any], *,
                         decider_device_id: str,
                         w_of: Callable[[str], float],
                         p_self: float) -> Dict[str, Any]:
    """THE PREDICTED TRADE of leaving this one question to the device, term by term.

    Built AT THE DECISION and not reconstructed from an aggregate afterwards, because the point of
    the record is to make the mechanism auditable per denial rather than merely counted.

    `w_self` is read EXPLICITLY through `w_of(decider_device_id)` and is NOT taken from `b["w_d"]`.
    They are the same number under the ruled `decider` reading, and they are DIFFERENT numbers
    under `max_harmed`, where `b["w_d"]` is a harmed device's weight. The own term is this
    question's own, so it must carry its own device's weight whichever reading the bar is on.

    THE BY-TYPE BREAKDOWN SUMS TO THE HARM THAT WAS COMPARED, by construction: `harm_on_time`
    accumulates `harm_by_type` from the same rows whose `value_lost` sums to
    `cf_objective.harm_warm_from_queue_delay`'s total, so `sum(by_type) == harm_unscaled`, and
    `harm == harm_unscaled * harm_scale`. The residual is computed and reported rather than
    claimed, so a reader sees the identity hold instead of being told it does.
    """
    w_self = float(w_of(str(decider_device_id)))
    own = w_self * float(max(min(float(p_self), 1.0), 0.0))
    by_type_raw = dict(h.get("harm_by_type") or {})
    saved = {t: float(by_type_raw.get(t, 0.0)) for t in HARM_TYPES}
    other_types = {k: float(v) for k, v in by_type_raw.items() if k not in HARM_TYPES}
    moved_raw = dict(h.get("n_moved_by_type") or {})
    moved_by_type = {t: int(moved_raw.get(t, 0)) for t in HARM_TYPES}
    n_rows = len(list(h.get("rows") or []))
    harm = float(h.get("harm", 0.0))
    # THE IDENTITY'S TOLERANCE IS DERIVED FROM THE ROUNDING THAT CAUSES THE RESIDUAL, not chosen
    # to make the check pass. `cf_objective.harm_warm_from_queue_delay` ROUNDS each row's
    # `value_lost` to 9 decimals in the row dict while accumulating its total UNROUNDED, so a sum
    # over the rounded rows can differ from the total by up to 5e-10 per row. The first version of
    # this check used a flat 1e-9 and reported `holds: false` at a residual of 1.265e-09 over 15
    # denials, which is the rounding and not a defect in the breakdown.
    tol = 5e-10 * max(n_rows, 1) + 1e-12
    return {
        "rule": DEVICE_ANSWERS_RULE,
        "sign_source": DEVICE_ANSWERS_SIGN_SOURCE,
        "register": ("PREDICTED at decision time from the committed D162 price and the committed "
                     "on-time curve. Not an observed outcome: a dry cell has no engine."),
        # the term the rule SUBTRACTS
        "p_self_on_time": float(p_self),
        "w_self": w_self,
        "w_self_source": "w_of(decider_device_id), read explicitly and not from the bar dict",
        "own_lost_weighted_p_on_time": own,
        # what the deviation SAVES, by the TYPE OF THE DEVICES SAVED, with explicit zeros
        "saved_on_time_answers_by_type": saved,
        "saved_total": harm,
        "saved_total_unscaled": float(h.get("harm_unscaled", harm)),
        "harm_scale": float(h.get("harm_scale", 1.0)),
        "by_type_sum": sum(saved.values()) + sum(other_types.values()),
        "by_type_sum_residual_against_unscaled": (
            sum(saved.values()) + sum(other_types.values())
            - float(h.get("harm_unscaled", harm))),
        "by_type_sum_tolerance": tol,
        "by_type_sum_tolerance_source": (
            "5e-10 x n_harm_rows + 1e-12: cf_objective rounds each row's value_lost to 9 decimals "
            "while accumulating the total unrounded, so the residual is that rounding"),
        "by_type_sum_holds": bool(abs(
            sum(saved.values()) + sum(other_types.values())
            - float(h.get("harm_unscaled", harm))) <= tol),
        "n_harm_rows": n_rows,
        "types_outside_the_declared_three": other_types,
        "n_moved_by_type": moved_by_type,
        "n_others_considered": int(h.get("n_others_considered", 0) or 0),
        "n_others_moved": int(h.get("n_others_moved", 0) or 0),
        # the comparison itself
        "net": harm - own,
        "bar": float(b.get("bar", 0.0)),
        "margin_cf_on_time": float(b.get("margin_cf_on_time", 0.0)),
        "bar_w_d": float(b.get("w_d", 0.0)),
        "bar_weight_source": b.get("bar_weight_source"),
        "bar_reading": b.get("reading"),
        "crosses": bool((harm - own) > float(b.get("bar", 0.0))),
    }


def decide(*, decider_device_id: str, now_s: float,
           alert_active: bool, n_alert_pending: int,
           u_rebuild: int, free_kv_tokens: float,
           victim: Optional[Dict[str, Any]],
           others: Sequence[Dict[str, Any]],
           deadline_abs_s: Optional[float], pred: Any,
           chunk_tokens: Optional[int],
           p_on_time: Callable[[float, float], float],
           w_of: Callable[[str], float] = default_w_of,
           w_source: str = W_SOURCE_DEFAULT,
           bar_reading: str = WEIGHT_ON_BAR_DEFAULT,
           harm_scale: float = 1.0,
           margin_scale: float = 1.0,
           device_answers: bool = False) -> Dict[str, Any]:
    """The protect-and-defer decision for ONE pending cold rebuild R, with its whole trace.

    Returns `action` in:
      BASE                 the base's rebuild goes out this epoch unchanged
      PROTECT_AND_DEFER    protect the victim H and hold R back to its latest safe start
      PROTECT_AND_CHUNK    protect H and send R as one chunk instead of the whole tail, because
                           R's latest safe start is already here and holding it whole would miss
                           its deadline
      DEVICE_ANSWERS       D218 (1), and only when `device_answers` is True: leave the question to
                           the device, because R is a RECALL QUERY whose latest safe start is
                           already here, so it can neither wait nor be sliced, and the harm it
                           does others exceeds its own forfeited on-time answer by more than the
                           bar. Spec v6 section 7's third request candidate.
    and the reason for every gate it did not pass. Nothing is enacted here: the arm enacts.
    """
    out: Dict[str, Any] = {
        "version": PD_VERSION, "decider_device_id": str(decider_device_id),
        "now_s": float(now_s), "alert_active": bool(alert_active),
        "n_alert_pending": int(n_alert_pending),
        "u_rebuild": max(int(u_rebuild), 0), "free_kv_tokens": float(free_kv_tokens),
        "victim": (dict(victim) if victim else None),
        "w_source": w_source, "action": "BASE", "gate": None,
        # recorded on EVERY decision, firing or not, so a cell can never be read as having had
        # the candidate available when it did not
        "device_answers_enabled": bool(device_answers),
    }
    # GATE 1: the compound is defined for a rebuild that exists. Nothing to defer, no decision.
    if int(u_rebuild) <= 0:
        out["gate"] = "no_rebuild"
        return out
    # GATE 2: "when alert episodes are active" (spec v6 section 7, the user's framing). With no
    # alert instant pending there is no episode for the rebuild to damage.
    if not alert_active:
        out["gate"] = "no_active_alert_episode"
        return out
    # GATE 3: "R's allocation would evict H before H's expected question". Two parts, and both
    # are required: the allocation must not fit in the free pool, and there must BE a victim whose
    # question falls inside the state horizon.
    fits = float(u_rebuild) <= float(free_kv_tokens)
    out["rebuild_fits_free_pool"] = bool(fits)
    if fits:
        out["gate"] = "rebuild_fits_without_evicting"
        return out
    if not victim:
        out["gate"] = "no_victim_with_a_question_in_the_horizon"
        return out
    # The quantities. Harm first, because the bar is cheap and harm is what the component exists
    # to measure: computing the bar first and short-circuiting would leave the harm distribution
    # unobservable on exactly the decisions that did not fire.
    h = harm_on_time(u_rebuild, others, p_on_time=p_on_time, w_of=w_of, harm_scale=harm_scale)
    b = bar(w_of, decider_device_id,
            harmed_device_ids=[str(r.get("device_id")) for r in others],
            reading=bar_reading, margin_scale=margin_scale)
    out["harm"] = h
    out["bar_detail"] = b
    out["harm_value"] = float(h["harm"])
    out["bar_value"] = float(b["bar"])
    out["crosses_bar"] = bool(float(h["harm"]) > float(b["bar"]))
    if deadline_abs_s is not None and pred is not None:
        out["latest_safe_start"] = latest_safe_start(now_s, deadline_abs_s, pred)
    else:
        out["latest_safe_start"] = None
    if not out["crosses_bar"]:
        out["gate"] = "harm_does_not_exceed_the_bar"
        return out
    # The harm exceeds the bar, so the base's choice is worse than the deviation by more than the
    # model-error bar. WHICH deviation depends on whether R can still wait.
    lss = out["latest_safe_start"]
    deferral_s = float((lss or {}).get("deferral_s", 0.0) or 0.0)
    out["deferral_s"] = deferral_s
    if deferral_s >= DECISION_PERIOD_S:
        out["action"] = "PROTECT_AND_DEFER"
        out["gate"] = "defer_to_latest_safe_start"
        return out
    # The latest safe start is already here, so the whole tail cannot wait. The remaining channel
    # is to SEND LESS NOW: the largest rung of the slice ladder whose harm is at or below the bar.
    #
    # A REQUEST HAS NO SLICE CHANNEL, and saying so here is a fix for a measured defect rather
    # than a precaution. `chunk_tokens=None` is how the caller declares that: a recall QUERY is
    # ONE PROMPT, and sending a slice of it answers nothing. While this branch accepted None it
    # returned PROTECT_AND_CHUNK for request legs, the arm's request leg acts only on
    # PROTECT_AND_DEFER, and the deviation was therefore DROPPED SILENTLY while its gate counter
    # recorded a decision: 43 of 45 "send less" gates on the 0.25x memory cell and 2 of 2 on the
    # 1x c5attr cell were request legs that enacted nothing. That is the write-only field wearing
    # a third mask, and it inflated the gate mix while deflating the port-rule count.
    if chunk_tokens is None:
        # D218 (1). THE CANDIDATE THAT APPLIES HERE IS THE THIRD REQUEST CANDIDATE, and it is now
        # built. Spec v6 section 7's request row: "leave to the device". The rule, its units and
        # its sign are `DEVICE_ANSWERS_RULE` and `DEVICE_ANSWERS_SIGN_SOURCE` above.
        if device_answers:
            if deadline_abs_s is None or pred is None:
                # p_self is this question's own expected on-time cloud answer, and without a
                # deadline or a service prediction there is no p_self to forfeit. The deviation
                # cannot be priced, so it is NOT taken and the decision remains unexpressible -
                # which is what it is, and it is counted as that and not as a declined trade.
                out["device_answers_unpriceable"] = True
                out["gate"] = ("wanted_to_act_but_the_device_trade_cannot_be_priced: "
                               "DEVICE_ANSWERS needs this question's own P(on time), and this "
                               "decision carries no deadline or no service prediction")
                return out
            p_self = float(p_on_time(float(pred.engine_s),
                                     float(deadline_abs_s) - float(now_s)))
            tr = device_answers_trade(h, b, decider_device_id=decider_device_id,
                                      w_of=w_of, p_self=p_self)
            out["device_answers_trade"] = tr
            out["device_answers_net"] = float(tr["net"])
            if tr["crosses"]:
                out["action"] = "DEVICE_ANSWERS"
                out["gate"] = ("leave_to_the_device: the rebuild cannot wait and cannot be "
                               "sliced, and it costs others %.6f on-time answers against this "
                               "question's own %.6f, a net %.6f over a bar of %.6f"
                               % (tr["saved_total"], tr["own_lost_weighted_p_on_time"],
                                  tr["net"], tr["bar"]))
                return out
            # THE BRANCH WAS REACHED AND THE TRADE WAS DECLINED. That is a DECISION, not an
            # absent channel, and it gets its own gate so the fall in the unexpressible counter
            # can never be read as larger than the channel actually made it.
            out["gate"] = ("device_trade_declined: the channel exists and the net %.6f does not "
                           "exceed the bar %.6f, so the base's admission stands"
                           % (tr["net"], tr["bar"]))
            return out
        out["gate"] = ("wanted_to_act_but_a_request_has_no_slice_channel: the latest safe start "
                       "is already here and a recall query is one prompt, so there is nothing to "
                       "send less of. The registered candidate that WOULD apply is "
                       "DEVICE_ANSWERS (spec v6 section 7's request row), which is not part of "
                       "the protect-and-defer compound and is not built here")
        return out
    ladder = [s for s in SLICE_LADDER if s < int(u_rebuild) and s <= int(chunk_tokens)]
    tried: List[Dict[str, Any]] = []
    for s in ladder:
        hc = harm_on_time(s, others, p_on_time=p_on_time, w_of=w_of, harm_scale=harm_scale)
        tried.append({"slice_tokens": s, "harm": hc["harm"]})
        if hc["harm"] <= float(b["bar"]):
            out["harm_if_chunked"] = hc
            out["slice_ladder_tried"] = tried
            out["action"] = "PROTECT_AND_CHUNK"
            out["chunk_tokens"] = int(s)
            out["gate"] = ("must_start_now_so_send_less: the whole tail of %d tokens carries "
                           "%.4f on-time answers of harm against a bar of %.4f, and a slice of "
                           "%d carries %.4f" % (int(u_rebuild), h["harm"], b["bar"], s,
                                                hc["harm"]))
            return out
    out["slice_ladder_tried"] = tried
    out["gate"] = ("wanted_to_act_but_neither_channel_is_expressible: the latest safe start is "
                   "already here, and %s" % ("no rung of the slice ladder is smaller than this "
                                             "rebuild" if not ladder else
                                             "no rung of the slice ladder meets the bar"))
    return out


# ---------------------------------------------------------------------------
# The hand-checkable trace (CLAUDE.md Step 3)


def trace_lines(d: Dict[str, Any]) -> List[str]:
    """One decision, term by term, readable by a person checking the arithmetic by hand."""
    L: List[str] = []
    L.append("PROTECT-AND-DEFER DECISION  %s  t = %.3f s" % (d.get("decider_device_id"),
                                                             d.get("now_s", 0.0)))
    L.append("  inputs")
    L.append("    rebuild R uncached tokens        u = %d" % d.get("u_rebuild", 0))
    L.append("    free GPU KV pool                     %.1f tokens   (rebuild fits: %s)"
             % (d.get("free_kv_tokens", 0.0), d.get("rebuild_fits_free_pool")))
    L.append("    alert episodes active            %s (%d instant(s) pending)"
             % (d.get("alert_active"), d.get("n_alert_pending", 0)))
    v = d.get("victim") or {}
    L.append("    victim history H                 %s, next question in %.2f s, %d tokens warm"
             % (v.get("session_id"), float(v.get("next_question_in_s", 0.0) or 0.0),
                int(v.get("warm_tokens", 0) or 0)))
    h = d.get("harm") or {}
    if h:
        L.append("  HARM: on-time cloud answers lost by others (D177, D162 queue term)")
        L.append("    per_queue_s (imported)           %.13f s per uncached token"
                 % h.get("per_queue_s", 0.0))
        L.append("    delta first token  = %.13f x %d = %.6f s%s"
                 % (h.get("per_queue_s", 0.0), h.get("u_rebuild", 0),
                    h.get("delta_first_token_s", 0.0),
                    "  [CAPPED at the healthy bound]"
                    if h.get("delta_capped_at_healthy_bound") else ""))
        L.append("    others considered %d, of which moved %d"
                 % (h.get("n_others_considered", 0), h.get("n_others_moved", 0)))
        for r in (h.get("rows") or []):
            L.append("      %-14s %-10s w = %.4f  p %.6f -> %.6f  lost %.6f"
                     % (str(r.get("req_id"))[:14], str(r.get("device_id"))[:10],
                        float(r.get("weight", 1.0)), float(r.get("p_on_time_before", 0.0)),
                        float(r.get("p_on_time_after", 0.0)), float(r.get("value_lost", 0.0))))
        L.append("    HARM = %.6f on-time cloud answers   by type %s"
                 % (h.get("harm", 0.0), h.get("harm_by_type")))
        L.append("    (the same rows under the device-discounted reading: %.6f; see "
                 "HARM_FORM_NOTE)" % h.get("harm_device_discounted", 0.0))
    b = d.get("bar_detail") or {}
    if b:
        L.append("  THE BAR: w_d x MARGIN_CF")
        L.append("    MARGIN_CF (on-time units)        %.17g   %s"
                 % (b.get("margin_cf_on_time", 0.0), MARGIN_CF_ON_TIME_SOURCE))
        L.append("    w_d = %.6f  from device %s (reading %r)"
                 % (b.get("w_d", 1.0), b.get("bar_weight_source"), b.get("reading")))
        L.append("    BAR = %.6f x %.17g = %.6f"
                 % (b.get("w_d", 1.0), b.get("margin_cf_on_time", 0.0), b.get("bar", 0.0)))
        L.append("    w source: %s" % d.get("w_source"))
        L.append("  TEST: harm %.6f %s bar %.6f"
                 % (d.get("harm_value", 0.0), ">" if d.get("crosses_bar") else "<=",
                    d.get("bar_value", 0.0)))
    lss = d.get("latest_safe_start")
    if lss:
        L.append("  LATEST SAFE START (D125 kappa, D151 (3))")
        L.append("    predicted service  %.6f s   kappa %.13f   calibrated %s"
                 % (lss.get("predicted_service_s", 0.0), lss.get("kappa", 1.0),
                    lss.get("kappa_calibrated")))
        L.append("    latest start = deadline - kappa x service = %.6f s  (deferral %.6f s, "
                 "must start now %s)" % (lss.get("latest_start_s", 0.0),
                                         lss.get("deferral_s", 0.0),
                                         lss.get("must_start_now")))
    tr = d.get("device_answers_trade")
    if tr:
        L.append("  THE DEVICE TRADE (D218 (1), spec v6 section 7's third request candidate)")
        L.append("    THIS question's own forfeit (replacement semantics, D165 B)")
        L.append("      P(on time) if admitted now        %.6f" % tr.get("p_self_on_time", 0.0))
        L.append("      w_self = %.6f  (%s)"
                 % (tr.get("w_self", 1.0), tr.get("w_self_source")))
        L.append("      own lost = w_self x p_self        %.6f on-time cloud answers"
                 % tr.get("own_lost_weighted_p_on_time", 0.0))
        L.append("    SAVED FOR OTHERS, by the type of the devices saved (explicit zeros kept)")
        for t in HARM_TYPES:
            L.append("      %-12s %12.6f on-time answers   (%d request(s) moved)"
                     % (t, float((tr.get("saved_on_time_answers_by_type") or {}).get(t, 0.0)),
                        int((tr.get("n_moved_by_type") or {}).get(t, 0))))
        for t, v in sorted((tr.get("types_outside_the_declared_three") or {}).items()):
            L.append("      %-12s %12.6f on-time answers   [OUTSIDE the declared three types]"
                     % (t, float(v)))
        L.append("      by-type sum %.9f against the compared harm %.9f, residual %.3e"
                 % (tr.get("by_type_sum", 0.0), tr.get("saved_total_unscaled", 0.0),
                    tr.get("by_type_sum_residual_against_unscaled", 0.0)))
        L.append("    TEST: saved %.6f - own %.6f = net %.6f %s bar %.6f"
                 % (tr.get("saved_total", 0.0), tr.get("own_lost_weighted_p_on_time", 0.0),
                    tr.get("net", 0.0), ">" if tr.get("crosses") else "<=",
                    tr.get("bar", 0.0)))
    L.append("  ACTION: %s" % d.get("action"))
    L.append("    reason: %s" % d.get("gate"))
    return L


def as_dict() -> Dict[str, Any]:
    return {
        "version": PD_VERSION,
        "compound": "protect and defer (spec v6 section 7, D165 (D))",
        "not_built_here": ["keep-ready set", "admit with protected victim", "plan_sync"],
        "switch": {"attr": SWITCH_ATTR, "scope": "arm instance", "default": False,
                   "class_level_on": "RAISES"},
        "device_answers": {"attr": DEVICE_ANSWERS_SWITCH_ATTR, "scope": "arm instance",
                           "default": False, "class_level_on": "RAISES",
                           "candidate": "spec v6 section 7's third request candidate, D218 (1)",
                           "rule": DEVICE_ANSWERS_RULE,
                           "sign_source": DEVICE_ANSWERS_SIGN_SOURCE,
                           "harm_types_reported": list(HARM_TYPES)},
        "margin": {"value": MARGIN_CF_ON_TIME, "source": MARGIN_CF_ON_TIME_SOURCE,
                   "tuned": False, "swept": False},
        "weight": {"injected": True, "default": W_SOURCE_DEFAULT,
                   "declared_gain": DECLARED_GAIN, "declared_gain_source": DECLARED_GAIN_SOURCE,
                   "adapter": W_ADAPTER_NOTE,
                   "bar_readings": list(WEIGHT_ON_BAR_READINGS),
                   "bar_reading_default": WEIGHT_ON_BAR_DEFAULT,
                   "note": WEIGHT_ON_BAR_NOTE},
        "harm": {"forms": list(HARM_FORMS), "default": HARM_FORM_DEFAULT, "note": HARM_FORM_NOTE,
                 "price_source": DP.SOURCE,
                 "per_queue_s": DP.PER_QUEUE_S,
                 "valuation": "cf_objective.harm_warm_from_queue_delay"},
        "kappa": KAPPA_INFO,
        "constants": {"decision_period_s": DECISION_PERIOD_S,
                      "state_horizon_s": STATE_HORIZON_S,
                      "alert_uncached_tokens": ALERT_UNCACHED_TOKENS},
        "proxies": PROXIES,
        "what_a_dry_cell_cannot_establish": (
            "the MAGNITUDE of harm against a real engine, and therefore whether the bar is ever "
            "crossed in a live regime. A dry cell does not exercise price: covex-v6-rules and "
            "covex-v6-rules-wo are byte-identical dry, so the charge mode is unexercised dry, and "
            "D174 part B3 found the same."),
    }


if __name__ == "__main__":
    import json
    print(json.dumps(as_dict(), indent=1))
