"""
FidelityFirstLifecycle: stage-1 selects fidelity per session by expected lifecycle cost,
not cheapest-sufficient size. Stage-2 runs the shared allocator over all nodes.

Lifecycle cost:
  expected_lifecycle_cost(f, L) = materialize_cost(f, L) + MEAN_EPOCHS_HELD * refresh_cost_per_epoch(f, L)

Node tier for all costs: cloud (a6000, 1.0x slowdown) — scalar reference independent of placement.
MEAN_EPOCHS_HELD = 10 — assumed; not tuned; documented here.

This is the "strong decomposed" baseline. fidelity_first (cheapest-sufficient by S_ready size)
is the "weak" variant. Both appear in all result tables for comparison.

Refresh cost difference between fidelity types:
  full/win: warm_append only — cheap (0.066-0.33s per epoch)
  sum80/sum200: cold_prefill of full context — expensive (up to 21.7s per epoch at L=65k)
At mid-to-large L, this makes win the lifecycle-optimal choice over sum80/sum200.
"""
from __future__ import annotations
from ...quality_b import sufficient
from ...solver_c import build_candidates, greedy_knapsack, _cold_prefill_s
from ..base import ProvisioningDecision

MEAN_EPOCHS_HELD = 10

_SUM80_MAT_S  = 0.027  # materialize cost for sum80 (stored text → restore, phase-1 measured)
_SUM200_MAT_S = 0.031  # materialize cost for sum200


def _warm_append_s(tok: int) -> float:
    return max(0.066, 0.330 * tok / 65536)


def _lifecycle_cost(f: str, L: int) -> float:
    """Expected lifecycle cost in seconds using cloud tier as reference."""
    if f == "full":
        mat = _cold_prefill_s(L, "cloud")
        ref = _warm_append_s(L)
    elif f == "win":
        # Materializing win = prefilling win-window (2048 tokens)
        mat = _cold_prefill_s(2048, "cloud")
        ref = _warm_append_s(2048)
    elif f == "sum200":
        mat = _SUM200_MAT_S
        ref = _cold_prefill_s(L, "cloud")   # must re-read full context to refresh
    elif f == "sum80":
        mat = _SUM80_MAT_S
        ref = _cold_prefill_s(L, "cloud")
    else:
        return float("inf")
    return mat + MEAN_EPOCHS_HELD * ref


def cheapest_lifecycle_tau(regime: str, L: int, tau: float) -> str:
    """Return fidelity with min lifecycle cost among those meeting sufficiency at tau."""
    candidates = []
    for f in ("sum80", "sum200", "win", "full"):
        if sufficient(f, regime, tau):
            candidates.append((f, _lifecycle_cost(f, L)))
    if not candidates:
        return "full"
    return min(candidates, key=lambda x: x[1])[0]


class FidelityFirstLifecycle:
    name = "fidelity_first_lifecycle"
    is_joint = False
    is_oracle = False

    def reset(self):
        self.last_candidate_set = set()

    def decide_c(self, sessions, prov_state, reachable_nodes, epoch, vf, nodes,
                 serving_distribution, current_regimes, tau, infeasibility_map):
        L_map = {sid: sess.L for sid, sess in sessions.items()}

        def fidelity_filter(sid, regime):
            return cheapest_lifecycle_tau(regime, L_map[sid], tau)

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
