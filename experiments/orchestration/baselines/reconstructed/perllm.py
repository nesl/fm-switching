#!/usr/bin/env python3
"""FAITHFUL RECONSTRUCTION of PerLLM's CS-UCB scheduler (arXiv:2405.14636).

Paper: Z. Yang, Y. Yang, C. Zhao, Q. Guo, W. He, W. Ji, "PerLLM: Personalized Inference
Scheduling with Edge-Cloud Collaboration for Diverse LLM Services". No official or
author-endorsed code release was found (see the card).

Mapping to the paper:
  super arm S_t        Section 3.2: one super arm IS a complete service-and-resource allocation
                       scheme (which service runs on which server). The problem is a
                       combinatorial multi-armed bandit (Section 1, Section 3.1).
  reward R(S)          Equation (4):
                         R(S) = -(1/T) sum_t E[w_tran E^t_tran + w_infer E^t_infer
                                              + w_idle E^t_idle] + lambda * f_t(y)
                       i.e. the negative weighted energy of transmission, inference and idle,
                       plus lambda times the constraint-satisfaction function.
  f(y)                 Section 3.2: "The scheme y satisfies all constraints if f(y) >= 0,
                       otherwise it violates at least one constraint." Added INTO the reward so
                       that a violating scheme is penalised rather than discarded.
  ucb()                Figure (CS-UCB block) / Section 3.2:
                         UCB(a, t) = R(a) + c * sqrt(ln t / N(a, t)) + P(t)
  schedule()           Algorithm 1: play a super arm; if the processing-time constraint and the
                       computing-power and bandwidth budgets all hold, accept it as (X*, S*);
                       otherwise update the regret and the arm and continue.
  constraints          Section 3.1 C1 (per-server processing-time requirement D_{i,t}), plus
                       sum_i C_it <= C^t_max (computing power) and sum_i B_it <= B^t_max
                       (bandwidth).

NOT reconstructed, and why: the approximation coefficients alpha, beta of Section 3.2 enter only
the regret ANALYSIS, not the decision rule, so they are accepted as inputs and not used to steer
the search; the paper's specific energy model constants (its Table 1 hardware) are replaced by
our measured costs in the adapted version, which is the point of the adaptation.

CPU only; no GPU, no inference.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Dict, Hashable, List, Optional, Sequence, Tuple


@dataclass
class Arm:
    """One super arm: a complete assignment, with its running reward estimate."""
    key: Hashable
    n: int = 0
    mean_reward: float = 0.0

    def update(self, r: float) -> None:
        self.n += 1
        self.mean_reward += (r - self.mean_reward) / self.n


def constraint_satisfaction(values: Sequence[float], limits: Sequence[float]) -> float:
    """Section 3.2's f(y): >= 0 iff every constraint holds. The margin is the worst slack, so a
    scheme that violates one constraint badly is penalised more than one that just misses."""
    if not values:
        return 0.0
    return min(lim - v for v, lim in zip(values, limits))


def reward(energy_tran: float, energy_infer: float, energy_idle: float,
           w_tran: float, w_infer: float, w_idle: float,
           f_y: float, lam: float) -> float:
    """Equation (4), for a single step (the paper's time average over T steps is taken by the
    caller across epochs)."""
    return -(w_tran * energy_tran + w_infer * energy_infer + w_idle * energy_idle) + lam * f_y


def ucb(arm: Arm, t: int, c: float = 1.0, p_t: float = 0.0) -> float:
    """UCB(a, t) = R(a) + c * sqrt(ln t / N(a, t)) + P(t). An unplayed arm is infinitely
    attractive, which is the standard optimism-under-uncertainty initialisation."""
    if arm.n == 0:
        return float("inf")
    return arm.mean_reward + c * math.sqrt(math.log(max(t, 2)) / arm.n) + p_t


class CSUCB:
    """Algorithm 1. `candidates()` enumerates the feasible super arms at this epoch;
    `evaluate(key)` returns (reward, constraint_values, constraint_limits) for one of them."""

    def __init__(self, c: float = 1.0, lam: float = 1.0) -> None:
        self.c, self.lam = float(c), float(lam)
        self.arms: Dict[Hashable, Arm] = {}
        self.t = 0
        self.regret = 0.0
        self.rejected = 0

    def _arm(self, key: Hashable) -> Arm:
        if key not in self.arms:
            self.arms[key] = Arm(key)
        return self.arms[key]

    def schedule(self, candidates: Sequence[Hashable],
                 evaluate: Callable[[Hashable], Tuple[float, Sequence[float], Sequence[float]]],
                 p_t: float = 0.0) -> Optional[Hashable]:
        """One pass of Algorithm 1: play super arms in UCB order and accept the first that
        satisfies every constraint; otherwise update the regret and keep going."""
        if not candidates:
            return None
        self.t += 1
        order = sorted(candidates, key=lambda k: -ucb(self._arm(k), self.t, self.c, p_t))
        best_r = -float("inf")
        for key in order:
            r, vals, lims = evaluate(key)
            f_y = constraint_satisfaction(vals, lims)
            self._arm(key).update(r)
            best_r = max(best_r, r)
            if f_y >= 0.0:                      # Algorithm 1, step 5: constraints hold -> accept
                return key
            self.rejected += 1                  # Algorithm 1, step 8: update regret and continue
        self.regret += max(best_r, 0.0)
        return order[0]                         # nothing feasible: return the most promising arm
