<!-- StudyB-baselines (addendum). FAITHFUL = unchanged from the original; ADAPTATION = changed, with its reason. Fairness rules 1-6 of the addendum hold for this baseline and are checked by `interface.check_fairness` and the smoke harness. -->
# StreamScout (arXiv:2609.00291) — case D, P0 for recall

**Paper.** "StreamScout: Learning When to Look Deeper for Streaming Video Understanding",
arXiv:2609.00291. **Verified by the arXiv API** (the addendum gave no id; it was found by title
search).

**Code.** None found. **Case D.**

**Files.** `reconstructed/streamscout.py`, `reconstructed/test_streamscout_toy.py`,
`streamscout_adapted.py`. **Experiment:** B-recall.

## The paper's algorithm

"Up to three increasingly informative visual views: a glance at recent frames, a uniform
look-back, [and a query-relevant view]. At each stage, the model answers immediately if the
available evidence is sufficient; otherwise, it escalates to the next view." The stop-or-escalate
policy is then sharpened by distillation: "we evaluate every stage of the cascade on an auxiliary
training set and identify the earliest stage at which the [answer is] adequate"; StreamScout-R
explores stopping behaviour beyond imitating that policy.

## Mapping, step by step

| paper | our code | note |
|---|---|---|
| view 1, recent glance | representation `RECENT` | FAITHFUL in role |
| view 2, uniform look-back | representation `D2` — StudyRH4's **fixed-stride** history, a uniform look-back by construction | FAITHFUL in role |
| view 3, query-relevant | representation `RICH` (the full history) | ADAPTATION A1 |
| stop-or-escalate loop | `cascade(signals, thresholds)` | FAITHFUL |
| distillation on a training set | `fit_thresholds` on the **StudyD3 development split** | FAITHFUL in procedure |
| sufficiency signal | the device answer's confidence, else the evidence count | ADAPTATION A2 |
| StreamScout-R | — | NOT REPRODUCED |

## Adaptations, with reasons

- **A1 no query-relevant retrieval.** We have no retrieval stage, so the deepest view is the full
  history rather than a query-relevant subset of it. **Consequence: the third stage is more
  expensive than the paper's and no cheaper in quality**, which disadvantages this baseline at
  depth; stated rather than hidden.
- **A2 the sufficiency signal is not the model's own.** The paper reads it from the VLM; we use
  the device answer's confidence where one exists and the evidence inventory's coverage
  otherwise.
- **A3 the earliest-adequate label.** On StudyD3, "adequate at stage *i*" is taken to mean the
  cloud arm would not have improved on the device by more than a margin at that depth. That is a
  committed-trace proxy for the paper's correctness label, and it is development-split only.

## Not reproduced, and why

The query-relevant retrieval; the VLM's sufficiency head; StreamScout-R's RL exploration; the
paper's token and latency measurements.

## Hyperparameters and provenance

| name | value | from |
|---|---|---|
| thresholds | distilled, `[-9.664, -10.970, -inf]` | `fit_thresholds` on 6,010 StudyD3 development rows |
| last threshold | `-inf` | the paper: the deepest view must answer |
