# Study S0 — Pre-Registration Audits for MV-RoboBench Thinking × View-Composition Experiment

**Date:** 2026-10-05  
**Status:** All three audits complete (`reports/study_s0_audits.md`). Main experiment not started.  
**Plan version:** 3 — v2 added Corrections 1–3; v3 applies the approved restructure
(Gate 2 within-block promoted to primary, interaction demoted) and adds the three-variant
image-feature static-predictor requirement. See the RESTRUCTURE and ADDITION blocks below.

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

**[RESTRUCTURE — 2026-10-05, approved]** Audit 1 established that the direct/compositional
contrast does not exist independently of category (6/8 categories 100% uniform on structural
markers). The design is therefore restructured:

- **Primary analysis:** the Gate 2 within-block static-predictor test (§B below).
- **Demoted:** the direct/compositional interaction, now reported as a clearly-labelled
  between-category comparison that cannot separate compositional structure from category
  difficulty (§C).
- **Unchanged:** Gate 1 on the full dataset (§A).

### Arms

Arm I = Qwen3-VL-4B-Instruct. Arm T = Qwen3-VL-4B-Thinking, frozen config CFG-A
(temp 0.6, top_p 0.95, top_k 20, max_new_tokens 8,192) per Audit 2. Both arms run every question.

---

### §A — Gate 1: net rescue (full dataset, n = 1,708)

**[CORRECTION 1]** Gate 1 is evaluated on

```
net_rescue = P(I wrong, T correct) − P(I correct, T wrong)
```

with a paired McNemar CI. Both discordant cells are reported separately alongside the net.
Gate 1 passes on **net > 5pp with CI lower bound > 0**, never on the rescued cell alone.

MDI at n = 1,708 is 3.5pp (Audit 3), so the dataset is well powered for this test.

---

### §B — Gate 2 (PRIMARY): within-block static-predictor test

**The instrument.** Audit 1 identified blocks of questions that are *byte-identical* on every
arrival-time textual and metadata feature. The primary unit is the **pooled IDEAL + USABLE blocks,
n = 466** across 5 categories; the single largest block (`spatial_viewpoint_identification`,
n = 137) is a secondary confirmatory unit.

**Label:** the (I wrong, T correct) indicator per question.

#### B.1 — Three required static-predictor variants

**[ADDITION — 2026-10-05]** S1 alone is not an adequate baseline. Within a byte-identical block
the images are the *only* varying input, and images are available at arrival. A predictor that
ignores the only varying input is a strawman, and its 0.5 AUROC would be an artifact of feature
choice, not evidence of unpredictability.

| variant | features |
|---|---|
| **S1** | text + metadata only: category one-hot, `n_views`, `q_len`, view-label configuration, MiniLM (all-MiniLM-L6-v2, 384-d) embedding of the question text |
| **S2** | image features only (see B.2) |
| **S3** | S1 ⊕ S2 concatenated |

**S1 cannot survive Gate 2.** Within a byte-identical block every S1 feature is constant by
construction, so S1's AUROC is exactly 0.5 as a *structural* fact about the block, not an
*empirical* finding about predictability. S1 is reported only to document that structural
degeneracy. A SURVIVED verdict may never rest on S1.

#### B.2 — Image features (required)

- **CLIP or SigLIP embedding** of the input views, mean-pooled across views
  (ViT-B/32 or SigLIP-base; state which, and freeze the checkpoint).
- **Cheap visual statistics**, per view and aggregated: resolution, mean and std pixel intensity,
  edge density (Sobel or Canny fraction), and encoded byte size as a scene-complexity proxy.
- **Task-structure similarity features.** For `spatial_viewpoint_identification` the question is
  "which option image matches the query view", so compute the CLIP cosine similarity between the
  query image and each of the 5 option images, and derive:
  - max similarity,
  - the **top-1 − top-2 margin** (a natural difficulty proxy: a small margin means two options are
    near-indistinguishable from the query),
  - the entropy of the similarity distribution.

  These make S2 a genuinely strong baseline rather than a formality. An analogous
  query-vs-candidate similarity feature must be constructed for any other block whose task has the
  same match-one-of-N structure; where it does not apply, state so.

**Images must be downloaded for this.** Audit 1 used a metadata-only path, but the main experiment
must fetch all 6,453 images regardless in order to run the models, so this adds no extra cost.

#### B.2a — Per-block S2 feature availability (must be reported)

**[ADDITION — 2026-10-05]** The query-to-option margin feature is only defined where the options
*are* images. Audit 1 establishes that this holds in exactly one category:

| block | n | options are | S2 features available |
|---|---|---|---|
| spatial_viewpoint_identification | 137 | **images** (`"Option A picture."` + 5 option images) | **FULL** — CLIP embedding, visual stats, query-to-option margin + entropy |
| robotic_affordance_recognition | 128 | text (`"Blue line."` …) | generic only |
| spatial_3d_spatial_consistency | 105 | text (coordinate tuples) | generic only |
| spatial_distance_judgement | 55 | text (grasp descriptions) | generic only |
| spatial_cross_view_matching | 41 | text (`"The yellow bounding box."` …) | generic only |

**Only 137 of the pooled 466 (29%) admit the strong feature; 71% do not.** The seven non-matching
categories supply 3 synchronized camera views with text options, so there is no query-to-option
correspondence to score.

For the multi-view blocks, S2's strongest available family is **inter-view CLIP similarity** —
pairwise cosine similarity among the 3 views, plus its min/mean/spread — which proxies how much
non-redundant information the extra views carry. This must be computed for those blocks so they
are not reduced to pixel statistics alone, but it is acknowledged as weaker than the
query-to-option margin.

**Reporting requirement.** S2 and S3 results must be reported **separately for the two
availability classes** and must not be pooled into a single verdict sentence:

> A near-chance S2 in a block where the query-to-option margin was unavailable is **not** evidence
> that image features fail to predict. It is evidence that the strong feature did not exist in
> that block. These two cases must not be pooled.

Because the strong feature covers only 29% of the pooled sample, a near-chance *pooled* S2 is by
default the weaker reading. The FIRES condition may therefore be met by the FULL-availability
block alone; the SURVIVED condition requires near-chance results in **both** classes, and the
FULL-availability block is underpowered on its own (§B.5) — this limitation must be stated in
the verdict rather than resolved by pooling.

#### B.3 — Fitting protocol

- LogisticRegression, L2, 5-fold CV, **OOF AUROC** reported (following StudyN2's selection
  criterion, which correctly rejected an in-fold-inflated predictor; see
  `reports/study_n2_results.md` §8).

- **[ADDITION — 2026-10-05] Folds are assigned at the BLOCK level, never per question.**
  All questions sharing a byte-identical question string go into the same fold
  (`GroupKFold`, groups = the block id). This mirrors StudyN2's discipline, which grouped its
  5-fold CV by `video_id` and confirmed no video spanned folds
  (`reports/study_n2_results.md` §1).

  *Why this is mandatory here:* the 137 questions in the primary block share every text and
  metadata feature. Under per-question folds those questions appear in both train and test, so
  S1 would be fitting and scoring on identical feature vectors — its structural 0.5 would be
  inflated into a spurious positive, and S2/S3 would absorb any residual block-level signal.
  Per-question folding would silently invalidate the entire Gate 2 test.

  **Report:** the fold sizes, the block→fold assignment, and an explicit confirmation that no
  block spans folds. This confirmation is a required line in the results, not an assumption.
- **Dimensionality reduction is mandatory and must be fit inside each fold.** CLIP embeddings are
  512–768-d against ~69 positives at the pooled level; fitting them raw will overfit. Reduce via
  PCA to ≤ 20 components (or use strong L2 chosen by nested CV), with the reduction fit on the
  training folds only.
- Standard scaling applies to dense features (MiniLM, CLIP, visual stats). Do **not** apply
  `StandardScaler(with_mean=False)` to any sparse matrix — this is the exact error that inflated
  StudyN2's P3 in-fold AUROC to 0.9367.

#### B.4 — The AUROC must be block-stratified

Pooling blocks naively would let *between*-block signal (which is just category signal) inflate
the AUROC and destroy the test. The reported statistic is a **stratified AUROC in which only
within-block pairs contribute** — i.e. every comparison is between a positive and a negative drawn
from the *same* block. Between-block pairs are excluded. Report the per-block AUROCs alongside the
stratified pooled value.

#### B.5 — Power (Audit 3b)

Hanley-McNeil, rescue-rate prior 0.1475 from StudyK:

| scope | n | positives | 95% CI if AUROC = 0.70 | max observed AUROC still ruling out 0.70 |
|---|---|---|---|---|
| pooled IDEAL+USABLE blocks | 466 | 69 | [0.627, 0.773] | **0.620** |
| primary block alone | 137 | 20 | [0.565, 0.835] | 0.560 |

The single 137-block is **underpowered for a SURVIVED verdict**: an observed AUROC of 0.60 there
leaves an upper bound of 0.740 and cannot rule out 0.70. The pooled n = 466 is therefore the
primary unit; the 137-block is confirmatory only.

#### B.6 — Pre-registered decision rule

```
Gate 2 FIRES if S2 or S3 reaches stratified within-block OOF AUROC >= 0.70
    (CI lower bound > 0.5). The need IS statically predictable — just not from text —
    and the dynamicity claim is NOT supported by this workload.

Gate 2 is SURVIVED only if ALL of:
    (a) S1, S2 and S3 are all near chance, with 95% CI upper bound < 0.70
        (at pooled n=466 this requires observed AUROC <= 0.620), AND
    (b) an oracle shows a substantial rescue population within the blocks:
        within-block net_rescue > 5pp with CI lower > 0 (MDI 6.7pp at n=466).

    S1 near chance is NOT sufficient and NOT admissible on its own: its 0.5 is
    structural, not empirical.

Otherwise INCONCLUSIVE — report which variant carried signal and at what CI.
```

#### B.7 — What each verdict means (framed before running)

**[ADDITION — 2026-10-05]** Stated in advance so that neither outcome can be re-interpreted after
the numbers are seen.

| verdict | meaning |
|---|---|
| **Gate 2 FIRES** | The rescue population **is** predictable at arrival from cheap image features. This is a usable escalation predictor and a publishable routing result. It is **not a failure**, and it does **not** license searching for another workload. It means the dynamicity claim is not supported on this workload, and the project pivots to the predictor. |
| **Gate 2 SURVIVED** | No arrival-time feature predicts membership, and a rescue population demonstrably exists. Runtime signals have something to explain. |
| **Neither** (S2 near chance **and** net_rescue ≤ 5pp) | The branch is empty — there is no population worth routing to in the first place. **Stop.** |

The third row is the outcome that ends the line of work, and it is listed here so that it is not
quietly reported as "inconclusive" and used to justify a further workload search.

---

### §C — Demoted: between-category comparison (secondary, clearly labelled)

The original interaction `[Δ_Think(compositional)] − [Δ_Think(direct)]` is reported **as a
between-category comparison only**, with the following statement attached wherever it appears:

> This contrast cannot distinguish compositional view structure from category-level difficulty.
> In 6 of 8 categories the structural markers are 100% uniform, so "compositional" and "category"
> are the same variable in this dataset. Any interaction found is equally well explained by
> category difficulty.

Power: 424 per stratum for a 10pp interaction; MDI 7.0pp if the dataset is split into two
half-size category strata (n = 854 each).

---

### §D — Full-dataset static predictor (context for §B)

The Correction 3 predictor is retained, run on the full n = 1,708, to establish the *between*-
category AUROC ceiling against which the within-block residual of §B is contrasted. Report:

1. Category one-hot alone.
2. Category + `n_views` + `q_len`.
3. Category + `n_views` + `q_len` + MiniLM embedding (StudyN2 P4 structure; P4 reached AUROC 0.765
   on a different label on LoCoMo).
4. The same three, each additionally with image features.

If category alone reaches AUROC ≥ 0.75 on the full dataset, that is itself strong evidence for a
design-time lookup policy at the *category* granularity, independent of the §B within-block result.

---

## Outputs

| File | Content |
|---|---|
| `reports/study_s0_audits.md` | Audit report with all three audits and GO/NO-GO verdict |
| `results/erqa/study_s0/audit1_mvrobobench.json` | 1,708 question records (metadata) |
| `results/erqa/study_s0/audit1_summary.json` | Category counts, confound check, homogeneity |
| `results/erqa/study_s0/audit2_trials.jsonl` | 300 decoding-config trials |
| `results/erqa/study_s0/audit3_power.json` | McNemar power |
| `results/erqa/study_s0/audit3b_auroc_power.json` | Gate 2 AUROC power |

---

## GO/NO-GO criteria — outcome

Evaluated in `reports/study_s0_audits.md` §4:

1. **Audit 1** — *FAILED as written.* The criterion assumed n_direct ≥ 400 and
   n_compositional ≥ 400; those strata do not exist. Resolved by the approved restructure above.
2. **Audit 2** — *CONDITIONAL.* think_closed = 100% (pass); the closest config sits 6.3pp from
   47.3% against a 5pp threshold. The threshold presumed the vendor number is reproducible; it
   was not reproduced in StudyK (−2.2pp) or StudyQ (−4.1pp). Recorded as a known fragility.
3. **Audit 3** — *PASS.* MDI 3.5pp full-dataset, ≤10.3pp per category, 7.0pp for half-dataset
   strata, 6.7pp for the pooled Gate 2 blocks.

**Decision: GO under the restructured design above.** The main experiment runs both arms over all
1,708 questions, with §B (pooled blocks, n = 466) as the primary analysis.

### Still open before the main experiment runs

- **License.** MV-RoboBench declares no license on its HF page and the paper states only that it
  is released as "an open resource". This is an unresolved publication risk — see
  `reports/study_s0_audits.md` §7.
- **Image download.** ~6,453 images must be fetched; Audit 1 deliberately avoided this.
- **Runtime projection.** 1,708 questions × 2 arms. At the Audit 2 median of ~14.9 s per Thinking
  question, arm T alone projects to ~7.1 h; MV-RoboBench supplies 3–6 images per question versus
  ERQA's 1–2, so this is a lower bound. Project from the first 10 trials before committing, and
  report the projection.

---

# StudyS1 AMENDMENT — competent-category stratum

**Pre-registered 2026-10-05, BEFORE arm T was run on this stratum.** Arm T had at that point been
run only as a 60-question pilot on the 137-block; no arm T data existed for either category below.

## Why this is an instrument replacement, not post-hoc fishing

A reader must be able to see this distinction, so it is stated plainly.

**The 137-block was abandoned because it cannot measure, not because it measured against us.**
It was pre-registered as primary on the grounds that its static features are *provably* degenerate
— every arrival-time text and metadata feature is constant across the block, forcing static AUROC
to 0.5 by construction. The pilot established that the block is **also label-degenerate**: both
arms sit at chance (arm I 23.3%, arm T 26.7% ± 11.2), discordance is 30% and near-symmetric
(b=10, c=8), and net_rescue is +3.3pp with CI [−10.5, +17.2] at n=60. A label produced by two
coin flips cannot be predicted by anything, so no predictor result from that block would carry
information. That is a broken instrument. Abandoning an instrument that **cannot** measure is a
different act from abandoning one that measured unfavourably, and only the latter is fishing.

**The stratum was selected on a criterion independent of the hypothesis.** The competent
categories were identified from **arm I alone, before arm T ran on them**. The selection criterion
is model competence — *not* any thinking-vs-instruct contrast, and not any quantity that appears
in the Gate 1 test:

> **Criterion:** arm I accuracy with a Wilson 95% CI **lower bound > 25%**, i.e. clearly above the
> 20% five-choice chance baseline.

| category | n | arm I acc | Wilson 95% CI | selected |
|---|---|---|---|---|
| spatial_distance_judgement | 201 | 41.3% | [34.7, 48.2] | **yes** |
| robotic_trajectory_selection | 200 | 33.5% | [27.3, 40.3] | **yes** |
| spatial_cross_view_matching | 200 | 26.5% | [20.9, 33.0] | no |
| robotic_step_execution | 234 | 24.8% | [19.7, 30.7] | no |
| spatial_viewpoint_identification | 256 | 24.2% | [19.4, 29.8] | no |
| robotic_action_planning | 204 | 20.6% | [15.6, 26.7] | no |
| robotic_affordance_recognition | 209 | 19.6% | [14.8, 25.5] | no |
| spatial_3d_spatial_consistency | 204 | 9.3% | [6.0, 14.1] | no |

**Stratum: n = 401.** The criterion separates cleanly — the next candidate's CI lower bound is
20.9%, essentially touching chance.

## Condition 1 — honest labelling (binding on the report and the registry)

Both must state, without softening:

- the 137-block was the **pre-registered primary instrument**;
- it returned a **degenerate label** — both arms at chance, net_rescue +3.3pp, CI [−10.5, +17.2],
  n = 60;
- the competent-category run is a **SECONDARY, POST-HOC stratum**;
- the verdict must read **"Gate 1 tested on a post-hoc stratum"** and must never be phrased as if
  the original design had been executed.

## Condition 2 — this run answers Gate 1 ONLY

Gate 2 required the byte-identical homogeneous block, and that block is dead. The competent
categories admit only **generic S2 features**: their options are text (`"The blue line."`,
`"Grab the item in the blue bounding box…"`), so the query-to-option CLIP margin — the one strong
image feature — is undefined for them.

> **A positive Gate 1 result here does NOT advance to the dynamicity claim.** It establishes only
> that a rescue population exists, and that MV-RoboBench provides no instrument to test that
> population's predictability. **No Gate 2 verdict may be reported from this run.**

## Condition 3 — the stop, pre-registered now

```
Gate 1 PASSES if net_rescue on the competent categories exceeds 5pp with a paired 95% CI
    (clustered appropriately) EXCLUDING 0.

Otherwise: "Neither — branch is empty." STOP.
    No third stratum. No further category selection. No additional workload.
```

**A near miss does not license re-aiming again.** If net_rescue lands at, say, 4.5pp, or at 6pp
with a CI touching 0, the outcome is "Neither — branch is empty", not a reason to pool in a third
category, widen the stratum, or seek another dataset. This sentence is written before the number
is known precisely so that it cannot be renegotiated after.

## Run specification

- Arm T on the 401 competent-category questions. Model, decoding and budget identical to the
  pilot: 4B-Thinking snap `1de27d8c`, frozen config CFG-A (temp 0.6, top_p 0.95, top_k 20,
  `max_new_tokens` 8192), bfloat16, `cuda:1`.
- **Arm I is reused**, not re-run — those 401 trials already exist in
  `results/mvrobobench/study_s1/study_s1_trials.jsonl` from the completed arm I sweep. The report
  must identify them as reused and name that source.
- Projection: 4.9h at the pilot's 44.1 s/question. Report a revised projection after 10 trials.
  **If it exceeds 8h, report and continue** — do not reduce the sample; it is the whole stratum.

## Analyses — only these five

1. Accuracy per arm on the competent categories, with n and 95% CI, chance baseline marked.
2. Paired discordance: b, c, and net_rescue with CI; **b and c reported separately**.
3. Per-category breakdown with n per cell, flagged **descriptive, not confirmatory**.
4. Verdict against the Condition 3 rule, in the exact form specified.
5. Think-token distribution and latency, for the cost side.

## Sanity checks

- Arm I trials identified as reused, with their source file.
- `think_closed` and `budget_hit` recorded per trial.
- **Parse failures reported separately, never scored silently as wrong.**

## Output

`reports/study_s1_competent_categories.md` — verdict first, then the five analyses, with the
Condition 1 labelling stated at the top.
