# StudyD9: 32B image Thinking vs Instruct on one matched vLLM stack

**E-id:** StudyD9 (pre-registered 2026-11-04, before any GPU run). **Host:** h100nvl GPU 2, run 11:23–12:54 on 2026-11-04.
**Status:** COMPLETE.

**Same for both arms:** vLLM 0.31.0 (FA3, prefix caching off, processor cache off), concurrency 8, the earlier arms' prompts and parsers, and the images pre-resized exactly as the HF arms did.

| | Instruct (I) | Thinking (T0, T1) |
|---|---|---|
| model | Qwen3-VL-32B-Instruct @0cfaf481 | Qwen3-VL-32B-Thinking @7edd10ff |
| decoding | greedy, max 512 | model-card VL sampling: T 1.0, top_p 0.95, top_k 20, repetition 1.0, presence 0, min_p 0; max 16,384 |
| request seed | — | 0 (T0) and 1 (T1), one per run |

**Input / stack / decoding match:** input and stack match between the arms; decoding differs by design (greedy vs sampled).

**Earlier Thinking T0.6 arms (StudyR arm D, StudyS2 arm D) are CONFOUNDED and are not compared here.**

## Results (observations)

Accuracy in %. Differences in pp, paired bootstrap over questions (2,000, seed 0).

| benchmark | n | I | T0 | T1 | T mean | T0 − I | T1 − I | Tmean − I | T0 − T1 |
|---|---|---|---|---|---|---|---|---|---|
| ERQA | 400 | 46.50 | 47.50 | 49.25 | 48.38 | +1.00 [−3.50, +5.25] | +2.75 [−2.00, +7.50] | +1.88 [−2.13, +6.00] | −1.75 [−5.50, +2.00] |
| MV-RoboBench | 401 | 46.88 | 46.38 | 45.64 | 46.01 | −0.50 [−5.49, +4.74] | −1.25 [−6.49, +4.24] | −0.87 [−5.61, +4.12] | +0.75 [−3.49, +5.24] |
| pooled | 801 | 46.69 | 46.94 | 47.44 | 47.19 | +0.25 [−3.00, +3.75] | +0.75 [−2.75, +4.24] | **+0.50 [−2.62, +3.81]** | −0.50 [−3.37, +2.37] |

**Thinking runs (both seeds):**
- **Empty answers:** 0.
- **Runaways:** 0. Every response finished with `stop`, and `</think>` closed in 1,602/1,602.
- **Completion tokens:** median 570, max 10,128 (cap 16,384).

**Instruct:** 0 empty answers, 0 runaways.

**Errors:** 0 in all three runs.

**Prompt tokens:**
- **Instruct:** equal to the HF processor's count for every question (801/801).
- **Thinking:** HF count + 2 for every question (1,602/1,602), the `<think>\n` the Thinking chat template appends. The inputs are otherwise identical.

## Stack check: vLLM Instruct vs the earlier HF Instruct arm C (same questions, prompts, greedy, max 512)

These comparisons are **BACKEND-MISMATCHED** (vLLM FA3 vs HF SDPA / FA2). Prompt tokens are equal on every question.

| benchmark | earlier arm | HF acc | vLLM acc | vLLM − HF [CI] | letter agreement |
|---|---|---|---|---|---|
| ERQA | StudyR C (SDPA) | 46.75 | 46.50 | −0.25 | 98.5 % |
| ERQA | StudyR-fa2 C | 46.75 | 46.50 | −0.25 | 98.3 % |
| MV-RoboBench | StudyS2 C (SDPA) | 47.88 | 46.88 | −1.00 | 97.3 % |
| MV-RoboBench | StudyS2-fa2 C | 48.13 | 46.88 | −1.25 | 97.3 % |

95 % CIs for vLLM − HF: ERQA SDPA [−1.25, +0.50], ERQA FA2 [−1.50, +0.75], MV-RoboBench SDPA [−2.49, +0.50], MV-RoboBench FA2 [−2.49, 0.00]. The last one touches 0 at its upper bound.

## Interpretation (separate from the observations)

- **No measurable difference between Thinking and Instruct** on these image benchmarks at 32B on a matched stack. The pooled difference is +0.5 pp [−2.6, +3.8].
- **The two Thinking seeds differ from each other** by as much as Thinking differs from Instruct (T0 − T1 −0.5 pp pooled).
- **The cost difference is large.** Thinking generates a median of 570 tokens against 1–2 for Instruct; StudyD10 measures the latency.
- **The stack check passes.** Moving Instruct from HF to vLLM changes accuracy by ≤ 1.25 pp and changes ≤ 2.7 % of letters, all within noise.
- **This is a measurement, not a causal test**, so mechanism verification is n/a.

## Results consistency check

| # | check | result |
|---|---|---|
| 1 | Cross-check | **PASS.** Instruct reproduces arm C within 1.25 pp (table above). |
| 2 | Plausibility | **PASS.** The Thinking runs took ~43 min per seed for 801 requests at concurrency 8; no latency headline here. |
| 3 | Distribution | **PASS.** Completion tokens spread 1–10,128; the two seeds differ (letter agreement in results JSON). |
| 4 | Definitions | **PASS.** Parsers are verbatim from `study_r_erqa.extract_letter` (A–D) and StudyS2's (A–E); the answer is the text after `</think>`; a runaway is `finish_reason` length or `</think>` never closed. |
| 5 | Claim linkage | Bears on the cloud-tier choice (Thinking vs Instruct as the escalation target): on images, Thinking buys no accuracy here. |
| 6 | Proxy validity | n/a. |

## Files

| file | contents |
|---|---|
| `experiments/erqa/study_d9_inputs.py` | inputs (CPU, HF venv) |
| `experiments/erqa/study_d9_vllm.py` | runner |
| `experiments/erqa/study_d9_analyse.py` | analysis |
| `results/erqa/study_d9/study_d9_inputs_manifest.jsonl` | inputs manifest |
| `results/erqa/study_d9/study_d9_requests_h100nvl.jsonl.gz` | per-request rows |
| `results/erqa/study_d9/study_d9_run_meta_h100nvl.json` | run meta |
| `results/erqa/study_d9/study_d9_results_h100nvl.json` | analysis results |
