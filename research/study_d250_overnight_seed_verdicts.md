# D250 s5 TO s7 PER-SEED VERDICTS (overnight 2026-11-25 to 26), recorded as REPORTED by the H100 (its scoring against the D250 pass rule; NOT re-scored by the main session; one seed per block). Same code on every arm (live2 152b47d4 at s5). cbd = robot correct-by-deadline (D155 (3)); robot cloud on-time is never quoted alone (D257 (3)).

## SEED 5, recorded 2026-11-26T11:55Z (7 cells, all valid, SA OK, 0 ENOSPC; 5 dashcam kind-2 ReadErrors: cascade 1, mooncake 2, eco-llm 2; robot pool n = 127)
| arm | cbd | cloud-correct | device-correct (standing) | cloud on-time | acc | SS | dashcam (worst) |
|---|---|---|---|---|---|---|---|
| rung 3 | **52** | 30 | 22 (62) | 65 | 0.462 | 292 | 5,535 (0.397) |
| base | 42 | 11 | 31 (97) | 30 | 0.367 | 344 | 5,631 (0.458) |
| cascade | 36 | 0 | 36 (121) | 6 | n/a | 158 | 2,228 (0.104) |
| simplestream | 39 | 38 | 1 (1) | 126 | 0.302 | 355 | 10,601 (0.889) |
| llf | 38 | 0 | 38 (124) | 3 | n/a | 135 | 7,120 (0.578) |
| mooncake | 42 | 4 | 38 (117) | 10 | 0.400 | 203 | 5,332 (0.439) |
| eco-llm | 39 | 16 | 23 (73) | 54 | 0.296 | 189 | 4,948 (0.414) |
**H100 verdict: PASS.** (1) Best baseline on cbd is a TIE (base and mooncake, 42); rung 3 52 = +10, above the 2 threshold (about 32 cloud questions at the 0.31 slope; direct cloud on-time gap +35 against base, +55 against mooncake). (2) Dashcam against the tied winners: base 5,631: -96 (inside the 154 bar); mooncake 5,332: +203: not worse beyond observation. Cloud-only: rung 3 30 against simplestream 38 (-8; simplestream is the best cloud-correct arm), against base 11 (+19), mooncake 4 (+26). **Beside:** baselines above rung 3 on dashcam beyond 154: simplestream +5,066, llf +1,585, neither a cbd winner; as at s4 simplestream wins cloud on-time (126 against 65) and dashcam and loses only on correctness (cbd 39 against 52).

## SEED 6, recorded 2026-11-26T14:26Z (7 cells, post-push live2 152b47d4, all valid, SA OK, 0 ENOSPC; 5 dashcam kind-2 ReadErrors: mooncake 2, eco-llm 3; robot pool n = 121)
| arm | cbd | cloud-correct | device-correct (standing) | cloud on-time | acc | SS | dashcam (worst) |
|---|---|---|---|---|---|---|---|
| rung 3 | **41** | 36 | 5 (54) | 67 | 0.537 | 312 | 6,026 (0.481) |
| base | 24 | 17 | 7 (89) | 32 | 0.531 | 345 | 5,141 (0.427) |
| cascade | 10 | 3 | 7 (114) | 7 | 0.429 | 144 | 2,048 (0.162) |
| simplestream | 16 | 16 | 0 (0) | 121 | 0.132 | 357 | 11,396 (0.962) |
| llf | 10 | 3 | 7 (117) | 4 | 0.750 | 188 | 8,147 (0.674) |
| mooncake | 11 | 4 | 7 (113) | 8 | 0.500 | 178 | 5,105 (0.425) |
| eco-llm | 17 | 10 | 7 (92) | 29 | 0.345 | 164 | 4,688 (0.392) |
**H100 verdict: PASS.** (1) Best baseline on cbd is `covex-v6-base` 24; rung 3 41 = +17, above the 2 threshold (about 55 cloud questions at the 0.31 slope; direct cloud on-time gap +35). (2) Dashcam against `base`: +885, not worse (bar 154). Cloud-only: rung 3 is the best cloud-correct arm (36 against `base` 17, `simplestream` 16: +19 against both). Cloud on-time: `simplestream` 121 against 67 (rung 3 loses it). Dashcam beaten beyond 154 by `simplestream` (+5,370) and `llf` (+2,121); neither is the cbd winner.
**FLAG (H100, unexplained further): the device-correct fraction at s6 is low in EVERY arm (rung 3 5 of 54 = 0.093, `base` 7 of 89 = 0.079, `llf` 7 of 117 = 0.06) against about 0.37 at s4 and s5. device_correct is fixed per question, so this is the s6 question mix (composition), not an arm fault; not further explained.** Seed 7 started 06:14 PST (rung 3 first); batch expected about 08:36.

## S6 DEVICE-CORRECT ANOMALY EXPLAINED, 2026-11-26T14:58Z (CPU, committed cells at s4 to s7, one seed per pool): it is the QUESTION MIX
| rung 3 1x | robot asks n | device-correct asks | share | distinct questions | distinct device-correct questions |
|---|---|---|---|---|---|
| s4 | 132 | 49 | 0.371 | 20 | 6 |
| s5 | 127 | 38 | 0.299 | 25 | 8 |
| **s6** | 121 | **7** | **0.058** | 20 | **1** |
| s7 | 105 | 31 | 0.295 | 22 | 6 |
(1) All arms see the same questions: simplestream, llf, mooncake, cascade and eco-llm carry identical opportunity ids and device_correct flags to rung 3 at every seed, so this is NOT an arm effect (there is no plain base cell at rq30 for s4 to s6). (2) device_correct belongs to the question id (57 distinct ids over four seeds, 0 inconsistent flags). (3) The question set is RESAMPLED per seed: each seed draws 20 to 25 distinct questions from the 97-question LH-REQ pool, overlap between seeds 3 to 11. (4) n is the number of ASKS: each question belongs to one device and is re-asked up to 17 times; asks before a robot's join point are not counted (D101); per-device ask counts vary widely (s7: robo001 3 asks, robo002 32). **The cause of the s5 to s7 pool sizes differing (127, 121, 105) was NOT verified (only the s4 trace is on origin).** (5) **s6 has ONE device-correct question, asked 7 times, all on robo005; every other s6 device has 0 device-correct asks.** At s4 three device-correct questions are asked 15, 12 and 8 times, so a handful of heavily repeated questions sets the fraction. A draw of 1 or fewer of 20 has probability about 4 percent at a rate of about 0.23 (13 of 57 distinct questions overall). (6) s6 has no identifiable sequential_action question (s4: two give 23 of the 49 device-correct asks, all device-correct; s7: one gives 11 of 31; s5's single one was device-wrong). s6 categories (identified asks): location_trace 30, temporal_ordering 21, visual_detail 21, time_duration 7, object_comparison 6, all with 0 device-correct; s4: visual_detail 59 (12 correct), location_trace 38 (14), sequential_action 23 (23). (7) Cloud accuracy on served is NOT higher at s6 (rung 3: 0.651 s4 on 126 served, 0.421 s5 on 121, 0.550 s6 on 111, 0.595 s7 on 84): the device is worse at this mix, not the cloud better. (8) History length does not explain it (5.5k to 53k tokens, median 14k to 18k at every seed). **Caveats:** category coverage is partial (61 of 97 pool questions; 35 to 55 asks per seed uncategorised at s5 to s7); a pool of about 20 distinct, heavily repeated questions makes 0.37, 0.30 and 0.30 as much draws as 0.06; the seed also changes the arrival, join and outage pattern. Not done: device-correct by question time; the 35 uncategorised s6 asks. **Consequence for the D250 reading: the s6 cbd gap is mostly cloud-correct (36 against base 17), so the pass does not rest on the device credit; the s6 cbd levels are lower for every arm because the device fallback pays little.** s7 rung 3 (n = 105): the other s7 cells are running.

## CORRECTION OF CONDITION AND CLUSTERED READING, 2026-11-26T15:50Z (research/study_question_sampling_clustered_bootstrap.md)
**The D250 seed batches (s5, s6, s7) are the HALVED-MEMORY condition (`_kv0.5r_h0.5`, rung 3 cells carry the name-only `_preD249` label), as at s4 (rung 3 cbd 72): the rung 3 cbd of 52 (s5), 41 (s6) and 40 (s7) in this file are halved-memory figures; the corresponding 1x rung 3 cells are 56, 61 and 50.** The s6 device-correct section above used the 1x cells (device-correct 7 at s6), the same question set at the same seed. **The pool is the 69 EVAL LH-REQ questions in 51 sessions, not 97 (the "97" in the s6 section is the full LH-REQ count including 28 DEV).** Clustered by question id, rung 3 minus `base` at `_kv0.5r_h0.5` is: s4 +11 (2, 22), s5 +10 (-3, 23), s6 +17 (3, 33), **s7 -1 (-8, 7)**: so the s5 PASS is not distinguishable from zero at the question level and s7 is flat against `base` (the s7 batch is still running; its verdict is the H100's to report and the count rule is unchanged). The H100's count-form rule counts asks; the clustered interval is reported beside it, not instead of it.

## SEED 7, recorded 2026-11-26T16:44Z (HALVED-MEMORY condition, `_kv0.5r_h0.5`; 7 cells, post-push live2 152b47d4, all valid, SA OK, 0 ENOSPC; 2 dashcam kind-2 ReadErrors on eco-llm; robot pool n = 105), as reported by the H100
| arm | cbd | cloud-correct | device-correct (standing) | cloud on-time | acc | SS | dashcam (worst) |
|---|---|---|---|---|---|---|---|
| rung 3 | **40** | 30 | 10 (55) | 50 | 0.600 | 305 | 5,530 (0.407) |
| base | **41** | 15 | 26 (84) | 21 | 0.714 | 355 | 6,541 (0.534) |
| cascade | 38 | 8 | 30 (95) | 10 | 0.800 | 152 | 1,896 (0.113) |
| simplestream | 24 | 24 | 0 (0) | 105 | 0.229 | 359 | 11,192 (0.947) |
| llf | 31 | 0 | 31 (105) | 0 | n/a | 187 | 9,358 (0.781) |
| mooncake | 32 | 3 | 29 (100) | 5 | 0.600 | 281 | 7,944 (0.658) |
| eco-llm | 28 | 20 | 8 (33) | 72 | 0.278 | 277 | 7,700 (0.629) |
**H100 verdict: FAIL on the ruled metric.** (1) The best baseline on cbd is `covex-v6-base` 41; rung 3 40 = -1 (the rule needs more than +2): FAIL. (2) Dashcam against `base`: 5,530 against 6,541 = -1,011, beyond the 154 bar: FAIL. Cloud-only: rung 3 is the best cloud-correct arm (30; simplestream 24, eco-llm 20, base 15): +15 against the cbd winner; cloud on-time: simplestream 105 against 50. Dashcam beaten beyond 154 by base (+1,011), mooncake (+2,414), llf (+3,828), eco-llm (+2,170), simplestream (+5,662).
**D250 BLOCK COMPLETE: per-seed rung 3 minus best baseline cbd: s4 +11, s5 +10, s6 +17 (PASS), s7 -1 (FAIL).** The clustered question-level CI computed beforehand (rung 3 minus `base` at `_kv0.5r_h0.5`: s4 +11 (2, 22), s5 +10 (-3, 23), s6 +17 (3, 33), s7 -1 (-8, 7)) matches the point values: **3 of 4 seeds pass the count rule, and only s4 and s6 have clustered intervals above 0**; s7's pool (105 asks, 22 questions, the smallest) has the fewest cloud-useful questions. Rung 3 is again the best cloud-correct arm at s7 and loses on cbd because `base`'s device fallback pays more (device-correct 26 against 10, standing 84 against 55), the same direction as the s6 question-mix flag. Cumulative: the D250 rule is a count rule per seed; the seed-level outcome is mixed, not a clean sweep. The six `-q5c` seed cells start now.
