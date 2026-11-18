#!/usr/bin/env python3
"""D86: the calibration map is an INPUT, and an INTERIM map may not run on a real server.

CPU only. Two jobs:

  1. LOAD AND LABEL a per-tier calibration map file. The labelling rule is not reimplemented
     here: `live2/fleet/data_sources.py::calibration` already derives it conservatively (a map is
     FINAL only if the file itself declares `"label": "FINAL"` and `"fit_sample": "dense"`, so
     the committed `orin2_calibration.json` is INTERIM and a missing declaration can never read
     as FINAL). This module calls it, and falls back to the same rule only if that module cannot
     be imported.
  2. CONVERT the a / b logistic form the committed file carries into the KNOTS form the policy
     library's `policy/calibration.py::load` reads, so the policy arm gets D57's maps without
     anything being refitted.

REFUSAL (D86): `require_runnable` raises for a non-stub run with a map labelled INTERIM.
"""
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DEFAULT_MAP = ROOT / "results/dashcam/study_orin2/orin2_calibration.json"

DEVICE_TIER = "device_4b_orin"
CLOUD_TIER = "h100_32b"

RAW_GRID = tuple(round(-14.0 + 0.25 * i, 3) for i in range(57))     # log p_yes, -14 to 0


class CalibrationRefused(RuntimeError):
    """A real-server run was asked to start with a map that is not fit for a measured run."""


def load_map(path: Any = None) -> Dict[str, Any]:
    p = Path(path) if path else DEFAULT_MAP
    try:
        sys.path.insert(0, str(HERE / "fleet"))
        import data_sources as DS                                     # noqa: E402
        return DS.calibration(p)
    except Exception:                                                 # noqa: BLE001
        return _fallback_load(p)


def _fallback_load(p: Path) -> Dict[str, Any]:
    import hashlib
    if not p.exists():
        raise FileNotFoundError(f"calibration map {p} does not exist")
    d = json.loads(p.read_text())
    label = "FINAL" if (d.get("label") == "FINAL" and d.get("fit_sample") == "dense") \
        else "INTERIM"
    maps = {DEVICE_TIER: dict(a=float(d["a"]), b=float(d["b"]))}
    for k, v in (d.get("compare") or {}).items():
        maps[k] = dict(a=float(v["a"]), b=float(v["b"]))
    return dict(path=str(p), sha256=hashlib.sha256(p.read_bytes()).hexdigest(), label=label,
                maps=maps, fit_split=d.get("fit_split"),
                note="labelled by live2/calib.py's fallback, same rule as fleet/data_sources.py")


def require_runnable(loaded: Dict[str, Any], server_kind: str) -> Dict[str, Any]:
    """D86: INTERIM maps are for flash builds and tests only, never an H100 measured run."""
    if loaded.get("label") == "INTERIM" and server_kind != "fake":
        raise CalibrationRefused(
            "D86: the calibration map %s is labelled INTERIM (fitted on an event-anchored "
            "sample, not dense instants) and may be used for flash builds and tests only. A run "
            "against a real server (%r) is refused until the dense JPEG refit of BOTH tiers has "
            "delivered a map the file itself declares FINAL." % (loaded.get("path"), server_kind))
    return loaded


def to_knots(loaded: Dict[str, Any], tiers: Optional[Sequence[str]] = None,
             grid: Sequence[float] = RAW_GRID) -> Dict[str, Any]:
    """The policy library's file format, derived from the a / b logistic maps.

    StudyORIN2's form is `log_odds = a * log(p_yes) + b`, so the probability on the common scale
    is sigmoid(a * raw + b) with `raw = log p_yes`. Sampling it on a grid is a REPRESENTATION
    CHANGE, not a refit: no datum is touched and the map is the committed one.
    """
    tiers = list(tiers) if tiers else [DEVICE_TIER, CLOUD_TIER]
    out: Dict[str, Any] = {"tiers": {}}
    for t in tiers:
        m = loaded["maps"].get(t)
        if m is None:
            raise KeyError(f"the calibration file has no map for tier {t!r}; "
                           f"it carries {sorted(loaded['maps'])}")
        knots = [[float(x), 1.0 / (1.0 + math.exp(-(m["a"] * x + m["b"])))] for x in grid]
        out["tiers"][t] = dict(
            knots=knots,
            source=("StudyORIN2 / D86 map a=%.6f b=%.6f from %s (sha256 %s), label %s, sampled "
                    "onto knots by live2/calib.py; sigmoid(a*log p_yes + b)"
                    % (m["a"], m["b"], loaded.get("path"), str(loaded.get("sha256"))[:12],
                       loaded.get("label"))))
    out["source"] = ("derived from %s, label %s (D86). NOT A NEW FIT."
                     % (loaded.get("path"), loaded.get("label")))
    out["label"] = loaded.get("label")
    return out


def write_knots(loaded: Dict[str, Any], out_path: Any,
                tiers: Optional[Sequence[str]] = None) -> Path:
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(to_knots(loaded, tiers), indent=1, sort_keys=True) + "\n")
    return p
