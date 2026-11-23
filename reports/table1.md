# StudyTABLE1: canonical correct-by-deadline table (D209)

Pipeline sha canon 8286822f (episodic_lib 2856152b, dsmap b600c819, dashcam_episodic 1d0125c9). Seeds 4-7, four-seed means. Superseded arms dropped (D205): confidence-cascade.

Columns: robot correct-by-deadline (correct by 3 s, cloud if on time else device); robot D176 (same, excluding the over-32k context-refusal recalls); single-shot correct by 2 s (StudySS2); pooled correct-in-time over robot and single-shot units; dashcam delivered-stream Nexar challenge mAP (D199, on-time cloud only, EVAL); and the on-time service columns. The dashcam D192 per-episode attainment is beside the mAP and is NOT part of the claim.

| arm | robot | robot D176 | single-shot | pooled | dashcam mAP (EVAL) | robot on-time | SS within 2s | dash attain (D192) |
|---|---|---|---|---|---|---|---|---|
| fair-c5attr-rr | 0.514 | 0.514 | 0.599 | 0.578 | 0.672 | 0.904 | 0.987 | n/a |
| state-uo | 0.503 | 0.503 | 0.598 | 0.574 | 0.630 | 0.869 | 0.973 | n/a |
| fair-c5attr | 0.507 | 0.507 | 0.596 | 0.574 | 0.656 | 0.881 | 0.961 | n/a |
| fair-c5attr-gain0 | 0.497 | 0.497 | 0.596 | 0.571 | 0.634 | 0.866 | 0.958 | n/a |
| state-uo-c5attr | 0.491 | 0.491 | 0.596 | 0.569 | 0.650 | 0.863 | 0.951 | n/a |
| state-shares-r1 | 0.469 | 0.469 | 0.600 | 0.567 | 0.673 | 0.773 | 0.992 | n/a |
| state-shares-r2 | 0.447 | 0.447 | 0.599 | 0.561 | 0.650 | 0.741 | 0.985 | n/a |
| state-shares | 0.427 | 0.427 | 0.600 | 0.557 | 0.659 | 0.482 | 0.972 | n/a |
| base | 0.359 | 0.359 | 0.600 | 0.540 | 0.669 | 0.249 | 0.968 | n/a |
| rules | 0.341 | 0.341 | 0.578 | 0.518 | 0.627 | 0.266 | 0.719 | n/a |
| simplestream | 0.224 | 0.224 | 0.600 | 0.504 | 0.659 | 0.996 | 0.997 | n/a |
| streamscout | 0.222 | 0.222 | 0.600 | 0.504 | 0.651 | 0.955 | 0.999 | n/a |
| eco-llm | 0.281 | 0.281 | 0.559 | 0.489 | 0.662 | 0.282 | 0.380 | n/a |
| llf | 0.277 | 0.277 | 0.561 | 0.489 | 0.639 | 0.051 | 0.431 | n/a |
| mooncake | 0.276 | 0.276 | 0.558 | 0.487 | 0.664 | 0.053 | 0.373 | n/a |
| b7-edf-feasibility | 0.273 | 0.273 | 0.556 | 0.485 | 0.662 | 0.053 | 0.367 | n/a |
| edf | 0.268 | 0.278 | 0.541 | 0.472 | 0.618 | 0.030 | 0.155 | n/a |
| kvflow-prefetch | 0.268 | 0.282 | 0.535 | 0.468 | 0.632 | 0.031 | 0.098 | n/a |
| always-cloud-fcfs | 0.266 | 0.277 | 0.535 | 0.467 | 0.635 | 0.030 | 0.100 | n/a |
| device-only | 0.256 | 0.256 | 0.537 | 0.467 | 0.627 | n/a | n/a | n/a |
| warm-all-lru | 0.262 | 0.272 | 0.535 | 0.466 | 0.637 | 0.020 | 0.070 | n/a |
| attentionstore-prefetch | 0.266 | 0.279 | 0.531 | 0.464 | 0.634 | 0.026 | 0.079 | n/a |
| querystream-proactive | 0.262 | 0.275 | 0.533 | 0.464 | 0.632 | 0.022 | 0.090 | n/a |
| lmcache | 0.262 | 0.277 | 0.531 | 0.463 | 0.633 | 0.020 | 0.083 | n/a |

Dashcam is a ranking metric (challenge mAP) with no per-unit correctness, so it is not pooled into the unit count; the pooled column is robot and single-shot units only. The D192 column is the thresholded per-episode attainment, kept beside the mAP and labelled not part of the claim (D199).
