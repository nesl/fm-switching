"""
E24c shared value function and allocator.

All policies use this exact value function and allocator.
Policies differ only in which (session, node, fidelity) candidates
they pass to the allocator — not in how they score or pack them.
"""
from __future__ import annotations

import bisect
from typing import Dict, List, Optional, Set, Tuple

from .quality_b import sufficient

# Measured cold-prefill tables (same as engine_b)
_RTX_L = [1024, 2048, 4096, 8192, 16384, 24576, 32768]
_RTX_S = [0.220, 0.468, 0.982, 2.028, 4.868, 8.525, 13.694]
_A6K_L = [1024, 2048, 4096, 8192, 16384, 24576, 32768, 49152, 65536]
_A6K_S = [0.165, 0.325, 0.667, 1.369, 3.090, 5.245, 7.805, 14.820, 21.720]

KV_BYTES_PER_TOK = 57344
_SUM80_GB  = 57344 * 80  / 1e9
_SUM200_GB = 57344 * 200 / 1e9
_WIN_GB    = 57344 * 2048 / 1e9


def _cold_prefill_s(L: int, tier: str) -> float:
    """Cold full-KV prefill cost in seconds. Returns inf if infeasible (edge OOM)."""
    if tier == "edge":
        if L >= 49152:
            return float("inf")
        table_L, table_S = _RTX_L, _RTX_S
    else:
        table_L, table_S = _A6K_L, _A6K_S

    if L <= table_L[0]:
        return table_S[0]
    if L >= table_L[-1]:
        if L == table_L[-1]:
            return table_S[-1]
        slope = (table_S[-1] - table_S[-2]) / (table_L[-1] - table_L[-2])
        return table_S[-1] + slope * (L - table_L[-1])
    idx = bisect.bisect_right(table_L, L)
    L0, L1 = table_L[idx - 1], table_L[idx]
    t0, t1 = table_S[idx - 1], table_S[idx]
    return t0 + (t1 - t0) * (L - L0) / (L1 - L0)


def _s_ready_gb(fidelity: str, L: int) -> float:
    if fidelity == "full":
        return KV_BYTES_PER_TOK * L / 1e9
    if fidelity == "win":
        return _WIN_GB
    if fidelity == "sum200":
        return _SUM200_GB
    if fidelity == "sum80":
        return _SUM80_GB
    return 0.0  # blind


class ValueFunction:
    """
    V(i, j, f) = P_serve × 1[sufficient(f, regime, tau)] × latency_saved_s

    latency_saved_s = cold_prefill(full, L, node_tier)
    — cost avoided vs a cold-miss (reactive always cold-materializes full).

    If full is infeasible at node j (edge OOM), latency_saved uses cloud tier
    as the reference (a cold miss would fall back to cloud).
    """

    def __init__(self, tau: float, infeasibility_map: Dict[str, Optional[int]],
                 node_tiers: Dict[str, str]):
        """
        tau: relative sufficiency threshold
        infeasibility_map: {node_id: max_L_for_full_KV}; None = no limit
        node_tiers: {node_id: "edge" | "cloud"}
        """
        self.tau = tau
        self.infeasibility_map = infeasibility_map
        self.node_tiers = node_tiers

    def compute(self, session_id: int, node_id: str, fidelity: str,
                L: int, regime: str, P_serve: float) -> float:
        """Return scalar value; 0.0 if infeasible or insufficient."""
        # Infeasibility: full KV not placeable at this node for this L
        if fidelity == "full":
            max_l = self.infeasibility_map.get(node_id)
            if max_l is not None and L > max_l:
                return 0.0

        # Quality sufficiency check
        if not sufficient(fidelity, regime, self.tau):
            return 0.0

        # Latency saved = cold_prefill(full, L, tier)
        tier = self.node_tiers.get(node_id, "cloud")
        cold_s = _cold_prefill_s(L, tier)
        if cold_s == float("inf"):
            # Edge is infeasible for full — but we already handled this above for fidelity==full.
            # For non-full fidelities at edge when L is large: the reference cost is cloud
            cold_s = _cold_prefill_s(L, "cloud")

        return P_serve * cold_s

    def density(self, value: float, fidelity: str, L: int) -> float:
        """value / S_ready_gb; 0 when S_ready = 0 (blind)."""
        s = _s_ready_gb(fidelity, L)
        if s <= 0:
            return 0.0
        return value / s


def greedy_knapsack(
    candidates: List[dict],
    nodes: dict,
    prov_state,
    sessions: dict,
) -> List[dict]:
    """
    Greedy by value density (value / s_ready_gb), deterministic tie-break.
    Per-node knapsack; one pass; no backtracking.
    Returns placed items (subset of candidates, each not already ready).
    candidates dicts have keys: session_id, node_id, fidelity, value, density, s_ready_gb
    """
    # Sort: descending density; tie-break by (session_id, node_id, fidelity)
    sorted_cands = sorted(
        candidates,
        key=lambda c: (-c["density"], c["session_id"], c["node_id"], c["fidelity"])
    )

    remaining: Dict[str, float] = {
        nid: nodes[nid].capacity_gb - prov_state.node_capacity_used.get(nid, 0.0)
        for nid in nodes
    }

    placed = []
    for item in sorted_cands:
        if item["value"] <= 0:
            continue
        nid = item["node_id"]
        # Skip if already ready — engine won't issue a redundant materialize
        existing = prov_state.get(item["session_id"], nid, item["fidelity"])
        if existing and existing.ready:
            continue
        needed = item["s_ready_gb"]
        if needed <= remaining.get(nid, 0.0) + 1e-9:
            placed.append(item)
            remaining[nid] = max(0.0, remaining.get(nid, 0.0) - needed)

    return placed


def build_candidates(session_ids, reachable_nodes, L_map, regime_map,
                     serving_dist, vf, fidelity_filter=None, node_filter=None,
                     infeasibility_map=None):
    """
    Build the full candidate list for a policy.

    fidelity_filter:   callable(session_id, regime) -> fidelity or None (= any)
    node_filter:       callable(session_id, reachable_nodes) -> list of allowed nodes or None (= any)
    infeasibility_map: {node_id: max_L_for_full_KV} — excludes infeasible (full, edge, L>max) items
    """
    from .quality import FIDELITIES
    infeasibility_map = infeasibility_map or {}
    candidates = []
    for sid in session_ids:
        L = L_map[sid]
        regime = regime_map[sid]
        dist = serving_dist.get(sid, {})

        allowed_nodes = reachable_nodes if node_filter is None else node_filter(sid, reachable_nodes)
        for nid in allowed_nodes:
            P_serve = dist.get(nid, 0.0)
            if fidelity_filter is not None:
                f_fixed = fidelity_filter(sid, regime)
                fids = [f_fixed] if f_fixed else []
            else:
                fids = [f for f in FIDELITIES if f != "blind"]

            for fidelity in fids:
                # Exclude infeasible combinations before generating candidates
                if fidelity == "full":
                    max_l = infeasibility_map.get(nid)
                    if max_l is not None and L > max_l:
                        continue
                val = vf.compute(sid, nid, fidelity, L, regime, P_serve)
                s = _s_ready_gb(fidelity, L)
                dens = vf.density(val, fidelity, L)
                candidates.append({
                    "session_id": sid,
                    "node_id": nid,
                    "fidelity": fidelity,
                    "value": val,
                    "density": dens,
                    "s_ready_gb": s,
                })
    return candidates


def assert_joint_contains(joint_candidates: Set[Tuple], other_candidates: Set[Tuple],
                           policy_name: str):
    """
    Assert every feasible candidate in other_candidates is also in joint_candidates.
    joint_candidates and other_candidates: sets of (session_id, node_id, fidelity).
    """
    # Filter to non-zero value candidates only (zero-value items are vacuously contained)
    diff = other_candidates - joint_candidates
    if diff:
        raise AssertionError(
            f"Containment FAIL for {policy_name}: "
            f"{len(diff)} candidates not in joint space: {list(diff)[:5]}"
        )
