#!/usr/bin/env python3
"""FAITHFUL RECONSTRUCTION of VideoStorm's resource allocation (NSDI 2017).

Paper: H. Zhang, G. Ananthanarayanan, P. Bodik, M. Philipose, P. Bahl, M. J. Freedman,
"Live Video Analytics at Scale with Approximation and Delay-Tolerance", NSDI 2017, pp. 377-392.
No official or author-endorsed code release was found (see the card), so this is a reconstruction
from the paper text, in the paper's OWN abstract setting: queries with resource-quality profiles,
an allocation `a_k`, a configuration `c_k`, and accumulating lag.

Mapping to the paper, step by step:

  utility()            Equation (1), Section 6.1:
                         U(Q, L) = U^B + alpha^Q * (Q - Q^M)+ - alpha^L * (L - L^M)+
                       with (x)+ the positive part. U^B is the baseline utility for meeting both
                       goals; there is "no bonus for lag being below L^M" (Section 6.1), which is
                       why the lag term is one-sided.
  predict_lag()        Equation (2), Section 6.2.1:
                         L_{k,t+T}(a_k, c_k) = L_{k,t} + T - T * a_k / D_k(c_k)
                       and Section 6.4's correction for a wrong profile, with the running average
                       mis-estimation mu = R_k / D_k(c):
                         L_{k,t+T} = L_{k,t} + T - T * a_k / D_k(c_k) * (1 / mu)
  allocate_maxsum()    Equation (3), Section 6.2.2 ("Maximizing sum of utilities"): a knapsack
                       variant. The paper's greedy approximation prefers the query with the
                       largest utility gain per unit resource and proceeds in increments of
                       "a small Delta (say, 1% of a core)", considering all configurations
                       c_i in P_i at each step, until resources run out or every query already
                       has its best configuration.
  allocate_maxmin()    Equation (4), Section 6.2.2 ("Maximizing minimum utility"): start from
                       a_k = 0; each step pick i = argmin_k U_k, give it Delta, then set its
                       configuration to argmax_c U_i(Q_i(c), L_{i,t+T}); repeat.
  placement_score()    Section 6.3: the mean of three scores in [0, 1] - utilization p (a
                       weighted dot product of the machine's available resources and the query's
                       demand), load balancing b = 1 - (M + D) / M_max, and lag spreading l (the
                       average L^M after placing q on m). A query migrates only if the score
                       improves by more than tau.

NOT reconstructed, and why: Section 5's greedy profile EXPLORATION (it searches a configuration
space by running the query, which needs inference); Section 6.4's multi-transform DAG allocation
(our queries are single-transform); the cluster-wide implementation details of Section 7.

CPU only; no GPU, no inference, no model.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple


@dataclass
class Config:
    """One point of a query's resource-quality profile P_k."""
    name: str
    quality: float          # Q(c) in [0, 1]
    demand: float           # D_k(c), resource units needed to keep up with the stream


@dataclass
class Query:
    """A VideoStorm query: its profile, its utility parameters and its current lag."""
    qid: str
    profile: Sequence[Config]
    u_base: float = 1.0      # U^B
    alpha_q: float = 1.0     # alpha^Q
    alpha_min_q: float = 0.0  # Q^M
    alpha_l: float = 1.0     # alpha^L, in 1/second (Section 6.1 footnote 2)
    lag_max_s: float = 0.0   # L^M
    lag_s: float = 0.0       # L_{k,t}
    mu: float = 1.0          # Section 6.4 running average R_k / D_k(c)
    alloc: float = 0.0       # a_k
    config: Optional[Config] = None


def utility(q: Query, quality: float, lag_s: float) -> float:
    """Equation (1), Section 6.1."""
    return (q.u_base
            + q.alpha_q * max(quality - q.alpha_min_q, 0.0)
            - q.alpha_l * max(lag_s - q.lag_max_s, 0.0))


def predict_lag(q: Query, alloc: float, cfg: Config, horizon_s: float) -> float:
    """Equation (2), Section 6.2.1, with Section 6.4's mis-estimation correction."""
    if cfg.demand <= 0:
        return max(q.lag_s - horizon_s, 0.0)
    drained = horizon_s * (alloc / cfg.demand) * (1.0 / max(q.mu, 1e-9))
    return max(q.lag_s + horizon_s - drained, 0.0)


def _best_config(q: Query, alloc: float, horizon_s: float) -> Tuple[Config, float]:
    """argmax_{c in P_k} U_k(Q_k(c), L_{k,t+T}(a_k, c)) - the inner step of both heuristics."""
    best, best_u = None, -float("inf")
    for c in q.profile:
        u = utility(q, c.quality, predict_lag(q, alloc, c, horizon_s))
        if u > best_u:
            best, best_u = c, u
    assert best is not None
    return best, best_u


def allocate_maxsum(queries: Sequence[Query], capacity: float, horizon_s: float,
                    delta: float = 0.01) -> Dict[str, Tuple[float, Config]]:
    """Equation (3) / Section 6.2.2. Greedy by utility gain per unit resource (u_k / a_k)."""
    alloc = {q.qid: 0.0 for q in queries}
    cfg = {q.qid: _best_config(q, 0.0, horizon_s)[0] for q in queries}
    cur = {q.qid: _best_config(q, 0.0, horizon_s)[1] for q in queries}
    spent = 0.0
    by_id = {q.qid: q for q in queries}
    while spent + delta <= capacity + 1e-12:
        best_id, best_gain, best_cfg, best_u = None, 0.0, None, None
        for q in queries:
            a = alloc[q.qid] + delta
            c, u = _best_config(q, a, horizon_s)
            gain = (u - cur[q.qid]) / delta       # utility gain normalised by resource spent
            if best_id is None or gain > best_gain:
                best_id, best_gain, best_cfg, best_u = q.qid, gain, c, u
        if best_id is None or best_gain <= 0.0:
            break                                  # every query already at its best configuration
        alloc[best_id] += delta
        cfg[best_id], cur[best_id] = best_cfg, best_u
        spent += delta
    return {qid: (alloc[qid], cfg[qid]) for qid in alloc}


def allocate_maxmin(queries: Sequence[Query], capacity: float, horizon_s: float,
                    delta: float = 0.01) -> Dict[str, Tuple[float, Config]]:
    """Equation (4) / Section 6.2.2. Repeatedly feed the worst query."""
    alloc = {q.qid: 0.0 for q in queries}
    cfg: Dict[str, Config] = {}
    cur: Dict[str, float] = {}
    for q in queries:
        c, u = _best_config(q, 0.0, horizon_s)
        cfg[q.qid], cur[q.qid] = c, u
    spent = 0.0
    while spent + delta <= capacity + 1e-12 and queries:
        worst = min(queries, key=lambda q: cur[q.qid])
        a = alloc[worst.qid] + delta
        c, u = _best_config(worst, a, horizon_s)
        if u <= cur[worst.qid] and alloc[worst.qid] > 0:
            break                                  # no further improvement available
        alloc[worst.qid] = a
        cfg[worst.qid], cur[worst.qid] = c, u
        spent += delta
    return {qid: (alloc[qid], cfg[qid]) for qid in alloc}


def placement_score(machine_avail: Sequence[float], machine_util: float, machine_util_max: float,
                    query_demand: Sequence[float], machine_mean_lag_max: float,
                    weights: Optional[Sequence[float]] = None) -> float:
    """Section 6.3: the mean of utilization p, load balancing b and lag spreading l."""
    w = list(weights or [1.0] * len(machine_avail))
    num = sum(wi * ai * di for wi, ai, di in zip(w, machine_avail, query_demand))
    na = sum((wi * ai) ** 2 for wi, ai in zip(w, machine_avail)) ** 0.5
    nd = sum((wi * di) ** 2 for wi, di in zip(w, query_demand)) ** 0.5
    p = (num / (na * nd)) if na > 0 and nd > 0 else 0.0
    d_total = sum(query_demand)
    b = 1.0 - (machine_util + d_total) / machine_util_max if machine_util_max > 0 else 0.0
    l = machine_mean_lag_max
    return (max(min(p, 1.0), 0.0) + max(min(b, 1.0), 0.0) + max(min(l, 1.0), 0.0)) / 3.0
