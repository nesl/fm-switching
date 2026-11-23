# OVERNIGHT HANDOFF (D187, user decision 2026-11-22 18:10)

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
