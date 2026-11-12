#!/usr/bin/env python3
"""StreamScout (arXiv:2609.00291), ADAPTED behind our policy interface. Case D. P0 for recall.

Decision logic = `reconstructed/streamscout.py`, unchanged. Mapping in cards/streamscout.md.

The paper's three increasingly informative views map onto our three committed representations,
in the paper's own order:
      recent glance    -> RECENT
      uniform look-back-> D2   (a fixed-stride history, StudyRH4's D2 - a UNIFORM look-back by
                                construction, which is why it is the second stage and not RICH)
      query-relevant   -> RICH (the full history, from which a query-relevant subset could be
                                drawn; we have no retrieval stage, so RICH is the deepest view)
At each stage the policy answers if the sufficiency signal clears that stage's threshold,
otherwise it escalates. The thresholds are distilled on the DEVELOPMENT split, never on
evaluation data.

CPU only.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent / "reconstructed"))

import costs as C
import devsplit as DS
from interface import (Action, Observation, Policy, RecallAction, StreamAction)
from streamscout import STAGES, cascade, fit_thresholds  # noqa: E402

STAGE_REP = ("RECENT", "D2", "RICH")


class StreamScoutAdapted(Policy):
    name = "streamscout"
    case = "D"
    experiments = ("B-recall",)
    paper = "StreamScout: Learning When to Look Deeper for Streaming Video Understanding, arXiv:2609.00291"
    decides = ("recall_decision", "representation", "episodic_mode")
    defaults_used = ("cadence_s", "frame_count", "session_action", "order")

    def __init__(self, thresholds: Optional[Sequence[float]] = None) -> None:
        if thresholds is None:
            thresholds = self._distil()
        self.thresholds = list(thresholds)

    @staticmethod
    def _distil() -> List[float]:
        """The paper's distillation step, on StudyD3's DEVELOPMENT clips.

        For each development example the three stage signals are the device arm's own score at
        increasing look-back depths, and the EARLIEST ADEQUATE STAGE is the first depth at which
        the cloud arm would not have improved on the device - i.e. the first stage whose evidence
        already suffices. Both come from committed development-split traces only.
        """
        ds = DS.router_dataset(device_arm=("4BI", 1), cloud_arm=("32BI", 1))
        sig, earliest = [], []
        for i in range(len(ds.X)):
            # stage signals: score now, the 3-window mean, the 5-window max (increasing depth)
            s = [float(ds.X[i, 0]), float(ds.X[i, 1]), float(ds.X[i, 2])]
            sig.append(s)
            gap = float(ds.gap[i])          # cloud - device at this moment
            earliest.append(0 if gap <= 0 else (1 if gap <= 1.0 else 2))
        return fit_thresholds(sig, earliest)

    def decide(self, obs: Observation) -> Action:
        rec: List[RecallAction] = []
        for q in obs.recall:
            # sufficiency signals at the three depths, from what the application actually holds
            have = {e.representation for e in q.evidence}
            conf = q.device_answer_confidence
            base = float(conf) if conf is not None else min(len(q.evidence) / 3.0, 1.0)
            sig = [base, base + 0.1, base + 0.2]
            stage, _early = cascade(sig, self.thresholds)
            rep = STAGE_REP[min(stage, len(STAGE_REP) - 1)]
            if rep not in have and have:
                rep = sorted(have, key=lambda r: STAGE_REP.index(r)
                             if r in STAGE_REP else 99)[-1]
            if stage == 0 and conf is None:
                rec.append(RecallAction(q.query_id, "DEVICE"))
            else:
                rec.append(RecallAction(q.query_id, "CLOUD", representation=rep))
        # StreamScout is a recall-side cascade; episodic streams take the documented default.
        return Action(streams=[StreamAction(s.stream_id, "local") for s in obs.streams],
                      recall=rec)
