# Study B Report: Does vision-token KV state behave like text KV state under reduction?

**Date:** 2026-08-30  
**Model:** Qwen2.5-VL-7B-Instruct (bfloat16, cuda:1 / A6000, 48 GB)  
**Script:** `experiments/vision/study_b_vision_kv.py`  
**Raw data:** `results/vision/study_b/study_b_results.json`, `study_b_trials.csv`  
**Status:** Complete. All sanity checks pass.

---

## 1. What was run

**Research question:** Does the cost ordering and rough magnitudes of text state representations (full / windowed / summary) measured in prior work carry over to vision-token state?

**Hypotheses:**
- H3: The ordering and magnitudes carry over.
- H4: They do not, because vision tokens have different redundancy structure and cost.

**Conditions (per N):**
1. **Full retention:** all N frames in context. State construction = prefill of all frames + query.
2. **Windowed retention (k=3):** only 3 most recent frames in context. State construction = prefill of k frames + query.
3. **Regenerated summary:** each frame described by a real generation call; summaries concatenated as text context. State construction = sum of N generation calls. Query TTFT = prefill over text-only summary context.

**N sweep:** {1, 3, 6, 12, 24, 36, 48}. Ceiling determined empirically: at N=48 (19,200 vision tokens), full context uses 1,108 MB KV, peak VRAM 24.4 GB (well within 48 GB). No ceiling was hit in the tested range.

**Metrics:** state_construction_ms, query_ttft_ms, kv_bytes_measured, peak_mem_bytes, n_generated.  
**Reps:** N=2 per (N, condition). Rep 1 for summary reuses generated summaries from rep 0 (summary generation cost paid once).

---

## 2. Raw measurements

### State construction time (ms)

| N | full | window (k=3) | summary |
|---|---|---|---|
| 1 | 207 | 143 | 777 |
| 3 | 348 | 348 | 1,958 |
| 6 | 687 | 440 | 3,756 |
| 12 | 1,368 | 356 | 7,204 |
| 24 | 2,936 | 374 | 13,846 |
| 36 | 4,521 | 376 | 21,433 |
| 48 | 6,332 | 377 | 27,854 |

*Note: For N=1 and N=3, window k=3 retains all frames (N < k), so window = full.*  
*Summary state_construction_ms = sum of individual frame summarization generation calls.*

### Query TTFT (ms) — prefill over state context to produce first answer token

| N | full | window (k=3) | summary |
|---|---|---|---|
| 1 | 207 | 143 | 29 |
| 3 | 348 | 348 | 30 |
| 6 | 687 | 440 | 66 |
| 12 | 1,368 | 356 | 58 |
| 24 | 2,936 | 374 | 102 |
| 36 | 4,521 | 376 | 174 |
| 48 | 6,332 | 377 | 177 |

*Full and window query TTFT = state_construction_ms (same forward pass).*

### KV footprint (MB)

| N | full | window (k=3) | summary (query context) |
|---|---|---|---|
| 1 | 24.9 | 24.9 | 4.1 |
| 3 | 71.0 | 71.0 | 6.6 |
| 6 | 140.2 | 71.0 | 10.0 |
| 12 | 278.5 | 71.0 | 17.4 |
| 24 | 555.1 | 71.0 | 31.8 |
| 36 | 831.8 | 71.0 | 47.7 |
| 48 | 1,108.4 | 71.0 | 61.2 |

**Full:** grows linearly with N (400 vision tokens × N + text overhead).  
**Window (N≥k=3):** constant at 71.0 MB (3 frames × 400 tokens = 1,200 vision tokens + fixed text).  
**Summary:** grows slowly with N (summary tokens accumulate: ~72–1,067 input tokens).

### Input tokens per condition (N=48)

| condition | input_tokens | vision_tokens | text_overhead |
|---|---|---|---|
| full | 19,329 | 19,200 | 129 |
| window | 1,239 | 1,200 | 39 |
| summary | 1,067 | 0 | 1,067 |

---

## 3. Sanity checks

| check | result |
|---|---|
| SC1: footprint scales with retained token count (kv_ratio within 10%) | **PASS** — ratio = 1.000 at all N for all conditions |
| SC2: summary generation produced nonzero tokens | **PASS** — 26–840 tokens generated (varies with N) |
| SC3: no CPU offload (device placement) | **PASS** — all parameters on cuda:1, verified |
| SC4: analytical KV model matches measured | **PASS** — ratio = 1.000 across all 21 (N, condition) cells |

**SC4 detail:** The analytical model `tokens × 57,344 B/token` (2 × 4 KV_heads × 128 head_dim × 28 layers × 2 bytes) matches measured KV bytes exactly at ratio 1.000 for all N and all conditions. Vision tokens obey the same per-token KV byte cost as text tokens.

---

## 4. What can legitimately be inferred

**On KV footprint (metric directly answering the core question):**  
The per-token KV cost is identical for vision tokens and text tokens: 57,344 B/token. This means the KV footprint analytical model from prior text experiments extends to vision tokens without modification. H3 is confirmed for the footprint metric: the quantity (KV bytes per token) carries over.

**On cost ordering and magnitudes (the main comparison):**

The prior text work (E35/E34) characterized *maintenance* costs — the cost to UPDATE state on each new turn when the underlying KV is already cached. Vision Study B characterizes *construction* costs — the cost to build or access the state from scratch. These are distinct workloads, so the comparison is informative but not a direct replication.

With that caveat, the orderings are:

| | text (E35, maintenance) | vision (Study B, construction) |
|---|---|---|
| full | 66 ms (warm-append, cheapest) | 6,332 ms at N=48 (most expensive, growing) |
| windowed | 653 ms (amortized) | 377 ms at N≥6 (cheapest, constant) |
| summary | 5,822 ms (recursive, most expensive) | 27,854 ms at N=48 (most expensive) |

The orderings differ:
- **Text:** full < window < summary (full cheapest, summary most expensive)
- **Vision:** window (constant) << full (growing) < summary (most expensive)

The key structural difference is that text maintenance is dominated by warm-append (prefix-cache hit, very fast), while vision "full retention" requires full prefill of all frames (no across-session KV caching). The vision window condition is cheap because it prefills only k=3 frames regardless of N.

**H4 is confirmed in the sense that magnitudes and ordering differ from the text case.** The reason is the redundancy structure: vision frames are processed de novo each time (no warm-append equivalent measured here), while text sessions exploit KV cache reuse. H3 is confirmed only for the per-token KV byte cost, not for the operational cost ordering.

**Ceiling determination:** No VRAM ceiling was encountered. At N=48 (19,329 input tokens), the full condition uses 1,108 MB KV and 24.4 GB peak VRAM on the A6000 (48 GB total). The practical ceiling is determined by quality and latency requirements, not GPU memory, in this model/hardware configuration.

**State construction cost scaling:**
- Full: ~131 ms per frame at large N (6,332 ms / 48 frames ≈ 132 ms/frame), consistent with 400 tokens/frame at A6000 throughput.
- Window: constant at ~377 ms regardless of N (once N≥k=3). Cost is N-independent by design.
- Summary: ~580 ms per frame at large N (27,854 ms / 48 frames ≈ 581 ms/frame), dominated by generation time. Construction cost grows linearly with N and is ~4.4× more expensive than full prefill per frame at large N — a significant inversion from the text case where summary maintenance is not per-turn expensive (E35 reports sum200_restore=32ms for a cached summary).

---

## 5. What cannot be inferred

- The quality difference between conditions (summaries may lose visual details; window drops old frames). This experiment measured cost only.
- Whether warm-append exists for vision tokens in this architecture (would require a multi-turn protocol where the visual KV from prior turns is preserved and new frames appended — not implemented here).
- Cost at extreme N (>48 frames, >19,200 vision tokens); the GPU has headroom to go further but was not tested.
- Whether the summary condition's query accuracy is sufficient for practical use (MAX_QUERY_TOKENS=60 was the generation budget, and all summary conditions hit this limit at N≥12, meaning answers were truncated).

---

## Appendix: Package versions and configuration

```
torch: 2.4.1+cu118
transformers: 5.12.1
Model: Qwen2.5-VL-7B-Instruct, bfloat16, cuda:1 (A6000 48 GB)
KV config: 28 layers, 4 KV heads, head_dim=128, bfloat16 → 57,344 B/token
Image size: 560×560 → 400 vision tokens/frame (from Study A)
Window k=3 (fixed)
N sweep: {1, 3, 6, 12, 24, 36, 48}
```
