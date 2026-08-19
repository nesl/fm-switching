"""
FidelityOnlyB: tau-aware fidelity-only policy for E24b.

Selects cheapest_sufficient_tau(regime, tau) fidelity and provisions at
the current serving node only (no placement optimization).
"""

from .base import BasePolicy, ProvisioningDecision
from ..quality_b import cheapest_sufficient_tau


class FidelityOnlyBPolicy(BasePolicy):
    def __init__(self, tau: float = 0.90):
        self._tau = tau

    @property
    def name(self) -> str:
        return "fidelity_only"

    def reset(self):
        pass

    def decide(self, sessions, prov_state, reachable_nodes, epoch,
               cost_model, nodes, next_serving_nodes, future_regimes, **kwargs):
        tau = kwargs.get("tau", self._tau)
        infeasibility_map = kwargs.get("infeasibility_map", {})
        decisions = []

        for sid, sess in sessions.items():
            regime = future_regimes.get(sid, sess.regime)
            fidelity = cheapest_sufficient_tau(regime, tau)
            node_id = sess.serving_node

            # Infeasibility check
            if fidelity == "full":
                max_l = infeasibility_map.get(node_id)
                if max_l is not None and sess.L > max_l:
                    node_id = "cloud"

            if node_id not in nodes:
                continue

            obj = prov_state.get(sid, node_id, fidelity)
            in_flight = prov_state.being_materialized_at(sid, node_id, 0.0, regime)
            if obj and obj.ready:
                if obj.staleness > 0:
                    decisions.append(ProvisioningDecision(
                        session_id=sid, node_id=node_id,
                        fidelity=fidelity, action="refresh"))
                continue
            if in_flight:
                continue
            if prov_state.can_fit(node_id, fidelity, sess.L, nodes):
                decisions.append(ProvisioningDecision(
                    session_id=sid, node_id=node_id,
                    fidelity=fidelity, action="materialize"))

        return decisions
