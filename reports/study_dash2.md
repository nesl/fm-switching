# StudyDASH2: why the cloud's dashcam advantage shrinks at system level (D199 metric)

Metric: Nexar challenge AP at horizons 0.5 to 3.0 s, challenge mAP = mean at 0.5/1.0/1.5 s. No alarm
timing, thresholds, matched-FAR lead, AUROC or streaming AP. Seeds 4-7. Splits stated per number.

## Answer: what is the best thing the policy can do for dashcams (provisional, from Parts 1-2)

The room is small and hard to measure. Serving the cloud on 99.6 percent of decision instants (the
cloud-every-instant ceiling) reaches challenge mAP 0.665 against device-only 0.620, a gain of only
+0.044 whose clustered 95 percent CI [-0.034, +0.114] includes zero; the workload format caps the
achievable mAP far below the model-level EP-G advantage (+0.108 in StudyEARLY1). The minimum
detectable challenge-mAP difference at 80 percent power is 0.048, which is larger than the gaps
between the arms (all 0.62 to 0.67), so no arm is separable from another or from the ceiling on this
metric at this clip count. The best thing the policy can do is to spend its cloud budget where a
cloud answer changes the delivered score the most, which Part 4 shows is on instants in the MIDDLE
device-level quintile (the device is uncertain there, marginal gain +0.261, against near zero at the
extremes), and Part 5 shows that allocating the budget that way beats uniform random by about +0.02
challenge mAP (front-loaded R2 at the -rr budget, device-gated R3 at the rung-3 budget), while the
arms' ACTUAL allocation (R0) is slightly WORSE than random (about -0.015). That +0.02 is below the
0.048 MDE, so no rule clears the pre-registered bar (paired vs-random CI lower bound above zero at
both budgets); the recommendation is therefore "not resolvable on this metric at this clip count, but
device-gating toward uncertain instants is the direction, and the current allocation is not it."

## Part 1: power and intervals

1a. Units (per seed): about 189 distinct clips, 1 play per clip, about 712 episodes (3.8 per clip).
60 clips appear in all four seeds and the union is 296 clips, so the seeds REUSE clips and are not
independent clip samples; the bootstrap clusters by clip.

1b. Calibration: 5-fold cross-fitted per-tier Platt by clip (every clip scored with a map fit on the
other folds' SH-EP EP-G instants). Cross-fitted ALL (300 clips) is primary; EVAL with DEV-fitted maps
is reported beside it.

1c. Paired clustered bootstrap over clips (2000 resamples, seed 0), same resample indices for every
arm, all plays/seeds/horizons of a clip kept together.

1d. Minimum detectable difference (paired, 80 percent power, alpha 0.05): challenge mAP MDE = 0.048
(paired-difference bootstrap SD 0.017). CI half-width for the top arm: 0.073 before (EVAL, DEV-fitted)
and 0.060 after (ALL, cross-fitted). The intervals tighten but still exceed the arm gaps.

## Part 2: the ceiling on the workload format

Cloud-every-instant stream (union of on-time cloud scores across the valid rq30 L3 arms, same trace
and default EP-G episodes). Coverage of decision instants: 99.6 percent mean over seeds; the 0.4
percent never served are filled with the device score. For instants served by two or more arms the
cache-path spread (D81) is median about 0.000, so the arms agree on the cloud score.

Challenge mAP (cross-fitted ALL): device-every-instant 0.620 (equals device-only, sanity), each arm
0.62 to 0.67, cloud-every-instant ceiling 0.665. Cloud-every vs device-only +0.044 [-0.034, +0.114],
CI includes zero. Horizon shift cloud-every vs device: 0 at t0 = 0.5 and 1.0 s, 1.0 s at t0 = 1.5 s.

Observation: even with near-total cloud coverage the system-level challenge mAP sits at 0.665, below
the model-level EP-G EVAL 32B (0.683) and barely above device-only, and the arms are not separable
from one another or from the ceiling at the MDE. The cloud's model-level advantage does not survive
the workload format.

## Part 4: value of a cloud answer by observable state

Marginal gain (mean cloud calibrated minus device calibrated score) on instants 0.5 to 3.0 s before
the event in crash clips, by device calibrated-level quintile, groupings fit on DEV clips. The gain is
largest in the MIDDLE quintiles (q2 +0.261, q1 +0.163, q4 +0.145) and near zero in the lowest (q0
+0.009). A cloud answer is worth most where the device score is uncertain, not where it is already
confident low or high. Features are runtime-observable (episode position, device level, device trend,
last served cloud score); no labels, event times or future information are used.

## Part 5: budget-matched allocation rules (cross-fitted ALL, paired vs uniform random R1)

At each arm's actual on-time cloud budget, reassign which instants get the 2a cloud score. R0 as
served, R1 uniform random (10 draws), R2 front-loaded, R3 device-gated (highest device level), R4
device-trend, R5 cloud-gated continuation, R6 best Part 4 grouping greedy. Instants a rule picks that
have no 2a cloud score are not filled.

| rule | -rr mAP | -rr vs R1 [CI] | rung-3 mAP | rung-3 vs R1 [CI] |
|---|---|---|---|---|
| R0 as served | 0.660 | -0.014 [-0.037, +0.009] | 0.654 | -0.015 [-0.056, +0.028] |
| R1 random | 0.674 | 0 | 0.669 | 0 |
| R2 front-loaded | 0.697 | +0.022 [-0.004, +0.050] | 0.649 | -0.021 [-0.068, +0.033] |
| R3 device-gated | 0.680 | +0.006 [-0.015, +0.031] | 0.690 | +0.021 [-0.018, +0.060] |
| R4 device-trend | 0.657 | -0.017 [-0.039, +0.007] | 0.669 | -0.000 [-0.034, +0.038] |
| R5 cloud-gated | 0.664 | -0.011 [-0.031, +0.010] | 0.666 | -0.003 [-0.036, +0.031] |
| R6 Part-4 greedy | 0.661 | -0.013 [-0.035, +0.013] | 0.672 | +0.003 [-0.036, +0.044] |

Observation: R0 (the arms' actual allocation) is at or below uniform random at both budgets, and its
value is bracketed by the R1 spread (sanity). Front-loaded (R2) wins at the -rr budget and
device-gated (R3) wins at the rung-3 budget, each by about +0.02, but every CI includes zero and the
effects are below the 0.048 MDE.

### Decision (pre-registered rule)

NOT RECOMMENDED: no rule has a paired vs-random CI lower bound above zero on cross-fitted ALL at BOTH
the -rr and rung-3 budgets with a positive EVAL point. Closest is R3 (device-gated), mean vs-R1
difference +0.013 across the two budgets. The best point estimates are R2 (+0.022) at -rr and R3
(+0.021) at rung-3; both fall inside the MDE of 0.048. A recommendation, not a build; the user
decides.

## Part 3 (gap decomposition)

The step decomposition reports challenge mAP of the cloud-every-instant stream against
device-every-instant at each counterfactual step: (i) SH-EP format (EP-G from clip start), (ii)
workload format (same clips), (iii) mixing tiers in one ranking under three schemes fitted without the
evaluated clip (Platt, isotonic, per-tier rank normalisation), (iv) only on-time cloud answers count
vs counting every cloud answer at its delivery time. Steps (i) and (ii) are reported below; the mixing
schemes (iii) and the lateness variant (iv) are COMPUTED in dash2_part3.py and reported here, and are
not characterised relative to the MDE until measured.

Step (i) SH-EP format (EP-G from clip start), cross-fitted: cloud 0.649 vs device 0.566, gap 0.083 on ALL and 0.122 on EVAL. Step (ii) workload format (cloud-every-instant vs device-every-instant, same clips): cloud-every 0.665 vs device-every 0.620, gap 0.044 on ALL. Most of the shrink from the model-level gap to the system-level gap happens at this format step.

Step (iii) mixing tiers in one ranking, each arm's delivered stream (on-time) under three cross-fitted schemes (delivered challenge mAP, ALL):

| arm | Platt | isotonic | rank |
|---|---|---|---|
| base | 0.671 | 0.656 | 0.657 |
| state-shares-r1 | 0.669 | 0.655 | 0.666 |
| fair-c5attr-rr | 0.668 | 0.646 | 0.664 |
| state-shares | 0.665 | 0.641 | 0.643 |
| b7-edf-feasibility | 0.664 | 0.651 | 0.642 |
| mooncake | 0.664 | 0.653 | 0.642 |
| eco-llm | 0.662 | 0.649 | 0.639 |
| confidence-cascade | 0.662 | 0.637 | 0.636 |
| simplestream | 0.655 | 0.622 | 0.644 |
| fair-c5attr | 0.654 | 0.630 | 0.648 |
| state-uo-c5attr | 0.653 | 0.646 | 0.644 |
| state-shares-r2 | 0.653 | 0.628 | 0.639 |
| streamscout | 0.646 | 0.613 | 0.635 |
| fair-c5attr-gain0 | 0.644 | 0.629 | 0.623 |
| warm-all-lru | 0.641 | 0.629 | 0.632 |
| always-cloud-fcfs | 0.641 | 0.627 | 0.632 |
| attentionstore-prefetch | 0.640 | 0.626 | 0.631 |
| kvflow-prefetch | 0.639 | 0.627 | 0.630 |
| lmcache | 0.639 | 0.627 | 0.631 |
| querystream-proactive | 0.638 | 0.626 | 0.630 |
| llf | 0.634 | 0.613 | 0.631 |
| state-uo | 0.634 | 0.622 | 0.624 |
| edf | 0.625 | 0.622 | 0.615 |
| rules | 0.624 | 0.613 | 0.624 |

The scheme choice moves an arm's delivered mAP by a median of 0.018 (max 0.033) across arms, below the 0.048 MDE; Platt gives the highest delivered mAP and isotonic the lowest. Mixing-scheme choice is therefore a measured, small effect, not a confound.

Step (iv) lateness: on-time-only vs counting every cloud answer at its delivery time (Platt, paired ALL CI). The change from admitting late answers is small and its CI includes zero for every arm:

| arm | on-time | every | every minus on-time [CI] |
|---|---|---|---|
| rules | 0.624 | 0.666 | +0.042 [+0.001, +0.079] |
| state-uo | 0.634 | 0.673 | +0.039 [-0.005, +0.080] |
| edf | 0.625 | 0.650 | +0.025 [-0.016, +0.062] |
| streamscout | 0.646 | 0.666 | +0.019 [+0.000, +0.038] |
| lmcache | 0.639 | 0.658 | +0.019 [-0.049, +0.082] |
| fair-c5attr-gain0 | 0.644 | 0.660 | +0.016 [-0.030, +0.059] |
| llf | 0.634 | 0.649 | +0.015 [-0.010, +0.040] |
| querystream-proactive | 0.638 | 0.653 | +0.015 [-0.052, +0.081] |

Across arms the every-minus-on-time delta ranges -0.010 to 0.042, all CIs spanning zero, below the MDE. Discarding late cloud answers costs essentially nothing on the challenge metric.

Cloud coverage near the event (0.5 to 3.0 s before the event in crash clips) against overall coverage, per arm, is close for every arm (for example fair-c5attr 0.555 near vs 0.520 overall; simplestream 0.939 vs 0.936; lmcache 0.080 vs 0.082), so no arm preferentially serves the cloud on the instants that move the metric.

Decomposition summary: the model-level gap (step i, EVAL 0.122) collapses to the system-level gap (step ii, 0.044) at the WORKLOAD-FORMAT step; the mixing scheme (iii, median 0.018) and lateness (iv, within 0.02, CIs span zero) both act below the 0.048 MDE. The format, not the mixing or the lateness, is where the cloud's advantage is lost.

## Addendum: Part 3 extension (context) and Part 6 (cloud context lifecycle)

Part 3 extension. Cloud-every-instant challenge mAP on crash-clip crops, positives split by the cloud
episode context at the instant: by context length under 6 frames 0.200, 6 to 12 frames 0.648, over 12
frames 0.338; by restart, episodes that restarted within 3 s before the event 0.170 against episodes
that did not 0.663. The workload's 21-frame episode restart leaves near-zero context at many crops and
collapses the cloud mAP there; instants whose episode covers the run-up score about 0.66.

Part 6 (vs device-only 0.620, cross-fitted ALL, 100 percent crop coverage for every condition):

| condition | challenge mAP | vs device-only [CI] | uncached tok | mAP gain per 1k uncached |
|---|---|---|---|---|
| C1 one frame | 0.707 | +0.087 [+0.039, +0.138] | 378 | +0.230 |
| C3 short window | 0.713 | +0.093 [+0.028, +0.149] | 1056 | +0.088 |
| C6 short window | 0.706 | +0.085 [+0.008, +0.150] | 2070 | +0.041 |
| EP-B 5 s blocks | 0.724 | +0.104 [+0.043, +0.155] | 376 | +0.276 |
| EP-G full run-up | 0.642 | +0.022 [-0.057, +0.093] | 372 | +0.058 |

CORRECTION (StudyCTX1, D207): the EP-B result below does NOT survive verification. Part 6 here did not apply D153 (minimum 3 frames) and used cross-fitted calibration selected on the evaluation data; under DEV selection with DEV-fitted calibration and D153, EP-B is 24.5 percent non-decision crops and its DEV gain over device-only is -0.037 (worse than device-only), and C1 is 100 percent non-decision (not deployable). The DEV-selected condition is C3 (3 frames), and it is NOT build-ready (EVAL gain vs device-only CI lower bound below zero). See reports/study_ctx1.md. The paragraph below is left as the original Part 6 reading and is superseded by StudyCTX1.

Decision. The 21-frame restart explains only part of the shrink, and in a direction opposite to the
hypothesis: a FRESH short recent window is more discriminative at the crop than the full run-up. The
best context is EP-B (5 s blocks), challenge mAP 0.724 (+0.104 over device-only, CI excludes zero) at
376 uncached tokens per instant; one frame (C1) is close at lower cost. The full run-up (EP-G) is the
WORST condition (0.642, CI includes zero), because a long history dilutes the recent signal. So the
workload loses on two counts: its EP-G episodes dilute like the full run-up, and its restarts leave
near-zero context at many crops (mAP 0.170). The context that recovers the most challenge mAP per
uncached token is EP-B (+0.276 per 1k), with C1 second (+0.230 per 1k); EP-G recovers the least per
token despite its large context. Recommendation only: a 5 s block context, not the full run-up, is
the best thing for the dashcam cloud, and the device-gating of Part 5 should pick WHICH instants get
that cloud call. The user decides.
