# StudyE10d-blocking: which part of a cold recall request blocks episodic scoring?

E-id: StudyE10d-blocking (`research/EXPERIMENTS.md`, pre-registered 2026-11-12). Host: h100nvl **GPU 2**, exclusive.

## 0. Question and design (recorded before running)

**Question.** StudyE10c (§6) found that each cold K1 RICH recall holds every episodic request that arrives during its prefill until the cold request's first token. Neither priority scheduling nor a 2,048-token step budget changes this. Which part of the cold request is the unsplittable unit?
- (a) client-to-engine handling of the ~40 MB body;
- (b) the vision-encoder pass over the video;
- (c) the language-model prefill of its ~11–12.6k tokens.

**Harness.** `study_e10d_blocking.py` imports `study_e10b_mixed.py` as E10c did. These are unchanged:
- `Episodic`, `run_cell`, the exclusivity monitor and the D7 open loop;
- the 30-s discard, 240-s window and 300-s drain cap;
- fresh server per cell.

What changes:
- **The cold request**, in four variants:

  | variant | cold request | isolates |
  |---|---|---|
  | V1 | E10c's cold K1 RICH request, PNG frames in the video data URL (≈ 40 MB) | control: must reproduce E10c within 2× |
  | V2 | the same npz frames, JPEG q88-encoded on the client (StudyE10a-full's encoder), same tokens, ≈ 6× smaller body | (a) |
  | V3 | text only: R1's question text plus seeded pseudo-word filler, token-matched to the K1 request's prompt-token count with the server's `/tokenize` (STOP if > 1 % off); no images; same sampling (temperature 0, max_tokens 4, seed) | (c) without (b) |
  | V4 | V1 with its encoder output already cached: sent once outside the window, prefix caching OFF so the LM prefill is recomputed | (b) without (c) — **only if** vLLM 0.31.0 keeps the encoder output (stage `reuse`) |

- **Logging only.**
  - `--enable-log-requests`.
  - A vLLM logging config with millisecond timestamps (`logs/e10d_vllm_logging.json`).
  - Each cold body carries a `request_id`.
  - The server log then gives, per cold request, "Received request" (after the API server rendered and preprocessed the body) and "Added request" (handed to the engine core). With the client's send and first-token times, that splits frontend from engine.
- **Engines:**
  - E0: E10c's E0 (defaults: chunked prefill on, `max_num_batched_tokens` 8192, fcfs);
  - E2: `--max-num-batched-tokens 2048`.
- **Condition C1:**
  - KV-GPU, k = 0, r = 0.05;
  - episodic N = 1 at 10 % (seed index 4) and 25 % (index 0) of 15.1 req/s;
  - cold seed 1000 + index;
  - cold questions in E10c's order. At most 15 per cell; 11 / 10 in the window at 10 % / 25 %.
- **Stages:**
  1. `prep` builds and token-matches the V3 prompts.
  2. `idle` times 5 sequential requests per variant on an idle E0 server, using the server log plus vLLM's per-request histogram deltas (queue, prefill = scheduled → first token, TTFT from frontend arrival).
  3. `reuse` (prefix caching off) sends a K1 request, the identical body again, then 20 episodic requests, then the body again. It tells whether the encoder output is reused and whether it survives.
  4. `run`: 12 cells (E0 / E2 × V1–V3 × 10 / 25 %), V1 first per engine with the control gate.
- **Estimated time:** about 2 h.

**Pre-registered reading.**
- A variant **blocks** iff its episodic p99 at 10 % exceeds the 0.45 s budget.
- V2 blocking like V1 means (a) is not the unit.
- V3 blocking means the LM prefill (c) is enough to block.
- V3 not blocking while V1 does means the encoder (b) is required.
- Release of the held episodic requests aligned with the cold *first token* rather than its *engine arrival* means engine-side, not frontend.

## 1. Mechanism verification (recorded BEFORE the sweep)

**Step 1, causal chain.**
- E10b / E10c measured that a cold K1 recall holds episodic requests until its first token. The scheduling literature (and FORMULATION's shared-replica cost) gives three places a single long request can hold others:
  - **(a)** the API server is busy receiving, parsing and preprocessing a 40 MB request (base64 decode of up to 256 PNG frames, HF video processor), delaying other requests' admission or streaming;
  - **(b)** the engine runs the vision encoder over the whole video item in one step;
  - **(c)** the engine spends consecutive steps on the cold request's LM prefill.
- **What vLLM 0.31.0's source says (read before the sweep, `vllm/v1/core/sched/scheduler.py`, `encoder_cache_manager.py`, `config/scheduler.py`):**
  - Each step schedules RUNNING requests first and only then WAITING ones (`# First, schedule the RUNNING requests` / `# Next, schedule the WAITING requests`).
  - `long_prefill_token_threshold` defaults to 0 (no cap), so a running cold prefill may take the whole per-step token budget (8,192 or 2,048) every step until it is done.
  - The encoder compute budget is `max(max_num_encoder_input_tokens, max_tokens_per_mm_item)`, so a whole video item is encoded in one step.
  - The encoder cache is 16,384 tokens (server log), about one K1 video.
- So (c) predicts that the chunk size changes the number of steps but not the hold, exactly as E10c saw. (b) predicts a hold only for the encoder step. (a) predicts the hold starts and ends with frontend events, not the first token.

**Step 2, instantiate each link.**

| link | implementing quantity | value / range in this run | varies as needed? | evidence |
|---|---|---|---|---|
| (a) frontend handling | cold body size; sent → 'Added request' time | V1 ≈ 40 MB vs V2 ≈ 6–7 MB; V3 ≈ 0.1 MB | yes, by variant | `body_mb`, server log |
| (b) vision-encoder pass | video item present (V1, V2) vs absent (V3); encoder output reused (V4) | present / absent | yes, by variant | prompt has a video item; reuse stage |
| (c) LM prefill length | prompt tokens | ≈ 11–12.6k in V1, V2, V3 (V3 matched within 1 %) | **constant across variants by design** — it is the controlled quantity, and E10c's chunk-size lever (8,192 vs 2,048) varies how it is stepped | /tokenize; `prompt_tokens` per row |
| episodic hold | episodic p99; fraction of slow episodic inside a cold window; release − cold first token | measured | to be measured | rows |

No link is ABSENT. Link (c) is CONSTANT across variants on purpose: V3 holds it fixed while removing (b) and shrinking (a).

**Step 3, trace one unit.** For one cold request per variant (loaded cell), the report gives:
- send, 'Received request', 'Added request' and first-token times;
- the episodic requests submitted around it, with TTFT and release relative to the cold first token (as E10c §6).

**Step 4, negative control.**
- Removing the cold request entirely is E10c's C0: episodic p99 0.23 s at 10 %, under budget. That is the null each blocking variant must depart from.
- V1 must reproduce E10c C1 at 10 % (E0 2.74 s, E2 2.95 s) and E10b C1 25 % (2.94 s) within 2×; otherwise STOP.

**Step 5, alternative explanation.**
- A V2 or V3 difference could come from something other than the targeted link:
  - V2 also changes pixel values, which do not affect the token count or the compute;
  - V3 changes attention content, but prefill cost depends on length.
- The idle phase timing gives each variant's frontend, queue and prefill durations, so a variant that blocks less can be checked against a shorter phase.
- If V3 blocks but holds episodic requests for a shorter time than V1, the encoder adds to the hold rather than causing it. Release-time alignment and idle prefill durations separate "unit" from "duration".

## 2. Run (2026-11-12 09:05 → 10:34)

- **Stages:** `prep`, then `idle` (done 09:20), then `reuse` (09:20–09:22), then `run` (09:22:52–10:34:33, 12 cells). Chain log: `logs/e10d_chain.log`. The whole run took about 1.5 h, inside the 2-h estimate.
- **Exclusivity:** 172 monitor samples; foreign process on GPU 2 in 0, our processes outside the job in 0. Not VOID.
- **V3 token match:** 15 / 15 cold questions match their K1 prompt-token count exactly (diff 0, worst relative 0.0). In every run cell, every cold request's `prompt_tokens` equals its expected count (V1 / V2 / V3 alike), and `cached_tokens` is 0.
- **Control gate (V1):** PASS in all three cells:

  | cell | p99 | reference | ratio |
  |---|---|---|---|
  | E0 10 % | 2.974 s | E10c E0 C1 2.739 s | 1.09 |
  | E0 25 % | 3.168 s | E10b C1 2.942 s | 1.08 |
  | E2 10 % | 2.919 s | E10c E2 C1 2.947 s | 0.99 |

- **Server logs:** every cold request was found in the server log ("Received request" and "Added request"), 15 / 15 at 10 % and 11 / 11 at 25 %, in all 12 cells.
- **V4 skipped.** The `reuse` stage (prefix caching OFF, E0 idle server, 3 questions) measured the engine prefill time (scheduled → first token):

  | request | prefill p50 | per question |
  |---|---|---|
  | A1, first K1 request | 2.43 s | 2.45 / 2.43 / 2.32 |
  | A2, identical body immediately after | 2.23 s | 2.23 / 2.26 / 2.13 |
  | A3, identical body after 20 episodic requests | 2.42 s | 2.42 / 2.47 / 2.34 |

  - vLLM 0.31.0 does reuse the encoder output for an immediate repeat: A1 − A2 = 0.19 s, which matches the idle V1 − V3 prefill difference of 0.22 s.
  - The reuse does not survive 20 episodic requests: A1 − A3 = −0.02 s. The encoder cache is 16,384 tokens, about one K1 video, and freeable entries are evicted LRU.
  - So V4 as specified (sent once outside the window, then the copy inside it) would recompute the encoder in every cell. V4 cannot be built without code changes and is **skipped**.
  - The A1 − A2 saving is still a direct measurement of (b)'s duration: **≈ 0.2 s**.

## 3. Idle phase timing (E0, idle server, 5 sequential requests per variant, medians)

All three variants have 12,645 prompt tokens (median) and queue time 0.

| variant | body | sent → 'Received' (render) | sent → 'Added' (frontend) | 'Added' → first token | vLLM prefill (scheduled → first) | vLLM TTFT (frontend arrival → first) | client TTFT |
|---|---|---|---|---|---|---|---|
| V1 PNG | 50.5 MB | 1.462 s | 1.466 s | 2.468 s | 2.390 s | 3.814 s | 3.977 s |
| V2 JPEG q88 | 8.2 MB | 0.751 s | 0.754 s | 2.452 s | 2.356 s | 3.195 s | 3.234 s |
| V3 text | 0.036 MB | 0.035 s | 0.038 s | 2.190 s | 2.171 s | 2.219 s | 2.233 s |

Phases of one cold RICH recall:
- **Frontend (a):** 1.47 s for the PNG body and 0.75 s for JPEG. This covers the upload, base64 decode and HF video processing in the API server, and it scales with the body.
- **Vision encoder (b):** about 0.2 s. Measured two ways: V1 − V3 prefill is 0.22 s, and the reuse saving A1 − A2 is 0.19 s.
- **LM prefill (c):** about 2.17 s, the V3 prefill, i.e. about 5.8k tok/s.

The engine-side hold candidate (b + c) is therefore about 2.4 s, and (c) is about 90 % of it.

(The idle summary from the run stage, before the log-matching fix, listed the body as "44 MB". 50.5 MB is the measured `body_mb` of the request bodies, the same quantity E10c described as "≈ 40 MB".)

## 4. Per-variant results (episodic N = 1, C1, budget 0.45 s)

| engine | variant | level | episodic n | p50 | p99 | blocks? | cold body | cold frontend p50 | cold 'Added' → first p50 | cold TTFT p50 |
|---|---|---|---|---|---|---|---|---|---|---|
| E0 | V1 PNG | 10 % | 383 | 0.145 | **2.974** | **yes** | 50.3 MB | 1.51 s | 2.48 s | 4.04 s |
| E0 | V2 JPEG | 10 % | 383 | 0.146 | **3.523** | **yes** | 8.2 MB | 0.84 s | 2.52 s | 3.35 s |
| E0 | V3 text | 10 % | 383 | 0.144 | **2.571** | **yes** | 0.036 MB | 0.04 s | 2.20 s | 2.23 s |
| E0 | V1 PNG | 25 % | 998 | 0.153 | 3.168 | yes | 50.3 MB | 1.52 s | 2.68 s | 4.28 s |
| E0 | V2 JPEG | 25 % | 998 | 0.155 | 3.178 | yes | 8.2 MB | 0.86 s | 2.66 s | 3.49 s |
| E0 | V3 text | 25 % | 998 | 0.150 | 2.246 | yes | 0.036 MB | 0.04 s | 2.23 s | 2.30 s |
| E2 | V1 PNG | 10 % | 383 | 0.146 | **2.919** | **yes** | 50.3 MB | 1.56 s | 2.56 s | 4.24 s |
| E2 | V2 JPEG | 10 % | 383 | 0.146 | **3.172** | **yes** | 8.2 MB | 0.85 s | 2.55 s | 3.41 s |
| E2 | V3 text | 10 % | 383 | 0.146 | **2.594** | **yes** | 0.036 MB | 0.04 s | 2.29 s | 2.32 s |
| E2 | V1 PNG | 25 % | 998 | 0.156 | 3.192 | yes | 50.3 MB | 1.58 s | 2.76 s | 4.31 s |
| E2 | V2 JPEG | 25 % | 998 | 0.154 | 3.262 | yes | 8.2 MB | 0.88 s | 2.81 s | 3.67 s |
| E2 | V3 text | 25 % | 998 | 0.151 | 2.203 | yes | 0.036 MB | 0.04 s | 2.42 s | 2.50 s |

All latencies are in seconds. Across all 12 cells: 0 episodic errors, 0 cold errors, every cold prompt token-exact.

**Hold analysis (E10c §6 method).**
- "Slow" means an episodic TTFT above 0.45 s.
- "Inside" means submitted in [cold sent, cold first token].
- "Release − cold first" is the slow request's first token minus the nearest cold first token.

| cell | slow | inside a cold window | release − cold first, p10 / p50 / p90 | slow submitted > 0.2 s before cold 'Added' | episodic submitted in the cold frontend phase*: n / slow |
|---|---|---|---|---|---|
| E0 V1 10 % | 43 | 42 | 0.00 / 0.18 / 0.43 | 1 | 19 / 5 |
| E0 V2 10 % | 44 | 44 | 0.00 / 0.09 / 0.30 | 11 | 15 / 13 |
| E0 V3 10 % | 26 | 26 | 0.00 / 0.20 / 0.26 | 0 | 0 / 0 |
| E0 V1 25 % | 111 | 106 | 0.00 / 0.23 / 0.52 | 20 | 45 / 20 |
| E0 V2 25 % | 114 | 110 | 0.00 / 0.25 / 0.64 | 15 | 18 / 15 |
| E0 V3 25 % | 68 | 64 | 0.21 / 0.39 / 0.54 | 0 | 0 / 0 |
| E2 V1 10 % | 44 | 44 | 0.00 / 0.13 / 0.44 | 2 | 20 / 6 |
| E2 V2 10 % | 44 | 44 | 0.00 / 0.09 / 0.26 | 12 | 16 / 14 |
| E2 V3 10 % | 26 | 26 | 0.00 / 0.00 / 0.16 | 0 | 0 / 0 |
| E2 V1 25 % | 108 | 101 | 0.00 / 0.34 / 0.67 | 18 | 46 / 18 |
| E2 V2 25 % | 118 | 111 | 0.00 / 0.34 / 0.67 | 14 | 17 / 14 |
| E2 V3 25 % | 66 | 64 | 0.00 / 0.13 / 0.34 | 0 | 0 / 0 |

\* "Frontend phase" means submitted in [cold sent, cold 'Added' − 0.2 s]. Source: `e10d_results.json` (`cells.*.hold`).

Readings:
- **Slow requests sit inside cold windows.** 94–100 % of slow episodic requests were submitted inside a cold window (V3 98–100 %).
- **They are released at the cold first token.** Release follows the cold first token by a median of 0.0–0.4 s, which is the time to drain the held batch.
- **V3 has no frontend phase, yet blocks.** Its 0.04-s frontend means every slow V3 request was submitted after the cold request reached the engine (min submit − 'Added' = −0.03 s, i.e. essentially at arrival).
- **A secondary frontend effect for V1 / V2** (the counts are `hold.submitted_in_cold_frontend_phase`, `hold.of_which_slow` and `hold.slow_submitted_over_0p2s_before_cold_added`): episodic requests submitted during the *last ~0.7 s* of the cold frontend phase are also held. The slow ones in that phase were submitted 0.27–0.69 s before 'Added'. Requests submitted earlier in the V1 frontend, during the upload and decode, are not held (V1 10 %: 14 / 14 that completed before 'Added' were within budget).
  - The 0.7 s matches the cold request's render step: the API server's HF video processing, which is about all of V2's 0.75-s frontend.
  - It extends the cold window by up to ~0.7 s. It does not create a hold of its own: the held requests are still released at the cold first token, not at 'Added'.

**Step 3 trace (E0, 10 %, the cold request in each cell with the most episodic arrivals during its engine phase; `e10d_results.json` `cells.*.trace`).** Times are relative to the cold send. Episodic entries read: submitted → TTFT (release − cold first token).

| variant | 'Received' | 'Added' | cold first token | episodic submitted → TTFT (release − cold first) |
|---|---|---|---|---|
| V1 | 1.181 | 1.184 | 3.261 | −0.36 → 0.15 (before); +0.22 → 0.15 (done before cold 'Added'); +0.64 → **2.63** (+0.00); +1.48 → **2.21** (+0.43); +1.53 → **2.18** (+0.43); +1.67 → **2.02** (+0.43); +1.70 → **1.99** (+0.43); +2.36 → **1.33** (+0.43); +2.84 → **0.86** (+0.44); +2.90 → **0.81** (+0.45); +3.30 → **0.47** (+0.51) |
| V2 | 0.857 | 0.862 | 5.027 | +0.74 → **4.29** (+0.00); +1.01 → **4.02** (+0.00); +3.48 → **1.68** (+0.13); +3.95 → **1.21** (+0.13); +4.09 → **1.24** (+0.30); +4.25 → **1.09** (+0.30); +4.49 → **0.84** (+0.30); +5.41 → 0.15 (after) |
| V3 | 0.027 | 0.029 | 1.718 | −0.36 → 0.16 (before); +0.22 → **1.62** (+0.13); +0.63 → **1.21** (+0.13); +1.48 → **0.50** (+0.26); +1.51 → **0.46** (+0.26); +1.67 → 0.43 (+0.38); +1.70 → 0.39 (+0.38) |

What the traces show:
- **Released at the cold first token.** Every episodic request submitted while the cold request was in the engine got its first token 0.0–0.5 s after the cold first token. That holds whatever the variant, so whatever the body size and whether or not there is a vision encoder.
- **Submitted before 'Added' but held anyway.** The V1 +0.64 s and V2 +0.74 / +1.01 s requests arrived *before* the cold request reached the engine. They were still released exactly at the cold first token (+0.00), so they too were held by the engine phase.
  - The V1 +0.22 s request finished normally, before the cold request reached the engine.
  - This is the secondary frontend effect above.
- **The V2 cold request here took 4.2 s in the engine** (vs 2.5 s typical). The previous cold request (sent 0.77 s earlier; engine arrival +0.07 s, first token +2.60 s) was still prefilling, so the two prefills ran back to back. That is why this request had the most arrivals and the longest hold. It is two units in series, not a different mechanism.

## 5. Engine check (documentation only; no option used in any cell)

Sources:
- vLLM 0.31.0 `vllm serve --help=all` (saved in the run's scratch notes);
- source `vllm/v1/core/sched/scheduler.py`, `vllm/config/scheduler.py`, `vllm/v1/core/encoder_cache_manager.py`;
- docs at https://docs.vllm.ai/en/v0.31.0/.

| capability | supported in 0.31.0? | flags | reference |
|---|---|---|---|
| Encoder disaggregation (encoder on separate instances, encoder outputs shipped to the LM instance: "EPD") | **Yes** | `--ec-transfer-config '<json>'` (ECTransferConfig: connector, role producer / consumer); `--mm-encoder-only` (run only the multimodal encoder) | https://docs.vllm.ai/en/v0.31.0/api/vllm/config/#vllm.config.ECTransferConfig ; `vllm serve --help=all` |
| Data-parallel vision encoder within one server | Yes (not disaggregation) | `--mm-encoder-tp-mode {weights,data}` | `vllm serve --help=all` |
| Chunked vision-encoder execution (encode a video item over several steps) | **No** | none. The encoder compute budget is `max(max_num_encoder_input_tokens, max_tokens_per_mm_item)`, so a whole item is encoded in one step | `scheduler.py`, `config/scheduler.py` |
| Chunked scheduling of a multimodal item's LM prefill (split the item's placeholder tokens across steps) | Yes, on by default | `--disable-chunked-mm-input` turns it **off** (all-or-nothing per item) | `vllm serve --help=all` |
| Capping one long prefill's share of each step | Yes, **off by default** (`0`) | `--long-prefill-token-threshold N`, `--long-prefill-token-threshold-adaptive`; with `--max-num-partial-prefills` / `--max-long-partial-prefills` | `config/scheduler.py`; `vllm serve --help=all` |
| Encoder-output cache across requests | Yes, 16,384 tokens here, LRU on freeable entries | `--mm-processor-cache-gb` / `--mm-processor-cache-type` control the *processor* cache, not the encoder cache | server log; §2 reuse test |

**Answer.**
- vLLM 0.31.0 does support encoder disaggregation (`--ec-transfer-config` + `--mm-encoder-only`). It does **not** support chunked vision-encoder scheduling: a video item is encoded in one step.
- By §4 neither would remove the hold: the encoder is about 0.2 s of a 2.4-s engine phase, and the hold is present without any encoder (V3).
- The scheduler lever aimed at the measured unit, a long LM prefill taking each step's whole token budget while running requests are scheduled first, is `--long-prefill-token-threshold`. It was **not tested** here (out of scope by the spec). It is the obvious next engine experiment.

## 6. Consistency protocol (6 checks)

1. **Cross-check against committed measurements.** PASS.

   | quantity | this run | prior | source | ratio | agree |
   |---|---|---|---|---|---|
   | C1 episodic p99, E0 N1 10 % (V1) | 2.974 s | 2.739 s | E10c | 1.09 | yes |
   | C1 episodic p99, E2 N1 10 % (V1) | 2.919 s | 2.947 s | E10c | 0.99 | yes |
   | C1 episodic p99, E0 N1 25 % (V1) | 3.168 s | 2.942 s | E10b | 1.08 | yes |
   | episodic p50, N1 | 0.144–0.156 s | 0.14–0.15 s | E10c / D7 | ≈ 1.0 | yes |
   | cold K1 TTFT p50 (V1, E0) | 4.04 s (10 %), 4.28 s (25 %) | 4.05 s / 4.15 s | E10c / E10b | 1.00 / 1.03 | yes |
   | K1 prompt tokens (median) | 12,645 | 12,645 | E10b parity gate | 1.00 | yes |
   | V2 JPEG q88 body vs PNG | 8.2 vs 50.3 MB (0.16×) | 5.5 vs 33.4 MB (0.16×, RECENT q88) | E10a-jpeg | 1.0 | yes |

2. **Physical plausibility.** PASS.
   - LM prefill of 12,645 tokens: 2.17 s idle (V3), i.e. ≈ 5.8k tok/s on one H100 for the 32B model. That is a prefill-only rate, consistent with the ≈ 3k tok/s E10c quoted for the whole 4-s cold TTFT including the frontend, and nothing is faster than the committed curves.
   - Vision encoder ≈ 0.2 s for a 256-frame video (two independent estimates: 0.22 s, 0.19 s).
   - Frontend: 50 MB in 1.47 s ≈ 34 MB/s including base64 decode and HF processing on one API-server process, which is plausible for CPU-bound work.
   - `cached_tokens` is 0 for every cold request (no prefix-cache artifact; the V3 filler is seeded per question).
3. **Distribution sanity.** PASS.
   - p99 differs across variants and levels (2.20–3.52 s). The idle per-request values vary:
     - V1 prefill 2.32–2.45 s;
     - frontend per request listed in `e10d_results.json` `idle.*.frontend_all`.
   - No constants where distributions are expected. The prompt-token equality (exact) is by construction: V3 is token-matched and V1 / V2 share frames, so tokens are equal.
   - The V2 E0 10 % p99 (3.52 s) is above V1's (2.97 s) although V2's frontend is shorter. That is within the spread produced by back-to-back cold requests (the §4 trace shows a 4.2-s engine phase from two prefills in series) at 383 episodic requests. p99 is the 4th-highest value, so a single overlap moves it.
4. **Definition audit.** PASS.
   - Budget 0.45 s, peak 15.1 req/s, window (30-s discard, 240 s), drain cap 300 s, C1 = (KV-GPU, k 0, r 0.05), and the seeds are E10b / E10c's.
   - "Blocks" = p99 at 10 % > 0.45 s (pre-registered).
   - "Slow", "inside" and "release" are E10c §6's definitions.
   - New names, defined in §0 and §4:
     - frontend = sent → 'Added request';
     - render = sent → 'Received request';
     - frontend phase = [sent, 'Added' − 0.2 s].
   - Note: vLLM's own `time_to_first_token_seconds` histogram measures from frontend arrival, not from the client send; it is reported as "vLLM TTFT", distinct from the client TTFT.
5. **Claim linkage.**
   - FORMULATION's shared-replica cost, i.e. whether recall can share a replica with episodic scoring. E10b / E10c found it cannot, under any scheduler setting.
   - This run **strengthens** that conclusion and locates its cause: the long LM prefill alone is enough. So any recall whose prompt is ~12k tokens blocks episodic scoring for its prefill duration, whatever the modality, body size or encoder placement.
   - It **weakens** two candidate mitigations: shrinking the body (JPEG / E10a), and encoder disaggregation.
   - It leaves admission control, a separate replica, or a per-step prefill cap (`--long-prefill-token-threshold`, untested) as the candidates.
6. **Proxy validity.**
   - Episodic p99 TTFT is the direct quantity.
   - V3 is a proxy for "K1 without its encoder". It is valid for prefill *cost*, because it has the same token count and the same max_tokens, and prefill cost depends on length. It is not valid for attention *content*, which does not affect the timing claim.
   - The 'Received' / 'Added' log lines are vLLM's own request-lifecycle logs. They are accurate to the logger's millisecond timestamp and are written from the same host clock as the client (one machine).
   - The secondary frontend effect (§4) is an inference from submit and release timing (held until the cold *first token*, not released at 'Added'). It is not a direct measurement of the API-server event loop, and is labelled as such.

**Result: PASS 6 / 6.**

## 7. Verdict

**Which variants block?** All of them, on both engines.

| engine | V1 PNG | V2 JPEG | V3 text-only, token-matched | V4 encoder-cached |
|---|---|---|---|---|
| E0 | **blocks** (2.97 s) | **blocks** (3.52 s) | **blocks** (2.57 s) | skipped: not buildable without code changes (§2) |
| E2 (2,048) | **blocks** (2.92 s) | **blocks** (3.17 s) | **blocks** (2.59 s) | skipped |

These are episodic p99 values at 10 %, against a 0.45-s budget.

**The unsplittable unit is (c), the language-model prefill.** By the pre-registered reading:
- **V2 blocks like V1**, so (a), the client-to-engine handling of the 40–50 MB body, is not the unit.
  - It does contribute a secondary effect: episodic requests arriving during the last ~0.7 s of the cold request's API-server processing are delayed into the engine phase and then held. That stretches the exposure window but is not the hold itself.
- **V3 blocks** with no image, no vision encoder and a 0.036 MB body, so (c), a 12.6k-token LM prefill, is sufficient. Its idle duration is 2.17 s of the 2.39-s engine phase.
- **Release is aligned with the cold first token** (median 0.0–0.4 s after, p90 ≤ 0.67 s) in all 12 cells, not with its engine arrival. So the hold is engine-side.
- **(b), the vision encoder, is not required.** It adds ≈ 0.2 s to the hold: V3's p99 is 0.33–1.06 s lower than V1 / V2's across the 8 comparisons, and V3 has 26 slow episodic requests at 10 % against V1's 43–44.
- **Chunk size does not split the unit:** E2 = E0 within noise for every variant, so a 2,048-token step budget does not shorten the hold. This is consistent with the source reading (Step 1): RUNNING requests are scheduled first, and the long-prefill threshold defaults to 0, so a running prefill takes the whole step budget each step.

**Rule 2 classification: real finding, mechanism present and exercised.**
- Every link was instantiated and varied as designed: body 50.3 / 8.2 / 0.036 MB, encoder present / present / absent, LM prefill constant at 12,645 tokens.
- The control reproduced E10c / E10b (ratios 0.99–1.09).
- Nothing was VOID.

**Implication.**
- Neither JPEG transport nor encoder disaggregation (`--ec-transfer-config` / `--mm-encoder-only`, which vLLM 0.31.0 supports) would restore episodic capacity on a shared replica.
- Chunked vision-encoder scheduling does not exist in 0.31.0, and the encoder is not the unit anyway.
- The remaining in-engine candidate is `--long-prefill-token-threshold`, which caps a running long prefill's per-step tokens so waiting requests are scheduled alongside it. It is untested.
- Otherwise cold recall needs its own replica or admission control (E10b / E10c).
