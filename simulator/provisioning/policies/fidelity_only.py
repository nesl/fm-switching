"""
Fidelity-only: serve from current node always; select cheapest-sufficient fidelity.
No proactive mobility-aware placement. Evicts full KV if cheaper fidelity suffices.
"""

from .base import BasePolicy, ProvisioningDecision
from ..quality import CHEAPEST_SUFFICIENT


class FidelityOnlyPolicy(BasePolicy):
    @property
    def name(self) -> str:
        return "fidelity_only"

    def reset(self):
        pass

    def decide(self, sessions, prov_state, reachable_nodes, epoch,
               cost_model, nodes, next_serving_nodes, future_regimes, **kwargs):
        decisions = []
        for sid, sess in sessions.items():
            # Use current serving node, not next (no mobility awareness)
            node_id = sess.serving_node
            if node_id not in reachable_nodes and node_id not in nodes:
                continue
            target_fidelity = CHEAPEST_SUFFICIENT.get(sess.regime, "full")
            obj = prov_state.get(sid, node_id, target_fidelity)
            in_flight = prov_state.being_materialized_at(
                sid, node_id, 0.0, sess.regime)
            if obj and obj.ready:
                if obj.staleness > 0:
                    decisions.append(ProvisioningDecision(
                        session_id=sid, node_id=node_id,
                        fidelity=target_fidelity, action="refresh"))
                continue
            if in_flight:
                continue
            if prov_state.can_fit(node_id, target_fidelity, sess.L, nodes):
                decisions.append(ProvisioningDecision(
                    session_id=sid, node_id=node_id,
                    fidelity=target_fidelity, action="materialize"))
        return decisions
