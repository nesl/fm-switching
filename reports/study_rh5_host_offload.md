# StudyRH5 — host-memory KV offload for warm D2 histories (H100, vLLM)

**Stack:** vLLM 0.31.0+cu129 (venv `~/.venvs/fm-switching-vllm`, torch 2.13.0+cu129), FlashAttention 3, CUDA graphs, gmu 0.90, max_model_len 32768, bf16 KV (62,944 tokens on GPU), prefix caching ON, Qwen3-VL-32B-Instruct @0cfaf481, h100nvl GPU 3 (PCIe Gen5 ×16). GPU+host = vLLM's native `OffloadingConnector` (`--kv-offloading-backend native --kv-offloading-size 256`; 274.88 GB pinned shared-memory region). Watchdog and GPU monitor ran for the whole chain; no foreign process on GPU 3. Analysis: original `.venv`, CPU.
Pre-registration: research/EXPERIMENTS.md StudyRH5 (2026-10-19, before any GPU run). Chain 19:25–23:28 (4.05 h; estimate 3.64 h — see Deviations).

## Decision: **OFFLOAD REMOVES SCARCITY**

| pre-registered condition | D = 16 | D = 24 | met? |
|---|---|---|---|
| GPU+host warm escalation TTFT median ≤ 1.5 s | **0.60 s** | **0.81 s** | yes |
| GPU+host p99 ≤ 10 s | **1.78 s** | **2.00 s** | yes |
| GPU-only collapses (median > 5 s) | **802 s** | **1,520 s** | yes |

With 256 GiB of host memory as a second KV tier, 24 warm D2 sessions (warm footprint ≈ 3.96× GPU KV) escalate with a 0.81-s median and 2.0-s p99, at a 0.97 token hit, 95% of it served from host. Without it, the same fleet has already collapsed at D = 8 (median 96 s). Within D ≤ 24 the new knee was not reached; the trend (median 0.54 → 0.52 → 0.60 → 0.81 s, waiting max 0 → 6) and GPU KV usage peaking at 0.97 at D = 24 point to the next limit being the GPU KV for the *running* set, not host capacity or PCIe (≈ 6 GB/s average load vs ≈ 50 GB/s measured reload rate).

Scope: one H100, one repetition per cell, 15-min windows, D2 sessions ≤ ~11.8 min (RH4's context limit; 46 over-context requests at D = 24 in both configs, as pre-registered). The accuracy side is RH4's (D2 = K1); RH5 adds no accuracy.

## Part A — isolated reload cost (one request at a time, D2 format)

| state (server) | size | n (sessions) | TTFT median [min, max] | cached / prompt | GPU-local hits | host hits | verified |
|---|---|---|---|---|---|---|---|
| GPU-WARM (GPU-only) | 11k | 12 (4) | 0.382 [0.336, 0.481] | 10,928 / 11,050 | 10,928 | 0 | 12/12 |
| GPU-WARM (GPU+host) | 11k | 12 (4) | 0.415 [0.364, 0.502] | 10,928 / 11,050 | 10,928 | 0 | 12/12 |
| **HOST-WARM** (GPU+host) | 11k | 12 (4) | **0.459 [0.399, 0.538]** | 11,040 / 11,050 | **0** | **11,040** | 12/12 |
| COLD (GPU-only) | 11k | 12 (4) | **2.445 [2.393, 2.541]** | 0 / 11,050 | 0 | 0 | 12/12 |
| GPU-WARM (GPU-only) | 28k | 6 (2) | 0.874 [0.782, 0.921] | 27,936 / 28,114 | 27,936 | 0 | 6/6 |
| GPU-WARM (GPU+host) | 28k | 6 (2) | 0.873 [0.803, 0.956] | 27,936 / 28,114 | 27,936 | 0 | 6/6 |
| **HOST-WARM** (GPU+host) | 28k | 6 (2) | **1.001 [0.971, 1.006]** | 28,104 / 28,114 | **0** | **28,104** | 6/6 |
| COLD (GPU-only) | 28k | 6 (2) | **7.367 [7.313, 7.420]** | 0 / 28,114 | 0 | 0 | 6/6 |

(Medians of prompt/cached/hits shown; n = sessions × 3 repetitions; only 2 of 234 sessions reach 28k, as pre-registered.)
- **Reload bandwidth:** 2.89 GB (11k) / 7.37 GB (28k) loaded per HOST-WARM request = exactly 262,144 B per host-hit token (64 layers × 8 KV heads × 128 × K,V × bf16) on every row; vLLM's load-time metric gives **47.6 GB/s (11k) and 52.9 GB/s (28k)** — 75–83% of PCIe Gen5 ×16's ~63 GB/s. Visible cost vs GPU-WARM on the same server: **+0.031 s (11k), +0.117 s (28k)**; the TTFT-implied rate (93.7 / 62.8 GB/s) exceeds the link, i.e. part of the load overlaps other request work — the metric rate is the transfer rate, the TTFT delta is what a user sees.
- **COLD** = full re-prefill at 4.5k (11k) / 3.8k (28k) tok/s: host reload is **5.3× (11k) / 7.4× (28k) faster than recompute** in TTFT, and ≈66× / 55× cheaper in added latency vs GPU-WARM (0.03–0.12 s vs 2.06–6.49 s).
- **How each state was verified** (pre-registered, from /metrics deltas with one request in flight, 1.5-s settle): GPU-WARM: GPU-local prefix hits ≥ 0.9× history and host hits ≤ 64; HOST-WARM: GPU-local hits ≤ 64 (GPU copy gone after ≥ 1.5× KV of filler histories), host (`external_prefix_cache_hits`) ≥ 0.9× history, `kv_offload_load_bytes` > 0; COLD: cached ≤ 64. 72/72 rows verified (36 per server).
- Offload overhead when the history is still on GPU: +0.033 s at 11k, none at 28k (GPU-WARM on the two servers); none visible in the fleet at D = 4 (0.54 vs 0.53 s).

## Part B — fleet (RH2 harness, plans, seeds; D2 history; P-WARM; rate 1.0; 15-min window)

| cell | D2 warm footprint | n esc | token hit | TTFT median | p90 | p99 | max | append hit | in flight at end | drain | waiting max | preempt | errors (ctx) | host share of hits | PCIe load / store (GB) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| GPU-only D4 | 0.66× | 38 | 0.96 | 0.53 | 0.83 | 1.37 | 1.40 | 0.95 | 1 | 1 s | 0 | 0 | 0 | — | — |
| GPU+host D4 | 0.66× | 38 | 0.96 | 0.54 | 0.82 | 0.98 | 1.01 | 0.96 | 1 | 1 s | 0 | 0 | 0 | 0.4% | 3 / 44 |
| GPU-only D8 | 1.19× | 76 | 0.72 | **95.6** | 201 | 238 | 240 | 0.35 | 118 | 98 s | 202 | 0 | 0 | — | — |
| GPU+host D8 | 1.19× | 76 | 0.97 | **0.52** | 0.86 | 1.15 | 1.33 | 0.95 | 1 | 1 s | 2 | 0 | 0 | 59% | 1,087 / 89 |
| GPU-only D16 | 2.48× | 147 | 0.38 | **802** | 1,514 | 1,904 | 1,923 | 0.04 | 1,019 | 1,938 s | 1,007 | 0 | 0 | — | — |
| GPU+host D16 | 2.48× | 147 | 0.97 | **0.60** | 1.09 | 1.78 | 2.13 | 0.95 | 4 | 2 s | 2 | 0 | 0 | 92% | 3,509 / 177 |
| GPU-only D24 | 3.96× | 215 | 0.24 | **1,520** | 2,654 | 3,144 | 3,169 | 0.09 | 1,780 | 3,095 s | 1,019 | 0 | 47 (46) | — | — |
| GPU+host D24 | 3.96× | 215 | 0.97 | **0.81** | 1.37 | 2.00 | 2.32 | 0.95 | 4 | 1 s | 6 | 0 | 46 (46) | 95% | 5,297 / 260 |

TTFT in seconds, warm escalations submitted in the window (all devices warm). Footprint = D × mean D2 history per append / 62,944 (pre-registered fluid-model value). Host share = external ÷ (external + GPU-local) prefix-hit tokens over window + drain. PCIe = `kv_offload_load/store_bytes` deltas. Errors: 46 over-context HTTP 400s at D = 24 in both configs (the one session past D2's ~708-s limit; 45 predicted) + 1 client ReadError (GPU-only).
- **GPU-only knee is at D = 8 (1.19×)** — earlier and far more severe than RH2's A-format knee (1.15× at D = 16, median 7.9 s): each D2 miss recomputes a ~9–10k-token history (vs ~4.7k), so misses saturate the GPU faster. The footprint rule still places the knee correctly (just above 1× KV); the severity scales with the recompute cost of the format.
- **GPU+host keeps appends warm:** append hit 0.95 at every D; GPU+host computes only new frames + question tails (191 → 1,123 tok/s in-window) while GPU-only's in-window demand reaches 22,170 tok/s.
- **Host memory:** server tree RSS ≈ 262–267 GiB with offload (the 256-GiB pinned region + ~8 GiB), vs 5.5–74 GiB without (the GPU-only server's RSS grows with its request backlog). The store volume needed in a cell (≤ 260 GB written at D = 24, including LRU turnover) and the analytic resident footprint (≈ 249k tokens ≈ 61 GiB at D = 24) are well below the 256-GiB buffer; the connector's `kv_offload_cpu_cache_usage_perc` gauge read ≤ 0.026, but its scale was not verified, so it is not used.

## Mechanism verification (Steps 1–5)

**Step 1 — causal chain.** RH2's knee: when the warm-set footprint exceeds GPU KV, prefix blocks are evicted, appends and escalations miss, every miss recomputes the whole history, the GPU becomes compute-bound and queues grow (FORMULATION.md: physical inertia = reconstruction cost growing with context; warm-state capacity). A second KV tier changes the cost of a miss from recompute (prefill at ~4 k tok/s) to reload (PCIe at ~50 GB/s ≈ 190k tok/s): if evicted blocks are kept in host memory and reloaded on a prefix hit, misses no longer generate compute, so the knee should move out to wherever host capacity, PCIe, or the GPU's running-set KV binds.

**Step 2 — instantiate each link.**

| causal link | implementing quantity | value / range | varies as expected? | evidence |
|---|---|---|---|---|
| footprint > KV → eviction | warm footprint ÷ KV; GPU-only append hit | 0.66× → 3.96×; 0.95 → 0.35 → 0.04 → 0.09 | yes | Part B GPU-only |
| eviction → recompute | GPU-only in-window computed demand | 206 → 4,991 → 15,634 → 22,170 tok/s | yes | Part B |
| recompute → queueing / latency | waiting max, TTFT median | 0 → 202 → 1,007 → 1,019; 0.53 → 96 → 802 → 1,520 s | yes | Part B |
| host tier → miss served by reload | host share of hits; PCIe load bytes | 0.4% → 59% → 92% → 95%; 3 → 5,297 GB | yes (grows with D) | Part B GPU+host, Part A verification |
| reload ≪ recompute | Part A TTFT HOST-WARM vs COLD | 0.46 vs 2.45 s (11k); 1.00 vs 7.37 s (28k) | yes | Part A |

No link is ABSENT or CONSTANT.

**Step 3 — trace one unit.** Part A, 28k, session 184833716600, rep 1, GPU+host server: append (history to 618 s, 310 frames, 28,216 prompt tokens) → GPU-WARM escalation (cached 27,936 GPU-local, TTFT 0.84–0.96 s) → filler histories ≥ 94k tokens (1.5× KV) evict the GPU copy → HOST-WARM escalation: prompt 28,216, cached 28,208 = 0 GPU-local + 28,208 external; load 7.39 GB (= 28,208 × 262,144 B), TTFT 1.006 s; only the ~8-token tail computed. Bound: neither KV nor compute (single request).

**Step 4 — negative control.** The GPU-only configuration *is* the mechanism disabled (no host tier) on the same harness, plans and seeds: it collapses from D = 8 (median 96 s → 1,520 s at D = 24) while GPU+host stays ≤ 0.81 s. At D = 4 (footprint 0.66×, no eviction) the two configs coincide (0.53 vs 0.54 s; host share 0.4%), as the mechanism predicts when nothing is evicted.

**Step 5 — alternative explanation.** "GPU+host is faster because the offload server schedules differently / batches better, not because of reload." Distinguished by (i) the host-hit counter: 92–95% of hit tokens at D = 16/24 came from host and PCIe load bytes match host-hit tokens × 256 KiB exactly in Part A; (ii) GPU-only and GPU+host coincide at D = 4 where no reload happens; (iii) GPU+host computed tokens stay at new-frames scale (1.1k tok/s) — the work removed is exactly the recompute. A second alternative — host RSS growth or PCIe contention limiting — is not observed within D ≤ 24 (PCIe ≈ 6 GB/s average, ~11% of the measured rate).

## Results consistency check

1. **Cross-check vs committed measurements**

| quantity | this run | prior | source | ratio | agree? |
|---|---|---|---|---|---|
| GPU KV capacity (image server) | 62,944 | 62,944 | RH3/RH4 image server | 1.00 | agree |
| cold prefill rate | 4.5k (11k) / 3.8k (28k) tok/s | 0.341 s + 0.244 ms/tok → 4.1k tok/s | RH2 calibration | 1.1 / 0.93 | agree |
| GPU-WARM escalation TTFT (warm, low load) | 0.38 s (11k), 0.53 s fleet D4 | 0.35–0.40 s | RH2 warm ≤ 0.55× | ~1 | agree |
| knee location (footprint) | 1.19× (D2) | 1.15× (A format) | RH2 | 1.03 | agree (location); severity differs — explained (2× recompute per miss) |
| D=24 over-context errors | 46 | 45 predicted | RH5 pre-registration | 1.02 | agree |
| KV bytes per token | 262,144 (measured load bytes ÷ host-hit tokens) | 262,144 (architecture) | model config | 1.00 | agree |

2. **Physical plausibility.** Reload 47.6–52.9 GB/s ≤ PCIe Gen5 ×16 peak (~63 GB/s): plausible. TTFT-implied 63–94 GB/s exceeds the link → part of the load is overlapped, not a faster link; reported as such. GPU-only collapse throughput: 19.95M in-window computed tokens over 900 + 3,095 s = **5.0k tok/s achieved** at D = 24 — consistent with isolated cold prefill (3.8–4.5k) plus batching, not faster. No rate exceeds committed curves by 2×.
3. **Distribution sanity.** Part A TTFT spreads 0.33–0.54 s (11k), 0.78–1.01 s (28k), COLD 2.39–2.54 / 7.31–7.42 s (tight because isolated, varying by session length); fleet TTFTs reported with p90/p99/max; no constant where a distribution is expected. Load bytes per token is exactly constant (262,144) — expected (architecture constant), not a short-circuit.
4. **Definition audit.** "Warm footprint" = D × mean D2 history per in-window append ÷ GPU KV (RH2 used the A-format equivalent; same definition, different format). "Hit" = token-weighted cached/prompt over escalations (RH2). "Host share" is new (external ÷ (external + local) prefix-hit tokens). "Computed prompt tok/s" (RH2's metric) is **in-window demand**, not achieved throughput — see Deviations.
5. **Claim linkage.** **C4** (physical inertia grows with context; warm-append vs cold re-prefill): supported and extended — the reload tier makes a warm-history miss cost +0.03–0.12 s instead of +2–6.5 s. **C5** (joint representation × placement × timing): the warm-capacity constraint that forced a representation trade-off (RH3/RH4: only 3–4 D2 sessions warm) is lifted to ≥ 24 sessions on one H100 with 256 GiB host RAM, so representation choice is no longer forced by KV scarcity in this range — the binding resources become GPU running-set KV and session length (RH4's ~12-min limit). FORMULATION §Scoping: host offload is same-GPU, same-model KV movement — not cross-tier KV transfer — so it is in scope.
6. **Proxy validity.** `external_prefix_cache_hits` as "served from host": validated in Part A (load bytes = host-hit tokens × KV bytes/token exactly; local hits 0). `kv_offload_cpu_cache_usage_perc`: scale unverified → not used. Warm footprint is the pre-registered fluid-model value (not a measured residency).

## H100 monitoring (this run)

`results/cost/h100_monitoring_summary.json` regenerated with StudyRH5 added: 4 step windows, 1,403 GPU-3 samples, 0 foreign processes, SM clock busy min / median / max 547 / 915 / 1,785 MHz (same power-limited operating point as R1–RH4), 11 log files hashed.

## Deviations and notes

- **Runtime estimate error (no STOP fired):** the pre-registered fluid model used 11k tok/s as achieved throughput, taken from RH2's "computed prompt tok/s" — which is in-window *demand*. Achieved collapse throughput was ~5k tok/s, so GPU-only drains ran 32 min (D16) and 52 min (D24) vs 6 / 19 min estimated. Total 4.05 h vs 3.64 h, inside the 6-h cap.
- **Part A 28k used 2 sessions** (only 2 of 234 reach ~28k), 3 repetitions each, as pre-registered.
- **Header** follows RH4's D2 wording with RH2's per-cell/device/session fields, so no two devices share a frame prefix.
- **LMCache** was not used: installing it would replace torch 2.13.0 with 2.14.1 (Step 0).

## Files

`experiments/cost/study_rh5_host_offload.py` (Part A, fleet, estimate), `experiments/cost/study_rh5_analyse.py`, `experiments/cost/h100_monitoring_summary.py` (RH5 added); `results/cost/study_rh5/`: `study_rh5_partA_h100nvl.jsonl.gz`, `study_rh5_requests_h100nvl.jsonl.gz`, `study_rh5_metrics_h100nvl.jsonl.gz`, `study_rh5_run_meta_h100nvl.json` (server flags, offload log lines, verification, estimate), `study_rh5_results_h100nvl.json`; `results/cost/h100_monitoring_summary.json`.
