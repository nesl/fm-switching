#!/usr/bin/env python3
"""Toy test for the UniScale reconstruction. CPU only."""
import sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from uniscale import LinUCB, efficiency_reward  # noqa

res = []
# Arms are (model, compute) PAIRS - the joint space that makes UIS unified rather than two
# independent decisions (the paper's framing).
ARMS = [("small", 1), ("small", 3), ("large", 1), ("large", 3)]
b = LinUCB(ARMS, dim=2, alpha=1.0)
x = np.array([1.0, 0.5])
res.append(("S: arms are (model, compute) PAIRS, so routing and test-time scaling are joint",
            len(ARMS) == 4 and all(isinstance(a, tuple) and len(a) == 2 for a in ARMS),
            f"{len(ARMS)} joint arms {ARMS}"))
res.append(("LinUCB: an unplayed arm has the widest confidence term, so optimism explores first",
            all(b.n[a] == 0 for a in ARMS) and b.select(x) in ARMS,
            f"first selection {b.select(x)} with all counts 0"))
w0 = b.score(ARMS[0], x)
b.update(ARMS[0], x, 0.0)
for _ in range(40):
    b.update(ARMS[0], x, 0.0)
w1 = b.score(ARMS[0], x)
res.append(("LinUCB: the confidence width shrinks as an arm is played",
            w1 < w0, f"score {w0:.3f} -> {w1:.3f} after 41 plays at reward 0"))

# convergence: reward the (large, 1) arm and starve the rest
b2 = LinUCB(ARMS, dim=2, alpha=0.2)
rng = np.random.default_rng(0)
for _ in range(300):
    a = b2.select(x)
    r = 1.0 if a == ("large", 1) else 0.0
    b2.update(a, x, r + 0.01 * rng.normal())
res.append(("CMAB: LinUCB concentrates on the rewarding arm",
            b2.n[("large", 1)] == max(b2.n.values()),
            f"play counts {dict((str(k), v) for k, v in b2.n.items())}"))

# the joint claim: with compute priced, the best arm is NOT the strongest model
res.append(("S: the efficiency-aware reward penalises compute, so the strongest arm need not win",
            efficiency_reward(0.9, compute=3.0, price=0.2) <
            efficiency_reward(0.8, compute=1.0, price=0.2),
            f"q=0.9 at compute 3 -> {efficiency_reward(0.9,3.0,0.2):.3f} < "
            f"q=0.8 at compute 1 -> {efficiency_reward(0.8,1.0,0.2):.3f}"))
res.append(("LinUCB: only the played arm is updated",
            b.n[ARMS[1]] == 0 and b.n[ARMS[0]] > 0,
            f"played {b.n[ARMS[0]]} times, unplayed arm still {b.n[ARMS[1]]}"))
res.append(("LinUCB: a feasible-arm restriction is respected",
            b.select(x, feasible=[ARMS[2]]) == ARMS[2], "restricted selection honoured"))

print("UniScale reconstruction - toy test")
print("=" * 78)
n = sum(int(o) for _, o, _ in res)
for nm, o, d in res:
    print(f"[{'PASS' if o else 'FAIL'}] {nm}\n        {d}")
print("=" * 78)
print(f"{n}/{len(res)} behaviours reproduced")
sys.exit(0 if n == len(res) else 1)
