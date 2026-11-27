# Orin notes (analysis host)

## 2026-11-27: d190_d192_poll.sh stopped by user ruling

- The scratchpad loop `d190_d192_poll.sh` (PID 1445420, started about 2.9 days earlier, 30 min interval) was stopped on 2026-11-27 by user ruling. It was killed by PID only; its child `sleep 1800` (PID 1744532) was also stopped. Neither is to be restarted.
- Reason: its figdata regeneration dropped 21 rows from `reports/figdata/F1.csv` (rung 3, eco-llm, kvflow, device-only) and left the tracked file dirty, so every rebase failed ("cannot rebase: You have unstaged changes").
- Its log is archived unchanged at `scratchpad/d190_d192_poll.log.2026-11-27.bak` (the live log is kept beside it).
- The modified file is preserved, untracked, at `reports/figdata/F1.csv.uncommitted-2026-11-27`. The tracked file was restored with `git checkout --` to HEAD. Nothing was deleted.

## 2026-11-27: F1.csv dropped-rows diagnosis (read-only, regenerator not run)

- Backup `reports/figdata/F1.csv.uncommitted-2026-11-27` (untracked, kept) against tracked `reports/figdata/F1.csv` at HEAD: the tracked file has 116 lines, the backup 95. The diff is 21 removed rows and 1 added row.
- Removed rows, by arm (5 rows each): kvflow-prefetch (seeds 4, 5, 6, 7 plus the seed-"all" row), device-only (seeds 4 to 7 plus "all"), covex-v6-fair-final (rung 3, seeds 4 to 7 plus "all"), covex-v6-state-final (seeds 4 to 7 plus "all"). The 21st removed row is the eco-llm seed-"all" row, which is replaced by a row with the same run directory and different content.
- Code path, `experiments/analysis/figdata/figdata.py`: `discover()` lines 126 to 175 build the arm-to-cell map and skip any run directory whose `cell.json` is missing (lines 131 to 133); `_figure_arms()` lines 713 to 718 keeps only arms present in that map; `build_F1()` lines 358 to 398 emits one row per standard cell (`is_standard`, line 352) and one seed-"all" row from `std[-1]`, the last standard cell of each arm.
- Cause (best explanation, not confirmed): `figdata.py` last changed 23 Nov (commit 41fe4c16), and the cell files for the dropped arms carry 23 Nov timestamps, so the code and the inputs are the same as when the tracked file was written on 24 Nov. The difference must lie in the run-directory state the regenerator saw at 17:19 on 26 Nov, when the poll loop ran it. A changed `discover()` result explains both the whole-arm drops and the eco-llm change, because `std[-1]` depends on which cells were found. Confirming it needs a read-only dry run of `discover()` that prints the per-arm cell count, which was not run here.
- Consequence: the rung-3 rows are missing from the tracked F1 until the file is regenerated from a verified run-directory state.

## 2026-11-27: population-script guard byte-identity check

- `oracle_feasible_pop.py` now asserts that each named substitution pattern matches at least once, and prints the match count to stderr. The patterns are `cell-pattern`, `trace-devices`, `trace-mix` and `module-link`.
- Re-run for n20 (`_c3-11-2`, seed 4), n32 (`_c3-11-2`, seed 4) and n16 (default tag, seed 4). Compared with the committed outputs: every number is identical. Only `_provenance` `git_commit` and `timestamp` differ. The committed copies were restored, so the re-run outputs are not committed.
