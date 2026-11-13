<!-- StudyB-baselines. Written for a reviewer: everything faithful to the original is marked FAITHFUL, everything we changed is marked ADAPTATION with its reason. -->
# AttentionStore / CachedAttention (USENIX ATC 2024) — case D

**Paper.** B. Gao, Z. He, P. Sharma, Q. Kang, D. Jevdjic, J. Deng, X. Yang, Z. Yu, P. Zuo,
"Cost-Efficient Large Language Model Serving for Multi-turn Conversations with CachedAttention",
*USENIX ATC 2024* (arXiv:2403.19708).

**Code.** None found. **Case D.**

**Files.** `reconstructed/attentionstore.py`, `reconstructed/test_attentionstore_toy.py`,
`attentionstore_adapted.py`.

## The paper's algorithm

| element | where | what it says |
|---|---|---|
| hierarchy | §1, §3 | HBM → host DRAM → disks: "cost-effective memory/storage mediums to save KV caches for all requests". |
| layer-wise pre-loading | §4.1, Figs. 6–7 | load layer `i+1`'s KV while layer `i` computes; with "a customized larger buffer" the overlap becomes perfect. |
| asynchronous saving | §4.1 | layer-wise write-back, so archiving does not block. |
| scheduler-aware fetching | §4.2 | fetch for the sessions the **job scheduler** will run next, not on demand at request time. |
| scheduler-aware eviction | §4.2 | evict by the **predicted next access** implied by the scheduler's queue — the paper's named departure from LRU. |
| decoupled positional encoding | §4.3 | decouple the positional encoding from the saved KV so a cache stays valid when the prefix shifts, and truncate. |

## Mapping, step by step

| paper | our code | note |
|---|---|---|
| overlap arithmetic, Figs. 6–7 | `layer_wise_preload_s` (head load always exposed; a `k`-layer buffer absorbs `(k−1)·per_compute` of the deficit) | FAITHFUL to the figures |
| async saving | `async_save_exposed_s` | FAITHFUL |
| §4.2 fetch | `scheduler_aware_fetch` | FAITHFUL |
| §4.2 eviction | `scheduler_aware_evict` (queue position first, LRU as the tie-break the paper falls back to) | FAITHFUL |
| §4.3 validity | `decoupled_positional_valid` (a predicate, not an embedding) | ADAPTATION A2 |
| "the scheduler's queue" | our recall queue in deadline order | ADAPTATION A3 |
| three tiers | GPU / host only | ADAPTATION A1 |
| layer granularity | whole session | ADAPTATION A1 |

## Adaptations, with reasons

- **A1 our interface is whole-session and two-tier.** The paper manages KV **layer-wise** across
  **three** tiers. Our `session_action` is `{KEEP_GPU_WARM, OFFLOAD_TO_HOST, EVICT}` for a whole
  session, and there is no disk tier. So the layer-wise pre-loading and the disk tier are
  **reconstructed and toy-tested but not used by the policy**; what the policy uses is
  scheduler-aware fetching and eviction, which is what the paper fundamentally decides.
  **This is the main limitation of this card.**
- **A2 positional decoupling becomes a validity predicate.** Re-embedding positions is a
  model-internal GPU operation. The reconstruction keeps the *consequence* — a decoupled cache
  survives a prefix shift — as a predicate.
- **A3 the queue is the deadline order.** Our serving scheduler runs recall in deadline order, so
  that order is the "scheduler's queue" §4.2 reads.

## Not reproduced, and why

Positional re-embedding and truncation inside the model; the disk tier's device characteristics;
the overlapping of vision/embedding stages; the paper's throughput and TTFT measurements.

## Hyperparameters and provenance

| name | value | from |
|---|---|---|
| `gpu_warm_slots` | 4 | StudyE10b's capacity table shows k = 4 warm sessions halving episodic capacity, so 4 is the measured operating point, not a guess |
| buffer layers | exposed, default 1 | the paper varies it (Figs. 6–7) without printing a value |

## AMENDMENT 2026-11-12: wired to MATERIALIZE

The interface gained `MATERIALIZE(session, target_tokens, slice_tokens)`, which is the explicit act
of BUILDING a session's cloud-side state, as against `KEEP_GPU_WARM`, which only holds state that
already exists. AttentionStore's scheduler-aware **fetch** promotes a session from the DRAM tier into HBM, which is a build, so the adapted policy now emits `MATERIALIZE` for a promotion of a session that is not already GPU-warm.

`slice_tokens = None` (one monolithic prefill) — the paper loads a whole prefix in one fetch, so the monolithic form is the
faithful one. Whether SLICING helps is the property under test (fairness rule 4) and is tested by
B11, not here.

**What changed, and what did not.** What changed is what this baseline DECLARES. What did not
change is what it is charged: the harness already billed the first promotion of a session to
GPU-warm at the measured cold-prefill cost (fairness rule 3), and it bills `MATERIALIZE` on the
same path. The re-run smoke record is identical field for field apart from the new
`materialize_*` counters.
