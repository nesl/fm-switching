# Study M — Plan: Reasoning Gate on Sensor Time-Series

**Date:** 2026-10-01  
**Status:** SMOKE TEST APPROVED — pending commit before inference  
**Pre-registered:** `research/EXPERIMENTS.md` row StudyM  
**Research question:** Does reasoning mode (thinking on) improve accuracy on a real CPS sensor time-series workload vs instruct/no-think at deployable 8B scale?

---

## Current scope: Smoke test (StudyM-smoke)

Full-scale plan (11,370 trials, 4 arms, SenTSR + TSRBench) is **deferred, not cancelled** (see §8). The smoke test establishes think-token rates, approximate accuracy levels, and whether to proceed to the full study.

**Smoke test scope:**
- SenTSR-Bench only, 30 of 110 series (seed=42), 3 questions each = 90 items
- Arms: T-OFF and T-ON only (vision arms deferred)
- 3 seeds per item = **540 trials total**
- TSRBench, ECG, and vision arms deferred

---

## 1. Dataset

### SenTSR-Bench

| field | value |
|---|---|
| arXiv | 2602.19455 (AISTATS 2026) |
| License | CC-BY-NC-4.0 |
| Download | HuggingFace `ZLHe0/SenTSR-Bench` — publicly available, no login required |
| Full dataset | 110 series × 3 stages = 330 4-option MCQ |
| Channels | 3: Acceleration, Velocity, Temperature |
| Series length | 123–170 hourly samples |
| Source domain | Real-world de-identified warehouse machine monitoring |

### Series selection (smoke test)

Selection: `numpy.random.default_rng(seed=42).choice(110, size=30, replace=False)`, sorted.

**Selected series indices (0-indexed, seed=42):**
```
[7, 8, 12, 17, 18, 36, 37, 43, 45, 47, 48, 49, 50, 54, 59,
 61, 63, 68, 71, 73, 75, 82, 83, 84, 86, 88, 89, 94, 96, 105]
```

Each selected series contributes 3 consecutive entries from the JSON (what_happened, how_happened, suggested_fix) at positions `series_idx * 3`, `series_idx * 3 + 1`, `series_idx * 3 + 2`.

Verified stage counts: 30 what_happened + 30 how_happened + 30 suggested_fix = 90 items total.

---

## 2. Models

| arm | model | HF id | cached | snapshot hash |
|---|---|---|---|---|
| T-OFF | Qwen3-8B | `Qwen/Qwen3-8B` | ✓ | `b968826d9c46dd6066d109eabc6255188de91218` |
| T-ON | Qwen3-8B | `Qwen/Qwen3-8B` | ✓ (same) | same as T-OFF |

Download target: `/mnt/ssd/hf_models/models--Qwen--Qwen3-8B/`

Vision arms (Qwen3-VL-8B-Instruct snap `0c351dd`, Qwen3-VL-8B-Thinking snap `92f3c4b`) are deferred.

---

## 3. Decoding (from Qwen3-8B model card, verbatim)

**Thinking mode (`enable_thinking=True`) — T-ON:**
> temperature=0.6, top_p=0.95, top_k=20, min_p=0

**Non-thinking mode (`enable_thinking=False`) — T-OFF:**
> temperature=0.7, top_p=0.8, top_k=20, min_p=0

The model card explicitly warns: *"DO NOT use greedy decoding, as it can lead to performance degradation and endless repetitions."* Optional `presence_penalty` 0–2 to reduce repetition — not applied by default; not used unless non-termination issues emerge.

**max_new_tokens:** 1,024 for T-OFF; 16,384 for T-ON. Budget hits are recorded as data, not stopped.

**Correction vs prior plan:** T-OFF `top_p` was recorded as 0.9 in the earlier draft; model card specifies **0.8**. Corrected here.

---

## 4. Encoding

Series serialized as plain text, one line per channel:
```
{ChannelName}: {v1:.4f}, {v2:.4f}, ..., {vN:.4f}
```
Token count: 1,132–1,260 tokens per series (within Qwen3-8B 32K context). No downsampling applied; encoding never depends on the question.

---

## 5. Prompts (pre-registered, quoted verbatim)

**T-OFF prompt:**
```
You are a sensor time series analysis expert for industrial warehouse monitoring.

The following multivariate time series records sensor readings over time:

{CHANNEL_NAME_1}: {v1:.4f}, {v2:.4f}, ...
{CHANNEL_NAME_2}: {v1:.4f}, {v2:.4f}, ...
{CHANNEL_NAME_3}: {v1:.4f}, {v2:.4f}, ...

Question: {QUESTION_TEXT}

Options:
A. {option_0}
B. {option_1}
C. {option_2}
D. {option_3}

Answer with a single letter (A, B, C, or D) on its own line.
```

**T-ON prompt:** Identical to T-OFF. No budget instruction added — repo finding (StudyJ3 §1) shows budget instructions are counterproductive. `enable_thinking=True` controls reasoning mode.

Both prompts use the `question` field verbatim from the JSON; options come from `options[0]`, `options[1]`, `options[2]`, `options[3]`. Ground truth: `correct_index` (0-indexed → A/B/C/D).

---

## 6. Trial Metrics (per trial)

`series_idx`, `entry_idx`, `stage` (what_happened/how_happened/suggested_fix), `arm` (T-OFF/T-ON), `seed`, `n_input_tokens`, `n_think_tokens`, `n_answer_tokens`, `think_closed` (bool — did `</think>` appear), `budget_hit` (bool — hit max_new_tokens), `parsed_answer` (A/B/C/D or null), `parse_status`, `correct` (bool), `total_latency_ms`, `model_snapshot`, `raw_output` (full model output string).

---

## 7. Pre-Registered Smoke-Test Decision Rule

**Primary metric:** item-level accuracy = mean correctness over 3 seeds. Paired comparison T-ON minus T-OFF on the 60 **reasoning items** (How Happened + Suggested Fix). Paired bootstrap 95% CI (10,000 resamples over items) + Wilcoxon signed-rank p-value.

| verdict | condition |
|---|---|
| **GO** | difference ≥ 10 pp AND CI excludes 0 AND T-OFF reasoning accuracy ≥ 35% |
| **NO-GO** | difference < 5 pp OR CI upper bound < 10 pp OR T-OFF reasoning accuracy ≤ 30% |
| **INCONCLUSIVE** | anything else — next step is scaling to all 110 series |

The full-scale 5 pp rule (EXPERIMENTS.md §Analyses B gate) is retained for the deferred full study and does **not** apply here.

**Descriptive (not gate):**
- Same paired comparison on 30 perception (What Happened) items
- Per-stage accuracy per arm with 95% Wilson CIs
- T-ON think tokens per stage: median, IQR, p90, max; budget-hit rate; non-termination rate
- Seed-to-seed correctness variance per item per arm
- Wall time, tok/s, per-trial latency

---

## 8. Required Descriptive Analyses (smoke test addendum)

These are required outputs alongside the GO/NO-GO gate. They do not modify the gate rule.

### A1. Flip structure

Using **majority vote over 3 seeds** per arm, classify each item into one of four cells: T-OFF-right/T-ON-right, T-OFF-wrong/T-ON-wrong, T-OFF-wrong→T-ON-right (T-ON helps), T-OFF-right→T-ON-wrong (T-ON hurts). Report McNemar's test on the discordant pairs (helped vs. hurt). Report the same 2×2 table for each seed individually to show how much flipping is seed noise. Report reasoning items (How+Fix) and perception items (What Happened) separately.

### A2. Seed noise floor

For each arm independently, compute the fraction of items whose correctness differs across its own 3 seeds. Compare the within-arm churn rate to the cross-arm flip rate from A1, as a baseline for how much of the T-ON/T-OFF difference exceeds within-arm noise.

### A3. Variance decomposition of T-ON think tokens

Fit a linear mixed-effects model: `log(think_tokens) ~ stage + (1|series) + (1|item)`, with seed as the residual. Report the share of variance attributable to: stage (fixed), series (random intercept), item (random intercept), and seed (residual). Repeat restricted to items where T-ON helped (wrong→right by majority vote). Budget-hit traces are treated as right-censored at `max_new_tokens`; state how many were censored and whether they are included or excluded from the model (use exclusion if censoring >10% of T-ON traces; state the choice).

### A4. Think tokens in helped items

Within the items where T-ON helped (wrong→right by majority vote), report think-token median, IQR, and range. Report whether think tokens are higher in helped items vs. items both arms got right (Wilcoxon one-sided, not a gate — descriptive only). Do not draw causal conclusions; report the numbers.

---

## 9. Deferred Full-Scale Plan (not cancelled)  <!-- was §8 before addendum -->

The full-scale study (11,370 trials, 4 arms including vision, SenTSR + TSRBench physical-sensor subset) is deferred pending smoke-test results. Full scope from the original Step 0 audit:

- SenTSR-Bench: all 110 series × 3 stages = 330 items
- TSRBench text-feasible physical-sensor: HAR (n=150) + River (n=300) = 450 items
- TSRBench vision-only: ECG (n=335, excluded from text arms — ~70K tokens)
- Vision arms: Qwen3-VL-8B-Instruct (`0c351dd`) and Qwen3-VL-8B-Thinking (`92f3c4b`), cached
- GPU time: 62–196h (stop condition; requires pilot confirmation before proceeding)

Resume this plan if the smoke test returns GO or INCONCLUSIVE.

---

## 10. Stop Conditions

- Stop if projected runtime exceeds 12h before starting
- Stop and report any change to prompts, encoding, item selection, or arms before applying it
- Never run git add, commit, push, or any history-altering git command

---

## 11. Output Files

| file | status |
|---|---|
| `reports/study_m_plan.md` | this file |
| `experiments/ts/study_m_smoke.py` | to be written after commit |
| `results/ts/study_m_smoke/study_m_smoke_trials.jsonl` | after inference |
| `reports/study_m_smoke_results.md` | after analysis |
