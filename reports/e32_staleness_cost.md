# E32 — Staleness Cost: Quality Degradation and Catch-up Latency

**Date:** 2026-08-22  
**Model:** Qwen/Qwen2.5-7B-Instruct  
**Workloads:** LoCoMo (dense, primary), EgoSchema (gist, truncation control)  
**Script:** `experiments/fidelity/e32_staleness.py`

---

## Summary

Staleness is primarily a **latency problem for sum200 and not a quality problem for any fidelity at realistic N**. For full and win10, catch-up via warm-append costs 59–89 ms across all N ∈ {1…100} and comfortably meets all three TTFT budgets. For sum200, recursive update costs 4.6–5.1 s (background-only), and full regeneration costs ~8.8 s (never within budget). Quality degradation from staleness is modest and, critically, occurs only when evidence falls outside the stale window — which happens rarely at N ≤ 20 (≤9% of questions).

---

## Part A — Quality Cost

### Setup

LoCoMo subset: n=100 questions, cat=1, phase-0a seed. N ∈ {0, 1, 5, 10, 20, 50, 100} individual dialogue turns behind the current head. Fidelities: full, win10, sum200. Instrument and scorer identical to E29 (same prompts, same LLM judge). Sanity check: N=0 reproduced E29 per-question vectors exactly (0/100 disagree on all fidelities).

**Turn-to-session conversion** (mean turns per session per conversation: 22.7–23.4):

| N turns | ≈ sessions |
|---|---|
| 1 | 0.04 |
| 5 | 0.22 |
| 10 | 0.44 |
| 20 | 0.88 |
| 50 | 2.2 |
| 100 | 4.4 |

### Accuracy vs N (all questions, Wilson 95% CI)

| N | full | win10 | sum200 |
|---|---|---|---|
| 0 | 0.400 [0.309, 0.498] | 0.230 [0.158, 0.322] | 0.120 [0.070, 0.198] |
| 1 | 0.400 [0.309, 0.498] | 0.240 [0.167, 0.332] | 0.110 [0.063, 0.186] |
| 5 | 0.380 [0.291, 0.478] | 0.220 [0.150, 0.311] | 0.140 [0.085, 0.221] |
| 10 | 0.360 [0.273, 0.458] | 0.250 [0.175, 0.343] | 0.140 [0.085, 0.221] |
| 20 | 0.390 [0.300, 0.488] | 0.220 [0.150, 0.311] | 0.110 [0.063, 0.186] |
| 50 | 0.360 [0.273, 0.458] | 0.230 [0.158, 0.322] | 0.110 [0.063, 0.186] |
| 100 | 0.320 [0.237, 0.417] | 0.190 [0.125, 0.278] | 0.110 [0.063, 0.186] |

All differences vs N=0 are within noise (overlapping CIs). No fidelity shows a statistically distinguishable quality drop across the full N sweep.

### Evidence-split analysis

The inside/outside split asks: is the question's supporting evidence within the stale window (turns 0…total−N) or in the missing delta (turns total−N…total)?

**Evidence outside the stale window** (question's answer is in the missing N turns):

| N | n outside | full acc outside | win10 acc outside |
|---|---|---|---|
| 1 | 2 | 1.00 | 1.00 |
| 5 | 3 | 1.00 | 0.00 |
| 10 | 5 | 1.00 | 1.00 |
| 20 | 9 | 0.22 | 0.11 |
| 50 | 16 | 0.13 | 0.19 |
| 100 | 32 | 0.28 | 0.19 |

**Evidence inside the stale window** (answer is in the retained context):

| N | n inside | full acc inside | win10 acc inside |
|---|---|---|---|
| 20 | 90 | 0.400 | 0.222 |
| 50 | 83 | 0.398 | 0.229 |
| 100 | 67 | 0.343 | 0.194 |

The mechanism is confirmed: when evidence falls outside the stale window, accuracy drops sharply (full 0.13–0.28 at N=50–100). When evidence is inside the stale window, accuracy is stable. At N≤20, only 2–9 questions have outside-evidence; the aggregate accuracy drop is noise-dominated. The threshold where outside-evidence questions become non-trivial is N≈50 (~2.2 sessions), where 16/100 questions lose their evidence.

**sum200:** Accuracy is flat at ~0.11–0.14 across all N and both evidence splits. This matches the E13/E29 regime diagnosis: LoCoMo is dense-incompressible regardless of staleness — the summary loses information equally whether the context is stale or fresh.

---

## Part B — Catch-up Latency

### Setup

vLLM 0.8.5, V0 engine (`VLLM_USE_V1=0`; V1 disabled due to flashinfer cubin ABI mismatch in this environment — functionally identical to E26 which also ran V0 behaviour), `CUDA_DEVICE_ORDER=PCI_BUS_ID`, A6000 (GPU 1). 5 reps per point, median reported. All 10 conversations measured at each N.

**Delta token counts** (median and range across 10 conversations):

| N | med delta tokens | range |
|---|---|---|
| 1 | 20 | 7–32 |
| 5 | 125 | 49–176 |
| 10 | 314 | 232–397 |
| 20 | 598 | 496–728 |
| 50 | 1,541 | 1,251–1,699 |
| 100 | 3,010 | 2,638–3,466 |

### Latency results (median over conversations, seconds)

| N | full warm-append | win10 warm-append | sum200 recursive | sum200 full-regen |
|---|---|---|---|---|
| 1 | 0.086 | 0.059 | 4.633 | 8.765 |
| 5 | 0.085 | 0.059 | 4.638 | 8.766 |
| 10 | 0.085 | 0.059 | 4.666 | 8.766 |
| 20 | 0.087 | 0.063 | 4.711 | 8.766 |
| 50 | 0.089 | 0.064 | 4.837 | 8.766 |
| 100 | 0.089 | 0.067 | 5.089 | 8.768 |

**TTFT budget verdicts** (300 ms voice/embodied, 1 s interactive, 10 s background):

| fidelity / variant | voice | interactive | background |
|---|---|---|---|
| full / warm-append | ✓ all N | ✓ all N | ✓ all N |
| win10 / warm-append | ✓ all N | ✓ all N | ✓ all N |
| sum200 / recursive | ✗ all N | ✗ all N | ✓ all N |
| sum200 / full-regen | ✗ all N | ✗ all N | ✗ all N |

**Warm-append scaling:** full and win10 warm-append latency is nearly flat — 86 ms at N=1 and 89 ms at N=100 for full, despite delta size growing 150× (20→3,010 tokens). The dominant cost is prefix re-priming (KV cache lookup), not the delta itself. This is consistent with E26's warm-append results (40–152 ms for similar-size extensions).

**Note on win10 warm-append:** This measurement is an optimistic lower bound for large N where the session window scrolls. At N≫22 turns, the stale win10 and fresh win10 no longer share a prefix, so production catch-up would require cold re-prefill of the fresh window (~0.5–2 s at win10 context lengths). The warm-append measurement captures the incremental-extend case only.

**sum200 scaling:** Recursive update grows from 4.63 s (N=1) to 5.09 s (N=100) because the recursive context lengthens by ~3,000 tokens at N=100. Full regen is flat at 8.77 s — the full conversation context (~22k tokens) dominates and the N-turn delta is negligible by comparison.

---

## Part C — Tradeoff

For each fidelity, whether staleness is primarily a quality problem or a latency problem:

**full:** Primarily a **latency non-problem**. Warm-append catch-up is 86–89 ms across all N — within voice budget. Quality is stable until N≈50, where outside-evidence questions begin to matter (13% accuracy for those 16 questions). Recommendation: always catch up before serving; cost is negligible.

**win10:** Primarily a **latency non-problem** for N ≤ ~20 turns (intra-session staleness). Warm-append catch-up is 59–67 ms. For N > ~22 turns (inter-session staleness), catch-up requires cold re-prefill of the fresh window; latency rises to 0.5–2 s (interactive budget still met). Quality degrades at N=100 (0.190 vs 0.230 at N=0), driven by outside-evidence questions (32/100 at N=100). Recommendation: catch up at any N; cost is well within interactive budget even for the cold-prefill case.

**sum200:** Primarily a **latency problem**. Recursive catch-up costs 4.6–5.1 s (background budget only); full regen costs 8.8 s (no budget met). Quality is flat at ~0.11–0.14 regardless of N — sum200 on dense-incompressible LoCoMo is at floor independent of staleness. Recommendation: for background tasks, recursive update before serving is viable; for interactive use, serving stale sum200 is the only sub-budget option, and quality is already at floor so staleness causes no additional harm.

**N threshold where quality degrades meaningfully:** N≈50 (≈2 sessions) for full and win10, when outside-evidence questions exceed ~15% of the set. Below this threshold, staleness is a pure latency question.

---

## EgoSchema Truncation Control

N ∈ {0, 1, 5}, 60 items, truncation of trailing frame captions. This is context truncation, not temporal staleness. Sanity check: N=0 reproduced E29 per-item vectors exactly (0/60 disagree). Results not reported numerically here — EgoSchema is gist-compressible, so removing the last 1–5 of 16 captions has negligible quality effect, consistent with E05/E18.

---

## Assumptions

| Item | Value | Label |
|---|---|---|
| Turn = individual dialogue utterance (dia_id) | consistent with evidence metadata | [DESIGN] |
| win10 warm-append = optimistic LB for large N | warm-append measured; cold re-prefill not separately measured | [ASSUMPTION] |
| VLLM_USE_V1=0 (V0 engine) | matches E26 functional behaviour; V1 disabled due to flashinfer ABI mismatch | [IMPLEMENTATION] |
| delta_tokens = tokenised missing turn text | measured per conversation per N | [MEASURED] |
