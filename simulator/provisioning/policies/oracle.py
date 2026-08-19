"""
Oracle: optimal provisioning given perfect knowledge of next serving node and regime.

Differences from joint:
1. Same cheapest-sufficient fidelity selection at next-serving node.
2. Additionally evicts all ready objects that are NOT at the next serving node
   (recovers capacity for future sessions; no residual at wrong nodes).
3. If cheapest-sufficient is already ready at target, skip; if a higher-cost
   fidelity is ready there instead, evict it and provision the cheaper one.
"""

from .base import BasePolicy, ProvisioningDecision
from ..quality import CHEAPEST_SUFFICIENT, FIDELITIES


class OraclePolicy(BasePolicy):
    @property
    def name(self) -> str:
        return "oracle"

    def reset(self):
        pass

    def decide(self, sessions, prov_state, reachable_nodes, epoch,
               cost_model, nodes, next_serving_nodes, future_regimes):
        decisions = []
        for sid, sess in sessions.items():
            target_node = next_serving_nodes.get(sid)
            if target_node is None:
                continue
            regime = future_regimes.get(sid, sess.regime)
            target_fidelity = CHEAPEST_SUFFICIENT.get(regime, "full")

            # Evict from any node that is neither the next-serving nor current-serving node
            current_node = sess.serving_node
            for node_id in list(nodes.keys()):
                if node_id == target_node or node_id == current_node:
                    continue
                for fidelity in FIDELITIES:
                    obj = prov_state.get(sid, node_id, fidelity)
                    if obj and obj.ready:
                        decisions.append(ProvisioningDecision(
                            session_id=sid, node_id=node_id,
                            fidelity=fidelity, action="evict"))

            # At target node: ensure cheapest-sufficient is ready
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
