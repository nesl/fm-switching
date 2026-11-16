#!/usr/bin/env python3
"""Arms (d) and (e) of StudyCTRL1b: the PREDICTABILITY CEILING and the CONTEXT-MODULATED TRICKLE.

CPU only. No GPU, no model server, no inference, and NO scikit-learn: this environment has none
(`metrics._ensure_sklearn_importable` installs a raising stub), so the logistic regression and the
gradient-boosted trees here are written out in numpy, deterministically, with no randomness at
all. They are small by construction, which is also what the brief asks for.

WHAT THE FEATURES CAN AND CANNOT BE, measured before anything was fitted:

  AVAILABLE. The device's own score dynamics: the raw recent values and the controller's own
  self-normalized signals (z, rise, instability in both readings, window IQR and median). Plus
  the committed per-clip Nexar metadata: scene, light and weather.

  NOT AVAILABLE, and this is a gap in the machine rather than in the method. The brief asks for
  "simple image features computed from the frames already on flash" (scene-change magnitude
  between consecutive frames, object count from a small CPU detector). THE FRAME STORE IS NOT ON
  THIS MACHINE: `d14b_prepare.py` reads `/home/pragya/data/dashcam/d14b_frames/small`, and
  `/home/pragya/data` does not exist here. No frame, no scene-change magnitude and no detector
  input; opencv is also absent. Nothing is substituted for them.

  DOES NOT EXIST AT ALL. Nexar ego speed: the committed clip table carries exactly file_name,
  label, scene, light, weather, duration_s and split. There is no speed, heading or GPS column,
  so the brief's "only if it exists in the dataset" resolves to IT DOES NOT.

  DELIBERATELY EXCLUDED. Elapsed time within the clip. Nexar's positive events sit at a
  characteristic position in each clip, so a model given the clock would learn the dataset's
  event placement rather than a signal a deployed device could use. Excluding it is a decision,
  recorded here, not an oversight.

So the ceiling this arm measures is a ceiling on SCORE-DYNAMICS-AND-CONTEXT predictability. It is
NOT a ceiling on what visual features could add, and the report says so wherever the number
appears.

THE TARGET (B8). Per decision instant i on a clip, the per-instant cloud gain in the units the
task metric actually rewards:

    y_i = (cloud score captured at i  -  the device's currently displayed score) x s,
    s = +1 on a positive clip, -1 on a negative clip

The sign is what makes this a UTILITY rather than a score difference: on a positive clip the task
wants the displayed score pushed up, on a negative clip pushed down. StudyCTRL1b's own finding
forces this reading, since an escalation pattern correlated with the label moves a rank metric
through the two tiers' scale offset alone. The models never see the label or the sign; inferring
it from features is exactly the predictability question being asked.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

SCENES = ("Urban", "Highway", "Sub-urban")
LIGHTS = ("Normal", "Twilight", "Dark")
WEATHERS = ("Clear", "Cloudy", "Rain")

SCORE_FEATURES = ("score_last", "score_lag1", "score_lag2", "score_lag3", "z", "rise",
                  "instability_var", "instability_flips", "window_iqr", "window_median",
                  "window_range", "rolling_mean4")
CONTEXT_FEATURES = (tuple("scene_" + s.lower().replace("-", "_") for s in SCENES)
                    + tuple("light_" + s.lower() for s in LIGHTS)
                    + tuple("weather_" + s.lower() for s in WEATHERS))
FEATURES = SCORE_FEATURES + CONTEXT_FEATURES

NOT_AVAILABLE = {
    "image_scene_change_magnitude": "THE FRAME STORE IS ABSENT on this machine "
                                    "(/home/pragya/data/dashcam/d14b_frames does not exist), so "
                                    "no inter-frame feature is computable and none is estimated",
    "object_count": "no frames to detect on, and opencv is not installed either; no detector "
                    "was installed because there is nothing for it to read",
    "ego_speed": "DOES NOT EXIST in the committed Nexar clip table, whose columns are file_name, "
                 "label, scene, light, weather, duration_s and split",
    "elapsed_time_in_clip": "EXCLUDED BY DECISION: Nexar events sit at a characteristic position "
                            "in each clip, so the clock would leak the dataset's event placement "
                            "rather than provide a deployable signal",
}

FLIP_LEVEL = math.log(0.5)


# ---------------------------------------------------------------- features
def _percentile(a: np.ndarray, q: float) -> float:
    return float(np.percentile(a, q))


def clip_features(val: np.ndarray, read: np.ndarray, w_c: float, delta: float, n_c: int,
                  cad_s: float, meta_row: Dict[str, str]) -> np.ndarray:
    """One feature row per DEVICE SAMPLE, from that sample and the ones before it only."""
    n = len(val)
    w_samples = max(int(round(w_c / cad_s)), 2)
    lag = max(int(round(delta / cad_s)), 1)
    X = np.zeros((n, len(FEATURES)), dtype=float)
    for k in range(n):
        lo = max(0, k - w_samples + 1)
        win = val[lo:k + 1]
        iqr = _percentile(win, 75) - _percentile(win, 25) if len(win) >= 2 else 0.0
        med = float(np.median(win)) if len(win) else 0.0
        safe = iqr if iqr > 1e-6 else np.nan
        seg = val[max(0, k - n_c + 1):k + 1]
        b = seg > FLIP_LEVEL
        flips = (float(np.count_nonzero(b[1:] != b[:-1])) / (len(seg) - 1) / 0.5
                 if len(seg) >= 2 else 0.0)
        row = [
            float(val[k]),
            float(val[k - 1]) if k >= 1 else float(val[k]),
            float(val[k - 2]) if k >= 2 else float(val[k]),
            float(val[k - 3]) if k >= 3 else float(val[k]),
            (float(val[k]) - med) / safe if safe == safe else 0.0,
            ((float(val[k]) - float(val[k - lag])) / safe) if (k - lag >= 0 and safe == safe)
            else 0.0,
            (float(np.std(seg, ddof=0)) / safe) if (len(seg) >= 2 and safe == safe) else 0.0,
            flips,
            float(iqr),
            med,
            float(win.max() - win.min()) if len(win) else 0.0,
            float(np.mean(val[max(0, k - 3):k + 1])),
        ]
        row += [1.0 if meta_row.get("scene") == s else 0.0 for s in SCENES]
        row += [1.0 if meta_row.get("light") == s else 0.0 for s in LIGHTS]
        row += [1.0 if meta_row.get("weather") == s else 0.0 for s in WEATHERS]
        X[k] = row
    return X


def clip_target(cloud: np.ndarray, displayed: np.ndarray, read: np.ndarray,
                label: str) -> np.ndarray:
    """B8's signed per-instant gain, read at each device sample's READ index."""
    s = 1.0 if label == "positive" else -1.0
    idx = np.clip(read, 0, len(cloud) - 1)
    return s * (cloud[idx].astype(float) - displayed[idx].astype(float))


# ---------------------------------------------------------------- logistic regression
@dataclass
class Logistic:
    """Full-batch gradient descent on standardized features. No randomness, no library."""
    l2: float = 1e-3
    iters: int = 400
    lr: float = 0.5
    mu: Optional[np.ndarray] = None
    sd: Optional[np.ndarray] = None
    w: Optional[np.ndarray] = None
    b: float = 0.0

    def fit(self, X: np.ndarray, y01: np.ndarray) -> "Logistic":
        self.mu = X.mean(axis=0)
        self.sd = X.std(axis=0)
        self.sd[self.sd < 1e-9] = 1.0
        Z = (X - self.mu) / self.sd
        n, d = Z.shape
        self.w = np.zeros(d)
        self.b = 0.0
        for _ in range(self.iters):
            p = 1.0 / (1.0 + np.exp(-(Z @ self.w + self.b)))
            g = Z.T @ (p - y01) / n + self.l2 * self.w
            gb = float(np.mean(p - y01))
            self.w -= self.lr * g
            self.b -= self.lr * gb
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        Z = (X - self.mu) / self.sd
        return 1.0 / (1.0 + np.exp(-(Z @ self.w + self.b)))

    def importances(self) -> Dict[str, float]:
        return {f: float(abs(c)) for f, c in zip(FEATURES, self.w)}


# ---------------------------------------------------------------- gradient-boosted trees
@dataclass
class Stump:
    feature: int
    threshold: float
    left: float
    right: float
    gain: float

    def apply(self, X: np.ndarray) -> np.ndarray:
        return np.where(X[:, self.feature] <= self.threshold, self.left, self.right)


@dataclass
class GBT:
    """Depth-1 regression trees (stumps) on quantile-binned features, squared loss, fixed
    learning rate. Deterministic: the split search is exhaustive over the bin edges."""
    n_trees: int = 150
    lr: float = 0.05
    n_bins: int = 24
    min_leaf: int = 50
    base: float = 0.0
    trees: List[Stump] = field(default_factory=list)
    edges: Optional[List[np.ndarray]] = None

    def _candidate_edges(self, X: np.ndarray) -> List[np.ndarray]:
        out = []
        qs = np.linspace(0, 100, self.n_bins + 1)[1:-1]
        for j in range(X.shape[1]):
            e = np.unique(np.percentile(X[:, j], qs))
            out.append(e)
        return out

    def fit(self, X: np.ndarray, y: np.ndarray) -> "GBT":
        self.edges = self._candidate_edges(X)
        self.base = float(np.mean(y))
        pred = np.full(len(y), self.base)
        self.trees = []
        for _ in range(self.n_trees):
            r = y - pred
            best: Optional[Stump] = None
            for j in range(X.shape[1]):
                col = X[:, j]
                for thr in self.edges[j]:
                    m = col <= thr
                    nl = int(m.sum())
                    if nl < self.min_leaf or len(y) - nl < self.min_leaf:
                        continue
                    ml, mr = float(r[m].mean()), float(r[~m].mean())
                    gain = nl * ml * ml + (len(y) - nl) * mr * mr
                    if best is None or gain > best.gain:
                        best = Stump(j, float(thr), ml, mr, gain)
            if best is None:
                break
            self.trees.append(best)
            pred = pred + self.lr * best.apply(X)
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        out = np.full(len(X), self.base)
        for t in self.trees:
            out = out + self.lr * t.apply(X)
        return out

    def importances(self) -> Dict[str, float]:
        imp = {f: 0.0 for f in FEATURES}
        for t in self.trees:
            imp[FEATURES[t.feature]] += t.gain
        s = sum(imp.values()) or 1.0
        return {k: v / s for k, v in imp.items()}


def r2(y: np.ndarray, p: np.ndarray) -> float:
    ss = float(((y - y.mean()) ** 2).sum())
    return float(1.0 - ((y - p) ** 2).sum() / ss) if ss > 0 else float("nan")


def auc(y01: np.ndarray, p: np.ndarray) -> float:
    o = np.argsort(p, kind="mergesort")
    yy = y01[o]
    npos, nneg = float(yy.sum()), float(len(yy) - yy.sum())
    if npos == 0 or nneg == 0:
        return float("nan")
    ranks = np.arange(1, len(yy) + 1, dtype=float)
    return float((ranks[yy > 0].sum() - npos * (npos + 1) / 2.0) / (npos * nneg))
