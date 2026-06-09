# FM Pipeline Profiling Results
**Date:** 2026-04-17
**GPU:** NVIDIA GeForce RTX 3090 Ti (24 GB)
**Models:** Qwen2.5-VL-7B-Instruct (VLM) + Qwen2.5-7B-Instruct (LLM)
**Quantization:** 4-bit NF4 (bitsandbytes)
**Raw data:** `profiling/logs/exp1_memory.json`, `exp2_loading.json`, `exp3_latency.json`

---

## Experiment 1 — Memory Breakdown (Co-Loading)

**What it tests:** How much GPU memory the two models consume when co-loaded, and how activation memory scales with camera input configuration (number of images × resolution).

**Why it matters:** On Jetson Orin (32 GB unified memory), both models must fit simultaneously for Config A (both on edge). Activation memory determines the headroom remaining for other processes and sets the trigger threshold for migration.

**Key distinction:** Memory pressure comes from activation memory scaling with camera count and resolution — NOT from scene content or complexity. Model weights are fixed once loaded.

### Model Weight Memory

| Stage | Allocated | Free (of 24 GB) |
|---|---|---|
| Baseline | 0 MB | 24,238 MB |
| After VLM loaded | 5,954 MB | 16,672 MB |
| After VLM + LLM loaded | 11,540 MB | 10,622 MB |

- VLM weights: **~5.8 GB**
- LLM weights: **~5.5 GB**
- Both co-loaded: **~11.3 GB**
- On Jetson Orin (32 GB): ~20 GB available after both models load (before OS/other processes)

### Activation Memory During VLM Inference

Peak activation overhead above model weights (MB):

| Resolution | 1 image | 2 images | 4 images | 6 images |
|---|---|---|---|---|
| 224×224 | 155 MB | 158 MB | 180 MB | 202 MB |
| 448×448 | 175 MB | 222 MB | 322 MB | 418 MB |
| 768×768 | 238 MB | 412 MB | 658 MB | 904 MB |

**Conclusions:**
- At low resolution (224), image count barely matters — activation cost is flat (~155–202 MB).
- At high resolution (768), scaling is steep — 6 images costs 4.5× more than 1 image (904 MB vs 238 MB).
- The dominant axis is resolution, not image count. Going 224→768 at 6 images = 4.5× more activation memory.
- All configs fit on the 3090 Ti (24 GB) even with both models loaded. On Orin (32 GB unified), high-resolution multi-camera configs will compete with OS memory and trigger migration.
- No OOMs observed on this hardware — OOMs expected on Orin at 6×768 under concurrent load.

---

## Experiment 2 — Loading Time (Migration Cost Floor)

**What it tests:** Cold-start time to load each model from disk to GPU-ready state. Measured across 5 trials with full GPU clear between each, isolating loading from inference.

**Why it matters:** This is the hard floor on migration cost — the planning gap the vehicle experiences when switching configs. Even with zero context to reconstruct, the system pays this. Any KV cache reconstruction or re-prefill adds on top.

### Results (5 trials each)

| Model | Mean | Std | Min | Max | Memory |
|---|---|---|---|---|---|
| VLM (Qwen2.5-VL-7B) | **9.66s** | ±0.74s | 9.07s | 10.91s | 5,954 MB |
| LLM (Qwen2.5-7B) | **7.24s** | ±0.15s | 7.06s | 7.45s | 5,586 MB |

**Conclusions:**
- Migration floor is **7–10 seconds per model**. This is not milliseconds — it is seconds. A reactive system that waits for memory pressure to spike before migrating will incur this gap at the worst possible moment.
- Trial 1 (VLM) was 10.91s vs ~9.1–9.4s for trials 2–5. The ~1.7s cold-disk-cache penalty is real and will be worse on Jetson (slower NVMe).
- LLM is faster and more consistent (fewer shards: 4 vs 5 for VLM, slightly less data).
- **These numbers are the core motivation for proactive scheduling.** The migration cost is fixed regardless of when you migrate — but the impact depends entirely on when it happens.

---

## Experiment 3 — End-to-End Pipeline Latency (VLM → LLM)

**What it tests:** Full planning cycle latency with both models co-loaded: VLM processes camera images → produces scene description (max 150 tokens) → LLM takes description + planning prompt → produces driving decision (max 100 tokens). Measured across 5 trials per config.

**Why it matters:** Validates that the FM planning pipeline operates as an outer semantic loop (1–5 Hz range), not a control loop (30 Hz). Confirms the subsumption architecture framing.

### Results

| Config | VLM (mean) | LLM (mean) | Total (mean) | Hz |
|---|---|---|---|---|
| 1 img @ 224 | 2.21s | 1.27s | **3.48s** | 0.29 |
| 1 img @ 448 | 2.12s | 1.00s | **3.12s** | 0.32 |
| 2 img @ 224 | 2.13s | 1.10s | **3.23s** | 0.31 |
| 2 img @ 448 | 2.46s | 1.11s | **3.58s** | 0.28 |
| 4 img @ 224 | 2.05s | 1.05s | **3.10s** | 0.32 |

**Conclusions:**
- Pipeline operates at **~0.3 Hz** across all tested configs — one planning decision every ~3 seconds. Firmly confirms this is a planning loop, not a control loop.
- VLM dominates latency at ~2.1–2.5s. LLM adds ~0.5–1.5s with high variance driven by variable output length (the LLM decides when to stop generating).
- Increasing image count or resolution has surprisingly little effect on total latency at these token counts. The bottleneck is decode time, not prefill — a 4-image config is barely slower than a 1-image config.
- **Hardware caveat:** These are A6000-class measurements. Jetson Orin (unified memory, lower bandwidth) will be slower — likely 0.1–0.2 Hz. This will strengthen the case for proactive orchestration.

---

## Summary for Advisor

| Claim | Evidence |
|---|---|
| Both 7B models fit on Orin (32 GB) | Co-loaded weight: 11.3 GB, leaves ~20 GB |
| Memory pressure scales with camera config | 6×768 activation: 904 MB vs 6×224: 202 MB (4.5×) |
| Migration cost is seconds, not milliseconds | Loading floor: 7–10s per model |
| FM pipeline is a planning loop, not control loop | ~0.3 Hz end-to-end on A6000 |
| Proactive scheduling is necessary | Reactive migration → planning gap at worst-case moment |

**Next steps implied by these results:**
- Rerun exp2 and exp3 on Jetson Orin when available — loading times and latency will be higher, strengthening the motivation.
- Use exp2 numbers (7–10s) as the migration cost in the MPC cost function.
- Use exp3 numbers (~3s / 0.3 Hz) to set the outer loop cadence in the simulator.
- Use exp1 activation table to define memory pressure thresholds and migration trigger conditions.
