# StudyD4-orin — N=3 device cost + cost of a cheap motion signal (Jetson AGX Orin)

**Date:** 2026-11-04 · **Host:** nesl-orin-3 (Jetson AGX Orin, 64 GB) · **Runtime:** llama.cpp `c0fd786` (CUDA sm_87) · **Model:** Qwen3VL-4B-Instruct-F16 (+mmproj-F16), sha256 verified · **E-id:** StudyD4-orin

**Goal.** Fill the missing **N=3** on-device cost, and measure the cost of a **cheap motion signal** (optical flow) relative to a model inference. Jetson only; MAXN mode 0, GPU pinned 1.3005 GHz (verified + logged per request, 0 bad rows). `cache_prompt=false` (cold), greedy, max 512, seed 0.

**Inputs.** DEV-RECENT frames from `identical_input_manifest.json`, per-PNG sha256 re-verified (**1560/1560 match**). **N=3 = each question's N=9 frames at positions 1/5/9, in time order.** These are **not Nexar frames and not the bytes the H100 used**; their per-frame token count (~332) closely matches Nexar SMALL (~336). Measured N=3 input ≈ **1133 tokens** (median).

---

## Part A — isolated latency (observations)

One request at a time (~1 s idle gap), first-after-load discarded. Energy = per-request trapezoidal integral of total board power (3 INA3221 rails).

| N | input tok (p50) | TTFT p50 / p90 / p99 (s) | total p50 / p99 (s) | energy/req p50 (gpu / cpu / sys, J) | calib vs StudyD8 |
|---|---|---|---|---|---|
| 1 | 443 | 0.500 / 0.518 / 0.527 | 0.555 / 0.581 | 12.8 (8.6 / 1.1 / 3.2) | **0.975×** (0.513 s) |
| **3** | **1133** | **1.339 / 1.365 / 1.393** | **1.394 / 1.448** | **43.6 (30.9 / 2.8 / 9.9)** | — (new point) |
| 9 | 3099 | 3.869 / 3.943 / 3.967 | 3.926 / 4.023 | 149.1 (108.5 / 8.3 / 32.0) | **1.007×** (3.843 s) |

Calibration N=1/N=9 reproduce StudyD8 within ±2.5%, so N=3 sits on the same curve. `cached_n=0` and clock pinned on every row. Accuracy (indicative, tiny-n): N=1 10%, N=3 22%, N=9 5% (n=20/50/20 — not meaningful at these samples; see Part B for the 120-question N=3 figure).

## Part B — sustained N=3 (observations)

**Cadence decision:** N=3 total-latency p99 = **1.448 s ≤ 2 s → cadence stays 2 s** (no bump). Scheduled every 2 s for 30 min, StudyD8 skip-not-queue. 10-min loaded-idle baseline first.

| metric | value |
|---|---|
| Baseline (loaded, idle, 10 min) | **9.66 W** |
| Requests / **missed** | **900 / 0** |
| TTFT p50 / p90 / p99 | 1.339 / 1.378 / 1.400 s |
| total latency p50 / p99 / max | 1.394 / 1.455 / 1.530 s |
| staleness p50 / p90 / max | 0.010 / 0.013 / 0.018 s |
| drift (first10 → last10 TTFT p50) | 1.339 → 1.341 s (**none**) |
| energy / req p50 | 46.5 J |
| mean board power | 33.4 W |
| energy / hour total · **above baseline** | 120.2 kJ · **85.4 kJ** |
| tj_max | 61.3 °C (no throttle) |
| greedy match / cached_n / clock bad | **1.000** / 0 / 0 |
| accuracy (indicative, 120 q) | 24% |

## Part C — motion-feature cost (observations)

Committed `experiments/dashcam/d2_flow.py` (dense Farneback + 17 features), **UNMODIFIED**, CPU-only, server stopped, nothing else running. 50 windows of 9 manifest frames. System cv2 4.8.0.

> **Resolution deviation (flagged):** the committed feature code's working resolution is **384×216**, not the 768×432 in the instructions. Honoring "do not change the features," the measurement is at the code's native 384×216; the task figure is not applied.

| metric | value |
|---|---|
| time / window (9 frames, 8 pairs) p50 / p90 / p99 | **0.261 / 0.269 / 0.272 s** |
| time / window min / max | 0.231 / 0.273 s |
| new-frame update — single Farneback pair p50 | **0.022 s** |
| new-frame update — window/8 (amortized) | 0.033 s |
| CPU-rail power during run | **3.14 W** (board 11.75 W vs 9.66 W idle) |
| incremental API in committed code? | **no** (single-pair + amortized reported as the marginal cost) |

---

## Reading (interpretation)

- **N=3 fills the device cost curve and is prefill-bound like its neighbours.** TTFT scales with prompt tokens — 443 / 1133 / 3099 tok → 0.50 / 1.34 / 3.87 s — at a gently rising per-token cost (1.13 → 1.18 → 1.25 ms/tok, the attention-quadratic term), exactly the shape StudyDevOne/StudyDevFast found. N=3 costs **~1.4 s / ~44 J**, about one-third of N=9 (3.9 s / 149 J) and ~3.4× an N=1 (0.5 s / 13 J). As a standing query at 2 s cadence it holds **900/900 ticks with zero misses, no drift, no throttle** — same "no sustained penalty" result as StudyD8 (sustained 46.5 J/req vs isolated 43.6 J, the small rise being the warmer saturated floor).
- **A cheap motion signal is far cheaper than a model inference.** One optical-flow feature window (9 frames) costs **0.26 s on CPU at ~3.1 W** — about **5× faster** and, at ~2 W above idle for 0.26 s (≈0.5 J) vs 43.6 J for an N=3 inference, roughly **~80× lower energy** than invoking the model once. The marginal cost of one new frame arriving is a single Farneback pair, **~0.022 s**. This is the quantitative basis for a motion gate: run the cheap flow feature continuously on CPU and only wake the GPU model when motion warrants, at a tiny fraction of the always-on inference cost.
- **The two run on different compute.** Optical flow is CPU-rail (3.1 W CPU, GPU idle); the model is GPU-rail (N=3 active ~33 W board, ~30.9 J of the 43.6 J on the GPU rail). A device can run the motion gate without touching the GPU, so the two costs add rather than compete.

---

## Results consistency check (6 checks)

**1. Cross-check against committed — PASS** (all ≤ 1.25×, within the 2× gate):

| quantity | this run | prior | source | ratio | agree |
|---|---|---|---|---|---|
| N=1 TTFT p50 | 0.500 s | 0.513 s | StudyD8 | 0.975 | ✓ |
| N=9 TTFT p50 | 3.869 s | 3.843 s | StudyD8 | 1.007 | ✓ |
| N=9 energy/req | 149 J | 150–159 J | StudyD8 B/C | 0.95–0.99 | ✓ |
| N=1 energy/req | 12.8 J | 16 J (StudyD8 A) | StudyD8 | 0.80 | ✓ (explained) |
| loaded-idle | 9.66 W | 9.61 W / 9.94 W | StudyD8 / DevOne | 1.00 | ✓ |
| N=3 TTFT / energy | 1.34 s / 43.6 J | — | new | — | fills gap monotonically |

N=3 is new and sits monotonically between N=1 and N=9 in tokens (443 < 1133 < 3099), TTFT (0.50 < 1.34 < 3.87 s) and energy (13 < 44 < 149 J). The N=1 energy sub-unity ratio (12.8 vs 16 J) is the same duty-cycle effect documented in StudyD8: Part A's ~1 s inter-request gap lets the GPU cool toward idle, so each isolated request's clamped integration window starts from a lower floor than a back-to-back sweep.

**2. Physical plausibility — PASS.** Prefill rates (TTFT-implied): N=1 886, N=3 845, N=9 801 tok/s — all within the committed ~800–1050 tok/s band, declining gently with length (quadratic), no rate > 2× any curve; `cached_n=0` rules out caching. Optical flow 8 dense-Farneback pairs / 0.26 s ≈ 33 ms/pair at 384×216 on the Orin CPU (single-pair 22 ms + feature/resize overhead) — physically reasonable; no committed prior to contradict.

**3. Distribution sanity — PASS.** p50/p90/p99 reported for every latency/energy figure; all non-degenerate (N=3 TTFT 1.339–1.393, tight as expected for a fixed 3-frame prefill; Part C 0.231–0.273 s/window). Part B greedy-match 1.000 is the intended determinism check (greedy + identical input), not a frozen constant — the underlying TTFTs still vary.

**4. Definition audit — PASS.** N=3 = N=9 positions 1/5/9, time order (documented). `cache_prompt=false` ⇒ cold (cached_n=0 every row). Energy = sum of 3 INA3221 rails (no VDD_IN). skip-not-queue; staleness = wall_start − scheduled. Part C: `d2_flow.py` unmodified, `FR` redirected to the manifest frames, working resolution 384×216 (not 768×432 — flagged, features unchanged). Same definitions as StudyD8.

**5. Claim linkage — PASS.** N=3 extends the device Context-Inertia cost curve (physical component). Part C supplies the cost of a non-model motion gate — a cheap signal that could trigger or suppress model inference — bearing on the representation × placement × **timing** trade-off (when to invoke the FM locally). The ~80× energy / ~5× latency gap between the flow feature and an N=3 inference is the quantity a timing policy would exploit. No scoped-out quantity measured.

**6. Proxy validity — stated.** Accuracy is **indicative only** (A6000 is the reference); the N=3 figure (24%, 120 q) sits between StudyDevOne's N=1 (12.5%) and N=9 (28%), consistent but not a settled accuracy. Part C uses **DEV-RECENT frames as a stand-in for Nexar** (explicitly not Nexar bytes; ~332 vs ~336 tok/frame) — valid for the *cost* measurement because dense-Farneback cost is set by resolution (384×216) and parameters, not by frame provenance. The 768×432 → 384×216 resolution gap is flagged; the cost is reported at the code's native resolution.

**Mechanism verification:** N/A — runtime latency/energy + CPU feature-cost measurement, no causal claim (as StudyD8/StudyDevFast/StudyDevOne); Steps 1–5 do not apply.

**STOP / sanity gates:** none tripped — clock pinned (0 bad rows), inputs verified (1560/1560), cached_n=0 everywhere, greedy match 1.000, no throttle (tj ≤ 61.3 °C ≪ 95 °C).

---

## Files

- Harness: `experiments/device/study_d4_orin.py` (reuses `dev_fast_latency.py`, `study_dev_one.py`, `dev_inputs.py`; Part C reuses `experiments/dashcam/d2_flow.py` **unmodified**).
- Part A: `results/device/study_d4_orin/partA_isolated.jsonl` (90 req incl. energy), `partA_warmup.json` (excluded), `partA_tegrastats.jsonl.gz`.
- Part B: `results/device/study_d4_orin/partB_sustained.jsonl` (900 req), `partB_baseline_tegrastats.jsonl.gz`, `partB_sustained_tegrastats.jsonl.gz`.
- Part C: `results/device/study_d4_orin/partC_features.json` (50 windows, timing + 17 features), `partC_tegrastats.jsonl.gz`.
- Aggregate: `results/device/study_d4_orin/study_d4_summary.json`.
- Inputs: `results/device/identical_input_manifest.json`; model sha256 `results/device/model_hashes.txt`.
