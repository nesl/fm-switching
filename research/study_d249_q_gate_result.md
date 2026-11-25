# THE D249 `-q` GATE CELL FAILS ON CORRECT-BY-DEADLINE. THE MECHANISM FIRED, IT IS WHY THE DECISIONS CHANGED, AND IT MADE THE ARM WORSE. THAT IS A SETTLED NEGATIVE.

**Cell `covex-v6-fair-final-q n16 s4 _L3_epg_rq30`, POST-PUSH on `live2 5edd1245654e5653`, ended 14:56:52,
VALID: `source_agreement` OK, 10,550 requests, 0 errors, 0 ENOSPC.**
**Scored against the rule AMENDED AT `412c3a75` AND TIMESTAMPED 2026-11-25T22:51:05Z, which is BEFORE any
figure from this cell reached the session that scored it.**

## REACHABILITY FIRST, AS RULED. THIS IS NOT AN ABSENT LINK.
```
state_chosen_TOUCH          906        NON-ZERO, so the arm made its characteristic decision
d249_queued_ahead_reads  67,236        and the field is ABSENT ON BOTH RUNG-3 COMPARATORS
d249_pwc_queue_priced    64,976
d249_pwc_queue_capped     1,218        the D256 cap bound, so the cap is live and not decorative
d249_pwc_queue_max_milli  2,781        exactly the cap
```
*** SO THE SWITCH OPERATED AND IS WHY THE DECISIONS CHANGED. THE READ IS NAMED, NON-ZERO, AND ABSENT IN THE
COMPARATOR. ***
**Touch delta: 906 against rung 3's 2,674, which is FEWER and was the predicted direction. IT IS NOT A PASS
CRITERION and is not read as one.**

## THE RESULT

| | cbd | cloud-correct | device-correct (standing) | cloud on-time | accuracy on served | dashcam |
|---|---|---|---|---|---|---|
| **`-q`** | **79** | 75 | 4 (14) | 118/132 | 0.636 | **8,719** |
| comparator, prereg-named un-suffixed | 83 | 82 | 1 (6) | 126/132 | 0.651 | 8,377 |
| `_rep2`, SA OK, beside it | 85 | 84 | 1 (5) | 127/132 | 0.661 | 8,323 |

**CONDITION 1: cbd 79 against the required 86. FAIL, at -4 against the comparator and -6 against `_rep2`.**
**CONDITION 2: dashcam 8,719 against 8,377 is +342, not worse, bar 54. HOLDS.**
*** VERDICT: FAIL, ON CORRECT-BY-DEADLINE. The SAME verdict against `_rep2`, so there is NO comparator
disagreement to report, which is the outcome the two-comparator rule was there to detect. ***
**And cloud-only the arm is ALSO behind: cloud-correct -7, cloud on-time -8, accuracy on served -0.015. So
the fail does not depend on the device-credit term.**
**Check 7 on the comparator: valid, 1 error, `source_agreement` ABSENT, which is the provenance weakness the
pre-registration named in advance rather than discovered afterwards.**

## *** WHAT THE ARM TRADED, WHICH IS THE EXPLICABLE PART ***
```
touches     906 against 2,674   -1,768
on-time     118 against 126        -8
dashcam   8,719 against 8,377     +342
```
**The queue-aware price made the arm TOUCH LESS, which cost it robot warmth and therefore robot correctness,
while freeing capacity that went to DASHCAM.** *** THAT IS A COHERENT TRADE IN THE WRONG DIRECTION FOR THE
RULED METRIC. The arm did not malfunction; it priced touches dearer, bought fewer, and the robot side is what
paid. ***

## *** RULE 2: THIS IS "FIRED AND DID NOT HELP", AND IT IS A **SETTLED** NEGATIVE ***

**CLAUDE.md lists five ways a null can arise and only one is evidence about the policy. This is that one,
and the two conditions it requires are both met:**
- **STEP 2 PASSED: the implementing quantity is NAMED (`d249_queued_ahead_reads`), NON-ZERO at 67,236, and
  ABSENT in both comparators, so it varies exactly where the claim says it should. The mechanism was not
  cancelled by geometry, not unexpressible, not unscorable and not unexercised.**
- **STEP 4 IS SATISFIED BY THE COMPARATOR ITSELF: disabling the mechanism IS rung 3, where the field is
  absent, and the result CHANGES, 83 against 79. The control moved the outcome.**
*** SO THIS IS NOT AN ARTEFACT OF AN ABSENT MECHANISM, WHICH IS WHAT E36, E36b AND E36c WERE. THE QUEUE-AWARE
PRICING PATH WAS BUILT, PROVED PRESENT, PROVED CONSUMED, AND MADE THE ARM WORSE ON THE METRIC IT WAS RULED
AGAINST. THAT IS A FINDING ABOUT THE POLICY AND IT IS SETTLED AT THIS SEED AND THIS CONDITION. ***

## CONSEQUENCES, AS RULED
**The `-q` s5 to s7 lines STAY `#PENDING-GATE` AND DO NOT RUN. The driver proceeds to D250 s5 to s7 with
rung 3 at s5 first.**
*** A FAIL IS A FAIL: THE MARGIN IS NOT RE-DERIVED, THE QUANTILE IS NOT MOVED, THE BINS ARE NOT CHANGED. The
D259 Method A margin of 0.331566 stands as the value the pre-commitment produced, and the arm it was scoped
to has now failed its gate under it. ***
**Scope: ONE SEED, ONE CONDITION. Nothing here is a claim about the queue-aware term at other seeds, at other
fleet sizes, or under memory pressure, and the s5 to s7 cells that would have tested that are the ones the
fail withholds.**
