#!/usr/bin/env python3
"""INAR-VL (arXiv:2605.18853, EdgeSys 2026), ADAPTED. Case D.

Decision logic = `reconstructed/inarvl.py` (Section 3 / Figure 1, stages 2-5), unchanged.
Mapping and adaptations in cards/inarvl.md.

The paper's signals are computed from the (image, question) pair. We do not re-read pixels (that
would be new measurement), so:
  image branch (blur, exposure, artifact, detail)  <- the DEVICE's own delivered score trajectory
      statistics, normalised to [0, 1]: a weak, flat, noisy trajectory plays the role of a
      degraded image, which is what the paper's signals are FOR (deciding when the edge model is
      out of its depth). Recorded as adaptation A1, and it is the largest departure in this card.
  text branch (6 complexity signals)               <- the recall query's category, deadline
      pressure and evidence inventory.
  candidate strengths (blur robustness, detail/OCR, reasoning)  <- our MEASURED accuracies:
      StudyE9b AP for the episodic arms, StudyRH4 / E6 for the recall arms, normalised.
  latency / energy                                 <- `costs` (StudyD4 / D7 / D7b / D8 / RH5).

CPU only.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent / "reconstructed"))

import costs as C
import profiles as P
from inarvl import Candidate, fuse, route  # noqa: E402
from interface import Action, Observation, Policy, RecallAction, StreamAction


def _norm(x: float, lo: float, hi: float) -> float:
    return float(min(max((x - lo) / (hi - lo + 1e-12), 0.0), 1.0))


class INARVLAdapted(Policy):
    name = "inar-vl"
    case = "D"
    experiments = ('A-episodic', 'C-mixed')
    paper = "Sabanovic, Maliakel, Brandic, INAR-VL, arXiv:2605.18853 (EdgeSys 2026)"
    decides = ("episodic_mode", "cadence_s", "frame_count", "recall_decision")
    defaults_used = ("representation", "session_action", "order", "engine_config")

    def __init__(self, setting: str = "measured@25", quality_floor: float = 0.6,
                 gain_per_second: float = 0.2, gain_per_joule: float = 0.0) -> None:
        self.quality_floor = float(quality_floor)
        self.gps, self.gpj = float(gain_per_second), float(gain_per_joule)
        rows = P.stream_profile(setting=setting, horizon=0.5, quality="streaming")
        qmax = max(r["quality"] for r in rows)
        self.cands: List[Candidate] = []
        for r in rows:
            strength = _norm(r["quality"], 0.0, qmax)
            self.cands.append(Candidate(
                name=r["name"], placement=("edge" if r["mode"] == "local" else "cloud"),
                blur_robustness=strength, detail_ocr=strength, reasoning=strength,
                latency_s=r["lag_s"], energy_j=0.0))
        self._by_name = {r["name"]: r for r in rows}

    def _image_signals(self, s) -> dict:
        h = np.asarray([v for v in s.delivered_scores], dtype=float)
        if len(h) == 0:
            return dict(blur=1.0, exposure=0.5, artifact=0.5, detail=0.0)
        # A weak / flat / noisy device trajectory is the analogue of a degraded image.
        return dict(blur=_norm(-float(h[-1]), 0.0, 12.0),
                    exposure=_norm(float(h.std()), 0.0, 4.0),
                    artifact=_norm(float(h.std()), 0.0, 6.0),
                    detail=_norm(float(h.max()) + 12.0, 0.0, 12.0))

    def decide(self, obs: Observation) -> Action:
        acts = []
        for s in obs.streams:
            r = fuse(self._image_signals(s),
                     dict(length=0.0, entity_numeric_density=0.0, question_type=0.0,
                          vocabulary_complexity=0.0, reasoning_markers=0.0,
                          context_dependency=0.0))
            c, _q, _why = route(r, self.cands, self.quality_floor, self.gps, self.gpj)
            row = self._by_name[c.name]
            if row["mode"] == "local" or not s.network.connected:
                acts.append(StreamAction(s.stream_id, "local"))
            else:
                acts.append(StreamAction(s.stream_id, "cloud", row["cadence_s"],
                                         row["frame_count"]))
        rec = []
        for q in obs.recall:
            # text branch: deadline pressure and evidence richness stand for question complexity
            slack = q.slack_s(obs.now_s)
            tr = dict(length=_norm(q.readiness_tokens, 0, 28000),
                      entity_numeric_density=_norm(len(q.evidence), 0, 3),
                      question_type=0.5, vocabulary_complexity=0.5,
                      reasoning_markers=_norm(q.readiness_tokens, 0, 28000),
                      context_dependency=1.0 - _norm(slack, 0.0, 10.0))
            r = fuse(dict(blur=0.0, exposure=0.5, artifact=0.0, detail=0.5), tr)
            c, _q2, _w = route(r, self.cands, self.quality_floor, self.gps, self.gpj)
            rec.append(RecallAction(q.query_id,
                                    "CLOUD" if c.placement == "cloud" else "DEVICE"))
        return Action(streams=acts, recall=rec)
