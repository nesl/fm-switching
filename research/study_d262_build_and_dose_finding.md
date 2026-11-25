# D266 ITEM 2: THE BUILD IS DONE, AND A STEP 0 CHECK SAYS THE SWEEP'S DOSE IS ALMOST ZERO AT ONE SEED. A DECISION IS NEEDED BEFORE 2.88 ACCELERATOR HOURS.

**Built on flash CPU. Nothing committed to `experiments/`, nothing pushed, no GPU, no cell. The crash cost
ZERO: every patch and proof artefact survived and nothing was silently redone.**

## *** THE FINDING THAT WAS NOT KNOWN WHEN THE ESTIMATE WAS APPROVED, AND IT COST NO ACCELERATOR TIME ***

**The abandon check's prediction half needs no cells, so it ran at the ruled design point first. Nesting and
window invariance hold at both seeds and all three rungs. BUT THE DOSE THE METRIC IS REQUIRED TO SEE IS
ALMOST NOTHING.**
| pair, `3:11:2` n16 1200 s D=120 centre | nested | window | added victims | **forced-miss floor** |
|---|---|---|---|---|
| s4, k 1 to 3 | yes | 540.0 | robo003, robo009 | **2** |
| s4, k 3 to 5 | yes | 540.0 | robo004, robo010 | **1** |
| **s5, k 1 to 3** | yes | 540.0 | robo007, robo009 | *** 0 *** |
| **s5, k 3 to 5** | yes | 540.0 | robo006, robo008 | *** 0 *** |
*** AT SEED 5 THE ADDED VICTIMS OWN ZERO QUESTIONS INSIDE THE WINDOW AT BOTH RUNGS. SO NOTHING
ARITHMETICALLY REQUIRES ANY METRIC TO MOVE WITH k THERE, AND A NULL AT SEED 5 IS **UNEXERCISED** ON THE
FORCED-MISS CHANNEL RATHER THAN A NEGATIVE. ***
**The only live channel at seed 5 is the reconnect backlog, about +10,700 D2 tokens per rung. So the check
classifies on TWO channels, and a k-effect at seed 4 but not seed 5 is consistent with forced misses alone
and is NOT evidence about the policy.**
*** THE DECISION THIS FORCES, AND IT IS THE USER'S: the abandon check is now MORE LIKELY THAN NOT to return
ABANDON-ON-THE-BACKLOG-CHANNEL rather than a policy channel, and that is knowable for ZERO accelerator
hours. The levers that would give the k contrast a forced-miss dose at both seeds are the outage DURATION or
the WINDOW POSITION, and BOTH ARE FIXED BY THE RULING, so neither was touched. ***

## AND A SECOND FINDING THAT IMPROVES ON THE ESTIMATE'S PESSIMISM

**The estimate's primary worry was that the robot metric cannot see k, because `robot_pool_on_time` reads
121/132 at BOTH k=3 and k=5 in the committed cells. ANOTHER RECORDED METRIC DOES SEPARATE THEM:
`correct_answers_delivered_by_deadline` reads 0.621212 at k=3 against 0.666667 at k=5, which is 82 against
88 questions, a separation of 6 where the primary metric is flat.**
*** BUT THE DIRECTION IS BACKWARDS: MORE VICTIMS GIVES A HIGHER SCORE. In the committed cells the victim
sets are DISJOINT and the windows 157 s apart, which is exactly the confound the nesting removes, SO THE
DIRECTION IS UNINTERPRETABLE THERE AND ONLY BECOMES READABLE UNDER NESTING. The separation is grounds for
scoring every recorded robot metric per D251, not grounds for expecting a particular sign. ***

## THE BUILD, AND ITS PROOFS

**The reorder is as ruled: in centre mode the window is settled FIRST and carries no k (`t_start = 0.5 x
(run_s - D)` = 540.0 s, inside the committed band), then victims are the first k of ONE EXPLICIT
k-INDEPENDENT PERMUTATION, with the whole permutation recorded in the meta. NOTHING RESTS ON
`random.sample` INTERNALS.**
| proof | result |
|---|---|
| trace identity, outage OFF, both mixes | **byte-identical** |
| trace identity, outage ON under the COMMITTED band rule | **byte-identical AND reproduces the committed record exactly** (k=3 robo003/005/006 at 786.901505 s; k=5 robo001-005 at 509.505651 s) |
| per-arm decision-log identity at 40:40:20, 6 arms | **0 mismatches each**, instrument determinism control passed FIRST |
| per-arm identity at `3:11:2`, the mix the cells will run | **0 mismatches each** |
| **the nesting check FAILS on the band rule, as it must** | windows 441.3 / 565.2 / 777.2, span 335.9 s, sets not contained. **SO THE CHECK IS NOT VACUOUS** |
| Step 2b, band against centre | **1,044 differing decisions, first at row 401** |
| the switch arrives typed | `str "centre"`, `t_start` 540.0, and a bad placement string RAISES rather than defaulting |

**Three of the five named risks are FIXED IN CODE: the trace-dir token now carries the placement rule, so a
stale trace cannot be served while every gate passes; the driver's glob and newest-match are GONE, replaced
by asserting against the cell's own header including `robots == sorted(victim_permutation[:k])`; and a
timeout is now a VOID with a reason instead of silence.** **Risk 4, the `_preD249` comparator, is a
SEQUENCING QUESTION and was not solved. Risk 5, the E-id, is mine.**

**An honest vacuity caveat the build raised itself rather than leaving to be found: `covex-v6-fair-final`
and `-stateoff` return the IDENTICAL digest because the dry path emits ZERO `state_action` rows for either.
`-stateoff`'s characteristic decision never fires on that instrument, so its row proves the shared path and
not its own mechanism.**

## THE MISSING OBSERVABLE IS BUILT AND IS LIVE

**It discriminates arms in the predicted direction on all five committed outage cells (victims cached at the
first post-reconnect question): rung 3 reads 3/3 and 5/5 where `-stateoff` reads 2/3 and `llf` has NO
READABLE VICTIM AT ALL.** **And the device-only count of 4 at k=3 s4 REPRODUCES THE COMMITTED AMENDMENT
FIGURE EXACTLY, which is the cross-check that the window and victims it reconstructs are the ones the cells
ran.**
**Two limits registered: the denominator is k and CAN BE ZERO, which makes it an ABSENT LINK for `llf`
rather than a null; and proxy validity is open, because WARM can come from the history surviving OR from the
reconnect burst having just prefilled. The pre-outage control distinguishes them, 3/3 before for rung 3
against 0/3 for `-stateoff`, so the before-number is reported beside every after-number.**

## *** THE ETA COLLAPSED BY ABOUT 7x, AND THE REASON IS WORTH RECORDING ***

**Estimate: 14.5 to 23.0 flash CPU hours. Actual: 0.9 h spent plus 1.0 to 2.5 h remaining.**
*** THE ESTIMATE PRICED BUILDING TWO INSTRUMENTS THAT ALREADY EXISTED: `d223_dry_digest_identity.py` for the
per-arm decision identity, and the one-sha-two-trees idiom for the trace identity. They were reused with one
added flag. AN ESTIMATE THAT DOES NOT SEARCH FOR EXISTING INSTRUMENTS OVERPRICES BY THE COST OF THE
INSTRUMENTS. ***
**Accelerator unchanged: scope A is 8 cells at 2.88 h; scope B plus the k=1 rung is 30 cells at 10.79 h.**
**And the build recommends NOT charging the estimate's separate 0.72 h two-cell keying gate, because old
against new keying is now answered on CPU by the band-rule positive control, the Step 2b decision diff and
the trace identity. The gate's two cells become the first two of scope A and the abandon check consumes
them.**
