# E36b — Fleet Policy Simulation with Measured A1 Ratio

**Date:** 2026-08-24  
**Host:** flash / CPU only (pure simulation, no GPU)  
**Script:** `experiments/orchestration/e36b_fleet.py`  
**Results:** `results/orchestration/e36b_fleet/`  
**Supersedes:** `reports/e36_fleet_policy.md` (E36) for conclusions that depended on A1.

---

## What changed from E36

E36 carried assumption A1 — qwen3b Jetson time = s × qwen7b Jetson time — shown at
s=0.43 (parameter-count ratio lower bound) and s=1.00 (no-speedup upper bound).  E37
measured qwen3b directly on the Jetson.  E37b computed per-operation ratios.

E36b replaces the A1 sensitivity axis with a single L-dependent measured curve:

| operation | L=1024 | L=4096 | L=8192 | L=16384 | trend |
|---|---|---|---|---|---|
| incr\_warm (LoCoMo device TTFT) | 0.593 | 0.641 | 0.681 | 0.705 | rises with L |
| full\_restore (EgoSchema device TTFT) | 0.475 | 0.496 | 0.517 | 0.542 | rises with L |

Ratios clamped at last measured value (0.705/0.542) for L > 16384.  A4 still applies
to the 7B baseline extrapolation.  The Stage 1 run count halves to 1,512 (no A1 axis).

No other inputs changed.  All committed cost and quality values are identical to E36.

---

## EgoSchema modeling note (unchanged from E36)

EgoSchema is modeled as **short independent sessions — cold restore per query, no
accumulated context**.  Device TTFT uses the measured full\_restore ratio.  Discriminating
cells for EgoSchema reflect per-query materialization latency, not maintenance.  EgoSchema
is the gist-compressible regime; it is not described as a compressible long-lived session.

---

## Stage 0 — Headroom Gate (measured A1)

**Device failure rates at measured ratio:**

| workload | budget | lat\_fail | cause |
|---|---|---|---|
| LoCoMo | 300ms | 95.2% | warm-append for L>~300 tok exceeds 300ms at measured 3B speed |
| LoCoMo | 1000ms | 46.5% | warm-append for L>~5k tok exceeds 1s |
| LoCoMo | 10000ms | 0.0% | all turns feasible within 10s |
| EgoSchema | 300ms | 100.0% | cold-restore of 1500–2500 tok ≥ 917ms (3B@1k) |
| EgoSchema | 1000ms | 100.0% | cold-restore of 1500–2500 tok ≥ 917ms |
| EgoSchema | 10000ms | 0.0% | all queries feasible within 10s |

**Non-discriminating cells (device meets both quality AND <5% latency failure):**
- locomo / 10000ms / q_slo=0.20 — quality PASS (0.230 ≥ 0.20); 0% latency failure
- egoschema / 10000ms / all q_slo — quality PASS (0.450); 0% latency failure (×3)

**K1: PASS — 4/18 cells non-discriminating (22%), well below 50% threshold.**

Comparison with E36 A1 bounds:

| workload | budget | s=0.43 (E36) | s=1.00 (E36) | measured (E36b) |
|---|---|---|---|---|
| LoCoMo | 300ms | 87.3% | 97.1% | **95.2%** |
| LoCoMo | 1000ms | 12.1% | 70.2% | **46.5%** |
| LoCoMo | 10000ms | 0.0% | 0.0% | **0.0%** |
| EgoSchema | 300ms | 100% | 100% | **100%** |
| EgoSchema | 1000ms | 100% | 100% | **100%** |
| EgoSchema | 10000ms | 0.0% | 0.0% | **0.0%** |

The measured curve sits between the two E36 bounds and is much closer to s=1.00 than to
s=0.43, confirming that the optimistic lower bound was misleading.

---

## Stage 1 — Fleet Simulation

**Configuration:**  
- Policies: device\_only, edge\_full\_lru, edge\_win10\_lru, edge\_sum200\_lru, reactive,
  budget\_aware, lifecycle\_aware  
- n\_robots ∈ {5, 10, 20} × cap\_frac ∈ {0.25, 0.50, 0.75, 1.00} × 3 seeds × 2 workloads
  × 3 q\_SLOs = 1,512 runs  
- n\_sessions = 20 per run; device TTFT uses measured L-dependent A1 ratio

---

## Stage 2 — Per-Cell Policy Ranking

### LoCoMo (dense-incompressible; warm-append device model)

| budget | q\_slo | #1 policy | both\_met | lifecycle\_aware | gap\_lc\_vs\_dev | K2 |
|---|---|---|---|---|---|---|
| 300ms | any | edge\_full\_lru | 0.142 | 0.142 | **+12.6pp** | PASS |
| 1000ms | any | edge\_full\_lru | 0.235 | 0.235 | **+6.8pp** | PASS |
| 10000ms | any | edge\_full\_lru | 0.405 | 0.405 | **+17.7pp** | PASS |

lifecycle\_aware co-ranks with edge\_full\_lru at all LoCoMo cells.

### EgoSchema (gist-compressible; cold-restore-per-query device model)

| budget | q\_slo | #1 policy | both\_met | lifecycle\_aware | gap\_lc\_vs\_dev | K2 |
|---|---|---|---|---|---|---|
| 300ms | any | edge\_win10\_lru | 0.502 | 0.114 | **+11.3pp** | PASS |
| 1000ms | any | edge\_full\_lru | 0.570 | 0.570 | **+57.0pp** | PASS |
| 10000ms | any | edge\_full\_lru | 0.570 | 0.570 | **+11.7pp** | PASS |

At 300ms budget, edge\_win10\_lru tops the ranking (+50.2pp vs device\_only) because
lifecycle\_aware sometimes selects full fidelity whose cold-admit TTFT exceeds 300ms.
lifecycle\_aware still passes K2 at +11.3pp.

---

## Kill-Condition Results

**K1:** PASS — 22% non-discriminating (4/18).

**K2:** **PASS** — lifecycle\_aware beats device\_only by ≥5pp in all 18 cells.  
- Minimum gap: locomo / 1000ms / any q\_slo = **+6.8pp**  
- Maximum gap: egoschema / 1000ms / any q\_slo = **+57.0pp**

E36's 3 K2-violating cells (locomo / 1000ms / s=0.43) do not arise under the measured
ratio.  Root-cause confirmed (E37b): at the measured device speed, device\_only fails
46.5% of LoCoMo 1s queries, giving lifecycle\_aware genuine headroom.

**K3:** PASS — all values trace to committed sources within 2×.

---

## Consistency Check (mandatory, 6-check protocol)

### Check 1 — Cross-check against committed measurements

| quantity | this run | prior committed | source | ratio | agree/disagree |
|---|---|---|---|---|---|
| Edge full warm-append | 66.0ms | 66ms (E26); 67ms (E35 N=1) | E26/E35 | 1.00 | AGREE |
| Edge win10 intra-session | 59.0ms | 41–77ms range (E35) | E35 | in range | AGREE |
| Edge win10 inter-session | 1031.0ms | ~1031ms (E35) | E35 | 1.00 | AGREE |
| Edge sum200 restore | 32.0ms | 32ms (E35/cost\_matrix) | E35 | 1.00 | AGREE |
| Jetson 7B incr\_warm 1k | 579.4ms | 579ms (E23) | E23 | 1.00 | AGREE |
| Jetson 7B incr\_warm 16k | 2162.8ms | 2163ms (E23) | E23 | 1.00 | AGREE |
| Measured 3B incr\_warm 1k | 343.84ms | 343.84ms (E37) | E37 | 1.00 | AGREE |
| Measured 3B incr\_warm 16k | 1524.03ms | 1524.03ms (E37) | E37 | 1.00 | AGREE |
| Q(full,locomo,qwen3b) | 0.230 | 0.230 (E29) | E29 | 1.00 | AGREE |
| Q(full,egoschema,qwen3b) | 0.450 | 0.450 (E29) | E29 | 1.00 | AGREE |

No disagreements > 2×.

### Check 2 — Physical plausibility

3B incr\_warm at L=8k: 853ms → 9,604 tok/s.  7B incr\_warm at L=8k: 1253ms → 6,542 tok/s.
3B is faster per token, consistent with smaller model.  Neither exceeds committed A6000
warm-append rates (5,984 tok/s cold prefill; warm-append is faster still).  OK.

3B full\_restore at L=8k: 17,486ms → 469 tok/s.  7B full\_restore at L=8k: 33,790ms → 243 tok/s.
Both consistent with committed Jetson cost curves.  OK.

### Check 3 — Distribution sanity

Stage 1 uses 3 seeds per configuration.  Per-seed `both_met` values vary with rng draws;
the averaged metric is stable.  No identical constants appear across varied L, seeds, or
fleet sizes.  The measured ratio table has tight IQRs per cell (<0.5%, E37 data).

### Check 4 — Definition audit

| name | definition this run | prior committed | agree? |
|---|---|---|---|
| incr\_warm | Jetson qwen7b warm-append, E23 `incremental_warm_ms` | E23 | YES |
| A1\_INCR\_WARM\_RATIO | 3B/7B measured ratio per L, E37 | E37b a1\_ratio\_table.csv | YES |
| LoCoMo session / turn | same as E36 (E33a §1.6, 22 turns/session) | E33a | YES |
| win10 tokens | 7,275 median (E33a) | E33a | YES |
| both\_met | TTFT ≤ budget AND quality correct | E24/E24b/E36 | YES |

### Check 5 — Claim linkage

| result | claim | bearing |
|---|---|---|
| K2 PASS at all 18 cells, minimum +6.8pp | C3: lifecycle-cost-aware fidelity selection sufficient at current node | SUPPORTS |
| locomo/1000ms device failure 46.5% | C4: physical inertia cost significant at device tier for dense workloads | SUPPORTS |
| EgoSchema edge policies +11–57pp vs device | C1: gist regime benefits from compression (edge representation) | SUPPORTS |
| LoCoMo quality ceiling 0.230 (3B/full) | C1: dense-incompressible — quality floor SLOs above 0.23 infeasible on device | SUPPORTS |

No cross-tier KV transfer measured (scoped out per FORMULATION.md).  No joint
fidelity×placement optimization (anti-coupling constraint from E24b/E24c respected).

### Check 6 — Proxy validity

- Quality: Monte Carlo draw from Q\_TABLE (committed E29 values).  Valid.
- Device TTFT: deterministic from E23 7B table × measured E37 ratio.  Both committed.
  Ratio interpolated linearly between measured L points, clamped at L=16384 for L > 16384.
  Limitation: no 3B measurement above L=16384 (A4 applies to 7B extrapolation; ratio
  clamped rather than extrapolated since trend direction is unknown above the last point).
- LoCoMo L-growth model: derived from E33a committed session statistics.  Valid as stated.

---

## Limitations

1. **No 3B measurement above L=16384.** The ratio is clamped at 0.705/0.542 for L > 16384.
   LoCoMo contexts reach ~22.8k tokens, so the top 26% of the L range relies on clamping
   rather than measurement.  The actual ratio likely continues rising; clamping understates
   the 3B's disadvantage at long contexts and is conservative in the direction that
   understates the edge's latency advantage.

2. **EgoSchema context size not committed (A2).** Assumed 1500–2500 tokens.
   The stage 0 discrimination at 300ms and 1000ms is robust: any L > ~500 tok fails
   cold-restore at 1000ms under the 3B.

3. **n\_sessions=20.** Short relative to committed 19–32 sessions per conversation.
   Averaged over 10 conversations × fleet configs; mean representative.

4. **Quality model stationary.** Q\_TABLE from E29; drift not modeled.

---

## Headline

Lifecycle-cost-aware fidelity selection at the edge tier (lifecycle\_aware policy)
beats device-only serving by 6.8–57.0pp across all workloads, TTFT budgets, and
quality SLOs under the measured Jetson qwen3b cost (E37).  Both K1 and K2 pass.
The E36 K2 violations were artifacts of an overly optimistic A1 lower bound.
