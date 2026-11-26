# StudyDASH-DIAG: why every arm is below device-only on dashcam

Read-only, committed data, nothing fixed. Scripts: `experiments/analysis/oracle/dashcam_diagnosis.py`
(parts 1 to 3) and the inline per-instant check recorded below. Scores: SH-EP EP-G per-instant
(DEV and EVAL) and the live s4 1x trace (`simplestream` dense cloud for the cloud tier).

## 1. Episode false-alarm rate per tier (no-crash clips, any instant over threshold)

| threshold set | split | device FAR | cloud FAR | n clips |
|---|---|---|---|---|
| D197 episode | DEV | 8.9% | 8.9% | 45 |
| D197 episode | EVAL | 3.8% | 2.9% | 105 |
| instant (score_cell) | DEV | 22.2% | 26.7% | 45 |
| instant (score_cell) | EVAL | 19.1% | 15.2% | 105 |

The D197 DEV 10% target holds on EVAL, and EVAL is lower, not higher. The instant thresholds do not
hold: episode-level FAR is 15 to 27% against a per-instant target of 3 to 5%, and the tier ordering
flips between DEV and EVAL.

## 2. Mixing

A mixed walk crosses only at instants where its own tier crosses. Every crossing of the mixed walk is
therefore a crossing of the device walk or the cloud walk, so mixing cannot add crossings. The
"extra chance" count is 0 by construction, not by measurement. Live s4 at D197, no-crash episodes
(n = 540): device-only FA 30, cloud-only FA 68, rung 3 (mixed) FA 61. The mixed stream sits between
the pure tiers, so mixing does not explain the negative shares.

## 3. Correctness at D197, live s4 1x (crash n = 172, no-crash n = 540)

| arm | crash correct | no-crash correct | total |
|---|---|---|---|
| device-only (floor) | 13 | 510 | 523 |
| rung 3 covex-v6-fair-final | 17 | 479 | 496 |
| cloud-only | 23 | 472 | 495 |

Cloud adds 4 to 10 crash detections and costs 31 to 38 no-crash episodes. The sign is real at D197 as
well as at the instant level (rung 3 at instant thresholds: 425 against floor 435).

## 4. Challenge metric (D199, committed DSMAP `reports/figures/dsmap_results.json`, ALL split, seeds 4 to 7)

Device-only challenge mAP 0.628. Base 0.671, fair-c5attr 0.662, simplestream 0.662, state-uo 0.635.
Nearly every arm is ABOVE device-only on the challenge metric and BELOW it on episode correctness.
The two metrics disagree in direction. (Different seed scopes: DSMAP pools seeds 4 to 7, episode
correctness is s4 only.)

## 5. Cause

The negative shares come from the cloud tier's operating point, not from ranking and not from mixing
and not from an arithmetic bug (the episode model matches the committed score_cell and the device
floor is reproduced exactly).

- Per-instant threshold transfer, cloud tier only. On no-crash instants the device score transfers:
  live FA 0.63% against SH-EP EVAL 0.77%. The cloud score does not: live FA 2.34% against SH-EP EVAL
  0.24%, about 10 times higher. The medians agree (live -14.4, SH-EP -14.5), so the gap is in the
  upper tail.
- The episode walk over dense instants amplifies a per-instant tail (more instants, more chances).
  This is why per-instant calibration does not give an episode FAR of 10%.
- The likely source of the tail is a context difference: SH-EP cloud scores are fresh-clip, while
  live cloud scores come from accumulated session history. That is a hypothesis, not verified here.

So the cloud threshold was calibrated on a score distribution that the live cloud does not produce.
The challenge metric is threshold-free and says the cloud ranks better. Episode correctness
penalises its operating point. The dashcam shares measure the threshold, not the policy, and should
not be used as policy evidence until the cloud threshold is recalibrated on live-context scores.
This is a calibration/transfer finding for a decision, not a fix made here.

## Limits

- Part 3 and the instant check are s4 only. The challenge comparison pools s4 to s7.
- The live cloud score source is the dense simplestream trace, not a per-arm request stream.
- Context-dependence of the cloud tail is a hypothesis; it would need a fresh-context vs warm-context
  score comparison on the same instants to confirm.

## Rulings applied (2026-11-25)

### 1. Dashcam thresholds recalibrated on live DEV clips (D6), both tiers
Rule = D197 (k-th largest no-crash episode max, k = ceil(0.10 n)). Clips: SH-EP DEV split, negatives only,
one episode per clip (max over instants and seeds 4 to 7). EVAL not read.
- Device theta = -0.0335 (D197 -0.2014; instant -2.5789). Cloud theta = -0.3869 (D197 -2.9298; instant -6.8760).
- Achieved DEV episode FAR 11.1% (5 of 45), D197 rule.

Shares beside the current ones (pooled over seeds, 1x; FAIR / HINDSIGHT):

| arm | instant (current) | live DEV (recalibrated) |
|---|---|---|
| fair-final-rung3 | -0.402 / -0.152 | -4.505 / -0.244 |
| base | -0.292 / -0.082 | -4.003 / -0.064 |
| state-uo | -0.157 / -0.076 | -3.188 / -0.051 |
| simplestream | -0.455 / -0.080 | -4.668 / -0.090 |
| confidence-cascade (flagged superseded) | -0.077 / +0.164 | -2.740 / +0.013 |

Live DEV crash-episode accuracy under the recalibrated thresholds is 5.1% device and 2.8% cloud, against
0.247 and 0.377 at the instant thresholds. The FAIR dashcam shares of -2 to -5 come from a denominator
near zero: the oracle gain on crash episodes is zero when cloud is worse than device there, so the
per-type share is not interpretable. The HINDSIGHT dashcam oracle falls from 63 to 2 units.

Why the recalibrated thresholds collapse: the pre-event maxima of DEV positives agree with SH-EP
(live device median -3.95 against -3.53; cloud -6.0 against -7.5). The threshold moves because it is an
order statistic over 45 negatives, k = 5, so it sits in a noisy top tail. That tail is near zero for
live device scores, where the crash maxima sit near -4. So the episode dashcam measure has little
crash separation at a 10% FAR operating point under either threshold set.

Headline for dashcam is the Nexar challenge metric (D199, committed DSMAP, Platt-calibrated, unaffected
by these thresholds): device-only 0.628, base 0.671, fair-c5attr 0.662, state-uo 0.635. Most arms rank
above device-only on challenge mAP.

### 2. h0.5 T-constrained LP
Driver `experiments/analysis/oracle/oracle_lp_d270.py`, D270 valuation (recall FAIR gain
acc[recall, cloud, WITH_HISTORY] minus acc[recall, device]; single-shot unchanged; dashcam per mode).
- Per type, capacity does not bind at T: 1x T = 17945.2 and h0.5 T = 11619.8 give identical values to 1.10T.
- The pooled LP reports capacity_binds = True, but its value is 94.314 for every T from 1000 tok/s up to 1e9.
  The flag marks a tight constraint, not a moved objective. The oracle value first falls below about
  1000 tok/s. Mean demand is about 380 tok/s (456k uncached tokens over 1200 s).
- So the T-constrained oracle equals the per-unit oracle at both T. The h0.5 shares in
  `oracle_h05_shares.json` stand under the same valuation.
- kv0.5r is retired. Its T mismatch (15569.8 measured on `_kv0.5`, applied to `_kv0.5r`) is flagged, not fixed.

### 3. D270 control (as implemented)
FAIR conditioned on context sent. Dashcam share<0 reported, not blocking. Share>1 is a hard STOP. Dashcam
floor definition unchanged (device-only). HINDSIGHT >= FAIR oracle is checked pooled and per seed against
the clustered bootstrap CI. A failure is blocking only when the gap exceeds the CI. Both threshold modes
pass pooled and for every seed (1x). D270 is not in the repo log. This implementation matches the
context-sent conditioning recorded as D268 corrected, so no new valuation was introduced.

## Candidate A dashcam measure: GATE FAILED (2026-11-25), STOP, no substitute

Measure: per-instant Platt crash probability per tier (raw score; 5-fold cross-fit by clip, committed
fold rule), labels 0.5 to 3.0 s lead window vs no-crash, value = Brier improvement of the cloud
probability over the device probability. Script `experiments/analysis/oracle/dashcam_brier.py`; output
`results/orchestration/live2/oracle/dashcam_brier_candidateA.json`. Gate pre-registered in the script header.

- G1 (cloud-only beats device-only): FAIL. Device Brier 0.0974, cloud Brier 0.1116, mean improvement
  -0.0142 (CI -0.0206 to -0.0079); log-loss improvement -0.0276. n = 25,622 labelled live instants
  (1,817 positive, 23,805 negative), seeds 4 to 7, 1x.
- G2 (arm ordering agrees with DSMAP challenge mAP): FAIL. Spearman rho = -0.63 (CI -0.71 to -0.55)
  across 23 arms. The realised cloud gain orders arms opposite to challenge mAP.

Reading: on the live trace the cloud probability is worse than the device probability for the same
instants, and the arms that serve cloud more score worse on this measure while scoring better on the
challenge metric. This matches the threshold finding above: the cloud score tail on live no-crash
instants is heavier than the SH-EP calibration sample. The calibration source here is SH-EP (all 300
clips, cross-fitted), so the live-versus-calibration transfer is the likely cause, not a fold leak (folds
are by clip, and each clip is scored by a map from the other folds). This is a diagnosis, not verified.

Per the gate, no oracle shares were computed with this measure and the dashcam oracle is not replaced.
Candidate A cannot be used for the dashcam oracle as specified. The dashcam headline stays the Nexar
challenge metric (D199).

## PRE-REGISTRATION: live versus SH-EP cloud shift, and candidate A-prime (written before any number)

### Step 1 diagnostic (fix nothing)
Pairs: (clip, t) matched between the live cloud score (per-arm `cloud_score` in committed dashcam
outcomes, on-time, seeds 4 to 7, 1x) and the SH-EP 32B EP-G score at the same clip and time. Paired
difference d = live minus SH-EP. Reported: n, mean, median, IQR, p5 and p95, split by
(a) cache path (WARM or COLD, from the live request `cache_path`), (b) episode position (live frame
count in the request, buckets 1-4, 5-8, 9+), (c) arm.
Body check, one instant per tier: frame count (live `mm_uuids` against SH-EP `n_frames`), frame time
order, and prompt tokens against SH-EP `prompt_tokens`. JPEG bytes compared where the live record carries them.

Classification rule (fixed now):
- BODY DEFECT: frame count or frame order differs for the same instant.
- INPUT ENCODING: frame count and order match, but prompt tokens or frame bytes differ.
- CACHE-PATH DRIFT: body matches, and the mean paired difference differs between WARM and COLD by more
  than 0.5 score units and more than 2 standard errors.
- CONTEXT COMPOSITION: body matches, cache path does not explain the difference, and the mean paired
  difference changes monotonically with frame count bucket by more than 0.5 score units.
- Otherwise: UNEXPLAINED, reported as such.

### Step 2 candidate A-prime
Same measure as candidate A (Brier improvement of the cloud probability over the device probability,
0.5 to 3.0 s lead window, device as reference, no-crash negatives). The difference is the calibration:
each tier's Platt map is fitted on LIVE scores (committed 1x seeds 4 to 7, instants labelled by the
window), cross-fitted by clip with the committed `clip_to_fold` rule. Each clip is scored by a map fitted
on the other folds. Pooled across arms and seeds.
Gates (identical to candidate A, pre-registered in `dashcam_brier.py`):
- G1: mean Brier improvement of cloud over device > 0 with clip-cluster bootstrap CI lower bound > 0.
- G2: Spearman rho between per-arm realised cloud gain and DSMAP challenge mAP > 0 with CI lower bound > 0.
A failure of either gate STOPS the step. No substitution.

## Step 1 result: live versus SH-EP shift (fixes nothing)

Paired on identical (clip, t): 47,126 pairs, 155 clips, 24 arms, seeds 4 to 7, 1x. Output
`results/orchestration/live2/oracle/dashcam_shift_step1.json`, script `dashcam_shift_step1.py`.

- Paired difference (live minus SH-EP 32B): mean -0.32, median 0.00, IQR -1.25 to 0.88, p5 -5.1, p95 3.4.
- By cache path: WARM n = 43,684, mean -0.29. COLD n = 3,437, mean -0.62. Five requests had no path.
- By frame bucket (live frames in request): 1 to 4 mean -0.59; 5 to 8 mean -0.64; 9+ mean -0.07.
- By arm: means from -0.25 (mooncake) to -0.70 (attentionstore-prefetch).
- Body, same instant, live against SH-EP: frame count matches in 411 of 47,126 pairs.
  - COLD: live median 3 frames (3,211 of 3,437 at most 3) against SH-EP median 11 frames with about 3,392
    cached tokens. The COLD live request carries no cached prefix and only the new frames.
  - WARM: live median 10 frames against SH-EP median 16 frames. The prefix sits in the server cache by
    design (append-only, D148), so this difference is the designed path.
  - Frame time order is sorted in all live requests.
- Not checkable from committed data: JPEG bytes (the live record stores frame identifiers, not bytes),
  and the on-device tier request body (device-local, not recorded).

Classification (pre-registered rule), CORRECTED: NOT a body defect. The first reading classified the COLD
path as a body defect. Flash verification (commit 8d19ad8d) found zero mid-episode truncations across 127
cells. Short cold requests are episode starts and cap restarts, and the gap to SH-EP is a context definition
shared by all arms (SH-EP pre-roll), not a live-path defect. No COLD-body fix is made. The pre-registered
frame-count rule fired on a context-definition difference, so the rule's label is withdrawn, not the data.

## Candidate A-prime: GATE FAILED (2026-11-25), STOP

Live-fitted Platt per tier, clip cross-fit with the committed `clip_to_fold` rule, pooled across arms
and seeds, Brier improvement of cloud over device. Script `dashcam_brier_aprime.py`; output
`results/orchestration/live2/oracle/dashcam_brier_aprime.json`.

- G1 (cloud beats device): mean improvement +0.00033, clip-cluster CI [-0.00058, +0.00129]. FAIL,
  because the lower bound is below zero. The point estimate is positive but indistinguishable from zero.
- G2 (arm ordering agrees with challenge mAP): Spearman rho +0.72, CI [-0.54, +0.83] across 23 arms. FAIL,
  because the CI includes zero.

Both gates fail. No oracle shares computed. The dashcam oracle is not replaced. The dashcam headline stays
the Nexar challenge metric (D199). The COLD-path "body defect" label is withdrawn (see 8d19ad8d); no body fix is made.


## CORRECTION (2026-11-25): the COLD-path body defect label is withdrawn
Flash verification (commit 8d19ad8d) found zero mid-episode truncations across 127 cells. Short cold requests
are episode starts and cap restarts. The live-versus-SH-EP gap is a context definition (SH-EP pre-roll)
shared by all arms. No COLD-body fix is made.

## Headline dashcam oracle (Nexar challenge mAP): ceiling gives STOP, not a bound

Method: share = (arm mAP minus device-only mAP) divided by (ceiling mAP minus device-only mAP). Ceiling =
cloud-every-instant delivered stream (dense simplestream cloud through the cloud Platt map at every trace
instant, DSMAP Part 2 method). 1x seeds 4 to 7 pooled, one value per source clip, paired clip-cluster
bootstrap (2000 resamples, seed 0). Script `experiments/analysis/early1/dashcam_share_headline.py`; output
`results/orchestration/live2/oracle/dashcam_share_headline.json`.

- Positive control passes: device-only mAP reproduces the committed DSMAP value exactly (0.627985).
- Device-only 0.6280, ceiling 0.6657, gap 0.0377, SE of gap 0.0394. The gap is not resolved.
- Clips needed to resolve the gap at 95%: about 5,038. Available: 300 (150 positive, 150 negative).
- Three arms exceed the ceiling, share above 1: base (1.13), state-shares-r1 (1.17), fair-c5attr-rr (1.03).
  Base mAP 0.6705 is above the ceiling 0.6657. The "cloud every instant" stream is therefore not an upper
  bound on challenge mAP. AP ranks clips across the stream, so mixing device and cloud scores can beat
  all-cloud. Under D270 a share above 1 is a hard STOP.
- Only simplestream has a share CI excluding zero (+0.90, CI +0.01 to +1.83).
- Minimum detectable difference (2 x 1.96 x SE of share) runs from 31 to 1,719 share units, so no
  per-arm share is informative at this clip count.

Decision: STOP. The headline dashcam oracle cannot be a cloud-every-instant ceiling. A valid ceiling needs
a per-instant or per-clip best-of-both choice, which is not deliverable, and it would still need the clip
count above to resolve the gap. The dashcam headline stays challenge mAP with arm-versus-device-only
differences reported, not shares.

## Dashcam reporting, 1x seeds 4-7 (the dashcam oracle share is dropped, 82f5d019)

Script `experiments/analysis/early1/dashcam_reporting.py`; output `results/orchestration/live2/oracle/dashcam_reporting.json`.

(1) Challenge-mAP difference from device-only (device 0.627985, 150 positive and 150 negative clips). Paired
clip-cluster bootstrap, 2000 resamples, seed 0. Every arm is labelled UNDERPOWERED at 300 clips: each 95% CI
includes zero. Minimum detectable difference runs from 0.025 (warm-all-lru, lmcache, attentionstore-prefetch
family) to 0.15 (simplestream, state-shares-r1). Largest pooled point differences: base +0.043 (CI -0.020 to
+0.088), state-shares-r1 +0.044, fair-c5attr-rr +0.039, state-shares +0.033, simplestream +0.034. Per seed
values are in the JSON.

(2) Per-episode on-time attainment (canon.dash_attainment, D179 (6) definition; target 0.25 per D71):

| arm | mean attainment (seeds 4-7) | fraction of episodes at or above 0.25 |
|---|---|---|
| fair-final-rung3 | 0.718 | 0.877 |
| simplestream | 0.949 | 0.999 |
| base | 0.528 | 0.651 |
| edf | 0.272 | 0.361 |
| state-uo | 0.223 | 0.338 |
| always-cloud-fcfs | 0.080 | 0.094 |

Per-seed attainment for all 24 arms is in the JSON.

Pooled share scope (oracle_results.json): the pooled block now covers robot and single-shot only, recorded in
the file's `scope` field and in `pooled_over_seeds_robot_single_shot_1x`. No arm exceeds 1. Examples (FAIR /
HINDSIGHT): rung 3 0.944 / 0.475, base 0.551 / 0.313, state-uo 0.916 / 0.460, simplestream 0.326 / 0.147.
