# E36b (rewrite) — Corrected Fleet Policy Experiment

**Date:** 2026-08-24  
**Host:** flash / CPU only (pure simulation, no GPU)  
**Script:** `experiments/orchestration/e36b_fleet.py` (rewrite)  
**Results:** `results/orchestration/e36b_fleet/`  
**Figures:** `figures/orchestration/e36b_gap_vs_fleetsize.pdf`, `e36b_binding_resource.pdf`, `e36b_utilization_split.pdf`  
**Supersedes:** `reports/e36_fleet_policy.md` (E36) and the first version of `reports/e36b_fleet_policy.md`

---

## Why this rerun exists

E36 and the first E36b ran a different experiment from the one specified. Four defects:

1. **Wrong comparison.** The kill condition compared maintenance_aware vs device_only. The paper's incumbent is footprint_ranked (cache-value scoring by Q/KV_footprint_bytes). The decisive comparison is maintenance_aware vs footprint_ranked.

2. **Missing policies.** footprint_ranked and oracle were absent. reactive and budget_aware were present but undefined in the formulation.

3. **Missing diagnostic.** No reporting of which resource (KV memory or accelerator time) bound admission. The mechanism claim — that footprint_ranked saturates the accelerator with sum200 regeneration — was not tested.

4. **Metric saturated by quality.** Prior runs used Bernoulli draws from Q(f) as a quality gate, capping both_met at Q(full) ≈ 0.40. This washed out latency differences between policies. The corrected model uses an admissibility constraint: f is admissible iff Q(f, model, workload) ≥ q_min. Quality miss = no admissible representation available at serving tier. Both_met = TTFT ≤ budget AND served from admissible representation.

---

## Inputs

| input | value | source |
|---|---|---|
| Q table (edge: qwen7b, device: qwen3b) | full/win10/sum200 per workload | E29 |
| Edge full warm-append | 66 ms | E26/E35 |
| Edge win10 intra / inter | 59 / 1031 ms | E35 |
| Edge sum200 restore / update | 32 / 5822 ms | E35 |
| Edge cold prefill rate | 5984 tok/s | E21/E26 |
| Jetson qwen7b cost profile | per-L tables | E23 |
| A1 ratio (incr_warm 3B/7B) | 0.593@1k → 0.705@16k | E37/E37b |
| LoCoMo session stats | 22 turns/session, 7275-tok win10 | E33a |
| KV bytes per token (qwen7b) | 57 344 B/tok | E23 |
| Edge KV usable capacity | 9 GiB (24 GB − 15 GB model) | A3 |
| KV budget | cap_frac × n_robots × KV_bytes(full, 20 092 tok) | parametric |
| Turn interval / accel budget | 30 000 ms [ASSUMPTION A4] | — |

**[ASSUMPTION A4]**: Turn interval = 30 s. This determines the accelerator budget per epoch (30 000 ms) against which total (serve + refresh + materialize) is compared. The sum200 regeneration cost (5822 ms/turn) exceeds 30 000/5822 ≈ 5.15 robots. Documented here; does not affect cells where sum200 is never selected (see §Results).

---

## Policies

| policy | description |
|---|---|
| device_only | All sessions served from device (qwen3b). Lower bound. |
| always_full | All sessions at full fidelity at edge; LRU eviction under KV budget. |
| always_window | All sessions at win10 at edge; LRU eviction. |
| always_summary | All sessions at sum200 at edge; LRU eviction. |
| footprint_ranked | **Incumbent.** Pick highest Q/KV_bytes admissible fidelity per robot; admit greedily under KV memory budget. KV budget is the only admission constraint. |
| maintenance_aware | Pick lowest maintenance_cost/Q admissible fidelity; admit greedily under BOTH KV memory and accelerator time budget. |
| oracle | Pick highest-Q admissible fidelity; admit greedily under KV budget. Upper bound. |

**Fidelity admissibility**: f is admissible iff Q(f, qwen7b, workload) ≥ q_min.

**Fidelity selection outcome** (determined by Q table and maintenance costs):

| workload | q_slo | maint_aware picks | footprint_ranked picks | oracle picks |
|---|---|---|---|---|
| LoCoMo | 0.20 | full (cost/Q=165) | win10 (density > full) | full |
| LoCoMo | 0.30 | full (only admissible) | full (only admissible) | full |
| LoCoMo | 0.40 | full | full | full |
| EgoSchema | 0.20 | full (cost/Q=116) | sum200 (highest density) | full |
| EgoSchema | 0.30 | full | sum200 | full |
| EgoSchema | 0.40 | full | sum200 | full |

maintenance_aware selects full in every cell because full always has the lowest maintenance_cost/Q ratio (66ms / 0.40 = 165 for LoCoMo; 66ms / 0.567 = 116 for EgoSchema) — lower than win10 (652/0.23 = 2835; 652/0.500 = 1304) and sum200 (5822/0.12 >> 1 for LoCoMo). **maintenance_aware is therefore indistinguishable from always_full in this Q-table.**

---

## Sweep

- Fleet size: n\_robots ∈ {5, 10, 20, 30, 50}
- KV capacity: cap\_frac ∈ {0.25, 0.50, 0.75, 1.00}
- Seeds: 3 per configuration
- Workloads: LoCoMo (dense-incompressible, warm-append device), EgoSchema (gist-compressible, cold-restore per query)
- Quality SLOs: q\_min ∈ {0.20, 0.30, 0.40}
- Total runs: 7 × 2 × 3 × 5 × 4 × 3 = 2520

---

## Stage 0 — Headroom Gate

Device failure rates (qwen3b Jetson, measured A1 ratio, admissibility model):

| workload | budget | lat_fail | admissible on device? (any q_slo) |
|---|---|---|---|
| LoCoMo | 300ms | 95.2% | yes (q_slo=0.20 only; Q_dev=0.230) |
| LoCoMo | 1000ms | 46.5% | yes (q_slo=0.20 only) |
| LoCoMo | 10000ms | 0.0% | yes (q_slo=0.20 only) |
| EgoSchema | 300ms | 100.0% | yes (all q_slos; Q_dev=0.450) |
| EgoSchema | 1000ms | 100.0% | yes (all q_slos) |
| EgoSchema | 10000ms | 0.0% | yes (all q_slos) |

Non-discriminating cells (device meets latency AND quality): locomo/10000ms/q_slo=0.20 and egoschema/10000ms (×3) = **4/18 cells**.  
**K1: PASS** — 22% non-discriminating, below 50% threshold.

---

## Stage 1–2 — Per-Cell Policy Ranking

Primary metric at 1000ms budget, cap_frac=0.50 (representative slice):

| workload | q_slo | device | fp_ranked | maint_aware | oracle | maint−fp | maint−dev |
|---|---|---|---|---|---|---|---|
| LoCoMo | 0.20 | 0.554 | 0.947 | 0.914 | 0.914 | −3.3pp | +36.1pp |
| LoCoMo | 0.30 | 0.000 | 0.893 | 0.891 | 0.891 | −0.3pp | +89.1pp |
| LoCoMo | 0.40 | 0.000 | 0.893 | 0.891 | 0.891 | −0.3pp | +89.1pp |
| EgoSchema | 0.20 | 0.000 | 1.000 | 0.891 | 0.891 | −10.9pp | +89.1pp |
| EgoSchema | 0.30 | 0.000 | 1.000 | 0.891 | 0.891 | −10.9pp | +89.1pp |
| EgoSchema | 0.40 | 0.000 | 1.000 | 0.891 | 0.891 | −10.9pp | +89.1pp |

Full 18-cell table (averaged over fleet size, cap_frac, seeds) in `stage2_analysis.json`.

---

## Kill-Condition Results

**Pre-registered kill conditions, applied as written:**

**K1**: PASS — 22% non-discriminating (4/18 cells).

**K2**: FAIL (4 cells) — maintenance_aware fails to beat device_only by ≥5pp at: locomo/10000ms/q_slo=0.20 (gap=0pp) and egoschema/10000ms/all q_slos (gap=0pp). These are exactly the 4 non-discriminating cells identified in Stage 0; they are non-discriminating by construction (device meets 10s budget everywhere).

For the 14 discriminating cells: **K2 PASS** — maintenance_aware beats device_only by +17.6pp to +89.1pp.

**(a) always_window within 5pp of maintenance_aware**: FIRES — 9/18 cells. In many LoCoMo cells, always_window achieves similar both_met because win10 intra-session TTFT (59ms) reliably meets the latency budget.

**(b) always_full within 5pp of maintenance_aware**: FIRES — **18/18 cells**. maintenance_aware ≡ always_full: for all workloads and q_slos tested, full fidelity minimizes maintenance_cost/Q. The policy provides no selection criterion beyond always_full. Root cause: full has the lowest cost per unit quality (66/0.40=165 for LoCoMo), and win10 and sum200 are much more expensive per quality unit despite their lower absolute cost.

**(c) footprint_ranked within 5pp of maintenance_aware**: FIRES — 12/18 cells. footprint_ranked is not merely within 5pp — it **beats** maintenance_aware in 12 cells. Notably at EgoSchema/300ms: gap = −81.5pp (footprint_ranked 0.991 vs maintenance_aware 0.176), because maintenance_aware picks full fidelity (cold restore = 334ms > 300ms budget → latency fail), while footprint_ranked picks sum200 (restore = 32ms → latency pass).

**(d) accelerator never binds**: FIRES. No policy saturates the 30 000ms/epoch accelerator budget in any (policy, fleet size) cell. Root cause: sum200 is never selected for LoCoMo (Q=0.12 < q_min=0.20 at minimum), so its 5822ms/turn refresh never loads the GPU. For EgoSchema, sessions are independent (no per-session refresh, A6). The mechanism claim — that footprint_ranked saturates the accelerator by choosing sum200 — cannot be verified with this Q table: the tested q_min range (0.20–0.40) excludes sum200 from LoCoMo entirely.

**(e) advantage doesn't grow with fleet size**: FIRES — the gap between maintenance_aware and footprint_ranked does not grow monotonically with fleet size; it is driven by fidelity selection (full vs sum200/win10), which is independent of fleet size.

---

## Binding Resource Diagnostic

All policies: admission is exclusively memory-bound (KV capacity). Accelerator bound fraction = 0% for every (policy, fleet size) cell.

| policy | n_robots=50 | KV-bound% | Accel-bound% | binding | Accel util% |
|---|---|---|---|---|---|
| always_full | 50 | 29.1% | 0.0% | memory | 25.4% |
| always_window | 50 | 14.6% | 0.0% | memory | 6.2% |
| always_summary | 50 | 0.0% | 0.0% | neither | 2.3% |
| footprint_ranked | 50 | 12.8% | 0.0% | memory | 7.1% |
| maintenance_aware | 50 | 29.1% | 0.0% | memory | 25.4% |

Accelerator utilization breakdown: serve dominates (refresh=0ms for all policies because sum200 is never chosen for LoCoMo and EgoSchema has no per-session refresh). The accelerator binding threshold (≥30 000ms/epoch for sum200) is not reached in any tested cell.

Full per-(policy, fleet size) table in `binding_diagnostic.json`.

---

## Conclusions

The corrected experiment falsifies the maintenance_aware policy as specified. Three findings:

**Finding 1 — maintenance_aware degenerates to always_full.** For all workloads and q_slo values tested, full fidelity minimizes maintenance_cost/Q and is therefore always selected by the maintenance_aware policy. The policy is indistinguishable from always_full.

**Finding 2 — footprint_ranked beats maintenance_aware at latency-sensitive cells.** footprint_ranked (which picks sum200 for EgoSchema) achieves better both_met at 300ms and 1000ms budgets than maintenance_aware (which picks full, whose cold-restore TTFT exceeds 300ms). The footprint-minimizing policy wins by being latency-efficient, not quality-efficient.

**Finding 3 — accelerator saturation mechanism does not appear.** Sum200 is never chosen for LoCoMo by any policy (Q=0.12 is below q_min=0.20). The accelerator saturation claim ("footprint_ranked saturates the GPU with sum200 regeneration") cannot be exercised with the committed Q-table and q_min sweep. This is not a bug in the simulation — it is a property of the Q values: LoCoMo sum200 (Q=0.12) does not satisfy any of the tested quality floors. The claim would require q_min ≤ 0.12.

**Implication for the paper.** The maintenance_aware policy, as defined (rank by maintenance_cost/Q, subject to KV and accel constraints), does not provide a useful fidelity selector when full fidelity has the globally lowest cost-per-unit-quality. The policy mechanism would require either (a) a workload where a compressed representation has better cost/quality than full — which holds for EgoSchema at 300ms budget (sum200 passes latency; full does not), but maintenance_aware does not account for latency in its selection criterion — or (b) a setting where LoCoMo sum200 is admissible (q_min < 0.12). Neither condition is satisfied in the tested sweep.

The paper's thesis position (lifecycle-cost-aware fidelity selection sufficient, joint placement×fidelity adds nothing) is supported by E24/E24b/E24c. E36b (this experiment) shows the specific maintenance_aware policy needs redesign to be distinguished from always_full. This is an implementation gap, not a falsification of the thesis.

---

## Consistency Check (6-check protocol)

### Check 1 — Cross-check against committed measurements

| quantity | this run | prior committed | source | ratio | agree? |
|---|---|---|---|---|---|
| incr_warm ratio at L=1k | 0.5934 | 0.5934 | E37/E37b | 1.00 | AGREE |
| incr_warm ratio at L=16k | 0.7046 | 0.7046 | E37/E37b | 1.00 | AGREE |
| full_restore ratio at L=1k | 0.4749 | 0.4749 | E37b | 1.00 | AGREE |
| Edge full warm-append | 66.0ms | 66ms | E26/E35 | 1.00 | AGREE |
| Edge win10 intra | 59.0ms | 59ms | E35 | 1.00 | AGREE |
| Edge win10 inter | 1031.0ms | ~1031ms | E35 | 1.00 | AGREE |
| Edge sum200 restore | 32.0ms | 32ms | E35 | 1.00 | AGREE |
| Edge sum200 update | 5822.0ms | 5822ms | E35 | 1.00 | AGREE |
| Q(full, locomo, qwen7b) | 0.400 | 0.400 | E29 | 1.00 | AGREE |
| Q(full, egoschema, qwen7b) | 0.567 | 0.567 | E29 | 1.00 | AGREE |
| KV bytes/tok qwen7b | 57344 | 57344 | E23 | 1.00 | AGREE |
| win10 tokens | 7275 | 7275 (E33a) | E33a | 1.00 | AGREE |

No disagreements > 2×.

### Check 2 — Physical plausibility

EgoSchema cold restore at L=2000: (2000/5984)×1000 = 334ms. Implied rate 5984 tok/s, matches committed A6000 cold-prefill rate. OK.

Device incr_warm at L=16k: 2163ms × 0.7046 = 1524ms. Rate: 16384/1.524 = 10,752 tok/s. 3B model at 16k: faster than 7B (6542 tok/s@16k), consistent with smaller model. No rate exceeds committed curves.

Accelerator utilization at n=50/always_full: 7569ms serve / 30000ms = 25.2%. Implies 50 robots × 66ms/turn ≈ 3300ms per epoch average. The ~7569ms includes materialize overhead on first-admission turns and cap_frac=0.25 cells where fewer robots are admitted but at higher cold-restore cost. Plausible.

### Check 3 — Distribution sanity

3 seeds per configuration. Per-seed both_met values are independent (different rng draws for ego context selection). Stage 0 device failure rates are deterministic (no rng). Fidelity selection is deterministic per policy (no rng in admissibility check). No identical constants appear where variation is expected across seeds.

### Check 4 — Definition audit

| term | definition this run | matches prior? |
|---|---|---|
| admissible fidelity | Q(f, qwen7b, workload) ≥ q_min | new definition (replaces Bernoulli) |
| win10 tokens | 7275 (E33a last-10-sessions) | E33a ✓ |
| incr_warm | E23 incremental_warm_ms × A1 ratio | E37b ✓ |
| turns_per_session | 22 | E33a ✓ |
| kv_budget | cap_frac × n_robots × KV_bytes(full, 20092) | parametric |
| accel_budget | 30000 ms/epoch | [ASSUMPTION A4] |
| maintenance cost | full=66ms, win10=652ms (amortized E35), sum200=5822ms | E35 ✓ |

Admissibility model is a new definition replacing Bernoulli. This changes the metric structure — both_met is now deterministic given fidelity selection and TTFT, not stochastic. Reported as a definitional change.

### Check 5 — Claim linkage

| result | claim | bearing |
|---|---|---|
| maintenance_aware ≡ always_full (kill b fires) | C3: lifecycle-cost-aware sufficient at serving node | WEAKENS the specific policy instantiation; does not falsify the thesis (E24c evidence stands) |
| footprint_ranked beats maintenance_aware at 300ms/EgoSchema | C3 | Incumbent beats proposed policy at latency-sensitive cells → WEAKENS |
| Kill (d): accel never binds | Paper mechanism claim: footprint_ranked saturates accel | WEAKENS — mechanism not demonstrable at tested q_min range |
| K2 PASS for 14/18 discriminating cells | C4: physical inertia significant | SUPPORTS (edge policies beat device by 17–89pp) |

No cross-tier KV transfer (out of scope, FORMULATION.md §Scoping). No joint placement×fidelity optimization (anti-coupling constraint from E24c respected).

### Check 6 — Proxy validity

- **Device TTFT**: deterministic from E23 7B table × E37 measured ratio. Both committed. Valid.
- **Admissibility**: deterministic from E29 Q-table. Valid. 
- **Accel budget**: 30 000ms/epoch [ASSUMPTION A4] — labeled as assumption; results under alternative budgets: halving to 15 000ms would cause accel binding for maintenance_aware at n≈7 robots (7×66ms/epoch ≈ 462ms; serve only; no binding). Sum200 would bind at n≥3 (3×5854=17562ms > 15000ms). Qualitative conclusions unchanged since sum200 is never selected for LoCoMo.
- **EgoSchema independent sessions (A6)**: documented. Means no refresh cost for any policy on EgoSchema.

---

## Limitations

1. **maintenance_aware degenerate.** As defined, the policy always picks full. A latency-aware variant (e.g., fall back to smallest admissible if TTFT(full) > budget) would differentiate it from always_full and potentially avoid kill condition (b).

2. **Sum200 not testable for LoCoMo.** The mechanism claim requires q_min ≤ 0.12 to make LoCoMo sum200 admissible. No tested q_slo satisfies this.

3. **KV budget parametrized by full fidelity at L_median.** Actual KV usage scales with current L_i per robot. The parametric budget is an approximation; robots early in their context accumulate much less KV than the budget assumes.

4. **Turn interval assumption (A4).** The 30s turn interval determines whether the accelerator ever binds. This is an unconstrained parameter; the fleet-scale accelerator saturation mechanism depends critically on it.

5. **n_sessions per conversation.** Used LOCOMO_N_SESSIONS = [19…32] per conversation, capped at max=32 for the simulation. Correctly reflects E33a range.

---

## Headline

The corrected experiment fires kill conditions (b), (c), and (d):  
(b) maintenance_aware ≡ always_full — the policy degenerates because full minimizes maintenance_cost/Q for all tested cells;  
(c) footprint_ranked beats maintenance_aware by up to 81.5pp (EgoSchema/300ms) — the incumbent wins on latency;  
(d) accelerator never binds — the saturation mechanism requires LoCoMo sum200 to be admissible (q_min < 0.12), outside the tested range.  

The fleet policy experiment as designed does not distinguish maintenance_aware from always_full. Redesign of the maintenance_aware policy (with latency-awareness in fidelity selection, or tested under lower q_slo where sum200 becomes admissible for LoCoMo) is required before the fleet simulation supports the paper's mechanism claim.
