# StudyE10b-mixed: episodic capacity under recall load on one 32B replica

E-id: StudyE10b-mixed (`research/EXPERIMENTS.md`, pre-registered 2026-11-11). Host: h100nvl **GPU 2** (GPU-4f1d7e47-e769-a289-4860-e71c0d97267c), exclusive.

## 0. Design decisions recorded before running

- **Harnesses reused.** No new protocol was written; the run states which code path each load uses.
  - **Episodic:** D7's open loop (`study_d7_capacity`'s method, re-implemented as `schedule` / `dispatch` / `timed_post` with the same Poisson seeds, scheduled-arrival latency and dispatch lateness) over D14 requests built by `d3_infer_vllm.body`.
  - **Warm recall:** **RH7's image-by-id path exists and is used**: `study_rh7_eager_lazy.Cell` (EAGER-DELTA: frame bytes once, then `uuid` references) driven by `study_rh6_offload_knee.device` with RH2 plans.
  - **Cold recall:** R1's own `body()` for K1 (captured before the RH imports rebind it).
- **Append cadence.** The spec says "eager append every 2 s as RH7 did". RH7 appended every **10 s of session time**, each append carrying the five new 2-s-stride D2 frames. I follow RH7 (10 s) and read "2 s" as the frame stride. This is flagged here and was not changed after seeing any result.
- **Timeline:** 1× real time, not compressed. With 4-min windows each warm session asks the questions that fall in its window; the count per cell is reported.
- **Prefix caching ON in every cell** (warm sessions need it).
  - Episodic D14 prompts are distinct within a server load (one manifest cursor), so they gain nothing from the cache except shared template / header blocks (reported as cached tokens) but do occupy KV blocks.
  - D7 / D7b ran with prefix caching OFF and processor cache 0 GB; here the processor cache is 128 GiB (RH7, needed for uuid references). The negative control is read with these differences stated.
- **One server, three request types.** RH3's engine-level image size (`longest_edge` 16,777,216) would shrink K1's 256-frame videos, because the video processor's budget is over all frames: 23.1M px vs the video default 25,165,824.
  - K1 requests therefore carry `mm_processor_kwargs = {"size": <video default>}` per request (`--trust-request-mm-kwargs`, as R1).
  - A token-parity gate checks all three request types before any cell: D14 N = 1 / 3 at 378 / 1,062 tokens, K1 = R1's processor count, D2 append = 90 tokens per frame with ≥ 90 % of the warm-up prompt cached. It STOPs on any mismatch.
- **Grid trimmed before running** (full factorial 240 cells ≈ 30 h). What runs and why:
  - **Baseline** k = 0, r = 0, N ∈ {1, 3} × {25, 50, 75, 90} %, both KV configs: the negative control and the starting point.
  - **KV-GPU, k ∈ {2, 4, 8, 16}, r = 0, both N:** the warm-recall sweep.
  - **KV-HOST, k ∈ {8, 16} only:** k ≤ 4 sessions hold at most about 0.7× GPU KV (about 11k tokens each vs 62,944), so the two configs cannot differ there. **Dropped:** KV-HOST k = 2, 4.
  - **KV-GPU, k = 0, r ∈ {0.05, 0.1}, both N:** the cold-recall sweep. **Dropped:** KV-HOST with cold recall only, because cold requests are not held warm, so offload cannot change them beyond eviction of nothing.
  - **Both configs, k = 8, r = 0.1, both N:** one combined cell. **Dropped:** the other k × r combinations (time).
  - **Levels per condition:** run top-down from the levels that met the budget at baseline (D7 / D7b: 75 % and 90 % already fail both budgets with no recall load), stopping at the first level that meets it. Capacity is therefore resolved only to the spec's levels; a 25 % failure is reported as "< 25 %".

## 1. Mechanism verification (recorded BEFORE the sweep)

**Step 1, causal chain.**
- One replica serves two workloads:
  - short distinct episodic prefills, each about 0.1–0.3 s of GPU work;
  - recall work: warm sessions' appends and escalations (small computed deltas over large cached prefixes), and cold RICH questions (about 12.6k-token prefills, about 2.5 s each).
- FORMULATION's physical component says reconstruction cost grows with context. On a shared replica that cost becomes queueing for everyone. Recall work therefore takes GPU time from episodic requests (compute queueing) and takes KV blocks (warm prefixes, about 11k tokens per session).
- When the warm set exceeds GPU KV (k ≥ about 6), GPU-only KV must evict. Evicted sessions re-prefill on their next append (KV eviction → extra compute). Host offload turns that re-prefill into a reload.
- So episodic capacity under its p99 budget should:
  - fall with r (compute);
  - fall with k mildly while the warm set fits;
  - fall sharply for KV-GPU past the fit point (eviction + re-prefill);
  - fall less for KV-HOST.

**Step 2, instantiate each link.**

| link | quantity | planned range | varies? | evidence |
|---|---|---|---|---|
| episodic load | arrival rate | 25–90 % of 15.1 / 5.38 req/s | yes, by design | D7 / D7b |
| cold recall compute | K1 prompt tokens × r | about 12.6k × {0, 0.05, 0.1} req/s ≈ 0–1.3k tok/s, 0–25 % of the 32B prefill rate (about 5k tok/s) | yes | R1 manifest; D7 |
| warm KV footprint | Σ session history tokens vs 62,944 | k = 2 / 4 / 8 / 16 ≈ 0.3 / 0.6 / 1.2 / 2.4× (about 9–11k per session) | yes; crosses 1× between k = 4 and 8 | RH5 / RH6 footprints |
| eviction → re-prefill | warm misses, cached tokens per append | 0 expected for k ≤ 4; > 0 for KV-GPU k ≥ 8; about 0 for KV-HOST | to be measured | rows + /metrics |
| compute queueing | waiting requests, GPU util, computed tok/s | per cell | to be measured | /metrics, Sampler |

No link is ABSENT or CONSTANT by design. The eviction link is checked per cell: if KV-GPU k = 16 shows no warm misses, the KV comparison is reported as unexercised.

**Step 3, trace one unit.** One episodic request and one warm escalation are traced from a loaded cell: scheduled → sent → first token, prompt / cached tokens, and the queue (running / waiting) and KV usage at that second.

**Step 4, negative control.** k = 0, r = 0 (no recall load) must reproduce D7 / D7b episodic p99 at matching levels within 2×. This is stated with the differences: prefix caching ON vs OFF, processor cache 128 GiB vs 0, D14 vs D3 clips with the same token counts.

**Step 5, alternative explanation.**
- A capacity drop could come from the client: dispatch lateness or bodies being built in the loop. All bodies are pre-built before the window, and dispatch lateness p99 is reported per cell.
- It could come from API-server ingestion (RH6's binding resource) rather than the GPU. API CPU is sampled each second; the bytes are small because warm sessions use uuid references.
- For KV, eviction vs plain compute is separated by warm-miss counts and computed tok/s.

**Step 3, trace (KV-HOST, k = 8, r = 0, N = 1, 25 %, at t = 93.1 s, 77 s into the window).**
- Episodic `01090_t03_N1`:
  - scheduled 93.095, dispatch lateness 0.015 s;
  - 378 prompt tokens, 0 cached, body 0.54 MB;
  - TTFT 0.326 s from scheduled arrival (service 0.311 s), within the 0.45 s budget.
- Warm escalation, device 2, session time 180 s:
  - scheduled 93.073, submit lag 0.038 s;
  - 91 frames, 8,312 prompt tokens, **8,224 cached** (99 %; the history is served from the host tier);
  - TTFT 0.501 s.
  - This particular escalation is one of the cache-miss *fallbacks* (§3.4), so its body carried the full 16.3 MB history instead of uuid references. The prefix still hit.
- Server at t = 93.13: 1 running, 0 waiting, GPU KV usage 10 %.
- Binding at that instant: neither; the queue is empty. The episodic TTFT is above the cell p50 (0.20 s) because it shared a scheduler step with the escalation's 88 computed tokens plus its host load.

**Step 4, negative control.** See §3.3. Recall load off (k = 0, r = 0) reproduces D7 / D7b p99 within 2× in **16 / 16** cells (ratio 0.81–1.25).

**Mechanism verdict: every link instantiated.**
- Episodic load: varied.
- Cold compute: 12,662-token prefills at TTFT 4.0–4.2 s.
- Warm KV footprint: KV-GPU warm misses go 0 / 54 (k = 2) → 1 / 106 (k = 4, light load) → 167–256 of 207–281 (k = 8 / 16).
- Eviction → re-prefill: KV-GPU k ≥ 8 appends have median cached fraction 0.002 and compute their whole 8–10k-token history. KV-HOST: 0 misses in every cell, with 434–857 GB loaded from host per window.
- Compute queueing: waiting, GPU util and computed tok/s all vary.

No link is ABSENT or CONSTANT, and the eviction link is exercised. Step 5's alternatives are addressed in §3.4.

## 2. Run record

- **45 cells completed:**
  - 16 baseline cells (k = 0, r = 0; 2 KV configurations × 2 N × 4 levels);
  - 29 recall cells (20 conditions; levels run top-down).
- Each cell has its own fresh server (empty prefix, processor and host caches), a 30-s warm-up, and a 240-s measured window (270 s scheduled minus 30 s discard).
- The token-parity gate PASSED before the first cell: D14 378 / 1,062, K1 = R1, D2 appends 90 tokens per frame; GPU KV 62,944 tokens in both configurations.
- Exclusivity monitor: 670 snapshots.
- **Interruption.** At 14:57:16, between cells, the monitor VOIDed the run on our own `[vllm] <defunct>` zombie left by the previous server's teardown. A zombie uses no CPU; its 96 % `pcpu` is the lifetime average ps reports. At 14:59:24 a foreign user (`nesl`, 37.5 GiB) took GPU 2, and the retry STOPped.
  - No cell was in progress at either event, and no partial cell was kept. The last completed cell, KV-HOST k8 N1 25 %, finished at 14:55:27 under a clean monitor.
  - Fix (implementation): the monitor ignores `<defunct>` processes.
  - The chain resumed with user approval at 15:36 once GPU 2 was free again, continuing from the next pending cell. The last cell finished at 16:44; the monitor was clean for the rest of the run.
- Run metadata: the stack block's `"gpu"` string reads "h100nvl GPU 1", a stale default from a reused RH helper. The recorded UUID GPU-4f1d7e47-e769-a289-4860-e71c0d97267c is nvidia-smi index **2**, which is authoritative.

## 3. Results

**Definitions.**
- Episodic latency = TTFT from the *scheduled* Poisson arrival, as D7.
- p99 is linear-interpolated as in D7. In cells with requests unfinished at the drain cap, those count as infinite latency and the p99 is nearest-rank.
- Budget: p99 ≤ 0.45 s (N = 1) or ≤ 1.21 s (N = 3).
- Capacity = highest pre-registered level (25 / 50 / 75 / 90 % of 15.1 or 5.38 req/s) that meets the budget.
- Cells marked "—" were not run, by the top-down rule.

### 3.1 Capacity table (episodic p99 in seconds per level; ✓ = meets budget)

| KV | k | r (req/s) | N | 25 % | 50 % | 75 % | 90 % | capacity | drop vs k = 0, r = 0 (same KV) |
|---|---|---|---|---|---|---|---|---|---|
| GPU | 0 | 0 | 1 | 0.286 ✓ | 0.461 | 1.555 | 3.069 | **25 % = 3.78 req/s** | — |
| GPU | 0 | 0 | 3 | 0.478 ✓ | 0.988 ✓ | 3.260 | 3.156 | **50 % = 2.69 req/s** | — |
| HOST | 0 | 0 | 1 | 0.308 ✓ | 0.462 | 1.608 | 2.999 | **25 % = 3.78** | — |
| HOST | 0 | 0 | 3 | 0.459 ✓ | 1.029 ✓ | 3.186 | 3.127 | **50 % = 2.69** | — |
| GPU | 2 | 0 | 1 | 0.313 ✓ | — | — | — | 25 % | none |
| GPU | 2 | 0 | 3 | — | 1.063 ✓ | — | — | 50 % | none |
| GPU | 4 | 0 | 1 | 0.536 | — | — | — | **< 25 %** | ≥ 3.78 req/s (all) |
| GPU | 4 | 0 | 3 | 0.705 ✓ † | 11.61 | — | — | 25 % | 1.34 req/s (−50 %) |
| GPU | 8 | 0 | 1 | 192.8 | — | — | — | **< 25 % (collapse)** | all |
| GPU | 8 | 0 | 3 | 183.3 | 280.7 | — | — | **< 25 % (collapse)** | all |
| GPU | 16 | 0 | 1 | ∞ (308 unfinished) | — | — | — | **< 25 % (collapse)** | all |
| GPU | 16 | 0 | 3 | ∞ (87) | ∞ (265) | — | — | **< 25 % (collapse)** | all |
| HOST | 8 | 0 | 1 | 0.429 ✓ | — | — | — | 25 % | none |
| HOST | 8 | 0 | 3 | 0.516 ✓ | 1.758 | — | — | 25 % | 1.34 req/s (−50 %) |
| HOST | 16 | 0 | 1 | 0.452 ‡ | — | — | — | **< 25 %** | ≥ 3.78 req/s (all) |
| HOST | 16 | 0 | 3 | 0.594 ✓ | 1.584 | — | — | 25 % | 1.34 req/s (−50 %) |
| GPU | 0 | 0.05 | 1 | 2.942 | — | — | — | **< 25 %** | all |
| GPU | 0 | 0.05 | 3 | 2.708 | 4.472 | — | — | **< 25 %** | all |
| GPU | 0 | 0.1 | 1 | 8.521 | — | — | — | **< 25 %** | all |
| GPU | 0 | 0.1 | 3 | 7.129 | 8.619 | — | — | **< 25 %** | all |
| GPU | 8 | 0.1 | 1 | 270.4 | — | — | — | **< 25 % (collapse)** | all |
| GPU | 8 | 0.1 | 3 | 271.6 | ∞ (76) | — | — | **< 25 % (collapse)** | all |
| HOST | 8 | 0.1 | 1 | 11.44 | — | — | — | **< 25 %** | all |
| HOST | 8 | 0.1 | 3 | 10.23 | 11.95 | — | — | **< 25 %** | all |

† **Definition-sensitive.** n = 287; the linear p99 is 0.705 s and the nearest-rank p99 is 1.812 s (> 1.21). The 1 % tail is three requests, so this pass is fragile. It is the only cell whose verdict depends on the p99 definition.

‡ A marginal miss: 0.452 vs 0.45.

"< 25 %" means the lowest pre-registered level fails, so capacity is unresolved below 3.78 / 1.34 req/s. "All" means the drop is the full baseline capacity at the resolution of the spec's levels.

### 3.2 Binding-resource diagnostics (in-window averages; GPU util from NVML; computed = prompt − local hits − host hits)

| cell | episodic p50 / p99 | waiting mean / max | GPU KV use max | warm misses | computed tok/s | GPU util | host load GB (s) | append TTFT p50 / p99 | escalation TTFT p50, cached frac | cold TTFT p50 / p99 |
|---|---|---|---|---|---|---|---|---|---|---|
| GPU k0 r0 N1 25 % | 0.13 / 0.29 | 0 / 0 | 0.00 | — | 1,423 | 39 % | — | — | — | — |
| GPU k0 r0 N1 90 % | 0.73 / 3.07 | 0 / 0 | 0.05 | — | 5,252 | 98 % | — | — | — | — |
| GPU k2 N1 25 % | 0.15 / 0.31 | 0 / 0 | 0.13 | 0 / 54 | 1,521 | 41 % | — | 0.20 / 0.33 | 0.21, 0.94 | — |
| GPU k4 N1 25 % | 0.15 / 0.54 | 0 / 0 | 0.36 | 1 / 106 | 1,634 | 43 % | — | 0.21 / 1.24 | 0.23, 0.95 | — |
| GPU k4 N3 50 % | 0.62 / 11.7 | 1.0 / 23 | 0.57 | **38 / 106** | 4,251 | 78 % | — | 0.73 / 11.1 | 1.07, 0.95 | — |
| GPU k8 N1 25 % | 63 / 193 | 147 / 400 | 0.66 | **167 / 207** | 4,962 | 98 % | — | 56 / 192 | 57, 0.94 | — |
| GPU k16 N1 25 % | 209 / ∞ | 506 / 959 | 0.58 | **255 / 281** | 5,105 | 100 % | — | 197 / 372 | 233, 0.82 | — |
| HOST k8 N1 25 % | 0.20 / 0.43 | 0.13 / 2 | 0.65 | 0 / 207 | 1,804 | 45 % | 434 (9.8 s) | 0.37 / 0.78 | 0.35, 0.97 | — |
| HOST k8 N3 50 % | 0.34 / 1.76 | 0.17 / 6 | 0.86 | 0 / 207 | 3,272 | 67 % | 467 (9.2 s) | 0.43 / 2.65 | 0.33, 0.97 | — |
| HOST k16 N1 25 % | 0.18 / 0.45 | 0.21 / 2 | 0.53 | 0 / 414 | 2,195 | 64 % | 852 (17.0 s) | 0.35 / 0.91 | 0.32, 0.97 | — |
| HOST k16 N3 50 % | 0.42 / 1.59 | 0.54 / 11 | 0.89 | 0 / 414 | 3,598 | 77 % | 857 (16.3 s) | 0.57 / 2.74 | 0.51, 0.97 | — |
| GPU r0.05 N1 25 % | 0.15 / 2.94 | 0 / 0 | 0.01 | — | 1,860 | 45 % | — | — | — | 4.15 / 4.47 |
| GPU r0.1 N1 25 % | 0.22 / 8.52 | 1.1 / 21 | 0.06 | — | 2,853 | 57 % | — | — | — | 4.17 / 13.05 |
| HOST k8 r0.1 N1 25 % | 0.50 / 11.4 | 4.1 / 48 | 0.87 | 0 / 207 | 3,018 | 70 % | 443 (8.9 s) | 0.46 / 13.6 | 0.44, 0.97 | 4.93 / 13.14 |
| GPU k8 r0.1 N1 25 % | 98 / 270 | 214 / 516 | 0.69 | 170 / 207 | 5,100 | 100 % | — | 88 / 270 | 92, 0.92 | 133 / 262 |

All 45 cells, with every field, are in `e10b_results.json`.

- Preemptions: 0 in every cell.
- Dispatch lateness p99: ≤ 0.04 s in every cell.
- API server: ≤ 0.52 cores mean in every cell.

**Binding resource, by condition.**

1. **No recall (baseline): GPU compute throughput.**
   - Computed tok/s rises linearly with load to 5.25k at 90 % (N = 1), with GPU util 98 %, which is the 32B prefill ceiling.
   - Waiting stays ≈ 0. vLLM admits everything and the latency grows inside the batch.
   - N = 1 at 50 % (0.461) misses the 0.45 budget by 2.4 %. D7b's own 50 % p99 was 0.449, so the budget sits on D7b's 50 % point. Baseline N = 1 capacity is 25 % here and 50 % in D7b at essentially the same p99 (§3.3).

2. **Cold recall (r > 0): head-of-line interference, not throughput.**
   - At r = 0.05, one 12,662-token prefill every 20 s takes TTFT 4.0–4.2 s (about F3's single-request cost; §4). It adds only about 440 computed tok/s, and GPU util stays at 45 %.
   - But every episodic request arriving during that prefill shares its scheduler steps. About 0.05 × 4 s ≈ 20 % of the time a long prefill is in flight, far more than the 1 % tail p99 measures, so p99 jumps from 0.29 to 2.9 s (N = 1) at 25 % load.
   - r = 0.1 doubles both, giving p99 7–9 s. The p50 barely moves (0.15–0.22 s).
   - **Even r = 0.05 (one cold RICH question per 20 s) takes the whole N = 1 and N = 3 capacity at the spec's resolution.** The binding resource is tail latency from co-scheduling with long prefills, not mean GPU capacity.

3. **Warm recall, KV-GPU: GPU KV capacity, which converts into compute.**
   - **k ≤ 2:** the warm set (about 9–10k tokens per session) fits; misses 0; appends cost a 90-token-per-frame delta; capacity unchanged.
   - **k = 4:** about 0.6× GPU KV (max use 0.36–0.57).
     - At N = 3 50 %, the episodic N = 3 prompts (1,062 tokens each, up to 23 waiting) push the warm prefixes out: 38 / 106 misses, each a whole-history re-prefill. p99 goes to 11.6 s.
     - At N = 1 25 %, there is 1 miss plus 4 full-byte fallback escalations. The few 9k-token re-prefills do the same tail damage as cold recall, and p99 is 0.54.
   - **k ≥ 8:** the warm set exceeds GPU KV (about 1.2–2.4×), and 80–91 % of follow-ups miss.
     - Each append then re-prefills its whole history (median cached fraction 0.002, about 9.6k tokens).
     - 8 sessions × about 9.6k tokens per 10 s ≈ 7.7k tok/s of demand exceeds the about 5.2k tok/s ceiling: GPU 98–100 %, waiting in the hundreds, episodic p50 50–210 s.
     - k = 16 leaves 87–308 episodic requests unfinished at the 300-s drain cap. Their only error type is "unfinished after drain cap".
     - **The chain is KV eviction → re-prefill → compute saturation.** It matches RH5's GPU-only collapse at D = 8.

4. **Warm recall, KV-HOST: host offload removes the collapse; the remaining cost is per-step GPU time of long-context recall requests.**
   - 0 warm misses in every cell. Every append reloads its history from the 256 GiB host tier: 6.9k / 13.6k tok/s of host hits at k = 8 / 16; 434 / 852 GB per window; 9–17 s of load time per 240 s.
   - Computed tok/s rises only 380–770 above baseline. GPU util is 45–77 %.
   - Yet N = 3 capacity drops 50 % → 25 % at both k = 8 and 16, and N = 1 at k = 16 misses by 2 ms.
   - The added p99 comes from episodic requests sharing steps with recall requests that attend over 8–10k-token contexts and wait on host loads. It is not a throughput limit: waiting max is 2–11.
   - **Offload turns a collapse into a ≤ 1-level drop.** k = 8 at N = 1 costs nothing measurable. k = 16 at N = 1 and k ≥ 8 at N = 3 cost one level.

5. **Combined (k = 8, r = 0.1).**
   - KV-GPU collapses, from eviction as in point 3. Cold questions also wait 130 s.
   - KV-HOST does not collapse: episodic p50 0.5 s, cold TTFT p50 4.9 s. But p99 is 10–12 s from cold-prefill interference, as in point 2, and the cell fails at 25 %.
   - Cold recall dominates once warm eviction is removed.

### 3.3 Negative control (k = 0, r = 0 vs D7 / D7b, 32B open loop, same levels)

| KV | N | level | p99 this run | p99 D7 / D7b | ratio | within 2×? | p50 this / prior | budget met (this / prior) |
|---|---|---|---|---|---|---|---|---|
| GPU | 1 | 25 % | 0.286 | 0.261 | 1.09 | yes | 0.130 / 0.142 | ✓ / ✓ |
| GPU | 1 | 50 % | 0.461 | 0.449 | 1.03 | yes | 0.172 / 0.178 | ✗ / ✓ |
| GPU | 1 | 75 % | 1.555 | 1.340 | 1.16 | yes | 0.293 / 0.298 | ✗ / ✗ |
| GPU | 1 | 90 % | 3.069 | 2.464 | 1.25 | yes | 0.726 / 0.744 | ✗ / ✗ |
| GPU | 3 | 25 % | 0.478 | 0.532 | 0.90 | yes | 0.221 / 0.264 | ✓ / ✓ |
| GPU | 3 | 50 % | 0.988 | 1.037 | 0.95 | yes | 0.253 / 0.294 | ✓ / ✓ |
| GPU | 3 | 75 % | 3.260 | 3.464 | 0.94 | yes | 0.529 / 0.592 | ✗ / ✗ |
| GPU | 3 | 90 % | 3.156 | 3.882 | 0.81 | yes | 0.957 / 1.082 | ✗ / ✗ |
| HOST | 1 | 25 % | 0.308 | 0.261 | 1.18 | yes | 0.172 / 0.142 | ✓ / ✓ |
| HOST | 1 | 50 % | 0.462 | 0.449 | 1.03 | yes | 0.208 / 0.178 | ✗ / ✓ |
| HOST | 1 | 75 % | 1.608 | 1.340 | 1.20 | yes | 0.292 / 0.298 | ✗ / ✗ |
| HOST | 1 | 90 % | 2.999 | 2.464 | 1.22 | yes | 0.743 / 0.744 | ✗ / ✗ |
| HOST | 3 | 25 % | 0.459 | 0.532 | 0.86 | yes | 0.232 / 0.264 | ✓ / ✓ |
| HOST | 3 | 50 % | 1.029 | 1.037 | 0.99 | yes | 0.270 / 0.294 | ✓ / ✓ |
| HOST | 3 | 75 % | 3.186 | 3.464 | 0.92 | yes | 0.567 / 0.592 | ✗ / ✗ |
| HOST | 3 | 90 % | 3.127 | 3.882 | 0.81 | yes | 0.963 / 1.082 | ✗ / ✗ |

**PASS: 16 / 16 within 2× (0.81–1.25), and 14 / 16 with the same pass / fail.**
- The two differences are N = 1 at 50 %, 0.461 / 0.462 vs 0.449 against a 0.45 budget: a boundary case.
- Differences from D7 / D7b, as stated in §0:
  - prefix caching ON vs OFF;
  - processor cache 128 GiB vs 0;
  - D14 vs D3 requests at the same token counts;
  - engine image-size kwargs (RH3 PROC_SIZE; Nexar frames are below it, and tokens are equal per the parity gate);
  - KV-HOST adds the offload connector.
- Offload with nothing to offload changes nothing (KV-GPU vs KV-HOST baselines are within 0.05 s at every level).
- Because the baseline itself sits on the N = 1 50 % boundary, every N = 1 capacity is resolved to "25 % or < 25 %". The spec's levels cannot show a drop smaller than one level.

### 3.4 Step 5 alternatives and flags

- **Client artefact: ruled out.** Bodies were pre-built; dispatch lateness p99 ≤ 0.04 s everywhere, including the collapsed cells; submit lag for recall ≤ 0.04 s.
- **API-server ingestion (RH6's binding resource): ruled out.** API ≤ 0.52 cores mean, because warm sessions send uuid references.
- **Eviction vs plain compute: separated.**
  - KV-GPU k ≥ 8 has 80–91 % warm misses and saturated computed tok/s.
  - KV-HOST at the same k has 0 misses and computed tok/s 2–3× lower, and does not collapse.
  - So the KV-GPU collapse is eviction-driven, not the warm sessions' delta compute.
- **Cache-miss fallbacks (flag, as RH7).** 1–6 per cell (1.3–3.3 % of recall requests; > 1 % in every warm cell, the same as RH7's EAGER cells): an escalation scheduled at the same instant as an append of the same session.
  - The fallback sends full bytes (up to about 16 MB) and still hits the prefix.
  - They are counted in all statistics.
  - At k = 4 N = 1 they are a plausible part of the 0.54 s tail; elsewhere they are negligible against the effect sizes.
- **Warm-up exposure.** Sessions start at RH2-planned offsets and run 1× real time. In-window warm work per cell: 47–380 appends and 8–44 escalations. With only 21–44 escalations per cell, escalation p99s are 1-in-20 to 1-in-40 statistics.

## 4. Results consistency check (6 checks)

1. **Cross-check against committed measurements.** All agree; no disagreement > 2×.

   | quantity | this run | prior | source | ratio | agree? |
   |---|---|---|---|---|---|
   | episodic p99, k = 0, r = 0, 16 cells | 0.29–3.26 s | 0.26–3.88 s | D7 / D7b | 0.81–1.25 | agree |
   | episodic prompt tokens N = 1 / 3 | 378 / 1,062 | 378 / 1,062 | D3 / D7 | 1.00 | agree |
   | GPU KV capacity | 62,944 | 62,944 | RH5 / RH6 | 1.00 | agree |
   | K1 prompt tokens | 12,662 (e.g.) = R1 per question | R1 | parity gate | 1.00 | agree |
   | cold K1 TTFT, light load | 3.97–4.15 s (12.6k tok) | about 4.2 s (F3: 270 ms / 1k image + 0.8 s video format) | F3 | about 0.97 | agree |
   | D2 append tokens per frame | 90 | 90 | RH4 / RH7 | 1.00 | agree |
   | KV-HOST warm escalation TTFT p50 | 0.27–0.57 s (k = 8–16) | 0.55 s (D = 48) / 0.54–0.81 s (D ≤ 24) | RH7 / RH5 | about 0.5–1.0 | agree |
   | KV-GPU collapse at 8 warm sessions | escalation p50 52–115 s | 96 s at D = 8 | RH5 GPU-only | 0.6–1.2 | agree |

2. **Physical plausibility.**
   - Computed tok/s ≤ 5,252, against D7b's peak 15.1 req/s × 378 ≈ 5.7k tok/s: not faster than the committed curve.
   - KV-HOST *prompt* tok/s reaches 18.6k, but 13.8k of it is host hits (`external_prefix_cache_hits`), so it is not computed. A cache is the explanation, and it is labelled.
   - Host load of 852 GB / 240 s = 3.6 GB/s is well under H100 NVL PCIe Gen5 bandwidth, and RH6's loads were of the same order.
   - Warm append TTFT 0.20 s for 90–450 computed tokens over a cached 4–10k prefix is consistent with RH7.

3. **Distribution sanity.**
   - p50 / p90 / p99 per cell, and waiting mean / max, are reported.
   - No constants: episodic p99s vary across cells, and baselines with the same rate under the two KV configurations differ by 0.01–0.07 s.
   - Append and escalation counts are identical across the cells of one (k) condition (e.g. 189 appends at k = 8). This is expected: the RH2 plan and 1× session time are deterministic, so the work is identical by design, not a short-circuit.

4. **Definition audit.**
   - "Capacity" = D7's definition (highest level meeting the p99 budget), at the spec's levels only. "Level" = fraction of D7 / D7b's measured peak.
   - "Warm miss" = cached < 0.5 × the session's previous prompt.
   - "k" = concurrent warm D2 sessions, as RH5's D.
   - "Cold recall" = R1 K1 RICH video, uncached.
   - Budgets 0.45 / 1.21 s as pre-registered. p99 is linear, as D7.

5. **Claim linkage.**
   - FORMULATION's physical component: reconstruction cost grows with context, here shown as shared-replica queueing.
   - FORMULATION's placement and timing questions, in CLAIMS (joint representation × placement × timing beats decomposed policies):
     - **Supports** that warm state placement interacts with the co-located workload. Where the warm state lives (GPU vs host tier) decides whether 8 warm sessions cost one level of episodic capacity or all of it.
     - **Supports** that cold full-context recall must not share a latency-critical replica: even 1 per 20 s takes the whole budget.
   - Nothing measured is scoped out: KV moves only GPU ↔ host on one model.

6. **Proxy validity.**
   - Episodic budget p99 = TTFT, since decisions are 1–2 tokens. Valid.
   - Recall accuracy is not measured; the token-parity gate guarantees the same prompts as RH4 / R1, so their accuracy applies.

**Consistency check: PASS 6 / 6.**

## 5. Interpretation

- **On one 32B replica, recall load is not free, and its form matters more than its volume.**
  - Cold RICH questions are the worst neighbour per request. One every 20 s puts the episodic p99 at 2.7–2.9 s with the GPU under half busy. If cold recall must be served, it needs its own replica, or prefill isolation (chunk-size cap or priority) before it can share.
  - Warm sessions are cheap **while they stay warm**. With GPU-only KV that holds to about k = 2 (and k = 4 only at light load). Past the GPU KV size they collapse the replica.
  - Host offload keeps them warm to at least k = 16 at a cost of one capacity level (N = 3) or none (N = 1, k = 8).
- **Binding resources by condition:**
  - baseline: GPU compute;
  - cold recall: tail interference;
  - warm with GPU-only KV: GPU KV capacity → compute;
  - warm with host offload: per-step GPU time of long-context requests;
  - never API CPU, never the client.
- The N = 1 results are coarse. The spec's levels put the baseline at 25 % (50 % misses by 11 ms), so "no drop" at N = 1 means "no drop that one level could show".

## 6. Deviations (all stated before results were seen unless marked)

- Grid trimmed (§0): 20 recall conditions + 16 baseline cells, top-down levels. Dropped:
  - KV-HOST k = 2, 4;
  - KV-HOST cold-only;
  - k × r combinations other than (8, 0.1);
  - levels above the first passing one.
- Append cadence 10 s of session time, as RH7 (§0).
- **After seeing the result:** the analysis p99 for cells with unfinished requests uses nearest-rank with unfinished = ∞, because linear interpolation with ∞ is undefined. It changes no verdict: those cells fail under any definition. A first analysis pass that used nearest-rank everywhere flipped KV-GPU k4 N3 25 %. It was reverted to D7's linear definition, and the sensitivity is flagged (†).
- Monitor zombie fix and the GPU 2 interruption and resume (§2).

## 7. Outputs

- `results/cost/study_e10/e10b_requests_h100nvl.jsonl` (53,700 rows)
- `e10b_metrics_h100nvl.jsonl`
- `e10b_cpu_h100nvl.jsonl`
- `e10b_monitor_h100nvl.jsonl`
- `e10b_run_meta_h100nvl.json`
- `e10b_results.json`

Scripts: `experiments/cost/study_e10b_mixed.py`, `study_e10b_analyse.py`.
