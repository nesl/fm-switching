#!/usr/bin/env python3
"""Toy test for the ECO-LLM reconstruction, in the paper's own abstract setting. CPU only."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ecollm import ConfigPoint, SLO, explore, select  # noqa

res = []
SPACE = [dict(model="small", retrieval="none"), dict(model="small", retrieval="rich"),
         dict(model="large", retrieval="none"), dict(model="large", retrieval="rich")]
TAB = {("small", "none"): (0.50, 0.05, 0.4), ("small", "rich"): (0.78, 0.09, 0.8),
       ("large", "none"): (0.72, 0.60, 1.6), ("large", "rich"): (0.85, 0.70, 2.4)}
pts = explore(SPACE, lambda c: TAB[(c["model"], c["retrieval"])])

res.append(("S: the configuration space is explored jointly over model AND pipeline components",
            len(pts) == 4 and all(len(p.knobs) == 2 for p in pts),
            f"{len(pts)} points, each with {len(pts[0].knobs)} knobs"))

# The paper's central claim: selecting the MODEL alone is not enough. Here small+rich (0.78)
# beats large+none (0.72) at a seventh of the cost, so a model-only router would be wrong.
def kv(p):
    return dict(p.knobs)


# a model-only router cannot change the retrieval knob, so it is stuck at "none"
best_model_only = max([p for p in pts if kv(p)["retrieval"] == "none"],
                      key=lambda p: p.quality)
best_joint, feas = select(pts, SLO(max_cost_gpu_s=0.10))
res.append(("S1/S2: joint selection beats model selection alone under a cost SLO",
            feas and best_joint.quality > best_model_only.quality,
            f"joint picked {best_joint.name} (q={best_joint.quality:.2f}, "
            f"cost={best_joint.cost_gpu_s:.2f}) vs model-only best "
            f"{best_model_only.name} (q={best_model_only.quality:.2f})"))

c, feas = select(pts, SLO(max_latency_s=1.0, max_cost_gpu_s=0.10))
res.append(("S: highest quality AMONG SLO-feasible configurations",
            feas and dict(c.knobs)["model"] == "small" and dict(c.knobs)["retrieval"] == "rich",
            f"chose {c.name}, feasible={feas}"))

c2, feas2 = select(pts, SLO(max_latency_s=0.1))
res.append(("S: with no feasible configuration, the least-violating one is chosen and flagged",
            (not feas2) and c2.latency_s == min(p.latency_s for p in pts),
            f"chose {c2.name} (latency {c2.latency_s}) with feasible={feas2}"))

tie = [ConfigPoint("a", (("k", 1),), 0.9, 0.9, 1.0), ConfigPoint("b", (("k", 2),), 0.9, 0.2, 1.0)]
c3, _ = select(tie, SLO())
res.append(("S: ties on quality break toward lower cost", c3.name == "b",
            f"chose {c3.name} at cost {c3.cost_gpu_s}"))

res.append(("S: an SLO with no constraints admits everything", SLO().feasible(pts[0]),
            "unconstrained SLO is feasible"))

print("ECO-LLM reconstruction - toy test")
print("=" * 78)
n = sum(int(o) for _, o, _ in res)
for nm, o, d in res:
    print(f"[{'PASS' if o else 'FAIL'}] {nm}\n        {d}")
print("=" * 78)
print(f"{n}/{len(res)} behaviours reproduced")
sys.exit(0 if n == len(res) else 1)
