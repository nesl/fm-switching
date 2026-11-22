# C5 replacement: pre-registered selection rule

Committed BEFORE any shares-cell result exists, per the user's addendum C of 2026-11-22. Nothing
in this file is adjustable once a shares cell has run.

## The rule

SHARE ADMISSION (D179, D180, D181) is the PRIMARY C5 replacement.

c5attr (the C5 attribution rule) is adopted as FALLBACK only if BOTH hold:
1. share admission FAILS at least one of its three D179 (6) pre-registered checks, AND
2. c5attr meets the ALERT TARGET at 3 or more of seeds 4, 5, 6, 7, with robot by-deadline within
   0.01 of the plain covex-v6-state-uo arm at the same seed.

If BOTH pass, share admission stays and c5attr is reported as a cheaper, less robust alternative.
If BOTH fail, neither is adopted and the engine flag long_prefill_token_threshold is the remaining
fallback, which is server-wide and forces every arm to be rerun.

## The three D179 (6) checks for share admission

Reported whatever the outcome, with no tuning afterwards:
1. alert per-episode target attainment at least the base's;
2. at least 90 percent of the committed rung-2 robot on-time gain over base retained;
3. assistance within 2 s at least 90 percent.

## What is reported per seed, for all three arms

plain covex-v6-state-uo, covex-v6-state-uo-c5attr, and the shares arm:
- dashcam on time / late / unsent counts, stating WHICH on-time rule each number uses (the
  coordinator's first-token flag and the scorer's t_delivered rule differ by the forward-hop
  bucket, 94 to 181 instants per cell, and both are reported);
- the dashcam verdict (per-device target, p_dash = 0.25, worst eligible device);
- robot on time and robot by-deadline;
- assistance within 2 s;
- hold time p50 and p90 per type, release_infeasible per type, planner abandonment rate.

## Two confounds recorded in advance, because they bear on how the rule reads

1. THE PLAIN ARM ALREADY MEETS DASHCAM AT SEED 6 with no fix at all (worst device 0.2646 against
   the 0.25 target), while failing at s4 and s5. So a candidate that meets at s6 has demonstrated
   nothing at that seed, and any count of "seeds met" must be read against the plain arm's own
   per-seed verdicts rather than against an assumption that the plain arm always fails.
2. C5's 0.8 s trip sits almost exactly at the p90 of its own input (monitor first-token p90 0.8374
   / 0.8063 / 0.7956 at uo s4 / s5 / s6, straddling the trip, while p50 is flat at 0.483). A
   control loop whose set point coincides with the p90 of the signal it reads will straddle a
   pass/fail line on small changes in the tail, so per-seed verdicts are expected to be noisy and
   the bucket counts carry more information than the verdicts.

## Register

The three D179 (6) checks are pre-registered PASS/FAIL conditions. The two confounds above are
stated observations from committed cells, not predictions. No outcome of any shares cell is
claimed anywhere in this file, because none exists yet.

## D181 floors: why lambda counts deliverable demand (addendum 5)

Floors reserve capacity for demand THE SYSTEM CAN DELIVER. An offered opportunity counts toward
lambda unless a FEASIBILITY check declined it; a THROTTLE decline counts.

The reason the two are not the same, which an earlier planner claim got wrong: a THROTTLE decline
is produced by the mechanism D179 replaces, so sizing the replacement from the throttle's own
restriction is circular and would bake C5's collapse into the floor meant to prevent it. A
FEASIBILITY decline is a correct decision about a request that cannot be delivered at all, and
reserving floor capacity for it takes capacity from work that can be.

Measured, which is what settles it per type rather than an assumption:
- alert: 47,098 offered, 39,949 sent, and the feasibility share of the 7,149 not sent is ZERO
  (no gate exists on that code path, and no decline counter appears in any base cell). The gap is
  entirely throttle, so lambda uses the OFFERED rate.
- recall: 485 offered, 179 sent. The 63 percent gap is b7 declining cold histories that cannot
  make a 3 s deadline, which is D147's explicit consequence. So lambda uses the SUBMITTED rate.
- assistance: 1,429 offered, 1,428 sent. b7 declines ONE request across four cells, so the choice
  does not matter to four significant figures.

Frozen: alert 1,622.1, recall 655.8, assistance 242.8 uncached tokens; sum 58.3 percent of
W_max = 4,323.3, so D180's 0.75 cap does not fire and nothing is scaled; flexible 1,802.6 (41.7
percent). Both D180 bounds are import-time assertions in experiments/orchestration/live2/
share_capacity.py so a later edit cannot silently break them.

STATED LIMITATION: the uncached and first-token factors are measured on requests the base ACTUALLY
SENT, so for recall they describe the deliverable population. If the 306 declined cold histories
are larger than those sent, and they are, the recall floor is biased DOWNWARD. That is consistent
with the rule's intent, and a cold rebuild that becomes feasible borrows from the flexible pool.
