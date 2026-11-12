#!/usr/bin/env python3
"""FAITHFUL RECONSTRUCTION of StreamScout's progressive evidence cascade (arXiv:2609.00291).

Paper: "StreamScout: Learning When to Look Deeper for Streaming Video Understanding",
arXiv:2609.00291. No official or author-endorsed code release was found.

Mapping to the paper:
  The model is offered "up to three increasingly informative visual views: a glance at recent
  frames, a uniform look-back, [and a query-relevant view]". "At each stage, the model answers
  immediately if the available evidence is sufficient; otherwise, it escalates to the next view."
  The stop-or-escalate policy is then sharpened: "we evaluate every stage of the cascade on an
  auxiliary training set and identify the earliest stage at which the [answer is] adequate", and
  StreamScout-R explores stopping behaviour beyond imitation of that distilled policy.

  STAGES              the three views, in order.
  cascade()           the stop-or-escalate loop: answer at the first stage whose sufficiency
                      signal clears that stage's threshold, else escalate; answer at the last
                      stage regardless, because there is nowhere further to go.
  fit_thresholds()    the distillation step: on a TRAINING set, find for each stage the threshold
                      that stops exactly when the earliest adequate stage has been reached.
                      Implemented as the quantile of the sufficiency signal at the examples whose
                      earliest adequate stage is this one or earlier.

NOT reconstructed, and why: the model's own sufficiency head (it is the VLM's output, which needs
inference); StreamScout-R's reinforcement-learning exploration of the stopping policy; the
query-relevant retrieval mechanism of the third view.

CPU only; no GPU, no inference.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

STAGES = ("recent", "uniform", "query_relevant")


def cascade(signals: Sequence[float], thresholds: Sequence[float]) -> Tuple[int, bool]:
    """The stop-or-escalate loop. `signals[i]` is the sufficiency signal at stage i.

    Returns (stage index answered at, stopped_early). The last stage always answers.
    """
    n = min(len(signals), len(thresholds), len(STAGES))
    for i in range(n):
        if signals[i] >= thresholds[i]:
            return i, i < n - 1
    return max(n - 1, 0), False


def fit_thresholds(train_signals: Sequence[Sequence[float]],
                   earliest_adequate: Sequence[int],
                   n_stages: int = len(STAGES)) -> List[float]:
    """The distillation step, on a TRAINING set only.

    `train_signals[j][i]` is example j's sufficiency signal at stage i; `earliest_adequate[j]` is
    the earliest stage at which that example's answer was adequate. For stage i the threshold is
    set so that examples whose earliest adequate stage is <= i stop at or before i: it is the
    low quantile of their stage-i signal, so the stop fires for them and not for the rest.
    """
    out = []
    for i in range(n_stages):
        stop_here = [s[i] for s, e in zip(train_signals, earliest_adequate)
                     if e <= i and i < len(s)]
        go_on = [s[i] for s, e in zip(train_signals, earliest_adequate)
                 if e > i and i < len(s)]
        if not stop_here:
            out.append(float("inf"))          # nothing is ever adequate this early: never stop
        elif not go_on:
            out.append(-float("inf"))         # everything is adequate here: always stop
        else:
            # the midpoint between the two groups, the standard one-dimensional separator
            out.append(float((np.quantile(stop_here, 0.1) + np.quantile(go_on, 0.9)) / 2.0))
    out[-1] = -float("inf")                   # the last stage must answer
    return out
