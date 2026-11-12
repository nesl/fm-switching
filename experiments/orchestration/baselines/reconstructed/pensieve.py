#!/usr/bin/env python3
"""FAITHFUL RECONSTRUCTION of Pensieve's multi-tier KV management (EuroSys 2025).

Paper: L. Yu, J. Lin, J. Li, "Stateful Large Language Model Serving with Pensieve",
EuroSys 2025 (arXiv:2312.05516). No official or author-endorsed code release was found.

Mapping to the paper:
  multi-tier cache     Sections 1 / 4: a GPU-CPU two-tier cache holding conversation history,
                       swapped in and out as capacity requires.
  eviction value       Section 4: eviction is at the granularity of a CHUNK of tokens, and a
                       chunk is kept when it is "attractive for longer and/or ... cheaper to
                       recompute" - so the policy prefers to DROP what is cheap to recompute and
                       keep what is expensive. `chunk_value()` is that ordering.
  token granularity    Section 4: "we decide to swap at the granularity of individual tokens",
                       so a session's history may be PARTIALLY resident and the missing segment
                       is recomputed.
  aot_swap_s()         Section 4: ahead-of-time swapping with pipelined transfer, overlapping
                       transfer with computation. Returns the exposed (non-overlapped) cost.
  serve_cost_s()       The consequence the paper measures: a request's cost is the transfer of
                       the resident part plus the RECOMPUTE of the dropped part.

NOT reconstructed, and why: the attention-kernel changes that let Pensieve attend over a
non-contiguous KV layout (a CUDA-level change); the pipelining implementation; the scheduler
integration with vLLM's block manager.

CPU only; no GPU, no inference.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

GPU, CPU, DROPPED = "GPU", "CPU", "DROPPED"


@dataclass
class Chunk:
    """A chunk of KV tokens of one session."""
    sid: str
    index: int
    tokens: int
    tier: str = GPU
    recompute_tok_s: float = 4500.0     # how fast this chunk can be recomputed if dropped
    reuse_horizon_s: float = 0.0        # how long it stays "attractive" (paper's wording)

    def recompute_s(self) -> float:
        return self.tokens / max(self.recompute_tok_s, 1e-9)


def chunk_value(c: Chunk) -> float:
    """Section 4's keep-ordering: value grows with how long the chunk stays attractive and with
    how EXPENSIVE it is to recompute. Evict the lowest value first."""
    return c.reuse_horizon_s * c.recompute_s()


def evict_to_fit(chunks: Sequence[Chunk], gpu_capacity_tokens: int) -> List[Chunk]:
    """Evict the least valuable chunks until the GPU tier fits. Evicted chunks go to CPU; if the
    CPU tier is not modelled by the caller they are DROPPED and must be recomputed."""
    out = [Chunk(c.sid, c.index, c.tokens, c.tier, c.recompute_tok_s, c.reuse_horizon_s)
           for c in chunks]
    resident = sorted([c for c in out if c.tier == GPU], key=chunk_value)
    total = sum(c.tokens for c in out if c.tier == GPU)
    i = 0
    while total > gpu_capacity_tokens and i < len(resident):
        resident[i].tier = CPU
        total -= resident[i].tokens
        i += 1
    return out


def aot_swap_s(transfer_s: float, compute_overlap_s: float) -> float:
    """Section 4: ahead-of-time, pipelined swapping. Only the unhidden part costs anything."""
    return max(transfer_s - compute_overlap_s, 0.0)


def serve_cost_s(chunks: Sequence[Chunk], cpu_to_gpu_tok_s: float,
                 compute_overlap_s: float = 0.0) -> float:
    """A request's exposed cost: pipelined transfer of the CPU-resident part plus full recompute
    of the dropped part. GPU-resident tokens cost nothing."""
    cpu_tokens = sum(c.tokens for c in chunks if c.tier == CPU)
    transfer = cpu_tokens / max(cpu_to_gpu_tok_s, 1e-9)
    recompute = sum(c.recompute_s() for c in chunks if c.tier == DROPPED)
    return aot_swap_s(transfer, compute_overlap_s) + recompute
