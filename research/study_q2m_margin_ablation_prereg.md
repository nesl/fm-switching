# `-q2m`: AN ABLATION OF THE D259 PRE-COMMITTED MARGIN, PRE-REGISTERED BEFORE ANY CELL (2026-11-26T02:30:24Z). No cell has run; nothing is built yet.

**User ruling D282. LABELLED ABLATION: it does NOT replace or re-derive the D259 Method A margin (0.331566), which stands as the value its pre-commitment produced. The `-q` verdicts (1x FAIL, halved-memory PASS, robot-heavy PASS) and the `-q2` verdicts (both gates FAIL) STAND.**
**Arm:** `covex-v6-fair-final-q2m` = `-q2` with the margin set to rung 3's committed `MARGIN_CF_ON_TIME` **0.6582** (MARGIN_CF 0.16456) instead of 0.331566. Nothing else changes. Switch default OFF. Question asked: is the margin the cause of the over-touching that sank `-q2` (TOUCH 10,446 and 5,257 against rung 3's 2,674 and 1,434)?

## The two gates, single seed s4, D275 form, the SAME bars as the `-q2` gates
**(a) 1x, `covex-v6-fair-final-q2m 16 4 _L3_epg_rq30`** against rung 3's committed comparator (un-suffixed cell: cbd 83, dashcam 8,377). PASS needs cbd >= 86 AND dashcam not worse than 8,377 beyond 54.
**(b) `covex-v6-fair-final-q2m 16 4 _kv0.5r_h0.5_L3_epg_rq30`** against rung 3's D250 cell (cbd 72, dashcam 6,112). PASS needs cbd >= 75 AND dashcam not worse than 6,112 beyond 154.
**Report beside rung 3, `-q` and `-q2` for each: TOUCH, HOLD_BACK, cloud-correct, cbd, and the worst dashcam device.** Known figures: 1x rung 3 83 / 8,377 / TOUCH 2,674 / HB 2; `-q` 79 / 8,719 / 906 / 87; `-q2` 82 / 7,303 / 10,446 / 6. Halved memory: rung 3 72 / 6,112 / 1,434 / 4; `-q` 77 / 6,759 / 787 / 93; `-q2` 65 / 4,234 / 5,257 / 4.
**Reachability, first:** TOUCH chosen > 0 (else absent link); HOLD_BACK reported; the arm's decisions must show the margin actually read is 0.6582 (a census of the margin used per decision, as in the D259 probe), and the `q2_` counters must be non-zero.
**Order:** the two cells are inserted at the next cell boundary AHEAD of the remaining LINKSYNC gate cells; result of each reported as soon as it lands, 1x first. **NO seeds are queued from this result; the user decides tonight.**

## A prediction will be added by timestamped amendment from a dry replay (`-q2` at margin 0.3316 against 0.6582, TOUCH and HOLD_BACK) BEFORE any live cell.
**Dry limitation, stated now:** the dry harness does not enforce the logical KV pool (`kv_capacity_enforced` False there), so a dry replay can speak to the 1x condition; for the halved-memory condition it can say only what the planner does without memory pressure, and the build record will state which.

## Unchanged
A fail is a fail; an unfloored dashcam delta is reported as unfloored; robot on-time is never quoted alone; check 7 on each comparator with `source_agreement` read from `header.json`; the push goes through a cell-boundary window with the H100 verifying hashes; light checks only (300 s switch-off identity on the default mix, one dry run showing the margin read is 0.6582, unit tests).

## AMENDMENT 2026-11-26T03:02:42Z, BEFORE ANY CELL: build record, dry prediction, reachability (build agent's report; the 4-path window values were independently re-staged on origin)
**Build:** switch `live2_q2m_rung3_margin` default OFF (instance-level, class attribute raises, raises without D249 and q2); READ site `d261_margin_scope.py:113` -> `arms_v6state.py:221` -> `v5/cf_planner.py:440`. D259 constants untouched: `-q` and `-q2` still return 0.0828915. Light checks: 300 s dry default mix, 235 of 235 constructible arms digest-identical to main, `-q2` unchanged (3,314 rows, ce07874fb5c39585); 20 unit checks pass. **Margin census over 1,200 s: `-q2m` 0.65824 on 60,920 decisions; `-q2` 0.331566 on 60,934; rung 3 0.65824; `-q` 0.331566. q2_ counters non-zero and identical in `-q2` and `-q2m` (q2_hbwarm_evals 114, q2_inflight_excluded_evals 112).**
**DRY PREDICTION (s4, 1x posted knobs; positive control passed: `-q2` reproduced TOUCH 7,353, HOLD_BACK 1, 18,927 rows, be0d89c156910feb):**
| arm | margin | TOUCH | HOLD_BACK | WARM | pieces | rows |
|---|---|---|---|---|---|---|
| rung 3 | 0.6582 | 2,954 | 0 | 6 | 163 | 14,539 |
| `-q` | 0.3316 | 1,175 | 74 | 0 | 88 | 12,555 |
| `-q2` | 0.3316 | 7,353 | 1 | 14 | 162 | 18,927 |
| `-q2m` | 0.6582 | 1,667 | 0 | 3 | 163 | 13,252 |
**Prediction: at 1x `-q2m` touches about 4.4x less than `-q2`, below rung 3 and near `-q`; HOLD_BACK about 0. This is a mechanism prediction (TOUCH and HOLD_BACK counts); NO cbd or dashcam prediction is claimed. Reachability: TOUCH 1,667 > 0.**
**Halved memory: NO prediction.** The dry harness can enforce the logical pool and it was run (31,472 tokens), but the pool essentially never binds in the dry (over cap in 5 of 12,001 epochs) and all four digests equal their 1x digests; the live effect (pinned 1,968 blocks, real eviction) is not modelled.
**Gate line caveat:** a `_kv0.5r` cell is refused by driver v43 (ENGINE ARGS MISMATCH) unless its line in the gated list carries `--num-gpu-blocks-override 1968 --max-model-len 31472` and the list sha is in `V6_GATE_OK`; the poster must include them. Lines: `covex-v6-fair-final-q2m 16 4 _L3_epg_rq30` and `covex-v6-fair-final-q2m 16 4 _kv0.5r_h0.5_L3_epg_rq30`. Window: 4 paths (3 M, 1 A), live2 ed93608b -> f0c4625f, orchestration 0a167349 -> 3dbdafa5, baselines 41c430d7 unchanged.

## RESULT, GATE (a) 1x s4, scored 2026-11-26T03:53Z against the bars above, as reported by the H100 (SA OK, valid, 0 errors), post-push on live2 f0c4625f
**FAIL on condition 1, by 1; condition 2 holds.** (1) cbd 85 against the required 86: FAIL (-1). (2) dashcam 8,365 against 8,377, -12 against a bar of 54: holds.
Reachability: TOUCH 1,336 (rung 3 2,674; `-q` 906; `-q2` 10,446), HOLD_BACK 3 (2; 87; 6), q2_inflight_excluded_evals 98, q2_hbwarm_evals 100, d249 reads 67,704. **Margin census in the LIVE cell: NOT readable from the outputs the H100 sees (only gain_*_over_margin counts), so UNVERIFIED live; the dry census (0.65824 on 60,920 decisions) stands as the build-side proof.**
| 1x s4 | cbd | cloud + device | on-time | acc | SS | dashcam | TOUCH | HOLD_BACK |
|---|---|---|---|---|---|---|---|---|
| `-q2m` | 85 | 84 + 1 (standing 5) | 127/132 | 0.661 | 353 | 8,365 (worst 0.673) | 1,336 | 3 |
| rung 3 | 83 | 82 + 1 | 126 | 0.651 | 351 | 8,377 | 2,674 | 2 |
| rung 3 `_rep2` | 85 | | 127 | 0.661 | 351 | 8,323 | | |
| `-q` | 79 | | 118 | | | 8,719 | 906 | 87 |
| `-q2` | 82 | 78 | 121 | 0.645 | 343 | 7,303 | 10,446 | 6 |
**Observations:** the margin alone took TOUCH from 10,446 to 1,336 (7.8x down, below rung 3's 2,674; the dry predicted 1,667), restored dashcam to within 12 of rung 3 (8,365 against 7,303), and put cbd at 85, tying rung 3's own replicate (`_rep2` 85) and 1 under the pre-registered bar of 86. A fail is a fail: the bar was fixed before the cell. Gate (b) is running (ends about 20:09); the D285 branch applies after it.

## AMENDMENT D286, 2026-11-26T03:58:19Z, BEFORE THE `_kv0.5r_h0.5` CELL ENDS (about 20:09) AND BEFORE ITS RESULT IS KNOWN (user ruling)
1. **The 1x verdict STANDS as a FAIL under its pre-registered bar (cbd 85 against 86).** It is recorded as a TIE with rung 3 at 1x (rung 3 83, its `_rep2` 85); nothing is re-scored.
2. **Branch for `-q2m` ONLY (replaces the D285 branch for this arm):** IF the `_kv0.5r_h0.5` cell PASSES its pre-registered bar (cbd >= 75 AND dashcam not worse than 6,112 beyond 154), queue `-q2m` s5, s6, s7 at 1x and at `_kv0.5r_h0.5` (6 cells) AFTER the D250 s5-s7 block, with PER-SEED readouts beside rung 3 at the same seeds. **The 1x seeds are labelled a "no worse than rung 3" CHECK, not a gate.** IF it FAILS, queue NOTHING and rung 3 stays the candidate. In every case the `-q` pressure seeds stay held.
3. **The live margin must be CONFIRMED from the `-q2m` decision log (MARGIN read 0.6582) and stated in the morning summary** (the 1x live cell's margin was not readable from the outputs the H100 sees; the dry census is the only proof so far).
