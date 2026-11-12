<!-- StudyB-baselines. Written for a reviewer: everything faithful to the original is marked FAITHFUL, everything we changed is marked ADAPTATION with its reason. -->
# Confidence cascade — FrugalGPT + AutoMix — case B

**Papers.** L. Chen, M. Zaharia, J. Zou, "FrugalGPT: How to Use Large Language Models While
Reducing Cost and Improving Performance", *TMLR 2024* (arXiv:2305.05176). P. Aggarwal, A. Madaan,
A. Anand et al., "AutoMix: Automatically Mixing Language Models", *NeurIPS 2024*
(arXiv:2310.12963).

**Code.** FrugalGPT `https://github.com/stanford-futuredata/FrugalGPT` (Apache-2.0), pinned
`2b23e6acbd4b`. AutoMix `https://github.com/automix-llm/automix`, linked from the paper's own
abstract ("`pip install automix-llm`"), Apache-2.0, pinned `531af3ee3c4e`. Both in
`~/baselines_src/`.

**Original smoke tests.** FrugalGPT: its committed offline cascade summary
(`summary/summary_HEADLINES_e8_full_2024.csv`) **loads and parses** — recorded as the CPU smoke.
Its package import needs `transformers` (a model stack), so the cascade itself was not run.
AutoMix: its `Scoring.ipynb` needs only pandas but reads
`data/automix_llama2_outputs_ver_n32.jsonl`, and the repo ships **no `data/` directory**, so its
own example cannot run without downloading generations. Both recorded in
`results/orchestration/study_b_baselines/b_originals_smoke.json`.

**Files.** `cascade_adapted.py`.

## The papers' algorithms

FrugalGPT has three cost levers: prompt adaptation, LLM approximation and the **LLM cascade**. The
cascade queries models in a learned order and **stops at the first answer a trained scorer judges
reliable**, with the scorer's threshold set by the cost budget.

AutoMix adds **self-verification** — the small model checks its own answer — and a **meta-verifier**
(a POMDP router) over that noisy verification signal, deciding whether to accept the small answer
or escalate.

What both fundamentally decide: *is the small model's answer good enough, or do we escalate?*

## Mapping, step by step

| paper | our code | note |
|---|---|---|
| cascade stage 1 / small model | device 4B | FAITHFUL |
| cascade stage 2 / large model | cloud 32B | FAITHFUL |
| scorer / verifier on an episodic stream | the device's **delivered** score against `tau_trigger` | ADAPTATION A1 |
| scorer / verifier on a recall query | `device_answer_confidence` (StudyD13 logprob) against a floor | FAITHFUL in role |
| threshold set by the cost budget | `tau_trigger` = the (1 − trigger_rate) quantile of the DEVICE arm's score on **development-split negatives** | ADAPTATION A2 |

## Adaptations, with reasons

- **A1 the episodic cascade IS StudyE9 / E9b escalation.** The task says so, and it is true: a
  threshold on the device's own delivered score that decides whether to call the 32B model is a
  two-stage confidence cascade. We therefore reuse that rule rather than inventing a second one.
- **A2 the threshold is fitted on the development split.** StudyE9 / E9b fit `tau_trigger` on
  the *evaluation* clips (cross-fitted within them). This suite's rule is stricter: the threshold
  comes from StudyD3's DEVELOPMENT clips. It lands at **−7.0009** at a 20 % trigger rate, against
  StudyE9b's cross-fitted −7.001 on validation — close, which is reassuring but not a result.
- **A3 two stages only.** FrugalGPT allows an arbitrary cascade length and learns the order; we
  have exactly two tiers, so the order is fixed and the length is 2.
- **A4 single-round verification.** AutoMix's meta-verifier is a POMDP solved over multiple
  verification rounds; we use the single-round threshold, which is AutoMix's own
  "self-verification" variant.

## Not reproduced, and why

FrugalGPT's prompt adaptation and LLM approximation (they change the prompt, not the placement,
and our action space has no prompt dimension); its learned cascade ORDER (two tiers leave nothing
to order); AutoMix's POMDP meta-verifier; both papers' trained scorers (they need the models).

## Hyperparameters and provenance

| name | value | from |
|---|---|---|
| `trigger_rate` | 0.20 primary | StudyE9 / E9b's primary trigger rate |
| `tau_trigger` | −7.0009 | fitted on 3,000 StudyD3 development-split negative scores |
| `confidence_floor` | caller-supplied, `None` by default | **no committed StudyD13 confidence distribution was used to pick one**; with `None` the cascade escalates whenever a device answer exists, which is the conservative reading. FLAGGED. |
