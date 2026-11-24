#!/usr/bin/env python3
"""DEVICE_ANSWERS ARMS: `covex-v6-final-da` (D218 (1)) and `covex-v6-final-nqd` (D232 (2)).

    rung 4 + DEVICE_ANSWERS                          covex-v6-final-da
    rung 3 + protect-and-defer + DEVICE_ANSWERS      covex-v6-final-nqd   <- THE RESHAPED RUNG 4
             + the deficit-fed state planner,
             WITHOUT the question-deferral leg

ITS OWN VERSION LABEL, AND THAT IS THE WHOLE POINT OF THIS FILE. `covex-v6-final` is POSTED, so
its behaviour may not move in place: a second registration under that key would re-point every
reader of its cells (`arms.ARMS` is a dict), and a behaviour change under the same name would
supersede the posted cell under D209 (1). Both arms here are NEW names, nothing in
`arms_final_ladder` is touched, and `covex-v6-final`'s bytes and its dry digest therefore cannot
move. That is proof (a), and it is a property of the code before it is a measurement.

WHAT DEVICE_ANSWERS ADDS, IN ONE SENTENCE. In the request leg's one branch where protect-and-defer
measurably reached "harm crosses the bar" and had no channel - the latest safe start is already
now, so it cannot defer, and a recall query is one prompt, so it cannot be sliced - the arm now
compares the weighted harm to others against this question's own weighted P(on time) and, if the
difference exceeds `w_d x MARGIN_CF`, leaves the question to the device (`ra.decision = "DEVICE"`).
`MARGIN_CF` is 0.6582 in D177's on-time units, unchanged, and there is NO gain weighting: D228 (2)
withdrew D220 (1), and `cf_protect_defer`'s harm call passes `acc_cloud=1.0, acc_device=0.0` with
the accuracy arguments unread, which is what the withdrawal requires.

*** WHY `-nqd` EXISTS, AND WHY THE LEG IS REMOVED RATHER THAN SWITCHED OFF (D232 (2)). ***
Question deferral was removed ON EVIDENCE, not on argument: about 54 live firings across both
posted rung-4 cells with ZERO rescues, one on-time loss at 1x, alert on-time -11.9 pp INSIDE its
own deferral windows against -0.9 pp outside, and at 0.5x the arm carrying it delivered about 111
robot answers on time against rung 3's 122. Rule 2 class: FIRED AND DID NOT HELP. The +1 robot
on-time at 1x came from two questions that were never deferred, so robot on-time not falling was
never evidence the leg helped.

The user ruled the leg REMOVED, and `request_defer=False` would not be that. A gated leg is one
instance attribute away from being back, its counters still exist, its state is still allocated
and its `decide` override still runs on every epoch to read the flag. `V6FinalNQD` deletes
`arms_v6cfr3._Rung4Mixin` FROM THE MRO instead, so:

  * `arms_v6cfr3.py:412` - `self.stats["rd_question_defers"] += 1`, the ONLY write to that counter
    outside `held/` anywhere in the tree - has no call path, because it is inside
    `_Rung4Mixin.decide` and that method is not in the MRO;
  * `cf_request_defer.SWITCH_ATTR` is never written on any object, so the switch is ABSENT rather
    than False, and there is no reader left that could act on it if it were set;
  * no `rd_decisions` / `rd_nets` / `rd_bars` / `rd_trace_*` state is allocated, so
    `coordinator.write_rd_decisions` returns `None` and no `rd_decisions.jsonl.gz` is written;
  * `make_nqd` ASSERTS all four at construction and raises `QuestionDeferralStillPresent`
    otherwise, so an arm that silently regained the leg fails in construction and not in a null
    three minutes into a cell.

"Zero by construction" is a claim about code, so it is made in the code and checked there.

*** WHAT `-nqd` DOES NOT CARRY, SAID HERE RATHER THAN DISCOVERED FROM A CELL. *** Pass 1's five
items (D222 (1) items 1, 2, 4, 5a, 5b) are ALL implemented inside the question-deferral leg -
`_rd_u`, `_rd_one`, `_rd_record`, `_Rung4Mixin.decide` and `cf_request_defer`. With the leg out of
the MRO, none of them has a reader in this arm. In particular:

  * the D222 safety refit 1.767170, applied as `safety * engine_s + LINK_RTT_S`, is read ONLY by
    `cf_request_defer`. Protect-and-defer's latest safe start is `cf_cost.latest_safe_start` at
    `cf_protect_defer.KAPPA` = 1.5775406165458339, network INSIDE the factor. Re-pointing
    protect-and-defer at the refit would change the gate that decides when DEVICE_ANSWERS becomes
    reachable at all, which is a methodological change nobody has ruled, so it is NOT done here.
  * D162 pricing in READING (B) was already protect-and-defer's, through `d162_price`, whose
    `PER_QUEUE_S` is drift-checked against the model's `per_queue_token` (per uncached token).
    Protect-and-defer never carried the `per_overlap`-per-REQUEST form pass-1 item 1 replaced.
  * `cf.model_d162` is DELIBERATELY NOT ATTACHED by this arm. `_Rung4Mixin._cf_engine` attaches
    it for the question-deferral gate, which is its only reader in the tree; attaching it here
    would be a quantity written and never read, which CLAUDE.md Step 2 calls ABSENT, and it is
    the write-only shape this project has been bitten by four times.

THE DEFICIT-FED STATE PLANNER (D206 (3)) IS INHERITED, NOT RE-IMPLEMENTED. `V6FairFinal` already
carries `arms_final_ladder._PlannerFeedMixin`, whose `_cf_engine` calls the ONE shared
`planner_deficit_weights.wire_planner`; `_ProtectDeferMixin` defines no `_cf_engine`, so that is
the method `-nqd` resolves to. `make_nqd` reads the result back and raises unless the engine holds
a live `PlannerDeficitWeights` reading THE SAME feed object as the legs. Two copies of a weight
adapter is how the limb and the legs stop agreeing, so there is one.

WHY THE READ-BACKS ARE NOT CEREMONY. `make_arm` has silently discarded a keyword in this project
before (`c_inflight=8` returned the default arm), and a field declared `int` was coerced to `bool`
and turned a 2 into a 1. So every switch is read back off EVERY object in the decide chain, with
its type, and a mismatch raises here.

REGISTRATION IS ADDITIVE. `arms.py` is another session's file and is not touched. `register()`
checks its own keys against `arms_final_ladder.PROTECTED_NAMES`, the final ladder's three names,
the committed rung-4 family and whatever is already in `arms.ARMS`, and it snapshots the protected
arms' factories before and after and raises if any of them moved.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

HERE = Path(__file__).resolve().parent
for _p in (str(HERE), str(HERE / "v5"), str(HERE / "fleet"), str(HERE / "hybrid"),
           str(HERE.parent / "baselines")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import arms_final_ladder as FL                                                 # noqa: E402
import arms_v6cf as VCF                                                        # noqa: E402
import arms_v6cfr3 as R4                                                       # noqa: E402
import arms_v6rr as RRARM                                                      # noqa: E402
import cf_protect_defer as PD                                                  # noqa: E402
import cf_request_defer as RD                                                  # noqa: E402
import deficit_gain_d178 as GAIND                                              # noqa: E402
import release_recheck as RR                                                   # noqa: E402

DA_VERSION = "covex-v6-final-da-1.0"
NQD_VERSION = "covex-v6-final-nqd-1.0"

RUNG4_DA = "covex-v6-final-da"
RUNG4_NQD = "covex-v6-final-nqd"

BUILT_FROM = {RUNG4_DA: FL.RUNG4, RUNG4_NQD: FL.RUNG3}

DA_NOTE = (
    "covex-v6-final plus spec v6 section 7's THIRD request candidate, DEVICE_ANSWERS, built under "
    "D218 (1). covex-v6-final itself is UNCHANGED and keeps its posted behaviour; this is a "
    "separate version label and a separate arm.")

NQD_NOTE = (
    "covex-v6-fair-final (rung 3) plus protect-and-defer, DEVICE_ANSWERS and the deficit-fed "
    "state planner (D206 (3)), with the QUESTION-DEFERRAL LEG REMOVED FROM THE MRO rather than "
    "switched off (D232 (2)). rd_question_defers is zero by construction: the only write to that "
    "counter lives in arms_v6cfr3._Rung4Mixin.decide, which is not in this arm's MRO. Pass 1's "
    "five items all live in that leg and are therefore ABSENT from this arm, including the "
    "D222 safety refit 1.767170, whose only reader is cf_request_defer.")


class DeviceAnswersWiringError(RuntimeError):
    """The DEVICE_ANSWERS switch did not arrive on the instance it was asked for."""


class QuestionDeferralStillPresent(RuntimeError):
    """The question-deferral leg is reachable on an arm that is declared not to have it."""


class PlannerLimbNotLive(RuntimeError):
    """The deficit-fed state planner (D206 (3)) did not arrive, or is not on the legs' feed."""


# ---------------------------------------------------------------------------------------------
# the read-backs


def _read_back(arm: Any, want: bool) -> Dict[str, Any]:
    """The DEVICE_ANSWERS switch READ BACK off every object the decide path can bind `self` to."""
    chain = [{"class": type(o).__name__,
              "declared_on_instance": PD.DEVICE_ANSWERS_SWITCH_ATTR in vars(o),
              "value": vars(o).get(PD.DEVICE_ANSWERS_SWITCH_ATTR),
              "type": type(vars(o).get(PD.DEVICE_ANSWERS_SWITCH_ATTR)).__name__}
             for o in arm._pd_targets()]
    got = PD.device_answers_enabled(arm)
    rep = {"attr": PD.DEVICE_ANSWERS_SWITCH_ATTR, "asked_for": bool(want),
           "arm_enables": bool(got), "chain": chain,
           "ARRIVED": bool(got == bool(want)),
           "declared_on_every_object": all(c["declared_on_instance"] for c in chain),
           "type_on_every_object": sorted({c["type"] for c in chain})}
    if not rep["ARRIVED"]:                                                 # pragma: no cover
        raise DeviceAnswersWiringError(
            "%s was asked for as %r and reads back as %r on %s. A switch that was passed and did "
            "not arrive is CLAUDE.md Step 2b's named failure, and it would have produced a null "
            "that looked like the candidate not firing."
            % (PD.DEVICE_ANSWERS_SWITCH_ATTR, bool(want), bool(got), type(arm).__name__))
    if not rep["declared_on_every_object"]:                                # pragma: no cover
        raise DeviceAnswersWiringError(
            "%s is missing from an object in the decide chain: %r. `V5Rules2Arm.decide` calls "
            "`self._base.decide`, so a reader that runs against an inner object would read the "
            "class default." % (PD.DEVICE_ANSWERS_SWITCH_ATTR, chain))
    if rep["type_on_every_object"] != ["bool"]:                            # pragma: no cover
        raise DeviceAnswersWiringError(
            "%s arrived with a type other than bool: %r. A field declared int and coerced to "
            "bool turned a 2 into a 1 in this project already."
            % (PD.DEVICE_ANSWERS_SWITCH_ATTR, rep["type_on_every_object"]))
    return rep


# THE FOUR CHECKS THAT MAKE "ZERO BY CONSTRUCTION" A PROPERTY OF THE CODE.
# Each one is a different route by which the leg could come back, and the fourth is the one a
# surface check would miss: an instance attribute set by a caller.
RD_STATE_ATTRS = ("rd_decisions", "rd_nets", "rd_bars", "rd_trace_kept", "rd_trace_crossed")


def _assert_no_question_deferral(arm: Any) -> Dict[str, Any]:
    """The leg is ABSENT, checked four ways, and each check names what it rules out."""
    mro = [c.__name__ for c in type(arm).__mro__]
    mixin_in_mro = R4._Rung4Mixin in type(arm).__mro__
    decide_owner = None
    for c in type(arm).__mro__:
        if "decide" in c.__dict__:
            decide_owner = c.__name__
            break
    state_present = sorted(a for a in RD_STATE_ATTRS if hasattr(arm, a))
    switch_declared = sorted(type(o).__name__ for o in arm._pd_targets()
                             if RD.SWITCH_ATTR in vars(o))
    rep = {
        "mro": mro,
        "_Rung4Mixin_in_mro": bool(mixin_in_mro),
        "first_decide_owner_in_mro": decide_owner,
        "rd_state_attrs_present": state_present,
        "objects_declaring_rd_switch": switch_declared,
        "rd_switch_attr": RD.SWITCH_ATTR,
        "rd_arm_enables": bool(RD.arm_enables(arm)),
        "has_rd_report": hasattr(arm, "rd_report"),
        "the_only_writer_of_rd_question_defers": (
            "arms_v6cfr3.py:412, inside _Rung4Mixin.decide; it is the only write to that counter "
            "outside held/ in the tree, so with the mixin out of the MRO it has no call path"),
    }
    if mixin_in_mro:                                                       # pragma: no cover
        raise QuestionDeferralStillPresent(
            "arms_v6cfr3._Rung4Mixin IS in %s's MRO (%r). D232 (2) removes the leg from the arm; "
            "`request_defer=False` is a gate and not a removal." % (type(arm).__name__, mro))
    if state_present:                                                      # pragma: no cover
        raise QuestionDeferralStillPresent(
            "the question-deferral leg's own state is allocated on this arm: %r" % (state_present,))
    if switch_declared:                                                    # pragma: no cover
        raise QuestionDeferralStillPresent(
            "%s is DECLARED on %r. The switch must be ABSENT, not False: a declared switch is one "
            "assignment away from a leg nobody expects." % (RD.SWITCH_ATTR, switch_declared))
    if hasattr(arm, "rd_report"):                                          # pragma: no cover
        raise QuestionDeferralStillPresent(
            "rd_report() resolves on this arm, so some object in the MRO still owns the leg")
    return rep


def _assert_planner_limb_live(arm: Any) -> Dict[str, Any]:
    """D206 (3): the state planner reads THIS arm's live feed, read back off the engine."""
    cf = arm._cf_engine()
    src = getattr(cf, "counters", None)
    rep = {"engine_counters_class": type(src).__name__,
           "is_declared_constant": bool(getattr(src, "IS_DECLARED_CONSTANT", True)),
           "wired_flag_planner_deficit": bool(getattr(cf, "_planner_deficit_wired", False)),
           "arm_planner_w_source": type(getattr(arm, "_planner_w_source", None)).__name__,
           "same_feed_object_as_the_legs": bool(
               getattr(getattr(src, "_arm", None), "_feed", None) is getattr(arm, "_feed", None)),
           "one_copy": ("planner_deficit_weights.wire_planner, shared with rung 3; this arm adds "
                        "no second swap, so the limb and the legs cannot do it two ways"),
           # recorded so a reader can see what was NOT attached, and why
           "model_d162_attached": bool(getattr(cf, "model_d162", None) is not None),
           "model_d162_note": ("deliberately NOT attached: its only reader in the tree is the "
                               "question-deferral gate, which this arm does not have, and a "
                               "quantity written and never read is ABSENT (CLAUDE.md Step 2)")}
    if rep["is_declared_constant"]:                                        # pragma: no cover
        raise PlannerLimbNotLive(
            "the engine still holds %r, a declared constant, so plan_state would price every "
            "device at 1.0 and D206 (3) would be absent" % (rep["engine_counters_class"],))
    if not rep["same_feed_object_as_the_legs"]:                            # pragma: no cover
        raise PlannerLimbNotLive(
            "the planner source is not reading THE SAME feed object as the legs, so the limb and "
            "the legs could disagree (D206 item 1b)")
    return rep


# ---------------------------------------------------------------------------------------------
# covex-v6-final-da: the POSTED rung 4 with the third request candidate


def make(name: str = RUNG4_DA, *, device_answers: bool = True, **kw: Any) -> Any:
    """Build the final rung 4 with the DEVICE_ANSWERS candidate, through `make_rung4`.

    *** THE SWITCH IS SET AFTER CONSTRUCTION, NOT PASSED INTO `make_rung4`. *** The user ruling of
    2026-11-24 forbids touching `make_rung4` or `covex-v6-final`, for a reason that is about
    evidence and not tidiness: `covex-v6-final` is the arm a posted cell is pinned to, and a
    kwarg added to its factory is a change inside that cell's start-up window. So this module
    reaches in afterwards and sets the switch on every object the decide path can bind `self` to -
    the same `_pd_targets()` loop and the same `object.__setattr__` that `make_rung4` itself uses
    for the request-deferral switch - and then READS IT BACK.
    """
    arm = FL.make_rung4(name, **kw)
    for obj in arm._pd_targets():
        object.__setattr__(obj, PD.DEVICE_ANSWERS_SWITCH_ATTR, bool(device_answers))
    arm.arm_version_da = DA_VERSION
    arm.DA_WIRED_PROOF = _read_back(arm, bool(device_answers))
    arm.DA_NOTE = DA_NOTE
    _publish_switches(arm)
    return arm


# ---------------------------------------------------------------------------------------------
# covex-v6-final-nqd: THE RESHAPED RUNG 4 (D232 (2))

# `_ProtectDeferMixin.live2_describe` reads `arms_v6cf.BASES[self._pd_base_key]`, and
# `arms_final_ladder` already registered the rung-3-final base under `R4_BASE_KEY` additively, so
# this class reuses that registration rather than adding a second one.
V6FinalNQD = type(
    "V6FinalNQD", (VCF._ProtectDeferMixin, FL.V6FairFinal),
    {"_pd_base_key": FL.R4_BASE_KEY,
     "__doc__": ("the reshaped rung 4 (D232 (2)): %s plus protect-and-defer and DEVICE_ANSWERS, "
                 "with arms_v6cfr3._Rung4Mixin DELETED from the MRO so the question-deferral leg "
                 "is absent rather than gated. This is V6Final's tuple minus that one mixin."
                 % (FL.RUNG3,))})

# THE STRUCTURAL GUARD AGAINST DIVERGENCE, because `make_nqd` below deliberately repeats
# `make_rung4`'s switch set rather than calling it. Repeating it is what keeps
# `arms_final_ladder.py` byte-identical, which is proof (a); the cost of repeating it is that a
# switch added to `make_rung4` later would be silently missing here. So the two signatures are
# COMPARED at import time and the difference must be exactly the question-deferral keyword.
_RUNG4_ONLY_EXPECTED = {"request_defer"}


def _signature_drift() -> Dict[str, Any]:
    import inspect                                                         # noqa: PLC0415
    a = {p for p in inspect.signature(FL.make_rung4).parameters if p not in ("name", "kw")}
    b = {p for p in inspect.signature(make_nqd).parameters
         if p not in ("name", "kw", "device_answers")}
    rep = {"make_rung4_only": sorted(a - b), "make_nqd_only": sorted(b - a),
            "expected_make_rung4_only": sorted(_RUNG4_ONLY_EXPECTED)}
    rep["DRIFTED"] = bool((a - b) != _RUNG4_ONLY_EXPECTED or (b - a))
    return rep


def make_nqd(name: str = RUNG4_NQD, *, device_answers: bool = True,
             protect_defer: bool = True,
             live_weight: bool = True, release_recheck: bool = True,
             recheck_types: Any = RRARM.RECHECK_TYPES,
             deficit_feed: bool = True, gain: float = GAIND.GAIN,
             ordering: bool = True, split: bool = True,
             planner_reads_feed: bool = True, qcache_key_fix: bool = True,
             control_harm_zero: bool = False, control_margin_huge: bool = False,
             **kw: Any) -> Any:
    """Build the reshaped rung 4: rung 3's four switches, protect-and-defer, DEVICE_ANSWERS.

    Every line below except the DEVICE_ANSWERS block and the three assertions is
    `arms_final_ladder.make_rung4`'s, in its order, MINUS its question-deferral block. The
    repetition is deliberate and `_signature_drift()` is the guard on it: calling `make_rung4` and
    then surgically removing a mixin from a built instance is not a thing this project should do,
    and editing `make_rung4` would move `covex-v6-final`'s bytes.
    """
    arm = V6FinalNQD(name=name, protect_defer=protect_defer,
                     control_harm_zero=control_harm_zero,
                     control_margin_huge=control_margin_huge, **kw)
    if qcache_key_fix:
        FL._set_qcache_fix(arm)
    arm._fairfeed_init(deficit_feed=deficit_feed, gain=gain, ordering=ordering, split=split)
    object.__setattr__(arm, RR.SWITCH_ATTR, bool(release_recheck))
    if release_recheck:
        object.__setattr__(arm, RR.TYPES_ATTR, tuple(recheck_types))
    if RR.arm_enables(arm) != bool(release_recheck):                       # pragma: no cover
        raise RR.ReleaseRecheckSwitchError("%s did not take" % (RR.SWITCH_ATTR,))
    if release_recheck and tuple(RR.types_for(arm)) != tuple(recheck_types):  # pragma: no cover
        raise RR.ReleaseRecheckSwitchError(
            "%s did not take: reads %r" % (RR.TYPES_ATTR, RR.types_for(arm)))
    # the prerequisite the COORDINATOR refuses on, checked at construction so the failure lands in
    # a proof and not 80 s into a live cell
    if release_recheck and not bool(vars(arm).get("live2_d162_pricing")):  # pragma: no cover
        raise RRARM.PrerequisiteNotMet(
            "%s enables %s without live2_d162_pricing, which the coordinator refuses"
            % (name, RR.SWITCH_ATTR))
    # protect-and-defer's own w_d, the committed accessor, read back exactly as `make_rung4` does.
    # It is kept because the BAR is `w_d * MARGIN_CF` and the harm rows are per-device weighted:
    # this is the protect-and-defer leg's wiring, not the removed leg's.
    if live_weight:
        arm._pd_w_of = lambda did, _a=arm: R4._weight_of(_a, did)
        arm._pd_w_source = R4.W_SOURCE_LIVE
    else:
        arm._pd_w_of = R4.PD.default_w_of
        arm._pd_w_source = R4.W_SOURCE_CONST1
    probe = "robo000"
    got = float(arm._pd_w_of(probe))
    arm.W_WIRED_PROOF = {"accessor": getattr(arm._pd_w_of, "__qualname__", repr(arm._pd_w_of)),
                         "live_weight": bool(live_weight), "probe_device": probe,
                         "probe_value_at_construction": got,
                         "bar_at_probe": got * R4.PD.MARGIN_CF_ON_TIME,
                         "feed_present": hasattr(arm, "_feed"),
                         "feed_gain": float(getattr(arm, "_feed_gain", float("nan"))),
                         "note": ("1.0 at construction is CORRECT: no opportunity has been "
                                  "offered yet, so every shortfall is 0 and every weight is at "
                                  "the D178 (2) floor. What must be true here is that the "
                                  "ACCESSOR is the live one; that the VALUE moves is a run-time "
                                  "property.")}
    if live_weight and not hasattr(arm, "_feed"):                          # pragma: no cover
        raise R4.WeightWiringError("live_weight was asked for and no feed is present")
    arm._planner_reads_feed_declared = bool(planner_reads_feed)
    if planner_reads_feed:
        arm._cf_engine()
        if getattr(arm._planner_w_source, "IS_DECLARED_CONSTANT", True):   # pragma: no cover
            raise FL.LadderSwitchError("the -nqd planner limb kept the declared constant")
    # ---- DEVICE_ANSWERS, set after construction and read back, exactly as `-da` does ----------
    for obj in arm._pd_targets():
        object.__setattr__(obj, PD.DEVICE_ANSWERS_SWITCH_ATTR, bool(device_answers))
    arm.arm_version_nqd = NQD_VERSION
    arm.DA_WIRED_PROOF = _read_back(arm, bool(device_answers))
    arm.NQD_NOTE = NQD_NOTE
    # ---- the three assertions that make the declaration checkable -----------------------------
    arm.NQD_REMOVAL_PROOF = _assert_no_question_deferral(arm)
    arm.NQD_PLANNER_PROOF = (_assert_planner_limb_live(arm) if planner_reads_feed else
                             {"planner_reads_feed": False})
    arm.NQD_SIGNATURE_DRIFT = _signature_drift()
    if arm.NQD_SIGNATURE_DRIFT["DRIFTED"]:                                 # pragma: no cover
        raise QuestionDeferralStillPresent(
            "make_rung4 and make_nqd no longer differ by exactly the question-deferral keyword: "
            "%r. A switch added to make_rung4 would be silently missing from the reshaped rung 4."
            % (arm.NQD_SIGNATURE_DRIFT,))
    _publish_switches(arm)
    return arm


# ---------------------------------------------------------------------------------------------
# the switch map, published WHERE IT LANDS IN THE CELL


def _publish_switches(arm: Any) -> None:
    """Publish the switch map into `arm.stats`, which is what a cell actually reports.

    `coordinator._arm_stats` breadth-walks ("_rules", "_base", "_scorer") and merges every `stats`
    mapping, so a key set here arrives at `coordinator_result.json -> arm_stats` beside the
    counters a reader already consults. No coordinator change is needed for that, and none is
    made: the held `-da` coordinator patch is a REVERSE patch against this base - every one of its
    hunks deletes - and applying it would revert Hit 7's `requested_window_s` and D213 item 3's
    `_belief_prefix_record`. `ra.decision == "DEVICE"` is already read by the coordinator.

    WHY UNCONDITIONALLY, AT CONSTRUCTION: a key written only on the branch that fires would be
    ABSENT on a cell where the candidate legitimately never fired, and ABSENT IS NOT False.

    AND IT IS READ FROM THE READERS, not restated from the keyword, so the field cannot say True
    while the switch is off. A field that restates its own input is the write-only shape wearing a
    label. `question_deferral_present` is read off the MRO for the same reason: it is the
    structural fact, not a flag someone set.
    """
    arm.stats["device_answers_enabled"] = bool(PD.device_answers_enabled(arm))
    arm.stats["protect_defer_enabled"] = bool(PD.arm_enables(arm))
    arm.stats["request_defer_enabled"] = bool(RD.arm_enables(arm))
    arm.stats["question_deferral_leg_in_mro"] = bool(R4._Rung4Mixin in type(arm).__mro__)


# ---------------------------------------------------------------------------------------------
# the arms

DA_ARMS: Dict[str, Any] = {
    # ---- D232 (2): THE RESHAPED RUNG 4. The arm the bar cells are for.
    RUNG4_NQD: (lambda **kw: make_nqd(RUNG4_NQD, **kw)),
    # THE OFF-SWITCH BAR, and it is proof (b): protect-and-defer AND DEVICE_ANSWERS both off, so
    # neither added channel has anywhere to fire from and the arm must collapse to
    # `covex-v6-fair-final` BYTE-IDENTICALLY. It is the test that the additions do nothing on
    # their own, and with the question-deferral leg gone it is also the test that removing the leg
    # from the MRO changed nothing else: rung 3 is exactly what is left.
    RUNG4_NQD + "-off": (lambda **kw: make_nqd(RUNG4_NQD + "-off", protect_defer=False,
                                               device_answers=False, **kw)),
    # THE STEP 2b B-SIDE: protect-and-defer ON, DEVICE_ANSWERS OFF. The one switch under test,
    # changed alone, so a decision difference against `-nqd` is that switch and nothing else.
    RUNG4_NQD + "-daoff": (lambda **kw: make_nqd(RUNG4_NQD + "-daoff", device_answers=False,
                                                 **kw)),
    # CLAUDE.md STEP 4, both directions, ON THE NEW BRANCH, each a NAMED ARM so the control is a
    # cell and not a code edit. `harm0` zeroes the harm at its source so `crosses_bar` is False
    # and the branch is never reached; `margin-huge` scales THE BAR AND ONLY THE BAR, with the
    # same consequence by the other route. A branch that survives its own negative control is not
    # a mechanism. BUILT here, run as cells only when wanted.
    RUNG4_NQD + "-harm0": (lambda **kw: make_nqd(RUNG4_NQD + "-harm0", control_harm_zero=True,
                                                 **kw)),
    RUNG4_NQD + "-margin-huge": (lambda **kw: make_nqd(RUNG4_NQD + "-margin-huge",
                                                       control_margin_huge=True, **kw)),
    # ---- D218 (1): the posted rung 4 with the candidate, kept so its dry proofs reproduce
    RUNG4_DA: (lambda **kw: make(RUNG4_DA, **kw)),
    RUNG4_DA + "-off": (lambda **kw: make(RUNG4_DA + "-off", protect_defer=False,
                                          request_defer=False, **kw)),
    RUNG4_DA + "-harm0": (lambda **kw: make(RUNG4_DA + "-harm0", control_harm_zero=True, **kw)),
    RUNG4_DA + "-margin-huge": (lambda **kw: make(RUNG4_DA + "-margin-huge",
                                                  control_margin_huge=True, **kw)),
}

MUST_NOT_SHADOW = tuple(sorted(set(FL.PROTECTED_NAMES)
                               | set(FL.FINAL_LADDER_ARMS)
                               | set(R4.V6CFR3_ARMS)))

# *** THE NAME LIST IS WRITTEN IN TWO FILES, SO THE DRIFT IS GUARDED AT IMPORT. ***
# `arms_v6cf.DEVICE_ANSWERS_LAZY_NAMES` is what puts these arms on `run_live2_real.py`'s import
# path (it imports `arms` and `hybrid` and nothing else). An arm added here and not there would
# RESOLVE in a friendly process and DIE AT CELL START, which is how four covex-v6-state cells
# were once skipped; an arm added there and not here would raise KeyError at build time inside a
# live cell. Both are launch failures, so the two sets must be equal and that is checked here
# rather than remembered.
_LAZY = tuple(getattr(VCF, "DEVICE_ANSWERS_LAZY_NAMES", ()))
if sorted(_LAZY) != sorted(DA_ARMS):                                       # pragma: no cover
    raise DeviceAnswersWiringError(
        "arms_v6cf.DEVICE_ANSWERS_LAZY_NAMES and this module's DA_ARMS disagree. Only in "
        "arms_v6cf: %r. Only here: %r. A name on one list and not the other is a cell that dies "
        "at launch." % (sorted(set(_LAZY) - set(DA_ARMS)), sorted(set(DA_ARMS) - set(_LAZY))))


def register() -> List[str]:
    """Additive registration with the collision check the D208 hazard note asks for IN CODE."""
    import arms as A                                                       # noqa: PLC0415
    clash = sorted(set(DA_ARMS) & set(MUST_NOT_SHADOW))
    if clash:                                                              # pragma: no cover
        raise DeviceAnswersWiringError(
            "this module would REPLACE existing arm name(s) %r. arms.ARMS is a dict, so a second "
            "registration under an existing key re-points every reader of that arm's committed "
            "cells." % (clash,))
    # A name already in `arms.ARMS` is normally a refusal. The ONE exception is this module's own
    # lazy shim from `arms_v6cf`, which exists so the name is on the harness's import path at all;
    # replacing a shim for the SAME name with the direct factory is not a collision. The shim is
    # identified by its own marker AND by the name it declares itself to be for, so a shim
    # standing in for a different arm is still a refusal.
    already = sorted(n for n in DA_ARMS if n in A.ARMS
                     and not (getattr(A.ARMS[n], "is_device_answers_lazy_shim", False)
                              and getattr(A.ARMS[n], "shim_for", None) == n))
    if already:                                                            # pragma: no cover
        raise DeviceAnswersWiringError(
            "name(s) %r are already in arms.ARMS and would be replaced" % (already,))
    watch = tuple(sorted(set(FL.PROTECTED_NAMES) | set(FL.FINAL_LADDER_ARMS)))
    before = {n: A.ARMS.get(n) for n in watch if n in A.ARMS}
    A.ARMS.update(DA_ARMS)
    after = {n: A.ARMS.get(n) for n in watch if n in A.ARMS}
    if before != after:                                                    # pragma: no cover
        raise DeviceAnswersWiringError("registration changed a protected arm's factory")
    return sorted(DA_ARMS)


ARMS = DA_ARMS
