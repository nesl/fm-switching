# FM-switching — Project Status

Last updated: 2026-08-20 (E27 complete)

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
| **Cost profiling** | Restore, update, and state-size as a function of context length per representation per tier | **Complete on all three tiers** — A6000, RTX 3090 Ti, and Jetson AGX Orin (2026-08-19); summary-update full-context rerun done per tier |

## Current stage

1. **Regime taxonomy** (fidelity, Phase 0a) — *complete*.
   EgoSchema = gist-compressible; Infini-THOR = structured-compressible; LoCoMo = dense-incompressible.
   Held under a second model (Mistral-7B); gate passed.

2. **Physical inertia cost** (Phase 1) — *complete on all three tiers* (A6000, RTX 3090 Ti, Jetson AGX Orin).
   Key crossovers: xB (summary pipeline beats full re-prefill) = L≈65K on A6000, never in range on
   3090Ti (update OOMs above 32K). xC (window ≥10× cheaper) = L≈8K on A6000, L≈4K on 3090Ti.
   Jetson Orin: full_restore feasible ≤16K (75 s), infeasible ≥24K by the 120 s time budget (never OOMs,
   65.9 GB unified); ran the 5.10.2/torch2.8/SDPA-no-flash-attn stack (vs 4.46.3/flash-attn on flash), so
   Jetson-vs-flash gaps include a software-stack component. Jetson crossover rows not yet computed.

3. **Simulator** — *E24, E24b, and E24c complete (2026-08-19)*.
   E24 (1,260 runs, single-edge): placement-aware policies +12pp vs reactive; joint ≤3pp over cache_value.
   E24b (9,720 runs, 3-edge, stressed): fidelity_only outperforms joint by 6–14pp across all regime mixes;
   L-scaling and drift-scaling predictions both falsified.
   E24c (1,440 runs, shared solver, 10 policies): COUPLING FALSIFIED (final). Median gap joint − best-decomposed
   = −1.3pp. New fidelity_first_lifecycle policy (lifecycle-cost-aware fidelity selection) beats joint in 38/48
   cells by up to 17.2pp. Root cause: joint's density metric (V/S_ready) over-selects sum200 (tiny, high density)
   over win (lower density, 100× cheaper refresh at large L). Value function incomplete — does not capture lifecycle
   refresh cost. Thesis position: lifecycle-cost-aware fidelity selection at current serving node is sufficient;
   explicit joint placement×fidelity optimization provides no value.
   Prior SSM+MPC+RL code in `simulator/` is kept for lineage.

## Next gate

Narrow the thesis to: "lifecycle-cost-aware fidelity selection at the current serving node is sufficient;
joint placement×fidelity optimization does not add value." Prepare submission with E24+E24b+E24c as the
simulator evidence. Recommend incorporating lifecycle cost into the value function as a future-work note.
E26 (vLLM calibration) and E23 (Jetson cost) are supporting evidence; proceed when ready but not blocking.

## Target venue

SenSys 2027 (second round) or MobiSys 2027. MLSys fallback if simulator results are strong but
framing needs adjustment.

## What is running where

| Host | Role | Current activity |
|---|---|---|
| **flash / A6000** | Fidelity experiments, server-tier cost profiling | Idle (Phase 1 fix-up committed) |
| **flash / RTX 3090 Ti** | Edge-tier cost profiling (GPU 0) | Idle (Phase 1 fix-up committed) |
| **Jetson AGX Orin** | Device-tier cost profiling (separate SSH host) | Idle — E23 done (qwen7b cost profile + full-context update rerun committed 2026-08-19) |

Flash hosts both A6000 (GPU 1) and RTX 3090 Ti (GPU 0) in the same machine.
Jetson is a separate SSH host; pull before running so it writes to `results/cost/profiles/jetson_orin/`.
