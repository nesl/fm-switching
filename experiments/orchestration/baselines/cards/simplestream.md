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

## StudyB-baselines amendment 2 (2026-11-13)

**Item 2: the episodic stream action follows `DEFAULTS["episodic_mode"]`.** The module's own
docstring said "episodic streams take the documented default"; the code emitted a literal
`StreamAction(sid, "local")`. That adapter bug is why StudySIM1c scored this arm at exactly the
device-only challenge mAP 0.4776 at every fleet size. With the fix its challenge mAP on the
representative cell is 0.5169 (ALL questions) and 0.5163 (EVAL), and its window selection, which
was always its point, is unchanged and still fitted on StudyD3's development clips.

## D133 live2 port note, added 2026-11-19: DEFERRED PENDING PART A, NOT SKIPPED

SimpleStream is **not ported to live2 yet**, and the reason is a gap in live2 rather than anything
about the baseline. Its mechanism is **unexpressible in the live2 action space as that space stands
today**, so a port made now would run cleanly and measure nothing.

**What it decides in our setting.** SimpleStream does not schedule. It chooses **which evidence to
send**: the most recent N frames instead of the full session history, with N fitted on StudyD3's
development split as recorded above. In live2 that choice is carried by
`RecallAction(q.query_id, "CLOUD", representation="RECENT")`.

**Why that cannot act today.** `RecallAction.representation` is **never read**. Every occurrence
across `live2/` and `live2/fleet/` is either an arm WRITING it (`arms.py:240`, `arms.py:370`,
`arms_policy.py:730`) or a `decides` / `defaults_used` declaration. Nothing consumes it. Worse,
`_submit_recall` sends and charges `max(int(s.est_tokens), 1)`, the **full believed history**,
whatever representation the arm asked for. So the evidence actually sent does not depend on the
arm's choice at all.

**The contrast that makes this a gap and not a design.** Dashcam-side evidence selection *is*
wired: `StreamAction.cadence_s` and `.frame_count` are read at `coordinator.py:409-410` and written
onto the device, and `frame_count` then reaches charged cost at `coordinator.py:495` through
`episodic_gpu_s("32BI", frame_count)`. An arm choosing how many frames per call, and how often,
acts on both behaviour and cost. The recall side has the same kind of lever and no reader. One half
of evidence selection is enacted and the other is inert, which is what identifies this as an
unfinished path rather than a deliberate restriction.

**Consequence if it were ported today.** With `representation` ignored, SimpleStream collapses to
always-CLOUD on full history: it would receive full-history latency AND full-history cost, and
score as a timeliness result that its actual design never produced. That is the shape of null this
study has been burned by before, and it is avoidable by waiting.

**Blocker.** Part A, extended to cover `RecallAction.representation` alongside `desired_tier`.
Session 1 owns it and will report when it lands. Port the moment it does; the card's adaptation,
including the fitted window, needs no change.

**Related.** QueryStream's Query-Aware Differential Pruning is blocked on the same path, and its
Proactive Response half is not. See `querystream.md`.

## Hit-7 reruns (2026-11-24): the fitted window applied, measured live

SimpleStream with its fitted 1-s window (hit 7, c511050), s4-s7 rerun cells: by_deadline (device-only floor beside) s4 0.174 (0.371, BELOW), s5 0.299 (0.299, AT), s6 0.132 (0.058, above), s7 0.229 (0.295, BELOW); delivery near-perfect: robot on time 132/132, 126/127, 121/121, 105/105; SS 356/357, 356/356, 357/357, 359/359. So at s4 and s7 answering from the cloud with a 1-s window was WORSE than the device-only fallback: on-time and correct are different axes, and a latency-optimal policy can be worse than not sending. Against the superseded fixed-window cells the change is +0.030 / 0 / -0.033 / -0.057 (mean -0.015, no consistent sign), EXPECTED because hit 7 corrected FIDELITY (1 frame per robot send, as the card specifies, verified live on every send; the old cells sent 6), not performance; the supersession is justified by fidelity alone. Related, NOT the same mechanism: cascade-routing sits on the floor because it almost never sends (port-rule fail); only its 18 s7 RECENT sends of the over-32k session are the short-representation case, consistent with the measured ~11 percent correct for RECENT on long-horizon questions (D152 (1)).
