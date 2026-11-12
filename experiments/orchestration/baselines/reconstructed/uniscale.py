#!/usr/bin/env python3
"""FAITHFUL RECONSTRUCTION of UniScale's LinUCB joint optimisation (arXiv:2605.30898).

Paper: K. Huang, X. Wang, M. Kong, Z. Shi et al., "UniScale: Adaptive Unified Inference Scaling
via Online Joint Optimization of Model Routing and Test-Time Scaling", arXiv:2605.30898
(29 May 2026). The task cites ICML 2026, which could not be verified in an index; the arXiv id IS
verified. No official or author-endorsed code release was found.

Mapping to the paper:
  The paper's framing: existing work treats MODEL ROUTING (switching among model scales) and
  TEST-TIME SCALING (adjusting compute within a fixed model) as "two largely independent
  dimensions"; UniScale unifies them ("Unified Inference Scaling", UIS), "models adaptive UIS as
  a contextual multi-armed bandit problem and learns inference policies via **LinUCB**", with an
  efficiency-aware reward.

  LinUCB        the standard contextual-bandit rule, per arm a:
                  A_a <- A_a + x x^T,  b_a <- b_a + r x,  theta_a = A_a^-1 b_a
                  score_a(x) = theta_a^T x + alpha * sqrt(x^T A_a^-1 x)
                select argmax_a score_a(x); update only the played arm, from its observed reward.
  arms          one arm per (model, compute) pair, which is what makes the optimisation JOINT
                rather than two independent decisions.
  reward        efficiency-aware: quality minus a price on the compute spent.

NOT reconstructed, and why: the paper's specific reward weights and its benchmark suite; the
test-time-scaling mechanism itself (sampling/self-consistency inside a model, which needs
inference). The arms are therefore (model, evidence/cadence) pairs in the adapted version, which
is the closest joint space our action set offers.

CPU only; no GPU, no inference.
"""
from __future__ import annotations

from typing import Dict, Hashable, List, Optional, Sequence, Tuple

import numpy as np


class LinUCB:
    """Contextual bandit over a fixed arm set. One ridge model per arm."""

    def __init__(self, arms: Sequence[Hashable], dim: int, alpha: float = 1.0,
                 lam: float = 1.0) -> None:
        self.arms = list(arms)
        self.dim, self.alpha = int(dim), float(alpha)
        self.A = {a: lam * np.eye(dim) for a in self.arms}
        self.b = {a: np.zeros(dim) for a in self.arms}
        self.n = {a: 0 for a in self.arms}

    def theta(self, a: Hashable) -> np.ndarray:
        return np.linalg.solve(self.A[a], self.b[a])

    def score(self, a: Hashable, x: np.ndarray) -> float:
        Ainv_x = np.linalg.solve(self.A[a], x)
        return float(self.theta(a) @ x + self.alpha * np.sqrt(max(x @ Ainv_x, 0.0)))

    def select(self, x: np.ndarray, feasible: Optional[Sequence[Hashable]] = None) -> Hashable:
        cand = list(feasible) if feasible else self.arms
        if not cand:
            raise ValueError("no feasible arm")
        # an unplayed arm has the largest confidence width, so optimism explores it first
        return max(cand, key=lambda a: self.score(a, x))

    def update(self, a: Hashable, x: np.ndarray, reward: float) -> None:
        self.A[a] = self.A[a] + np.outer(x, x)
        self.b[a] = self.b[a] + float(reward) * x
        self.n[a] += 1


def efficiency_reward(quality: float, compute: float, price: float) -> float:
    """The paper's efficiency-aware reward: quality net of a price on compute."""
    return float(quality) - float(price) * float(compute)
