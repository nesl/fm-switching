#!/usr/bin/env python3
"""StudyORACLE LP core (CPU only, read-only; no images). The provable upper-bound transportation LP
from reports/study_oracle.md, with a self-contained unit test. This file is the LP MACHINERY ONLY;
it emits NO oracle bound. The per-type valuations (recall/single-shot acc_cloud-acc_device, dashcam
max-over-subsets per D197) and the per-arm shares + clustered bootstrap are built on top of this and
are NOT written to reports/figures/oracle_results.json until each is verified, per the pre-reg.

The LP (pre-reg "The LP"): units u with value v_u, best-case work W_u (tokens, the warm-prefix W_q,
Stage 1/2 verified), and a window [a_u, d_u] = [arrival, deadline - net]. One shared capacity of T
tokens per second, preemptible and arbitrarily splittable:

    maximize   sum_u v_u * x_u
    s.t.       sum_t f_{u,t} = W_u * x_u          (work served if admitted)
               sum_u f_{u,t} <= T * width_t       (capacity per time slot)
               f_{u,t} = 0 for t outside u window (deadline)
               0 <= x_u <= 1

Time is discretized at the EVENT BREAKPOINTS (sorted distinct arrivals and deadlines), so the slot
count is O(n_units) and variables exist only where a unit's window overlaps a slot. Solved with
HiGHS (scipy.optimize.linprog). This is a relaxation of any real schedule (R1-R4 in the pre-reg), so
LP_opt >= integer_opt >= any realizable schedule.
"""
from __future__ import annotations
import sys
from dataclasses import dataclass
from typing import List
import numpy as np
from scipy.optimize import linprog


@dataclass
class Unit:
    uid: str
    value: float          # v_u (FAIR gain or HINDSIGHT gain; may be <= 0, then never served)
    work: float           # W_u tokens (best-case warm-prefix)
    release: float        # a_u seconds
    deadline: float       # d_u seconds (already net-adjusted)


def solve_oracle_lp(units: List[Unit], T: float, dt_cap: float = None):
    """Maximize served value under one preemptible capacity T tok/s. Returns dict with lp_value,
    per-unit x_u, status, and whether capacity binds (Step 2b)."""
    # negative-value units are never served (pre-reg): drop them, they contribute 0.
    pos = [u for u in units if u.value > 0 and u.work > 0 and u.deadline > u.release]
    if not pos:
        return {"lp_value": 0.0, "x": {u.uid: 0.0 for u in units}, "status": "trivial_no_units",
                "capacity_binds": False, "n_units": len(units), "n_served_units": 0}
    # event breakpoints
    bps = sorted(set([u.release for u in pos] + [u.deadline for u in pos]))
    slots = [(bps[i], bps[i + 1]) for i in range(len(bps) - 1)]
    slot_w = np.array([b - a for a, b in slots])
    nslot = len(slots)
    # variable layout: x_u (len P) then f_{u,s} for in-window slots (sparse index map)
    P = len(pos)
    fidx = {}
    col = P
    for ui, u in enumerate(pos):
        for si, (a, b) in enumerate(slots):
            if a >= u.release - 1e-9 and b <= u.deadline + 1e-9:
                fidx[(ui, si)] = col
                col += 1
    ncol = col
    # objective: maximize sum v_u x_u  -> minimize -v
    c = np.zeros(ncol)
    for ui, u in enumerate(pos):
        c[ui] = -u.value
    # equality: sum_s f_{u,s} - W_u x_u = 0  for each u
    Aeq_rows, Aeq_data = [], []
    beq = []
    for ui, u in enumerate(pos):
        row = np.zeros(ncol)
        row[ui] = -u.work
        for si in range(nslot):
            if (ui, si) in fidx:
                row[fidx[(ui, si)]] = 1.0
        Aeq_rows.append(row)
        beq.append(0.0)
    # capacity: sum_u f_{u,s} <= T * width_s  for each slot
    Aub_rows, bub = [], []
    for si in range(nslot):
        row = np.zeros(ncol)
        any_in = False
        for ui in range(P):
            if (ui, si) in fidx:
                row[fidx[(ui, si)]] = 1.0
                any_in = True
        if any_in:
            Aub_rows.append(row)
            bub.append(T * slot_w[si])
    bounds = [(0.0, 1.0)] * P + [(0.0, None)] * (ncol - P)
    res = linprog(c, A_ub=np.array(Aub_rows) if Aub_rows else None,
                  b_ub=np.array(bub) if bub else None,
                  A_eq=np.array(Aeq_rows), b_eq=np.array(beq),
                  bounds=bounds, method="highs")
    if not res.success:
        return {"lp_value": None, "status": "LP_FAILED: " + res.message, "capacity_binds": None,
                "n_units": len(units)}
    x = {u.uid: float(round(res.x[ui], 9)) for ui, u in enumerate(pos)}
    for u in units:
        x.setdefault(u.uid, 0.0)
    lp_value = float(-res.fun)
    # Step 2b: does capacity bind? A slot binds if its flow hits T*width (dual > 0 or slack ~0).
    binds = False
    if Aub_rows:
        flows = np.array(Aub_rows) @ res.x
        caps = np.array(bub)
        binds = bool(np.any(flows >= caps - 1e-6 * np.maximum(1.0, caps)))
    return {"lp_value": round(lp_value, 6), "x": x, "status": "optimal",
            "capacity_binds": binds, "n_units": len(units),
            "n_served_units": int(sum(1 for v in x.values() if v > 1e-9))}


def greedy_edf(units: List[Unit], T: float):
    """Constructive feasible LOWER bound: serve in deadline order, each unit fully if its work fits
    in the remaining capacity of its window at rate T; skip otherwise. Realized served value."""
    pos = sorted([u for u in units if u.value > 0 and u.work > 0 and u.deadline > u.release],
                 key=lambda u: u.deadline)
    bps = sorted(set([u.release for u in pos] + [u.deadline for u in pos]))
    slots = [(bps[i], bps[i + 1]) for i in range(len(bps) - 1)]
    cap = {i: T * (b - a) for i, (a, b) in enumerate(slots)}
    served = 0.0
    for u in pos:
        need = u.work
        win = [i for i, (a, b) in enumerate(slots)
               if a >= u.release - 1e-9 and b <= u.deadline + 1e-9]
        avail = sum(cap[i] for i in win)
        if avail + 1e-9 >= need:
            for i in win:
                take = min(cap[i], need)
                cap[i] -= take
                need -= take
                if need <= 1e-9:
                    break
            served += u.value
    return round(served, 6)


def _unit_test():
    """Hand-checkable cases proving the LP maximizes served value under capacity and deadlines."""
    ok = True
    # Case 1: one slot of width 1 s, capacity T=100 tok. Two units, each work 100, values 3 and 1,
    # both in [0,1]. Only 100 tokens available -> serve the value-3 unit fully (x=1), the value-1
    # unit gets the leftover 0 -> lp_value = 3.0 exactly.
    u = [Unit("hi", 3.0, 100, 0, 1), Unit("lo", 1.0, 100, 0, 1)]
    r = solve_oracle_lp(u, T=100.0)
    exp = 3.0
    print(f"case1 lp_value={r['lp_value']} expect {exp} served={r['n_served_units']} binds={r['capacity_binds']}")
    ok &= abs(r["lp_value"] - exp) < 1e-6 and r["capacity_binds"]
    # Case 2: capacity 300 > total work 200 -> both fit fully -> 4.0, with real slack (NOT binding).
    r2 = solve_oracle_lp(u, T=300.0)
    print(f"case2 lp_value={r2['lp_value']} expect 4.0 binds={r2['capacity_binds']} (expect False)")
    ok &= abs(r2["lp_value"] - 4.0) < 1e-6 and not r2["capacity_binds"]
    # Case 3: fractional - one slot width 1, T=150, two value-1 units each work 100. Total work 200
    # but only 150 available -> serve x summing to 1.5 -> lp_value 1.5.
    u3 = [Unit("a", 1.0, 100, 0, 1), Unit("b", 1.0, 100, 0, 1)]
    r3 = solve_oracle_lp(u3, T=150.0)
    print(f"case3 lp_value={r3['lp_value']} expect 1.5")
    ok &= abs(r3["lp_value"] - 1.5) < 1e-6
    # Case 4: disjoint windows do not compete. Two units, work 100 each, T=100, windows [0,1] and
    # [1,2] -> both fully served -> 2.0 (greedy equals LP here).
    u4 = [Unit("x", 1.0, 100, 0, 1), Unit("y", 1.0, 100, 1, 2)]
    r4 = solve_oracle_lp(u4, T=100.0)
    g4 = greedy_edf(u4, T=100.0)
    print(f"case4 lp_value={r4['lp_value']} greedy={g4} expect 2.0 both")
    ok &= abs(r4["lp_value"] - 2.0) < 1e-6 and abs(g4 - 2.0) < 1e-6
    # Case 5: greedy <= LP always (relaxation). Case1: greedy serves only 'hi' (3.0) <= lp 3.0.
    g1 = greedy_edf(u, T=100.0)
    print(f"case5 greedy(case1)={g1} <= lp 3.0 : {g1 <= 3.0 + 1e-9}")
    ok &= g1 <= 3.0 + 1e-9
    # Case 6: negative-value unit is never served.
    u6 = [Unit("neg", -1.0, 50, 0, 1), Unit("pos", 2.0, 50, 0, 1)]
    r6 = solve_oracle_lp(u6, T=100.0)
    print(f"case6 lp_value={r6['lp_value']} expect 2.0 (neg dropped) served={r6['n_served_units']}")
    ok &= abs(r6["lp_value"] - 2.0) < 1e-6 and r6["n_served_units"] == 1
    print("UNIT TEST:", "PASS" if ok else "*** FAIL ***")
    return ok


if __name__ == "__main__":
    sys.exit(0 if _unit_test() else 1)
