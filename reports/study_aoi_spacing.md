# StudyAOI-spacing: do dashcam cloud checks interact over time?

Offline analysis, committed data only. CPU only on the Jetson AGX Orin: no GPU, no model server,
no inference. Every score is read from a committed body; every metric is computed with the
committed scorer, imported rather than re-implemented. No em dashes anywhere.

HEAD at start (`git pull --ff-only`): `a6822b85ece297e6ae3fd255b0ecf48b18909ec8`.

## 0. Question and verdict

We currently treat each dashcam decision instant (every 0.5 s) as an independent opportunity. Two
offline tests decide whether to move to an age-of-information view, where the value of a cloud
check depends on how long since the stream was last checked:

1. does the SPACING of cloud checks matter, at a fixed cloud-served budget f, on the dataset's own
   metric (streaming AP; and the challenge mAP)?
2. does a dependence show up at particular horizons before the event (challenge AP per horizon),
   even if the pooled AP hides it?

**Verdict: spacing does NOT matter.** At a fixed budget, the three event-agnostic spacing patterns
(EVEN, CLUSTERED, RANDOM) are indistinguishable on both headline metrics, at every budget and at
every horizon: the largest paired difference is 0.006 challenge mAP against a device-to-cloud gap
of 0.104 (about 5 percent of the budget's value), and almost every paired CI includes zero. This
is a REAL NEGATIVE, not inconclusive: the negative control (cloud score set equal to device)
collapses every schedule onto device-only exactly, and the FRONT / BACK sanity schedules move the
metric by 0.10 mAP, so the pipeline would show a spacing effect if one existed. The dependence that
DOES exist is on PHASE relative to the event (serving the pre-event crop instants), which no
budget-spacing rule can exploit without already knowing the event time. The redundancy timescale of
the cloud's per-instant advantage is about 0.5 to 1.0 s (gain autocorrelation 0.44 at 0.5 s, 0.30
at 1.0 s, decayed to zero by 6 s), short enough that how the budget is spaced does not change the
pooled result.

## 1. Data inventory (all committed; cited paths)

AP stays the headline. It is the Nexar dataset's own metric (challenge mAP, with streaming AP as
our committed per-instant variant), so this study informs SCHEDULING design, not a metric change.
No first-Yes, time-to-alert or threshold-crossing measure is added: those were rejected for this
project because the models are Yes/No-biased and the challenge metric is the decided headline.

| role | path | content |
|---|---|---|
| device (Orin 4B) per-instant raw score | `results/dashcam/study_orin1/orin1_dense_scores.jsonl.gz` | 42,014 rows, 300 clips, `score` = log P(Yes) on the 0.25 s grid from t=3.0 (StudyORIN1-dense, real Orin hardware) |
| cloud (32B JPEG) per-instant raw score | `results/orchestration/live2/pre/live2_pre_part2_requests.jsonl.gz` | 42,014 rows, `frame_ref`=`clip|t`, `score`=log P(Yes); the JPEG body the D105 FINAL cloud map was fit on (StudyLIVE2-pre Part 2) |
| clip meta (label, event, alert, duration, grid) | `results/dashcam/study_d14b/d14b_trace_h100nvl.jsonl.gz` | 300 clips (150 pos / 150 neg), `time_of_event`, `time_of_alert`, `duration_s` (4BI_N1 arm, via StudyE9c `read_clip_meta`) |
| D105 FINAL calibration maps + fold map | `results/orchestration/live2/calibration/live2_calibration_dense_jpeg.json` | label FINAL; per-fold Platt maps `folds.maps[k]` for tiers `device_4b_orin` and `h100_32b`; `folds.assignment` clip to fold 0..4 |
| fold definition (D6 / StudyCTRL1b) | `results/dashcam/ctrl1b/d14b_folds.json` | the committed 5-fold-by-clip assignment (sha256(file_name) mod 5, stratified by label) |

Alignment verified before scoring: the three bodies cover the identical 300 clips, with
byte-identical 0.25 s contiguous grids per clip (grid lengths 61 to 229), identical clip labels,
and the D105 fold assignment is IDENTICAL to `ctrl1b/d14b_folds.json` and to the CTRL1c assignment.

Calibration is applied with the committed `ctrl1c_calibrate.apply_map` (platt: logit = a*score + b),
CROSS-FITTED out of fold: every clip in fold k is calibrated by `folds.maps[k]` for its tier, which
was fit on the other four folds (the committed `crossfit_ctx` convention). Calibration matters here
precisely because a schedule MIXES tiers per instant: a single-tier arm's AP is invariant to a
monotone per-tier map, but a mixed stream's AP depends on where the device and cloud values sit on
a common probability scale.

## 2. Method

**Decision grid and delivery.** Decisions are made every 0.5 s (every second point of the 0.25 s
scoring grid) and held forward onto the skipped 0.25 s point, which is StudyE9b's convention ("0.5 s
decisions held forward onto the 0.25 s grid") and matches the committed live scorer's `_ap_streams`.
At each decision a schedule picks the device or the cloud tier; the chosen tier's calibrated score
at that frame is delivered and held. Every instant is covered by exactly one tier, so no delivery
is missing.

**Scorers (imported, never re-implemented).** Streaming AP is `study_e9b_dense.ApEngine`
(positives one crop per horizon at event-h, negatives every grid point; horizons 0.0 / 0.5 / 1.0 /
1.5 s, CTRL1c primary is the mean over 0.5 / 1.0 / 1.5 s). Challenge mAP is `study_e9d_delay.Challenge`
(StudyE9c's one-crop-per-clip metric at horizons 0.5 / 1.0 / 1.5 s, unweighted mean; the per-horizon
AP is the time-resolved view). Both use the committed clip-clustered paired bootstrap, 2,000
resamples, seed 0.

**Schedules.** At each cloud-served fraction f in {0.10, 0.25, 0.50, 0.75} we decide, per clip,
which of its 0.5 s decision instants are cloud-served; a served instant takes the calibrated cloud
score, every other instant the calibrated device score.

- EVEN: m = round(n*f) served instants, evenly spaced, random phase per clip, 100 seeds.
- CLUSTERED: contiguous blocks of k in {2, 4, 8}, spaced to give fraction f, random phase, 100 seeds.
- RANDOM: i.i.d. Bernoulli(f) per instant, 100 seeds.
- references: device-only (f=0), always-cloud (f=1).
- sanity: FRONT-loaded and BACK-loaded (first / last f of each clip).

Point and bootstrap vectors are averaged over the 100 phase/draw seeds (the StudyE9d placement
convention), so family CIs and paired differences are shared and paired on the same clip resamples.

**Provisional decisions** (posted with defaults; recorded in the JSON; no latency or budget choice
was contradicted by the data). (i) No cloud transit latency: a served instant delivers at its own
0.5 s decision point, held forward, with zero added delay. This isolates the value of SPACING at a
fixed budget; StudyE9d covers the cost of delay, and mixing the two would confound the question.
(ii) f is the fraction of a clip's 0.5 s DECISION instants served by the cloud. (iii) 100 seeds per
family, metric and bootstrap averaged over seeds.

## 3. Does spacing matter? (paired, EVEN vs RANDOM and CLUSTERED vs RANDOM)

Paired differences against RANDOM at the same budget, seed-averaged, with a 2,000-resample paired
clip bootstrap. Positive = the pattern beats RANDOM.

### 3.1 Pooled challenge mAP (device-to-cloud gap at zero latency: 0.504 to 0.608 = +0.104)

| f | EVEN - RANDOM | worst CLUSTERED - RANDOM | any CI excludes zero? |
|---|---|---|---|
| 0.10 | +0.0011 | -0.0004 (k2) | only CLUSTERED_k4 at h=1.5 (+0.0022) |
| 0.25 | -0.0004 | -0.0064 (k8) | CLUSTERED_k8 mAP and all horizons (negative; see caveat) |
| 0.50 | +0.0014 | +0.0002 (k2) | CLUSTERED_k4 mAP (+0.0049), CLUSTERED_k8 streaming (+0.0002) |
| 0.75 | +0.0010 | -0.0009 (k2) | none |

### 3.2 Pooled streaming AP (primary, mean over 0.5 / 1.0 / 1.5 s)

Every EVEN - RANDOM and CLUSTERED - RANDOM difference is at or below 0.0003 in magnitude and NO CI
excludes zero at any budget. Spacing is irrelevant for the streaming metric.

**Reading.** EVEN never beats RANDOM by a resolvable margin on either metric at any budget. The
clustered patterns mostly tie RANDOM; the handful of CIs that exclude zero are negligible in size
(at most 0.006 mAP, about 5 percent of the 0.104 device-to-cloud gap), a consequence of the tight
seed-averaged bootstrap turning tiny differences significant, not of a scheduling-relevant effect.
CAVEAT on the one real loser, CLUSTERED_k8 at f=0.25: its achieved budget is 0.207, not 0.25,
because blocks of 8 on short clips under-fill the target; its deficit is partly a smaller budget,
not spacing. At f=0.50, CLUSTERED_k4 is the only pattern that resolvably beats RANDOM on the
challenge mAP, by +0.005, which is below the 0.01 tolerance StudyE9 uses for "same AP".

### 3.3 Largest difference and the per-device target

The 0.25 budget is the current per-device target. At 0.25 the EVEN - RANDOM challenge-mAP gap is
-0.0004 (not resolvable) and the streaming gap is -0.00004. The largest EVEN - RANDOM challenge-mAP
gap over all budgets is +0.0014 at f=0.50 (not resolvable). There is no budget at which spacing
matters.

## 4. Time-resolved view: challenge AP at each horizon

One crop per clip at event - h. The cloud's advantage over the device is real and present at every
horizon, largest at the shortest horizon; the event-agnostic spacing patterns are indistinguishable
from one another at every horizon; FRONT / BACK show where the value actually sits.

| arm | h=0.5 | h=1.0 | h=1.5 | mAP |
|---|---|---|---|---|
| device-only | 0.660 | 0.500 | 0.354 | 0.504 |
| always-cloud | 0.772 | 0.617 | 0.435 | 0.608 |
| EVEN @ f=0.25 | 0.700 | 0.533 | 0.383 | 0.539 |
| RANDOM @ f=0.25 | 0.700 | 0.534 | 0.383 | 0.539 |
| CLUSTERED_k4 @ f=0.25 | 0.704 | 0.538 | 0.382 | 0.541 |
| FRONT @ f=0.25 | 0.663 | 0.509 | 0.365 | 0.512 |
| BACK @ f=0.25 | 0.662 | 0.502 | 0.354 | 0.506 |
| EVEN @ f=0.50 | 0.729 | 0.569 | 0.401 | 0.566 |
| RANDOM @ f=0.50 | 0.728 | 0.564 | 0.402 | 0.565 |
| CLUSTERED_k4 @ f=0.50 | 0.732 | 0.568 | 0.410 | 0.570 |
| FRONT @ f=0.50 | 0.776 | 0.610 | 0.419 | 0.602 |
| BACK @ f=0.50 | 0.649 | 0.503 | 0.369 | 0.507 |

At f=0.50, FRONT-loading reaches challenge mAP 0.602, nearly always-cloud (0.608), while
BACK-loading sits at 0.507, nearly device-only (0.504). The Nexar events lie in the middle to
latter part of these clips, and the challenge crops are at event - h, so FRONT at 0.5 covers the
crop region and BACK misses it. PHASE relative to the event dominates the metric, by about 0.10 mAP,
while the agnostic spacing patterns, which do not know the event time, all land in between and tie.
A scheduler cannot convert this into a policy without a runtime signal for when the event is about
to happen, which is the very thing it is trying to detect.

## 5. Redundancy timescale: autocorrelation of the cloud-minus-device gain

Gain(t) = calibrated cloud logit - calibrated device logit at each 0.5 s decision, per clip;
autocorrelation averaged over all 300 clips. Mean gain -0.050, mean absolute per-clip gain 0.289,
mean per-clip variance 0.234.

| lag (s) | 0.5 | 1.0 | 1.5 | 2.0 | 2.5 | 3.0 | 3.5 | 4.0 | 5.0 | 6.0 |
|---|---|---|---|---|---|---|---|---|---|---|
| mean ACF | 0.444 | 0.302 | 0.232 | 0.184 | 0.149 | 0.114 | 0.077 | 0.067 | 0.032 | 0.001 |

The gain crosses 1/e (0.368) between 0.5 and 1.0 s, so the redundancy timescale is about 0.5 to
1.0 s, roughly one to two decision steps; the series never goes negative and reaches zero by 6 s.
The cloud's per-instant advantage is only weakly correlated across consecutive instants, which is
the direct reason spacing does not matter: there is no block of strongly redundant instants that a
spread-out schedule would avoid or a clustered schedule would waste.

## 6. Mechanism verification (CLAUDE.md)

This is an offline analysis, not a simulator policy, but the spacing claim is causal and is verified.

- **Causal chain.** If the cloud's per-instant advantage over the device were correlated across
  consecutive instants (a redundancy timescale longer than the inter-check spacing), then at a fixed
  budget a schedule that SPREADS its checks would sample more independent information than one that
  CLUSTERS them, and the pooled AP would be higher for EVEN than for CLUSTERED, with RANDOM between.
- **Instantiated quantity.** The implementing quantity is the paired AP difference between spacing
  patterns at matched budget. It is present and non-degenerate (the metric responds to placement:
  FRONT 0.602 vs BACK 0.507 at f=0.5, and device-only 0.504 vs always-cloud 0.608), and the gain
  autocorrelation that the claim needs is non-zero at short lag (0.44 at 0.5 s). The quantity simply
  does not vary across EVEN / CLUSTERED / RANDOM.
- **Negative control (Step 4).** With the cloud score set equal to the device score, spacing carries
  no information; every schedule reproduced device-only to worst absolute difference 0.0. The link is
  wired correctly and the metric would move if spacing mattered.
- **Alternative explanation.** The same flat result would arise if the pipeline were insensitive to
  WHICH instants are cloud-served. Ruled out by FRONT / BACK (0.10 mAP apart) and by the endpoints,
  so the flatness is a property of the data, not of the instrument.
- **Classification (Rule 2): REAL NEGATIVE.** The mechanism is present, the control changes the
  result, and spacing still does not produce the effect. An age-of-information view keyed to spacing
  pattern is not warranted by this data.

## 7. Results consistency check (CLAUDE.md six checks)

1. **Cross-check against committed measurements.** Single-tier AP is invariant to a monotone
   per-tier calibration, so the reference arms depend only on the raw scores. This run is zero
   latency, so the right anchor is StudyE9c's zero-latency arms. always-cloud challenge mAP 0.6079
   vs StudyE9c 32BI_N1 zero 0.6368 (ratio 0.955); device-only 0.5044 vs StudyE9c 4BI_N1 zero 0.5223
   (ratio 0.966). Both within 5 percent, with the expected direction: this run's cloud is the JPEG
   32B body (vs PNG H100) and the device is the Orin 4B (vs H100 4B, StudyORIN1-dense reported a ~1
   log-unit offset but an indistinguishable challenge AP, 0.5735 vs 0.5764). No disagreement exceeds
   2x.
2. **Physical plausibility.** All AP values lie between the committed device-only and always-cloud
   levels; no schedule exceeds always-cloud or falls below device-only. No rate or level is faster
   or higher than the committed curves.
3. **Distribution sanity.** Every cell carries a 2,000-resample clip-bootstrap CI; the mixed
   schedules do not collapse to a constant (they range 0.504 to 0.608 with f), and the per-seed
   averaging is over 100 distinct phase/draw seeds.
4. **Definition audit.** Streaming AP, challenge mAP, the horizons (0.0/0.5/1.0/1.5 and 0.5/1.0/1.5),
   the 0.25 s grid, the 0.5 s decision cadence, the sample-and-hold, the clip-bootstrap and the
   D105 cross-fitting folds are all the committed objects, used through the committed modules.
5. **Claim linkage.** Bears on whether scheduling should move to an age-of-information value
   (StudyCTRL1c's per-device budget target of 25 percent): it should not, on spacing grounds.
6. **Proxy validity.** Two proxies, both stated: the device tier is the Orin 4B dense body, a valid
   device-tier score (StudyORIN1-dense), not the H100 4B; and no cloud transit latency is modelled,
   so these numbers isolate spacing value and are not delivered-quality numbers (StudyE9d covers
   delay). Neither proxy affects the spacing verdict, which is a within-run comparison at matched
   budget and matched latency.

## 8. Answers to the brief's questions

- Does EVEN beat RANDOM, or CLUSTERED lose to RANDOM, on pooled AP? At which horizons? No. EVEN
  never resolvably beats RANDOM on streaming AP or challenge mAP at any budget or horizon. CLUSTERED
  ties RANDOM except for negligible blips (k4 +0.005 mAP at f=0.5; k8 -0.006 at f=0.25, confounded
  by a 0.207 achieved budget). No horizon shows a spacing effect.
- At which f is the difference largest? There is no resolvable difference; the largest point gap is
  +0.0014 mAP (EVEN - RANDOM) at f=0.50. At the 0.25 target the gap is -0.0004.
- Is the cloud's per-instant gain autocorrelated across consecutive instants? Weakly: ACF 0.44 at
  0.5 s, 0.30 at 1.0 s, 0 by 6 s. The redundancy timescale is about 0.5 to 1.0 s.

## 9. Outputs

- `results/dashcam/study_aoi/aoi_spacing_results.json` (with `_provenance`).
- Script `experiments/dashcam/study_aoi_spacing.py` (CPU only; imports the committed scorers and the
  committed calibration map; runs no model).
- This report.
