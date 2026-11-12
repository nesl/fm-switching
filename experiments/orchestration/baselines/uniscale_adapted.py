#!/usr/bin/env python3
"""UniScale (arXiv:2605.30898), ADAPTED behind our policy interface. Case D. P1.

Decision logic = `reconstructed/uniscale.py` (LinUCB, efficiency-aware reward), unchanged.
Mapping in cards/uniscale.md.

  arms      <- the JOINT product the paper insists on: (tier/model, evidence-or-cadence
               compute). For episodic streams that is (local | cloud) x cadence x frame count,
               which is exactly "model routing x test-time compute" in our action space.
  context x <- the device's own delivered-score features (causal), plus load.
  reward    <- `efficiency_reward(quality, compute, price)` with quality from the measured
               profile and compute in charged GPU-seconds, which is the paper's
               efficiency-aware reward with our units.
  online    <- the bandit is updated from the realised reward at the NEXT epoch, so it learns
               online exactly as the paper does; no future value is ever used.

CPU only.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent / "reconstructed"))

import costs as C
import profiles as P
from interface import (Action, Observation, Policy, RecallAction, StreamAction)
from uniscale import LinUCB, efficiency_reward  # noqa: E402


class UniScaleAdapted(Policy):
    name = "uniscale"
    case = "D"
    experiments = ("A-episodic", "C-mixed")
    paper = "Huang et al., UniScale: Adaptive Unified Inference Scaling, arXiv:2605.30898"
    decides = ("episodic_mode", "cadence_s", "frame_count")
    defaults_used = ("recall_decision", "representation", "session_action", "order")

    def __init__(self, setting: str = "measured@25", alpha: float = 0.5,
                 compute_price: float = 0.02, horizon_s: float = 10.0) -> None:
        self.rows = P.stream_profile(setting=setting, horizon=0.5, quality="streaming")
        self.by = {r["name"]: r for r in self.rows}
        self.price, self.horizon_s = float(compute_price), float(horizon_s)
        self.dim = 4
        self.bandit = LinUCB([r["name"] for r in self.rows], dim=self.dim, alpha=float(alpha))
        self._pending: Optional[Tuple[str, np.ndarray]] = None

    def reset(self, seed: int = 0) -> None:
        self.bandit = LinUCB([r["name"] for r in self.rows], dim=self.dim,
                             alpha=self.bandit.alpha)
        self._pending = None

    @staticmethod
    def _context(obs: Observation) -> np.ndarray:
        vs = [s.latest_score() for s in obs.streams]
        vs = [v for v in vs if v is not None]
        mean = float(np.mean(vs)) if vs else -12.0
        mx = float(np.max(vs)) if vs else -12.0
        return np.array([1.0, mean / 12.0, mx / 12.0, obs.cloud.gpu_kv_fraction], dtype=float)

    def decide(self, obs: Observation) -> Action:
        x = self._context(obs)
        # online update from the PREVIOUS epoch's realised reward (never a future value)
        if self._pending is not None:
            arm, xprev = self._pending
            r = self.by[arm]
            self.bandit.update(arm, xprev,
                               efficiency_reward(r["quality"],
                                                 r["demand_gpu_s_per_s"] * self.horizon_s,
                                                 self.price))
        # restrict to arms the budget can actually afford: a feasibility filter, not a new rule
        feasible = [r["name"] for r in self.rows
                    if r["demand_gpu_s_per_s"] * max(len(obs.streams), 1) * C.GRID_STEP_S
                    <= max(obs.budget_remaining_gpu_s, 0.0)] or [self.rows[0]["name"]]
        arm = self.bandit.select(x, feasible=feasible)
        self._pending = (arm, x)
        row = self.by[arm]
        acts = []
        for s in obs.streams:
            if row["mode"] == "local" or not s.network.connected:
                acts.append(StreamAction(s.stream_id, "local"))
            else:
                acts.append(StreamAction(s.stream_id, "cloud", row["cadence_s"],
                                         row["frame_count"]))
        return Action(streams=acts,
                      recall=[RecallAction(q.query_id, "CLOUD") for q in obs.recall])
