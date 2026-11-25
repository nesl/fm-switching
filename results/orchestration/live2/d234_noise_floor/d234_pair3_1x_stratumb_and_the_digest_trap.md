# The 1x pair: a second stratum-B observation, and the digest trap CONFIRMED

**Provenance.** Read-only on flash, 2026-11-24. `origin/main` resolved once; committed
`d179_rung2_verdict.py` imported unmodified, md5 `fa8bce9bccff7cbbbad429df372b0df9` (post-D232).
**Positive control PASSED: the 1x original reproduces 0.619234 (fixed-19) and 0.711137 (true-denominator).**
**This is a STRATUM-B observation, not a floor.**

## The pair

`covex-v6-fair-final_n16_s4_1200s_h27_3t_L3_epg_rq30` against `..._rep2`.

| scale | original | rep2 | signed | difference |
|---|---|---|---|---|
| fixed-19 | 0.619234 | 0.615242 | -0.003992 | **0.003992** |
| true-denominator | 0.711137 | 0.705658 | -0.005479 | **0.005479** |

**The replicate is LOWER on both scales.** Hand-checkable: pooled alert on-time **8,377 against 8,323** of
11,764, so the difference is exactly **54 / 13,528 = 0.003992**.

## *** THE DIGEST TRAP IS CONFIRMED, AND A DIGEST-ONLY RULE WOULD HAVE MANUFACTURED A FLOOR THAT VOIDED EVERY VERDICT ON THE BOARD ***

| cell | `runner_digest` | evicted | over_cap | peak_tokens | fixed-19 att |
|---|---|---|---|---|---|
| 1x `_rep2` | `03e90ad889c91ba2` | **0** | **0** | 48,975 | 0.615242 |
| kv0.5r `_rep2` | `03e90ad889c91ba2` | **6** | 6 | 32,470 | 0.461561 |
| kv0.5r `_rep3` | `03e90ad889c91ba2` | **6** | 5 | 32,470 | 0.461709 |

**One source digest provably spans cells that are different experiments**, with `evicted` 0 against 6 and
attainment differing by **0.153681** on fixed-19 and **0.178110** on the new scale. *(Correction to an
earlier figure of mine: 0.146289 is the two ORIGINALS' 1x-versus-kv gap; the gap across the cells that
actually share the digest is 0.153681.)*
*** SO A DIGEST-ONLY REPLICATE RULE WOULD HAVE ADMITTED THE 1x AND kv0.5r REPS AS A SAME-CODE PAIR AND
PRODUCED AN IN-CONDITION FLOOR OF 0.153681 - FIVE TIMES THE ENTIRE CROSS-REGIME FLOOR, WHICH WOULD HAVE
VOIDED EVERY VERDICT ON THE BOARD. *** The digest-plus-condition rule is what prevents it, and this is the
case that proves it.
**The mechanism is worse than "the digest ignores server flags": the two `experiments/` trees are not even
the same.** The 1x rep ran on `50e364b42493`, the kv0.5r reps on `3932b279c3ea`. **The digest is identical
anyway because it covers only LOADED source, 151 files of 478**, and **the only 6 paths differing between
those trees are all under `analysis/robot_idle/`, none loaded at run time.** So the analysis-only
run-path-identical ruling is **verified by content**, with the probe fired (self-diff 0 paths; a genuinely
run-path-differing pair gives 88).

## Stratum B on three independent grounds, each verified

1. **The original has NO `source_agreement` key at all** - absent from `cell.json` and `header.json`. **So
   this pair cannot be certified by the digest route in principle: one side has no digest.**
2. `experiments/orchestration` differs: `9ac31b68c19e` against `c6a83f0eaf3d` (`lib` identical).
3. `scorer/score.py` differs: `93483b23` against `b3e49def`, both confirmed as real blobs, **with the
   comparison refused while either side was empty** - the guard that caught an empty-string false equality
   on the first attempt at that path.
**In total 63 `.py` files differ in the run path.** This is not a replicate pair.

## Against the three bars

| bar | fixed-19 | NEW |
|---|---|---|
| cross-regime committed max | **SMALLER**, 0.144x | **SMALLER**, 0.184x |
| in-condition CERTIFIED same-code pair | **LARGER, 26.97x** | **LARGER, 2.25x** |
| comparator-relevant stratum-B spread | SMALLER, 0.351x | SMALLER, 0.338x |

*** AND THE MOST IMPORTANT METHODOLOGICAL POINT IN THIS FILE: THE TWO SCALES DISAGREE ABOUT THE MAGNITUDE
BY A FACTOR OF 12 - 26.97x against 2.25x - BECAUSE THE CERTIFIED FIXED-19 PAIR DIFFERENCE IS A NEAR-EXACT
CANCELLATION AT 2 INSTANTS. SO ANY STATEMENT OF THE FORM "N TIMES THE FLOOR" IS MEANINGLESS WITHOUT NAMING
THE SCALE. *** The fixed-19 certified floor is unusually small by luck of cancellation, which inflates
every ratio taken against it. **The conservative reading of the marginal verdicts is the
comparator-relevant one at about 2.5 to 2.9x, not the 191x to 222x the fixed-19 certified floor yields.**

## What it licenses, and what it does not

**Licenses:** an upper bound on same-code noise for this arm at seed 4, and a tight one. Stratum-B
observations in `L3_epg_rq30` for this family now number **three: 0.003992, 0.011236, 0.011384**, agreeing
on an order of magnitude of roughly 0.004 to 0.011, well under the 0.027752 cross-regime bar. **An upper
bound that comes in low is informative about the bound.**
**Does NOT license:** use as a floor in either direction. It is code-changed by 63 files, so it bounds
noise only from above; it is **27x the certified pair on fixed-19**, and that ratio measures the **code
delta's contribution**, not run-to-run noise. **Reading it as a floor would inflate the floor 27-fold,
which is the wrong direction for marginal verdicts.** Still n=1 per pairing, seed 4 only, no percentile and
no per-episode claim: **this pair disagrees on 530 of 712 episodes**, 2,464 instants of absolute churn, max
per-episode difference 19, netting -54. **The certified in-condition floor is unchanged at 0.000148 /
0.002434 and remains the only certified same-code observation in this condition.**

## Episode structure, and `stateoff` 1x

**Key sets identical, per-episode size vectors identical element for element, 0 differing sizes.** The
`L3_epg_rq30` episode-structure invariance now holds across **six cells, two kv settings and three arms**,
so both scales' denominators are common and 1x and kv0.5r attainments are exactly commensurable.
**`stateoff` 1x is UNCHANGED**: 42.8x this new stratum-B observation on fixed-19, 35.8x on NEW, and 6.16x /
6.60x against the cross-regime max as committed. **Outside on every bar and both scales; it was never the
marginal one.** Its comparator qualifier is now sharper: **`orig_1x` has no `source_agreement` at all**, so
its code state rests only on a `header.git_commit` that happens to resolve, which is weaker provenance than
the digest route now primary. **The 1x cell's own `header.git_commit` `629f2c7a` is UNRESOLVABLE in flash's
store and the tree route was used instead.**
