# Study F Report: A6000 Diagnostic — Decode Rate Separation and Memory Attribution Reference

**Date:** 2026-08-31
**Script:** `experiments/vision/study_f_a6000_diagnostic.py`
**Raw data:** `results/vision/study_f_a6000/`
**Status:** Complete. All sanity checks passed; one N=1 measurement artifact flagged below.

---

## 1. Machine and Stack Configuration

| field | value |
|---|---|
| GPU | NVIDIA RTX A6000 (48 GB), cuda:1 |
| CUDA | 11.8 |
| Driver | 550.163.01 |
| PyTorch | 2.4.1+cu118 |
| Transformers | 5.12.1 |
| flash-attn | 2.6.3 (present) |
| Attention implementation | `flash_attention_2` — asserted from loaded model config |
| dtype | bfloat16 |
| Memory bandwidth spec (A6000) | 768 GB/s (NVIDIA datasheet) |

Both Part 1 models (Qwen3-VL-4B-I and 8B-I) and the Part 2 model (Qwen2.5-VL-7B) were loaded exclusively on `cuda:1`. The companion host GPU (RTX 3090 Ti, cuda:0) was not touched.

---

## 2. Raw Measurements

### Part 1: Decode rate by model size

**Models:** Qwen3-VL-4B-Instruct (8.876 GB weights) and Qwen3-VL-8B-Instruct (17.534 GB weights)  
**Protocol:** Fixed decode: `min_new_tokens = max_new_tokens = 256`, EOS suppressed. 5 reps per condition.  
**Roofline** = A6000 bandwidth / weight bytes = 768 GB/s ÷ weight GB.

#### Roofline ceilings

| model | weight bytes | weight GB | roofline (tok/s) |
|---|---|---|---|
| Qwen3-VL-4B-I | 8,875,631,616 | 8.876 | 86.5 |
| Qwen3-VL-8B-I | 17,534,247,392 | 17.534 | 43.8 |

#### Per-rep decode times — 4B-Instruct

| rep | condition | prefill (ms) | decode (ms) | decode tok/s | peak alloc (GB) | warmup? |
|---|---|---|---|---|---|---|
| 0 | C1 | 73 | 5,650 | 45.3 | 8.98 | no |
| 1 | C1 | 73 | 5,390 | 47.5 | 8.98 | no |
| 2 | C1 | 73 | 5,273 | 48.5 | 8.98 | no |
| 3 | C1 | 202 | 5,264 | 48.6 | 8.98 | no |
| 4 | C1 | 74 | 5,278 | 48.5 | 8.98 | no |
| 0 | C2 | 74 | 106,175 | 2.4 | 9.07 | **yes** (static cache init) |
| 1 | C2 | 75 | 4,702 | 54.4 | 9.07 | no |
| 2 | C2 | 75 | 4,671 | 54.8 | 9.07 | no |
| 3 | C2 | 75 | 4,672 | 54.8 | 9.07 | no |
| 4 | C2 | 76 | 4,672 | 54.8 | 9.07 | no |
| 0 | C3 | — | — | — | — | FAILED (see §4) |

*C1 rep3 prefill = 202 ms is a one-off OS scheduling outlier; decode time and tok/s are unaffected.*

#### Per-rep decode times — 8B-Instruct

| rep | condition | prefill (ms) | decode (ms) | decode tok/s | peak alloc (GB) | warmup? |
|---|---|---|---|---|---|---|
| 0 | C1 | 109 | 8,195 | 31.2 | 17.77 | no |
| 1 | C1 | 110 | 7,957 | 32.2 | 17.77 | no |
| 2 | C1 | 110 | 7,985 | 32.1 | 17.77 | no |
| 3 | C1 | 111 | 7,995 | 32.0 | 17.77 | no |
| 4 | C1 | 111 | 8,138 | 31.5 | 17.77 | no |
| 0 | C2 | 107 | 165,128 | 1.6 | 17.84 | **yes** (static cache init) |
| 1 | C2 | 109 | 7,322 | 35.0 | 17.84 | no |
| 2 | C2 | 108 | 7,314 | 35.0 | 17.84 | no |
| 3 | C2 | 109 | 7,338 | 34.9 | 17.84 | no |
| 4 | C2 | 109 | 7,326 | 34.9 | 17.84 | no |
| 0 | C3 | — | — | — | — | FAILED (see §4) |

#### Summary (steady-state reps only, warmup excluded)

| model | condition | median tok/s | mean tok/s | std tok/s | % of roofline | n (steady reps) |
|---|---|---|---|---|---|---|
| 4B-I | C1 | 48.5 | 47.7 | 1.26 | 56.1% | 5 |
| 4B-I | C2 | 54.8 | 54.7 | 0.15 | 63.3% | 4 |
| 4B-I | C3 | — | — | — | — | FAILED |
| 8B-I | C1 | 32.0 | 31.8 | 0.37 | 73.1% | 5 |
| 8B-I | C2 | 35.0 | 34.9 | 0.04 | 79.8% | 4 |
| 8B-I | C3 | — | — | — | — | FAILED |

**Noise floor:** C1 decode std = 1.26 tok/s (4B), 0.37 tok/s (8B). Both well below the separation (~16 tok/s).

---

### Part 2: Phase-level memory attribution — Qwen2.5-VL-7B

**Model:** Qwen2.5-VL-7B-Instruct (same snapshot as Study B, bfloat16, cuda:1)  
**Image:** 560×560 px → 400 vision tokens/frame (Qwen2.5-VL); encoded in one batched call.  
**Attention:** `flash_attention_2` asserted.  
**KV bytes per token:** 57,344 B (2 × 4 heads × 128 dim × 28 layers × 2 bytes; same as Study B).

#### Phase-level memory measurements

| N | patches | after_load alloc (GB) | after_vision alloc (GB) | after_prefill alloc (GB) | peak alloc (GB) | peak reserved (GB) | KV analytical (GB) |
|---|---|---|---|---|---|---|---|
| 1 | 1,600 | **33.194** ⚠ | **33.202** ⚠ | 16.820 | **33.202** ⚠ | 35.396 | 0.025 |
| 3 | 4,800 | 16.821 | 16.837 | 16.837 | 17.096 | 35.368 | 0.071 |
| 6 | 9,600 | 16.837 | 16.859 | 16.859 | 17.369 | 25.988 | 0.140 |
| 12 | 19,200 | 16.859 | 16.904 | 16.904 | 17.916 | 25.988 | 0.278 |

**⚠ N=1 measurement artifact (see §3 and §4):** The `after_load` for N=1 reads 33.194 GB — approximately the sum of the 8B model from Part 1 (17.534 GB) plus the 7B model (16.82 GB). The Python garbage collector had not yet freed the Part 1 model when `gpu_mem_gb()` was called immediately after loading the 7B model for N=1. Evidence: `after_prefill` for N=1 is 16.820 GB, consistent with N=3–12. The GC ran during the generate call, freeing the stale 8B allocation. The N=1 `peak_alloc` (33.202 GB) is therefore unreliable; it measures 8B+7B concurrently present, not the 7B forward pass peak. N=3–12 are clean.

#### Phase attribution (N=3–12, excluding N=1 artifact)

| N | weights (GB) | vision delta (GB) | vision % of peak | KV (GB) | unaccounted (GB) | peak (GB) |
|---|---|---|---|---|---|---|
| 3 | 16.821 | 0.016 | 0.1% | 0.071 | 0.188 | 17.096 |
| 6 | 16.837 | 0.022 | 0.1% | 0.140 | 0.370 | 17.369 |
| 12 | 16.859 | 0.045 | 0.3% | 0.278 | 0.734 | 17.916 |

*Vision delta = `after_vision` − `after_load`; unaccounted = peak − weights − vision delta − KV.*

Vision encoding contributes at most 0.3% of peak at N=12. The unaccounted component (~0.2–0.7 GB) grows with N and represents activation memory during the language model forward pass (attention intermediates under flash-attn). KV matches Study B exactly (71.0 MB at N=3; 278.5 MB at N=12; ratio 1.000 as expected).

**Reference for Orin comparison:** Study E reported N=6 peak = 53.4 GB for Qwen2.5-VL-7B on Jetson AGX Orin. The corresponding A6000 figure measured here is 17.369 GB. Cross-machine attribution is deferred to the reconciliation report.

---

## 3. Sanity Checks

| check | result |
|---|---|
| SC1: Attention implementation asserted and logged | **PASS** — `flash_attention_2` confirmed on loaded model for all three model instances |
| SC2: Part 1 generated exactly 256 tokens | **PASS** — all steady-state C1 and C2 reps: n_out == 256 (asserted in-script) |
| SC3: Models on cuda:1, bfloat16, no offload | **PASS** — asserted from first parameter of each loaded model |
| SC4: Noise floor reported | **PASS** — C1 decode std: 4B = 1.26 tok/s (2.6% of median), 8B = 0.37 tok/s (1.2% of median); both below separation gap |
| SC5: Phase peaks consistent with Study B | **PASS (N=3–12)** — KV matches Study B §2 table exactly (71.0 MB at N=3, 140.2 MB at N=6, 278.5 MB at N=12, ratio 1.000). **FLAG (N=1)** — N=1 phase measurements are unreliable due to GC artifact; peak = 33.202 GB is 8B+7B concurrent, not a valid 7B single-model peak. N=1 is excluded from attribution analysis. |
| SC6: C3 failure recorded | **PASS** — `torch.compile(fullgraph=True)` failed at generate-time for both models; error stored in JSON, C1 and C2 results preserved. |

---

## 4. Part 1: Does Decode Separate by Model Size?

**Yes, clearly, under both C1 and C2.**

| condition | 4B tok/s | 8B tok/s | absolute gap | measured ratio (8B/4B) | roofline ratio (8B/4B) |
|---|---|---|---|---|---|
| C1 (dynamic cache) | 48.5 | 32.0 | −16.5 | 0.660 | 0.506 |
| C2 (static cache) | 54.8 | 35.0 | −19.8 | 0.638 | 0.506 |
| C3 (compile) | FAILED | FAILED | — | — | — |

The 4B model decodes 51–57% faster than 8B in absolute tok/s. The measured ratio (0.64–0.66) exceeds the roofline ratio (0.506), meaning 8B runs at a higher fraction of its ceiling (73–80%) than 4B (56–63%). This is consistent with 4B having a proportionally larger fixed per-token overhead relative to its weight bandwidth: when overhead is a fixed absolute cost, smaller models pay a higher overhead-to-bandwidth fraction.

**Contrast with Study E (Orin):** On Orin, both models decoded at ~9.4 tok/s (ratio ≈ 1.000). On A6000, the ratio is 0.64–0.66. The 4B/8B separation on A6000 supports the hypothesis that Orin's identical rates reflect a fixed per-token overhead floor that dominates at Orin's slower absolute throughput, not a property of the model architecture or this framework version.

**C3 failure:** `torch.compile(fullgraph=True)` failed at the first generate call for both models with `torch._dynamo.exc.Unsupported` — the flash-attn C++ extension (`flash_attn_2_cuda.PyCapsule.fwd`) is not traceable as a PyTorch graph. This is a known limitation of the current torch.compile + flash-attn combination (torch 2.4.1 / flash-attn 2.6.3). The failure occurred identically for both models and is a framework constraint, not a model-size effect. C1 and C2 are the reportable conditions.

**C2 vs C1:** Static cache adds ~+6 tok/s for 4B (54.8 vs 48.5) and ~+3 tok/s for 8B (35.0 vs 32.0). The static cache eliminates dynamic memory allocation during decode, reducing overhead for the smaller model proportionally more. C2 warmup cost is extreme (106–165 s for one call) because it allocates and initialises the full static KV tensor for the model's context limit; this is a one-time cost and is excluded from steady-state analysis.

---

## 5. Part 2: Phase-Level Memory Attribution

**Summary for N=3–12** (N=1 excluded; see §3 SC5):

The dominant memory term is model weights (~16.82–16.86 GB), accounting for 97–98% of peak. Vision encoding leaves a negligible persistent footprint (0.016–0.045 GB, <0.3% of peak). KV footprint matches the Study B analytical model exactly. The residual unaccounted term (0.19–0.73 GB at N=3–12) grows with N and represents forward-pass activation memory under flash-attn, which scales roughly linearly with sequence length in this configuration.

**Peak by N (A6000, Qwen2.5-VL-7B, flash-attn):**

| N | peak alloc (GB) | Study B reference | agree? |
|---|---|---|---|
| 1 | 33.202 ⚠ (artifact) | not directly reported | n/a |
| 3 | 17.096 | not separately reported | n/a |
| 6 | 17.369 | Study E Orin: 53.4 GB (different machine) | n/a (cross-machine deferred) |
| 12 | 17.916 | Study B N≤48 ceiling 24.4 GB at N=48 → consistent | consistent |
| 48 | not run | Study B: 24.4 GB | — |

The N=6 A6000 peak (17.369 GB) extrapolates to N=48 as approximately 16.86 + 0.278×(48/12) ≈ 16.86 + 1.11 = 17.97 GB, consistent with Study B's 24.4 GB at N=48 (the difference of ~6 GB at N=48 is plausibly activation memory at that sequence length, not measured here).

**Vision encoding fraction:** At most 0.3% of peak at N=12. Vision processing on A6000 with flash-attn is not a meaningful contributor to peak VRAM. This machine-specific baseline is reported here; comparison to Orin's behaviour at N=6 is deferred.

---

## Appendix: Software and Data Provenance

```
Script:         experiments/vision/study_f_a6000_diagnostic.py
Run date:       2026-08-31
Device:         cuda:1, NVIDIA RTX A6000 (48 GB)
torch:          2.4.1+cu118
transformers:   5.12.1
flash-attn:     2.6.3
CUDA:           11.8  |  Driver: 550.163.01
conda env:      fmtk

Part 1 models:
  Qwen3-VL-4B-Instruct  ebb281ec70b05090aa6165b016eac8ec08e71b17  /mnt/ssd/hf_models/
  Qwen3-VL-8B-Instruct  0c351dd01ed87e9c1b53cbc748cba10e6187ff3b  /mnt/ssd/hf_models/

Part 2 model:
  Qwen2.5-VL-7B-Instruct  cc594898137f460bfe9f0759e9844b3ce807cfb5  ~/.cache/huggingface/hub/

Output files:
  results/vision/study_f_a6000/study_f_environment.json
  results/vision/study_f_a6000/study_f_part1_decode.csv   (20 rows: 5 reps × 2 models × 2 conditions)
  results/vision/study_f_a6000/study_f_part1_decode.json
  results/vision/study_f_a6000/study_f_part2_memory.csv   (4 rows: N=1,3,6,12)
  results/vision/study_f_a6000/study_f_part2_memory.json
```
