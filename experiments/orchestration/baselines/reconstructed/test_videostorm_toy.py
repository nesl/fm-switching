#!/usr/bin/env python3
"""Toy test for the VideoStorm reconstruction, in the paper's own abstract setting.

Each check names the qualitative behaviour from the paper that it reproduces. CPU only.
Run: python test_videostorm_toy.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from videostorm import (Config, Query, allocate_maxmin, allocate_maxsum, predict_lag,  # noqa
                        placement_score, utility)

T = 10.0        # scheduling horizon, seconds
CAP = 1.0       # cluster capacity, in "cores"
results = []


def mk(qid, demands, qualities, lag=0.0, lag_max=0.0, aq=1.0, al=0.1):
    return Query(qid=qid,
                 profile=[Config(f"c{i}", q, d) for i, (q, d) in enumerate(zip(qualities, demands))],
                 u_base=1.0, alpha_q=aq, alpha_min_q=0.0, alpha_l=al, lag_max_s=lag_max,
                 lag_s=lag)


# ---- behaviour 1: Equation (2), Section 6.2.1 -- "query lag accumulates over time if we
#      allocate less resources than query demand".
q = mk("a", [1.0], [0.5])
lag_under = predict_lag(q, alloc=0.25, cfg=q.profile[0], horizon_s=T)
lag_match = predict_lag(q, alloc=1.0, cfg=q.profile[0], horizon_s=T)
ok1 = lag_under > q.lag_s and abs(lag_match - q.lag_s) < 1e-9
results.append(("Eq (2), S6.2.1: lag accumulates when a_k < D_k and holds when a_k = D_k",
                ok1, f"under-allocated lag {q.lag_s} -> {lag_under:.2f} s; matched -> {lag_match:.2f} s"))

# ---- behaviour 2: Section 6.1 / Figure 6 -- "there is no bonus for lag being below L^M".
qq = mk("b", [1.0], [0.5], lag_max=5.0)
ok2 = utility(qq, 0.5, 0.0) == utility(qq, 0.5, 5.0) > utility(qq, 0.5, 10.0)
results.append(("S6.1 / Fig 6: no bonus for lag below L^M, penalty only above it",
                ok2, f"U(L=0)={utility(qq,0.5,0.0):.3f} U(L=5)={utility(qq,0.5,5.0):.3f} "
                     f"U(L=10)={utility(qq,0.5,10.0):.3f}"))

# ---- behaviour 3: Section 6.2.2 / 8.2.1 -- MaxMin "maximally improves the utility of the worst
#      query", so it beats an equal (fair) split on the MINIMUM utility.
#      Two queries: one cheap and already fine, one expensive and badly lagged.
def utils(alloc_map, qs):
    out = {}
    for qy in qs:
        a, c = alloc_map[qy.qid]
        out[qy.qid] = utility(qy, c.quality, predict_lag(qy, a, c, T))
    return out


qs = [mk("cheap", [0.1, 0.2], [0.3, 0.6], lag=0.0, lag_max=2.0),
      mk("starved", [0.5, 0.9], [0.4, 0.9], lag=20.0, lag_max=2.0)]
mm = allocate_maxmin(qs, CAP, T)
ms = allocate_maxsum(qs, CAP, T)
fair = {qy.qid: (CAP / len(qs), qy.profile[0]) for qy in qs}
for qy in qs:                                    # fair split still picks the best config it can
    a = CAP / len(qs)
    best = max(qy.profile, key=lambda c: utility(qy, c.quality, predict_lag(qy, a, c, T)))
    fair[qy.qid] = (a, best)
u_mm, u_ms, u_fair = utils(mm, qs), utils(ms, qs), utils(fair, qs)
ok3 = min(u_mm.values()) >= min(u_fair.values()) - 1e-9
results.append(("S6.2.2 / S8.2.1: MaxMin's minimum utility is at least the equal-split minimum",
                ok3, f"min MaxMin {min(u_mm.values()):.3f} vs min equal-split "
                     f"{min(u_fair.values()):.3f}"))

# ---- behaviour 4: Equations (3) vs (4) -- the defining trade-off. MaxSum maximises the TOTAL,
#      MaxMin the MINIMUM, so each should win on its own objective.
ok4 = (sum(u_ms.values()) >= sum(u_mm.values()) - 1e-9
       and min(u_mm.values()) >= min(u_ms.values()) - 1e-9)
results.append(("Eq (3) vs Eq (4): MaxSum wins on total utility, MaxMin on minimum utility",
                ok4, f"total MaxSum {sum(u_ms.values()):.3f} >= MaxMin {sum(u_mm.values()):.3f}; "
                     f"min MaxMin {min(u_mm.values()):.3f} >= MaxSum {min(u_ms.values()):.3f}"))

# ---- behaviour 5: Section 6.2.2 -- the allocation never exceeds capacity R (Eq 3 constraint).
ok5 = (sum(a for a, _ in mm.values()) <= CAP + 1e-9
       and sum(a for a, _ in ms.values()) <= CAP + 1e-9)
results.append(("Eq (3) constraint: sum_k a_k <= R in both heuristics",
                ok5, f"MaxMin spent {sum(a for a,_ in mm.values()):.2f}, "
                     f"MaxSum spent {sum(a for a,_ in ms.values()):.2f} of R = {CAP}"))

# ---- behaviour 6: Section 6.3 -- the placement score is a mean of three scores in [0, 1].
s = placement_score([1.0, 1.0], machine_util=0.2, machine_util_max=1.0,
                    query_demand=[0.3, 0.3], machine_mean_lag_max=0.5)
ok6 = 0.0 <= s <= 1.0
results.append(("S6.3: placement score is in [0, 1]", ok6, f"score {s:.3f}"))

print("VideoStorm reconstruction - toy test in the paper's abstract setting")
print("=" * 78)
npass = 0
for name, ok, detail in results:
    print(f"[{'PASS' if ok else 'FAIL'}] {name}\n        {detail}")
    npass += int(ok)
print("=" * 78)
print(f"{npass}/{len(results)} behaviours reproduced")
sys.exit(0 if npass == len(results) else 1)
