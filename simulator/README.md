# simulator/

Contains the prior SSM+MPC+RL control-plane code and the current cost model.
The SSM+MPC+RL direction is superseded by the representation-aware framing;
code is kept for lineage. See `research/DECISIONS.md` (entry 2026-06-20).

The simulator will be rebuilt for the new framing (E24 in `research/EXPERIMENTS.md`),
at which point `cost_model.py` will be rewired to read from `results/fidelity/` and
`results/cost/` instead of the six pinned root files below.

---

## cost_model.py — MODEL knob and loading convention

`MODEL = "smollm2"` at the top of `simulator/cost_model.py` is the single global knob.
Change it to switch the entire simulation to a different model. Valid: `"smollm2"` | `"qwen7b"`.

`MODEL` drives three quantities at import time:

| data | source | fallback |
|---|---|---|
| QUALITY, EFFECTIVE_TOKENS | `results/frontier_<MODEL>.json` | hardcoded smollm2 measured values |
| KV_MB_PER_TOKEN | `_KV_MB_PER_TOKEN_BY_MODEL[MODEL]` lookup | — (dict always present) |
| Edge inertia curve | `results/inertia_<MODEL>_jetson.json` | linear FP16 prefill rate |
| Server inertia curve | `results/inertia_<MODEL>_a6000.json` | linear CLOUD prefill rate |

Both tiers use the same `MODEL` by default (keeps quality tier-independent).
A commented heterogeneous-tier block in `cost_model.py` documents how to enable
per-tier model overrides and explains the confound that introduces.

Drop any schema-named JSON into `results/` and re-import to activate; no code change needed.

### Pinned root files (do not move)

`cost_model.py` imports these six files by absolute path at load time.
They must remain at `results/` root until the simulator rebuild rewires the paths:

```
results/frontier_qwen7b.json
results/frontier_qwen7b_perquestion.json
results/frontier_smollm2.json
results/frontier_smollm2_perquestion.json
results/inertia_smollm2_a6000.json
results/inertia_smollm2_jetson.json
```
