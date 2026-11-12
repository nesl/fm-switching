<!-- StudyB-baselines. Written for a reviewer: everything faithful to the original is marked FAITHFUL, everything we changed is marked ADAPTATION with its reason. -->
# INAR-VL (EdgeSys 2026) — case D

**Paper.** A. Sabanovic, P. J. Maliakel, I. Brandic, "INAR-VL: Input-Aware Routing for Edge-Cloud
Vision-Language Inference", arXiv:2605.18853; accepted at the 9th International Workshop on Edge
Systems, Analytics and Networking (**EdgeSys 2026**).

**Code.** None found (searched the arXiv page, both authors' pages and GitHub). **Case D.**

**Files.** `reconstructed/inarvl.py`, `reconstructed/test_inarvl_toy.py`, `inarvl_adapted.py`.

## The paper's algorithm (§3 / Figure 1, stage by stage)

1. **Input ingestion** — an (image, question) pair.
2. **Feature extraction** — image branch: **blur, exposure, artifact, detail**; text branch: six
   complexity signals — **length, entity/numeric density, question type, vocabulary complexity,
   reasoning markers, context-dependency markers**.
3. **Fusion** — "both branches are normalized and merged into a 10-dimensional request
   descriptor `r`".
4. **Router** — "jointly selects model and placement by optimizing predicted accuracy against
   latency and energy, approximating the Pareto frontier over edge and cloud candidates"; each
   candidate carries "three normalized strength descriptors in [0,1] (blur robustness,
   detail/OCR capability, and reasoning ability)".
5. **Decision** — "prioritizes edge execution when the predicted quality is sufficient, and
   otherwise offloads to the cloud only if the expected quality gain justifies the additional
   cost".

Measured operating points it reports: edge-only 66.5 % at 824 ms / 7.5 J; cloud-only 74.4 % at
2,408 ms / 26.0 J; INAR-VL keeps 36 % of requests on the edge, −24 % latency, −26 % energy, 97 %
of cloud accuracy. Routing overhead 10–30 ms of CPU.

## Mapping, step by step

| paper | our code | note |
|---|---|---|
| stage 3 fusion | `fuse` (exactly 10 dimensions) | FAITHFUL |
| stage 4 quality predictor | `predicted_quality` (demand-weighted match of the three strengths) | ADAPTATION A2 |
| stage 4 Pareto frontier | `pareto_frontier` over (quality, latency, energy) | FAITHFUL |
| stage 5 decision rule | `route` | FAITHFUL |
| image signals | the DEVICE's own delivered score-trajectory statistics | **ADAPTATION A1 — the largest departure** |
| text signals | the recall query's tokens, evidence count and deadline pressure | ADAPTATION A3 |
| candidate strengths | our measured accuracies, normalised | ADAPTATION A4 |
| latency / energy | `costs` (StudyD4 / D7 / D7b / D8 / RH5); energy set to 0 | ADAPTATION A5 |

## Adaptations, with reasons

- **A1 no pixels are read.** Computing blur/exposure/artifact/detail would be new measurement.
  We substitute the device's own trajectory statistics, because those signals exist in the paper
  to decide *when the edge model is out of its depth*, and a weak, flat, noisy device trajectory
  carries that same information in our setting. **It is nonetheless a substitution of a different
  signal family, and a reviewer should treat this baseline as "INAR-VL's router structure on our
  signals", not as INAR-VL.**
- **A2 the quality predictor's weights are not published**, so the reconstruction uses the
  paper's structure with unit weights; the adapted version supplies measured accuracies.
- **A5 energy is not modelled** — we have no committed per-request energy for the cloud tier, so
  `gain_per_joule` defaults to 0 and the trade-off runs on latency alone. FLAGGED: the paper's
  headline includes a 26 % energy saving that this baseline cannot express.

## Not reproduced, and why

The image signal extractors; the fitted quality predictor; the multi-model edge pool (Qwen-VL vs
LLaVA complementarity, its Table 1); the 10–30 ms routing overhead; energy.

## Hyperparameters and provenance

| name | value | from |
|---|---|---|
| `quality_floor` | 0.6 | our own; the paper tunes "sufficient quality" per deployment |
| `gain_per_second` | 0.2 | our own latency price, stated not fitted |
| `gain_per_joule` | 0.0 | no committed energy model (A5) |
