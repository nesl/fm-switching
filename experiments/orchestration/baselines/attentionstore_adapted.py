#!/usr/bin/env python3
"""AttentionStore / CachedAttention (USENIX ATC 2024), ADAPTED. Case D.

Decision logic = `reconstructed/attentionstore.py` (Sections 4.1-4.3), unchanged. Mapping and
every adaptation in cards/attentionstore.md. The one that matters: the paper manages KV
LAYER-WISE and across three tiers (HBM / DRAM / disk); our interface's session actions are
WHOLE-SESSION and two-tier (GPU / host / evict), so the layer-wise pre-loading and the disk tier
are NOT expressible and are not used here - the scheduler-aware FETCH and EVICTION, which are
what the paper fundamentally decides, are.

CPU only.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent / "reconstructed"))

import costs as C
from attentionstore import (DRAM, HBM, Session, scheduler_aware_evict,  # noqa: E402
                            scheduler_aware_fetch)
from interface import (Action, Observation, Policy, RecallAction, SessionAction,
                       StreamAction, materialize)


class AttentionStoreAdapted(Policy):
    name = "attentionstore"
    case = "D"
    experiments = ('B-recall',)
    paper = ("Gao et al., Cost-Efficient LLM Serving for Multi-turn Conversations with "
             "CachedAttention, USENIX ATC 2024 (arXiv:2403.19708)")
    decides = ("session_action", "recall_decision", "order")
    defaults_used = ("episodic_mode", "cadence_s", "frame_count", "representation")

    def __init__(self, gpu_warm_slots: int = 4) -> None:
        self.gpu_warm_slots = int(gpu_warm_slots)

    def decide(self, obs: Observation) -> Action:
        # The "scheduler's queue" in our setting is the recall queue in deadline order: that is
        # what the serving scheduler will run next (Section 4.2).
        queue = [q.session_id for q in sorted(obs.recall, key=lambda x: x.deadline_s)]
        sess: Dict[str, Session] = {}
        for sid in obs.cloud.gpu_warm_sessions:
            sess[sid] = Session(sid, 0, HBM, last_access_s=0.0)
        for sid in obs.cloud.host_warm_sessions:
            sess.setdefault(sid, Session(sid, 0, DRAM, last_access_s=0.0))
        for q in obs.recall:
            sess.setdefault(q.session_id, Session(q.session_id, q.readiness_tokens, DRAM,
                                                  last_access_s=obs.now_s))
            sess[q.session_id].tokens = max(sess[q.session_id].tokens, q.readiness_tokens)

        promote = scheduler_aware_fetch(queue, sess, self.gpu_warm_slots)
        over = max(len([s for s in sess.values() if s.tier == HBM]) + len(promote)
                   - self.gpu_warm_slots, 0)
        demote = scheduler_aware_evict(queue, sess, over)
        acts: List[SessionAction] = []
        for sid in promote:
            # AttentionStore's scheduler-aware FETCH is a build, not a hold: amendment 2026-11-12
            # wires it to MATERIALIZE with slice_tokens = None (the paper loads a whole prefix).
            acts.append(materialize(sid, max(sess[sid].tokens, 1), slice_tokens=None)
                        if sid not in obs.cloud.gpu_warm_sessions
                        else SessionAction(sid, "KEEP_GPU_WARM"))
        for sid in demote:
            if sid not in promote:
                acts.append(SessionAction(sid, "OFFLOAD_TO_HOST"))
        seen = {a.session_id for a in acts}
        for sid, s in sess.items():
            if sid not in seen and s.tier == HBM:
                acts.append(SessionAction(sid, "KEEP_GPU_WARM"))
        return Action(
            streams=[StreamAction(s.stream_id, "cloud") for s in obs.streams],
            recall=[RecallAction(q.query_id, "CLOUD")
                    for q in sorted(obs.recall, key=lambda x: x.deadline_s)],
            sessions=acts, order="FCFS")
