"""
HandoverSched: Lee-style delay-only handoff policy for E24b.

On handoff (next serving node ≠ current serving node):
  - Ship KV if transfer_cost + prefill_at_target < cold_prefill_at_target
  - Otherwise: let reactive cold-prefill at target.
Always full fidelity, no pre-provisioning otherwise.

Oracle parity: uses next_serving_nodes (1 epoch ahead) to detect upcoming
handoffs and pre-schedule the transfer decision.
"""

from .base import BasePolicy, ProvisioningDecision
from ..topology_b import EDGE_MAX_L_FULL


class HandoverSchedPolicy(BasePolicy):
    @property
    def name(self) -> str:
        return "handover_sched"

    def reset(self):
        self._prev_serving: dict = {}

    def decide(self, sessions, prov_state, reachable_nodes, epoch,
               cost_model, nodes, next_serving_nodes, future_regimes, **kwargs):
        infeasibility_map = kwargs.get("infeasibility_map", {})
        decisions = []

        for sid, sess in sessions.items():
            current_node = sess.serving_node
            next_node = next_serving_nodes.get(sid, current_node)

            # Check infeasibility at next node for full
            if infeasibility_map.get(next_node) is not None and sess.L > infeasibility_map[next_node]:
                next_node = "cloud"

            if next_node == current_node:
                # No handoff — maintain current full KV
                obj = prov_state.get(sid, current_node, "full")
                in_flight = prov_state.being_materialized_at(sid, current_node, 0.0, sess.regime)
                if obj and obj.ready:
                    if obj.staleness > 0:
                        decisions.append(ProvisioningDecision(
                            session_id=sid, node_id=current_node,
                            fidelity="full", action="refresh"))
                    continue
                if in_flight:
                    continue
                if prov_state.can_fit(current_node, "full", sess.L, nodes):
                    decisions.append(ProvisioningDecision(
                        session_id=sid, node_id=current_node,
                        fidelity="full", action="materialize"))
                continue

            # Handoff detected: decide ship vs re-prefill
            if next_node not in nodes:
                continue

            target_tier = nodes[next_node].tier
            # Transfer cost (text-format): marginal vs cold prefill at target
            transfer_cost = cost_model.transfer_s("full", sess.L)
            # After transfer, still need to prefill at target (stored → ready)
            prefill_at_target = cost_model.cold_prefill_s(
                sess.L, slowdown=nodes[next_node].prefill_slowdown)
            total_ship = transfer_cost + prefill_at_target

            # Cold prefill at target from scratch (no text transfer needed,
            # assumes text always stored locally at requesting tier)
            cold_at_target = prefill_at_target

            obj = prov_state.get(sid, next_node, "full")
            in_flight = prov_state.being_materialized_at(sid, next_node, 0.0, sess.regime)
            if obj and obj.ready:
                continue
            if in_flight:
                continue

            # Ship is beneficial if it avoids additional transfer overhead
            # (both paths pay cold_prefill_at_target; ship adds transfer on top)
            # Actual benefit: ship saves nothing vs cold if only text is transferred.
            # Real benefit: if full KV is already ready at current node, can skip
            # cold prefill entirely with KV transfer (but KV transfer over WAN is
            # infeasible per FORMULATION.md). So handover_sched can only move text
            # and re-prefill — it equals reactive for latency, but with 1 epoch lead
            # allows materialization to complete before handoff.
            # Decision: if total_ship < cold_at_target (impossible since total_ship
            # = transfer + prefill >= prefill), materialize 1 epoch early at target.
            # Practical gain: materialization started 1 epoch ahead → warm on arrival.
            if prov_state.can_fit(next_node, "full", sess.L, nodes):
                decisions.append(ProvisioningDecision(
                    session_id=sid, node_id=next_node,
                    fidelity="full", action="materialize"))

        return decisions
