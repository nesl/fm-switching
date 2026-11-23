# OVERNIGHT HANDOFF (D187). READ THIS FIRST.

## STATE AT 09:15Z (01:15 PST) 2026-11-23: NO AUTONOMOUS WORK REMAINS. A RESUMED SESSION SHOULD STAND DOWN.

EVERYTHING D187 ASKED FOR IS DONE OR IS WAITING ON A USER DECISION. If you are a watchdog-resumed
session, read this section, confirm the three facts below, and STOP. Do not invent new work, and do
not re-run anything: the GPU is busy with the _kv0.5 sweep, which runs autonomously on the H100 and
needs nothing from this box.

THE THREE FACTS TO CONFIRM, each cheap:
  1. origin/main carries reports/MORNING_SUMMARY_2026-11-23.md (a30147c2 or later), which includes
     the rung-2 verdict, the rung-3 verdict on all four seeds, the rung-4 block, every overnight
     decision, and the open items.
  2. The H100 is running the _kv0.5 sweep (llf s4 landed at 3867119e). GPU not idle.
  3. No cell list is awaiting a proof from this box.
If all three hold, there is nothing to do. Touch ops/heartbeat and exit.

WHAT IS FINISHED, with its commit:
  RUNG 2  SETTLED. c5attr is rung 2 under D184; no shares version met all three checks at all four
          seeds. r1 is the best shares version (check 2: 0.7229 / 0.9773 / 0.7727 / 0.8906) and is
          the TRADE-OFF ABLATION. r2 is REFUTED by its own pre-registered failure condition.
          Verdict in research/EXPERIMENTS.md StudyD179-SHARES and in the morning summary.
  RUNG 3  RUN AND SCORED, four seeds, at 3a6fb3e0. Check 2 PASSES EVERYWHERE (99 to 106 percent
          retention), check 3 PASSES EVERYWHERE, check 1 FAILS at s4, s6 and s7 (by 0.0013, 0.0299
          and 0.0788). Meets all three at s5 only, so by the same rule it does not qualify.
  RUNG 4  BUILT AND PROVED, INCLUDING Step 2b at 0.25x on the c5attr base, cell list posted with a
          matched-memory control. IT CANNOT RUN, and must not be unblocked overnight: see below.

THE FINDING THAT MATTERS MOST, and it is about the problem rather than any arm: shares and r1 pass
check 1 everywhere and fail check 2 everywhere; rung 3 passes check 2 everywhere and fails check 1 at
three seeds. ALERTS AND ROBOT TRADE AGAINST EACH OTHER UNDER BOTH MECHANISMS, IN OPPOSITE
DIRECTIONS. That argues the binding constraint is the shared resource, not either policy's logic.

## WHY YOU MUST NOT ITERATE FURTHER WITHOUT THE USER

RUNG 3's failing margins at s4 (0.0013) and s6 (0.0299) are INSIDE the run-to-run variance measured
tonight (0.05 to 0.06 on pooled dashcam, from the gain-0 control against the committed c5attr base,
which are decision-identical dry). So rung 3 is AT PARITY on alerts at those seeds. Chasing a 0.0013
shortfall would be TUNING TOWARD PASSING, which D187 (3) forbids outright. Only s7's 0.0788 is
clearly outside the noise.

RUNG 4 is blocked because `arms_v6cf` imports `cf_protect_defer`, which calls
`cf_objective.attainment_margin` AT IMPORT TIME, and that function exists ONLY in an UNCOMMITTED
edit in the shared worktree at /tmp/claude-1001/mapwt. Its registration was REVERTED at 67dd0514
after it made origin/main unimportable and killed five cells at launch. DO NOT re-add the
registration. DO NOT push that edit: it is half-finished D177 work whose harm side was never
converted, and unproven policy code must not go in to unblock a GPU.

## THE RULE THAT CAUSED THE ONE OUTAGE TONIGHT, repeated because it is easy to miss

A PROOF MUST RUN ON A TREE CONTAINING ONLY WHAT IS COMMITTED. The shared worktree has uncommitted
live-path edits (arms.py, coordinator.py, hybrid_arm.py, share_admission.py, v5/cf_objective.py).
Digest proofs there are safe ONLY because matching a committed bar is the one direction a dirty tree
cannot fake. An IMPORT or REGISTRATION proof has no such protection and must use a clean checkout.

## OPEN ITEMS, ALL FOR THE USER, none to be actioned overnight

  1. Floors and W_max: the recall floor was derived from the BASE arm's COLD questions (7,717
     uncached); rung-2 questions are warm at 1,177 to 1,438, which would give 12 to 18 instead of
     655.8. ALERT IS UNAFFECTED. Shrinking it would make recall MORE oversize, because a share is
     floor plus a cut of the flexible pool. Decide which job the floor is doing first.
  2. The arms_v6state id(obs) cache fix: prepared behind `live2_qcache_key_fix`, DEFAULT OFF, used
     in no cell. It CHANGES rung-2 decisions at seed 6. Live effect cannot be bounded from dry
     replays. Enabling it means rerunning the final rung-2 arm AND its comparators together.
  3. The assistance image grid: no D-row authorises the per-type cost; resizing would help the arm
     under test, which is why it was not done.
  4. check 1 is a ONE-SIDED test with no tolerance, and three rung-3 verdicts turn on margins at or
     inside measured variance. Whether it should carry a tolerance is methodological.
  5. The gzipped coordinator_result reads as ABSENT in the scorer with no error. A guard that FAILS
     LOUDLY would be better than a quiet fallback.
  6. Two over-broad `mv` allow rules in .claude/settings.local.json, flagged by Claude Code itself.

## WATCHDOG NOTE

Each `claude -c -p` resume is ONE-SHOT: it does its work and exits, so the heartbeat goes stale and
the next cron tick restarts another. That is why the restart counter climbs even when nothing is
wrong. With no autonomous work left, the correct behaviour for a resume is to confirm the three
facts above and exit, which costs one cheap check rather than a wasted iteration.

---

## STATE AT 00:02 PST, 2026-11-23, from a watchdog-resumed session. READ THIS BEFORE TOUCHING RUNG 3.

THE RUNG-3 GRID IS PROGRESSING NORMALLY AND MUST NOT BE RERUN. Completed and VALID:

  covex-v6-fair-c5attr        s4  robot 122/132  ss 337/357  dashcam MEETS  pooled 0.5074
  covex-v6-fair-c5attr        s5  robot 114/127  ss 343/356  dashcam MEETS  pooled 0.4921
  covex-v6-fair-c5attr-gain0  s4  robot 119/132  ss 337/357  dashcam FAILS  pooled 0.2134
  covex-v6-fair-c5attr-gain0  s5  robot 114/127  ss 349/356  dashcam FAILS  pooled 0.2461

c5attr s6 started about 23:52 and should end about 00:14; s7 follows, to about 00:36. The driver log
commits only BETWEEN cells, so the absence of a start line for s6 is expected while it runs.

A TRAP I NEARLY FELL INTO, RECORDED SO THE NEXT SESSION DOES NOT. Several run directories under
runs/ contain ONLY mm_gate.json and mm_uuid_check.json, with NO cell.json:

  covex-v6-fair-c5attr_n16_s6_...            IN PROGRESS, preflight files written first
  covex-v6-fair-c5attr_n16_s7_...            NOT STARTED YET
  ..._rerun directories for gain0 s4, gain0 s5, c5attr s5, c5attr s6, c5attr s7

THESE ARE NOT FAILED CELLS. The _rerun directories are artefacts of the 22:46 arms.py import
incident: driver v28 auto-skipped the five cells that died at launch, creating _rerun attempts that
also died, and the H100 then UN-SKIPPED them so they ran under their ORIGINAL names, which is why
the plain gain0 s4, c5attr s5 and gain0 s5 directories are complete and valid. A session that reads
"stub only" as "failed" could conclude the grid broke and rerun valid cells, which the H100's
standing rules forbid outright ("never rerun a valid cell").

WHAT I DID NOT DO, DELIBERATELY: I did not score a partial grid. Two of four seeds are in, and the
D179 verdict is PER SEED with no pooled rescue, so a two-seed score is not a result and would invite
being quoted as one.

THE TWO-SEED CONTRAST SO FAR, as an indication and not a verdict: the ordering feed roughly DOUBLES
pooled dashcam on-time against its own gain-0 control, 0.5074 against 0.2134 at s4 and 0.4921
against 0.2461 at s5, with robot +3 then unchanged and assistance 0 then -6. Both treatment cells
clear the 0.25 per-device bar comfortably; both controls sit NEAR it, so the FAIL label on the
control is a threshold crossing on a quantity whose run-to-run variance is about 0.05 to 0.06 here
(measured from gain0 against the committed c5attr base, which are decision-identical dry). Quote the
DOUBLING, which is 4 to 6 times that variance, not the label flip.

NEXT STEP, when s6 and s7 land: score all four seeds with the committed pre-registered scorer,
unchanged, using --shares-arm covex-v6-fair-c5attr, and DECOMPRESS coordinator_result.json.gz first
or the diagnostics read as absent without error.

RUNG 4 REMAINS UN-GATED AND CANNOT RUN: its registration was reverted at 67dd0514 because
arms_v6cf imports cf_protect_defer, which calls cf_objective.attainment_margin at import time, and
that function exists only in an UNCOMMITTED edit in the shared worktree. Do not re-add the
registration and do not push that edit to unblock anything: it is half-finished D177 work whose harm
side was never converted.

THE SHARED WORKTREE AT /tmp/claude-1001/mapwt HAS UNCOMMITTED LIVE-PATH EDITS (arms.py,
coordinator.py, hybrid_arm.py, share_admission.py, v5/cf_objective.py and others). Anything proved
there may not hold on origin; that is exactly what caused the 22:46 outage. Prove imports and
registrations on a CLEAN checkout.

# OVERNIGHT HANDOFF (D187). READ THIS FIRST.

## STATE AT 07:05Z (23:05 local), rewritten by a watchdog-resumed session

THE SECTIONS BELOW THIS ONE WERE WRITTEN AT 05:25Z AND ARE NOW FOUR HOURS STALE. They predate the
rung-2 verdict, the morning summary, rung 3, rung 4, and an outage. Read THIS section; treat the
rest as history. I am a watchdog-resumed session: the previous worker's heartbeat went stale at
625 s and its background tasks were orphaned, so it had ended. I claimed `ops/heartbeat` first.

ENVIRONMENT NOTE THAT WILL WASTE YOUR TIME OTHERWISE: `conda` is NOT on a resumed session's PATH
(login shell is sh). Use `/home/pragya/miniconda3/bin/conda run -n fmtk`. And `conda run` does NOT
forward stdin, so a heredoc piped into it runs nothing and EXITS 0: pass a file.

### RUNG 2 IS SETTLED. D184 APPLIES: c5attr IS RUNG 2.

No shares version met all three D179 checks at all four seeds, which is the rule. Check 2, scored by
the committed pre-registered scorer with its positive control exact:

  shares  0.30 / 0.56 / 0.33 / 0.28      0 of 4 pass
  r1      0.7229 / 0.9773 / 0.7727 / 0.8906   1 of 4   BEST SHARES VERSION
  r2      0.53 / 0.98 / 0.77 / 0.875     1 of 4   REFUTED by its own failure condition

Checks 1 and 3 PASS at all four seeds for every version. r1 is the TRADE-OFF ABLATION: it restores
alert attainment ABOVE base at every seed (0.744 to 0.820, where the committed rung 2 sits at 0.188
to 0.276, WORSE than base) and holds assistance at 96 to 100 percent, paid for in robot on-time.
The morning summary is committed at `reports/MORNING_SUMMARY_2026-11-23.md` (36b8da6b) and the
`StudyD179-SHARES` row carries the full verdict. NOTHING FURTHER IS OWED ON RUNG 2.

### AN OUTAGE I CAUSED, AND WHAT IT STILL BLOCKS

I pushed a rung-4 registration line into `arms.py` that made origin/main UNIMPORTABLE: it pulls in
`cf_protect_defer`, which calls `cf_objective.attainment_margin` AT IMPORT TIME, and that function
exists ONLY in an UNCOMMITTED local edit to `v5/cf_objective.py` in the shared worktree. Every arm
died at cell start. Reverted at `67dd0514`; the H100 confirmed the import on a full checkout, lifted
its HOLD, and restarted with driver v29, which now STOPS AND HOLDS when a cell produces no
cell.json within 120 s instead of auto-skipping. GPU idle 22:45 to 22:48 only. Recorded at
`eaefd73e`.

WHAT IT BLOCKS: RUNG 4 CANNOT RUN. Its registration is still reverted (commented, with the reason
in place, so do not simply re-add it). `V6CFPD_CELLS` is posted and un-gated. Restoring it requires
EITHER committing the `cf_objective` change WITH ITS OWN PROOF, or making `cf_protect_defer` not
depend on it at import time. The previous session deliberately chose NOT to push that change because
it is half-finished D177 work whose HARM side was never converted. DO NOT push unproven policy code
to unblock a GPU. If you think rung 4 is worth unblocking tonight, the honest route is the second
one, and it needs its own proof.

### RUNG 3 IS RUNNING AND ONLY ONE SEED HAS SCORED

DO NOT MISTAKE THE EMPTY DIRECTORIES FOR DATA. This is the trap in the current tree:

  covex-v6-fair-c5attr s4                       HAS cell.json, VALID, the only scored cell
  s5, s6, s7 and both -gain0 cells              directories exist with NO cell.json
  the same names with a `_rerun` suffix          also exist with NO cell.json

Every one of those empty directories is from 22:43 to 22:45, BEFORE the import fix: their `.stdout`
files carry the `AttributeError: module 'cf_objective' has no attribute 'attainment_margin'`
traceback, and they contain only `mm_gate.json` and `mm_uuid_check.json`. THEY ARE LAUNCH FAILURES,
NOT RESULTS. A session that globs the run directory and scores whatever matches will silently pick
them up. Check for `cell.json` before using any cell.

The H100 restarted the queue at 22:48 on `67dd0514`: -gain0 s4, c5attr s5, -gain0 s5, c5attr s6,
c5attr s7, to about 00:40 local, then the `_kv0.5` sweep resumes.

s4's RESULT, for the record: covex-v6-fair-c5attr robot on time 122/132 against the c5attr base's
117 and base's 35, SS 337/357, dashcam MEETS at pooled 0.507 with worst device 0.473 where the
c5attr base FAILS at 0.263, by_deadline 0.629, robot late 8 inside the bound of 10. So at s4 the
ordering consumer improves robot slightly AND flips the dashcam verdict. ONE SEED. The other three
are the test, and nothing should be written up as a rung-3 result until they land.

### THE NEXT STEP

1. WAIT for the four remaining rung-3 cells. Do not score a partial grid as if it were complete.
2. When they land, score with the COMMITTED scorer, unchanged:
     /home/pragya/miniconda3/bin/conda run -n fmtk python \
       experiments/orchestration/live2/d179_rung2_verdict.py --runs <dir> \
       --shares-arm covex-v6-fair-c5attr --rung2-arm covex-v6-state-uo-c5attr \
       --out ... --report ... --pins results/orchestration/live2/frozen_test/d179_rung2_verdict_prereg.json
   READ THE `positive control: PASS` LINE FIRST. If it is not that, the scorer is broken rather than
   the cells. Decompress any `coordinator_result.json.gz` before scoring, or the diagnostics read as
   ABSENT and will be mistaken for zero.
3. Rung 3's attribution is already established and does not need re-deriving: ORDERING is the whole
   contribution, 4,512 differing decisions against the gain-0 control, with the ORDER-ONLY arm
   byte-identical to the both-consumers arm and SPLIT-ONLY at exactly 0, replicated independently by
   three sessions to the digit.
4. Leave rung 4 blocked and say so. Leave the six open items for the user.

### THE SIX OPEN ITEMS FOR THE USER, all in reports/OVERNIGHT_DECISIONS.md with evidence

floors and W_max regime (D188 (1)); the `id(obs)` cache fix prepared behind an OFF switch and never
used, which DOES change rung-2 decisions at seed 6; the assistance image grid no D-row authorises;
the assistance control that was written on a shared counter and so was unfalsifiable; the gzipped
`coordinator_result` scorer defect; and two over-broad `mv` allow rules in `.claude/settings.local.json`.

---

## HISTORY BELOW THIS LINE, WRITTEN AT 05:25Z AND SUPERSEDED


## STATE AT 05:25Z (21:25 local), written by a SECOND watchdog-resumed session

The previous worker's heartbeat went stale at 1,109 s and the watchdog restarted me at 05:10:01Z in
tmux `fmsw-overnight`. I claimed `ops/heartbeat` immediately. Note for whoever follows: `conda` is
NOT on this session's PATH (login shell is sh); use `/home/pragya/miniconda3/bin/conda run -n fmtk`.

### THE FALLBACK CONDITION IS NOW SATISFIED, measured with the committed scorer

r2 s4 and s5 scored with the committed pre-registered scorer, `--shares-arm
covex-v6-state-shares-r2`, gz decompressed first, POSITIVE CONTROL PASS 4 of 4 cells exact:

  r2 s4  retention 0.5301  check 2 FAIL   (r1 0.7229)   base 35, uo 118, r2 79
  r2 s5  retention 0.9773  check 2 PASS   (r1 0.9773)   base 27, uo 115, r2 113

Checks 1 and 3 PASS at both. So r2 FAILS AT s4 and therefore CANNOT meet the rule "all three checks
at all four seeds", whatever s6 and s7 return. r1 also fails (s4, s6, s7). THE BEST SHARES VERSION
FAILS AT AT LEAST ONE SEED, which is exactly the D184 trigger.

### WHAT I DID NOT DO, AND WHY

I did NOT declare D184 and post rung-3 cells, for two reasons that a later session should weigh
rather than inherit:

1. THE DEADLINE IS AMBIGUOUS AND NOBODY RESOLVED IT. The rule says "by about 05:00". Local time is
   UTC-8, so 05:00 LOCAL is 13:00Z and 05:00Z was 25 minutes ago. The previous session asked the
   user which was meant and got no answer. Under the LOCAL reading there are still about 7.5 hours,
   and D187 (2) says to keep iterating. Under the UTC reading the fallback is already due. The
   CONDITION is met either way; only the timing of the declaration turns on it.
2. WHICH VERSION IS "BEST" IS NOT YET DETERMINED. r1 is ahead on s4 (0.7229 against 0.5301) and
   equal on s5. If r2 s6 and s7 come in above r1's 0.7727 and 0.8906, "best version" becomes a
   judgement rather than a reading, and that judgement belongs in the write-up. r2 s6 and s7 are
   running on the H100 and cost nothing of ours, so the complete grid is worth having before
   anything is written up as the ablation.

### THE NEXT STEP

1. When r2 s6 and s7 land, score all four seeds with the committed scorer, gz decompressed, and
   record the complete r1-against-r2 table.
2. Then apply D184: c5attr is rung 2; rungs 3 and 4 build on it; the BEST shares version is
   reported as the TRADE-OFF ABLATION. State which version was chosen as best and on what basis.
3. Rung 3 is already built base-agnostic and `covex-v6-fair-c5attr` is registered, as is
   `covex-v6-cf-pd-c5attr` for rung 4, so neither needs new code to run on the c5attr base. Posting
   those cell lists is the way to keep the H100 fed under D187 (4) once r2's grid is complete.

### WHAT NOTHING TONIGHT HAS CHANGED, and must stay that way

Floors and W_max are frozen per D188 (1). The `id(obs)` cache fix is NOT applied per D188 (2), and
the agent that was preparing it behind an OFF switch landed NOTHING, so the live path is untouched:
`live2_qcache_key_fix` appears nowhere. That is the state the ruling requires.


## STATE AT 04:55Z (20:55 local), written by a WATCHDOG-RESUMED session

I am a watchdog-resumed session. The previous interactive session stopped at about 04:38Z; its
heartbeat went stale at 698 s and the watchdog started me at 04:50:01Z in tmux `fmsw-overnight`
with `--permission-mode auto`. I claimed `ops/heartbeat` immediately so no second session spawns.
NOTHING WAS LEFT HALF-APPLIED IN THE LIVE PATH.

### THE SCOREBOARD

check 2 retention, bar 0.90, scored by the committed pre-registered scorer:

  version                 s4      s5      s6      s7     passes
  shares (pre-fix)      0.30    0.56    0.33    0.28     0 of 4
  r1 (cold-pricing)     0.7229  0.9773  0.7727  0.8906   1 of 4   <- BEST SHARES VERSION
  r2 (queue-register)   0.53    pending pending pending  0 of 1 so far

Checks 1 and 3 PASS at all four seeds for both r1 and r2 s4. Only check 2 fails.

### r2 s4 WENT THE WRONG WAY, and the pre-registered reading is "fired and did not help"

robot on time 79 against r1's 95; `release_infeasible_recall` 47 against r1's 34, where the
pre-registration expected it to FALL. THE LINK DID FIRE: median `queued_uncached_ahead` at the
skips fell from 1,496 to 1,101, so the corrected input reached the decision. The refusals are now
SIZE-dominated (median est_first_token 1.855 s against 1.758 s remaining). The likely system
explanation, NOT yet measured: a more permissive re-check admits more work, which raises W, which
makes share admission deny more (`share_deny_recall` 467 -> 643), so the arm settles at a worse
equilibrium. HARM BOUND HELD: 4 late against a bound of 10.

TWO CAVEATS THAT MUST TRAVEL WITH THAT NUMBER: it is ONE SEED, and live-trajectory variance between
r1 and r2 at the same seed is NOT MEASURED. A 0.72 to 0.53 swing could be partly noise.

### THE NEXT STEP

1. When r2 s5, s6, s7 land, score all four with the COMMITTED scorer, unchanged, passing
   `--shares-arm covex-v6-state-shares-r2`. The scorer exposes the arm as a parameter, so r2 is
   scored WITHOUT editing a pre-registered instrument. Read the
   `positive control: PASS (8/8 cells exact)` line FIRST.
2. BEFORE SCORING r2, DECOMPRESS `coordinator_result.json.gz` TO `coordinator_result.json` in each
   r2 run directory. My own P0 serialisation made that file large enough that the harness now
   gzips it, and the scorer reads a missing file as `{}` with NO ERROR, so every diagnostic from it
   silently reads as ABSENT. The three CHECKS are unaffected (they come from `cell.json`'s
   `score.score.sweep[0]` and `outcomes.jsonl.gz`). Recorded in OVERNIGHT_DECISIONS.md.
3. Apply the FALLBACK TRIGGER below exactly as written.

### WHAT IS NOT DONE, and is optional tonight

D188 (2), preparing the `id(obs)` cache fix behind an OFF switch with its proofs, was started and
its agent was STOPPED when the previous session ended. IT LANDED NOTHING: no commit, and
`live2_qcache_key_fix` appears nowhere in `arms_v6state.py`. The live path is untouched, which is
the state the user's ruling requires tonight. It can be redone tomorrow or by a later session; it
is NOT a blocker for the r2 verdict or the fallback.


## THE FALLBACK TRIGGER. READ THIS BEFORE SCORING ANYTHING.

USER CORRECTION 2026-11-23: an earlier version of this file said D184 applies "if check 2 still
fails at 3 or more seeds". THAT WAS WRONG AND IS WITHDRAWN. Do not use a count of failing seeds as
the trigger.

THE RULE (D184 with D187 (2)): SHARES IS RUNG 2 ONLY IF IT MEETS ALL THREE D179 CHECKS AT ALL FOUR
SEEDS, 4, 5, 6 AND 7. There is no partial credit, no majority, and no pooling: the scorer's own rule
is that the verdict is per seed because a pooled figure can hide a per-seed failure.

SO: IF, BY ABOUT 05:00, THE BEST SHARES VERSION STILL FAILS ANY CHECK AT ANY SEED, APPLY D184.
  c5attr becomes rung 2.
  Rungs 3 and 4 build on c5attr.
  Shares, in its BEST version, is reported as the TRADE-OFF ABLATION, not as a failure: it restores
  alert attainment above base at every seed while giving back robot on-time, and that is the result.

WHERE THINGS STAND AGAINST THAT RULE, so nobody has to infer it: r1 passes all three checks at s5
ONLY (check 2 at 0.7229 / 0.9773 / 0.77 / pending for s4 / s5 / s6 / s7). ONE SEED PASSING IS NOT
THE TARGET. r2 therefore has to pass all three checks at ALL FOUR seeds to displace the fallback,
and r2's own pre-registration (3ed47764) treats s4 and s6 as targets with s5 as a control that must
not regress. If r2 lifts s4 and s6 but drops s5 below 0.90, THAT IS STILL A FAILURE OF THE RULE.


## 03:45Z UPDATE, written by a WATCHDOG-RESUMED session

THE RESUME WORKED. The interactive session died (the user warned SSH might crash); the heartbeat
went stale at 1,170 s and the watchdog started this session at 03:30:01Z with
--permission-mode auto. This session HAS write access: it has read the cells, written an artefact
and pushed. So the user's auto-mode ruling closed the gap that made earlier restarts useless.
Whoever reads this next: touch ops/heartbeat when you start, or the watchdog will spawn a second
worker in ten minutes.

STATE: r1 s4 and s5 are on origin. s6 and s7 were still running. The H100 is autonomous and does
not need this session.

### r1 RESULTS SO FAR, against the pre-registered check at c7c60e5b

  s4: robot on time 60 -> 95 (uo 118, base 35); recall skips 70 -> 34 (bar was <= 13, NOT met);
      check 2 retention 72 percent (bar 90), FAIL; checks 1 and 3 PASS; no lateness (2 late).
  s5: recall skips 48 -> 15, so the fix works HARDER at s5 than at s4.

The failure condition does NOT apply: both headline counters moved, so the mispriced-size
explanation is confirmed in direction and incomplete in size.

### THE RESIDUAL IS A QUEUE QUESTION, NOT A SIZE QUESTION (42aeb03d)

Read DIRECTLY from release_infeasible_events, which the P0 instrumentation shipped with the fix.
TWO HYPOTHESES REFUTED, including the user's and mine:

  USER'S (warms and touches never update last_telemetry_cached_tokens): REFUTED. Only 7 of 34 s4
  prefixes are multiples of the 1,024 build-piece size; the rest are values built_tokens cannot
  produce. The corrector's guard at coordinator.py:1702 is SESSION-based, not KIND-based.

  MINE (the telemetry lags because history grows between completions): REFUTED by the same values,
  and already weakened by the user's arithmetic (a 6,900-token gap needs ~76 frames of growth).

  BELIEF COLD WHILE ENGINE WARM: 0 of 34 at s4, 3 of 15 at s5. Not the main lever at either seed.

  THE FINDING: at s4 the size term ALONE exceeds the slack in only 9 of 34 skips. The other 25 are
  feasible on their own size and are refused only once queued_uncached_ahead is added (p50 1,496,
  max 9,839). At s5 it is 7 by size and 8 by queue.

### THE NEXT CANDIDATE FIX, AND WHY IT WAS NOT APPLIED

The re-check passes queued_uncached_ahead=self._uncached_in_flight, which drains at COMPLETION and
so carries the DECODE TAIL of requests whose prefill is already done. The work actually ahead in the
prefill queue is the submit-to-FIRST-TOKEN quantity, which the coordinator already tracks as the
D179 W tracker. share_admission.py's own docstring says _uncached_in_flight is "the right queue
input for the D174 budget charge and the wrong resource here"; that was applied to W and NOT to the
re-check.

DO NOT APPLY IT WITHOUT SETTLING THIS FIRST: the D162 fit's own regressor definition is NOT
recoverable from the committed artefacts. cost_model_gate_d162.json records the coefficient and that
the term varies, but not whether the regressor was completion-based or first-token-based. Swapping
the input would change a FITTED model's input on an unestablished premise AND would lower the
predicted first-token time, admitting more requests, which is the direction that flatters the arm
under test. D187 (3) forbids that. WHAT WOULD SETTLE IT: the regressor definition in the D162
fitting script or its input frame. If the fit used a first-token queue, swapping is a correction; if
completion-based, swapping is a recalibration and the coefficient must be refitted.

DIRECTION DISCIPLINE: understating the queue is the UNSAFE direction, admitting work that cannot
fit, which surfaces as LATENESS. r1 s4 has only 2 late robot requests, so there is no lateness
budget to spend.

### NEXT STEP

1. When r1 s6 and s7 land, score all four with the COMMITTED pre-registered scorer, unchanged:
     conda run -n fmtk python experiments/orchestration/live2/d179_rung2_verdict.py \
       --runs <dir> --out results/orchestration/live2/frozen_test/d179_rung2_verdict_r1.json \
       --report reports/study_d179_rung2_verdict_r1.md \
       --pins results/orchestration/live2/frozen_test/d179_rung2_verdict_prereg.json
   Base cells are hybrid-F-lhreq-noc3_n16_s{4,5,6,7}_1200s_h27_3t_L3_epg_rq30 (D172 names).
   READ THE `positive control: PASS (8/8 cells exact)` LINE FIRST.
2. Apply the fallback trigger exactly as stated in THE FALLBACK TRIGGER section at the top of this file. The earlier wording here, "if check 2 still fails at 3 or more seeds", was WRONG and is withdrawn by user correction: the trigger is ANY check failing at ANY seed,
   shares is reported as a trade-off ablation, and rungs 3 and 4 build on c5attr.

---

## EARLIER STATE, KEPT FOR CONTEXT

## STATE AT 03:05Z. THE WORK IS NOT BLOCKED ON THIS SESSION.

THE GPU WORK IS AUTONOMOUS AND DOES NOT NEED ME. V6SHARES_R1_CELLS is gated by the H100 at
79eedc6d and runs covex-v6-state-shares-r1 at seeds 4, 5, 6, 7 after the covex-v6-base s4 _kv0.5
cell ending about 18:47 local. The H100 reports each seed itself. If this session is gone, THE
CELLS STILL RUN.

THE NEXT STEP, when the four r1 cells are on origin:
  1. Assemble a runs dir with base, uo and r1 at seeds 4 to 7. The base is
     hybrid-F-lhreq-noc3_n16_s{4,5,6,7}_1200s_h27_3t_L3_epg_rq30 (committed cells keep their
     ORIGINAL names under D172; there is no covex-v6-base cell at these seeds, and the _L3_epg
     cells WITHOUT rq30 are a different workload).
  2. Run the COMMITTED PRE-REGISTERED scorer, unchanged:
       conda run -n fmtk python experiments/orchestration/live2/d179_rung2_verdict.py \
         --runs <dir> --out results/orchestration/live2/frozen_test/d179_rung2_verdict_r1.json \
         --report reports/study_d179_rung2_verdict_r1.md \
         --pins results/orchestration/live2/frozen_test/d179_rung2_verdict_prereg.json
     READ THE `positive control: PASS (8/8 cells exact)` LINE FIRST. If it is not that, the scorer
     is broken, not the cells, and the comparison must not be read.
  3. Score against the pass check pre-registered at c7c60e5b, WITH ITS FAILURE CONDITION:
     release_infeasible_recall falls from 70 toward at most 13 at s4; robot_pool_on_time rises from
     60 toward 118; assistance must NOT move (positive control). IF THE FIRST TWO DO NOT MOVE, THE
     NAMED EXPLANATION IS WRONG and is reported as wrong. The fix is not kept for being harmless.
  4. Watch the lateness signature the H100 named: skips falling WITHOUT on-time rising to match
     would mean a stale-prefix residue rather than a fix.

IF SHARES STILL FAILS CHECK 2 AFTER r1, D184 APPLIES: c5attr becomes rung 2, shares is reported as
a trade-off ablation, and rungs 3 and 4 build on c5attr. Do not iterate further on shares past
about 05:00.

## WHAT IS FOR THE USER AND MUST NOT BE DONE AUTONOMOUSLY

1. RE-DERIVING THE FLOORS AND W_max. The fix drops the policy's predicted recall u by roughly an
   order of magnitude, so the recall floor and W_max may now be mis-sized for the regime they
   govern. Methodological under CLAUDE.md. r1 runs on the EXISTING frozen constants.
2. THE arms_v6state.py:236 id(obs) CACHE FIX. Decision-neutral on 12 of 12 dry rung-2 cells, but a
   dry replay cannot bound the LIVE effect.
3. THE ASSISTANCE IMAGE GRID. Assistance images are sent at native resolution (p50 1,307 image
   tokens) while alert and recall frames are downsized offline (338 and 90). No D-row authorises
   the per-type cost. Resizing would make assistance fit inside its share and would very likely
   help the arm under test, which is exactly why it was NOT done: the image grid is the workload.
4. THE PERMISSIONS FINDING. Watchdog-restarted sessions are effectively READ-ONLY: refused repo
   writes and even grep reads under /tmp/claude-1001/ where the workflow lives. The H100
   reproduced the same on its box. So a faithful restart produces a session that CANNOT continue
   the work. This limits what D187 (5)'s resilience plan can deliver and was not worked around.

## RESILIENCE AS IT NOW STANDS

ops/watchdog.sh, cron every 10 minutes plus @reboot, gated on ops/heartbeat with a 600 s staleness
threshold (shortened from 1,800 s at the user's request for a faster restart). Tested both ways:
fresh heartbeat does not restart, a staled one does. Its original condition was "does the tmux
session exist", which was wrong in BOTH directions, since the working session is not in tmux and
each spawned `claude -p` exits when its prompt ends, refilling the condition; it spawned three
sessions in twenty minutes before the gate.

THIS SESSION IS NOT IN TMUX AND CANNOT MOVE ITSELF THERE. It is attached to the user's client, so
an SSH loss kills it. That is the gap the watchdog exists for, and item 4 above is why the watchdog
cannot fully close it.

---

## EARLIER STATE, KEPT FOR CONTEXT

The user is away until morning and has granted autonomy under D187. A resumed session reads THIS
FILE FIRST, then continues the next step. Updated after every milestone and at least every 2 hours.

## D187 RULES, which autonomy does NOT relax

- Implementation bugs: fix, prove, rerun.
- Design changes: only when justified by a MEASURED mechanism. Each is a NEW LABELLED VERSION and
  is recorded in `reports/OVERNIGHT_DECISIONS.md` as OVERNIGHT DECISION, PROVISIONAL, with the
  evidence, for the user's morning review.
- NEVER change targets, deadlines, metrics, workload, seeds (never 1 to 3, never HOLDOUT),
  baselines, pass bars or the margin. NEVER drop or exclude data. NEVER tune a parameter toward
  passing: derive from FIT/DEV or from committed base cells only. REPORT EVERY RESULT WHATEVER ITS
  DIRECTION.
- If shares cannot be made to pass by about 05:00, apply D184: c5attr becomes rung 2, and rungs 3
  and 4 are built on it.
- Held or unproved code defaults OFF. One dry cell per process. STOP conditions still stop: record
  and move to the next track rather than idling.
- D166 commit rules. No Claude attribution. No em dashes.

## WHERE THINGS STAND AT 18:15

RUNG 2 VERDICT IS IN, and it is a split. Scored by the PRE-REGISTERED scorer
`experiments/orchestration/live2/d179_rung2_verdict.py` (written before any shares cell existed),
positive control PASS 8 of 8 cells, 48 of 48 counts exact. Committed at `a16f22eb`.

  seed | check 1 alert | check 2 robot retention | check 3 assistance
   4   | PASS          | FAIL 0.3012             | PASS
   5   | PASS          | FAIL 0.5568             | PASS
   6   | PASS          | FAIL 0.3333             | PASS
   7   | PASS          | FAIL 0.2813             | PASS

Bar 0.90. Base on-time 35 / 27 / 41 / 19; uo 118 / 115 / 107 / 83; shares 60 / 76 / 63 / 37.
Shares did what D179 was built to do (the committed rung 2 made alerts WORSE than base at every
seed; shares restores alert attainment ABOVE base at every seed and holds assistance above 96
percent). The price is the robot pool.

NOTE ON TWO READINGS, because D186's bars use the other one: the user's bars reconstruct as
`base + 0.9 x (uo - base)` on `by_deadline`, which is an ACCURACY that also falls back to the
DEVICE answer and so re-admits the side D177 excludes. On that reading shares clears s5 by a hair
(0.417 against 0.416) and fails s4, s6, s7. On the PRE-REGISTERED quantity (robot ON-TIME) it fails
all four. The committed figure is on-time.

## THE CURRENT HYPOTHESIS, and the gate for the pre-approved fix

The robot loss is in the SKIPS, not in lateness: at s4 shares sent 62 of 132 recall questions and
60 of the 62 were on time, while `release_infeasible_recall` was 70.

MISPRICED SIZE is the leading explanation and the fix for it is PRE-APPROVED by D187 (1).
`coordinator.py`, in `_submit_recall`:

    _uncached = (int(tokens) if s.residency_readiness() == "COLD"
                 else max(int(tokens) - int(getattr(s, "built_tokens", 0) or 0), 0))

The warm prefix is subtracted ONLY when readiness is not COLD. A COLD belief therefore predicts the
FULL history. The user measured rung-2 recall at 1,177 (uo) and 1,438 (shares) engine-reported
uncached, against a BASE median of 7,717 which is the cold, no-warming figure. So a COLD belief can
overestimate several-fold, and BOTH the share gate and the release re-check receive this same value,
so they would be wrong together.

IMPORTANT CORRECTION TO EARLIER WORK: the 7,717 median appears in
`results/orchestration/live2/frozen_test/d179_overrun_without_recall.json` and in
`share_capacity.FACTORS`. It is the BASE arm and does NOT describe rung 2. Any oversize analysis
built on it is wrong in magnitude: against recall's own share of 1,256.7, a 1,438 median is oversize
by 14 percent, not by 4.5x.

## 18:45 UPDATE: THE DIAGNOSIS LANDED, THE FIX IS APPLIED, CELLS NOT YET POSTED

(a) MISPRICED SIZE DOMINATES at every seed: 57 of 70, 44 of 48, 41 of 46, 44 of 46. So the
D187 (1) pre-approved branch applies and the fix is going in WITHOUT waiting for the user.

THE HYPOTHESIS WAS REFUTED AND THE REAL MECHANISM IS ADJACENT. Not a COLD belief: COLD-while-warm
is 8 of 210 skips, and readiness is GPU-WARM at 69 of 70 at s4, so the warm prefix WAS subtracted.
THE WRONG QUANTITY WAS. `built_tokens` counts only the coordinator's own 1,024-token build pieces
while the engine holds the whole history from the EP-G per-frame uploads. Median predicted u at s4
is 14,712 against the engine's own 1,050 on the SAME opportunity in uo, 15.6x. The size term alone,
zero queue, exceeded the slack in 29 / 30 / 23 / 32 skips; with the engine's count, 1 / 0 / 1 / 0.

DONE SO FAR:
- `c7c60e5b` pre-registration, committed BEFORE any cell, with the pass check AND its failure
  condition (if release_infeasible_recall and robot_pool_on_time do not move, the explanation is
  wrong and is reported as such rather than the fix being kept for being harmless).
- The fix is applied at `coordinator.py` (the D187 (1) block), reading
  `session.last_telemetry_cached_tokens`, which `engine_actions.py:358` already writes and which
  was read NOWHERE in the pricing path. MAX of it and `built_tokens`, since both are lower bounds.
- P0 instrumentation: `release_infeasible_events` and `share_events` are now serialised into
  `coordinator_result.json`, capped at 20,000 with the true total recorded beside them. Without
  this the r1 cells would be as unreadable as the four that forced the diagnosis to RECONSTRUCT
  every quantity with a declared proxy.
- `covex-v6-state-shares-r1` registered as a LABEL, proved arm-side IDENTICAL to
  `covex-v6-state-shares`, so the only difference is the coordinator's pricing.
- COMPARABILITY CHECKED, NOT ASSUMED: `budget_refusal` is ABSENT (not merely zero) in all eight
  committed rung-2 cells, so the mispriced charge never bound and `covex-v6-state-uo` stays a valid
  comparator for check 2. The dry prescreen on uo tests that directly: uo has no release re-check,
  so for it `_uncached` reaches only the budget charge, and if the budget never binds its digest
  must be UNCHANGED.

NEXT STEP, IN ORDER:
1. Read the two prescreen cells (`covex-v6-base` must stay af8befb9420ad86a / 12,085;
   `covex-v6-state-uo` must stay 9a4be873eb3c5fba / 14,218). A change in uo would mean the fix is
   NOT inert there and check 2's comparator would need rerunning before any r1 result is read.
2. Commit the fix, the P0 serialisation and the r1 label.
3. Post `runs/V6SHARES_R1_CELLS`: covex-v6-state-shares-r1 16 {4,5,6,7} _L3_epg_rq30, and tell the
   H100 to run them FIRST.
4. Score with the committed pre-registered scorer, unchanged.

REMEMBER THE TRAP, stated in the pre-registration: on a DRY cell
`last_telemetry_cached_tokens` is always None because there is no engine. The dry prescreen proves
the fix HARMLESS and proves NOTHING about whether it fires. THE FIRING PROOF MUST BE LIVE.

## IN FLIGHT RIGHT NOW

- Addendum 13 + 14 diagnosis (read-only, one agent, one report): per-skip classification
  (a) mispriced size / (b) delayed by the oversize rule into true infeasibility / (c) correctly
  infeasible / (d) other, for seeds 4 to 7; plus whether the `arms_v6state.py:236` `id(obs)` cache
  can change LIVE decisions.
- Addendum 13b (read-only, separate agent): image processor settings per query type, and whether
  assistance images are capped by the same rule.

## NEXT STEP WHEN THE DIAGNOSIS LANDS

IF (a) MISPRICED SIZE DOMINATES: it is an implementation bug against D179 (1) / D174. Fix so the
predicted uncached reflects the warm prefix the engine actually holds; prove with byte-identity of
every non-affected arm with switches off, plus a dry s4 report showing recall skips and
predicted-against-engine uncached; post `covex-v6-state-shares-r1` seeds 4 to 7 and let the H100 run
them FIRST. This is PRE-APPROVED: do not wait for the user.

OTHERWISE: D184 applies. c5attr is rung 2, shares is reported as a trade-off ablation, and rungs 3
and 4 build on c5attr.

## OPEN ITEMS QUEUED BEHIND THE RULING

1. `pending_by_type` is declared in `share_admission.allowed()` and NEVER READ, so D179 (3)'s
   "the flexible pool goes to types WITH PENDING WORK" is unimplemented and every share is tighter
   than specified. A write-only argument.
2. `arms_v6state.py:236` keys its `_queued_behind` cache on `id(obs)`, a MEMORY ADDRESS, because
   `obs.epoch` is a str and the isinstance test never fires. Likely cause of the documented
   "dry decisions do not reproduce across runs" defect. Fix HELD because the rung-2 grid was
   running; the grid is now complete, so it can proceed once addendum 14 reports.
3. The W overrun with ALERT ALONE (s5 370 time samples, s6 196) is NOT explained by the oversize
   account. Hypothesis, unverified: EP-G accumulates unsent frames, so a HELD alert's next request
   grows past alert's 2,223 share and becomes oversize and headroom-exempt. If true it also means
   shares changes the very quantity its floors were derived from.
4. Rung 3 (`covex-v6-fair`): pass condition MET by the ORDERING consumer alone, 3,902 differing
   decisions against gain 0, with the flexible split contributing exactly 0. Device lookup fixed at
   `3325e02c`. No live cell posted yet.
5. Rung 4 (protect-and-defer): built and proved, ABSENT LINK at 1x memory, 19 characteristic
   decisions at 0.25x. Not scored. Aimed at the late alert frames behind recall prefills.

## RESILIENCE (D187 (5))

- Watchdog: `ops/watchdog.sh`, cron every 10 minutes plus @reboot. It starts the track inside tmux
  (session `fmsw-overnight`) so an SSH outage cannot kill it, and resumes Claude with
  `claude -c -p` using ONLY the permission settings already configured. No permission bypass, no
  TLS change.
- TESTED BOTH WAYS at 18:12, logged in `ops/watchdog.log`: with a live session it logged
  "OK session alive" and did NOT restart or write state; with the session killed it created the
  tmux session and incremented the restart counter to 1. The restart path was tested with a DUMMY
  command rather than the real one, deliberately, so the test could not spawn a second Claude
  working the same repo concurrently. State was reset afterwards so the budget starts fresh.
- DELIBERATE LIMIT: a restart BUDGET of 6 per hour. Once spent the watchdog logs and STOPS rather
  than looping, because a session that dies that often is failing rather than unlucky, and a
  watchdog that keeps restarting a failing session is worse than none.
- Coordination with the H100 is through the repo only: cell lists and commits.

## LAST COMMIT

`a16f22eb` D179 rung-2 verdict. Cells pending on the H100: eco-llm s6 and s7, then the `_kv0.5`
sweep, which is its fallback queue while no new cell list is posted.
