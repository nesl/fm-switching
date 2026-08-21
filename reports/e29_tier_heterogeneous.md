# E29 — Tier-Heterogeneous Fidelity Audit

Generated: 2026-08-21 15:42

## Motivation

The project has so far assumed one model at every tier. That assumption is unrealistic. In a real device/edge/cloud deployment the tiers run different model sizes, and the reason to move a session to a larger tier is that the larger model answers better. This has two consequences that had not been measured: (a) KV cache is model-specific, so materialized state cannot cross tiers with different model sizes and every tier transition forces re-materialization from text; (b) the quality of a given state fidelity depends on which model reads it, so the Q table becomes Q(fidelity, regime, model) rather than Q(fidelity, regime).

This experiment measures (b). It does not touch (a), which is an architectural fact: on any tier transition between model sizes, full-restore cost applies regardless of the current representation. The physical cost model from E21–E23 applies.

## Setup

Models: Qwen2.5-3B-Instruct (qwen3b, device tier) and Qwen2.5-7B-Instruct (qwen7b, edge/cloud tier). Same family, different size; isolates capacity from architecture.

Subsets: phase0a fixed seeds (data/audit_subsets/phase0a/). LoCoMo n=100, EgoSchema n=60. Results are directly comparable to the committed phase0a Q tables.

Conditions per model: blind, window-10, summary-80, summary-200, full (own summaries), plus cross-tier conditions: 3B reading 7B-generated summaries and 7B reading 3B-generated summaries.

Instrument: identical to multimodel_locomo.py / multimodel_egoschema.py (same scorer, judge, prompts, subset IDs). No methodological changes.

## Sanity Check: qwen7b vs Phase0a Reference

- locomo/qwen7b: full=0.400, ref=0.400, delta=0.000 → **PASS**
- egoschema/qwen7b: full=0.567, ref=0.567, delta=0.000 → **PASS**

All sanity checks passed.

## Locomo

### qwen3b (n=100)

| condition | acc | 95% CI | gap vs full | p | sig |
|---|---|---|---|---|---|
| blind | 0.030 | [0.000, 0.070] | +0.200 | 0.000 | *** |
| window-10 | 0.180 | [0.110, 0.260] | +0.050 | 0.224 | ns |
| summary-80 | 0.090 | [0.040, 0.150] | +0.140 | 0.003 | ** |
| summary-200 | 0.120 | [0.060, 0.190] | +0.110 | 0.039 | * |
| full | 0.230 | [0.150, 0.320] | +0.000 | 1.000 | ns |
| cross-qwen7b-sum80 | 0.090 | [0.040, 0.150] | +0.140 | 0.002 | ** |
| cross-qwen7b-sum200 | 0.110 | [0.050, 0.170] | +0.120 | 0.014 | * |

### qwen7b (n=100)

| condition | acc | 95% CI | gap vs full | p | sig |
|---|---|---|---|---|---|
| blind | 0.080 | [0.030, 0.140] | +0.320 | 0.000 | *** |
| window-10 | 0.230 | [0.150, 0.320] | +0.170 | 0.004 | ** |
| summary-80 | 0.120 | [0.060, 0.190] | +0.280 | 0.000 | *** |
| summary-200 | 0.120 | [0.060, 0.190] | +0.280 | 0.000 | *** |
| full | 0.400 | [0.290, 0.500] | +0.000 | 1.000 | ns |
| cross-qwen3b-sum80 | 0.130 | [0.070, 0.210] | +0.270 | 0.000 | *** |
| cross-qwen3b-sum200 | 0.140 | [0.070, 0.210] | +0.260 | 0.000 | *** |

## Egoschema

### qwen3b (n=60)

| condition | acc | 95% CI | gap vs full | p | sig |
|---|---|---|---|---|---|
| blind | 0.300 | [0.200, 0.417] | +0.150 | 0.040 | * |
| window-10 | 0.450 | [0.317, 0.567] | +0.000 | 1.000 | ns |
| summary-80 | 0.400 | [0.267, 0.533] | +0.050 | 0.416 | ns |
| summary-200 | 0.433 | [0.300, 0.550] | +0.017 | 1.000 | ns |
| full | 0.450 | [0.317, 0.583] | +0.000 | 1.000 | ns |
| cross-qwen7b-sum80 | 0.383 | [0.250, 0.500] | +0.067 | 0.421 | ns |
| cross-qwen7b-sum200 | 0.417 | [0.283, 0.533] | +0.033 | 0.677 | ns |

### qwen7b (n=60)

| condition | acc | 95% CI | gap vs full | p | sig |
|---|---|---|---|---|---|
| blind | 0.200 | [0.117, 0.300] | +0.367 | 0.000 | *** |
| window-10 | 0.500 | [0.367, 0.617] | +0.067 | 0.230 | ns |
| summary-80 | 0.433 | [0.300, 0.567] | +0.133 | 0.049 | * |
| summary-200 | 0.483 | [0.350, 0.600] | +0.083 | 0.272 | ns |
| full | 0.567 | [0.433, 0.683] | +0.000 | 1.000 | ns |
| cross-qwen3b-sum80 | 0.417 | [0.283, 0.550] | +0.150 | 0.029 | * |
| cross-qwen3b-sum200 | 0.450 | [0.317, 0.583] | +0.117 | 0.108 | ns |

## Sufficiency Table — Q(f, w) ≥ τ·Q(full, w)

Relative sufficiency criterion (τ ∈ {0.90, 0.95}) for own-summary conditions. Cross-tier conditions excluded from sufficiency table (not a deployment option).

| workload | model | condition | acc | τ=0.90 | τ=0.95 |
|---|---|---|---|---|---|
| locomo | qwen3b | blind | 0.030 | ✗ | ✗ |
| locomo | qwen3b | window-10 | 0.180 | ✗ | ✗ |
| locomo | qwen3b | summary-80 | 0.090 | ✗ | ✗ |
| locomo | qwen3b | summary-200 | 0.120 | ✗ | ✗ |
| locomo | qwen7b | blind | 0.080 | ✗ | ✗ |
| locomo | qwen7b | window-10 | 0.230 | ✗ | ✗ |
| locomo | qwen7b | summary-80 | 0.120 | ✗ | ✗ |
| locomo | qwen7b | summary-200 | 0.120 | ✗ | ✗ |
| egoschema | qwen3b | blind | 0.300 | ✗ | ✗ |
| egoschema | qwen3b | window-10 | 0.450 | ✓ | ✓ |
| egoschema | qwen3b | summary-80 | 0.400 | ✗ | ✗ |
| egoschema | qwen3b | summary-200 | 0.433 | ✓ | ✓ |
| egoschema | qwen7b | blind | 0.200 | ✗ | ✗ |
| egoschema | qwen7b | window-10 | 0.500 | ✗ | ✗ |
| egoschema | qwen7b | summary-80 | 0.433 | ✗ | ✗ |
| egoschema | qwen7b | summary-200 | 0.483 | ✗ | ✗ |

### Sufficiency disagreements between qwen3b and qwen7b

**τ=0.9:**
  - egoschema/window-10 at τ=0.9: qwen3b=0.450 (sufficient), qwen7b=0.500 (insufficient)
  - egoschema/summary-200 at τ=0.9: qwen3b=0.433 (sufficient), qwen7b=0.483 (insufficient)
**τ=0.95:**
  - egoschema/window-10 at τ=0.95: qwen3b=0.450 (sufficient), qwen7b=0.500 (insufficient)
  - egoschema/summary-200 at τ=0.95: qwen3b=0.433 (sufficient), qwen7b=0.483 (insufficient)

## Question 1: Does the sufficiency verdict change between 3B and 7B?

**locomo:**
  - blind: τ=0.90 agree  τ=0.95 agree
  - window-10: τ=0.90 agree  τ=0.95 agree
  - summary-80: τ=0.90 agree  τ=0.95 agree
  - summary-200: τ=0.90 agree  τ=0.95 agree
**egoschema:**
  - blind: τ=0.90 agree  τ=0.95 agree
  - window-10: τ=0.90 DISAGREE  τ=0.95 DISAGREE **← DISAGREE**
  - summary-80: τ=0.90 agree  τ=0.95 agree
  - summary-200: τ=0.90 DISAGREE  τ=0.95 DISAGREE **← DISAGREE**

## Question 2: Does a 7B-generated summary help the 3B reader?

Compare qwen3b reading qwen7b-generated summaries vs qwen3b reading own summaries.

**locomo:**
  - budget=80: 3B-own=0.090, 3B-reading-7B=0.090, diff=+0.000, p=1.000 (ns)
  - budget=200: 3B-own=0.120, 3B-reading-7B=0.110, diff=-0.010, p=1.000 (ns)
**egoschema:**
  - budget=80: 3B-own=0.400, 3B-reading-7B=0.383, diff=-0.017, p=1.000 (ns)
  - budget=200: 3B-own=0.433, 3B-reading-7B=0.417, diff=-0.017, p=1.000 (ns)

Interpretation: if diff ≈ 0 and ns, a stronger summarizer does not help the weaker reader (consistent with phase0a cross-model result on Qwen/Mistral).

## Question 3: Is qwen3b full accuracy high enough for a device tier to self-serve dense sessions?

LoCoMo: qwen3b full=0.230 [0.150, 0.320], qwen3b blind=0.030; qwen7b full=0.400.

The device tier (qwen3b) has non-trivial full accuracy above blind, suggesting partial self-sufficiency at device tier for some dense queries.

## Q(fidelity, regime, model) Table

Drop-in replacement for the existing Q table in the simulator. Regime: dense-incompressible (LoCoMo), gist-compressible (EgoSchema).

| fidelity | regime | model | Q | 95% CI |
|---|---|---|---|---|
| blind | dense-incompressible | qwen3b | 0.030 | [0.000, 0.070] |
| window-10 | dense-incompressible | qwen3b | 0.180 | [0.110, 0.260] |
| summary-80 | dense-incompressible | qwen3b | 0.090 | [0.040, 0.150] |
| summary-200 | dense-incompressible | qwen3b | 0.120 | [0.060, 0.190] |
| full | dense-incompressible | qwen3b | 0.230 | [0.150, 0.320] |
| blind | dense-incompressible | qwen7b | 0.080 | [0.030, 0.140] |
| window-10 | dense-incompressible | qwen7b | 0.230 | [0.150, 0.320] |
| summary-80 | dense-incompressible | qwen7b | 0.120 | [0.060, 0.190] |
| summary-200 | dense-incompressible | qwen7b | 0.120 | [0.060, 0.190] |
| full | dense-incompressible | qwen7b | 0.400 | [0.290, 0.500] |
| blind | gist-compressible | qwen3b | 0.300 | [0.200, 0.417] |
| window-10 | gist-compressible | qwen3b | 0.450 | [0.317, 0.567] |
| summary-80 | gist-compressible | qwen3b | 0.400 | [0.267, 0.533] |
| summary-200 | gist-compressible | qwen3b | 0.433 | [0.300, 0.550] |
| full | gist-compressible | qwen3b | 0.450 | [0.317, 0.583] |
| blind | gist-compressible | qwen7b | 0.200 | [0.117, 0.300] |
| window-10 | gist-compressible | qwen7b | 0.500 | [0.367, 0.617] |
| summary-80 | gist-compressible | qwen7b | 0.433 | [0.300, 0.567] |
| summary-200 | gist-compressible | qwen7b | 0.483 | [0.350, 0.600] |
| full | gist-compressible | qwen7b | 0.567 | [0.433, 0.683] |

## Cross-Tier Summary Conditions

Accuracy when a model reads summaries generated by the other model.

| workload | reader | summarizer | budget | acc | 95% CI | vs reader own | p |
|---|---|---|---|---|---|---|---|
| locomo | qwen3b | qwen7b | 80 | 0.090 | [0.040, 0.150] | +0.000 | 1.000 |
| locomo | qwen3b | qwen7b | 200 | 0.110 | [0.050, 0.170] | -0.010 | 1.000 |
| locomo | qwen7b | qwen3b | 80 | 0.130 | [0.070, 0.210] | +0.010 | 1.000 |
| locomo | qwen7b | qwen3b | 200 | 0.140 | [0.070, 0.210] | +0.020 | 0.739 |
| egoschema | qwen3b | qwen7b | 80 | 0.383 | [0.250, 0.500] | -0.017 | 1.000 |
| egoschema | qwen3b | qwen7b | 200 | 0.417 | [0.283, 0.533] | -0.017 | 1.000 |
| egoschema | qwen7b | qwen3b | 80 | 0.417 | [0.283, 0.550] | -0.017 | 1.000 |
| egoschema | qwen7b | qwen3b | 200 | 0.450 | [0.317, 0.583] | -0.033 | 0.789 |

## Implication for the Tier Model in FORMULATION.md

This experiment extends the single-model assumption (FORMULATION.md §Simplifications) by measuring Q(fidelity, regime, model) for a realistic device/edge size pair (3B device, 7B edge). The key findings are summarized here for integration. FORMULATION.md has not been edited; these findings should inform a future update.

Three implications for the tier model. First, the Q table is model-dependent in the gist-compressible regime but not in the dense-incompressible regime. On LoCoMo, both 3B and 7B agree that no compressed fidelity is sufficient at any τ — the ranking of fidelities is the same (full ≫ summary ≈ window, all well below threshold). On EgoSchema, the models disagree: window-10 and summary-200 pass the τ=0.90/0.95 threshold for 3B (full=0.450) but not for 7B (full=0.567), because the larger model's higher absolute full accuracy raises the relative bar. This means a runtime provisioning system targeting a device tier can use a compressed representation that would be insufficient for the same workload on the edge tier; the regime estimate alone does not determine the fidelity choice — the serving model matters.

Second, a stronger summarizer (7B) does not help a weaker reader (3B). Cross-tier summaries produce the same or slightly worse accuracy than own-summaries at p≫0.05 across all conditions and workloads. This is consistent with the phase0a Qwen/Mistral result and appears robust: the deficit in 3B is a reader-capacity limitation, not a summary-quality limitation. Implications: the runtime gains nothing by generating summaries on the edge tier for device-tier consumption, and the reverse (device-tier summaries read by edge) similarly adds no accuracy over edge-generated summaries.

Third, the device tier (3B) is partially self-sufficient on dense sessions: qwen3b full=0.230 (vs blind=0.030), meaning 3B can retrieve 23% of dense facts with full context vs 7B's 40%. The device tier is not useless on dense workloads, but it answers dense queries at roughly 57% of the edge tier's capability. For sessions operating at a dense-incompressible SLO, device-only service with 3B full context will miss ~3 in 4 answerable questions that edge (7B full) would correctly answer. Whether this gap is acceptable depends on the SLO tolerance, but the cost model (which assumes a uniform model) should incorporate a model-capability penalty when sessions are served at the device tier.
