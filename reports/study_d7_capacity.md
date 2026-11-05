# StudyD7-capacity: how many dashcam standing-query streams can one H100 carry?

**E-id:** StudyD7-capacity (pre-registered 2026-11-04, before any GPU run).

**Status:** finished 2026-11-04 21:17 → 2026-11-05 01:24 on h100nvl GPU 2. **Not void:** 0 in-run isolation overlaps.

**Sources:**
- `results/cost/study_d7/study_d7_levels_h100nvl.jsonl` (one row per level).
- `study_d7_requests_h100nvl.jsonl.gz` (per request).
- `study_d7_isolation_h100nvl.jsonl`, `study_d7_others_h100nvl.jsonl` (other users' GPU / CPU activity; written by the run as `study_d4_others_h100nvl.jsonl` and renamed — a naming bug from code reused from StudyD4) and `study_d7_run_meta_h100nvl.json`.
- Summary with derived streams: `study_d7_results_h100nvl.json`.

## Setup

**Models:** 32B-I (`@0cfaf481`) then 4B-I (`@ebb281ec`). One server load per model. Within a load, N = 3 runs first, then N = 9.

**Requests:**
- StudyD3 SMALL requests from development clips, cycled in a fixed order, so every prompt within a level is distinct.
- Prompt tokens: 1,062 at N = 3 and 3,090 at N = 9.

**Stack:**
- vLLM 0.31.0, FA3, max_model_len 32,768, gpu-memory-utilization 0.90, TP 1.
- **Prefix caching off; multimodal processor cache 0 GB.**
- `--limit-mm-per-prompt image 9`, localhost.

**Decoding:** greedy, max_tokens 8, seed 0.

**Part A, closed loop:**
- Concurrency 1, 2, 4, 8, 16 and 32, 5 min each. The first 30 s are discarded.
- Peak = highest closed-loop throughput.

**Part B, open loop:**
- Poisson arrivals at 25 / 50 / 75 / 90 / 100 / 110 % of the Part A peak, 5 min each, with the first 30 s discarded.
- Each level uses its own seed (`default_rng(level index)`).
- Latency is measured from the **scheduled** arrival time. A 120 s drain follows each level; requests still unfinished after it are counted.

**Client accuracy:**
- p99 lateness in dispatching requests is ≤ 0.057 s at every level.
- Median client-side queue delay is ≤ 2.3 ms.
- So the latencies reflect the server, not the load generator.

**Isolation:** as in StudyD4. Nothing else of ours ran, and other users stayed on GPUs 0/1/3.

## Observations

### Part A: closed loop

**Throughput, req/s (p99 TTFT, s):**

| model / N | c = 1 | c = 2 | c = 4 | c = 8 | c = 16 | c = 32 | **peak** |
|---|---|---|---|---|---|---|---|
| 32B-I / 3 | 3.45 (0.28) | 4.39 (0.44) | 4.89 (0.78) | 5.24 (1.45) | 5.38 (2.73) | 5.37 (5.73) | **5.38** |
| 32B-I / 9 | 1.50 (0.66) | 1.70 (1.10) | 1.76 (2.14) | 1.77 (4.47) | 1.80 (8.88) | 1.80 (17.76) | **1.80** |
| 4B-I / 3 | 8.52 (0.12) | 15.10 (0.15) | 27.16 (0.16) | 28.95 (0.33) | 29.75 (0.66) | 29.87 (1.04) | **29.87** |
| 4B-I / 9 | 4.20 (0.26) | 6.35 (0.35) | 9.61 (0.50) | 9.70 (0.90) | 9.77 (1.63) | 9.78 (3.25) | **9.78** |

- 0 errors and 0 unfinished at every level.
- GPU utilisation reaches 99–100 % from concurrency 4 (32B: from concurrency 2 at N = 9).
- GPU memory peaks at 83–87 GiB, as allocated by gpu-memory-utilization 0.90.

### Part B: open loop

**Achieved throughput, req/s / p99 TTFT, s, from scheduled arrival:**

| model / N | 25 % | 50 % | 75 % | 90 % | 100 % | 110 % |
|---|---|---|---|---|---|---|
| 32B-I / 3 | 1.22 / 0.53 | 2.69 / 1.04 | 4.21 / 3.46 | 4.81 / 3.88 | 5.46 / 10.05 | 6.04 / 37.36 |
| 32B-I / 9 | 0.40 / 1.22 | 0.91 / 2.18 | 1.50 / 6.83 | 1.50 / 7.61 | 1.77 / 9.87 | 2.10 / 54.60 |
| 4B-I / 3 | 7.47 / 0.20 | 15.06 / 0.28 | 22.67 / 0.53 | 27.14 / 0.91 | 30.01 / 4.81 | 32.92 / 34.18 |
| 4B-I / 9 | 2.31 / 0.48 | 4.89 / 0.68 | 7.50 / 1.66 | 8.96 / 2.74 | 9.95 / 7.03 | 11.02 / 38.78 |

- 0 errors and 0 unfinished at every level.
- **Achieved vs target rate:** achieved throughput is the realised Poisson arrival count over the 270 s window, so it differs from the target by sampling variation. At 32B / 9, 75 % gave 406 arrivals against about 364 expected (+2.2 SD), and 90 % gave 404 against about 437 (−1.5 SD). The two levels therefore realised nearly the same rate (1.50 req/s).
- **Small samples:** p99 at the lowest levels rests on few requests (32B / 9 at 25 %: 109 requests), so it is close to the maximum.
- At 100–110 % of peak, latency grows without bound over the 5 min, as expected for an overloaded queue.

### Derived: streams per GPU

**Method (pre-registered):** streams = (highest open-loop achieved throughput among levels with p99 TTFT ≤ L and 0 errors / unfinished) × evaluation interval T.

**Scope:** this is arithmetic for this input and server on localhost, with no network. It is **not a deployment claim**.

| model / N | p99 ≤ 1 s: T = 1 / 2 / 5 s | p99 ≤ 2 s: T = 1 / 2 / 5 s | p99 ≤ 5 s: T = 1 / 2 / 5 s |
|---|---|---|---|
| 32B-I / 3 | 1.2 / 2.4 / 6.1 | 2.7 / 5.4 / 13.5 | 4.8 / 9.6 / 24.1 |
| 32B-I / 9 | < lowest tested level | 0.4 / 0.8 / 2.0 | 0.9 / 1.8 / 4.5 |
| 4B-I / 3 | 27.1 / 54.3 / 135.7 | 27.1 / 54.3 / 135.7 | 30.0 / 60.0 / 150.1 |
| 4B-I / 9 | 4.9 / 9.8 / 24.5 | 7.5 / 15.0 / 37.5 | 9.0 / 17.9 / 44.8 |

- The values are quantised by the six tested load levels, so the true limit lies between the passing level and the next one.
- 32B / 9 under p99 ≤ 1 s: even the 25 % level (p99 1.22 s) misses the limit, so no value is derived.

## Results consistency check

**1. Cross-check against committed measurements.**

| quantity | this run | prior | source | ratio | agree? |
|---|---|---|---|---|---|
| 32B-I N = 3 TTFT, concurrency 1 | 0.264 s p50 | 0.260 s p50 | StudyD4 (same session) | 1.02 | agree |
| 32B-I N = 9 TTFT, concurrency 1 | 0.643 s | 0.615 s | StudyD4 | 1.05 | agree |
| 4B-I N = 3 / N = 9 TTFT, concurrency 1 | 0.113 / 0.232 s | 0.102 / 0.227 s | StudyD4 | 1.11 / 1.02 | agree |
| 32B-I TTFT, ~1k-token image prompt | 0.264 s | 0.26–0.30 s | StudyD10 | ~1 | agree |

- No earlier committed capacity (throughput-under-load) measurement exists for these models and this input.

**2. Physical plausibility.** Implied prefill throughput at peak:

| model / N | calculation | tokens/s |
|---|---|---|
| 32B / 3 | 5.38 × 1,062 | ~5.7k |
| 32B / 9 | 1.80 × 3,090 | ~5.6k |
| 4B / 3 | 29.9 × 1,062 | ~31.7k |
| 4B / 9 | 9.78 × 3,090 | ~30.2k |

- Within each model the tokens/s is nearly constant across N, which is what compute-bound prefill predicts.
- 32B at ~5.6k tok/s is about 1.1× its single-request rate at N = 9 (StudyD4, ~5.0k). Batching adds little because one 3k-token prefill already saturates the GPU.
- 4B gains about 2.2× from batching (13.6k → 30k).
- No rate exceeds a committed curve by more than 2× on a like-for-like basis. Cache counters are off and prompts are distinct. **PASS.**

**3. Distribution sanity.**
- p50 / p90 / p99 / max are reported per level, and latency rises with load.
- No constants where variation is expected.
- **PASS**, with the caveat on small-sample p99 at the lowest levels.

**4. Definition audit.**
- TTFT is as in StudyD4 / D10. In open loop it is measured from the scheduled arrival.
- Throughput = completed requests started after warm-up, divided by the 270 s window.
- "Peak" = highest Part A throughput.
- **PASS.**

**5. Claim linkage.** FORMULATION.md cost / provisioning side: how much cloud capacity a standing query needs at a given N, model and latency target.
- The derived table speaks to cloud-tier capacity.
- It does not speak to device cost or network.

**6. Proxy validity.** Localhost Poisson arrivals stand in for many independent dashcam streams. This is valid for server capacity. It does not model:
- synchronised (bursty) arrivals;
- network variability;
- input variation beyond the D3 development clips.

These are stated limitations.

## Interpretation

- **Prompt tokens set capacity.** Throughput at saturation scales with 1 / (prompt tokens) within each model: N = 9 gives about 1/3 the req/s of N = 3.
- **4B carries about 5.5× as many streams as 32B** at the same N.
- **32B at N = 9 is the tightest case:** under a 2 s p99 it supports 0.4 req/s, about 2 streams at a 5 s evaluation interval. Under p99 ≤ 1 s it supports none at the tested loads.
- **Latency limits bind well below peak.** Holding p99 near 1–2 s costs roughly 25–50 % of peak throughput for 32B, and about 10 % for 4B at N = 3.
