# Study G — Transfer Cost

**Date:** 2026-08-31  
**Device:** A6000 (cuda:1), 48 GB, flash_attention_2  
**Model:** Qwen2.5-VL-7B-Instruct, Study B snapshot cc594898  
**Stack:** torch 2.4.1+cu118 · transformers 5.12.1 · bfloat16  
**Script:** `experiments/vision/study_g_transfer_cost.py`  
**Outputs:** `results/vision/study_g/`

---

## 1. What was run

The study measures the end-to-end cost of moving a session representation between tiers — payload size, serialization, reconstruction latency, and the full transfer-plus-reconstruction distribution under the Markov network model — for seven candidate representations at N ∈ {1, 3, 6, 12, 24, 48} frames per session.

**Representations:**

| label | description |
|---|---|
| R1 | Raw frames, PNG encoded |
| R2a | JPEG at quality 85 |
| R2b | JPEG at quality 60 |
| R3 | Window k=3 most recent frames, JPEG q=85 |
| R4 | Preprocessed pixel tensors (processor output), bfloat16 |
| R5 | Vision embeddings, post-encoder, bfloat16 |
| R6 | KV cache, all layers, bfloat16 — **ANALYTICAL ONLY** (see §6) |
| R7 | Text summary, per-frame `model.generate()` call; transfer cost is UTF-8 bytes |

R4 and R5 are labeled **same-model-only**: the receiving tier must run identical model weights to use these representations.

**Network model:** `simulator/markov_network.py` (not modified). Four profiles: campus, urban, indoor, harsh. 200 samples per (repr, N, profile) cell; stall-and-resume assumption; RTT added once at start.

**Parts:**
- Part 1: payload bytes and serialization time
- Part 2: reconstruction cost (deserialization + vision encoding + LM prefill), N_REPS=2
- Part 3: end-to-end distribution (p50, p95, p99) per (repr, N, profile)
- Part 4: dominance analysis

---

## 2. Payload sizes and serialization costs

| N | R1 PNG | R2a JPEG-85 | R2b JPEG-60 | R3 win-k3 J85 | R4 pix tensor | R5 vision emb | R6 KV (analytical) | R7 summary |
|---|---|---|---|---|---|---|---|---|
| 1 | 943 KB | 232 KB | 145 KB | 232 KB | 3.6 MB | 2.7 MB | 23.5 MB | 134 B |
| 3 | 2.7 MB | 696 KB | 436 KB | 696 KB | 10.8 MB | 8.2 MB | 67.4 MB | 403 B |
| 6 | 5.4 MB | 1.4 MB | 874 KB | 697 KB | 21.5 MB | 16.4 MB | 133 MB | 808 B |
| 12 | 10.8 MB | 2.7 MB | 1.7 MB | 697 KB | 43.1 MB | 32.8 MB | 265 MB | 1.6 KB |
| 24 | 21.6 MB | 5.4 MB | 3.4 MB | 697 KB | 86.1 MB | 65.7 MB | 529 MB | 3.2 KB |
| 48 | 43.2 MB | 10.9 MB | 6.8 MB | 697 KB | 172 MB | 131 MB | 1,057 MB | 6.3 KB |

**Key structural observations:**
- R7 is three to six orders of magnitude smaller than any other representation.
- R3 payload is constant at N≥3 (k=3 frames only; JPEG ~697 KB independent of session length).
- R6 KV cache grows linearly with N tokens and is by far the largest representation at N≥6. Analytical formula: N × 400 tokens/frame × 57,344 B/token (Study B).
- R4/R5 are sub-linear vs R6 (no per-layer duplication), but both scale linearly with N.
- Serialization times are negligible for all representations relative to network transfer.

**Sanity check SC1 (measured vs analytical):** R4 ratio = 1.000; R5 ratio = 1.000 at all N. Overhead in serialized bytes vs raw tensor bytes is 0.04–0.06% (torch.save header), consistent across N.

---

## 3. Reconstruction costs

Median over N_REPS=2 reps. "total" = deserialization + any encoding step + LM prefill.

| N | R1 | R2a | R2b | R3 | R4† | R5† | R6† | R7 |
|---|---|---|---|---|---|---|---|---|
| 1 | 150 ms | 150 ms | 149 ms | 150 ms | 198 ms | 91 ms | — | 30 ms |
| 3 | 361 ms | 358 ms | 359 ms | 358 ms | 487 ms | 203 ms | — | 66 ms |
| 6 | 706 ms | 699 ms | 695 ms | 361 ms | 944 ms | 395 ms | — | 44 ms |
| 12 | 1,402 ms | 1,382 ms | 1,378 ms | 361 ms | 1,854 ms | 774 ms | — | 69 ms |
| 24 | 2,887 ms | 2,849 ms | 2,838 ms | 363 ms | 3,808 ms | 1,642 ms | — | 127 ms |
| 48 | 6,247 ms | 6,165 ms | 6,220 ms | 365 ms | 8,109 ms | 3,749 ms | — | 237 ms |

†R4 and R5 are same-model-only. R6 reconstruction not measured (KV extraction unavailable — see §6).

**Key findings:**
- R7 reconstruction is cheapest at all N. At N=48: R7=237 ms vs R3=365 ms (1.5×) vs R2a=6,165 ms (26×) vs R1=6,247 ms (26×).
- R3 is approximately constant (k=3 regardless of N) for N≥3, making it the only representation whose reconstruction cost does not grow with session length.
- R5 (vision embeddings) is roughly half the reconstruction time of R1/R2a/R2b at the same N. This is because R5 skips vision encoding: only the LM prefill is charged.
- R4 is the most expensive overall because it pays for both the pixel-tensor transfer (larger payload than R1/R2) and the full vision-encode + LM-prefill path. R4's "same-model-only" restriction buys nothing on latency compared to R1.
- R2a and R2b are essentially identical to R1 in reconstruction time. JPEG compression reduces payload by 4× but the reconstruction path (PIL decode → processor → full prefill) is identical. The bottleneck is LM prefill, not decode.
- R7 reconstruction grows slowly (text-only prefill, O(L_text) not O(L_frames×400)); at N=48 the summary context is 6.3 KB ≈ ~1,600 tokens, giving a ~237 ms text prefill.

---

## 4. End-to-end distributions per profile

Selected p50 values (ms) at N=12 — illustrative cell:

| repr | campus | urban | indoor | harsh |
|---|---|---|---|---|
| R7 | 72 | 82 | 120 | 89 |
| R3 | 421 | 440 | 639 | 501 |
| R2b | 1,524 | 1,542 | 2,010 | 1,559 |
| R2a | 1,613 | 1,615 | 2,340 | 1,721 |
| R5† | 3,532 | 5,006 | 7,444 | 5,786 |
| R1 | 2,310 | 2,321 | 3,853 | 2,345 |
| R4† | 5,473 | 7,253 | 10,461 | 7,424 |
| R6† | (analytical payload only; reconstruction not measured) | | | |

†Same-model-only.

**At p95, campus, N=48:**

| repr | p95 (ms) |
|---|---|
| R7 | 379 |
| R3 | 645 |
| R2b | 7,602 |
| R2a | 7,380 |
| R1 | 12,122 |
| R5† | 17,774 |
| R4† | 25,561 |

Network profiles: campus (98.2% connected) is the most favorable; indoor (87.3%) and harsh (42.6%) add stall latency. R7 remains dominant in all four profiles. Harsh adds more variance (p95 >> p50) for large payloads because disconnection intervals can accumulate.

---

## 5. Dominance verdict

**R7 (text summary) dominates all other representations at p50 in all 24 (repr × profile) cells measured.**

At p99, R7 wins in 21/24 cells; R2a wins in 2 cells (campus/urban at N=1, where the payload is only 237 KB and the 1-s reconnection stall dominates), and R2b wins 1 cell.

**Does this mean the representation choice is not a research problem?** No. The dominance of R7 is a latency-only finding. R7 achieves low transfer cost precisely because text summaries discard visual detail. On the LoCoMo workload (Study B / E13 / E20), full-retention significantly outperforms summary (gap ≈ −24 pp). The system must trade reconstruction latency against reconstruction fidelity. R7 wins on transfer; it loses on semantic fidelity for dense workloads. The representation decision remains a research problem — it is now quantified as a latency/fidelity tradeoff, not as a latency-only choice.

**Crossover structure:**
- R3 (window k=3) is the only non-summary representation competitive with R7 at small N. At N=1–3, R3 payload equals R2a; for N≥3 R3 is constant. R3 is the best choice if same-model-only representations are excluded and the session is long (N≥6).
- R6 (KV cache, analytical) would be the most expensive payload by far (1.1 GB at N=48), plus reconstruction is not measured. Under the network model, KV transfer alone at N=48 campus p50 requires many seconds even at 100 Mbps. KV migration between tiers is not competitive on network cost.
- R4 and R5 are worse than R1/R2 on end-to-end latency at all tested N because their larger payloads outweigh any reconstruction savings. R5's reconstruction advantage (vision encoding skipped) is erased by the payload penalty.

---

## 6. Sanity checks

**SC1 — Size vs analytical (all N):** R4 ratio = 1.000; R5 ratio = 1.000. PASS.

**SC2 — Round-trip integrity (N=6 spot-check):** Serialized R5 features were deserialized, injected at image-token positions via `model.get_input_embeddings()` + `_merge_input_ids_with_image_features`, and the model was queried. Output: 48 tokens, "The image appears to be a collection of five separate images, each showing a dif…" — model produced a coherent response. PASS.

**SC3 — All forwards under `torch.no_grad()`:** Confirmed by instrumentation. PASS.

**SC4 — Device / dtype / attention:** cuda:1, bfloat16, flash_attention_2 confirmed at startup. PASS.

**SC5 — Noise floor:** N_REPS=2 per N. Spread at N=6 between two reps: R1: 706 vs 706 ms (0.0%); R2a: 699 vs 700 ms (<0.2%). Low variance — N_REPS=2 is sufficient for reporting medians.

**R6 KV extraction note:** `DynamicCache.key_cache` attribute is absent in transformers 5.12.1. R6 payload size is ANALYTICAL (N × n_input_tokens × 57,344 B). R6 reconstruction time is NOT MEASURED and R6 is excluded from the network simulation. All R6 numbers in the payload table are clearly labeled ANALYTICAL.

**R4/R5 same-model-only note:** The receiving tier must run identical model weights (Qwen2.5-VL-7B at the same snapshot). These representations cannot be used for cross-model migration. All R4/R5 results are labeled accordingly.

**Synthetic frames:** All 48 input frames are random-pixel synthetic images (seeded). Visual content is not meaningful. R7 summaries all describe "a person wearing a white shirt with a black…" — the model hallucinates consistent but fake content on pure noise. This does not affect timing measurements, which are the study's object.

---

## 7. What cannot be inferred

- **R6 reconstruction latency.** The KV cache API changed in transformers 5.10.2+; extraction is not possible in this stack. R6 reconstruction time on A6000 is not measured and cannot be interpolated from payload size alone. This is the primary gap relative to the original study specification.

- **Fidelity cost of R3, R7.** R3 reduces the visible context to k=3 frames regardless of session length. R7 replaces visual information with text. Both win on latency; both lose information. How much they lose depends on the workload (EgoSchema: minimal; LoCoMo: substantial). This study does not measure accuracy — that is the function of the fidelity audit studies.

- **Orin-side reconstruction latency.** Study E Part 2 construction times on Orin are inflated by a `no_grad()` omission (Study F). Corrected Orin times for full-retention at N=6: 17.64 GB, feasible. Orin reconstruction latency for other representations (R2a, R3, R7) has not been measured and cannot be derived from A6000 measurements without knowing the Orin prefill rate for multimodal inputs.

- **Actual network conditions.** The Markov model is parameterized from the Irish 5G driving dataset and the herolab indoor RSSI dataset (Study E31b). Orin is an indoor device; the campus and urban profiles may overstate connectivity. The harsh profile (42.6% connected) is more representative of adversarial conditions.

- **Serialization time for R6.** If KV extraction were available, torch.save of 1+ GB tensors would take several seconds — not negligible. This cost is absent from all R6 entries.

---

## Appendix: Provenance

```json
{
  "script": "experiments/vision/study_g_transfer_cost.py",
  "model": "Qwen2.5-VL-7B-Instruct (cc594898)",
  "device": "cuda:1 (NVIDIA RTX A6000, 48 GB)",
  "dtype": "torch.bfloat16",
  "attn_impl": "flash_attention_2",
  "torch": "2.4.1+cu118",
  "transformers": "5.12.1",
  "n_values": [1, 3, 6, 12, 24, 48],
  "n_reps": 2,
  "n_network_samples": 200,
  "trace_seconds": 3600,
  "network_model": "simulator/markov_network.py (unmodified)",
  "stall_assumption": "stall-and-resume; RTT added once at start",
  "date": "2026-08-31"
}
```
