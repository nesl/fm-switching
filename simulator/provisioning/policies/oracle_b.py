"""
OracleB: corrected oracle for E24b.

Strategy: provision cheapest_sufficient at BOTH the current serving node AND
the next serving node, without evicting anything. This strictly dominates
JointB (which only targets next_serving_node) by additionally maintaining
coverage at the current serving node.

E24 failure: the original oracle evicted aggressively, destroying fallback
copies under high-mobility dense sessions. This version never evicts.

Oracle dominance by construction: oracle does everything joint does (provision
at next_serving) plus also maintains current_serving. If joint achieves
warm_hit, oracle also achieves warm_hit (same next_serving provision).
Additionally oracle may achieve warm_hit when the serving node stays the
same (current_serving provision).
"""

from .base import BasePolicy, ProvisioningDecision
from ..quality_b import cheapest_sufficient_tau


class OracleBPolicy(BasePolicy):
    def __init__(self, tau: float = 0.90):
        self._tau = tau

    @property
    def name(self) -> str:
        return "oracle"

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

            # Target both current serving and next serving
            target_nodes = set()
            target_nodes.add(sess.serving_node)
            next_n = next_serving_nodes.get(sid)
            if next_n:
                target_nodes.add(next_n)

            for node_id in target_nodes:
                if node_id not in nodes:
                    continue

                # Infeasibility: can't place full on edge beyond max_L
                f = fidelity
                if f == "full":
                    max_l = infeasibility_map.get(node_id)
                    if max_l is not None and sess.L > max_l:
                        # Infeasible at this node — skip (cloud always feasible)
                        if node_id == "cloud":
                            pass  # cloud has no limit
                        else:
                            continue

                obj = prov_state.get(sid, node_id, f)
                in_flight = prov_state.being_materialized_at(sid, node_id, 0.0, regime)

                if obj and obj.ready:
                    if obj.staleness > 0:
                        decisions.append(ProvisioningDecision(
                            session_id=sid, node_id=node_id,
                            fidelity=f, action="refresh"))
                    continue
                if in_flight:
                    continue
                if prov_state.can_fit(node_id, f, sess.L, nodes):
                    decisions.append(ProvisioningDecision(
                        session_id=sid, node_id=node_id,
                        fidelity=f, action="materialize"))

        return decisions
