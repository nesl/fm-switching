#!/usr/bin/env python3
"""Preble (arXiv:2407.00023), ADAPTED behind our policy interface. Case B. P0.

Original: https://github.com/WukLab/preble (Apache-2.0, the authors' lab), cloned to
~/baselines_src/preble, pinned at `1a35eae20c41`.

**LABELLED AS A POLICY ADAPTATION, NOT A REPRODUCTION OF THE SYSTEM.** Preble is a DISTRIBUTED
scheduler: it "co-optimizes KV state reuse and computation load-balancing" ACROSS GPUs, because
"a naive solution that always sends requests with shared prefixes to the same GPU would result in
imbalanced loads", while load-balancing alone sends shared prefixes to different GPUs and wastes
the cache. With ONE replica there is nothing to balance across, so what survives is the
PRINCIPLE: trade cache affinity against load, and admit/order accordingly.
`multi_instance_adapted = True` records this under fairness rule 2.

Adapted decision: a score per pending recall query,
    affinity  = 1 if its session's KV is already GPU-warm, 0.5 if host-warm, 0 if cold
    load      = the current queue depth and GPU KV occupancy
    score     = affinity - load_weight * load_pressure
and the queue is ordered by that score, with admission refused while load pressure exceeds a
threshold - Preble's hierarchical global/local split collapsed to one level.

CPU only.
"""
from __future__ import annotations

from typing import List

import costs as C
from interface import (Action, Observation, Policy, RecallAction, SessionAction, StreamAction)

AFFINITY = {"GPU-WARM": 1.0, "HOST-WARM": 0.5, "COLD": 0.0}


class PrebleAdapted(Policy):
    name = "preble"
    case = "B"
    experiments = ("C-mixed",)
    paper = "Srivatsa, He, Abhyankar, Li et al., Preble: Efficient Distributed Prompt Scheduling for LLM Serving, arXiv:2407.00023"
    decides = ("recall_decision", "order", "session_action")
    defaults_used = ("episodic_mode", "cadence_s", "frame_count", "representation",
                     "engine_config")
    multi_instance_adapted = True
    restricts_action_space = None

    def __init__(self, load_weight: float = 1.0, max_load_pressure: float = 0.9,
                 gpu_warm_slots: int = 4) -> None:
        self.load_weight = float(load_weight)
        self.max_load_pressure = float(max_load_pressure)
        self.gpu_warm_slots = int(gpu_warm_slots)

    @staticmethod
    def _load_pressure(obs: Observation) -> float:
        q = sum(obs.cloud.queued_by_class.values()) + sum(obs.cloud.running_by_class.values())
        return max(obs.cloud.gpu_kv_fraction, min(q / 8.0, 1.0))

    def decide(self, obs: Observation) -> Action:
        lp = self._load_pressure(obs)
        scored = []
        for q in obs.recall:
            aff = AFFINITY.get(q.readiness, 0.0)
            scored.append((aff - self.load_weight * lp, q))
        scored.sort(key=lambda t: -t[0])
        rec: List[RecallAction] = []
        for score, q in scored:
            # cache-affinity-aware admission: under load, serve the cache-resident work and shed
            # the cold work to the device rather than paying a full prefill while overloaded.
            if lp > self.max_load_pressure and AFFINITY.get(q.readiness, 0.0) <= 0.0:
                rec.append(RecallAction(q.query_id, "DEVICE"))
            else:
                rec.append(RecallAction(q.query_id, "CLOUD"))
        # keep the cache hot for the sessions the affinity term favours
        warm = [q.session_id for _s, q in scored[:self.gpu_warm_slots]]
        known = sorted(set(obs.cloud.gpu_warm_sessions) | set(obs.cloud.host_warm_sessions)
                       | {q.session_id for q in obs.recall})
        sess = [SessionAction(s, "KEEP_GPU_WARM" if s in warm else "OFFLOAD_TO_HOST")
                for s in known]
        return Action(streams=[StreamAction(s.stream_id, "cloud") for s in obs.streams],
                      recall=rec, sessions=sess, order="PREBLE-AFFINITY-LOAD")
