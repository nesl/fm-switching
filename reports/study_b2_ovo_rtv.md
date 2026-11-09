# StudyB2-ovo-rtv: Qwen3-VL 4B / 8B / 32B, Instruct and Thinking, on OVO-Bench and RTV-Bench

**E-id:** StudyB2-ovo-rtv (pre-registered 2026-11-06 ~14:40, before any B2 inference; authorised by the user).

**Status:** Stage 1 COMPLETE 2026-11-07 10:37: all six arms at 100 % coverage, plus the latency sample. Videos deleted (Stage 2, 180.5 GiB), recorded below.

**Purpose:** collect clean, reanalysable per-question rows for every arm of the matrix while GPU 2 is available.
- **Descriptive only:** no policy, threshold or time-shift claim.
- The latency sample is single-request, localhost, with no network.

## Matrix (written before inference)

| arm | repo @ revision | decoding | source |
|---|---|---|---|
| 4BI | Qwen/Qwen3-VL-4B-Instruct @ `ebb281ec70b05090aa6165b016eac8ec08e71b17` | greedy, max_tokens 64, logprobs top 20, seed 0 | StudyB1 |
| 8BI | Qwen/Qwen3-VL-8B-Instruct @ `0c351dd01ed87e9c1b53cbc748cba10e6187ff3b` | same | StudyB1 |
| 32BI | Qwen/Qwen3-VL-32B-Instruct @ `0cfaf48183f594c314753d30a4c4974bc75f3ccb` | same | **not rerun:** StudyB1 rows (15,486 / 15,486) |
| 4BT | Qwen/Qwen3-VL-4B-Thinking @ `1de27d8c51f12e819435303b9e84c4e25ba8401e` | T 1.0, top_p 0.95, top_k 20, repetition_penalty 1.0, presence_penalty 0.0, max_tokens 16,384, seed 0; whole response saved | model card README, "Generation Hyperparameters", VL section |
| 8BT | Qwen/Qwen3-VL-8B-Thinking @ `92f3c4b4feadd3a016ef468d103bb5f58b2a2c6b` | same | same (identical values) |
| 32BT | Qwen/Qwen3-VL-32B-Thinking @ `7edd10ffd1196091948fb245ff63e406ccb2d4d1` | same | **not rerun:** StudyB1 rows once Stage 0 ends |

- **Card note:** 32B-Thinking's `generation_config.json` has temperature 0.8, while its card's VL section says 1.0. Every request sets the decoding explicitly, so the card value is in effect, as in StudyB1.
- **Stack:** identical to StudyB1.
  - vLLM 0.31.0, FA3, max_model_len 32,768, gpu memory utilisation 0.90, TP 1, bf16, server seed 0.
  - Prefix caching off, `--mm-processor-cache-gb 0`, `--limit-mm-per-prompt {"image": 37, "video": 0}`.
  - Concurrency 8; h100nvl GPU 2.

## Input, templates, parsers and query time (written before inference)
- Exactly StudyB1 (`reports/study_b1_h100.md`): `experiments/benchmarks/b1_common.py` is used **unchanged**.
  - Its SHA-256 must equal `50d3d54d…8b19`.
  - It is verified before the stage and at the start of every GPU step; a mismatch writes `logs/dseries_HALT` and stops the queue.
- RECENT = 9 frames over [max(0, t − 3), t]; HISTORY = 37 frames over [0, t]; LANCZOS 768 × 432 lossless PNG; latest frame with pts ≤ t.
- Query time: OVO `realtime` / `test_info[j].realtime`; RTV `end_time`, **accepted by the user** (2026-11-06).
- The same 100 grey requests per arm and input as StudyB1: the first 50 of each dataset's order.

## Plan and controls (written before inference)
- **Order:**
  - Instruct arms first (4BI, then 8BI), then Thinking (4BT, then 8BT).
  - Each arm runs batches of 200 alternating RECENT (OVO forward, OVO other, RTV) then HISTORY (same), each part in the fixed seed-0 task-stratified order. Any stopping point is therefore a near-proportional sample.
  - The 100 grey requests per input run after the first full cycle.
- **Smoke before each new arm** (Step 3 traces):
  - 3 main requests per input × part, plus 2 grey per input; separate rows files `b2_smoke_<arm>.jsonl.gz`.
  - A smoke failure halts the queue.
- **Repeat control (Step 4 negative control, a gate):**
  - 4BI runs StudyB1's 1,200 bridge requests (plus its 200 grey) first, in StudyB1's bridge order.
  - Its predicted answers (strict-parser answer and status) are compared with StudyB1's 4BI rows.
  - Below **99 %** agreement on the 1,200, or any frame-hash difference, halts the queue before the rest of 4BI.
- **Frame identity:** every B2 row's frame SHA-256 list is compared online with StudyB1's 32BI row for the same (item, input, grey). Any difference halts the queue.
- **Stop rules:**
  - A foreign process on GPU 2 stops everything (watchdog). `b2_supervisor.sh` resumes once GPU 2 has been free for 5 minutes.
  - More than 1 % of an arm's requests still failed after up to 2 transport retries stops that arm (recorded), and the rest continue.
  - A server-log error stops that arm.
  - No requests are dropped or filtered.
- **Latency sample:**
  - Runs after the matrix, with nothing else of ours running.
  - StudyD10's method: per arm × sub-dataset (OVO, RTV) × input, the first 50 questions of the fixed order, one at a time, streaming, cold (prefix caching and the mm cache off, counters checked).
  - The first request per load is discarded and logged. Neighbour GPU steps are flagged, not dropped.
  - Reported: TTFT, total, prompt and completion tokens, GPU 2 SM clock.

## Mechanism verification (Steps 1, 2 and 5 written before inference; Steps 3 and 4 filled from the smoke steps and the repeat control before each arm's sweep)
**Step 1: causal chain.**
- The claim: on identical causal input, model size (4B / 8B / 32B) and reasoning mode (Instruct / Thinking) change per-question correctness.
- Link to FORMULATION.md §Regime uncertainty / §Decisions: the system chooses which capability tier to provision for a query. That choice matters only if tiers answer the same query differently.
- The chain:
  1. The same frames (identical SHA-256) and the same prompt reach every arm.
  2. The arms differ only in weights (size) or in reasoning mode and its decoding.
  3. The generated answer differs.
  4. The upstream (and strict) parser scores it differently.
  5. Per-question correctness differs.

**Step 2: instantiate each link** (values filled from the rows).

| causal link | implementing quantity | value / range in this run | varies as expected? | evidence |
|---|---|---|---|---|
| identical input across arms | frame SHA-256 list per (item, input, grey) vs StudyB1 32BI; prompt tokens | 0 mismatches in 15 pairs × 15,286; prompt tokens equal within a mode, +2 Thinking | CONSTANT, as required | online check + analysis |
| arm differs | served model / revision; decoding | 6 arms, revisions above | yes, by construction | run meta |
| reasoning mode active | Thinking completion tokens; `</think>` closed | p50 135–214, p90 687–2,650, max 16,384; not closed on 4 / 4 / 6 of 15,286 | > 0 and varies: yes | rows |
| answer differs | per-question disagreement between arms on matched items | correctness 12–24 %, answers 19–37 % | > 0 / 1,200 repeat control: yes | rows |
| correctness differs | matched correctness difference (both scorers) | size +0.015 to +0.071 (32B vs 4B / 8B); mode −0.022 to +0.026 (upstream) | — | analysis |

**Step 3: trace one request per new arm** (`b2_smoke_<arm>.jsonl.gz`, recorded 2026-11-06 19:29–19:37, before any sweep).

The same request as StudyB1's trace: RTV `rtv_2420_q-group-jigunncp6-2-option0` (Object-SP), video `embodied_perspective/EmbodiedPerspective_082.mp4`, t = `end_time` = 55.43 s, RECENT. "How many cups/bowls are currently cleaned and placed in the basin?", A. 4 / B. 5 / C. 6 / D. 7, ground truth A.
- **Frames:** targets 52.430 … 55.430 (9 over [52.43, 55.43]).
  - Selected pts: 52.400, 52.800, 53.167, 53.533, 53.900, 54.300, 54.667, 55.033, 55.400, all ≤ t.
  - Frame SHA-256: `0425ab27f5b53d09…`, `4e9f244e301b11c9…`, …
  - **Identical in all four new arms and equal to StudyB1's 32BI row** (online frame check: 22 / 22 smoke requests per arm match).

| arm | prompt / completion tokens | finish | response (answer region) | upstream | strict |
|---|---|---|---|---|---|
| 4BI | 3,118 / 5 | stop | "A. 4" (first-token top 3: A −0.02, B −4.27, C −5.52) | correct | A (ok) |
| 8BI | 3,118 / 2 | stop | "A" (A −0.09, B −2.84, C −4.09) | correct | A (ok) |
| 4BT | 3,120 / 327 | stop, `</think>` closed | "…the dish rack has 4 items … So the answer is A.\n</think>\n\nA" → "A" | correct | A (ok) |
| 8BT | 3,120 / 1,054 | stop, `</think>` closed | "…Yes, that's five. So the answer is B.5.\n</think>\n\nB" → "B" | wrong | B (ok) |
| (StudyB1 32BI) | 3,118 / 5 | stop | "A. 4" | correct | A (ok) |

- **All 22 smoke requests per arm** (3 per input × part plus 2 grey per input) completed with finish `stop` and 0 errors.
- **Prompt tokens:**
  - Instruct: 3,106–3,124+ (RECENT) and 12,571–12,658 (HISTORY), the same as StudyB1.
  - Thinking: +2 on each (the template's generation prefix).
- **Thinking completion tokens:** 49–4,934 (4BT) and 52–3,969 (8BT). `</think>` closed on every smoke request.
- **Per-question answers differ across arms** on identical input (8BT answers B here), which is the quantity the study records.

**Step 4: negative control.**
- The arm difference is disabled by running **the same arm twice on identical input**: 4BI on StudyB1's 1,200 bridge requests.
- Per-question answer disagreement must collapse to about 0; the gate is ≥ 99 % agreement.
- Grey frames must fall to about the guessing floor.

**Step 4 result (recorded 2026-11-06 19:46, before the rest of 4BI; `b2_repeat_control_4BI.json`):**
- **Main requests:** 4BI on StudyB1's 1,200 bridge requests, run again ~24 h later on a fresh server load.
  - **1,200 / 1,200 identical predicted answers** (strict answer and status; agreement 1.000 ≥ 0.99 gate).
  - 1,200 / 1,200 identical upstream correctness and 1,200 / 1,200 identical frame SHA-256 lists.
  - 1,198 / 1,200 identical response texts. The 2 that differ have the same letter with or without the option text: "C" vs "C. In the back of a Buddha statue." (OVO 644, RECENT); "A. Woman" vs "A" (RTV 0959, RECENT).
- **Grey:** 200 / 200 identical answers; 198 / 200 identical texts, again letter vs letter plus option text.
- **PASS:** with the arm difference disabled, per-question answer disagreement is 0 / 1,200, so between-arm disagreement in the sweep is attributable to the arm. Greedy decoding under concurrency 8 is not byte-deterministic (2 / 1,200 texts differ in form), and no answer changed.

**Step 5: alternative explanations.**
- **Format compliance or truncation:** a size or mode difference could come from answer-format compliance or truncation rather than capability.
  - Thinking may not close `</think>` within 16k tokens.
  - A small model may phrase answers the upstream parser misses.
  - Distinguishing data: truncated, empty and unparsed rates per arm; accuracy on parsed-only items; the strict-parser ambiguity counts; both scorers for every comparison.
- **Confounded by design:** reasoning mode and decoding (sampled vs greedy) cannot be separated, as in StudyB1.
- **Seed noise:** Thinking samples with seed 0 only, so per-question Thinking answers carry sampling noise. No Thinking repeat control is run, so this noise is not separated from the mode difference at the per-question level.

## Run record (written after the run)
- **Host / GPU:** h100nvl GPU 2.
  - Stack identical to StudyB1: vLLM 0.31.0, FlashAttention 3, prefix caching off, mm processor cache off, image limit 37, concurrency 8.
  - `b1_common.py` SHA-256 verified at every GPU step: `50d3d54d…8b19`, unchanged.
- **Timeline (2026-11-06 → 07):**

  | step | start | end | requests |
  |---|---|---|---|
  | smoke 4BI / 8BI / 4BT / 8BT | 19:29:45 | 19:37:57 | 22 each, 0 errors |
  | 4BI (bridge repeat control first) | 19:37:58 | 21:01:13 | 15,486 |
  | 8BI | 21:01:14 | 23:05:16 | 15,486 |
  | 4BT | 23:05:17 | 03:09:03 | 15,486 |
  | 8BT | 03:09:04 | 08:17:52 | 15,486 |
  | latency sample (attempt 1) | 08:17:53 | 08:25:05 | 0. Failed on a meta-logging bug in `b2_latency.py` (`revision` passed twice) before any request; fixed and rerun |
  | latency sample | 08:49:50 | 10:37:04 | 1,200 + 6 discarded warm-ups |

- **Errors:** 0 request errors and 0 still-failed requests in every arm. 0 server-log errors.
- **Stops:** no foreign process on GPU 2 and no HALT. Disk stayed at 37 GiB free.
- **Online frame check:** 15,486 / 15,486 rows per new arm matched StudyB1's 32BI frame SHA-256 list.
- **Not rerun:** 32BI and 32BT come from StudyB1, both at 15,486 / 15,486.

### Coverage

| arm | source | main | grey | coverage |
|---|---|---|---|---|
| 4BI | StudyB2 | 15,286 / 15,286 | 200 / 200 | 100 % |
| 8BI | StudyB2 | 15,286 / 15,286 | 200 / 200 | 100 % |
| 32BI | StudyB1 | 15,286 / 15,286 | 200 / 200 | 100 % |
| 4BT | StudyB2 | 15,286 / 15,286 | 200 / 200 | 100 % |
| 8BT | StudyB2 | 15,286 / 15,286 | 200 / 200 | 100 % |
| 32BT | StudyB1 | 15,286 / 15,286 | 200 / 200 | 100 % |

## Observations (written after the run; no interpretation in this section)

### Identity of input across arms (Step 2, link 1)
- **Frames:** frame SHA-256 lists are identical on every matched (item, input) for all 15 arm pairs (15,286 compared per pair; 0 mismatches).
- **Prompt tokens:**
  - equal within a mode;
  - Thinking = Instruct + 2 on every request: the Thinking chat template's generation prefix, the same in all three sizes.

**Input, stack and decoding for the comparisons below:**
- Input is identical.
- Stack is identical (same host, GPU, vLLM and flags).
- Decoding differs only between modes: greedy with 64 tokens vs sampled with up to 16,384, seed 0.

### Accuracy (upstream scorer [video-bootstrap 95 % CI]; strict scorer below)
- "floor" = mean 1 / options over items with a floor. The OVO forward floor excludes REC (open count).
- Unparsed, empty and truncated answers count as wrong.

| cell | floor | 4BI | 8BI | 32BI | 4BT | 8BT | 32BT |
|---|---|---|---|---|---|---|---|
| ovo_bench/RECENT | 0.35 | 0.553 [0.52, 0.59] | 0.556 [0.52, 0.59] | 0.577 [0.54, 0.61] | 0.574 [0.54, 0.61] | 0.581 [0.55, 0.61] | 0.604 [0.57, 0.64] |
| ovo_bench/HISTORY | 0.35 | 0.571 [0.54, 0.60] | 0.579 [0.55, 0.61] | 0.629 [0.60, 0.66] | 0.567 [0.54, 0.60] | 0.575 [0.55, 0.60] | 0.638 [0.61, 0.67] |
| ovo_bench:ovo_forward/RECENT | 0.50 | 0.410 [0.36, 0.46] | 0.416 [0.37, 0.46] | 0.412 [0.36, 0.46] | 0.446 [0.39, 0.50] | 0.461 [0.41, 0.51] | 0.456 [0.40, 0.51] |
| ovo_bench:ovo_forward/HISTORY | 0.50 | 0.489 [0.45, 0.53] | 0.522 [0.48, 0.56] | 0.555 [0.51, 0.60] | 0.512 [0.46, 0.56] | 0.535 [0.49, 0.58] | 0.593 [0.54, 0.64] |
| ovo_bench:ovo_other/RECENT | 0.26 | 0.705 [0.68, 0.73] | 0.705 [0.67, 0.74] | 0.754 [0.73, 0.78] | 0.710 [0.68, 0.74] | 0.708 [0.68, 0.74] | 0.762 [0.74, 0.79] |
| ovo_bench:ovo_other/HISTORY | 0.26 | 0.658 [0.63, 0.69] | 0.640 [0.61, 0.67] | 0.708 [0.68, 0.73] | 0.626 [0.60, 0.65] | 0.617 [0.59, 0.65] | 0.687 [0.66, 0.71] |
| rtv_bench/RECENT | 0.30 | 0.654 [0.64, 0.67] | 0.672 [0.66, 0.69] | 0.687 [0.67, 0.70] | 0.646 [0.63, 0.66] | 0.650 [0.63, 0.67] | 0.684 [0.67, 0.70] |
| rtv_bench/HISTORY | 0.30 | 0.585 [0.57, 0.60] | 0.564 [0.55, 0.58] | 0.600 [0.59, 0.62] | 0.569 [0.56, 0.58] | 0.557 [0.54, 0.57] | 0.610 [0.60, 0.63] |

Strict scorer:

| cell | 4BI | 8BI | 32BI | 4BT | 8BT | 32BT |
|---|---|---|---|---|---|---|
| ovo_bench/RECENT | 0.534 | 0.555 | 0.561 | 0.574 | 0.580 | 0.603 |
| ovo_bench/HISTORY | 0.551 | 0.579 | 0.610 | 0.567 | 0.575 | 0.638 |
| ovo_bench:ovo_forward/RECENT | 0.410 | 0.416 | 0.412 | 0.446 | 0.461 | 0.456 |
| ovo_bench:ovo_forward/HISTORY | 0.489 | 0.522 | 0.555 | 0.512 | 0.535 | 0.593 |
| ovo_bench:ovo_other/RECENT | 0.666 | 0.703 | 0.721 | 0.710 | 0.707 | 0.761 |
| ovo_bench:ovo_other/HISTORY | 0.616 | 0.640 | 0.668 | 0.625 | 0.616 | 0.686 |
| rtv_bench/RECENT | 0.653 | 0.672 | 0.686 | 0.646 | 0.650 | 0.683 |
| rtv_bench/HISTORY | 0.584 | 0.564 | 0.599 | 0.569 | 0.556 | 0.609 |

- **Spread across the 36 tasks (min–max upstream accuracy):**
  - 4BI 0.18–0.96; 8BI 0.20–0.95; 32BI 0.17–0.97; 4BT 0.19–0.95; 8BT 0.22–0.94; 32BT 0.20–0.95.
  - In every arm the minimum is OVO REC under RECENT and the maximum is OVO OCR under RECENT.
  - Per-task rows are in the appendix.

### Truncation, unparsed answers and generated tokens (main questions)

| arm | cell | n | truncated | unparsed | ambiguous | empty | no answer region | parsed-only acc | completion tokens p50 / p90 / max |
|---|---|---|---|---|---|---|---|---|---|
| 4BI | ovo_bench/RECENT | 3035 | 2 | 70 | 68 | 0 | 0 | 0.547 | 2 / 11 / 64 |
| 4BI | ovo_bench/HISTORY | 3035 | 1 | 71 | 69 | 0 | 0 | 0.565 | 2 / 12 / 64 |
| 4BI | rtv_bench/RECENT | 4608 | 0 | 5 | 5 | 0 | 0 | 0.654 | 5 / 7 / 19 |
| 4BI | rtv_bench/HISTORY | 4608 | 0 | 7 | 5 | 0 | 0 | 0.585 | 5 / 7 / 17 |
| 8BI | ovo_bench/RECENT | 3035 | 0 | 4 | 2 | 0 | 0 | 0.556 | 2 / 2 / 17 |
| 8BI | ovo_bench/HISTORY | 3035 | 0 | 2 | 0 | 0 | 0 | 0.580 | 2 / 2 / 23 |
| 8BI | rtv_bench/RECENT | 4608 | 0 | 2 | 2 | 0 | 0 | 0.672 | 2 / 2 / 10 |
| 8BI | rtv_bench/HISTORY | 4608 | 0 | 2 | 2 | 0 | 0 | 0.564 | 2 / 2 / 14 |
| 32BI | ovo_bench/RECENT | 3035 | 6 | 57 | 52 | 0 | 0 | 0.573 | 2 / 7 / 64 |
| 32BI | ovo_bench/HISTORY | 3035 | 1 | 68 | 66 | 0 | 0 | 0.625 | 2 / 10 / 64 |
| 32BI | rtv_bench/RECENT | 4608 | 9 | 13 | 8 | 0 | 0 | 0.688 | 2 / 6 / 64 |
| 32BI | rtv_bench/HISTORY | 4608 | 3 | 12 | 10 | 0 | 0 | 0.601 | 2 / 6 / 64 |
| 4BT | ovo_bench/RECENT | 3035 | 0 | 0 | 0 | 0 | 0 | 0.574 | 187 / 1620 / 7716 |
| 4BT | ovo_bench/HISTORY | 3035 | 1 | 2 | 2 | 0 | 0 | 0.567 | 204 / 2650 / 16384 |
| 4BT | rtv_bench/RECENT | 4608 | 0 | 8 | 3 | 0 | 0 | 0.647 | 190 / 1186 / 5304 |
| 4BT | rtv_bench/HISTORY | 4608 | 3 | 11 | 5 | 0 | 3 | 0.570 | 171 / 920 / 16384 |
| 8BT | ovo_bench/RECENT | 3035 | 0 | 2 | 2 | 0 | 0 | 0.580 | 154 / 1258 / 9321 |
| 8BT | ovo_bench/HISTORY | 3035 | 1 | 2 | 1 | 0 | 0 | 0.575 | 160 / 2332 / 16384 |
| 8BT | rtv_bench/RECENT | 4608 | 0 | 6 | 2 | 0 | 0 | 0.650 | 157 / 1165 / 9953 |
| 8BT | rtv_bench/HISTORY | 4608 | 3 | 9 | 4 | 0 | 3 | 0.557 | 150 / 923 / 16384 |
| 32BT | ovo_bench/RECENT | 3035 | 0 | 1 | 1 | 0 | 0 | 0.603 | 135 / 729 / 4802 |
| 32BT | ovo_bench/HISTORY | 3035 | 3 | 4 | 1 | 0 | 3 | 0.639 | 145 / 1407 / 16384 |
| 32BT | rtv_bench/RECENT | 4608 | 0 | 16 | 13 | 0 | 0 | 0.685 | 139 / 745 / 6040 |
| 32BT | rtv_bench/HISTORY | 4608 | 3 | 17 | 9 | 0 | 3 | 0.611 | 160 / 687 / 16384 |

- **Instruct truncation:** the 64-token cap; at most 9 per cell.
- **Thinking truncation:** the 16,384-token cap. 4BT 4, 8BT 4, 32BT 6 of 15,286, all under HISTORY.
- **Thinking completion lengths:** p50 135–214 tokens per cell; p90 687–2,650.
- **4BI has 68–69 ambiguous OVO answers per input:** the response contains more than one option letter. Under OVO's substring scorer these can score correct, which is why 4BI's upstream accuracy exceeds its strict accuracy on OVO (by 0.019–0.039 in the OVO cells).
- **8BI almost always answers with a single letter:** p90 of 2 tokens, 0–4 unparsed per cell.

### Paired comparisons (matched questions; video bootstrap, 2,000 resamples, seed 0; both scorers)

| comparison | n | n videos | upstream diff [video CI] | strict diff [video CI] | correctness disagree | answer disagree |
|---|---|---|---|---|---|---|
| 4BI/ovo_bench/HISTORY-RECENT | 3035 | 644 | +0.018 [-0.005, +0.041] | +0.016 [-0.006, +0.038] | 0.248 | 0.383 |
| 4BI/rtv_bench/HISTORY-RECENT | 4608 | 552 | -0.069 [-0.083, -0.057] | -0.069 [-0.082, -0.056] | 0.213 | 0.269 |
| 8BI/ovo_bench/HISTORY-RECENT | 3035 | 644 | +0.023 [+0.001, +0.045] | +0.024 [+0.003, +0.047] | 0.257 | 0.386 |
| 8BI/rtv_bench/HISTORY-RECENT | 4608 | 552 | -0.107 [-0.121, -0.094] | -0.107 [-0.122, -0.094] | 0.229 | 0.290 |
| 32BI/ovo_bench/HISTORY-RECENT | 3035 | 644 | +0.051 [+0.029, +0.074] | +0.048 [+0.025, +0.071] | 0.244 | 0.361 |
| 32BI/rtv_bench/HISTORY-RECENT | 4608 | 552 | -0.087 [-0.102, -0.072] | -0.087 [-0.101, -0.072] | 0.227 | 0.287 |
| 4BT/ovo_bench/HISTORY-RECENT | 3035 | 644 | -0.006 [-0.028, +0.015] | -0.007 [-0.031, +0.016] | 0.261 | 0.410 |
| 4BT/rtv_bench/HISTORY-RECENT | 4608 | 552 | -0.077 [-0.091, -0.063] | -0.077 [-0.092, -0.062] | 0.245 | 0.312 |
| 8BT/ovo_bench/HISTORY-RECENT | 3035 | 644 | -0.006 [-0.029, +0.016] | -0.005 [-0.031, +0.019] | 0.266 | 0.406 |
| 8BT/rtv_bench/HISTORY-RECENT | 4608 | 552 | -0.093 [-0.107, -0.079] | -0.093 [-0.106, -0.079] | 0.250 | 0.319 |
| 32BT/ovo_bench/HISTORY-RECENT | 3035 | 644 | +0.035 [+0.009, +0.061] | +0.035 [+0.010, +0.060] | 0.263 | 0.377 |
| 32BT/rtv_bench/HISTORY-RECENT | 4608 | 552 | -0.074 [-0.090, -0.060] | -0.074 [-0.089, -0.060] | 0.232 | 0.291 |
| 32BI-4BI/ovo_bench/RECENT | 3035 | 644 | +0.024 [+0.010, +0.040] | +0.027 [+0.012, +0.043] | 0.147 | 0.215 |
| 32BI-4BI/ovo_bench/HISTORY | 3035 | 644 | +0.058 [+0.040, +0.077] | +0.059 [+0.040, +0.077] | 0.216 | 0.304 |
| 32BI-4BI/rtv_bench/RECENT | 4608 | 552 | +0.033 [+0.021, +0.045] | +0.033 [+0.021, +0.045] | 0.185 | 0.235 |
| 32BI-4BI/rtv_bench/HISTORY | 4608 | 552 | +0.015 [+0.003, +0.027] | +0.015 [+0.002, +0.027] | 0.219 | 0.283 |
| 32BI-8BI/ovo_bench/RECENT | 3035 | 644 | +0.021 [+0.007, +0.036] | +0.007 [-0.007, +0.022] | 0.132 | 0.200 |
| 32BI-8BI/ovo_bench/HISTORY | 3035 | 644 | +0.049 [+0.031, +0.069] | +0.030 [+0.011, +0.051] | 0.206 | 0.302 |
| 32BI-8BI/rtv_bench/RECENT | 4608 | 552 | +0.015 [+0.005, +0.027] | +0.014 [+0.003, +0.026] | 0.157 | 0.201 |
| 32BI-8BI/rtv_bench/HISTORY | 4608 | 552 | +0.036 [+0.024, +0.048] | +0.035 [+0.023, +0.046] | 0.187 | 0.249 |
| 8BI-4BI/ovo_bench/RECENT | 3035 | 644 | +0.003 [-0.010, +0.017] | +0.021 [+0.007, +0.035] | 0.124 | 0.194 |
| 8BI-4BI/ovo_bench/HISTORY | 3035 | 644 | +0.009 [-0.008, +0.025] | +0.029 [+0.013, +0.045] | 0.185 | 0.285 |
| 8BI-4BI/rtv_bench/RECENT | 4608 | 552 | +0.018 [+0.007, +0.028] | +0.018 [+0.007, +0.029] | 0.166 | 0.217 |
| 8BI-4BI/rtv_bench/HISTORY | 4608 | 552 | -0.020 [-0.032, -0.008] | -0.020 [-0.032, -0.008] | 0.192 | 0.260 |
| 32BT-4BT/ovo_bench/RECENT | 3035 | 644 | +0.030 [+0.015, +0.046] | +0.030 [+0.016, +0.045] | 0.141 | 0.221 |
| 32BT-4BT/ovo_bench/HISTORY | 3035 | 644 | +0.071 [+0.054, +0.088] | +0.071 [+0.053, +0.089] | 0.204 | 0.318 |
| 32BT-4BT/rtv_bench/RECENT | 4608 | 552 | +0.038 [+0.026, +0.049] | +0.037 [+0.026, +0.049] | 0.172 | 0.219 |
| 32BT-4BT/rtv_bench/HISTORY | 4608 | 552 | +0.041 [+0.028, +0.053] | +0.040 [+0.027, +0.052] | 0.199 | 0.264 |
| 32BT-8BT/ovo_bench/RECENT | 3035 | 644 | +0.023 [+0.009, +0.037] | +0.023 [+0.009, +0.038] | 0.134 | 0.204 |
| 32BT-8BT/ovo_bench/HISTORY | 3035 | 644 | +0.063 [+0.048, +0.080] | +0.063 [+0.047, +0.080] | 0.194 | 0.297 |
| 32BT-8BT/rtv_bench/RECENT | 4608 | 552 | +0.034 [+0.023, +0.045] | +0.033 [+0.023, +0.044] | 0.171 | 0.216 |
| 32BT-8BT/rtv_bench/HISTORY | 4608 | 552 | +0.054 [+0.043, +0.065] | +0.053 [+0.041, +0.064] | 0.196 | 0.257 |
| 8BT-4BT/ovo_bench/RECENT | 3035 | 644 | +0.007 [-0.007, +0.019] | +0.006 [-0.006, +0.020] | 0.127 | 0.197 |
| 8BT-4BT/ovo_bench/HISTORY | 3035 | 644 | +0.008 [-0.008, +0.024] | +0.008 [-0.008, +0.024] | 0.182 | 0.314 |
| 8BT-4BT/rtv_bench/RECENT | 4608 | 552 | +0.003 [-0.008, +0.014] | +0.004 [-0.008, +0.015] | 0.153 | 0.200 |
| 8BT-4BT/rtv_bench/HISTORY | 4608 | 552 | -0.013 [-0.024, -0.000] | -0.013 [-0.024, -0.001] | 0.186 | 0.251 |
| 4BT-4BI/ovo_bench/RECENT | 3035 | 644 | +0.021 [+0.005, +0.038] | +0.040 [+0.023, +0.056] | 0.166 | 0.261 |
| 4BT-4BI/ovo_bench/HISTORY | 3035 | 644 | -0.003 [-0.023, +0.016] | +0.016 [-0.002, +0.036] | 0.235 | 0.370 |
| 4BT-4BI/rtv_bench/RECENT | 4608 | 552 | -0.008 [-0.019, +0.003] | -0.008 [-0.020, +0.003] | 0.176 | 0.231 |
| 4BT-4BI/rtv_bench/HISTORY | 4608 | 552 | -0.015 [-0.029, -0.002] | -0.015 [-0.028, -0.002] | 0.198 | 0.265 |
| 8BT-8BI/ovo_bench/RECENT | 3035 | 644 | +0.025 [+0.011, +0.039] | +0.025 [+0.011, +0.039] | 0.164 | 0.233 |
| 8BT-8BI/ovo_bench/HISTORY | 3035 | 644 | -0.004 [-0.021, +0.013] | -0.005 [-0.022, +0.013] | 0.225 | 0.339 |
| 8BT-8BI/rtv_bench/RECENT | 4608 | 552 | -0.022 [-0.033, -0.010] | -0.022 [-0.033, -0.011] | 0.165 | 0.209 |
| 8BT-8BI/rtv_bench/HISTORY | 4608 | 552 | -0.008 [-0.018, +0.003] | -0.008 [-0.019, +0.003] | 0.192 | 0.259 |
| 32BT-32BI/ovo_bench/RECENT | 3035 | 644 | +0.026 [+0.013, +0.039] | +0.042 [+0.029, +0.055] | 0.132 | 0.202 |
| 32BT-32BI/ovo_bench/HISTORY | 3035 | 644 | +0.010 [-0.009, +0.027] | +0.028 [+0.009, +0.048] | 0.189 | 0.292 |
| 32BT-32BI/rtv_bench/RECENT | 4608 | 552 | -0.003 [-0.014, +0.008] | -0.003 [-0.014, +0.008] | 0.150 | 0.186 |
| 32BT-32BI/rtv_bench/HISTORY | 4608 | 552 | +0.010 [-0.001, +0.022] | +0.010 [-0.002, +0.021] | 0.166 | 0.218 |

**Size: 32B − 4B and 32B − 8B (same mode):**
- Positive in all 16 cells under the upstream scorer:
  - Instruct +0.015 to +0.058;
  - Thinking +0.023 to +0.071.
- The CI excludes 0 in all 16 cells under the upstream scorer and in 15 of 16 under strict. The exception is 32BI − 8BI on OVO RECENT under strict: +0.007 [−0.007, +0.022].
- The largest gaps are on OVO HISTORY (+0.049 to +0.071).

**8B − 4B:**
- Within ±0.03 in every cell.
- Instruct OVO depends on the scorer: upstream +0.003 / +0.009 vs strict +0.021 / +0.029 (4BI's ambiguous answers above).
- On RTV HISTORY it is negative in both modes: Instruct −0.020 [−0.032, −0.008]; Thinking −0.013 [−0.024, −0.000].

**Thinking − Instruct, per size (upstream):**
- 4B: −0.015 to +0.021.
- 8B: −0.022 to +0.025.
- 32B: −0.003 to +0.026.
- The largest positive difference in every size is on OVO RECENT (+0.021, +0.025, +0.026). Under strict it is +0.040, +0.025, +0.042: the Instruct arms' ambiguous answers are penalised by strict.
- RTV is −0.022 to +0.010.
- Per-question correctness disagreement is 13–24 %, against 0 / 1,200 in the repeat control.

**HISTORY − RECENT** (a comparison of inputs: 37 frames over [0, t] vs 9 over the last 3 s, ≈ 12.6k vs 3.1k prompt tokens):
- RTV is negative in all six arms: −0.069 to −0.107, every CI excluding 0.
- OVO is positive for the three Instruct arms (+0.018 to +0.051) and for 32BT (+0.035).
- OVO is ≈ 0 for 4BT and 8BT (−0.006 each, CIs including 0).

### Grey-frame control (the same 100 questions per arm × input: first 50 of each dataset's order; pixels grey, question and options real)

| arm/input | n | upstream acc | strict acc | floor | answers | unparsed | truncated |
|---|---|---|---|---|---|---|---|
| 4BI/RECENT | 100 | 0.34 | 0.34 | 0.32 | {'A': 35, 'No': 15, 'B': 15, 'D': 13, '0': 11, 'C': 11} | 0 | 0 |
| 4BI/HISTORY | 100 | 0.36 | 0.36 | 0.32 | {'A': 35, 'B': 17, 'No': 15, 'C': 12, '0': 11, 'D': 10} | 0 | 0 |
| 8BI/RECENT | 100 | 0.26 | 0.26 | 0.32 | {'A': 21, 'B': 21, 'C': 17, 'No': 15, 'D': 14, '0': 11, 'None': 1} | 1 | 0 |
| 8BI/HISTORY | 100 | 0.32 | 0.32 | 0.32 | {'B': 28, 'A': 20, 'C': 17, 'No': 15, '0': 11, 'D': 9} | 0 | 0 |
| 32BI/RECENT | 100 | 0.37 | 0.36 | 0.32 | {'A': 33, 'B': 17, 'No': 15, 'D': 12, '0': 11, 'C': 11, 'None': 1} | 1 | 1 |
| 32BI/HISTORY | 100 | 0.39 | 0.38 | 0.32 | {'A': 27, 'B': 20, 'No': 15, 'D': 15, '0': 11, 'C': 11, 'None': 1} | 1 | 1 |
| 4BT/RECENT | 100 | 0.32 | 0.32 | 0.32 | {'B': 25, 'A': 20, 'D': 17, 'No': 15, 'C': 12, '0': 11} | 0 | 0 |
| 4BT/HISTORY | 100 | 0.26 | 0.26 | 0.32 | {'B': 25, 'A': 20, 'D': 17, 'No': 15, 'C': 12, '0': 11} | 0 | 0 |
| 8BT/RECENT | 100 | 0.32 | 0.32 | 0.32 | {'B': 25, 'D': 19, 'No': 15, 'A': 15, 'C': 13, '0': 11, 'None': 2} | 2 | 0 |
| 8BT/HISTORY | 100 | 0.37 | 0.36 | 0.32 | {'B': 26, 'A': 21, 'D': 16, 'No': 15, '0': 11, 'C': 10, 'None': 1} | 1 | 1 |
| 32BT/RECENT | 100 | 0.35 | 0.34 | 0.32 | {'A': 27, 'B': 20, 'D': 17, 'No': 15, '0': 11, 'C': 9, 'None': 1} | 1 | 0 |
| 32BT/HISTORY | 100 | 0.31 | 0.31 | 0.32 | {'A': 24, 'B': 20, 'D': 17, 'No': 15, 'C': 13, '0': 11} | 0 | 0 |

- **Grey accuracy vs floor:** 0.26–0.39 against a floor of 0.32.
- **Below the floor:** two cells are at 0.26 (8BI RECENT, 4BT HISTORY; n = 100 each).
- **Above the floor:** the highest is 32BI HISTORY at 0.39.
- **Answers:** every arm answers "No" to the 15 SSR / CRR items and "0" to the 11 REC items. The multiple-choice letters lean to A or B, depending on the arm.

### Latency sample (StudyD10 method)
- One request at a time, streaming.
- Cold: prefix caching and mm processor cache off; cache-hit counters unchanged across every load; `cached_tokens` = 0 on every request.
- The first request after each load was discarded.
- Localhost (127.0.0.1), **no network**.
- Isolation: 236 checks, none saw other work of ours, so **not VOID**.
- Neighbour GPUs ran another user's vLLM throughout (GPUs 0, 1, 3); no request coincided with a ≥ 50-point utilisation step.

Warm-ups discarded: 6; isolation VOID = False (236 checks); cache counters grew: never.

| arm / sub-dataset / input | n | TTFT p50 / p90 / max (s) | total p50 / p90 / max (s) | prompt tok p50 | completion tok p50 / max | GPU-2 SM MHz median (p50 of requests) | neighbour-flagged | truncated |
|---|---|---|---|---|---|---|---|---|
| 32BI/ovo_bench/HISTORY | 50 | 2.99 / 3.03 / 3.05 | 3.03 / 3.20 / 3.29 | 12605 | 2 / 14 | 990 | 0 | 0 |
| 32BI/ovo_bench/RECENT | 50 | 0.63 / 0.66 / 0.79 | 0.66 / 0.82 / 0.94 | 3140 | 2 / 14 | 1035 | 0 | 0 |
| 32BI/rtv_bench/HISTORY | 50 | 3.02 / 3.05 / 3.07 | 3.07 / 3.17 / 3.26 | 12579 | 2 / 10 | 945 | 0 | 0 |
| 32BI/rtv_bench/RECENT | 50 | 0.64 / 0.66 / 0.68 | 0.68 / 0.77 / 0.82 | 3114 | 2 / 8 | 1005 | 0 | 0 |
| 32BT/ovo_bench/HISTORY | 50 | 3.03 / 3.08 / 3.17 | 5.99 / 28.87 / 144.99 | 12607 | 123 / 5795 | 1260 | 0 | 0 |
| 32BT/ovo_bench/RECENT | 50 | 0.65 / 0.67 / 0.68 | 3.48 / 13.21 / 39.30 | 3142 | 122 / 1675 | 1290 | 0 | 0 |
| 32BT/rtv_bench/HISTORY | 50 | 3.02 / 3.05 / 3.10 | 7.20 / 13.51 / 39.49 | 12581 | 173 / 1506 | 1275 | 0 | 0 |
| 32BT/rtv_bench/RECENT | 50 | 0.66 / 0.67 / 0.70 | 4.15 / 20.89 / 61.11 | 3116 | 150 / 2594 | 1290 | 0 | 0 |
| 4BI/ovo_bench/HISTORY | 50 | 0.97 / 1.00 / 1.05 | 0.99 / 1.05 / 1.08 | 12605 | 3 / 17 | 1695 | 0 | 0 |
| 4BI/ovo_bench/RECENT | 50 | 0.22 / 0.24 / 0.34 | 0.23 / 0.27 / 0.34 | 3140 | 2 / 17 | 1624 | 0 | 0 |
| 4BI/rtv_bench/HISTORY | 50 | 0.96 / 0.99 / 1.05 | 0.99 / 1.02 / 1.10 | 12579 | 5 / 13 | 1710 | 0 | 0 |
| 4BI/rtv_bench/RECENT | 50 | 0.22 / 0.24 / 0.25 | 0.25 / 0.26 / 0.27 | 3114 | 5 / 10 | 1605 | 0 | 0 |
| 4BT/ovo_bench/HISTORY | 50 | 0.96 / 1.00 / 1.08 | 1.76 / 13.35 / 41.00 | 12607 | 156 / 7870 | 1785 | 0 | 0 |
| 4BT/ovo_bench/RECENT | 50 | 0.23 / 0.25 / 0.27 | 1.06 / 6.06 / 20.29 | 3142 | 184 / 4348 | 1785 | 0 | 0 |
| 4BT/rtv_bench/HISTORY | 50 | 0.95 / 0.99 / 1.03 | 2.00 / 4.83 / 8.28 | 12581 | 214 / 1473 | 1785 | 0 | 0 |
| 4BT/rtv_bench/RECENT | 50 | 0.23 / 0.25 / 0.26 | 1.02 / 5.84 / 13.33 | 3116 | 176 / 2874 | 1785 | 0 | 0 |
| 8BI/ovo_bench/HISTORY | 50 | 1.19 / 1.23 / 1.30 | 1.21 / 1.25 / 1.32 | 12605 | 2 / 12 | 1215 | 0 | 0 |
| 8BI/ovo_bench/RECENT | 50 | 0.29 / 0.30 / 0.34 | 0.29 / 0.31 / 0.37 | 3140 | 2 / 12 | 1365 | 0 | 0 |
| 8BI/rtv_bench/HISTORY | 50 | 1.20 / 1.22 / 1.24 | 1.22 / 1.25 / 1.28 | 12579 | 2 / 7 | 1200 | 0 | 0 |
| 8BI/rtv_bench/RECENT | 50 | 0.28 / 0.29 / 0.30 | 0.29 / 0.30 / 0.32 | 3114 | 2 / 5 | 1448 | 0 | 0 |
| 8BT/ovo_bench/HISTORY | 50 | 1.21 / 1.25 / 1.41 | 2.27 / 15.36 / 61.39 | 12607 | 144 / 8283 | 1440 | 0 | 0 |
| 8BT/ovo_bench/RECENT | 50 | 0.30 / 0.31 / 0.47 | 1.17 / 5.94 / 23.82 | 3142 | 135 / 3589 | 1770 | 0 | 0 |
| 8BT/rtv_bench/HISTORY | 50 | 1.19 / 1.22 / 1.28 | 1.94 / 5.19 / 9.12 | 12581 | 104 / 1127 | 1395 | 0 | 0 |
| 8BT/rtv_bench/RECENT | 50 | 0.29 / 0.31 / 0.32 | 1.13 / 9.22 / 21.14 | 3116 | 128 / 3171 | 1755 | 0 | 0 |

**Latency observations:**
- **TTFT by size** (RECENT / HISTORY, both modes): 4B ≈ 0.22 / 0.96 s; 8B ≈ 0.29 / 1.20 s; 32B ≈ 0.64 / 3.0 s.
- **TTFT does not depend on mode:** Thinking's first streamed token is a reasoning token.
- **Thinking total latency:**
  - p50 1.0–7.2 s;
  - p90 up to 28.9 s;
  - max 145 s (32BT, OVO HISTORY, 5,795 completion tokens).
- **Instruct total latency:** within 0.05–0.25 s of TTFT.
- **GPU-2 SM clock** (median over each request, p50 across requests):
  - 4B arms 1,605–1,785 MHz;
  - 8B arms 1,200–1,770 MHz;
  - 32B arms 945–1,290 MHz.
  - The clock is logged per request (`gpu2`, `sm_mhz_at_send`); its cause (power or thermal management) is not established here.

### Other checks
- **Frames at or before t:** every frame of every request is at or before t (asserted per request and re-checked).
- **Repeat control (Step 4):** 1,200 / 1,200 identical answers (see above).
- **Fewer distinct frames than N:** the same requests in every arm (short videos, low frame rate, or t beyond the video end).
- **Result files:** all under 90 MB (largest 33.2 MB, `b2_rows_4BT.jsonl.gz`). Per-request latency and isolation rows gzipped.

## Results consistency check (6 checks, before the interpretation)
1. **Cross-check against committed measurements.**

   | quantity | this run | prior run | source | ratio | agree? |
   |---|---|---|---|---|---|
   | 4BI answers on the 1,200 bridge requests | identical on 1,200 / 1,200 | StudyB1 4BI | StudyB1 | 1.00 | agree |
   | 32B-I cold TTFT, 9 frames (~3.1k tokens) | 0.64 s | 0.62 s (N = 9) | StudyD4-latency | 1.03 | agree |
   | 4B-I cold TTFT, 9 frames | 0.22 s | 0.23 s (N = 9) | StudyD4-latency | 0.96 | agree |
   | prompt tokens per 768 × 432 frame | ≈ 340 | ≈ 336 | StudyD4-orin / StudyClean | 1.01 | agree |
   | 32B accuracy (32BI / 32BT) | StudyB1 rows reused | — | StudyB1 | — | identical by construction |
   | 4B / 8B on these benchmarks | this table | StudyB1-flash 4B / 8B | flash (A6000, own template and code path) | not compared | stack and template differ; not like-for-like |

   No disagreement > 2× on a like-for-like quantity.
2. **Physical plausibility.**
   - Prefill rates implied by cold TTFT: 32B 12.6k / 3.0 s ≈ 4.2k tokens/s and 3.1k / 0.64 s ≈ 4.9k tokens/s; 8B ≈ 10.5k tokens/s; 4B ≈ 13–14k tokens/s.
   - The 32B values are within the D4 / D7 H100 curves (D7 batch throughput ≈ 4.9–5.3k tokens/s), and nothing is faster than the committed curves. 4B / 8B have no committed H100 prefill curve beyond D4's 4B N = 9 point, which agrees.
   - Sweep wall time: 4BI 1 h 23 m, 8BI 2 h 02 m, 4BT 4 h 04 m, 8BT 5 h 09 m for 15,486 requests at concurrency 8.
3. **Distribution sanity.**
   - Accuracy varies by task (0.17–0.97); completion tokens 1–64 (Instruct) and 1–16,384 (Thinking).
   - Latency spreads are reported as p50 / p90 / max per cell. TTFT is tight within a cell (p90 / p50 ≤ 1.1), as expected for fixed-size cold prefill. No constant appears where a distribution is expected.
4. **Definition audit.**
   - RECENT / HISTORY, query time, scorers and the grey control are exactly as in StudyB1 (same code, same SHA).
   - "RECENT" is also a D-series / StudyClean name with a different window (flagged in StudyB1).
   - TTFT = send → first streamed token (reasoning or content), as in StudyD10.
5. **Claim linkage.**
   - FORMULATION.md §Regime uncertainty / §Decisions.
   - **Supports:** capability tiers (size, mode) answer the same query differently on 12–24 % of matched questions (0 % repeat control), and 32B is more accurate than 4B and 8B in both modes.
   - **Does not speak to:** policy, thresholds or time-shift, by design.
6. **Proxy validity.**
   - RTV `end_time` as the query time is accepted by the user.
   - The upstream OVO multiple-choice scorer is lenient, so both scorers are reported for every comparison. Directions agree; magnitudes differ where an arm gives ambiguous answers (4BI, and 32BI on OVO).

**Outcome:** no check failed. Flags carried: the OVO forward-template deviation (StudyB1), and the SM clock difference by model size (observed, not explained).

## Interpretation
- **Size:**
  - On identical input, 32B is more accurate than both 4B and 8B in both modes, by 1.5–7 pp.
  - The gap is largest with full history on OVO.
  - 8B is not consistently better than 4B on these two benchmarks.
- **Reasoning mode:**
  - Thinking changes per-question correctness substantially (12–24 % of questions flip) but changes accuracy by at most ±2.6 pp (upstream) at any size.
  - It costs about 30–100× the generated tokens (p50 ≈ 135–214 vs 2–5) and several seconds of added latency per request (p50), with a long tail.
  - Mode and sampled decoding are confounded.
- **Inputs:**
  - Full history hurts RTV's current-scene questions in every arm.
  - It helps OVO's forward-active tasks for the Instruct arms and 32BT, but not for 4BT / 8BT.
  - The inputs differ in token budget (≈ 4×), so "more frames" and "older frames" are not separated.
- **Grey control:** near the floor in every arm, so the visual input carries the accuracy above it.

## Stage 2: video deletion (2026-11-07 ~11:25, per the user's DELETION rule)
**Conditions:**
- Every arm and input in the matrix finished (6 × 15,486), plus the latency sample (not VOID).
- Rows were read back by `b2_analyse.py`, and this report section exists.
- `results/datasets/download_manifest_h100.json` records the pinned HF revisions (OVO `fec29e33`, RTV `62ec75f8`), the code commits (`c34093f9`, `a928cbe8`), the file scope and the LFS / per-video sha256. `ovo_bench/tar_listing_h100.txt` is kept.

**Deleted (every path listed first in `results/datasets/deletion_h100_ovo_rtv.json`, with bytes):**

| dataset | files | bytes |
|---|---|---|
| OVO-Bench | 645 mp4 under `ovo_bench/src_videos/src_videos/` + 5 archive parts `ovo_bench/hf/src_videos.tar.parta{a..e}` | 92,682,982,629 |
| RTV-Bench | 552 mp4 under `rtv_bench/hf/videos/` | 101,136,583,137 |
| **total** | **1,202** | **193,819,565,766 (180.5 GiB)** |

- Each path was checked before removal: a regular file (not a symlink), under its dataset directory, an mp4 or an archive part, and the size recorded in the list. 0 errors; no wildcard.
- **Kept:** annotations (`ovo_bench/code/data/ovo_bench_new.json`, `rtv_bench/hf/QA.json`), code clones, HF README / .gitattributes, ffprobe logs, the tar listing and logs.
- **Free disk on the data volume:** 37 GiB before, 217 GiB after.

## Appendix: per-task results (all arms)

| arm | cell | n | floor | upstream [video CI] | strict | trunc | unparsed | tokens p50 / p90 / max |
|---|---|---|---|---|---|---|---|---|
| 4BI | ovo_bench/ACR/HISTORY | 109 | 0.25 | 0.679 [0.57, 0.77] | 0.679 | 0.000 | 0.009 | 10 / 13 / 19 |
| 4BI | ovo_bench/ACR/RECENT | 109 | 0.25 | 0.826 [0.75, 0.89] | 0.826 | 0.000 | 0.009 | 10 / 13 / 18 |
| 4BI | ovo_bench/ASI/HISTORY | 148 | 0.25 | 0.662 [0.59, 0.74] | 0.662 | 0.000 | 0.000 | 7 / 14 / 23 |
| 4BI | ovo_bench/ASI/RECENT | 148 | 0.25 | 0.541 [0.46, 0.61] | 0.541 | 0.000 | 0.000 | 6 / 12 / 22 |
| 4BI | ovo_bench/ATR/HISTORY | 116 | 0.25 | 0.784 [0.68, 0.87] | 0.776 | 0.000 | 0.000 | 7 / 13 / 16 |
| 4BI | ovo_bench/ATR/RECENT | 116 | 0.25 | 0.828 [0.75, 0.90] | 0.810 | 0.000 | 0.009 | 7 / 13 / 17 |
| 4BI | ovo_bench/CRR/HISTORY | 240 | 0.50 | 0.458 [0.42, 0.52] | 0.458 | 0.000 | 0.000 | 2 / 2 / 2 |
| 4BI | ovo_bench/CRR/RECENT | 240 | 0.50 | 0.412 [0.39, 0.44] | 0.412 | 0.000 | 0.000 | 2 / 2 / 2 |
| 4BI | ovo_bench/EPM/HISTORY | 297 | 0.27 | 0.609 [0.55, 0.67] | 0.576 | 0.000 | 0.037 | 6 / 10 / 15 |
| 4BI | ovo_bench/EPM/RECENT | 297 | 0.27 | 0.562 [0.51, 0.62] | 0.549 | 0.003 | 0.030 | 5 / 8 / 64 |
| 4BI | ovo_bench/FPD/HISTORY | 101 | 0.25 | 0.743 [0.64, 0.83] | 0.743 | 0.010 | 0.010 | 13 / 16 / 64 |
| 4BI | ovo_bench/FPD/RECENT | 101 | 0.25 | 0.733 [0.62, 0.83] | 0.733 | 0.010 | 0.000 | 12 / 16 / 64 |
| 4BI | ovo_bench/HLD/HISTORY | 186 | 0.28 | 0.376 [0.30, 0.45] | 0.366 | 0.000 | 0.027 | 6 / 8 / 16 |
| 4BI | ovo_bench/HLD/RECENT | 186 | 0.28 | 0.532 [0.46, 0.61] | 0.522 | 0.000 | 0.027 | 6 / 7 / 11 |
| 4BI | ovo_bench/OCR/HISTORY | 149 | 0.25 | 0.839 [0.78, 0.90] | 0.812 | 0.000 | 0.013 | 8 / 15 / 59 |
| 4BI | ovo_bench/OCR/RECENT | 149 | 0.25 | 0.960 [0.93, 0.99] | 0.946 | 0.000 | 0.013 | 7 / 14 / 59 |
| 4BI | ovo_bench/OJR/HISTORY | 184 | 0.25 | 0.766 [0.69, 0.84] | 0.560 | 0.000 | 0.245 | 7 / 13 / 23 |
| 4BI | ovo_bench/OJR/RECENT | 184 | 0.25 | 0.853 [0.79, 0.90] | 0.630 | 0.000 | 0.250 | 7 / 13 / 21 |
| 4BI | ovo_bench/REC/HISTORY | 698 | — | 0.355 [0.30, 0.42] | 0.355 | 0.000 | 0.000 | 2 / 2 / 3 |
| 4BI | ovo_bench/REC/RECENT | 698 | — | 0.183 [0.15, 0.22] | 0.183 | 0.000 | 0.000 | 2 / 2 / 3 |
| 4BI | ovo_bench/SSR/HISTORY | 629 | 0.50 | 0.649 [0.61, 0.69] | 0.649 | 0.000 | 0.000 | 2 / 2 / 2 |
| 4BI | ovo_bench/SSR/RECENT | 629 | 0.50 | 0.661 [0.61, 0.72] | 0.661 | 0.000 | 0.000 | 2 / 2 / 2 |
| 4BI | ovo_bench/STU/HISTORY | 178 | 0.25 | 0.624 [0.54, 0.71] | 0.590 | 0.000 | 0.034 | 11 / 17 / 31 |
| 4BI | ovo_bench/STU/RECENT | 178 | 0.25 | 0.725 [0.64, 0.81] | 0.691 | 0.000 | 0.034 | 11 / 17 / 25 |
| 4BI | rtv_bench/Action-FP/HISTORY | 365 | 0.35 | 0.597 [0.54, 0.65] | 0.597 | 0.000 | 0.000 | 5 / 7 / 16 |
| 4BI | rtv_bench/Action-FP/RECENT | 365 | 0.35 | 0.663 [0.62, 0.71] | 0.663 | 0.000 | 0.000 | 5 / 7 / 16 |
| 4BI | rtv_bench/Action-GU/HISTORY | 92 | 0.28 | 0.598 [0.50, 0.70] | 0.598 | 0.000 | 0.000 | 5 / 10 / 13 |
| 4BI | rtv_bench/Action-GU/RECENT | 92 | 0.28 | 0.663 [0.57, 0.76] | 0.663 | 0.000 | 0.000 | 5 / 8 / 13 |
| 4BI | rtv_bench/Action-IA/HISTORY | 339 | 0.34 | 0.617 [0.58, 0.66] | 0.614 | 0.000 | 0.003 | 4 / 9 / 14 |
| 4BI | rtv_bench/Action-IA/RECENT | 339 | 0.34 | 0.690 [0.65, 0.73] | 0.687 | 0.000 | 0.003 | 4 / 8 / 14 |
| 4BI | rtv_bench/Action-PU/HISTORY | 148 | 0.36 | 0.622 [0.56, 0.69] | 0.622 | 0.000 | 0.000 | 5 / 8 / 12 |
| 4BI | rtv_bench/Action-PU/RECENT | 148 | 0.36 | 0.696 [0.63, 0.76] | 0.696 | 0.000 | 0.000 | 5 / 8 / 12 |
| 4BI | rtv_bench/Action-SP/HISTORY | 225 | 0.33 | 0.484 [0.43, 0.54] | 0.484 | 0.000 | 0.000 | 5 / 6 / 12 |
| 4BI | rtv_bench/Action-SP/RECENT | 225 | 0.33 | 0.538 [0.48, 0.60] | 0.538 | 0.000 | 0.000 | 5 / 6 / 10 |
| 4BI | rtv_bench/Action-SR/HISTORY | 213 | 0.29 | 0.413 [0.36, 0.47] | 0.413 | 0.000 | 0.000 | 5 / 6 / 6 |
| 4BI | rtv_bench/Action-SR/RECENT | 213 | 0.29 | 0.479 [0.41, 0.55] | 0.479 | 0.000 | 0.000 | 5 / 6 / 6 |
| 4BI | rtv_bench/Action-TP/HISTORY | 170 | 0.32 | 0.506 [0.42, 0.60] | 0.506 | 0.000 | 0.000 | 4 / 9 / 15 |
| 4BI | rtv_bench/Action-TP/RECENT | 170 | 0.32 | 0.641 [0.57, 0.71] | 0.641 | 0.000 | 0.000 | 4 / 9 / 15 |
| 4BI | rtv_bench/Action-VP/HISTORY | 140 | 0.34 | 0.571 [0.50, 0.65] | 0.571 | 0.000 | 0.000 | 5 / 8 / 15 |
| 4BI | rtv_bench/Action-VP/RECENT | 140 | 0.34 | 0.600 [0.51, 0.69] | 0.600 | 0.000 | 0.000 | 5 / 7 / 15 |
| 4BI | rtv_bench/Event-FP/HISTORY | 119 | 0.30 | 0.546 [0.47, 0.62] | 0.546 | 0.000 | 0.000 | 5 / 7 / 9 |
| 4BI | rtv_bench/Event-FP/RECENT | 119 | 0.30 | 0.630 [0.55, 0.72] | 0.630 | 0.000 | 0.000 | 5 / 7 / 10 |
| 4BI | rtv_bench/Event-GU/HISTORY | 247 | 0.27 | 0.514 [0.46, 0.57] | 0.514 | 0.000 | 0.000 | 5 / 6 / 17 |
| 4BI | rtv_bench/Event-GU/RECENT | 247 | 0.27 | 0.526 [0.48, 0.57] | 0.526 | 0.000 | 0.000 | 4 / 6 / 17 |
| 4BI | rtv_bench/Event-IA/HISTORY | 126 | 0.34 | 0.651 [0.57, 0.74] | 0.651 | 0.000 | 0.000 | 5 / 8 / 15 |
| 4BI | rtv_bench/Event-IA/RECENT | 126 | 0.34 | 0.706 [0.62, 0.79] | 0.706 | 0.000 | 0.000 | 5 / 9 / 15 |
| 4BI | rtv_bench/Event-PU/HISTORY | 127 | 0.28 | 0.543 [0.47, 0.62] | 0.543 | 0.000 | 0.000 | 5 / 8 / 10 |
| 4BI | rtv_bench/Event-PU/RECENT | 127 | 0.28 | 0.575 [0.50, 0.64] | 0.575 | 0.000 | 0.008 | 5 / 8 / 11 |
| 4BI | rtv_bench/Event-SP/HISTORY | 112 | 0.28 | 0.554 [0.45, 0.67] | 0.554 | 0.000 | 0.000 | 5 / 9 / 12 |
| 4BI | rtv_bench/Event-SP/RECENT | 112 | 0.28 | 0.670 [0.58, 0.77] | 0.670 | 0.000 | 0.000 | 5 / 9 / 12 |
| 4BI | rtv_bench/Event-SR/HISTORY | 214 | 0.27 | 0.579 [0.52, 0.64] | 0.579 | 0.000 | 0.000 | 5 / 7 / 11 |
| 4BI | rtv_bench/Event-SR/RECENT | 214 | 0.27 | 0.645 [0.59, 0.71] | 0.645 | 0.000 | 0.000 | 5 / 6 / 11 |
| 4BI | rtv_bench/Event-TP/HISTORY | 114 | 0.29 | 0.570 [0.49, 0.67] | 0.570 | 0.000 | 0.000 | 5 / 8 / 15 |
| 4BI | rtv_bench/Event-TP/RECENT | 114 | 0.29 | 0.693 [0.60, 0.77] | 0.693 | 0.000 | 0.000 | 5 / 7 / 15 |
| 4BI | rtv_bench/Event-VP/HISTORY | 458 | 0.33 | 0.598 [0.55, 0.65] | 0.598 | 0.000 | 0.000 | 5 / 8 / 15 |
| 4BI | rtv_bench/Event-VP/RECENT | 458 | 0.33 | 0.666 [0.61, 0.72] | 0.666 | 0.000 | 0.000 | 5 / 7 / 15 |
| 4BI | rtv_bench/Object-FP/HISTORY | 102 | 0.35 | 0.725 [0.65, 0.79] | 0.725 | 0.000 | 0.000 | 4 / 6 / 9 |
| 4BI | rtv_bench/Object-FP/RECENT | 102 | 0.35 | 0.765 [0.69, 0.83] | 0.765 | 0.000 | 0.000 | 4 / 6 / 9 |
| 4BI | rtv_bench/Object-GU/HISTORY | 135 | 0.25 | 0.541 [0.47, 0.60] | 0.541 | 0.000 | 0.000 | 5 / 8 / 15 |
| 4BI | rtv_bench/Object-GU/RECENT | 135 | 0.25 | 0.570 [0.49, 0.65] | 0.570 | 0.000 | 0.000 | 5 / 7 / 12 |
| 4BI | rtv_bench/Object-IA/HISTORY | 87 | 0.28 | 0.575 [0.49, 0.67] | 0.575 | 0.000 | 0.023 | 4 / 6 / 8 |
| 4BI | rtv_bench/Object-IA/RECENT | 87 | 0.28 | 0.609 [0.51, 0.71] | 0.609 | 0.000 | 0.000 | 2 / 5 / 9 |
| 4BI | rtv_bench/Object-PU/HISTORY | 270 | 0.26 | 0.678 [0.62, 0.73] | 0.678 | 0.000 | 0.000 | 5 / 8 / 12 |
| 4BI | rtv_bench/Object-PU/RECENT | 270 | 0.26 | 0.763 [0.71, 0.81] | 0.763 | 0.000 | 0.000 | 5 / 8 / 12 |
| 4BI | rtv_bench/Object-SP/HISTORY | 200 | 0.29 | 0.705 [0.65, 0.76] | 0.705 | 0.000 | 0.000 | 4 / 6 / 16 |
| 4BI | rtv_bench/Object-SP/RECENT | 200 | 0.29 | 0.800 [0.74, 0.86] | 0.800 | 0.000 | 0.000 | 4 / 6 / 16 |
| 4BI | rtv_bench/Object-SR/HISTORY | 161 | 0.26 | 0.547 [0.50, 0.60] | 0.547 | 0.000 | 0.000 | 5 / 6 / 12 |
| 4BI | rtv_bench/Object-SR/RECENT | 161 | 0.26 | 0.578 [0.53, 0.63] | 0.578 | 0.000 | 0.000 | 5 / 6 / 19 |
| 4BI | rtv_bench/Object-TP/HISTORY | 303 | 0.28 | 0.663 [0.61, 0.72] | 0.660 | 0.000 | 0.007 | 4 / 6 / 11 |
| 4BI | rtv_bench/Object-TP/RECENT | 303 | 0.28 | 0.729 [0.68, 0.78] | 0.726 | 0.000 | 0.003 | 4 / 6 / 11 |
| 4BI | rtv_bench/Object-VP/HISTORY | 141 | 0.28 | 0.560 [0.47, 0.66] | 0.553 | 0.000 | 0.014 | 5 / 6 / 12 |
| 4BI | rtv_bench/Object-VP/RECENT | 141 | 0.28 | 0.752 [0.67, 0.83] | 0.745 | 0.000 | 0.014 | 4 / 6 / 16 |
| 8BI | ovo_bench/ACR/HISTORY | 109 | 0.25 | 0.688 [0.60, 0.77] | 0.688 | 0.000 | 0.009 | 2 / 2 / 22 |
| 8BI | ovo_bench/ACR/RECENT | 109 | 0.25 | 0.862 [0.80, 0.92] | 0.862 | 0.000 | 0.009 | 2 / 2 / 11 |
| 8BI | ovo_bench/ASI/HISTORY | 148 | 0.25 | 0.703 [0.63, 0.77] | 0.703 | 0.000 | 0.000 | 2 / 2 / 7 |
| 8BI | ovo_bench/ASI/RECENT | 148 | 0.25 | 0.622 [0.54, 0.70] | 0.622 | 0.000 | 0.000 | 2 / 2 / 7 |
| 8BI | ovo_bench/ATR/HISTORY | 116 | 0.25 | 0.819 [0.72, 0.90] | 0.819 | 0.000 | 0.000 | 2 / 5 / 13 |
| 8BI | ovo_bench/ATR/RECENT | 116 | 0.25 | 0.845 [0.77, 0.91] | 0.836 | 0.000 | 0.000 | 2 / 4 / 13 |
| 8BI | ovo_bench/CRR/HISTORY | 240 | 0.50 | 0.504 [0.46, 0.59] | 0.504 | 0.000 | 0.000 | 2 / 2 / 2 |
| 8BI | ovo_bench/CRR/RECENT | 240 | 0.50 | 0.421 [0.39, 0.46] | 0.421 | 0.000 | 0.000 | 2 / 2 / 2 |
| 8BI | ovo_bench/EPM/HISTORY | 297 | 0.27 | 0.620 [0.56, 0.68] | 0.620 | 0.000 | 0.000 | 2 / 2 / 12 |
| 8BI | ovo_bench/EPM/RECENT | 297 | 0.27 | 0.556 [0.50, 0.61] | 0.556 | 0.000 | 0.000 | 2 / 2 / 12 |
| 8BI | ovo_bench/FPD/HISTORY | 101 | 0.25 | 0.762 [0.67, 0.85] | 0.762 | 0.000 | 0.010 | 2 / 2 / 6 |
| 8BI | ovo_bench/FPD/RECENT | 101 | 0.25 | 0.733 [0.63, 0.83] | 0.733 | 0.000 | 0.010 | 2 / 2 / 6 |
| 8BI | ovo_bench/HLD/HISTORY | 186 | 0.28 | 0.258 [0.20, 0.32] | 0.258 | 0.000 | 0.000 | 2 / 2 / 9 |
| 8BI | ovo_bench/HLD/RECENT | 186 | 0.28 | 0.446 [0.38, 0.52] | 0.446 | 0.000 | 0.000 | 2 / 2 / 8 |
| 8BI | ovo_bench/OCR/HISTORY | 149 | 0.25 | 0.812 [0.74, 0.88] | 0.812 | 0.000 | 0.000 | 2 / 2 / 15 |
| 8BI | ovo_bench/OCR/RECENT | 149 | 0.25 | 0.946 [0.91, 0.98] | 0.946 | 0.000 | 0.000 | 2 / 2 / 9 |
| 8BI | ovo_bench/OJR/HISTORY | 184 | 0.25 | 0.679 [0.61, 0.74] | 0.679 | 0.000 | 0.000 | 2 / 5 / 23 |
| 8BI | ovo_bench/OJR/RECENT | 184 | 0.25 | 0.848 [0.79, 0.90] | 0.837 | 0.000 | 0.011 | 2 / 2 / 10 |
| 8BI | ovo_bench/REC/HISTORY | 698 | — | 0.395 [0.34, 0.45] | 0.395 | 0.000 | 0.000 | 2 / 2 / 3 |
| 8BI | ovo_bench/REC/RECENT | 698 | — | 0.196 [0.17, 0.23] | 0.196 | 0.000 | 0.000 | 2 / 2 / 3 |
| 8BI | ovo_bench/SSR/HISTORY | 629 | 0.50 | 0.669 [0.63, 0.71] | 0.669 | 0.000 | 0.000 | 2 / 2 / 2 |
| 8BI | ovo_bench/SSR/RECENT | 629 | 0.50 | 0.658 [0.62, 0.70] | 0.658 | 0.000 | 0.000 | 2 / 2 / 2 |
| 8BI | ovo_bench/STU/HISTORY | 178 | 0.25 | 0.624 [0.56, 0.70] | 0.624 | 0.000 | 0.000 | 2 / 9 / 21 |
| 8BI | ovo_bench/STU/RECENT | 178 | 0.25 | 0.742 [0.67, 0.81] | 0.742 | 0.000 | 0.000 | 2 / 2 / 17 |
| 8BI | rtv_bench/Action-FP/HISTORY | 365 | 0.35 | 0.603 [0.56, 0.65] | 0.603 | 0.000 | 0.000 | 2 / 2 / 8 |
| 8BI | rtv_bench/Action-FP/RECENT | 365 | 0.35 | 0.701 [0.66, 0.75] | 0.701 | 0.000 | 0.000 | 2 / 2 / 7 |
| 8BI | rtv_bench/Action-GU/HISTORY | 92 | 0.28 | 0.522 [0.45, 0.59] | 0.522 | 0.000 | 0.000 | 2 / 2 / 7 |
| 8BI | rtv_bench/Action-GU/RECENT | 92 | 0.28 | 0.674 [0.58, 0.77] | 0.674 | 0.000 | 0.000 | 2 / 2 / 5 |
| 8BI | rtv_bench/Action-IA/HISTORY | 339 | 0.34 | 0.552 [0.51, 0.60] | 0.552 | 0.000 | 0.000 | 2 / 2 / 14 |
| 8BI | rtv_bench/Action-IA/RECENT | 339 | 0.34 | 0.729 [0.68, 0.77] | 0.729 | 0.000 | 0.000 | 2 / 2 / 5 |
| 8BI | rtv_bench/Action-PU/HISTORY | 148 | 0.36 | 0.588 [0.52, 0.65] | 0.588 | 0.000 | 0.000 | 2 / 2 / 8 |
| 8BI | rtv_bench/Action-PU/RECENT | 148 | 0.36 | 0.723 [0.66, 0.78] | 0.723 | 0.000 | 0.000 | 2 / 2 / 6 |
| 8BI | rtv_bench/Action-SP/HISTORY | 225 | 0.33 | 0.484 [0.43, 0.53] | 0.484 | 0.000 | 0.000 | 2 / 2 / 2 |
| 8BI | rtv_bench/Action-SP/RECENT | 225 | 0.33 | 0.564 [0.50, 0.63] | 0.564 | 0.000 | 0.000 | 2 / 2 / 2 |
| 8BI | rtv_bench/Action-SR/HISTORY | 213 | 0.29 | 0.404 [0.35, 0.46] | 0.404 | 0.000 | 0.000 | 2 / 2 / 4 |
| 8BI | rtv_bench/Action-SR/RECENT | 213 | 0.29 | 0.526 [0.46, 0.59] | 0.526 | 0.000 | 0.000 | 2 / 2 / 2 |
| 8BI | rtv_bench/Action-TP/HISTORY | 170 | 0.32 | 0.471 [0.39, 0.56] | 0.471 | 0.000 | 0.000 | 2 / 2 / 6 |
| 8BI | rtv_bench/Action-TP/RECENT | 170 | 0.32 | 0.676 [0.61, 0.74] | 0.676 | 0.000 | 0.000 | 2 / 2 / 6 |
| 8BI | rtv_bench/Action-VP/HISTORY | 140 | 0.34 | 0.536 [0.43, 0.63] | 0.536 | 0.000 | 0.000 | 2 / 2 / 6 |
| 8BI | rtv_bench/Action-VP/RECENT | 140 | 0.34 | 0.636 [0.55, 0.72] | 0.636 | 0.000 | 0.000 | 2 / 2 / 6 |
| 8BI | rtv_bench/Event-FP/HISTORY | 119 | 0.30 | 0.538 [0.48, 0.61] | 0.538 | 0.000 | 0.000 | 2 / 2 / 5 |
| 8BI | rtv_bench/Event-FP/RECENT | 119 | 0.30 | 0.630 [0.56, 0.70] | 0.630 | 0.000 | 0.000 | 2 / 2 / 5 |
| 8BI | rtv_bench/Event-GU/HISTORY | 247 | 0.27 | 0.478 [0.43, 0.53] | 0.478 | 0.000 | 0.000 | 2 / 3 / 9 |
| 8BI | rtv_bench/Event-GU/RECENT | 247 | 0.27 | 0.534 [0.49, 0.59] | 0.534 | 0.000 | 0.000 | 2 / 2 / 7 |
| 8BI | rtv_bench/Event-IA/HISTORY | 126 | 0.34 | 0.595 [0.49, 0.70] | 0.595 | 0.000 | 0.000 | 2 / 2 / 4 |
| 8BI | rtv_bench/Event-IA/RECENT | 126 | 0.34 | 0.722 [0.62, 0.83] | 0.722 | 0.000 | 0.000 | 2 / 2 / 5 |
| 8BI | rtv_bench/Event-PU/HISTORY | 127 | 0.28 | 0.551 [0.48, 0.63] | 0.551 | 0.000 | 0.000 | 2 / 2 / 5 |
| 8BI | rtv_bench/Event-PU/RECENT | 127 | 0.28 | 0.591 [0.52, 0.66] | 0.591 | 0.000 | 0.000 | 2 / 2 / 7 |
| 8BI | rtv_bench/Event-SP/HISTORY | 112 | 0.28 | 0.589 [0.50, 0.69] | 0.589 | 0.000 | 0.000 | 2 / 2 / 7 |
| 8BI | rtv_bench/Event-SP/RECENT | 112 | 0.28 | 0.741 [0.64, 0.84] | 0.741 | 0.000 | 0.000 | 2 / 2 / 2 |
| 8BI | rtv_bench/Event-SR/HISTORY | 214 | 0.27 | 0.575 [0.52, 0.63] | 0.575 | 0.000 | 0.000 | 2 / 5 / 6 |
| 8BI | rtv_bench/Event-SR/RECENT | 214 | 0.27 | 0.636 [0.57, 0.70] | 0.636 | 0.000 | 0.000 | 2 / 5 / 7 |
| 8BI | rtv_bench/Event-TP/HISTORY | 114 | 0.29 | 0.570 [0.48, 0.67] | 0.570 | 0.000 | 0.000 | 2 / 2 / 5 |
| 8BI | rtv_bench/Event-TP/RECENT | 114 | 0.29 | 0.737 [0.65, 0.81] | 0.737 | 0.000 | 0.000 | 2 / 2 / 5 |
| 8BI | rtv_bench/Event-VP/HISTORY | 458 | 0.33 | 0.592 [0.54, 0.65] | 0.592 | 0.000 | 0.000 | 2 / 2 / 7 |
| 8BI | rtv_bench/Event-VP/RECENT | 458 | 0.33 | 0.659 [0.61, 0.71] | 0.659 | 0.000 | 0.000 | 2 / 2 / 10 |
| 8BI | rtv_bench/Object-FP/HISTORY | 102 | 0.35 | 0.608 [0.53, 0.68] | 0.608 | 0.000 | 0.000 | 2 / 2 / 5 |
| 8BI | rtv_bench/Object-FP/RECENT | 102 | 0.35 | 0.804 [0.74, 0.87] | 0.804 | 0.000 | 0.000 | 2 / 2 / 5 |
| 8BI | rtv_bench/Object-GU/HISTORY | 135 | 0.25 | 0.578 [0.51, 0.64] | 0.578 | 0.000 | 0.000 | 2 / 2 / 7 |
| 8BI | rtv_bench/Object-GU/RECENT | 135 | 0.25 | 0.585 [0.51, 0.66] | 0.585 | 0.000 | 0.000 | 2 / 2 / 7 |
| 8BI | rtv_bench/Object-IA/HISTORY | 87 | 0.28 | 0.494 [0.42, 0.56] | 0.494 | 0.000 | 0.000 | 2 / 2 / 5 |
| 8BI | rtv_bench/Object-IA/RECENT | 87 | 0.28 | 0.586 [0.52, 0.65] | 0.586 | 0.000 | 0.000 | 2 / 2 / 5 |
| 8BI | rtv_bench/Object-PU/HISTORY | 270 | 0.26 | 0.644 [0.59, 0.70] | 0.644 | 0.000 | 0.000 | 2 / 2 / 8 |
| 8BI | rtv_bench/Object-PU/RECENT | 270 | 0.26 | 0.748 [0.69, 0.80] | 0.748 | 0.000 | 0.000 | 2 / 2 / 8 |
| 8BI | rtv_bench/Object-SP/HISTORY | 200 | 0.29 | 0.655 [0.60, 0.71] | 0.655 | 0.000 | 0.000 | 2 / 2 / 6 |
| 8BI | rtv_bench/Object-SP/RECENT | 200 | 0.29 | 0.790 [0.74, 0.84] | 0.790 | 0.000 | 0.005 | 2 / 2 / 6 |
| 8BI | rtv_bench/Object-SR/HISTORY | 161 | 0.26 | 0.547 [0.46, 0.64] | 0.547 | 0.000 | 0.000 | 2 / 2 / 5 |
| 8BI | rtv_bench/Object-SR/RECENT | 161 | 0.26 | 0.590 [0.52, 0.65] | 0.590 | 0.000 | 0.000 | 2 / 2 / 5 |
| 8BI | rtv_bench/Object-TP/HISTORY | 303 | 0.28 | 0.647 [0.60, 0.70] | 0.647 | 0.000 | 0.007 | 2 / 2 / 6 |
| 8BI | rtv_bench/Object-TP/RECENT | 303 | 0.28 | 0.756 [0.71, 0.81] | 0.756 | 0.000 | 0.003 | 2 / 2 / 6 |
| 8BI | rtv_bench/Object-VP/HISTORY | 141 | 0.28 | 0.596 [0.52, 0.67] | 0.596 | 0.000 | 0.000 | 2 / 2 / 5 |
| 8BI | rtv_bench/Object-VP/RECENT | 141 | 0.28 | 0.752 [0.66, 0.85] | 0.752 | 0.000 | 0.000 | 2 / 2 / 5 |
| 32BI | ovo_bench/ACR/HISTORY | 109 | 0.25 | 0.706 [0.60, 0.80] | 0.706 | 0.009 | 0.009 | 10 / 14 / 64 |
| 32BI | ovo_bench/ACR/RECENT | 109 | 0.25 | 0.890 [0.83, 0.94] | 0.890 | 0.009 | 0.009 | 8 / 12 / 64 |
| 32BI | ovo_bench/ASI/HISTORY | 148 | 0.25 | 0.709 [0.64, 0.78] | 0.709 | 0.000 | 0.000 | 6 / 12 / 22 |
| 32BI | ovo_bench/ASI/RECENT | 148 | 0.25 | 0.622 [0.54, 0.70] | 0.622 | 0.007 | 0.007 | 2 / 8 / 64 |
| 32BI | ovo_bench/ATR/HISTORY | 116 | 0.25 | 0.862 [0.77, 0.93] | 0.853 | 0.000 | 0.000 | 6 / 11 / 16 |
| 32BI | ovo_bench/ATR/RECENT | 116 | 0.25 | 0.897 [0.84, 0.95] | 0.888 | 0.000 | 0.009 | 2 / 8 / 16 |
| 32BI | ovo_bench/CRR/HISTORY | 240 | 0.50 | 0.537 [0.48, 0.61] | 0.537 | 0.000 | 0.000 | 2 / 2 / 2 |
| 32BI | ovo_bench/CRR/RECENT | 240 | 0.50 | 0.396 [0.37, 0.43] | 0.396 | 0.000 | 0.000 | 2 / 2 / 2 |
| 32BI | ovo_bench/EPM/HISTORY | 297 | 0.27 | 0.677 [0.62, 0.74] | 0.643 | 0.000 | 0.044 | 6 / 10 / 15 |
| 32BI | ovo_bench/EPM/RECENT | 297 | 0.27 | 0.562 [0.51, 0.62] | 0.549 | 0.003 | 0.027 | 4 / 7 / 64 |
| 32BI | ovo_bench/FPD/HISTORY | 101 | 0.25 | 0.772 [0.69, 0.85] | 0.772 | 0.000 | 0.010 | 12 / 15 / 40 |
| 32BI | ovo_bench/FPD/RECENT | 101 | 0.25 | 0.772 [0.68, 0.86] | 0.772 | 0.000 | 0.010 | 2 / 14 / 41 |
| 32BI | ovo_bench/HLD/HISTORY | 186 | 0.28 | 0.527 [0.44, 0.61] | 0.522 | 0.000 | 0.022 | 6 / 7 / 11 |
| 32BI | ovo_bench/HLD/RECENT | 186 | 0.28 | 0.715 [0.64, 0.78] | 0.710 | 0.000 | 0.011 | 2 / 6 / 11 |
| 32BI | ovo_bench/OCR/HISTORY | 149 | 0.25 | 0.826 [0.76, 0.89] | 0.805 | 0.000 | 0.013 | 2 / 9 / 21 |
| 32BI | ovo_bench/OCR/RECENT | 149 | 0.25 | 0.966 [0.94, 0.99] | 0.960 | 0.007 | 0.000 | 2 / 7 / 64 |
| 32BI | ovo_bench/OJR/HISTORY | 184 | 0.25 | 0.761 [0.69, 0.82] | 0.565 | 0.000 | 0.223 | 6 / 11 / 18 |
| 32BI | ovo_bench/OJR/RECENT | 184 | 0.25 | 0.870 [0.81, 0.92] | 0.674 | 0.005 | 0.212 | 6 / 9 / 64 |
| 32BI | ovo_bench/REC/HISTORY | 698 | — | 0.421 [0.36, 0.49] | 0.421 | 0.000 | 0.000 | 2 / 2 / 3 |
| 32BI | ovo_bench/REC/RECENT | 698 | — | 0.170 [0.14, 0.21] | 0.170 | 0.000 | 0.000 | 2 / 2 / 3 |
| 32BI | ovo_bench/SSR/HISTORY | 629 | 0.50 | 0.709 [0.67, 0.75] | 0.709 | 0.000 | 0.000 | 2 / 2 / 2 |
| 32BI | ovo_bench/SSR/RECENT | 629 | 0.50 | 0.685 [0.64, 0.73] | 0.685 | 0.000 | 0.000 | 2 / 2 / 2 |
| 32BI | ovo_bench/STU/HISTORY | 178 | 0.25 | 0.657 [0.58, 0.73] | 0.618 | 0.000 | 0.034 | 8 / 16 / 31 |
| 32BI | ovo_bench/STU/RECENT | 178 | 0.25 | 0.742 [0.65, 0.82] | 0.713 | 0.006 | 0.022 | 2 / 14 / 64 |
| 32BI | rtv_bench/Action-FP/HISTORY | 365 | 0.35 | 0.633 [0.59, 0.68] | 0.633 | 0.000 | 0.000 | 2 / 6 / 13 |
| 32BI | rtv_bench/Action-FP/RECENT | 365 | 0.35 | 0.710 [0.66, 0.76] | 0.710 | 0.000 | 0.000 | 2 / 5 / 14 |
| 32BI | rtv_bench/Action-GU/HISTORY | 92 | 0.28 | 0.565 [0.48, 0.64] | 0.565 | 0.000 | 0.000 | 2 / 5 / 10 |
| 32BI | rtv_bench/Action-GU/RECENT | 92 | 0.28 | 0.685 [0.59, 0.78] | 0.685 | 0.000 | 0.000 | 2 / 5 / 11 |
| 32BI | rtv_bench/Action-IA/HISTORY | 339 | 0.34 | 0.640 [0.59, 0.69] | 0.637 | 0.000 | 0.003 | 2 / 6 / 11 |
| 32BI | rtv_bench/Action-IA/RECENT | 339 | 0.34 | 0.735 [0.68, 0.78] | 0.735 | 0.003 | 0.003 | 2 / 5 / 64 |
| 32BI | rtv_bench/Action-PU/HISTORY | 148 | 0.36 | 0.628 [0.57, 0.69] | 0.628 | 0.000 | 0.000 | 2 / 5 / 12 |
| 32BI | rtv_bench/Action-PU/RECENT | 148 | 0.36 | 0.770 [0.72, 0.82] | 0.770 | 0.000 | 0.000 | 2 / 5 / 12 |
| 32BI | rtv_bench/Action-SP/HISTORY | 225 | 0.33 | 0.516 [0.47, 0.56] | 0.516 | 0.000 | 0.000 | 2 / 5 / 10 |
| 32BI | rtv_bench/Action-SP/RECENT | 225 | 0.33 | 0.613 [0.55, 0.67] | 0.613 | 0.004 | 0.004 | 2 / 5 / 64 |
| 32BI | rtv_bench/Action-SR/HISTORY | 213 | 0.29 | 0.404 [0.34, 0.46] | 0.404 | 0.000 | 0.000 | 2 / 6 / 6 |
| 32BI | rtv_bench/Action-SR/RECENT | 213 | 0.29 | 0.526 [0.46, 0.59] | 0.526 | 0.000 | 0.000 | 2 / 5 / 6 |
| 32BI | rtv_bench/Action-TP/HISTORY | 170 | 0.32 | 0.435 [0.35, 0.52] | 0.435 | 0.000 | 0.000 | 2 / 9 / 10 |
| 32BI | rtv_bench/Action-TP/RECENT | 170 | 0.32 | 0.659 [0.60, 0.73] | 0.659 | 0.000 | 0.000 | 2 / 7 / 10 |
| 32BI | rtv_bench/Action-VP/HISTORY | 140 | 0.34 | 0.557 [0.48, 0.63] | 0.557 | 0.000 | 0.000 | 2 / 6 / 11 |
| 32BI | rtv_bench/Action-VP/RECENT | 140 | 0.34 | 0.700 [0.62, 0.78] | 0.700 | 0.000 | 0.000 | 2 / 5 / 11 |
| 32BI | rtv_bench/Event-FP/HISTORY | 119 | 0.30 | 0.630 [0.57, 0.70] | 0.630 | 0.000 | 0.000 | 4 / 6 / 10 |
| 32BI | rtv_bench/Event-FP/RECENT | 119 | 0.30 | 0.639 [0.56, 0.72] | 0.639 | 0.000 | 0.000 | 2 / 6 / 10 |
| 32BI | rtv_bench/Event-GU/HISTORY | 247 | 0.27 | 0.543 [0.49, 0.60] | 0.543 | 0.000 | 0.000 | 4 / 5 / 13 |
| 32BI | rtv_bench/Event-GU/RECENT | 247 | 0.27 | 0.534 [0.49, 0.59] | 0.534 | 0.000 | 0.000 | 2 / 5 / 9 |
| 32BI | rtv_bench/Event-IA/HISTORY | 126 | 0.34 | 0.627 [0.55, 0.71] | 0.627 | 0.000 | 0.000 | 2 / 8 / 12 |
| 32BI | rtv_bench/Event-IA/RECENT | 126 | 0.34 | 0.746 [0.67, 0.82] | 0.746 | 0.008 | 0.000 | 2 / 7 / 64 |
| 32BI | rtv_bench/Event-PU/HISTORY | 127 | 0.28 | 0.606 [0.54, 0.67] | 0.598 | 0.000 | 0.016 | 4 / 8 / 11 |
| 32BI | rtv_bench/Event-PU/RECENT | 127 | 0.28 | 0.669 [0.61, 0.72] | 0.669 | 0.000 | 0.008 | 2 / 7 / 11 |
| 32BI | rtv_bench/Event-SP/HISTORY | 112 | 0.28 | 0.598 [0.50, 0.70] | 0.598 | 0.000 | 0.000 | 4 / 8 / 12 |
| 32BI | rtv_bench/Event-SP/RECENT | 112 | 0.28 | 0.723 [0.64, 0.81] | 0.723 | 0.000 | 0.000 | 2 / 8 / 12 |
| 32BI | rtv_bench/Event-SR/HISTORY | 214 | 0.27 | 0.593 [0.53, 0.65] | 0.593 | 0.000 | 0.000 | 2 / 5 / 11 |
| 32BI | rtv_bench/Event-SR/RECENT | 214 | 0.27 | 0.650 [0.58, 0.71] | 0.645 | 0.009 | 0.009 | 2 / 5 / 64 |
| 32BI | rtv_bench/Event-TP/HISTORY | 114 | 0.29 | 0.605 [0.51, 0.71] | 0.605 | 0.000 | 0.000 | 4 / 6 / 15 |
| 32BI | rtv_bench/Event-TP/RECENT | 114 | 0.29 | 0.763 [0.68, 0.84] | 0.763 | 0.000 | 0.000 | 2 / 6 / 13 |
| 32BI | rtv_bench/Event-VP/HISTORY | 458 | 0.33 | 0.611 [0.56, 0.66] | 0.611 | 0.000 | 0.000 | 2 / 6 / 13 |
| 32BI | rtv_bench/Event-VP/RECENT | 458 | 0.33 | 0.712 [0.67, 0.76] | 0.712 | 0.000 | 0.000 | 2 / 5 / 13 |
| 32BI | rtv_bench/Object-FP/HISTORY | 102 | 0.35 | 0.696 [0.61, 0.78] | 0.696 | 0.000 | 0.000 | 2 / 5 / 9 |
| 32BI | rtv_bench/Object-FP/RECENT | 102 | 0.35 | 0.735 [0.67, 0.80] | 0.735 | 0.000 | 0.000 | 2 / 4 / 9 |
| 32BI | rtv_bench/Object-GU/HISTORY | 135 | 0.25 | 0.622 [0.56, 0.70] | 0.622 | 0.000 | 0.000 | 5 / 7 / 15 |
| 32BI | rtv_bench/Object-GU/RECENT | 135 | 0.25 | 0.556 [0.49, 0.62] | 0.556 | 0.000 | 0.000 | 2 / 7 / 12 |
| 32BI | rtv_bench/Object-IA/HISTORY | 87 | 0.28 | 0.540 [0.45, 0.63] | 0.540 | 0.034 | 0.034 | 2 / 6 / 64 |
| 32BI | rtv_bench/Object-IA/RECENT | 87 | 0.28 | 0.655 [0.59, 0.72] | 0.655 | 0.011 | 0.011 | 2 / 6 / 64 |
| 32BI | rtv_bench/Object-PU/HISTORY | 270 | 0.26 | 0.693 [0.64, 0.74] | 0.693 | 0.000 | 0.000 | 2 / 6 / 12 |
| 32BI | rtv_bench/Object-PU/RECENT | 270 | 0.26 | 0.763 [0.71, 0.81] | 0.759 | 0.011 | 0.011 | 2 / 6 / 64 |
| 32BI | rtv_bench/Object-SP/HISTORY | 200 | 0.29 | 0.725 [0.67, 0.78] | 0.725 | 0.000 | 0.000 | 2 / 5 / 6 |
| 32BI | rtv_bench/Object-SP/RECENT | 200 | 0.29 | 0.780 [0.72, 0.83] | 0.775 | 0.000 | 0.005 | 2 / 5 / 9 |
| 32BI | rtv_bench/Object-SR/HISTORY | 161 | 0.26 | 0.553 [0.48, 0.62] | 0.553 | 0.000 | 0.000 | 4 / 7 / 19 |
| 32BI | rtv_bench/Object-SR/RECENT | 161 | 0.26 | 0.634 [0.57, 0.70] | 0.634 | 0.000 | 0.000 | 2 / 6 / 19 |
| 32BI | rtv_bench/Object-TP/HISTORY | 303 | 0.28 | 0.667 [0.62, 0.72] | 0.663 | 0.000 | 0.010 | 4 / 6 / 11 |
| 32BI | rtv_bench/Object-TP/RECENT | 303 | 0.28 | 0.759 [0.71, 0.81] | 0.756 | 0.000 | 0.003 | 2 / 6 / 11 |
| 32BI | rtv_bench/Object-VP/HISTORY | 141 | 0.28 | 0.603 [0.51, 0.68] | 0.596 | 0.000 | 0.021 | 4 / 6 / 12 |
| 32BI | rtv_bench/Object-VP/RECENT | 141 | 0.28 | 0.709 [0.63, 0.79] | 0.702 | 0.000 | 0.014 | 2 / 6 / 16 |
| 4BT | ovo_bench/ACR/HISTORY | 109 | 0.25 | 0.651 [0.57, 0.74] | 0.642 | 0.000 | 0.009 | 132 / 362 / 3549 |
| 4BT | ovo_bench/ACR/RECENT | 109 | 0.25 | 0.862 [0.80, 0.92] | 0.862 | 0.000 | 0.000 | 133 / 484 / 3733 |
| 4BT | ovo_bench/ASI/HISTORY | 148 | 0.25 | 0.723 [0.65, 0.79] | 0.723 | 0.000 | 0.000 | 213 / 888 / 3296 |
| 4BT | ovo_bench/ASI/RECENT | 148 | 0.25 | 0.547 [0.47, 0.63] | 0.547 | 0.000 | 0.000 | 408 / 1128 / 3842 |
| 4BT | ovo_bench/ATR/HISTORY | 116 | 0.25 | 0.733 [0.64, 0.82] | 0.733 | 0.000 | 0.000 | 89 / 285 / 941 |
| 4BT | ovo_bench/ATR/RECENT | 116 | 0.25 | 0.776 [0.69, 0.86] | 0.776 | 0.000 | 0.000 | 90 / 300 / 1805 |
| 4BT | ovo_bench/CRR/HISTORY | 240 | 0.50 | 0.558 [0.50, 0.63] | 0.558 | 0.000 | 0.000 | 556 / 1478 / 6442 |
| 4BT | ovo_bench/CRR/RECENT | 240 | 0.50 | 0.463 [0.40, 0.52] | 0.463 | 0.000 | 0.000 | 225 / 869 / 3323 |
| 4BT | ovo_bench/EPM/HISTORY | 297 | 0.27 | 0.586 [0.53, 0.65] | 0.586 | 0.000 | 0.000 | 109 / 370 / 1989 |
| 4BT | ovo_bench/EPM/RECENT | 297 | 0.27 | 0.559 [0.49, 0.63] | 0.559 | 0.000 | 0.000 | 152 / 658 / 3677 |
| 4BT | ovo_bench/FPD/HISTORY | 101 | 0.25 | 0.683 [0.59, 0.78] | 0.683 | 0.010 | 0.010 | 130 / 574 / 16384 |
| 4BT | ovo_bench/FPD/RECENT | 101 | 0.25 | 0.713 [0.62, 0.81] | 0.713 | 0.000 | 0.000 | 157 / 611 / 3037 |
| 4BT | ovo_bench/HLD/HISTORY | 186 | 0.28 | 0.414 [0.34, 0.48] | 0.414 | 0.000 | 0.000 | 180 / 625 / 3013 |
| 4BT | ovo_bench/HLD/RECENT | 186 | 0.28 | 0.602 [0.53, 0.67] | 0.602 | 0.000 | 0.000 | 194 / 588 / 2891 |
| 4BT | ovo_bench/OCR/HISTORY | 149 | 0.25 | 0.765 [0.69, 0.84] | 0.765 | 0.000 | 0.000 | 86 / 348 / 2250 |
| 4BT | ovo_bench/OCR/RECENT | 149 | 0.25 | 0.946 [0.91, 0.98] | 0.946 | 0.000 | 0.000 | 82 / 584 / 4201 |
| 4BT | ovo_bench/OJR/HISTORY | 184 | 0.25 | 0.663 [0.60, 0.73] | 0.663 | 0.000 | 0.000 | 102 / 484 / 2399 |
| 4BT | ovo_bench/OJR/RECENT | 184 | 0.25 | 0.826 [0.76, 0.89] | 0.826 | 0.000 | 0.000 | 101 / 299 / 4459 |
| 4BT | ovo_bench/REC/HISTORY | 698 | — | 0.317 [0.26, 0.39] | 0.317 | 0.000 | 0.000 | 2120 / 5483 / 12633 |
| 4BT | ovo_bench/REC/RECENT | 698 | — | 0.186 [0.15, 0.23] | 0.186 | 0.000 | 0.000 | 1174 / 3286 / 7716 |
| 4BT | ovo_bench/SSR/HISTORY | 629 | 0.50 | 0.712 [0.68, 0.74] | 0.712 | 0.000 | 0.000 | 106 / 552 / 2684 |
| 4BT | ovo_bench/SSR/RECENT | 629 | 0.50 | 0.728 [0.69, 0.76] | 0.728 | 0.000 | 0.000 | 105 / 503 / 2942 |
| 4BT | ovo_bench/STU/HISTORY | 178 | 0.25 | 0.562 [0.48, 0.64] | 0.562 | 0.000 | 0.000 | 202 / 874 / 3095 |
| 4BT | ovo_bench/STU/RECENT | 178 | 0.25 | 0.753 [0.67, 0.83] | 0.753 | 0.000 | 0.000 | 192 / 1173 / 4357 |
| 4BT | rtv_bench/Action-FP/HISTORY | 365 | 0.35 | 0.581 [0.54, 0.62] | 0.581 | 0.000 | 0.000 | 197 / 720 / 2296 |
| 4BT | rtv_bench/Action-FP/RECENT | 365 | 0.35 | 0.627 [0.58, 0.68] | 0.627 | 0.000 | 0.000 | 187 / 888 / 4946 |
| 4BT | rtv_bench/Action-GU/HISTORY | 92 | 0.28 | 0.543 [0.46, 0.62] | 0.543 | 0.011 | 0.011 | 162 / 1146 / 16384 |
| 4BT | rtv_bench/Action-GU/RECENT | 92 | 0.28 | 0.652 [0.56, 0.74] | 0.652 | 0.000 | 0.000 | 244 / 1499 / 2359 |
| 4BT | rtv_bench/Action-IA/HISTORY | 339 | 0.34 | 0.593 [0.55, 0.64] | 0.593 | 0.000 | 0.000 | 142 / 682 / 4902 |
| 4BT | rtv_bench/Action-IA/RECENT | 339 | 0.34 | 0.705 [0.66, 0.75] | 0.705 | 0.000 | 0.000 | 200 / 1010 / 2771 |
| 4BT | rtv_bench/Action-PU/HISTORY | 148 | 0.36 | 0.588 [0.53, 0.65] | 0.588 | 0.000 | 0.000 | 202 / 850 / 2340 |
| 4BT | rtv_bench/Action-PU/RECENT | 148 | 0.36 | 0.676 [0.61, 0.74] | 0.676 | 0.000 | 0.000 | 260 / 1384 / 3979 |
| 4BT | rtv_bench/Action-SP/HISTORY | 225 | 0.33 | 0.480 [0.43, 0.53] | 0.480 | 0.000 | 0.000 | 360 / 1067 / 3007 |
| 4BT | rtv_bench/Action-SP/RECENT | 225 | 0.33 | 0.507 [0.43, 0.58] | 0.507 | 0.000 | 0.000 | 420 / 1199 / 3513 |
| 4BT | rtv_bench/Action-SR/HISTORY | 213 | 0.29 | 0.380 [0.33, 0.43] | 0.380 | 0.000 | 0.000 | 356 / 992 / 2249 |
| 4BT | rtv_bench/Action-SR/RECENT | 213 | 0.29 | 0.498 [0.44, 0.56] | 0.498 | 0.000 | 0.000 | 711 / 1711 / 3981 |
| 4BT | rtv_bench/Action-TP/HISTORY | 170 | 0.32 | 0.447 [0.37, 0.53] | 0.447 | 0.006 | 0.006 | 264 / 1076 / 16384 |
| 4BT | rtv_bench/Action-TP/RECENT | 170 | 0.32 | 0.600 [0.52, 0.67] | 0.600 | 0.000 | 0.000 | 302 / 2044 / 4288 |
| 4BT | rtv_bench/Action-VP/HISTORY | 140 | 0.34 | 0.507 [0.43, 0.59] | 0.507 | 0.000 | 0.000 | 246 / 1106 / 4825 |
| 4BT | rtv_bench/Action-VP/RECENT | 140 | 0.34 | 0.621 [0.54, 0.71] | 0.621 | 0.000 | 0.000 | 427 / 1266 / 3430 |
| 4BT | rtv_bench/Event-FP/HISTORY | 119 | 0.30 | 0.504 [0.45, 0.56] | 0.504 | 0.000 | 0.000 | 161 / 645 / 2385 |
| 4BT | rtv_bench/Event-FP/RECENT | 119 | 0.30 | 0.672 [0.61, 0.74] | 0.672 | 0.000 | 0.000 | 175 / 943 / 3620 |
| 4BT | rtv_bench/Event-GU/HISTORY | 247 | 0.27 | 0.490 [0.42, 0.55] | 0.490 | 0.000 | 0.000 | 528 / 2093 / 6165 |
| 4BT | rtv_bench/Event-GU/RECENT | 247 | 0.27 | 0.526 [0.47, 0.58] | 0.526 | 0.000 | 0.000 | 439 / 2256 / 4557 |
| 4BT | rtv_bench/Event-IA/HISTORY | 126 | 0.34 | 0.595 [0.51, 0.70] | 0.595 | 0.000 | 0.000 | 118 / 584 / 2855 |
| 4BT | rtv_bench/Event-IA/RECENT | 126 | 0.34 | 0.643 [0.55, 0.74] | 0.643 | 0.000 | 0.000 | 128 / 851 / 3272 |
| 4BT | rtv_bench/Event-PU/HISTORY | 127 | 0.28 | 0.496 [0.43, 0.57] | 0.496 | 0.000 | 0.000 | 124 / 605 / 3769 |
| 4BT | rtv_bench/Event-PU/RECENT | 127 | 0.28 | 0.591 [0.52, 0.66] | 0.591 | 0.000 | 0.000 | 142 / 788 / 3405 |
| 4BT | rtv_bench/Event-SP/HISTORY | 112 | 0.28 | 0.616 [0.50, 0.72] | 0.616 | 0.000 | 0.000 | 144 / 1069 / 2275 |
| 4BT | rtv_bench/Event-SP/RECENT | 112 | 0.28 | 0.723 [0.62, 0.82] | 0.723 | 0.000 | 0.000 | 128 / 774 / 1934 |
| 4BT | rtv_bench/Event-SR/HISTORY | 214 | 0.27 | 0.551 [0.50, 0.61] | 0.551 | 0.000 | 0.000 | 202 / 809 / 5254 |
| 4BT | rtv_bench/Event-SR/RECENT | 214 | 0.27 | 0.612 [0.55, 0.67] | 0.612 | 0.000 | 0.000 | 279 / 1096 / 3244 |
| 4BT | rtv_bench/Event-TP/HISTORY | 114 | 0.29 | 0.623 [0.52, 0.73] | 0.623 | 0.000 | 0.000 | 126 / 633 / 2383 |
| 4BT | rtv_bench/Event-TP/RECENT | 114 | 0.29 | 0.763 [0.69, 0.83] | 0.763 | 0.000 | 0.000 | 136 / 926 / 2497 |
| 4BT | rtv_bench/Event-VP/HISTORY | 458 | 0.33 | 0.603 [0.55, 0.65] | 0.603 | 0.000 | 0.000 | 143 / 757 / 6652 |
| 4BT | rtv_bench/Event-VP/RECENT | 458 | 0.33 | 0.648 [0.60, 0.70] | 0.648 | 0.000 | 0.000 | 138 / 686 / 5304 |
| 4BT | rtv_bench/Object-FP/HISTORY | 102 | 0.35 | 0.676 [0.61, 0.74] | 0.676 | 0.000 | 0.000 | 153 / 740 / 4131 |
| 4BT | rtv_bench/Object-FP/RECENT | 102 | 0.35 | 0.696 [0.62, 0.76] | 0.696 | 0.000 | 0.000 | 172 / 1477 / 3099 |
| 4BT | rtv_bench/Object-GU/HISTORY | 135 | 0.25 | 0.615 [0.55, 0.69] | 0.615 | 0.000 | 0.000 | 248 / 1388 / 3541 |
| 4BT | rtv_bench/Object-GU/RECENT | 135 | 0.25 | 0.533 [0.46, 0.60] | 0.533 | 0.000 | 0.000 | 328 / 1438 / 3926 |
| 4BT | rtv_bench/Object-IA/HISTORY | 87 | 0.28 | 0.563 [0.50, 0.63] | 0.563 | 0.000 | 0.000 | 333 / 1314 / 2473 |
| 4BT | rtv_bench/Object-IA/RECENT | 87 | 0.28 | 0.598 [0.54, 0.66] | 0.598 | 0.000 | 0.000 | 482 / 1517 / 3699 |
| 4BT | rtv_bench/Object-PU/HISTORY | 270 | 0.26 | 0.681 [0.63, 0.73] | 0.681 | 0.000 | 0.000 | 112 / 460 / 3681 |
| 4BT | rtv_bench/Object-PU/RECENT | 270 | 0.26 | 0.756 [0.70, 0.81] | 0.756 | 0.000 | 0.000 | 110 / 548 / 2624 |
| 4BT | rtv_bench/Object-SP/HISTORY | 200 | 0.29 | 0.695 [0.64, 0.75] | 0.690 | 0.000 | 0.015 | 101 / 531 / 8724 |
| 4BT | rtv_bench/Object-SP/RECENT | 200 | 0.29 | 0.795 [0.74, 0.85] | 0.785 | 0.000 | 0.020 | 92 / 534 / 2098 |
| 4BT | rtv_bench/Object-SR/HISTORY | 161 | 0.26 | 0.522 [0.45, 0.58] | 0.522 | 0.000 | 0.000 | 153 / 937 / 2765 |
| 4BT | rtv_bench/Object-SR/RECENT | 161 | 0.26 | 0.609 [0.55, 0.66] | 0.609 | 0.000 | 0.000 | 177 / 975 / 4462 |
| 4BT | rtv_bench/Object-TP/HISTORY | 303 | 0.28 | 0.650 [0.59, 0.71] | 0.647 | 0.003 | 0.013 | 117 / 818 / 16384 |
| 4BT | rtv_bench/Object-TP/RECENT | 303 | 0.28 | 0.729 [0.67, 0.79] | 0.726 | 0.000 | 0.010 | 115 / 857 / 4693 |
| 4BT | rtv_bench/Object-VP/HISTORY | 141 | 0.28 | 0.567 [0.48, 0.66] | 0.567 | 0.000 | 0.014 | 120 / 719 / 2251 |
| 4BT | rtv_bench/Object-VP/RECENT | 141 | 0.28 | 0.730 [0.64, 0.82] | 0.723 | 0.000 | 0.007 | 180 / 827 / 3536 |
| 8BT | ovo_bench/ACR/HISTORY | 109 | 0.25 | 0.633 [0.55, 0.72] | 0.633 | 0.000 | 0.009 | 133 / 725 / 2438 |
| 8BT | ovo_bench/ACR/RECENT | 109 | 0.25 | 0.826 [0.76, 0.89] | 0.817 | 0.000 | 0.009 | 116 / 386 / 4908 |
| 8BT | ovo_bench/ASI/HISTORY | 148 | 0.25 | 0.682 [0.61, 0.76] | 0.682 | 0.000 | 0.000 | 217 / 1411 / 5117 |
| 8BT | ovo_bench/ASI/RECENT | 148 | 0.25 | 0.601 [0.52, 0.68] | 0.601 | 0.000 | 0.000 | 310 / 910 / 2996 |
| 8BT | ovo_bench/ATR/HISTORY | 116 | 0.25 | 0.759 [0.65, 0.85] | 0.759 | 0.000 | 0.000 | 75 / 280 / 1070 |
| 8BT | ovo_bench/ATR/RECENT | 116 | 0.25 | 0.845 [0.77, 0.91] | 0.845 | 0.000 | 0.000 | 86 / 280 / 2160 |
| 8BT | ovo_bench/CRR/HISTORY | 240 | 0.50 | 0.517 [0.45, 0.60] | 0.517 | 0.000 | 0.000 | 233 / 844 / 4916 |
| 8BT | ovo_bench/CRR/RECENT | 240 | 0.50 | 0.433 [0.39, 0.48] | 0.433 | 0.000 | 0.000 | 152 / 675 / 2938 |
| 8BT | ovo_bench/EPM/HISTORY | 297 | 0.27 | 0.576 [0.50, 0.65] | 0.576 | 0.000 | 0.000 | 91 / 394 / 1875 |
| 8BT | ovo_bench/EPM/RECENT | 297 | 0.27 | 0.552 [0.49, 0.61] | 0.552 | 0.000 | 0.000 | 121 / 632 / 2458 |
| 8BT | ovo_bench/FPD/HISTORY | 101 | 0.25 | 0.653 [0.54, 0.75] | 0.644 | 0.010 | 0.010 | 125 / 668 / 16384 |
| 8BT | ovo_bench/FPD/RECENT | 101 | 0.25 | 0.673 [0.57, 0.77] | 0.663 | 0.000 | 0.010 | 139 / 558 / 6226 |
| 8BT | ovo_bench/HLD/HISTORY | 186 | 0.28 | 0.468 [0.39, 0.55] | 0.468 | 0.000 | 0.000 | 146 / 531 / 2975 |
| 8BT | ovo_bench/HLD/RECENT | 186 | 0.28 | 0.602 [0.53, 0.67] | 0.602 | 0.000 | 0.000 | 179 / 522 / 2233 |
| 8BT | ovo_bench/OCR/HISTORY | 149 | 0.25 | 0.765 [0.69, 0.84] | 0.765 | 0.000 | 0.000 | 71 / 460 / 1882 |
| 8BT | ovo_bench/OCR/RECENT | 149 | 0.25 | 0.940 [0.90, 0.98] | 0.940 | 0.000 | 0.000 | 76 / 402 / 3683 |
| 8BT | ovo_bench/OJR/HISTORY | 184 | 0.25 | 0.630 [0.55, 0.71] | 0.630 | 0.000 | 0.000 | 84 / 476 / 3305 |
| 8BT | ovo_bench/OJR/RECENT | 184 | 0.25 | 0.826 [0.77, 0.88] | 0.826 | 0.000 | 0.000 | 86 / 288 / 2353 |
| 8BT | ovo_bench/REC/HISTORY | 698 | — | 0.377 [0.31, 0.45] | 0.377 | 0.000 | 0.000 | 1882 / 4705 / 10179 |
| 8BT | ovo_bench/REC/RECENT | 698 | — | 0.215 [0.18, 0.25] | 0.215 | 0.000 | 0.000 | 889 / 2622 / 9321 |
| 8BT | ovo_bench/SSR/HISTORY | 629 | 0.50 | 0.719 [0.69, 0.75] | 0.719 | 0.000 | 0.000 | 106 / 393 / 3149 |
| 8BT | ovo_bench/SSR/RECENT | 629 | 0.50 | 0.744 [0.71, 0.78] | 0.744 | 0.000 | 0.000 | 103 / 360 / 2132 |
| 8BT | ovo_bench/STU/HISTORY | 178 | 0.25 | 0.528 [0.44, 0.61] | 0.528 | 0.000 | 0.000 | 128 / 817 / 2320 |
| 8BT | ovo_bench/STU/RECENT | 178 | 0.25 | 0.713 [0.63, 0.79] | 0.713 | 0.000 | 0.000 | 134 / 886 / 2700 |
| 8BT | rtv_bench/Action-FP/HISTORY | 365 | 0.35 | 0.548 [0.51, 0.59] | 0.548 | 0.000 | 0.000 | 143 / 636 / 2245 |
| 8BT | rtv_bench/Action-FP/RECENT | 365 | 0.35 | 0.655 [0.60, 0.71] | 0.655 | 0.000 | 0.000 | 133 / 653 / 4470 |
| 8BT | rtv_bench/Action-GU/HISTORY | 92 | 0.28 | 0.500 [0.44, 0.55] | 0.500 | 0.011 | 0.011 | 168 / 964 / 16384 |
| 8BT | rtv_bench/Action-GU/RECENT | 92 | 0.28 | 0.663 [0.55, 0.77] | 0.663 | 0.000 | 0.000 | 172 / 1189 / 3691 |
| 8BT | rtv_bench/Action-IA/HISTORY | 339 | 0.34 | 0.569 [0.52, 0.61] | 0.569 | 0.000 | 0.000 | 130 / 667 / 4112 |
| 8BT | rtv_bench/Action-IA/RECENT | 339 | 0.34 | 0.670 [0.62, 0.72] | 0.670 | 0.000 | 0.000 | 181 / 925 / 3521 |
| 8BT | rtv_bench/Action-PU/HISTORY | 148 | 0.36 | 0.601 [0.54, 0.66] | 0.601 | 0.000 | 0.000 | 140 / 1003 / 3574 |
| 8BT | rtv_bench/Action-PU/RECENT | 148 | 0.36 | 0.676 [0.60, 0.75] | 0.676 | 0.000 | 0.000 | 168 / 1500 / 3235 |
| 8BT | rtv_bench/Action-SP/HISTORY | 225 | 0.33 | 0.449 [0.40, 0.50] | 0.449 | 0.004 | 0.004 | 317 / 1136 / 16384 |
| 8BT | rtv_bench/Action-SP/RECENT | 225 | 0.33 | 0.511 [0.45, 0.58] | 0.511 | 0.000 | 0.000 | 356 / 1390 / 4111 |
| 8BT | rtv_bench/Action-SR/HISTORY | 213 | 0.29 | 0.343 [0.29, 0.40] | 0.343 | 0.000 | 0.000 | 357 / 1312 / 4471 |
| 8BT | rtv_bench/Action-SR/RECENT | 213 | 0.29 | 0.446 [0.37, 0.51] | 0.446 | 0.000 | 0.000 | 571 / 1574 / 3743 |
| 8BT | rtv_bench/Action-TP/HISTORY | 170 | 0.32 | 0.465 [0.38, 0.55] | 0.465 | 0.000 | 0.000 | 216 / 1029 / 1938 |
| 8BT | rtv_bench/Action-TP/RECENT | 170 | 0.32 | 0.647 [0.56, 0.73] | 0.647 | 0.000 | 0.000 | 198 / 1476 / 4858 |
| 8BT | rtv_bench/Action-VP/HISTORY | 140 | 0.34 | 0.507 [0.43, 0.59] | 0.507 | 0.000 | 0.000 | 172 / 938 / 2556 |
| 8BT | rtv_bench/Action-VP/RECENT | 140 | 0.34 | 0.600 [0.52, 0.68] | 0.600 | 0.000 | 0.000 | 380 / 1523 / 2614 |
| 8BT | rtv_bench/Event-FP/HISTORY | 119 | 0.30 | 0.538 [0.45, 0.61] | 0.538 | 0.000 | 0.000 | 140 / 557 / 2189 |
| 8BT | rtv_bench/Event-FP/RECENT | 119 | 0.30 | 0.697 [0.63, 0.77] | 0.697 | 0.000 | 0.000 | 116 / 790 / 2794 |
| 8BT | rtv_bench/Event-GU/HISTORY | 247 | 0.27 | 0.486 [0.43, 0.55] | 0.486 | 0.000 | 0.000 | 420 / 1776 / 5317 |
| 8BT | rtv_bench/Event-GU/RECENT | 247 | 0.27 | 0.530 [0.48, 0.58] | 0.530 | 0.000 | 0.000 | 313 / 2029 / 4943 |
| 8BT | rtv_bench/Event-IA/HISTORY | 126 | 0.34 | 0.587 [0.49, 0.69] | 0.587 | 0.000 | 0.000 | 98 / 703 / 2597 |
| 8BT | rtv_bench/Event-IA/RECENT | 126 | 0.34 | 0.651 [0.54, 0.75] | 0.651 | 0.000 | 0.000 | 110 / 962 / 4462 |
| 8BT | rtv_bench/Event-PU/HISTORY | 127 | 0.28 | 0.543 [0.46, 0.64] | 0.543 | 0.000 | 0.000 | 120 / 616 / 3465 |
| 8BT | rtv_bench/Event-PU/RECENT | 127 | 0.28 | 0.598 [0.52, 0.68] | 0.598 | 0.000 | 0.000 | 117 / 722 / 2543 |
| 8BT | rtv_bench/Event-SP/HISTORY | 112 | 0.28 | 0.536 [0.44, 0.63] | 0.536 | 0.000 | 0.000 | 140 / 1430 / 5020 |
| 8BT | rtv_bench/Event-SP/RECENT | 112 | 0.28 | 0.741 [0.66, 0.83] | 0.741 | 0.000 | 0.000 | 108 / 845 / 2608 |
| 8BT | rtv_bench/Event-SR/HISTORY | 214 | 0.27 | 0.528 [0.48, 0.58] | 0.528 | 0.000 | 0.000 | 194 / 817 / 3577 |
| 8BT | rtv_bench/Event-SR/RECENT | 214 | 0.27 | 0.617 [0.55, 0.68] | 0.617 | 0.000 | 0.000 | 360 / 1319 / 3529 |
| 8BT | rtv_bench/Event-TP/HISTORY | 114 | 0.29 | 0.561 [0.46, 0.67] | 0.561 | 0.000 | 0.000 | 137 / 665 / 6294 |
| 8BT | rtv_bench/Event-TP/RECENT | 114 | 0.29 | 0.746 [0.67, 0.82] | 0.746 | 0.000 | 0.000 | 135 / 867 / 1746 |
| 8BT | rtv_bench/Event-VP/HISTORY | 458 | 0.33 | 0.616 [0.56, 0.67] | 0.616 | 0.002 | 0.002 | 120 / 641 / 16384 |
| 8BT | rtv_bench/Event-VP/RECENT | 458 | 0.33 | 0.664 [0.61, 0.72] | 0.664 | 0.000 | 0.002 | 147 / 861 / 9953 |
| 8BT | rtv_bench/Object-FP/HISTORY | 102 | 0.35 | 0.578 [0.50, 0.66] | 0.578 | 0.000 | 0.000 | 135 / 1091 / 4989 |
| 8BT | rtv_bench/Object-FP/RECENT | 102 | 0.35 | 0.755 [0.69, 0.82] | 0.755 | 0.000 | 0.000 | 162 / 1493 / 3263 |
| 8BT | rtv_bench/Object-GU/HISTORY | 135 | 0.25 | 0.541 [0.48, 0.61] | 0.541 | 0.000 | 0.000 | 198 / 1165 / 3086 |
| 8BT | rtv_bench/Object-GU/RECENT | 135 | 0.25 | 0.541 [0.46, 0.61] | 0.541 | 0.000 | 0.000 | 256 / 1327 / 3439 |
| 8BT | rtv_bench/Object-IA/HISTORY | 87 | 0.28 | 0.517 [0.40, 0.61] | 0.517 | 0.000 | 0.000 | 429 / 998 / 2753 |
| 8BT | rtv_bench/Object-IA/RECENT | 87 | 0.28 | 0.609 [0.55, 0.68] | 0.609 | 0.000 | 0.000 | 433 / 1060 / 3234 |
| 8BT | rtv_bench/Object-PU/HISTORY | 270 | 0.26 | 0.656 [0.61, 0.71] | 0.656 | 0.000 | 0.000 | 92 / 542 / 3787 |
| 8BT | rtv_bench/Object-PU/RECENT | 270 | 0.26 | 0.741 [0.69, 0.79] | 0.741 | 0.000 | 0.000 | 96 / 522 / 3905 |
| 8BT | rtv_bench/Object-SP/HISTORY | 200 | 0.29 | 0.715 [0.66, 0.77] | 0.715 | 0.000 | 0.010 | 100 / 835 / 5109 |
| 8BT | rtv_bench/Object-SP/RECENT | 200 | 0.29 | 0.775 [0.72, 0.83] | 0.775 | 0.000 | 0.000 | 86 / 538 / 2078 |
| 8BT | rtv_bench/Object-SR/HISTORY | 161 | 0.26 | 0.534 [0.49, 0.57] | 0.534 | 0.000 | 0.000 | 100 / 952 / 3703 |
| 8BT | rtv_bench/Object-SR/RECENT | 161 | 0.26 | 0.609 [0.54, 0.67] | 0.609 | 0.000 | 0.000 | 132 / 939 / 4590 |
| 8BT | rtv_bench/Object-TP/HISTORY | 303 | 0.28 | 0.650 [0.59, 0.70] | 0.647 | 0.000 | 0.010 | 103 / 791 / 2612 |
| 8BT | rtv_bench/Object-TP/RECENT | 303 | 0.28 | 0.752 [0.69, 0.81] | 0.746 | 0.000 | 0.013 | 106 / 856 / 4613 |
| 8BT | rtv_bench/Object-VP/HISTORY | 141 | 0.28 | 0.617 [0.53, 0.70] | 0.610 | 0.000 | 0.007 | 101 / 754 / 2569 |
| 8BT | rtv_bench/Object-VP/RECENT | 141 | 0.28 | 0.738 [0.67, 0.81] | 0.738 | 0.000 | 0.007 | 116 / 911 / 2527 |
| 32BT | ovo_bench/ACR/HISTORY | 109 | 0.25 | 0.725 [0.62, 0.82] | 0.725 | 0.000 | 0.000 | 111 / 329 / 2055 |
| 32BT | ovo_bench/ACR/RECENT | 109 | 0.25 | 0.890 [0.83, 0.94] | 0.890 | 0.000 | 0.000 | 118 / 298 / 3514 |
| 32BT | ovo_bench/ASI/HISTORY | 148 | 0.25 | 0.838 [0.78, 0.89] | 0.838 | 0.000 | 0.000 | 147 / 463 / 1927 |
| 32BT | ovo_bench/ASI/RECENT | 148 | 0.25 | 0.689 [0.61, 0.76] | 0.689 | 0.000 | 0.000 | 222 / 811 / 3440 |
| 32BT | ovo_bench/ATR/HISTORY | 116 | 0.25 | 0.802 [0.70, 0.89] | 0.802 | 0.000 | 0.000 | 84 / 203 / 828 |
| 32BT | ovo_bench/ATR/RECENT | 116 | 0.25 | 0.888 [0.83, 0.94] | 0.888 | 0.000 | 0.000 | 81 / 225 / 1255 |
| 32BT | ovo_bench/CRR/HISTORY | 240 | 0.50 | 0.567 [0.51, 0.65] | 0.567 | 0.000 | 0.000 | 172 / 549 / 2158 |
| 32BT | ovo_bench/CRR/RECENT | 240 | 0.50 | 0.442 [0.42, 0.47] | 0.442 | 0.000 | 0.000 | 143 / 610 / 1879 |
| 32BT | ovo_bench/EPM/HISTORY | 297 | 0.27 | 0.613 [0.55, 0.68] | 0.613 | 0.003 | 0.003 | 89 / 246 / 16384 |
| 32BT | ovo_bench/EPM/RECENT | 297 | 0.27 | 0.596 [0.55, 0.65] | 0.596 | 0.000 | 0.000 | 107 / 455 / 1659 |
| 32BT | ovo_bench/FPD/HISTORY | 101 | 0.25 | 0.723 [0.62, 0.82] | 0.723 | 0.000 | 0.000 | 129 / 533 / 3791 |
| 32BT | ovo_bench/FPD/RECENT | 101 | 0.25 | 0.752 [0.66, 0.84] | 0.752 | 0.000 | 0.000 | 139 / 354 / 2544 |
| 32BT | ovo_bench/HLD/HISTORY | 186 | 0.28 | 0.484 [0.41, 0.56] | 0.484 | 0.000 | 0.000 | 156 / 472 / 1757 |
| 32BT | ovo_bench/HLD/RECENT | 186 | 0.28 | 0.694 [0.62, 0.77] | 0.694 | 0.000 | 0.000 | 158 / 392 / 2019 |
| 32BT | ovo_bench/OCR/HISTORY | 149 | 0.25 | 0.819 [0.75, 0.89] | 0.819 | 0.000 | 0.000 | 69 / 231 / 2616 |
| 32BT | ovo_bench/OCR/RECENT | 149 | 0.25 | 0.953 [0.92, 0.98] | 0.953 | 0.000 | 0.000 | 76 / 207 / 3450 |
| 32BT | ovo_bench/OJR/HISTORY | 184 | 0.25 | 0.750 [0.68, 0.82] | 0.745 | 0.000 | 0.005 | 78 / 327 / 4449 |
| 32BT | ovo_bench/OJR/RECENT | 184 | 0.25 | 0.842 [0.79, 0.89] | 0.837 | 0.000 | 0.005 | 82 / 237 / 3973 |
| 32BT | ovo_bench/REC/HISTORY | 698 | — | 0.460 [0.39, 0.54] | 0.460 | 0.003 | 0.003 | 881 / 4004 / 16384 |
| 32BT | ovo_bench/REC/RECENT | 698 | — | 0.198 [0.16, 0.24] | 0.198 | 0.000 | 0.000 | 410 / 1578 / 4802 |
| 32BT | ovo_bench/SSR/HISTORY | 629 | 0.50 | 0.750 [0.71, 0.79] | 0.750 | 0.000 | 0.000 | 109 / 596 / 3832 |
| 32BT | ovo_bench/SSR/RECENT | 629 | 0.50 | 0.747 [0.71, 0.79] | 0.747 | 0.000 | 0.000 | 96 / 363 / 1967 |
| 32BT | ovo_bench/STU/HISTORY | 178 | 0.25 | 0.601 [0.52, 0.68] | 0.601 | 0.000 | 0.000 | 130 / 398 / 3012 |
| 32BT | ovo_bench/STU/RECENT | 178 | 0.25 | 0.770 [0.69, 0.84] | 0.770 | 0.000 | 0.000 | 124 / 451 / 4380 |
| 32BT | rtv_bench/Action-FP/HISTORY | 365 | 0.35 | 0.633 [0.59, 0.68] | 0.633 | 0.000 | 0.000 | 149 / 430 / 1950 |
| 32BT | rtv_bench/Action-FP/RECENT | 365 | 0.35 | 0.682 [0.64, 0.72] | 0.682 | 0.000 | 0.000 | 123 / 545 / 2306 |
| 32BT | rtv_bench/Action-GU/HISTORY | 92 | 0.28 | 0.598 [0.52, 0.67] | 0.598 | 0.000 | 0.000 | 180 / 857 / 4648 |
| 32BT | rtv_bench/Action-GU/RECENT | 92 | 0.28 | 0.620 [0.53, 0.72] | 0.620 | 0.000 | 0.000 | 171 / 1160 / 2794 |
| 32BT | rtv_bench/Action-IA/HISTORY | 339 | 0.34 | 0.637 [0.60, 0.68] | 0.637 | 0.000 | 0.000 | 156 / 535 / 8848 |
| 32BT | rtv_bench/Action-IA/RECENT | 339 | 0.34 | 0.720 [0.67, 0.77] | 0.720 | 0.000 | 0.000 | 178 / 617 / 1840 |
| 32BT | rtv_bench/Action-PU/HISTORY | 148 | 0.36 | 0.642 [0.59, 0.70] | 0.642 | 0.000 | 0.000 | 140 / 476 / 961 |
| 32BT | rtv_bench/Action-PU/RECENT | 148 | 0.36 | 0.757 [0.69, 0.82] | 0.757 | 0.000 | 0.000 | 152 / 762 / 3030 |
| 32BT | rtv_bench/Action-SP/HISTORY | 225 | 0.33 | 0.480 [0.42, 0.54] | 0.480 | 0.000 | 0.000 | 321 / 944 / 3653 |
| 32BT | rtv_bench/Action-SP/RECENT | 225 | 0.33 | 0.587 [0.53, 0.64] | 0.587 | 0.000 | 0.000 | 318 / 956 / 3510 |
| 32BT | rtv_bench/Action-SR/HISTORY | 213 | 0.29 | 0.441 [0.39, 0.50] | 0.441 | 0.000 | 0.000 | 303 / 688 / 1720 |
| 32BT | rtv_bench/Action-SR/RECENT | 213 | 0.29 | 0.474 [0.41, 0.54] | 0.474 | 0.000 | 0.000 | 369 / 998 / 4235 |
| 32BT | rtv_bench/Action-TP/HISTORY | 170 | 0.32 | 0.482 [0.40, 0.56] | 0.482 | 0.006 | 0.006 | 208 / 683 / 16384 |
| 32BT | rtv_bench/Action-TP/RECENT | 170 | 0.32 | 0.718 [0.64, 0.79] | 0.718 | 0.000 | 0.000 | 134 / 1050 / 3013 |
| 32BT | rtv_bench/Action-VP/HISTORY | 140 | 0.34 | 0.564 [0.49, 0.64] | 0.564 | 0.000 | 0.000 | 262 / 972 / 1816 |
| 32BT | rtv_bench/Action-VP/RECENT | 140 | 0.34 | 0.643 [0.57, 0.73] | 0.643 | 0.000 | 0.000 | 270 / 789 / 2141 |
| 32BT | rtv_bench/Event-FP/HISTORY | 119 | 0.30 | 0.597 [0.53, 0.66] | 0.597 | 0.000 | 0.000 | 132 / 369 / 1484 |
| 32BT | rtv_bench/Event-FP/RECENT | 119 | 0.30 | 0.689 [0.61, 0.77] | 0.689 | 0.000 | 0.000 | 113 / 529 / 2867 |
| 32BT | rtv_bench/Event-GU/HISTORY | 247 | 0.27 | 0.538 [0.48, 0.60] | 0.538 | 0.000 | 0.000 | 362 / 1791 / 8825 |
| 32BT | rtv_bench/Event-GU/RECENT | 247 | 0.27 | 0.526 [0.47, 0.58] | 0.526 | 0.000 | 0.000 | 236 / 1551 / 4478 |
| 32BT | rtv_bench/Event-IA/HISTORY | 126 | 0.34 | 0.635 [0.53, 0.75] | 0.635 | 0.008 | 0.008 | 109 / 405 / 16384 |
| 32BT | rtv_bench/Event-IA/RECENT | 126 | 0.34 | 0.690 [0.59, 0.80] | 0.690 | 0.000 | 0.000 | 124 / 536 / 4085 |
| 32BT | rtv_bench/Event-PU/HISTORY | 127 | 0.28 | 0.591 [0.50, 0.68] | 0.591 | 0.000 | 0.000 | 111 / 562 / 2599 |
| 32BT | rtv_bench/Event-PU/RECENT | 127 | 0.28 | 0.630 [0.56, 0.69] | 0.630 | 0.000 | 0.000 | 100 / 558 / 3188 |
| 32BT | rtv_bench/Event-SP/HISTORY | 112 | 0.28 | 0.625 [0.54, 0.71] | 0.625 | 0.000 | 0.000 | 142 / 689 / 4134 |
| 32BT | rtv_bench/Event-SP/RECENT | 112 | 0.28 | 0.732 [0.66, 0.81] | 0.732 | 0.000 | 0.000 | 117 / 504 / 1934 |
| 32BT | rtv_bench/Event-SR/HISTORY | 214 | 0.27 | 0.598 [0.53, 0.66] | 0.598 | 0.000 | 0.000 | 184 / 768 / 2870 |
| 32BT | rtv_bench/Event-SR/RECENT | 214 | 0.27 | 0.682 [0.62, 0.75] | 0.682 | 0.000 | 0.000 | 220 / 845 / 6040 |
| 32BT | rtv_bench/Event-TP/HISTORY | 114 | 0.29 | 0.570 [0.47, 0.69] | 0.561 | 0.000 | 0.009 | 98 / 525 / 5163 |
| 32BT | rtv_bench/Event-TP/RECENT | 114 | 0.29 | 0.737 [0.65, 0.82] | 0.737 | 0.000 | 0.000 | 101 / 527 / 1377 |
| 32BT | rtv_bench/Event-VP/HISTORY | 458 | 0.33 | 0.666 [0.61, 0.71] | 0.666 | 0.000 | 0.000 | 163 / 586 / 5427 |
| 32BT | rtv_bench/Event-VP/RECENT | 458 | 0.33 | 0.703 [0.65, 0.76] | 0.703 | 0.000 | 0.000 | 134 / 548 / 2063 |
| 32BT | rtv_bench/Object-FP/HISTORY | 102 | 0.35 | 0.627 [0.56, 0.70] | 0.627 | 0.000 | 0.000 | 151 / 458 / 2774 |
| 32BT | rtv_bench/Object-FP/RECENT | 102 | 0.35 | 0.755 [0.70, 0.81] | 0.755 | 0.000 | 0.000 | 118 / 863 / 1644 |
| 32BT | rtv_bench/Object-GU/HISTORY | 135 | 0.25 | 0.600 [0.52, 0.68] | 0.600 | 0.000 | 0.000 | 200 / 1304 / 5363 |
| 32BT | rtv_bench/Object-GU/RECENT | 135 | 0.25 | 0.570 [0.50, 0.63] | 0.570 | 0.000 | 0.000 | 144 / 964 / 2127 |
| 32BT | rtv_bench/Object-IA/HISTORY | 87 | 0.28 | 0.575 [0.49, 0.65] | 0.575 | 0.000 | 0.000 | 248 / 841 / 1889 |
| 32BT | rtv_bench/Object-IA/RECENT | 87 | 0.28 | 0.621 [0.55, 0.68] | 0.621 | 0.000 | 0.000 | 272 / 813 / 1786 |
| 32BT | rtv_bench/Object-PU/HISTORY | 270 | 0.26 | 0.696 [0.64, 0.76] | 0.696 | 0.000 | 0.000 | 93 / 413 / 1624 |
| 32BT | rtv_bench/Object-PU/RECENT | 270 | 0.26 | 0.789 [0.74, 0.84] | 0.789 | 0.000 | 0.000 | 88 / 323 / 2628 |
| 32BT | rtv_bench/Object-SP/HISTORY | 200 | 0.29 | 0.750 [0.70, 0.81] | 0.740 | 0.000 | 0.020 | 83 / 509 / 4738 |
| 32BT | rtv_bench/Object-SP/RECENT | 200 | 0.29 | 0.830 [0.78, 0.88] | 0.820 | 0.000 | 0.025 | 82 / 318 / 1796 |
| 32BT | rtv_bench/Object-SR/HISTORY | 161 | 0.26 | 0.609 [0.56, 0.67] | 0.609 | 0.000 | 0.000 | 133 / 520 / 2130 |
| 32BT | rtv_bench/Object-SR/RECENT | 161 | 0.26 | 0.683 [0.60, 0.76] | 0.683 | 0.000 | 0.000 | 126 / 738 / 3539 |
| 32BT | rtv_bench/Object-TP/HISTORY | 303 | 0.28 | 0.680 [0.63, 0.73] | 0.673 | 0.003 | 0.017 | 115 / 631 / 16384 |
| 32BT | rtv_bench/Object-TP/RECENT | 303 | 0.28 | 0.749 [0.70, 0.80] | 0.743 | 0.000 | 0.020 | 102 / 633 / 3264 |
| 32BT | rtv_bench/Object-VP/HISTORY | 141 | 0.28 | 0.631 [0.53, 0.72] | 0.617 | 0.000 | 0.035 | 108 / 656 / 3510 |
| 32BT | rtv_bench/Object-VP/RECENT | 141 | 0.28 | 0.773 [0.70, 0.85] | 0.759 | 0.000 | 0.035 | 113 / 635 / 2492 |
