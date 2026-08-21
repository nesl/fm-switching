"""
Fidelity_first: stage-1 fixes fidelity = cheapest_sufficient per session;
stage-2 runs the shared allocator over all nodes with that fidelity fixed.
"""
from __future__ import annotations
from ...quality_b import cheapest_sufficient_tau
from ...solver_c import build_candidates, greedy_knapsack
from ..base import ProvisioningDecision


class FidelityFirst:
    name = "fidelity_first"
    is_joint = False
    is_oracle = False

    def reset(self):
        self.last_candidate_set = set()

    def decide_c(self, sessions, prov_state, reachable_nodes, epoch, vf, nodes,
                 serving_distribution, current_regimes, tau, infeasibility_map):
        L_map = {sid: sess.L for sid, sess in sessions.items()}

        def fidelity_filter(sid, regime):
            return cheapest_sufficient_tau(regime, tau)

        candidates = build_candidates(
            list(sessions.keys()), reachable_nodes, L_map, current_regimes,
            serving_distribution, vf, fidelity_filter=fidelity_filter,
            infeasibility_map=infeasibility_map)
        self.last_candidate_set = {(c["session_id"], c["node_id"], c["fidelity"])
                                    for c in candidates}
        placed = greedy_knapsack(candidates, nodes, prov_state, sessions)
        decisions = []
        for item in placed:
            obj = prov_state.get(item["session_id"], item["node_id"], item["fidelity"])
            if obj and obj.ready:
                continue
            decisions.append(ProvisioningDecision(
                session_id=item["session_id"],
                node_id=item["node_id"],
                fidelity=item["fidelity"],
                action="materialize",
            ))
        return decisions
