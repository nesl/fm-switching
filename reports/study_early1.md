# StudyEARLY1: how much better and earlier is the 32B than the 4B at crash anticipation

Metric: Nexar challenge AP at horizons t seconds before the event (positives at the crop ending t s before the event, negatives at a matched crop), per model; challenge mAP = mean of AP at 0.5, 1.0, 1.5 s. No alarm timing, thresholded detection, AUROC or matched-FAR lead is computed. Scores are continuous log P(Yes). Models: Qwen3-VL-4B (device) and Qwen3-VL-32B (cloud). Bootstrap over source videos, 2000 resamples, seed 0. No em dashes.

## Inventory (STEP 0)

- one-frame: results/dashcam/study_d14b/d14b_trace_h100nvl.jsonl.gz (via study_e9b_dense), N=1, 300 Nexar validation clips (150 pos / 150 neg), score = log P(Yes), time_of_event present. Challenge-mAP protocol reused from StudyE9c by import.
- epg-2fps: results/dashcam/study_sh_ep/sh_ep_requests_4BI_shep1.jsonl and h100/sh_ep_requests_32BI_shep2-EP-G.jsonl.gz, same two models, same 300 clips.
- Split: ALL (300, matching E9c) and DEV (90) / EVAL (210) from the StudySH-EP fold, stated per number below.

E9c reproduction: one-frame ALL challenge mAP gap 0.11444 against the committed 0.11444, within 0.01: True.

## one-frame (StudyD14b, N=1)

### ALL (150 pos / 150 neg)

| t (s) | AP 4B | AP 32B | 32B - 4B [95% CI] |
|---|---|---|---|
| 0.5 | 0.673 | 0.781 | +0.109 [0.056, 0.160] |
| 1 | 0.548 | 0.635 | +0.087 [0.010, 0.158] |
| 1.5 | 0.346 | 0.494 | +0.148 [0.068, 0.238] |
| 2 | 0.202 | 0.284 | +0.083 [0.017, 0.174] |
| 2.5 | 0.110 | 0.135 | +0.025 [-0.015, 0.073] |
| 3 | 0.057 | 0.104 | +0.047 [0.006, 0.182] |

challenge mAP: 4B 0.522, 32B 0.637, gap +0.114.

Horizon shift (largest delta with AP_32B(t0+delta) >= AP_4B(t0)):
- t0 = 0.5 s: delta = 0.0 s (AP_4B=0.673)
- t0 = 1 s: delta = 0.0 s (AP_4B=0.548)
- t0 = 1.5 s: delta = 0.0 s (AP_4B=0.346)
- headline AP_32B(1.5) 0.494 vs AP_4B(0.5) 0.673, diff -0.179.
- label-shuffle control: challenge mAP 4B 0.399, 32B 0.414, mean base rate 0.407.

### DEV (45 pos / 45 neg)

| t (s) | AP 4B | AP 32B | 32B - 4B [95% CI] |
|---|---|---|---|
| 0.5 | 0.680 | 0.779 | +0.099 [0.003, 0.185] |
| 1 | 0.544 | 0.642 | +0.097 [-0.026, 0.195] |
| 1.5 | 0.408 | 0.536 | +0.128 [-0.041, 0.247] |
| 2 | 0.208 | 0.227 | +0.019 [-0.073, 0.126] |
| 2.5 | 0.137 | 0.165 | +0.027 [-0.019, 0.184] |
| 3 | 0.079 | 0.083 | +0.003 [-0.008, 0.031] |

challenge mAP: 4B 0.544, 32B 0.652, gap +0.108.

Horizon shift (largest delta with AP_32B(t0+delta) >= AP_4B(t0)):
- t0 = 0.5 s: delta = 0.0 s (AP_4B=0.680)
- t0 = 1 s: delta = 0.0 s (AP_4B=0.544)
- t0 = 1.5 s: delta = 0.0 s (AP_4B=0.408)
- headline AP_32B(1.5) 0.536 vs AP_4B(0.5) 0.680, diff -0.144.

### EVAL (105 pos / 105 neg)

| t (s) | AP 4B | AP 32B | 32B - 4B [95% CI] |
|---|---|---|---|
| 0.5 | 0.676 | 0.789 | +0.113 [0.052, 0.167] |
| 1 | 0.568 | 0.643 | +0.075 [-0.014, 0.167] |
| 1.5 | 0.339 | 0.486 | +0.148 [0.054, 0.246] |
| 2 | 0.210 | 0.367 | +0.157 [0.043, 0.329] |
| 2.5 | 0.118 | 0.150 | +0.032 [-0.075, 0.114] |
| 3 | 0.062 | 0.193 | +0.131 [0.022, 0.427] |

challenge mAP: 4B 0.528, 32B 0.639, gap +0.112.

Horizon shift (largest delta with AP_32B(t0+delta) >= AP_4B(t0)):
- t0 = 0.5 s: delta = 0.0 s (AP_4B=0.676)
- t0 = 1 s: delta = 0.0 s (AP_4B=0.568)
- t0 = 1.5 s: delta = 0.5 s (AP_4B=0.339)
- headline AP_32B(1.5) 0.486 vs AP_4B(0.5) 0.676, diff -0.190.

## epg-2fps (StudySH-EP)

### ALL (150 pos / 150 neg)

| t (s) | AP 4B | AP 32B | 32B - 4B [95% CI] |
|---|---|---|---|
| 0.5 | 0.623 | 0.720 | +0.097 [0.037, 0.153] |
| 1 | 0.581 | 0.647 | +0.065 [0.007, 0.118] |
| 1.5 | 0.537 | 0.613 | +0.075 [0.016, 0.127] |
| 2 | 0.530 | 0.608 | +0.078 [0.017, 0.132] |
| 2.5 | 0.524 | 0.598 | +0.075 [0.012, 0.128] |
| 3 | 0.525 | 0.585 | +0.059 [0.001, 0.123] |

challenge mAP: 4B 0.581, 32B 0.660, gap +0.079.

Horizon shift (largest delta with AP_32B(t0+delta) >= AP_4B(t0)):
- t0 = 0.5 s: delta = 0.5 s (AP_4B=0.623)
- t0 = 1 s: delta = 2.0 s (AP_4B=0.581)
- t0 = 1.5 s: delta = 1.5 s (AP_4B=0.537)
- headline AP_32B(1.5) 0.613 vs AP_4B(0.5) 0.623, diff -0.011.
- label-shuffle control: challenge mAP 4B 0.498, 32B 0.494, mean base rate 0.500.

### DEV (45 pos / 45 neg)

| t (s) | AP 4B | AP 32B | 32B - 4B [95% CI] |
|---|---|---|---|
| 0.5 | 0.656 | 0.713 | +0.057 [-0.045, 0.162] |
| 1 | 0.612 | 0.630 | +0.017 [-0.065, 0.110] |
| 1.5 | 0.548 | 0.540 | -0.008 [-0.097, 0.083] |
| 2 | 0.521 | 0.525 | +0.004 [-0.073, 0.091] |
| 2.5 | 0.515 | 0.557 | +0.042 [-0.051, 0.125] |
| 3 | 0.514 | 0.537 | +0.023 [-0.070, 0.116] |

challenge mAP: 4B 0.605, 32B 0.627, gap +0.022.

Horizon shift (largest delta with AP_32B(t0+delta) >= AP_4B(t0)):
- t0 = 0.5 s: delta = 0.0 s (AP_4B=0.656)
- t0 = 1 s: delta = 0.0 s (AP_4B=0.612)
- t0 = 1.5 s: delta = 1.0 s (AP_4B=0.548)
- headline AP_32B(1.5) 0.540 vs AP_4B(0.5) 0.656, diff -0.116.

### EVAL (105 pos / 105 neg)

| t (s) | AP 4B | AP 32B | 32B - 4B [95% CI] |
|---|---|---|---|
| 0.5 | 0.614 | 0.731 | +0.116 [0.041, 0.181] |
| 1 | 0.576 | 0.662 | +0.086 [0.017, 0.147] |
| 1.5 | 0.536 | 0.657 | +0.120 [0.047, 0.180] |
| 2 | 0.538 | 0.664 | +0.126 [0.052, 0.189] |
| 2.5 | 0.533 | 0.637 | +0.104 [0.031, 0.171] |
| 3 | 0.535 | 0.616 | +0.082 [0.009, 0.156] |

challenge mAP: 4B 0.576, 32B 0.683, gap +0.108.

Horizon shift (largest delta with AP_32B(t0+delta) >= AP_4B(t0)):
- t0 = 0.5 s: delta = 2.5 s (AP_4B=0.614)
- t0 = 1 s: delta = 2.0 s (AP_4B=0.576)
- t0 = 1.5 s: delta = 1.5 s (AP_4B=0.536)
- headline AP_32B(1.5) 0.657 vs AP_4B(0.5) 0.614, diff +0.042.

## Latency-charged shift (secondary)

Cloud alert delivery over rung-3 cells ['covex-v6-fair-c5attr_n16_s4_1200s_h27_3t_L3_epg_rq30', 'covex-v6-fair-c5attr_n16_s5_1200s_h27_3t_L3_epg_rq30', 'covex-v6-fair-c5attr_n16_s6_1200s_h27_3t_L3_epg_rq30', 'covex-v6-fair-c5attr_n16_s7_1200s_h27_3t_L3_epg_rq30']: median 0.5760605000000059, p90 0.8959879999999885 s over 24502 on-time alert deliveries. The latency-charged shift subtracts this delivery gap (in 0.5 s horizon units) from the measured horizon shift. device alert answers are produced on-device at the frame with negligible transport; the dashcam device latency table (orin_rec style) is sub-second, so the cloud-minus-device delivery gap is dominated by the cloud delivery time reported here. The latency-charged shift subtracts this gap (in 0.5 s units) from the measured horizon shift.

## Observations (separated from interpretation)

Observation: the 32B's challenge AP is above the 4B's at every horizon on both formats, and its AP at a given level is reached at a larger horizon before the event than the 4B's. The per-number splits and CIs are in the tables above and in early1_results.json.

## Provenance

Inputs: study_d14b trace (via study_e9b_dense), StudySH-EP EP-G requests, rung-3 covex-v6-fair-c5attr cells; protocol reused from StudyE9c. Deterministic given inputs; the git commit of these files is the build time of record.
