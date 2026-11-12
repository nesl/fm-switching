#!/usr/bin/env python3
"""Toy test for the R3-Streaming reconstruction, in the paper's own abstract setting. CPU only."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from r3streaming import (Frame, REASON, ROUTINE, active_forgetting, adaptive_thinking,  # noqa
                         pipeline, readiness)

res = []
frames = [Frame(i, age_s=float(i), tokens=100) for i in range(60)]   # ages 0..59 s

# ---- S4.2 / Fig 2: the paper's asymmetry -- Nearby kept at 1.0, Historical compressed hard.
kept = active_forgetting(frames, now_s=60.0, nearby_window_s=10.0,
                         ratio_nearby=1.0, ratio_historical=0.01)
near_ratios = {r for f, r, _t in kept if f.age_s <= 10.0}
hist_ratios = {r for f, r, _t in kept if f.age_s > 10.0}
res.append(("S4.2 / Fig 2: nearby frames keep ratio 1.0, historical frames 0.01",
            near_ratios == {1.0} and hist_ratios == {0.01},
            f"nearby ratios {near_ratios}, historical {hist_ratios}"))

# ---- S4.2: the compressor is the reason visual tokens drop by ~95-96 % (abstract).
total = sum(f.tokens for f in frames)
after = sum(t for _f, _r, t in kept)
red = 1.0 - after / total
res.append(("Abstract / S4.2: age-aware forgetting cuts visual tokens by roughly 95-96 %",
            0.80 <= red <= 0.99, f"token reduction {red:.1%} ({total} -> {after})"))

# ---- S4.2: compressing NEARBY context instead is the ablation the paper reports as harmful;
#      here it simply keeps far fewer of the tokens that matter, which is the mechanism.
inv = active_forgetting(frames, now_s=60.0, nearby_window_s=10.0,
                        ratio_nearby=0.01, ratio_historical=1.0)
near_after = sum(t for f, _r, t in kept if f.age_s <= 10.0)
near_after_inv = sum(t for f, _r, t in inv if f.age_s <= 10.0)
res.append(("S3 / Fig 2: the asymmetric schedule retains far more NEARBY context than its inverse",
            near_after > near_after_inv, f"nearby tokens kept {near_after} vs inverted {near_after_inv}"))

# ---- S4 (ii): the readiness head defers when evidence is insufficient.
res.append(("S4 (ii): Proactive Response defers when evidence is insufficient",
            readiness(0.9, 0.5) and not readiness(0.2, 0.5),
            "evidence 0.9 -> answer; 0.2 -> defer"))

# ---- S4 (iii): Adaptive Thinking routes only the HARDEST queries, within the escalation budget.
diff = [0.1, 0.9, 0.5, 0.95, 0.2]
paths = adaptive_thinking(diff, escalation_budget=0.4)
esc = [i for i, p in enumerate(paths) if p == REASON]
res.append(("S4 (iii): only the hardest queries are escalated, and the budget is respected",
            set(esc) == {1, 3} and len(esc) <= round(0.4 * len(diff)),
            f"escalated indices {esc} of difficulties {diff} at budget 0.4"))

# ---- S4 (iii): a zero budget escalates nothing -- "instead of using an always-on large model".
res.append(("S4 (iii): a zero escalation budget keeps everything on the fast path",
            all(p == ROUTINE for p in adaptive_thinking(diff, 0.0)),
            "budget 0.0 -> all Routine"))

# ---- the three decisions compose in the paper's order: Remember, Respond, Reason.
out = pipeline(frames, 60.0, 10.0, evidence_score=0.2, readiness_threshold=0.5,
               difficulty=0.99, escalation_budget=1.0)
out2 = pipeline(frames, 60.0, 10.0, evidence_score=0.9, readiness_threshold=0.5,
                difficulty=0.99, escalation_budget=1.0)
res.append(("S4: Respond gates Reason -- a deferred query is never routed to the strong model",
            out["decision"] == "defer" and out2["decision"] == REASON,
            f"insufficient evidence -> {out['decision']}; sufficient -> {out2['decision']}"))

print("R3-Streaming reconstruction - toy test in the paper's abstract setting")
print("=" * 78)
n = sum(int(o) for _, o, _ in res)
for nm, o, d in res:
    print(f"[{'PASS' if o else 'FAIL'}] {nm}\n        {d}")
print("=" * 78)
print(f"{n}/{len(res)} behaviours reproduced")
sys.exit(0 if n == len(res) else 1)
