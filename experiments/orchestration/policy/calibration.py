"""D57 (user decision, 2026-11-16): per-tier score calibration.

THE PROBLEM D57 FIXES. A device model and a cloud model do not put their raw scores on the same
scale. StudyCTRL1b measured this directly: its oracle arm moved a rank metric by itself because
the two tiers' scores live on different scales (POL2 ambiguity A12). So any comparison that puts
one tier's raw score against another's, and any decision in which the cloud UPGRADES the device's
answer, is meaningless until both have been mapped to a COMMON probability scale.

WHAT THIS MODULE IS. A calibration is a per-tier MONOTONE map raw score -> probability, FITTED ON
DEV and LOADED FROM A FILE. Nothing here fits anything: StudyCTRL1c produces the maps, and this
module reads them, checks they are monotone, and applies them.

THE GUARD. The default calibration is the IDENTITY map for every tier, which is not a
calibration: it is the absence of one. `require_calibrated` therefore RAISES whenever scores from
MORE THAN ONE tier are about to be compared under identity maps, unless the caller is a test and
says so explicitly (`identity_for_tests`). A single-tier comparison needs no calibration and is
allowed, because a monotone map cannot change the order inside one tier.

This is the opposite of the usual default. It is deliberate: an uncalibrated cross-tier
comparison is silent and wrong, and this repository's own record (E30 versus E32, StudyCTRL1b's
oracle arm) is that the silent-and-wrong cases are the expensive ones.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

IDENTITY = "identity"


class CalibrationMissing(RuntimeError):
    """Raised when scores from two tiers would be compared with no calibration between them."""


class CalibrationInvalid(ValueError):
    """Raised when a loaded map is not usable as a monotone raw score to probability map."""


@dataclass
class MonotoneMap:
    """A piecewise-linear monotone map from a raw score to a probability.

    `knots` is a list of (raw, probability) pairs, strictly increasing in raw and non-decreasing
    in probability, with every probability in [0, 1]. Outside the measured raw range the end
    value is HELD and the caller is told, because extrapolating a calibration is exactly the
    failure mode `utility._interp` already refuses for u_SH.
    """

    tier: str
    knots: List[Tuple[float, float]] = field(default_factory=list)
    source: str = "IDENTITY: no calibration has been fitted for this tier"

    def is_identity(self) -> bool:
        return not self.knots

    def __post_init__(self) -> None:
        if not self.knots:
            return
        ks = [(float(a), float(b)) for a, b in self.knots]
        for (x0, y0), (x1, y1) in zip(ks, ks[1:]):
            if not x1 > x0:
                raise CalibrationInvalid(
                    "calibration for tier %r is not strictly increasing in raw score at %r"
                    % (self.tier, x1))
            if y1 < y0 - 1e-12:
                raise CalibrationInvalid(
                    "calibration for tier %r is not monotone in probability at raw %r"
                    % (self.tier, x1))
        for _, y in ks:
            if not -1e-12 <= y <= 1.0 + 1e-12:
                raise CalibrationInvalid(
                    "calibration for tier %r maps to %r, which is not a probability"
                    % (self.tier, y))
        self.knots = ks

    def apply(self, raw: float) -> Tuple[float, bool]:
        """(probability, within_measured_raw_range)."""
        if self.is_identity():
            return float(raw), True
        xs = [x for x, _ in self.knots]
        if raw <= xs[0]:
            return self.knots[0][1], raw >= xs[0] - 1e-12
        if raw >= xs[-1]:
            return self.knots[-1][1], raw <= xs[-1] + 1e-12
        for (x0, y0), (x1, y1) in zip(self.knots, self.knots[1:]):
            if x0 <= raw <= x1:
                w = (raw - x0) / (x1 - x0)
                return y0 * (1 - w) + y1 * w, True
        raise AssertionError("unreachable")


@dataclass
class TierCalibration:
    """The per-tier maps D57 asks for, plus the guard that stops an uncalibrated comparison."""

    maps: Dict[str, MonotoneMap] = field(default_factory=dict)
    allow_identity_mixed_tier: bool = False
    source_file: Optional[str] = None

    def map_for(self, tier: str) -> MonotoneMap:
        m = self.maps.get(tier)
        if m is None:
            m = MonotoneMap(tier=tier)
            self.maps[tier] = m
        return m

    def to_probability(self, tier: str, raw: float) -> Dict[str, Any]:
        m = self.map_for(tier)
        p, inrange = m.apply(raw)
        return dict(tier=tier, raw=float(raw), probability=float(p),
                    within_measured_range=bool(inrange), identity=m.is_identity(),
                    source=m.source)

    def all_identity(self, tiers: Iterable[str]) -> bool:
        return all(self.map_for(t).is_identity() for t in tiers)

    def describe(self) -> Dict[str, Any]:
        return dict(source_file=self.source_file,
                    allow_identity_mixed_tier=self.allow_identity_mixed_tier,
                    tiers={t: dict(identity=m.is_identity(), n_knots=len(m.knots),
                                   source=m.source) for t, m in sorted(self.maps.items())})


def require_calibrated(cal: Optional[TierCalibration], tiers: Sequence[str],
                       context: str) -> TierCalibration:
    """D57's loud failure. Call this before ANY comparison, ranking, upgrade or gain estimate
    that mixes tiers.

    A comparison inside ONE tier is always allowed: a monotone map preserves order, so the
    calibration cannot change the answer. A comparison ACROSS tiers with no calibration is
    refused, because the two raw scales are not the same quantity."""
    distinct = sorted({str(t) for t in tiers if t is not None})
    if len(distinct) <= 1:
        return cal if cal is not None else TierCalibration()
    if cal is None:
        raise CalibrationMissing(
            "D57: %s compares scores from tiers %s and no per-tier calibration was supplied. "
            "Set Params.tier_calibration to a TierCalibration loaded from StudyCTRL1c's fitted "
            "maps, or, in a test, to calibration.identity_for_tests()." % (context, distinct))
    if cal.all_identity(distinct) and not cal.allow_identity_mixed_tier:
        raise CalibrationMissing(
            "D57: %s compares scores from tiers %s under IDENTITY maps, which is the absence of "
            "a calibration, not a calibration. StudyCTRL1b measured that the two tiers' raw "
            "scores are on different scales. Load the DEV-fitted maps (StudyCTRL1c) or, in a "
            "test, use calibration.identity_for_tests()." % (context, distinct))
    return cal


def rank_across_tiers(cal: Optional[TierCalibration], items: Sequence[Dict[str, Any]],
                      context: str) -> List[Dict[str, Any]]:
    """D57: rank items whose raw scores come from DIFFERENT tiers.

    Every raw score is mapped to the common probability scale FIRST, and only then compared. The
    guard runs before anything is sorted, so an uncalibrated ranking cannot be produced at all.
    Each item needs `tier` and `raw`; anything else it carries is passed through."""
    rows = list(items)
    cal = require_calibrated(cal, [r.get("tier") for r in rows], context)
    out = []
    for r in rows:
        m = cal.to_probability(str(r.get("tier")), float(r.get("raw", 0.0)))
        out.append(dict(r, probability=m["probability"], identity_map=m["identity"],
                        within_measured_range=m["within_measured_range"]))
    out.sort(key=lambda r: (-r["probability"], str(r.get("id", ""))))
    return out


def upgrade_decision(cal: Optional[TierCalibration], cloud: Dict[str, Any],
                     device: Dict[str, Any], margin: float = 0.0) -> Dict[str, Any]:
    """D57: should the cloud's answer UPGRADE the device's?

    Both raw scores go onto the common probability scale before the comparison, because that is
    exactly the comparison StudyCTRL1b showed is meaningless on raw scales. `margin` is the
    calibrated probability the cloud must beat the device by; 0.0 means any improvement counts
    and is not a fitted threshold."""
    cal = require_calibrated(cal, [cloud.get("tier"), device.get("tier")],
                             "the cloud upgrading the device's answer")
    c = cal.to_probability(str(cloud.get("tier")), float(cloud.get("raw", 0.0)))
    d = cal.to_probability(str(device.get("tier")), float(device.get("raw", 0.0)))
    return dict(upgrade=bool(c["probability"] - d["probability"] > float(margin)),
                cloud=c, device=d, margin=float(margin),
                delta_probability=float(c["probability"] - d["probability"]),
                rule="compared on the common calibrated probability scale (D57), never on raw "
                     "scores: StudyCTRL1b measured that the two tiers' raw scores are on "
                     "different scales")


def identity_for_tests() -> TierCalibration:
    """The ONLY sanctioned way to compare tiers under identity maps. Named so it cannot be used
    by accident and so a grep finds every place that relies on it."""
    return TierCalibration(allow_identity_mixed_tier=True,
                           source_file="identity_for_tests(): NOT A CALIBRATION")


def load(path: Any) -> TierCalibration:
    """Load D57's maps from a file. The actual maps come from StudyCTRL1c; this row does not fit
    them (the brief is explicit about that).

    File format, one object:
        {"tiers": {"<tier>": {"knots": [[raw, p], ...], "source": "..."}}, "source": "..."}
    """
    p = Path(path)
    raw = json.loads(p.read_text())
    tiers = raw.get("tiers")
    if not isinstance(tiers, dict) or not tiers:
        raise CalibrationInvalid("%s carries no 'tiers' object" % p)
    maps: Dict[str, MonotoneMap] = {}
    for tier, spec in tiers.items():
        knots = spec.get("knots") or []
        if not knots:
            raise CalibrationInvalid(
                "tier %r in %s has no knots; omit the tier rather than writing an empty map, so "
                "an absent calibration is never mistaken for a fitted one" % (tier, p))
        maps[tier] = MonotoneMap(tier=tier, knots=[tuple(k) for k in knots],
                                 source=str(spec.get("source", "unstated in the file")))
    return TierCalibration(maps=maps, allow_identity_mixed_tier=False, source_file=str(p))
