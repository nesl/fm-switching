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
  tail-first within    a prefix loses its TAIL tokens first and keeps its HEAD, so a partly
  one prefix           evicted prefix can still be resumed from its surviving head
  P_loss(g)            the FRACTION of a prefix's blocks the pool predicts will be freed over a
                       gap of g seconds, given the demand the rollout predicts in that window

P_loss is READ FROM THE PREDICTED EVICTION, never set by hand (A6.2). It is MECHANISTIC: pool
size (a parameter), referenced versus unreferenced blocks, the free-block order, and the KV that
arrivals allocate before the resume. Nothing in `predict_loss` reads a fitted curve.

WHAT STUDYENG1b MEASURED, and where it may and may not be used (StudyPOL3-update, 2026-11-16).
StudyENG1b measured the staircase this bookkeeping is supposed to produce: a prefix is FULLY
RESIDENT while other work has allocated less than the free pool (capacity minus the prefix),
loses its TAIL partially between 1.0 and 1.25 of the free pool, and is TOTALLY lost above 1.25.
Three parts of that measurement enter this module:

  1. tail-first partial loss is now explicit (`PrefixEntry.head_tokens`), because ENG1b's 32
     partial losses all kept the LEADING 3,360 to 5,360 tokens;
  2. re-referencing an unreferenced prefix moves it behind others in the free queue, which is
     why StudyENG1b's W25 cells lost prefixes BELOW 1.0 of the free pool: that is already the
     behaviour of `reference()` updating `last_used`, and it is now stated;
  3. the staircase ITSELF is available only as `eng1b_long_gap_curve`, the long-gap fallback A6
     point 2 names, for gaps the rollout does not reach. IT IS NOT USED BY `predict_loss` AND IT
     IS NOT USED BY T0. T0's whole question is whether the bookkeeping reproduces the staircase,
     so feeding the staircase back in would make the test vacuous.
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
    built_tokens: int = 0

    def __post_init__(self) -> None:
        if self.built_tokens <= 0:
            self.built_tokens = max(int(self.tokens), 0)

    def head_tokens(self) -> int:
        """StudyENG1b: the engine frees a request's blocks TAIL FIRST, so what survives is the
        prefix's LEADING tokens and a partly evicted prefix is resumable from that head."""
        return max(int(self.tokens), 0)

    def lost_tail_tokens(self) -> int:
        return max(int(self.built_tokens) - max(int(self.tokens), 0), 0)


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
        e.built_tokens = max(e.built_tokens, e.tokens)
        e.referenced = referenced
        e.last_used = t
        self.t = max(self.t, t)
        return e

    def reference(self, prefix_id: str, t: float, held: bool = True) -> None:
        """Holding a prefix also moves it to the BACK of the free queue.

        StudyENG1b's W25 cells are the measurement of this: the 8 warm sessions re-referenced
        their own cached contexts during the gap, which pushed those blocks behind the deferred
        prefix in the free queue without allocating anything new, and the prefix was then lost at
        as little as 0.17 of the nominal free pool. Updating `last_used` on a reference is that
        mechanism, not a heuristic."""
        e = self.entries.get(prefix_id)
        if e is None:
            return
        e.referenced = held
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
        which is the only protection that exists: holding a request on it (A6.3).

        Within one prefix the tokens freed are its TAIL (StudyENG1b): `e.tokens` is the surviving
        HEAD afterwards, and `e.lost_tail_tokens()` is what went."""
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

    def allocate(self, prefix_id: str, tokens: int, t: float,
                 owner_job: Optional[str] = None, owner_device: Optional[str] = None,
                 rep: str = "RICH", store: Optional[Any] = None) -> Dict[str, Any]:
        """One arrival's KV allocation, which is the ONLY thing that evicts an unreferenced
        prefix (StudyENG1b: survival is a step function of allocated KV, not of elapsed time).

        Blocks the GPU pool frees are offered to the host tier through `store` (D56), and what
        the host cannot hold becomes COLD. Nothing is deleted."""
        freed = self.make_room(max(int(tokens), 0), t)
        demotion = {}
        if store is not None and freed:
            demotion = store.demote_from_gpu(freed, t)
        self.put(prefix_id, max(int(tokens), 0), t, referenced=True, owner_job=owner_job,
                 owner_device=owner_device, rep=rep)
        return dict(freed=freed, demoted=demotion, allocated_tokens=int(tokens),
                    occupancy_tokens=self.occupancy(), free_tokens=self.free_tokens())

    def clone(self) -> "KVPool":
        return KVPool(capacity_tokens=self.capacity_tokens, t=self.t,
                      entries={k: PrefixEntry(v.prefix_id, v.tokens, v.referenced, v.last_used,
                                              v.owner_job, v.owner_device, v.rep,
                                              v.built_tokens)
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

# StudyENG1b section 4, version (ii) (allocation measured before the resume was SCHEDULED, which
# is the quantity the eviction actually sees). Bins are allocated KV as a fraction of the free
# pool (capacity minus the prefix); the value is the MEAN FRACTION of the prefix lost in the bin.
# Pooled over E0 and KV-HOST because the measured staircase is identical on both servers (the
# server decides where the evicted blocks GO, not whether they go).
ENG1B_STAIRCASE: List[Tuple[float, float]] = [
    (1.00, 0.00),
    (1.10, 0.33),
    (1.25, 0.60),
    (1.50, 1.00),
]
ENG1B_STAIRCASE_SOURCE = (
    "StudyENG1b section 4 (M5): fully resident below 1.0 of the free pool, tail-first partial "
    "loss of about a third at 1.0 to 1.1 and 60 % at 1.1 to 1.25, total loss from 1.25. "
    "LONG-GAP FALLBACK ONLY (addendum A6 point 2). It must NOT be used where the rollout reaches "
    "the resume time, and it must NOT be used in T0, whose question is whether the pool's own "
    "bookkeeping reproduces this curve.")


def eng1b_long_gap_curve(allocated_fraction_of_free_pool: float) -> float:
    """A6 point 2's long-gap fallback, from StudyENG1b's measured staircase.

    The argument is NOT a gap length. StudyENG1b's verdict is that survival is a step function of
    the KV other work allocates and that gap length matters only through allocation, so a curve
    in seconds would be a curve in the wrong variable. A caller with a gap beyond the rollout's
    reach converts it to allocation with the predicted arrival rate first."""
    x = float(allocated_fraction_of_free_pool)
    xs = [a for a, _ in ENG1B_STAIRCASE]
    if x <= xs[0]:
        return 0.0
    if x >= xs[-1]:
        return 1.0
    for (x0, y0), (x1, y1) in zip(ENG1B_STAIRCASE, ENG1B_STAIRCASE[1:]):
        if x0 <= x <= x1:
            w = (x - x0) / (x1 - x0)
            return float(y0 * (1 - w) + y1 * w)
    raise AssertionError("unreachable")


def survival_p_loss(curve: Optional[SurvivalCurve], gap_s: float) -> Dict[str, Any]:
    """A6.2's beyond-horizon extension, for the part of a gap the rollout does not reach.

    `curve` is a callable supplied by the caller. `eng1b_long_gap_curve` is the measured one
    (M5, StudyENG1b) and takes ALLOCATION as a fraction of the free pool, so a caller passing it
    must convert the beyond-horizon gap into predicted allocation itself. With no curve the
    beyond-horizon part contributes nothing and the result is flagged, which is unchanged."""
    if curve is None:
        return dict(p_loss=0.0, available=False,
                    note="NO SURVIVAL CURVE WAS SUPPLIED, so the beyond-horizon part of the gap "
                         "contributes nothing and every result that depends on it is flagged "
                         "beyond_horizon_unmeasured. StudyENG1b's measured staircase is "
                         "available as kvpool.eng1b_long_gap_curve and is the LONG-GAP FALLBACK "
                         "ONLY (M5); it is deliberately not the default, because the in-horizon "
                         "P_loss must stay mechanistic (A6.2)")
    return dict(p_loss=float(curve(gap_s)), available=True,
                note="supplied survival curve; if this is eng1b_long_gap_curve the argument is "
                     "allocation as a fraction of the free pool, not seconds (%s)"
                     % ENG1B_STAIRCASE_SOURCE)
