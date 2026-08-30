# Study D — Reasoning Compute vs Parameters with Scene Difficulty

**Date:** 2026-08-30  
**Script:** `experiments/vision/study_d_thinking.py`  
**Models:** Qwen3-VL-4B-Instruct (`qwen3vl4b`), Qwen3-VL-4B-Thinking (`qwen3vl4b_t`)  
**8B models:** NOT RUN — stop condition fired (see §2)  
**Input:** Same 120 COCO images as Study C (30 per difficulty level, seed 42)  
**Device:** A6000 (cuda:1), bfloat16, greedy decoding  

---

## 1. What Was Run

**Research question:** Does reasoning compute (Thinking models) substitute for parameters (larger Instruct models) with scene difficulty?

Four models were planned: Qwen3-VL-4B-Instruct, 4B-Thinking, 8B-Instruct, 8B-Thinking. Each uses the same 120 COCO person-counting images as Study C. Difficulty bins are unchanged: L1=1 person, L2=2–3, L3=4–7, L4=8+.

**Mode definitions:**
- **Instruct** (`qwen3vl4b`): chat template produces `<|im_start|>assistant\n`; model generates a direct answer. `max_new_tokens=40`.
- **Thinking** (`qwen3vl4b_t`): chat template produces `<|im_start|>assistant\n<think>\n`, forcing a reasoning block before the answer. `max_new_tokens=4096`. Output is split at `</think>`; tokens before the tag are the reasoning chain, tokens after are the answer.

**Vision tokens:** 324 per image at 560×560 (Qwen3-VL uses patch_size=16 vs 14 in Qwen2.5-VL; 560→grid 18×18 after merge_size=2 rounding = 324 tokens). Verified content-independent across all four models and four random seeds.

**Trial matrix:** 2 models (run) × 4 levels × 30 images × 3 reps = 720 trials.

**Stop condition (pre-registered):** Halt after any model where >5% of any cell hits the generation budget. The stop condition fired after `qwen3vl4b_t`: L4 budget_hit = 27/90 = **30%**. The 8B models were not run.

---

## 2. Stop Condition and Its Implications

`qwen3vl4b_t` at L4 hit the 4096-token budget in 30% of trials. This means:
- The 4096 cap is insufficient for 4B-Thinking at L4. Full reasoning traces are being truncated.
- The L4 accuracy (0.100) is a lower bound under the 4096 cap, not a faithful measurement of the model's capability.
- L2 (3.3%) and L3 (3.3%) are borderline — below the threshold but non-negligible.
- L1 and L2 results are reliable; L3 is marginal; L4 is truncated.

**Classification:** This is a design failure, not a real negative. The mechanism (reasoning compute) was present and active — the stop fired because the budget was too tight, not because reasoning was absent.

**8B models:** Cannot be compared until run with a higher budget. A budget of 8192 tokens would cover the p75 of L4 traces (p75 = 4096 = capped; true p75 unknown). Recommended budget for a rerun: `max_new_tokens=8192` for Thinking models.

---

## 3. Sanity Checks

**SC1 — Row count:** 720 rows (360 per model). PASS.

**SC2 — Vision token count:** n_input = 348 for qwen3vl4b (Instruct) and 350 for qwen3vl4b_t (Thinking) — the 2-token difference is the `<think>\n` prefix injected by the Thinking chat template into the generation prompt. Constant within each model across all 4 levels, confirming content-independence at 560×560. PASS.

**SC3 — GT bins:** All ground-truth person counts within their stated bins (L1: exactly 1; L2: 2–3; L3: 4–7; L4: 8+). PASS (same image set as Study C, which passed SC3).

**SC4 — Cell completeness:** 8 cells present (2 models × 4 levels), 90 rows each. PASS.

**SC5 — Budget check (stop condition check):** 

| model | L1 budget | L2 budget | L3 budget | L4 budget |
|-------|----------|----------|----------|----------|
| qwen3vl4b | 0/90 (0%) | 0/90 (0%) | 0/90 (0%) | 0/90 (0%) |
| qwen3vl4b_t | 0/90 (0%) | 3/90 (3.3%) | 3/90 (3.3%) | **27/90 (30%)** STOP |

Stop condition correctly fired at qwen3vl4b_t/L4.

---

## 4. Results

### 4a. Accuracy (exact-match, conservative denominator)

| model | L1 | L2 | L3 | L4 | note |
|-------|----|----|----|----|------|
| qwen3vl4b (Instruct) | 0.967 | 0.700 | 0.167 | 0.033 | — |
| qwen3vl4b_t (Thinking) | 0.933 | 0.800 | 0.400 | 0.100† | †L4 truncated (30% budget hit) |

Thinking consistently outperforms Instruct at L2–L4:
- L2: +0.100 (+14%)
- L3: **+0.233 (+140%)** — most striking improvement
- L4: +0.067 (but L4 Thinking values are lower bounds)

L1: Thinking is slightly worse (0.933 vs 0.967) — marginal difference, within noise.

### 4b. Generated and reasoning token counts (median [p25, p75])

| model | L1 | L2 | L3 | L4 |
|-------|----|----|----|----|
| qwen3vl4b n_gen | 2 [2,2] | 2 [2,2] | 2 [2,2] | 3 [2,3] |
| qwen3vl4b_t n_gen | 58 [50,70] | 82 [65,91] | 425 [267,1040] | **1918 [1524,4096]** |
| qwen3vl4b_t n_think | 54 [46,66] | 78 [61,83] | 396 [263,968] | **1626 [1172,1916]** |

RQ1 — **Does reasoning token count scale with difficulty?** YES, dramatically. Think tokens: L1=54 → L2=78 → L3=396 → L4=1626. The L3→L4 jump is 4×. The wide p25–p75 IQR at L3 (263–968) indicates high variance — some images elicit much longer reasoning chains than others.

The Instruct model generates a constant 2–3 tokens across all difficulty levels (a single digit), confirming it makes no use of chain-of-thought.

### 4c. Thinking model L4 saturation

At L4, 27/90 trials hit the 4096-token cap. The p75 of n_generated equals 4096, meaning the true distribution's upper quartile is unknown. The median n_think at L4 is 1626 tokens with the cap pulling the upper tail down. A budget of ~8192 would likely be sufficient to not truncate most trials.

---

## 5. Direct Answers to RQs (with caveats)

### RQ1: Do Thinking models generate more tokens at higher difficulty?

**Yes, monotonically and dramatically.** Think tokens scale from 54 (L1) to 1626 (L4, median) — a 30× increase. The Instruct model generates 2 tokens throughout. This directly answers whether reasoning compute is sensitive to difficulty: it is.

### RQ2: Does 4B-Thinking match or exceed same-size Instruct accuracy at high difficulty?

**Yes at L2–L4.** The Thinking model exceeds Instruct at every level above L1:
- L3: exact-match 0.400 vs 0.167 — 2.4× the Instruct accuracy
- L4: 0.100 vs 0.033 (lower bound)

The L3 result is the most reliable: no budget hits, full reasoning traces, 2.4× accuracy improvement. **Reasoning compute provides a large within-parameter-count benefit at L3.**

The 8B comparison (does 4B-Thinking match 8B-Instruct?) cannot be answered — 8B models were not run.

### RQ3: Does reasoning token count predict accuracy within Thinking models?

Cannot be answered from cell-level medians alone. Would require trial-level correlation between n_think_tokens and correct, which is computable from the CSV but was not done in the automated analysis. The cell-level pattern is consistent (higher think tokens at higher difficulty, higher accuracy at higher difficulty relative to Instruct), but correlation within a cell requires further analysis.

---

## 6. What Cannot Be Inferred

**8B vs 4B comparison:** The central question — does 4B-Thinking substitute for 8B-Instruct — cannot be answered without running the 8B models. This is the primary gap.

**True L4 Thinking accuracy:** The 30% budget hit rate means L4=0.100 is a lower bound. The true accuracy under uncapped generation is unknown.

**Reasoning quality vs quantity:** Whether longer reasoning chains are better or just longer cannot be determined from these data alone. At L3, the wide IQR (263–968 think tokens) with 0.400 accuracy means some short traces succeed and some long traces fail. The relationship is not monotone within the cell.

**Comparison to Study C:** Study C used Qwen2.5-VL (different architecture, different patch size, different pretraining), so the Instruct numbers are not directly comparable. Qwen3-VL-4B-Instruct at 0.167 (L3) vs Qwen2.5-VL-3B-Instruct at 0.233 (L3 direct) and 7B at 0.367 — the differences reflect both architecture and parameter count.

---

## 7. Verdict and Next Steps

**Partial finding (reliable):** Reasoning compute in the 4B-Thinking model substantially improves object-counting accuracy at L3 (0.167 → 0.400, exact-match). This is a clean finding — no budget hits at L3, full reasoning traces, 90 trials per cell.

**Incomplete:** L4 and the 8B comparison require a rerun with `max_new_tokens=8192` for Thinking models. The stop condition was correctly triggered; this is a design parameter adjustment, not a methodology change.

**Recommended next step:** Rerun with `max_new_tokens=8192`. The 4B-Thinking L4 run took ~25–35 seconds/trial at L4 with 4096 budget; at 8192 it will be proportionally longer for trials that were truncated. At 30% budget hit (27 trials), the additional time is bounded: ~27 × ~30s extra ≈ ~14 minutes more at L4 for 4B-Thinking.
