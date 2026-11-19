# StudyEVNEED: how often does a robot question actually need history?

> **MOTIVATION CORRECTION (D135).** The +17.5 pp history benefit that launched Part C's rationale
> holds **only for questions whose evidence lies outside the recent window, about 12 percent of
> them**. Across all questions, history **HELPS 8.05 percent and HURTS 6.86 percent, net +1.18 pp
> with a CI of [-1.42, +3.79] that does not exclude zero.** The figure is real and it is
> conditional; quoting it unconditioned overstates the effect on the full question set by about
> fifteen times.

Session 2, D134 follow-on. **Offline and read-only**: no policy code changed, no GPU used, every
number from committed per-question records. Prefix `evidence-need`.

**Why now.** `RecallAction.representation` is read and charged as of `e924005`, so evidence
selection is finally expressible. Part A made it possible; this study asks whether it is worth
anything.

---

## 0. DATA INVENTORY, and one gap that bounds item 3

| resolution | pairs that exist | n |
|---|---|---|
| **per-question** | K1 = 32B-I x RICH, K3 = 32B-I x RECENT, K2 = 32B-T x RICH | 845 each |
| **per-category** | 32B-RICH, 32B-RECENT, **32B-D2**, 4B-D2, device-N1-orin | 8 categories |
| aggregate only | 4B-I x RECENT 0.3278, 4B-T x RICH 0.3089, 8B-I x RICH 0.3621 | 845 each |
| **ABSENT** | **4B-I x RICH** (StudyR1 records "NOT AVAILABLE, no StudyO run exists"); **32B x D2 PER-QUESTION** | - |

**Join validated before anything was built on it: 845 of 845 question ids carry BOTH K1 and K3.
Zero missing.**

**The gap that bounds item 3:** no intermediate window and no summary representation exists at
per-question resolution. Only the two endpoints, RECENT and RICH, plus D2 at category resolution.
So this study can size the endpoint choice and cannot size a graded ladder.

---

## 1. THE 2x2. The net delta hides flows SIX TIMES its size

845 questions, bootstrap CIs at 2,000 resamples.

| outcome | n | share |
|---|---|---|
| both right | 266 | 31.5 % |
| both wrong | 453 | 53.6 % |
| **RECENT right, RICH wrong (history HURTS)** | **58** | **6.9 %** |
| **RECENT wrong, RICH right (history HELPS)** | **68** | **8.0 %** |

| quantity | value | 95 % CI |
|---|---|---|
| history HELPS | **8.05 %** | [6.27, 9.94] |
| history HURTS | **6.86 %** | [5.21, 8.52] |
| net (`K1_minus_K3`) | **+1.18 %** | [-1.42, +3.79] |

**The headline: representation changes the answer on 14.9 percent of questions, and it changes it
in BOTH directions at nearly equal rates.** The committed net of +1.18 pp, which does not exclude
zero, is the small residue of two large and opposing flows. **Every delta reported in this project
so far has been that residue.**

## 1.1 HELPS is coverage-dependent. HURTS is NOT

| split | n | HELPS | HURTS | net |
|---|---|---|---|---|
| RECENT window COVERS the evidence | 748 | **5.88 %** | 6.82 % | -0.94 |
| RECENT window MISSES the evidence | 97 | **24.74 %** | **7.22 %** | +17.53 |

**History helps four times more often when the recent window misses the evidence, exactly as
expected. But history HURTS at a flat ~7 percent whether the window covers the evidence or not.**

That asymmetry is the structural result of item 1. The benefit of history is predictable from
coverage; **the cost of history is not predictable from coverage at all.** Any rule built on
"does the recent window cover the evidence" can capture the upside and is blind to the downside.

## 1.2 By question type, the net runs BOTH WAYS

| category | n | HELPS | HURTS | net |
|---|---|---|---|---|
| sequential_action | 102 | 15.69 | 8.82 | **+6.86** |
| temporal_ordering_recognition | 90 | 14.44 | 8.89 | +5.56 |
| visual_detail_recall | 143 | 6.99 | 4.20 | +2.80 |
| object_comparison | 91 | 6.59 | 4.40 | +2.20 |
| time_duration | 121 | 4.13 | 2.48 | +1.65 |
| spatial_aware_reasoning | 91 | 3.30 | 3.30 | 0.00 |
| counting_objects_events | 110 | 6.36 | 7.27 | -0.91 |
| **location_trace** | 97 | 8.25 | **17.53** | **-9.28** |

**`location_trace` is the strongest signal in the study and it points the WRONG way: sending the
full history costs 9.3 pp net, with history actively hurting on 17.5 percent of its questions.**

**This independently corroborates the non-monotonicity result from the committed per-category
tables, where D2 beat RICH on `location_trace` by +17.2 pp.** Two different measurements, one
per-question and one per-category, agree that this category is harmed by more history. That is a
real property of the workload, not an artefact of either table.

## 1.3 By history size: a LIMITATION, not a result

| bucket | n |
|---|---|
| under 5k tokens | 4 |
| 5k to 11k | 18 |
| 11k to 19,381 | 823 |
| **above 19,381, the D132 feasibility breakeven** | **0** |

**No StudyR1 question has a history above the feasibility breakeven.** So the question item 3 was
to answer, how many physically infeasible questions become answerable on time with RECENT and at
what accuracy, **cannot be answered from committed accuracy data at all**. The timing half is
computable from the cost curve; the accuracy half has no evidence. This is stated as a gap rather
than filled.

---

## 2. CAN IT BE PREDICTED AT QUESTION TIME? No, on both counts

**DEV/EVAL discipline: the committed split is real and was applied, not assumed.**
`experiments/orchestration/baselines/sember_split.py` exposes `is_dev(question_id)` and
`is_eval(question_id)`; the committed `amend2_sember_split.json` states the rule as *"split by
video on sha256(video_id); lowest 30 percent of the digest order is DEV"*. Applied here: **DEV
243, EVAL 602, overlap 0.** Every rule below is fitted on DEV only and scored on EVAL only.

**EVAL base rates: HELPS 8.14 percent, HURTS 7.14 percent.** A rule has signal only if its
precision beats these.

| rule | flow | precision | recall | lift over base |
|---|---|---|---|---|
| **A. coverage** *(ORACLE, NON-DEPLOYABLE)* | predict HELPS | **0.217** | 0.306 | **2.7x** |
| **A. coverage** *(ORACLE, NON-DEPLOYABLE)* | predict HURTS | 0.068 | 0.837 | **0.95x, BELOW base rate** |
| B. category, fitted on DEV | predict HELPS | 0.097 | 0.469 | 1.19x |
| B. category, fitted on DEV | predict HURTS | 0.071 | 0.605 | **1.00x, exactly chance** |

### 2.1 Nothing predicts the HURTS flow

**This is the question that decides whether the lever is worth building, and the answer is no.**
Coverage, which is the strongest signal available and is not even deployable, predicts HURTS at
**0.068 against a base rate of 0.0714** — below chance. The DEV-fitted category rule predicts it at
**exactly** the base rate.

**So the achievable gain is capped at the HELPS side**, and roughly 7 percent of questions will
continue to be actively harmed by whatever representation is sent, with nothing in the candidate
set able to identify them in advance. That is a finding in its own right and it follows directly
from item 1.1: the cost of history is independent of coverage, so coverage-like features cannot
see it.

### 2.2 The per-category lever does not survive DEV to EVAL

The category net in item 1.2 ran from +6.86 to -9.28 and looked like the natural lever. **Fitted
honestly on DEV and scored on EVAL it gives a lift of 1.19x on HELPS and 1.00x on HURTS.** The
category table was reading sampling noise at n = 90 to 143 per category, and the DEV-selected set
(`sequential_action`, `temporal_ordering_recognition`, `visual_detail_recall`) does not generalise.

**I would have reported the per-category policy as the recommendation on the full-sample table.**
The split is what prevented that.

### 2.3 AND THE CATEGORY IS NOT AVAILABLE AT RUNTIME ANYWAY

`arms_policy.py:73` sets **`QTYPE = "counting_objects_events"`**, described as *"the one committed
RC question type (P9)"*, and `d.qtype = QTYPE` at line 433. **`qtype` appears ZERO times in
`coordinator.py` and ZERO times in `cstate.py`.** The per-question category never reaches a
decision.

**So rule B is an oracle bound like rule A, and every per-category number in this report is
descriptive rather than actionable.** Both candidate rules are labelled non-deployable in the table
above.

### 2.4 A CONSEQUENCE BEYOND THIS STUDY: the policy's quality model is mis-specified by 14 to 20 pp

Because `qtype` is pinned to one category, every `rc_accuracy` lookup the policy makes is for
`counting_objects_events`, which is **12.2 percent of trace questions** and one of the hardest:

| representation | what the policy SEES | trace-weighted TRUTH | error |
|---|---|---|---|
| RICH | 0.2500 | 0.4246 | **-17.5 pp** |
| RECENT | 0.2500 | 0.3941 | -14.4 pp |
| D2 | 0.2222 | 0.4260 | **-20.4 pp** |

**The policy systematically under-values every cloud representation by 14 to 20 pp, and the SIGN
of the D2-against-RICH comparison is inverted**: it sees D2 as worse than RICH (0.2222 against
0.2500) when on the trace mix D2 is better (0.4260 against 0.4246).

This is a **seventh** entry for the channel catalogue, and it is a new shape: not dead, not absent,
but **CONSTANT AND UNREPRESENTATIVE**. It passes every check that asks whether a quantity is
non-zero and varies, because it is non-zero; it fails because it does not vary with the thing it
names. It would make COVEX under-value recall service generally, which is consistent with the
admission behaviour seen throughout this report.

---

## 3. LIMITATIONS, with implications named

1. **No per-question measurement above the feasibility breakeven.** 0 of 845 StudyR1 questions
   exceed 19,381 tokens, while the D132 ceiling found about **9.6 percent of TRACE questions above
   it**, because trace histories accumulate across a run and StudyR1's per-question setup does not.
   **The questions that matter most for feasibility are exactly the ones with no committed accuracy
   measurement.** Item 3's timing half is computable; its accuracy half has no evidence. This is an
   evidence gap, not an analysis limitation.
2. **Only the ENDPOINTS of the representation ladder exist at per-question resolution.**
   FM-switching's axis is graded, full / window / summary-80 / summary-200, and this workload has
   per-question data for RICH and RECENT only, plus D2 at category resolution. **Anyone designing a
   graded policy from this report should know the middle of the ladder has never been measured
   here.**
3. **S-EMBER only**, one workload, 845 questions, 234 videos. The LoCoMo contrast in the
   orchestration report shows the representation axis behaves oppositely on another workload.
4. The committed JPEG and cache-path caveats (D70, D81) apply to the underlying StudyR1 records.

---

## 3. THE LEVER, timing half. 95.7 percent of recall GPU time, and every infeasible question rescued

Seeds 0, 4, 5 and 6 at **10, 12 and 14 devices**, the crossover band. History size taken **at
question arrival** from the trace's `history_tokens`, the same construction as the D132 ceiling,
never the session's final size. Cost from the committed curve: `recall_gpu_s(h, "COLD")` plus
`recall_gpu_s(h, "GPU-WARM")`. RECENT is the committed `RECENT_WINDOW_TOKENS = 467`.

**EVERY ROW BELOW CARRIES THE NO-MEMORY-LIMIT CAVEAT:** these traces are pre-pressure,
`gpu_kv_tokens` was handed to arms and never enforced, and there was no automatic eviction.

| n | questions | full-history GPU-s | RECENT GPU-s | saved | infeasible | **rescued** |
|---|---|---|---|---|---|---|
| 10 | 92 | 249.8 | 11.04 | **238.7 (95.6 %)** | 7 | **7 of 7** |
| 12 | 108 | 302.4 | 12.96 | **289.5 (95.7 %)** | 9 | **9 of 9** |
| 14 | 136 | 385.5 | 16.32 | **369.2 (95.8 %)** | 12 | **12 of 12** |

Per seed the saving is 94.5 to 96.1 percent, with no cell outside that range.

### 3.1 The size of it, in terms the queueing result can use

At 14 devices, recall rebuilds cost **385.5 GPU-seconds over a 600 s run: roughly 64 percent of
one GPU, spent entirely on reconstructing history.** Sending RECENT instead would cut that to
**16.3 GPU-s, about 2.7 percent.**

**This is the same quantity the queueing account of the hardening report is about.** The robot axis
is bound by delay against a 5.0 s deadline, and recall rebuilds are what saturate the engine and
create that delay. **Removing 95.7 percent of recall GPU time is the largest single lever measured
anywhere in this work**, and it acts directly on the binding constraint rather than on the price of
it.

### 3.2 Every infeasible question is rescued, and that is arithmetic rather than luck

All 28 questions above the 19,381-token feasibility breakeven across the band become feasible under
RECENT: **7 of 7, 9 of 9 and 12 of 12.** The rescue rate is 100 percent by construction, because
467 tokens sits two orders of magnitude below the breakeven, so no question sent as RECENT can be
infeasible on an idle engine.

### 3.3 THE CATCH, and it is the whole study in one line

**The accuracy cost of this lever is unmeasured exactly where the lever is largest.**

- On the questions that HAVE committed accuracy data, RECENT costs **+1.18 pp net** with a CI
  including zero, which is small; but that net is the residue of **8.05 percent helped and 6.86
  percent harmed** (item 1), and **nothing in the candidate set predicts the harmed flow**
  (item 2).
- On the questions this lever *rescues*, the ones above the breakeven, **there is no committed
  accuracy measurement at all**: 0 of 845 StudyR1 questions reach that length (item 1.3). They are
  currently undeliverable, so today they are answered on-device or not at all; whether a 467-token
  RECENT answer beats that is **unknown and unmeasurable from committed data**.

**So the recommendation this study supports is narrow and I am stating it as such:** the timing
lever is real, large and acts on the binding constraint. **It cannot yet be converted into a
deployable policy**, because the two things a policy needs are both missing: a runtime signal for
when history matters (item 2: none exists, and the category that might have served is dropped in
`cstate`), and an accuracy measurement in the regime where the lever pays most (item 1.3: absent).

**The highest-value single experiment this study identifies** is therefore not a policy change: it
is a per-question accuracy measurement for long histories and for D2, which would close both gaps
at once.
