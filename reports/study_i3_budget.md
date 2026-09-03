# Study I3 — S-EMBER SPARSE vs TEMPORAL at Full Power

**Date:** 2026-09-03
**Script:** `experiments/sember/study_i3_budget.py`
**Data:** Study I manifest — 150 videos, 459 questions, 7 categories
**Total valid trials:** 1836
**Reused from study_i2:** 0 trials (4B SPARSE n=459; 4B TEMPORAL, 8B SPARSE, 8B TEMPORAL n=100 each)

---

## 1. What was run and reuse decision

### 1.1 Arms (SPATIAL dropped from study_i2)

SPATIAL was dropped because study_i2 at full n=459 showed SPATIAL worse than SPARSE in 5 of 7 categories while using 2.6× more tokens and 2.8× more latency.

| arm | frame policy | max_frames | typical vis_tokens | budget binds? |
|---|---|---|---|---|
| SPARSE | 16 frames uniform [0, qt] | 16 | ~4,536 | No |
| TEMPORAL | 1fps [0, qt] | 256 | ~11,264 | Yes (spatial reduced for qt>43s) |

### 1.2 Reuse decision for 4B SPARSE

Study_i2 ran 4B SPARSE at n=459 with the same:
- Frame loading code path (SPARSE arm, 16 uniform frames, seek-based)
- Inference code (same processor settings, same VIDEO_TOKEN_ID count for vision_tokens)
- Model snapshot and tokenizer
- GSER assertion per trial

These 459 trials are copied verbatim with `reused_from: study_i2`. They are verified in S2 below: median vision_tokens matches I2 within 5%.
For 4B TEMPORAL, 8B SPARSE, 8B TEMPORAL, the 100 existing I2 trials are similarly copied as prior work; the remaining 359 per cell were run fresh.

### 1.3 Frame caching for TEMPORAL

Study I2 used per-frame backward seeks (256 seeks per question). Each seek is slow because PyAV must seek to the nearest keyframe and decode forward. The estimated overhead was ~73s of video-decode per TEMPORAL trial (vs ~2s inference), making 459 trials ≈ 9 hours of decode alone.

Study I3 groups questions by video and decodes each video ONCE sequentially (no backward seeks) up to max(question_time) for that video. Each question then slices the cached frame-dict. The GSER causal contract is preserved: `frames_from_cache()` retains only frames where timestamp ≤ question_time.

150 videos, median 3 questions/video (range 2–6). Decode cost amortised over questions sharing the same video.

### 1.4 Profiling breakdown

Profiling was skipped (4B model not loaded before analysis in this run).
Decode timings are captured per trial in the `decode_latency_ms` field.

---

## 2. Sanity checks

**S1 SPARSE req==proc:** PASS

**S2 Vision tokens vs I2 medians (within 5%):**

| arm | this run median | I2 median | ratio | verdict |
|---|---|---|---|---|
| SPARSE | 4536 | 4536 | 1.0 | PASS |
| TEMPORAL | 11264 | 11264 | 1.0 | PASS |

**S3 GSER:** GSER asserted per trial in load_frames_sparse_timed and frames_from_cache

**S4 Parse rate per cell:**

| cell | n | parse_ok | rate |
|---|---|---|---|
| qwen3vl4b_SPARSE | 459 | 459 | 1.0000 |
| qwen3vl4b_TEMPORAL | 459 | 459 | 1.0000 |
| qwen3vl8b_SPARSE | 459 | 459 | 1.0000 |
| qwen3vl8b_TEMPORAL | 459 | 459 | 1.0000 |

**S5 Device/dtype:** asserted per model load: dtype=bfloat16, device=cuda:1

---

## 3. Analysis A — Overall accuracy

Random baseline: 20.0%. Cells at or below baseline marked ★.

| model | arm | n | acc | 95% CI |
|---|---|---|---|---|
| qwen3vl4b | SPARSE | 459 | 0.266 | [0.227, 0.308] |
| qwen3vl4b | TEMPORAL | 459 | 0.292 | [0.252, 0.335] |
| qwen3vl8b | SPARSE | 459 | 0.272 | [0.234, 0.315] |
| qwen3vl8b | TEMPORAL | 459 | 0.320 | [0.279, 0.364] |

---

## 4. Analysis B — Per-category accuracy: THE DECIDING ANALYSIS

Winner declared only when |acc_SPARSE − acc_TEMPORAL| > combined half-width (√(hw_SPARSE² + hw_TEMPORAL²)). Point-estimate leaders are noted separately.

### qwen3vl4b

**Verdict:** UNDERPOWERED: no category shows difference exceeding combined CI

| category | SPARSE n | SPARSE acc | TEMPORAL n | TEMPORAL acc | diff | combined_hw | exceeds CI? | winner |
|---|---|---|---|---|---|---|---|---|
| time_duration | 93 | 0.237 [0.162,0.332] | 93 | 0.301 [0.217,0.401] | -0.065 | 0.125 | no | tie_or_underpowered |
| visual_detail_recall | 94 | 0.415 [0.321,0.516] | 94 | 0.436 [0.340,0.537] | -0.021 | 0.139 | no | tie_or_underpowered |
| sequential_action | 61 | 0.262 [0.168,0.384] | 61 | 0.295 [0.196,0.419] | -0.033 | 0.155 | no | tie_or_underpowered |
| location_trace | 52 | 0.115 [0.054,0.230] | 52 | 0.211 [0.122,0.340] | -0.096 | 0.140 | no | tie_or_underpowered |
| spatial_aware_reasoning | 56 | 0.161 [0.087,0.278] | 56 | 0.161 [0.087,0.278] | +0.000 | 0.135 | no | tie_or_underpowered |
| object_comparison | 56 | 0.339 [0.229,0.470] | 56 | 0.286 [0.184,0.415] | +0.054 | 0.167 | no | tie_or_underpowered |
| temporal_ordering_recognition | 47 | 0.234 [0.136,0.372] | 47 | 0.234 [0.136,0.372] | +0.000 | 0.167 | no | tie_or_underpowered |

### qwen3vl8b

**Verdict:** UNDERPOWERED: no category shows difference exceeding combined CI

| category | SPARSE n | SPARSE acc | TEMPORAL n | TEMPORAL acc | diff | combined_hw | exceeds CI? | winner |
|---|---|---|---|---|---|---|---|---|
| time_duration | 93 | 0.301 [0.217,0.401] | 93 | 0.366 [0.275,0.467] | -0.065 | 0.133 | no | tie_or_underpowered |
| visual_detail_recall | 94 | 0.436 [0.340,0.537] | 94 | 0.425 [0.330,0.526] | +0.011 | 0.139 | no | tie_or_underpowered |
| sequential_action | 61 | 0.197 [0.116,0.313] | 61 | 0.311 [0.209,0.436] | -0.115 | 0.150 | no | tie_or_underpowered |
| location_trace | 52 | 0.192 [0.108,0.319] | 52 | 0.288 [0.183,0.423] | -0.096 | 0.160 | no | tie_or_underpowered |
| spatial_aware_reasoning | 56 | 0.089 [0.039,0.193] | 56 | 0.107 [0.050,0.215] | -0.018 | 0.113 | no | tie_or_underpowered |
| object_comparison | 56 | 0.304 [0.199,0.433] | 56 | 0.304 [0.199,0.433] | +0.000 | 0.166 | no | tie_or_underpowered |
| temporal_ordering_recognition | 47 | 0.255 [0.152,0.395] | 47 | 0.340 [0.222,0.483] | -0.085 | 0.178 | no | tie_or_underpowered |

---

## 5. Analysis C — Accuracy vs evidence distance (4B model)

Bins by `farthest_dist_s` = question_time − answer_start_time.
Hypothesis: TEMPORAL helps most at large distance (SPARSE at 16 frames samples coarsely over long prefixes).

| distance bin | SPARSE n | SPARSE acc | TEMPORAL n | TEMPORAL acc | diff (T−S) | TEMPORAL helps? |
|---|---|---|---|---|---|---|
| [0,30) | 67 | 0.254 | 67 | 0.313 | +0.060 | yes |
| [30,60) | 134 | 0.298 | 134 | 0.306 | +0.007 | no |
| [60,120) | 124 | 0.250 | 124 | 0.323 | +0.073 | yes |
| [120,300) | 103 | 0.262 | 103 | 0.252 | -0.010 | no |
| [300,+) | 31 | 0.226 | 31 | 0.194 | -0.032 | no |

---

## 6. Analysis D — 8B minus 4B gap per arm per category

Cells marked DEGENERATE are excluded: acc≈0 with flagged position bias.

| arm | category | 4B acc (n) | 8B acc (n) | gap (8B−4B) | gap CI half | note |
|---|---|---|---|---|---|---|
| SPARSE | time_duration | 0.237 (93) | 0.301 (93) | +0.065 | 0.127 | contaminated_4b |
| SPARSE | visual_detail_recall | 0.415 (94) | 0.436 (94) | +0.021 | 0.141 |  |
| SPARSE | sequential_action | 0.262 (61) | 0.197 (61) | -0.066 | 0.149 |  |
| SPARSE | location_trace | 0.115 (52) | 0.192 (52) | +0.077 | 0.138 | contaminated_8b |
| SPARSE | spatial_aware_reasoning | 0.161 (56) | 0.089 (56) | -0.071 | 0.122 | contaminated_8b |
| SPARSE | object_comparison | 0.339 (56) | 0.304 (56) | -0.036 | 0.173 | contaminated_8b |
| SPARSE | temporal_ordering_recognition | 0.234 (47) | 0.255 (47) | +0.021 | 0.174 | contaminated_4b |
| TEMPORAL | time_duration | 0.301 (93) | 0.366 (93) | +0.065 | 0.135 |  |
| TEMPORAL | visual_detail_recall | 0.436 (94) | 0.425 (94) | -0.011 | 0.142 |  |
| TEMPORAL | sequential_action | 0.295 (61) | 0.311 (61) | +0.016 | 0.163 | contaminated_4b |
| TEMPORAL | location_trace | 0.211 (52) | 0.288 (52) | +0.077 | 0.166 |  |
| TEMPORAL | spatial_aware_reasoning | 0.161 (56) | 0.107 (56) | -0.054 | 0.126 |  |
| TEMPORAL | object_comparison | 0.286 (56) | 0.304 (56) | +0.018 | 0.169 |  |
| TEMPORAL | temporal_ordering_recognition | 0.234 (47) | 0.340 (47) | +0.106 | 0.182 | contaminated_4b |

---

## 7. Analysis E — Latency, tokens, peak memory

| model | arm | n | lat_med_ms | lat_p90_ms | decode_ms (n) | mem_med_gb | vis_tok_median | acc | acc/s |
|---|---|---|---|---|---|---|---|---|---|
| qwen3vl4b | SPARSE | 459 | 810 | 816 | — (reused) | 9.53 | 4536 | 0.266 | 0.3280 |
| qwen3vl4b | TEMPORAL | 459 | 5871 | 7876 | 3494 (n=359) | 11.55 | 11264 | 0.292 | 0.0497 |
| qwen3vl8b | SPARSE | 459 | 5295 | 7782 | 5946 (n=359) | 17.78 | 4536 | 0.272 | 0.0514 |
| qwen3vl8b | TEMPORAL | 459 | 7029 | 9060 | 3478 (n=359) | 20.11 | 11264 | 0.320 | 0.0456 |

**Accuracy/latency tradeoff:**
- qwen3vl4b: TEMPORAL is 7.2× slower than SPARSE; accuracy difference = +0.026
- qwen3vl8b: TEMPORAL is 1.3× slower than SPARSE; accuracy difference = +0.048

---

## 8. Analysis F — Position bias

Chi-square vs uniform A-E distribution. Cells with n < 25 (expected < 5 per option) are marked **not_testable** — not 'no bias'. This corrects study_i2's treatment of small cells.

| model | arm | cell | n | biased? | p_value | note |
|---|---|---|---|---|---|---|
| qwen3vl4b | SPARSE | overall | 459 | YES *** | 0.0021 |  |
| qwen3vl4b | SPARSE | time_duration | 93 | YES *** | 0.002 |  |
| qwen3vl4b | SPARSE | visual_detail_recall | 94 | no | 0.3672 |  |
| qwen3vl4b | SPARSE | sequential_action | 61 | no | 0.0824 |  |
| qwen3vl4b | SPARSE | location_trace | 52 | no | 0.7287 |  |
| qwen3vl4b | SPARSE | spatial_aware_reasoning | 56 | no | 0.2461 |  |
| qwen3vl4b | SPARSE | object_comparison | 56 | no | 0.9623 |  |
| qwen3vl4b | SPARSE | temporal_ordering_recognition | 47 | YES *** | 0.0003 |  |
| qwen3vl4b | TEMPORAL | overall | 459 | YES *** | 0.0084 |  |
| qwen3vl4b | TEMPORAL | time_duration | 93 | no | 0.0989 |  |
| qwen3vl4b | TEMPORAL | visual_detail_recall | 94 | no | 0.724 |  |
| qwen3vl4b | TEMPORAL | sequential_action | 61 | YES *** | 0.026 |  |
| qwen3vl4b | TEMPORAL | location_trace | 52 | no | 0.6585 |  |
| qwen3vl4b | TEMPORAL | spatial_aware_reasoning | 56 | no | 0.5698 |  |
| qwen3vl4b | TEMPORAL | object_comparison | 56 | no | 0.2461 |  |
| qwen3vl4b | TEMPORAL | temporal_ordering_recognition | 47 | YES *** | 0.001 |  |
| qwen3vl8b | SPARSE | overall | 459 | YES *** | 0.0 |  |
| qwen3vl8b | SPARSE | time_duration | 93 | YES *** | 0.0002 |  |
| qwen3vl8b | SPARSE | visual_detail_recall | 94 | no | 0.3289 |  |
| qwen3vl8b | SPARSE | sequential_action | 61 | no | 0.2143 |  |
| qwen3vl8b | SPARSE | location_trace | 52 | YES *** | 0.0145 |  |
| qwen3vl8b | SPARSE | spatial_aware_reasoning | 56 | YES *** | 0.0199 |  |
| qwen3vl8b | SPARSE | object_comparison | 56 | YES *** | 0.0455 |  |
| qwen3vl8b | SPARSE | temporal_ordering_recognition | 47 | no | 0.2444 |  |
| qwen3vl8b | TEMPORAL | overall | 459 | YES *** | 0.0093 |  |
| qwen3vl8b | TEMPORAL | time_duration | 93 | no | 0.0538 |  |
| qwen3vl8b | TEMPORAL | visual_detail_recall | 94 | no | 0.0765 |  |
| qwen3vl8b | TEMPORAL | sequential_action | 61 | no | 0.5828 |  |
| qwen3vl8b | TEMPORAL | location_trace | 52 | no | 0.6585 |  |
| qwen3vl8b | TEMPORAL | spatial_aware_reasoning | 56 | no | 0.0568 |  |
| qwen3vl8b | TEMPORAL | object_comparison | 56 | no | 0.1539 |  |
| qwen3vl8b | TEMPORAL | temporal_ordering_recognition | 47 | YES *** | 0.0108 |  |

---

## 9. Three plain answers

**Q1: Does SPARSE or TEMPORAL win, and does it depend on category?**

- **qwen3vl4b:** UNDERPOWERED: no category shows difference exceeding combined CI
- **qwen3vl8b:** UNDERPOWERED: no category shows difference exceeding combined CI

**Q2: Does TEMPORAL's advantage (if any) grow with evidence distance?**

TEMPORAL − SPARSE accuracy by distance bin:
  - [0,30) (n=67): +0.060
  - [30,60) (n=134): +0.007
  - [60,120) (n=124): +0.073
  - [120,300) (n=103): -0.010
  - [300,+) (n=31): -0.032
Trend is not monotone — hypothesis not supported.

**Q3: What does TEMPORAL cost in latency relative to SPARSE, and is any accuracy gain worth it?**

- **qwen3vl4b:** TEMPORAL is 7.2× the latency of SPARSE; accuracy diff = +0.026. accuracy difference is within noise; TEMPORAL cost is not justified.
- **qwen3vl8b:** TEMPORAL is 1.3× the latency of SPARSE; accuracy diff = +0.048. TEMPORAL wins by +0.048 at 1.3× latency cost.

---

## 10. What cannot be inferred

- This is a measurement study, not a causal experiment. Accuracy differences between arms are observed under the GSER protocol.
- The text-only baseline uses 4B only from study_i (diag).
- decode_latency_ms in reused 4B SPARSE trials is not available (marked as reused); the latency reported for those trials covers inference only.
- Frame caching amortises decode cost per video. Reported decode_latency_ms for TEMPORAL is amortised (total video decode ÷ n_questions_for_that_video), not the cost of decoding just one question's frames.
- Category n varies (44–93); smaller categories have wider CIs and fewer cells will exceed the CI threshold regardless of arm performance.
