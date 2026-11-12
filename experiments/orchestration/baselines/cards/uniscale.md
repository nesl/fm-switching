<!-- StudyB-baselines (addendum). FAITHFUL = unchanged from the original; ADAPTATION = changed, with its reason. Fairness rules 1-6 of the addendum hold for this baseline and are checked by `interface.check_fairness` and the smoke harness. -->
# UniScale (arXiv:2605.30898) — case D, P1

**Paper.** K. Huang, X. Wang, M. Kong, Z. Shi et al., "UniScale: Adaptive Unified Inference
Scaling via Online Joint Optimization of Model Routing and Test-Time Scaling", arXiv:2605.30898
(29 May 2026). **The arXiv id is verified; the ICML 2026 venue the addendum gives could NOT be
verified in an index and is flagged.**

**Code.** None found. **Case D.**

**Files.** `reconstructed/uniscale.py`, `reconstructed/test_uniscale_toy.py`,
`uniscale_adapted.py`. **Experiments:** A-episodic, C-mixed.

## The paper's algorithm

Its framing: model routing and test-time scaling are "two largely independent dimensions", and
UniScale unifies them ("Unified Inference Scaling"), "model[ling] adaptive UIS as a contextual
multi-armed bandit problem" and learning "inference policies via **LinUCB**", with an
efficiency-aware reward.

## Mapping

| paper | our code | note |
|---|---|---|
| LinUCB | `LinUCB` — `A_a += x xᵀ`, `b_a += r x`, `score = θᵀx + α√(xᵀA⁻¹x)`, update the played arm only | FAITHFUL |
| arms = (model, compute) pairs | our `(tier, cadence, N)` profile rows — model routing × test-time compute in one arm set | ADAPTATION A1 |
| efficiency-aware reward | `efficiency_reward(quality, compute, price)` | FAITHFUL in form |
| online learning | the bandit is updated at the NEXT epoch from the realised reward | FAITHFUL |
| test-time scaling mechanism | — | NOT REPRODUCED |

## Adaptations, with reasons

- **A1 "test-time compute" is our cadence and frame count.** The paper adjusts inference compute
  inside a fixed model (sampling, self-consistency); we have no such lever, but we do have
  cadence and N, which are compute knobs at fixed model scale. The arm set is therefore the
  product of tier and those knobs, which preserves the paper's *joint* structure.
  **Consequence: this is UniScale's optimiser on our compute axis, not its compute axis.**
- **A2 the reward's price is ours.** `compute_price = 0.02` per GPU-second is stated, not fitted;
  the paper does not print its weights.
- **A3 feasibility filter.** Arms the budget cannot afford are excluded from the selection — an
  admissibility restriction, not a change to LinUCB.

## Not reproduced, and why

Test-time scaling itself (sampling inside a model needs inference); the paper's reward weights;
its benchmark suite.

## Hyperparameters and provenance

| name | value | from |
|---|---|---|
| `alpha` | 0.5 | our own exploration constant; the paper does not print one |
| `compute_price` | 0.02 / GPU-s | our own, stated |
| context | `[1, mean device score / 12, max / 12, GPU KV fraction]` | causal observation only |
