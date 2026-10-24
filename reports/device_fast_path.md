# On-device fast path — shortened DEV-RECENT latency + energy (Jetson AGX Orin)

**Date:** 2026-10-23 · **Host:** nesl-orin-3 (Jetson AGX Orin, 64 GB) · **Runtime:** llama.cpp `c0fd786` (CUDA sm_87) · **E-id:** StudyDevFast

**Question.** Can the device answer a DEV-RECENT S-EMBER question within a few seconds when the recent-frame input is shortened, and what is the energy cost per configuration?

**Design (pre-registered, EXPERIMENTS.md StudyDevFast).** Same stack/harness/sample as StudyDeviceLatency-sember (F16 GGUFs, sha256 verified; server flags `--jinja --reasoning-format deepseek -ngl 99 -fa on -c 16384`; same 120-question RECENT sample; prompt-cache on; one request at a time). Sweep: DEV-RECENT **N ∈ {37 (control), 18, 9}** × models **{4B-Instruct (greedy, max 512), 4B-Thinking (model-card sampling, seed 0, max 16384)}** = 6 cells × 120 q = **720 requests**. Cells run strictly one at a time, nothing else on the Orin. **MAXN mode 0, GPU pinned 1.3005 GHz** (verified identical to the existing latency runs).

---

## Results — latency / energy / accuracy (per cell, median unless noted)

| cell | N (frames) | input tok | TTFT s | total latency s (med / p90 / max) | think tok (med) | decode tok/s | **energy J/req (med / p90)** | active power W | idle W | TTFT ≤ 5 s | latency ≤ 10 s | acc (indicative) | tj max |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **4B-Instruct N=37** | 37 | 12,420 | **16.98** | 17.0 / 17.4 / 18 | 0 | — | **749 / 754** | 43.8 | 10.03 | 0.8 % | 1.7 % | 34 % (41/120) | 66.7 |
| **4B-Instruct N=18** | 18 | 6,123 | **7.76** | 7.8 / 8.0 / 8 | 0 | — | **332 / 334** | 42.4 | 9.76 | 0.8 % | **100 %** | 31 % (37/120) | 65.6 |
| **4B-Instruct N=9** | 9 | 3,130 | **3.79** | 3.9 / 3.9 / 4 | 0 | — | **159 / 160** | 41.1 | 9.76 | **100 %** | **100 %** | 28 % (34/120) | 64.7 |
| **4B-Thinking N=37** | 37 | 12,422 | 17.15 | **38.2 / 93.1 / 212** | 342 | 16.2 | **1,634 / 3,939** | 42.7 | 9.75 | 0.8 % | 0 % | 33 % (40/120) | 66.3 |
| **4B-Thinking N=18** | 18 | 6,125 | 7.86 | **34.7 / 137.2 / 440** | 477 | 17.7 | **1,465 / 5,806** | 42.3 | 9.76 | 0.8 % | 0 % | 31 % (38/120) | 65.5 |
| **4B-Thinking N=9** | 9 | 3,132 | 3.88 | **32.1 / 133.7 / 419** | 524 | 18.6 | **1,363 / 5,690** | 42.4 | 9.85 | **100 %** | 7.5 % | 27 % (33/120) | 65.3 |

Accuracy Wilson-95 CIs (n=120, indicative — the reference accuracy is the A6000's, not this device): I37 [0.26,0.43], I18 [0.23,0.40], I9 [0.21,0.37], T37 [0.26,0.42], T18 [0.24,0.40], T9 [0.20,0.36]. Peak RAM 27–28.5 GB all cells. **budget_hit = 0 / 720** (no reasoning run hit the 16,384 cap; every long tail was a natural stop). Energy J/req is the trapezoidal integral of **total board power** over `[request_start, request_end]`, including the ~10 W loaded-idle floor.

---

## Answer to the question

**1. The few-seconds fast path exists for Instruct, and shortening the input is what buys it.** Instruct latency *is* TTFT (the answer is ~2 tokens), and TTFT is prefill-bound and ~linear in frame count: **17.0 s → 7.8 s → 3.9 s** as N goes 37 → 18 → 9. At **N=9 every one of the 120 Instruct queries finishes in ≤ 4 s** (100 % ≤ 5 s TTFT and ≤ 10 s total); at N=18, 100 % finish ≤ 10 s. So a device that shortens the recent window to ~9 frames answers in a few seconds.

**2. The fast path does NOT exist for Thinking at any N.** Thinking TTFT drops identically (17.2 → 7.9 → 3.9 s), but total latency is **reasoning-bound**, not input-bound: median stays **38 → 35 → 32 s** — barely moved — because the generated reasoning (342 → 477 → 524 median tokens) dwarfs the prefill saving. Only 7.5 % of N=9 Thinking queries finish in ≤ 10 s.

**3. Shortening the input makes the Thinking tail WORSE.** As N falls 37 → 18 → 9, the Thinking p90 latency rises **93 → 137 → 134 s**, the max rises **212 → 440 → 419 s**, median think-tokens rise **342 → 477 → 524**, and p90 energy rises **3,939 → 5,806 → 5,690 J**. With less visual evidence on screen, the model reasons *longer* to compensate. The same question (`3b03a5a9768b`) ran 4,314 think-tokens / 256 s at N=18 and 5,836 / 328 s at N=9. Trimming frames trades a few seconds of prefill for a much heavier reasoning tail — a net loss for Thinking.

**4. Energy per request.** Instruct energy is ~linear in frames: **749 → 332 → 159 J** (median), tracking prefill work; active board power is ~41–44 W against a ~9.8–10.0 W loaded-idle floor. Thinking median energy is **1,363–1,634 J** but its p90 reaches **5.7–5.8 kJ** — the cost is in the reasoning tail, not the input. Per-rail split (median): the **GPU rail is ~70 %** of total board power (e.g. Instruct N=37: GPU 562 / VIN_SYS 150 / CPU 37 J), VIN_SYS ~20 %, CPU_CV ~5 %.

**5. Accuracy (indicative only).** Both arms trend down ~6 pp as frames are cut (Instruct 34 → 30 → 28 %, Thinking 33 → 31 → 27 %), but the Wilson-95 CIs overlap heavily at n=120 — the accuracy cost of shortening is directionally real but not statistically resolved here, and this is on-device DEV-RECENT 5-way MCQ, not the A6000 reference. So the fast path buys latency/energy at a plausible but unquantified accuracy cost.

**Bottom line.** On this device, "answer in a few seconds" is achievable by (a) using the **Instruct** model and (b) **shortening the recent window** (N=9 → <4 s, N=18 → <8 s). The **Thinking** model cannot hit a few-seconds budget at any input length, and shortening its input is counterproductive (longer reasoning, higher tail energy).

---

## Energy methodology (important)

This AGX Orin exposes **no `VDD_IN` rail**. tegrastats reports three INA3221 channels: `VDD_GPU_SOC`, `VDD_CPU_CV`, `VIN_SYS_5V0`. **Total board power = the sum of the three** (the jtop "TOT" convention); the per-rail breakdown is retained in the raw trace and the stats. Sampling was `tegrastats --interval 100` (100 ms), each row wall-clock stamped on read (tegrastats' own 1-s stamp is too coarse); per-request energy is the trapezoidal integral of total power over the request's `[wall_start, wall_end]`, with edge samples clamped to the bounds. A **60 s loaded-idle baseline** (server up, model resident, no request, 3 s post-warmup settle) was measured before each cell: **9.75–10.03 W** across all six cells (min/max within ±0.1 W — tight, confirming a clean idle).

---

## Results consistency check (6 checks)

**1. Cross-check vs committed measurements — PASS (this is the N=37 control).** The N=37 cells re-measure StudyDeviceLatency-sember on the identical frames/model/flags:

| quantity | this run | prior (StudyDeviceLatency) | ratio | agree |
|---|---|---|---|---|
| 4B-I N=37 TTFT median | 16.98 s | 17.0 s | 0.999 | ✓ (≤10 %) |
| 4B-I N=37 input tokens | 12,420 | 12,420 | 1.00 | ✓ |
| 4B-T N=37 TTFT median | 17.15 s | 17.2 s | 0.997 | ✓ (≤10 %) |
| 4B-T N=37 input tokens | 12,422 | 12,422 | 1.00 | ✓ |
| 4B-T N=37 decode tok/s | 16.2 | 16.2 | 1.00 | ✓ |

The control reproduces the prior study to <0.3 % on TTFT and exactly on input and decode — same device state, same harness.

**2. Physical plausibility — PASS.** 4B-T N=37 decode = 16.2 tok/s = **0.63× the 25.6 tok/s F16 weight-streaming roofline** (8 GB weights / 204.8 GB/s) and 1.0× the committed prior — below roofline, no caching artifact. Per-request energy satisfies `energy_j ≈ mean_w × latency` by construction (trapezoid). Active power 41–44 W is well within the Orin MAXN envelope.

**3. Distribution sanity — PASS.** Energy and latency are distributions, not constants: e.g. 4B-T N=18 latency IQR ~26 s, energy IQR ~1.4 kJ, think-token IQR ~430. Instruct cells are tight (latency IQR <0.3 s) as expected for a ~2-token, prefill-bound answer. No suspicious constants.

**4. Definition audit — PASS.** N = frame count (cells 37/18/9; `n_frames_median` = N except where a question's 120 s window starts near video start, giving fewer frames — e.g. one N=33 item). Per-frame = 332 tokens (560×560 incl. marker, from `dev_inputs.py`); input ≈ N·332 + text, matching the table. Decode tok/s = `(n_gen−1)/(latency−ttft)`, same formula as StudyDeviceLatency. Energy rail defined as above (sum of 3 INA3221 channels; no VDD_IN). Idle = 60 s loaded-idle.

**5. Claim linkage — PASS.** Bears on the **physical component of Context Inertia** (FORMULATION: transfer + reconstruction latency grows with context length). Confirms device TTFT is ~linear in frame count (prefill-bound) and quantifies the device-tier energy term. New qualitative finding: for a reasoning model the latency/energy tail is input-length-independent and grows as input shrinks — relevant to any policy that would shorten context to cut latency. No scoped-out quantity measured.

**6. Proxy validity — stated.** (a) Accuracy is **indicative only**; reference accuracy is the A6000's via the shared `dev_inputs.py`. (b) Total board power is the **sum of 3 INA3221 rails** (jtop TOT), a proxy for module power since this Orin has no single VDD_IN; per-rail breakdown reported. (c) **N=18/9 frames are the nearest-available subset of the cached N=37 DEV-RECENT frames** (same `[qt−120 s, qt]` window) — a documented approximation of `frame_times(qt, N)` snapped to the cached ~1 fps grid, chosen so the device stays inference-only (no video re-fetch) during energy measurement.

**Mechanism verification:** N/A — this is a runtime latency + energy measurement with no causal claim (same as StudyDeviceLatency-sember); mechanism-verification Steps 1–5 do not apply.

**Throttling:** none. tj_max ≤ 66.7 °C across all 720 requests (Orin thermal throttle threshold ~99 °C), GPU pinned at 1.3005 GHz (MAXN, set in preflight; sudo not available to alter mid-run). budget_hit 0/720.

---

## Files

- Harness: `experiments/device/dev_fast_latency.py` (reuses `experiments/device/dev_inputs.py`); analysis `experiments/device/dev_fast_analyse.py`.
- Per-request rows (incl. per-request energy): `results/device/devfast_{4bi_f16,4bt_f16}_n{37,18,9}.jsonl`.
- 100 ms raw power traces: `results/device/devfast_tegrastats_*.jsonl.gz`; per-token streams: `results/device/devfast_tokens_*.jsonl.gz`.
- Aggregates: `results/device/devfast_stats.json`; idle baselines + provenance: `results/device/devfast_summary.json`.
- Model sha256 (verified this run): `results/device/model_hashes.txt` (`Qwen3VL-4B-{Instruct,Thinking}-F16` + mmproj-F16).
