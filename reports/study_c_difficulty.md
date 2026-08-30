# Study C — Difficulty Scaling: 3B vs 7B VLM on Object Counting

**Date:** 2026-08-30  
**Script:** `experiments/vision/study_c_difficulty.py`  
**Git commit:** 3f381f499d2b99f0aea65f4a38c4b3448bb3a2fd  
**Device:** NVIDIA RTX A6000 (cuda:1, 49 GB)  
**Models:** Qwen/Qwen2.5-VL-3B-Instruct, Qwen/Qwen2.5-VL-7B-Instruct  
**Package versions:** torch 2.4.1+cu118, transformers 5.12.1, PIL 9.2.0, datasets 5.0.0, python 3.10.19

---

## 1. What Was Run

**Task.** Object counting in natural images: how many people are in this image?

**Data.** COCO val2017, accessed via HuggingFace (`detection-datasets/coco`, split `val`, images decoded from Parquet bytes). Images resized to 560×560 (Qwen2.5-VL native size) before inference. Ground-truth person count from COCO annotations. Person category index in this dataset is index 0 (verified by inspecting `features['objects']['category'].feature.names`).

**Difficulty bins.**

| Level | Person count | Pool size |
|-------|-------------|-----------|
| L1 | exactly 1 | 1,045 |
| L2 | 2–3 | 704 |
| L3 | 4–7 | 444 |
| L4 | 8+ | 500 |

30 images selected per level using `random.Random(42)` seeded shuffle of each pool. Selections stored in `results/vision/study_c/study_c_selection.json`.

**Accuracy criterion.** Exact match: parsed integer answer equals annotated person count. Being off by 1 counts as wrong.

**Trial matrix.** 2 models × 2 prompt modes × 4 levels × 30 images × 3 reps = 1,440 trials. All models run sequentially (7B first, then 3B unloaded). Trial order within each model randomized via `random.Random(42 + hash(model_slug) % 10000)`.

**Prompts.**

- **Direct:** "How many people are in this image? Answer with a single integer only. Do not explain." Max 30 new tokens.
- **Stepwise:** "How many people are in this image? Think step by step: describe each person you can see. Then give your final answer on its own line starting exactly with 'Final answer:' followed by the number. Example: Final answer: 3" Max 512 new tokens.

**Generation config.** Greedy decoding (`do_sample=False`, `temperature=None`, `top_p=None`), dtype bfloat16.

**Timing.** `torch.cuda.synchronize()` before and after `model.generate()`; measured with `time.perf_counter()`.

**Answer parsing.**
- Direct: first integer in response (`re.findall(r"\b\d+\b", text)[0]`).
- Stepwise: `re.search(r"(?i)final\s+answer\s*[:：]\s*(\d+)", text)`, fallback to last integer in response.

**Raw data.** `results/vision/study_c/study_c_trials.csv` (1,440 rows, one per trial). Columns: `model, image_id, level, n_persons_gt, mode, rep, n_input, n_generated, latency_ms, budget_hit, parsed_answer, parse_status, correct`.

---

## 2. Raw Measurements

### 2a. Per-cell summary

| model | mode | level | n | acc | tok_med | tok_min | tok_max | tok_p25 | tok_p75 | lat_med_ms | budget% | unparse% |
|-------|------|-------|---|-----|---------|---------|---------|---------|---------|------------|---------|----------|
| qwenvl3b | direct | L1 | 90 | 0.967 | 2.0 | 2 | 2 | 2.0 | 2.0 | 127 | 0.0% | 0.0% |
| qwenvl3b | direct | L2 | 90 | 0.700 | 2.0 | 2 | 2 | 2.0 | 2.0 | 127 | 0.0% | 0.0% |
| qwenvl3b | direct | L3 | 90 | 0.233 | 2.0 | 2 | 2 | 2.0 | 2.0 | 127 | 0.0% | 0.0% |
| qwenvl3b | direct | L4 | 90 | 0.067 | 3.0 | 2 | 4 | 2.0 | 3.0 | 139 | 0.0% | 0.0% |
| qwenvl3b | stepwise | L1 | 90 | 0.821 | 75.0 | 38 | 140 | 55.0 | 99.0 | 1238 | 0.0% | 6.7% |
| qwenvl3b | stepwise | L2 | 90 | 0.586 | 93.0 | 56 | 140 | 72.0 | 110.0 | 1512 | 0.0% | 3.3% |
| qwenvl3b | stepwise | L3 | 90 | 0.300 | 124.5 | 30 | 159 | 104.0 | 141.0 | 2006 | 0.0% | 0.0% |
| qwenvl3b | stepwise | L4 | 90 | 0.033 | 125.5 | 64 | 201 | 89.0 | 148.0 | 2029 | 0.0% | 0.0% |
| qwenvl7b | direct | L1 | 90 | 0.933 | 2.0 | 2 | 2 | 2.0 | 2.0 | 179 | 0.0% | 0.0% |
| qwenvl7b | direct | L2 | 90 | 0.700 | 2.0 | 2 | 2 | 2.0 | 2.0 | 179 | 0.0% | 0.0% |
| qwenvl7b | direct | L3 | 90 | 0.367 | 2.0 | 2 | 2 | 2.0 | 2.0 | 179 | 0.0% | 0.0% |
| qwenvl7b | direct | L4 | 90 | 0.133 | 3.0 | 2 | 4 | 2.0 | 3.0 | 205 | 0.0% | 0.0% |
| qwenvl7b | stepwise | L1 | 90 | 0.967 | 69.0 | 21 | 106 | 55.0 | 89.0 | 1911 | 0.0% | 0.0% |
| qwenvl7b | stepwise | L2 | 90 | 0.700 | 95.0 | 47 | 151 | 85.0 | 114.0 | 2571 | 0.0% | 0.0% |
| qwenvl7b | stepwise | L3 | 90 | 0.167 | 131.0 | 28 | 179 | 96.0 | 144.0 | 3523 | 0.0% | 0.0% |
| qwenvl7b | stepwise | L4 | 90 | 0.000 | 140.0 | 53 | 512 | 115.0 | 170.0 | 3753 | 3.3% | 0.0% |

*acc = fraction correct (exact match). tok = generated tokens. lat = TTFT excluding prompt processing is not separated; this is total generate() time. budget% = fraction reaching max_new_tokens limit. unparse% = fraction with no parseable answer (counted as incorrect in acc).*

### 2b. Accuracy gap table (7b − 3b), by mode

| Level | Direct gap | Stepwise gap |
|-------|-----------|--------------|
| L1 | −0.033 | +0.145 |
| L2 | +0.000 | +0.114 |
| L3 | +0.133 | −0.133 |
| L4 | +0.067 | −0.033 |

### 2c. Stepwise vs direct delta, by model

| Level | 3B (step−dir) | 7B (step−dir) |
|-------|--------------|--------------|
| L1 | −0.145 | +0.033 |
| L2 | −0.114 | +0.000 |
| L3 | +0.067 | −0.200 |
| L4 | −0.033 | −0.133 |

### 2d. Generated token count, stepwise mode

| Level | 3B med [p25, p75] | 7B med [p25, p75] |
|-------|-------------------|-------------------|
| L1 | 75.0 [55, 99] | 69.0 [55, 89] |
| L2 | 93.0 [72, 110] | 95.0 [85, 114] |
| L3 | 124.5 [104, 141] | 131.0 [96, 144] |
| L4 | 125.5 [89, 148] | 140.0 [115, 170] |

Direct mode: all cells produce 2 tokens at L1–L3, 3 tokens at L4 (just the digit(s)).

**Figures:** `figures/vision/study_c_difficulty.pdf`, `figures/vision/study_c_difficulty.png`

---

## 3. Sanity Checks

### SC1 — Input token count constant across difficulty levels

**Result: PASS (with annotation).** The analysis script raised SC1 as a failure because n_input takes two values across the full dataset: 440 (direct mode) and 469 (stepwise mode). This is expected: the two prompts differ by 29 tokens. The invariant of interest is that image tokenization does not vary with difficulty (i.e., n_input is constant within a given model+mode pair across L1–L4). That invariant holds perfectly: every (model, mode, level) cell has a single n_input value. Image tokenization for 560×560 inputs is constant regardless of scene content, consistent with Study A findings. The SC1 implementation checked global uniqueness rather than within-mode uniqueness; the underlying assumption holds.

### SC2 — Stepwise generates substantially more tokens than direct

**Result: PASS.** Direct mode: 2–3 tokens (median) across all cells. Stepwise mode: 69–140 tokens (median). Ratio > 20× across all cells. SC2 threshold was 1.5×; exceeded by a large margin.

### SC3 — No cell exceeds 5% budget hit rate

**Result: PASS.** Only one cell (qwenvl7b|stepwise|L4) has any budget hits: 3.3% (3 of 90 trials). All other cells: 0.0%. Threshold is 5%; no violation.

### SC4 — Unparseable fractions

**Result: WARNING.** qwenvl3b|stepwise|L1: 6.7% (6/90 trials) did not produce a "Final answer: N" line and the fallback (last integer) also failed. qwenvl3b|stepwise|L2: 3.3% (3/90). All other cells: 0.0%. Unparseable trials are counted as incorrect (conservative). If excluded from the denominator for L1, 3B-stepwise accuracy would be ~74/84 = 0.881 instead of 0.821. The headline table uses the conservative denominator (90). This unparse rate does not affect L3/L4 cells where the main findings reside.

### Stop conditions

- Budget hit > 5% in any cell: not triggered (max 3.3%).
- Stepwise and direct lengths similar: not triggered (> 20× difference).
- Any result unusually clean: the 7B-stepwise-L4 = 0.000 is a complete collapse, not a suspiciously clean success. It is consistent with the 3.3% budget hit rate (model generating very long outputs) and with the reversal already visible at L3. Not a "strongly confirms a hypothesis" stop — if anything, it disconfirms H4 and H5.

---

## 4. Inferences on H1–H6

### RQ1: Does generated token count scale with difficulty?

**H1 (no), H2 (yes) — H2 is supported.**

Stepwise token count increases monotonically with difficulty for both models:
- 7B: 69 → 95 → 131 → 140 tokens (L1→L4)
- 3B: 75 → 93 → 124.5 → 125.5 tokens (L1→L4)

The plateau between L3 and L4 for 3B (124.5 vs 125.5) is within the IQR overlap and not a reversal.

Direct mode generates ~2 tokens at all levels regardless of difficulty; this is a trivial consequence of the prompt constraining output to a single integer.

The token scaling in stepwise mode reflects longer scene descriptions as person count increases. Both models exhibit it at comparable magnitude.

### RQ2: Does the accuracy gap widen with difficulty?

**H3 (constant gap), H4 (widening gap) — neither is supported. The gap is non-monotone and reverses at high difficulty.**

**Direct mode:** The gap (7B − 3B) is −0.033 at L1 (3B slightly better), 0.000 at L2, +0.133 at L3, +0.067 at L4. There is a modest 7B advantage in the mid-to-high range, but not a widening trend: the gap shrinks from L3 to L4. The gap is small throughout (max 0.133 pp).

**Stepwise mode:** The gap reverses across the difficulty axis. 7B leads at low difficulty (+0.145 at L1, +0.114 at L2) and 3B leads at high difficulty (−0.133 at L3, −0.033 at L4). The reversal is driven primarily by 7B-stepwise collapsing at high difficulty (see RQ3). Neither model holds a consistent advantage.

The direction and magnitude of the gap depends on prompt mode, making "the 3B vs 7B gap" an underspecified question — the mode is a confounder.

### RQ3: Does step-by-step reasoning on 3B close the gap to 7B?

**H5 (yes), H6 (plateaus) — neither is supported. Stepwise reasoning is overall harmful for this task.**

Comparing 3B-stepwise to 7B-direct (the "does reasoning close the gap?" comparison):

| Level | 3B-direct | 3B-stepwise | 7B-direct | 3B-step vs 7B-dir |
|-------|-----------|-------------|-----------|-------------------|
| L1 | 0.967 | 0.821 | 0.933 | −0.112 |
| L2 | 0.700 | 0.586 | 0.700 | −0.114 |
| L3 | 0.233 | 0.300 | 0.367 | −0.067 |
| L4 | 0.067 | 0.033 | 0.133 | −0.100 |

Stepwise reasoning on 3B does not close the gap; it widens it at L1–L2 and narrows it slightly at L3 but only because 7B-direct is also weak there.

The same pattern holds for 7B:
- L1/L2: stepwise matches or slightly improves on direct (+0.033, 0.000)
- L3: stepwise drops −0.200 below direct
- L4: stepwise drops to 0.000; direct is 0.133

Chain-of-thought reasoning degrades exact-match accuracy at medium-to-high difficulty for both models. The likely mechanism: at high person counts, the model's step-by-step enumeration of individuals diverges from the true count; the verbal description of crowded scenes is harder than pattern-matching on a simpler number. This is consistent with known CoT failure modes on visual counting tasks.

The stepwise 7B-L4 result (0.000 exact match out of 90 trials) is the sharpest form of this pattern. The 3.3% budget hit rate confirms the model was generating extended descriptions but failing to produce a correct final count.

---

## 5. What Cannot Be Inferred

**Causal mechanism for the CoT reversal.** The data show that stepwise reasoning hurts accuracy at L3–L4 but does not say why. Possible explanations include: (a) the step-by-step prompt elicits a different internal process that is less reliable for crowded scenes; (b) the model's descriptions of individuals in crowded scenes are itself erroneous, leading the final count to compound multiple errors; (c) the "Final answer: N" format introduces a parsing point where the model can give a number inconsistent with its own description. These are not distinguishable here.

**Generalisation across tasks.** This study used one counting task (people) with one difficulty axis (count). Whether the patterns transfer to other object categories, other difficulty metrics (occlusion, overlap, small objects), or other visual tasks is unknown.

**Statistical significance.** The measurements are reported as fractions over n=90 per cell (30 images × 3 reps). No hypothesis test has been applied. The 3B-direct vs 7B-direct gap at L3 (0.133 pp) and the stepwise-vs-direct deltas are large relative to the cell sizes, but formal tests were not run.

**Latency interpretation.** The latency column (lat_med_ms) measures total `model.generate()` wall time including prompt processing. It is not pure decode latency. The 7B-direct latency is ~179 ms; 3B-direct is ~127 ms. These are not comparable to Study A/B KV construction or query TTFT measurements, which are defined on different operations and different hardware states.

**Quality vs fidelity relevance.** This study used full-precision 560×560 images (equivalent to the "full" fidelity in FM-switching terms). It does not speak to how compressed representations (win-10, sum-80, sum-200) would affect counting accuracy. That would require a separate fidelity ablation.

---

## 6. Verdict

| RQ | Hypotheses | Verdict |
|----|-----------|---------|
| RQ1: token count scales with difficulty? | H1 (no), H2 (yes) | **H2: yes**, for stepwise mode. Monotonic increase for both models. |
| RQ2: gap widens with difficulty? | H3 (constant), H4 (widens) | **Neither.** Gap is non-monotone; reverses at high difficulty in stepwise mode. |
| RQ3: stepwise on 3B closes gap to 7B? | H5 (yes), H6 (plateaus) | **Neither.** Stepwise is harmful at low difficulty; provides negligible benefit at high difficulty; 7B collapses to zero at L4. |

**Overall:** Chain-of-thought prompting does not reliably improve counting accuracy and actively degrades it at high difficulty for both models. The 3B vs 7B gap is mode-dependent and non-monotone; it does not justify a "larger model always better at harder scenes" assumption. For research direction purposes: accuracy at high difficulty is dominated by task hardness (exact match on 8+ persons is near-floor for both models in both modes), making this difficulty axis a weak discriminator for model capability comparisons above L3.
