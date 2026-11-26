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
