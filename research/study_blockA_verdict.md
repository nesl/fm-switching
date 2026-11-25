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
