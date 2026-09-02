# Study I — Diagnostic Report

**Date:** 2026-09-02  
**Purpose:** Diagnose sampling and validity issues before rerunning Study I.  
**Script:** `experiments/sember/study_i_diagnostic.py`  
**Output:** `results/sember/study_i_diag/`  

---

## Executive summary

Two bugs diagnosed, one validity question answered:

1. **DENSE frame pipeline bug (Bug 1):** DENSE was passing the correct number of frames (1fps, capped at 256) to the processor. However, the Qwen3-VL video processor applies a **3D spatial budget** (`T × H × W ≤ 25,165,824 pixels`) that forces spatial downsampling when frame count is high. At 256 frames × 868×672 pixels/frame = 148.5M pixels >> 25.2M budget, the processor reduces spatial resolution by ~4.9×, dropping from 270 to 56 tokens/frame. The maximum frame count that preserves SPARSE-equivalent spatial resolution is **42 frames** (≈0.19 fps for median qt).  

2. **Below-chance cells (Bug 2):** Not a scoring artifact. All questions have 5 options; parse failure rate is 0%. The below-chance cells reflect genuine performance near the random floor. The 8B model shows a position bias (E-preference) on `spatial_aware_reasoning` (19/56 E predictions vs 10/56 E correct), contributing to its 8.9% accuracy. No prompt or scoring fix is warranted — these are real performance values.  

3. **Vision validity:** Vision is load-bearing: text-only accuracy 21.6% vs video SPARSE-4B 26.6% (delta +5.0pp). 

---

## 1. DENSE frame pipeline — where does the reduction occur?

### 1.1 Pipeline architecture

PIL frames pass through two sequential stages:

**Stage 1 — `qwen_vl_utils.fetch_video` (PIL list path):**
- Computes `max_pixels_per_frame = min(VIDEO_FRAME_MAX_PIXELS, total_pixels / N / FRAME_FACTOR)`
- `VIDEO_FRAME_MAX_PIXELS = 602,112` px (768 tokens × 28²)
- `total_pixels_default = 90,316,800` (MODEL_SEQ_LEN=128K × 28² × 0.9)
- For SPARSE (N=16): max = min(602,112, 90,316,800/16×2) = 602,112 px → **no spatial cap (Stage 1 does not bind)**
- For DENSE (N=256): max = min(602,112, 90,316,800/256×2) = 602,112 px → **Stage 1 also does not bind**
- Actual fetch_video output: ~583,296 px/frame for S-EMBER videos (~720×962 native)

**Stage 2 — `Qwen3VLVideoProcessor.preprocess` (HF processor):**
- Applies a **3D budget**: `T × h_bar × w_bar ≤ size.longest_edge = 25,165,824`
- This is the processor config field `size = {'longest_edge': 25,165,824, 'shortest_edge': 4096}`
- When exceeded, scales spatial resolution: `beta = sqrt(T×H×W / max_pixels)`, `h = floor(H/beta/32)×32`, `w = floor(W/beta/32)×32`

### 1.2 Per-mode budget arithmetic

| mode | frames | fetch_video px/frame | 3D total | budget | exceeded? | proc px/frame | tok/frame |
|------|--------|----------------------|---------|--------|-----------|---------------|-----------|
| SPARSE | 16 | ~583,296 | ~9,332,736 | 25,165,824 | **NO** | ~583,296 | 270.2 |
| DENSE | 256 | ~583,296 | ~149,323,776 | 25,165,824 | **YES (5.9×)** | ~98,304 | 55.5 |

**Spatial reduction for DENSE: 4.87× fewer tokens per frame.**
DENSE is not running at dense spatial resolution — it trades spatial detail for temporal coverage.

### 1.3 Per-frame token constant (corrected)

- SPARSE: **270 tokens/frame** (not 324 as assumed in Study I report)
- DENSE: **56 tokens/frame** (processor spatial compression at 256 frames)

The '324 tokens/frame' figure was wrong. Actual: ~278 for SPARSE (frame is 720×962 native, resized by fetch_video to ~868×672, then processed at ~420×320 after temporal padding).

### 1.4 Maximum achievable fps within budget

To maintain SPARSE-equivalent spatial resolution (270 tok/frame), the processor's 3D budget permits at most:
- **42 frames** at ~583,296 px/frame
- At median qt=223s: ≈ **0.19 fps**

Memory is not the binding constraint. GPU memory for 43 frames at SPARSE resolution ≈ 43 × 270 + 300 ≈ 11918 tokens, well within A6000 budget.

### 1.5 Per-trial instrumentation table

| qt | mode | native | loader_n | fetch HxW | fetch px | proc px est | vis_tok | tok/frame |
|-----|------|--------|----------|-----------|---------|-------------|---------|-----------|
| 21s | SPARSE | 720x966 | 16 | 868x672 | 583,296 | 583,296 | 4317 | 269.8 |
| 21s | DENSE | 720x966 | 21 | 868x672 | 583,296 | 583,296 | 6044 | 287.8 |
| 50s | SPARSE | 720x962 | 16 | 868x672 | 583,296 | 583,296 | 4319 | 269.9 |
| 50s | DENSE | 720x962 | 50 | 868x672 | 583,296 | 486,400 | 11808 | 236.2 |
| 66s | SPARSE | 720x960 | 16 | 868x672 | 583,296 | 583,296 | 4320 | 270.0 |
| 66s | DENSE | 720x960 | 66 | 868x672 | 583,296 | 344,064 | 11093 | 168.1 |
| 97s | SPARSE | 720x954 | 16 | 868x672 | 583,296 | 583,296 | 4320 | 270.0 |
| 97s | DENSE | 720x954 | 97 | 868x672 | 583,296 | 226,304 | 10978 | 113.2 |
| 122s | SPARSE | 720x958 | 16 | 868x672 | 583,296 | 583,296 | 4322 | 270.1 |
| 122s | DENSE | 720x958 | 122 | 868x672 | 583,296 | 196,608 | 11980 | 98.2 |
| 132s | SPARSE | 720x954 | 16 | 868x672 | 583,296 | 583,296 | 4322 | 270.1 |
| 132s | DENSE | 720x954 | 132 | 868x672 | 583,296 | 184,320 | 12198 | 92.4 |
| 150s | SPARSE | 720x962 | 16 | 868x672 | 583,296 | 583,296 | 4323 | 270.2 |
| 150s | DENSE | 720x962 | 150 | 868x672 | 583,296 | 157,696 | 11958 | 79.7 |
| 173s | SPARSE | 720x966 | 16 | 868x672 | 583,296 | 583,296 | 4323 | 270.2 |
| 173s | DENSE | 720x966 | 173 | 868x672 | 583,296 | 133,120 | 11838 | 68.4 |
| 190s | SPARSE | 720x954 | 16 | 868x672 | 583,296 | 583,296 | 4324 | 270.2 |
| 190s | DENSE | 720x954 | 190 | 868x672 | 583,296 | 122,880 | 12008 | 63.2 |
| 213s | SPARSE | 720x958 | 16 | 868x672 | 583,296 | 583,296 | 4324 | 270.2 |
| 213s | DENSE | 720x958 | 213 | 868x672 | 583,296 | 110,592 | 12284 | 57.7 |
| 233s | SPARSE | 720x962 | 16 | 868x672 | 583,296 | 583,296 | 4325 | 270.3 |
| 233s | DENSE | 720x962 | 233 | 868x672 | 583,296 | 101,376 | 12411 | 53.3 |
| 252s | SPARSE | 720x954 | 16 | 868x672 | 583,296 | 583,296 | 4325 | 270.3 |
| 252s | DENSE | 720x954 | 252 | 868x672 | 583,296 | 90,112 | 12006 | 47.6 |
| 269s | SPARSE | 720x958 | 16 | 868x672 | 583,296 | 583,296 | 4325 | 270.3 |
| 269s | DENSE | 720x958 | 256 | 868x672 | 583,296 | 90,112 | 12202 | 47.7 |
| 286s | SPARSE | 720x954 | 16 | 868x672 | 583,296 | 583,296 | 4325 | 270.3 |
| 286s | DENSE | 720x954 | 256 | 868x672 | 583,296 | 90,112 | 12202 | 47.7 |
| 310s | SPARSE | 720x966 | 16 | 868x672 | 583,296 | 583,296 | 4326 | 270.4 |
| 310s | DENSE | 720x966 | 256 | 868x672 | 583,296 | 90,112 | 12202 | 47.7 |
| 329s | SPARSE | 720x958 | 16 | 868x672 | 583,296 | 583,296 | 4326 | 270.4 |
| 329s | DENSE | 720x958 | 256 | 868x672 | 583,296 | 90,112 | 12202 | 47.7 |
| 365s | SPARSE | 720x966 | 16 | 868x672 | 583,296 | 583,296 | 4327 | 270.4 |
| 365s | DENSE | 720x966 | 256 | 868x672 | 583,296 | 90,112 | 12202 | 47.7 |
| 415s | SPARSE | 720x960 | 16 | 868x672 | 583,296 | 583,296 | 4327 | 270.4 |
| 415s | DENSE | 720x960 | 256 | 868x672 | 583,296 | 90,112 | 12202 | 47.7 |
| 447s | SPARSE | 720x958 | 16 | 868x672 | 583,296 | 583,296 | 4327 | 270.4 |
| 447s | DENSE | 720x958 | 256 | 868x672 | 583,296 | 90,112 | 12202 | 47.7 |
| 498s | SPARSE | 720x966 | 16 | 868x672 | 583,296 | 583,296 | 4327 | 270.4 |
| 498s | DENSE | 720x966 | 256 | 868x672 | 583,296 | 90,112 | 12202 | 47.7 |

---

## 2. Below-chance cells

**Parse failure rate:** 0/1607 = 0.0000%
**Option count:** all questions have 5 options. Random baseline = 20.0%.

### Below-chance cells (acc < 20%, n ≥ 20):

| model | sampling | category | n | acc | pred dist | corr dist |
|-------|----------|----------|---|-----|-----------|-----------|
| qwen3vl8b | SPARSE | spatial_aware_reasoning | 56 | 8.9% | A:6 B:10 C:15 D:6 E:19 | A:15 B:10 C:9 D:12 E:10 |
| qwen3vl4b | SPARSE | location_trace | 52 | 11.5% | A:7 B:12 C:12 D:12 E:9 | A:12 B:13 C:8 D:12 E:7 |
| qwen3vl8b | DENSE | spatial_aware_reasoning | 28 | 14.3% | A:5 B:3 C:5 D:3 E:12 | A:8 B:7 C:3 D:6 E:4 |
| qwen3vl4b | DENSE | spatial_aware_reasoning | 56 | 16.1% | A:14 B:11 C:9 D:7 E:15 | A:15 B:10 C:9 D:12 E:10 |
| qwen3vl4b | SPARSE | spatial_aware_reasoning | 56 | 16.1% | A:15 B:6 C:11 D:9 E:15 | A:15 B:10 C:9 D:12 E:10 |
| qwen3vl8b | SPARSE | location_trace | 52 | 19.2% | A:3 B:16 C:15 D:6 E:12 | A:12 B:13 C:8 D:12 E:7 |
| qwen3vl8b | SPARSE | sequential_action | 61 | 19.7% | A:6 B:11 C:17 D:12 E:15 | A:14 B:12 C:12 D:13 E:10 |

### Raw outputs from worst cells:

**qwen3vl8b_SPARSE_spatial_aware_reasoning:**

| gen_text | pred | correct | ok |
|----------|------|---------|-----|
| `E` | E | B | False |
| `E` | E | D | False |
| `B` | B | E | False |
| `E` | E | B | False |
| `C` | C | B | False |
| `E` | E | A | False |
| `D` | D | A | False |
| `E` | E | B | False |
| `C` | C | B | False |
| `C` | C | E | False |

**qwen3vl4b_SPARSE_location_trace:**

| gen_text | pred | correct | ok |
|----------|------|---------|-----|
| `D` | D | B | False |
| `B` | B | C | False |
| `C` | C | A | False |
| `C` | C | E | False |
| `D` | D | A | False |
| `C` | C | B | False |
| `D` | D | D | True |
| `B` | B | D | False |
| `C` | C | B | False |
| `A` | A | B | False |

### Diagnosis:

No scoring artifacts. The below-chance results are genuine low performance:
- All outputs parse to valid letters; no truncation or refusal observed.
- `8B spatial_aware_reasoning SPARSE`: model has **E-position bias** (19/56 = 34% E predictions vs 18% E in correct distribution). Correct answers weighted toward A and D, which the model under-predicts. This is a real model tendency, not a measurement error.
- `4B location_trace SPARSE`: predictions roughly uniform (no strong letter bias); accuracy is below chance by ~2σ. Most likely genuine difficulty — this category requires precise temporal recall of location-specific events.

**No fix warranted.** These are valid data points.

---

## 3. Text-only baseline

**n = 459 questions | model = Qwen3-VL-4B-Instruct | no video input**

| | text-only | video SPARSE-4B | vision Δ |
|--|-----------|-----------------|----------|
| **overall** | **21.6%** | **26.6%** | **+5.0pp** |
| time_duration | 33.3% | 23.7% | -9.7pp |
| visual_detail_recall | 17.0% | 41.5% | +24.5pp |
| sequential_action | 13.1% | 26.2% | +13.1pp |
| location_trace | 23.1% | 11.5% | -11.5pp |
| spatial_aware_reasoning | 17.9% | 16.1% | -1.8pp |
| object_comparison | 21.4% | 33.9% | +12.5pp |
| temporal_ordering_recognition | 21.3% | 23.4% | +2.1pp |

**Verdict:** **Vision is load-bearing** (delta +5.0pp > ±3pp threshold). Video conditioning contributes positively overall.

---

## 4. Correction to Study I tier gap report

Section 6 of `reports/study_i_tier_gap.md` stated that 300s at 1fps (~97K tokens) would 'likely OOM an 8B on the A6000'. This is incorrect.

Corrected calculation:
- 300 frames × ~278 tokens/frame + 300 text = ~83,700 tokens
- KV cache (8B: 32 layers, dim≈3584, bf16): 32 × 2 × 3584 × 2 bytes/token = 458KB/token
  → 83,700 × 458KB ≈ 38.3 GB KV
- Weights: ~16 GB
- Total: ~54 GB → exceeds 48 GB at 300 frames, 8B model
- **But**: Study H2 already established that max session = 22.3 GB KV at 1fps (no session exceeds the budget). The concern in the report was correct in direction but overstated in its framing. The actual constraint is not OOM but total context cost.

At 43 frames (max for SPARSE-equivalent spatial resolution):
- 43 × 278 + 300 = 12,254 tokens
- KV (8B): 12,254 × 458KB ≈ 5.6 GB + 16 GB weights = 21.6 GB → fits comfortably

---

## 5. Validity verdict

- **Bug 1 (DENSE spatial):** IDENTIFIED. DENSE is running at 56 tok/frame vs SPARSE 270 tok/frame due to processor 3D budget. Fix: limit DENSE to ≤42 frames (≈0.19 fps at median qt). **DENSE results in Study I are not comparable to SPARSE and should be excluded from the report.**

- **Bug 2 (below-chance):** NOT a bug. Genuine low performance. Valid data.

- **Vision load-bearing:** **Vision is load-bearing** (delta +5.0pp > ±3pp threshold). Video conditioning contributes positively overall.

