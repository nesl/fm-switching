# PRE-REGISTRATION: the cold-pricing fix (r1), written and committed BEFORE its cells

D187 (1) and (2). This file is committed before any `covex-v6-state-shares-r1` cell is posted, so
the pass check cannot be shaped by the result. Nothing in it may be edited after a cell runs; a
later correction is appended with its date and reason.

## THE MECHANISM, measured, not assumed

The diagnosis (`results/orchestration/live2/frozen_test/d179_recall_skip_diagnosis.json`) classifies
every release-infeasible recall skip at seeds 4 to 7. MISPRICED SIZE dominates at every seed: 57 of
70, 44 of 48, 41 of 46, 44 of 46.

THE HYPOTHESIS BOTH THE USER AND I HELD IS REFUTED, and the real mechanism is adjacent to it. We
expected a COLD residency belief predicting the full history. COLD-while-warm occurs at only 8 of
210 skips; readiness is GPU-WARM at 69 of 70 skips at s4 and at all 48 at s5. The warm prefix IS
subtracted. THE WRONG QUANTITY IS SUBTRACTED: `built_tokens` (`cstate.py:119`, written only at
`coordinator.py:1777`) counts the coordinator's own 1,024-token build pieces, while the engine holds
the whole history from the EP-G per-frame uploads. Median predicted u at s4 is 14,712 against the
engine's own 1,050 on the same opportunity in `covex-v6-state-uo`, a ratio of 15.6x.

The size term ALONE, with zero queue, already exceeds the slack in 29 / 30 / 23 / 32 skips. With the
engine's own count it exceeds the slack in 1 / 0 / 1 / 0.

## THE FIX, one site, `coordinator.py:1219-1220`

The engine's own prefix is already observed and written to `session.last_telemetry_cached_tokens`
(`engine_actions.py:358`) and is READ NOWHERE in the pricing path: ABSENT in CLAUDE.md's sense. The
fix reads it, taking the MAX of the two lower bounds rather than replacing one with the other,
because `built_tokens` exists before a session's first request and the telemetry only after one.

## THE PASS CHECK, pre-registered

PRIMARY, at seed 4, against the committed `covex-v6-state-shares` cell:
1. `release_infeasible_recall` falls from 70 toward AT MOST 13, that being the 10 class-c plus 2
   class-d plus 1 class-b skips the diagnosis says are not mispriced.
2. `robot_pool_on_time` rises from 60 toward 118 (the committed `covex-v6-state-uo` figure).
3. The three D179 (6) checks are re-scored by the committed pre-registered scorer, unchanged.

IF THE SIZE CHANNEL ALONE BEHAVES AS CLAIMED, the fix accounts for at most 49 of the 57 class-a
skips at s4; the remainder need the queue term too. That bound is from the artefact's
`proposed_fix_input_probe` and is an UPPER BOUND on the size channel, not a measurement.

IF 1 AND 2 DO NOT MOVE, THE NAMED EXPLANATION IS WRONG and that is the finding; it is reported as
such and the fix is not kept merely because it is harmless.

POSITIVE CONTROL ALREADY IN THE DATA: assistance must NOT move. Assistance sessions get no build
pieces and hold no cached prefix, and its predicted-to-engine ratio is already 0.972 at every seed.
If assistance moves, the fix is doing something other than what is claimed.

ALTERNATIVE EXPLANATION, and what distinguishes it: the same headline could come from the queue
term, since the inflated u also inflates `_uncached_in_flight` for every other request. The
distinguishing measurement is already made: the size term ALONE, with zero queue, exceeds the slack
in 29 / 30 / 23 / 32 skips, which no queue effect explains. Both channels are fed by the same wrong
u, so both are expected to improve; only the size channel is claimed.

## WHAT IS DELIBERATELY NOT CHANGED, because D187 forbids it without a ruling

1. THE FLOORS AND W_max ARE NOT RE-DERIVED. They are frozen in `share_capacity.py` from the four
   committed base cells per D181, using the base's engine-reported medians (recall 7,717, which is
   the BASE's cold, no-warming figure). After the fix the policy's predicted recall u becomes
   engine-comparable and falls by roughly an order of magnitude, so the recall floor and W_max may
   now be mis-sized for the regime they govern. RE-DERIVING THEM IS A METHODOLOGICAL CHANGE and
   needs the user's ruling. r1 therefore runs with the EXISTING frozen constants. If r1's recall
   behaviour looks constrained by a floor rather than by pricing, that is the next thing to raise,
   not to fix.
2. THE OVERSIZE RULE IS UNCHANGED, per the user's D186 ("no change to the oversize rule itself").
3. NO TARGET, DEADLINE, METRIC, WORKLOAD, SEED, BASELINE, BAR OR MARGIN IS TOUCHED.

## A COMPARABILITY CAVEAT THAT MUST TRAVEL WITH ANY r1 RESULT

`_uncached` also feeds the D162 budget price (`coordinator.py:1222`) and `_uncached_in_flight`
(`:1283`). `covex-v6-state-uo` runs with `d162_pricing` on, so THE SAME MISPRICING IS PRESENT IN
COMMITTED RUNG 2's BUDGET CHARGE. r1 against committed uo is therefore not a like-for-like
comparison of pricing. The mitigating measurement, to be checked rather than assumed when r1 lands:
every committed rung-2 cell reports `budget_refusal` 0, so if the budget never binds, the inflated
charge is inert in uo and uo remains a valid comparator. If any rung-2 cell shows a non-zero budget
refusal, uo must be rerun with the fix before check 2 is read.

## PROOF ORDER

- P0 PREREQUISITE, instrumentation: serialise `release_infeasible_events` and `_share_events` to the
  run directory. Today both die with the process, which is why the diagnosis above had to be a
  reconstruction rather than a reading. Without it the r1 cells are as unreadable as these four.
- P1 dry byte-identity prescreen on the arms the fix cannot reach, each audited against a value
  committed BEFORE the change.
- P2 THE TRAP, stated so it cannot be misread: on a DRY cell `last_telemetry_cached_tokens` is
  always None, because there is no engine. A dry prescreen proves the fix HARMLESS and proves
  NOTHING about whether it fires. THE FIRING PROOF MUST BE LIVE.
- P3 the live r1 cells at seeds 4 to 7, scored by the committed scorer.
