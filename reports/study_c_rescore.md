# Study C Re-scoring — Tolerance-Based Accuracy and Error Analysis

**Date:** 2026-08-30  
**Input:** `results/vision/study_c/study_c_trials.csv` (1,440 rows)  
**Scripts:** `experiments/vision/study_c_rescore.py`, `experiments/vision/study_c_rescore_plots.py`  
**No inference. No model loading. Re-analysis of existing data only.**

---

## 1. What Was Recomputed

The original Study C scored object-counting accuracy by exact match (parsed integer equals annotated person count). Near-zero exact-match accuracy at L3 and L4 raised the question of whether the floor reflects genuine model failure or an artifact of the scoring criterion. This re-analysis applies tolerance-based scoring, decomposes the error distribution, and computes Spearman correlation between parsed answers and ground truth.

**Parse-status handling.** Two non-standard parse statuses appear in the CSV:
- `parse_status = "unparseable"` (9 rows total: 6 in qwenvl3b|stepwise|L1, 3 in qwenvl3b|stepwise|L2): no valid integer could be extracted. These rows have an empty `correct` field. Excluded from error statistics; counted in denominators for conservative accuracy.
- `parse_status = "fallback_last_number"` (6 rows: all in qwenvl3b|stepwise|L4): a valid integer was found as the last number in the text (not via the "Final answer:" pattern). These have valid `parsed_answer` and `correct` fields and are included as parseable.

**Scoring note from original report.** The original report claimed unparseable rows were "counted as incorrect (conservative)." The data shows the original script used the restricted denominator (parseable rows only) for the two cells that had `parse_status="unparseable"` rows. This is documented in SC2 below and affects two cells by 1–5 pp. Both conservative and restricted values are reported here; conservative is the primary metric.

---

## 2. Sanity Checks

**SC1 — Row count:** 1,440 rows. PASS.

**SC2 — Exact-match replication:** Recomputed exact-match (conservative) matches the original report for 14 of 16 cells. Two cells had discrepancies because the original used restricted denominator:

| Cell | Original | Recomputed (conservative) | Restricted | Note |
|------|---------|--------------------------|------------|------|
| qwenvl3b\|stepwise\|L1 | 0.821 | 0.767 | 0.821 | Original used restricted (n_parseable=84) |
| qwenvl3b\|stepwise\|L2 | 0.586 | 0.567 | 0.586 | Original used restricted (n_parseable=87) |
| All other 14 cells | — | match ≤ 0.001 | — | No unparseable rows; conservative = restricted |

PASS (discrepancies explained and documented).

**SC3 — GT bins:** All 1,440 ground-truth values fall within their stated level bins (L1: exactly 1; L2: 2–3; L3: 4–7; L4: 8+). PASS.

**SC4 — Row accounting:** All 16 cells contain exactly 90 rows. Total = 1,440. No rows dropped. PASS.

---

## 3. Metric Tables

### 3a. Full per-cell table

*ex_c = exact conservative, w1_c = within-1 conservative, w2_c = within-2 conservative, rt25 = |err|/gt ≤ 0.25, ME = mean signed error, MAE = mean absolute error, SP = Spearman correlation. unp = unparseable rows (excluded from error stats).*

| model | mode | level | n | unp | ex_c | w1_c | w2_c | rt25 | ME | MAE | Spearman |
|-------|------|-------|---|-----|------|------|------|------|----|-----|----------|
| qwenvl3b | direct | L1 | 90 | 0 | 0.967 | 1.000 | 1.000 | 0.967 | −0.03 | 0.03 | 0.952 |
| qwenvl3b | direct | L2 | 90 | 0 | 0.700 | 0.900 | 0.967 | 0.700 | −0.37 | 0.43 | 0.520 |
| qwenvl3b | direct | L3 | 90 | 0 | 0.233 | 0.667 | 0.767 | 0.667 | −1.43 | 1.70 | 0.412 |
| qwenvl3b | direct | L4 | 90 | 0 | 0.067 | 0.367 | 0.467 | 0.467 | +0.37 | 6.50 | 0.551 |
| qwenvl3b | stepwise | L1 | 90 | 6 | 0.767 | 0.933 | 0.933 | 0.767 | +0.11 | 0.18 | 0.779 |
| qwenvl3b | stepwise | L2 | 90 | 3 | 0.567 | 0.933 | 0.967 | 0.567 | −0.24 | 0.45 | 0.545 |
| qwenvl3b | stepwise | L3 | 90 | 0 | 0.300 | 0.633 | 0.867 | 0.633 | −1.03 | 1.37 | 0.348 |
| qwenvl3b | stepwise | L4 | 90 | 0 | 0.033 | 0.033 | 0.233 | 0.233 | −4.47 | 4.87 | 0.506 |
| qwenvl7b | direct | L1 | 90 | 0 | 0.933 | 1.000 | 1.000 | 0.933 | −0.07 | 0.07 | 0.907 |
| qwenvl7b | direct | L2 | 90 | 0 | 0.700 | 0.933 | 0.967 | 0.700 | −0.33 | 0.40 | 0.595 |
| qwenvl7b | direct | L3 | 90 | 0 | 0.367 | 0.800 | 0.867 | 0.800 | −0.87 | 1.13 | 0.529 |
| qwenvl7b | direct | L4 | 90 | 0 | 0.133 | 0.333 | 0.467 | 0.533 | +1.77 | 5.97 | 0.667 |
| qwenvl7b | stepwise | L1 | 90 | 0 | 0.967 | 1.000 | 1.000 | 0.967 | −0.03 | 0.03 | 0.952 |
| qwenvl7b | stepwise | L2 | 90 | 0 | 0.700 | 0.933 | 1.000 | 0.700 | −0.30 | 0.37 | 0.601 |
| qwenvl7b | stepwise | L3 | 90 | 0 | 0.167 | 0.633 | 0.767 | 0.633 | −1.70 | 1.83 | 0.434 |
| qwenvl7b | stepwise | L4 | 90 | 0 | 0.000 | 0.100 | 0.233 | 0.233 | −4.53 | 6.00 | 0.418 |

### 3b. 7B-minus-3B gap by tolerance

| mode | level | exact gap | w1 gap | w2 gap | rt25 gap |
|------|-------|-----------|--------|--------|----------|
| direct | L1 | −0.033 | 0.000 | 0.000 | −0.033 |
| direct | L2 | 0.000 | +0.033 | 0.000 | 0.000 |
| direct | L3 | +0.133 | +0.133 | +0.100 | +0.133 |
| direct | L4 | +0.067 | −0.033 | 0.000 | +0.067 |
| stepwise | L1 | +0.200 | +0.067 | +0.067 | +0.200 |
| stepwise | L2 | +0.133 | 0.000 | +0.033 | +0.133 |
| stepwise | L3 | −0.133 | 0.000 | −0.100 | 0.000 |
| stepwise | L4 | −0.033 | +0.100 | 0.000 | 0.000 |

### 3c. Pooled Spearman per (model, mode)

| model | mode | pooled ρ | n (parseable) |
|-------|------|---------|---------------|
| qwenvl3b | direct | 0.753 | 360 |
| qwenvl3b | stepwise | 0.858 | 351 |
| qwenvl7b | direct | 0.883 | 360 |
| qwenvl7b | stepwise | 0.696 | 360 |

**Figures:** `figures/vision/study_c_rescore_accuracy.{pdf,png}`, `study_c_rescore_errors.{pdf,png}`, `study_c_rescore_scatter.{pdf,png}`

---

## 4. Direct Answers to RQ1–RQ3

### RQ1: Does headroom reappear at L3 and L4 under tolerance scoring?

**Yes, substantially at L3. Partially at L4.**

At L3, within-1 accuracy is 2–3× the exact-match accuracy:

| model/mode | exact | within-1 | within-2 |
|------------|-------|---------|---------|
| 3B direct | 0.233 | 0.667 | 0.767 |
| 7B direct | 0.367 | 0.800 | 0.867 |
| 3B stepwise | 0.300 | 0.633 | 0.867 |
| 7B stepwise | 0.167 | 0.633 | 0.767 |

At L4, modest headroom appears under within-1 (0.033–0.467 across conditions) and within-2 (0.233–0.533). The absolute values remain low, but they are not uniformly zero.

The near-zero exact-match accuracy at L3 and L4 is therefore substantially an artifact of the scoring criterion. Models are frequently off by one count, not randomly guessing.

### RQ2: Do 3B and 7B error distributions differ at high difficulty where exact match is similar?

**Yes, in signed-error pattern and Spearman correlation, but not dramatically in tolerance-based accuracy.**

**At L3 (direct mode):** The 7B advantage (+0.133 exact) is preserved under within-1 (+0.133) and within-2 (+0.100). 7B genuinely makes fewer errors in direct mode at L3. Under stepwise, the 3B advantage under exact match vanishes under within-1 (gap = 0.000): both models are off by similar amounts; 7B makes larger errors in absolute terms (MAE 1.83 vs 1.37), so the 3B apparent advantage at L3 stepwise exact-match is partly a sampling artifact of which errors fall just inside vs outside the zero-tolerance boundary.

**At L4:** The signed-error patterns diverge. In **direct** mode, 7B has a higher mean error (+1.77 vs +0.37), meaning 7B overcounts more on average; 3B's median is −1.5 (undercount). In **stepwise** mode, both models undercount by ~4.5 people on average (3B: −4.47, 7B: −4.53) — nearly identical, consistent with a shared failure mode (step-by-step enumeration loses track of dense crowds). The Spearman correlation at L4 direct is higher for 7B (0.667) than 3B (0.551), indicating 7B's predictions better track the rank-ordering of person counts.

**Summary:** A capability gap exists under tolerance scoring at L3 (direct mode). At L4 both models are largely indistinguishable in tolerance-based accuracy, but 7B maintains higher ordinal correlation in direct mode.

### RQ3: Is there systematic directional bias, and does it change with difficulty?

**Yes. The bias changes sign and magnitude with difficulty, and differs by mode.**

| level | 3B direct ME | 7B direct ME | 3B stepwise ME | 7B stepwise ME |
|-------|-------------|-------------|----------------|----------------|
| L1 | −0.03 | −0.07 | +0.11 | −0.03 |
| L2 | −0.37 | −0.33 | −0.24 | −0.30 |
| L3 | −1.43 | −0.87 | −1.03 | −1.70 |
| L4 | +0.37 | +1.77 | −4.47 | −4.53 |

- **L1:** Both models are essentially unbiased (|ME| < 0.15).
- **L2:** Mild undercount (−0.24 to −0.37). Models tend to say "2" when ground truth is "3."
- **L3:** Systematic undercount by ~1 person for both models and both modes (median = −1.00 in all cells). The model reliably misses one person in 4–7 person scenes.
- **L4 direct:** The bias reverses sign — both models overcount on average (means +0.37 and +1.77), while both have negative medians (−1.5 and −1.0). The mean is pulled up by rare large overcounts (e.g., predicting 25 when GT is 10). The typical behavior is still undercounting, but tail overcounts are larger for 7B.
- **L4 stepwise:** Both models massively undercount (mean ~−4.5 persons). This is the CoT collapse noted in the original study — long reasoning traces diverge and lose count.

The undercount trend at L2–L3 is consistent with a simple hypothesis: models see a partial view of the scene and count visible/salient persons, missing occluded or peripheral ones. The L4 direct overcount tail may reflect models choosing a number from a different distribution (e.g., "about 20" for a crowd scene).

### Spearman correlation: models are tracking count, not guessing

The pooled Spearman correlation ranges from 0.696 to 0.883 across conditions — all substantially above zero. At L4 specifically, direct mode Spearman is 0.551 (3B) and 0.667 (7B), meaning models that produce near-zero exact-match accuracy are still producing outputs that positively correlate with the true count. The L4 exact-match floor is a calibration problem, not a complete perception failure.

L4 stepwise Spearman is lower (0.418 for 7B, 0.506 for 3B), consistent with the CoT collapse producing less informative answers.

---

## 5. What Cannot Be Inferred

**Why the within-1 accuracy is high but within-2 is only modestly higher at some cells.** The errors are often concentrated at ±1 (off by one) rather than ±2. This is visible in the error distributions but the mechanism (e.g., counting vs localization, occlusion) cannot be determined from these data.

**Whether a different image resolution would change the accuracy pattern.** All images were resized to 560×560. Higher resolution could reveal occluded persons and change the accuracy floor.

**Whether the overcount tail at L4 direct reflects a specific failure mode** (e.g., the model sees motion blur or overlap as multiple people). Inspecting which images produce large positive errors would require examining individual cases — possible but not done here.

**Statistical significance.** No hypothesis tests were applied. The differences reported are descriptive. With n=90 per cell, a gap of ~0.10 in accuracy corresponds to about 9 trials, which should be detectable with a McNemar test but has not been tested.

---

## 6. Usability Verdict

**The difficulty axis becomes usable at L3 under tolerance scoring but remains a weak discriminator at L4.**

Under within-1 scoring, L3 accuracy spans 0.633–0.800 (vs 0.167–0.367 exact), giving enough headroom to observe model and mode differences. L4 within-1 spans 0.033–0.467, which is low but non-degenerate. A future experiment targeting this difficulty range should use within-1 or relative-tolerance (25%) as the primary accuracy metric rather than exact match. The task does not need to be replaced — the scoring criterion does.

**One-sentence answer:** The difficulty axis is usable for L3 under within-1 scoring (headroom 0.63–0.80), and partially usable at L4, but exact-match should be retired as the primary criterion for multi-person counting above L2.
