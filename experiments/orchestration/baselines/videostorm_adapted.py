#!/usr/bin/env python3
"""VideoStorm (NSDI 2017), ADAPTED behind our policy interface. Case D.

The decision logic is the reconstruction in `reconstructed/videostorm.py` (Equations 1-4,
Sections 6.1-6.3), called unchanged. This module only translates our observation into the
paper's abstract objects and its allocation back into our action space. Every translation is
listed in `cards/videostorm.md`.

Translation (and nothing else is changed):
  query k            <- one episodic stream
  profile P_k        <- `profiles.stream_profile`: configuration = (mode, cadence c, frame
                        count N); quality Q(c) = StudyE9b's measured always-on AP for that arm
                        and cadence (or StudyE9c's challenge mAP); demand D_k(c) = cloud
                        GPU-seconds per wall second; lag = StudyE9b's sample-and-hold shift
  capacity R         <- the budget's remaining cloud GPU-seconds per wall second
  lag L_{k,t}        <- the configuration's hold shift (a property of the tier, not a backlog)
  allocation a_k     <- read back as: a_k > 0 and the chosen configuration is a cloud one
                        => that stream runs on the cloud at that (c, N); otherwise local
  recall queries     <- VideoStorm has no stateful jobs, so these take the documented defaults
                        (serve on cloud, FCFS, LRU host offload), as the task specifies

CPU only.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent / "reconstructed"))

import profiles as P
from interface import (Action, Observation, Policy, RecallAction, SessionAction, StreamAction)
from videostorm import Config, Query, allocate_maxmin, allocate_maxsum, utility  # noqa: E402


class VideoStormAdapted(Policy):
    name = "videostorm"
    case = "D"
    experiments = ('A-episodic',)
    paper = "Zhang et al., Live Video Analytics at Scale with Approximation and Delay-Tolerance, NSDI 2017"
    decides = ("episodic_mode", "cadence_s", "frame_count")
    defaults_used = ("recall_decision", "representation", "session_action", "order",
                     "engine_config")

    def __init__(self, objective: str = "maxmin", setting: str = "measured@25",
                 horizon_s: float = 10.0, horizon_ap: float = 0.5, delta: float = 0.01,
                 quality: str = "streaming",
                 alpha_q: float = 1.0, alpha_l: float = 1.0, lag_max_s: float = 0.5,
                 u_base: float = 0.0, q_min: float = 0.0) -> None:
        if objective not in ("maxmin", "maxsum"):
            raise ValueError(objective)
        self.objective = objective
        self.setting = setting
        self.horizon_s = float(horizon_s)
        self.delta = float(delta)
        self.quality = quality
        # Utility parameters. The paper says alpha^Q, Q^M, alpha^L and L^M are "query-specific and
        # set based on the application" (S6.1) and suggests a small template set. Ours are the
        # paper's own template shape with our units; see the card for the provenance of each.
        self.alpha_q, self.alpha_l = float(alpha_q), float(alpha_l)
        self.lag_max_s, self.u_base, self.q_min = float(lag_max_s), float(u_base), float(q_min)
        self._rows = P.stream_profile(setting=setting, horizon=horizon_ap, quality=quality)
        if not self._rows:
            raise RuntimeError("empty profile: no measured quality on this scale")

    def _query(self, stream_id: str) -> Query:
        return Query(
            qid=stream_id,
            profile=[Config(r["name"], r["quality"], max(r["demand_gpu_s_per_s"], 0.0))
                     for r in self._rows],
            u_base=self.u_base, alpha_q=self.alpha_q, alpha_min_q=self.q_min,
            alpha_l=self.alpha_l, lag_max_s=self.lag_max_s,
            lag_s=0.0)

    def decide(self, obs: Observation) -> Action:
        if not obs.streams:
            return Action(recall=[RecallAction(q.query_id, "CLOUD") for q in obs.recall])
        # The paper's lag is a backlog; ours is the tier's delivery hold shift, so each query's
        # L_{k,t} starts at the shift of its CURRENT configuration (the card explains why).
        qs: List[Query] = []
        by_name = {r["name"]: r for r in self._rows}
        for s in obs.streams:
            q = self._query(s.stream_id)
            cur = (f"cloud/32BI_N{s.frame_count}@{s.cadence_s}" if s.on_cloud else "local")
            q.lag_s = by_name.get(cur, self._rows[0])["lag_s"]
            qs.append(q)
        # Capacity R: the cloud GPU-seconds per wall second the budget still affords over the
        # horizon. A stream that is not reachable cannot be allocated at all.
        cap = max(obs.budget_remaining_gpu_s / max(self.horizon_s, 1e-9), 0.0)
        alloc = (allocate_maxmin if self.objective == "maxmin" else allocate_maxsum)(
            qs, cap, self.horizon_s, self.delta)
        acts: List[StreamAction] = []
        for s in obs.streams:
            a, cfg = alloc[s.stream_id]
            row = by_name[cfg.name]
            if row["mode"] == "local" or a <= 0.0 or not s.network.connected:
                acts.append(StreamAction(s.stream_id, "local"))
            else:
                acts.append(StreamAction(s.stream_id, "cloud", row["cadence_s"],
                                         row["frame_count"]))
        return Action(
            streams=acts,
            recall=[RecallAction(q.query_id, "CLOUD") for q in obs.recall],
            order="FCFS",
        )
