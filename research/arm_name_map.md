# Arm name map (D172)

Every arm name used in this project, mapped onto the spec v6 ablation ladder.

**Committed cells keep their original names.** Nothing in this file renames a committed file, a
committed digest or a committed row. The map is read in both directions: a reader meeting
`v5-rules-2` in a committed cell finds its rung here, and a reader meeting `covex-v6-rules` in a
new cell finds the committed cells that are the same arm.

Machine-readable source: `experiments/orchestration/live2/arm_names_v6.py`.
Identity proof: `experiments/orchestration/live2/v6_alias_proof.py` ->
`results/orchestration/live2/frozen_test/v6_alias_proof.json`.

---

## The ladder

| rung | v6 name | adds over the rung below | implemented by | committed cells | status |
|---|---|---|---|---|---|
| 0 | `covex-v6-base` | the `hybrid-F-lhreq-noc3` rules | `hybrid-F-lhreq-noc3` | **6** | READY |
| 1 | `covex-v6-rules` | chunked just-in-time warming + saturation guard | `v5-rules-2` | **4** | READY |
| 2 | `covex-v6-state` | per-type host retention (`max_offload_tokens = 0` for alert and single-shot), TOUCH chosen by `plan_state`, residency belief corrected from engine telemetry including host hits, state-based pricing | none yet | 0 | **NOT BUILT** |
| 3 | `covex-v6-fair` | deficit feed + value reader on | none yet | 0 | **SUPERSEDED NAME, DO NOT USE FOR NEW CELLS.** Its description is stale on two counts: D177 (2) REMOVED the value reader, and `arms_v6fair.py:129` classifies by request KIND, which merges ASSISTANCE INTO RECALL (`asst00x` completions arrive as kind `recall` with deadline 2.0). The file is left untouched so the old name keeps its old meaning for provenance |
| 3 | `covex-v6-fair-shares`, `covex-v6-fair-c5attr` (each with `-off` and `-gain0`) | PER-DEVICE deficit feed only; no value reader (D177 (2)); classification by DEVICE PREFIX; cloud on-time answers only; `w_d = 1 + 2.0 x (shortfall_d / target_d)` floored at 1, range [1, 3] (D182, user addendum 12 item 2; the raw unnormalised form is NOT RUN) | none yet | 0 | **BUILT, DEFAULT OFF, NOT YET EVIDENCE.** The base is a parameter, so the same arm runs on either rung-2 outcome; the choice is made by picking the NAME when a cell is posted, with no code edit after the D184 verdict. Consumers: ORDERING by `w_d` descending then deadline (primary), and the flexible-pool split. A rung-3 cell may not be read as evidence about the weighting until the addendum 12 item 5 pass condition is met |
| 4 | `covex-v6` | the counterfactual: request, state and sync decisions, compound candidates, the episode-rule switch | `v5-full` | **0** | runnable, no cells |
| 4 | `covex-v6-cf-pd-shares`, `covex-v6-cf-pd-c5attr` (each with `-off`) | PROTECT-AND-DEFER only (spec v6 section 7, D165 (D)), over a **RUNG-2** base. `w_d` is the CONSTANT 1.0 here by that family's own record, so a cell of it is not evidence about the weighting | `arms_v6cf.py` | 0 | **BUILT, DEFAULT OFF.** At 1x it moves ZERO decisions (measured twice); its posted cells carry `_kv0.25` and the memory setting may not be dropped from the citation |
| 4 | `covex-v6-cf-c5attr` (with `-off`, `-pdonly`, `-rqonly`, `-w1`, `-harm0`, `-margin-huge`, `-gain0`) | **RUNG 4 ON THE RUNG-3 BASE (D190 (3), the ladder is CUMULATIVE).** Rung 3 (`covex-v6-fair-c5attr`) plus BOTH counterfactual decisions: protect-and-defer (`cf_protect_defer`) and QUESTION-DEFERRAL (`cf_request_defer`, D151 (3), scoped in by D191 item 2). The deficit weight is **LIVE** in both `w_j` (inside the harm sum) and `w_R` (on the bar) | `arms_v6cfr3.py` | 0 | **BUILT, DEFAULT OFF, NOT YET EVIDENCE.** Pre-registration: `reports/study_rung4_counterfactual.md`. `-off` must be byte-identical to the COMMITTED RUNG-3 arm (`12e4f73ce0ebd865` / 13,812), **not** to rung 2 |

---

## Old name to rung

| committed name | rung | note |
|---|---|---|
| `hybrid-F-lhreq-noc3` | `covex-v6-base` | the base every higher rung is built on |
| `v5-rules-2` | `covex-v6-rules` | |
| `v5-rules-2-off` | `covex-v6-rules` negative control | warming off; must collapse to the base byte-identically |
| `v5-rules-2-noguard` | `covex-v6-rules` ablation | saturation guard off |
| `v5-rules-2-nojit` | `covex-v6-rules` ablation | chunked just-in-time warming off |
| `v5-full` | `covex-v6` | |
| `v5-full-off` | `covex-v6` negative control | counterfactual off; collapses to `covex-v6-rules` |
| `v5-full-noguarddefer` | `covex-v6` ablation | defer-to-guard off |
| `v5-full-nohealthy` | `covex-v6` ablation | healthy-regime filter off |
| `v5-rules`, `v5-rules-off`, `v5-rules-noyield` | **not a rung** | see below |

### `v5-rules` is not rung 1 under another name

`v5-rules` is the **naive per-frame** warm-ahead design (D150). `v5-rules-2` replaced it with
**chunked just-in-time** warming and the saturation guard (D160), which is a different mechanism
and not a tuning of the same one. Mapping `v5-rules` onto `covex-v6-rules` would make a superseded
design read as the committed one, so it is recorded as superseded and left off the ladder.

---

## Two things this map must not be read as saying

**Rung 4 has no committed cells.** `covex-v6` is identical to `v5-full` by decision digest, and
`v5-full` has run **zero** cells, so there is nothing to reuse and the rung is not covered by
existing runs. "Reused, never rerun" is only worth something where cells exist; over zero cells it
is vacuous.

**`v5-full` had never run at all before 2026-11-21.** `V5FullArm.__call__` dispatched through
`self._rules.__class__`, which resolves against the running object, so a `V5FullArm` borrowing
`V5Rules2Arm.__call__` found its own method again and recursed until the stack ran out. The arm
raised `RecursionError` on its **first observation**, every time. Fixed by naming the delegate
class statically in both `arms_v5rules2.py` and `arms_v5full.py`. Any earlier statement that
`v5-full` was built and ready described a class that existed, not an arm that ran.

---

## Rungs that are not built do not resolve to the rung below

`covex-v6-state` and `covex-v6-fair` are registered to a factory that **raises** and names the
missing components. Aliasing either to the rung below would be the worst failure available here:
every cell would run, every proof would pass, every output would be well formed, and the arm would
not contain the mechanism its name claims. A driver asking for one gets a recorded blocker and
skips the item.

| rung | missing |
|---|---|
| `covex-v6-state` | `plan_state` has no caller outside the proofs; residency belief is not corrected from telemetry (`telemetry_cached_tokens` NULL); no arm class exists |
| `covex-v6-fair` | `DeficitCounters.observe()` has no caller, so every weight is 1.0; the value reader is off; the D165 lexicographic objective is not built; no arm class exists. The rung-3 work now lives under `covex-v6-fair-shares` / `-c5attr`; `cf_objective.DeficitCounters` still carries one 0.90 target per kind with no per-episode reset and `DEFICIT_GAIN = 1.0`, and is NOT the D178 feed |

---

## Rung 4's two families are not the same arm, and the difference is the base

`covex-v6-cf-pd-*` is protect-and-defer over a **rung-2** base. `covex-v6-cf-c5attr` is rung 4 over
the **rung-3** base. Reading one as the other is not a naming nicety:

* on the rung-2 base the deficit weight is identically 1.0, so `w_j` (inside the harm sum) and
  `w_R` (on the bar) are both 1, the ratio that decides is `harm / MARGIN_CF`, and the deficit
  counters cannot move a single deferral. That is Rule 2's `cancelled by geometry` **by
  construction**, and a cell of it is silent about the weighting however it comes out;
* on the rung-3 base both weights are live, and rung 3's ordering consumer is underneath, so the
  pending-work order the harm is computed against is rung 3's and not rung 2's.

`-off` therefore has two different bars. `covex-v6-cf-pd-c5attr-off` collapses to the rung-2 digest
`9a4be873eb3c5fba` / 14,218; `covex-v6-cf-c5attr-off` collapses to the rung-3 digest
`12e4f73ce0ebd865` / 13,812. Checking the wrong one would credit rung 4 with the rung below it.

### The two legs are reported separately, and `-pdonly` exists because of a measured null

`-pdonly` and `-rqonly` are the one-factor arms addendum 12 item 5 requires: "a combined count that
cannot be attributed is not a pass". `-pdonly` is also the exact treatment of D191 step (a).
Protect-and-defer is **UNEXERCISED at 1x** on this base (Rule 2) — every decision stops at
`no_active_alert_episode` or `rebuild_fits_without_evicting` — which is an absent link and not a
negative. The question-deferral leg does fire at 1x. Neither module was re-thresholded to make
either statement true.


## Cell lists

| list | rung | release condition |
|---|---|---|
| `runs/V6STATE_CELLS` | `covex-v6-state` | rung built, Step 2b proofs, spec v6 section 12 rows IMPLEMENTED for the components it uses |
| `runs/V6FAIR_CELLS` | `covex-v6-fair` | as above |
| `runs/V6_CELLS` | `covex-v6` | as above, **and** `MARGIN_CF` applied per D171 |

`V5FULL_CELLS` is superseded by `V6_CELLS` and is still read, so an old name that lands is not
missed.
