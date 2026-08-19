"""
Cache-value: greedy expected-value heuristic.

Expected value of provisioning fidelity f at node n for session s:
  EV = Q(f, regime) * P(serve at n next) - cost_weight * S_ready_gb(f, L)

P(serve at n next) = 1.0 if n == next_serving_node, else 0.1 (residual chance).
cost_weight balances quality gain against capacity cost.
Provisions the (f, n) pair with highest positive EV.
"""

from .base import BasePolicy, ProvisioningDecision
from ..quality import quality, FIDELITIES, CHEAPEST_SUFFICIENT

_COST_WEIGHT = 0.05   # GB^-1 units; balances quality vs capacity
_RESIDUAL_P  = 0.10   # probability of serving at non-predicted node


class CacheValuePolicy(BasePolicy):
    @property
    def name(self) -> str:
        return "cache_value"

    def reset(self):
        pass

    def decide(self, sessions, prov_state, reachable_nodes, epoch,
               cost_model, nodes, next_serving_nodes, future_regimes):
        decisions = []
        for sid, sess in sessions.items():
            predicted_node = next_serving_nodes.get(sid)
            regime = future_regimes.get(sid, sess.regime)
            best_ev = 0.0
            best_fidelity = None
            best_node = None

            for node_id in reachable_nodes:
                p_serve = 1.0 if node_id == predicted_node else _RESIDUAL_P
                for fidelity in FIDELITIES:
                    obj = prov_state.get(sid, node_id, fidelity)
                    if obj and obj.ready:
                        continue  # already provisioned
                    if not prov_state.can_fit(node_id, fidelity, sess.L, nodes):
                        continue
                    q = quality(fidelity, regime)
                    size_gb = cost_model.s_ready_gb(fidelity, sess.L)
                    ev = q * p_serve - _COST_WEIGHT * size_gb
                    if ev > best_ev:
                        best_ev = ev
                        best_fidelity = fidelity
                        best_node = node_id

            if best_node is not None and best_fidelity is not None:
                if not prov_state.being_materialized_at(sid, best_node, 0.0, regime):
                    decisions.append(ProvisioningDecision(
                        session_id=sid, node_id=best_node,
                        fidelity=best_fidelity, action="materialize"))
        return decisions
