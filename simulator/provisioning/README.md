# simulator/provisioning — Config Schema

Fidelity-aware state-provisioning simulator for FM-switching coupling falsification (E24).

---

## Config schema

All fields passed to `SimulationEngine.run()` and the smoke test:

### Node config

```python
from simulator.provisioning.topology import Node, DEFAULT_NODES

nodes = {
    "device": Node("device", capacity_gb=4.0,  prefill_slowdown=6.0),
    "edge":   Node("edge",   capacity_gb=9.0,  prefill_slowdown=1.5),
    "cloud":  Node("cloud",  capacity_gb=34.0, prefill_slowdown=1.0),
}
```

| Field | Type | Description |
|---|---|---|
| `node_id` | str | "device" / "edge" / "cloud" |
| `capacity_gb` | float | GPU memory available for KV after model residency |
| `prefill_slowdown` | float | Multiplier vs A6000 reference cold-prefill time |

Pass a subset of nodes to restrict the topology (e.g., `{"edge", "cloud"}` for 2-node config).

### Session config

```python
sessions_cfg = [
    {
        "session_id": 0,
        "regime":     "compressible",   # "compressible" | "mixed_sensitive" | "dense"
        "L":          8192,             # initial context length (tokens)
        "turn_rate":  200,              # tokens added per epoch
    },
    ...
]
```

| Field | Type | Description |
|---|---|---|
| `session_id` | int | Unique identifier |
| `regime` | str | Workload regime; determines Q(f, regime) and cheapest-sufficient fidelity |
| `L` | int | Initial context length in tokens |
| `turn_rate` | int | Tokens appended per epoch (simulates conversation growth) |
| `serving_node` | str (optional) | Override initial serving node; default = best reachable at epoch 0 |

### Engine config

```python
engine = SimulationEngine(
    nodes=nodes,
    q_min=0.30,
    materialize_epochs=1,   # epochs until a queued materialization completes
)
result = engine.run(
    policy=JointPolicy(),
    sessions_cfg=sessions_cfg,
    n_epochs=20,
    mobility_level="moderate",   # "static" | "predictable" | "moderate" | "high"
    seed=42,
)
```

| Parameter | Default | Description |
|---|---|---|
| `q_min` | 0.30 | Minimum Q(f, regime) for a warm hit; below this = degraded |
| `materialize_epochs` | 1 | Latency of async materialization in epochs (1 epoch = 30 s) |
| `mobility_level` | "moderate" | Maps to Markov profile: static→campus, predictable→urban, moderate→indoor, high→harsh |
| `seed` | 42 | RNG seed for Markov trace |

### Regime → fidelity mapping (q_min = 0.30)

| Regime | Cheapest-sufficient | Q(cheapest, regime) |
|---|---|---|
| compressible | sum80 | 0.470 |
| mixed_sensitive | sum80 | 0.550 |
| dense | full | 0.340 |

---

## Outcome classification

Each request is classified into exactly one outcome; fractions sum to 1.0:

| Outcome | Condition |
|---|---|
| `warm_hit` | Ready object at serving node, Q ≥ q_min, staleness = 0 |
| `warm_stale` | Ready object at serving node, Q ≥ q_min, staleness > 0 |
| `cold` | No ready object at serving node → on-demand full cold prefill |
| `degraded` | Ready object exists but Q(f, regime) < q_min |

---

## Policies

| Policy | Description |
|---|---|
| `ReactivePolicy` | No pre-provisioning; all requests served cold on demand |
| `ReplicationPolicy` | Maintains full KV at every reachable node |
| `PlacementOnlyPolicy` | Pre-provisions full at predicted next-serving node |
| `FidelityOnlyPolicy` | Cheapest-sufficient fidelity at current serving node (no mobility awareness) |
| `CacheValuePolicy` | Expected-value greedy: Q × P(serve) − cost_weight × size_gb |
| `JointPolicy` | Cheapest-sufficient at predicted next-serving node |
| `OraclePolicy` | Joint + evict from unreachable nodes (oracle cleanup) |

All 7 policies receive the same oracle-parity information: true next-serving node and true regime.

---

## Smoke test

```bash
python simulator/provisioning/smoke_test.py
```

Config: 2 nodes (edge + cloud), 5 sessions, 20 epochs, compressible, moderate mobility.

PASS criteria:
1. All 7 policies complete without exception.
2. Outcome fractions sum to 1.0 per request (within 1e-9).
3. Capacity accounting never exceeds C_j at any node, any epoch.
