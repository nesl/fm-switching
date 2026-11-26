#!/usr/bin/env python3
"""`-unlatch` registration proofs: rung 3 + ONLY the D261 switch. CPU only."""
from __future__ import annotations
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for p in (HERE / "hybrid", HERE, HERE / "fleet", HERE / "v5", HERE / "tests", HERE.parent / "baselines", HERE.parent / "sim"):
    sys.path.insert(0, str(p))
import arms as A                                                               # noqa: E402
import d261_cold_unlatch as CU                                                 # noqa: E402

FAILS = []


def check(name, ok, detail=""):
    print("%s %s %s" % ("PASS" if ok else "FAIL", name, detail))
    if not ok:
        FAILS.append(name)


def main():
    u = A.make_arm("covex-v6-fair-final-unlatch")
    r = A.make_arm("covex-v6-fair-final")
    check("D261 ON on unlatch, OFF on rung 3", CU.arm_enables(u) is True and CU.arm_enables(r) is False)
    check("same class as rung 3", type(u) is type(r))
    sw = ("live2_d249_queue_visibility", "live2_q2_inflight_exclusion", "live2_q2m_rung3_margin",
          "live2_q4_avoided_rebuild_credit", "live2_q4b_next_question_basis", "live2_q4c_c5attr_touch_warm",
          "live2_q5_queue_aware_holdback", "live2_q5b_released_piece_pricing")
    check("D249 and every q switch OFF", not any(vars(u).get(s, False) for s in sw), repr([s for s in sw if vars(u).get(s)]))
    check("belief_apply ON (as rung 3's)", bool(getattr(u, "live2_belief_apply", False)) and bool(getattr(r, "live2_belief_apply", False)))
    check("margin 0.65824 (rung 3 default)", abs(u._cf_engine()._margin().value - 0.65824) < 1e-9)
    simple = lambda d: {k: v for k, v in d.items() if k != "name" and isinstance(v, (bool, int, float, str, type(None)))}
    ud, rd = simple(vars(u)), simple(vars(r))
    diff = sorted(k for k in set(ud) | set(rd) if repr(ud.get(k)) != repr(rd.get(k)) and k not in ("_cf", "_planner_w_source"))
    check("scalar instance attributes differ from rung 3 only by the D261 switch", diff == ["live2_d261_cold_unlatch"], repr(diff))
    print("FAILS:", FAILS)
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
