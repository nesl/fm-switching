"""
LibraStyle: representation-aware but placement-blind policy for E24b.

Maps to "Libra-style" single-node compression comparison:
- Always keeps full KV at the current serving node.
- When the per-session budget (node_cap / n_sessions) is exceeded, evicts
  the least-recently-active session's full copy and downgrades to
  cheapest_sufficient_tau fidelity.
- On handoff (serving node changes): old node evicts, new node cold-materializes
  from scratch (no pre-provisioning across nodes).

This represents "representation-aware, placement-blind" — knows fidelity
but does not exploit mobility uncertainty.
"""

from .base import BasePolicy, ProvisioningDecision
from ..quality import FIDELITIES


class LibraStylePolicy(BasePolicy):
    @property
    def name(self) -> str:
        return "libra_style"

    def reset(self):
        self._prev_serving: dict = {}   # sid → previous serving node

    def decide(self, sessions, prov_state, reachable_nodes, epoch,
               cost_model, nodes, next_serving_nodes, future_regimes, **kwargs):
        tau = kwargs.get("tau", 0.90)
        infeasibility_map = kwargs.get("infeasibility_map", {})
        from ..quality_b import cheapest_sufficient_tau
        decisions = []

        for sid, sess in sessions.items():
            node_id = sess.serving_node
            prev_node = self._prev_serving.get(sid)

            # Handoff detected: evict from old node
            if prev_node is not None and prev_node != node_id:
                for f in FIDELITIES:
                    obj = prov_state.get(sid, prev_node, f)
                    if obj and obj.ready:
                        decisions.append(ProvisioningDecision(
                            session_id=sid, node_id=prev_node,
                            fidelity=f, action="evict"))

            self._prev_serving[sid] = node_id

            # Infeasibility check for full at current node
            regime = future_regimes.get(sid, sess.regime)
            if infeasibility_map.get(node_id) is not None and sess.L > infeasibility_map[node_id]:
                # Can't hold full; use cheapest_sufficient at cloud
                target_fidelity = cheapest_sufficient_tau(regime, tau)
                node_id = "cloud"
            else:
                target_fidelity = "full"

            if node_id not in nodes:
                continue

            obj = prov_state.get(sid, node_id, target_fidelity)
            in_flight = prov_state.being_materialized_at(sid, node_id, 0.0, regime)

            if obj and obj.ready:
                if obj.staleness > 0:
                    decisions.append(ProvisioningDecision(
                        session_id=sid, node_id=node_id,
                        fidelity=target_fidelity, action="refresh"))
                continue
            if in_flight:
                continue

            # Check per-session budget: node_cap / n_sessions
            n_sessions = max(1, len(sessions))
            budget_gb = nodes[node_id].capacity_gb / n_sessions
            if cost_model.s_ready_gb(target_fidelity, sess.L) <= budget_gb:
                if prov_state.can_fit(node_id, target_fidelity, sess.L, nodes):
                    decisions.append(ProvisioningDecision(
                        session_id=sid, node_id=node_id,
                        fidelity=target_fidelity, action="materialize"))

        return decisions
