# Study S0 — Pre-Registration Audits for MV-RoboBench Thinking × View-Composition Experiment

**Date:** 2026-10-05  
**Status:** Audits in progress (Audit 2 GPU run active). Do not start the main experiment.  
**Plan version:** 2 (incorporates corrections from 2026-10-05 — see CORRECTION blocks below)

---

## Purpose

Three audits that produce the inputs for a pre-registered experiment. No hypothesis test in S0 itself. Outputs determine:
- Frozen decoding config for main experiment
- n and strata for power calculation
- Whether the dataset can test both gates (see below)
- Pre-registered analysis plan for the static-predictor Gate 2 check

---

## Two-gate structure

**[CORRECTION 1 — 2026-10-05]** The experiment has two purposes that must be stated separately:

**Gate 1 — does a net reasoning-benefit population exist?**

A population of (Instruct wrong, Thinking correct) queries must be large enough to be worth routing to. This is not sufficient on its own.

**Criterion (corrected):** Gate 1 passes only on *net rescue*:

```
net_rescue = P(I wrong, T correct) − P(I correct, T wrong)
```

with a paired McNemar CI. Both discordant cells must be reported separately *and* the net. Gate 1 passes on net > epsilon (pre-registered epsilon = 5pp), not on the rescued cell alone.

**Motivation for correction:** On ERQA, P(I wrong, T correct) ≈ 15% and P(I correct, T wrong) ≈ 12%, leaving net ≈ 3pp. Both populations were large but the net was near zero — a policy that routes all queries to Thinking would have gained almost nothing. Reporting only the rescued cell would have made this look like a positive result.

**Gate 2 — can membership be predicted from arrival-time features?**

Given that a net-rescue population exists, can it be identified *before* execution using features visible at query arrival? If yes, the policy is a static lookup table and there is no runtime decision to make. This is the gate that determines whether the project has a runtime systems problem.

**What would overturn Gate 2:** residual variance *within* a category — two structurally identical questions where Thinking rescues one and wastes tokens on the other. A benchmark with clean category labels that each map uniformly to one winner makes Gate 2 *easier* to fire (worse for us), because the category label is readable at arrival.

---

## Audit 1 — MV-RoboBench dataset audit

**Purpose:** Verify dataset properties, define the direct/compositional binary contrast, and assess whether the dataset can test Gate 2.

**Required outputs:**

1. n by category and by source (AgiWorld vs BridgeV2).
2. Direct/Compositional count per category. Definition: Compositional = answering REQUIRES combining evidence across ≥2 views (judged from question construction, not model performance). Direct = single view suffices.
3. For power calc: n_direct, n_compositional.

**[CORRECTION 2 — 2026-10-05] Within-category homogeneity analysis (added requirement):**

For each category, report:
- What static features are available per question at arrival time: category label, n_views, question text length (chars and tokens), any other metadata fields in the HF release.
- How much do questions *within* that category vary on those features? Concretely: SD of n_views within category, SD of question text length within category, visual inspection of question phrasing diversity.
- **Verdict per category:** is the category homogeneous (low within-category variance on static features) or heterogeneous? A homogeneous category cannot test Gate 2 because any within-category variance in which-arm-wins cannot be attributed to statically-observable differences.

**Summary verdict:** Which categories have the largest *between*-category / *within*-category variance ratio on static features? These are the best instruments for Gate 2. Report which categories come closest to the ideal (large between-category contrast, large within-category diversity).

**Script:** CPU, no GPU required.  
**Output:** section in `reports/study_s0_audits.md`.

---

## Audit 2 — Decoding config validation

**Purpose:** Identify the decoding config closest to the published 4B-Thinking accuracy (47.3% on ERQA), characterise budget-hit rate and looping behaviour.

**Configs:**
- CFG-A: `do_sample=True, temperature=0.6, top_p=0.95, top_k=20, max_new_tokens=8192`
- CFG-B: `do_sample=True, temperature=1.0, top_p=0.95, top_k=20, max_new_tokens=40960` (card defaults)
- CFG-C: `do_sample=True, temperature=1.0, top_p=0.95, top_k=20, max_new_tokens=16384` (card, capped)

**Model:** Qwen3-VL-4B-Thinking, snapshot `1de27d8c`, bfloat16, device_map=auto (A6000+RTX3090Ti).  
**Dataset:** 100 ERQA questions, seed=42 shuffle of the 400-question test set, sorted indices.

**Per config report:**
- Accuracy with Wilson 95% CI; comparison to 47.3% published reference.
- Budget-hit rate (n_gen ≥ max_new_tokens − 5).
- Think-token distribution: median, IQR, max.
- Degenerate repetition rate (10-gram repetition in last 500 chars).
- `think_closed` rate (fraction of outputs that produced `</think>` before budget).

**Frozen config decision:** The config whose accuracy comes closest to 47.3% becomes the frozen config for the main experiment.

**Script:** `experiments/erqa/study_s0_audit2.py`  
**Output:** `results/erqa/study_s0/audit2_trials.jsonl`; section in `reports/study_s0_audits.md`.

**Known fix (2026-10-05):** The Qwen3-VL chat template injects `<think>\n` as the final prompt token; generated tokens start *inside* the think block. Detection must search for `</think>` in the generated output, not the full `<think>…</think>` pattern. Applied in script.

---

## Audit 3 — Power calculation

**Purpose:** Compute McNemar within-stratum n at 5/10/15pp delta, interaction n at 10pp delta, and the minimum detectable interaction (MDI) at the observed category counts.

**Inputs from Audit 1:** n_direct, n_compositional.  
**Computation:** CPU, closed-form McNemar approximation, α=0.05 two-tailed, β=0.20.

**Output:** within-stratum n table; interaction n; MDI at observed counts; section in `reports/study_s0_audits.md`.

---

## Pre-registered main experiment design

**[CORRECTION 3 — 2026-10-05] Static predictor analysis added as required pre-registered analysis:**

### Interaction test (original, unchanged)

2×2 factorial: arm A = 4B-Instruct, arm B = 4B-Thinking; strata = Direct vs Compositional questions.
Pre-registered test: interaction [Δ_Think(Compositional)] − [Δ_Think(Direct)] > 0, McNemar paired.

Gate 1 criterion (corrected per Correction 1): net_rescue = P(I wrong, T correct) − P(I correct, T wrong) > 5pp with CI lower > 0, reported separately per stratum and overall.

### Static predictor analysis (new required analysis)

**Motivation:** If category label alone predicts which queries benefit from Thinking, the policy is a design-time static mapping. Gate 2 fires and the dynamicity claim is not supported by this workload. A weak static predictor baseline would make Gate 2 look survivable when it is not. This analysis uses the strongest available static predictor drawn from prior work.

**Label:** (I wrong, T correct) indicator per question (the net-rescue population member).

**Features at arrival time (all static — no execution required):**
- Category label (one-hot, 8 categories)
- n_views (integer count of frames/images supplied per question)
- Question text length (character count)
- MiniLM sentence embedding of question text (all-MiniLM-L6-v2, 384 dims)

**Baseline approach:** Follow StudyN2's P4 predictor (see `reports/study_n2_results.md`): MiniLM embedding, LogisticRegression with L2 penalty, C=1.0, no StandardScaler for sparse features (dense MiniLM embeddings: standard scaling is appropriate), 5-fold CV, no leakage across folds. StudyN2 P4 reached AUROC 0.765 on a different label (needs_escalation) on LoCoMo.

**Models to fit and report (5-fold CV AUROC):**
1. Category one-hot alone (logistic regression).
2. Non-embedding static features: category + n_views + q_len (logistic regression).
3. Full static predictor: category + n_views + q_len + MiniLM embedding (logistic regression — this replicates StudyN2 P4 structure).

**Required outputs:**
- AUROC of category alone (model 1).
- AUROC of full static predictor (model 3).
- Fraction of net-rescue population *not* identified by model 3 at optimal threshold (residual fraction).

**Pre-registered decision rule for Gate 2:**

```
IF category_alone_AUROC >= 0.75:
    Gate 2 FIRES — policy is a design-time lookup; dynamicity claim is not supported.

IF full_static_AUROC >= 0.75 AND category_alone_AUROC < 0.75:
    Gate 2 partially fires — arrival-time text features identify the rescue population but
    the category label alone is insufficient, suggesting within-category residual structure.
    Report which non-category features carry the predictive weight.

IF residual_fraction > 0.50 (i.e., model 3 cannot identify >50% of net-rescue at optimal threshold):
    Gate 2 is survived — substantial rescue population is not statically predictable.
    Runtime signals have something to explain.
```

**Note on conservatism:** A weak static predictor baseline (e.g., only n_views and q_len, no embedding) would falsely make Gate 2 look survivable. The full P4-structure predictor (MiniLM embedding included) must be used as the baseline, consistent with StudyN2.

---

## Outputs

| File | Content |
|---|---|
| `reports/study_s0_audits.md` | Final report with all three audit sections and GO/NO-GO verdict |
| `results/erqa/study_s0/audit2_trials.jsonl` | Per-trial records for Audit 2 |

---

## GO/NO-GO criteria for proceeding to main experiment

All three must pass:
1. **Audit 1:** n_direct ≥ 400 AND n_compositional ≥ 400 AND within-category homogeneity assessed (verdict per category recorded).
2. **Audit 2:** At least one config has accuracy within 5pp of 47.3% AND think_closed ≥ 95% for that config.
3. **Audit 3:** MDI at observed category n ≤ 15pp (else increase n or collapse categories).

If GO: main experiment uses frozen config, n=min(n_direct, n_compositional) per stratum (or n per power calc), 4B-Thinking and 4B-Instruct, all questions in both strata.
