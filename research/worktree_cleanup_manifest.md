# Worktree and scratch-tree cleanup manifest

Ruling: **D228 (5)**. Commit authority: **D166**. Produced 2026-11-24 on flash.

This file is the audit record required by D228 (5) clause (d). Clause (c) requires a
**separate session that did not do this classification** to spot-check it; that check is
recorded in the section at the end, which this session deliberately leaves empty.

## What was classified, and against what

Four scratch trees under
`/tmp/claude-1001/-home-pragya-Desktop-FM-switching/8ab3f7e8-2a5d-4e65-8ff9-c6ae1f12519b/scratchpad/`:
`d213_e1`, `sessA_cs`, `sessA_ver`, `n206`.

**None of the four is a git worktree.** `git worktree list` on this repo reports exactly two
checkouts, `/home/pragya/Desktop/FM-switching` and `/tmp/claude-1001/mapwt`. All four trees are
plain directory copies with no `.git`, so `git worktree remove` does not apply to any of them and
`git worktree prune` has nothing to reclaim. They are removed with `rm -rf` after this manifest is
committed, which is the order D228 (5) clause (d) requires: the audit record lands first.

Classification method, per file:

1. Compute the git blob sha of the file on disk.
2. Map the file to a repo-relative path (`n206` is a repo-root copy; `d213_e1/shared_results`
   and `d213_e1/shared_results_i3` are copies of `results/`; the rest are flat scratch).
3. `IDENTICAL_ON_ORIGIN` if origin/main has that same path at that same blob;
   `CONTENT_ON_ORIGIN` if that blob is anywhere in origin/main's tree;
   otherwise compare against gunzipped origin `.gz` blobs, against blobs reachable from
   origin/main via `git rev-list --objects`, and against origin's version of the same path.

Base for the classification: `8d29e86b9a33eeba1df81f7c16cf72b09de2a8a5`.
origin/main advanced to `72032bb240608e90cfeea0c246672b78af62f226` during the work; the two rescued files were committed on top of it.
Re-checked immediately before deletion: zero files in the four trees had been modified since the
scan began, and no process had a cwd, an argv path or an open fd under any of them.

## Counts per class

| tree | action | files | MB |
|---|---|---:|---:|
| `d213_e1` | archive | 30 | 26.8 |
| `d213_e1` | commit | 1 | 0.0 |
| `d213_e1` | delete | 19634 | 7310.4 |
| `n206` | abandoned | 1 | 0.0 |
| `n206` | archive | 1 | 0.0 |
| `n206` | delete | 8926 | 2313.4 |
| `sessA_cs` | delete | 3 | 1.8 |
| `sessA_ver` | commit | 1 | 0.0 |
| `sessA_ver` | delete | 3 | 1.8 |
| **total** | | **28600** | **9654.3** |

Of the deletions, every row is justified by one of: byte-identical to origin at the same path;
content byte-identical to a blob on origin; recoverable from origin after decompression;
blob still reachable from origin/main through history; cache, log or build output; an ephemeral
session marker; or an earlier draft of work that has since landed. The per-class breakdown:

| tree | classifier verdict | files | MB |
|---|---|---:|---:|
| `d213_e1` | CONTENT_ON_ORIGIN | 18 | 0.1 |
| `d213_e1` | DIVERGENT_FROM_ORIGIN | 17 | 2.1 |
| `d213_e1` | IDENTICAL_ON_ORIGIN | 19561 | 7198.0 |
| `d213_e1` | NOVEL | 35 | 109.4 |
| `d213_e1` | REGENERABLE | 3 | 0.9 |
| `n206` | CONTENT_ON_ORIGIN | 2 | 0.0 |
| `n206` | DIVERGENT_FROM_ORIGIN | 43 | 3.3 |
| `n206` | IDENTICAL_ON_ORIGIN | 8751 | 2308.0 |
| `n206` | NOVEL | 2 | 0.0 |
| `n206` | REGENERABLE | 128 | 2.0 |
| `sessA_cs` | CONTENT_ON_ORIGIN | 1 | 0.0 |
| `sessA_cs` | NOVEL | 2 | 1.8 |
| `sessA_ver` | CONTENT_ON_ORIGIN | 1 | 0.0 |
| `sessA_ver` | NOVEL | 2 | 1.8 |

## Committed (clause c: uncommitted results belonging to landed work)

| path committed | size | sha | reason |
|---|---:|---|---|
| `results/orchestration/live2/d213_metrics_scrape/d213_rung4_live_count.json` | 15639 | `72032bb240608e90cfeea0c246672b78af62f226` | from `d213_e1/out/rung4_live_count.json`. result of landed work, not committed by its own session |
| `results/orchestration/live2/d218_device_answers/d218_1x_count_reproduction_cell.json` | 15967 | `72032bb240608e90cfeea0c246672b78af62f226` | from `sessA_ver/da_1x.json`. result of landed work, not committed by its own session |

Both landed in commit `72032bb240608e90cfeea0c246672b78af62f226`, verified by reading the published bytes back from origin and
comparing them to the source files (`cmp` rc=0 for both), and by confirming that commit touches
exactly two paths. Neither file carries the `_provenance` stamp the convention requires; they are
committed as written rather than restamped, because both are referenced by byte-identity and
digest claims that editing them would break.

## Archived (clause c: cannot be regenerated, or too large to commit)

Archive directory, named here as the ruling requires: **`/home/pragya/fm_archive/2026-11-24/`**.
Chosen on `/` (3.7 T, 28 G free at the time of the move, the only volume on this box; there is no
`/data`). It is outside `/tmp`, which is subject to cleanup. Copies were verified byte-identical
to their sources (`cmp` and `diff -rq`, rc=0) before anything was deleted. **Never delete.**

| archived path | size | source | reason |
|---|---:|---|---|
| `/home/pragya/fm_archive/2026-11-24/d213_e1/rows/A_covex-v6-cf-c5attr_s4.rows.json` | 7553781 | `d213_e1/rows/A_covex-v6-cf-c5attr_s4.rows.json` | raw s4 cell rows, not committed anywhere on origin; over the 5 MB commit limit; arm digest IS committed in d213_metrics_scrape/digests_e1.json so the rows remain verifiable |
| `/home/pragya/fm_archive/2026-11-24/d213_e1/rows/A_covex-v6-fair-c5attr_s4.rows.json` | 7187870 | `d213_e1/rows/A_covex-v6-fair-c5attr_s4.rows.json` | raw s4 cell rows, not committed anywhere on origin; over the 5 MB commit limit; arm digest IS committed in d213_metrics_scrape/digests_e1.json so the rows remain verifiable |
| `/home/pragya/fm_archive/2026-11-24/d213_e1/rung4_live/A1_covex-v6-cf-pd-c5attr_work/traces/seed4_n16_300s_A_r40-40-20_lh_req_ss2_L3_epg_perframe_rq30/trace.jsonl` | 2200881 | `d213_e1/rung4_live/A1_covex-v6-cf-pd-c5attr_work/traces/seed4_n16_300s_A_r40-40-20_lh_req_ss2_L3_epg_perframe_rq30/trace.jsonl` | raw output of the D213 CPU-stub rung-4 cell; summary committed separately; preserved rather than deleted because it is a measured run |
| `/home/pragya/fm_archive/2026-11-24/d213_e1/rung4_live/B1_covex-v6-cf-pd-c5attr_work/traces/seed4_n16_300s_A_r40-40-20_lh_req_ss2_L3_epg_perframe_rq30/trace.jsonl` | 2200881 | `d213_e1/rung4_live/B1_covex-v6-cf-pd-c5attr_work/traces/seed4_n16_300s_A_r40-40-20_lh_req_ss2_L3_epg_perframe_rq30/trace.jsonl` | raw output of the D213 CPU-stub rung-4 cell; summary committed separately; preserved rather than deleted because it is a measured run |
| `/home/pragya/fm_archive/2026-11-24/d213_e1/rung4_live/A1_covex-v6-cf-pd-c5attr/request.jsonl` | 1296893 | `d213_e1/rung4_live/A1_covex-v6-cf-pd-c5attr/request.jsonl` | raw output of the D213 CPU-stub rung-4 cell; summary committed separately; preserved rather than deleted because it is a measured run |
| `/home/pragya/fm_archive/2026-11-24/d213_e1/rung4_live/A1_covex-v6-cf-pd-c5attr/outcomes.jsonl` | 1241892 | `d213_e1/rung4_live/A1_covex-v6-cf-pd-c5attr/outcomes.jsonl` | raw output of the D213 CPU-stub rung-4 cell; summary committed separately; preserved rather than deleted because it is a measured run |
| `/home/pragya/fm_archive/2026-11-24/d213_e1/rung4_live/B1_covex-v6-cf-pd-c5attr/outcomes.jsonl` | 1219936 | `d213_e1/rung4_live/B1_covex-v6-cf-pd-c5attr/outcomes.jsonl` | raw output of the D213 CPU-stub rung-4 cell; summary committed separately; preserved rather than deleted because it is a measured run |
| `/home/pragya/fm_archive/2026-11-24/d213_e1/rung4_live/B1_covex-v6-cf-pd-c5attr/request.jsonl` | 1184059 | `d213_e1/rung4_live/B1_covex-v6-cf-pd-c5attr/request.jsonl` | raw output of the D213 CPU-stub rung-4 cell; summary committed separately; preserved rather than deleted because it is a measured run |
| `/home/pragya/fm_archive/2026-11-24/d213_e1/rung4_live/A1_covex-v6-cf-pd-c5attr_work/traces/seed4_n16_300s_A_r40-40-20_lh_req_ss2_L3_epg_perframe_rq30/device_answers.jsonl` | 769508 | `d213_e1/rung4_live/A1_covex-v6-cf-pd-c5attr_work/traces/seed4_n16_300s_A_r40-40-20_lh_req_ss2_L3_epg_perframe_rq30/device_answers.jsonl` | raw output of the D213 CPU-stub rung-4 cell; summary committed separately; preserved rather than deleted because it is a measured run |
| `/home/pragya/fm_archive/2026-11-24/d213_e1/rung4_live/B1_covex-v6-cf-pd-c5attr_work/traces/seed4_n16_300s_A_r40-40-20_lh_req_ss2_L3_epg_perframe_rq30/device_answers.jsonl` | 769508 | `d213_e1/rung4_live/B1_covex-v6-cf-pd-c5attr_work/traces/seed4_n16_300s_A_r40-40-20_lh_req_ss2_L3_epg_perframe_rq30/device_answers.jsonl` | raw output of the D213 CPU-stub rung-4 cell; summary committed separately; preserved rather than deleted because it is a measured run |
| `/home/pragya/fm_archive/2026-11-24/d213_e1/rung4_live/A1_covex-v6-cf-pd-c5attr/decision.jsonl` | 514722 | `d213_e1/rung4_live/A1_covex-v6-cf-pd-c5attr/decision.jsonl` | raw output of the D213 CPU-stub rung-4 cell; summary committed separately; preserved rather than deleted because it is a measured run |
| `/home/pragya/fm_archive/2026-11-24/d213_e1/rung4_live/B1_covex-v6-cf-pd-c5attr/decision.jsonl` | 452225 | `d213_e1/rung4_live/B1_covex-v6-cf-pd-c5attr/decision.jsonl` | raw output of the D213 CPU-stub rung-4 cell; summary committed separately; preserved rather than deleted because it is a measured run |
| `/home/pragya/fm_archive/2026-11-24/d213_e1/rung4_live/B1_covex-v6-cf-pd-c5attr/residency.jsonl` | 27674 | `d213_e1/rung4_live/B1_covex-v6-cf-pd-c5attr/residency.jsonl` | raw output of the D213 CPU-stub rung-4 cell; summary committed separately; preserved rather than deleted because it is a measured run |
| `/home/pragya/fm_archive/2026-11-24/d213_e1/rung4_live/A1_covex-v6-cf-pd-c5attr/residency.jsonl` | 22814 | `d213_e1/rung4_live/A1_covex-v6-cf-pd-c5attr/residency.jsonl` | raw output of the D213 CPU-stub rung-4 cell; summary committed separately; preserved rather than deleted because it is a measured run |
| `/home/pragya/fm_archive/2026-11-24/d213_e1/rung4_live/A1_covex-v6-cf-pd-c5attr/decision_time.jsonl.gz` | 22209 | `d213_e1/rung4_live/A1_covex-v6-cf-pd-c5attr/decision_time.jsonl.gz` | raw output of the D213 CPU-stub rung-4 cell; summary committed separately; preserved rather than deleted because it is a measured run |
| `/home/pragya/fm_archive/2026-11-24/d213_e1/rung4_live/B1_covex-v6-cf-pd-c5attr/decision_time.jsonl.gz` | 22098 | `d213_e1/rung4_live/B1_covex-v6-cf-pd-c5attr/decision_time.jsonl.gz` | raw output of the D213 CPU-stub rung-4 cell; summary committed separately; preserved rather than deleted because it is a measured run |
| `/home/pragya/fm_archive/2026-11-24/d213_e1/rung4_live/A1_covex-v6-cf-pd-c5attr_work/traces/seed4_n16_300s_A_r40-40-20_lh_req_ss2_L3_epg_perframe_rq30/trace_meta.json` | 11901 | `d213_e1/rung4_live/A1_covex-v6-cf-pd-c5attr_work/traces/seed4_n16_300s_A_r40-40-20_lh_req_ss2_L3_epg_perframe_rq30/trace_meta.json` | raw output of the D213 CPU-stub rung-4 cell; summary committed separately; preserved rather than deleted because it is a measured run |
| `/home/pragya/fm_archive/2026-11-24/d213_e1/rung4_live/B1_covex-v6-cf-pd-c5attr_work/traces/seed4_n16_300s_A_r40-40-20_lh_req_ss2_L3_epg_perframe_rq30/trace_meta.json` | 11901 | `d213_e1/rung4_live/B1_covex-v6-cf-pd-c5attr_work/traces/seed4_n16_300s_A_r40-40-20_lh_req_ss2_L3_epg_perframe_rq30/trace_meta.json` | raw output of the D213 CPU-stub rung-4 cell; summary committed separately; preserved rather than deleted because it is a measured run |
| `/home/pragya/fm_archive/2026-11-24/n206/test_d206_no_live_deficitcounters.py` | 10205 | `n206/experiments/orchestration/live2/tests/test_d206_no_live_deficitcounters.py` | uncommitted guard test (D206 (3)); no equivalent on origin; its sibling files in this tree are pre-D223 drafts so it is not verified against current origin -- preserved, not committed, and flagged for the D206 owner |
| `/home/pragya/fm_archive/2026-11-24/d213_e1/rung4_live/B1_covex-v6-cf-pd-c5attr/coordinator_result.json` | 8643 | `d213_e1/rung4_live/B1_covex-v6-cf-pd-c5attr/coordinator_result.json` | raw output of the D213 CPU-stub rung-4 cell; summary committed separately; preserved rather than deleted because it is a measured run |
| `/home/pragya/fm_archive/2026-11-24/d213_e1/rung4_live/A1_covex-v6-cf-pd-c5attr/coordinator_result.json` | 7894 | `d213_e1/rung4_live/A1_covex-v6-cf-pd-c5attr/coordinator_result.json` | raw output of the D213 CPU-stub rung-4 cell; summary committed separately; preserved rather than deleted because it is a measured run |
| `/home/pragya/fm_archive/2026-11-24/d213_e1/rung4_live/B1_covex-v6-cf-pd-c5attr/run_meta.json` | 7702 | `d213_e1/rung4_live/B1_covex-v6-cf-pd-c5attr/run_meta.json` | raw output of the D213 CPU-stub rung-4 cell; summary committed separately; preserved rather than deleted because it is a measured run |
| `/home/pragya/fm_archive/2026-11-24/d213_e1/rung4_live/A1_covex-v6-cf-pd-c5attr/run_meta.json` | 7701 | `d213_e1/rung4_live/A1_covex-v6-cf-pd-c5attr/run_meta.json` | raw output of the D213 CPU-stub rung-4 cell; summary committed separately; preserved rather than deleted because it is a measured run |
| `/home/pragya/fm_archive/2026-11-24/d213_e1/rung4_live/A1_covex-v6-cf-pd-c5attr/header.json` | 4970 | `d213_e1/rung4_live/A1_covex-v6-cf-pd-c5attr/header.json` | raw output of the D213 CPU-stub rung-4 cell; summary committed separately; preserved rather than deleted because it is a measured run |
| `/home/pragya/fm_archive/2026-11-24/d213_e1/rung4_live/B1_covex-v6-cf-pd-c5attr/header.json` | 4970 | `d213_e1/rung4_live/B1_covex-v6-cf-pd-c5attr/header.json` | raw output of the D213 CPU-stub rung-4 cell; summary committed separately; preserved rather than deleted because it is a measured run |
| `/home/pragya/fm_archive/2026-11-24/d213_e1/rung4_live/A1_covex-v6-cf-pd-c5attr/host_load.jsonl.gz` | 4950 | `d213_e1/rung4_live/A1_covex-v6-cf-pd-c5attr/host_load.jsonl.gz` | raw output of the D213 CPU-stub rung-4 cell; summary committed separately; preserved rather than deleted because it is a measured run |
| `/home/pragya/fm_archive/2026-11-24/d213_e1/rung4_live/B1_covex-v6-cf-pd-c5attr/host_load.jsonl.gz` | 4861 | `d213_e1/rung4_live/B1_covex-v6-cf-pd-c5attr/host_load.jsonl.gz` | raw output of the D213 CPU-stub rung-4 cell; summary committed separately; preserved rather than deleted because it is a measured run |
| `/home/pragya/fm_archive/2026-11-24/d213_e1/rung4_live/A1_covex-v6-cf-pd-c5attr/frames_preflight.json` | 1460 | `d213_e1/rung4_live/A1_covex-v6-cf-pd-c5attr/frames_preflight.json` | raw output of the D213 CPU-stub rung-4 cell; summary committed separately; preserved rather than deleted because it is a measured run |
| `/home/pragya/fm_archive/2026-11-24/d213_e1/rung4_live/B1_covex-v6-cf-pd-c5attr/frames_preflight.json` | 1460 | `d213_e1/rung4_live/B1_covex-v6-cf-pd-c5attr/frames_preflight.json` | raw output of the D213 CPU-stub rung-4 cell; summary committed separately; preserved rather than deleted because it is a measured run |
| `/home/pragya/fm_archive/2026-11-24/d213_e1/rung4_live/A1_covex-v6-cf-pd-c5attr/cell.json` | 828 | `d213_e1/rung4_live/A1_covex-v6-cf-pd-c5attr/cell.json` | raw output of the D213 CPU-stub rung-4 cell; summary committed separately; preserved rather than deleted because it is a measured run |
| `/home/pragya/fm_archive/2026-11-24/d213_e1/rung4_live/B1_covex-v6-cf-pd-c5attr/cell.json` | 827 | `d213_e1/rung4_live/B1_covex-v6-cf-pd-c5attr/cell.json` | raw output of the D213 CPU-stub rung-4 cell; summary committed separately; preserved rather than deleted because it is a measured run |

`rows/B_covex-v6-cf-c5attr_s4.rows.json` and `rows/B_covex-v6-fair-c5attr_s4.rows.json` are NOT
archived: each is byte-identical to the archived `A_` copy (proved by `cmp`), which is itself the
D213 finding those cells were run to establish.

## Abandoned (clause c: one line, then delete)

| path | size | reason |
|---|---:|---|
| `n206/results/orchestration/live2/frozen_test/runs/V6CFR3_KV025_CELLS` | 4289 | 0.25x rung-4 cell list posted under D206 (3); D223 (1) removed 0.25x entirely (no 0.25x cells queued or run for any arm). Superseded before it was ever committed. |

## Flagged for the owning D-row, not resolved by this session

`n206/experiments/orchestration/live2/tests/test_d206_no_live_deficitcounters.py` is the D206 (3)
guard test: it asserts that no registered arm's live path constructs `cf_objective.DeficitCounters`,
and proves the declared-constant equivalence at all five read sites. **No equivalent exists on
origin** (no path matches `test_d206`, and of origin's thirteen `live2/tests/` files only
`test_cf_objective_d177.py` mentions `DeficitCounters`, for a different purpose). It is therefore
real uncommitted code, not a duplicate.

It was archived rather than committed, because every sibling file in `n206` is a pre-D223 draft:
`n206`'s `arms_v6fair.py` still hard-codes `limit_tokens=32768`, which D223 (2) replaced with the
server's configured `max-model-len`. A guard test from that tree is not verified against current
origin, and a cleanup session should not add a possibly-failing test to the suite. The file is
preserved at `/home/pragya/fm_archive/2026-11-24/n206/test_d206_no_live_deficitcounters.py` for
whoever owns D206 (3) to run and land.

## Per-file rows for every judgment class

The rows below are the ones that required a decision rather than a sha comparison: every
`DIVERGENT_FROM_ORIGIN` and every `NOVEL` file in all four trees. These are the rows clause (c)
directs a spot-checker at. `blob` is the git blob sha of the file as it sat on disk.

### `n206` (47 rows)

| path | size | blob | class | action | reason |
|---|---:|---|---|---|---|
| `research/EXPERIMENTS.md` | 1216639 | `a1afb7898e68` | DIVERGENT_FROM_ORIGIN | delete | older committed version of a file origin/main has since advanced; that exact blob is still reachable from origin/main |
| `results/INDEX.md` | 493809 | `168b5a16dc98` | DIVERGENT_FROM_ORIGIN | delete | older committed version of a file origin/main has since advanced; that exact blob is still reachable from origin/main |
| `research/policy_design_log.md` | 191765 | `0ca970332ed0` | DIVERGENT_FROM_ORIGIN | delete | older committed version of a file origin/main has since advanced; that exact blob is still reachable from origin/main |
| `research/STATUS.md` | 182880 | `f7bfeae33f81` | DIVERGENT_FROM_ORIGIN | delete | older committed version of a file origin/main has since advanced; that exact blob is still reachable from origin/main |
| `experiments/orchestration/live2/coordinator.py` | 145571 | `2752640584d1` | DIVERGENT_FROM_ORIGIN | delete | older committed version of a file origin/main has since advanced; that exact blob is still reachable from origin/main |
| `results/orchestration/live2/frozen_test/d200_gatea_safety.json` | 115523 | `cced08a82163` | DIVERGENT_FROM_ORIGIN | delete | earlier draft of work that LANDED on origin in a later form (verified: origin carries the same mechanism plus D223 (2), which this tree predates). Nothing here exists only in this tree |
| `experiments/orchestration/live2/scorer/score.py` | 95907 | `93483b23c731` | DIVERGENT_FROM_ORIGIN | delete | older committed version of a file origin/main has since advanced; that exact blob is still reachable from origin/main |
| `experiments/orchestration/live2/baseline_matrix_table.py` | 71043 | `bcc41ba79122` | DIVERGENT_FROM_ORIGIN | delete | older committed version of a file origin/main has since advanced; that exact blob is still reachable from origin/main |
| `experiments/orchestration/live2/d179_rung2_verdict.py` | 64927 | `21c04bac7ace` | DIVERGENT_FROM_ORIGIN | delete | older committed version of a file origin/main has since advanced; that exact blob is still reachable from origin/main |
| `experiments/orchestration/live2/fleet/trace.py` | 64313 | `c3b90970f1f1` | DIVERGENT_FROM_ORIGIN | delete | older committed version of a file origin/main has since advanced; that exact blob is still reachable from origin/main |
| `experiments/orchestration/live2/v5/cf_planner.py` | 56643 | `2dc41bf717de` | DIVERGENT_FROM_ORIGIN | delete | earlier draft of work that LANDED on origin in a later form (verified: origin carries the same mechanism plus D223 (2), which this tree predates). Nothing here exists only in this tree |
| `experiments/orchestration/live2/hybrid/hybrid_arm.py` | 54540 | `6fee76bef907` | DIVERGENT_FROM_ORIGIN | delete | older committed version of a file origin/main has since advanced; that exact blob is still reachable from origin/main |
| `experiments/orchestration/live2/v5/cf_objective.py` | 54037 | `7663d5cce699` | DIVERGENT_FROM_ORIGIN | delete | earlier draft of work that LANDED on origin in a later form (verified: origin carries the same mechanism plus D223 (2), which this tree predates). Nothing here exists only in this tree |
| `experiments/orchestration/live2/arms_v6cfr3.py` | 38764 | `c8bf05f351b3` | DIVERGENT_FROM_ORIGIN | delete | earlier draft of work that LANDED on origin in a later form (verified: origin carries the same mechanism plus D223 (2), which this tree predates). Nothing here exists only in this tree |
| `experiments/orchestration/live2/cstate.py` | 38178 | `5f3b0fde6b03` | DIVERGENT_FROM_ORIGIN | delete | older committed version of a file origin/main has since advanced; that exact blob is still reachable from origin/main |
| `research/OVERNIGHT_HANDOFF_H100.md` | 33789 | `f4c664094a79` | DIVERGENT_FROM_ORIGIN | delete | older committed version of a file origin/main has since advanced; that exact blob is still reachable from origin/main |
| `experiments/orchestration/live2/arms_v6cf.py` | 33657 | `e483155aa32f` | DIVERGENT_FROM_ORIGIN | delete | older committed version of a file origin/main has since advanced; that exact blob is still reachable from origin/main |
| `reports/study_e1_nexar_lead.md` | 33223 | `41d0a423c609` | DIVERGENT_FROM_ORIGIN | delete | older committed version of a file origin/main has since advanced; that exact blob is still reachable from origin/main |
| `experiments/orchestration/live2/run_live2_real.py` | 31197 | `a5e957540ec3` | DIVERGENT_FROM_ORIGIN | delete | older committed version of a file origin/main has since advanced; that exact blob is still reachable from origin/main |
| `experiments/orchestration/live/adapter.py` | 28576 | `f534379e63d4` | DIVERGENT_FROM_ORIGIN | delete | older committed version of a file origin/main has since advanced; that exact blob is still reachable from origin/main |
| `experiments/orchestration/baselines/interface.py` | 28366 | `1a1d2419f36c` | DIVERGENT_FROM_ORIGIN | delete | older committed version of a file origin/main has since advanced; that exact blob is still reachable from origin/main |
| `experiments/orchestration/live2/engine_actions.py` | 28013 | `1ee3f792e7ff` | DIVERGENT_FROM_ORIGIN | delete | older committed version of a file origin/main has since advanced; that exact blob is still reachable from origin/main |
| `experiments/orchestration/live2/procsplit.py` | 23894 | `19b9905994aa` | DIVERGENT_FROM_ORIGIN | delete | older committed version of a file origin/main has since advanced; that exact blob is still reachable from origin/main |
| `experiments/orchestration/live2/schema.py` | 20479 | `422c23fa48cd` | DIVERGENT_FROM_ORIGIN | delete | older committed version of a file origin/main has since advanced; that exact blob is still reachable from origin/main |
| `experiments/orchestration/live2/arms_published.py` | 20211 | `54327d813447` | DIVERGENT_FROM_ORIGIN | delete | older committed version of a file origin/main has since advanced; that exact blob is still reachable from origin/main |
| `experiments/orchestration/study_live2_pilot.py` | 19062 | `d1c063a058b0` | DIVERGENT_FROM_ORIGIN | delete | older committed version of a file origin/main has since advanced; that exact blob is still reachable from origin/main |
| `experiments/analysis/early1/dsmap.py` | 17230 | `0493534e1769` | DIVERGENT_FROM_ORIGIN | delete | older committed version of a file origin/main has since advanced; that exact blob is still reachable from origin/main |
| `experiments/orchestration/live2/d200_gatea_safety.py` | 17005 | `97ddc163b84a` | DIVERGENT_FROM_ORIGIN | delete | earlier draft of work that LANDED on origin in a later form (verified: origin carries the same mechanism plus D223 (2), which this tree predates). Nothing here exists only in this tree |
| `experiments/analysis/episodic/build_episodic.py` | 15726 | `5e3724d49245` | DIVERGENT_FROM_ORIGIN | delete | older committed version of a file origin/main has since advanced; that exact blob is still reachable from origin/main |
| `experiments/orchestration/live2/asyncbackend.py` | 15073 | `079099b1b0c0` | DIVERGENT_FROM_ORIGIN | delete | older committed version of a file origin/main has since advanced; that exact blob is still reachable from origin/main |
| `experiments/orchestration/baselines/cards/ecollm.md` | 12633 | `0d06075e7a4a` | DIVERGENT_FROM_ORIGIN | delete | older committed version of a file origin/main has since advanced; that exact blob is still reachable from origin/main |
| `reports/study_dash2.md` | 12602 | `477dd6aec65f` | DIVERGENT_FROM_ORIGIN | delete | older committed version of a file origin/main has since advanced; that exact blob is still reachable from origin/main |
| `experiments/orchestration/live2/arms_v6fair.py` | 11230 | `e5bca38fc807` | DIVERGENT_FROM_ORIGIN | delete | earlier draft of work that LANDED on origin in a later form (verified: origin carries the same mechanism plus D223 (2), which this tree predates). Nothing here exists only in this tree |
| `experiments/orchestration/live2/touch_policy.py` | 10789 | `8c1bcb38e481` | DIVERGENT_FROM_ORIGIN | delete | older committed version of a file origin/main has since advanced; that exact blob is still reachable from origin/main |
| `research/OVERNIGHT_HANDOFF.md` | 7033 | `6a1d6ba46d08` | DIVERGENT_FROM_ORIGIN | delete | older committed version of a file origin/main has since advanced; that exact blob is still reachable from origin/main |
| `experiments/analysis/episodic/episodic_lib.py` | 6388 | `f07b4f2f621d` | DIVERGENT_FROM_ORIGIN | delete | older committed version of a file origin/main has since advanced; that exact blob is still reachable from origin/main |
| `experiments/orchestration/baselines/cards/simplestream.md` | 6318 | `2d67aa53da64` | DIVERGENT_FROM_ORIGIN | delete | older committed version of a file origin/main has since advanced; that exact blob is still reachable from origin/main |
| `results/orchestration/live2/d200_one_deficit_weight/EXPERIMENTS_row_draft.md` | 5744 | `5ea8b0739142` | DIVERGENT_FROM_ORIGIN | delete | older committed version of a file origin/main has since advanced; that exact blob is still reachable from origin/main |
| `experiments/orchestration/h100_overnight_watchdog.sh` | 5396 | `73be302938da` | DIVERGENT_FROM_ORIGIN | delete | older committed version of a file origin/main has since advanced; that exact blob is still reachable from origin/main |
| `experiments/orchestration/baselines/simplestream_adapted.py` | 4709 | `02132f1db6db` | DIVERGENT_FROM_ORIGIN | delete | older committed version of a file origin/main has since advanced; that exact blob is still reachable from origin/main |
| `experiments/orchestration/baselines/cards/mooncake.md` | 3999 | `a0950da87e2c` | DIVERGENT_FROM_ORIGIN | delete | older committed version of a file origin/main has since advanced; that exact blob is still reachable from origin/main |
| `reports/study_dsmap.md` | 3526 | `276e877e7456` | DIVERGENT_FROM_ORIGIN | delete | older committed version of a file origin/main has since advanced; that exact blob is still reachable from origin/main |
| `results/orchestration/live2/frozen_test/runs/DEVWAIT_READY` | 3381 | `1aa54f750744` | DIVERGENT_FROM_ORIGIN | delete | older committed version of a file origin/main has since advanced; that exact blob is still reachable from origin/main |
| `experiments/orchestration/live2/tests/test_d206_no_live_deficitcounters.py` | 10205 | `1582b9ff2944` | NOVEL | archive | uncommitted guard test (D206 (3)); no equivalent on origin; its sibling files in this tree are pre-D223 drafts so it is not verified against current origin -- preserved, not committed, and flagged for the D206 owner |
| `results/orchestration/live2/frozen_test/runs/V6CFR3_KV025_CELLS` | 4289 | `27a824e6913c` | NOVEL | abandoned | 0.25x rung-4 cell list posted under D206 (3); D223 (1) removed 0.25x entirely (no 0.25x cells queued or run for any arm). Superseded before it was ever committed. |
| `ops/STANDDOWN` | 360 | `d59c2f40406a` | NOVEL | delete | ops marker that expired 2026-11-23 13:00Z; carries no result |
| `SHA` | 41 | `aa23cbea5afd` | NOVEL | delete | ephemeral session marker (pid / base sha / scoped list / git index file); carries no result |

### `d213_e1` (83 rows)

| path | size | blob | class | action | reason |
|---|---:|---|---|---|---|
| `shared_results_i3/INDEX.md` | 546026 | `bbc5309e6be8` | DIVERGENT_FROM_ORIGIN | delete | older committed version of a file origin/main has since advanced; that exact blob is still reachable from origin/main |
| `shared_results/INDEX.md` | 535541 | `60ade199e42f` | DIVERGENT_FROM_ORIGIN | delete | older committed version of a file origin/main has since advanced; that exact blob is still reachable from origin/main |
| `shared_results_i3/orchestration/live2/pilot/pilot_monitor.jsonl` | 313493 | `68bdf24e33ab` | DIVERGENT_FROM_ORIGIN | delete | older committed version of a file origin/main has since advanced; that exact blob is still reachable from origin/main |
| `shared_results/orchestration/live2/pilot/pilot_monitor.jsonl` | 304505 | `66ba64a4a6cb` | DIVERGENT_FROM_ORIGIN | delete | older committed version of a file origin/main has since advanced; that exact blob is still reachable from origin/main |
| `shared_results_i3/orchestration/live2/frozen_test/runs/simplestream_n16_s6_1200s_h27_3t_L3_epg_rq30_rerun/cell.json` | 232077 | `af136c8fb032` | DIVERGENT_FROM_ORIGIN | delete | older committed version of a file origin/main has since advanced; that exact blob is still reachable from origin/main |
| `shared_results/orchestration/live2/frozen_test/d208_final_s4_verdict.json` | 43166 | `701861563110` | DIVERGENT_FROM_ORIGIN | delete | older committed version of a file origin/main has since advanced; that exact blob is still reachable from origin/main |
| `shared_results_i3/orchestration/live2/frozen_test/runs/FILLER_QUEUE` | 15826 | `dea3c8f363fa` | DIVERGENT_FROM_ORIGIN | delete | older committed version of a file origin/main has since advanced; that exact blob is still reachable from origin/main |
| `shared_results/orchestration/live2/frozen_test/runs/FILLER_QUEUE` | 15614 | `9d78f960a416` | DIVERGENT_FROM_ORIGIN | delete | older committed version of a file origin/main has since advanced; that exact blob is still reachable from origin/main |
| `shared_results_i3/orchestration/live2/frozen_test/d208_rung4_mechanism_convergence.json` | 12824 | `aaa24382eabd` | DIVERGENT_FROM_ORIGIN | delete | older committed version of a file origin/main has since advanced; that exact blob is still reachable from origin/main |
| `shared_results/orchestration/live2/ladder_final/d208_proof_a_bars.json` | 9416 | `797a218726dc` | DIVERGENT_FROM_ORIGIN | delete | older committed version of a file origin/main has since advanced; that exact blob is still reachable from origin/main |
| `shared_results_i3/orchestration/live2/frozen_test/trace_digests.jsonl` | 8988 | `184a0884a674` | DIVERGENT_FROM_ORIGIN | delete | older committed version of a file origin/main has since advanced; that exact blob is still reachable from origin/main |
| `shared_results/orchestration/live2/frozen_test/trace_digests.jsonl` | 8988 | `184a0884a674` | DIVERGENT_FROM_ORIGIN | delete | older committed version of a file origin/main has since advanced; that exact blob is still reachable from origin/main |
| `shared_results/orchestration/live2/d218_device_answers/d218_device_answers_prereg.json` | 6780 | `6a3af19f89fd` | DIVERGENT_FROM_ORIGIN | delete | older committed version of a file origin/main has since advanced; that exact blob is still reachable from origin/main |
| `shared_results_i3/orchestration/live2/d213_metrics_scrape/E1_IS_AN_ABSENT_LINK.json` | 6419 | `2b7f2e32bc14` | DIVERGENT_FROM_ORIGIN | delete | older committed version of a file origin/main has since advanced; that exact blob is still reachable from origin/main |
| `shared_results_i3/orchestration/live2/frozen_test/runs/MATRIX_READY_CELLS` | 5678 | `b97cdc4d28a7` | DIVERGENT_FROM_ORIGIN | delete | older committed version of a file origin/main has since advanced; that exact blob is still reachable from origin/main |
| `shared_results/orchestration/live2/frozen_test/runs/MATRIX_READY_CELLS` | 4430 | `38d2f1dd7d31` | DIVERGENT_FROM_ORIGIN | delete | older committed version of a file origin/main has since advanced; that exact blob is still reachable from origin/main |
| `shared_results/orchestration/live2/d213_metrics_scrape/digests_PARTIAL_SUPERSEDED.json` | 2130 | `61e0546ffad0` | DIVERGENT_FROM_ORIGIN | delete | older committed version of a file origin/main has since advanced; that exact blob is still reachable from origin/main |
| `rows/B_covex-v6-cf-c5attr_s4.rows.json` | 7553781 | `cadfe57ad1ad` | NOVEL | delete | byte-identical duplicate of the A_ copy in the same tree (A==B proved by cmp); the A_ copy is archived |
| `rows/A_covex-v6-cf-c5attr_s4.rows.json` | 7553781 | `cadfe57ad1ad` | NOVEL | archive | raw s4 cell rows, not committed anywhere on origin; over the 5 MB commit limit; arm digest IS committed in d213_metrics_scrape/digests_e1.json so the rows remain verifiable |
| `rows/B_covex-v6-state-uo_s4.rows.json` | 7395861 | `e06c3925247d` | NOVEL | delete | byte-identical to committed content after decompression of a .gz blob on origin/main |
| `rows/A_covex-v6-state-uo_s4.rows.json` | 7395861 | `e06c3925247d` | NOVEL | delete | byte-identical to committed content after decompression of a .gz blob on origin/main |
| `rows/B_covex-v6-cf-pd-c5attr_s4.rows.json` | 7395861 | `e06c3925247d` | NOVEL | delete | byte-identical to committed content after decompression of a .gz blob on origin/main |
| `rows/A_covex-v6-state-uo-c5attr_s4.rows.json` | 7395861 | `e06c3925247d` | NOVEL | delete | byte-identical to committed content after decompression of a .gz blob on origin/main |
| `rows/B_covex-v6-state-uo-c5attr_s4.rows.json` | 7395861 | `e06c3925247d` | NOVEL | delete | byte-identical to committed content after decompression of a .gz blob on origin/main |
| `rows/A_covex-v6-cf-pd-c5attr_s4.rows.json` | 7395861 | `e06c3925247d` | NOVEL | delete | byte-identical to committed content after decompression of a .gz blob on origin/main |
| `rows/A_covex-v6-fair-c5attr_s4.rows.json` | 7187870 | `06ca1e22498d` | NOVEL | archive | raw s4 cell rows, not committed anywhere on origin; over the 5 MB commit limit; arm digest IS committed in d213_metrics_scrape/digests_e1.json so the rows remain verifiable |
| `rows/B_covex-v6-fair-c5attr_s4.rows.json` | 7187870 | `06ca1e22498d` | NOVEL | delete | byte-identical duplicate of the A_ copy in the same tree (A==B proved by cmp); the A_ copy is archived |
| `rows/B_covex-v6-base_s4.rows.json` | 6197398 | `81fc8c373465` | NOVEL | delete | byte-identical to committed content after decompression of a .gz blob on origin/main |
| `rows/B1_covex-v6-base_s4.rows.json` | 6197398 | `81fc8c373465` | NOVEL | delete | byte-identical to committed content after decompression of a .gz blob on origin/main |
| `rows/B2_covex-v6-base_s4.rows.json` | 6197398 | `81fc8c373465` | NOVEL | delete | byte-identical to committed content after decompression of a .gz blob on origin/main |
| `rows/A2_covex-v6-base_s4.rows.json` | 6197398 | `81fc8c373465` | NOVEL | delete | byte-identical to committed content after decompression of a .gz blob on origin/main |
| `rows/A1_covex-v6-base_s4.rows.json` | 6197398 | `81fc8c373465` | NOVEL | delete | byte-identical to committed content after decompression of a .gz blob on origin/main |
| `rows/A_covex-v6-base_s4.rows.json` | 6197398 | `81fc8c373465` | NOVEL | delete | byte-identical to committed content after decompression of a .gz blob on origin/main |
| `rows/B_covex-v6-rules_s4.rows.json` | 6140727 | `5c0564cecc0e` | NOVEL | delete | byte-identical to committed content after decompression of a .gz blob on origin/main |
| `rows/A_covex-v6-rules_s4.rows.json` | 6140727 | `5c0564cecc0e` | NOVEL | delete | byte-identical to committed content after decompression of a .gz blob on origin/main |
| `rung4_live/A1_covex-v6-cf-pd-c5attr_work/traces/seed4_n16_300s_A_r40-40-20_lh_req_ss2_L3_epg_perframe_rq30/trace.jsonl` | 2200881 | `5ef13cfb52c5` | NOVEL | archive | raw output of the D213 CPU-stub rung-4 cell; summary committed separately; preserved rather than deleted because it is a measured run |
| `rung4_live/B1_covex-v6-cf-pd-c5attr_work/traces/seed4_n16_300s_A_r40-40-20_lh_req_ss2_L3_epg_perframe_rq30/trace.jsonl` | 2200881 | `5ef13cfb52c5` | NOVEL | archive | raw output of the D213 CPU-stub rung-4 cell; summary committed separately; preserved rather than deleted because it is a measured run |
| `rung4_live/A1_covex-v6-cf-pd-c5attr/request.jsonl` | 1296893 | `390c61dda736` | NOVEL | archive | raw output of the D213 CPU-stub rung-4 cell; summary committed separately; preserved rather than deleted because it is a measured run |
| `rung4_live/A1_covex-v6-cf-pd-c5attr/outcomes.jsonl` | 1241892 | `e3b60d52ab70` | NOVEL | archive | raw output of the D213 CPU-stub rung-4 cell; summary committed separately; preserved rather than deleted because it is a measured run |
| `rung4_live/B1_covex-v6-cf-pd-c5attr/outcomes.jsonl` | 1219936 | `0c679998baee` | NOVEL | archive | raw output of the D213 CPU-stub rung-4 cell; summary committed separately; preserved rather than deleted because it is a measured run |
| `rung4_live/B1_covex-v6-cf-pd-c5attr/request.jsonl` | 1184059 | `6d0ccc02ec47` | NOVEL | archive | raw output of the D213 CPU-stub rung-4 cell; summary committed separately; preserved rather than deleted because it is a measured run |
| `rung4_live/A1_covex-v6-cf-pd-c5attr_work/traces/seed4_n16_300s_A_r40-40-20_lh_req_ss2_L3_epg_perframe_rq30/device_answers.jsonl` | 769508 | `2a9db478f71a` | NOVEL | archive | raw output of the D213 CPU-stub rung-4 cell; summary committed separately; preserved rather than deleted because it is a measured run |
| `rung4_live/B1_covex-v6-cf-pd-c5attr_work/traces/seed4_n16_300s_A_r40-40-20_lh_req_ss2_L3_epg_perframe_rq30/device_answers.jsonl` | 769508 | `2a9db478f71a` | NOVEL | archive | raw output of the D213 CPU-stub rung-4 cell; summary committed separately; preserved rather than deleted because it is a measured run |
| `rung4_live/A1_covex-v6-cf-pd-c5attr/decision.jsonl` | 514722 | `a2dd78501676` | NOVEL | archive | raw output of the D213 CPU-stub rung-4 cell; summary committed separately; preserved rather than deleted because it is a measured run |
| `rung4_live/B1_covex-v6-cf-pd-c5attr/decision.jsonl` | 452225 | `075815bdbd39` | NOVEL | archive | raw output of the D213 CPU-stub rung-4 cell; summary committed separately; preserved rather than deleted because it is a measured run |
| `out/digests_e1.json` | 283799 | `40fa164fba3d` | NOVEL | delete | earlier partial version of a file origin/main committed in a later, larger form under results/orchestration/live2/d213_metrics_scrape/ |
| `out/item3_digests.json` | 169881 | `efe5394e96be` | NOVEL | delete | earlier partial version of a file origin/main committed in a later, larger form under results/orchestration/live2/d213_metrics_scrape/ |
| `coord_published.py` | 150022 | `2b832f08d402` | NOVEL | delete | verbatim copy of a committed file version; blob reachable from origin/main via git rev-list --objects |
| `coord_at_tip.py` | 146395 | `6e5fe0c3d0a8` | NOVEL | delete | verbatim copy of a committed file version; blob reachable from origin/main via git rev-list --objects |
| `rung4_live/B1_covex-v6-cf-pd-c5attr/residency.jsonl` | 27674 | `3f6b7b64ee36` | NOVEL | archive | raw output of the D213 CPU-stub rung-4 cell; summary committed separately; preserved rather than deleted because it is a measured run |
| `rung4_live/A1_covex-v6-cf-pd-c5attr/residency.jsonl` | 22814 | `333aafc266f2` | NOVEL | archive | raw output of the D213 CPU-stub rung-4 cell; summary committed separately; preserved rather than deleted because it is a measured run |
| `rung4_live/A1_covex-v6-cf-pd-c5attr/decision_time.jsonl.gz` | 22209 | `1b1f890e0d62` | NOVEL | archive | raw output of the D213 CPU-stub rung-4 cell; summary committed separately; preserved rather than deleted because it is a measured run |
| `rung4_live/B1_covex-v6-cf-pd-c5attr/decision_time.jsonl.gz` | 22098 | `2b19d24fb918` | NOVEL | archive | raw output of the D213 CPU-stub rung-4 cell; summary committed separately; preserved rather than deleted because it is a measured run |
| `patch_async.py` | 18435 | `422db7a6b066` | NOVEL | delete | verbatim copy of a committed file version; blob reachable from origin/main via git rev-list --objects |
| `out/rung4_live_count.json` | 15639 | `77f6228a217d` | NOVEL | commit | result of landed work, not committed by its own session |
| `rung4_live/A1_covex-v6-cf-pd-c5attr_work/traces/seed4_n16_300s_A_r40-40-20_lh_req_ss2_L3_epg_perframe_rq30/trace_meta.json` | 11901 | `ddb9caef947d` | NOVEL | archive | raw output of the D213 CPU-stub rung-4 cell; summary committed separately; preserved rather than deleted because it is a measured run |
| `rung4_live/B1_covex-v6-cf-pd-c5attr_work/traces/seed4_n16_300s_A_r40-40-20_lh_req_ss2_L3_epg_perframe_rq30/trace_meta.json` | 11901 | `ddb9caef947d` | NOVEL | archive | raw output of the D213 CPU-stub rung-4 cell; summary committed separately; preserved rather than deleted because it is a measured run |
| `rung4_live/B1_covex-v6-cf-pd-c5attr/coordinator_result.json` | 8643 | `4be5e12297c6` | NOVEL | archive | raw output of the D213 CPU-stub rung-4 cell; summary committed separately; preserved rather than deleted because it is a measured run |
| `rung4_live/A1_covex-v6-cf-pd-c5attr/coordinator_result.json` | 7894 | `85b863de8ff6` | NOVEL | archive | raw output of the D213 CPU-stub rung-4 cell; summary committed separately; preserved rather than deleted because it is a measured run |
| `rung4_live/B1_covex-v6-cf-pd-c5attr/run_meta.json` | 7702 | `29798b347264` | NOVEL | archive | raw output of the D213 CPU-stub rung-4 cell; summary committed separately; preserved rather than deleted because it is a measured run |
| `rung4_live/A1_covex-v6-cf-pd-c5attr/run_meta.json` | 7701 | `e50de5fdd015` | NOVEL | archive | raw output of the D213 CPU-stub rung-4 cell; summary committed separately; preserved rather than deleted because it is a measured run |
| `rung4_live/A1_covex-v6-cf-pd-c5attr/header.json` | 4970 | `0c098ae5d226` | NOVEL | archive | raw output of the D213 CPU-stub rung-4 cell; summary committed separately; preserved rather than deleted because it is a measured run |
| `rung4_live/B1_covex-v6-cf-pd-c5attr/header.json` | 4970 | `dc344c570aa9` | NOVEL | archive | raw output of the D213 CPU-stub rung-4 cell; summary committed separately; preserved rather than deleted because it is a measured run |
| `rung4_live/A1_covex-v6-cf-pd-c5attr/host_load.jsonl.gz` | 4950 | `62271614d3e5` | NOVEL | archive | raw output of the D213 CPU-stub rung-4 cell; summary committed separately; preserved rather than deleted because it is a measured run |
| `rung4_live/B1_covex-v6-cf-pd-c5attr/host_load.jsonl.gz` | 4861 | `a36238c69c63` | NOVEL | archive | raw output of the D213 CPU-stub rung-4 cell; summary committed separately; preserved rather than deleted because it is a measured run |
| `commit_e1.sh` | 4024 | `22fa33b723a6` | NOVEL | delete | one-shot commit driver script for work that has landed |
| `commit_msg.txt` | 3173 | `30c18df29d20` | NOVEL | delete | commit message already used; the text is preserved in the git log of the landed commit |
| `item3_msg.txt` | 2495 | `54492279c43c` | NOVEL | delete | commit message already used; the text is preserved in the git log of the landed commit |
| `out/digests_PARTIAL_SUPERSEDED.json` | 2130 | `61e0546ffad0` | NOVEL | delete | earlier partial version of a file origin/main committed in a later, larger form under results/orchestration/live2/d213_metrics_scrape/ |
| `corrections_msg.txt` | 2034 | `fc0efe70e9c6` | NOVEL | delete | commit message already used; the text is preserved in the git log of the landed commit |
| `commit_corrections.sh` | 1843 | `359479326264` | NOVEL | delete | one-shot commit driver script for work that has landed |
| `commit_item3.sh` | 1565 | `08f16c37bb96` | NOVEL | delete | one-shot commit driver script for work that has landed |
| `rung4_live/A1_covex-v6-cf-pd-c5attr/frames_preflight.json` | 1460 | `26bf3d73f68f` | NOVEL | archive | raw output of the D213 CPU-stub rung-4 cell; summary committed separately; preserved rather than deleted because it is a measured run |
| `rung4_live/B1_covex-v6-cf-pd-c5attr/frames_preflight.json` | 1460 | `e2353fe71068` | NOVEL | archive | raw output of the D213 CPU-stub rung-4 cell; summary committed separately; preserved rather than deleted because it is a measured run |
| `rung4_live/A1_covex-v6-cf-pd-c5attr/cell.json` | 828 | `14aae99257f3` | NOVEL | archive | raw output of the D213 CPU-stub rung-4 cell; summary committed separately; preserved rather than deleted because it is a measured run |
| `rung4_live/B1_covex-v6-cf-pd-c5attr/cell.json` | 827 | `eacd9fa7e143` | NOVEL | archive | raw output of the D213 CPU-stub rung-4 cell; summary committed separately; preserved rather than deleted because it is a measured run |
| `SCOPED_LIST` | 74 | `0be97db5e112` | NOVEL | delete | ephemeral session marker (pid / base sha / scoped list / git index file); carries no result |
| `ITEM3_BASE_SHA` | 41 | `99f7d5b3e5df` | NOVEL | delete | ephemeral session marker (pid / base sha / scoped list / git index file); carries no result |
| `PATCH_BASE_BLOB` | 41 | `7356237f0f43` | NOVEL | delete | ephemeral session marker (pid / base sha / scoped list / git index file); carries no result |
| `ORIGIN_SHA` | 41 | `99f7d5b3e5df` | NOVEL | delete | ephemeral session marker (pid / base sha / scoped list / git index file); carries no result |
| `ITEM3_DRIVER_PID` | 7 | `2176d9c49fa3` | NOVEL | delete | ephemeral session marker (pid / base sha / scoped list / git index file); carries no result |
| `RUNG4_PID` | 7 | `28b842003303` | NOVEL | delete | ephemeral session marker (pid / base sha / scoped list / git index file); carries no result |
| `DRIVER_PID` | 7 | `55f287791978` | NOVEL | delete | ephemeral session marker (pid / base sha / scoped list / git index file); carries no result |

### `sessA_cs` (2 rows)

| path | size | blob | class | action | reason |
|---|---:|---|---|---|---|
| `idx` | 1831273 | `a113ea81a65a` | NOVEL | delete | ephemeral session marker (pid / base sha / scoped list / git index file); carries no result |
| `m.txt` | 2475 | `57e2fa7faab4` | NOVEL | delete | commit message already used; the text is preserved in the git log of the landed commit |

### `sessA_ver` (3 rows)

| path | size | blob | class | action | reason |
|---|---:|---|---|---|---|
| `idx` | 1832774 | `c9201b75c871` | NOVEL | delete | ephemeral session marker (pid / base sha / scoped list / git index file); carries no result |
| `da_1x.json` | 15967 | `647719e469c7` | NOVEL | commit | result of landed work, not committed by its own session |
| `m.txt` | 2561 | `d8f70e7ec9f4` | NOVEL | delete | commit message already used; the text is preserved in the git log of the landed commit |

## Bulk rows (mechanically verified, aggregated)

The remaining rows are the ones whose verdict is a sha comparison rather than a judgement:
`IDENTICAL_ON_ORIGIN`, `CONTENT_ON_ORIGIN` and `REGENERABLE`. They are aggregated by directory
here; the per-file list with every blob sha is machine-readable at
`/tmp/claude-1001/-home-pragya-Desktop-FM-switching/8ab3f7e8-2a5d-4e65-8ff9-c6ae1f12519b/scratchpad/worktree_cleanup_d228/decided.json` and is regenerated by `/tmp/claude-1001/-home-pragya-Desktop-FM-switching/8ab3f7e8-2a5d-4e65-8ff9-c6ae1f12519b/scratchpad/worktree_cleanup_d228/classify.py`.

| tree | subtree | class | files | MB |
|---|---|---|---:|---:|
| `d213_e1` | `(tree root)` | CONTENT_ON_ORIGIN | 7 | 0.0 |
| `d213_e1` | `out` | CONTENT_ON_ORIGIN | 11 | 0.1 |
| `d213_e1` | `out` | REGENERABLE | 1 | 0.0 |
| `d213_e1` | `shared_results` | IDENTICAL_ON_ORIGIN | 9644 | 3574.6 |
| `d213_e1` | `shared_results` | REGENERABLE | 1 | 0.4 |
| `d213_e1` | `shared_results_i3` | IDENTICAL_ON_ORIGIN | 9917 | 3623.5 |
| `d213_e1` | `shared_results_i3` | REGENERABLE | 1 | 0.5 |
| `n206` | `(tree root)` | IDENTICAL_ON_ORIGIN | 6 | 0.0 |
| `n206` | `cells` | CONTENT_ON_ORIGIN | 2 | 0.0 |
| `n206` | `data` | IDENTICAL_ON_ORIGIN | 5 | 0.0 |
| `n206` | `experiments` | IDENTICAL_ON_ORIGIN | 898 | 13.1 |
| `n206` | `experiments` | REGENERABLE | 127 | 1.7 |
| `n206` | `ops` | IDENTICAL_ON_ORIGIN | 1 | 0.0 |
| `n206` | `plots` | IDENTICAL_ON_ORIGIN | 24 | 0.5 |
| `n206` | `reports` | IDENTICAL_ON_ORIGIN | 250 | 6.9 |
| `n206` | `research` | IDENTICAL_ON_ORIGIN | 19 | 0.3 |
| `n206` | `results` | IDENTICAL_ON_ORIGIN | 7477 | 2286.6 |
| `n206` | `results` | REGENERABLE | 1 | 0.4 |
| `n206` | `simulator` | IDENTICAL_ON_ORIGIN | 71 | 0.4 |
| `sessA_cs` | `(tree root)` | CONTENT_ON_ORIGIN | 1 | 0.0 |
| `sessA_ver` | `(tree root)` | CONTENT_ON_ORIGIN | 1 | 0.0 |

## Trees deliberately NOT touched

| tree | size | why skipped |
|---|---:|---|
| `scratchpad/e1land_6736b0` | 3.6 G | **LIVE RUN.** `d227_e1_metrics_proofs.py` was running under it (pid 523651/523653, `timeout 1800`, cwd and argv both under the tree) when this cleanup started. Not in the task scope and not examined. |
| `scratchpad/d223x` | 12 M | Had live processes shortly before this session and its newest file was written about 14 minutes before the scan began. No process held it at scan time, but D228 (5) clause (f) and the instruction to check by process rather than by name both argue for leaving a just-active tree alone. Not classified. |
| `scratchpad/rung4p1_8ab3f7e8` | 2.7 G | **Claimed by the rung-4 pass-1 build**, which is the policy proof that must run alone (D216). Off limits by instruction; not classified, not touched. |
| `/tmp/claude-1001/mapwt` | - | A real git worktree, about 1,800 commits behind origin, carrying another session's 632 uncommitted lines (`coordinator.py`, `v5/cf_objective.py`, `arms.py`, the D182 deficit-ordering hook). Those are with the user. Not cleaned, not committed, not deleted. |

Box census before the deletions, by process rather than by name (interpreter plus a cwd or argv
path under the repo or a scratchpad tree): no python or conda process held any such path, and no
live2 harness was running, so nothing was yielded to and no wait was needed. loadavg 0.09 / 0.25
/ 0.44 before, recorded again after. No dry cell, digest sweep or one-cell invocation was run by
this task at any point; it is filesystem classification plus git reads plus commits.

## Spot check (D228 (5) clause (c)) - TO BE FILLED BY A DIFFERENT SESSION

A session that did not perform the classification above must check at least 20 rows, including
every `delete` row in the uncommitted-code class, against origin and against this manifest, and
record the result here. The uncommitted-code delete rows are the `DIVERGENT_FROM_ORIGIN` and
`NOVEL` rows listed per file above: 60 and 75 respectively.

_Not yet performed._

