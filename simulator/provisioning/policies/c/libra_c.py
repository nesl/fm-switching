"""
LibraC: current serving node only; budget-aware fidelity selection with LRU-style eviction.
Per-session budget = C_j / n_sessions. Chooses cheapest sufficient fidelity that fits budget;
falls back to cheaper fidelities if needed.
"""
from __future__ import annotations
from ...quality_b import cheapest_sufficient_tau, sufficient
from ...solver_c import greedy_knapsack, _s_ready_gb, _cold_prefill_s
from ..base import ProvisioningDecision

_FIDELITY_ORDER = ["sum80", "sum200", "win", "full"]


class LibraC:
    name = "libra_style"
    is_joint = False
    is_oracle = False

    def reset(self):
        self.last_candidate_set = set()

    def decide_c(self, sessions, prov_state, reachable_nodes, epoch, vf, nodes,
                 serving_distribution, current_regimes, tau, infeasibility_map):
        # Current serving node = first edge in reachable, else cloud
        serving = None
        for nid in ("edge0", "edge1", "edge2"):
            if nid in reachable_nodes:
                serving = nid
                break
        if serving is None:
            serving = "cloud"

        n_sessions = max(1, len(sessions))
        cap_j = nodes[serving].capacity_gb
        budget_per_sess = cap_j / n_sessions

        candidates = []
        for sid, sess in sessions.items():
            L = sess.L
            regime = current_regimes[sid]
            # Try cheapest sufficient first; if too large for budget, go cheaper
            fidelity_chosen = None
            for f in _FIDELITY_ORDER:
                if not sufficient(f, regime, tau):
                    continue
                if f == "full":
                    max_l = infeasibility_map.get(serving)
                    if max_l is not None and L > max_l:
                        continue
                s = _s_ready_gb(f, L)
                if s <= budget_per_sess + 1e-9:
                    fidelity_chosen = f
                    break

            if fidelity_chosen is None:
                continue  # no sufficient fidelity fits budget

            dist = serving_distribution.get(sid, {})
            P_serve = dist.get(serving, 0.0)
            val = vf.compute(sid, serving, fidelity_chosen, L, regime, P_serve)
            s = _s_ready_gb(fidelity_chosen, L)
            dens = val / s if s > 0 else 0.0
            candidates.append({
                "session_id": sid, "node_id": serving, "fidelity": fidelity_chosen,
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
