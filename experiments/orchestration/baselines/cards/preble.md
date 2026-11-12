<!-- StudyB-baselines (addendum). FAITHFUL = unchanged from the original; ADAPTATION = changed, with its reason. Fairness rules 1-6 of the addendum hold for this baseline and are checked by `interface.check_fairness` and the smoke harness. -->
# Preble (arXiv:2407.00023) — case B, P0

**Paper.** V. Srivatsa, Z. He, R. Abhyankar, D. Li et al., "Preble: Efficient Distributed Prompt
Scheduling for LLM Serving", arXiv:2407.00023. **Verified (OpenAlex + arXiv API).**

**Code.** `https://github.com/WukLab/preble` — the authors' own lab, linked from the paper.
Apache-2.0. Cloned to `~/baselines_src/preble`, pinned `1a35eae20c41`.

**Files.** `preble_adapted.py`. **Experiment:** C-mixed.

## LABELLED AS A POLICY ADAPTATION, NOT A REPRODUCTION

Preble is a **distributed** scheduler. Its problem statement is explicitly multi-GPU: sending all
shared-prefix requests to one GPU "would result in imbalanced loads and low overall GPU
utilization", while balancing load alone "result[s] in requests with shared prefixes being sent
to different GPUs, causing KV computation at all these GPUs that could otherwise be avoided".
With **one** replica there is nothing to balance across. What survives is the **principle** —
trade cache affinity against load pressure — and that is what this baseline implements.
`multi_instance_adapted = True` records it under fairness rule 2.

## Mapping

| Preble | our code | note |
|---|---|---|
| KV-state reuse term | `AFFINITY` = 1.0 GPU-warm / 0.5 host-warm / 0.0 cold (StudyRH5's readiness states) | ADAPTATION A1 |
| load-balancing term | `_load_pressure` from queue depth and GPU KV occupancy | ADAPTATION A2 |
| co-optimised score | `affinity − load_weight × load_pressure`, used to order the queue | FAITHFUL in form |
| hierarchical global/local scheduling | collapsed to one level | ADAPTATION A3 |
| cross-GPU placement | — | NOT REPRODUCED (one replica) |

## Adaptations, with reasons

- **A1 affinity is readiness, not prefix overlap.** Our sessions do not share prompt prefixes;
  what they share is their own KV across turns, and StudyRH5 measured exactly what that is worth
  (0.382 s GPU-warm vs 2.445 s cold at 11k tokens). Affinity is therefore the readiness state.
- **A2 load pressure is local.** One replica, so pressure is its own queue and KV occupancy.
- **A3 one scheduling level.** The global/local split exists to coordinate replicas.
- **A4 under load, cold work is shed to the device** rather than queued — the admission half of
  Preble's trade, expressed in our action space.

## Not reproduced, and why

Everything multi-GPU: placement, migration, the global scheduler, the load-balancing objective
across replicas. Also its prefix-tree matching, since our sessions do not share prefixes.

## Hyperparameters and provenance

| name | value | from |
|---|---|---|
| `load_weight` | 1.0 | our own; the paper tunes the trade per cluster |
| `max_load_pressure` | 0.9 | our own admission threshold, stated |
| `gpu_warm_slots` | 4 | StudyE10b's measured warm-session operating point |
