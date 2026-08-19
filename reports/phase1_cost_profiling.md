# Phase 1 — Cost Profiling Report

Generated: 2026-08-19 09:54

## Overview

Measures restore and update latency for four state representations (full-replay, window-10, summary-80, summary-200) as a function of context length L, with 5 reps per point (first excluded as warm-up). Real contexts are sampled from LoCoMo conversation logs and Infini-THOR trajectory files. Transfer cost is derived from state size at {1, 10, 100} Mbps and {50, 200} ms RTT.

Window-10 = last 10 corpus turns (~200 tokens/turn). Summary restore uses a fixed ~80/200-token stub text (constant latency). Summary update = generation of 80/200 tokens from the L-token context. Incremental warm = forward pass of 200 new tokens given warm KV cache. Incremental cold = full cold prefill of L+200 tokens.

## Tier: a6000

### Model: qwen7b

GPU: NVIDIA RTX A6000 (51.0 GB) | LLM: Qwen/Qwen2.5-7B-Instruct | KV bytes/token: 57,344

#### Restore Latency (ms, median of reps ≥2)

| L tokens | full | window | sum-80 | sum-200 | full peak GB | feasible |
|---|---|---|---|---|---|---|
| 1,024 | 165 | 94 | 28 | 31 | 15.46 | ✓ |
| 2,048 | 325 | 93 | 29 | 32 | 15.65 | ✓ |
| 4,096 | 667 | 68 | 29 | 32 | 16.07 | ✓ |
| 8,192 | 1369 | 62 | 29 | 32 | 16.89 | ✓ |
| 16,384 | 3090 | 70 | 29 | 32 | 18.53 | ✓ |
| 24,576 | 5245 | 98 | 30 | 32 | 20.17 | ✓ |
| 32,768 | 7805 | 65 | 29 | 32 | 21.81 | ✓ |
| 49,152 | 14820 | 67 | 31 | 36 | 25.10 | ✓ |
| 65,536 | 21720 | 68 | 31 | 36 | 28.38 | ✓ |

#### Update Latency (ms, median)

| L tokens | sum-80 update | sum-200 update | incr warm | incr cold |
|---|---|---|---|---|
| 1,024 | 2535 | 5722 | 66 | 200 |
| 2,048 | 2796 | 3525 | 38 | 345 |
| 4,096 | 2812 | 3563 | 45 | 717 |
| 8,192 | 2824 | 3556 | 63 | 1458 |
| 16,384 | 2825 | 3590 | 95 | 3269 |
| 24,576 | 2864 | 3600 | 126 | 5561 |
| 32,768 | 2875 | 3581 | 154 | 8184 |
| 49,152 | 2881 | 3591 | 318 | 15766 |
| 65,536 | 2871 | 3561 | 330 | 22523 |

#### State Sizes and KV Cache

| L tokens | full (KB) | window (KB) | sum-80 (B) | sum-200 (B) | KV cache (MB) |
|---|---|---|---|---|---|
| 1,024 | 4 | 2 | 317 | 684 | 58.7 |
| 2,048 | 8 | 2 | 317 | 684 | 117.4 |
| 4,096 | 17 | 1 | 317 | 684 | 234.9 |
| 8,192 | 34 | 1 | 317 | 684 | 469.8 |
| 16,384 | 67 | 2 | 317 | 684 | 939.5 |
| 24,576 | 99 | 2 | 317 | 684 | 1409.3 |
| 32,768 | 131 | 1 | 317 | 684 | 1879.0 |
| 49,152 | 199 | 1 | 317 | 684 | 2818.6 |
| 65,536 | 264 | 1 | 317 | 684 | 3758.1 |

## Tier: rtx3090ti

### Model: qwen7b

GPU: NVIDIA GeForce RTX 3090 Ti (25.4 GB) | LLM: Qwen/Qwen2.5-7B-Instruct | KV bytes/token: 57,344

#### Restore Latency (ms, median of reps ≥2)

| L tokens | full | window | sum-80 | sum-200 | full peak GB | feasible |
|---|---|---|---|---|---|---|
| 1,024 | 220 | 119 | 25 | 32 | 15.46 | ✓ |
| 2,048 | 468 | 117 | 27 | 33 | 15.65 | ✓ |
| 4,096 | 982 | 91 | 28 | 34 | 16.07 | ✓ |
| 8,192 | 2028 | 79 | 28 | 35 | 16.89 | ✓ |
| 16,384 | 4868 | 97 | 28 | 35 | 18.53 | ✓ |
| 24,576 | 8525 | 137 | 28 | 33 | 20.17 | ✓ |
| 32,768 | 13694 | 89 | 30 | 37 | 21.81 | ✓ |
| 49,152 | — | 100 | 31 | 39 | — | ✗ |
| 65,536 | — | 104 | 32 | 39 | — | ✗ |

#### Update Latency (ms, median)

| L tokens | sum-80 update | sum-200 update | incr warm | incr cold |
|---|---|---|---|---|
| 1,024 | 2185 | 4943 | 34 | 264 |
| 2,048 | 2538 | 3113 | 41 | 500 |
| 4,096 | 2530 | 3178 | 48 | 983 |
| 8,192 | 2546 | 3107 | 63 | 2118 |
| 16,384 | 2555 | 3164 | 106 | 5086 |
| 24,576 | 2611 | 3277 | — | — |
| 32,768 | 2672 | 3327 | — | — |
| 49,152 | 2730 | 3400 | — | — |
| 65,536 | 2796 | 3499 | — | — |

#### State Sizes and KV Cache

| L tokens | full (KB) | window (KB) | sum-80 (B) | sum-200 (B) | KV cache (MB) |
|---|---|---|---|---|---|
| 1,024 | 4 | 2 | 317 | 684 | 58.7 |
| 2,048 | 8 | 2 | 317 | 684 | 117.4 |
| 4,096 | 17 | 1 | 317 | 684 | 234.9 |
| 8,192 | 34 | 1 | 317 | 684 | 469.8 |
| 16,384 | 67 | 2 | 317 | 684 | 939.5 |
| 24,576 | 99 | 2 | 317 | 684 | 1409.3 |
| 32,768 | 131 | 1 | 317 | 684 | 1879.0 |
| 49,152 | 199 | 1 | 317 | 684 | 2818.6 |
| 65,536 | 264 | 1 | 317 | 684 | 3758.1 |

## Tier: jetson_orin

*No results available for jetson_orin. Run `phase1_cost_profile.py --tier {tier}` on the target host.*

## Crossover Analysis

For each (tier, model, bandwidth, RTT) combination, the L at which:

- **A**: transferring full text becomes slower than re-prefilling from scratch (transfer_time > full_restore_ms/1000)

- **B**: full re-prefill becomes slower than summary pipeline (full_restore > sum80_update + sum80_restore)

- **C**: window-10 restore becomes ≥10× cheaper than full restore

'none_in_range' = crossover did not occur within the swept L range.


| tier | model | bandwidth | RTT | xA (L tokens) | xB (L tokens) | xC (L tokens) |
|---|---|---|---|---|---|---|
| a6000 | qwen7b | 1 Mbps | 50 ms | none_in_range | 16384 | 8192 |
| a6000 | qwen7b | 1 Mbps | 200 ms | 1024 | 16384 | 8192 |
| a6000 | qwen7b | 10 Mbps | 50 ms | none_in_range | 16384 | 8192 |
| a6000 | qwen7b | 10 Mbps | 200 ms | 1024 | 16384 | 8192 |
| a6000 | qwen7b | 100 Mbps | 50 ms | none_in_range | 16384 | 8192 |
| a6000 | qwen7b | 100 Mbps | 200 ms | 1024 | 16384 | 8192 |
| rtx3090ti | qwen7b | 1 Mbps | 50 ms | none_in_range | 16384 | 4096 |
| rtx3090ti | qwen7b | 1 Mbps | 200 ms | 1024 | 16384 | 4096 |
| rtx3090ti | qwen7b | 10 Mbps | 50 ms | none_in_range | 16384 | 4096 |
| rtx3090ti | qwen7b | 10 Mbps | 200 ms | none_in_range | 16384 | 4096 |
| rtx3090ti | qwen7b | 100 Mbps | 50 ms | none_in_range | 16384 | 4096 |
| rtx3090ti | qwen7b | 100 Mbps | 200 ms | none_in_range | 16384 | 4096 |

## Key Findings

**a6000 / qwen7b**:

- At L=1K: full-restore 165 ms, window 94 ms (57% of full), sum-80 restore 28 ms (17% of full).
- At L=64K: full-restore 21.7 s, window 68 ms, sum-80 update 2.9 s, warm-append 330 ms.
- No OOM across the full sweep (max L=65,536).
- xB (summary pipeline faster than full re-prefill): L=16384 tokens. Below this L, full re-prefill is cheaper; above it, regenerating a summary and restoring from it is faster.
- xC (window-10 ≥10× cheaper than full): L=8192 tokens. Window-restore latency is ~constant (~65-130 ms) regardless of L because it ingests a fixed ~2 K-token window.
- Transfer cost (text) is dominated by re-prefill at all tested bandwidths (≥1 Mbps): full text of 64K tokens is only ~256 KB → 2 s at 1 Mbps vs re-prefill cost of 21+ s. RTT matters at small L only.

**rtx3090ti / qwen7b**:

- At L=1K: full-restore 220 ms, window 119 ms (54% of full), sum-80 restore 25 ms (12% of full).
- OOM boundary: full-restore infeasible at L=49,152 (GPU memory exceeded; max feasible L=32,768).
- xB (summary pipeline faster than full re-prefill): L=16384 tokens. Below this L, full re-prefill is cheaper; above it, regenerating a summary and restoring from it is faster.
- xC (window-10 ≥10× cheaper than full): L=4096 tokens. Window-restore latency is ~constant (~65-130 ms) regardless of L because it ingests a fixed ~2 K-token window.
- Transfer cost (text) is dominated by re-prefill at all tested bandwidths (≥1 Mbps): full text of 64K tokens is only ~256 KB → 2 s at 1 Mbps vs re-prefill cost of 21+ s. RTT matters at small L only.

## Caveats

- Summary restore latency is constant (fixed stub text) — it does not vary with L. This is correct: the summarized representation is always ~80/200 tokens.

- Summary update latency is measured from the first 8000 chars of the context, not the full L tokens, to keep the update sweep tractable. At large L this underestimates the true update cost (which grows with L); the full-L update cost can be inferred from full_restore scaling × generation overhead.

- Incremental warm latency is constant (~200 tokens) because it only measures the new-turn append step, not the prior prefill. The cost of keeping state warm is the KV memory footprint (kv_bytes × L).

- Transfer cost does not include network measurement; it is derived from state size / bandwidth + RTT. Run under netem to validate.

- Jetson Orin rows are pending: run `phase1_cost_profile.py --tier jetson_orin` on the Jetson host.
