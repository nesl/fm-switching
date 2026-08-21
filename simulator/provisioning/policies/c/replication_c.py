"""
ReplicationC: provision full KV at every reachable node.
Uses shared allocator; uniform P_serve across reachable nodes.
Containment: full is in joint's space → always passes.
"""
from __future__ import annotations
from ...solver_c import greedy_knapsack, _s_ready_gb, _cold_prefill_s
from ..base import ProvisioningDecision


class ReplicationC:
    name = "replication"
    is_joint = False
    is_oracle = False

    def reset(self):
        self.last_candidate_set = set()

    def decide_c(self, sessions, prov_state, reachable_nodes, epoch, vf, nodes,
                 serving_distribution, current_regimes, tau, infeasibility_map):
        n_reachable = max(1, len(reachable_nodes))
        candidates = []
        for sid, sess in sessions.items():
            L = sess.L
            for nid in reachable_nodes:
                # Skip if infeasible for full
                max_l = infeasibility_map.get(nid)
                if max_l is not None and L > max_l:
                    continue
                P_serve = 1.0 / n_reachable
                tier = nodes[nid].tier if hasattr(nodes[nid], "tier") else "cloud"
                cold_s = _cold_prefill_s(L, tier)
                if cold_s == float("inf"):
                    cold_s = _cold_prefill_s(L, "cloud")
                val = P_serve * cold_s  # sufficient always True for full
                s = _s_ready_gb("full", L)
                dens = val / s if s > 0 else 0.0
                candidates.append({
                    "session_id": sid, "node_id": nid, "fidelity": "full",
                    "value": val, "density": dens, "s_ready_gb": s,
                })
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
