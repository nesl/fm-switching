#!/usr/bin/env python3
"""PerLLM (arXiv:2405.14636), ADAPTED behind our policy interface. Case D.

Decision logic = `reconstructed/perllm.py` (Algorithm 1, Equation 4, the CS-UCB rule), unchanged.
Mapping and adaptations in cards/perllm.md.

  super arm S_t    <- one complete assignment of every episodic stream to {local, cloud@(c, N)}
                      and every pending recall query to {device, cloud}. The space is pruned to a
                      per-stream candidate list, because the full product is combinatorial and
                      the paper's own search is over a candidate set (adaptation A2).
  reward Eq (4)    <- our DELIVERED UTILITY in place of the paper's energy terms: the measured
                      quality of the chosen configuration minus the charged GPU-seconds, plus
                      lambda * f(y). The task specifies this substitution.
  constraints      <- C1 processing time (each recall query's deadline), computing power
                      (budget GPU-seconds) and bandwidth (uplink bytes), exactly the paper's
                      three constraint families.

CPU only.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent / "reconstructed"))

import costs as C
import profiles as P
from interface import (Action, Observation, Policy, RecallAction, StreamAction)
from perllm import CSUCB, constraint_satisfaction, reward  # noqa: E402


class PerLLMAdapted(Policy):
    name = "perllm"
    case = "D"
    experiments = ('C-mixed',)
    paper = "Yang et al., PerLLM: Personalized Inference Scheduling with Edge-Cloud Collaboration (arXiv:2405.14636)"
    decides = ("episodic_mode", "cadence_s", "frame_count", "recall_decision")
    defaults_used = ("representation", "session_action", "order", "engine_config")

    def __init__(self, setting: str = "measured@25", c_ucb: float = 1.0, lam: float = 1.0,
                 horizon_s: float = 10.0, w_quality: float = 1.0, w_gpu: float = 1.0) -> None:
        self.rows = P.stream_profile(setting=setting, horizon=0.5, quality="streaming")
        self.horizon_s = float(horizon_s)
        self.w_quality, self.w_gpu = float(w_quality), float(w_gpu)
        self.bandit = CSUCB(c=c_ucb, lam=lam)

    def reset(self, seed: int = 0) -> None:
        self.bandit = CSUCB(c=self.bandit.c, lam=self.bandit.lam)

    def decide(self, obs: Observation) -> Action:
        rows = self.rows
        # Candidate super arms: every stream on the same configuration (the paper's own search is
        # over a pruned candidate set, Section 3.2). Each candidate is identified by a row name.
        cands = [r["name"] for r in rows]
        by_name = {r["name"]: r for r in rows}
        n = max(len(obs.streams), 1)

        def evaluate(key) -> Tuple[float, List[float], List[float]]:
            r = by_name[key]
            gpu = r["demand_gpu_s_per_s"] * n * self.horizon_s
            up = r["uplink_bytes_per_s"] * n * self.horizon_s
            quality = r["quality"] * n
            worst_slack = min((q.slack_s(obs.now_s) for q in obs.recall), default=1.0)
            # C1: the processing time of the pending work must fit the tightest deadline.
            proc = max((C.recall_ttft_s(max(q.readiness_tokens, 1), q.readiness)
                        for q in obs.recall), default=0.0)
            vals = [proc, gpu, up]
            lims = [max(worst_slack, 0.0), max(obs.budget_remaining_gpu_s, 0.0), float("inf")]
            f_y = constraint_satisfaction(vals, lims)
            # Equation (4) with our delivered utility instead of the paper's energy model.
            rwd = reward(energy_tran=0.0, energy_infer=gpu, energy_idle=0.0,
                         w_tran=0.0, w_infer=self.w_gpu, w_idle=0.0,
                         f_y=f_y, lam=self.bandit.lam) + self.w_quality * quality
            return rwd, vals, lims

        key = self.bandit.schedule(cands, evaluate)
        r = by_name[key] if key is not None else rows[0]
        acts = []
        for s in obs.streams:
            if r["mode"] == "local" or not s.network.connected:
                acts.append(StreamAction(s.stream_id, "local"))
            else:
                acts.append(StreamAction(s.stream_id, "cloud", r["cadence_s"], r["frame_count"]))
        rec = []
        left = obs.budget_remaining_gpu_s
        for q in sorted(obs.recall, key=lambda x: x.deadline_s):
            cost = C.recall_gpu_s(max(q.readiness_tokens, 1), q.readiness)
            if cost <= left and cost <= q.slack_s(obs.now_s):
                left -= cost
                rec.append(RecallAction(q.query_id, "CLOUD"))
            else:
                rec.append(RecallAction(q.query_id, "DEVICE"))
        return Action(streams=acts, recall=rec)
