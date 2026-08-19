"""
SimulationEngineB: extended simulation engine for E24b.

Extensions over E24 engine:
- 3-edge topology (MobilityModel3Edge)
- Node-tier-specific cold-prefill costs (rtx3090ti vs a6000)
- infeasibility_map: prevents placing full KV on edge nodes when L > max_L_feasible
- Regime drift: sessions cycle through regimes at a configurable rate
- Per-request latency tracking (for p95/p99)
- L-band SLO breakdown (small/mid/large)
- Oracle-domination assertion
- next_2_reachable passed to oracle

Latency SLO = 5.0s (configurable).

Cold-miss materialization: ONLY if prov_state.can_fit() — tight capacity means
some cold misses remain cold every epoch. This is correct behavior.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .quality import FIDELITIES, Q_TABLE
from .quality_b import cheapest_sufficient_tau
from .state import ProvisioningState, SessionState
from .topology_b import MobilityModel3Edge, NodeB

# RTX3090Ti cold-prefill table (measured, E22); feasible up to L=32768
_RTX_L = [1024, 2048, 4096, 8192, 16384, 24576, 32768]
_RTX_S = [0.220, 0.468, 0.982, 2.028, 4.868, 8.525, 13.694]
# a6000 cold-prefill table (measured, E21); extrapolate beyond 65536
_A6K_L = [1024, 2048, 4096, 8192, 16384, 24576, 32768, 49152, 65536]
_A6K_S = [0.165, 0.325, 0.667, 1.369, 3.090, 5.245, 7.805, 14.820, 21.720]

LATENCY_SLO_S = 5.0
L_BAND_SMALL_MAX = 16384
L_BAND_MID_MAX   = 40960

_REGIME_DRIFT_ORDER = ["compressible", "mixed_sensitive", "dense"]


def _l_band(L: int) -> str:
    if L <= L_BAND_SMALL_MAX:
        return "small"
    if L <= L_BAND_MID_MAX:
        return "mid"
    return "large"


def _cold_prefill(L: int, tier: str) -> Tuple[float, bool]:
    """Returns (seconds, is_extrapolated). INFEASIBLE returns (inf, False)."""
    if tier == "edge":
        if L >= 49152:
            return float("inf"), False   # OOM — infeasible
        table_L, table_S = _RTX_L, _RTX_S
        if L > table_L[-1]:
            slope = (table_S[-1] - table_S[-2]) / (table_L[-1] - table_L[-2])
            return table_S[-1] + slope * (L - table_L[-1]), True  # EXTRAPOLATED
    else:
        table_L, table_S = _A6K_L, _A6K_S
        if L > table_L[-1]:
            slope = (table_S[-1] - table_S[-2]) / (table_L[-1] - table_L[-2])
            return table_S[-1] + slope * (L - table_L[-1]), True  # EXTRAPOLATED

    L_clamped = max(table_L[0], min(table_L[-1], L))
    idx = bisect.bisect_right(table_L, L_clamped)
    if idx == 0:
        return table_S[0], False
    if idx >= len(table_L):
        return table_S[-1], False
    L0, L1 = table_L[idx - 1], table_L[idx]
    t0, t1 = table_S[idx - 1], table_S[idx]
    return t0 + (t1 - t0) * (L_clamped - L0) / (L1 - L0), False


@dataclass
class SimResultB:
    policy_name: str
    n_epochs: int
    n_sessions: int
    tau: float
    drift_rate: int
    # Raw outcome fractions
    warm_hit: float = 0.0
    warm_stale: float = 0.0
    cold_miss: float = 0.0
    degraded: float = 0.0
    placement_miss: float = 0.0
    materialization_miss: float = 0.0
    infeasible_miss: float = 0.0
    # SLO: latency <= 5s AND quality threshold met
    slo_fraction: float = 0.0
    slo_by_band: Dict[str, float] = field(default_factory=dict)
    # Latency percentiles
    p50_latency_s: float = 0.0
    p95_latency_s: float = 0.0
    p99_latency_s: float = 0.0
    mean_latency_s: float = 0.0
    # Quality
    mean_quality: float = 0.0
    # Diagnostics
    capacity_violations: int = 0
    cold_materializations: int = 0
    extrapolated_points: int = 0


class SimulationEngineB:
    def __init__(self,
                 nodes: Dict[str, NodeB],
                 q_min_tau: float = 0.90,
                 latency_slo_s: float = LATENCY_SLO_S,
                 materialize_epochs: int = 1):
        self.nodes = nodes
        self.tau = q_min_tau
        self.latency_slo = latency_slo_s
        self.materialize_epochs = materialize_epochs
        self.infeasibility_map: Dict[str, Optional[int]] = {
            nid: n.max_L_feasible_full for nid, n in nodes.items()
        }

    def run(self, policy, sessions_cfg: List[dict], n_epochs: int,
            mobility_level: str = "moderate", seed: int = 42,
            drift_rate: int = 0) -> SimResultB:
        from .costs import COST_MODEL

        policy.reset()
        node_ids = list(self.nodes.keys())

        mob = MobilityModel3Edge(mobility_level, n_epochs, seed=seed)

        # Build sessions
        sessions: Dict[int, SessionState] = {}
        for cfg in sessions_cfg:
            sess = SessionState(
                session_id=cfg["session_id"],
                regime=cfg["regime"],
                L=cfg["L"],
                turn_rate=cfg.get("turn_rate", 880),
                serving_node=mob.serving_node(0),
            )
            sess._drift_rate = drift_rate
            sess._drift_epoch_counter = 0
            sess._regime_idx = (_REGIME_DRIFT_ORDER.index(cfg["regime"])
                                if cfg["regime"] in _REGIME_DRIFT_ORDER else 0)
            sessions[cfg["session_id"]] = sess

        prov_state = ProvisioningState(node_ids, COST_MODEL)

        totals = {k: 0 for k in ("warm_hit", "warm_stale", "cold_miss", "degraded",
                                   "placement_miss", "materialization_miss", "infeasible_miss")}
        slo_hits = 0
        band_hits: Dict[str, int] = {"small": 0, "mid": 0, "large": 0}
        band_total: Dict[str, int] = {"small": 0, "mid": 0, "large": 0}
        latencies: List[float] = []
        qualities: List[float] = []
        capacity_violations = 0
        cold_mats = 0
        extrap_points = 0

        for epoch in range(n_epochs):
            # Drift: cycle regimes
            if drift_rate > 0:
                for sess in sessions.values():
                    sess._drift_epoch_counter += 1
                    if sess._drift_epoch_counter >= drift_rate:
                        sess._drift_epoch_counter = 0
                        sess._regime_idx = (sess._regime_idx + 1) % len(_REGIME_DRIFT_ORDER)
                        sess.regime = _REGIME_DRIFT_ORDER[sess._regime_idx]

            reachable = mob.reachable_nodes(epoch)
            next_serving = {sid: mob.next_serving_node(epoch) for sid in sessions}
            next_2 = mob.reachable_next_2(epoch)
            future_regimes = {sid: sess.regime for sid, sess in sessions.items()}

            serve_node = mob.serving_node(epoch)
            for sess in sessions.values():
                sess.serving_node = serve_node

            # Step 1: advance materializations
            prov_state.advance_materializations(self.nodes, sessions)

            # Step 2: policy decides
            decisions = policy.decide(
                sessions=sessions,
                prov_state=prov_state,
                reachable_nodes=reachable,
                epoch=epoch,
                cost_model=COST_MODEL,
                nodes=self.nodes,
                next_serving_nodes=next_serving,
                future_regimes=future_regimes,
                tau=self.tau,
                infeasibility_map=self.infeasibility_map,
                next_2_reachable=next_2,
            )
            self._execute_decisions(decisions, prov_state, sessions)

            # Step 3: classify outcomes
            for sid, sess in sessions.items():
                node_id = sess.serving_node
                tier = self.nodes[node_id].tier
                outcome, latency_s, quality_val, is_extrap = self._classify(
                    prov_state, sid, node_id, sess, tier)

                if is_extrap:
                    extrap_points += 1

                totals[outcome] += 1
                latencies.append(latency_s)
                qualities.append(quality_val)

                band = _l_band(sess.L)
                band_total[band] += 1

                # SLO hit: latency <= SLO AND quality met (outcome is warm)
                if latency_s <= self.latency_slo and outcome in ("warm_hit", "warm_stale"):
                    slo_hits += 1
                    band_hits[band] += 1

                # Reactive cold materialization — only if capacity allows
                if outcome == "cold_miss":
                    cold_s_val, _ = _cold_prefill(sess.L, tier)
                    if cold_s_val != float("inf"):
                        # Check infeasibility
                        max_l = self.infeasibility_map.get(node_id)
                        if max_l is None or sess.L <= max_l:
                            if prov_state.can_fit(node_id, "full", sess.L, self.nodes):
                                prov_state.make_ready(sid, node_id, "full", sess.L, staleness=0)
                                cold_mats += 1

            # Capacity violations check
            for node_id, used in prov_state.node_capacity_used.items():
                cap = self.nodes[node_id].capacity_gb
                if used > cap + 1e-6:
                    capacity_violations += 1

            # Step 4: advance sessions
            prov_state.increment_staleness(list(sessions.keys()))
            for sess in sessions.values():
                sess.advance()

        n_requests = n_epochs * len(sessions)
        fracs = {k: v / n_requests for k, v in totals.items()}
        slo_frac = slo_hits / n_requests

        band_slo_frac = {
            b: (band_hits[b] / band_total[b] if band_total[b] > 0 else 0.0)
            for b in ("small", "mid", "large")
        }

        latencies_sorted = sorted(latencies)
        n = len(latencies_sorted)
        p50 = latencies_sorted[int(0.50 * n)] if n else 0.0
        p95 = latencies_sorted[min(int(0.95 * n), n - 1)] if n else 0.0
        p99 = latencies_sorted[min(int(0.99 * n), n - 1)] if n else 0.0

        return SimResultB(
            policy_name=policy.name,
            n_epochs=n_epochs,
            n_sessions=len(sessions),
            tau=self.tau,
            drift_rate=drift_rate,
            warm_hit=fracs["warm_hit"],
            warm_stale=fracs["warm_stale"],
            cold_miss=fracs["cold_miss"],
            degraded=fracs["degraded"],
            placement_miss=fracs["placement_miss"],
            materialization_miss=fracs["materialization_miss"],
            infeasible_miss=fracs["infeasible_miss"],
            slo_fraction=slo_frac,
            slo_by_band=band_slo_frac,
            p50_latency_s=p50,
            p95_latency_s=p95,
            p99_latency_s=p99,
            mean_latency_s=sum(latencies) / n if n else 0.0,
            mean_quality=sum(qualities) / n if n else 0.0,
            capacity_violations=capacity_violations,
            cold_materializations=cold_mats,
            extrapolated_points=extrap_points,
        )

    def _execute_decisions(self, decisions, prov_state: ProvisioningState,
                           sessions: Dict[int, SessionState]):
        for dec in decisions:
            sid = dec.session_id
            sess = sessions.get(sid)
            if sess is None:
                continue
            if dec.action == "materialize":
                if dec.fidelity == "full":
                    max_l = self.infeasibility_map.get(dec.node_id)
                    if max_l is not None and sess.L > max_l:
                        continue  # infeasible — reject silently
                if prov_state.can_fit(dec.node_id, dec.fidelity, sess.L, self.nodes):
                    prov_state.start_materialization(
                        sid, dec.node_id, dec.fidelity,
                        eta_epochs=self.materialize_epochs)
            elif dec.action == "refresh":
                obj = prov_state.get(sid, dec.node_id, dec.fidelity)
                if obj and obj.ready:
                    prov_state.reset_staleness(sid, dec.node_id, dec.fidelity)
            elif dec.action == "evict":
                prov_state.evict(sid, dec.node_id, dec.fidelity, sess.L)
            elif dec.action in ("store", "noop"):
                pass

    def _classify(self, prov_state: ProvisioningState, sid: int,
                  node_id: str, sess: SessionState,
                  tier: str) -> Tuple[str, float, float, bool]:
        """Returns (outcome, latency_s, quality_val, is_extrapolated)."""
        from .quality import quality as q_fn
        regime = sess.regime
        cold_s, is_extrap = _cold_prefill(sess.L, tier)
        q_threshold = self.tau * Q_TABLE[regime]["full"]

        max_l = self.infeasibility_map.get(node_id)
        node_feasible = (max_l is None or sess.L <= max_l)

        best = prov_state.best_ready_object(sid, node_id, 0.0, regime)

        if best is None:
            if not node_feasible:
                return "infeasible_miss", float("inf"), 0.0, is_extrap
            # Check placement miss: sufficient copy elsewhere
            if prov_state.any_sufficient_elsewhere(
                    sid, node_id, q_threshold, regime, list(self.nodes.keys())):
                return "placement_miss", cold_s, 0.0, is_extrap
            # Check materialization miss: being materialized here
            if prov_state.being_materialized_at(sid, node_id, 0.0, regime):
                return "materialization_miss", cold_s, 0.0, is_extrap
            return "cold_miss", cold_s, 0.0, is_extrap

        q_val = q_fn(best.fidelity, regime)

        if q_val < q_threshold:
            return "degraded", cold_s, q_val, is_extrap

        # Quality SLO met — compute serving latency
        if best.fidelity == "full":
            refresh_per_epoch = max(0.066, 0.330 * sess.L / 65536)
        elif best.fidelity == "win":
            refresh_per_epoch = max(0.066, 0.330 * 2048 / 65536)
        elif best.fidelity in ("sum80", "sum200"):
            refresh_per_epoch = cold_s  # re-read full context
        else:
            refresh_per_epoch = 0.0

        if best.staleness == 0:
            return "warm_hit", 0.0, q_val, is_extrap
        return "warm_stale", refresh_per_epoch * best.staleness, q_val, is_extrap
