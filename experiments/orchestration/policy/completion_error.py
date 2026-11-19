#!/usr/bin/env python3
"""D122 v1.1 F4: the cost model's MEASURED completion-time error, from committed FIT data only.

The source is the step model's own residual summary in
`results/cost/study_eng1/eng1_step_model.json`, whose `fit_data` field states

    "Part A (A_E0) and Part B E0 (B_E0) steps; Part C (incl. HOLDOUT) not used"

so it is FIT-only by construction. No HOLDOUT file is read here: not ENG1 Part C, not ENG1c Part
D, not ENG1d, not ENG1e. The frozen JSON is READ only and its md5 is untouched.

THE FORM, pre-registered before fitting (report section V17.2). A multiplicative error on the
predicted completion time,

    T = T_hat * exp(eps),   eps ~ Normal(0, sigma_band^2)

with `sigma_band` calibrated from the committed MEDIAN RELATIVE residual of the token band the
job's pieces fall in, using the half-normal relation for a zero-median log error,

    median|eps| = 0.6745 * sigma   =>   sigma = median_rel_res / 0.6745

There is no free parameter: the only inputs are the committed medians and a normal quantile.

THE CAVEAT THAT TRAVELS WITH IT. These are PER-STEP residuals and a completion time is a sum of
many steps, so independent per-step errors would partly average out. Using the per-step relative
residual as the completion-time relative residual therefore OVERSTATES the uncertainty, and
`sigma_band` is an upper bound rather than a calibrated completion-time sigma. Committed
predicted-against-actual completion pairs do not exist, and none are invented here.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Dict, Optional, Tuple

# The 0.5 quantile of a half-normal: median|Z| = 0.6744897501960817 for Z ~ N(0, 1).
HALF_NORMAL_MEDIAN = 0.6744897501960817

STEP_MODEL_PATH = "results/cost/study_eng1/eng1_step_model.json"

# (lower, upper] token bounds for each committed residual band, read off its own key name.
_BAND_BOUNDS: Tuple[Tuple[str, float, float], ...] = (
    ("tok_0_1", 0.0, 1.0),
    ("tok_1_512", 1.0, 512.0),
    ("tok_512_2048", 512.0, 2048.0),
    ("tok_2048_4096", 2048.0, 4096.0),
    ("tok_4096_8193", 4096.0, 8193.0),
)

_CACHE: Dict[str, Dict[str, float]] = {}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def load_sigmas(path: Optional[Path] = None) -> Dict[str, float]:
    """`band name -> sigma`, derived from the committed median relative residuals."""
    p = str(Path(path) if path is not None else (_repo_root() / STEP_MODEL_PATH))
    hit = _CACHE.get(p)
    if hit is not None:
        return hit
    raw = json.loads(Path(p).read_text())
    fit = str(raw.get("fit_data", ""))
    if "HOLDOUT) not used" not in fit:
        raise ValueError(
            "refusing to calibrate the completion-time error from %s: its fit_data is %r and "
            "does not state that the HOLDOUT was excluded" % (p, fit))
    bands = raw["residual_bands"]
    out: Dict[str, float] = {}
    for name, _lo, _hi in _BAND_BOUNDS:
        b = bands.get(name) or {}
        rel = b.get("median_rel_res")
        if rel is None:
            continue
        out[name] = float(rel) / HALF_NORMAL_MEDIAN
    if not out:
        raise ValueError("no committed median relative residual found in %s" % p)
    _CACHE[p] = out
    return out


def sigma_for_tokens(tokens: int, path: Optional[Path] = None) -> float:
    """The sigma of the committed band this piece size falls in.

    Below the smallest band and above the largest, the nearest band is used rather than
    extrapolating, which is the same rule the committed curves state for sizes outside their
    measured range.
    """
    sig = load_sigmas(path)
    tok = max(float(tokens), 0.0)
    for name, lo, hi in _BAND_BOUNDS:
        if name in sig and lo < tok <= hi:
            return sig[name]
    named = [(lo, hi, name) for name, lo, hi in _BAND_BOUNDS if name in sig]
    if not named:
        raise ValueError("no committed band available")
    if tok <= named[0][0]:
        return sig[named[0][2]]
    return sig[named[-1][2]]


def p_finish_by(deadline_s: float, predicted_s: float, sigma: float) -> float:
    """P(T <= deadline) for T = predicted * exp(eps), eps ~ N(0, sigma^2).

    Degenerate cases keep the indicator's answer, so the probabilistic path agrees with the
    0/1 path wherever the error model has nothing to say: a non-positive prediction always
    finishes, and a non-positive deadline never does.
    """
    d = float(deadline_s)
    m = float(predicted_s)
    if d <= 0.0:
        return 0.0
    if m <= 0.0:
        return 1.0
    s = float(sigma)
    if s <= 0.0:
        return 1.0 if m <= d else 0.0
    z = (math.log(d) - math.log(m)) / s
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


# The 0.90 quantile of a standard normal, for the q90 safety factor below.
NORMAL_Q90 = 1.2815515655446004


def kappa_for_tokens(tokens: int, path: Optional[Path] = None) -> float:
    """D129: the q90 safety factor on predicted completion, from committed FIT-only residuals.

    PROVENANCE, and the choice behind it. The design note asks for the q90 ratio of MEASURED to
    PREDICTED JOB COMPLETION time on committed FIT/DEV data. No such quantity exists in committed
    derived form: StudyPOL6's own records carry cell-level timing aggregates, not
    predicted-against-actual completion pairs, and the raw pairs live in files that MIX FIT and
    HOLDOUT trials (StudyENG1c Part D), which POL6 separated with a split manifest.

    Opening a mixed file and relying on my own filtering is the one unrecoverable mistake
    available here, so this derives kappa instead from a source already verified as FIT-only:
    `eng1_step_model.json`, whose `fit_data` states Part C including the HOLDOUT was not used.
    Under the same log-normal error model as `p_finish_by`,

        kappa = exp(z_0.90 * sigma_band)

    LIMITATION, carried with the number: these are per-STEP residuals and a completion sums many
    steps, so independent errors would partly average out and this OVERSTATES the spread. kappa is
    therefore conservative, which is the safe direction for a latest-start time.
    """
    return float(math.exp(NORMAL_Q90 * sigma_for_tokens(tokens, path)))


def describe(path: Optional[Path] = None) -> Dict[str, object]:
    sig = load_sigmas(path)
    p = str(Path(path) if path is not None else (_repo_root() / STEP_MODEL_PATH))
    raw = json.loads(Path(p).read_text())
    return dict(source=STEP_MODEL_PATH, fit_data=raw.get("fit_data"), n=raw.get("n"),
                r2=raw.get("r2"), form="T = T_hat * exp(eps), eps ~ N(0, sigma_band^2)",
                calibration="sigma = median_rel_res / 0.6744897501960817",
                sigma_by_band={k: round(v, 6) for k, v in sorted(sig.items())},
                kappa_by_band={k: round(math.exp(NORMAL_Q90 * v), 6)
                               for k, v in sorted(sig.items())},
                caveat="per-STEP residuals used for a completion time that sums many steps, so "
                       "sigma is an UPPER BOUND and the form is conservative")
