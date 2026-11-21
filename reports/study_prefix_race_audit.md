# Audit: which still-used cells were run before the race fix (D159 item E)

Session D (flash / A6000), 2026-11-21. Analysis only, no run.
Instrument: `experiments/orchestration/live2/v5/race_fix_cell_audit.py`.
Driver input: `results/orchestration/live2/frozen_test/runs/RERUN_CELLS`.

## Method, and why it is ancestry rather than timestamps

The race fix is `2b8714c`, "race fix: split sent from confirmed, all three proofs passing",
2026-11-20 21:28. No cell directory carries a usable wall-clock timestamp: `run_meta.json`
and `header.json` have no `timestamp` field populated. Every real cell does carry the
`git_commit` the harness stamped at run time, so the test used here is **a cell ran WITH the
fix if and only if `2b8714c` is an ancestor of that commit.** That is exact, needs no clock
agreement between hosts, and survives the morning's SHA rewrite because `2b8714c` predates
the rewritten range and is an ancestor of both the old and the new history.

Result over the 84 real cell directories (the 38 `*_REFUSED_preflight*` directories are
refusals, not runs, and are excluded): **58 pre-fix, 26 post-fix, 2 unknown**.

## What this changes, in order of consequence

### 1. Both fit cells of the D156 (4) cost-model gate are pre-fix

| role | status | cell |
|---|---|---|
| FIT | **PRE-FIX** | `warm-all-lru_n16_s4_1200s_h27_3t_L3_cal1f` |
| FIT | **PRE-FIX** | `warm-all-lru-reactive_n16_s4_1200s_h27_3t_L3_cal1f` |
| TEST | **PRE-FIX** | `warm-all-lru-off_n16_s4_1200s_h27_3t_L3_epg` |
| TEST | **PRE-FIX** | `warm-all-lru-reactive_n16_s4_1200s_h27_3t_L3_epg` |
| TEST | post-fix | `warm-all-lru_n16_s4_1200s_h27_3t_L3_epg_rf` |
| TEST | post-fix | `warm-all-lru_n16_s4_1200s_h27_3t_kv0.25_L3_epg_rf` |

**4 of the 6 cells in that gate are pre-fix, including both fit cells.** The gate exists to
predict warm first-token latency, and the race biases warm counts downward, so the gate was
fitted on data contaminated on precisely the quantity it models. This does not rescue the
FAIL verdict: 52 percent negative in-sample predictions is a defect of the model FORM and
contaminated warmth cannot produce negative latencies. But it does mean the refit ordered
under D159 (B) must not reuse these cells, and Tier 1 of `RERUN_CELLS` is exactly them.

### 2. Every cell of the committed 26-cell gate set is pre-fix, which QUALIFIES my own 07:20 finding

25 of the 26 resolve as pre-fix and the 26th is the UNKNOWN `edf_n16_s6`, so **none is
post-fix.** That set is session B's `P_hat` source.

At 07:20 I reported that the `by_arm` split's `warm_rows_held_out: 0` is **structural**,
because all eight hybrid cells are 0.00 percent warm. That inference is now only partly
supported. The eight cells are pre-fix, and the race suppresses warmth, so some of that zero
may be a race artefact rather than a property of the hybrid arms. **I over-claimed the word
structural and I withdraw it pending the rerun.**

What is unchanged: the committed artefact *does* hold out a side with zero warm rows, so its
held-out error still cannot speak to warm prediction, and MARGIN_CF stays blocked on that
ground whatever the rerun shows. What changes is only the *reason*: "these arms never go
warm" becomes "these arms recorded no warm rows in pre-fix runs". Tier 3 of `RERUN_CELLS`
is the two cells that settle it, and I have pre-registered both outcomes there.

### 3. The seed-4 row of the frozen-test headline table mixes race status with arm

Of the 28 `_L3_epg` cells at seeds 4 and 5, five are pre-fix and all five are **seed 4**:
`b7-edf-feasibility`, `eco-llm`, `warm-all-lru`, `warm-all-lru-off` and
`warm-all-lru-reactive`. Every other seed-4 cell and every seed-5 cell is post-fix. So a
comparison like `b7-edf-feasibility` s4 against `edf` s4 differs in race status as well as
arm, on a confound that acts on warmth. `warm-all-lru` s4 already has a post-fix twin
(`_L3_epg_rf`), so Tier 2 is the remaining two.

## Full pre-fix inventory

Listed so that nothing here is a judgement the reader cannot re-check. Cells marked LISTED
appear in `RERUN_CELLS`; the rest are argued as superseded in that file's trailing notes.

| cell | run commit | in RERUN_CELLS |
|---|---|---|
| `always-cloud-fcfs_n16_s4_1200s_h27_3t` | `cf4aa7c` | superseded |
| `b7-edf-feasibility_n16_s0_1200s_h27_3t` | `379965b` | superseded |
| `b7-edf-feasibility_n16_s0_1200s_h27_3t_rerun` | `379965b` | superseded |
| `b7-edf-feasibility_n16_s4_1200s_h27_3t` | `c487d01` | superseded |
| `b7-edf-feasibility_n16_s4_1200s_h27_3t_L3` | `cb7743f` | superseded |
| `b7-edf-feasibility_n16_s4_1200s_h27_3t_L3_epg` | `bdc9638` | **LISTED** |
| `b7-edf-feasibility_n16_s5_1200s_h27_3t` | `1e122e2` | superseded |
| `b7-edf-feasibility_n16_s6_1200s_h27_3t` | `72a4011` | superseded |
| `b7-edf-feasibility_n20_s0_1200s_h27_3t` | `854787e` | superseded |
| `b7-edf-feasibility_n20_s0_1200s_h27_3t_rerun` | `0628b3b` | superseded |
| `eco-llm_n14_s0_1200s_h27_3t` | `2d037eb` | superseded |
| `eco-llm_n14_s0_1200s_h27_3t_rerun` | `2d037eb` | superseded |
| `eco-llm_n16_s0_1200s_h27_3t` | `98ff542` | superseded |
| `eco-llm_n16_s0_1200s_h27_3t_postfix` | `cf50cf8` | superseded |
| `eco-llm_n16_s0_1200s_h27_3t_rerun` | `98ff542` | superseded |
| `eco-llm_n16_s4_1200s_h27_3t` | `1fd3b31` | superseded |
| `eco-llm_n16_s4_1200s_h27_3t_L3` | `47f7565` | superseded |
| `eco-llm_n16_s4_1200s_h27_3t_L3_epg` | `8afb6f5` | **LISTED** |
| `eco-llm_n16_s4_1200s_h27_3t_postfix` | `b40d092` | superseded |
| `eco-llm_n16_s5_1200s_h27_3t` | `3fafc28` | superseded |
| `eco-llm_n16_s5_1200s_h27_3t_postfix` | `e0e0778` | superseded |
| `eco-llm_n16_s6_1200s_h27_3t` | `858ab8d` | superseded |
| `eco-llm_n16_s6_1200s_h27_3t_postfix` | `ae03344` | superseded |
| `eco-llm_n16_s6_1200s_h27_3t_rerun` | `858ab8d` | superseded |
| `edf_n16_s4_1200s_h27_3t` | `4c26f12` | superseded |
| `edf_n16_s4_1200s_h27_3t_L3` | `026b567` | superseded |
| `edf_n16_s5_1200s_h27_3t` | `16e0ed9` | superseded |
| `hybrid-F-lhreq_n16_s0_1200s_h27_3t` | `6025069` | superseded |
| `hybrid-F-lhreq_n16_s0_1200s_h27_3t_postfix` | `dbdb4fa` | superseded |
| `hybrid-F-lhreq_n16_s0_1200s_h27_3t_rerun` | `6025069` | superseded |
| `hybrid-F-lhreq_n16_s4_1200s_h27_3t` | `e6d6a3f` | **LISTED** |
| `hybrid-F-lhreq_n16_s4_1200s_h27_3t_postfix` | `0ac5b8a` | superseded |
| `hybrid-F-lhreq_n16_s5_1200s_h27_3t` | `406b8ab` | superseded |
| `hybrid-F-lhreq_n16_s5_1200s_h27_3t_postfix` | `1559514` | superseded |
| `hybrid-F-lhreq_n16_s6_1200s_h27_3t` | `62edb7f` | superseded |
| `hybrid-F-lhreq_n16_s6_1200s_h27_3t_postfix` | `a9d8bed` | superseded |
| `hybrid-F6-lhreq_n16_s0_1200s_h27_3t` | `4b92e12` | superseded |
| `hybrid-F6-lhreq_n16_s0_1200s_h27_3t_rerun` | `4b92e12` | superseded |
| `hybrid-F6-lhreq_n16_s4_1200s_h27_3t` | `78eeefa` | **LISTED** |
| `hybrid-F6-lhreq_n16_s5_1200s_h27_3t` | `9db235b` | superseded |
| `hybrid-F6-lhreq_n16_s6_1200s_h27_3t` | `0e42b66` | superseded |
| `llf_n16_s4_1200s_h27_3t` | `8eb7b66` | superseded |
| `llf_n16_s4_1200s_h27_3t_L3` | `d0fc7f7` | superseded |
| `llf_n16_s5_1200s_h27_3t` | `fd51e81` | superseded |
| `llf_n16_s6_1200s_h27_3t_rerun` | `e2c8933` | superseded |
| `mooncake_n14_s0_1200s_h27_3t` | `22f8cf1` | superseded |
| `mooncake_n16_s0_1200s_h27_3t` | `1f82c7b` | superseded |
| `mooncake_n16_s4_1200s_h27_3t` | `c2f6a81` | superseded |
| `mooncake_n16_s4_1200s_h27_3t_L3` | `f93e63d` | superseded |
| `mooncake_n16_s5_1200s_h27_3t` | `ee91d73` | superseded |
| `mooncake_n16_s6_1200s_h27_3t` | `69418f6` | superseded |
| `mooncake_n16_s6_1200s_h27_3t_rerun` | `69418f6` | superseded |
| `simplestream_n16_s4_1200s_h27_3t_L3` | `c2e96e6` | superseded |
| `warm-all-lru-off_n16_s4_1200s_h27_3t_L3_epg` | `c284721` | **LISTED** |
| `warm-all-lru-reactive_n16_s4_1200s_h27_3t_L3_cal1f` | `b685fbb` | **LISTED** |
| `warm-all-lru-reactive_n16_s4_1200s_h27_3t_L3_epg` | `9615bca` | **LISTED** |
| `warm-all-lru_n16_s4_1200s_h27_3t_L3_cal1f` | `16e9131` | **LISTED** |
| `warm-all-lru_n16_s4_1200s_h27_3t_L3_epg` | `6677ccc` | superseded |

## Two provenance defects found while doing this

- `edf_n16_s6_1200s_h27_3t` records `git_commit` **42e96ae**, which is **unreachable on
  origin**. It is not in the SHA rewrite map's old column, so the rewrite did not cause it;
  the commit was most likely never pushed. Its race status is therefore undetermined and I
  have not guessed it.
- `llf_n16_s6_1200s_h27_3t` has **no `git_commit` field at all**, so it fails the CLAUDE.md
  provenance convention.

Both are recorded as defects rather than scheduled as reruns, because the remedy is to fix
the stamp, and a rerun would not tell us what the original run was.

## Register

- The pre/post split is **MEASURED** by git ancestry over 84 cell directories, not inferred
  from names or dates.
- "Still used" is a **JUDGEMENT** about which cells current analysis depends on, and the
  reasoning for each exclusion is written out in `RERUN_CELLS` so it can be disputed.
- The warmth-bias direction (downward) is **MEASURED**, on one arm/workload/seed pair across
  the fix: warm robot deliveries 1 then 6. The MAGNITUDE on any other cell is **not**
  measured and is not assumed here.

---

## CORRECTION 07:40: pre-fix is not race-contaminated, and I withdrew a word I should have kept

Everything above dates cells correctly and then draws the wrong inference from the date. The race
sent piece bytes before confirmation and **its signature is an HTTP 400**, which is how the fix was
proved (4,244 to 0 on one arm/workload/seed). So the question "was this cell bitten" is answered by
the 400 count in the cell's own request log, not by whether it predates `2b8714c`. An arm that
issues no pieces cannot be bitten at all. The H100's remark that `llf` issues no pieces is what
prompted the check.

Measured over all eight cells I listed:

| cell | requests | HTTP 400 | warm % | verdict |
|---|---|---|---|---|
| `b7-edf-feasibility` 16 4 `_L3_epg` | 12,126 | **0** | 91.10 | race-clean |
| `eco-llm` 16 4 `_L3_epg` | 12,134 | 4 | 91.00 | race-clean, 0.03 percent |
| `warm-all-lru-off` 16 4 `_L3_epg` | 12,126 | **0** | 91.10 | race-clean |
| `warm-all-lru-reactive` 16 4 `_L3_epg` | 12,523 | **0** | 91.32 | race-clean |
| `warm-all-lru-reactive` 16 4 `_L3_cal1f` | 13,954 | **0** | 2.82 | race-clean |
| `hybrid-F-lhreq` 16 4 (base) | 12,825 | **0** | **0.00** | race-clean |
| `hybrid-F6-lhreq` 16 4 (base) | 12,616 | **0** | **0.00** | race-clean |
| `warm-all-lru` 16 4 `_L3_cal1f` | 14,360 | **226** | 3.24 | **CONTAMINATED** |

**Seven of the eight need no GPU time.** `eco-llm`'s 4 of 12,134 moved nothing: 91.00 percent warm
against 91.10 for the two zero-400 cells on the identical workload. `RERUN_CELLS` is now the single
contaminated still-used cell, `warm-all-lru 16 4 _L3_cal1f_rf`, which is a **fit** cell of the
D156 (4) gate. Its co-fit cell is clean, so that one cell is the entire contamination in that fit
set. About 140 GPU-minutes freed.

### Section 2 above is wrong and "structural" is restored

Both hybrid cells measure **0 non-200, 0 HTTP 400 and 0 warm rows**. The race never fired in them,
so their zero warm is a property of the arms and **my 07:20 finding stands exactly as first
written**. The withdrawal in section 2 was my own over-correction, produced by inferring
contamination from a date rather than measuring it. Both the error and its reversal are left here
rather than edited away, because the failure mode is the interesting part: within ninety minutes I
over-claimed a word, withdrew it on an unmeasured inference, and then restored it on measurement.
The lesson is the one the knee retraction taught, in the other direction: **check before
publishing, including before publishing a retraction.**

The H100 separately notes it never applied "structural" to the gate's hybrid cells at all; its one
use of the word is `noc3`'s WARM 0 at seeds 4 and 5 on EP-G, which ran post-fix with 0 pieces. That
stands independently.

### Census and the two provenance gaps, resolved by the H100

The census is **83 real cells, not 84.** `llf_n16_s6_1200s_h27_3t` (no suffix) is **not a run**: it
is the attempt that died at `import hybrid` before writing `run_meta`, and the real cell is the
`_rerun` directory at `e2c8933`. `edf_n16_s6`'s `git_commit` **42e96ae** exists on the H100 as an
orphaned local "logs" commit from 2026-11-20 16:14, left unreachable because the driver's next
`pull --rebase` rewrote it before pushing. So that cell **is** pre-fix, and it is a 5 s dashcam-1f
D151 calibration cell of an arm that issues no pieces, so the race could not touch it either way.
Neither needs a rerun. The orphan is not being pushed: there is no branch for it and nothing reads
it.
