#!/usr/bin/env python3
"""FAITHFUL RECONSTRUCTION of CachedAttention / AttentionStore's KV cache management
(USENIX ATC 2024).

Paper: B. Gao, Z. He, P. Sharma, Q. Kang, D. Jevdjic, J. Deng, X. Yang, Z. Yu, P. Zuo,
"Cost-Efficient Large Language Model Serving for Multi-turn Conversations with CachedAttention",
USENIX ATC 2024 (arXiv:2403.19708). No official or author-endorsed code release was found.

Mapping to the paper:
  Hierarchy            Section 1 / Section 3: HBM -> host DRAM -> disks, "cost-effective
                       memory/storage mediums to save KV caches for all requests".
  layer_wise_preload() Section 4.1 / Figures 6-7: the KV cache of layer i+1 is loaded while layer
                       i computes, so the load is hidden; with a buffer large enough the overlap
                       is "perfect". Reconstructed as the overlap arithmetic: the exposed cost is
                       max(0, load_per_layer - compute_per_layer) summed over layers, plus the
                       first layer's load, which cannot be hidden.
  async_save()         Section 4.1: asynchronous (layer-wise) saving / write-back, so a session
                       being archived does not block the next request.
  scheduler_aware_fetch()   Section 4.2: the fetch is driven by the JOB SCHEDULER's queue - the
                       cache of a session about to be scheduled is fetched first, instead of
                       fetching on demand at request time.
  scheduler_aware_evict()   Section 4.2: eviction by the PREDICTED NEXT ACCESS implied by the
                       scheduler's queue order, rather than by recency. A session that the
                       scheduler will not reach for a long time is evicted first; this is the
                       paper's named departure from LRU.
  decouple_positional()     Section 4.3: the positional encoding is decoupled from the saved KV
                       so a cache stays valid when the prefix shifts, and the cache may be
                       truncated; reconstructed as a validity predicate, not as an embedding.

NOT reconstructed, and why: the actual re-embedding of positional encodings (a model-internal
operation needing a GPU and weights); the disk tier's device characteristics; the paper's
overlapping of the vision/embedding stages. The sub-session (LAYER) granularity is reconstructed
here but is NOT expressible in our policy interface, whose session actions are whole-session -
recorded as adaptation A1 in the card.

CPU only; no GPU, no inference.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

HBM, DRAM, DISK = "HBM", "DRAM", "DISK"
TIERS = (HBM, DRAM, DISK)


@dataclass
class Session:
    sid: str
    tokens: int
    tier: str = DISK
    last_access_s: float = 0.0


def layer_wise_preload_s(n_layers: int, load_total_s: float, compute_total_s: float,
                         buffer_layers: int = 1) -> float:
    """Section 4.1 / Figures 6-7. Returns the EXPOSED (non-overlapped) load time.

    Per layer the loader has `compute_total_s / n_layers` of cover; with a buffer of k layers the
    loader may run k layers ahead, so the first k loads are exposed and the rest are hidden to the
    extent the per-layer compute covers them.
    """
    if n_layers <= 0:
        return load_total_s
    per_load = load_total_s / n_layers
    per_compute = compute_total_s / n_layers
    k = max(int(buffer_layers), 1)
    # The FIRST layer's load has nothing to overlap with, so it is always exposed (Figure 6b/6c).
    # After that the loader runs ahead; a buffer of k layers gives it (k - 1) layers of extra
    # lead, so it can absorb that much of any steady-state deficit (Figure 7a vs 7b).
    rest = max(n_layers - 1, 0)
    deficit = rest * max(per_load - per_compute, 0.0)
    absorbed = (k - 1) * per_compute
    return per_load + max(deficit - absorbed, 0.0)


def async_save_exposed_s(save_total_s: float, overlap_s: float) -> float:
    """Section 4.1: asynchronous saving. Only the part that cannot overlap is exposed."""
    return max(save_total_s - overlap_s, 0.0)


def scheduler_aware_fetch(queue: Sequence[str], sessions: Dict[str, Session],
                          hbm_slots: int) -> List[str]:
    """Section 4.2: fetch for the sessions the SCHEDULER will run next, in queue order, not on
    demand. Returns the session ids to promote into HBM."""
    out: List[str] = []
    for sid in queue:
        if len(out) >= hbm_slots:
            break
        s = sessions.get(sid)
        if s is not None and s.tier != HBM:
            out.append(sid)
    return out


def scheduler_aware_evict(queue: Sequence[str], sessions: Dict[str, Session],
                          n_evict: int) -> List[str]:
    """Section 4.2: evict by PREDICTED NEXT ACCESS from the scheduler's queue, not by recency.

    A session absent from the queue has an infinite predicted next access and is evicted first;
    ties break on least-recently-used, which is the paper's fallback when the scheduler has no
    opinion.
    """
    pos = {sid: i for i, sid in enumerate(queue)}
    resident = [s for s in sessions.values() if s.tier == HBM]
    resident.sort(key=lambda s: (-pos.get(s.sid, 10 ** 9), s.last_access_s))
    return [s.sid for s in resident[:max(n_evict, 0)]]


def decoupled_positional_valid(saved_prefix_tokens: int, current_prefix_tokens: int,
                               decoupled: bool) -> bool:
    """Section 4.3. With the positional encoding embedded in the KV (the baseline), a saved cache
    is valid only if the prefix is unchanged. Decoupled, it stays valid and may be truncated."""
    if decoupled:
        return saved_prefix_tokens > 0
    return saved_prefix_tokens == current_prefix_tokens
