"""
JointB: tau-aware joint policy for E24b.

Provisions cheapest_sufficient_tau(regime, tau) at next-serving node.
Falls back to cloud when edge node is infeasible (L > max_L_feasible_full
and fidelity == "full").
"""

from .base import BasePolicy, ProvisioningDecision
from ..quality_b import cheapest_sufficient_tau


class JointBPolicy(BasePolicy):
    def __init__(self, tau: float = 0.90):
        self._tau = tau

    @property
    def name(self) -> str:
        return "joint"

    def reset(self):
        pass

    def decide(self, sessions, prov_state, reachable_nodes, epoch,
               cost_model, nodes, next_serving_nodes, future_regimes, **kwargs):
        tau = kwargs.get("tau", self._tau)
        infeasibility_map = kwargs.get("infeasibility_map", {})
        decisions = []

        for sid, sess in sessions.items():
            regime = future_regimes.get(sid, sess.regime)
            target_fidelity = cheapest_sufficient_tau(regime, tau)
            target_node = next_serving_nodes.get(sid)
            if target_node is None:
                continue

            # Infeasibility fallback: if target_node can't hold full, try cloud
            if target_fidelity == "full":
                max_l = infeasibility_map.get(target_node)
                if max_l is not None and sess.L > max_l:
                    target_node = "cloud"

            if target_node not in nodes:
                continue

            obj = prov_state.get(sid, target_node, target_fidelity)
            in_flight = prov_state.being_materialized_at(sid, target_node, 0.0, regime)
            if obj and obj.ready:
                if obj.staleness > 0:
                    decisions.append(ProvisioningDecision(
                        session_id=sid, node_id=target_node,
                        fidelity=target_fidelity, action="refresh"))
                continue
            if in_flight:
                continue
            if prov_state.can_fit(target_node, target_fidelity, sess.L, nodes):
                decisions.append(ProvisioningDecision(
                    session_id=sid, node_id=target_node,
                    fidelity=target_fidelity, action="materialize"))

        return decisions
