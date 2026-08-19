"""
SimulationEngine: per-epoch loop for fidelity-provisioning simulation.

Epoch flow:
  1. advance_materializations (complete pending from last epoch)
  2. policy.decide() → execute decisions
  3. serving phase: for each session, classify outcome
  4. session advance (grow L, increment staleness)

Outcome classification per request (mutually exclusive, sum=1.0):
  warm_hit:   ready object at serving_node meets q_min, staleness=0
  warm_stale: ready object at serving_node meets q_min, staleness>0 (refresh needed)
  cold:       no ready object at serving_node → on-demand cold materialization
  degraded:   best ready object exists but Q(f, regime) < q_min

Capacity invariant: node_capacity_used[n] <= C_j for all n, all epochs.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .costs import CostModel, COST_MODEL
from .quality import quality, FIDELITIES, CHEAPEST_SUFFICIENT
from .state import ProvisioningState, SessionState
from .topology import DEFAULT_NODES, MobilityModel, Node


_NODE_PREFERENCE = ["edge", "cloud", "device"]   # prefer edge (lowest latency if present)


def _preferred_node(reachable: List[str], nodes: Dict[str, Node]) -> str:
    for n in _NODE_PREFERENCE:
        if n in reachable and n in nodes:
            return n
    return reachable[0]


@dataclass
class EpochRecord:
    epoch: int
    policy_name: str
    outcomes: Dict[str, int] = field(default_factory=dict)   # outcome → count
    capacity_max: Dict[str, float] = field(default_factory=dict)  # node_id → peak GB


LATENCY_SLO_S = 5.0   # seconds; warm_stale refresh exceeding this = SLO miss


@dataclass
class SimResult:
    policy_name: str
    n_epochs: int
    n_sessions: int
    outcome_totals: Dict[str, int] = field(default_factory=dict)
    outcome_fractions: Dict[str, float] = field(default_factory=dict)
    capacity_violations: int = 0
    epoch_records: List[EpochRecord] = field(default_factory=list)
    # Stage 2 extended metrics
    slo_fraction: float = 0.0          # quality AND latency SLO met
    capability_hit_rate: float = 0.0   # warm_hit (ready, q_ok, staleness=0)
    false_warm_hit_rate: float = 0.0   # degraded / n_requests
    placement_miss_rate: float = 0.0   # cold but sufficient exists elsewhere
    materialization_miss_rate: float = 0.0  # cold because mat in-flight
    cold_miss_rate: float = 0.0        # hard cold (no object anywhere sufficient)
    mean_quality: float = 0.0          # avg Q(f_served, regime)
    bytes_transferred_total: float = 0.0    # stored-text bytes moved by policy
    cold_materializations: int = 0     # on-demand cold-materialize events


class SimulationEngine:
    def __init__(self,
                 nodes: Dict[str, Node] = None,
                 cost_model: CostModel = None,
                 q_min: float = 0.30,
                 materialize_epochs: int = 1):
        """
        nodes: subset of node_ids to include in this run (e.g., {"edge", "cloud"}).
        materialize_epochs: epochs until a start_materialization call completes (default 1).
        """
        self.nodes = nodes or DEFAULT_NODES
        self.cm = cost_model or COST_MODEL
        self.q_min = q_min
        self.materialize_epochs = materialize_epochs

    def run(self, policy, sessions_cfg: List[dict], n_epochs: int,
            mobility_level: str = "moderate", seed: int = 42) -> SimResult:
        """
        Run simulation for one policy.

        sessions_cfg: list of dicts, each with keys:
          session_id, regime, L (initial), turn_rate, (optional) serving_node
        """
        policy.reset()
        node_ids = list(self.nodes.keys())

        # Build MobilityModel
        mob = MobilityModel(mobility_level, n_epochs, seed=seed, nodes=self.nodes)

        # Initialize sessions
        sessions: Dict[int, SessionState] = {}
        for cfg in sessions_cfg:
            reachable0 = mob.reachable_nodes(0)
            default_node = _preferred_node(reachable0, self.nodes)
            sessions[cfg["session_id"]] = SessionState(
                session_id=cfg["session_id"],
                regime=cfg["regime"],
                L=cfg["L"],
                turn_rate=cfg.get("turn_rate", 200),
                serving_node=cfg.get("serving_node", default_node),
            )

        prov_state = ProvisioningState(node_ids, self.cm)

        outcomes_total: Dict[str, int] = {
            "warm_hit": 0, "warm_stale": 0, "cold": 0, "degraded": 0}
        epoch_records: List[EpochRecord] = []
        capacity_violations = 0

        # Stage 2 extended counters
        slo_met = 0
        quality_sum = 0.0
        bytes_transferred = 0.0
        cold_mat_count = 0
        placement_miss_count = 0
        mat_miss_count = 0
        hard_cold_count = 0

        node_ids_all = list(self.nodes.keys())

        for epoch in range(n_epochs):
            reachable = mob.reachable_nodes(epoch)
            next_reachable = mob.next_reachable_nodes(epoch)

            # Determine per-session serving node this epoch
            serving_nodes: Dict[int, str] = {}
            for sid, sess in sessions.items():
                serving_nodes[sid] = _preferred_node(reachable, self.nodes)
                sess.serving_node = serving_nodes[sid]

            # oracle-parity: next-epoch serving nodes (all policies get this)
            next_serving_nodes: Dict[int, str] = {
                sid: _preferred_node(next_reachable, self.nodes)
                for sid in sessions
            }

            # oracle-parity: regime is fixed (no drift in smoke test)
            future_regimes: Dict[int, str] = {
                sid: sess.regime for sid, sess in sessions.items()
            }

            # Step 1: complete pending materializations
            prov_state.advance_materializations(self.nodes, sessions)

            # Step 2: policy decides; execute decisions
            decisions = policy.decide(
                sessions=sessions,
                prov_state=prov_state,
                reachable_nodes=reachable,
                epoch=epoch,
                cost_model=self.cm,
                nodes=self.nodes,
                next_serving_nodes=next_serving_nodes,
                future_regimes=future_regimes,
            )
            bytes_transferred += self._execute_decisions(decisions, prov_state, sessions)

            # Step 3: serving phase — classify outcomes
            epoch_outcomes: Dict[str, int] = {
                "warm_hit": 0, "warm_stale": 0, "cold": 0, "degraded": 0}
            for sid, sess in sessions.items():
                node_id = serving_nodes[sid]
                outcome, is_slo, q_served, miss_sub = self._classify_extended(
                    prov_state, sid, node_id, sess, node_ids_all)
                epoch_outcomes[outcome] += 1
                outcomes_total[outcome] += 1
                quality_sum += q_served
                if is_slo:
                    slo_met += 1
                if miss_sub == "placement":
                    placement_miss_count += 1
                elif miss_sub == "mat":
                    mat_miss_count += 1
                elif miss_sub == "hard_cold":
                    hard_cold_count += 1

                # On-demand cold materialize (reactive baseline behavior)
                if outcome == "cold":
                    cold_mat_count += 1
                    prov_state.make_ready(sid, node_id, "full", sess.L, staleness=0)

            # Step 4: verify capacity invariant
            rec = EpochRecord(epoch=epoch, policy_name=policy.name,
                              outcomes=dict(epoch_outcomes))
            for node_id, used in prov_state.node_capacity_used.items():
                cap = self.nodes[node_id].capacity_gb
                rec.capacity_max[node_id] = used
                if used > cap + 1e-6:
                    capacity_violations += 1

            epoch_records.append(rec)

            # Step 5: advance sessions
            prov_state.increment_staleness(list(sessions.keys()))
            for sess in sessions.values():
                sess.advance()

        # Build result
        n_requests = n_epochs * len(sessions)
        fractions = {k: v / n_requests for k, v in outcomes_total.items()}

        return SimResult(
            policy_name=policy.name,
            n_epochs=n_epochs,
            n_sessions=len(sessions),
            outcome_totals=outcomes_total,
            outcome_fractions=fractions,
            capacity_violations=capacity_violations,
            epoch_records=epoch_records,
            slo_fraction=slo_met / n_requests,
            capability_hit_rate=outcomes_total["warm_hit"] / n_requests,
            false_warm_hit_rate=outcomes_total["degraded"] / n_requests,
            placement_miss_rate=placement_miss_count / n_requests,
            materialization_miss_rate=mat_miss_count / n_requests,
            cold_miss_rate=hard_cold_count / n_requests,
            mean_quality=quality_sum / n_requests,
            bytes_transferred_total=bytes_transferred,
            cold_materializations=cold_mat_count,
        )

    def _execute_decisions(self, decisions, prov_state: ProvisioningState,
                           sessions: Dict[int, SessionState]) -> float:
        """Execute decisions; return total stored-text bytes transferred."""
        bytes_moved = 0.0
        for dec in decisions:
            sid = dec.session_id
            sess = sessions.get(sid)
            if sess is None:
                continue
            if dec.action == "materialize":
                if prov_state.can_fit(dec.node_id, dec.fidelity, sess.L, self.nodes):
                    prov_state.start_materialization(
                        sid, dec.node_id, dec.fidelity,
                        eta_epochs=self.materialize_epochs)
                    bytes_moved += self.cm.transfer_s(dec.fidelity, sess.L) * 10e6
            elif dec.action == "refresh":
                obj = prov_state.get(sid, dec.node_id, dec.fidelity)
                if obj and obj.ready:
                    prov_state.reset_staleness(sid, dec.node_id, dec.fidelity)
            elif dec.action == "evict":
                prov_state.evict(sid, dec.node_id, dec.fidelity, sess.L)
            elif dec.action in ("store", "noop"):
                pass
        return bytes_moved

    def _classify_extended(self, prov_state: ProvisioningState, sid: int,
                           node_id: str, sess: SessionState,
                           all_node_ids: list):
        """
        Returns (outcome, is_slo_met, q_served, miss_subtype).
        miss_subtype: "placement" | "mat" | "hard_cold" | None
        """
        best = prov_state.best_ready_object(sid, node_id, self.q_min, sess.regime)
        if best is None:
            any_ready = None
            for fidelity in FIDELITIES:
                obj = prov_state.get(sid, node_id, fidelity)
                if obj and obj.ready:
                    any_ready = obj
                    break
            if any_ready is not None:
                q = quality(any_ready.fidelity, sess.regime)
                if q < self.q_min:
                    return ("degraded", False, q, None)
            # cold — determine subtype
            if prov_state.being_materialized_at(sid, node_id, self.q_min, sess.regime):
                miss_sub = "mat"
            elif prov_state.any_sufficient_elsewhere(sid, node_id, self.q_min,
                                                      sess.regime, all_node_ids):
                miss_sub = "placement"
            else:
                miss_sub = "hard_cold"
            return ("cold", False, 0.0, miss_sub)
        # Ready and quality-sufficient
        q = quality(best.fidelity, sess.regime)
        if best.staleness > 0:
            refresh_cost = self.cm.refresh_s(best.fidelity, sess.L)
            slo_met = refresh_cost <= LATENCY_SLO_S
            return ("warm_stale", slo_met, q, None)
        return ("warm_hit", True, q, None)

    def _classify(self, prov_state: ProvisioningState, sid: int,
                  node_id: str, sess: SessionState) -> str:
        """Backward-compat wrapper."""
        outcome, _, _, _ = self._classify_extended(
            prov_state, sid, node_id, sess, list(self.nodes.keys()))
        return outcome
