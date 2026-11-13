<!-- StudyB-baselines (addendum). FAITHFUL = unchanged from the original; ADAPTATION = changed, with its reason. Fairness rules 1-6 of the addendum hold for this baseline and are checked by `interface.check_fairness` and the smoke harness. -->
# KVFlow (arXiv:2507.07400) — case D, P1

**Paper.** Z. Pan, A. Patel, Z. Hu, Y. Shen et al., "KVFlow: Efficient Prefix Caching for
Accelerating LLM-Based Multi-Agent Workflows", arXiv:2507.07400 (10 Jul 2025). **The arXiv id is
verified; the NeurIPS 2025 venue the addendum gives could NOT be verified in an index and is
flagged.**

**Code.** None found (the GitHub links in the PDF are dependencies: langgraph, TensorRT-LLM).
**Case D.**

**Files.** `reconstructed/kvflow.py`, `reconstructed/test_kvflow_toy.py`, `kvflow_adapted.py`.
**Experiment:** B-recall.

## The paper's algorithm

The problem: systems "typically evict KV caches using a Least Recently Used (LRU) policy, which
fails to [capture] reuse", so an agent is chosen as "the eviction candidate since it has not been
accessed recently", producing "a cache miss" when it next runs. The fix: a **steps-to-execution**
value per node taken from the **workflow graph**, driving "a fine-grained eviction policy at the
KV node level, allowing KVFlow to preserve entries likely to be reused", plus "a fully overlapped
KV prefetching mechanism".

## THE PAPER'S CORE SIGNAL IS NOT CAUSALLY AVAILABLE TO US

KVFlow reads steps-to-execution off a **known** workflow graph. Our scheduler has no graph: *when
a client session will next ask* is precisely what it may not know, and fairness rule 5 forbids
reading it. The addendum anticipates this — "adapt its reuse-priority principle to client sessions
using only causal signals (no future workflow knowledge)" — and that is what the adapted policy
does: it **estimates** the same quantity from each session's own observed inter-arrival history
(an exponentially-weighted mean gap, turned into expected seconds until the next arrival) and
feeds the estimate into the paper's eviction and prefetch rules unchanged.

**This is a principle adaptation, not a reproduction.** KVFlow's advantage over LRU comes from
exact future knowledge; a causal estimate is strictly weaker, and any result must say so.

## Mapping

| paper | our code | note |
|---|---|---|
| steps-to-execution from the workflow | `_steps_to_execution` from observed inter-arrival gaps | **ADAPTATION A1 — the core signal** |
| evict the node furthest from reuse | `kvflow.evict` | FAITHFUL |
| KV-node granularity | one node per session | ADAPTATION A2 |
| fully overlapped prefetch | `prefetch` + `exposed_prefetch_s` | FAITHFUL in arithmetic |
| tree-structured shared prefixes | — | NOT REPRODUCED (our sessions share no prefix) |

## Not reproduced, and why

The workflow-graph extraction; the shared-prefix tree; the CUDA-level prefetch overlap; the
paper's agentic benchmarks.

## Hyperparameters and provenance

| name | value | from |
|---|---|---|
| `gpu_capacity_tokens` | 60,000 | StudyRH5's measured GPU KV capacity (62,944 at bf16), rounded down |
| `prefetch_horizon_s` | 5 s | our own, stated |
| `alpha` (EWMA) | 0.3 | our own, stated |

## AMENDMENT 2026-11-12: wired to MATERIALIZE

The interface gained `MATERIALIZE(session, target_tokens, slice_tokens)`, which is the explicit act
of BUILDING a session's cloud-side state, as against `KEEP_GPU_WARM`, which only holds state that
already exists. KVFlow's **prefetch** pulls a KV node in ahead of its predicted next execution, which is a build, so the adapted policy now emits `MATERIALIZE` for a node it keeps that is not yet GPU-resident and `KEEP_GPU_WARM` for one that is.

`slice_tokens = None` (one monolithic prefill) — the paper prefetches a whole prefix, not a part of one, so the monolithic form is the
faithful one. Whether SLICING helps is the property under test (fairness rule 4) and is tested by
B11, not here.

**What changed, and what did not.** What changed is what this baseline DECLARES. What did not
change is what it is charged: the harness already billed the first promotion of a session to
GPU-warm at the measured cold-prefill cost (fairness rule 3), and it bills `MATERIALIZE` on the
same path. The re-run smoke record is identical field for field apart from the new
`materialize_*` counters.
