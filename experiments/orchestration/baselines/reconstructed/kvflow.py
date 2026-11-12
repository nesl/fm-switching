#!/usr/bin/env python3
"""FAITHFUL RECONSTRUCTION of KVFlow's reuse-aware KV management (arXiv:2507.07400).

Paper: Z. Pan, A. Patel, Z. Hu, Y. Shen et al., "KVFlow: Efficient Prefix Caching for
Accelerating LLM-Based Multi-Agent Workflows", arXiv:2507.07400 (10 Jul 2025; the task cites
NeurIPS 2025, which could not be verified in an index - the arXiv id IS verified). No official or
author-endorsed code release was found.

Mapping to the paper:
  The problem: systems "typically evict KV caches using a Least Recently Used (LRU) policy, which
  fails to [capture] reuse", so an agent whose cache has not been touched recently is evicted
  "since it has not been accessed recently", causing a miss when it next runs.
  The fix: a **steps-to-execution** value per agent, taken from the workflow graph, driving a
  "fine-grained eviction policy at the KV node level ... [preserving] entries likely to be
  reused", plus "a fully overlapped KV prefetching mechanism".

  steps_to_execution()  the paper's priority signal: how many workflow steps until this node runs
                        again. Smaller = evict later.
  evict()               evict the node with the LARGEST steps-to-execution (furthest from reuse),
                        at KV-node granularity, which is the paper's named departure from LRU.
  prefetch()            fetch the nodes about to execute, overlapped with computation, so the
                        exposed cost is only what the overlap cannot hide.

**THE SIGNAL IS NOT CAUSALLY AVAILABLE TO US.** KVFlow reads steps-to-execution from a KNOWN
workflow graph. Our scheduler has no such graph: when a client session will next ask is exactly
what it may not know. The adapted version therefore ESTIMATES the same quantity from observed
history, and the card states that this is a principle adaptation, not a reproduction.

NOT reconstructed, and why: the workflow-graph extraction; the tree-structured shared-prefix
cache (our sessions do not share prefixes); the CUDA-level prefetch overlap.

CPU only; no GPU, no inference.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence


@dataclass
class KVNode:
    """One KV node: in the paper an agent's fixed prompt, for us a session's history."""
    node_id: str
    tokens: int
    resident: bool = True
    steps_to_execution: float = float("inf")   # the paper's priority signal


def steps_to_execution(order: Sequence[str], now_index: int, node_id: str) -> float:
    """How many steps until `node_id` runs again, given the workflow's execution order."""
    for k in range(now_index, len(order)):
        if order[k] == node_id:
            return float(k - now_index)
    return float("inf")


def evict(nodes: Sequence[KVNode], capacity_tokens: int) -> List[KVNode]:
    """Evict the nodes FURTHEST from their next execution until the tier fits.

    This is the paper's point: LRU would evict by recency and lose a node that is about to run.
    """
    out = [KVNode(n.node_id, n.tokens, n.resident, n.steps_to_execution) for n in nodes]
    resident = [n for n in out if n.resident]
    total = sum(n.tokens for n in resident)
    # largest steps-to-execution first; ties by larger footprint, which frees more per eviction
    victims = sorted(resident, key=lambda n: (-n.steps_to_execution, -n.tokens))
    i = 0
    while total > capacity_tokens and i < len(victims):
        victims[i].resident = False
        total -= victims[i].tokens
        i += 1
    return out


def prefetch(nodes: Sequence[KVNode], horizon_steps: float, slots: int) -> List[str]:
    """Nodes due to execute within `horizon_steps` and not resident, nearest first."""
    cand = [n for n in nodes if not n.resident and n.steps_to_execution <= horizon_steps]
    cand.sort(key=lambda n: n.steps_to_execution)
    return [n.node_id for n in cand[:max(slots, 0)]]


def exposed_prefetch_s(transfer_s: float, compute_overlap_s: float) -> float:
    """"Fully overlapped" prefetching: only the part the overlap cannot hide is exposed."""
    return max(transfer_s - compute_overlap_s, 0.0)
