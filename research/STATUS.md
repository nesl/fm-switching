# FM-switching — Project Status

Last updated: 2026-08-19

## Framing

Mobile FM agents operating at the edge must maintain session state between turns.
That state can be held in one of four representations — full-replay, window-10,
summary-80, or summary-200 — which differ in reconstruction cost (transfer + re-prefill
latency) and in fidelity (how much task-relevant information survives compression).
**Context Inertia** is the joint cost of holding that state: it has a *physical* component
(transfer and reconstruction time, which grows with context length and degrades with
network conditions) and a *semantic* component (cheaper representations discard
information the future turn needs, in a workload-dependent way).

## Two measurement instruments

| Instrument | What it measures | Status |
|---|---|---|
| **Fidelity audit** | QA accuracy of blind / summary-80 / summary-200 / window-10 / full across EgoSchema, Infini-THOR, LoCoMo | Complete: three-regime taxonomy established under Qwen2.5-7B and Mistral-7B (Phase 0a gate passed) |
| **Cost profiling** | Restore, update, and state-size as a function of context length per representation per tier | A6000 and RTX 3090 Ti done; summary-update fix-up committed; Jetson Orin pending |

## Current stage

1. **Regime taxonomy** (fidelity, Phase 0a) — *complete*.
   EgoSchema = gist-compressible; Infini-THOR = structured-compressible; LoCoMo = dense-incompressible.
   Held under a second model (Mistral-7B); gate passed.

2. **Physical inertia cost** (Phase 1) — *complete on A6000 and RTX 3090 Ti*; Jetson Orin pending.
   Key crossovers: xB (summary pipeline beats full re-prefill) = L≈65K on A6000, never in range on
   3090Ti (update OOMs above 32K). xC (window ≥10× cheaper) = L≈8K on A6000, L≈4K on 3090Ti.

3. **Simulator** — *in scope; not yet started under the new framing*.
   The accept/reject claim (C5) requires a trace-driven simulator showing that joint
   representation + placement + timing beats decomposed policies under a quality SLO.
   Prior SSM+MPC+RL code in `simulator/` is kept for lineage.

## Next gate

Trace-driven simulator: joint policy (representation × placement × timing) vs decomposed baselines,
under quality SLO, across mobility regimes and network conditions.

## Target venue

SenSys 2027 (second round) or MobiSys 2027. MLSys fallback if simulator results are strong but
framing needs adjustment.

## What is running where

| Host | Role | Current activity |
|---|---|---|
| **flash / A6000** | Fidelity experiments, server-tier cost profiling | Idle (Phase 1 fix-up committed) |
| **flash / RTX 3090 Ti** | Edge-tier cost profiling (GPU 0) | Idle (Phase 1 fix-up committed) |
| **Jetson AGX Orin** | Device-tier cost profiling (separate SSH host) | Pending: run `experiments/cost/cost_profile.py --tier jetson_orin --model qwen7b` |

Flash hosts both A6000 (GPU 1) and RTX 3090 Ti (GPU 0) in the same machine.
Jetson is a separate SSH host; pull before running so it writes to `results/cost/profiles/jetson_orin/`.
