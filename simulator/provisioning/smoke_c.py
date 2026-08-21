"""
E24c Stage 1 smoke test.
3 cells; all 9 policies; checks outcomes sum to 1.0, capacity never exceeded,
containment passes, degraded=0. Oracle dominance reported (not fatal).
Prints ValueFunction.compute() source at end.
"""
import sys, inspect
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from simulator.provisioning.engine_c import SimulationEngineC
from simulator.provisioning.topology_b import make_nodes_b
from simulator.provisioning.solver_c import ValueFunction
from simulator.provisioning.policies.c import (
    JointC, FidelityFirst, PlacementFirst, CacheValueC,
    OracleC, ReactiveC, ReplicationC, LibraC, HandoverC,
)

POLICIES = [JointC(), FidelityFirst(), PlacementFirst(), CacheValueC(),
            OracleC(), ReactiveC(), ReplicationC(), LibraC(), HandoverC()]

SMOKE_CELLS = [
    {
        "label": "Cell 1 (L=8192, static, tau=0.90, drift=0)",
        "sessions": [
            {"session_id": i, "regime": r, "L": 8192, "turn_rate": 100}
            for i, r in enumerate(
                ["compressible","compressible","compressible",
                 "mixed_sensitive","dense"])
        ],
        "mobility": "static",
        "tau": 0.90,
        "drift_rate": 0,
        "cap_frac": 0.50,
        "n_epochs": 20,
    },
    {
        "label": "Cell 2 (L=32768, moderate, tau=0.90, drift=0)",
        "sessions": [
            {"session_id": i, "regime": r, "L": 32768, "turn_rate": 100}
            for i, r in enumerate(
                ["compressible","compressible","compressible",
                 "mixed_sensitive","dense"])
        ],
        "mobility": "moderate",
        "tau": 0.90,
        "drift_rate": 0,
        "cap_frac": 0.50,
        "n_epochs": 20,
    },
    {
        "label": "Cell 3 (L=49152, high, tau=0.95, drift=20)",
        "sessions": [
            {"session_id": i, "regime": r, "L": 49152, "turn_rate": 100}
            for i, r in enumerate(
                ["dense","dense","dense","compressible","compressible"])
        ],
        "mobility": "high",
        "tau": 0.95,
        "drift_rate": 20,
        "cap_frac": 0.50,
        "n_epochs": 40,
    },
]

_OUTCOMES = ("warm_hit","warm_stale","cold_miss","degraded","placement_miss",
             "materialization_miss","infeasible_miss")

def capacity_for_cell(cell, n_sessions=5, tau=0.90):
    """50% of cheapest-sufficient-mix normalization."""
    from simulator.provisioning.quality_b import cheapest_sufficient_tau
    from simulator.provisioning.solver_c import _s_ready_gb
    from simulator.provisioning.quality import Q_TABLE
    L_mid = cell["sessions"][0]["L"]
    total = 0.0
    for cfg in cell["sessions"]:
        f = cheapest_sufficient_tau(cfg["regime"], tau)
        total += _s_ready_gb(f, L_mid)
    n_nodes = 4  # 3 edge + 1 cloud
    ref_per_node = total  # one copy per node at cheapest sufficient
    return cell["cap_frac"] * ref_per_node  # per-node cap

def run_cell(cell):
    tau = cell["tau"]
    cap_gb = max(0.5, capacity_for_cell(cell, tau=tau))
    nodes = make_nodes_b(edge_cap_gb=cap_gb, cloud_cap_gb=cap_gb * 4)
    engine = SimulationEngineC(nodes, tau=tau)

    print(f"\n{'='*60}")
    print(f"=== SMOKE TEST {cell['label']} ===")
    print(f"    per-node edge cap={cap_gb:.3f} GB  cloud cap={cap_gb*4:.3f} GB")
    print(f"{'='*60}")

    results = {}
    for policy in POLICIES:
        policy.reset()
        r = engine.run(
            policy,
            sessions_cfg=cell["sessions"],
            n_epochs=cell["n_epochs"],
            mobility_level=cell["mobility"],
            seed=42,
            drift_rate=cell["drift_rate"],
        )
        results[policy.name] = r

    # Check 1: outcome fractions sum to ~1.0
    all_pass = True
    for name, r in results.items():
        total = sum(getattr(r, k) for k in _OUTCOMES)
        if abs(total - 1.0) > 1e-4:
            print(f"  ERROR: {name} outcome fractions sum = {total:.6f} != 1.0")
            all_pass = False

    print(f"  [outcomes sum to 1.0]: {'PASS' if all_pass else 'FAIL'}")
    print(f"  [capacity violations]: {sum(r.capacity_violations for r in results.values())}")
    print(f"  [containment violations]: {sum(r.containment_violations for r in results.values())}")

    # Check containment
    contain_ok = all(r.containment_violations == 0 for r in results.values())
    print(f"  [containment assertion]: {'PASS' if contain_ok else 'FAIL'}")

    # Check degraded=0 (only at drift=0; drift causes stale fidelity → degraded is expected)
    if cell["drift_rate"] == 0:
        degraded_ok = all(r.degraded == 0.0 for r in results.values())
        if not degraded_ok:
            bad = [(n, r.degraded) for n, r in results.items() if r.degraded > 0]
            print(f"  [degraded=0 at drift=0]: FAIL — {bad}")
        else:
            print(f"  [degraded=0 at drift=0]: PASS")
    else:
        bad = [(n, f"{r.degraded:.3f}") for n, r in results.items() if r.degraded > 0]
        print(f"  [degraded at drift={cell['drift_rate']}]: {bad if bad else 'none'} (expected with drift)")

    # Print table
    fmt = f"  {'policy':<18} {'slo_frac':>8} {'degraded':>8} {'cold_miss':>9} {'plac_miss':>9} {'cap_viol':>8}"
    print(fmt)
    print("  " + "-"*65)
    for policy in POLICIES:
        r = results[policy.name]
        print(f"  {policy.name:<18} {r.slo_fraction:>8.3f} {r.degraded:>8.3f} "
              f"{r.cold_miss:>9.3f} {r.placement_miss:>9.3f} {r.capacity_violations:>8}")

    # Oracle dominance
    oracle_slo = results["oracle"].slo_fraction
    max_other = max(r.slo_fraction for n, r in results.items() if n != "oracle")
    if oracle_slo >= max_other - 0.01:
        print(f"  oracle dominance: PASS  (oracle={oracle_slo:.3f}, max_other={max_other:.3f})")
    else:
        print(f"  oracle dominance: VIOLATION  oracle={oracle_slo:.3f} < max_other={max_other:.3f}")

    # Note joint == cache_value
    j_slo = results["joint"].slo_fraction
    cv_slo = results["cache_value"].slo_fraction
    print(f"  joint == cache_value: {'YES' if abs(j_slo - cv_slo) < 1e-6 else f'NO (diff={j_slo-cv_slo:.4f})'}")

    # Assert hard failures
    if not all_pass:
        raise AssertionError("Outcome fractions do not sum to 1.0 — see above")
    if r.capacity_violations > 0:
        raise AssertionError("Capacity violation detected")

    return results


if __name__ == "__main__":
    for cell in SMOKE_CELLS:
        run_cell(cell)

    print("\n" + "="*60)
    print("=== VALUE FUNCTION CODE ===")
    print("="*60)
    src = inspect.getsource(ValueFunction.compute)
    print(src)

    print("\nStage 1 smoke test complete. Awaiting Stage 2 authorization.")
