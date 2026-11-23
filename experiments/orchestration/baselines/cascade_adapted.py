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

from typing import Any, Dict, List, Optional, Tuple

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
    # amendment 2 item 3b (2026-11-13): this baseline's PUBLISHED mechanism observes the
    # device-side model's own answer before deciding, so it receives
    # `device_answer_confidence` and the harness charges that device answer.
    reads_device_answer = True
    # D154 (5) / D146 (2), THE CHARGE AND ITS REGISTER. The device answer this arm waits for is
    # charged `costs.DEV_LAT_S = 0.567 s` (StudyD8 arm A's single-frame total p50), read by
    # `coordinator.py:63 DEVICE_ANSWER_CHARGE_S` and applied at `coordinator.py:471` (the device
    # answer's service time) and `:505` (the earliest instant this arm may act). That 0.567 s is a
    # PROXY and is SUPERSEDED by StudyORIN-REC's measured warm device completion latency, p50
    # 0.2697 s per question (commit 00a223d). Because both application sites are LIVE
    # decision-timing sites, adopting the measured value changes what this arm DOES and needs a
    # RERUN, not a re-score: every committed cell of this arm is therefore labelled `proxy-0.567`,
    # which `scorer/score.py:cascade_device_wait` emits into the header of every score it writes.
    # `data_sources.DEVICE_WAIT_RULE_S` is NOT the site to change: it has one reference in the
    # repository, its own declaration. No attribute is declared here for the measured value, on
    # purpose: nothing reads a per-arm wait, and a field written and never read is absent.
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
        # The recall confidence floor is the median device confidence on DEVELOPMENT data.
        # amendment 2 (2026-11-13): S-EMBER now has a pre-registered DEV / EVAL split by video
        # (`sember_split.py`), so this floor is FITTED on the committed device-answer
        # probabilities of DEV questions only and every recall metric is reported on EVAL only.
        # Before the split it was left None, which made the cascade escalate every query that
        # had a committed probability at all.
        import device_confidence as _DC
        self.confidence_floor = (float(confidence_floor) if confidence_floor is not None
                                 else _DC.dev_median())
        self.confidence_floor_source = ("median committed device confidence (StudyE7 Job A "
                                        "4B-D2) over S-EMBER DEV questions")
        # D164 / user ruling 2026-11-22 item 2: ONE FLOOR PER CONFIDENCE TYPE, by the card's own
        # procedure (the median committed device confidence over DEV questions) applied to each
        # type's own DEV population. The types are different signals on different scales -- the
        # robot and mcq values are letter-probability mass, the free-form and point values are a
        # geometric mean token probability -- so one floor across them is not a stricter or looser
        # operating point, it is a different one per type by accident. The values are READ from
        # the committed calibration file, never re-derived here.
        self.confidence_floors = _DC.fitted_floors()
        self.confidence_floors_source = ("results/orchestration/live2/cascade_calibration/"
                                         "cascade_thresholds.json, fitted on DEV per type under "
                                         "research/prereg_cascade_calibration.md")
        self.stats = dict(arm=self.name, escalate_cloud=0, stop_device=0, no_confidence_device=0,
                          unknown_type=0, by_type={}, stream_scores_seen={})

    def reset(self, seed: int = 0) -> None:
        self.stats = dict(arm=self.name, escalate_cloud=0, stop_device=0, no_confidence_device=0,
                          unknown_type=0, by_type={}, stream_scores_seen={})

    def _floor_for(self, q) -> Tuple[Optional[float], str]:
        """The floor for THIS query's confidence type, and the type itself.

        The type is resolved from `q.question_id` (the field D171 (3) added) against the same
        committed row that supplies the confidence value. A question whose type cannot be resolved
        falls back to the card's single S-EMBER DEV floor and is COUNTED, so a cell decided by a
        fallback is visible rather than silent.
        """
        import device_confidence as _DC
        kind = _DC.kind_of(getattr(q, "question_id", None))
        if kind is None or self.confidence_floors.get(kind) is None:
            self.stats["unknown_type"] += 1
            return self.confidence_floor, (kind or "unresolved")
        return float(self.confidence_floors[kind]), kind

    def _count(self, kind: str, what: str) -> None:
        d = self.stats["by_type"].setdefault(kind, dict(escalate_cloud=0, stop_device=0))
        d[what] += 1

    def decide(self, obs: Observation) -> Action:
        acts: List[StreamAction] = []
        for s in obs.streams:
            # D205 (2b): the DEVICE's own newest score, not the application-visible stream.
            #
            # The card is explicit. Its mapping table gives "scorer / verifier on an episodic
            # stream | the device's DELIVERED score against `tau_trigger` | ADAPTATION A1", and A2
            # sets that threshold as "the (1 - trigger_rate) quantile of the DEVICE arm's score on
            # development-split negatives": tau_trigger = -7.0009 fitted on 3,000 StudyD3
            # development-split negatives, and D164 re-fits it per confidence type with the
            # `episodic` type at -7.000911 on StudyD3 DEV negatives at rate 0.20. A threshold
            # fitted on the DEVICE arm's scores must be compared against a DEVICE score.
            # `latest_score()` is the application-visible stream and carries the CLOUD's answer for
            # every instant the cloud served in time, which is a different population.
            #
            # The card already named this defect: its D164 section records that the quantity A2's
            # threshold is compared against "in live2 is a PLACEHOLDER: coordinator._device_answer
            # appends (t, 0.0) and the cloud path appends (delivered, 0.0)". Because the score is
            # log P(Yes), that 0.0 was the MAXIMUM of the range, so `v >= -7.0009` held on every
            # instant of every committed cell and this arm escalated unconditionally.
            #
            # NEITHER PATH OF THIS ARM NEEDS THE CLOUD SCORE, so a DRY cell is a valid proof for
            # it: the episodic scorer reads the device's own score here, and the recall scorer
            # reads `device_answer_confidence`, a committed per-question table lookup
            # (cstate.py:516) that a dry cell supplies too.
            v = s.latest_device_score("confidence-cascade")
            # Step 2 instrumentation: the thresholded quantity itself, so a CONSTANT where a
            # distribution is expected is visible in the proof rather than inferred (CLAUDE.md
            # results check 3).
            k = "None" if v is None else repr(round(float(v), 6))
            self.stats["stream_scores_seen"][k] = self.stats["stream_scores_seen"].get(k, 0) + 1
            escalate = (v is not None and v >= self.tau_trigger and s.network.connected)
            acts.append(StreamAction(s.stream_id, "cloud" if escalate else "local",
                                     self.cadence_s if escalate else None,
                                     self.frame_count if escalate else None))
        rec: List[RecallAction] = []
        for q in obs.recall:
            c = q.device_answer_confidence
            if c is None:
                # no device answer yet: the cascade's first stage has not run, so run it locally
                self.stats["no_confidence_device"] += 1
                rec.append(RecallAction(q.query_id, "DEVICE"))
                continue
            floor, kind = self._floor_for(q)
            if floor is None or c < floor:
                self.stats["escalate_cloud"] += 1
                self._count(kind, "escalate_cloud")
                rec.append(RecallAction(q.query_id, "CLOUD"))
            else:
                self.stats["stop_device"] += 1
                self._count(kind, "stop_device")
                rec.append(RecallAction(q.query_id, "DEVICE"))
        return Action(streams=acts, recall=rec)
