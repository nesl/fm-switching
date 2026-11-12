#!/usr/bin/env python3
"""ECO-LLM (arXiv:2507.09003), ADAPTED behind our policy interface. Case D. P0.

Decision logic = `reconstructed/ecollm.py`, unchanged. Mapping in cards/ecollm.md.

  configuration space  <- the JOINT product of our actions, which is what the paper insists on:
      episodic  (mode, cadence c, frame count N) from `profiles.stream_profile`
      recall    (tier, representation in {RECENT, RICH, D2}) at the session's current readiness
  Emulator             <- replaced by our committed measurements: StudyE9b / E9c for episodic
      quality, StudyRH5 / E10b for recall service time, `costs` for GPU-seconds and latency
  SLOs                 <- the recall query's deadline and the remaining GPU-second budget
  dynamic selection    <- `ecollm.select` per query, every epoch

Fairness: rules 1-6 hold; it decides the full episodic and recall action space and relies on the
documented defaults only for session placement and ordering.

CPU only.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent / "reconstructed"))

import costs as C
import profiles as P
from ecollm import SLO, ConfigPoint, explore, select  # noqa: E402
from interface import (Action, Observation, Policy, RecallAction, SessionAction, StreamAction)

REPS = ("RECENT", "D2", "RICH")
# Relative recall quality by representation, from StudyRH4 / E6's committed ordering (D2 = K1 is
# RH4's own finding). These are ORDINAL weights, not accuracies; the card says so.
REP_QUALITY = {"RECENT": 0.6, "D2": 1.0, "RICH": 1.0}
REP_TOKEN_SCALE = {"RECENT": 0.35, "D2": 1.0, "RICH": 1.0}


class ECOLLMAdapted(Policy):
    name = "eco-llm"
    case = "D"
    experiments = ("A-episodic", "B-recall", "C-mixed")
    paper = ("Patidar, Crown, Hsieh, Xu, ECO-LLM: Orchestration for Domain-specific Edge-Cloud "
             "Language Models, arXiv:2507.09003")
    decides = ("episodic_mode", "cadence_s", "frame_count", "recall_decision", "representation")
    defaults_used = ("session_action", "order", "engine_config")

    def __init__(self, setting: str = "measured@25", horizon_ap: float = 0.5,
                 horizon_s: float = 10.0) -> None:
        self.setting, self.horizon_s = setting, float(horizon_s)
        self.rows = P.stream_profile(setting=setting, horizon=horizon_ap, quality="streaming")
        self._ep_points = explore(
            [dict(name=r["name"]) for r in self.rows],
            lambda cfg: self._eval_episodic(cfg["name"]))
        self._by_name = {r["name"]: r for r in self.rows}

    def _eval_episodic(self, name: str):
        r = self._by_name[name] if hasattr(self, "_by_name") else \
            next(x for x in self.rows if x["name"] == name)
        return (r["quality"], r["demand_gpu_s_per_s"] * self.horizon_s, r["lag_s"])

    def decide(self, obs: Observation) -> Action:
        # ---- episodic: one joint configuration selection under the budget SLO
        slo_ep = SLO(max_cost_gpu_s=max(obs.budget_remaining_gpu_s, 0.0)
                     / max(len(obs.streams), 1))
        pick, _feas = select(self._ep_points, slo_ep)
        row = self._by_name[dict(pick.knobs)["name"]]
        acts = []
        for s in obs.streams:
            if row["mode"] == "local" or not s.network.connected:
                acts.append(StreamAction(s.stream_id, "local"))
            else:
                acts.append(StreamAction(s.stream_id, "cloud", row["cadence_s"],
                                         row["frame_count"]))
        # ---- recall: a joint (tier, representation) selection per query under its own SLOs
        rec: List[RecallAction] = []
        left = obs.budget_remaining_gpu_s
        for q in sorted(obs.recall, key=lambda x: x.deadline_s):
            have = {e.representation for e in q.evidence} or {"RECENT"}
            space, tab = [], {}
            for rep in REPS:
                if rep not in have:
                    continue
                tok = max(int(q.readiness_tokens * REP_TOKEN_SCALE[rep]), 1)
                lat = C.recall_ttft_s(tok, q.readiness)
                tab[("cloud", rep)] = (REP_QUALITY[rep], C.recall_gpu_s(tok, q.readiness), lat)
                space.append(dict(tier="cloud", rep=rep))
            # the device option: no cloud cost, lower quality, and it is always feasible
            tab[("device", "RECENT")] = (REP_QUALITY["RECENT"] * 0.5, 0.0, 0.0)
            space.append(dict(tier="device", rep="RECENT"))
            pts = explore(space, lambda cfg: tab[(cfg["tier"], cfg["rep"])])
            slo = SLO(max_latency_s=max(q.slack_s(obs.now_s), 0.0), max_cost_gpu_s=max(left, 0.0))
            c, _f = select(pts, slo)
            k = dict(c.knobs)
            if k["tier"] == "cloud":
                left -= c.cost_gpu_s
                rec.append(RecallAction(q.query_id, "CLOUD", representation=k["rep"]))
            else:
                rec.append(RecallAction(q.query_id, "DEVICE"))
        return Action(streams=acts, recall=rec, order="EDF")
