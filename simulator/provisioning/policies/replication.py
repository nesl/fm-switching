"""
Replication (RoutedSync-derived): maintain ready-full at every reachable node.
Eviction rule: when capacity exceeded, evict session with largest S_ready(full, L)
that is NOT the current serving session.
"""

from .base import BasePolicy, ProvisioningDecision
from ..quality import quality


class ReplicationPolicy(BasePolicy):
    @property
    def name(self) -> str:
        return "replication"

    def reset(self):
        pass

    def decide(self, sessions, prov_state, reachable_nodes, epoch,
               cost_model, nodes, next_serving_nodes, future_regimes, **kwargs):
        decisions = []
        for node_id in reachable_nodes:
            node = nodes[node_id]
            # Try to provision full-fidelity for each session at this node
            for sid, sess in sessions.items():
                obj = prov_state.get(sid, node_id, "full")
                if obj and obj.ready:
                    # Refresh if stale
                    if obj.staleness > 0:
                        decisions.append(ProvisioningDecision(
                            session_id=sid, node_id=node_id,
                            fidelity="full", action="refresh"))
                    continue
                # Not ready — try to materialize
                if prov_state.can_fit(node_id, "full", sess.L, nodes):
                    decisions.append(ProvisioningDecision(
                        session_id=sid, node_id=node_id,
                        fidelity="full", action="materialize"))
                else:
                    # Evict largest non-serving session to make room
                    evicted = self._evict_largest(node_id, sess.L, sess.session_id,
                                                   sessions, prov_state, cost_model, nodes)
                    if evicted:
                        decisions.append(ProvisioningDecision(
                            session_id=sid, node_id=node_id,
                            fidelity="full", action="materialize"))
        return decisions

    def _evict_largest(self, node_id, needed_L, protect_sid, sessions, prov_state,
                       cost_model, nodes):
        """Evict the session with largest ready-full footprint, except protect_sid."""
        candidates = []
        for key, obj in prov_state.objects.items():
            s_id, n_id, fid = key
            if n_id != node_id or fid != "full" or not obj.ready:
                continue
            if s_id == protect_sid:
                continue
            L_i = sessions[s_id].L if s_id in sessions else 0
            candidates.append((cost_model.s_ready_gb("full", L_i), s_id, L_i))
        if not candidates:
            return False
        candidates.sort(reverse=True)
        _, evict_sid, evict_L = candidates[0]
        prov_state.evict(evict_sid, node_id, "full", evict_L)
        return True
