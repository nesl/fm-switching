"""
SimulationEngineC: E24c engine.

Key changes from engine_b:
- All policies use the shared ValueFunction + greedy_knapsack (solver_c.py)
- Policies receive serving_node_distribution (5-epoch lookahead)
- Oracle receives true_next_serving as distribution {sid: {node: 1.0}}
- Containment assertion runs every epoch for all non-joint policies
- Oracle dominance assertion at end of run (reports violation, does not silence)
"""
from __future__ import annotations

import bisect
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .quality import FIDELITIES, Q_TABLE
from .quality_b import cheapest_sufficient_tau
from .solver_c import (
    ValueFunction, greedy_knapsack, build_candidates, assert_joint_contains,
    _cold_prefill_s, _s_ready_gb,
)
from .state import ProvisioningState, SessionState
from .topology_b import MobilityModel3Edge, NodeB

LATENCY_SLO_S = 5.0
L_BAND_SMALL_MAX = 16384
L_BAND_MID_MAX   = 40960

_REGIME_DRIFT_ORDER = ["compressible", "mixed_sensitive", "dense"]
_FIDELITY_SIZE_ORDER = ["sum80", "sum200", "win", "full"]


def _l_band(L: int) -> str:
    if L <= L_BAND_SMALL_MAX:
        return "small"
    if L <= L_BAND_MID_MAX:
        return "mid"
    return "large"


def _preferred_node(reachable: List[str]) -> str:
    for prefix in ("edge0", "edge1", "edge2"):
        if prefix in reachable:
            return prefix
    return "cloud"


def _serving_distribution(mob: MobilityModel3Edge, epoch: int, n_epochs: int,
                           lookahead: int = 5) -> Dict[str, float]:
    counts: Dict[str, int] = {}
    n = 0
    for k in range(1, min(lookahead + 1, n_epochs - epoch)):
        serving = mob.serving_node(epoch + k)
        counts[serving] = counts.get(serving, 0) + 1
        n += 1
    if n == 0:
        return {"cloud": 1.0}
    return {node: c / n for node, c in counts.items()}


@dataclass
class SimResultC:
    policy_name: str
    n_epochs: int
    n_sessions: int
    tau: float
    drift_rate: int
    slo_fraction: float = 0.0
    slo_by_band: Dict[str, float] = field(default_factory=dict)
    warm_hit: float = 0.0
    warm_stale: float = 0.0
    cold_miss: float = 0.0
    degraded: float = 0.0
    placement_miss: float = 0.0
    materialization_miss: float = 0.0
    infeasible_miss: float = 0.0
    p95_latency_s: float = 0.0
    p99_latency_s: float = 0.0
    mean_latency_s: float = 0.0
    mean_quality: float = 0.0
    capacity_violations: int = 0
    cold_materializations: int = 0
    containment_violations: int = 0
    oracle_dominance_violation: bool = False
    # Addition 2: refresh instrumentation
    total_refresh_cost_s: float = 0.0
    refresh_events_by_fidelity: Dict[str, int] = field(default_factory=dict)
    slo_fail_on_refresh_fraction: float = 0.0
    mean_staleness_at_serve: float = 0.0
    # Addition 3: multi-fidelity diagnostic (joint only; 0.0 for other policies)
    multi_fidelity_sessions_fraction: float = 0.0
    multi_fidelity_slo_delta: float = 0.0


class SimulationEngineC:
    def __init__(self, nodes: Dict[str, NodeB], tau: float = 0.90,
                 latency_slo_s: float = LATENCY_SLO_S, materialize_epochs: int = 1):
        self.nodes = nodes
        self.tau = tau
        self.latency_slo = latency_slo_s
        self.materialize_epochs = materialize_epochs
        self.node_tiers = {nid: n.tier for nid, n in nodes.items()}
        self.infeasibility_map = {nid: n.max_L_feasible_full for nid, n in nodes.items()}
        self.vf = ValueFunction(tau, self.infeasibility_map, self.node_tiers)

    def run(self, policy, sessions_cfg: List[dict], n_epochs: int,
            mobility_level: str = "moderate", seed: int = 42,
            drift_rate: int = 0) -> SimResultC:

        policy.reset()
        node_ids = list(self.nodes.keys())
        mob = MobilityModel3Edge(mobility_level, n_epochs, seed=seed)

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

        prov_state = ProvisioningState(node_ids, None)

        totals = {k: 0 for k in ("warm_hit", "warm_stale", "cold_miss", "degraded",
                                  "placement_miss", "materialization_miss", "infeasible_miss")}
        slo_hits = 0
        band_hits = {"small": 0, "mid": 0, "large": 0}
        band_total = {"small": 0, "mid": 0, "large": 0}
        latencies: List[float] = []
        qualities: List[float] = []
        cap_violations = 0
        cold_mats = 0
        contain_violations = 0

        # Refresh instrumentation
        total_refresh_cost_s = 0.0
        refresh_events_by_fidelity: Dict[str, int] = {}
        slo_fail_refresh_count = 0
        staleness_sum = 0
        staleness_served_count = 0

        # Multi-fidelity diagnostic (tracked regardless; only non-zero for joint)
        epoch_multi_fid: List[bool] = []
        epoch_slo_count: List[int] = []
        sessions_ever_multi_fid: set = set()

        is_joint = getattr(policy, "is_joint", False)

        for epoch in range(n_epochs):
            # Drift
            if drift_rate > 0:
                for sess in sessions.values():
                    sess._drift_epoch_counter += 1
                    if sess._drift_epoch_counter >= drift_rate:
                        sess._drift_epoch_counter = 0
                        sess._regime_idx = (sess._regime_idx + 1) % len(_REGIME_DRIFT_ORDER)
                        sess.regime = _REGIME_DRIFT_ORDER[sess._regime_idx]

            reachable = mob.reachable_nodes(epoch)
            serve_node = mob.serving_node(epoch)
            true_next = mob.next_serving_node(epoch)

            for sess in sessions.values():
                sess.serving_node = serve_node

            # Serving distribution for non-oracle policies
            dist_shared = _serving_distribution(mob, epoch, n_epochs)
            serving_dist = {sid: dist_shared for sid in sessions}

            # Oracle gets deterministic distribution
            oracle_dist = {sid: {true_next: 1.0} for sid in sessions}

            current_regimes = {sid: sess.regime for sid, sess in sessions.items()}
            L_map = {sid: sess.L for sid, sess in sessions.items()}

            # Step 1: complete pending materializations
            prov_state.advance_materializations(self.nodes, sessions)

            # Step 2: policy decides
            use_dist = oracle_dist if getattr(policy, "is_oracle", False) else serving_dist
            decisions = policy.decide_c(
                sessions=sessions,
                prov_state=prov_state,
                reachable_nodes=reachable,
                epoch=epoch,
                vf=self.vf,
                nodes=self.nodes,
                serving_distribution=use_dist,
                current_regimes=current_regimes,
                tau=self.tau,
                infeasibility_map=self.infeasibility_map,
            )

            # Containment assertion for non-joint, non-oracle policies
            if not is_joint and not getattr(policy, "is_oracle", False):
                joint_set = self._joint_candidate_set(
                    list(sessions.keys()), reachable, L_map, current_regimes, serving_dist)
                other_set = policy.last_candidate_set if hasattr(policy, "last_candidate_set") else set()
                try:
                    assert_joint_contains(joint_set, other_set, policy.name)
                except AssertionError:
                    contain_violations += 1

            self._execute_decisions(decisions, prov_state, sessions)

            # Multi-fidelity check: for joint, count sessions with ≥2 fidelities ready at serving node
            epoch_mf = False
            if is_joint:
                for sid, sess in sessions.items():
                    nid = sess.serving_node
                    ready_count = sum(
                        1 for f in FIDELITIES
                        if (obj := prov_state.get(sid, nid, f)) and obj.ready
                    )
                    if ready_count >= 2:
                        epoch_mf = True
                        sessions_ever_multi_fid.add(sid)
            epoch_multi_fid.append(epoch_mf)

            # Step 3: classify
            epoch_slo_n = 0
            for sid, sess in sessions.items():
                node_id = sess.serving_node
                tier = self.nodes[node_id].tier
                outcome, lat_s, q_val, staleness, served_fid = self._classify(
                    prov_state, sid, node_id, sess, tier)

                totals[outcome] += 1
                latencies.append(lat_s)
                qualities.append(q_val)
                band = _l_band(sess.L)
                band_total[band] += 1

                slo_hit = lat_s <= self.latency_slo and outcome in ("warm_hit", "warm_stale")
                if slo_hit:
                    slo_hits += 1
                    band_hits[band] += 1
                    epoch_slo_n += 1

                # Refresh tracking
                if outcome == "warm_stale" and served_fid is not None:
                    total_refresh_cost_s += lat_s
                    refresh_events_by_fidelity[served_fid] = \
                        refresh_events_by_fidelity.get(served_fid, 0) + 1
                    if lat_s > self.latency_slo:
                        slo_fail_refresh_count += 1

                # Staleness tracking (all outcomes with a served object)
                if served_fid is not None and outcome not in ("cold_miss", "placement_miss",
                                                               "materialization_miss", "infeasible_miss"):
                    staleness_sum += staleness
                    staleness_served_count += 1

                # Reactive cold materialize
                if outcome == "cold_miss":
                    cold_s = _cold_prefill_s(sess.L, tier)
                    if cold_s != float("inf"):
                        max_l = self.infeasibility_map.get(node_id)
                        if max_l is None or sess.L <= max_l:
                            if prov_state.can_fit(node_id, "full", sess.L, self.nodes):
                                prov_state.make_ready(sid, node_id, "full", sess.L, staleness=0)
                                cold_mats += 1

            epoch_slo_count.append(epoch_slo_n)

            for nid, used in prov_state.node_capacity_used.items():
                if used > self.nodes[nid].capacity_gb + 1e-6:
                    cap_violations += 1

            prov_state.increment_staleness(list(sessions.keys()))
            for sess in sessions.values():
                sess.advance()

        n_req = n_epochs * len(sessions)
        fracs = {k: v / n_req for k, v in totals.items()}
        slo_frac = slo_hits / n_req
        band_slo = {b: (band_hits[b] / band_total[b] if band_total[b] > 0 else 0.0)
                    for b in ("small", "mid", "large")}
        lats = sorted(latencies)
        n = len(lats)
        p95 = lats[min(int(0.95 * n), n - 1)] if n else 0.0
        p99 = lats[min(int(0.99 * n), n - 1)] if n else 0.0

        # Compute multi-fidelity delta (joint only)
        mf_sess_frac = (len(sessions_ever_multi_fid) / len(sessions)) if is_joint and sessions else 0.0
        mf_slo_delta = 0.0
        if is_joint and epoch_multi_fid:
            n_sess = len(sessions)
            epochs_with = [epoch_slo_count[i] / n_sess for i, m in enumerate(epoch_multi_fid) if m]
            epochs_without = [epoch_slo_count[i] / n_sess for i, m in enumerate(epoch_multi_fid) if not m]
            if epochs_with and epochs_without:
                mf_slo_delta = sum(epochs_with) / len(epochs_with) - sum(epochs_without) / len(epochs_without)
            elif epochs_with:
                mf_slo_delta = sum(epochs_with) / len(epochs_with)

        return SimResultC(
            policy_name=policy.name,
            n_epochs=n_epochs, n_sessions=len(sessions),
            tau=self.tau, drift_rate=drift_rate,
            slo_fraction=slo_frac, slo_by_band=band_slo,
            warm_hit=fracs["warm_hit"], warm_stale=fracs["warm_stale"],
            cold_miss=fracs["cold_miss"], degraded=fracs["degraded"],
            placement_miss=fracs["placement_miss"],
            materialization_miss=fracs["materialization_miss"],
            infeasible_miss=fracs["infeasible_miss"],
            p95_latency_s=p95, p99_latency_s=p99,
            mean_latency_s=sum(latencies) / n if n else 0.0,
            mean_quality=sum(qualities) / n if n else 0.0,
            capacity_violations=cap_violations,
            cold_materializations=cold_mats,
            containment_violations=contain_violations,
            total_refresh_cost_s=total_refresh_cost_s,
            refresh_events_by_fidelity=refresh_events_by_fidelity,
            slo_fail_on_refresh_fraction=slo_fail_refresh_count / n_req if n_req else 0.0,
            mean_staleness_at_serve=(staleness_sum / staleness_served_count
                                     if staleness_served_count else 0.0),
            multi_fidelity_sessions_fraction=mf_sess_frac,
            multi_fidelity_slo_delta=mf_slo_delta,
        )

    def _joint_candidate_set(self, session_ids, reachable_nodes, L_map, regime_map,
                              serving_dist):
        """Compute joint's full feasible candidate set for containment checking."""
        result = set()
        for sid in session_ids:
            L = L_map[sid]
            for nid in reachable_nodes:
                for f in FIDELITIES:
                    if f == "blind":
                        continue
                    if f == "full":
                        max_l = self.infeasibility_map.get(nid)
                        if max_l is not None and L > max_l:
                            continue
                    result.add((sid, nid, f))
        return result

    def _execute_decisions(self, decisions, prov_state, sessions):
        for dec in decisions:
            sid = dec.session_id
            sess = sessions.get(sid)
            if sess is None:
                continue
            if dec.action == "materialize":
                if dec.fidelity == "full":
                    max_l = self.infeasibility_map.get(dec.node_id)
                    if max_l is not None and sess.L > max_l:
                        continue
                if prov_state.can_fit(dec.node_id, dec.fidelity, sess.L, self.nodes):
                    prov_state.start_materialization(
                        sid, dec.node_id, dec.fidelity,
                        eta_epochs=self.materialize_epochs)
            elif dec.action == "evict":
                prov_state.evict(sid, dec.node_id, dec.fidelity, sess.L)
            elif dec.action in ("refresh", "store", "noop"):
                if dec.action == "refresh":
                    obj = prov_state.get(sid, dec.node_id, dec.fidelity)
                    if obj and obj.ready:
                        prov_state.reset_staleness(sid, dec.node_id, dec.fidelity)

    def _classify(self, prov_state, sid, node_id, sess, tier):
        """
        Returns (outcome, lat_s, q_val, staleness, served_fidelity).
        staleness and served_fidelity are 0 / None for miss outcomes.
        """
        from .quality import quality as q_fn
        regime = sess.regime
        cold_s = _cold_prefill_s(sess.L, tier)
        q_threshold = self.tau * Q_TABLE[regime]["full"]
        max_l = self.infeasibility_map.get(node_id)
        node_feasible = (max_l is None or sess.L <= max_l)

        best = prov_state.best_ready_object(sid, node_id, 0.0, regime)

        if best is None:
            if not node_feasible:
                return "infeasible_miss", float("inf"), 0.0, 0, None
            if prov_state.any_sufficient_elsewhere(
                    sid, node_id, q_threshold, regime, list(self.nodes.keys())):
                return "placement_miss", cold_s, 0.0, 0, None
            if prov_state.being_materialized_at(sid, node_id, 0.0, regime):
                return "materialization_miss", cold_s, 0.0, 0, None
            return "cold_miss", cold_s, 0.0, 0, None

        q_val = q_fn(best.fidelity, regime)
        if q_val < q_threshold:
            return "degraded", cold_s, q_val, best.staleness, best.fidelity

        if best.staleness == 0:
            return "warm_hit", 0.0, q_val, 0, best.fidelity
        if best.fidelity in ("sum80", "sum200"):
            refresh_s = cold_s  # must re-read full context
        elif best.fidelity in ("full", "win"):
            tok = sess.L if best.fidelity == "full" else 2048
            refresh_s = max(0.066, 0.330 * tok / 65536)
        else:
            refresh_s = 0.0
        return "warm_stale", refresh_s * best.staleness, q_val, best.staleness, best.fidelity


def run_all_policies(policies_list, sessions_cfg, n_epochs, mobility_level,
                     seed, drift_rate, nodes, tau, latency_slo=LATENCY_SLO_S):
    """Convenience: run every policy and return {name: SimResultC}."""
    engine = SimulationEngineC(nodes, tau=tau, latency_slo_s=latency_slo)
    results = {}
    for policy in policies_list:
        results[policy.name] = engine.run(
            policy, sessions_cfg, n_epochs,
            mobility_level=mobility_level, seed=seed, drift_rate=drift_rate)
    return results
