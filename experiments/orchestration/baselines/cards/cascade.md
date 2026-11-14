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

## StudyB-baselines amendment 2 (2026-11-13)

**Item 3: the confidence is committed, and item 3b: it is declared and charged.** The recall
stage reads StudyE7 Job A's per-question `letter_probs` (the 4B-D2 configuration the harness
answers a DEVICE recall with) through `device_confidence.py`. FrugalGPT's scorer and AutoMix's
verifier both read the SMALL MODEL'S ANSWER, so `reads_device_answer = True` and the harness
charges that device answer (StudyD8's 0.567 s, a RULE) before the arm's next action on the query.

**The floor is now FITTED, on a pre-registered DEV split.** Until this amendment
`confidence_floor` was None, and the rule `if c is None -> DEVICE; elif floor is None or c < floor
-> CLOUD; else DEVICE` therefore escalated EVERY query that had a committed probability: 81 of 83
in the representative cell, with the 2 that stayed on the device being the ones with no committed
value. S-EMBER had no development split, so amendment 2 pre-registered one (`sember_split.py`:
split by video on sha256(video_id), lowest 30 % of the digest order to DEV, stratified by video
length bucket) and the floor is the **median committed device confidence over DEV questions =
0.7358**. Every recall metric in this suite is now reported on EVAL questions only, so the floor
is not fitted on anything it is scored over.

**Measured consequence** on the representative cell. On the pre-amendment question set, so that
the before and after are the same cell: recall timely accuracy 0.3048 -> 0.3405 and recall
decisions 83 DEVICE -> 40 CLOUD + 43 DEVICE (the 43 are the queries whose committed device
confidence is at or above the fitted floor, plus the 2 with no committed value at all). On the EVAL split, which is what every recall metric
is now reported on, the arm's timely accuracy is 0.3330.
