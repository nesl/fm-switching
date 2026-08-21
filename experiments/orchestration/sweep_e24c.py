"""
E24c Stage 2 sweep: 48 cells × 10 policies × 3 seeds = 1,440 runs.

Grid: capacity {25,50,75}% × mobility {moderate,high}
      × regime_mix {mixed,mostly_dense} × tau {0.90,0.95} × drift {0,20}

Sessions per cell: 15, L_init=8192, turn_rate=880, n_epochs=100.
Topology: 3 edge (rtx3090ti, 9GB) + cloud (a6000, 34GB).
Capacity normalised: new = cheapest-sufficient-mix fill at 25/50/75%.
Bandwidth: 10 Mbps, RTT 50ms. Latency SLO: 5.0s.

Output: results/orchestration/e24c_coupling/<cap>_<mob>_<regime>_tau<tau>_drift<drift>/cell.json
"""
import sys, json, time
from itertools import product
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from simulator.provisioning.engine_c import SimulationEngineC, run_all_policies
from simulator.provisioning.topology_b import make_nodes_b, NodeB
from simulator.provisioning.quality_b import cheapest_sufficient_tau
from simulator.provisioning.solver_c import _s_ready_gb
from simulator.provisioning.policies.c import ALL_POLICIES_C

SEEDS = [42, 1337, 99]
N_EPOCHS = 100
N_SESSIONS = 15
L_INIT = 8192
TURN_RATE = 880
LATENCY_SLO = 5.0
N_EDGE = 3
EDGE_CAP_TOTAL_GB = 9.0    # RTX 3090 Ti VRAM
CLOUD_CAP_TOTAL_GB = 34.0  # A6000 VRAM

CAPACITIES = [0.25, 0.50, 0.75]
MOBILITIES = ["moderate", "high"]
REGIME_MIXES = {
    "mixed":        ["compressible", "compressible", "compressible",
                     "mixed_sensitive", "mixed_sensitive", "mixed_sensitive",
                     "mixed_sensitive", "mixed_sensitive", "dense",
                     "dense", "dense", "dense",
                     "compressible", "compressible", "compressible"],
    "mostly_dense": ["dense", "dense", "dense", "dense", "dense",
                     "dense", "dense", "dense", "dense",
                     "mixed_sensitive", "mixed_sensitive", "mixed_sensitive",
                     "compressible", "compressible", "compressible"],
}
TAUS = [0.90, 0.95]
DRIFTS = [0, 20]


def _ref_capacity_per_node(regimes: list, tau: float) -> float:
    """
    Reference = cheapest-sufficient-mix total S_ready at L_INIT,
    divided over N_EDGE+1 nodes (one copy per node at cheapest-sufficient).
    This is the full-fill reference for capacity fractions.
    """
    total = 0.0
    for r in regimes:
        f = cheapest_sufficient_tau(r, tau)
        total += _s_ready_gb(f, L_INIT)
    return total  # per-node reference (one copy per session per node)


def _make_nodes(cap_frac: float, regimes: list, tau: float):
    ref = _ref_capacity_per_node(regimes, tau)
    edge_cap = max(0.5, cap_frac * ref)
    cloud_cap = min(CLOUD_CAP_TOTAL_GB, max(2.0, cap_frac * ref * 4))
    return make_nodes_b(edge_cap_gb=edge_cap, cloud_cap_gb=cloud_cap)


def _cell_dir(cap_frac, mob, regime_key, tau, drift):
    cap_pct = int(cap_frac * 100)
    return (ROOT / "results" / "orchestration" / "e24c_coupling"
            / f"cap{cap_pct}_{mob}_{regime_key}_tau{int(tau*100)}_drift{drift}")


def result_to_dict(r):
    return {
        "policy": r.policy_name,
        "slo_fraction": round(r.slo_fraction, 6),
        "slo_by_band": {k: round(v, 6) for k, v in r.slo_by_band.items()},
        "warm_hit": round(r.warm_hit, 6),
        "warm_stale": round(r.warm_stale, 6),
        "cold_miss": round(r.cold_miss, 6),
        "degraded": round(r.degraded, 6),
        "placement_miss": round(r.placement_miss, 6),
        "materialization_miss": round(r.materialization_miss, 6),
        "infeasible_miss": round(r.infeasible_miss, 6),
        "p95_latency_s": round(r.p95_latency_s, 4),
        "p99_latency_s": round(r.p99_latency_s, 4),
        "mean_quality": round(r.mean_quality, 6),
        "total_refresh_cost_s": round(r.total_refresh_cost_s, 4),
        "refresh_events_by_fidelity": r.refresh_events_by_fidelity,
        "slo_fail_on_refresh_fraction": round(r.slo_fail_on_refresh_fraction, 6),
        "mean_staleness_at_serve": round(r.mean_staleness_at_serve, 4),
        "multi_fidelity_sessions_fraction": round(r.multi_fidelity_sessions_fraction, 6),
        "multi_fidelity_slo_delta": round(r.multi_fidelity_slo_delta, 6),
        "capacity_violations": r.capacity_violations,
        "containment_violations": r.containment_violations,
    }


def run_cell(cap_frac, mob, regime_key, tau, drift):
    regimes = REGIME_MIXES[regime_key]
    sessions_cfg = [
        {"session_id": i, "regime": r, "L": L_INIT, "turn_rate": TURN_RATE}
        for i, r in enumerate(regimes)
    ]
    nodes = _make_nodes(cap_frac, regimes, tau)

    # Collect per-seed results
    per_seed = {p.name: [] for p in ALL_POLICIES_C}
    for seed in SEEDS:
        seed_results = run_all_policies(
            ALL_POLICIES_C, sessions_cfg, N_EPOCHS, mob, seed, drift, nodes, tau,
            latency_slo=LATENCY_SLO)
        for name, r in seed_results.items():
            per_seed[name].append(r)

    # Aggregate: mean/min/max over seeds
    policy_rows = {}
    for name, rs in per_seed.items():
        slos = [r.slo_fraction for r in rs]
        base = result_to_dict(rs[0])  # use seed-0 for scalar diagnostics
        base["slo_mean"] = round(sum(slos) / len(slos), 6)
        base["slo_min"]  = round(min(slos), 6)
        base["slo_max"]  = round(max(slos), 6)
        # Aggregate refresh over seeds
        base["total_refresh_cost_s"] = round(
            sum(r.total_refresh_cost_s for r in rs) / len(rs), 4)
        base["mean_staleness_at_serve"] = round(
            sum(r.mean_staleness_at_serve for r in rs) / len(rs), 4)
        # L-band SLO averaged over seeds
        base["slo_by_band"] = {
            b: round(sum(r.slo_by_band.get(b, 0.0) for r in rs) / len(rs), 6)
            for b in ("small", "mid", "large")
        }
        policy_rows[name] = base

    # Joint multi-fidelity diagnostics (averaged over seeds)
    joint_rs = per_seed.get("joint", [])
    if joint_rs:
        policy_rows["joint"]["multi_fidelity_sessions_fraction"] = round(
            sum(r.multi_fidelity_sessions_fraction for r in joint_rs) / len(joint_rs), 6)
        policy_rows["joint"]["multi_fidelity_slo_delta"] = round(
            sum(r.multi_fidelity_slo_delta for r in joint_rs) / len(joint_rs), 6)

    cell_doc = {
        "config": {
            "cap_frac": cap_frac,
            "mobility": mob,
            "regime_mix": regime_key,
            "tau": tau,
            "drift_rate": drift,
            "n_sessions": N_SESSIONS,
            "L_init": L_INIT,
            "turn_rate": TURN_RATE,
            "n_epochs": N_EPOCHS,
            "seeds": SEEDS,
            "latency_slo_s": LATENCY_SLO,
        },
        "policies": policy_rows,
    }

    out_dir = _cell_dir(cap_frac, mob, regime_key, tau, drift)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "cell.json").write_text(json.dumps(cell_doc, indent=2))
    return cell_doc


def main():
    t0 = time.time()
    grid = list(product(CAPACITIES, MOBILITIES, REGIME_MIXES.keys(), TAUS, DRIFTS))
    n_cells = len(grid)
    print(f"E24c sweep: {n_cells} cells × {len(ALL_POLICIES_C)} policies × {len(SEEDS)} seeds "
          f"= {n_cells * len(ALL_POLICIES_C) * len(SEEDS)} runs")

    for idx, (cap_frac, mob, regime_key, tau, drift) in enumerate(grid):
        t_cell = time.time()
        cell_doc = run_cell(cap_frac, mob, regime_key, tau, drift)
        elapsed = time.time() - t_cell
        joint_slo = cell_doc["policies"]["joint"]["slo_mean"]
        best_decomp = max(
            cell_doc["policies"][p]["slo_mean"]
            for p in ("fidelity_first", "fidelity_first_lifecycle",
                       "placement_first", "cache_value", "libra_style", "handover_sched")
            if p in cell_doc["policies"]
        )
        cap_pct = int(cap_frac * 100)
        print(f"  [{idx+1:2d}/{n_cells}] cap={cap_pct}% mob={mob} reg={regime_key} "
              f"tau={tau} drift={drift}  "
              f"joint={joint_slo:.3f} best_decomp={best_decomp:.3f} "
              f"gap={joint_slo-best_decomp:+.3f}  {elapsed:.1f}s")

    print(f"\nSweep complete in {time.time()-t0:.1f}s")
    print(f"Output: results/orchestration/e24c_coupling/")


if __name__ == "__main__":
    main()
