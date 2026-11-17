#!/usr/bin/env python3
"""StudyCTRL1c-calibrated: the PER-TIER CALIBRATION that StudyCTRL1b's decision D57 requires.

CPU only; no GPU, no model server, no inference, and no scikit-learn. Every score is a committed
StudyD14b trace. Nothing in StudyCTRL1b is edited; this module is imported by
`ctrl1c_crossfit.py` and adds one object, a per-tier monotone map.

WHY. StudyCTRL1b measured that the two tiers' raw log P(Yes) are not on one scale (the 32B runs a
median -5.125 log units below the 4B), so any arm that mixes tiers is penalized by the offset
alone, which is why its positives-only oracle scored BELOW device-only. A per-tier calibration
removes the offset: after it, both tiers' values are estimates of the same quantity, the
probability that this clip contains the event, so a rank metric over a mixed stream is no longer
reading the tier identity.

THE PRIMARY MAP IS PLATT SCALING and it is stored, and applied, as the CALIBRATED LOG-ODDS

    g(s) = a * s + b,      p(s) = 1 / (1 + exp(-g(s)))

which is the same fit written in the form that is AFFINE in the raw score. Two properties follow
and both are used:

  (i) every metric in this study is a RANK metric over the pooled delivered values, and sigmoid is
      one common increasing function applied to both tiers' calibrated log-odds, so AP is
      identical whether the log-odds or the probability is delivered. The log-odds form is stored
      because it is the one a policy can add to a utility.

  (ii) the device controller's signals (z, rise, instability) are all divided by the window IQR,
      so they are invariant to an affine rescaling with a > 0. The DEVICE FILTER's episodes are
      therefore bit-identical to StudyCTRL1b's under the primary calibration, which is what makes
      the comparison in this row a comparison of the METRIC and the SCALE and not of a different
      controller. The isotonic sensitivity has no such property and is reported separately.

If a fitted a <= 0 the map would REVERSE the within-tier order and the sanity check that
always-cloud and device-only are unchanged would fail; `fit_platt` records the sign and the
caller asserts it.

THE LABEL. The primary fit uses the CLIP-LEVEL label (does this clip contain the event) at every
decision instant on the 0.5-s cadence, which is the brief's pre-registered choice and is also the
label the challenge metric and the streaming AP rank against. The instant-level sensitivity marks
only the instants within 1.5 s before the event of a positive clip, which is a different estimand
(is an event imminent) and is reported as a sensitivity, never as the primary.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for p in (HERE, ROOT / "experiments/orchestration/sim",
          ROOT / "experiments/orchestration/baselines", ROOT / "experiments/lib"):
    sys.path.insert(0, str(p))

import ctrl1_controller as C                              # noqa: E402

TIERS = (C.DEVICE, C.CLOUD)
TIER_NAME = {C.DEVICE: "device_4BI_N1", C.CLOUD: "cloud_32BI_N1"}
INSTANT_LABEL_LEAD_S = 1.5
KINDS = ("platt", "isotonic", "platt_instant")
KIND_D3DEV = "d3dev"
# the three KINDS above are fitted ON the evaluation clips and must therefore be cross-fitted;
# d3dev is fitted on a DISJOINT split and is one map per tier for every clip and every fold.
ALL_KINDS = KINDS + (KIND_D3DEV,)


def tier_key(tier: Tuple[str, int]) -> str:
    return TIER_NAME[tier]


# ---------------------------------------------------------------- the fitting sample
def fit_sample(ctx, sched, clips: Sequence[str], tier: Tuple[str, int], instant_label: bool
               ) -> Tuple[np.ndarray, np.ndarray]:
    """One row per DECISION INSTANT of each clip, on the 0.5-s cadence, with the raw tier score
    captured at that instant and its label."""
    ts = sched["call_cadence_steps"]
    xs, ys = [], []
    for c in clips:
        G = ctx["meta"][c]["G"]
        idx = np.arange(0, G, ts)
        xs.append(ctx["arrs"][tier][c][idx])
        pos = ctx["meta"][c]["label"] == "positive"
        if not instant_label:
            ys.append(np.full(len(idx), 1.0 if pos else 0.0))
            continue
        if not pos or ctx["meta"][c]["event"] is None:
            ys.append(np.zeros(len(idx)))
            continue
        t = C.T0 + idx * C.STEP
        ev = float(ctx["meta"][c]["event"])
        ys.append(((t >= ev - INSTANT_LABEL_LEAD_S) & (t <= ev)).astype(float))
    return np.concatenate(xs), np.concatenate(ys)


# ---------------------------------------------------------------- Platt
def fit_platt(s: np.ndarray, y: np.ndarray, iters: int = 200) -> Dict[str, Any]:
    """1-D logistic regression by Newton / IRLS on the raw score, with a tiny ridge on the slope
    for numerical safety only (1e-9, which moves the fit far below the reported precision)."""
    x = np.asarray(s, dtype=float)
    t = np.asarray(y, dtype=float)
    mu, sd = float(x.mean()), float(x.std())
    sd = sd if sd > 1e-12 else 1.0
    z = (x - mu) / sd
    w = np.zeros(2)
    w[1] = math.log(max(t.mean(), 1e-6) / max(1.0 - t.mean(), 1e-6))
    X = np.column_stack([z, np.ones_like(z)])
    ll_prev = -np.inf
    for _ in range(iters):
        e = X @ w
        p = 1.0 / (1.0 + np.exp(-e))
        g = X.T @ (p - t) + 1e-9 * w
        W = np.clip(p * (1.0 - p), 1e-12, None)
        H = X.T @ (X * W[:, None]) + 1e-9 * np.eye(2)
        step = np.linalg.solve(H, g)
        w = w - step
        ll = float(np.sum(t * np.log(np.clip(p, 1e-15, 1)) +
                          (1 - t) * np.log(np.clip(1 - p, 1e-15, 1))))
        if abs(ll - ll_prev) < 1e-10:
            break
        ll_prev = ll
    a = float(w[0] / sd)
    b = float(w[1] - w[0] * mu / sd)
    return dict(kind="platt", a=a, b=b, n=int(x.size), n_positive=int(t.sum()),
                base_rate=float(t.mean()), monotone_increasing=bool(a > 0),
                form="log_odds = a * raw_score + b; p = 1 / (1 + exp(-log_odds))",
                log_likelihood=ll_prev)


# ---------------------------------------------------------------- isotonic
def fit_isotonic(s: np.ndarray, y: np.ndarray) -> Dict[str, Any]:
    """Pool-adjacent-violators, non-decreasing in the raw score, on the unique raw values."""
    x = np.asarray(s, dtype=float)
    t = np.asarray(y, dtype=float)
    o = np.argsort(x, kind="stable")
    xs, ts = x[o], t[o]
    ux, inv = np.unique(xs, return_inverse=True)
    wsum = np.bincount(inv, weights=np.ones_like(ts), minlength=len(ux))
    ysum = np.bincount(inv, weights=ts, minlength=len(ux))
    vals = list(ysum / wsum)
    wts = list(wsum)
    xsl = list(ux)
    i = 0
    while i < len(vals) - 1:
        if vals[i] <= vals[i + 1] + 1e-15:
            i += 1
            continue
        w = wts[i] + wts[i + 1]
        v = (vals[i] * wts[i] + vals[i + 1] * wts[i + 1]) / w
        vals[i:i + 2] = [v]
        wts[i:i + 2] = [w]
        xsl[i:i + 2] = [xsl[i + 1]]
        if i > 0:
            i -= 1
    return dict(kind="isotonic", x=[float(v) for v in xsl], y=[float(v) for v in vals],
                n=int(x.size), n_positive=int(t.sum()), base_rate=float(t.mean()),
                n_blocks=len(vals), monotone_increasing=True,
                form="p = y[searchsorted(x, raw_score, side='left')], clipped to the end blocks")


# ---------------------------------------------------------------- application
def apply_map(m: Dict[str, Any], s: np.ndarray) -> np.ndarray:
    if m["kind"] == "isotonic":
        xk = np.asarray(m["x"], dtype=float)
        yk = np.asarray(m["y"], dtype=float)
        j = np.searchsorted(xk, np.asarray(s, dtype=float), side="left")
        return yk[np.clip(j, 0, len(yk) - 1)]
    return float(m["a"]) * np.asarray(s, dtype=float) + float(m["b"])


def prob_of(m: Dict[str, Any], s: np.ndarray) -> np.ndarray:
    v = apply_map(m, s)
    if m["kind"] == "isotonic":
        return v
    return 1.0 / (1.0 + np.exp(-v))


def fit_maps(ctx, sched, clips: Sequence[str], kind: str) -> Dict[str, Dict[str, Any]]:
    out = {}
    for tier in TIERS:
        s, y = fit_sample(ctx, sched, clips, tier, instant_label=(kind == "platt_instant"))
        m = fit_isotonic(s, y) if kind == "isotonic" else fit_platt(s, y)
        m["tier"] = tier_key(tier)
        m["kind_requested"] = kind
        m["label"] = ("instant within %.1f s before the event in a positive clip"
                      % INSTANT_LABEL_LEAD_S) if kind == "platt_instant" else \
                     "clip-level: does the clip contain the event"
        m["n_clips_fitted_on"] = len(clips)
        m["raw_percentiles"] = dict(p05=float(np.percentile(s, 5)),
                                    p50=float(np.percentile(s, 50)),
                                    p95=float(np.percentile(s, 95)))
        out[tier_key(tier)] = m
    return out


def calibrated_arrs(ctx, maps: Dict[str, Dict[str, Any]]) -> Dict[Any, Dict[str, np.ndarray]]:
    """A copy of ctx['arrs'] whose two scored tiers carry the calibrated value. Every other arm is
    passed through untouched, so StudyFRAMES1-style arms are unaffected."""
    arrs = dict(ctx["arrs"])
    for tier in TIERS:
        m = maps[tier_key(tier)]
        arrs[tier] = {c: apply_map(m, v) for c, v in ctx["arrs"][tier].items()}
    return arrs


def calibrated_ctx(ctx, maps: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    out = dict(ctx)
    out["arrs"] = calibrated_arrs(ctx, maps)
    return out


def crossfit_ctx(ctx, maps_by_fold: Dict[str, Dict[str, Dict[str, Any]]],
                 assignment: Dict[str, int]) -> Dict[str, Any]:
    """Every clip calibrated by the map of ITS OWN fold, which was fitted on the other four. This
    is the object every pooled number is computed on."""
    arrs = dict(ctx["arrs"])
    for tier in TIERS:
        per = {}
        for c, v in ctx["arrs"][tier].items():
            m = maps_by_fold[str(assignment[c])][tier_key(tier)]
            per[c] = apply_map(m, v)
        arrs[tier] = per
    out = dict(ctx)
    out["arrs"] = arrs
    return out


# ---------------------------------------------------------------- reliability
def reliability(ctx, sched, maps: Dict[str, Dict[str, Any]], clips: Sequence[str],
                instant_label: bool = False, n_bins: int = 10) -> Dict[str, Any]:
    """The calibration curve on HELD-OUT instants: equal-count bins of the calibrated probability
    against the observed frequency, with the Brier score and the expected calibration error."""
    out = {}
    for tier in TIERS:
        s, y = fit_sample(ctx, sched, clips, tier, instant_label)
        p = prob_of(maps[tier_key(tier)], s)
        q = np.quantile(p, np.linspace(0, 1, n_bins + 1))
        q[0] -= 1e-12
        q[-1] += 1e-12
        j = np.clip(np.searchsorted(q, p, side="left") - 1, 0, n_bins - 1)
        bins, ece = [], 0.0
        for k in range(n_bins):
            m = j == k
            if not m.any():
                continue
            mp, my = float(p[m].mean()), float(y[m].mean())
            bins.append(dict(bin=k, n=int(m.sum()), mean_predicted=mp, observed_frequency=my))
            ece += (m.sum() / len(p)) * abs(mp - my)
        out[tier_key(tier)] = dict(
            n=int(len(p)), base_rate=float(y.mean()), mean_predicted=float(p.mean()),
            brier=float(np.mean((p - y) ** 2)),
            brier_of_base_rate=float(np.mean((y.mean() - y) ** 2)),
            expected_calibration_error=float(ece), bins=bins)
    return out


# ---------------------------------------------------------------- the StudyD3 DEV calibration
D3_TRACE = ROOT / "results/dashcam/study_d3_nexar/d3_requests_h100nvl.jsonl.gz"
SPLIT_CSV = ROOT / "results/dashcam/study_d2_nexar/nexar_train_split_seed0.csv"
D3_MODEL_OF_TIER = {C.DEVICE: "4BI", C.CLOUD: "32BI"}


def d3_dev_sample(tier: Tuple[str, int]) -> Tuple[np.ndarray, np.ndarray, Dict[str, Any]]:
    """(score, clip-level label) for one tier on the StudyD3 DEV clips, which are DISJOINT from the
    300 StudyD14b evaluation clips.

    WHY THIS EXISTS. A calibration fitted on the evaluation clips has to be cross-fitted to stay
    honest, and five per-fold maps are five different monotone functions, which a metric that ranks
    ACROSS clips cannot absorb. StudyD3 scored the Nexar DEV side with BOTH tiers at N = 1, so one
    map per tier can be fitted there and used for every clip, every fold, every decision and every
    delivered score. Nothing about the 300 clips enters it, so no cross-fitting is needed and the
    per-tier monotone invariance holds exactly.

    THE SCORE IS THE SAME OBJECT. StudyD14b's committed `score` is log(p_yes) to 0.0 over all
    168,056 rows, so log(p_yes) is taken here and the two studies are on one definition.

    WHAT IS DIFFERENT ABOUT THE SAMPLE, declared and not hidden: StudyD3 sampled EVENT-ANCHORED
    offsets, ten per clip at -3.0, -2.5, -2.0, -1.5, -1.0, -0.5, 0.0, +0.5, +1.0 and +2.0 s
    relative to the event (a pseudo-event on negative clips), so the SPACING is 0.5 s, the same as
    the decision cadence, but the WINDOW is a 5-s neighbourhood of the event rather than the whole
    clip. The calibration therefore sees the score distribution near events, not the clip-wide one.
    """
    import csv
    import gzip
    import json as _json
    want = D3_MODEL_OF_TIER[tier]
    val = {r["file_name"] for r in csv.DictReader(SPLIT_CSV.open())
           if r["split"] == "val"}
    xs, ys, clips, offs = [], [], set(), set()
    for ln in gzip.open(D3_TRACE, "rt"):
        r = _json.loads(ln)
        if r.get("grey") or r["file_name"] is None or r["n"] != 1 or r["model"] != want:
            continue
        if r["file_name"] in val:                 # cannot happen; asserted below
            raise AssertionError("a StudyD3 row landed on an evaluation clip: %s" % r["file_name"])
        xs.append(math.log(r["p_yes"]))
        ys.append(1.0 if r["label"] == "positive" else 0.0)
        clips.add(r["file_name"])
        offs.add(float(r["offset"]))
    meta = dict(n_rows=len(xs), n_clips=len(clips), n_positive_rows=int(sum(ys)),
                offsets_s=sorted(offs), offset_spacing_s=0.5,
                overlap_with_evaluation_clips=len(clips & val),
                source=str(D3_TRACE.relative_to(ROOT)),
                split_source=str(SPLIT_CSV.relative_to(ROOT)),
                tier_model=want, n_frames=1,
                score_definition="log(p_yes), identical to StudyD14b's committed `score`")
    assert meta["overlap_with_evaluation_clips"] == 0
    return np.asarray(xs), np.asarray(ys), meta


def fit_maps_d3dev() -> Dict[str, Dict[str, Any]]:
    """ONE Platt map per tier, fitted on the StudyD3 DEV clips, for BOTH the trigger decisions and
    the scoring of the delivered stream."""
    out = {}
    for tier in TIERS:
        s, y, meta = d3_dev_sample(tier)
        m = fit_platt(s, y)
        m["tier"] = tier_key(tier)
        m["kind_requested"] = "d3dev"
        m["label"] = "clip-level: does the clip contain the event"
        m["fitted_on"] = "StudyD3 Nexar DEV clips, DISJOINT from the 300 evaluation clips"
        m["d3_sample"] = meta
        m["n_clips_fitted_on"] = meta["n_clips"]
        m["raw_percentiles"] = dict(p05=float(np.percentile(s, 5)),
                                    p50=float(np.percentile(s, 50)),
                                    p95=float(np.percentile(s, 95)))
        out[tier_key(tier)] = m
    return out
