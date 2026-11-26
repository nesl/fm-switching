#!/usr/bin/env python3
"""q5c registration proofs: `-q5c` = `-q5b` + the EXISTING D261 switch, nothing else. CPU only."""
from __future__ import annotations
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for p in (HERE / "hybrid", HERE, HERE / "fleet", HERE / "v5", HERE / "tests", HERE.parent / "baselines", HERE.parent / "sim"):
    sys.path.insert(0, str(p))
import arms as A                                                               # noqa: E402
import d261_cold_unlatch as CU                                                 # noqa: E402
import q5_queue_aware_holdback as Q5                                           # noqa: E402

FAILS = []


def check(name, ok, detail=""):
    print("%s %s %s" % ("PASS" if ok else "FAIL", name, detail))
    if not ok:
        FAILS.append(name)


def main():
    c = A.make_arm("covex-v6-fair-final-q5c")
    b = A.make_arm("covex-v6-fair-final-q5b")
    check("q5c: D261, q5, q5b all ON", CU.arm_enables(c) and Q5.arm_enables(c) and Q5.q5b_arm_enables(c))
    check("q5b: D261 OFF, q5 and q5b ON", not CU.arm_enables(b) and Q5.q5b_arm_enables(b))
    check("q5c and q5b are one class", type(c) is type(b))
    check("q5c keeps D249, q2, q2m and q4 OFF (rung 3 touch logic)",
          not any(getattr(c, a, False) is True for a in ("live2_d249_queue_visibility", "live2_q2_inflight_exclusion",
                                                           "live2_q2m_rung3_margin", "live2_q4_avoided_rebuild_credit")))
    check("q5c margin is rung 3's 0.65824", abs(c._cf_engine()._margin().value - 0.65824) < 1e-9)
    for n in ("covex-v6-fair-final", "covex-v6-fair-final-q5", "covex-v6-fair-final-q5b"):
        check("D261 OFF on %s" % n, CU.arm_enables(A.make_arm(n)) is False)
    for n in ("covex-v6-fair-final-q", "covex-v6-fair-final-q2m"):
        check("D261 still ON on %s" % n, CU.arm_enables(A.make_arm(n)) is True)
    check("D261 module constants unchanged", CU.RESTORABLE_TIERS == ("gpu", "host") and CU.D261_SWITCH == "live2_d261_cold_unlatch")
    print("FAILS:", FAILS)
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
