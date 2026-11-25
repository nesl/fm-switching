# D234 noise floor, RECOMPUTED on the post-D232 PRIMARY definition

## Provenance

| field | value |
|---|---|
| nature of this artefact | **RECOMPUTATION of an already-committed floor on a CHANGED metric definition. It is NOT a new measurement.** No run was executed, no repo file was edited. Every input was read from git at one pinned sha. |
| pinned sha (`origin/main`, resolved once) | `1c536fbece2dec1a5c0c2dbc7180490fcdb3fa46` |
| UTC timestamp of this recomputation | 2026-11-25T02:52Z |
| module recomputed with | `experiments/orchestration/live2/d179_rung2_verdict.py` at the pinned sha, imported UNMODIFIED |
| module md5 AFTER D232 (used here; blob `bed469b247ee18695d4ed585be32a5c4a61b600d`) | `fa8bce9bccff7cbbbad429df372b0df9` |
| module md5 BEFORE D232 (the floor's own reader; blob `9755aaa2c9b0241a4651965e646040a69efe4f63`) | `18bcbcefdad096048e3ec6dd2ee9b20d` |
| the floor file recomputed | `results/orchestration/live2/d234_noise_floor/d234_noise_floor.json` (48,025 bytes at the pinned sha) |
| the floor file's declared `ruling_and_analysis_sha` | `20155f4aab50068b4adbd49091ec9e090d62aea6` |
| commit that changed the definition | `cd5805547bb085fd0c0840c51298e090c4c05b3d` "D232", author 2026-11-24 16:33:35 -0800, **committer 2026-11-24 18:23:36 -0800** |

Working directory was NOT read or grepped: it is ~2,080 commits behind origin. Free disk at start 28 GB (floor 15 GB). No artefact read in this recomputation contains the string `No space left on device`; see the probe-firability note below.

### The definition change, verified here and not taken on report

`git cat-file -t` confirms all four cited commits (`cd580554`, `35e3c57e`, `20155f4a`, `1c536fbe`) are present as real commit objects in the local store before any `rev-parse` was trusted. The blob of `d179_rung2_verdict.py` is byte-identical at `35e3c57e` and `20155f4a` (`9755aaa2...`, md5 `18bcbce...`) and differs at `cd580554` and at the pinned sha (`bed469b2...`, md5 `fa8bce9b...`). Both md5s match the claim exactly.

The diff of those two blobs confirms the claim in full, inside `_alert_episode_block`:

- **Before D232:** `per_episode_PRIMARY.mean_attainment` = mean over episodes of `k / 19` (`ALERT_INSTANTS_PER_EPISODE`), and `per_episode_true_denominator_BESIDE` carried `k / len(v)`.
- **After D232:** `per_episode_PRIMARY.mean_attainment` = mean over episodes of `k / len(v)` (the episode's ACTUAL decision-instant count), and the fixed-19 number was **renamed** to `per_episode_fixed19_BESIDE`. The key `per_episode_true_denominator_BESIDE` no longer exists.

**The key name `per_episode_PRIMARY.mean_attainment` was kept across a change of meaning.** The committed D234 floor declares its `read_route` as `alert_episodes.numerator_COMMITTED_RULE_PRIMARY.per_episode_PRIMARY.mean_attainment` through this module at `20155f4a`, where PRIMARY was fixed-19. The committed floor values are therefore on the fixed-19 scale, and any post-D232 read of the same key compared against them mixes scales. That is the defect this file repairs.

(The same commit also made `--comparator-arm` a required argument of `verdict_for_seed` with no silent default to the base. That change is noted for the record and does not bear on the floor.)

---

## 1. What the committed floor file actually says (extracted, not inferred)

`read_route`:

| metric | route |
|---|---|
| per-episode alert attainment | `experiments/orchestration/live2/d179_rung2_verdict.py` (imported UNMODIFIED from the ruling sha) -> `read_cell(run_dir)` -> `alert_episodes.numerator_COMMITTED_RULE_PRIMARY.per_episode_PRIMARY.mean_attainment` |
| robot on-time | `cell.json` -> `score.score.robot_value.n_cloud_standing`, denominator `score.score.robot_value.n` |
| robot correct-by-deadline | `cell.json` -> `score.score.robot_value.standing_accuracy_by_deadline` |

`same_code_check._how`, verbatim: "each side's `header.json` git_commit was read; where they differ, `git diff --name-only <shaA> <shaB> -- experiments/ fleet/ scorer/` was run and the changed .py files counted. A pair with any changed .py in the run path is NOT a replicate."

`LIMITATIONS`, verbatim:
1. n=8 is too few for a 95th percentile; the max observed difference is the honest statistic and is reported as such.
2. no same-code replicate pair exists in the `L3_epg_rq30` condition the verdicts were called in; the floor is transferred across conditions on the strength of an identical alert-metric definition, not an identical regime.
3. robot correct-by-deadline has NO same-code replicate pair at all; no floor is reported for it.
4. the robot on-time fraction floor is granularity-limited by denominators of 15 to 28; only the count floor of 1 opportunity transfers.
5. seeds in the floor are 0 and 6 only (s0 x6, s6 x2); seeds 1 to 3 and HOLDOUT were never read.

`COMMENSURABILITY_CAVEAT` (condensed, its own words): every same-code replicate pair is in the pre-EP-G `_1200s_h27_3t` condition; every pair in the `L3_epg_rq30` condition the verdicts were called in is code-changed, so the floor and the verdicts are not from the same regime. What IS the same is the alert type (device prefix `dash`, kind `monitor`, deadline 1.0 s), the episode recipe, the 21-frame cap and "the declared per-episode denominator 19". What is NOT the same: the module's own crosstab check returns FALSE on every stratum-A cell because the robot deadline is 5.0 s there against 3.0 s in `L3_epg_rq30`, and stratum-A alert attainment sits at 0.710 to 0.932 against three of four verdict arms below 0.20. Which way it cuts: stratum B is in the verdict condition and gives a larger spread, is code-contaminated so is an upper bound not a floor, and both strata put the floor at or above 0.02.

**Note for the reader:** that caveat names "the declared per-episode denominator 19" as part of what is identical between the two regimes. Section 7 below shows that the actual instant counts are 19 in neither regime uniformly, and that their modes DIFFER between them (19 in `L3_epg_rq30`, 21 in `_1200s_h27_3t`). The caveat was true of the declared constant and is not true of the quantity the new PRIMARY divides by.

### Stratum A: the 8 same-code replicate pairs, by cell name

| # | base cell | rerun cell | arm | seed | n_dev | same sha | committed att. pair | committed abs diff |
|---|---|---|---|---|---|---|---|---|
| 1 | `b7-edf-feasibility_n16_s0_1200s_h27_3t` | `..._rerun` | b7-edf-feasibility | 0 | 16 | yes | 0.814354 / 0.816342 | 0.001988 |
| 2 | `b7-edf-feasibility_n20_s0_1200s_h27_3t` | `..._rerun` | b7-edf-feasibility | 0 | 20 | no, 0 changed .py | 0.008055 / 0.008055 | 0.0 |
| 3 | `eco-llm_n14_s0_1200s_h27_3t` | `..._rerun` | eco-llm | 0 | 14 | yes | 0.820832 / 0.821126 | 0.000294 |
| 4 | `eco-llm_n16_s0_1200s_h27_3t` | `..._rerun` | eco-llm | 0 | 16 | yes | 0.738830 / 0.738241 | 0.000589 |
| 5 | `eco-llm_n16_s6_1200s_h27_3t` | `..._rerun` | eco-llm | 6 | 16 | yes | 0.756524 / 0.754607 | 0.001917 |
| 6 | `hybrid-F-lhreq_n16_s0_1200s_h27_3t` | `..._rerun` | hybrid-F-lhreq | 0 | 16 | yes | 0.787265 / 0.779904 | 0.007361 |
| 7 | `hybrid-F6-lhreq_n16_s0_1200s_h27_3t` | `..._rerun` | hybrid-F6-lhreq | 0 | 16 | yes | 0.710710 / 0.738462 | **0.027752** |
| 8 | `mooncake_n16_s6_1200s_h27_3t` | `..._rerun` | mooncake | 6 | 16 | yes | 0.854931 / 0.858838 | 0.003907 |

Every stratum-A cell carries `robot_correct_by_deadline_ABSENT`: `score.score.robot_value.standing_accuracy_by_deadline` is **ABSENT** from that condition's `robot_value` block. That is reported as ABSENT, never as 0.

### Stratum B: the 12 code-changed pairs, by cell name

All are `_n16_sX_1200s_h27_3t_L3_epg_rq30` against the same name plus `_rerun`:
`covex-v6-final` s4; `eco-llm` s4, s6, s7; `simplestream` s4, s5, s6, s7; `confidence-cascade` s4, s5, s6, s7.

---

## 2 and 3. POSITIVE CONTROL: the fixed-19 column must reproduce the committed floor. IT DOES.

Both members of all 8 stratum-A pairs (and all 12 stratum-B pairs) were re-read with the module at the pinned sha, imported unmodified, taking `per_episode_fixed19_BESIDE.mean_attainment` as the old PRIMARY and `per_episode_PRIMARY.mean_attainment` as the new one.

| # | cell pair | fixed-19 recomputed (base / rerun) | committed att. pair | fixed-19 abs diff | committed abs diff | match |
|---|---|---|---|---|---|---|
| 1 | b7-edf-feasibility n16 s0 | 0.814354 / 0.816342 | 0.814354 / 0.816342 | 0.001988 | 0.001988 | **EXACT** |
| 2 | b7-edf-feasibility n20 s0 | 0.008055 / 0.008055 | 0.008055 / 0.008055 | 0.0 | 0.0 | **EXACT** |
| 3 | eco-llm n14 s0 | 0.820832 / 0.821126 | 0.820832 / 0.821126 | 0.000294 | 0.000294 | **EXACT** |
| 4 | eco-llm n16 s0 | 0.738830 / 0.738241 | 0.738830 / 0.738241 | 0.000589 | 0.000589 | **EXACT** |
| 5 | eco-llm n16 s6 | 0.756524 / 0.754607 | 0.756524 / 0.754607 | 0.001917 | 0.001917 | **EXACT** |
| 6 | hybrid-F-lhreq n16 s0 | 0.787265 / 0.779904 | 0.787265 / 0.779904 | 0.007361 | 0.007361 | **EXACT** |
| 7 | hybrid-F6-lhreq n16 s0 | 0.710710 / 0.738462 | 0.710710 / 0.738462 | 0.027752 | 0.027752 | **EXACT** |
| 8 | mooncake n16 s6 | 0.854931 / 0.858838 | 0.854931 / 0.858838 | 0.003907 | 0.003907 | **EXACT** |

Sorted fixed-19 per-pair differences, recomputed: `[0.0, 0.000294, 0.000589, 0.001917, 0.001988, 0.003907, 0.007361, 0.027752]` -- **identical, element for element, to the committed `all_sorted`.** min 0.0, median 0.001953, max observed 0.027752, linear-interp p95 0.020615, all reproduced.

**POSITIVE CONTROL: PASSED, 8 of 8 pairs and 16 of 16 individual cells exact to 6 decimals.** All 12 stratum-B pairs also reproduce exactly (24 of 24 cells), which is 20 of 20 pairs in total. The reader is therefore sound and `per_episode_fixed19_BESIDE` after D232 is the same quantity `per_episode_PRIMARY` was before it. Everything below is gated on this and the gate is open.

---

## 4. The floor on the NEW definition -- STRATUM A

| # | cell pair | NEW PRIMARY (base / rerun) | NEW abs diff | fixed-19 abs diff | new / old |
|---|---|---|---|---|---|
| 2 | b7-edf-feasibility n20 s0 | 0.007288 / 0.007288 | 0.0 | 0.0 | n/a (both 0) |
| 4 | eco-llm n16 s0 | 0.753083 / 0.752734 | 0.000349 | 0.000589 | 0.59x |
| 3 | eco-llm n14 s0 | 0.842745 / 0.843131 | 0.000386 | 0.000294 | 1.31x |
| 5 | eco-llm n16 s6 | 0.777201 / 0.775198 | 0.002003 | 0.001917 | 1.04x |
| 1 | b7-edf-feasibility n16 s0 | 0.831442 / 0.833522 | 0.002080 | 0.001988 | 1.05x |
| 8 | mooncake n16 s6 | 0.878220 / 0.881933 | 0.003713 | 0.003907 | 0.95x |
| 6 | hybrid-F-lhreq n16 s0 | 0.803230 / 0.794579 | 0.008651 | 0.007361 | 1.18x |
| 7 | hybrid-F6-lhreq n16 s0 | 0.723648 / 0.753353 | **0.029705** | 0.027752 | 1.07x |

**All 8 NEW-definition per-pair absolute differences, sorted:**
`[0.0, 0.000349, 0.000386, 0.002003, 0.002080, 0.003713, 0.008651, 0.029705]`

| statistic | fixed-19 (committed) | NEW true-denominator | change |
|---|---|---|---|
| n pairs | 8 | 8 | -- |
| min | 0.0 | 0.0 | unchanged |
| **median** | 0.001953 | **0.002041** | **+0.000088, 1.045x WIDER** |
| **max observed** | 0.027752 | **0.029705** | **+0.001953, 1.070x WIDER** |
| p95 linear interp (not supportable at n=8, given for continuity only) | 0.020615 | 0.022336 | 1.083x wider |
| max / next-largest | 3.770x | 3.434x | still one dominating pair |

**The floor is WIDER on the new definition, by 7.0 percent on the max observed (0.027752 to 0.029705) and 4.5 percent on the median (0.001953 to 0.002041).** The widening is small and the ordering of the pairs is nearly preserved; the same pair (hybrid-F6-lhreq n16 s0) sets the maximum on both definitions. Two of the eight pairs moved the other way (eco-llm n16 s0 narrowed to 0.59x, mooncake n16 s6 to 0.95x), so the widening is a net effect of the stratum, not a uniform rescaling, and **it is not legitimate to obtain the new floor by multiplying the old one by a constant.** That is why this file recomputes rather than rescales.

## 5. The floor on the NEW definition -- STRATUM B (code-changed, an UPPER BOUND, not a floor)

All 12 pairs are recoverable. No pair was excluded: all 24 cells exist at the pinned sha, all reproduce their committed fixed-19 value exactly, and none is marked INVALID.

| cell pair (arm, seed) | NEW PRIMARY (base / rerun) | NEW abs diff | fixed-19 abs diff |
|---|---|---|---|
| eco-llm s7 | 0.759718 / 0.757031 | 0.002687 | 0.003317 |
| eco-llm s4 | 0.070438 / 0.067064 | 0.003374 | 0.002883 |
| covex-v6-final s4 | 0.712180 / 0.699629 | 0.012551 | 0.014119 |
| eco-llm s6 | 0.423946 / 0.408351 | 0.015595 | 0.015450 |
| confidence-cascade s5 | 0.185084 / 0.204683 | 0.019599 | 0.011721 |
| simplestream s4 | 0.917201 / 0.937342 | 0.020141 | 0.017445 |
| simplestream s6 | 0.950852 / 0.978490 | 0.027638 | 0.024542 |
| simplestream s7 | 0.943472 / 0.971310 | 0.027838 | 0.022409 |
| simplestream s5 | 0.878500 / 0.909356 | 0.030856 | 0.028011 |
| confidence-cascade s6 | 0.136710 / 0.196487 | 0.059777 | 0.048861 |
| confidence-cascade s4 | 0.287184 / 0.193851 | 0.093333 | 0.085674 |
| confidence-cascade s7 | 0.085822 / 0.185662 | **0.099840** | 0.085803 |

Sorted NEW: `[0.002687, 0.003374, 0.012551, 0.015595, 0.019599, 0.020141, 0.027638, 0.027838, 0.030856, 0.059777, 0.093333, 0.099840]`

| statistic | fixed-19 (committed) | NEW true-denominator | change |
|---|---|---|---|
| n pairs | 12 | 12 | -- |
| min | 0.002883 | 0.002687 | 0.93x narrower |
| median | 0.019927 | 0.023890 | 1.199x WIDER |
| max observed | 0.085803 | 0.099840 | **1.164x WIDER** |

**Stratum B is also WIDER on the new definition**, and by more than stratum A: +16.4 percent on the max, +19.9 percent on the median. The direction agrees with stratum A, which is the one thing these samples jointly support.

---

## 6. Today's deltas RE-RULED on the new definition

Cell directory names were found by listing `results/orchestration/live2/frozen_test/runs/` at the pinned sha, not assumed. Every value below is a fresh `read_cell` of that directory through the module at the pinned sha; the fixed-19 column is **not** a rescaling of today's numbers, it is an independent re-read that happens to agree with them.

Per-cell attainments, both definitions:

| cell | fixed-19 (old PRIMARY) | NEW PRIMARY (true denom) | n_episodes | `run_valid` | `err` |
|---|---|---|---|---|---|
| `covex-v6-fair-final_n16_s4_1200s_h27_3t_L3_epg_rq30` (comparator, 1x) | 0.619234 | 0.711137 | 712 | true | none |
| `covex-v6-fair-final_n16_s4_1200s_h27_3t_kv0.5r_L3_epg_rq30` (comparator, kv0.5r) | 0.472945 | 0.543782 | 712 | true | none |
| `covex-v6-fair-final-stateoff_n16_s4_1200s_h27_3t_L3_epg_rq30` | 0.448403 | 0.515148 | 712 | true | none |
| `covex-v6-fair-final-stateoff_n16_s4_1200s_h27_3t_kv0.5r_L3_epg_rq30_rerun` | 0.439976 | 0.505729 | 712 | true | none |
| `covex-v6-fair-final-notouch_n16_s4_1200s_h27_3t_kv0.5r_L3_epg_rq30` | 0.501257 | 0.574823 | 712 | true | none |
| `covex-v6-fair-final-stateoff_n16_s4_1200s_h27_3t_kv0.5r_L3_epg_rq30` (the NON-rerun; see note) | 0.433989 | 0.498958 | 712 | true | **`TornTree: torn_lazy_import ['experiments/orchestration/live2/arms_final_ladder.py']`** |

The three fixed-19 readings given for checking are reproduced exactly: stateoff 1x 0.448403 vs 0.619234; stateoff kv0.5r `_rerun` 0.439976 vs 0.472945; notouch kv0.5r 0.501257 vs 0.472945. **The handed-over numbers check out and were not assumed.**

**On the count of four.** Only three distinct treatment-versus-comparator deltas exist among the cells named in the task, because `notouch` exists at kv0.5r only (there is no `covex-v6-fair-final-notouch` 1x directory at the pinned sha). The fourth row below is the `stateoff` kv0.5r cell WITHOUT `_rerun`, which is the only other candidate in the ladder and is almost certainly why the `_rerun` exists: it carries a `TornTree: torn_lazy_import` error on `arms_final_ladder.py`. It is reported for completeness and **must not be used**; the `_rerun` supersedes it.

Re-ruling against the matching stratum-A max observed (fixed-19 bar 0.027752; NEW bar 0.029705):

| delta | definition | treatment | comparator | delta (comp minus treat) | abs | ratio to matching floor | above floor? |
|---|---|---|---|---|---|---|---|
| stateoff 1x | fixed-19 | 0.448403 | 0.619234 | +0.170831 | 0.170831 | **6.156x** | yes |
| stateoff 1x | **NEW** | 0.515148 | 0.711137 | +0.195989 | 0.195989 | **6.598x** | yes |
| stateoff kv0.5r `_rerun` | fixed-19 | 0.439976 | 0.472945 | +0.032969 | 0.032969 | **1.188x** | yes, marginally |
| stateoff kv0.5r `_rerun` | **NEW** | 0.505729 | 0.543782 | +0.038053 | 0.038053 | **1.281x** | yes, marginally |
| notouch kv0.5r | fixed-19 | 0.501257 | 0.472945 | -0.028312 | 0.028312 | **1.020x** | yes, barely; sign is REVERSED (notouch above the comparator) |
| notouch kv0.5r | **NEW** | 0.574823 | 0.543782 | -0.031041 | 0.031041 | **1.045x** | yes, barely; sign still reversed |
| stateoff kv0.5r NON-rerun (ERRORED, do not use) | fixed-19 | 0.433989 | 0.472945 | +0.038956 | 0.038956 | 1.404x | n/a |
| stateoff kv0.5r NON-rerun (ERRORED, do not use) | **NEW** | 0.498958 | 0.543782 | +0.044824 | 0.044824 | 1.509x | n/a |

**Does any verdict CHANGE? NO. Not one of the four.** On the new definition every delta grows (by 14.7, 15.4, 9.6 and 15.1 percent respectively) while its floor grows by only 7.0 percent, so every ratio rises and every sign is preserved. The two marginal calls become slightly less marginal rather than more: 1.188x to 1.281x, and 1.020x to 1.045x. The qualitative reading is unchanged: `stateoff` at 1x is far outside the floor; `stateoff` at kv0.5r and `notouch` at kv0.5r sit just outside it and are not separable from replicate noise in any practical sense.

Two cross-checks that do not change the verdicts but bound them:

- Against the stratum-A **interpolated p95** rather than the max (0.020615 old, 0.022336 new), the ratios become 8.29x / 8.77x, 1.60x / 1.70x and 1.37x / 1.39x. Unchanged in sign and in which deltas are marginal. The p95 is not a supportable statistic at n=8 and is given only to show the verdicts do not hinge on which of the two bars is used.
- Against the stratum-B max observed, which IS in the `L3_epg_rq30` condition but is code-contaminated and so is an upper bound and not a floor (0.085803 old, 0.099840 new): `stateoff` 1x is 1.99x / 1.96x and stays outside; **`stateoff` kv0.5r (0.38x / 0.38x) and `notouch` kv0.5r (0.33x / 0.31x) fall WELL INSIDE it on both definitions.** The marginal pair being inside the upper bound is a pre-existing feature of the committed analysis, is unchanged by D232, and is the strongest reservation attached to those two deltas on either definition.

---

## 7. LATTICE CONSEQUENCE: `k/19` no longer holds on the new PRIMARY

On the new PRIMARY, `mean_attainment` is a mean of `k / len(v)` over episodes of differing `len(v)`, so the per-episode values no longer lie on the `k/19` lattice and no linear combination of them does either. Any downstream assertion that an attainment value is an integer multiple of `1/19`, or that a delta is a multiple of `1/(19 n)`, **will fire falsely on every post-D232 read.**

Representative cell, `covex-v6-fair-final_n16_s4_1200s_h27_3t_L3_epg_rq30` (counted directly from the module's own `_committed_delivery` / `_episode_key` primitives on that cell's outcomes and requests):

- 712 episodes, **14 distinct episode sizes**, **mean size 16.5225**
- size histogram: `{2:1, 4:1, 5:4, 6:2, 7:7, 8:33, 9:15, 10:94, 11:22, 12:2, 13:2, 15:1, 18:1, 19:527}`
- **OFF-LATTICE (size not equal to 19): 185 of 712 episodes, 25.98 percent.** On-lattice: 527.
- The module reports the same shape in its own `instants_per_episode` block: `{min: 2, median: 19.0, max: 19}`.

`covex-v6-fair-final-stateoff_n16_s4_1200s_h27_3t_L3_epg_rq30` has an identical histogram and the identical 185 of 712, as expected: the episode recipe is fixed by the seed and the condition, not by the arm.

**A finding not in the committed floor file, which bears on its own commensurability claim.** In the stratum-A condition `_1200s_h27_3t`, the modal episode size is **21**, not 19, and `episode_positions_seen` is 0 to 20 rather than 2 to 20. In `b7-edf-feasibility_n16_s0_1200s_h27_3t`: 715 episodes, 14 distinct sizes, mean 18.5203, histogram `{1:1, 2:2, 7:4, 8:1, 9:3, 10:31, 11:19, 12:93, 13:24, 14:5, 15:2, 19:1, 20:1, 21:528}`, and **714 of 715 episodes, 99.86 percent, are off the 19-lattice.** So the fixed-19 denominator was never the actual instant count in the stratum-A regime at all, and the two regimes' actual denominators differ systematically (mode 21 against mode 19). The `COMMENSURABILITY_CAVEAT` lists "the declared per-episode denominator 19" among what is identical across the two regimes. That was true of the declared constant. It is **not** true of the quantity the new PRIMARY divides by, and the new-definition stratum-A floor is therefore measured on predominantly 21-instant episodes while the verdict cells are predominantly 19-instant. This is a NEW commensurability gap that the fixed-19 floor did not have, and it is additional to, not a replacement for, the gap the committed file already declares.

---

## WHAT THIS CANNOT ESTABLISH

1. **n=8 cannot support a percentile.** `0.95 * (8 - 1) = 6.65`, so any interpolated p95 sits 65 percent of the way from the 7th value to the single largest and is a restatement of the largest, not an estimate of a tail. The honest statistic is the **max observed**: 0.027752 on fixed-19 and **0.029705** on the new definition. The p95 figures (0.020615 and 0.022336) are carried here only to show the verdicts do not depend on which bar is used, and must not be quoted as percentiles.
2. **The max observed is set by one pair on either definition.** `hybrid-F6-lhreq_n16_s0_1200s_h27_3t` sets it on both, at **3.77x the next-largest pair on fixed-19 (0.027752 against 0.007361) and 3.43x on the new definition (0.029705 against 0.008651)**. It is one run pair out of eight. The floor is effectively a single observation with a seven-point context, and nothing here establishes that a ninth pair would not double it. The figure "about 3.8x the next" holds on the fixed-19 definition and is 3.43x, not 3.8x, on the new one.
3. **There is still no same-code replicate in the `L3_epg_rq30` condition.** Recomputing on the new definition does not touch this. Every stratum-A pair remains in the pre-EP-G `_1200s_h27_3t` condition with a 5.0 s robot deadline, and every pair that IS in `L3_epg_rq30` is code-changed by 42 to 168 `.py` files and so is stratum B, an upper bound. The floor is still transferred across regimes, and section 7 shows that the transfer now also crosses a difference in the actual per-episode denominator, so the new-definition transfer is **weaker**, not stronger, than the fixed-19 one even though both the floor and the deltas grew.
4. **Nothing here is a measurement.** No simulation was run. This file re-reads committed artefacts through a changed reader. It cannot speak to whether either definition is the right one, only to what each yields and whether the comparison is commensurable.
5. **This recomputation covers one metric.** Robot on-time and robot correct-by-deadline are untouched by D232 (they are read from `cell.json`, not through `_alert_episode_block`), so their committed floors stand unchanged. Robot correct-by-deadline remains **ABSENT** from every stratum-A cell's `robot_value` block and has no same-code floor at all. ABSENT, not zero.
6. **Seed and arm coverage is unchanged and narrow.** Stratum A is seeds 0 and 6 only (s0 x6, s6 x2) and five arms, none of them a `covex-v6-fair-final` variant. The deltas re-ruled in section 6 are all seed 4.
7. **One candidate L3 replicate could NOT be certified, and the check that would have certified it returned a FALSE ZERO.** `covex-v6-fair-final_n16_s4_1200s_h27_3t_kv0.5r_L3_epg_rq30` and its `_rep2` are the same arm, seed and condition in the verdict regime, and would fill the gap in item 3 if they were same-code. Their `header.json` shas differ (`9172f154...` against `6282ee40...`), and `git diff --name-only <a> <b> -- experiments/ fleet/ scorer/` returns **0 changed `.py` files**, which would read as a same-code proof. It is not one: **`git cat-file -t 6282ee40...` shows that sha is ABSENT from the local object store**, and `git diff` against an unresolvable sha yields an empty diff rather than an error. The zero is an artefact of the missing object. The pair is therefore **NOT** added to stratum A, and the item-3 limitation stands. For the record only, its differences are 0.011384 on fixed-19 and 0.016234 on the new definition, both of which would sit mid-stratum; they are not part of any floor reported here.

## Probe firability (every zero and every not-found in this file)

Three zeros and one absence are reported above. Each was proved capable of firing, per the standing hazard that a probe which cannot fire returns the reassuring answer.

| zero / absence reported | proof the probe CAN fire |
|---|---|
| no artefact contains `No space left on device` (0 hits across the whole `runs/` tree at the pinned sha) | the identical `git grep` form over the identical pathspec returns **318** files for a string known to be present (`run_valid` in `*/cell.json`). The grep works; the string is genuinely absent. |
| `metrics_health` ABSENT from the two `covex-v6-fair-final` comparator cells' `cell.json` | the same probe returns 1 for the four `stateoff` / `notouch` cells, and `git grep -l metrics_health` over `runs/*/cell.json` at the pinned sha matches **23** files. It is 0 for `runs/*/header.json` across the entire tree, confirming the standing hazard: a probe reading `header.json` would have returned a false ABSENT for all 27 cells including the ones that have the key. **`metrics_health` lives in `cell.json`.** Where present it reads `state: never_scraped, engine_metrics_trusted: false, scrape_enabled: false`, which bears on engine KV quantities and not on alert attainment. |
| `standing_accuracy_by_deadline` ABSENT from stratum-A `robot_value` | recorded as such by the committed floor file per cell, with the key list it DID find in that block. Reported as ABSENT, never as 0. |
| 0 changed `.py` files between the two `kv0.5r` run shas | **the probe COULD NOT fire**, and the zero is rejected. See item 7 above. This is the one zero in this file that is not trusted. |
