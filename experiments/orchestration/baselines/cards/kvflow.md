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

## StudyB-baselines amendment 2 (2026-11-13)

**Item 5: `host_offload_intent = "retain"`.** KVFlow's OFFLOAD_TO_HOST means "this session's
state should survive somewhere cheaper", not "discard it". In StudySIM1c's no-host world the
harness mapped it to EVICT, so no session was ever GPU-warm and all 83 recalls were COLD. The
harness now maps a RETAIN arm's OFFLOAD_TO_HOST to KEEP_GPU_WARM, with the engine's GPU KV
capacity (62,944 tokens) and its LRU eviction still binding, the budget still binding, and
fairness rule 3 still charging a first promotion at the measured cold-prefill cost. In the live
harness, where a host tier exists, the arm uses the real host tier and nothing is mapped.
Measured consequence on the representative cell: challenge mAP 0.5135 -> 0.5169 (ALL).


## D130 live2 port note, added 2026-11-19 (measurement, not a change to this adaptation)

**Behavioural collapse measured in live2.** On seed 4 at 8 devices over 300 s, once the ignored `order` field is excluded, this arm's ACTION SEQUENCE is byte-identical to: `pensieve`. The three arms emit the same streams, recall decisions and session actions at every one of 3,001 decision periods.

**The collapse is REGIME DEPENDENT, not structural.** At 16 devices the same arms DIVERGE (ekya and videostorm give different action sequences and different robot delivery, 18 of 21 against 19 of 21), so this is convergence under a non-binding capacity rather than two names for one mechanism.

**Consequence for any leaderboard.** Rows for these arms at a cell where they collapse are NOT independent witnesses, and counting them separately overstates the evidence. The measured count is in `results/orchestration/live2/baselines_published/arm_independence.json`.

`live2/coordinator.py` NEVER READS the action's `order` field: it contains zero references to it, and the two `.order` matches are `self.st.order`, a different object. Any part of this system's scheduling discipline expressed through `order` therefore CANNOT reach a decision in live2. This is a property of the live2 harness, not of the adaptation, and nothing in the adaptation was altered.
