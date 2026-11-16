# StudyCTRL1-episodes: the self-normalized device controller, its episodes, and what
escalation-only cloud use actually captures

Pre-registered in `research/EXPERIMENTS.md` (StudyCTRL1-episodes) before anything was computed, including the DEV / EVAL split rule, the objective and the budget levels. CPU only on flash: no GPU, no model server, no inference. Every score is a committed StudyD14b trace.

**One sentence.** The controller behaves exactly as designed and its parameters transfer nothing: fitted on 90 DEV clips it captures 46 to 130 % of the DEV cloud-minus-device gap, and on the 210 held-out EVAL clips it captures **-18.2 % to 15.2 % with every confidence interval spanning zero**, is indistinguishable from an absolute-confidence trigger and from random escalation at the same budget, and sits inside the range StudyE9b already reported (3 to 18 % of the gap) for a cruder trigger on a coarser grid.

**The honest reading, stated before any table.** The EVAL subset cannot resolve the quantity this study exists to measure. On 105 positive and 105 negative clips the always-cloud minus device-only gap itself is **+0.0598 with CI [-0.0076, +0.1395]**, which includes zero, so a FRACTION of that gap is a ratio whose denominator is not resolved. Every key number below is therefore reported as INCONCLUSIVE in the sense of CLAUDE.md Rule 2, not as a real negative. The mechanism is present and was verified before these numbers were written (section 3).

---

## 1. The DEV / EVAL split, and why it had to be created

Part 1 step 1 asked for the Nexar DEV / EVAL split covering the D14b clips, and the stop condition fired: the canonical split (`results/dashcam/study_d2_nexar/nexar_train_split_seed0.csv`) is dev 751 / val 300 / test 449 clips and **StudyD14b IS the 300 val clips**, so they carry no DEV / EVAL partition at all; StudyD3 ran the dev clips but as a 10-offset design, which has no 0.25-s trajectory for a window length, a lag or a frame count to be fitted against. The user authorized the rule below before anything was computed.

    sha256(file_name) hex order, lowest 30 % to DEV, stratified by label; pre-registered in research/EXPERIMENTS.md (StudyCTRL1-episodes) before any computation

| side | clips | positive | negative | video seconds |
|---|---|---|---|---|
| DEV | 90 | 45 | 45 | 3419.4 |
| EVAL | 210 | 105 | 105 | 7941.7 |

Clip-level overlap is **0** and video-level overlap is **0** (the clip IS the video here). Scene, light and weather counts are in `results/dashcam/ctrl1/d14b_split.json`; the split is stratified by label only, which is the pre-registered rule.

**What the split costs, stated once and carried everywhere.** The committed challenge mAP references were computed over all 300 clips. They are recomputed here on each side:

| reference | all 300 (committed) | this pipeline, all 300 | DEV 90 | EVAL 210 |
|---|---|---|---|---|
| device-only 4BI N=1 | 0.4776 | 0.4776042449 | 0.4922 | 0.4822 |
| always-cloud 32BI N=1 @0.5 s | 0.5675 | 0.5675307472 | 0.5481 | 0.5420 |

The all-300 column reproduces StudyE9c to **+5.55e-17** and **-1.11e-16**, i.e. within one unit in the last place, which is consistency check 1 and is also the strongest available check that this study's delivery model, crop geometry and AP are StudyE9b / E9c / E9d's own and not a re-implementation.

## 2. The controller

Spec 7.7 with the price term OFF, over the device's OWN delivered samples. The device arm is 4BI N=1 at StudyE9b's saturated duty: it starts a score every **0.75 s** and each score is readable **3 grid steps** after its capture (StudyD8 latency 0.567 s). The controller never sees the 0.25-s trace and never sees an absolute confidence.

| quantity | value | source |
|---|---|---|
| device cadence | 3 grid steps (0.75 s) | StudyE9b saturated duty |
| device read shift | 3 grid steps (0.75 s) | StudyD8 latency 0.567 s |
| cloud end-to-end latency | 0.3950 s | StudyE9b setting (ii): RTT 0.044 s + 354,902 B at 13.6 Mbit/s + StudyD7b TTFT 0.1422 s |
| cloud read shift | 2 grid steps (0.50 s) | ceil(latency / 0.25) |
| episode call cadence T | 0.50 s (2 steps) | spec 7.7 / the brief |
| maximum calls per episode E | 10 | the brief's default |
| contention | NONE | pre-registered: zero contention |

### 2.1 Where the spec is silent, and what was chosen

Nothing here was decided silently; each row is in the module docstring too.

| # | the spec says | the question | the choice, and why |
|---|---|---|---|
| A1 | "rise score_t - score_{t - delta}" while calling all three signals self-normalized | is rise normalized? | rise AND instability are divided by the same window IQR as z. A raw log-unit rise and a dimensionless z cannot share one threshold theta without a unit error. The unnormalized reading is not implemented. |
| A2 | "instability over n_c frames" | which statistic? | BOTH readings the brief offers are implemented and the choice is made on DEV like any other fitted quantity: `var` = standard deviation of the last n_c samples / window IQR; `flips` = sign changes of score > log 0.5 over the last n_c samples, as a fraction, divided by 0.5. DEV selected `var` at every budget. |
| A3 | nothing | what if the window is flat? | an IQR below 1e-6 yields NO signal and cannot escalate. Dividing by a floor instead would make a flat window the most escalation-prone state, which inverts the mechanism. |
| A4 | nothing | what does the application display? | the most recently DELIVERED value from either source, as one sample-and-hold. This is StudyE9b's own mixed-stream semantics. Preferring the cloud for a whole episode even after a newer device sample would credit the cloud with values it did not deliver. |
| A5 | "theta_k: DEV-fitted" | fitted how, against what target? | theta is solved by bisection per combination to hit each pre-registered budget ON DEV, then applied UNCHANGED to EVAL; the realized EVAL fraction is reported next to the DEV target and never retuned. |

## 3. Mechanism verification, Steps 1 to 5

Recorded on DEV ONLY and **before any EVAL number was computed**, as CLAUDE.md requires. Artifact: `results/dashcam/ctrl1/ctrl1_mechanism.json`.

**Step 1, the causal chain.** If the device's own score trajectory carries information about an approaching event (StudyD14b measured it: the 4B's score rises before the event), then a controller reading only SELF-NORMALIZED features of that trajectory (z, rise, instability against its own window median and IQR, spec 7.7) fires more often shortly before events than elsewhere; each firing opens an episode of 0.5-s cloud calls whose answers are delivered 2 grid steps later and become the application's displayed score; because the 32B's score separates positives from negatives better than the 4B's at the same instant (StudyE9c: 0.5675 against 0.4776 over all 300 clips), replacing the displayed score at the challenge crop instants raises challenge mAP; so escalation-only cloud use captures part of the always-cloud minus device-only gap, and the share captured rises with the escalation budget.

**Step 2, each link instantiated.**

| causal link | implementing quantity | value / range on DEV | varies as expected? |
|---|---|---|---|
| score trajectory -> self-normalized signal | max(z, rise, instability) per device sample | n = 4055, p5 0.083, median 0.857, p95 2.667, max 4.000; median 0.957 within 2 s before an event against 0.857 far from any event | YES |
| signal -> escalation | escalated fraction of device-time as theta moves | theta 0.5 -> 0.850, theta 1.0 -> 0.593, theta 1.5 -> 0.352, theta 2.0 -> 0.204, theta 3.0 -> 0.064, theta 4.0 -> 0.000, theta 5.0 -> 0.000 | YES, monotone |
| escalation -> an episode open at the scored instant | fraction of scored positive DEV clips with an open episode at the crop | budget 0.05: h=0.5 0.111, h=1.0 0.105, h=1.5 0.136; budget 0.1: h=0.5 0.178, h=1.0 0.158, h=1.5 0.182; budget 0.2: h=0.5 0.222, h=1.0 0.184, h=1.5 0.136; budget 0.4: h=0.5 0.400, h=1.0 0.368, h=1.5 0.364 | YES, rises with the budget |
| cloud delivery -> displayed score | grid points differing from device-only at the 40 % budget | 3800 of 12646 (0.300) | YES, non-zero |
| displayed score -> challenge mAP | DEV challenge mAP by budget | device-only 0.4922, escalation-only 5%: 0.5179, 10%: 0.5259, 20%: 0.5459, 40%: 0.5646, always-cloud 0.5481 | YES |

No link is ABSENT or CONSTANT, so the sweep was allowed to proceed.

**Step 3, one traced unit** (one episode on one DEV positive clip, at the 10 % budget). Clip `00086.mp4`, event at 19.400 s, scored at horizon 0.5 s, crop index 64 (t = 19.00 s).

| device sample | captured at (s) | readable at (s) | score |
|---|---|---|---|
| 16 | 15.00 | 15.75 | -15.00000 |
| 17 | 15.75 | 16.50 | -16.00000 |
| 18 | 16.50 | 17.25 | -13.50000 |
| 19 | 17.25 | 18.00 | -3.52975 |

Window median -14.25000, window IQR 4.24256, so z = (-3.52975 - -14.25000) / 4.24256 = **2.5268** and rise = **2.9393**, against theta = **2.6667**. The episode opens at t = 18.00 s, calls fire at 18.00 s, 18.50 s, 19.00 s and their answers are readable at 18.50 s, 19.00 s, 19.50 s. It closes at t = 19.50 s. At the crop the displayed score is **-11.37501** under escalation-only against **-6.50150** under device-only (the cloud's own score captured at the crop instant is -4.14101).

**Step 4, the negative control, and the most important single result in this report.** The control replaces the cloud's score with the DEVICE'S OWN score, so an escalation buys the cloud PATH (a call every 0.50 s delivered after 0.395 s) and nothing else. It does NOT collapse to the null, and that decomposes the effect:

| budget | escalation-only | control: device scores through the cloud path | device-only | gain from path freshness | gain from cloud score quality | quality share |
|---|---|---|---|---|---|---|
| 5.0 % | 0.5179 | 0.5027 | 0.4922 | +0.0105 | +0.0152 | 59 % |
| 10.0 % | 0.5259 | 0.5073 | 0.4922 | +0.0151 | +0.0186 | 55 % |
| 20.0 % | 0.5459 | 0.5157 | 0.4922 | +0.0235 | +0.0302 | 56 % |
| 40.0 % | 0.5646 | 0.5142 | 0.4922 | +0.0220 | +0.0504 | 70 % |

THE CONTROL DOES NOT COLLAPSE TO THE NULL, and that is a result, not a failure: escalation-only's gain decomposes into a path-freshness part (the control's gain over device-only) and a cloud-score-quality part (the rest). Both are mechanisms the policy can use, but only the second is what 'the cloud is better' means, so the shares are reported with every headline number and the random-escalation arm at the same budget is the comparator that isolates targeting from both.

The control cell is DEV, 90 clips, setting measured@25.

**Step 5, the alternative explanation.** The same headline could be produced by (a) the controller TIMING cloud calls to the moments that matter [the claimed mechanism], or (b) nothing more than the cloud path being FRESHER and FASTER than the device path (calls every 0.50 s delivered after 0.39 s, against device samples every 0.75 s delivered after 0.567 s), so that any escalation at all, however placed, would help. The two are distinguished by the RANDOM-escalation arm, which has the same cadence and latency and the same budget but no targeting, and by the ABSOLUTE-CONFIDENCE arm, which targets on the raw score instead. If escalation-only does not beat random at the same budget, explanation (b) is the live one and the controller's targeting is not doing the work.

## 4. The DEV grid search

maximize DEV challenge mAP of escalation-only (device answers always, cloud upgrades during episodes, zero contention) at a fixed escalation budget; pre-registered

Grid: W_c [1.5, 3.0, 6.0] s, delta [0.75, 1.5, 3.0] s, n_c [2, 3, 4] samples, K_c [1, 2, 4] samples, instability mode ['var', 'flips'], theta solved per combination. That is **162 combinations** per budget, all evaluated on DEV only.

| budget | theta | W_c (s) | delta (s) | n_c | K_c | instability | DEV escalated fraction | DEV mAP | DEV gap captured |
|---|---|---|---|---|---|---|---|---|---|
| 5.0 % | 3.1219 | 3.00 | 1.50 | 2 | 1 | var | 0.0501 | 0.5179 | 46 % |
| 10.0 % | 2.6667 | 3.00 | 1.50 | 2 | 1 | var | 0.1000 | 0.5259 | 60 % |
| 20.0 % | 4.5718 | 1.50 | 3.00 | 2 | 1 | var | 0.2001 | 0.5459 | 96 % |
| 40.0 % | 3.5000 | 1.50 | 3.00 | 3 | 1 | var | 0.4000 | 0.5646 | 129 % |

DEV references: device-only 0.4922, always-cloud 0.5481. Every budget was hit to within the pre-registered tolerance of 0.0025.

**On DEV the controller looks good, and at the 40 % budget it SCORES ABOVE always-cloud (0.5646 against 0.5481).** That is not a bug and it is worth stating plainly: the displayed stream is a MIXTURE, and the device's own samples fill the 0.395 s after each cloud call and the gaps between episodes, so a mixture can beat either pure arm on a 90-clip crop set. It is also the first sign of how much of this is sampling noise, which section 5 settles.

The absolute-confidence control and the random arm were tuned on DEV at the same budgets:

| budget | absolute threshold tau on the raw device score | DEV fraction | random: p(open) per decision instant | calls per random episode | DEV fraction |
|---|---|---|---|---|---|
| 5.0 % | -1.3133 | 0.0493 | 0.01941 | 2 | 0.0500 |
| 10.0 % | -2.8120 | 0.0965 | 0.04093 | 2 | 0.0997 |
| 20.0 % | -5.2552 | 0.1997 | 0.06527 | 3 | 0.1996 |
| 40.0 % | -8.5002 | 0.3960 | 0.14523 | 3 | 0.4002 |

## 5. EVAL: episode statistics and the arms

Settings fitted on DEV, applied unchanged. 210 clips, 105 positive and 105 negative.

### 5.1 How often the device escalates, and for how long

| budget | realized EVAL escalated fraction | episodes | escalations per device-minute | episode length p50 (s) | length IQR (s) | calls per episode p50 (max) | false episodes per minute on negatives |
|---|---|---|---|---|---|---|---|
| 5.0 % | 0.0503 | 257 | 2.10 | 1.25 | 1.25 to 1.75 | 2 (4) | 2.14 |
| 10.0 % | 0.0966 | 490 | 4.00 | 1.25 | 1.25 to 1.75 | 2 (4) | 4.25 |
| 20.0 % | 0.2002 | 828 | 6.77 | 1.75 | 1.25 to 2.25 | 3 (10) | 6.45 |
| 40.0 % | 0.3900 | 1637 | 13.38 | 1.75 | 1.25 to 2.25 | 3 (10) | 13.18 |

**False episodes per minute on negative clips track the escalation rate almost exactly** (2.14 against 2.10 per minute at the 5 %% budget, 13.18 against 13.38 at 40 %%), which is the cleanest statement of what the controller is doing: it is not separating event-bearing moments from ordinary ones, it is firing at a rate set by theta.

### 5.2 Is an episode open when it matters?

The fraction of scored positive EVAL clips with an open episode at each challenge horizon, that is 0.5 / 1.0 / 1.5 s before the event:

| budget | h = 0.5 s | h = 1.0 s | h = 1.5 s |
|---|---|---|---|
| 5.0 % | 0.067 | 0.074 | 0.159 |
| 10.0 % | 0.143 | 0.162 | 0.227 |
| 20.0 % | 0.267 | 0.338 | 0.273 |
| 40.0 % | 0.438 | 0.485 | 0.386 |

At the 5 %% budget an episode is open at the scored instant on 7 to 16 %% of positive clips; at 40 %% on 39 to 49 %%. Compare the escalated fraction itself (5 %% and 39 %%): at the low budget the controller is slightly BETTER than chance at being open when it matters (6.7-15.9 %% against 5 %%), at the high budget it is at or slightly above chance. That small edge is the entire mechanism, and section 5.3 shows it does not survive the metric.

### 5.3 Challenge mAP, all five arms

StudyE9c's challenge mAP (one crop per clip, horizons 0.5 / 1.0 / 1.5 s, unweighted mean), EVAL subset, with 2,000-resample paired clip-bootstrap CIs at seed 0.

| budget | device-only | escalation-only | absolute-confidence | random-escalation | always-cloud |
|---|---|---|---|---|---|
| 5.0 % | 0.4822 | **0.4713** [0.4114, 0.5585] | 0.4784 | 0.4819 | 0.5420 |
| 10.0 % | 0.4822 | **0.4833** [0.4220, 0.5702] | 0.4971 | 0.4836 | 0.5420 |
| 20.0 % | 0.4822 | **0.4803** [0.4219, 0.5680] | 0.4757 | 0.4722 | 0.5420 |
| 40.0 % | 0.4822 | **0.4913** [0.4330, 0.5795] | 0.5024 | 0.4932 | 0.5420 |

Paired differences, same resamples:

| budget | escalation-only minus device-only | minus random | minus absolute | always-cloud minus device-only |
|---|---|---|---|---|
| 5.0 % | -0.0109 [-0.0308, +0.0040] | -0.0106 [-0.0373, +0.0112] | -0.0070 [-0.0385, +0.0186] | +0.0598 [-0.0076, +0.1395] |
| 10.0 % | +0.0011 [-0.0223, +0.0239] | -0.0003 [-0.0311, +0.0278] | -0.0138 [-0.0605, +0.0225] | +0.0598 [-0.0076, +0.1395] |
| 20.0 % | -0.0019 [-0.0350, +0.0353] | +0.0081 [-0.0340, +0.0468] | +0.0046 [-0.0295, +0.0369] | +0.0598 [-0.0076, +0.1395] |
| 40.0 % | +0.0091 [-0.0325, +0.0533] | -0.0019 [-0.0556, +0.0482] | -0.0112 [-0.0499, +0.0254] | +0.0598 [-0.0076, +0.1395] |

**Not one interval excludes zero**, including always-cloud minus device-only.

## 6. THE KEY NUMBER

The fraction of the always-cloud minus device-only challenge-mAP gap that escalation-only captures, with the CI taken over the SAME clip resamples as the arms themselves:

| budget | escalation-only | absolute-confidence | random-escalation | gap being divided |
|---|---|---|---|---|
| 5.0 % | **-18.2 %** [-172, 121] | **-6.4 %** [-123, 80] | **-0.5 %** [-77, 78] | +0.0598 |
| 10.0 % | **1.9 %** [-113, 94] | **25.0 %** [-97, 194] | **2.3 %** [-73, 88] | +0.0598 |
| 20.0 % | **-3.2 %** [-242, 143] | **-10.9 %** [-305, 216] | **-16.7 %** [-248, 107] | +0.0598 |
| 40.0 % | **15.2 %** [-183, 138] | **33.8 %** [-175, 172] | **18.4 %** [-139, 148] | +0.0598 |

**How this compares with StudyE9b.** StudyE9b's device-triggered escalation (a threshold on the device's delivered score, 1-s grid, streaming AP, all 300 clips) captured 3 %% of the span at trigger 5 %%, 13 %% at 10 %%, 13 %% at 20 %% and 18 %% at 40 %%. Our point estimates at the same budgets are -18.2 %%, +1.9 %%, -3.2 %% and +15.2 %%. **Does this controller differ from that one? No measurable difference, in either direction.** The paired difference between escalation-only and the absolute-confidence trigger (which is StudyE9b's trigger family) is -0.0070, -0.0138, +0.0046 and -0.0112 mAP at the four budgets, with every interval spanning zero. Self-normalization buys nothing detectable here; it also costs nothing.

**Why the numbers are not resolvable, quantified.** The denominator is a +0.0598 gap whose own CI is [-0.0076, +0.1395] on 105 positive and 105 negative clips. The bootstrap standard deviation of that difference is about 0.0375 mAP (CI width / 3.92), so an effect equal to a quarter of the gap, 0.0149 mAP, would need roughly **49 times** the clips to be resolved at 80 % power, that is of the order of 10384 clips rather than 210. The honest conclusion is that the EVAL subset bounds the answer loosely, not that the controller captures nothing.

**DEV against EVAL, the transfer failure in one table.** This is the finding with the most consequence for the policy, because it says what a DEV-fitted controller threshold is worth.

| budget | DEV gap captured | EVAL gap captured | DEV mAP | EVAL mAP |
|---|---|---|---|---|
| 5.0 % | 46 % | -18.2 % | 0.5179 | 0.4713 |
| 10.0 % | 60 % | 1.9 % | 0.5259 | 0.4833 |
| 20.0 % | 96 % | -3.2 % | 0.5459 | 0.4803 |
| 40.0 % | 129 % | 15.2 % | 0.5646 | 0.4913 |

162 combinations times 4 budgets were scored on 45 positive and 45 negative DEV clips. The DEV column is therefore a selection maximum, not an estimate, and the EVAL column is what the same settings deliver on held-out clips. **A DEV-fitted theta on 90 clips does not transfer.**

## 7. Streaming AP, under its own name

StudyE9b's dense streaming AP, never mixed with the challenge mAP:

| budget | arm | h = 0.0 | h = 0.5 | h = 1.0 | h = 1.5 |
|---|---|---|---|---|---|
| 5.0 % | device-only | 0.0146 | 0.0122 | 0.0122 | 0.0101 |
| 5.0 % | escalation-only | 0.0147 | 0.0123 | 0.0125 | 0.0100 |
| 5.0 % | always-cloud | 0.0320 | 0.0186 | 0.0144 | 0.0129 |
| 10.0 % | device-only | 0.0146 | 0.0122 | 0.0122 | 0.0101 |
| 10.0 % | escalation-only | 0.0150 | 0.0128 | 0.0132 | 0.0104 |
| 10.0 % | always-cloud | 0.0320 | 0.0186 | 0.0144 | 0.0129 |
| 20.0 % | device-only | 0.0146 | 0.0122 | 0.0122 | 0.0101 |
| 20.0 % | escalation-only | 0.0173 | 0.0128 | 0.0124 | 0.0103 |
| 20.0 % | always-cloud | 0.0320 | 0.0186 | 0.0144 | 0.0129 |
| 40.0 % | device-only | 0.0146 | 0.0122 | 0.0122 | 0.0101 |
| 40.0 % | escalation-only | 0.0167 | 0.0128 | 0.0123 | 0.0102 |
| 40.0 % | always-cloud | 0.0320 | 0.0186 | 0.0144 | 0.0129 |

## 8. The workload traces for the live evaluation

`results/dashcam/ctrl1/ctrl1_workload_traces.json` carries, per EVAL clip and per budget, every escalation with its episode's call times and the delivery time each call's answer would have under setting (ii) with zero contention, plus the **eligible-opportunity grid**: every decision instant on the 0.5-s cadence while the task is active (spec 1.2's SLO denominator for SH). 210 clips, 14749 eligible opportunities in total, and 490 episodes at the 10 % budget. A live run replaces the delivery times with its own measured TTFTs and keeps everything else.

## 9. Results consistency check, 6 of 6

| # | check | outcome |
|---|---|---|
| 1 | cross-check against committed measurements | **PASS.** This pipeline reproduces StudyE9c's all-300 always-cloud 32BI N=1 @0.5 s (0.5675307472 against 0.5675307472, -1.11e-16) and device-only 4BI N=1 (0.4776042449 against 0.4776042449, +5.55e-17), i.e. to 1 ulp. No quantity here disagrees with a prior committed value by more than that. |
| 2 | physical plausibility | **PASS.** Every latency is a committed constant, not a fitted one: device 0.567 s (StudyD8), cloud 0.3950 s = RTT 0.044 + 354,902 B / 1.7 MB/s + TTFT 0.1422 (StudyD7b at 25 % load). Implied read shifts are 3 and 2 grid steps. Nothing is faster than a committed curve because nothing is measured here. |
| 3 | distribution sanity | **PASS.** Spread is reported with every median: episode length p25 / p50 / p75 and max, calls per episode p50 and max, signal p5 / p50 / p95, and a bootstrap CI on every mAP. The one constant is device-only's mAP across budgets, which must be constant: the device arm does not depend on the budget. |
| 4 | definition audit | **PASS.** `Challenge`, `ap_fast`, `cloud_delivered`, `held_stream`, the 0.25-s grid, the 0.5 / 1.0 / 1.5 s horizons and setting (ii) are taken unchanged from StudyE9b / E9c / E9d by import, not re-implemented. The two quantities this study defines are named differently from anything committed: `escalated fraction of device-time` and `gap fraction captured`. |
| 5 | claim linkage | **PASS.** The headline bears on the policy's M2 input (spec 7.7's controller) and on FORMULATION's semantic-component claim only through the Nexar task metric. It WEAKENS any claim that a self-normalized device controller captures a useful share of the cloud's advantage at these budgets, and it does not speak to the physical component at all. Nothing measured here is scoped out by FORMULATION. |
| 6 | proxy validity | **PASS with two proxies declared.** (a) The device arm is the 4B run on the H100, standing in for an Orin; StudyORIN1-dense would replace it and is not required by this row. (b) Challenge mAP over the displayed score is the task metric, but the controller's own signals are computed on the same committed scores, so a trace artifact would appear on both sides; the negative control in section 3 is what separates them. Neither proxy is load-bearing for the conclusion, which is a null. |

## 10. What this study establishes, and what it does not

1. **The controller works mechanically and is fully specified.** Every link of its causal chain is present and varies (section 3), one episode is traced end to end, and the code is spec 7.7 with the price term off.
2. **Its DEV-fitted parameters do not transfer.** 46 to 130 %% of the gap on DEV becomes -18 to +15 %% on EVAL. Any future use of a DEV-fitted theta should expect this.
3. **Self-normalization is not measurably better than an absolute threshold** at any budget, which is a direct answer to the question the row asked and is consistent with StudyE9b's finding that the gate, not the answerer, is binding.
4. **Part of what escalation buys is not capability at all.** The negative control puts 30 to 45 %% of the DEV gain down to the cloud path being fresher and faster than the device path. The policy may legitimately use that, but it must not be called a capability gain.
5. **The key number is INCONCLUSIVE, not a real negative** (CLAUDE.md Rule 2): the mechanism was present and the control moved the result, but the EVAL subset cannot resolve even the denominator. What would settle it is more scored clips, which means the 449-clip Nexar test split or a denser crop design, not a different controller.
6. **Not established here:** anything about contention (the study is zero-contention by pre-registration), anything about an Orin device, and anything about the price term beta, which is off.

## 11. Files

| file | what |
|---|---|
| `experiments/dashcam/d14b_split.py` | the pre-registered DEV / EVAL split and the subset context helper |
| `experiments/dashcam/ctrl1_controller.py` | the controller, the DEV search, the arms, the metrics, the mechanism verification and the workload traces |
| `results/dashcam/ctrl1/d14b_split.json` | the split, with per-stratum counts |
| `results/dashcam/ctrl1/ctrl1_dev_search.json` | all 162 combinations x 4 budgets on DEV, the chosen settings, the absolute and random tunings |
| `results/dashcam/ctrl1/ctrl1_mechanism.json` | Steps 1-5, recorded before the EVAL numbers |
| `results/dashcam/ctrl1/ctrl1_eval.json` | every EVAL number, with CIs |
| `results/dashcam/ctrl1/ctrl1_consistency.json` | the all-300 reproduction behind check 1 |
| `results/dashcam/ctrl1/ctrl1_workload_traces.json` | per-clip escalations, episode call times and the eligible-opportunity grid, for the live evaluation |

