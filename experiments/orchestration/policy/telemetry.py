"""Spec 6.5 (D44, D47): residency believed from engine TELEMETRY, conservatively when ambiguous.

The engine exposes separate LOCAL (GPU) and EXTERNAL (host-connector) prefix-cache hit counters
(StudyE10c metrics). A promotion is REQUESTED when issued and CONFIRMED only when telemetry shows
the expected state; unconfirmed promotions receive no future-value credit.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .state import TIERS, HistoryBelief


@dataclass
class TelemetrySnapshot:
    local_hits: int = 0
    external_hits: int = 0
    offload_loads: int = 0
    evictions: int = 0
    cached_tokens: int = 0
    t: float = 0.0

    def minus(self, other: "TelemetrySnapshot") -> "TelemetrySnapshot":
        return TelemetrySnapshot(
            local_hits=self.local_hits - other.local_hits,
            external_hits=self.external_hits - other.external_hits,
            offload_loads=self.offload_loads - other.offload_loads,
            evictions=self.evictions - other.evictions,
            cached_tokens=self.cached_tokens, t=self.t)


@dataclass
class ResidencyBelief:
    conservatism: float = 0.5
    log: List[Dict[str, Any]] = field(default_factory=list)

    def update(self, belief: HistoryBelief, delta: TelemetrySnapshot, t: float) -> str:
        """Returns the verdict: GPU, HOST, STORED or AMBIGUOUS."""
        if delta.local_hits > 0 and delta.external_hits == 0:
            verdict = "GPU"
        elif delta.external_hits > 0 and delta.local_hits == 0:
            verdict = "HOST"
        elif delta.evictions > 0 and delta.local_hits == 0 and delta.external_hits == 0:
            verdict = "STORED"
        elif delta.local_hits > 0 and delta.external_hits > 0:
            verdict = "AMBIGUOUS"
        else:
            verdict = "AMBIGUOUS"
        if verdict == "AMBIGUOUS":
            self._conservative(belief)
        else:
            belief.probs = {t_: (1.0 if t_ == verdict else 0.0) for t_ in TIERS}
            belief.confirmed_tier = verdict
            if belief.requested and belief.requested[0] == verdict:
                belief.requested = None
        belief.normalize()
        self.log.append(dict(t=t, rep=belief.rep, verdict=verdict,
                             local_hits=delta.local_hits, external_hits=delta.external_hits,
                             offload_loads=delta.offload_loads, evictions=delta.evictions,
                             probs=dict(belief.probs),
                             requested=(belief.requested[0] if belief.requested else None)))
        return verdict

    def _conservative(self, belief: HistoryBelief) -> None:
        """Ambiguity moves mass toward the COLDER tier, never toward the warmest (spec 6.5)."""
        c = self.conservatism
        p = dict(belief.probs)
        moved_gpu = p["GPU"] * c
        moved_host = p["HOST"] * c
        p["GPU"] -= moved_gpu
        p["HOST"] += moved_gpu - moved_host
        p["STORED"] += moved_host
        belief.probs = p
        belief.normalize()

    def request(self, belief: HistoryBelief, target: str, t: float) -> None:
        if target not in TIERS:
            raise ValueError("unknown tier %r" % target)
        belief.requested = (target, t)
        belief.desired_tier = target
        self.log.append(dict(t=t, rep=belief.rep, verdict="REQUESTED", target=target))

    def divergence(self, belief: HistoryBelief) -> Dict[str, Any]:
        return dict(desired=belief.desired_tier, believed=belief.most_likely(),
                    confirmed=belief.confirmed_tier,
                    diverged=bool(belief.desired_tier != belief.most_likely()),
                    unconfirmed_request=(belief.requested[0] if belief.requested else None))

    def credit_allowed(self, belief: HistoryBelief) -> bool:
        """Spec 6.5: future-value credit only for CONFIRMED transitions."""
        return belief.requested is None
