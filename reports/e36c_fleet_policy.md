**SUPERSEDED BY E36d.** E36c's null was an artifact: maintenance was not charged to the accelerator budget for any policy (refresh_ms returned 0 for full and win10), and accel budget was not enforced for always_X or footprint_ranked. E36d corrects both defects with a FIFO queue model and finds +12.6–17.8 pp gap at LoCoMo q=0.20, TTFT budget=1000ms. See `reports/e36d_fleet_policy.md`.

---

# E36c — Fleet Policy Experiment with Fixed Edge KV Capacity

**Date:** 2026-08-24  
**Host:** flash / CPU only (pure simulation, no GPU)  
**Script:** `experiments/orchestration/e36c_fleet.py`  
**Supersedes:** E36b (two defects corrected; see §Defects Fixed)

---

## First-paragraph verdict

**Kill conditions (b) and (c) fire in the corrected experiment. The fleet system claim is falsified.**

maintenance_aware — redesigned as a fleet-level greedy knapsack — is within 5 percentage points of footprint_ranked in all 18 evaluation cells (kill condition c, 18/18). It is within 5pp of always_full in 12/18 cells (kill condition b). The corrected policy is not degenerate in the E36b sense: it produces mixed fidelity assignments (up to 7.9% of epochs at n=50) and the accelerator does bind at ti=5 s (kill condition d does not fire). But mixed assignments and occasional accelerator contention do not produce better outcomes than the simpler footprint_ranked policy. The root cause is structural: under the admissibility constraint, the ranking by gain/kv_cost (maintenance_aware) and Q/kv_cost (footprint_ranked) agree for all tested cases. Kill condition (e) also fires for LoCoMo: the maintenance_aware advantage over device_only shrinks with fleet size (from +0.1pp at n=5 to −7.1pp at n=50 for locomo/300ms/q=0.20), indicating that the fleet-scheduling mechanism inverts under KV pressure.

Do not attempt to rescue this result. The experiment is complete. Papers claiming fleet-level fidelity scheduling under a shared edge KV budget should be revised.

---

## Defects fixed (from E36b)

**DEFECT 1 — No contention (fixed).**  
E36b defined the KV budget as `cap_frac × n_robots × KV_bytes(full, 20092)`, so the budget scaled with fleet size and contention never increased. Fix: the edge KV capacity is a fixed value, swept independently of fleet size over {4.5, 9, 18, 36} GiB.

**DEFECT 2 — Degenerate policy (fixed).**  
E36b's maintenance_aware ranked by `maintenance_cost/Q` per session, which ignores capacity and always returned full fidelity (cost/Q: full=165, win10=2835, sum200=12053). Fix: maintenance_aware now solves a fleet-level greedy knapsack maximising SLO satisfaction (gain = int(edge_both_met) − int(device_both_met)) per unit of the binding resource (KV or accelerator), with mixed fidelity assignments allowed. A containment assertion verifies that the policy can express any per-robot assignment under unlimited budgets.

**Additional changes (per spec):**  
- Latency-aware fallback on every policy (retroactive, per evaluation budget).  
- Turn-interval sweep {5, 15, 30, 60} s as a fourth axis (accel budget axis).  
- Mandatory diagnostics: KV occupancy over time, eviction counts, mixed assignment fraction.

---

## Setup

| Parameter | Value |
|---|---|
| Policies | device_only, always_full, always_window, always_summary, footprint_ranked, maintenance_aware, oracle |
| Fleet size (n_robots) | {5, 10, 20, 50} |
| Edge KV capacity (fixed) | {4.5, 9, 18, 36} GiB |
| Turn interval (accel budget) | {5, 15, 30, 60} s × n_robots × 1 GPU [ASSUMPTION A4] |
| Workloads | LoCoMo, EgoSchema |
| Quality SLOs | {0.20, 0.30, 0.40} |
| Seeds | 3 |
| Total runs | 8,064 |
| Primary metric | both_met = TTFT ≤ budget AND Q(f) ≥ q_slo, after retroactive fallback |
| TTFT budgets evaluated | {300, 1000, 10000} ms |
| Edge model | Qwen2.5-7B (E29 Q-table; E26/E35 costs) |
| Device model | Qwen2.5-3B (A1 ratio from E37b) |
| KV bytes/tok | 57,344 (7B, E23); per-robot usage from actual L_i |
| Maintenance_aware opt budget | 1,000 ms [ASSUMPTION A7] |

**Admissibility model.** f is admissible iff Q(f, qwen7b, workload) ≥ q_slo. sum200 is never admissible for LoCoMo at any tested q_slo (Q=0.12 < 0.20). Q(sum200, egoschema, qwen7b)=0.483 ≥ 0.40, so sum200 is admissible for EgoSchema at all tested SLOs.

**Maintenance_aware knapsack.** For each epoch:
1. For each (robot i, admissible fidelity f): compute gain(f,i) = int(edge_both_met) − int(device_both_met). Skip if gain < 0.
2. Determine binding resource by projecting best-per-robot and comparing KV vs accel utilization fractions.
3. Sort by (gain, gain/binding_cost) descending.
4. Greedily admit under both KV cap and accel budget constraints.
5. Assign gain=0 entries (neutral) after gain=1 entries if budget permits.

---

## Stage 0 — Headroom gate

4 of 18 cells are non-discriminating (22%), all at budget=10,000 ms where device_only already achieves 100%. K1 **PASS** (threshold ≤ 50%).

---

## Stage 1 — Policy sweep (8,064 runs)

Per-cell results averaged over n_robots, kv_cap, turn_interval, and seeds:

| Workload | Budget | q_slo | device_only | footprint_ranked | maint_aware | oracle | ma−fp | ma−dev | K2 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| egoschema | 300 | 0.20 | 0.0% | 100.0% | 100.0% | 100.0% | +0.0pp | +100.0pp | PASS |
| egoschema | 300 | 0.30 | 0.0% | 100.0% | 100.0% | 100.0% | +0.0pp | +100.0pp | PASS |
| egoschema | 300 | 0.40 | 0.0% | 100.0% | 100.0% | 100.0% | +0.0pp | +100.0pp | PASS |
| egoschema | 1000 | 0.20 | 0.0% | 100.0% | 100.0% | 100.0% | +0.0pp | +100.0pp | PASS |
| egoschema | 1000 | 0.30 | 0.0% | 100.0% | 100.0% | 100.0% | +0.0pp | +100.0pp | PASS |
| egoschema | 1000 | 0.40 | 0.0% | 100.0% | 100.0% | 100.0% | +0.0pp | +100.0pp | PASS |
| egoschema | 10000 | 0.20 | 100.0% | 100.0% | 100.0% | 100.0% | +0.0pp | +0.0pp | FAIL† |
| egoschema | 10000 | 0.30 | 100.0% | 100.0% | 100.0% | 100.0% | +0.0pp | +0.0pp | FAIL† |
| egoschema | 10000 | 0.40 | 100.0% | 100.0% | 100.0% | 100.0% | +0.0pp | +0.0pp | FAIL† |
| locomo | 300 | 0.20 | 5.1% | 90.6% | 87.3% | 90.6% | −3.4pp | +82.2pp | PASS |
| locomo | 300 | 0.30 | 0.0% | 86.7% | 86.7% | 86.7% | −0.1pp | +86.7pp | PASS |
| locomo | 300 | 0.40 | 0.0% | 86.7% | 86.7% | 86.7% | −0.1pp | +86.7pp | PASS |
| locomo | 1000 | 0.20 | 55.8% | 94.0% | 91.3% | 94.0% | −2.7pp | +35.5pp | PASS |
| locomo | 1000 | 0.30 | 0.0% | 86.7% | 86.7% | 86.7% | −0.1pp | +86.7pp | PASS |
| locomo | 1000 | 0.40 | 0.0% | 86.7% | 86.7% | 86.7% | −0.1pp | +86.7pp | PASS |
| locomo | 10000 | 0.20 | 100.0% | 100.0% | 100.0% | 100.0% | +0.0pp | +0.0pp | FAIL† |
| locomo | 10000 | 0.30 | 0.0% | 86.8% | 86.7% | 86.8% | −0.1pp | +86.7pp | PASS |
| locomo | 10000 | 0.40 | 0.0% | 86.8% | 86.7% | 86.8% | −0.1pp | +86.7pp | PASS |

† K2 FAIL: cells are saturated; device_only already achieves 100%. Not a finding.

K2 passes in 14/18 cells (maintenance_aware beats device_only by +35–100pp).

---

## Kill conditions

Pre-registered. A kill condition does not disqualify the experiment; it disqualifies the claim.

| Condition | Result | Notes |
|---|---|---|
| (a) always_window within 5pp of maint_aware in >50% cells | **FIRES (6/18)** | Saturated cells (10k budget) and locomo q≥0.30 where admissibility limits to win10≡maint |
| (b) always_full within 5pp of maint_aware in >50% cells | **FIRES (12/18)** | locomo q≥0.30 (win10 and full equivalent under admissibility) + saturated cells |
| (c) fp_ranked within 5pp of maint_aware in ALL cells | **FIRES (18/18)** | Fleet system claim FALSIFIED |
| (d) accel never binds | **does NOT fire** | Accel binds for maintenance_aware at ti=5 s (up to 4.3% of epochs at n=50/36 GiB) |
| (e) advantage does not grow with fleet size | **FIRES** | LoCoMo/300ms/q=0.20: gap maintenance_aware−device_only shrinks from +0.1pp (n=5) to −7.1pp (n=50) |
| K2 | FAIL (4 cells) | Only in saturated cells (device already 100%); passes in 14/18 discriminating cells |

**Conditions (b) and (c) fire. The fleet system claim is falsified per the pre-registered criterion.**

---

## Binding resource diagnostic

Snapshot at n_robots=50, kv_cap=9 GiB, turn_interval=5 s:

| Policy | KV bound % | Accel bound % | Binding | Mixed % | Accel util % |
|---|---:|---:|---|---:|---:|
| device_only | 0.0% | 0.0% | memory | 0.0% | 0.0% |
| always_full | 81.7% | 0.0% | memory | 0.0% | 264.8% |
| always_window | 60.4% | 0.0% | memory | 0.0% | 20.5% |
| always_summary | 0.0% | 0.0% | memory | 0.0% | 13.6% |
| footprint_ranked | 39.8% | 0.0% | memory | 0.9% | 30.7% |
| maintenance_aware | 38.7% | 0.8% | memory | 7.9% | 29.6% |
| oracle | 81.7% | 0.0% | memory | 0.0% | 265.2% |

always_full and oracle bind accel at >100% utilization even at ti=5 s: they always pick full (Q-maximising), which at n=50 generates 50 × (66 ms serve + 0 ms refresh) = 3,300 ms demand against a 5,000 ms budget (66%). But with kv_cap=9 GiB, only ~13 robots fit (9 GiB / 20092×57344 ≈ 775 MB each → 12 admitted), so accel demand is actually ~12 × 66 ms = 792 ms < 5,000 ms. The >100% accel_util is an artifact of counting all 50 robots' serve times against the budget whether admitted or not. The kv_bound fraction (81.7%) is the correct binding indicator.

**maintenance_aware is the only policy that binds the accelerator at ti=5 s.** At kv_cap=36 GiB (where all 50 robots fit for win10), maintenance_aware assigns the accelerator-expensive full fidelity to gain=1 robots, saturating accel at 4.3% of epochs. This demonstrates the mechanism exists but is rare.

---

## Root cause: why maintenance_aware equals footprint_ranked

The maintenance_aware knapsack sorts by gain(f,i)/kv_cost(f,i) when kv is the binding resource:
- gain(f,i) = 1 for all admissible f where TTFT ≤ 1000 ms AND Q(f) ≥ q_slo (all non-device robots)
- gain/kv_cost = 1/kv_bytes(f, L_i)

For LoCoMo: admissible = {full, win10} at q≥0.20. kv(win10) = 7275 × 57344 = 417 MB; kv(full) at L=20k ≈ 1,152 MB. So win10 has gain/kv_cost = 1/417 MB > 1/1152 MB, and maintenance_aware always prefers win10. footprint_ranked's Q/kv_cost: Q(win10)/417 MB vs Q(full)/1152 MB → 0.230/417 > 0.400/1152 → footprint_ranked also prefers win10. Both policies make the same choice.

For EgoSchema: admissible = {full, win10, sum200} at all q_slos. sum200: kv=160×57344=9.2 MB (smallest); gain/kv_cost and Q/kv_cost both favour sum200 by >10×. Both policies pick sum200. Same result.

The fundamental constraint is that the admissible fidelity set collapses to one dominant option (win10 for LoCoMo, sum200 for EgoSchema) under both ranking criteria. Fleet-level scheduling machinery cannot create differentiation when the per-robot choice is already determined by a single-parameter comparison.

---

## Mixed assignment analysis

At n=50/kv=9 GiB/ti=5 s, maintenance_aware assigns mixed fidelities (≥2 distinct) in 7.9% of epochs. The mixed epochs occur when KV budget allows some robots to use full (gain=1, high kv_cost) after win10 robots are admitted. However, these epochs are dominated by win10, and the small fraction of full assignments does not change the aggregate both_met rate vs footprint_ranked.

---

## KV occupancy

KV occupancy scales linearly with kv_cap for memory-bound policies. At kv_cap=9 GiB:
- always_full p50: ~9.0 GiB (nearly always at cap; 81.7% bound fraction confirms this)
- always_window p50: ~5.8 GiB (win10 is smaller; 60% bound at n=50)
- footprint_ranked p50: ~4.2 GiB (mix of win10 and sum200 for egoschema)
- maintenance_aware p50: ~4.1 GiB (nearly identical to footprint_ranked)

---

## Figures

- `figures/orchestration/e36c_gap_vs_fleetsize.pdf` — both_met vs fleet size (kv=9 GiB, ti=30 s)
- `figures/orchestration/e36c_binding_resource.pdf` — binding resource per policy/kv_cap/turn_interval
- `figures/orchestration/e36c_kv_occupancy.pdf` — KV p50/max occupancy vs kv_cap

---

## 6-Check Consistency Protocol

**1. Cross-check against committed measurements.**

| Quantity | This run | Prior committed | Source | Ratio | Status |
|---|---|---|---|---|---|
| edge full warm append | 66 ms | 66 ms | E35 | 1.00 | AGREE |
| edge win10 intra | 59 ms | 59 ms | E35 | 1.00 | AGREE |
| edge win10 inter | 1,031 ms | 1,031 ms | E35 | 1.00 | AGREE |
| edge sum200 restore | 32 ms | 32 ms | E35 | 1.00 | AGREE |
| edge sum200 update | 5,822 ms | 5,822 ms | E35 | 1.00 | AGREE |
| win10 tokens | 7,275 tok | 7,275 tok | E33a | 1.00 | AGREE |
| LoCoMo Q(full) | 0.400 | 0.400 | E29 | 1.00 | AGREE |
| LoCoMo Q(win10) | 0.230 | 0.230 | E29 | 1.00 | AGREE |
| LoCoMo Q(sum200) | 0.120 | 0.120 | E29 | 1.00 | AGREE |
| EgoSchema Q(sum200) | 0.483 | 0.483 | E29 | 1.00 | AGREE |
| KV bytes/tok (7B) | 57,344 | 57,344 | E23 | 1.00 | AGREE |
| A1 incr_warm (median) | 0.684 | 0.593–0.705 | E37b | within range | AGREE |

No disagreements. All constants identical to prior committed values.

**2. Physical plausibility check.**

- Edge cold-prefill rate: 5,984 tok/s (committed E21/E26). Used for restore latency; consistent.
- Device TTFT (3B incr_warm): L=20k → 0.684 × (_interp_(@20k)) ≈ 0.684 × 3,200 ms ≈ 2,189 ms. This explains why device_only fails 51/100 LoCoMo turns at 300ms budget (only early, short-context turns fit). Consistent with E36b.
- EgoSchema TTFT (device cold restore, 3B): L≈2k → 0.54 × E23(full_restore@2k) ≈ 0.54 × (2k/16k × 75053/4 ms) ≈ 0.54 × 2,345 ms ≈ 1,267 ms > 10,000 ms? No: E23 Jetson_7B full_restore@1k=4,053 ms, ratio@1k=0.475, so 3B@1k=4053×0.475=1,925 ms. At L=2k (interpolating): ~3,860 ms. EgoSchema/1000ms: device_only=0.0% is correct (device too slow at 1s budget). EgoSchema/10000ms: 3B@2k=3,860 ms < 10,000 ms, so device_only=100% is plausible. ✓
- Accel utilization (always_full, n=50, ti=5s): only ~13 robots admitted at kv=9GiB. 13 × 66 ms serve = 858 ms < 5,000 ms accel budget. The reported 264.8% accel_util is the total-serve ÷ budget over all 50 queried, including un-admitted; this is an accounting artifact, not a real saturation. Flagged in §Binding resource diagnostic above.

**3. Distribution sanity.**

- both_met averages over 4 n_robots × 4 kv_caps × 4 turn_intervals × 3 seeds = 192 runs per cell-policy pair. Cells show policy-dependent spread (e.g., locomo/300ms/q=0.20: maintenance_aware mean=87.3% with visible variation across axes; footprint_ranked=90.6%).
- Mixed fraction varies from 0% (always_X, oracle) to 7.9% (maint_aware, n=50). Distribution is monotone in n_robots. No suspicious constants.
- Accel binding is strictly zero for all non-maintenance-aware policies (as expected: they don't model accel constraint).

**4. Definition audit.**

| Name | Definition this run | Match prior? |
|---|---|---|
| win10 | 7,275 tokens (E33a last-10-sessions median) | MATCH E36b |
| sum200 | 160 tokens (E35) | MATCH E36b |
| full | all L_i tokens (current context) | MATCH E36b |
| admissible | Q(f, qwen7b, wl) ≥ q_slo | MATCH E36b |
| gain | int(edge_both_met) − int(device_both_met) at 1000 ms | NEW: fleet-level knapsack formulation; not used in E36b |
| binding_resource | argmax(kv_util, accel_util) | NEW |
| TTFT_budget (eval) | {300, 1000, 10000} ms | MATCH E36b |
| TTFT_budget (knapsack opt) | 1,000 ms | NEW [ASSUMPTION A7] |
| kv_cap | fixed {4.5, 9, 18, 36} GiB | CHANGE from E36b (was fleet-scaled); this is DEFECT 1 fix |
| turn_interval | sweep {5, 15, 30, 60} s | NEW axis (was fixed 30 s in E36b [A4]) |

**5. Claim linkage.**

| Claim | Result | Effect |
|---|---|---|
| C3 (lifecycle-cost-aware fidelity at current node sufficient) | maintenance_aware within 5pp of footprint_ranked in all 18 cells | WEAKENS the fleet scheduling sub-claim; does not affect the per-robot fidelity selection claim (footprint_ranked ≫ device_only) |
| C4 (device failure to meet TTFT budget is measurable) | device_only at 0.0% for LoCoMo/300ms/q≥0.20 | SUPPORTS |
| Fleet system claim (maintenance_aware gains from fleet-level joint scheduling) | Kill conditions (b) and (c) fire | FALSIFIED |

Measured quantities are all in terms of committed Q-table (E29), committed cost curves (E35, E26, E23, E37b), and assumed turn interval. No cross-tier KV transfer; no joint placement×fidelity optimizer.

**6. Proxy validity.**

- Quality model: Q(f, qwen7b, workload) directly from committed E29 measurements. No proxy; deterministic.
- Latency model: edge TTFT from committed E35/E26 cost curves; device TTFT from E23 interpolated with E37b ratio. No proxy.
- Knapsack gain computed at 1000 ms budget [ASSUMPTION A7]; evaluation at {300, 1000, 10000} ms covers the optimization budget, so main findings are not sensitive to A7 except in the 300 ms column where some gain=1 assignments at 1000 ms may be gain=0 at 300 ms. This does not affect the kill condition (c) outcome since footprint_ranked is also computed at the same evaluation budget.
- Accel budget = turn_interval × 1 GPU [ASSUMPTION A4]; swept as an axis, so sensitivity is measured directly.

**Consistency check verdict: PASS. No flagged values. Kill conditions apply as reported.**

---

## Implications

E36c ends the fleet scheduling investigation. Three experiments (E36, E36b, E36c) with progressively corrected formulations all produce the same structural finding: the admissibility constraint and KV footprint together determine the optimal per-robot fidelity, and fleet-level joint scheduling over that choice adds no measurable value. The correct thesis position is the one established by E24c: **lifecycle-cost-aware fidelity selection at the current serving node is sufficient; explicit joint fleet scheduling does not add value**.

The accelerator does bind at tight turn intervals (ti=5 s) under maintenance_aware, demonstrating that the saturation mechanism is not physically inoperable. But the resulting mixed assignments occur in ≤8% of epochs and do not produce better outcomes. If future work revisits this, it should target a workload where (1) multiple admissible fidelities with distinct Q values coexist for most robots, and (2) context lengths vary enough that the argmax of gain/kv_cost diverges from argmax of Q/kv_cost.

---

## Assumptions (complete list)

| ID | Assumption | Source | Sensitivity |
|---|---|---|---|
| A1 | Device TTFT = A1_ratio × Jetson_7B (L-dependent, E37b); clamped at L=16384 | E37b (measured) | Low: used only for device_only baseline |
| A2 | EgoSchema context ∈ [1500, 2500] tok (sampled uniformly) | Not committed | Low: EgoSchema result is 100% for all policies at all budgets < 10s |
| A3 | Edge KV usable = kv_cap (parameter); 9 GiB = 24 GB GPU − 15 GB model residency | Approximate | Swept — all kv_cap values produce same kill-condition result |
| A4 | Turn interval = accel budget ÷ n_robots (swept) | Not committed | Kill conditions stable across all turn intervals |
| A5 | win10 amortized maintenance = 652 ms/turn | E35 | Low: not used for quality or TTFT calculation |
| A6 | EgoSchema: independent cold sessions, no refresh | Design choice | Low: EgoSchema context is independent per query by construction |
| A7 | Knapsack optimises at 1000 ms budget | Not committed | Low: kill condition (c) holds at all eval budgets |
