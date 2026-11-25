# Block A verdict (D238): nine cells, three arms, three seeds, same-code comparators

**D238 withheld any block-A verdict until all nine cells were in. All nine are in, all valid,
`source_agreement` OK on all nine, no ENOSPC, no INVALID, no reruns.** Every number below is computed from
the pooled integers with **each seed's own denominator**, read from that cell.

## What block A bought

**Before tonight every ablation verdict was measured against a comparator that differed by dozens of
run-path files.** Block A runs the comparator beside both ablations at three seeds on identical code.
**`-stateoff` and `-notouch` are same-code with their comparators by SUBTREE at all three seeds**
(`experiments/orchestration` `c6a83f0eaf3d`, `experiments/lib` `46a6bf61441a`, blobs `6508e4e5f063` /
`5b980c612854` / `b3e49def431b`), verified on this box through the tree, since no `-notouch` commit
resolves here and **the tree is the durable key.**

## The nine cells, alert attainment on the fixed-19 scale

| seed | denominator | comparator | `-stateoff` | ratio to the 0.027752 bar | `-notouch` | ratio |
|---|---|---|---|---|---|---|
| s5 | 19 x 714 = 13,566 | 0.486289 | 0.437049, **-0.049241** | **1.77x OUTSIDE** | 0.469040, **-0.017249** | 0.62x INSIDE |
| s6 | 19 x 712 = 13,528 | 0.509240 | 0.478637, **-0.030603** | **1.10x OUTSIDE** | 0.520033, **+0.010792** | 0.39x INSIDE |
| s7 | 19 x 714 = 13,566 | 0.501548 | 0.477296, **-0.024252** | **0.87x INSIDE** | 0.529043, **+0.027495** | 0.99x INSIDE |

## *** THE TWO HEADLINE READINGS ***

**1. `-stateoff` is negative at all three seeds and DECLINING MONOTONICALLY: 1.77x, 1.10x, 0.87x. It clears
the widest bar at two of three seeds and falls INSIDE it at s7.** So **the halved-pool state-channel effect
is seed-dependent in magnitude and not separable at every seed. It cannot be reported as "decisive at
kv0.5r".** The 1x reading of 6.16x stands at a different memory level and is untouched by this.

**2. `-notouch` IS INSIDE THE BAR AT ALL THREE SEEDS ON FIXED-19: 0.62x, 0.39x, 0.99x.** Its **SIGN**
pattern holds across four seeds, but **no magnitude clears the bar at any block-A seed.** **So on attainment
`-notouch` is not separable from noise anywhere in block A.**

### The registered prediction, and what it did and did not establish

**Registered before cell 9 started, with the commit timestamp and the state of the world as proof of
ordering rather than a backdated label: the sign of the s7 fixed-19 delta.** **Result: POSITIVE, +373 over
13,566, confirmed independently from the raw logs with all three integers agreeing exactly (7,177, 6,804,
11,779).** **The pattern holds on sign across four seeds spanning a 17-fold dose range with the only
negative at the lowest dose.**
**It was registered that MAGNITUDE is not part of the test, precisely so a positive inside the bars could
not be reinterpreted. That provision is now load-bearing: the s7 magnitude is 0.99x, INSIDE.**
*** AND THE TWO SCALES DISAGREE ABOUT s7's SEPARABILITY: fixed-19 gives +0.027495 against a 0.027752 bar,
INSIDE by 257 millionths; the true-denominator scale gives +0.033324 against 0.029705, OUTSIDE at 1.122x.
Any claim that s7 is outside the noise floor MUST name the scale. *** The exact episode count of 714
decides it, which is why a bracket was not good enough.

## The dose, with one column named

**DOSE = the comparator's `counts.completed_touch`**, which measures the mechanism **as actually enacted in
the unablated arm**, i.e. what the ablation removes:

| seed | DOSE | `-notouch`'s own `state_touch_chosen_not_enacted` | attainment delta |
|---|---|---|---|
| s5 | **171** | 140 | -0.017249 |
| s6 | **401** | 612 | +0.010792 |
| s7 | **2,152** | 2,075 | +0.027495 |
| *(s4, functionally same-code only)* | 2,899 | 2,966 | +0.039696 |

**`-notouch`'s own counter is the EXERCISED-NESS PROOF and not the dose.** **The two columns were mixed in
an earlier draft of mine; they agree on ORDER (s5 < s6 < s7 < s4) so "the only negative at the lowest dose"
survives either way, but a verdict must use one and name it.**
*** THE DOSE IS NOT AN INDEPENDENT VARIABLE. It is an observed property of each seed's trace, so "higher
dose" and "different seed" are the same variable, and the denominators and episode histograms differ along
with it. The comparator's own dose-attainment relation is NON-MONOTONIC (171 to 0.486289, 401 to 0.509240,
2,152 to 0.501548). So this is an OBSERVATION of consistency, NOT a dose-response finding, and an
alternative that fits equally well is that the sign tracks comparator headroom rather than dose. ***

## The two robot metrics measure different things, and the divergence is expected

| seed | `correct_by_deadline` (primary) | robot cloud on-time | alert attainment |
|---|---|---|---|
| s5 | -0.118110 | -67 of 127 | -0.049241 |
| s6 | **-0.231405** | -50 of 121 | -0.030603 |
| s7 | -0.114285 | -57 of 105 | **-0.024252** |

**The robot metrics stay large at s7 while attainment falls inside the bar.** *** THE EXPLANATION IS A
PROXY-VALIDITY FACT, not an anomaly: per `d231_ptg_guard/d231_ptg_prereg.json`'s own
`AMENDMENT_3_D232_CLOSES_BOTH_OPEN_FLAGS.flag_1_CLOSED_bar_2_is_readable.CAVEAT_THAT_MUST_BE_CARRIED_check_6_proxy_validity`,
THE DEVICE HALF OF `correct_by_deadline` IS INERT IN 244 OF 244 CELLS: `DEVICE_WAIT_S = 0` and device
latency peaks at 0.3108 s, so the device answer can never be late. ***
**Stated without any rate, which is the exactly true form: ON THE SUBSET WHERE THE DEVICE ANSWER IS
CORRECT, CLOUD LATENESS COSTS NOTHING ON THIS METRIC.** **So `correct_by_deadline` mixes cloud timeliness
with device accuracy, the device component carrying no timing information, and an arm that abandons the
cloud for a correct device answer scores as one that delivered a correct cloud answer on time.** **This
caveat must travel wherever the metric is quoted.** Cloud on-time is a pure timeliness count. **The two are
not two measurements of one thing that disagree; they measure different things.**

## Denominators, read per cell, and a trap

**All three pool denominators move with seed and NOTHING may be pooled as a count:**
robot **127 / 121 / 105**, single-shot **356 / 357 / 359**, dashcam instants **11,769 / 11,786 / 11,779**,
episodes **714 / 712 / 714**.
**The trap: s6 has the SAME episode count as s4 (712) with 22 more instants and a different histogram,
including a minimum episode size of 1 that no other seed has.** **Carrying "712" from s4 gets the episode
count right, passes a plausibility check, and silently uses the wrong instant total.** **Four of the five
carried-denominator errors tonight produced a visibly wrong number; this one would not.**

## Figure check by the accelerator box, every integer re-read from the nine cells

**All match.** The pooled alert on-time integers, the robot and single-shot denominators, both dose columns,
the robot on-time deltas (-67 = 52 - 119, -50 = 54 - 104, -57 = 27 - 84) and the three
`correct_by_deadline` deltas were re-read **from the cells rather than from its own earlier reports**, and
every one agrees with what this verdict divided by.
*** ONE EXCEPTION, STATED RATHER THAN GLOSSED: THE EPISODE COUNTS 714 / 712 / 714 ARE MINE AND IT CANNOT
CERTIFY THEM. *** They were read from the cells by this box, so they are verified once and not twice.
**Every attainment figure in this verdict divides by them**, so a wrong episode count would move every
delta. **The s7 figure in particular decides whether `-notouch` reads 0.99x INSIDE or something else, which
is the one place the count is load-bearing.**

## The 6,475 repeat: RESOLVED, a real coincidence

**Checked on the per-device dashcam breakdown, and the two cells differ on EVERY ONE of the six devices
while summing to the same total:**
```
stateoff s6   988  1,072  1,018  1,093  1,198  1,106   = 6,475
stateoff s7   921  1,059  1,198  1,192  1,026  1,079   = 6,475
differ on all six devices; no device matches
```
**So it is a genuine coincidence of integer arithmetic, not a copied or defaulted value.** **That is the
FIFTH exact equality tonight and the FOURTH that turned out real and differently composed** - alongside the
55-equals-55 robot tie, the s7 `correct_by_deadline` tie that decomposed into two offsetting one-unit
changes, and the 121-equals-121 count coincidence. **Only one of the five was an artefact, and it was a
broken probe rather than a broken number.**

## Flagged, not diagnosed

*** `-stateoff` gives a pooled alert on-time of EXACTLY 6,475 at BOTH s6 AND s7, over DIFFERENT denominators
(11,786 and 11,779). *** The attainments differ (0.478637 and 0.477296), so it is not a copied attainment:
**the pooled COUNT itself repeats across two seeds for the same arm.** Given that three exact equalities
tonight were real and differently composed while a fourth was a broken probe, **this should be checked
rather than assumed coincidental.** It does not affect any verdict above, since both deltas are computed
from their own seeds' denominators.

## CORRECTION, 2026-11-25 03:3x: the lattice sentences hold for two arms and NOT for `-stateoff`

**`piece_tokens` was read from all NINE block-A decision logs, one per cell rather than one per arm,
because one per arm is the error this correction exists to fix:**
```
fair-final _rep2   s5 {121 x13, 1024 x138}   s6 {121 x13, 1024 x134}   s7 {121 x11, 1024 x142}
notouch            s5 {121 x13, 1024 x139}   s6 {121 x13, 1024 x136}   s7 {121 x11, 1024 x143}
stateoff           s5 {121, 301, 1024}       s6 {121, 301, 481, 1024}  s7 {121, 481, 1024}
```
**So `fair-final` and `-notouch` emit only {121, 1024} at every seed and their decompositions STAND**
(32,470 = 31x1024 + 6x121; 32,107 = (31, 3); 32,228 = (31, 4)).
*** `-stateoff` EMITS REMAINDER PIECES AT ALL THREE SEEDS. Its peaks 33,010, 32,889 and 32,768 happen to
land on the lattice, but WITH REMAINDERS IN THE BUILD PATH THAT LANDING IS NOT EVIDENCE, so those three
decompositions are withdrawn from any "confirmed on-lattice" claim. ***
**The ceiling verdict on `peak_tokens` is UNAFFECTED: it rests on `host_peak_tokens` varying by seed, on
`peak_tokens` varying by arm and seed, and on the 1x control's 83 distinct values across 233 cells, none of
which is a lattice argument.**

## A MECHANISTIC LEAD NOBODY WAS LOOKING FOR: THE STATE CHANNEL APPEARS TO SUPPRESS REMAINDER PIECES

**`-stateoff` IS `fair-final` with the state channel off, and it emits remainders where `fair-final` does
not. `-notouch` has the state channel ON (only `touch_requests` is off) and emits NO remainders.**
```
state channel ON   -> no remainders   2 arms x 3 seeds = 6 cells
state channel OFF  -> remainders      1 arm  x 3 seeds = 3 cells
```
**So remainder emission tracks the state channel exactly across nine cells, and it is not a property of the
arm family.** *** THAT IS A CANDIDATE MECHANISM FOR WHAT THE STATE CHANNEL DOES, and it is the first one
tonight that is about the BUILD PATH rather than about scheduling: with the channel on, builds complete in
full slices; with it off, they leave partial remainders. *** **Labelled a HYPOTHESIS, not a finding: nine
cells show the correlation and nothing here shows the direction of causation or that remainders cost
anything.** **It is worth chasing because the state channel is the ablation that costs the most, and a
mechanism for that cost has not otherwise been identified.**

## A LIMITATION ON THE s7 COMPARISON, found after this verdict was first written: AN END-OF-WINDOW STALL AFFECTS ALL THREE s7 CELLS

**A census of all ELEVEN s7 kv0.5r cells found that SIX have ZERO completions between about 1,196.3 s and
about 1,199.5 s, against five that complete normally through it:**
```
STALLED      confidence-cascade 16 submitted / 0 completed   fair-final ORIGINAL 10 / 0
             fair-final _rep2    8 / 0    notouch 5 / 0    stateoff 4 / 0    covex-v6-rules 4 / 0
NOT STALLED  covex-v6-base 32 / 30   eco-llm 35 / 34   llf 36 / 27   mooncake 34 / 30   simplestream 35 / 31
```
*** ALL THREE BLOCK-A s7 CELLS ARE IN THE STALLED GROUP, so the s7 deltas in this verdict are between cells
that SHARE the event rather than between one affected and one clean cell. *** **The per-cell loss is at
most the 8, 5 and 4 requests submitted into that window, against the s7 dashcam denominator of 11,779 instants and 105
robot opportunities per cell, and the spread between arms is 4 requests. *(This sentence first read 11,764, which is **s4's** denominator carried onto an s7 statement; the verdict's own table gives s5 / s6 / s7 as 11,769 / 11,786 / 11,779. Numerically immaterial, and the wrong figure for the seed.)* NO FIGURE IN THIS VERDICT MOVES**,
and the `-notouch` 0.99x reading at s7 is unaffected at this magnitude.
**It is recorded because it is a shared property of the compared cells that was not known when the
comparison was made, not because it changes a number.**
**CAUSE NOT DIAGNOSED, NEEDS ENGINE TIMING: bounded and declined, not missed.** **The discriminating
question is well posed and worth one look later: what do `confidence-cascade` and five covex-v6 arms share
that `covex-v6-base` does not?** **It is NOT builds** (cascade builds nothing and stalls; base builds
nothing and does not), **NOT code state** (the original `fair-final` s7 is a different code state from
`_rep2` and both stall), and **NOT the piece-size pattern** (fair-final emits only {121, 1024} and
`-stateoff` emits remainders; both stall).

## REQUEST-COUNT RETENTION UNDER A HALVED POOL, and why it is NOT a capacity result

**Asked as "does rung 3 hold more throughput than rung 2 under memory pressure", and the answer has to be
stated in the unit that was actually measured.**
```
ratio kv0.5r / 1x, n_requests
  covex-v6-fair-final  s4  10,585 / 12,177 = 0.869   SAME CODE, SAME DIGEST: the clean one
  covex-v6-fair-final  s5 0.845   s6 0.862   s7 0.859  (_rep2 against 1x ORIGINALS: STRATUM B)
  covex-v6-state-final     mean 6,110 / 11,873 = 0.515
```
*** THE HONEST FORM: `fair-final` keeps about 86 PERCENT OF ITS 1x REQUEST COUNT under a halved pool and
`state-final` about 52 PERCENT. NEITHER NUMBER IS SERVED CAPACITY. ***
**`n_requests` is what the ARM CHOSE TO SEND, not what the server could serve**, and `state-final`'s count
is low largely because its policy leaves dashcam instants UNSENT: **7,195 / 6,414 / 7,455 of about 11,780
at s5 / s6 / s7, so it declines to send 54 to 63 percent of them.**
*** AND THE ENGINE POINTS THE OTHER WAY: the watch line shows `state-final` kv0.5r at 4,700 to 4,800 tok/s
against `fair-final` kv0.5r at 4,200 to 4,500, so the engine is NO LESS BUSY under `state-final` - it sends
FEWER BUT LARGER requests. ***
**So a first framing of this as "capacity falls linearly with the pool and quality falls superlinearly" is
WITHDRAWN before it was recorded as a result. It mixed a POLICY choice with SERVICE capacity, which is a
proxy-validity failure of exactly the kind check 6 exists to catch.** **A real capacity-retention
comparison needs served tokens or engine load, not request counts.**
**What DOES survive: the dashcam on-time rates are measured against ALL instants and therefore already
charge an arm for declining to send, so they remain a fair end-to-end metric. It is the request count that
is policy-contaminated, not the attainment.**

## THE s7 END-OF-WINDOW STALL: SIX ARMS EACH SIDE, FIVE HYPOTHESES ELIMINATED

```
STALLED      confidence-cascade, covex-v6-fair-final (BOTH code states), -notouch, -stateoff, covex-v6-rules
NOT STALLED  covex-v6-base, eco-llm, llf, mooncake, simplestream, covex-v6-state-final
```
| eliminated as the trigger | why |
|---|---|
| builds | `cascade` builds nothing and STALLS; `base` builds nothing and does NOT |
| code state | both `fair-final` s7 code states stall |
| piece-size pattern | `fair-final` {121, 1024} and `-stateoff` remainders BOTH stall |
| the rules core | `state-final` WRAPS `rules`; `rules` stalls, `state-final` does not |
| the state channel | ALL FOUR combinations occur, so it neither predicts nor prevents |

**The state channel's elimination is confirmed FROM THE CELLS, not from the arm names:** `state-final`
carries it (`state_decisions` 40,844 / 39,965 / 37,137 / 29,212 at s4 to s7, `completed_touch` 876 / 601 /
476 / 922) and `covex-v6-rules` does NOT (`state_decisions` ABSENT at s7). **So the four combinations are
ON and not stalled, ON and stalled, OFF and stalled, and ABSENT and stalled.**
**CAUSE NOT DIAGNOSED, NEEDS ENGINE TIMING: bounded and declined, not missed.**

## `-notouch` AGAINST ITS SAME-SEED COMPARATOR: THE FOUR ROWS, WITH NO TRADEOFF STATEMENT

**All four re-read from the cells. `cbd` is shown as COUNTS as well as the stored fraction, so the table
checks itself.**
| cell | den | cbd notouch / comp | d cbd | robot cloud on-time | d robot | dashcam | d dashcam |
|---|---|---|---|---|---|---|---|
| kv0.5r s5 | 127 | 58 / 57 (0.456693 / 0.448819) | **+1** | 114 / 119 | -5 | 6,363 / 6,597 | **-234** |
| kv0.5r s6 | 121 | 58 / 55 (0.479339 / 0.454545) | **+3** | 107 / 104 | **+3** | 7,035 / 6,889 | **+146** |
| kv0.5r s7 | 105 | 50 / 50 (0.476190 / 0.476190) | **0** | 83 / 84 | -1 | 7,177 / 6,804 | **+373** |
| 1x s4 | 132 | 84 / 85 (0.636364 / 0.643939) | **-1** | 124 / 127 | -3 | 8,568 / 8,323 | **+245** |

*** NO TRADEOFF OR COST STATEMENT IS SUPPORTED BY THESE ROWS, AND NONE IS MADE. ***
**What the data support, and only this: `-notouch`'s DASHCAM difference is POSITIVE at 3 of 4 cells, the
exception being `s5`, the LOWEST-DOSE seed. Its ROBOT differences are SMALL, MIXED IN SIGN, and inside or
near the only floor available (a same-code robot floor of 2 opportunities, n = 1 pair, kv0.5r).**
**In counts the headline robot metric moves by +1, +3, 0 and -1, so only s6 reaches that floor at all.**
*** TWO EARLIER READINGS OF THESE SAME ROWS ARE WITHDRAWN. *** **"Touches buy robot attainment and cost
dashcam attainment" was wrong. Its replacement, "the cost is consistent and the benefit is not" - offered
as the MORE CONSERVATIVE version - was ALSO wrong, and wrong twice over: it was built from memory of the
s6 cell rather than from the rows, and it used robot CLOUD ON-TIME, the secondary metric, in place of
`correct_by_deadline`, the headline one.** **`cloud on-time` is down at 3 of 4; `correct_by_deadline` is UP
at s5 and s6, TIED at s7 and DOWN at 1x s4. The two metrics disagree in sign on the same cells, which is
why the metric must be named before the direction.**

## THE 1x CELLS, AND WHY THE SIGN CHANGE IS CONFOUNDED RATHER THAN A MEMORY EFFECT

**Block D's `-notouch` dashcam deltas against their same-seed comparators, with s7 still to land:**
```
1x s4  +245  (dose 2,633)   SAME-CODE pair, c6a83f0eaf3d: block D's ONLY stratum-A pair
1x s5   +35  (dose   175)   STRATUM B, comparator f73fb3e4e5c9
1x s6   -12  (dose   406)   STRATUM B, comparator 29c42039ad11
```
**So across six cells the dashcam delta is 4 POSITIVE and 2 NEGATIVE, ranging 0.10 to 3.17 percent of about
11,780 instants.**
*** THE SIGN CHANGE BETWEEN kv0.5r AND 1x AT s5 AND s6 IS NOT A MEMORY EFFECT, AND MUST NOT BE WRITTEN AS
ONE. *** **The kv0.5r deltas (-234, +146) are SAME-CODE pairs; the 1x deltas (+35, -12) are STRATUM B
against ORIGINAL comparators running TWO DIFFERENT OLDER CODE STATES. So each apparent flip changes TWO
THINGS AT ONCE: the memory condition AND the comparator's code.** **The measured code-delta bound is 29 to
310 pooled dashcam instants, which COVERS BOTH 1x DELTAS ENTIRELY, so a comparator code change alone could
produce them.**
**The supported statement is therefore: "the dashcam delta's sign is NOT STABLE ACROSS THE CELLS WE HAVE,
and the two condition-to-condition sign changes COINCIDE WITH A COMPARATOR CODE CHANGE, so memory and code
are CONFOUNDED."** **It is NOT "the sign depends on the memory condition".**
*** AND THE SEPARATING COMPARISON DOES NOT EXIST IN THE DATA: no seed has a clean same-code pair at BOTH
conditions. Only 1x s4 is same-code, the kv0.5r s4 `-notouch` cell ran on tree e849b005af8d (functionally
same-code, with the diff named), and s5, s6 and s7 are stratum B at 1x. s7 will not separate them either,
because its 1x comparator is also an original. ***
**BLOCK D CANNOT BE POOLED ACROSS SEEDS**, because its three stratum-B comparators are three different
pieces of code: it is ONE CLEAN PAIR plus THREE STRATUM-B PAIRS SPANNING **TWO** COMPARATOR CODE STATES.
*(Corrected: this first read "three pairs not comparable to one another". The s6 and s7 originals SHARE
orchestration `29c42039ad11`, so block D has THREE comparator code states across FOUR pairs, not four, and
**s6 and s7 ARE mutually comparable**. Only s5 stands alone.)*
**A third reading of these rows is withdrawn here. "The sign reverses between memory conditions" was a
CONFOUND, asserted without naming the alternative explanation that was stated in the same message that
supplied the delta. That is a Step 5 failure specifically: the alternative was not merely available, it had
already been given to me.**

## BLOCK D VERDICT: 4 of 4 VALID, AND THE TOUCHES FACTOR IS NOT ESTABLISHED AS LOAD-BEARING AT 1x

**D238's condition is met: 4 of 4 valid, `source_agreement` OK on all four, no ENOSPC, no INVALID, no
reruns. The verdict may be written.**
| seed | stratum | robot | cbd | single-shot | dashcam | dashcam pp | dose notouch / comp |
|---|---|---|---|---|---|---|---|
| s4 | **SAME CODE** | -3 | **-1** | +1 | **+245** | +2.083 | 2,633 / 2,676 |
| s5 | B | 0 | **0** | -3 | +35 | +0.297 | 175 / 172 |
| s6 | B | -1 | **0** | 0 | -12 | -0.102 | 406 / 413 |
| s7 | B | 0 | **0** | -1 | +28 | +0.238 | 2,211 / 2,205 |

*** THE VERDICT: BLOCK D ESTABLISHES NO EFFECT OF THE TOUCHES FACTOR AT 1x ON ANY CHANNEL. ***
**`correct_by_deadline`, the headline robot metric, moves by -1, 0, 0, 0 against denominators of 132, 127,
121 and 105. Cloud on-time moves -3, 0, -1, 0. Single-shot moves +1, -3, 0, -1. Three of four channels are
indistinguishable from zero in EVERY cell.**
*** AND THE ONE NOTABLE VALUE IS NOT CORROBORATED BY THE CELL BEST PLACED TO CORROBORATE IT. s4 and s7
carry COMPARABLE DOSES - 2,633 and 2,211 touches suppressed, a ratio of 1.19 - and dashcam deltas of +245
and +28, a ratio of 8.8. The effect does NOT track the dose. *** **So the +245 at s4, which is block D's
only same-code pair and its largest figure, is not reproduced at a near-equal dose.**

**RULE 2 CLASSIFICATION: this is a null and it is classified "FIRED AND DID NOT HELP", which is the only
class that is evidence about the policy.** **The mechanism was PRESENT and VARIED: `state_touch_chosen_not_enacted` ran 175, 406, 2,211 and 2,633 across the four cells, a 15-fold range,
with `submitted_touch` 0 throughout and the comparator's `completed_touch` matching within 1.7 percent at
every seed. `state_decisions` agreed to within 0.5 percent, so the planner ran the same and the difference
was in ENACTMENT.** **It is NOT unexercised, NOT unexpressible and NOT cancelled by geometry.**
**Step 4 applies DIRECTLY and without a separate control run, because `-notouch` IS the negative control
for the touches factor: disabling touches does not change the outcome, which by Step 4's own statement
means the mechanism is not driving the result.**
*** SCOPE, STATED SO IT IS NOT OVERREAD: this is a finding about the TOUCHES FACTOR inside the policy, at
1x, on these four seeds. It is NOT a finding about the policy as a whole, and it does not bear on the other
four factors. ***
**TAKEN WITH BLOCK A: dashcam deltas across all seven cells are 4 positive and 3 negative with no stable
sign, the robot channel sits inside its floor at both memory conditions, and memory and comparator code are
confounded at every seed except 1x s4. THE TOUCHES FACTOR IS NOT ESTABLISHED AS LOAD-BEARING AT EITHER
MEMORY CONDITION.**

## THE SAME-CODE CLAIM IS STRONGER THAN PAIRWISE: ALL 34 CELLS RUN SINCE 19:00 SHARE ONE RUN-PATH SUBTREE

**Checked across every cell started since 19:00 on 2026-11-24, 34 in all, from the kv0.5r s4 `_rep2`
through `eco-llm` n8 s4:**
```
driver start-line TREE == that cell's OWN header.git_commit tree :  34 of 34   (0 differ, 0 unresolved)
whole trees        3932b279c3ea    2 cells (kv0.5r s4 _rep2, _rep3)
                   50e364b42493   32 cells
experiments/orchestration SUBTREE   c6a83f0eaf3d   in ALL 34
```
*** SO THE WHOLE-TREE DIFFERENCE LIES ENTIRELY OUTSIDE THE RUN PATH, and the run path is IDENTICAL across
all 34 cells. Every cell ran the code we assumed when pairing it, and ALL PAIRINGS STAND UNTOUCHED. ***
**This is a stronger statement than the pairwise checks it replaces: instead of "this pair matches on the
subtree", it is "all 34 cells match on the subtree, and the only run-path difference in any pair is the
stratum-B comparators' OWN older trees, which are already named."**
**It also vindicates the rule rather than merely passing it. The whole tree moved during the night, because
`research/` and `results/` pushes moved it; the SUBTREE did not. A pairing read from the whole tree would
have shown a spurious difference between two cells, and a pairing read from commit order would have been
wrong outright.**

## *** A DEFECT IN THE DRIVER, FOUND WHILE ARRANGING A PUSH, THAT INVALIDATES NOTHING ***

**The driver's between-cells pull EXISTS (`study_frozen_grid_driver_v37.sh:214`, `git pull --rebase -q
origin main`, up to 3 tries) and HAS BEEN FAILING SILENTLY ALL NIGHT, with errors sent to `/dev/null`.**
**The "PUSH NOT ON ORIGIN" lines at cell ends are that failure.** The consequence is that cells start on a
local base behind origin and the separate pusher completes the rebase about three minutes INTO the next
cell, which is the mid-cell path that produced an INVALID `torn_lazy_import` cell the previous day.
*** WHY IT HARMED NOTHING: NO `experiments/` CHANGE REACHED ORIGIN ALL NIGHT. Every push was to `research/`
or `results/`, so the run path never moved, which the 34-of-34 subtree check above confirms independently
rather than assumes. ***
**Recorded because a reader meeting the "PUSH NOT ON ORIGIN" lines in a log should know they are a real
silent failure and not noise, and because the safe-push procedure it forced is now the precedent: pause the
pusher at a cell boundary, rebase with no cell running, restore.**

## What this does NOT establish

- **No settled finding for either arm.** `-stateoff` clears the bar at two of three seeds and declines into
  it; `-notouch` clears at none on fixed-19.
- **Three seeds, one condition, one pool.** Nothing here speaks to 1x, where the `-stateoff` reading is
  6.16x and untouched.
- **The floors are n = 1.** The in-condition same-code pair is a single observation licensing the MEAN only:
  it disagreed on 78 to 84 percent of episodes in every comparison.
- **Per-episode churn makes every figure a statement about the mean:** 579 to 602 of 712 to 714 episodes
  differ in each comparison, with whole 19-instant episodes flipping in both directions and the net a small
  residue.
- **`-notouch` s4 is FUNCTIONALLY same-code only** (diff: `d179_rung2_verdict.py`, and one COMMENT line in
  `scorer/score.py`), never plain same-code.
