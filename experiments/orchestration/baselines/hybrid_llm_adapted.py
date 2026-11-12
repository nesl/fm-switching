#!/usr/bin/env python3
"""Hybrid LLM (ICLR 2024), ADAPTED behind our policy interface. Case D.

Decision logic = `reconstructed/hybrid_llm.py` (Equations 1-4, Sections 3.1-3.3), unchanged.
This module only supplies features, labels and the routing threshold. Full mapping in
cards/hybrid_llm.md.

  small model S   <- the device 4B arm;  large model L <- the cloud 32B arm
  quality q(.)    <- the continuous Nexar score log P(Yes) at the same moment, so the quality gap
                     H(x) = q(S(x)) - q(L(x)) is computed from committed traces, not from a
                     BART score
  features x      <- StudyD3 DEVELOPMENT-split device-score trajectory features (`devsplit`)
  router          <- the paper's rdet / rprob / rtrans, trained on the development split only
  routing rule    <- send to the SMALL model (keep local) when p_w(x) >= threshold; the threshold
                     is the paper's cost knob

CPU only.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent / "reconstructed"))

import devsplit as DS
from hybrid_llm import HybridRouter  # noqa: E402
from interface import Action, Observation, Policy, RecallAction, StreamAction


def _features(stream) -> List[float]:
    """The same six features `devsplit.FEATURES` defines, from the stream's DELIVERED history."""
    h = [v for v in stream.delivered_scores if v is not None]
    if not h:
        return [0.0] * len(DS.FEATURES)
    prev = np.asarray(h[:-1] if len(h) > 1 else h, dtype=float)
    sl = 0.0
    if len(prev) >= 2:
        sl = float(np.polyfit(np.arange(len(prev), dtype=float), prev, 1)[0])
    return [float(h[-1]), float(prev.mean()), float(prev.max()), sl, float(prev.std()),
            float(len(h))]


class HybridLLMAdapted(Policy):
    name = "hybrid-llm"
    case = "D"
    experiments = ('A-episodic', 'C-mixed')
    paper = "Ding et al., Hybrid LLM: Cost-Efficient and Quality-Aware Query Routing, ICLR 2024"
    decides = ("episodic_mode", "recall_decision")
    defaults_used = ("cadence_s", "frame_count", "representation", "session_action", "order")

    def __init__(self, variant: str = "trans", threshold: float = 0.5,
                 cadence_s: float = 0.5, frame_count: int = 1) -> None:
        self.variant, self.threshold = variant, float(threshold)
        self.cadence_s, self.frame_count = float(cadence_s), int(frame_count)
        ds = DS.router_dataset(device_arm=("4BI", 1), cloud_arm=("32BI", 1))
        # y^det / y^prob / y^trans all estimate Pr[H(x) >= 0] = Pr[the device is as good as the
        # cloud]. The offset design gives ONE response per (clip, offset), so y^prob's 10-sample
        # expectation is unavailable; we pass the single-sample quality pair and the reconstruction
        # falls back to y^det inside rprob/rtrans, which is recorded as adaptation A1.
        self.router = HybridRouter(variant).fit(ds.X, ds.q_small, ds.q_large)
        self.n_dev = int(len(ds.X))
        self.t_star = self.router.t_star

    def decide(self, obs: Observation) -> Action:
        acts = []
        for s in obs.streams:
            x = np.asarray([_features(s)], dtype=float)
            keep_local = bool(self.router.route(x, self.threshold)[0]) or not s.network.connected
            acts.append(StreamAction(s.stream_id, "local" if keep_local else "cloud",
                                     None if keep_local else self.cadence_s,
                                     None if keep_local else self.frame_count))
        # Hybrid LLM routes a single request, not a stateful session; recall queries use the same
        # router on the device answer's confidence where one exists, else the documented default.
        rec = []
        for q in obs.recall:
            c = q.device_answer_confidence
            rec.append(RecallAction(q.query_id, "DEVICE" if (c is not None and c >= 0.5)
                                    else "CLOUD"))
        return Action(streams=acts, recall=rec)
