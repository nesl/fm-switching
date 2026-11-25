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

## Second pass: the `mapwt` git worktree (D228 (5), commit authority D166)

Produced 2026-11-24 on flash, by a session that did not do the first pass. This section is
appended; no row above it is altered.

**User tightening that governs this whole section: because the owner of `mapwt` is unknown,
NOTHING in it is classed "abandoned, delete". Not one file. Nothing was deleted, and `mapwt`
itself was NOT removed.**

### What `mapwt` is, and the two sha bases

`/tmp/claude-1001/mapwt` **is** a registered git worktree of this repo (`git worktree list`
reports it; its `.git` file points at `.git/worktrees/mapwt`). Unlike the four plain copies in the
first pass, `git worktree remove` would apply to it.

- `HEAD` = `47237572`, which is **974 commits behind** origin/main and **5 commits ahead of it by
  sha**. It is NOT an ancestor of origin/main.
- Classification base: `acc34010f4432202c3c96924b001b6499bbbe4a9`. origin/main advanced to
  `b79708066fad1a3a49f31f59b0df91f214548241` during the work; **every file was re-classified
  against that tip** and exactly one row changed class (`research/OVERNIGHT_HANDOFF.md`, from
  differs to identical, because a live session landed it mid-task). Both results are recorded
  below.

### The derived file and line counts, which supersede two earlier figures

| quantity | this pass | earlier claim | why the earlier claim differed |
|---|---:|---|---|
| files in the uncommitted set | **171** | 139 | 139 counted `git status` ENTRIES with directories collapsed (140 entries: 17 modified + 123 untracked). Expanding the untracked directories gives 154 untracked files + 17 modified = 171. |
| changed lines | **5,576 vs `mapwt`'s own HEAD** (5,509 insertions + 67 deletions, 17 files) | 5,576 / 139 files | The 5,576 figure is correct **against `mapwt`'s HEAD**, which is 974 commits behind. It is not a measure of unlanded work. |
| lines unique to `mapwt` **vs origin** | **161** at `acc34010`, **163** at the tip, across 5 files | 632 across 3 files | The 632 figure was measured from a handful of files and is superseded, as is any reading of 5,576 as unlanded work. |

### The finding: `mapwt` holds no unlanded work

Classified per file by comparing the git blob sha of the file on disk against origin's blob at the
same path:

| class vs origin | at `acc34010` | at tip `b7970806` |
|---|---:|---:|
| `IDENTICAL_ON_ORIGIN` | 146 | 147 |
| `DIFFERS_FROM_ORIGIN` | 24 | 23 |
| `ABSENT_ON_ORIGIN` | 1 | 1 |
| **total** | **171** | **171** |

**Only one file in `mapwt` is absent from origin**: `d179_proofs.log` (440 bytes), the console log
of a D179 release-recheck proof run, containing a conda failure line and a `STOP:` line. It is
regenerable output, which clause (c) would delete; under the user's tightening it is archived.

**In every one of the differing files, origin carries the LATER form.** Summed over the 23
differing files at the tip: 163 lines exist in `mapwt` and not on origin, against **11,664 lines
that exist on origin and are missing from `mapwt`**. All 163 were read, and each is an earlier
form of a line origin now carries evolved:

| file | lines unique to `mapwt` | what they are, read against origin |
|---|---:|---|
| `v5/cf_objective.py` | 145 | docstring and comment block predating the D177 / D220 (1) / D228 (2) evolution of the objective |
| `coordinator.py` | 11 | the one-argument `_device_answer(o)` form; origin line 671 is `_device_answer(o, ev)` |
| `arms.py` | 2 | `# from arms_v6cf import V6CF_ARMS` **commented out**; origin lines 785-786 have that wiring live |
| `hybrid/hybrid_arm.py` | 2 | the hard-coded `CONTEXT_LIMIT_TOKENS = 32768`; origin line 422 reads `CL.limit_tokens()` per **D223 (2)** |
| `research/EXPERIMENTS.md` | 1 | an earlier draft of the StudyD226 row; origin's row is the later "rowless rule amended" form |
| `results/INDEX.md` | 1 | an earlier draft of the `d226_rescore` row; all three `d226_rescore` outputs are committed on origin |
| `research/STATUS.md` | 1 | a superseded "Last updated" header paragraph |

**Consequence, and the reason nothing was committed: committing any of these 23 files would
REVERT landed work.** `hybrid_arm.py` would undo D223 (2); `arms.py` would re-comment the v6cf
wiring; `coordinator.py` would regress `_device_answer` to its one-argument form. D228 (5) clause
(c) directs that uncommitted code belonging to landed work be committed; here the content *matches
landed work by having been superseded by it*, so the correct action under that clause is no commit
at all.

### The 5 commits ahead of origin by sha: content all landed

`acc34010..HEAD` is five commits (`f6021b61`, `ef48f61c`, `f3482026`, `d9f61a2c`, `47237572`) -
StudyC5-ATTR and the D179 share-admission interface and allocator body. They touch 21 paths.
**Every file those commits CREATED is byte-identical on origin**: `arms_v6c5.py`,
`c5attr_digest_proofs.py`, `c5attr_one_cell.py`, `c5attr_replay_proofs.py`,
`c5attr_trip_attribution.py`, `research/prereg_c5_engine_flag.md`, `reports/study_c5_candidates.md`,
`c5attr_digest_proofs.json`, `c5attr_replay_proofs.json`, `c5attr_trip_attribution.json`,
`v6_harness_name_proof.json`. The other 10 are shared files origin has evolved further.
`share_admission.py`, the subject of three of the five commits, is byte-identical to origin at
working-tree level, so the D179 allocator work landed in full. The five commits were re-landed on
origin under different shas; none of their content is lost.

Two files the first pass flagged by name are byte-identical to origin and need no action:
`dashcam_ontime_reconcile.py` (blob `af4efdcd`, the feared +687/-19) and
`research/policy_design_log.md` (the requesting session's D220-to-D228 staging copy, all landed).

### Census by process, not by name or size

Enumerated `/proc/<pid>/cwd`, `/proc/<pid>/cmdline` and every `/proc/<pid>/fd/*` for paths under
`/tmp/claude-1001/mapwt`.

**`mapwt` is ACTIVE and was NOT removed.** Findings, in order:

- At the first census no process held it by cwd or fd. The only argv matches were a
  `tmux`/`claude` **prompt string** for the watchdog-restarted `fmsw-overnight` session, which
  instructs that session to "check for uncommitted edits in the shared worktree at
  /tmp/claude-1001/mapwt" - a name match, not a holder, and exactly the kind of match this clause
  exists to distinguish.
- Files inside `mapwt` were nevertheless written at 10:00, 10:12, 10:20, 10:21 and 10:31 PST, with
  separate inodes from the main checkout, so the writes are genuinely into this tree.
- At the re-census immediately before the copy, **pid 588984 held `/tmp/claude-1001/mapwt` as its
  cwd**, and `research/OVERNIGHT_HANDOFF.md` had been written again. The pid had exited before it
  could be identified, so it was a transient shell spawned by a live session.
- `ops/watchdog.log` shows the `fmsw-overnight` session restarted on a 10-to-20-minute cadence
  (5 restarts in the logged window), each restart carrying the prompt above.

Because a live session is touching this tree, the archive was taken (a read-only copy cannot
disturb it) and **removal was deliberately not attempted**. No cells, no sweeps, no dry runs, no
digest invocations were performed by this task; it is filesystem classification plus git reads.

### Archive (clause c, under the user's tightening: everything not committed)

Archive directory: **`/home/pragya/fm_archive/2026-11-24/mapwt/`**, beside the first pass's trees
on the same volume. Relative paths preserved. **Never delete.**

Because nothing was committed, "everything else" is the whole uncommitted set: **all 171 files**,
including the 147 already byte-identical to origin. They are archived not because they are at risk
but because the tightening forbids classing anything here as deletable while the owner is unknown.

**Verification, recorded as the user required before any removal:**

| check | value |
|---|---|
| files copied | 171 |
| files present in archive (`find -type f`) | **171** |
| per-file `cmp` against source | 171 of 171 identical, 0 mismatches |
| modified during the copy (sha256 + mtime before vs after) | **0 of 171** |
| archive tree sha256, content only | `e1e43215c7bdb0b04ced7179ff86696b200b58e4e025b29daf630b6a803d8245` |
| archive tree sha256, sorted paths plus content | `681112346dd7afb178cd419b55137b496ece46d15397aaa63091121cb28af411` |
| archive size | 9.9 MB |

The tree sha256 is computed as `find . -type f -print0 \| sort -z \| xargs -0 sha256sum` over the
archive, then sha256 of that listing (content-only variant: sha256 of the hash column alone).

**`mapwt` has NOT been removed and NOTHING has been deleted.** Removal is left for the user to
confirm, per their instruction to archive, verify and stop. When it is confirmed, `mapwt` is a
registered worktree, so `git worktree remove` (not `rm -rf`) is the correct command, and the live
session writing into it must be quiesced first.

### Per-file rows, with the D-row or study each appears to belong to

Attribution is by path and filename against the D-row index, and is offered so the **user** can
decide; it is not a judgement that the file is or is not wanted. All 171 rows are listed.

| archived path | size | class vs origin | appears to belong to | reason |
|---|---:|---|---|---|
| `/home/pragya/fm_archive/2026-11-24/mapwt/d179_proofs.log` | 440 | ABSENT_ON_ORIGIN | D179 (share admission floors, release recheck, rung-2 verdict) | no such path on origin/main; regenerable console log of a proof run, preserved rather than deleted under the user's tightening |
| `/home/pragya/fm_archive/2026-11-24/mapwt/experiments/analysis/episodic/build_episodic.py` | 16234 | IDENTICAL_ON_ORIGIN | episodic scores build (D85 / D87 offline scoring) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/experiments/orchestration/live2/arms.py` | 45775 | DIFFERS_FROM_ORIGIN | live2 arm registry, shared live-path file; mapwt copy has the v6cf wiring COMMENTED OUT, origin has it live | differs from origin/main at the same path, and in EVERY case origin carries the LATER form (mapwt is 974 commits behind); committing it would revert landed work, so it is archived, not committed |
| `/home/pragya/fm_archive/2026-11-24/mapwt/experiments/orchestration/live2/arms_v6cf.py` | 34946 | DIFFERS_FROM_ORIGIN | cf-protect-defer arm family (D187 cf-pd; D228 (2) margin MARGIN_CF) | differs from origin/main at the same path, and in EVERY case origin carries the LATER form (mapwt is 974 commits behind); committing it would revert landed work, so it is archived, not committed |
| `/home/pragya/fm_archive/2026-11-24/mapwt/experiments/orchestration/live2/arms_v6fairfeed.py` | 24985 | IDENTICAL_ON_ORIGIN | D178 (deficit feed / fair feed) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/experiments/orchestration/live2/arms_v6shares.py` | 9070 | IDENTICAL_ON_ORIGIN | D179 (share admission and capacity) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/experiments/orchestration/live2/baseline_matrix_table.py` | 72472 | IDENTICAL_ON_ORIGIN | D225 (conformance / baseline matrix table) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/experiments/orchestration/live2/cf_pd_one_cell.py` | 9714 | IDENTICAL_ON_ORIGIN | cf-protect-defer arm family (D187 cf-pd; D228 (2) margin MARGIN_CF) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/experiments/orchestration/live2/cf_pd_proofs.py` | 24853 | IDENTICAL_ON_ORIGIN | cf-protect-defer arm family (D187 cf-pd; D228 (2) margin MARGIN_CF) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/experiments/orchestration/live2/cf_pd_tests.py` | 18179 | IDENTICAL_ON_ORIGIN | cf-protect-defer arm family (D187 cf-pd; D228 (2) margin MARGIN_CF) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/experiments/orchestration/live2/cf_protect_defer.py` | 36246 | DIFFERS_FROM_ORIGIN | cf-protect-defer arm family (D187 cf-pd; D228 (2) margin MARGIN_CF) | differs from origin/main at the same path, and in EVERY case origin carries the LATER form (mapwt is 974 commits behind); committing it would revert landed work, so it is archived, not committed |
| `/home/pragya/fm_archive/2026-11-24/mapwt/experiments/orchestration/live2/coordinator.py` | 138920 | DIFFERS_FROM_ORIGIN | live2 coordinator, shared live-path file (many D-rows); mapwt copy predates origin | differs from origin/main at the same path, and in EVERY case origin carries the LATER form (mapwt is 974 commits behind); committing it would revert landed work, so it is archived, not committed |
| `/home/pragya/fm_archive/2026-11-24/mapwt/experiments/orchestration/live2/d178_deficit_feed_proofs.py` | 21711 | IDENTICAL_ON_ORIGIN | D178 (deficit feed, fair-feed weight band) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/experiments/orchestration/live2/d178_deficit_feed_trace.py` | 13616 | IDENTICAL_ON_ORIGIN | D178 (deficit feed, fair-feed weight band) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/experiments/orchestration/live2/d178_fairfeed_name_proof.py` | 7485 | IDENTICAL_ON_ORIGIN | D178 (deficit feed, fair-feed weight band) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/experiments/orchestration/live2/d178_weight_band.py` | 10489 | IDENTICAL_ON_ORIGIN | D178 (deficit feed, fair-feed weight band) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/experiments/orchestration/live2/d179_release_recheck_proofs.py` | 10089 | IDENTICAL_ON_ORIGIN | D179 (share admission floors, release recheck, rung-2 verdict) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/experiments/orchestration/live2/d179_release_recheck_trace.py` | 7827 | IDENTICAL_ON_ORIGIN | D179 (share admission floors, release recheck, rung-2 verdict) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/experiments/orchestration/live2/d179_rung2_verdict.py` | 66155 | DIFFERS_FROM_ORIGIN | D179 (share admission floors, release recheck, rung-2 verdict) | differs from origin/main at the same path, and in EVERY case origin carries the LATER form (mapwt is 974 commits behind); committing it would revert landed work, so it is archived, not committed |
| `/home/pragya/fm_archive/2026-11-24/mapwt/experiments/orchestration/live2/d179_share_tests.py` | 44588 | DIFFERS_FROM_ORIGIN | D179 (share admission floors, release recheck, rung-2 verdict) | differs from origin/main at the same path, and in EVERY case origin carries the LATER form (mapwt is 974 commits behind); committing it would revert landed work, so it is archived, not committed |
| `/home/pragya/fm_archive/2026-11-24/mapwt/experiments/orchestration/live2/d191_fleet_eligibility.py` | 1686 | IDENTICAL_ON_ORIGIN | D191 (fleet eligibility, deadline-25 confounds, KV flow rate) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/experiments/orchestration/live2/d200_fair_counter_probe.py` | 1450 | IDENTICAL_ON_ORIGIN | D200 (gate-A safety, one-deficit-weight, R3 planner weight probe) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/experiments/orchestration/live2/d200_gatea_safety.py` | 13805 | DIFFERS_FROM_ORIGIN | D200 (gate-A safety, one-deficit-weight, R3 planner weight probe) | differs from origin/main at the same path, and in EVERY case origin carries the LATER form (mapwt is 974 commits behind); committing it would revert landed work, so it is archived, not committed |
| `/home/pragya/fm_archive/2026-11-24/mapwt/experiments/orchestration/live2/d200_r3_planner_weight_probe.py` | 5392 | IDENTICAL_ON_ORIGIN | D200 (gate-A safety, one-deficit-weight, R3 planner weight probe) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/experiments/orchestration/live2/d206_c2_chain.sh` | 1348 | IDENTICAL_ON_ORIGIN | D206 (C2 chain) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/experiments/orchestration/live2/d208_ladder_chain.sh` | 1272 | IDENTICAL_ON_ORIGIN | D208 (final ladder, rung-4 mechanism convergence, proof A) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/experiments/orchestration/live2/d208_score_proof_a.py` | 3260 | IDENTICAL_ON_ORIGIN | D208 (final ladder, rung-4 mechanism convergence, proof A) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/experiments/orchestration/live2/d213_patch_asyncbackend.py` | 20406 | IDENTICAL_ON_ORIGIN | D213 (metrics scrape, asyncbackend patch) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/experiments/orchestration/live2/dashcam_deadline_release_estimate.py` | 66243 | IDENTICAL_ON_ORIGIN | E1 dashcam deadline-release estimate | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/experiments/orchestration/live2/dashcam_ontime_reconcile.py` | 91188 | IDENTICAL_ON_ORIGIN | E1 dashcam on-time reconcile (D176 robot headline) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/experiments/orchestration/live2/deficit_feed.py` | 21433 | IDENTICAL_ON_ORIGIN | D178 (deficit feed / fair feed) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/experiments/orchestration/live2/deficit_gain_d178.py` | 9899 | IDENTICAL_ON_ORIGIN | D178 (deficit feed, fair-feed weight band) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/experiments/orchestration/live2/held/d218_device_answers/README.md` | 4113 | IDENTICAL_ON_ORIGIN | D218 (DEVICE_ANSWERS rule) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/experiments/orchestration/live2/hybrid/hybrid_arm.py` | 54540 | DIFFERS_FROM_ORIGIN | D223 (2) (context limit) - mapwt copy is the PRE-D223(2) hard-coded 32,768 form | differs from origin/main at the same path, and in EVERY case origin carries the LATER form (mapwt is 974 commits behind); committing it would revert landed work, so it is archived, not committed |
| `/home/pragya/fm_archive/2026-11-24/mapwt/experiments/orchestration/live2/release_recheck.py` | 12004 | DIFFERS_FROM_ORIGIN | D179 / D190 / D196 (release recheck) | differs from origin/main at the same path, and in EVERY case origin carries the LATER form (mapwt is 974 commits behind); committing it would revert landed work, so it is archived, not committed |
| `/home/pragya/fm_archive/2026-11-24/mapwt/experiments/orchestration/live2/share_admission.py` | 14830 | IDENTICAL_ON_ORIGIN | D179 (share admission and capacity) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/experiments/orchestration/live2/share_capacity.py` | 6534 | IDENTICAL_ON_ORIGIN | D179 (share admission and capacity) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/experiments/orchestration/live2/tests/test_deficit_feed.py` | 18082 | IDENTICAL_ON_ORIGIN | D178 (deficit feed / fair feed) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/experiments/orchestration/live2/tests/test_release_recheck.py` | 23886 | IDENTICAL_ON_ORIGIN | D179 / D190 / D196 (release recheck) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/experiments/orchestration/live2/v5/cf_objective.py` | 33621 | DIFFERS_FROM_ORIGIN | D177 / D220 (1) / D228 (2) (cf objective, on-time units, gain weighting withdrawn) | differs from origin/main at the same path, and in EVERY case origin carries the LATER form (mapwt is 974 commits behind); committing it would revert landed work, so it is archived, not committed |
| `/home/pragya/fm_archive/2026-11-24/mapwt/experiments/orchestration/live2/v6_harness_name_proof.py` | 5792 | IDENTICAL_ON_ORIGIN | harness arm-name proofs (D178 / D179 naming gates) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/experiments/orchestration/live2/v6shares_name_proof.py` | 8958 | IDENTICAL_ON_ORIGIN | D179 (share admission and capacity) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/experiments/orchestration/study_live2_pilot.py` | 21168 | IDENTICAL_ON_ORIGIN | live2 pilot driver, shared live-path file | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/reports/MORNING_SUMMARY_2026-11-23.md` | 25058 | IDENTICAL_ON_ORIGIN | session handoff bookkeeping (not a D-row deliverable) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/reports/OVERNIGHT_DECISIONS.md` | 34227 | IDENTICAL_ON_ORIGIN | session handoff bookkeeping (not a D-row deliverable) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/reports/figures/episodic_scores_README.md` | 7085 | DIFFERS_FROM_ORIGIN | episodic scores build (D85 / D87 offline scoring) | differs from origin/main at the same path, and in EVERY case origin carries the LATER form (mapwt is 974 commits behind); committing it would revert landed work, so it is archived, not committed |
| `/home/pragya/fm_archive/2026-11-24/mapwt/reports/prereg_cold_pricing_r1.md` | 5942 | IDENTICAL_ON_ORIGIN | pre-registration document (see its own header for the D-row) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/reports/prereg_queue_register_r2.md` | 5440 | IDENTICAL_ON_ORIGIN | pre-registration document (see its own header for the D-row) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/reports/study_c5_selection_rule.md` | 5004 | IDENTICAL_ON_ORIGIN | StudyC5-ATTR (C5 attribution candidate; D179/D185 gate) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/reports/study_d179_rung2_verdict.md` | 23280 | IDENTICAL_ON_ORIGIN | D179 (share admission floors, release recheck, rung-2 verdict) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/reports/study_d185_rung3_verdict.md` | 5668 | IDENTICAL_ON_ORIGIN | D185 (rung-3 verdict, fair C5-attr gate) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/reports/study_d209_placeholder_fixes.md` | 87453 | IDENTICAL_ON_ORIGIN | D209 (placeholder fixes) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/reports/study_d218_device_answers.md` | 46319 | IDENTICAL_ON_ORIGIN | D218 (DEVICE_ANSWERS rule) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/reports/study_e1_nexar_lead.md` | 34485 | IDENTICAL_ON_ORIGIN | E1 (Nexar lead study) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/research/EXPERIMENTS.md` | 1314400 | DIFFERS_FROM_ORIGIN | repo bookkeeping (STATUS / EXPERIMENTS / INDEX) | differs from origin/main at the same path, and in EVERY case origin carries the LATER form (mapwt is 974 commits behind); committing it would revert landed work, so it is archived, not committed |
| `/home/pragya/fm_archive/2026-11-24/mapwt/research/OVERNIGHT_HANDOFF.md` | 133495 | DIFFERS_FROM_ORIGIN | session handoff bookkeeping (not a D-row deliverable) | differs from origin/main at the same path, and in EVERY case origin carries the LATER form (mapwt is 974 commits behind); committing it would revert landed work, so it is archived, not committed |
| `/home/pragya/fm_archive/2026-11-24/mapwt/research/STATUS.md` | 190366 | DIFFERS_FROM_ORIGIN | repo bookkeeping (STATUS / EXPERIMENTS / INDEX) | differs from origin/main at the same path, and in EVERY case origin carries the LATER form (mapwt is 974 commits behind); committing it would revert landed work, so it is archived, not committed |
| `/home/pragya/fm_archive/2026-11-24/mapwt/research/policy_design_log.md` | 223067 | IDENTICAL_ON_ORIGIN | D220 to D228 appends; this is the requesting session's STAGING COPY and it is byte-identical to origin, so all of it landed | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/INDEX.md` | 559922 | DIFFERS_FROM_ORIGIN | repo bookkeeping (STATUS / EXPERIMENTS / INDEX) | differs from origin/main at the same path, and in EVERY case origin carries the LATER form (mapwt is 974 commits behind); committing it would revert landed work, so it is archived, not committed |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/d200_one_deficit_weight/EXPERIMENTS_row_draft.md` | 5744 | DIFFERS_FROM_ORIGIN | D200 (gate-A safety, one-deficit-weight, R3 planner weight probe) | differs from origin/main at the same path, and in EVERY case origin carries the LATER form (mapwt is 974 commits behind); committing it would revert landed work, so it is archived, not committed |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/d200_one_deficit_weight/base.json` | 854 | IDENTICAL_ON_ORIGIN | D200 (gate-A safety, one-deficit-weight, R3 planner weight probe) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/d200_one_deficit_weight/build_plan_1a_1b.json` | 7718 | IDENTICAL_ON_ORIGIN | D200 (gate-A safety, one-deficit-weight, R3 planner weight probe) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/d200_one_deficit_weight/d200_fair_counter_probe.json` | 712 | IDENTICAL_ON_ORIGIN | D200 (gate-A safety, one-deficit-weight, R3 planner weight probe) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/d200_one_deficit_weight/r3.json` | 860 | IDENTICAL_ON_ORIGIN | D200 (gate-A safety, one-deficit-weight, R3 planner weight probe) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/d200_one_deficit_weight/r4.json` | 9021 | IDENTICAL_ON_ORIGIN | D200 (gate-A safety, one-deficit-weight, R3 planner weight probe) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/d200_one_deficit_weight/r4.rd.json` | 80144 | IDENTICAL_ON_ORIGIN | D200 (gate-A safety, one-deficit-weight, R3 planner weight probe) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/d213_metrics_scrape/item3_belief_prefix_byte_identity.json` | 5152 | IDENTICAL_ON_ORIGIN | D213 (metrics scrape, asyncbackend patch) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/d213_metrics_scrape/item3_digests_RAW.json` | 169880 | IDENTICAL_ON_ORIGIN | D213 (metrics scrape, asyncbackend patch) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/d216_final_kv025/d216_digest_crosscheck_0ce3c2.json` | 7140 | IDENTICAL_ON_ORIGIN | D216 (final KV 0.25x) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/d218_device_answers/d218_device_answers_prereg.json` | 9433 | IDENTICAL_ON_ORIGIN | D218 (DEVICE_ANSWERS rule) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/d218_device_answers/d218_prereg.json` | 14433 | IDENTICAL_ON_ORIGIN | D218 (DEVICE_ANSWERS rule) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/d218_device_answers/d218_prereg_addendum.json` | 5769 | IDENTICAL_ON_ORIGIN | D218 (DEVICE_ANSWERS rule) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/d223_byte_identity_1x.json` | 47047 | IDENTICAL_ON_ORIGIN | D223 (2) (configured max-model-len replaces hard-coded 32,768 context limit) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/c5_item_c_repriced.json` | 7100 | IDENTICAL_ON_ORIGIN | StudyC5-ATTR (C5 attribution candidate; D179/D185 gate) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/cf_pd_mechanism_tests.json` | 15312 | DIFFERS_FROM_ORIGIN | cf-protect-defer arm family (D187 cf-pd; D228 (2) margin MARGIN_CF) | differs from origin/main at the same path, and in EVERY case origin carries the LATER form (mapwt is 974 commits behind); committing it would revert landed work, so it is archived, not committed |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/cf_pd_proofs.json` | 69395 | IDENTICAL_ON_ORIGIN | cf-protect-defer arm family (D187 cf-pd; D228 (2) margin MARGIN_CF) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/d178_deficit_feed_proofs.json` | 21623 | IDENTICAL_ON_ORIGIN | D178 (deficit feed, fair-feed weight band) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/d178_deficit_feed_trace.json` | 41427 | IDENTICAL_ON_ORIGIN | D178 (deficit feed, fair-feed weight band) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/d178_fairfeed_name_proof.json` | 3858 | IDENTICAL_ON_ORIGIN | D178 (deficit feed, fair-feed weight band) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/d178_weight_band.json` | 4074 | IDENTICAL_ON_ORIGIN | D178 (deficit feed, fair-feed weight band) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/d179_absolute_fallback_mislabel.json` | 2307 | IDENTICAL_ON_ORIGIN | D179 (share admission floors, release recheck, rung-2 verdict) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/d179_dry_s4_report.json` | 4988 | DIFFERS_FROM_ORIGIN | D179 (share admission floors, release recheck, rung-2 verdict) | differs from origin/main at the same path, and in EVERY case origin carries the LATER form (mapwt is 974 commits behind); committing it would revert landed work, so it is archived, not committed |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/d179_overrun_without_recall.json` | 4743 | IDENTICAL_ON_ORIGIN | D179 (share admission floors, release recheck, rung-2 verdict) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/d179_release_recheck_proofs.json` | 4197 | IDENTICAL_ON_ORIGIN | D179 (share admission floors, release recheck, rung-2 verdict) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/d179_release_recheck_trace.json` | 5783 | IDENTICAL_ON_ORIGIN | D179 (share admission floors, release recheck, rung-2 verdict) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/d179_rung2_verdict_prereg.json` | 44550 | IDENTICAL_ON_ORIGIN | D179 (share admission floors, release recheck, rung-2 verdict) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/d179_share_admission_proofs.json` | 9140 | IDENTICAL_ON_ORIGIN | D179 (share admission floors, release recheck, rung-2 verdict) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/d179_share_tests.json` | 13059 | DIFFERS_FROM_ORIGIN | D179 (share admission floors, release recheck, rung-2 verdict) | differs from origin/main at the same path, and in EVERY case origin carries the LATER form (mapwt is 974 commits behind); committing it would revert landed work, so it is archived, not committed |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/d179_uncached_register_proofs.json` | 4786 | IDENTICAL_ON_ORIGIN | D179 (share admission floors, release recheck, rung-2 verdict) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/d181_share_floors.json` | 3040 | IDENTICAL_ON_ORIGIN | D181 (share floors) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/d185_fair_c5attr_gate.json` | 5467 | IDENTICAL_ON_ORIGIN | D185 (rung-3 verdict, fair C5-attr gate) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/d185_rung3_verdict.json` | 181243 | IDENTICAL_ON_ORIGIN | D185 (rung-3 verdict, fair C5-attr gate) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/d187_cfpd_c5attr_proofs.json` | 8857 | IDENTICAL_ON_ORIGIN | D187 (R1 cold pricing, R2 queue register, cf-pd C5-attr proofs) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/d187_r1_proofs.json` | 7009 | IDENTICAL_ON_ORIGIN | D187 (R1 cold pricing, R2 queue register, cf-pd C5-attr proofs) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/d187_r1_residual_diagnosis.json` | 6111 | IDENTICAL_ON_ORIGIN | D187 (R1 cold pricing, R2 queue register, cf-pd C5-attr proofs) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/d187_r2_proofs.json` | 4350 | IDENTICAL_ON_ORIGIN | D187 (R1 cold pricing, R2 queue register, cf-pd C5-attr proofs) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/d189_kv05_logical_only.json` | 2112 | IDENTICAL_ON_ORIGIN | D189 (reduced-KV / LMCache s4 recovery) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/d189_lmcache_s4_recovered_digest.json` | 3579 | IDENTICAL_ON_ORIGIN | D189 (reduced-KV / LMCache s4 recovery) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/d189_real_kv025_985_proof.json` | 8030 | IDENTICAL_ON_ORIGIN | D189 (reduced-KV / LMCache s4 recovery) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/d189_real_kv025_launcher_proof.json` | 3854 | IDENTICAL_ON_ORIGIN | D189 (reduced-KV / LMCache s4 recovery) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/d189_reduced_kv_context_rejections.json` | 8027 | IDENTICAL_ON_ORIGIN | D189 (reduced-KV / LMCache s4 recovery) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/d190_rr_proofs.json` | 15224 | IDENTICAL_ON_ORIGIN | D190 (release-recheck proofs) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/d191_deadline25_confounds.json` | 4179 | IDENTICAL_ON_ORIGIN | D191 (fleet eligibility, deadline-25 confounds, KV flow rate) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/d191_fleet_eligibility.json` | 1779 | IDENTICAL_ON_ORIGIN | D191 (fleet eligibility, deadline-25 confounds, KV flow rate) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/d196_rr_four_seed_verdict.json` | 2493 | IDENTICAL_ON_ORIGIN | D196 (release-recheck four-seed verdict) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/d196_rr_s4_verdict.json` | 41401 | IDENTICAL_ON_ORIGIN | D196 (release-recheck four-seed verdict) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/d196_rr_s5_verdict.json` | 41476 | IDENTICAL_ON_ORIGIN | D196 (release-recheck four-seed verdict) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/d196_rr_s6_verdict.json` | 43445 | IDENTICAL_ON_ORIGIN | D196 (release-recheck four-seed verdict) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/d196_rr_s7_verdict.json` | 42337 | IDENTICAL_ON_ORIGIN | D196 (release-recheck four-seed verdict) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/d200_gatea_prereg.json` | 8456 | IDENTICAL_ON_ORIGIN | D200 (gate-A safety, one-deficit-weight, R3 planner weight probe) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/d200_gatea_safety.json` | 113296 | DIFFERS_FROM_ORIGIN | D200 (gate-A safety, one-deficit-weight, R3 planner weight probe) | differs from origin/main at the same path, and in EVERY case origin carries the LATER form (mapwt is 974 commits behind); committing it would revert landed work, so it is archived, not committed |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/d200_r3_planner_weight_probe.json` | 2504 | IDENTICAL_ON_ORIGIN | D200 (gate-A safety, one-deficit-weight, R3 planner weight probe) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/d208_LADDER_FINAL_COMPLETE.json` | 15238 | IDENTICAL_ON_ORIGIN | D208 (final ladder, rung-4 mechanism convergence, proof A) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/d208_fair_final_s4_verdict.json` | 44155 | IDENTICAL_ON_ORIGIN | D208 (final ladder, rung-4 mechanism convergence, proof A) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/d208_fair_final_s4_verdict_COMPLETE.json` | 41066 | IDENTICAL_ON_ORIGIN | D208 (final ladder, rung-4 mechanism convergence, proof A) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/d208_fair_final_s5_s6_verdict.json` | 24631 | IDENTICAL_ON_ORIGIN | D208 (final ladder, rung-4 mechanism convergence, proof A) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/d208_fair_final_s5_verdict.json` | 43781 | IDENTICAL_ON_ORIGIN | D208 (final ladder, rung-4 mechanism convergence, proof A) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/d208_final_s4_verdict.json` | 46588 | IDENTICAL_ON_ORIGIN | D208 (final ladder, rung-4 mechanism convergence, proof A) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/d208_final_s5_verdict.json` | 49859 | IDENTICAL_ON_ORIGIN | D208 (final ladder, rung-4 mechanism convergence, proof A) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/d208_final_s6_verdict.json` | 46432 | IDENTICAL_ON_ORIGIN | D208 (final ladder, rung-4 mechanism convergence, proof A) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/d208_final_s7_verdict.json` | 46772 | IDENTICAL_ON_ORIGIN | D208 (final ladder, rung-4 mechanism convergence, proof A) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/d208_rung4_mechanism_convergence.json` | 18541 | IDENTICAL_ON_ORIGIN | D208 (final ladder, rung-4 mechanism convergence, proof A) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/d223_context_limit_offered.json` | 4491 | IDENTICAL_ON_ORIGIN | D223 (2) (configured max-model-len replaces hard-coded 32,768 context limit) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/d226_missing_r10175_adjudication.json` | 4133 | IDENTICAL_ON_ORIGIN | D226 (missing r10175 adjudication) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/dashcam_deadline_release_estimate.json` | 179465 | IDENTICAL_ON_ORIGIN | E1 dashcam deadline-release estimate | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/dashcam_ontime_reconcile.json` | 233202 | IDENTICAL_ON_ORIGIN | E1 dashcam on-time reconcile (D176 robot headline) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/oversized_logs_manifest.jsonl` | 9791 | DIFFERS_FROM_ORIGIN | live2 logging bookkeeping | differs from origin/main at the same path, and in EVERY case origin carries the LATER form (mapwt is 974 commits behind); committing it would revert landed work, so it is archived, not committed |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/runs/C5DIAG_CELLS` | 13796 | IDENTICAL_ON_ORIGIN | StudyC5-ATTR (C5 attribution candidate; D179/D185 gate) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/runs/DEADLINE25_CELLS` | 1983 | IDENTICAL_ON_ORIGIN | live2 frozen-test cell roster (see the roster name for its rung) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/runs/DEVWAIT_READY` | 4497 | IDENTICAL_ON_ORIGIN | live2 frozen-test cell roster (see the roster name for its rung) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/runs/FINAL_LADDER_CELLS_S5_S7` | 3019 | IDENTICAL_ON_ORIGIN | live2 frozen-test cell roster (see the roster name for its rung) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/runs/KV025_CELLS` | 20371 | IDENTICAL_ON_ORIGIN | D189 / D216 (reduced-KV cells) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/runs/KV025_RUNGS_CELLS` | 2995 | IDENTICAL_ON_ORIGIN | D189 / D216 (reduced-KV cells) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/runs/LOAD1220_CELLS` | 2556 | IDENTICAL_ON_ORIGIN | live2 frozen-test cell roster (see the roster name for its rung) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/runs/RUNG3_KV05R_CELLS` | 8459 | IDENTICAL_ON_ORIGIN | D189 / D216 (reduced-KV cells) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/runs/V6CFPD_CELLS` | 5348 | IDENTICAL_ON_ORIGIN | cf-protect-defer arm family (D187 cf-pd; D228 (2) margin MARGIN_CF) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/runs/V6RR_CELLS` | 2483 | IDENTICAL_ON_ORIGIN | live2 frozen-test cell roster (see the roster name for its rung) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/runs/V6SHARES_R1_CELLS` | 3392 | IDENTICAL_ON_ORIGIN | D179 (share admission and capacity) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/runs/V6SHARES_R2_CELLS` | 3774 | IDENTICAL_ON_ORIGIN | D179 (share admission and capacity) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/traces/d192_device_scores_provenance.json` | 4943 | IDENTICAL_ON_ORIGIN | D192 (device scores provenance) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/traces/seed4_n16_1200s_A_r40-40-20_lh_req_ss2_L3_epg_perframe_rq30/dashcam_instants.jsonl.gz` | 535220 | IDENTICAL_ON_ORIGIN | D196 / D208 ladder seed traces (seeds 4-7, 1200s cells) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/traces/seed4_n16_1200s_A_r40-40-20_lh_req_ss2_L3_epg_perframe_rq30/device_answers.jsonl.gz` | 403848 | IDENTICAL_ON_ORIGIN | D196 / D208 ladder seed traces (seeds 4-7, 1200s cells) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/traces/seed5_n16_1200s_A_r40-40-20_lh_req_ss2_L3_epg_perframe_rq30/dashcam_instants.jsonl.gz` | 535666 | IDENTICAL_ON_ORIGIN | D196 / D208 ladder seed traces (seeds 4-7, 1200s cells) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/traces/seed5_n16_1200s_A_r40-40-20_lh_req_ss2_L3_epg_perframe_rq30/device_answers.jsonl.gz` | 404341 | IDENTICAL_ON_ORIGIN | D196 / D208 ladder seed traces (seeds 4-7, 1200s cells) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/traces/seed6_n16_1200s_A_r40-40-20_lh_req_ss2_L3_epg_perframe_rq30/dashcam_instants.jsonl.gz` | 536288 | IDENTICAL_ON_ORIGIN | D196 / D208 ladder seed traces (seeds 4-7, 1200s cells) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/traces/seed6_n16_1200s_A_r40-40-20_lh_req_ss2_L3_epg_perframe_rq30/device_answers.jsonl.gz` | 404763 | IDENTICAL_ON_ORIGIN | D196 / D208 ladder seed traces (seeds 4-7, 1200s cells) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/traces/seed7_n16_1200s_A_r40-40-20_lh_req_ss2_L3_epg_perframe_rq30/dashcam_instants.jsonl.gz` | 535515 | IDENTICAL_ON_ORIGIN | D196 / D208 ladder seed traces (seeds 4-7, 1200s cells) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/traces/seed7_n16_1200s_A_r40-40-20_lh_req_ss2_L3_epg_perframe_rq30/device_answers.jsonl.gz` | 403867 | IDENTICAL_ON_ORIGIN | D196 / D208 ladder seed traces (seeds 4-7, 1200s cells) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/frozen_test/v6shares_name_proof.json` | 3695 | IDENTICAL_ON_ORIGIN | D179 (share admission and capacity) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/kv_prefetch/d191_kvflow_live_rate_note.json` | 5615 | IDENTICAL_ON_ORIGIN | D191 (fleet eligibility, deadline-25 confounds, KV flow rate) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/ladder_final/cells/A_base.err` | 0 | IDENTICAL_ON_ORIGIN | D208 (final ladder cells and proofs) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/ladder_final/cells/A_base.json` | 854 | IDENTICAL_ON_ORIGIN | D208 (final ladder cells and proofs) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/ladder_final/cells/A_base.rows.json.gz` | 100011 | IDENTICAL_ON_ORIGIN | D208 (final ladder cells and proofs) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/ladder_final/cells/A_rules.err` | 0 | IDENTICAL_ON_ORIGIN | D208 (final ladder cells and proofs) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/ladder_final/cells/A_rules.json` | 853 | IDENTICAL_ON_ORIGIN | D208 (final ladder cells and proofs) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/ladder_final/cells/A_rules.rows.json.gz` | 109474 | IDENTICAL_ON_ORIGIN | D208 (final ladder cells and proofs) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/ladder_final/cells/a_always-cloud-fcfs.err` | 0 | IDENTICAL_ON_ORIGIN | D208 (final ladder cells and proofs) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/ladder_final/cells/a_always-cloud-fcfs.json` | 856 | IDENTICAL_ON_ORIGIN | D208 (final ladder cells and proofs) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/ladder_final/cells/a_b7-edf-feasibility.err` | 0 | IDENTICAL_ON_ORIGIN | D208 (final ladder cells and proofs) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/ladder_final/cells/a_b7-edf-feasibility.json` | 857 | IDENTICAL_ON_ORIGIN | D208 (final ladder cells and proofs) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/ladder_final/cells/a_edf.err` | 0 | IDENTICAL_ON_ORIGIN | D208 (final ladder cells and proofs) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/ladder_final/cells/a_edf.json` | 842 | IDENTICAL_ON_ORIGIN | D208 (final ladder cells and proofs) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/ladder_final/cells/a_llf.err` | 0 | IDENTICAL_ON_ORIGIN | D208 (final ladder cells and proofs) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/ladder_final/cells/a_llf.json` | 0 | DIFFERS_FROM_ORIGIN | D208 (final ladder cells and proofs) | differs from origin/main at the same path, and in EVERY case origin carries the LATER form (mapwt is 974 commits behind); committing it would revert landed work, so it is archived, not committed |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/ladder_final/cells/chain.out` | 149 | IDENTICAL_ON_ORIGIN | D208 (final ladder cells and proofs) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/ladder_final/cells/chain_a.out` | 286 | DIFFERS_FROM_ORIGIN | D208 (final ladder cells and proofs) | differs from origin/main at the same path, and in EVERY case origin carries the LATER form (mapwt is 974 commits behind); committing it would revert landed work, so it is archived, not committed |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/ladder_final/d208_latent_hazards.json` | 3856 | IDENTICAL_ON_ORIGIN | D208 (final ladder, rung-4 mechanism convergence, proof A) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/ladder_final/d208_proof_a_bars.json` | 12411 | IDENTICAL_ON_ORIGIN | D208 (final ladder, rung-4 mechanism convergence, proof A) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/ladder_final/d208_proof_a_loadavg.json` | 3935 | DIFFERS_FROM_ORIGIN | D208 (final ladder, rung-4 mechanism convergence, proof A) | differs from origin/main at the same path, and in EVERY case origin carries the LATER form (mapwt is 974 commits behind); committing it would revert landed work, so it is archived, not committed |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/ladder_final_run_head_tree_map.json` | 4005 | IDENTICAL_ON_ORIGIN | D208 (final ladder cells and proofs) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |
| `/home/pragya/fm_archive/2026-11-24/mapwt/results/orchestration/live2/placeholder_fixes/d211_host_traffic_measured.json` | 4556 | IDENTICAL_ON_ORIGIN | D211 (host traffic measured) | byte-identical to origin/main at the same path; archived under the user's tightening (nothing in mapwt may be classed abandoned-delete, owner unknown), not because it is at risk |

## Spot check (D228 (5) clause (c)) - TO BE FILLED BY A DIFFERENT SESSION

A session that did not perform the classification above must check at least 20 rows, including
every `delete` row in the uncommitted-code class, against origin and against this manifest, and
record the result here. The uncommitted-code delete rows are the `DIVERGENT_FROM_ORIGIN` and
`NOVEL` rows listed per file above: 60 and 75 respectively.

**Performed 2026-11-24** by a session that did not do the classification (it was given the D206 (3)
guard test and this spot-check, nothing else). Checked against origin at
`b79708066fad1a3a49f31f59b0df91f214548241`, with the classification base
`8d29e86b9a33eeba1df81f7c16cf72b09de2a8a5` and the rescue commit
`72032bb240608e90cfeea0c246672b78af62f226` both confirmed as ancestors of it.

**Coverage: 135 of 135 judgment rows**, which is every row in the per-file tables above (60
`DIVERGENT_FROM_ORIGIN` and 75 `NOVEL`, across `n206` 47, `d213_e1` 83, `sessA_cs` 2, `sessA_ver`
3). The user's addendum widened clause (c)'s floor of 20 to the full 60 + 75 set, and the full set
was covered, so no sampling was done.

**What this check could and could not look at.** The files themselves were deleted after this
manifest landed, which was the order clause (d) requires, so **no file content was inspected**.
What was checked is the recorded blob shas, the recorded paths and the manifest's own reasoning
against origin's git objects. Statements below about content are statements about blob identity,
not about bytes read off disk.

| check | result |
|---|---|
| rows parsed from the per-file tables | 135, matching the 60 + 75 stated above |
| class verdict reproduced from the manifest's own stated rule | **135 of 135 agree**; zero disagreements |
| rows whose reason claims the blob "is still reachable from origin/main" | 54; **54 of 54 verified reachable** from `origin/main`, zero exceptions |
| `NOVEL` rows whose blob is nevertheless present in the classification base tree (which would make them `CONTENT_ON_ORIGIN`) | **0** |
| action tallies against the counts table | archive 31, commit 2, abandoned 1, delete 101; consistent |
| per-class breakdown table against the action table | sums exactly for all four trees (19,634 / 8,926 / 3 / 3); it is a breakdown **of the deletions only**, which is what the sentence above it says, and its `DIVERGENT`/`NOVEL` cells match the delete-action subset of the per-file rows exactly (17, 35, 43, 2, 2, 2) |

The reachability index used for the 54 rows was validated before it was trusted, rather than after:
all 282 distinct historical blobs of `research/EXPERIMENTS.md` were enumerated independently and
**282 of 282** were found in the index, so an absence reported by it is an absence and not an empty
index. The index was built with `git rev-list --objects` against a resolved literal sha, never with
a filesystem grep.

**The limit of the check, stated rather than implied.** Of the 135 recorded blob shas, **63 resolve
in the object store and 72 do not**. The 72 are not an error: the content was uncommitted and the
files are now deleted, so those shas are unverifiable by anyone, now or later. They break down as
66 `NOVEL` rows (28 raw D213 CPU-stub cell outputs, 14 claimed byte-identical after `.gz`
decompression, 10 ephemeral session markers, 5 used commit messages, 3 one-shot commit drivers, 2
intra-tree duplicates, 2 oversized s4 row files, 1 superseded cell list, 1 earlier partial version)
and 6 `DIVERGENT_FROM_ORIGIN` rows. For those 6 the manifest does **not** claim blob reachability;
it claims the weaker and correct thing, that the work landed on origin in a later form. For the 14
`.gz` rows in particular, the decompression claim cannot be re-verified from here and is recorded
as resting on the classifying session's `cmp`.

**Four reasoning claims checked directly against origin, all four hold.**

1. The pre-D223 premise used to archive rather than commit the D206 guard test. Origin's
   `arms_v6fair.py` carries `limit_tokens=CL.limit_tokens()` with an explicit `D170, D223 (2)`
   ruling and a comment naming the retyped 32768 that used to stand there, so the landed form is as
   described. (The test itself has since been run against current origin and passes 18 of 18; see
   the D206 (3) commit. That is new information about the test, not a fault in this manifest: the
   manifest's stated ground was that it was *unverified*, which it was.)
2. The archived guard test's recorded blob `1582b9ff2944` matches `git hash-object` of the archived
   file, and the file is byte-identical to what has now been committed.
3. The two rescued results are on origin at the stated paths and the stated sizes (15,639 and
   15,967 bytes), the commit `72032bb2` touches **exactly two paths**, and **neither file contains
   `_provenance`**. The missing stamp is therefore real and is **correctly recorded above as a
   declared gap** with its reason (byte-identity and digest claims reference them), not left as an
   oversight.
4. The `abandoned` row's `V6CFR3_KV025_CELLS` matches no path anywhere in origin's tree, consistent
   with D223 (1) removing 0.25x before that cell list was ever committed.

Independently confirmed: `git worktree list` on this repo reports exactly the two checkouts this
manifest names, so the statement that none of the four classified trees is a git worktree stands.

**Disagreements: none that change an action.** One label would be sharpened. Six `delete` rows
carry blobs that are absent from the classification base tree but **are** reachable from
`origin/main`'s history, so their content is recoverable from origin and not merely an
uncommitted draft: `n206/ops/STANDDOWN`, and `d213_e1`'s `out/digests_e1.json`,
`out/digests_PARTIAL_SUPERSEDED.json`, `coord_published.py`, `coord_at_tip.py` and
`patch_async.py`. `NOVEL` is correct as the manifest defines it, which is a comparison against the
tip tree; the note is only that these six are better justified than the label alone suggests. The
remaining three history-reachable `NOVEL` rows are reachable for a known reason: the two rescued
results were committed in `72032bb2`, and the guard test was committed under D206 (3) by this
session.

**Verdict: the classification is sound on every row it was possible to check, and the two
`_provenance` omissions are recorded as the declared gap they are.** No row's action is disputed.


## Third pass: `rung4p1_8ab3f7e8`, the rung-4 pass-1 build tree (D228 (5), commit authority D166)

Ruling: **D228 (5)**. Commit authority: **D166**. Produced 2026-11-24 on flash by a session that
did not perform the first two passes. This section **extends** this file; no earlier row is
altered.

Target:
`/tmp/claude-1001/-home-pragya-Desktop-FM-switching/8ab3f7e8-2a5d-4e65-8ff9-c6ae1f12519b/scratchpad/rung4p1_8ab3f7e8`,
8,143 MB, the working area of the rung-4 pass-1 build. `mapwt` was left untouched by instruction.

**It is not a git worktree.** `git worktree list` reports exactly three checkouts
(`/home/pragya/Desktop/FM-switching`, `scratchpad/stateoff_01T8MWad7BRhG6fF73CRUcAn/wt`, and
`/tmp/claude-1001/mapwt`), none of them this tree. It is a plain directory copy with no `.git`,
so `git worktree remove` does not apply and `rm -rf` is the removal. This manifest section is
committed **before** the removal, which is the order D228 (5) clause (d) requires.

### Census by process, not by name or size

Before anything was read for classification, every `/proc/<pid>` was walked for `cwd`, full
`argv` **and** open fds, plus a scan of `/proc/<pid>/maps`. **Nothing held this tree:** zero
`cwd` entries, zero open fds and zero mapped files under `rung4p1_8ab3f7e8`. The pass-1 build's
detached summariser and `da_chain.sh` had both exited (`da_chain.stdout` and `autosumm.log` are
0 bytes). The only live processes in the scratchpad were under
`ptg_build_01T8MWad7BRhG6fF73CRUcAn` (pids 1037281, 1037328, 1051797, an A/A `so_before` /
`so_after` guard-proof run), which is off limits and was not touched. The single `argv` hit for
the string `rung4p1` was the census command's own shell, a self-match, not a holder.

### The classification base, and why the working tree was never used for it

Base: `origin/main` re-resolved to the literal sha **`009ed6e31b6c1a3e882c5bea31b2ebcb5250d526`**
(fetched at the start of this pass; `origin/main` had advanced from `044da55d`). Every absence
claim in this section is a read of origin by sha, never a grep of a checkout:
`research/worktree_cleanup_manifest.md` **does not exist in the local checkout at all**, which is
the concrete reason the rule matters here. The `git ls-tree -r` blob list at that sha was asserted
non-empty before use (12,614 paths, 11,180 distinct blobs); the per-tree lists were asserted at
over 1,000 entries each. Of the 12,733 files outside the archived tree, **12,567 had their content
already on origin and 166 did not** - a split recorded here because an all-or-nothing answer would
have meant the inputs were wrong rather than the trees being uniform.

### THE CONTAMINATED TREE: identified as `e2`, archived, never to be deleted

The build's own record of the defect is `handoff/tree_guard.py` and `handoff/PREREG_AMENDMENT.md`:
mid-build the session's tree was found carrying the **held DEVICE_ANSWERS implementation in files
it had not declared changing**, a proof sweep was already running on it, the sweep was killed, the
digests discarded, numbers already quoted were withdrawn, the tree was rebuilt from a fresh
archive, and `tree_guard.py` was written as the remedy. **The build could not establish how the
code arrived and declined to invent a cause, and kept the tree so the contamination stays
auditable.**

Three `git archive` trees were present (`e2`, `pristine`, `e6`; no `e4` or `e5`). The contaminated
one is **`e2`**, on this evidence:

1. `tree_guard.py` lists three files that legitimately carry the DEVICE_ANSWERS switch name in
   `EXPECT_MARKER` and states that `arms_final_ladder.py` is **"DELIBERATELY ABSENT: the ruling
   forbids touching it until the fold, so a marker there is a FATAL finding and not an expected
   one."** `e2` carries `DEVICE_ANSWERS_SWITCH_ATTR` in **exactly that file**.
2. Four files in `e2` carry held DEVICE_ANSWERS code: `arms_final_ladder.py` (9 references),
   `arms_v6cf.py` (9), `cf_protect_defer.py` (36), `coordinator.py` (1).
3. `e2`'s `make_rung4` - **`covex-v6-final`'s own factory** - takes `device_answers: bool = True`,
   so the arm under test carried undeclared code with an **undeclared switch defaulting ON**.
4. At `e2`'s base sha `1fd0cdc9`, and at `acc34010` and `b8ce0873` too, `git grep` for
   `DEVICE_ANSWERS_SWITCH_ATTR` and `live2_cf_device_answers` returns hits **only** under
   `experiments/orchestration/live2/held/d218_device_answers/`. The markers in `e2`'s live files
   are therefore not committed content.
5. `handoff/ALONE_p1_final_start.txt` records `tree guard: PASS (6319 examined, 11 declared, 0
   undeclared, 0 stray markers)` and `e2` holds **6,320** non-`__pycache__` files: the pass-1
   proofs ran on **this** tree, and it had **no** stray marker at that moment. The
   `arms_final_ladder.py` marker appeared afterwards. That is the silent acquisition, and this
   tree is its only physical record.
6. The siblings are distinguished rather than assumed. **`pristine`** (base `acc34010`, 10:31) is
   byte-identical to its base - 0 modified, 0 new across 6,276 files - the fresh rebuild.
   **`e6`** (base `b8ce0873`, 11:54) carries the marker only in the three `EXPECT_MARKER` files
   plus the new `arms_v6cf_device.py`, with `arms_final_ladder.py` **clean**: it is the legitimate
   separate-arm DEVICE_ANSWERS build of `PREREG_AMENDMENT.md`. Origin corroborates this
   independently at `research/OVERNIGHT_HANDOFF.md`, which records that run's guard FAIL as
   benign, with `UNDECLARED differences: 0` and one forbidden marker that "was the **intentionally
   restored** `arms_v6cf_device.py`".

**The whole tree is archived, not only the files known to diverge.** Selecting just the diff would
presuppose knowledge of where the contamination entered, which is precisely what was never
established.

| archive | path | files | MB | tree sha256 | verification |
|---|---|---:|---:|---|---|
| contaminated tree `e2` | `/home/pragya/fm_archive/2026-11-24/rung4p1_contaminated_e2` | 6,588 | 2,719 | `3371b70bc0612e8bec8eb242272f6eb7b88399206fecce880956ac9fe1dfbca0` | **both**: per-file `cmp` (0 mismatches) **and** tree sha256 |
| build records | `/home/pragya/fm_archive/2026-11-24/rung4p1_build_records` | 123 | 2.2 | `d1535bdbdbe24d192a4a35728dc0c341d8408f1020d44833a90b91c5edfb318e` | **both**: per-file `cmp` (0 mismatches) **and** tree sha256 |

The tree sha256 is taken over sorted repo-relative paths with each path, its byte size and its
content fed to one digest, so a renamed or truncated file changes it. **Reproducing the two
hashes:** `rung4p1_contaminated_e2`'s digest covers the directory exactly as it stands, all 6,588
files, and was re-derived after the source was deleted and still matches. `rung4p1_build_records`'s
digest `d1535bdb` covers the **123 mirrored files only**, which is the set that was compared
against the source; the directory as it stands also holds the 5 files of `_e6_divergent_files/`,
which have no counterpart in the source layout, so a digest over the whole directory is
`6df5f86fcaa6930337e03757ce7ff3b8c88e352675bf2eecfef3af63178e70b7` instead. Both figures are given
so that neither reads as a mismatch. Both archives were verified
**before** the source was touched. `rung4p1_contaminated_e2_EVIDENCE.txt` sits beside the archive
and carries the base sha, the divergent paths with the git blob sha of the archived copy against
the base blob, the DEVICE_ANSWERS reference count per file, and the six points above, so the
defect is inspectable without unpacking 2.7 GB.

`rung4p1_build_records` holds `handoff/`, `held/`, `work/`, `da/`, `pc/` and the loose build
scripts, logs and JSON, plus `_e6_divergent_files/` - the four files in which `e6` diverges from
its base, with its `BASE_SHA` - so that deleting `e6` as regenerable cannot lose the deliberate
DEVICE_ANSWERS build even though origin has since moved past it.

### Disk, and the standing 15 GB floor

The archive volume (`/`, shared with the scratchpad) was checked **before starting and again
immediately before each copy**, with a hard assert at each point rather than an `&&` list.
Free: **26,702 MB before**, projected 23,983 MB after the 2,719 MB tree, **24,029 MB measured**
before the records copy, **24,016 MB** after it. The new standing rule - refuse to start below
15,360 MB and re-check before the copy - held at every check. Neither copy's return code was
trusted on its own: an earlier space exhaustion on this volume returned rc=120 or rc=2 with
**zero bytes of stderr**, so both archives were accepted only on the content comparisons above.

### Counts per class

| subtree / group | action | files | MB | reason |
|---|---|---:|---:|---|
| `e2` | **archive, never delete** | 6,588 | 2,719 | the contaminated tree; a state that arose once by an unknown mechanism, not regenerable |
| `pristine` | delete | 6,407 | 2,708 | regenerable: `git archive acc34010`, **proven** byte-identical to its base, 0 modified and 0 new |
| `e6` | delete | 6,464 | 2,715 | regenerable from `b8ce0873`; its 4 divergent files are archived under `_e6_divergent_files/`, and `cf_protect_defer.py` is on origin at the identical blob `643a8fb0` |
| `handoff/`, `held/`, `work/`, `da/`, `pc/`, loose scripts and logs | **archive**, then delete | 123 | 2.2 | deliverables and dry-proof captures; substance landed on origin but `work/selfid1`, `work/selfid2` and the ALONE censuses are unverified data, so nothing here was deleted without a copy |
| `tree_guard.py` | **commit** | 1 | 0.005 | genuinely uncommitted code belonging to landed work |

### Committed (clause c: uncommitted code belonging to landed work)

| path | blob | reason |
|---|---|---|
| `experiments/orchestration/live2/tree_guard.py` | see commit below | **absent from origin entirely** at `009ed6e3`: `git ls-tree -r --name-only` matches no path containing `tree_guard`, and the string `tree_guard` appears in no file on origin. Yet D232 (6) is a ruling about this tooling, and `research/EXPERIMENTS.md`'s `StudyD222-PASS1-NQD` row certifies that "**EVERY TREE-GUARD CALL EXITED 0** ... each captured to its own `.rc` and tested with an explicit if-then-exit, never an `&&` list, per D232 (6)". The instrument those proofs rest on was never committed. The version committed is the **later** root copy (5,428 bytes), not `handoff/`'s earlier one (3,590 bytes): it splits severity into FATAL (undeclared difference or stray held marker) and ADVISORY (a declared file that matches git, i.e. a stale list and not a dirty tree), which is the distinction origin's `OVERNIGHT_HANDOFF.md` records as the fix the benign FAIL demanded. |

Nothing else was committed. Every other pass-1 deliverable was checked **by path and by blob** at
`009ed6e3` and had landed: `arms_v6cf_device.py`, `d222_measured_safety.py`, `metrics_trust.py`,
`d227_e1_metrics_proofs.py`, `results/orchestration/live2/d222_pass1/d222_safety_refit.json`,
`d227_e1_metrics/d227_e1_metrics_proofs.json`, and the proof JSONs `proof_ab_pass1_tree.json`,
`proof_ab_pristine_tree.json` and `proof_c_dry_s4.json`. `e6`'s `cf_protect_defer.py` is on origin
at the **identical** blob `643a8fb0`.

The `handoff/` design and pre-registration documents were **not** committed: their substance had
already landed, not as files but folded into committed text - `PREREG_PASS1_ROW.md` and
`PREREG_AMENDMENT.md` into `research/EXPERIMENTS.md`'s `StudyD222-PASS1` and `-NQD` rows (checked
by the distinctive constants `0.0001535807289338535`, `1.767170` and `247.4582067460825`) and the
build-miss disclosure into **D231 (1)** in `research/policy_design_log.md`, which states it
without softening: "**BUILD MISS: DEVICE_ANSWERS was not built into pass 1** (3 decisions wanted
it), contrary to D221 / D228 (3)". Committing the drafts would have duplicated landed text into
`research/` against live edits by other sessions. They are archived instead, and this is the line
that records it.

### Flagged, not resolved by this session

- `handoff/PREREG_AMENDMENT.md`'s own framing sentence - "**A proof that passes on a tree that was
  not pushed is not a proof of the cell**, and 'the proofs passed' is exactly the sentence that
  hid it" - appears **nowhere on origin**. The ruling and the remedy landed; that one generalisable
  sentence did not. Whoever owns the pass-1 row may want it in the record. The text is preserved at
  `rung4p1_build_records/handoff/PREREG_AMENDMENT.md`.
- The cause of the contamination remains **unestablished**, as the pass-1 build said. Archiving it
  does not close it.

### Spot check for this third pass - TO BE FILLED BY A DIFFERENT SESSION

Per D228 (5) clause (d), a session that did not perform this classification should check it. Left
deliberately empty. The two claims most worth re-deriving independently: that `e2` and not `e6` is
the contaminated tree, and that `tree_guard.py` is absent from origin.
