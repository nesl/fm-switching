# StudyCTRL1c-calibrated: the trigger comparison redone with per-tier calibration and streaming AP

> **READ THIS FIRST. This report holds TWO RUNS.** Sections 1 to 15 are the FIRST RUN, whose primary
> reading was the fully cross-fitted calibration (five per-fold Platt maps); it raised one STOP AND
> ASK, on sanity check (a). The user ruled, and **sections 16 to 22 are the FINAL PRIMARY: ONE Platt
> map per tier fitted on the StudyD3 Nexar DEV split, used for both the trigger decisions and the
> scoring.** Under the final primary sanity check (a) holds EXACTLY, and **the answer to Q11 CHANGES:
> the cloud-initiated trickle at a 10 % call budget beats random escalation (+116.8 capture-fraction
> points, CI [+3.5, +359.0], live trigger in 5 of 5 folds), where the first run found that no causal
> family beat random anywhere.** Section 18 also re-labels the Rule 2 classification under the band
> the user set, and NO causal cell survives as a real negative. Every table in sections 1 to 15 is
> retained as a LABELLED SENSITIVITY and is NOT the primary reading.

Pre-registered before anything was computed. A concurrent session (StudyPOL3/T0) holds
`research/EXPERIMENTS.md`, and CLAUDE.md forbids editing it from two sessions at once, so the full
13-field row text was written to the session scratchpad
(`.../scratchpad/ctrl1c_prereg_FROZEN.md`, timestamped **2026-11-16T14:36:42-08:00**) BEFORE the
first number was produced, and the EXPERIMENTS.md row was inserted verbatim from that frozen text
at the end of the study. That file is the pre-registration of record; the registry row is a copy of
it. Nothing in the frozen text, including the decision rule and the sanity checks, was changed
after computation began.

CPU only on flash: no GPU, no model server, no inference, no scikit-learn. Every score is a
committed StudyD14b trace. **StudyCTRL1b-crossfit is SUPERSEDED FOR COMPARISON by this row, not
deleted**: it stays in `results/dashcam/ctrl1b/` and `reports/study_ctrl1b_crossfit.md`.

---

## 0. One page

**A STOP AND ASK fired, and it is the first thing to read.** Sanity check (a), as the brief words
it, cannot hold under the design the brief pre-registers, and the violation is measured, not
argued. The check says always-cloud and device-only must be unchanged by calibration "because a
per-tier monotone map does not reorder scores within a tier". That is exactly true of ONE map per
tier and it is verified here to 0.0: with a single per-tier Platt map applied to all 300 clips,
device-only is 0.4776042449177038 and always-cloud 0.5675307471627266, bit-identical to StudyE9c,
and the streaming AP is identical to StudyE9b at every horizon to 7e-18. But the brief also
requires the calibration to be CROSS-FITTED, so the five folds carry five DIFFERENT affine maps,
and both metrics rank ACROSS clips: a value from fold 0 and a value from fold 1 are then no longer
on one scale. Under the cross-fitted application the references move to device-only 0.4524929 and
always-cloud 0.5629252, that is -0.0251 and -0.0046 challenge mAP, and the always-cloud minus
device-only gap the arms compete for grows from 0.0899 to 0.1104. The denominator of every capture
fraction therefore shifts by an amount comparable to the effects being measured. This is a property
of cross-fitting a calibration under a cross-clip rank metric, and the user should decide which of
the two readings is primary before Q11 is settled. Both are reported in full; the pre-registered
cross-fitted one is used for the decision rule, and section 8 re-scores the IDENTICAL episodes on
one common scale so the two can be read side by side.

**The gate passed.** The positives-only oracle, the artifact that made StudyCTRL1b unreadable,
scores 0.5447 against device-only 0.4525 under the cross-fitted calibration, a margin of **+0.0923**
(and 0.5725 against 0.4776, margin +0.0949, on one map). Without the calibration the same arm
scores 0.3911 against 0.4776, margin **-0.0865**, reproducing StudyCTRL1b's number exactly. The
defect D57 named is real, it is removed, and the negative control that disables the calibration
brings it straight back.

**And the answer to Q11 does not change.** Under the pre-registered rule, on the pre-registered
primary metric, **NOT ONE CAUSAL TRIGGER FAMILY BEATS RANDOM ESCALATION AT THE SAME BUDGET AT ANY
BUDGET.** Only the two non-causal oracles do. The same verdict holds under all three calibrations
and under both scale readings, with one direction-reversed exception at 5 % where random beats the
two trickle arms. What the calibration DOES change is how large the headroom looks: StudyE9b's own
device-triggered escalation, with its decisions byte-identical, goes from capturing 3 to 18 % of
the gap to capturing 12 to 49 % of it. The trigger family is still not where the value is; the
scale was.

---

## 1. What changed from StudyCTRL1b, and nothing else

| # | change | why | where |
|---|---|---|---|
| C1 | per-tier calibration, primary Platt on the training folds' decision instants with the clip-level label, stored and applied as the calibrated log-odds a*s + b | D57: the 32B's raw score runs a median -5.125 log units below the 4B's, so mixing tiers in a rank metric reads tier identity | `ctrl1c_calibrate.py` |
| C2 | primary metric is StudyE9b's STREAMING AP over all decision instants, averaged over horizons 0.5 / 1.0 / 1.5 s; challenge mAP is the secondary. **The fitting objective follows the primary metric** | D58: the challenge mAP reads one crop per clip | `ctrl1c_metrics.py`, `fit_fold` |
| C3 | background cadence grid extended from {1, 2, 4} s to {1, 2, 4, 5, 6, 8, 10} s for the cloud trickle and the context-modulated trickle | D58: 4 s alone costs 0.1250 of the decision instants | `BG_CADENCES_S` |
| C4 | the learned ceiling's signed per-instant gain target retargeted onto the calibrated scale | follows C1 | `fit_learned` on the calibrated Runner |
| C5 | a LOAD column beside the budget, DERIVED from the committed ENG1 step model | D58: the budget is a test variable standing for cloud spare capacity | `load_column` |
| C6 | the absolute-confidence and cloud-trickle threshold searches bisect over the training folds' own observed min and max instead of StudyCTRL1b's [-30, 0.5] log units | [-30, 0.5] was chosen for the RAW score and is meaningless on the calibrated scale; a search bound is not a model parameter and every realized budget is reported beside its target | `fit_fold`, `fit_context_trickle` |

Carried forward UNCHANGED and declared rather than re-derived: the 5 folds (label-stratified,
sha256(file_name) order, fold = rank mod 5, 60 clips each, 300 total), the 11 arms, the tunable
grid, the 0.5-s decision cadence, every latency (device cadence 0.75 s and latency 0.567 s, cloud
latency 0.3950 s, uplink 13.6 Mbit/s, RTT 0.044 s), the call-fraction budget metric (B1), the
oracle's two readings (B2b) and its CONSTANT lead link (B2c), the episode-close rule (B3), the
background-charging rule (B4), trigger causality (B5), the signed-gain target (B8) and the context
threshold rule (B9: 0.5 for a binary feature, the training median for a continuous one).

**C2 is a decision, so it is recorded as one.** StudyCTRL1b selected tunables by maximizing the
training folds' challenge mAP. This row declares that metric defective for the trigger question,
so selecting on it would carry the defect into the comparison; the objective is therefore the
training folds' streaming AP at the same fixed call-fraction budget. The brief lists metric
definitions among the things this row may change, so this is inside the pre-registered scope, but
it means the SECONDARY challenge-mAP column here is not directly comparable with StudyCTRL1b's
headline table: the arms behind it were chosen on a different objective. The two readings of the
same arms are kept in one table so this cannot be read past.

**The three NOT AVAILABLE feature families stay NOT AVAILABLE and nothing is substituted**: no
image features (the d14b frame store does not exist on this machine and opencv is absent), no
Nexar ego speed (not in the committed clip table), and elapsed time in the clip excluded by
decision as an event-placement leak. The learned ceiling remains a ceiling on
SCORE-DYNAMICS-AND-CONTEXT predictability.

---

## 2. The calibration fits

Per tier, per fold, fitted on the 240 training clips' decision instants on the 0.5-s cadence with
the clip-level label. Stored as the calibrated log-odds `g(s) = a * s + b`; the probability is its
sigmoid and gives an identical AP, because one common increasing function applied to both tiers'
calibrated log-odds cannot change the pooled order.

| fold | device 4BI N1 a | device b | cloud 32BI N1 a | cloud b | training base rate |
|---|---|---|---|---|---|
| 0 | +0.086642 | +1.0076 | +0.081366 | +1.3026 | 0.5191 |
| 1 | +0.053570 | +0.5959 | +0.077949 | +1.1756 | 0.5078 |
| 2 | +0.077925 | +0.9063 | +0.078784 | +1.2399 | 0.5147 |
| 3 | +0.063718 | +0.7304 | +0.076662 | +1.1973 | 0.5132 |
| 4 | +0.053250 | +0.6062 | +0.074241 | +1.1336 | 0.5097 |

Every slope is positive, which is what makes the map order-preserving within a tier; the code
records the sign and the sanity check asserts it.

Two single-map fits are saved for the policy library, and neither is used in any cross-fitted
number: `dev90` (the committed D14b DEV side, device a +0.038113 b +0.4388, cloud a +0.049983
b +0.7683) and `all300` (device a +0.066681 b +0.7643, cloud a +0.077677 b +1.2077). The policy
library should prefer `dev90`, which never saw the committed EVAL side.

**Reliability on HELD-OUT instants** (Brier against the Brier of the base rate, and the
expected calibration error over 10 equal-count bins):

| fold | device Brier | device base-rate Brier | device ECE | cloud Brier | cloud base-rate Brier | cloud ECE |
|---|---|---|---|---|---|---|
| 0 | 0.26380 | 0.24986 | 0.1201 | 0.24288 | 0.24986 | 0.0577 |
| 1 | 0.23564 | 0.24888 | 0.0839 | 0.23909 | 0.24888 | 0.0706 |
| 2 | 0.25236 | 0.24996 | 0.0608 | 0.23811 | 0.24996 | 0.0559 |
| 3 | 0.24097 | 0.24987 | 0.0764 | 0.23437 | 0.24987 | 0.0341 |
| 4 | 0.23540 | 0.24934 | 0.0707 | 0.23389 | 0.24934 | 0.0506 |

**The cloud's calibration generalizes and the device's barely does.** The 32B's calibrated
probability beats the base rate out of sample in 5 of 5 folds; the 4B's does not in 2 of 5 (folds 0
and 2), and its ECE is the larger in 5 of 5. A per-instant score is being asked to predict a
CLIP-level label, which is the brief's pre-registered estimand, and the 4B carries less of that
than the 32B. This is a limitation of the primary calibration target, not of the mechanism: the
calibration's job here is to put the two tiers on one scale, and it does that (section 6, link C1),
whether or not either tier's probability is individually sharp.

Isotonic, the first sensitivity, collapses the scale into few blocks and therefore creates ties:
device 35 to 61 blocks and cloud 92 to 168 blocks across the folds, from about 16,800 training
instants. Ties can reorder values WITHIN a tier, so the isotonic reading does not inherit the
exactness of sanity check (a); that is visible in section 9.

---

## 3. SANITY CHECKS, with the exact numbers that had to match

### (a) always-cloud and device-only unchanged by calibration

What must match, and why: both arms deliver scores from ONE tier only, so a single per-tier
monotone map cannot reorder their values. Their challenge mAP must equal StudyE9c's committed
0.5675307471627266 and 0.4776042449177038, and their streaming AP must equal StudyE9b's committed
`device-only|measured@25|far5` and `always-cloud/32BI_N1|measured@25|cad50|far5` at every horizon.

| reading | device-only challenge | always-cloud challenge | diff vs committed | streaming AP max abs diff vs StudyE9b (device / cloud) | verdict |
|---|---|---|---|---|---|
| raw, no calibration (reproduction control) | 0.4776042449177038 | 0.5675307471627266 | 0.0 / 0.0 | 1.7e-18 / 6.9e-18 | PASS, exact |
| ONE per-tier Platt map, all 300 clips | 0.4776042449177038 | 0.5675307471627266 | 0.0 / 0.0 | 1.7e-18 / 6.9e-18 | **PASS, exact** |
| CROSS-FITTED, five per-fold maps (the pre-registered primary) | 0.4524929003089864 | 0.5629252475901950 | -0.0251113 / -0.0046055 | 0.0009 / 0.0029 | **FAIL as written** |

The committed streaming-AP values this reproduces exactly, for the record: device-only 0.012609464
/ 0.010432229 / 0.010234065 / 0.009205415 and always-cloud 0.038397437 / 0.016134323 / 0.012664104
/ 0.011025698 at h = 0 / 0.5 / 1.0 / 1.5 s.

**This is a STOP AND ASK.** The invariance the check asserts is a property of ONE monotone map per
tier, and it is confirmed to machine zero. It cannot hold for five maps, because both metrics rank
across clips and five affine maps with different slopes are five different monotone functions. The
consequence is not cosmetic: the gap the arms compete for is 0.1104 challenge mAP cross-fitted
against 0.0899 on one map, so the capture-fraction denominator moves by about 23 %. The study was
completed under both readings rather than stopped, because every arm at a given budget is scored on
the SAME scale and the same resamples, so the arm-versus-random comparisons the decision rule needs
remain internally paired. What the user has to decide is whether the primary reading should be the
pre-registered cross-fitted one or the one-common-scale one of section 8. A third option, and the
one this report would suggest, is to cross-fit the calibration for the DECISION the trigger makes
and score the delivered stream on one common map, which is leak-free for the decision and
artifact-free for the metric; that is a design change beyond the brief and is not done here.

### (b) the positives-only oracle must score at or above device-only on challenge mAP, THE GATE

| scale | oracle positives only | oracle every crop | device-only | always-cloud | margin over device-only | gate |
|---|---|---|---|---|---|---|
| raw, no calibration | 0.3910784585 | 0.5494724279 | 0.4776042449 | 0.5675307472 | **-0.0865258** | would FAIL |
| calibrated, cross-fitted (primary) | 0.5447489662 | 0.5418397813 | 0.4524929003 | 0.5629252476 | **+0.0922561** | **PASS** |
| calibrated, one common map | 0.5725405374 | 0.5488112537 | 0.4776042449 | 0.5675307472 | **+0.0949363** | **PASS** |

The raw row reproduces StudyCTRL1b's 0.3911 and 0.4776 exactly, which is both the cross-check of
check 1 and the mechanism-off control of Step 4. The gate is cleared on the primary and on the
alternative scale, so conclusions may proceed. Note the ordering also inverts as the mechanism
predicts: raw, the every-crop oracle beat the positives-only one by +0.158, because spending on
positives only was being punished by the offset; calibrated, the positives-only oracle is now the
HIGHER of the two (+0.0029 cross-fitted, +0.0237 on one map), which is what an oracle that spends
only where the label is should look like once the offset is gone.

### (c) calibration and tunables fitted on training folds only

| fold | train clips | held clips | overlap | clips the calibration was fitted on |
|---|---|---|---|---|
| 0 to 4 | 240 | 60 | **0** | **240** |

Asserted in code (`sanity`, `check_c_no_leakage`): the assertion fails the run if any fold's
overlap is non-zero or if any calibration was fitted on a number of clips other than its fold's
training count. No held-out clip enters any fit, calibration included.

### (d) the streaming-AP engine accepts calibrated scores without changing its definition

It does, and this is asserted rather than assumed: `ctrl1c_metrics.assert_matches_metrics_module`
compares the engine's point values against `metrics.streaming_ap` itself on the calibrated
device-only stream and requires agreement below 1e-12. Worst absolute difference **0.0**. The only
thing added to the committed definition is the average over horizons 0.5 / 1.0 / 1.5 s, and the
paired-resample draw that `ApEngine.full` already computes from one shared label-stratified clip
resample. So the second STOP AND ASK condition did not fire.

---

## 4. FIRST RUN, now a SENSITIVITY: arm x budget on the cross-fitted calibration

**This table is the FIRST RUN's cross-fitted reading. It is a labelled sensitivity. The FINAL PRIMARY main table is section 17.**

Capture fraction is (arm minus device-only) divided by (always-cloud minus device-only), with the
CI over the same 2,000 paired clip resamples (seed 0) as the arms themselves. All 300 clips, every
one held out, cross-fitted Platt calibration. "beats random" is the PRE-REGISTERED rule: the pooled
5-fold difference in captured fraction against random escalation, resample by resample, with a
bootstrap CI excluding 0. The LOAD column is DERIVED from the ENG1 step model (section 5), not
measured.

**Read the oracles' streaming-AP capture as a diagnostic, not as a fraction of a bound.** On the
challenge metric the oracle sits below always-cloud, as a timing bound should. On the STREAMING
metric it sits far above it (capture +1075 %), because the streaming AP scores each positive clip
at exactly the grid point nearest `event - h`, and the oracle places its calls so a cloud answer is
DELIVERED at those instants, while always-cloud samples on a 0.5-s cadence with a 0.395 s delivery
and so is reading a value captured up to 0.9 s earlier. The denominator is therefore not an upper
bound for a non-causal arm on this metric. It is still the right denominator for the causal arms,
which is what the decision rule compares, and it is the denominator the brief pre-registers.


### Budget 5 % of the call rate (DERIVED load: about 144 devices per H100)

streaming-AP gap 0.00377 (CI [+0.00183, +0.00683]), challenge-mAP gap 0.1104 (CI [+0.0527, +0.1660])

| arm | streaming AP | streaming capture % | CI % | beats random | challenge mAP | challenge capture % | CI % | beats random | call fraction | n episodes |
|---|---|---|---|---|---|---|---|---|---|---|
| device filter (spec 7.7) | 0.00948 | +7.4 | [-5.2, +48.0] | no | 0.4633 | +9.8 | [-3.2, +28.4] | no | 0.0487 | 380 |
| oracle trigger, positives only (NON-CAUSAL) NON-CAUSAL | 0.04974 | +1075.2 | [+610.1, +2006.0] | YES | 0.5447 | +83.5 | [+50.2, +145.0] | YES | 0.0508 | 150 |
| oracle timing bound, every crop (NON-CAUSAL) NON-CAUSAL | 0.02699 | +471.8 | [+255.5, +1042.8] | YES | 0.5418 | +80.9 | [+63.4, +94.5] | YES | 0.0508 | 300 |
| cloud trickle | 0.00917 | -0.9 | [-8.1, +0.4] | no | 0.4529 | +0.4 | [-6.5, +5.5] | no (random is better, CI excludes 0) | 0.0542 | 0 |
| context-modulated trickle | 0.00918 | -0.7 | [-3.7, +0.3] | no | 0.4521 | -0.4 | [-3.3, +1.5] | no (random is better, CI excludes 0) | 0.0113 | 0 |
| predictability ceiling, boosted trees (LEARNED) LEARNED CEILING | 0.00997 | +20.3 | [-5.2, +129.6] | no | 0.4771 | +22.3 | [-2.1, +46.4] | no | 0.0525 | 166 |
| predictability ceiling, logistic (LEARNED) LEARNED CEILING | 0.01007 | +23.1 | [+2.9, +132.0] | no | 0.4725 | +18.1 | [+0.2, +43.0] | no | 0.0541 | 188 |
| absolute-confidence trigger | 0.00937 | +4.4 | [-9.2, +25.1] | no | 0.4671 | +13.2 | [-5.2, +31.1] | no | 0.0530 | 290 |
| random escalation | 0.00966 | +12.1 | [-1.4, +78.9] | reference | 0.4721 | +17.7 | [+3.4, +39.6] | reference | 0.0543 | 482 |
| device-only (reference) | 0.00920 | 0.0 | - | - | 0.4525 | 0.0 | - | - | 0.0000 | 0 |
| always-cloud (reference) | 0.01297 | +100.0 | - | - | 0.5629 | +100.0 | - | - | 1.0000 | 0 |

### Budget 10 % of the call rate (DERIVED load: about 72 devices per H100)

streaming-AP gap 0.00377 (CI [+0.00183, +0.00683]), challenge-mAP gap 0.1104 (CI [+0.0527, +0.1660])

| arm | streaming AP | streaming capture % | CI % | beats random | challenge mAP | challenge capture % | CI % | beats random | call fraction | n episodes |
|---|---|---|---|---|---|---|---|---|---|---|
| device filter (spec 7.7) | 0.01026 | +28.0 | [+7.8, +123.2] | no | 0.4740 | +19.5 | [-5.0, +44.7] | no | 0.1031 | 436 |
| oracle trigger, positives only (NON-CAUSAL) NON-CAUSAL | 0.04974 | +1075.2 | [+610.1, +2006.0] | YES | 0.5447 | +83.5 | [+50.2, +145.0] | YES | 0.0997 | 150 |
| oracle timing bound, every crop (NON-CAUSAL) NON-CAUSAL | 0.01993 | +284.6 | [+177.8, +687.7] | YES | 0.5418 | +80.9 | [+63.4, +94.5] | YES | 0.1043 | 300 |
| cloud trickle | 0.01054 | +35.6 | [+15.4, +98.9] | no | 0.4780 | +23.1 | [+1.3, +45.1] | no | 0.0996 | 98 |
| context-modulated trickle | 0.01113 | +51.0 | [+17.8, +136.8] | no | 0.4870 | +31.3 | [+12.2, +58.4] | no | 0.1040 | 22 |
| predictability ceiling, boosted trees (LEARNED) LEARNED CEILING | 0.00979 | +15.6 | [-5.4, +87.4] | no | 0.4801 | +25.0 | [-0.7, +49.1] | no | 0.0992 | 322 |
| predictability ceiling, logistic (LEARNED) LEARNED CEILING | 0.00971 | +13.5 | [-5.2, +54.4] | no | 0.4692 | +15.2 | [-7.0, +36.4] | no | 0.1008 | 330 |
| absolute-confidence trigger | 0.00981 | +16.1 | [+3.2, +48.2] | no | 0.4716 | +17.3 | [-6.4, +39.8] | no | 0.0996 | 312 |
| random escalation | 0.01016 | +25.4 | [+0.5, +139.6] | reference | 0.4737 | +19.2 | [+2.9, +42.0] | reference | 0.1121 | 516 |
| device-only (reference) | 0.00920 | 0.0 | - | - | 0.4525 | 0.0 | - | - | 0.0000 | 0 |
| always-cloud (reference) | 0.01297 | +100.0 | - | - | 0.5629 | +100.0 | - | - | 1.0000 | 0 |

### Budget 20 % of the call rate (DERIVED load: about 36 devices per H100)

streaming-AP gap 0.00377 (CI [+0.00183, +0.00683]), challenge-mAP gap 0.1104 (CI [+0.0527, +0.1660])

| arm | streaming AP | streaming capture % | CI % | beats random | challenge mAP | challenge capture % | CI % | beats random | call fraction | n episodes |
|---|---|---|---|---|---|---|---|---|---|---|
| device filter (spec 7.7) | 0.01014 | +24.9 | [+6.3, +69.9] | no | 0.4762 | +21.5 | [-2.8, +44.5] | no | 0.2007 | 842 |
| oracle trigger, positives only (NON-CAUSAL) NON-CAUSAL | 0.04974 | +1075.2 | [+610.1, +2006.0] | YES | 0.5447 | +83.5 | [+50.2, +145.0] | YES | 0.1995 | 150 |
| oracle timing bound, every crop (NON-CAUSAL) NON-CAUSAL | 0.01906 | +261.5 | [+167.6, +628.7] | YES | 0.5418 | +80.9 | [+63.4, +94.5] | YES | 0.2022 | 300 |
| cloud trickle | 0.01086 | +44.0 | [+21.5, +94.7] | no | 0.4995 | +42.6 | [+20.1, +73.5] | no | 0.2038 | 271 |
| context-modulated trickle | 0.01114 | +51.4 | [+25.4, +107.4] | no | 0.4829 | +27.5 | [+3.9, +48.4] | no | 0.2104 | 156 |
| predictability ceiling, boosted trees (LEARNED) LEARNED CEILING | 0.01032 | +29.6 | [+6.6, +80.2] | no | 0.4935 | +37.1 | [+4.2, +63.9] | no | 0.1950 | 588 |
| predictability ceiling, logistic (LEARNED) LEARNED CEILING | 0.01014 | +24.9 | [-0.6, +66.9] | no | 0.4752 | +20.6 | [-17.3, +45.1] | no | 0.1945 | 581 |
| absolute-confidence trigger | 0.00994 | +19.5 | [-0.6, +43.0] | no | 0.4841 | +28.7 | [-2.6, +54.8] | no | 0.2005 | 645 |
| random escalation | 0.01013 | +24.6 | [+0.9, +92.6] | reference | 0.4826 | +27.3 | [+6.3, +53.8] | reference | 0.2063 | 900 |
| device-only (reference) | 0.00920 | 0.0 | - | - | 0.4525 | 0.0 | - | - | 0.0000 | 0 |
| always-cloud (reference) | 0.01297 | +100.0 | - | - | 0.5629 | +100.0 | - | - | 1.0000 | 0 |

### Budget 40 % of the call rate (DERIVED load: about 18 devices per H100)

streaming-AP gap 0.00377 (CI [+0.00183, +0.00683]), challenge-mAP gap 0.1104 (CI [+0.0527, +0.1660])

| arm | streaming AP | streaming capture % | CI % | beats random | challenge mAP | challenge capture % | CI % | beats random | call fraction | n episodes |
|---|---|---|---|---|---|---|---|---|---|---|
| device filter (spec 7.7) | 0.01142 | +58.9 | [+30.1, +145.7] | no | 0.5134 | +55.1 | [+30.3, +86.6] | no | 0.4010 | 1248 |
| oracle trigger, positives only (NON-CAUSAL) NON-CAUSAL | 0.04974 | +1075.2 | [+610.1, +2006.0] | YES | 0.5447 | +83.5 | [+50.2, +145.0] | no | 0.2246 | 150 |
| oracle timing bound, every crop (NON-CAUSAL) NON-CAUSAL | 0.01601 | +180.6 | [+122.8, +333.1] | YES | 0.5418 | +80.9 | [+63.4, +94.5] | no | 0.3996 | 300 |
| cloud trickle | 0.01047 | +33.6 | [+10.9, +69.8] | no | 0.5015 | +44.3 | [+19.7, +71.1] | no | 0.4031 | 775 |
| context-modulated trickle | 0.01130 | +55.7 | [+31.2, +97.6] | no | 0.4989 | +42.0 | [+15.2, +65.9] | no | 0.3907 | 564 |
| predictability ceiling, boosted trees (LEARNED) LEARNED CEILING | 0.01070 | +39.7 | [+13.7, +72.3] | no | 0.5023 | +45.1 | [+10.8, +72.9] | no | 0.3707 | 1004 |
| predictability ceiling, logistic (LEARNED) LEARNED CEILING | 0.01061 | +37.4 | [+11.9, +70.2] | no | 0.4965 | +39.8 | [+2.4, +66.2] | no | 0.3971 | 1098 |
| absolute-confidence trigger | 0.01088 | +44.6 | [+21.2, +74.2] | no | 0.5027 | +45.5 | [+15.1, +70.9] | no | 0.4044 | 1030 |
| random escalation | 0.01149 | +60.7 | [+36.4, +113.3] | reference | 0.5241 | +64.8 | [+39.1, +111.3] | reference | 0.4056 | 1422 |
| device-only (reference) | 0.00920 | 0.0 | - | - | 0.4525 | 0.0 | - | - | 0.0000 | 0 |
| always-cloud (reference) | 0.01297 | +100.0 | - | - | 0.5629 | +100.0 | - | - | 1.0000 | 0 |
### 4.1 What the table says, read off the intervals

Arms whose capture-fraction interval EXCLUDES ZERO on the primary metric, which is the only
statement the design supports about a single arm:

* `oracle-trigger` and `oracle-timing-bound` at 5, 10, 20 and 40 % (both NON-CAUSAL)
* `escalation-only` (the device filter) at 10, 20 and 40 %
* `cloud-initiated` at 10, 20 and 40 %
* `context-trickle` at 10, 20 and 40 %
* `ceiling-gbt` at 20 and 40 %, `ceiling-logistic` at 5 and 40 %
* `absolute-confidence` at 10 and 40 %
* `random-escalation` at 10, 20 and 40 %

**Arms that beat RANDOM at the same budget on the primary metric: none, at any budget, except the
two non-causal oracles.** The pre-registered difference in captured fraction, in capture-fraction
points, with its paired CI:

| budget | arm | difference against random (streaming capture) | CI | excludes 0 | difference (challenge mAP) | CI | excludes 0 |
|---|---|---|---|---|---|---|---|
| 5 % | device filter | -4.7 | [-59.6, +26.5] | no | -0.0088 | [-0.0291, +0.0135] | no |
| 5 % | cloud trickle | -13.0 | [-84.3, +0.0] | no | -0.0192 | [-0.0370, -0.0015] | yes, RANDOM IS BETTER |
| 5 % | context trickle | -12.8 | [-80.8, +0.6] | no | -0.0200 | [-0.0368, -0.0028] | yes, RANDOM IS BETTER |
| 5 % | ceiling gbt | +8.2 | [-51.0, +104.7] | no | +0.0050 | [-0.0233, +0.0332] | no |
| 5 % | ceiling logistic | +11.0 | [-54.5, +110.1] | no | +0.0005 | [-0.0243, +0.0271] | no |
| 5 % | absolute confidence | -7.7 | [-79.3, +18.8] | no | -0.0049 | [-0.0269, +0.0154] | no |
| 10 % | device filter | +2.6 | [-95.5, +91.8] | no | +0.0003 | [-0.0299, +0.0324] | no |
| 10 % | cloud trickle | +10.2 | [-104.6, +77.0] | no | +0.0043 | [-0.0233, +0.0300] | no |
| 10 % | context trickle | +25.7 | [-91.8, +112.3] | no | +0.0133 | [-0.0142, +0.0404] | no |
| 10 % | ceiling gbt | -9.8 | [-127.7, +62.0] | no | +0.0064 | [-0.0252, +0.0403] | no |
| 10 % | ceiling logistic | -11.9 | [-131.2, +34.5] | no | -0.0045 | [-0.0338, +0.0256] | no |
| 10 % | absolute confidence | -9.3 | [-123.2, +31.2] | no | -0.0021 | [-0.0307, +0.0265] | no |
| 20 % | device filter | +0.3 | [-52.1, +36.6] | no | -0.0064 | [-0.0353, +0.0233] | no |
| 20 % | cloud trickle | +19.4 | [-41.2, +71.2] | no | +0.0169 | [-0.0138, +0.0475] | no |
| 20 % | context trickle | +26.8 | [-33.2, +86.4] | no | +0.0003 | [-0.0306, +0.0286] | no |
| 20 % | ceiling gbt | +5.0 | [-62.1, +57.4] | no | +0.0109 | [-0.0250, +0.0519] | no |
| 20 % | ceiling logistic | +0.3 | [-71.7, +46.3] | no | -0.0074 | [-0.0411, +0.0292] | no |
| 20 % | absolute confidence | -5.1 | [-68.4, +22.2] | no | +0.0015 | [-0.0295, +0.0329] | no |
| 40 % | device filter | -1.8 | [-42.9, +63.7] | no | -0.0107 | [-0.0505, +0.0315] | no |
| 40 % | cloud trickle | -27.2 | [-77.5, +4.6] | no | -0.0226 | [-0.0570, +0.0126] | no |
| 40 % | context trickle | -5.0 | [-52.0, +30.5] | no | -0.0252 | [-0.0600, +0.0114] | no |
| 40 % | ceiling gbt | -21.1 | [-78.8, +15.7] | no | -0.0218 | [-0.0601, +0.0208] | no |
| 40 % | ceiling logistic | -23.3 | [-80.7, +11.8] | no | -0.0276 | [-0.0645, +0.0140] | no |
| 40 % | absolute confidence | -16.2 | [-78.6, +20.8] | no | -0.0214 | [-0.0616, +0.0191] | no |
| 5 to 40 % | oracle trigger (NON-CAUSAL) | +1015 to +1063 | all exclude 0 | yes | +0.021 to +0.073 | excludes 0 at 5, 10, 20 % | yes except 40 % |
| 5 to 40 % | oracle timing bound (NON-CAUSAL) | +120 to +460 | all exclude 0 | yes | +0.018 to +0.070 | excludes 0 at 5, 10, 20 % | yes except 40 % |

The largest causal point estimate at a budget at or below 20 % is the context-modulated trickle at
20 % (+26.8 capture-fraction points over random, CI -33.2 to +86.4) and at 10 % (+25.7, CI -91.8 to
+112.3). At 10 % four of its five folds have a DEGENERATE trigger (section 7), so even that point
estimate is mostly its background cadence and not its trigger.

### 4.2 Episodes, at the 20 % budget

Distributions, not medians alone, because consistency check 3 requires the spread:

| arm | escalations per device-minute | episode length s p50 (p25, p75, min, max) | calls per episode p50 | false episodes per minute on negatives |
|---|---|---|---|---|
| device filter | 4.81 | 2.25 (1.75, 3.75, 0.25, 5.25) | 4.0 | 4.98 |
| absolute confidence | 3.68 | 3.75 (2.25, 5.25, 0.25, 5.25) | 7.0 | 3.37 |
| random escalation | 5.14 | 2.25 (1.75, 3.75, 0.25, 3.75) | 4.0 | 4.85 |
| oracle trigger | 0.86 | 14.75 (14.25, 15.25, 5.75, 15.75) | 29.0 | 0.00 |
| oracle timing bound | 1.71 | 7.75 (7.25, 7.75, 1.75, 7.75) | 15.0 | 1.76 |
| cloud trickle | 1.55 | 3.75 (2.25, 5.25, 0.25, 5.25) | 7.0 | 0.97 |
| context trickle | 0.89 | 4.25 (2.63, 5.25, 0.50, 5.25) | 8.5 | 0.62 |
| ceiling gbt | 3.36 | 3.75 (2.75, 5.25, 0.25, 5.25) | 7.0 | 2.74 |
| ceiling logistic | 3.32 | 3.75 (2.25, 5.25, 0.25, 5.25) | 7.0 | 3.20 |

The device filter's false-episode rate on negatives (4.98 per minute) still tracks its escalation
rate (4.81) almost exactly, which is StudyCTRL1's cleanest statement of the same thing: it fires at
a rate rather than at the right moments. Calibration did not change that.

### 4.3 Per-horizon streaming AP, and h = 0

Reported because the brief asks for each horizon as well as the primary average. At the 5 % budget:

| arm | h = 0 | h = 0.5 | h = 1.0 | h = 1.5 | primary mean |
|---|---|---|---|---|---|
| device-only | 0.01167 | 0.00955 | 0.00939 | 0.00866 | 0.00920 |
| always-cloud | 0.03545 | 0.01571 | 0.01225 | 0.01096 | 0.01297 |
| device filter | 0.01857 | 0.01002 | 0.00959 | 0.00884 | 0.00948 |
| oracle trigger | 0.02780 | 0.07213 | 0.05685 | 0.02024 | 0.04974 |
| oracle timing bound | 0.01527 | 0.03750 | 0.03278 | 0.01069 | 0.02699 |
| cloud trickle | 0.01155 | 0.00952 | 0.00932 | 0.00865 | 0.00917 |
| context trickle | 0.01164 | 0.00954 | 0.00937 | 0.00862 | 0.00918 |
| ceiling gbt | 0.01953 | 0.01067 | 0.01069 | 0.00855 | 0.00997 |
| ceiling logistic | 0.01958 | 0.01138 | 0.00973 | 0.00910 | 0.01007 |
| absolute confidence | 0.01247 | 0.01002 | 0.00939 | 0.00869 | 0.00937 |
| random escalation | 0.01437 | 0.01062 | 0.00956 | 0.00879 | 0.00966 |

h = 0 is the horizon the committed StudyE9b capture was quoted at and it behaves differently from
the primary average: at 5 % the device filter is +0.0069 above device-only at h = 0 but only
+0.0003 on the primary. Every horizon of every arm and budget is in
`results/dashcam/ctrl1c/ctrl1c_pooled_platt.json` under `streaming_ap_by_horizon`.

### 4.4 Per-fold spread of the primary metric

At the 20 % budget, the five held-out folds (consistency check 3: a pooled number over folds of
very different difficulty should not be read as if the folds agreed):

| fold | device-only | always-cloud | device filter | cloud trickle | random |
|---|---|---|---|---|---|
| 0 | 0.00621 | 0.01212 | 0.00818 | 0.00869 | 0.00747 |
| 1 | 0.02236 | 0.03314 | 0.03312 | 0.04593 | 0.03300 |
| 2 | 0.00941 | 0.01279 | 0.00941 | 0.00953 | 0.00904 |
| 3 | 0.00993 | 0.01096 | 0.01220 | 0.01224 | 0.01369 |
| 4 | 0.01898 | 0.02779 | 0.01845 | 0.03250 | 0.02054 |

Fold 1's device-only streaming AP is 3.6 times fold 0's. The folds are label-balanced by
construction but not difficulty-balanced, which is why the pooled CI is as wide as it is and why no
single-fold ordering should be quoted.

---

## 5. The load column: what each budget means as cloud capacity

**DERIVED from the committed ENG1 step model, NOT measured in this row.** Source
`results/cost/study_eng1/eng1_step_model.json` (piecewise-linear, R^2 0.985, n 5,974, fitted on
Part A and Part B E0 steps; Part C and the HOLDOUT were not used in the fit).

One escalation call is one N1 Nexar request of **378 prompt tokens** (StudyD3 / D4 / D14
`PROMPT_TOK[1]`) with one image. Evaluating the step model at tok = 378, images_in_step = 1,
prefill_reqs = 1, decode_reqs = 0, ctx = tok gives **69.47 ms** of accelerator step time per call,
and the measured multimodal admission stall adds **13.89 ms** (12.74 ms + 1.15 ms per image). A
device at budget B on the 0.5-s decision cadence issues B / 0.5 calls per second.

| budget | calls/s per device | devices per H100 (step only) | devices per H100 (with the admission stall) | in-flight requests at 0.395 s |
|---|---|---|---|---|
| 5 % | 0.10 | 143.96 | 119.97 | 0.040 |
| 10 % | 0.20 | 71.98 | 59.98 | 0.079 |
| 20 % | 0.40 | 35.99 | 29.99 | 0.158 |
| 40 % | 0.80 | 17.99 | 15.00 | 0.316 |

Every assumption, stated:

1. the call is a single prefill request in its own step, 378 tokens, one image;
2. the step model is read in its ISOLATED-call form though it was fitted on BUSY intervals. ENG1
   measured the engine to be SUB-LINEAR in batched small prefills (16-batch / 16 x single = 0.51 at
   N = 1), so a batched fleet would fit MORE devices than this column states and the column is a
   lower bound in that respect;
3. the device count is a pure throughput bound at 100 % accelerator utilization. Queueing is
   ignored, so the committed 0.395 s cloud latency is NOT guaranteed at the stated count; the
   in-flight column is Little's law at that arrival rate and is what the latency budget would have
   to accommodate;
4. the admission-stall column charges every call the full stall as if no two calls shared a step,
   which is the pessimistic end;
5. every device runs the same workload at the same budget with uncorrelated escalation times;
   correlated bursts reduce the count;
6. the step model is the H100 NVL's (sn4622120321) and no other tier.

**Read as load:** the 5 to 20 % cells are a shared H100 serving roughly 144 down to 36 devices, and
the 40 % cell is 18. The budget axis is a fleet-size axis.

---

## 6. Mechanism verification, Steps 1 to 5

Recorded on TRAINING folds only and BEFORE any pooled number was written; the pooling stage refuses
to run without `ctrl1c_mechanism_platt.json` on disk. StudyCTRL1b's own Steps 1 to 5 for the arms
themselves were re-run UNCHANGED on the calibrated scale and are attached in the same file under
`ctrl1b_protocol`, so the arms' links are verified in this row rather than inherited.

### Step 1, the causal chain

If the two tiers' raw scores are on different scales (StudyCTRL1b measured a median -5.125 log-unit
offset), then a rank metric over a MIXED stream is partly reading tier identity rather than
evidence, so an arm whose calls are label-correlated is rewarded or punished by the offset alone; a
PER-TIER calibration maps each tier's score to the same quantity, the probability that the clip
contains the event, which is spec 4.1 as the v3.1 addendum reads it (u_SH must be a CALIBRATED
utility and never a raw tier score); with the offset removed, the measured ordering of the trigger
families is a statement about WHEN each trigger spends and not about WHICH TIER it spends on, and
the positives-only oracle, which spends only where the label is, must stop scoring below
device-only. In parallel, because the challenge mAP reads one crop per clip, the primary metric
moves to StudyE9b's STREAMING AP over all decision instants, so a trigger that improves the
displayed score away from that one crop is now credited for it; and because the cheapest
pre-registered background cadence cost more than the 5 % and 10 % budgets, extending the cadence
grid is what makes the cloud-initiated family TESTABLE at those budgets at all.

### Step 2, the links

| causal link | implementing quantity | value / range in this run | varies as expected? | evidence |
|---|---|---|---|---|
| C1: per-tier calibration removes the tiers' scale offset | median (cloud minus device) over all training instants, and at the crop instants of training positives | all instants: **-5.1250 raw, -0.0639 calibrated** (80x smaller). At crops: p50 **-3.2500 raw with the cloud higher in 24.1 % of cases**, against p50 **+0.0951 calibrated with the cloud higher in 58.4 %** (n = 257) | YES | the quantity the calibration exists to remove is large before it and near zero after it; had it been zero before, the calibration could not have mattered |
| C1: the offset drives the positives-only oracle's sign | training-fold challenge mAP of the positives-only oracle against device-only | raw **0.4042 against 0.4951** (below); calibrated cross-fitted **0.5826 against 0.4867** (above); one map **0.5967 against 0.4951** (above) | YES | this is the artifact D57 named, and the Step 4 control that disables the calibration brings it back |
| C2: episodes change the delivered score and the STREAMING AP moves | training-fold streaming AP of the device filter by budget against the two references | 0.013139 / 0.013899 / 0.013930 / 0.015403 at 5 / 10 / 20 / 40 %, device-only **0.011750**, always-cloud **0.014528**; spread **0.002264**, gap **0.002778** | YES | the primary metric moves with the budget and its denominator is non-zero; a constant primary or a zero gap would make every capture fraction undefined |
| C3: the extended cadence grid makes the cloud trickle feasible | the budget each cadence costs before any episode, and feasible cadences per budget in the new grid against StudyCTRL1b's | floors 0.5000 / 0.2500 / 0.1250 / 0.1000 / 0.0833 / 0.0625 / 0.0500 at 1 / 2 / 4 / 5 / 6 / 8 / 10 s. Feasible cadences, new grid against old: **1 against 0** at 5 %, **4 against 0** at 10 %, 5 against 1 at 20 %, 6 against 2 at 40 % | YES, with one cell marked | the extension adds feasible cadences at both budgets StudyCTRL1b could not measure. **At 5 % the only feasible cadence is 10 s, whose floor 0.0500 EQUALS the budget, so the episode headroom is exactly 0.0000 and the trigger cannot fire: that cell is marked `trigger_degenerate` in all 5 folds and is NOT reported as a measured arm** |
| C4: the calibrated signed gain is a non-degenerate learning target | the target's distribution and the fitted model's prediction spread, fold 0 | calibrated target mean +0.0306, sd **0.4126**, 52.9 % positive (raw: mean +0.2734, sd 6.5178, 52.0 % positive); prediction sd **0.0324**, GBT training r2 **0.0116** | YES | the retargeted objective is non-degenerate and the prediction varies across instants; a flat prediction would make the ceiling identical to random |

No link under C1 to C4 is ABSENT or CONSTANT, so the sweep was allowed to run. **Two arm-level
cells ARE degenerate and are declared rather than reported:** the cloud trickle at 5 % (zero
episode headroom, all 5 folds) and the context-modulated trickle at 5 % (INFEASIBLE in 4 folds,
degenerate in the 5th) and at 10 % (degenerate in 4 of 5 folds). Under CLAUDE.md those cells have
not tested the trigger and their rows are INCONCLUSIVE BY DESIGN, not measurements of a trigger.

### Step 3, one traced unit

`results/dashcam/ctrl1c/ctrl1c_mechanism_platt.json`, `step3_trace`, carries one clip's traced
decision instant and episode at the 10 % budget with every quantity a person can check by hand: the
calibrated log-odds of each device sample in the window with its capture and readable times, the
window median and IQR, z, theta and K_c, the episode's open index, every call time and delivery
time, the calibrated cloud score at each call, the calls charged and the clip's own decision
instants with the resulting call fraction, and the displayed calibrated score at each challenge
crop with a flag for whether the cloud upgraded it. The arithmetic is stated in the record.

### Step 4, the negative controls

**(i) calibration disabled** (the mechanism-off condition for C1, every episode and every budget
held fixed). Training folds of fold 0:

| scale | positives-only oracle | device-only | verdict |
|---|---|---|---|
| raw | 0.4042 | 0.4951 | BELOW, the artifact is present |
| calibrated, cross-fitted | 0.5826 | 0.4867 | ABOVE |
| calibrated, one map | 0.5967 | 0.4951 | ABOVE |

The result DOES change when the mechanism is disabled, so the calibration is what is driving it.

**(ii) the cloud's score replaced by the device's own**, call pattern unchanged, so an escalation
buys the cloud PATH and nothing else. On the primary metric, training folds of fold 0:

| budget | device filter | device scores through the cloud path | device-only | from path freshness | from cloud score quality |
|---|---|---|---|---|---|
| 5 % | 0.01314 | 0.01203 | 0.01175 | +0.00028 (20 %) | +0.00111 (80 %) |
| 10 % | 0.01390 | 0.01195 | 0.01175 | +0.00020 (9 %) | +0.00195 (91 %) |
| 20 % | 0.01393 | 0.01204 | 0.01175 | +0.00029 (13 %) | +0.00189 (87 %) |
| 40 % | 0.01540 | 0.01228 | 0.01175 | +0.00053 (15 %) | +0.00312 (85 %) |

The control does not collapse to the null and is reported as a decomposition, as in StudyCTRL1 and
StudyCTRL1b. On the calibrated primary metric the split is 9 to 20 % path freshness and 80 to 91 %
cloud score quality, against StudyCTRL1b's 30 to 45 / 55 to 70 on the raw challenge metric: once
the tiers are on one scale, more of what an escalation buys is attributable to the cloud's answer
and less to the fresher path.

**(iii) affine invariance of the device filter**, the control that separates "the calibration
changed the scale" from "the calibration changed the controller". Platt is affine with a > 0 and
every spec 7.7 signal is divided by the window IQR, so under the fitted theta the episodes must be
identical on the raw and the calibrated arrays. **They are, at all four budgets, bit-identical in
open indices and call indices.** So the device filter in this row is StudyCTRL1b's controller
exactly, and the table is a comparison of the metric and the scale, not of a different controller.

**(iv) the permuted-target control for the learned ceiling** is re-run unchanged from StudyCTRL1b
and recorded in `ctrl1b_protocol.learned_arms.step4_controls.permuted_target`.

### Step 5, the alternative explanations

The headline could be produced by (a) the calibration removing the tier offset so that the metric
reads evidence rather than tier identity, which is the claimed mechanism; or (b) the calibration
merely compressing the score range so that values crowd together and the rank metric is driven by
ties; or (c) the change of primary metric alone, since the streaming AP reads every instant and the
challenge mAP one crop per clip, so the two could reorder the arms with no calibration at all. (b)
is excluded by control (iii): an affine map with a > 0 creates no ties and leaves every single-tier
arm's AP bit-identical, which is measured to 0.0, and the isotonic sensitivity is reported
separately precisely because it DOES create ties. (c) is separated by reporting both metrics on the
SAME arms in one table, so the metric change and the calibration change are never one number. A
fourth explanation cannot be separated within this design and is the reason for the sanity-check
stop: because the calibration is CROSS-FITTED, five folds carry five different affine maps and a
cross-clip rank metric also sees fold identity. Section 8 measures that by re-scoring the identical
episodes on one common map.

---

## 7. FIRST RUN: the cloud-initiated arm, feasibility with the new cadences

**The cadence feasibility is a property of the budget metric and is unchanged under the final primary; the per-fold choices and episode counts under the final primary are in section 17 and 21.**

StudyCTRL1b could not measure this arm at 5 % or 10 % at all, because its cheapest cadence (4 s)
costs 0.1250 of the decision instants. With the extended grid:

| budget | cadence | background floor | feasible | chosen by n folds | trigger degenerate in the chosen cell |
|---|---|---|---|---|---|
| 5 % | 1 / 2 / 4 / 5 / 6 / 8 s | 0.5000 / 0.2500 / 0.1250 / 0.1000 / 0.0833 / 0.0625 | NO | 0 | - |
| 5 % | **10 s** | **0.0500** | yes | **5 of 5** | **YES in 5 of 5 (headroom exactly 0.0000)** |
| 10 % | 1 / 2 / 4 s | 0.5000 / 0.2500 / 0.1250 | NO | 0 | - |
| 10 % | 5 s | 0.1000 | yes | 0 | - |
| 10 % | 6 s | 0.0833 | yes | 0 | - |
| 10 % | **8 s** | **0.0625** | yes | **5 of 5** | **no, headroom 0.0375** |
| 10 % | 10 s | 0.0500 | yes | 0 | - |
| 20 % | 1 / 2 s | 0.5000 / 0.2500 | NO | 0 | - |
| 20 % | 4 s | 0.1250 | yes | 4 of 5 | no |
| 20 % | 8 s | 0.0625 | yes | 1 of 5 | no |
| 20 % | 5 / 6 / 10 s | 0.1000 / 0.0833 / 0.0500 | yes | 0 | - |
| 40 % | 1 s | 0.5000 | NO | 0 | - |
| 40 % | 4 s | 0.1250 | yes | 3 of 5 | no |
| 40 % | 6 s | 0.0833 | yes | 1 of 5 | no |
| 40 % | 8 s | 0.0625 | yes | 1 of 5 | no |
| 40 % | 2 / 5 / 10 s | 0.2500 / 0.1000 / 0.0500 | yes | 0 | - |

**Answer to the brief's question.** The arm is now FEASIBLE at 10 % with a live trigger, in all five
folds, at an 8-s background cadence. **At 5 % it is feasible only in a degenerate sense:** the only
cadence that fits, 10 s, costs exactly 0.0500 of the decision instants, which IS the budget, so
after the budget is spent on background sampling there is nothing left for an episode and the
threshold search drives the trigger to never fire (0 episodes over 300 clips in all 5 folds). Its
5 % row in section 4 is therefore the BACKGROUND CADENCE ALONE, with the trigger absent, and under
CLAUDE.md that cell has not tested the cloud-initiated trigger: it is INCONCLUSIVE by design. What
it does establish is that a 10-s cloud-side poll with no trigger at all is worth -0.9 % of the gap
(CI -8.1 to +0.4), that is nothing, and is measurably worse than spending the same budget at random
on the secondary metric.

**The context-modulated trickle inherits the same floor and is worse off**, because halving the
cadence on the modulated clips raises its mean floor:

| budget | fold 0 | fold 1 | fold 2 | fold 3 | fold 4 |
|---|---|---|---|---|---|
| 5 % | c = 10 s, 0 episodes, DEGENERATE | INFEASIBLE | INFEASIBLE | INFEASIBLE | INFEASIBLE |
| 10 % | c = 8 s, 65 episodes | c = 8 s, 0 ep, DEGENERATE | c = 8 s, 0 ep, DEGENERATE | c = 10 s, 0 ep, DEGENERATE | c = 8 s, 0 ep, DEGENERATE |
| 20 % | c = 8 s, 321 episodes | c = 4 s, 0 ep, DEGENERATE | c = 4 s, 0 ep, DEGENERATE | c = 8 s, 188 ep | c = 4 s, 7 ep |
| 40 % | c = 4 s, 592 ep | c = 5 s, 675 ep | c = 2 s, 22 ep | c = 8 s, 594 ep | c = 4 s, 508 ep |

So the context-modulated trickle is INCONCLUSIVE by design at 5 % (no live trigger in any fold) and
at 10 % (a live trigger in 1 fold of 5), partly exercised at 20 % (3 of 5) and properly exercised
only at 40 %. Its 20 % point estimate, the largest causal estimate in the table, rests on three
folds' triggers and two folds' background cadence, and that is the honest reading of it.

**The 0.5-s decision cadence is the binding constraint here, not the trigger design.** A cloud-side
poll must cost `call_cadence / background_cadence` of the decision instants, so a 5 % budget admits
no poll faster than 10 s and leaves no room for the episode the poll exists to open. If the cloud
trickle is to be testable at a 5 % budget, the pre-registered budget metric has to stop charging a
background sample and an episode call the same, or the decision cadence has to change. Both are
methodological changes beyond this brief and neither is made here.

---

## 8. FIRST RUN, now a SENSITIVITY: the same episodes re-scored on ONE common scale

**Superseded by section 17: under the final primary there is only one scale, so this re-scoring is no longer needed.**

This isolates the cross-fold scale heterogeneity that sanity check (a) exposed. The episodes are
the IDENTICAL cross-fitted ones, so no decision changed; only the map used to score the delivered
stream changed, from five per-fold maps to the single all-300 Platt map. That map is fitted with
all 300 clips' labels, which is a two-parameter-per-tier leak that touches no decision, only the
units of the delivered score; it is reported for that reason and is not the primary.


### Budget 5 %

| arm | streaming AP | streaming capture % | challenge mAP | challenge capture % | beats random (streaming) |
|---|---|---|---|---|---|
| device-only | 0.00996 | n/a | 0.4776 | n/a | - |
| always-cloud | 0.01327 | n/a | 0.5675 | n/a | - |
| escalation-only | 0.01023 | +8.2 | 0.4912 | +15.1 | False |
| oracle-trigger | 0.12276 | +3400.3 | 0.5725 | +105.6 | True |
| oracle-timing-bound | 0.04139 | +947.5 | 0.5488 | +79.2 | True |
| cloud-initiated | 0.00983 | -3.8 | 0.4779 | +0.3 | CI excludes 0 but NEGATIVE: random is better |
| context-trickle | 0.00990 | -1.8 | 0.4772 | -0.4 | False |
| ceiling-gbt | 0.01031 | +10.5 | 0.4955 | +19.9 | False |
| ceiling-logistic | 0.01105 | +33.1 | 0.4927 | +16.8 | False |
| absolute-confidence | 0.01111 | +34.6 | 0.4843 | +7.4 | False |
| random-escalation | 0.01035 | +11.8 | 0.4997 | +24.6 | - |

### Budget 10 %

| arm | streaming AP | streaming capture % | challenge mAP | challenge capture % | beats random (streaming) |
|---|---|---|---|---|---|
| device-only | 0.00996 | n/a | 0.4776 | n/a | - |
| always-cloud | 0.01327 | n/a | 0.5675 | n/a | - |
| escalation-only | 0.01109 | +34.1 | 0.4990 | +23.8 | False |
| oracle-trigger | 0.12276 | +3400.3 | 0.5725 | +105.6 | True |
| oracle-timing-bound | 0.03146 | +648.1 | 0.5488 | +79.2 | True |
| cloud-initiated | 0.01427 | +130.1 | 0.4913 | +15.2 | False |
| context-trickle | 0.01334 | +102.0 | 0.5040 | +29.4 | False |
| ceiling-gbt | 0.01026 | +9.1 | 0.4979 | +22.5 | False |
| ceiling-logistic | 0.01051 | +16.6 | 0.4867 | +10.1 | False |
| absolute-confidence | 0.01117 | +36.5 | 0.4846 | +7.8 | False |
| random-escalation | 0.01080 | +25.5 | 0.5012 | +26.3 | - |

### Budget 20 %

| arm | streaming AP | streaming capture % | challenge mAP | challenge capture % | beats random (streaming) |
|---|---|---|---|---|---|
| device-only | 0.00996 | n/a | 0.4776 | n/a | - |
| always-cloud | 0.01327 | n/a | 0.5675 | n/a | - |
| escalation-only | 0.01146 | +45.2 | 0.4952 | +19.6 | False |
| oracle-trigger | 0.12276 | +3400.3 | 0.5725 | +105.6 | True |
| oracle-timing-bound | 0.02678 | +507.1 | 0.5488 | +79.2 | True |
| cloud-initiated | 0.01196 | +60.4 | 0.5123 | +38.6 | False |
| context-trickle | 0.01233 | +71.6 | 0.4906 | +14.5 | False |
| ceiling-gbt | 0.01096 | +30.2 | 0.5063 | +32.0 | False |
| ceiling-logistic | 0.01094 | +29.6 | 0.4923 | +16.3 | False |
| absolute-confidence | 0.01060 | +19.2 | 0.4931 | +17.2 | False |
| random-escalation | 0.01141 | +43.8 | 0.5099 | +35.9 | - |

### Budget 40 %

| arm | streaming AP | streaming capture % | challenge mAP | challenge capture % | beats random (streaming) |
|---|---|---|---|---|---|
| device-only | 0.00996 | n/a | 0.4776 | n/a | - |
| always-cloud | 0.01327 | n/a | 0.5675 | n/a | - |
| escalation-only | 0.01188 | +58.0 | 0.5294 | +57.6 | False |
| oracle-trigger | 0.12276 | +3400.3 | 0.5725 | +105.6 | True |
| oracle-timing-bound | 0.01976 | +295.6 | 0.5488 | +79.2 | True |
| cloud-initiated | 0.01082 | +25.9 | 0.5088 | +34.7 | CI excludes 0 but NEGATIVE: random is better |
| context-trickle | 0.01204 | +62.9 | 0.5120 | +38.2 | False |
| ceiling-gbt | 0.01156 | +48.2 | 0.5159 | +42.5 | False |
| ceiling-logistic | 0.01133 | +41.3 | 0.5116 | +37.8 | False |
| absolute-confidence | 0.01151 | +46.9 | 0.5137 | +40.1 | False |
| random-escalation | 0.01226 | +69.5 | 0.5437 | +73.5 | - |

**What this reading changes and what it does not.** The references return to the committed values
exactly (device-only 0.4776, always-cloud 0.5675 on the challenge metric; 0.00996 and 0.01327 on
the primary). Every capture fraction moves, in both directions, by up to about 30 points. The
positives-only oracle now exceeds always-cloud on the challenge metric (0.5725 against 0.5675,
capture +105.6 %), which is what a perfectly timed arm should do once the offset is gone and is a
sharper statement of the gate than the cross-fitted row gives. And **the verdict on Q11 does not
change**: no causal arm beats random in the positive direction at any budget here either. The two
cells where a causal arm's difference against random excludes zero are the cloud trickle at 5 % and
at 40 %, and in both the sign is NEGATIVE, that is random is the better arm.

---

## 9. FIRST RUN: sensitivity to the two alternative calibrations

Both were fitted and run end to end, with every tunable re-fitted on the calibrated scale, exactly
as the primary was. **The primary decides; these are reported in full because the brief asks for
all three.**

References first, because they move:

| calibration | device-only challenge | always-cloud challenge | device-only streaming | always-cloud streaming | streaming gap |
|---|---|---|---|---|---|
| Platt, clip label (PRIMARY) | 0.452493 | 0.562925 | 0.009202 | 0.012972 | 0.003770 |
| isotonic, clip label | 0.430139 | 0.559399 | 0.009476 | 0.012890 | 0.003415 |
| Platt, instant label | 0.468734 | 0.566684 | 0.009620 | 0.012871 | 0.003251 |

Isotonic moves the device-only reference furthest (-0.0475 against the committed value), as
expected: it has 35 to 61 blocks per fold on the device tier, so it ties together large groups of
distinct raw scores and those ties DO reorder values within a tier.

Streaming-AP capture, with CI and the beats-random verdict, all three side by side:


| budget | arm | platt (primary) | isotonic | platt instant-label |
|---|---|---|---|---|
| 5 % | escalation-only | +7.4 [-5.2, +48.0] no | -3.5 [-204.7, +177.7] no | +17.6 [-14.0, +188.1] no |
| 5 % | oracle-trigger | +1075.2 [+610.1, +2006.0] YES | +857.9 [-2669.1, +6691.5] no | +544.4 [+228.1, +1343.1] YES |
| 5 % | oracle-timing-bound | +471.8 [+255.5, +1042.8] YES | +522.3 [-1038.7, +3095.3] no | +164.2 [+67.7, +785.6] YES |
| 5 % | cloud-initiated | -0.9 [-8.1, +0.4] no | -11.7 [-278.7, +201.4] no | +0.3 [-7.7, +2.0] no |
| 5 % | context-trickle | -0.7 [-3.7, +0.3] no | -5.2 [-155.7, +120.6] no | -0.5 [-4.9, +0.7] no |
| 5 % | ceiling-gbt | +20.3 [-5.2, +129.6] no | -5.8 [-270.2, +207.6] no | +3.5 [-14.2, +26.1] no |
| 5 % | ceiling-logistic | +23.1 [+2.9, +132.0] no | -9.2 [-269.4, +205.8] no | -1.9 [-26.2, +9.4] no |
| 5 % | absolute-confidence | +4.4 [-9.2, +25.1] no | -5.5 [-193.8, +131.9] no | +5.4 [-8.1, +27.1] no |
| 5 % | random-escalation | +12.1 [-1.4, +78.9] - | +8.3 [-149.7, +139.6] - | +1.7 [-9.2, +9.6] - |
| 10 % | escalation-only | +28.0 [+7.8, +123.2] no | +3.4 [-231.9, +184.5] no | +15.3 [+1.0, +46.4] no |
| 10 % | oracle-trigger | +1075.2 [+610.1, +2006.0] YES | +857.9 [-2669.1, +6691.5] no | +544.4 [+228.1, +1343.1] YES |
| 10 % | oracle-timing-bound | +284.6 [+177.8, +687.7] YES | +440.5 [-786.1, +2341.5] no | +104.8 [+56.8, +304.9] YES |
| 10 % | cloud-initiated | +35.6 [+15.4, +98.9] no | -2.5 [-245.5, +190.1] no | +22.2 [+1.3, +123.2] no |
| 10 % | context-trickle | +51.0 [+17.8, +136.8] no | +7.2 [-213.6, +180.7] no | +23.8 [+5.2, +67.1] no |
| 10 % | ceiling-gbt | +15.6 [-5.4, +87.4] no | +5.7 [-231.7, +194.3] no | +9.4 [-12.5, +42.8] no |
| 10 % | ceiling-logistic | +13.5 [-5.2, +54.4] no | +17.3 [-152.2, +160.7] no | +4.8 [-13.9, +22.4] no |
| 10 % | absolute-confidence | +16.1 [+3.2, +48.2] no | -11.3 [-317.8, +211.2] no | +15.1 [-0.7, +46.4] no |
| 10 % | random-escalation | +25.4 [+0.5, +139.6] - | +1.5 [-240.4, +185.5] - | +7.0 [-12.5, +34.8] - |
| 20 % | escalation-only | +24.9 [+6.3, +69.9] no | +1.4 [-259.7, +196.3] no | +25.7 [+3.4, +91.7] no |
| 20 % | oracle-trigger | +1075.2 [+610.1, +2006.0] YES | +857.9 [-2669.1, +6691.5] no | +544.4 [+228.1, +1343.1] YES |
| 20 % | oracle-timing-bound | +261.5 [+167.6, +628.7] YES | +352.7 [-522.6, +1712.4] no | +103.7 [+59.8, +289.3] YES |
| 20 % | cloud-initiated | +44.0 [+21.5, +94.7] no | +5.7 [-228.1, +202.7] no | +34.5 [+12.8, +80.7] no |
| 20 % | context-trickle | +51.4 [+25.4, +107.4] no | +33.5 [-104.9, +171.4] no | +37.0 [+15.2, +95.6] no |
| 20 % | ceiling-gbt | +29.6 [+6.6, +80.2] no | -8.3 [-340.5, +236.6] no | +10.0 [-22.1, +36.1] no |
| 20 % | ceiling-logistic | +24.9 [-0.6, +66.9] no | +10.1 [-256.9, +207.8] no | +9.8 [-17.9, +36.3] no |
| 20 % | absolute-confidence | +19.5 [-0.6, +43.0] no | +15.8 [-214.8, +196.8] no | +16.3 [-11.2, +41.9] no |
| 20 % | random-escalation | +24.6 [+0.9, +92.6] - | +17.4 [-170.2, +176.3] - | +16.1 [-7.7, +56.7] - |
| 40 % | escalation-only | +58.9 [+30.1, +145.7] no | +29.3 [-149.2, +163.8] no | +44.6 [+21.3, +104.1] no |
| 40 % | oracle-trigger | +1075.2 [+610.1, +2006.0] YES | +857.9 [-2669.1, +6691.5] no | +544.4 [+228.1, +1343.1] YES |
| 40 % | oracle-timing-bound | +180.6 [+122.8, +333.1] YES | +230.5 [-191.8, +944.6] no | +93.6 [+60.1, +213.5] no |
| 40 % | cloud-initiated | +33.6 [+10.9, +69.8] no | +27.4 [-168.6, +188.4] no | +34.6 [+10.9, +66.2] no |
| 40 % | context-trickle | +55.7 [+31.2, +97.6] no | +17.5 [-231.1, +212.6] no | +44.0 [+19.7, +82.9] no |
| 40 % | ceiling-gbt | +39.7 [+13.7, +72.3] no | +27.4 [-191.4, +190.7] no | +39.3 [+11.9, +82.1] no |
| 40 % | ceiling-logistic | +37.4 [+11.9, +70.2] no | +31.8 [-170.8, +185.4] no | +28.2 [-3.6, +96.0] no |
| 40 % | absolute-confidence | +44.6 [+21.2, +74.2] no | +31.8 [-153.6, +166.3] no | +42.1 [+13.5, +79.0] no |
| 40 % | random-escalation | +60.7 [+36.4, +113.3] - | +37.6 [-121.7, +151.0] - | +57.1 [+32.3, +129.1] - |

**What the sensitivities say.** The verdict is identical under all three: not one causal arm beats
random at any budget. The two alternatives differ in how much they can resolve at all. Under
ISOTONIC every interval is enormous (the gap denominator itself is poorly resolved once large
groups of scores are tied) and even the two non-causal oracles stop excluding zero, so that
calibration is not usable for this comparison and is reported as such rather than as a
disagreement. Under the INSTANT-LABEL Platt fit the oracles still separate at 5, 10 and 20 % and
the causal ordering is the same as the primary's, with slightly smaller point estimates; its base
rate is 0.0213 to 0.0217 rather than about 0.51, which is a different estimand (is an event
imminent) and is why the brief makes it a sensitivity and not the primary.

---

## 10. StudyE9b recheck: old against new

The committed cell, identified exactly:
`escalation-32B|32BI_N1|measured@25|cad50|far5|trig{5,10,20,40}|q75|k2|L10|c0` in
`results/dashcam/study_e9b/e9b_study1_results.json`, scored at horizon h = 0 against
`device-only|measured@25|far5` and `always-cloud/32BI_N1|measured@25|cad50|far5`. **A definition
correction on the way:** StudyCTRL1-episodes' report described this as a "1-s grid" result; it is
the 0.25-s grid with a 0.5-s cloud call cadence (cad50), which is the same call cadence this row
uses. StudyE9b's own `run_escalation` is called, not re-implemented.

| trigger rate | committed capture | reproduced from the raw traces | calibrated, cross-fitted | calibrated, ONE common map |
|---|---|---|---|---|
| 5 % | 0.03048 | **0.030498** | **0.20074** | **0.11644** |
| 10 % | 0.13311 | **0.133053** | **0.20208** | **0.48953** |
| 20 % | 0.12742 | **0.127403** | **0.36425** | **0.34012** |
| 40 % | 0.17753 | **0.177544** | **0.49826** | **0.37065** |

So StudyE9b's committed "3 to 18 % of the gap" becomes **12 to 49 %** on one common scale and
**20 to 50 %** cross-fitted. The reproduction column agrees with the committed values to 5
significant figures, which is the strongest available check that this is the same cell.

**The decisions are unchanged on one map and changed under cross-fitting, and the invocation counts
prove it.** StudyE9b's alarm, dismiss and trigger thresholds are score QUANTILES of the pooled
negative instants, so under ONE affine map with a > 0 a quantile maps to the transformed quantile
and every decision is identical:

| trigger rate | invocations, raw | invocations, one common map | invocations, cross-fitted |
|---|---|---|---|
| 5 % | 2,269 | **2,269** | 1,803 |
| 10 % | 4,419 | **4,419** | 3,704 |
| 20 % | 7,562 | **7,562** | 7,174 |
| 40 % | 12,785 | **12,785** | 12,755 |

The one-map column is therefore the clean statement: **with byte-identical escalation decisions and
byte-identical cloud work, calibrating the two tiers onto one scale raises the measured capture
from 3, 13, 13 and 18 % to 12, 49, 34 and 37 %.** The cross-fitted column changes the decisions too,
because a pooled quantile over five differently scaled folds is not the image of the raw quantile,
which is the same artifact sanity check (a) exposed.

---

## 11. FIRST RUN: results consistency check, 6 of 6

**The final primary's own 6-of-6 check is section 20.**

| # | check | outcome |
|---|---|---|
| 1 | cross-check against committed measurements | **PASS, and exactly, with one deliberate exception.** Challenge mAP, one per-tier map: device-only 0.4776042449177038 against the committed 0.4776042449177038 (difference 0.0) and always-cloud 0.5675307471627266 against 0.5675307471627266 (0.0). Streaming AP against StudyE9b's committed baselines at every horizon: worst absolute difference 1.7e-18 (device) and 6.9e-18 (cloud), ratio 1.000. StudyE9b's escalation capture reproduced to 5 significant figures at all four trigger rates (table in section 10). StudyCTRL1b's positives-only oracle reproduced exactly (0.3911 raw) and its raw median tier offset reproduced exactly (-5.1250 against the committed -5.125). THE EXCEPTION: under the pre-registered CROSS-FITTED calibration the two references move by -0.0251 and -0.0046 challenge mAP, ratios 0.947 and 0.992, which is far inside the 2x bar but is a DISAGREEMENT WITH A COMMITTED VALUE and is therefore investigated, explained and surfaced in section 3 rather than absorbed. |
| 2 | physical plausibility | **PASS.** Nothing is timed in this row. Every latency is a committed constant: device cadence 0.75 s and latency 0.567 s, cloud latency 0.3950 s, call cadence 0.50 s, uplink 13.6 Mbit/s, RTT 0.044 s. The one derived rate is the load column: 69.47 ms of H100 step time for a 378-token single-image prefill implies about 5,440 prompt tokens per second for an isolated small call, which is slower than the committed large-prefill rates and therefore not a caching artifact; it is labelled DERIVED and its six assumptions are listed in section 5. |
| 3 | distribution sanity | **PASS.** Every capture fraction and every paired difference carries a 2,000-resample CI (section 4 and 4.1). Episode lengths and call counts are reported as distributions with p25, p50, p75, min and max (4.2). Per-fold values are reported beside the pooled ones and they disagree by up to 3.6x (4.4). No quantity agrees to more precision than its inputs vary: the one place where numbers repeat to many decimals is the oracle across budgets, which StudyCTRL1b already established as the metric's own CONSTANT lead link (B2c) and which is carried forward with its explanation. |
| 4 | definition audit | **PASS with two definitions changed on purpose and one prior description corrected.** Unchanged and verified identical to the committed ones: the challenge metric (`study_e9d_delay.Challenge`, horizons 0.5 / 1.0 / 1.5 s, one crop per clip, unweighted mean of per-horizon AP), AP (`study_e9d_delay.ap_fast`, with sklearn absent and a raising stub installed by `metrics._ensure_sklearn_importable`), the delivery model (StudyE9b `held_stream` / `cloud_delivered`, setting (ii) measured@25), the streaming AP (StudyE9b `ApEngine`, asserted equal to `metrics.streaming_ap` to 0.0), the fold rule, the budget metric (call fraction, B1), a "turn" as a decision instant on the 0.5-s cadence, and an "episode" as spec 7.7's open-to-close interval. CHANGED ON PURPOSE: the PRIMARY METRIC (challenge mAP to streaming AP, C2, with both reported for every arm) and the SELECTION OBJECTIVE that follows it. CORRECTED: StudyCTRL1-episodes described StudyE9b's escalation cell as a "1-s grid" result; it is the 0.25-s grid at a 0.5-s call cadence (cad50), stated in section 10. No name is used with two different definitions inside this row. |
| 5 | claim linkage | **PASS.** The headline bears on the v3.1 addendum's open question Q11 (which SH trigger family) and on spec 4.1's u_SH, and it SUPPORTS the addendum's requirement that escalation be decided on a calibrated gain rather than a tier's own score: with the offset removed, the same escalation decisions are worth 2 to 4 times more measured capture (section 10), while the choice among trigger families remains unresolvable (section 4). It WEAKENS any claim that a better-targeted trigger is what stands between device-only and always-cloud on this workload, now for a second time and on a metric that reads every instant. It also bears on spec 7.7: the device filter's episodes are bit-identical to StudyCTRL1b's under the primary calibration, so nothing about the controller is re-opened. Nothing measured here is scoped out by FORMULATION.md: no KV moves between tiers, no cross-architecture transfer is measured, and no quantity is read from a cache. |
| 6 | proxy validity | **PASS with four proxies declared.** (a) The CLIP-LEVEL label as the calibration target: it is what the brief pre-registers and what both metrics rank against, but it makes a per-instant score predict a clip-level fact, and section 2 shows the device tier's calibrated probability failing to beat the base rate out of sample in 2 of 5 folds. Valid for putting the two tiers on one scale, which is what the mechanism needs, and NOT validated as a per-instant event probability; the instant-label sensitivity is the alternative estimand. (b) The challenge metric reads ONE crop per clip, so an arm that delivers at that instant is credited with the whole clip; this is why the primary moved to the streaming AP, and the challenge column is the secondary for exactly this reason. (c) The learned ceiling's target uses the clip label's SIGN (B8), so it is a ceiling available to an oracle-signed objective and not a deployable policy. (d) The context-modulated trickle's context signal is CLIP-LEVEL Nexar metadata standing in for the per-instant visual signal the brief intended, because the frame store is absent. None of (b) to (d) is load-bearing for the headline, which is a null; (a) is load-bearing and is the reason all three calibrations are reported. |

---

## 12. FIRST RUN, now SUPERSEDED: the decision rule and its outcome for Q11 on the cross-fitted reading

**SUPERSEDED BY SECTION 21. The verdict below (none beats random) is the CROSS-FITTED reading, which is now a sensitivity; under the final primary the cloud-initiated trickle beats random at 10 %. The Rule 2 labels below are also superseded by section 18.2.**

The rule, quoted from the frozen pre-registration: *an arm beats random at a budget if the pooled
5-fold difference in captured fraction of the always-cloud minus device-only gap (streaming AP
primary) has a bootstrap CI excluding 0. The recommended family for Q11 is the arm with the highest
streaming-AP capture at budgets <= 20 % among those that beat random; if none beats random, say so
plainly.*

**NONE BEATS RANDOM.** Not at 5 %, not at 10 %, not at 20 %, and not at 40 %. Of the five causal
trigger families, zero have a difference-against-random interval that excludes zero in the positive
direction at any budget, on the primary metric, under the primary calibration. The same holds under
both sensitivity calibrations and under the one-common-scale re-scoring. The only arms that beat
random are the two NON-CAUSAL oracles, which are bounds and not policies. **The rule therefore
returns no recommended family, and under the rule as written Q11 cannot be decided from this
evidence.**

**Rule 2 classification of the null (CLAUDE.md).** This null is **MIXED and must be read per cell**,
not as one verdict:

* **REAL NEGATIVE** for the device filter (spec 7.7), the absolute-confidence trigger and both
  learned ceilings, at every budget: their mechanisms were present and exercised (Step 2 links all
  non-zero and varying, the Step 4 controls changed the result, the device filter's episodes are
  bit-identical to StudyCTRL1b's so the controller is the same object), they operated as specified,
  and they did not beat random. For the learned ceiling this is the informative one, because it is
  fitted on an oracle-signed target with a flexible model and still does not separate: on the
  features a device actually has, after calibration, there is very little left to extract.
* **INCONCLUSIVE, a design failure** for the cloud trickle at 5 % and for the context-modulated
  trickle at 5 % and 10 %: in those cells the trigger never fires, because the cheapest feasible
  background cadence consumes the whole budget (section 7). Those cells have not tested the claim
  and their numbers are not evidence that a cloud-initiated trigger does not work at low budget.
  The cloud trickle at 10, 20 and 40 % and the context trickle at 40 % ARE exercised and are real
  negatives; the context trickle at 20 % is exercised in 3 folds of 5 and should be read as partly
  inconclusive.

**What IS settled, and it is the row's most useful output.** The defect D57 named is real and is
now removed and quantified: the tier offset falls from -5.1250 to -0.0639 log-odds, the
positives-only oracle moves from -0.0865 below device-only to +0.0923 above it, and StudyE9b's own
escalation, with byte-identical decisions and byte-identical cloud work, goes from capturing 3 to
18 % of the gap to capturing 12 to 49 %. The value that calibration unlocks is two to four times
the value that any choice among trigger families is worth, and the latter is still not measurable.

---

## 13. FIRST RUN INTERPRETATION (separately labelled; not a measurement; written on the cross-fitted reading)

Everything above this line is measured or declared. What follows is reading.

**The policy consequence is an assignment to u_SH, not to a trigger family.** If the capacity to
decide Q11 is what is wanted, this row says it is not available from this workload at this n, and
that two prior attempts have now said so on two different metrics. The thing that DID move, by a
factor of two to four, is what the cloud's answer is worth once both tiers speak the same units.
StudyPOL2-build already reads u_SH from a calibrated DEV table and has no path that accepts a raw
score; this row is the measurement behind that choice, and
`results/dashcam/ctrl1c/ctrl1c_calibration.json` is the artefact the library can load, with
`single_map.platt.dev90` as the recommended entry because it never saw the committed EVAL side.

**A suggestion the user may want to accept or reject.** Q11 leaves three trigger families
interchangeable in code. On this evidence the cheapest-to-operate family is the one to pick, since
none is measurably better: that is the device filter (spec 7.7), which needs no cloud-side poll, no
background budget floor and no clip metadata, and whose episodes are already instrumented in the
workload traces. The two trickle families carry a structural disadvantage this row measured rather
than argued: a cloud-side poll costs `call_cadence / background_cadence` of the decision instants
before it opens a single episode, so at a 5 % budget (about 144 devices per H100) it has no room to
exist. That is an argument from feasibility, not from quality, and it is the only argument the data
supports.

**What would actually decide Q11.** Not a cleverer trigger. The non-causal timing bound captures
+180 to +472 % of the streaming-AP gap and +81 % of the challenge gap, so the headroom is real and
large and no causal trigger reaches it. Three things would move it, in order of expected value: the
frame store restored to this machine, so the ceiling can be computed with the visual features the
brief intended rather than with clip metadata; a budget metric that does not charge a background
poll and an episode call the same, so the cloud-initiated family is testable where a shared H100
actually has capacity; and more clips, since fold 1's device-only streaming AP is 3.6 times fold
0's and the pooled CI is dominated by that spread.

**One thing this row quietly settles about the metric.** The streaming AP, which reads every
decision instant, and the challenge mAP, which reads one crop per clip, agree on the verdict and
disagree on the magnitudes, sometimes by a factor of two. Neither is a substitute for the other and
this row reports both for every arm. But the streaming AP has a property the challenge metric does
not: a non-causal arm can exceed always-cloud on it, because always-cloud is a 0.5-s poll with a
0.395 s delivery and not an oracle placement. Any future capture fraction computed on the streaming
AP should say whether its arm is causal before it is read as a fraction of a bound.

---

## 14. FIRST RUN: what this row does NOT establish

* It does not decide Q11. It supplies the comparison, cleaned of the three defects, and the
  comparison does not separate the families.
* It does not measure the cloud-initiated trigger at a 5 % budget, or the context-modulated trickle
  at 5 % or 10 %: the trigger cannot fire there. Those rows are background cadence alone.
* It does not establish that either tier's calibrated probability is a good per-instant event
  probability. The device tier's fails to beat the base rate out of sample in 2 of 5 folds.
* It does not bound what visual features could predict, for want of the frames.
* It does not resolve which scale reading should be primary. That WAS the open STOP AND ASK;
  **it is RESOLVED in section 16, and the STOP AND ASK is closed.** The final primary is one
  Platt map per tier fitted on the StudyD3 Nexar DEV split, under which sanity check (a) holds
  exactly.

---

## 15. FIRST RUN files (the second run's are in section 22)

| file | what |
|---|---|
| `experiments/dashcam/ctrl1c_calibrate.py` | the per-tier calibration: Platt, isotonic, instant-label Platt, their application, the cross-fitted and single-map contexts, and the reliability curves |
| `experiments/dashcam/ctrl1c_metrics.py` | the primary metric: StudyE9b's ApEngine averaged over horizons 0.5 / 1.0 / 1.5 s, the paired bootstrap, the capture fraction, the pre-registered difference-against-random, and the assertion that it reproduces `metrics.streaming_ap` |
| `experiments/dashcam/ctrl1c_crossfit.py` | the study: per-fold fits on the calibrated scale, the extended cadence grid, mechanism verification Steps 1 to 5, the pooled held-out evaluation with both metrics, the one-common-scale re-scoring, the sanity checks, the load column and the StudyE9b recheck |
| `results/dashcam/ctrl1c/ctrl1c_calibration.json` | every calibration fit: 3 kinds x 5 folds x 2 tiers, plus the DEV-90 and all-300 single maps and the reliability curves, in a form the policy library can load |
| `results/dashcam/ctrl1c/ctrl1c_fits_platt.json` | the primary run's training-fold fits: controller, absolute confidence, random, oracle leads, cloud trickle candidates per cadence, learned models and context trickle |
| `results/dashcam/ctrl1c/ctrl1c_fits_isotonic.json` | the same for the isotonic sensitivity |
| `results/dashcam/ctrl1c/ctrl1c_fits_platt_instant.json` | the same for the instant-label sensitivity |
| `results/dashcam/ctrl1c/ctrl1c_mechanism_platt.json` | mechanism verification Steps 1 to 5 for C1 to C4, with StudyCTRL1b's own protocol re-run on the calibrated scale attached |
| `results/dashcam/ctrl1c/ctrl1c_pooled_platt.json` | the primary pooled held-out results: capture tables, both metrics, per-horizon, per-fold, episode statistics, the one-common-scale re-scoring and the sanity checks |
| `results/dashcam/ctrl1c/ctrl1c_pooled_isotonic.json` | the isotonic sensitivity's pooled results |
| `results/dashcam/ctrl1c/ctrl1c_pooled_platt_instant.json` | the instant-label sensitivity's pooled results |
| `results/dashcam/ctrl1c/ctrl1c_e9b_recheck_platt.json` | the StudyE9b recheck: three scales, four trigger rates, invocation counts |
| `results/dashcam/ctrl1c/ctrl1c_load_column.json` | the DERIVED load column and its six assumptions |
| `reports/study_ctrl1c_calibrated.md` | this report |

Imported and NOT edited: `experiments/dashcam/ctrl1b_crossfit.py`, `ctrl1b_learned.py`,
`d14b_folds.py`, `ctrl1_controller.py`, `d14b_split.py`,
`experiments/orchestration/sim/metrics.py`, `experiments/dashcam/study_e9b_dense.py`,
`study_e9_episodes.py`, `study_e9d_delay.py`.

---

# SECOND RUN: the FINAL PRIMARY

Everything from section 1 to section 15 above is the FIRST RUN. Its primary reading was the fully
cross-fitted calibration (five per-fold Platt maps), which raised the one open STOP AND ASK in
section 3: sanity check (a) cannot hold under five maps. The user ruled on that stop and the ruling
is executed here. **Sections 16 to 22 are the FINAL PRIMARY. The first run's cross-fitted tables in
sections 4, 7, 8 and 12, and its two alternative calibrations in section 9, are retained as
LABELLED SENSITIVITIES and are no longer the primary reading.**

---

## 16. Check A, check B, and the branch taken

### 16.1 Check A: do 4B and 32B scores exist on the StudyD3 DEV split

**YES.** Both tiers are scored at N = 1 on the StudyD3 Nexar DEV clips, in one committed file:

| what | where |
|---|---|
| the scores (both tiers, N = 1 / 3 / 9) | `results/dashcam/study_d3_nexar/d3_requests_h100nvl.jsonl.gz` |
| the run contract (models, revisions, query, decoding) | `results/dashcam/study_d3_nexar/d3_run_meta_h100nvl.json` |
| the tokenised N = 1 prompt | `results/dashcam/study_d3_nexar/prompt_trace_N1.txt` |
| the split that defines DEV against the evaluation side | `results/dashcam/study_d2_nexar/nexar_train_split_seed0.csv` |
| the 300 evaluation clips and their folds | `results/dashcam/ctrl1b/d14b_folds.json` |
| the fitted maps, written by the first run | `results/dashcam/ctrl1c/ctrl1c_calibration.json`, `single_map.d3dev` |

N = 1 rows used: **6,010 per tier** (4BI and 32BI), over **601 clips**, 3,010 positive rows,
base rate 0.5008.

**(i) Decision cadence / offset design: it is the OFFSET design, not the dense trajectory.**
StudyD3 renders ten EVENT-ANCHORED prefix ends per clip at offsets -3.0, -2.5, -2.0, -1.5, -1.0,
-0.5, 0.0, +0.5, +1.0 and +2.0 s relative to the event (a pseudo-event assigned by D2's rule on
negative clips). The SPACING between the first nine offsets is 0.5 s, the same as this row's
decision cadence, but the sample covers only a 5-s neighbourhood of the event, not the whole clip:
6,010 rows over 601 clips is exactly 10 rows per clip. StudyD14b, by contrast, scores absolute clip
times on a 0.25-s grid over the whole clip. So StudyCTRL1's finding is confirmed: **D3 DEV holds a
10-offset design, not a 0.25 / 0.5-s trajectory.** This is a DECLARED DEVIATION from the ruling's
"same decision cadence" and its sensitivity is in 16.2.

**(ii) Model variants and request contract: IDENTICAL. PASSES.**

| property | StudyD3 DEV | StudyD14b evaluation | same |
|---|---|---|---|
| device model | `Qwen/Qwen3-VL-4B-Instruct` rev `ebb281ec70b05090aa6165b016eac8ec08e71b17` | the same repo at the same revision | YES |
| cloud model | `Qwen/Qwen3-VL-32B-Instruct` rev `0cfaf48183f594c314753d30a4c4974bc75f3ccb` | the same repo at the same revision | YES |
| query | "Is a collision or near-collision involving the camera vehicle happening or about to happen? Answer only Yes or No." | byte-identical | YES |
| N = 1 header | "The following is 1 dashcam frame." on 12,020 of 12,020 rows | the same string on 84,028 of 84,028 rows | YES |
| N = 1 prompt tokens | 378 on every row | 378 on every row | YES |
| image contract | 1 image, 336 image pads, SMALL 768x432 LANCZOS lossless PNG | the same, 336 pads | YES |
| decoding | temperature 0.0, max_tokens 8, seed 0, logprobs, top_logprobs 20 | identical | YES |
| prefix caching | off, `--no-enable-prefix-caching`, mm-processor-cache 0 | off, same flags | YES |
| score definition | log(p_yes) | log(p_yes), StudyD14b's committed `score` to 0.0 | YES |

**(iii) Clip overlap with the 300 evaluation clips: ZERO. PASSES.** The 601 D3 N = 1 clips are all
on the `dev` side of `nexar_train_split_seed0.csv`; all 300 evaluation clips are on the `val` side.
Intersection computed directly on the file names: **0 clips**. The assertion is also in the code
(`ctrl1c_calibrate.d3_dev_sample`, which raises if a D3 row lands on an evaluation clip) and is
re-asserted in sanity check (c) below.

**Both (ii) and (iii) hold, so the YES branch is VALID and is the branch taken:** ONE Platt map per
tier, fitted on the StudyD3 DEV split with the clip-level label as pre-registered, used for BOTH
the trigger decisions AND the scoring of the delivered stream, for every clip and every fold. No
per-fold calibration. The tunables remain cross-fitted on each fold's 240 training clips, which is
unchanged from the pre-registration.

The maps, exactly as applied (`log_odds = a * log(p_yes) + b`):

| tier | a | b | n rows | n clips | base rate |
|---|---|---|---|---|---|
| device 4BI N1 | +0.114603 | +1.140751 | 6,010 | 601 | 0.5008 |
| cloud 32BI N1 | +0.129472 | +1.848187 | 6,010 | 601 | 0.5008 |

### 16.2 The declared deviation, and its one sensitivity

The deviation: the map is fitted on an EVENT-ANCHORED 10-offset sample at 0.5-s spacing, not on the
dense whole-clip decision-instant trajectory the ruling's phrase "same decision cadence" implies.
The required sensitivity compares the D3-fitted map's parameters against a Platt map fitted on the
StudyD14b DEV-fold instants (`single_map.platt.dev90`, 6,349 instants over the committed 90-clip
D14b DEV side, which never saw the 300 evaluation clips):

| tier | quantity | D3 DEV (final primary) | D14b DEV-90 instants | difference |
|---|---|---|---|---|
| device 4BI N1 | slope a | +0.114603 | +0.038113 | **3.007x steeper** |
| device 4BI N1 | intercept b | +1.140751 | +0.438842 | +0.701909 |
| device 4BI N1 | raw score at p = 0.5 | -9.9539 | -11.5143 | **1.5604 log units** |
| cloud 32BI N1 | slope a | +0.129472 | +0.049983 | **2.590x steeper** |
| cloud 32BI N1 | intercept b | +1.848187 | +0.768324 | +1.079862 |
| cloud 32BI N1 | raw score at p = 0.5 | -14.2748 | -15.3718 | **1.0971 log units** |
| both | the TIER OFFSET at p = 0.5 (cloud minus device) | **-4.3209** | **-3.8575** | 0.4634 |

**What the difference is and is not.** The two maps disagree substantially in SHARPNESS: the D3 map
is 2.6 to 3.0 times steeper, which is what fitting on a 5-s neighbourhood of the event rather than
on whole clips should do, because near-event instants carry more of the clip label. They agree much
more closely on the thing the mechanism needs, which is the TIER OFFSET: the raw score at which
each tier crosses p = 0.5 differs between the tiers by -4.32 log units under the D3 map and -3.86
under the D14b DEV map, a 0.46-log-unit disagreement against a RAW offset of -5.125. Since both
metrics are rank metrics and a common increasing function of the calibrated log-odds cannot change
the pooled order, the slope disagreement affects the two tiers almost equally and the measured
residual tier offset after calibration is -0.1197 log-odds under the D3 map against -5.1250 raw
(section 21, link C1). The deviation is therefore material to any claim about per-instant
PROBABILITY values and immaterial to the per-tier scale alignment this row needs it for.

### 16.3 Check B: `ctrl1c_fits_d3dev.json` verified by refitting fold 0 from scratch

Fold 0's tunables were recomputed from scratch under the same d3dev map, in a separate process, and
compared leaf by leaf against the committed file after the identical JSON round trip.

**TOTAL LEAF DIFFERENCES: 0**, over the whole fold-0 record: `controller`, `absolute`, `random`,
`oracle`, `cloud_initiated` (all seven cadences), `objective`, `search_ranges`,
`train_references`, `learned` and `context_trickle`. The headline tunables:

| budget | W_c | delta | n_c | K_c | mode | theta | train call fraction | train streaming AP | match |
|---|---|---|---|---|---|---|---|---|---|
| 5 % | 3.0 | 1.50 | 2 | 1 | var | 3.0000009537 | 0.0495055368 | 0.013873549669 | **exact** |
| 10 % | 3.0 | 1.50 | 2 | 2 | var | 2.8419165611 | 0.0998993308 | 0.014445374217 | **exact** |
| 20 % | 3.0 | 1.50 | 2 | 2 | var | 2.2771806717 | 0.1999170960 | 0.014430408685 | **exact** |
| 40 % | 6.0 | 1.50 | 2 | 4 | var | 1.6000256538 | 0.3999526263 | 0.015694434516 | **exact** |

The file is verified and **no refit of the other four folds was needed.** The verification ran for
196 s on CPU; its script is `.../scratchpad/verify_b.py` and is not a committed artefact.

### 16.4 One implementation fix, applied and reported

The pooling stage's sanity check (c) asserted `calibration_fitted_on_n_clips == n_train` for every
fold, which was written for a calibration fitted ON the evaluation clips. Under the d3dev map the
calibration is fitted on 601 DISJOINT clips and that assertion fails although the leak-free
condition is strictly STRONGER. The assertion now branches on the calibration kind and requires,
for d3dev, that the calibration's overlap with the 300 evaluation clips be 0 in every fold. The
check_a explanation string likewise branches, because the cross-fitting caveat does not apply when
all five by-fold maps are the same object. Both are implementation fixes under CLAUDE.md (an
incorrect measurement procedure for this branch), not methodological changes: no data, fold, arm,
budget, cadence or metric definition is touched.

### 16.5 Sanity checks under the final primary

**(a) always-cloud and device-only unchanged by calibration: HOLDS EXACTLY.** This is what the YES
branch demanded be verified, and it is verified to machine zero in BOTH contexts, because under
d3dev the cross-fitted context and the single-map context are the same object:

| context | device-only challenge | always-cloud challenge | diff vs committed | streaming AP max abs diff vs StudyE9b (device / cloud) | verdict |
|---|---|---|---|---|---|
| raw, no calibration (reproduction control) | 0.4776042449177038 | 0.5675307471627266 | 0.0 / 0.0 | 1.7e-18 / 6.9e-18 | PASS, exact |
| d3dev, ONE map per tier, single-map context | 0.4776042449177038 | 0.5675307471627266 | **0.0 / 0.0** | **1.7e-18 / 6.9e-18** | **PASS, EXACT** |
| d3dev, cross-fitted context (the same five maps) | 0.4776042449177038 | 0.5675307471627266 | **0.0 / 0.0** | **1.7e-18 / 6.9e-18** | **PASS, EXACT** |

So the STOP AND ASK the first run raised is resolved rather than argued: the challenge-mAP gap the
arms compete for returns to the committed **0.0899** (against 0.1104 cross-fitted), and the
streaming-AP gap is **0.00332** (device-only 0.00995724, always-cloud 0.01327471).

**(b) the positives-only oracle gate: PASS.**

| scale | oracle positives only | device-only | margin | gate |
|---|---|---|---|---|
| raw, no calibration | 0.3910784585 | 0.4776042449 | **-0.0865258** | would FAIL |
| d3dev (final primary) | **0.5703711658** | **0.4776042449** | **+0.0927669** | **PASS** |

**(c) no leakage: PASS.** Train / held-out overlap 0 in all five folds, 240 train and 60 held in
each; the calibration is fitted on 601 D3 DEV clips of which **0** are among the 300.

**(d) the streaming-AP engine accepts the calibrated scores without changing its definition: PASS.**
Worst absolute difference against `metrics.streaming_ap` itself: **0.0**.

---

## 17. FINAL PRIMARY main table: arm x budget under the StudyD3 DEV map

All 300 clips, every one held out of its fold's tunables. Capture fraction is (arm minus
device-only) divided by (always-cloud minus device-only) on the primary metric, with the CI over
the same 2,000 paired clip resamples (seed 0). "beats random" is the PRE-REGISTERED rule: the
pooled 5-fold difference in captured fraction against random escalation, resample by resample, with
a bootstrap CI excluding 0; the sign is stated whenever it excludes 0. References: streaming
device-only 0.00996 and always-cloud 0.01327, streaming gap **0.00332**; challenge device-only
0.4776 and always-cloud 0.5675, challenge gap **0.0899**, at every budget. The LOAD column is
DERIVED from the ENG1 step model (section 5) and is unchanged.

The oracles' streaming-AP capture remains a diagnostic, not a fraction of a bound, for the reason
section 4 gives.

### Budget 5 % of the call rate (DERIVED load: about 144 devices per H100)

| arm | streaming AP | streaming capture % | CI % | beats random | challenge mAP | challenge capture % | call fraction | n episodes |
|---|---|---|---|---|---|---|---|---|
| device filter (spec 7.7) | 0.01023 | +8.3 | [-14.2, +62.1] | no | 0.4912 | +15.2 | 0.0487 | 380 |
| oracle trigger, positives only (NON-CAUSAL) | 0.11790 | +3253.7 | [+1723.2, +7910.5] | YES | 0.5704 | +103.2 | 0.0508 | 150 |
| oracle timing bound, every crop (NON-CAUSAL) | 0.04006 | +907.5 | [+465.5, +2644.1] | YES | 0.5489 | +79.3 | 0.0508 | 300 |
| cloud trickle | 0.00984 | -3.6 | [-29.6, -0.3] | yes, RANDOM IS BETTER (and trigger DEGENERATE in 5 of 5 folds) | 0.4779 | +0.3 | 0.0542 | 0 |
| context-modulated trickle | 0.00990 | -1.7 | [-13.8, -0.1] | no (trigger DEGENERATE or INFEASIBLE in 5 of 5 folds) | 0.4773 | -0.4 | 0.0113 | 0 |
| predictability ceiling, boosted trees (LEARNED) | 0.01024 | +8.4 | [-21.7, +54.1] | no | 0.4901 | +13.9 | 0.0478 | 188 |
| predictability ceiling, logistic (LEARNED) | 0.01158 | +48.9 | [+3.4, +389.9] | no | 0.5009 | +25.9 | 0.0499 | 168 |
| absolute-confidence trigger | 0.01111 | +34.6 | [-16.6, +184.0] | no | 0.4849 | +8.2 | 0.0530 | 290 |
| random escalation | 0.01034 | +11.7 | [-6.1, +69.1] | reference | 0.4992 | +24.1 | 0.0543 | 482 |
| device-only (reference) | 0.00996 | 0.0 | - | - | 0.4776 | 0.0 | 0.0000 | 0 |
| always-cloud (reference) | 0.01327 | +100.0 | - | - | 0.5675 | +100.0 | 1.0000 | 0 |

### Budget 10 % of the call rate (DERIVED load: about 72 devices per H100)

| arm | streaming AP | streaming capture % | CI % | beats random | challenge mAP | challenge capture % | call fraction | n episodes |
|---|---|---|---|---|---|---|---|---|
| device filter (spec 7.7) | 0.01083 | +26.5 | [+2.3, +93.5] | no | 0.5039 | +29.3 | 0.1036 | 487 |
| oracle trigger, positives only (NON-CAUSAL) | 0.11790 | +3253.7 | [+1723.2, +7910.5] | YES | 0.5704 | +103.2 | 0.0997 | 150 |
| oracle timing bound, every crop (NON-CAUSAL) | 0.03059 | +621.8 | [+331.9, +1570.6] | YES | 0.5489 | +79.3 | 0.1043 | 300 |
| **cloud trickle** | **0.01417** | **+127.0** | **[+24.2, +374.6]** | **YES (live trigger in 5 of 5 folds)** | 0.4905 | +14.4 | 0.0999 | 105 |
| context-modulated trickle | 0.01322 | +98.3 | [+25.1, +422.5] | YES, but trigger DEGENERATE in 4 of 5 folds | 0.5028 | +28.0 | 0.1029 | 25 |
| predictability ceiling, boosted trees (LEARNED) | 0.01041 | +13.7 | [-17.5, +52.2] | no | 0.4954 | +19.8 | 0.0971 | 365 |
| predictability ceiling, logistic (LEARNED) | 0.01115 | +35.9 | [-7.0, +158.1] | no | 0.4933 | +17.5 | 0.0945 | 304 |
| absolute-confidence trigger | 0.01107 | +33.6 | [-6.3, +188.4] | no | 0.4847 | +7.9 | 0.0974 | 329 |
| random escalation | 0.01030 | +10.2 | [-10.9, +59.6] | reference | 0.4978 | +22.5 | 0.1096 | 554 |
| device-only (reference) | 0.00996 | 0.0 | - | - | 0.4776 | 0.0 | 0.0000 | 0 |
| always-cloud (reference) | 0.01327 | +100.0 | - | - | 0.5675 | +100.0 | 1.0000 | 0 |

### Budget 20 % of the call rate (DERIVED load: about 36 devices per H100)

| arm | streaming AP | streaming capture % | CI % | beats random | challenge mAP | challenge capture % | call fraction | n episodes |
|---|---|---|---|---|---|---|---|---|
| device filter (spec 7.7) | 0.01145 | +45.1 | [-1.6, +228.5] | no | 0.4960 | +20.5 | 0.2008 | 839 |
| oracle trigger, positives only (NON-CAUSAL) | 0.11790 | +3253.7 | [+1723.2, +7910.5] | YES | 0.5704 | +103.2 | 0.1995 | 150 |
| oracle timing bound, every crop (NON-CAUSAL) | 0.02622 | +490.1 | [+271.0, +1193.4] | YES | 0.5489 | +79.3 | 0.2022 | 300 |
| cloud trickle | 0.01201 | +61.8 | [+22.5, +181.2] | no | 0.5012 | +26.3 | 0.2017 | 298 |
| context-modulated trickle | 0.01223 | +68.5 | [+25.1, +209.6] | no (live trigger in 3 of 5 folds) | 0.4952 | +19.6 | 0.2077 | 126 |
| predictability ceiling, boosted trees (LEARNED) | 0.01083 | +26.4 | [-13.9, +78.8] | no | 0.5130 | +39.3 | 0.1886 | 663 |
| predictability ceiling, logistic (LEARNED) | 0.01171 | +52.8 | [+7.5, +169.4] | no | 0.5011 | +26.2 | 0.1812 | 588 |
| absolute-confidence trigger | 0.01060 | +19.3 | [-20.3, +75.4] | no | 0.4936 | +17.8 | 0.2005 | 645 |
| random escalation | 0.01141 | +43.9 | [-9.5, +223.5] | reference | 0.5093 | +35.3 | 0.2063 | 900 |
| device-only (reference) | 0.00996 | 0.0 | - | - | 0.4776 | 0.0 | 0.0000 | 0 |
| always-cloud (reference) | 0.01327 | +100.0 | - | - | 0.5675 | +100.0 | 1.0000 | 0 |

### Budget 40 % of the call rate (DERIVED load: about 18 devices per H100)

| arm | streaming AP | streaming capture % | CI % | beats random | challenge mAP | challenge capture % | call fraction | n episodes |
|---|---|---|---|---|---|---|---|---|
| device filter (spec 7.7) | 0.01186 | +57.5 | [+21.6, +120.4] | no | 0.5287 | +56.8 | 0.4010 | 1248 |
| oracle trigger, positives only (NON-CAUSAL) | 0.11790 | +3253.7 | [+1723.2, +7910.5] | YES | 0.5704 | +103.2 | 0.2246 | 150 |
| oracle timing bound, every crop (NON-CAUSAL) | 0.01950 | +287.6 | [+178.0, +680.7] | YES | 0.5489 | +79.3 | 0.3996 | 300 |
| cloud trickle | 0.01154 | +47.6 | [+3.5, +105.1] | no | 0.5027 | +27.9 | 0.4009 | 723 |
| context-modulated trickle | 0.01203 | +62.4 | [+26.2, +119.9] | no | 0.5118 | +38.0 | 0.3898 | 557 |
| predictability ceiling, boosted trees (LEARNED) | 0.01177 | +54.6 | [+11.2, +112.9] | no | 0.5164 | +43.1 | 0.3784 | 1123 |
| predictability ceiling, logistic (LEARNED) | 0.01181 | +56.0 | [+9.6, +129.7] | no | 0.5109 | +37.1 | 0.3659 | 1154 |
| absolute-confidence trigger | 0.01151 | +46.9 | [+13.0, +89.4] | no | 0.5134 | +39.8 | 0.4044 | 1030 |
| random escalation | 0.01224 | +68.8 | [+31.6, +149.6] | reference | 0.5428 | +72.5 | 0.4056 | 1422 |
| device-only (reference) | 0.00996 | 0.0 | - | - | 0.4776 | 0.0 | 0.0000 | 0 |
| always-cloud (reference) | 0.01327 | +100.0 | - | - | 0.5675 | +100.0 | 1.0000 | 0 |

### 17.1 The pre-registered difference against random, every causal arm and budget

In capture-fraction points on the primary metric, paired resample by resample:

| budget | arm | difference vs random | CI | excludes 0 | reading |
|---|---|---|---|---|---|
| 5 % | device filter | -3.3 | [-58.9, +45.4] | no | - |
| 5 % | cloud trickle | -15.3 | [-89.0, -1.5] | yes | RANDOM IS BETTER, and the trigger is degenerate in 5 of 5 folds |
| 5 % | context trickle | -13.4 | [-74.7, +1.8] | no | - |
| 5 % | ceiling gbt | -3.3 | [-70.2, +39.7] | no | - |
| 5 % | ceiling logistic | +37.2 | [-27.0, +372.2] | no | - |
| 5 % | absolute confidence | +23.0 | [-55.7, +168.8] | no | - |
| 10 % | device filter | +16.2 | [-27.9, +83.2] | no | - |
| 10 % | **cloud trickle** | **+116.8** | **[+3.5, +359.0]** | **yes** | **THE ARM BEATS RANDOM, live trigger in 5 of 5 folds** |
| 10 % | context trickle | +88.1 | [+5.4, +399.6] | yes | the arm beats random, but the trigger is degenerate in 4 of 5 folds |
| 10 % | ceiling gbt | +3.5 | [-47.0, +40.8] | no | - |
| 10 % | ceiling logistic | +25.7 | [-35.1, +146.6] | no | - |
| 10 % | absolute confidence | +23.4 | [-34.8, +183.2] | no | - |
| 20 % | device filter | +1.2 | [-115.7, +123.0] | no | - |
| 20 % | cloud trickle | +17.9 | [-134.9, +109.1] | no | - |
| 20 % | context trickle | +24.6 | [-159.4, +167.0] | no | live trigger in 3 of 5 folds |
| 20 % | ceiling gbt | -17.5 | [-222.8, +57.1] | no | - |
| 20 % | ceiling logistic | +8.9 | [-191.7, +146.5] | no | - |
| 20 % | absolute confidence | -24.6 | [-189.8, +23.5] | no | - |
| 40 % | device filter | -11.4 | [-84.9, +38.0] | no | - |
| 40 % | cloud trickle | -21.2 | [-118.0, +54.2] | no | - |
| 40 % | context trickle | -6.4 | [-91.0, +63.1] | no | - |
| 40 % | ceiling gbt | -14.2 | [-105.2, +51.4] | no | - |
| 40 % | ceiling logistic | -12.9 | [-83.9, +47.5] | no | - |
| 40 % | absolute confidence | -21.9 | [-113.5, +34.9] | no | - |
| 5 to 40 % | oracle trigger (NON-CAUSAL) | +3184.9 to +3243.5 | all exclude 0 | yes | - |
| 5 to 40 % | oracle timing bound (NON-CAUSAL) | +218.7 to +895.8 | all exclude 0 | yes | - |

**On the SECONDARY metric (challenge mAP) not one causal arm beats random in the positive direction
at any budget**, and three cells exclude zero in the NEGATIVE direction: the cloud trickle at 5 %
(-0.0214, CI [-0.0401, -0.0027]), the context trickle at 5 % (-0.0220, CI [-0.0395, -0.0043]) and
the cloud trickle at 40 % (-0.0401, CI [-0.0716, -0.0024]). The 10 % cloud-trickle cell, which wins
on the primary, is -0.0073 with CI [-0.0349, +0.0241] on the secondary, that is indistinguishable
from random there.

### 17.2 Per-fold spread of the 10 % cell, because the headline rests on it

Streaming AP on the five held-out folds at the 10 % budget:

| fold | device-only | always-cloud | device filter | cloud trickle | context trickle | random |
|---|---|---|---|---|---|---|
| 0 | 0.00621 | 0.01212 | 0.00701 | 0.00860 | 0.00891 | 0.00745 |
| 1 | 0.02236 | 0.03314 | 0.02502 | **0.04866** | 0.05911 | 0.02218 |
| 2 | 0.00941 | 0.01279 | 0.01051 | 0.00985 | 0.00982 | 0.00950 |
| 3 | 0.00993 | 0.01096 | 0.01075 | 0.01178 | 0.01051 | 0.00961 |
| 4 | 0.01898 | 0.02779 | 0.02570 | **0.04220** | 0.04274 | 0.01992 |

The cloud trickle's advantage over random at 10 % is concentrated in folds 1 and 4, where it is 2.2x
and 2.1x random; in folds 0, 2 and 3 the margin is small. Both arms also EXCEED always-cloud in
folds 1 and 4, which is possible on the streaming AP for the reason section 4 gives (always-cloud
is a 0.5-s poll with a 0.395-s delivery, not an oracle placement) but means the 10 % capture
fraction is not bounded by 100 % and should not be read as "most of the gap". The pooled CI is wide
for exactly this reason: fold 1's device-only streaming AP is 3.6x fold 0's.

### 17.3 Episodes at the 20 % budget, as distributions

| arm | escalations per device-minute | episode length s p50 (p25, p75, min, max) | calls per episode p50 | false episodes per minute on negatives |
|---|---|---|---|---|
| device filter | 4.79 | 2.25 (1.75, 3.75, 0.25, 5.25) | 4.0 | 5.03 |
| absolute confidence | 3.68 | 3.75 (2.25, 5.25, 0.25, 5.25) | 7.0 | 3.37 |
| random escalation | 5.14 | 2.25 (1.75, 3.75, 0.25, 3.75) | 4.0 | 4.85 |
| oracle trigger | 0.86 | 14.75 (14.25, 15.25, 5.75, 15.75) | 29.0 | 0.00 |
| oracle timing bound | 1.71 | 7.75 (7.25, 7.75, 1.75, 7.75) | 15.0 | 1.76 |
| cloud trickle | 1.70 | 3.75 (2.75, 5.25, 0.25, 5.25) | 7.0 | 1.22 |
| context trickle | 0.72 | 3.25 (1.75, 5.25, 0.50, 5.25) | 6.0 | 0.50 |
| ceiling gbt | 3.79 | 3.25 (2.25, 3.88, 0.25, 5.25) | 6.0 | 3.14 |
| ceiling logistic | 3.36 | 3.75 (2.00, 5.25, 0.25, 5.25) | 7.0 | 2.96 |

### 17.4 Per-horizon streaming AP at the 5 % budget, and h = 0

| arm | h = 0 | h = 0.5 | h = 1.0 | h = 1.5 | primary mean |
|---|---|---|---|---|---|
| device-only | 0.01261 | 0.01043 | 0.01023 | 0.00921 | 0.00996 |
| always-cloud | 0.03840 | 0.01613 | 0.01266 | 0.01103 | 0.01327 |
| device filter | 0.01964 | 0.01072 | 0.01068 | 0.00931 | 0.01023 |
| oracle trigger | 0.06034 | 0.14273 | 0.12641 | 0.08456 | 0.11790 |
| oracle timing bound | 0.02041 | 0.05763 | 0.04660 | 0.01596 | 0.04006 |
| cloud trickle | 0.01241 | 0.01030 | 0.01005 | 0.00916 | 0.00984 |
| context trickle | 0.01254 | 0.01039 | 0.01016 | 0.00915 | 0.00990 |
| ceiling gbt | 0.02031 | 0.01121 | 0.01017 | 0.00933 | 0.01024 |
| ceiling logistic | 0.02231 | 0.01351 | 0.01105 | 0.01018 | 0.01158 |
| absolute confidence | 0.01645 | 0.01397 | 0.01017 | 0.00919 | 0.01111 |
| random escalation | 0.01678 | 0.01104 | 0.01051 | 0.00949 | 0.01034 |

Every horizon of every arm and budget is in `results/dashcam/ctrl1c/ctrl1c_pooled_d3dev.json` under
`streaming_ap_by_horizon`.

---

## 18. POWER, and the re-labelled Rule 2 classification

For every causal arm and budget: the half-width of the pooled bootstrap CI on the capture
difference against random, and the difference that would be detected with 80 % power at alpha 0.05
given the observed bootstrap variance (`(z_0.975 + z_0.80) * sd`, with `z_0.975 + z_0.80 =
2.8015852`). All figures are in capture-fraction POINTS on the primary metric.

### 18.1 Minimum detectable difference

| budget | arm | difference | CI | CI half-width | bootstrap sd | MDD at 80 % power, alpha 0.05 |
|---|---|---|---|---|---|---|
| 5 % | device filter | -3.3 | [-58.9, +45.4] | 52.2 | 147.2 | 412.5 |
| 5 % | cloud trickle | -15.3 | [-89.0, -1.5] | 43.8 | 63.7 | 178.5 |
| 5 % | context trickle | -13.4 | [-74.7, +1.8] | 38.2 | 39.6 | 110.9 |
| 5 % | ceiling gbt | -3.3 | [-70.2, +39.7] | 54.9 | 42.9 | 120.3 |
| 5 % | ceiling logistic | +37.2 | [-27.0, +372.2] | 199.6 | 690.8 | 1935.2 |
| 5 % | absolute confidence | +23.0 | [-55.7, +168.8] | 112.3 | 80.9 | 226.8 |
| 10 % | device filter | +16.2 | [-27.9, +83.2] | 55.6 | 54.7 | 153.1 |
| 10 % | cloud trickle | +116.8 | [+3.5, +359.0] | 177.7 | 158.3 | 443.4 |
| 10 % | context trickle | +88.1 | [+5.4, +399.6] | 197.1 | 151.5 | 424.4 |
| 10 % | ceiling gbt | +3.5 | [-47.0, +40.8] | 43.9 | 29.3 | 82.0 |
| 10 % | ceiling logistic | +25.7 | [-35.1, +146.6] | 90.8 | 128.1 | 358.8 |
| 10 % | absolute confidence | +23.4 | [-34.8, +183.2] | 109.0 | 68.7 | 192.4 |
| 20 % | device filter | +1.2 | [-115.7, +123.0] | 119.4 | 119.0 | 333.5 |
| 20 % | cloud trickle | +17.9 | [-134.9, +109.1] | 122.0 | 88.3 | 247.4 |
| 20 % | context trickle | +24.6 | [-159.4, +167.0] | 163.2 | 123.9 | 347.1 |
| 20 % | ceiling gbt | -17.5 | [-222.8, +57.1] | 140.0 | 78.7 | 220.5 |
| 20 % | ceiling logistic | +8.9 | [-191.7, +146.5] | 169.1 | 170.2 | 476.9 |
| 20 % | absolute confidence | -24.6 | [-189.8, +23.5] | 106.6 | 80.6 | 225.9 |
| 40 % | device filter | -11.4 | [-84.9, +38.0] | 61.4 | 53.2 | 149.1 |
| 40 % | cloud trickle | -21.2 | [-118.0, +54.2] | 86.1 | 156.6 | 438.7 |
| 40 % | context trickle | -6.4 | [-91.0, +63.1] | 77.1 | 161.3 | 451.8 |
| 40 % | ceiling gbt | -14.2 | [-105.2, +51.4] | 78.3 | 186.9 | 523.6 |
| 40 % | ceiling logistic | -12.9 | [-83.9, +47.5] | 65.7 | 52.9 | 148.3 |
| 40 % | absolute confidence | -21.9 | [-113.5, +34.9] | 74.2 | 140.8 | 394.4 |

**The smallest MDD anywhere in the table is 82 points of capture** (the GBT ceiling at 10 %) and the
median is about 290. The design can detect a difference of roughly one capture-fraction gap or
more, and nothing finer. The smallest CI half-width is 38 points.

### 18.2 Rule 2 re-labelling, OLD against NEW, side by side

The NEW rule, as the user set it: an arm is a **real negative** only if its CI on the difference
against random EXCLUDES differences larger than **10 points of capture** (that is, the CI's upper
bound is at or below +0.10); otherwise it is **inconclusive (underpowered)**. The DESIGN status
(whether the trigger could fire at all) is carried as a third column, because a cell whose trigger
never fires has not tested the claim whatever its power.

| budget | arm | OLD label (first run) | NEW power label | design status under the final primary | net |
|---|---|---|---|---|---|
| 5 % | device filter | real negative | **inconclusive (underpowered)** | exercised | **CHANGED** |
| 5 % | absolute confidence | real negative | **inconclusive (underpowered)** | exercised | **CHANGED** |
| 5 % | ceiling gbt | real negative | **inconclusive (underpowered)** | exercised | **CHANGED** |
| 5 % | ceiling logistic | real negative | **inconclusive (underpowered)** | exercised | **CHANGED** |
| 5 % | cloud trickle | inconclusive by design | real negative (CI upper -1.5) | DEGENERATE in 5 of 5 folds | inconclusive by design, unchanged |
| 5 % | context trickle | inconclusive by design | real negative (CI upper +1.8) | DEGENERATE or INFEASIBLE in 5 of 5 | inconclusive by design, unchanged |
| 10 % | device filter | real negative | **inconclusive (underpowered)** | exercised | **CHANGED** |
| 10 % | absolute confidence | real negative | **inconclusive (underpowered)** | exercised | **CHANGED** |
| 10 % | ceiling gbt | real negative | **inconclusive (underpowered)** | exercised | **CHANGED** |
| 10 % | ceiling logistic | real negative | **inconclusive (underpowered)** | exercised | **CHANGED** |
| 10 % | cloud trickle | real negative | **NOT A NULL: the arm beats random** | live trigger in 5 of 5 folds | **CHANGED** |
| 10 % | context trickle | inconclusive by design | **NOT A NULL on the point estimate, but DEGENERATE in 4 of 5 folds** | DEGENERATE in 4 of 5 | inconclusive by design |
| 20 % | device filter | real negative | **inconclusive (underpowered)** | exercised | **CHANGED** |
| 20 % | absolute confidence | real negative | **inconclusive (underpowered)** | exercised | **CHANGED** |
| 20 % | ceiling gbt | real negative | **inconclusive (underpowered)** | exercised | **CHANGED** |
| 20 % | ceiling logistic | real negative | **inconclusive (underpowered)** | exercised | **CHANGED** |
| 20 % | cloud trickle | real negative | **inconclusive (underpowered)** | exercised | **CHANGED** |
| 20 % | context trickle | partly inconclusive (3 of 5 folds live) | **inconclusive (underpowered)** | live in 3 of 5 folds | **CHANGED** |
| 40 % | device filter | real negative | **inconclusive (underpowered)** | exercised | **CHANGED** |
| 40 % | absolute confidence | real negative | **inconclusive (underpowered)** | exercised | **CHANGED** |
| 40 % | ceiling gbt | real negative | **inconclusive (underpowered)** | exercised | **CHANGED** |
| 40 % | ceiling logistic | real negative | **inconclusive (underpowered)** | exercised | **CHANGED** |
| 40 % | cloud trickle | real negative | **inconclusive (underpowered)** | exercised | **CHANGED** |
| 40 % | context trickle | real negative | **inconclusive (underpowered)** | exercised | **CHANGED** |

**Headline of the re-labelling: NOT ONE causal cell survives as a real negative.** Eighteen cells
move from "real negative" to "inconclusive (underpowered)": the device filter, the absolute-
confidence trigger and both learned ceilings at all four budgets, plus the cloud trickle at 20 and
40 % and the context trickle at 20 and 40 %. Two cells move out of the null category entirely
(the cloud trickle and the context trickle at 10 %, which now beat random). The only two cells
whose CI upper bound does fall below +10 points, the two trickle arms at 5 %, are the two cells
whose trigger cannot fire at all, so they remain INCONCLUSIVE BY DESIGN and their narrow interval
is a property of a background cadence with no trigger, not of a tested trigger.

**What this means for the first run's conclusions.** The first run's section 12 classified four
arms as settled real negatives at every budget. Under the band the user set, that classification
does not hold: the design's minimum detectable difference is 82 to 1,935 capture-fraction points,
so a difference of 10 points could never have been resolved, and the correct Rule 2 reading of
those cells is INCONCLUSIVE (UNDERPOWERED), not a settled finding. This is a design limitation of
the comparison at n = 300 clips in 5 folds, and it is now on the record as one.

---

## 19. StudyE9b corrected capture, beside random, under the final primary

The committed cell is unchanged:
`escalation-32B|32BI_N1|measured@25|cad50|far5|trig{5,10,20,40}|q75|k2|L10|c0` in
`results/dashcam/study_e9b/e9b_study1_results.json`.

### 19.1 The correction, at StudyE9b's own horizon h = 0

| trigger rate | committed capture | reproduced from the raw traces | d3dev calibrated (FINAL PRIMARY) | invocations raw | invocations calibrated |
|---|---|---|---|---|---|
| 5 % | 0.03048 | **0.030498** | **0.11686** | 2,269 | **2,269** |
| 10 % | 0.13311 | **0.133053** | **0.48984** | 4,419 | **4,419** |
| 20 % | 0.12742 | **0.127403** | **0.34158** | 7,562 | **7,562** |
| 40 % | 0.17753 | **0.177544** | **0.37140** | 12,785 | **12,785** |

The invocation counts are identical on the raw and the calibrated scale at every trigger rate,
which is the proof that the decisions are byte-identical: StudyE9b's alarm, dismiss and trigger
thresholds are quantiles of the pooled negative instants, and under ONE per-tier affine map with
a > 0 a quantile maps to the transformed quantile. So **with byte-identical escalation decisions
and byte-identical cloud work, putting the two tiers on one scale raises the measured capture from
3, 13, 13 and 18 % of the gap to 12, 49, 34 and 37 %.** Under the first run's cross-fitted map the
decisions moved (1,803 / 3,704 / 7,174 / 12,755 invocations) and that reading is superseded.

### 19.2 The same arm beside RANDOM, on the primary metric

The comparison the user asked for. StudyE9b's trigger rate is a quantile on negatives, not a call
fraction, so each row is matched to the pre-registered budget whose random arm has the closest
REALIZED call fraction, and the match is reported. References on the primary metric: device-only
0.00995724, always-cloud 0.01327471, gap 0.00332.

| E9b trigger rate | realized call fraction | E9b capture | E9b capture CI | matched random budget | random realized fraction | RANDOM capture | difference | CI | excludes 0 | CI half-width | MDD 80 % | Rule 2 power label |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 5 % | 0.1075 | **+32.4 %** | [+5.7, +136.1] | 10 % | 0.1096 | **+10.2 %** | **+22.1** | [-27.8, +132.5] | no | 80.1 | 149.1 | inconclusive (underpowered) |
| 10 % | 0.2095 | **+9.3 %** | [-35.9, +37.3] | 20 % | 0.2063 | **+43.9 %** | **-34.6** | [-233.5, +24.1] | no | 128.8 | 305.6 | inconclusive (underpowered) |
| 20 % | 0.3584 | **+44.5 %** | [-0.0, +133.2] | 40 % | 0.4056 | **+68.8 %** | **-24.4** | [-126.9, +79.3] | no | 103.1 | 525.8 | inconclusive (underpowered) |
| 40 % | 0.6060 | **+72.0 %** | [+34.8, +154.1] | none | - | - | - | - | - | - | NO MATCHED RANDOM ARM: realized 0.6060 is more than 0.15 above the 40 % budget's random arm at 0.4056, so the pre-registered grid has no comparator |

**So the corrected StudyE9b capture is not distinguishable from random escalation at matched cloud
work at any of the three comparable trigger rates**, and at two of the three the point estimate is
BELOW random. The value the correction reveals is in the SCALE, not in StudyE9b's trigger. The
MDDs, 149 to 526 capture-fraction points, say the comparison could not have resolved anything
smaller.

---

## 20. Results consistency check, 6 of 6, under the final primary

| # | check | outcome |
|---|---|---|
| 1 | cross-check against committed measurements | **PASS, and now with NO exception.** Challenge mAP: device-only 0.4776042449177038 against the committed 0.4776042449177038 (difference 0.0, ratio 1.000) and always-cloud 0.5675307471627266 against 0.5675307471627266 (0.0, ratio 1.000), in BOTH the single-map and the cross-fitted context, because they are the same map. Streaming AP against StudyE9b's committed baselines at every horizon: worst absolute difference 1.7e-18 (device) and 6.9e-18 (cloud). StudyE9b's capture reproduced to 5 significant figures at all four trigger rates (19.1) with identical invocation counts. The positives-only oracle's raw value 0.3910784585 and the raw tier offset -5.124983770601705 against the committed -5.125 both reproduce. Against the FIRST RUN: the one-common-map E9b captures were 0.11644 / 0.48953 / 0.34012 / 0.37065 and are 0.11686 / 0.48984 / 0.34158 / 0.37140 here (ratios 1.004 / 1.001 / 1.004 / 1.002, a different single map with identical decisions), and the one-map positives-only oracle was 0.5725405374 against 0.5703711658 here (ratio 0.996). Every ratio is far inside the 2x bar. The first run's DISAGREEMENT WITH A COMMITTED VALUE, the -0.0251 and -0.0046 shift in the references, is GONE under the final primary: that was the cross-fitting artifact and it is the reason this branch is primary. Fold 0's tunables reproduce with 0 leaf differences (16.3). |
| 2 | physical plausibility | **PASS.** Nothing is timed in this row. Every latency is a committed constant: device cadence 0.75 s and latency 0.567 s, cloud latency 0.3950 s, call cadence 0.50 s, uplink 13.6 Mbit/s, RTT 0.044 s. The one derived rate is the load column, unchanged from section 5: 69.47 ms of H100 step time for a 378-token single-image prefill, about 5,440 prompt tokens per second for an isolated small call, which is SLOWER than the committed large-prefill rates and so is not a caching artifact. No cache of any kind is enabled anywhere in this row: the D3 and D14b traces were both produced with `--no-enable-prefix-caching` and `--mm-processor-cache-gb 0`, and this row re-reads committed files on CPU. |
| 3 | distribution sanity | **PASS, with one spread flagged.** Every capture fraction and every paired difference carries a 2,000-resample CI and, new in this run, a bootstrap sd, CI half-width and MDD (section 18). Episode lengths and call counts are reported as distributions with p25, p50, p75, min and max (17.3). Per-fold values are reported beside the pooled ones (17.2) and they disagree by up to 3.6x: fold 1's device-only streaming AP is 0.02236 against fold 0's 0.00621. FLAGGED: the headline 10 % cloud-trickle result is concentrated in folds 1 and 4 and is small in folds 0, 2 and 3, which is why its CI runs from +3.5 to +359.0 points. The oracle's values repeating across budgets is StudyCTRL1b's CONSTANT lead link (B2c), carried forward with its explanation. No quantity agrees to more precision than its inputs vary. |
| 4 | definition audit | **PASS, with one NEW object declared and no name reused.** Unchanged and verified identical to the committed definitions: the challenge metric (`study_e9d_delay.Challenge`, horizons 0.5 / 1.0 / 1.5 s, one crop per clip), AP (`study_e9d_delay.ap_fast`, sklearn absent and a raising stub installed by `metrics._ensure_sklearn_importable`), the delivery model (StudyE9b `held_stream` / `cloud_delivered`, setting measured@25), the streaming AP (StudyE9b `ApEngine`, asserted equal to `metrics.streaming_ap` to 0.0), the 5-fold rule, the call-fraction budget (B1), a "turn" as a decision instant on the 0.5-s cadence, an "episode" as spec 7.7's open-to-close interval, and the two primary / secondary metrics as the first run defined them. NEW: the CALIBRATION SAMPLE is now the StudyD3 Nexar DEV split, 601 clips, 10 event-anchored offsets per clip at 0.5-s spacing within a 5-s neighbourhood of the event, 6,010 rows per tier, clip-level label. That is a DIFFERENT sample from the first run's (the 240 training clips' whole-clip decision instants, about 16,800 rows per fold), and it is named `d3dev` rather than `platt` precisely so the two are never confused; both are in `ctrl1c_calibration.json` under their own keys. The score definition is log(p_yes) in both studies, verified identical to StudyD14b's committed `score` to 0.0. |
| 5 | claim linkage | **PASS.** The headline bears on the v3.1 addendum's open question Q11 (which SH trigger family) and on spec 4.1's u_SH. It SUPPORTS the addendum's requirement that escalation be decided on a calibrated gain rather than a tier's own score, now more strongly than the first run did: the same StudyE9b escalation decisions are worth 4x, 3.7x, 2.7x and 2.1x more measured capture once the tiers share a scale, with the decisions byte-identical and the invariance holding to machine zero. On Q11 it now returns a RECOMMENDED FAMILY under the pre-registered rule (section 21), where the first run returned none, and the change is attributable to the calibration branch alone, since folds, arms, budgets, cadences and metrics are unchanged. It WEAKENS the first run's claim that the trigger families cannot be separated at all, and section 18 weakens the first run's four "real negative" classifications. Nothing measured here is scoped out by FORMULATION.md: no KV moves between tiers, no cross-architecture transfer is measured, no quantity is read from a cache. |
| 6 | proxy validity | **PASS with five proxies declared, one of them new.** NEW: (e) the StudyD3 DEV event-anchored offset sample stands in for the whole-clip decision-instant distribution the ruling asked for ("same decision cadence"). It actually measures the score distribution in a 5-s neighbourhood of the event at 0.5-s spacing. It is VALID for fitting a per-tier score-to-probability map whose job is to align the two tiers' scales, which is what the mechanism needs and what section 21's link C1 measures; it is NOT validated as a map for per-instant probability values far from events, and section 16.2 quantifies the disagreement against a D14b-DEV-fitted map (slopes 2.6 to 3.0x steeper, p = 0.5 crossings 1.10 to 1.56 log units apart, tier offset at the crossing -4.32 against -3.86). Because the deviation is declared and its size is measured, it is reported as a limitation of the map's sharpness and not of the headline. Carried forward unchanged from the first run: (a) the clip-level label as the calibration target, (b) the challenge metric reading one crop per clip, which is why it is the secondary, (c) the learned ceiling's oracle-signed target, (d) the context-modulated trickle's clip-level Nexar metadata standing in for a per-instant visual signal. |

---

## 21. The pre-registered decision rule, and its outcome for Q11 under the FINAL PRIMARY

The rule, quoted from the frozen pre-registration: *an arm beats random at a budget if the pooled
5-fold difference in captured fraction of the always-cloud minus device-only gap (streaming AP
primary) has a bootstrap CI excluding 0. The recommended family for Q11 is the arm with the highest
streaming-AP capture at budgets <= 20 % among those that beat random; if none beats random, say so
plainly.*

**TWO CAUSAL ARMS BEAT RANDOM, BOTH AT THE 10 % BUDGET, AND THE RULE RETURNS A RECOMMENDED FAMILY.**

| arm | budget | streaming capture | difference vs random | CI | trigger live |
|---|---|---|---|---|---|
| **cloud-initiated trickle** | **10 %** | **+127.0 %** | **+116.8** | **[+3.5, +359.0]** | **5 of 5 folds** |
| context-modulated trickle | 10 % | +98.3 % | +88.1 | [+5.4, +399.6] | 1 of 5 folds |

**The recommended family under the rule as written is the CLOUD-INITIATED TRICKLE at a 10 % call
budget** (an 8-s background cadence in all five folds, 105 episodes over the 300 clips, realized
call fraction 0.0999): it has the highest streaming-AP capture at a budget at or below 20 % among
the arms that beat random, and unlike the context-modulated trickle its trigger is live in all five
folds, so the cell is a measurement of the trigger and not of its background cadence.

**Four qualifications, all measured and none of them optional.**

1. The margin is barely resolved. The CI on the difference runs from +3.5 to +359.0 capture-fraction
   points, a half-width of 177.7, and the design's MDD at 80 % power in that cell is 443.4 points.
   The interval excludes zero, which is what the rule asks, and it excludes nothing else.
2. It is concentrated in two folds of five (17.2). In folds 1 and 4 the arm is 2.2x and 2.1x random;
   in folds 0, 2 and 3 the margin is small.
3. It does not appear on the secondary metric. On challenge mAP the same cell is -0.0073 against
   random, CI [-0.0349, +0.0241], that is indistinguishable.
4. It does not hold at the neighbouring budgets. At 5 % the same arm is WORSE than random
   (-15.3 points, CI [-89.0, -1.5]) and its trigger cannot fire at all; at 20 % and 40 % the
   difference is +17.9 and -21.2 with intervals that include zero.

**At every other budget, no causal arm beats random.** At 5 % the cloud trickle's difference
excludes zero in the NEGATIVE direction, with a degenerate trigger. At 20 % and 40 % not one causal
arm's interval excludes zero in either direction. On the SECONDARY metric no causal arm beats random
at any budget. The two non-causal oracles beat random at every budget on the primary, as bounds and
not as policies.

**Rule 2 classification under the final primary.** Per cell, with the band the user set:

* **NOT A NULL:** the cloud-initiated trickle at 10 % (exercised in 5 of 5 folds, beats random) and
  the context-modulated trickle at 10 % (beats random on the point estimate but DEGENERATE in 4 of
  5 folds, so the cell has not tested the trigger and the result is inconclusive by design).
* **INCONCLUSIVE (UNDERPOWERED):** every other causal cell, 18 of them, including all four cells
  the first run called settled real negatives for the device filter, the absolute-confidence trigger
  and the two learned ceilings. Their intervals do not exclude a 10-point difference and the
  design's MDD is 82 points at best.
* **INCONCLUSIVE BY DESIGN:** the cloud trickle at 5 % (degenerate in 5 of 5 folds) and the context
  trickle at 5 % (degenerate in 1 fold, infeasible in 4). The 10-s cadence that fits a 5 % budget
  costs exactly 0.0500 of the decision instants, which IS the budget, so no episode headroom
  remains. Unchanged from the first run, and unchanged by the calibration branch.
* **NO REAL NEGATIVE REMAINS** anywhere in the causal table.

**Mechanism verification under this calibration** is recorded in
`results/dashcam/ctrl1c/ctrl1c_mechanism_d3dev.json`, written at 16:10 BEFORE any pooled number
under this map, and the pooling stage refuses to run without it. All four links are non-zero and
vary as the chain requires: C1 the tier offset falls from **-5.1250 raw to -0.1197 calibrated** over
all training instants, and at the training positives' crop instants from p50 -3.2500 with the cloud
higher in 24.1 % of cases to p50 +0.1242 with the cloud higher in 58.0 % (n = 257); C1 the
positives-only oracle moves from 0.4043 BELOW device-only 0.4951 to 0.5935 ABOVE it; C2 the
training streaming AP moves with the budget (0.013874 / 0.014445 / 0.014430 / 0.015694 against
device-only 0.011750 and always-cloud 0.014528); C3 the extended cadence grid makes 1, 4, 5 and 6
cadences feasible at 5 / 10 / 20 / 40 % against StudyCTRL1b's 0, 0, 1 and 2; C4 the retargeted
signed-gain target has sd 0.6286 and the GBT prediction sd 0.0411. **No link is ABSENT or
CONSTANT.** Step 4's negative control still collapses the result: with the calibration disabled the
positives-only oracle returns to 0.4043 against device-only 0.4951, below it.

---

## 22. Files, second run

| file | what | run |
|---|---|---|
| `results/dashcam/ctrl1c/ctrl1c_calibration.json` | unchanged; `single_map.d3dev` holds the two maps the final primary uses, and `d3dev_note` states why they need no cross-fitting | first run |
| `results/dashcam/ctrl1c/ctrl1c_fits_d3dev.json` | the per-fold tunables under the d3dev map; fold 0 verified by refitting from scratch with 0 leaf differences | second run |
| `results/dashcam/ctrl1c/ctrl1c_mechanism_d3dev.json` | mechanism verification Steps 1 to 5 under the d3dev map, written before any pooled number | second run |
| `results/dashcam/ctrl1c/ctrl1c_pooled_d3dev.json` | **THE FINAL PRIMARY**: capture tables, both metrics, per-horizon, per-fold, episode statistics, the power block per arm and budget, and the four sanity checks | second run |
| `results/dashcam/ctrl1c/ctrl1c_e9b_recheck_d3dev.json` | the StudyE9b correction under the d3dev map, three scales, four trigger rates, invocation counts | second run |
| `results/dashcam/ctrl1c/ctrl1c_e9b_vs_random_d3dev.json` | the StudyE9b arm beside the matched random arm, with the difference, its CI, half-width, MDD and Rule 2 power label | second run |
| `results/dashcam/ctrl1c/ctrl1c_load_column.json` | the DERIVED load column, re-written unchanged | both |
| `experiments/dashcam/ctrl1c_crossfit.py` | the study; the second run adds the d3dev branch of sanity check (c) and of the check_a explanation, and nothing else | both |
| `experiments/dashcam/ctrl1c_calibrate.py` | the calibration; `fit_maps_d3dev` and `d3_dev_sample` are the final primary's map | first run |
| `experiments/dashcam/ctrl1c_metrics.py` | the primary metric, the paired bootstrap, the capture difference, and the power block (`Z_SUM_80`, `RULE2_BAND = 0.10`) | first run |
| `results/dashcam/ctrl1c/ctrl1c_pooled_platt.json`, `ctrl1c_fits_platt.json`, `ctrl1c_mechanism_platt.json`, `ctrl1c_e9b_recheck_platt.json` | the FIRST RUN's fully cross-fitted reading, now a LABELLED SENSITIVITY | first run |
| `results/dashcam/ctrl1c/ctrl1c_pooled_isotonic.json`, `ctrl1c_fits_isotonic.json`, `ctrl1c_pooled_platt_instant.json`, `ctrl1c_fits_platt_instant.json` | the first run's two alternative calibrations, sensitivities (section 9) | first run |

Imported and NOT edited: `experiments/dashcam/ctrl1b_crossfit.py`, `ctrl1b_learned.py`,
`d14b_folds.py`, `ctrl1_controller.py`, `d14b_split.py`,
`experiments/orchestration/sim/metrics.py`, `experiments/dashcam/study_e9b_dense.py`,
`study_e9_episodes.py`, `study_e9d_delay.py`.
