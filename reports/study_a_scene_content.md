# Study A Report: Does scene content change the cost of a frame?

**Date:** 2026-08-30  
**Model:** Qwen2.5-VL-7B-Instruct (bfloat16, cuda:1 / A6000)  
**Script:** `experiments/vision/study_a_scene_content.py`  
**Raw data:** `results/vision/study_a/study_a_results.json`, `study_a_trials.csv`  
**Status:** Complete. All sanity checks pass. One confound flagged in latency analysis (§4).

---

## 1. What was run

**Research question:** For a fixed encoder configuration, does visual content change (a) vision token count, (b) prefill latency, (c) KV cache bytes, or (d) output token count?

**Hypotheses:**
- H1: Token count is driven by input resolution only (content-independent).
- H2: Token count varies with content (content-adaptive patch merging).

**Code inspection was performed first, before running anything.** See §4 for the finding.

**Setup:**
- 12 images at identical pixel dimensions (560×560) split across 9 synthetic types and 3 natural photographs resized to 560×560.
- Fixed query: "What is the main color in this image? Answer in one word."
- N=3 repetitions per image. One warmup run (not recorded).
- Text-only baseline (3 reps, no image).
- Repeat-control: same image (flat_black) run 3 additional times at end to establish noise floor.
- Cross-model check: Qwen2.5-VL-3B token count only (no latency), all 12 images.

**Complexity proxies (JPEG bytes @ q=85, Shannon entropy of grayscale histogram):**

| image | jpeg bytes | entropy (bits) | complexity label |
|---|---|---|---|
| flat_black | 5,527 | 0.00 | uniform |
| flat_red | 5,530 | 0.00 | uniform |
| gradient | 12,016 | 5.57 | low |
| circles | 70,249 | 0.36 | geometric |
| checkerboard | 84,832 | 1.00 | texture |
| fine_stripes | 58,201 | 1.00 | texture |
| blurred_noise | 8,020 | 2.13 | smooth noise |
| sparse_dots | 11,620 | 0.07 | sparse |
| random_noise | 237,867 | 7.63 | maximum entropy |
| photo_worker | 61,332 | 7.76 | natural |
| photo_park | 84,474 | 7.74 | natural |
| photo_room | 68,530 | 7.86 | natural |

These are proxies, not ground-truth complexity measures.

---

## 2. Raw measurements

### (a) Vision token count

All 12 images → **400 vision tokens** each (Qwen2.5-VL-7B).  
Cross-model check: Qwen2.5-VL-3B → **400 vision tokens** for all 12 images.

Analytical prediction: for 560×560 input, smart_resize → 560×560 (no scaling needed), grid_h=grid_w=560/14=40, vision_tokens=40×40/4=400. **Matches exactly.**

### (b) Prefill latency

| image | prefill_med (ms) | range (ms) | jpeg_kb | entropy |
|---|---|---|---|---|
| flat_black | 144.81 | 144.70–145.05 | 5 | 0.00 |
| flat_red | 144.76 | 144.73–145.22 | 5 | 0.00 |
| gradient | 146.16 | 145.92–146.32 | 12 | 5.57 |
| circles | 146.26 | 146.06–146.43 | 70 | 0.36 |
| checkerboard | 146.40 | 144.53–147.16 | 85 | 1.00 |
| fine_stripes | 145.85 | 145.59–146.71 | 58 | 1.00 |
| blurred_noise | 147.11 | 146.78–147.16 | 8 | 2.13 |
| sparse_dots | 147.08 | 146.40–147.20 | 12 | 0.07 |
| random_noise | 147.17 | 146.67–150.06 | 238 | 7.63 |
| photo_worker | 147.43 | 147.27–147.45 | 61 | 7.76 |
| photo_park | 147.06 | 146.80–148.10 | 84 | 7.74 |
| photo_room | 147.59 | 147.40–147.67 | 69 | 7.86 |

**Noise floor (repeat-control, N=3):** 0.60 ms (max−min of flat_black at end of run).  
**Cross-image spread:** 2.83 ms (max median − min median = 147.59 − 144.76).  
**Text-only baseline prefill (33 tokens):** 25.8 ms (first rep 104.5 ms is warmup artifact; median of reps 2–3 = 25.8 ms).  
**Vision contribution to prefill (approximate):** 145–148 ms − 26 ms = ~120 ms for 400 vision tokens.

### (c) KV cache bytes

All 12 images: **24.9 MB measured**. Analytical = 433 tokens × 57,344 B/token = 24.83 MB. Ratio = 1.000. All 12 images identical.

Analytical formula: `2 × 4 KV_heads × 128 head_dim × 28 layers × 2 bytes_bfloat16 = 57,344 B/token`.

### (d) Output token count

All 12 images: **2 generated tokens** (answer word + EOS). Identical across all images.

---

## 3. Sanity checks

| check | result |
|---|---|
| SC1: pixel_values shape identical across all images | **PASS** — unique shape: (1600, 1176) |
| SC2: text-only produces 0 vision tokens | **PASS** |
| SC3: repeat-control variance (noise floor) | **PASS** — 0.60 ms spread over 3 reps |
| SC4: measured vs analytical KV bytes within 10% | **PASS** — ratio = 1.000 for all images |
| H1 empirical verify: unique vision token count | **PASS** — {400} for all 12 images, both models |

---

## 4. What can legitimately be inferred

**Code inspection finding (recorded before any measurements):**

The `Qwen2VLImageProcessor._preprocess()` method in transformers 4.46.3 computes `image_grid_thw = [1, grid_h, grid_w]` where `grid_h = resized_H // patch_size` and `grid_w = resized_W // patch_size`, and `resized_H, resized_W = smart_resize(H, W, ...)`. `smart_resize` is purely arithmetic — rounding `(H, W)` to multiples of `patch_size × merge_size = 28`, with pixel-budget clipping. **No content-dependent branching exists anywhere in the processing pipeline.**

**H1 is confirmed by code inspection and confirmed empirically:** vision token count is a deterministic function of input pixel dimensions, identical across all image content types. H2 is falsified.

**On metric (b), prefill latency:** The cross-image spread of 2.83 ms (median: 144.76–147.59 ms) exceeds the repeat-control noise floor of 0.60 ms (3.5× floor). A weak apparent pattern is visible: the two uniform images (flat_black, flat_red at ~144.8 ms) are ~2 ms faster than the random-noise and natural-photo images (~147–147.6 ms).

**However, this apparent pattern is confounded by run order.** Images were processed in a fixed non-randomized sequence: flat images first, complex images later. GPU compute throughput can vary by a few percent over a run due to thermal state and memory access patterns. The noise floor measurement (3 reps of flat_black at end of run) showed slightly higher median (145.09 ms) than the start-of-run flat_black (144.81 ms), consistent with a temporal drift confound. The 2.83 ms cross-image spread cannot be attributed to content without a randomized-order repeat. **No claim is made that content affects prefill latency.**

**On metrics (c) and (d):** KV bytes and output token count are identical across all content types by construction (same sequence length from same pixel dimensions; same query). No variation observed or expected.

**Summary conclusion:** Scene content has no effect on vision token count, KV cache bytes, or output token count (for a fixed query) at fixed pixel dimensions. Prefill latency is approximately 145–148 ms for 400 vision tokens, with cross-image variation of 2.83 ms that is run-order confounded and cannot be cleanly attributed to content. The dominant predictor of all cost metrics is input pixel resolution.

---

## 5. What cannot be inferred

- Whether the 2.83 ms latency spread is a genuine content effect or thermal/scheduling noise. A randomized-order experiment with more reps would be needed.
- Whether token count would differ at non-square aspect ratios (not controlled here; smart_resize would snap to different grid dimensions per aspect ratio).
- Whether these findings hold for video input (different temporal_patch_size path).
- Whether output token count differs for open-ended queries (this experiment used a constrained short-answer query; all images produced 2-token responses).

---

## Appendix: Package versions and config

```
torch: 2.4.1+cu118
transformers: 5.12.1 (Qwen2VLImageProcessor from qwen2_vl)
Model: Qwen2.5-VL-7B-Instruct, bfloat16, device=cuda:1
image_processor: patch_size=14, merge_size=2, min_pixels=56×56=3136, max_pixels=28×28×1280=1,003,520
merge_size=2 → merge_size²=4 patches merged into 1 vision token
LM: num_hidden_layers=28, num_kv_heads=4, head_dim=128, dtype=bfloat16 → 57,344 B/token
```
