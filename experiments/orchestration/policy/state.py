"""Spec 2: entities and state. Plain dataclasses; no behaviour beyond bookkeeping and invariants.

Spec 2.1 holds a BELIEVED tier DISTRIBUTION per (device, representation), not a tier, so
`HistoryBelief` carries probabilities and the planner reads expectations over them (6.5).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

TIERS = ("GPU", "HOST", "STORED")
_COLDER = {"GPU": "HOST", "HOST": "STORED", "STORED": "DEVICE"}


def colder(tier: str) -> str:
    if tier not in _COLDER:
        raise ValueError("unknown tier %r" % tier)
    return _COLDER[tier]


@dataclass
class Link:
    bandwidth_bytes_s: float
    rtt_s: float
    reachable: bool = True
    p_reachable_within_hs: float = 1.0

    def up_s(self, payload_bytes: int) -> float:
        return payload_bytes / self.bandwidth_bytes_s + self.rtt_s / 2.0

    def down_s(self) -> float:
        return self.rtt_s / 2.0


@dataclass
class HistoryBelief:
    rep: str
    size_tokens: int
    probs: Dict[str, float] = field(default_factory=lambda: {"GPU": 0.0, "HOST": 0.0,
                                                             "STORED": 1.0})
    staleness_s: float = 0.0
    unsent_frames: int = 0
    desired_tier: str = "STORED"
    requested: Optional[Tuple[str, float]] = None      # (target tier, time requested)
    confirmed_tier: Optional[str] = None

    def __post_init__(self) -> None:
        self.normalize()

    def normalize(self) -> None:
        for t in TIERS:
            self.probs.setdefault(t, 0.0)
        s = sum(self.probs[t] for t in TIERS)
        if s <= 0:
            raise ValueError("a tier belief must carry mass")
        for t in TIERS:
            self.probs[t] = self.probs[t] / s

    def expected(self, value_by_tier: Dict[str, float]) -> float:
        return sum(self.probs[t] * value_by_tier[t] for t in TIERS)

    def most_likely(self) -> str:
        return max(TIERS, key=lambda t: self.probs[t])


@dataclass
class Episode:
    device: str
    task: str
    cadence_s: float
    opened_at: float
    calls_issued: List[float] = field(default_factory=list)
    max_calls: int = 10
    phase: Optional[float] = None
    closed_at: Optional[float] = None
    negative_delta_j_calls: int = 0

    def due_at(self) -> float:
        base = self.calls_issued[-1] if self.calls_issued else self.opened_at
        return base + self.cadence_s

    def exhausted(self) -> bool:
        return len(self.calls_issued) >= self.max_calls


@dataclass
class Job:
    """Spec 2.2 and 7.3: an admitted RC job needing history on the cloud."""
    job_id: str
    device: str
    qtype: str
    rep: str
    deadline: float
    admitted_at: float
    pieces_total: int
    pieces_done: int = 0
    tokens_per_piece: int = 1024
    feasibility: str = "FEASIBLE"
    p_finish: float = 1.0
    answered: bool = False

    def pieces_left(self) -> int:
        return max(self.pieces_total - self.pieces_done, 0)

    def tokens_left(self) -> int:
        return self.pieces_left() * self.tokens_per_piece


@dataclass
class PendingItem:
    """Anything the coordinator may release now or defer (spec 2.2, 7.2)."""
    item_id: str
    kind: str                     # episode_call | rc_piece | state_action | summary | upload
    device: str
    due_at: float
    deadline: Optional[float] = None
    tokens: int = 0
    frames: int = 1
    job_id: Optional[str] = None
    readiness: str = "COLD"
    payload_bytes: int = 0
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Opportunity:
    """Spec 1.2 and 3.1: one eligible opportunity, the SLO denominator."""
    opp_id: str
    device: str
    task: str
    t: float
    qtype: Optional[str] = None
    deadline: Optional[float] = None
    device_utility: float = 0.0
    served_by: str = "device"
    delivered_delay_s: Optional[float] = None


@dataclass
class Device:
    device_id: str
    link: Link
    history: Dict[str, HistoryBelief] = field(default_factory=dict)
    episodes: List[Episode] = field(default_factory=list)
    z: Dict[str, float] = field(default_factory=dict)
    lambda_rc: Dict[str, float] = field(default_factory=dict)
    lambda_esc: float = 0.0
    controller: Any = None
    demand: Any = None
    qtype: Optional[str] = None

    def z_of(self, task: str) -> float:
        return float(self.z.get(task, 0.0))

    def bump_z(self, task: str, p_target: float, success_hat: float) -> float:
        self.z[task] = max(self.z_of(task) + p_target - success_hat, 0.0)
        return self.z[task]


@dataclass
class Fleet:
    devices: Dict[str, Device] = field(default_factory=dict)
    jobs: Dict[str, Job] = field(default_factory=dict)
    pending: List[PendingItem] = field(default_factory=list)
    in_flight: List[PendingItem] = field(default_factory=list)
    t: float = 0.0
    gpu_backlog_s: float = 0.0

    def add_device(self, d: Device) -> Device:
        if d.device_id in self.devices:
            raise ValueError("duplicate device %r" % d.device_id)
        self.devices[d.device_id] = d
        return d

    def device(self, did: str) -> Device:
        return self.devices[did]

    def calendar(self, horizon_s: float) -> List[PendingItem]:
        """Spec 2.2 and 7.2 step 1: known arrivals inside the horizon, deadline-ordered."""
        end = self.t + horizon_s
        known = [p for p in self.pending if p.due_at <= end]
        return sorted(known, key=lambda p: (p.deadline if p.deadline is not None else 1e18,
                                            p.due_at, p.item_id))
