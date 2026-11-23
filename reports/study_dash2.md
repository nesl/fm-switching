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

The step decomposition (SH-EP format; workload format; the three mixing schemes Platt, isotonic and
rank, fitted without the evaluated clip; on-time only vs every cloud answer) is the remaining piece;
the ceiling in Part 2 already locates the loss at the workload-format step (model-level EP-G 0.683 to
cloud-every-instant 0.665), with mixing and lateness acting below the 0.048 MDE.
