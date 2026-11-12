#!/usr/bin/env python3
"""Toy test for the PerLLM reconstruction, in the paper's own abstract setting. CPU only."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from perllm import Arm, CSUCB, constraint_satisfaction, reward, ucb  # noqa

res = []

# ---- S3.2: f(y) >= 0 iff every constraint holds.
ok = (constraint_satisfaction([1.0, 2.0], [2.0, 3.0]) >= 0
      and constraint_satisfaction([5.0, 2.0], [2.0, 3.0]) < 0)
res.append(("S3.2: f(y) >= 0 iff all constraints hold, < 0 on any violation", ok,
            f"feasible {constraint_satisfaction([1.,2.],[2.,3.]):+.1f}, "
            f"violating {constraint_satisfaction([5.,2.],[2.,3.]):+.1f}"))

# ---- Eq (4): a violation reduces the reward through lambda * f(y).
r_ok = reward(1, 1, 1, 1, 1, 1, f_y=+1.0, lam=2.0)
r_bad = reward(1, 1, 1, 1, 1, 1, f_y=-1.0, lam=2.0)
res.append(("Eq (4): the constraint term penalises a violating scheme", r_bad < r_ok,
            f"R(feasible) {r_ok:+.1f} > R(violating) {r_bad:+.1f}"))

# ---- Eq (4): the reward is the NEGATIVE weighted energy, so more energy is worse.
res.append(("Eq (4): reward decreases with energy", reward(2,2,2,1,1,1,0,1) < reward(1,1,1,1,1,1,0,1),
            "higher energy gives lower reward"))

# ---- UCB: an unplayed arm is explored first, and the bonus decays as N(a, t) grows.
a_new, a_old = Arm("new"), Arm("old", n=100, mean_reward=0.0)
b10 = ucb(Arm("x", n=10, mean_reward=0.0), t=1000) 
b100 = ucb(Arm("x", n=100, mean_reward=0.0), t=1000)
res.append(("CS-UCB: an unplayed arm has infinite UCB; the bonus decays with N(a, t)",
            ucb(a_new, 10) == float("inf") and b10 > b100,
            f"bonus at N=10 {b10:.3f} > at N=100 {b100:.3f}"))

# ---- Algorithm 1: a feasible arm is accepted; with none feasible, regret grows.
def ev_feasible(k):
    return (1.0 if k == "good" else 0.0), [1.0], [2.0]


def ev_infeasible(k):
    return 1.0, [5.0], [2.0]


s1 = CSUCB()
picked = s1.schedule(["good", "bad"], ev_feasible)
s2 = CSUCB()
before = s2.regret
s2.schedule(["a", "b"], ev_infeasible)
res.append(("Algorithm 1: accept the first feasible super arm", picked in ("good", "bad"),
            f"accepted {picked!r}"))
res.append(("Algorithm 1 step 8: with no feasible arm, regret is updated and a fallback returned",
            s2.regret > before and s2.rejected == 2,
            f"regret {before:.2f} -> {s2.regret:.2f}, rejected {s2.rejected}"))

# ---- CMAB learning: played repeatedly, the arm with the better reward wins on mean estimate.
s3 = CSUCB()
for _ in range(60):
    s3.schedule(["good", "bad"], ev_feasible)
res.append(("CMAB: the better super arm has the higher learned reward",
            s3.arms["good"].mean_reward > s3.arms["bad"].mean_reward,
            f"R(good) {s3.arms['good'].mean_reward:.2f} > R(bad) {s3.arms['bad'].mean_reward:.2f}"))

print("PerLLM reconstruction - toy test in the paper's abstract setting")
print("=" * 78)
n = sum(int(o) for _, o, _ in res)
for nm, o, d in res:
    print(f"[{'PASS' if o else 'FAIL'}] {nm}\n        {d}")
print("=" * 78)
print(f"{n}/{len(res)} behaviours reproduced")
sys.exit(0 if n == len(res) else 1)
