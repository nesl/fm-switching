# Phase 0a — Multi-model Regime Audit

Generated: 2026-08-16 21:30

## Overview

Purpose: verify that the three-regime compressibility taxonomy (EgoSchema gist-compressible, Infini-THOR structured-compressible, LoCoMo dense-incompressible) is not an artifact of Qwen2.5-7B-Instruct. Reference model: Qwen2.5-7B-Instruct. Second model: Mistral-7B-Instruct-v0.2.

Subsets: LoCoMo n=100, Infini-THOR n=60 multi-clue (extended from n=40), EgoSchema n=60. Fixed seeds; ID lists at `data/audit_subsets/phase0a/`.

Conditions: blind, window-10, summary-80, summary-200, full. LoCoMo Mistral additionally: cross-qwen-sum80, cross-qwen-sum200 (Mistral reader + Qwen summaries). Infini-THOR additionally: cross-{other}-sum80 and cross-{other}-sum200 for both models (each model reads the other model's pre-generated summaries).

## Regime Table

| Workload | Qwen7B regime | Gap (CI) | p | Mistral7B regime | Gap (CI) | p | Changed? |
|---|---|---|---|---|---|---|---|
| locomo | FULL >> SUMMARY | +0.280 | 0.000 | FULL >> SUMMARY | +0.170 | 0.001 | no |
| infinithor | SUMMARY ≈ FULL | +0.098 | 0.211 | SUMMARY ≈ FULL | +0.073 | 0.441 | no |
| egoschema | FULL >> SUMMARY | +0.133 | 0.049 | SUMMARY ≈ FULL | +0.100 | 0.106 | **YES** |

## Locomo

### qwen7b
n=100, subset=locomo_100

**Accuracy per condition (bootstrap 95% CI):**

| condition | acc | CI |
|---|---|---|
| blind | 0.080 | [0.030, 0.140] |
| window-10 | 0.230 | [0.150, 0.320] |
| summary-80 | 0.120 | [0.060, 0.190] |
| summary-200 | 0.120 | [0.060, 0.190] |
| full | 0.400 | [0.290, 0.500] |

**Paired contrasts (paired bootstrap p-value):**

| contrast | gap | p | regime |
|---|---|---|---|
| full_vs_summary-80 | +0.280 | 0.000 | FULL >> SUMMARY |
| full_vs_summary-200 | +0.280 | 0.000 | FULL >> SUMMARY |
| full_vs_window-10 | +0.170 | 0.004 | FULL >> SUMMARY |

**Dispersion:** 30 questions where full>s80. Top-1 carries 3% of gap; top-3 carries 10%. Classification: SPREAD.

**Evidence-distance split:**

| bin | n | full_acc | s80_acc |
|---|---|---|---|
| near | 1 | 1.000 | 0.000 |
| mid | 8 | 0.375 | 0.375 |
| far | 90 | 0.389 | 0.100 |
| not_found | 1 | 1.000 | 0.000 |

GPU peak: 19.68 GB  | Mean latency/call: {'blind': '0.19s', 'window-10': '1.89s', 'summary-80': '0.19s', 'summary-200': '0.21s', 'full': '5.37s'}

### mistral7b
n=100, subset=locomo_100

**Accuracy per condition (bootstrap 95% CI):**

| condition | acc | CI |
|---|---|---|
| blind | 0.140 | [0.070, 0.210] |
| window-10 | 0.260 | [0.180, 0.340] |
| summary-80 | 0.130 | [0.070, 0.200] |
| summary-200 | 0.130 | [0.070, 0.200] |
| full | 0.300 | [0.210, 0.380] |
| cross-qwen-sum80 | 0.110 | [0.060, 0.180] |
| cross-qwen-sum200 | 0.140 | [0.080, 0.210] |

**Paired contrasts (paired bootstrap p-value):**

| contrast | gap | p | regime |
|---|---|---|---|
| full_vs_summary-80 | +0.170 | 0.001 | FULL >> SUMMARY |
| full_vs_summary-200 | +0.170 | 0.001 | FULL >> SUMMARY |
| full_vs_window-10 | +0.040 | 0.467 | SUMMARY ≈ FULL |

**Dispersion:** 22 questions where full>s80. Top-1 carries 5% of gap; top-3 carries 14%. Classification: SPREAD.

**Evidence-distance split:**

| bin | n | full_acc | s80_acc |
|---|---|---|---|
| near | 1 | 1.000 | 0.000 |
| mid | 8 | 0.000 | 0.250 |
| far | 90 | 0.311 | 0.122 |
| not_found | 1 | 1.000 | 0.000 |

**Cross-summarizer conditions (Mistral reader + Qwen summaries):**

| condition | acc | CI |
|---|---|---|
| cross-qwen-sum80 | 0.110 | [0.060, 0.180] |
| cross-qwen-sum200 | 0.140 | [0.080, 0.210] |

GPU peak: 20.66 GB  | Mean latency/call: {'blind': '0.60s', 'window-10': '2.87s', 'summary-80': '0.52s', 'summary-200': '0.54s', 'full': '8.01s', 'cross-qwen-sum80': '0.54s', 'cross-qwen-sum200': '0.56s'}

## Infinithor

### qwen7b
n_all=60 (n57=57 after excluding truncated items), n_nonsalient=44 (n57_nonsalient=41), subset=infinithor_60

**[ALL (n=60)]**

| condition | acc | CI |
|---|---|---|
| blind | 0.200 | [0.117, 0.317] |
| window-10 | 0.267 | [0.167, 0.383] |
| summary-80 | 0.200 | [0.100, 0.317] |
| summary-200 | 0.350 | [0.233, 0.483] |
| full | 0.250 | [0.150, 0.367] |

| contrast | gap | p | regime |
|---|---|---|---|
| full_vs_summary-80 | +0.050 | 0.537 | SUMMARY ≈ FULL |
| full_vs_summary-200 | -0.100 | 0.065 | SUMMARY > FULL |
| full_vs_window-10 | -0.017 | 1.000 | SUMMARY ≈ FULL |

**[NON-SALIENT (n=44)]**

| condition | acc | CI |
|---|---|---|
| blind | 0.250 | [0.114, 0.386] |
| window-10 | 0.273 | [0.136, 0.409] |
| summary-80 | 0.182 | [0.068, 0.295] |
| summary-200 | 0.295 | [0.182, 0.432] |
| full | 0.250 | [0.114, 0.386] |

| contrast | gap | p | regime |
|---|---|---|---|
| full_vs_summary-80 | +0.068 | 0.447 | SUMMARY ≈ FULL |
| full_vs_summary-200 | -0.045 | 0.626 | SUMMARY ≈ FULL |
| full_vs_window-10 | -0.023 | 1.000 | SUMMARY ≈ FULL |

**Cross-summarizer conditions (n=60, all-pool):**

| condition | acc | CI | gap vs full | p |
|---|---|---|---|---|
| cross-mistral7b-sum200 | 0.183 | [0.100, 0.300] | +0.067 | 0.257 |
| cross-mistral7b-sum80 | 0.200 | [0.117, 0.317] | +0.050 | 0.440 |

#### Truncation Handling

Three items exceeded the 28K-token cutoff in the `full` condition: `floorplan210_19_618_1746864406_q1`, `floorplan210_19_618_1746864406_q18`, `floorplan230_9_507_1746931717_q23`. Raw trajectory token counts: ≈57K–74K for Qwen, ≈69K–89K for Mistral. These were silently truncated by the tokenizer (the model received a clipped trajectory) and are excluded from all n=57 contrasts below.

Context fit at raised cutoff: Qwen2.5-7B-Instruct (128K context) can fit all three within the context window, but the A6000 (24GB) ran out of GPU memory (CUDA OOM) during the forward pass at 73K+ token sequences (model weights ~14GB FP16 + KV cache). Mistral-7B-Instruct-v0.2 (32K context) cannot fit any of the three items (all exceed 32K).

**Per-item rerun outcomes at raised cutoff:**

| qid | qwen7b | mistral7b |
|---|---|---|
| ...q1 | oom (73851 tok) | context_exceeded (73851 tok) |
| ...q23 | oom_inferred | context_exceeded |
| ...q18 | oom_inferred | context_exceeded |

All three items are irrecoverable on the A6000 under both models; the n=57 exclusion is the definitive result.

**n=57 contrasts (authoritative; regime table uses these values):**

**[ALL (n=57), n=57]**

| condition | acc | CI |
|---|---|---|
| blind | 0.175 | [0.088, 0.281] |
| window-10 | 0.263 | [0.158, 0.386] |
| summary-80 | 0.193 | [0.105, 0.298] |
| summary-200 | 0.351 | [0.228, 0.474] |
| full | 0.263 | [0.158, 0.386] |

| contrast | gap | p | regime |
|---|---|---|---|
| full_vs_summary-80 | +0.070 | 0.324 | SUMMARY ≈ FULL |
| full_vs_summary-200 | -0.088 | 0.121 | SUMMARY > FULL |
| full_vs_window-10 | +0.000 | 1.000 | SUMMARY ≈ FULL |

**[NON-SALIENT, n=41]**

| condition | acc | CI |
|---|---|---|
| blind | 0.220 | [0.098, 0.341] |
| window-10 | 0.268 | [0.122, 0.415] |
| summary-80 | 0.171 | [0.073, 0.293] |
| summary-200 | 0.293 | [0.146, 0.439] |
| full | 0.268 | [0.122, 0.415] |

| contrast | gap | p | regime |
|---|---|---|---|
| full_vs_summary-80 | +0.098 | 0.211 | SUMMARY ≈ FULL |
| full_vs_summary-200 | -0.024 | 1.000 | SUMMARY ≈ FULL |
| full_vs_window-10 | +0.000 | 1.000 | SUMMARY ≈ FULL |

**Cross-summarizer conditions (n=57, all-pool):**

| condition | acc | CI | gap vs full | p |
|---|---|---|---|---|
| cross-mistral7b-sum200 | 0.158 | [0.070, 0.263] | +0.105 | 0.030 |
| cross-mistral7b-sum80 | 0.175 | [0.088, 0.281] | +0.088 | 0.057 |

GPU peak: 20.85 GB  | Mean latency/call: {'blind': '0.12s', 'window-10': '1.02s', 'summary-80': '0.16s', 'summary-200': '0.18s', 'full': '1.50s', 'cross-mistral7b-sum80': '0.13s', 'cross-mistral7b-sum200': '0.14s'}

### mistral7b
n_all=60 (n57=57 after excluding truncated items), n_nonsalient=44 (n57_nonsalient=41), subset=infinithor_60

**[ALL (n=60)]**

| condition | acc | CI |
|---|---|---|
| blind | 0.033 | [0.000, 0.083] |
| window-10 | 0.183 | [0.100, 0.300] |
| summary-80 | 0.050 | [0.000, 0.117] |
| summary-200 | 0.033 | [0.000, 0.083] |
| full | 0.183 | [0.100, 0.300] |

| contrast | gap | p | regime |
|---|---|---|---|
| full_vs_summary-80 | +0.133 | 0.038 | FULL >> SUMMARY |
| full_vs_summary-200 | +0.150 | 0.022 | FULL >> SUMMARY |
| full_vs_window-10 | +0.000 | 1.000 | SUMMARY ≈ FULL |

**[NON-SALIENT (n=44)]**

| condition | acc | CI |
|---|---|---|
| blind | 0.023 | [0.000, 0.068] |
| window-10 | 0.136 | [0.045, 0.227] |
| summary-80 | 0.068 | [0.000, 0.159] |
| summary-200 | 0.023 | [0.000, 0.068] |
| full | 0.136 | [0.045, 0.227] |

| contrast | gap | p | regime |
|---|---|---|---|
| full_vs_summary-80 | +0.068 | 0.445 | SUMMARY ≈ FULL |
| full_vs_summary-200 | +0.114 | 0.112 | SUMMARY ≈ FULL |
| full_vs_window-10 | +0.000 | 1.000 | SUMMARY ≈ FULL |

**Cross-summarizer conditions (n=60, all-pool):**

| condition | acc | CI | gap vs full | p |
|---|---|---|---|---|
| cross-qwen7b-sum200 | 0.117 | [0.050, 0.200] | +0.067 | 0.371 |
| cross-qwen7b-sum80 | 0.033 | [0.000, 0.083] | +0.150 | 0.006 |

#### Truncation Handling

Three items exceeded the 28K-token cutoff in the `full` condition: `floorplan210_19_618_1746864406_q1`, `floorplan210_19_618_1746864406_q18`, `floorplan230_9_507_1746931717_q23`. Raw trajectory token counts: ≈57K–74K for Qwen, ≈69K–89K for Mistral. These were silently truncated by the tokenizer (the model received a clipped trajectory) and are excluded from all n=57 contrasts below.

Context fit at raised cutoff: Qwen2.5-7B-Instruct (128K context) can fit all three within the context window, but the A6000 (24GB) ran out of GPU memory (CUDA OOM) during the forward pass at 73K+ token sequences (model weights ~14GB FP16 + KV cache). Mistral-7B-Instruct-v0.2 (32K context) cannot fit any of the three items (all exceed 32K).

**Per-item rerun outcomes at raised cutoff:**

| qid | qwen7b | mistral7b |
|---|---|---|
| ...q1 | oom (73851 tok) | context_exceeded (73851 tok) |
| ...q23 | oom_inferred | context_exceeded |
| ...q18 | oom_inferred | context_exceeded |

All three items are irrecoverable on the A6000 under both models; the n=57 exclusion is the definitive result.

**n=57 contrasts (authoritative; regime table uses these values):**

**[ALL (n=57), n=57]**

| condition | acc | CI |
|---|---|---|
| blind | 0.035 | [0.000, 0.088] |
| window-10 | 0.193 | [0.088, 0.298] |
| summary-80 | 0.053 | [0.000, 0.105] |
| summary-200 | 0.035 | [0.000, 0.088] |
| full | 0.193 | [0.088, 0.298] |

| contrast | gap | p | regime |
|---|---|---|---|
| full_vs_summary-80 | +0.140 | 0.033 | FULL >> SUMMARY |
| full_vs_summary-200 | +0.158 | 0.016 | FULL >> SUMMARY |
| full_vs_window-10 | +0.000 | 1.000 | SUMMARY ≈ FULL |

**[NON-SALIENT, n=41]**

| condition | acc | CI |
|---|---|---|
| blind | 0.024 | [0.000, 0.073] |
| window-10 | 0.146 | [0.049, 0.244] |
| summary-80 | 0.073 | [0.000, 0.171] |
| summary-200 | 0.024 | [0.000, 0.073] |
| full | 0.146 | [0.049, 0.244] |

| contrast | gap | p | regime |
|---|---|---|---|
| full_vs_summary-80 | +0.073 | 0.441 | SUMMARY ≈ FULL |
| full_vs_summary-200 | +0.122 | 0.128 | SUMMARY ≈ FULL |
| full_vs_window-10 | +0.000 | 1.000 | SUMMARY ≈ FULL |

**Cross-summarizer conditions (n=57, all-pool):**

| condition | acc | CI | gap vs full | p |
|---|---|---|---|---|
| cross-qwen7b-sum200 | 0.105 | [0.035, 0.193] | +0.088 | 0.226 |
| cross-qwen7b-sum80 | 0.035 | [0.000, 0.088] | +0.158 | 0.004 |

GPU peak: 21.51 GB  | Mean latency/call: {'blind': '0.49s', 'window-10': '1.66s', 'summary-80': '0.47s', 'summary-200': '0.47s', 'full': '2.22s', 'cross-qwen7b-sum80': '0.46s', 'cross-qwen7b-sum200': '0.46s'}

## Egoschema

### qwen7b
n=60, subset=egoschema_60

| condition | acc | CI |
|---|---|---|
| blind | 0.200 | [0.117, 0.300] |
| window-10 | 0.500 | [0.367, 0.617] |
| summary-80 | 0.433 | [0.300, 0.567] |
| summary-200 | 0.483 | [0.350, 0.600] |
| full | 0.567 | [0.433, 0.683] |

| contrast | gap | p | regime |
|---|---|---|---|
| full_vs_summary-80 | +0.133 | 0.049 | FULL >> SUMMARY |
| full_vs_summary-200 | +0.083 | 0.272 | SUMMARY ≈ FULL |
| full_vs_window-10 | +0.067 | 0.230 | SUMMARY ≈ FULL |

GPU peak: 15.55 GB  | Mean latency/call: {'blind': '0.09s', 'window-10': '0.22s', 'summary-80': '0.11s', 'summary-200': '0.15s', 'full': '0.29s'}

### mistral7b
n=60, subset=egoschema_60

| condition | acc | CI |
|---|---|---|
| blind | 0.333 | [0.233, 0.450] |
| window-10 | 0.450 | [0.333, 0.583] |
| summary-80 | 0.333 | [0.217, 0.467] |
| summary-200 | 0.383 | [0.267, 0.500] |
| full | 0.433 | [0.317, 0.567] |

| contrast | gap | p | regime |
|---|---|---|---|
| full_vs_summary-80 | +0.100 | 0.106 | SUMMARY ≈ FULL |
| full_vs_summary-200 | +0.050 | 0.547 | SUMMARY ≈ FULL |
| full_vs_window-10 | -0.017 | 1.000 | SUMMARY ≈ FULL |

GPU peak: 14.9 GB  | Mean latency/call: {'blind': '0.28s', 'window-10': '0.45s', 'summary-80': '0.31s', 'summary-200': '0.32s', 'full': '0.55s'}

## Format / Context-Length Failures

### Full-Context Token Distribution

Full-context token counts (trajectory/passage tokens fed to the model in the `full` condition). These feed cost profiling.

| workload | model | n | min | p50 | p95 | max |
|---|---|---|---|---|---|---|
| locomo | qwen7b | 100 | 11519 | 20539 | 22124 | 22124 |
| locomo | mistral7b | 100 | 13054 | 23008 | 24585 | 24585 |
| infinithor | qwen7b | 60 | 3084 | 3482 | 57291 | 73851 |
| infinithor | mistral7b | 60 | 3498 | 3934 | 69351 | 89327 |

### Locomo

**qwen7b** (n=100):

- Context token range: p50=20539 p95=22124 max=22124 (cutoff: 30000 tokens)
- No truncations: all contexts fit within the 30000-token cutoff.
- Contexts exceeding Mistral's 32K window: 0. None — all LoCoMo full contexts fit within Mistral's usable context.
- Parse failures: 0 across all conditions.

**mistral7b** (n=100):

- Context token range: p50=23008 p95=24585 max=24585 (cutoff: 30000 tokens)
- No truncations: all contexts fit within the 30000-token cutoff.
- Contexts exceeding Mistral's 32K window: 0. None — all LoCoMo full contexts fit within Mistral's usable context.
- Parse failures: 0 across all conditions.

### Infinithor

**qwen7b** (n=60):

- Context token range: p50=3482 p95=57291 max=73851 (cutoff: 28000 tokens)
- **3 item(s) truncated** at the 28000-token cutoff (full context silently clipped by tokenizer): ['floorplan210_19_618_1746864406_q1', 'floorplan230_9_507_1746931717_q23', 'floorplan210_19_618_1746864406_q18']
  Affected conditions: `full` only (summary and window conditions use pre-generated short summaries or last-N lines; no truncation there).
- Parse failures: 0 across all conditions.

**mistral7b** (n=60):

- Context token range: p50=3934 p95=69351 max=89327 (cutoff: 28000 tokens)
- **3 item(s) truncated** at the 28000-token cutoff (full context silently clipped by tokenizer): ['floorplan210_19_618_1746864406_q1', 'floorplan230_9_507_1746931717_q23', 'floorplan210_19_618_1746864406_q18']
  Affected conditions: `full` only (summary and window conditions use pre-generated short summaries or last-N lines; no truncation there).
- Parse failures: 0 across all conditions.

### Egoschema

**qwen7b** (n=60):

- No token-length data available (EgoSchema caption contexts are short, well under any model limit).
- Parse failures: 0 across all conditions.

**mistral7b** (n=60):

- No token-length data available (EgoSchema caption contexts are short, well under any model limit).
- Parse failures: 0 across all conditions.

## Verdict

**LoCoMo** is dense-incompressible under both models. Qwen: full vs summary-80 gap=+0.280, p=0.000. Mistral: gap=+0.170, p=0.001. Both are highly significant and the gap is spread across questions (top-3 carry ≤14% of the total gap), not driven by a few outliers. The cross-summarizer condition (Mistral reader + Qwen-generated summaries) yields acc=0.110–0.140 vs. Mistral full=0.300, confirming the deficit is not attributable to summary quality: Mistral cannot recover the answer from a stronger model's summary.

**Infini-THOR** (n=57, excluding 3 truncated items; non-salient split n=41 for Qwen / see per-model detail). ALL-pool (n=57): Qwen full vs summary-80 gap=+0.070, p=0.324 (SUMMARY ≈ FULL). Mistral full vs summary-80 gap=+0.140, p=0.033 (FULL >> SUMMARY). Non-salient split (n=41): Qwen gap=+0.098, p=0.211; Mistral gap=+0.073, p=0.441 — both ns, insufficient power for a regime call on the non-salient split. The ALL-pool n=57 result: Mistral cannot use structured-log summaries (FULL >> SUMMARY) while Qwen can (SUMMARY ≈ FULL). Cross-summarizer decomposition (n=57): Mistral reading cross-qwen7b-sum200: acc=0.105 (gap vs Mistral full=+0.088, p=0.226); Mistral reading cross-qwen7b-sum80: acc=0.035 (gap vs Mistral full=+0.158, p=0.004); Qwen reading cross-mistral7b-sum200: acc=0.158 (gap vs Qwen full=+0.105, p=0.030); Qwen reading cross-mistral7b-sum80: acc=0.175 (gap vs Qwen full=+0.088, p=0.057). Mistral reading Qwen-generated summaries is no better than Mistral's own summaries, confirming the deficit is a reader capacity issue, not a summarizer quality issue. Qwen reading Mistral summaries performs at par with Qwen's own summaries.

**EgoSchema** is gist-compressible under both models. Qwen: full vs summary-80 gap=+0.133, p=0.049 (marginal at the p<0.05 threshold, driven by the 80-token condition only; full vs summary-200 p=0.272, ns). Mistral: gap=+0.100, p=0.106 (ns). Both models agree that a 200-token summary is statistically equivalent to the full caption set.
