# StudyT0b-fidelity: re-testing approval test T0 on fresh H100 data

Design log D60. Pre-registered in `research/EXPERIMENTS.md` (row StudyT0b-fidelity, 2026-11-16, on the user's
ruling, before any data for it existed; Part 2 addendum 2026-11-17, before any ENG1c-based computation). Scripts:
`experiments/orchestration/policy/score_t0b.py` with the frozen policy modules. Results:
`results/orchestration/study_t0b/`. Scoring host: flash, CPU only, no GPU. The measurement being scored was taken
on h100nvl GPU 2 by StudyENG1c-hostfull.

**THIS REPORT COVERS PART 2 UP TO THE GATE AND NOT PAST IT.** The user's gate of 2026-11-17 authorizes everything
up to the one-shot holdout scoring and stops there. The 120 StudyENG1c Part D HOLDOUT pairs were NOT built, NOT
read and NOT scored. `results/orchestration/study_t0b/t0b_holdout_eng1c.json` does not exist, and the loader
refuses to construct a holdout trial without an explicit authorization string (a test asserts the refusal).

## 0. What this re-test is, in one paragraph

StudyT0-fidelity ran approval test T0 on StudyENG1 Part C and criterion (i) FAILED: the model agreed with the
measurement on 0.586 of held-out trials against a 0.90 bar whose own measurement-repeatability ceiling was 0.8276
(see the erratum in `reports/study_t0_fidelity.md` section 0A; the figure was first reported as 83.9 %).
StudyPOL4-engine then revised the cost model, adding a host-KV transfer term, a long-prefill scale and a
batch-prefill gain, and froze it. T0b asks whether the revision holds up on data the model has never seen. The
fresh collection is StudyENG1c-hostfull Part D, whose held-out split was written at 2026-11-16T15:04:32Z before
its first request and whose 120 HOLDOUT pairs ENG1c recorded and did not analyse. This report is the FIT dry run
on ENG1c's own 360 FIT pairs, which exists to verify the adapter and to show the user and the planner what the
revision does out of sample before the holdout is spent.

**Every ENG1c pair is OUT OF SAMPLE for the model.** No StudyPOL4 coefficient and no StudyT0 parameter was fitted
on any StudyENG1c datum: terms (a), (b) and (c) were fitted on StudyENG1 Parts A, B and D and on StudyENG1b. The
360 pairs scored here are called FIT because they are ENG1c's own fit split.

## 0A. Erratum: the freeze record's git sha, and the md5s that bind it

`results/orchestration/study_t0b/t0b_freeze.json` records `git.head = 4a9facb...`. A rebase onto
origin/main (StudyENG1c-hostfull, `8b51be8`) rewrote that commit, so the recorded sha no longer exists. The freeze
file is NOT edited; the mapping and the re-verification are in the sidecar
`results/orchestration/study_t0b/t0b_freeze_erratum.json`.

| recorded in the freeze | the same commit after the rebase | the commit whose tree reproduces every frozen md5 |
|---|---|---|
| `4a9facba5c597a91a08dc8da39518c73e0263858` | `cfd30ce...` (StudyPOL4-engine Part 1) | `8e82792...` (StudyPOL4-engine Part 1b) |

**The md5s are the binding record, and they verify.** All 12 frozen md5s match the tree at `8e82792` and the
working tree exactly. Ten of the twelve also match `cfd30ce`; the two that do not,
`experiments/orchestration/policy/fit_pol4_terms.py` and `results/orchestration/study_pol4/pol4_terms.json`, were
uncommitted Part 1b files in the working tree when the freeze was taken, which the freeze itself records
(`git.clean` false, both listed in `git.porcelain`). They were committed in `8e82792`. The frozen model is
therefore unchanged, and content rather than a sha decides that.

## 0B. Pre-registration record for Part 2

| what | when (UTC) | md5 of the frozen 13-field row |
|---|---|---|
| Part 2 addendum written to the T0b row, before any ENG1c-based computation | 2026-11-17T15:48:32Z | `0d910cd1e48c4dad1a82889803bb87c0` |
| count correction (see below), before any criterion was scored | 2026-11-17T15:54:23Z | `86651ce85653e9d77a761b55b52ee429` |

**Count corrected and disclosed.** The addendum first said 240 FIT pairs at 10 per cell, which was my arithmetic
on ENG1c's 20 trials per cell with 5 held out. The record and ENG1c's own results JSON both say 15 FIT and 5
HOLDOUT per cell: **360 FIT pairs and 120 HOLDOUT pairs** over 24 cells. Only the counts changed. The cells, the
split and the design are as registered, and the correction was made before any criterion was scored.

**Two design decisions, accepted by the user in the same turn and labelled throughout.**

1. **Delay model with residency given.** The frozen model prices a host reload (term a) and a cold rebuild (term b)
   but carries no host-tier residency bookkeeping. The tier at arrival is therefore an INPUT taken from the
   measurement, exactly as Part C's cached tokens were an input to T0. Of the 360 scored trials, 235 arrived cold,
   90 host-warm and 35 locally warm, and the measured cold-versus-warm state agreed with ENG1c's write-order
   simulator in 351 of 360. Predicting residency from write volume (StudyENG1c implication 1) is a separate later
   test on ENG1c's non-holdout rows and was not started.
2. **The (i-b) ceiling comes from the 72 FIT repeat pairs.** ENG1c's repeat rule put the independent repeat on the
   first three FIT trials of each cell, so no HOLDOUT pair carries a repeat. (i-b)'s denominator is the 72 FIT
   repeat pairs over the SAME 24 cells as its numerator. That satisfies the row's "the same conditions" and not
   "the same trials", and it is the one deviation from the row's wording.

## 1. Definition audit finding: "imposed delay" has two definitions

CLAUDE.md consistency check 4 caught this before any verdict was written, and it is the single most important
methodological fact in this report.

| experiment | "imposed delay" means | reproduces ENG1c's published `imposed_s`? |
|---|---|---|
| StudyENG1 Part C, StudyT0, StudyPOL4 | sum over episodic background of **TTFT**(with) minus TTFT(without) | NO: median 1.16 s apart, max 5.71 s |
| StudyENG1c Part D | sum over episodic background of end-to-end **latency**(with) minus latency(without) | YES: max absolute difference **1.4e-14 s** over all 360 trials |

These are different quantities, not an implementation discrepancy, and the adapter reproduces ENG1c's own numbers
exactly under ENG1c's own definition. Both are scored below. The **latency** column is the primary for T0b,
because it is the collection's own published quantity; the **TTFT** column is reported beside it because StudyT0's
failing 0.586 was measured that way and only that column is comparable to it. The two agree closely in every
verdict, so nothing here turns on the choice.

## 2. Mechanism verification (CLAUDE.md Steps 1 to 5)

Recorded in `results/orchestration/study_t0b/t0b_mechanism.json`, written by the same run BEFORE any criterion was
scored; the driver stops without scoring if Step 2 finds an ABSENT or CONSTANT link.

**Step 1. Causal chain.** ENG1c Part D injects one device's next request into a running trace. If the physical
component of context inertia is real (FORMULATION.md: reconstruction cost grows with context length), then the
tier the history is in at arrival decides the action's own work: a GPU-warm or host-warm arrival needs a transfer
at most, a cold arrival a full prefill of about 11k tokens. That work occupies a shared engine, so it delays the
requests queued behind it. The model predicts the imposed delay by charging the action's prefill (term b for its
length, term c for how it batches with co-arriving prefills) or its host transfer (term a), replaying both arms of
the recorded pair and differencing them. T0b asks whether that predicted difference matches the measured one.
Because residency is given, the chain tested here starts at the action's work, not at the eviction rule.

**Step 2. Instantiation.** No link is ABSENT or CONSTANT.

| causal link | implementing quantity | value / range in this run | varies? | evidence |
|---|---|---|---|---|
| the action occupies the engine | EngineSim step time over the action's prefill | predicted imposed delay -0.0109 to 68.6 s | yes | per state: cold 0.004 to 68.6 s, host-warm -0.011 to 20.2 s, locally warm -0.002 to 12.2 s |
| a cold history costs a prefill, a host-warm one a transfer | the action's prompt and cached tokens, term (a)'s external tokens | action prompt 10,934 to 12,980 tokens; host-transferred 0 to 11,200 tokens | yes | 235 cold, 90 host-warm, 35 locally warm trials |
| the occupied engine delays what queues behind it | the paired difference of background latencies in the simulation | control with the action removed: median 0.0025 s against 3.67 s with it | yes | Step 4 (a) |
| the host tier makes a warm arrival cheap | term (a), 50.14 GB/s and 0.8845 ms fixed | action TTFT change 0.058 to 0.059 s on all 90 host trials | yes | Step 4 (b) |

**Step 3. Trace of one unit** (`27_P25|mono11k|0`, in the mechanism JSON in full). One injected request of 10,995
prompt tokens, 0 cached, 122 encoder units charged, body 0.0202 MB, injected 3.7328 s into the trace. 46 episodic
background requests in each arm. Predicted action TTFT 2.2297 s against a measured 2.2414 s. Charged in 46
simulated steps with the action against 64 without. Summed over the 46 matched background requests, the predicted
imposed delay is 29.0103 s against a measured 26.6946 s. The per-request deltas show the shape: requests 0, 10, 11
and 12 are untouched (delta 0.0000 s), request 13 jumps from 0.1326 s to 2.7610 s, and the queue drains over the
following arrivals. What bound the trial: the engine's step queue, not any KV or accelerator budget.

**Step 4. Negative controls.** Two, both on every scored FIT trial (control a on the first 40 in record order).

- **(a) Remove the action from the with arm.** The two arms are replayed from their own recorded arrival times, so
  their difference is not identically zero without an action; the control is that the residue collapses. Median
  absolute predicted delay 0.0025 s against 3.6737 s with the action on the same trials, a factor of about 1,470.
- **(b) Zero term (a)'s host-transfer input.** The term changes the ACTION's own predicted TTFT in **90 of 90**
  host trials (median 0.0586 s, the transfer of about 11k tokens) and changes the delay imposed on others in
  **46 of 90**, while changing nothing at all in **0 of 270** non-host trials. The 44 host trials where the
  imposed delay does not move are trials where no compared background request was queued behind the action, so
  the transfer lands in an idle window and reaches nobody. That is the mechanism, not an absent term.

**Step 5. Alternative explanation.** The headline could be produced by (a) the cost model pricing the action's own
work correctly, or (b) the imposed delay being dominated by how many background requests happen to arrive during
the action, which the replay reproduces from the record whatever the action costs. They separate on the
cold-versus-warm contrast within a cell: under (b) a cold and a warm arrival in the same cell would be predicted
alike, because the trace is the same. Control (b) is the sharp form of that test. A second alternative, that the
model looks good only because residency was handed to it, is why the residency input is labelled and why
predicting residency is a separate test.

## 3. Results: the four criteria on 360 ENG1c Part D FIT pairs, old model against frozen new model

`eng1` is StudyT0's frozen model, bit-identical to the one that failed on Part C. `pol4` is the frozen revision.
**OUT OF SAMPLE for the model** (nothing was fitted on ENG1c); FIT in the sense of being ENG1c's fit split.

| criterion | bar | repeatability ceiling | old `eng1` | new `pol4` | verdict on the new model |
|---|---|---|---|---|---|
| (i) delay imposed on others, absolute, latency | 0.90 | **0.8889** | 0.2972 | **0.5500** | FAIL |
| (i) the same on the TTFT definition | 0.90 | 0.9167 | 0.3056 | 0.5556 | FAIL |
| **(i-b) repeatability-scaled, latency** | **0.90 of the ceiling** | 0.8889 | 0.3344 | **0.6188** | **FAIL** |
| (i-b) the same on the TTFT definition | 0.90 of the ceiling | 0.9167 | 0.3333 | 0.6061 | FAIL |
| (ii) ranking, latency | 0.90 | n/a | **1.0000** | 0.9412 | PASS, with one pair worse than the old model |
| (ii) ranking, TTFT | 0.90 | n/a | 0.9412 | 0.9412 | PASS |
| (iii) job completion, median ARE | 0.20 | n/a | 0.1628 | **0.0496** | PASS |
| (iv) ENG1b-style prefix loss, on ENG1c Part B | 0.90 | n/a | n/a | 0.9839 | PASS but nearly degenerate, see 3.4 |

The three numbers criterion (i) must be read as, on the primary definition: the **bar is 0.90**, the
**measurement repeatability ceiling is 0.8889** (64 of 72 repeat pairs agree with each other under the criterion's
own tolerance), and the **model is 0.5500**. The old model was 59.2 points of the ceiling below it; the new model
is 33.9 points below. The bar itself is above the ceiling, so no predictor could reach 0.90 on these trials, which
is exactly why (i-b) exists: against its own scaled bar of 0.80 (0.9 x 0.8889) the model still fails, at 0.5500.

### 3.1 Per cap, per load and per action, with the direction of the error

Positive signed error is over-prediction. Medians over trials; `pass` is criterion (i) on the latency definition.

| cut | n | measured median | `eng1` pred | `eng1` pass | `eng1` med signed | `pol4` pred | `pol4` pass | `pol4` med signed |
|---|---|---|---|---|---|---|---|---|
| cap 27 GiB | 90 | 4.038 | 9.228 | 0.178 | +5.495 | 6.489 | 0.500 | +2.186 |
| cap 38 GiB | 90 | 4.023 | 9.846 | 0.200 | +5.322 | 7.336 | 0.511 | +2.233 |
| cap 60 GiB | 90 | 5.363 | 11.695 | 0.167 | +6.093 | 7.910 | 0.556 | +2.237 |
| cap 256 GiB | 90 | 0.044 | 0.015 | 0.644 | +0.022 | 0.074 | 0.633 | +0.057 |
| load P25 | 180 | 3.416 | 8.112 | 0.283 | +4.070 | 5.978 | 0.517 | +1.685 |
| load S2 | 180 | 3.178 | 8.296 | 0.311 | +5.163 | 5.748 | 0.583 | +2.030 |
| action mono11k | 120 | 12.063 | 19.522 | 0.408 | +6.227 | 14.071 | **0.908** | +1.155 |
| action piece2048 | 120 | 4.927 | 11.506 | 0.242 | +6.501 | 7.724 | 0.450 | +2.719 |
| action piece1024 | 120 | 2.855 | 7.260 | 0.242 | +4.166 | 4.880 | 0.292 | +1.974 |

Per cap and load together, `pol4` ranges from 0.467 (27 GiB, S2) to 0.756 (256 GiB, S2); the old model ranges from
0.111 to 0.733. Pooled, the error is an over-prediction in **318 of 360 trials (88.3 %)** under the new model and
297 of 360 (82.5 %) under the old one, but the median signed error falls from **+4.691 s to +1.932 s** and the
number of failing trials from **253 to 162**. Of the 162 remaining failures, 152 are over-predictions.

**Where the revision wins and where it does not.** The merged-step correction that Part 1b fitted carries
mono11k from 0.408 to 0.908 out of sample, which is the strongest confirmation in this report: the term was
chosen on ENG1 Part C and it transfers to a different host configuration and a different load generator. The
piece-wise rebuilds do not follow: piece2048 reaches 0.450 and piece1024 only 0.292, both still over-predicted by
about +2.0 to +2.7 s at the median. The predicted-over-measured ratio of medians is 1.17 for mono11k, 1.57 for
piece2048 and 1.71 for piece1024.

### 3.2 The one ranking pair the new model gets wrong, and the regression it represents

On the latency definition the old model agrees on 17 of 17 included action pairs and the new model on 16 of 17.
The single disagreement is in cell `256_S2`, mono11k against piece2048: measured medians **0.021 s and 0.009 s**,
predicted **0.059 s and 0.068 s**. The pair is included because the 2x inclusion rule compares magnitudes, and
0.021 / 0.009 = 2.39; both values are a hundredth of a second on the 256 GiB reference server, where almost every
arrival is host-warm and imposes nothing. So the regression is real and must be recorded as such under the brief's
regression stop condition, and its substance is an ordering between two medians 12 ms apart, inside the
measurement's own repeatability. On the TTFT definition both models miss exactly one pair (`256_P25`, mono11k
against piece1024) and score 0.9412.

**STOP EVENT, RECORDED 2026-11-17 on the user's ruling.** (ii) falls from 1.0000 to 0.9412 on the primary
definition while (i), (i-b) and (iii) all improve substantially. This is logged as a stop event rather than
explained away, and with it a **known limitation of the pre-registered inclusion rule**: "action pairs whose
measured values differ by more than 2x" compares MAGNITUDES, so on the 256 GiB reference server, where almost
every arrival is host-warm and imposes nothing, it admits a pair of medians 21 ms and 9 ms apart that sits well
inside the measurement's own repeatability. **The rule is NOT changed** (changing a pre-registered criterion
because it produced an inconvenient pair is exactly the move pre-registration exists to prevent). The event and
the limitation are carried in the `StudyT0b-fidelity` row of `research/EXPERIMENTS.md` and read together with the
magnitudes above.

**Primary definition fixed, before any holdout read.** On the same ruling, the LATENCY sum is the primary
definition of "delay imposed on others" for every T0b criterion and the TTFT sum is secondary, for the reasons in
section 1: the latency sum is the fresh collection's own published quantity and the adapter reproduces all 360 of
its values to 1.4e-14 s. This is recorded in the registry row so that the holdout, whenever it is spent, is scored
against a definition fixed before it was read.

### 3.3 Criterion (iii): the action's own completion time

Median absolute relative error falls from 0.1628 to 0.0496 over 360 trials, well inside the 0.20 bar. Per action
the new model gives 0.087 (mono11k), 0.039 (piece2048) and 0.019 (piece1024) against the old model's 0.272, 0.123
and 0.076. This is the cleanest out-of-sample win: the revision roughly triples the accuracy of the action's own
cost on data it never saw.

### 3.4 Criterion (iv) on ENG1c Part B: computed, nearly degenerate, and not a re-test

ENG1c Part B is the ENG1b trial repeated under host caps, and it is not part of ENG1c's holdout, so reading it
spends nothing. Class accuracy is **0.9839 (305 of 310)** with a median absolute error of 0.000 in the fraction
lost. But the measured classes are **300 total and 10 none, with `partial` never occurring**: 96.8 % of trials sit
in one class, which the pool bookkeeping gets right by construction because the filler written during the gap
(about 78.9k tokens) exceeds the free GPU pool in every trial. Under CLAUDE.md Rule 2 this is reported and is NOT
treated as a strong re-test of (iv); T0's registered (iv) result of 0.9718 stands as the informative one. The five
errors are four `total` predicted `partial` and one `total` predicted `none`.

## 4. Why criterion (i) still fails, and what measurement would close it

The residual is a systematic over-prediction concentrated in the piece-wise rebuilds under load, and its sign and
size line up with the one quantity StudyPOL4 Part 1b identified and deliberately did not model: how much of a
running prefill's remaining work a newly arrived request actually waits for. The simulator assumes full
serialization. Part 1b estimated the blocking fraction from StudyENG1 Part C FIT rows as 0.803 pooled
(CI 0.727 to 0.856), 1.149 behind a monolithic prefill and 0.679 to 0.703 behind piece rebuilds. A blocking
fraction below 1 behind piece rebuilds is exactly what an over-prediction of their imposed delay looks like, and
the ratios in section 3.1 (1.57 and 1.71 for the piece actions against 1.17 for mono) have the same ordering.

This is a consistent reading, not a demonstration: Part C and Part D both vary load and action together and
neither can separate the queue channel from the blocking channel. StudyENG1d (loaded-arrival blocking on the
H100, with its own pre-registered holdout, per the user's decision 2 of 2026-11-17) is the measurement that would
settle it.

## 5. StudyPOL4-engine Part 1b, restated for this record

The four items the user asked to see alongside the dry run. All of this is StudyPOL4 Part 1b, scored on StudyENG1
Part C FIT trials and IN-SAMPLE for the choice of terms; the full account is `reports/study_pol4_engine.md`
section 2A.

**(a) The burst4 over-prediction is the over-charge of a merged multi-prefill step.** Four candidates were checked
explicitly. Front-end serialization: 36 microseconds of a 131 ms over-prediction, 0.03 %, ruled out as a direct
channel. The compared-request set: balanced in all 406 trials, and the superset definition moves the ratio from
1.529 to 1.502, ruled out. The per-image admission stall and its possible double count with the per-image step
term: the charge for the action's own images is exactly 0.00 ms, and zeroing both coefficients changes burst4 by
less than 1e-6 s, so there is no double count to remove. Step composition: the merged 3-prefill step is predicted
at 0.2390 s against a measured floor of 0.1764 s, a ratio of **1.355** over 58 trials, matching Part A A1's
independently measured 1.084 to 1.346 on data that entered no fit. The error is in the tail of the queue behind
that step (+0.30 to 0.60 s offset, ratio 3.08; +0.60 to 1.20 s, ratio 4.06).

**(b) The batching term was kept, renamed in substance by its mechanism, and its sign flipped on correction.**
Part 1 reported the fitted exponent as a PENALTY and concluded the measurement refuted T0 diagnosis C. That was
wrong, and the error was mine: `fit_pol4_terms._a1_cells` passed each A1 cell's `N`, the query's frame count (1 or
3), where the simulator counts encoder work in the step model's own 90-token units (4 and 12). Every A1 request
was charged a quarter of its encoder work, which flipped the sign. Corrected, the exponent is **+0.100, a gain**
(10 % window 0.090 to 0.110, excluding zero; the absolute-objective secondary agrees in sign at +0.150), and the
old model gives 15 to 18 % too little batching gain at k=16 against the published anchors. Diagnosis C is
supported, the term represents the merged-step over-charge that (a) identified, and the term was therefore kept
rather than removed. The sign test in the suite was flipped and a regression guard added that re-derives every A1
cell's encoder-unit count and requires it to differ from `N`.

**(c) Loaded blocking IS identifiable from Part C FIT rows, and it was not added to the model.** Under a criterion
stated before the estimate was read (at least 30 arrivals from at least 10 trials, bootstrap CI half-width below
0.25, resampling trials rather than arrivals): rho = **0.803 [0.727, 0.856]** pooled over 1,753 arrivals in 346
trials; 0.735 at P25, 0.869 at P40, 0.759 at S2; and **1.149 [1.123, 1.206]** behind a monolithic prefill, which
is above the simulator's rho = 1 and above Part B's unloaded 0.97 to 1.00. By action: piece2048 0.969, burst4
0.703, piece1024 0.679, append5 0.494, hostreload 0.195. Reported in sample and NOT modelled, because Part C
varies load and action together and cannot separate the queue channel from the blocking channel.

**(d) The re-frozen configuration is `pol4`, all three terms, chosen by mechanism and not by score.**
`pol4_nobatch` was rejected because switching term (c) off asserts that merged multi-prefill steps are charged
correctly, which two independent measurements deny; it also scored criterion (i) lower (0.6650) and regressed (ii)
to 0.9500. On Part C FIT the frozen `pol4` gives (i) 0.7562 against a 0.8276 ceiling and a 0.90 bar it still
fails, (ii) 0.9833, (iii) 0.1039, (iv) 0.9718.

## 6. Results consistency check (CLAUDE.md, six checks)

**1. Cross-check against committed measurements.**

| quantity | this run | prior run | source of prior | ratio | agree |
|---|---|---|---|---|---|
| imposed delay per trial, latency definition | reproduced on all 360 | ENG1c `D.trials[].imposed_s` | `eng1c_results.json` | 1.000 (max abs diff 1.4e-14 s) | yes |
| criterion (i) scoring path, TTFT | 0.5556 | 0.5556 from the frozen `run_t0.evaluate_part_c` on the same trials | `run_t0.py` | 1.000 (max per-trial diff < 1e-9 s) | yes |
| host reload cost over resident, about 11k tokens | term (a) charges 0.0586 s | +0.094 s (ENG1c Part B), +0.12 s (ENG1b) | ENG1c section 4, ENG1b | 0.62 / 0.49 | yes, within 2x, and in the direction of UNDER-charging the transfer |
| criterion (i) on the old model | 0.2972 out of sample here | 0.6355 on Part C FIT, 0.586 on the Part C holdout | StudyPOL4, StudyT0 | 0.47 / 0.51 | yes, within 2x; ENG1c Part D is a harder population, 235 of 360 arrivals cold |
| repeatability ceiling for criterion (i) | 0.8889 (ENG1c Part D) | 0.8276 (ENG1 Part C) | `study_t0_fidelity.md` section 0A | 1.07 | yes |

No disagreement above 2x. The transfer-term row is noted as a limitation rather than a discrepancy: term (a) is
fitted at 50.14 GB/s and ENG1c measures about 29 GB/s for the same reload, so the term under-charges a host
transfer by roughly 35 ms, which pushes predictions DOWN and therefore cannot explain the over-prediction that
criterion (i) fails on.

**2. Physical plausibility.** The action's predicted TTFT on the traced cold unit is 2.2297 s for 10,995 prompt
tokens including 122 encoder units, about 4.9k tokens/s, against ENG1c's measured 2.2414 s on the same request and
the committed H100 build rate of about 4 to 5k tokens/s. Term (a)'s 0.0586 s for about 2.9 GB of KV is 49 GB/s,
below PCIe Gen5 x16 and 1.7x faster than ENG1c's measured 29 GB/s, so it is optimistic but not impossible.
Nothing predicted is faster than a committed curve by more than 2x.

**3. Distribution sanity.** Every criterion is reported with its n, and every cut in section 3.1 carries the
median measured, median predicted, median signed error and pass fraction; the per-trial rows are in
`t0b_fit_dryrun_eng1c.json`. The predicted imposed delay spans -0.0109 to 68.6 s and the measured spans a similar
range, so no constant appears where a distribution is expected. The two measurements of the same trial disagree
enough to fail the criterion in 8 of 72 repeat pairs, which is what sets the ceiling below 1.

**4. Definition audit.** The finding is section 1 and it is the reason this report scores both definitions. Other
named objects: "action" is T0's own three actions (mono11k, piece2048, piece1024), mapped from ENG1c's variant
names; "background condition" is (cap, load), which is what ENG1c varied, where T0's was load alone;
"compared-request set" is `COMPARED_KINDS = ("episodic",)`, unchanged from StudyPOL4 and reproducing ENG1c's own
sum exactly; "imposed delay", "encoder unit" (90 tokens) and "repeatability ceiling" are used as in StudyPOL4
Part 1b.

**5. Claim linkage.** C4, the physical component of context inertia: the dry run bears on it and supports it in
part. The cost model now predicts the action's own completion time to 5 % out of sample and ranks actions
correctly in 16 of 17 pairs, so the physical component is real and largely priced; but the delay a cold
reconstruction imposes on others is still over-predicted by about 1.6x for piece-wise rebuilds, so the quantity
the policy would schedule on is not yet trustworthy to that precision. C5, joint policy beats decomposed: not
tested here. Nothing measured falls outside FORMULATION.md's scope.

**6. Proxy validity.** Two proxies, both stated. (a) Residency at arrival is a measurement input, taken from the
injected job's own recorded cached tokens, with ENG1c's write-order simulator as a cross-check; they agree on
cold-versus-warm in 351 of 360 trials. It is valid for the delay question and says nothing about predicting
residency. (b) Term (a)'s per-request host-transfer input comes from a PER-RUN engine counter, chargeable to the
action only where the counter matches the action's cached tokens and the baseline arm's counter is zero; 14 of 360
trials fail that test and are charged nothing, which under-charges those trials and is recorded.

**Result: PASS 6 of 6, with one finding (the two definitions) and two labelled limitations** (the under-charged
transfer rate; the 14 unattributable counters).

## 7. Verdicts

- **(i) and (i-b): FAIL out of sample, and the revision roughly doubles the model's agreement.** On the primary
  definition: bar 0.90, repeatability ceiling 0.8889, old model 0.2972, new model 0.5500, (i-b) ratio 0.6188
  against a 0.90 bar. Not inconclusive: the mechanism was present and exercised (Step 2 passed on every link,
  both negative controls moved the result), so this is a real negative for the claim that the revised model
  predicts imposed delay to within the measurement's own repeatability.
- **(ii): PASS at 0.9412, with one pair worse than the old model's 1.0000**, that pair being two medians 12 ms
  apart on the 256 GiB reference server. Recorded as a regression under the brief's stop condition.
- **(iii): PASS and much improved**, median ARE 0.1628 to 0.0496.
- **(iv): PASS at 0.9839 on ENG1c Part B but nearly degenerate** (300 of 310 in one class, `partial` absent), so
  T0's registered 0.9718 remains the informative result.
- **The holdout was not touched, and on the user's ruling of 2026-11-17 it is NOT to be spent now.** 120 pairs
  remain unspent. StudyENG1d (H100, loaded-arrival blocking, running at the time of writing) measures the missing
  quantity directly, and the one-shot run waits for it.

## 9. What comes next: StudyPOL5-engine, on the user's plan of 2026-11-17

Not started, and not to be started until the StudyENG1d report exists and the user says go. Recorded here so the
sequence is on the record before any of it is fitted.

1. Add a **load-dependent blocking term**, fitted on StudyENG1d FIT trials only, with StudyENG1 Part C FIT as a
   cross-check, **per action type**. Section 4 is the evidence that this is where the residual lives.
2. **Reconcile the host transfer rate.** Term (a) uses 50.14 GB/s, fitted on StudyENG1 Part D; StudyENG1c measures
   about 29 GB/s for the same reload (section 6, check 1). Refit or extend term (a) on StudyENG1c non-holdout rows
   and state which conditions each rate applies to.
3. **Fix the primary imposed-delay definition in the frozen T0b row before any holdout read.** Done on
   2026-11-17: the latency sum is primary, the TTFT sum secondary, with the reason recorded in the row.
4. **Record the (ii) regression as a stop event and as a known limitation of the 2x inclusion rule, without
   changing the rule.** Done on 2026-11-17: section 3.2 and the registry row.
5. **Re-freeze, then run T0b one-shot on BOTH the StudyENG1c HOLDOUT and the StudyENG1d HOLDOUT**, reported
   separately.

## 10. Files

| file | what |
|---|---|
| `experiments/orchestration/policy/score_t0b.py` | NEW. The ENG1c Part D adapter, the holdout fence, both definitions, the four criteria, the repeatability ceiling and the mechanism controls |
| `experiments/orchestration/policy/tests/test_t0b_score.py` | NEW. 21 tests: the fence, the adapter against ENG1c's own numbers, the ceiling, (i-b), the residency input and the (iv) degeneracy |
| `results/orchestration/study_t0b/t0b_fit_dryrun_eng1c.json` | every number in sections 1 and 3, per trial and per cut, both models, both definitions |
| `results/orchestration/study_t0b/t0b_mechanism.json` | Steps 1 to 5 and both negative controls, written before any criterion was scored |
| `results/orchestration/study_t0b/t0b_freeze_erratum.json` | the post-rebase sha map and the re-verification of all 12 frozen md5s |
| `results/orchestration/study_t0b/t0b_freeze.json` | UNCHANGED. The freeze StudyPOL4-engine took on 2026-11-17T05:36:55Z |
