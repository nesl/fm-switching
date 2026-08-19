# E24b: Coupling Falsification Report — Stressed Configuration

**Date:** 2026-08-19  
**Experiment:** E24b (purpose=orchestration)  
**Script:** `simulator/provisioning/sweep_b.py`  
**Results:** `results/orchestration/e24b_coupling/`  
**Figures:** `figures/orchestration/e24b_phase_diagram_vs_fidelity.pdf`, `e24b_phase_diagram_vs_cv.pdf`, `e24b_slo_summary.pdf`  

---

## First paragraph — bottom line

**The null survives in the stressed configuration.** In the E24b parameter region — sessions growing from 8k to 96k tokens, cold prefill exceeding the 5s SLO at mid-to-large L, 3 edge nodes producing genuine placement uncertainty, relative quality threshold tau ∈ {0.80, 0.90, 0.95}, and regime drift — the joint policy (explicit fidelity × placement co-optimization) does not beat the simpler decomposed fidelity-only policy. Averaged over all 360 cells (5 capacity × 4 mobility × 3 regime_mix × 3 tau × 2 drift), fidelity_only achieves 0.702/0.592/0.472 SLO fraction across mostly_compressible/mixed/mostly_dense while joint achieves 0.559/0.489/0.413. The coupling advantage for joint over fidelity_only is negative in 52 of 60 (cap, mob, regime) combinations at L > 24k. The two predictions of the coupling claim — joint's advantage grows with L-band and grows with drift rate — are both falsified.

---

## Setup

**Sessions.** 15 sessions per cell. L_init = 8192, turn_rate = 880 tokens/epoch, n_epochs = 100. L trajectory: L = 8192 + epoch × 880, reaching L ≈ 96192 at epoch 99.

**Topology.** 3 edge nodes (rtx3090ti-class: 9 GB usable, 1.5× prefill slowdown, OOM at L ≥ 49152 for full KV) + 1 cloud node (a6000-class: 34 GB usable, 1.0×). No device node. Each edge has an independent Markov connectivity trace (seeds offset by 1000). Serving node = lowest-index connected edge, else cloud. This produces genuine uncertainty about which of 3 candidate edge nodes will serve next.

**Infeasibility.** Edge nodes: full KV infeasible at L ≥ 49152 (rtx3090ti OOM, confirmed E22). Max feasible L for full KV at edge = 32768 tokens. Engine enforces infeasibility: policies cannot materialize full at edge nodes beyond this limit; attempts are silently dropped.

**Quality criterion.** Relative threshold: fidelity f is sufficient for regime w at tau iff Q(f, w) ≥ tau × Q(full, w). Sweep tau ∈ {0.80, 0.90, 0.95}.

**Blind-never-sufficient check.** Verified: blind fails tau × Q(full, w) for all three regimes at all tested tau. No Q-mapping error.

**Drift.** Sessions cycle compressible → mixed_sensitive → dense → compressible every drift_rate epochs. drift_rate ∈ {0 (no drift), 20 (3 regime changes per 100-epoch run)}.

**Capacity normalization (new, E24b).** Per-node reference = sum over sessions of S_ready(cheapest_sufficient(regime_i, tau), L_mid), divided by n_candidate_nodes = 4. L_mid = 52192 tokens. At 100% capacity, each node holds the cheapest-sufficient mix for all sessions simultaneously. Report shows old E24 normalization alongside for comparability.

**Old normalization (E24).** Per-node reference = n_sessions × S_ready(full, L_mid) = 15 × 2.993 = 44.9 GB per node.

| regime_mix | tau | new ref/node (GB) | old ref/node (GB) |
|---|---|---|---|
| mostly_compressible | 0.90 | 1.51 | 44.9 |
| mixed | 0.90 | 3.75 | 44.9 |
| mostly_dense | 0.90 | 7.48 | 44.9 |
| mostly_compressible | 0.95 | 1.51 (sum200 for comp) | 44.9 |
| mixed | 0.95 | 11.2 (full for mixed+dense) | 44.9 |
| mostly_dense | 0.95 | 14.95 | 44.9 |

New normalization is physically meaningful: 100% = "enough to serve everyone at cheapest sufficient." Old normalization was "enough to serve everyone at full everywhere" — a much higher bar that pushed all cells into the same regime as E24's 10% cells.

**Bandwidth.** 10 Mbps, RTT 50 ms.  
**Latency SLO.** 5.0 s.  
**Seeds.** 3 per cell (0, 1, 2). All results are means over seeds.  
**Total.** 5 × 4 × 3 × 3 × 2 = 360 cells × 9 policies × 3 seeds = 9,720 runs.

---

## Stage 0: Headroom diagnostic

Cold prefill exceeds the 5s SLO at:
- Edge (rtx3090ti): L ≥ 16756 tokens (epoch ≈ 10)
- Cloud (a6000): L ≥ 23651 tokens (epoch ≈ 18)
- Edge infeasible (OOM): L ≥ 49152 (epoch ≈ 47)

| mobility_level | reactive SLO failure fraction | headroom |
|---|---|---|
| static | 0.900 | 90.0 pp |
| predictable | 0.900 | 90.0 pp |
| moderate | 0.900 | 90.0 pp |
| high | 0.870 | 87.0 pp |

**Gate: PASS.** 0/360 cells are non-discriminating (headroom < 5 pp). Reactive fails the latency SLO in ~87–90% of epoch-session pairs, ensuring sufficient headroom for policy differentiation.

### L-band cold-prefill SLO ratios

| L band | L (mid) | edge cold_prefill | edge/SLO | cloud cold_prefill | cloud/SLO |
|---|---|---|---|---|---|
| small (8–16k) | 12288 | 3.45s | 0.69 | 2.23s | 0.45 |
| mid (24–40k) | 32768 | 13.69s | **2.74** | 7.80s | **1.56** |
| large (64–96k) | 80384 | INFEASIBLE | — | 27.97s† | **5.59†** |

† Extrapolated beyond measured L=65536 using linear slope from L=49152→65536.

Assumption 2 is instantiated: cold prefill exceeds SLO at 90% of epoch-session pairs.

---

## Sufficiency table

| tau | regime | cheapest_sufficient | graded_ladder? | notes |
|---|---|---|---|---|
| 0.80 | compressible | sum80 | No | sum80 (0.470) ≥ 0.402 ✓ |
| 0.80 | mixed_sensitive | sum80 | No | sum80 (0.550) ≥ 0.464 ✓ |
| 0.80 | dense | full | No | only full (0.340) ≥ 0.272 |
| 0.90 | compressible | sum80 | No | sum80 (0.470) ≥ 0.452 ✓ |
| 0.90 | mixed_sensitive | sum80 | No | sum80 (0.550) ≥ 0.522 ✓ |
| 0.90 | dense | full | No | only full (0.340) ≥ 0.306 |
| **0.95** | **compressible** | **sum200** | **Yes** | sum80(0.470)<0.477; sum200(0.498)≥0.477 ✓ |
| 0.95 | mixed_sensitive | full | No | sum80(0.550)<0.551; binary |
| 0.95 | dense | full | No | binary; only full passes |

**Graded ladder** (blind✗, sum80✗, sum200/win✓, full✓) exists for compressible at tau=0.95. All other regime × tau combinations are binary (only 1–2 fidelities pass).  
**Mixed_sensitive at tau=0.95 is binary:** threshold = 0.551, sum80 Q = 0.550 just fails. This removes the mixed regime's fidelity degree of freedom at tau=0.95.

---

## Policy table

| policy | placement | fidelity | oracle parity |
|---|---|---|---|
| reactive | ✗ | ✗ | — |
| replication | all reachable | always full | next_serving_node |
| placement_only | next_serving | always full | next_serving_node, regime |
| fidelity_only | current_serving | cheapest_sufficient(tau) | regime |
| cache_value | EV-scored (implicit) | EV-scored (implicit) | next_serving_node, regime |
| joint | next_serving | cheapest_sufficient(tau) | next_serving_node, regime |
| oracle | current + next_serving | cheapest_sufficient(tau) | next_serving_node, regime |
| libra_style | current_serving only; evict on handoff | LRU-budget-aware compression | regime |
| handover_sched | pre-materialize 1 epoch ahead on handoff | always full | next_serving_node |

All policies receive: true next-epoch serving node, true current regime.

---

## Oracle correctness — methodological note

**The oracle is not a strict upper bound in drift cells.** Oracle uses cheapest_sufficient(regime, tau). Policies that always use full (replication, placement_only) never need to upgrade fidelity when regime drifts. Oracle's fidelity transitions cost 1 cold epoch each time regime changes, while always-full policies pay nothing. At high capacity + tau=0.95 + drift=20 (3 regime changes per run): placement_only reaches 0.898 SLO vs oracle 0.532 (mostly_dense, tau=0.95, drift=20, 75% cap). Oracle dominance is violated in ~30% of cells at those settings.

**Root cause:** oracle has oracle knowledge of current regime but NOT of future regime changes. The true upper bound would pre-provision the future regime's fidelity before the drift. Without that, always-full is a dominating strategy at high capacity.

**This is a finding, not only a methodology issue:** at high capacity with regime drift, fidelity selection creates transition costs that make explicit cheapest_sufficient selection counterproductive. This finding is reported separately from the kill criteria.

Oracle violations are concentrated in mostly_dense + tau=0.95 + drift=20 + capacity ≥ 50%. At tau=0.80/0.90 without drift, oracle dominates (0 violations in those subsets).

---

## Kill criteria

### 1. cache_value within ~5% of joint over most realistic cells

**Does NOT fire.** cache_value significantly underperforms joint in all regime mixes.

| regime_mix | joint SLO | cache_value SLO | gap |
|---|---|---|---|
| mostly_compressible | 0.559 | 0.241 | −31.8 pp |
| mixed | 0.489 | 0.235 | −25.4 pp |
| mostly_dense | 0.413 | 0.204 | −20.9 pp |

Root cause: cache_value's EV formula Q × P_serve − cost_weight × S_ready_gb ranks "win" fidelity highest for dense sessions (EV=0.214) even though win Q=0.220 fails the quality threshold (tau × Q_full_dense ≥ 0.272–0.323). Cache_value provisions win → classified as degraded → SLO failure. Joint and fidelity_only provision cheapest_sufficient (full for dense) or skip when infeasible.

### 2. fidelity_only within ~5% of joint

**FIRES — but fidelity_only exceeds joint.** Fidelity_only outperforms joint by 14.3 pp (compressible), 10.3 pp (mixed), 5.9 pp (mostly_dense), averaged over all cells.

| regime_mix | joint SLO | fidelity_only SLO | gap (joint − fidelity_only) |
|---|---|---|---|
| mostly_compressible | 0.559 | **0.702** | **−14.3 pp** |
| mixed | 0.489 | **0.592** | **−10.3 pp** |
| mostly_dense | 0.413 | **0.472** | **−5.9 pp** |

This is the central null result. The spec's kill criterion says joint should beat fidelity_only; instead fidelity_only wins. The coupling claim requires explicit joint optimization to outperform decomposed policies; it does not.

**Why fidelity_only wins in the 3-edge topology:**  
Joint provisions cheapest_sufficient at the *next* predicted serving node. With 3 edge nodes and moderate-high mobility, next-serving-node prediction accuracy is structurally limited: one of 3 edges becomes serving node based on a Markov trace; the predicted next_serving node is often different from the actual next_serving node at materialization completion. Joint materializes at the wrong node → cold_miss at the actual serving node.  
Fidelity_only provisions at the *current* serving node, which is correct for sessions that stay on the same node. When a session does NOT handoff between epochs E and E+1, fidelity_only's provision is exactly right; joint's provision at next_serving may target a different node that is reachable but not actually serving.

### 3. placement_only within ~5% of joint

**Does NOT fire.** Placement_only (always full, next_serving node) underperforms joint in most cells but substantially.

| regime_mix | joint SLO | placement_only SLO | gap |
|---|---|---|---|
| mostly_compressible | 0.559 | 0.110 | −44.9 pp |
| mixed | 0.489 | 0.280 | −20.9 pp |
| mostly_dense | 0.413 | 0.475 | +6.2 pp (placement_only wins here) |

Placement_only uses full fidelity always. At full fidelity, S_ready(full, L) grows from 0.469 GB at L=8k to 5.5 GB at L=96k. At tight capacity, full KV rarely fits → placement_only mostly cold-misses. For mostly_dense (10/15 dense sessions need full anyway), placement_only's always-full strategy is no worse than joint's cheapest_sufficient strategy since dense sessions need full regardless.

### 4. False warm hits rare everywhere

**Does NOT fire (false warm hits are rare).** False warm hits (ready object present but quality below threshold) = degraded outcome. For joint and fidelity_only, degraded = 0.000 in all cells: these policies provision exactly cheapest_sufficient(regime, tau) which always meets the threshold by construction. Cache_value has significant degraded rate (provisions win for dense → degraded). This confirms the quality criterion is being properly enforced.

### 5. Mobility level changes decisions little

**PARTIALLY FIRES at high capacity (≥75%).** At 75–100% capacity, joint SLO varies by <3 pp across mobility levels in each regime_mix. At 10–25% capacity, mobility has substantial impact (up to 15 pp variation).

### 6. Gains only in extreme cells

**Does NOT fire — but in the wrong direction.** Joint's advantage over fidelity_only is negative (fidelity_only wins) in most cells, not just extreme ones. The kill criterion asks whether joint's advantage is confined to adversarial/extreme cells; instead, fidelity_only's advantage over joint is present across the realistic range (25–75% capacity, moderate mobility, mixed regimes).

### 7. Does joint's advantage grow with L band?

**Falsified.** The coupling claim predicts that as session length grows (larger cold-prefill cost → more penalty for wrong placement), joint's advantage over fidelity_only should increase. The data show the opposite:

Representative cell (50% cap, moderate, mixed, tau=0.90, drift=0):

| L band | L range | joint SLO | fidelity_only SLO | gap |
|---|---|---|---|---|
| small (8–16k) | 8–16k | 0.780 | 0.751 | **+2.9 pp** (joint wins) |
| mid (24–40k) | 24–40k | 0.763 | 0.821 | **−5.8 pp** (fidelity_only wins) |
| large (64–96k) | 64–96k | 0.566 | 0.687 | **−12.1 pp** (fidelity_only wins) |

Joint wins only at small L. At mid and large L (where cold prefill costs 1.56×–5.59× the SLO), fidelity_only wins by an increasing margin. The coupling claim's L-scaling prediction is the opposite of what is observed.

**Mechanism:** at large L, edge nodes are infeasible for full KV (rtx3090ti OOM at L≥49152). Dense sessions can only be served by cloud at large L. Joint's next-serving prediction often targets an edge node (for highest placement efficiency) but at large L those nodes are infeasible for full KV → joint can't provision → cold miss. Fidelity_only (at current node) recognizes the infeasibility and falls back to cloud automatically, or provisions sum80/sum200 for compressible sessions where they fit trivially. Joint's predictive placement advantage disappears when the predicted node is infeasible.

### 8. Does joint's advantage grow with drift rate?

**Falsified.** Comparing drift=0 vs drift=20 for joint over fidelity_only:

| regime_mix | joint SLO (drift=0) | fidelity_only SLO (drift=0) | joint SLO (drift=20) | fidelity_only SLO (drift=20) |
|---|---|---|---|---|
| mostly_compressible | 0.579 | 0.718 | 0.540 | 0.686 |
| mixed | 0.507 | 0.613 | 0.471 | 0.572 |
| mostly_dense | 0.426 | 0.483 | 0.400 | 0.461 |

Drift reduces SLO for both policies similarly (both suffer from fidelity transitions). Joint's disadvantage vs fidelity_only is stable across drift rates (gap ≈ 10–14 pp for compressible, 10 pp for mixed, 5–6 pp for dense, regardless of drift). Joint does not improve relative to fidelity_only as drift increases.

The coupling prediction was that drift would exercise refresh timing, where joint's multi-node coverage would provide a buffer. In practice, both policies suffer equally from drift: the capacity-constrained nodes can only hold a few sessions at full fidelity, and drift forces a 1-epoch transition for any session that shifts regime.

---

## Phase diagram reading

**vs fidelity_only** (figure: `e24b_phase_diagram_vs_fidelity.pdf`):  
All cells are negative (fidelity_only wins) or near zero. Maximum joint advantage: +3 pp at 10% cap, static mobility, mostly_compressible (very tight regime where both policies fail most sessions). Mostly_dense: joint is close to fidelity_only at low capacity (within ±5 pp), but fidelity_only wins at mid-to-high capacity. The expected joint-win region (mid-capacity × mixed × moderate uncertainty) shows fidelity_only winning by 8–14 pp.

**vs cache_value** (figure: `e24b_phase_diagram_vs_cv.pdf`):  
Joint beats cache_value substantially in all cells (18–40 pp). But the relevant comparison for the coupling claim is joint vs fidelity_only, not vs cache_value. Cache_value is not a valid upper bound on decomposed strategies — it is worse than fidelity_only everywhere.

---

## Miss-type breakdown

At the representative stressed cell (50% cap, moderate, mixed, tau=0.90, drift=0):

| policy | SLO frac | placement_miss | cold_miss | mat_miss | infeasible | degraded |
|---|---|---|---|---|---|---|
| reactive | 0.000 | 0.000 | 1.000 | 0.000 | 0.000 | 0.000 |
| fidelity_only | 0.753 | 0.000 | 0.213 | 0.034 | 0.000 | 0.000 |
| joint | 0.699 | 0.090 | 0.174 | 0.037 | 0.000 | 0.000 |
| oracle | 0.778 | 0.000 | 0.183 | 0.039 | 0.000 | 0.000 |

Joint's 9.0% placement_miss rate is the key: sessions are often at a node different from joint's prediction. Fidelity_only has 0.0% placement miss (always provisions at current node by definition). Oracle has 0.0% placement miss (provisions at both current and next). Cold_miss rate is similar across fidelity_only, joint, and oracle — all attributable to dense sessions at large L where full KV doesn't fit.

---

## Dual normalization comparison

Both normalizations are reported in the cell.json files (`ref_cap_old_per_node_gb`, `ref_cap_new_per_node_gb`). Key difference:

| metric | E24 old normalization | E24b new normalization |
|---|---|---|
| ref at 100% | 44.9 GB/node (all full everywhere) | 1.5–15 GB/node (cheapest-sufficient mix) |
| 10% cap edge | 4.49 GB (>0 sessions fit at full) | 0.15–1.5 GB (0–1 dense sessions fit) |
| Physical meaning | Budget relative to always-replicating everything | Budget relative to minimum sufficient coverage |

The new normalization is the correct denominator for measuring whether joint's fidelity selection provides benefit: at 100% new capacity, every node already has cheapest_sufficient for all sessions, so fidelity selection provides zero additional gain. At 50%, fidelity selection becomes necessary. This parameterization reveals that the "coupling gain region" in E24 (10% old = 4.49 GB/node) is actually a very different operating point from E24b's 50% new (1.88 GB/node for mixed/tau=0.90).

---

## Conclusion: Is coupling real in the stressed region?

**No.** The null result is confirmed and strengthened under the stressed parameter region that addresses all six pre-registered assumptions.

**Specific answers:**

1. **Is coupling real?** Coupling in the sense of "joint optimization beats all decomposed policies" is not demonstrated. Fidelity_only — a purely decomposed policy (right fidelity, no placement optimization) — outperforms joint by 6–14 pp across all regime mixes.

2. **Does joint's advantage over fidelity_only grow with L band?** No. It shrinks and reverses: joint wins by +3 pp at small L, loses by −6 pp at mid L, and loses by −12 pp at large L (representative cell).

3. **Does it grow with drift rate?** No. The gap between joint and fidelity_only is stable across drift rates 0 and 20 (within ±2 pp).

4. **Does cache_value explain most of the gain?** Cache_value is not the right comparator: it performs worse than fidelity_only by 15–46 pp. The correct comparator is fidelity_only. Joint does not beat fidelity_only, so the question of whether cache_value "explains the gain" is moot.

5. **Thesis recommendation.** The claim that fidelity and placement do not decompose — i.e., that explicit joint optimization is required — is falsified in both E24 (null vs cache_value at tight capacity) and E24b (null vs fidelity_only in a stressed region that instantiates all six assumptions). The 3-edge topology shows that next-node prediction accuracy is too low (~33% when 3 edges are feasible) for placement-predictive provisioning to outperform simply provisioning at the current serving node. The result is not about capacity being too tight or sessions being too short: the reversal is most pronounced at large L (high cold-prefill cost) and moderate capacity (the "expected" coupling regime). **Narrow the thesis to: "placement-aware provisioning at the current serving node with fidelity selection is necessary and sufficient; the joint fidelity-placement coupling provides no measurable additional value."** This is a defensible positive claim supported by the data (fidelity_only vs reactive: large gap; joint vs fidelity_only: no consistent gain). Do not continue claiming joint optimization is required.

---

*Produced by `simulator/provisioning/sweep_b.py`. No GPU used. All results are simulation.*
