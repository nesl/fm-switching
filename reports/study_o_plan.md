# Study O — Plan: S-EMBER State × Compute Factorial

**Date:** 2026-10-03  
**Status:** PENDING APPROVAL — no inference until approved  
**Pre-registered:** `research/EXPERIMENTS.md` row StudyO  
**Research questions:**

| Q | Question |
|---|---|
| Q1 (primary) | Does the accuracy gain from a larger model or thinking mode depend on whether retained frames contain the evidence? |
| Q2 | What is the best state arm per (category, distance bin)? |
| Q3 | Does counting accuracy scale with count difficulty? |
| Q4 | Does coverage-based escalation (Study N2 P4 predictor) translate to end-to-end accuracy gain? |

**Fixes relative to I2/I3:** Frames must be sampled from [0, question_time], not the first N seconds.

---

## 1. Dataset

S-EMBER grounding annotations: 9,438 QA pairs (10 excluded for negative nearest-evidence distance) from 3,141 videos. Source: `results/sember/study_h/data/sember_grounding.jsonl`.

Study O uses a **stratified random sample** (size TBD; see §8 Sample Check) drawn from S-EMBER:

- Stratify by `category` × `distance_bin` (bins: farthest ≤ 60 s, 60–120 s, > 120 s)
- Include `counting_objects_events`; report with and without separately
- Seed: 42

**Study O videos must be withheld from N2 training** (see §7 Q4): exclude all Study O `video_id` values from Study N2's training folds when retraining the P4 predictor.

---

## 2. Frame-Selection Arms

| arm | description | fps | frames | pixel budget |
|---|---|---|---|---|
| RECENT | trailing W=120 s at 1fps | 1 | ≤ 120 (capped at question_time) | unconstrained |
| UNIFORM | 16 frames over [0, question_time] | — | 16 | unconstrained |
| RICH | 256 frames over [0, question_time] | — | 256 | binding (Qwen3-VL processor cap) |

Frame selection is from [0, question_time] for UNIFORM and RICH; from [question_time − 120, question_time] for RECENT.

---

## 3. Model Arms

| arm | model | HF id |
|---|---|---|
| 4B-I | Qwen3-VL-4B-Instruct | `Qwen/Qwen3-VL-4B-Instruct` |
| 8B-I | Qwen3-VL-8B-Instruct | `Qwen/Qwen3-VL-8B-Instruct` |
| 4B-T | Qwen3-VL-4B-Thinking | `Qwen/Qwen3-VL-4B-Instruct` (thinking mode) |

**Full factorial:** 3 frame-selection arms × 3 model arms = 9 cells per question.  
Host: A6000 (flash, cuda:1).

**Q4 designations** (cells must be present in the factorial):

| role | cell |
|---|---|
| local | 4B-I × RECENT (last 120 s) |
| remote (Instruct) | 8B-I × RICH |
| remote (Thinking subset) | 4B-T × RICH |

---

## 4. Q1 — Primary Interaction Analysis

**Model:** mixed-effects logistic `correct ~ model_arm × evidence_covered + state_arm + (1|question_id)`.  
`evidence_covered` = 1 if the retained frame window includes the question's farthest evidence time (farthest ≤ W for RECENT, always 1 for RICH/UNIFORM since they span [0, qt]).

**Pre-registered decision rule:**

| verdict | condition |
|---|---|
| K1 fires (STOP) | interaction coefficient < 3 pp AND n.s. at α = 0.05 |
| PROCEED | otherwise |

---

## 5. Q2 — State-Arm Allocation Lookup Table

For each (category, distance_bin) cell, report the best state arm by mean accuracy. Compute oracle coverage: fraction of questions covered if each question were assigned its best (category, distance_bin) arm. K2: if per-category lookup captures ≥ 80% of the oracle gap (best per-question arm vs random), report as a positive finding (lookup sufficient for allocation).

---

## 6. Q3 — Counting Accuracy by Count Bin

For `counting_objects_events` questions, report accuracy by count bin (1–2, 3–5, 6–10, 10+) × model arm. Primary test: monotone decrease in accuracy with count bin (Jonckheere–Terpstra test, α = 0.05). K3: if all Instruct arms are within 5 pp of chance across all count bins, counting is at floor regardless of state and the model-routing claim is vacuous.

---

## 7. Q4 — Escalation Policy Evaluation

### Motivation

Study N2 established SIGNAL (AUROC = 0.766, gap_closed = 44.9%, CI = [41.9%, 48.0%]) that the P4 predictor (all-MiniLM-L6-v2 + log(1+qt)) can rank questions by need for full-history access at L = 120 s and e = 0.2. Coverage is a proxy metric. Q4 tests whether this ranking converts to **end-to-end accuracy gain**.

### Predictor retraining

Train N2's P4 predictor on S-EMBER questions with all Study O video_ids removed from the training set. Use the same 5-fold grouped CV by video_id with seed = 42. Apply the predictor to every Study O question to produce per-question P(needs_escalation). No new inference is needed for this step (sentence-transformer features only).

### Policies (at each escalation rate e ∈ {0.1, 0.2, 0.3})

| label | policy |
|---|---|
| (a) never escalate | always serve local (4B-I × RECENT) |
| (b) always escalate | always serve remote (8B-I × RICH) |
| (c) random at rate e | escalate a random e-fraction (analytic: (1−p)×acc_local + e×acc_remote, where p=P(farthest>120)) |
| (d) predictor top-e | escalate the top-e fraction by P(needs_escalation) from retrained P4 |
| (e) oracle (evidence distance) | escalate the top-e fraction by true farthest distance |
| (f) accuracy oracle | escalate the e-fraction where remote is correct and local is wrong (maximum accuracy oracle at rate e) |

Policies (a)–(f) are all derived from the factorial's per-question correctness outcomes: no additional inference.

### Metric

End-to-end accuracy per policy: `(fraction not escalated and local correct) + (fraction escalated and remote correct)`.

### Primary Q4 test

Accuracy of policy (d) minus policy (c) at e = 0.2. Paired bootstrap clustered by video_id (2,000 resamples; same protocol as N2). Report 95% CI and whether it excludes 0.

Also report what fraction of the (c)-to-(f) gap policy (d) closes:

```
gap_closed_accuracy = (acc_d − acc_c) / (acc_f − acc_c)
```

Report for both remote configurations (8B-I × RICH and 4B-T × RICH).

### Kill condition K4

If policy (d) minus policy (c) at e = 0.2 is under 1 pp with CI including 0, coverage-based escalation does not convert into accuracy gain. The runtime-signal claim stays at the coverage level (Study N2) only. Report the reason: either (i) local and remote accuracy are too similar (model routing does not matter), or (ii) the predictor's coverage ranking does not correlate with local-vs-remote accuracy differences.

---

## 8. Sample Check

Before finalising the sample, confirm:

1. **Q4 power:** report the fraction of Study O questions with farthest > 120 s (expected ≈ 29.7% from H2). For the planned n, compute the minimum detectable accuracy difference (d minus c) at 80% power (two-sided α = 0.05) using the clustered-bootstrap variance from the N2 run as a pilot estimate of intra-video correlation.

2. **Q1 cell balance:** ensure ≥ 20 questions per (category × distance_bin × state_arm) cell for the mixed-effects model.

Report both checks in the script's pre-run output; halt if either fails.

---

## 9. Kill Conditions

| condition | trigger | action |
|---|---|---|
| K1 | Q1 interaction < 3 pp AND n.s. | stop; evidence_covered does not moderate gain; report and do not run Q2–Q4 analyses for publication |
| K2 | per-category lookup captures ≥ 80% oracle gap | positive allocation finding; summarise as lookup table |
| K3 | all Instruct arms within 5 pp of chance | counting at floor; model-routing claim vacuous |
| K4 | (d) − (c) < 1 pp with CI including 0 at e = 0.2 | coverage-based escalation does not translate to accuracy; N2 signal stays at coverage level only |

---

## 10. Output Files

| file | status |
|---|---|
| `reports/study_o_plan.md` | this file |
| `experiments/sember/study_o_*.py` | to be written after approval |
| `results/sember/study_o/` | after inference |
| `reports/study_o_results.md` | after analysis |
