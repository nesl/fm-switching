# PRE-REGISTERED, before running: what the race-clean refit of the D156 (4) gate will do

Session D (flash / A6000), 2026-11-21 ~08:10. Committed BEFORE the refit is run, so it can fail.

## What changed

`warm-all-lru_n16_s4_1200s_h27_3t_L3_cal1f_rf` is the race-fixed rerun of the gate's contaminated
FIT cell. Reported by the H100: **HTTP 400 went 226 to ZERO** (transport 103 to 82, 200s 10,324),
robot `cache_path` WARM 9 / COLD 9 / null 2. So swapping it for the original makes the gate's fit
set **race-clean**: its co-fit cell `warm-all-lru-reactive_..._L3_cal1f` already measured 0 400s.

This isolates one question and only one: **was the FAIL caused by race contamination, or by the
model form?**

## The prediction

**The gate still FAILS, and the three failure grounds survive largely unchanged.** Specifically:

1. **Negative first-token predictions stay above 40 percent in sample.** They were 52.2 percent.
2. **The fitted intercept stays materially negative**, within a factor of about 2 of the original
   -2.3675 s.
3. **The held-out ratio stays negative**, so there is still no sense in which it is off by a factor.

## Why, and what would refute it

The negative predictions are a consequence of fitting one unconstrained linear form across two fit
cells that differ enormously in **service severity**, not of contaminated warmth. Contaminated
warmth biases the warm/cold mix; it cannot make a latency prediction negative. The severity
difference is still present after the swap, and by the H100's own numbers it is still large: the
race-clean cell sits at **4,924 uncached tok/s with dashcam first-token p50 65.6 s pooled**, which
is a crossing cell, while its co-fit `-reactive` cell never crosses. So the fit set still straddles
the transition with one cell on each side, which is the condition that drives the intercept
negative.

**This prediction is refuted if** the in-sample negative fraction drops below about 20 percent, or
the intercept comes back within about 0.2 s of zero, or the held-out ratio turns positive and lands
in 0.5 to 2.0. Any of those would mean contamination, not form, was doing the work, and would mean
my D156 (4) diagnosis was wrong.

## What it does NOT decide

Nothing here is the D159 (B) refit. That one requires a pre-registered form with **non-negative
predictions** and an explicit **queueing or capacity term**, fitted on a **controlled load sweep**,
with a held-out split containing **warm and loaded** requests. This is only the contamination
control on the existing gate, which is worth running because it is free: the cell already exists,
the estimator is imported unchanged, and only the cell list differs.

One figure is also worth recording from the rerun independently of the gate: the robot WARM count on
this cell is **9 of 18 released**, against the original's warm count, which the race suppressed.
That is a second instance of the overnight finding that the race was a confound on **warmth** and
not only on errors.

## Defect, recurring

`n_requests` and `n_errors` are **null** in `cell.json` on this cell too, which the H100 flagged
again. Already on the defect list as not warm-all-specific; this is a third arm exhibiting it.
