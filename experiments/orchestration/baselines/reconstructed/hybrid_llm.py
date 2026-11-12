#!/usr/bin/env python3
"""FAITHFUL RECONSTRUCTION of Hybrid LLM's router (ICLR 2024).

Paper: D. Ding, A. Mallick, C. Wang, R. Sim, S. Mukherjee, V. Ruhle, L. V. S. Lakshmanan,
A. H. Awadallah, "Hybrid LLM: Cost-Efficient and Quality-Aware Query Routing", ICLR 2024
(arXiv:2404.14618). No official or author-endorsed code release was found (see the card).

Mapping to the paper:
  quality_gap()      Section 3: H(x) := q(S(x)) - q(L(x)), the difference in response quality
                     between the small and the large model. A random variable, because responses
                     are non-deterministic.
  label_det()        Section 3.1: the hard label y^det = 1[q(S(x)) >= q(L(x))], i.e. a
                     single-sample estimate of Pr[H(x) >= 0]. Trained with Equation (1), the
                     binary cross-entropy loss.
  label_prob()       Section 3.2: the soft label y^prob = E[1[q(S(x)) >= q(L(x))]], estimated in
                     the paper by sampling 10 responses from each model. Lower variance than
                     y^det. Trained with Equation (2).
  transform_labels() Section 3.3: y^trans(t), with t* chosen by Equation (3),
                       t* = argmax_t (1 / N^2) sum_{i,i'} | y^trans_i(t) - y^trans_i'(t) |
                     solved by grid search in the paper, "and we leave more sophisticated
                     approaches for future work". Trained with Equation (4).
  route()            The router outputs p_w(x), an estimate of Pr[H(x) >= 0]; a query goes to the
                     SMALL model when p_w(x) >= threshold. The paper sweeps the threshold to
                     trace the cost-quality curve, so the threshold is a knob, not a constant.

NOT reconstructed, and why: the DeBERTa-v3-large (300M) backbone of Section 4 (it is a
transformer that needs a GPU to train; this reconstruction keeps the paper's LABELS, LOSSES and
ROUTING RULE exactly and lets the caller supply any feature encoder, which is what the adapted
version does with StudyE6 / E12 features); the BART-score quality function q(.) (we substitute a
task-appropriate quality, stated per use).

CPU only; no GPU, no inference.
"""
from __future__ import annotations

from typing import Callable, Optional, Sequence, Tuple

import numpy as np


def quality_gap(q_small: Sequence[float], q_large: Sequence[float]) -> np.ndarray:
    """Section 3: H(x) = q(S(x)) - q(L(x))."""
    return np.asarray(q_small, dtype=float) - np.asarray(q_large, dtype=float)


def label_det(q_small: Sequence[float], q_large: Sequence[float]) -> np.ndarray:
    """Section 3.1: y^det = 1[q(S) >= q(L)], a single-sample estimate of Pr[H >= 0]."""
    return (quality_gap(q_small, q_large) >= 0).astype(float)


def label_prob(q_small_samples: Sequence[Sequence[float]],
               q_large_samples: Sequence[Sequence[float]]) -> np.ndarray:
    """Section 3.2: y^prob = E[1[q(S) >= q(L)]], the sample mean over paired draws."""
    out = []
    for s, l in zip(q_small_samples, q_large_samples):
        s, l = np.asarray(s, float), np.asarray(l, float)
        # all pairs, which is the unbiased estimate of the expectation of the indicator
        out.append(float((s[:, None] >= l[None, :]).mean()))
    return np.asarray(out)


def transform_labels(y_prob: Sequence[float], t: float) -> np.ndarray:
    """Section 3.3: the transformation that spreads the soft labels apart.

    The paper describes a monotone relabelling controlled by a single t and selected by
    Equation (3). We use the paper's stated FORM - push labels away from the middle by a power
    transform about 0.5 - because the paper does not print the closed form; this is recorded as
    reconstruction gap G1 in the card and is the only place a shape had to be chosen.
    """
    y = np.clip(np.asarray(y_prob, float), 0.0, 1.0)
    t = max(float(t), 1e-6)
    up = y >= 0.5
    out = np.empty_like(y)
    # both branches are masked rather than computed everywhere: a negative base under a
    # fractional power is nan, and np.where would evaluate it before selecting.
    out[up] = 0.5 + 0.5 * np.power(2.0 * y[up] - 1.0, t)
    out[~up] = 0.5 - 0.5 * np.power(1.0 - 2.0 * y[~up], t)
    return out


def best_t(y_prob: Sequence[float], grid: Sequence[float] = tuple(np.linspace(0.1, 3.0, 30))
           ) -> float:
    """Equation (3), by grid search as the paper does."""
    best, best_obj = None, -np.inf
    for t in grid:
        yt = transform_labels(y_prob, t)
        obj = float(np.abs(yt[:, None] - yt[None, :]).mean())
        if obj > best_obj:
            best, best_obj = float(t), obj
    assert best is not None
    return best


def bce_loss(y: Sequence[float], p: Sequence[float], eps: float = 1e-9) -> float:
    """Equations (1), (2) and (4) are the same binary cross-entropy with different labels."""
    y, p = np.asarray(y, float), np.clip(np.asarray(p, float), eps, 1 - eps)
    return float(-np.mean(y * np.log(p) + (1.0 - y) * np.log(1.0 - p)))


class HybridRouter:
    """The paper's three routers, differing ONLY in the training label (Sections 3.1-3.3).

    `fit_fn` trains any probabilistic binary classifier on (X, soft label) and returns a callable
    giving p_w(x). The paper uses DeBERTa-v3-large; the backbone is deliberately pluggable here
    so the reconstruction can be exercised on CPU (see the card).
    """

    def __init__(self, variant: str = "det", fit_fn: Optional[Callable] = None) -> None:
        if variant not in ("det", "prob", "trans"):
            raise ValueError(variant)
        self.variant = variant
        self.fit_fn = fit_fn or _default_fit
        self.predict: Optional[Callable[[np.ndarray], np.ndarray]] = None
        self.t_star: Optional[float] = None

    def labels(self, q_small, q_large, q_small_samples=None, q_large_samples=None) -> np.ndarray:
        if self.variant == "det":
            return label_det(q_small, q_large)
        yp = (label_prob(q_small_samples, q_large_samples)
              if q_small_samples is not None else label_det(q_small, q_large))
        if self.variant == "prob":
            return yp
        self.t_star = best_t(yp)
        return transform_labels(yp, self.t_star)

    def fit(self, X, q_small, q_large, q_small_samples=None, q_large_samples=None):
        y = self.labels(q_small, q_large, q_small_samples, q_large_samples)
        self.predict = self.fit_fn(np.asarray(X, float), y)
        return self

    def route(self, X, threshold: float = 0.5) -> np.ndarray:
        """True = send to the SMALL model (the router's score estimates Pr[H(x) >= 0])."""
        assert self.predict is not None, "fit() first"
        return self.predict(np.asarray(X, float)) >= threshold


def _default_fit(X: np.ndarray, y: np.ndarray):
    """A logistic regression on soft labels, by the same BCE objective as Equations (1)/(2)/(4).

    Implemented directly (not sklearn) because sklearn's LogisticRegression takes hard labels
    only, and the paper's rprob / rtrans need SOFT ones - using hard labels there would silently
    collapse all three routers into rdet.
    """
    X = np.hstack([X, np.ones((len(X), 1))])
    w = np.zeros(X.shape[1])
    for _ in range(600):
        p = 1.0 / (1.0 + np.exp(-X @ w))
        g = X.T @ (p - y) / len(X)
        h = (X * (p * (1 - p))[:, None]).T @ X / len(X) + 1e-6 * np.eye(X.shape[1])
        try:
            w = w - np.linalg.solve(h, g)
        except np.linalg.LinAlgError:
            w = w - 0.1 * g
        if np.max(np.abs(g)) < 1e-9:
            break

    def predict(Z: np.ndarray) -> np.ndarray:
        Z = np.hstack([np.asarray(Z, float), np.ones((len(Z), 1))])
        return 1.0 / (1.0 + np.exp(-Z @ w))
    return predict
