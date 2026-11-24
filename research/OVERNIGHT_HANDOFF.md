# OVERNIGHT HANDOFF, 2026-11-23 evening. Written BEFORE step 1, per the user's plan.

ALL TIMES ARE PST AND STATE THEIR ZONE. Derive idleness from the newest commit's timestamp WITH ITS
OFFSET (`git log --date=iso-strict`), never from a bare clock time: reading PST commit times as UTC
once produced a false "H100 idle eight hours" claim while it had committed one minute earlier.

## READ THIS FIRST, FOR A WATCHDOG RESUME. STATE AS OF 2026-11-23 22:20 PST.

*** THE RESUME PROMPT CONTAINS THREE STALE PREMISES. DO NOT WASTE CALLS ON THEM. ***
- **`ops/watchdog.log` AND `ops/track.log` NOW EXIST ON DISK. CORRECTED 2026-11-23 22:31.** The
  earlier entry said they did not exist anywhere; that was checked with `git cat-file -e`, WHICH ONLY
  TESTS ORIGIN, so it could never have seen a gitignored local file. They are local-only and live:
  `ops/watchdog.log` 299 lines, `ops/track.log` 1,298 lines, newest entry 06:30:01Z. **READ THEM, they
  are informative**, but they are NOT a concurrency check: watchdog.log records session liveness and
  track.log carries prior resumes' own reports. *** WHAT watchdog.log SAYS RIGHT NOW MATTERS: heartbeat
  STALE and `RESTART 3/12: session fmsw-overnight absent` at 06:10, 06:20 and 06:30Z. THE CLAUDE SESSION IS
  RESTARTED EVERY TEN MINUTES, which is why you are reading this. Expect to be resumed again; leave the
  file fit for that.***

*** THE RESTARTS ARE EXPECTED BEHAVIOUR, NOT A CRASH, AND THE OVERNIGHT WORK IS ALIVE. Established by
process census at 22:40, so no resume needs to re-derive it. ***
- The watchdog launches `claude -c --permission-mode auto -p '<the resume prompt>'`, which is a
  ONE-SHOT non-interactive session: it exits when its turn ends. The watchdog then finds no session,
  calls the heartbeat STALE and restarts it. **So "heartbeat STALE" plus "session absent" is what a
  HEALTHY `-p` run looks like to this watchdog.** It is bounded: the log counts `RESTART n/12`, and it
  stood at 4/12 at 22:40. DO NOT read the restarts as evidence that anything broke, and do not go
  hunting for the crash. Each restart does cost a full session, so leave this file accurate.
- **E1's 52-cell sweep IS RUNNING.** pid 304781 is
  `d213_digest_driver.py --out out/digests_e1.json`, with a LIVE CHILD running
  `cf_pd_one_cell.py --arm v5-rules-2 --seed 4 --n 16 --run-s 1200 --cutoff-off`. **DO NOT KILL IT and
  do not start a second sweep.** The ALONE rule means a dry cell of your own must WAIT.
- The DEVICE_ANSWERS driver `d218_da_driver.py` was restarted and is writing to `scratchpad/cells`.

*** A CORRECTION TO THIS FILE'S OWN HANG-DETECTION LESSON, because I got the discriminator wrong
earlier tonight and a future resume would kill a healthy driver with it. ***
The catalogue below records a driver that sat 59 minutes at `00:00:00` CPU having started nothing. I
treated **zero own CPU** as the hang signal. **THAT IS WRONG AND DANGEROUS: AN ORCHESTRATOR DRIVER
CORRECTLY SHOWS ~0 OWN CPU, BECAUSE ITS CHILDREN DO THE WORK.** pid 304781 has consumed `00:00:00` in
2.5 hours and is perfectly healthy. **THE REAL DISCRIMINATOR IS CHILDREN: `0 CPU` AND `ps --ppid <pid>`
EMPTY is a hang; `0 CPU` WITH a live child burning CPU is a working orchestrator.** Check children, and
check what the child is doing, before calling anything hung.
- **D187 IS NOT IN THIS FILE.** It is `research/policy_design_log.md:208`. Its guardrails, which DO
  apply: every change justified by a MEASURED mechanism and PRE-REGISTERED (commit before its cells);
  each design change a NEW LABELLED version recorded as OVERNIGHT DECISION, PROVISIONAL; never change
  targets, deadlines, metrics, workload, seeds (never 1-3 or HOLDOUT), baselines or pass bars; never
  drop or exclude data; NEVER TUNE A PARAMETER TOWARD PASSING; every result reported whatever its
  direction; held or unproved code defaults OFF; one dry cell per process; D166 commit rules; NO Claude
  attribution lines; no em dashes.
- *** D187 (2)'s "FIX WITHOUT WAITING FOR APPROVAL" IS SUPERSEDED FOR THE RUNG-4 DEFECT. *** The user's
  instruction of 2026-11-23 evening commissioned the diagnosis and required the remedy be "costed, NOT
  built", and the standing rule is STOP AND REPORT, DO NOT DECIDE when a pre-registered condition
  fails. **DO NOT BUILD THE QUEUE-TERM FIX.** It is diagnosed, costed and waiting on the user.

*** HOW TO CHECK CONCURRENCY CORRECTLY (the shared worktree lies): ***
`/tmp/claude-1001/mapwt` is HUNDREDS of commits behind origin (1,500 earlier tonight, 670 later), so
`git status` there reports STALENESS AS MODIFICATION and shows committed files as `??` untracked. *** THE TEST THIS FILE PREVIOUSLY PRESCRIBED IS ALSO WRONG, AND FOR THE SAME REASON IT WARNS ABOUT.
`git diff --stat origin/main -- <path>` IN A STALE WORKTREE REPORTS STALENESS AS DELETION: run against
`experiments/` it prints `124 files changed, 238 insertions, 33,648 DELETIONS`, which is 680 commits of
origin's own additions, NOT anyone's edits. A real edit and a missing file are indistinguishable in it.
*** THE TEST THAT ACTUALLY WORKS IS AGAINST THE WORKTREE'S OWN HEAD, NOT ORIGIN: ***
`git -C /tmp/claude-1001/mapwt diff --stat HEAD -- experiments/` plus `git status --porcelain -- <path>`.
Anything it prints is an UNCOMMITTED WORKING-TREE EDIT, because staleness cannot appear in a diff against
one's own HEAD. As of 22:31 that test CONFIRMS the conclusion the broken test had reached by luck:
`M arms.py`, `M coordinator.py` (+483), `M v5/cf_objective.py` (+123), and five more under
`experiments/`, 1,482 insertions in all. **LIVE UNCOMMITTED EDITS TO RUN-PATH FILES. Another session is
mid-work on them.** **A RUN-PATH FREEZE IS ALSO IN FORCE until the ladder completes**,
so TOUCH NO RUN-PATH FILE for either reason.

*** WHAT IS ALREADY SCORED. DO NOT RE-SCORE. ***
| arm | s4 | s5 | s6 | s7 |
|---|---|---|---|---|
| rung 3 `covex-v6-fair-final` | ALL THREE PASS | **ALL THREE PASS**, retention 1.1059 (`3c644d81`) | **ALL THREE PASS**, retention 1.0769 (`f476ee96`) | cell missing |
| rung 4 `covex-v6-final` | ALL THREE PASS | **check 2 FAIL 0.851** (`8e05580e`) | **check 2 FAIL 0.871** (`c7c92285`) | cell missing |

**RUNG 4 PASSES CHECK 2 AT ONE SEED OF THREE, ON ROBOT RETENTION ALONE**; its checks 1 and 3 pass
everywhere and its alert attainment is slightly ABOVE rung 3's at both failing seeds, so it buys a small
alert gain with a larger robot loss. **RUNG 3 PASSES EVERYTHING EVERYWHERE SCORED.** Rung 2 standing
alone is WORSE THAN BASE on alerts (0.2407 vs 0.3962 at s5) and would fail check 1.
**THE CAUSE IS DIAGNOSED AND VERIFIED AT CODE LEVEL** (`reports/study_rung4_s5_failure.md`, `7ab3b070`):
`arms_v6cfr3.py` calls `CC.predict(cf.model, int(u_request), 0, 0, 0)` while `v5/cf_cost.py:149` is
`predict(model, tokens, cached_tokens=0, overlap_ft=0, overlap_decode=0, link_s=...)` computing
`ft = intercept + per_uncached*unc + per_overlap*overlap_ft`, so **D162's queueing term is IDENTICALLY
ZERO on a gate reached only when other requests are queued.** 14 losses, 0 gains, residual ZERO at s5;
s4 had 2 gains and passed, so **s4's pass is the luckier draw of the same losing trade.**

*** STATE AS OF 2026-11-23 22:55 PST, FROM A PROCESS CENSUS, SO NO RESUME RE-DERIVES IT. ***
- *** E1's 52-CELL SWEEP IS FINISHED AND ITS RESULT IS NOW COMMITTED (this commit). *** It wrote
  `out/digests_e1.json` at 22:46:26 and EXITED; pid 304781 is GONE, which is COMPLETION, not a crash.
  **VERDICT: precheck_passed true, n_arms 24, n_identical 24, n_moved 0, moved_arms [], setwise
  decisions moved 0.** So E1's NON-INTERFERENCE gate PASSES and the ESCALATE-AND-STOP condition did not
  fire. **THE SWEEP'S OWN FILE LABELS WHAT IT CANNOT SHOW, and that label must travel with it:** "how
  many rung-4 decisions the scrape moves: a dry cell builds no backend, so the mechanism is ABSENT and a
  zero here is UNEXERCISED, not a measurement". `covex-v6-final` IS NOT ONE OF THE 24 ARMS; this proves
  only that the scrape disturbs nothing else. CAVEAT RECORDED, NOT BURIED: `n_cells_not_alone = 24`, all
  24 pairs ran with foreign load at loadavg 1.15 to 2.22. A and B agreeing bit-exactly under varying
  load is direct evidence of determinism, and tonight a digest reproduced bit-exactly at loadavg 34.97,
  so the not-alone condition weakens the ALONE claim but not the identity conclusion.
- **THE DEVICE_ANSWERS DRIVER IS WAITING, NOT HUNG, AND THE HANG RULE IN THIS FILE WOULD HAVE
  MISDIAGNOSED IT.** pid 346850 shows `00:00:00` CPU and `ps --ppid` EMPTY after 11 minutes, which this
  file's corrected rule calls a hang. **IT IS NOT: a foreign cell IS running** (`run_live2_real.py
  --arm covex-v6-cf-pd-c5attr`, pid 351013, whose parent chain ends at init, so it is NOT a DA
  descendant), and the DA driver carries `--wait-s 90` and an alone-wait. *** SO THE DISCRIMINATOR NEEDS
  A THIRD STATE, and this is its final form: 0 CPU + no descendants + NOTHING ELSE RUNNING = HANG;
  0 CPU + a live descendant = WORKING ORCHESTRATOR; 0 CPU + no descendants + A FOREIGN CELL RUNNING =
  CORRECTLY WAITING ON THE ALONE RULE. *** Check descendants by walking the parent chain to init, not
  by `ps --ppid` alone, because a cell launched through a shell is not a direct child.
- Ladder at **10 of 12**: `covex-v6-fair-final` s7 IS on origin (17 files); `covex-v6-final` s7 and
  `covex-v6-state-final` s7 are ABSENT. Rung 4 s7 started 22:41:30; state-final s7 due about 23:25.
- Watchdog at **RESTART 5/12**. The budget is finite: 7 restarts left, so do not spend one re-deriving
  what is written above.

*** PRE-COMPUTED FOR s7 SO THE NEXT RESUME READS THE CELL IMMEDIATELY, NOT AFTER AN HOUR OF SETUP: ***
- **RUNG 4's s7 CHECK-2 THRESHOLD IS 78 OF 105, NOT 77.5.** base 19, fair-final 84, gain 65;
  `(shares - 19)/65 >= 0.90` needs `shares >= 77.5`, and answers are integers, so **78 PASSES (0.9077)
  AND 77 FAILS (0.8923)**. Rung 4 may therefore lose AT MOST 6 robot answers against rung 3's 84. **IT
  LOST 14 AT s5 AND 9 AT s6.** That is context, NOT a prediction: s7's mix differs sharply (2,445 robot
  requests against 681 at s6) and base is unusually strong on alerts here at pooled 0.638.
- **THE s7 SERVABLE POOL IS 87, NOT 105, AND THIS IS VERIFIED, NOT PRESUMED.** fair-final s7 has 18
  robot rows with NO `t_delivered`, and those 18 opportunity ids are the IDENTICAL SET to D176's 18
  over-32k questions at seed 7 (intersection 18, zero either way, checked against
  `frozen_test/d170_overlimit.json`). Declining them is D170 behaviour, not a loss. So fair-final is
  **84 of 105 = 0.800 OFFERED but 84 of 87 = 0.966 SERVABLE**. *** REPORT BOTH AND NAME THE DENOMINATOR
  AT THE POINT OF USE; THE PRE-REGISTERED BAR STAYS ON 105, because switching it to 87 would be moving
  a bar after the numbers exist. ***
- `dashcam_all_meet` is PER DEVICE against the 0.25 attainment target (`scorer/score.py:713-719`,
  `meets = eligible and frac >= p_dash - 1e-12`, all-of over ELIGIBLE devices), NOT pooled. So
  state-final s6 reading TRUE at a pooled 0.3161 is CORRECT. "Meets the target" and "is good" are
  different statements. **And the dashcam denominator key is `n_instants`, NOT `n`:** summing `n` gives
  a ZERO denominator and a silent 0.0 fraction.

*** THE NEXT STEP, WHICHEVER APPLIES FIRST: ***
1. ~~`covex-v6-state-final` s6 -> score RUNG 3 at s6~~ **DONE at `f476ee96`: ALL THREE PASS, robot
   retention 1.076923, check 1 +0.166322, positive control 2 of 2 exact.** Rung 3 now passes everything
   at s4, s5 AND s6, and EXCEEDS its comparator's gain at both s5 (1.1059) and s6 (1.0769), not merely
   retaining 0.90 of it. **THE LADDER IS AT 9 OF 12 COMMITTED CELLS; s7 HAS NONE OF THE THREE FINAL
   ARMS** (only `hybrid-F-lhreq-noc3` s7 exists), so as of 22:31 THERE IS NOTHING LEFT TO SCORE.
2. s7 cells land -> score **rung 4 s7 as soon as `fair-final` s7 exists** (rung 4's comparator is
   fair-final, NOT state-final, so it does not wait for state-final s7), and rung 3 s7 once state-final
   s7 exists. Scoring recipe: extract the three cells from origin into a scratch `runs/` dir and run
   `d179_rung2_verdict.py --runs <dir> --seeds <n> --shares-arm <arm> --base-arm hybrid-F-lhreq-noc3
   --rung2-arm <comparator>`. **CONFIRM `positive control: PASS` EVERY TIME before reading a verdict.**
3. Nothing scorable -> do NOT invent work on run-path files. The handoff's five overnight steps below
   are owned by other sessions.

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
- *** A RECORD-ONLY COMMIT CAN REPORT SUCCESS AND CHANGE NOTHING. BOUND THE FILE COUNT FROM BELOW,
  NOT ONLY FROM ABOVE, AND READ THE PUBLISHED BYTES BACK. *** A session staged FIVE files from a
  correct scoped list; `diff-tree` reported FOUR. Its working copy of the fifth had been overwritten by
  raw driver output, so the blob it pushed was byte-identical to the one already on origin. **THE PUSH
  SUCCEEDED AND CORRECTED THE ONE FILE THAT MATTERED MOST: NOTHING** - the misleading headline stayed
  published while a commit claiming to fix it landed on top. Its own guard asserted "at most 5 files"
  and PASSED AT 4: **bounded from above, never from below.** So: assert the EXACT expected count, and
  then `git show origin/main:<path>` the file and grep it for the SPECIFIC TEXT the commit exists to
  add. A scoped list guarantees what is STAGED, never that staging CHANGED anything. This is the
  pattern in the RECORDING layer rather than the measurement layer.
- *** "ZERO CPU" IS NOT A HANG SIGNATURE. THE DISCRIMINATOR IS WHETHER IT HAS A WORKING DESCENDANT. ***
  A driver at `00:00:00` CPU after 59 minutes with NO CHILDREN was genuinely hung and had started no
  cell. The same driver later showed `00:00:00` CPU after 20 minutes and was PERFECTLY HEALTHY, because
  it was blocked waiting on a child burning CPU (`346850` 0:00 -> child `357145`, 102 s elapsed, 1:44
  CPU, state `Rl`). A parent blocked on a working child is the NORMAL shape of a driver. So walk the
  tree with `ps -eo pid,ppid,time,stat` and ask whether any DESCENDANT is accumulating CPU; reporting a
  healthy driver as hung would have had someone kill a running cell.
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
