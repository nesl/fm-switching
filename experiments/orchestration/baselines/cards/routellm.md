<!-- StudyB-baselines. Written for a reviewer: everything faithful to the original is marked FAITHFUL, everything we changed is marked ADAPTATION with its reason. -->
# RouteLLM — case B

**Paper.** I. Ong, A. Almahairi, V. Wu, W.-L. Chiang, T. Wu, J. E. Gonzalez, M. W. Kadous,
I. Stoica, "RouteLLM: Learning to Route LLMs with Preference Data" (arXiv:2406.18665).

**Code.** `https://github.com/lm-sys/RouteLLM` (Apache-2.0), pinned `0b64fdafe049` (2024-08-10),
in `~/baselines_src/routellm`.

**Original smoke test.** Not run: `routellm/tests/{test_openai_client,test_openai_server}.py`
both require an OpenAI API key and network calls, and this task forbids handling credentials; the
`mf` router additionally downloads a checkpoint from HuggingFace. Recorded in
`results/orchestration/study_b_baselines/b_originals_smoke.json`.

**Files.** `routellm_adapted.py`.

## The paper's algorithm

RouteLLM learns a binary router from **preference data** (which of two models won) that decides
per query whether the weak or the strong model should answer, and **calibrates a threshold** to
hit a target strong-model call fraction. Its four routers are similarity-weighted ranking, a
**matrix factorisation** model, a BERT classifier and a causal-LLM classifier.

## Mapping, step by step

| paper | our code | note |
|---|---|---|
| weak / strong model | device 4B / cloud 32B | ADAPTATION A1 |
| preference label | which arm had the higher committed Nexar score at the same moment (development split) | ADAPTATION A2 |
| matrix-factorisation router | `_MatrixFactorisation` — with two models the Bradley-Terry factorisation collapses to one latent score per query, `sigmoid(⟨u(x), v_strong − v_weak⟩)` | ADAPTATION A3 |
| threshold calibration | the development-split quantile that sends exactly the target fraction to the strong model | FAITHFUL |
| BERT / causal-LLM routers | — | NOT REPRODUCED |

## Adaptations, with reasons

- **A1/A2 preference data from committed traces.** RouteLLM's labels come from human preference
  votes; ours come from which tier actually scored the moment higher. That is a preference in the
  same sense (a pairwise win) and needs no new measurement.
- **A3 a linear encoder.** The paper learns a query embedding; we use the six development-split
  trajectory features linearly. **Consequence: the router's capacity is much lower than the
  paper's.**
- **A4 calibration is exact here.** Because we calibrate on the development split and evaluate on
  validation clips, the realised strong-call fraction may drift from the target; the development
  fraction is recorded (`dev_strong_rate`, 0.500 at target 0.5).

## Not reproduced, and why

The BERT and causal-LLM routers (GPU training); the similarity-weighted ranking router (it needs
an embedding index over a query corpus we do not have); the paper's benchmark transfer results.

## Hyperparameters and provenance

| name | value | from |
|---|---|---|
| router | `mf` | the paper's strongest CPU-trainable router |
| `target_strong_fraction` | set by the harness to the matched budget | RouteLLM's own calibration procedure |
| threshold | 0.4969 at target 0.5 | development-split quantile |
| training rows | 6,010 over 601 development clips | StudyD3 |
