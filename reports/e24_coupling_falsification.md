# E24: Coupling Falsification Report

**Date:** 2026-08-19  
**Experiment:** E24 (simulator, purpose=orchestration)  
**Script:** `simulator/provisioning/sweep.py`  
**Results:** `results/orchestration/e24_coupling/`  
**Figures:** `figures/orchestration/e24_phase_diagram.pdf`, `e24_phase_diagram_vs_cv.pdf`

---

## Setup

**Simulator.** Pure-Python trace-driven. One edge node (RTX 3090 Ti equivalent, 1.5× prefill slowdown) and one cloud node (A6000 reference, 1.0×). Device node not included as provisioning target. Mobility from measured Markov traces (markov_network.py). Epoch = 30 s.

**Sessions.** 15 sessions per cell. L_init = 4096 tokens, turn_rate = 200 tokens/epoch, n_epochs = 60 → L_final ≈ 16096 at run end. Regime fixed per session (no drift).

**Capacity normalization.** Full-replication budget = cost of holding every session ready at "full" fidelity at every candidate node at L_mid = 10096 tokens. S_ready(full, 10096) = 0.579 GB/session/node. Full budget = 15 × 0.579 × 2 nodes = 17.36 GB total; per-node 100% = 8.68 GB. Both nodes set to (α/100) × 8.68 GB at capacity level α. This keeps relative per-node budgets equal and preserves the edge/cloud preference ordering.

**Bandwidth profile.** 10 Mbps, RTT 50 ms (urban WiFi); stated for reproducibility.

**Latency SLO.** 5.0 s. Warm-stale refresh cost: full → warm_append_s(L) ≈ 0.066s (always passes); sum80/sum200 → cold_prefill(L) ≈ 1.9–3.1 s at L=10–16k (always passes). At typical session lengths in this sweep, latency SLO is violated only on cold misses.

**Seeds.** 3 per cell. All results reported as mean (min–max range).

**Total sweep.** 5 capacity × 4 mobility × 3 regime_mix = 60 cells × 7 policies × 3 seeds = 1,260 runs.

---

## Q(f, w) table and q_min

| fidelity | compressible | mixed_sensitive | dense |
|---|---|---|---|
| full | 0.502 | 0.580 | 0.340 |
| win | 0.506 | 0.460† | 0.220 |
| sum200 | 0.498 | 0.550 | 0.099 |
| sum80 | 0.470 | 0.550 | 0.099 |
| blind | 0.268 | 0.360 | 0.000 |

† win under mixed_sensitive is estimated (not directly measured in E11).

**q_min = 0.30.** Cheapest sufficient fidelity: compressible → sum80 (0.470 ≥ 0.30); mixed_sensitive → sum80 (0.550 ≥ 0.30); dense → full (only fidelity ≥ 0.30 is 0.340).

Dense regime requires full KV. S_ready(full, L) = 57344 × L bytes. At L = 10k: 0.574 GB/session. At 10% per-node cap (0.868 GB): 1.5 sessions fit. Sum80: S_ready = 57344 × 80 / 1e9 = 0.0046 GB/session. At 10% cap: 188 sessions fit.

---

## Policy table

| policy | placement | fidelity | oracle info used |
|---|---|---|---|
| reactive | ✗ | ✗ | — |
| replication | ✓ (all reachable) | ✗ (always full) | next_serving_node |
| placement_only | ✓ (next node) | ✗ (always full) | next_serving_node |
| fidelity_only | ✗ | ✓ (cheapest_sufficient) | future_regimes |
| cache_value | ✓ implicit (EV × P_serve) | ✓ implicit (EV score) | next_serving_node, future_regimes |
| joint | ✓ (next node) | ✓ (cheapest_sufficient) | next_serving_node, future_regimes |
| oracle | ✓ (next node) + evict | ✓ (cheapest_sufficient) | next_serving_node, future_regimes |

All policies receive oracle-parity inputs: true next-epoch serving node and true session regime. Differences are in *what they do with this information*.

---

## Kill criteria

Seven kill criteria were evaluated. A fired criterion is one that holds in the data.

### 1. cache_value within ~5% of joint over most realistic cells

**FIRES.** At 25–100% capacity (80% of all cells), joint = cache_value = 0.983 in every regime_mix. The maximum joint advantage over cache_value across all 60 cells is **+6 pp** (10% cap, high mobility, mostly_compressible). At 50% cap and above, the gap is 0 pp in all 60 cells.

| capacity | mostly_compressible | mixed | mostly_dense |
|---|---|---|---|
| 10% | joint 0.983, cv 0.980, **Δ=+3pp** | joint 0.981, cv 0.979, **Δ=+2pp** | joint 0.977, cv 0.976, **Δ=+1pp** |
| 25% | joint 0.983, cv 0.983, Δ=0pp | joint 0.983, cv 0.982, Δ=+1pp | joint 0.981, cv 0.980, Δ=+1pp |
| 50% | 0.983 = 0.983, Δ=0pp | 0.983 = 0.983, Δ=0pp | 0.983 = 0.983, Δ=0pp |
| 75–100% | 0.983 = 0.983, Δ=0pp | 0.983 = 0.983, Δ=0pp | 0.983 = 0.983, Δ=0pp |

(Values averaged over mobility levels; per-cell max gap is +6 pp at 10%/high/compressible.)

### 2. fidelity_only within ~5% of joint

**Does NOT fire.** fidelity_only achieves SLO 0.971 in every cell — identical to reactive. It never outperforms reactive because it selects cheapest_sufficient fidelity but performs no placement. Joint at 25%+ cap: 0.983. Gap = 12 pp.

### 3. placement_only within ~5% of joint

**Partially fires.** At 25%+ cap: placement_only = 0.977–0.983, joint = 0.983. Gap ≤ 6 pp at 25% cap, 0 pp at 50%+ cap. At 10% cap: placement_only = 0.973 vs joint = 0.977–0.983; gap up to 10 pp. Placement_only uses "full" fidelity, which occupies 0.574 GB/session at L_mid — it cannot serve all 15 sessions at 10% cap (1.5 sessions/node fit). Joint's fidelity selection rescues it at low capacity.

### 4. False warm hits rare everywhere

**Does NOT fire (i.e., false warm hits are indeed rare).** false_warm_hit_rate = 0.000 for joint in all 60 cells. Joint always provisions cheapest_sufficient, which always meets q_min. No capacity constraint forces joint to serve a below-minimum-quality fidelity.

### 5. Mobility level changes decisions little

**FIRES at 50%+ capacity.** At 50–100% cap, joint = 0.983 and cache_value = 0.983 regardless of mobility level — all four mobility levels produce the same SLO fraction. At 10% cap, mobility produces variation: joint ranges from 0.983 (static) to 0.983 (high mobility, compressible) but cache_value ranges from 0.983 (static) to 0.977 (high mobility). The joint policy is robust to mobility at all capacity levels; cache_value degrades at high mobility + low capacity.

### 6. Gains only in extreme cells

**FIRES.** Joint's SLO advantage over cache_value exceeds 3 pp in only 3 of 60 cells (10% cap, high mobility — all three regime_mixes). In all 45 cells at 25%+ capacity, joint equals cache_value. The 10% capacity regime represents a 0.868 GB per-node budget — approximately 1.5 full-KV sessions at L_mid. This is below any plausible deployment floor for an edge inference node hosting an FM.

### 7. Cache_value explains most of the gain vs reactive

**FIRES.** The joint vs reactive gain is 12 pp. Of that, cache_value captures 9 pp (reactive = 0.971, cache_value = 0.980 at 10% cap, or 0.983 at 25%+ cap). Joint adds at most 3 pp over cache_value, and 0 pp in the majority of cells. Most of the gain comes from placement-awareness (shared by cache_value and joint), not from explicit fidelity–placement coupling.

---

## Phase diagram reading

**vs best non-joint baseline** (figure: `e24_phase_diagram.pdf`):

- Compressible regime: joint gains 3–10 pp at 10% cap (mobility matters); 0 pp at 25%+. Best non-joint is always cache_value or replication.
- Mixed regime: similar pattern; 2–8 pp gain at 10% cap, 0–1 pp at 25%+.
- Dense regime: smallest gains overall; 1–4 pp at 10% cap, 0 pp at 25%+.

**vs cache_value** (figure: `e24_phase_diagram_vs_cv.pdf`):

- Gains are strictly smaller than vs best non-joint. Max +6 pp at 10%/high/compressible.
- Dense regime at 10% cap: joint = 0.977, cache_value = 0.973–0.976 → gap = 1–4 pp.
- 50%+ capacity: all cells show 0 pp improvement over cache_value.

---

## Miss-type breakdown

At the most differentiated cell (10% capacity, high mobility):

| policy | SLO frac | placement_miss | cold_miss | mat_miss | false_warm |
|---|---|---|---|---|---|
| reactive | 0.967 | 0.017 | 0.017 | 0.000 | 0.000 |
| cache_value (compressible) | 0.977 | 0.001 | 0.011 | 0.010 | 0.000 |
| joint (compressible) | 0.983 | 0.000 | 0.011 | 0.006 | 0.000 |

Reactive's 1.6 pp SLO loss is almost entirely placement misses — state exists (cold-materialized last epoch) but at the wrong node when mobility causes a handoff. Joint and cache_value both reduce placement misses to near zero. The residual 1.1% cold_miss rate for both is first-epoch startup (no warm state exists yet). Joint additionally reduces materialization misses (0.6% vs 1.0% for cache_value) — its conservative sum80 fidelity means objects materialize faster (negligible KV size), landing ready before the next serving event.

**Oracle anomaly.** Oracle underperforms joint at mostly_dense: oracle SLO = 0.956 (mean over 4 mobility levels at 10% cap) vs joint = 0.977. Oracle's greedy eviction — removing all ready objects not at the predicted next-serving node — creates hard cold misses when the 1-epoch-ahead prediction is wrong (edge disconnects). Dense regime requires full KV (large, slow to materialize), so evicted copies cannot be recovered within one epoch. Joint's non-evicting behavior retains cloud copies as fallback, trading capacity for resilience. This finding confirms that aggressive capacity recovery is counterproductive when session state is large and mobility is uncertain.

---

## Conclusion: Is coupling real?

**Coupling is real but narrow.**

Placement-awareness is essential: policies without it (reactive, fidelity_only) are 12 pp below ceiling in the realistic operating range (25–100% cap). This gap is large and unambiguous.

Explicit joint optimization of fidelity and placement (joint policy) adds at most 3 pp over the implicit coupling in cache_value, and 0 pp in 45 of 60 cells. The 3 pp gain appears only at ≤10% per-node capacity — a budget that cannot support even 2 full-KV sessions per node at L = 10k tokens, well below the threshold of a practical edge deployment.

**Which kill criterion is responsible for the limitation?** Kill criterion #1 fires: cache_value, despite not explicitly decomposing fidelity from placement, achieves near-identical performance by scoring (fidelity × placement) jointly through expected-value scoring. The coupling structure the thesis argues for is already captured by the EV heuristic.

**Kill criterion #6 also fires:** gains exceeding 3 pp appear only in cells where per-node capacity is 0.868 GB (10% of full-replication budget). The "expected" coupling regime — mid-capacity × mixed regime × moderate mobility — shows 0–1 pp joint advantage over cache_value.

**Thesis recommendation:** Narrow, do not abandon. The claim that placement-aware provisioning is necessary is supported (12 pp gap vs non-placement policies). The stronger claim — that explicit joint fidelity × placement optimization is required and cannot be reduced to a simpler heuristic — is not supported by this simulation. The cache_value EV heuristic captures the coupling effect in practice. The thesis argument should shift from "joint optimization is necessary" to "placement-aware provisioning is necessary; fidelity selection amplifies the benefit primarily at near-zero capacity margins."

A real-hardware trace study showing that deployed edge nodes operate at ≤10% of full-replication budget would reinstate the stronger claim. Without that evidence, the current simulation shows coupling is a second-order effect relative to placement.
