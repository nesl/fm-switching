"""Addendum A6.2: the KV POOL the rollout tracks, and the predicted eviction P_loss is read from.

WHY THIS EXISTS (A6's problem statement). A reconstruction job's pieces are released separately
(v3 7.4). Between pieces NO request holds the already-built prefix, so its blocks are cached but
UNREFERENCED, and the engine frees those first under pressure. The prefix cannot be pinned (D44).
Deferring the next piece is therefore not only a delay, it risks losing work already done.

WHAT IS MODELLED, and nothing beyond it:
  occupancy            tokens currently held
  referenced           whether a request is holding the prefix right now
  free-block order     unreferenced first, least recently used first, which is the engine's own
                       order as StudyE10c's telemetry exposes it
  P_loss(g)            the FRACTION of a prefix's blocks the pool predicts will be freed over a
                       gap of g seconds, given the demand the rollout predicts in that window

P_loss is READ FROM THE PREDICTED EVICTION, never set by hand (A6.2). Where the rollout does not
reach the resume time, A6 says to extend it with the measured survival curve from M5; M5 does not
exist yet, so the curve is a pluggable callable that DEFAULTS TO NONE and the result is flagged
`beyond_horizon_unmeasured` rather than being quietly filled in.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple


@dataclass
class PrefixEntry:
    prefix_id: str
    tokens: int
    referenced: bool = False
    last_used: float = 0.0
    owner_job: Optional[str] = None
    owner_device: Optional[str] = None
    rep: str = "RICH"


@dataclass
class KVPool:
    """GPU KV occupancy with referenced and unreferenced blocks, and the engine's free order."""
    capacity_tokens: int
    entries: Dict[str, PrefixEntry] = field(default_factory=dict)
    evicted: Dict[str, int] = field(default_factory=dict)
    t: float = 0.0

    def occupancy(self) -> int:
        return sum(e.tokens for e in self.entries.values())

    def free_tokens(self) -> int:
        return max(self.capacity_tokens - self.occupancy(), 0)

    def pressure(self) -> float:
        return (self.occupancy() / self.capacity_tokens) if self.capacity_tokens else 0.0

    def put(self, prefix_id: str, tokens: int, t: float, referenced: bool = True,
            owner_job: Optional[str] = None, owner_device: Optional[str] = None,
            rep: str = "RICH") -> PrefixEntry:
        e = self.entries.get(prefix_id)
        if e is None:
            e = PrefixEntry(prefix_id, 0, referenced, t, owner_job, owner_device, rep)
            self.entries[prefix_id] = e
        e.tokens = max(e.tokens, 0) + max(tokens, 0)
        e.referenced = referenced
        e.last_used = t
        self.t = max(self.t, t)
        return e

    def reference(self, prefix_id: str, t: float, held: bool = True) -> None:
        e = self.entries.get(prefix_id)
        if e is None:
            return
        e.referenced = held
        if held:
            e.last_used = t
        self.t = max(self.t, t)

    def free_order(self) -> List[str]:
        """The engine's own order: UNREFERENCED blocks first, least recently used first.
        Referenced blocks are listed last and are never freed by `make_room`."""
        un = sorted((e for e in self.entries.values() if not e.referenced),
                    key=lambda e: (e.last_used, e.prefix_id))
        ref = sorted((e for e in self.entries.values() if e.referenced),
                     key=lambda e: (e.last_used, e.prefix_id))
        return [e.prefix_id for e in un] + [e.prefix_id for e in ref]

    def make_room(self, tokens_needed: int, t: float) -> Dict[str, int]:
        """Free unreferenced blocks, in the engine's order, until the demand fits.

        Returns how many tokens were freed per prefix. A referenced prefix is NEVER freed here,
        which is the only protection that exists: holding a request on it (A6.3)."""
        freed: Dict[str, int] = {}
        need = tokens_needed - self.free_tokens()
        if need <= 0:
            return freed
        for pid in self.free_order():
            if need <= 0:
                break
            e = self.entries[pid]
            if e.referenced:
                continue
            take = min(e.tokens, need)
            e.tokens -= take
            need -= take
            freed[pid] = freed.get(pid, 0) + take
            self.evicted[pid] = self.evicted.get(pid, 0) + take
            if e.tokens <= 0:
                del self.entries[pid]
        self.t = max(self.t, t)
        return freed

    def predict_loss(self, prefix_id: str, demand_tokens: int, t: float) -> Dict[str, Any]:
        """A6.2: P_loss as the FRACTION of this prefix's blocks the pool predicts will be freed
        when `demand_tokens` of other work needs room during the gap.

        A fraction rather than an indicator because a partial eviction is the common case and it
        costs a partial restore; the caller multiplies it by the restore cost."""
        e = self.entries.get(prefix_id)
        if e is None:
            return dict(p_loss=1.0, basis="the prefix is not in the pool at all",
                        tokens=0, evicted_tokens=0)
        if e.tokens <= 0:
            return dict(p_loss=1.0, basis="the prefix holds no blocks", tokens=0,
                        evicted_tokens=0)
        shadow = self.clone()
        shadow.reference(prefix_id, t, held=False)
        freed = shadow.make_room(demand_tokens, t)
        ev = freed.get(prefix_id, 0)
        return dict(p_loss=float(ev) / float(e.tokens), tokens=e.tokens, evicted_tokens=ev,
                    demand_tokens=demand_tokens, pressure=self.pressure(),
                    basis="fraction of the prefix's blocks freed by the predicted demand, with "
                          "the prefix unreferenced between pieces (A6.2)")

    def clone(self) -> "KVPool":
        return KVPool(capacity_tokens=self.capacity_tokens, t=self.t,
                      entries={k: PrefixEntry(v.prefix_id, v.tokens, v.referenced, v.last_used,
                                              v.owner_job, v.owner_device, v.rep)
                               for k, v in self.entries.items()},
                      evicted=dict(self.evicted))

    def describe(self) -> Dict[str, Any]:
        return dict(capacity_tokens=self.capacity_tokens, occupancy_tokens=self.occupancy(),
                    pressure=self.pressure(), n_prefixes=len(self.entries),
                    referenced=[e.prefix_id for e in self.entries.values() if e.referenced],
                    free_order=self.free_order())


def prefix_id_for(job_id: str) -> str:
    return "prefix:%s" % job_id


SurvivalCurve = Callable[[float], float]


def survival_p_loss(curve: Optional[SurvivalCurve], gap_s: float) -> Dict[str, Any]:
    """A6.2's beyond-horizon extension. M5 will supply the curve; until then there is none, and
    this says so instead of inventing one."""
    if curve is None:
        return dict(p_loss=0.0, available=False,
                    note="NO MEASURED SURVIVAL CURVE EXISTS (A6 assigns it to M5), so the "
                         "beyond-horizon part of the gap contributes nothing and every result "
                         "that depends on it is flagged beyond_horizon_unmeasured")
    return dict(p_loss=float(curve(gap_s)), available=True, note="supplied survival curve")
