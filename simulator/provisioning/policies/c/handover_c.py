"""
HandoverC: decides ship-KV vs re-prefill at the target on predicted handoff.
Full fidelity only. Ships if transfer + 0.5*cold_prefill < cold_prefill at target
(0.5 factor accounts for overlapped transfer).
"""
from __future__ import annotations
from ...solver_c import _cold_prefill_s, _s_ready_gb
from ..base import ProvisioningDecision

_BW_MBPS = 10.0
_RTT_MS  = 50.0
_FULL_TEXT_BYTES_PER_TOK = 4


def _transfer_s(L: int) -> float:
    rtt_s = _RTT_MS / 1000.0
    text_bytes = _FULL_TEXT_BYTES_PER_TOK * L
    bw_bps = _BW_MBPS * 1e6
    return rtt_s + (text_bytes * 8) / bw_bps


class HandoverC:
    name = "handover_sched"
    is_joint = False
    is_oracle = False

    def reset(self): pass

    def decide_c(self, sessions, prov_state, reachable_nodes, epoch, vf, nodes,
                 serving_distribution, current_regimes, tau, infeasibility_map):
        decisions = []
        for sid, sess in sessions.items():
            current_serving = sess.serving_node
            dist = serving_distribution.get(sid, {})
            # Predicted next serving node
            next_node = max(dist, key=dist.get) if dist else current_serving

            # Only act on predicted handoff
            if next_node == current_serving:
                continue
            if next_node not in reachable_nodes:
                continue

            L = sess.L
            max_l = infeasibility_map.get(next_node)
            if max_l is not None and L > max_l:
                continue  # full KV infeasible at target

            tier = nodes[next_node].tier if hasattr(nodes[next_node], "tier") else "cloud"
            cold_s = _cold_prefill_s(L, tier)
            transfer_s = _transfer_s(L)

            # Ship if: transfer + 0.5*cold < cold  →  transfer < 0.5*cold
            if transfer_s < 0.5 * cold_s:
                obj = prov_state.get(sid, next_node, "full")
                if obj and obj.ready:
                    continue
                if prov_state.can_fit(next_node, "full", L, nodes):
                    decisions.append(ProvisioningDecision(
                        session_id=sid, node_id=next_node,
                        fidelity="full", action="materialize"))
        return decisions
