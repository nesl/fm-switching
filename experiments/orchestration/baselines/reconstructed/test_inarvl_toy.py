#!/usr/bin/env python3
"""Toy test for the INAR-VL reconstruction, in the paper's own abstract setting. CPU only."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from inarvl import Candidate, DESCRIPTOR_FIELDS, fuse, pareto_frontier, predicted_quality, route  # noqa

res = []
# The paper's own measured operating points (Section 2.1 / abstract): edge-only 66.5 % at 824 ms
# and 7.5 J; cloud-only 74.4 % at 2408 ms and 26.0 J.
EDGE = Candidate("edge-2B", "edge", blur_robustness=0.4, detail_ocr=0.5, reasoning=0.4,
                 latency_s=0.824, energy_j=7.5)
CLOUD = Candidate("cloud-32B", "cloud", blur_robustness=0.9, detail_ocr=0.9, reasoning=0.95,
                  latency_s=2.408, energy_j=26.0)

# ---- stage (3): the descriptor r has exactly the paper's 10 dimensions.
r = fuse(dict(blur=0.1, exposure=0.5, artifact=0.0, detail=0.2),
         dict(length=0.2, entity_numeric_density=0.1, question_type=0.0,
              vocabulary_complexity=0.1, reasoning_markers=0.0, context_dependency=0.0))
res.append(("S3 stage (3): the fused request descriptor r is 10-dimensional",
            len(r) == 10 == len(DESCRIPTOR_FIELDS), f"len(r) = {len(r)}"))

# ---- stage (4): the quality predictor uses the three strength descriptors, so the cloud model
#      (stronger on all three) never scores below the edge model on the same input.
res.append(("S3 stage (4): a uniformly stronger model predicts at least as much quality",
            predicted_quality(r, CLOUD) >= predicted_quality(r, EDGE),
            f"q(cloud) {predicted_quality(r, CLOUD):.3f} >= q(edge) {predicted_quality(r, EDGE):.3f}"))

# ---- stage (5): an EASY input (sharp, low reasoning demand) stays on the edge when the quality
#      floor is met -- "the system prioritizes edge execution when the predicted quality is
#      sufficient".
c, q, why = route(r, [EDGE, CLOUD], quality_floor=0.3, gain_per_second=1.0, gain_per_joule=0.01)
res.append(("S3 stage (5): an easy input is kept on the edge when the quality floor is met",
            c.placement == "edge", f"chose {c.name} ({why})"))

# ---- stage (5): a HARD input (blurred, reasoning-heavy) raises the cloud's predicted gain, so
#      it offloads -- "otherwise offloads to the cloud only if the expected quality gain
#      justifies the additional cost".
r_hard = fuse(dict(blur=0.9, exposure=0.3, artifact=0.6, detail=0.9),
              dict(length=0.9, entity_numeric_density=0.8, question_type=1.0,
                   vocabulary_complexity=0.9, reasoning_markers=1.0, context_dependency=0.9))
c2, q2, why2 = route(r_hard, [EDGE, CLOUD], quality_floor=0.8, gain_per_second=0.05,
                     gain_per_joule=0.001)
res.append(("S3 stage (5): a hard input offloads when the gain justifies the cost",
            c2.placement == "cloud", f"chose {c2.name} ({why2})"))

# ---- stage (5): the SAME hard input stays local when latency and energy are priced high -- the
#      cost term is what makes the router input-aware rather than accuracy-greedy.
c3, _q3, why3 = route(r_hard, [EDGE, CLOUD], quality_floor=0.8, gain_per_second=10.0,
                      gain_per_joule=1.0)
res.append(("S3 stage (5): the same input stays on the edge when latency / energy are priced high",
            c3.placement == "edge", f"chose {c3.name} ({why3})"))

# ---- stage (4): the Pareto frontier drops a candidate dominated on all three axes.
WORSE = Candidate("cloud-worse", "cloud", 0.1, 0.1, 0.1, latency_s=3.0, energy_j=40.0)
front = [c.name for c, _ in pareto_frontier([EDGE, CLOUD, WORSE], r)]
res.append(("S3 stage (4): a dominated candidate is pruned from the Pareto frontier",
            "cloud-worse" not in front, f"frontier {front}"))

print("INAR-VL reconstruction - toy test in the paper's abstract setting")
print("=" * 78)
n = sum(int(o) for _, o, _ in res)
for nm, o, d in res:
    print(f"[{'PASS' if o else 'FAIL'}] {nm}\n        {d}")
print("=" * 78)
print(f"{n}/{len(res)} behaviours reproduced")
sys.exit(0 if n == len(res) else 1)
