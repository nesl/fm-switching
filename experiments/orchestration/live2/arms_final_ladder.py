#!/usr/bin/env python3
"""THE FINAL THREE-RUNG LADDER (D208), REGISTERED BESIDE THE COMMITTED ARMS AND NEVER REPLACING ONE.

    rung 2   covex-v6-state-final   covex-v6-state-uo-c5attr + the D188 (2) id(obs) cache-key fix
    rung 3   covex-v6-fair-final    rung 2 + the D185 per-device deficit feed (ordering consumer)
                                           + the STATE PLANNER reading that same feed (D206 (2))
                                           + the ALERT release re-check (D179 (4), the -rr switch)
    rung 4   covex-v6-final         rung 3 + the two counterfactual decisions, protect-and-defer
                                           and question deferral, with the planner limb on the
                                           same feed (D206 (3))

WHY THE NAMES CARRY `-final` AND WHY THAT IS NOT COSMETIC. `covex-v6-state`, `covex-v6-fair` and
`covex-v6` ARE ALREADY REGISTERED NAMES, and `covex-v6-state` carries SIX committed cell
directories (s4, s4_rerun, s5, s6, s7, s7_rerun) and a `results/INDEX.md` citation. `arms.ARMS` is
a dict, so a second registration under one of those keys REPLACES rather than adds, and every
reader of those six committed cells would silently be comparing against a different policy. The
user ruled the suffix (D208, option 2) for exactly that reason. The paper's labels are mapped at
write-up; the code names stay as they are here.

NOTHING IN THIS MODULE RE-IMPLEMENTS A MECHANISM. Every rung is composed from the committed module
that already owns its mechanism, which is why this file is short:

    the id(obs) fix        `arms_v6state.QCACHE_KEY_FIX_SWITCH`, built and proven under D188 (2)
                           and OFF BY DEFAULT. D188 (2) says it must stay off "until the final
                           rung-2 arm and its comparators are rerun TOGETHER with it ON", and this
                           ladder is that rerun. Keyed on `(epoch, now_s)`, which cannot alias.
    the deficit feed       `arms_v6fairfeed.DeficitFeedMixin` over a rung-2 base, unchanged
    the planner limb       `planner_deficit_weights.wire_planner`, ONE copy, shared with rung 4
    the release re-check   `arms_v6rr._AlertRecheckMixin` and `release_recheck`, unchanged
    protect-and-defer      `arms_v6cf._ProtectDeferMixin` over `cf_protect_defer`, unchanged
    question deferral      `arms_v6cfr3._Rung4Mixin` over `cf_request_defer`, unchanged

MRO, AND WHY IT IS IN THIS ORDER. Each rung puts the mechanism it ADDS leftmost, so that mechanism
runs FIRST and calls `super().decide` down into the rung below. The ladder therefore fires bottom
up on every epoch and each added rule sees the action the rung beneath it actually produced.
Reversing any pair would make a compound revise an action the lower rung had not yet ordered.

TWO-PHASE CONSTRUCTION, because the feed does not exist at `__init__` time. `_fairfeed_init` builds
`self._feed`, so anything that closes over the feed is wired AFTER it, and every switch is then
READ BACK through its own strict reader so a construction that did not take RAISES here rather than
producing a plausible null. Every switch in this file is an arm-scoped INSTANCE attribute: a truthy
CLASS attribute raises in all three strict readers, because a class-level switch would turn a rung
on for every arm that inherits it and make the cells incomparable.

WHAT IS NOT IN THIS LADDER, SAID HERE RATHER THAN DISCOVERED LATER. No ablations (D210). No 0.25x
variants (D209 (4) and the user's hold). No share admission, because the c5attr rung-2 base carries
none and the flexible-split consumer of the deficit feed is therefore ABSENT BY CONSTRUCTION on
this base (`share_admission._share_ok` returns before `SA.allowed`), which is Rule 2's
`unexpressible` and NOT a mechanism this ladder dropped.
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

import arms_v6c5 as C5                                                         # noqa: E402
import arms_v6cf as VCF                                                        # noqa: E402
import arms_v6cfr3 as R4                                                       # noqa: E402
import arms_v6fairfeed as FF                                                   # noqa: E402
import arms_v6rr as RRARM                                                      # noqa: E402
import arms_v6state as VS                                                      # noqa: E402
import d249_queue_visibility as QV                                             # noqa: E402
import d261_cold_unlatch as CU                                                 # noqa: E402
import link_read as LR                                                         # noqa: E402
import link_sync as LS                                                         # noqa: E402
import deficit_gain_d178 as GAIND                                              # noqa: E402
import planner_deficit_weights as PDW                                          # noqa: E402
import release_recheck as RR                                                   # noqa: E402

LADDER_VERSION = "covex-v6-final-ladder-1.0"

RUNG2 = "covex-v6-state-final"
RUNG3 = "covex-v6-fair-final"
RUNG4 = "covex-v6-final"
# D230 (2): the per-type saturation guard, built on rung 3 AS A LABELLED VARIANT. It is the
# SAME CLASS and the SAME constructor as RUNG3 with one switch flipped, so a difference
# between the two cells is attributable to that switch and to nothing else.
RUNG3_PTG = "covex-v6-fair-final-ptg"
# D249 (2026-11-25, PROVISIONAL): rung 3 with queue and harm visibility in the state planner.
# SAME CLASS and SAME constructor as RUNG3 with one switch flipped, so a difference between the
# two cells is attributable to that switch and to nothing else.
RUNG3_D249 = "covex-v6-fair-final-q"
# q2 stage 1: `-q` plus the in-flight rows EXCLUDED from the HOLD_BACK/WARM harm (TOUCH harm keeps them).
# SAME CLASS and constructor as RUNG3_D249 with one extra switch (`QV.Q2_SWITCH`) flipped.
RUNG3_Q2 = "covex-v6-fair-final-q2"
# q2m ablation (user ruling D282): `-q2` with the margin at rung 3's committed 0.6582 (MS.Q2M_SWITCH).
RUNG3_Q2M = "covex-v6-fair-final-q2m"
# q4 (study_q4_avoided_rebuild_credit_prereg): `-q2m` plus the avoided-rebuild credit on TOUCH
# (`q4_avoided_rebuild.Q4_SWITCH`). SAME CLASS and constructor as RUNG3_Q2M with one more switch.
RUNG3_Q4 = "covex-v6-fair-final-q4"
# link_events line: `-q` plus the arm-side READ of `Observation.device_links` (decision-neutral).
RUNG3_LINK = "covex-v6-fair-final-q-link"
# link_sync line: `-q` plus post-outage sync control. "ours" = priority release (form iv) and the
# question-first / wait / device choice; the control = FIFO release, deficit gain 0 (D226).
# THE GATE ARMS ARE THE D177 CURRENCY, AS RULED (accuracy not read; question-first accuracy 0.568799
# PROVISIONAL, reporting only). The `-acc` pair carries a MODELLED value (a stand-in missing-evidence
# accuracy and a uniform evidence share) and is NOT for a gate cell without a user ruling.
RUNG3_SYNC = "covex-v6-fair-final-q-sync"                 # MAIN: accuracy-weighted (D281)
RUNG3_SYNC_D177 = "covex-v6-fair-final-q-sync-d177"       # ABLATION: on-time only
RUNG3_SYNC_CTL = "covex-v6-fair-final-q-sync-ctl"         # naive recovery: FIFO, deficit gain 0
RUNG3_SYNC_FREE = "covex-v6-fair-final-q-sync-free"       # extra: d177 plus release-when-free

# The committed arm each final rung is built FROM, for the mapping row the user asked for.
BUILT_FROM = {RUNG2: "covex-v6-state-uo-c5attr",
              RUNG3: "covex-v6-fair-c5attr plus covex-v6-fair-c5attr-rr",
              RUNG4: "covex-v6-cf-c5attr"}


class LadderSwitchError(RuntimeError):
    """A final-rung switch did not take on the instance it was set on."""


# ---------------------------------------------------------------------------------------------
# rung 2


class V6StateFinal(C5.V6StateUoC5AttrArm):
    """rung 2: the c5attr rung-2 arm with the D188 (2) cache-key fix ON.

    The fix itself is NOT here. It is `arms_v6state._queued_behind`'s own switch, and this class
    exists only so rung 3 has a BASE CLASS to be mixed over: `arms_v6fairfeed.make_class` takes a
    class, not a factory. The switch is set on the INSTANCE by `make_rung2` and by every rung above
    it, never on this class, because `arms_v6state.qcache_key_fix_enabled` RAISES on a truthy class
    attribute and it is right to.
    """


def _set_qcache_fix(arm: Any) -> None:
    """Turn the D188 (2) fix on for THIS INSTANCE and read it back through the strict reader."""
    object.__setattr__(arm, VS.QCACHE_KEY_FIX_SWITCH, True)
    # the resolved cache must not already hold the OFF answer from an earlier call
    arm.__dict__.pop("_qcache_key_fix_resolved", None)
    if not VS.qcache_key_fix_enabled(arm):                                 # pragma: no cover
        raise LadderSwitchError(
            "%s did not take on the instance of %s, so the final ladder would have run with the "
            "id(obs) memory-address cache key that D188 (2) exists to remove"
            % (VS.QCACHE_KEY_FIX_SWITCH, type(arm).__name__))


def make_rung2(name: str = RUNG2, *, qcache_key_fix: bool = True, **kw: Any) -> Any:
    arm = V6StateFinal(name=name, **kw)
    if qcache_key_fix:
        _set_qcache_fix(arm)
    return arm


# ---------------------------------------------------------------------------------------------
# rung 3

# Registered ADDITIVELY into the feed module's base map, the pattern `arms_v6cfr3` uses on
# `arms_v6cf.BASES`: it adds a third key and changes neither of the two already there, so
# `covex-v6-fair-c5attr` and `covex-v6-fair-shares` cannot move.
FF.BASES.setdefault(RUNG2, V6StateFinal)
FF.BASE_HAS_WEIGHT_READER.setdefault(RUNG2, False)


def _build_rung3_class() -> Any:
    feed_over_rung2 = FF.make_class(RUNG2)
    return type("V6FairFinal", (RRARM._AlertRecheckMixin, feed_over_rung2),
                {"__doc__": ("rung 3: %s plus the deficit feed, the planner limb on that feed and "
                             "the ALERT release re-check" % (RUNG2,)),
                 "_fairfeed_base_name": RUNG2})


class _PlannerFeedMixin:
    """`_cf_engine` with the STATE PLANNER reading this rung's own live feed (D206 (2), (3)).

    The base builds the engine with `cf_objective.NoPlannerDeficitFeed`, which is the correct
    DECLARATION for a rung whose feed does not reach the planner and is wrong for these rungs. The
    swap goes through the ONE shared `wire_planner`, so rung 3 and rung 4 cannot do it two ways.

    MEASURED CONSEQUENCE, so nobody reads this as cosmetic: on the dry s4 cell the same swap moves
    687 of 60,473 rung-3 state decisions (63,242 weight reads, 0 unresolved, 53,597 above the w = 1
    floor), recorded in `d200_r3_planner_weight_probe.json`. That measurement was made on the
    PRE-FINAL rung-3 arm and is what D208 applies here.
    """

    def _cf_engine(self) -> Any:
        return PDW.wire_planner(self, super()._cf_engine())                # type: ignore[misc]

    def planner_weight_report(self) -> Dict[str, Any]:
        src = getattr(self, "_planner_w_source", None)
        return src.as_dict() if src is not None else {"source": None, "wired": False}


def _build_rung3_final() -> Any:
    base = _build_rung3_class()
    return type("V6FairFinalWired", (_PlannerFeedMixin, base), {"__doc__": base.__doc__})


V6FairFinal = _build_rung3_final()


def _set_per_type_guard(arm: Any, thresholds=None) -> None:
    """Turn the D230 (2) / D178 (3) per-type guard on for THIS INSTANCE and read it back.

    SET ON BOTH OBJECTS, and that is not belt-and-braces. `guard_state` is defined on
    `V5Rules2Arm` and every rung-2+ consumer calls it as `self._rules.guard_state(obs)`
    (arms_v6state.py:382, arms_v6cf.py:442, arms_v6cfr3.py:371), so `self` at the READ is the
    composed `_rules` object and the switch must be there. The arm itself is set too, because
    `V6StateArm.__getattr__` makes the arm answer for `_rules` and a switch that disagreed
    between the two is `d225_switch_diff`'s SHADOWED case: the value a reader gets would then
    depend on which object it asked. `arms_v5rules2.py:112-118` records the same lesson for
    `over_limit_infeasible`, which was the switch that taught it.
    """
    import arms_v5rules2 as R2                                             # noqa: PLC0415
    thr = dict(R2.GUARD_LAG_S_BY_CLASS_D178 if thresholds is None else thresholds)
    rules = vars(arm).get("_rules")
    if rules is None:                                                      # pragma: no cover
        raise LadderSwitchError(
            "%s has no `_rules`, so there is no object holding `guard_state` to switch. The\n"
            "per-type guard would have been set on an arm that never reads it, which is the\n"
            "write-only field CLAUDE.md Step 2 is about." % (type(arm).__name__,))
    for obj in (rules, arm):
        object.__setattr__(obj, R2.GUARD_PER_TYPE_SWITCH, True)
        object.__setattr__(obj, "guard_lag_s_by_class", dict(thr))
    # read back THROUGH THE STRICT READER, on the object the read site actually runs against
    for obj in (rules, arm):
        if not R2.guard_per_type_enabled(obj):                             # pragma: no cover
            raise LadderSwitchError(
                "%s did not take on %s, so the variant would have run the committed single\n"
                "2.0 s guard under a name that says it does not."
                % (R2.GUARD_PER_TYPE_SWITCH, type(obj).__name__))
        got = dict(getattr(obj, "guard_lag_s_by_class", {}) or {})
        if got != thr:                                                     # pragma: no cover
            raise LadderSwitchError(
                "the per-type thresholds did not take on %s: reads %r, expected %r"
                % (type(obj).__name__, got, thr))


def _set_hysteresis(arm: Any) -> None:
    """D166 (3) / D231 (3). Set on BOTH objects and read back, for the reason
    `_set_per_type_guard` gives: `guard_state` runs against the composed `_rules`."""
    import arms_v5rules2 as R2                                             # noqa: PLC0415
    rules = vars(arm).get("_rules")
    if rules is None:                                                      # pragma: no cover
        raise LadderSwitchError("no `_rules` to hold the hysteresis latch")
    for obj in (rules, arm):
        object.__setattr__(obj, R2.GUARD_HYSTERESIS_SWITCH, True)
        object.__setattr__(obj, "guard_exit_factor", float(R2.GUARD_EXIT_FACTOR_D166))
        object.__setattr__(obj, "guard_exit_hold_s", float(R2.GUARD_EXIT_HOLD_S_D166))
    for obj in (rules, arm):
        if not R2.guard_hysteresis_enabled(obj):                           # pragma: no cover
            raise LadderSwitchError(
                "%s did not take on %s, so the variant would have run the memoryless guard "
                "under a name that says it latches."
                % (R2.GUARD_HYSTERESIS_SWITCH, type(obj).__name__))
    # the LATCH STATE must be ONE object, not two: `guard_state` runs against `_rules`, and a
    # second copy on the arm would be a dead latch that no period ever advances.
    if "_g_latched" in vars(arm):                                           # pragma: no cover
        raise LadderSwitchError(
            "%s carries its OWN `_g_latched`, which would SHADOW the latch `guard_state`\n"
            "actually advances on `_rules`: the arm would answer from a latch no period ever\n"
            "moved. There must be exactly one." % (type(arm).__name__,))


def _set_guard_log(arm: Any) -> None:
    """D230 (2) limitation 1. Logging only; `coordinator.write_guard_log` is the writer."""
    import arms_v5rules2 as R2                                             # noqa: PLC0415
    rules = vars(arm).get("_rules")
    if rules is None:                                                      # pragma: no cover
        raise LadderSwitchError("no `_rules` to hold the guard log")
    for obj in (rules, arm):
        object.__setattr__(obj, "guard_log", True)
        object.__setattr__(obj, "GUARD_LOG_CAP", int(R2.GUARD_LOG_CAP_DEFAULT))
    # the rows list lives on `_rules`, which is the object `guard_state` appends from, and on
    # the arm, which is what `coordinator.write_guard_log` reads. ONE list, two references.
    rows: List[Dict[str, Any]] = []
    for obj in (rules, arm):
        object.__setattr__(obj, "guard_log_rows", rows)
        object.__setattr__(obj, "_guard_log_last_t", None)
    if arm.guard_log_rows is not rules.guard_log_rows:                      # pragma: no cover
        raise LadderSwitchError("the guard log list is not shared, so the written file would "
                                "be the empty one the coordinator happens to hold")


def _set_d249(arm: Any) -> None:
    """Turn D249 queue-and-harm visibility on for THIS INSTANCE and read it back strictly.

    The coordinator reads the SAME instance attribute (`coordinator.__init__` ->
    `d249_queue_visibility.arm_enables`) to decide whether to publish the in-flight rows, and
    `arms_v6state` reads it to decide whether to consume them. One attribute on one object, so a
    build where the publisher is on and the consumer off is not expressible.
    """
    object.__setattr__(arm, QV.D249_SWITCH, True)
    arm.__dict__.pop("_d249_resolved", None)
    if not QV.arm_enables(arm):                                            # pragma: no cover
        raise LadderSwitchError(
            "%s did not take on the instance of %s, so the cell would have run rung 3 under a "
            "D249 name with no queue visibility at all" % (QV.D249_SWITCH, type(arm).__name__))


def _set_q2(arm: Any) -> None:
    """Turn the q2 in-flight exclusion on for THIS INSTANCE and read it back strictly. Needs D249."""
    if not QV.arm_enables(arm):
        raise LadderSwitchError("q2 requires D249 queue visibility on the same instance")
    object.__setattr__(arm, QV.Q2_SWITCH, True)
    arm.__dict__.pop("_q2_resolved", None)
    if QV.q2_arm_enables(arm) is not True or not arm._q2_on():             # pragma: no cover
        raise LadderSwitchError("%s did not take on the instance of %s"
                                % (QV.Q2_SWITCH, type(arm).__name__))


def _set_q2m(arm: Any) -> None:
    """Turn the q2m margin (rung 3's committed value) on for THIS INSTANCE and read it back."""
    import d261_margin_scope as _MS                                        # noqa: PLC0415
    if not (QV.arm_enables(arm) and QV.q2_arm_enables(arm)):
        raise LadderSwitchError("q2m requires D249 and q2 on the same instance")
    object.__setattr__(arm, _MS.Q2M_SWITCH, True)
    if _MS.q2m_arm_enables(arm) is not True:                               # pragma: no cover
        raise LadderSwitchError("%s did not take on the instance of %s"
                                % (_MS.Q2M_SWITCH, type(arm).__name__))


def _set_q4(arm: Any) -> None:
    """Turn the q4 avoided-rebuild credit on for THIS INSTANCE and read it back. Needs q2m."""
    import q4_avoided_rebuild as _Q4                                       # noqa: PLC0415
    import d261_margin_scope as _MS                                        # noqa: PLC0415
    if not _MS.q2m_arm_enables(arm):
        raise LadderSwitchError("q4 requires the q2m switch on the same instance")
    object.__setattr__(arm, _Q4.Q4_SWITCH, True)
    arm.__dict__.pop("_q4_resolved", None)
    if _Q4.arm_enables(arm) is not True or not arm._q4_on():              # pragma: no cover
        raise LadderSwitchError("%s did not take on the instance of %s"
                                % (_Q4.Q4_SWITCH, type(arm).__name__))


def _set_cold_unlatch(arm: Any) -> None:
    """Turn D261 (a rejection is not proof of cold) on for THIS INSTANCE and read it back.

    `coordinator.__init__` reads the SAME instance attribute through
    `d261_cold_unlatch.arm_enables`, and the coordinator is the only consumer, so a build where
    the switch is set and the consumer off is not expressible.
    """
    object.__setattr__(arm, CU.D261_SWITCH, True)
    if not CU.arm_enables(arm):                                            # pragma: no cover
        raise LadderSwitchError(
            "%s did not take on the instance of %s, so the cell would have run the latch under "
            "a name that says it clears" % (CU.D261_SWITCH, type(arm).__name__))


def make_rung3(name: str = RUNG3, *, release_recheck: bool = True,
               recheck_types: Any = RRARM.RECHECK_TYPES,
               deficit_feed: bool = True, gain: float = GAIND.GAIN,
               ordering: bool = True, split: bool = True,
               planner_reads_feed: bool = True, qcache_key_fix: bool = True,
               per_type_guard: bool = False, guard_lag_s_by_class: Any = None,
               hysteresis: Any = None, guard_log: Any = None,
               d249_queue_visibility: bool = False,
               q2_inflight_exclusion: bool = False,
               q2m_margin: bool = False,
               q4_credit: bool = False,
               cold_unlatch: Any = None,
               link_read: bool = False,
               link_sync: Any = None, link_currency: str = "acc", link_tiebreak: str = "hold",
               **kw: Any) -> Any:
    """Build rung 3. Four switches, each set on the instance and each read back.

    D230 (2) adds a fifth, `per_type_guard`, DEFAULT OFF (D187): `make_rung3()` with no
    arguments is still exactly `covex-v6-fair-final`. `guard_log` defaults to None meaning
    "follow the guard switch", so the labelled variant logs and rung 3 does not.
    """
    arm = V6FairFinal(name=name, **kw)
    if qcache_key_fix:
        _set_qcache_fix(arm)
    arm._fairfeed_init(deficit_feed=deficit_feed, gain=gain, ordering=ordering, split=split)
    object.__setattr__(arm, RR.SWITCH_ATTR, bool(release_recheck))
    if release_recheck:
        object.__setattr__(arm, RR.TYPES_ATTR, tuple(recheck_types))
    if RR.arm_enables(arm) != bool(release_recheck):                       # pragma: no cover
        raise RR.ReleaseRecheckSwitchError(
            "%s did not take on the instance of %s" % (RR.SWITCH_ATTR, type(arm).__name__))
    if release_recheck and tuple(RR.types_for(arm)) != tuple(recheck_types):  # pragma: no cover
        raise RR.ReleaseRecheckSwitchError(
            "%s did not take: reads %r" % (RR.TYPES_ATTR, RR.types_for(arm)))
    # the prerequisite the COORDINATOR refuses on, checked at construction so the failure lands in
    # a proof and not 80 s into a live cell
    if release_recheck and not bool(vars(arm).get("live2_d162_pricing")):  # pragma: no cover
        raise RRARM.PrerequisiteNotMet(
            "%s enables %s without live2_d162_pricing, which the coordinator refuses"
            % (name, RR.SWITCH_ATTR))
    # D230 (2) / D178 (3). After `_fairfeed_init`, so `_rules` exists to be switched.
    if per_type_guard:
        _set_per_type_guard(arm, guard_lag_s_by_class)
    # D231 (3): the variant carries BOTH halves of freeze-gate row 10.7. `hysteresis=None`
    # means "follow the per-type switch", so `covex-v6-fair-final-ptg` latches and
    # `covex-v6-fair-final` does not; an explicit False is how the Step 4 controls separate
    # the two mechanisms.
    if (per_type_guard if hysteresis is None else bool(hysteresis)):
        _set_hysteresis(arm)
    if (per_type_guard if guard_log is None else bool(guard_log)):
        _set_guard_log(arm)
    # D249, DEFAULT OFF (the ruling): `make_rung3()` with no arguments is still exactly
    # `covex-v6-fair-final`, and the only arm that passes True is `covex-v6-fair-final-q`.
    if d249_queue_visibility:
        _set_d249(arm)
    if q2_inflight_exclusion:
        _set_q2(arm)
    if q2m_margin:
        _set_q2m(arm)
    if q4_credit:
        _set_q4(arm)
    # D261 (user ruling 2026-11-25 item 2), DEV LINE ONLY. `cold_unlatch=None` means "follow the
    # D249 switch", so `covex-v6-fair-final-q` carries it and `covex-v6-fair-final` does not:
    # `make_rung3()` with no arguments is still exactly rung 3. An explicit False is how the
    # switch-off control separates this mechanism from D249 inside ONE tree.
    if (d249_queue_visibility if cold_unlatch is None else bool(cold_unlatch)):
        _set_cold_unlatch(arm)
    arm._planner_reads_feed_declared = bool(planner_reads_feed)
    if planner_reads_feed:
        # wire it NOW rather than lazily, so a wiring failure raises in construction
        arm._cf_engine()
        if getattr(arm._planner_w_source, "IS_DECLARED_CONSTANT", True):   # pragma: no cover
            raise LadderSwitchError("the rung-3 planner limb kept the declared constant")
    if link_read:
        LR.install(arm)
    if link_sync is not None:
        LR.install(arm)
        LS.install(arm, str(link_sync), str(link_currency), str(link_tiebreak))
    return arm


# ---------------------------------------------------------------------------------------------
# rung 4

# `_ProtectDeferMixin.live2_describe` reads `arms_v6cf.BASES[self._pd_base_key]`, so the new base
# is registered there too, additively.
R4_BASE_KEY = "fair_final"
VCF.BASES.setdefault(R4_BASE_KEY, {
    "module": __name__,
    "cls": "V6Final",
    "base_arm": RUNG3,
    "why": ("rung 3 of the final ladder: the deficit feed with BOTH the ordering consumer and the "
            "state planner reading it, plus the alert release re-check"),
})


def _build_rung4_final() -> Any:
    return type("V6Final", (R4._Rung4Mixin, VCF._ProtectDeferMixin, V6FairFinal),
                {"_pd_base_key": R4_BASE_KEY,
                 "__doc__": "rung 4: %s plus both counterfactual decisions" % (RUNG3,)})


V6Final = _build_rung4_final()


def make_rung4(name: str = RUNG4, *, protect_defer: bool = True, request_defer: bool = True,
               live_weight: bool = True, release_recheck: bool = True,
               recheck_types: Any = RRARM.RECHECK_TYPES,
               deficit_feed: bool = True, gain: float = GAIND.GAIN,
               ordering: bool = True, split: bool = True,
               planner_reads_feed: bool = True, qcache_key_fix: bool = True,
               control_harm_zero: bool = False, control_margin_huge: bool = False,
               **kw: Any) -> Any:
    """Build rung 4. Rung 3's four switches plus the two counterfactual legs and the w_d wiring."""
    arm = V6Final(name=name, protect_defer=protect_defer,
                  control_harm_zero=control_harm_zero,
                  control_margin_huge=control_margin_huge, **kw)
    if qcache_key_fix:
        _set_qcache_fix(arm)
    arm._fairfeed_init(deficit_feed=deficit_feed, gain=gain, ordering=ordering, split=split)
    object.__setattr__(arm, RR.SWITCH_ATTR, bool(release_recheck))
    if release_recheck:
        object.__setattr__(arm, RR.TYPES_ATTR, tuple(recheck_types))
    if RR.arm_enables(arm) != bool(release_recheck):                       # pragma: no cover
        raise RR.ReleaseRecheckSwitchError("%s did not take" % (RR.SWITCH_ATTR,))
    # the question-deferral leg's own state and its own arm-scoped switch, exactly as rung 4's
    # committed module sets them
    arm.rd_decisions: List[Dict[str, Any]] = []
    arm.rd_nets: List[float] = []
    arm.rd_bars: List[float] = []
    arm.rd_trace_kept = None
    arm.rd_trace_crossed = None
    for obj in arm._pd_targets():
        object.__setattr__(obj, R4.RD.SWITCH_ATTR, bool(request_defer))
    if R4.RD.arm_enables(arm) != bool(request_defer):                      # pragma: no cover
        raise R4.RD.RequestDeferSwitchError("%s did not take" % (R4.RD.SWITCH_ATTR,))
    # the two legs' own w_d, the committed accessor, read back exactly as `arms_v6cfr3.make` does
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
                         "note": ("1.0 at construction is CORRECT: no opportunity has been offered "
                                  "yet, so every shortfall is 0 and every weight is at the D178 "
                                  "(2) floor. What must be true here is that the ACCESSOR is the "
                                  "live one; that the VALUE moves is a run-time property.")}
    if live_weight and not hasattr(arm, "_feed"):                          # pragma: no cover
        raise R4.WeightWiringError("live_weight was asked for and no feed is present")
    arm._planner_reads_feed_declared = bool(planner_reads_feed)
    if planner_reads_feed:
        arm._cf_engine()
        if getattr(arm._planner_w_source, "IS_DECLARED_CONSTANT", True):   # pragma: no cover
            raise LadderSwitchError("the rung-4 planner limb kept the declared constant")
    return arm


# ---------------------------------------------------------------------------------------------
# registration: ADDITIVE, and it must never shadow a committed name

FINAL_LADDER_ARMS: Dict[str, Any] = {
    RUNG2: (lambda **kw: make_rung2(RUNG2, **kw)),
    RUNG3: (lambda **kw: make_rung3(RUNG3, **kw)),
    # D230 (2): rung 3 with the D178 (3) per-type guard. The ONLY difference from RUNG3.
    RUNG3_PTG: (lambda **kw: make_rung3(RUNG3_PTG, per_type_guard=True, **kw)),
    # D249: rung 3 plus queue and harm visibility. DEFAULT OFF EVERYWHERE ELSE.
    RUNG3_D249: (lambda **kw: make_rung3(RUNG3_D249, d249_queue_visibility=True, **kw)),
    RUNG3_Q2: (lambda **kw: make_rung3(RUNG3_Q2, d249_queue_visibility=True,
                                       q2_inflight_exclusion=True, **kw)),
    RUNG3_LINK: (lambda **kw: make_rung3(RUNG3_LINK, d249_queue_visibility=True,
                                         link_read=True, **kw)),
    RUNG3_SYNC: (lambda **kw: make_rung3(RUNG3_SYNC, d249_queue_visibility=True,
                                         link_sync="ours", link_currency="acc", **kw)),
    RUNG3_SYNC_D177: (lambda **kw: make_rung3(RUNG3_SYNC_D177, d249_queue_visibility=True,
                                              link_sync="ours", link_currency="d177", **kw)),
    RUNG3_SYNC_FREE: (lambda **kw: make_rung3(RUNG3_SYNC_FREE, d249_queue_visibility=True,
                                              link_sync="ours", link_currency="d177",
                                              link_tiebreak="free", **kw)),
    RUNG3_SYNC_CTL: (lambda **kw: make_rung3(RUNG3_SYNC_CTL, d249_queue_visibility=True,
                                             link_sync="fifo", link_currency="acc", gain=0.0, **kw)),
    # CLAUDE.md Step 4 negative control, as a NAMED ARM so the control is a cell and not a
    # code edit: the per-type machinery fully live with all three thresholds set to the
    # committed single 2.0 s bar. It must collapse to `covex-v6-fair-final` EXACTLY.
    # D231 (3): this control disables BOTH mechanisms the variant adds, because the variant
    # now adds two. Thresholds at the committed 2.0 s bar AND the latch off: that is the only
    # setting that can collapse to `covex-v6-fair-final` exactly, and a control that left the
    # latch on would fail for a reason that is not the thing being controlled.
    RUNG3_PTG + "-ctl20": (lambda **kw: make_rung3(
        RUNG3_PTG + "-ctl20", per_type_guard=True, hysteresis=False,
        guard_lag_s_by_class={"episodic": 2.0, "recall": 2.0, "assistance": 2.0}, **kw)),
    # THE TWO ONE-FACTOR ARMS, so a difference against rung 3 is attributable. Addendum 12
    # item 5: "a combined count that cannot be attributed is not a pass".
    # -nohyst: the per-type THRESHOLDS alone (this is what the build was before D231 (3)).
    RUNG3_PTG + "-nohyst": (lambda **kw: make_rung3(RUNG3_PTG + "-nohyst",
                                                    per_type_guard=True, hysteresis=False,
                                                    **kw)),
    # -hystonly: the LATCH alone, over the committed 2.0 s bar on all three channels.
    RUNG3_PTG + "-hystonly": (lambda **kw: make_rung3(
        RUNG3_PTG + "-hystonly", per_type_guard=True, hysteresis=True,
        guard_lag_s_by_class={"episodic": 2.0, "recall": 2.0, "assistance": 2.0}, **kw)),
    # Proof 5's control: the variant WITHOUT the per-period log, so "adding the log does not
    # change decisions" is a cell-versus-cell comparison and not an argument from reading.
    RUNG3_PTG + "-nolog": (lambda **kw: make_rung3(RUNG3_PTG + "-nolog",
                                                   per_type_guard=True, guard_log=False, **kw)),
    # And rung 3 itself WITH the log and nothing else, which is the other half of that proof.
    RUNG3 + "-glog": (lambda **kw: make_rung3(RUNG3 + "-glog", guard_log=True, **kw)),
    RUNG4: (lambda **kw: make_rung4(RUNG4, **kw)),
}

# The committed names this module must NOT touch. `register` refuses if any of them is in its own
# key set, which is the check that makes "registered beside, never replacing" a property of the
# code rather than of a reading of it.
PROTECTED_NAMES = ("covex-v6", "covex-v6-state", "covex-v6-fair", "covex-v6-base",
                   "covex-v6-rules", "covex-v6-state-uo-c5attr", "covex-v6-fair-c5attr",
                   "covex-v6-fair-c5attr-rr", "covex-v6-cf-c5attr")


def register() -> List[str]:
    """Additive registration, with the collision check that D208 turns on."""
    import arms as A
    clash = sorted(set(FINAL_LADDER_ARMS) & set(PROTECTED_NAMES))
    if clash:                                                              # pragma: no cover
        raise LadderSwitchError(
            "the final ladder would REPLACE committed arm name(s) %r. arms.ARMS is a dict, so a "
            "second registration under a committed key re-points every reader of that arm's "
            "committed cells. D208 ruled the -final suffix for exactly this reason." % (clash,))
    before = {n: A.ARMS.get(n) for n in PROTECTED_NAMES if n in A.ARMS}
    A.ARMS.update(FINAL_LADDER_ARMS)
    after = {n: A.ARMS.get(n) for n in PROTECTED_NAMES if n in A.ARMS}
    if before != after:                                                    # pragma: no cover
        raise LadderSwitchError("registration changed a protected arm's factory")
    return sorted(FINAL_LADDER_ARMS)


ARMS = FINAL_LADDER_ARMS
