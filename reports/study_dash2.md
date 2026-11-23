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
metric at this clip count. The best the policy can do is therefore not to chase a system-level mAP
gap that the format does not expose, but to spend its cloud budget where a cloud answer changes the
delivered score the most; Parts 4 and 5 quantify that and the allocation rules, and this paragraph is
updated when they land.

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

## Parts 3 to 5

Gap decomposition, value of a cloud answer by observable state, and the budget-matched allocation
rules with the pre-registered decision rule are computed next and appended here.
