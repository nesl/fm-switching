#!/usr/bin/env python3
"""LMCache, ADAPTED behind our policy interface. Case B.

Original: https://github.com/LMCache/LMCache (Apache-2.0), cloned to ~/baselines_src/lmcache.

LMCache is a KV offload-and-reuse LAYER rather than a scheduler: it stores KV for reusable text
across GPU, host DRAM and disk, and serves a request from the highest tier that has it. As a
POLICY its decision is therefore the storage one: admit a session's KV to the cache, place it in
a tier, and evict by LRU when the tier is full. That is what this baseline decides; request order
is the documented FCFS default.

Translation (cards/lmcache.md): tiers GPU / host (our interface has no disk tier); admission on
every session that asks; LRU eviction, which is LMCache's default policy, and the reason it is a
useful contrast to AttentionStore's scheduler-aware eviction and Pensieve's value-ordered one.

CPU only.
"""
from __future__ import annotations

from typing import Dict, List

from interface import (Action, Observation, Policy, RecallAction, SessionAction, StreamAction)


class LMCacheAdapted(Policy):
    name = "lmcache"
    case = "B"
    experiments = ('B-recall',)
    paper = "LMCache (KV offload and reuse layer); arXiv:2510.09665 for the system paper"
    decides = ("session_action",)
    defaults_used = ("episodic_mode", "cadence_s", "frame_count", "recall_decision",
                     "representation", "order")

    def __init__(self, gpu_slots: int = 4) -> None:
        self.gpu_slots = int(gpu_slots)
        self._last: Dict[str, float] = {}

    def reset(self, seed: int = 0) -> None:
        self._last.clear()

    def decide(self, obs: Observation) -> Action:
        for q in obs.recall:
            self._last[q.session_id] = obs.now_s
        known = sorted(set(obs.cloud.gpu_warm_sessions) | set(obs.cloud.host_warm_sessions)
                       | {q.session_id for q in obs.recall})
        for sid in known:
            self._last.setdefault(sid, -1.0)
        # LRU: keep the most recently used in the GPU tier, offload the rest to host.
        ranked = sorted(known, key=lambda s: -self._last[s])
        warm = set(ranked[:self.gpu_slots])
        return Action(
            streams=[StreamAction(s.stream_id, "cloud") for s in obs.streams],
            recall=[RecallAction(q.query_id, "CLOUD") for q in obs.recall],
            sessions=[SessionAction(s, "KEEP_GPU_WARM" if s in warm else "OFFLOAD_TO_HOST")
                      for s in known])
