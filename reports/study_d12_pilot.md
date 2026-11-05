# StudyD12-pilot: 50-item time-series pilot on the D-series vLLM stack

**E-id:** StudyD12-pilot (pre-registered 2026-11-04 ~15:25, before any GPU run). It replaces the flash pilot of StudyD12-prep: the A6000 was busy with another user, and flash's vLLM 0.8.5 can't load Qwen3-VL.

**Run:** h100nvl GPU 2, 2026-11-04 17:53–17:58. **Status: COMPLETE. ALL NUMBERS INDICATIVE (n = 50 per dataset).**

**Stack:** vLLM 0.31.0 (FA3, max_model_len 32,768, prefix + processor cache off).

| | |
|---|---|
| models | Qwen3-VL-4B-Instruct @ebb281ec, Qwen3-VL-32B-Instruct @0cfaf481 |
| decoding | greedy, max_tokens 512, request seed 0, concurrency 8 |
| items | the prep manifest's 50-item sets (seed 0) |
| prompts | `prompt_text` / `prompt_plot` verbatim |
| PLOT arm | the committed PNG sent first, then the prompt |

**WISDM and MIT-BIH are OUR OWN task formulations:**
- WISDM: 18-way activity classification from a 10 s, 3-axis phone accelerometer window.
- MIT-BIH: 5-way AAMI beat classification from a 1 s MLII window.

STARK questions and answers are the benchmark's own, verbatim, and only the text arm is run (the series is inside the question).

## Results (observations)

Accuracy with Wilson 95 % CI.

| dataset / arm | model | accuracy [Wilson 95 %] | majority | chance | no-parse failures (truncated at 512) | empty | prompt tokens median / max |
|---|---|---|---|---|---|---|---|
| WISDM / TEXT | 4B | 4 % [1, 13] | 6 % | 5.6 % | 0 | 0 | 3,851 / 4,071 |
| WISDM / TEXT | 32B | 8 % [3, 19] | 6 % | 5.6 % | 0 | 0 | 3,851 / 4,071 |
| WISDM / PLOT | 4B | 6 % [2, 16] | 6 % | 5.6 % | 0 | 0 | 490 / 490 |
| WISDM / PLOT | 32B | 8 % [3, 19] | 6 % | 5.6 % | **7 (7)** | 0 | 490 / 490 |
| MIT-BIH / TEXT | 4B | 24 % [14, 37] | 20 % | 20 % | 0 | 0 | 2,785 / 2,785 |
| MIT-BIH / TEXT | 32B | 24 % [14, 37] | 20 % | 20 % | 0 | 0 | 2,785 / 2,785 |
| MIT-BIH / PLOT | 4B | 20 % [11, 33] | 20 % | 20 % | 0 | 0 | 507 / 507 |
| MIT-BIH / PLOT | 32B | 20 % [11, 33] | 20 % | 20 % | 0 | 0 | 507 / 507 |
| STARK / TEXT, categorical (34) | 4B | 88 % [73, 95] | 53 % | 50 % | 0 | 0 | 535 / 2,118 (all 50) |
| STARK / TEXT, categorical (34) | 32B | 74 % [57, 85] | 53 % | 50 % | **7 (7)** | 0 | 535 / 2,118 |

**STARK continuous items (16; no accuracy defined):** both models parsed 16/16, with an answer of the right shape in 10/16. The RMSE per item is in the results JSON.

**Answer distributions** (option numbers):
- **MIT-BIH PLOT:** both models answer "1" (N) on 50/50.
- **MIT-BIH TEXT:** "1" on 36/50 (4B) and 44/50 (32B).
- **WISDM PLOT, 4B:** "5" (standing) on 48/50.
- **WISDM TEXT:** "5" on 30/50 (4B) and 23/50 (32B).

**32B's failures are all truncations.** It reasons step by step and is cut off at the pre-registered 512 tokens before the answer tag (`finish_reason: length`; median completion 217–281 tokens on those arms vs 11–12 elsewhere). On the 27 STARK categorical items 32B did answer, 25 are correct; this is reported as context only and not substituted for the pre-registered number.

**Checks:**
- **Prompt tokens:** equal to the prep's 4B processor count for every WISDM / MIT-BIH request (200/200 per model).
- **Errors:** 0 HTTP errors and 0 transport errors.
- **Server logs:** no errors.

## Interpretation (separate from the observations)

- **WISDM and MIT-BIH (our formulations): neither model reads the series in either form.** Accuracy sits at chance or majority, and the answers collapse onto one or two options. So no TEXT vs PLOT difference can be measured.
- **STARK categorical items (the benchmark's own): well above chance and majority for 4B.** 32B's lower number comes from truncation at 512 tokens, not from wrong answers among those it completed.
- **Before any main sweep:** the 512-token cap is binding for 32B on STARK and WISDM-PLOT, so a main run with 32B needs a larger cap (or Thinking with its own budget). This is a design input, not a result.

## H100 time for a main sweep with 32B Thinking (T 1.0, top_p 0.95, top_k 20, max 16,384); estimate, NOT run

| assumed median completion | hours per 1,000 items (concurrency 8) |
|---|---|
| 570 tokens | ≈ 0.9 h |
| 2,000 tokens | ≈ 3.1 h |
| 4,000 tokens | ≈ 6.2 h |

**Basis:** StudyD9's measured 32B-Thinking throughput on the same stack (801 items per seed in ~43 min at concurrency 8, median 570 completion tokens; ~3.2 s per item) and StudyD10's ~43 tokens/s single-request decode. Prompt sizes here (0.5–4k tokens) are comparable.

Completion length on these tasks is unknown and dominates the estimate. A ~30-item 32B-Thinking timing probe would pin it down.

## Results consistency check

| # | check | result |
|---|---|---|
| 1 | Cross-check | **PASS.** Prompt tokens equal the prep's independent HF-processor count (400/400 WISDM / MIT-BIH requests). |
| 2 | Plausibility | n/a (no latency claim). |
| 3 | Distribution | **FLAGGED.** Prediction collapse onto one option (MIT-BIH PLOT 50/50 "1") is reported as an observation, not hidden. |
| 4 | Definitions | **PASS.** Scoring as pre-registered; truncations count as failures. |
| 5 | Claim linkage | Feasibility screen for the time-series modality; no FORMULATION claim tested. |
| 6 | Proxy validity | n/a. |

**Mechanism verification:** n/a (feasibility; no causal claim).

## Files

| file | contents |
|---|---|
| `experiments/ts/study_d12_pilot_vllm.py` | runner |
| `experiments/ts/study_d12_pilot_analyse.py` | analysis |
| `results/ts/study_d12_pilot/study_d12_pilot_requests_h100nvl.jsonl` | per-request rows |
| `results/ts/study_d12_pilot/study_d12_pilot_run_meta_h100nvl.json` | run meta |
| `results/ts/study_d12_pilot/study_d12_pilot_results_h100nvl.json` | analysis results |
