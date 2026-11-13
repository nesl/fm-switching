#!/usr/bin/env python3
"""StudySIM1c-scoped - the metrics. CPU only; nothing here runs a model.

Every metric is computed with the function the study that defined it uses, imported rather than
re-implemented, so the two studies cannot drift apart:

  * CHALLENGE mAP (the headline) - StudyE9c's definition, through StudyE9d's `Challenge` class.
  * STREAMING AP - StudyE9b's `ApEngine`, reported under its own name and never mixed with the
    challenge metric (StudyE9c: the two differ by 56x in chance level; signs and orderings
    transfer, absolute levels never).
  * RECALL TIMELY ACCURACY - the committed per-question `correct` flags of StudyB-baselines'
    `b_recall_accuracy.json`, read per category and question-time bin. NOTHING IS ESTIMATED: a
    question answered after its deadline, or not answered at all, counts as not correct, and the
    accuracy of an answer that WAS delivered in time is the committed cell for its
    configuration, category and bin.
  * STARVATION - any query unanswered past 3x its deadline, per class.
  * GPU-s and GPU KV occupancy - from the engine's own counters.

Scores are continuous log P(Yes) throughout. No literal Yes / No appears anywhere.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
for p in (ROOT / "experiments/dashcam", ROOT / "experiments/orchestration/baselines"):
    sys.path.insert(0, str(p))

_CHAL = None


def _ensure_sklearn_importable() -> Optional[str]:
    """StudyE9c imports `sklearn.metrics.average_precision_score` at module level, and no Python
    environment on this host currently has a working scikit-learn (the `fmtk` env's scipy and
    sklearn are built against NumPy 1.x while NumPy 2.2.6 is installed, and no other env has it
    at all). StudyE9c's geometry helpers - `read_clip_meta`, `fake_event_times`, `crop_index` -
    are all this file needs from it, and the AP itself is computed by StudyE9d's `ap_fast`, which
    StudyE9d control (d) verified AGAINST `average_precision_score` on every real cell (0 of 159
    mismatches, worst absolute difference 1.1e-16).

    So a stub is installed ONLY when the real package is missing, and its one function RAISES.
    Nothing can silently substitute a different AP: either `ap_fast` is used, or the run stops.
    """
    try:
        import sklearn.metrics  # noqa: F401
        return None
    except Exception:
        import types
        def _refuse(*_a, **_k):
            raise RuntimeError(
                "scikit-learn is not installed in this environment; StudySIM1c computes AP with "
                "StudyE9d's ap_fast, which StudyE9d control (d) verified against "
                "average_precision_score to 1.1e-16. Nothing may call sklearn's version here.")
        m = types.ModuleType("sklearn")
        mm = types.ModuleType("sklearn.metrics")
        mm.average_precision_score = _refuse
        m.metrics = mm
        sys.modules.setdefault("sklearn", m)
        sys.modules.setdefault("sklearn.metrics", mm)
        return ("scikit-learn absent: a raising stub was installed so StudyE9c's geometry "
                "helpers could be imported; AP is computed by StudyE9d's verified ap_fast")


SKLEARN_NOTE = None


def challenge(ctx):
    """StudyE9c's challenge metric, built once per process from StudyE9d's own class."""
    global _CHAL, SKLEARN_NOTE
    if _CHAL is None:
        SKLEARN_NOTE = _ensure_sklearn_importable()
        import study_e9d_delay as D
        _CHAL = D.Challenge(ctx)
    return _CHAL


def challenge_map(ctx, delivered: Dict[str, np.ndarray]) -> Dict:
    """One crop per clip at horizons 0.5 / 1.0 / 1.5 s, unweighted mean - StudyE9c's mAP."""
    return challenge(ctx).point(delivered)


_APENG = {}


def streaming_ap(ctx, delivered: Dict[str, np.ndarray],
                 horizons: Sequence[float] = (0.0, 0.5, 1.0, 1.5)) -> Dict[float, float]:
    """StudyE9b's dense streaming AP. REPORTED UNDER ITS OWN NAME, never mixed with the mAP."""
    import study_e9b_dense as B
    key = tuple(horizons)
    if key not in _APENG:
        _APENG[key] = B.ApEngine(ctx["meta"], ctx["pos"], ctx["neg"], horizons, ctx["step"])
    return {float(h): float(v) for h, v in _APENG[key].point(delivered).items()}


# ================================================================ recall
_RA = None


def recall_table() -> Dict:
    global _RA
    if _RA is None:
        import json
        f = (ROOT / "results/orchestration/study_b_baselines/b_recall_accuracy.json")
        _RA = json.loads(f.read_text())
    return _RA


def qbin(t: float) -> str:
    return "le120" if t <= 120 else ("120-480" if t <= 480 else "gt480")


# Which committed configuration a decision maps to. The cloud tier is 32BI and the device tier is
# 4BI (fairness rule 1), and the representation the policy chose selects the column.
CLOUD_CONFIG = {"RICH": "32B-RICH", "RECENT": "32B-RECENT", "D2": "32B-D2"}
DEVICE_CONFIG = "4B-D2"     # StudyE7 Job A, the DEVICE PROXY - see the note below


DEVICE_PROXY_NOTE = (
    "A DEVICE recall answer is scored with StudyE7 Job A's committed per-question flags (the 4B "
    "on StudyRH4's D2 input). StudyD15 Part A REJECTED the H100-for-Orin proxy as an EXACT "
    "numerical stand-in, so every device recall number here is valid for ORDERING and "
    "first-order value and is NOT an exact device number. StudyE8 Part D measured 68/68 warm and "
    "27/27 cold agreement on byte-identical inputs and StudyF4 measured 0.972-0.981 per-question "
    "agreement, which is what makes the ordering usable.")


def answer_accuracy(config: str, category: str, question_time_s: float) -> Optional[float]:
    """The committed accuracy cell for this configuration, category and question-time bin, with
    the category-only cell as the fallback when the finer cell is empty or unreliable. Returns
    None when no committed cell exists - never a guess."""
    t = recall_table()
    c = t["configs"].get(config)
    if c is None:
        return None
    cell = c["by_category_bin"].get(f"{category}|{qbin(question_time_s)}")
    if cell and not cell["unreliable"] and cell["accuracy"] is not None:
        return float(cell["accuracy"])
    cell = c["by_category"].get(category)
    if cell and cell["accuracy"] is not None:
        return float(cell["accuracy"])
    return c["accuracy"]


def recall_metrics(answers: List[Dict], deadline_s: float) -> Dict:
    """`answers` is one row per question that arrived, each with:
        category, question_time_s, decision, delivered_s (None if never answered), config.
    Timely accuracy counts a late or missing answer as not correct."""
    n = len(answers)
    if n == 0:
        return dict(n=0, timely_accuracy=None, answered=0, on_time=0, starved=0,
                    accuracy_of_on_time=None, by_decision={})
    on_time, acc_sum, starved, answered = 0, 0.0, 0, 0
    acc_on_time = []
    bydec: Dict[str, Dict] = {}
    for a in answers:
        d = a["decision"]
        row = bydec.setdefault(d, dict(n=0, on_time=0, acc_sum=0.0))
        row["n"] += 1
        if a.get("delivered_s") is not None:
            answered += 1
            late = a["delivered_s"] - a["arrival_s"]
            if late <= deadline_s + 1e-9:
                on_time += 1
                row["on_time"] += 1
                p = answer_accuracy(a["config"], a["category"], a["question_time_s"])
                if p is not None:
                    acc_sum += p
                    row["acc_sum"] += p
                    acc_on_time.append(p)
            if late > 3.0 * deadline_s:
                starved += 1
        else:
            starved += 1
    return dict(n=n, answered=answered, on_time=on_time, starved=starved,
                timely_accuracy=acc_sum / n,
                accuracy_of_on_time=(float(np.mean(acc_on_time)) if acc_on_time else None),
                by_decision={k: dict(n=v["n"], on_time=v["on_time"],
                                     timely_accuracy=v["acc_sum"] / v["n"] if v["n"] else None)
                             for k, v in bydec.items()})


# ================================================================ bootstrap over seeds
def boot_ci(values: Sequence[float], n: int = 2000, seed: int = 0) -> Optional[List[float]]:
    """Percentile CI over SEEDS - the resampling unit for every swept quantity."""
    v = np.asarray([x for x in values if x is not None], dtype=float)
    if v.size < 2:
        return None
    rng = np.random.default_rng(seed)
    b = v[rng.integers(0, v.size, (n, v.size))].mean(axis=1)
    return [float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))]
