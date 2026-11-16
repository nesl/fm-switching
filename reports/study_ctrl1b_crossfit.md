# StudyCTRL1b-crossfit: the trigger comparison, cross-fitted on all 300 clips

Pre-registered in `research/EXPERIMENTS.md` (StudyCTRL1b-crossfit) before anything was computed, including the fold rule, the budget metric and the objective; amendment 1 (the v3.1 addendum's two extra arms) was recorded there before those arms were computed too. CPU only on flash: no GPU, no model server, no inference, no scikit-learn. Every score is a committed StudyD14b trace.

**StudyCTRL1-episodes' 90/210 results are SUPERSEDED, not deleted.** They remain in `results/dashcam/ctrl1/` and `reports/study_ctrl1_episodes.md`, and section 2 says exactly what changed.

**One sentence.** With every clip scored held out, the gap the triggers compete for is 0.0899 challenge mAP (always-cloud 0.5675 against device-only 0.4776) and the pooled 300-clip design resolves it for the first time; but the row's largest finding is not a capture fraction, it is that THE TWO TIERS' SCORES ARE NOT ON A COMMON SCALE, so a trigger whose firing correlates with the label moves this rank metric through the scale offset alone, which is why the brief's positives-only oracle scores BELOW device-only while the same perfect timing applied to every clip's crop sits far above it.

---

## 1. The design

* **Folds.** within each label stratum, order by sha256(file_name) hex; fold = rank mod 5; pre-registered in research/EXPERIMENTS.md (StudyCTRL1b-crossfit) before any computation
* Five folds of 60 clips, each 30 positive and 30 negative, so the challenge metric's base rate is identical across folds. Fold durations 2267, 2244, 2336, 2228, 2286 s.
* **Cross-fitting.** Every tunable is chosen on the four training folds and applied unchanged to the held-out fold: the controller's (W_c, delta, n_c, K_c, instability mode, theta), the absolute-confidence tau, the random opening probability, the cloud-initiated cadence and threshold, the oracle lead, the two learned models and their thresholds, and the context-modulated trickle's cadence, context feature and threshold. The pooled result concatenates the five held-out folds, so each clip is scored under settings fitted without it.
* **The objective is unchanged** from StudyCTRL1: maximize the training folds' challenge mAP of escalation-only at a fixed escalation budget.

## 2. What changed from the 90/210 split, and what that costs

| | StudyCTRL1-episodes | StudyCTRL1b-crossfit |
|---|---|---|
| clips fitted on | 90 DEV | 240 per fold |
| clips reported on | 210 EVAL | 300, every one held out |
| budget metric | fraction of device-time with an OPEN EPISODE | total cloud CALLS divided by decision instants on the 0.5-s cadence |
| arms | 5 | 11 |
| always-cloud minus device-only | +0.0598, CI -0.0076 to +0.1395 (could not resolve the denominator) | +0.0899, CI [+0.0357, +0.1497] |

**Why the budget metric had to change (B1).** StudyCTRL1 charged an arm the fraction of device-time with an open episode. That cannot price the cloud-initiated arm, whose background samples occupy no episode at all, so the pre-registered metric here is the call fraction, in which a background sample and an episode follow-up cost the same because each is one cloud call. The open-time fraction is still computed and reported for every arm, so the two definitions can be compared directly; the consequence is that this row's 5 / 10 / 20 / 40 % levels are NOT interchangeable with StudyCTRL1's, and no number is carried across.

## 3. KEY TABLE: what each trigger captures of the always-cloud gap

The capture fraction is (arm minus device-only) divided by (always-cloud minus device-only), with the CI taken over the SAME 2,000 paired clip resamples (seed 0) as the arms themselves, so the numerator and denominator move together. All 300 clips, every one held out.

### Budget 5 % of the call rate

| arm | capture % | CI % | challenge mAP | realized call fraction | open-time fraction | calls on positives / on negatives |
|---|---|---|---|---|---|---|
| device filter (spec 7.7) | -1.6 | [-34.2, +21.0] | 0.4762 | 0.0450 | 0.0509 | 0.97 |
| oracle trigger, positives only (NON-CAUSAL) **NON-CAUSAL** | -96.2 | [-297.3, -41.4] | 0.3911 | 0.0508 | 0.0546 | n/a |
| oracle timing bound, every crop (NON-CAUSAL) **NON-CAUSAL** | +79.9 | [+52.7, +100.5] | 0.5495 | 0.0508 | 0.0581 | 0.75 |
| cloud trickle | +0.0 | [+0.0, +0.0] | 0.4776 | 0.0000 | 0.0000 | n/a |
| context-modulated trickle | +0.0 | [+0.0, +0.0] | 0.4776 | 0.0000 | 0.0000 | n/a |
| predictability ceiling, boosted trees (LEARNED) **LEARNED CEILING** | +8.9 | [-0.5, +31.2] | 0.4856 | 0.0422 | 0.0452 | 0.37 |
| predictability ceiling, logistic (LEARNED) **LEARNED CEILING** | +8.0 | [+0.6, +26.9] | 0.4848 | 0.0383 | 0.0403 | 0.46 |
| absolute-confidence trigger | +11.4 | [-28.5, +44.0] | 0.4878 | 0.0507 | 0.0550 | 1.34 |
| random escalation | -4.2 | [-33.6, +8.6] | 0.4738 | 0.0547 | 0.0623 | 1.49 |
| device-only (reference) | 0.0 | - | 0.4776 | 0.0000 | 0.0000 | - |
| always-cloud (reference) | 100.0 | - | 0.5675 | 1.0000 | 1.0000 | 1.00 |

The cloud-initiated arm is INFEASIBLE at this budget in 5 of 5 folds: the cheapest background cadence the brief specifies, 4 s, already costs 0.1250 of the decision instants, and 1 s and 2 s cost 0.5000 and 0.2500. A budget below the floor cannot be met by any threshold, so the arm is reported as infeasible rather than run over budget. Reaching 5 % would need a background cadence of about 10 s and 10 % about 5 s, neither of which is in the pre-registered grid; adding them would be a methodological change beyond the brief and is not done here.

### Budget 10 % of the call rate

| arm | capture % | CI % | challenge mAP | realized call fraction | open-time fraction | calls on positives / on negatives |
|---|---|---|---|---|---|---|
| device filter (spec 7.7) | +16.8 | [-9.0, +46.0] | 0.4927 | 0.1033 | 0.1175 | 0.96 |
| oracle trigger, positives only (NON-CAUSAL) **NON-CAUSAL** | -96.2 | [-297.3, -41.4] | 0.3911 | 0.0997 | 0.1037 | n/a |
| oracle timing bound, every crop (NON-CAUSAL) **NON-CAUSAL** | +79.9 | [+52.7, +100.5] | 0.5495 | 0.1043 | 0.1119 | 0.85 |
| cloud trickle | +0.0 | [+0.0, +0.0] | 0.4776 | 0.0000 | 0.0000 | n/a |
| context-modulated trickle | +0.0 | [+0.0, +0.0] | 0.4776 | 0.0000 | 0.0000 | n/a |
| predictability ceiling, boosted trees (LEARNED) **LEARNED CEILING** | +7.1 | [-10.7, +27.9] | 0.4840 | 0.0856 | 0.0896 | 0.44 |
| predictability ceiling, logistic (LEARNED) **LEARNED CEILING** | +7.0 | [-6.5, +26.8] | 0.4839 | 0.0908 | 0.0932 | 0.40 |
| absolute-confidence trigger | +24.5 | [-9.3, +68.0] | 0.4997 | 0.0999 | 0.1082 | 1.35 |
| random escalation | +11.0 | [-14.9, +36.4] | 0.4875 | 0.1068 | 0.1236 | 1.24 |
| device-only (reference) | 0.0 | - | 0.4776 | 0.0000 | 0.0000 | - |
| always-cloud (reference) | 100.0 | - | 0.5675 | 1.0000 | 1.0000 | 1.00 |

The cloud-initiated arm is INFEASIBLE at this budget in 5 of 5 folds: the cheapest background cadence the brief specifies, 4 s, already costs 0.1250 of the decision instants, and 1 s and 2 s cost 0.5000 and 0.2500. A budget below the floor cannot be met by any threshold, so the arm is reported as infeasible rather than run over budget. Reaching 5 % would need a background cadence of about 10 s and 10 % about 5 s, neither of which is in the pre-registered grid; adding them would be a methodological change beyond the brief and is not done here.

### Budget 20 % of the call rate

| arm | capture % | CI % | challenge mAP | realized call fraction | open-time fraction | calls on positives / on negatives |
|---|---|---|---|---|---|---|
| device filter (spec 7.7) | +24.2 | [-5.7, +60.0] | 0.4994 | 0.2122 | 0.2393 | 0.97 |
| oracle trigger, positives only (NON-CAUSAL) **NON-CAUSAL** | -96.2 | [-297.3, -41.4] | 0.3911 | 0.1995 | 0.2039 | n/a |
| oracle timing bound, every crop (NON-CAUSAL) **NON-CAUSAL** | +79.9 | [+52.7, +100.5] | 0.5495 | 0.2022 | 0.2102 | 0.92 |
| cloud trickle | +14.2 | [-16.3, +43.3] | 0.4904 | 0.2005 | 0.0770 | 1.30 |
| context-modulated trickle | +10.9 | [-21.4, +38.5] | 0.4874 | 0.2037 | 0.0353 | 1.13 |
| predictability ceiling, boosted trees (LEARNED) **LEARNED CEILING** | +24.9 | [+5.4, +65.7] | 0.5000 | 0.1946 | 0.1997 | 0.48 |
| predictability ceiling, logistic (LEARNED) **LEARNED CEILING** | +28.8 | [+4.6, +70.7] | 0.5035 | 0.2121 | 0.2150 | 0.50 |
| absolute-confidence trigger | +5.8 | [-60.4, +38.5] | 0.4828 | 0.1980 | 0.2120 | 1.31 |
| random escalation | +15.7 | [-16.3, +47.6] | 0.4917 | 0.2014 | 0.2291 | 1.10 |
| device-only (reference) | 0.0 | - | 0.4776 | 0.0000 | 0.0000 | - |
| always-cloud (reference) | 100.0 | - | 0.5675 | 1.0000 | 1.0000 | 1.00 |

### Budget 40 % of the call rate

| arm | capture % | CI % | challenge mAP | realized call fraction | open-time fraction | calls on positives / on negatives |
|---|---|---|---|---|---|---|
| device filter (spec 7.7) | +49.9 | [+10.3, +91.9] | 0.5225 | 0.3977 | 0.4409 | 0.99 |
| oracle trigger, positives only (NON-CAUSAL) **NON-CAUSAL** | -96.2 | [-297.3, -41.4] | 0.3911 | 0.2246 | 0.2292 | n/a |
| oracle timing bound, every crop (NON-CAUSAL) **NON-CAUSAL** | +79.9 | [+52.7, +100.5] | 0.5495 | 0.3996 | 0.4084 | 1.02 |
| cloud trickle | +44.4 | [+11.4, +101.6] | 0.5175 | 0.3989 | 0.3052 | 1.31 |
| context-modulated trickle | +37.5 | [+3.6, +88.9] | 0.5113 | 0.3992 | 0.2409 | 1.21 |
| predictability ceiling, boosted trees (LEARNED) **LEARNED CEILING** | +30.3 | [+2.0, +71.1] | 0.5049 | 0.3867 | 0.3963 | 0.58 |
| predictability ceiling, logistic (LEARNED) **LEARNED CEILING** | +36.9 | [+9.6, +84.1] | 0.5108 | 0.3887 | 0.3925 | 0.58 |
| absolute-confidence trigger | +56.6 | [+10.1, +93.9] | 0.5285 | 0.3974 | 0.4160 | 1.26 |
| random escalation | +36.7 | [+1.2, +77.4] | 0.5106 | 0.4106 | 0.4579 | 1.01 |
| device-only (reference) | 0.0 | - | 0.4776 | 0.0000 | 0.0000 | - |
| always-cloud (reference) | 100.0 | - | 0.5675 | 1.0000 | 1.0000 | 1.00 |

### 3.1 What the table says, read off the intervals

Only these arms have a capture-fraction interval that EXCLUDES ZERO at any budget, which is the only statement the design supports about a single arm:

* `oracle-trigger` at 5 %, 10 %, 20 %, 40 %
* `oracle-timing-bound` at 5 %, 10 %, 20 %, 40 %
* `ceiling-logistic` at 5 %, 20 %, 40 %
* `ceiling-gbt` at 20 %, 40 %
* `escalation-only` at 40 %
* `cloud-initiated` at 40 %
* `context-trickle` at 40 %
* `absolute-confidence` at 40 %
* `random-escalation` at 40 %

Everything else is indistinguishable from capturing nothing. In particular, the paired differences that matter for the brief's question are these, at the 20 % budget:

| comparison | difference in challenge mAP | CI | excludes zero |
|---|---|---|---|
| escalation-only minus random-escalation | +0.0076 | [-0.0212, +0.0364] | no |
| ceiling-gbt minus random-escalation | +0.0082 | [-0.0266, +0.0381] | no |
| ceiling-logistic minus random-escalation | +0.0117 | [-0.0241, +0.0436] | no |
| cloud-initiated minus random-escalation | -0.0013 | [-0.0326, +0.0272] | no |
| context-trickle minus random-escalation | -0.0043 | [-0.0382, +0.0250] | no |
| absolute-confidence minus random-escalation | -0.0089 | [-0.0490, +0.0262] | no |
| oracle-timing-bound minus random-escalation | +0.0577 | [+0.0122, +0.1034] | yes |
| ceiling-gbt minus escalation-only | +0.0006 | [-0.0290, +0.0270] | no |
| oracle-timing-bound minus oracle-trigger | +0.1584 | [+0.1227, +0.2008] | yes |
| always-cloud minus device-only | +0.0899 | [+0.0357, +0.1497] | yes |

**So the device filter is still not measurably better than spending the same budget at random**, which is the same verdict StudyCTRL1 reached on 210 clips, now reached on 300 with the denominator resolved. What the 300-clip design adds is the arm that IS separable: perfect timing, applied to every clip's crop instant, captures +80 % (CI +53 to +101) of the gap at the 20 % budget, so the headroom exists and no causal trigger here reaches it.

**The single sentence the addendum's Q11 should be decided on.** NOT ONE CAUSAL TRIGGER BEATS RANDOM ESCALATION AT THE SAME BUDGET on this workload: the device filter, the cloud trickle, the context-modulated trickle, the absolute-confidence trigger and even the LEARNED CEILING all have differences against random whose intervals span zero. The learned ceiling is the informative one, because it is fitted on an oracle-signed target with a flexible model and still only matches the hand-built device filter (`ceiling-gbt minus escalation-only` +0.0006, CI -0.0290 to +0.0270): on the features a device actually has, there is very little signal left to extract, and choosing among trigger FAMILIES is not where this workload's headroom lies. The headroom is real (the non-causal timing bound reaches it) and it sits behind calibration and budget, not behind a cleverer trigger.

## 4. The finding that reorders the row: the two tiers are not on one scale

Over the training clips the 32B's raw log P(Yes) runs BELOW the 4B's at every percentile: cloud p05 / p50 / p95 = -23.125 / -16.125 / -2.579 against device -18.250 / -11.000 / -1.910, a median offset of -5.125 log units.

At the crop instants of training positives the cloud's score is a median -3.2500 BELOW the device's displayed score and is higher in only 24.1 % of cases. The challenge metric ranks crops ACROSS clips, so substituting cloud scores on the positives only pushes the positives down the ranking: the arm is penalized for escalating correctly.

The control isolates it, holding the timing fixed and removing only the label correlation of the spending:

| budget | oracle, positives only | oracle, every crop | device-only | always-cloud |
|---|---|---|---|---|
| 5 % | 0.4042 | 0.4179 | 0.4951 | 0.5468 |
| 10 % | 0.4042 | 0.4444 | 0.4951 | 0.5468 |
| 20 % | 0.4042 | 0.4582 | 0.4951 | 0.5468 |
| 40 % | 0.4042 | 0.4667 | 0.4951 | 0.5468 |

**What this means for the brief's oracle.** The brief asks for an arm that escalates "exactly over the challenge-horizon windows before each positive event" AND is "an upper bound on any trigger at that budget". On this metric those two requirements are incompatible, and the incompatibility is measured, not argued. Both readings are therefore reported: `oracle-trigger` is the brief's literal arm and `oracle-timing-bound` is the same placement extended to every clip's crop instant, which is the arm that actually bounds timing. Nothing is hidden by this; the literal arm's number is in every table above.

**And for the policy.** This is direct evidence for spec 4.1 as the addendum reads it: u_SH must be a CALIBRATED utility, never a raw tier score. StudyPOL2-build's library reads u_SH from the DEV table for exactly this reason, and `utility.u_sh_cloud` has no path that accepts a score.

**A second structural property, also the metric's and not the arms'.** The oracle's value is EXACTLY invariant to its lead extension: the crop instant is served by the same call whatever the lead, and the challenge metric reads no other instant. The mechanism verification records that link as CONSTANT and the oracle is therefore one number rather than a budget curve, which is also why its budget matching is cosmetic.

## 5. Mechanism verification, Steps 1 to 5

Recorded on TRAINING folds only and BEFORE any pooled number was written; the pooling stage refuses to run without `ctrl1b_mechanism.json` on disk.

### 5.1 The two triggers of the first brief

**Step 1, the chains.** Oracle: If a cloud answer delivered AT a challenge crop instant carries a better-separating score than the device's own held sample at that instant (StudyE9c measured the pooled separation: 32B 0.5675 against 4B 0.4776 over all 300 clips), then placing calls so that each positive clip's crop instants are served by a cloud delivery, and spending nothing on negatives, must capture at least as much of the always-cloud minus device-only gap as any causal trigger at the same budget. The oracle therefore bounds TIMING: whatever remains uncaptured at a given budget cannot be recovered by a better trigger, only by a better cloud answer or by more budget.

Cloud-initiated: If the cloud's own 32B score at a background cadence c carries the approach of an event (the same signal StudyD14b measured on the 4B, on a stronger model), then background sampling at cadence c detects it, an episode opened at the 0.5-s cadence covers the crop instants that follow, and the delivered 32B scores replace the device's at those instants, raising challenge mAP. The cost is paid twice over, in background samples and in episode calls, so the arm is only worth it if the detection is sharp enough that the episodes land where they matter.

**Step 2, the links.**

| arm | link | varies? | evidence |
|---|---|---|---|
| oracle-trigger | oracle placement -> a cloud delivery at the crop instant | varies | the oracle serves every crop instant it is defined on, the fitted controller a minority of them, so the quantity separates the arms |
| oracle-trigger | lead extension -> budget -> metric | CONSTANT in the metric | the call fraction rises monotonically with the lead, but the metric is EXACTLY CONSTANT across it (spread 0.00e+00): the crop instant is served by the same call whatever the lead and the challenge metric reads no other instant. Per CLAUDE.m |
| oracle-trigger | cloud answer -> a better score AT the crop instant | varies | the cloud's score at the instant the oracle serves differs from the device's, so perfect timing has something to deliver; its SIGN is what decides whether the bound is above or below device-only |
| both new arms | tier score scale -> rank metric | varies | the two tiers are NOT on a common scale, so any arm whose calls are label-correlated moves the rank metric through the scale offset alone. This link is the reason the oracle has two readings (B2b) and it bears directly on spec 4.1: u_SH mus |
| cloud-initiated | background cloud score -> episode trigger | varies | the trigger count falls as tau rises, so the threshold is a live knob |
| cloud-initiated | episode -> displayed score -> challenge mAP | varies | both move with the budget where the arm is feasible |

**Step 3** traces one oracle episode and one cloud-initiated episode in `ctrl1b_mechanism.json`, with the window arithmetic, the triggering background sample, its read time, every call time and the displayed score at each crop.

**Step 4, two controls.** The label-correlation control is section 4. The second holds the cloud-initiated arm's sampling fixed and disables only its trigger:

| budget | with the trigger | background only | device-only | episodes worth |
|---|---|---|---|---|
| 5 % | INFEASIBLE | - | - | - |
| 10 % | INFEASIBLE | - | - | - |
| 20 % | 0.4971 | 0.4923 | 0.4951 | +0.0047 |
| 40 % | 0.5169 | 0.4923 | 0.4951 | +0.0246 |

**Step 5, the alternative explanation.** For the ORACLE the competing explanation is the same one StudyCTRL1 could not rule out: that any cloud call at all helps because the cloud PATH is fresher than the device's 0.75-s held samples, not because the call is well placed. The control in Step 4 separates them directly by running the oracle's own call pattern with the device's own scores. For the CLOUD-INITIATED arm the competing explanation is that its benefit is entirely the background sampling, which upgrades the display every c seconds whether or not an episode ever opens; the trigger-disabled control separates those two. A third explanation covers both arms and cannot be separated within this study: the challenge metric reads ONE crop per clip, so an arm that happens to deliver a cloud score at that one instant is credited with the whole clip, and 300 clips carry 300 such instants. That is a property of the committed metric, not of the arms, and it is why the oracle is reported as a bound on timing rather than as an achievable policy.

### 5.2 The two arms of the addendum

**Step 1.** Ceiling: If the per-instant cloud gain is predictable from features a device already has, then a model fitted on the training folds predicts it on the held-out fold, escalating at the instants of highest predicted gain captures more of the always-cloud minus device-only gap than a rule that does not look at those features, and the capture fraction it reaches is a CEILING on what any trigger built from the same features could reach.

Context-modulated trickle: If a cheap context signal marks streams whose cloud gain is higher, then spending the same budget at a doubled background cadence on those streams and the base cadence elsewhere captures more of the gap than a uniform cadence does.

**Step 2, the links.**

| arm | link | varies? | evidence |
|---|---|---|---|
| ceiling | device-observable features -> the per-instant cloud gain | yes | the prediction varies across instants and tracks the target to the stated r2; a flat prediction would make the arm identical to random at the same budget |
| ceiling | predicted gain -> episodes -> challenge mAP | yes | the threshold is a live budget knob and the metric moves with it |
| context-trickle | context signal -> background cadence | yes | the modulation fires on a proper subset of the clips, so the arm differs from arm (b) at both cadences |

**Step 4, the permuted-target control**, which is the only control that can falsify a LEARNED arm: the same model class, the same episode machinery and the same budget, fitted on a shuffled target (seed 0), so only the feature-to-gain relation is destroyed.

| budget | ceiling, real target | ceiling, permuted target | device-only | always-cloud |
|---|---|---|---|---|
| 5 % | 0.5050 | 0.4929 | 0.4951 | 0.5468 |
| 10 % | 0.5125 | 0.5006 | 0.4951 | 0.5468 |
| 20 % | 0.5082 | 0.4988 | 0.4951 | 0.5468 |
| 40 % | 0.5227 | 0.5099 | 0.4951 | 0.5468 |

**Step 5.** The ceiling's apparent gain could come from (a) the features genuinely predicting where the cloud helps [the claimed mechanism], or (b) the arm simply spending its budget in a different TEXTURE, for instance in many short episodes rather than few long ones, which changes freshness without any targeting. The permuted-target control separates these: it keeps the model class, the episode machinery and the budget and removes only the signal. The random-escalation arm at the same budget is the second comparator. A third explanation cannot be separated here and is stated with the number: the ceiling is fitted on a target DEFINED using the clip label's sign (B8), so it is an upper bound available to an oracle-signed objective and not a deployable policy, which is why the brief labels it a ceiling.

## 6. The predictability ceiling: what is predictable, and from what

Fitted per fold on the training folds' device samples (11054 rows in fold 0), predicting the SIGNED per-instant cloud gain (B8): the cloud's score at the instant minus the device's displayed score, times +1 on a positive clip and -1 on a negative one. The models never see the label.

| fold | boosted-tree train r2 | logistic train AUC | strongest features (boosted trees) |
|---|---|---|---|
| 0 | 0.0419 | 0.6184 | `scene_urban` 0.40, `scene_sub_urban` 0.25, `window_iqr` 0.07 |
| 1 | 0.0228 | 0.5855 | `scene_urban` 0.31, `window_median` 0.17, `window_iqr` 0.14 |
| 2 | 0.0358 | 0.6098 | `scene_sub_urban` 0.40, `window_iqr` 0.13, `rolling_mean4` 0.10 |
| 3 | 0.0333 | 0.6044 | `scene_sub_urban` 0.59, `scene_urban` 0.19, `window_median` 0.05 |
| 4 | 0.0290 | 0.5960 | `scene_sub_urban` 0.31, `scene_urban` 0.22, `weather_clear` 0.11 |

**What the features could NOT be, declared rather than substituted.** The brief asks for simple image features and, if it exists, ego speed.

| feature family | status |
|---|---|
| `image_scene_change_magnitude` | THE FRAME STORE IS ABSENT on this machine (/home/pragya/data/dashcam/d14b_frames does not exist), so no inter-frame feature is computable and none is estimated |
| `object_count` | no frames to detect on, and opencv is not installed either; no detector was installed because there is nothing for it to read |
| `ego_speed` | DOES NOT EXIST in the committed Nexar clip table, whose columns are file_name, label, scene, light, weather, duration_s and split |
| `elapsed_time_in_clip` | EXCLUDED BY DECISION: Nexar events sit at a characteristic position in each clip, so the clock would leak the dataset's event placement rather than provide a deployable signal |

So this is a ceiling on SCORE-DYNAMICS-AND-CONTEXT predictability, and NOT a ceiling on what visual features could add. Closing that gap needs the frame store restored to this machine; nothing else about the arm would change.

## 7. The context-modulated trickle

The context signal is the strongest NON-SCORE feature by the training folds' own boosted-tree importance. Its threshold rule (B9): 0.5 for a BINARY feature, the training-fold MEDIAN for a continuous one; neither is fitted to the outcome. The median alone DEGENERATES on a one-hot feature whose category covers more than half the rows (its median is then 1.0 and the test v > threshold never fires), which the mechanism verification caught as a CONSTANT link before any pooled number was written; see the report's section on arm (e). Fold 0 chose `scene_urban` (importance 0.3956). Every available non-score feature is CLIP-LEVEL Nexar metadata, so the modulation is per clip; with the frame store present it would be a per-instant visual signal.

**Mechanism verification changed this arm before any pooled number existed.** The first threshold rule was the training-fold MEDIAN of the chosen feature. On a one-hot feature whose category covers more than half the clips, the median is 1.0 and the strict test never fires, so the arm was byte-for-byte identical to arm (b): Step 2 recorded the link context-signal-to-cadence as CONSTANT, which CLAUDE.md makes a stopping condition. The rule was corrected to 0.5 for a BINARY feature and the median for a continuous one, neither fitted to the outcome, and the arm re-run. The degenerate version is not reported as a result.

| fold | context feature chosen | threshold | boosted-tree importance |
|---|---|---|---|
| 0 | `scene_urban` | 0.500 | 0.3956 |
| 1 | `scene_urban` | 0.500 | 0.3068 |
| 2 | `scene_sub_urban` | 0.500 | 0.3954 |
| 3 | `scene_sub_urban` | 0.500 | 0.5946 |
| 4 | `scene_sub_urban` | 0.500 | 0.3116 |

## 8. Episodes, and what the triggers actually do with their budget

| budget | arm | escalations per device-minute | p50 episode length (s) | p50 calls | false episodes per minute on negatives |
|---|---|---|---|---|---|
| 5 % | escalation-only | 1.51 | 2.25 | 4.0 | 1.54 |
| 5 % | ceiling-gbt | 0.95 | 2.25 | 4.0 | 1.38 |
| 5 % | absolute-confidence | 1.25 | 2.25 | 4.0 | 1.09 |
| 5 % | random-escalation | 2.02 | 2.25 | 4.0 | 1.61 |
| 5 % | oracle-timing-bound | 1.71 | 2.25 | 4.0 | 1.76 |
| 10 % | escalation-only | 3.64 | 1.75 | 3.0 | 3.67 |
| 10 % | ceiling-gbt | 1.59 | 3.25 | 7.0 | 2.17 |
| 10 % | absolute-confidence | 2.60 | 2.25 | 4.0 | 2.24 |
| 10 % | random-escalation | 4.50 | 1.25 | 2.0 | 4.10 |
| 10 % | oracle-timing-bound | 1.71 | 4.25 | 8.0 | 1.76 |
| 20 % | escalation-only | 7.27 | 1.75 | 3.0 | 7.41 |
| 20 % | cloud-initiated | 1.67 | 2.25 | 4.0 | 1.14 |
| 20 % | context-trickle | 0.73 | 2.75 | 5.0 | 0.45 |
| 20 % | ceiling-gbt | 3.15 | 5.25 | 10.0 | 4.37 |
| 20 % | absolute-confidence | 4.73 | 2.25 | 4.0 | 4.28 |
| 20 % | random-escalation | 7.63 | 1.75 | 3.0 | 7.28 |
| 20 % | oracle-timing-bound | 1.71 | 7.75 | 15.0 | 1.76 |
| 40 % | escalation-only | 12.17 | 2.25 | 4.0 | 12.11 |
| 40 % | cloud-initiated | 5.26 | 3.75 | 7.0 | 4.51 |
| 40 % | context-trickle | 4.77 | 2.75 | 5.0 | 4.03 |
| 40 % | ceiling-gbt | 6.24 | 5.25 | 10.0 | 7.69 |
| 40 % | absolute-confidence | 7.70 | 3.00 | 6.0 | 6.91 |
| 40 % | random-escalation | 14.25 | 2.25 | 4.0 | 14.05 |
| 40 % | oracle-timing-bound | 1.71 | 15.25 | 30.0 | 1.76 |

## 9. The negative control, recomputed under cross-fitting

Replacing the cloud's score with the device's OWN score, while keeping the escalation pattern and the cloud path (calls every 0.50 s delivered after 0.395 s), separates what an escalation buys into PATH FRESHNESS and CLOUD SCORE QUALITY. Computed on the held-out clips, not on the fitted ones.

| budget | escalation-only | device scores through the cloud path | device-only | freshness share | score-quality share |
|---|---|---|---|---|---|
| 5 % | 0.4762 | 0.4747 | 0.4776 | +202 % | -102 % |
| 10 % | 0.4927 | 0.4795 | 0.4776 | +12 % | +88 % |
| 20 % | 0.4994 | 0.4860 | 0.4776 | +39 % | +61 % |
| 40 % | 0.5225 | 0.4852 | 0.4776 | +17 % | +83 % |

## 10. StudyFRAMES1 re-run on all 300 clips

StudyFRAMES1 re-run on all 300 clips: the pooled matched-delay curve (no tunable, so pooling is the whole gain) and a genuine cross-fitted CHOOSE-N object (B6).

| tier | delay (s) | pooled N3 minus N1 | CI | excludes zero | folds choosing N=3 | cross-fitted choose-N gain | CI |
|---|---|---|---|---|---|---|---|
| 32BI | 0.00 | -0.0041 | [-0.0637, +0.0530] | no | 2 of 5 | -0.0003 | [-0.0280, +0.0279] |
| 32BI | 0.50 | +0.0061 | [-0.0518, +0.0571] | no | 3 of 5 | +0.0039 | [-0.0362, +0.0430] |
| 32BI | 1.00 | +0.0099 | [-0.0390, +0.0605] | no | 3 of 5 | +0.0041 | [-0.0336, +0.0442] |
| 32BI | 1.50 | -0.0092 | [-0.0573, +0.0375] | no | 3 of 5 | -0.0097 | [-0.0476, +0.0256] |
| 32BI | 2.00 | -0.0202 | [-0.0711, +0.0259] | no | 0 of 5 | +0.0000 | [+0.0000, +0.0000] |
| 32BI | 3.00 | -0.0254 | [-0.0730, +0.0152] | no | 0 of 5 | +0.0000 | [+0.0000, +0.0000] |
| 4BI | 0.00 | +0.0003 | [-0.0528, +0.0482] | no | 3 of 5 | -0.0060 | [-0.0475, +0.0351] |
| 4BI | 0.50 | -0.0064 | [-0.0563, +0.0376] | no | 2 of 5 | +0.0013 | [-0.0382, +0.0378] |
| 4BI | 1.00 | -0.0149 | [-0.0650, +0.0287] | no | 1 of 5 | -0.0103 | [-0.0403, +0.0182] |
| 4BI | 1.50 | -0.0222 | [-0.0725, +0.0198] | no | 0 of 5 | +0.0000 | [+0.0000, +0.0000] |
| 4BI | 2.00 | -0.0139 | [-0.0581, +0.0242] | no | 0 of 5 | +0.0000 | [+0.0000, +0.0000] |
| 4BI | 3.00 | -0.0355 | [-0.0719, -0.0032] | yes | 0 of 5 | +0.0000 | [+0.0000, +0.0000] |

At each arm's own measured latency on all 300 clips the 32B at N = 3 is -0.0172 mAP against N = 1 (CI -0.0774 to +0.0402), with hold shifts 1.00 s and 0.50 s. The 4B at N = 3 has NO committed serving latency and nothing is estimated for it.

**Cross-fitting FRAMES1 is a power gain, not a bias removal (B6)**, because the matched-delay comparison has no tunable: pooling to 300 clips narrows the interval and nothing else. The genuinely cross-fitted object is CHOOSE-N, which picks N on the four training folds and applies it to the held-out fold. That is what a DEV-fitted profile table would do, and its column above is the direct test of whether the DEV frame bonus transfers.

## 11. Results consistency check, 6 of 6

| # | check | outcome |
|---|---|---|
| 1 | cross-check against committed measurements | **PASS, and exactly.** The pooled design scores all 300 clips, so this is a DIRECT comparison with StudyE9c rather than the subset recomputation StudyCTRL1 had to make: always-cloud 0.5675307471627266 against the committed 0.5675307471627267 (difference -1.11e-16) and device-only 0.4776042449177038 against 0.4776042449177038 (difference +5.55e-17). |
| 2 | physical plausibility | **PASS.** Nothing is timed. Every latency is a committed constant: device cadence 0.75 s and latency 0.567 s, cloud latency 0.3950 s, call cadence 0.50 s, uplink 13.6 Mbit/s, RTT 0.044 s. |
| 3 | distribution sanity | **PASS.** Every capture fraction and every paired difference carries a 2,000-resample CI; episode lengths and call counts are reported as distributions with p25, p50, p75, min and max; per-fold values are reported beside every pooled one. |
| 4 | definition audit | **PASS with one definition CHANGED ON PURPOSE.** The challenge metric, AP, the delivery model and the fold rule are the committed ones (listed in `ctrl1b_consistency.json`). The BUDGET is deliberately redefined from StudyCTRL1's open-time fraction to the call fraction, for the reason in section 2, and both numbers are reported for every arm so no comparison can be made across the two definitions by accident. |
| 5 | claim linkage | **PASS.** This bears on spec 7.7 (the device controller), on the v3.1 addendum's open question Q11 (which SH trigger family), and on spec 4.1's u_SH. It WEAKENS any claim that a better-targeted trigger is what stands between device-only and always-cloud on this workload, and it SUPPORTS the addendum's requirement that escalation be decided on a calibrated gain rather than on a tier's own score. |
| 6 | proxy validity | **PASS with three proxies declared.** (a) The challenge metric reads ONE crop per clip, so an arm that happens to deliver at that instant is credited for the whole clip; this is a property of the committed metric and it is why the oracle is a bound on timing rather than an achievable policy. (b) The predictability ceiling is fitted on a target whose SIGN uses the clip label, so it is an upper bound available to an oracle-signed objective and not a deployable policy, which is why it is labelled a ceiling. (c) The context-modulated trickle's context signal is clip-level metadata standing in for the per-instant visual signal the brief intended, because the frame store is absent. |

## 12. What this row does NOT establish

* It does not establish that any causal trigger beats another on this workload. Read the CIs in section 3 before quoting any single capture fraction.
* It does not measure the cloud-initiated arm at the 5 %% or 10 %% budget AT ALL: the brief's background cadences cost more than those budgets, and the grid was not widened.
* It does not bound what visual features could predict, for want of the frames.
* It does not decide the addendum's Q11 by itself; it supplies the measured comparison that the decision should rest on, and StudyPOL2-build's trigger families are swappable precisely so that decision can be made later with one assignment.

## 13. Files

| file | what |
|---|---|
| `experiments/dashcam/d14b_folds.py` | the pre-registered fold assignment |
| `experiments/dashcam/ctrl1b_crossfit.py` | the study: fits, arms, mechanism, pooling, frames, workload traces |
| `experiments/dashcam/ctrl1b_learned.py` | arms (d) and (e): features, the numpy logistic regression and the numpy boosted stumps, and the list of features that are not available |
| `results/dashcam/ctrl1b/d14b_folds.json` | the fold assignment, per fold and per clip |
| `results/dashcam/ctrl1b/ctrl1b_fits.json` | every training-fold fit, including the models and their importances |
| `results/dashcam/ctrl1b/ctrl1b_mechanism.json` | mechanism verification Steps 1-5 for all four new arms |
| `results/dashcam/ctrl1b/ctrl1b_crossfit.json` | the pooled held-out results, the capture tables, episode statistics and the negative control |
| `results/dashcam/ctrl1b/ctrl1b_consistency.json` | the 6-check protocol's inputs |
| `results/dashcam/ctrl1b/frames1b_crossfit.json` | the StudyFRAMES1 re-run |
| `results/dashcam/ctrl1b/ctrl1b_workload_traces.json` | held-out escalation, call and background-sample times for all 300 clips, every arm, every budget |

