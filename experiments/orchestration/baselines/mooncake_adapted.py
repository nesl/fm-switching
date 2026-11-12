#!/usr/bin/env python3
"""Mooncake, ADAPTED behind our policy interface. Case B. P0/P1.

Paper: "Mooncake: A KVCache-centric Disaggregated Architecture for LLM Serving"
(ACM Transactions on Storage 2025; FAST '25), arXiv:2407.00079.
Original: https://github.com/kvcache-ai/Mooncake (Apache-2.0), cloned to ~/baselines_src/mooncake,
pinned at `5ffbf763368d`.

What it fundamentally decides, and what we keep: **prediction-based early rejection** under
overload. "Unlike traditional studies that assume all requests will be processed, Mooncake faces
challenges due to highly overloaded scenarios. To mitigate these, we developed a
prediction-based early rejection policy", with SLOs on TTFT and TBT and the aim of maximising
KVCache reuse.

Adapted (cards/mooncake.md): the disaggregated prefill/decode pools collapse to our single
replica (`multi_instance_adapted = True`, fairness rule 2); the TBT SLO has no analogue because
our episodic and recall requests are prefill-dominated (StudyE10d: the LM prefill is the
unsplittable unit), so only the TTFT SLO is enforced; KV reuse is the readiness state from
StudyRH5, and the policy prefers reuse-resident work and EARLY-REJECTS what it predicts will
miss.

CPU only.
"""
from __future__ import annotations

from typing import List

import costs as C
from interface import (Action, Observation, Policy, RecallAction, SessionAction, StreamAction)


class MooncakeAdapted(Policy):
    name = "mooncake"
    case = "B"
    experiments = ("C-mixed",)
    paper = "Qin et al., Mooncake: A KVCache-centric Disaggregated Architecture for LLM Serving, ACM TOS 2025 / FAST 25 (arXiv:2407.00079)"
    decides = ("recall_decision", "order", "session_action")
    defaults_used = ("episodic_mode", "cadence_s", "frame_count", "representation",
                     "engine_config")
    multi_instance_adapted = True

    def __init__(self, overload_queue: int = 4, reject_on_predicted_miss: bool = True,
                 gpu_warm_slots: int = 4) -> None:
        self.overload_queue = int(overload_queue)
        self.reject = bool(reject_on_predicted_miss)
        self.gpu_warm_slots = int(gpu_warm_slots)

    def decide(self, obs: Observation) -> Action:
        queued = sum(obs.cloud.queued_by_class.values())
        overloaded = queued >= self.overload_queue
        rec: List[RecallAction] = []
        # Maximise KV reuse: serve the cache-resident work first (its TTFT is lowest).
        order = sorted(obs.recall,
                       key=lambda q: ({"GPU-WARM": 0, "HOST-WARM": 1, "COLD": 2}[q.readiness],
                                      q.deadline_s))
        for q in order:
            pred = C.recall_ttft_s(max(q.readiness_tokens, 1), q.readiness)
            will_miss = pred > q.slack_s(obs.now_s)
            if will_miss and overloaded and self.reject:
                # prediction-based EARLY REJECTION: do not start work that cannot meet its SLO
                rec.append(RecallAction(q.query_id, "REJECT"))
            elif will_miss:
                rec.append(RecallAction(q.query_id, "DEVICE"))
            else:
                rec.append(RecallAction(q.query_id, "CLOUD"))
        warm = [q.session_id for q in order[:self.gpu_warm_slots]]
        known = sorted(set(obs.cloud.gpu_warm_sessions) | set(obs.cloud.host_warm_sessions)
                       | {q.session_id for q in obs.recall})
        return Action(
            streams=[StreamAction(s.stream_id, "cloud") for s in obs.streams],
            recall=rec,
            sessions=[SessionAction(s, "KEEP_GPU_WARM" if s in warm else "OFFLOAD_TO_HOST")
                      for s in known],
            order="MOONCAKE-REUSE-FIRST")
