#!/usr/bin/env python3
"""Toy test for the StreamScout reconstruction. CPU only."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from streamscout import STAGES, cascade, fit_thresholds  # noqa

res = []
res.append(("S: three increasingly informative views, recent -> uniform -> query-relevant",
            STAGES == ("recent", "uniform", "query_relevant"), f"stages {STAGES}"))

th = [0.8, 0.5, -float("inf")]
i, early = cascade([0.9, 0.0, 0.0], th)
res.append(("S: answers immediately at stage 0 when the recent glance is sufficient",
            i == 0 and early, f"answered at stage {i} ({STAGES[i]}), stopped early={early}"))
i2, _ = cascade([0.1, 0.9, 0.0], th)
res.append(("S: escalates to the uniform look-back when the glance is insufficient",
            i2 == 1, f"answered at stage {i2} ({STAGES[i2]})"))
i3, early3 = cascade([0.1, 0.1, 0.1], th)
res.append(("S: the last stage always answers - there is nowhere further to escalate",
            i3 == 2 and not early3, f"answered at stage {i3} ({STAGES[i3]})"))

# the distillation step: thresholds fitted on a TRAINING set reproduce the earliest adequate stage
train = [[0.9, 0.9, 0.9], [0.9, 0.9, 0.9], [0.2, 0.8, 0.9], [0.1, 0.2, 0.9], [0.15, 0.25, 0.9]]
earliest = [0, 0, 1, 2, 2]
fitted = fit_thresholds(train, earliest)
got = [cascade(s, fitted)[0] for s in train]
res.append(("S: thresholds distilled on a TRAINING set stop at the earliest adequate stage",
            got == earliest, f"fitted thresholds {[round(t,3) if t==t and abs(t)!=float('inf') else t for t in fitted]}; "
                             f"stages {got} vs earliest adequate {earliest}"))
res.append(("S: the final threshold is -inf so the deepest view is never skipped",
            fitted[-1] == -float("inf"), f"last threshold {fitted[-1]}"))
res.append(("S: a harder example escalates further than an easier one",
            cascade(train[0], fitted)[0] < cascade(train[3], fitted)[0],
            f"easy -> stage {cascade(train[0], fitted)[0]}, hard -> stage {cascade(train[3], fitted)[0]}"))

print("StreamScout reconstruction - toy test")
print("=" * 78)
n = sum(int(o) for _, o, _ in res)
for nm, o, d in res:
    print(f"[{'PASS' if o else 'FAIL'}] {nm}\n        {d}")
print("=" * 78)
print(f"{n}/{len(res)} behaviours reproduced")
sys.exit(0 if n == len(res) else 1)
