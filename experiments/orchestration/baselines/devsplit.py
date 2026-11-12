#!/usr/bin/env python3
"""The DEVELOPMENT split, and the only place baselines may fit a hyperparameter.

StudyB-baselines. CPU only.

StudyD14 / D14b are the 300 VALIDATION clips; StudyD3 ran the DEVELOPMENT clips of the same
`nexar_train_split_seed0.csv` (StudyD14's report, "Different clips: validation here vs
development in D3"). Every router, threshold and bandit prior in this suite is fitted here and
never on StudyD14 / D14b, which is the rule the StudyB row pre-registers.

What D3 gives: for each development clip, each arm (4BI / 32BI x N = 1 / 3 / 9) and each offset
in {-3.0, -2.5, -2.0, -1.5, -1.0, -0.5, 0.0, 0.5, 1.0, 2.0} seconds relative to the event, the
continuous score log P(Yes). It is an OFFSET design, not a dense trace, so a baseline fitted here
sees the shape of the score around the event but not a 0.25-s trajectory - stated in every card
that uses it.
"""
from __future__ import annotations

import gzip
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
D3 = ROOT / "results/dashcam/study_d3_nexar/d3_requests_h100nvl.jsonl.gz"
OFFSETS = (-3.0, -2.5, -2.0, -1.5, -1.0, -0.5, 0.0, 0.5, 1.0, 2.0)
FLOOR = 1e-12


def _score(p_yes: float) -> float:
    return math.log(max(float(p_yes), FLOOR))


def load(arms: Sequence[Tuple[str, int]] = (("4BI", 1), ("32BI", 1), ("32BI", 3))
         ) -> Tuple[Dict[Tuple[str, int], Dict[str, Dict[float, float]]], Dict[str, str]]:
    """-> (scores[arm][clip][offset] = log P(Yes), labels[clip] = "positive" | "negative")."""
    want = set(arms)
    sc: Dict[Tuple[str, int], Dict[str, Dict[float, float]]] = {a: {} for a in want}
    lab: Dict[str, str] = {}
    for ln in gzip.open(D3, "rt"):
        r = json.loads(ln)
        if r.get("grey") or r.get("error"):
            continue
        a = (r["model"], int(r["n"]))
        if a not in want:
            continue
        clip, off = r["file_name"], float(r["offset"])
        sc[a].setdefault(clip, {})[off] = _score(r["p_yes"])
        lab.setdefault(clip, r["label"])
    return sc, lab


@dataclass
class RouterDataset:
    """A development-split dataset in the form the routing baselines want.

    X        features available to a router at the decision moment, from the DEVICE arm only
             (its own score trajectory up to that offset) - strictly causal.
    q_small  the device arm's score at this offset (the "small model" quality proxy).
    q_large  the cloud arm's score at the same offset (the "large model" quality proxy).
    gap      q_large - q_small, i.e. MINUS Hybrid LLM's H(x); a positive gap means the cloud
             helps here.
    """
    X: np.ndarray
    q_small: np.ndarray
    q_large: np.ndarray
    clips: List[str]
    offsets: List[float]
    feature_names: List[str]

    @property
    def gap(self) -> np.ndarray:
        return self.q_large - self.q_small


FEATURES = ["dev_score", "dev_mean_prev", "dev_max_prev", "dev_slope_prev", "dev_std_prev",
            "n_prev"]


def router_dataset(device_arm: Tuple[str, int] = ("4BI", 1),
                   cloud_arm: Tuple[str, int] = ("32BI", 1)) -> RouterDataset:
    """Build the development-split router dataset. Features at offset o use only offsets <= o of
    the DEVICE arm, so nothing from the future or from the cloud enters X."""
    sc, _lab = load(arms=(device_arm, cloud_arm))
    X, qs, ql, clips, offs = [], [], [], [], []
    for clip, per in sorted(sc[device_arm].items()):
        if clip not in sc[cloud_arm]:
            continue
        for o in OFFSETS:
            if o not in per or o not in sc[cloud_arm][clip]:
                continue
            hist = [per[p] for p in OFFSETS if p <= o and p in per]
            if not hist:
                continue
            prev = hist[:-1] if len(hist) > 1 else hist
            v = np.asarray(prev, dtype=float)
            sl = 0.0
            if len(v) >= 2:
                sl = float(np.polyfit(np.arange(len(v), dtype=float), v, 1)[0])
            X.append([hist[-1], float(v.mean()), float(v.max()), sl, float(v.std()),
                      float(len(hist))])
            qs.append(per[o])
            ql.append(sc[cloud_arm][clip][o])
            clips.append(clip)
            offs.append(o)
    return RouterDataset(np.asarray(X, float), np.asarray(qs, float), np.asarray(ql, float),
                         clips, offs, list(FEATURES))
