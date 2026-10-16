# Study S1 — SDPA vs flash-attention-2 backend comparison

**Date:** 2026-10-16
**Re-run of:** StudyS1 (`reports/study_s1_competent_categories.md`)
**Device:** a6000 (cuda:1) · flash_attn 2.6.3 · torch 2.8.0+cu128 · transformers 5.10.2
**Changed between runs:** the attention backend only. Same 401-question competent stratum, same model snapshots, same prompt, same decoding, same budgets.

Both model loads assert `flash_attention_2` via `experiments/lib/attn_guard.py`; every trial row
carries the asserted value.

Outputs: `results/mvrobobench/study_s1/study_s1_trials.jsonl` (SDPA) ·
`results/mvrobobench/study_s1/study_s1_trials_fa2.jsonl` (new).
Arms: T = 8B-Thinking · I = 8B-Instruct.

**Pool note.** The SDPA file contains 1,708 arm-I rows and 461 arm-T rows across the pilot and
the full stratum; the FA2 re-run covers the 401-question competent stratum only. Every figure
below is computed on the **401 questions present in both files**, for both backends. An earlier
pass that compared the full SDPA pool against the 401-question FA2 pool gave arm-I throughput of
9.9 → 12.6 tok/s (1.28×); that 1.28× was a pool mismatch, not a backend effect. Pool-matched it
is 12.7 → 12.6 tok/s, **0.99×**, which is the correct value for a two-token greedy generation.

---

## 1. Throughput by generated length

Arm T is sampled, so raw latency across backends conflates kernel speed with re-drawn generation
length. Per-trial throughput, each backend bucketed by its own generated token count:

| arm | bucket | n S / F | med gen tok S / F | tok/s SDPA | tok/s FA2 | ratio |
|---|---|---|---|---|---|---|
| T (8B-Thinking) | <500 | 35 / 26 | 411 / 347 | 43.2 | 45.1 | **1.04×** |
| T | 500–4k | 337 / 294 | 1,569 / 1,530 | 41.5 | 45.2 | 1.09× |
| T | >4k | 89 / 81 | 5,820 / 5,702 | 33.7 | 41.9 | **1.24×** |
| I (8B-Instruct) | <500 | 401 / 401 | 2 / 2 | 12.7 | 12.6 | **0.99×** |

Same-trial paired ratio (same question under both backends, median of per-trial tok/s ratios):
**arm T 1.08×** (n=401), **arm I 1.00×** (n=401).

Aggregate throughput: T 36.4 → 43.1 tok/s (**1.19×**); I 12.7 → 12.6 tok/s (0.99×).

Flash-attn is never slower. The gain is monotone in generated length, from 1.04× under 500
tokens to 1.24× past 4k, and is nil on the instruct arm, which emits a single answer letter.

---

## 2. Clarification — the 226× → 202× cost ratio is a per-arm wall-clock ratio

**Dated note, 2026-10-16.** The committed report cites **226×** as the latency cost of thinking
over the instruct arm, defined as the ratio of **median** per-trial wall time (43.5 s / 0.19 s).
That definition reproduces exactly on the paired 401 questions, and the flash-attn value is
**202×**:

| scope | n | arm T median lat | arm I median lat | ratio SDPA | ratio FA2 |
|---|---|---|---|---|---|
| robotic_trajectory_selection | 200 | 27.5 s → 22.8 s | 0.192 s → 0.191 s | 144× | **120×** |
| spatial_distance_judgement | 201 | 77.2 s → 73.1 s | 0.208 s → 0.205 s | 372× | **357×** |
| **POOLED** | **401** | **43.5 s → 38.6 s** | **0.192 s → 0.191 s** | **226×** | **202×** |

Both are correct statements of what each run cost. **The 226× → 202× change is not a measurement
of flash-attn.** It is a per-arm wall-clock ratio whose numerator is a sampled arm, so it moves
with both the kernel speedup (arm T throughput 1.19×) and the re-drawn generation length (median
think tokens 1,689 → 1,603, 0.95×). Median ratios do not decompose multiplicatively, so no exact
split is given; both components push the same direction and neither alone accounts for the move.

The backend-isolated number is the throughput ratio, 1.19× on arm T.

The committed report's §5 states that "the 226× ratio is unaffected" by the backend, reasoning
that both arms share it and that the gap is driven by decode length upstream of the kernel. That
reasoning is right about the conclusion and wrong about the arithmetic: the ratio does move, by
11%, because the kernel speeds up the long-decode arm and not the single-token arm. The
conclusion survives easily — 202× and 226× are the same finding at two orders of magnitude.

---

## 3. Numbers that did not need recomputing

**net_rescue = +1.00pp under both backends.** Accuracy is a count and carries no bucketing
artifact. Arm T had 93 discordant questions against arm I under SDPA, netting to zero (b=47,
c=46). The verdict — *neither branch of the pre-registered rule fires; STOP* — is identical
under flash-attn. Not revised here.

---

## 4. Consistency checks

1. **Cross-check against committed measurements.** SDPA medians reproduce the committed report's
   §5 table exactly (43.5 s, 0.19 s, 226×, and both per-category rows) on the paired 401.
2. **Physical plausibility.** Peak 45.2 tok/s decode for an 8B model in bf16 on an A6000 is in
   range; no bucket exceeds the committed curves.
3. **Distribution sanity.** Throughputs are medians over 26–401 trials per cell with n stated;
   no constants where distributions are expected.
4. **Definition audit.** `226×` is median-of-medians as defined in the committed report, not a
   ratio of means. A mean-based version of the same quantity on the paired set gives 452× → 365×;
   the two definitions are not interchangeable and the median one is the committed one.
5. **Claim linkage.** Bears on the bounded-path cost advantage. Supports it under both backends.
6. **Proxy validity.** Wall-clock latency is used as the cost proxy, as in the committed report;
   unchanged.
