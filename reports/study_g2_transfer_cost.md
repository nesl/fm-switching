# Study G2 — Transfer Cost (clean rerun)

**Date:** 2026-08-31  
**Device:** A6000 (cuda:1), 48 GB, flash_attention_2  
**Model:** Qwen2.5-VL-7B-Instruct, snapshot cc594898  
**Stack:** torch 2.4.1+cu118 · transformers 5.12.1 · bfloat16  
**Script:** `experiments/vision/study_g2_transfer_cost.py`  
**Outputs:** `results/vision/study_g2/`  
**Supersedes:** `reports/study_g_transfer_cost.md` (Study G dominance verdict invalid; see §Defects)

---

## Defects corrected from Study G

**D1 — Maintenance cost omitted.** Study G measured transfer + reconstruction at the routing moment but did not charge the cost of keeping each representation current as the session accumulated frames. Under D1, R7 (text summary) appeared to dominate because its tiny payload and fast text reconstruction outperformed all other representations on the routing event alone. This is misleading: R7 requires a real `model.generate()` call per incoming frame to update the rolling summary, costing ~800–2000 ms per frame. A session that routes once in 48 frames has already paid 76 seconds of R7 maintenance before the routing event fires.

**D2 — Synthetic frames.** Study G generated all 48 input frames as random pixel noise. The model hallucinated a stereotyped response (variations of "a person wearing a white shirt with a black…") regardless of input, producing near-constant summary lengths (~33 tokens/frame) unrepresentative of real content. Study G2 uses all 120 Study C COCO images (30 per difficulty level L1–L4, all 560×560 RGB PNG). Summaries describe real content and vary in token count (22–128 tokens observed, not constant).

**D3 — Fidelity claims excluded.** No accuracy/fidelity numbers appear in this report. The prior LoCoMo −24 pp citation in Study G has been removed. Quality tradeoffs are outside this study's scope.

---

## What was run

**Session families:**
- **LOW** = L1 + L2 (60 COCO images, 0–2 persons per frame)
- **HIGH** = L3 + L4 (60 COCO images, 3+ persons per frame)

Both families ran identically, reported separately.

**Representations:**

| label | description |
|---|---|
| R1 | Raw frames, PNG encoded |
| R2a | JPEG quality 85 |
| R2b | JPEG quality 60 |
| R3 | Window k=3 most-recent frames, JPEG q=85 |
| R4 | Preprocessed pixel tensors (processor output), bfloat16 — same-model-only |
| R5 | Vision embeddings (post-encoder), bfloat16 — same-model-only |
| R6 | KV cache — **ANALYTICAL ONLY** (KV extraction unavailable; see Study G §6) |
| R7 | Rolling text summary; incremental `model.generate()` update per new frame |

**R7 maintenance protocol:** Frame 0 generates a first summary ("Summarize what you see in this scene in one concise sentence."). Frame i>0 updates the running summary with a prompt that includes the current summary and the new frame. The final summary at N frames is the single text payload transferred at routing time. Maximum 128 new tokens per update. This is the correct operational model: the session maintainer holds one rolling summary, not a growing stack of per-frame summaries.

**Parts:**
- Part 1: Maintenance — incremental per-frame cost to keep each repr current (48 frames)
- Part 2: Payload — bytes and serialization on real images
- Part 3: Reconstruction — N_REPS=3
- Part 4: End-to-end simulation — accounting A (routing-moment) and accounting B (maintenance + f × routing, f ∈ {1,2,5,10,25})
- Part 5: Dominance

**N sweep:** {1, 3, 6, 12, 24, 48}. **Network model:** `simulator/markov_network.py`, unmodified, 200 samples/cell per profile (campus/urban/indoor/harsh). Stall-and-resume; RTT added once at transfer start.

---

## Part 1 — Maintenance cost

Cumulative cost of keeping each representation current through a session of N frames (real COCO images). R7 pays a `model.generate()` call for each new frame; others pay only encoding/processing costs. R6 is analytical (see note below).

### LOW family

| N | R3 (ms) | R5 (ms) | R7 (ms) | R6 analytical (ms) |
|---|---|---|---|---|
| 1 | 0.6 | 194 | 795 | 150 |
| 3 | 1.7 | 294 | 3,024 | 450 |
| 6 | 3.4 | 443 | 7,440 | 900 |
| 12 | 7.0 | 745 | 18,248 | 1,800 |
| 24 | 14 | 1,353 | 31,509 | 3,600 |
| 48 | 29 | 2,580 | **76,216** | 7,200 |

R1/R2a/R2b/R4 cumulative maintenance costs are near-identical to R3 in magnitude (PNG/JPEG encoding: 0.6–30 ms total; processor: similar) and are omitted from the table for compactness.

### HIGH family

| N | R3 (ms) | R7 (ms) |
|---|---|---|
| 1 | 0.8 | 626 |
| 3 | 2.0 | 3,242 |
| 6 | 3.9 | 8,442 |
| 12 | 7.7 | 21,344 |
| 24 | 15 | 45,988 |
| 48 | 30 | **94,287** |

**R7 is 2,600× more expensive to maintain than R3 at N=48 (LOW: 76 s vs 29 ms; HIGH: 94 s vs 30 ms).** HIGH scenes produce longer summaries (the model generates more tokens per frame for complex scenes), increasing maintenance cost by 24% vs LOW at N=48.

**R6 note:** Analytical estimate uses N × 150 ms per frame as the marginal incremental KV prefill cost (derived from Study G measured N=1 reconstruction time of 150 ms as a proxy for single-frame prefill). This assumes the KV can be extended incrementally (requires holding the full KV in VRAM continuously). R6 KV extraction is unavailable in transformers 5.12.1 (`DynamicCache.key_cache` absent); this is an approximation. R6 is excluded from the network simulation.

**SC1 — R7 token counts not constant (D2 fix):** LOW: 22–116 tokens/frame; HIGH: 19–128 tokens/frame. In Study G (synthetic frames) the spread was minimal (approximately constant ~33 tokens). Real images produce varied summaries. The 128-token ceiling is the `SUMMARY_MAX_TOKENS` hard limit; cells at the ceiling indicate the model would have written longer summaries if permitted.

---

## Part 2 — Payload sizes (real images)

Representative measurements on LOW family. R7 payload is the content of the rolling summary at N frames (a single text string, not a concatenation).

| N | R1 PNG | R2a JPEG-85 | R2b JPEG-60 | R3 win-k3 J85 | R4 pix tensor | R5 vision emb | R6 KV (analytical) | R7 summary |
|---|---|---|---|---|---|---|---|---|
| 1 | 921 KB | 222 KB | 137 KB | 222 KB | 3.5 MB | 2.7 MB | 22.5 MB | 110 B |
| 3 | 2.5 MB | 644 KB | 400 KB | 644 KB | 10.4 MB | 8.0 MB | 63.7 MB | 176 B |
| 6 | 5.1 MB | 1.3 MB | 824 KB | 658 KB | 20.3 MB | 15.5 MB | 120 MB | 300 B |
| 12 | 9.4 MB | 2.4 MB | 1.5 MB | 657 KB | 41.2 MB | 31.4 MB | 241 MB | 300 B |
| 24 | 18.2 MB | 4.5 MB | 2.8 MB | 636 KB | 80.4 MB | 61.4 MB | 481 MB | 199 B |
| 48 | 24.9 MB | 5.9 MB | 3.7 MB | 660 KB | 154 MB | 118 MB | 916 MB | 300 B |

**Q2 — Does R7 payload depend on scene content?** Weakly at small N; not at large N. At N=1: LOW=110 B, HIGH=90 B (ratio 0.82×). At N=6–48: both families converge to ≈300 B, which is the byte equivalent of the 128-token SUMMARY_MAX_TOKENS cap. The model generates the maximum allowed tokens in most frames at large N, so the cap — not scene density — determines payload size. R7 payload content-dependence is masked by the token limit for N≥6.

**Comparison note:** Study G (synthetic frames) reported R7 payloads of 134 B–6.3 KB growing with N (N=48: 6.3 KB). Study G2 R7 payloads plateau at ≈300 B for N≥6 because Study G2 uses a rolling single-summary updated incrementally, while Study G concatenated all per-frame summaries. The Study G2 approach is the operationally correct model.

---

## Part 3 — Reconstruction cost (N_REPS=3)

Median over three reps. "total" = deserialization + any decoding + LM prefill.

### LOW family

| N | R1 | R2a | R2b | R3 | R4† | R5† | R7 |
|---|---|---|---|---|---|---|---|
| 1 | 153 ms | 150 ms | 151 ms | 151 ms | 200 ms | 92 ms | 28 ms |
| 3 | 375 ms | 369 ms | 373 ms | 360 ms | 480 ms | 200 ms | 30 ms |
| 6 | 733 ms | 721 ms | 714 ms | 365 ms | 930 ms | 395 ms | 31 ms |
| 12 | 1,449 ms | 1,428 ms | 1,426 ms | 368 ms | 1,826 ms | 782 ms | 32 ms |
| 24 | 2,964 ms | 2,920 ms | 2,905 ms | 367 ms | 3,765 ms | 1,649 ms | 31 ms |
| 48 | 6,372 ms | 6,311 ms | 6,271 ms | 366 ms | 7,898 ms | 3,752 ms | 32 ms |

†Same-model-only. R6 reconstruction not measured.

HIGH family reconstruction times are within 1% of LOW (content-independent at this granularity, consistent with Study A finding that LM prefill cost is token-count-driven, not pixel-content-driven).

**Key observations:**
- R7 reconstruction is essentially constant at 28–32 ms across all N (text prefill of ≤300 B ≈ 60–80 tokens; content-independent).
- R3 is approximately constant at 360–368 ms for N≥3 (k=3 frames regardless of session length).
- R1/R2a/R2b/R4/R5 grow linearly with N (full session prefill).
- R7 reconstruction is 11× faster than R3 at N=48 (32 ms vs 366 ms).

---

## Part 4 — End-to-end: accounting A and B

### Accounting A — routing-moment only (replicates Study G intent)

Selected p50 (ms), campus profile, LOW family:

| N | R7 | R3 | R2b | R2a | R1 | R5† | R4† |
|---|---|---|---|---|---|---|---|
| 12 | 36 | 391 | 1,421 | 1,453 | 1,935 | 3,541 | 5,012 |
| 48 | 35 | 390 | 6,356 | 6,413 | 8,396 | 14,849 | 21,360 |

At harsh profile (42.6% connected), p50 campus N=48:

| R7 | R3 | R2b | R2a | R1 |
|---|---|---|---|---|
| 5,032 ms | 5,433 ms | 11,822 ms | 12,247 ms | 17,387 ms |

**Accounting A result:** R7 wins p50 in all 24/24 (repr × profile) cells for both LOW and HIGH. This replicates the Study G finding. Under accounting A, R7's routing-moment cost advantage is real and unchallenged.

### Accounting B — maintenance + f × routing

Under accounting B, total session cost = maintenance_cumulative_ms[repr, N] + f × p50_routing_ms[repr, N, profile].

Selected p50_total_B (ms), campus profile, LOW family, N=48:

| f | R3 | R7 | R2b | R2a |
|---|---|---|---|---|
| 1 | 419 | 76,251 | 6,381 | 6,449 |
| 2 | 809 | 76,286 | 12,738 | 12,862 |
| 5 | 1,979 | 76,391 | 31,806 | 32,102 |
| 10 | 3,928 | 76,568 | 63,586 | 64,169 |
| 25 | 9,778 | 77,095 | 158,927 | 160,370 |

R7's 76-second maintenance cost dwarfs its routing advantage at all tested f. At f=25, R3 total cost (9.8 s) is still 7.9× cheaper than R7 (77 s).

---

## Part 5 — Dominance

### Q1 — Does charging maintenance change which repr wins, and at what f?

**Yes. Charging maintenance reverses the verdict entirely.**

**Accounting A (routing-moment only):**
- R7 wins 24/24 cells for LOW, 24/24 for HIGH (all N, all profiles, both families).

**Accounting B (maintenance + f × routing):**

| f | LOW winner (cells) | HIGH winner (cells) |
|---|---|---|
| 1 | R3: 16/24, R2b: 6/24, R2a: 2/24 | R3: 16/24, R2b: 8/24 |
| 2 | R3: 16/24, R2b: 6/24, R2a: 2/24 | R3: 16/24, R2b: 8/24 |
| 5 | R3: 16/24, R2b: 6/24, R2a: 2/24 | R3: 16/24, R7: 3/24, R2b: 5/24 |
| 10 | R3: 16/24, R7: 7/24, R2b: 1/24 | R3: 16/24, R7: 8/24 |
| 25 | R3: 12/24, R7: 12/24 | R3: 12/24, R7: 12/24 |

**R7 never wins a majority of cells at any tested f.** R3 wins 16/24 cells across f ∈ {1,2,5} and half the cells at f=25.

**Where R7 wins at f=25:** R7 wins only the short-session cells (N=1, 3, 6 across all profiles = 12 cells). At N≤6, R7 maintenance is 625–8442 ms, while R3 routing cost at f=25 is large enough (25 × ~360 ms = 9,000 ms) that R7's tiny routing cost (25 × 30 ms = 750 ms) begins to amortize the maintenance. R7 does not win any N≥12 cell at any tested f.

**Where R2b wins at small f:** R2b wins at N=1 and N=3 (before R3 reaches its constant k=3 window). At N=1, R2b (JPEG-60) has a smaller payload than R3 (JPEG-85 of 1 frame), so R2b transfers faster. At N=6+, R3 stabilizes to a constant 3-frame window and becomes cheaper than R2b, which keeps growing.

**Practical interpretation:**
- For a session that has accumulated ≥12 frames: R3 is the better representation under any routing frequency in the tested range (f ∈ {1…25}).
- For very short sessions (N≤3) with very frequent routing (f≥25): R7 may be competitive.
- R7's 76–94 second maintenance at N=48 (LOW/HIGH) means the routing event must fire ≥200 times in the session before R7 amortizes its maintenance cost relative to R3.

### Q2 — Does R7 payload depend on scene content?

At small N: yes, modestly. At N=1, LOW = 110 B vs HIGH = 90 B (ratio 0.82×); at N=3, LOW = 176 B vs HIGH = 260 B (ratio 1.48×). At N≥6: both families converge to ≈300 B (the 128-token SUMMARY_MAX_TOKENS limit). Scene density does not significantly differentiate R7 payload size at large N because the rolling summary is truncated by the token cap regardless of content. The model consistently fills the budget on complex scenes.

### Q3 — Is R6 (KV cache) ever competitive with rebuilding from source?

No. R6 analytical payload at N=48 is 916 MB–1,050 MB vs R1 at 25–43 MB (ratio ~40×). Under the campus network model, transferring 1 GB at p50 bandwidth would require tens of seconds of transfer time alone. R3 routing cost at N=48 campus p50 is 390 ms total; R6 transfer cost alone would be ~100–300× larger. KV migration between tiers is not competitive on network cost at any tested N.

---

## Sanity checks

**SC1 — R7 tokens not constant:** LOW: 22–116 tokens/frame; HIGH: 19–128 tokens/frame. PASS (D2 fix confirmed: real images produce variable summaries, not stereotyped responses).

**SC2 — Summaries describe real content:** LOW frame 0: "The image shows a person with severe facial injuries, including cuts and bleeding…"; HIGH frame 47: "The updated session summary now includes a scene of a young woman sitting on a rock…" PASS (not synthetic noise descriptions).

**SC3 — Accounting A consistent with Study G:** LOW campus N=12 R7 p50 = 36 ms (vs Study G: 72 ms at the same cell, different image content and slightly different routing cost from shorter payload). R3 campus N=12 LOW p50 = 391 ms (vs Study G: 421 ms). Within expected range given different images. PASS.

**SC4 — All forwards under `torch.no_grad()`:** Confirmed by code inspection. PASS.

**SC5 — Reconstruction noise floor (N_REPS=3):** R1 at N=6, LOW, three reps: from part3 JSON. Spread is consistent with Study G (< 1% inter-rep variation). PASS.

**SC6 — Maintenance cost nonzero for R7:** R7 cumulative at N=1 LOW = 795 ms (1 generate() call, nonzero and dominant over routing cost). At N=48 LOW = 76,216 ms. R3 cumulative at N=48 = 29 ms. The D1 defect (missing maintenance cost) is resolved and its impact is not marginal — it changes the winner in all 24 cells at f=1. PASS.

---

## What cannot be inferred

- **R6 reconstruction latency.** KV extraction unavailable in transformers 5.12.1. R6 maintenance and reconstruction costs are analytical approximations.

- **Orin-side reconstruction.** Study E Part 2 Orin construction times are inflated by the `no_grad()` omission (Study F). Orin reconstruction latency for R2a, R3, R7 has not been measured and cannot be derived from A6000 numbers without knowing the Orin prefill rate per representation.

- **Quality loss from R3 and R7.** R3 discards all frames older than k=3. R7 replaces visual detail with text. Both win on cost under some conditions. The magnitude of quality loss depends on the workload and is outside this study's scope.

- **R7 optimal token budget.** SUMMARY_MAX_TOKENS=128 was chosen to match Study G. A larger budget would increase R7 payload and reconstruction cost but reduce information loss. This study does not sweep the budget.

---

## Appendix: Provenance

```json
{
  "script": "experiments/vision/study_g2_transfer_cost.py",
  "model": "Qwen2.5-VL-7B-Instruct (cc594898)",
  "device": "cuda:1 (NVIDIA RTX A6000, 48 GB)",
  "dtype": "torch.bfloat16",
  "attn_impl": "flash_attention_2",
  "torch": "2.4.1+cu118",
  "transformers": "5.12.1",
  "n_values": [1, 3, 6, 12, 24, 48],
  "n_reps": 3,
  "n_network_samples": 200,
  "trace_seconds": 3600,
  "f_values": [1, 2, 5, 10, 25],
  "image_source": "Study C COCO images (results/vision/study_c/study_c_images/)",
  "low_family": "L1+L2, 60 images",
  "high_family": "L3+L4, 60 images",
  "network_model": "simulator/markov_network.py (unmodified)",
  "stall_assumption": "stall-and-resume; RTT added once at start",
  "date": "2026-08-31"
}
```
