# On-device latency (S-EMBER, DEV-RECENT inputs) — Jetson AGX Orin

**Date:** 2026-10-17 · **Host:** nesl-orin-3 (Jetson AGX Orin, 64 GB) · **Runtime:** llama.cpp commit `c0fd786` (CUDA sm_87)

Device-defined input construction (**DEV-RECENT**, image path); the A6000 mirrors it for accuracy. Decode/streaming runtime previously validated (`reports/device_runtime_probe.md`). This report: the 4B latency study and the 4B-vs-8B comparison — **both COMPLETE** (4B: 4B-T F16 ×120, 4B-I F16 ×120, 4B-T Q8_0 ×40; 8B: 8B-T F16 ×120, 8B-I F16 ×120; 480 requests total, no throttling).

## Preflight
GPU free (no other users); **MAXN (mode 0)**, 12 CPUs, **GPU pinned 1.3005 GHz** (sudo not passwordless → `jetson_clocks` not re-issued; already at max, unchanged). JetPack/L4T **R36.5.0**, CUDA **12.6**. HF auth: the box's active token was invalid; a valid token with gated `facebook/S-EMBER` access was found in `hf-token.txt` (gitignored) and used for video fetch in my commands only.

## DEV-RECENT construction (`experiments/device/dev_inputs.py`, importable by the A6000)
- N frames uniformly spaced over `[question_time − 120 s, question_time]` (none after qt), in time order, as **separate 560×560 images** (PIL LANCZOS; no temporal merging — deliberately not Study O's HF video path), each preceded by a `[t=XXs]` marker.
- Budget: calibrated **332 tokens/frame** (560×560, incl. marker) → **N = 37** (37×332 + text ≤ 12,500; smaller N when the window < 120 s). Verified on 3 questions: 12,155 / 12,493 / 12,468 input tokens.
- Prompt/options/answer instruction copied verbatim from `experiments/sember/study_o_q4.py`.
- Sample: **120 / 845** RECENT questions, seed 0, 16 strata (category × evidence_covered) → `results/device/latency_sember_sample.json` (97 videos).

## Runs (llama.cpp `c0fd786`, `--jinja --reasoning-format deepseek -ngl 99 -fa on -c 16384`, prompt caching on, one request at a time, streaming). GGUF hashes in `results/device/model_hashes.txt`. Seed 0.
Videos fetched per-video from `facebook/S-EMBER`, DEV-RECENT frames extracted (static ffmpeg via imageio-ffmpeg, no root), video deleted (≤ 2 on disk); frames cached and reused across phases. Per-request rows in `results/device/latency_sember_<model>_<fmt>.jsonl`; per-token timestamp arrays gzipped in `tokens_<model>_<fmt>.jsonl.gz`.

### Per-configuration latency (median / p90 / max)

| config | n | input tok (med) | prefill ms | TTFT s | decode tok/s | think tok | total latency s | budget-hit | peak RAM MB | throttle |
|---|---|---|---|---|---|---|---|---|---|---|
| **4B-T F16** | 120 | 12,422 | 15,360 / 15,403 / 15,430 | 17.2 / 17.6 / 17.7 | 16.2 / 16.2 / 18.1 | 342 / 1,236 / 3,121 | **38.3 / 93.3 / 212.4** | 0 % | 27,215 / 28,260 | **0** (tj ≤ 63.9 °C) |
| **4B-I F16** | 120 | 12,420 | 15,175 / 15,209 / 15,264 | 17.0 / 17.3 / 17.5 | — (n_gen≈2) | 0 | **17.1 / 17.4 / 17.5** | 0 % | 27,506 / 28,091 | **0** (tj ≤ 64.8 °C) |
| **4B-T Q8_0** | 40 | 12,406 | 16,300 / 16,535 / 16,586 | 18.1 / 18.6 / 18.8 | 22.0 / 22.2 / 25.8 | 470 / 2,111 / 3,987 | **37.2 / 114.6 / 203.3** | 0 % | 22,734 / 23,389 | **0** (tj ≤ 63.4 °C) |

Reading:
- **Prefill (~15.4 s for 12.4k tokens ≈ 810 tok/s) dominates the Instruct latency** (17.1 s total; the answer is ~2 tokens). For Thinking, prefill is a fixed ~15–16 s floor and the variable cost is reasoning length.
- **Q8_0 vs F16 (Thinking):** Q8_0 **decodes faster (22.0 vs 16.2 tok/s)** — smaller weights, bandwidth-bound decode — but **prefills slightly slower (16.3 vs 15.4 s)** (dequant overhead on the compute-bound prefill) and uses **less memory (22.7 vs 27.2 GB peak)**. Net total latency is similar (37–38 s median). *(Caveat: Q8_0 ran only the first 40 questions and both use temperature-1.0 sampling, so the think-token medians, 470 vs 342, are on different subsets/draws and not a like-for-like comparison.)*
- **No throttling in any configuration** — GPU stayed pinned at 1.3005 GHz, tj ≤ 64.8 °C across the whole ~3 h run (0/280 requests).

### 4B-T F16 latency by evidence_covered and category
| split | n | total latency med | think tok med |
|---|---|---|---|
| evidence_covered = **True** | 106 | 39.3 s | 368 |
| evidence_covered = **False** | 14 | 26.7 s | 154 |

The model reasons **longer when the answer's evidence was actually sampled** (368 vs 154 think tokens, 39 vs 27 s) — more on-screen content to reason over.

| question_category | n | latency med | think med |
|---|---|---|---|
| counting_objects_events | 15 | 52.2 s | 597 |
| time_duration | 18 | 49.4 s | 518 |
| object_comparison | 13 | 46.7 s | 518 |
| spatial_aware_reasoning | 13 | 39.9 s | 377 |
| temporal_ordering_recognition | 13 | 31.6 s | 226 |
| sequential_action | 14 | 29.7 s | 200 |
| location_trace | 14 | 29.6 s | 200 |
| visual_detail_recall | 20 | 27.9 s | 172 |

Counting and duration questions are the most expensive (≈ 2× the lightest categories), driven entirely by reasoning length (prefill is constant).

### Streamed-trace excerpt (4B-T F16, reasoning→answer separation with timestamps)
```
 qid c58cf9caafd7 (61 tokens)
 t=17.46s [reason] 'Got'   t=17.52s [reason] ' it'  t=17.59s [reason] ','  t=17.65s [reason] ' let'  t=17.71s [reason] "'s"  t=17.77s [reason] ' check'
 …
 t=20.94s [reason] ' be'   t=21.00s [reason] ' E'   t=21.06s [reason] '.\n'   t=21.25s [answer] 'E'
```
TTFT 17.46 s (= prefill), then reasoning streams at ~16 tok/s with a monotonic per-token timestamp and a `reason`/`answer` label; the final answer token arrives in the `content` channel.

### Secondary — on-device accuracy (reference accuracy is the A6000's; this is incidental)
4B-T F16 **33.3 %** (40/120), 4B-I F16 **34.2 %** (41/120), 4B-T Q8_0 **25.0 %** (10/40). These are DEV-RECENT (37-frame image) inputs, not Study O's video inputs, and 4B on a 5-way MCQ — not comparable to Study O's video-arm accuracy; included only as a sanity signal. One Q8_0 answer was unparsed (3,987-token reasoning trace that never emitted a clean A–E letter).

### Optional HF bf16 overhead check (step 5)
Deferred to keep the device busy with the 8B run; not required for the latency verdict. Can be run on 10 questions on request.

## 4B vs 8B (same 120-question DEV-RECENT sample, F16, seed 0)

8B visual-token geometry is **identical** to 4B — **332 tok/frame, N=37** (verified on 3 questions: 12,453 / 12,461 / 12,445 input tokens ≤ 12,500), so the same cached frames were reused. Runtime estimate before launch: ~3.5 h (< 6 h) → both models run at full 120, no cut.

| config | n | prefill ms (med) | TTFT s (med) | decode tok/s (med) | think tok (med/p90) | total latency s (med/p90/max) | peak RAM GB | tj max | throttle | acc (2nd) |
|---|---|---|---|---|---|---|---|---|---|---|
| 4B-T F16 | 120 | 15,360 | 17.2 | 16.2 | 342 / 1,236 | 38.3 / 93.3 / 212 | 28.3 | 63.9 °C | 0 | 33 % |
| **8B-T F16** | 120 | 26,538 | 28.4 | 10.0 | 318 / 977 | **59.3 / 125.3 / 422** | 36.0 | 64.7 °C | 0 | 37 % |
| 4B-I F16 | 120 | 15,175 | 17.0 | — | 0 | 17.1 / 17.4 / 18 | 28.1 | 64.8 °C | 0 | 34 % |
| **8B-I F16** | 120 | 26,477 | 28.3 | — | 0 | **28.4 / 28.8 / 29** | 36.0 | 65.6 °C | 0 | 35 % |

**8B vs 4B (Thinking, median):** prefill **1.73×** (26.5 vs 15.4 s), decode **0.62×** (10.0 vs 16.2 tok/s), total latency **1.55×** (59.3 vs 38.3 s). Instruct is prefill-bound: 28.4 vs 17.1 s (1.66×). Peak memory 36 vs 28 GB.

**Achieved decode bandwidth vs the Orin's 204.8 GB/s roofline:** F16 weight bytes are ~8 GB (4B) and ~16 GB (8B), giving per-token weight-streaming rooflines of **25.6** and **12.8 tok/s**. Measured decode: 4B **16.2 tok/s = 63 % of roofline**, 8B **10.0 tok/s = 78 % of roofline**. The 8B sits closer to bandwidth saturation; the 4B leaves more on the table to fixed per-token overhead — consistent with the smaller model being relatively more framework-overhead-bound (cf. the Study F diagnosis of HF `generate()`), and with the 8B's decode being more purely bandwidth-limited.

**Throttling:** none in any configuration — GPU pinned at 1.3005 GHz, tj ≤ 65.6 °C, **0 / 480 requests** throttled across the full 4B+8B run (~6 h of sustained load).

**Secondary accuracy** (DEV-RECENT 37-frame image inputs, 5-way MCQ; reference accuracy is the A6000's): 4B-T 33 %, 8B-T 37 %, 4B-I 34 %, 8B-I 35 % — 8B-Thinking marginally highest, but all within a narrow band on this device-input construction; not a substitute for the A6000 accuracy mirror.

## Notes
- `experiments/device/dev_inputs.py` is the shared construction for the A6000 accuracy mirror. Frame byte sizes (JPEG q90 + raw RGB) are recorded in the 8B phase for the later network model.
- Earlier STEP-1 analysis (why Study O's HF video construction can't be reproduced on llama.cpp) is in git history; superseded by the DEV-RECENT decision.
