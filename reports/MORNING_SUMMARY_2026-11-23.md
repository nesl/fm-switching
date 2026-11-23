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

RUNG 3 (covex-v6-fair, D185 per-device normalised deficit): PROVED ON THE c5attr BASE AND GATED.
V6FAIR_C5ATTR_CELLS, sha256 fe061dd9, four cells at seeds 4 and 5, running about 22:22 to 23:50.
Step 2b on that base: 4,512 differing decisions against the gain-0 control, computed INDEPENDENTLY
BY TWO SESSIONS WITH THE SAME ANSWER. The attribution is exact: the ORDER-ONLY arm is BYTE-IDENTICAL
to the both-consumers arm (12e4f73ce0ebd865 / 13,812) and SPLIT-ONLY is EXACTLY ZERO, identical to
the control. So rung 3's entire contribution is the ORDERING consumer, and the flexible-split
consumer contributes nothing on this base, which is what "absent by construction" predicts when
share admission is not in the chain. Off-switch identity and the name proof with its negative
control both pass.

RUNG 4 (protect-and-defer): BUILT AND PROVED EARLIER, NOT YET RUN ON THE c5attr BASE. Absent link at
1x memory (declared, not a negative), 19 characteristic decisions at 0.25x, both Step 4 controls
collapsing exactly to the OFF digest, harm a real distribution (median 0.9995, max 5.996, 70 distinct
values, ceiling the 6 pending alert devices). Its sign question resolved better than it was posed:
there are TWO deficit weights, w_j inside the harm sum and w_R scaling the bar, and conflating them
does not invert the mechanism, it CANCELS it.

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
