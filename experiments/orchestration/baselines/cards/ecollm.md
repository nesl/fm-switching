<!-- StudyB-baselines (addendum). FAITHFUL = unchanged from the original; ADAPTATION = changed, with its reason. Fairness rules 1-6 of the addendum hold for this baseline and are checked by `interface.check_fairness` and the smoke harness. -->
# ECO-LLM (arXiv:2507.09003) — case D, P0

**Paper.** P. Patidar, A. Crown, K. Hsieh, Y. Xu, "ECO-LLM: Orchestration for Domain-specific
Edge-Cloud Language Models", arXiv:2507.09003 (11 Jul 2025, Microsoft Research). **Verified by
the arXiv API.**

> **NAME CHECK.** The id resolves to a paper whose *title* is "Orchestration for Domain-specific
> Edge-Cloud Language Models"; ECO-LLM is the system name inside it. A **different** 2024 paper,
> "ECO-LLM: LLM-based Edge Cloud Optimization", also uses the name — OpenAlex returns that one for
> a title search. The id given in the addendum is the Microsoft Research one, which is what is
> implemented here.

**Code.** None found (searched the arXiv page, the authors' pages, Microsoft Research, GitHub by
title and author; the only GitHub links in the PDF are unrelated dependencies). **Case D.**

**Files.** `reconstructed/ecollm.py`, `reconstructed/test_ecollm_toy.py`, `ecollm_adapted.py`.
**Experiments:** A-episodic, B-recall, C-mixed.

## The paper's algorithm

Its stated insight: prior work "primarily focus[es] on selecting the best LLM model ... while
neglecting the critical interplay between the components of the LLM serving pipeline", naming
RouteLLM and AutoMix as examples. ECO-LLM therefore (a) "systematically expl[ores] component
configurations" offline, with an **Emulator** that "efficiently explores the vast configuration
space", and (b) "dynamically select[s] optimal resource[s]" per query so that user-defined
**SLOs** are met while accuracy stays stable.

## Mapping, step by step

| paper | our code | note |
|---|---|---|
| configuration space | the joint product of our actions: episodic (mode, cadence, N) and recall (tier, representation) | ADAPTATION A1 |
| Emulator | `explore(space, evaluate)` with `evaluate` reading committed measurements | ADAPTATION A2 |
| SLOs | `SLO(max_latency_s, max_cost_gpu_s, min_quality)` = the query's deadline and the remaining budget | FAITHFUL in role |
| dynamic selection | `select(points, slo)`: highest quality among feasible; least-violating otherwise | FAITHFUL |
| tie-breaking | lower cost wins, matching "meets SLOs while maintaining stable accuracy" at lower cost | FAITHFUL |

## Adaptations, with reasons

- **A1 the configuration space is ours.** The paper's components include context retrieval/RAG;
  we have no retrieval stage, so the joint space is (tier, representation) for recall and
  (mode, cadence, N) for episodic. The *jointness* — the paper's whole point — is preserved.
- **A2 the Emulator is replaced by measurement.** The Emulator runs the pipeline, which needs
  inference. We read StudyE9b / E9c (episodic quality), StudyRH5 / E10b (recall service time) and
  `costs` (GPU-seconds, latency). **Consequence: our exploration is exact and exhaustive rather
  than emulated, which makes selection easier than in the paper.**
- **A3 recall representation quality is ORDINAL, not measured.** `REP_QUALITY` gives RECENT 0.6
  and D2 = RICH 1.0, from StudyRH4's committed finding that D2 = K1. These are **ordinal weights,
  not accuracies**, and no accuracy claim may be read off them. FLAGGED as the weakest input.

## Not reproduced, and why

The Emulator; the retrieval/RAG component of the configuration space; the domain-specific tuning
of its evaluation; its hardware-platform comparison.

## Hyperparameters and provenance

| name | value | from |
|---|---|---|
| SLO budget | the remaining GPU-seconds divided across live streams | our budget, not the paper's |
| recall SLO | the query's own deadline | the observation |
| `REP_QUALITY` | 0.6 / 1.0 / 1.0 | ordinal, from StudyRH4 (A3) |
