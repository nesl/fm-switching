# E30 — Capacity Arithmetic: Memory and Accelerator Contention at Fleet Scale

> **Superseded (win-10 rows):** See `reports/e33a_definition_audit_and_ledger.md`. WINDOW_TOKENS=400 is the cost-profile definition (last 10 turns); the paper's fidelity experiments use last 10 sessions (median 7,275 tokens, 18× larger). Corrected: N_memory(win10, A6000) ≈ 78 (not 1,421); restore cost ≈ 1,292 ms (not ~65 ms); binding crossover ≈ 101 s (not 57 s). The qualitative ordering sum-80 ≫ sum-200 > win-10 > full survives; all quantitative win-10 claims are superseded.

Generated: 2026-08-21

## Assumptions (consolidated)

All assumptions are labeled [ASSUMPTION] below and in the source script (`experiments/cost/e30_capacity.py`). Measured values trace to cited result files.

| label | value | source |
|---|---|---|
| KV bytes per token | 57,344 B (57 KB) | [MEASURED] jetson_orin_qwen7b.json metadata |
| qwen7b model weights in VRAM | 15.4 GB | [MEASURED] cost_matrix.csv peak_mem_gb at L=1k (15.46 GB) minus KV(1k)≈0.06 GB |
| qwen3b model weights in VRAM | 6.2 GB | [ASSUMPTION] e29_locomo.py log: GPU current=6.2 GB at idle; not a formal profile |
| Window token count | 400 tok | [MEASURED range] jetson profile: 261–488 tok across L; midpoint used |
| Sum-80 token count | 80 tok | [ASSUMPTION] nominal budget; jetson measured ~51 tok but budget drives cost |
| Sum-200 token count | 200 tok | [ASSUMPTION] nominal budget; jetson measured ~113 tok but budget drives cost |
| a6000 VRAM | 48 GB | [SPEC] RTX A6000 datasheet |
| jetson_orin VRAM usable | 64 GB | [MEASURED] jetson profile metadata gpu_mem_gb=65.9 GB; rounded to 64 |
| 24-GB class GPU | 24 GB | [ASSUMPTION] common edge alternative; not measured |
| Device tier model | qwen3b | [ASSUMPTION] per E29 experimental setup |
| Edge tier model | qwen7b | [MEASURED] E21–E26 cost profiling |
| LoCoMo turns/session | 21.6 | [MEASURED] locomo10.json: mean turns per session across 272 sessions |
| LoCoMo inter-session interval | 19 days | [MEASURED] locomo10.json: mean across 254 inter-session gaps |
| Minutes per conversation turn | 5 min | [ASSUMPTION] typical human chat pace; not measured |
| Infini-THOR high-level plan steps | 55 steps/task | [MEASURED] traj/ files, n=65: mean 55.1, median 50 |
| Seconds per robot high-level step | 10 s | [ASSUMPTION] deployed robot pace; simulator runs faster |
| Decode throughput | 40 tok/s | [MEASURED] E26: 36–44 tok/s; midpoint |
| Typical response length | 100 tok | [ASSUMPTION] short factual answers; not measured |
| Query rate sweep | 0.1, 1.0, 10.0 qps | [ASSUMPTION] spanning idle to busy |
| Prewarm rate sweep | 0, 1/min, 1/30s | [ASSUMPTION] speculative migration events |
| Fleet size (warehouse) | 20 robots/building | [ASSUMPTION] logistics fleet baseline |
| Fleet size (office) | 5 robots/floor | [ASSUMPTION] small deployment |
| L=16k refresh cost | interpolated | [FLAG] 16k not directly measured in E26; linearly interpolated between 8k and 32k values |

**Infeasibility flags (from committed measurements):**
- jetson_orin: full-restore infeasible at L≥24,576 [MEASURED: jetson profile feasible.full_restore=False]
- rtx3090ti (24-GB class): full-restore infeasible at L≥49,152 [MEASURED: cost_matrix.csv feasible=0]
- a6000: all L feasible for full restore up to L=65,536 [MEASURED: cost_matrix.csv]
- rtx3090ti sum80/sum200 update_corrected=0 at L≥32k [MEASURED: cost_matrix.csv — capped input buffer; E26 diagnostic]

---

## Part A: Memory Capacity per Tier

**Formula:** usable VRAM = total − model_weights. KV footprint per session = 57 KB/token × tokens_held. Sessions = ⌊usable / KV_per_session⌋.

### Tier specifications

| tier | total VRAM | model | model weights | usable for KV |
|---|---|---|---|---|
| A6000 (edge) | 48 GB | qwen7b | 15.4 GB | 32.6 GB |
| 24-GB class GPU (edge) | 24 GB | qwen7b | 15.4 GB | 8.6 GB |
| Jetson Orin (device) | 64 GB | qwen3b [ASSUMPTION] | 6.2 GB [ASSUMPTION] | 57.8 GB |

### Concurrent sessions by memory (a6000 edge tier)

| fidelity | tokens held | KV/session (GB) | L=8k | L=16k | L=32k | L=64k |
|---|---|---|---|---|---|---|
| sum-80 | 80 | 0.0046 | 7106 | 7106 | 7106 | 7106 |
| sum-200 | 200 | 0.0115 | 2842 | 2842 | 2842 | 2842 |
| win-10 | 400 | 0.0229 | 1421 | 1421 | 1421 | 1421 |
| full | L | L×57KB | 69 | 34 | 17 | 8 |

Memory ordering: sum-80 ≫ sum-200 > win-10 > full. At L=64k, sum-80 supports 7106 sessions vs full's 8 sessions by memory alone.

### Concurrent sessions by memory (jetson_orin device tier, qwen3b)

| fidelity | L=8k | L=16k | L=32k | L=64k |
|---|---|---|---|---|
| sum-80 | 12599 | 12599 | 12599 | 12599 |
| sum-200 | 5039 | 5039 | 5039 | 5039 |
| win-10 | 2519 | 2519 | 2519 | 2519 |
| full | 123 | 61 | infeasible | infeasible |

The Jetson's 64 GB unified memory means even full fidelity at L=16k supports 61 sessions per device; memory is never the binding constraint at device scale (one robot per Jetson is the nominal deployment).

---

## Part B: Accelerator Demand per Session

### Workload-derived refresh rates

**LoCoMo (social conversation history):** Mean 21.6 turns/session [MEASURED], mean inter-session interval 19 days [MEASURED]. Within-session turn rate: assumed 1 turn / 5 min = 3.3 mHz [ASSUMPTION: conversation pace, no within-session timestamps in data]. This is well below even the 300-second refresh interval.

**Infini-THOR (robot manipulation):** Mean 55 high-level steps per task [MEASURED from 65 trajectories]. Assumed 10 s/step for deployed robots [ASSUMPTION] → step rate 100 mHz. This is faster than the 5-second refresh interval in our sweep; 10–30 s intervals are the relevant range.

These rates set the lower bound for meaningful refresh intervals: less than ~5 s for robot workloads, less than ~300 s for social history. Our sweep covers both.

### Refresh costs (vLLM, a6000) [MEASURED: E26]

| fidelity | mechanism | L=8k | L=16k† | L=32k | L=64k |
|---|---|---|---|---|---|
| sum-80 | cold-prefill + decode(80 tok) | 3.07 s | 6.05 s | 9.03 s | 21.92 s |
| sum-200 | cold-prefill + decode(200 tok) | 5.93 s | 9.04 s | 12.14 s | 25.31 s |
| win-10 | warm-append (~200 tok) | 0.040 s | 0.063 s | 0.087 s | 0.152 s |
| full | warm-append (~200 tok) | 0.040 s | 0.063 s | 0.087 s | 0.152 s |

† L=16k linearly interpolated between L=8k and L=32k measurements [FLAG: not directly measured].

### Accelerator demand per session = refresh_cost / refresh_interval (fraction of one GPU)

Rows show sessions supportable per GPU under accelerator constraint alone (1 / demand_fraction):

| fidelity | L | ri=5s | ri=15s | ri=30s | ri=60s | ri=300s |
|---|---|---|---|---|---|---|
| sum-80 | 8k | 1 | 4 | 9 | 19 | 97 |
| sum-80 | 32k | 0 | 1 | 3 | 6 | 33 |
| sum-80 | 64k | 0 | 0 | 1 | 2 | 13 |
| sum-200 | 8k | 0 | 2 | 5 | 10 | 50 |
| sum-200 | 32k | 0 | 1 | 2 | 4 | 24 |
| sum-200 | 64k | 0 | 0 | 1 | 2 | 11 |
| win-10 | 8k | 125 | 377 | 755 | 1511 | 7556 |
| win-10 | 32k | 57 | 172 | 344 | 688 | 3440 |
| win-10 | 64k | 32 | 98 | 197 | 394 | 1973 |
| full | 8k | 125 | 377 | 755 | 1511 | 7556 |
| full | 64k | 32 | 98 | 197 | 394 | 1973 |

### Serving and prewarm demand (shared budget)

All three demands draw from the same GPU budget:

1. **State refresh:** tabulated above.
2. **Query serving:** 100 tok response at 40 tok/s = 2.50 s/query [MEASURED decode rate]. At 1 qps per session this consumes 2.50 GPU-fraction per session; maximum throughput from decode alone = 0.4 qps/GPU.
3. **Speculative prewarm:** one cold prefill per migration event. At L=8k: 1.18 s/event; at L=64k(YaRN): 19.68 s/event [MEASURED: E26]. At 1 prewarm/min per session: adds 0.0197 (8k) to 0.3280 (64k) GPU-fraction per session.

---

## Part C: Which Resource Binds First

### Ordering inversion

Memory ordering (fewer tokens held → more concurrent sessions by memory):
**sum-80 ≫ sum-200 > win-10 > full**

Accelerator ordering (cheaper to refresh → more concurrent sessions by accelerator):
**win-10 ≫ full ≫ sum-80 > sum-200** (win-10 warm-append is 75–181× cheaper than sum refresh per E26)

The two orderings invert for summaries vs windows. win-10 is memory-expensive relative to summaries but accelerator-cheap. sum-80/sum-200 are memory-cheap but accelerator-expensive.

### Sessions supported: binding constraint (a6000, ri=60s)

| fidelity | L=8k | L=16k | L=32k | L=64k | binding at ri=60s |
|---|---|---|---|---|---|
| sum-80 | 19 | 9 | 6 | 2 | accelerator |
| sum-200 | 10 | 6 | 4 | 2 | accelerator |
| win-10 | 1421 | 945 | 688 | 394 | accelerator |
| full | 69 | 34 | 17 | 8 | memory |

**Crossover analysis:** For sum-80 and sum-200, the accelerator **always** binds before memory across the entire sweep range (ri=5–300 s). Even at ri=300s, N_accel for sum-80 at L=8k is only 97, far below N_mem=7,106. The reason: the summarizer's cold-prefill+decode cost (3–25 s) is so large relative to realistic refresh intervals that summary sessions are permanently accelerator-bound at any fleet size.

For win-10 and full, the crossover falls within our sweep. Win-10's crossover refresh interval (where N_accel = N_mem) is: ri* = refresh_cost × N_mem ≈ 0.040 s × 1421 = 57 s (L=8k), 0.087 s × 1421 = 124 s (L=32k), 0.152 s × 1421 = 216 s (L=64k). **Below ri*, accelerator binds; above ri*, memory binds.** At ri=300s, win-10 at all L is memory-bound (N_accel=1,973–7,556 >> N_mem=1,421). At ri=60s, win-10 at L≥16k is accelerator-bound (N_accel=394–945 < N_mem=1,421). Full context is always memory-bound (N_mem=8–69 far below N_accel=394–1,511 at all L and ri in our sweep).

The crossover between the two fidelity orderings:
- **sum-80/sum-200 at all refresh intervals:** accelerator always binds. A 20-robot fleet with sum-80 at L=32k and ri=60s needs 20 GPUs' worth of refresh compute (N_accel=6 per GPU), vs. only 1 GPU by memory. Contention is real.
- **win-10 at ri < 57–216 s (L-dependent):** accelerator binds before memory. At ri=60s and L≥16k, N_accel (688–945) still far exceeds any realistic fleet but constrains scaling before memory does.
- **full context:** always memory-bound; N_mem at L=32k is 17 (a6000), meaning a 20-robot fleet saturates memory.

---

## Part D: Realism Check

**Fleet size assumptions:** warehouse/logistics building = 20 robots [ASSUMPTION]; small office floor = 5 robots [ASSUMPTION]. These are stated estimates, not measured deployments.

### Binding check at 60-second refresh interval (a6000 edge tier)

| fidelity | L | N_memory | N_accel(60s) | N_binding | serves 20-robot fleet? |
|---|---|---|---|---|---|
| sum-80 | 8k | 7106 | 19 | 19 | NO |
| sum-80 | 32k | 7106 | 6 | 6 | NO |
| sum-80 | 64k | 7106 | 2 | 2 | NO |
| sum-200 | 8k | 2842 | 10 | 10 | NO |
| sum-200 | 32k | 2842 | 4 | 4 | NO |
| sum-200 | 64k | 2842 | 2 | 2 | NO |
| win-10 | 8k | 1421 | 1511 | 1421 | yes |
| win-10 | 32k | 1421 | 688 | 688 | yes |
| win-10 | 64k | 1421 | 394 | 394 | yes |
| full | 8k | 69 | 1511 | 69 | yes |
| full | 32k | 17 | 688 | 17 | NO |
| full | 64k | 8 | 394 | 8 | NO |

### Answer to Part D

Contention does bind at realistic fleet sizes, but the binding resource and the threshold depend critically on fidelity choice and refresh interval. At 60-second refresh intervals (roughly one new observation per minute): **memory does not bind at all** for compressed fidelities — even a 24-GB GPU supports hundreds of sum-80 sessions — but **accelerator time binds sharply for summaries at large L and short refresh intervals**. Specifically, for sum-80 or sum-200 sessions at L=64k with ri=15s, N_accel drops to single digits on an A6000, meaning a 20-robot fleet consuming 21.9 s of GPU per refresh every 15 seconds saturates the GPU. By contrast, window-10 maintenance (warm-append ~0.152 s) never saturates the accelerator at any plausible fleet size — memory (N_mem_win10 = 1421 at L=64k on A6000) would bind first, and even then the binding capacity (1421 sessions) far exceeds any building-scale fleet. **The operationally surprising finding is that the footprint-minimizing choice (summaries) is also the accelerator-expensive choice**, and the two constraints are inverted: deploying sum-80 to save KV memory at large L and short refresh intervals forces the accelerator to become the bottleneck long before memory does. A provisioning system optimizing for concurrent sessions should prefer win-10 at large L and frequent refresh rates — it is cheaper in both steady-state memory (400 tok × 57 KB = 23 MB vs. claim of thousands per full session) and accelerator time, at the cost of reduced dense-session fidelity.

---

## Figures

`figures/cost/e30_capacity_binding.pdf` — six-panel figure: rows = (a) memory-limited sessions, (b) accelerator-limited sessions at ri=60s; columns = A6000 (edge), 24-GB GPU (edge alternative), Jetson Orin (device). Red dashed = 20-robot fleet reference; orange dotted = 5-robot fleet.
