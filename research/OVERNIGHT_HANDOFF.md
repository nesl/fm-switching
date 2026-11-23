# OVERNIGHT HANDOFF (D187). READ THIS FIRST.

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
