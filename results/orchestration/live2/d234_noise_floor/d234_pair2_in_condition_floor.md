# The first same-code replicate pair in `L3_epg_rq30`: an in-condition observed difference

**Provenance.** Read-only analysis on flash, 2026-11-24. `origin/main` resolved once; the committed
`d179_rung2_verdict.py` imported unmodified, md5 `fa8bce9bccff7cbbbad429df372b0df9` (post-D232), with
`cd580554^` confirmed as `18bcbcefdad096048e3ec6dd2ee9b20d` (pre-D232). **This is ONE OBSERVED DIFFERENCE,
n = 1 pair. It is not a floor in any statistical sense and must not be used as one.**

## The pair

`covex-v6-fair-final_n16_s4_1200s_h27_3t_kv0.5r_L3_epg_rq30_rep2` against `..._rep3`.

| scale | rep2 | rep3 | difference |
|---|---|---|---|
| fixed-19 (`per_episode_fixed19_BESIDE`, the pre-D232 PRIMARY, the scale the committed floor is on) | 0.461561 | 0.461709 | **0.000148** |
| true-denominator (`per_episode_PRIMARY`, post-D232) | 0.527548 | 0.525114 | **0.002434** |

**POSITIVE CONTROL PASSED EXACTLY and over-delivered: all seven cells reproduce their committed values on
both scales**, including the comparator's 0.472945 and 0.619234 and the three committed ratios 6.156,
1.188 and 1.020.

## *** THE CROSS-REGIME FLOOR WAS FAR TOO WIDE, NOT TOO NARROW ***

| scale | in-condition pair | committed cross-regime max | the cross-regime bar is |
|---|---|---|---|
| fixed-19 | 0.000148 | 0.027752 | **187.5x WIDER** |
| true-denominator | 0.002434 | 0.029705 | **12.2x WIDER** |

**So the marginal verdicts STRENGTHEN rather than weaken, and NEITHER IS VOIDED.** `stateoff` kv0.5r moves
from 1.19x to **222.8x**; `notouch` kv0.5r from 1.02x to **191.3x**; `stateoff` 1x from 6.16x to 1154.3x.
All signs preserved, including `notouch` remaining above its comparator.
*One honest exception:* on the new scale the pair difference is **1.19x the cross-regime MEDIAN** (0.002041),
marginally above it though far below the max. On fixed-19 it is below the median too.

## *** THE QUALIFIER THAT MUST TRAVEL WITH THOSE RATIOS: THE COMPARATOR IS NOT SAME-CODE WITH THE PAIR ***

The certified pair is rep2 against rep3. **The cell the two marginal verdicts are actually measured against
is the ORIGINAL comparator, which ran on `experiments/` tree `9466e11f`, and 42 `.py` FILES DIFFER from the
reps' `3932b279c3ea`** - including `coordinator.py`, `cstate.py`, `asyncbackend.py` and `arms_v6cf.py`.

| pairing | fixed-19 | true-denom | same-code certified |
|---|---|---|---|
| **rep2 vs rep3** | **0.000148** | **0.002434** | **YES** |
| original vs rep2 | 0.011384 | 0.016234 | no, 42 `.py` differ |
| original vs rep3 | 0.011236 | 0.018668 | no, 42 `.py` differ |

**Against the uncertified but comparator-relevant spread of 0.011384, the two marginal verdicts are only
2.90x and 2.49x on fixed-19.** Still outside, far less comfortably. **The 191x and 222x figures are the
NARROWEST DEFENSIBLE READING, not the only one, and both bars must be reported side by side.**

## How same-code was certified, and it was NOT by the tree hash

**Both rep cells' `header.git_commit` values are ABSENT from the object store** (`6282ee40` and
`d52a57e7`), and neither is on origin: `git fetch origin <sha>` returns "not our ref". **The warned hazard
fired verbatim: `git rev-parse <absent-sha>:experiments` echoed the input sha back while failing.**
*** WHAT CERTIFIES THE PAIR IS IN-CELL AND STRONGER: `source_agreement.runner_digest` =
`03e90ad889c91ba2` IDENTICALLY in both, `child_start_digest` = `66128702d111118c` identically, over 478
on-disk source files, with `runner_child_mismatch`, `torn_lazy_import` and `moved_after_import` all empty
and `tree_files_changed_during_cell_n` = 0. *** A sha256-over-files proof of what the process actually
loaded, which needs no reachable commit and describes the bytes that RAN rather than the bytes someone
committed. **Both cells also share an identical `trace_dir`, so this is a same-input same-code pair
differing only by run-time nondeterminism.** Both `source_agreement.verdict` = OK; both `metrics_health`
PRESENT and `never_scraped`, read from `cell.json`.

## *** THE FINDING THAT LIMITS WHAT THIS LICENSES: THE MEAN IS STABLE AND THE EPISODES ARE NOT ***

The fixed-19 difference is exactly **2 instants out of 11,764**: pooled on-time **6,244 against 6,246**,
and 6244/13528 = 0.4615612 against 6246/13528 = 0.4617090, hand-checkable.
**But 559 OF 712 EPISODES HAVE A DIFFERING NUMERATOR, the sum of absolute per-episode differences is 3,216
instants, and max per-episode difference is 19 - entire episodes flipping from fully on-time to fully
missed, in BOTH directions (264 where rep3 is higher, 295 where rep2 is higher). The signed sum is +2.**
**So this is a floor on the MEAN ONLY.** It licenses no per-episode, per-device, per-stratum or tail claim
whatever: two same-code runs of this cell disagree about **78 percent of episodes**, about zero-attainment
counts (144 against 129) and about perfect counts (111 against 91 on the new scale). **The new scale's
16.4x larger difference is exactly this: the two net-differing instants land in short episodes where
1/len(v) is large, so the true-denominator mean amplifies what fixed-19 flattens.**

## Denominators

Identical across the pair and all seven cells: `n_instants` 11,764, 712 episodes, `instants_per_episode`
min 2 / median 19 / max 19, mean size 16.5225. **Episode key sets identical, and the per-episode SIZE
VECTORS identical element for element**, so both scales' denominators are bit-identical between the pair
members and **the entire difference is numerator.** 185 of 712 episodes are off the 19-lattice.

## What n = 1 does not license

**No percentile, no spread, no variance, no confidence interval, no standard error.** A single difference
has zero degrees of freedom. **And no claim that this is the typical or the maximum in-condition
difference.** The cross-regime stratum A, at n = 8, had its max set by a single pair at **3.77x the
next-largest** - direct evidence that one more pair in this family can multiply the observed maximum
several-fold. **A ninth draw here could be ten times this one and nothing in this result would have
anticipated it. Quoting 0.000148 as a bar is the narrowest possible reading and is anti-conservative.** The
ratios above should be quoted as "against a single observed same-code difference", never as "against the
in-condition noise floor". **The cross-regime floor is not retired by this; both bars stand side by side.**

## Open item, recorded rather than waved through

**`_rep3` has `n_errors` = 1 and `_rep2` has 0, with no payload stored anywhere** - no `errors` key, no
`error_detail`, nothing error-shaped in `arm_stats`. **This is an unresolved asymmetry inside the very pair
that sets the floor.** The committed 1x comparator also carries a lone error, so one is evidently tolerated
in this family, but it is not explained.

## Register marks

`correct_answers_delivered_by_deadline` is stored as a **FRACTION**, not a count: 0.643939 and 0.628788
with `n_by_deadline` 132. **The counts 85 and 83 are DERIVED** (0.643939 x 132 = 85.0 exactly), so the
derivation is sound but the stored value is the fraction. Dashcam on-time is a **committed sweep row**
summed over 6 devices; an independent recomputation from the module's own primitives returned the same
6,244 and 6,246, which is **a control validation of the reader, not a second measurement**.
