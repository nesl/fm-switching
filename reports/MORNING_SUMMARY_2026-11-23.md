# MORNING SUMMARY, 2026-11-23

Written under D187 overnight autonomy. Everything below is committed and readable from the repo.
Where a number is mine rather than the committed scorer's, it says so.

## 1. THE HEADLINE

RUNG 2 IS c5attr, under D184. No shares version met all three D179 checks at all four seeds, which
is the rule (D184 with D187 (2), corrected mid-night after an earlier handoff wrongly said "3 or
more seeds"). The best shares version is r1 and it is reported as the TRADE-OFF ABLATION.

THE TRADE IS THE RESULT, not a consolation. The committed rung 2 (covex-v6-state-uo) bought its
robot gain by making ALERTS WORSE THAN BASE at every seed: dashcam pooled on-time 0.188 to 0.276
against base 0.457 to 0.638. Shares and r1 restore alerts ABOVE base at every seed (0.744 to 0.820)
and hold assistance at 96 to 100 percent, paid for in robot on-time. That is a real finding about
the design space and it stands whichever arm becomes rung 2.

## 2. PER-SEED TABLE, every rung-2 version

Robot on time, out of the seed's pool (132 / 127 / 121 / 105):

  arm                        s4        s5        s6        s7
  base hybrid-F-lhreq-noc3   35        27        41        19
  covex-v6-state-uo         118       115       107        83
  covex-v6-state-shares      60        76        63        37
  covex-v6-state-shares-r1   95       113        92        76
  covex-v6-state-shares-r2   79       113        92        75

CHECK 2, robot on-time gain retained, bar 0.90. Scored by the PRE-REGISTERED scorer
(experiments/orchestration/live2/d179_rung2_verdict.py, written and committed BEFORE any shares cell
existed), positive control exact on 8 of 8 cells:

  shares   0.30     0.56     0.33     0.28      0 of 4 pass
  r1       0.7229   0.9773   0.7727   0.8906    1 of 4 pass  (s7 misses by 0.0094, one question)
  r2       0.53     0.98     0.77     0.875     1 of 4 pass

CHECKS 1 and 3 PASS AT ALL FOUR SEEDS FOR EVERY VERSION. Check 1 (alert per-episode attainment at
least the base's) and check 3 (assistance within 2 s at least 90 percent, measured 96 to 100).

ROBOT LATE, against the pre-registered harm bound of 10 per seed: r1 2 / 1 / 5 / 0, r2 4 / 1 / 4 / 1.
The bound held everywhere, so no version traded skips for misses.

## 3. WHY r1 AND NOT r2

r2 IS A REFUTED MECHANISM under its own pre-registered failure condition
(reports/prereg_queue_register_r2.md): the queue-refused skips ROSE at both target seeds, 25 to 32
at s4 and 7 to 9 at s6. Rule 2 class: FIRED AND DID NOT HELP. Not an absent link, because
release_infeasible_alert fell at all three scored seeds and the fed queue value fell at the s4 skips.

THE MECHANISM IS A FEEDBACK LOOP, measured in d187_r2_diagnosis.json: a more permissive re-check
released more recall work (recall gate calls 2,442 to 3,246, admits 1,975 to 2,603), so w[recall] was
non-zero more often, so D179 (3)'s one-oversize-recall-at-a-time rule bit harder. 171 of the 176 rise
in share_deny_recall is `oversize_wait_for_own_type`, only 6 is w_max. The same extra foreground work
SQUEEZED BACKGROUND PIECES, so on the 31 shared skipped opportunities est_tokens was unchanged on 30
while the subtracted prefix fell by exactly one 1,024-token build piece on 10 rows, RAISING u and
worsening the SIZE term too. Both terms got worse.

TWO CLAIMS KEPT APART. The register fix is CORRECT ON ITS OWN TERMS (cost_model_gate_d162.py:97
builds the regressor over submit-to-first-token intervals, so W is the quantity the coefficient was
fitted on and _uncached_in_flight is not) and REFUTED AS A LEVER for check 2. It is NOT recommended
on correctness grounds alone, because it made s4 worse. That trade is yours.

NOT A SETTLED NEGATIVE: live-trajectory variance between r1 and r2 at the same seed is UNMEASURED.
Bounding it needs at least three repeat cells of one unchanged arm at one seed; none exist. The
MECHANISM account rests on counters far outside plausible replicate noise.

## 4. WHAT r1 FIXED, AND WHAT IT DID NOT

r1 corrected a mispriced recall size: `_submit_recall` subtracted `built_tokens`, the coordinator's
own 1,024-token build pieces, while the engine held the whole EP-G history. Median predicted u was
14,712 against the engine's 1,050 on the same opportunity, 15.6x. Mispriced size dominated the skips
at every seed (57 of 70, 44 of 48, 41 of 46, 44 of 46).

NOT THE HYPOTHESIS EITHER OF US HELD. We both expected a COLD residency belief. Readiness is
GPU-WARM at 69 of 70 skips at s4 and COLD-while-warm occurs at 8 of 210. The warm prefix WAS being
subtracted; the WRONG QUANTITY was.

THE RESIDUAL IS NOT FIXABLE WITH THE SIGNALS AVAILABLE. `cached_tokens` is min(resident prefix, that
request's own prompt), and a touch sends only confirmed frames while a build piece sends the built
prefix plus one slice, so NEITHER CAN EVER REPORT A PREFIX LARGER THAN THE BUILT ONE. Only a recall
presents the whole history. The telemetry is CENSORED, not stale. All three prefix candidates were
disqualified on direction, including two I proposed; one would have converted a skip into a late
answer on the exact row it targeted (measured 4.413 s first token against 2.953 s slack).

## 5. RUNG 3 AND RUNG 4

### RUNG 3 IS RUN AND SCORED, AND IT FAILS THE MIRROR IMAGE OF WHAT SHARES FAILED

Four seeds, scored by the SAME committed pre-registered scorer, positive control exact on 8 of 8
cells, with `--shares-arm covex-v6-fair-c5attr` and `--rung2-arm covex-v6-state-uo-c5attr`:

  seed | check 1 alert vs base      | check 2 robot retained | check 3 assistance
   4   | FAIL by 0.0013            | PASS 1.0610            | PASS
   5   | PASS by 0.0307            | PASS 0.9886            | PASS
   6   | FAIL by 0.0299            | PASS 1.0625            | PASS
   7   | FAIL by 0.0788            | PASS 1.0156            | PASS

CHECK 2 PASSES AT ALL FOUR SEEDS AT 99 TO 106 PERCENT RETENTION, so rung 3 keeps essentially the
whole rung-2 robot gain over base and slightly exceeds it at three seeds. CHECK 3 PASSES EVERYWHERE.
CHECK 1 FAILS AT THREE SEEDS. So rung 3 meets all three checks at s5 only, exactly as shares did,
and by the same rule it does not qualify.

THE SYMMETRY IS THE FINDING, and it is worth more than either arm alone:
  shares and r1, on the shares base:   check 1 PASS everywhere, check 2 FAIL everywhere
  rung 3, on the c5attr base:          check 2 PASS everywhere, check 1 FAIL at three seeds
Alerts and robot trade against each other under BOTH mechanisms, in opposite directions. That argues
the binding constraint is the shared resource rather than either policy's logic, which is a claim
about the problem and not about an arm.

WHAT RUNG 3 DOES, measured against its own gain-0 control at the two seeds that have one: the
ordering feed roughly DOUBLES pooled dashcam on-time, 0.5074 against 0.2134 at s4 and 0.4921 against
0.2461 at s5, with robot +3 then unchanged and assistance 0 then -6. Against the c5attr base at all
four seeds it is ahead on robot at three and -1 at s5, ahead on assistance at two, and ahead on
pooled dashcam at all four (0.49 to 0.55 against 0.26 to 0.33).

TWO MARGIN CAUTIONS THAT DECIDE THREE OF THE FOUR VERDICTS, and neither should be used to argue the
verdict away:
  1. s4 fails check 1 by 0.0013 and s6 by 0.0299, both INSIDE the run-to-run variance measured
     tonight (0.05 to 0.06 on pooled dashcam, from gain0 against the committed c5attr base, which
     are decision-identical dry). Only s7's 0.0788 is clearly outside it. So rung 3 is at PARITY
     with base on alerts at s4 and s6 and genuinely below at s7. PARITY IS NOT "AT LEAST", and the
     check as written is one-sided, so parity fails it.
  2. Whether a one-sided check should carry a tolerance comparable to measured variance is a
     METHODOLOGICAL question for the user. Changing it now, after seeing which side the result
     landed on, would be exactly the tuning D187 (3) forbids. The verdict above is the check as
     specified.

ALSO MEASURED, because a bound was breached in letter: robot late by the coordinator flag is 8 / 5 /
12 / 3, and s6's 12 exceeds the "at most 10" bound used for shares and rung 4. A per-opportunity
join at s6 under one consistent delivery rule shows 11 of those 12 were ALREADY late under the
c5attr base, with exactly 1 opportunity lost and 2 gained. The c5attr base's own late count at s6 is
about 13 by the same rule. SO THE BOUND WAS MIS-APPLIED BY ME: it was calibrated on the SHARES base,
where late ran 0 to 5, and imported to judge an arm on the c5attr base, whose own late count already
exceeds it. That makes the base's behaviour look like the arm's harm, which is the same error shape
as the assistance control in item 7.4. Caveat on those counts: they use raw
`t_delivered - t_opportunity <= deadline` without the committed D144/D146 rewrites, so the JOIN
direction is trustworthy and the ABSOLUTE counts are not the scorer's.

### RUNG 4 IS BLOCKED AND CANNOT RUN

Built and proved, including Step 2b AT 0.25x ON THE c5attr BASE (switch ON 183a3ad7928452c9 / 13,287
against OFF 9a4be873eb3c5fba / 14,218; 264 decisions, 39 defers and chunks, 33 protects, harm median
0.9996 and max 5.996 over 128 computations, 73 over the bar). Its cell list V6CFPD_CELLS is posted
with the matched-memory control and the logical-pool caveat.

IT CANNOT RUN because its registration was REVERTED at 67dd0514: `arms_v6cf` imports
`cf_protect_defer`, which calls `cf_objective.attainment_margin` AT IMPORT TIME, and that function
exists only in an UNCOMMITTED edit in the shared worktree. Pushing that edit would unblock it in one
line and MUST NOT BE DONE: it is half-finished D177 work whose harm side was never converted. Rung 4
runs when that change is committed WITH its own proof, or when cf_protect_defer stops depending on it
at import time. Both are user decisions, not overnight ones.

## 6. OVERNIGHT DECISIONS, all PROVISIONAL, all in reports/OVERNIGHT_DECISIONS.md with evidence

1. The assistance IMAGE GRID finding: FINDING, NO ACTION. Assistance images are sent at native
   resolution (p50 1,307 image tokens) while alert and recall frames are downsized offline to 338
   and 90. No D-row authorises the per-type cost. Pre-resizing would make assistance fit inside its
   share and would very likely help the arm under test, which is exactly why it was NOT done: the
   image grid is the workload, and D187 (3) forbids changing it.
2. The WATCHDOG was wrong in both directions and is now heartbeat-gated. Its condition was "does the
   tmux session exist", but the working session is not in tmux and each spawned `claude -p` exits
   when its prompt ends, refilling the condition; it spawned three sessions in twenty minutes.
3. AUTO MODE on the watchdog, on the user's explicit ruling, after two resumed sessions reported
   being effectively read-only. It is not a bypass: permission checks still apply.
4. The D188 (1) RECALL-FLOOR REGIME DEFECT: recorded, nothing changed. See open items.
5. The D188 (2) CACHE FIX: prepared behind an OFF switch, never used in a cell, and it OVERTURNED an
   earlier zero. See open items.
6. The gzipped coordinator_result scorer defect, caused by my own P0 change. See open items.

## 7. OPEN ITEMS FOR YOU

1. FLOORS AND W_max (D188 (1)). The recall floor 655.8 was derived from the BASE arm's COLD questions
   (median 7,717 uncached). Rung-2 questions are WARM at 1,177 to 1,438, which would give a floor of
   12.4 to 17.7, that is 37 to 53 times smaller. ALERT IS NOT AFFECTED: its 374 median is already
   warm, so the alert floor and W_max rest on the right regime. THE NON-OBVIOUS PART: shrinking the
   recall floor would make recall MORE oversize, because a type's share is floor plus its cut of the
   flexible pool, so the share would fall from 1,256.7 to about 616 and a 1,300-token warm recall
   would go from 1.03x to 2.1x its share, serialising MORE. The underlying tension is that floors are
   sized for AVERAGE CONCURRENT WORK by Little's law while the admission test compares A SINGLE
   REQUEST against the share. Decide which job the floor is doing before re-deriving it.
2. THE id(obs) CACHE FIX (D188 (2)), prepared behind `live2_qcache_key_fix`, default OFF, used in no
   cell. It CHANGES RUNG-2 DECISIONS at seed 6 for shares, r1 and r2 (35 rows setwise, 696
   positionally, one extra HOLD_BACK), and `harm_warm_nonzero` moves in all 20 cells tested. An
   earlier measurement reporting zero was WRONG because it applied the candidate through a WRAPPER
   installed on both sides, AND THE WRAPPER ALLOCATES, perturbing the very address reuse under test.
   An instrument that allocates cannot measure an allocation-dependent bug. THE LIVE EFFECT CANNOT BE
   BOUNDED FROM DRY REPLAYS. If you enable it, the final rung-2 arm AND ITS COMPARATORS must be
   rerun together with it ON, because covex-v6-state-uo supplies check 2's bar.
3. THE ASSISTANCE IMAGE GRID, as above: a per-type effective image cost that no D-row authorises.
4. THE ASSISTANCE CONTROL WAS BADLY WRITTEN BY ME. "Assistance must not move" was unfalsifiable,
   because assistance moves through the shared `_uncached_in_flight` counter. Its own predicted u is
   identical under both formulas (371 of 371 and 382 of 382 gate events), so the fix did not reprice
   it. Restate such controls on quantities the mechanism OWNS, not on outcomes it shares.
5. THE GZIPPED coordinator_result DEFECT, caused by my P0 serialisation making the file large enough
   for the harness to compress it. The committed scorer reads a missing file as `{}` with NO ERROR,
   so diagnostics would read as ABSENT and be mistaken for ZERO. Verdicts are unaffected (they come
   from cell.json and outcomes). I fixed the INPUT, not the instrument. A guard that FAILS LOUDLY
   when the .gz exists and the plain file does not would be better than a quiet fallback.
6. TWO OVER-BROAD ALLOW RULES in .claude/settings.local.json, flagged by Claude Code itself: both
   `mv` rules have a WILDCARD BEFORE THE REST OF THE COMMAND, so they also match any options
   inserted there and approve them without a prompt. They look like leftovers from a one-off
   directory move. I did not edit them: permission configuration is yours, and that holds even when
   the change would be a tightening.

## 8. WHAT I WOULD WANT YOU TO KNOW ABOUT HOW TONIGHT WENT

THREE MECHANISMS WERE REFUTED BY THEIR OWN PRE-REGISTERED FAILURE CONDITIONS: the COLD-belief
hypothesis, the prefix-growth hypothesis, and the queue-register lever. In each case the refutation
came from a measurement that existed BECAUSE the condition was written down before the run. The two
things that survived are narrower than what I first proposed.

THE GATES CAUGHT WHAT MY OWN CHECKS DID NOT. The H100 corrected me four times from reading code
rather than running anything: stale telemetry on eviction, a COLD-with-built_tokens case my tests
missed, digests asserted in prose instead of a committed file, and a provenance stamp pointing at
superseded code. It also refused to gate a cell list whose Step 2b proof was "verified by
construction", which would have cost 88 minutes of H100 time to discover an absent link live. I had
briefed that agent to verify exactly that and it posted anyway.

THE RECURRING FAULT SHAPE, five instances tonight: a quantity written in one place and read in
another, with nothing checking the two agree about its meaning. `desired_tier`, `_uncached_in_flight`
register, `_log_decision`'s dropped `key`, `built_tokens` against the engine's prefix, and
`pending_by_type` declared and never read. I would treat "which code reads this, and does it mean the
same thing there?" as a standing check rather than an occasional one.

## 9. ADDED AFTER 07:00, so the summary above met its deadline and this did not exist yet

Sections 1 to 8 were committed before 07:00 as instructed. This section covers work that landed
between 07:00 and 08:00 and is kept separate rather than folded in, so the timeline stays readable.

### 9a. THE RUNG-3 FINDING THAT MATTERS MOST, and it needs a ruling rather than more cells

D186 names `mean_per_episode_attainment` the PRIMARY rule for check 1, and section 5's verdict is on
that rule: rung 3 meets all three checks at s5 only. Reading the committed verdict file more closely
turned up something section 5 does not say.

THE TWO STATISTICS DISAGREE IN DIRECTION at both near-noise seeds.

  seed   mean per-episode (D186 PRIMARY)      fraction of episodes at or above the 0.25 bar
  s4     -0.0013  FAIL                        +0.0056   (0.6053 to 0.6110)
  s5     +0.0307  PASS                        +0.0546
  s6     -0.0299  FAIL                        +0.0056   (0.6081 to 0.6138)
  s7     -0.0788  FAIL                        -0.0574

At s4 and s6 rung 3 puts MORE episodes over the 0.25 bar while its MEAN falls. s5 agrees with its
pass and s7 agrees with its fail. So on the bar-fraction statistic rung 3 is AHEAD of base at three
of four seeds and behind only at s7, which is also the only seed whose miss is outside measured
variance.

THAT IS THE SIGNATURE OF REDISTRIBUTION: pulling episodes that sit near the bar over it, at the cost
of episodes already well above it. Which is precisely what a per-device deficit feed is built to do,
so the mechanism is behaving as designed rather than accidentally. It is CLAUDE.md consistency check
3's stratum-against-mean warning in its sharpest form, the two disagreeing in SIGN and not in
magnitude.

I DID NOT ACT ON IT AND THE VERDICT STANDS AS SCORED. The SLO-meeting fraction is the project's
stated objective while the mean is D186's committed primary, and switching the rule now, having just
seen that it flips three seeds, is exactly the tuning the guardrails forbid. It is recorded in the
StudyFAIR-FEED row at 52dc3215 as a question for you.

### 9b. THE VARIANCE BAND WAS TESTED AND HELD, which also tested my r2 reading

I had staked the 0.05 to 0.06 run-to-run band in advance on the gain0 s6 cell: land near the
committed c5attr base and the band holds and check 1's s6 miss is noise; land far and the band was
wrong AND SO WAS MY READING OF THE R2 REFUTATION, which leans on the same figure. It landed 0.042
from base (0.289 against 0.331), INSIDE the band, from a third independent decision-identical pair.
So section 3's r2 conclusion rests on a number that has now been checked rather than assumed.

The feed's lift on its own matched control is consistent at three seeds: +0.29 at s4, +0.25 at s5,
+0.21 at s6, pooled dashcam against gain0. I ARGUED AGAINST SPENDING GPU ON THAT CONTROL and was
overruled; it is now the best-supported number in the rung. My reason was GPU economy and the axis
was wrong: s6 and s7 are exactly where check 1 fails by more than noise, so they are where the
attribution carries the most weight.

### 9c. D189 EDGE CONDITIONS: one condition reposted, one NOT BUILT

ITEM 1, memory. I first posted the LOGICAL-only tag condition. THAT WAS THE WRONG CONDITION: you had
already ruled at 07:35 to 07:40 for a REAL engine 0.25x, recorded at OVERNIGHT_HANDOFF_H100.md line
168, and the ruling crossed with my posting. The H100 declined to gate it, which was the right call.
Reposted at e1b5040b with `--num-gpu-blocks-override 984 --max-model-len 15744` on all 12 lines;
gated. The launcher entry that makes it possible is at 72e2d718 with the default path proved
unchanged over 9 flag lists.

TWO FINDINGS FROM THE PROBE, THE SECOND CORRECTING THE FIRST. No arm is unable to run at 0.25x:
`cstate.py:498-517` evicts rather than raising, and there is NO admission gate on pool size anywhere.
I then pre-registered that four of the six arms CANNOT BE BOUND, because mooncake, simplestream,
eco-llm and covex-v6-base never build a prefix, their largest prompt is below the pool, and three of
them reach the pool only through `arms.py:82 self._caps`, which has exactly ONE occurrence in the
repo and it is a WRITE. THAT HOLDS ONLY FOR THE LOGICAL CONDITION. The H100 pointed out that under
the real engine fewer vLLM blocks means more preemption and less concurrency for EVERY arm, so the
pool binds all six AT THE ENGINE whether or not an arm can observe it. It is right, and the real
condition is informative for all six where the logical one was informative for two. Engine refusals
remain a separate channel and hit only llf (20 and 2) and covex-v6-rules (55 and 37).

ITEM 2, network outages: NOT BUILT, and it should not be. The read-only survey found an ABSENT LINK.
`cstate.py:595` hard-codes `network=NetworkState(connected=True, ...)` as a LITERAL, so every
`not s.network.connected` branch in every arm is dead code and `coordinator.py:791 on_outage` is
unreachable. NONE of the seven arms reads a link state; eco-llm's single read is dashcam-only on a
constant True. The described 56-cell grid would return cells BYTE-IDENTICAL to the no-outage cells.
`Link.reachable` is declared and written at three sites with no decision-changing read, the
`desired_tier` shape exactly. `v5/cf_planner.py:697-802 plan_sync` is fully implemented with NO arm
caller, which is UNEXERCISED under Rule 2, the same class as E36. "Independent vs correlated across
devices" exists nowhere in the repo. Estimate 30 to 47 hours plus three methodological rulings, and
D150 SYNC (5) and spec v6's inputs table already order outage scenarios after the core grid, so the
absence is scheduled rather than an oversight.

ITEM 3, recall deadline 2.5 s and load at 12 and 20 devices: PROPOSED ONLY, not posted. 36 cells,
roughly 13 hours. Two things to decide first: a 2.5 s deadline changes a PRE-REGISTERED target so it
must be a separate condition rather than a re-score, and 12 or 20 devices changes fleet size, which
moves the floors and W_max further from the regime they were derived in. Neither blocks it as
baseline characterisation; both block reading it against the D179 checks.

### 9d. BASELINE COVERAGE: kvflow-prefetch, and a stale committed proof

KVFLOW_CELLS and DEVWAIT_S67_CELLS posted at d3e8d697, both gated.

kvflow-prefetch PASSES THE PORT RULE on this workload: the characteristic decision `prefetch_ahead`
occurs 108 times against the base's 9, so 99 attributable, and that 99 EQUALS the arm's own
`prefetch_ahead_emitted` of 99 exactly, an observed log count and an internal counter arriving at the
same number by different routes. Off-switch byte-identical to base; name proof through
run_live2_real.py with a negative control confirming an unknown name still exits 1.

TWO CAVEATS THAT MUST TRAVEL WITH THOSE CELLS. The committed `kvflow_prefetch_proofs.json` records
`prefills_issued_committed: 0` with verdict UNEXPRESSIBLE, and the arm's module docstring still says
warming ahead is not expressible. BOTH ARE STALE, pinned to 55ec283: PATCH 1 has since landed
`Observation.live_sessions`, so THE ARM NEVER CHANGED, THE CHANNEL IT ACTS THROUGH WAS OPENED. Anyone
reading that docstring would wrongly call these cells a relabelled zero. And
`prefetch_ahead_unexpressible` is 19,107 against 99 emitted, so the mechanism is live and reaches a
decision but is NOT FULLY EXPRESSED; these cells are not the published system at full strength.

STREAMSCOUT AND LMCACHE COMPARABILITY: ALL FOUR EXISTING s4/s5 CELLS ARE NOW CLOSED BY MEASUREMENT,
after an interval where two of them were not. Two cell revisions returned "upload-pack: not our ref"
from origin because they are PRE-REBASE ORIGINALS whose rebased copies reached origin; the H100 held
the objects and pushed them to refs/h100/*. streamscout: `git diff 50777f0d ef4a963a` over live2/ and
baselines/ returns ZERO differing files, run on this box, and the s4 digest is byte-identical to
origin/main, so s5 follows by composition. lmcache: dry digest `2b789696e98821c4` / 37,080 rows on
BOTH 4af40941 and origin/main, agreeing with the prior measurement at 469929a, so all three revisions
match. The static argument alone would NOT have settled lmcache, because `arms_published.py` imports
every baseline adapter AT MODULE LEVEL and `baselines/device_confidence.py` is NEW, and no static
reading distinguishes "imported and inert" from "imported and mutating". Provenance recorded: that
sha reached this box as a recovered object, NOT from origin.

### 9e. ADDED TO THE OPEN ITEMS IN SECTION 7

1. WHICH STATISTIC CHECK 1 SHOULD USE, 9a. The mean and the SLO-bar fraction disagree in direction at
   two seeds and the choice flips three verdicts. I have not touched it.
2. WHETHER D189 ITEM 3 RUNS, and under what label, 9c.
3. WHETHER ITEM 2 IS WORTH 30 TO 47 HOURS, 9c. My recommendation is no, not now.
4. The `arms_v6state.py:236 id(obs)` cache, still FIXED TOMORROW per D188 (2), prepared behind a
   switch defaulting OFF and applied to no cell.
5. Rung 4 is still blocked and still needs the `v5/cf_objective.py` ruling, unchanged from 5/139.
6. The two STALE committed artefacts in 9d: `kvflow_prefetch_proofs.json`'s UNEXPRESSIBLE verdict and
   `arms_kvprefetch.py`'s docstring. Neither is wrong about the code at 55ec283; both are wrong about
   the code now, and a reader has no way to tell.
