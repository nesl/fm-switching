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
