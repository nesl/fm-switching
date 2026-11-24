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

### THE ONE PATTERN BEHIND MOST OF TONIGHT'S NEAR-MISSES: AN INSTRUMENT THAT RETURNS A CONFIDENT WRONG
### ANSWER POINTING AT A HARMFUL ACTION. Four distinct instances in one evening, each caught only by
### someone checking WHAT THE INSTRUMENT CLASSIFIED rather than WHAT IT CONCLUDED.
### THE FAMILY, stated once: A BOUND NOBODY STATES, PLUS AN OUTPUT THAT LOOKS LIKE PROGRESS.

| instrument | how it failed | what it looked like | what the wrong action would have been |
|---|---|---|---|
| alone-guards, THREE sessions | bounded by a name pattern, a hardcoded basename list, and a tree snapshot | `alone: true` while the box was busy | a digest recorded as alone that was not |
| a byte-identity check | a raw line-number rule swept two function bodies into "post-run" | PASS on the real tree | shipping wiring whose in-run statements were never checked |
| a hung driver | blocked with 00:00:00 CPU and no children for 59 minutes | indistinguishable from a long cell | waiting out an hour, then reporting a table from nothing |
| a completeness check | "trees already present" looked for ONE file, so minimal stub trees satisfied it and the rebuild was skipped | a proof running against a tree with no coordinator, no fleet and no tests | a failure that reads as a CODE fault rather than a missing tree |
| a liveness watch | `grep -lq ... /proc/*/cmdline` exited non-zero on ERROR, not no-match, so the negation read "gone" | a false terminal state | RELAUNCHING a running sweep, putting two drivers on the box and breaking the alone rule it enforced |

THE OPERATIONAL RULES THAT FALL OUT, AND THEY ARE CHEAP:
- READ WHAT A CHECK CLASSIFIED, NOT ITS VERDICT. An impossible success is as diagnostic as an impossible
  failure, and arithmetic checking cannot see either.
- A CHECK SHOULD CARRY ITS OWN NEGATIVE CONTROL AND RUN IT EVERY TIME. One session now injects four
  decision-changing statements and requires all four to be REJECTED; the real tree passing is the
  positive control.
- SILENCE MUST BE DISTINGUISHABLE FROM PROGRESS. Bound every wait, and make it end on at least three
  conditions named separately: the result appeared, the process died without writing, and the resource
  floor was hit. A watch that reports a false terminal state is WORSE than no watch, because the wrong
  action looks correct.
- COUNT PROCESSES BY WHAT THEY ARE, never by a name. An interpreter plus a path under the repo or a
  scratchpad tree, or enumerate `/proc/<pid>/cwd`. State the census's own blind spot in the record.
- PREFER EVIDENCE OVER A FLAG. Two independent runs agreeing exactly is DIRECT evidence of determinism;
  an alone-flag is only an argument that nothing COULD have disturbed the cell. Record the census and
  the loadavg magnitudes BESIDE any boolean so it can be re-adjudicated later.
- NEVER LET A WAIT HAVE ONLY THE TWO TERMINAL CONDITIONS A READER EXPECTS, and RECORD WHICH ONE FIRED.
  One session's waits now end on a clear guard, a timeout, OR low disk, each written into a
  `wait_terminated_by` field, so "still waiting", "gave up" and "stopped on disk" are three
  DISTINGUISHABLE states in the output rather than one silence. A bounded wait that also ends on
  PROCESS-DISAPPEARANCE would have caught the hung driver with nobody watching.
- A HALTED PROOF MUST NEVER READ AS A CLEAN ONE. The same session's byte-identity proof now writes a
  VERDICT of "NOT RUN: LOW DISK" saying IN WORDS that it is NEITHER A PASS NOR A FAILURE.
- HELD CODE LIVES AS A `.patch`, NOT A `.py`, AND IN GIT RATHER THAN ONLY IN /tmp. The D214 wiring
  existed ONLY inside a scratchpad tree that was about to be deleted for disk; it is now committed at
  `experiments/orchestration/live2/held/` as a patch plus a README, verified to reproduce the held
  md5, with NOTHING importing it and `run_live2_real.py` on origin still at ZERO occurrences of
  `figure_instrumentation`. COMMITTING A PATCH IS NOT LANDING THE WIRING, and storing it as `.patch`
  rather than `.py` is what keeps it out of an import or a glob.
- *** NEVER ESTABLISH AN ABSENCE BY GREPPING THE SHARED WORKTREE. IT IS ABOUT 1,500 COMMITS BEHIND
  ORIGIN. *** `/home/pragya/Desktop/FM-switching` sat at `17bdf159` while origin was at `7ca9d1e7`:
  1,500 commits. A file committed tonight IS NOT THERE, so `grep -r` over it returns nothing for a file
  that exists. THIS COST ME A WRONG ESCALATION: I told an agent its proof script was uncommitted and
  "one cleanup from destruction" on the strength of `grep -rln ALL_PASS experiments/` returning empty.
  It was committed, and `ALL_PASS` is in THIRTEEN committed files. ALWAYS use `git grep <literal-sha>`
  or `git show <sha>:<path>`, never a filesystem grep of that tree, for any claim about what is or is
  not in the repo. The same staleness is why files committed tonight show as `??` untracked there.
- *** A SUMMARISER THAT PROBES FOR A KEY NAMED AFTER A VALUE PRINTS `None` FOREVER. *** A proof wrote
  `{"verdict": "ALL_PASS", ...}` and a summary line reported `ALL_PASS: None`, which reads as an
  unset aggregate and sent me hunting a swallowed fifth check. There was none: four `P*` keys, all
  PASS, and the aggregate is computed as `all(... for k in out if k.startswith("P"))`, so coverage is
  complete BY CONSTRUCTION and `None` was unreachable from that code. A reader asking for
  `d.get("ALL_PASS")` on a dict whose KEY is `verdict` gets `None` whatever the verdict says. READ THE
  FIELD, THEN ASSERT ITS VALUE IS THE LITERAL EXPECTED STRING; never probe for a key named after the
  value you hope to see, and never read a `None` as a failure before checking the schema.
- AND FOR RELAYED CLAIMS: a NEGATIVE assertion about a primary artefact is cheap to check and expensive
  to propagate. Three were relayed unverified today (a loadavg precedent that did not exist, a
  touch-price magnitude off by about 26x, and two metric names that did exist). Check a negative against
  the artefact BEFORE passing it on, and send the command and its output with it.


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
