<!-- StudyB-baselines. Written for a reviewer: everything faithful to the original is marked FAITHFUL, everything we changed is marked ADAPTATION with its reason. -->
# Hybrid LLM (ICLR 2024) — case D

**Paper.** D. Ding, A. Mallick, C. Wang, R. Sim, S. Mukherjee, V. Ruhle, L. V. S. Lakshmanan,
A. H. Awadallah, "Hybrid LLM: Cost-Efficient and Quality-Aware Query Routing", *ICLR 2024*
(arXiv:2404.14618).

**Code.** None found. The paper's only GitHub reference is `microsoft/Llama-2-Onnx`, a model
repository used in its experiments, not the router. No author-endorsed release located.
**Case D.**

**Files.** `reconstructed/hybrid_llm.py`, `reconstructed/test_hybrid_llm_toy.py`,
`hybrid_llm_adapted.py`.

## The paper's algorithm

| element | where | what it says |
|---|---|---|
| quality gap | §3 | `H(x) := q(S(x)) − q(L(x))`, a random variable because responses are non-deterministic. |
| deterministic router `r_det` | §3.1, **Eq. (1)** | hard label `y^det = 1[q(S) ≥ q(L)]`, a single-sample estimate of `Pr[H ≥ 0]`; BCE loss. |
| probabilistic router `r_prob` | §3.2, **Eq. (2)** | soft label `y^prob = E[1[q(S) ≥ q(L)]]`, estimated from 10 responses per model; "the hard label `y^det` is a higher-variance estimate". |
| transformation `r_trans` | §3.3, **Eq. (3)**, **Eq. (4)** | relabel to spread the labels apart; `t* = argmax_t (1/N²) Σ_{i,i'} |y^trans_i(t) − y^trans_i'(t)|`, "solved via grid-search"; retrain with Eq. (4). |
| routing | §3, §4 | the router emits `p_w(x) ≈ Pr[H(x) ≥ 0]`; queries go to the SMALL model when it is high, and the threshold is swept to trace the cost-quality curve. |
| backbone | §4 | DeBERTa-v3-large (300M). |

## Mapping, step by step

| paper | our code | note |
|---|---|---|
| `H(x)` | `quality_gap` | FAITHFUL |
| Eq. (1) label | `label_det` | FAITHFUL |
| Eq. (2) label | `label_prob` (all-pairs indicator mean) | FAITHFUL |
| Eq. (3) `t*` grid search | `best_t` | FAITHFUL in objective |
| Eq. (4) / Eq. (1) / Eq. (2) loss | `bce_loss`, `_default_fit` (Newton on the BCE with SOFT labels) | FAITHFUL |
| routing rule | `HybridRouter.route(X, threshold)` | FAITHFUL |
| small / large model | device 4B / cloud 32B | ADAPTATION A2 |
| `q(.)` | the committed Nexar score log P(Yes) at the same moment | ADAPTATION A3 |
| features `x` | StudyD3 development-split device-trajectory features | ADAPTATION A4 |
| DeBERTa backbone | a logistic model on 6 features | ADAPTATION A5 |

## Adaptations, with reasons

- **A1 reconstruction gap G1 — the transformation's closed form.** §3.3 states the objective
  (Eq. 3) and that `t` is grid-searched, but does not print the relabelling function. We use a
  power transform about 0.5, which is monotone, one-parameter and maximises Eq. (3)'s spread —
  the paper's stated FORM. **This is the one place a shape had to be chosen, and it is flagged
  here and in the module docstring.**
- **A2/A3 models and quality.** The two tiers are our device and cloud arms; `q(.)` is the Nexar
  continuous score rather than a BART score, so `H` is computed from committed traces.
- **A4 features.** StudyD3's offset design gives the device's score at ten offsets per clip, so
  the features are trajectory statistics over the offsets ≤ the decision moment — strictly
  causal, development split only.
- **A5 backbone.** DeBERTa needs a GPU to train. The reconstruction keeps the paper's labels,
  losses and routing rule and makes the encoder pluggable; the adapted version uses a logistic
  model. **Consequence: the router's capacity is far lower than the paper's**, so this baseline
  tests the paper's *labelling and routing scheme*, not its encoder.
- **A6 `y^prob` degenerates to `y^det` here.** StudyD3 has ONE response per (clip, offset, arm),
  so the 10-sample expectation of Eq. (2) is unavailable and `r_prob` / `r_trans` receive the
  single-sample pair. **This collapses the paper's three routers toward one on our data**, and is
  the most important limitation of this baseline.

## Not reproduced, and why

The DeBERTa-v3-large backbone; the BART-score quality function; the 10-sample response
distribution (A6); the paper's benchmark suite.

## Hyperparameters and provenance

| name | value | from |
|---|---|---|
| variant | `trans` default; `det` and `prob` available | the paper reports all three (§4) |
| `t*` | grid-searched, 0.1 on our development data | Eq. (3), grid `linspace(0.1, 3.0, 30)` |
| routing threshold | 0.5 default | the paper's cost knob; swept, not fitted |
| training rows | 6,010 over 601 development clips | StudyD3 |
