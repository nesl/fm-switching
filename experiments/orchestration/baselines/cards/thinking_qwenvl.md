<!-- StudyB-baselines (addendum). FAITHFUL = unchanged from the original; ADAPTATION = changed, with its reason. Fairness rules 1-6 of the addendum hold for this baseline and are checked by `interface.check_fairness` and the smoke harness. -->
# ATDM / Thinking-QwenVL (arXiv:2604.18459) — case D, P1 (component)

**Paper.** K. Zhang, Z. Yang, M. Han, H. Hao et al., "Progressive Online Video Understanding with
Evidence-Aligned Timing and Transparent Decisions", arXiv:2604.18459 (20 Apr 2026). **The arXiv id
is verified; the ICLR 2026 venue the addendum gives could NOT be verified in an index and is
flagged.**

**Code.** None found. **Case D.**

**Files.** `reconstructed/thinking_qwenvl.py`, `reconstructed/test_thinking_qwenvl_toy.py`,
`thinking_qwenvl_adapted.py`. **Experiment:** A-episodic.

## The paper's algorithm

"A visual agent should answer only once the video first contains sufficient evidence, and it
should show when and why it decided." The **Active Thinking Decision Maker (ATDM)** is "a
transparent reasoning controller that externalizes its decision process using observable
progress (ρ) and confidence ... to pinpoint the sufficient-evidence timestamp t*". A second
module, HPSI, integrates semantics hierarchically.

## Mapping

| paper | our code | note |
|---|---|---|
| the two observable quantities ρ and confidence | `atdm(progress, confidence, ...)` | FAITHFUL |
| answer only when BOTH suffice | the rule's conjunction | FAITHFUL |
| t* | `t_star(...)`, the first epoch at which both clear | FAITHFUL |
| transparency | every `Decision` carries a `reason`, and the adapted policy keeps a `decision_log` | FAITHFUL — this is the paper's point and it is preserved |
| ρ | the fraction of the session's representations that exist at some tier | ADAPTATION A1 |
| confidence | the device answer's confidence, or the device score mapped to [0, 1] | ADAPTATION A2 |
| HPSI | — | NOT REPRODUCED |

## Adaptations, with reasons

- **A1/A2 ρ and confidence are not model outputs here.** The paper gets both from the VLM; we
  substitute observable proxies. **Consequence: this baseline tests the paper's TIMING RULE on our
  signals, not its estimator.**
- **A3 it is a COMPONENT baseline, and says so.** `restricts_action_space` is declared with a
  reason (fairness rule 4): it decides readiness and stopping only, so the timing decision is
  isolated and everything else takes the documented defaults.

## Not reproduced, and why

The model-internal estimation of ρ and confidence; HPSI; the paper's timing metrics and
benchmarks.

## Hyperparameters and provenance

| name | value | from |
|---|---|---|
| `progress_threshold` | 0.6 | our own, stated |
| `confidence_threshold` | 0.6 | our own, stated |
| `defer_s` | 0.5 s | our own, stated |

## StudyB-baselines amendment 2 (2026-11-13)

**Item 4: the evidence inventory now lists the representations that exist.** StudySIM1d section
1.1 found rho = 0.3333 in every query of every cell, because the harness built every inventory
from two `EvidenceItem`s that both carried `D2`. `research/FORMULATION.md` (Section "State
objects: fidelity x materialization") describes a session's state at several fidelities at once,
and this system genuinely holds two of them for a recall: the device's own recent window (RECENT;
`device_always_warm` is a fixed design assumption, and StudyF4 Part A measured the device
answering from exactly that window, median 467 input tokens) and the session's strided history
(D2), stored on the device and ready on the GPU when the session is GPU-warm. RICH - the full
history - is NOT listed, because nothing in this world retains it server-side. The arm's rule is
unchanged: rho is still the count of distinct representations divided by 3, and it is now
**0.667** against the 0.6 threshold, so the progress gate passes and the arm's timing decision is
exercised for the first time.

**Item 3b: `reads_device_answer = True`.** ATDM answers when progress and CONFIDENCE both clear
their thresholds, and the confidence is the running model's own; in our two-tier mapping that
model is the device, so the field is supplied and the device answer is charged.

**Measured consequence** on the representative cell: recall timely accuracy 0.000 -> 0.253, with
54 of 83 queries answered and 29 DEFERRED to the end of the run.

**DEFERRAL UNEXERCISED - read the recall numbers with this.** The harness's per-query device
confidence is STATIC: the committed tables give one value per question, so a deferral can never
gain evidence and a query below the confidence threshold is deferred until the run ends. The
amendment makes the harness honour `defer_s` (so the DEFER count is a property of the arm and not
of the tick rate) and counts a starved query as untimely, but the mechanism ATDM exists to test -
wait, gather more evidence, then answer - is NOT exercised here.
