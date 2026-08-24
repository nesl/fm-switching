> **SUPERSEDED.** E36 and the first E36b used wrong policies (no footprint_ranked incumbent,
> wrong quality model, missing binding-resource diagnostic). Corrected experiment: see
> `reports/e36b_fleet_policy.md` (rewrite, 2026-08-24).

# E36 — Maintenance-Aware Fleet Admission and Representation Policy

**Date:** 2026-08-23  
**Host:** flash / CPU only (pure simulation, no GPU)  
**Script:** `experiments/orchestration/e36_fleet.py`  
**Results:** `results/orchestration/e36_fleet/`

---

**A1 resolved (2026-08-24):** Assumption A1 has been measured (E37/E37b). The measured incr\_warm ratio is 0.593–0.705 (L-dependent, median 0.684 across LoCoMo turns), refuting both the s=0.43 lower bound (too optimistic by 38%) and s=1.00 upper bound. At the measured ratio, device\_only fails 46.5% of LoCoMo 1s queries; K2 gap ≈11pp — **K2 PASSES at the measured device speed**. See `reports/phase1_cost_profiling.md §Measured A1 ratio`. This report is superseded by E36b for any conclusion that depended on the A1 assumption.

---

## Summary

E36 tests whether a lifecycle-cost-aware fidelity selection policy (lifecycle_aware)
beats device-only serving in a robot fleet under three TTFT budgets × three quality SLOs
× two workloads × two A1 sensitivity bounds.  K2 is violated: lifecycle_aware fails to
beat device_only by the required ≥5pp threshold in 3/36 cells — all at the locomo /
1000ms budget / s=0.43 A1 bound.  Per the pre-registered protocol, this is reported here
with no policy tuning.  The violation is sensitivity-driven: when qwen3b is assumed to be
2.3× faster than qwen7b (s=0.43), device_only already serves 87.7% of LoCoMo turns within
1000ms via warm-append, leaving little room for edge to help on latency.

---

## Assumptions (load-bearing)

**A1 [NOT MEASURED, LOAD-BEARING]:**  qwen3b Jetson time = s × qwen7b Jetson time.
s is a time ratio (not a rate ratio).  s=0.43 is the 3B/7B parameter-count ratio,
used as a lower bound.  s=1.00 means no speedup, used as an upper bound.  The Jetson
qwen3b measurement is currently running on the Jetson hardware and will replace this
assumption once committed.  All Stage 2 results are shown at both bounds.

**A2 [NOT MEASURED]:**  EgoSchema full-context size ≈ 1500–2500 tokens.  Not committed.
Used to compute device cold-restore TTFT for EgoSchema queries.

**A4 [INTERPOLATION]:**  LoCoMo incr_warm for L ∈ (16384, 24576) is extrapolated at the
rate from the last measured point (L=16384).  Does not extrapolate past the infeasibility
boundary at L=24576 (E23: infeasible, not a slower measured rate).

---

## EgoSchema modeling note

EgoSchema is modeled as **short independent sessions: cold restore per query, no accumulated
context, no persistent session state on the device**.  Each EgoSchema query arrives as an
independent 1500–2500-token context.  Device_only serves EgoSchema by cold-restoring the
full context on Jetson per query; edge policies restore the representation (sum200: 32ms,
win10: 59ms, full: ~250–420ms) once and serve the query.  Discriminating cells for
EgoSchema reflect **per-query materialization latency**, not maintenance cost.  EgoSchema
is the gist-compressible regime and is not described as a long-lived compressible session.

---

## Stage 0 — Headroom Gate

**Corrected model:**
- LoCoMo device_only: warm-append per turn, continuous session on Jetson (64GB unified,
  no eviction).  Device TTFT = E23 `incr_warm_ms` × A1 scale.
- EgoSchema device_only: cold restore per query (independent sessions).
  Device TTFT = E23 `full_restore_ms` × A1 scale.

**Gate (K1):** PASS — 4/18 cells non-discriminating (22%) at both A1 bounds.

Non-discriminating cells (device meets quality AND latency ≤5% fail rate):
| workload   | budget | q_slo | reason |
|---|---|---|---|
| locomo     | 10000ms | 0.20 | Q_device=0.230 ≥ 0.20; warm-append 0% fail at 10s |
| egoschema  | 10000ms | 0.20 | Q_device=0.450 ≥ 0.20; cold-restore 0% fail at 10s |
| egoschema  | 10000ms | 0.30 | Q_device=0.450 ≥ 0.30; 0% fail |
| egoschema  | 10000ms | 0.40 | Q_device=0.450 ≥ 0.40; 0% fail |

LoCoMo warm-append latency failure rates by budget and A1 bound:
| budget | s=0.43 | s=1.00 |
|---|---|---|
| 300ms  | 87.3%  | 97.1%  |
| 1000ms | 12.1%  | 70.2%  |
| 10000ms | 0.0%  |  0.0%  |

EgoSchema cold-restore latency failure rates:
| budget | s=0.43 | s=1.00 |
|---|---|---|
| 300ms  | 100.0% | 100.0% |
| 1000ms | 100.0% | 100.0% |
| 10000ms |  0.0% |  0.0%  |

---

## Stage 1 — Fleet Simulation

**Configuration:**  
- Policies: device_only, edge_full_lru, edge_win10_lru, edge_sum200_lru, reactive,
  budget_aware, lifecycle_aware  
- n_robots ∈ {5, 10, 20} × cap_frac ∈ {0.25, 0.50, 0.75, 1.00} × 3 seeds × 2 workloads
  × 3 q_SLOs × 2 A1 scales = 3,024 runs  
- n_sessions = 20 per run

**Metric:** `both_met` = fraction of queries satisfying TTFT ≤ budget AND quality correct.

---

## Stage 2 — Per-Cell Policy Ranking

**Metric:** `both_met`, averaged over n_robots × cap_frac × seeds.

### LoCoMo (dense-incompressible; warm-append device model)

| budget  | q_slo | scale | #1 policy        | both_met | vs device | K2   |
|---|---|---|---|---|---|---|
| 300ms   | 0.20  | 0.43  | reactive         | 0.149    | +10.8pp   | PASS |
| 300ms   | 0.20  | 1.00  | edge_full_lru    | 0.142    | +13.2pp   | PASS |
| 300ms   | 0.30  | 0.43  | reactive         | 0.149    | +10.8pp   | PASS |
| 300ms   | 0.30  | 1.00  | edge_full_lru    | 0.142    | +13.2pp   | PASS |
| 300ms   | 0.40  | 0.43  | reactive         | 0.149    | +10.8pp   | PASS |
| 300ms   | 0.40  | 1.00  | edge_full_lru    | 0.142    | +13.2pp   | PASS |
| 1000ms  | 0.20  | 0.43  | edge_full_lru    | 0.235    | +0.7pp    | **FAIL** |
| 1000ms  | 0.20  | 1.00  | edge_full_lru    | 0.235    | +14.2pp   | PASS |
| 1000ms  | 0.30  | 0.43  | edge_full_lru    | 0.235    | +0.7pp    | **FAIL** |
| 1000ms  | 0.30  | 1.00  | edge_full_lru    | 0.235    | +14.2pp   | PASS |
| 1000ms  | 0.40  | 0.43  | edge_full_lru    | 0.235    | +0.7pp    | **FAIL** |
| 1000ms  | 0.40  | 1.00  | edge_full_lru    | 0.235    | +14.2pp   | PASS |
| 10000ms | 0.20  | 0.43  | edge_full_lru    | 0.405    | +17.7pp   | PASS |
| 10000ms | 0.20  | 1.00  | edge_full_lru    | 0.405    | +17.7pp   | PASS |
| 10000ms | 0.30  | 0.43  | edge_full_lru    | 0.405    | +17.7pp   | PASS |
| 10000ms | 0.30  | 1.00  | edge_full_lru    | 0.405    | +17.7pp   | PASS |
| 10000ms | 0.40  | 0.43  | edge_full_lru    | 0.405    | +17.7pp   | PASS |
| 10000ms | 0.40  | 1.00  | edge_full_lru    | 0.405    | +17.7pp   | PASS |

lifecycle_aware (vs device) by cell for LoCoMo:
- 300ms: s=0.43 +10.2pp / s=1.00 +13.2pp
- 1000ms: s=0.43 +0.7pp (K2 FAIL) / s=1.00 +14.2pp
- 10000ms: s=0.43 +17.7pp / s=1.00 +17.7pp

### EgoSchema (gist-compressible; cold-restore-per-query device model)

| budget  | q_slo | scale | #1 policy        | both_met | vs device | K2   |
|---|---|---|---|---|---|---|
| 300ms   | any   | any   | edge_win10_lru   | 0.502    | +50.2pp   | PASS |
| 1000ms  | any   | any   | edge_full_lru    | 0.570    | +57.0pp   | PASS |
| 10000ms | any   | any   | edge_full_lru    | 0.570    | +11.7pp   | PASS |

lifecycle_aware ties with edge_full_lru at 1000ms and 10000ms (+57.0pp, +11.7pp).
At 300ms budget, edge_win10_lru beats lifecycle_aware (+50.2pp vs +11.3pp) because
lifecycle_aware sometimes selects full fidelity, whose cold-admit TTFT exceeds 300ms.

---

## Kill-Condition Results

**K1 (≤50% non-discriminating at Stage 0):** PASS — 22% non-discriminating at both A1 bounds.

**K2 (lifecycle_aware beats device_only by >5pp in ALL cells):** **FAIL**  
3 cells violate K2:
- locomo / 1000ms / q_slo=0.20 / s=0.43: gap = +0.7pp
- locomo / 1000ms / q_slo=0.30 / s=0.43: gap = +0.7pp
- locomo / 1000ms / q_slo=0.40 / s=0.43: gap = +0.7pp

**Root cause of K2 violation (not a policy tuning target):**
At s=0.43, qwen3b warm-append on Jetson is fast enough that device_only already serves
87.9% of LoCoMo turns within 1000ms.  The edge's latency advantage vanishes when the
device tier is competitive.  At s=1.00 (no 3B speedup), the gap is 14.2pp in the same
cells — K2 passes.  The violation is structural, not a policy deficiency: if qwen3b
Jetson latency is close to 0.43× of qwen7b, the 1000ms budget is already largely met
without edge offloading.  The K2 outcome will be resolved once the measured A1 ratio
replaces the assumption.

**K3 (values within 2× of committed source):** See consistency check below.

---

## Consistency Check (mandatory, 6-check protocol)

### Check 1 — Cross-check against committed measurements

| quantity | this run | prior committed | source | ratio | agree/disagree |
|---|---|---|---|---|---|
| EDGE full warm-append | 66.0ms | 66ms (E26); 67ms(E35,N=1) | E26/E35 | 1.00 | AGREE |
| EDGE win10 intra-session | 59.0ms | 41–77ms (E35 range) | E35 | in range | AGREE |
| EDGE win10 inter-session | 1031.0ms | ~1031ms (E35) | E35 | 1.00 | AGREE |
| EDGE sum200 restore | 32.0ms | 32ms (E35) | E35 | 1.00 | AGREE |
| EDGE sum200 update | 5822.0ms | 5822ms (E35) | E35 | 1.00 | AGREE |
| Jetson qwen7b incr_warm 1k | 579.4ms | 579ms (E23) | E23 | 1.00 | AGREE |
| Jetson qwen7b incr_warm 16k | 2162.8ms | 2163ms (E23) | E23 | 1.00 | AGREE |
| Jetson qwen7b full_restore 16k | 75053.7ms | 75054ms (E23) | E23 | 1.00 | AGREE |
| Q(full,locomo,qwen7b) | 0.400 | 0.400 (E29) | E29 | 1.00 | AGREE |
| Q(full,egoschema,qwen3b) | 0.450 | 0.450 (E29) | E29 | 1.00 | AGREE |
| Q(sum200,locomo,qwen7b) | 0.120 | 0.120 (E29) | E29 | 1.00 | AGREE |

No disagreements > 2×.

### Check 2 — Physical plausibility

LoCoMo warm-append: incr_warm at L=16k = 2163ms → rate ≈ 7.6 tok/ms = 7,600 tok/s.
Committed A6000 cold prefill ≈ 5,984 tok/s (cost_matrix.csv).  Jetson warm-append being
faster than A6000 cold prefill in tok/s is plausible because warm-append does not re-prefill
the full KV cache — it processes only the new turn tokens.  The physical story is consistent.

EgoSchema cold-restore at L=2000 at s=1.00: full_restore_2048 = 8010ms → 2000/8.0 ≈ 250 tok/ms.
At s=0.43: 8010 × 0.43 = 3444ms → 2000/3.4 ≈ 580 tok/ms.  Both plausible relative to E23.

EDGE sum200_restore = 32ms for 160 tok → 5000 tok/s.  Edge A6000 cold prefill = 5984 tok/s.
Agreement within 20%: PASS.

### Check 3 — Distribution sanity

Stage 1 uses 3 seeds per configuration.  Per-seed results are independent (different rng
sequences).  The `both_met` metric is computed over all turns across all robots in a run.
The averaged metric is meaningful because robot assignments cycle through the 10 LoCoMo
conversations.  No identical constants across varied seeds.

### Check 4 — Definition audit

| name | definition this run | prior committed | agree? |
|---|---|---|---|
| incr_warm | Jetson qwen7b warm-append TTFT at given L | E23 `incremental_warm_ms` | YES |
| full_restore | Jetson qwen7b cold-restore TTFT | E23 `full_restore_ms` | YES |
| LoCoMo session | sequence of turns sharing one KV accumulation block | E33a §1.6 (22 turns/sess) | YES |
| TTFT budget | query TTFT ≤ budget_ms | same across E24/E24b/E24c | YES |
| both_met | TTFT ≤ budget AND quality correct | E24/E24b/E24c | YES |
| win10 tokens | 7275 median (E33a) | E33a | YES |
| sum200 tokens | 160 (E33a) | E33a | YES |

### Check 5 — Claim linkage

| headline result | CLAIMS.md / FORMULATION.md claim | bearing |
|---|---|---|
| lifecycle_aware beats device_only by ≥10pp at relaxed budgets | C3: lifecycle-cost-aware fidelity selection sufficient at current node | SUPPORTS |
| K2 violation at locomo / 1000ms / s=0.43 | C3: must be qualified — only holds when device tier is latency-constrained | WEAKENS (conditional) |
| EgoSchema: any edge policy +11–57pp vs device | C1: gist regime benefits from compression | SUPPORTS |
| edge_full_lru co-ranks with lifecycle_aware | C3: lifecycle-cost-aware selection; fidelity variety matters less when capacity is sufficient | SPEAKS TO (nuance) |

FORMULATION.md §Scoping: this experiment measures single-tier (edge) placement policies.
No cross-tier KV transfer is modeled.  No joint fidelity×placement optimization is
attempted (anti-coupling constraint from E24b/E24c).  In scope.

### Check 6 — Proxy validity

- Quality correctness is sampled from Q_TABLE using rng.random() < Q_f.  This is a Monte
  Carlo draw from the committed accuracy.  It is not a proxy — it directly implements the
  committed quality distribution for large n.  Valid for headline conclusions.
- TTFT is computed deterministically from committed cost measurements and A1 assumption.
  Where A1 is load-bearing, the result is reported at both A1 bounds.  Valid as stated.
- LoCoMo context growth model: L grows linearly per turn at rate (ctx_total/n_sessions)/22.
  This is derived from committed E33a data.  Proxy is reasonable; actual growth could be
  irregular within a session.  Not used as a headline — used to determine device_incr_warm
  input, which is interpolated from E23 measurements.  Limitation noted.

---

## Limitations

1. **A1 is unmeasured.** The 1000ms K2 violation at s=0.43 may resolve once the Jetson
   qwen3b measurement replaces the assumption.  No conclusion about this cell should be
   drawn until the measurement lands.

2. **n_sessions=20 per run.** Short relative to real LoCoMo conversations (19–32 sessions
   committed).  All runs use the same 10-conversation rotation, so the mean is representative
   but the tails are not.

3. **cap_frac averages over all fleet sizes.** The per-cell ranking averages over
   n_robots∈{5,10,20} × cap_frac∈{0.25,0.50,0.75,1.00}.  A larger fleet with lower
   cap_frac (more robots competing for slots) would penalize LRU policies more.

4. **EgoSchema context size is not committed.** A2 (1500–2500 tok) is an estimate.
   The stage 0 discrimination for EgoSchema at 300ms and 1000ms is robust to this
   range (any L ≥ 500 tok fails cold-restore at 1000ms under qwen7b).

5. **Quality model is stationary.** The Q_TABLE values are from E29 (n=282 LoCoMo,
   n=500 EgoSchema).  In a real session, quality may degrade as context drifts from
   the summary representation.  Not modeled here.

---

## Next step

Once the Jetson qwen3b measurement (`results/cost/profiles/jetson_orin_qwen3b.json`) is
committed, compute the empirical A1 ratio per L, replace the 0.43–1.00 range with the
measured value, and re-check K2 for the locomo / 1000ms cells.  If the measured ratio is
close to 0.43, K2 may remain violated and warrants a policy design note about latency
parity removing the edge advantage.  If closer to 1.00, K2 passes and the main headline
holds across all cells.
