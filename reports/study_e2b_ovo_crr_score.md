# StudyE2b-ovo-crr-score: does 32B become correct earlier on OVO-Bench CRR once Yes-bias is controlled?

**E-id:** StudyE2b-ovo-crr-score (pre-registered 2026-11-09, before any computation; authorised by the user).

**Status:** COMPLETE 2026-11-09.

**Label:** **OFFLINE ANALYSIS OF EXISTING SCORES.** It uses StudyB1's 32B-I and StudyB2-ovo-rtv's 4B-I / 8B-I rows. No new inference, CPU only, Instruct only (no Thinking rows).

**Script:** `experiments/orchestration/study_e2b_ovo_crr_score.py` (dashcam venv for scikit-learn).

**Results:** `results/orchestration/study_e2b/e2b_results.json`.

## Data, comparability and definitions
- **Data:** CRR, 48 entries × 5 sub-queries at increasing times, the same question (StudyE2 structure).
- **Input, stack and decoding:** identical frames across models (re-verified in StudyE2: 0 mismatches), same stack and template, greedy decoding.
- **RECENT vs HISTORY:** HISTORY carries about 4× the tokens of RECENT (≈ 12.6k vs 3.1k); this applies to every input contrast.
- **Gold and clue:** gold from the annotations (No = type 0 before the clue, Yes = type 1 after); c = the first gold-Yes sub-query.
- **Score:** from the saved first-token top-20 logprobs.
  - Yes mass = the sum of p over tokens whose whitespace-stripped lower-case form is "yes" or "y"; No mass the same for "no" or "n".
  - p = Yes / (Yes + No); log p floored at 1e-12.
- **Statistics:** video bootstrap, 2,000 resamples, seed 0, resampling videos jointly for both models in paired differences. **There are only 10 videos**, so the CIs are coarse.
- **Part 3:**
  - Folds: 2 by video (KFold, seed 0).
  - Threshold: the lowest threshold such that ≤ 10 % of the training-half pre-clue p are ≥ it. The 0 % variant puts it just above every training pre-clue p.
  - Answer: Yes if p ≥ threshold. The settle point is as in StudyE2: the smallest index after which every answer is correct; an entry wrong at the last sub-query never settles.

## Observations (no interpretation in this section)

### Structure

- **Entries:** 48 entries from **10 videos**, 5 sub-queries each, the same question text.
- **Gold pattern:** {'00111': 48} for every entry, so the **clue index c = 2 in all 48 entries** (2 pre-clue, 3 post-clue sub-queries).
- **Gap from sub-query c − 1 to c:** 3 / 8 / 59 s (min / median / max). From c to c + 1: 8 s in every entry.

### Score checks (run before analysis)

| arm / input | n | first token Yes / No / neither | neither Yes nor No in top 20 | missing logprobs | (p > 0.5) agrees with recorded correctness |
|---|---|---|---|---|---|
| 4BI/RECENT | 240 | 17 / 223 / 0 | 0 (0.0 %) | 0 | 99.2 % |
| 4BI/HISTORY | 240 | 22 / 218 / 0 | 0 (0.0 %) | 0 | 99.2 % |
| 8BI/RECENT | 240 | 25 / 215 / 0 | 0 (0.0 %) | 0 | 99.6 % |
| 8BI/HISTORY | 240 | 73 / 167 / 0 | 0 (0.0 %) | 0 | 98.3 % |
| 32BI/RECENT | 240 | 35 / 205 / 0 | 0 (0.0 %) | 0 | 100.0 % |
| 32BI/HISTORY | 240 | 103 / 137 / 0 | 0 (0.0 %) | 0 | 98.3 % |

The first token was never a non-Yes / No token, so there are no examples to show. StudyE2's settle counts reproduce from the recorded answers: 4BI/RECENT 0, 4BI/HISTORY 9, 8BI/RECENT 1, 8BI/HISTORY 16, 32BI/RECENT 1, 32BI/HISTORY 27 (HISTORY 4B 9 / 8B 16 / 32B 27, as required).

### Part 1: AUROC of p, post-clue (gold Yes) vs pre-clue (gold No) [video-bootstrap CI, 10 videos]

| model | input | pooled AUROC | mean within-entry AUROC |
|---|---|---|---|
| 4BI | RECENT | 0.393 [0.342, 0.445] | 0.361 [0.298, 0.438] |
| 8BI | RECENT | 0.464 [0.429, 0.515] | 0.458 [0.402, 0.525] |
| 32BI | RECENT | 0.434 [0.391, 0.492] | 0.431 [0.379, 0.490] |
| 4BI | HISTORY | 0.559 [0.530, 0.614] | 0.576 [0.527, 0.646] |
| 8BI | HISTORY | 0.605 [0.566, 0.666] | 0.576 [0.507, 0.671] |
| 32BI | HISTORY | 0.592 [0.543, 0.674] | 0.615 [0.537, 0.721] |

| pair | input | pooled diff [CI] | within-entry diff [CI] |
|---|---|---|---|
| 32BI-4BI | RECENT | +0.041 [0.008, 0.084] | +0.069 [0.017, 0.110] |
| 32BI-8BI | RECENT | -0.030 [-0.060, 0.001] | -0.028 [-0.069, 0.004] |
| 8BI-4BI | RECENT | +0.071 [0.035, 0.111] | +0.097 [0.072, 0.119] |
| 32BI-4BI | HISTORY | +0.033 [-0.001, 0.082] | +0.038 [-0.019, 0.103] |
| 32BI-8BI | HISTORY | -0.013 [-0.050, 0.039] | +0.038 [-0.010, 0.100] |
| 8BI-4BI | HISTORY | +0.046 [0.014, 0.085] | -0.000 [-0.049, 0.053] |

### Part 2: per-entry rise above the sub-query-0 baseline (rise index − c, in sub-queries; δ = 2 primary)

| δ | model | input | correct rise (k ≥ c) | false rise (k < c) | no rise |
|---|---|---|---|---|---|
| 1 | 4BI | RECENT | 11 | 15 | 22 |
| 1 | 8BI | RECENT | 15 | 18 | 15 |
| 1 | 32BI | RECENT | 17 | 11 | 20 |
| 1 | 4BI | HISTORY | 17 | 13 | 18 |
| 1 | 8BI | HISTORY | 10 | 20 | 18 |
| 1 | 32BI | HISTORY | 10 | 16 | 22 |
| 2 (primary) | 4BI | RECENT | 12 | 10 | 26 |
| 2 (primary) | 8BI | RECENT | 18 | 13 | 17 |
| 2 (primary) | 32BI | RECENT | 16 | 9 | 23 |
| 2 (primary) | 4BI | HISTORY | 13 | 10 | 25 |
| 2 (primary) | 8BI | HISTORY | 13 | 11 | 24 |
| 2 (primary) | 32BI | HISTORY | 11 | 8 | 29 |
| 3 | 4BI | RECENT | 10 | 8 | 30 |
| 3 | 8BI | RECENT | 17 | 9 | 22 |
| 3 | 32BI | RECENT | 14 | 8 | 26 |
| 3 | 4BI | HISTORY | 9 | 5 | 34 |
| 3 | 8BI | HISTORY | 8 | 10 | 30 |
| 3 | 32BI | HISTORY | 11 | 5 | 32 |

| δ | pair | input | both correct rise | mean diff (sub-queries) [CI] | earlier / same / later | only big / only small correct |
|---|---|---|---|---|---|---|
| 1 | 32BI-4BI | RECENT | 9 | 0.00 [0.00, 0.00] | 0 / 9 / 0 | 8 / 2 |
| 1 | 32BI-8BI | RECENT | 12 | 0.00 [0.00, 0.00] | 0 / 12 / 0 | 5 / 3 |
| 1 | 8BI-4BI | RECENT | 9 | 0.00 [0.00, 0.00] | 0 / 9 / 0 | 6 / 2 |
| 1 | 32BI-4BI | HISTORY | 6 | -0.33 [-1.00, 0.00] | 2 / 4 / 0 | 4 / 11 |
| 1 | 32BI-8BI | HISTORY | 5 | 0.00 [-0.45, 0.75] | 1 / 3 / 1 | 5 / 5 |
| 1 | 8BI-4BI | HISTORY | 6 | -0.33 [-1.00, 0.44] | 2 / 3 / 1 | 4 / 11 |
| 2 | 32BI-4BI | RECENT | 9 | -0.22 [-0.67, 0.00] | 1 / 8 / 0 | 7 / 3 |
| 2 | 32BI-8BI | RECENT | 13 | 0.08 [0.00, 0.20] | 0 / 12 / 1 | 3 / 5 |
| 2 | 8BI-4BI | RECENT | 10 | -0.20 [-0.60, 0.00] | 1 / 9 / 0 | 8 / 2 |
| 2 | 32BI-4BI | HISTORY | 7 | -0.14 [-0.43, 0.00] | 1 / 6 / 0 | 4 / 6 |
| 2 | 32BI-8BI | HISTORY | 7 | -0.14 [-0.40, 0.00] | 1 / 6 / 0 | 4 / 6 |
| 2 | 8BI-4BI | HISTORY | 6 | -0.17 [-0.80, 0.43] | 2 / 3 / 1 | 7 / 7 |
| 3 | 32BI-4BI | RECENT | 8 | 0.00 [0.00, 0.00] | 0 / 8 / 0 | 6 / 2 |
| 3 | 32BI-8BI | RECENT | 12 | -0.17 [-0.43, 0.15] | 3 / 8 / 1 | 2 / 5 |
| 3 | 8BI-4BI | RECENT | 10 | 0.20 [0.00, 0.44] | 0 / 8 / 2 | 7 / 0 |
| 3 | 32BI-4BI | HISTORY | 7 | -0.29 [-0.60, 0.00] | 2 / 5 / 0 | 4 / 2 |
| 3 | 32BI-8BI | HISTORY | 5 | -0.20 [-0.43, 0.00] | 1 / 4 / 0 | 6 / 3 |
| 3 | 8BI-4BI | HISTORY | 4 | -0.25 [-1.00, 0.00] | 1 / 3 / 0 | 4 / 5 |

### Part 3: matched Yes-bias (threshold on p fit on half the videos; held-out pre-clue false-Yes rate), StudyE2 settle point on thresholded answers

| target | model | input | thresholds (fold 0 / 1) | held-out pre-clue false-Yes | entries that settle (of 48) |
|---|---|---|---|---|---|
| 10 % | 4BI | RECENT | 0.076 / 0.562 | 18.8 % | 1 |
| 10 % | 8BI | RECENT | 0.060 / 0.924 | 15.6 % | 2 |
| 10 % | 32BI | RECENT | 0.881 / 0.989 | 7.3 % | 0 |
| 10 % | 4BI | HISTORY | 0.378 / 0.378 | 8.3 % | 10 |
| 10 % | 8BI | HISTORY | 0.731 / 0.818 | 12.5 % | 13 |
| 10 % | 32BI | HISTORY | 0.905 / 0.947 | 8.3 % | 11 |
| 0 % (secondary) | 4BI | RECENT | 0.881 / 0.977 | 2.1 % | 0 |
| 0 % (secondary) | 8BI | RECENT | 0.852 / 0.998 | 6.2 % | 0 |
| 0 % (secondary) | 32BI | RECENT | 0.991 / 0.999 | 4.2 % | 0 |
| 0 % (secondary) | 4BI | HISTORY | 0.622 / 0.924 | 2.1 % | 5 |
| 0 % (secondary) | 8BI | HISTORY | 0.963 / 0.991 | 2.1 % | 6 |
| 0 % (secondary) | 32BI | HISTORY | 0.991 / 0.995 | 1.0 % | 2 |

| target | pair | input | both settle | only big / only small | settle diff, s [CI] | settle diff, sub-queries [CI] | earlier / same / later |
|---|---|---|---|---|---|---|---|
| 10 % | 32BI-4BI | RECENT | 0 | 0 / 1 | — — | — — | 0 / 0 / 0 |
| 10 % | 32BI-8BI | RECENT | 0 | 0 / 2 | — — | — — | 0 / 0 / 0 |
| 10 % | 8BI-4BI | RECENT | 1 | 1 / 0 | 0.0 [0.0, 0.0] | 0.00 [0.00, 0.00] | 0 / 1 / 0 |
| 10 % | 32BI-4BI | HISTORY | 8 | 3 / 2 | 0.1 [-10.0, 10.3] | 0.00 [-1.00, 1.00] | 1 / 6 / 1 |
| 10 % | 32BI-8BI | HISTORY | 8 | 3 / 5 | 2.2 [-8.6, 16.0] | 0.00 [-0.90, 1.00] | 1 / 5 / 2 |
| 10 % | 8BI-4BI | HISTORY | 9 | 4 / 1 | -9.8 [-30.3, 7.8] | -0.44 [-1.80, 0.77] | 3 / 5 / 1 |
| 0 % | 32BI-4BI | RECENT | 0 | 0 / 0 | — — | — — | 0 / 0 / 0 |
| 0 % | 32BI-8BI | RECENT | 0 | 0 / 0 | — — | — — | 0 / 0 / 0 |
| 0 % | 8BI-4BI | RECENT | 0 | 0 / 0 | — — | — — | 0 / 0 / 0 |
| 0 % | 32BI-4BI | HISTORY | 1 | 1 / 4 | 0.0 [0.0, 0.0] | 0.00 [0.00, 0.00] | 0 / 1 / 0 |
| 0 % | 32BI-8BI | HISTORY | 2 | 0 / 4 | 0.0 [0.0, 0.0] | 0.00 [0.00, 0.00] | 0 / 2 / 0 |
| 0 % | 8BI-4BI | HISTORY | 3 | 3 / 2 | 0.0 [0.0, 0.0] | 0.00 [0.00, 0.00] | 0 / 3 / 0 |

### Key observations
- **Structure:** every entry has gold No, No, Yes, Yes, Yes (c = 2), so there are exactly 2 pre-clue sub-queries per entry.
- **Ranking (Part 1):**
  - **RECENT:** every model ranks post-clue sub-queries *below* pre-clue ones (pooled AUROC 0.39–0.46, CIs below 0.5 for 4B and 32B). With only the last 3 s, the models are less inclined to say Yes after the clue than before it.
  - **HISTORY:** AUROC is 0.56–0.61. 32B − 4B is +0.033 [−0.001, +0.082] pooled and +0.038 [−0.019, +0.103] within-entry; neither CI excludes 0.
- **Rise (Part 2, δ = 2):** correct rises in 11–18 entries per model × input and false rises in 8–13. When both models have a correct rise, they rise at the same sub-query in 3–12 of 6–13 entries. Paired means are −0.22 to +0.08 sub-queries, with every CI touching or including 0. δ = 1 and 3 agree.
- **Matched Yes-bias (Part 3, 10 %):**
  - **Achieved held-out pre-clue false-Yes:** HISTORY 8.3 % (4B), 12.5 % (8B), 8.3 % (32B). RECENT 18.8 %, 15.6 %, 7.3 %: two thresholds per arm on 5 videos each are unstable.
  - **HISTORY settles:** 4B 10, 8B 13, 32B 11 of 48 (recorded answers in StudyE2: 9 / 16 / 27).
  - **Paired 32B − 4B, HISTORY:** 8 both settle; only-32B 3, only-4B 2. The settle difference is +0.1 s [−10.0, +10.3] and 0.00 sub-queries [−1, +1]; 1 earlier, 6 same, 1 later.
  - **RECENT:** 0–2 entries settle per model, and no pair has an estimable difference.
- **Matched Yes-bias (0 %, secondary):** 0–6 entries settle per model. Paired n is 0–3, all at the same sub-query.

## Results consistency check
1. **Cross-check against committed measurements:**
   - StudyE2's settle counts reproduce exactly from the recorded answers (HISTORY 9 / 16 / 27; RECENT 0 / 1 / 1).
   - p > 0.5 matches the recorded upstream correctness on 98.3–100 % of sub-queries.
   - The first-token Yes counts equal StudyE2 / B2's answer distributions (e.g. 32B-I RECENT: 35 Yes / 205 No, as in StudyB1).
2. **Physical plausibility:** not applicable.
3. **Distribution sanity:** p varies across sub-queries and models, and thresholds differ by fold and model (0.06–0.99). Pooled and within-entry AUROCs vary.
   - **Flag:** with 10 videos, the fold-specific thresholds swing widely, e.g. 4B RECENT 0.076 vs 0.562, giving held-out false-Yes rates of 7–19 % against a 10 % target.
4. **Definition audit:**
   - The score, rise and settle definitions are as pre-registered.
   - **"Pre-clue"** = gold No, which is exactly sub-queries 0–1 in every entry. So the rise baseline is one sub-query (0), and a rise at k = 1 is a false rise.
5. **Claim linkage:** FORMULATION.md §Decisions. This **weakens** StudyE2's apparent "32B becomes correct earlier" on CRR: that apparent lead does not survive matched Yes-bias.
6. **Proxy validity:**
   - The settle point on thresholded answers is a proxy for recognition at a fixed willingness to say Yes. It depends on the threshold, which is estimated from 96 pre-clue sub-queries across 10 videos, so it is noisy; this is reported as a limitation.
   - p's agreement with the recorded answers (≥ 98.3 %) supports using the first-token logprobs as the model's answer score.

**Outcome:** all stop checks passed. Flags: 10 videos (coarse CIs, unstable thresholds), and held-out false-Yes outside 10 % for RECENT 4B / 8B.

## Interpretation
- **The StudyE2 settle lead was driven by Yes-bias.** At a matched 10 % false-Yes rate on pre-clue sub-queries, 32B and 4B settle on about the same number of CRR entries under HISTORY (11 vs 10), at the same sub-query in 6 of the 8 entries where both settle (difference +0.1 s, CI −10 to +10 s). The 32B earliness claim fails the pre-registered rule: the part 3 CI includes 0, and part 1 does not exclude 0 either.
- **Ranking:** with full history, 32B ranks post-clue sub-queries slightly above pre-clue ones more often than 4B (+0.03 AUROC), but within noise on 10 videos.
- **RECENT:** none of the models' Yes-tendency goes up after the clue (AUROC below 0.5), so nothing can settle. The 3-second window, not model size, limits this task. HISTORY also carries about 4× the tokens.

