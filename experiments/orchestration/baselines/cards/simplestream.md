<!-- StudyB-baselines (addendum). FAITHFUL = unchanged from the original; ADAPTATION = changed, with its reason. Fairness rules 1-6 of the addendum hold for this baseline and are checked by `interface.check_fairness` and the smoke harness. -->
# SimpleStream (arXiv:2604.02317) — case B, REQUIRED

**Paper.** Y. Shen, S. Tian, J. Yang, Z. Liu, "A Simple Baseline for Streaming Video
Understanding", arXiv:2604.02317 (2 Apr 2026). **Verified by the arXiv API.** Its finding: "a
sliding-window baseline that feeds only the most recent N frames to an off-the-shelf VLM already
matches or surpasses published streaming models."

**Code.** `https://github.com/EvolvingLMMs-Lab/SimpleStream`, cloned to
`~/baselines_src/simplestream`, pinned `be227ee8ce90`.

> **LICENCE FLAG, the same as Ekya's.** The repository contains **no LICENSE or COPYING file** and
> the README names none, so no use or modification right is granted. The clone is used for
> citation and commit pinning only; **no file in it was opened, run or copied**, and this adapted
> policy is written from the paper. Surfaced for the user.

**Files.** `simplestream_adapted.py`. **Experiment:** B-recall.

## THE WINDOW IS FITTED, NOT CHOSEN TO BE WEAK

The addendum requires "the best feasible recent window, window size selected on training data
only ..., never an arbitrarily poor window", and that requirement is the difference between a
fair baseline and a straw man. `_select_window()` scores each candidate window on the **StudyD3
development split** by the AUROC with which the device's own window statistic separates positive
from negative development clips, and takes the best:

| window | 1 s (4 steps) | 3 s (12) | 5 s (20) | 10 s (40) |
|---|---|---|---|---|
| development AUROC | **0.654** | 0.644 | 0.632 | 0.632 |

**Selected: 1 s.** The candidate set, every score and the winner are recorded on the policy
object (`selection`) so a reviewer can see the fit.

## Mapping

| paper | our code | note |
|---|---|---|
| sliding window of the most recent N frames | representation `RECENT` on the cloud, no history reuse | FAITHFUL in role |
| off-the-shelf VLM | our 32B cloud arm, unchanged | FAITHFUL (fairness rule 1) |
| window size N | selected on the development split (above) | FAITHFUL to the addendum's requirement |
| its 13-model offline comparison | — | NOT REPRODUCED |

## Adaptations, with reasons

- **A1 the window is expressed as a representation.** Our action space offers representations, not
  a free frame count for recall, so "most recent N frames" is `RECENT` — the committed
  recent-window representation StudyRH3 / RH4 built.
- **A2 no history is reused.** That is the point of the baseline: it tests whether a recent window
  alone suffices, so it never asks for D2 or RICH.

## Not reproduced, and why

The paper's benchmark comparison against 13 offline models; its frame-count sweep inside a single
VLM call (our RECENT representation has a fixed, measured frame budget).

## Hyperparameters and provenance

| name | value | from |
|---|---|---|
| window | 1 s, selected on development data | `_select_window()` over StudyD3, 6,010 rows / 601 clips |
