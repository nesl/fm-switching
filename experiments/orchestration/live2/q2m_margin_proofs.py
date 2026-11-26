#!/usr/bin/env python3
"""q2m unit proofs (ablation of the D259 margin). CPU only. Run: python q2m_margin_proofs.py"""
from __future__ import annotations
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for p in (HERE / "hybrid", HERE, HERE / "fleet", HERE / "v5", HERE / "tests", HERE.parent / "baselines", HERE.parent / "sim"):
    sys.path.insert(0, str(p))

import arms as A                                                               # noqa: E402
import d249_queue_visibility as QV                                             # noqa: E402
import d261_margin_scope as MS                                                 # noqa: E402

Q2M, Q2, Q, R3 = ("covex-v6-fair-final-q2m", "covex-v6-fair-final-q2", "covex-v6-fair-final-q", "covex-v6-fair-final")
FAILS = []


def check(name, ok, detail=""):
    print("%s %s %s" % ("PASS" if ok else "FAIL", name, detail))
    if not ok:
        FAILS.append(name)


def used_margin(arm):
    return arm._cf_engine()._margin().value


def main():
    check("registered", Q2M in A.ARMS or A.make_arm(Q2M) is not None)
    for n in (R3, Q, Q2, "covex-v6-state-final", "covex-v6-fair-final-notouch"):
        a = A.make_arm(n)
        check("switch OFF default on %s" % n, MS.q2m_arm_enables(a) is False)
    a = A.make_arm(Q2M)
    check("q2m ON, d249 ON, q2 ON on q2m", MS.q2m_arm_enables(a) and QV.arm_enables(a) and QV.q2_arm_enables(a))
    check("q2m override is rung 3 value 0.16456", MS.margin_override_for(a) == 0.16456, repr(MS.margin_override_for(a)))
    check("q2 override stays D259 0.0828915", MS.margin_override_for(A.make_arm(Q2)) == 0.0828915)
    check("q override stays D259", MS.margin_override_for(A.make_arm(Q)) == 0.0828915)
    check("rung3 override None", MS.margin_override_for(A.make_arm(R3)) is None)
    check("D259 constants untouched", MS.MARGIN_CF_D259_METHOD_A == 0.0828915 and MS.MARGIN_CF_ON_TIME_D259_METHOD_A == 0.331566)
    check("q2m on-time/correctness relation", abs(MS.MARGIN_CF_Q2M_RUNG3 / 0.25 - MS.MARGIN_CF_ON_TIME_Q2M_RUNG3) < 1e-9)
    m2m, m2, m3 = used_margin(a), used_margin(A.make_arm(Q2)), used_margin(A.make_arm(R3))
    check("planner READ q2m on-time 0.65824", abs(m2m - 0.65824) < 1e-9, repr(m2m))
    check("planner READ q2 on-time 0.331566", abs(m2 - 0.331566) < 1e-9, repr(m2))
    check("planner READ rung3 on-time 0.65824", abs(m3 - 0.65824) < 1e-9, repr(m3))
    check("q2m planner source is the scorable override", a._cf_engine()._margin().scorable is True)
    # class attribute raises
    r = A.make_arm(R3)
    k = type(r)
    setattr(k, MS.Q2M_SWITCH, True)
    try:
        MS.q2m_arm_enables(r); raised = False
    except MS.Q2MSwitchError:
        raised = True
    finally:
        delattr(k, MS.Q2M_SWITCH)
    check("class attribute raises", raised)
    b = A.make_arm(Q2)
    object.__setattr__(b, MS.Q2M_SWITCH, 1)
    try:
        MS.q2m_arm_enables(b); raised = False
    except MS.Q2MSwitchError:
        raised = True
    check("non-bool raises", raised)
    c = A.make_arm(Q)
    object.__setattr__(c, MS.Q2M_SWITCH, True)
    try:
        MS.margin_override_for(c); raised = False
    except MS.Q2MSwitchError:
        raised = True
    check("q2m without q2 raises", raised)
    print("FAILS:", FAILS)
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
