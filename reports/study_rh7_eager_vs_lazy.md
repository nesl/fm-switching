# StudyRH7 — eager vs lazy with the history re-send removed (H100, vLLM)

**Stack:** vLLM 0.31.0+cu129 (venv `~/.venvs/fm-switching-vllm`, torch 2.13.0+cu129), FlashAttention 3, CUDA graphs, gmu 0.90, max_model_len 32768, bf16 KV (62,944 tokens on GPU), prefix caching ON, Qwen3-VL-32B-Instruct @0cfaf481, h100nvl GPU 3. Server = RH6's GPU+host server (native `OffloadingConnector`, 256 GiB) **+ `--mm-processor-cache-gb 128`** (the one approved flag change), restarted for every cell. Harness = RH6's (RH2 plans, seed 0, per-device headers, 1× real time, 15-min window, escalation rate 1.0, greedy, max_tokens 1 / 4, D2 frames).

Pre-registration: research/EXPERIMENTS.md StudyRH7 (2026-10-21, before any GPU run), amended with the user's approval after Step 0 and before the fleet (gate clause withdrawn, D128 → D64, processor-cache flag, fallback handling, binding-attribution rule). Step 0 10:51–10:55; smoke 11:09–11:20; fleet 11:21–15:02 (3.7 h vs 4.95 h estimate, cap 8 h). Watchdog (foreign process on GPU 3, MemAvailable < 150 GiB) and GPU monitor ran for every GPU stage: 0 foreign processes, floor never reached (MemAvailable ≥ 1,148 GiB). One repetition per cell. Analysis: original `.venv`, CPU.

## Decisions

### Rule 1 — PROTOCOL ARTIFACT REMOVED: **yes**

EAGER-DELTA at D = 48: upstream-of-engine queue median **1** (≤ 10), escalation TTFT median **0.55 s** (≤ 1.5), p99 **1.21 s** (≤ 10). RH6's eager cell at the same D, plan and server (full-history bytes on every append) had median 654 s, p99 881 s and a median upstream queue of 1,301. Offered request bodies fell from 107 MB/s (RH6 A D48) to 5.9 MB/s; API-server CPU in-window median 0.40 core (RH6: 3.8). Host-hit verification passed in every cell (262,144 B per external-hit token for EAGER; 262,7xx for the lazy cells, +0.3%).

### Rule 2 — eager vs lazy at matched D

Escalation TTFT (s), in-window, all escalations (EAGER includes its 1.2–1.4% cache-miss fallbacks):

| D | EAGER p50 / p99 | LAZY p50 / p99 | LAZYD p50 / p99 | EAGER − LAZY p50 / p99 | binding — EAGER | binding — LAZY / LAZYD | computed tok per escalation E / L / LD |
|---|---|---|---|---|---|---|---|
| 32 | **0.34 / 1.01** | 1.63 / 10.42 | 1.56 / 10.08 | −1.29 / −9.41 | none (engine idle; rule: "engine (unattributed)" from ≤ 5 waiting) | per-request cold prefill; no queue (rule: "engine (unattributed)") | 5,063 / 5,371 / 5,369 |
| 48 | **0.55 / 1.21** | 2.06 / 13.72 | 1.87 / 13.95 | −1.51 / −12.51 | none binding (rule flags kv_running_set: KV max 0.95, waiting ≤ 8) | per-request cold prefill (rule: "engine (unattributed)") | 5,135 / 5,531 / 5,529 |
| 64 | **1.13 / 2.98** | 3.12 / 25.91 | 2.92 / 26.35 | −1.99 / −22.93 | GPU side, near saturation (rule: kv_running_set — KV max 0.99, waiting ≤ 19; GPU 100%) | GPU compute bursts (rule: kv_running_set; GPU 100%) | 4,924 / 5,552 / 5,560 |
| 96 | 146.6 / 212.7 | **100.5 / 151.8** | **96.5 / 147.4** | **+46.1 / +60.9** | GPU-side KV-load path (rule: kv_running_set; engine queue 1,090, running mostly 0, PCIe 17 GB/s) | GPU compute (4.6k tok/s achieved) + host capacity (rule: all three) | 4,738 / 6,606 / 6,573 |

"Computed tokens per escalation" = in-window (prompt − cached) over all requests ÷ in-window escalations; for EAGER it includes the ~10 appends per escalation. **Eager does not compute fewer tokens than lazy** (4.7–5.1k vs 5.4–6.6k per escalation, −6% to −28%); it computes them *earlier*, and it reloads the cached history from host on every append (PCIe 7.3–18.1 TB per cell vs 0.4–0.9 TB for lazy).

MATERIAL gap (one policy meets p99 ≤ T, the other does not):

| D | T = 2 s | T = 5 s | T = 15 s |
|---|---|---|---|
| 32 | **material** (EAGER) | **material** (EAGER) | not (both meet) |
| 48 | **material** (EAGER) | **material** (EAGER) | not (both meet) |
| 64 | not (neither meets) | **material** (EAGER) | **material** (EAGER) |
| 96 | not (neither) | not (neither) | not (neither) |

LAZYD gives the same table as LAZY (its p99 differs from LAZY's by ≤ 0.5 s at D32–D64 and by 4.3 s at D96, where both fail every T).

### Rule 3 — largest D sustained (p99 ≤ T)

| policy | T = 2 s | T = 5 s | T = 15 s | resource binding at the first failing D |
|---|---|---|---|---|
| EAGER-DELTA | **48** | **64** | **64** | GPU side (rule: kv_running_set) — at D64 for 2 s; at D96 for 5/15 s (engine queue 1,090, PCIe 17–20 GB/s, 0 host misses, live set 0.88× of 256 GiB) |
| LAZY | none (D32 p99 10.4) | none | **48** | GPU compute (rule at D64: kv_running_set; GPU 100%; at D96 achieved 4.6k tok/s ≈ RH5's 5.0k ceiling) |
| LAZYD | none | none | **48** | as LAZY |

As expected by the pre-registration, nothing binds in the API server once history is referenced (upstream queue median ≤ 2 in every cell). **Host capacity does not bind eager** at 256 GiB up to D96 (0 warm misses; analytic live-set peak 239 GiB at D96). What binds eager is the GPU side of the warm path: each append must bring its ~10.5k-token cached prefix into the 62,944-token GPU KV (only ~6 histories fit) and run there; the fleet serves ~7 appends/s (D64 offered 6.68 served 6.67; D96 offered 7.97 served 6.98, drain 5.68). The pre-registered flags name this kv_running_set; they cannot separate "GPU KV running-set capacity" from "offload-connector load throughput" (PCIe 17–20 GB/s, below the 35 GB/s threshold; during overload most of the 1,000+ requests sit in *waiting* with running ≈ 0–3, consistent with requests waiting on KV loads).

**Overload reverses the ordering.** At D96 eager is *worse* than lazy (median 147 vs 101 s): eager's per-append reload work grows with D whether or not anyone escalates, while lazy's work grows only with escalations. Below its knee eager wins by 3–10× on p99; past it, lazy degrades less.

### Approved-condition checks

- **LAZY D48 vs RH6 B3 (±10% on median and hit):** median 2.06 vs 2.29 s (**−10.1%, just outside**), hit 0.5085 vs 0.5085 (identical), p99 13.72 vs 13.85 s (−0.9%). By the rule this **does not reproduce** and is reported as a possible processor-cache confound (128 GiB: 52% of LAZY's image items were processor-cache hits, so re-sent frames skipped HF preprocessing). The confound is small: all 401 requests have identical prompt and cached tokens to RH6 B3 (the hit equality is deterministic, not a coincidence), and the per-request paired TTFT ratio is 0.988 (median −0.04 s).
- **Cache-miss fallbacks:** EAGER 45 / 57 / 81 / 101 (1.4 / 1.2 / 1.3 / 1.4% of requests) — **flagged (> 1%) in every EAGER cell**; 0 in every lazy cell. All but one are escalations scheduled at the same instant as an append of the same device: the append (spawned first) carries the new frames' bytes and the escalation references them before the server has inserted them. Harness timing artifact; a deployed client would send the newest frames with the escalation. Effect on EAGER escalation TTFT: without fallbacks median / p99 0.33 / 0.98 (D32), 0.53 / 1.20 (D48), 1.15 / 3.00 (D64), 146.2 / 212.6 (D96) — no decision changes. Never counted as errors.
- **Host memory:** see §Host memory. Engine-core RSS 276–303 GiB (256 GiB pinned offload buffer + processor-cache data + model runtime), API process 4–21 GiB (RH6 D96: 834 GiB). Processor cache estimated 33–88 GiB (items × 2.16 MB; vLLM has no size metric) — EAGER's extra host memory over LAZY at matched D is ≤ 4.3 GiB of processor cache (engine-core RSS +1.0 to +1.7 GiB), because LAZY also caches its (content-hashed) images.
- **DELTA/FULL body at the fleet median history:** 0.05 at 96–106 frames (EAGER; median over requests within ±5 frames of the median) — the expected ~5%. LAZYD 0.45–0.50 (it re-sends the frames since the previous escalation).

### Sensitivity (not pre-registered): window-start burst

Lazy devices start the window cold mid-session, so their first escalations arrive together; 21 of LAZY D64's 54 slowest escalations are scheduled in the window's first 60 s (EAGER D64: 1 of 54; its slow requests are late, when load builds). Excluding escalations scheduled in the first 120 s: LAZY p50 / p99 1.61 / 5.15 (D32), 1.93 / 7.59 (D48), 2.71 / 10.72 (D64); EAGER 1.17 / 3.00 at D64. Under this view LAZY would sustain D64 at T = 15 s (making D64 not material at 15 s) and still sustain nothing at T = 2 s or 5 s; EAGER's sustained D is unchanged. The pre-registered decisions above use the full window.

## Step 0 — referencing images without re-sending them (vLLM 0.31.0, no upgrade)

**Path.** An image content part may carry a client `uuid` (`entrypoints/chat_utils.py`). Sent with bytes, the processed item is cached in the multimodal processor cache under that uuid (mirrored LRU: metadata in the API server, data in the engine core). Sent as `{"type": "image_url", "image_url": null, "uuid": U}`, the item is taken from that cache; if it is not there, the request fails with HTTP 400 "Cache miss for image at index i but data is not provided" (`multimodal/processing/processor.py: _get_cache_missing_items`) — never a silent drop. The prefix-cache block keys use the item's mm hash (= the uuid), so KV reuse is unchanged. Capacity: the default cache is 4 GiB; a processed D2 frame is 2.16 MB (pixel_values 352 × 1536 fp32), and the largest cell sends ≤ 42.5k distinct session-frames (≤ 92 GB), hence 128 GiB.

**Verification (3 sessions: RH2 plan D48 devices 0–2, first session from its warm-up offset; warm-up + 3 appends at 10 s + 1 escalation; FULL = RH6 bytes, FULLU = bytes + uuids, DELTA = bytes only for frames not yet sent in the session + uuid references; identical header; `return_token_ids`).**

| criterion (user's) | result |
|---|---|
| (a) identical prompt token ids and cached tokens | **PASS** — token ids identical in all 3 formats at all 15 steps (1,029–6,052 tokens, 11–66 images); prompt tokens equal; DELTA cached == FULLU cached == FULL cached at every append/escalation (warm-up: FULL 0, FULLU/DELTA 32 = the shared header block); identical greedy outputs |
| (b) body shrinks to roughly the new frames | **PASS** — DELTA append body / new-frame bytes = 1.003–1.012 (4–5 new frames, 0.63–1.03 MB vs FULL 2.8–11.7 MB) |
| (c) API-server CPU per request drops | **PASS** — 0.06 s vs 0.30 s per append (DELTA/FULL 0.20; FULLU 0.29 s) |
| negative control | **PASS** — a uuid never sent → HTTP 400 "Cache miss for image at index 0 but data is not provided." |

**Gate amendment (user-approved before any fleet run).** The pre-registered gate also required "DELTA body ≤ 10% of the FULL body". That clause was Claude's addition, not in the user's spec, and depends on history length: with 5 new frames in 16–66-frame histories DELTA/FULL = 0.079–0.300, so the gate returned FAIL and the chain stopped. The clause is withdrawn; Step 0 passes on the user's criteria. Smoke sanity check of the ratio (D = 4, scratchpad): 5-new-frame appends 0.30 at 16 frames, 0.11–0.19 at 21–41 frames, 0.069–0.070 at 81 frames, i.e. ≈ 5 new / history length — ≈ 5% at the fleet median (~100 frames; the fleet value is measured per cell below).

## Mechanism verification (Steps 1–5; recorded before the fleet ran)

**Step 1 — causal chain.** A warm (eager) device keeps its history resident by sending each new frame as it arrives; an escalation then costs only the question and the frames since the last append (C4 / FORMULATION §context inertia: reconstruction cost grows with history, so keeping state warm pays). In RH6 that warm path was taxed by the *serving protocol*: every append re-sent the whole history's image bytes, which the API server had to receive and decode, and that ingestion — not the GPU, PCIe or host KV — collapsed at D = 48. With uuid references the bytes per append fall to the new frames (Step 0: ~1/20 at median history) and API CPU per append to ~0.2×, so the eager knee should move to a GPU-side resource: host→GPU reload of the cached prefix (PCIe), GPU compute for new frames, running-set KV, or host-buffer capacity (live set vs 256 GiB). Lazy devices send nothing until an escalation and then recompute (or host-reload, if the previous escalation's prefix is still offloaded) the whole history: their cost is GPU compute per escalation, plus, for LAZY, the full-history bytes per escalation; LAZYD removes those bytes. The eager-vs-lazy trade-off is then: eager pays continuous reload/append work and host capacity to make escalations cheap; lazy pays a large per-escalation compute burst. The deadline T decides which wins at each D.

**Step 2 — instantiate each link** (pre-fleet evidence from Step 0 and smoke; fleet values are added in §Mechanism verification — fleet values).

| causal link | implementing quantity | pre-fleet value | varies as expected? | evidence |
|---|---|---|---|---|
| uuid refs remove re-sent bytes | request body MB; body / full-equivalent | DELTA appends 1.003–1.012 × new-frame bytes; 0.07 at 81 frames | yes (∝ new / history) | Step 0 b_rows; smoke records `full_equiv_mb` |
| fewer bytes → less API CPU | API CPU-s per request | 0.06 vs 0.30 s | yes | Step 0 psutil |
| refs keep KV reuse | cached tokens | identical to FULL at every step | yes | Step 0 a_rows |
| eager keeps state warm | append/escalation cached tokens | smoke EAGER: escalations 5,520/5,751 etc. cached | yes | smoke records |
| lazy recomputes | escalation cached tokens | smoke LAZY: 0–16 cached except a repeat prefix (3,984) | yes | smoke records |
| host tier used | load bytes / external hit token | 262,144 B (verified per cell in the fleet) | measured per cell | kv_offload counters |
| cache misses → full resend | fallback count | 0 in Step 0 and smoke | per cell | records `fallback` |

No link is ABSENT or CONSTANT before the fleet.

**Step 3 — trace one unit** (smoke, real record). `RH7_SMOKE_EAGER_D4`, append with 61 frames: 5 new frames' bytes (0.97 MB) + 56 uuid refs; full-bytes equivalent 10.79 MB (ratio 0.090). Prompt 5,534 tokens, cached 5,072 (from the previous append), computed 462 (5 × 90 + text); TTFT 0.183 s. Bound: nothing (D = 4) — engine idle, API idle. The fleet section repeats this trace for a record at D\* of each policy.

**Step 4 — negative control.** The mechanism under test is "re-sent history bytes bind the eager fleet". It is switched off/on at equal GPU work twice: (i) **LAZY vs LAZYD** at every D — the same escalations, prompts and KV work, with and without the full-history bytes; if bytes do not matter, the two must coincide; (ii) **EAGER-DELTA D48 vs RH6 A D48** (committed) — same plan and server except for the bytes (and the processor-cache size); RH6 collapsed (median 654 s), so if the protocol artifact is what bound it, EAGER-DELTA D48 must not.

**Step 5 — alternative explanations to check in the data.** (a) *A better EAGER-DELTA result comes from the 128-GiB processor cache, not from fewer bytes* (cached items skip HF preprocessing even when bytes are re-sent): distinguished by LAZY (full bytes, same server) — the LAZY D48 vs RH6 B3 reproduction check measures what the cache alone changes. (b) *The harness is the bottleneck*: submit lag p99 per cell. (c) *Eager's advantage is only GPU-resident KV, not the host tier*: host share of hits and 262,144 B/hit-token per cell. (d) *Plan coverage, not policy*: D96 has 68/96 devices out of sessions before window end — both policies see the same plan, so the comparison is matched, but D96 is not 2× D48's load (7,170 vs 4,662 eager events).

## Per-cell metrics

Window = 900 s from window start; "whole" (PCIe, achieved, KV, waiting) = window start → drain end. All TTFTs from submission; submit lag p99 ≤ 0.13 s in every cell (harness on time).

**Latency and queue location**

| cell | req/s | esc n | esc TTFT p50 / p90 / p99 / max (s) | append TTFT p50 / p99 | upstream-of-engine q (median) | engine q (median) | waiting max | in flight at window end | drain (s) | GPU util (window median %) | API cores (window median) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| EAGER D32 | 3.46 | 267 | 0.34 / 0.67 / 1.01 / 1.58 | 0.34 / 0.96 | 0 | 0 | 5 | 0 | 0 | 62 | 0.26 |
| LAZY D32 | 0.30 | 267 | 1.63 / 4.07 / 10.42 / 14.01 | — | 0 | 0 | 3 | 0 | 0 | 0 | 0.02 |
| LAZYD D32 | 0.30 | 267 | 1.56 / 4.07 / 10.08 / 13.96 | — | 0 | 0 | 4 | 0 | 0 | 0 | 0.02 |
| EAGER D48 | 5.18 | 397 | 0.55 / 0.92 / 1.21 / 1.69 | 0.48 / 1.24 | 1 | 1 | 8 | 1 | 0.2 | 85 | 0.40 |
| LAZY D48 | 0.45 | 397 | 2.06 / 6.36 / 13.72 / 15.63 | — | 0 | 0 | 6 | 0 | 0 | 89 | 0.03 |
| LAZYD D48 | 0.45 | 397 | 1.87 / 5.69 / 13.95 / 15.48 | — | 0 | 0 | 6 | 0 | 0 | 76 | 0.03 |
| EAGER D64 | 6.68 | 533 | 1.13 / 2.12 / 2.98 / 3.45 | 1.04 / 3.00 | 2 | 5 | 19 | 1 | 0.1 | 100 | 0.51 |
| LAZY D64 | 0.60 | 533 | 3.12 / 15.68 / 25.91 / 29.70 | — | 0 | 1 | 19 | 0 | 0 | 100 | 0.14 |
| LAZYD D64 | 0.60 | 533 | 2.92 / 15.57 / 26.35 / 28.29 | — | 0 | 1 | 18 | 0 | 0 | 100 | 0.11 |
| EAGER D96 | 7.97 | 658 | 146.6 / 209.3 / 212.7 / 213.1 | 146.1 / 212.4 | 2 | 1,090 | 1,410 | 886 | 154 | 100 | 0.61 |
| LAZY D96 | 0.74 | 658 | 100.5 / 142.9 / 151.8 / 154.2 | — | 1 | 71 | 111 | 24 | 38 | 100 | 0.35 |
| LAZYD D96 | 0.74 | 658 | 96.5 / 138.5 / 147.4 / 148.8 | — | 1 | 70 | 107 | 21 | 35 | 100 | 0.20 |

**KV, host tier, compute, bytes**

| cell | token hit | host share of hits | B / host-hit token | KV median / max | PCIe load avg / best 30 s / 1-s peak (GB/s); total TB | computed tok/s achieved / demand | computed tok per esc | warm misses | alloc failures | body MB/s offered / served | DELTA body / full (all; at median history) | processor-cache hits / queries |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| EAGER D32 | 0.955 | 0.963 | 262,209 | 0.00 / 0.92 | 8.1 / 10.2 / 23.3; 7.3 | 1,524 / 1,502 | 5,063 | 0 / 2,995 | 0 | 4.1 / 4.1 | 0.05; 0.05 (101 fr.) | 340,853 / 355,232 |
| LAZY D32 | 0.523 | 0.929 | 263,371 | 0.00 / 0.86 | 0.4 / 1.0 / 7.4; 0.38 | 1,590 / 1,593 | 5,371 | 0 / 173 | 0 | 7.0 / 7.0 | 1.00 | 18,854 / 34,898 |
| LAZYD D32 | 0.523 | 0.927 | 263,374 | 0.00 / 0.86 | 0.4 / 0.9 / 5.9; 0.38 | 1,588 / 1,593 | 5,369 | 0 / 173 | 0 | 3.3 / 3.3 | 0.45; 0.46 | 18,854 / 34,898 |
| EAGER D48 | 0.955 | 0.976 | 262,186 | 0.19 / 0.95 | 12.3 / 15.0 / 24.2; 11.1 | 2,281 / 2,265 | 5,135 | 0 / 4,507 | 0 | 5.9 / 5.9 | 0.05; 0.05 (101 fr.) | 503,147 / 524,736 |
| LAZY D48 | 0.508 | 0.979 | 262,950 | 0.00 / 0.94 | 0.6 / 1.3 / 10.5; 0.58 | 2,433 / 2,440 | 5,531 | 0 / 251 | 0 | 10.3 / 10.3 | 1.00 | 26,588 / 50,876 |
| LAZYD D48 | 0.509 | 0.977 | 262,951 | 0.00 / 0.83 | 0.6 / 1.3 / 10.6; 0.58 | 2,435 / 2,439 | 5,529 | 0 / 252 | 0 | 5.0 / 5.0 | 0.49; 0.49 | 26,588 / 50,876 |
| EAGER D64 | 0.955 | 0.977 | 262,177 | 0.50 / 0.99 | 15.7 / 18.0 / 28.0; 14.2 | 2,908 / 2,916 | 4,924 | 0 / 5,824 | 0 | 7.9 / 7.9 | 0.05; 0.05 (96 fr.) | 635,489 / 663,183 |
| LAZY D64 | 0.510 | 0.985 | 262,735 | 0.21 / 0.96 | 0.9 / 2.1 / 8.7; 0.80 | 3,279 / 3,288 | 5,552 | 9 / 339 | 0 | 14.0 / 14.0 | 1.00 | 36,129 / 68,034 |
| LAZYD D64 | 0.509 | 0.983 | 262,737 | 0.22 / 0.97 | 0.9 / 1.9 / 10.7; 0.79 | 3,286 / 3,293 | 5,560 | 9 / 338 | 0 | 6.6 / 6.6 | 0.46; 0.50 | 36,129 / 68,034 |
| EAGER D96 | 0.957 | 0.981 | 262,170 | 0.59 / 0.99 | 17.1 / 19.9 / 27.9; 18.1 | 2,971 / 3,464 | 4,738 | 0 / 5,416 | 0 | 9.6 / 8.3 | 0.04; 0.05 (106 fr.) | 805,796 / 838,700 |
| LAZY D96 | 0.433 | 0.971 | 262,699 | 0.58 / 0.99 | 0.9 / 1.9 / 10.9; 0.85 | 4,622 / 4,830 | 6,606 | 60 / 302 | 0 | 17.7 / 16.9 | 1.00 | 44,718 / 85,962 |
| LAZYD D96 | 0.436 | 0.973 | 262,694 | 0.59 / 0.99 | 0.9 / 2.1 / 10.7; 0.85 | 4,617 / 4,805 | 6,573 | 60 / 306 | 0 | 8.5 / 8.3 | 0.45; 0.45 | 44,718 / 85,962 |

Warm miss = cached < 0.5 × the previous completed request's prompt in the same device-session (RH6 definition); for lazy cells this measures whether the previous escalation's prefix survived in the host buffer. Host-hit verification (whole cell, 262,144 B ± 5%) **passed in all 12 cells**. Errors: over-context 400s (sessions longer than 32,768 tokens; same plan artifact as RH6) — EAGER 46 / 46 / 46 / 63, lazy 4 per cell; one other error (`ReadError`, EAGER D96). No censored requests (the 2,400-s drain cap was never reached).

## Host memory (approved condition 2a)

| cell | engine-core RSS peak (GiB) | API-server RSS peak | tree peak | MemAvailable min | KV offload buffer | processor cache (est.; items) |
|---|---|---|---|---|---|---|
| EAGER D32 / LAZY / LAZYD | 276.9 / 275.9 / 275.9 | 7.1 / 4.3 / 4.2 | 280.6 / 279.0 / 278.4 | 1,196 | 256 GiB | 35.4 (16,772) / 32.7 (15,470) / 32.7 |
| EAGER D48 / LAZY / LAZYD | 286.1 / 284.4 / 284.4 | 9.6 / 4.7 / 4.4 | 291.0 / 287.3 / 286.9 | 1,185 | 256 GiB | 54.3 (25,712) / 50.1 (23,714) / 50.1 |
| EAGER D64 / LAZY / LAZYD | 293.9 / 292.3 / 292.3 | 12.2 / 5.1 / 5.0 | 300.1 / 295.7 / 295.4 | 1,176 | 256 GiB | 70.5 (33,377) / 66.2 (31,331) / 66.2 |
| EAGER D96 / LAZY / LAZYD | 303.4 / 302.0 / 302.0 | 21.1 / 13.7 / 10.3 | 324.2 / 312.3 / 309.6 | 1,148 | 256 GiB | 88.2 (41,772) / 85.9 (40,670) / 85.9 |

RSS sampled every 10 s (server tree, split API process / engine-core children). The engine-core RSS holds the pinned 256 GiB offload buffer, the processor-cache data and the runtime; the processor-cache size is estimated (items × 2.16 MB processed D2 frame; vLLM 0.31.0 exposes only `mm_cache_queries/hits`). The estimate exceeds the measured RSS growth above the offload buffer (e.g. EAGER D96: 88 GiB estimated vs ~47 GiB above 256), so the 2.16 MB fp32 item size likely overstates the cached size (vLLM may store processed tensors in bf16) — treated as an upper bound. EAGER's host-memory cost over LAZY at matched D: ≤ 4.3 GiB of processor cache, +1.0–1.7 GiB engine RSS, +2.8–7.4 GiB API RSS.

## Mechanism verification — fleet values

**Step 2 (completed with fleet values).**

| causal link | implementing quantity | value / range | varies as expected? |
|---|---|---|---|
| refs remove re-sent bytes | body MB/s offered (EAGER) | 4.1–9.6 MB/s (RH6 A: 72–172) | yes; body/full 0.05 at median history |
| fewer bytes → API not binding | upstream-of-engine q median; API cores | ≤ 2 in every cell; ≤ 0.61 core (RH6 D48: 1,301; 3.8) | yes |
| eager keeps state warm | EAGER token hit; host share | 0.955–0.957; 96–98% host-served | yes, flat in D |
| warm path costs reload | PCIe load TB (EAGER vs LAZY) | 7.3 → 18.1 TB vs 0.4–0.9 | yes, ∝ append rate |
| lazy recomputes | lazy token hit; computed tok per escalation | 0.43–0.52; 5.4–6.6k | yes (hit falls at D96 as the host buffer stops holding previous escalations: 60/302 misses) |
| bytes matter for lazy? | LAZY vs LAZYD TTFT | p50 within 0.07–0.21 s (D≤64), 4 s at D96 | barely — lazy is compute-bound |
| GPU side binds eager at its knee | engine queue; served rate | D96: 1,090; serves ~7 req/s of 7.97 offered | yes |
| host capacity | warm misses (EAGER); live-set peak | 0 in every EAGER cell; 0.34–0.88× of 256 GiB | not reached (EAGER) |

No link ABSENT or CONSTANT.

**Step 3 — traces (real records, `study_rh7_requests_h100nvl.jsonl.gz`).**
- *EAGER D48, median escalation:* device 02, session 0, session time 363 s: 182 frames, 1 new frame's bytes + 181 refs, body 0.27 MB (full-bytes equivalent 33.6 MB); submitted 0.004 s after schedule with 3 requests in flight. Prompt 16,614 tokens, cached 16,320 (98% host-served in this cell → ~4.3 GB reloaded at 262,144 B/token), computed 294. TTFT 0.531 s. Bound: none — engine queue ≤ 1, API idle.
- *EAGER D96, median escalation:* device 76, session 1, t = 122 s: 62 frames (1 new), body 0.14 MB (full 8.46 MB); 1,001 requests in flight at submit. Prompt 5,758, cached 5,520, computed 238 — the request's own work is < 0.2 s, but TTFT 145.7 s: it waited in the engine queue (waiting ~1,000–1,400, running 0–3) behind other appends' KV reloads. Bound: GPU-side warm path (not API: upstream q 2; not host capacity: 0 misses).
- *LAZY D64, p99 escalation:* device 00, session 0, t = 117 s, scheduled 34 s into the window: 59 frames, full bytes 11.1 MB; prompt 5,477, cached 3,984 (the previous escalation's prefix), computed 1,493; 11 requests in flight (the window-start burst of cold lazy escalations). TTFT 26.1 s = queueing behind cold prefills. Bound: GPU compute (bursty).

**Step 4 — negative controls (outcomes).** (i) LAZY vs LAZYD (bytes on/off at equal GPU work): TTFT medians differ by ≤ 0.21 s at D ≤ 64 and p99 by ≤ 0.5 s; bodies differ 2× — so for lazy devices the re-sent bytes are *not* what drives latency; the bytes mechanism only binds at eager's request rate. (ii) EAGER-DELTA D48 vs RH6 A D48 (same plan and server family; bytes per append 107 → 5.9 MB/s): median 654 s → 0.55 s, upstream queue 1,301 → 1. Removing the bytes removes the RH6 collapse; the mechanism claimed by RH6 is confirmed by switching it off.

**Step 5 — alternatives, checked.** (a) *The 128-GiB processor cache, not fewer bytes, rescued eager:* LAZY (full bytes, same cache) reproduces RH6 B3 to −10% median / identical hit — the cache changes little for full-byte traffic; and RH6's API server collapsed on *ingestion* (bytes), which the cache does not remove. (b) *Harness bottleneck:* submit lag p99 ≤ 0.13 s, harness ≤ 0.18 cores. (c) *Eager's win is GPU-resident KV only:* host share of hits 96–98% in every EAGER cell, 262,144 B per host-hit token — the host tier carries it. (d) *Plan coverage, not policy:* both policies run the same plans; D96 offers only 1.19–1.23× D64's request rate (68/96 devices finish their plans early), so the D64→D96 step is a smaller load step than the D label suggests. (e) *Window-start burst inflates lazy tails:* real (see Sensitivity); it changes D64's 15-s materiality, not the other decisions.

## Results consistency check

1. **Cross-check against committed measurements.**

| quantity | this run | prior | source | ratio | agree? |
|---|---|---|---|---|---|
| LAZY D48 esc TTFT median / p99 / hit | 2.06 / 13.72 / 0.5085 | 2.29 / 13.85 / 0.5085 (RH6 B3) | results/cost/study_rh6 | 0.90 / 0.99 / 1.00 | agree (< 2×); median just outside the approved ±10% — reported above |
| EAGER D32 esc median (bytes removed) | 0.34 s | 0.56 s (RH6 A D32, full bytes) | study_rh6 | 0.61 | agree (< 2×); direction expected |
| EAGER D32 PCIe load total | 7.28 TB | 7.27 TB (RH6 A D32) | study_rh6 | 1.00 | agree — same plan, same reloads |
| bytes per host-hit token | 262,144–263,374 | 262,144 | RH5 / RH6 | 1.000–1.005 | agree |
| achieved computed tok/s at saturation | 4.62k (LAZY D96) | 5.0k (RH5 GPU-only collapse), 4.83k (RH6 C) | RH5, RH6 | 0.92 / 0.96 | agree |
| D2 tokens per frame | 90 | 90 | RH6 | 1.00 | agree |
| GPU KV tokens | 62,944 | 62,944 | RH5/RH6 servers | 1.00 | agree |

2. **Physical plausibility.** EAGER D48 escalation: 16,320 cached tokens ≈ 4.3 GB host-served within a 0.53-s TTFT → ≤ 8 GB/s needed, under the measured 1-s peaks (23–28 GB/s); computed 294 tokens. EAGER served ~7 appends/s at saturation ≈ 73k reloaded tokens/s ≈ 19 GB/s — equal to the measured 17–20 GB/s. Lazy cold escalations: ~5.5k computed tokens in a 1.6–2.1 s median (≈ 2.6–3.4k tok/s per request, below the 4.5–5k prefill rate). Nothing faster than committed curves.
3. **Distribution sanity.** The identical LAZY D48 / RH6 B3 hit (to 16 digits) is explained: all 401 requests have identical prompt and cached tokens — cached tokens in lazy cells are a deterministic function of the plan (previous escalation's block-aligned prefix). Bytes-per-host-hit-token is exactly 262,144 in some cells and up to +0.5% in lazy cells (partial blocks), not a constant. TTFT spreads are reported (p90/p99/max) in every cell.
4. **Definition audit.** D2 = 352×256 PNG, 90 tokens/frame (+ text), stride 2 s — as RH6. Escalation TTFT from client submission to first content token — as RH6. "Computed tokens" = prompt − cached — as RH6. Warm miss — as RH6. New: "computed tokens per escalation" (defined in Rule 2); "upstream-of-engine queue" = RH6's (not pre-registered in RH6; pre-registered here). Over-context requests are excluded as errors, as in RH6.
5. **Claim linkage.** **C4** (physical inertia grows with context): supports — lazy escalations pay history-proportional prefill (p99 10–26 s at D ≤ 64), while warm (eager) state answers in 0.3–1.1 s median. **C5** (joint representation × placement × *timing*): supports the timing dimension — with the protocol fixed, the eager/lazy choice is *material* at every deadline tested for some D (2 s at D ≤ 48, 5 s at D ≤ 64, 15 s at D64), and the better choice **reverses past the eager knee** (D96: lazy p50 −31%). The reversal is the kind of regime-dependence C5 needs; a single repetition per cell bounds how strongly it can be stated.
6. **Proxy validity.** (i) "Binding resource" labels come from pre-registered thresholds; at the eager knee they read kv_running_set, but they cannot separate GPU-KV running-set capacity from offload-load throughput (stated). (ii) NVML GPU util counts any kernel (including KV-copy kernels), so 100% is "GPU busy", not "compute-bound". (iii) Computed tok/s ignores attention over the cached context and the reload; the gpu_compute flag (≥ 4k tok/s) therefore never fires for eager even when the GPU is saturated — reported as a limitation, not used for a headline. (iv) Processor-cache size is an estimate (upper bound).

## H100 monitoring (this run)

`results/cost/h100_monitoring_summary.json` regenerated with StudyRH7 (queue10): 3 step windows (step0 10:51–10:55 rc 1 = the STOP; smoke 11:09–11:20; fleet 11:21–15:02), 1,352 GPU-3 samples, **0 foreign processes** (1,308 GPU-3 process samples, all own vLLM pids from 16 server logs), no watchdog FOREIGN or memory-floor line, SM clock busy min / median / max 570 / 1,080 / 1,785 MHz, GPU-3 memory ≤ 88,688 MiB. The summary script's chain-log regex matched only single-digit queue numbers (`QUEUE\d`); fixed to `QUEUE\d+` (earlier runs unchanged).

## Deviations and notes

- **Step 0 gate STOP and amendment:** pre-registered gate FAIL on a clause Claude added ("DELTA ≤ 10% of FULL"); chain halted at 10:55; the user withdrew the clause and approved continuing (Step 0 passes on the user's criteria). Recorded in the step0 JSON (`amendment`) and the EXPERIMENTS row.
- **Grid:** D128 replaced by D64 (user, before the fleet).
- **Server flag:** `--mm-processor-cache-gb 128` (user-approved) in every RH7 cell; server restarted per cell (RH6 shared one server across a Part).
- **Incident — stray server on GPU 0 (11:07, ~70 s):** an offline run of `--stage estimate` fell through into the fleet path (a `return` lost when the estimate gate was edited) and started a vLLM server outside tmux without a GPU pin; it loaded on **GPU 0** (shared host GPU, not ours) until stopped. GPU 0 was released, no results or metadata were written, the stray `/dev/shm` semaphore was removed, and the `return` restored. No RH7 data came from it.
- **Cache-miss fallbacks > 1% in every EAGER cell** (harness timing race; see Approved-condition checks). Not fixed mid-fleet to keep cells consistent.
- **Binding-attribution rule** fixed after Step 0, before the fleet (EXPERIMENTS amendment v).
- **Not pre-registered:** window-start sensitivity; running-vs-waiting split at EAGER D96.
- **Over-context errors** as in RH6 (plan sessions longer than 32,768 tokens).
- **Single repetition per cell.**

## Files

- `experiments/cost/study_rh7_eager_lazy.py` — harness (vLLM venv): step0, estimate, smoke, fleet.
- `experiments/cost/study_rh7_analyse.py` — analysis (original `.venv`).
- `experiments/cost/h100_monitoring_summary.py` — RH7 added; queue regex fix.
- `results/cost/study_rh7/study_rh7_step0_h100nvl.json` — Step 0 records (token ids), verdict, amendment.
- `results/cost/study_rh7/study_rh7_requests_h100nvl.jsonl.gz` (requests), `…_metrics_…jsonl.gz` (1-s /metrics), `…_cpu_…jsonl.gz` (1-s CPU/GPU sampler), `…_run_meta_h100nvl.json` (servers, counters, memory timelines, estimate), `…_results_h100nvl.json` (analysis + decisions).
- `results/cost/h100_monitoring_summary.json` — regenerated.
