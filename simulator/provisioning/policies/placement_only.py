"""
Placement-only: mobility-aware node selection, always full fidelity.
Pre-provisions full at the predicted next-serving node; evicts from nodes
that are no longer reachable.
"""

from .base import BasePolicy, ProvisioningDecision


class PlacementOnlyPolicy(BasePolicy):
    @property
    def name(self) -> str:
        return "placement_only"

    def reset(self):
        pass

    def decide(self, sessions, prov_state, reachable_nodes, epoch,
               cost_model, nodes, next_serving_nodes, future_regimes):
        decisions = []
        for sid, sess in sessions.items():
            target_node = next_serving_nodes.get(sid)
            if target_node is None:
                continue
            obj = prov_state.get(sid, target_node, "full")
            in_flight = prov_state.being_materialized_at(sid, target_node, 0.0, sess.regime)
            if obj and obj.ready:
                if obj.staleness > 0:
                    decisions.append(ProvisioningDecision(
                        session_id=sid, node_id=target_node,
                        fidelity="full", action="refresh"))
                continue
            if in_flight:
                continue
            if prov_state.can_fit(target_node, "full", sess.L, nodes):
                decisions.append(ProvisioningDecision(
                    session_id=sid, node_id=target_node,
                    fidelity="full", action="materialize"))
        return decisions
