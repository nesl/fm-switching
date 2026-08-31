# Study D2 — Reasoning Compute vs Parameters with Scene Difficulty

**Date:** 2026-08-30  
**Script:** `experiments/vision/study_d2_thinking.py`  
**Models:** Qwen3-VL-4B-Instruct, 4B-Thinking, 8B-Instruct, 8B-Thinking  
**Device:** A6000 (cuda:1), bfloat16, greedy decoding  
**transformers:** 5.12.1 · **torch:** 2.4.1+cu118  

---

## 1. What Was Run

**Research question:** Does reasoning compute (Thinking models) substitute for parameters (larger Instruct models) as scene difficulty increases? And is reasoning token count within a difficulty level predictable enough to budget for?

**Main matrix (quantitative):** L1–L3 × 4 models × 3 reps = 1,080 planned trials.  
**L4 probe (qualitative):** L4 × 2 Thinking models × 10 images × 1 rep = 20 trials. Records whether the reasoning block closed before the budget was consumed. This is a classification exercise, not an accuracy measurement.

**Difficulty bins** (same as Study C):

| Level | Person count | Images | Reps | Cells |
|-------|-------------|--------|------|-------|
| L1 | exactly 1 | 30 | 3 | 90 |
| L2 | 2–3 | 30 | 3 | 90 |
| L3 | 4–7 | 30 | 3 | 90 |

**Mode definitions:**
- **Instruct:** chat template produces `<|im_start|>assistant\n`; model answers directly. `max_new_tokens=40`.
- **Thinking:** chat template produces `<|im_start|>assistant\n<think>\n`, forcing a reasoning block. `max_new_tokens=8192`. Output split at `</think>`; tokens before the tag = reasoning chain; tokens after = answer.

**Vision tokens:** 324 per image at 560×560 (Qwen3-VL patch_size=16, grid 18×18 after merge_size=2). Content-independent; verified empirically in Study D. `n_input=348` for Instruct, `n_input=350` for Thinking (the 2-token difference is the `<think>\n` prefix in the generation prompt).

**Provenance note:** Study D2 inherits 4B-Instruct (360 rows) and 8B-Instruct (360 rows) from a prior partial run of the same script that was killed before the Thinking models completed. Those rows were migrated to the new column schema and reused via resume. All Thinking rows were run fresh. The 41 partial 4B-Thinking L1–L3 rows from a prior aborted run (at the same 8192 budget) were also reused.

**Why 8192 (not 4096):** Study D's original run used max_new_tokens=4096 for Thinking models. At L4, 4B-Thinking hit the budget in 30% of trials; the first L4 trial in the aborted Study D2 run showed n_gen=8192 with status=no_think_tag (model still inside the reasoning block when cut off). The budget was raised to 8192 to allow L3 to complete cleanly and to probe what happens at L4.

---

## 2. Raw Measurements

### 2a. Accuracy — all four tolerance criteria

**L1 (1 person):**

| model | exact | within-1 | within-2 | rt25 |
|-------|-------|---------|---------|------|
| 4B-Instruct | 0.967 | 1.000 | 1.000 | 0.967 |
| 8B-Instruct | 0.967 | 1.000 | 1.000 | 0.967 |
| 4B-Thinking | 0.933 | 1.000 | 1.000 | 0.933 |
| 8B-Thinking | 0.967 | 1.000 | 1.000 | 0.967 |

**L2 (2–3 people):**

| model | exact | within-1 | within-2 | rt25 |
|-------|-------|---------|---------|------|
| 4B-Instruct | 0.700 | 0.933 | 0.967 | 0.700 |
| 8B-Instruct | 0.700 | 0.900 | 0.967 | 0.700 |
| 4B-Thinking | **0.800** | 0.933 | 0.967 | **0.800** |
| 8B-Thinking | 0.667 | 0.933 | 0.967 | 0.667 |

**L3 (4–7 people):**

| model | exact | within-1 | within-2 | rt25 |
|-------|-------|---------|---------|------|
| 4B-Instruct | 0.167 | 0.733 | 0.800 | 0.733 |
| 8B-Instruct | 0.333 | 0.733 | 0.800 | 0.733 |
| 4B-Thinking | **0.400** | **0.767** | **0.867** | **0.767** |
| 8B-Thinking | 0.367 | **0.767** | 0.833 | **0.767** |

### 2b. Latency and throughput (main matrix, median)

| model | L1 lat (ms) | L2 lat (ms) | L3 lat (ms) | tok/s |
|-------|------------|------------|------------|-------|
| 4B-Instruct | 94 | 94 | 94 | 21 |
| 8B-Instruct | 140 | 139 | 140 | 14 |
| 4B-Thinking | 1,201 | 1,677 | **8,693** | 48 |
| 8B-Thinking | 1,645 | 2,643 | **14,501** | 32 |

Thinking models have higher tok/s than Instruct because they generate far more tokens per trial. Instruct generates 2–3 tokens per trial; Thinking generates 50–500+ tokens per trial at the same wall-clock throughput.

### 2c. Budget hits (main matrix)

All Instruct cells: 0/90 (0%).  
Thinking models — 3/90 (3.3%) at L2 and L3 for both 4B-T and 8B-T. All below the 5% stop threshold. Main matrix is complete and untruncated.

### 2d. L4 probe — termination classification

| model | n | non_termination | verbose_bounded | complete |
|-------|---|----------------|----------------|---------|
| 4B-Thinking | 10 | 2 (20%) | 0 (0%) | 8 (80%) |
| 8B-Thinking | 10 | 3 (30%) | 0 (0%) | 7 (70%) |

**Definition of termination classes:**
- `complete`: n_gen < max_new_tokens — model finished within budget.
- `verbose_bounded`: n_gen == max_new_tokens AND `</think>` was found — model produced an answer but continued generating until cutoff.
- `non_termination`: n_gen == max_new_tokens AND `</think>` was NOT found — model was still inside the reasoning block when cut off; no answer was produced.

**Key finding:** All L4 budget-hit trials are `non_termination`. There are no `verbose_bounded` cases. When these Thinking models hit the 8192-token cap at L4, they have not yet produced an answer — the reasoning chain did not converge within the budget. The 8B model has a higher non-termination rate (30%) than the 4B model (20%) on this image set, which is a small-sample result (10 images) and should not be over-interpreted, but it does suggest that 8B does not trivially fix the L4 non-termination problem.

Representative L4 probe token counts (complete trials only):

| model | image_id | gt | n_think_tokens | latency (s) |
|-------|----------|----|---------------|------------|
| 4B-T | 6771 | 8 | ~740 | 15.7 |
| 4B-T | 98287 | 14 | ~1620 | 36.6 |
| 4B-T | 44590 | 12 | ~5210 | 141.0 |
| 4B-T | 1584 | 11 | ~990 | 32.4 |

Token count at L4 is not monotone in object count: gt=12 needed 5× more tokens than gt=14. Scene complexity and layout drive reasoning length, not headcount alone.

---

## 3. Sanity Checks

**SC1 — Row count:** Main matrix: 1,260 rows (4 models × 3 levels × 90 trials). L4 probe: 20 rows (2 Thinking models × 10 images × 1 rep). PASS.

**SC2 — Vision token count:** `n_input=348` constant across all Instruct trials; `n_input=350` constant across all Thinking trials. Content-independent; the 2-token gap matches the `<think>\n` prefix. PASS.

**SC3 — GT bins:** Identical image set to Study C; SC3 already passed there. PASS.

**SC4 — Cell completeness:** All 12 main-matrix cells contain exactly 90 rows. PASS.

**SC5 — Budget hits:** Thinking models: 3/90 (3.3%) at L2 and L3 for both 4B-T and 8B-T. All below the 5% stop threshold. No stop condition triggered. PASS.

**SC6 — Thinking vs Instruct mode distinction:** Instruct models produce 2–3 tokens per trial (`n_think_tokens=0` in all Instruct rows). Thinking models produce `n_think_tokens>0` in all but the 12 budget-hit trials (3.3% of L2+L3 rows) where the think tag did not close. PASS.

**SC7 — Precision and device:** All four models loaded on cuda:1 at torch.bfloat16. Verified via `next(model.parameters()).dtype` assertion inside the script. PASS.

---

## 4. Analysis A — Accuracy Under All Tolerance Criteria

The key pattern across all four tolerances:

**L1:** All models near ceiling under exact-match (0.933–0.967). Under within-1, all models reach 1.000. L1 is too easy to discriminate models; no finding here.

**L2:** Exact-match: 4B-Thinking (0.800) beats both Instruct models (0.700) and 8B-Thinking (0.667). Under within-1, the gap collapses to 0.900–0.933 across all four models — essentially equivalent. This means 4B-Thinking's L2 advantage under exact-match is driven by off-by-one errors that it avoids more often, not by fundamentally better scene understanding.

**L3:** Exact-match: 4B-Thinking (0.400) > 8B-Thinking (0.367) > 8B-Instruct (0.333) > 4B-Instruct (0.167). Under within-1, the Thinking models (0.767) lead the Instruct models (0.733) — a modest gap of 3.4 percentage points that is consistent across both Thinking models. Under within-2, 4B-Thinking (0.867) leads, but all models reach 0.800 or above.

**Observation:** Exact-match undersells all models at L3, consistent with Study C rescore findings. The within-1 criterion is the appropriate primary criterion at L3.

---

## 5. Analysis B — The Decisive Comparison

**Does 4B-Thinking match or exceed 8B-Instruct accuracy, and at what latency cost?**

| Level | 4B-T exact | 8B-I exact | Δ exact | 4B-T within-1 | 8B-I within-1 | Δ w1 | Lat ratio (4B-T / 8B-I) |
|-------|-----------|-----------|--------|--------------|--------------|------|--------------------------|
| L1 | 0.933 | 0.967 | −0.033 | 1.000 | 1.000 | 0.000 | 13× |
| L2 | 0.800 | 0.700 | **+0.100** | 0.933 | 0.900 | **+0.033** | 12× |
| L3 | 0.400 | 0.333 | **+0.067** | 0.767 | 0.733 | **+0.034** | 62× |

**Direct answers:**

- **L1:** No. 4B-Thinking is slightly worse than 8B-Instruct under exact-match (−0.033); tied under within-1. Latency cost: 13×. Reasoning compute at L1 is pure overhead.

- **L2:** Yes under both exact-match (+0.100) and within-1 (+0.033). Latency cost: 12× (4B-T median 1,677ms vs 8B-I median 139ms). The gain is real but modest at within-1, and 12× latency is substantial.

- **L3:** Yes under both exact-match (+0.067) and within-1 (+0.034). Latency cost: 62× (4B-T median 8,693ms vs 8B-I median 140ms). The accuracy advantage is small; whether 62× latency is acceptable depends on the serving context.

**Comparison against 8B-Thinking:** At L3, 4B-T (0.767 within-1) and 8B-T (0.767 within-1) are identical. 4B-T is faster (8.7s vs 14.5s, 1.7× ratio). This means that for L3, the 8B Thinking model provides no accuracy benefit over the 4B Thinking model, while costing 1.7× more latency.

---

## 6. Analysis C — Thinking-Token Distribution

| model | level | median | p25 | p75 | min | max | IQR/median |
|-------|-------|--------|-----|-----|-----|-----|-----------|
| 4B-T | L1 | 54 | 46 | 66 | 36 | 137 | 0.37 |
| 4B-T | L2 | 78 | 61 | 87 | 36 | 8192† | 0.33 |
| 4B-T | L3 | 420 | 263 | 1,036 | 38 | 8192† | **1.84** |
| 8B-T | L1 | 48 | 38 | 54 | 27 | 172 | 0.34 |
| 8B-T | L2 | 80 | 58 | 99 | 36 | 8192† | 0.51 |
| 8B-T | L3 | 464 | 162 | 954 | 74 | 8192† | **1.71** |

† Max=8192 indicates the budget-hit trials (3/90 per cell); true distribution upper tail is truncated.

**Key observation:** At L1 and L2, IQR/median < 0.5 — distributions are moderately tight and broadly predictable. At L3, IQR/median ≈ 1.8 — the interquartile range exceeds the median. p25 to p75 spans 263→1036 tokens for 4B-T, a 4× range. This means the 75th-percentile trial at L3 uses ~4× the tokens of the 25th-percentile trial. Reasoning length at L3 cannot be predicted in advance for a specific image.

The L3 min (38 tokens for 4B-T) is nearly identical to the L1 median (54 tokens), confirming that some L3 images can be answered with very short reasoning chains — likely images where the crowd is visually obvious or countable at a glance. Others require extended enumeration, leading to 1000+ token traces.

---

## 7. Analysis D — Within-Cell Correlation: n_think vs Correctness

Point-biserial r computed within each cell (not pooled across levels, which would manufacture a correlation from the difficulty trend).

| model | L1 | L2 | L3 |
|-------|----|----|-----|
| 4B-T | **−0.818** | +0.097 | −0.216 |
| 8B-T | **−0.881** | −0.312 | −0.153 |

**Interpretation:**

**L1 (large negative r):** At L1, longer reasoning chains are strongly associated with incorrect answers. The correct answer to "how many people?" when there is exactly 1 person is a short chain; the model overcounts or second-guesses itself when it reasons longer. More thinking at L1 is a liability.

**L2 (near zero or weak negative):** No meaningful relationship. The model can arrive at the correct or incorrect answer with short or long chains. The task is neither easy enough to be hurt by thinking nor hard enough to reliably benefit from it.

**L3 (weak negative):** Slightly negative — longer traces do not predict correctness within the cell. This means that within L3, extended reasoning is not a reliable signal of a better answer. Some long traces succeed; some short traces fail. The benefit of thinking at L3 (observed in accuracy tables) comes from the typical case, not from the tail of long traces.

**Summary:** Longer thinking tokens do not predict correctness within a difficulty level. The accuracy benefit of Thinking models is distributed across the typical response, not concentrated in the longest traces.

---

## 8. Analysis E — Token Growth vs Object Count

Think-tokens per median GT person count:

| model | L1 (gt_med=1) | L2 (gt_med=2) | L3 (gt_med=5) |
|-------|--------------|--------------|--------------|
| 4B-T | 53.5 tok/person | 39.0 tok/person | 84.1 tok/person |
| 8B-T | 47.5 tok/person | 40.2 tok/person | 92.7 tok/person |

**Pattern:** The ratio is not constant — it drops from L1→L2 then rises sharply at L3.

- **L1→L2:** tokens per person drops from ~50 to ~40. Marginal cost of an additional person decreases, consistent with efficient enumeration ("I see person A, person B").
- **L2→L3:** tokens per person more than doubles, rising from ~40 to ~85–93. The cost of adding people from 2–3 to 4–7 is superlinear.

**Interpretation:** Simple enumeration does not explain L3 token counts. At L3, the model is doing more than listing people — it is likely revisiting, recounting, or handling crowd ambiguity. This superlinear growth is consistent with L3 being the difficulty transition identified in Study C, where compression-omission failures spike and exact-match floors.

---

## 9. Direct Answers to the Two Key Questions

### At each difficulty level, does reasoning compute on the small model substitute for parameters on the large model, and at what latency cost?

**L1:** No. 4B-Thinking is not better than 8B-Instruct (−0.033 exact, 0 within-1). Latency cost is 13×. Reasoning is overhead at L1.

**L2:** Marginally yes. 4B-Thinking beats 8B-Instruct by +0.100 exact and +0.033 within-1. Latency cost is 12×. The gain under within-1 is small enough that it may not be robust at larger n.

**L3:** Yes, by a small but consistent margin. 4B-Thinking beats 8B-Instruct by +0.067 exact and +0.034 within-1. Latency cost is 62×. For applications where latency is not a binding constraint and exact counting at L3 is required, 4B-Thinking is the better choice. For latency-sensitive applications, 8B-Instruct achieves equivalent within-1 accuracy at 62× lower latency.

### Is thinking-token count within a difficulty level predictable, or is the dispersion large enough that it cannot be known in advance?

**L1–L2:** Broadly predictable. IQR/median < 0.5; most trials fall within a 2× range of the median.

**L3:** Not predictable. IQR/median ≈ 1.8; p25 to p75 spans a 4× range (263–1036 tokens for 4B-T). A specific L3 trial could consume anywhere from 38 to 8192 tokens. This means worst-case latency at L3 is unbounded within the 8192-token budget. Any serving system that must guarantee L3 latency must budget for the 95th percentile, not the median.

---

## 10. What Cannot Be Inferred

**L4 accuracy:** The L4 probe was a 10-image, 1-rep termination classification exercise. It does not provide accuracy estimates. The 8 complete 4B-T trials and 7 complete 8B-T trials produced answers, but n=8/7 is too small to report as accuracy.

**Comparison across study generations (Study C vs D2):** Study C used Qwen2.5-VL (patch_size=14, 400 vision tokens). Study D2 uses Qwen3-VL (patch_size=16, 324 vision tokens). Numbers are not directly comparable across architectures.

**Why some L4 images complete and others do not:** The 10 probe images were the first 10 L4 images by image_id. Non-termination occurred on 2 of 10 for 4B-T and 3 of 10 for 8B-T. The distinguishing scene features are not known from the data collected.

**n=90 power:** With 90 trials per cell and typical Thinking model within-1 accuracy ~0.767, the standard error is ≈ 0.044. Differences of 0.033–0.034 (the 4B-T vs 8B-I within-1 gap) are within ~1 SE and are not individually conclusive. The pattern is consistent across all four tolerance criteria and both Thinking models, which provides some robustness, but a larger-n replication would be needed to confirm the L2 and L3 within-1 gaps.

---

## 11. Verdict

**Reliable findings (main matrix, L1–L3, no budget issues):**

1. Reasoning compute (4B-Thinking) exceeds same-generation larger parameters (8B-Instruct) at L3 under exact-match (0.400 vs 0.333) and within-1 (0.767 vs 0.733). The accuracy gain is real but small; the latency cost is 62×.

2. At L3, 4B-Thinking and 8B-Thinking achieve identical within-1 accuracy (0.767 each). Larger parameters do not improve Thinking model accuracy at L3; 4B-Thinking is the more efficient Thinking choice.

3. Think-token count within L3 is unpredictable (IQR/median ≈ 1.8). Worst-case latency cannot be bounded from the median. Systems serving L3 difficulty with Thinking models must plan for the tail, not the center.

4. Within each difficulty level, longer reasoning traces do not predict correctness (point-biserial r ≤ +0.097, often negative). At L1, more thinking is associated with wrong answers (r ≈ −0.85).

**L4 probe finding:** At L4 with 8192-token budget, 20–30% of trials are `non_termination` — the model never closes its reasoning block and produces no answer. There are zero `verbose_bounded` cases. Budget failure at L4 is always reasoning non-convergence, not post-answer verbosity.

**Recommended next steps:** The within-1 accuracy gap (4B-T vs 8B-I at L3: +0.034) is the primary open question from a power standpoint. A 270-trial replication (same 30 images, 3× more reps) would shrink the SE to ~0.025 and allow a more confident conclusion about whether the gap is real. Separately, a larger L4 probe (30 images, 1 rep) would give a more stable estimate of the non-termination rate and identify which scene features drive non-convergence.
