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
