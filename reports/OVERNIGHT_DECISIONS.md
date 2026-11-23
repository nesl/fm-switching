# OVERNIGHT DECISIONS (D187), for the user's morning review

Every entry is PROVISIONAL and carries its evidence. A FINDING entry means something was measured
and NO ACTION was taken, with the reason. A DECISION entry means a new labelled version was built.

---

## 2026-11-22 18:20 FINDING, NO ACTION TAKEN: assistance is oversize because of an image grid that no D-row sets

WHAT WAS MEASURED (read-only, `results/orchestration/live2/frozen_test/image_settings_by_type.json`,
pushed at `c4db4122`). There is exactly ONE image-processor setting, server-wide, for all three
query types: `--mm-processor-kwargs {"size": {"shortest_edge": 4096, "longest_edge": 16777216}}`.
It binds NOTHING: the largest image any type sends is 9.4x below max_pixels and the smallest is 48x
above min_pixels, so no image of any type is rescaled by the processor. Our body builder performs
NO resize, crop or re-encode (`bodies.py:127-147`): it base64s the stored bytes verbatim.

THE DIFFERENCE IS UPSTREAM, IN STORAGE, AND IT IS PER TYPE:
  alert frames       768x432, downsized OFFLINE before storage   338 image tokens
  recall frames      352x256, downsized OFFLINE before storage     90 image tokens
  assistance images  NATIVE dataset resolution, NO pre-resize anywhere
                     p50 1448x938, p90 1448x1536, max 1536x1536  p50 1,307 image tokens

So one assistance image costs 3.9x an alert frame and 14.5x a recall frame.

WHY IT MATTERS TO D179, and it revises my own earlier account. I reported that assistance is
"routinely OVERSIZE against its own share" and used that to explain the W overrun with no recall
present. That is true as far as it goes, but the CAUSE is not the admission rule: as sent, the
median assistance request is 1.63x its own 843.7-token share and therefore takes an oversize
branch; on alert's 768x432 grid the same request would be a CONSTRUCTED 407 tokens, 0.48x its
share, comfortably inside it. Assistance's oversize status turns on an image grid, not on D179 (3).

A SECOND, INDEPENDENT CAUSE compounds it: assistance holds ZERO residency by construction
(`trace.py:567-574`), cached fraction exactly 0.0 on all 1,428 requests, so it pays its whole prompt
every time, while alert's append-only EP-G episode is 89.3 percent cached at p50.

NO D-ROW AUTHORISES THE PER-TYPE EFFECTIVE COST. D67, D70, D91, D111, D136, D143, D148, D153, D156
and D172 were searched. D70 and D91 fix the wire format and inherit the two grids from upstream
studies; D136 and D143 choose the SS datasets and the split only; D172 requires only that the
setting be STATED. The SETTING is uniform and authorised. The effective per-image cost is recorded
nowhere.

WHY NO ACTION WAS TAKEN, and this is the point of the entry. The obvious change, pre-resizing
assistance images to a comparable grid, would make assistance fit inside its share and would very
likely improve the shares arm's numbers. D187 (3) forbids it: "NEVER change targets, deadlines,
metrics, workload, seeds, baselines, pass bars or the margin". The image grid IS the workload. A
change that happens to help the arm under test, made overnight, on a quantity no decision governs,
is exactly the kind of thing the rule exists to prevent, so it is reported and left for the user.

REGISTER: 1,372 and 374 are MEASURED medians; 407 is a CONSTRUCTED bound, not a census.

POSITIVE CONTROLS ON THE READING, both exact before any table was trusted: the EP-G law
`prompt_tokens = 42 + 338 x n_frames` holds on 39,945 of 39,945 alert requests across the four base
cells, deviation histogram {0: 39945}; and `share_capacity.FACTORS` medians recompute from the four
cells that file names as its source at alert 374, recall 7,717, assistance 1,372, ratio 1.000000.

TWO SMALLER ITEMS FROM THE SAME READ:
1. A PROXY THAT FAILS, flagged by the code itself: assistance UPLINK BYTES substitute the S-EMBER D2
   median for every SS2 image (`fleet/data_sources.py:661`), understating them by 2.2x to 24x in
   area. It touches no token count, so nothing above depends on it, but any assistive uplink figure
   resting on it is unvalidated.
2. In the `b7-edf-feasibility` s4 cell, 74 of 8,058 alert requests deviate from the EP-G law, while
   the four base cells are 0 of 39,945. Not diagnosed and not used for any number here; flagged as a
   cheap check for whoever owns b7.

---

## 2026-11-23 02:40Z DECISION, PROVISIONAL: the watchdog's restart condition was wrong in both directions, and its restarts cannot do the work

WHAT HAPPENED. The watchdog installed under D187 (5) restarted on the condition "does the tmux
session `fmsw-overnight` exist". It spawned three sessions in twenty minutes (02:12, 02:20, 02:30)
and would have spent its whole six-per-hour budget. The condition was wrong in BOTH directions at
once:

1. The session actually doing the work was never in tmux. It is attached to the user's client, so
   it cannot move itself there, and to the watchdog it therefore looked DOWN while it was working.
2. Each spawned `claude -c -p` EXITS when its prompt completes, so the tmux session vanishes within
   a minute and the next cron tick spawns another. The restart condition was self-refilling.

THE CORRECTION, applied: a HEARTBEAT gate. A live worker touches `ops/heartbeat`; if it is fresher
than 1,800 s the watchdog does not restart. Tested both ways and logged: fresh gives "OK worker
heartbeat 0s old, not restarting", and an artificially staled heartbeat still fires the restart, so
the gate did not simply disable the watchdog.

THE MORE IMPORTANT FINDING, AND IT IS A PERMISSIONS QUESTION FOR THE USER, NOT SOMETHING TO ROUTE
AROUND. The sessions the watchdog spawns are effectively READ-ONLY. A watchdog-resumed session
reported being refused repo writes, refused even `sed` and `grep` READS under `/tmp/claude-1001/`
where the whole workflow lives, and prompted for `tmux ls`. The H100 independently reproduced the
same thing on its own box. So a faithful restart produces a session that cannot continue the work.
Nothing was changed to work around that, per D187 (5)'s "using only the permission settings already
configured".

WHAT THE SPAWNED SESSION DID WITH THE ONE CHANNEL IT HAD, which is worth recording because it was
correct. It read the handoff, independently found a real defect in the cold-pricing fix (the engine
telemetry was being subtracted on the COLD branch, where it is stale because nothing resets it on
eviction), could not apply the correction, and sent it to the H100 with the exact replacement code
so nobody would have to rediscover it. It also declined to ask the H100 to commit on its behalf and
said so. The H100 verified the defect from the code itself rather than acting on relay, and refused
the proxy write. BOTH behaved correctly.

A CORRECTION TO MY OWN EARLIER REPORT: I told the user that a message the H100 received, which I had
not sent, was "the one event tonight I cannot account for". It is now accounted for. It came from my
own watchdog-spawned session on this box, which is why it arrived with a different session id and
the name "A6000" and described itself as read-only. There was no spoofing and nothing unexplained.

A SECOND CORRECTION, to the fix itself: my first attempt at the COLD guard subtracted `built_tokens`
on the COLD branch whenever it was non-zero, which changed COLD pricing in the UNSAFE direction (an
evicted session's build pieces are evicted with it) and added a second change on top of the
telemetry fix, so an r1-against-shares comparison would have carried two changes rather than one.
The H100 caught it and also noted that my four test cases did not cover COLD with `built_tokens` > 0
- the single case that distinguishes the two forms. The final form leaves COLD exactly as it was and
changes only the warm branch, verified case by case.

---

## 2026-11-23 03:40Z FINDING, NO FURTHER CODE CHANGE: the residual r1 skips are mostly NOT a pricing problem, and the 6.4x was largely a measurement artefact

r1 s5 PASSES ALL THREE D179 CHECKS (retention 0.9773 against a 0.90 bar, skips 48 to 12 against a
bar of 13). r1 s4 does not (0.7229, skips 70 to 34). THE FIX IS SEED-DEPENDENT, NOT UNIFORMLY
SHORT, which was invisible from s4 alone.

BOTH HYPOTHESES WERE REFUTED BY MEASUREMENT, mine and the user's.
- "telemetry never written": 0 of 34 at s4 and 0 of 12 at s5. The field was set at EVERY skip.
- "belief COLD while the engine was warm": 0 of 34 and 0 of 12. Readiness is GPU-WARM at every one.
- Warms and touches DO write the field (touch 5,668, build piece 234, recall 73 on the skipped
  sessions), and the belief-apply-off restore at coordinator.py:1708 restores only `belief` and
  `last_touch_s`, so it is never clobbered.

THE REAL DEFECT IS CENSORING, NOT STALENESS. `cached_tokens` is min(resident prefix, that request's
own prompt). A touch sends only the confirmed frames (coordinator.py:1118-1127) and a build piece
sends the built prefix plus one slice (1197-1204), so NEITHER CAN EVER REPORT A PREFIX LARGER THAN
THE BUILT ONE. Only a recall presents the whole history. The last write before a skip was a build
piece at 24 of 34. So the field is not lagging behind reality; it is structurally incapable of
reporting it.

TWO FINDINGS THAT REFRAME THE PROBLEM, and both reduce the value of any further pricing work.

(1) ONLY 9 OF THE 34 SKIPS AT s4 WERE REFUSED BY THE SIZE TERM AT ALL. The other 25 were refused by
the QUEUE term with a predicted u that already fits the slack (s5: 7 size, 5 queue). So pricing is a
MINORITY of the residual and a perfect prefix fix cannot reach the bar.

(2) THE 6.4x RESIDUAL MISPRICING IS LARGELY A FEEDBACK ARTEFACT, measured by stratification rather
than argued. Because only a recall plants the whole history, uo's engine prefix on these sessions
was planted by UO'S OWN EARLIER RECALLS, which are exactly the ones r1 skipped. Predicted-over-
engine ratio by number of prior uo recalls on that session: 0 prior gives 1.04 to 1.13; 1 gives
1.11; 2 gives 14.87; 3 or more gives 10.73. Fifteen of the 34 skips sit on sessions r1 had never
released a recall on. THE CROSS-ARM ENGINE PROXY IS CONTAMINATED BY THE VERY DIFFERENCE BEING
MEASURED, and any future "predicted against engine" ratio quoted across arms must be stratified this
way or it is not evidence.

THREE CANDIDATE FIXES, ALL DISQUALIFIED OR REJECTED ON MEASUREMENT, INCLUDING MINE:
- "add tokens uploaded since last completion" (my suggestion): DISQUALIFIED by direction. It asserts
  every uploaded token is resident. On robo001|s000 it would subtract 25,501 where uo's own first
  recall at that instant reports the engine holding 6,928, giving a measured first token of 4.413 s
  against 2.953 s of slack. It converts a skip into a LATE ANSWER on exactly the row it targets.
- "coordinator's own sent-bytes record": DISQUALIFIED, same direction and worse; the pool turns over
  about 89 times in 1,200 s and re-sent bytes double-count.
- "running max of telemetry": REJECTED on a measured gain of 0 of 34, because max(built, telemetry)
  already dominates every earlier value.

A FOURTH CANDIDATE I FOUND AND AM NOT ACTING ON, for the user to rule on. The release re-check is
fed `queued_uncached_ahead=self._uncached_in_flight` (coordinator.py:937 and 1279), and that counter
DRAINS AT COMPLETION, so it includes decode time and overstates the work ahead of a request's FIRST
TOKEN. The D179 W tracker is the first-token-drained quantity and already exists. Since 25 of the 34
residual skips are queue-refused, this could matter more than any prefix fix. I DID NOT CHANGE IT:
the D162 gate artefact does not record which counter its queue regressor was fitted against, and
feeding the model a different quantity from the one it was fitted on could bias predictions LOW,
which is the unsafe direction. Establishing the fit's definition, or ruling without it, is the
user's call, not an overnight implementation fix.

THE ASSISTANCE CONTROL: ITS INTENT HOLDS, ITS LETTER DOES NOT, AND THE CONTROL WAS BADLY WRITTEN.
Assistance moved (skips 12 to 0 at s4, 12 to 3 at s5), so as literally pre-registered the control
failed. But assistance's OWN predicted u is identical under the pre-fix and post-fix formulas on
371 of 371 gate events at s4 and 382 of 382 at s5, tested WITHIN the r1 cell so no cross-cell proxy
is needed: those sessions carry no build pieces and no whole-history request, so the prefix
subtracted is 0 either way and the max() the fix added has nothing to choose between. The benign
"w_max headroom freed" explanation that I offered is RULED OUT by measurement: share_deny_assistance
went 14 to 15 at s4 and 18 to 31 at s5, so the gate got TIGHTER, not looser. The real coupling is
indirect, through the shared `_uncached_in_flight` counter that recall releases feed.

THE LESSON, which outlives this fix: A CONTROL THAT IS PERMITTED TO MOVE THROUGH A SHARED COUNTER IS
NOT A CONTROL. "Assistance must not move" was unfalsifiable in the presence of a shared queue. It
should have been written as "assistance's OWN PREDICTED u must not move", which is checkable and
passes 371 of 371 and 382 of 382. Future pre-registrations should state controls on quantities the
mechanism owns, not on outcomes it shares.

---

## 2026-11-23 04:30Z OPEN ITEM FOR THE USER (D188 (1)): the recall floor was derived in the wrong regime, and re-deriving it naively would make things WORSE

USER RULING D188 (1): the floors and W_max STAY FROZEN tonight (alert 1,622.1, recall 655.8,
assistance 242.8, flexible 1,802.6, W_max 4,323.3). They are NOT re-derived overnight. The issue is
recorded here with its evidence for tomorrow's discussion, which the user will decide ON MECHANISM
and NOT on the r2 verdict.

THE DISCREPANCY, computed from the frozen constants and tonight's measured medians.

D181 derives each floor by Little's law, floor = lambda x median uncached x median first token, from
the four committed covex-v6-base cells. For recall that is 0.0373 x 7,717 x 2.279 = 656.0, matching
the frozen 655.8. But 7,717 is the BASE arm's COLD question cost, because the base does no warming.
Rung-2 questions are WARM, and tonight's engine-reported medians are 1,177 (uo), 1,438 (shares) and
about 1,178 (r1).

Re-deriving on those warm numbers, using the committed D162 first-token model:

  uo     u 1,177 -> first token 0.2825 s -> floor  12.4 tokens   53x smaller
  shares u 1,438 -> first token 0.3301 s -> floor  17.7 tokens   37x smaller
  r1     u 1,178 -> first token 0.2827 s -> floor  12.4 tokens   53x smaller

At a mid estimate of u = 1,300 the recall floor would be 14.8 tokens, freeing 641 tokens into the
flexible pool, which would grow from 1,802.6 to 2,443.6, that is from 41.7 to 56.5 percent of W_max.

ALERT IS NOT AFFECTED THE SAME WAY and should not be swept into the same correction: its median of
374 uncached is ALREADY a warm number, because EP-G episodes are 89.3 percent cached at p50. So the
alert floor of 1,622.1 and W_max itself rest on the right regime. This is a RECALL-specific defect,
not a general one.

THE NON-OBVIOUS CONSEQUENCE, WHICH IS THE REASON THIS NEEDS A MECHANISM DISCUSSION RATHER THAN AN
ARITHMETIC FIX. Shrinking the recall floor would make recall MORE oversize, not less. A type's own
share is floor plus its cut of the flexible pool. Today recall's share is 655.8 + 600.9 = 1,256.7,
and a warm recall of about 1,300 tokens sits at roughly 1.03x its share. With the floor re-derived
to 14.8 the share would fall to about 616, and the SAME request would sit at about 2.1x its share,
that is MORE DEEPLY OVERSIZE. Since D179 (3) admits an oversize request only when nothing else of
its type is in flight, recall would be serialised MORE often, not less.

THE UNDERLYING TENSION, stated plainly for tomorrow: FLOORS ARE SIZED FOR AVERAGE CONCURRENT WORK by
Little's law, while the ADMISSION TEST COMPARES A SINGLE REQUEST against the share. Those are
different quantities. A floor that correctly describes expected concurrency can be far too small to
admit one typical request, and that gap is what pushes a type onto the oversize path. Any re-derivation
should decide which of the two jobs the floor is doing, rather than making the Little's-law number
more accurate and inheriting the admission consequence by accident.

NOTHING WAS CHANGED. The constants are as frozen, with both D180 bounds still import-time assertions
in share_capacity.py, and r1 and r2 both ran on them.

---

## 2026-11-23 04:45Z DEFECT CAUSED BY MY OWN P0 CHANGE: the r2 cells gzip coordinator_result, and the committed scorer reads it as ABSENT, silently

WHAT HAPPENED. The P0 instrumentation that shipped with the r1 fix serialises
`release_infeasible_events` and `share_events` into `coordinator_result.json`. That made the file
large enough that the harness now writes `coordinator_result.json.gz` instead: the r2 s4 cell has
`coordinator_result.json.gz` at 252 KB where every earlier cell, r1 included, has a plain
`coordinator_result.json`.

WHY IT IS DANGEROUS RATHER THAN MERELY UNTIDY. The committed pre-registered scorer reads it as

    coord = json.load(open(coord_path)) if os.path.exists(coord_path) else {}

so a missing file yields an EMPTY DICT with NO ERROR AND NO WARNING. Every diagnostic sourced from
it (`release_infeasible` per type, the share counters, planner abandonment) would read as ABSENT,
which in this project has repeatedly been mistaken for ZERO. It is the same shape as the faults
caught all night: a quantity that cannot be read reported as a quantity that is not there.

WHAT IS AND IS NOT AFFECTED. The three pre-registered D179 checks come from `cell.json`'s
`score.score.sweep[0]` and from `outcomes.jsonl.gz`, NOT from `coordinator_result`, so the VERDICT
is not affected. The DIAGNOSTICS are. The H100's own per-seed reports read the cell directly and are
unaffected.

THE FIX APPLIED, and deliberately NOT to the scorer: when assembling a runs directory for scoring,
decompress `coordinator_result.json.gz` to `coordinator_result.json`. The scorer was pre-registered
before any shares cell existed and its value comes from not being edited after the data arrives, so
the input is normalised instead of the instrument. A `.gz` fallback inside the scorer would also be
defensible as a pure reader fix, but it is not necessary, and the smaller change is the one that
cannot be argued with tomorrow.

RECORDED FOR TOMORROW: if the scorer is ever rerun by someone assembling a runs directory by hand,
they must decompress that file first, or the diagnostics silently empty. Worth a one-line guard in
the scorer that FAILS LOUDLY when `coordinator_result.json.gz` exists and `coordinator_result.json`
does not, rather than a fallback that quietly succeeds.

---

## 2026-11-23 05:40Z DETERMINATION: r1 DOMINATES r2, both fail the rule, so D184 applies

Scored with the committed pre-registered scorer, gz decompressed, positive control PASS 6 of 6
cells exact. Check 2 retention, bar 0.90:

  seed      r1        r2        r2 better?
  s4      0.7229    0.5301     NO, worse by 0.193
  s5      0.9773    0.9773     equal
  s6      0.7727    0.7727     equal
  s7      0.8906    pending    cannot change the dominance below

r1 IS THE BEST SHARES VERSION, unambiguously: greater than or equal to r2 at every scored seed and
strictly better at s4. That resolves the "which version is best" question an earlier handoff
deferred, and it does so WITHOUT needing s7, because r2 would have to beat r1 at s4 to change the
ordering and s4 is already measured.

BOTH VERSIONS FAIL THE RULE: each passes all three checks at s5 only, against a rule of all three
at all four seeds. So the D184 trigger is satisfied. c5attr is rung 2, rungs 3 and 4 build on it,
and r1 is reported as the TRADE-OFF ABLATION.

THE r2 RESULT IS "FIRED AND DID NOT HELP", the one Rule 2 category that is evidence about the
policy rather than about plumbing. The queue-register fix was RIGHT ABOUT THE REGISTER: the D162
regressor is built over submit-to-first-token intervals and the re-check had been fed a
submit-to-completion counter, and the corrected input did reach the decision, with the median
queued-ahead at the skips falling from 1,496 to 1,101. It still made s4 worse. The likely system
explanation, measured but not isolated, is that a more permissive re-check admits more work, which
raises W, which makes share admission deny more (share_deny_recall 467 to 643), settling the arm at
a worse equilibrium. BEING RIGHT ABOUT A QUANTITY IS NOT THE SAME AS BEING RIGHT ABOUT THE OUTCOME,
and that is the lesson worth keeping from r2.

## 2026-11-23 05:40Z FINDING: a docstring in arms_v6fairfeed.py is now STALE and would mislead the next reader

That file's header (around lines 26 to 34) states that the deficit feed's weights are consumed by
D179 share admission AND BY NOTHING ELSE, and concludes that on the c5attr base the weights have no
reader at all and the feed is an ABSENT LINK BY CONSTRUCTION. That was true when written and is now
FALSE: the D182 ordering consumer added a SECOND reader, the _deficit_order_key hook in
hybrid_arm.py, which has nothing to do with share admission.

VERIFIED EMPIRICALLY RATHER THAN BY READING. Constructing covex-v6-fair-c5attr gives the chain
V6FairFeed -> V5Rules2Arm -> HybridArm with the ordering override installed ON THE HybridArm,
exactly as for covex-v6-fair-shares. So the feed CAN steer on the c5attr base, through the ordering
consumer, which is the only consumer that ever did anything: the dry attribution measured ordering
at 3,902 differing decisions and the flexible split at exactly 0.

WHY IT MATTERS RIGHT NOW: D184 puts rung 3 on the c5attr base, and that docstring would tell the
next session rung 3 cannot be tested there. It can. The docstring needs correcting and I did NOT
edit it: I am a one-turn watchdog-resumed session, and editing a live-path file without being able
to follow through on a byte-identity proof is the wrong trade even for a comment. Recorded here so
the correction is not lost.
