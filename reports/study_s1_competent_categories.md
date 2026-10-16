# StudyS1 — Gate 1 on the competent-category stratum

**Date:** 2026-10-06
**Pre-registration:** `reports/study_s0_plan.md` §StudyS1 AMENDMENT, recorded **before** this run.
**Analysis script:** `experiments/erqa/study_s1_analyze.py` · **Trials:** `results/mvrobobench/study_s1/study_s1_trials.jsonl`

---

## Condition 1 — how this result must be read

Stated first, before any number, because the framing changes what the result means.

- The **137-question byte-identical block** of `spatial_viewpoint_identification` was the
  **pre-registered primary instrument**.
- It returned a **degenerate label**: both arms sat at chance (arm I 23.3%, arm T 26.7% ± 11.2),
  discordance was 30% and near-symmetric (b=10, c=8), and net_rescue was **+3.3pp with CI
  [−10.5, +17.2]** at n=60. A label produced by two coin flips cannot be predicted by anything,
  so that instrument cannot measure.
- What follows is therefore a **SECONDARY, POST-HOC STRATUM**: the two categories where arm I is
  clearly above chance, selected on a criterion independent of the hypothesis (arm I Wilson 95% CI
  lower bound > 25%), fixed from arm I data **before** arm T ran on them.
- Accordingly: **Gate 1 was tested on a post-hoc stratum.** This is *not* the originally designed
  experiment, and nothing below should be read as if the original design had been executed.

**Condition 2 — scope.** This run answers **Gate 1 only**. The byte-identical block required for
Gate 2 is dead, and these two categories have *text* options, so the query-to-option CLIP margin —
the one strong image feature — is undefined for them. **No Gate 2 verdict is reported here**, and a
Gate 1 result either way does not advance the dynamicity claim.

---

## VERDICT (Condition 3)

> **net_rescue = +1.00pp, 95% CI [−4.74, +6.74], n = 401**
>
> - net > 5pp? **NO** (+1.00pp)
> - CI excludes 0? **NO** (lower bound −4.74pp)
>
> ## → **Neither — branch is empty. STOP.**

Per the pre-registered rule: no third stratum, no further category selection, no additional
workload. **A near miss does not license re-aiming, and this is not a near miss** — the point
estimate is a fifth of the threshold and the interval straddles zero. McNemar χ² (continuity-
corrected) = 0.065 against a critical value of 3.841.

### Classification of this null (CLAUDE.md Rule 2)

**Real negative — a settled finding, not a design failure.**

This is the distinction that matters, and it separates this result from the 137-block pilot:

| | 137-block pilot | this stratum |
|---|---|---|
| arm I accuracy | 23.3% (chance = 20%) | **37.4%** |
| arm T accuracy | 26.7% (chance = 20%) | **38.4%** |
| mechanism present? | **No** — label was coin-flip noise | **Yes** — both arms competent |
| classification | **Inconclusive** (design failure) | **Real negative** (settled) |

Both arms here are substantially above chance, the discordance is large and genuine (34.4% of
questions get a different answer from the two arms), and thinking was exercised throughout
(`think_closed` 95.5%, median 1,689 think tokens). The mechanism operated as specified and did
not produce the claimed effect.

**Power caveat, stated rather than buried.** At n=401 with the StudyK discordance prior the MDI is
~6.5pp, just above the 5pp pass threshold. A true effect between 5 and 6.5pp could have failed to
clear the interval. The observed +1.00pp sits far below that window, so the conclusion does not
rest on the marginal zone — but the test was adequately, not generously, powered.

---

## 1. Accuracy per arm

Chance baseline = **20.0%** (five-choice).

| arm | correct | n | accuracy | 95% CI (Wilson) |
|---|---|---|---|---|
| **I** (Instruct, reused) | 150 | 401 | **37.4%** | [32.8, 42.2] |
| **T** (Thinking, CFG-A) | 154 | 401 | **38.4%** | [33.8, 43.3] |

Unpaired difference +1.00pp — descriptive only; the paired net below is the test.

---

## 2. Paired discordance

| quantity | count | rate |
|---|---|---|
| **b** — I wrong, T correct | **71** | 17.7% |
| **c** — I correct, T wrong | **67** | 16.7% |
| discordance (b + c) | 138 | **34.4%** |
| **net_rescue = (b − c)/n** | | **+1.00pp, CI [−4.74, +6.74]** |

McNemar χ² (continuity-corrected) = 0.065, critical value 3.841 at α = 0.05.

**This is the substantive finding.** Thinking changes the answer on **more than a third** of
questions and nets essentially nothing: it rescues 71 and breaks 67. The rescue population is real
and large in absolute terms — but so is the anti-rescue population, and they very nearly cancel.
Reporting only b (17.7% "rescued by thinking") would have made this look like a strong positive.
That is precisely the error Correction 1 was introduced to prevent, and this run is a direct
vindication of requiring the net.

**Clustering.** The stratum has only 2 clusters (categories). A 2-cluster sandwich estimator is
unreliable, so per-cluster nets are reported instead of a cluster-robust CI:
`spatial_distance_judgement` **+2.5pp**, `robotic_trajectory_selection` **−0.5pp**. The two
clusters straddle zero and point in opposite directions, which is itself evidence against a
consistent underlying effect.

---

## 3. Per-category breakdown — **DESCRIPTIVE, NOT CONFIRMATORY**

| category | n | arm I | arm T | b | c | net | 95% CI |
|---|---|---|---|---|---|---|---|
| spatial_distance_judgement | 201 | 41.3% | 43.8% | 36 | 31 | +2.5pp | [−5.5, +10.5] |
| robotic_trajectory_selection | 200 | 33.5% | 33.0% | 35 | 36 | −0.5pp | [−8.8, +7.8] |

Neither category individually clears the threshold; both intervals include zero. These cells are
descriptive — the stratum was pre-registered as the pooled n=401 unit, and per-category figures are
shown for transparency, not as separate tests.

---

## 4. Verdict against the rule

Stated above, first. **Neither — branch is empty. STOP.**

---

## 5. Think-token distribution and latency (cost side)

All ratios in this table are **median-of-medians** (median arm-T per-trial latency / median
arm-I per-trial latency). The mean-of-means version of the POOLED figure is 452×; the two are
not interchangeable.

| scope | think med | IQR | max | arm T lat med | arm I lat med | ratio (median-of-medians) |
|---|---|---|---|---|---|---|
| spatial_distance_judgement | 2,562 | [1,261, 4,186] | 8,117 | 77.2 s | 0.21 s | **372×** |
| robotic_trajectory_selection | 1,148 | [620, 1,956] | 5,683 | 27.5 s | 0.19 s | **144×** |
| **POOLED** | **1,689** | [873, 3,155] | 8,117 | **43.5 s** | **0.19 s** | **226×** |

Arm T consumed **7.93 h** of A6000 time for 401 questions. Arm I covered the same questions in
roughly 80 seconds.

**The cost conclusion is sharper than the accuracy one.** Thinking costs **226× the latency**
(median-of-medians) of
the Instruct arm and returns **+1.00pp**, with an interval that includes zero and a negative lower
bound. On this workload the bounded path is not merely competitive — it dominates, by more than
two orders of magnitude on the only axis where the two differ materially. This is consistent with
StudyQ on ERQA, where 8B-Instruct matched 4B-Thinking's accuracy at 91× the speed (that figure
is **mean-of-means**, not median — see `reports/study_q_fa2_backend.md`; the two studies'
headline ratios are therefore computed on different bases).

**Attention backend (added 2026-10-15).** `study_s1_mvrobobench.py` passes no
`attn_implementation`, so both arms ran on the transformers default, **SDPA** (`transformers
5.12.1`; `flash_attn 2.6.3` is installed on this box but was not requested). The 226×
(median-of-medians) ratio is
unaffected on two counts: both arms share the backend, and the gap is driven by decode length
(1,689 think tokens vs a single letter), which is upstream of the attention kernel. The StudyQ
comparison is also backend-matched — no script under `experiments/erqa/` sets
`attn_implementation`, so that family is uniformly SDPA. Absolute per-trial latencies here should
still not be read against the flash-attn-2 cost curves in `experiments/sember/` and
`experiments/vision/`.

**Measured, 2026-10-16.** The claim immediately above that "the 226× ratio is unaffected" has
since been tested rather than argued: the study was re-run end to end on flash-attention-2 and
the same median-of-medians ratio reads **202×** (per-category 144× → 120× and 372× → 357×). The
ratio does move, by 11%, because flash-attn speeds up the long-decode thinking arm (throughput
1.19×) and not the single-token instruct arm (0.99×), and because the sampled arm re-drew
slightly shorter sequences (median think tokens 1,689 → 1,603). The conclusion is unchanged at
two orders of magnitude, and `net_rescue` is +1.00pp under both backends. Full comparison:
`reports/study_s1_fa2_backend.md`. The 226× above is the correct figure for this SDPA run and is
left as written.

### Non-termination is workload-dependent — a fourth data point

| workload | model + decoding | budget | non-termination |
|---|---|---|---|
| ERQA (StudyS0 Audit 2) | 4B-T, temp 0.6 | 8,192 | **0%** |
| MV-RoboBench / trajectory_selection | 4B-T, temp 0.6 | 8,192 | **0%** |
| MV-RoboBench / distance_judgement | 4B-T, temp 0.6 | 8,192 | **8.5%** |
| SiGNgapore2D (StudyJ2) | 4B-T, temp 0.6 | 24,576 | **20–30%** |

Two categories of the *same dataset* differ by 8.5 points under identical model, decoding and
budget. Non-termination is a property of the workload, not of the model — now supported across
four cells rather than the two recorded in the Audit 2 report.

---

## Sanity checks

- **Arm I trials are REUSED, not re-run.** Source: the completed arm I sweep in
  `results/mvrobobench/study_s1/study_s1_trials.jsonl`. All 401 matched to arm T by `qid_path`.
- **`think_closed`:** 383/401 (95.5%). Not closed: 18 (4.5%).
- **`budget_hit`:** 18/401 (4.5%), all in `spatial_distance_judgement`.
- **Parse failures reported separately, not silently scored wrong:** arm T **12** (3.0%),
  arm I **0**. These emitted no extractable letter and are scored incorrect; the asymmetry is
  itself a cost of the Thinking arm.
- **Truncation scoring.** Truncated traces score 0 under the deployment-realistic convention used
  in StudyP. 2 truncated traces nonetheless emitted the correct letter; scoring those as correct
  would move arm T from 38.4% to 38.9% and the net from +1.00pp to +1.50pp — **the verdict is
  unchanged** under either convention.
- **Sensitivity bound.** Even if *all* 12 arm-T parse failures were scored correct, arm T would
  reach 41.4% and the net +4.0pp — still below the 5pp threshold, with the CI still including zero.
  The verdict is robust to the most favourable scoring assumption available.

---

## What this settles, and what it does not

**Settles:** on MV-RoboBench's two competent categories, thinking mode produces no net accuracy
benefit over the Instruct model at 226× the latency (median-of-medians), despite altering more than a third of the
answers. A real negative.

**Does not settle:** the dynamicity claim. Per Condition 2, Gate 2 was never testable here — the
only instrument with provably degenerate static features was also label-degenerate, and these
categories lack image-valued options. **MV-RoboBench provides no instrument to test the
predictability of a rescue population**, and this run does not change that.

Per Condition 3, the pre-registered stop applies: no third stratum, no further category selection,
no additional workload.
