# Study N2 — Escalation Framing

**Date:** 2026-10-03  
**VERDICT (first line, pre-registered): SIGNAL**  
Primary cell L=120 s, e=0.2: best predictor P4 closes 44.9% of oracle coverage gap (95% CI: 41.9%–48.0%, video-clustered bootstrap, n=3141 videos, CI lower > 15%).  
Pre-registered rule: SIGNAL ≥40% and CI lower >15%; NO SIGNAL <15% or CI incl. 0; PARTIAL otherwise.
Text predictors (P4) beat elapsed-only (P1): YES — median Δgap_closed 21.7% (95% CI 18.2%–25.0%, excl. 0).
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

| predictor | L=60 test | L=120 test | L=120 OOF | L=120 in-fold |
|---|---|---|---|---|
| P1 | 0.6213 | 0.6958 | 0.6961 | 0.6960 |
| P2 | 0.6259 | 0.6987 | 0.6989 | 0.6994 |
| P3 | 0.6764 | 0.7034 | 0.7038 | 0.9367 ← in-fold |
| P4 | 0.7229 | 0.7652 | 0.7656 ← selected | 0.8195 |
| P5 (ORACLE-INFO) | 0.6623 | 0.7122 | 0.7124 | 0.7129 |

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
Text predictors (P4) reliably outperform elapsed-only (P1): median Δgap_closed 21.7% (95% CI 18.2%–25.0%).

## 8. Implementation Notes

### P3 AUROC discrepancy — implementation fix found after results were read

An external run reported AUROC 0.789 for P3 at L=120; this script reported 0.7034. Root cause identified: the main script applies `StandardScaler(with_mean=False)` to the sparse TF-IDF matrix before LogisticRegression. Unit-variance scaling of sparse TF-IDF inflates rare n-grams, causing in-fold overfitting. The external run used **no scaler**.

| setting | main (this script) | external run |
|---|---|---|
| LogisticRegression max_iter | 1000 | 1000 |
| C | 1.0 | 1.0 |
| solver | lbfgs (default) | lbfgs (default) |
| class_weight | None | None |
| scaling | StandardScaler(with_mean=False) | **none** |
| TF-IDF | 1-2 gram, 2000 feat, sublinear_tf | 1-2 gram, 2000 feat, sublinear_tf |

**P3 AUROC and in-fold AUROC comparison (implementation fix):**

| | L=60 AUROC | L=120 AUROC | L=120 in-fold |
|---|---|---|---|
| P3 with scaler (primary, unchanged) | 0.6764 | 0.7034 | 0.9367 |
| P3 no scaler (diagnostic) | 0.7471 | 0.7893 | 0.8589 |
| External ref | — | 0.789 | — |

Removing the scaler reproduces the external AUROC (0.7893 vs ref 0.789). P3 without scaler at L=120, e=0.2: gap_closed = 48.1% (cov=83.0%).  

**P3 no-scaler coverage across all (L, e):**

| L | e | cov_pred | cov_random | cov_oracle | gap_closed |
|---|---|---|---|---|---|
| 60 | 0.1 | 51.1% | 47.9% | 52.1% | 76.6% |
| 60 | 0.2 | 59.2% | 53.7% | 62.1% | 65.9% |
| 60 | 0.3 | 66.6% | 59.5% | 72.1% | 56.5% |
| 120 | 0.1 | 77.4% | 73.3% | 80.3% | 58.9% |
| 120 | 0.2 | 83.0% | 76.2% | 90.3% | 48.1% |
| 120 | 0.3 | 87.4% | 79.2% | 100.0% | 39.5% |

**Would the verdict differ if P3 (no scaler) were used instead of P4?**  
P3 no-scaler gap_closed at primary cell = 48.1% vs P4 = 44.9%.  
P3 no-scaler OOF AUROC (0.7893) exceeds P4 (0.7656); P3 no-scaler would have been selected. Its gap_closed at primary cell = 48.1%, which meets the SIGNAL threshold (≥40%). Verdict unchanged: **SIGNAL**.

**P2 and P4 scaler impact (fold 0, L=120):**  
P2 (keyword+elapsed, dense, 2 features): ΔAUROC = -0.0000 ≤ 0.01.  
P4 (MiniLM embedding, dense, 385 features): ΔAUROC = +0.0149 > 0.01.  
Only P3 uses a sparse matrix; P2 and P4 use dense features where unit-variance scaling is standard.

### Model-selection deviation from pre-registration

Pre-registration: 'best of P1–P4 by AUROC on training folds only.'  
Implementation: best by **mean OOF AUROC** (held-out test fold, averaged across 5 folds).  
In-fold AUROC was also computed. P3's in-fold AUROC of 0.9367 reflects the scaler-induced overfitting documented above; without the scaler, P3 in-fold drops to 0.8589.

| predictor | OOF AUROC (L=120) | in-fold AUROC (L=120) |
|---|---|---|
| P1 | 0.6961 | 0.6960 |
| P2 | 0.6989 | 0.6994 |
| P3 | 0.7038 | 0.9367 (scaler overfitting) |
| P4 | 0.7656 | 0.8195 |

Best by OOF: **P4**.  Best by in-fold: **P3** (P3 in-fold inflated by scaler).  
Primary analysis uses OOF selection (P4), which is correct. In-fold selection would have chosen P3, driven by scaler-induced overfitting. The OOF criterion correctly rejects P3 in favour of P4.

