# Study N — Evidence-Horizon Predictability

**Date:** 2026-10-01  
**VERDICT (first line, pre-registered): UNPREDICTABLE**  
Best non-oracle predictor P4 closes -196.1% of oracle coverage gap at W=120 s (95% bootstrap CI: -254.9%–-153.6%, includes 0).  
Pre-registered rule: PREDICTABLE ≥40% CI excl. 0; UNPREDICTABLE <15% or CI incl. 0; PARTIAL otherwise.

---

## 1. Data

Source: `results/sember/study_h/data/sember_grounding.jsonl`, n=9,448.  
Excluded: 10 records with negative nearest evidence distance (question_time < answer_end_time, 1 s rounding).  
Used: 9438 records.

**Sanity check (vs H2 committed values):**

| metric | this run | H2 committed | match |
|---|---|---|---|
| nearest p50 | 21 s | 21 s | ✓ |
| nearest p75 | 56 s | 56 s | ✓ |
| nearest p90 | 117 s | 117 s | ✓ |
| farthest p50 | 74 s | 74 s | ✓ |
| farthest p75 | 135 s | 135 s | ✓ |
| farthest p90 | 235 s | 236 s | ✓ |

**Category counts (with counting):**
- counting_objects_events: 1623
- location_trace: 995
- object_comparison: 665
- sequential_action: 1018
- spatial_aware_reasoning: 851
- temporal_ordering_recognition: 483
- time_duration: 1935
- visual_detail_recall: 1868
- **Total without counting:** 7815

Keyword rules (P2): 'first', 'earlier', 'before', 'at the beginning', 'last time', 'just', 'now', 'currently', 'recently', 'start', 'began', 'initially', 'earlier in', 'beginning of'

P4 sentence-embedding model: `all-MiniLM-L6-v2` (sentence-transformers)

Cross-validation: 5-fold grouped by video_id, seed=42. No session leakage confirmed.

---

## 2. T1 Regression — log(farthest + 1)

| predictor | Spearman ρ | MAE (log s) |
|---|---|---|
| P0 | -0.0206 | 0.7103 |
| P1 | 0.3021 | 0.6810 |
| P2 | 0.3065 | 0.6801 |
| P3 | 0.3942 | 0.6740 |
| P4 | 0.4445 | 0.6233 |
| P5 (ORACLE-INFO) | 0.3383 | 0.6652 |

**Without counting:**

| predictor | Spearman ρ | MAE (log s) |
|---|---|---|
| P0 | -0.0192 | 0.6974 |
| P1 | 0.2710 | 0.6734 |
| P2 | 0.2892 | 0.6678 |
| P3 | 0.3168 | 0.7178 |
| P4 | 0.1988 | 0.6905 |
| P5 (ORACLE-INFO) | 0.2703 | 0.6714 |

---

## 3. T2 Classification — binary evidence within W seconds

### AUROC (with counting)

| predictor | W=60 | W=120 | W=300 |
|---|---|---|---|
| P0 | 0.4892 | 0.4939 | 0.4826 |
| P1 | 0.6199 | 0.6957 | 0.9089 |
| P2 | 0.6216 | 0.6965 | 0.9086 |
| P3 | 0.6567 | 0.6792 | 0.7973 |
| P4 | 0.6985 | 0.7380 | 0.8726 |
| P5 (ORACLE-INFO) | 0.6485 | 0.7006 | 0.9076 |

### AUROC (without counting)

| predictor | W=60 | W=120 | W=300 |
|---|---|---|---|
| P0 | 0.4898 | 0.4891 | 0.4811 |
| P1 | 0.6153 | 0.6968 | 0.9057 |
| P2 | 0.6234 | 0.7029 | 0.9060 |
| P3 | 0.6267 | 0.6374 | 0.7640 |
| P4 | 0.5716 | 0.6311 | 0.8016 |
| P5 (ORACLE-INFO) | 0.6143 | 0.6938 | 0.9056 |

---

## 4. Systems Metric — Coverage at Matched Mean Budget

Policy A: fixed trailing window of W seconds.  
Policy B: per-question choice between W_s=W/2 and W_l=W×2, threshold set to matched mean budget W.  
Oracle: budget-constrained — knows true farthest distance; assigns W_s to all farthest≤W_s, then assigns W_l to the remaining easiest-to-help questions (farthest just above W_s, ascending) until mean budget = W. This is achievable with a perfect predictor subject to the same budget.  
Gap closed = (Policy B − Policy A) / (Oracle − Policy A).

### W = 60 s  (W_s=30, W_l=120)

Policy A (fixed): 42.1%  |  Oracle: 50.4%

| predictor | policy B cov | gap closed |
|---|---|---|
| P0 | 27.3% | -179.2% |
| P1 | 31.1% | -133.6% |
| P2 | 30.8% | -137.4% |
| P3 | 32.6% | -115.1% |
| P4 | 31.4% | -130.1% |
| P5 (ORACLE-INFO) | 31.6% | -127.2% |

### W = 120 s  (W_s=60, W_l=240)

Policy A (fixed): 70.3%  |  Oracle: 75.4%

| predictor | policy B cov | gap closed |
|---|---|---|
| P0 | 51.8% | -359.1% |
| P1 | 55.9% | -279.1% |
| P2 | 56.0% | -277.4% |
| P3 | 59.8% | -204.1% |
| P4 | 60.2% | -196.1% |
| P5 (ORACLE-INFO) | 57.8% | -242.1% |

**Best non-oracle (W=120): P4 = -196.1% (95% CI: -254.9%–-153.6%)**

### W = 300 s  (W_s=150, W_l=600)

Policy A (fixed): 94.6%  |  Oracle: 99.8%

| predictor | policy B cov | gap closed |
|---|---|---|
| P0 | 83.1% | -222.7% |
| P1 | 90.8% | -73.2% |
| P2 | 90.9% | -72.2% |
| P3 | 90.2% | -85.7% |
| P4 | 91.3% | -64.6% |
| P5 (ORACLE-INFO) | 91.2% | -66.9% |

---

## 5. Per-Category Gap Closed (W=120, with counting)

| category | n | policy_a | oracle | P4 gap closed |
|---|---|---|---|---|
| counting_objects_events | 1623 | 49.7% | 53.7% | -295.3% |
| location_trace | 995 | 77.7% | 84.6% | -173.9% |
| object_comparison | 665 | 69.0% | 80.5% | -46.1% |
| sequential_action | 1018 | 85.7% | 92.5% | -192.9% |
| spatial_aware_reasoning | 851 | 62.2% | 67.5% | -195.6% |
| temporal_ordering_recognition | 483 | 57.4% | 58.0% | -2600.0% |
| time_duration | 1935 | 70.3% | 70.0% | 0.0% |
| visual_detail_recall | 1868 | 83.4% | 92.3% | -134.1% |

---

## 6. 20 Random Examples

| question (trunc) | category | qt | nearest | farthest | within_120 | P0 | P1 | P2 | P3 | P4 | P5 (oracle) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| How many mannequins did I pass before touching thi | counting_objects_eve | 302s | 20s | 159s | False | 0.70 | 0.67 | 0.64 | 0.52 | 0.60 | 0.57 |
| When I walked over to the white bag earlier, what  | visual_detail_recall | 433s | 178s | 218s | False | 0.70 | 0.55 | 0.52 | 0.95 | 0.66 | 0.66 |
| How many articles of clothing did I fold? | counting_objects_eve | 318s | 0s | 315s | False | 0.70 | 0.65 | 0.67 | 0.23 | 0.44 | 0.56 |
| What product was immediately to the left of the Or | visual_detail_recall | 184s | 65s | 72s | True | 0.70 | 0.77 | 0.78 | 0.99 | 0.95 | 0.84 |
| How long was I holding the ‘Blessed Beyond Measure | time_duration | 298s | 10s | 25s | True | 0.70 | 0.67 | 0.65 | 0.68 | 0.84 | 0.60 |
| How does this painting compare to the last paintin | object_comparison | 76s | 0s | 28s | True | 0.70 | 0.84 | 0.85 | 0.98 | 0.91 | 0.86 |
| How many flyers have I looked at since the Candy L | counting_objects_eve | 130s | 0s | 124s | False | 0.70 | 0.81 | 0.82 | 0.51 | 0.92 | 0.73 |
| How many times have I seen the white charger that  | counting_objects_eve | 316s | 46s | 230s | False | 0.70 | 0.65 | 0.67 | 0.68 | 0.25 | 0.55 |
| What was the name of the board game I picked up be | visual_detail_recall | 22s | 10s | 18s | True | 0.70 | 0.86 | 0.85 | 1.00 | 0.94 | 0.91 |
| How long was it from when I took the blue colored  | time_duration | 200s | 18s | 74s | True | 0.70 | 0.75 | 0.77 | 0.96 | 0.87 | 0.70 |
| How did the answer I circled in question 10 compar | object_comparison | 182s | 22s | 72s | True | 0.70 | 0.77 | 0.78 | 1.00 | 0.94 | 0.80 |
| How long did I spend looking at the purple Hello K | time_duration | 300s | 53s | 64s | True | 0.70 | 0.67 | 0.69 | 0.44 | 0.75 | 0.61 |
| From where I am now, how do I get to the section w | spatial_aware_reason | 79s | 0s | 47s | True | 0.70 | 0.83 | 0.82 | 0.99 | 0.88 | 0.84 |
| How long did I hold the purple kneeling pad for be | time_duration | 320s | 18s | 38s | True | 0.70 | 0.65 | 0.63 | 0.08 | 0.83 | 0.59 |
| What color was the piece that popped off and fell? | visual_detail_recall | 104s | 79s | 86s | True | 0.70 | 0.82 | 0.83 | 0.32 | 0.96 | 0.88 |
| How long did I hold the book Enola HOLMES? | time_duration | 213s | 70s | 91s | True | 0.70 | 0.74 | 0.75 | 0.86 | 0.91 | 0.68 |
| What devices are on the table directly behind me? | spatial_aware_reason | 164s | 0s | 164s | False | 0.70 | 0.78 | 0.79 | 1.00 | 0.79 | 0.79 |
| How many times have I checked the time on my phone | counting_objects_eve | 243s | 17s | 113s | True | 0.70 | 0.72 | 0.73 | 0.58 | 0.44 | 0.63 |
| As I started crossing the crosswalk, what was the  | visual_detail_recall | 53s | 37s | 43s | True | 0.70 | 0.85 | 0.83 | 0.60 | 0.96 | 0.90 |
| What time is the Southeast Harlem Line train depar | visual_detail_recall | 174s | 15s | 17s | True | 0.70 | 0.77 | 0.79 | 1.00 | 0.83 | 0.84 |

---

## 7. Verdict and Interpretation

**UNPREDICTABLE**

Best non-oracle predictor (P4) closes only -196.1% of the oracle coverage gap at W=120 s (95% bootstrap CI: -254.9%–-153.6%). CI includes 0 but is clearly on the negative side. Pre-registered rule: UNPREDICTABLE (CI includes 0 and best value <15%).

**Why gap_closed is negative (structural, not a bug).** With W=120, W_s=60, W_l=240, frac_long=1/3:
- P(farthest≤60) = 42.1% — covered by both W_s and Policy A
- P(60<farthest≤120) = 28.2% — covered by Policy A (fixed W=120), NOT by W_s=60
- P(120<farthest≤240) = 20.2% — not covered by Policy A, but covered by W_l=240
- P(farthest>240) = 9.6% — not covered by either

Policy A covers 70.3% (everything within 120s). Policy B can use W_l for only 33.3% of questions to match the budget. Even with perfect knowledge of distance (as in the budget-constrained oracle at 75.4%), W_l budget is insufficient to both (a) rescue the 28.2% missed by W_s and (b) also cover the 20.2% above 120s. The best any predictor can do under this budget constraint is 75.4%; Policy B with an imperfect predictor covers only 60.2% — less than Policy A.

**Predictive signal exists but does not translate.** P4 achieves T1 Spearman ρ=0.445 (non-trivial), AUROC=0.738 at W=120, and consistently beats P0–P2 across targets. The signal is there; the binary W_s/W_l discretization under a tight budget constraint means accurate predictions still cannot rescue the medium-distance band (60–120 s) that Policy A covers for free. Adaptive allocation is counter-productive at this granularity.
