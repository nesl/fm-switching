<!-- StudyB-baselines. Written for a reviewer: everything faithful to the original is marked FAITHFUL, everything we changed is marked ADAPTATION with its reason. -->
# PerLLM — case D

**Paper.** Z. Yang, Y. Yang, C. Zhao, Q. Guo, W. He, W. Ji, "PerLLM: Personalized Inference
Scheduling with Edge-Cloud Collaboration for Diverse LLM Services" (arXiv:2405.14636).

**Code.** None found. **Case D.**

**Files.** `reconstructed/perllm.py`, `reconstructed/test_perllm_toy.py`, `perllm_adapted.py`.

## The paper's algorithm

| element | where | what it says |
|---|---|---|
| formulation | §1, §3.1 | edge-cloud collaboration as a **combinatorial multi-armed bandit**; a **super arm** is a complete service-and-resource allocation scheme. |
| reward | **Eq. (4)** | `R(S) = −(1/T) Σ_t E[w_tran·E^t_tran + w_infer·E^t_infer + w_idle·E^t_idle] + λ·f_t(y)` — negative weighted energy plus the constraint-satisfaction term. |
| constraint function | §3.2 | "The scheme `y` satisfies all constraints if `f(y) ≥ 0`, otherwise it violates at least one constraint"; folded INTO the reward so violations are penalised rather than discarded. |
| CS-UCB | §3.2 (figure) | `UCB(a,t) = R(a) + c·sqrt(ln t / N(a,t)) + P(t)`. |
| Algorithm 1 | §3.2 | play a super arm; if the processing-time requirement and the computing-power and bandwidth budgets hold, accept as `(X*, S*)`; else update the regret and continue. |
| constraints | §3.1 | C1 per-server processing time `D_{i,t}`; `Σ_i C_it ≤ C^t_max`; `Σ_i B_it ≤ B^t_max`. |

## Mapping, step by step

| paper | our code | note |
|---|---|---|
| `f(y)` | `constraint_satisfaction` (worst slack, ≥ 0 iff feasible) | FAITHFUL |
| Eq. (4) | `reward` | FAITHFUL in form |
| `UCB(a,t)` | `ucb` (unplayed arm ⇒ `inf`) | FAITHFUL |
| Algorithm 1 | `CSUCB.schedule` | FAITHFUL |
| super arm | one configuration applied to every stream, plus deadline-ordered recall admission | ADAPTATION A1 |
| energy terms | our **delivered utility** and charged GPU-seconds | ADAPTATION A2 |
| C1 / computing / bandwidth | tightest recall deadline / budget GPU-s / uplink bytes | ADAPTATION A3 |

## Adaptations, with reasons

- **A1 the super-arm space is pruned.** The full product over streams and queries is
  combinatorial; the paper's own search is over a candidate set, so we enumerate one candidate
  per profile row (a shared configuration) and admit recall greedily by deadline inside it.
  **Consequence: the bandit explores configurations, not per-stream assignments**, which is a
  smaller space than the paper's.
- **A2 the reward is delivered utility, not energy.** The task specifies this substitution: the
  paper's three energy terms are replaced by measured quality minus charged GPU-seconds. We keep
  `λ·f(y)` exactly, so the constraint mechanism is the paper's.
- **A3 the three constraint families map directly** onto our deadline, GPU-second budget and
  uplink.

## Not reproduced, and why

The approximation coefficients α, β (they enter only the regret ANALYSIS, §3.2, not the decision
rule); the paper's energy model constants (its Table 1 hardware); its multi-service workload mix;
the per-server placement across many edge servers (we have one device tier and one cloud replica).

## Hyperparameters and provenance

| name | value | from |
|---|---|---|
| `c` (UCB) | 1.0 | standard UCB1 constant; the paper does not print a value |
| `λ` | 1.0 | the paper calls λ "the coefficient of the constraint satisfaction function" without a value |
| `P(t)` | 0.0 | the paper's figure includes a `P(t)` term it does not define; set to zero and FLAGGED as reconstruction gap G1 |
| horizon | 10 s | our scheduling epoch scale |
