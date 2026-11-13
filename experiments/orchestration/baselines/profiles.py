#!/usr/bin/env python3
"""Resource-quality profiles for episodic streams, read from our committed measurements.

StudyB-baselines. CPU only. These are the profiles the adapted VideoStorm, Ekya and PerLLM
baselines consume; they are MEASURED, not fitted here.

For a stream the configuration is (mode, cadence c, frame count N). Quality comes from
StudyE9b's streaming AP and StudyE9c's challenge mAP for the matching always-on arm; lag is
StudyE9b's sample-and-hold shift; demand is cloud GPU-seconds per second of stream.

The two quality scales are kept SEPARATE and named, per StudyE9c: "challenge mAP" and
"streaming AP" are not comparable in level, and a baseline must pick one and say which.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import costs as C

ROOT = Path(__file__).resolve().parents[3]
E9B = ROOT / "results/dashcam/study_e9b/e9b_study1_results.json"
E9C = ROOT / "results/dashcam/study_e9c/e9c_results.json"
E9D = ROOT / "results/dashcam/study_e9d/e9d_results.json"

_S1 = json.loads(E9B.read_text())
_S2 = json.loads(E9C.read_text())
STREAMING_CHANCE = _S1["chance_rate"]
CHALLENGE_CHANCE = sum(_S2["base_rate_by_horizon"].values()) / len(_S2["base_rate_by_horizon"])
SETTINGS = ("zero", "measured@25", "measured@75")


def streaming_ap(arm: Optional[str], setting: str, cadence_s: float, horizon: float = 0.5,
                 far: int = 5) -> float:
    """StudyE9b always-on AP at a horizon. `arm` None means the device arm (device-only)."""
    if arm is None:
        return _S1["baselines"][f"device-only|{setting}|far{far}"]["ap"][str(horizon)]["ap"]
    k = f"always-cloud/{arm}|{setting}|cad{int(round(cadence_s*100))}|far{far}"
    return _S1["baselines"][k]["ap"][str(horizon)]["ap"]


def challenge_map(arm: Optional[str], setting: str) -> Optional[float]:
    """StudyE9c challenge mAP for the matching arm, where StudyE9c scored it.

    StudyE9c scored only cadence 0.5 s, so a profile at another cadence has NO challenge mAP and
    this returns None rather than an interpolated guess.
    """
    nm = "device-only 4BI_N1" if arm is None else f"always-cloud {arm}"
    key = f"{nm}|{setting}"
    cell = _S2["arms"].get(key)
    return None if cell is None else cell["mAP"]["value"]


def hold_shift_s(arm: Optional[str], setting: str) -> float:
    """StudyE9b's sample-and-hold shift: VideoStorm's `lag` in our setting."""
    if arm is None:
        return C.hold_shift_steps(0.0 if setting == "zero" else C.DEV_LAT_S) * C.GRID_STEP_S
    if setting == "zero":
        return 0.0
    model, n = arm.split("_N")[0], int(arm.split("_N")[1])
    load = 25 if setting.endswith("25") else 75
    return C.hold_shift_steps(C.episodic_cloud_latency_s(model, n, load)) * C.GRID_STEP_S


def demand_gpu_s_per_s(arm: str, cadence_s: float) -> float:
    """Cloud GPU-seconds consumed per wall second by one stream at this configuration."""
    model, n = arm.split("_N")[0], int(arm.split("_N")[1])
    return C.episodic_gpu_s(model, n) / cadence_s


def uplink_bytes_per_s(arm: str, cadence_s: float, jpeg: bool = False) -> float:
    n = int(arm.split("_N")[1])
    return C.episodic_uplink_bytes(n, jpeg) / cadence_s


def stream_profile(setting: str = "measured@25", horizon: float = 0.5,
                   arms: Tuple[str, ...] = ("32BI_N1", "32BI_N3"),
                   quality: str = "streaming") -> List[Dict]:
    """The full resource-quality profile P_k for one episodic stream.

    quality = "streaming" (StudyE9b AP at `horizon`) or "challenge" (StudyE9c mAP, cadence 0.5 s
    only). Rows whose quality is unavailable on the chosen scale are omitted, and the omission is
    visible because the caller can compare len() against the cadence x arm product.
    """
    rows: List[Dict] = []
    q_dev = (streaming_ap(None, setting, 0.5, horizon) if quality == "streaming"
             else challenge_map(None, setting))
    if q_dev is not None:
        rows.append(dict(name="local", mode="local", cadence_s=None, frame_count=None,
                         quality=q_dev, demand_gpu_s_per_s=0.0, uplink_bytes_per_s=0.0,
                         lag_s=hold_shift_s(None, setting)))
    for arm in arms:
        for c in C.__dict__.get("_CAD", (0.25, 0.5, 1.0)):
            q = (streaming_ap(arm, setting, c, horizon) if quality == "streaming"
                 else (challenge_map(arm, setting) if abs(c - 0.5) < 1e-9 else None))
            if q is None:
                continue
            rows.append(dict(name=f"cloud/{arm}@{c}", mode="cloud", cadence_s=c,
                             frame_count=int(arm.split("_N")[1]), quality=q,
                             demand_gpu_s_per_s=demand_gpu_s_per_s(arm, c),
                             uplink_bytes_per_s=uplink_bytes_per_s(arm, c),
                             lag_s=hold_shift_s(arm, setting)))
    return rows


# ================================================================ amendment 2026-11-12
# (b) the StudyE9d delay curves and the committed recall accuracy tables.
_S3 = json.loads(E9D.read_text())
DELAYS_S = tuple(float(d) for d in _S3["delays_s"])
BLOCK_WINDOWS_S = tuple(float(w) for w in _S3["windows_s"])


def delay_curve(arm: str, cadence_s: float = 0.5, quality: str = "challenge",
                horizon: float = 0.0) -> List[Tuple[float, float]]:
    """StudyE9d's V(d): [(added delay s, value)] for one arm and cadence.

    `quality` = "challenge" (StudyE9c mAP) or "streaming" (StudyE9b AP at `horizon`). The two are
    NOT comparable in level; a caller picks one and says which, per StudyE9c's rule.
    """
    key = f"always-cloud {arm}@{cadence_s}"
    out = []
    for d in DELAYS_S:
        c = _S3["vd"].get(f"{key}|d{d}")
        if c is None:
            continue
        out.append((d, c["challenge_mAP"]["value"] if quality == "challenge"
                    else c["streaming"][str(horizon)]["ap"]))
    if not out:
        raise KeyError(f"StudyE9d has no curve for {key}")
    return out


def device_value(quality: str = "challenge", horizon: float = 0.0) -> float:
    """The device arm's value on the same scale - StudyE9d's reference line."""
    c = _S3["vd"]["device-only 4BI_N1"]
    return (c["challenge_mAP"]["value"] if quality == "challenge"
            else c["streaming"][str(horizon)]["ap"])


def value_at_delay(arm: str, delay_s: float, cadence_s: float = 0.5,
                   quality: str = "challenge", horizon: float = 0.0) -> float:
    """V(d) at an arbitrary delay, by LINEAR INTERPOLATION between StudyE9d's 0.25-s grid points
    and held flat beyond 3.0 s. The interpolation is a RULE, not a measurement, and is stated in
    every card that uses it."""
    cur = delay_curve(arm, cadence_s, quality, horizon)
    xs = [x for x, _ in cur]
    ys = [y for _, y in cur]
    if delay_s <= xs[0]:
        return ys[0]
    if delay_s >= xs[-1]:
        return ys[-1]
    return _lerp(xs, ys, delay_s)


def _lerp(xs, ys, x):
    for i in range(1, len(xs)):
        if x <= xs[i]:
            f = (x - xs[i - 1]) / (xs[i] - xs[i - 1])
            return ys[i - 1] + f * (ys[i] - ys[i - 1])
    return ys[-1]


def d_star_s(arm: str, cadence_s: float = 0.5, quality: str = "challenge",
             horizon: float = 0.0) -> Optional[float]:
    """StudyE9d's d*: the added delay at which this arm falls to the device's value. None means it
    does not cross inside StudyE9d's 3-s grid. StudyE9d's own warning applies: the CIs are wide
    and d* is NOT a threshold - a policy should read the curve."""
    k = f"always-cloud {arm}@{cadence_s}"
    m = "challenge_mAP" if quality == "challenge" else f"streaming_h{horizon}"
    return _S3["dstar"][k][m]["d_star_s"]


def blocking_loss(arm: str, window_s: float, mode: str = "QUEUE", cadence_s: float = 0.5,
                  quality: str = "challenge", horizon: float = 0.0) -> Optional[float]:
    """StudyE9d part (b): the mean value LOST when the cloud path is blocked for `window_s`,
    under QUEUE or SUSPEND. StudyE9d's noise floor (about 0.001 mAP) applies: a loss smaller than
    that is not resolvable and should be read as zero."""
    c = _S3["blocking"].get(f"always-cloud {arm}@{cadence_s}|{mode}|w{window_s}")
    if c is None:
        return None
    return (c["mAP_loss"]["mean"] if quality == "challenge"
            else c["streaming_loss"][str(horizon)]["mean"])


def recall_accuracy(config: str, category: Optional[str] = None,
                    question_time_s: Optional[float] = None) -> Optional[float]:
    """Committed recall accuracy per configuration x category x question-time bin.

    Reads `recall_profiles`, which counts COMMITTED per-question `correct` flags and never
    estimates. Returns None where no committed cell exists.
    """
    import recall_profiles as RP
    return RP.accuracy(config, category, question_time_s)


PROVENANCE = {
    "delay curves": "StudyE9d V(d) on StudyD14b's 0.25-s grid, setting (ii) at 25 % load; "
                    "value BETWEEN grid points is linearly interpolated, which is a RULE",
    "blocking loss": "StudyE9d part (b), mean over 20 window placements; noise floor about "
                     "0.001 challenge mAP",
    "recall accuracy": "committed per-question `correct` flags via recall_profiles (StudyR1 K1 / "
                       "K3, StudyRH4 D2, StudyD11 U, StudyClean H1 / H2, StudyE7 4B D2 as the "
                       "DEVICE PROXY, StudyF4 device N = 1 / 3 / 9); never estimated",
    "quality (streaming)": "StudyE9b always-on AP at the requested horizon, alarm FPR 5 %",
    "quality (challenge)": "StudyE9c challenge mAP; scored at cadence 0.5 s only, so other "
                           "cadences return None rather than an interpolated value",
    "lag": "StudyE9b sample-and-hold shift = ceil(L / 0.25) x 0.25 s",
    "demand": "StudyE9 / E9b GPU-seconds per resolver call divided by the cadence",
    "uplink": "StudyD4 request bytes divided by the cadence",
}
