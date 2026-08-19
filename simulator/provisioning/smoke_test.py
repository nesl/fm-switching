"""
Stage 1 smoke test for simulator/provisioning/.

Config: 2 nodes (edge + cloud), 5 sessions, 20 epochs, compressible regime.

PASS criteria:
  1. All 7 policies complete without exception.
  2. Outcome classification sums to 1.0 per request (within 1e-9).
  3. Capacity accounting never exceeds C_j at any node, any epoch.
"""

import sys
from pathlib import Path

# Ensure repo root is on path
_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_ROOT))

from simulator.provisioning.engine import SimulationEngine
from simulator.provisioning.topology import DEFAULT_NODES
from simulator.provisioning.policies.reactive import ReactivePolicy
from simulator.provisioning.policies.replication import ReplicationPolicy
from simulator.provisioning.policies.placement_only import PlacementOnlyPolicy
from simulator.provisioning.policies.fidelity_only import FidelityOnlyPolicy
from simulator.provisioning.policies.cache_value import CacheValuePolicy
from simulator.provisioning.policies.joint import JointPolicy
from simulator.provisioning.policies.oracle import OraclePolicy


# ── Config ────────────────────────────────────────────────────────────────────

NODES = {k: DEFAULT_NODES[k] for k in ("edge", "cloud")}

SESSIONS = [
    {"session_id": i, "regime": "compressible", "L": 8192, "turn_rate": 200}
    for i in range(5)
]

N_EPOCHS = 20
MOBILITY_LEVEL = "moderate"   # indoor: mixed edge connectivity
Q_MIN = 0.30
SEED = 42

POLICIES = [
    ReactivePolicy(),
    ReplicationPolicy(),
    PlacementOnlyPolicy(),
    FidelityOnlyPolicy(),
    CacheValuePolicy(),
    JointPolicy(),
    OraclePolicy(),
]


# ── Runner ────────────────────────────────────────────────────────────────────

def run_smoke_test():
    engine = SimulationEngine(nodes=NODES, q_min=Q_MIN, materialize_epochs=1)
    n_requests = N_EPOCHS * len(SESSIONS)

    all_pass = True
    results = []

    for policy in POLICIES:
        result = engine.run(
            policy=policy,
            sessions_cfg=SESSIONS,
            n_epochs=N_EPOCHS,
            mobility_level=MOBILITY_LEVEL,
            seed=SEED,
        )
        results.append(result)

        frac_sum = sum(result.outcome_fractions.values())
        sum_ok = abs(frac_sum - 1.0) < 1e-9
        cap_ok = result.capacity_violations == 0

        status = "PASS" if (sum_ok and cap_ok) else "FAIL"
        if not (sum_ok and cap_ok):
            all_pass = False

        frac_str = "  ".join(
            f"{k}={v:.3f}" for k, v in result.outcome_fractions.items()
        )
        print(
            f"[{status}] {policy.name:18s}  "
            f"{frac_str}  "
            f"sum={frac_sum:.9f}  "
            f"cap_violations={result.capacity_violations}"
        )

        if not sum_ok:
            print(f"       !! fraction sum {frac_sum:.9f} != 1.0")
        if not cap_ok:
            print(f"       !! {result.capacity_violations} capacity violation(s)")
            for rec in result.epoch_records:
                for node_id, used in rec.capacity_max.items():
                    cap = NODES[node_id].capacity_gb
                    if used > cap + 1e-6:
                        print(f"          epoch={rec.epoch} node={node_id} "
                              f"used={used:.3f}GB cap={cap:.3f}GB")

    print()
    print("── Capacity ceilings ──")
    for node_id, node in NODES.items():
        print(f"  {node_id}: {node.capacity_gb:.1f} GB")

    print()
    if all_pass:
        print("SMOKE TEST: PASS — all 7 policies; fractions sum to 1.0; capacity OK")
        return 0
    else:
        print("SMOKE TEST: FAIL — see above")
        return 1


if __name__ == "__main__":
    sys.exit(run_smoke_test())
