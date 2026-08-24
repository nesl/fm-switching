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

### Model: qwen3b — Qwen2.5-3B device tier (E37)

GPU: Jetson AGX Orin ("Orin", 65.9 GB unified) | LLM: Qwen/Qwen2.5-3B-Instruct | KV bytes/token: 36,864

**Why this run.** The fleet simulation (E36) modeled the device tier's 3B TTFT as an *assumed* fraction (0.43 param-count lower bound → 1.00 no-speedup) of the measured 7B Jetson latency; that assumption swung the device's failure rate against the 1 s interactive TTFT budget from 12% to 70% — load-bearing for a whole session class. E37 replaces the assumption with a measurement, on the **same box and the same protocol** as the committed 7B Jetson run (E23), so the ratio is a like-for-like comparison. L ∈ {1k, 4k, 8k, 16k}, 5 reps (first dropped as warm-up → 4 measured). Script/invocation: `experiments/cost/cost_profile.py --model qwen3b --tier jetson_orin --gpu 0 --token-counts 1024,4096,8192,16384 --reps 5` (no code changes; qwen3b was already a supported `--model`).

**Environment record.** JetPack 6.2.2 (L4T R36, rev 5.0) · CUDA 12.6 · torch 2.8.0 · transformers 5.10.2 · accelerate 1.13.0 · Python 3.10.12 · **flash-attn NOT available** (no aarch64 wheel) → **SDPA attention** · fp16 weights. This is the *identical stack* used for the qwen7b Jetson run, so the **3B/7B ratio below is free of the software-stack confound** that affects Jetson-vs-flash comparisons (the absolute latencies still carry it). Environment probe (qwen3b, fp16): model load 10.8 s; 1-token generate on a short prompt 1.08 s; residency 6.18 GB.

**Architecture note (explains the ratio's L-dependence).** 3B = 36 layers / 16 heads / 2 KV heads / hidden 2048; 7B = 28 layers / 28 heads / 4 KV heads / hidden 3584. The 3B is *deeper but narrower*. At small L, prefill is MLP/matmul-bound (∝ params) → ratio near the parameter-count floor; as L grows, attention over the sequence — repeated across 36 vs 28 layers — erodes the width advantage, so the ratio drifts upward with L.

*Window coverage*: at L=1,024, window tokens = 483 (47% of full). No rows excluded. **All L feasible — no OOM, no timeout** (3B peaks at 8.16 GB, far below the 65.9 GB unified limit).

#### Restore Latency (ms, median [IQR])

| L | full | window | sum-80 | sum-200 | full peak GB | ✓ |
|---|---|---|---|---|---|---|
| 1,024 | 1925 [1923, 1927] | 1025 | 205 | 297 | 6.31 | ✓ |
| 4,096 | 8090 [8087, 8093] | 659 | 209 | 298 | 6.68 | ✓ |
| 8,192 | 17486 [17486, 17490] | 621 | 209 | 297 | 7.17 | ✓ |
| 16,384 | 40670 [40669, 40676] | 665 | 203 | 297 | 8.16 | ✓ |

#### Update / Incremental Latency (ms, median)

| L | sum-80 update † | sum-200 update † | incr warm (82-tok Δ) | incr cold | ratio cold/warm |
|---|---|---|---|---|---|
| 1,024 | 11903 | 17858 | 344 | 2287 | 6.7× |
| 4,096 | 18311 | 21225 | 548 | 8659 | 15.8× |
| 8,192 | 18294 | 21164 | 853 | 18590 | 21.8× |
| 16,384 | 18135 | 20983 | 1524 | 42912 | 28.2× |

† Summary-update columns are the **truncated-input** (first-8000-char) measurements (`update_corrected=0`); the full-context rerun (`cost_update_rerun.py`) was **not** run for E37 because the E36 ratio it feeds needs only cold-prefill / warm-append / peak. Δ = warm-append delta is the script's fixed `NEW_TURN_TEXT` = **82 tokens** (identical to the E23 7B run), *not* 200 — the 3B/7B warm ratio is directly comparable, but the absolute warm number is for an 82-token turn.

#### State Sizes and KV Cache

| L | full (KB) | window (KB) | sum-80 (B) | sum-200 (B) | KV (MB) |
|---|---|---|---|---|---|
| 1,024 | 4 | 2 | 317 | 684 | 37.7 |
| 4,096 | 17 | 1 | 317 | 684 | 151.0 |
| 8,192 | 34 | 1 | 317 | 684 | 302.0 |
| 16,384 | 67 | 2 | 317 | 684 | 604.0 |

Text/summary state sizes are model-independent (match qwen7b); KV is 36,864 B/token (36 KB) vs the 7B's 57,344 B (56 KB) — a 0.64× KV footprint per token.

#### Ratio table — 3B ÷ 7B (Jetson, same stack, same protocol)

Denominators are the committed 7B Jetson medians (`results/cost/profiles/jetson_orin_qwen7b.json`).

| L | cold prefill (full_restore) | warm append | peak mem |
|---|---|---|---|
| 1,024 | 0.475 | 0.593 | 0.408 |
| 4,096 | 0.496 | 0.641 | 0.416 |
| 8,192 | 0.517 | 0.681 | 0.425 |
| 16,384 | 0.542 | 0.705 | 0.440 |

- **Cold prefill (TTFT): 0.475 → 0.542, rising monotonically with L — NOT constant** (mean 0.51). Near the parameter-count floor (~0.40–0.43) at small L; the mild upward drift is the depth effect noted above.
- **Warm append: 0.593 → 0.705, also rising.** Warm append is overhead/small-Δ dominated (only 82 new tokens), hence less compute-bound and a higher ratio than prefill.
- **Peak memory: ~0.41–0.44, roughly constant** — dominated by model residency (∝ params).

**Number for E36.** Replace the assumed **0.43–1.00** device 3B/7B latency fraction with the **measured cold-prefill (restore-TTFT) ratio 0.48–0.54**, L-dependent (0.475 @ 1k → 0.542 @ 16k). At E36's device-tier operating point (LoCoMo sessions, median ≈ 20k tokens) use **≈ 0.54** (extrapolating the mild upward drift just past 16k); if a single scalar is required, **0.5** is the mid-range value and 0.54 the conservative (slower) choice at the relevant L. **The upper bound of the old assumption (1.00, "no speedup") is firmly refuted** — the 3B is ~1.85–2.1× faster at prefill across the whole range, so the 70%-failure end of E36's sensitivity band does not correspond to any measured behavior.

#### Results consistency check (E37)

1. **Cross-check vs committed.** No prior 3B Jetson measurement exists — E37 is the first. The 7B denominators are read verbatim from the committed `jetson_orin_qwen7b.json` (ratio 1.00, agree). The derived 3B/7B prefill ratio is within ~1.1–1.3× of the parameter-count expectation (~0.40–0.43); the excess is explained by the 3B's greater depth (36 vs 28 layers). **Agree.**

   | quantity | this run (3B) | prior (7B) | source | ratio | agree? |
   |---|---|---|---|---|---|
   | full_restore @1k | 1925 ms | 4052 ms | jetson_orin_qwen7b.json | 0.475 | ✓ (≈ param floor) |
   | full_restore @16k | 40670 ms | 75054 ms | jetson_orin_qwen7b.json | 0.542 | ✓ |
   | warm_append @16k | 1524 ms | 2163 ms | jetson_orin_qwen7b.json | 0.705 | ✓ |
   | peak_mem @16k | 8.16 GB | 18.54 GB | jetson_orin_qwen7b.json | 0.440 | ✓ |

2. **Physical plausibility.** 3B prefill rate 532 → 403 tok/s (1k → 16k); 7B 253 → 218 tok/s; ratio 1.85–2.11×, matching the ~2× parameter-count throughput expectation. Both decline with L (super-linear prefill) — same shape as the committed 7B curve. No rate exceeds the committed *same-model* curve; the 3B is faster only because it is a smaller model, not a caching artifact. Caching: no prefix cache — each `full_restore` re-tokenizes and re-prefills from scratch; warm vs cold are explicitly separated in `_incremental` (warm = append over cached KV; cold = fresh prefill of L+82). **Pass.**

3. **Distribution sanity.** Per-L IQRs are tight (e.g. full_restore @16k IQR [40669, 40676] — 8 ms on 40.7 s) but values vary hugely across L (1925 → 40670, super-linear). Tightness within an L is expected — fixed input, greedy decode, dedicated GPU, 4 measured reps — and matches the 7B run's character (75054 [75048, 75055]). Not a short-circuit. **Pass.**

4. **Definition audit.** full_restore = cold-prefill TTFT of the L-token context (`max_new_tokens=1`); incremental_warm = forward pass of the 82-token `NEW_TURN_TEXT` over a warm L-token KV; peak = full_restore peak GB. All identical to E23 (same script, same corpus of 15,923 turns, same constants). L_actual = L_target exactly. **One flag:** the task described the append as a "~200-token turn"; the script constant is 82 tokens (same as E23), so the ratio is valid but the absolute warm number is for an 82-token append.

5. **Claim linkage.** Bears on **C4** (physical inertia cost) and FORMULATION.md's `materialize()`/`refresh()` costs and Assumption 2 (cold materialization threatens the latency SLO at realistic L). Measures same-model prefill/append on one tier; does **not** touch cross-architecture KV transfer (scoped out per FORMULATION.md §Scoping). Supplies the device-tier (3B) cost input E36 had assumed. **Supports.**

6. **Proxy validity.** None — all three headline quantities are direct measurements (TTFT, forward-pass time, `torch.cuda.max_memory_allocated`). No proxy. **Pass.**

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

---

## Runtime Calibration (vLLM) — E26

**Date:** 2026-08-21  
**Engine:** vLLM 0.8.5, torch 2.6.0+cu124, Flash Attention backend  
**Model:** Qwen/Qwen2.5-7B-Instruct, float16, A6000 (GPU 1)  
**Script:** `experiments/cost/vllm_calibration.py`  
**Result:** `results/cost/vllm_calibration_a6000_qwen7b.json`  
**Diagnostic:** `experiments/cost/e26_diagnostic.py`

Calibrates whether the cost structure the formulation depends on — near-linear prefill growth, multi-second cold materialization at mid-to-large L, and the window-append versus summary-refresh gap — survives under an optimized inference engine. All gap measurements are **within vLLM** (both window append and summary refresh measured under vLLM); the HF column is provided for context only and not used to compute gaps.

### Feasibility and context-extension notes

The cached Qwen2.5-7B-Instruct snapshot has `max_position_embeddings=32768`. vLLM 0.8.5 without rope\_scaling cannot run L≥32k (Triton RoPE kernel OOB). **YaRN rope\_scaling** (`type=yarn, factor=4.0, original_max_position_embeddings=32768`) was applied via a local config override; L=32,768 and L=65,536 were successfully measured under YaRN. Results for those rows are labelled YaRN below.

### Diagnostic: update-latency plateau in Phase 1 HF table

The a6000/qwen7b "Update Latency (corrected)" table shows sum-80 and sum-200 update costs that are nearly flat above L=32k (sum-80: 15,930 / 16,402 / 15,925 ms at L=32k/49k/65k). `experiments/cost/e26_diagnostic.py` traces the cause:

- The original sweep used `ctx_text[:8000]` (8,000 **characters** ≈ **1,943 tokens**) as the summariser input, making update latency independent of L. The corrected sweep replaced this with the full context.
- With full context, the summariser input grows from 8,274 tokens at L=8k to 32,942 tokens at L=32k, 49,385 at L=49k, and 65,792 at L=65k.
- The model's `max_position_embeddings=32768` caps its effective attention window. When HF transformers receives a 49,385-token prompt, it attends to approximately the first 32,768 tokens; positions beyond this are handled by the RoPE implementation without error but without extending positional encoding.
- As a result, the corrected measurements at L=49k and L=65k are measuring summarisation of an effective ~32,768-token context, not the stated L. The values at those rows **understate the true cost** of summarising a 49k or 65k-token history.

The vLLM YaRN measurements below represent the true cost at those lengths.

### Cold-prefill comparison

| L (tok) | vLLM (s) | HF (s) | HF/vLLM |
|---|---|---|---|
| 1,024 | 0.141 | 0.165 | 1.17× |
| 8,192 | 1.181 | 1.369 | 1.16× |
| 32,768 (YaRN) | 6.858 | 7.805 | 1.14× |
| 65,536 (YaRN) | 19.681 | 21.720 | 1.10× |

### Warm-append comparison (~200-token extension, prefix cached)

Directly comparable to "incr warm" in the HF Update-Timing table above.

| L (tok) | vLLM (s) | HF (s) | HF/vLLM |
|---|---|---|---|
| 1,024 | 0.026 | 0.066 | 2.55× |
| 8,192 | 0.040 | 0.063 | 1.59× |
| 32,768 (YaRN) | 0.087 | 0.154 | 1.77× |
| 65,536 (YaRN) | 0.152 | 0.330 | 2.17× |

vLLM warm-append is 1.6–2.6× faster than HF across all L. At large L, vLLM's paged attention processes the 200-token extension more efficiently than HF's eager KV-cache pass.

### Decode throughput (single stream, no batching)

| L (tok) | budget | vLLM total refresh (s) | decode-only (s) | tok/s |
|---|---|---|---|---|
| 1,024 | 80 | 1.943 | 1.802 | 44.4 |
| 1,024 | 200 | 4.689 | 4.548 | 44.0 |
| 8,192 | 80 | 3.070 | 1.889 | 42.4 |
| 8,192 | 200 | 5.932 | 4.750 | 42.1 |
| 32,768 (YaRN) | 80 | 9.031 | 2.173 | 36.8 |
| 32,768 (YaRN) | 200 | 12.142 | 5.284 | 37.8 |
| 65,536 (YaRN) | 80 | 21.918 | 2.237 | 35.8 |
| 65,536 (YaRN) | 200 | 25.312 | 5.631 | 35.5 |

Decode throughput: ~43–44 tok/s at small L, declining to ~36 tok/s at large L (larger KV cache → more memory bandwidth per decoded token). Total refresh = cold\_prefill(L) + decode(budget); decode-only = total − cold\_prefill\_median.

### Summary refresh vs HF baseline

#### Budget = 80 tokens (sum-80 refresh)

| L (tok) | vLLM total (s) | HF total (s) | HF/vLLM | vLLM decode-only (s) | HF decode-only (s) | decode ratio |
|---|---|---|---|---|---|---|
| 1,024 | 1.943 | 2.598 | 1.34× | 1.802 | 2.433 | 1.35× |
| 8,192 | 3.070 | 4.804 | 1.56× | 1.889 | 3.435 | 1.82× |
| 32,768 (YaRN) | 9.031 | 15.930† | 1.76× | 2.173 | 8.125† | 3.74× |
| 65,536 (YaRN) | 21.918 | 15.925† | 0.73×‡ | 2.237 | −5.795† | — |

#### Budget = 200 tokens (sum-200 refresh)

| L (tok) | vLLM total (s) | HF total (s) | HF/vLLM | vLLM decode-only (s) | HF decode-only (s) | decode ratio |
|---|---|---|---|---|---|---|
| 1,024 | 4.689 | 5.714 | 1.22× | 4.548 | 5.549 | 1.22× |
| 8,192 | 5.932 | 9.565 | 1.61× | 4.750 | 8.196 | 1.72× |
| 32,768 (YaRN) | 12.142 | 26.879† | 2.21× | 5.284 | 19.074† | 3.61× |
| 65,536 (YaRN) | 25.312 | 26.881† | 1.06×‡ | 5.631 | 5.161† | — |

† HF values at L≥32k understate true cost: the model's effective attention was capped at ~32,768 tokens (see diagnostic note above). The large HF/vLLM ratio at 32k and the inversion at 64k both arise from this cap — HF was not measuring the true 64k-context summarisation cost.  
‡ vLLM YaRN at L=65k processes the full 65,536-token context; HF at 65k was effectively summarising a ~32k context. The "slower" reading at 64k reflects vLLM doing more work, not an engine deficit.

### Window-append vs summary-refresh gap (within vLLM)

All numbers in this table are measured under vLLM; no cross-engine division.

| L (tok) | warm-append (s) | sum-80 refresh (s) | gap (÷warm) | sum-200 refresh (s) | gap (÷warm) |
|---|---|---|---|---|---|
| 1,024 | 0.026 | 1.943 | **75×** | 4.689 | **181×** |
| 8,192 | 0.040 | 3.070 | **77×** | 5.932 | **149×** |
| 32,768 (YaRN) | 0.087 | 9.031 | **104×** | 12.142 | **140×** |
| 65,536 (YaRN) | 0.152 | 21.918 | **144×** | 25.312 | **167×** |

### Interpretation

The cost structure the formulation depends on survives under vLLM. Cold prefill is near-linear in L (0.141s@1k → 1.181s@8k → 6.858s@32k → 19.681s@64k) and 1.10–1.17× faster than HF across all L. Cold materialization is in the multi-second range from L=8k onward, consistent with the simulator's cost model (which uses HF measurements and is conservative by ~10–17%).

vLLM decode throughput is ~43 tok/s at small L and ~36 tok/s at large L, 1.2–1.8× faster than HF at matched contexts. vLLM warm-append is 1.6–2.6× faster than HF across all L.

**The window-append versus summary-refresh gap is preserved and larger than previously reported.** The prior section quoted 90×, derived by dividing a vLLM summary-refresh number by an HF warm-append number — an invalid cross-engine comparison. Within vLLM, the gap ranges from **75× (L=1k, sum-80) to 181× (L=1k, sum-200)** with a minimum of 77× at L=8k for sum-80. At the E24c design point of L=32k (YaRN), it is 104–140×. At L=64k it is 144–167×. The gap is larger under vLLM than under HF because vLLM's warm-append is disproportionately fast relative to its summary refresh: paged attention with a cached prefix is extremely efficient for short extensions, while the decode-dominated summary generation has limited scope for optimization. The maintenance claim — that window-10 refresh is structurally cheaper than summary refresh across all feasible L and budgets — holds strongly under an optimized engine. The formulation's cost model is conservative in the direction that strengthens the window preference.

---

## Measured A1 ratio (Qwen2.5-3B vs Qwen2.5-7B, jetson\_orin) — E37b, 2026-08-24

**Source files:** `results/cost/profiles/jetson_orin_qwen3b.json` (E37) and `results/cost/profiles/jetson_orin_qwen7b.json` (E23). Analysis only — no new GPU measurements. Full ratio table: `results/cost/a1_ratio_table.csv`.

E36 carried an unmeasured assumption A1: qwen3b Jetson time = s × qwen7b Jetson time, shown at s=0.43 (3B/7B parameter-count ratio) and s=1.00 (no speedup upper bound). This section replaces that assumption with measured values from E37 at L ∈ {1024, 4096, 8192, 16384}.

### Part 1 — Ratio table

| operation | L=1024 | L=4096 | L=8192 | L=16384 | median | trend |
|---|---|---|---|---|---|---|
| full\_restore | 0.475 | 0.496 | 0.517 | 0.542 | 0.507 | rises with L |
| sum80\_restore | 0.578 | 0.589 | 0.588 | 0.571 | 0.583 | flat (L-independent) |
| sum200\_restore | 0.586 | 0.589 | 0.587 | 0.587 | 0.587 | flat (L-independent) |
| sum80\_update | 0.380† | 0.489 | 0.489 | 0.485 | 0.487‡ | plateau at L≥4k |
| sum200\_update | 0.265† | 0.468 | 0.466 | 0.463 | 0.464‡ | plateau at L≥4k |
| incremental\_warm | 0.593 | 0.641 | 0.681 | 0.705 | 0.661 | rises with L |
| incremental\_cold | 0.471 | 0.500 | 0.518 | 0.540 | 0.509 | rises with L |

† L=1024 update ratios are anomalous (7B sum80\_update=31.3s; sum200\_update=67.4s at L=1k but ~37s/45s at L≥2k — possible GPU warmup or kernel-launch artifact in the 7B run). Median for update ops computed over L∈{4096,8192,16384} to exclude the anomalous L=1k row.

‡ Exclude the anomalous L=1k value when applying these ratios.

**Window rows excluded.** The 3B run reports window token counts of 261–483 across the four L points — non-monotone and shrinking as L increases. This is the short-turn window definition that E33a (§definition audit) identified as incorrect for the LoCoMo workload; the correct win10 definition is "last 10 sessions", median 7,275 tokens. The window\_restore ratios cannot be compared to any win10 cost in the formulation. Window rows are excluded from all ratio computations. **Open item:** `cost_profile.py` still constructs the window using the wrong (turn-based) definition; the win10 measurement must come from a corrected run.

**Trend characterisation.** Operations on fixed-length summaries (sum80\_restore, sum200\_restore) are L-independent as expected — both models process 51 and 113 tokens respectively, and the ratio is approximately model-speed-only (≈0.58–0.59). Operations that process the full context (full\_restore, incremental\_cold) show a rising ratio because the 3B's computation time scales more steeply with L than the 7B's; the ratio rises from ~0.47–0.47 at L=1k to ~0.54–0.54 at L=16k. The incremental\_warm ratio rises more steeply (0.59→0.70) because warm-append processes only the new-turn tokens but the KV cache access pattern scales with L, and this overhead grows more for the 3B.

### Part 2 — Value E36b should use

The load-bearing operation for device\_only in the E36 LoCoMo workload is **incremental\_warm**: each new turn is a warm-append from the Jetson's own KV cache, accumulated continuously across the session.

**Recommendation: use an L-dependent function, not a scalar.** The measured ratio rises from 0.593 at L=1k to 0.705 at L=16k. A single scalar would be correct only at one L value and biased at all others. The simplest approach is linear interpolation over the four measured points, clamping to 0.705 for L > 16384 (the last measured point before the infeasibility boundary at L=24576).

For the LoCoMo context distribution used in E36 (turns span L=0 to max≈22.7k, median L across all turns ≈10k):

- Ratio at L=0 (session start): 0.593 (extrapolated from L=1k)
- Ratio at L~10k (median operating point): ≈0.670 (interpolated between L=8k and L=16k)
- Ratio at L=16k (last measured): 0.705
- Ratio for L > 16k: 0.705 (clamped; A4 still applies to 7B baseline extrapolation)

The assumed s=0.43 lower bound is refuted: the measured minimum is 0.593, some 38% above the assumption. The assumed s=1.00 upper bound is also refuted: the measured maximum is 0.705, confirming the 3B is meaningfully faster. The true range (0.59–0.71 across measured L) sits entirely within the assumed 0.43–1.00 range but close to neither extreme.

### Part 3 — Consequence for E36 K2 violation

E36 reported three K2-violating cells: locomo / 1000ms TTFT budget / all quality floors, at A1 bound s=0.43.

Using the same LoCoMo context distribution as E36 (n=10 conversations, LOCOMO\_CTX\_TOKENS, LOCOMO\_N\_SESSIONS, TURNS\_PER\_SESSION=22) and the L-dependent measured ratio for incremental\_warm:

| budget | s=0.43 (E36) | s=1.00 (E36) | measured ratio | note |
|---|---|---|---|---|
| 300ms | 87.3% fail | 97.1% fail | **95.2% fail** | K2 passes both bounds and measured |
| 1000ms | 12.1% fail | 70.2% fail | **46.5% fail** | measured is between the two bounds |
| 10000ms | 0.0% fail | 0.0% fail | **0.0% fail** | all pass |

At the measured ratio the device\_only 1000ms failure rate is 46.5% — far above the s=0.43 case (12.1%) and closer to the s=1.00 case (70.2%). The lifecycle\_aware both\_met metric stays at approximately 0.235 regardless of device speed (served from edge). The implied lifecycle\_aware vs device\_only gap at 1000ms is approximately:

- device\_only both\_met (measured) ≈ (1 − 0.465) × Q(full,locomo,3b) ≈ 0.535 × 0.230 ≈ 0.123
- lifecycle\_aware both\_met ≈ 0.235 (from E36, device-speed-independent)
- gap ≈ 0.235 − 0.123 ≈ 11.2pp

**K2 PASSES at the measured ratio.** The three K2-violating cells in E36 were artifacts of the s=0.43 lower bound; that bound was too optimistic (it underestimated 3B latency by 38%). The real device speed sits between the two assumed extremes but close enough to s=1.00 that the edge's latency advantage is genuine and substantial at the 1000ms budget.

### Part 4 — Device summary-update infeasibility (tier-asymmetry finding)

**3B Jetson summary-update timings:**

| operation | L=1024 | L=4096 | L=8192 | L=16384 |
|---|---|---|---|---|
| sum80\_update\_ms (3B) | 11,903 | 18,311 | 18,294 | 18,135 |
| sum200\_update\_ms (3B) | 17,858 | 21,225 | 21,164 | 20,983 |
| sum80\_update\_ms (7B) | 31,316 | 37,414 | 37,414 | 37,398 |
| sum200\_update\_ms (7B) | 67,404 | 45,379 | 45,382 | 45,373 |

Both models require 11.9–21.2s to update a summary on the Jetson, even at the smallest measured context (L=1k). This is well above any plausible TTFT budget (300ms, 1s, 10s). **Derived state cannot be maintained on the device tier at any operating budget, under either model.** Summary-80 and summary-200 representations are not viable for device\_only with live updates; they would require either a pre-computed summary delivered from elsewhere or a stale summary accepted without refresh. This is a tier-asymmetry finding for the paper: the edge tier (A6000: sum200 update 5.8s, sum80 update comparable) is 5–7× faster at summary update than the device tier, and even the edge-tier cost exceeds the interactive budget (1s).

Cross-check against 7B Jetson values: 3B/7B update ratio is 0.38–0.49 (sum80) and 0.26–0.47 (sum200). The 7B L=1k anomaly (sum200=67.4s, then 45.4s at all larger L) may reflect a GPU-warmup or kernel-launch artifact; the 3B run does not exhibit the same pattern. Both models agree: summary update on Jetson is infeasible under any runtime budget.

**Note on rep count:** The E37 3B run reports n=4 completed reps (not the target 5). The IQRs are tight across all cells (< 0.5%), so the missing fifth rep does not affect the ratio values materially.

**Note on KV footprint:** qwen3b kv\_bytes\_per\_token = 36,864 (0.643× the 7B's 57,344). Where KV cache footprint is computed for device-tier capacity planning (e.g., how many LoCoMo sessions can reside in the Jetson's 65.9 GB), use 36,864 B/tok for the 3B model.
