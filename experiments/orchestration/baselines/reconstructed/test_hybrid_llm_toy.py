#!/usr/bin/env python3
"""Toy test for the Hybrid LLM reconstruction, in the paper's own abstract setting. CPU only."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hybrid_llm import (HybridRouter, bce_loss, best_t, label_det, label_prob,  # noqa
                        quality_gap, transform_labels)

rng = np.random.default_rng(0)
res = []

# A toy population: one feature x drives the quality gap. Small model wins for low x.
n = 400
X = rng.uniform(0, 1, size=(n, 1))
gap_mean = 0.5 - X[:, 0]                       # H(x) > 0 for x < 0.5
qs_samples = [rng.normal(0.5 + g, 0.25, 10) for g in gap_mean]
ql_samples = [rng.normal(0.5, 0.25, 10) for _ in gap_mean]
q_small = np.array([s[0] for s in qs_samples])
q_large = np.array([l[0] for l in ql_samples])

# ---- behaviour 1: Section 3 -- the quality gap is the difference of the two qualities.
res.append(("S3: H(x) = q(S(x)) - q(L(x))",
            np.allclose(quality_gap(q_small, q_large), q_small - q_large),
            "definition reproduced elementwise"))

# ---- behaviour 2: Sections 3.1-3.2 -- y^det is a HIGHER-VARIANCE estimate of the same
#      expectation that y^prob estimates ("the hard label y^det is a higher-variance estimate").
yd, yp = label_det(q_small, q_large), label_prob(qs_samples, ql_samples)
ok2 = yd.var() > yp.var() and abs(yd.mean() - yp.mean()) < 0.1
res.append(("S3.1 vs S3.2: y^det has higher variance than y^prob at a similar mean",
            ok2, f"var {yd.var():.4f} vs {yp.var():.4f}; mean {yd.mean():.3f} vs {yp.mean():.3f}"))

# ---- behaviour 3: Section 3.3 / Figure 4 -- the transformation makes the label distribution
#      "significantly more balanced", i.e. pushes labels away from the middle.
t = best_t(yp)
yt = transform_labels(yp, t)
ok3 = np.abs(yt - 0.5).mean() >= np.abs(yp - 0.5).mean() - 1e-12
res.append(("S3.3 / Fig 4 / Eq (3): the transformation spreads labels away from 0.5",
            ok3, f"t* = {t:.2f}; mean |y - 0.5| {np.abs(yp-0.5).mean():.3f} -> "
                 f"{np.abs(yt-0.5).mean():.3f}"))

# ---- behaviour 4: Section 3 -- the router's score estimates Pr[H(x) >= 0], so it must be
#      DECREASING in x in this population (small model wins at low x).
r = HybridRouter("prob").fit(X, q_small, q_large, qs_samples, ql_samples)
p_lo = r.predict(np.array([[0.1]]))[0]
p_hi = r.predict(np.array([[0.9]]))[0]
ok4 = p_lo > p_hi
res.append(("S3: p_w(x) tracks Pr[H(x) >= 0], high where the small model wins",
            ok4, f"p(x=0.1) = {p_lo:.3f} > p(x=0.9) = {p_hi:.3f}"))

# ---- behaviour 5: the routing threshold is the cost knob -- raising it sends LESS traffic to
#      the small model, which is the cost-quality trade-off the paper sweeps (Section 4).
fracs = [r.route(X, th).mean() for th in (0.2, 0.5, 0.8)]
ok5 = fracs[0] >= fracs[1] >= fracs[2]
res.append(("S4: the threshold is monotone in the small-model traffic share",
            ok5, "small-model share at thresholds 0.2/0.5/0.8 = "
                 + "/".join(f"{f:.2f}" for f in fracs)))

# ---- behaviour 6: Equations (1)/(2)/(4) are one BCE with three labels; a perfect predictor
#      attains a lower loss than a constant one.
ok6 = bce_loss(yd, np.clip(yd, 1e-6, 1 - 1e-6)) < bce_loss(yd, np.full(n, 0.5))
res.append(("Eq (1)/(2)/(4): BCE rewards a correct predictor over a constant",
            ok6, "perfect < constant-0.5 loss"))

print("Hybrid LLM reconstruction - toy test in the paper's abstract setting")
print("=" * 78)
npass = sum(int(ok) for _, ok, _ in res)
for nm, ok, d in res:
    print(f"[{'PASS' if ok else 'FAIL'}] {nm}\n        {d}")
print("=" * 78)
print(f"{npass}/{len(res)} behaviours reproduced")
sys.exit(0 if npass == len(res) else 1)
