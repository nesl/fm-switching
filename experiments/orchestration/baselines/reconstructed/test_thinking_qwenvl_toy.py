#!/usr/bin/env python3
"""Toy test for the ATDM (Thinking-QwenVL) reconstruction. CPU only."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from thinking_qwenvl import atdm, t_star  # noqa

res = []
d = atdm(progress=0.2, confidence=0.9, progress_threshold=0.6, confidence_threshold=0.6)
res.append(("S: ATDM waits when PROGRESS is insufficient, and says so",
            (not d.answer_now) and "progress" in d.reason, f"reason: {d.reason}"))
d2 = atdm(0.9, 0.2, 0.6, 0.6)
res.append(("S: ATDM waits when CONFIDENCE is insufficient, and says so",
            (not d2.answer_now) and "confidence" in d2.reason, f"reason: {d2.reason}"))
d3 = atdm(0.9, 0.9, 0.6, 0.6)
res.append(("S: ATDM answers only when BOTH observable quantities are sufficient",
            d3.answer_now and "both sufficient" in d3.reason, f"reason: {d3.reason}"))

prog = [0.1, 0.3, 0.5, 0.7, 0.9]
conf = [0.2, 0.4, 0.7, 0.8, 0.9]
times = [1.0, 2.0, 3.0, 4.0, 5.0]
t, trace = t_star(prog, conf, times, 0.6, 0.6)
res.append(("S: t* is the FIRST timestamp at which sufficient evidence has appeared",
            t == 4.0, f"t* = {t} s (progress/confidence first clear 0.6/0.6 at t = 4 s)"))
res.append(("S: every step of the decision is externalised - the paper's transparency claim",
            len(trace) == len(times) and all(x.reason for x in trace),
            f"{len(trace)} decisions, all carrying a reason"))
t_none, _ = t_star([0.1] * 5, [0.1] * 5, times, 0.6, 0.6)
res.append(("S: with evidence never sufficient, ATDM never commits",
            t_none is None, f"t* = {t_none}"))
res.append(("S: raising the thresholds delays t*",
            (t_star(prog, conf, times, 0.85, 0.85)[0] or 99) > t,
            f"t* at thresholds 0.85 = {t_star(prog, conf, times, 0.85, 0.85)[0]} s > {t} s"))

print("ATDM / Thinking-QwenVL reconstruction - toy test")
print("=" * 78)
n = sum(int(o) for _, o, _ in res)
for nm, o, d_ in res:
    print(f"[{'PASS' if o else 'FAIL'}] {nm}\n        {d_}")
print("=" * 78)
print(f"{n}/{len(res)} behaviours reproduced")
sys.exit(0 if n == len(res) else 1)
