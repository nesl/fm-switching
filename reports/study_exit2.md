# StudyEXIT2: episode early exit, fit and projection (D202)

## Part C: trajectory model (StudyEXIT2-fit), fit DEV report EVAL

Platt cloud map a=0.0450 b=0.5808. Clip overlap: the workload uses 88 of 90 SH-EP DEV clips, so Part D reports EVAL-clip episodes.

| k | crash caught (EVAL) | false crash on no-crash | fire time before event (med) | false normal on crash | n_train |
|---|---|---|---|---|---|
| 2 | 0.143 | 0.067 | 0.56 s | 0.229 | 766 |
| 3 | 0.133 | 0.038 | 0.4 s | 0.219 | 721 |
| 4 | 0.162 | 0.038 | 0.48 s | 0.267 | 676 |

Reference D197 level-only trigger (EVAL): crash caught 0.095, false crash 0.029, median fire time 0.08 s. The trajectory model (level plus slope) catches more and fires earlier than the level-only trigger. The normal-exit rule generalizes poorly (DEV 10 percent target, EVAL 22 to 27 percent false normal exit) and is reported as unreliable.

## Part D: net benefit projection on rung 3 (covex-v6-fair-c5attr seeds 4-7)

Dashcam cloud GPU total over the four cells: 3210.1 s. Rung 3 delivered-stream EVAL mAP 0.656; device-only 0.627; best Part B baseline mooncake 0.664.

| pattern,k | net GPU frac | gpu saved (s) | extra (s) | mAP change vs rung3 [paired CI] | exits tc/fc/tn/fn |
|---|---|---|---|---|---|
| S_k2 | +0.2035 | 653.2 | 0.0 | -0.0234 [-0.061, +0.013] | 76/119/454/148 |
| S_k3 | +0.1622 | 520.7 | 0.0 | -0.0290 [-0.063, +0.004] | 65/96/398/125 |
| S_k4 | +0.1832 | 588.2 | 0.0 | -0.0084 [-0.045, +0.028] | 70/70/528/159 |
| D_k2 | +0.2603 | 936.6 | 101.1 | -0.0359 [-0.076, +0.001] | 90/165/653/205 |
| D_k3 | +0.2010 | 805.8 | 160.4 | -0.0276 [-0.066, +0.009] | 77/136/602/191 |
| D_k4 | +0.2068 | 883.7 | 219.8 | -0.0103 [-0.054, +0.033] | 79/118/764/236 |

Workload composition per seed (crash / no-crash episodes): s4: 172/540, s5: 192/522, s6: 173/539, s7: 187/527

Net GPU freed is an UPPER-BOUND indicator: an offline projection cannot say how freed GPU turns into fewer late alerts; that needs a live cell.

## RECOMMENDATION (pre-registered rule)

NOT NET POSITIVE: no (pattern,k) meets net GPU >= 10% with mAP change CI lower bound >= -0.01. No (pattern, k) qualifies; the numbers are in the table above. A recommendation, not a build; the user decides.

## Approximations and caveats

The mAP-change CI is a PAIRED clip bootstrap: the exit stream and the rung-3 as-served stream are scored on the same resampled clips (same seed, so the per-horizon bootstrap indices align) and the per-resample difference is taken. Pattern D uses the real cloud score at a served first-k instant and the device score as a stand-in where rung 3 did not serve it; the extra GPU is charged for every unserved first-k instant regardless. These are projection assumptions, stated so the recommendation can be read with them in view.
