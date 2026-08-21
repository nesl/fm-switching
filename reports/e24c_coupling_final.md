# E24c Coupling Falsification — Final Report

**Date:** 2026-08-19  
**Sweep:** 48 cells × 10 policies × 3 seeds = 1,440 runs  
**Script:** `experiments/orchestration/sweep_e24c.py`  
**Results:** `results/orchestration/e24c_coupling/`  
**Figures:** `figures/orchestration/e24c_gap_vs_best_decomposed_drift{0,20}.{pdf,png}`, `e24c_refresh_cost.{pdf,png}`

---

## Decision: Coupling claim falsified

The pre-committed decision rule: "If the median gap of joint over the best decomposed policy (including fidelity_first_lifecycle) is within ±5 pp, the coupling claim is falsified."

**Median gap = −1.30 pp (joint underperforms best decomposed).** The coupling claim is falsified. Zero of 48 cells show joint winning by more than 5 pp. Five cells show the best decomposed policy winning by more than 5 pp (maximum 17.2 pp). 43 of 48 cells fall within ±5 pp.

Thesis narrowing: the joint optimization of fidelity × placement × timing does not outperform a lifecycle-cost-aware fidelity selection followed by independent placement. The system claim should narrow to: placement-aware provisioning at the current serving node, with fidelity selected by expected lifecycle cost.

---

## Finding 1: Does a fidelity-vs-refresh-cost effect exist?

Yes, and it is large (up to 28 pp in individual cells). The effect mechanism:

**Joint's value function (`V = P_serve × cold_prefill_saved`) scores candidates by materialization benefit but ignores refresh cost.** This causes joint's density-sorted allocator to place `sum200` objects first (density ≈ 119 × P, because S_ready(sum200) = 0.0115 GB is tiny) before placing `win` objects (density ≈ 11.7 × P, S_ready = 0.117 GB). Both are sufficient for compressible sessions at tau = 0.90 and 0.95 (when sum200 is sufficient).

The consequence: at constrained capacity, `sum200` materializes and occupies space before `win`. In some epochs and nodes, `win` fails its capacity check at materialization-completion time, leaving `sum200` as the only ready object. The engine's `best_ready_object` then serves `sum200` (rank 2 < win rank 3), incurring refresh cost = `cold_prefill(sess.L, edge)`. As L grows past 49152 tokens (~46 epochs at turn_rate = 880), edge cold-prefill becomes infeasible (OOM), and any epoch with a sum200 warm-stale event fails SLO unconditionally.

**fidelity_first_lifecycle avoids sum200 entirely.** By computing expected lifecycle cost (materialize + 10 × refresh per epoch) using cloud-tier reference, it selects `win` for compressible sessions at mid-to-large L:

| Fidelity | lifecycle cost at L=32k (cloud) |
|---|---|
| sum80 | 0.027 + 10 × 7.80 = **78.1 s** |
| sum200 | 0.031 + 10 × 7.80 = **78.1 s** |
| win | 0.325 + 10 × 0.066 = **0.98 s** |
| full | 7.80 + 10 × 0.165 = **9.5 s** |

`win` wins at any L ≥ 5k. By locking to `win`, fidelity_first_lifecycle gets zero sum200 events and avoids the growing cold-prefill SLO failures that plague joint and fidelity_first (weak).

**Magnitude:** In the 12 most discriminating cells (tau=0.95, mixed regime), `slo_fail_on_refresh_fraction` is 0.273–0.658 for joint/fidelity_first (many events, mostly infinity-latency) vs. 0.095–0.312 for fidelity_first_lifecycle (fewer events, finite latency).

---

## Finding 2: Is joint's advantage concentrated in cells where multi-fidelity provisioning occurs?

Partially, but it does not overcome the refresh-cost disadvantage.

Joint's multi-fidelity provisioning (≥2 distinct fidelities ready at the same node for the same session) occurs in 66.9% of sessions on average (mean mf_frac = 0.669 across cells). In 47 of 48 cells, SLO fraction is higher in epochs where multi-fidelity provisioning is active (mean mf_delta = +0.172).

However, multi-fidelity provisioning is the mechanism that causes the sum200 problem: joint places both sum200 and win at the same node. When capacity is tight, placing sum200 first (density priority) crowds out win. In cells where joint and fidelity_first_lifecycle have equal SLO (gap = 0 at tau=0.90, mostly_dense), the mixed-regime sessions don't benefit from win vs. sum200 switching because only full is sufficient for dense sessions — and both policies place full identically.

**Summary:** Multi-fidelity provisioning gives a within-joint benefit (epochs with multi-fidelity coverage have +17 pp SLO delta on average), but the benefit is illusory: the multi-fidelity object (sum200) causes refresh failures that would not occur with single-fidelity win selection. Removing sum200 and keeping only win strictly dominates.

---

## Finding 3: Is this the original placement coupling claim, or a different claim?

**A different claim.** The original E24 coupling claim (C5) was: "jointly optimizing placement node and fidelity simultaneously beats any policy that fixes one dimension first." E24b falsified this in the stressed regime (relative tau, 3-edge topology). E24c's shared solver was designed to retest this with the containment guarantee.

E24c instead reveals a **value function incompleteness**: joint's density metric `V / S_ready` captures materialization cost but not refresh cost. A lifecycle-cost-aware decomposed policy (fidelity_first_lifecycle) corrects this at fidelity selection time, without any placement-fidelity coupling. The remaining question (does optimizing placement simultaneously with lifecycle-aware fidelity add anything?) is answered by the cell-level data: fidelity_first_lifecycle outperforms joint in 38/48 cells (0 cells the reverse) because joint wastes capacity on sum200, and joint's placement stage is no better than fidelity_first_lifecycle's allocator (same knapsack, same nodes, same capacity constraints).

The claim that survives: **lifecycle-cost-aware fidelity selection (prefer win over sum200 at mid-to-large L) captures the dominant effect. Placement follows from the shared allocator independently.**

---

## Oracle violations

Oracle underperforms joint in 2 of 48 cells (Cell 2 and Cell 3 from the smoke test; these persist in the full sweep at matching parameters). Root cause: oracle concentrates P = 1.0 on the predicted next serving node and evicts fallback copies, while joint's distributional coverage maintains multi-node backup. When oracle mispredicts (moderate/high mobility), it has no warm-state fallback. This is a known limitation of the oracle construction (1-step lookahead + aggressive eviction), not a bug. Violations are reported and not suppressed.

---

## Sweep parameters

| Parameter | Values |
|---|---|
| Capacity (% of cheapest-sufficient-mix ref) | 25%, 50%, 75% |
| Mobility | moderate, high |
| Regime mix | mixed (6C/5M/4D), mostly_dense (9D/3M/3C) |
| Tau | 0.90, 0.95 |
| Drift rate | 0, 20 epochs per regime step |
| Sessions | 15, L_init=8192, turn_rate=880 |
| Epochs | 100 |
| Seeds | 3 (42, 1337, 99) |
| Policies | 10 (joint, fidelity_first, fidelity_first_lifecycle, placement_first, cache_value, oracle, reactive, replication, libra_style, handover_sched) |
| Topology | 3 edge (RTX 3090 Ti, S_ready limited to L≤32768) + 1 cloud (A6000) |
| SLO | 5.0 s |

---

## Summary table (selected cells)

| Cap | Mob | Regime | tau | drift | joint | ff_weak | ff_lifecycle | gap (j−ffl) |
|---|---|---|---|---|---|---|---|---|
| 25% | moderate | mixed | 0.95 | 0 | 0.088 | 0.044 | 0.126 | −0.038 |
| 50% | high | mixed | 0.95 | 0 | 0.221 | 0.094 | 0.294 | −0.073 |
| 75% | moderate | mixed | 0.95 | 0 | 0.235 | 0.123 | 0.407 | **−0.172** |
| 75% | high | mixed | 0.95 | 0 | 0.256 | 0.130 | 0.413 | **−0.157** |
| 50% | moderate | mixed | 0.90 | 0 | 0.088 | 0.045 | 0.088 | 0.000 |
| 75% | moderate | mixed | 0.90 | 0 | 0.107 | 0.054 | 0.107 | 0.000 |

At tau=0.90 (sum80 sufficient for compressible), lifecycle selection and cheapest-sufficient selection converge, and joint equals the best decomposed policy. At tau=0.95 (sum80 insufficient, sum200 barely sufficient), lifecycle selection diverges strongly by preferring win.

---

## Known limitations

- Win's Q(win, mixed_sensitive) = 0.460 is **ESTIMATED** (not directly measured in E11); all other Q-table values are measured. Results at mixed_sensitive regime carry this caveat.
- Refresh cost in the simulator uses a simplified staleness model (linear in epochs held). Real refresh cost depends on actual content-diff size, not just epoch count.
- Value function for future work: incorporate lifecycle cost directly into V(i, j, f) to align density ordering with long-run optimality. This is a next-step for the thesis, not a bug fix.
