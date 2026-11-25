# D259: METHOD A IS 0.331566, TOUCH IS REACHABLE UNDER IT, AND THE MARGIN IS NOT BEHIND THE D249 SWITCH

*** THE PRE-COMMITMENT WAS HONOURED LITERALLY. The binning, tie rule, merge rule, quantile, bootstrap unit
and resample count were written to a file and sha256'd BEFORE any per-bin error, any p90 or any bootstrap
existed. Method A's number became the margin with no further choice. No third method, no re-binning, no
change of quantile, no reach for B. ***
**No live gate cell was run, per D259. Nothing is committed to `experiments/`. KV is not enforced in this
harness, so no reduced-memory claim is made from any of it.**

## THE POSITIVE CONTROL CAME FIRST

**Before computing anything new, the committed D169 statistic was reproduced EXACTLY: n 476 / 271 / 205,
p90 0.164560, warm 0.150341, cold 0.173231, p50 0.011560, 8 of 8 trace fairness digests OK, 0 cells and 0
questions skipped.** **So a surprising Method A value could not be the extraction breaking.**

## (1) METHOD A = 0.331566 IN ON-TIME UNITS

**Hand-checked by this session from the driving bin: sum of `P_hat` 29.91518416109821 / 48 = 0.6232330034,
on time 14 / 48 = 0.2916666667, error 0.331566336690 - matching to twelve decimals.** Hence
`MARGIN_CF = 0.0828915`, and 0.0828915 / 0.250 = 0.331566 exactly.
**All ten equal-count deciles met the minimum 40 with no merge. p50 over questions 0.040944.**
```
the new bar against the old, and against the best decision in the cell:
   A / OLD      = 0.5037      the new bar is about half the old
   A / Z max    = 0.5968      it sits at 59.7 pct of the best decision
   OLD / Z max  = 1.1848      the old bar sat ABOVE it, which is why TOUCH was unreachable
```

*** A FRAGILITY THE NUMBER ITSELF HIDES, STATED AND NOT ACTED ON. *** With n = 476 the nearest-rank p90
reads index 428, and the driving bin holds 48 questions = 10.084 pct, so **indices 428 to 475 ALL carry its
error and THE p90 OVER QUESTIONS IS EXACTLY THE SINGLE LARGEST PER-BIN ERROR.** **At 47 questions in that
bin the value would have been 0.159437, A FACTOR OF 2.08 LOWER.** **So the margin is decided by one bin's
membership count, and the bootstrap CI [0.074751, 0.422546] is that knife-edge rather than sampling noise
alone.** **The pre-registered procedure returned 0.331566 and that is the margin.**
**AND THE POOLED VALUE HIDES AN 11.1x STRATIFICATION, reported beside it and not inside it: warm p90
0.036118 (n 271) against cold p90 0.400432 (n 205).**
**The driving bin is 24 rows from one arm and 23 from the other, so it is not one arm's artefact.**
**Bootstrap: the unit check found the 476 rows are 298 DISTINCT trace questions with 178 appearing twice,
so the pre-registration's clustering clause took effect and the unit is `(seed, opportunity_id)`; 10,000
resamples with the bins RE-DERIVED inside each, because the binning is part of the estimator.**

## (2) METHOD B = 0.349995, REPORTING ONLY. IT NEVER BECAME THE MARGIN.

**A and B agree within 5.6 pct of each other while the committed statistic is 1.99x both.** That agreement
is worth more than either value: two different error definitions land together and the old one lands twice
as high, which is the units-and-semantics argument showing up as a number.

## (3) REACHABILITY UNDER A: TOUCH IS REACHABLE

| quantity | OLD bar 0.65824 | **METHOD A bar 0.331566** |
|---|---|---|
| **TOUCH COULD clear the bar** | **0 of 61,678** | *** 1,177 of 61,678 (1.91 pct) *** |
| **TOUCH chosen / emitted** | **0 / 0** | *** 1,175 / 1,175 *** |
| KEEP | 61,610 | 60,429 |
| HOLD_BACK chosen / enacted | 68 / 68 | 74 / 74 |
| `state_deviations` | 68 | **1,249** |
| **`state_action` rows in the log** | **0** | **1,175** |
| Z max | 0.555588 | **0.555588, unchanged to nine decimals** |
| `d249_pwc_queue_capped` | 5,740 | 5,852 (9.49 pct) |

**1,177 clear it, 1,175 choose TOUCH and 2 are won by HOLD_BACK.** **The D256 cap STILL changes no
decision: capped and uncapped give the same 12,555 rows and the same digest, 0 positional and 0 setwise,
while raising Z's median 16.4 pct and not its p90, p99 or max.**
**ENACTED touches are NOT instrumented in the dry harness: recorded as an ABSENT KEY, never as a zero. The
evidence the choice reaches the log is the 1,175 `state_action` rows against 0 under the old bar.**

## *** (4) THE FINDING THAT CHANGES THE GATE: THE MARGIN IS A GLOBAL CONSTANT, NOT A SWITCH ***

**`diff -rq` shows exactly two changed files, so every difference below IS the margin:** `v5/cf_margin.py`
(the value) and `cf_protect_defer.py` (an assert-only guard re-pin).
*** AND `MARGIN_CF` IS DECLARED IN `cf_margin.py` "AND NOWHERE ELSE IN `cf_*`", WITH 18 FILES READING
`resolve_margin` OR `MARGIN_CF_ON_TIME`. SO RUNG 3 - THE FREEZE CANDIDATE AND THE GATE'S OWN COMPARATOR -
READS THE SAME CONSTANT. ***
| rung 3, seed 4, 1x | OLD bar | **METHOD A bar** |
|---|---|---|
| rows / wide digest | 14,539 / `5a03c2807da3681a` | **20,870 / `b12fe27632ac56ca`** |
| **TOUCH chosen** | **2,954** | *** 9,296, a 3.15x rise *** |
| `state_deviations` | 2,960 | *** 9,320, PLUS 6,360 *** |

**So the posted-cell OFF identity CANNOT hold under this margin, and its failure is CORRECT rather than
diagnostic.** Dev build 2's version of that proof, with the margin held at 0.65824, still holds untouched.

*** THE SCOPE QUESTION, WHICH NO RULING ANSWERS AND WHICH IS THE USER'S. *** **D259's wording is
ARM-SCOPED: "the Method A value becomes `MARGIN_CF_ON_TIME` for `covex-v6-fair-final-q`".** **THE CODE HAS
ONE GLOBAL CONSTANT. So delivering the ruling AS WRITTEN REQUIRES MAKING THE MARGIN PER-ARM, which is a
code change the ruling does not authorise.** Two readings, and they are not the same experiment:
- **(a) ARM-SCOPED, as the wording says:** needs a per-arm margin resolution plus a proof that rung 3 is
  byte-identical. A small change, but a change to a shared constant's resolution path.
- **(b) GLOBAL, as the code is today:** *** CHANGES THE FREEZE CANDIDATE by 6,360 deviations and triples
  its touches, makes every committed rung-3 cell non-comparable, and reopens D234 (4). *** That is a far
  larger decision than D259 appears to contemplate.
**The gate cell is pre-registered and ready but its COMPARATOR depends on this answer: under either reading
the comparator must be a SAME-CODE rung-3 cell run on the Method A tree, never the committed rung-3 cell.**

## (4b) LIGHT PROOFS ON THE METHOD A TREE

| proof | result |
|---|---|
| OFF identity vs the POSTED rung-3 cell | **FAILS, and correctly: 20,870 rows, positional 18,444, setwise 6,381.** The scope finding, not a plumbing break |
| **Step 2b, ON vs rung 3, both on the A tree** | positional 18,936, **setwise 9,287** |
| **Step 2b FOR THE MARGIN ITSELF, ON old bar vs ON under A** | positional 10,623, **setwise 1,181. The switch reached a decision** |
| positive control, `llf` A tree vs BEFORE | **IDENTICAL: 14,075 / `961be8fe4942d86b`, 0 / 0** |
| positive control NOT vacuous, `llf` vs rung 3 on the A tree | differs at **ROW 0** |
| instrument control, ON plain vs ON under the probe | **IDENTICAL, 0 / 0** |
| the 247.5x unit guard | **4 of 4 `CC.predict(` sites still carry literal `0, 0`** |
| unit suite | **18 of 20 PASS; the 2 failures are EXACTLY the two tests pinned to the old value**, which fail by construction under any recalibration |

## STEP 5, STATED PLAINLY BECAUSE IT LIMITS THE WHOLE RESULT

*** THIS CELL CANNOT DISTINGUISH THE CALIBRATION ARGUMENT FROM A BARE LOOSENING OF THE BAR. The planner
reads ONE SCALAR, so ANY smaller number would do the same thing, and the two are separated ONLY by the
audit trail. *** **The forbidden shortcut was excluded: the observed Z distribution was never read to set
anything, and 0.331566 landing between its p99 0.380086 and its max 0.555588 is an observation after the
fact, not a selection.** **Rule 2 does not apply: this is not a null. TOUCH fired 1,175 times and both
negative controls changed the result.**

## OWED BEFORE ANY OF THIS IS CITED OR COMMITTED

1. **An INDEX row for the margin artefacts** (the E-id `StudyD249-QPLANNER` is now open; the INDEX row is
   not).
2. *** ABOUT TWELVE SITES PINNED TO 0.6582 MUST BE RE-PINNED IN THE SAME CHANGE OR THE SUITE FAILS BY
   DESIGN: *** `cf_pd_tests.py:85-86`, `tests/test_cf_objective_d191.py:144-145`,
   `tests/test_cf_objective_d177.py:145-149` and `:210`, `d249_queue_unit_proofs.py:216-217`, plus
   narrative strings at `v5/cf_planner.py:101,409`, `arms_v6cf_device.py:21`, `arms.py:774`,
   `d190_rung4_r3_proofs.py:168`, and `cf_margin.py`'s own docstring, `MARGIN_CF_RULE` and
   `UNIT_CONVERSION_GAP`, **which already contradict its own lines 49-69.**
3. **`research/FORMULATION.md`'s decision-rule block states the margin as 0.6582 under D255 and needs the
   D259 value beside it.**
4. *** THE SCOPE QUESTION OF (4) IS THE USER'S AND IS UNANSWERED. ***

---
---

# THE AGENT'S FULL RECORD FOLLOWS, UNEDITED

# D259 RECORD: METHOD A COMPUTED AND MADE THE MARGIN; TOUCH IS REACHABLE; THE MARGIN ALSO MOVES RUNG 3

BUILT IN SCRATCH. NOTHING APPLIED TO THE REPOSITORY, NOTHING COMMITTED, NOTHING PUSHED.
Disk at start 24 GB free, 23 GB at the end (floor 15 GB). Read-only git through the literal sha
`3d06eac5c1d2fe48d7fd05f66e4d41702830dce2` (today's `origin/main`). Dev build 2's trees were
REUSED, not rebuilt: `tree_a` is a copy of `d249/after_cap` plus two files, `tree_a_uncap` a copy
of `d249/after` plus the same two.

## PRE-REGISTRATION ORDER, which is the whole point
1. `out/PREREG_D259_BINNING.md` written and sha256'd (`1f2ae1ee9954a56a...`) BEFORE any per-bin
   error, any p90 or any bootstrap was computed.
2. Row extraction run, positive control reproduced.
3. Methods A and B computed. Method A's value became `MARGIN_CF_ON_TIME` with no further choice.
4. Reachability re-run under A. Light proofs run. Gate pre-registration written.

## (1) METHOD A = 0.331566 (on-time units). THE MARGIN, WHATEVER IT IS.
`MARGIN_CF_ON_TIME = 0.331566`, hence `MARGIN_CF = 0.0828915` for continuity with the committed
symbol, hence `cf_objective.attainment_margin` returns 0.331566 exactly (division by 0.25 is exact).

### POSITIVE CONTROL: the committed statistic reproduced EXACTLY before anything new was computed
n_overall 476, n_warm 271, n_cold 205, error_p90_overall 0.164560, warm 0.150341, cold 0.173231,
error_p50_overall 0.011560, on_time_rate 0.5987, p_hat_mean 0.6509, all 8 trace fairness digests OK,
0 cells skipped, 0 questions skipped for missing input. Every figure matches
`cf_margin.py:49-69`'s committed block. So the extraction is the committed extraction.

### METHOD A BIN TABLE (pooled, equal-count deciles, min 40 satisfied without any merge)
| bin | P_hat lo | P_hat hi | n | n_warm | n_cold | mean P_hat | freq on time | n on time | error |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 0.000000 | 0.003625 | 47 | 33 | 14 | 0.000655 | 0.000000 | 0 | 0.000655 |
| 1 | 0.004951 | 0.071674 | 48 | 25 | 23 | 0.027786 | 0.083333 | 4 | 0.055548 |
| 2 | 0.081747 | 0.461985 | 47 | 23 | 24 | 0.258211 | 0.212766 | 10 | 0.045445 |
| 3 | 0.462062 | 0.732844 | 48 | 13 | 35 | 0.623233 | 0.291667 | 14 | **0.331566** |
| 4 | 0.733415 | 0.833488 | 48 | 19 | 29 | 0.784437 | 0.625000 | 30 | 0.159437 |
| 5 | 0.836780 | 0.912388 | 47 | 12 | 35 | 0.873203 | 0.872340 | 41 | 0.000862 |
| 6 | 0.914259 | 0.965010 | 48 | 17 | 31 | 0.941524 | 0.958333 | 46 | 0.016809 |
| 7 | 0.969010 | 0.999019 | 47 | 33 | 14 | 0.991049 | 0.978723 | 46 | 0.012326 |
| 8 | 0.999028 | 0.999552 | 48 | 48 | 0 | 0.999277 | 0.958333 | 46 | 0.040944 |
| 9 | 0.999557 | 1.000000 | 48 | 48 | 0 | 0.999863 | 1.000000 | 48 | 0.000137 |

p50 over questions 0.040944; per-bin errors range 0.000137 to 0.331566.

### WARM AND COLD SEPARATELY (reported, not the margin). The min-40 rule MERGED each to 5 bins.
warm p90 **0.036118** (n 271, deciles of 27 are below 40 so they merge to 5 bins of 54/55);
cold p90 **0.400432** (n 205, 5 bins of 41).
| warm bin | lo | hi | n | mean P_hat | freq | error |  | cold bin | lo | hi | n | mean P_hat | freq | error |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 0.000000 | 0.037079 | 54 | 0.007935 | 0.037037 | 0.029102 |  | 0 | 0.000000 | 0.115474 | 41 | 0.027603 | 0.000000 | 0.027603 |
| 1 | 0.037434 | 0.803118 | 54 | 0.470930 | 0.462963 | 0.007967 |  | 1 | 0.120748 | 0.658238 | 41 | 0.424823 | 0.024390 | **0.400432** |
| 2 | 0.808810 | 0.997570 | 54 | 0.933022 | 0.907407 | 0.025615 |  | 2 | 0.663839 | 0.829571 | 41 | 0.753384 | 0.585366 | 0.168018 |
| 3 | 0.997892 | 0.999489 | 54 | 0.999081 | 0.962963 | 0.036118 |  | 3 | 0.829837 | 0.922780 | 41 | 0.874932 | 0.878049 | 0.003116 |
| 4 | 0.999491 | 1.000000 | 55 | 0.999819 | 1.000000 | 0.000181 |  | 4 | 0.924717 | 0.998344 | 41 | 0.959696 | 1.000000 | 0.040304 |

### BOOTSTRAP CI FOR A
Resampling unit: the QUESTION CLUSTER `(seed, opportunity_id)`. The uniqueness check found the
population holds **298 distinct trace questions**, 178 of them appearing TWICE (once in each arm of
that seed's pair) and 120 once, so the pre-registration's clause took effect and the cluster is the
unit. 10,000 resamples, seed 20261125, bins RE-DERIVED inside each resample because the binning is
part of the estimator.
**PRIMARY, clustered: 95 pct CI [0.074751, 0.422546], median 0.216089, mean 0.225209, min 0.025704,
max 0.569238.**
Reported beside it, the row-level bootstrap that ignores the clustering (10,000 resamples):
bins re-derived [0.097758, 0.435614], median 0.281590; bins held fixed [0.081243, 0.432454],
median 0.258648.

### THE ESTIMATOR IS KNIFE-EDGE ON ONE BIN, STATED BECAUSE IT IS NOT VISIBLE IN THE NUMBER
n = 476, so the committed nearest-rank p90 reads index `int(round(0.9 x 475))` = 428. Bin 3 holds 48
questions = 10.084 pct, so indices 428 to 475 all carry bin 3's error and **the p90 over questions
is EXACTLY the single LARGEST per-bin error**. Had bin 3 held 47 questions (9.87 pct) the p90 would
have been **0.159437**, bin 4's error, a factor of 2.08 lower. The clustered CI's width
(0.0748 to 0.4226) is this instability, not sampling noise alone. **This is reported, not acted on:
the pre-registered procedure produced 0.331566 and that is the margin.**

### HAND-CHECKABLE TRACE OF ONE UNIT (bin 3, the bin that sets the margin)
48 questions; sum of P_hat 29.91518416109821 / 48 = 0.6232330033562127; on time 14 / 48 =
0.2916666666666667; error |0.6232330033562127 - 0.2916666666666667| = 0.331566336689546.
One question in it: cell `hybrid-F-lhreq-noc3_n16_s4_1200s_h27_3t_L3_epg_rq30`, opp `opp0001483`,
P_hat 0.483905813878413, on_time false, warm false. It carries bin 3's error 0.331566, and its
own committed-statistic error was 0.250 x |0.4839 - 0| = 0.120976.
Mixing weight of the driving stratum: bin 3 is 9.87 to 10.08 pct of the population, 35 of its 48
rows cold, 24 from `v5-rules-2` and 23 from `hybrid-F-lhreq-noc3`, so it is not one arm's artefact.

## (2) METHOD B = 0.349995 (on-time units). REPORTING ONLY. IT IS NOT THE MARGIN.
Same pooled deciles; bins 7, 8 and 9 held zero cold rows, so the pre-registered merge collapsed
them into one bin of 143 and 8 bins remain.
| bin | lo | hi | n | n_warm | n_cold | mean P_hat warm | mean P_hat cold | freq warm | freq cold | d P_hat | d freq | error |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 0.000000 | 0.003625 | 47 | 33 | 14 | 0.000636 | 0.000700 | 0.000000 | 0.000000 | -0.000064 | 0.000000 | 0.000064 |
| 1 | 0.004951 | 0.071674 | 48 | 25 | 23 | 0.023361 | 0.032595 | 0.160000 | 0.000000 | -0.009233 | 0.160000 | 0.169233 |
| 2 | 0.081747 | 0.461985 | 47 | 23 | 24 | 0.280217 | 0.237121 | 0.434783 | 0.000000 | 0.043095 | 0.434783 | 0.391687 |
| 3 | 0.462062 | 0.732844 | 48 | 13 | 35 | 0.614823 | 0.626357 | 0.538462 | 0.200000 | -0.011534 | 0.338462 | **0.349995** |
| 4 | 0.733415 | 0.833488 | 48 | 19 | 29 | 0.785491 | 0.783746 | 0.526316 | 0.689655 | 0.001746 | -0.163339 | 0.165085 |
| 5 | 0.836780 | 0.912388 | 47 | 12 | 35 | 0.876155 | 0.872190 | 0.916667 | 0.857143 | 0.003965 | 0.059524 | 0.055559 |
| 6 | 0.914259 | 0.965010 | 48 | 17 | 31 | 0.938522 | 0.943171 | 0.882353 | 1.000000 | -0.004649 | -0.117647 | 0.112998 |
| 7 | 0.969010 | 1.000000 | 143 | 129 | 14 | 0.998035 | 0.985105 | 0.976744 | 1.000000 | 0.012931 | -0.023256 | 0.036187 |

The two methods agree within 5.6 pct of each other (0.331566 against 0.349995) while the committed
statistic is 1.99x both. Method B's value also lands on bin 3.

## (3) REACHABILITY UNDER A: TOUCH IS REACHABLE
Same posted cell throughout (seed 4, n16, 1200 s, 40:40:20, lh_req, ss2, epg, per-frame, rq30, 1x,
`--cutoff-off`), same probe as dev build 2 (`d249/drv/reach_probe.py`), ONE CELL PER PROCESS.

| quantity | OLD bar 0.65824 (dev build 2, capped) | **METHOD A bar 0.331566 (capped)** | METHOD A (uncapped) |
|---|---|---|---|
| state decisions | 61,678 | **61,678** | 61,678 |
| TOUCH scored at every decision (`no_touch_value`) | 0 | **0** | 0 |
| **decisions where TOUCH COULD clear the bar** | **0 of 61,678** | **1,177 of 61,678 (1.91 pct)** | 1,177 |
| **TOUCH chosen / emitted** | **0 / 0** | **1,175 / 1,175** | 1,175 / 1,175 |
| KEEP | 61,610 | **60,429** | 60,429 |
| HOLD_BACK chosen / enacted | 68 / 68 | **74 / 74** | 74 / 74 |
| WARM chosen | 0 | **0** | 0 |
| RELOAD chosen | 0 (UNEXERCISED: offered only at host-warm) | **0 (UNEXERCISED)** | 0 |
| SLICE chosen | 0 | **0** | 0 |
| `state_deviations` | 68 | **1,249** | 1,249 |
| `state_action` ROWS IN THE DECISION LOG | **0** | **1,175** | 1,175 |
| Z p10 / p50 / p90 / p99 / **max** | 0.000146 / 0.006822 / 0.16754 / 0.38009 / **0.555588** | 0.000113 / 0.005316 / 0.147939 / 0.380086 / **0.555588** | 0.000068 / 0.004567 / 0.147939 / 0.380086 / **0.555588** |
| max `p_warm - p_cold` | 0.593995773 | **0.593995773** | 0.593995773 |
| `d249_pwc_queue_capped` | 5,740 (9.31 pct) | **5,852 (9.49 pct)** | 0 |
| `d249_pwc_queue_max_milli` | 2,781 | **2,781** | **15,862** |
| `d249_pwc_queue_milli_sum` | 31,988,427 | **32,162,727** | 44,013,331 |

- **Z max is 0.555588 under both bars, to nine decimals**, so the Method A bar at 0.331566 sits
  **59.7 pct of the way to the best decision in the cell** where the old bar sat above it. 1,177
  decisions clear it; 1,175 of those choose TOUCH and 2 are won by HOLD_BACK
  (`gain_TOUCH_over_margin` 1,177 against `state_chosen_TOUCH` 1,175).
- **The cap still changes no decision under A**: capped and uncapped give the SAME 12,555 rows and
  the SAME wide digest `41724e38cfaa2eb4`, 0 positional and 0 setwise. It raises Z in the middle
  (p50 0.004567 to 0.005316, +16.4 pct) and not at p90, p99 or the max.
- **A COUNTER THAT IS NOT INSTRUMENTED, read as ABSENT and NOT as zero:** `test_hybrid.dry` has no
  `submitted_touch` / `completed_touch` key, so ENACTED touches are not countable in the dry
  harness. The evidence that the choice reaches the log is the 1,175 `state_action` rows, against
  0 under the old bar and 2,954 in rung 3. Enacted counts come from the live gate cell.

## (4) LIGHT PROOFS ON THE METHOD A TREE
`diff -rq` against `d249/after_cap` reports exactly TWO files: `v5/cf_margin.py` (the value) and
`cf_protect_defer.py` (its import-time value guard RE-PINNED from 0.6582 to 0.331566, an assert-only
change that cannot alter behaviour). So every difference below is the margin.

| proof | result |
|---|---|
| **1. OFF-switch identity against the posted rung-3 cell (14,539 rows, `5a03c2807da3681a`)** | **FAILS: 20,870 rows, `b12fe27632ac56ca`, positional 18,444, setwise 6,381. SEE BELOW: this is a SCOPE FINDING, not a plumbing break.** |
| 1b. rung 3 under the OLD bar vs under A, same tree lineage | positional 18,444, setwise 6,381; first differing row index 2,426, OFF-bar `release_monitor` t 260.7 against A-bar `state_action` t 260.5 |
| **2. Step 2b, ON arm vs rung 3, both on the A tree** | positional 18,936, **setwise 9,287**; first differing row index 1,932, rung 3 `release_infeasible` t 207.0 against ON `state_action` t 206.9 |
| **2b. Step 2b for the MARGIN ITSELF, ON arm old bar vs ON arm under A** | positional 10,623, **setwise 1,181**; first differing row index 1,932, old-bar `release_infeasible` t 207.0 against A-bar `state_action` t 206.9. **The switch reached a decision.** |
| 4. positive control, `llf` on the A tree vs the BEFORE tree | **IDENTICAL: 14,075 rows, `961be8fe4942d86b`, 0 positional, 0 setwise.** The margin is unreachable from an arm that does not read it. |
| 4b. positive control NOT VACUOUS, `llf` vs rung 3 on the A tree | differs at **ROW INDEX 0**, positional 20,867, setwise 18,713 |
| 5. instrument control, ON plain vs ON under the reach probe, both on the A tree | **IDENTICAL: 12,555 rows, `41724e38cfaa2eb4`, 0 positional, 0 setwise.** The probe does not perturb what it measures. |
| static scan, the 247.5x unit guard | **4 of 4 `CC.predict(` sites still carry literal `0, 0`**; the queue is still added in SECONDS (`arms_v6state.py:415`, cap at `:424-425`, used at `:436,:438`) |
| unit suite | **18 of 20 PASS. The 2 failures are EXACTLY the two tests pinned to the OLD value**: "MARGIN_CF is 0.16456 in correctness units" and "the planner's bar is already MARGIN_CF_ON_TIME = 0.65824". They fail BY CONSTRUCTION under a recalibration and must be re-pinned in the same change. No other test fails. |

## *** THE FINDING THAT CHANGES THE GATE: THE MARGIN IS NOT BEHIND THE D249 SWITCH ***
`covex-v6-fair-final` (rung 3, the freeze candidate and the gate's own comparator) READS THE SAME
MARGIN, so the recalibration moves it too:

| rung 3 (`covex-v6-fair-final`), seed 4, 1x | OLD bar 0.65824 | **METHOD A bar 0.331566** |
|---|---|---|
| decision rows / wide digest | 14,539 / `5a03c2807da3681a` | **20,870 / `b12fe27632ac56ca`** |
| `state_decisions` | 60,920 | 60,934 |
| `state_chosen_KEEP` | 57,960 | **51,614** |
| **`state_chosen_TOUCH` / emitted** | **2,954 / 2,954** | **9,296 / 9,296 (3.15x)** |
| `state_chosen_HOLD_BACK` / enacted | ABSENT / ABSENT (counter never created) | 1 / 1 |
| `state_chosen_WARM` | 6 | 23 |
| `state_deviations` | 2,960 | **9,320** |
| `submitted_piece` | 163 | 162 |

**So the posted-cell OFF identity cannot hold under this margin, and its failure is correct rather
than diagnostic.** Dev build 2's version of that proof (the D249 CODE change with the margin held
at 0.65824) still holds untouched at 14,539 / `5a03c2807da3681a`; nothing here disturbs it.
**THE CONSEQUENCE FOR D259's PASS RULE: the comparator must be a SAME-CODE rung-3 cell run on the
Method A tree, never the committed rung-3 cell, because the recalibration changes the comparator by
6,360 deviations.** Whether the recalibrated margin SHOULD apply to rung 3 as well as to
`covex-v6-fair-final-q` is a question no ruling answers; it is the user's, and no answer was
assumed here. Both readings are live and they are not the same experiment.

## RESULTS CONSISTENCY CHECK
**1. Cross-check against committed measurements.**
| quantity | this run | prior run | source of prior | ratio | agree |
|---|---|---|---|---|---|
| D169 population n / warm / cold | 476 / 271 / 205 | 476 / 271 / 205 | `margin_cf_d169.json` via `cf_margin.py:49-69`, D169 | 1.00 | AGREE |
| committed p90 (accuracy units) | 0.164560 | 0.16456 | `cf_margin.py:72`, commit `96655fd0` | 1.00 | AGREE |
| committed p90 warm / cold | 0.150341 / 0.173231 | 0.150341 / 0.173231 | same | 1.00 | AGREE |
| committed p50 | 0.011560 | 0.01156 | same | 1.00 | AGREE |
| `A_D2_DEV` | 0.250 | 0.250 = 7 of 28, Wilson [0.1268, 0.4336] | `cf_objective.py:502`, `cf_protect_defer.py:258` | 1.00 | AGREE |
| old bar in on-time units | 0.65824 | 0.6582 | D255, FORMULATION.md decision rule | 1.00 | AGREE |
| state decisions, ON arm | 61,678 | 61,678 | `cell_r3q2_after` / build 2 capped | 1.00 | AGREE |
| `d249_queued_ahead_reads` | 61,678 | 61,678 (NOT build 1's 122,506) | build 2, trap 1 | 1.00 | AGREE, trap avoided |
| Z max | 0.555588 | 0.555588 | build 2 (c) | 1.00 | AGREE |
| max `p_warm - p_cold` | 0.593995773 | 0.593995773 | build 2 (c) | 1.00 | AGREE |
| `llf` rows / digest | 14,075 / `961be8fe4942d86b` | same | build 2 (d) | 1.00 | AGREE |
| rung-3 rows / digest under the OLD bar | 14,539 / `5a03c2807da3681a` | same | build 2 (d) | 1.00 | AGREE |
| uncapped `d249_pwc_queue_max_milli` | 15,862 | 15,705 | build 2 (a) | 1.010 | AGREE (trajectory moved; TOUCH now fires) |
No disagreement exceeds 2x. The only ratio away from 1.00 is 1.010 and it is explained.

**2. Physical plausibility.** No new latency or throughput is measured. The only rates in play are
the committed ones, re-read at the point of use: `per_queue_token` 0.0001535807289338535 s per
TOKEN, `per_overlap` 0.038004811772727576 s per REQUEST (247.5x apart, different units), the cap
bound 2.781 SECONDS of first token, `d249_pwc_queue_max_milli` in MILLISECONDS, which is why 2,781
and 2.781 are one quantity. Queue priced 32,162.727 s over 60,723 priced decisions = 0.5297 s each,
inside the 2.781 s bound, with 9.49 pct capped at it. Nothing is faster than a committed curve.

**3. Distribution sanity.** No constant appears where a distribution is expected: the 10 per-bin
errors span 0.000137 to 0.331566; Z spans -0.1511 to 0.555588 across nine percentiles; the
bootstrap spans 0.0257 to 0.5692. **The artefact-spread test was applied to the per-bin error and
it passes**: each value is a difference of two quantities (a mean of frozen-model predictions and a
realised frequency) whose per-bin inputs are printed in the table, so the column can mean what it
says. **The averaged-out-effect test found a real stratification and it is reported beside the
mean, not hidden in it:** warm 0.036118 against cold 0.400432, an 11.1x difference, with mixing
weights 271 and 205; the pooled margin is set by a 48-question bin that is 73 pct cold. Quoting
0.331566 as a property of the population without the warm and cold figures would be the mistake the
check exists to catch.

**4. Definition audit.** `MARGIN_CF_ON_TIME` = on-time units = a count of on-time cloud answers =
`MARGIN_CF / A_D2_DEV` (`cf_objective.attainment_margin`); D259 fixes the computation in these
units and NO division by `A_D2_DEV` was applied anywhere in Method A or B. `MARGIN_CF` stays the
accuracy-units symbol, 0.0828915 here. p90 = NEAREST-RANK, the committed
`s[min(int(round(0.9*(n-1))), n-1)]`, index 428 of 476, unchanged. A "question" = one robot
opportunity RELEASED in a healthy-regime window of one cell, which is 476 rows over **298 distinct
trace questions**; the committed statistic treated the 476 as independent and this run keeps that
for the point estimate and corrects for it in the CI. "Healthy window" = D162's rule, observed
first-token p50 of the question's own 100 s submit window <= 2.781 s, unchanged. No name is used
with two definitions, with one exception RECORDED: the committed `error` field is in accuracy units
while D259's per-bin `error` is in on-time units, a factor of exactly 4, and the two are never
mixed in one table here.

**5. Claim linkage.** `research/FORMULATION.md` decision rule: "Deviate from KEEP only if
`value - harm > margin`", with D255 fixing the margin as `MARGIN_CF_ON_TIME` and the RECALIBRATION
clause requiring the method be reported BEFORE it is applied, which dev build 2 did and this run
honoured. The reachability result bears on **C5** (joint representation x placement x timing beats
decomposed policies): under the old bar the TOUCH channel of the joint policy was UNEXERCISED, so
no C5 comparison could read it; under A it fires 1,175 times, which makes the channel testable and
is not yet evidence either way. The margin itself SPEAKS TO NO CLAIM: it is an instrument
calibration, and saying so is the point of this check. Nothing measured here is scoped out by
FORMULATION.md section Scoping: no KV transfer and no cross-architecture claim is made, and KV
capacity is not enforced in this harness, so NO kv0.5r claim is made from any of it.

**6. Proxy validity.** Two proxies, both declared. (i) `freq(on time | bin)` proxies the true
conditional on-time probability for the bin; valid for a calibration error, with n 47 or 48 per bin
so one flipped question moves a bin's frequency by 0.021 and the minimum defensible resolution of
any per-bin error is about that. (ii) `on_time` = `t_delivered <= deadline_abs_s + 1e-9` with the
deadline reconstructed as `t_opportunity + deadline_s` where absent; this is the committed
definition, unchanged. (iii) The question cluster `(seed, opportunity_id)` proxies question
identity; the same trace is generated per seed and both arms of a seed release the same
opportunity ids, which is why 178 clusters hold exactly 2 rows. Used for the CI only, never for the
point estimate.

**7. Validate the control, not only the result.** The POSITIVE CONTROL was run FIRST and reproduced
the committed statistic to every published decimal (0.164560 / 0.150341 / 0.173231 / 0.011560 at
476 / 271 / 205) before any new number was computed, so a surprising Method A value could not be
the extraction breaking. On the arm side: `llf` is IDENTICAL across trees (0 of 14,075) AND differs
from rung 3 at ROW INDEX 0, so the identity instrument is neither broken nor vacuous; the
reachability probe is byte-transparent; and **the control arm's own numbers were checked and found
CHANGED, which is the finding of section (4)** - rung 3 moved 14,539 to 20,870 rows under the new
margin. An arm-versus-arm check could not have seen that, because both arms moved.

## MECHANISM VERIFICATION
**Step 0, what would invalidate this run, asked before it started.** Is the comparator about to
change? YES, and that is exactly what section (4) found: rung 3 reads the margin, so the posted
cell is not a fixed bar under a recalibration. Is a default about to be restored? No. Does a run I
depend on key into my analysis? Yes, and the build-1 `cell_r3q_after` doubling trap was avoided by
reading only `cell_r3q_cap_plain` / `cell_r3q2_after` lineage, confirmed by
`d249_queued_ahead_reads` 61,678 and not 122,506. Does the mechanism have a reachable path at this
size? That is the question (3) answers, and it was asked before the margin was wired in.

**Step 1, the causal chain.** If the deviation bar (FORMULATION.md decision rule, D255) is a p90
absolute error measured against a SINGLE Bernoulli realisation, it carries irreducible outcome
variance that the compared quantity `p_question x (p_warm - p_cold)` does not contain, so the bar
is larger than the uncertainty of the thing it gates; measuring the SAME frozen model's error
against the FREQUENCY its own prediction implies (the calibration error) removes that variance
term while changing neither the population, the model, the filter nor the quantile, so the
recalibrated bar is smaller; a smaller bar is cleared by more decisions; and a decision that clears
the bar chooses TOUCH, which the planner emits.

**Step 2, each link instantiated.**
| causal link | implementing quantity | value / range in this run | varies as expected? | evidence |
|---|---|---|---|---|
| the bar is a p90 over the D169 population | `margin_cf_d169.py` rows, re-extracted | 476 rows, P_hat 0.000000 to 1.000000 | YES | positive control reproduces 0.164560 exactly |
| removing the Bernoulli term shrinks the bar | per-bin calibration error | 0.000137 to 0.331566, p90 0.331566 | YES, 1.99x below 0.65824 | the bin table above |
| the bar reaches the planner | `cf_margin.MARGIN_CF` -> `cf_objective.attainment_margin` -> `cf_planner._margin` -> `margin_effective` | 0.0828915 -> 0.331566 -> `w_d x 0.331566`, `w_d` 1.0 to 3.0 | YES | the READ is `cf_planner.plan_state`'s `best.value > margin_effective`; the probe recovers `w_d = margin_effective / 0.331566` per decision and `margin_effective > 0` at 61,678 of 61,678 |
| a smaller bar is cleared by more decisions | `touch_could_clear_bar` | 0 -> 1,177 | YES | 0 of 61,678 at 0.65824, 1,177 of 61,678 at 0.331566 |
| a clearing decision chooses and emits TOUCH | `state_chosen_TOUCH`, `state_touch_emitted`, `state_action` rows | 0/0/0 -> 1,175/1,175/1,175 | YES | the decision log itself; the row is in the log, not only the counter |
No link is ABSENT, zero or constant. Each has a named READ, not merely a write.

**Step 2b, the switch reaches a decision.** Proof 2b: the ON arm under the old bar and under A
differ in **1,181 setwise decisions**, first difference at row index 1,932 where `release_infeasible`
at t 207.0 becomes `state_action` at t 206.9. The logs are NOT identical, so this is a result and
not an ABSENT LINK. The switch arrived with its declared type and value: `MARGIN_CF` is a float
0.0828915 and `attainment_margin` returns float 0.331566, asserted at import by the re-pinned
guard, which would have raised had either moved.

**Step 3, one traced unit.** Given above for the margin's unit (bin 3, arithmetic checkable by
hand) and for the decision-side unit (the first differing decision at t 206.9 s, with the Z
distribution, the bar, `w_d` and the per-candidate margin recovered per decision). All input
quantities, the bound that bound each decision (the queue cap bound 2.781 s binding 5,852 of 60,723
priced decisions) and the chosen outcome are instrumented.

**Step 4, negative control.** TWO were run, and both changed the result, so the mechanism is not
inert. (i) **Disable the margin change:** rung 3 and the ON arm on the OLD bar reproduce dev build
2 exactly (14,539 / `5a03c2807da3681a` and 11,386 / `b7bb6e018b6e1d27`) with TOUCH chosen 0 on the
ON arm. (ii) **Remove the arm's dependence on the margin:** `llf`, which never reads it, is
byte-identical across the two trees (0 of 14,075 differing). So the result is driven by the margin
and by nothing else in the tree. The CELL is seed 4, n16, 1200 s, 1x, rq30.

**Step 5, the alternative explanation.** The headline "TOUCH becomes reachable" could be produced
by (a) the recalibration removing outcome variance from the bar [the claimed mechanism], or by
(b) ANY smaller number in that position, the margin having simply been lowered by about half, with
the calibration argument doing no work. **NOTHING IN THE REACHABILITY DATA DISTINGUISHES THESE, and
it cannot**: the planner reads one scalar. What distinguishes them is entirely upstream and is the
reason the pre-registration exists: the number was fixed by a procedure declared before the errors
were computed, on a frozen model and a pre-committed population, and it reads no arm output. The
forbidden shortcut is named and excluded - the observed Z distribution (p90 0.147939, p99 0.380086,
max 0.555588) was NOT read to set anything, and the fact that 0.331566 falls between that p99 and
that max is an OBSERVATION AFTER THE FACT, not a selection. A reader who wants (a) distinguished
from (b) empirically will not get it from this cell; they get it from the audit trail.
**RULE 2 does not apply: this is not a null.** TOUCH fired 1,175 times and the negative controls
changed the result, so the deviation channel is EXERCISED where dev build 2 found it UNEXERCISED.

## ARTEFACTS, all in scratch
`out/PREREG_D259_BINNING.md` (sha256 `1f2ae1ee9954a56a`), `out/PREREG_D259_GATE_CELL.md`
(`84b34f170f347aa5`), `out/d259_rows.json` (the 476 per-question rows, which the committed record
never held), `out/d259_methods_ab.json`, `out/d259_boot_cluster.json`, `out/reach_a_cap.json`,
`out/reach_a_uncap.json`, `out/cell_r3_a.json.gz`, `out/cell_llf_a.json.gz`,
`out/cell_r3q_a_plain.json.gz`, `out/cell_r3q_a_cap_probe.json.gz`,
`out/cell_r3q_a_uncap_probe.json.gz`, the six `d259_p*.json` diffs,
`out/d259_unit_proofs.json`, `out/chain_d259.log`; drivers `drv/extract_rows.py`
(`c56911a0446a3c21`), `drv/methods_ab.py` (`a7bceb4a1c8d301c`), `drv/boot_cluster.py`
(`d975ee8a3c80a29`), `drv/chain_d259.sh`.

## OWED BEFORE ANY OF THIS IS CITED OR COMMITTED
1. No E-id exists for D249, D256 or D259 in `research/EXPERIMENTS.md`, and no `results/INDEX.md`
   row exists for the margin artefacts. Drafts are in the handback report; neither file was edited.
2. Every site pinned to the OLD value must be re-pinned in the same change or the suite fails by
   design: `cf_pd_tests.py:85-86`, `tests/test_cf_objective_d191.py:144-145`,
   `tests/test_cf_objective_d177.py:145-149` and `:210`, `d249_queue_unit_proofs.py:216-217`, plus
   the narrative strings in `v5/cf_planner.py:101,409`, `arms_v6cf_device.py:21`, `arms.py:774`,
   `d190_rung4_r3_proofs.py:168`, and `cf_margin.py`'s own docstring / `MARGIN_CF_RULE` /
   `UNIT_CONVERSION_GAP`, which already contradict lines 49-69.
3. `research/FORMULATION.md`'s decision-rule block states the margin as 0.6582 under D255 and would
   need the D259 value beside it.
4. The scope question of section (4) is the user's and is not answered here.
