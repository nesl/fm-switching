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


## D130 live2 port note, added 2026-11-19 (measurement, not a change to this adaptation)

**`mooncake` and `b7-edf-feasibility` are GENUINELY DISTINCT in live2, and converge in OUTCOME.** Their action sequences differ at 8 devices and again at 16 devices, so they are not one mechanism under two names. They nonetheless produce identical outcomes across the leaderboard cells.

The convergence is explained: their only behavioural differences are the `order` field (`MOONCAKE-REUSE-FIRST` against `EDF`) and session actions (mooncake emits KEEP_GPU_WARM, b7 emits none). The first cannot reach a decision at all, and the second did not change an outcome in these cells. A measured convergence of two distinct schedulers is a result about the regime, and it is recorded here rather than being read as duplication.

`live2/coordinator.py` NEVER READS the action's `order` field: it contains zero references to it, and the two `.order` matches are `self.st.order`, a different object. Any part of this system's scheduling discipline expressed through `order` therefore CANNOT reach a decision in live2. This is a property of the live2 harness, not of the adaptation, and nothing in the adaptation was altered.

## GPU-warm slots sized to the KV pool (user ruling 2026-11-23, hit 14)

The published design sizes itself to the KV memory it has. `gpu_warm_slots = 4` above (StudyE10b) is
the **1x** value; in live2 the slots now scale in proportion to the GPU-KV pool the harness gives the
arm: `slots = max(1, round(4 x gpu_kv_tokens / 62,944))`, so **4 at 1x (unchanged), 2 at 0.5x, 1 at
0.25x**. The real engine pools at 0.5x / 0.25x (31,488 / 15,760 tokens) round to the same counts. Only
`live2_configure` reads the capacity (`live2/arms_published.py::MooncakeArm`); `decide` is untouched,
and `live2_describe` reports the read as `capacity_read`.

Proof (`results/orchestration/live2/mooncake_slots/mooncake_slots_proof.json`, one sha, two trees, one
dry cell at a time): mooncake 1x IDENTICAL (7544b3aa16433c70), mooncake 0.25x MOVES (7544b3aa ->
c89aefd5, the unpatched arm being capacity-blind), every other paper arm identical at 1x and 0.25x,
positive control covex-v6-base af8befb9420ad86a reproduced.

**Reading the 1x row: IDENTICAL BY CONSTRUCTION, a positive control, not a null.** At 1x the rule
evaluates to round(4 x 62,944 / 62,944) = 4, exactly the hardcoded StudyE10b value, so the fix MUST be a
no-op there; 7544b3aa16433c70 reproducing at 1x shows the rule reduces correctly at the full pool, i.e.
nothing was changed that was not meant to change. The rule AGREES with the old constant where that
constant was right (1x) and departs from it where it was wrong (0.5x: 2, 0.25x: 1). This is the benign
version of "identical in one condition", unlike a mechanism that is unreachable.
