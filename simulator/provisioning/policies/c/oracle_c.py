"""
OracleC: same allocator as joint, but P_serve=1.0 for true next serving node.
Also evicts objects at nodes not in the next 2-epoch window, if a sufficient
copy exists elsewhere (no fallback destruction).
"""
from __future__ import annotations
from ...solver_c import build_candidates, greedy_knapsack, _s_ready_gb
from ...quality_b import sufficient
from ...quality import FIDELITIES, Q_TABLE
from ..base import ProvisioningDecision


class OracleC:
    name = "oracle"
    is_joint = False
    is_oracle = True

    def reset(self): pass

    def decide_c(self, sessions, prov_state, reachable_nodes, epoch, vf, nodes,
                 serving_distribution, current_regimes, tau, infeasibility_map):
        """serving_distribution for oracle is {sid: {true_next: 1.0}}."""
        L_map = {sid: sess.L for sid, sess in sessions.items()}
        candidates = build_candidates(
            list(sessions.keys()), reachable_nodes, L_map, current_regimes,
            serving_distribution, vf, infeasibility_map=infeasibility_map)
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

        # Evict objects at nodes NOT predicted to serve next epoch,
        # only if the session has a sufficient copy elsewhere.
        for sid, sess in sessions.items():
            regime = current_regimes[sid]
            q_threshold = tau * Q_TABLE[regime]["full"]
            predicted_node = max(serving_distribution[sid], key=serving_distribution[sid].get)
            for nid in list(nodes.keys()):
                if nid == predicted_node:
                    continue
                for f in FIDELITIES:
                    obj = prov_state.get(sid, nid, f)
                    if obj and obj.ready:
                        # Only evict if a sufficient copy exists elsewhere
                        has_elsewhere = prov_state.any_sufficient_elsewhere(
                            sid, nid, q_threshold, regime, list(nodes.keys()))
                        if has_elsewhere:
                            decisions.append(ProvisioningDecision(
                                session_id=sid, node_id=nid,
                                fidelity=f, action="evict"))
        return decisions
