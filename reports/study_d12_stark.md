# StudyD12-stark: STARK (text only) accuracy and latency for 4B-I, 32B-I and 32B-Thinking

**E-id:** StudyD12-stark (pre-registered 2026-11-04, before any GPU run).

**Status:** finished 2026-11-05 on h100nvl GPU 2.
- Accuracy runs 01:27–05:51.
- Latency runs 05:51–08:35; **not void** (323 in-run isolation checks, 0 overlaps).
- All 500 items ran in every arm; the Thinking projection was 3.76 h ≤ 4 h, so the 250-item cap did not trigger.

**Sources:**
- `results/ts/study_d12_stark/stark_manifest.jsonl`, `stark_sample.json`
- `stark_requests_h100nvl.jsonl`, `stark_run_meta_h100nvl.json`
- `stark_latency_requests_h100nvl.jsonl`, `stark_latency_isolation_h100nvl.jsonl`
- `stark_results_h100nvl.json`

**Deviation (implementation, not method):**
- **What happened:** the first attempt of the `sample` step (01:24) was launched with an interpreter that lacked `httpx` and failed. The four dependent jobs then failed for lack of a manifest.
- **What was re-run:** all five steps were re-queued unchanged with the correct interpreter as `*_r2` at 01:27. FAILED markers from the first attempt are kept in `logs/dseries_done/`.
- **Watchdog gap:** the GPU-2 watchdog and host monitor were not running from 01:27 to 01:44. When the queue restarted, the old sessions had not yet exited, so new ones could not start; they were restarted at 01:44. No error occurred in that window, but a short foreign process on GPU 2 cannot be ruled out for it.

## Setup

**Items:**
- 500 STARK items from `prquan/STARK_10k`, seed 0. Stratified round-robin over the 41 tiered families (12–13 per family).
- The 50 StudyD12-pilot items are excluded by query text (6 encountered and skipped).
- Composition: 308 categorical and 192 continuous items; tiers 1/2/3 = 192/223/85.

**Input:** the questions verbatim, TEXT only (the series is inside the question).
- Prompt tokens: median 525, max 2,157.

**Arms (same items, prompt and stack; decoding differs by design):**

| arm | revision | decoding | max_tokens |
|---|---|---|---|
| 4B-I | `@ebb281ec` | greedy | 2,048 |
| 32B-I | `@0cfaf481` | greedy | 2,048 |
| 32B-Thinking | `@7edd10ff` | T 1.0, top_p 0.95, top_k 20, seed 0 | 16,384 |

- All three run at concurrency 8 on vLLM 0.31.0, FA3, with prefix and processor caches off.

**Scoring (pre-registered):**
- **Categorical:** the first number in the LAST `[RESULTS_START] … [RESULTS_END]` span (for Thinking, the text after `</think>`), compared with the answer.
- **Continuous:** STARK's own error measure, ported from `nesl/STARK_Benchmark` `distance.py`:
  - RMSE, or relative L2 for the four field-variable tasks.
  - Benchmark default fill when the loc_/track_ families are unparsable.
  - A prediction shorter than the answer is invalid.
- **Truncation** (`finish_reason` = length) counts as a failure and is also reported as its own rate.

**Latency (D10 method):**
- 50 items per arm (`Random(0)` sample), one request at a time, cold, streamed.
- The first request per model load is discarded.
- Isolated: nothing else of ours ran.

**Analysis fixes made before writing this report (summary or scoring bugs; the per-item measure is unchanged):**
1. A truncated item could count as "parsed" if a result span appeared inside unfinished reasoning. Truncation now always counts as a failure, as pre-registered.
   - Categorical accuracy was unchanged by this: no truncated item had been scored correct.
   - Continuous parse rate for Thinking fell from 0.44 to 0.36.
2. NaN errors (unparsed field-variable predictions, which STARK leaves as NaN) were turning per-family medians into NaN. They are now counted separately and kept out of the median and mean.

## Observations

### Categorical items (n = 308; majority baseline 50.0 %, chance 50 %)

| arm | correct | accuracy [Wilson 95 %] | truncated (= no-parse failures) | completion tok p50 / p90 / max |
|---|---|---|---|---|
| 4B-I | 252 | **81.8 %** [77.1, 85.7] | 0 | 12 / 21 / 42 |
| 32B-I | 273 | **88.6 %** [84.6, 91.7] | 18 (5.8 %) | 201 / 758 / 2,048 |
| 32B-Thinking | 285 | **92.5 %** [89.0, 95.0] | 6 (1.9 %) | 4,178 / 16,384 / 16,384 |

- Completion tokens are over all 500 items.

**Paired bootstrap (same 308 items, 2,000 resamples, seed 0):**

| comparison | difference [95 % CI] |
|---|---|
| 32B-I − 4B-I | **+6.8 pp** [+1.6, +12.0] |
| 32B-T − 4B-I | **+10.7 pp** [+5.8, +15.3] |
| 32B-I − 32B-T | −3.9 pp [−7.8, 0.0] (upper bound at 0) |

### Continuous items (n = 192)

**Overall per arm:**
- **Parse rate:** 4B-I 1.00, 32B-I 1.00, 32B-Thinking **0.36**.
- **Thinking truncation:** 123 of its 192 continuous items were truncated, against 6 of 308 categorical items.
- **Default fill (Thinking):** 108 items received the benchmark's default prediction.
- **NaN errors:** 6 (spatial_impute, Thinking only).

**60 items are "invalid" in every arm:** the five `track_*_online` trajectory families (12 items each).
- The answer is a T × 2 trajectory, and the models write one result span per step.
- STARK's parser reads only the first span, so the prediction is shorter than the answer.
- The identical count across arms shows this is a property of the single-turn prompt combined with the ported measure, not of any model.
- I did not change the measure.
- **These 60 items are unscored.** Scoring them would need a decision (e.g. multi-turn online evaluation as STARK may intend, or concatenating spans), which is a methodological change for the user to decide.

**Median error by family** (n in parentheses; the Thinking column has all items, then parsed-only; lower is better):

| family (12 items each) | 4B-I | 32B-I | 32B-T (all) | 32B-T (parsed only) |
|---|---|---|---|---|
| loc_bearing | 3.21 | 3.34 | 2.77 | — (0) |
| loc_event_spatio | 2.95 | 2.49 | 2.42 | 0.139 (2) |
| loc_event_temp | 0.513 | 0.589 | 2.61 | 0.0047 (1) |
| loc_range | 2.43 | 1.83 | 1.97 | 0.0166 (3) |
| loc_range_bearing | 3.08 | 2.36 | 0.0865 | 0.0704 (9) |
| loc_region | 2.12 | 1.31 | 1.27 | 1.27 (10) |
| spatial_impute (rel. L2) | 0.00158 | 0.00113 | 0.00077 (6; 6 NaN) | 0.00077 (5) |
| spatiotemporal_forecast (rel. L2) | 0.105 | 0.0521 | 0.0674 | 0.0674 (12) |
| spatiotemporal_impute (rel. L2) | 0.0238 | 0.0188 | 0.0180 | 0.0180 (12) |
| temporal_impute (rel. L2) | 0.0321 | 0.0220 | 0.0216 | 0.0216 (12) |
| track_event_temp_online | 5.43 | 5.30 | 4.79 | — (0) |

- 4B-I and 32B-I parsed every item, so their all-items and parsed-only medians are identical.
- **Thinking's "all" medians mix two kinds of item:** precise answers where it finished, and the benchmark's default fill where it was truncated. On loc_event_temp, for example, the median of 2.61 is driven by fills. Its parsed-only medians are much lower but rest on 0–3 items in four loc_ families.

### Single-request latency (50 items per arm; warm-ups excluded)

| arm | TTFT p50 / p90 / max (s) | total p50 / p90 / max (s) | completion tok p50 / p90 / max | truncated / runaway |
|---|---|---|---|---|
| 4B-I | 0.031 / 0.043 / 0.065 | 0.085 / 0.123 / 0.205 | 12 / 21 / 37 | 0 |
| 32B-I | 0.113 / 0.259 / 0.385 | 4.60 / 14.4 / 42.8 | 199 / 640 / 1,864 | 0 |
| 32B-Thinking | 0.103 / 0.243 / 0.403 | **174.5 / 389.6 / 391.0** | 7,457 / 16,384 / 16,384 | 13 / 50 |

- Prompt tokens: median 525–527, max 2,157–2,159.
- For Thinking, TTFT is time to the first streamed token, which is reasoning text, not the answer.

## Results consistency check

**1. Cross-check against committed measurements.**

| quantity | this run | prior | source | ratio | agree? |
|---|---|---|---|---|---|
| 4B-I STARK categorical accuracy | 81.8 % [77, 86] (n = 308) | 88 % [73, 95] (n = 34) | StudyD12-pilot | 0.93 | agree (CIs overlap) |
| 32B-I STARK categorical accuracy | 88.6 % (cap 2,048) | 74 % (cap 512; 7 truncations) | StudyD12-pilot | 1.20 | different cap; explained below |
| prompt tokens median / max | 525 / 2,157 | 535 / 2,118 | StudyD12-pilot | ~1.0 | agree |
| 32B decode rate, single request | 32B-I ~43 tok/s (199 tok / 4.6 s); Thinking 16,384 tok / ~389 s ≈ 42 tok/s | ~43 tok/s | StudyD10 | ~1.0 | agree |

- **Why the 32B-I accuracy differs from the pilot:**
  - The pilot's 32B number was capped at 512 tokens (7 truncations). On the 27 items it did answer, it scored 25/27 = 93 %.
  - At a 2,048 cap, 32B-I truncates 5.8 % of categorical items.
  - So the difference is the pre-registered cap change, not a disagreement in measurement.

**2. Physical plausibility.**
- Decode is about 42–43 tok/s for 32B in both modes, matching StudyD10.
- 4B-I has a TTFT of 0.031 s for about 525 tokens, roughly 17k tok/s prefill on text-only input. That is plausible for a 4B model on an H100, and caches were off.
- Thinking's maximum total time is 391 s = 16,384 tokens at ~42 tok/s, the token cap.
- **PASS.**

**3. Distribution sanity.**
- Spreads are reported.
- Completion tokens vary widely (Thinking 7k median, with a cap pile-up).
- The one constant is structural: the same 60 invalid items in every arm, explained above (prompt/measure mismatch).
- **PASS, with that flag.**

**4. Definition audit.**
- Scoring is as pre-registered, and truncation is a failure.
- Two summary bugs were found and fixed before this report (see Setup).
- The continuous measure is STARK's own; the online-tracking family mismatch is recorded, not redefined.

**5. Claim linkage.** This bears on the feasibility of using a cloud-tier larger or reasoning model for time-series questions. It is not a FORMULATION.md causal claim (registered as feasibility). The accuracy versus cost trade-off is:

| arm | categorical accuracy | single-request time p50 |
|---|---|---|
| 4B-I | 82 % | 0.09 s |
| 32B-I | 89 % | 4.6 s |
| 32B-Thinking | 93 % | 175 s |

**6. Proxy validity.**
- STARK TEXT items stand in for sensor-reasoning queries, as in the pilot.
- Single-request localhost latency is a lower bound on cloud response time (no network, no contention).

## Interpretation

- **Categorical items:**
  - All three arms are far above the 50 % majority baseline.
  - The larger model helps: +6.8 pp for 32B-I over 4B-I.
  - Thinking helps further over 4B-I (+10.7 pp).
  - Thinking versus 32B-I is borderline (+3.9 pp, CI upper bound exactly 0).
- **Thinking costs a great deal more:** a median of about 175 s per request versus 4.6 s (32B-I) and 0.09 s (4B-I). A quarter of its outputs hit the 16k cap.
- **Continuous items:** Thinking's measured error is dominated by truncation; it parsed only 36 % of them. Where it finished, its errors are mostly the lowest.
  - With five of eleven families resting on 0–3 parsed items, I do not rank the arms on continuous items.
- **Online-tracking items:** the 60 unscored items need a scoring decision before any statement about them.
