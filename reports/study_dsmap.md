# StudyDSMAP: delivered-stream challenge mAP per arm (D202 (4))

Delivered score per decision instant: the cloud score where an on-time cloud answer exists (outcomes.jsonl.gz, joined by opportunity_id), else the device score (dashcam_instants). Each tier Platt-calibrated on StudySH-EP DEV EP-G before mixing (D57), then the Nexar challenge protocol (E9c). Seeds 4-7 pooled; splits ALL / DEV (90) / EVAL (210) from the StudySH-EP fold. Bootstrap over clips, 2000 resamples, seed 0.

Platt maps (calibrated log-odds = a*score + b, fit on SH-EP DEV EP-G, n=1170): device 4BI a=0.0346 b=0.2898; cloud 32BI a=0.0450 b=0.5808.

## Delivered-stream challenge mAP per arm (EVAL), paired vs rung 3

| arm | mAP ALL | mAP EVAL [95% CI] | EVAL vs rung3 [CI] | EVAL vs device-only [CI] |
|---|---|---|---|---|
| state-shares-r1 | 0.672 | 0.673 [0.597, 0.748] | +0.017 [-0.037, +0.066] | +0.045 [-0.041, +0.119] |
| fair-c5attr-rr | 0.667 | 0.672 [0.598, 0.744] | +0.016 [-0.046, +0.074] | +0.044 [-0.041, +0.114] |
| base | 0.671 | 0.669 [0.593, 0.739] | +0.013 [-0.031, +0.052] | +0.041 [-0.029, +0.100] |
| mooncake | 0.660 | 0.664 [0.592, 0.735] | +0.009 [-0.048, +0.062] | +0.037 [-0.004, +0.071] |
| b7-edf-feasibility | 0.660 | 0.662 [0.592, 0.733] | +0.006 [-0.049, +0.060] | +0.035 [-0.006, +0.067] |
| simplestream | 0.662 | 0.662 [0.589, 0.737] | +0.006 [-0.046, +0.054] | +0.034 [-0.059, +0.117] |
| eco-llm | 0.657 | 0.659 [0.589, 0.727] | +0.003 [-0.054, +0.060] | +0.032 [-0.009, +0.063] |
| state-shares | 0.661 | 0.659 [0.590, 0.735] | +0.003 [-0.045, +0.048] | +0.031 [-0.053, +0.108] |
| fair-c5attr | 0.662 | 0.656 [0.584, 0.736] | +0.000 [+0.000, +0.000] | +0.028 [-0.046, +0.094] |
| streamscout | 0.647 | 0.651 [0.578, 0.728] | -0.005 [-0.056, +0.041] | +0.023 [-0.066, +0.104] |
| state-shares-r2 | 0.653 | 0.650 [0.581, 0.729] | -0.005 [-0.049, +0.036] | +0.023 [-0.062, +0.100] |
| state-uo-c5attr | 0.655 | 0.650 [0.581, 0.722] | -0.005 [-0.049, +0.038] | +0.023 [-0.022, +0.064] |
| llf | 0.640 | 0.639 [0.568, 0.723] | -0.017 [-0.064, +0.032] | +0.012 [-0.066, +0.088] |
| warm-all-lru | 0.640 | 0.637 [0.568, 0.717] | -0.019 [-0.084, +0.054] | +0.009 [-0.002, +0.021] |
| always-cloud-fcfs | 0.640 | 0.635 [0.567, 0.714] | -0.021 [-0.085, +0.051] | +0.007 [-0.007, +0.022] |
| fair-c5attr-gain0 | 0.640 | 0.634 [0.567, 0.712] | -0.021 [-0.069, +0.030] | +0.007 [-0.037, +0.044] |
| attentionstore-prefetch | 0.639 | 0.634 [0.566, 0.713] | -0.022 [-0.086, +0.051] | +0.006 [-0.008, +0.021] |
| lmcache | 0.639 | 0.633 [0.565, 0.713] | -0.022 [-0.087, +0.049] | +0.006 [-0.009, +0.020] |
| querystream-proactive | 0.638 | 0.632 [0.565, 0.711] | -0.023 [-0.088, +0.048] | +0.005 [-0.010, +0.019] |
| kvflow-prefetch | 0.638 | 0.632 [0.564, 0.711] | -0.023 [-0.089, +0.048] | +0.005 [-0.009, +0.018] |
| state-uo | 0.635 | 0.630 [0.561, 0.706] | -0.025 [-0.069, +0.021] | +0.003 [-0.043, +0.045] |
| device-only | 0.628 | 0.627 [0.559, 0.706] | -0.028 [-0.094, +0.046] | +0.000 [+0.000, +0.000] |
| rules | 0.630 | 0.627 [0.561, 0.703] | -0.028 [-0.090, +0.034] | -0.000 [-0.032, +0.023] |
| edf | 0.627 | 0.618 [0.550, 0.700] | -0.038 [-0.085, +0.015] | -0.010 [-0.060, +0.041] |

## Sanity

device-only delivered stream uses only device scores, so it IS the device-table computation; the two are identical by construction.

## Provenance

Inputs: each arm's cell outcomes.jsonl.gz and the per-seed dashcam_instants traces; StudySH-EP DEV EP-G for Platt; E9c challenge protocol. Deterministic given inputs.
