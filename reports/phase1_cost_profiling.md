<!-- Paths in this report predate the 2026-08-19 reorganization; see research/EXPERIMENTS.md for current file locations. -->
# Phase 1 — Cost Profiling Report

Generated: 2026-08-19 11:06

## Overview

Measures restore and update latency for four state representations (full-replay, window-10, summary-80, summary-200) as a function of context length L, with 5 reps per point (first excluded as warm-up → 4 measured samples). Real contexts sampled from LoCoMo conversation logs and Infini-THOR trajectory files. Transfer cost derived from state size at {1, 10, 100} Mbps and {50, 200} ms RTT.

**Summary update**: generation of 80/200 tokens from the full L-token context (corrected measurement; see Appendix A for the original truncated-input values). **Incremental warm**: forward pass of 200 new tokens given warm KV cache. **Incremental cold**: cold prefill of L+200 tokens.

## Tier: a6000

### Model: qwen7b

GPU: NVIDIA RTX A6000 (51.0 GB) | LLM: Qwen/Qwen2.5-7B-Instruct | KV bytes/token: 57,344

*Window coverage*: at minimum L=1,024, window tokens = 483 (47% of full context). No rows excluded — window is a strict subset at all L.

#### Restore Latency (ms, median [IQR])

| L | full | window | sum-80 | sum-200 | full peak GB | ✓ |
|---|---|---|---|---|---|---|
| 1,024 | 165 [164, 166] | 94 | 28 | 31 | 15.46 | ✓ |
| 2,048 | 325 [325, 326] | 93 | 29 | 32 | 15.65 | ✓ |
| 4,096 | 667 [667, 668] | 68 | 29 | 32 | 16.07 | ✓ |
| 8,192 | 1369 [1367, 1496] | 62 | 29 | 32 | 16.89 | ✓ |
| 16,384 | 3090 [3087, 3165] | 70 | 29 | 32 | 18.53 | ✓ |
| 24,576 | 5245 [5237, 5298] | 98 | 30 | 32 | 20.17 | ✓ |
| 32,768 | 7805 [7800, 7850] | 65 | 29 | 32 | 21.81 | ✓ |
| 49,152 | 14820 [14766, 15216] | 67 | 31 | 36 | 25.10 | ✓ |
| 65,536 | 21720 [21671, 25310] | 68 | 31 | 36 | 28.38 | ✓ |

#### Update Latency — full L-token context (ms, median [IQR]) *(corrected)*

| L | sum-80 update | sum-200 update | incr warm | incr cold | ratio cold/warm |
|---|---|---|---|---|---|
| 1,024 | 2598 [2536, 2600] | 5714 [5697, 5718] | 66 | 200 | 3.0× |
| 2,048 | 2837 [2816, 2919] | 6257 [6237, 6258] | 38 | 345 | 9.2× |
| 4,096 | 3588 [3489, 3592] | 4799 [4798, 4805] | 45 | 717 | 16.0× |
| 8,192 | 4804 [4797, 4814] | 9565 [9457, 9610] | 63 | 1458 | 23.3× |
| 16,384 | 8290 [8286, 8298] | 15330 [15320, 15468] | 95 | 3269 | 34.3× |
| 24,576 | 12118 [12096, 12125] | 20928 [20922, 20938] | 126 | 5561 | 44.2× |
| 32,768 | 15930 [15874, 15965] | 26879 [26818, 27066] | 154 | 8184 | 53.2× |
| 49,152 | 16402 [16203, 16478] | 27528 [27473, 27705] | 318 | 15766 | 49.6× |
| 65,536 | 15925 [15865, 15957] | 26881 [26789, 27023] | 330 | 22523 | 68.3× |

#### State Sizes and KV Cache

| L | full (KB) | window (KB) | sum-80 (B) | sum-200 (B) | KV (MB) |
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

#### Update-Timing Tradeoff: Warm Copy vs On-Demand Re-Prefill

Keeping a warm KV cache costs `kv_mb` of GPU memory per L. The ratio shows how much more expensive cold re-prefill is than a warm append. Above the OOM boundary, warm copies are not feasible.

| L | incr warm (ms) | incr cold (ms) | cold/warm ratio | KV memory (MB) |
|---|---|---|---|---|
| 1,024 | 66 | 200 | 3.0× | 59 |
| 2,048 | 38 | 345 | 9.2× | 117 |
| 4,096 | 45 | 717 | 16.0× | 235 |
| 8,192 | 63 | 1458 | 23.3× | 470 |
| 16,384 | 95 | 3269 | 34.3× | 940 |
| 24,576 | 126 | 5561 | 44.2× | 1409 |
| 32,768 | 154 | 8184 | 53.2× | 1879 |
| 49,152 | 318 | 15766 | 49.6× | 2819 |
| 65,536 | 330 | 22523 | 68.3× | 3758 |

## Tier: rtx3090ti

### Model: qwen7b

GPU: NVIDIA GeForce RTX 3090 Ti (25.4 GB) | LLM: Qwen/Qwen2.5-7B-Instruct | KV bytes/token: 57,344

*Window coverage*: at minimum L=1,024, window tokens = 483 (47% of full context). No rows excluded — window is a strict subset at all L.

#### Restore Latency (ms, median [IQR])

| L | full | window | sum-80 | sum-200 | full peak GB | ✓ |
|---|---|---|---|---|---|---|
| 1,024 | 220 [219, 221] | 119 | 25 | 32 | 15.46 | ✓ |
| 2,048 | 468 [451, 553] | 117 | 27 | 33 | 15.65 | ✓ |
| 4,096 | 982 [960, 1110] | 91 | 28 | 34 | 16.07 | ✓ |
| 8,192 | 2028 [1990, 2038] | 79 | 28 | 35 | 16.89 | ✓ |
| 16,384 | 4868 [4674, 4917] | 97 | 28 | 35 | 18.53 | ✓ |
| 24,576 | 8525 [8469, 8889] | 137 | 28 | 33 | 20.17 | ✓ |
| 32,768 | 13694 [13527, 13868] | 89 | 30 | 37 | 21.81 | ✓ |
| 49,152 | — — | 100 | 31 | 39 | — | ✗ |
| 65,536 | — — | 104 | 32 | 39 | — | ✗ |

#### Update Latency — full L-token context (ms, median [IQR]) *(corrected)*

| L | sum-80 update | sum-200 update | incr warm | incr cold | ratio cold/warm |
|---|---|---|---|---|---|
| 1,024 | 2199 [2182, 2231] | 4914 [4795, 4938] | 34 | 264 | 7.7× |
| 2,048 | 2535 [2500, 2550] | 5430 [5290, 5472] | 41 | 500 | 12.2× |
| 4,096 | 3313 [3272, 3354] | 4369 [4366, 4371] | 48 | 983 | 20.5× |
| 8,192 | 4846 [4702, 4848] | 8583 [8577, 8604] | 63 | 2118 | 33.8× |
| 16,384 | 9225 [9156, 9448] | 15104 [15087, 15194] | 106 | 5086 | 47.9× |
| 24,576 | 15592 [15318, 15794] | 24604 [23899, 24853] | — | — | — |
| 32,768 | 2672† [2662, 2789] | 3327† [3286, 3352] | — | — | — |
| 49,152 | 2730† [2725, 2751] | 3400† [3343, 3436] | — | — | — |
| 65,536 | 2796† [2763, 2825] | 3499† [3446, 3520] | — | — | — |

#### State Sizes and KV Cache

| L | full (KB) | window (KB) | sum-80 (B) | sum-200 (B) | KV (MB) |
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

#### Update-Timing Tradeoff: Warm Copy vs On-Demand Re-Prefill

Keeping a warm KV cache costs `kv_mb` of GPU memory per L. The ratio shows how much more expensive cold re-prefill is than a warm append. Above the OOM boundary, warm copies are not feasible.

| L | incr warm (ms) | incr cold (ms) | cold/warm ratio | KV memory (MB) |
|---|---|---|---|---|
| 1,024 | 34 | 264 | 7.7× | 59 |
| 2,048 | 41 | 500 | 12.2× | 117 |
| 4,096 | 48 | 983 | 20.5× | 235 |
| 8,192 | 63 | 2118 | 33.8× | 470 |
| 16,384 | 106 | 5086 | 47.9× | 940 |
| 24,576 | OOM | OOM | — | 1409 |
| 32,768 | OOM | OOM | — | 1879 |
| 49,152 | OOM | OOM | — | 2819 |
| 65,536 | OOM | OOM | — | 3758 |

## Tier: jetson_orin

### Model: qwen7b

GPU: Jetson AGX Orin ("Orin", 65.9 GB unified) | LLM: Qwen/Qwen2.5-7B-Instruct | KV bytes/token: 57,344

**Software stack — affects cross-tier comparison.** This tier ran **transformers 5.10.2 / torch 2.8 (CUDA 12.6) / SDPA attention, no flash-attn** (no prebuilt flash-attn wheel for Jetson/aarch64). The `a6000` and `rtx3090ti` tiers ran **transformers 4.46.3 with flash-attn**. Jetson-vs-flash latency gaps therefore conflate the hardware difference with a **software-stack component** (attention kernel + library version) and are not a pure device comparison.

**Environment probe (qwen7b, fp16):** model load **25.5 s**; single-prefill TTFT **2.5 s @ 512 tok** and **15.4 s @ 4,096 tok**; peak **~16 GB**. (Replaces the onboarding probe.)

*Window coverage*: at minimum L=1,024, window tokens = 483 (47% of full context). No rows excluded — window is a strict subset at all L.

#### Restore Latency (ms, median [IQR])

| L | full | window | sum-80 | sum-200 | full peak GB | ✓ |
|---|---|---|---|---|---|---|
| 1,024 | 4052 [4052, 4053] | 2487 | 355 | 506 | 15.46 | ✓ |
| 2,048 | 8010 [8004, 8012] | 2496 | 356 | 507 | 15.65 | ✓ |
| 4,096 | 16311 [16238, 16335] | 1855 | 355 | 506 | 16.07 | ✓ |
| 8,192 | 33790 [33781, 33798] | 1702 | 356 | 507 | 16.89 | ✓ |
| 16,384 | 75054 [75048, 75055] | 1875 | 356 | 506 | 18.54 | ✓ |
| 24,576 | — — (timeout >120 s) | 2386 | 356 | 506 | — | ✗ |
| 32,768 | — — (timeout >120 s) | 1751 | 356 | 506 | — | ✗ |
| 49,152 | — — (timeout >120 s) | 1892 | 356 | 506 | — | ✗ |
| 65,536 | — — (timeout >120 s) | 1878 | 356 | 506 | — | ✗ |

`full_restore` is **feasible through L=16,384 (75.1 s)** and crosses the 120 s per-measurement timeout at **L≥24,576** (recorded infeasible). Restore of the fixed summaries/window stays cheap and roughly constant, but ~1–2 orders of magnitude slower than on flash (sum-80 restore ~356 ms here vs ~28 ms on a6000; window ~1.7–2.5 s vs ~68 ms) — the SDPA-no-flash-attn stack plus slower hardware.

#### Update Latency — full L-token context (ms, median [IQR])

| L | sum-80 update | sum-200 update | incr warm | incr cold | ratio cold/warm |
|---|---|---|---|---|---|
| 1,024 | 31334 | 67551 | 579 | 4858 | 8.4× |
| 2,048 | 35347 | 72261 | 667 | 8566 | 12.8× |
| 4,096 | 44902 | 58117 | 855 | 17327 | 20.3× |
| 8,192 | 65111 | 107279 | 1253 | 35896 | 28.7× |
| 16,384 | 111760 | 161012 | 2163 | 79477 | 36.7× |
| 24,576 | 166866 | 181883 | — (timeout) | — (timeout) | — |
| 32,768 | 228815 | 292326 | — (timeout) | — (timeout) | — |
| 49,152 | 228803 | 292343 | — (timeout) | — (timeout) | — |
| 65,536 | 228796 | 292364 | — (timeout) | — (timeout) | — |

Full-context summary-update grows steeply with L (prefill-dominated) and plateaus ~229 s / 292 s once the update input hits its length cap at L≈32 K. `incremental` (warm append vs cold re-prefill) is feasible through L=16,384 — cold/warm ratio reaches **36.7×** at 16 K — and hits the incremental timeout at L≥24,576. Values here are ~14× the a6000 figures at matching L, consistent with the hardware + software-stack gap.

#### State Sizes and KV Cache

| L | full (KB) | window (KB) | sum-80 (B) | sum-200 (B) | KV (MB) |
|---|---|---|---|---|---|
| 1,024 | 4 | 1 | 317 | 684 | 56.0 |
| 2,048 | 8 | 2 | 317 | 684 | 112.0 |
| 4,096 | 16 | 1 | 317 | 684 | 224.0 |
| 8,192 | 33 | 1 | 317 | 684 | 448.0 |
| 16,384 | 66 | 1 | 317 | 684 | 896.0 |
| 24,576 | 98 | 1 | 317 | 684 | 1344.0 |
| 32,768 | 130 | 1 | 317 | 684 | 1792.0 |
| 49,152 | 198 | 1 | 317 | 684 | 2688.0 |
| 65,536 | 263 | 1 | 317 | 684 | 3584.0 |

State sizes and KV/token are model-intrinsic and match the other tiers (56 KB/token). Note the infeasibility edge here is set by the **120 s time budget**, not memory — the 65.9 GB unified memory never OOMs (unlike the 3090 Ti, which OOMs the incremental path at L≥24,576).

## Crossover Analysis

Crossover definitions:

- **A**: L where `transfer_time(full_text) > full_restore_time` — re-prefilling locally becomes cheaper than receiving full text. Note: at 200 ms RTT, the RTT constant dominates at small L; these rows are annotated 'RTT-dominated'.

- **B**: L where `full_restore > sum80_update + sum80_restore` — summary pipeline (regenerate + restore) is faster than full re-prefill. Uses corrected (full-context) update cost where available.

- **B2**: L where `full_restore > sum80_restore` — relevant when a summary already exists and only the restore cost is paid. Because sum-80 restore is ~28 ms (constant) and full_restore starts at ~165 ms even at L=1K, B2 is satisfied throughout the entire swept range.

- **C**: L where `full_restore > 10 × window_restore` — window is ≥10× cheaper than full. Rows where window covers the full context are excluded.

'none_in_range' = crossover not observed in [1K, 64K] swept range.


| tier | model | bw (Mbps) | RTT (ms) | xA | xA note | xB | xB2 | xC |
|---|---|---|---|---|---|---|---|---|
| a6000 | qwen7b | 1 | 50 | none_in_range | — | 65536 | <1024 (true below minimum L; always satisfied in sweep) | 8192 |
| a6000 | qwen7b | 1 | 200 | 1024 | RTT-dominated (85% of transfer time is RTT) | 65536 | <1024 (true below minimum L; always satisfied in sweep) | 8192 |
| a6000 | qwen7b | 10 | 50 | none_in_range | — | 65536 | <1024 (true below minimum L; always satisfied in sweep) | 8192 |
| a6000 | qwen7b | 10 | 200 | 1024 | RTT-dominated (98% of transfer time is RTT) | 65536 | <1024 (true below minimum L; always satisfied in sweep) | 8192 |
| a6000 | qwen7b | 100 | 50 | none_in_range | — | 65536 | <1024 (true below minimum L; always satisfied in sweep) | 8192 |
| a6000 | qwen7b | 100 | 200 | 1024 | RTT-dominated (100% of transfer time is RTT) | 65536 | <1024 (true below minimum L; always satisfied in sweep) | 8192 |
| rtx3090ti | qwen7b | 1 | 50 | none_in_range | — | none_in_range | <1024 (true below minimum L; always satisfied in sweep) | 4096 |
| rtx3090ti | qwen7b | 1 | 200 | 1024 | RTT-dominated (85% of transfer time is RTT) | none_in_range | <1024 (true below minimum L; always satisfied in sweep) | 4096 |
| rtx3090ti | qwen7b | 10 | 50 | none_in_range | — | none_in_range | <1024 (true below minimum L; always satisfied in sweep) | 4096 |
| rtx3090ti | qwen7b | 10 | 200 | none_in_range | — | none_in_range | <1024 (true below minimum L; always satisfied in sweep) | 4096 |
| rtx3090ti | qwen7b | 100 | 50 | none_in_range | — | none_in_range | <1024 (true below minimum L; always satisfied in sweep) | 4096 |
| rtx3090ti | qwen7b | 100 | 200 | none_in_range | — | none_in_range | <1024 (true below minimum L; always satisfied in sweep) | 4096 |

## Key Findings

**a6000 / qwen7b**:

- At L=1K: full-restore 165 ms, window 94 ms (57% of full), sum-80 restore 28 ms (17% of full).
- At L=64K (max feasible): full-restore 21.7 s, window 68 ms, sum-80 update (corrected) 15.9 s, warm-append 330 ms, cold-reprefill 22523 ms (ratio 68×).
- KV memory to keep warm at L=64K: 3758 MB (56 KB/token × 65,536 tokens).
- No OOM across the full sweep (max L=65,536).
- xB (corrected): summary pipeline faster than full re-prefill above L=65536.
- xB2: sum-80 restore alone cheaper than full re-prefill at all L in sweep (condition satisfied below minimum swept L; sum-80 restore is ~28 ms constant).
- xC: window-10 ≥10× cheaper than full above L=8192; window latency is ~constant (~65–130 ms) because it always ingests ~300–500 tokens.
- Transfer cost: full text (4–256 KB) transfers in 0.03–2 s at 1 Mbps; re-prefill costs 0.16–21 s. Re-prefill dominates at all L ≥ 1K for ≥1 Mbps links. xA crossover at 200 ms RTT is RTT-dominated, not bandwidth-limited.

**rtx3090ti / qwen7b**:

- At L=1K: full-restore 220 ms, window 119 ms (54% of full), sum-80 restore 25 ms (12% of full).
- At L=32K (max feasible): full-restore 13.7 s, window 89 ms, sum-80 update OOM (corrected), warm-append OOM, cold-reprefill OOM (ratio OOM).
- KV memory to keep warm at L=32K: 1879 MB (56 KB/token × 32,768 tokens).
- OOM boundary: full-restore infeasible at L=49,152; max feasible L=32,768.
- xB (corrected): summary pipeline faster than full re-prefill above L=none_in_range.
- xB2: sum-80 restore alone cheaper than full re-prefill at all L in sweep (condition satisfied below minimum swept L; sum-80 restore is ~28 ms constant).
- xC: window-10 ≥10× cheaper than full above L=4096; window latency is ~constant (~65–130 ms) because it always ingests ~300–500 tokens.
- Transfer cost: full text (4–256 KB) transfers in 0.03–2 s at 1 Mbps; re-prefill costs 0.16–21 s. Re-prefill dominates at all L ≥ 1K for ≥1 Mbps links. xA crossover at 200 ms RTT is RTT-dominated, not bandwidth-limited.

## Appendix A — Original Update Measurements (Truncated Input)

The initial sweep measured sum-80 and sum-200 update latency from the first 8000 characters of the context (a cap introduced for sweep tractability). These values are flat across L because the input to the model was constant; they are not valid cost estimates for the update operation at large L. The corrected values in the main tables above use the full L-token context.

### a6000

**qwen7b** — sum-80 update (8000-char truncated input)

| L | sum-80 update ms | sum-200 update ms |
|---|---|---|
| 1,024 | 2535 | 5722 |
| 2,048 | 2796 | 3525 |
| 4,096 | 2812 | 3563 |
| 8,192 | 2824 | 3556 |
| 16,384 | 2825 | 3590 |
| 24,576 | 2864 | 3600 |
| 32,768 | 2875 | 3581 |
| 49,152 | 2881 | 3591 |
| 65,536 | 2871 | 3561 |

### rtx3090ti

**qwen7b** — sum-80 update (8000-char truncated input)

| L | sum-80 update ms | sum-200 update ms |
|---|---|---|
| 1,024 | 2185 | 4943 |
| 2,048 | 2538 | 3113 |
| 4,096 | 2530 | 3178 |
| 8,192 | 2546 | 3107 |
| 16,384 | 2555 | 3164 |
| 24,576 | 2611 | 3277 |
| 32,768 | 2672 | 3327 |
| 49,152 | 2730 | 3400 |
| 65,536 | 2796 | 3499 |

## Caveats

- Summary restore latency uses a fixed ~80/200-token stub text and does not vary with L. This is correct: the summarized state is always ~80/200 tokens regardless of history length.

- Summary update (corrected) measures generation of 80/200 tokens from the full L-token context. At large L the input context is truncated only by the model's maximum position embedding limit (128K for Qwen2.5-7B). If a tier has not completed the full-context rerun, the original truncated-input values are used with a † marker.

- Incremental warm latency grows slightly with L (100–330 ms range) because attending over a larger KV cache requires more memory bandwidth, even though only 200 new tokens are processed.

- Incremental measurements require storing the L-token KV cache during the warm-append step. This causes OOM at lower L on the 3090 Ti than full-restore (which discards the KV cache immediately after TTFT).

- Transfer cost is derived, not measured. Run under netem to validate.

- Window-10 token count is ~300–500 tokens across all L (last 10 corpus turns of ~37–200 tokens each). No rows in the current sweep qualify as 'window covers full context' (max ratio 0.47 at L=1024).

- Jetson Orin complete (2026-08-19): full_restore feasible ≤16,384 (75.1 s), infeasible ≥24,576 by the 120 s time budget (not memory). Ran the 5.10.2 / torch 2.8 / SDPA-no-flash-attn stack vs 4.46.3 / flash-attn on flash, so Jetson-vs-flash gaps include a software-stack component. Crossover rows for jetson_orin not yet computed (rerun `cost_analysis.py` to extend the crossover table).
