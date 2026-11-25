#!/usr/bin/env python3
"""D261: THE D259 METHOD A MARGIN, SCOPED TO `covex-v6-fair-final-q` AND TO NOTHING ELSE.

STATUS: DEV BUILD on user ruling D261 (provisional, 2026-11-25). The committed margin is
UNCHANGED for every arm. `v5/cf_margin.MARGIN_CF` keeps its committed 0.16456 and stays the one
declared constant; this module declares no name `MARGIN_CF` at module level, so
`cf_margin.margin_declaration_audit` still reports ONE declaration for the counterfactual.

WHY A SCOPE AND NOT A RE-PIN. The margin is declared in `v5/cf_margin.py` and read by many files,
so re-pinning the constant applied D259's value to EVERY arm: rung 3's touches went from 2,954 to
9,296 and its deviations moved by 6,360. D261 forbids that. The value therefore travels with the
ARM, through the planner instance that reads it, and the module constant stays the default.

THE VALUE, and both registers, because a number in the wrong register survives every arithmetic
check. D259's Method A returned the margin in ON-TIME units; the planner's own single read
(`v5/cf_planner.Counterfactual._margin`) resolves `cf_margin.MARGIN_CF` in CORRECTNESS units and
divides by `A_D2_DEV = 0.250` through `cf_objective.attainment_margin`. So the override is
declared here in CORRECTNESS units, which is the register `resolve_margin` returns, and the
planner converts it exactly as it converts the committed value. No second conversion exists.

    committed   MARGIN_CF = 0.16456     -> on-time 0.65824
    D259 (A)    MARGIN_CF = 0.0828915   -> on-time 0.331566      (0.0828915 / 0.250)

ONE SWITCH, NOT TWO. The scope is keyed on `d249_queue_visibility.arm_enables`, the same instance
attribute the queue visibility uses, so a build where the queue term is on and the margin off, or
the reverse, is not expressible. `covex-v6-fair-final-q` is the only arm that carries it.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import d249_queue_visibility as QV

# CORRECTNESS units, the register `cf_margin.resolve_margin` returns. Declared under a name that
# is NOT `MARGIN_CF`, deliberately: `cf_margin.margin_declaration_audit` parses the tree for
# module-level bindings of that exact name and a second one is a reported conflict.
MARGIN_CF_D259_METHOD_A: float = 0.0828915
MARGIN_CF_ON_TIME_D259_METHOD_A: float = 0.331566
A_D2_DEV_EXPECTED: float = 0.250

MARGIN_CF_D259_SOURCE = (
    "D259 Method A, approved at D259 and pre-committed to whatever value it returned: calibration "
    "error of the frozen `cf-ontime-d162-1.0` model on the D169 population of 476 robot questions, "
    "binned by predicted P_hat in pre-registered equal-count deciles, p90 over questions. "
    "0.0828915 in correctness units; 0.331566 in on-time units, which is 0.0828915 / A_D2_DEV.")

MARGIN_CF_D259_SCOPE = (
    "D261: this value applies to `covex-v6-fair-final-q` ONLY, through "
    "`d249_queue_visibility.arm_enables` on the arm instance. Every other arm, `_preD249` "
    "included, reads `cf_margin.MARGIN_CF` = 0.16456 unchanged.")


class D261ScopeError(RuntimeError):
    """The scoped margin was asked for in a register or a unit relation that is not the committed
    one, which would make the override and the default incomparable."""


def assert_unit_relation(a_d2_dev: float) -> float:
    """FAIL LOUD unless the on-time and correctness forms of the D259 value still stand in the
    committed `A_D2_DEV` relation. A later refit of `A_D2_DEV` would otherwise silently move the
    scoped bar while leaving both literals in place, which is the shape of the 247.5x unit trap
    `d249_queue_visibility` guards against on the queue coefficient."""
    a = float(a_d2_dev)
    if abs(a - A_D2_DEV_EXPECTED) > 1e-12:
        raise D261ScopeError(
            "A_D2_DEV has moved to %r from the committed %r, so the D259 pair "
            "(%r correctness, %r on-time) is no longer one value in two registers"
            % (a, A_D2_DEV_EXPECTED, MARGIN_CF_D259_METHOD_A, MARGIN_CF_ON_TIME_D259_METHOD_A))
    if abs(MARGIN_CF_D259_METHOD_A / a - MARGIN_CF_ON_TIME_D259_METHOD_A) > 1e-9:
        raise D261ScopeError(
            "%r / %r is not %r" % (MARGIN_CF_D259_METHOD_A, a, MARGIN_CF_ON_TIME_D259_METHOD_A))
    return MARGIN_CF_D259_METHOD_A


def margin_override_for(arm: Any) -> Optional[float]:
    """The margin this ARM's planner must use, in CORRECTNESS units, or None for the committed
    default. None is the answer for every arm but `covex-v6-fair-final-q`."""
    return MARGIN_CF_D259_METHOD_A if QV.arm_enables(arm) else None


def describe(arm: Any = None) -> Dict[str, Any]:
    on = bool(arm is not None and QV.arm_enables(arm))
    return {"switch": QV.D249_SWITCH,
            "enabled": on,
            "margin_cf_correctness_units": (MARGIN_CF_D259_METHOD_A if on else None),
            "margin_cf_on_time_units": (MARGIN_CF_ON_TIME_D259_METHOD_A if on else None),
            "default_is_the_committed_constant": True,
            "source": MARGIN_CF_D259_SOURCE,
            "scope": MARGIN_CF_D259_SCOPE}
