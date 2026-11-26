# D275 PRE-REGISTRATION: THE TWO `-q` PRESSURE GATES, FIXED BEFORE EITHER CELL RUNS

**Committed 2026-11-25T23:29:03Z. NEITHER CELL HAS RUN AND NO FIGURE FROM EITHER EXISTS.**
**The 1x gate failure stands (`3ce9ba27`) and `-q` s5 to s7 at 1x DO NOT RUN.**

## THE TWO GATES, each a NEW SINGLE-SEED gate

**(a) `covex-v6-fair-final-q 16 4 _kv0.5r_h0.5_L3_epg_rq30`**
comparator: rung 3's committed D250 cell, robot cbd **72**, dashcam **6,112** (worst device 0.454).
*** PASS NEEDS cbd >= 75, AND dashcam not worse than 6,112 beyond its same-code observation. ***

**(b) `covex-v6-fair-final-q 16 4 _c3-11-2_L3_epg_rq30`**
comparator: rung 3's committed P3 cell, robot 176 of 229 on-time, dashcam 4,770 of 5,869.
*** PASS NEEDS cbd TO BEAT THE COMPARATOR'S cbd BY MORE THAN 2, AND dashcam not worse beyond observation. ***
**The comparator's cbd COUNT is read from the committed cell by the scorer. IT IS NOT STATED HERE BECAUSE I
COULD NOT VERIFY IT FROM THE CELL'S OWN SWEEP BLOCK, WHICH CARRIES NO cbd FIELD. A number I cannot read is a
number I do not write into a pre-registration.**

## REACHABILITY, FIRST AND BEFORE ANY SCORING, AS BEFORE
**`state_chosen_TOUCH` > 0, else the cell is an ABSENT LINK and the pass rule is not scored at all.**
**`d249_queued_ahead_reads` non-zero in the `-q` cell and ABSENT on the comparator.**
**The TOUCH delta is reported; ITS DIRECTION IS NOT A CRITERION. At 1x the `-q` arm touched 906 against
rung 3's 2,674, and fewer is the expected direction.**

## *** CORRECTION, 2026-11-25T23:30:04Z: BOTH COMPARATORS READ `source_agreement` **OK**, NOT ABSENT. MY CLAIM WAS WRONG AND IT IS WITHDRAWN. ***

**I read `header.source_agreement` inside `cell.json`. THAT FILE HAS NO `header` KEY AT ALL: the header is a
SEPARATE `header.json`, where both comparators read verdict OK.** *** SO THE PROVENANCE WEAKNESS I RECORDED
ABOVE DOES NOT EXIST. A FALSE WEAKNESS IN A PRE-REGISTRATION IS WORSE THAN NONE, BECAUSE IT DISCOUNTS A
SOUND COMPARATOR. *** **Same class as reading `run_meta.n_errors` earlier today when `n_errors` is
top-level: a wrong key path reported as an absence. Check 7 still runs on each comparator; it will now
record OK rather than an absence.**

## UNCHANGED
**Check 7 on each comparator before its comparison is read; robot cloud on-time never quoted alone, with
cloud-correct, device-correct and cloud accuracy on served beside it; an unfloored dashcam delta reported as
UNFLOORED; A FAIL IS A FAIL, with the margin, quantile and bins untouched.**
**Scope: one seed per condition. The 1x failure is not evidence about either pressure condition, and neither
is evidence about the other.**

## RESULT, GATE (a) `_kv0.5r_h0.5` s4, scored 2026-11-26T00:03Z against the rule above, as reported by the H100 and re-checked here
**PASS.** Post-push, valid (SA OK, 0 errors). Reachability met: TOUCH 787 (rung 3 1,434), `d249_queued_ahead_reads` 60,738 (absent on rung 3), priced 57,719, capped 2,151.
| | cbd | cloud-correct | device (standing) | on-time | acc served | SS | dashcam (worst) |
|---|---|---|---|---|---|---|---|
| `-q` | **77** | 64 | 13 (41) | 91/132 | 0.703 | 320 | 6,759 (0.541) |
| rung 3, D250 s4 (SA OK) | 72 | 49 | 23 (60) | 72 | 0.681 | 311 | 6,112 (0.454) |
(1) cbd 77 >= 75: PASS (+5). (2) dashcam +647, bar 154: PASS. **Cloud-only +15 correct, +19 on-time: the pass is cloud-earned** (device share 13 of 77 against 23 of 72).
**Scope: ONE SEED, ONE CONDITION.** It is the opposite sign from the 1x gate (`3ce9ba27`, FAIL at -4). Nothing here changes that failure and nothing extends this pass to other seeds or conditions.

## RESULT, GATE (b) `_c3-11-2` s4, scored 2026-11-26T00:25Z, as reported by the H100 and re-checked here
**PASS on condition 1; condition 2 UNFLOORED.** Post-push, valid (SA OK, 0 errors). Reachability met: TOUCH 3,420 (P3 1,398), `d249_queued_ahead_reads` 96,701 (absent on P3), priced 72,784, capped 3,450.
| | cbd | cloud-correct | device (standing) | on-time | acc | SS | dashcam (worst) |
|---|---|---|---|---|---|---|---|
| `-q` | **136**/229 | 116 | 20 (44) | 185 | 0.627 | 216 | 4,737 (0.793) |
| P3 (SA OK) | 127 | 107 | 20 (53) | 176 | 0.608 | 222 | 4,770 (0.796) |
(1) cbd +9 > 2: PASS, cloud-earned (+9 cloud-correct, device 20 against 20). (2) dashcam -33, but P3 has NO same-code replicate, so the bar is UNFLOORED: not called a difference, and not demonstrated to hold either. SS -6.
**Direction note: in this mix `-q` touches 2.4x MORE than P3, the opposite direction to the 1x cell (906 against 2,674) and gate (a) (787 against 1,434). The touch delta is not a criterion and is recorded only.**
**Across the three `-q` gates, one seed each: 1x FAIL (-4), halved memory PASS (+5), robot-heavy PASS (+9). Nothing here extends any one result to another seed.**
