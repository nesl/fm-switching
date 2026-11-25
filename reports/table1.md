# StudyTABLE1: canonical correct-by-deadline table (D209)

Pipeline sha canon 298d8315 (episodic_lib 35e3c57e, dsmap 35e3c57e, dashcam_episodic 1d0125c9). Seeds 4-7, four-seed means. Superseded arms dropped (D205): confidence-cascade.

Columns: robot correct-by-deadline (correct by 3 s, cloud if on time else device); robot D176 (same, excluding the over-32k context-refusal recalls); single-shot correct by 2 s (StudySS2); pooled correct-in-time over robot and single-shot units; dashcam delivered-stream Nexar challenge mAP (D199, on-time cloud only, EVAL); the on-time service columns; and the dashcam per-episode on-time attainment SERVICE columns.

| arm | robot | robot D176 | single-shot | pooled | dashcam mAP (EVAL) | robot on-time | SS within 2s | dash per-episode on-time attainment | dash episodes >= 0.25 |
|---|---|---|---|---|---|---|---|---|---|
| fair-c5attr-rr | 0.514 | 0.514 | 0.599 | 0.578 | 0.672 | 0.904 | 0.987 | 0.729 | 0.887 |
| state-uo | 0.503 | 0.503 | 0.598 | 0.574 | 0.630 | 0.869 | 0.973 | 0.223 | 0.338 |
| fair-c5attr | 0.507 | 0.507 | 0.596 | 0.574 | 0.656 | 0.881 | 0.961 | 0.502 | 0.665 |
| fair-c5attr-gain0 | 0.497 | 0.497 | 0.596 | 0.571 | 0.634 | 0.866 | 0.958 | 0.254 | 0.367 |
| state-uo-c5attr | 0.491 | 0.491 | 0.596 | 0.569 | 0.650 | 0.863 | 0.951 | 0.291 | 0.422 |
| state-shares-r1 | 0.469 | 0.469 | 0.600 | 0.567 | 0.673 | 0.773 | 0.992 | 0.785 | 0.922 |
| state-shares-r2 | 0.447 | 0.447 | 0.598 | 0.560 | 0.650 | 0.741 | 0.985 | 0.784 | 0.935 |
| state-shares | 0.427 | 0.427 | 0.600 | 0.557 | 0.659 | 0.482 | 0.972 | 0.766 | 0.918 |
| base | 0.359 | 0.359 | 0.600 | 0.540 | 0.669 | 0.249 | 0.968 | 0.528 | 0.651 |
| rules | 0.341 | 0.341 | 0.578 | 0.518 | 0.627 | 0.266 | 0.719 | 0.102 | 0.145 |
| streamscout | 0.222 | 0.222 | 0.600 | 0.504 | 0.651 | 0.955 | 0.999 | 0.775 | 0.980 |
| simplestream | 0.209 | 0.209 | 0.600 | 0.501 | 0.662 | 0.998 | 0.999 | 0.949 | 0.999 |
| eco-llm | 0.272 | 0.272 | 0.565 | 0.492 | 0.659 | 0.352 | 0.473 | 0.411 | 0.465 |
| llf | 0.277 | 0.277 | 0.561 | 0.489 | 0.639 | 0.051 | 0.431 | 0.621 | 0.763 |
| mooncake | 0.276 | 0.276 | 0.558 | 0.487 | 0.664 | 0.053 | 0.373 | 0.326 | 0.370 |
| b7-edf-feasibility | 0.273 | 0.273 | 0.556 | 0.485 | 0.662 | 0.053 | 0.367 | 0.324 | 0.368 |
| edf | 0.268 | 0.278 | 0.541 | 0.472 | 0.618 | 0.030 | 0.155 | 0.272 | 0.361 |
| kvflow-prefetch | 0.268 | 0.282 | 0.535 | 0.468 | 0.632 | 0.031 | 0.098 | 0.079 | 0.092 |
| always-cloud-fcfs | 0.266 | 0.277 | 0.535 | 0.467 | 0.635 | 0.030 | 0.100 | 0.080 | 0.094 |
| device-only | 0.256 | 0.256 | 0.537 | 0.467 | 0.627 | n/a | n/a | 0.000 | 0.000 |
| warm-all-lru | 0.262 | 0.272 | 0.535 | 0.466 | 0.637 | 0.020 | 0.070 | 0.055 | 0.066 |
| attentionstore-prefetch | 0.266 | 0.279 | 0.531 | 0.464 | 0.634 | 0.026 | 0.079 | 0.078 | 0.092 |
| querystream-proactive | 0.262 | 0.275 | 0.533 | 0.464 | 0.632 | 0.022 | 0.090 | 0.077 | 0.089 |
| lmcache | 0.262 | 0.277 | 0.531 | 0.463 | 0.633 | 0.020 | 0.083 | 0.079 | 0.093 |

Dashcam is a ranking metric (challenge mAP) with no per-unit correctness, so it is not pooled into the unit count; the pooled column is robot and single-shot units only.

**Dashcam per-episode on-time attainment** is the dashcam SERVICE metric, scored by d179_rung2_verdict.py's definition (D179 (6) check 1): for each alert episode, the count of on-time CLOUD alert instants (committed delivery rule, L = 1.0 s, D144/D146 passes; device on-time is never added) over the flat D178 denominator of 19 (positions 2 to 20 of the 21-frame episode), meaned over episodes; the next column is the fraction of episodes at or above the 0.25 target (D178 (1), the scorer's p_dash). This is SEPARATE from the D192 thresholded episode correctness. Device-only has no on-time cloud alerts, so its attainment is 0 by definition.

## Paired question-clustered CIs (correct-in-time diff, 2000 reps, seed 0)

Diff = arm minus comparator, pooled over seeds 4-7, clusters resampled by question identity. Positive favours the arm.

| arm | pooled vs -rr [95% CI] | pooled vs device-only [95% CI] | robot vs device-only | single-shot vs device-only |
|---|---|---|---|---|
| fair-c5attr-rr | n/a | +0.112 [+0.071, +0.155] | +0.260 [+0.208, +0.313] | +0.062 [+0.008, +0.115] |
| state-uo | -0.004 [-0.008, +0.000] | +0.108 [+0.068, +0.150] | +0.247 [+0.197, +0.300] | +0.060 [+0.007, +0.112] |
| fair-c5attr | -0.004 [-0.009, +0.001] | +0.108 [+0.070, +0.148] | +0.252 [+0.200, +0.302] | +0.059 [+0.006, +0.109] |
| fair-c5attr-gain0 | -0.007 [-0.012, -0.002] | +0.105 [+0.066, +0.146] | +0.241 [+0.190, +0.293] | +0.059 [+0.006, +0.110] |
| state-uo-c5attr | -0.009 [-0.014, -0.004] | +0.103 [+0.063, +0.144] | +0.235 [+0.185, +0.288] | +0.058 [+0.006, +0.108] |
| state-shares-r1 | -0.011 [-0.019, -0.005] | +0.100 [+0.060, +0.142] | +0.212 [+0.162, +0.263] | +0.062 [+0.008, +0.114] |
| state-shares-r2 | -0.018 [-0.027, -0.010] | +0.094 [+0.054, +0.135] | +0.190 [+0.141, +0.240] | +0.061 [+0.008, +0.112] |
| state-shares | -0.021 [-0.033, -0.010] | +0.090 [+0.052, +0.131] | +0.171 [+0.134, +0.212] | +0.063 [+0.010, +0.113] |
| base | -0.039 [-0.053, -0.025] | +0.073 [+0.034, +0.112] | +0.103 [+0.076, +0.132] | +0.063 [+0.009, +0.115] |
| rules | -0.060 [-0.078, -0.042] | +0.052 [+0.020, +0.085] | +0.085 [+0.056, +0.115] | +0.041 [-0.004, +0.082] |
| streamscout | -0.075 [-0.090, -0.059] | +0.037 [-0.005, +0.081] | -0.039 [-0.087, +0.006] | +0.063 [+0.007, +0.116] |
| simplestream | -0.077 [-0.093, -0.062] | +0.034 [-0.007, +0.078] | -0.049 [-0.093, -0.002] | +0.063 [+0.007, +0.116] |
| eco-llm | -0.095 [-0.124, -0.068] | +0.014 [-0.010, +0.038] | +0.029 [-0.002, +0.059] | +0.027 [-0.001, +0.055] |
| llf | -0.089 [-0.115, -0.063] | +0.022 [-0.001, +0.046] | +0.021 [+0.008, +0.035] | +0.023 [-0.007, +0.053] |
| mooncake | -0.091 [-0.121, -0.062] | +0.020 [+0.003, +0.037] | +0.019 [+0.008, +0.031] | +0.021 [-0.003, +0.044] |
| b7-edf-feasibility | -0.094 [-0.123, -0.064] | +0.018 [+0.001, +0.036] | +0.016 [+0.006, +0.029] | +0.019 [-0.004, +0.041] |
| edf | -0.106 [-0.142, -0.070] | +0.006 [-0.005, +0.017] | +0.013 [+0.002, +0.025] | +0.003 [-0.012, +0.017] |
| kvflow-prefetch | -0.111 [-0.152, -0.070] | +0.002 [-0.009, +0.013] | +0.014 [+0.005, +0.025] | -0.002 [-0.016, +0.013] |
| always-cloud-fcfs | -0.111 [-0.151, -0.071] | +0.002 [-0.009, +0.013] | +0.012 [+0.003, +0.022] | -0.002 [-0.017, +0.013] |
| device-only | -0.112 [-0.155, -0.071] | n/a | n/a | n/a |
| warm-all-lru | -0.113 [-0.152, -0.072] | -0.000 [-0.009, +0.009] | +0.007 [+0.001, +0.015] | -0.003 [-0.014, +0.008] |
| attentionstore-prefetch | -0.114 [-0.158, -0.074] | -0.002 [-0.011, +0.007] | +0.012 [+0.003, +0.023] | -0.006 [-0.019, +0.004] |
| querystream-proactive | -0.114 [-0.157, -0.074] | -0.002 [-0.011, +0.007] | +0.008 [+0.001, +0.016] | -0.005 [-0.017, +0.007] |
| lmcache | -0.115 [-0.158, -0.076] | -0.003 [-0.012, +0.005] | +0.008 [+0.001, +0.016] | -0.006 [-0.019, +0.004] |

The dashcam delivered-stream mAP paired CIs vs rung 3 and device-only are in the StudyDSMAP report (reports/study_dsmap.md); they are not separable (all span 0, MDE 0.048 > arm gaps).
