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
