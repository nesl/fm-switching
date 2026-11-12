<!-- StudyB-baselines. Written for a reviewer: everything faithful to the original is marked FAITHFUL, everything we changed is marked ADAPTATION with its reason. -->
# R3-Streaming — case D

**Paper.** J. Liu, J. Huang, Z. Jia, J. Li, X. Zhang, Z. Guo, B. Li, W. Zeng, Y. Lu, X. Jin,
"An Efficient Streaming Video Understanding Framework with Agentic Control" (**R3-Streaming**:
Remember, Respond, Reason), arXiv:2605.17921 (v1 18 May 2026, v2 1 June 2026).

**Code.** None found. **Case D.**

**Files.** `reconstructed/r3streaming.py`, `reconstructed/test_r3streaming_toy.py`,
`r3streaming_adapted.py`.

## The paper's algorithm (§4, three decisions)

| decision | where | what it says |
|---|---|---|
| **Remember** — Active Forgetting | §4.2 | a **training-free, age-aware** memory compressor that "keeps recent context at high fidelity and compresses old memory aggressively". §3 / Fig. 2 report the asymmetry: "preserving Nearby context is critical, while Historical memory can be compressed more aggressively", with the best setting **Nearby = 1.0, Historical = 0.01** reaching 71.0 on StreamingBench, "+2.4 over no compression". |
| **Respond** — Proactive Response | §4 (ii) | "a readiness head that emits `<Routine>` and defers answering when evidence is insufficient"; implemented in the paper as a lightweight head on the frozen fast model. |
| **Reason** — Adaptive Thinking | §4 (iii) | "routes only hard queries to slow/thinking inference instead of using an always-on large model", trained with **TB-GRPO** so routing stays "within deployable escalation budgets". |

Reported: 57.92 on OVO-Bench, 76.36 on StreamingBench, 95–96 % visual-token reduction.

## Mapping, step by step

| paper | our code | note |
|---|---|---|
| age-aware forgetting | `active_forgetting` (nearby ratio 1.0, historical 0.01, both exposed so Fig. 2's ablation runs) | FAITHFUL |
| readiness / defer | `readiness` + our `DEFER` action | FAITHFUL — our interface has DEFER, so this maps exactly |
| adaptive thinking under a budget | `adaptive_thinking` (escalate the hardest fraction) | FAITHFUL to the deployed behaviour |
| Respond gates Reason | `pipeline`, and the adapted policy's ordering | FAITHFUL |
| compression ratio | quantised to our three committed representations {RECENT, RICH, D2} | ADAPTATION A1 |
| readiness head | device answer confidence, else evidence coverage | ADAPTATION A2 |
| difficulty | the session's history length (tokens), normalised | ADAPTATION A3 |
| TB-GRPO | — | NOT REPRODUCED |

## Adaptations, with reasons

- **A1 the compression ratio is quantised.** The paper compresses visual tokens continuously; we
  can only choose among representations we have actually built and measured (RECENT / RICH / D2),
  so the ratio becomes a three-way choice. **Consequence: the 95–96 % token reduction cannot be
  reproduced as a continuum**, only as whichever committed representation is closest in spirit.
- **A2 the readiness head is not trained.** It is a head on a frozen VLM; training needs a GPU.
  We substitute the device answer's confidence where one exists, and the evidence inventory's
  coverage otherwise.
- **A3 difficulty is history length.** The paper's notion of a "hard query" is learned by
  TB-GRPO. We use a causal proxy. FLAGGED: this is a substitution, not a reproduction.
- **A4 the cascade is independent, as the task asks.** Memory policy, readiness and router are
  three separate decisions here, which is the paper's own decomposition.

## Not reproduced, and why

TB-GRPO (a reinforcement-learning TRAINING objective needing GPUs and the model); the readiness
head's weights; the visual-token compressor's internals; the benchmark numbers.

## Hyperparameters and provenance

| name | value | from |
|---|---|---|
| nearby / historical ratio | 1.0 / 0.01 | the paper's best setting, §3 / Fig. 2 |
| `nearby_window_s` | 10 s | our own; the paper's "Nearby" window is benchmark-specific |
| `readiness_threshold` | 0.5 | our own, stated not fitted |
| `escalation_budget` | 0.25 | our own; the paper's budget is set by TB-GRPO's target |
