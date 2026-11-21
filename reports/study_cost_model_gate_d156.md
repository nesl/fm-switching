# The D156 (4) cost-model gate: FAIL, and full v5 does not go live

**Script** `experiments/orchestration/live2/v5/cost_model_gate_d156.py`
**Result** `results/orchestration/live2/frozen_test/cost_model_gate_d156.json`
**Decisions** D151 (6), D154 (2), D156 (4), D157 (2). CPU only, committed logs only.

The overnight brief asked for the cost-model gate and said: *if the gate fails, v5 does NOT go
live; report why.* **The gate fails. This is why.**

The estimator is **not** reimplemented: `features`, `fit` and `apply` are imported unchanged from
the committed `live2/cost_model_gate.py`, so only the D156 (4) split differs. The committed
script's own `main()` skips any directory containing `_rerun`, which would silently drop a held-out
cell, so the cell list here is explicit rather than discovered.

## The split, and the first thing wrong with it

| | cells | requests | warm |
|---|---|---|---|
| **FIT**, D156 (4) CALIBRATION-1F | 2 | 27,985 | **3.1 percent** |
| **TEST**, held out, EP-G WARM-ALL upload-pf | 4 | 42,417 | **88.6 percent** |

**The model's cache-state term is fitted on a population that is 3 percent warm and applied to one
that is 89 percent warm, a 29x difference in the regime the gate exists to test.**

## The verdict: FAIL, on three independent grounds

Fitted model: `first_token = -2.3675 + 3.063e-04 * uncached + 0.04662 * overlap`

| | n | predicted p50 | actual p50 | ratio | **negative predictions** |
|---|---|---|---|---|---|
| in sample (CAL1F) | 27,985 | **-1.2727 s** | 0.7629 s | **-1.67** | **52.2 percent** |
| held out (EP-G) | 42,417 | **-1.4344 s** | 0.7081 s | **-2.03** | **61.6 percent** |

1. **The model predicts NEGATIVE first-token latency for 52.2 percent of its own fit data and 61.6
   percent of the held-out data.** A negative first-token time is physically impossible, so the
   model is **invalid, not inaccurate** (consistency check 2). This is visible **in sample**, with no
   held-out test needed.
2. **The held-out ratio is negative**, so there is no sense in which the model is "off by a factor".
3. **The held-out p90 absolute first-token error is 31.92 s**, against a 1.0 s dashcam deadline
   (D154 (1)) and a 3.0 s robot deadline. Within-regime it is worse, 184.8 s.

**Consequence, stated as the brief requires: full v5 does NOT go live.** D154 (2) forbids any v5
cell while MARGIN_CF is unset, and MARGIN_CF is defined off a gate that does not pass.

## A reductio that settles the MARGIN_CF units question

D154 (2) defines MARGIN_CF as **the gate's held-out p90 absolute prediction error**. D157 (2) later
names the units as `0.250 * |P_hat - 1[on time]|`, p90, over robot questions. **Taken literally on
the cost model, D154 (2) would set MARGIN_CF to 31.92 seconds**, larger than every deadline in the
system, which would make every counterfactual deviation either always or never permitted.

**So D154 (2)'s latency reading is unusable and D157 (2)'s on-time-probability reading must govern.**
That is settled by arithmetic rather than by preference, and it is worth recording because the two
definitions were never reconciled in the log.

**And the latency p90 is not even a robot quantity.** Of the 4,242 held-out requests above the p90
of absolute first-token error: **4,129 are dashcam, 108 single-shot, 5 robot.** A margin taken from
it would be calibrated on dashcam monitors and spent on robot recall decisions.

## The diagnosis: the FIT set is internally confounded by arm

| cell | n | warm | first-token p50 | **overlap p50** | prompt tokens p50 |
|---|---|---|---|---|---|
| CAL1F `warm-all-lru` | 14,031 | 3.3 pc | **31.890 s** | **969** | 378 |
| CAL1F `warm-all-lru-reactive` | 13,954 | 2.8 pc | **0.266 s** | **6** | 378 |
| EP-G `warm-all-lru-off` | 12,126 | 91.1 pc | 0.452 s | 10 | 3,760 |
| EP-G `warm-all-lru-reactive` | 12,523 | 91.3 pc | 0.446 s | 10 | 3,422 |
| EP-G `warm-all-lru` `_rf` | 8,257 | 83.4 pc | **99.507 s** | **2,048** | 3,760 |
| EP-G `warm-all-lru` `kv0.25` | 9,511 | 86.1 pc | **138.554 s** | **2,529** | 3,760 |

**The two fit cells differ by 160x in overlap and 120x in first-token latency on the same
workload.** OLS must span overlap 6 to 969 with one linear term, and it buys the fit at the cheap
end by driving the intercept to **-2.37 s**. That is the whole mechanism of the failure.

**This is the gate's recorded defect recurring in a new form.** `policy_v5_assessment.md:23` already
says of the previous gate that *warm is confounded with arm*. Here **load** is confounded with arm,
**inside the fit set**, which is worse: the earlier confound limited what the gate could identify,
this one makes the fitted model physically invalid.

## Positive control (consistency check 7): the instrument is sound, the fit set is not

The committed `cost_model_gate.json` recorded, over 26 pre-EP-G cells, intercept **-0.024** and
held-out first-token ratios of **0.91 to 1.13**. Same functions, same code path. **So this estimator
produces a sound model where overlap is small and homogeneous, and an invalid one on this fit set.**
An impossible failure that reproduces on one data set and not another is evidence about the data
set. **The check is not broken and the estimator is not broken; the D156 (4) fit set is.**

## Retraction: the queue is created by the ARM, not by EP-G

**I was about to write that D153's EP-G format created the queue that breaks the model, and the
table above refutes it.** On the same EP-G workload, `-off` and `-reactive` sit at 0.45 s and
overlap 10 while `warm-all-lru` sits at 99.5 s and overlap 2,048. On the same CAL1F workload,
`warm-all-lru` is already at 31.9 s and overlap 969 while `-reactive` is at 0.27 s and overlap 6.

**So unconditional prefill drives overlap from about 10 to about 2,000, a 200x load increase, and
EP-G multiplies the result by roughly 3x (31.9 s to 99.5 s on the same arm).** The arm is the first
order term and the workload the second. Recorded before it was published, unlike the earlier
register error in `study_v5_rules.md`.

**This independently corroborates the central v5-rules finding on a different arm.** v5-rules'
83,961 prefills and warm-all-lru's overlap of 2,048 are the same mechanism measured two ways:
prefilling ahead of demand buys cache residency and spends the engine.

**One further note on the quarter pool.** `kv0.25` has *higher* overlap (2,529 against 2,048) and a
*deeper* queue (138.6 s against 99.5 s) than the full pool, while its warm share is unchanged (86.1
against 83.4 percent). So shrinking the KV pool did not reduce warm residency; it raised the
re-prefill load. **Warm residency on this workload is not pool-capacity-bound, but load is.**

## What is NOT done here, because it would be a methodological change

The failure is attributable to the fit set, so **a refit on a fit set that is not internally
confounded by arm might pass.** D156 (4) pre-registered the fit set, so changing it is the user's
decision and not mine at 04:00. Options, my default first:

1. **Leave it. The gate fails as pre-registered, MARGIN_CF stays unset, full v5 does not go live.**
   My default, and it requires no decision.
2. Refit on a fit set stratified by load, or excluding the `warm-all-lru` CAL1F cell as a
   high-load outlier. Changes the pre-registered split; also the excluded cell is the only fit cell
   that exercises the loaded regime, so this trades one confound for a coverage gap.
3. Change the model form, constraining the intercept to be non-negative or fitting in log space,
   and add a queueing term. **This is the remedy the data actually points at**, because a linear
   overlap term cannot describe a system whose first-token latency spans 0.27 s to 138 s. It is a
   change to the instrument and needs pre-registration.

**Also noted:** the CAL1F `warm-all-lru` fit cell carries 226 HTTP 400s and 103 transport errors, so
under D158 (4) it is **race-affected**, and it is the same cell that is the load outlier. The other
five cells have zero 400s.

## Mechanism verification and consistency checks

- **Step 0** asked what would invalidate this run: a fit or test cell that is invalid or
  race-affected. All six cells are `run_valid` true; the fit cell's race-affected status is recorded
  above rather than discovered after.
- **Step 2** the read that consumes the quantity: `cf_planner` feasibility, via `apply`. Not
  exercised here, because the gate must pass before the planner may use the model.
- **Check 2 (physical plausibility)** is the check that fails, and it fails in sample.
- **Check 3 (distribution sanity)** the 160x overlap spread inside the fit set is the artefact
  spread this check exists to surface.
- **Check 7 (validate the control)** the committed gate's own recorded ratios are the positive
  control and they pass, which is what licenses the conclusion being about the fit set.
- **Rule 2** this is not a null, it is a failed gate, so the taxonomy does not apply.
