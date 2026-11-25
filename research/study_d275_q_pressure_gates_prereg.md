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
