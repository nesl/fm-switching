#!/usr/bin/env python3
"""ATDM / Thinking-QwenVL (arXiv:2604.18459), ADAPTED. Case D. P1, readiness component.

Decision logic = `reconstructed/thinking_qwenvl.py` (ATDM), unchanged. Mapping in
cards/thinking_qwenvl.md.

  progress rho  <- how much of the evidence the application holds: the fraction of the session's
                   representations that exist at some tier, which is observable.
  confidence    <- the device answer's confidence (StudyD13 logprob) where one exists; for an
                   episodic stream, the device's own delivered score mapped to [0, 1].
  t*            <- the first epoch at which both clear their thresholds; before that the policy
                   DEFERS, which our action space supports directly.

This is a COMPONENT baseline: it decides readiness/stopping only, and everything else takes the
documented defaults. `restricts_action_space` is declared because that restriction IS the
property being tested (fairness rule 4).

CPU only.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parent / "reconstructed"))

from interface import (Action, Observation, Policy, RecallAction, StreamAction)
from thinking_qwenvl import atdm  # noqa: E402


class ThinkingQwenVLAdapted(Policy):
    name = "thinking-qwenvl-atdm"
    case = "D"
    experiments = ("A-episodic",)
    paper = ("Zhang et al., Progressive Online Video Understanding with Evidence-Aligned Timing "
             "and Transparent Decisions, arXiv:2604.18459")
    decides = ("recall_decision", "defer_s", "episodic_mode")
    defaults_used = ("cadence_s", "frame_count", "representation", "session_action", "order")
    restricts_action_space = "decides readiness / stopping only"
    restriction_reason = ("it is a COMPONENT baseline for response timing, which is the property "
                          "under test; every other part of the action space takes the documented "
                          "defaults so the timing decision is isolated")

    def __init__(self, progress_threshold: float = 0.6, confidence_threshold: float = 0.6,
                 defer_s: float = 0.5) -> None:
        self.pt, self.ct, self.defer_s = (float(progress_threshold), float(confidence_threshold),
                                          float(defer_s))
        self.decision_log: List[str] = []

    def reset(self, seed: int = 0) -> None:
        self.decision_log = []

    def decide(self, obs: Observation) -> Action:
        rec = []
        for q in obs.recall:
            rho = min(len({e.representation for e in q.evidence}) / 3.0, 1.0)
            conf = (float(q.device_answer_confidence)
                    if q.device_answer_confidence is not None else rho)
            d = atdm(rho, conf, self.pt, self.ct)
            # the transparency the paper is about: the reason is kept, not discarded
            self.decision_log.append(f"t={obs.now_s:.2f} {q.query_id}: {d.reason}")
            rec.append(RecallAction(q.query_id, "CLOUD") if d.answer_now
                       else RecallAction(q.query_id, "DEFER", defer_s=self.defer_s))
        acts = []
        for s in obs.streams:
            v = s.latest_score()
            # map the device score into [0, 1] as a confidence surrogate; progress is how much
            # history the stream has delivered so far
            conf = 0.0 if v is None else max(min((v + 12.0) / 12.0, 1.0), 0.0)
            rho = min(len(s.delivered_scores) / 20.0, 1.0)
            d = atdm(rho, conf, self.pt, self.ct)
            acts.append(StreamAction(s.stream_id,
                                     "cloud" if (d.answer_now and s.network.connected)
                                     else "local"))
        return Action(streams=acts, recall=rec)
