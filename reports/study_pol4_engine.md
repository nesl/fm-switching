# StudyPOL4-engine: fixing the three engine-model gaps that made StudyT0's criterion (i) fail

Pre-registered in `research/EXPERIMENTS.md` (row StudyPOL4-engine). Design log D60, Part 1 and
Part 1b. **Part 1b** (sections 2.3 and 2A) was run after the user's decision 1 of 2026-11-17: do
not adopt a configuration on its FIT score, and do not keep a term labelled "sub-linear batching"
whose fitted sign is a penalty and whose motivating diagnosis the measurement refutes. Attributing
the burst4 over-prediction as that decision required found a defect in term (c)'s OWN FIT SCRIPT
which had flipped the term's sign; correcting it supports diagnosis C, raises criterion (i) from
0.6355 to 0.7562 and changes this report's Part 1 conclusion about term (c). The erratum is in
section 2.3 and nothing in Part 1's other two terms changed by a single digit.

**ERRATUM INDEX (Part 1b, 2026-11-17).** Part 1 of this report stated that term (c) fitted as a
PENALTY and that StudyT0-fidelity's diagnosis C was refuted by the measurement. **Both statements
are withdrawn.** The cause was a defect in term (c)'s own fit script and not in any measurement:
`fit_pol4_terms._a1_cells` passed each A1 cell's `N`, the QUERY'S FRAME COUNT (1 or 3), where the
simulator counts encoder work in the step model's own 90-token ENCODER UNITS, in which a 378-token
single-frame query is **4** units and a 1,062-token three-frame query is **12**. Every A1 request
was therefore charged a quarter of its measured encoder work, which depressed the predicted base
and flipped the sign. **Corrected, the fitted exponent is a GAIN of +0.100** (10 % window 0.090 to
0.110, excluding zero; the absolute-objective secondary agrees in sign at +0.150), the old model
gives 15 % to 18 % TOO LITTLE batching gain at k = 16 against the published anchors, and
**diagnosis C is SUPPORTED**. Part 1's original wording is kept where it stands, marked, so the
record shows what was claimed and what corrected it. Every location:

| where | what Part 1 said | corrected in |
|---|---|---|
| section 2.3 | the exponent is a penalty (-0.030); the old model reproduces the anchors; diagnosis C "not supported by the measurement" | section 2.3's own ERRATUM, with the measured anchors recomputed |
| section 3, mechanism Step 2 | one link "CONTRARY to the claim that motivated it" | the ERRATUM note in Step 2 |
| section 3, mechanism Step 5 | alternative (c), a k-independent base error | section 2A.5, which refutes it on Part B's idle-engine rows |
| section 3, Rule 2 | term (c) classified against diagnosis C | the Rule 2 paragraph, now a real positive FOR diagnosis C |
| the `StudyPOL4-engine` row of `research/EXPERIMENTS.md` | the same penalty record in its mechanism_verification field | an inline erratum in that field |
| `experiments/orchestration/policy/tests/test_pol4_engine.py` | a test asserting the penalty sign | the test now asserts a gain, and a second test re-derives every A1 cell's encoder-unit count |
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
| i | delay imposed on others, within 1.5x or 0.1 s | 0.6355 (258/406) FAIL | **0.7562 (307/406) FAIL** | 0.6650 (270/406) FAIL |
| ii | ranking, action pairs differing by more than 2x | 0.9667 (58/60) PASS | **0.9833 (59/60) PASS** | 0.9500 (57/60) PASS |
| iii | job completion time, median absolute relative error | 0.1643 PASS | **0.1039 PASS** | 0.1233 PASS |
| iv | ENG1b prefix loss, class accuracy (852 trials) | 0.9718 PASS | **0.9718 PASS** | 0.9718 PASS |

Criterion (i)'s bar is 0.90 and the model still fails it. The relevant second number is the
**measurement's own repeatability ceiling on these cuts, 0.8276** (72 of 87 repeat pairs): the
revised model is 7.1 points below what the measurement itself supports, where the old model was
19.2 points below it.

**EVERY NUMBER IN THIS TABLE IS IN-SAMPLE FOR THE CHOICE OF TERMS AND NONE OF IT IS A TEST OF THE
REVISED MODEL.** No coefficient of any new term saw a Part C trial: all three were fitted on
StudyENG1 Parts A, B and D and on StudyENG1b. But these 406 FIT trials produced the attribution
in `reports/study_t0_fidelity.md` section 11 that decided WHICH three terms to add, and they
already carried two implementation fixes. The label is repeated at every site below, in every
output JSON, and in the registry row. StudyT0b on fresh data is the only test.

**What moved, and what did not.**

* Criterion (i) improved by **12.1 points**, 0.6355 to 0.7562, against a repeatability ceiling of
  0.8276. In Part 1 it had moved the wrong way (0.6305); the whole of that difference is term
  (c)'s corrected sign, which section 2.3 traces to one expression in its fit script.
* Criterion (ii) improved and (iii) improved by 6.0 points of median relative error; (iv) is
  untouched by construction (it is a KV-pool prediction, not a step-time one).
* **The brief's decisive STOP AND ASK did not trigger for the frozen model**: none of (ii), (iii)
  or (iv) got worse under `pol4`. It DID trigger for the `pol4_nobatch` ablation, which drops (ii)
  below the old model (0.9500 against 0.9667) and also scores (i) lower than `pol4`. So
  `pol4_nobatch` is not a candidate on either count and is kept only as D60's term-(c) ablation.
* Per action, the picture is sharp and is in section 4: **mono11k 0.529 to 1.000, exactly its own
  noise ceiling of 1.000**, burst4 0.543 to 0.714 (ceiling 0.867), piece1024 0.629 to 0.729,
  append5 0.700 to 0.729, piece2048 0.829 to 0.814, and hostreload 0.571 to 0.500 with its
  completion error cut from 0.394 to 0.147. Per load, every one of the five improves or holds.
* **The direction of the remaining error narrowed**: over-prediction in 68.7 % of trials before and
  57.1 % after, median signed error +0.0894 s to +0.0221 s, and 148 failures to 99.

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

### 2.3 Term (c), sub-linear batching: the diagnosis holds, and Part 1's reading of it was wrong

StudyT0-fidelity section 11.4 diagnosis C: the step model's "linear per-image and per-prefill-
request terms do not reproduce the full sub-linear batching gain StudyENG1 measured at larger k".

**ERRATUM.** Part 1 of this study reported the opposite: that the fitted exponent was a small
PENALTY (-0.030), that the old model already reproduced the published anchors to 4.0 % and 0.3 %,
and that diagnosis C was therefore "not supported by the measurement". **That conclusion was
wrong, and the cause was a defect in the term's own fit script, not in the measurement.**
`fit_pol4_terms._a1_cells` passed each A1 cell's `N` to the simulator as the request's image
count. `N` is the QUERY'S FRAME COUNT: StudyENG1 section 2 records an A1 query as 378 tokens at
N = 1 and about 1,062 at N = 3, which is 36 question tokens plus 342 tokens per query image, and
both cells reproduce 342.0 exactly from the record. The simulator's `n_images`, however, is
counted in the step model's own ENCODER-TOKEN UNITS of 90, because `per_encoder_input_ms` was
fitted on steps whose images were 90-token D2 history frames. A 378-token query is **4** of those
units and a 1,062-token query is **12**, not 1 and 3. Passing 1 and 3 charged every A1 request a
quarter of its measured encoder work, which depressed the predicted base and flipped the sign.
The fix is one expression and the convention is now the one every other call site uses; a test
asserts it, and a second test asserts the fitted sign is a gain so the flip cannot recur silently.

**What the measurement says once the convention is right.** The published anchors are the
MEASURED ratios and are unchanged: recomputed from the 1,860 A1 rows as the batch's last first
token, median over 30 batches, `t(16) / (16 x t(1))` = **0.50977** at N = 1 and **0.73058** at
N = 3 against the published 0.510 and 0.731. What changes is the old model's ratio against them:

| | measured | old model | old / measured | new model | new / measured |
|---|---|---|---|---|---|
| N = 1, k = 16 | 0.5098 | 0.5859 | **1.149** | 0.4930 | 0.967 |
| N = 3, k = 16 | 0.7306 | 0.8644 | **1.183** | 0.7332 | 1.004 |

The old model gives **too little** batching gain, by 15 % to 18 % at k = 16, which is diagnosis C.
Per cell its over-charge grows with k and holds at both frame counts:

| cell | measured | old (ratio) | new (ratio) |
|---|---|---|---|
| N=1 k=1 | 0.1349 s | 0.1343 (0.996) | 0.1343 (0.996) |
| N=1 k=4 | 0.3410 | 0.3735 (1.095) | 0.3516 (1.031) |
| N=1 k=16 | 1.1004 | 1.2591 (1.144) | 1.0595 (0.963) |
| N=3 k=1 | 0.2518 | 0.2865 (1.138) | 0.2865 (1.138) |
| N=3 k=4 | 0.7655 | 0.9111 (1.190) | 0.8487 (1.109) |
| N=3 k=16 | 2.9433 | 3.9619 (1.346) | 3.3607 (1.142) |

**ERRATUM (Part 1b): this coefficient replaces the -0.030 PENALTY Part 1 reported; the sign was an
artefact of passing the frame count `N` instead of 90-token encoder units, see the erratum index and
section 2.3.**

`batch_prefill_gain(m) = m ** (-0.100)` for m > 1 prefills sharing a step, 1.0 at m = 1. Fitted on
**StudyENG1 Part A A1, 10 cells, 300 batches**, on the batching RATIO `t(k) / (k x t(1))`, which
is StudyENG1's own H-step statistic and is invariant to any error in the single-request base. The
window within 10 % of the fit's minimum is **0.090 to 0.110**, which excludes zero. The secondary
objective, the absolute batch completion time, now gives **+0.150**: the two objectives **agree in
sign**, which they did not under the old convention, and the ratio fit is the one used. Over the
sweep the gain spans 0.933 at m = 2 to 0.736 at m = 21 on 2,055 of 28,969 steps.

The k = 2 cells are unchanged by the term at both frame counts (1.088 and 1.033 before and
after), because a 2-request batch is handed off far enough apart that the simulator schedules it
as two single-prefill steps, which the term leaves alone by construction.

**Checked against Part C FIT burst4, as the brief required: the check now passes.** burst4's
criterion (i) pass rate rises from 0.543 to **0.714** against a noise ceiling of 0.867, its
median ratio falls from 1.529 to **1.140**, and its predicted median lands on the measurement
(0.2193 s against 0.2187 s). Section 2A.4 shows why this is the term that reaches burst4 at all.

---

## 2A. Part 1b: attributing the burst4 over-prediction, candidate by candidate

The brief named four candidates and required that each be checked explicitly, with evidence, and
that the one which explains the cell be identified. Output
`results/orchestration/study_pol4/pol4_part1b.json`; driver
`experiments/orchestration/policy/analyze_pol4_1b.py`. **Every number in this section that comes
from Part C is IN-SAMPLE**: these are the trials that chose the terms.

The tension the brief pointed at is real and is resolved here: the first fit reported
single-request steps UNDER-predicted at about 0.80 while burst4's imposed delay was
OVER-predicted at about 1.66. The 0.80 was the fit script's own defect (section 2.3); the
over-prediction is a genuine over-charge of a MERGED multi-prefill step, which is the same
quantity A1 measures.

### 2A.1 Candidate 1, the front-end serialization terms: RULED OUT, with the number

Every compared request's predicted delay splits exactly into the change in its hand-off time,
which is the only way StudyENG1 section 7's serial front end can reach another request directly,
and the change in its wait after hand-off. The two shares add to the predicted imposed delay to
within 1e-9, which a test asserts on a real trial.

| action | median over-prediction | front-end share | engine share |
|---|---|---|---|
| burst4 | +0.1305 s | **+0.000036 s** | +0.2785 s |
| mono11k | +10.1338 | +0.4046 | +30.4909 |
| piece2048 | +0.1460 | +0.0009 | +0.8507 |
| piece1024 | +0.0151 | +0.0000 | +0.2024 |
| append5 | -0.0002 | +0.0000 | +0.0987 |
| hostreload | -0.0076 | +0.0000 | +0.0067 |

burst4 is the one cell whose action hands four requests to a serial front end at once, so it is
where this candidate had to show up. It contributes **36 microseconds of a 131 millisecond
over-prediction, 0.03 %**. The front end is not the channel. It does act INDIRECTLY, by staggering
the four hand-offs so the simulator schedules the burst as 1 + 3 rather than 4 together, and that
split matches the measurement: the measured action TTFTs on the traced trial are 0.1719 s then
0.3458 / 0.3465 / 0.3471 s and the predicted are 0.1319 then 0.3692 / 0.3696 / 0.3701, so the
STRUCTURE is right and only the merged step's duration is wrong.

### 2A.2 Candidate 2, the compared-request set: RULED OUT

| action | matched p50 | with p50 | without p50 | unbalanced trials | ratio, episodic | ratio, every background kind |
|---|---|---|---|---|---|---|
| burst4 | 42 | 42 | 42 | **0 of 70** | 1.529 | 1.502 |
| mono11k | 42 | 42 | 42 | 0 of 70 | 1.481 | 1.481 |
| piece2048 | 42 | 42 | 42 | 0 of 70 | 1.155 | 1.142 |
| piece1024 | 42 | 42 | 42 | 0 of 70 | 0.954 | 0.921 |
| append5 | 42 | 42 | 42 | 0 of 70 | 0.829 | 0.770 |
| hostreload | 48 | 48 | 48 | 0 of 56 | 0.211 | 0.211 |

The match is balanced in every one of the 406 trials, so no arm contributes requests the other
does not, and re-running the whole comparison over the SUPERSET definition (every background
kind, which is the definition StudyT0's registered run used by mistake) moves burst4's ratio from
1.529 to 1.502. The set is not the explanation.

### 2A.3 Candidate 3, the per-image admission stall and whether it double counts: RULED OUT

The step model carries three image-sensitive coefficients: `per_encoder_input_ms` = 8.6219 ms,
charged in the step the images are encoded in, and the two admission terms
`admission_per_image_ms` = **-1.2492 ms** and `admission_per_1k_encoder_tokens_ms` = 18.1485 ms,
charged to the step BEFORE a batch starts prefilling. StudyENG1 fitted all three in the same step
regressions, so they are not a double count by construction; what Part 1b measures is their
magnitude and what happens without them.

* The admission charge the simulator levies for the **action's own images** is **0.00 ms** in all
  six cells. The burst's requests are never in an `admitting_next` list, because the engine is
  between steps when they arrive, so no admission charge for them exists to be double counted.
* Zeroing BOTH admission coefficients and re-scoring every cell changes burst4's median
  over-prediction by **less than 1e-6 s** (+0.1305 to +0.1305). It moves only mono11k, and there
  by 0.34 s of 10.13.

A separate definition question arises here and is answered in section 2A.4: `n_images` for a
single-frame query is 4, not 1. That is a naming problem, not an over-charge, and correcting it to
a literal frame count makes the model WORSE, which is why it is not "fixed".

### 2A.4 Candidate 4, how co-arriving requests are scheduled into steps: THIS IS THE EXPLANATION

Where in time the prediction goes wrong decides between a wrong own-block magnitude, which moves
the first blocked arrival, and a wrong blocking rule, which moves the whole window behind it. Sums
over every matched arrival in the bin, across all 70 burst4 FIT trials, old model:

| arrival offset from injection | n | measured sum | predicted sum | ratio |
|---|---|---|---|---|
| before -0.05 s | 1,256 | 0.713 s | 0.366 s | 0.51 |
| -0.05 to +0.05 | 31 | 3.678 | 4.459 | 1.21 |
| +0.05 to +0.15 | 41 | 7.946 | 11.749 | 1.48 |
| +0.15 to +0.30 | 36 | 4.707 | 7.147 | 1.52 |
| +0.30 to +0.60 | 98 | 3.158 | 9.727 | **3.08** |
| +0.60 to +1.20 | 214 | 1.022 | 4.153 | **4.06** |
| +1.20 to +2.50 | 474 | -0.457 | 0.135 | - |
| after +2.50 | 1,418 | -0.867 | -0.224 | - |

The error is not at the moment of injection; it is in the TAIL. The measured disturbance is
essentially over by +0.30 s and the model keeps delaying arrivals out to +1.20 s. That is a queue
that drains too slowly, and what sets the drain rate is the duration of the step the burst's
co-arriving prefills share.

**Measured directly.** The action requests that reach their first token at the same instant were
in one engine step. Taking the span from the moment the engine became free (the first token of the
action request that finished before the group) to that shared instant gives a LOWER bound on the
step that served them, so the ratio below is the smallest over-charge the record is consistent
with:

| | n trials | prefills in the step | predicted step | measured span, lower bound | ratio |
|---|---|---|---|---|---|
| burst4, old model | 58 | 3 | 0.2390 s | 0.1764 s | **1.355** |
| burst4, new model | 58 | 3 | 0.2171 s | 0.1764 s | 1.230 |

**1.355 is the same over-charge, in the same direction, that A1 measures on batched steps (1.084
to 1.346, section 2.3), on data that never entered any fit here.** That is the agreement which
identifies the mechanism: the old model charges a merged multi-prefill step too much, an arrival
that lands inside such a step waits for the rest of it, and the queue behind it inherits the
error. A prefill-cost multiplier on merged steps is exactly the shape of that mechanism, which is
why term (c) is the term that reaches burst4 and why switching it off restores burst4 to the old
model exactly (section 3, Step 4).

The residual 1.230 is reported and not chased: the corrected term closes 35 % of the merged-step
over-charge and the rest would need a measurement of step boundaries, which Part C does not
record.

### 2A.5 The single-request base: named as its own gap, and NO TERM ADDED

The brief asked for the k-independent base under-prediction (0.804 at k = 1, 0.771 at k = 16) to
be named separately from batching and for a term only if a measurement supports one.

**Most of it does not exist.** It was the fit script's frame-count defect. Scored on Part B's solo
rows, which are measured on an idle engine and are independent of Part C, and on the A1 k = 1
cells under both conventions:

| source | n | measured p50 | predicted p50 | ratio |
|---|---|---|---|---|
| Part B solo_ep, 378 new tokens | 20 | 0.1410 s | 0.1332 s | **0.945** |
| Part B solo, 500 to 2,500 new tokens | 40 | 0.4355 | 0.4254 | 0.977 |
| Part B solo_long, above 8,192 new tokens | 20 | 2.6803 | 3.0014 | 1.120 |
| A1 k=1 N=1, images passed as the frame count (the defect) | 60 | 0.1349 | 0.1085 | **0.804** |
| A1 k=1 N=1, images passed as encoder units (the convention) | 60 | 0.1349 | 0.1343 | **0.996** |
| A1 k=1 N=3, images passed as encoder units | 60 | 0.2518 | 0.2865 | 1.138 |

The 0.804 reproduces the first fit's figure exactly and is an artefact of the convention, not a
property of the model. What survives is a **5.5 % under-prediction at 378 tokens** and a **13.8 %
OVER-prediction of a 3-frame query**, in opposite directions, both smaller than the cell-to-cell
scatter, and neither with a measurement isolating its cause. **No term is added.** The one
remaining size-dependent residual, 1.120 above one step, is what term (b) exists for and is
already charged there.

### 2A.6 Blocking under load: identifiable, estimated, and NOT added to the model

StudyENG1 Part B H-admit measured rho = 0.97 to 1.00 on an UNLOADED engine: a request arriving
while a long prefill runs waits for essentially all of its remaining work, and the simulator
implements rho = 1 by construction. The brief asked whether the loaded value can be identified
from the Part C FIT per-request rows. It can:

    rho_hat = (TTFT_with - TTFT_without) / (t_action_last_first_token - t_arrival)

for a compared request whose recorded arrival falls between the action's injection and the
action's last first token, both measured. The denominator is the action's remaining work at that
arrival. Identifiability was decided by a criterion stated before the estimate was read: at least
30 arrivals from at least 10 distinct trials AND a bootstrap CI half-width below 0.25, which is
the width at which the loaded value could still be told apart from the unloaded 0.97 to 1.00. The
bootstrap resamples TRIALS, not arrivals, so the many arrivals inside one trial are not counted as
independent.

| cut | trials | arrivals | rho | 95 % CI | half-width | identified |
|---|---|---|---|---|---|---|
| all | 346 | 1,753 | **0.803** | 0.727 to 0.856 | 0.064 | yes |
| P25 | - | 234 | 0.735 | 0.623 to 0.827 | 0.102 | yes |
| P40 | - | 410 | 0.869 | 0.628 to 1.028 | 0.200 | yes |
| S2 | - | 248 | 0.759 | 0.620 to 0.876 | 0.128 | yes |
| mono11k | 70 | 1,105 | **1.149** | 1.123 to 1.206 | 0.041 | yes |
| piece2048 | 68 | 208 | 0.969 | 0.899 to 1.085 | 0.093 | yes |
| burst4 | 59 | 127 | 0.703 | 0.628 to 0.792 | 0.082 | yes |
| piece1024 | 61 | 143 | 0.679 | 0.577 to 0.767 | 0.095 | yes |
| append5 | 50 | 91 | 0.494 | 0.400 to 0.560 | 0.080 | yes |
| hostreload | 38 | 79 | 0.195 | 0.132 to 0.294 | 0.081 | yes |

Two readings, both worth recording and neither acted on:

1. **Behind a monolithic long prefill under load, blocking EXCEEDS the action's own remaining
   work**: rho = 1.149 with a CI excluding 1.0. The simulator's rho = 1 understates it, because
   under load the action also lengthens the queue the arrival joins, and that second channel is
   not in the rule. This is the loaded-arrival blocking measurement the user and this study agree
   is missing; it is now bounded from Part C but not measured, because Part C varies load and the
   action together and cannot separate the two channels.
2. **Behind the short actions, blocking is well below 1** (0.49 to 0.70), consistent with an
   arrival joining the running batch rather than waiting it out.

**ERRATUM (StudyPOL5-engine, 2026-11-17): reading 2 is WITHDRAWN and the rho values here are
biased low.** StudyENG1d measured loaded-arrival blocking directly on fresh traces and found
rho_b = 0.82 to 1.44 behind piece actions, with **0 of 248 in-window arrivals joining a piece's
step**, against the 0.49 to 0.70 and the "joins the running batch" reading above. Reading 1 (that
blocking behind a monolithic prefill exceeds the action's own remaining work) is CONFIRMED:
StudyENG1d measures rho_b 1.17 to 1.43 for mono11k, rising with load.

**The cause of the bias is identified.** This section's rho divides by the time from the arrival
to the action's FIRST TOKEN, measured from the action's SUBMISSION, so its denominator includes
the action's front-end window: the 0.66 to 0.71 s that StudyENG1d measures for mono11k under load,
0.16 to 0.19 s for piece2048 and about 0.10 s for piece1024. An arrival inside that window is
charged a denominator it never waited on the engine for, which pushes rho down, and it pushes it
down hardest for the short actions, where the front-end window is the largest share of the span.
StudyENG1d's rho_b divides by the time from the arrival to the end of the action's last prefill
STEP, measured from SCHEDULING, which excludes that window. Applying this section's own definition
to StudyENG1d's data gives mono11k 1.262, piece2048 1.084 and piece1024 0.839 (StudyENG1d section
8), which reproduces the direction and the ordering of the numbers above and confirms that the
definition, not the engine, is what differs. The remaining gap is consistent with this section
pooling W25, the lightest load.

**What stands.** The table's ordering across actions is right, its use (reported, not modelled) was
right, and the decision not to fit a blocking coefficient to these FIT trials was right. The
absolute values should be read as a lower bound, and StudyENG1d's rho_b is the measurement.

**Nothing here enters the model.** These numbers come from the same FIT trials criterion (i) is
scored on, so fitting a blocking coefficient to them and re-scoring would be circular. StudyENG1d,
a loaded-arrival measurement on the H100 after StudyENG1c, is the way to pin it; the user has
already ruled that it will be a separate study with its own pre-registered holdout, and that
StudyENG1c is not to be modified mid-run.

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
Part C result was seen: term (c)'s fitted sign was a penalty and the old model appeared to
reproduce the published anchors. **ERRATUM (Part 1b): that record is WITHDRAWN.** It came from
`fit_pol4_terms._a1_cells` passing the query's frame count `N` (1 and 3) where the simulator needs
90-token encoder units (4 and 12); corrected, the exponent is a GAIN of +0.100 and diagnosis C is
supported. The sign was an artefact of
term (c)'s own fit script (section 2.3), and under the simulator's own encoder-token convention
the link runs in the direction diagnosis C claimed: the old model gives 15 % to 18 % too little
batching gain at k = 16, measured on Part A data that entered no fit here. The gain now spans
0.933 at m = 2 to 0.736 at m = 21 on the same 2,055 of 28,969 steps.

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
| hostreload | 0.1882 | 0.0085 | 0.1143 | 0.0276 | 0.1143 | 0.0339 |
| mono11k | 32.9236 | 59.9372 | 34.8716 | 34.8716 | 44.3538 | 44.8987 |
| burst4 | 0.3297 | 0.4881 | 0.2604 | 0.2604 | 0.2604 | 0.4881 |
| piece2048 | 0.9072 | 1.1322 | 1.0183 | 1.0183 | 1.0183 | 1.1322 |

Re-run after Part 1b's correction. The controls pass: disabling the host term removes 82.0 % of
the hostreload cell's change and nothing in the other three; disabling the long-prefill term
removes 37.8 % of the mono11k change and moves no other cell; disabling the batching term removes
40.0 % of the mono11k change and restores piece2048 and burst4 **exactly** to the old model
(shares 1.000 and 1.000). Each cell's change is attributable to the term whose measurement it
rests on, every term moves at least one cell, and no term moves a cell its mechanism cannot
reach.

**Step 5.** Three alternatives named, with what distinguishes each: for (a), that the reload is
free to the engine and hostreload's delay is noise, excluded by the engine's own 57 ms transfer
counter which lives outside Part C; for (b), that the mono11k gap is a scheduling error and not an
own-block magnitude error, which the quadratic-amplification arithmetic above supports and which
is why the residue is left open; for (c), that the measured batching behaviour is already
reproduced and the A1 residual is a k-independent base error. **Part 1b tested that alternative
and refuted it**: the base is 0.996 at A1 k=1 N=1 and 0.945 on Part B's 20 independent idle-engine
solo requests, so there is no k-independent base error to absorb, and the A1 residual grows
monotonically with k at both frame counts (1.084 to 1.144 at N=1, 1.176 to 1.346 at N=3), which is
k-dependent by inspection. A fourth alternative is named and distinguished in section 2A: that
burst4's error is in the front-end serialization or in the compared-request set rather than in
step composition, excluded by a front-end share of 36 microseconds in 131 milliseconds and by a
balanced match in all 406 trials.

**Rule 2 classification.** The three terms are **present, non-zero and varying** (Step 2) and each
one changes the result when disabled (Step 4), so there is no ABSENT or CONSTANT link and nothing
here is an inconclusive from an absent mechanism. Criterion (i) still FAILS its 0.90 bar at
0.7562, and that failure is a **real negative for the revised model against the bar on FIT data**,
qualified twice: these 406 trials are not a held-out sample for a model whose terms they chose, and
the bar is above the measurement's own repeatability ceiling of 0.8276 on the same cuts, so no
predictor could reach 0.90 here. Per term: (a) is a real positive (the gap was total and is now 83
% closed on its own cell); (b) is a real partial positive with its shortfall quantified and its
residual mechanism named and left unmodelled for want of a measurement; (c) is a **real positive
for diagnosis C**, on Part A data that entered no fit, after Part 1's contrary finding was traced
to its fit script. Part 1b's two negatives are both real and both reported as such: the
single-request base gap does not exist (section 2A.5) and no term was added for it, and blocking
under load is identified but deliberately not modelled (section 2A.6).

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
| mono11k | 70 | **1.000** | 0.529 | **1.000** | +10.134 | **+0.630** | 1.481 | **1.019** | 97 % | 60 % | 0.157 | **0.031** |
| hostreload | 56 | 0.750 | 0.571 | 0.500 | -0.008 | +0.031 | **0.211** | **0.543** | 48 % | 61 % | 0.394 | **0.147** |
| piece2048 | 70 | 0.867 | 0.829 | 0.814 | +0.146 | **+0.040** | 1.155 | **1.018** | 74 % | 56 % | 0.081 | 0.079 |
| piece1024 | 70 | 0.800 | 0.629 | **0.729** | +0.015 | **+0.000** | 0.954 | 0.869 | 56 % | 50 % | 0.117 | 0.114 |
| append5 | 70 | 0.667 | 0.700 | **0.729** | -0.000 | -0.008 | 0.829 | 0.741 | 50 % | 46 % | 0.180 | 0.179 |
| burst4 | 70 | 0.867 | 0.543 | **0.714** | +0.131 | **+0.051** | 1.529 | **1.140** | 83 % | 71 % | 0.275 | **0.176** |

Medians of the quantity itself (s): mono11k measured 22.215, predicted 31.178 to **22.951**;
hostreload measured 0.0491, predicted 0.0055 to **0.0378**; piece2048 0.7399, 0.8721 to 0.8210;
piece1024 0.2217, 0.2220 to 0.2189; append5 0.0787, 0.0960 to 0.0842; burst4 0.2187, 0.2855 to
**0.2193**.

Read against the ceilings: the two cells StudyT0 attributed the failure to are the two that move
most. **mono11k**, the one cell where the measurement is perfectly repeatable (ceiling 1.000),
closes the **whole** 47.1-point shortfall and its median signed error falls from +10.134 s to
+0.630 s on a measured 22.215 s. **burst4** closes 17.1 of a 32.4-point shortfall and its
predicted median lands on the measurement to 0.3 %. **append5** is now 6.2 points ABOVE its own
noise ceiling of 0.667, which is as far as a predictor can usefully go on that cell. **piece2048**
loses 1.5 points, one trial, while its median signed error falls by 3.6x and its ratio moves from
1.155 to 1.018: a cell can lose a trial to the 0.1 s absolute window while getting better in
magnitude.

**hostreload** is the one cell that falls, 0.571 to 0.500, and the reason is unchanged from Part 1
and is a property of the criterion, not of the term. It closes the under-prediction in ratio
(0.211 to 0.543) and cuts its completion error by 2.7x (0.394 to 0.147), but its measured values
sit inside StudyENG1's own repeat noise: the old model passed many of those trials by predicting
nearly zero and landing inside the 0.1 s absolute window, and a term that is right in magnitude
can lose such a trial. Its own ceiling is 0.750, so 0.25 of the cell is unreachable by anything.
Stated, not argued away.

### 4.2 Per load

| load | n | noise ceiling | pass (i) eng1 | pass (i) pol4 | pass (i) pol4_nobatch | measured p50 | eng1 p50 | pol4 p50 |
|---|---|---|---|---|---|---|---|---|
| P25 | 84 | 0.889 | 0.750 | **0.810** | 0.786 | 0.1676 | 0.1440 | 0.1589 |
| P40 | 84 | 0.611 | 0.488 | **0.655** | 0.560 | 0.3922 | 0.4064 | 0.3617 |
| S2 | 84 | 0.944 | 0.821 | **0.905** | 0.869 | 0.1202 | 0.1949 | 0.1511 |
| S4 | 84 | 0.833 | 0.452 | **0.726** | 0.440 | 0.6003 | 0.9978 | 0.7099 |
| W25 | 70 | 0.867 | 0.671 | 0.671 | 0.671 | 0.2221 | 0.2676 | 0.2260 |

Every load improves or holds, and the two that improve most are the two heaviest: S4 by 27.4
points and P40 by 16.7. **P40 now sits above its own noise ceiling** (0.655 against 0.611), which
is the load where the measurement is least repeatable. W25 is flat because its action is a warm
append whose steps are never merged and whose host reloads the model does not charge (section 9,
item 3). The per-load median signed error falls at every load: +0.0338 to +0.0125 at P25, +0.1556
to +0.0226 at P40, +0.0381 to +0.0134 at S2, +0.3214 to +0.1253 at S4 and +0.0683 to -0.0073 at
W25.

### 4.3 The direction of the errors

**The model still OVER-predicts, but much less and in fewer trials.** Over the 406 FIT trials the
old model over-predicts in 279 (68.7 %) with a median signed error of +0.0894 s; the new model in
232 (57.1 %) at **+0.0221 s**, a 4.0x reduction in the median bias. Failures fall from 148 to 99,
and the share of failures that are over-predictions falls from 77.7 % (115 of 148) to 63.6 % (63 of
99), so the residual failures are less one-sided than before. The one systematic UNDER-prediction
the old model had, hostreload at ratio 0.211, is the one the new model corrects, and correcting it
moves that cell from under to slightly over (0.543 in ratio, over in 61 % of trials). Four of five
per-load median signed errors remain positive; W25's crosses to -0.0073 s.

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
| P25 | 48.6x | **35.9x** | 33.2x | yes, 15.4x closer to 2.7x |
| P40 | 52.9x | **34.2x** | 36.3x | yes, 16.6x closer to 2.1x |
| S2 | 42.5x | **32.3x** | 30.9x | yes, 11.6x closer to 1.4x |
| S4 | 43.5x | **28.6x** | 27.8x | yes, 15.7x closer to 0.8x |
| W25 | 42.7x | **32.6x** | 38.3x | no, past it: 4.4x off becomes 5.7x off |

In absolute terms the predicted mono11k median falls by 26.2 % at P25, 41.8 % at P40, 27.7 % at
S2, 44.8 % at S4 and 25.1 % at W25, while the two piece actions move by 0 to 27 %. So the revised
model still prefers pieces to a monolithic reconstruction everywhere, but by 15 to 34 % less, and
in four of five conditions that is a large move toward the measurement; W25 is the one condition
where it overshoots. The practical
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
| A1 batching anchor, MEASURED, N=1 | 0.50977 | 0.510 | ENG1 section 5 H-step | 0.9995 | agree |
| A1 batching anchor, MEASURED, N=3 | 0.73058 | 0.731 | same | 0.9994 | agree |
| A1 batching anchor, OLD MODEL, N=1 | 0.5859 | **0.48905 reported in Part 1 of this report** | section 2.3 before the erratum | 1.198 | **disagree, and Part 1's figure is withdrawn: see the erratum** |
| A1 k=1 N=1 own cost, OLD model | 0.1343 s | 0.1085 s reported in Part 1 as 0.804 of measured | same | 1.238 | **disagree, same cause, same erratum** |
| solo episodic own cost, measured | 0.1410 s (Part B solo_ep, n=20) | 0.1416 s (Part C quiet arrivals, n=158) | independent cut of the record | 0.9958 | agree, two sources |
| query image tokens implied by A1 | 342.0 at both N=1 and N=3 | 378 = 36 + 342 N, ENG1 section 2 | ENG1 section 2 | 1.0000 | agree, exactly |
| history frame tokens | 90.00 (slope over 1,118 Part C build rows with recorded frame counts, intercept 44) | 90 | ENG1 section 11 check 4 | 1.0000 | agree |

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
| **`n_images` / `images_in_step`** | **a count of the step model's 90-token ENCODER UNITS, not a count of images or frames.** `per_encoder_input_ms` was fitted on steps whose images were 90-token D2 history frames, so it behaves as a per-90-encoder-token rate. A 378-token single-frame query is 4 units and a 1,062-token three-frame query is 12 | **A NAME USED WITH TWO DIFFERENT DEFINITIONS, which is exactly what this check exists to catch.** The simulator and `trace_replay._n_images` always used encoder units; `fit_pol4_terms._a1_cells` used the literal frame count for one fit, which produced Part 1's wrong sign. The encoder-unit convention is validated against the measurement in section 2A.5 and the literal-frame one is not: the literal count predicts a solo query at 0.761 of measured, the encoder-unit count at 0.945 to 0.996. The name is misleading and is left as it is, because renaming a field in the frozen path would change the freeze; the definition is recorded here and asserted by a test |
| a "query image" versus a "history frame" | a query image is 342 prompt tokens and a D2 history frame is 90, both recovered from the committed record (section 2A.5) | NEW distinction, made here; both numbers are StudyENG1's own and agree with it exactly |
| the "blocking fraction" rho | measured delay of a compared arrival divided by the action's measured remaining work at that arrival | the statistic is StudyENG1 Part B H-admit's; the loaded version is new and is NOT used in the model |
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
| `n_images` as a proxy for a request's ENCODER WORK | 90-token encoder units, derived from the request's new tokens, not a physical image count | VALID for the cost, and demonstrated so against two independent measurements (section 2A.5): a 378-token single-frame query needs 4 units' worth of encoder time, because its one image is 342 tokens. INVALID as an image count, and Part 1's term (c) fit is what happens when it is read that way. No conclusion rests on the number being a count of images |
| the measured shared first-token instant as evidence of ONE engine step | that those requests reached their first token within 5 ms of each other | VALID as a LOWER bound on the step that served them, which is how section 2A.4 uses it; it cannot show the step was not longer, so the reported 1.355 over-charge is a floor and not an estimate |
| the paired difference as the imposed delay | the measured quantity, by construction | inherited from StudyT0-fidelity; valid for criteria (i) and (ii), not sufficient alone for absolute latency, which the solo cross-checks and criterion (iii) carry |
| 90 prompt tokens per D2 frame | the encoder-token count of a request | inherited from StudyENG1 section 11 check 4, declared there as reproducing the 41-plus-image stall and under-predicting the 1-to-4-image stall; unchanged here |

---

## 7. The freeze

`results/orchestration/study_t0b/t0b_freeze.json`, written after the tests were green and after
the re-score, and verified against the working tree at the instant of writing (`verify.ok` true,
no file changed).

* **RE-FROZEN after Part 1b.** The Part 1 freeze (2026-11-17T04:11:34Z, HEAD
  `35825d5ceec12646f341cb40fd23f51e2c3e59ce`, `pol4_terms.json` md5
  `150c22189af0412cb150b8205bc2382a`) is superseded. It was never binding: StudyT0b cannot start
  until StudyENG1c commits its Part D holdout, `results/cost/study_eng1c/` does not exist, and no
  T0b evaluation had been run against it.
* frozen at 2026-11-17T05:36:55Z, git HEAD `4a9facba5c597a91a08dc8da39518c73e0263858`, branch
  `main`, working tree **NOT clean and recorded as such**: Part 1b's own uncommitted library
  changes are present, which is why the file md5s and not the commit identify the frozen model.
* **frozen model: `pol4`**, all three terms at their fitted values, term (c) at the corrected
  +0.100.
* **why this configuration, by mechanism and not by score**, which is what the user's decision 1
  required. Term (a) is the only term that charges a transfer the engine's own counters record and
  the model charged nowhere. Term (b) is the only term fitted on the own-block cost of a prefill
  that exceeds one step. Term (c) represents the over-charge of a merged multi-prefill step, which
  is measured on Part A at 1.084 to 1.346 and independently on Part C burst4 at a floor of 1.355,
  and it is the only term whose shape can reach that quantity. All three mechanisms are present,
  measured outside Part C, and each one moves only the cells its mechanism can reach (section 3,
  Step 4). `pol4_nobatch` is rejected on the mechanism: switching term (c) off asserts that merged
  steps are charged correctly, which two independent measurements say they are not. It also scores
  lower on (i) and regresses (ii), so no reading of the numbers favours it either.
* flag selector: `policy.eng1_engine.make_sim(engine_model=...)` and
  `Eng1Engine.load(engine_model=...)`, over `ENGINE_MODELS = ("eng1", "pol4", "pol4_nobatch")`.
  All three settings are recorded in the freeze with their full coefficient sets.
* the brief's regression gate is re-checked and `pol4` passes it: no criterion among (ii), (iii)
  and (iv) is worse than the old model's.

| md5 at freeze | file |
|---|---|
| `7da0a984bca4ba4f0ff81d5cee54d18c` | `results/cost/study_eng1/eng1_step_model.json` (UNCHANGED from StudyT0's freeze: the step model was not refitted) |
| `d7ddbd2878e4d7127abde86de3ce5337` | `results/orchestration/study_pol4/pol4_terms.json` (was `150c22189af0412cb150b8205bc2382a` at the Part 1 freeze; terms (a) and (b) are byte-identical, term (c)'s exponent changed from -0.030 to +0.100) |
| `7e8779ceaeecdb055ff37bde4b3893c1` | `experiments/orchestration/policy/eng1_engine.py` |
| `ee15fa84fa7a2a0d56c569271be75271` | `experiments/orchestration/policy/fit_pol4_terms.py` (was `33bf0f4f6c646965a00a032d934de84c`: the `_a1_cells` encoder-unit fix and the reporting it added) |
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

**184 before Part 1, 211 after Part 1, 226 after Part 1b, all green**, under
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
shared steps, and an assertion on the fitted sign so the finding cannot be silently reversed (5);
the holdout exclusion including a faked leak that must raise (2); and the external token
attribution counts (2).

**Part 1b: 15 more tests, 14 new in `policy/tests/test_pol4_part1b.py` and one rewritten.** The
rewritten one is the sign assertion, which now requires the exponent to be POSITIVE, requires the
old model's ratio to exceed the published anchors by more than 2 % at both frame counts, and
requires the new model to be closer than the old at both; its docstring carries the erratum, so
anyone reversing it has to read why. One new test is the regression guard for the defect itself: it
re-derives every A1 cell's image count and requires it to equal the encoder-unit value and to
differ from `N`. The monotonicity test now requires the gain to DECREASE in m and to be below 1.
The other 13 cover the Part 1b analysis: the blocking estimator against a synthetic pair of arms
whose rho is 0.55 by construction, that an arrival outside the action's window is not counted, that
a thin cut is not declared identified, that the identifiability thresholds are the stated ones,
that the bootstrap CI brackets its median, and that the estimator records that it is not added to
the model (6); and the four candidate checks, that the front-end and engine shares add to the
predicted delay to 9 decimal places on a real trial, that the front end is below 1 % of burst4's
over-prediction, that the compared set is balanced and the superset definition agrees within 5 %,
that the admission charge for the action is exactly zero and zeroing both coefficients changes
nothing, that the merged step is over-charged and the term reduces it against an unchanged
measured span, and that the query-image token count recovered from the record is 342 at both frame
counts with the frame-count convention reproducing the 0.804 figure (7).

## 9. Open items for the user, and what was NOT done

1. **Criterion (i) is 0.7562 and still FAILS its 0.90 bar.** Three numbers belong side by side, as
   StudyT0's own verdict wording requires: the bar **0.90**, the measurement's repeatability
   ceiling on these cuts **0.8276**, and the model **0.7562**. The bar is above the ceiling, so no
   predictor can reach it on these trials; the model is 7.1 points below the ceiling, where the old
   model was 19.2 below. That remaining 7.1 points is the honest size of the fidelity gap on FIT
   data, and it is not a settled number, because these trials chose the terms.
2. **The mono11k own-block residue is closed, and the loaded-blocking measurement is still
   missing.** Part 1 reported that closing mono11k needed a loaded-arrival blocking measurement;
   in the event the cell went to 1.000 of its own ceiling through the merged-step correction, which
   is a different channel. The loaded-blocking question is nevertheless real and is now BOUNDED
   rather than measured: section 2A.6 estimates rho = 1.149 (CI 1.123 to 1.206) behind a monolithic
   prefill under load against the simulator's rho = 1, from Part C FIT, in sample. Part C varies
   load and action together and cannot separate the queue channel from the blocking channel, so
   the number is reported and NOT modelled. StudyENG1d after StudyENG1c is the way to pin it; per
   the user's decision 2 StudyENG1c is not modified mid-run.
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
| `experiments/orchestration/policy/tests/test_pol4_engine.py` | NEW. 27 tests, 3 of them rewritten in Part 1b |
| `experiments/orchestration/policy/analyze_pol4_1b.py` | NEW, Part 1b. The four-candidate attribution, the single-request base check and the loaded blocking estimator |
| `experiments/orchestration/policy/tests/test_pol4_part1b.py` | NEW, Part 1b. 14 tests |
| `results/orchestration/study_pol4/pol4_part1b.json` | NEW, Part 1b. Every number in section 2A |
| `results/orchestration/study_pol4/pol4_terms.json` | the fitted terms with every fit set, cross-check and plausibility figure |
| `results/orchestration/study_pol4/pol4_term_ablation.json` | mechanism verification Step 4 |
| `results/orchestration/study_pol4/pol4_fit_rescore_eng1.json` | the FIT re-score under the old model (reproduces StudyT0's dry run exactly) |
| `results/orchestration/study_pol4/pol4_fit_rescore_pol4.json` | the FIT re-score under the frozen new model |
| `results/orchestration/study_pol4/pol4_fit_rescore_pol4_nobatch.json` | the FIT re-score under the term-(c) ablation |
| `results/orchestration/study_pol4/pol4_old_vs_new.json` | the side-by-side comparison, the regression gate and the ranking change |
| `results/orchestration/study_t0b/t0b_freeze.json` | the freeze: git state, 12 file md5s, the flag settings and the binding constraint |
