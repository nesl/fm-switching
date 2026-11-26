# TOUCH TOKEN PREDICTION AUDIT (2026-11-26T02:56Z). CPU, committed s4 cells, as reported by the audit agent, not independently re-run. Nothing built. STOPPED per the ruling: the bulk is NOT under-predicted.
**Predicted value:** the constant 15 uncached tokens for every touch (touch_policy.py TOUCH_UNCACHED_TOKENS; D174 price 15 x 0.00018243 s). The decision log carries no per-touch predicted field, so "under-predicted" is relative to the constant. Actual = prompt_tokens - cached_tokens, joined by decision_id (8 and 11 q2 touches had no response row).
| cell | n | actual/predicted median | p10 | p90 | sum actual / sum predicted | max uncached |
|---|---|---|---|---|---|---|
| rung 3, 1x | 2,674 | 0.20 | 0.07 | 1.00 | 0.40 | 15 |
| `-q`, 1x | 906 | 0.47 | 0.47 | 0.60 | 0.48 | 9 |
| `-q2`, 1x | 10,438 | 0.33 | 0.07 | 0.73 | 0.40 | 19 |
| rung 3, halved | 1,371 | 0.20 | 0.07 | 1.00 | 2.85 | 17,651 |
| `-q`, halved | 787 | 0.47 | 0.47 | 0.60 | 1.28 | 9,521 |
| `-q2`, halved | 5,170 | 0.47 | 0.20 | 0.73 | 2.95 | 23,141 |
**At 1x the 15-token charge is a safe OVERestimate for every touch (0 re-prefills in 14,018 touches). At halved memory the bulk is unchanged (excluding re-prefills sum/pred is 0.33, 0.48, 0.47, the same as 1x); the mean is 1.3x to 3.0x under-predicted only because of 26 re-prefills (actual > 1,000 tokens): rung 3 4 (0.3 percent of touches, 88.5 percent of touch tokens), `-q` 1 (62.8 percent), `-q2` 21 (84.2 percent), median 7,031 to 13,000 tokens.** Under-prediction is a TAIL phenomenon, not a shift of the bulk; one 17,651-token touch is 30 percent of rung 3's halved token sum, so the ratios are fragile (not bootstrapped).
**Link to dashcam on-time: NOT supported as the driver by these counts.** Re-prefills 0 / 0 / 0 at 1x (on-time 8,378 / 8,719 / 7,303) while `-q2` still loses 1,416 against `-q`; at halved memory 4 / 1 / 21 (6,112 / 6,759 / 4,235), where the ordering matches only for `-q2`. About 7,500 frames missed in the worst cell against 192,649 re-prefill tokens. Within cell, 60 s windows with a re-prefill had more dashcam misses (0.810 against 0.421, 0.738 against 0.408, 0.707 against 0.584) but with 1 to 9 exposed windows and shared eviction pressure as a common cause.
**State:** re-prefill touches occur only under halved memory and nearly all hit sessions the planner believed GPU-resident (4 of 4, 1 of 1, 17 of 21 for `-q2`): the planner's residency belief is stale under pressure. No eviction event is logged on touches.
**Confounding:** one seed; touch volume and policy differ by arm; re-prefill coincides with eviction pressure that hurts dashcam directly.
**Per the ruling, step 2 (the online-ratio price) is NOT built. Decision for the user:** whether a tail-only mispricing (26 touches, none at 1x) justifies it; the audit points at stale residency belief rather than the 15-token price.
