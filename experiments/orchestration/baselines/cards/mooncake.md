<!-- StudyB-baselines (addendum). FAITHFUL = unchanged from the original; ADAPTATION = changed, with its reason. Fairness rules 1-6 of the addendum hold for this baseline and are checked by `interface.check_fairness` and the smoke harness. -->
# Mooncake — case B, P0/P1

**Paper.** R. Qin et al., "Mooncake: A KVCache-centric Disaggregated Architecture for LLM
Serving", **ACM Transactions on Storage 2025** (FAST '25), arXiv:2407.00079. **Verified
(OpenAlex: ACM TOS 2025).**

**Code.** `https://github.com/kvcache-ai/Mooncake`, Apache-2.0. Cloned to
`~/baselines_src/mooncake`, pinned `5ffbf763368d`.

**Files.** `mooncake_adapted.py`. **Experiment:** C-mixed.

## The paper's algorithm

"Unlike traditional studies that assume all requests will be processed, Mooncake faces challenges
due to highly overloaded scenarios. To mitigate these, we developed a **prediction-based early
rejection policy**." Its SLOs are latency-related, "mainly the time to first token (TTFT) and the
time between tokens (TBT)", and its architecture maximises KVCache reuse across a disaggregated
prefill/decode pool.

## Mapping

| Mooncake | our code | note |
|---|---|---|
| prediction-based early rejection | `REJECT` when the predicted TTFT exceeds the slack **and** the replica is overloaded | FAITHFUL |
| TTFT SLO | the recall query's deadline, predicted via `costs.recall_ttft_s` | FAITHFUL |
| maximise KVCache reuse | serve GPU-warm, then host-warm, then cold (`MOONCAKE-REUSE-FIRST` order) | FAITHFUL in effect |
| TBT SLO | — | ADAPTATION A2 |
| disaggregated prefill/decode pools | one replica | ADAPTATION A1, `multi_instance_adapted = True` |

## Adaptations, with reasons

- **A1 one replica.** The disaggregation is the paper's architecture, not its policy; the policy
  — early rejection under overload with reuse-first ordering — transfers intact.
- **A2 no TBT SLO.** Our requests are prefill-dominated: StudyE10d showed the ~12.6k-token LM
  prefill is the unsplittable unit that holds episodic scoring, and our recall answers are short.
  A time-between-tokens SLO would have nothing to bind on, so only TTFT is enforced. **Stated
  rather than silently dropped.**
- **A3 rejection is gated on overload.** The paper rejects when overloaded; when not overloaded
  this baseline falls back to the device instead of rejecting, which is strictly kinder to the
  workload and is the primary setting.

## Not reproduced, and why

The disaggregated architecture; the transfer engine and its storage tiers; the TBT SLO; the
paper's throughput results.

## Hyperparameters and provenance

| name | value | from |
|---|---|---|
| `overload_queue` | 4 | our own overload trigger, stated |
| `gpu_warm_slots` | 4 | StudyE10b |
| TTFT predictions | StudyRH5 curves | committed measurement |
