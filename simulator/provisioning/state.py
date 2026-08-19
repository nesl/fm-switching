"""
Session and provisioning state for the fidelity-provisioning simulator.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from .costs import CostModel, COST_MODEL
from .quality import FIDELITIES


@dataclass
class StateObject:
    session_id: int
    node_id: str
    fidelity: str       # "full", "win", "sum80", "sum200", "blind"
    ready: bool         # True = KV-resident; False = stored only
    staleness: int      # turns (epochs) behind session's current head
    being_materialized: bool = False
    eta_epochs: int = 0   # epochs until materialization completes; 0 = idle


@dataclass
class SessionState:
    session_id: int
    regime: str
    L: int              # current context length (tokens)
    turn_rate: int      # tokens added per epoch
    serving_node: str   # current node actively serving this session
    turns_since_last_serve: int = 0

    def advance(self):
        """Called once per epoch to grow L and update turn counter."""
        self.L += self.turn_rate
        self.turns_since_last_serve += 1


# Fidelity quality ordering for "best available" selection (higher index = higher quality)
_FIDELITY_RANK = {f: i for i, f in enumerate(["blind", "sum80", "sum200", "win", "full"])}


class ProvisioningState:
    """Tracks all state objects and per-node GPU capacity usage."""

    def __init__(self, node_ids: list, cost_model: CostModel = None):
        self._cm = cost_model or COST_MODEL
        # objects[(session_id, node_id, fidelity)] = StateObject
        self.objects: Dict[Tuple[int, str, str], StateObject] = {}
        # GB used per node for ready KV objects
        self.node_capacity_used: Dict[str, float] = {nid: 0.0 for nid in node_ids}

    def _key(self, session_id: int, node_id: str, fidelity: str):
        return (session_id, node_id, fidelity)

    def get(self, session_id: int, node_id: str, fidelity: str) -> Optional[StateObject]:
        return self.objects.get(self._key(session_id, node_id, fidelity))

    def can_fit(self, node_id: str, fidelity: str, L: int, nodes: dict) -> bool:
        """True if adding S_ready(f, L) to node doesn't exceed capacity."""
        cap = nodes[node_id].capacity_gb
        needed = self._cm.s_ready_gb(fidelity, L)
        return self.node_capacity_used.get(node_id, 0.0) + needed <= cap + 1e-9

    def make_ready(self, session_id: int, node_id: str, fidelity: str,
                   L: int, staleness: int = 0):
        """Mark object as KV-resident; allocate capacity. Idempotent if already ready."""
        key = self._key(session_id, node_id, fidelity)
        if key in self.objects and self.objects[key].ready:
            return  # already ready
        needed = self._cm.s_ready_gb(fidelity, L)
        self.node_capacity_used[node_id] = self.node_capacity_used.get(node_id, 0.0) + needed
        if key not in self.objects:
            self.objects[key] = StateObject(
                session_id=session_id, node_id=node_id, fidelity=fidelity,
                ready=True, staleness=staleness)
        else:
            obj = self.objects[key]
            obj.ready = True
            obj.being_materialized = False
            obj.eta_epochs = 0
            obj.staleness = staleness

    def evict(self, session_id: int, node_id: str, fidelity: str, L: int):
        """Evict (de-materialize) object, freeing capacity. Object remains as stored."""
        key = self._key(session_id, node_id, fidelity)
        obj = self.objects.get(key)
        if obj and obj.ready:
            freed = self._cm.s_ready_gb(fidelity, L)
            self.node_capacity_used[node_id] = max(
                0.0, self.node_capacity_used.get(node_id, 0.0) - freed)
            obj.ready = False
            obj.being_materialized = False
            obj.eta_epochs = 0

    def start_materialization(self, session_id: int, node_id: str, fidelity: str,
                              eta_epochs: int):
        """Mark an object as being materialized (not yet ready)."""
        key = self._key(session_id, node_id, fidelity)
        if key not in self.objects:
            self.objects[key] = StateObject(
                session_id=session_id, node_id=node_id, fidelity=fidelity,
                ready=False, staleness=0,
                being_materialized=True, eta_epochs=eta_epochs)
        else:
            obj = self.objects[key]
            if not obj.ready:
                obj.being_materialized = True
                obj.eta_epochs = eta_epochs

    def ensure_stored(self, session_id: int, node_id: str, fidelity: str):
        """Ensure object exists in stored form (no capacity cost)."""
        key = self._key(session_id, node_id, fidelity)
        if key not in self.objects:
            self.objects[key] = StateObject(
                session_id=session_id, node_id=node_id, fidelity=fidelity,
                ready=False, staleness=0)

    def best_ready_object(self, session_id: int, node_id: str,
                          q_min: float, regime: str) -> Optional[StateObject]:
        """Return the highest-quality ready object at node meeting q_min; None otherwise."""
        from .quality import quality
        best = None
        best_rank = -1
        for fidelity in FIDELITIES:
            key = self._key(session_id, node_id, fidelity)
            obj = self.objects.get(key)
            if obj and obj.ready and not obj.being_materialized:
                q = quality(fidelity, regime)
                rank = _FIDELITY_RANK[fidelity]
                if rank > best_rank:
                    best = obj
                    best_rank = rank
        return best

    def any_sufficient_elsewhere(self, session_id: int, node_id: str,
                                  q_min: float, regime: str, all_nodes: list) -> bool:
        """Return True if sufficient-quality ready object exists at some other node."""
        from .quality import quality
        for nid in all_nodes:
            if nid == node_id:
                continue
            for fidelity in FIDELITIES:
                key = self._key(session_id, nid, fidelity)
                obj = self.objects.get(key)
                if obj and obj.ready and quality(fidelity, regime) >= q_min:
                    return True
        return False

    def being_materialized_at(self, session_id: int, node_id: str,
                               q_min: float, regime: str) -> bool:
        """Return True if a sufficient-fidelity object is being materialized at node."""
        from .quality import quality
        for fidelity in FIDELITIES:
            key = self._key(session_id, node_id, fidelity)
            obj = self.objects.get(key)
            if obj and obj.being_materialized and quality(fidelity, regime) >= q_min:
                return True
        return False

    def advance_materializations(self, nodes: dict, sessions: dict):
        """
        Advance ETA counters. Complete materializations that reach ETA=0.
        sessions: {session_id: SessionState}
        """
        for key, obj in list(self.objects.items()):
            if obj.being_materialized:
                obj.eta_epochs -= 1
                if obj.eta_epochs <= 0:
                    sid = obj.session_id
                    L = sessions[sid].L if sid in sessions else 0
                    # Only complete if there's still capacity
                    needed = self._cm.s_ready_gb(obj.fidelity, L)
                    cap = nodes[obj.node_id].capacity_gb
                    used = self.node_capacity_used.get(obj.node_id, 0.0)
                    if used + needed <= cap + 1e-9:
                        self.node_capacity_used[obj.node_id] = used + needed
                        obj.ready = True
                    obj.being_materialized = False
                    obj.eta_epochs = 0

    def increment_staleness(self, session_ids: list):
        """Increment staleness of all ready objects for listed sessions."""
        for key, obj in self.objects.items():
            if obj.session_id in session_ids and obj.ready:
                obj.staleness += 1

    def reset_staleness(self, session_id: int, node_id: str, fidelity: str):
        key = self._key(session_id, node_id, fidelity)
        if key in self.objects:
            self.objects[key].staleness = 0
