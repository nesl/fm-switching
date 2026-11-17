# StudyPOL4-engine: fixing the three engine-model gaps that made StudyT0's criterion (i) fail

Pre-registered in `research/EXPERIMENTS.md` (row StudyPOL4-engine). Design log D60, Part 1.
CPU only on flash: no GPU, no model server, no inference. Every live measurement used here was
taken on h100nvl GPU 2 by StudyENG1-steptime and StudyENG1b-prefix-survival and is only READ.
This row is an explicit METHODOLOGICAL CHANGE to the cost model StudyT0-fidelity froze, declared
as such under that row's dependency clause.

**Pre-registration order.** CLAUDE.md requires the registry row before any computation and the
brief forbids editing `research/EXPERIMENTS.md` until the end of the session, because other
sessions append rows concurrently. The full 13-field row text was therefore frozen to a
timestamped scratchpad file at **2026-11-17T03:48:24Z** (md5 `795e7b253ab478c7a619af167d8fdcbc`)
**before anything was fitted or scored**, and inserted verbatim at the end after re-reading the
registry immediately beforehand. The three result cells the frozen text itself marks
`TO BE FILLED` (verdict, consistency_check, mechanism_verification) were filled at that point;
every design and criterion cell is byte-identical to the frozen text. Mechanism verification
Steps 1 to 5 were likewise frozen, at **2026-11-17T04:03:43Z** (md5
`73bb4a55524dc071bd521ad8bc106924`), after the fit and the term ablation and **before** the
406-trial re-score sweep.

**The HOLDOUT is spent and was not touched.** `eng1_holdout_split.json` is loaded only to
EXCLUDE. The exclusion is asserted in code (`run_pol4.split_fit_trials`), three ways: no scored
trial's `(load, action, trial)` appears in the split file; the number excluded equals the split
file's size; every triple in the split file is present in the record and excluded. The audit
block written into every output file reads `n_part_c_trials 580, n_fit_scored 406,
n_holdout_excluded 174, n_holdout_in_split_file 174, holdout_trials_used 0`. Two tests assert it,
including one that fakes a leak and requires the assertion to fire.

---

## 1. Headline

| | criterion on the 406 Part C FIT trials | old model `eng1` | new model `pol4` | ablation `pol4_nobatch` |
|---|---|---|---|---|
| i | delay imposed on others, within 1.5x or 0.1 s | 0.6355 (258/406) FAIL | **0.6305 (256/406) FAIL** | 0.6650 (270/406) FAIL |
| ii | ranking, action pairs differing by more than 2x | 0.9667 (58/60) PASS | **0.9833 (59/60) PASS** | 0.9500 (57/60) PASS |
| iii | job completion time, median absolute relative error | 0.1643 PASS | **0.1338 PASS** | 0.1233 PASS |
| iv | ENG1b prefix loss, class accuracy (852 trials) | 0.9718 PASS | **0.9718 PASS** | 0.9718 PASS |

**EVERY NUMBER IN THIS TABLE IS IN-SAMPLE FOR THE CHOICE OF TERMS AND NONE OF IT IS A TEST OF THE
REVISED MODEL.** No coefficient of any new term saw a Part C trial: all three were fitted on
StudyENG1 Parts A, B and D and on StudyENG1b. But these 406 FIT trials produced the attribution
in `reports/study_t0_fidelity.md` section 11 that decided WHICH three terms to add, and they
already carried two implementation fixes. The label is repeated at every site below, in every
output JSON, and in the registry row. StudyT0b on fresh data is the only test.

**What moved, and what did not.**

* Criterion (i) did **not** improve: 0.6355 to 0.6305, two trials worse. The gain on the
  monolithic action (+13 trials) is cancelled by losses on the three cells term (c) touches.
* Criterion (ii) improved and (iii) improved by 3.0 points of median relative error; (iv) is
  untouched by construction (it is a KV-pool prediction, not a step-time one).
* **The brief's decisive STOP AND ASK did not trigger for the frozen model**: none of (ii), (iii)
  or (iv) got worse under `pol4`. It DID trigger for the `pol4_nobatch` ablation, which scores
  (i) highest but drops (ii) below the old model (0.9500 against 0.9667). That is the trade the
  brief forbids, so `pol4_nobatch` is NOT frozen and is kept only as D60's term-(c) ablation.
* Per action, the picture is sharp and is in section 4: mono11k 0.529 to 0.714 against a noise
  ceiling of 1.000, hostreload's completion error 0.394 to 0.141, and burst4 0.543 to 0.400.

---

## 2. The three terms

All three are read from `results/orchestration/study_pol4/pol4_terms.json`, fitted by
`policy/fit_pol4_terms.py`. Nothing is typed into `policy/eng1_engine.py`: StudyT0-fidelity's
contract test is EXTENDED to the new coefficients rather than deleted, and a second test refuses a
terms file that does not state `holdout_trials_used: 0` or that is missing a coefficient. Setting
all three to their neutral values (no external tokens, scale 1.0, exponent 0.0) recovers
StudyT0-fidelity's model exactly, which a test asserts to 12 decimal places on a three-request
fixture.

### 2.1 Term (a), host-KV transfer: the gap was total, and the counters pin it

StudyT0-fidelity section 11.3: "The engine model has no term for an external KV transfer at all",
median predicted/measured ratio 0.21 on hostreload.

**The preferred source was available and was used: the per-interval engine counters, fitted
per request.** The question of whether `kv_offload_load_bytes_total` and
`kv_offload_load_time_total` can be read PER REQUEST is settled from the record, not assumed.
StudyENG1 records each Part D query's Prometheus deltas over that query's own
[submit, completion] window, and its pre-registered H-tier verdict is that attribution is
unambiguous at concurrency 1 and degrades at concurrency 4. Reproduced directly on the LOAD
counters:

| cell | n | rows with non-zero load counters | rate GB/s (p50, min, max) | distinct bytes per token |
|---|---|---|---|---|
| conc 1, host | 30 | **30** | 50.14, 36.59, 54.82 | **1 value: 262,144** |
| conc 1, gpu | 30 | **0** | n/a | n/a |
| conc 1, cold | 30 | **0** | n/a | n/a |
| conc 4, host | 36 | 36 | 52.30, 45.55, 56.41 | **14 values, up to 1,050,495** |
| conc 4, gpu | 44 | **15** (contaminated) | 46.24, 45.19, 56.96 | 7 values |
| conc 4, cold | 40 | **28** (contaminated) | 53.60, 45.55, 56.41 | n/a |

At concurrency 1 the counters fire in every host row, in no gpu row and in no cold row, and the
bytes per token are a single exact value. That is per-request attribution. At concurrency 4 they
fire in gpu and cold rows too and the bytes per token roughly double and quadruple in the host
rows, which is the same window contamination StudyENG1 measured (100 % to 40 % accuracy). **The
fit therefore uses the 30 concurrency-1 host rows and nothing else.**

| coefficient | value | source |
|---|---|---|
| `host_kv_bytes_per_token` | **262,144 B** (exactly 256 KiB) | ENG1 Part D conc-1 host rows, `kv_offload_load_bytes_total / cached_tokens`: a single distinct value in all 30, and in all 56 Part C FIT hostreload rows too |
| `host_kv_transfer_gb_per_s` | **50.1377** | same rows, median of per-row `load_bytes / load_time` (n = 30, 36.59 to 54.82) |
| `host_kv_lookup_fixed_ms` | **0.8845** | same rows, median `kv_offload_lookup_sync_delay_seconds_sum / count` |

so `host_reload_ms(ext) = 0.8845 + 1000 x 262,144 x ext / (50.1377e9)`, which is **59.36 ms at
11,184 tokens**. It is charged to the step in which the reloading request's prefill begins, so it
is paid by that request AND, through step occupancy, by every request sharing or queued behind
that step. A fixed per-reload term beyond the measured lookup delay is NOT identifiable here and
that is stated rather than invented: every Part D host query moves about 10.9k tokens, so an
intercept and a slope cannot be separated. The linearity in tokens rests on the measured bytes
per token being a single constant.

**Cross-checks, reported as checks and folded into nothing.**

| cross-check | tokens | measured | the fitted term predicts | ratio | reading |
|---|---|---|---|---|---|
| ENG1 Part D TTFT delta, conc 1 (host 0.1671 s minus gpu 0.1001 s) | 10,968 | 0.06704 s | 0.05823 s | **0.869** | the term accounts for 86.9 % of the TTFT delta; the rest is the query's own scheduling, which the simulator models separately |
| ENG1 Part C **FIT** hostreload counters (out of sample for the fit) | 10,928 | 0.05457 s | 0.05802 s | **1.063** | 53.22 GB/s measured against 50.14 fitted; the 24 HOLDOUT rows were skipped and counted |
| StudyENG1b reload minus resident resume (n 45 / 117) | 10,384 | 0.13313 s | 0.05518 s | **0.414** | see below |
| ENG1 section 2.3 smoke note, 2.93 GB in about 80 ms | 11,184 | 36.63 GB/s implied | 50.14 GB/s fitted | **1.369** | not a disagreement: 36.59 GB/s is the MINIMUM of the fitted distribution's own 30 rows |

**The two TTFT-based estimates disagree by 2.10x** (6.11 us/token from Part D against
12.82 us/token from ENG1b) and that is reported rather than averaged. It does **not** trigger the
brief's stop condition, which fires only if the counters are also not attributable per request,
and they are. The disagreement has a named cause: ENG1b's resume prefills 23 frames of its own
behind a 4.2 MB body while Part D's query is a 0.02 MB question with no new frames, so the ENG1b
delta contains the interaction between the transfer and the resume's own work. That interaction is
exactly what the simulator represents as separate step occupancy, so putting it inside the
coefficient would double-count it. StudyENG1b's committed per-trial record carries no
`kv_offload` counters, so it cannot be fitted the preferred way.

**Physical plausibility.** 50.14 GB/s is below PCIe Gen5 x16's about 63 GB/s; the full fitted
range 36.59 to 54.82 GB/s spans StudyENG1's own flagged 36 to 44 GB/s single-transfer band and
StudyENG1b's TTFT-derived about 22 GB/s is slower still because it divides bytes by a TTFT delta
rather than by a transfer time. Nothing here is faster than a committed curve by the 2x CLAUDE.md
flags; the one ratio above 2x is the ENG1b TTFT estimate and it is explained above.

**The STORE side is measured and deliberately NOT charged.** The connector writes every built
block through to host, at a measured 41.47 GB/s (37.70 to 43.55, n = 172 Part C hostreload run
summaries). In the Part C design that write-through happens during the setup build, and every
setup request finishes before its trace starts, which `trace_replay.setup_overlap_report` checks
per trial and which held for all 406 FIT trials. The store is therefore outside the measured
window in BOTH arms and cannot enter the paired difference. It is recorded as a KNOWN OMISSION
with a committed rate, so a future scenario whose store lands inside the window has a number to
use. `kv_offload_cpu_cache_usage_perc` is a gauge and is absent from the counter deltas (0 of 30
rows), so it contributes no coefficient.

**How a request's external tokens are known.** RECORDED, not inferred, and attributed only where
the record permits. Each Part C run summary carries
`prompt_tokens_by_source|external_kv_transfer` for the whole run, so it is attributed to the
action only when BOTH (1) the arm's counter equals the arm's action rows' cached tokens within
StudyENG1's 32-token chaining tolerance and (2) the OTHER arm's counter is zero. On the committed
record that selects the hostreload cells and nothing else: 56 of 56 FIT hostreload with-arms
attributed, 0 of the other 350 FIT with-arms, and **130 W25 arm counters left UNATTRIBUTED and
charged nothing**, because there the counter is the 8 warm sessions' own host hits (19k to 50k
tokens, present in both arms and present even where the action has no cached tokens at all). Those
reloads are real engine work the model does not charge; they occur in both arms of a W25 pair, so
they largely cancel in the paired difference, and that is a declared limitation, not a silent one.
Two tests assert the attribution counts.

### 2.2 Term (b), the monolithic cold prefill's own block

StudyT0-fidelity section 11.4 diagnosis A: the own 2.7-second block is over-predicted by 1.09x
and the queue turns that into a median +10.13 s (ratio 1.48).

`long_prefill_scale(L) = 0.789119 + 0.009228 x L/1000` multiplies the step's PREFILL cost (the
step as scheduled minus the same step with no prefill work, so decode-only steps and the step
model's admission terms are untouched) for a request whose total new tokens L exceed one
8,192-token step. By StudyENG1's H-admit verdict (a) such a request holds the single
partial-prefill slot, so those steps carry no other prefill and the step-level form is exactly the
own-block form.

Fitted on **StudyENG1 Part A (A2 `piece` rows with j = 0, A2mono `mono` rows) and Part B
`solo_long` rows**, cell medians, restricted to new tokens above 8,192: **17 cells, 230
requests**. Per cell the scale that makes the simulator's solo TTFT equal the measured median is
solved exactly (the prefill part is linear in the scale), then least squares over the cells:
R^2 **0.8455**, median absolute residual **0.0090**. The required scale rises monotonically with
size, from 0.823 to 0.968 at about 8.2k tokens through 0.875 to 0.906 at 11 to 13k to 1.022 to
1.081 at 26 to 30k, which is why a size-dependent scale and not a single factor is fitted; a
single pooled factor would have made the 26k cells worse. `scale(11,127) = 0.8910`.

**It hits its target.** The solo monolithic 11k cross-check, on StudyT0's exact inputs, moves from
2.9212 s (ratio 1.093 of the measured 2.673 s, reproducing T0's committed 2.921) to **2.6605 s,
ratio 0.995**. The 2,048-token piece and the N=1 episodic cross-checks are untouched (0.5963 and
0.1077), as the term's definition requires.

**And it does not close the mono11k imposed-delay gap, which was predicted in advance.** Step 5 of
the frozen mechanism verification recorded, before the sweep, that a 10.9 % reduction of the block
reduces the predicted imposed delay by only 14.1 % at P40 because the queue amplification is
roughly quadratic, while the measured gap at that cell is 45 %. Observed: mono11k's median ratio
falls from 1.481 to 1.268 and its median signed error from +10.13 s to +5.76 s, a real and large
improvement, but it remains over-predicted in 86 % of trials. **StudyT0's diagnosis A is therefore
correct in mechanism and insufficient in magnitude: the own-block error is about a third of the
mono11k imposed-delay error.** The remainder points at the scheduling alternative named in Step 5
(the model treats the whole block as head-of-line blocking for every arrival, as StudyENG1
measured on an UNLOADED server at rho 0.97 to 1.00; the loaded-arrival regime has no committed
measurement). **No term was added for it. That is a STOP AND ASK condition of the brief, reported
rather than papered over**: closing it would need a coefficient with no measurement behind it.

### 2.3 Term (c), sub-linear batching: the diagnosis it was added for is not supported

StudyT0-fidelity section 11.4 diagnosis C: the step model's "linear per-image and per-prefill-
request terms do not reproduce the full sub-linear batching gain StudyENG1 measured at larger k".

**The published anchors reproduce exactly from the Part A rows**, as the brief required rather
than taking them on trust. Recomputed from the 1,860 A1 rows as the batch's last first token,
median over 30 batches: `t(16) / (16 x t(1))` = **0.50977** at N = 1 and **0.73058** at N = 3,
against the published 0.510 and 0.731. The reproduction matches.

**But the old model already reproduced them.** Its implied ratios are 0.48905 and 0.73292, i.e.
within **4.0 %** and **0.3 %** of the measurement, and across all eight A1 batching cells its
predicted ratio is 0.897 to 1.043 times the measured one with no systematic shortfall. What the
old model does get wrong on A1 is a **k-INDEPENDENT** under-prediction of the base: the
predicted/measured ratio is 0.804 at k = 1, 0.838 at k = 2 and 0.771 at k = 16. A term on
MULTI-prefill steps cannot represent a k = 1 error, so the term is fitted on the batching RATIO,
which divides that base error out. Fitting the absolute batch completion time instead gives
exponent -0.19, which would make the N = 1 k = 16 ratio 0.688 against a measured 0.510, a 35 %
error on the very statistic StudyENG1 published; that objective is scanned, reported and not used.

`batch_prefill_gain(m) = m ** (-(-0.030)) = m ** 0.030` for m > 1 prefills sharing a step, 1.0 at
m = 1. Fitted on **StudyENG1 Part A A1, 10 cells, 300 batches**; the window within 10 % of the
fit's minimum is **-0.040 to -0.015**, which excludes zero, so the data do prefer a small
batching PENALTY to neutrality, but **the sign is the opposite of the diagnosis the term was added
for.** Over the sweep the gain spans 1.021 at m = 2 to 1.096 at m = 21 on 2,055 of 28,969 steps.

**Checked against Part C FIT burst4, as the brief required: the check fails.** burst4's criterion
(i) pass rate falls from 0.543 to 0.400 and its median ratio rises from 1.529 to 1.660; append5
and piece2048 also move slightly the wrong way. Switching the term off (`pol4_nobatch`) restores
all three cells exactly to the old model and lifts criterion (i) to 0.6650, but drops criterion
(ii) to 0.9500, below the old model, which is the regression the brief stops on. **So burst4's
over-prediction is not a missing batching gain**, and term (c) is kept at its fitted value because
hand-setting it to zero after seeing the Part C result would be tuning on FIT data and would
itself trip the regression gate.

---

## 3. Mechanism verification (CLAUDE.md Steps 1 to 5)

Recorded in full, **before the re-score sweep**, in the frozen scratchpad file of
2026-11-17T04:03:43Z (md5 `73bb4a55524dc071bd521ad8bc106924`). Summary:

**Step 1.** The chain: a cost that is real engine work but is charged to no step cannot reach
other requests, so the model under-predicts (term (a)); a cost charged at the wrong magnitude is
amplified by every arrival queued behind the step (term (b)); and if several short prefills share
a step the step model's per-step aggregates must reproduce the measured batching behaviour (term
(c)). Each link is traced to StudyENG1 sections 5, 6, 7 and 8 and to FORMULATION.md Constraints 2.

**Step 2.** Five links instantiated, **none ABSENT and none CONSTANT**: the host charge is 57.52
to 59.44 ms over 10,832 to 11,200 external tokens on exactly 56 steps and zero elsewhere; the
attribution is 56 of 56 hostreload with-arms and 0 of 350 others with 130 W25 counters identified
as unattributable; the long-prefill scale is 0.88995 to 0.89543 over L = 10,927 to 11,521 on 140
steps and 1.0 everywhere else; the batching gain spans 1.021 to 1.096 on 2,055 steps with m
running 1 to 21. One link was recorded as **CONTRARY to the claim that motivated it** before any
Part C result was seen: term (c)'s fitted sign is a penalty and the old model already reproduced
the published anchors, so diagnosis C's mechanism is not present in the measurement and no burst4
improvement may be attributed to it.

**Step 3.** One traced unit in full arithmetic, Part C FIT trial `P25|hostreload|2`: every input
(11,098 prompt tokens, 11,008 cached of which 11,008 recorded external, 90 new tokens, 1 image,
0.0200 MB, 2 output tokens), the term (a) charge computed by hand to 58.4396 ms, the statement
that terms (b) and (c) are both exactly 1.0 for this unit and why, the one step the action
occupies before and after (49.221 ms to 107.660 ms), the action's own predicted TTFT (0.09282 s to
0.15126 s), the predicted imposed delay over the 44 matched episodic requests (0.00576 s to
0.03550 s) against the measured 0.02273 s, the six largest per-request deltas in each, **what
bound it** (the engine step; the KV pool held one about 11k prefix in a 62,944-token pool and did
not bind), and the per-unit outcome.

**Step 4, negative control.** One documented cell, load P40, FIT trials only; each term switched
to its neutral value one at a time. Output
`results/orchestration/study_pol4/pol4_term_ablation.json`.

| action | measured p50 | eng1 | pol4 | host term off | long term off | batch term off |
|---|---|---|---|---|---|---|
| hostreload | 0.1882 | 0.0085 | 0.1422 | 0.0318 | 0.1422 | 0.0339 |
| mono11k | 32.9236 | 59.9372 | 51.4892 | 51.4892 | 65.4434 | 44.8987 |
| burst4 | 0.3297 | 0.4881 | 0.4808 | 0.4808 | 0.4808 | 0.4881 |
| piece2048 | 0.9072 | 1.1322 | 1.1814 | 1.1814 | 1.1814 | 1.1322 |

The controls pass: disabling the host term removes 82.6 % of the hostreload cell's change and
nothing in the other three; disabling the long-prefill term removes the whole of the mono11k
change and moves no other cell; disabling the batching term restores piece2048 and burst4 exactly
to the old model. Each cell's change is attributable to the term whose measurement it rests on,
and the result does change when each mechanism is removed.

**Step 5.** Three alternatives named, with what distinguishes each: for (a), that the reload is
free to the engine and hostreload's delay is noise, excluded by the engine's own 57 ms transfer
counter which lives outside Part C; for (b), that the mono11k gap is a scheduling error and not an
own-block magnitude error, which the quadratic-amplification arithmetic above supports and which
is why the residue is left open; for (c), that the measured batching behaviour is already
reproduced and the A1 residual is a k-independent base error, which the per-k ratios establish.

**Rule 2 classification.** The three terms are **present, non-zero and varying** (Step 2) and each
one changes the result when disabled (Step 4). Criterion (i)'s failure to improve on FIT data is
therefore **a real negative for the fix as a whole on FIT data, not an inconclusive from an absent
mechanism**: there is no ABSENT or CONSTANT link. It is also **not a settled finding about the
revised model**, because the FIT trials are not a held-out sample for it. Per term: (a) is a real
positive (the gap was total and is now 83 % closed on its own cell); (b) is a real partial
positive with its shortfall quantified and its residual mechanism named and left unmodelled for
want of a measurement; (c) is a **real negative against diagnosis C**, since the mechanism it
claimed is measurably absent from StudyENG1 Part A.

---

## 4. The four criteria per action and per load, old versus new

**IN-SAMPLE FOR THE CHOICE OF TERMS, on FIT trials (see section 1).** `noise` is criterion (i)
applied to two independent measurements of the same trial, per cut: the ceiling. `med_signed` is
median(predicted minus measured), so positive is OVER-prediction. `med_ratio` is
median(|predicted| / |measured|), which is StudyT0-fidelity section 11's column and the only
ratio defined when a per-trial sum changes sign; the signed version is also published in the JSON.

### 4.1 Per action

| action | n | noise ceiling | pass (i) eng1 | pass (i) pol4 | med_signed eng1 | med_signed pol4 | med_ratio eng1 | med_ratio pol4 | % over eng1 | % over pol4 | completion ARE eng1 | completion ARE pol4 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| mono11k | 70 | **1.000** | 0.529 | **0.714** | +10.134 | **+5.755** | 1.481 | **1.268** | 97 % | 86 % | 0.157 | **0.085** |
| hostreload | 56 | 0.750 | 0.571 | 0.536 | -0.008 | +0.031 | **0.211** | **0.596** | 48 % | 61 % | 0.394 | **0.141** |
| piece2048 | 70 | 0.867 | 0.829 | 0.800 | +0.146 | +0.163 | 1.155 | 1.218 | 74 % | 79 % | 0.081 | 0.081 |
| piece1024 | 70 | 0.800 | 0.629 | 0.629 | +0.015 | +0.020 | 0.954 | 0.935 | 56 % | 59 % | 0.117 | 0.117 |
| append5 | 70 | 0.667 | 0.700 | 0.686 | -0.000 | +0.009 | 0.829 | 0.872 | 50 % | 54 % | 0.180 | 0.180 |
| burst4 | 70 | 0.867 | 0.543 | **0.400** | +0.131 | +0.158 | 1.529 | 1.660 | 83 % | 87 % | 0.275 | 0.316 |

Medians of the quantity itself (s): mono11k measured 22.215, predicted 31.178 to **26.722**;
hostreload measured 0.0491, predicted 0.0055 to **0.0378**; piece2048 0.7399, 0.8721 to 0.8798;
piece1024 0.2217, 0.2220 to 0.2250; append5 0.0787, 0.0960 to 0.0977; burst4 0.2187, 0.2855 to
0.3104.

Read against the ceilings: the two cells StudyT0 attributed the failure to behave as the terms
predict and no better. **mono11k**, the one cell where the measurement is perfectly repeatable
(ceiling 1.000), closes 18.5 points of a 47.1-point shortfall. **hostreload** closes the
under-prediction almost entirely in ratio (0.211 to 0.596) and cuts its completion error by 2.8x
(0.394 to 0.141), yet its criterion (i) pass rate falls 3.5 points, because its measured values
sit inside StudyENG1's own repeat noise: the old model passed many of those trials by predicting
nearly zero and landing inside the 0.1 s absolute window, and a term that is right in magnitude
can lose such a trial. That is a property of the criterion on near-noise cells, stated and not
argued away. **burst4** is the term (c) regression of section 2.3.

### 4.2 Per load

| load | n | noise ceiling | pass (i) eng1 | pass (i) pol4 | pass (i) pol4_nobatch | measured p50 | eng1 p50 | pol4 p50 |
|---|---|---|---|---|---|---|---|---|
| P25 | 84 | 0.889 | 0.750 | 0.762 | 0.786 | 0.1676 | 0.1440 | 0.1806 |
| P40 | 84 | 0.611 | 0.488 | 0.488 | 0.560 | 0.3922 | 0.4064 | 0.4591 |
| S2 | 84 | 0.944 | 0.821 | 0.821 | 0.869 | 0.1202 | 0.1949 | 0.2091 |
| S4 | 84 | 0.833 | 0.452 | 0.417 | 0.440 | 0.6003 | 0.9978 | 1.0595 |
| W25 | 70 | 0.867 | 0.671 | 0.671 | 0.671 | 0.2221 | 0.2676 | 0.2634 |

### 4.3 The direction of the errors

**The model still OVER-predicts, and slightly more than before.** Over the 406 FIT trials the old
model over-predicts in 279 (68.7 %) with a median signed error of +0.0894 s; the new model in 289
(71.2 %) at +0.1062 s. Of the 148 old failures 115 (77.7 %) were over-predictions; of the 150 new
failures 123 (82.0 %) are. The direction is unchanged: the one systematic UNDER-prediction the old
model had, hostreload at ratio 0.211, is the one the new model corrects, and correcting it moves
that cell from under to slightly over (0.596 of the way, i.e. still under in ratio but over in 61 %
of trials). Every per-load median signed error remains positive.

---

## 5. What the fix does to the piece-versus-monolithic preference

For each of the five Part C FIT conditions, the predicted ordering of the three reconstruction
actions by imposed delay, cheapest first, under both models. **IN-SAMPLE FOR THE CHOICE OF TERMS.**

| load | predicted order, eng1 | predicted order, pol4 | measured order | order changed? |
|---|---|---|---|---|
| P25 | piece1024, piece2048, mono11k | piece1024, piece2048, mono11k | piece1024, piece2048, mono11k | no |
| P40 | piece1024, piece2048, mono11k | piece1024, piece2048, mono11k | piece1024, piece2048, mono11k | no |
| S2 | piece1024, piece2048, mono11k | piece1024, piece2048, mono11k | piece1024, piece2048, mono11k | no |
| S4 | piece1024, piece2048, mono11k | piece1024, piece2048, mono11k | piece1024, piece2048, mono11k | no |
| W25 | piece1024, piece2048, mono11k | piece1024, piece2048, mono11k | piece1024, piece2048, mono11k | no |

**The ORDER does not change in any condition, and both models already matched the measured order
in all five.** What changes is the STRENGTH of the preference, which is what a scheduler trades
against utility. The predicted cost of a monolithic reconstruction relative to a 2,048-token
piece:

| load | eng1 | pol4 | measured | pol4 moves toward the measurement? |
|---|---|---|---|---|
| P25 | 48.6x | **42.1x** | 33.2x | yes |
| P40 | 52.9x | **43.6x** | 36.3x | yes |
| S2 | 42.6x | **34.2x** | 30.9x | yes |
| S4 | 43.5x | **40.2x** | 27.8x | yes |
| W25 | 42.7x | **32.4x** | 38.3x | yes, past it (32.4 against 38.3) |

In absolute terms the predicted mono11k median falls by 13.4 % at P25, 14.1 % at P40, 15.6 % at
S2, 1.1 % at S4 and 15.2 % at W25, while the two piece actions move by at most 7 %. So the
revised model still prefers pieces to a monolithic reconstruction everywhere, but by 7 to 24 %
less, and in four of five conditions that is a move toward the measurement. The practical
consequence for the policy is that a monolithic reconstruction is priced less punitively and a
marginal case that the old model would have refused may now be admitted; nothing in this row tests
whether that is the right call, which is StudyT0b's and D60's business.

---

## 6. Results consistency check (CLAUDE.md, six checks)

### 1. Cross-check against committed measurements

| quantity | this run | prior run | source of prior | ratio | agree |
|---|---|---|---|---|---|
| criterion (i) on 406 FIT, OLD model | 0.635468 | 0.6354679 | `results/orchestration/study_t0/t0_dryrun_partc_fit.json` | 1.0000 | agree |
| criterion (ii) on FIT, OLD | 0.966667 | 0.9666667 | same | 1.0000 | agree |
| criterion (iii) on FIT, OLD | 0.164265 | 0.16426451 | same | 1.0000 | agree |
| criterion (iv), ENG1b class accuracy | 0.971831 | 0.9718310 | `t0_eng1b_prefix_loss.json` | 1.0000 | agree |
| mono11k med_signed, OLD | +10.134 s | +10.134 s | study_t0_fidelity.md section 11.1 | 1.0000 | agree |
| pooled over-prediction share, OLD | 0.6872, +0.0894 s, 115/33 | 0.687, +0.0894 s, 115/33 | section 11.3 | 1.0000 | agree |
| solo monolithic 11k TTFT, OLD | 2.9212 s | 2.921 s | section 2.2 | 1.0000 | agree |
| solo 2,048-piece on 11k, OLD | 0.5963 s | 0.596 s | section 2.2 | 1.0001 | agree |
| solo N=1 episodic, OLD | 0.1077 s | 0.108 s | section 2.2 | 0.9977 | agree |
| criterion (i) noise ceiling, 87 FIT repeats | 0.8276 (72/87) | **0.8276 (72/87)** committed JSON; **0.8391 (73/87)** in T0's headline | `t0_dryrun_partc_fit.json` vs `t0_holdout_partc.json` | 1.0000 / 0.9863 | agree with the committed post-fix value; see note |
| host transfer rate | 50.14 GB/s | 36.63 GB/s implied | ENG1 section 2.3 smoke note | 1.369 | agree, explained |
| host transfer rate | 50.14 GB/s | about 22 GB/s | ENG1b section 7 check 2 | **2.279** | **investigated and explained below** |
| ENG1b reload cost over resident | 0.1331 s | 0.12 s | ENG1b section 5 | 1.109 | agree |
| KV bytes per token | 262,144 B | 2.93 GB / 11,184 tok = 261,899 B | ENG1 section 2.3 | 1.0009 | agree |

**The OLD model reproduces every committed StudyT0-fidelity number to the committed precision**,
which is the strongest available evidence that the flag leaves the frozen path untouched and that
the comparison in this report is apples to apples.

*The one documented disagreement above 2x* is StudyENG1b's about 22 GB/s against the fitted
50.14 GB/s (ratio 2.28). It is not a measurement conflict: ENG1b's figure divides about 2.7 GB by
the 0.12 s TTFT DELTA between a reload resume and a resident resume, which also contains the
resume's own 23-frame prefill and 4.2 MB of front-end work; the fitted figure divides bytes by the
engine's own `kv_offload_load_time`. The two measure different things and the counter-based one is
the quantity the term needs, which is why the brief prefers it. Using ENG1b's number instead would
over-charge the transfer by 2.3x and double-count work the simulator already models.

*The noise-ceiling note.* T0's headline quotes a repeatability ceiling of 83.9 % (73 of 87). Its
own committed dry-run file records 82.76 % (72 of 87) for the same 87 repeats, because the
`COMPARED_KINDS` fix (T0 section 8 check 1) landed between the holdout run and the dry-run
re-score and removes one W25 trial from the passing set. This run reproduces the post-fix 82.76 %
exactly. No verdict of T0 changes; the discrepancy is in T0's committed artifacts, not introduced
here, and it is recorded so the 83.9 % figure is not reused as a post-fix ceiling.

### 2. Physical plausibility

| measurement | implied rate | committed curve | ratio | flag |
|---|---|---|---|---|
| host KV transfer, fitted | 50.14 GB/s (range 36.59 to 54.82) | PCIe Gen5 x16 about 63 GB/s; ENG1 flagged 36 to 44 GB/s | 0.80 of the bus, 1.14 to 1.39 of the flagged band | no flag: the fitted range contains the flagged band and never exceeds the bus |
| host KV store, measured, not charged | 41.47 GB/s (37.70 to 43.55) | same | inside the flagged band | no flag |
| monolithic 11k prefill, NEW model | 3,963 tok/s end to end; 5,029 tok/s engine only | measured 4,163 and 5,356 tok/s on the same request; SLICE1 engine-only 5.3k tok/s | 0.952 / 0.939 | no flag, and the direction is SLOWER than measured, the opposite of a caching artefact |
| monolithic 11k prefill, OLD model | 3,625 / 4,497 tok/s | same | 0.871 / 0.840 | no flag |
| term (a) at 10,384 tokens | 55.18 ms, i.e. 49.3 GB/s equivalent | ENG1b 2.7 GB in 0.12 s | consistent once the resume's own work is removed | no flag |

Every predicted rate in this row is slower than its committed curve. Nothing is faster, so nothing
here can be a caching artefact. **Caching, stated per CLAUDE.md:** no measurement was taken in
this row. The live runs this row reads had vLLM prefix caching ON throughout; each Part C
request's recorded `cached_tokens` is an INPUT, so a piece on a cached prefix is simulated warm and
a monolithic request cold, exactly as recorded, and term (a) is charged only where the record says
the cached tokens came from the host tier. No warm number is compared with a cold one anywhere.

### 3. Distribution sanity

No constant appears where a distribution belongs. The host transfer rate is reported with n, p50,
min and max for every cell of the attributability table and spans 36.59 to 54.82 GB/s over 30 rows.
The 17 long-prefill fit cells each carry n, measured median, min and max, and required scales from
0.823 to 1.081. The 10 A1 cells each carry 30 batches with min and max. Per-load, per-action and
per-cell tables in all four result JSONs carry n, min, p10, p50, p90, max and mean of both measured
and predicted. **Two constants are genuine and are explained**: the bytes per token is exactly
262,144 in all 30 Part D and all 56 Part C FIT rows, which is 256 KiB and a KV block geometry, not
a short circuit (the conc-4 rows show 14 distinct values once windows overlap, which is what a
contaminated counter looks like); and criterion (iv) is bit-identical across all three
configurations because it is a KV-pool prediction that no step-time term touches, which the
ablation confirms rather than assumes.

### 4. Definition audit

| object | definition used here | matches prior? |
|---|---|---|
| a "long prefill" (term (b) scope) | a request whose NEW tokens exceed one 8,192-token step, so it holds vLLM's single partial-prefill slot (StudyENG1 H-admit verdict a) | NEW name, defined here; the 8,192 step and the partial slot are StudyENG1 section 1.2 and 6 |
| the "prefill cost" a scale multiplies | the step as scheduled minus the same step with no prefill work, so the intercept, the decode term and the admission terms are untouched | NEW, defined here and asserted by a test that a decode-only step and a solo short prefill are unchanged |
| the "batching gain" | `m ** (-exponent)` on the prefill cost of a step shared by m prefills, fitted on the ratio `t(k) / (k x t(1))`, StudyENG1's own H-step statistic | the statistic is StudyENG1 section 5's; the functional form is new |
| "external tokens" | `prompt_tokens_by_source|external_kv_transfer`, attributed to the action only under the two conditions of section 2.1 | the counter is StudyENG1 Part D's; the attribution rule is new and is tested |
| `med_ratio` | median(|predicted| / |measured|) | reproduces StudyT0 section 11.1 exactly for mono11k (1.481 against 1.48), hostreload (0.211 against 0.21), append5 (0.829 against 0.84) and piece2048 (1.155 against 1.16), and to 1.09x and 1.05x for burst4 (1.529 against 1.66) and piece1024 (0.954 against 1.00). T0's ratio column is not carried in a committed JSON, only in its report, so the residual difference cannot be traced further; the signed version is published beside it so neither can be mistaken for the other |
| win-10, sum-80, "a turn", "a session" | not used in this row | n/a |
| "imposed delay", "a trial", "reconstructible", 90 tokens per frame, "fully resident" | unchanged from StudyT0-fidelity and StudyENG1b | yes |

### 5. Claim linkage

The four criteria bear on `research/POLICY_SPEC_v3.md` sections 5.2 and 11 (approval test T0: does
the cost model predict live engine behaviour?) and on nothing else directly. Term (a) **supports
C4** (physical inertia): the cost of holding state on a colder tier is not only measurable but
chargeable to the scheduler's own step model at 262,144 bytes and 50.14 GB/s per token moved, and
the old model's silence about it was a 4.4x under-prediction on its own cell. Terms (b) and (c)
speak to spec 5.2's tolerance language and to nothing in CLAIMS.md. **C5** (joint policy beats
decomposed) is **not tested** here; this row unblocks it by making the engine model one that T0b
can test. Nothing measured here is scoped out: every KV involved is the same model's own, so
FORMULATION.md's Scoping line on KV portability between heterogeneous tiers does not apply, and the
host tier here is the same 32B model's KV offloaded by vLLM's native connector, which StudyENG1b
section 7 check 5 already established is in scope.

### 6. Proxy validity

| proxy | what it actually measures | valid for the claim? |
|---|---|---|
| the run-level `external_kv_transfer` counter as a PER-REQUEST quantity | tokens served from host over a whole run | VALID only under the two conditions of section 2.1, which select the hostreload cells; INVALID for the W25 cells, where it is the warm sessions' own hits, and those 130 arm counters are excluded and charged nothing rather than used. No headline rests on a W25 host charge |
| the Part D concurrency-1 counter delta as that request's transfer | the counters over one request's window | VALID at concurrency 1 and demonstrated so (30/30 host, 0/30 gpu, 0/30 cold, one bytes-per-token value); INVALID at concurrency 4 and demonstrated so; the fit uses concurrency 1 only |
| the TTFT delta by tier as the transfer cost | transfer plus the request's own scheduling and its own prefill | NOT used as a fit input; used only as a cross-check, and the 2.10x spread between its two instances is explained by what each instance also contains |
| the paired difference as the imposed delay | the measured quantity, by construction | inherited from StudyT0-fidelity; valid for criteria (i) and (ii), not sufficient alone for absolute latency, which the solo cross-checks and criterion (iii) carry |
| 90 prompt tokens per D2 frame | the encoder-token count of a request | inherited from StudyENG1 section 11 check 4, declared there as reproducing the 41-plus-image stall and under-predicting the 1-to-4-image stall; unchanged here |

---

## 7. The freeze

`results/orchestration/study_t0b/t0b_freeze.json`, written after the tests were green and after
the re-score, and verified against the working tree at the instant of writing (`verify.ok` true,
no file changed).

* frozen at 2026-11-17T04:11:34Z, git HEAD `35825d5ceec12646f341cb40fd23f51e2c3e59ce`, branch
  `main`, working tree **NOT clean and recorded as such**: this row's own uncommitted library
  changes are present, which is why the file md5s and not the commit identify the frozen model.
* **frozen model: `pol4`**, all three terms at their fitted values.
* flag selector: `policy.eng1_engine.make_sim(engine_model=...)` and
  `Eng1Engine.load(engine_model=...)`, over `ENGINE_MODELS = ("eng1", "pol4", "pol4_nobatch")`.
  All three settings are recorded in the freeze with their full coefficient sets.
* why `pol4` and not `pol4_nobatch`: `pol4` is the only configuration that passes the brief's
  regression gate on the FIT trials. `pol4_nobatch` scores criterion (i) higher but drops (ii)
  below the old model, which is the trade the brief forbids.

| md5 at freeze | file |
|---|---|
| `7da0a984bca4ba4f0ff81d5cee54d18c` | `results/cost/study_eng1/eng1_step_model.json` (UNCHANGED from StudyT0's freeze: the step model was not refitted) |
| `150c22189af0412cb150b8205bc2382a` | `results/orchestration/study_pol4/pol4_terms.json` |
| `7e8779ceaeecdb055ff37bde4b3893c1` | `experiments/orchestration/policy/eng1_engine.py` |
| `33bf0f4f6c646965a00a032d934de84c` | `experiments/orchestration/policy/fit_pol4_terms.py` |
| `c8590fd16b12adceeb1ba672d4ef4396` | `experiments/orchestration/policy/trace_replay.py` |
| `02a68eec82a7953390897ae63a5af114` | `experiments/orchestration/policy/run_pol4.py` |
| `f465266c313738f8b628b8c3577a3450` | `experiments/orchestration/policy/freeze_t0b.py` |
| `3f7d2edfc193e7d21e2ae0bc162c91e6` | `experiments/orchestration/policy/run_t0.py` |
| `2c41bdef137d79f3ca816ae190da9a42` | `experiments/orchestration/policy/t0_harness.py` |
| `69e2622e9e49e5503a3a9a8a09651f61` | `experiments/orchestration/policy/kvpool.py` |
| `b4607d14d0897eaed4a02d55f75cdb51` | `experiments/orchestration/policy/tiers.py` |
| `abbbca7ae904e41851ca4b99fae73345` | `experiments/orchestration/policy/params.py` |

**After this freeze the model may not change for T0b.** The binding constraint is carried in the
freeze file: T0b must be evaluated on FRESH held-out data only; the 174 Part C HOLDOUT triples are
spent and were not read here; and the 406 Part C FIT trials are also not a held-out sample for this
model, because they chose which terms were added.

---

## 8. Tests

**184 before, 211 after, all green**, under
`python -m unittest discover -s experiments/orchestration/policy/tests -t experiments/orchestration`.
27 new tests in `policy/tests/test_pol4_engine.py`: term provenance and the refusal of a terms file
that does not state zero holdout use or is missing a coefficient (3); the extended no-typed-
coefficient contract and the step model's own unchanged provenance (2); the flag, the three
configurations, the refusal of an unknown flag and the bit-identity of the old path to 12 decimal
places (4); term (a) zero without external tokens, linear in them, reproducing the Part D
transfer time, reaching a co-scheduled request, never exceeding cached tokens, and reaching the
policy-facing engine (5); term (b) exactly neutral at or below one step, below one at 11k, rising
with size, moving the monolithic solo TTFT toward the measurement, and not touching a single-step
piece (4); term (c) exactly neutral at m = 1, neutral at exponent 0, monotone, touching only
shared steps, and an assertion that the FITTED SIGN IS A PENALTY so the finding cannot be silently
reversed (5); the holdout exclusion including a faked leak that must raise (2); and the external
token attribution counts (2).

## 9. Open items for the user, and what was NOT done

1. **Criterion (i) did not improve on FIT data** (0.6355 to 0.6305). The brief did not make that a
   stop condition and (ii) to (iv) did not regress, so this row completed; but the headline reason
   is term (c), and the user may wish to overrule the freeze in favour of `pol4_nobatch` (i)
   0.6650, which is one flag, already implemented and tested. It is not frozen because it drops
   (ii) below the old model, which the brief forbids.
2. **The mono11k residue is left unmodelled on purpose.** Closing it needs a loaded-arrival
   blocking measurement that StudyENG1 Part B did not take (it measured rho on an unloaded
   server). That is a STOP AND ASK: the term would have no measurement behind it.
3. **The W25 host reloads are real engine work the model does not charge**, because the recorded
   counter cannot be attributed per request there. A per-request local-versus-external split on a
   W25-like load would close it; StudyENG1 Part D already showed the counters cannot provide it
   above concurrency 1.
4. **The write-through store is measured at 41.47 GB/s and not charged**, because in Part C it
   always falls outside the measured window. Any scenario that defers a build into a trace window
   would need it.
5. `results/cost/study_eng1c/` does not exist, so no StudyENG1c datum entered anything and Part 2
   of the brief (StudyT0b) was correctly not started.

## 10. Files

| file | what |
|---|---|
| `experiments/orchestration/policy/fit_pol4_terms.py` | NEW. The fit of all three terms, the counter attributability test, the cross-checks and the store-side measurement |
| `experiments/orchestration/policy/eng1_engine.py` | the three terms as `Pol4Terms`, the `engine_model` flag, `make_sim`, and `external_cached_tokens` on `SimRequest` |
| `experiments/orchestration/policy/trace_replay.py` | the recorded external-token attribution rule and the unattributed-counter record |
| `experiments/orchestration/policy/run_pol4.py` | NEW. The FIT re-score of the four criteria over the three configurations, the error-direction tables, the noise ceilings, the term ablation, the regression gate and the piece-versus-monolithic comparison |
| `experiments/orchestration/policy/freeze_t0b.py` | NEW. The freeze |
| `experiments/orchestration/policy/tests/test_pol4_engine.py` | NEW. 27 tests |
| `results/orchestration/study_pol4/pol4_terms.json` | the fitted terms with every fit set, cross-check and plausibility figure |
| `results/orchestration/study_pol4/pol4_term_ablation.json` | mechanism verification Step 4 |
| `results/orchestration/study_pol4/pol4_fit_rescore_eng1.json` | the FIT re-score under the old model (reproduces StudyT0's dry run exactly) |
| `results/orchestration/study_pol4/pol4_fit_rescore_pol4.json` | the FIT re-score under the frozen new model |
| `results/orchestration/study_pol4/pol4_fit_rescore_pol4_nobatch.json` | the FIT re-score under the term-(c) ablation |
| `results/orchestration/study_pol4/pol4_old_vs_new.json` | the side-by-side comparison, the regression gate and the ranking change |
| `results/orchestration/study_t0b/t0b_freeze.json` | the freeze: git state, 12 file md5s, the flag settings and the binding constraint |
