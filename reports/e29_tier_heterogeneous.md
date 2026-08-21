# E29 — Tier-Heterogeneous Fidelity Audit

Generated: 2026-08-21 15:42 · Follow-up analysis added: 2026-08-21

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

## Paired Substitution Tests

Do cheaper fidelity conditions on the larger model match full fidelity on the smaller model? Paired bootstrap (1000 resamples, seed=42). Diff = 7B/condition − 3B/full. Figure: `figures/fidelity/e29_substitution.pdf`.

| workload | contrast | 3B/full | 7B/cond | diff | 95% CI | p | sig | distinguishable? |
|---|---|---|---|---|---|---|---|---|
| LoCoMo | 7B/window-10 vs 3B/full | 0.230 | 0.230 | +0.000 | [−0.080, +0.080] | 1.000 | ns | No |
| LoCoMo | 7B/summary-200 vs 3B/full | 0.230 | 0.120 | −0.110 | [−0.200, −0.030] | 0.010 | * | Yes (7B/sum-200 worse) |
| LoCoMo | 7B/full vs 3B/full [ceiling] | 0.230 | 0.400 | +0.170 | [+0.080, +0.270] | 0.002 | ** | Yes |
| EgoSchema | 7B/window-10 vs 3B/full | 0.450 | 0.500 | +0.050 | [−0.067, +0.167] | 0.459 | ns | No |
| EgoSchema | 7B/summary-200 vs 3B/full | 0.450 | 0.483 | +0.033 | [−0.117, +0.183] | 0.663 | ns | No |
| EgoSchema | 7B/full vs 3B/full [ceiling] | 0.450 | 0.567 | +0.117 | [−0.033, +0.267] | 0.117 | ns | No |

**LoCoMo:** 7B/window-10 is statistically indistinguishable from 3B/full (p=1.000, both acc=0.230). 7B/summary-200 is significantly *worse* than 3B/full (diff=−0.110, p=0.010): on a dense-incompressible workload, deploying the larger model with a compressed summary does not recover device-tier full-context performance. Even the 7B capability ceiling (7B/full) is distinguishably better than 3B/full (diff=+0.170, p=0.002), confirming the absolute tier gap.

**EgoSchema:** All three comparisons are not statistically distinguishable (p=0.459, 0.663, 0.117). 7B/window-10 (acc=0.500) and 7B/summary-200 (acc=0.483) both exceed 3B/full (acc=0.450) in raw accuracy, but the differences are not significant on n=60. The capability ceiling (7B/full vs 3B/full) is also ns on the gist-compressible workload.

## Sufficiency Tables

### Relative sufficiency — Q(f, w) ≥ τ·Q(full, w)

Relative sufficiency criterion (τ ∈ {0.90, 0.95}) for own-summary conditions. Cross-tier conditions excluded (not a deployment option).

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

### Absolute sufficiency — acc ≥ q

Application quality floor q ∈ {0.20, 0.30, 0.40}: pass if the condition's raw accuracy meets the floor regardless of model.

| workload | model | condition | acc | q≥0.20 | q≥0.30 | q≥0.40 |
|---|---|---|---|---|---|---|
| locomo | qwen3b | blind | 0.030 | ✗ | ✗ | ✗ |
| locomo | qwen3b | window-10 | 0.180 | ✗ | ✗ | ✗ |
| locomo | qwen3b | summary-80 | 0.090 | ✗ | ✗ | ✗ |
| locomo | qwen3b | summary-200 | 0.120 | ✗ | ✗ | ✗ |
| locomo | qwen3b | full | 0.230 | ✓ | ✗ | ✗ |
| locomo | qwen7b | blind | 0.080 | ✗ | ✗ | ✗ |
| locomo | qwen7b | window-10 | 0.230 | ✓ | ✗ | ✗ |
| locomo | qwen7b | summary-80 | 0.120 | ✗ | ✗ | ✗ |
| locomo | qwen7b | summary-200 | 0.120 | ✗ | ✗ | ✗ |
| locomo | qwen7b | full | 0.400 | ✓ | ✓ | ✓ |
| egoschema | qwen3b | blind | 0.300 | ✓ | ✓ | ✗ |
| egoschema | qwen3b | window-10 | 0.450 | ✓ | ✓ | ✓ |
| egoschema | qwen3b | summary-80 | 0.400 | ✓ | ✓ | ✓ |
| egoschema | qwen3b | summary-200 | 0.433 | ✓ | ✓ | ✓ |
| egoschema | qwen3b | full | 0.450 | ✓ | ✓ | ✓ |
| egoschema | qwen7b | blind | 0.200 | ✓ | ✗ | ✗ |
| egoschema | qwen7b | window-10 | 0.500 | ✓ | ✓ | ✓ |
| egoschema | qwen7b | summary-80 | 0.433 | ✓ | ✓ | ✓ |
| egoschema | qwen7b | summary-200 | 0.483 | ✓ | ✓ | ✓ |
| egoschema | qwen7b | full | 0.567 | ✓ | ✓ | ✓ |

**Cheapest (fidelity, tier) meeting each floor:**

| workload | q≥0.20 | q≥0.30 | q≥0.40 |
|---|---|---|---|
| LoCoMo | (window-10, 7B) or (full, 3B) | (full, 7B) | (full, 7B) |
| EgoSchema | (blind, 3B) acc=0.30 | (blind, 3B) acc=0.30 | (window-10, 3B) acc=0.45 |

On dense sessions (LoCoMo), even the modest q≥0.20 floor requires either 7B with windowed context or 3B at full fidelity; no compressed representation on either tier meets q≥0.30. On gist-compressible sessions (EgoSchema), the device tier (3B) with window-10 is the cheapest pair meeting all three floors.

### Sufficiency disagreements — interpretation

The relative disagreements on EgoSchema arise from the scaling of the bar, not from a meaningful deployment difference. 7B/window-10 achieves acc=0.500, which is *higher* than 3B/window-10 (0.450); the relative criterion nevertheless marks 7B as failing because 0.500 < 0.567×0.90 = 0.510. Likewise 7B/summary-200 (0.483) exceeds 3B/summary-200 (0.433) but fails its higher bar (0.567×0.90=0.510).

The claim in the earlier draft that "a runtime provisioning system targeting a device tier can use a compressed representation that would be insufficient for the same workload on the edge tier" is incorrect. Both 7B/window-10 and 7B/summary-200 are also used at the edge. They are relatively insufficient *for the 7B model* by the τ criterion, but they deliver higher absolute accuracy than the corresponding 3B conditions. The correct statement is: the relative sufficiency verdict depends on the model's own full accuracy, and a model with higher full accuracy faces a higher bar; EgoSchema/window-10 passes for 3B (ratio=1.00) but fails for 7B (ratio=0.88) because 7B's full accuracy is 12 percentage points higher.

## Question 1: Does the sufficiency verdict change between 3B and 7B?

**locomo:**
  - blind: τ=0.90 agree  τ=0.95 agree
  - window-10: τ=0.90 agree  τ=0.95 agree
  - summary-80: τ=0.90 agree  τ=0.95 agree
  - summary-200: τ=0.90 agree  τ=0.95 agree
**egoschema:**
  - blind: τ=0.90 agree  τ=0.95 agree
  - window-10: τ=0.90 DISAGREE  τ=0.95 DISAGREE (3B passes, 7B fails — 7B's higher bar explains the gap)
  - summary-80: τ=0.90 agree  τ=0.95 agree
  - summary-200: τ=0.90 DISAGREE  τ=0.95 DISAGREE (3B passes, 7B fails — same mechanism)

## Question 2: Does a 7B-generated summary help the 3B reader?

Compare qwen3b reading qwen7b-generated summaries vs qwen3b reading own summaries.

**locomo:**
  - budget=80: 3B-own=0.090, 3B-reading-7B=0.090, diff=+0.000, p=1.000 (ns)
  - budget=200: 3B-own=0.120, 3B-reading-7B=0.110, diff=−0.010, p=1.000 (ns)
**egoschema:**
  - budget=80: 3B-own=0.400, 3B-reading-7B=0.383, diff=−0.017, p=1.000 (ns)
  - budget=200: 3B-own=0.433, 3B-reading-7B=0.417, diff=−0.017, p=1.000 (ns)

Interpretation: if diff ≈ 0 and ns, a stronger summarizer does not help the weaker reader (consistent with phase0a cross-model result on Qwen/Mistral).

## Question 3: Is qwen3b full accuracy high enough for a device tier to self-serve dense sessions?

LoCoMo: qwen3b full=0.230 [0.150, 0.320], qwen3b blind=0.030; qwen7b full=0.400.

The device tier (qwen3b) has non-trivial full accuracy above blind, suggesting partial self-sufficiency at device tier for some dense queries.

## Fidelity Sensitivity

Window-10 vs full contrast per model per workload (paired bootstrap, diff = full − window-10):

| workload | model | window-10 | full | diff (full−win) | p | sig |
|---|---|---|---|---|---|---|
| LoCoMo | qwen3b | 0.180 | 0.230 | +0.050 | 0.127 | ns |
| LoCoMo | qwen7b | 0.230 | 0.400 | +0.170 | 0.002 | ** |
| EgoSchema | qwen3b | 0.450 | 0.450 | +0.000 | 1.000 | ns |
| EgoSchema | qwen7b | 0.500 | 0.567 | +0.067 | 0.075 | ns |

The smaller model (3B) is less sensitive to fidelity in both workloads. On LoCoMo — the demanding dense-incompressible workload — the full-vs-window gap is +0.170 and highly significant for 7B (p=0.002) but only +0.050 and not significant for 3B (p=0.127). On EgoSchema the gap is zero for 3B and marginal for 7B (p=0.075). This pattern is consistent with 3B having lower overall accuracy: a model that cannot reliably retrieve dense facts even with full context shows a smaller marginal benefit from full context over windowed context. The insensitivity of 3B to fidelity is therefore a symptom of lower absolute capability, not robustness.

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
| locomo | qwen3b | qwen7b | 200 | 0.110 | [0.050, 0.170] | −0.010 | 1.000 |
| locomo | qwen7b | qwen3b | 80 | 0.130 | [0.070, 0.210] | +0.010 | 1.000 |
| locomo | qwen7b | qwen3b | 200 | 0.140 | [0.070, 0.210] | +0.020 | 0.739 |
| egoschema | qwen3b | qwen7b | 80 | 0.383 | [0.250, 0.500] | −0.017 | 1.000 |
| egoschema | qwen3b | qwen7b | 200 | 0.417 | [0.283, 0.533] | −0.017 | 1.000 |
| egoschema | qwen7b | qwen3b | 80 | 0.417 | [0.283, 0.550] | −0.017 | 1.000 |
| egoschema | qwen7b | qwen3b | 200 | 0.450 | [0.317, 0.583] | −0.033 | 0.789 |

## Implication for the Tier Model in FORMULATION.md

This experiment extends the single-model assumption (FORMULATION.md §Simplifications) by measuring Q(fidelity, regime, model) for a realistic device/edge size pair (3B device, 7B edge). The key findings are summarized here for integration. FORMULATION.md has not been edited; these findings should inform a future update.

**Q table model-dependence.** The relative sufficiency verdict is model-dependent in the gist-compressible regime. On LoCoMo, 3B and 7B agree across all fidelities (all insufficient). On EgoSchema, 7B delivers higher absolute accuracy at every fidelity than 3B, but because 7B's full accuracy (0.567) is higher, its relative bar is also higher, and window-10 and summary-200 fail the τ criterion for 7B while passing for 3B. This is an artifact of the relative criterion, not a deployment difference: a runtime that uses window-10 at the edge is not making an insufficient choice by the absolute standard — 7B/window-10 at 0.500 exceeds any 3B condition. Planners using absolute quality floors (the operational standard) should consult the absolute sufficiency table.

**Cross-tier summaries add no value.** A stronger summarizer (7B) does not help a weaker reader (3B), and vice versa. All cross-tier summary comparisons are ns (p≫0.05). The deficit in 3B is a reader-capacity limitation. The runtime gains nothing by generating summaries on the larger tier for consumption by the smaller.

**Paired substitution: dense sessions require edge tier.** On LoCoMo, 7B/window-10 achieves the same accuracy as 3B/full (both 0.230, p=1.000). Using window-10 context on the 7B model is operationally equivalent to full context on the 3B model at dense-incompressible sessions — neither is sufficient, but they tie. By contrast 7B/summary-200 is significantly *worse* than 3B/full (p=0.010), so summary fidelity on the larger model does not recover device-tier full-context performance. Meeting q≥0.30 on dense sessions requires 7B full context; no other (fidelity, tier) pair achieves it.

**Fidelity insensitivity in smaller models is an accuracy floor symptom.** 3B shows no significant fidelity sensitivity in either workload (p=0.127 LoCoMo; p=1.000 EgoSchema). 7B is significantly sensitive on LoCoMo (p=0.002) and marginally on EgoSchema (p=0.075). The interpretation is that a model too weak to retrieve dense facts even with full context shows a smaller marginal benefit from fidelity; insensitivity reflects a low accuracy ceiling, not robustness to compression.
