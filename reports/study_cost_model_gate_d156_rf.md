# The race-clean refit of the D156 (4) gate: the FAIL is the model FORM, not contamination

Session D (flash / A6000), 2026-11-21 08:15. Prediction committed at `1a491f9` **before** this ran:
`results/orchestration/live2/frozen_test/cost_model_gate_d156_rf_prediction.md`. Result:
`cost_model_gate_d156_rf.json`. Script: `v5/cost_model_gate_d156_rf.py`, which differs from the
committed FAIL run in **one fit cell and nothing else**; the estimator is still imported unchanged
from `live2/cost_model_gate.py`.

## The prediction held on all three grounds, and the gate failed slightly WORSE

| | original (contaminated fit cell) | race-clean refit | predicted |
|---|---|---|---|
| verdict | FAIL | **FAIL** | FAIL |
| intercept | -2.3675 s | **-2.8699 s** | materially negative, within about 2x |
| in-sample negative predictions | 52.2 percent | **59.8 percent** | above 40 percent |
| held-out negative predictions | 61.6 percent | 61.2 percent | n/a |
| held-out ratio p50 | -2.03 | **-2.3861** | stays negative |
| held-out p90 absolute error | 31.92 s | **41.17 s** | n/a |

None of the three refutation conditions fired: the negative fraction did not fall below 20 percent,
the intercept did not come back within 0.2 s of zero, and the held-out ratio did not turn positive.

**So the FAIL is a property of the model form, not of race contamination.** Contaminated warmth
biases the warm/cold mix; it cannot make a latency prediction negative. That was the argument, and
it survived the only test available.

## Why it got worse, which is a finding in itself

The contaminated cell's 226 HTTP 400s were **failing fast**. A 400 returns almost immediately, so
every one of them entered the fit as a short, cheap request and **masked how saturated that cell
actually was**. Removing them reveals the cell's real service behaviour:

| fit cell | first-token p50 | overlap p50 |
|---|---|---|
| `warm-all-lru _L3_cal1f` (contaminated) | 31.890 s | 969 |
| **`warm-all-lru _L3_cal1f_rf` (race-clean)** | **64.542 s** | **1,426** |
| `warm-all-lru-reactive _L3_cal1f` (co-fit, always clean) | 0.266 s | 6 |

So the severity straddle inside the fit set **widened** from about **120x to about 243x** in
first-token p50, and the overlap spread from about 161x to about 238x. The intercept moved from
-2.37 s to -2.87 s, monotonically with the straddle. That is the diagnosis confirmed by its own
dose-response: **more straddle, more negative intercept.**

It also adds a third instance to the overnight finding that the race was a confound on more than
errors. It biased **warmth** downward (measured earlier, 1 to 6 warm robot deliveries across the
fix), and it biased **apparent service health upward**, because fast failures look like fast
service. Any pre-fix cell's latency distribution is therefore optimistic in proportion to its 400
count, which is a reason to prefer the race-clean cell in the D159 (B) refit even though the FAIL
verdict does not depend on it.

## What this does and does not settle

**Settles:** v5 still does not go live, and the reason is unchanged from the 06:00 summary. The
remedy is the one D159 (B) orders, and this run says that remedy is necessary rather than optional:
no amount of cleaner data rescues an unconstrained linear form fitted across a 243x severity
difference.

**Does not settle:** whether a form with non-negative predictions and an explicit queueing term,
fitted on a controlled load sweep, transfers. That is the D159 (B) refit and it needs the sweep,
which does not exist yet.

**Positive control, unchanged (check 7):** the committed `cost_model_gate.json` records intercept
-0.024 and held-out ratios 0.91 to 1.13 over 26 cells using the same functions and the same code
path. The estimator is sound; the fit set is not. Note, from the D159 (E) audit, that those 26 cells
are all pre-race-fix, and the worst 100 s window across all of them never exceeds 2.781 s, so the
positive control passes **on cells that never straddle the transition**. That is consistent with
everything here and is the cleanest statement of the gate's real precondition: **the form holds
inside one regime and breaks across the transition.**

## Register

- All figures **MEASURED**, from the committed request logs of six cells, by an estimator imported
  unchanged.
- The prediction was **committed before the run**, at `1a491f9`, and is linked above so it can be
  checked rather than taken on trust.
- "The 400s masked saturation" is **ARGUED** from the before/after pair on one cell plus the
  mechanism that a 400 returns fast. It is one cell, so it is a mechanism proposal and not a
  measured law.

## Defect, third arm

`n_requests` and `n_errors` are **null** in `cell.json` on the rerun too. Already recorded as not
warm-all-specific; this is the third arm showing it.
