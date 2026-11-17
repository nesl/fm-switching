#!/usr/bin/env python3
"""StudyCTRL1c-calibrated: the PRIMARY metric, StudyE9b's streaming AP, with the paired bootstrap
that the pre-registered decision rule needs. CPU only.

StudyCTRL1b's primary was the challenge mAP, which reads ONE crop per clip; decision D58 makes the
primary trigger metric the STREAMING AP over all decision instants instead. The definition is NOT
re-implemented here: `experiments/orchestration/sim/metrics.streaming_ap` builds StudyE9b's
`ApEngine` and that same class is used directly, so this module adds only (a) the average over
horizons 0.5 / 1.0 / 1.5 s that the brief pre-registers as the primary, and (b) the paired
clip-bootstrap draw, which `ApEngine.full` already computes from ONE shared label-stratified
resample per engine instance, so every arm scored through one engine is paired with every other.

`assert_matches_metrics_module` checks the point values against `metrics.streaming_ap` itself, so
the primary cannot drift from the committed definition.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Sequence

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for p in (HERE, ROOT / "experiments/orchestration/sim",
          ROOT / "experiments/orchestration/baselines", ROOT / "experiments/lib"):
    sys.path.insert(0, str(p))

import metrics as M                                       # noqa: E402

HORIZONS = (0.0, 0.5, 1.0, 1.5)
# two-sided alpha 0.05 at 80 % power: z_{0.975} + z_{0.80}
Z_SUM_80 = 1.959963984540054 + 0.8416212335729143
# the coordinator's re-labelling band: an arm is a real negative only if its CI on the difference
# versus random excludes differences larger than this many points of capture.
RULE2_BAND = 0.10
PRIMARY_HORIZONS = (0.5, 1.0, 1.5)
_ENG: Dict[Any, Any] = {}


def engine(sub, horizons: Sequence[float] = HORIZONS):
    M._ensure_sklearn_importable()
    import study_e9b_dense as B
    key = (tuple(sub["pos"]), tuple(sub["neg"]), tuple(horizons), sub["step"])
    if key not in _ENG:
        _ENG[key] = B.ApEngine(sub["meta"], sub["pos"], sub["neg"], tuple(horizons), sub["step"])
    return _ENG[key]


def primary_point(sub, stream: Dict[str, np.ndarray]) -> float:
    """The pre-registered primary: streaming AP averaged over horizons 0.5, 1.0 and 1.5 s."""
    pt = engine(sub).point(stream)
    return float(np.mean([pt[h] for h in PRIMARY_HORIZONS]))


def arms_full(sub, streams: Dict[str, Dict[str, np.ndarray]]) -> Dict[str, Any]:
    """Every arm through ONE engine instance, so the resamples are shared and paired."""
    eng = engine(sub)
    out: Dict[str, Any] = dict(by_horizon={}, primary={}, boot={})
    for a, s in streams.items():
        full, boot = eng.full(s)
        out["by_horizon"][a] = {str(h): dict(ap=float(full[h]["ap"]), ci=list(full[h]["ci"]))
                                for h in eng.H}
        pb = np.mean([boot[h] for h in PRIMARY_HORIZONS], axis=0)
        out["boot"][a] = pb
        out["primary"][a] = dict(
            ap=float(np.mean([full[h]["ap"] for h in PRIMARY_HORIZONS])),
            ci=[float(np.percentile(pb, 2.5)), float(np.percentile(pb, 97.5))])
    return out


def capture(res: Dict[str, Any], arm: str, dev: str = "device-only",
            cloud: str = "always-cloud") -> Dict[str, Any]:
    """The share of the always-cloud minus device-only STREAMING-AP gap that this arm captures,
    with the CI over the same resamples as the arms themselves."""
    num = res["boot"][arm] - res["boot"][dev]
    den = res["boot"][cloud] - res["boot"][dev]
    ok = np.abs(den) > 1e-12
    f = num[ok] / den[ok]
    pd = res["primary"][cloud]["ap"] - res["primary"][dev]["ap"]
    return dict(value=(float((res["primary"][arm]["ap"] - res["primary"][dev]["ap"]) / pd)
                       if abs(pd) > 1e-12 else None),
                ci=[float(np.percentile(f, 2.5)), float(np.percentile(f, 97.5))]
                if len(f) else None,
                gap_ap=float(pd),
                arm_minus_device=float(res["primary"][arm]["ap"] - res["primary"][dev]["ap"]),
                n_usable_resamples=int(ok.sum()))


def capture_difference(res: Dict[str, Any], arm: str, ref: str = "random-escalation",
                       dev: str = "device-only", cloud: str = "always-cloud") -> Dict[str, Any]:
    """THE PRE-REGISTERED DECISION QUANTITY: the difference in captured fraction between an arm and
    the reference, resample by resample. An arm beats the reference when this CI excludes 0."""
    den = res["boot"][cloud] - res["boot"][dev]
    ok = np.abs(den) > 1e-12
    d = (res["boot"][arm][ok] - res["boot"][ref][ok]) / den[ok]
    lo, hi = float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))
    pd = res["primary"][cloud]["ap"] - res["primary"][dev]["ap"]
    sd = float(np.std(d, ddof=1)) if len(d) > 1 else float("nan")
    return dict(difference=(float((res["primary"][arm]["ap"] - res["primary"][ref]["ap"]) / pd)
                            if abs(pd) > 1e-12 else None),
                ci=[lo, hi], excludes_zero=bool(lo > 0 or hi < 0),
                ap_difference=float(res["primary"][arm]["ap"] - res["primary"][ref]["ap"]),
                n_usable_resamples=int(ok.sum()),
                bootstrap_sd=sd, ci_half_width=float((hi - lo) / 2.0),
                mde_80pct_power_alpha05=float(Z_SUM_80 * sd),
                ci_upper=hi, ci_lower=lo,
                excludes_above_10_points=bool(hi <= RULE2_BAND),
                rule2_power_label=("real negative" if hi <= RULE2_BAND
                                   else "inconclusive (underpowered)"))


def ap_difference(res: Dict[str, Any], a: str, b: str) -> Dict[str, Any]:
    d = res["boot"][a] - res["boot"][b]
    lo, hi = float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))
    return dict(difference=float(res["primary"][a]["ap"] - res["primary"][b]["ap"]),
                ci=[lo, hi], excludes_zero=bool(lo > 0 or hi < 0))


def assert_matches_metrics_module(sub, stream: Dict[str, np.ndarray]) -> Dict[str, Any]:
    """The primary must equal what `metrics.streaming_ap` itself returns, to machine precision."""
    mine = engine(sub).point(stream)
    theirs = M.streaming_ap(sub, stream, horizons=HORIZONS)
    worst = max(abs(float(mine[h]) - float(theirs[float(h)])) for h in mine)
    assert worst < 1e-12, ("the streaming-AP engine used here does not reproduce "
                           "metrics.streaming_ap (worst %.3e)" % worst)
    return dict(worst_abs_difference=float(worst),
                per_horizon={str(h): float(mine[h]) for h in mine},
                note=("the primary is StudyE9b's ApEngine through metrics.streaming_ap's own "
                      "construction; only the average over horizons 0.5 / 1.0 / 1.5 s is added"))
