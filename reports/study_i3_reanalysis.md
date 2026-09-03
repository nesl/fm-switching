# Study I3 Re-analysis — Paired Tests and Corrected Accounting

**Date:** 2026-09-03
**Input:** `results/sember/study_i3/study_i3_trials.jsonl` (1,836 trials)
**Script:** `experiments/sember/study_i3_reanalyse.py`
**Supersedes:** Study I3 Analysis (reports/study_i3_budget.md) — that report's Analysis B used independent-sample CIs on paired data.

---

## 1. What Was Recomputed and From Which Files

All analyses use the per-trial JSONL. No new inference was run.

**Three defects fixed:**

**Defect 1 (wrong test):** Study I3 compared independent-sample Wilson CIs. Because SPARSE and TEMPORAL ran on the *same* 459 questions with the *same* model, the data are paired. McNemar's test is the correct test. Independent CIs ignore between-question correlation and inflate the standard error, making real differences harder to detect.

**Defect 2 (latency):** Study I3 Analysis E reported 8B SPARSE median = 5,295 ms against 1,225 ms in Study I2 for the same arm — a 4.3× discrepancy. Root cause: in I3, fresh trials measure `total_latency_ms = decode + preprocess + forward` (video-seek decode tracked), while reused I2 trials measure `total_latency_ms = inference only`. Study I3 compared these two quantities as if they were the same. They are not. Corrected table below uses inference-only time consistently.

**Defect 3 (reuse header):** The I3 report header states 'Reused from study_i2: 0 trials'. This contradicts Section 1.2. Actual counts from per-trial records:

| cell | reused from I2 | run fresh in I3 |
|---|---|---|
| qwen3vl4b_SPARSE | 459 | 0 |
| qwen3vl4b_TEMPORAL | 100 | 359 |
| qwen3vl8b_SPARSE | 100 | 359 |
| qwen3vl8b_TEMPORAL | 100 | 359 |

The header figure is wrong. The correct total reused is 759 trials.

---

## 2. Sanity Checks

- **Trial counts:** all four cells 459/459 — PASS
- **Pairing:** SPARSE question_id set == TEMPORAL question_id set for both models — PASS
- **Accuracy reproduction:** recomputed unpaired accuracies match Study I3 Analysis A to within 1e-4 for all four cells — PASS
- **Contingency sums:** a+b+c+d == n for every tested cell — PASS

---

## 3. Paired Per-Category Results (McNemar's Test with BH Correction)

**Legend:** b = SPARSE correct, TEMPORAL wrong; c = SPARSE wrong, TEMPORAL correct.
Positive paired_diff means TEMPORAL wins. BH correction across 7 categories per model.
Sig* = significant after BH correction (adj_p < 0.05).

### qwen3vl4b

**Overall (n=459):** SPARSE=0.266 TEMPORAL=0.292 diff=+0.026 95%CI=[-0.015,+0.068] b=39 c=51 p=0.2463 (chisq_continuity)

| category | n | b | c | SPARSE_acc | TEMPORAL_acc | paired_diff | 95%CI | raw_p | adj_p_BH | method | sig? |
|---|---|---|---|---|---|---|---|---|---|---|---|
| time_duration | 93 | 2 | 8 | 0.237 | 0.301 | +0.065 | [+0.000,+0.129] | 0.1094 | 0.7656 | exact_binomial | no |
| visual_detail_recall | 94 | 10 | 12 | 0.415 | 0.436 | +0.021 | [-0.074,+0.117] | 0.8318 | 1.0000 | exact_binomial | no |
| sequential_action | 61 | 8 | 10 | 0.262 | 0.295 | +0.033 | [-0.098,+0.164] | 0.8145 | 1.0000 | exact_binomial | no |
| location_trace | 52 | 3 | 8 | 0.115 | 0.211 | +0.096 | [-0.019,+0.211] | 0.2266 | 0.7930 | exact_binomial | no |
| spatial_aware_reasoning | 56 | 3 | 3 | 0.161 | 0.161 | +0.000 | [-0.089,+0.089] | 1.0000 | 1.0000 | exact_binomial | no |
| object_comparison | 56 | 9 | 6 | 0.339 | 0.286 | -0.054 | [-0.196,+0.089] | 0.6072 | 1.0000 | exact_binomial | no |
| temporal_ordering_recognition | 47 | 4 | 4 | 0.234 | 0.234 | +0.000 | [-0.106,+0.128] | 1.0000 | 1.0000 | exact_binomial | no |

### qwen3vl8b

**Overall (n=459):** SPARSE=0.272 TEMPORAL=0.320 diff=+0.048 95%CI=[+0.004,+0.094] b=45 c=67 p=0.0472 (chisq_continuity)

| category | n | b | c | SPARSE_acc | TEMPORAL_acc | paired_diff | 95%CI | raw_p | adj_p_BH | method | sig? |
|---|---|---|---|---|---|---|---|---|---|---|---|
| time_duration | 93 | 5 | 11 | 0.301 | 0.366 | +0.065 | [-0.021,+0.150] | 0.2101 | 0.5370 | exact_binomial | no |
| visual_detail_recall | 94 | 13 | 12 | 0.436 | 0.425 | -0.011 | [-0.117,+0.096] | 1.0000 | 1.0000 | chisq_continuity | no |
| sequential_action | 61 | 9 | 16 | 0.197 | 0.311 | +0.115 | [-0.049,+0.279] | 0.2301 | 0.5370 | chisq_continuity | no |
| location_trace | 52 | 3 | 8 | 0.192 | 0.288 | +0.096 | [-0.019,+0.211] | 0.2266 | 0.5370 | exact_binomial | no |
| spatial_aware_reasoning | 56 | 1 | 2 | 0.089 | 0.107 | +0.018 | [-0.036,+0.089] | 1.0000 | 1.0000 | exact_binomial | no |
| object_comparison | 56 | 9 | 9 | 0.304 | 0.304 | +0.000 | [-0.143,+0.143] | 1.0000 | 1.0000 | exact_binomial | no |
| temporal_ordering_recognition | 47 | 5 | 9 | 0.255 | 0.340 | +0.085 | [-0.064,+0.234] | 0.4239 | 0.7419 | exact_binomial | no |

## 4. Allocation Verdict

### qwen3vl4b

- Categories where TEMPORAL significantly better (after BH): 0 — none
- Categories where SPARSE significantly better (after BH): 0 — none
- No significant difference: 7

**VERDICT:** INCONCLUSIVE: No category reaches significance after BH correction. The comparison remains inconclusive even under the paired test.

### qwen3vl8b

- Categories where TEMPORAL significantly better (after BH): 0 — none
- Categories where SPARSE significantly better (after BH): 0 — none
- No significant difference: 7

**VERDICT:** INCONCLUSIVE: No category reaches significance after BH correction. The comparison remains inconclusive even under the paired test.

---

## 5. Paired Distance Analysis (Analysis C)

Paired SPARSE vs TEMPORAL, per farthest_dist_s bin. Both models shown.

### qwen3vl4b

| bin | n | b | c | paired_diff | 95%CI | raw_p | method |
|---|---|---|---|---|---|---|---|
| (0, 30) | 67 | 7 | 11 | +0.060 | [-0.060,+0.179] | 0.4807 | exact_binomial |
| (30, 60) | 134 | 12 | 13 | +0.007 | [-0.067,+0.082] | 1.0000 | chisq_continuity |
| (60, 120) | 124 | 7 | 16 | +0.073 | [+0.000,+0.145] | 0.0931 | exact_binomial |
| (120, 300) | 103 | 11 | 10 | -0.010 | [-0.097,+0.078] | 1.0000 | exact_binomial |
| (300, inf) | 31 | 2 | 1 | -0.032 | [-0.161,+0.065] | 1.0000 | exact_binomial |

### qwen3vl8b

| bin | n | b | c | paired_diff | 95%CI | raw_p | method |
|---|---|---|---|---|---|---|---|
| (0, 30) | 67 | 5 | 12 | +0.104 | [-0.015,+0.224] | 0.1435 | exact_binomial |
| (30, 60) | 134 | 17 | 16 | -0.007 | [-0.090,+0.075] | 1.0000 | chisq_continuity |
| (60, 120) | 124 | 14 | 22 | +0.065 | [-0.032,+0.161] | 0.2433 | chisq_continuity |
| (120, 300) | 103 | 5 | 15 | +0.097 | [+0.019,+0.184] | 0.0414 | exact_binomial |
| (300, inf) | 31 | 4 | 2 | -0.065 | [-0.226,+0.097] | 0.6875 | exact_binomial |

Note: BH correction not applied to distance bins (exploratory). p-values are uncorrected.

---

## 6. Paired Model-Gap Analysis (Analysis D: 8B vs 4B)

Positive diff = 8B better. BH correction across 7 categories per arm.

### SPARSE arm

**Overall:** 4B=0.266 8B=0.272 diff=+0.006 CI=[-0.033,+0.046] b=40 c=43 p=0.8262 (chisq_continuity)

| category | n | b | c | 4B_acc | 8B_acc | diff | 95%CI | raw_p | adj_p_BH | sig? |
|---|---|---|---|---|---|---|---|---|---|---|
| time_duration | 93 | 5 | 11 | 0.237 | 0.301 | +0.065 | [-0.021,+0.150] | 0.2101 | 0.6016 | no |
| visual_detail_recall | 94 | 8 | 10 | 0.415 | 0.436 | +0.021 | [-0.064,+0.106] | 0.8145 | 0.9503 | no |
| sequential_action | 61 | 6 | 2 | 0.262 | 0.197 | -0.066 | [-0.164,+0.016] | 0.2891 | 0.6016 | no |
| location_trace | 52 | 3 | 7 | 0.115 | 0.192 | +0.077 | [-0.038,+0.192] | 0.3438 | 0.6016 | no |
| spatial_aware_reasoning | 56 | 6 | 2 | 0.161 | 0.089 | -0.071 | [-0.179,+0.018] | 0.2891 | 0.6016 | no |
| object_comparison | 56 | 8 | 6 | 0.339 | 0.304 | -0.036 | [-0.161,+0.089] | 0.7905 | 0.9503 | no |
| temporal_ordering_recognition | 47 | 4 | 5 | 0.234 | 0.255 | +0.021 | [-0.106,+0.149] | 1.0000 | 1.0000 | no |

### TEMPORAL arm

**Overall:** 4B=0.292 8B=0.320 diff=+0.028 CI=[-0.011,+0.068] b=37 c=50 p=0.1983 (chisq_continuity)

| category | n | b | c | 4B_acc | 8B_acc | diff | 95%CI | raw_p | adj_p_BH | sig? |
|---|---|---|---|---|---|---|---|---|---|---|
| time_duration | 93 | 7 | 13 | 0.301 | 0.366 | +0.065 | [-0.032,+0.161] | 0.2632 | 0.7954 | no |
| visual_detail_recall | 94 | 7 | 6 | 0.436 | 0.425 | -0.011 | [-0.085,+0.064] | 1.0000 | 1.0000 | no |
| sequential_action | 61 | 5 | 6 | 0.295 | 0.311 | +0.016 | [-0.098,+0.115] | 1.0000 | 1.0000 | no |
| location_trace | 52 | 6 | 10 | 0.211 | 0.288 | +0.077 | [-0.077,+0.231] | 0.4545 | 0.7954 | no |
| spatial_aware_reasoning | 56 | 5 | 2 | 0.161 | 0.107 | -0.054 | [-0.143,+0.036] | 0.4531 | 0.7954 | no |
| object_comparison | 56 | 3 | 4 | 0.286 | 0.304 | +0.018 | [-0.071,+0.107] | 1.0000 | 1.0000 | no |
| temporal_ordering_recognition | 47 | 4 | 9 | 0.234 | 0.340 | +0.106 | [-0.043,+0.255] | 0.2668 | 0.7954 | no |

---

## 7. Corrected Latency Accounting

**Root cause of Defect 2:** In Study I3, fresh trials measure `total_latency_ms = video_decode + preprocess + forward`. Reused I2 trials measure `total_latency_ms = prefill + generation (inference only)`. Study I3 Analysis E averaged these two quantities together in one column, making 8B SPARSE appear 4.3× slower than in I2 (5,295 ms vs 1,225 ms). The 4,374 ms difference is entirely video-seek decode for 16 frames, not model inference.

**Corrected inference-only latency** uses `forward_ms` for fresh I3 trials and `prefill_ms_est` for reused I2 trials (both measure model forward wall time; output is 2 tokens so autoregressive contribution is negligible).

| cell | n_reused | n_fresh | total_lat_med_ms | infer_only_med_ms | decode_fresh_med_ms | forward_fresh_med_ms |
|---|---|---|---|---|---|---|
| qwen3vl4b_SPARSE | 459 | 0 | 810 | 769 | — (no fresh trials) | — (no fresh trials) |
| qwen3vl4b_TEMPORAL | 100 | 359 | 5871 | 2235 | 2436 | 2249 |
| qwen3vl8b_SPARSE | 100 | 359 | 5295 | 1228 | 4374 | 1229 |
| qwen3vl8b_TEMPORAL | 100 | 359 | 7029 | 3255 | 2431 | 3267 |

**Cross-check 8B SPARSE:** I2 inference median = 1224.8 ms, I3 inference-only median (forward_ms, fresh trials) = 1227.8 ms, ratio = 1.002 — AGREE.

**The 7.2× and 1.3× ratios from Study I3 Analysis E are not reproducible** from consistent measurements.
Corrected inference-only ratios (using infer_only_med_ms):
- 4B TEMPORAL / 4B SPARSE = 2.91×
- 8B TEMPORAL / 8B SPARSE = 2.65×

Note: 4B SPARSE is entirely reused from I2 (no fresh I3 trials), so its inference latency comes from I2's measurement context. The corrected ratio for 4B uses I2 prefill_ms_est for all SPARSE trials and forward_ms for fresh TEMPORAL trials; the mix is not perfectly comparable but is substantially better than the total_latency_ms mix.

---

## 8. Position Bias: Bias-Only Baseline

Study I3 found significant letter-choice bias (chi-square vs uniform) in all four overall cells.
A bias-only baseline computes: for each question, what is the probability a model guessing
from its own marginal letter distribution gives the correct answer?
This bounds how much of the measured accuracy is explainable by letter preference alone.

| cell | marginal A | B | C | D | E | bias_only_acc | measured_acc | lift_over_bias |
|---|---|---|---|---|---|---|---|---|---|
| qwen3vl4b_SPARSE | 0.194 | 0.150 | 0.261 | 0.174 | 0.220 | 0.199 | 0.266 | +0.067 |
| qwen3vl4b_TEMPORAL | 0.224 | 0.157 | 0.242 | 0.161 | 0.216 | 0.200 | 0.292 | +0.092 |
| qwen3vl8b_SPARSE | 0.137 | 0.233 | 0.264 | 0.137 | 0.229 | 0.196 | 0.272 | +0.076 |
| qwen3vl8b_TEMPORAL | 0.181 | 0.233 | 0.222 | 0.142 | 0.222 | 0.198 | 0.320 | +0.123 |

**Interpretation:** `lift_over_bias` is the accuracy gap between the model's actual performance
and what pure letter preference predicts. A small lift would indicate the cell is measuring
letter preference rather than video understanding.

---

## 9. Plain-Language Summary

**Under the paired test, does TEMPORAL beat SPARSE, and where?**

- **qwen3vl4b:** overall TEMPORAL−SPARSE = +0.026 (CI [-0.015,+0.068], p=0.2463). INCONCLUSIVE: No category reaches significance after BH correction. The comparison remains inconclusive even under the paired test.

- **qwen3vl8b:** overall TEMPORAL−SPARSE = +0.048 (CI [+0.004,+0.094], p=0.0472). INCONCLUSIVE: No category reaches significance after BH correction. The comparison remains inconclusive even under the paired test.

**Is the allocation static or category-dependent?**

- **qwen3vl4b:** INCONCLUSIVE: No category reaches significance after BH correction. The comparison remains inconclusive even under the p...

- **qwen3vl8b:** INCONCLUSIVE: No category reaches significance after BH correction. The comparison remains inconclusive even under the p...

**How much of the measured accuracy could letter bias alone account for?**

- qwen3vl4b_SPARSE: measured=0.266, bias-only=0.199, lift=+0.067. Measured accuracy meaningfully exceeds bias-only baseline.
- qwen3vl4b_TEMPORAL: measured=0.292, bias-only=0.200, lift=+0.092. Measured accuracy meaningfully exceeds bias-only baseline.
- qwen3vl8b_SPARSE: measured=0.272, bias-only=0.196, lift=+0.076. Measured accuracy meaningfully exceeds bias-only baseline.
- qwen3vl8b_TEMPORAL: measured=0.320, bias-only=0.198, lift=+0.123. Measured accuracy meaningfully exceeds bias-only baseline.

---

## 10. What Cannot Be Inferred

- **4B SPARSE inference latency from I3 directly:** all 459 trials are reused from I2; no `forward_ms` exists in the I3 JSONL for that cell.
- **TEMPORAL decode overhead vs I2:** I2 used per-frame seeks (no decode tracking); I3 used sequential cache (amortised per video). The two decode numbers are not on the same footing.
- **Position bias correction:** would require rerunning with permuted option orders.
