#!/usr/bin/env python3
"""RouteLLM (arXiv:2406.18665), ADAPTED behind our policy interface. Case B.

Original: https://github.com/lm-sys/RouteLLM (Apache-2.0), cloned to ~/baselines_src/routellm.

RouteLLM learns a binary router from PREFERENCE data that decides, per query, whether the weak or
the strong model should answer, and calibrates a threshold to hit a target strong-model call
fraction. The paper's routers are: similarity-weighted ranking, MATRIX FACTORISATION, a BERT
classifier and a causal-LLM classifier. The two we can run on CPU without a GPU are the matrix
factorisation and a (linear) classifier; the BERT and causal-LLM routers are not reproduced
(adaptation A3).

Translation (full list in cards/routellm.md):
  weak / strong model   <- device 4B / cloud 32B
  preference label      <- which arm had the higher committed Nexar score at the same moment on
                           the DEVELOPMENT split (a win/loss, which is what RouteLLM's
                           preference data is)
  calibrated threshold  <- RouteLLM's own calibration: pick the threshold whose DEVELOPMENT-split
                           strong-call fraction equals the target budget
  features              <- `devsplit.FEATURES` (the device's own trajectory)

CPU only.
"""
from __future__ import annotations

from typing import List, Optional

import numpy as np

import devsplit as DS
from interface import Action, Observation, Policy, RecallAction, StreamAction
from hybrid_llm_adapted import _features


class _MatrixFactorisation:
    """RouteLLM's matrix-factorisation router, reduced to our two-model case.

    With two models the Bradley-Terry matrix factorisation collapses to a single latent score per
    query: win_prob(strong) = sigmoid(<u(query), v_strong - v_weak>). We learn u(query) as a
    linear map of the query features, which is the paper's "embedding" step with a linear encoder
    in place of its learned one (adaptation A4).
    """

    def __init__(self, dim: int = 6, lr: float = 0.5, iters: int = 800) -> None:
        self.w: Optional[np.ndarray] = None
        self.lr, self.iters = lr, iters

    def fit(self, X: np.ndarray, strong_wins: np.ndarray) -> "_MatrixFactorisation":
        Z = np.hstack([X, np.ones((len(X), 1))])
        Z = (Z - Z.mean(0)) / (Z.std(0) + 1e-9)
        w = np.zeros(Z.shape[1])
        for _ in range(self.iters):
            p = 1.0 / (1.0 + np.exp(-Z @ w))
            g = Z.T @ (p - strong_wins) / len(Z)
            w -= self.lr * g
        self.w, self._mu, self._sd = w, Z.mean(0) * 0, 1.0
        self._fit_mu = np.hstack([X, np.ones((len(X), 1))]).mean(0)
        self._fit_sd = np.hstack([X, np.ones((len(X), 1))]).std(0) + 1e-9
        return self

    def strong_prob(self, X: np.ndarray) -> np.ndarray:
        Z = np.hstack([np.asarray(X, float), np.ones((len(X), 1))])
        Z = (Z - self._fit_mu) / self._fit_sd
        return 1.0 / (1.0 + np.exp(-Z @ self.w))


class RouteLLMAdapted(Policy):
    name = "routellm"
    case = "B"
    experiments = ('A-episodic', 'C-mixed')
    paper = "Ong et al., RouteLLM: Learning to Route LLMs with Preference Data (arXiv:2406.18665)"
    decides = ("episodic_mode", "recall_decision")
    defaults_used = ("cadence_s", "frame_count", "representation", "session_action", "order")

    def __init__(self, router: str = "mf", target_strong_fraction: float = 0.5,
                 cadence_s: float = 0.5, frame_count: int = 1) -> None:
        if router not in ("mf", "classifier"):
            raise ValueError(router)
        self.router_kind = router
        self.cadence_s, self.frame_count = float(cadence_s), int(frame_count)
        ds = DS.router_dataset(device_arm=("4BI", 1), cloud_arm=("32BI", 1))
        strong_wins = (ds.gap > 0).astype(float)      # the preference label
        self.model = _MatrixFactorisation().fit(ds.X, strong_wins)
        p = self.model.strong_prob(ds.X)
        # RouteLLM's calibration: the threshold that sends exactly the target fraction to the
        # strong model ON DEVELOPMENT DATA.
        self.threshold = float(np.quantile(p, 1.0 - float(target_strong_fraction)))
        self.n_dev = int(len(ds.X))
        self.dev_strong_rate = float((p >= self.threshold).mean())

    def decide(self, obs: Observation) -> Action:
        acts = []
        for s in obs.streams:
            x = np.asarray([_features(s)], float)
            strong = bool(self.model.strong_prob(x)[0] >= self.threshold) and s.network.connected
            acts.append(StreamAction(s.stream_id, "cloud" if strong else "local",
                                     self.cadence_s if strong else None,
                                     self.frame_count if strong else None))
        rec = [RecallAction(q.query_id, "CLOUD") for q in obs.recall]
        return Action(streams=acts, recall=rec)
