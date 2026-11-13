#!/usr/bin/env python3
"""Pensieve (EuroSys 2025), ADAPTED behind our policy interface. Case D.

Decision logic = `reconstructed/pensieve.py` (Section 4), unchanged. Mapping and adaptations in
cards/pensieve.md. The one that matters: Pensieve evicts at TOKEN / CHUNK granularity and allows
a session to be partially resident; our interface's session actions are whole-session, so a
partial residency is expressed as OFFLOAD_TO_HOST for the whole session (adaptation A1), and the
chunk-level value ordering decides WHICH sessions are offloaded first.

CPU only.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parent / "reconstructed"))

import costs as C
from interface import (Action, Observation, Policy, RecallAction, SessionAction,
                       StreamAction, materialize)
from pensieve import CPU, GPU, Chunk, chunk_value, evict_to_fit  # noqa: E402


class PensieveAdapted(Policy):
    name = "pensieve"
    case = "D"
    experiments = ('B-recall',)
    paper = "Yu, Lin, Li, Stateful Large Language Model Serving with Pensieve, EuroSys 2025"
    decides = ("session_action", "recall_decision", "order")
    defaults_used = ("episodic_mode", "cadence_s", "frame_count", "representation")

    def __init__(self, gpu_capacity_tokens: int = 60000, reuse_horizon_s: float = 30.0) -> None:
        self.cap = int(gpu_capacity_tokens)
        self.reuse_horizon_s = float(reuse_horizon_s)

    def decide(self, obs: Observation) -> Action:
        # One chunk per session, sized by its readiness tokens; the recompute rate is StudyRH5's
        # measured cold prefill rate for that size, which is what makes a long history
        # "expensive to recompute" in the paper's sense.
        chunks: List[Chunk] = []
        tokens = {}
        for q in obs.recall:
            tokens[q.session_id] = max(tokens.get(q.session_id, 0), q.readiness_tokens)
        for sid in obs.cloud.gpu_warm_sessions:
            tokens.setdefault(sid, 11000)
        for sid, tok in sorted(tokens.items()):
            rate = C.COLD_PREFILL_TOK_S[min(C.RECALL_SIZES, key=lambda s: abs(s - tok))]
            chunks.append(Chunk(sid, 0, tok,
                                GPU if sid in obs.cloud.gpu_warm_sessions else CPU,
                                recompute_tok_s=rate, reuse_horizon_s=self.reuse_horizon_s))
        after = evict_to_fit(chunks, self.cap)
        sess = [(materialize(c.sid, max(tokens.get(c.sid, 11000), 1), slice_tokens=None)
                 if (c.tier == GPU and c.sid not in obs.cloud.gpu_warm_sessions)
                 else SessionAction(c.sid, "KEEP_GPU_WARM" if c.tier == GPU
                                    else "OFFLOAD_TO_HOST"))
                for c in after]
        return Action(
            streams=[StreamAction(s.stream_id, "cloud") for s in obs.streams],
            recall=[RecallAction(q.query_id, "CLOUD") for q in obs.recall],
            sessions=sess, order="FCFS")
