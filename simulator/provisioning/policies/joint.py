"""
Joint: combines mobility-aware placement with fidelity selection.
Pre-provisions cheapest-sufficient fidelity at the predicted next-serving node.
Also evicts from nodes that won't be reachable next epoch.
"""

from .base import BasePolicy, ProvisioningDecision
from ..quality import CHEAPEST_SUFFICIENT


class JointPolicy(BasePolicy):
    @property
    def name(self) -> str:
        return "joint"

    def reset(self):
        pass

    def decide(self, sessions, prov_state, reachable_nodes, epoch,
               cost_model, nodes, next_serving_nodes, future_regimes, **kwargs):
        decisions = []
        for sid, sess in sessions.items():
            target_node = next_serving_nodes.get(sid)
            if target_node is None:
                continue
            regime = future_regimes.get(sid, sess.regime)
            target_fidelity = CHEAPEST_SUFFICIENT.get(regime, "full")

            obj = prov_state.get(sid, target_node, target_fidelity)
            in_flight = prov_state.being_materialized_at(
                sid, target_node, 0.0, regime)
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
