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
