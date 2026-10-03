# Study N2 — Escalation Framing

**Date:** 2026-10-03  
**VERDICT (first line, pre-registered): SIGNAL**  
Primary cell L=120 s, e=0.2: best predictor P4 closes 44.9% of oracle coverage gap (95% CI: 41.9%–48.0%, CI lower > 15%).  
Pre-registered rule: SIGNAL ≥40% and CI lower >15%; NO SIGNAL <15% or CI incl. 0; PARTIAL otherwise.
Text predictors (P4) beat elapsed-only (P1): YES — median Δgap_closed 21.7% (95% CI 18.5%–24.7%, excl. 0).
**Disclosure:** exploratory analysis at L=120, e=0.2 found gap_closed ≈47% (AUROC 0.79). This is a confirmatory re-implementation, not independent evidence.

---

## 1. Data

Source: `results/sember/study_h/data/sember_grounding.jsonl`, n=9,448.  
Excluded: 10 negative-nearest.  Used: 9438 records.  
Grouped 5-fold CV by video_id, seed=42. No video leakage confirmed.

P(needs_escalation): L=60 → 0.579, L=120 → 0.297  
(Expected ≈0.579 / 0.297)

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

## 2. AUROC per Predictor

### With counting

| predictor | L=60 test | L=60 mean_oof | L=120 test | L=120 mean_oof |
|---|---|---|---|---|
| P1 | 0.6213 | 0.6218 | 0.6958 | 0.6961 |
| P2 | 0.6259 | 0.6262 | 0.6987 | 0.6989 |
| P3 | 0.6764 | 0.6766 | 0.7034 | 0.7038 |
| P4 | 0.7229 | 0.7227 | 0.7652 | 0.7656 |
| P5 (ORACLE-INFO) | 0.6623 | 0.6621 | 0.7122 | 0.7124 |

### Without counting

| predictor | L=60 test | L=120 test |
|---|---|---|
| P1 | 0.6178 | 0.6968 |
| P2 | 0.6368 | 0.7119 |
| P3 | 0.6419 | 0.6563 |
| P4 | 0.6028 | 0.6633 |
| P5 (ORACLE-INFO) | 0.6235 | 0.6962 |

## 3. Coverage and Gap Closed (with counting)

Gap closed = (cov_pred − cov_random) / (cov_oracle − cov_random).  
Random baseline: analytic (1−p)+e×p where p=P(farthest>L). Oracle: escalate true positives first.

### L=60 s, e=0.1

p(needs escalation)=0.579 | random coverage=47.9% | oracle coverage=52.1%

| predictor | cov_pred | gap closed |
|---|---|---|
| P1 | 48.8% | 21.3% |
| P2 | 49.0% | 25.6% |
| P3 | 49.7% | 42.4% |
| P4 | 50.9% | 70.3% |
| P5 (ORACLE-INFO) | 49.9% | 46.7% |

### L=60 s, e=0.2

p(needs escalation)=0.579 | random coverage=53.7% | oracle coverage=62.1%

| predictor | cov_pred | gap closed |
|---|---|---|
| P1 | 55.6% | 22.3% |
| P2 | 55.7% | 23.3% |
| P3 | 57.3% | 42.3% |
| P4 | 58.9% | 61.7% |
| P5 (ORACLE-INFO) | 57.0% | 39.4% |

### L=60 s, e=0.3

p(needs escalation)=0.579 | random coverage=59.5% | oracle coverage=72.1%

| predictor | cov_pred | gap closed |
|---|---|---|
| P1 | 62.1% | 20.4% |
| P2 | 62.1% | 21.0% |
| P3 | 64.4% | 39.2% |
| P4 | 66.2% | 53.6% |
| P5 (ORACLE-INFO) | 63.3% | 30.4% |

### L=120 s, e=0.1

p(needs escalation)=0.297 | random coverage=73.3% | oracle coverage=80.3%

| predictor | cov_pred | gap closed |
|---|---|---|
| P1 | 74.9% | 23.6% |
| P2 | 75.1% | 26.8% |
| P3 | 75.9% | 37.8% |
| P4 | 77.2% | 56.5% |
| P5 (ORACLE-INFO) | 75.6% | 33.2% |

### L=120 s, e=0.2

p(needs escalation)=0.297 | random coverage=76.2% | oracle coverage=90.3%

| predictor | cov_pred | gap closed |
|---|---|---|
| P1 | 79.5% | 23.0% |
| P2 | 79.6% | 24.0% |
| P3 | 81.0% | 34.2% |
| P4 | 82.5% | 44.9% |
| P5 (ORACLE-INFO) | 80.2% | 28.2% |

**Primary cell (L=120, e=0.2): P4 = 44.9% (95% CI: 41.9%–48.0%)**

### L=120 s, e=0.3

p(needs escalation)=0.297 | random coverage=79.2% | oracle coverage=100.0%

| predictor | cov_pred | gap closed |
|---|---|---|
| P1 | 83.4% | 20.3% |
| P2 | 83.7% | 21.5% |
| P3 | 85.1% | 28.5% |
| P4 | 86.6% | 35.6% |
| P5 (ORACLE-INFO) | 83.9% | 22.7% |

## 4. Per-Category Lookup Check (L=120, e=0.2, with counting)

| category | n | random | oracle | P4 gap_closed | P5 (ORACLE-INFO) gap_closed |
|---|---|---|---|---|---|
| counting_objects_events | 1623 | 59.8% | 69.8% | 56.1% | 35.7% |
| location_trace | 995 | 82.2% | 97.7% | 19.1% | 12.0% |
| object_comparison | 665 | 75.2% | 89.0% | 53.2% | 39.0% |
| sequential_action | 1018 | 88.5% | 100.0% | 15.2% | 5.0% |
| spatial_aware_reasoning | 851 | 69.7% | 82.1% | 34.7% | 15.7% |
| temporal_ordering_recognition | 483 | 65.9% | 77.4% | 48.0% | 39.1% |
| time_duration | 1935 | 76.2% | 90.3% | 37.5% | 29.0% |
| visual_detail_recall | 1868 | 86.7% | 100.0% | 21.2% | 19.6% |

## 5. Calibration — P4 at L=120

| bin | n | mean_pred | frac_pos |
|---|---|---|---|
| [0.0,0.1) | 2538 | 0.048 | 0.079 |
| [0.1,0.2) | 1732 | 0.148 | 0.200 |
| [0.2,0.3) | 1258 | 0.246 | 0.271 |
| [0.3,0.4) | 1011 | 0.349 | 0.346 |
| [0.4,0.5) | 837 | 0.449 | 0.405 |
| [0.5,0.6) | 684 | 0.550 | 0.482 |
| [0.6,0.7) | 551 | 0.647 | 0.570 |
| [0.7,0.8) | 444 | 0.748 | 0.642 |
| [0.8,0.9) | 297 | 0.845 | 0.764 |
| [0.9,1.0) | 86 | 0.931 | 0.837 |

## 6. 20 Random Examples

| question (trunc) | category | qt | farthest | esc_120 | P1 | P2 | P3 | P4 | P5 |
|---|---|---|---|---|---|---|---|---|---|
| How many mannequins did I pass before touching thi | counting_objects_eve | 302s | 159s | True | 0.377 | 0.412 | 0.668 | 0.496 | 0.473 |
| When I walked over to the white bag earlier, what  | visual_detail_recall | 433s | 218s | True | 0.483 | 0.52 | 0.174 | 0.387 | 0.366 |
| How many articles of clothing did I fold? | counting_objects_eve | 318s | 315s | True | 0.393 | 0.375 | 0.881 | 0.657 | 0.489 |
| What product was immediately to the left of the Or | visual_detail_recall | 184s | 72s | False | 0.244 | 0.224 | 0.014 | 0.048 | 0.171 |
| How long was I holding the ‘Blessed Beyond Measure | time_duration | 298s | 25s | False | 0.375 | 0.401 | 0.469 | 0.179 | 0.441 |
| How does this painting compare to the last paintin | object_comparison | 76s | 28s | False | 0.095 | 0.084 | 0.004 | 0.04 | 0.081 |
| How many flyers have I looked at since the Candy L | counting_objects_eve | 130s | 124s | True | 0.172 | 0.156 | 0.302 | 0.058 | 0.235 |
| How many times have I seen the white charger that  | counting_objects_eve | 316s | 230s | True | 0.392 | 0.378 | 0.495 | 0.751 | 0.497 |
| What was the name of the board game I picked up be | visual_detail_recall | 22s | 18s | False | 0.023 | 0.025 | 0.0 | 0.005 | 0.014 |
| How long was it from when I took the blue colored  | time_duration | 200s | 74s | False | 0.268 | 0.25 | 0.022 | 0.144 | 0.319 |
| How did the answer I circled in question 10 compar | object_comparison | 182s | 72s | False | 0.242 | 0.227 | 0.0 | 0.056 | 0.212 |
| How long did I spend looking at the purple Hello K | time_duration | 300s | 64s | False | 0.372 | 0.355 | 0.623 | 0.291 | 0.438 |
| From where I am now, how do I get to the section w | spatial_aware_reason | 79s | 47s | False | 0.102 | 0.112 | 0.002 | 0.059 | 0.099 |
| How long did I hold the purple kneeling pad for be | time_duration | 320s | 38s | False | 0.391 | 0.425 | 0.969 | 0.225 | 0.457 |
| What color was the piece that popped off and fell? | visual_detail_recall | 104s | 86s | False | 0.138 | 0.13 | 0.568 | 0.029 | 0.089 |
| How long did I hold the book Enola HOLMES? | time_duration | 213s | 91s | False | 0.282 | 0.269 | 0.131 | 0.115 | 0.341 |
| What devices are on the table directly behind me? | spatial_aware_reason | 164s | 164s | True | 0.219 | 0.204 | 0.0 | 0.196 | 0.213 |
| How many times have I checked the time on my phone | counting_objects_eve | 243s | 113s | False | 0.315 | 0.298 | 0.474 | 0.597 | 0.405 |
| As I started crossing the crosswalk, what was the  | visual_detail_recall | 53s | 43s | False | 0.066 | 0.073 | 0.064 | 0.012 | 0.041 |
| What time is the Southeast Harlem Line train depar | visual_detail_recall | 174s | 17s | False | 0.231 | 0.212 | 0.001 | 0.148 | 0.161 |

## 7. Verdict and Interpretation

**SIGNAL**

Primary cell L=120, e=0.2: P4 closes 44.9% of oracle gap (cov_pred=82.5%, random=76.2%, oracle=90.3%).  
95% CI: 41.9%–48.0%.

Evidence-horizon-based escalation works under the pre-registered rule. Predictive signal (AUROC=0.765) translates to coverage gain over random escalation.
Text predictors (P4) reliably outperform elapsed-only (P1): median Δgap_closed 21.7% (95% CI 18.5%–24.7%).

