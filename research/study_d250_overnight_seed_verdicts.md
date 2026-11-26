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
