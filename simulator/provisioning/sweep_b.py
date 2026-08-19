"""
E24b sweep runner.

Stage 0: headroom diagnostic — compute reactive SLO failure fraction analytically.
         Gate: if >50% of cells have <5 pp headroom, STOP.
Stage 1-2: 5 cap × 4 mob × 3 regime_mix × 3 tau × 2 drift × 9 policies × 3 seeds.

Run: python simulator/provisioning/sweep_b.py
"""

from __future__ import annotations

import json
import math
import multiprocessing
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Tuple

# Make simulator packages importable
_REPO = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(_REPO / "simulator"))

from simulator.provisioning.quality import Q_TABLE, FIDELITIES
from simulator.provisioning.quality_b import (
    verify_blind_never_sufficient, sufficiency_table,
    cheapest_sufficient_tau, sufficient, has_graded_ladder,
)
from simulator.provisioning.topology_b import make_nodes_b, EDGE_MAX_L_FULL
from simulator.provisioning.engine_b import _cold_prefill
from simulator.provisioning.engine_b import SimulationEngineB, LATENCY_SLO_S, _l_band
from simulator.provisioning.costs import COST_MODEL

# ------------------------------------------------------------------
# Sweep parameters
# ------------------------------------------------------------------
CAPACITY_PCTS  = [10, 25, 50, 75, 100]
MOBILITY_LEVELS = ["static", "predictable", "moderate", "high"]
REGIME_MIXES   = ["mostly_compressible", "mixed", "mostly_dense"]
TAUS           = [0.80, 0.90, 0.95]
DRIFT_RATES    = [0, 20]
SEEDS          = [0, 1, 2]

N_SESSIONS   = 15
N_EPOCHS     = 100
L_INIT       = 8192
TURN_RATE    = 880    # tokens/epoch → L_final ≈ 96192

_REGIME_COUNTS = {
    "mostly_compressible": {"compressible": 10, "mixed_sensitive": 3, "dense": 2},
    "mixed":               {"compressible": 5,  "mixed_sensitive": 5, "dense": 5},
    "mostly_dense":        {"compressible": 2,  "mixed_sensitive": 3, "dense": 10},
}

OUT_DIR = _REPO / "results" / "orchestration" / "e24b_coupling"
FIG_DIR = _REPO / "figures" / "orchestration"

# ------------------------------------------------------------------
# Infeasibility map for edge nodes
# ------------------------------------------------------------------
INFEASIBILITY_MAP_EDGE = EDGE_MAX_L_FULL  # 32768

# ------------------------------------------------------------------
# Cold-prefill SLO ratios (for reporting)
# ------------------------------------------------------------------
_L_BAND_REPS = {
    "small": 12288,   # midpoint 8k-16k
    "mid":   32768,   # midpoint 24k-40k
    "large": 80384,   # midpoint 64k-96k
}


def _slo_ratio_table():
    rows = []
    for band, L in _L_BAND_REPS.items():
        for tier in ("edge", "cloud"):
            s, extrap = _cold_prefill(L, tier)
            rows.append({
                "band": band, "L": L, "tier": tier,
                "cold_prefill_s": round(s, 2) if s != float("inf") else "INFEASIBLE",
                "slo_ratio": round(s / LATENCY_SLO_S, 2) if s != float("inf") else "INFEASIBLE",
                "extrapolated": extrap,
            })
    return rows


# ------------------------------------------------------------------
# Capacity normalization
# ------------------------------------------------------------------
def _ref_capacity_old(n_sessions: int, n_candidate_nodes: int) -> float:
    """Old E24 normalization: all sessions at full fidelity at every node."""
    L_mid = L_INIT + (N_EPOCHS // 2) * TURN_RATE  # 52192
    s_full = COST_MODEL.s_ready_gb("full", L_mid)
    total = n_sessions * s_full * n_candidate_nodes
    return total / n_candidate_nodes  # per-node


def _ref_capacity_new(regime_mix: str, tau: float, n_candidate_nodes: int) -> float:
    """New E24b normalization: cheapest-sufficient mix per node."""
    L_mid = L_INIT + (N_EPOCHS // 2) * TURN_RATE
    counts = _REGIME_COUNTS[regime_mix]
    total = 0.0
    for regime, count in counts.items():
        f = cheapest_sufficient_tau(regime, tau)
        total += count * COST_MODEL.s_ready_gb(f, L_mid)
    return total / n_candidate_nodes  # per-node (same load on each candidate)


# ------------------------------------------------------------------
# Sessions config builder
# ------------------------------------------------------------------
def _sessions_cfg(regime_mix: str) -> List[dict]:
    counts = _REGIME_COUNTS[regime_mix]
    cfgs = []
    sid = 0
    for regime, count in counts.items():
        for _ in range(count):
            cfgs.append({
                "session_id": sid,
                "regime": regime,
                "L": L_INIT,
                "turn_rate": TURN_RATE,
            })
            sid += 1
    return cfgs


# ------------------------------------------------------------------
# Policy factory
# ------------------------------------------------------------------
def _make_policies(tau: float):
    from simulator.provisioning.policies.reactive import ReactivePolicy
    from simulator.provisioning.policies.replication import ReplicationPolicy
    from simulator.provisioning.policies.placement_only import PlacementOnlyPolicy
    from simulator.provisioning.policies.cache_value import CacheValuePolicy
    from simulator.provisioning.policies.joint_b import JointBPolicy
    from simulator.provisioning.policies.fidelity_only_b import FidelityOnlyBPolicy
    from simulator.provisioning.policies.oracle_b import OracleBPolicy
    from simulator.provisioning.policies.libra_style import LibraStylePolicy
    from simulator.provisioning.policies.handover_sched import HandoverSchedPolicy

    return [
        ReactivePolicy(),
        ReplicationPolicy(),
        PlacementOnlyPolicy(),
        FidelityOnlyBPolicy(tau=tau),
        CacheValuePolicy(),
        JointBPolicy(tau=tau),
        OracleBPolicy(tau=tau),
        LibraStylePolicy(),
        HandoverSchedPolicy(),
    ]


# ------------------------------------------------------------------
# Stage 0: headroom diagnostic
# ------------------------------------------------------------------
def _compute_headroom(mobility_level: str, seed: int = 0) -> float:
    """
    Fraction of (epoch, session) pairs where reactive fails SLO.
    Reactive: cold-prefill full at serving node each epoch.
    SLO fails if cold_prefill > LATENCY_SLO_S.
    """
    from simulator.provisioning.topology_b import MobilityModel3Edge
    mob = MobilityModel3Edge(mobility_level, N_EPOCHS, seed=seed)

    fail = 0
    total = 0
    for epoch in range(N_EPOCHS):
        serving = mob.serving_node(epoch)
        tier = "edge" if serving.startswith("edge") else "cloud"
        L = L_INIT + epoch * TURN_RATE
        cold_s, _ = _cold_prefill(L, tier)
        for _ in range(N_SESSIONS):
            total += 1
            if cold_s > LATENCY_SLO_S:
                fail += 1

    return fail / total


def stage0_headroom():
    print("=" * 60)
    print("STAGE 0: Headroom Diagnostic")
    print("=" * 60)
    print(f"Reactive SLO failure fraction per mobility level")
    print(f"(sessions L = {L_INIT} + epoch × {TURN_RATE}, n_epochs={N_EPOCHS})")
    print()

    results = {}
    for mob in MOBILITY_LEVELS:
        h = _compute_headroom(mob)
        results[mob] = h
        print(f"  {mob:12s}: headroom = {h:.3f} ({h*100:.1f} pp)")

    print()
    # Headroom is the same across all (cap, tau, drift, regime_mix) cells
    # since reactive is agnostic to those
    total_cells = len(CAPACITY_PCTS) * len(MOBILITY_LEVELS) * len(REGIME_MIXES) * len(TAUS) * len(DRIFT_RATES)
    non_disc = sum(1 for h in results.values() if h < 0.05) * (total_cells // len(MOBILITY_LEVELS))
    frac_non_disc = non_disc / total_cells
    print(f"Non-discriminating cells (headroom < 5 pp): {non_disc}/{total_cells} ({frac_non_disc:.1%})")

    if frac_non_disc > 0.5:
        print()
        print("GATE FAILED: >50% of cells non-discriminating.")
        print("Parameter region is wrong. Report:")
        for mob, h in results.items():
            print(f"  {mob}: {h:.3f}")
        sys.exit(1)

    print("Gate passed — proceeding to Stage 1.\n")
    return results


# ------------------------------------------------------------------
# Run a single cell (one combination of parameters, all policies × seeds)
# ------------------------------------------------------------------
def _run_cell(args) -> Tuple[str, dict]:
    (cap_pct, mob_level, regime_mix, tau, drift_rate) = args

    # Compute capacity (new E24b normalization)
    n_candidate_nodes = 4  # 3 edge + 1 cloud
    ref_per_node = _ref_capacity_new(regime_mix, tau, n_candidate_nodes)
    cap_gb = (cap_pct / 100.0) * ref_per_node

    ref_old_per_node = _ref_capacity_old(N_SESSIONS, n_candidate_nodes)
    cap_old_gb = (cap_pct / 100.0) * ref_old_per_node

    edge_cap = min(cap_gb, 48.0)   # hardware ceiling for bookkeeping
    cloud_cap = min(cap_gb * (34.0 / 9.0), 34.0)  # scale cloud proportionally
    # Actually: set both to cap_gb parametrically (no hardware clamping in sweep)
    nodes = make_nodes_b(edge_cap_gb=cap_gb, cloud_cap_gb=cap_gb)

    sessions_cfg = _sessions_cfg(regime_mix)
    policies = _make_policies(tau)

    cell_key = f"{cap_pct}pct_{mob_level}_{regime_mix}_tau{int(tau*100)}_drift{drift_rate}"

    policy_results = {}
    for policy in policies:
        seed_results = []
        for seed in SEEDS:
            engine = SimulationEngineB(nodes=nodes, q_min_tau=tau, latency_slo_s=LATENCY_SLO_S)
            try:
                result = engine.run(
                    policy, sessions_cfg, N_EPOCHS,
                    mobility_level=mob_level, seed=seed, drift_rate=drift_rate)
                seed_results.append({
                    "seed": seed,
                    "slo_fraction": result.slo_fraction,
                    "warm_hit": result.warm_hit,
                    "warm_stale": result.warm_stale,
                    "cold_miss": result.cold_miss,
                    "degraded": result.degraded,
                    "placement_miss": result.placement_miss,
                    "materialization_miss": result.materialization_miss,
                    "infeasible_miss": result.infeasible_miss,
                    "p50_latency_s": result.p50_latency_s,
                    "p95_latency_s": result.p95_latency_s,
                    "p99_latency_s": result.p99_latency_s,
                    "mean_latency_s": result.mean_latency_s,
                    "mean_quality": result.mean_quality,
                    "slo_by_band": result.slo_by_band,
                    "capacity_violations": result.capacity_violations,
                    "cold_materializations": result.cold_materializations,
                    "extrapolated_points": result.extrapolated_points,
                })
            except Exception as e:
                seed_results.append({"seed": seed, "error": str(e)})

        vals = [r["slo_fraction"] for r in seed_results if "slo_fraction" in r]
        policy_results[policy.name] = {
            "seeds": seed_results,
            "mean_slo": sum(vals) / len(vals) if vals else None,
            "min_slo": min(vals) if vals else None,
            "max_slo": max(vals) if vals else None,
        }

    # Oracle dominance check
    oracle_slo = policy_results.get("oracle", {}).get("mean_slo")
    if oracle_slo is not None:
        for pname, pr in policy_results.items():
            if pname == "oracle":
                continue
            p_slo = pr.get("mean_slo")
            if p_slo is not None and p_slo > oracle_slo + 0.001:
                print(f"WARNING: oracle dominance violated in {cell_key}: "
                      f"{pname} ({p_slo:.4f}) > oracle ({oracle_slo:.4f})")

    cell_data = {
        "config": {
            "capacity_pct": cap_pct,
            "mobility_level": mob_level,
            "regime_mix": regime_mix,
            "tau": tau,
            "drift_rate": drift_rate,
            "n_sessions": N_SESSIONS,
            "n_epochs": N_EPOCHS,
            "L_init": L_INIT,
            "turn_rate": TURN_RATE,
            "edge_cap_gb": round(cap_gb, 4),
            "cloud_cap_gb": round(cap_gb, 4),
            "ref_cap_new_per_node_gb": round(ref_per_node, 4),
            "ref_cap_old_per_node_gb": round(ref_old_per_node, 4),
            "seeds": SEEDS,
        },
        "policies": policy_results,
    }

    return cell_key, cell_data


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------
def main():
    # Verify blind never sufficient
    verify_blind_never_sufficient()
    print("Blind-never-sufficient check: PASS\n")

    # Print sufficiency table
    print("Sufficiency table (tau × regime × cheapest_sufficient):")
    for row in sufficiency_table():
        cs = row["cheapest_sufficient"]
        graded = has_graded_ladder(row["regime"], row["tau"])
        print(f"  tau={row['tau']:.2f}  {row['regime']:18s}  cheapest_sufficient={cs}  graded_ladder={graded}")
    print()

    # Print SLO ratio table
    print("Cold-prefill SLO ratio (L_mid per band, SLO=5.0s):")
    for row in _slo_ratio_table():
        s = row['cold_prefill_s']
        r = row['slo_ratio']
        ext = " [EXTRAPOLATED]" if row['extrapolated'] else ""
        print(f"  {row['band']:5s}  L={row['L']:6d}  {row['tier']:5s}  "
              f"cold={s}s  ratio={r}{ext}")
    print()

    # Stage 0 headroom gate
    headroom = stage0_headroom()

    # Build cell list
    cells = []
    for cap in CAPACITY_PCTS:
        for mob in MOBILITY_LEVELS:
            for regime in REGIME_MIXES:
                for tau in TAUS:
                    for drift in DRIFT_RATES:
                        cells.append((cap, mob, regime, tau, drift))

    print(f"Running {len(cells)} cells × {len(SEEDS)} seeds × 9 policies = "
          f"{len(cells) * len(SEEDS) * 9} runs")
    print(f"n_epochs={N_EPOCHS}, n_sessions={N_SESSIONS}\n")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)

    start = time.time()
    n_workers = min(multiprocessing.cpu_count(), 8)
    print(f"Using {n_workers} parallel workers\n")

    completed = 0
    with multiprocessing.Pool(n_workers) as pool:
        for cell_key, cell_data in pool.imap_unordered(_run_cell, cells):
            cell_dir = OUT_DIR / cell_key
            cell_dir.mkdir(parents=True, exist_ok=True)
            with open(cell_dir / "cell.json", "w") as f:
                json.dump(cell_data, f, indent=2)
            completed += 1
            if completed % 30 == 0 or completed == len(cells):
                elapsed = time.time() - start
                print(f"  {completed}/{len(cells)} cells done ({elapsed:.0f}s)")

    elapsed = time.time() - start
    print(f"\nSweep complete: {completed} cells in {elapsed:.0f}s\n")

    # Print summary table
    print_summary()


def print_summary():
    """Print mean slo_fraction per policy per regime_mix (averaged over all other dims)."""
    from collections import defaultdict

    agg = defaultdict(list)  # (policy, regime_mix) → [slo_fraction]
    for cell_dir in sorted(OUT_DIR.iterdir()):
        cell_file = cell_dir / "cell.json"
        if not cell_file.exists():
            continue
        with open(cell_file) as f:
            data = json.load(f)
        regime_mix = data["config"]["regime_mix"]
        for pname, pr in data["policies"].items():
            if pr.get("mean_slo") is not None:
                agg[(pname, regime_mix)].append(pr["mean_slo"])

    policies_order = ["reactive", "replication", "placement_only", "fidelity_only",
                      "cache_value", "joint", "oracle", "libra_style", "handover_sched"]
    print("Mean SLO fraction by policy × regime_mix (over all cap/mob/tau/drift):")
    header = f"{'policy':20s}" + "".join(f"{r:22s}" for r in REGIME_MIXES)
    print(header)
    for p in policies_order:
        row = f"{p:20s}"
        for r in REGIME_MIXES:
            vals = agg.get((p, r), [])
            if vals:
                row += f"{sum(vals)/len(vals):.4f} ({len(vals):3d})"
            else:
                row += "N/A                   "
        print(row)


if __name__ == "__main__":
    multiprocessing.set_start_method("spawn", force=True)
    main()
