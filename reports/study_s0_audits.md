# Study S0 — Pre-Registration Audits

**Date:** 2026-10-05
**Status:** All three audits complete. **Main experiment NOT started** — awaiting review.
**Plan:** `reports/study_s0_plan.md` (v2, with Corrections 1–3)

No hypothesis test is performed in S0. These audits produce the inputs (frozen config, n, strata,
instrument selection) for a pre-registered experiment.

---

## Headline

| Audit | Result |
|---|---|
| 1 — Dataset | **The planned direct/compositional contrast does not exist.** It is determined by category in 6/8 categories. However, the dataset contains large *statically-identical* question blocks that make it an unusually strong Gate 2 instrument. |
| 2 — Decoding | All three configs are statistically indistinguishable (40.0–41.0%, CIs span ~19pp). Zero budget hits in all 300 trials. Frozen config: **CFG-A**, on grounds of cross-study consistency. |
| 3 — Power | Net-rescue MDI = 3.5pp at full dataset, ~9–10pp per category. Gate 2 pooled-block MDI = 6.7pp at n=466. |

**Recommendation: GO, but the design must be restructured** — the primary analysis should become
the Gate 2 within-block test, not the direct/compositional interaction. This is a methodological
change and requires sign-off before implementation (see §5).

---

## 1. Audit 1 — MV-RoboBench dataset audit

**Source:** `AaronFengZY24/MV_Robobench` (HF dataset). No explicit license declared on the HF page.
**Method:** metadata-only. 1,708 `QA.json` files downloaded; per-question view counts derived from
the repo file listing. Images were never downloaded. Scripts:
`experiments/erqa/study_s0_audit1.py`, `experiments/erqa/study_s0_audit1_analyze.py`.

### 1.1 Composition

n = **1,708** questions, 5-choice, across 8 categories and 2 source corpora.

| source | n | image resolution |
|---|---|---|
| agiworld | 1,147 | 640×480 RGB |
| bridgev2 | 561 | 256×256 RGB |

| category | n |
|---|---|
| robotic_action_planning | 204 |
| robotic_affordance_recognition | 209 |
| robotic_step_execution | 234 |
| robotic_trajectory_selection | 200 |
| spatial_3d_spatial_consistency | 204 |
| spatial_cross_view_matching | 200 |
| spatial_distance_judgement | 201 |
| spatial_viewpoint_identification | 256 |

`QA.json` schema: `question`, `options`, `correct`, `type`, `images` (each with `path` and an
`illustration` label naming the view, e.g. "left gripper view", "head view").

### 1.2 Direct/compositional contrast — **cannot be constructed**

The contrast was to be judged from question construction: compositional = answering requires
combining evidence across ≥2 views. Operationalised by two structural markers in the question text:
an **anchor** (`"options are based on <one named view>"`, i.e. the reasoning frame is a single view)
and a **cross-view cue** (`"across these images"`, `"corresponds to the same"`,
`"each color appears exactly once"`, `"synchronized views"`).

| category | n | anchored | cross-cue | 100% uniform? |
|---|---|---|---|---|
| robotic_action_planning | 204 | 100% | 0% | **YES** |
| robotic_affordance_recognition | 209 | 0% | 100% | **YES** |
| robotic_step_execution | 234 | 100% | 0% | **YES** |
| robotic_trajectory_selection | 200 | 0% | 68% | no |
| spatial_3d_spatial_consistency | 204 | 100% | 100% | **YES** |
| spatial_cross_view_matching | 200 | 0% | 13% | no |
| spatial_distance_judgement | 201 | 0% | 100% | **YES** |
| spatial_viewpoint_identification | 256 | 0% | 0% | **YES** |

**6 of 8 categories are 100% uniform on these markers.** The direct/compositional distinction is
therefore *determined by* the category label, not orthogonal to it.

Consequence: the pre-registered interaction `[Δ_think(compositional)] − [Δ_think(direct)]` is a
**between-category comparison**, not an independent within-category factor. It cannot separate
"compositional structure" from "category identity" — those are the same variable in this dataset.
Any interaction found would be equally well explained by category-level difficulty.

### 1.3 Correction 2 — within-category homogeneity of arrival-time features

Features a static predictor can see before execution: category label, `n_views`, question length,
view-label configuration, and the question text itself (→ MiniLM embedding).

| category | n | distinct question strings | largest identical block | n_views mean(sd) | verdict |
|---|---|---|---|---|---|
| spatial_viewpoint_identification | 256 | **2** | **137** (54%) | 6.00 (0.00) | **IDEAL** |
| robotic_affordance_recognition | 209 | 2 | 128 (61%) | 3.39 (0.49) | USABLE |
| spatial_3d_spatial_consistency | 204 | 13 | 105 (51%) | 3.39 (0.49) | USABLE |
| spatial_distance_judgement | 201 | 23 | 55 (27%) | 3.40 (0.49) | USABLE |
| spatial_cross_view_matching | 200 | 68 | 41 (20%) | 3.40 (0.49) | USABLE |
| robotic_trajectory_selection | 200 | 194 | 4 | 3.40 (0.49) | weak |
| robotic_action_planning | 204 | 200 | 2 | 3.39 (0.49) | weak |
| robotic_step_execution | 234 | 231 | 2 | 3.34 (0.47) | weak |

- **IDEAL** — a large block identical on *every* arrival-time static feature. A static predictor
  must assign all members the same score, so its within-block AUROC is exactly 0.5 by construction.
- **USABLE** — substantial repeated blocks; partial static degeneracy.
- **weak** — questions textually near-unique; a MiniLM embedding may well separate them.

**Primary Gate 2 instrument: `spatial_viewpoint_identification`.** Its 256 questions contain only
**two** distinct question strings — 137 questions share one byte-identical string
("Given the image captured by the head camera, which of the following images shows the
left-gripper camera's view at that exact moment?") and 119 share the other. Within the 137-block,
category, `n_views` (6, sd=0), view configuration, question length, and the full text are all
constant; only the *images* differ.

This is the ideal instrument in the sense set out in the plan: a dataset with large
between-category and near-zero within-category static variance. Between/within variance ratios
across the full dataset are 4.33 for `n_views` and 110.6 for question length — question length is
almost entirely a function of category.

If Thinking rescues some members of the 137-block and wastes tokens on others, that variance is
**unreachable** by category, `n_views`, question length, or any text embedding, because every one
of those features is identical across the block. That is the condition under which Gate 2 is
survived.

---

## 2. Audit 2 — Decoding and software-stack validation

**Model:** Qwen3-VL-4B-Thinking, snapshot `1de27d8c`, bfloat16, **single GPU (`cuda:1`, RTX A6000)**.
**Data:** 100 ERQA questions (seed=42 shuffle of the 400-question test set, sorted indices).
**Script:** `experiments/erqa/study_s0_audit2.py` · **Trials:** `results/erqa/study_s0/audit2_trials.jsonl` (300)

### 2.1 Software stack

| component | version |
|---|---|
| transformers | **5.12.1** |
| torch | 2.4.1+cu118 |

**Looping-issue check: NOT AFFECTED.** The known Qwen3-VL repetition-loop regression
(olmo-eval issue #441) affects transformers **5.17.x**, where 10–37% of outputs degenerate into
repetition versus 2–3% under 5.7.0. This run is on 5.12.1, outside the affected range. The observed
5% loop rate is consistent with the sub-5.17 baseline.

### 2.2 Caching and device disclosure

Prefix caching was not enabled. Each question was a fresh `generate()` call with no shared prefix
across questions and no reuse of prior KV state; nothing was cached before measurement.

**Device-configuration note.** An initial partial run (60 CFG-A trials) executed with
`device_map="auto"`, which split the 4B model across both GPUs. Those 60 trials were **discarded**
and re-run, because latency is a reported metric and a split-device run is not comparable to a
single-device one. All 300 trials reported here were produced on `cuda:1` alone.

### 2.3 Results

| config | temp | max_new_tokens | acc | 95% CI (Wilson) | think med | IQR | max | lat med | budget hits | loops | think_closed |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **CFG-A** (ours) | 0.6 | 8,192 | **41.0%** | [31.9, 50.8] | 668 | [256, 1231] | 3,841 | 14.9 s | **0/100** | 5 | 100% |
| CFG-B (card) | 1.0 | 40,960 | 40.0% | [30.9, 49.8] | 640 | [234, 1226] | 8,491 | 14.4 s | **0/100** | 5 | 100% |
| CFG-C (card, capped) | 1.0 | 16,384 | 40.0% | [30.9, 49.8] | 640 | [234, 1226] | 8,491 | 14.4 s | **0/100** | 5 | 100% |

### 2.4 Interpretation

**The ~6pp shortfall against the published 47.3% is unexplained.** It is *not* a budget artifact:
there were **0/100 budget hits in every config**, and the longest think trace observed (3,841 tokens
in CFG-A) reaches 47% of even the smallest cap. Nothing was truncated, so truncation cannot
account for the gap. CFG-B — temperature 1.0 with a 40,960-token budget, i.e. five times the
headroom — did not close it either.

The shortfall reproduces a pattern already present in the committed record: StudyK measured
THINKING at 45.1% (−2.2pp vs published) and StudyQ measured 4B-T at 43.2% (−4.1pp vs published).
Our 41.0% on a 100-question subset has a CI of [31.9, 50.8], which comfortably includes both prior
values. The harness is therefore consistent with our own prior committed measurements; what is not
reproduced is the *vendor's* number, and that was already true in two earlier studies. The cause
remains open.

**CFG-B = CFG-C is a tautology, not a finding.** The two configs differ only in `max_new_tokens`
(40,960 vs 16,384). Since neither cap ever binds, that single difference never takes effect, and
with the same seed and temperature the two runs are necessarily byte-identical. This is not
evidence that budget does not matter in general; it is a statement that within this run the only
thing distinguishing the two configs was inert.

The informative comparison is **CFG-A vs CFG-B** — temperature 0.6 vs 1.0. They differ by **1.0pp**
with confidence intervals spanning roughly 19pp. At n=100 these are **indistinguishable**.

**Repetition loops are not identical across configs.** The looping question IDs are:

| config | looping question IDs |
|---|---|
| CFG-A | 231, 253, 257, 259, 284 |
| CFG-B | 68, 130, 144, 240, 331 |
| CFG-C | 68, 130, 144, 240, 331 |

CFG-B and CFG-C coincide for the tautological reason above. CFG-A and CFG-B share **zero** of
their five looping questions. The loop set is therefore not stable across decoding temperature —
which argues *against* treating looping as a fixed property of particular questions, and leaves
both temperature and sampling noise as live candidates at this sample size (5 events per config is
far too few to separate them). The library-version hypothesis is ruled out here by §2.1.

### 2.5 Cross-workload contrast on non-termination

| workload | model + decoding | budget | non-termination |
|---|---|---|---|
| ERQA (this audit) | 4B-Thinking, temp 0.6 | 8,192 | **0/100 (0%)** |
| SiGNgapore2D (StudyJ2) | 4B-Thinking, temp 0.6 | 24,576 | **20–30%** |

Same model, same decoding family, a *larger* budget on the workload that fails to terminate.
Non-termination is therefore **workload-dependent, not a property of the model**. Any claim about
reasoning-length behaviour must be stated per workload.

### 2.6 Frozen config decision

**Frozen config: CFG-A** (temperature 0.6, top_p 0.95, top_k 20, max_new_tokens 8,192).

The rationale is **consistency with StudyK, StudyP, and StudyQ**, which all used this configuration.
It is explicitly *not* accuracy: 41.0% vs 40.0% at n=100 is noise, and the three configs'
confidence intervals almost completely overlap.

**Disclosed deviation from vendor guidance.** The Qwen3-VL-Thinking model card recommends
**temperature = 1.0** for vision-language tasks. CFG-A uses 0.6 and therefore departs from that
recommendation. The deviation is taken on cross-study-consistency grounds, and is defensible here
because the two settings are statistically indistinguishable on this workload (§2.4). The 8,192
budget is sufficient on ERQA — the model never approaches it — but §2.5 shows this does not
generalise to other workloads.

---

## 3. Audit 3 — Power calculation

**Script:** `experiments/erqa/study_s0_audit3_power.py` · **Output:** `results/erqa/study_s0/audit3_power.json`
**Test:** McNemar paired, α = 0.05 two-tailed, power = 0.80.
**Discordance prior:** StudyK on ERQA — b = 59, c = 49, n = 400 ⇒ p_discordant = 0.270,
observed net = +2.5pp. This prior is assumed to transfer to MV-RoboBench; if the true discordance
rate differs, required n scales linearly with it.

### 3.1 Correction 1 — net rescue

Gate 1 is evaluated on **net_rescue = P(I wrong, T correct) − P(I correct, T wrong)**, with both
discordant cells reported separately alongside the net.

| target net_rescue | n required |
|---|---|
| 5 pp | 848 |
| 10 pp | 212 |
| 15 pp | 94 |

Minimum detectable net_rescue at available n:

| scope | n | MDI |
|---|---|---|
| **full dataset** | 1,708 | **3.5 pp** |
| spatial_viewpoint_identification | 256 | 9.1 pp |
| robotic_step_execution | 234 | 9.5 pp |
| robotic_affordance_recognition | 209 | 10.1 pp |
| spatial_3d_spatial_consistency | 204 | 10.2 pp |
| robotic_action_planning | 204 | 10.2 pp |
| spatial_distance_judgement | 201 | 10.3 pp |
| robotic_trajectory_selection | 200 | 10.3 pp |
| spatial_cross_view_matching | 200 | 10.3 pp |

The full dataset is well powered for the Gate 1 net test. Per-category tests detect only
fairly large effects (~10pp).

### 3.2 Interaction (now a between-category contrast)

Per §1.2 this is no longer an orthogonal factor; n below is per stratum, where a stratum is a
*set of categories*.

| target interaction | n per stratum |
|---|---|
| 5 pp | 1,695 |
| 10 pp | 424 |
| 15 pp | 188 |

MDI: 14.6pp at the smallest category (n=200), 12.9pp at the largest (n=256), **7.0pp** if the
dataset is split into two half-size category strata (n=854 each).

### 3.3 Gate 2 within-block power

Within a statically-identical block every static predictor scores all members identically, so
within-block AUROC = 0.5 by construction. What must be estimated is whether the rescue population
inside the block is large enough to matter.

| category | block n | ±95% CI on rescue rate (at 15%) |
|---|---|---|
| spatial_viewpoint_identification | 137 | ±6.0 pp |
| robotic_affordance_recognition | 128 | ±6.2 pp |
| spatial_3d_spatial_consistency | 105 | ±6.8 pp |
| spatial_distance_judgement | 55 | ±9.4 pp |
| spatial_cross_view_matching | 41 | ±10.9 pp |

**Pooled IDEAL + USABLE blocks: n = 466** across 5 categories — ±3.2pp on the rescue rate, and
MDI for net_rescue within the pooled blocks of **6.7pp**. This is adequate to test Gate 2.

---

## 4. GO / NO-GO against the pre-registered criteria

| # | Criterion | Result |
|---|---|---|
| 1 | Audit 1: n_direct ≥ 400 **and** n_compositional ≥ 400, homogeneity assessed | **FAIL as written** — the strata do not exist (§1.2). Homogeneity assessed (§1.3) and is favourable. |
| 2 | Audit 2: a config within 5pp of 47.3% **and** think_closed ≥ 95% | **CONDITIONAL** — think_closed = 100% (pass); closest config is 6.3pp below 47.3% (marginal fail of a threshold that assumed the vendor number is reproducible; it was not reproduced in StudyK or StudyQ either). |
| 3 | Audit 3: MDI ≤ 15pp | **PASS** — 3.5pp full-dataset, ≤10.3pp per category, 7.0pp for half-dataset strata. |

---

## 5. Recommendation — requires sign-off before implementation

Criterion 1 fails because the dataset does not contain the factor the experiment was designed
around. This is a **design failure discovered by the audit**, which is what the audit is for; it is
not a result about the model.

Two of the three criteria cannot be met by simply running the planned experiment, so the design
must change. The recommended restructure:

1. **Demote the direct/compositional interaction.** Report it, clearly labelled as a
   between-category comparison that cannot distinguish compositional structure from category
   difficulty. It should not be the primary analysis.

2. **Promote the Gate 2 within-block test to primary.** Run both arms over the pooled
   IDEAL + USABLE blocks (n = 466), with `spatial_viewpoint_identification`'s 137-question
   identical block as the headline instrument. Within those blocks every arrival-time static
   feature is constant, so the static predictor's AUROC is 0.5 *by construction* and any
   net-rescue population found there is, by construction, not statically predictable. This is a
   stronger test of the thing the project actually needs to know than the original interaction was.

3. **Keep Gate 1 on the full dataset** (n = 1,708, MDI 3.5pp), reported as net_rescue with both
   discordant cells shown separately per Correction 1.

4. **Keep the Correction 3 static-predictor analysis** as specified, run on the full dataset. Its
   role is now to establish the *between*-category AUROC ceiling, against which the within-block
   residual is contrasted.

Per `CLAUDE.md`, changing strata and the primary metric is a **methodological change** and must be
discussed before being applied. **Not implemented. Awaiting direction.**

---

## 6. Files

| path | contents |
|---|---|
| `experiments/erqa/study_s0_audit1.py` | MV-RoboBench metadata fetch (no images) |
| `experiments/erqa/study_s0_audit1_analyze.py` | Category counts, confound check, homogeneity |
| `experiments/erqa/study_s0_audit2.py` | Decoding config validation |
| `experiments/erqa/study_s0_audit3_power.py` | McNemar power calculation |
| `results/erqa/study_s0/audit1_mvrobobench.json` | 1,708 question records |
| `results/erqa/study_s0/audit1_summary.json` | Audit 1 summary |
| `results/erqa/study_s0/audit2_trials.jsonl` | 300 decoding trials |
| `results/erqa/study_s0/audit3_power.json` | Power results |
