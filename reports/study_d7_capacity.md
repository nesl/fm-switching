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
  - **Correction (2026-11-05):** this is not true at every level. The D3 manifest has 6,010 requests per N, so a level above ~20 req/s over 300 s cycles through it again. In 8 of the 48 levels (all 4B-I / N = 3: closed loop at concurrency 4–32, open loop at 75–110 %), 855–3,921 requests repeated a request id already sent in that level. Prefix caching was off and the processor cache was 0 GB, so a repeat is recomputed in full. No number in this report changes. (Counted with `study_d4_d7_analyse.repeats`, read-only.)
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

---

## StudyD7b: N = 1 capacity (added 2026-11-05)

**E-id:** StudyD7b (pre-registered 2026-11-05, before any GPU run; authorised by the user).

**Status:** finished 2026-11-05 17:21 → 19:27 on h100nvl GPU 2, after StudyD14-trace.
- **Not void:** 248 in-run isolation checks, 0 overlaps.
- The dataset copy finished at 16:49. A queue gate set `~/.fmnet_latency_active` before the run and found no pull to pause.

**Sources (`results/cost/study_d7b/`; earlier D7 files untouched):**
- `study_d7b_levels_h100nvl.jsonl`
- `study_d7b_requests_h100nvl.jsonl.gz`
- `study_d7b_isolation_h100nvl.jsonl`
- `study_d7b_others_h100nvl.jsonl`
- `study_d7b_run_meta_h100nvl.json`
- `study_d7b_results_h100nvl.json` (summary with derived streams)

**Method:** exactly StudyD7's script, server settings, isolation rules and formula (`study_d7_capacity.py --ns 1 --out results/cost/study_d7b --slug study_d7b`; only N and the output location are parameters).
- 32B-I, then 4B-I, at N = 1: the StudyD3 SMALL N = 1 requests, the same frames StudyD4 used, cycled in the D3 manifest order.
- 378 prompt tokens.
- Greedy, max_tokens 8, streamed. Prefix caching off; processor cache 0 GB.

### Observations
**Part A, closed loop: throughput req/s (TTFT p50 / p99, s; GPU-2 utilisation mean; SM clock median MHz)**

| concurrency | 32B-I / N = 1 | 4B-I / N = 1 |
|---|---|---|
| 1 | 6.30 (0.134 / 0.148; 73 %; 1,230) | 13.81 (0.070 / 0.083; 29 %; 1,785) |
| 2 | 9.26 (0.162 / 0.205; 89 %; 1,080) | 23.77 (0.079 / 0.113; 40 %; 1,770) |
| 4 | 12.73 (0.278 / 0.282; 100 %; 945) | 37.62 (0.096 / 0.126; 55 %; 1,755) |
| 8 | 13.56 (0.536 / 0.546; 100 %; 870) | 56.55 (0.125 / 0.190; 76 %; 1,575) |
| 16 | 14.52 (1.045 / 1.061; 100 %; 855) | 77.95 (0.179 / 0.236; 95 %; 1,305) |
| 32 | 15.10 (1.647 / 1.908; 100 %; 870) | 78.03 (0.373 / 0.492; 94 %; 1,260) |
| **peak** | **15.10** | **78.03** |

**Part B, open loop: achieved req/s / TTFT p50 / p90 / p99 from the scheduled arrival (s); errors**

| % of peak | 32B-I / N = 1 | 4B-I / N = 1 |
|---|---|---|
| 25 | 3.76 / 0.142 / 0.200 / 0.261; 0 | 19.49 / 0.083 / 0.110 / 0.137; 0 |
| 50 | 7.72 / 0.178 / 0.310 / 0.449; 0 | 39.13 / 0.098 / 0.146 / 0.204; 0 |
| 75 | 11.53 / 0.298 / 0.713 / 1.340; 0 | 58.98 / 0.136 / 0.234 / 0.318; 0 |
| 90 | 13.95 / 0.744 / 1.317 / 2.464; 0 | 70.40 / 0.193 / 0.364 / 0.554; **1** |
| 100 | 15.30 / 2.575 / 4.251 / 5.083; 0 | 78.31 / 0.337 / 0.740 / 1.157; 0 |
| 110 | 16.96 / 17.73 / 32.54 / 33.98; 0 | 86.68 / 58.60 / 103.9 / 115.7; **28** (client-bound, see below) |

- **Unfinished:** 0 at every level.
- **Queue delay** (client-side, sent − scheduled): median ≤ 1 ms, and dispatch lateness p99 ≤ 0.063 s, at every level except 4B-I 110 %.
- **4B-I 110 % is CLIENT-BOUND:**
  - Dispatch lateness had a median of 45.9 s and a p99 of 103 s, and GPU utilisation fell to 75 %.
  - Its TTFTs therefore include client queueing; they are not a server measurement.
  - It fails every p99 limit regardless.
- **Errors:** 29 in total, all httpx `ReadError` with no HTTP status:
  - 1 at 4B 90 %, 11 ms after sending;
  - 28 at 4B 110 %, 11–114 s after sending.

  Neither server log (`logs/study_x_server_{32BI,4BI}_1105_*.log`) contains an error line. The cause is not confirmed. D7's method has no retries, so the errors stand as recorded.
- **Repeated requests within a level** (6,010 distinct N = 1 requests):
  - 32B-I never repeats (≤ 5,088 requests per level).
  - 4B-I repeats in 10 of 12 levels, up to 20,039 of 26,049 requests (110 %). Caches were off, so each repeat is recomputed in full.
- **SM clock:** the GPU-2 SM clock median falls as load rises (32B: 1,230 → 855 MHz; 4B: 1,785 → 1,260 MHz). It was logged, not controlled; the cause was not checked (as in StudyD4).

### Derived: streams per GPU
**Formula:** D7's, unchanged. Streams = highest open-loop achieved throughput among levels with p99 TTFT ≤ L and **0 errors / unfinished**, × evaluation interval T.

**Scope:** localhost arithmetic for this input and server, no network. **Not a deployment claim.**

| model / N | p99 ≤ 1 s: T = 1 / 2 / 5 s | p99 ≤ 2 s: T = 1 / 2 / 5 s | p99 ≤ 5 s: T = 1 / 2 / 5 s |
|---|---|---|---|
| 32B-I / 1 | 7.7 / 15.4 / 38.6 | 11.5 / 23.1 / 57.7 | 14.0 / 27.9 / 69.8 |
| 4B-I / 1 | 59.0 / 118.0 / 294.9 | 78.3 / 156.6 / 391.6 | 78.3 / 156.6 / 391.6 |

- **The single 4B 90 % ReadError decides one cell.** Under the formula's zero-error rule the 90 % level (p99 0.554 s) is excluded, so 4B p99 ≤ 1 s uses the 75 % level (58.98 req/s). Without that rule it would be 70.40 req/s (70.4 / 140.8 / 352.0 streams). Both are stated; the formula's value is the registered one.
- Values are quantised by the six tested levels.

### Comparison with StudyD4 N = 1 (single request, same frames, same stack)
| model | D7b closed-loop concurrency 1 TTFT p50 / p99 | StudyD4 TTFT p50 / p99 | ratio (p50) |
|---|---|---|---|
| 32B-I | 0.134 / 0.148 s | 0.137 / 0.142 s | 0.98 |
| 4B-I | 0.070 / 0.083 s | 0.074 / 0.082 s | 0.95 |

Input, stack and decoding match. D4 sent one request at a time with a pause; D7b concurrency 1 sends back to back.

### Results consistency check (StudyD7b)
**1. Cross-check:** concurrency-1 TTFT agrees with StudyD4 (ratios 0.95–0.98, table above). Prompt tokens are 378, as in D4.

**2. Physical plausibility.** Implied prefill at peak:

| model | calculation | tokens/s | StudyD7 (N = 3 / 9) |
|---|---|---|---|
| 32B-I | 15.10 × 378 | ~5.7k | ~5.7k / 5.6k |
| 4B-I | 78.0 × 378 | ~29.5k | ~31.7k / 30.2k |

Nearly constant across N within each model, as compute-bound prefill predicts. Nothing is > 2× a committed rate, caches were off, and repeats were recomputed. **PASS.**

**3. Distribution sanity:** p50 / p90 / p99 / max reported, rising with load; no constants. **PASS**, with the client-bound 4B 110 % level flagged.

**4. Definition audit:** TTFT, throughput, peak and the streams formula are identical to StudyD7. **PASS.**

**5. Claim linkage:** as StudyD7 (cloud-tier capacity per standing query). N = 1 is the cheapest input.

**6. Proxy validity:** as StudyD7. In addition, the 4B levels repeat requests heavily. With caches off this does not change compute, but the request mix is less varied than at 32B.

### Interpretation (StudyD7b)
- **At N = 1, capacity is about 2.8× (32B) and 2.6× (4B) the N = 3 values in StudyD7.** That is consistent with throughput set by prompt tokens: 378 vs 1,062.
- **32B-I at N = 1 meets p99 ≤ 1 s up to ~7.7 req/s,** about 38 streams at a 5 s evaluation interval. At N = 9 it met that limit at no tested level.
- **4B-I at N = 1 carries roughly 5× the 32B load** under the same limits.
