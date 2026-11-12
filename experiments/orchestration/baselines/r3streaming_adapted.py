#!/usr/bin/env python3
"""R3-Streaming (arXiv:2605.17921), ADAPTED behind our policy interface. Case D.

Decision logic = `reconstructed/r3streaming.py` (Section 4's three decisions), unchanged. The
task asks for its remember / respond / reason decomposition as an INDEPENDENT CASCADE, and that
is exactly how it is wired here. Mapping in cards/r3streaming.md.

  Remember (Active Forgetting)  <- the recall representation: nearby context at full fidelity,
      historical context compressed. In our action space the representation choice {RECENT, RICH,
      D2} IS this decision: RECENT = keep only nearby, D2 = keep a strided history, RICH = keep
      the full history. The paper's continuous ratio is therefore quantised to our three
      committed representations (adaptation A1).
  Respond (readiness head)      <- whether to answer now or DEFER: our interface has a DEFER
      action, so this maps exactly. The evidence score is the device answer's confidence where
      one exists, else the evidence inventory's coverage.
  Reason (Adaptive Thinking)    <- route the hardest queries to the 32B cloud model under an
      escalation-rate budget; the rest answer on the device.

CPU only.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent / "reconstructed"))

from interface import (Action, Observation, Policy, RecallAction, StreamAction)
from r3streaming import REASON, ROUTINE, adaptive_thinking, readiness  # noqa: E402


class R3StreamingAdapted(Policy):
    name = "r3-streaming"
    case = "D"
    experiments = ('A-episodic', 'B-recall')
    paper = "Liu et al., An Efficient Streaming Video Understanding Framework with Agentic Control (R3-Streaming), arXiv:2605.17921"
    decides = ("episodic_mode", "recall_decision", "representation", "defer_s")
    defaults_used = ("cadence_s", "frame_count", "session_action", "order")

    def __init__(self, readiness_threshold: float = 0.5, escalation_budget: float = 0.25,
                 nearby_window_s: float = 10.0, defer_s: float = 1.0) -> None:
        self.readiness_threshold = float(readiness_threshold)
        self.escalation_budget = float(escalation_budget)
        self.nearby_window_s = float(nearby_window_s)
        self.defer_s = float(defer_s)

    @staticmethod
    def _evidence_score(q) -> float:
        if q.device_answer_confidence is not None:
            return float(q.device_answer_confidence)
        # no device answer: use how much evidence exists at all, which is the readiness head's
        # input in our setting
        return min(len(q.evidence) / 3.0, 1.0)

    @staticmethod
    def _difficulty(q) -> float:
        # a long history and a tight deadline make a query hard, in the paper's sense
        return min(q.readiness_tokens / 28000.0, 1.0)

    def _representation(self, q, now_s: float) -> str:
        """Remember: nearby at full fidelity, historical compressed."""
        has = {e.representation for e in q.evidence}
        if "D2" in has:
            return "D2"            # a strided history IS the compressed form we hold
        if "RECENT" in has:
            return "RECENT"
        return "RICH" if "RICH" in has else "RECENT"

    def decide(self, obs: Observation) -> Action:
        diffs = [self._difficulty(q) for q in obs.recall]
        paths = adaptive_thinking(diffs, self.escalation_budget)
        rec: List[RecallAction] = []
        for q, path in zip(obs.recall, paths):
            if not readiness(self._evidence_score(q), self.readiness_threshold):
                rec.append(RecallAction(q.query_id, "DEFER", defer_s=self.defer_s))
            elif path == REASON:
                rec.append(RecallAction(q.query_id, "CLOUD",
                                        representation=self._representation(q, obs.now_s)))
            else:
                rec.append(RecallAction(q.query_id, "DEVICE"))
        # Episodic streams: the same Reason gate on the device's own trajectory. The paper's
        # "always-on large model" is what it argues against, so a stream escalates only when its
        # own difficulty puts it inside the escalation budget.
        sdiff = [abs(s.latest_score() or -12.0) ** -1 if s.latest_score() else 0.0
                 for s in obs.streams]
        spaths = adaptive_thinking(sdiff, self.escalation_budget)
        acts = [StreamAction(s.stream_id,
                             "cloud" if (p == REASON and s.network.connected) else "local")
                for s, p in zip(obs.streams, spaths)]
        return Action(streams=acts, recall=rec)
