# StudyT0-fidelity: does the policy's cost model predict live engine behaviour it has never seen?

Pre-registered in `research/EXPERIMENTS.md` (row StudyT0-fidelity). CPU only on flash: no GPU, no
model server, no inference. Every live measurement replayed here was taken on h100nvl GPU 2 by
StudyENG1-steptime and StudyENG1b-prefix-survival; this row only predicts and compares.
Approval test T0 of `research/POLICY_SPEC_v3.md` sections 5.2 and 11.

**Pre-registration order.** CLAUDE.md requires an E-id row before work starts and the brief
forbids editing `research/EXPERIMENTS.md` until the end, because a second session (StudyCTRL1c)
was editing the repository concurrently and a mid-run edit risked clobbering its work. The full
13-field row text, including the four pass criteria VERBATIM as the brief states them, was
therefore written to a frozen scratchpad file BEFORE anything was computed, at
2026-11-16T22:34:26Z (md5 44cbb9c82ea7cc540f0c90519c9271e2; one formatting-only correction at
22:34:46Z, still before any computation, removing a placeholder character from the registry's
blank 13th cell). The row was inserted verbatim from that frozen text at the end of the session
after re-reading the registry immediately beforehand. The criteria below are reproduced from that
file and were not changed after any result was seen.

**Headline, in one table.**

| # | criterion, verbatim as pre-registered | result | verdict |
|---|---|---|---|
| i | "Delay imposed on others: prediction within 1.5x of measured, or within 0.1 s absolute for small values, for at least 90 % of HOLDOUT triples." | **bar 90 % \| measurement repeatability ceiling 83.9 % \| model 58.6 %** (102 of 174) | **FAIL** |
| ii | "Ranking: within each background condition, the predicted ordering of actions matches the measured ordering for at least 90 % of action pairs whose measured values differ by more than 2x." | 61 of 63 included pairs = 96.8 % | **PASS** |
| iii | "Job completion time: median absolute relative error at most 20 %." | 16.69 % over 174 | **PASS** |
| iv | "ENG1b prefix loss: none/partial/total class correct for at least 90 % of trials; also report MAE of fraction lost." | 828 of 852 = 97.2 %; MAE of fraction lost 0.0247 | **PASS** |

**Criterion (i): the FAIL STANDS, and it is a REAL FIDELITY GAP, not only an over-strict bar.**
Three numbers belong together and are reported together everywhere this verdict appears:

| the bar | the measurement repeatability ceiling | the model |
|---|---|---|
| **90 %** (pre-registered) | **83.9 %** (73 of 87: StudyENG1's own independent repeats scored on the same criterion) | **58.6 %** (102 of 174 holdout triples) |

> **ERRATUM, 2026-11-17: the ceiling is 82.76 %, not 83.9 %.** See section 0A. The verdict,
> the FAIL, the classification as a real fidelity gap and every other number in this report are
> unchanged; the shortfall of the model below the ceiling widens from 25.3 to 24.2 points.

Two things are true at once and neither cancels the other. The bar was set above what the
measurement can support, so a perfect predictor would also have failed it. **And the model falls
well below the ceiling as well**: it agrees with the measurement on 58.6 % of trials where the
measurement agrees with itself on 83.9 %, a shortfall of 25.3 points that the bar's strictness
does not explain. The clearest single case is the monolithic 11k action, where the measurement is
perfectly repeatable on FIT data (noise ceiling 1.000) and the model still passes only 52.9 %
(section 11). This is therefore classified a **REAL NEGATIVE and a real fidelity gap**, NOT
inconclusive and NOT merely an artefact of the threshold. Section 7 gives the arithmetic, section
11 attributes the gap, and section 12 pre-registers T0b, whose criterion (i-b) scales the
tolerance to the measurement's own repeatability so that the bar and the gap can be separated.

---

---

## 0A. Erratum: the repeatability ceiling is 82.76 %, not 83.9 %

**Raised and traced by StudyPOL4-engine on 2026-11-17** while reproducing this report's numbers
under the old model, and recorded here on the user's instruction. It changes no verdict.

**What this report says.** The repeatability ceiling for criterion (i) is quoted as **83.9 %**
(0.8391, 73 of 87 repeat pairs) at every site where the bar/ceiling/model triple appears: the
headline above, the verdict table of section 7, sections 9 and 10, the interpretation in section
11.6 and the ruling record in section 11.7.

**What is correct.** **82.76 %** (0.8276, **72** of the same 87 repeat pairs).

**The cause.** The `COMPARED_KINDS` fix recorded in section 8, check 1 of this report. The
registered one-shot holdout run summed the imposed delay over the superset of background kinds,
which wrongly included the eight warm sessions' own appends in the W25 cells; the corrected
definition sums over the episodic background stream only, which is StudyENG1 section 9's published
quantity. That fix landed between the one-shot run and the dry-run re-score. It moves exactly one
repeat pair out of the passing set, and the pair is identified rather than inferred: scoring the
same 87 repeats both ways gives **73 of 87 under the superset definition and 72 of 87 under the
episodic-only one**, and the single trial that flips is **`W25|piece1024|0`**, a W25 cell, which
is where the two definitions can differ at all. So the ceiling computed from the corrected
definition is 72 of 87 and the 83.9 % figure is the PRE-FIX value. This report's committed dry-run artifact
`results/orchestration/study_t0/t0_dryrun_partc_fit.json` already records 0.8276; only the prose
carried the pre-fix number forward. StudyPOL4 reproduces 0.8276 exactly from the same 87 repeats
and records the cross-check in `reports/study_pol4_engine.md` section 6, check 1.

**What does not change.** The model's 58.6 % is scored on the holdout and is untouched by this.
The bar is 90 % and is pre-registered. The FAIL stands. The bar is still above the ceiling, so a
perfect predictor would still have failed; and the model is still well below the ceiling, so this
is still a real fidelity gap and not only an over-strict bar. The one quantity that moves is the
size of that shortfall: **24.2 points, not 25.3**. The registered verdict, its log and the frozen
artifacts are NOT edited, in keeping with the user's ruling of 2026-11-16 that the registered T0
verdict and its log stay exactly as run; this erratum sits beside them.

**Where the figure is used downstream.** T0b's criterion (i-b) is a RATIO and does not contain the
number, so the pre-registered criterion is unaffected; the figure it cited in its rationale
(section 12) is corrected in place to 82.76 % with a pointer here. StudyPOL4-engine quotes 0.8276
throughout, which is the post-fix value.

## 1. What was predicted, and from what

For each recorded trial the rollout is fed the trial's ACTUAL recorded background arrivals, sizes
and timings plus the server configuration, and predicts:

* the total delay the action imposes on all other requests;
* the action's own completion time;
* (StudyENG1b) none / partial / total loss of the built prefix and the fraction lost.

**The engine model is StudyENG1's measurement and nothing else** (`policy/eng1_engine.py`). The
step model is loaded from `results/cost/study_eng1/eng1_step_model.json`, which StudyENG1 fitted
on Part A and Part B E0 steps and whose own `fit_data` field states that Part C and the HOLDOUT
never entered it; the loader REFUSES a model file that does not state its fit data. The structure
around it is read from `reports/study_eng1_steptime.md`: the two-regime serial front end
(section 7), batched short prefills and the single partial-prefill slot for long ones (H-step and
H-admit verdict a, sections 5 and 6), the admission stall as the next step's images and encoder
tokens (section 8), 8,192-token chunked prefill and a 62,944-token KV pool as PARAMETERS
(section 1.2), and 90 prompt tokens per D2 frame (section 11 check 4). **No coefficient was
fitted in this row and a test asserts that no fitted number is typed into the module.**

**The unit of comparison is the paired difference** (ambiguity A35). StudyENG1 Part C measures the
imposed delay as the sum, over background requests matched by index, of TTFT(with) minus
TTFT(without) across a with-arm and a without-arm replay of the same background trace. T0
predicts that same difference the same way: each arm is simulated from its own recorded arrival
times and the prediction is the difference of the two simulated sums. Any error common to both
arms cancels in the prediction exactly as it cancels in the measurement. Section 8 check 6 states
why this is a declared proxy and what distinguishes it from the alternative.

**Caching, stated per CLAUDE.md.** The live runs had vLLM prefix caching ON throughout, and every
Part C request was cold except where a cached prefix was the object of measurement; StudyENG1
verified this with 0 cached-token mismatches over 30,164 compared background requests. This row
reads each request's recorded `cached_tokens` as an INPUT, so a piece on a cached prefix is
simulated as warm and a monolithic request as cold, exactly as recorded. No number here mixes a
warm and a cold condition.

---

## 2. Step 1, the dry run on Part C FIT trials

406 FIT trials (580 Part C trials total, 174 held out), all 406 reconstructible: every setup
request finished before its trace started, so no trial needed a setup replay, and the measured
and predicted sums matched over the same request set in all 406.

| criterion | dry run (FIT, n = 406) | verdict |
|---|---|---|
| i, delay within 1.5x or 0.1 s | 258 of 406 = 63.6 % | FAIL |
| ii, ranking | 58 of 60 included pairs = 96.7 % | PASS |
| iii, completion, median absolute relative error | 16.43 % | PASS |

Per load and per action:

| load | n | fraction passing (i) | measured p50 (s) | predicted p50 (s) | completion median ARE |
|---|---|---|---|---|---|
| P25 | 84 | 0.750 | 0.1676 | 0.1440 | 0.140 |
| P40 | 84 | 0.488 | 0.3922 | 0.4064 | 0.162 |
| S2 | 84 | 0.821 | 0.1202 | 0.1949 | 0.159 |
| S4 | 84 | 0.452 | 0.6003 | 0.9978 | 0.204 |
| W25 | 70 | 0.671 | 0.2221 | 0.2676 | 0.189 |

| action | fraction passing (i) | completion median ARE |
|---|---|---|
| append5 | 0.700 | 0.180 |
| burst4 | 0.543 | 0.275 |
| hostreload | 0.571 | 0.394 |
| mono11k | 0.529 | 0.157 |
| piece1024 | 0.629 | 0.117 |
| piece2048 | 0.829 | 0.081 |

### 2.1 Two implementation fixes found in the dry run, and why each is an implementation fix

The brief permits fixing IMPLEMENTATION bugs found in the dry run and requires stopping and
reporting instead of changing the MODEL. Two were found. Neither adds a term and neither refits a
coefficient; both correct how the committed model is USED.

**Fix 1: short prefills must share a step.** The first implementation serialized every prefill at
the request level, taking StudyENG1's H-admit verdict (a) and dropping its H-step verdict. That is
wrong use of the committed model, not a conservative choice: Part A A1 measured BATCHES of k
simultaneous small prefills (k in 1, 2, 4, 8, 16) and those batched steps ARE part of the step
model's own 5,974-step fit data, so the model's `per_prefill_req` and `per_encoder_input` terms
are per-step aggregates over a batch. Serializing every prefill evaluates the model outside the
batch compositions it was fitted on. The scheduler now admits waiting requests FCFS up to the
8,192-token step budget, while a prefill too large for one step holds the single partial-prefill
slot and runs alone, which is H-admit. Effect: the burst4 cells moved from per-cell median ratios
of 2.0 to 4.0 down to 1.1 to 1.95, and nothing else moved materially.

**Fix 2: the compared request set.** Caught not by the dry run but by CLAUDE.md's consistency
check 1, and fixed on FIT data only. See section 8 check 1; the fix changed no verdict.

### 2.2 Did the dry run show the MODEL is wrong?

This is one of the brief's STOP AND ASK conditions and it was evaluated explicitly. **It did not
trigger**, and the reasoning is recorded so it can be overruled.

The dominant systematic is that the monolithic 11k action's imposed delay is over-predicted by a
factor of about 1.3 to 1.9. It is traceable to a 1.09x over-prediction of that request's own
blocking duration, amplified by the queue. Three facts say the model is biased rather than wrong:

| solo cross-check, with no difference to cancel | predicted | StudyENG1 measured | ratio |
|---|---|---|---|
| monolithic ~11k cold request, client TTFT | 2.921 s | 2.673 s (Part B solo, E0) | 1.09 |
| 2,048-token piece on an ~11k cached prefix | 0.596 s | 0.564 s (A2, c ~11k) | 1.06 |
| N=1 episodic request | 0.108 s | 0.135 to 0.141 s | 0.78 |

and the predicted and measured imposed delays are strongly correlated across trials whose
measured value spans an order of magnitude: r = 0.955 for mono11k, r = 0.951 for piece2048,
r = 0.647 for burst4, r = 0.072 for hostreload (whose measured values are inside StudyENG1's own
repeat noise and therefore carry no signal in either direction). A model that is wrong does not
rank-order a 10x spread at r = 0.95. The judgement recorded here is that this is a QUANTIFIED
FIDELITY LIMIT with a named mechanism, not a wrong model, and that the honest response is to
report the bias and let the pre-registered criterion fail. **If the reader disagrees, the
decision to overrule is theirs: nothing in this row was corrected against the holdout.**

---

## 3. Step 2, the freeze

The working-tree git hash and an md5 of every model, parameter and source file whose exact bytes
decide the prediction were recorded BEFORE the holdout run, re-verified at the instant of the run
by `t0_harness.FrozenState.verify`, and written to
`results/orchestration/study_t0/t0_freeze.json`.

* frozen at 2026-11-16T22:57:57.788975+00:00
* git HEAD `ea4a6e8116ba0ed1b7746a792d36be43dc1f4009`, branch `main`
* working tree NOT clean, and that is RECORDED rather than corrected: this row's own uncommitted
  library changes were present, which is why the file md5s and not the commit are what identify
  the model that was tested

| md5 at freeze | file |
|---|---|
| `7da0a984bca4ba4f0ff81d5cee54d18c` | `results/cost/study_eng1/eng1_step_model.json` |
| `d390037af3d48abdc3f91572fe6e8ccd` | `experiments/orchestration/policy/eng1_engine.py` |
| `8e3eabdff05184e3d95eacbe7c5bf358` | `experiments/orchestration/policy/trace_replay.py` |
| `69e2622e9e49e5503a3a9a8a09651f61` | `experiments/orchestration/policy/kvpool.py` |
| `b4607d14d0897eaed4a02d55f75cdb51` | `experiments/orchestration/policy/tiers.py` |
| `abbbca7ae904e41851ca4b99fae73345` | `experiments/orchestration/policy/params.py` |
| `2c41bdef137d79f3ca816ae190da9a42` | `experiments/orchestration/policy/t0_harness.py` |
| `25fe3914aae7534c81a53d265a046e4c` | `experiments/orchestration/policy/run_t0.py` |

**The one-shot mode.** `T0Harness.run` still refuses any split named holdout, eval or test, and
any split name it does not recognize, unchanged. The single authorized run went through the new
`T0Harness.run_holdout_once`, which (a) requires a `FrozenState` that verifies against the
working tree at run time, (b) requires a non-empty `authorization` string recording who
authorized it, (c) appends a log line with the UTC timestamp, the git head and every file md5 to
`t0_one_shot.log`, and (d) REFUSES a second run once a result file exists. A refused run never
calls the computation at all, which five tests assert, including that the result file is not
created and that the callable is never invoked.

Log line of the run that happened: started 2026-11-16T22:57:57.808389+00:00, finished
22:57:58.559239+00:00, host `nesl-Z790-CLASSIFIED`, authorization "user brief of 2026-11-16:
'This one HOLDOUT run is authorized by the user.' (StudyT0-fidelity, Part 2 Step 3)".

**Two file md5s changed AFTER the run** and the change is declared here rather than discovered
later. `trace_replay.py` is now `72b743a2b730fa19841f1ed72f352b98` and `run_t0.py` is now
`393821de3e3ea36c2724b8537c781f08`, because CLAUDE.md's consistency check 1 (section 8) found a
definition error after the holdout had been run and the fix was applied on FIT data. **The
holdout result file and `t0_freeze.json` were not touched, the holdout was not re-run, and the
holdout numbers in this report are the ones the one-shot run produced under the frozen bytes.**
Section 8 check 1 quantifies the fix's effect on FIT data and shows it changes no verdict.

---

## 4. Step 3, the holdout: run once, 174 triples

All 174 held-out triples reconstructed; none had to be dropped. The pre-registered criteria, with
StudyENG1's measurement noise beside each one:

| criterion | holdout result | threshold | verdict | noise from ENG1's independent repeats | noise alone fails it? |
|---|---|---|---|---|---|
| i, delay within 1.5x or 0.1 s | **bar 0.90 \| ceiling 0.8391 \| model 0.5862** (102 of 174) | 0.90 | **FAIL** | the same criterion applied to two independent measurements of the same trial passes 73 of 87 = 0.8391 | yes for the bar, AND the model is 25.3 points below the ceiling as well, so the FAIL is a REAL FIDELITY GAP and not only an over-strict bar |
| ii, ranking of action pairs differing by more than 2x | 61 of 63 = 0.9683 | 0.90 | **PASS** | evaluated on per-cell MEDIANS over 6 trials, so the relevant noise is the median's; the per-cell repeat spread has p50 0.0101 to 0.3148 s against cell medians of 0.02 to 69 s | no |
| iii, completion time, median absolute relative error | 0.1669 | 0.20 | **PASS** | NOT AVAILABLE: StudyENG1 repeated the without-arm only, so the action's own completion time has no repeat | cannot be computed |
| iv, ENG1b prefix loss class | 828 of 852 = 0.9718, MAE of fraction 0.0247 | 0.90 | **PASS** | StudyENG1b ran 6 repetitions per cell with Wilson intervals; no repeat of a single trial exists | cannot be computed |

### 4.1 Per load

| load | n | fraction passing (i) | measured p50 (s) | predicted p50 (s) | completion median ARE |
|---|---|---|---|---|---|
| P25 | 36 | 0.750 | 0.227 | 0.217 | 0.127 |
| P40 | 36 | 0.500 | 0.567 | 0.560 | 0.180 |
| S2 | 36 | 0.750 | 0.265 | 0.196 | 0.149 |
| S4 | 36 | 0.417 | 0.593 | 1.034 | 0.199 |
| W25 | 30 | 0.500 | 0.489 | 0.484 | 0.223 |

### 4.2 Per action

| action | n | fraction passing (i) | measured p50 (s) | predicted p50 (s) | completion median ARE |
|---|---|---|---|---|---|
| append5 | 30 | 0.767 | 0.060 | 0.027 | 0.171 |
| burst4 | 30 | 0.367 | 0.343 | 0.645 | 0.323 |
| hostreload | 24 | 0.458 | 0.034 | 0.020 | 0.415 |
| mono11k | 30 | 0.533 | 37.114 | 44.688 | 0.127 |
| piece1024 | 30 | 0.467 | 0.245 | 0.308 | 0.109 |
| piece2048 | 30 | 0.900 | 1.186 | 1.157 | 0.079 |

### 4.3 Per cell

| cell | n | pass (i) | measured p50 (s) | predicted p50 (s) |
|---|---|---|---|---|
| P25 append5 | 6 | 1.00 | -0.015 | 0.030 |
| P25 burst4 | 6 | 0.50 | 0.245 | 0.435 |
| P25 hostreload | 6 | 0.67 | 0.039 | 0.002 |
| P25 mono11k | 6 | 0.83 | 24.949 | 32.711 |
| P25 piece1024 | 6 | 0.50 | 0.198 | 0.145 |
| P25 piece2048 | 6 | 1.00 | 0.538 | 0.467 |
| P40 append5 | 6 | 0.83 | 0.068 | 0.023 |
| P40 burst4 | 6 | 0.17 | 0.399 | 0.840 |
| P40 hostreload | 6 | 0.50 | 0.022 | 0.034 |
| P40 mono11k | 6 | 0.00 | 44.914 | 82.280 |
| P40 piece1024 | 6 | 0.50 | 0.475 | 0.276 |
| P40 piece2048 | 6 | 1.00 | 1.469 | 1.480 |
| S2 append5 | 6 | 0.83 | 0.089 | 0.054 |
| S2 burst4 | 6 | 0.67 | 0.188 | 0.300 |
| S2 hostreload | 6 | 0.33 | -0.058 | 0.020 |
| S2 mono11k | 6 | 0.83 | 21.391 | 29.506 |
| S2 piece1024 | 6 | 0.83 | 0.156 | 0.113 |
| S2 piece2048 | 6 | 1.00 | 0.605 | 0.680 |
| S4 append5 | 6 | 0.67 | 0.117 | 0.184 |
| S4 burst4 | 6 | 0.17 | 0.662 | 1.499 |
| S4 hostreload | 6 | 0.33 | 0.152 | 0.063 |
| S4 mono11k | 6 | 0.00 | 69.218 | 134.435 |
| S4 piece1024 | 6 | 0.33 | 0.544 | 0.762 |
| S4 piece2048 | 6 | 1.00 | 2.709 | 3.550 |
| W25 append5 | 6 | 0.50 | 0.055 | -0.001 |
| W25 burst4 | 6 | 0.33 | 0.476 | 0.601 |
| W25 mono11k | 6 | 1.00 | 36.616 | 38.026 |
| W25 piece1024 | 6 | 0.17 | 0.154 | 0.362 |
| W25 piece2048 | 6 | 0.50 | 1.394 | 1.328 |

Two cells, P40 mono11k and S4 mono11k, pass 0 of 6. Both are the heavy-load monolithic cells
where the amplification of section 2.2 is largest.

### 4.4 The worst-predicted holdout trials, with a diagnosis

| trial | measured (s) | predicted (s) | absolute error (s) | ratio | diagnosis |
|---|---|---|---|---|---|
| S4 mono11k 0 | 75.893 | 153.969 | 78.075 | 2.03 | A | 
| S4 mono11k 3 | 66.036 | 139.889 | 73.852 | 2.12 | A |
| S4 mono11k 10 | 61.106 | 131.130 | 70.024 | 2.15 | A |
| S4 mono11k 15 | 65.897 | 128.993 | 63.096 | 1.96 | A |
| S4 mono11k 16 | 72.399 | 132.417 | 60.018 | 1.83 | A |
| S4 mono11k 11 | 78.752 | 136.454 | 57.702 | 1.73 | A |
| P40 mono11k 11 | 58.462 | 113.775 | 55.313 | 1.95 | A |
| P40 mono11k 9 | 79.451 | 131.449 | 51.998 | 1.65 | A |
| P40 mono11k 19 | 44.607 | 86.450 | 41.843 | 1.94 | A |
| P40 mono11k 10 | 45.221 | 78.110 | 32.889 | 1.73 | A |

Every one of the ten largest absolute errors on the holdout is the same failure. There are three
diagnoses in all, and the first accounts for all ten.

**A, queue amplification of a 9 % blocking error.** The monolithic ~11k action blocks the engine
for the whole of its prefill (H-admit verdict a), so the delay it imposes is a sum over every
arrival that queues behind it, and under the heaviest loads (P40 Poisson, S4 four periodic
streams) that is 12 to 45 requests per trial. The step model over-predicts the action's own
blocking by 1.09x (2.921 s against a measured 2.673 s solo). Because each queued arrival inherits
the whole remaining block, a 9 % error in the block becomes a 70 to 115 % error in the sum, and it
grows with load, which is exactly the pattern: P25 passes 5 of 6, P40 and S4 pass 0 of 6. A term
that shortened the 8,192-token step would fix it and would be a MODEL CHANGE, so it was not made.

**B, no host KV transfer term.** `hostreload` is the worst-predicted action for its own completion
time (median ARE 0.415) because the engine model has no term for an external KV transfer at all:
the recorded external cache hits are treated as free, while StudyENG1 Part D measured the reload
as +0.067 s over GPU-resident plus a 2.93 GB transfer in about 80 ms. Adding such a term is a new
term and therefore a model change, so it was not made. Its imposed delay carries no information
either way: the measured values (p50 -0.058 to 0.152 s) are inside StudyENG1's own repeat noise
for those cells, which StudyENG1 itself flagged.

**C, sub-linear batching under-modelled for a burst.** `burst4` is over-predicted by about 1.4 to
2.3x per cell median even after the batching fix, and its completion-time ARE is 0.323. Four
378-token prefills arriving together now share steps, but the step model's linear
`per_encoder_input` and `per_prefill_req` terms do not reproduce the full H-step gain measured at
larger k (batch time(16) / 16 x time(1) = 0.510 for N=1). Closing that gap means a new
interaction term, which is a model change.

---

## 5. Step 4, StudyENG1b: mechanistic prefix loss, 852 trials

**Weaker evidence than the holdout test, and labelled so.** StudyENG1b has no held-out split, so
these 852 trials are the whole study. No parameter used here was fitted on ENG1b and the measured
staircase was not called: the prediction is `kvpool.KVPool` bookkeeping only, given the server's
pool size (62,944 tokens, read from the ENG1b result file per server load), the built prefix as
the single UNREFERENCED entry, and the recorded allocation of other work during the gap.

Primary pressure variable: allocation before the resume was SCHEDULED, which is StudyENG1b's
version (ii) and its own stated valid quantity. The PRE-REGISTERED version (i), allocation before
the resume was ISSUED, is reported beside it.

| | class accuracy | verdict at the 90 % threshold | MAE of fraction lost |
|---|---|---|---|
| version (ii), before scheduling (primary) | 828 of 852 = 0.9718 | **PASS** | 0.0247 |
| version (i), before issue (as pre-registered in ENG1b) | 735 of 852 = 0.8627 | FAIL | 0.1337 |

The gap between the two is StudyENG1b's own finding, not a new one: when a resume queues behind a
still-running filler build, the filler keeps allocating between issue and scheduling, so version
(i) undercounts pressure in exactly those trials. Under version (i) the errors are 107 total
losses predicted as none; under version (ii) they are not.

**Confusion matrix, version (ii) (measured to predicted):**

| measured | predicted none | predicted partial | predicted total |
|---|---|---|---|
| none (647) | 647 | 0 | 0 |
| partial (32) | 6 | 21 | 5 |
| total (173) | 13 | 0 | 160 |

The classes are not degenerate: 647 none, 32 partial, 173 total, and the predictor gets all three.

| cut | n | class accuracy | MAE of fraction |
|---|---|---|---|
| E0 | 426 | 0.977 | 0.017 |
| KV-HOST | 426 | 0.967 | 0.033 |
| 1,024-token pieces | 192 | 1.000 | 0.002 |
| 2,048-token pieces | 660 | 0.964 | 0.031 |
| gap 0.5 s | 132 | 1.000 | 0.001 |
| gap 2 s | 228 | 1.000 | 0.002 |
| gap 5 s | 132 | 0.970 | 0.017 |
| gap 10 s | 228 | 0.961 | 0.031 |
| gap 20 s | 132 | 0.917 | 0.085 |

**Where every error is, and why.** 24 trials are misclassified. 19 of them are W25 cells, whose
accuracy is 0.683 against 0.976 to 1.000 for every other load. Every one of the six worst is a
W25 trial whose prefix was measured TOTALLY lost while the recorded allocation (16,278 to 46,780
tokens) is well below the free pool (52,552 tokens) and the pool therefore predicts none. That is
precisely the mechanism StudyENG1b identified: the 8 warm sessions re-reference their own cached
contexts during the gap, which moves those blocks behind the deferred prefix in the free queue
WITHOUT counting as new allocation, so the effective free pool is smaller than capacity minus
prefix. `kvpool.KVPool.reference` implements that mechanism and a unit test shows the free order
reversing, but the ENG1b per-trial record exposes only the AGGREGATE allocation and not the
per-request re-reference timeline, so the replay cannot feed the mechanism the input it needs.
This is a LIMIT OF THE RECORDED DATA, not of the model, and it is why W25 is reported separately
rather than pooled away. Split out: over the 792 non-W25 trials the class accuracy is 787 of 792
= 0.9937 with an MAE of the fraction lost of 0.0067; over the 60 W25 trials it is 41 of 60 =
0.6833. The pooled 0.9718 is the number the pre-registered criterion is scored on and it is the
one in the headline table; the split is reported so the pooled figure is not mistaken for uniform
accuracy.

---

## 6. Mechanism verification (CLAUDE.md Steps 1 to 5)

Recorded BEFORE the holdout sweep, at 2026-11-16T22:55:08Z, frozen in the session scratchpad
(md5 5a2c39460fa8f562c901f1330a92a608) and reproduced here. The dry run and the negative control
had been run at that point; the holdout had not been read, predicted or evaluated.

**Step 1, the causal chain.** T0 does not test a policy claim; it tests whether the policy's cost
model predicts the engine, so the chain is the chain of physical cause inside the engine. One
action's work enters a shared accelerator whose capacity is finite (FORMULATION.md section
Constraints 2, serving feasibility: work must be materialized on the serving node). Its body is
parsed and rendered by a SERIAL front end, which delays the hand-off of every request behind it
(StudyENG1 section 7). Its prefill then occupies the engine: short prefills that fit one step's
token budget are batched with others and the step grows sub-linearly (H-step), while a prefill
too large for one step holds the single partial-prefill slot and every later arrival waits for
its remaining chunks (H-admit verdict a). Each step's duration is set by its composition (the
fitted step model) and each image-bearing admission puts a multimodal preparation stall on the
critical path of whatever is running (section 8). The consequence is that the action's cost is
paid twice, once as its own completion time and once as delay imposed on every other request, and
the second is the quantity the rollout must predict to score an action at all (spec 3.5 and 5.1;
spec 5.2 makes T0 the precondition for relying on it). For StudyENG1b the chain is A6's: a built
prefix whose request has finished is cached but UNREFERENCED (FORMULATION.md Constraints 1,
ready-capacity: KV that is not held is not ready), other work's allocation takes free blocks in
free-queue order, and once allocation exceeds the blocks not holding the prefix its TAIL is
overwritten, which is why deferring a piece costs a restore.

**Step 2, each link instantiated.**

| causal link | implementing quantity | value / range in this run | varies as expected? | evidence |
|---|---|---|---|---|
| the action's body occupies a serial front end | `eng1_engine.frontend_service_s` | 0.021 s (hostreload, 0.02 MB) to 0.471 s (mono11k, 21.9 MB) | yes, by body size | step logs; committed fit 29.6 + 20.2/MB idle, 6.9 + 17.7 busy |
| short prefills batch into one step | `EngineSim._schedulable` to the 8,192-token budget | burst4's 4 x 378 tokens share steps; batching moved the burst4 cell ratios from 2.0-4.0x to 1.1-1.95x | yes, only below the budget | dry run before and after fix 1 |
| a long prefill holds the partial slot and blocks | the same function returning one request | mono11k's 11,043 new tokens occupy 2 steps of 1.901 s and 0.549 s alone | yes, only above the budget | solo cross-check 2.921 s against 2.673 s measured |
| step duration is set by composition | `StepModel.step_ms` | 0.028 s (decode only) to 1.901 s (8,192 tokens, 91 images) | yes, by tokens, images, batch size, cached context | `eng1_step_model.json`, R^2 0.985 on 5,974 steps |
| the admission stall is on the critical path | the model's two admission terms | 0 to 0.166 s per admitted batch | yes, with the next step's images | committed coefficient; the 41-plus-image bin is 66 ms |
| imposed delay accumulates over the queue | difference of two replays | predicted 0.000 to 153.97 s; measured -1.43 to 79.45 s | yes, by action and load, and correlated r = 0.955 (mono11k), 0.951 (piece2048) | dry run and holdout |
| allocation evicts an unreferenced prefix, tail first | `kvpool.KVPool.allocate` | predicted lost fraction 0.0 to 1.0 over 852 trials, 0 below 1.0 of the free pool | yes, a step function of allocation and not of gap | ENG1b: accuracy 0.9718, MAE 0.0247 |

No link is ABSENT or CONSTANT, so the sweep was not blocked. Two links are WEAK and are named
rather than passed: the engine has NO term for host KV transfer, which is diagnosis B; and the
1,024-token ENG1b cells never reach a partial loss, so the tail-first rule is exercised by the
2,048-token cells only.

**Step 3, one traced unit.** Unit: one Part C trial, P40 piece2048 trial 0, a FIT trial.

```
arm WITHOUT: t0_trace 1794796886.298881, 61 background requests, 0 actions
  setup b7532x865 (setup_prefix, 11,024 prompt tokens, 0 cached) finished 1.400 s BEFORE the
  trace start, so it is in neither arm's timeline and leaves only the cached prefix the action
  row records
arm WITH:    t0_trace 1794796900.455634, the same 61 background requests, 1 action
  setup b7534x865 finished 1.406 s before the trace start
  ACTION C7533x865-inj, submitted 3.9449 s into the trace
    inputs      13,094 prompt tokens, 11,008 cached  ->  2,086 NEW tokens
                23 frames; body 5.3319 MB; 1 output token
    front end   idle at its arrival -> 29.6 + 20.2 x 5.3319 = 137.3 ms
    engine      2,086 new tokens fit one 8,192-token step, so the action is BATCHED with
                whatever else is schedulable; its step carries 23 images and a cached
                context of 11,008 tokens (the per token x cached-context term)
    KV bytes    not binding in this trial; the GPU pool is not the Part C constraint
    accelerator the action's step time is charged to the engine timeline, and every request
                in that step has its output delayed by it
    outcome     predicted action completion 0.5970 s | measured 0.6138 s | ARE 2.7 %
  eight largest predicted per-request delays, against their measured values:
    episodic 24   pred 0.7391 - 0.1363 = +0.6028    meas 0.5221 - 0.1464 = +0.3757
    episodic 25   pred 0.6611 - 0.1510 = +0.5101    meas 0.6279 - 0.1597 = +0.4682
    episodic 28   pred 0.6030 - 0.1422 = +0.4609    meas 0.3744 - 0.2701 = +0.1043
    episodic 26   pred 0.5744 - 0.1596 = +0.4148    meas 0.5415 - 0.1683 = +0.3732
    episodic 30   pred 0.5508 - 0.2549 = +0.2959    meas 0.4087 - 0.2179 = +0.1908
    episodic 29   pred 0.5986 - 0.3040 = +0.2946    meas 0.3701 - 0.1526 = +0.2176
    episodic 32   pred 0.4411 - 0.1707 = +0.2703    meas 0.2614 - 0.1558 = +0.1056
    episodic 27   pred 0.3780 - 0.1342 = +0.2438    meas 0.3452 - 0.1424 = +0.2029
  summed over all 61 matched background requests:
    PREDICTED total imposed delay 3.6679 s
    MEASURED  total imposed delay 2.4554 s      ratio 1.49
  what bound it: the engine step. Not the KV pool and not the front end: the action's 2,086 new
  tokens fit one step, and the delay is that step's duration over the requests whose output it
  delayed plus the cascade of arrivals that then queue behind them.
```

Unit: one ENG1b trial, E0_2048, load P25_f1, gap 5.0 s, repetition 5.

```
  prefix built            10,389 tokens
  GPU KV pool             62,944 tokens  (a PARAMETER, not a constant)
  free pool               62,944 - 10,389 = 52,555 tokens
  allocated by other work before the resume was SCHEDULED      33,902 tokens
  33,902 <= 52,555, so make_room frees nothing
  PREDICTED  lost 0 tokens, fraction 0.000, class "none"
  MEASURED   lost 5 tokens (local hits 10,384), class "none" under ENG1b's 32-token tolerance
  what bound it: nothing. The allocation never exceeded the free pool, which is the mechanism
  and the reason a 5-second gap cost nothing.
```

**Step 4, the negative control.** Cell: P40 piece2048, the 14 FIT trials, which is also the
Step 3 cell. Mechanism disabled by REMOVING the action from the with-arm replay, so the only
remaining difference between the two replays is the arms' recorded submit instants. The median
absolute predicted imposed delay falls from 1.1322 s with the action to 0.0074 s with it removed,
a ratio of 0.0065: removing the mechanism removes 99.35 % of the prediction. It is not bit-zero
because the two arms are separate live runs whose submit instants differ by StudyENG1's measured
dispatch jitter (at most 3.3 ms) and the replay uses each arm's own recorded arrivals, so the
control asks whether that floor is negligible against the effect rather than whether it is
exactly zero. File: `results/orchestration/study_t0/t0_negative_control.json`.

**Step 5, the alternative explanation.** A pass on the delay criteria could be produced by (a) the
engine model reproducing the engine's step-level behaviour, the claimed mechanism, or (b) the
PAIRING doing the work: because the prediction is a difference of two replays of the same arrival
schedule, a model that got every absolute TTFT wrong by a constant would still predict the
difference, so a pass could reflect cancellation rather than fidelity. Three things in the data
distinguish them. First, the solo cross-checks have no difference to cancel and still agree
(2.921 against 2.673 s; 0.596 against 0.564 s; 0.108 against 0.135 to 0.141 s). Second,
alternative (b) predicts no relationship between the SIZE of the predicted and measured
differences, while the data give r = 0.955 for mono11k across trials spanning 8 to 88 s. Third,
criterion (iii) is an ABSOLUTE quantity with nothing to cancel and it is scored on the same runs
and passes at 16.69 %. For ENG1b the alternative is that the class is right because almost all
trials are "none" and the predictor is nearly constant; the confusion matrix refutes it (647
none, 32 partial, 173 total, all three predicted).

**Rule 2 classification.** Criterion (i)'s FAIL is not a null from an absent mechanism: Step 2
found no ABSENT or CONSTANT link and Step 4 showed the result collapses when the mechanism is
removed, so the mechanism was present and operated. It is a **REAL NEGATIVE** and **NOT
INCONCLUSIVE**, on both of CLAUDE.md's grounds: the mechanism was present (Step 2 found no ABSENT
or CONSTANT link) and the control changed the result (Step 4). Reported with the three numbers
together, bar 90 % | ceiling 83.9 % | model 58.6 %: the bar was above what the measurement
supports, AND the model is 25.3 points below that ceiling, so the shortfall is a real fidelity
gap in the model and not only a property of the threshold. Criteria (ii), (iii) and (iv) are
positives and need no classification.

---

## 7. The noise comparison: the bar, the ceiling and the model, side by side

StudyENG1 ran an INDEPENDENT REPEAT of the without-run for 87 FIT trials (3 per cell, all FIT, so
reading them touches no holdout datum). For each of those the imposed delay can be computed two
ways that differ ONLY by run-to-run noise: sum(with - without) and sum(with - repeat). Applying
criterion (i) to that pair gives the fraction the criterion could reach from measurement
reproducibility alone, which is a ceiling no prediction can exceed.

**bar 0.90 | measurement repeatability ceiling 0.8391 (73 of 87) | model 0.5862.** The ceiling is
below the bar, so the criterion fails on noise alone. The model is a further 25.3 points below
the ceiling, so it ALSO fails against what the measurement supports. Both statements are
reported; neither is used to excuse the other.

Per-cell repeat spread, as the absolute summed delay of the repeat against the without-run:

| cell | n | p50 (s) | max (s) | cell | n | p50 (s) | max (s) |
|---|---|---|---|---|---|---|---|
| P25 append5 | 3 | 0.0370 | 0.0593 | S4 append5 | 3 | 0.1114 | 0.1311 |
| P25 burst4 | 3 | 0.0603 | 0.1099 | S4 burst4 | 3 | 0.0103 | 0.0296 |
| P25 hostreload | 3 | 0.0466 | 1.7765 | S4 hostreload | 3 | 0.0289 | 0.0296 |
| P25 mono11k | 3 | 0.0429 | 0.3657 | S4 mono11k | 3 | 0.0905 | 0.1465 |
| P25 piece1024 | 3 | 0.0377 | 0.0713 | S4 piece1024 | 3 | 0.1586 | 0.3159 |
| P25 piece2048 | 3 | 0.0375 | 0.0947 | S4 piece2048 | 3 | 0.0616 | 0.0909 |
| P40 append5 | 3 | 0.1536 | 0.7708 | W25 append5 | 3 | 0.0555 | 0.9581 |
| P40 burst4 | 3 | 0.0533 | 0.6268 | W25 burst4 | 3 | 0.0253 | 0.1652 |
| P40 hostreload | 3 | 0.2191 | 0.2904 | W25 mono11k | 3 | 0.0305 | 0.2195 |
| P40 mono11k | 3 | 0.3148 | 0.3174 | W25 piece1024 | 3 | 0.0749 | 0.1042 |
| P40 piece1024 | 3 | 0.1422 | 0.2034 | W25 piece2048 | 3 | 0.0532 | 0.5190 |
| P40 piece2048 | 3 | 0.1783 | 1.2881 | S2 (all six cells) | 18 | 0.0083 to 0.0496 | 0.1318 |

Pooled over all 87: p50 0.0503 s, p90 0.3152 s, max 1.7765 s.

Why this breaks criterion (i). The criterion's 0.1 s absolute allowance is smaller than the p90
of the measurement's own reproducibility (0.315 s), so in the near-noise cells the measurement
disagrees with itself by more than the window; and its 1.5x ratio test is applied to quantities
whose measured value is sometimes a small number of either sign (the holdout's P25 append5 median
is -0.015 s and S2 hostreload is -0.058 s), where a ratio is not a meaningful statistic at all. A
criterion stated on per-trial sums of a quantity with this much run-to-run variance cannot be met
at 90 % by anything. **It was pre-registered as written and is reported as FAIL as written; it is
not restated, reweighted or recomputed on medians here.** Section 9 says what a replacement
criterion would have to look like.

---

## 8. Results consistency check (CLAUDE.md, six checks)

**1. Cross-check against committed measurements. PASS, after ONE DISAGREEMENT FOUND, DIAGNOSED
AND FIXED.**

The decisive check is that the MEASURED quantity this row computes from the raw logs reproduces
StudyENG1 section 9's published per-cell table, because if it does not, T0 is comparing
predictions against a different quantity than the one the experiment reported.

| quantity | this run | prior committed value | source of prior | ratio | agree |
|---|---|---|---|---|---|
| Part C imposed delay, all 24 non-W25 cell medians | 0.0131 to 71.2122 s | 0.01 to 71.2 s | StudyENG1 section 9 | 0.93 to 1.31 | yes, every cell reproduces to the published precision |
| Part C imposed delay, the 5 W25 cell medians, FIRST implementation | 0.1911, 0.1314, 23.4614, 0.2496, 0.9033 s | 0.05, 0.06, 16.9, 0.14, 0.44 s | StudyENG1 section 9 | 3.82, 2.19, 1.39, 1.78, 2.05 | **NO, three cells over 2x** |
| Part C imposed delay, the 5 W25 cell medians, AFTER the fix | 0.0536, 0.0642, 16.8934, 0.1360, 0.4406 s | the same | the same | 1.07, 1.07, 1.00, 0.97, 1.00 | yes |
| monolithic ~11k solo TTFT, predicted | 2.921 s | 2.673 s | StudyENG1 Part B solo, E0 | 1.09 | yes |
| 2,048-token piece on ~11k, predicted | 0.596 s | 0.564 s | StudyENG1 A2 | 1.06 | yes |
| N=1 episodic solo TTFT, predicted | 0.108 s | 0.135 to 0.141 s | StudyENG1 Part B, D7b | 0.78 | yes |
| GPU KV pool | 62,944 tokens | 62,944 | StudyENG1 1.2, ENG1b 3, SLICE1 | 1.00 | yes |
| ENG1b prefix sizes | 10,389 to 10,392 and 4,992 tokens | 10,390 to 10,392 and 4,992 | StudyENG1b section 3 | 1.00 | yes |

**The disagreement, diagnosed.** StudyENG1 section 9's published per-cell table sums over the
EPISODIC BACKGROUND STREAM ONLY. In the W25 cells the trace also carries 8 warm sessions' appends
and escalations; those requests run and occupy the engine, but they are NOT in the published sum.
The first implementation summed over them too, which inflated all five W25 medians, three of them
by more than 2x. Restricting the summed set to the episodic stream, while keeping the warm
sessions in the SIMULATION because they really do take engine time, reproduces all five published
medians exactly (16.8934 against 16.900 for W25 mono11k; 0.4406 against 0.440; 0.1360 against
0.140; 0.0642 against 0.060; 0.0536 against 0.050). The fix is `trace_replay.COMPARED_KINDS`, it
is documented in that module's docstring, and two tests pin it, one asserting that including the
warm sessions does NOT reproduce the published value so the definition cannot drift back.

**What that means for the holdout, stated plainly.** The fix was found AFTER the one-shot holdout
run and the holdout was NOT re-run. The holdout numbers in section 4 therefore use the superset
definition for the 30 W25 triples (5 cells x 6) and the identical definition for the other 144,
since outside W25 the two definitions coincide. The effect on the verdicts is bounded by
arithmetic and by the FIT comparison:

* criterion (i) FAILS under both definitions. On FIT data the fix moved it from 0.6034 (245 of
  406) to 0.6355 (258 of 406), both far below 0.90. On the holdout, even if ALL 30 W25 triples
  passed, the maximum attainable would be 132 of 174 = 0.759, so no definition of the W25 subset
  can make criterion (i) pass.
* criterion (iii) PASSES under both: 0.1643 on FIT after the fix against 0.1669 on the holdout,
  and the action's own completion time does not depend on the compared set at all.
* criterion (ii) PASSES under both on FIT: 0.9833 (57 of 58) before the fix and 0.9667 (58 of 60)
  after. It is the one criterion whose holdout value could in principle move, because it is
  computed on per-cell medians and the five W25 medians change by about 2x. **RESOLVED on the
  user's ruling of 2026-11-16**: the holdout was NOT re-predicted and not re-run, and criterion
  (ii) was re-scored from the SAME frozen predictions as a labelled SECONDARY check, giving 59 of
  61 = 0.9672 PASS against the registered 61 of 63 = 0.9683 PASS. See section 10.1.

A definition-corrected RE-RUN of the holdout was **not taken**, on the user's ruling: the
registered verdict and the one-shot log stand exactly as run, and the correction is reported as a
separate secondary score instead. The one-shot fence was never overridden and the registered
artifacts are byte-identical before and after (section 10.1).

**2. Physical plausibility. PASS.**

| measurement | implied rate | committed curve | flag |
|---|---|---|---|
| predicted 8,192-token prefill step, 91 images | 4.31k tok/s | StudyENG1 engine-only 5.3k tok/s, SLICE1 5.3k tok/s | SLOWER than committed, so not a caching artefact |
| predicted monolithic ~11k end to end | 3.78k tok/s | StudyENG1 measured 4.2k tok/s end to end | slower, fine |
| predicted 2,048-token piece on a cached prefix | 3.50k tok/s of NEW tokens | StudyENG1 A2 3.67k tok/s equivalent | 0.95, fine |
| ENG1b eviction arithmetic | exact token bookkeeping against a pool size | n/a | no rate to be implausible |

Nothing predicted is faster than its committed curve, which is the direction CLAUDE.md's check 2
exists to catch. The bias of this model is the opposite one, over-prediction of cost, which is
what diagnosis A describes.

**3. Distribution sanity. PASS.** Every reported median carries its spread: the result JSONs hold
min, p10, p50, p90, max and mean per load, per action and per cell, with n; section 7 reports the
noise distribution rather than a single noise number; and section 5 reports ENG1b's confusion
matrix and per-cut tables rather than a pooled accuracy alone. No constant appears where a
distribution is expected: the 174 holdout predictions take 174 distinct values, the mono11k cells
span 50.9 to 154.0 s predicted against 30.0 to 79.5 s measured, and the ENG1b predicted fractions
are bimodal with 21 intermediate values, matching the measured bimodality with 32 partial losses.
The one place a distribution WAS collapsed is named in `reports/study_pol3_update.md` check 3:
`ENG1B_STAIRCASE` holds bin means, and it is not used here.

**4. Definition audit. PASS, with one name corrected and three pinned.**

| object | definition used in this run | prior committed definition | match |
|---|---|---|---|
| imposed delay on others | sum over the EPISODIC background requests, matched by index, of TTFT(with) - TTFT(without) | StudyENG1 section 9's published table, which this now reproduces in all 29 cells | yes, AFTER the fix of check 1; the first implementation used a superset and is recorded above |
| action completion time | for one action its latency; for a burst, last completion minus first submit | StudyENG1 records `latency_s` per request; the burst rule is stated here because StudyENG1 reports a burst's delay but not one completion time | stated, new for bursts |
| a step | the busy interval between consecutive output batches | StudyENG1 section 2.4, which validated it and REJECTED `elapsed_ms` | yes |
| a frame | 90 prompt tokens | StudyENG1 section 11 check 4 | yes |
| a piece | a prefix-chained request at 1,024 or 2,048 tokens | SLICE1 and StudyENG1 | yes |
| cold | cached tokens at or below 16 on a fresh namespace | StudyENG1 and SLICE1 | yes, read from the record |
| fully resident | local hits at or above prefix minus 32 tokens | StudyENG1b section 7 check 4 | yes |
| free pool | KV capacity minus prefix tokens | StudyENG1b, user point 2 | yes |
| pressure | allocation before the resume was SCHEDULED, with before-ISSUE reported beside it | StudyENG1b version (ii) and version (i) | yes, both reported |

**5. Claim linkage. PASS.** Criterion (iii)'s PASS and criterion (ii)'s PASS bear on spec 5.2 and
11, which make T0 the precondition for relying on the rollout, and on `research/CLAIMS.md` C5
(joint policy beats decomposed) INDIRECTLY: they do not support C5, they remove one of the
obstacles to testing it, since StudySIM1d's engine model failed out of sample on exactly the
slice-versus-episodic mixtures these traces contain. Criterion (iv)'s PASS bears on C4 (physical
inertia, warm versus cold) by showing that the restore cost A6 prices is PREDICTABLE from pool
bookkeeping, not merely real. Criterion (i)'s FAIL bears on spec 5.2's tolerance language and says
that a per-trial tolerance of this kind is not the right instrument. Nothing measured here is
scoped out by `research/FORMULATION.md`: all KV involved is the SAME model's, so the section
Scoping line on KV portability does not apply, and the host tier of StudyENG1b holds the same
model's KV. One quantity does not map to a claim and is reported as such: the action's own
completion time is an engine property the policy needs but no claim rests on.

**6. Proxy validity. PASS with three proxies declared.** (i) THE PAIRED DIFFERENCE as the imposed
delay: it is what StudyENG1 measures, so it is not a proxy for the measurement, but it IS a proxy
for engine fidelity, since errors common to both arms cancel. It is valid for the criterion as
written and NOT sufficient on its own to claim the model predicts absolute latencies; the solo
cross-checks and criterion (iii) are what carry that, and Step 5 says so. (ii) 90 TOKENS PER FRAME
as the encoder-token count: it is StudyENG1's own frame definition and it reproduces the committed
41-plus-image admission stall (18.1 ms per 1k encoder tokens x 91 x 90 = 66.8 ms against a
measured 66 ms), so it is valid at large image counts; at 1 to 4 images the step model
under-predicts the measured stall by 20 to 28 ms and that residual is left in, declared, and is
part of why small-delay cells scatter. (iii) STUDYENG1b's AGGREGATE ALLOCATION as the pressure a
prefix sees: valid everywhere except W25, where the re-reference mechanism needs a per-request
timeline the record does not expose; W25 is reported separately and is NOT pooled into a headline.

---

## 9. Interpretation, kept separate from the verdicts

Nothing in this section changes a number above.

**What T0 establishes.** The policy's cost model, built from StudyENG1's measurement and with no
coefficient fitted in this row, predicts out of sample: it RANKS actions correctly (96.8 % of
holdout pairs that differ by more than 2x) and it predicts an action's own completion time to a
median 16.7 % relative error, both on 174 triples it had never seen, under a freeze whose hashes
are recorded. That retires the specific failure T0 exists to catch. StudySIM1d's engine model
failed out of sample on slice-versus-episodic interactions, which is why spec 5.2 put T0 before
any reliance on the rollout; this model does not fail that way on those mixtures.

**What T0 does not establish.** The model is BIASED HIGH on the imposed delay, by about 1.3x on a
cell median and up to 2.15x on the heaviest single trial, concentrated entirely in the monolithic
cold-prefill action under heavy load. The mechanism is understood (diagnosis A: a 9 % error in a
2.7-second block, amplified by 12 to 45 queued arrivals), so a scheduler using this model will
systematically OVERSTATE the cost of a monolithic reconstruction relative to a piece. That
direction matters for the next gate: it biases the policy TOWARD smaller pieces and away from
monolithic rebuilds, which is the direction the policy is already expected to prefer, so a
later finding that the policy prefers pieces must be read with this bias in mind and cannot be
claimed as a clean result until either the bias is removed or an ablation shows the preference
survives without it.

**Criterion (i) measured two things at once, and both are real.** Bar 90 % | ceiling 83.9 % |
model 58.6 %. The bar was above the measurement's own repeatability, so part of the FAIL is a
property of the threshold: its 0.1 s absolute window is narrower than the measurement's p90
reproducibility (0.315 s), and its 1.5x ratio test is applied to per-trial sums that are
sometimes small and of either sign. **That does not explain the FAIL and must not be used to
soften it.** The model is 25.3 points below the ceiling, 77.7 % of its FIT failures are
over-predictions, and on the one action where the measurement is perfectly repeatable on FIT data
(monolithic 11k, ceiling 1.000) the model still passes only 52.9 % with a median over-prediction
of +10.13 s. **This is a real fidelity gap in the cost model.** The right response is therefore
both: a criterion that separates the two (T0b's (i-b), section 12, which scales the tolerance to
the measurement's own repeatability) AND work on the over-prediction itself, which section 11
localizes to the monolithic cold prefill and the small-prefill burst.

**The ENG1b result is the strongest thing here and the weakest evidence.** 97.2 % class accuracy
and an MAE of 0.0247 on the fraction lost, from pool bookkeeping with no ENG1b-fitted parameter
and without calling ENG1b's own measured staircase, is a strong mechanistic result: the A6
deferral risk is computable from capacity, the unreferenced prefix and the recorded allocation.
But ENG1b has no held-out split, so these 852 trials are the whole study and the result is not a
held-out test, which is why it is reported beneath the holdout rather than beside it. The 19 W25
errors are the honest edge: the mechanism that explains them is implemented and tested, and the
recorded data cannot drive it.

**One number to carry forward.** The pre-registered version (i) pressure variable would have
scored 86.3 % and FAILED, against 97.2 % for version (ii). StudyENG1b had already identified (ii)
as the valid quantity and labelled (i) an invalid proxy, so this is a case where the earlier
study's own post-hoc refinement was right and the pre-registration was wrong. Both are reported.

---

## 10. The two open decisions, as ruled by the user on 2026-11-16

**Q1, the holdout re-run: KEEP ONE-SHOT, ADD A LABELLED SECONDARY.** The registered T0 verdict,
`t0_holdout_partc.json` and `t0_one_shot.log` stand exactly as run and are not superseded.
Criterion (ii) is re-scored under the corrected compared-request definition as a clearly separate
SECONDARY check from the same frozen predictions. Section 10.1.

**Q2, criterion (i): the FAIL STANDS.** Reported as bar 90 % | ceiling 83.9 % | model 58.6 %
wherever the verdict appears, classified a REAL NEGATIVE and a real fidelity gap, and NOT as
inconclusive. T0b is pre-registered in section 12 with a repeatability-scaled criterion (i-b).

### 10.1 SECONDARY check: criterion (ii) under the corrected compared-request definition

**This is a SECONDARY, LABELLED re-score. It does not replace the registered verdict.**

| scoring of criterion (ii) | included pairs | agreeing | fraction | verdict |
|---|---|---|---|---|
| **REGISTERED** (as the one-shot run scored it) | 63 | 61 | **0.9683** | **PASS** |
| **SECONDARY, corrected definition** | 61 | 59 | **0.9672** | **PASS** |

**The error being corrected is a SCORING-DEFINITION ERROR, not a model change.** StudyENG1
section 9's published per-cell table sums the imposed delay over the EPISODIC background stream
only; the registered run also summed the 8 warm sessions' appends and escalations that exist in
the W25 cells. What changed is **which requests enter the sum**, nothing else. This is verifiable
rather than asserted: of the eight files frozen before the one-shot run, six are byte-identical
today, including the step model JSON (`7da0a984bca4ba4f0ff81d5cee54d18c`) and the engine model
`eng1_engine.py` (`d390037af3d48abdc3f91572fe6e8ccd`). The only two that changed,
`trace_replay.py` and `run_t0.py`, changed solely in the summed set.

**No re-prediction.** `run_t0.holdout_secondary_criterion_ii` first recomputes the registered
SUPERSET-summed predicted and measured delay for all 174 trials and **refuses to continue unless
every one matches the registered file to within 1e-9**. It matched for all 174, so the secondary
score is a different SUMMATION of predictions already made, not new predictions. The registered
artifacts were opened read-only for that check and were not modified: `t0_holdout_partc.json`
remains `d9559db97e5681d8cc174f71701d4213` and `t0_one_shot.log` remains
`30e24b72c968339453a99b68c62e791f`, unchanged before and after.

**Exactly which cells the bug affected: the five W25 cells, and no others.** Outside W25 the two
definitions coincide, because there the background IS the episodic stream, so 144 of the 174
holdout triples are scored identically under both.

| affected cell | registered median (s) | corrected median (s) | ratio | moved more than 2x |
|---|---|---|---|---|
| **W25 append5** | 0.0555 | -0.0034 | -16.13 | **YES** |
| **W25 piece1024** | 0.1541 | -0.0030 | -52.24 | **YES** |
| **W25 piece2048** | 1.3937 | 0.6734 | 2.07 | **YES** |
| W25 burst4 | 0.4758 | 0.3613 | 1.32 | no |
| W25 mono11k | 36.6160 | 29.8495 | 1.23 | no |

The three cells whose medians moved by more than 2x are **W25 append5, W25 piece1024 and W25
piece2048**. In the first two the corrected median is a near-zero negative value, which is the
expected consequence of removing the warm sessions: what remained was an episodic-only sum inside
the measurement's own noise. That is also why the secondary scoring includes two fewer pairs (61
against 63): two action pairs no longer differ by more than the 2x gate, so the criterion
excludes them by its own pre-registered rule.

**Both scorings fail the same two pairs**, and they are the same two: P25 append5 versus
hostreload (measured -0.0147 and 0.0389 s) and P40 append5 versus hostreload (measured 0.0679 and
0.0218 s). Both are comparisons between two actions whose imposed delay is a few tens of
milliseconds, i.e. inside the repeat noise for those cells, so the ranking that is missed is a
ranking between two effects that are not separated by the measurement either. The conclusion is
unchanged by the correction: criterion (ii) PASSES, and the only pairs it misses are near-noise.

File: `results/orchestration/study_t0/t0_holdout_secondary_criterion_ii.json`.

---

## 11. Error tables and the attribution of criterion (i)'s failure

**FIT TRIALS ONLY.** Every number in this section comes from the 406 Part C FIT trials and the 87
FIT repeats. No diagnosis in this section looks at the holdout, because a model corrected against
the holdout would make every later comparison on it in-sample, and because the holdout is now
spent (section 12). The holdout's own per-load, per-action and per-cell tables are in section 4
and are reported, not diagnosed.

### 11.1 Per action (a), with the direction of error (b)

`noise` is the same criterion applied to two independent measurements of the same trial, per
action, i.e. the ceiling for that action. `med_signed` is median(predicted minus measured), so a
positive value is OVER-prediction. `med_ratio` is median(predicted / measured).

| action | n | model pass (i) | noise ceiling | measured p50 (s) | predicted p50 (s) | med_signed (s) | med_ratio | % over-predicted | completion median ARE |
|---|---|---|---|---|---|---|---|---|---|
| mono11k | 70 | 0.529 | **1.000** | 22.215 | 31.178 | **+10.134** | **1.48** | **97 %** | 0.157 |
| burst4 | 70 | 0.543 | 0.867 | 0.219 | 0.286 | +0.131 | **1.66** | **83 %** | 0.275 |
| hostreload | 56 | 0.571 | 0.750 | 0.049 | 0.005 | -0.008 | **0.21** | 48 % | 0.394 |
| piece1024 | 70 | 0.629 | 0.800 | 0.222 | 0.222 | +0.015 | 1.00 | 56 % | 0.117 |
| append5 | 70 | 0.700 | 0.667 | 0.079 | 0.096 | -0.000 | 0.84 | 50 % | 0.180 |
| piece2048 | 70 | 0.829 | 0.867 | 0.740 | 0.872 | +0.146 | 1.16 | 74 % | 0.081 |

### 11.2 Per load (a), with the direction of error (b)

| load | n | model pass (i) | noise ceiling | measured p50 (s) | predicted p50 (s) | med_signed (s) | med_ratio | % over-predicted | completion median ARE |
|---|---|---|---|---|---|---|---|---|---|
| S4 | 84 | 0.452 | 0.833 | 0.600 | 0.998 | **+0.321** | **1.54** | **83 %** | 0.204 |
| P40 | 84 | 0.488 | **0.611** | 0.392 | 0.406 | +0.156 | 1.21 | 68 % | 0.162 |
| W25 | 70 | 0.671 | 0.867 | 0.222 | 0.268 | +0.068 | 1.09 | 64 % | 0.189 |
| P25 | 84 | 0.750 | 0.889 | 0.168 | 0.144 | +0.034 | 1.09 | 64 % | 0.140 |
| S2 | 84 | 0.821 | 0.944 | 0.120 | 0.195 | +0.038 | 1.12 | 63 % | 0.159 |

### 11.3 The direction of the errors, stated explicitly (b)

**The model OVER-PREDICTS the delay an action imposes on others.** Over the 406 FIT trials it
over-predicts in 279, that is **68.7 %**, with a median signed error of **+0.0894 s**. Of the 148
trials that FAIL criterion (i), **115 (77.7 %) are over-predictions and 33 (22.3 %) are
under-predictions**. Every per-load median signed error is positive, and four of the six
per-action medians are.

There is exactly one systematic UNDER-prediction and it is a different mechanism: **hostreload**,
median ratio 0.21, predicted p50 0.005 s against a measured 0.049 s. The engine model has no term
for an external KV transfer at all, so a host reload's recorded external cache hits are treated as
free while StudyENG1 Part D measured the reload as +0.067 s over GPU-resident plus 2.93 GB moved
in about 80 ms. Adding such a term is a NEW TERM and therefore a model change, so it was not made.
Its absolute size is small and sits inside the repeat noise for those cells, but the direction is
unambiguous and should not be hidden inside a pooled over-prediction.

### 11.4 Which actions and loads drive the failure (c)

Failures of criterion (i) across the 406 FIT trials, by action and by load:

| action | failures | share of the 148 | load | failures | share of the 148 |
|---|---|---|---|---|---|
| mono11k | 33 | 22.3 % | S4 | 46 | 31.1 % |
| burst4 | 32 | 21.6 % | P40 | 43 | 29.1 % |
| piece1024 | 26 | 17.6 % | W25 | 23 | 15.5 % |
| hostreload | 24 | 16.2 % | P25 | 21 | 14.2 % |
| append5 | 21 | 14.2 % | S2 | 15 | 10.1 % |
| piece2048 | 12 | 8.1 % | | | |

Counting failures alone is not an attribution, because an action can fail where the measurement
also fails itself. Comparing each cut against **its own** noise ceiling separates the two:

**Driven by a real model error (model well below its own ceiling):**

* **mono11k is the clearest case in the study.** Its noise ceiling on FIT data is **1.000**: the
  measurement agrees with itself on every one of its repeats. The model passes **0.529**, a
  47.1-point shortfall, over-predicting in **97 %** of trials by a median **+10.13 s** (ratio
  1.48). There is no threshold argument available here. The mechanism is diagnosis A of section
  4.4: the step model over-predicts the request's own 2.7-second block by 1.09x, and because the
  action blocks every arrival behind it, that 9 % becomes 48 % once summed over the 12 to 45
  arrivals that queue.
* **burst4**, ceiling 0.867 against a model 0.543, a 32.4-point shortfall, over-predicting in
  83 % of trials at a median ratio of 1.66. Mechanism: diagnosis C, the step model's linear
  per-image and per-prefill-request terms do not reproduce the full sub-linear batching gain
  StudyENG1 measured at larger k (0.510 for N=1 at k = 16), so four co-arriving small prefills
  are still charged too much even after they are correctly batched into shared steps.
* **S4 and P40 are the loads that drive it**, together 60.2 % of all failures, and both are the
  loads where the queue behind a blocking action is longest, so both amplify the two mechanisms
  above. S4's median signed error is +0.321 s at a ratio of 1.54.

**Not driven by a model error (model at or near its ceiling):**

* **append5**: model 0.700 against a ceiling of **0.667**. The model is at, indeed slightly above,
  what the measurement supports; this cell cannot be improved by a better model.
* **piece1024** (0.629 against 0.800) and **piece2048** (0.829 against 0.867) are within 17 and 4
  points of their ceilings, with median ratios of 1.00 and 1.16. These are close to as good as
  this data can show.
* **P40 as a load** has the lowest ceiling in the study, **0.611**: at 40 % Poisson load the
  measurement disagrees with itself on 39 % of trials. Its 43 failures are therefore mostly bar
  and noise rather than model, which is why the per-ACTION attribution above is the reliable one
  and the per-load counts alone are not.

**Summary of (c).** Criterion (i)'s failure is driven by **over-prediction of the imposed delay of
the monolithic cold reconstruction (mono11k) and of the small-prefill burst (burst4), amplified by
the heaviest loads (S4, P40)**. The piece actions and the warm append are at or near their noise
ceilings and contribute little. The single systematic under-prediction, hostreload, is a missing
host-KV-transfer term. All three are model gaps with named mechanisms and all three would require
a model change to close, which this row did not make.

### 11.5 Criteria (ii), (iii) and (iv) as registered, plus the secondary (d)

| criterion | registered result | verdict | secondary or variant |
|---|---|---|---|
| ii, ranking | 61 of 63 included pairs = **0.9683** | **PASS** | SECONDARY under the corrected compared-request definition: 59 of 61 = **0.9672**, **PASS** (section 10.1). Both miss the same two near-noise append5-versus-hostreload pairs |
| iii, job completion time | median absolute relative error **0.1669** over 174 | **PASS** | none; the action's own completion time does not depend on the compared set, and FIT gives 0.1643 |
| iv, ENG1b prefix loss | **828 of 852 = 0.9718** class accuracy, MAE of fraction lost **0.0247** | **PASS** | the PRE-REGISTERED pressure variable (version (i), allocation before issue) gives 0.8627 and FAILS; StudyENG1b had already labelled it an invalid proxy. Split out: 787 of 792 = 0.9937 on non-W25, 41 of 60 = 0.6833 on W25 |

---

## 12. T0b, pre-registered now

Pre-registered on the user's ruling of 2026-11-16, **before any further analysis of T0 and before
any data for it exists**. The row text was frozen to a timestamped scratchpad file at
2026-11-16T23:19:27Z (md5 `011e34fafac89c525e3e71be9047bd1a`) and appended VERBATIM to
`research/EXPERIMENTS.md` as the row **StudyT0b-fidelity** after re-reading that file immediately
beforehand, which mattered: the concurrent StudyCTRL1c session had added a row in the interval,
and the insertion was append-only so it could not disturb it. **T0b is NOT YET RUN.**

**Criterion (i-b), delay imposed on others, repeatability-scaled.** Passes if the fraction of
trials where prediction and measurement agree (within 1.5x or 0.1 s absolute) is at least 0.9
times the fraction where two independent repeats of the same trial agree under the same tolerance,
computed on the same conditions.

**Criteria (ii), (iii) and (iv): unchanged from T0.** Ranking at 90 % of action pairs differing by
more than 2x; job completion time at a median absolute relative error of at most 20 %; ENG1b
prefix-loss class correct for at least 90 % of trials with the MAE of the fraction lost also
reported.

**Why (i-b) is the right instrument.** It makes the denominator the measurement's own agreement
with itself, so a bar set above the measurement's repeatability can no longer absorb the verdict
and a real model gap can no longer hide behind one. On T0's data the two quantities were **82.76 %
and 58.6 %** (the ceiling corrected per the erratum in section 0A; this rationale originally cited
83.9 %, and the criterion itself is a ratio that does not contain either number, so the
pre-registered wording is unchanged); (i-b) asks for the second to reach 0.9 of the first, on the
same conditions, which is a question about the MODEL and not about the threshold.

**BINDING CONSTRAINT, recorded on the row: T0b must be evaluated on FRESH held-out data only. The
174 StudyENG1 Part C HOLDOUT triples are SPENT and must not be used to evaluate T0b or any revised
model.** They were consumed by the single authorized one-shot run at 2026-11-16T22:57:57Z, and any
residual computed on them now informs model decisions, which makes every later comparison on them
in-sample. The same applies to the 406 Part C FIT trials, which have now been used for two
implementation fixes and for the attribution in section 11. **This report therefore does NOT score
(i-b) on the holdout, and the ratio of T0's two reported numbers must not be read as a T0b
result**: T0b has no result, and it will have one only on fresh data.

**(i-b) additionally requires per-trial independent repeats in the fresh collection**, because its
denominator is the measurement's agreement with itself under the same tolerance on the same
conditions. A collection without repeats cannot score (i-b), and the row says T0b must not be run
against one.

**Data source: TBD, a new H100 collection, deliberately not chosen here.** Its design, cells, n,
repeat count and held-out split must be pre-registered in their own row before any run, with the
split fixed before the first request.

**What T0b scores, and what may not change silently.** T0b scores the SAME cost model this row
froze (step model `7da0a984bca4ba4f0ff81d5cee54d18c`, `eng1_engine.py`
`d390037af3d48abdc3f91572fe6e8ccd`). If the model is revised first, the revision is a
methodological change needing its own row, and T0b then tests the revision, which must be stated
in its verdict. The bias T0b is expected to be sensitive to is recorded now so it cannot be
discovered afterwards: the imposed delay of a monolithic cold reconstruction is over-predicted by
1.3 to 2.15x, and section 11 localizes the gap to mono11k and burst4 under the heaviest loads.

---

## 13. Files

| file | what |
|---|---|
| `experiments/orchestration/policy/eng1_engine.py` | NEW. StudyENG1's step model, front end, admission stall and scheduling structure, as the `EngineModel` protocol and a step-level simulator |
| `experiments/orchestration/policy/trace_replay.py` | NEW. Reconstruction of each Part C trial and each ENG1b trial from the committed logs, and the paired prediction |
| `experiments/orchestration/policy/run_t0.py` | NEW. The driver, the pre-registered criteria, the noise ceiling and the negative control |
| `experiments/orchestration/policy/t0_harness.py` | the one-shot holdout mode, `FrozenState`, the freeze verification and the log |
| `experiments/orchestration/policy/tests/test_t0_fidelity.py` | NEW. 24 tests: solo cross-checks, no hard-coded coefficient, the scheduling structure, the compared-set definition, two secondary-re-score guard tests, and five fence tests |
| `results/orchestration/study_t0/t0_dryrun_partc_fit.json` | the dry run on 406 FIT trials, after both implementation fixes |
| `results/orchestration/study_t0/t0_negative_control.json` | mechanism verification Step 4 |
| `results/orchestration/study_t0/t0_freeze.json` | the frozen git hash and file md5s |
| `results/orchestration/study_t0/t0_one_shot.log` | the one line the authorized run wrote |
| `results/orchestration/study_t0/t0_holdout_partc.json` | the ONE holdout run, 174 triples |
| `results/orchestration/study_t0/t0_eng1b_prefix_loss.json` | the 852 ENG1b trials, version (ii) |
| `results/orchestration/study_t0/t0_holdout_secondary_criterion_ii.json` | the SECONDARY criterion (ii) re-score of section 10.1, with the bit-equality check against the registered file |
