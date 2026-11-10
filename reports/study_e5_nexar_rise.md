# StudyE5-nexar-rise: which model's score rises first, relative to its own earlier level, before a crash?

**E-id:** StudyE5-nexar-rise (pre-registered 2026-11-09, before any computation; authorised by the user).

**Status:** COMPLETE 2026-11-09. Parts F (TTA at a fixed FPR) and G (AP at fixed horizons) were added after E5's per-clip results were seen; they are at the end.

**Label:** **OFFLINE ANALYSIS OF EXISTING SCORES** (StudyD14-trace validation traces). No new inference, CPU only, and no test or development clip was read.

**Question:** for each real crash, which model's score first rises clearly above its own earlier level in the same clip, and by how much earlier? This asks when each model notices a change, not when it answers Yes.

**Script:** `experiments/orchestration/study_e5_nexar_rise.py` (dashcam venv).

**Results:** `results/orchestration/study_e5/e5_results.json`.

## Data, comparability and definitions (fixed before computing)
- **Data:** D14 validation traces: 150 positive and 150 negative clips, one decision per second at t = 3, 4, … s; s = log P(Yes) as stored (floor 1e-12); event times from `d14_sample.json`.
- **Input, stack and decoding:** for matched N, the two models had identical frames and prompt tokens (D14 checks), the same stack and greedy decoding. The pairs 32B N = 9 vs 4B N = 3 and 32B N = 1 vs 4B N = 3 differ in frame count, as stated in each table.
- **Reference time r:**
  - Positives: time_of_event.
  - Negatives: StudyD2's rule (`d2_prepare.py`): negatives in file-name order, `random.Random(0).choice` over the sorted positive time_of_event values of the same duration bin (18–20 s, 38–42 s, other), clipped to [3, D − 2] when D ≥ 5. The pool is the 150 validation positives, since only validation clips may be read.
- **Baseline:** 3 ≤ t ≤ r − 5, at least 5 seconds required; m = median; d = max(1.4826 × MAD, 0.5).
- **Search window:** r − 5 ≤ t ≤ r + 3.
- **Rise rules:**
  - Primary: first t with s ≥ m + 3d.
  - Secondary: k = 2; and k = 3 with 2 consecutive seconds (the rise time is the first of the two).
  - All times are relative to r.
- **Matched false-rise rates (secondary):**
  - Per model, k is the smallest value in 0.50 … 15.00 (step 0.05) whose false-rise rate on one half of the negatives is ≤ 10 %. The halves are 2 folds by clip, seed 0.
  - Each k is evaluated on the other half, then the folds are swapped and pooled.
  - Each positive uses the k fitted on the negative fold opposite its own positive fold.
- **Statistics:** clip bootstrap, 2,000 resamples, seed 0. Differences are big − small (negative = 32B earlier).

## Sanity checks (run first)
| check | result |
|---|---|
| D14 event-time AUROCs (0.738 / 0.773 / 0.778 / 0.841 / 0.825) within 0.002 | **PASS, exact** (|diff| = 0.000 for all 5 arms) |
| no grey rows in the input | PASS (0) |
| every positive has time_of_event | PASS (150 / 150) |
| positives with r − 5 < 8 s (short baseline) | 11: 00026, 00083, 00235, 00275, 00283, 00362, 00417, 00573, 00629, 00883, 00915 (r = 9.2–10.7 s, the short 18–20 s clips; exactly the 11 excluded positives, below) |
| clips without a valid baseline (stop if > 20 % in any arm) | 11 positives + 22 negatives = **11 %** in every arm → PASS |
| floor 0.5 sets the threshold | in 1–5 of 267 clips per arm; median raw d 2.0–3.0 log units → the floor rarely binds |
| assigned negative r matches the positive distribution | KS p = 0.83 (18–20 s), 0.996 (38–42 s), 0.85 (other); 1 negative clipped |

## Observations (no interpretation in this section)

### Reference times (negatives assigned by the StudyD2 rule from validation-positive event times)

| duration bin | positives | negatives | positive p5 / p50 / p95 | negative p5 / p50 / p95 | KS p |
|---|---|---|---|---|---|
| 18-20 s | 11 | 22 | 9.5 / 10.2 / 10.7 | 9.2 / 10.1 / 10.6 | 0.83 |
| 38-42 s | 131 | 123 | 18.4 / 19.8 / 21.1 | 18.5 / 19.7 / 21.2 | 1.00 |
| other s | 8 | 5 | 17.7 / 19.4 / 54.3 | 17.9 / 18.8 / 32.5 | 0.85 |

Negatives clipped to [3, D − 2]: 1.

### Baselines

| arm | excluded (< 5 baseline s): pos / neg (fraction) | floor 0.5 applied | raw spread d p5 / p25 / p50 / p75 / p95 (log units) | median baseline seconds |
|---|---|---|---|---|
| 4BI_N1 | 11 / 22 (0.11) | 5 of 267 | 0.74 / 1.48 / 2.04 / 3.15 / 4.64 | 12 |
| 4BI_N3 | 11 / 22 (0.11) | 2 of 267 | 0.99 / 1.67 / 2.41 / 3.14 / 4.82 | 12 |
| 32BI_N1 | 11 / 22 (0.11) | 4 of 267 | 0.74 / 1.71 / 2.69 / 3.98 / 6.17 | 12 |
| 32BI_N3 | 11 / 22 (0.11) | 1 of 267 | 1.11 / 2.04 / 2.97 / 4.39 / 6.76 | 12 |
| 32BI_N9 | 11 / 22 (0.11) | 2 of 267 | 0.83 / 1.76 / 2.41 / 3.43 / 5.50 | 12 |

### 1. Per arm: rise fraction and rise time (s, relative to r; median [p25, p75])


**Rule k3 (primary)**

| arm | positives with a rise | rise − event, median [p25, p75] | rise − alert, median | negatives with a false rise | false rise − r, median |
|---|---|---|---|---|---|
| 4BI_N1 | 43.2 % (n 139) | -1.23 [-3.51, -0.17] | 0.07 | 36.7 % (n 128) | -1.90 |
| 4BI_N3 | 38.1 % (n 139) | -0.60 [-2.90, 0.27] | 0.63 | 33.6 % (n 128) | -1.60 |
| 32BI_N1 | 53.2 % (n 139) | -1.29 [-3.38, -0.48] | 0.18 | 43.8 % (n 128) | -2.24 |
| 32BI_N3 | 57.6 % (n 139) | -1.28 [-3.23, -0.19] | 0.32 | 39.8 % (n 128) | -2.13 |
| 32BI_N9 | 67.6 % (n 139) | -0.76 [-2.39, 0.17] | 0.61 | 36.7 % (n 128) | -3.24 |

**Rule k2 (secondary)**

| arm | positives with a rise | rise − event, median [p25, p75] | rise − alert, median | negatives with a false rise | false rise − r, median |
|---|---|---|---|---|---|
| 4BI_N1 | 63.3 % (n 139) | -1.79 [-3.81, -0.17] | -0.21 | 57.0 % (n 128) | -1.90 |
| 4BI_N3 | 59.7 % (n 139) | -1.60 [-3.53, -0.19] | 0.20 | 47.7 % (n 128) | -2.40 |
| 32BI_N1 | 76.3 % (n 139) | -2.05 [-3.71, -0.64] | -0.60 | 59.4 % (n 128) | -2.21 |
| 32BI_N3 | 74.8 % (n 139) | -1.63 [-3.91, -0.46] | -0.34 | 57.0 % (n 128) | -2.49 |
| 32BI_N9 | 84.9 % (n 139) | -1.39 [-3.32, -0.31] | 0.20 | 52.3 % (n 128) | -3.22 |

**Rule k3_2consec (secondary)**

| arm | positives with a rise | rise − event, median [p25, p75] | rise − alert, median | negatives with a false rise | false rise − r, median |
|---|---|---|---|---|---|
| 4BI_N1 | 24.5 % (n 139) | -1.49 [-3.74, -0.17] | -0.21 | 19.5 % (n 128) | -0.87 |
| 4BI_N3 | 25.2 % (n 139) | -1.90 [-3.17, 0.06] | -0.28 | 18.8 % (n 128) | -2.13 |
| 32BI_N1 | 34.5 % (n 139) | -0.80 [-2.37, -0.08] | 0.58 | 19.5 % (n 128) | -2.13 |
| 32BI_N3 | 43.9 % (n 139) | -0.67 [-2.12, 0.07] | 0.60 | 21.9 % (n 128) | -1.50 |
| 32BI_N9 | 49.6 % (n 139) | -0.71 [-1.90, 0.40] | 0.71 | 22.7 % (n 128) | -2.36 |

### 2–4. Paired lead (big − small rise time, s; negative = 32B earlier), fairness and who-first


**Rule k3 (primary)**

| pair | input / stack / decoding | both rise | only 32B | only 4B | neither | mean [CI] | median [CI] | 32B earlier / same / later | false rise 32B / 4B (ratio; fair?) | who first, all 150: 32B / 4B / tie / neither |
|---|---|---|---|---|---|---|---|---|---|---|
| 32BI_N1-4BI_N1 | same frames, stack, greedy | 42 | 32 | 18 | 47 | -0.38 [-0.98, 0.19] | 0.00 [0.00, 0.00] | 10 / 22 / 10 | 43.8 / 36.7 % (1.19; yes) | 42 / 28 / 22 / 58 |
| 32BI_N3-4BI_N3 | same frames, stack, greedy | 40 | 40 | 13 | 46 | -0.20 [-0.88, 0.47] | 0.00 [0.00, 0.50] | 11 / 15 / 14 | 39.8 / 33.6 % (1.19; yes) | 51 / 27 / 15 / 57 |
| 32BI_N9-4BI_N3 | 9 vs 3 frames; same stack, greedy | 40 | 54 | 13 | 32 | -0.20 [-0.90, 0.53] | 0.00 [-0.50, 1.00] | 14 / 11 / 15 | 36.7 / 33.6 % (1.09; yes) | 68 / 28 / 11 / 43 |
| 32BI_N1-4BI_N3 | 1 vs 3 frames; same stack, greedy | 38 | 36 | 15 | 50 | -0.32 [-1.21, 0.55] | 0.00 [0.00, 0.50] | 12 / 13 / 13 | 43.8 / 33.6 % (1.30; yes) | 48 / 28 / 13 / 61 |

**Rule k2 (secondary)**

| pair | input / stack / decoding | both rise | only 32B | only 4B | neither | mean [CI] | median [CI] | 32B earlier / same / later | false rise 32B / 4B (ratio; fair?) | who first, all 150: 32B / 4B / tie / neither |
|---|---|---|---|---|---|---|---|---|---|---|
| 32BI_N1-4BI_N1 | same frames, stack, greedy | 75 | 31 | 13 | 20 | -0.05 [-0.48, 0.39] | 0.00 [0.00, 0.00] | 20 / 39 / 16 | 59.4 / 57.0 % (1.04; yes) | 51 / 29 / 39 / 31 |
| 32BI_N3-4BI_N3 | same frames, stack, greedy | 69 | 35 | 14 | 21 | -0.10 [-0.52, 0.30] | 0.00 [0.00, 0.00] | 22 / 30 / 17 | 57.0 / 47.7 % (1.20; yes) | 57 / 31 / 30 / 32 |
| 32BI_N9-4BI_N3 | 9 vs 3 frames; same stack, greedy | 75 | 43 | 8 | 13 | 0.09 [-0.33, 0.52] | 0.00 [0.00, 0.00] | 24 / 28 / 23 | 52.3 / 47.7 % (1.10; yes) | 67 / 31 / 28 / 24 |
| 32BI_N1-4BI_N3 | 1 vs 3 frames; same stack, greedy | 70 | 36 | 13 | 20 | -0.10 [-0.70, 0.51] | 0.00 [0.00, 0.00] | 24 / 25 / 21 | 59.4 / 47.7 % (1.25; yes) | 60 / 34 / 25 / 31 |

**Rule k3_2consec (secondary)**

| pair | input / stack / decoding | both rise | only 32B | only 4B | neither | mean [CI] | median [CI] | 32B earlier / same / later | false rise 32B / 4B (ratio; fair?) | who first, all 150: 32B / 4B / tie / neither |
|---|---|---|---|---|---|---|---|---|---|---|
| 32BI_N1-4BI_N1 | same frames, stack, greedy | 19 | 29 | 15 | 76 | 0.42 [-0.16, 1.00] | 0.00 [0.00, 1.00] | 3 / 8 / 8 | 19.5 / 19.5 % (1.00; yes) | 32 / 23 / 8 / 87 |
| 32BI_N3-4BI_N3 | same frames, stack, greedy | 21 | 40 | 14 | 64 | 0.76 [-0.24, 1.71] | 0.00 [0.00, 1.00] | 3 / 9 / 9 | 21.9 / 18.8 % (1.17; yes) | 43 / 23 / 9 / 75 |
| 32BI_N9-4BI_N3 | 9 vs 3 frames; same stack, greedy | 22 | 47 | 13 | 57 | 0.59 [-0.36, 1.55] | 0.50 [0.00, 1.00] | 6 / 5 / 11 | 22.7 / 18.8 % (1.21; yes) | 53 / 24 / 5 / 68 |
| 32BI_N1-4BI_N3 | 1 vs 3 frames; same stack, greedy | 17 | 31 | 18 | 73 | 0.24 [-0.82, 1.41] | 0.00 [-1.00, 1.00] | 6 / 4 / 7 | 19.5 / 18.8 % (1.04; yes) | 37 / 25 / 4 / 84 |

### 3 (secondary). Matched false-rise rate: k per model for 10 % false rise, cross-fitted on negatives

| arm | k fold 0 / fold 1 | held-out false-rise (pooled) | positives with a rise | rise − event median [p25, p75] |
|---|---|---|---|---|
| 4BI_N1 | 9.45 / 8.20 | 7.8 % | 7.2 % | -1.33 [-4.26, 0.72] |
| 4BI_N3 | 5.25 / 6.75 | 11.7 % | 10.1 % | -1.24 [-2.10, -0.58] |
| 32BI_N1 | 9.80 / 11.10 | 8.6 % | 7.2 % | -1.27 [-2.21, -0.30] |
| 32BI_N3 | 7.10 / 8.95 | 10.9 % | 13.7 % | 0.07 [-1.77, 0.42] |
| 32BI_N9 | 10.10 / 9.70 | 10.9 % | 10.8 % | 0.22 [-0.53, 0.73] |

| pair | both rise | only 32B | only 4B | neither | mean [CI] | median [CI] | 32B earlier / same / later | who first: 32B / 4B / tie / neither |
|---|---|---|---|---|---|---|---|---|
| 32BI_N1-4BI_N1 | 4 | 6 | 6 | 123 | 1.00 [0.00, 3.00] | 0.00 [0.00, 4.00] | 0 / 3 / 1 | 6 / 7 / 3 / 134 |
| 32BI_N3-4BI_N3 | 6 | 13 | 8 | 112 | 0.33 [-1.17, 1.33] | 1.00 [-1.50, 1.50] | 1 / 1 / 4 | 14 / 12 / 1 / 123 |
| 32BI_N9-4BI_N3 | 5 | 10 | 9 | 115 | -0.20 [-1.80, 1.20] | 0.00 [-3.00, 2.00] | 1 / 3 / 1 | 11 / 10 / 3 / 126 |
| 32BI_N1-4BI_N3 | 5 | 5 | 9 | 120 | -0.60 [-2.80, 1.60] | 0.00 [-4.00, 3.00] | 2 / 1 / 2 | 7 / 11 / 1 / 131 |

### 5. REFERENCE ONLY: first second the model's own answer is Yes (P(Yes) > 0.5) in the search window. **Biased by each model's willingness to say Yes.**

| arm | positives with a Yes | Yes − event median | negatives with a Yes in the window | raw Yes rate, all negative seconds |
|---|---|---|---|---|
| 4BI_N1 | 22.0 % | -0.43 | 10.7 % | 1.98 % |
| 4BI_N3 | 45.3 % | -0.15 | 32.7 % | 5.60 % |
| 32BI_N1 | 18.7 % | 0.03 | 8.0 % | 1.08 % |
| 32BI_N3 | 28.0 % | 0.32 | 8.7 % | 1.35 % |
| 32BI_N9 | 14.7 % | 0.37 | 2.0 % | 0.62 % |

| pair | both | only 32B | only 4B | neither | mean [CI] | median | 32B earlier / same / later |
|---|---|---|---|---|---|---|---|
| 32BI_N1-4BI_N1 | 17 | 11 | 16 | 106 | 0.53 [-0.71, 1.82] | 0.00 | 4 / 6 / 7 |
| 32BI_N3-4BI_N3 | 39 | 3 | 29 | 79 | 0.72 [0.23, 1.31] | 0.00 | 5 / 19 / 15 |
| 32BI_N9-4BI_N3 | 21 | 1 | 47 | 81 | 1.19 [0.38, 2.19] | 1.00 | 2 / 8 / 11 |
| 32BI_N1-4BI_N3 | 22 | 6 | 46 | 76 | 1.14 [0.23, 2.18] | 0.50 | 3 / 8 / 11 |

### 6. REFERENCE ONLY: event-relative AUROC (D14 definition)

| arm | −3 s | −2 s | −1 s | 0 s | +1 s |
|---|---|---|---|---|---|
| 4BI_N1 | 0.571 | 0.613 | 0.682 | 0.738 | 0.713 |
| 4BI_N3 | 0.563 | 0.614 | 0.688 | 0.773 | 0.750 |
| 32BI_N1 | 0.610 | 0.645 | 0.748 | 0.778 | 0.751 |
| 32BI_N3 | 0.591 | 0.661 | 0.748 | 0.841 | 0.808 |
| 32BI_N9 | 0.590 | 0.634 | 0.729 | 0.825 | 0.831 |

### Key observations
- **Rise and false-rise rates are both high under the primary rule (k = 3).**
  - Positives rise in 38–43 % (4B) and 53–68 % (32B) of clips.
  - Negatives also "rise" in their search window in 34–44 % of clips: 4B 33.6–36.7 %, 32B 36.7–43.8 %.
  - False-rise ratios within each pair are 1.09–1.30, so **the primary comparison is fair for all four pairs** (≤ 2×).
- **Paired lead, primary:** on clips where both models rise (38–42 per pair), every mean difference has a CI that includes 0 (−0.38 to −0.20 s), and every median is 0 s. 32B is earlier on 10–14 clips, the same second on 11–22, and later on 10–15.
- **Who first, over all 150 positives (primary):** 32B first on 42–68 clips vs 4B first on 28. The extra "32B first" clips are mostly clips where 32B rises and 4B does not (only-32B 32–54 vs only-4B 13–18), at a slightly higher 32B false-rise rate.
- **Secondary rules:** k = 2 (false rise 48–59 %) and k = 3 with 2 consecutive seconds (false rise 19–23 %) give the same pattern. Paired means are −0.10 to +0.76 s, every CI includes 0, and every median is 0 except 32B N = 9 vs 4B N = 3 at k3-2consec (+0.5 s, 32B later).
- **Matched 10 % false-rise rate (secondary):**
  - The fitted k is 5.3–11.1, and the held-out false rise is 7.8–11.7 %.
  - At those thresholds only 7–14 % of positives rise in any arm.
  - Paired n is 4–6 per pair; the median differences are 0 / +1.0 / 0 / 0 s, with CIs spanning 0.
  - Who-first is about even: 6 vs 7, 14 vs 12, 11 vs 10, 7 vs 11.
- **Reference: first Yes.** 4B says Yes more often on negative seconds (2.0 % and 5.6 % at N = 1 and N = 3, vs 1.1 / 1.3 / 0.6 % for 32B). Its first Yes comes earlier than 32B's (N = 3 pair +0.72 s [+0.23, +1.31], 32B later). This reflects willingness to say Yes, as labelled.
- **Reference: AUROC.** Event-relative AUROC is higher for 32B from −1 s (0.73–0.75 vs 0.68–0.69).

## Results consistency check
1. **Cross-check against committed measurements:**
   - D14 AUROCs are reproduced exactly; the AUROC-by-offset reference equals E1's curve (same data, same definition).
   - The assigned negative reference times follow StudyD2's rule, with KS p ≥ 0.83 in every bin.
   - No > 2× disagreement.
2. **Physical plausibility:** not applicable (no latency or throughput).
3. **Distribution sanity:** d varies per clip (p5–p95 0.74–6.8 log units). Rise times are spread across the search window (p25–p75 reported). Paired medians of exactly 0 come from integer-second decision times; the counts of same-second rises (11–39 per pair) are reported.
4. **Definition audit:** all definitions as pre-registered.
   - The search window r − 5 … r + 3 also includes post-event seconds, so a "rise" can be a post-event reaction; rise times are reported relative to the event.
   - The matched-k grid (0.50–15.00, step 0.05) is an implementation choice for "choose k for 10 %"; it was set before the results were seen.
5. **Claim linkage:** FORMULATION.md §Decisions (which tier to provision for a standing query). The per-clip analysis **does not support** an earlier-noticing advantage for 32B: no lead meets the pre-registered criterion.
6. **Proxy validity:**
   - "Rise above the clip's own baseline" is a proxy for "the model noticed a change". It is noisy: 34–44 % of negative clips "rise" in a 9-second window at k = 3. So a rise on a positive is weak evidence of noticing the crash, unless it happens at matched low false-rise rates, where few clips rise.

**Outcome:** all checks passed. No lead met the pre-registered criterion (CI excluding 0 under the primary rule AND holding at matched false-rise rates) for any pair. No further rules were tested after seeing the results.

## Interpretation
- **No earlier noticing:** measured against each model's own earlier level, neither model notices a coming crash earlier than the other on these traces.
- **What "32B first" reflects:** 32B's score departs from its baseline in more crash clips, so it is "first" more often when non-rising clips count as never. But it also departs slightly more often in normal clips, and when both rise, they rise in the same second at the median.
- **At strict matched thresholds:** with 10 % false rises, too few crash clips rise for either model to support a timing comparison.
- **The earlier evidence of a 32B lead stands as a ranking difference:** the about 1 s AUROC difference near the event (D3 / D14 / E1) is a difference in how scores rank at a given offset. It is not visible as earlier within-clip change.

## Part F: time-to-accident (TTA) at a fixed false-positive rate. ADDED AFTER E5's per-clip results were seen; reported separately from them

**Label:** **OFFLINE ANALYSIS OF EXISTING SCORES.** This uses the field convention: a threshold chosen to hold a fixed false-positive rate, and TTA before the event.

**Definitions:**
- **Threshold per arm:** the lowest threshold such that at most a fraction q of training-fold negative-clip decision seconds have s ≥ threshold, for q = 0.10 and 0.01.
  - 2 folds by clip, stratified by label, seed 0; evaluated on the other fold, swapped and pooled.
  - At one decision per second, **q = 0.10 is 360 and q = 0.01 is 36 false alarms per hour**, far above E1's 1–20 per hour.
- **Anticipated:** s ≥ threshold at some t in [event − 5, event]. TTA = event − first such t (positive = before the event).
- **Statistics:** clip bootstrap, 2,000 resamples, seed 0. Paired differences are 32B − 4B in TTA, so **positive = 32B earlier**.

| arm | q | held-out q achieved | recall [CI] | mean TTA (s) [CI] | median TTA (s) [CI] | n anticipated |
|---|---|---|---|---|---|---|
| 4BI_N1 | 0.1 | 0.1007 | 0.407 [0.327, 0.487] | 2.53 [2.13, 2.90] | 2.46 [1.67, 3.43] | 61 |
| 4BI_N3 | 0.1 | 0.0983 | 0.407 [0.333, 0.487] | 2.03 [1.65, 2.42] | 1.82 [0.92, 2.46] | 61 |
| 32BI_N1 | 0.1 | 0.0997 | 0.527 [0.447, 0.607] | 2.32 [1.98, 2.71] | 2.09 [1.36, 2.91] | 79 |
| 32BI_N3 | 0.1 | 0.1020 | 0.553 [0.473, 0.633] | 1.92 [1.59, 2.25] | 1.30 [0.90, 2.03] | 83 |
| 32BI_N9 | 0.1 | 0.0993 | 0.487 [0.407, 0.567] | 2.07 [1.72, 2.43] | 1.52 [1.05, 2.30] | 73 |
| 4BI_N1 | 0.01 | 0.0100 | 0.060 [0.027, 0.100] | 1.62 [0.48, 2.89] | 0.57 [0.30, 3.93] | 9 |
| 4BI_N3 | 0.01 | 0.0117 | 0.080 [0.040, 0.127] | 1.03 [0.47, 1.74] | 0.50 [0.30, 1.28] | 12 |
| 32BI_N1 | 0.01 | 0.0098 | 0.093 [0.047, 0.140] | 1.30 [0.53, 2.12] | 0.48 [0.30, 1.52] | 14 |
| 32BI_N3 | 0.01 | 0.0096 | 0.080 [0.040, 0.127] | 1.63 [0.93, 2.33] | 1.24 [0.32, 2.86] | 12 |
| 32BI_N9 | 0.01 | 0.0104 | 0.067 [0.033, 0.113] | 1.39 [0.69, 2.11] | 1.16 [0.30, 2.80] | 10 |

**Paired TTA (32B − 4B, s; positive = 32B earlier).**

| q | pair | both | only 32B | only 4B | neither | mean [CI] | median [CI] | 32B earlier / same / later | composite over all 150 (not anticipated = TTA 0): mean [CI] |
|---|---|---|---|---|---|---|---|---|---|
| 0.1 | 32BI_N1-4BI_N1 | 45 | 34 | 16 | 55 | -0.22 [-0.67, 0.20] | 0.00 [0.00, 0.00] | 8 / 23 / 14 | +0.194 [-0.087, +0.469] |
| 0.1 | 32BI_N3-4BI_N3 | 46 | 37 | 15 | 52 | -0.15 [-0.59, 0.26] | 0.00 [0.00, 0.00] | 9 / 25 / 12 | +0.233 [-0.041, +0.513] |
| 0.1 | 32BI_N9-4BI_N3 | 42 | 31 | 19 | 58 | -0.10 [-0.57, 0.40] | 0.00 [0.00, 0.00] | 7 / 24 / 11 | +0.178 [-0.101, +0.457] |
| 0.1 | 32BI_N1-4BI_N3 | 46 | 33 | 15 | 56 | 0.04 [-0.50, 0.59] | 0.00 [0.00, 0.00] | 10 / 24 / 12 | +0.394 [+0.109, +0.691] |
| 0.01 | 32BI_N1-4BI_N1 | 4 | 10 | 5 | 131 | -0.75 [-2.25, 0.00] | 0.00 [-3.00, 0.00] | 0 / 3 / 1 | +0.024 [-0.115, +0.155] |
| 0.01 | 32BI_N3-4BI_N3 | 6 | 6 | 6 | 132 | 0.50 [0.00, 1.17] | 0.00 [0.00, 1.50] | 2 / 4 / 0 | +0.048 [-0.067, +0.161] |
| 0.01 | 32BI_N9-4BI_N3 | 5 | 5 | 7 | 133 | 0.40 [-0.40, 1.40] | 0.00 [-1.00, 2.00] | 2 / 2 / 1 | +0.010 [-0.093, +0.115] |
| 0.01 | 32BI_N1-4BI_N3 | 5 | 9 | 7 | 129 | -0.20 [-0.60, 0.00] | 0.00 [-1.00, 0.00] | 0 / 4 / 1 | +0.039 [-0.074, +0.163] |

**Part F observations:**
- **Held-out q:** within 0.0983–0.1020 (target 0.10) and 0.0096–0.0117 (target 0.01) in every arm.
- **q = 0.10:**
  - **Recall:** 32B anticipates more crashes, 0.487–0.553, against 0.407 for 4B.
  - **Paired TTA on clips both anticipate (42–46 per pair):** mean −0.22 to +0.04 s, every CI including 0; median 0 s; most clips are the same second (23–25).
  - **Composite (non-anticipated = 0):** +0.18 to +0.39 s. **Only 32B N = 1 vs 4B N = 3 excludes 0, at +0.39 [+0.11, +0.69] s.** Because the composite counts not-anticipated as TTA 0, it combines recall with timing.
- **q = 0.01:** recall is 0.060–0.093. Paired n is 4–6, and every paired and composite CI includes 0.
- **No 32B earliness claim meets the rule** on paired TTA among clips both anticipate, at either q.

## Part G: AP at fixed horizons (Nexar challenge style). ADDED AFTER E5's per-clip results were seen; reported separately from them

**Label:** **OFFLINE ANALYSIS OF EXISTING SCORES.**

**Definitions:**
- **Positives:** each positive clip's score at the whole-second t nearest event − h, clamped to its grid.
- **Negatives:** all 5,196 negative-clip decision seconds. The base rate is 150 / (150 + 5,196) = 0.028, so chance AP ≈ 0.028.
- **Approximation:** D14 decisions are 1 s apart, so **horizons below 1 s are approximate**. 75 of 150 positives had t moved by more than 0.25 s from event − h at every horizon (0 clamped).
- **Not the challenge's test set:** these are validation traces, not the Nexar challenge's own test clips, and the challenge's AP definition and negative set differ, so the numbers are not comparable to its leaderboard.
- **Bootstrap:** resamples positive and negative clips (stratified by label) jointly for all arms; 2,000 resamples, seed 0.

| h (s) | arm | AP [CI] | AUROC [CI] |
|---|---|---|---|
| 0.0 | 4BI_N1 | 0.102 [0.069, 0.154] | 0.738 [0.687, 0.784] |
| 0.0 | 4BI_N3 | 0.141 [0.097, 0.202] | 0.773 [0.729, 0.814] |
| 0.0 | 32BI_N1 | 0.147 [0.101, 0.209] | 0.778 [0.733, 0.820] |
| 0.0 | 32BI_N3 | 0.182 [0.129, 0.252] | 0.841 [0.806, 0.873] |
| 0.0 | 32BI_N9 | 0.150 [0.104, 0.219] | 0.825 [0.788, 0.858] |
| 0.5 | 4BI_N1 | 0.062 [0.049, 0.096] | 0.713 [0.663, 0.762] |
| 0.5 | 4BI_N3 | 0.079 [0.060, 0.121] | 0.740 [0.696, 0.783] |
| 0.5 | 32BI_N1 | 0.107 [0.080, 0.165] | 0.775 [0.731, 0.818] |
| 0.5 | 32BI_N3 | 0.113 [0.083, 0.162] | 0.809 [0.772, 0.845] |
| 0.5 | 32BI_N9 | 0.088 [0.068, 0.135] | 0.779 [0.738, 0.819] |
| 1.0 | 4BI_N1 | 0.051 [0.041, 0.075] | 0.683 [0.630, 0.731] |
| 1.0 | 4BI_N3 | 0.054 [0.043, 0.078] | 0.688 [0.641, 0.736] |
| 1.0 | 32BI_N1 | 0.072 [0.057, 0.102] | 0.749 [0.706, 0.792] |
| 1.0 | 32BI_N3 | 0.067 [0.054, 0.089] | 0.749 [0.709, 0.789] |
| 1.0 | 32BI_N9 | 0.061 [0.049, 0.082] | 0.731 [0.692, 0.769] |
| 1.5 | 4BI_N1 | 0.040 [0.034, 0.053] | 0.632 [0.578, 0.686] |
| 1.5 | 4BI_N3 | 0.040 [0.033, 0.058] | 0.620 [0.569, 0.670] |
| 1.5 | 32BI_N1 | 0.048 [0.040, 0.065] | 0.674 [0.626, 0.720] |
| 1.5 | 32BI_N3 | 0.048 [0.041, 0.063] | 0.685 [0.641, 0.728] |
| 1.5 | 32BI_N9 | 0.045 [0.038, 0.060] | 0.665 [0.619, 0.708] |
| 2.0 | 4BI_N1 | 0.037 [0.032, 0.049] | 0.613 [0.558, 0.663] |
| 2.0 | 4BI_N3 | 0.038 [0.032, 0.048] | 0.614 [0.562, 0.666] |
| 2.0 | 32BI_N1 | 0.041 [0.035, 0.055] | 0.645 [0.597, 0.693] |
| 2.0 | 32BI_N3 | 0.043 [0.036, 0.054] | 0.661 [0.613, 0.707] |
| 2.0 | 32BI_N9 | 0.040 [0.034, 0.052] | 0.634 [0.583, 0.681] |

**Paired 32B − 4B (joint clip bootstrap).**

| h (s) | pair | AP diff [CI] | AUROC diff [CI] |
|---|---|---|---|
| 0.0 | 32BI_N1-4BI_N1 | +0.045 [+0.009, +0.086] | +0.040 [+0.005, +0.077] |
| 0.0 | 32BI_N3-4BI_N3 | +0.041 [+0.006, +0.079] | +0.068 [+0.036, +0.102] |
| 0.0 | 32BI_N9-4BI_N3 | +0.009 [-0.027, +0.055] | +0.051 [+0.014, +0.088] |
| 0.0 | 32BI_N1-4BI_N3 | +0.006 [-0.040, +0.052] | +0.005 [-0.034, +0.041] |
| 0.5 | 32BI_N1-4BI_N1 | +0.045 [+0.016, +0.088] | +0.062 [+0.026, +0.101] |
| 0.5 | 32BI_N3-4BI_N3 | +0.034 [+0.009, +0.060] | +0.069 [+0.031, +0.108] |
| 0.5 | 32BI_N9-4BI_N3 | +0.008 [-0.016, +0.038] | +0.039 [+0.000, +0.080] |
| 0.5 | 32BI_N1-4BI_N3 | +0.028 [-0.003, +0.068] | +0.035 [-0.003, +0.073] |
| 1.0 | 32BI_N1-4BI_N1 | +0.021 [+0.005, +0.041] | +0.067 [+0.029, +0.106] |
| 1.0 | 32BI_N3-4BI_N3 | +0.013 [-0.003, +0.027] | +0.061 [+0.023, +0.101] |
| 1.0 | 32BI_N9-4BI_N3 | +0.007 [-0.009, +0.021] | +0.042 [+0.002, +0.085] |
| 1.0 | 32BI_N1-4BI_N3 | +0.019 [+0.001, +0.039] | +0.061 [+0.020, +0.105] |
| 1.5 | 32BI_N1-4BI_N1 | +0.007 [-0.001, +0.019] | +0.042 [+0.003, +0.082] |
| 1.5 | 32BI_N3-4BI_N3 | +0.008 [-0.004, +0.017] | +0.065 [+0.022, +0.107] |
| 1.5 | 32BI_N9-4BI_N3 | +0.005 [-0.008, +0.014] | +0.045 [-0.001, +0.090] |
| 1.5 | 32BI_N1-4BI_N3 | +0.007 [-0.006, +0.020] | +0.054 [+0.009, +0.101] |
| 2.0 | 32BI_N1-4BI_N1 | +0.004 [-0.003, +0.014] | +0.032 [-0.006, +0.073] |
| 2.0 | 32BI_N3-4BI_N3 | +0.005 [-0.001, +0.013] | +0.047 [+0.006, +0.091] |
| 2.0 | 32BI_N9-4BI_N3 | +0.002 [-0.005, +0.011] | +0.019 [-0.026, +0.067] |
| 2.0 | 32BI_N1-4BI_N3 | +0.003 [-0.004, +0.014] | +0.030 [-0.014, +0.077] |

**Part G observations:**
- **AP falls with horizon for every arm:** 0.10–0.18 at h = 0, 0.04–0.05 at h = 1.5 s and 0.037–0.043 at h = 2 s, against a base rate of 0.028. AUROC falls similarly, from 0.74–0.84 to 0.61–0.66.
- **Matched N pairs (N = 1, N = 3):**
  - 32B has higher AP at h = 0 and 0.5 s, with CIs excluding 0 (+0.034 to +0.045). At h = 1.0 s the N = 1 pair still excludes 0 (+0.021 [+0.005, +0.041]); the N = 3 pair does not (+0.013 [−0.003, +0.027]).
  - At h ≥ 1.5 s no AP difference excludes 0.
  - 32B has higher AUROC from h = 0 through 1.5 s in both matched pairs (+0.040 to +0.069, CIs excluding 0), and at h = 2 s for N = 3 only (+0.047).
- **32B N = 9 vs 4B N = 3:** no AP difference excludes 0 at any horizon. AUROC excludes 0 at h = 0 and 1.0 s; at h = 0.5 s the lower bound is 0.000.

## Parts F and G: interpretation (separate from E5's per-clip result)
- **The two conventions point the same way as E1 and E5.**
  - In the challenge convention (Part G), 32B separates the seconds just before a crash from normal driving better than 4B, measurably up to about 1 s ahead (AP) and 1.5 s ahead (AUROC). That is better detection at a fixed horizon.
  - In the TTA convention (Part F), at a per-second false-positive rate of 10 %, 32B catches more crashes but does not catch the shared ones earlier. At 1 % neither catches enough to compare.
- **No earliness claim:** E5's within-clip rise shows no earlier noticing either. So the 32B advantage on this data is a better ranking near the event, not an earlier first alarm on the same crash.
- **Operating points:** the per-second rates in Part F (36–360 per hour) are 2–360× higher than the alarm budgets in E1 (1–20 per hour), where detection was low for both.

