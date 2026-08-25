# E36e — Fleet Capacity Relationship

**Status:** Part A PASS (P1–P4), Part A2 PASS (P1b), Part B: S1 PASS, S2 FAIL (structural — see §S2 diagnosis), S3 PASS, S4 reported.

**The capacity relationship is real.** Representations differ in maintenance cost, which consumes shared accelerator time. The ordering of sessions supported under memory pressure and accelerator pressure is inverted. A rule that ranks by footprint selects the wrong representation in the accelerator-bound regime, leaving 7–26 pp of throughput on the table. The proposed `maintenance_aware` policy corrects this in the accel-bound regime but fails in the memory-bound regime because it uses accelerator capacity as its score without incorporating the memory ceiling. The correct policy (N_eff-ranked = min(N_mem, N_accel)) would pass S2 by construction; its implementation is left as an open item.

Script: `experiments/orchestration/e36e_fleet.py`  
Kill conditions: `research/KILL_CONDITIONS.md` (pre-registered 2026-08-24, supersedes E36–E36d)  
Primary result files: `results/orchestration/e36e_fleet/`

---

## Mechanism Verification (CLAUDE.md mandatory)

**Step 1 — Causal chain.** Maintenance costs differ by representation (FORMULATION.md §refresh: full=66ms/turn, win10=690ms amortized, sum200=5822ms). These costs consume shared accelerator time budgeted as `turn_interval × 1000ms` per epoch. The number of concurrent sessions the accelerator can support is N_accel = ⌊budget/(maint+serve)⌋. The number memory can support is N_mem = ⌊kv_cap/kv_per_session⌋. Effective capacity = min(N_mem, N_accel). Because the maintenance-cost ordering (full cheapest) and footprint ordering (sum200 smallest) are opposite, N_accel and N_mem rank representations in reversed order. A selection rule that ranks by footprint (Q/kv_bytes) picks the representation that maximizes N_mem but minimizes N_accel in the accelerator-constrained regime, reducing effective throughput. The paper claim is this capacity inversion; it is not a policy-tournament claim.

**Step 2 — All links present.** maint_ms non-zero and representation-dependent: full=66ms, win10_amz=690ms, sum200=5822ms (all committed; see Step 4 definition audit). N_accel varies by representation and turn interval (P1 verified). P3 confirms footprint_ranked selects the representation with lower N_eff (6 vs 8 sessions at ti=5s, kv=9GiB). P4 negative control confirms maintenance cost is the driver. No ABSENT or CONSTANT links.

**Step 3 — Representative trace** (n=50, kv=9GiB, ti=5s, q=0.20, locomo, ttft=1000ms, epoch 0). Epoch budget = 5000ms. maintenance_aware selects full for each robot (N_accel=40, N_mem=8; accel-bound regime, full is N_eff-optimal). Greedy admission: admits 8 robots, maint_used=8×66=528ms, serve=8×59=472ms, total=1000ms ≪ 5000ms budget. Remaining 42 robots: device TTFT for those with context_L>12K tokens ≈ 1200–1524ms > 1000ms SLO → device_both_met = False for 16 of 42. footprint_ranked selects win10 (Q/kv_bytes=5.51×10⁻¹⁰ > full). Admits 6: maint=6×690=4140ms, serve=6×59=354ms, total=4494ms ≤ 5000ms. 8 vs 6 edge robots → gap propagates to both_met. Observed maintenance_aware=0.711, footprint_ranked=0.579 (gap=+13.2pp). Matches prediction direction.

**Step 4 — Negative control.** With maint=0: N_accel(full)=N_accel(win10)=84 (budget/serve_ms only). Both policies select win10 (footprint_ranked wins on Q/kv_bytes; maintenance_aware by accel-ranked, tied at 84, falls back to same criterion). Rules converge; consistent with P4 analytic result.

**Step 5 — Alternative explanation.** `maintenance_aware` could outperform `footprint_ranked` simply by matching `always_full`, which happens to be optimal in the accel-bound regime for independent reasons. This is the intended mechanism (per KILL_CONDITIONS.md S2: matching always_full where full is optimal is a PASS). The distinguishing test is S3: footprint_ranked must be measurably worse in the accel-bound regime. S3 PASS: gap = +7–26pp across all kv_cap values at ti=5s.

---

## Six-Check Consistency Protocol (CLAUDE.md mandatory)

**Check 1 — Cross-check against committed measurements.**

| quantity | this run | prior committed | source | ratio | agree |
|---|---|---|---|---|---|
| maint_full_ms | 66.0 | 66.0 | E26/E34 | 1.00 | ✓ |
| maint_win10_slide_ms | 1031.0 | 1031.0 | E34 | 1.00 | ✓ |
| maint_win10_growth_ms | 36.0 | 36.0 | E34 | 1.00 | ✓ |
| maint_sum200_ms | 5822.0 | 5822.0 | E35 | 1.00 | ✓ |
| serve_full_ms | 59.0 | 59.0 | [ASSUMPTION B1] | 1.00 | n/a |
| serve_win10_ms | 59.0 | 59.0 | E35 | 1.00 | ✓ |
| serve_sum200_ms | 32.0 | 32.0 | E35 | 1.00 | ✓ |
| tokens_win10 | 7,275 | 7,275 | E33a | 1.00 | ✓ |
| tokens_sum200 | 160 | 160 | E29 | 1.00 | ✓ |
| Q(full, locomo) | 0.40 | 0.40 | E29 | 1.00 | ✓ |
| Q(win10, locomo) | 0.23 | 0.23 | E29 | 1.00 | ✓ |
| Q(sum200, locomo) | 0.12 | 0.12 | E29 | 1.00 | ✓ |
| KV_BYTES_PER_TOK | 57,344 | 57,344 | E23 | 1.00 | ✓ |
| L_locomo_median | 20,092 | 20,092 | E33a | 1.00 | ✓ |

No disagreements.

**Check 2 — Physical plausibility.** N_accel(full, ti=5s)=40: implies 40×125ms=5000ms = exactly 5s budget. ✓ N_accel(win10_amz, ti=5s)=6: 6×749ms=4494ms ≤ 5000ms. ✓ Device TTFT at L=16K: 2162.8×0.7046=1524ms (E23×E37 A1 ratio). ✓ No rate implies faster than committed curves.

**Check 3 — Distribution sanity.** both_met at (n=50, kv=9GiB, ti=5s, locomo, q=0.20, ttft=1000ms) across three seeds: maintenance_aware = {42:0.713, 123:0.709, 7:0.711} → IQR < 0.005. Spread is narrow but not constant (differs at three decimal places), consistent with small-fleet sampling noise. Not a caching artifact.

**Check 4 — Definition audit.**

| name | definition in this run | consistent with prior? |
|---|---|---|
| win10 | last 10 sessions; 7,275 tokens (E33a) | ✓ (E33a defines this) |
| sum200 | 200-token summary; 160 tokens KV (E29) | ✓ |
| full | full session history; L=20,092 tok median | ✓ (E33a) |
| turn | one robot query-response pair | ✓ |
| epoch | one turn_interval period; all robots served or fell back | defined here |
| session_idx | index of current session in robot's history (0..n_sess-1) | new term; consistent with LOCOMO_N_SESSIONS (E33a) |

**Check 5 — Claim linkage.** S3 gap (+7–26pp) supports FORMULATION.md §refresh (maintenance costs differ by representation and consume accelerator time) and §5 (prefill is proactive cost, not critical-path latency). S1 (regime-dependent optimum) supports FORMULATION.md §capacity (binding resource changes with turn rate). The S2 failure does not contradict the capacity claim; it diagnoses a policy that implements a truncated version of the optimal selection rule.

**Check 6 — Proxy validity.** both_met is a direct measurement of simultaneous quality-SLO and TTFT-SLO satisfaction, not a proxy. context_L as proxy for device TTFT is validated by Phase 1 cost profiling (E23×E37): device TTFT crosses 1000ms at L≈11,800 tokens. 32% of robots exceed this at epoch 0 with steady-state initialization.

All six checks pass.

---

## Part A — Primary Measurements (P1–P4)

*Committed values: KV_BYTES_PER_TOK=57,344 B/tok (E23), L_full_median=20,092 tok (E33a), TOKENS_WIN10=7,275 (E33a), TOKENS_SUM200=160 (E29), MAINT_FULL=66ms (E26/E34), MAINT_WIN10_SLIDE=1031ms (E34), MAINT_WIN10_GROWTH=36ms (E34), SLIDE_FRAC=0.657 (E34), MAINT_SUM200=5822ms (E35), SERVE_FULL=59ms [ASSUMPTION B1], SERVE_WIN10=59ms (E35), SERVE_SUM200=32ms (E35).*

### Sessions supported table (kv=9GiB; M=memory-bound, A=accel-bound)

| fidelity | ti=5s | ti=15s | ti=30s | ti=60s | N_mem |
|---|---|---|---|---|---|
| full | 8M | 8M | 8M | 8M | 8 |
| win10 (amortized) | 6A | 20A | 23M | 23M | 23 |
| win10 (slide only) | 4A | 13A | 23M | 23M | 23 |
| win10 (growth only) | 23M | 23M | 23M | 23M | 23 |
| sum200 | 0A | 2A | 5A | 10A | 1053 |

### P1 — Inverted orderings. PASS.

Memory ordering: **sum200 > win10 > full**. Accelerator ordering at all turn intervals: **full > win10 > sum200**. Fully inverted at all four ti values (5s, 15s, 30s, 60s).

### P2 — Binding-resource flip. PASS.

Crossover thresholds at kv=9GiB (below = accel-bound, above = memory-bound):

| fidelity | crossover ti (s) | in sweep [5–60s]? |
|---|---|---|
| full | 1.0s | No — always KV-bound in sweep |
| win10 (amortized) | **17.2s** | **Yes — flip observable** |
| win10 (slide) | 25.1s | Yes |
| sum200 | 6,164s | No — always accel-bound in sweep |

Thresholds are distinct (1.0 ≠ 17.2 ≠ 25.1 ≠ 6164). The full/win10 crossover at 17s is the central finding.

### P3 — Footprint selection lands on wrong side. PASS.

At ti=5s (accel-bound), q_slo=0.20 (admissible: full Q=0.40, win10 Q=0.23; sum200 inadmissible):

- Q/kv_bytes: win10 (5.51×10⁻¹⁰) > full (3.47×10⁻¹⁰) → footprint_ranked selects **win10** → 6 sessions
- N_accel: full (40) > win10 (6) → maintenance_ranked selects **full** → 8 sessions
- Delta: **2 sessions** (maint_ranked − fp_ranked)

### P4 — Negative control. PASS.

With maintenance costs set to zero: N_accel = budget/serve_ms for all fidelities (identical serve_ms=59ms for full and win10). footprint_ranked and maintenance_ranked both select the same representation. The inversion in P1 and the delta in P3 collapse. Maintenance cost is the driver.

### E36d "Path 2" re-examination

E36d attributed a residual gap at ti=60s to "Path 2": win10 slide maintenance (1031ms) > 1000ms TTFT SLO in the synchronous queue model. Under the proactive maintenance model (this experiment), served robots always have TTFT = serve_ms = 59ms — maintenance happened before the query arrived. Path 2 was an artifact of E36d's synchronous queue model and does not exist under the correct formulation.

At ti=60s: full=8 sessions (KV-bound), win10=23 sessions (KV-bound). Win10 supports 2.9× more sessions. The E36d gap at ti=60s was driven by the incorrect model.

---

## Part A2 — Three Addenda

### P1b — Effective capacity is non-monotone. PASS.

Effective capacity N_eff = min(N_mem, N_accel). Argmax across representations:

| ti | argmax | N_eff | interpretation |
|---|---|---|---|
| 5s | **full** | 8 | maintenance-minimizing extreme |
| 15s | **win10** | 20 | NEITHER EXTREME |
| 30s | **win10** | 23 | NEITHER EXTREME |
| 60s | **win10** | 23 | NEITHER EXTREME |

Win10 maximizes effective sessions at ti≥15s in 3/4 cells. This is the headline result of Part A.

**Scope clarification (a): The two-way result is a load-dependent crossover, not a three-point non-monotonicity.** The claim is that full → win10 is the optimal representation transition as turn rate decreases past the 17s crossover. This is a two-way comparison between the only two representations admissible for LoCoMo (q≥0.20). The non-monotone shape (win10 in the middle) arises because full has the worst memory footprint and win10 has worse accelerator efficiency than full — their min curves cross. The third representation (sum200) is inadmissible for LoCoMo on quality grounds and is excluded from the operating regime where the claim applies.

**Scope clarification (b): The three-way non-monotonicity requires a workload where sum200 is both quality-admissible and context-accumulating.** LoCoMo and EgoSchema each fail in one direction:
- LoCoMo: Q(sum200)=0.12 < q_slo=0.20. sum200 is quality-inadmissible. The three-way result does not apply.
- EgoSchema: Q(sum200)=0.483, admissible. But EgoSchema is single-session (n_sess=1) — robots never accumulate multi-session context. Maintenance cost for sum200 arises from regenerating a summary of the accumulated session history; with no accumulation, maint≈0. The three-way non-monotone result requires sum200's high maintenance cost to be exercised, which requires accumulated context. EgoSchema does not provide this.

No tested workload satisfies both conditions simultaneously. The three-way non-monotone result is a mathematical property of the capacity formulas but is not observable in either tested workload.

### Batching (Addendum 2)

Sum200 regenerates 160-token summaries — embarrassingly batchable under continuous batching (as in vLLM). Full and win10 use KV-append (single forward pass); batching gain for append is marginal.

**[ASSUMPTION B2] No batching speedup for append.** This is an assumption, not a measurement. Per scope clarification (c) below.

Batching speedup B applied to sum200 maintenance only (maint_eff = MAINT_SUM200_MS / B):

| B | sum200 N_accel(5s) | N_accel(15s) | N_accel(30s) | N_accel(60s) |
|---|---|---|---|---|
| 1 | 0 | 2 | 5 | 10 |
| 2 | 1 | 5 | 10 | 20 |
| 4 | 3 | 10 | 20 | **40** |
| 8 | **6** | 19 | 39 | 78 |
| 16 | 12 | 37 | 75 | 151 |

win10 reference (unchanged): 6 / 20 / 40 / 80.

- **Full inversion (full vs sum200 in accel):** Never collapses. Full always has the lowest maintenance (66ms) → highest N_accel for any B. B*=∞.
- **Partial sum200 recovery past win10 at ti=5s:** At B≈8.
- **Three-way non-monotone (all three representations):** Holds for B≤2. Collapses at B=4, ti=60s (sum200 N_eff=40 > win10 N_eff=23).
- **Two-way non-monotone (full vs win10, LoCoMo operative claim):** Immune to batching. Full and win10 both use append; no batching speedup applies. The crossover at ti≈17s persists for any B.

**Scope clarification (c): No batching speedup for append is an assumption, not a measurement.** The claim that full and win10 benefit only marginally from batching rests on the observation that KV-append is a single incremental forward pass already handled by the serving stack's existing batch queue — additional parallelism from batching many append operations together does not compound with per-session throughput the way decoding batches do. This has not been measured. A measurement of append throughput under N concurrent append requests (N ∈ {1,4,16,50}) would be needed to confirm the assumption. If append is also batchable (e.g., via prefix-sharing across similar sessions), the two-way non-monotone could also shift with B, and this analysis should be rerun.

### Refresh policy axis (Addendum 3)

For sum200 only. [ASSUMPTION A2a]: stale trigger rate R(K) ≈ K/22 for LoCoMo (uniform evidence distribution, E33a; lower bound on miss rate). E27 periodic-K numbers NOT used (flagged buggy).

| policy | accel demand/turn | deadline miss | N_accel(5s) | N_accel(60s) |
|---|---|---|---|---|
| eager (proactive) | 5,822ms | 0.0% | 0 | 10 |
| periodic-2 (proactive) | 2,911ms | 0.0% | 1 | 20 |
| periodic-5 (proactive) | 1,164ms | 0.0% | 4 | 50 |
| periodic-10 (proactive) | 582ms | 0.0% | 8 | 97 |
| lazy (K=1) | 265ms | 4.5% | 16 | 202 |
| lazy (K=5) | 1,323ms | 22.7% | 3 | 44 |
| lazy (K=10) | 2,646ms | 45.5% | 1 | 22 |

Frontier: proactive policies trade accelerator utilization for zero deadline misses; lazy policies accumulate deadline misses at rate R (each miss = TTFT of 5854ms >> 1000ms SLO). Periodic-10 is Pareto-best on accelerator among proactive options.

- Three-way non-monotone collapses at periodic-5 (sum200 N_accel(60s)=50 > win10=23).
- Two-way non-monotone (full vs win10, LoCoMo): insensitive — no regeneration axis for append.
- For LoCoMo at q≥0.20: sum200 is quality-inadmissible. The refresh axis is moot for the LoCoMo headline.

---

## Part B — Fleet Simulation

### Initialization state (corrected)

**Bug corrected:** prior run initialized all robots at `session_idx=0` (session birth), making context_L tiny (L_mean=382 tokens) and device TTFT fast (≤400ms). All policies produced both_met=1.000 — the mechanism was unexercised. Classified as INCONCLUSIVE per CLAUDE.md Rule 2.

**Fix applied:** `ph_sess = rng.randint(0, n_sess-1)` — both session age and turn phase are now desynchronized at initialization.

**Realized initialization state** (n=50, seed=42, locomo):

| metric | epoch 0 | epoch 30 (final) |
|---|---|---|
| session_idx: min | 0 | 1 |
| session_idx: max | 21 | 22 |
| session_idx: mean | 9.9 | 11.0 |
| context_L: min | 207 | 1,450 |
| context_L: max | 19,703 | 20,960 |
| context_L: mean | 9,520 | 10,692 |
| robots above 12K threshold (device TTFT>1000ms) | **16/50 (32%)** | **18/50 (36%)** |
| robots at session ceiling (clamped) | 4/50 | 7/50 |

Fleet is in steady state at epoch 0: 32% of robots have accumulated enough context that device fallback fails the TTFT SLO.

**Session-end behavior:** `_advance_robot` uses `session_idx = min(session_idx+1, n_sess-1)`. When a robot reaches its final session (session_idx = n_sess−1), it remains there — context_L approaches and stays at ctx_tokens. There is no restart at session_idx=0. There is no churn. The context-length distribution is monotonically non-decreasing per robot over the run. No robots exit the simulation.

### Mechanism verification post-fix (negative control)

Representative cell (n=50, kv=9GiB, ti=5s, locomo, q=0.20, ttft=1000ms):

| policy | both_met |
|---|---|
| always_full | 0.711 |
| always_window | 0.642 |
| footprint_ranked | **0.579** |
| maintenance_aware | **0.711** |
| device_only | 0.562 |

Gap (maintenance_aware − footprint_ranked): **+13.2pp**. both_met ≠ 1.000 — mechanism activated. Prediction was 0.20–0.70; realized 0.57–0.71, within range.

Negative control with maint=0: N_accel(full)=N_accel(win10)=84 (serve_ms=59ms only). Both policies select win10. Rules converge. Consistent with P4.

### S1 — Best fixed representation is regime-dependent. PASS.

Primary: locomo, q=0.20, ttft=1000ms, n=50.

| kv | ti=5s best | ti=60s best | regime-dependent? |
|---|---|---|---|
| 4.5 GiB | always_full (0.574) | always_window (0.592) | **Yes** |
| 9.0 GiB | always_full (0.659) | always_window (0.702) | **Yes** |
| 18.0 GiB | always_full (0.822) | always_window (0.957) | **Yes** |
| 36.0 GiB | always_full (1.000) | always_full (1.000) | No (saturation) |

At kv=36GiB: edge capacity (N_mem(full)=33, N_mem(win10)=92) exceeds n_robots=50 for window representation at most turn rates; results saturate at 1.000 for multiple policies. This is a saturation cell, not a counterexample.

At kv≤18GiB: always_full optimal at ti=5s (accel-bound), always_window optimal at ti≥30s (memory-bound). The crossover is between ti=5s and ti=30s, consistent with the Part A analytic prediction of ti≈17s (amortized win10 crossover).

**S1 PASS** — best fixed representation changes with turn interval in 3/4 kv_cap values.

### S2 — maintenance_aware matches or beats best_fixed per regime. FAIL (2 cells).

| kv | ti | best_fixed | bf_val | ma_val | regret | verdict |
|---|---|---|---|---|---|---|
| 4.5 | 5s | always_full | 0.574 | 0.574 | +0.000 | PASS |
| 4.5 | 15s | always_window | 0.592 | 0.574 | **+0.018** | PASS |
| 4.5 | 30s | always_window | 0.592 | 0.574 | **+0.018** | PASS |
| 4.5 | 60s | always_window | 0.592 | 0.574 | **+0.018** | PASS |
| 9.0 | 5s | always_full | 0.659 | 0.659 | +0.000 | PASS |
| 9.0 | 15s | always_window | 0.700 | 0.659 | **+0.041** | PASS |
| 9.0 | 30s | always_window | 0.702 | 0.659 | **+0.043** | PASS |
| 9.0 | 60s | always_window | 0.702 | 0.659 | **+0.043** | PASS |
| 18.0 | 5s | always_full | 0.822 | 0.822 | +0.000 | PASS |
| 18.0 | 15s | always_full | 0.822 | 0.822 | +0.000 | PASS |
| **18.0** | **30s** | **always_window** | **0.950** | **0.822** | **+0.128** | **FAIL** |
| **18.0** | **60s** | **always_window** | **0.957** | **0.822** | **+0.135** | **FAIL** |
| 36.0 | 5s | always_full | 0.903 | 0.903 | +0.000 | PASS |
| 36.0 | 15–60s | always_full | 1.000 | 1.000 | +0.000 | PASS |

**S2 FAIL: 2/16 cells exceed 5pp regret.** Both failures are at kv=18GiB, ti≥30s.

**Structural diagnosis.** At kv=18GiB, ti=30s:
- N_mem(full)=16, N_accel(full,30s)=240. Effective N_eff(full)=16 (memory-bound).
- N_mem(win10)=46, N_accel(win10,30s)=40. Effective N_eff(win10)=40 (accel-bound).
- Win10 supports 40 sessions vs full's 16. Always_window correctly exploits this.
- `maintenance_aware` selects by N_accel score: full scores 240 >> win10 scores 40. It selects full.
- This is correct in the accel-bound regime (where N_accel is the binding constraint) but wrong in the memory-bound regime (where N_accel is non-binding and the correct score is N_mem).

The policy uses N_accel as its selection score unconditionally, which is only optimal when the accelerator is the binding constraint. The correct selection criterion is **N_eff = min(N_mem, N_accel)**, which reduces to N_accel in the accel-bound regime (where the present policy is correct) and to N_mem in the memory-bound regime (where the present policy fails).

**Per KILL_CONDITIONS.md:** "P1-P4 pass, S2 or S3 fail: the relationship is real but not exploitable by the proposed rule. Report the characterization and the failure of the rule, including why."

The rule fails for a diagnosed structural reason. An N_eff-ranked policy would pass S2 by construction — it exactly recovers the Part A analytic optimum. Implementing N_eff-ranking requires knowing kv_cap at policy-selection time, which is available to the serving tier. This is a policy design revision, not a change to the capacity claim.

### S3 — footprint_ranked measurably worse where accelerator binds. PASS.

Accel-bound regime: ti=5s (per Part A, full is accel-bound only at ti<1s; win10 is accel-bound at ti<17s; at ti=5s both are accel-constrained for their respective memory footprints at kv≤18GiB).

| kv | fp_ranked | maint_aware | gap | verdict |
|---|---|---|---|---|
| 4.5 GiB | 0.504 | 0.574 | **+7.0pp** | PASS |
| 9.0 GiB | 0.578 | 0.659 | **+8.1pp** | PASS |
| 18.0 GiB | 0.640 | 0.822 | **+18.1pp** | PASS |
| 36.0 GiB | 0.640 | 0.903 | **+26.3pp** | PASS |

**S3 PASS** — footprint_ranked is 7–26pp worse than maintenance_aware at ti=5s in all four kv_cap values. The gap grows with kv_cap because larger kv_cap raises N_mem, making the full-representation selection by maintenance_aware more valuable (N_eff(full) rises with kv_cap while N_eff(win10_at_5s)=6 remains fixed).

### S4 — Activation region. (Reporting requirement.)

Activating cells (gap > 1pp, maintenance_aware vs footprint_ranked): **40/288**.

Non-activating cells by structural reason:

| reason | count |
|---|---|
| EgoSchema: no accumulation (single-session, maint≈0) | 144 |
| LoCoMo q≥0.30: only full admissible (no choice) | 70 |
| Large kv + slow turnrate: both memory-bound, gap from other source | 12 |
| Near-saturation: both policies close to 1.000 ceiling | 12 |
| Other (small fleet, non-binding regimes) | 10 |

**Activation conditions:** locomo workload, q_slo=0.20 (both full and win10 admissible), kv_cap≤18GiB (both representations create capacity pressure), ti≤15s (accelerator constrains win10, creating differentiation). The mechanism does not activate in EgoSchema because that workload involves single sessions with no maintenance accumulation (append-only context, no cross-session summary regeneration). It does not activate at q≥0.30 for LoCoMo because only full is admissible — there is nothing to choose between.

---

## Assumptions

| label | assumption | status |
|---|---|---|
| B1 | SERVE_FULL_MS = 59ms (same as win10 intra-session, E35) | Unverified; win10 intra-session from E35; full may differ. |
| B2 | No batching speedup for KV-append (full, win10) | Unverified. Continuous batching of append operations could reduce per-session effective maint. Measurement needed: N concurrent appends, N∈{1,4,16,50}. |
| A2a | Stale trigger rate R(K) ≈ K/22 for LoCoMo | Derived from uniform evidence distribution assumption + E33a turns. E32 periodic-K not used (buggy). Lower bound. |

---

## Verdict against kill conditions

**P1: PASS.** Memory ordering inverted relative to accelerator ordering at all turn intervals.  
**P2: PASS.** Binding resource flips at representation-specific thresholds (full≈1s, win10≈17s, sum200≈6164s).  
**P3: PASS.** Footprint_ranked selects 6 sessions; maintenance_ranked selects 8 sessions; delta=2 at ti=5s, kv=9GiB.  
**P4: PASS.** Inversion and delta collapse with maintenance costs set to zero.  

**S1: PASS.** Best fixed representation is always_full at ti=5s and always_window at ti≥30s (for kv≤18GiB). Regime-dependent.  
**S2: FAIL (structural).** maintenance_aware uses N_accel as selection score; this is correct in the accel-bound regime but wrong in the memory-bound regime (kv=18GiB, ti≥30s; regret +12.8–13.5pp). The correct policy is N_eff-ranked = min(N_mem, N_accel). Capacity claim is unaffected.  
**S3: PASS.** footprint_ranked is 7–26pp worse than maintenance_aware in the accel-bound regime (ti=5s) at all four kv_cap values.  
**S4:** Reported. 40/288 cells activate. Structural reason stated for all 248 non-activating cells.

**Paper outcome (per KILL_CONDITIONS.md):** P1–P4 pass, S2 fails due to a diagnosed policy design issue. Outcome: "the relationship is real but not exploitable by the proposed rule." The paper contribution is the capacity characterization (P1–P4, Part A analytic result) plus S3 evidence that the correct regime-aware policy outperforms footprint_ranked in the accel-bound regime. The N_eff-ranked policy is the natural completion; implementing it and re-verifying S2 is an open item.

---

*After-task protocol: update research/EXPERIMENTS.md E36e row, append to results/INDEX.md, update research/STATUS.md.*

**S2 resolution (E36f):** E36f implemented neff_ranked and found S2 still fails in 3 cells at ti=5s (new failure mode: dynamic-L mixed-fleet effect); the E36e S2 cells (kv=18GiB, ti≥30s) now pass. See `reports/e36f_neff_policy.md`.
