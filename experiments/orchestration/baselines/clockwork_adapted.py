#!/usr/bin/env python3
"""Clockwork (OSDI 2020), ADAPTED behind our policy interface. Case B.

Original: https://gitlab.mpi-sws.org/cld/ml/clockwork (~26k lines of C++, Distinguished Artifact
Award), cloned to ~/baselines_src/clockwork at a pinned commit.

What Clockwork fundamentally decides (and what we keep): whether to ADMIT a request at all.
Section 4.1: the controller "concludes that the request will complete within its specified SLO"
by summing the predicted time to LOAD the model weights and to subsequently INFER, and it drops
a request whose deadline cannot be met ("The controller is aware that r4 will miss its deadline",
Figure 2). Section 5.2 exposes only LOAD and INFER as actions. Section 5.3 schedules by
STRATEGIES - (model, latest timestamp, batch size) - dequeuing "strategies until it finds one
that is valid: latest has not elapsed, and the batch queue for the specified batch size has
sufficient requests", and dropping requests from a batch queue once their latest has passed.

Translation into our setting (full list in cards/clockwork.md):
  LOAD time      <- the readiness cost of the session's KV: COLD / HOST-WARM / GPU-WARM from
                    StudyRH5 via `costs.recall_ttft_s`. This is exactly Clockwork's "load the
                    model into hardware if not already there", with a KV cache in place of model
                    weights.
  INFER time     <- the same curve's compute component, plus the measured queueing implied by
                    `cloud.latency_estimate_s` at the current load.
  SLO            <- each recall query's own deadline.
  strategies     <- (session, readiness, latest) ordered by `latest`; our interface has no batch
                    size, so the batch dimension is dropped (adaptation A2).
  episodic       <- a standing query has no deadline, so Clockwork has nothing to say about it;
                    streams take the documented default and are admitted only while the budget
                    allows.

CPU only.
"""
from __future__ import annotations

from typing import List

import costs as C
from interface import (Action, Observation, Policy, RecallAction, SessionAction, StreamAction)


class ClockworkAdapted(Policy):
    name = "clockwork"
    case = "B"
    experiments = ('C-mixed',)
    paper = "Gujarati et al., Serving DNNs like Clockwork, OSDI 2020"
    decides = ("recall_decision", "order", "session_action")
    defaults_used = ("cadence_s", "frame_count", "representation", "episodic_mode",
                     "engine_config")

    def __init__(self, safety_margin_s: float = 0.0, reject_instead_of_local: bool = False,
                 keep_warm_slots: int = 0) -> None:
        self.margin = float(safety_margin_s)
        self.reject = bool(reject_instead_of_local)
        self.keep_warm_slots = int(keep_warm_slots)

    def _predicted_s(self, obs: Observation, q) -> float:
        """LOAD + INFER, from our measured curves at the query's CURRENT readiness."""
        load_infer = C.recall_ttft_s(max(q.readiness_tokens, 1), q.readiness)
        queue = obs.cloud.latency_estimate_s.get("recall", 0.0)
        return load_infer + queue + self.margin

    def decide(self, obs: Observation) -> Action:
        rec: List[RecallAction] = []
        # Section 5.3: strategies ordered by `latest`, i.e. by how soon the request must start.
        for q in sorted(obs.recall, key=lambda x: x.deadline_s - self._predicted_s(obs, x)):
            pred = self._predicted_s(obs, q)
            if pred <= q.slack_s(obs.now_s):
                rec.append(RecallAction(q.query_id, "CLOUD"))
            else:
                # Figure 2 / Section 4.1: a request that cannot meet its SLO is dropped rather
                # than served late. We expose both readings and the card states which is primary.
                rec.append(RecallAction(q.query_id, "REJECT" if self.reject else "DEVICE"))
        mode = "cloud" if obs.budget_remaining_gpu_s > 0 else "local"
        # Section 4.2 "consolidating choice": no operation may have implicit performance
        # side-effects, so warm state is managed explicitly rather than opportunistically.
        sess = []
        warm = list(obs.cloud.gpu_warm_sessions)
        for i, sid in enumerate(warm):
            sess.append(SessionAction(sid, "KEEP_GPU_WARM" if i < self.keep_warm_slots
                                      else "OFFLOAD_TO_HOST"))
        return Action(streams=[StreamAction(s.stream_id, mode) for s in obs.streams],
                      recall=rec, sessions=sess, order="EDF")
