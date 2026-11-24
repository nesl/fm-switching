# OVERNIGHT HANDOFF, 2026-11-23 evening. Written BEFORE step 1, per the user's plan.

ALL TIMES ARE PST AND STATE THEIR ZONE. Derive idleness from the newest commit's timestamp WITH ITS
OFFSET (`git log --date=iso-strict`), never from a bare clock time: reading PST commit times as UTC
once produced a false "H100 idle eight hours" claim while it had committed one minute earlier.

## WHERE THE WORK IS

RUNNING NOW (H100): nine final-ladder cells, s5 to s7 for `covex-v6-fair-final`, `covex-v6-final`,
`covex-v6-state-final`, from ~20:11, LADDER COMPLETE ~23:20. Then hit 7 lands on `coordinator.py` and
`cstate.py` with its final-rung identity pass; then SimpleStream reruns as filler; then item 3.
ALL TWELVE LADDER CELLS RUN ON ONE COORDINATOR COMMIT by agreement, so "did the coordinator change
mid-ladder?" never arises. Hit 7 AND item 3 are both `coordinator.py` edits, so BOTH wait for the last
cell. Score each cell as it lands with the committed `d179_rung2_verdict.py`; the s4 verdict is
complete and committed.

## THE FIVE OVERNIGHT STEPS, IN ORDER

1. **DEVICE_ANSWERS (D218 (1))** against the FROZEN pre-registration `77cf269e`, on a NEW VERSION LABEL
   so the posted `covex-v6-final` is untouched. Dry report: per-kind counts at 1x AND 0.25x,
   `pd_request_device_answers`, `pd_request_crossed_bar_unexpressible` BEFORE and AFTER, and THE
   PREDICTED TRADE PER DENIAL (this question's lost weighted P(on time) against on-time answers saved
   BY TYPE, alert / recall / assistance). **THE 1x COUNT DECIDES WHETHER THE POSTED `covex-v6-final` s4
   IS SUPERSEDED: IF NON-ZERO, STOP AND REPORT, DO NOT DECIDE.**
2. **E1**: enable the `/metrics` scrape for `covex-v6-final`'s GATE ONLY; prove EVERY other arm
   byte-identical; report HOW MANY RUNG-4 DECISIONS MOVE. MUST LAND BEFORE ANY 0.25x POLICY CELL
   (D216 (2)). `asyncbackend.py` is uncontested, so this can proceed independently of hit 7.
3. **ITEM 3 (D216 (3))**: record the belief's predicted GPU-resident prefix per request so D211 signal
   (a) is computable. Site is `coordinator.py:2126`, so IT WAITS FOR HIT 7.
4. **THE 0.25x PAIR, user-approved FOR THIS PAIR ONLY**, once 1 to 3 pass: `covex-v6-fair-final` and the
   DEVICE_ANSWERS build of `covex-v6-final` at 0.25x s4, REAL ENGINE POOL
   (`--num-gpu-blocks-override 985 --max-model-len 15744`, pool of record 15,760 = 985 x 16), posted
   BEHIND the remaining `FINAL_LADDER_CELLS`. Bar: the frozen D190 (3) rung-4 test at 0.25x, reported
   BESIDE per-type percent correct-by-deadline, single-shot within 2 s, and total on-time cloud answers.
   VALIDATE D211 signals (a) and (b) on these two cells against `host_counters_d211.log` at the frozen
   bar.
5. Rulings applied in this commit: the scorer LABEL fix with its erratum (governing test unchanged), and
   the `arms_v6cf.py` doc line.

## WHAT IS DONE AND MUST NOT BE REDONE

`FINAL_LADDER_CELLS` posted `43ad8be8`; s5 to s7 posted `599e2dbc`. s4 verdict COMPLETE: all three rungs
PASS, rung 3 by +0.1767 on the harder "above base's" bar with retention 1.0833; **rung 4 by +0.004066,
which at 712 episodes is ABOUT 2.9 EPISODES while the fraction meeting the 0.25 target FELL by about 8
EPISODES, so the two alert measures DISAGREE IN SIGN and it must never be quoted as a clean win.** The
better account of rung 4 at 1x is that it sent 675 FEWER robot requests for 121 on time against 126 with
`by_deadline` IDENTICAL. Rung 2 has no bar of its own and rides with rung 3.

## HAZARDS THAT HAVE EACH COST SOMETHING TODAY

- ALONE GUARDS ARE UNRELIABLE. Three sessions found theirs blind to processes they had no name for, each
  bounded differently (a tree snapshot, a `"one_cell"` pattern, a hardcoded basename list). COUNT LIVE2
  PROCESSES BY WHAT THEY ARE (an interpreter plus a path under the repo or a scratchpad tree, or
  enumerate `/proc/<pid>/cwd`), NEVER by a name pattern, and record the census and loadavg BESIDE the
  boolean. A `/proc` matcher hits your OWN SHELL on a READ-ONLY SCAN, so the hazard is in the MATCHER,
  not the kill; never `pgrep -f`/`pkill -f` on a self-matching pattern (exit 144).
- THE SHARED WORKTREE IS NOT SAFE FOR CELLS. Run every proof cell from a PRIVATE `git archive` of ONE
  LITERAL SHA and cmp-check `arms.py`, `coordinator.py` and `v5/cf_objective.py` inside the archived
  tree first; `arms.py` and `coordinator.py` are in every arm's import graph.
- RE-RESOLVE `origin/main` TO ONE LITERAL SHA IMMEDIATELY BEFORE COMMITTING. Origin moved more than
  thirty times today and a split ref silently reverts another session's files with a CLEAN FAST-FORWARD
  at push time.
- DO NOT ASSERT AN ABSENCE FROM A TRUNCATED VIEW. A `head -40` grep produced a false "the engine emits
  neither key" claim, and I relayed it. Include the exact command and its output with any absence claim.
- A BAR IS ONLY COMPARABLE WITHIN ONE RECIPE, and every bar-table row now carries the commit that
  produced it and the ruled fixes it predates (D217 (4)).

## OPEN, NEEDING A USER RULING

- **E3, one line**: `run_live2_real.py` builds `cell.json` from a fixed key list and `metrics_health`
  appears nowhere in it, so a cell with failed metrics fetches does not say so. The fix is
  `out["metrics_health"] = (res.get("backend") or {}).get("metrics_health")`. WAITS FOR A RULING.
- `cstate.py:17`'s doc line still says `vllm:gpu_cache_usage_perc`. NOT corrected here because the H100
  holds `cstate.py` for hit 7; do it after hit 7 lands.
- D211 signal (a) will have NO 1x live cell to validate on, because item 3 lands after the last ladder
  cell. Its validation now needs the 0.25x pair or a dedicated later cell.
