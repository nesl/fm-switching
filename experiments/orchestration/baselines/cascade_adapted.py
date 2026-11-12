#!/usr/bin/env python3
"""Confidence cascade - FrugalGPT (TMLR 2024) and AutoMix (NeurIPS 2024), ADAPTED. Case B.

Originals: https://github.com/stanford-futuredata/FrugalGPT (Apache-2.0) and
https://github.com/automix-llm/automix (linked from arXiv:2310.12963), cloned to
~/baselines_src/.

What they decide: whether the SMALL model's answer is good enough, or whether to escalate to a
larger one. FrugalGPT's LLM cascade queries models in a fixed order and stops when a trained
scorer judges the answer reliable; AutoMix adds self-verification and a meta-verifier (a POMDP
router) over the small model's own verification signal.

Translation (full list in cards/cascade.md):
  episodic       <- StudyE9 / E9b's escalation IS this baseline, and the task says to reuse it:
                    escalate a stream to the cloud when the device's DELIVERED score crosses
                    tau_trigger, the threshold fitted at a target trigger rate. We therefore call
                    the same rule, with the threshold fitted on the DEVELOPMENT split.
  recall         <- escalate to the 32B resolver when the 4B answer's confidence is low
                    (StudyD13 logprob, carried on the observation as
                    `device_answer_confidence`), which is FrugalGPT's scorer and AutoMix's
                    verifier in our setting.
  cascade order  <- device (4B) then cloud (32B); a two-stage cascade, where FrugalGPT allows
                    arbitrarily many stages (adaptation A1).

NOT reproduced: FrugalGPT's prompt adaptation and LLM approximation (its other two cost levers,
which change the prompt rather than the placement); AutoMix's POMDP meta-verifier solved over
multiple verification rounds - we use the single-round threshold, which is AutoMix's own
"self-verification" variant (adaptation A2).

CPU only.
"""
from __future__ import annotations

from typing import List, Optional

import numpy as np

import devsplit as DS
from interface import (Action, Observation, Policy, RecallAction, StreamAction)


class CascadeAdapted(Policy):
    name = "confidence-cascade"
    case = "B"
    experiments = ('A-episodic',)
    paper = ("Chen et al., FrugalGPT, TMLR 2024; Aggarwal et al., AutoMix, NeurIPS 2024 "
             "(arXiv:2310.12963)")
    decides = ("episodic_mode", "recall_decision")
    defaults_used = ("cadence_s", "frame_count", "representation", "session_action", "order")

    def __init__(self, trigger_rate: float = 0.20, confidence_floor: Optional[float] = None,
                 cadence_s: float = 0.5, frame_count: int = 1) -> None:
        self.trigger_rate = float(trigger_rate)
        self.cadence_s, self.frame_count = float(cadence_s), int(frame_count)
        # tau_trigger is the (1 - rate) quantile of the DEVICE arm's score distribution on
        # DEVELOPMENT-split negatives, which is StudyE9's own threshold procedure moved off the
        # evaluation clips.
        sc, lab = DS.load(arms=(("4BI", 1),))
        neg = np.array([v for clip, per in sc[("4BI", 1)].items()
                        if lab[clip] == "negative" for v in per.values()])
        self.tau_trigger = float(np.quantile(neg, 1.0 - self.trigger_rate))
        self.n_dev_negatives = int(len(neg))
        # The recall confidence floor is the median device confidence on development data when it
        # is available; otherwise the caller must supply one (never fitted on evaluation data).
        self.confidence_floor = confidence_floor

    def decide(self, obs: Observation) -> Action:
        acts: List[StreamAction] = []
        for s in obs.streams:
            v = s.latest_score()
            escalate = (v is not None and v >= self.tau_trigger and s.network.connected)
            acts.append(StreamAction(s.stream_id, "cloud" if escalate else "local",
                                     self.cadence_s if escalate else None,
                                     self.frame_count if escalate else None))
        rec: List[RecallAction] = []
        for q in obs.recall:
            c = q.device_answer_confidence
            if c is None:
                # no device answer yet: the cascade's first stage has not run, so run it locally
                rec.append(RecallAction(q.query_id, "DEVICE"))
            elif self.confidence_floor is None or c < self.confidence_floor:
                rec.append(RecallAction(q.query_id, "CLOUD"))
            else:
                rec.append(RecallAction(q.query_id, "DEVICE"))
        return Action(streams=acts, recall=rec)
