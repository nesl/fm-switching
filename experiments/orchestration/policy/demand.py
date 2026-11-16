"""Spec 6.4 (D48): SEPARATE demand rates per device.

lambda_rc is split by the representation a question type would use, lambda_esc counts escalations
and is used for calendar arrivals and controller load ONLY, never for history value. The
conditional recall rate during episodes is behind its flag and the flag is OFF, because
StudyPROF1-dev found the test NOT COMPUTABLE from committed data.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class Demand:
    alpha: float = 0.1
    lambda_rc: Dict[str, float] = field(default_factory=dict)
    lambda_esc: float = 0.0
    _last_rc: Dict[str, float] = field(default_factory=dict)
    _last_esc: Optional[float] = None
    conditional_rate_enabled: bool = False
    conditional_ratio: float = 1.0

    def prior_from_profiles(self, pf, reps=("RICH", "RECENT", "D2")) -> "Demand":
        """Spec 2.1: EWMA with DEV PRIORS. The prior is split across representations by the DEV
        question-type mix, which is the only committed split that exists."""
        total = pf.lambda_rc_default()
        qmap = pf.raw["RC"]["question_type_to_representation"]
        counts: Dict[str, int] = {}
        for q, v in qmap.items():
            r = v["representation"]
            n = int(v.get("candidates", {}).get(r, {}).get("n", 0))
            counts[r] = counts.get(r, 0) + max(n, 0)
        s = sum(counts.values())
        for r in reps:
            self.lambda_rc[r] = total * (counts.get(r, 0) / s if s else 0.0)
        self.conditional_rate_enabled = bool(pf.conditional_rate_available())
        return self

    def observe_recall(self, rep: str, dt_s: float) -> float:
        if dt_s <= 0:
            raise ValueError("inter-arrival must be positive")
        inst = 1.0 / dt_s
        cur = self.lambda_rc.get(rep, inst)
        self.lambda_rc[rep] = (1 - self.alpha) * cur + self.alpha * inst
        self._last_rc[rep] = inst
        return self.lambda_rc[rep]

    def observe_escalation(self, dt_s: float) -> float:
        if dt_s <= 0:
            raise ValueError("inter-arrival must be positive")
        inst = 1.0 / dt_s
        self.lambda_esc = ((1 - self.alpha) * self.lambda_esc + self.alpha * inst
                           if self.lambda_esc else inst)
        self._last_esc = inst
        return self.lambda_esc

    def rate_rc(self, rep: str, in_episode: bool = False) -> float:
        base = float(self.lambda_rc.get(rep, 0.0))
        if in_episode and self.conditional_rate_enabled:
            return base * self.conditional_ratio
        return base

    def p_need_within(self, rep: str, h_s: float, in_episode: bool = False) -> float:
        """Spec 6.1: 1 - exp(-lambda * H_s)."""
        import math
        return 1.0 - math.exp(-self.rate_rc(rep, in_episode) * max(h_s, 0.0))
