# StudyE6-intervention — can a policy predict WHICH intervention helps, and does a combined policy beat an independent evidence selector plus model router?

**OFFLINE ANALYSIS OF EXISTING RESULTS.** CPU only on the flash host: no GPU was used, no model server was started, and no inference was run. All numbers come from committed per-question result files of earlier studies.

**E-id:** `StudyE6-intervention`, pre-registered in `research/EXPERIMENTS.md` on 2026-11-10 **before any number in this report was computed** (user-authorized row).  
**Scripts:** `experiments/orchestration/study_e6_part0_upload_fix.py` (Part 0), `experiments/orchestration/study_e6_intervention.py` (main), `experiments/orchestration/study_e6_report.py` (this file).  
**Results:** `results/orchestration/study_e6/e6_part0_upload_fix.json`, `e6_results.json`, `e6_realized_vectors.npz`.  
**Environment:** conda env `fmtk` (scikit-learn 1.1.3, numpy 1.24.4, scipy 1.9.1).

## Prominent flags (read first)

1. **No policy tested here comes close to the oracle, and the headline answer to the question is negative.** The per-question oracle over the four cells scores 0.5621 against 0.3953 for the best static cell; every learned policy lands between those two and most land below the static cell.
2. **The combined policy never beats the best independent baseline.** Of the paired contrasts, the only CIs that exclude zero do so on the **negative** side (combined worse). The pre-registered rule for 'combined beats independent' therefore fails, and it fails in the direction opposite to the hypothesis.
3. **No feature set adds value over F1.** Question text (F2), session history (F3) and 4B confidence (F4) never improve AUROC over category + question time with a CI excluding zero; in three contrasts they are significantly **worse**. By the pre-registered rule, the decision reduces to a per-type lookup rule.
4. **Part 0 overturns one of StudyE4's stated conclusions.** E4's per-question analysis charged cloud-held history arms for every frame since the previous question, while its session analysis charged only the newest pending frame. Under the consistent (session) rule, E4's finding that *'at constrained uplinks and short deadlines the answer is a single configuration'* does not hold: headroom at 13.6 Mbit/s PNG 5 s goes from 0.004 (≈ noise) to 0.079.
5. **Setting (b) is dominated by upload feasibility, not by prediction.** Because RECENT pays its full frame set every question, at 13.6 Mbit/s PNG 10 s only 0.9% of H1 and 0.7% of K3 requests can be delivered at all, against 99.9% of K1. There is little left to decide.
6. **F4's confidence probe is unaffordable at a constrained uplink.** Reading 4B's letter logprobs requires shipping the RECENT frames first, so at 13.6 Mbit/s PNG 10 s every F4 policy collapses to ≈0.0059 utility.
7. **Noise floor.** Near-identical arms (StudyD11 arm F) disagree on 0.59% (32B) and 1.47% (4B) of questions, giving an oracle-headroom floor of 0.15 pp / 0.44 pp. Differences at or below ~0.0044 are indistinguishable from run-to-run noise.

## 1. Arms, and what each comparison can identify

All four primary cells are S-EMBER, 845 questions, Instruct, greedy, max 512 tokens, vLLM 0.31.0 on h100nvl. None is marked INVALID in `research/EXPERIMENTS.md` or excluded by `reports/comparability_ledger.md`.

| cell | model | evidence construction | source | accuracy |
|---|---|---|---|---|
| H1 | 4B-I | RECENT (121 frames) | StudyClean | 32.54% |
| H2 | 4B-I | RICH (≤ 256 frames at 1 fps) | StudyClean | 30.18% |
| K3 | 32B-I | RECENT (121 frames) | StudyR1 batched | 38.34% |
| K1 | 32B-I | RICH (≤ 256 frames at 1 fps) | StudyR1 batched | 39.53% |

All 845 questions are present in all four cells, so every target below is a complete paired comparison. **Match statements, as required:**

- **K3 vs H1 (cap_recent)** — IDENTICAL_INPUT (ledger H1-K3): same requests 845/845, same vLLM 0.31.0 FA3, both greedy 512. Differs: model (4B vs 32B) and GPU (1 vs 3). Identifies capability at fixed input.
- **K1 vs H2 (cap_rich)** — IDENTICAL_INPUT (ledger H2-K1): prompt tokens 845/845 exact, same stack and decoding, GPU 1 vs 3.
- **H2 vs H1 (ev_4B)** — REALLOCATED_BUDGET (ledger H2-H1): same server, stack, decoding, questions. RICH vs RECENT moves window, frame count and resolution TOGETHER under one token budget - not history length alone.
- **K1 vs K3 (ev_32B)** — REALLOCATED_BUDGET (ledger K1-K3): same model, stack, host, greedy. Same caveat as H2-H1.
- **K1 vs H1 (both)** — model and evidence move together; not decomposable into one factor.
- **D13 vs H1 (F4 features)** — same model, stack and decoding, logprobs=True; predictions 845/845 identical and prompt tokens 845/845 identical (checks.d13_vs_h1), so D13 confidence is H1's own confidence.

The two evidence contrasts are therefore *not* clean history-length manipulations: the ledger labels RICH-vs-RECENT `REALLOCATED_BUDGET` because window, frame count and resolution move together under one token budget. Every statement about 'evidence gain' below inherits that.

## 2. PART 0 — E4 upload-consistency fix

### 2.1 The inconsistency

`study_e4_counterfactual.py:196-201` charges a cloud-held history arm for **every frame newer than the previous question of the same video**, whereas the session analysis at `:395-399` charges it for **only the newest pending frame**. The same arm is therefore billed two different ways in one study. Part 0 adopts the session rule throughout Part 1; RECENT arms pay their full frame set per question under both rules, since they hold nothing at the cloud.

**Assumption, stated explicitly as the spec requires:** RICH re-samples frames at each question (StudyRH3), so a cloud holding all frames at 1 fps can build the RICH input without a fresh upload. The newest-frame charge is the marginal cost of keeping that cloud-side store current, not the cost of building the prompt.

**Reproduction check (this is also consistency check 1).** The Part 0 script reimplements E4's curves, UNKNOWN handling, cross-fitting and bootstrap, and under the *original* rule it reproduces the committed `e4_results.json` table 4.1 with **max absolute difference 0.0000 across all 24 cells**. The corrected numbers below therefore differ from E4 only because of the upload rule.

### 2.2 What the fix does to the upload charge

| arm | held at cloud | rule | median | mean | max |
|---|---|---|---|---|---|
| H1 | no | E4 original | 34.260 MB | 33.267 MB | 34.474 MB |
| H1 | no | **corrected** | 34.260 MB | 33.267 MB | 34.474 MB |
| K3 | no | E4 original | 34.260 MB | 33.267 MB | 34.474 MB |
| K3 | no | **corrected** | 34.260 MB | 33.267 MB | 34.474 MB |
| H2 | yes | E4 original | 15.083 MB | 17.625 MB | 36.310 MB |
| H2 | yes | **corrected** | 0.157 MB | 0.222 MB | 0.696 MB |
| K1 | yes | E4 original | 15.083 MB | 17.625 MB | 36.310 MB |
| K1 | yes | **corrected** | 0.157 MB | 0.222 MB | 0.696 MB |
| U32 | yes | E4 original | 29.875 MB | 27.954 MB | 60.971 MB |
| U32 | yes | **corrected** | 0.283 MB | 0.316 MB | 0.696 MB |
| D2 | yes | E4 original | 6.293 MB | 7.462 MB | 33.283 MB |
| D2 | yes | **corrected** | 0.140 MB | 0.140 MB | 0.140 MB |

RECENT arms are unchanged by construction. The history arms' median per-question upload falls by about two orders of magnitude (RICH 15.083 → 0.157 MB, ≈96×; D2 6.293 → 0.140 MB).

### 2.3 E4 table 4.1 recomputed (headroom over per-type; noise floor 0.0015 / 0.0044)

| network / format / deadline | oracle OLD | per-type OLD | headroom OLD [95% CI] | oracle NEW | per-type NEW | headroom NEW [95% CI] | best static NEW |
|---|---|---|---|---|---|---|---|
| 13.6 Mbit/s / png / 1s s | 0.002 | 0.002 | 0.000 [+0.000, +0.000] ≈ noise | 0.062 | 0.058 | **0.004** [+0.000, +0.008] ≈ noise | `cl-32B-D2` |
| 13.6 Mbit/s / png / 2s s | 0.017 | 0.017 | 0.000 [+0.000, +0.000] ≈ noise | 0.224 | 0.155 | **0.069** [+0.051, +0.087] | `cl-32B-D2` |
| 13.6 Mbit/s / png / 5s s | 0.140 | 0.136 | 0.004 [+0.000, +0.008] ≈ noise | 0.467 | 0.388 | **0.079** [+0.061, +0.098] | `cl-32B-RICH` |
| 13.6 Mbit/s / png / 10s s | 0.333 | 0.265 | 0.067 [+0.051, +0.085] | 0.467 | 0.389 | **0.078** [+0.060, +0.097] | `cl-32B-RICH` |
| 13.6 Mbit/s / raw / 5s s | 0.063 | 0.063 | 0.000 [+0.000, +0.000] ≈ noise | 0.466 | 0.383 | **0.083** [+0.064, +0.102] | `cl-32B-RICH` |
| 13.6 Mbit/s / raw / 10s s | 0.211 | 0.187 | 0.024 [+0.014, +0.034] | 0.467 | 0.389 | **0.078** [+0.060, +0.097] | `cl-32B-RICH` |
| 88 Mbit/s / png / 1s s | 0.038 | 0.037 | 0.001 [+0.000, +0.004] ≈ noise | 0.112 | 0.097 | **0.015** [+0.008, +0.024] | `cl-32B-D2` |
| 88 Mbit/s / png / 2s s | 0.143 | 0.118 | 0.025 [+0.015, +0.036] | 0.231 | 0.153 | **0.078** [+0.059, +0.097] | `cl-32B-D2` |
| 88 Mbit/s / png / 5s s | 0.453 | 0.310 | 0.143 [+0.120, +0.166] | 0.528 | 0.383 | **0.144** [+0.122, +0.169] | `cl-32B-RICH` |
| 88 Mbit/s / png / 10s s | 0.554 | 0.385 | 0.169 [+0.145, +0.195] | 0.554 | 0.385 | **0.169** [+0.145, +0.195] | `cl-32B-RICH` |
| 88 Mbit/s / raw / 2s s | 0.090 | 0.084 | 0.006 [+0.001, +0.012] | 0.231 | 0.153 | **0.078** [+0.059, +0.097] | `cl-32B-D2` |
| 88 Mbit/s / raw / 5s s | 0.279 | 0.246 | 0.033 [+0.022, +0.046] | 0.467 | 0.389 | **0.078** [+0.060, +0.097] | `cl-32B-RICH` |
| 88 Mbit/s / raw / 10s s | 0.543 | 0.343 | 0.200 [+0.172, +0.229] | 0.550 | 0.379 | **0.172** [+0.148, +0.197] | `cl-32B-RICH` |
| 5 Mbit/s / png / 5s s | 0.030 | 0.030 | 0.000 [+0.000, +0.000] ≈ noise | 0.465 | 0.375 | **0.090** [+0.071, +0.109] | `cl-32B-RICH` |
| 5 Mbit/s / png / 10s s | 0.135 | 0.122 | 0.013 [+0.006, +0.021] | 0.467 | 0.389 | **0.078** [+0.060, +0.097] | `cl-32B-RICH` |
| 5 Mbit/s / raw / 10s s | 0.049 | 0.041 | 0.007 [+0.002, +0.014] | 0.467 | 0.389 | **0.078** [+0.060, +0.097] | `cl-32B-RICH` |

Under the original rule, 7 of these 16 cells had headroom at or below the noise floor and the best static configuration was `cl-32B-D2` almost everywhere. Under the corrected rule only the 1 s-deadline cells remain at the floor, and the best static configuration becomes `cl-32B-RICH` in most cells — because once history is held at the cloud, the cheap-upload advantage that made D2 attractive largely disappears.

### 2.4 E4 section 5 classification recomputed, and how much of the representation class survives

| network / format / deadline | rule | n oracle>per-type | capability | evidence | representation | location | interaction | representation share |
|---|---|---|---|---|---|---|---|---|
| 13.6 Mbit/s / png / 5s s | E4 original | 3 | 0 | 1 | 2 | 0 | 0 | 66.7% |
| 13.6 Mbit/s / png / 5s s | **corrected** | 67 | 30 | 4 | 30 | 0 | 3 | 44.8% |
| 13.6 Mbit/s / png / 10s s | E4 original | 57 | 1 | 1 | 44 | 0 | 11 | 77.2% |
| 13.6 Mbit/s / png / 10s s | **corrected** | 66 | 30 | 4 | 29 | 0 | 3 | 43.9% |
| 88 Mbit/s / png / 2s s | E4 original | 21 | 0 | 1 | 0 | 0 | 20 | 0.0% |
| 88 Mbit/s / png / 2s s | **corrected** | 66 | 0 | 1 | 0 | 0 | 65 | 0.0% |
| 88 Mbit/s / png / 5s s | E4 original | 121 | 0 | 14 | 6 | 0 | 101 | 5.0% |
| 88 Mbit/s / png / 5s s | **corrected** | 122 | 24 | 5 | 28 | 0 | 65 | 23.0% |
| 88 Mbit/s / png / 10s s | E4 original | 143 | 50 | 55 | 14 | 0 | 24 | 9.8% |
| 88 Mbit/s / png / 10s s | **corrected** | 143 | 50 | 55 | 14 | 0 | 24 | 9.8% |
| 88 Mbit/s / raw / 10s s | E4 original | 169 | 56 | 59 | 13 | 0 | 41 | 7.7% |
| 88 Mbit/s / raw / 10s s | **corrected** | 145 | 46 | 46 | 18 | 0 | 35 | 12.4% |
| 5 Mbit/s / png / 10s s | E4 original | 11 | 0 | 1 | 8 | 0 | 2 | 72.7% |
| 5 Mbit/s / png / 10s s | **corrected** | 66 | 30 | 4 | 29 | 0 | 3 | 43.9% |

**How much of the representation class survives.** In absolute counts it grows, because the set of questions where the oracle beats per-type grows: summed over the seven cells above, the exclusive representation class goes from 118 to 235 questions. As a *share* of switching questions it roughly halves at low bandwidth (13.6 Mbit/s PNG 10 s: 77.2% → 43.9%; 5 Mbit/s PNG 10 s: 72.7% → 43.9%) and grows at 88 Mbit/s 5 s (5.0% → 23.0%). It remains the largest single exclusive factor in the low-bandwidth cells. The qualitative change is that **capability becomes a real low-bandwidth factor** (0 → 30 questions at 13.6 Mbit/s PNG 5 s and 10 s), which it was not under the original charge, because a 32B request on cloud-held history now fits inside the deadline.

## 3. Setup

| item | definition used in this run |
|---|---|
| policy action | one of the four cells H1 / H2 / K3 / K1 per question (the spec's four interventions: neither, richer evidence, larger model, both) |
| accuracy | fraction of 845 questions answered correctly by the cell the policy chose |
| utility | correct AND (compute + upload + RTT) ≤ deadline, with Part 0's corrected upload rule |
| cross-fitting | 5 folds by video (`KFold(5, shuffle=True, random_state=0)` over 234 videos), seed 0; every vectoriser, scaler, model and threshold fitted inside training folds only; all reported values are pooled out-of-fold |
| budgets | fraction of questions allowed on 32B ∈ {0.25, 0.5, 1.0} × fraction allowed to use RICH ∈ {0.25, 0.5, 1.0} |
| allocation under budget | every policy supplies a score matrix over the four cells and the allocation maximises total predicted score subject to the budgets (LP, HiGHS). This makes 'maximise predicted correctness within the budget' one rule for all policies: the lookup policies' predictor is a training-fold table, the learned policies' is a fitted model. The oracle's predictor is the truth. |
| CI | video-clustered bootstrap, 2,000 resamples, seed 0, resampling videos not questions |
| noise floor | StudyD11 arm F vs K3 and vs H1 (E4 §6) |

**Feature sets** (the spec's information constraint: only what is available before the question):

- **F0** — none (static); intercept only
- **F1** — question category (one-hot) + question time + question-time bin (one-hot)
- **F2** — F1 + question text TF-IDF (min_df=3, max_features=300, sublinear_tf; fitted in training folds only)
- **F3** — F2 + session history: count of earlier questions in the same video, per-category counts, first/last earlier question time, gap to the previous question, mean gap
- **F4** — F2 + StudyD13 4B-RECENT answer-letter logprobs for the current question (top logprob, top-2 margin, entropy over letters, letter mass in top-k, logprob token count); charged the 4B run's cost in setting (b)

*No-leakage audit.* F0-F3 use only question metadata, question text and earlier questions' metadata in the same video: no answer, correctness or model output of any question. F4 uses the 4B RECENT model output for the CURRENT question only (spec-permitted, cost charged).

**Independent-baseline components.** Evidence selector: an R8a-style coverage predictor on F2, target = evidence outside the recent window (`evidence_covered == False` on the RECENT construction), fitted in training folds. Its out-of-fold AUROC is **0.7063** (logreg) / **0.8039** (gbt), which brackets StudyR8a's corrected query-only figure of 0.7885. *That is the right benchmark: StudyR8a's own 2026-11-03 correction states that every Part 1 AUROC against the evidence label was produced by a model fitted on device-failure labels, so the 0.4741 and 0.6247 figures in its Part 1 table must not be used.* Model router variants:

- `always32B` — model router sends every question to 32B
- `conf4B` — 4B RECENT top-letter probability (StudyD13); escalate the least-confident questions, quantile threshold chosen on training folds to maximise training-fold accuracy
- `clsF2` — classifier on F2 predicting K3 > H1

The three router variants are all reported; the strongest at each setting is the baseline, as pre-registered.

**Held-fixed factor for the single-factor policies.** `capability_only` and `evidence_only` hold one factor at the best static cell's value, chosen inside the training folds. In all 5 folds the training-fold best static cell is `K1`, so capability-only varies the model at RICH and evidence-only varies the evidence at 32B.

## 4. Mechanism verification (CLAUDE.md Steps 1-5)

**Step 1, causal chain.** The question is whether a *decidable* signal exists. The chain: if the four cells disagree question by question (FORMULATION's Q(f, w) varying by representation and model), then the per-question best action varies; if some feature observable *before* the question correlates with which cell wins, a policy conditioning on that feature beats a fixed choice; and if the capability and evidence decisions interact, a policy predicting the four cells jointly beats two independent predictors under the same resources. The third link is the specific claim this study exists to test, and it is the one that fails.

**Step 2, instantiate each link.**

| causal link | implementing quantity | value / range in this run | varies as expected? | evidence |
|---|---|---|---|---|
| cells disagree per question | per-target improves / harms counts | cap@RECENT 124/75, ev@4B 57/77, cap@RICH 147/68 | yes | §5 |
| disagreement is not noise | near-identical arm disagreement | 0.59% / 1.47% vs 16-26% between real cells | yes, 10-40x smaller | §5 |
| a pre-question signal exists | out-of-fold AUROC, F1, best target | 0.671 | weakly: 0.53-0.67, CIs above 0.5 for 4 of 5 targets | §6 |
| richer signals add information | AUROC delta of F2/F3/F4 vs F1 | all 30 contrasts' CIs include 0, except 3 where F2/F3/F4 are **worse** | **NO — this link is effectively ABSENT** | §6 |
| capability and evidence interact decidably | combined minus best independent | every CI includes 0 or excludes it negatively | **NO — this link is ABSENT** | §8 |

Two links are ABSENT. Under CLAUDE.md's rule that is a stopping condition **for running a sweep that assumes them**. It is not a stopping condition here, because the absence of those links *is the measured result the study was pre-registered to test*, not an unnoticed defect: the pre-registration names the interpretation rule that fires when F2/F3 add nothing over F1. The consequence is recorded under Rule 2 in §11, and no conclusion below assumes either link.

**Step 3, one-question trace.** Question 28fc07ed…, video 1271720381302919_start_0.0_end_318.135, qt = 122.0 s, time_duration; 88 Mbit/s + 22 ms, PNG, 10 s deadline, under Part 0's corrected upload rule.

| cell | answers | prompt tokens | compute s | upload B (corrected) | network s | total s | correct | deliverable | utility |
|---|---|---|---|---|---|---|---|---|---|
| cl-4B-RECENT | H1 | 12293 | 1.00 | 31,838,730 | 2.92 | 3.92 | no | yes | 0 |
| cl-4B-RICH | H2 | 12491 | 1.04 | 13,419,630 | 1.24 | 2.28 | no | yes | 0 |
| cl-32B-RECENT | K3 | 12293 | 3.03 | 31,838,730 | 2.92 | 5.94 | yes | yes | 1 |
| cl-32B-RICH | K1 | 12491 | 3.73 | 13,419,630 | 1.24 | 4.98 | yes | yes | 1 |

The trace is E4's own (same question, same curves); the upload column is the quantity Part 0 changes. Arithmetic check: 31,838,730 B x 8 / 88e6 = 2.894 s, + 0.022 s RTT = 2.916 s, matching the RECENT rows.

**Step 4, negative control.** Two controls, both pre-specified. (a) **F0**, a feature set with no features: its AUROC is 0.443, 0.415, 0.458, 0.457, 0.430 across the five targets — at or below chance, as an intercept-only model must be, confirming the AUROC machinery is not manufacturing signal. (b) **near-identical arms** (StudyD11 arm F vs K3 / H1): oracle headroom 0.15 pp / 0.44 pp, so when the mechanism (genuinely different inputs or models) is removed, the headroom collapses to under half a point against the 16.7-point oracle-minus-static gap measured here.

**Step 5, alternative explanation.** The headline negative — no policy beats the lookup — has at least three explanations this design cannot separate. (i) The per-question winner genuinely is unpredictable from pre-question information. (ii) It is predictable, but not from *these* features at n = 845: the targets are sparse (57 positives for evidence @ 4B out of 845) and 5-fold cross-fitting leaves ~676 training rows per fold against 300 TF-IDF columns. (iii) A large part of the oracle's margin is the single-draw selection effect: the oracle is credited whenever *any* cell happened to be right, and with four greedy arms that inflates it even if nothing is learnable. StudyO-q4 §2d makes this point for sampled arms (14.6% run-to-run flips exceeding its 13.28 pp oracle gap). **Here it is weaker but not absent:** these are greedy Instruct arms whose near-identical-arm flip rate is only 1.47%, so the oracle's margin is mostly real disagreement between genuinely different inputs rather than resampling noise. Nothing in the data distinguishes (i) from (ii).

## 5. Targets, their joint distribution, and the noise floor

| target | improves (+1) | unchanged (0) | harms (−1) | mean |
|---|---|---|---|---|
| capability @ RECENT (K3−H1) | 124 | 646 | 75 | +0.0580 |
| evidence @ 4B (H2−H1) | 57 | 711 | 77 | -0.0237 |
| both (K1−H1) | 154 | 596 | 95 | +0.0698 |
| capability @ RICH (K1−H2) | 147 | 630 | 68 | +0.0935 |
| evidence @ 32B (K1−K3) | 68 | 719 | 58 | +0.0118 |

**The two kinds of intervention behave differently.** Capability is asymmetric — making the model bigger helps about 1.7-2.2x as often as it hurts (124/75 at RECENT, 147/68 at RICH). Evidence is close to a coin flip — 57/77 at 4B (net negative) and 68/58 at 32B. Both evidence contrasts are `REALLOCATED_BUDGET`, so this is a statement about RICH-vs-RECENT as a package, not about history length.

**Joint distribution over (H1, H2, K3, K1) correctness**, most frequent first:

| pattern H1 H2 K3 K1 | n | reading |
|---|---|---|
| 0 0 0 0 | 370 | no cell answers it |
| 1 1 1 1 | 141 | every cell answers it |
| 0 0 1 1 | 86 | 32B answers it, 4B does not |
| 1 1 0 0 | 37 | 4B answers it, 32B does not |
| 0 0 0 1 | 31 | only 32B+RICH |
| 1 0 1 1 | 28 | only 4B+RICH fails |
| 1 0 0 0 | 27 | only 4B+RECENT |
| 0 1 0 1 | 26 | only the RICH cells |

Of 845 questions, **370 are answered by no cell** and **141 by all four**; only 334 questions are decidable at all. That is the ceiling on any policy: the oracle's 0.5621 is 475/845, and the 141 unanimous questions are free to every policy.

| noise pair | n | disagreement | oracle headroom |
|---|---|---|---|
| F32 vs K3 | 678 | 0.59% | 0.15 pp |
| F4 vs H1 | 678 | 1.47% | 0.44 pp |

## 6. AUROC per target per feature set (diagnostic only), and the lookup-table test

Target = gain > 0 (the intervention improves this question). Out-of-fold, video-clustered CIs.

**logreg**

| target | F0 (control) | F1 | F2 | F3 | F4 |
|---|---|---|---|---|---|
| capability @ RECENT (K3−H1) | 0.443 [0.39, 0.50] | 0.605 [0.55, 0.66] | 0.583 [0.53, 0.63] | 0.573 [0.52, 0.63] | 0.595 [0.54, 0.64] |
| evidence @ 4B (H2−H1) | 0.415 [0.34, 0.49] | 0.666 [0.60, 0.73] | 0.637 [0.57, 0.70] | 0.643 [0.58, 0.70] | 0.648 [0.58, 0.72] |
| both (K1−H1) | 0.458 [0.41, 0.51] | 0.567 [0.51, 0.62] | 0.536 [0.49, 0.59] | 0.533 [0.49, 0.58] | 0.549 [0.50, 0.60] |
| capability @ RICH (K1−H2) | 0.457 [0.41, 0.51] | 0.554 [0.50, 0.61] | 0.483 [0.43, 0.53] | 0.482 [0.43, 0.53] | 0.485 [0.44, 0.53] |
| evidence @ 32B (K1−K3) | 0.430 [0.35, 0.51] | 0.671 [0.61, 0.73] | 0.605 [0.52, 0.68] | 0.621 [0.53, 0.70] | 0.609 [0.52, 0.69] |

**gbt**

| target | F0 (control) | F1 | F2 | F3 | F4 |
|---|---|---|---|---|---|
| capability @ RECENT (K3−H1) | 0.443 [0.39, 0.50] | 0.571 [0.52, 0.63] | 0.590 [0.53, 0.64] | 0.595 [0.54, 0.65] | 0.617 [0.56, 0.67] |
| evidence @ 4B (H2−H1) | 0.415 [0.34, 0.49] | 0.601 [0.53, 0.67] | 0.615 [0.54, 0.69] | 0.604 [0.53, 0.67] | 0.608 [0.54, 0.68] |
| both (K1−H1) | 0.458 [0.41, 0.51] | 0.535 [0.48, 0.59] | 0.537 [0.48, 0.59] | 0.551 [0.50, 0.60] | 0.553 [0.50, 0.60] |
| capability @ RICH (K1−H2) | 0.457 [0.41, 0.51] | 0.528 [0.47, 0.58] | 0.527 [0.48, 0.57] | 0.523 [0.47, 0.57] | 0.526 [0.48, 0.57] |
| evidence @ 32B (K1−K3) | 0.430 [0.35, 0.51] | 0.650 [0.59, 0.71] | 0.588 [0.50, 0.67] | 0.596 [0.51, 0.67] | 0.579 [0.49, 0.65] |

### The lookup-table test: does any feature set add value over F1?

| comparison | learner | target | ΔAUROC | 95% CI | CI excludes 0 |
|---|---|---|---|---|---|
| F2-minus-F1 | logreg | capability @ RECENT (K3−H1) | -0.0218 | [-0.085, +0.039] | no |
| F3-minus-F1 | logreg | capability @ RECENT (K3−H1) | -0.0322 | [-0.097, +0.030] | no |
| F4-minus-F1 | logreg | capability @ RECENT (K3−H1) | -0.0099 | [-0.072, +0.050] | no |
| F2-minus-F1 | logreg | evidence @ 4B (H2−H1) | -0.0290 | [-0.116, +0.065] | no |
| F3-minus-F1 | logreg | evidence @ 4B (H2−H1) | -0.0224 | [-0.107, +0.067] | no |
| F4-minus-F1 | logreg | evidence @ 4B (H2−H1) | -0.0173 | [-0.103, +0.075] | no |
| F2-minus-F1 | logreg | both (K1−H1) | -0.0302 | [-0.095, +0.033] | no |
| F3-minus-F1 | logreg | both (K1−H1) | -0.0337 | [-0.100, +0.031] | no |
| F4-minus-F1 | logreg | both (K1−H1) | -0.0172 | [-0.080, +0.048] | no |
| F2-minus-F1 | logreg | capability @ RICH (K1−H2) | -0.0712 | [-0.139, -0.000] | **yes** (**worse**) |
| F3-minus-F1 | logreg | capability @ RICH (K1−H2) | -0.0722 | [-0.140, -0.004] | **yes** (**worse**) |
| F4-minus-F1 | logreg | capability @ RICH (K1−H2) | -0.0691 | [-0.139, -0.002] | **yes** (**worse**) |
| F2-minus-F1 | logreg | evidence @ 32B (K1−K3) | -0.0658 | [-0.169, +0.022] | no |
| F3-minus-F1 | logreg | evidence @ 32B (K1−K3) | -0.0499 | [-0.152, +0.037] | no |
| F4-minus-F1 | logreg | evidence @ 32B (K1−K3) | -0.0615 | [-0.161, +0.026] | no |
| F2-minus-F1 | gbt | capability @ RECENT (K3−H1) | +0.0192 | [-0.049, +0.087] | no |
| F3-minus-F1 | gbt | capability @ RECENT (K3−H1) | +0.0242 | [-0.041, +0.092] | no |
| F4-minus-F1 | gbt | capability @ RECENT (K3−H1) | +0.0465 | [-0.022, +0.114] | no |
| F2-minus-F1 | gbt | evidence @ 4B (H2−H1) | +0.0135 | [-0.066, +0.100] | no |
| F3-minus-F1 | gbt | evidence @ 4B (H2−H1) | +0.0024 | [-0.079, +0.096] | no |
| F4-minus-F1 | gbt | evidence @ 4B (H2−H1) | +0.0072 | [-0.077, +0.094] | no |
| F2-minus-F1 | gbt | both (K1−H1) | +0.0017 | [-0.068, +0.070] | no |
| F3-minus-F1 | gbt | both (K1−H1) | +0.0157 | [-0.054, +0.085] | no |
| F4-minus-F1 | gbt | both (K1−H1) | +0.0180 | [-0.051, +0.088] | no |
| F2-minus-F1 | gbt | capability @ RICH (K1−H2) | -0.0019 | [-0.064, +0.057] | no |
| F3-minus-F1 | gbt | capability @ RICH (K1−H2) | -0.0056 | [-0.068, +0.053] | no |
| F4-minus-F1 | gbt | capability @ RICH (K1−H2) | -0.0024 | [-0.065, +0.059] | no |
| F2-minus-F1 | gbt | evidence @ 32B (K1−K3) | -0.0612 | [-0.149, +0.020] | no |
| F3-minus-F1 | gbt | evidence @ 32B (K1−K3) | -0.0537 | [-0.144, +0.028] | no |
| F4-minus-F1 | gbt | evidence @ 32B (K1−K3) | -0.0706 | [-0.161, +0.009] | no |

**0 of 30 contrasts show a feature set beating F1 with a CI excluding zero; 3 show one losing to F1 with a CI excluding zero.** Question text, session history and 4B confidence add nothing measurable over category plus question time. By the pre-registered rule: **the decision reduces to a per-type lookup rule.** The three significant losses are all `cap_rich` under logistic regression, consistent with 300 TF-IDF columns overwhelming ~676 training rows rather than with the text carrying anti-information.

## 7. Setting (a) — accuracy under budgets

Each sub-table is one budget cell. `Δ vs per-type` and `fraction of oracle headroom` are paired against the per-type lookup in the same budget cell, with video-bootstrap CIs.

**32B budget 0.25, RICH budget 0.25** — oracle 0.5621, best static 0.3302, per-type 0.3482

| policy | feature set | learner | accuracy | Δ vs per-type [95% CI] | headroom fraction [95% CI] | Δ vs best static [95% CI] |
|---|---|---|---|---|---|---|
| oracle (upper bound) | F1 | logreg | 0.5621 | +0.2139 [+0.185, +0.243] | +1.00 [+1.00, +1.00] | +0.2320 [+0.202, +0.263] |
| best static cell | F1 | logreg | 0.3302 | -0.0180 [-0.042, +0.006] | -0.08 [-0.21, +0.03] | +0.0000 [+0.000, +0.000] |
| per-type lookup | F1 | logreg | 0.3482 | +0.0000 [+0.000, +0.000] | +0.00 [+0.00, +0.00] | +0.0180 [-0.006, +0.042] |
| independent: coverage × always-32B | F1 | logreg | 0.3547 | +0.0065 [-0.018, +0.031] | +0.03 [-0.09, +0.14] | +0.0246 [+0.004, +0.045] |
| independent: coverage × always-32B | F1 | gbt | 0.3527 | +0.0044 [-0.020, +0.029] | +0.02 [-0.10, +0.13] | +0.0225 [+0.002, +0.042] |
| independent: coverage × always-32B | F2 | logreg | 0.3547 | +0.0065 [-0.018, +0.031] | +0.03 [-0.09, +0.14] | +0.0246 [+0.004, +0.045] |
| independent: coverage × always-32B | F2 | gbt | 0.3527 | +0.0044 [-0.020, +0.029] | +0.02 [-0.10, +0.13] | +0.0225 [+0.002, +0.042] |
| independent: coverage × always-32B | F3 | logreg | 0.3547 | +0.0065 [-0.018, +0.031] | +0.03 [-0.09, +0.14] | +0.0246 [+0.004, +0.045] |
| independent: coverage × always-32B | F3 | gbt | 0.3527 | +0.0044 [-0.020, +0.029] | +0.02 [-0.10, +0.13] | +0.0225 [+0.002, +0.042] |
| independent: coverage × always-32B | F4 | logreg | 0.3547 | +0.0065 [-0.018, +0.031] | +0.03 [-0.09, +0.14] | +0.0246 [+0.004, +0.045] |
| independent: coverage × always-32B | F4 | gbt | 0.3527 | +0.0044 [-0.020, +0.029] | +0.02 [-0.10, +0.13] | +0.0225 [+0.002, +0.042] |
| independent: coverage × 4B-confidence | F1 | logreg | 0.3527 | +0.0044 [-0.020, +0.029] | +0.02 [-0.10, +0.13] | +0.0225 [+0.001, +0.045] |
| independent: coverage × 4B-confidence | F1 | gbt | 0.3503 | +0.0021 [-0.022, +0.027] | +0.01 [-0.11, +0.12] | +0.0201 [-0.001, +0.041] |
| independent: coverage × 4B-confidence | F2 | logreg | 0.3527 | +0.0044 [-0.020, +0.029] | +0.02 [-0.10, +0.13] | +0.0225 [+0.001, +0.045] |
| independent: coverage × 4B-confidence | F2 | gbt | 0.3503 | +0.0021 [-0.022, +0.027] | +0.01 [-0.11, +0.12] | +0.0201 [-0.001, +0.041] |
| independent: coverage × 4B-confidence | F3 | logreg | 0.3527 | +0.0044 [-0.020, +0.029] | +0.02 [-0.10, +0.13] | +0.0225 [+0.001, +0.045] |
| independent: coverage × 4B-confidence | F3 | gbt | 0.3503 | +0.0021 [-0.022, +0.027] | +0.01 [-0.11, +0.12] | +0.0201 [-0.001, +0.041] |
| independent: coverage × 4B-confidence | F4 | logreg | 0.3527 | +0.0044 [-0.020, +0.029] | +0.02 [-0.10, +0.13] | +0.0225 [+0.001, +0.045] |
| independent: coverage × 4B-confidence | F4 | gbt | 0.3503 | +0.0021 [-0.022, +0.027] | +0.01 [-0.11, +0.12] | +0.0201 [-0.001, +0.041] |
| independent: coverage × F2 classifier | F1 | logreg | 0.3420 | -0.0062 [-0.029, +0.017] | -0.03 [-0.15, +0.08] | +0.0118 [-0.007, +0.030] |
| independent: coverage × F2 classifier | F1 | gbt | 0.3314 | -0.0169 [-0.041, +0.007] | -0.08 [-0.20, +0.03] | +0.0012 [-0.016, +0.018] |
| independent: coverage × F2 classifier | F2 | logreg | 0.3420 | -0.0062 [-0.029, +0.017] | -0.03 [-0.15, +0.08] | +0.0118 [-0.007, +0.030] |
| independent: coverage × F2 classifier | F2 | gbt | 0.3314 | -0.0169 [-0.041, +0.007] | -0.08 [-0.20, +0.03] | +0.0012 [-0.016, +0.018] |
| independent: coverage × F2 classifier | F3 | logreg | 0.3420 | -0.0062 [-0.029, +0.017] | -0.03 [-0.15, +0.08] | +0.0118 [-0.007, +0.030] |
| independent: coverage × F2 classifier | F3 | gbt | 0.3314 | -0.0169 [-0.041, +0.007] | -0.08 [-0.20, +0.03] | +0.0012 [-0.016, +0.018] |
| independent: coverage × F2 classifier | F4 | logreg | 0.3420 | -0.0062 [-0.029, +0.017] | -0.03 [-0.15, +0.08] | +0.0118 [-0.007, +0.030] |
| independent: coverage × F2 classifier | F4 | gbt | 0.3314 | -0.0169 [-0.041, +0.007] | -0.08 [-0.20, +0.03] | +0.0012 [-0.016, +0.018] |
| capability-only | F1 | logreg | 0.3444 | -0.0038 [-0.029, +0.022] | -0.02 [-0.15, +0.10] | +0.0142 [-0.006, +0.035] |
| capability-only | F1 | gbt | 0.3361 | -0.0121 [-0.035, +0.010] | -0.06 [-0.18, +0.04] | +0.0059 [-0.014, +0.026] |
| capability-only | F2 | logreg | 0.3293 | -0.0189 [-0.044, +0.005] | -0.09 [-0.22, +0.02] | -0.0009 [-0.023, +0.022] |
| capability-only | F2 | gbt | 0.3396 | -0.0086 [-0.032, +0.014] | -0.04 [-0.16, +0.06] | +0.0095 [-0.011, +0.030] |
| capability-only | F3 | logreg | 0.3349 | -0.0133 [-0.038, +0.011] | -0.06 [-0.19, +0.05] | +0.0047 [-0.018, +0.028] |
| capability-only | F3 | gbt | 0.3373 | -0.0109 [-0.033, +0.012] | -0.05 [-0.17, +0.05] | +0.0071 [-0.015, +0.027] |
| capability-only | F4 | logreg | 0.3183 | -0.0299 [-0.055, -0.007] | -0.14 [-0.27, -0.03] | -0.0118 [-0.032, +0.010] |
| capability-only | F4 | gbt | 0.3219 | -0.0263 [-0.050, -0.004] | -0.12 [-0.25, -0.02] | -0.0083 [-0.028, +0.010] |
| evidence-only | F1 | logreg | 0.3441 | -0.0041 [-0.029, +0.021] | -0.02 [-0.15, +0.09] | +0.0139 [-0.007, +0.035] |
| evidence-only | F1 | gbt | 0.3385 | -0.0098 [-0.033, +0.013] | -0.05 [-0.17, +0.06] | +0.0083 [-0.014, +0.029] |
| evidence-only | F2 | logreg | 0.3459 | -0.0024 [-0.028, +0.022] | -0.01 [-0.14, +0.10] | +0.0157 [-0.006, +0.037] |
| evidence-only | F2 | gbt | 0.3420 | -0.0062 [-0.031, +0.018] | -0.03 [-0.16, +0.08] | +0.0118 [-0.011, +0.032] |
| evidence-only | F3 | logreg | 0.3408 | -0.0074 [-0.031, +0.017] | -0.03 [-0.15, +0.08] | +0.0107 [-0.010, +0.031] |
| evidence-only | F3 | gbt | 0.3444 | -0.0038 [-0.029, +0.021] | -0.02 [-0.14, +0.09] | +0.0142 [-0.010, +0.035] |
| evidence-only | F4 | logreg | 0.3322 | -0.0160 [-0.041, +0.008] | -0.07 [-0.21, +0.04] | +0.0021 [-0.020, +0.024] |
| evidence-only | F4 | gbt | 0.3385 | -0.0098 [-0.034, +0.014] | -0.05 [-0.17, +0.06] | +0.0083 [-0.012, +0.028] |
| combined (all four cells) | F1 | logreg | 0.3470 | -0.0012 [-0.019, +0.016] | -0.01 [-0.09, +0.07] | +0.0169 [-0.009, +0.040] |
| combined (all four cells) | F1 | gbt | 0.3456 | -0.0027 [-0.025, +0.020] | -0.01 [-0.12, +0.09] | +0.0154 [-0.010, +0.041] |
| combined (all four cells) | F2 | logreg | 0.3577 | +0.0095 [-0.015, +0.033] | +0.04 [-0.07, +0.15] | +0.0275 [+0.002, +0.052] |
| combined (all four cells) | F2 | gbt | 0.3586 | +0.0104 [-0.016, +0.037] | +0.05 [-0.08, +0.16] | +0.0284 [+0.002, +0.052] |
| combined (all four cells) | F3 | logreg | 0.3589 | +0.0107 [-0.014, +0.035] | +0.05 [-0.07, +0.16] | +0.0287 [+0.005, +0.052] |
| combined (all four cells) | F3 | gbt | 0.3506 | +0.0024 [-0.023, +0.029] | +0.01 [-0.12, +0.13] | +0.0204 [-0.003, +0.043] |
| combined (all four cells) | F4 | logreg | 0.3518 | +0.0036 [-0.021, +0.027] | +0.02 [-0.10, +0.12] | +0.0216 [-0.002, +0.045] |
| combined (all four cells) | F4 | gbt | 0.3612 | +0.0130 [-0.013, +0.040] | +0.06 [-0.07, +0.17] | +0.0311 [+0.008, +0.055] |

**32B budget 0.25, RICH budget 0.5** — oracle 0.5621, best static 0.3302, per-type 0.3456

| policy | feature set | learner | accuracy | Δ vs per-type [95% CI] | headroom fraction [95% CI] | Δ vs best static [95% CI] |
|---|---|---|---|---|---|---|
| oracle (upper bound) | F1 | logreg | 0.5621 | +0.2166 [+0.186, +0.247] | +1.00 [+1.00, +1.00] | +0.2320 [+0.202, +0.263] |
| best static cell | F1 | logreg | 0.3302 | -0.0154 [-0.041, +0.011] | -0.07 [-0.20, +0.05] | +0.0000 [+0.000, +0.000] |
| per-type lookup | F1 | logreg | 0.3456 | +0.0000 [+0.000, +0.000] | +0.00 [+0.00, +0.00] | +0.0154 [-0.011, +0.041] |
| independent: coverage × always-32B | F1 | logreg | 0.3547 | +0.0092 [-0.016, +0.036] | +0.04 [-0.08, +0.16] | +0.0246 [+0.004, +0.045] |
| independent: coverage × always-32B | F1 | gbt | 0.3527 | +0.0071 [-0.019, +0.034] | +0.03 [-0.09, +0.15] | +0.0225 [+0.002, +0.042] |
| independent: coverage × always-32B | F2 | logreg | 0.3547 | +0.0092 [-0.016, +0.036] | +0.04 [-0.08, +0.16] | +0.0246 [+0.004, +0.045] |
| independent: coverage × always-32B | F2 | gbt | 0.3527 | +0.0071 [-0.019, +0.034] | +0.03 [-0.09, +0.15] | +0.0225 [+0.002, +0.042] |
| independent: coverage × always-32B | F3 | logreg | 0.3547 | +0.0092 [-0.016, +0.036] | +0.04 [-0.08, +0.16] | +0.0246 [+0.004, +0.045] |
| independent: coverage × always-32B | F3 | gbt | 0.3527 | +0.0071 [-0.019, +0.034] | +0.03 [-0.09, +0.15] | +0.0225 [+0.002, +0.042] |
| independent: coverage × always-32B | F4 | logreg | 0.3547 | +0.0092 [-0.016, +0.036] | +0.04 [-0.08, +0.16] | +0.0246 [+0.004, +0.045] |
| independent: coverage × always-32B | F4 | gbt | 0.3527 | +0.0071 [-0.019, +0.034] | +0.03 [-0.09, +0.15] | +0.0225 [+0.002, +0.042] |
| independent: coverage × 4B-confidence | F1 | logreg | 0.3527 | +0.0071 [-0.018, +0.035] | +0.03 [-0.09, +0.15] | +0.0225 [+0.001, +0.045] |
| independent: coverage × 4B-confidence | F1 | gbt | 0.3503 | +0.0047 [-0.022, +0.033] | +0.02 [-0.11, +0.14] | +0.0201 [-0.001, +0.041] |
| independent: coverage × 4B-confidence | F2 | logreg | 0.3527 | +0.0071 [-0.018, +0.035] | +0.03 [-0.09, +0.15] | +0.0225 [+0.001, +0.045] |
| independent: coverage × 4B-confidence | F2 | gbt | 0.3503 | +0.0047 [-0.022, +0.033] | +0.02 [-0.11, +0.14] | +0.0201 [-0.001, +0.041] |
| independent: coverage × 4B-confidence | F3 | logreg | 0.3527 | +0.0071 [-0.018, +0.035] | +0.03 [-0.09, +0.15] | +0.0225 [+0.001, +0.045] |
| independent: coverage × 4B-confidence | F3 | gbt | 0.3503 | +0.0047 [-0.022, +0.033] | +0.02 [-0.11, +0.14] | +0.0201 [-0.001, +0.041] |
| independent: coverage × 4B-confidence | F4 | logreg | 0.3527 | +0.0071 [-0.018, +0.035] | +0.03 [-0.09, +0.15] | +0.0225 [+0.001, +0.045] |
| independent: coverage × 4B-confidence | F4 | gbt | 0.3503 | +0.0047 [-0.022, +0.033] | +0.02 [-0.11, +0.14] | +0.0201 [-0.001, +0.041] |
| independent: coverage × F2 classifier | F1 | logreg | 0.3420 | -0.0036 [-0.030, +0.024] | -0.02 [-0.15, +0.10] | +0.0118 [-0.007, +0.030] |
| independent: coverage × F2 classifier | F1 | gbt | 0.3314 | -0.0142 [-0.039, +0.012] | -0.07 [-0.20, +0.05] | +0.0012 [-0.016, +0.018] |
| independent: coverage × F2 classifier | F2 | logreg | 0.3420 | -0.0036 [-0.030, +0.024] | -0.02 [-0.15, +0.10] | +0.0118 [-0.007, +0.030] |
| independent: coverage × F2 classifier | F2 | gbt | 0.3314 | -0.0142 [-0.039, +0.012] | -0.07 [-0.20, +0.05] | +0.0012 [-0.016, +0.018] |
| independent: coverage × F2 classifier | F3 | logreg | 0.3420 | -0.0036 [-0.030, +0.024] | -0.02 [-0.15, +0.10] | +0.0118 [-0.007, +0.030] |
| independent: coverage × F2 classifier | F3 | gbt | 0.3314 | -0.0142 [-0.039, +0.012] | -0.07 [-0.20, +0.05] | +0.0012 [-0.016, +0.018] |
| independent: coverage × F2 classifier | F4 | logreg | 0.3420 | -0.0036 [-0.030, +0.024] | -0.02 [-0.15, +0.10] | +0.0118 [-0.007, +0.030] |
| independent: coverage × F2 classifier | F4 | gbt | 0.3314 | -0.0142 [-0.039, +0.012] | -0.07 [-0.20, +0.05] | +0.0012 [-0.016, +0.018] |
| capability-only | F1 | logreg | 0.3429 | -0.0027 [-0.025, +0.020] | -0.01 [-0.12, +0.09] | +0.0127 [-0.015, +0.040] |
| capability-only | F1 | gbt | 0.3544 | +0.0089 [-0.014, +0.032] | +0.04 [-0.07, +0.14] | +0.0243 [-0.003, +0.052] |
| capability-only | F2 | logreg | 0.3426 | -0.0030 [-0.029, +0.024] | -0.01 [-0.14, +0.10] | +0.0124 [-0.013, +0.039] |
| capability-only | F2 | gbt | 0.3355 | -0.0101 [-0.036, +0.016] | -0.05 [-0.18, +0.07] | +0.0053 [-0.020, +0.030] |
| capability-only | F3 | logreg | 0.3435 | -0.0021 [-0.029, +0.024] | -0.01 [-0.15, +0.10] | +0.0133 [-0.011, +0.039] |
| capability-only | F3 | gbt | 0.3456 | +0.0000 [-0.025, +0.024] | +0.00 [-0.12, +0.10] | +0.0154 [-0.011, +0.040] |
| capability-only | F4 | logreg | 0.3249 | -0.0207 [-0.047, +0.006] | -0.10 [-0.24, +0.03] | -0.0053 [-0.032, +0.020] |
| capability-only | F4 | gbt | 0.3343 | -0.0112 [-0.036, +0.013] | -0.05 [-0.18, +0.06] | +0.0041 [-0.023, +0.029] |
| evidence-only | F1 | logreg | 0.3441 | -0.0015 [-0.028, +0.027] | -0.01 [-0.14, +0.12] | +0.0139 [-0.007, +0.035] |
| evidence-only | F1 | gbt | 0.3385 | -0.0071 [-0.032, +0.020] | -0.03 [-0.17, +0.08] | +0.0083 [-0.014, +0.029] |
| evidence-only | F2 | logreg | 0.3459 | +0.0003 [-0.027, +0.028] | +0.00 [-0.14, +0.12] | +0.0157 [-0.006, +0.037] |
| evidence-only | F2 | gbt | 0.3420 | -0.0036 [-0.029, +0.022] | -0.02 [-0.14, +0.10] | +0.0118 [-0.011, +0.032] |
| evidence-only | F3 | logreg | 0.3408 | -0.0047 [-0.031, +0.023] | -0.02 [-0.15, +0.10] | +0.0107 [-0.010, +0.031] |
| evidence-only | F3 | gbt | 0.3444 | -0.0012 [-0.028, +0.026] | -0.01 [-0.14, +0.11] | +0.0142 [-0.010, +0.035] |
| evidence-only | F4 | logreg | 0.3322 | -0.0133 [-0.040, +0.013] | -0.06 [-0.20, +0.06] | +0.0021 [-0.020, +0.024] |
| evidence-only | F4 | gbt | 0.3385 | -0.0071 [-0.033, +0.019] | -0.03 [-0.17, +0.08] | +0.0083 [-0.012, +0.028] |
| combined (all four cells) | F1 | logreg | 0.3503 | +0.0047 [-0.015, +0.024] | +0.02 [-0.07, +0.10] | +0.0201 [-0.007, +0.046] |
| combined (all four cells) | F1 | gbt | 0.3432 | -0.0024 [-0.025, +0.020] | -0.01 [-0.12, +0.09] | +0.0130 [-0.013, +0.038] |
| combined (all four cells) | F2 | logreg | 0.3491 | +0.0036 [-0.022, +0.029] | +0.02 [-0.11, +0.13] | +0.0189 [-0.006, +0.044] |
| combined (all four cells) | F2 | gbt | 0.3538 | +0.0083 [-0.020, +0.035] | +0.04 [-0.10, +0.15] | +0.0237 [-0.002, +0.049] |
| combined (all four cells) | F3 | logreg | 0.3482 | +0.0027 [-0.023, +0.029] | +0.01 [-0.11, +0.12] | +0.0180 [-0.007, +0.044] |
| combined (all four cells) | F3 | gbt | 0.3518 | +0.0062 [-0.022, +0.034] | +0.03 [-0.11, +0.15] | +0.0216 [-0.002, +0.046] |
| combined (all four cells) | F4 | logreg | 0.3396 | -0.0059 [-0.031, +0.019] | -0.03 [-0.16, +0.08] | +0.0095 [-0.015, +0.034] |
| combined (all four cells) | F4 | gbt | 0.3530 | +0.0074 [-0.020, +0.035] | +0.03 [-0.10, +0.15] | +0.0228 [-0.003, +0.047] |

**32B budget 0.25, RICH budget 1** — oracle 0.5621, best static 0.3290, per-type 0.3467

| policy | feature set | learner | accuracy | Δ vs per-type [95% CI] | headroom fraction [95% CI] | Δ vs best static [95% CI] |
|---|---|---|---|---|---|---|
| oracle (upper bound) | F1 | logreg | 0.5621 | +0.2154 [+0.185, +0.246] | +1.00 [+1.00, +1.00] | +0.2331 [+0.203, +0.264] |
| best static cell | F1 | logreg | 0.3290 | -0.0178 [-0.043, +0.009] | -0.08 [-0.21, +0.04] | +0.0000 [+0.000, +0.000] |
| per-type lookup | F1 | logreg | 0.3467 | +0.0000 [+0.000, +0.000] | +0.00 [+0.00, +0.00] | +0.0178 [-0.009, +0.043] |
| independent: coverage × always-32B | F1 | logreg | 0.3547 | +0.0080 [-0.018, +0.035] | +0.04 [-0.09, +0.15] | +0.0257 [+0.006, +0.046] |
| independent: coverage × always-32B | F1 | gbt | 0.3527 | +0.0059 [-0.021, +0.034] | +0.03 [-0.10, +0.15] | +0.0237 [+0.005, +0.042] |
| independent: coverage × always-32B | F2 | logreg | 0.3547 | +0.0080 [-0.018, +0.035] | +0.04 [-0.09, +0.15] | +0.0257 [+0.006, +0.046] |
| independent: coverage × always-32B | F2 | gbt | 0.3527 | +0.0059 [-0.021, +0.034] | +0.03 [-0.10, +0.15] | +0.0237 [+0.005, +0.042] |
| independent: coverage × always-32B | F3 | logreg | 0.3547 | +0.0080 [-0.018, +0.035] | +0.04 [-0.09, +0.15] | +0.0257 [+0.006, +0.046] |
| independent: coverage × always-32B | F3 | gbt | 0.3527 | +0.0059 [-0.021, +0.034] | +0.03 [-0.10, +0.15] | +0.0237 [+0.005, +0.042] |
| independent: coverage × always-32B | F4 | logreg | 0.3547 | +0.0080 [-0.018, +0.035] | +0.04 [-0.09, +0.15] | +0.0257 [+0.006, +0.046] |
| independent: coverage × always-32B | F4 | gbt | 0.3527 | +0.0059 [-0.021, +0.034] | +0.03 [-0.10, +0.15] | +0.0237 [+0.005, +0.042] |
| independent: coverage × 4B-confidence | F1 | logreg | 0.3527 | +0.0059 [-0.020, +0.034] | +0.03 [-0.10, +0.14] | +0.0237 [+0.002, +0.046] |
| independent: coverage × 4B-confidence | F1 | gbt | 0.3503 | +0.0036 [-0.023, +0.032] | +0.02 [-0.12, +0.14] | +0.0213 [+0.001, +0.041] |
| independent: coverage × 4B-confidence | F2 | logreg | 0.3527 | +0.0059 [-0.020, +0.034] | +0.03 [-0.10, +0.14] | +0.0237 [+0.002, +0.046] |
| independent: coverage × 4B-confidence | F2 | gbt | 0.3503 | +0.0036 [-0.023, +0.032] | +0.02 [-0.12, +0.14] | +0.0213 [+0.001, +0.041] |
| independent: coverage × 4B-confidence | F3 | logreg | 0.3527 | +0.0059 [-0.020, +0.034] | +0.03 [-0.10, +0.14] | +0.0237 [+0.002, +0.046] |
| independent: coverage × 4B-confidence | F3 | gbt | 0.3503 | +0.0036 [-0.023, +0.032] | +0.02 [-0.12, +0.14] | +0.0213 [+0.001, +0.041] |
| independent: coverage × 4B-confidence | F4 | logreg | 0.3527 | +0.0059 [-0.020, +0.034] | +0.03 [-0.10, +0.14] | +0.0237 [+0.002, +0.046] |
| independent: coverage × 4B-confidence | F4 | gbt | 0.3503 | +0.0036 [-0.023, +0.032] | +0.02 [-0.12, +0.14] | +0.0213 [+0.001, +0.041] |
| independent: coverage × F2 classifier | F1 | logreg | 0.3420 | -0.0047 [-0.031, +0.023] | -0.02 [-0.15, +0.10] | +0.0130 [-0.006, +0.032] |
| independent: coverage × F2 classifier | F1 | gbt | 0.3314 | -0.0154 [-0.041, +0.011] | -0.07 [-0.21, +0.05] | +0.0024 [-0.014, +0.018] |
| independent: coverage × F2 classifier | F2 | logreg | 0.3420 | -0.0047 [-0.031, +0.023] | -0.02 [-0.15, +0.10] | +0.0130 [-0.006, +0.032] |
| independent: coverage × F2 classifier | F2 | gbt | 0.3314 | -0.0154 [-0.041, +0.011] | -0.07 [-0.21, +0.05] | +0.0024 [-0.014, +0.018] |
| independent: coverage × F2 classifier | F3 | logreg | 0.3420 | -0.0047 [-0.031, +0.023] | -0.02 [-0.15, +0.10] | +0.0130 [-0.006, +0.032] |
| independent: coverage × F2 classifier | F3 | gbt | 0.3314 | -0.0154 [-0.041, +0.011] | -0.07 [-0.21, +0.05] | +0.0024 [-0.014, +0.018] |
| independent: coverage × F2 classifier | F4 | logreg | 0.3420 | -0.0047 [-0.031, +0.023] | -0.02 [-0.15, +0.10] | +0.0130 [-0.006, +0.032] |
| independent: coverage × F2 classifier | F4 | gbt | 0.3314 | -0.0154 [-0.041, +0.011] | -0.07 [-0.21, +0.05] | +0.0024 [-0.014, +0.018] |
| capability-only | F1 | logreg | 0.3231 | -0.0237 [-0.048, +0.000] | -0.11 [-0.24, +0.00] | -0.0059 [-0.038, +0.025] |
| capability-only | F1 | gbt | 0.3373 | -0.0095 [-0.033, +0.014] | -0.04 [-0.17, +0.06] | +0.0083 [-0.021, +0.036] |
| capability-only | F2 | logreg | 0.3266 | -0.0201 [-0.045, +0.006] | -0.09 [-0.23, +0.02] | -0.0024 [-0.028, +0.024] |
| capability-only | F2 | gbt | 0.3254 | -0.0213 [-0.048, +0.004] | -0.10 [-0.24, +0.02] | -0.0036 [-0.034, +0.026] |
| capability-only | F3 | logreg | 0.3254 | -0.0213 [-0.048, +0.006] | -0.10 [-0.24, +0.03] | -0.0036 [-0.031, +0.025] |
| capability-only | F3 | gbt | 0.3219 | -0.0249 [-0.051, +0.001] | -0.12 [-0.26, +0.00] | -0.0071 [-0.037, +0.022] |
| capability-only | F4 | logreg | 0.3251 | -0.0216 [-0.048, +0.004] | -0.10 [-0.24, +0.02] | -0.0038 [-0.032, +0.022] |
| capability-only | F4 | gbt | 0.3287 | -0.0180 [-0.045, +0.006] | -0.08 [-0.23, +0.03] | -0.0003 [-0.030, +0.028] |
| evidence-only | F1 | logreg | 0.3441 | -0.0027 [-0.029, +0.026] | -0.01 [-0.15, +0.11] | +0.0151 [-0.006, +0.037] |
| evidence-only | F1 | gbt | 0.3385 | -0.0083 [-0.033, +0.019] | -0.04 [-0.17, +0.08] | +0.0095 [-0.012, +0.029] |
| evidence-only | F2 | logreg | 0.3459 | -0.0009 [-0.028, +0.026] | -0.00 [-0.14, +0.12] | +0.0169 [-0.004, +0.039] |
| evidence-only | F2 | gbt | 0.3420 | -0.0047 [-0.031, +0.021] | -0.02 [-0.15, +0.10] | +0.0130 [-0.008, +0.033] |
| evidence-only | F3 | logreg | 0.3408 | -0.0059 [-0.032, +0.021] | -0.03 [-0.16, +0.09] | +0.0118 [-0.008, +0.032] |
| evidence-only | F3 | gbt | 0.3444 | -0.0024 [-0.029, +0.025] | -0.01 [-0.14, +0.11] | +0.0154 [-0.008, +0.036] |
| evidence-only | F4 | logreg | 0.3322 | -0.0145 [-0.041, +0.013] | -0.07 [-0.21, +0.06] | +0.0033 [-0.017, +0.025] |
| evidence-only | F4 | gbt | 0.3385 | -0.0083 [-0.035, +0.018] | -0.04 [-0.18, +0.08] | +0.0095 [-0.011, +0.029] |
| combined (all four cells) | F1 | logreg | 0.3503 | +0.0036 [-0.016, +0.022] | +0.02 [-0.08, +0.10] | +0.0213 [-0.006, +0.047] |
| combined (all four cells) | F1 | gbt | 0.3432 | -0.0036 [-0.026, +0.019] | -0.02 [-0.13, +0.08] | +0.0142 [-0.011, +0.039] |
| combined (all four cells) | F2 | logreg | 0.3491 | +0.0024 [-0.023, +0.028] | +0.01 [-0.12, +0.12] | +0.0201 [-0.005, +0.044] |
| combined (all four cells) | F2 | gbt | 0.3538 | +0.0071 [-0.021, +0.034] | +0.03 [-0.11, +0.15] | +0.0249 [-0.001, +0.049] |
| combined (all four cells) | F3 | logreg | 0.3482 | +0.0015 [-0.024, +0.027] | +0.01 [-0.12, +0.12] | +0.0192 [-0.006, +0.045] |
| combined (all four cells) | F3 | gbt | 0.3518 | +0.0050 [-0.023, +0.033] | +0.02 [-0.12, +0.14] | +0.0228 [-0.002, +0.047] |
| combined (all four cells) | F4 | logreg | 0.3396 | -0.0071 [-0.032, +0.017] | -0.03 [-0.16, +0.07] | +0.0107 [-0.013, +0.033] |
| combined (all four cells) | F4 | gbt | 0.3530 | +0.0062 [-0.021, +0.034] | +0.03 [-0.11, +0.15] | +0.0240 [-0.001, +0.049] |

**32B budget 0.5, RICH budget 0.25** — oracle 0.5621, best static 0.3432, per-type 0.3811

| policy | feature set | learner | accuracy | Δ vs per-type [95% CI] | headroom fraction [95% CI] | Δ vs best static [95% CI] |
|---|---|---|---|---|---|---|
| oracle (upper bound) | F1 | logreg | 0.5621 | +0.1811 [+0.155, +0.208] | +1.00 [+1.00, +1.00] | +0.2189 [+0.190, +0.249] |
| best static cell | F1 | logreg | 0.3432 | -0.0379 [-0.066, -0.010] | -0.21 [-0.40, -0.05] | +0.0000 [+0.000, +0.000] |
| per-type lookup | F1 | logreg | 0.3811 | +0.0000 [+0.000, +0.000] | +0.00 [+0.00, +0.00] | +0.0379 [+0.010, +0.066] |
| independent: coverage × always-32B | F1 | logreg | 0.3680 | -0.0130 [-0.041, +0.014] | -0.07 [-0.25, +0.07] | +0.0249 [+0.001, +0.049] |
| independent: coverage × always-32B | F1 | gbt | 0.3728 | -0.0083 [-0.036, +0.020] | -0.05 [-0.22, +0.10] | +0.0296 [+0.004, +0.056] |
| independent: coverage × always-32B | F2 | logreg | 0.3680 | -0.0130 [-0.041, +0.014] | -0.07 [-0.25, +0.07] | +0.0249 [+0.001, +0.049] |
| independent: coverage × always-32B | F2 | gbt | 0.3728 | -0.0083 [-0.036, +0.020] | -0.05 [-0.22, +0.10] | +0.0296 [+0.004, +0.056] |
| independent: coverage × always-32B | F3 | logreg | 0.3680 | -0.0130 [-0.041, +0.014] | -0.07 [-0.25, +0.07] | +0.0249 [+0.001, +0.049] |
| independent: coverage × always-32B | F3 | gbt | 0.3728 | -0.0083 [-0.036, +0.020] | -0.05 [-0.22, +0.10] | +0.0296 [+0.004, +0.056] |
| independent: coverage × always-32B | F4 | logreg | 0.3680 | -0.0130 [-0.041, +0.014] | -0.07 [-0.25, +0.07] | +0.0249 [+0.001, +0.049] |
| independent: coverage × always-32B | F4 | gbt | 0.3728 | -0.0083 [-0.036, +0.020] | -0.05 [-0.22, +0.10] | +0.0296 [+0.004, +0.056] |
| independent: coverage × 4B-confidence | F1 | logreg | 0.3657 | -0.0154 [-0.042, +0.012] | -0.08 [-0.25, +0.06] | +0.0225 [+0.000, +0.045] |
| independent: coverage × 4B-confidence | F1 | gbt | 0.3716 | -0.0095 [-0.036, +0.018] | -0.05 [-0.22, +0.09] | +0.0284 [+0.003, +0.055] |
| independent: coverage × 4B-confidence | F2 | logreg | 0.3657 | -0.0154 [-0.042, +0.012] | -0.08 [-0.25, +0.06] | +0.0225 [+0.000, +0.045] |
| independent: coverage × 4B-confidence | F2 | gbt | 0.3716 | -0.0095 [-0.036, +0.018] | -0.05 [-0.22, +0.09] | +0.0284 [+0.003, +0.055] |
| independent: coverage × 4B-confidence | F3 | logreg | 0.3657 | -0.0154 [-0.042, +0.012] | -0.08 [-0.25, +0.06] | +0.0225 [+0.000, +0.045] |
| independent: coverage × 4B-confidence | F3 | gbt | 0.3716 | -0.0095 [-0.036, +0.018] | -0.05 [-0.22, +0.09] | +0.0284 [+0.003, +0.055] |
| independent: coverage × 4B-confidence | F4 | logreg | 0.3657 | -0.0154 [-0.042, +0.012] | -0.08 [-0.25, +0.06] | +0.0225 [+0.000, +0.045] |
| independent: coverage × 4B-confidence | F4 | gbt | 0.3716 | -0.0095 [-0.036, +0.018] | -0.05 [-0.22, +0.09] | +0.0284 [+0.003, +0.055] |
| independent: coverage × F2 classifier | F1 | logreg | 0.3420 | -0.0391 [-0.064, -0.014] | -0.22 [-0.38, -0.07] | -0.0012 [-0.023, +0.021] |
| independent: coverage × F2 classifier | F1 | gbt | 0.3314 | -0.0497 [-0.078, -0.022] | -0.27 [-0.47, -0.11] | -0.0118 [-0.036, +0.011] |
| independent: coverage × F2 classifier | F2 | logreg | 0.3420 | -0.0391 [-0.064, -0.014] | -0.22 [-0.38, -0.07] | -0.0012 [-0.023, +0.021] |
| independent: coverage × F2 classifier | F2 | gbt | 0.3314 | -0.0497 [-0.078, -0.022] | -0.27 [-0.47, -0.11] | -0.0118 [-0.036, +0.011] |
| independent: coverage × F2 classifier | F3 | logreg | 0.3420 | -0.0391 [-0.064, -0.014] | -0.22 [-0.38, -0.07] | -0.0012 [-0.023, +0.021] |
| independent: coverage × F2 classifier | F3 | gbt | 0.3314 | -0.0497 [-0.078, -0.022] | -0.27 [-0.47, -0.11] | -0.0118 [-0.036, +0.011] |
| independent: coverage × F2 classifier | F4 | logreg | 0.3420 | -0.0391 [-0.064, -0.014] | -0.22 [-0.38, -0.07] | -0.0012 [-0.023, +0.021] |
| independent: coverage × F2 classifier | F4 | gbt | 0.3314 | -0.0497 [-0.078, -0.022] | -0.27 [-0.47, -0.11] | -0.0118 [-0.036, +0.011] |
| capability-only | F1 | logreg | 0.3444 | -0.0367 [-0.066, -0.007] | -0.20 [-0.40, -0.03] | +0.0012 [-0.021, +0.022] |
| capability-only | F1 | gbt | 0.3361 | -0.0450 [-0.072, -0.019] | -0.25 [-0.43, -0.10] | -0.0071 [-0.029, +0.014] |
| capability-only | F2 | logreg | 0.3293 | -0.0518 [-0.081, -0.023] | -0.29 [-0.48, -0.12] | -0.0139 [-0.040, +0.013] |
| capability-only | F2 | gbt | 0.3396 | -0.0414 [-0.070, -0.013] | -0.23 [-0.41, -0.07] | -0.0036 [-0.029, +0.021] |
| capability-only | F3 | logreg | 0.3349 | -0.0462 [-0.075, -0.016] | -0.25 [-0.45, -0.08] | -0.0083 [-0.035, +0.019] |
| capability-only | F3 | gbt | 0.3373 | -0.0438 [-0.071, -0.016] | -0.24 [-0.43, -0.08] | -0.0059 [-0.031, +0.018] |
| capability-only | F4 | logreg | 0.3183 | -0.0627 [-0.092, -0.034] | -0.35 [-0.55, -0.17] | -0.0249 [-0.050, +0.000] |
| capability-only | F4 | gbt | 0.3219 | -0.0592 [-0.088, -0.031] | -0.33 [-0.52, -0.16] | -0.0213 [-0.045, +0.001] |
| evidence-only | F1 | logreg | 0.3586 | -0.0225 [-0.047, +0.001] | -0.12 [-0.28, +0.01] | +0.0154 [-0.010, +0.042] |
| evidence-only | F1 | gbt | 0.3734 | -0.0077 [-0.033, +0.015] | -0.04 [-0.19, +0.08] | +0.0302 [+0.002, +0.056] |
| evidence-only | F2 | logreg | 0.3657 | -0.0154 [-0.045, +0.014] | -0.08 [-0.27, +0.07] | +0.0225 [-0.005, +0.050] |
| evidence-only | F2 | gbt | 0.3680 | -0.0130 [-0.042, +0.014] | -0.07 [-0.24, +0.07] | +0.0249 [-0.001, +0.050] |
| evidence-only | F3 | logreg | 0.3592 | -0.0219 [-0.051, +0.005] | -0.12 [-0.31, +0.02] | +0.0160 [-0.011, +0.045] |
| evidence-only | F3 | gbt | 0.3657 | -0.0154 [-0.042, +0.010] | -0.08 [-0.25, +0.05] | +0.0225 [-0.004, +0.047] |
| evidence-only | F4 | logreg | 0.3633 | -0.0178 [-0.046, +0.010] | -0.10 [-0.28, +0.05] | +0.0201 [-0.009, +0.048] |
| evidence-only | F4 | gbt | 0.3598 | -0.0213 [-0.050, +0.005] | -0.12 [-0.30, +0.03] | +0.0166 [-0.011, +0.043] |
| combined (all four cells) | F1 | logreg | 0.3716 | -0.0095 [-0.025, +0.006] | -0.05 [-0.15, +0.03] | +0.0284 [+0.000, +0.058] |
| combined (all four cells) | F1 | gbt | 0.3686 | -0.0124 [-0.035, +0.010] | -0.07 [-0.20, +0.05] | +0.0254 [-0.002, +0.053] |
| combined (all four cells) | F2 | logreg | 0.3728 | -0.0083 [-0.033, +0.017] | -0.05 [-0.20, +0.09] | +0.0296 [+0.002, +0.058] |
| combined (all four cells) | F2 | gbt | 0.3672 | -0.0139 [-0.043, +0.016] | -0.08 [-0.26, +0.08] | +0.0240 [-0.004, +0.052] |
| combined (all four cells) | F3 | logreg | 0.3781 | -0.0030 [-0.028, +0.022] | -0.02 [-0.17, +0.12] | +0.0349 [+0.008, +0.063] |
| combined (all four cells) | F3 | gbt | 0.3609 | -0.0201 [-0.047, +0.006] | -0.11 [-0.28, +0.03] | +0.0178 [-0.009, +0.046] |
| combined (all four cells) | F4 | logreg | 0.3749 | -0.0062 [-0.033, +0.022] | -0.03 [-0.20, +0.11] | +0.0317 [+0.002, +0.060] |
| combined (all four cells) | F4 | gbt | 0.3694 | -0.0117 [-0.039, +0.017] | -0.06 [-0.24, +0.08] | +0.0262 [-0.001, +0.053] |

**32B budget 0.5, RICH budget 0.5** — oracle 0.5621, best static 0.3467, per-type 0.3805

| policy | feature set | learner | accuracy | Δ vs per-type [95% CI] | headroom fraction [95% CI] | Δ vs best static [95% CI] |
|---|---|---|---|---|---|---|
| oracle (upper bound) | F1 | logreg | 0.5621 | +0.1817 [+0.154, +0.209] | +1.00 [+1.00, +1.00] | +0.2154 [+0.185, +0.246] |
| best static cell | F1 | logreg | 0.3467 | -0.0337 [-0.062, -0.006] | -0.19 [-0.37, -0.03] | +0.0000 [+0.000, +0.000] |
| per-type lookup | F1 | logreg | 0.3805 | +0.0000 [+0.000, +0.000] | +0.00 [+0.00, +0.00] | +0.0337 [+0.006, +0.062] |
| independent: coverage × always-32B | F1 | logreg | 0.3680 | -0.0124 [-0.041, +0.016] | -0.07 [-0.25, +0.08] | +0.0213 [-0.007, +0.050] |
| independent: coverage × always-32B | F1 | gbt | 0.3728 | -0.0077 [-0.037, +0.022] | -0.04 [-0.22, +0.11] | +0.0260 [-0.002, +0.054] |
| independent: coverage × always-32B | F2 | logreg | 0.3680 | -0.0124 [-0.041, +0.016] | -0.07 [-0.25, +0.08] | +0.0213 [-0.007, +0.050] |
| independent: coverage × always-32B | F2 | gbt | 0.3728 | -0.0077 [-0.037, +0.022] | -0.04 [-0.22, +0.11] | +0.0260 [-0.002, +0.054] |
| independent: coverage × always-32B | F3 | logreg | 0.3680 | -0.0124 [-0.041, +0.016] | -0.07 [-0.25, +0.08] | +0.0213 [-0.007, +0.050] |
| independent: coverage × always-32B | F3 | gbt | 0.3728 | -0.0077 [-0.037, +0.022] | -0.04 [-0.22, +0.11] | +0.0260 [-0.002, +0.054] |
| independent: coverage × always-32B | F4 | logreg | 0.3680 | -0.0124 [-0.041, +0.016] | -0.07 [-0.25, +0.08] | +0.0213 [-0.007, +0.050] |
| independent: coverage × always-32B | F4 | gbt | 0.3728 | -0.0077 [-0.037, +0.022] | -0.04 [-0.22, +0.11] | +0.0260 [-0.002, +0.054] |
| independent: coverage × 4B-confidence | F1 | logreg | 0.3657 | -0.0148 [-0.042, +0.012] | -0.08 [-0.25, +0.06] | +0.0189 [-0.009, +0.047] |
| independent: coverage × 4B-confidence | F1 | gbt | 0.3716 | -0.0089 [-0.036, +0.019] | -0.05 [-0.22, +0.10] | +0.0249 [-0.002, +0.053] |
| independent: coverage × 4B-confidence | F2 | logreg | 0.3657 | -0.0148 [-0.042, +0.012] | -0.08 [-0.25, +0.06] | +0.0189 [-0.009, +0.047] |
| independent: coverage × 4B-confidence | F2 | gbt | 0.3716 | -0.0089 [-0.036, +0.019] | -0.05 [-0.22, +0.10] | +0.0249 [-0.002, +0.053] |
| independent: coverage × 4B-confidence | F3 | logreg | 0.3657 | -0.0148 [-0.042, +0.012] | -0.08 [-0.25, +0.06] | +0.0189 [-0.009, +0.047] |
| independent: coverage × 4B-confidence | F3 | gbt | 0.3716 | -0.0089 [-0.036, +0.019] | -0.05 [-0.22, +0.10] | +0.0249 [-0.002, +0.053] |
| independent: coverage × 4B-confidence | F4 | logreg | 0.3657 | -0.0148 [-0.042, +0.012] | -0.08 [-0.25, +0.06] | +0.0189 [-0.009, +0.047] |
| independent: coverage × 4B-confidence | F4 | gbt | 0.3716 | -0.0089 [-0.036, +0.019] | -0.05 [-0.22, +0.10] | +0.0249 [-0.002, +0.053] |
| independent: coverage × F2 classifier | F1 | logreg | 0.3420 | -0.0385 [-0.065, -0.011] | -0.21 [-0.39, -0.05] | -0.0047 [-0.031, +0.020] |
| independent: coverage × F2 classifier | F1 | gbt | 0.3314 | -0.0491 [-0.077, -0.020] | -0.27 [-0.46, -0.10] | -0.0154 [-0.042, +0.009] |
| independent: coverage × F2 classifier | F2 | logreg | 0.3420 | -0.0385 [-0.065, -0.011] | -0.21 [-0.39, -0.05] | -0.0047 [-0.031, +0.020] |
| independent: coverage × F2 classifier | F2 | gbt | 0.3314 | -0.0491 [-0.077, -0.020] | -0.27 [-0.46, -0.10] | -0.0154 [-0.042, +0.009] |
| independent: coverage × F2 classifier | F3 | logreg | 0.3420 | -0.0385 [-0.065, -0.011] | -0.21 [-0.39, -0.05] | -0.0047 [-0.031, +0.020] |
| independent: coverage × F2 classifier | F3 | gbt | 0.3314 | -0.0491 [-0.077, -0.020] | -0.27 [-0.46, -0.10] | -0.0154 [-0.042, +0.009] |
| independent: coverage × F2 classifier | F4 | logreg | 0.3420 | -0.0385 [-0.065, -0.011] | -0.21 [-0.39, -0.05] | -0.0047 [-0.031, +0.020] |
| independent: coverage × F2 classifier | F4 | gbt | 0.3314 | -0.0491 [-0.077, -0.020] | -0.27 [-0.46, -0.10] | -0.0154 [-0.042, +0.009] |
| capability-only | F1 | logreg | 0.3645 | -0.0160 [-0.040, +0.008] | -0.09 [-0.24, +0.04] | +0.0178 [-0.009, +0.045] |
| capability-only | F1 | gbt | 0.3675 | -0.0130 [-0.038, +0.011] | -0.07 [-0.22, +0.06] | +0.0207 [-0.007, +0.048] |
| capability-only | F2 | logreg | 0.3485 | -0.0320 [-0.060, -0.005] | -0.18 [-0.36, -0.03] | +0.0018 [-0.027, +0.031] |
| capability-only | F2 | gbt | 0.3521 | -0.0284 [-0.057, -0.001] | -0.16 [-0.35, -0.00] | +0.0053 [-0.025, +0.033] |
| capability-only | F3 | logreg | 0.3515 | -0.0290 [-0.057, +0.000] | -0.16 [-0.34, +0.00] | +0.0047 [-0.024, +0.035] |
| capability-only | F3 | gbt | 0.3503 | -0.0302 [-0.057, -0.005] | -0.17 [-0.35, -0.02] | +0.0036 [-0.025, +0.030] |
| capability-only | F4 | logreg | 0.3337 | -0.0467 [-0.075, -0.017] | -0.26 [-0.45, -0.09] | -0.0130 [-0.042, +0.017] |
| capability-only | F4 | gbt | 0.3479 | -0.0325 [-0.059, -0.006] | -0.18 [-0.35, -0.03] | +0.0012 [-0.028, +0.028] |
| evidence-only | F1 | logreg | 0.3615 | -0.0189 [-0.044, +0.006] | -0.10 [-0.26, +0.03] | +0.0148 [-0.012, +0.042] |
| evidence-only | F1 | gbt | 0.3781 | -0.0024 [-0.027, +0.021] | -0.01 [-0.16, +0.11] | +0.0314 [+0.003, +0.062] |
| evidence-only | F2 | logreg | 0.3645 | -0.0160 [-0.044, +0.013] | -0.09 [-0.27, +0.07] | +0.0178 [-0.013, +0.047] |
| evidence-only | F2 | gbt | 0.3669 | -0.0136 [-0.041, +0.012] | -0.07 [-0.24, +0.07] | +0.0201 [-0.007, +0.046] |
| evidence-only | F3 | logreg | 0.3592 | -0.0213 [-0.048, +0.006] | -0.12 [-0.29, +0.03] | +0.0124 [-0.018, +0.044] |
| evidence-only | F3 | gbt | 0.3657 | -0.0148 [-0.040, +0.011] | -0.08 [-0.24, +0.06] | +0.0189 [-0.008, +0.044] |
| evidence-only | F4 | logreg | 0.3633 | -0.0172 [-0.045, +0.011] | -0.09 [-0.28, +0.06] | +0.0166 [-0.013, +0.047] |
| evidence-only | F4 | gbt | 0.3598 | -0.0207 [-0.049, +0.006] | -0.11 [-0.30, +0.03] | +0.0130 [-0.014, +0.037] |
| combined (all four cells) | F1 | logreg | 0.3710 | -0.0095 [-0.027, +0.009] | -0.05 [-0.16, +0.05] | +0.0243 [-0.003, +0.051] |
| combined (all four cells) | F1 | gbt | 0.3716 | -0.0089 [-0.030, +0.013] | -0.05 [-0.18, +0.07] | +0.0249 [-0.004, +0.054] |
| combined (all four cells) | F2 | logreg | 0.3698 | -0.0107 [-0.038, +0.016] | -0.06 [-0.23, +0.08] | +0.0231 [-0.007, +0.055] |
| combined (all four cells) | F2 | gbt | 0.3680 | -0.0124 [-0.041, +0.015] | -0.07 [-0.25, +0.08] | +0.0213 [-0.009, +0.051] |
| combined (all four cells) | F3 | logreg | 0.3710 | -0.0095 [-0.037, +0.020] | -0.05 [-0.22, +0.10] | +0.0243 [-0.005, +0.054] |
| combined (all four cells) | F3 | gbt | 0.3728 | -0.0077 [-0.036, +0.020] | -0.04 [-0.21, +0.10] | +0.0260 [-0.005, +0.056] |
| combined (all four cells) | F4 | logreg | 0.3633 | -0.0172 [-0.046, +0.011] | -0.09 [-0.28, +0.06] | +0.0166 [-0.014, +0.046] |
| combined (all four cells) | F4 | gbt | 0.3633 | -0.0172 [-0.045, +0.010] | -0.09 [-0.28, +0.05] | +0.0166 [-0.013, +0.046] |

**32B budget 0.5, RICH budget 1** — oracle 0.5621, best static 0.3438, per-type 0.3828

| policy | feature set | learner | accuracy | Δ vs per-type [95% CI] | headroom fraction [95% CI] | Δ vs best static [95% CI] |
|---|---|---|---|---|---|---|
| oracle (upper bound) | F1 | logreg | 0.5621 | +0.1793 [+0.152, +0.207] | +1.00 [+1.00, +1.00] | +0.2183 [+0.188, +0.249] |
| best static cell | F1 | logreg | 0.3438 | -0.0391 [-0.067, -0.011] | -0.22 [-0.40, -0.06] | +0.0000 [+0.000, +0.000] |
| per-type lookup | F1 | logreg | 0.3828 | +0.0000 [+0.000, +0.000] | +0.00 [+0.00, +0.00] | +0.0391 [+0.011, +0.067] |
| independent: coverage × always-32B | F1 | logreg | 0.3680 | -0.0148 [-0.044, +0.014] | -0.08 [-0.27, +0.07] | +0.0243 [-0.002, +0.051] |
| independent: coverage × always-32B | F1 | gbt | 0.3728 | -0.0101 [-0.040, +0.020] | -0.06 [-0.24, +0.11] | +0.0290 [+0.003, +0.056] |
| independent: coverage × always-32B | F2 | logreg | 0.3680 | -0.0148 [-0.044, +0.014] | -0.08 [-0.27, +0.07] | +0.0243 [-0.002, +0.051] |
| independent: coverage × always-32B | F2 | gbt | 0.3728 | -0.0101 [-0.040, +0.020] | -0.06 [-0.24, +0.11] | +0.0290 [+0.003, +0.056] |
| independent: coverage × always-32B | F3 | logreg | 0.3680 | -0.0148 [-0.044, +0.014] | -0.08 [-0.27, +0.07] | +0.0243 [-0.002, +0.051] |
| independent: coverage × always-32B | F3 | gbt | 0.3728 | -0.0101 [-0.040, +0.020] | -0.06 [-0.24, +0.11] | +0.0290 [+0.003, +0.056] |
| independent: coverage × always-32B | F4 | logreg | 0.3680 | -0.0148 [-0.044, +0.014] | -0.08 [-0.27, +0.07] | +0.0243 [-0.002, +0.051] |
| independent: coverage × always-32B | F4 | gbt | 0.3728 | -0.0101 [-0.040, +0.020] | -0.06 [-0.24, +0.11] | +0.0290 [+0.003, +0.056] |
| independent: coverage × 4B-confidence | F1 | logreg | 0.3657 | -0.0172 [-0.045, +0.011] | -0.10 [-0.27, +0.06] | +0.0219 [-0.004, +0.048] |
| independent: coverage × 4B-confidence | F1 | gbt | 0.3716 | -0.0112 [-0.039, +0.017] | -0.06 [-0.25, +0.09] | +0.0278 [+0.003, +0.054] |
| independent: coverage × 4B-confidence | F2 | logreg | 0.3657 | -0.0172 [-0.045, +0.011] | -0.10 [-0.27, +0.06] | +0.0219 [-0.004, +0.048] |
| independent: coverage × 4B-confidence | F2 | gbt | 0.3716 | -0.0112 [-0.039, +0.017] | -0.06 [-0.25, +0.09] | +0.0278 [+0.003, +0.054] |
| independent: coverage × 4B-confidence | F3 | logreg | 0.3657 | -0.0172 [-0.045, +0.011] | -0.10 [-0.27, +0.06] | +0.0219 [-0.004, +0.048] |
| independent: coverage × 4B-confidence | F3 | gbt | 0.3716 | -0.0112 [-0.039, +0.017] | -0.06 [-0.25, +0.09] | +0.0278 [+0.003, +0.054] |
| independent: coverage × 4B-confidence | F4 | logreg | 0.3657 | -0.0172 [-0.045, +0.011] | -0.10 [-0.27, +0.06] | +0.0219 [-0.004, +0.048] |
| independent: coverage × 4B-confidence | F4 | gbt | 0.3716 | -0.0112 [-0.039, +0.017] | -0.06 [-0.25, +0.09] | +0.0278 [+0.003, +0.054] |
| independent: coverage × F2 classifier | F1 | logreg | 0.3420 | -0.0408 [-0.068, -0.013] | -0.23 [-0.41, -0.06] | -0.0018 [-0.026, +0.022] |
| independent: coverage × F2 classifier | F1 | gbt | 0.3314 | -0.0515 [-0.080, -0.022] | -0.29 [-0.49, -0.11] | -0.0124 [-0.038, +0.012] |
| independent: coverage × F2 classifier | F2 | logreg | 0.3420 | -0.0408 [-0.068, -0.013] | -0.23 [-0.41, -0.06] | -0.0018 [-0.026, +0.022] |
| independent: coverage × F2 classifier | F2 | gbt | 0.3314 | -0.0515 [-0.080, -0.022] | -0.29 [-0.49, -0.11] | -0.0124 [-0.038, +0.012] |
| independent: coverage × F2 classifier | F3 | logreg | 0.3420 | -0.0408 [-0.068, -0.013] | -0.23 [-0.41, -0.06] | -0.0018 [-0.026, +0.022] |
| independent: coverage × F2 classifier | F3 | gbt | 0.3314 | -0.0515 [-0.080, -0.022] | -0.29 [-0.49, -0.11] | -0.0124 [-0.038, +0.012] |
| independent: coverage × F2 classifier | F4 | logreg | 0.3420 | -0.0408 [-0.068, -0.013] | -0.23 [-0.41, -0.06] | -0.0018 [-0.026, +0.022] |
| independent: coverage × F2 classifier | F4 | gbt | 0.3314 | -0.0515 [-0.080, -0.022] | -0.29 [-0.49, -0.11] | -0.0124 [-0.038, +0.012] |
| capability-only | F1 | logreg | 0.3538 | -0.0290 [-0.053, -0.006] | -0.16 [-0.32, -0.03] | +0.0101 [-0.021, +0.038] |
| capability-only | F1 | gbt | 0.3580 | -0.0249 [-0.048, -0.001] | -0.14 [-0.29, -0.01] | +0.0142 [-0.015, +0.043] |
| capability-only | F2 | logreg | 0.3503 | -0.0325 [-0.062, -0.005] | -0.18 [-0.37, -0.02] | +0.0065 [-0.024, +0.034] |
| capability-only | F2 | gbt | 0.3550 | -0.0278 [-0.055, -0.001] | -0.16 [-0.33, -0.01] | +0.0112 [-0.018, +0.039] |
| capability-only | F3 | logreg | 0.3527 | -0.0302 [-0.058, -0.002] | -0.17 [-0.36, -0.01] | +0.0089 [-0.020, +0.037] |
| capability-only | F3 | gbt | 0.3538 | -0.0290 [-0.056, -0.002] | -0.16 [-0.35, -0.01] | +0.0101 [-0.021, +0.039] |
| capability-only | F4 | logreg | 0.3568 | -0.0260 [-0.055, +0.002] | -0.15 [-0.33, +0.01] | +0.0130 [-0.019, +0.043] |
| capability-only | F4 | gbt | 0.3491 | -0.0337 [-0.059, -0.008] | -0.19 [-0.36, -0.04] | +0.0053 [-0.024, +0.033] |
| evidence-only | F1 | logreg | 0.3615 | -0.0213 [-0.045, +0.003] | -0.12 [-0.27, +0.02] | +0.0178 [-0.009, +0.044] |
| evidence-only | F1 | gbt | 0.3781 | -0.0047 [-0.030, +0.019] | -0.03 [-0.18, +0.10] | +0.0343 [+0.006, +0.062] |
| evidence-only | F2 | logreg | 0.3645 | -0.0183 [-0.047, +0.010] | -0.10 [-0.28, +0.05] | +0.0207 [-0.007, +0.050] |
| evidence-only | F2 | gbt | 0.3669 | -0.0160 [-0.043, +0.010] | -0.09 [-0.26, +0.05] | +0.0231 [-0.004, +0.049] |
| evidence-only | F3 | logreg | 0.3592 | -0.0237 [-0.051, +0.004] | -0.13 [-0.31, +0.02] | +0.0154 [-0.013, +0.044] |
| evidence-only | F3 | gbt | 0.3657 | -0.0172 [-0.043, +0.009] | -0.10 [-0.26, +0.05] | +0.0219 [-0.004, +0.046] |
| evidence-only | F4 | logreg | 0.3633 | -0.0195 [-0.048, +0.010] | -0.11 [-0.29, +0.05] | +0.0195 [-0.008, +0.047] |
| evidence-only | F4 | gbt | 0.3598 | -0.0231 [-0.051, +0.004] | -0.13 [-0.31, +0.02] | +0.0160 [-0.010, +0.041] |
| combined (all four cells) | F1 | logreg | 0.3710 | -0.0118 [-0.029, +0.007] | -0.07 [-0.17, +0.03] | +0.0272 [-0.001, +0.056] |
| combined (all four cells) | F1 | gbt | 0.3716 | -0.0112 [-0.033, +0.012] | -0.06 [-0.20, +0.06] | +0.0278 [-0.001, +0.056] |
| combined (all four cells) | F2 | logreg | 0.3698 | -0.0130 [-0.040, +0.014] | -0.07 [-0.24, +0.07] | +0.0260 [-0.003, +0.057] |
| combined (all four cells) | F2 | gbt | 0.3680 | -0.0148 [-0.043, +0.013] | -0.08 [-0.27, +0.07] | +0.0243 [-0.006, +0.054] |
| combined (all four cells) | F3 | logreg | 0.3710 | -0.0118 [-0.040, +0.018] | -0.07 [-0.24, +0.09] | +0.0272 [-0.001, +0.056] |
| combined (all four cells) | F3 | gbt | 0.3728 | -0.0101 [-0.039, +0.017] | -0.06 [-0.24, +0.09] | +0.0290 [-0.001, +0.058] |
| combined (all four cells) | F4 | logreg | 0.3633 | -0.0195 [-0.048, +0.009] | -0.11 [-0.30, +0.04] | +0.0195 [-0.011, +0.049] |
| combined (all four cells) | F4 | gbt | 0.3633 | -0.0195 [-0.048, +0.008] | -0.11 [-0.30, +0.04] | +0.0195 [-0.008, +0.047] |

**32B budget 1, RICH budget 0.25** — oracle 0.5621, best static 0.3763, per-type 0.3893

| policy | feature set | learner | accuracy | Δ vs per-type [95% CI] | headroom fraction [95% CI] | Δ vs best static [95% CI] |
|---|---|---|---|---|---|---|
| oracle (upper bound) | F1 | logreg | 0.5621 | +0.1728 [+0.148, +0.198] | +1.00 [+1.00, +1.00] | +0.1858 [+0.159, +0.212] |
| best static cell | F1 | logreg | 0.3763 | -0.0130 [-0.035, +0.011] | -0.08 [-0.22, +0.06] | +0.0000 [+0.000, +0.000] |
| per-type lookup | F1 | logreg | 0.3893 | +0.0000 [+0.000, +0.000] | +0.00 [+0.00, +0.00] | +0.0130 [-0.011, +0.035] |
| independent: coverage × always-32B | F1 | logreg | 0.3882 | -0.0012 [-0.022, +0.019] | -0.01 [-0.13, +0.11] | +0.0118 [-0.004, +0.028] |
| independent: coverage × always-32B | F1 | gbt | 0.3775 | -0.0118 [-0.035, +0.011] | -0.07 [-0.22, +0.06] | +0.0012 [-0.015, +0.017] |
| independent: coverage × always-32B | F2 | logreg | 0.3882 | -0.0012 [-0.022, +0.019] | -0.01 [-0.13, +0.11] | +0.0118 [-0.004, +0.028] |
| independent: coverage × always-32B | F2 | gbt | 0.3775 | -0.0118 [-0.035, +0.011] | -0.07 [-0.22, +0.06] | +0.0012 [-0.015, +0.017] |
| independent: coverage × always-32B | F3 | logreg | 0.3882 | -0.0012 [-0.022, +0.019] | -0.01 [-0.13, +0.11] | +0.0118 [-0.004, +0.028] |
| independent: coverage × always-32B | F3 | gbt | 0.3775 | -0.0118 [-0.035, +0.011] | -0.07 [-0.22, +0.06] | +0.0012 [-0.015, +0.017] |
| independent: coverage × always-32B | F4 | logreg | 0.3882 | -0.0012 [-0.022, +0.019] | -0.01 [-0.13, +0.11] | +0.0118 [-0.004, +0.028] |
| independent: coverage × always-32B | F4 | gbt | 0.3775 | -0.0118 [-0.035, +0.011] | -0.07 [-0.22, +0.06] | +0.0012 [-0.015, +0.017] |
| independent: coverage × 4B-confidence | F1 | logreg | 0.3811 | -0.0083 [-0.029, +0.013] | -0.05 [-0.18, +0.07] | +0.0047 [-0.013, +0.021] |
| independent: coverage × 4B-confidence | F1 | gbt | 0.3728 | -0.0166 [-0.039, +0.006] | -0.10 [-0.25, +0.04] | -0.0036 [-0.021, +0.013] |
| independent: coverage × 4B-confidence | F2 | logreg | 0.3811 | -0.0083 [-0.029, +0.013] | -0.05 [-0.18, +0.07] | +0.0047 [-0.013, +0.021] |
| independent: coverage × 4B-confidence | F2 | gbt | 0.3728 | -0.0166 [-0.039, +0.006] | -0.10 [-0.25, +0.04] | -0.0036 [-0.021, +0.013] |
| independent: coverage × 4B-confidence | F3 | logreg | 0.3811 | -0.0083 [-0.029, +0.013] | -0.05 [-0.18, +0.07] | +0.0047 [-0.013, +0.021] |
| independent: coverage × 4B-confidence | F3 | gbt | 0.3728 | -0.0166 [-0.039, +0.006] | -0.10 [-0.25, +0.04] | -0.0036 [-0.021, +0.013] |
| independent: coverage × 4B-confidence | F4 | logreg | 0.3811 | -0.0083 [-0.029, +0.013] | -0.05 [-0.18, +0.07] | +0.0047 [-0.013, +0.021] |
| independent: coverage × 4B-confidence | F4 | gbt | 0.3728 | -0.0166 [-0.039, +0.006] | -0.10 [-0.25, +0.04] | -0.0036 [-0.021, +0.013] |
| independent: coverage × F2 classifier | F1 | logreg | 0.3420 | -0.0473 [-0.077, -0.017] | -0.27 [-0.50, -0.09] | -0.0343 [-0.063, -0.006] |
| independent: coverage × F2 classifier | F1 | gbt | 0.3314 | -0.0580 [-0.091, -0.025] | -0.34 [-0.58, -0.13] | -0.0450 [-0.077, -0.014] |
| independent: coverage × F2 classifier | F2 | logreg | 0.3420 | -0.0473 [-0.077, -0.017] | -0.27 [-0.50, -0.09] | -0.0343 [-0.063, -0.006] |
| independent: coverage × F2 classifier | F2 | gbt | 0.3314 | -0.0580 [-0.091, -0.025] | -0.34 [-0.58, -0.13] | -0.0450 [-0.077, -0.014] |
| independent: coverage × F2 classifier | F3 | logreg | 0.3420 | -0.0473 [-0.077, -0.017] | -0.27 [-0.50, -0.09] | -0.0343 [-0.063, -0.006] |
| independent: coverage × F2 classifier | F3 | gbt | 0.3314 | -0.0580 [-0.091, -0.025] | -0.34 [-0.58, -0.13] | -0.0450 [-0.077, -0.014] |
| independent: coverage × F2 classifier | F4 | logreg | 0.3420 | -0.0473 [-0.077, -0.017] | -0.27 [-0.50, -0.09] | -0.0343 [-0.063, -0.006] |
| independent: coverage × F2 classifier | F4 | gbt | 0.3314 | -0.0580 [-0.091, -0.025] | -0.34 [-0.58, -0.13] | -0.0450 [-0.077, -0.014] |
| capability-only | F1 | logreg | 0.3444 | -0.0450 [-0.075, -0.014] | -0.26 [-0.49, -0.07] | -0.0320 [-0.060, -0.005] |
| capability-only | F1 | gbt | 0.3361 | -0.0533 [-0.082, -0.024] | -0.31 [-0.53, -0.12] | -0.0402 [-0.069, -0.011] |
| capability-only | F2 | logreg | 0.3293 | -0.0601 [-0.093, -0.028] | -0.35 [-0.58, -0.15] | -0.0470 [-0.078, -0.016] |
| capability-only | F2 | gbt | 0.3396 | -0.0497 [-0.084, -0.018] | -0.29 [-0.53, -0.10] | -0.0367 [-0.069, -0.006] |
| capability-only | F3 | logreg | 0.3349 | -0.0544 [-0.088, -0.021] | -0.32 [-0.56, -0.11] | -0.0414 [-0.075, -0.008] |
| capability-only | F3 | gbt | 0.3373 | -0.0521 [-0.084, -0.022] | -0.30 [-0.53, -0.12] | -0.0391 [-0.071, -0.007] |
| capability-only | F4 | logreg | 0.3183 | -0.0710 [-0.103, -0.039] | -0.41 [-0.65, -0.21] | -0.0580 [-0.090, -0.027] |
| capability-only | F4 | gbt | 0.3219 | -0.0675 [-0.100, -0.037] | -0.39 [-0.64, -0.20] | -0.0544 [-0.085, -0.025] |
| evidence-only | F1 | logreg | 0.3870 | -0.0024 [-0.019, +0.014] | -0.01 [-0.12, +0.08] | +0.0107 [-0.008, +0.029] |
| evidence-only | F1 | gbt | 0.3976 | +0.0083 [-0.010, +0.028] | +0.05 [-0.07, +0.15] | +0.0213 [+0.001, +0.038] |
| evidence-only | F2 | logreg | 0.3917 | +0.0024 [-0.017, +0.023] | +0.01 [-0.10, +0.13] | +0.0154 [-0.002, +0.033] |
| evidence-only | F2 | gbt | 0.3822 | -0.0071 [-0.030, +0.014] | -0.04 [-0.19, +0.08] | +0.0059 [-0.010, +0.022] |
| evidence-only | F3 | logreg | 0.3953 | +0.0059 [-0.014, +0.027] | +0.03 [-0.09, +0.15] | +0.0189 [+0.001, +0.038] |
| evidence-only | F3 | gbt | 0.3882 | -0.0012 [-0.021, +0.019] | -0.01 [-0.13, +0.10] | +0.0118 [-0.005, +0.028] |
| evidence-only | F4 | logreg | 0.3929 | +0.0036 [-0.017, +0.024] | +0.02 [-0.10, +0.13] | +0.0166 [-0.001, +0.034] |
| evidence-only | F4 | gbt | 0.3846 | -0.0047 [-0.025, +0.016] | -0.03 [-0.16, +0.09] | +0.0083 [-0.007, +0.023] |
| combined (all four cells) | F1 | logreg | 0.3917 | +0.0024 [-0.013, +0.018] | +0.01 [-0.08, +0.10] | +0.0154 [-0.007, +0.037] |
| combined (all four cells) | F1 | gbt | 0.3725 | -0.0169 [-0.038, +0.003] | -0.10 [-0.24, +0.02] | -0.0038 [-0.027, +0.017] |
| combined (all four cells) | F2 | logreg | 0.3751 | -0.0142 [-0.040, +0.013] | -0.08 [-0.25, +0.07] | -0.0012 [-0.029, +0.029] |
| combined (all four cells) | F2 | gbt | 0.3740 | -0.0154 [-0.041, +0.011] | -0.09 [-0.26, +0.06] | -0.0024 [-0.024, +0.020] |
| combined (all four cells) | F3 | logreg | 0.3751 | -0.0142 [-0.039, +0.013] | -0.08 [-0.24, +0.07] | -0.0012 [-0.029, +0.027] |
| combined (all four cells) | F3 | gbt | 0.3624 | -0.0269 [-0.050, -0.005] | -0.16 [-0.31, -0.03] | -0.0139 [-0.037, +0.008] |
| combined (all four cells) | F4 | logreg | 0.3751 | -0.0142 [-0.041, +0.012] | -0.08 [-0.26, +0.07] | -0.0012 [-0.027, +0.025] |
| combined (all four cells) | F4 | gbt | 0.3802 | -0.0092 [-0.033, +0.014] | -0.05 [-0.20, +0.08] | +0.0038 [-0.018, +0.026] |

**32B budget 1, RICH budget 0.5** — oracle 0.5621, best static 0.3811, per-type 0.3834

| policy | feature set | learner | accuracy | Δ vs per-type [95% CI] | headroom fraction [95% CI] | Δ vs best static [95% CI] |
|---|---|---|---|---|---|---|
| oracle (upper bound) | F1 | logreg | 0.5621 | +0.1787 [+0.154, +0.205] | +1.00 [+1.00, +1.00] | +0.1811 [+0.155, +0.206] |
| best static cell | F1 | logreg | 0.3811 | -0.0024 [-0.024, +0.020] | -0.01 [-0.14, +0.11] | +0.0000 [+0.000, +0.000] |
| per-type lookup | F1 | logreg | 0.3834 | +0.0000 [+0.000, +0.000] | +0.00 [+0.00, +0.00] | +0.0024 [-0.020, +0.024] |
| independent: coverage × always-32B | F1 | logreg | 0.3882 | +0.0047 [-0.020, +0.028] | +0.03 [-0.12, +0.15] | +0.0071 [-0.012, +0.025] |
| independent: coverage × always-32B | F1 | gbt | 0.3775 | -0.0059 [-0.032, +0.018] | -0.03 [-0.19, +0.10] | -0.0036 [-0.024, +0.016] |
| independent: coverage × always-32B | F2 | logreg | 0.3882 | +0.0047 [-0.020, +0.028] | +0.03 [-0.12, +0.15] | +0.0071 [-0.012, +0.025] |
| independent: coverage × always-32B | F2 | gbt | 0.3775 | -0.0059 [-0.032, +0.018] | -0.03 [-0.19, +0.10] | -0.0036 [-0.024, +0.016] |
| independent: coverage × always-32B | F3 | logreg | 0.3882 | +0.0047 [-0.020, +0.028] | +0.03 [-0.12, +0.15] | +0.0071 [-0.012, +0.025] |
| independent: coverage × always-32B | F3 | gbt | 0.3775 | -0.0059 [-0.032, +0.018] | -0.03 [-0.19, +0.10] | -0.0036 [-0.024, +0.016] |
| independent: coverage × always-32B | F4 | logreg | 0.3882 | +0.0047 [-0.020, +0.028] | +0.03 [-0.12, +0.15] | +0.0071 [-0.012, +0.025] |
| independent: coverage × always-32B | F4 | gbt | 0.3775 | -0.0059 [-0.032, +0.018] | -0.03 [-0.19, +0.10] | -0.0036 [-0.024, +0.016] |
| independent: coverage × 4B-confidence | F1 | logreg | 0.3811 | -0.0024 [-0.026, +0.022] | -0.01 [-0.16, +0.12] | +0.0000 [-0.021, +0.020] |
| independent: coverage × 4B-confidence | F1 | gbt | 0.3728 | -0.0107 [-0.036, +0.015] | -0.06 [-0.22, +0.08] | -0.0083 [-0.031, +0.012] |
| independent: coverage × 4B-confidence | F2 | logreg | 0.3811 | -0.0024 [-0.026, +0.022] | -0.01 [-0.16, +0.12] | +0.0000 [-0.021, +0.020] |
| independent: coverage × 4B-confidence | F2 | gbt | 0.3728 | -0.0107 [-0.036, +0.015] | -0.06 [-0.22, +0.08] | -0.0083 [-0.031, +0.012] |
| independent: coverage × 4B-confidence | F3 | logreg | 0.3811 | -0.0024 [-0.026, +0.022] | -0.01 [-0.16, +0.12] | +0.0000 [-0.021, +0.020] |
| independent: coverage × 4B-confidence | F3 | gbt | 0.3728 | -0.0107 [-0.036, +0.015] | -0.06 [-0.22, +0.08] | -0.0083 [-0.031, +0.012] |
| independent: coverage × 4B-confidence | F4 | logreg | 0.3811 | -0.0024 [-0.026, +0.022] | -0.01 [-0.16, +0.12] | +0.0000 [-0.021, +0.020] |
| independent: coverage × 4B-confidence | F4 | gbt | 0.3728 | -0.0107 [-0.036, +0.015] | -0.06 [-0.22, +0.08] | -0.0083 [-0.031, +0.012] |
| independent: coverage × F2 classifier | F1 | logreg | 0.3420 | -0.0414 [-0.071, -0.011] | -0.23 [-0.44, -0.06] | -0.0391 [-0.069, -0.009] |
| independent: coverage × F2 classifier | F1 | gbt | 0.3314 | -0.0521 [-0.085, -0.020] | -0.29 [-0.53, -0.10] | -0.0497 [-0.083, -0.019] |
| independent: coverage × F2 classifier | F2 | logreg | 0.3420 | -0.0414 [-0.071, -0.011] | -0.23 [-0.44, -0.06] | -0.0391 [-0.069, -0.009] |
| independent: coverage × F2 classifier | F2 | gbt | 0.3314 | -0.0521 [-0.085, -0.020] | -0.29 [-0.53, -0.10] | -0.0497 [-0.083, -0.019] |
| independent: coverage × F2 classifier | F3 | logreg | 0.3420 | -0.0414 [-0.071, -0.011] | -0.23 [-0.44, -0.06] | -0.0391 [-0.069, -0.009] |
| independent: coverage × F2 classifier | F3 | gbt | 0.3314 | -0.0521 [-0.085, -0.020] | -0.29 [-0.53, -0.10] | -0.0497 [-0.083, -0.019] |
| independent: coverage × F2 classifier | F4 | logreg | 0.3420 | -0.0414 [-0.071, -0.011] | -0.23 [-0.44, -0.06] | -0.0391 [-0.069, -0.009] |
| independent: coverage × F2 classifier | F4 | gbt | 0.3314 | -0.0521 [-0.085, -0.020] | -0.29 [-0.53, -0.10] | -0.0497 [-0.083, -0.019] |
| capability-only | F1 | logreg | 0.3645 | -0.0189 [-0.042, +0.002] | -0.11 [-0.25, +0.01] | -0.0166 [-0.042, +0.008] |
| capability-only | F1 | gbt | 0.3675 | -0.0160 [-0.042, +0.008] | -0.09 [-0.25, +0.05] | -0.0136 [-0.042, +0.013] |
| capability-only | F2 | logreg | 0.3485 | -0.0349 [-0.065, -0.005] | -0.20 [-0.39, -0.03] | -0.0325 [-0.063, -0.002] |
| capability-only | F2 | gbt | 0.3521 | -0.0314 [-0.061, -0.002] | -0.18 [-0.38, -0.01] | -0.0290 [-0.059, +0.001] |
| capability-only | F3 | logreg | 0.3515 | -0.0320 [-0.062, -0.001] | -0.18 [-0.38, -0.01] | -0.0296 [-0.059, +0.002] |
| capability-only | F3 | gbt | 0.3503 | -0.0331 [-0.060, -0.006] | -0.19 [-0.37, -0.03] | -0.0308 [-0.059, -0.003] |
| capability-only | F4 | logreg | 0.3337 | -0.0497 [-0.078, -0.020] | -0.28 [-0.47, -0.11] | -0.0473 [-0.078, -0.017] |
| capability-only | F4 | gbt | 0.3479 | -0.0355 [-0.064, -0.007] | -0.20 [-0.39, -0.04] | -0.0331 [-0.062, -0.005] |
| evidence-only | F1 | logreg | 0.3917 | +0.0083 [-0.008, +0.026] | +0.05 [-0.05, +0.14] | +0.0107 [-0.007, +0.029] |
| evidence-only | F1 | gbt | 0.4024 | +0.0189 [-0.001, +0.039] | +0.11 [-0.01, +0.21] | +0.0213 [+0.000, +0.042] |
| evidence-only | F2 | logreg | 0.3959 | +0.0124 [-0.008, +0.033] | +0.07 [-0.05, +0.17] | +0.0148 [-0.004, +0.033] |
| evidence-only | F2 | gbt | 0.3846 | +0.0012 [-0.020, +0.023] | +0.01 [-0.12, +0.12] | +0.0036 [-0.014, +0.020] |
| evidence-only | F3 | logreg | 0.3959 | +0.0124 [-0.009, +0.034] | +0.07 [-0.06, +0.18] | +0.0148 [-0.005, +0.034] |
| evidence-only | F3 | gbt | 0.3876 | +0.0041 [-0.018, +0.026] | +0.02 [-0.11, +0.14] | +0.0065 [-0.011, +0.022] |
| evidence-only | F4 | logreg | 0.3941 | +0.0107 [-0.011, +0.032] | +0.06 [-0.07, +0.17] | +0.0130 [-0.007, +0.031] |
| evidence-only | F4 | gbt | 0.3893 | +0.0059 [-0.017, +0.029] | +0.03 [-0.10, +0.15] | +0.0083 [-0.008, +0.025] |
| combined (all four cells) | F1 | logreg | 0.3964 | +0.0130 [-0.002, +0.030] | +0.07 [-0.01, +0.16] | +0.0154 [-0.006, +0.036] |
| combined (all four cells) | F1 | gbt | 0.3822 | -0.0012 [-0.023, +0.021] | -0.01 [-0.14, +0.12] | +0.0012 [-0.025, +0.026] |
| combined (all four cells) | F2 | logreg | 0.3740 | -0.0095 [-0.034, +0.017] | -0.05 [-0.21, +0.09] | -0.0071 [-0.034, +0.020] |
| combined (all four cells) | F2 | gbt | 0.3728 | -0.0107 [-0.034, +0.014] | -0.06 [-0.21, +0.07] | -0.0083 [-0.031, +0.015] |
| combined (all four cells) | F3 | logreg | 0.3692 | -0.0142 [-0.040, +0.014] | -0.08 [-0.24, +0.07] | -0.0118 [-0.039, +0.016] |
| combined (all four cells) | F3 | gbt | 0.3680 | -0.0154 [-0.041, +0.008] | -0.09 [-0.24, +0.04] | -0.0130 [-0.036, +0.008] |
| combined (all four cells) | F4 | logreg | 0.3692 | -0.0142 [-0.040, +0.012] | -0.08 [-0.24, +0.06] | -0.0118 [-0.038, +0.014] |
| combined (all four cells) | F4 | gbt | 0.3740 | -0.0095 [-0.034, +0.017] | -0.05 [-0.21, +0.09] | -0.0071 [-0.029, +0.015] |

**32B budget 1, RICH budget 1** — oracle 0.5621, best static 0.3953, per-type 0.3799

| policy | feature set | learner | accuracy | Δ vs per-type [95% CI] | headroom fraction [95% CI] | Δ vs best static [95% CI] |
|---|---|---|---|---|---|---|
| oracle (upper bound) | F1 | logreg | 0.5621 | +0.1822 [+0.156, +0.208] | +1.00 [+1.00, +1.00] | +0.1669 [+0.142, +0.192] |
| best static cell | F1 | logreg | 0.3953 | +0.0154 [-0.005, +0.036] | +0.08 [-0.03, +0.19] | +0.0000 [+0.000, +0.000] |
| per-type lookup | F1 | logreg | 0.3799 | +0.0000 [+0.000, +0.000] | +0.00 [+0.00, +0.00] | -0.0154 [-0.036, +0.005] |
| independent: coverage × always-32B | F1 | logreg | 0.3882 | +0.0083 [-0.017, +0.033] | +0.05 [-0.10, +0.17] | -0.0071 [-0.033, +0.017] |
| independent: coverage × always-32B | F1 | gbt | 0.3775 | -0.0024 [-0.029, +0.023] | -0.01 [-0.17, +0.12] | -0.0178 [-0.044, +0.007] |
| independent: coverage × always-32B | F2 | logreg | 0.3882 | +0.0083 [-0.017, +0.033] | +0.05 [-0.10, +0.17] | -0.0071 [-0.033, +0.017] |
| independent: coverage × always-32B | F2 | gbt | 0.3775 | -0.0024 [-0.029, +0.023] | -0.01 [-0.17, +0.12] | -0.0178 [-0.044, +0.007] |
| independent: coverage × always-32B | F3 | logreg | 0.3882 | +0.0083 [-0.017, +0.033] | +0.05 [-0.10, +0.17] | -0.0071 [-0.033, +0.017] |
| independent: coverage × always-32B | F3 | gbt | 0.3775 | -0.0024 [-0.029, +0.023] | -0.01 [-0.17, +0.12] | -0.0178 [-0.044, +0.007] |
| independent: coverage × always-32B | F4 | logreg | 0.3882 | +0.0083 [-0.017, +0.033] | +0.05 [-0.10, +0.17] | -0.0071 [-0.033, +0.017] |
| independent: coverage × always-32B | F4 | gbt | 0.3775 | -0.0024 [-0.029, +0.023] | -0.01 [-0.17, +0.12] | -0.0178 [-0.044, +0.007] |
| independent: coverage × 4B-confidence | F1 | logreg | 0.3811 | +0.0012 [-0.024, +0.027] | +0.01 [-0.14, +0.14] | -0.0142 [-0.039, +0.010] |
| independent: coverage × 4B-confidence | F1 | gbt | 0.3728 | -0.0071 [-0.033, +0.019] | -0.04 [-0.20, +0.10] | -0.0225 [-0.050, +0.002] |
| independent: coverage × 4B-confidence | F2 | logreg | 0.3811 | +0.0012 [-0.024, +0.027] | +0.01 [-0.14, +0.14] | -0.0142 [-0.039, +0.010] |
| independent: coverage × 4B-confidence | F2 | gbt | 0.3728 | -0.0071 [-0.033, +0.019] | -0.04 [-0.20, +0.10] | -0.0225 [-0.050, +0.002] |
| independent: coverage × 4B-confidence | F3 | logreg | 0.3811 | +0.0012 [-0.024, +0.027] | +0.01 [-0.14, +0.14] | -0.0142 [-0.039, +0.010] |
| independent: coverage × 4B-confidence | F3 | gbt | 0.3728 | -0.0071 [-0.033, +0.019] | -0.04 [-0.20, +0.10] | -0.0225 [-0.050, +0.002] |
| independent: coverage × 4B-confidence | F4 | logreg | 0.3811 | +0.0012 [-0.024, +0.027] | +0.01 [-0.14, +0.14] | -0.0142 [-0.039, +0.010] |
| independent: coverage × 4B-confidence | F4 | gbt | 0.3728 | -0.0071 [-0.033, +0.019] | -0.04 [-0.20, +0.10] | -0.0225 [-0.050, +0.002] |
| independent: coverage × F2 classifier | F1 | logreg | 0.3420 | -0.0379 [-0.067, -0.007] | -0.21 [-0.40, -0.04] | -0.0533 [-0.086, -0.021] |
| independent: coverage × F2 classifier | F1 | gbt | 0.3314 | -0.0485 [-0.081, -0.017] | -0.27 [-0.49, -0.09] | -0.0639 [-0.101, -0.030] |
| independent: coverage × F2 classifier | F2 | logreg | 0.3420 | -0.0379 [-0.067, -0.007] | -0.21 [-0.40, -0.04] | -0.0533 [-0.086, -0.021] |
| independent: coverage × F2 classifier | F2 | gbt | 0.3314 | -0.0485 [-0.081, -0.017] | -0.27 [-0.49, -0.09] | -0.0639 [-0.101, -0.030] |
| independent: coverage × F2 classifier | F3 | logreg | 0.3420 | -0.0379 [-0.067, -0.007] | -0.21 [-0.40, -0.04] | -0.0533 [-0.086, -0.021] |
| independent: coverage × F2 classifier | F3 | gbt | 0.3314 | -0.0485 [-0.081, -0.017] | -0.27 [-0.49, -0.09] | -0.0639 [-0.101, -0.030] |
| independent: coverage × F2 classifier | F4 | logreg | 0.3420 | -0.0379 [-0.067, -0.007] | -0.21 [-0.40, -0.04] | -0.0533 [-0.086, -0.021] |
| independent: coverage × F2 classifier | F4 | gbt | 0.3314 | -0.0485 [-0.081, -0.017] | -0.27 [-0.49, -0.09] | -0.0639 [-0.101, -0.030] |
| capability-only | F1 | logreg | 0.3846 | +0.0047 [-0.014, +0.024] | +0.03 [-0.08, +0.13] | -0.0107 [-0.021, -0.001] |
| capability-only | F1 | gbt | 0.3704 | -0.0095 [-0.030, +0.011] | -0.05 [-0.17, +0.06] | -0.0249 [-0.043, -0.008] |
| capability-only | F2 | logreg | 0.3574 | -0.0225 [-0.048, +0.004] | -0.12 [-0.28, +0.02] | -0.0379 [-0.060, -0.016] |
| capability-only | F2 | gbt | 0.3751 | -0.0047 [-0.031, +0.020] | -0.03 [-0.18, +0.10] | -0.0201 [-0.041, +0.000] |
| capability-only | F3 | logreg | 0.3574 | -0.0225 [-0.049, +0.004] | -0.12 [-0.28, +0.02] | -0.0379 [-0.060, -0.016] |
| capability-only | F3 | gbt | 0.3680 | -0.0118 [-0.036, +0.011] | -0.06 [-0.21, +0.06] | -0.0272 [-0.046, -0.008] |
| capability-only | F4 | logreg | 0.3609 | -0.0189 [-0.045, +0.008] | -0.10 [-0.27, +0.04] | -0.0343 [-0.056, -0.013] |
| capability-only | F4 | gbt | 0.3645 | -0.0154 [-0.040, +0.008] | -0.08 [-0.24, +0.05] | -0.0308 [-0.049, -0.011] |
| evidence-only | F1 | logreg | 0.4036 | +0.0237 [+0.005, +0.044] | +0.13 [+0.03, +0.23] | +0.0083 [-0.004, +0.021] |
| evidence-only | F1 | gbt | 0.4036 | +0.0237 [+0.004, +0.043] | +0.13 [+0.02, +0.23] | +0.0083 [-0.009, +0.025] |
| evidence-only | F2 | logreg | 0.3964 | +0.0166 [-0.006, +0.038] | +0.09 [-0.03, +0.20] | +0.0012 [-0.017, +0.020] |
| evidence-only | F2 | gbt | 0.3834 | +0.0036 [-0.019, +0.027] | +0.02 [-0.11, +0.14] | -0.0118 [-0.030, +0.005] |
| evidence-only | F3 | logreg | 0.3953 | +0.0154 [-0.007, +0.037] | +0.08 [-0.04, +0.20] | +0.0000 [-0.019, +0.018] |
| evidence-only | F3 | gbt | 0.3870 | +0.0071 [-0.017, +0.031] | +0.04 [-0.10, +0.16] | -0.0083 [-0.026, +0.008] |
| evidence-only | F4 | logreg | 0.3953 | +0.0154 [-0.007, +0.037] | +0.08 [-0.04, +0.19] | +0.0000 [-0.019, +0.018] |
| evidence-only | F4 | gbt | 0.3893 | +0.0095 [-0.014, +0.034] | +0.05 [-0.08, +0.17] | -0.0059 [-0.024, +0.011] |
| combined (all four cells) | F1 | logreg | 0.3988 | +0.0189 [+0.002, +0.037] | +0.10 [+0.01, +0.19] | +0.0036 [-0.015, +0.022] |
| combined (all four cells) | F1 | gbt | 0.3822 | +0.0024 [-0.020, +0.024] | +0.01 [-0.11, +0.13] | -0.0130 [-0.038, +0.011] |
| combined (all four cells) | F2 | logreg | 0.3740 | -0.0059 [-0.031, +0.020] | -0.03 [-0.19, +0.10] | -0.0213 [-0.046, +0.005] |
| combined (all four cells) | F2 | gbt | 0.3728 | -0.0071 [-0.032, +0.018] | -0.04 [-0.19, +0.09] | -0.0225 [-0.047, +0.001] |
| combined (all four cells) | F3 | logreg | 0.3692 | -0.0107 [-0.037, +0.018] | -0.06 [-0.22, +0.09] | -0.0260 [-0.052, +0.001] |
| combined (all four cells) | F3 | gbt | 0.3680 | -0.0118 [-0.037, +0.013] | -0.06 [-0.22, +0.07] | -0.0272 [-0.053, -0.002] |
| combined (all four cells) | F4 | logreg | 0.3692 | -0.0107 [-0.037, +0.015] | -0.06 [-0.21, +0.08] | -0.0260 [-0.050, -0.001] |
| combined (all four cells) | F4 | gbt | 0.3740 | -0.0059 [-0.032, +0.021] | -0.03 [-0.19, +0.10] | -0.0213 [-0.045, +0.002] |

## 8. Setting (b) — timely utility with Part 0's corrected costs

utility = correct AND (compute + upload + RTT) <= deadline. Upload uses PART 0's corrected rule: RICH cells pay only the newest pending frame; RECENT cells pay all their frames. Compute from the same cold curves as StudyE4; a prompt outside the measured token range is UNKNOWN and that cell is unavailable (utility 0), as in E4. F4 additionally pays the 4B RECENT run (compute + its upload) before deciding, except when it then chooses H1, whose answer it already has.

**Deliverability first, because it dominates.** Fraction of the 845 questions each cell can deliver inside the deadline:

| network / format / deadline | H1 (4B RECENT) | H2 (4B RICH) | K3 (32B RECENT) | K1 (32B RICH) |
|---|---|---|---|---|
| 88 Mbit/s / png / 5s s | 0.8521 | 0.4426 | 0.0260 | 0.9988 |
| 88 Mbit/s / png / 10s s | 0.8521 | 0.4426 | 1.0000 | 0.9988 |
| 13.6 Mbit/s / png / 10s s | 0.0095 | 0.4426 | 0.0071 | 0.9988 |

| network / format / deadline | per-cell utility H1 | H2 | K3 | K1 |
|---|---|---|---|---|
| 88 Mbit/s / png / 5s s | 0.2840 | 0.1491 | 0.0154 | 0.3941 |
| 88 Mbit/s / png / 10s s | 0.2840 | 0.1491 | 0.3834 | 0.3941 |
| 13.6 Mbit/s / png / 10s s | 0.0047 | 0.1491 | 0.0047 | 0.3941 |

H2's 0.4426 deliverability is a *compute* limit, not a network one: the cold 4B curve ends at 12,501 tokens and RICH's median prompt is 12,597, so 471 of 845 are UNKNOWN and counted unavailable exactly as E4 does. H1's and K3's collapse at 13.6 Mbit/s is a network limit: 34 MB of RECENT frames needs ~20 s on that uplink.

**88 Mbit/s / png / 5s s** — oracle 0.4982, best static 0.3941, per-type 0.3929

| policy | feature set | learner | utility | Δ vs per-type [95% CI] | headroom fraction [95% CI] | Δ vs best static [95% CI] |
|---|---|---|---|---|---|---|
| oracle (upper bound) | F1 | logreg | 0.4982 | +0.1053 [+0.086, +0.126] | +1.00 [+1.00, +1.00] | +0.1041 [+0.085, +0.124] |
| best static cell | F1 | logreg | 0.3941 | +0.0012 [-0.017, +0.020] | +0.01 [-0.18, +0.18] | +0.0000 [+0.000, +0.000] |
| per-type lookup | F1 | logreg | 0.3929 | +0.0000 [+0.000, +0.000] | +0.00 [+0.00, +0.00] | -0.0012 [-0.020, +0.017] |
| independent: coverage × always-32B | F1 | logreg | 0.3740 | -0.0189 [-0.037, +0.001] | -0.18 [-0.39, +0.01] | -0.0201 [-0.031, -0.009] |
| independent: coverage × always-32B | F1 | gbt | 0.3941 | +0.0012 [-0.017, +0.020] | +0.01 [-0.18, +0.18] | +0.0000 [+0.000, +0.000] |
| independent: coverage × always-32B | F2 | logreg | 0.3740 | -0.0189 [-0.037, +0.001] | -0.18 [-0.39, +0.01] | -0.0201 [-0.031, -0.009] |
| independent: coverage × always-32B | F2 | gbt | 0.3941 | +0.0012 [-0.017, +0.020] | +0.01 [-0.18, +0.18] | +0.0000 [+0.000, +0.000] |
| independent: coverage × always-32B | F3 | logreg | 0.3740 | -0.0189 [-0.037, +0.001] | -0.18 [-0.39, +0.01] | -0.0201 [-0.031, -0.009] |
| independent: coverage × always-32B | F3 | gbt | 0.3941 | +0.0012 [-0.017, +0.020] | +0.01 [-0.18, +0.18] | +0.0000 [+0.000, +0.000] |
| independent: coverage × always-32B | F4 | logreg | 0.2852 | -0.1077 [-0.138, -0.077] | -1.02 [-1.53, -0.64] | -0.1089 [-0.144, -0.075] |
| independent: coverage × always-32B | F4 | gbt | 0.2852 | -0.1077 [-0.138, -0.077] | -1.02 [-1.53, -0.64] | -0.1089 [-0.144, -0.075] |
| independent: coverage × 4B-confidence | F1 | logreg | 0.3680 | -0.0249 [-0.044, -0.005] | -0.24 [-0.46, -0.04] | -0.0260 [-0.040, -0.012] |
| independent: coverage × 4B-confidence | F1 | gbt | 0.3870 | -0.0059 [-0.024, +0.013] | -0.06 [-0.26, +0.11] | -0.0071 [-0.017, +0.002] |
| independent: coverage × 4B-confidence | F2 | logreg | 0.3680 | -0.0249 [-0.044, -0.005] | -0.24 [-0.46, -0.04] | -0.0260 [-0.040, -0.012] |
| independent: coverage × 4B-confidence | F2 | gbt | 0.3870 | -0.0059 [-0.024, +0.013] | -0.06 [-0.26, +0.11] | -0.0071 [-0.017, +0.002] |
| independent: coverage × 4B-confidence | F3 | logreg | 0.3680 | -0.0249 [-0.044, -0.005] | -0.24 [-0.46, -0.04] | -0.0260 [-0.040, -0.012] |
| independent: coverage × 4B-confidence | F3 | gbt | 0.3870 | -0.0059 [-0.024, +0.013] | -0.06 [-0.26, +0.11] | -0.0071 [-0.017, +0.002] |
| independent: coverage × 4B-confidence | F4 | logreg | 0.2852 | -0.1077 [-0.138, -0.077] | -1.02 [-1.53, -0.64] | -0.1089 [-0.144, -0.075] |
| independent: coverage × 4B-confidence | F4 | gbt | 0.2852 | -0.1077 [-0.138, -0.077] | -1.02 [-1.53, -0.64] | -0.1089 [-0.144, -0.075] |
| independent: coverage × F2 classifier | F1 | logreg | 0.3053 | -0.0876 [-0.117, -0.058] | -0.83 [-1.29, -0.49] | -0.0888 [-0.122, -0.057] |
| independent: coverage × F2 classifier | F1 | gbt | 0.3290 | -0.0639 [-0.093, -0.035] | -0.61 [-1.01, -0.30] | -0.0651 [-0.100, -0.031] |
| independent: coverage × F2 classifier | F2 | logreg | 0.3053 | -0.0876 [-0.117, -0.058] | -0.83 [-1.29, -0.49] | -0.0888 [-0.122, -0.057] |
| independent: coverage × F2 classifier | F2 | gbt | 0.3290 | -0.0639 [-0.093, -0.035] | -0.61 [-1.01, -0.30] | -0.0651 [-0.100, -0.031] |
| independent: coverage × F2 classifier | F3 | logreg | 0.3053 | -0.0876 [-0.117, -0.058] | -0.83 [-1.29, -0.49] | -0.0888 [-0.122, -0.057] |
| independent: coverage × F2 classifier | F3 | gbt | 0.3290 | -0.0639 [-0.093, -0.035] | -0.61 [-1.01, -0.30] | -0.0651 [-0.100, -0.031] |
| independent: coverage × F2 classifier | F4 | logreg | 0.2840 | -0.1089 [-0.139, -0.078] | -1.03 [-1.55, -0.66] | -0.1101 [-0.146, -0.075] |
| independent: coverage × F2 classifier | F4 | gbt | 0.2840 | -0.1089 [-0.139, -0.078] | -1.03 [-1.55, -0.66] | -0.1101 [-0.146, -0.075] |
| capability-only | F1 | logreg | 0.3917 | -0.0012 [-0.020, +0.018] | -0.01 [-0.21, +0.16] | -0.0024 [-0.008, +0.003] |
| capability-only | F1 | gbt | 0.3870 | -0.0059 [-0.024, +0.012] | -0.06 [-0.25, +0.10] | -0.0071 [-0.018, +0.004] |
| capability-only | F2 | logreg | 0.3740 | -0.0189 [-0.039, +0.001] | -0.18 [-0.42, +0.01] | -0.0201 [-0.035, -0.006] |
| capability-only | F2 | gbt | 0.3822 | -0.0107 [-0.031, +0.011] | -0.10 [-0.34, +0.09] | -0.0118 [-0.027, +0.002] |
| capability-only | F3 | logreg | 0.3763 | -0.0166 [-0.036, +0.005] | -0.16 [-0.39, +0.04] | -0.0178 [-0.033, -0.003] |
| capability-only | F3 | gbt | 0.3763 | -0.0166 [-0.037, +0.004] | -0.16 [-0.40, +0.03] | -0.0178 [-0.032, -0.004] |
| capability-only | F4 | logreg | 0.0722 | -0.3207 [-0.353, -0.289] | -3.04 [-3.88, -2.39] | -0.3219 [-0.357, -0.288] |
| capability-only | F4 | gbt | 0.0722 | -0.3207 [-0.353, -0.289] | -3.04 [-3.88, -2.39] | -0.3219 [-0.357, -0.288] |
| evidence-only | F1 | logreg | 0.3941 | +0.0012 [-0.017, +0.020] | +0.01 [-0.18, +0.18] | +0.0000 [+0.000, +0.000] |
| evidence-only | F1 | gbt | 0.3941 | +0.0012 [-0.017, +0.020] | +0.01 [-0.18, +0.18] | +0.0000 [+0.000, +0.000] |
| evidence-only | F2 | logreg | 0.3929 | +0.0000 [-0.018, +0.019] | +0.00 [-0.19, +0.17] | -0.0012 [-0.004, +0.000] |
| evidence-only | F2 | gbt | 0.3941 | +0.0012 [-0.017, +0.020] | +0.01 [-0.18, +0.18] | +0.0000 [+0.000, +0.000] |
| evidence-only | F3 | logreg | 0.3917 | -0.0012 [-0.019, +0.018] | -0.01 [-0.20, +0.16] | -0.0024 [-0.006, +0.000] |
| evidence-only | F3 | gbt | 0.3941 | +0.0012 [-0.017, +0.020] | +0.01 [-0.18, +0.18] | +0.0000 [+0.000, +0.000] |
| evidence-only | F4 | logreg | 0.0095 | -0.3834 [-0.419, -0.348] | -3.64 [-4.59, -2.88] | -0.3846 [-0.420, -0.349] |
| evidence-only | F4 | gbt | 0.0095 | -0.3834 [-0.419, -0.348] | -3.64 [-4.59, -2.88] | -0.3846 [-0.420, -0.349] |
| combined (all four cells) | F1 | logreg | 0.3929 | +0.0000 [-0.016, +0.016] | +0.00 [-0.17, +0.14] | -0.0012 [-0.017, +0.014] |
| combined (all four cells) | F1 | gbt | 0.3775 | -0.0154 [-0.034, +0.004] | -0.15 [-0.35, +0.03] | -0.0166 [-0.038, +0.004] |
| combined (all four cells) | F2 | logreg | 0.3645 | -0.0284 [-0.053, -0.005] | -0.27 [-0.57, -0.04] | -0.0296 [-0.053, -0.006] |
| combined (all four cells) | F2 | gbt | 0.3680 | -0.0249 [-0.049, -0.002] | -0.24 [-0.52, -0.02] | -0.0260 [-0.048, -0.004] |
| combined (all four cells) | F3 | logreg | 0.3645 | -0.0284 [-0.053, -0.003] | -0.27 [-0.57, -0.03] | -0.0296 [-0.054, -0.005] |
| combined (all four cells) | F3 | gbt | 0.3692 | -0.0237 [-0.047, -0.001] | -0.22 [-0.50, -0.01] | -0.0249 [-0.046, -0.002] |
| combined (all four cells) | F4 | logreg | 0.2852 | -0.1077 [-0.138, -0.077] | -1.02 [-1.54, -0.65] | -0.1089 [-0.144, -0.074] |
| combined (all four cells) | F4 | gbt | 0.2828 | -0.1101 [-0.140, -0.079] | -1.04 [-1.57, -0.67] | -0.1112 [-0.147, -0.076] |

**88 Mbit/s / png / 10s s** — oracle 0.5337, best static 0.3953, per-type 0.3858

| policy | feature set | learner | utility | Δ vs per-type [95% CI] | headroom fraction [95% CI] | Δ vs best static [95% CI] |
|---|---|---|---|---|---|---|
| oracle (upper bound) | F1 | logreg | 0.5337 | +0.1479 [+0.124, +0.175] | +1.00 [+1.00, +1.00] | +0.1385 [+0.115, +0.162] |
| best static cell | F1 | logreg | 0.3953 | +0.0095 [-0.010, +0.030] | +0.06 [-0.07, +0.19] | +0.0000 [+0.000, +0.000] |
| per-type lookup | F1 | logreg | 0.3858 | +0.0000 [+0.000, +0.000] | +0.00 [+0.00, +0.00] | -0.0095 [-0.030, +0.010] |
| independent: coverage × always-32B | F1 | logreg | 0.3882 | +0.0024 [-0.021, +0.026] | +0.02 [-0.15, +0.17] | -0.0071 [-0.033, +0.017] |
| independent: coverage × always-32B | F1 | gbt | 0.3775 | -0.0083 [-0.033, +0.015] | -0.06 [-0.25, +0.10] | -0.0178 [-0.044, +0.007] |
| independent: coverage × always-32B | F2 | logreg | 0.3882 | +0.0024 [-0.021, +0.026] | +0.02 [-0.15, +0.17] | -0.0071 [-0.033, +0.017] |
| independent: coverage × always-32B | F2 | gbt | 0.3775 | -0.0083 [-0.033, +0.015] | -0.06 [-0.25, +0.10] | -0.0178 [-0.044, +0.007] |
| independent: coverage × always-32B | F3 | logreg | 0.3882 | +0.0024 [-0.021, +0.026] | +0.02 [-0.15, +0.17] | -0.0071 [-0.033, +0.017] |
| independent: coverage × always-32B | F3 | gbt | 0.3775 | -0.0083 [-0.033, +0.015] | -0.06 [-0.25, +0.10] | -0.0178 [-0.044, +0.007] |
| independent: coverage × always-32B | F4 | logreg | 0.3302 | -0.0556 [-0.080, -0.031] | -0.38 [-0.60, -0.19] | -0.0651 [-0.082, -0.047] |
| independent: coverage × always-32B | F4 | gbt | 0.3408 | -0.0450 [-0.069, -0.021] | -0.30 [-0.51, -0.13] | -0.0544 [-0.070, -0.039] |
| independent: coverage × 4B-confidence | F1 | logreg | 0.3787 | -0.0071 [-0.030, +0.016] | -0.05 [-0.23, +0.10] | -0.0166 [-0.042, +0.008] |
| independent: coverage × 4B-confidence | F1 | gbt | 0.3692 | -0.0166 [-0.042, +0.008] | -0.11 [-0.31, +0.05] | -0.0260 [-0.053, -0.001] |
| independent: coverage × 4B-confidence | F2 | logreg | 0.3787 | -0.0071 [-0.030, +0.016] | -0.05 [-0.23, +0.10] | -0.0166 [-0.042, +0.008] |
| independent: coverage × 4B-confidence | F2 | gbt | 0.3692 | -0.0166 [-0.042, +0.008] | -0.11 [-0.31, +0.05] | -0.0260 [-0.053, -0.001] |
| independent: coverage × 4B-confidence | F3 | logreg | 0.3787 | -0.0071 [-0.030, +0.016] | -0.05 [-0.23, +0.10] | -0.0166 [-0.042, +0.008] |
| independent: coverage × 4B-confidence | F3 | gbt | 0.3692 | -0.0166 [-0.042, +0.008] | -0.11 [-0.31, +0.05] | -0.0260 [-0.053, -0.001] |
| independent: coverage × 4B-confidence | F4 | logreg | 0.3290 | -0.0568 [-0.082, -0.033] | -0.38 [-0.61, -0.20] | -0.0663 [-0.085, -0.048] |
| independent: coverage × 4B-confidence | F4 | gbt | 0.3396 | -0.0462 [-0.071, -0.022] | -0.31 [-0.53, -0.14] | -0.0556 [-0.072, -0.039] |
| independent: coverage × F2 classifier | F1 | logreg | 0.3444 | -0.0414 [-0.071, -0.012] | -0.28 [-0.54, -0.07] | -0.0509 [-0.084, -0.018] |
| independent: coverage × F2 classifier | F1 | gbt | 0.3349 | -0.0509 [-0.083, -0.019] | -0.34 [-0.64, -0.12] | -0.0604 [-0.096, -0.025] |
| independent: coverage × F2 classifier | F2 | logreg | 0.3444 | -0.0414 [-0.071, -0.012] | -0.28 [-0.54, -0.07] | -0.0509 [-0.084, -0.018] |
| independent: coverage × F2 classifier | F2 | gbt | 0.3349 | -0.0509 [-0.083, -0.019] | -0.34 [-0.64, -0.12] | -0.0604 [-0.096, -0.025] |
| independent: coverage × F2 classifier | F3 | logreg | 0.3444 | -0.0414 [-0.071, -0.012] | -0.28 [-0.54, -0.07] | -0.0509 [-0.084, -0.018] |
| independent: coverage × F2 classifier | F3 | gbt | 0.3349 | -0.0509 [-0.083, -0.019] | -0.34 [-0.64, -0.12] | -0.0604 [-0.096, -0.025] |
| independent: coverage × F2 classifier | F4 | logreg | 0.2781 | -0.1077 [-0.140, -0.075] | -0.73 [-1.08, -0.46] | -0.1172 [-0.151, -0.084] |
| independent: coverage × F2 classifier | F4 | gbt | 0.2817 | -0.1041 [-0.137, -0.070] | -0.70 [-1.06, -0.43] | -0.1136 [-0.148, -0.080] |
| capability-only | F1 | logreg | 0.3917 | +0.0059 [-0.014, +0.026] | +0.04 [-0.11, +0.17] | -0.0036 [-0.010, +0.002] |
| capability-only | F1 | gbt | 0.3870 | +0.0012 [-0.018, +0.021] | +0.01 [-0.13, +0.13] | -0.0083 [-0.020, +0.002] |
| capability-only | F2 | logreg | 0.3740 | -0.0118 [-0.035, +0.012] | -0.08 [-0.26, +0.07] | -0.0213 [-0.036, -0.007] |
| capability-only | F2 | gbt | 0.3822 | -0.0036 [-0.026, +0.020] | -0.02 [-0.19, +0.13] | -0.0130 [-0.028, +0.001] |
| capability-only | F3 | logreg | 0.3763 | -0.0095 [-0.032, +0.015] | -0.06 [-0.24, +0.09] | -0.0189 [-0.034, -0.004] |
| capability-only | F3 | gbt | 0.3763 | -0.0095 [-0.032, +0.013] | -0.06 [-0.23, +0.08] | -0.0189 [-0.034, -0.005] |
| capability-only | F4 | logreg | 0.3254 | -0.0604 [-0.085, -0.035] | -0.41 [-0.65, -0.22] | -0.0698 [-0.089, -0.051] |
| capability-only | F4 | gbt | 0.3254 | -0.0604 [-0.085, -0.036] | -0.41 [-0.64, -0.22] | -0.0698 [-0.089, -0.050] |
| evidence-only | F1 | logreg | 0.4036 | +0.0178 [+0.001, +0.035] | +0.12 [+0.01, +0.23] | +0.0083 [-0.004, +0.021] |
| evidence-only | F1 | gbt | 0.4036 | +0.0178 [-0.001, +0.036] | +0.12 [-0.01, +0.23] | +0.0083 [-0.009, +0.025] |
| evidence-only | F2 | logreg | 0.3964 | +0.0107 [-0.008, +0.031] | +0.07 [-0.06, +0.20] | +0.0012 [-0.017, +0.020] |
| evidence-only | F2 | gbt | 0.3834 | -0.0024 [-0.023, +0.018] | -0.02 [-0.17, +0.11] | -0.0118 [-0.030, +0.005] |
| evidence-only | F3 | logreg | 0.3953 | +0.0095 [-0.012, +0.031] | +0.06 [-0.08, +0.20] | +0.0000 [-0.019, +0.018] |
| evidence-only | F3 | gbt | 0.3870 | +0.0012 [-0.019, +0.022] | +0.01 [-0.15, +0.14] | -0.0083 [-0.026, +0.008] |
| evidence-only | F4 | logreg | 0.3408 | -0.0450 [-0.069, -0.021] | -0.30 [-0.51, -0.13] | -0.0544 [-0.070, -0.039] |
| evidence-only | F4 | gbt | 0.3408 | -0.0450 [-0.069, -0.021] | -0.30 [-0.51, -0.13] | -0.0544 [-0.070, -0.039] |
| combined (all four cells) | F1 | logreg | 0.4024 | +0.0166 [+0.002, +0.032] | +0.11 [+0.02, +0.21] | +0.0071 [-0.009, +0.024] |
| combined (all four cells) | F1 | gbt | 0.3893 | +0.0036 [-0.017, +0.023] | +0.02 [-0.12, +0.15] | -0.0059 [-0.029, +0.017] |
| combined (all four cells) | F2 | logreg | 0.3751 | -0.0107 [-0.034, +0.014] | -0.07 [-0.25, +0.09] | -0.0201 [-0.044, +0.004] |
| combined (all four cells) | F2 | gbt | 0.3740 | -0.0118 [-0.034, +0.011] | -0.08 [-0.26, +0.07] | -0.0213 [-0.044, +0.001] |
| combined (all four cells) | F3 | logreg | 0.3704 | -0.0154 [-0.039, +0.011] | -0.10 [-0.30, +0.06] | -0.0249 [-0.049, +0.000] |
| combined (all four cells) | F3 | gbt | 0.3740 | -0.0118 [-0.036, +0.012] | -0.08 [-0.27, +0.08] | -0.0213 [-0.045, +0.002] |
| combined (all four cells) | F4 | logreg | 0.3089 | -0.0769 [-0.106, -0.049] | -0.52 [-0.81, -0.30] | -0.0864 [-0.112, -0.061] |
| combined (all four cells) | F4 | gbt | 0.3136 | -0.0722 [-0.100, -0.045] | -0.49 [-0.75, -0.28] | -0.0817 [-0.106, -0.059] |

**13.6 Mbit/s / png / 10s s** — oracle 0.4308, best static 0.3941, per-type 0.3917

| policy | feature set | learner | utility | Δ vs per-type [95% CI] | headroom fraction [95% CI] | Δ vs best static [95% CI] |
|---|---|---|---|---|---|---|
| oracle (upper bound) | F1 | logreg | 0.4308 | +0.0391 [+0.027, +0.053] | +1.00 [+1.00, +1.00] | +0.0367 [+0.025, +0.050] |
| best static cell | F1 | logreg | 0.3941 | +0.0024 [-0.007, +0.013] | +0.06 [-0.22, +0.29] | +0.0000 [+0.000, +0.000] |
| per-type lookup | F1 | logreg | 0.3917 | +0.0000 [+0.000, +0.000] | +0.00 [+0.00, +0.00] | -0.0024 [-0.013, +0.007] |
| independent: coverage × always-32B | F1 | logreg | 0.3586 | -0.0331 [-0.050, -0.017] | -0.85 [-1.58, -0.38] | -0.0355 [-0.049, -0.023] |
| independent: coverage × always-32B | F1 | gbt | 0.3941 | +0.0024 [-0.007, +0.013] | +0.06 [-0.22, +0.29] | +0.0000 [+0.000, +0.000] |
| independent: coverage × always-32B | F2 | logreg | 0.3586 | -0.0331 [-0.050, -0.017] | -0.85 [-1.58, -0.38] | -0.0355 [-0.049, -0.023] |
| independent: coverage × always-32B | F2 | gbt | 0.3941 | +0.0024 [-0.007, +0.013] | +0.06 [-0.22, +0.29] | +0.0000 [+0.000, +0.000] |
| independent: coverage × always-32B | F3 | logreg | 0.3586 | -0.0331 [-0.050, -0.017] | -0.85 [-1.58, -0.38] | -0.0355 [-0.049, -0.023] |
| independent: coverage × always-32B | F3 | gbt | 0.3941 | +0.0024 [-0.007, +0.013] | +0.06 [-0.22, +0.29] | +0.0000 [+0.000, +0.000] |
| independent: coverage × always-32B | F4 | logreg | 0.0071 | -0.3846 [-0.420, -0.349] | -9.85 [-14.65, -7.05] | -0.3870 [-0.422, -0.351] |
| independent: coverage × always-32B | F4 | gbt | 0.0071 | -0.3846 [-0.420, -0.349] | -9.85 [-14.65, -7.05] | -0.3870 [-0.422, -0.351] |
| independent: coverage × 4B-confidence | F1 | logreg | 0.3325 | -0.0592 [-0.078, -0.041] | -1.52 [-2.54, -0.88] | -0.0615 [-0.080, -0.046] |
| independent: coverage × 4B-confidence | F1 | gbt | 0.3669 | -0.0249 [-0.039, -0.011] | -0.64 [-1.27, -0.25] | -0.0272 [-0.040, -0.016] |
| independent: coverage × 4B-confidence | F2 | logreg | 0.3325 | -0.0592 [-0.078, -0.041] | -1.52 [-2.54, -0.88] | -0.0615 [-0.080, -0.046] |
| independent: coverage × 4B-confidence | F2 | gbt | 0.3669 | -0.0249 [-0.039, -0.011] | -0.64 [-1.27, -0.25] | -0.0272 [-0.040, -0.016] |
| independent: coverage × 4B-confidence | F3 | logreg | 0.3325 | -0.0592 [-0.078, -0.041] | -1.52 [-2.54, -0.88] | -0.0615 [-0.080, -0.046] |
| independent: coverage × 4B-confidence | F3 | gbt | 0.3669 | -0.0249 [-0.039, -0.011] | -0.64 [-1.27, -0.25] | -0.0272 [-0.040, -0.016] |
| independent: coverage × 4B-confidence | F4 | logreg | 0.0071 | -0.3846 [-0.420, -0.349] | -9.85 [-14.65, -7.05] | -0.3870 [-0.422, -0.351] |
| independent: coverage × 4B-confidence | F4 | gbt | 0.0071 | -0.3846 [-0.420, -0.349] | -9.85 [-14.65, -7.05] | -0.3870 [-0.422, -0.351] |
| independent: coverage × F2 classifier | F1 | logreg | 0.2852 | -0.1065 [-0.132, -0.080] | -2.73 [-4.67, -1.67] | -0.1089 [-0.134, -0.082] |
| independent: coverage × F2 classifier | F1 | gbt | 0.3598 | -0.0320 [-0.052, -0.012] | -0.82 [-1.80, -0.25] | -0.0343 [-0.056, -0.013] |
| independent: coverage × F2 classifier | F2 | logreg | 0.2852 | -0.1065 [-0.132, -0.080] | -2.73 [-4.67, -1.67] | -0.1089 [-0.134, -0.082] |
| independent: coverage × F2 classifier | F2 | gbt | 0.3598 | -0.0320 [-0.052, -0.012] | -0.82 [-1.80, -0.25] | -0.0343 [-0.056, -0.013] |
| independent: coverage × F2 classifier | F3 | logreg | 0.2852 | -0.1065 [-0.132, -0.080] | -2.73 [-4.67, -1.67] | -0.1089 [-0.134, -0.082] |
| independent: coverage × F2 classifier | F3 | gbt | 0.3598 | -0.0320 [-0.052, -0.012] | -0.82 [-1.80, -0.25] | -0.0343 [-0.056, -0.013] |
| independent: coverage × F2 classifier | F4 | logreg | 0.0047 | -0.3870 [-0.422, -0.353] | -9.91 [-14.77, -7.10] | -0.3893 [-0.424, -0.354] |
| independent: coverage × F2 classifier | F4 | gbt | 0.0047 | -0.3870 [-0.422, -0.353] | -9.91 [-14.77, -7.10] | -0.3893 [-0.424, -0.354] |
| capability-only | F1 | logreg | 0.3917 | +0.0000 [-0.011, +0.012] | +0.00 [-0.31, +0.27] | -0.0024 [-0.008, +0.003] |
| capability-only | F1 | gbt | 0.3870 | -0.0047 [-0.017, +0.007] | -0.12 [-0.54, +0.16] | -0.0071 [-0.018, +0.004] |
| capability-only | F2 | logreg | 0.3740 | -0.0178 [-0.033, -0.002] | -0.45 [-1.08, -0.05] | -0.0201 [-0.035, -0.006] |
| capability-only | F2 | gbt | 0.3822 | -0.0095 [-0.025, +0.005] | -0.24 [-0.78, +0.12] | -0.0118 [-0.027, +0.002] |
| capability-only | F3 | logreg | 0.3763 | -0.0154 [-0.031, +0.001] | -0.39 [-1.04, +0.03] | -0.0178 [-0.033, -0.003] |
| capability-only | F3 | gbt | 0.3763 | -0.0154 [-0.030, -0.001] | -0.39 [-0.96, -0.03] | -0.0178 [-0.032, -0.004] |
| capability-only | F4 | logreg | 0.0036 | -0.3882 [-0.424, -0.353] | -9.94 [-14.77, -7.13] | -0.3905 [-0.427, -0.355] |
| capability-only | F4 | gbt | 0.0036 | -0.3882 [-0.424, -0.353] | -9.94 [-14.77, -7.13] | -0.3905 [-0.427, -0.355] |
| evidence-only | F1 | logreg | 0.3941 | +0.0024 [-0.007, +0.013] | +0.06 [-0.22, +0.29] | +0.0000 [+0.000, +0.000] |
| evidence-only | F1 | gbt | 0.3941 | +0.0024 [-0.007, +0.013] | +0.06 [-0.22, +0.29] | +0.0000 [+0.000, +0.000] |
| evidence-only | F2 | logreg | 0.3929 | +0.0012 [-0.008, +0.012] | +0.03 [-0.26, +0.27] | -0.0012 [-0.004, +0.000] |
| evidence-only | F2 | gbt | 0.3941 | +0.0024 [-0.007, +0.013] | +0.06 [-0.22, +0.29] | +0.0000 [+0.000, +0.000] |
| evidence-only | F3 | logreg | 0.3917 | +0.0000 [-0.010, +0.011] | +0.00 [-0.31, +0.24] | -0.0024 [-0.006, +0.000] |
| evidence-only | F3 | gbt | 0.3941 | +0.0024 [-0.007, +0.013] | +0.06 [-0.22, +0.29] | +0.0000 [+0.000, +0.000] |
| evidence-only | F4 | logreg | 0.0036 | -0.3882 [-0.424, -0.352] | -9.94 [-14.79, -7.11] | -0.3905 [-0.427, -0.354] |
| evidence-only | F4 | gbt | 0.0036 | -0.3882 [-0.424, -0.352] | -9.94 [-14.79, -7.11] | -0.3905 [-0.427, -0.354] |
| combined (all four cells) | F1 | logreg | 0.3929 | +0.0012 [-0.009, +0.013] | +0.03 [-0.28, +0.28] | -0.0012 [-0.007, +0.005] |
| combined (all four cells) | F1 | gbt | 0.3870 | -0.0047 [-0.017, +0.007] | -0.12 [-0.54, +0.16] | -0.0071 [-0.018, +0.004] |
| combined (all four cells) | F2 | logreg | 0.3716 | -0.0201 [-0.036, -0.005] | -0.52 [-1.20, -0.10] | -0.0225 [-0.038, -0.008] |
| combined (all four cells) | F2 | gbt | 0.3822 | -0.0095 [-0.025, +0.005] | -0.24 [-0.78, +0.12] | -0.0118 [-0.027, +0.002] |
| combined (all four cells) | F3 | logreg | 0.3740 | -0.0178 [-0.034, -0.001] | -0.45 [-1.14, -0.03] | -0.0201 [-0.036, -0.005] |
| combined (all four cells) | F3 | gbt | 0.3763 | -0.0154 [-0.030, -0.001] | -0.39 [-0.96, -0.03] | -0.0178 [-0.032, -0.004] |
| combined (all four cells) | F4 | logreg | 0.0059 | -0.3858 [-0.421, -0.351] | -9.88 [-14.73, -7.09] | -0.3882 [-0.423, -0.352] |
| combined (all four cells) | F4 | gbt | 0.0047 | -0.3870 [-0.422, -0.353] | -9.91 [-14.77, -7.10] | -0.3893 [-0.424, -0.354] |

## 9. The pre-registered contrast: combined minus best independent baseline

| setting | feature set | learner | best independent variant | independent | combined | paired diff | 95% CI | CI excludes 0 |
|---|---|---|---|---|---|---|---|---|
| accuracy: b32=0.25, bRICH=0.25 | F2 | logreg | `always32B` | 0.3547 | 0.3577 | +0.0030 | [-0.021, +0.026] | no |
| accuracy: b32=0.25, bRICH=0.5 | F2 | logreg | `always32B` | 0.3547 | 0.3491 | -0.0056 | [-0.030, +0.018] | no |
| accuracy: b32=0.25, bRICH=1.0 | F2 | logreg | `always32B` | 0.3547 | 0.3491 | -0.0056 | [-0.030, +0.018] | no |
| accuracy: b32=0.5, bRICH=0.25 | F2 | logreg | `always32B` | 0.3680 | 0.3728 | +0.0047 | [-0.020, +0.031] | no |
| accuracy: b32=0.5, bRICH=0.5 | F2 | logreg | `always32B` | 0.3680 | 0.3698 | +0.0018 | [-0.024, +0.028] | no |
| accuracy: b32=0.5, bRICH=1.0 | F2 | logreg | `always32B` | 0.3680 | 0.3698 | +0.0018 | [-0.024, +0.028] | no |
| accuracy: b32=1.0, bRICH=0.25 | F2 | logreg | `always32B` | 0.3882 | 0.3751 | -0.0130 | [-0.040, +0.015] | no |
| accuracy: b32=1.0, bRICH=0.5 | F2 | logreg | `always32B` | 0.3882 | 0.3740 | -0.0142 | [-0.040, +0.013] | no |
| accuracy: b32=1.0, bRICH=1.0 | F2 | logreg | `always32B` | 0.3882 | 0.3740 | -0.0142 | [-0.040, +0.013] | no |
| utility: 88 Mbit/s / png / 5s s | F2 | logreg | `always32B` | 0.3740 | 0.3645 | -0.0095 | [-0.033, +0.014] | no |
| utility: 88 Mbit/s / png / 10s s | F2 | logreg | `always32B` | 0.3882 | 0.3751 | -0.0130 | [-0.036, +0.012] | no |
| utility: 13.6 Mbit/s / png / 10s s | F2 | logreg | `always32B` | 0.3586 | 0.3716 | +0.0130 | [-0.005, +0.031] | no |
| accuracy: b32=0.25, bRICH=0.25 | F3 | logreg | `always32B` | 0.3547 | 0.3589 | +0.0041 | [-0.019, +0.027] | no |
| accuracy: b32=0.25, bRICH=0.5 | F3 | logreg | `always32B` | 0.3547 | 0.3482 | -0.0065 | [-0.031, +0.018] | no |
| accuracy: b32=0.25, bRICH=1.0 | F3 | logreg | `always32B` | 0.3547 | 0.3482 | -0.0065 | [-0.031, +0.018] | no |
| accuracy: b32=0.5, bRICH=0.25 | F3 | logreg | `always32B` | 0.3680 | 0.3781 | +0.0101 | [-0.014, +0.037] | no |
| accuracy: b32=0.5, bRICH=0.5 | F3 | logreg | `always32B` | 0.3680 | 0.3710 | +0.0030 | [-0.023, +0.030] | no |
| accuracy: b32=0.5, bRICH=1.0 | F3 | logreg | `always32B` | 0.3680 | 0.3710 | +0.0030 | [-0.023, +0.030] | no |
| accuracy: b32=1.0, bRICH=0.25 | F3 | logreg | `always32B` | 0.3882 | 0.3751 | -0.0130 | [-0.038, +0.013] | no |
| accuracy: b32=1.0, bRICH=0.5 | F3 | logreg | `always32B` | 0.3882 | 0.3692 | -0.0189 | [-0.045, +0.009] | no |
| accuracy: b32=1.0, bRICH=1.0 | F3 | logreg | `always32B` | 0.3882 | 0.3692 | -0.0189 | [-0.045, +0.009] | no |
| utility: 88 Mbit/s / png / 5s s | F3 | logreg | `always32B` | 0.3740 | 0.3645 | -0.0095 | [-0.033, +0.014] | no |
| utility: 88 Mbit/s / png / 10s s | F3 | logreg | `always32B` | 0.3882 | 0.3704 | -0.0178 | [-0.042, +0.008] | no |
| utility: 13.6 Mbit/s / png / 10s s | F3 | logreg | `always32B` | 0.3586 | 0.3740 | +0.0154 | [-0.002, +0.034] | no |
| accuracy: b32=0.25, bRICH=0.25 | F4 | logreg | `always32B` | 0.3547 | 0.3518 | -0.0030 | [-0.027, +0.020] | no |
| accuracy: b32=0.25, bRICH=0.5 | F4 | logreg | `always32B` | 0.3547 | 0.3396 | -0.0151 | [-0.040, +0.009] | no |
| accuracy: b32=0.25, bRICH=1.0 | F4 | logreg | `always32B` | 0.3547 | 0.3396 | -0.0151 | [-0.040, +0.009] | no |
| accuracy: b32=0.5, bRICH=0.25 | F4 | logreg | `always32B` | 0.3680 | 0.3749 | +0.0068 | [-0.018, +0.032] | no |
| accuracy: b32=0.5, bRICH=0.5 | F4 | logreg | `always32B` | 0.3680 | 0.3633 | -0.0047 | [-0.031, +0.023] | no |
| accuracy: b32=0.5, bRICH=1.0 | F4 | logreg | `always32B` | 0.3680 | 0.3633 | -0.0047 | [-0.031, +0.023] | no |
| accuracy: b32=1.0, bRICH=0.25 | F4 | logreg | `always32B` | 0.3882 | 0.3751 | -0.0130 | [-0.037, +0.011] | no |
| accuracy: b32=1.0, bRICH=0.5 | F4 | logreg | `always32B` | 0.3882 | 0.3692 | -0.0189 | [-0.044, +0.006] | no |
| accuracy: b32=1.0, bRICH=1.0 | F4 | logreg | `always32B` | 0.3882 | 0.3692 | -0.0189 | [-0.044, +0.006] | no |
| utility: 88 Mbit/s / png / 5s s | F4 | logreg | `always32B` | 0.2852 | 0.2852 | +0.0000 | [-0.004, +0.004] | no |
| utility: 88 Mbit/s / png / 10s s | F4 | logreg | `always32B` | 0.3302 | 0.3089 | -0.0213 | [-0.045, +0.001] | no |
| utility: 13.6 Mbit/s / png / 10s s | F4 | logreg | `always32B` | 0.0071 | 0.0059 | -0.0012 | [-0.004, +0.000] | no |
| accuracy: b32=0.25, bRICH=0.25 | F2 | gbt | `always32B` | 0.3527 | 0.3586 | +0.0059 | [-0.015, +0.027] | no |
| accuracy: b32=0.25, bRICH=0.5 | F2 | gbt | `always32B` | 0.3527 | 0.3538 | +0.0012 | [-0.022, +0.024] | no |
| accuracy: b32=0.25, bRICH=1.0 | F2 | gbt | `always32B` | 0.3527 | 0.3538 | +0.0012 | [-0.022, +0.024] | no |
| accuracy: b32=0.5, bRICH=0.25 | F2 | gbt | `always32B` | 0.3728 | 0.3672 | -0.0056 | [-0.031, +0.018] | no |
| accuracy: b32=0.5, bRICH=0.5 | F2 | gbt | `always32B` | 0.3728 | 0.3680 | -0.0047 | [-0.032, +0.022] | no |
| accuracy: b32=0.5, bRICH=1.0 | F2 | gbt | `always32B` | 0.3728 | 0.3680 | -0.0047 | [-0.032, +0.022] | no |
| accuracy: b32=1.0, bRICH=0.25 | F2 | gbt | `always32B` | 0.3775 | 0.3740 | -0.0036 | [-0.024, +0.018] | no |
| accuracy: b32=1.0, bRICH=0.5 | F2 | gbt | `always32B` | 0.3775 | 0.3728 | -0.0047 | [-0.027, +0.019] | no |
| accuracy: b32=1.0, bRICH=1.0 | F2 | gbt | `always32B` | 0.3775 | 0.3728 | -0.0047 | [-0.027, +0.019] | no |
| utility: 88 Mbit/s / png / 5s s | F2 | gbt | `always32B` | 0.3941 | 0.3680 | -0.0260 | [-0.048, -0.004] | **yes** (**combined worse**) |
| utility: 88 Mbit/s / png / 10s s | F2 | gbt | `always32B` | 0.3775 | 0.3740 | -0.0036 | [-0.026, +0.019] | no |
| utility: 13.6 Mbit/s / png / 10s s | F2 | gbt | `always32B` | 0.3941 | 0.3822 | -0.0118 | [-0.027, +0.002] | no |
| accuracy: b32=0.25, bRICH=0.25 | F3 | gbt | `always32B` | 0.3527 | 0.3506 | -0.0021 | [-0.022, +0.019] | no |
| accuracy: b32=0.25, bRICH=0.5 | F3 | gbt | `always32B` | 0.3527 | 0.3518 | -0.0009 | [-0.024, +0.020] | no |
| accuracy: b32=0.25, bRICH=1.0 | F3 | gbt | `always32B` | 0.3527 | 0.3518 | -0.0009 | [-0.024, +0.020] | no |
| accuracy: b32=0.5, bRICH=0.25 | F3 | gbt | `always32B` | 0.3728 | 0.3609 | -0.0118 | [-0.038, +0.013] | no |
| accuracy: b32=0.5, bRICH=0.5 | F3 | gbt | `always32B` | 0.3728 | 0.3728 | +0.0000 | [-0.028, +0.027] | no |
| accuracy: b32=0.5, bRICH=1.0 | F3 | gbt | `always32B` | 0.3728 | 0.3728 | +0.0000 | [-0.028, +0.027] | no |
| accuracy: b32=1.0, bRICH=0.25 | F3 | gbt | `always32B` | 0.3775 | 0.3624 | -0.0151 | [-0.037, +0.006] | no |
| accuracy: b32=1.0, bRICH=0.5 | F3 | gbt | `always32B` | 0.3775 | 0.3680 | -0.0095 | [-0.033, +0.015] | no |
| accuracy: b32=1.0, bRICH=1.0 | F3 | gbt | `always32B` | 0.3775 | 0.3680 | -0.0095 | [-0.033, +0.015] | no |
| utility: 88 Mbit/s / png / 5s s | F3 | gbt | `always32B` | 0.3941 | 0.3692 | -0.0249 | [-0.046, -0.002] | **yes** (**combined worse**) |
| utility: 88 Mbit/s / png / 10s s | F3 | gbt | `always32B` | 0.3775 | 0.3740 | -0.0036 | [-0.026, +0.020] | no |
| utility: 13.6 Mbit/s / png / 10s s | F3 | gbt | `always32B` | 0.3941 | 0.3763 | -0.0178 | [-0.032, -0.004] | **yes** (**combined worse**) |
| accuracy: b32=0.25, bRICH=0.25 | F4 | gbt | `always32B` | 0.3527 | 0.3612 | +0.0086 | [-0.013, +0.030] | no |
| accuracy: b32=0.25, bRICH=0.5 | F4 | gbt | `always32B` | 0.3527 | 0.3530 | +0.0003 | [-0.023, +0.023] | no |
| accuracy: b32=0.25, bRICH=1.0 | F4 | gbt | `always32B` | 0.3527 | 0.3530 | +0.0003 | [-0.023, +0.023] | no |
| accuracy: b32=0.5, bRICH=0.25 | F4 | gbt | `always32B` | 0.3728 | 0.3694 | -0.0034 | [-0.028, +0.020] | no |
| accuracy: b32=0.5, bRICH=0.5 | F4 | gbt | `always32B` | 0.3728 | 0.3633 | -0.0095 | [-0.036, +0.017] | no |
| accuracy: b32=0.5, bRICH=1.0 | F4 | gbt | `always32B` | 0.3728 | 0.3633 | -0.0095 | [-0.036, +0.017] | no |
| accuracy: b32=1.0, bRICH=0.25 | F4 | gbt | `always32B` | 0.3775 | 0.3802 | +0.0027 | [-0.018, +0.025] | no |
| accuracy: b32=1.0, bRICH=0.5 | F4 | gbt | `always32B` | 0.3775 | 0.3740 | -0.0036 | [-0.028, +0.022] | no |
| accuracy: b32=1.0, bRICH=1.0 | F4 | gbt | `always32B` | 0.3775 | 0.3740 | -0.0036 | [-0.028, +0.022] | no |
| utility: 88 Mbit/s / png / 5s s | F4 | gbt | `always32B` | 0.2852 | 0.2828 | -0.0024 | [-0.006, +0.000] | no |
| utility: 88 Mbit/s / png / 10s s | F4 | gbt | `always32B` | 0.3408 | 0.3136 | -0.0272 | [-0.046, -0.007] | **yes** (**combined worse**) |
| utility: 13.6 Mbit/s / png / 10s s | F4 | gbt | `always32B` | 0.0071 | 0.0047 | -0.0024 | [-0.006, +0.000] | no |

**0 of 72 contrasts have a CI excluding zero in combined's favour; 4 have a CI excluding zero against it.** The pre-registered rule was: *combined beats independent only if the paired CI excludes 0 in at least one pre-specified setting and is not below 0 in others.* The first clause fails and the second fails as well. **Combined does not beat the independent decomposition, and where the difference is resolvable it is worse.**

In every setting the strongest independent variant is `always32B` — the coverage predictor paired with 'send everything to the big model'. Neither confidence-thresholded routing nor an F2 classifier for K3 > H1 improves on it.

## 10. The capability-prediction rule, and results within each question category

Pre-registered rule: *capability prediction counts as useful only if the capability-only policy beats always-32B or always-4B within its budget.*

Across all 54 (feature set × learner × budget) cells: capability-only beats always-32B in **0** of them, and in **21** it loses with a CI excluding zero. It beats always-4B in **43**.

| cell | capability-only | always-32B (within budget) | always-4B | diff vs always-32B | 95% CI |
|---|---|---|---|---|---|
| F2 / logreg / b32=0.25 / bRICH=0.25 | 0.3293 | 0.3547 | 0.3254 | -0.0254 | [-0.046, -0.005] |
| F2 / logreg / b32=0.25 / bRICH=0.5 | 0.3426 | 0.3547 | 0.3254 | -0.0121 | [-0.037, +0.012] |
| F2 / logreg / b32=0.25 / bRICH=1.0 | 0.3266 | 0.3547 | 0.3254 | -0.0281 | [-0.058, +0.001] |
| F2 / logreg / b32=0.5 / bRICH=0.25 | 0.3293 | 0.3680 | 0.3254 | -0.0388 | [-0.065, -0.014] |
| F2 / logreg / b32=0.5 / bRICH=0.5 | 0.3485 | 0.3680 | 0.3254 | -0.0195 | [-0.050, +0.010] |
| F2 / logreg / b32=0.5 / bRICH=1.0 | 0.3503 | 0.3680 | 0.3254 | -0.0178 | [-0.050, +0.014] |
| F2 / logreg / b32=1.0 / bRICH=0.25 | 0.3293 | 0.3882 | 0.3254 | -0.0589 | [-0.092, -0.027] |
| F2 / logreg / b32=1.0 / bRICH=0.5 | 0.3485 | 0.3882 | 0.3254 | -0.0396 | [-0.072, -0.007] |
| F2 / logreg / b32=1.0 / bRICH=1.0 | 0.3574 | 0.3882 | 0.3254 | -0.0308 | [-0.063, +0.000] |
| F2 / gbt / b32=0.25 / bRICH=0.25 | 0.3396 | 0.3527 | 0.3254 | -0.0130 | [-0.032, +0.007] |
| F2 / gbt / b32=0.25 / bRICH=0.5 | 0.3355 | 0.3527 | 0.3254 | -0.0172 | [-0.041, +0.007] |
| F2 / gbt / b32=0.25 / bRICH=1.0 | 0.3254 | 0.3527 | 0.3254 | -0.0272 | [-0.058, +0.004] |
| F2 / gbt / b32=0.5 / bRICH=0.25 | 0.3396 | 0.3728 | 0.3254 | -0.0331 | [-0.059, -0.007] |
| F2 / gbt / b32=0.5 / bRICH=0.5 | 0.3521 | 0.3728 | 0.3254 | -0.0207 | [-0.050, +0.008] |
| F2 / gbt / b32=0.5 / bRICH=1.0 | 0.3550 | 0.3728 | 0.3254 | -0.0178 | [-0.051, +0.014] |
| F2 / gbt / b32=1.0 / bRICH=0.25 | 0.3396 | 0.3775 | 0.3254 | -0.0379 | [-0.070, -0.005] |
| F2 / gbt / b32=1.0 / bRICH=0.5 | 0.3521 | 0.3775 | 0.3254 | -0.0254 | [-0.058, +0.008] |
| F2 / gbt / b32=1.0 / bRICH=1.0 | 0.3751 | 0.3775 | 0.3254 | -0.0024 | [-0.032, +0.029] |

**Reading the rule honestly.** Taken literally, the 'or always-4B' clause fires. But that comparison is not informative: capability-only is *allowed* to spend its whole 32B budget, so beating a policy that never uses 32B is close to automatic. The informative comparator is always-32B, and capability-only never beats it — not even at the tightest budget, where predicting *which* questions deserve the big model should pay most. **Capability prediction is not useful in this data**: spending a fixed 32B budget on arbitrary questions does as well as spending it on predicted ones.

### Within each question category

| category | n | H1 | H2 | K3 | K1 | oracle | per-type | best independent | combined F2/gbt | cap improves/harms (RECENT) | ev improves/harms (4B) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| visual_detail_recall | 143 | 0.538 | 0.483 | 0.552 | 0.580 | 0.706 | 0.538 | 0.566 | 0.566 | 15/13 | 7/15 |
| time_duration | 121 | 0.298 | 0.298 | 0.446 | 0.463 | 0.595 | 0.438 | 0.446 | 0.446 | 29/11 | 4/4 |
| counting_objects_events | 110 | 0.164 | 0.209 | 0.273 | 0.264 | 0.400 | 0.255 | 0.273 | 0.218 | 19/7 | 8/3 |
| sequential_action | 102 | 0.314 | 0.343 | 0.382 | 0.451 | 0.618 | 0.431 | 0.363 | 0.431 | 12/5 | 17/14 |
| location_trace | 97 | 0.309 | 0.216 | 0.402 | 0.309 | 0.598 | 0.340 | 0.361 | 0.340 | 19/10 | 5/14 |
| object_comparison | 91 | 0.352 | 0.341 | 0.363 | 0.385 | 0.549 | 0.374 | 0.374 | 0.341 | 12/11 | 6/7 |
| spatial_aware_reasoning | 91 | 0.209 | 0.154 | 0.154 | 0.154 | 0.330 | 0.176 | 0.209 | 0.187 | 4/9 | 5/10 |
| temporal_ordering_recognition | 90 | 0.344 | 0.289 | 0.400 | 0.456 | 0.633 | 0.400 | 0.400 | 0.344 | 14/9 | 5/10 |

`spatial_aware_reasoning` is the one category where the 4B RECENT cell is the best of the four (0.209 against 0.154 for all three others) — more evidence and a bigger model both hurt it. `location_trace` is the one where RECENT beats RICH at 32B (0.402 vs 0.309). These are the cells a per-type table can already exploit, which is why per-type is the reference the learned policies fail to beat.

## 11. Results consistency check (CLAUDE.md, 6 checks)

| # | check | outcome |
|---|---|---|
| 1 | cross-check vs committed | **PASS.** Cell accuracies reproduce StudyR1 / StudyClean exactly: H1 32.54%, H2 30.18%, K3 38.34%, K1 39.53% — the same values E4 §1 and the ledger record. Part 0 reproduces committed E4 table 4.1 at max abs diff 0.0000 over 24 cells. The coverage predictor's AUROC 0.7063 / 0.8039 brackets StudyR8a's corrected 0.7885. No ratio > 2x. |
| 2 | physical plausibility | **PASS.** No new latency measured. Compute comes from E4's curves unchanged; the only changed quantity is upload bytes, and its arithmetic is checked in the §4 trace (31,838,730 B x 8 / 88e6 + 0.022 = 2.916 s). The corrected rule makes uploads *smaller*, so no implied rate exceeds a committed curve. |
| 3 | distribution sanity | **PASS with note.** Identical values across cells are explained, not hidden: the three `indep_*` rows are constant across F1/F2/F3 because those policies' components are fitted on F2 by definition, so the feature-set label does not vary them; policies are identical at bRICH = 0.5 and 1.0 wherever the unconstrained optimum already uses RICH on under half the questions. Per-category spreads are reported in §10 rather than a bare mean. |
| 4 | definition audit | **PASS with note.** RECENT / RICH are the ledger cells R1.K3 / R1.K1 with StudyClean H1 / H2 replaying the identical requests. 'Per-type' is E4's definition (category x qt bin). **New to this study:** the four-cell action space, the five intervention targets, and the LP budget allocation; none reuses an existing name. The 'evidence gain' name is used for a `REALLOCATED_BUDGET` contrast, flagged at §1 and wherever it appears. |
| 5 | claim linkage | Bears directly on the coupling claim (joint representation x placement x timing beats decomposed policies). **It weakens the decidable form of that claim on this workload:** the joint policy does not beat the decomposed one, and the gap is negative where resolvable. It does not speak to the claim's upper-bound form, which E4 measured and Part 0 revises upward at low bandwidth. Placement is absent by construction here (all four cells are cloud), so this study says nothing about location. |
| 6 | proxy validity | **Flagged, three proxies.** (a) `evidence_covered` from the RECENT construction is the training label for the coverage predictor; it is an annotation-derived flag, not something available at inference, and is used only as a fitting target inside training folds. (b) StudyD13's letter logprobs stand in for H1's confidence: predictions agree 100.0% and prompt tokens 100.0% of 845, so this proxy is exact rather than approximate. (c) The oracle is an upper bound inflated by single-draw selection (§4 Step 5). |

## 12. Observations (data only, no interpretation)

1. The four cells leave only 334 of 845 questions decidable: 370 are missed by every cell and 141 answered by all four.
2. The per-question oracle scores 0.5621 unconstrained; the best static cell (K1) 0.3953; the per-type lookup 0.3799. Per-type is **below** the best static cell, replicating E4's observation that per-type routing captures nothing over static.
3. The best realised policy anywhere in setting (a) is evidence-only on F1, 0.4036, which is +0.0083 against the best static cell with CI [-0.004, +0.021].
4. Capability gains are asymmetric (bigger model helps ~2x as often as it hurts); evidence gains are near-symmetric and net-negative at 4B.
5. No feature set beats F1 on any target with a CI excluding zero (0 of 30 contrasts); 3 are significantly worse than F1.
6. Combined beats the best independent baseline in 0 of 72 pre-specified contrasts with a CI excluding zero, and loses in 4.
7. Capability-only beats always-32B in 0 of 54 cells, and loses with a CI excluding zero in 21.
8. In setting (b) the binding constraint is deliverability, not choice: at 13.6 Mbit/s PNG 10 s only the RICH cells can be delivered, and at 88 Mbit/s PNG 5 s K3 delivers on 2.6% of questions.
9. Part 0: correcting the upload inconsistency raises oracle utility in 14 of 16 reported cells, leaves 88 Mbit/s PNG 10 s unchanged, and lowers headroom over per-type at 88 Mbit/s raw 10 s (0.200 → 0.172).

## 13. Interpretation (inference, labelled as such)

- **The study's question gets a negative answer on this workload, and it is a *real negative* for the combined-vs-independent comparison.** The mechanism was present and exercised: the cells genuinely disagree (§5), the disagreement is 10-40x the noise floor, the independent baseline is strong, and the combined policy had strictly more information than the decomposition. Under CLAUDE.md Rule 2 this is a **real negative**, not an inconclusive one — with the caveat in the next bullet.
- **The feature-set result is inconclusive-for-want-of-power, not a real negative.** Concluding that question text and session history carry no information about which intervention helps would require ruling out the n = 845 / sparse-target explanation, and three contrasts where F2 is *significantly worse* than F1 are the signature of overfitting, not of absent signal. What is settled is narrower: **at this sample size, with these features, nothing beats a category x question-time table.**
- **Capability prediction specifically does not pay.** Across every budget, spending a fixed 32B allowance on predicted-gain questions is no better than spending it arbitrarily. This is the cleanest negative in the study, because the comparator (always-32B within the same budget) is exactly matched on resources.
- **The oracle gap is large but is not evidence that a policy could close it.** 0.562 vs 0.395 is a 16.7-point gap, and nothing here recovers more than about a point of it. Part of that gap is the four-arm selection effect; how much, this design cannot say.
- **Part 0 changes what StudyE4 should be read as saying.** E4's low-bandwidth conclusion was an artefact of charging one arm two different ways. With the charge made consistent, switching value at constrained uplinks is real (0.078-0.090 at 5-10 s) rather than ≈ noise, and the configuration that looked uniquely best there (D2) loses its advantage to cloud-held RICH. The upper-bound claim survives and is somewhat stronger; the 'nothing to switch between at low bandwidth' claim does not survive.
- **What would move this.** Not more features on 845 questions. Either many more questions, or an action space whose arms differ more than these four do — 370 of 845 questions are missed by all four cells, which caps any router's reach before prediction enters.

## 14. Files

- `experiments/orchestration/study_e6_part0_upload_fix.py`
- `experiments/orchestration/study_e6_intervention.py`
- `experiments/orchestration/study_e6_report.py`
- `results/orchestration/study_e6/e6_part0_upload_fix.json`
- `results/orchestration/study_e6/e6_results.json`
- `results/orchestration/study_e6/e6_realized_vectors.npz`
- `reports/study_e6_intervention.md` (this file)
