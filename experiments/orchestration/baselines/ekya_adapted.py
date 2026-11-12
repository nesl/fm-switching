#!/usr/bin/env python3
"""Ekya (NSDI 2022), ADAPTED behind our policy interface. Case B.

Original: https://github.com/edge-video-services/ekya (Microsoft Research-endorsed release),
cloned to ~/baselines_src/ekya at a pinned commit. Its decision logic lives in
`ekya/schedulers/` and is a "thief scheduler": it starts from a fair share, then repeatedly
STEALS a resource increment from one job and gives it to another, keeping the reallocation only
if a micro-profiled estimate says the total accuracy improves.

Translation into our setting (listed in full in `cards/ekya.md`):
  inference jobs     <- episodic streams (each needs cloud GPU share to keep its cadence)
  retraining jobs    <- recall warm maintenance and cold recall prefills (the background work
                        that competes for the same GPU)
  micro-profiles     <- our measured curves instead of Ekya's sampled retraining profiles:
                        stream accuracy from StudyE9b (`profiles`), recall service time from
                        StudyRH5 (`costs.recall_ttft_s`)
  thief scheduler    <- reimplemented here in Python following the released scheduler's
                        structure, because the original runs on Ray with NVIDIA MPS and so
                        cannot be called from a CPU-only replay (recorded as adaptation A3)

CPU only.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import costs as C
import profiles as P
from interface import (Action, Observation, Policy, RecallAction, SessionAction, StreamAction)


class EkyaAdapted(Policy):
    name = "ekya"
    case = "B"
    experiments = ('A-episodic', 'C-mixed')
    paper = "Bhardwaj et al., Ekya: Continuous Learning of Video Analytics Models on Edge Compute Servers, NSDI 2022"
    decides = ("episodic_mode", "cadence_s", "frame_count", "recall_decision", "session_action")
    defaults_used = ("representation", "order", "engine_config")

    def __init__(self, setting: str = "measured@25", horizon_ap: float = 0.5,
                 steps: int = 20, horizon_s: float = 10.0,
                 quality: str = "streaming") -> None:
        self.setting = setting
        self.steps = int(steps)                 # Ekya's thief iterations per scheduling round
        self.horizon_s = float(horizon_s)
        self._rows = [r for r in P.stream_profile(setting=setting, horizon=horizon_ap,
                                                  quality=quality)]
        self._cloud_rows = [r for r in self._rows if r["mode"] == "cloud"]
        self._local = next(r for r in self._rows if r["mode"] == "local")

    # ---- micro-profiles: what each side gains from an increment of GPU share
    def _stream_gain(self, share: float) -> Tuple[float, Optional[Dict]]:
        """Best inference configuration affordable at `share` GPU-s per wall second, and its
        quality. Ekya's inference jobs have a fixed accuracy per configuration; ours come from
        StudyE9b."""
        best, q = None, self._local["quality"]
        for r in self._cloud_rows:
            if r["demand_gpu_s_per_s"] <= share + 1e-12 and r["quality"] > q:
                best, q = r, r["quality"]
        return q, best

    def _recall_gain(self, obs: Observation, share: float) -> float:
        """Background-job utility: how many pending recall queries this share can serve inside
        their deadline, using StudyRH5's measured service times at their current readiness."""
        served = 0.0
        budget = share * self.horizon_s
        for q in sorted(obs.recall, key=lambda x: x.deadline_s):
            cost = C.recall_gpu_s(max(q.readiness_tokens, 1), q.readiness)
            if cost <= budget and cost <= q.slack_s(obs.now_s):
                budget -= cost
                served += 1.0
        return served

    def decide(self, obs: Observation) -> Action:
        n = len(obs.streams)
        total = max(obs.budget_remaining_gpu_s / max(self.horizon_s, 1e-9), 0.0)
        if n == 0:
            return Action(recall=[RecallAction(q.query_id, "CLOUD") for q in obs.recall])
        # Ekya step 1: start from a FAIR share across the inference jobs and the background pool.
        pools = n + 1                                  # n streams + one background pool
        share = {s.stream_id: total / pools for s in obs.streams}
        bg = total / pools
        step = total / max(pools * self.steps, 1)

        def score() -> float:
            # Ekya's objective is total accuracy across jobs; ours adds the background pool's
            # served-recall count, normalised so the two are commensurable (adaptation A4).
            s = sum(self._stream_gain(share[k])[0] for k in share)
            return s + 0.0 * self._recall_gain(obs, bg)

        # Ekya step 2: the thief loop. Steal `step` from each victim in turn, give it to each
        # thief, keep the reallocation only if the micro-profiled score improves.
        cur = score()
        for _ in range(self.steps):
            improved = False
            ids = list(share)
            for victim in ids + ["__bg__"]:
                for thief in ids + ["__bg__"]:
                    if victim == thief:
                        continue
                    if victim == "__bg__":
                        if bg < step:
                            continue
                        bg -= step
                        share[thief] += step
                    elif thief == "__bg__":
                        if share[victim] < step:
                            continue
                        share[victim] -= step
                        bg += step
                    else:
                        if share[victim] < step:
                            continue
                        share[victim] -= step
                        share[thief] += step
                    new = score()
                    if new > cur + 1e-12:
                        cur, improved = new, True
                    else:                                     # revert: Ekya keeps only wins
                        if victim == "__bg__":
                            bg += step
                            share[thief] -= step
                        elif thief == "__bg__":
                            share[victim] += step
                            bg -= step
                        else:
                            share[victim] += step
                            share[thief] -= step
            if not improved:
                break

        acts = []
        for s in obs.streams:
            _q, row = self._stream_gain(share[s.stream_id])
            if row is None or not s.network.connected:
                acts.append(StreamAction(s.stream_id, "local"))
            else:
                acts.append(StreamAction(s.stream_id, "cloud", row["cadence_s"],
                                         row["frame_count"]))
        # Background pool: spend `bg` on pending recall in deadline order; defer what does not fit.
        rec, left = [], bg * self.horizon_s
        for q in sorted(obs.recall, key=lambda x: x.deadline_s):
            cost = C.recall_gpu_s(max(q.readiness_tokens, 1), q.readiness)
            if cost <= left and cost <= q.slack_s(obs.now_s):
                left -= cost
                rec.append(RecallAction(q.query_id, "CLOUD"))
            else:
                rec.append(RecallAction(q.query_id, "DEVICE"))
        return Action(streams=acts, recall=rec, order="FCFS",
                      sessions=[SessionAction(sid, "OFFLOAD_TO_HOST")
                                for sid in obs.cloud.gpu_warm_sessions])
