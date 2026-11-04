# StudyD10: single-request latency snapshot, 32B on h100nvl GPU 2

**E-id:** StudyD10 (pre-registered 2026-11-04). **Run:** 13:35:48–14:26:47 on 2026-11-04. **Status:** COMPLETE; **not void**.

**Conditions:**
- vLLM 0.31.0 (FA3); prefix caching **off**, multimodal processor cache **off**.
- One request at a time, cold, on localhost (no network).
- Request bodies are pre-serialised before the clock starts.
- **Shared host:** another user's vLLM ran on GPU 3 throughout; GPUs 0 and 1 were idle.
- The first request after each model load is discarded and logged.

**Cache check:** the prefix and multimodal cache-hit counters stayed at 0 across every load, warm-ups included.

| load | requests | model | decoding |
|---|---|---|---|
| S-EMBER | 50 | Qwen3-VL-32B-Thinking | R1 K1 (RICH) video requests with K2's exact settings: T 1.0, top_p 0.95, top_k 20, max 16,384, seed 42 |
| ERQA + MV-RoboBench | 50 + 50 | Qwen3-VL-32B-Thinking | StudyD9's Thinking settings, request seed 0 |
| ERQA + MV-RoboBench | 50 + 50 | Qwen3-VL-32B-Instruct | greedy, max 512 |

All samples are `random.Random(0).sample`.

## Isolation (spec: no work of ours may overlap)

The run waited at a pre-start guard (40 checks, 13:01–13:34) until two consecutive checks 60 s apart saw no other work of ours: our StudyD11 input build had to finish first. From `run start` to `run end` there were **108 checks** (start, every 30 s, end): **0 overlaps**, and no GPU process of ours outside the run.

*Implementation fix:* the run script logged `VOID=True` because it also counted the pre-start-wait checks, which see overlap by design. I fixed the script, and the meta now holds the recomputed value (`void: false`, plus `void_as_logged_by_run: true` and the correction note).

## Results (observations; seconds; tokens)

| cell | TTFT p50 / p90 / max | total p50 / p90 / max | prompt tok p50 / p90 / max | completion tok p50 / p90 / max | runaways | neighbour-flagged |
|---|---|---|---|---|---|---|
| S-EMBER K1, Thinking | 3.908 / 4.008 / 4.034 | 8.08 / 17.48 / 38.95 | 12,611 / 12,743 / 13,048 | 181 / 564 / 1,450 | 0 | 0 |
| ERQA, Thinking | 0.301 / 0.477 / 0.854 | 6.81 / 34.60 / 161.19 | 1,132 / 1,946 / 3,528 | 280 / 1,485 / 6,881 | 0 | 0 |
| MV-RoboBench, Thinking | 0.265 / 0.284 / 0.300 | 13.24 / 55.05 / 161.75 | 1,033 / 1,078 / 1,079 | 561 / 2,356 / 6,874 | 0 | 3 (q 51, 31, 280) |
| ERQA, Instruct | 0.283 / 0.478 / 0.798 | 0.31 / 0.50 / 0.82 | 1,130 / 1,944 / 3,526 | 2 / 2 / 2 | 0 | 0 |
| MV-RoboBench, Instruct | 0.258 / 0.265 / 0.283 | 0.29 / 0.40 / 0.42 | 1,031 / 1,076 / 1,077 | 7 / 7 / 7 | 0 | 0 |

- **Time to `</think>` (p50):** S-EMBER 7.99 s; ERQA 6.74 s; MV-RoboBench 13.17 s.
- **Decode rate (p50):** 40–44 tokens/s per request.
- **GPU-2 SM clock:** median of per-request medians 1,219–1,346 MHz; per-request minimum 472–592 MHz, the idle clock at the request edges.
- **Errors:** 0 of 300. Every Thinking request closed `</think>`.
- **Accuracy:** indicative only (n = 50, not a D10 aim). It is stored in the results JSON.

**Discarded warm-ups** (first request after each model load):

| load | warm-up TTFT | warm-up total |
|---|---|---|
| S-EMBER | 4.03 s | 6.28 s |
| images, Thinking | 0.33 s | 38.1 s |
| images, Instruct | 0.41 s | 0.44 s |

## Interpretation (separate from the observations)

- **TTFT is set by the prompt.** About 3.9 s for the ~12.6k-token S-EMBER video prompt (~3,200 tokens/s prefill), and about 0.26–0.30 s for ~1k-token image prompts.
- **Thinking's cost is all decode.** Instruct answers images in about 0.3 s total. Thinking takes 6.8–13.2 s at the median and up to 162 s, at a near-constant ~43 tokens/s. The tail is set by completion length (p90 1.5k–2.4k tokens; max ~6.9k).
- **Thinking buys no image accuracy.** On the same questions, StudyD9 found Thinking ≈ Instruct (pooled +0.5 pp [−2.6, +3.8]). So on images the Thinking tier costs roughly 20–45× the median latency for no measured gain.

## Results consistency check

| # | check | result |
|---|---|---|
| 1 | Cross-check | **PASS (within 2×).** S-EMBER TTFT 3.91 s at a median of 12,611 prompt tokens vs StudyClean H5 32B N = 37: 3.01 s at 12,420 tokens (same vLLM stack, GPU 1). Ratio 1.30×. The inputs differ (one 1 fps video at R1's sizes vs 37 separate 560×560 images); the gap is reported, not explained. |
| 2 | Plausibility | **PASS.** Prefill ~3.2k tokens/s and decode ~43 tokens/s for 32B bf16 on one H100; cache counters stayed at 0. |
| 3 | Distribution | **PASS.** Spread is reported (p50/p90/max); TTFT varies with prompt length; no constants. |
| 4 | Definitions | **PASS.** TTFT runs from immediately before send to the first streamed token (reasoning or content); total runs to stream close; a runaway is `finish_reason` length or `</think>` not closed. |
| 5 | Claim linkage | Cost side of the device/cloud escalation: the latency of the Thinking cloud tier vs Instruct. |
| 6 | Proxy validity | n/a. |

## Files

| file | contents |
|---|---|
| `experiments/cost/study_d10_latency.py` | runner |
| `experiments/cost/study_d10_analyse.py` | analysis |
| `results/cost/study_d10/study_d10_requests_h100nvl.jsonl` | per-request rows |
| `results/cost/study_d10/study_d10_isolation_h100nvl.jsonl` | isolation checks |
| `results/cost/study_d10/study_d10_snapshots_h100nvl.jsonl` | host snapshots |
| `results/cost/study_d10/study_d10_run_meta_h100nvl.json` | run meta |
| `results/cost/study_d10/study_d10_results_h100nvl.json` | analysis results |
