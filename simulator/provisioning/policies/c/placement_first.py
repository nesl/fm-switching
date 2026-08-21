"""
Placement_first: stage-1 fixes node = argmax P_serve per session;
stage-2 runs the shared allocator over all fidelities at that node.
"""
from __future__ import annotations
from ...solver_c import build_candidates, greedy_knapsack
from ..base import ProvisioningDecision


def _best_node(sid, reachable_nodes, serving_dist):
    dist = serving_dist.get(sid, {})
    best_node = None
    best_p = -1.0
    for nid in reachable_nodes:
        p = dist.get(nid, 0.0)
        if p > best_p or (p == best_p and (best_node is None or nid < best_node)):
            best_p = p
            best_node = nid
    return best_node or (reachable_nodes[0] if reachable_nodes else "cloud")


class PlacementFirst:
    name = "placement_first"
    is_joint = False
    is_oracle = False

    def reset(self):
        self.last_candidate_set = set()

    def decide_c(self, sessions, prov_state, reachable_nodes, epoch, vf, nodes,
                 serving_distribution, current_regimes, tau, infeasibility_map):
        L_map = {sid: sess.L for sid, sess in sessions.items()}

        def node_filter(sid, reachable):
            return [_best_node(sid, reachable, serving_distribution)]

        candidates = build_candidates(
            list(sessions.keys()), reachable_nodes, L_map, current_regimes,
            serving_distribution, vf, node_filter=node_filter,
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
