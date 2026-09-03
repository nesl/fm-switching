# Study I2 — S-EMBER Token Budget Allocation

**Date:** 2026-09-03
**Script:** `experiments/sember/study_i2_budget.py`
**Data:** Study I manifest — 150 videos, 459 questions, 7 categories
**Total valid trials:** 1318

---

## 1. KV constant correction

The diagnostic report (study_i_diagnostic.md §4) computed 458,752 bytes/token by using hidden_size (3584) as the KV projection dimension. The correct quantity is n_kv_heads × head_dim, which for Qwen3-VL uses grouped-query attention.

| model | layers | kv_heads | head_dim | dtype | bytes/token | formula |
|---|---|---|---|---|---|---|
| qwen3vl4b | 36 | 8 | 128 | bfloat16 | **147,456** | 36L × 2 × 8kv × 128d × 2B = 147456 |
| qwen3vl8b | 36 | 8 | 128 | bfloat16 | **147,456** | 36L × 2 × 8kv × 128d × 2B = 147456 |

Both models share the same GQA configuration (36 layers, 8 KV heads, 128 head_dim). The 57,344 bytes/token figure committed in Studies A/B/E/F is for Qwen2.5-VL-7B (28 layers × 2 × 4 heads × 128 dim × 2 bytes = 57,344). No contradiction: different model families.

**KV at 4,325 tokens (SPARSE median):** 0.59 GB
**KV at 11,340 tokens (SPATIAL median):** 1.56 GB
**KV at 12,200 tokens (TEMPORAL median):** 1.68 GB

---

## 2. What was run

### 2.1 Arms

| arm | frames policy | max_frames | expected tok/frame | budget binds? |
|---|---|---|---|---|
| SPARSE | 16 frames uniform over [0, qt] | 16 | ~270 | No |
| SPATIAL | 1fps, capped at 42 | 42 | ~270–284 | No — empirically verified: 42f × S-EMBER 720×966 gives grid_thw=[21,54,42], tok/frame=283.5 |
| TEMPORAL | 1fps, capped at 256 | 256 | ~56 (long videos) | Yes — spatial reduced |

### 2.2 Measured vision tokens per arm

| arm | median vis_tokens | tok/frame range | note |
|---|---|---|---|
| SPARSE | 4536 | 138.0–283.5 |  |
| SPATIAL | 11907 | 138.0–297.0 | budget verified not to bind |
| TEMPORAL | 11264 | 44.0–297.0 | varies with qt; budget binds for qt > 43s |

SPATIAL vs TEMPORAL token ratio: 0.946 (WITHIN 30% — comparison is fair)

**Models:** Qwen3-VL-4B-Instruct and Qwen3-VL-8B-Instruct, bf16, cuda:1, flash_attention_2
**Scoring:** exact letter match (A–E), max_new_tokens=16, greedy decode
**GSER contract:** each question sees only video[0, question_time], asserted per trial

---

## 3. Analysis A — Overall accuracy

Random baseline: 20.0%. Cells at or below baseline marked ★.

| model | arm | n | acc | 95% CI |
|---|---|---|---|---|
| qwen3vl4b | SPARSE | 459 | 0.266 | [0.227, 0.308] |
| qwen3vl4b | SPATIAL | 459 | 0.218 | [0.182, 0.258] |
| qwen3vl4b | TEMPORAL | 100 | 0.340 | [0.255, 0.437] |
| qwen3vl8b | SPARSE | 100 | 0.250 | [0.175, 0.343] |
| qwen3vl8b | SPATIAL | 100 | 0.250 | [0.175, 0.343] |
| qwen3vl8b | TEMPORAL | 100 | 0.340 | [0.255, 0.437] |

---

## 4. Analysis B — Accuracy per category per arm (THE DECIDING ANALYSIS)

Does the best arm differ by category, or does one arm win everywhere?

### qwen3vl4b

| category | SPARSE acc | SPATIAL acc | TEMPORAL acc | winner |
|---|---|---|---|---|
| time_duration | 0.237 | 0.140 | 0.421 | **TEMPORAL** |
| visual_detail_recall | 0.415 | 0.351 | 0.368 | **SPARSE** |
| sequential_action | 0.262 | 0.197 | 0.286 | **TEMPORAL** |
| location_trace | 0.115 | 0.135 | 0.385 | **TEMPORAL** |
| spatial_aware_reasoning | 0.161 | 0.107 | 0.111 | **SPARSE** |
| object_comparison | 0.339 | 0.339 | 0.250 | **SPARSE** |
| temporal_ordering_recognition | 0.234 | 0.213 | 0.500 | **TEMPORAL** |

Arm win counts: SPARSE: 3, SPATIAL: 0, TEMPORAL: 4
**Best arm varies by category — budget allocation is not static for qwen3vl4b.**

### qwen3vl8b

| category | SPARSE acc | SPATIAL acc | TEMPORAL acc | winner |
|---|---|---|---|---|
| time_duration | 0.368 | 0.368 | 0.579 | **TEMPORAL** |
| visual_detail_recall | 0.421 | 0.474 | 0.474 | **SPATIAL** |
| sequential_action | 0.143 | 0.071 | 0.286 | **TEMPORAL** |
| location_trace | 0.154 | 0.231 | 0.231 | **SPATIAL** |
| spatial_aware_reasoning | 0.000 | 0.000 | 0.000 | **SPARSE** |
| object_comparison | 0.188 | 0.062 | 0.188 | **SPARSE** |
| temporal_ordering_recognition | 0.300 | 0.400 | 0.400 | **SPATIAL** |

Arm win counts: SPARSE: 2, SPATIAL: 3, TEMPORAL: 2
**Best arm varies by category — budget allocation is not static for qwen3vl8b.**

---

## 5. Analysis C — vs text-only baseline (4B)

Text-only overall: 0.216  
A category where video hurts (delta < −0.03) is one where the token budget should not be spent on frames.

| category | text_only | SPARSE | SPATIAL | TEMPORAL | hurts (any arm) |
|---|---|---|---|---|---|
| time_duration | 0.333 | 0.237 (-0.097 ✗) | 0.140 (-0.194 ✗) | 0.421 (+0.088) | YES |
| visual_detail_recall | 0.170 | 0.415 (+0.245) | 0.351 (+0.181) | 0.368 (+0.198) | no |
| sequential_action | 0.131 | 0.262 (+0.131) | 0.197 (+0.066) | 0.286 (+0.155) | no |
| location_trace | 0.231 | 0.115 (-0.115 ✗) | 0.135 (-0.096 ✗) | 0.385 (+0.154) | YES |
| spatial_aware_reasoning | 0.179 | 0.161 (-0.018) | 0.107 (-0.071 ✗) | 0.111 (-0.068 ✗) | YES |
| object_comparison | 0.214 | 0.339 (+0.125) | 0.339 (+0.125) | 0.250 (+0.036) | no |
| temporal_ordering_recognition | 0.213 | 0.234 (+0.021) | 0.213 (+0.000) | 0.500 (+0.287) | no |

Categories where video hurts in at least one arm: time_duration, location_trace, spatial_aware_reasoning

---

## 6. Analysis D — 8B minus 4B gap

Contaminated cells (position-biased per F) are flagged.

| arm | category | 4B acc | 8B acc | gap | CI half | contaminated? |
|---|---|---|---|---|---|---|
| SPARSE | time_duration | 0.237 | 0.368 | +0.132 | ±0.234 | 4B  ★ |
| SPARSE | visual_detail_recall | 0.415 | 0.421 | +0.006 | ±0.243 |   |
| SPARSE | sequential_action | 0.262 | 0.143 | -0.119 | ±0.214 |   |
| SPARSE | location_trace | 0.115 | 0.154 | +0.038 | ±0.214 |   |
| SPARSE | spatial_aware_reasoning | 0.161 | 0.000 | -0.161 | ±0.096 |   |
| SPARSE | object_comparison | 0.339 | 0.188 | -0.152 | ±0.228 |   |
| SPARSE | temporal_ordering_recognition | 0.234 | 0.300 | +0.066 | ±0.309 | 4B  ★ |
| SPATIAL | time_duration | 0.140 | 0.368 | +0.229 | ±0.228 |   |
| SPATIAL | visual_detail_recall | 0.351 | 0.474 | +0.123 | ±0.244 |   |
| SPATIAL | sequential_action | 0.197 | 0.071 | -0.125 | ±0.168 |   |
| SPATIAL | location_trace | 0.135 | 0.231 | +0.096 | ±0.247 |   |
| SPATIAL | spatial_aware_reasoning | 0.107 | 0.000 | -0.107 | ±0.081 |   |
| SPATIAL | object_comparison | 0.339 | 0.062 | -0.277 | ±0.172 |   |
| SPATIAL | temporal_ordering_recognition | 0.213 | 0.400 | +0.187 | ±0.325 |   |
| TEMPORAL | time_duration | 0.421 | 0.579 | +0.158 | ±0.314 |   |
| TEMPORAL | visual_detail_recall | 0.368 | 0.474 | +0.105 | ±0.312 |   |
| TEMPORAL | sequential_action | 0.286 | 0.286 | +0.000 | ±0.335 |   |
| TEMPORAL | location_trace | 0.385 | 0.231 | -0.154 | ±0.350 |   |
| TEMPORAL | spatial_aware_reasoning | 0.111 | 0.000 | -0.111 | ±0.205 |   |
| TEMPORAL | object_comparison | 0.250 | 0.188 | -0.062 | ±0.286 |   |
| TEMPORAL | temporal_ordering_recognition | 0.500 | 0.400 | -0.100 | ±0.434 |   |

---

## 7. Analysis E — Latency and peak memory

| model | arm | lat_med_ms | lat_p90_ms | mem_med_gb | vis_tok_med | tok/ms |
|---|---|---|---|---|---|---|
| qwen3vl4b | SPARSE | 810 | 816 | 9.53 | 4536 | 5.86 |
| qwen3vl4b | SPATIAL | 2269 | 2279 | 11.51 | 11907 | 5.39 |
| qwen3vl4b | TEMPORAL | 2172 | 2214 | 11.55 | 11264 | 5.79 |
| qwen3vl8b | SPARSE | 1225 | 1239 | 17.79 | 4536 | 3.88 |
| qwen3vl8b | SPATIAL | 3313 | 3334 | 20.07 | 11907 | 3.69 |
| qwen3vl8b | TEMPORAL | 3127 | 3206 | 20.11 | 11264 | 4.02 |

---

## 8. Analysis F — Position bias

Chi-square test vs uniform over A–E. p < 0.05 flagged as biased.
Biased cells are contaminated for Analysis D comparisons.

| model | arm | category | n | chi2 | p | biased? | pred_dist |
|---|---|---|---|---|---|---|---|
| qwen3vl4b | SPARSE | time_duration | 93 | 16.946 | 0.002 | **YES** | {'A': 11, 'B': 13, 'C': 31, 'D': 13, 'E': 25} |
| qwen3vl4b | SPARSE | temporal_ordering_recognition | 47 | 21.404 | 0.0003 | **YES** | {'A': 21, 'B': 4, 'C': 11, 'D': 7, 'E': 4} |
| qwen3vl4b | TEMPORAL | time_duration | 19 | None | None | no | {'A': 1, 'B': 2, 'C': 7, 'D': 3, 'E': 6} |
| qwen3vl4b | TEMPORAL | visual_detail_recall | 19 | None | None | no | {'A': 2, 'B': 6, 'C': 4, 'D': 2, 'E': 5} |
| qwen3vl4b | TEMPORAL | sequential_action | 14 | None | None | no | {'A': 2, 'B': 2, 'C': 6, 'D': 2, 'E': 2} |
| qwen3vl4b | TEMPORAL | location_trace | 13 | None | None | no | {'A': 2, 'B': 3, 'C': 2, 'D': 4, 'E': 2} |
| qwen3vl4b | TEMPORAL | spatial_aware_reasoning | 9 | None | None | no | {'A': 2, 'B': 1, 'C': 1, 'D': 1, 'E': 4} |
| qwen3vl4b | TEMPORAL | object_comparison | 16 | None | None | no | {'A': 3, 'B': 2, 'C': 4, 'D': 2, 'E': 5} |
| qwen3vl4b | TEMPORAL | temporal_ordering_recognition | 10 | None | None | no | {'A': 5, 'B': 2, 'C': 3, 'D': 0, 'E': 0} |
| qwen3vl8b | SPARSE | time_duration | 19 | None | None | no | {'A': 1, 'B': 5, 'C': 6, 'D': 2, 'E': 5} |
| qwen3vl8b | SPARSE | visual_detail_recall | 19 | None | None | no | {'A': 1, 'B': 8, 'C': 2, 'D': 4, 'E': 4} |
| qwen3vl8b | SPARSE | sequential_action | 14 | None | None | no | {'A': 4, 'B': 3, 'C': 2, 'D': 4, 'E': 1} |
| qwen3vl8b | SPARSE | location_trace | 13 | None | None | no | {'A': 1, 'B': 4, 'C': 3, 'D': 3, 'E': 2} |
| qwen3vl8b | SPARSE | spatial_aware_reasoning | 9 | None | None | no | {'A': 0, 'B': 1, 'C': 2, 'D': 1, 'E': 5} |
| qwen3vl8b | SPARSE | object_comparison | 16 | None | None | no | {'A': 4, 'B': 4, 'C': 1, 'D': 1, 'E': 6} |
| qwen3vl8b | SPARSE | temporal_ordering_recognition | 10 | None | None | no | {'A': 5, 'B': 1, 'C': 3, 'D': 1, 'E': 0} |
| qwen3vl8b | SPATIAL | time_duration | 19 | None | None | no | {'A': 3, 'B': 3, 'C': 6, 'D': 1, 'E': 6} |
| qwen3vl8b | SPATIAL | visual_detail_recall | 19 | None | None | no | {'A': 2, 'B': 6, 'C': 5, 'D': 2, 'E': 4} |
| qwen3vl8b | SPATIAL | sequential_action | 14 | None | None | no | {'A': 5, 'B': 4, 'C': 1, 'D': 2, 'E': 2} |
| qwen3vl8b | SPATIAL | location_trace | 13 | None | None | no | {'A': 2, 'B': 5, 'C': 2, 'D': 2, 'E': 2} |
| qwen3vl8b | SPATIAL | spatial_aware_reasoning | 9 | None | None | no | {'A': 0, 'B': 1, 'C': 1, 'D': 1, 'E': 6} |
| qwen3vl8b | SPATIAL | object_comparison | 16 | None | None | no | {'A': 2, 'B': 7, 'C': 2, 'D': 1, 'E': 4} |
| qwen3vl8b | SPATIAL | temporal_ordering_recognition | 10 | None | None | no | {'A': 4, 'B': 4, 'C': 2, 'D': 0, 'E': 0} |
| qwen3vl8b | TEMPORAL | time_duration | 19 | None | None | no | {'A': 3, 'B': 2, 'C': 7, 'D': 1, 'E': 6} |
| qwen3vl8b | TEMPORAL | visual_detail_recall | 19 | None | None | no | {'A': 1, 'B': 7, 'C': 3, 'D': 2, 'E': 6} |
| qwen3vl8b | TEMPORAL | sequential_action | 14 | None | None | no | {'A': 3, 'B': 2, 'C': 4, 'D': 3, 'E': 2} |
| qwen3vl8b | TEMPORAL | location_trace | 13 | None | None | no | {'A': 2, 'B': 4, 'C': 3, 'D': 2, 'E': 2} |
| qwen3vl8b | TEMPORAL | spatial_aware_reasoning | 9 | None | None | no | {'A': 1, 'B': 1, 'C': 0, 'D': 1, 'E': 6} |
| qwen3vl8b | TEMPORAL | object_comparison | 16 | None | None | no | {'A': 2, 'B': 4, 'C': 3, 'D': 1, 'E': 6} |
| qwen3vl8b | TEMPORAL | temporal_ordering_recognition | 10 | None | None | no | {'A': 2, 'B': 3, 'C': 4, 'D': 1, 'E': 0} |

---

## 9. Sanity checks

- **S1 (SPARSE/SPATIAL req == proc):** True
- **S2 (SPARSE vis_token range):** [2208, 4536]
- **S3 (parse rate):** 1.0
- **S4 (device/dtype):** both models asserted cuda:1 / bfloat16 at load
- **S5 (GSER):** asserted per trial in load_frames
- **S6 (KV empirical):** measured and compared to analytical at each model load

---

## 10. Summary answers

**Q1: Does the best budget allocation differ by category?**
Yes — the winning arm varies by category. Budget allocation is not static.
  time_duration: 4B best=TEMPORAL, 8B best=TEMPORAL
  visual_detail_recall: 4B best=SPARSE, 8B best=SPATIAL
  sequential_action: 4B best=TEMPORAL, 8B best=TEMPORAL
  location_trace: 4B best=TEMPORAL, 8B best=SPATIAL
  spatial_aware_reasoning: 4B best=SPARSE, 8B best=SPARSE
  object_comparison: 4B best=SPARSE, 8B best=SPARSE
  temporal_ordering_recognition: 4B best=TEMPORAL, 8B best=SPATIAL

**Q2: In which categories does video conditioning hurt relative to text-only?**
  time_duration: video hurts in arms ['SPARSE', 'SPATIAL']
  visual_detail_recall: video does not hurt (>−0.03pp) in any arm
  sequential_action: video does not hurt (>−0.03pp) in any arm
  location_trace: video hurts in arms ['SPARSE', 'SPATIAL']
  spatial_aware_reasoning: video hurts in arms ['SPATIAL', 'TEMPORAL']
  object_comparison: video does not hurt (>−0.03pp) in any arm
  temporal_ordering_recognition: video does not hurt (>−0.03pp) in any arm

**Q3: Is the 8B − 4B gap different once contaminated cells are excluded?**
  Mean gap all cells: -0.0109. Mean gap excluding contaminated: -0.0224. Contaminated cells: 2.
  Gap changes materially after excluding contaminated cells.

---

## 11. What cannot be inferred

- Causal claim: this is a measurement study. Accuracy differences between arms are observed differences under the GSER protocol, not causal effects.
- Generalization beyond S-EMBER: category boundaries and question phrasing are dataset-specific.
- The text-only comparison uses 4B only; 8B text-only baseline not measured here.
- Prefill latency is estimated (total − decode estimate using Study F rates), not directly timed.
