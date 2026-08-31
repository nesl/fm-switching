# Study E — Device-side inference & state-construction cost on Jetson AGX Orin

**Date:** 2026-08-31 · **Device:** Jetson AGX Orin (nesl-orin-3, 64 GB) · **Purpose:** device-side half of the cost model.
Measurement only — no accuracy claims, no new hypotheses.

Raw data: `results/vision/study_e/study_e_part1_trials.csv` (Part 1, 360 trials),
`study_e_part2_trials.csv` / `study_e_part2_results.json` (Part 2),
`study_e_thermal.csv` (Part 3, 10,345 samples).
Scripts: `experiments/vision/study_e_orin_cost.py` (Part 1),
`study_e_state_cost.py` (Part 2), `thermal_sampler.py` (Part 3).

---

## 1. Device configuration (as reported at the start)

| item | value |
|---|---|
| Unit | **64 GB** Jetson AGX Orin (MemTotal 64,336,092 kB ≈ 61 GiB; Swap 30 GiB) |
| Power mode (as found) | **MODE_15W** (nvpmodel index 1) — only 4 of 12 CPUs online |
| Power mode (set for this study) | **MAXN (mode 0)**, set explicitly via `sudo nvpmodel -m 0` (required a reboot; SSH persistence verified beforehand) |
| Clocks | `jetson_clocks` applied: **12 CPUs online @ 2.2016 GHz**, **GPU pinned @ 1.3005 GHz** (8 TPCs), EMC @ 3.199 GHz, DLA0/1 @ 1.6 GHz. Re-applied after reboot (does not persist). |
| JetPack / L4T | JetPack 6.2.2 / L4T R36.5.0 |
| CUDA / torch / transformers | CUDA 12.6 / torch **2.8.0** / transformers **5.10.2** (accelerate 1.13.0, Python 3.10.12) |
| flash-attn | **NOT available** (no aarch64 wheel) → **SDPA attention** |
| Disk | 57 GB eMMC, no external SSD. Started at 4 GB free; freed 24 GB of text-model cache; VL models managed sequentially (one/two on disk at a time). |

**Software-stack caveat (load-bearing for every cross-tier comparison below).** The A6000
reference studies (D2, B) ran **torch 2.4.1+cu118 / transformers 5.12.1 with flash-attn**.
This Orin ran **torch 2.8.0 / transformers 5.10.2 with SDPA and no flash-attn**. Orin-vs-A6000
gaps therefore conflate the hardware difference with a software-stack component (attention
kernel + library versions). This is not a pure device comparison — but it *is* the realistic
device stack, and one consequence (the O(L²) SDPA memory ceiling, §4) is the study's headline.

**Models.** Part 1: Qwen3-VL-{4B,8B}-{Instruct,Thinking}, bfloat16, pinned to the Study D2
snapshots. Part 2: Qwen2.5-VL-7B-Instruct, bfloat16, pinned to the Study B snapshot. All
downloaded to the Orin (4B pair 2×8.3 GB, 8B pair 2×~16 GB, Qwen2.5-VL-7B ~16 GB). Disk was a
binding constraint — models cycled through the eMMC one/two at a time. No model failed to load.

---

## 2. Raw measurements

### Part 1 — inference cost (L2, L3; 15 images/level; 3 reps; greedy; Instruct max_new=40, Thinking max_new=8192)

Per-model: load time, idle memory after load, noise-floor CV (5 back-to-back reps of one fixed trial).

| model | load s | idle mem | n_input | noise-floor CV |
|---|---|---|---|---|
| Qwen3-VL-4B-Instruct | 6.1 | 8.88 GB | 348 | 0.28% |
| Qwen3-VL-4B-Thinking | 5.4 | 8.88 GB | 350 | 0.07% |
| Qwen3-VL-8B-Instruct | 8.3 | 17.53 GB | 348 | 0.30% |
| Qwen3-VL-8B-Thinking | 8.3 | 17.53 GB | 350 | 0.03% |

Per-cell medians (n=45 per cell):

| model | level | TTFT ms | latency ms | decode tok/s | n_gen | think tok | peak mem GB | budget-hit |
|---|---|---|---|---|---|---|---|---|
| 4B-Instruct | L2 | 281 | 390 | — (n_gen=2) | 2 | 0 | 8.99 | 0% |
| 4B-Instruct | L3 | 281 | 390 | — | 2 | 0 | 8.99 | 0% |
| 4B-Thinking | L2 | 280 | 8,266 | 9.4 | 76 | 72 | 8.99 | 7% |
| 4B-Thinking | L3 | 280 | 53,547 | 9.4 | 500 | 496 | 9.03 | 13% |
| 8B-Instruct | L2 | 434 | 544 | — | 2 | 0 | 17.66 | 0% |
| 8B-Instruct | L3 | 434 | 544 | — | 2 | 0 | 17.66 | 0% |
| 8B-Thinking | L2 | 434 | 9,430 | 9.4 | 86 | 82 | 17.66 | 0% |
| 8B-Thinking | L3 | 434 | 43,415 | 9.4 | 408 | 404 | 17.67 | 13% |

Structure of the device cost:
- **Decode rate is ~9.2–9.5 tok/s for every model, 4B and 8B alike.** On-device decode is not
  parameter-bound here — it is overhead / memory-bandwidth bound (SDPA, no flash-attn). The
  8B's extra cost appears in **prefill/TTFT (434 vs 280 ms, ~1.55×)** and **memory (17.7 vs 9.0 GB)**,
  not in decode rate.
- **Thinking latency is dominated by generated length.** L3 generates far more reasoning
  (4B: 500 think tok → 53.5 s; 8B: 408 think tok → 43.4 s). At L3 the 8B is *faster* than the 4B
  because it reasons more concisely (fewer think tokens) at the same decode rate.
- **Budget-hits** (8192-token cap) at L3 ≈ 13% for both Thinking models; a budget-hit trial takes
  ~8192/9.4 ≈ 14.5 min.

### Part 2 — state-construction cost (Qwen2.5-VL-7B; synthetic frames; full / window k=3 / regenerated summary; 560×560 → 400 vision tok/frame)

Median over reps (rep 0). Peak memory is the binding quantity.

| N | condition | state-construct ms | query TTFT ms | KV MB | peak GB | input tok |
|---|---|---|---|---|---|---|
| 1 | full | 807 | 807 | 24.9 | 22.96 | 435 |
| 1 | window | 839 | 839 | 24.9 | 22.96 | 435 |
| 1 | summary | 2,998 | 124 | 4.1 | 17.08 | 72 |
| 3 | full | 3,530 | 3,530 | 71.0 | 35.30 | 1,239 |
| 3 | window | 3,528 | 3,528 | 71.0 | 35.30 | 1,239 |
| 3 | summary | 7,558 | 141 | 6.6 | 17.38 | 115 |
| 6 | full | 7,743 | 7,743 | 140.2 | **53.39** | 2,445 |
| 6 | window | 3,277 | 3,277 | 71.0 | 35.30 | 1,239 |
| 6 | summary | 14,002 | 200 | 10.0 | 17.78 | 175 |
| 12 | **full** | **OOM** | — | — | — | 4,835 |
| 12 | window | 3,648 | 3,648 | 71.0 | 35.30 | 1,239 |
| 12 | summary | 27,370 | 352 | 17.4 | 18.63 | 304 |

**Empirical ceiling: full retention is feasible to N=6 (peak 53.4 GB) and OOMs at N=12** —
`NvMapMemAllocInternalTagged error 12` (ENOMEM) / CUDACachingAllocator NVML assert. Window
(constant k=3 frames) and summary (text-only query) remain feasible at N=12; the sweep halted
at the full-retention ceiling per the stop rule, so higher N was not attempted for those two.
Ordering (as in Study B): window (constant ~3.3 s) < full (growing) < summary (most expensive to construct).

### Part 3 — thermal & sustained load

| quantity | value |
|---|---|
| Sampling | sysfs (thermal zones + GPU devfreq), every 5 s, **10,345 samples over 14.5 h continuous** |
| tj (junction) temp | min 47.1 °C, **max 65.1 °C** |
| GPU clock | **constant 1,300,500,000 Hz throughout** |
| Throttle samples (freq < locked max) | **0** |
| Throughput drift (4B-Thinking) | first-10 trials 9.17 tok/s vs last-10 9.40 tok/s — **no degradation** |

Over 14.5 h of sustained VL inference at MAXN, the Orin **never throttled** (max 65 °C, far below
the ~95–105 °C throttle threshold) and throughput was flat early-to-late.

---

## 3. Sanity checks (all pass) + results-consistency check

| check | result |
|---|---|
| Model on GPU at intended precision (verified, not assumed) | **PASS** — first param `cuda:0`, `torch.bfloat16`, asserted for every model |
| No CPU offload / no silent fallback | **PASS** — 0 params off `cuda` for every model |
| Vision token count matches A6000 for the **same model** | **PASS** — Qwen3-VL n_input = 348 (Instruct) / 350 (Thinking) = Study D2 exactly (raw vision tokens 324; the 400 figure is Qwen2.5-VL's, a different model). Qwen2.5-VL vision tokens = **400** = Study A/B exactly. |
| Measured KV vs analytical (within 10%) | **PASS** — ratio = 1.000 at all N (Part 2), analytical 57,344 B/tok reproduced |
| Repeat-control noise floor | **PASS** — CV 0.03–0.30% across models; far below the effects measured |
| n_input constant within mode | **PASS** — constant across all images per model |

**Consistency check vs committed measurements.** (1) *Cross-check*: Qwen2.5-VL KV/token 57,344 B
matches Study B; vision tokens 400 (Qwen2.5-VL) / 324 (Qwen3-VL) match A5/D2; n_input 348/350
matches D2. (2) *Physical plausibility*: every Orin number is **slower** than the corresponding
A6000 number (no result faster than the committed curves) — Orin decode 9.4 tok/s vs A6000 ~30–50 tok/s;
Orin N=6 full-prefill 316 tok/s vs A6000 ~3,560 tok/s. (3) *Distribution sanity*: noise-floor CV
< 0.3%, and Thinking latency varies with n_gen as expected (not constant). (4) *Definition audit*:
"full / window k=3 / summary", 560×560→400 vision tok, N sweep {1,3,6,12,24,36,48} identical to
Study B; L2=(2–3), L3=(4–7) persons identical to Study D2. (5) *Claim linkage*: measurement study,
device-side cost inputs; no causal claim (Mechanism-verification protocol N/A). (6) *Proxy validity*:
no proxies — direct TTFT / forward-pass / peak-mem / sysfs-temp measurements.

---

## 4. Orin vs A6000 comparison

### Part 1 — inference (A6000 from `reports/study_d2_thinking.md` / `results/vision/study_d2/`)

| model | level | Orin lat | A6000 lat | ratio | Orin decode t/s | A6000 decode t/s* |
|---|---|---|---|---|---|---|
| 4B-Instruct | L2/L3 | 390 ms | 94 ms | **4.15×** | — | — |
| 8B-Instruct | L2/L3 | 544 ms | 139 ms | **3.91×** | — | — |
| 4B-Thinking | L2 | 8,266 ms | 1,677 ms | 4.93× | 9.4 | ~49 |
| 4B-Thinking | L3 | 53,547 ms | 8,693 ms | 6.16× | 9.4 | ~49 |
| 8B-Thinking | L2 | 9,430 ms | 2,643 ms | 3.57× | 9.4 | ~32 |
| 8B-Thinking | L3 | 43,415 ms | 14,501 ms | 2.99× | 9.4 | ~32 |

\* A6000 decode is *derived* (n_gen / latency; Study D2 did not split TTFT from decode). **The
Thinking latency ratios are confounded** by n_gen differing across hardware — greedy decode is not
bit-identical across the SDPA-Orin and flash-attn-A6000 kernels (e.g. 4B-T L3 n_gen 500 vs 424;
8B-T L3 408 vs 468), so total latency mixes device speed with output length. The **per-token decode
comparison is the clean one: Orin ~9.4 tok/s vs A6000 ~30–50 tok/s → the Orin decodes ~3–5× slower.**
Instruct (n_gen=2 both, deterministic) gives a clean prefill-dominated ratio of ~4×.

### Part 2 — state construction (A6000 from `reports/study_b_vision_kv.md`)

| N | condition | Orin state-ms | A6000 state-ms | ratio |
|---|---|---|---|---|
| 1 | full | 807 | 207 | 3.9× |
| 3 | full | 3,530 | 348 | 10.1× |
| 6 | full | 7,743 | 687 | **11.3×** |
| 6 | window | 3,277 | 440 | 7.4× |
| 6 | summary | 14,002 | 3,756 | 3.7× |

The full-retention ratio **widens with N** (3.9× → 11.3×): without flash-attn the Orin's O(L²)
SDPA attention gets relatively worse as context grows. **Ceiling:** full retention Orin **N=6**
vs A6000 **N≥48** (Study B never hit a ceiling). Peak memory at the ceiling: Orin 53.4 GB @ N=6
vs A6000 24.4 GB @ N=48 — the Orin uses *more* memory for *fewer* frames, entirely the attention-kernel
difference, and OOMs despite 65.9 GB unified (vs the A6000's 48 GB).

---

## Explicit answers to the study's questions

1. **Thinking vs Instruct device-side latency, and vs the A6000.** On the Orin, Thinking costs
   ~21× (4B, L2) to ~137× (4B, L3) the Instruct latency, because Thinking generates 76–500 tokens at
   9.4 tok/s while Instruct emits ~2. The device is ~4× slower than the A6000 on Instruct (prefill-dominated)
   and ~3–6× slower on Thinking total latency; on a clean per-token basis the Orin decodes ~3–5× slower
   (~9.4 vs ~30–50 tok/s). The Thinking/Instruct *ratio* is larger on the Orin than the A6000 because
   the device penalty falls hardest on decode, which Thinking is dominated by.

2. **Largest N per representation vs A6000.** Full retention: **Orin N=6** (peak 53.4 GB; OOM at N=12)
   vs **A6000 N≥48** (24.4 GB, ceiling never hit). Window (k=3) and summary: feasible to at least N=12
   on both (constant/near-constant footprint). The device ceiling is ~8× lower for full retention —
   caused by O(L²) SDPA attention memory (no flash-attn), not by total memory (the Orin has more).

3. **Does sustained load throttle the device?** **No.** Over 14.5 h continuous load at MAXN, GPU clock
   stayed pinned at 1.3005 GHz (0/10,345 throttle samples), max tj 65 °C, and 4B-Thinking throughput
   was flat (9.17 → 9.40 tok/s early-to-late). Timings are stable; the noise floor (CV < 0.3%) is far
   below the measured effects.

---

## 5. What cannot be inferred

- **Pure hardware ratios.** Every Orin-vs-A6000 gap includes the software-stack component
  (SDPA-no-flash-attn / torch 2.8 / transformers 5.10.2 vs flash-attn / torch 2.4.1 / 5.12.1).
  The O(L²) memory ceiling in particular is a stack effect, not silicon.
- **A6000 TTFT / decode split.** Study D2 logged only total latency, so the A6000 decode rate is
  derived (n_gen/latency), not measured; the per-token ratio is approximate.
- **Thinking total-latency ratios** conflate device speed with output length (greedy decode diverges
  across kernels → different n_gen). Only the Instruct ratio and the Orin decode rate are clean.
- **Accuracy / quality.** This study measured cost only; correctness was recorded but no accuracy claim is made.
- **Window/summary ceilings on the Orin.** The sweep halted at the full-retention OOM (N=12), so the
  window and summary ceilings are lower bounds (feasible ≥ N=12), not measured maxima.
- **32 GB Orin behavior.** This is a 64 GB unit; a 32 GB unit would hit the full-retention ceiling at
  smaller N still.
