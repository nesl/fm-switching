"""
E24 Stage 2 sweep: capacity × mobility × regime_mix.

Capacity normalization:
  L_mid = 4096 + 30*200 = 10096 tokens
  S_ready(full, 10096) = 57344 * 10096 / 1e9 ≈ 0.579 GB per session per node
  n_sessions = 15, n_candidate_nodes = 2 (edge + cloud)
  full_replication_gb = 15 * 0.579 * 2 = 17.36 GB
  per_node_100pct = 17.36 / 2 = 8.68 GB

  Both edge and cloud are set to the same parameterized capacity (α/100) * 8.68 GB.
  Simplification: equal per-node budget; relative cloud/edge preference preserved
  through node ordering in _NODE_PREFERENCE (edge first).

Regime mix compositions (n=15 sessions):
  mostly_compressible: 10 compressible, 3 mixed_sensitive, 2 dense
  mixed:                5 compressible, 5 mixed_sensitive, 5 dense
  mostly_dense:         2 compressible, 3 mixed_sensitive, 10 dense

Bandwidth profile: 10 Mbps, RTT 50 ms (urban WiFi; state in report).

Total cells: 5 capacity × 4 mobility × 3 regime_mix = 60
Total runs:  60 × 7 policies × 3 seeds = 1,260
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path

# Ensure simulator/provisioning is importable
_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE.parent.parent))  # repo root

from simulator.provisioning.engine import SimulationEngine
from simulator.provisioning.costs import COST_MODEL, KV_BYTES_PER_TOK
from simulator.provisioning.topology import Node
from simulator.provisioning.policies.reactive import ReactivePolicy
from simulator.provisioning.policies.replication import ReplicationPolicy
from simulator.provisioning.policies.placement_only import PlacementOnlyPolicy
from simulator.provisioning.policies.fidelity_only import FidelityOnlyPolicy
from simulator.provisioning.policies.cache_value import CacheValuePolicy
from simulator.provisioning.policies.joint import JointPolicy
from simulator.provisioning.policies.oracle import OraclePolicy

# ── Sweep parameters ──────────────────────────────────────────────────────────

CAPACITY_PCTS = [10, 25, 50, 75, 100]
MOBILITY_LEVELS = ["static", "predictable", "moderate", "high"]
REGIME_MIXES = ["mostly_compressible", "mixed", "mostly_dense"]
SEEDS = [0, 1, 2]

N_SESSIONS = 15
N_EPOCHS = 60
L_INIT = 4096
TURN_RATE = 200   # tokens/epoch

# ── Capacity normalization ────────────────────────────────────────────────────

L_MID = L_INIT + (N_EPOCHS // 2) * TURN_RATE   # = 10096
_S_FULL_MID = KV_BYTES_PER_TOK * L_MID / 1e9    # GB per session per node
N_CANDIDATE_NODES = 2
_FULL_REPLICATION_GB = N_SESSIONS * _S_FULL_MID * N_CANDIDATE_NODES
PER_NODE_100PCT_GB = _FULL_REPLICATION_GB / N_CANDIDATE_NODES

# ── Regime mix definitions ────────────────────────────────────────────────────

_REGIME_COMPOSITIONS = {
    "mostly_compressible": ["compressible"] * 10 + ["mixed_sensitive"] * 3 + ["dense"] * 2,
    "mixed":               ["compressible"] * 5  + ["mixed_sensitive"] * 5 + ["dense"] * 5,
    "mostly_dense":        ["compressible"] * 2  + ["mixed_sensitive"] * 3 + ["dense"] * 10,
}

# ── Policy factory ────────────────────────────────────────────────────────────

def make_policies():
    return [
        ReactivePolicy(),
        ReplicationPolicy(),
        PlacementOnlyPolicy(),
        FidelityOnlyPolicy(),
        CacheValuePolicy(),
        JointPolicy(),
        OraclePolicy(),
    ]

# ── Session config builder ────────────────────────────────────────────────────

def make_sessions(regime_mix: str, seed: int) -> list:
    regimes = _REGIME_COMPOSITIONS[regime_mix]
    return [
        {
            "session_id": i,
            "regime": reg,
            "L": L_INIT,
            "turn_rate": TURN_RATE,
        }
        for i, reg in enumerate(regimes)
    ]

# ── Node builder ─────────────────────────────────────────────────────────────

def make_nodes(capacity_pct: int) -> dict:
    cap = (capacity_pct / 100.0) * PER_NODE_100PCT_GB
    return {
        "edge":  Node("edge",  capacity_gb=cap,           prefill_slowdown=1.5),
        "cloud": Node("cloud", capacity_gb=cap,           prefill_slowdown=1.0),
    }

# ── Result dir ────────────────────────────────────────────────────────────────

_RESULT_ROOT = Path(__file__).parent.parent.parent / "results" / "orchestration" / "e24_coupling"

def cell_dir(capacity_pct, mobility, regime_mix) -> Path:
    name = f"{capacity_pct}pct_{mobility}_{regime_mix}"
    d = _RESULT_ROOT / name
    d.mkdir(parents=True, exist_ok=True)
    return d

# ── Per-run metric extraction ─────────────────────────────────────────────────

def extract_metrics(result) -> dict:
    return {
        "slo_fraction":             result.slo_fraction,
        "capability_hit_rate":      result.capability_hit_rate,
        "false_warm_hit_rate":      result.false_warm_hit_rate,
        "placement_miss_rate":      result.placement_miss_rate,
        "materialization_miss_rate":result.materialization_miss_rate,
        "cold_miss_rate":           result.cold_miss_rate,
        "mean_quality":             result.mean_quality,
        "bytes_transferred_total":  result.bytes_transferred_total,
        "cold_materializations":    result.cold_materializations,
        "warm_hit_frac":            result.outcome_fractions.get("warm_hit", 0.0),
        "warm_stale_frac":          result.outcome_fractions.get("warm_stale", 0.0),
        "cold_frac":                result.outcome_fractions.get("cold", 0.0),
        "degraded_frac":            result.outcome_fractions.get("degraded", 0.0),
        "capacity_violations":      result.capacity_violations,
    }

# ── Main sweep ────────────────────────────────────────────────────────────────

def run_sweep():
    total_cells = len(CAPACITY_PCTS) * len(MOBILITY_LEVELS) * len(REGIME_MIXES)
    cell_num = 0

    print(f"E24 Stage 2 sweep")
    print(f"  {N_SESSIONS} sessions, {N_EPOCHS} epochs, {len(SEEDS)} seeds/cell")
    print(f"  Per-node 100% capacity: {PER_NODE_100PCT_GB:.3f} GB")
    print(f"  Total cells: {total_cells} × {len(make_policies())} policies × {len(SEEDS)} seeds "
          f"= {total_cells * len(make_policies()) * len(SEEDS)} runs\n")

    for cap_pct in CAPACITY_PCTS:
        for mobility in MOBILITY_LEVELS:
            for regime_mix in REGIME_MIXES:
                cell_num += 1
                nodes = make_nodes(cap_pct)
                engine = SimulationEngine(nodes=nodes, cost_model=COST_MODEL)
                policies = make_policies()

                policy_results: dict = {}

                for policy in policies:
                    seed_metrics = []
                    for seed in SEEDS:
                        sessions_cfg = make_sessions(regime_mix, seed)
                        try:
                            result = engine.run(
                                policy=policy,
                                sessions_cfg=sessions_cfg,
                                n_epochs=N_EPOCHS,
                                mobility_level=mobility,
                                seed=seed,
                            )
                            seed_metrics.append(extract_metrics(result))
                        except Exception as e:
                            seed_metrics.append({
                                "error": str(e),
                                "traceback": traceback.format_exc(),
                            })

                    # Aggregate across seeds
                    valid = [m for m in seed_metrics if "error" not in m]
                    if valid:
                        agg = {}
                        for key in valid[0]:
                            vals = [m[key] for m in valid]
                            agg[key] = {
                                "seeds": vals,
                                "mean": sum(vals) / len(vals),
                                "min":  min(vals),
                                "max":  max(vals),
                            }
                        policy_results[policy.name] = agg
                    else:
                        policy_results[policy.name] = {"error": seed_metrics}

                cell_data = {
                    "config": {
                        "capacity_pct": cap_pct,
                        "per_node_cap_gb": (cap_pct / 100.0) * PER_NODE_100PCT_GB,
                        "mobility_level": mobility,
                        "regime_mix": regime_mix,
                        "n_sessions": N_SESSIONS,
                        "n_epochs": N_EPOCHS,
                        "L_init": L_INIT,
                        "turn_rate": TURN_RATE,
                        "seeds": SEEDS,
                        "bw_mbps": 10.0,
                        "rtt_ms": 50.0,
                    },
                    "policies": policy_results,
                }

                out_path = cell_dir(cap_pct, mobility, regime_mix) / "cell.json"
                with open(out_path, "w") as f:
                    json.dump(cell_data, f, indent=2)

                # Progress summary
                joint_slo = policy_results.get("joint", {}).get("slo_fraction", {})
                cv_slo    = policy_results.get("cache_value", {}).get("slo_fraction", {})
                j_mean = joint_slo.get("mean", float("nan")) if isinstance(joint_slo, dict) else float("nan")
                c_mean = cv_slo.get("mean", float("nan")) if isinstance(cv_slo, dict) else float("nan")
                print(f"  [{cell_num:2d}/{total_cells}] cap={cap_pct:3d}% mob={mobility:<12s} "
                      f"mix={regime_mix:<22s} "
                      f"joint={j_mean:.3f} cv={c_mean:.3f} Δ={j_mean-c_mean:+.3f}")

    print(f"\nSweep complete. Results in {_RESULT_ROOT}")

    # Print summary table
    print_summary_table()


def print_summary_table():
    """Print mean slo_fraction per policy per regime_mix (averaged over cap% and mobility)."""
    from collections import defaultdict

    policy_names = [p.name for p in make_policies()]
    agg = defaultdict(lambda: defaultdict(list))

    for cap_pct in CAPACITY_PCTS:
        for mobility in MOBILITY_LEVELS:
            for regime_mix in REGIME_MIXES:
                p = cell_dir(cap_pct, mobility, regime_mix) / "cell.json"
                if not p.exists():
                    continue
                with open(p) as f:
                    cell = json.load(f)
                for pname in policy_names:
                    m = cell["policies"].get(pname, {}).get("slo_fraction", {})
                    if isinstance(m, dict) and "mean" in m:
                        agg[regime_mix][pname].append(m["mean"])

    print("\n── Mean SLO fraction by regime_mix (avg over capacity × mobility) ──")
    header = f"{'policy':<18}" + "".join(f"{rm:<26}" for rm in REGIME_MIXES)
    print(header)
    print("-" * len(header))
    for pname in policy_names:
        row = f"{pname:<18}"
        for rm in REGIME_MIXES:
            vals = agg[rm][pname]
            if vals:
                row += f"{sum(vals)/len(vals):.3f} ({min(vals):.3f}-{max(vals):.3f})  "
            else:
                row += f"{'n/a':<26}"
        print(row)


if __name__ == "__main__":
    run_sweep()
