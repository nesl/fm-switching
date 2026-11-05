# StudyD4-latency: single-request latency for the dashcam input on one H100

**E-id:** StudyD4-latency (pre-registered 2026-11-04, before any GPU run).

**Status:** finished 2026-11-04 21:13–21:17 on h100nvl GPU 2. **Not void:** 9 in-run isolation checks, 0 overlaps.

**Sources:**
- `results/cost/study_d4/study_d4_requests_h100nvl.jsonl`, `study_d4_isolation_h100nvl.jsonl`, `study_d4_others_h100nvl.jsonl`, `study_d4_snapshots_h100nvl.jsonl`, `study_d4_run_meta_h100nvl.json`.
- Summary: `study_d4_results_h100nvl.json`.

## Setup

**Requests:**
- 50 (clip, offset) pairs: a `Random(0)` sample of the StudyD3 N = 9 request ids (development clips).
- The same pairs are used at N = 1 and N = 3.
- Frames are StudyD3's SMALL 768×432 PNGs, with StudyD3's header and query.

**Models:** 4B-I (`@ebb281ec`), then 32B-I (`@0cfaf481`).

**Stack:**
- vLLM 0.31.0, FA3, max_model_len 32,768, gpu-memory-utilization 0.90.
- **Prefix caching off; multimodal processor cache 0 GB.**
- **Caching:** vLLM's prefix-cache and multimodal-cache hit counters were 0 before and after each model's run. `cached_tokens` = 0 on all 300 measured requests. Nothing was cached before measurement, and no request could be served from cache, so all numbers are cold.

**Decoding:** greedy, max_tokens 8, seed 0, streamed with usage.

**Procedure:**
- One request at a time on localhost, with bodies serialised in advance.
- The first request after each model load is a warm-up. It is discarded and logged:
  - 4B N = 1: TTFT 0.071 s.
  - 32B N = 1: TTFT 0.126 s.

**Isolation:**
- No other process of ours ran: checked over 2 clear pre-start checks 60 s apart, then every ~30 s during the run.
- Other users' GPU processes and per-user CPU were logged (`study_d4_others_h100nvl.jsonl`):
  - liying on GPUs 0/1, gaofeng's vLLM on GPU 3, none on GPU 2.
  - liying used about 200 % CPU throughout.

## Observations

| model / N | n (errors) | prompt tok | TTFT p50 / p90 / p99 / max (s) | TTFT min (s) | total p50 (s) | completion tok p50 | GPU-2 SM clock p50 (MHz) |
|---|---|---|---|---|---|---|---|
| 4B-I / 1 | 50 (0) | 378 | 0.074 / 0.078 / 0.082 / 0.083 | 0.045 | 0.078 | 2 | 1,785 |
| 4B-I / 3 | 50 (0) | 1,062 | 0.102 / 0.111 / 0.128 / 0.140 | 0.090 | 0.106 | 2 | 1,755 |
| 4B-I / 9 | 50 (0) | 3,090 | 0.227 / 0.238 / 0.270 / 0.291 | 0.215 | 0.233 | 2 | 1,759 |
| 32B-I / 1 | 50 (0) | 378 | 0.137 / 0.140 / 0.142 / 0.142 | 0.112 | 0.162 | 2 | 1,406 |
| 32B-I / 3 | 50 (0) | 1,062 | 0.260 / 0.265 / 0.280 / 0.288 | 0.222 | 0.285 | 2 | 1,328 |
| 32B-I / 9 | 50 (0) | 3,090 | 0.615 / 0.628 / 0.666 / 0.700 | 0.593 | 0.640 | 2 | 1,050 |

**Request bytes (median per request; images are identical across models):**

| N | image bytes PNG | image bytes JPEG q90 | request body PNG (base64) | request body JPEG q90 (base64) |
|---|---|---|---|---|
| 1 | 354,902 | 59,601 | 473,650 | 79,917 |
| 3 | 1,057,532 | 177,773 | 1,410,683 | 237,672 |
| 9 | 3,188,243 | 529,361 | 4,252,063 | 706,896 |

- **JPEG q90 bytes** come from re-encoding the same frames. JPEG was **not** sent to the model, so these byte counts are for uplink arithmetic only. Whether JPEG changes the answers is not measured here.
- **TTFT scaling:** from N = 1 to N = 9, TTFT rises about 3.1× for 4B and about 4.5× for 32B.
- **SM clock:** the GPU's median SM clock during 32B requests was lower than during 4B requests, and lower at larger N (1,050 MHz at 32B N = 9 vs about 1,760 MHz for 4B). The clock was logged, not controlled. The cause (power or thermal limit) was not checked.

## Results consistency check

**1. Cross-check against committed measurements.**

| quantity | this run | prior | source | ratio | agree? |
|---|---|---|---|---|---|
| 32B-I TTFT, ~1k-token image prompt | 0.260 s (1,062 tok) | 0.26–0.30 s (~1k tok images) | StudyD10 | 0.87–1.0 | agree |
| 32B-I N = 9 TTFT, single request | 0.615 s | 0.643 s p50 (closed loop, concurrency 1) | StudyD7 (same session) | 0.96 | agree |
| 4B-I N = 9 TTFT, single request | 0.227 s | 0.232 s p50 (closed loop, concurrency 1) | StudyD7 | 0.98 | agree |
| N = 9 prompt tokens | 3,090 | 3,090 | StudyD2 / D3 | 1.00 | agree |

**2. Physical plausibility.**
- Implied prefill rates (prompt tokens / TTFT, including image encoding):
  - 32B: about 2.8k tok/s at N = 1 and about 5.0k tok/s at N = 9.
  - 4B: about 5.1k tok/s at N = 1 and about 13.6k tok/s at N = 9.
- The 32B rate is within 2× of StudyD10's ~3.2k tok/s measured on the same GPU and stack (at 12.6k tokens).
- No committed H100 4B curve exists. The 4B rate is 2.7× the 32B rate here, which is consistent with a model 8× smaller.
- Cache counters stayed at 0. **PASS.**

**3. Distribution sanity.**
- Spread is reported (min to max).
- TTFT varies with N and model, and varies within each cell.
- Completion tokens = 2 everywhere: the answer word plus end-of-sequence, as expected for a Yes/No answer.
- **PASS.**

**4. Definition audit.**
- TTFT runs from immediately before send to the first streamed token; total runs to stream close. This is the StudyD10 definition.
- N, SMALL and the headers are StudyD3's.
- **PASS.**

**5. Claim linkage.** FORMULATION.md cost side, which concerns the cloud-tier response time for the dashcam standing query.
- The run supplies the measured cloud-side compute component only.
- No network, uplink or queueing time is included.

**6. Proxy validity.**
- Localhost single-request latency stands in for "cloud response time" without network or contention. That is valid only as a lower bound on the server-side part.
- JPEG bytes stand in for an uplink payload whose effect on accuracy is untested.
- Both are stated as limitations.

## Interpretation

- **Compute is not the bottleneck when the server is otherwise idle:** at N = 9, compute adds about 0.23 s (4B) and about 0.62 s (32B) per evaluation.
- **Upload size probably dominates on a cellular link.** At N = 9 a request is about 4.3 MB as PNG, or about 0.7 MB at JPEG q90. Uplink arithmetic was not done here.
- This is a single-request, no-contention measurement. Load behaviour is in StudyD7.
