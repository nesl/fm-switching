"""Spec 3.2 and 4: bounded task utilities and the gain of a cloud action.

Every table comes from `Profiles` (StudyPROF1-dev, DEV only, spec D6). u_SH is interpolated
LINEARLY in delivered delay on StudyE9d's own 0.25-s grid and is NOT extrapolated past its last
measured delay: beyond that the curve's value is held and the caller is told, because an
extrapolated utility is exactly the kind of number this repository has been burned by.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .profiles import MissingEvidence, Profiles


def _interp(grid: List[Tuple[float, float]], d: float) -> Tuple[float, bool]:
    if d < 0:
        raise ValueError("delivered delay cannot be negative")
    xs = [x for x, _ in grid]
    if d <= xs[0]:
        return grid[0][1], True
    if d >= xs[-1]:
        return grid[-1][1], False
    for (x0, y0), (x1, y1) in zip(grid, grid[1:]):
        if x0 <= d <= x1:
            w = (d - x0) / (x1 - x0)
            return y0 * (1 - w) + y1 * w, True
    raise AssertionError("unreachable")


def u_sh_device(pf: Profiles, mapping: str = "identity") -> float:
    return pf.u_sh_device(mapping)


def u_sh_cloud(pf: Profiles, delay_s: float, m_frames: int = 1, cadence_s: float = 0.5,
               mapping: str = "identity", allow_m_gt_1: bool = False) -> Tuple[float, bool]:
    """(utility, within_measured_range). m > 1 requires the merging flag: spec 7.9's enabling
    condition is NOT met and the m = 3 table is DEV-optimistic (StudyFRAMES1)."""
    if m_frames != 1 and not allow_m_gt_1:
        raise MissingEvidence(
            "u_SH at m = %d may only be read with merging explicitly enabled: spec 7.9's "
            "enabling condition is not met and StudyFRAMES1 / StudyCTRL1b found no held-out "
            "benefit. %s" % (m_frames, pf.frames_warning()))
    return _interp(pf.u_sh_grid(m_frames, cadence_s, mapping), delay_s)


def u_ss(pf: Profiles, delay_s: float, l_ss: float) -> float:
    """Spec 4.2: a cliff at L_SS. There is no committed SS accuracy, so this raises rather than
    guessing (spec 13, P2 pins the single-shot workload)."""
    raise MissingEvidence(
        "u_SS needs acc_SS^cloud and no committed single-shot accuracy exists (spec 13 pins the "
        "SS workload, P2). The policy must not score SS opportunities until it does.")


def t_ready_s(pf: Profiles, rep: str, tier: str, size_tokens: int, staleness_s: float,
              unsent_frames: int, link, model: str = "32BI") -> Dict[str, float]:
    """Spec 4.3's T_ready, term by term, so a caller can see what bound it."""
    up = link.up_s(unsent_frames * int(pf.raw["durations"]["catchup_per_frame"]
                                       .get("bytes_per_frame", 0) or 0)) if unsent_frames else 0.0
    if tier == "GPU":
        restore = 0.0
        readiness = "GPU-WARM"
    elif tier == "HOST":
        restore = size_tokens * pf.seconds_per_token("reload", size_tokens)
        readiness = "HOST-WARM"
    else:
        restore = size_tokens * pf.seconds_per_token("rebuild", size_tokens)
        readiness = "COLD"
    frames = staleness_s / float(pf.raw["durations"]["catchup_per_frame"]["d2_stride_s"])
    catchup = frames * pf.catchup_per_frame_s(model)
    answer = pf.recall_ttft_s(readiness, size_tokens)
    return dict(t_upload=up, t_restore=restore, t_catchup=catchup, t_answer=answer,
                total=up + restore + catchup + answer, readiness=readiness)


def u_rc(pf: Profiles, qtype: str, rep: str, t_ready: float, t_queue: float, link,
         deadline_s: float, tier: str = "cloud") -> Tuple[float, bool]:
    """Spec 4.3: the cloud answer counts only if it lands inside the deadline."""
    delivered = t_ready + t_queue + link.down_s()
    if delivered > deadline_s:
        return pf.rc_accuracy(qtype, "D2", "device"), False
    return pf.rc_accuracy(qtype, rep, tier), True


def gain(pf: Profiles, task: str, cloud_u: float, device_u: float,
         omega: Optional[Dict[str, float]] = None) -> float:
    """Spec 3.2: g_r(x) = omega_k * (u_cloud - u_device). May be zero or negative (D39)."""
    w = (omega or {}).get(task)
    if w is None:
        w = pf.omega(task)
    return float(w) * (float(cloud_u) - float(device_u))
