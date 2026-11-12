#!/usr/bin/env python3
"""Measured cost curves the baselines and the smoke harness read.

StudyB-baselines. CPU only. EVERY number here is a committed measurement with its source named;
nothing is fitted, interpolated beyond a stated rule, or invented. If a baseline needs a quantity
that is not here, that is a gap to report, not a number to guess.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "experiments/dashcam"))

# ---------------------------------------------------------------- episodic (StudyE9 / E9b)
# Re-exported from study_e9_episodes so there is exactly one copy of each constant in the repo.
try:
    import study_e9_episodes as _E9
    FRAME_BYTES: Dict[int, int] = dict(_E9.FRAME_BYTES)            # StudyD4 median PNG bytes
    FRAME_BYTES_JPEG: Dict[int, int] = dict(_E9.FRAME_BYTES_JPEG)  # StudyD4 JPEG q90 bytes
    UPLINK_BPS: float = _E9.UPLINK_BPS                             # 13.6 Mbit/s
    RTT_S: float = _E9.RTT_S                                       # 0.044 s
    DEV_LAT_S: float = _E9.DEV_LAT_S                               # StudyD8 arm A total p50
    CLOUD_TTFT: Dict[Tuple[str, int, int], float] = dict(_E9.CLOUD_TTFT)   # StudyD7 / D7b
    PREFILL_TOK_S: Dict[str, float] = dict(_E9.PREFILL_TOK_S)      # StudyD7 / D7b saturated
    PROMPT_TOK: Dict[int, int] = dict(_E9.PROMPT_TOK)              # StudyD3 / D4 / D14
    _IMPORTED = True
except Exception:                                                  # pragma: no cover
    _IMPORTED = False
    FRAME_BYTES = {1: 354902, 3: 1057532, 9: 3188243}
    FRAME_BYTES_JPEG = {1: 59601, 3: 177773, 9: 529361}
    UPLINK_BPS = 13.6e6 / 8.0
    RTT_S = 0.044
    DEV_LAT_S = 0.567
    CLOUD_TTFT = {("32BI", 1, 25): 0.1422, ("32BI", 1, 75): 0.2976,
                  ("32BI", 3, 25): 0.2643, ("32BI", 3, 75): 0.5915,
                  ("4BI", 1, 25): 0.0827, ("4BI", 1, 75): 0.1359}
    PREFILL_TOK_S = {"32BI": 5600.0, "4BI": 29500.0}
    PROMPT_TOK = {1: 378, 3: 1062}

DEVICE_CADENCE_S = 0.75     # StudyE9b: ceil(0.567 / 0.25) x 0.25, saturated duty (flagged there)
GRID_STEP_S = 0.25          # StudyD14b decision grid


def episodic_cloud_latency_s(model: str, n: int, load_pct: int, jpeg: bool = False) -> float:
    """StudyE9b setting (ii) (PNG) or (iii) (JPEG): RTT + upload + server TTFT, UNROUNDED."""
    by = FRAME_BYTES_JPEG if jpeg else FRAME_BYTES
    return RTT_S + by[n] / UPLINK_BPS + CLOUD_TTFT[(model, n, load_pct)]


def hold_shift_steps(latency_s: float, step_s: float = GRID_STEP_S) -> int:
    """StudyE9b sample-and-hold: the first grid index at which a score computed on-grid can be
    read. The latency is not rounded; only the read moment is quantised to the decision grid."""
    return int(math.ceil(latency_s / step_s - 1e-9))


def episodic_gpu_s(model: str, n: int) -> float:
    """GPU-seconds charged per resolver call (StudyE9 / E9b accounting)."""
    return PROMPT_TOK[n] / PREFILL_TOK_S[model]


def episodic_uplink_bytes(n: int, jpeg: bool = False) -> int:
    return (FRAME_BYTES_JPEG if jpeg else FRAME_BYTES)[n]


# ---------------------------------------------------------------- recall (StudyRH5, E10b/c/d)
# StudyRH5 Part A, isolated reload cost, D2 format, one request at a time. TTFT medians.
RECALL_TTFT_S: Dict[Tuple[int, str], float] = {
    (11000, "GPU-WARM"): 0.382,     # GPU-only server
    (11000, "HOST-WARM"): 0.459,
    (11000, "COLD"): 2.445,
    (28000, "GPU-WARM"): 0.874,
    (28000, "HOST-WARM"): 1.001,
    (28000, "COLD"): 7.367,
}
RECALL_SIZES = (11000, 28000)
# StudyRH5: COLD is a full re-prefill at these measured rates.
COLD_PREFILL_TOK_S: Dict[int, float] = {11000: 4500.0, 28000: 3800.0}
# StudyE10d: a cold K1 RICH recall is 12,645 prompt tokens; LM prefill about 2.17 s (~5.8k tok/s),
# frontend 1.47 s for the PNG body / 0.75 s JPEG / 0.04 s text-only, vision encoder about 0.2 s.
K1_RICH_TOKENS = 12645
K1_RICH_LM_PREFILL_S = 2.17
K1_RICH_FRONTEND_S = {"png": 1.47, "jpeg": 0.75, "text": 0.04}
VISION_ENCODER_S = 0.2
# StudyRH5: host reload moves exactly this many bytes per host-hit token (64 layers x 8 KV heads
# x 128 x {K,V} x bf16).
HOST_BYTES_PER_TOKEN = 262144
HOST_RELOAD_GB_S = {11000: 47.6, 28000: 52.9}   # StudyRH5 vLLM load-time metric

# StudyE10b episodic capacity on one 32B replica, N = 3, p99 budget met (req/s).
EPISODIC_CAPACITY_REQ_S = {
    ("GPU", 0, 0.0): 2.69,     # 50 % of peak, no recall load
    ("HOST", 0, 0.0): 2.69,
    ("GPU", 4, 0.0): 1.34,     # k = 4 warm sessions halves it
    ("HOST", 8, 0.0): 1.34,
}


def _nearest_size(tokens: int) -> int:
    return min(RECALL_SIZES, key=lambda s: abs(s - tokens))


def recall_ttft_s(tokens: int, readiness: str) -> float:
    """TTFT for a recall query at a given readiness.

    StudyRH5 measured two sizes only (11k and 28k). Between and beyond them this interpolates
    LINEARLY IN TOKENS for the warm states and uses the measured cold prefill rate for COLD. The
    rule is stated here and in every card that relies on it; it is NOT a measurement.
    """
    if readiness not in ("GPU-WARM", "HOST-WARM", "COLD"):
        raise ValueError(readiness)
    lo, hi = RECALL_SIZES
    if readiness == "COLD":
        rate = COLD_PREFILL_TOK_S[_nearest_size(tokens)]
        return tokens / rate
    a, b = RECALL_TTFT_S[(lo, readiness)], RECALL_TTFT_S[(hi, readiness)]
    if tokens <= lo:
        return a * tokens / lo
    if tokens >= hi:
        return b * tokens / hi
    return a + (b - a) * (tokens - lo) / (hi - lo)


def recall_gpu_s(tokens: int, readiness: str) -> float:
    """GPU-seconds charged. A warm hit charges its TTFT; COLD charges the prefill it recomputes.
    This is the same accounting StudyRH5 / E10b use: the GPU is busy for the TTFT it reports."""
    return recall_ttft_s(tokens, readiness)


def host_reload_bytes(tokens: int) -> int:
    return tokens * HOST_BYTES_PER_TOKEN


def warm_hold_cost_gpu_s(tokens: int, seconds_held: float) -> float:
    """Keeping a session GPU-warm occupies KV, it does not burn GPU time. Returned as 0.0 GPU-s
    with the KV footprint accounted separately; StudyRH5 is explicit that the binding resource is
    GPU KV for the running set, not compute."""
    return 0.0


SOURCES = {
    "FRAME_BYTES": "StudyD4 median PNG request bytes",
    "FRAME_BYTES_JPEG": "StudyD4 JPEG q90 request bytes",
    "UPLINK_BPS": "13.6 Mbit/s uplink (StudyE9 setting (ii))",
    "RTT_S": "0.044 s RTT (StudyE9 setting (ii))",
    "DEV_LAT_S": "StudyD8 arm A, sustained 1 Hz N=1, total p50",
    "CLOUD_TTFT": "StudyD7 / D7b open-loop TTFT p50 at 25 % and 75 % of peak",
    "PREFILL_TOK_S": "StudyD7 / D7b saturated prefill",
    "PROMPT_TOK": "StudyD3 / D4 / D14 prompt tokens",
    "DEVICE_CADENCE_S": "StudyE9b saturated device cadence (flagged extrapolation from D8's 1 Hz)",
    "RECALL_TTFT_S": "StudyRH5 Part A isolated reload cost, D2 format, TTFT medians",
    "COLD_PREFILL_TOK_S": "StudyRH5 Part A cold re-prefill rates",
    "K1_RICH_*": "StudyE10d idle-phase decomposition",
    "HOST_BYTES_PER_TOKEN": "StudyRH5 (64 layers x 8 KV heads x 128 x K,V x bf16)",
    "HOST_RELOAD_GB_S": "StudyRH5 vLLM load-time metric",
    "EPISODIC_CAPACITY_REQ_S": "StudyE10b capacity table, N = 3, p99 budget",
}
INTERPOLATION_RULES = {
    "recall_ttft_s": "linear in tokens between StudyRH5's 11k and 28k for the warm states; "
                     "measured cold prefill rate for COLD. A RULE, not a measurement.",
}
