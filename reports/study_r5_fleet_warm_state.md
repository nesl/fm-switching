# StudyR5 — a cloud fleet with warm per-device history: escalation latency and warm-state capacity

**Host:** h100nvl (`sn4622120321`), **GPU 3**, exclusive (session watchdog; only our processes ever appeared) ·
**Run:** sweep 2026-10-17 16:30 → 23:26, FP8 23:28 → 2026-10-18 00:29 · **Pre-registered:** `research/EXPERIMENTS.md`
row StudyR5, written before any R5 GPU run. **Systems construction; accuracy not measured.**

**Stack:** vLLM 0.31.0+cu129, torch 2.13.0+cu129 (venv `~/.venvs/fm-switching-vllm`), Qwen3-VL-32B-Instruct
@`0cfaf481`. Server settings, as StudyX:
- FLASH_ATTN (FA3), CUDA graphs;
- `gpu_memory_utilization` 0.90, `max_model_len` 32,768;
- **prefix caching ON**;
- `--enable-prompt-tokens-details` (per-request `cached_tokens`);
- ≤ 640 images per prompt, image processor bounds 4,096–20,480 px (frames are not rescaled), localhost-bound.

**KV capacity (startup log): 65,280 tokens in bf16, 130,720 tokens with `--kv-cache-dtype fp8`** (2.00×; 15.94 /
15.96 GiB available).

## Answers

1. **Warm state works while it fits.**
   - At D = 1–8, P-WARM escalations hit the prefix cache on 94–97% of their prompt tokens. P-COLD gets 53–61%
     (from the device's own previous escalations) and only 9–10% when escalations are sparse.
   - Median escalation TTFT is **0.32–0.38 s (WARM) vs 0.53–0.68 s (COLD)**, and p99 is 0.8–1.0 s vs 1.1–2.8 s.
   - At 20% escalation (D=8), WARM gives 0.54 s vs COLD 1.47 s median.
2. **Keeping it warm is cheap in latency terms but costs compute when escalations are rare.**
   - Appends are 89–99% of all computed prompt tokens under P-WARM.
   - With every question escalating, total computed tokens are about the same as P-COLD (D=8: 199 vs 209 tok/s),
     because COLD re-prefills what WARM appended.
   - At 20% escalation, WARM computes **3×** more (186 vs 61 tok/s).
3. **Capacity: warm state collapses between D = 8 and 16 in bf16, and between 16 and 32 with FP8.**
   - In both cases the trigger is the combined history working set outgrowing the KV cache.
   - Once appends miss, they re-prefill whole histories. The server then cannot keep up with the append stream, and
     escalations queue behind it.
   - **At D=32, P-WARM is catastrophically worse than P-COLD:** median escalation TTFT 637 s vs 1.7 s, with 1,823
     requests in flight at the window's end and a 22-minute drain.
4. **D\*** (pre-registered: smallest D where P-WARM's escalation token hit rate < 50%) **= 32 in bf16.**
   - The hit rate at D=16 is still 0.71, but the **latency knee is at D=16**: TTFT median 8.6 s, p90 81 s, with 43
     preemptions.
   - The server-wide prefix hit rate, which includes appends, is already 0.41 at D=16.
   - The token-hit criterion understates the collapse, because escalations that do get served often find their
     prefix while the appends ahead of them have missed.
5. **FP8 KV doubles capacity and moves the knee by one D step.**
   - At FP8 D=16: escalation hit 0.95, TTFT median 0.53 s, p99 2.3 s, no preemptions. In bf16 the same D gave 0.71,
     8.6 s and 161 s.
   - At FP8 D=32 it collapses as well (hit 0.66, median TTFT 342 s).

## Design (as pre-registered; one disclosed change)

**History:**
- frames at 1 fps from session start, each a separate image in time order;
- fixed **160×128** (H×W; 128×160 for landscape);
- **22 tokens/frame** (20 visual + 2 delimiters; probe-verified), so 10 minutes = **13,200 tokens**;
- a cell / device / session text header leads each prompt, so prefixes are never shared across devices or cells.

**Devices:**
- D distinct S-EMBER sessions from the 845-question pool (234 videos shuffled with seed 0, dealt round-robin; each
  device chains its own videos). A session runs to its last question.
- **Replay is 1× (real time).** This changed from the 10× I proposed earlier, before running and recorded in the
  pre-registration: at 10× the D=32 append stream (about 32 requests/s, each resending up to 600 images) would make
  API-side image preprocessing the bottleneck instead of KV.
- Each device starts at a seeded uniform offset into its first session, and its real questions arrive at their
  `question_time`.

**Policies:**
- **P-COLD:** no uploads; each escalation sends header + all frames so far + question.
- **P-WARM:** an append every 10 s of session time (all frames so far, `max_tokens` 1) plus escalations.
- Escalations are greedy with `max_tokens` 4.

**Window:** 15 minutes of wall time after warm-up. P-WARM's warm-up uploads each device's history up to its offset;
it takes 0.4–26 s and is not measured. Requests submitted inside the window are measured, then everything drains.

## Results (every cell one repetition, except WARM D=8 ×2)

| cell | escalations | escalation token hit | server prefix hit | escalation TTFT median / p90 / p99 / max (s) | preemptions | KV max (active) | appends (share of computed tokens) | computed prompt tok/s | in flight at window end / drain |
|---|---|---|---|---|---|---|---|---|---|
| COLD D1 | 14 | 0.61 | 0.60 | 0.53 / 1.00 / 1.09 / 1.11 | 0 | 0% | — | 26 | 1 / 1 s |
| **WARM D1** | 14 | **0.94** | 0.95 | **0.32** / 0.44 / 0.76 / 0.80 | 0 | 0% | 89 (0.85) | 25 | 1 / 1 s |
| COLD D2 | 23 | 0.61 | 0.61 | 0.56 / 1.03 / 1.43 / 1.51 | 0 | 15% | — | 46 | 1 |
| WARM D2 | 23 | 0.95 | 0.95 | 0.36 / 0.50 / 0.81 / 0.82 | 0 | 8% | 179 (0.88) | 51 | 1 |
| COLD D4 | 38 | 0.55 | 0.54 | 0.63 / 1.31 / 1.75 / 1.90 | 0 | 0% | — | 98 | 1 |
| WARM D4 | 38 | 0.95 | 0.95 | 0.38 / 0.61 / 0.81 / 0.85 | 0 | 10% | 356 (0.89) | 100 | 1 |
| COLD D8 | 76 | 0.53 | 0.54 | 0.68 / 1.35 / 2.78 / 2.95 | 0 | 19% | — | 209 | 1 |
| **WARM D8** | 76 | **0.95** | 0.95 | **0.38** / 0.76 / 1.00 / 1.00 | 0 | 19% | 711 (0.89) | 199 | 1 |
| WARM D8 rep 2 (seed 1) | 72 | 0.96 | 0.95 | 0.52 / 0.77 / 0.99 / 1.21 | 0 | 15% | 713 (0.90) | 197 | 1 |
| COLD D16 | 146 | 0.38 | 0.37 | 0.77 / 2.39 / 3.75 / 4.40 | 0 | 26% | — | 535 | 2 / 1 s |
| **WARM D16** | 147 | 0.71 | **0.41** | **8.64 / 80.9 / 161 / 167** | **43** | **97%** | 1,423 (0.95) | **5,227** | **154 / 171 s** |
| COLD D32 | 266 | 0.11 | 0.11 | 1.70 / 5.28 / 15.5 / 18.6 | 0 | 39% | — | 1,470 | 5 / 6 s |
| **WARM D32** | 266 | 0.20 | 0.09 | **637 / 1,283 / 1,454 / 1,492** | 1 | 94% | 2,791 (0.91) | 14,237 | **1,823 / 1,331 s** |
| COLD D8, 20% escalate | 9 | 0.09 | 0.09 | 1.47 / 4.07 / 5.09 / 5.20 | 0 | 19% | — | 61 | 1 |
| WARM D8, 20% escalate | 9 | 0.97 | 0.95 | 0.54 / 0.79 / 1.07 / 1.10 | 0 | 10% | 711 (0.99) | 186 | 1 |
| COLD D32, 20% escalate | 46 | 0.10 | 0.10 | 0.98 / 2.47 / 4.61 / 4.96 | 0 | 20% | — | 242 | 0 |
| WARM D32, 20% escalate | 46 | 0.08 | 0.04 | 606 / 1,292 / 1,443 / 1,445 | 0 | 62% | 2,798 (0.98) | 13,686 | 1,681 / 1,330 s |
| **FP8** WARM D8 | 76 | 0.95 | 0.95 | 0.42 / 0.88 / 1.29 / 1.46 | 0 | 6% | 711 (0.89) | 198 | 1 |
| **FP8** WARM D16 | 147 | **0.95** | **0.95** | **0.53** / 1.16 / 2.26 / 2.72 | **0** | 22% | 1,423 (0.90) | 397 | 2 / 1 s |
| **FP8** WARM D32 | 267 | 0.66 | 0.37 | 342 / 828 / 964 / 993 | 0 | 55% | 2,797 (0.95) | 10,974 | 1,493 / 910 s |

**Column notes:**
- **"Escalation token hit"** = Σ `cached_tokens` / Σ `prompt_tokens` over in-window escalations.
- **"Server prefix hit"** = the prefix-cache hits/queries counter delta over the window. It includes appends.
- **"KV max (active)"** is vLLM's `kv_cache_usage_perc`, which counts blocks held by running requests only. Idle
  cached prefixes don't show in it.

**Append cost, beyond the table:**
- Append latency summed over the window was 258 s at WARM D8 (about 0.33 s median per append, prompt median 4,236
  tokens, append hit 0.95).
- At WARM D16 the median append took 16 s (append hit 0.33), and at D32, 711 s.
- Escalation arrival rates are identical between policies (open-loop real questions): 0.9–17.7 per minute.

## Mechanism verification

1. **Causal chain** (FORMULATION.md: reconstruction cost grows with context length; tier capacity is a memory
   budget).
   - A warm prefix in the cloud's KV means an escalation prefills only new tokens, which lowers TTFT.
   - The sum of warm histories is bounded by KV capacity. Past it, LRU eviction drops warm prefixes, appends miss,
     and the misses re-prefill whole histories.
   - That load queues escalations behind it.
2. **Instantiated quantities.**

   | link | quantity | value / range | varies as claimed? |
   |---|---|---|---|
   | warm prefix reused | escalation `cached_tokens` / prompt | 0.94–0.97 (WARM D ≤ 8) vs 0.53–0.61 (COLD) | yes |
   | less prefill → lower TTFT | escalation TTFT median | 0.32–0.38 vs 0.53–0.68 s | yes |
   | capacity bound | KV tokens | 65,280 (bf16) / 130,720 (FP8) | yes, by flag |
   | eviction past capacity | append hit rate | 0.95 (D8) → 0.33 (D16) → 0.12 (D32); FP8 0.95 at D16 | yes |
   | re-prefill load | computed prompt tok/s | 199 (D8) → 5,227 (D16) → 14,237 (D32) | yes |
   | queueing | waiting max / preemptions | 0 → 145 / 43 (D16) → 999 (D32) | yes |

3. **Mechanism check (pre-registered, before the sweep continued).**
   - At D=1, P-WARM's escalation token hit was 0.94, and its median TTFT 0.32 s vs COLD 0.53 s → **passed**.
   - At the largest D (32), hits dropped to 0.20 (escalations) and 0.09 (server).
4. **Negative and positive controls.**
   - P-COLD at the same D has the mechanism absent: no appends, so no warm state to lose. It shows no collapse
     (D=32 median TTFT 1.7 s).
   - FP8 doubles KV at the same request load. The collapse moves from D=16 to D=32, which isolates **KV capacity**
     as the trigger rather than request rate.
5. **Alternative explanation.** The collapse could be pure compute overload from the append request rate (3.2/s
   at D=32), regardless of KV.
   - Against it: at FP8 D=16 the append rate is the same as bf16 D=16 (1,423 appends), and FP8 shows no collapse
     (hits 0.95, 397 tok/s computed).
   - What breaks first is cache residency. Compute overload follows from the misses and amplifies them.

## Results consistency check

1. **Cross-check against committed measurements.**

   | quantity | StudyR5 | prior | source | ratio |
   |---|---|---|---|---|
   | KV tokens (bf16) | 65,280 | 62,944 | StudyX (different multimodal limits change the profiling reservation) | 1.04 |
   | tokens/frame | 22.0 | 22 (design) | probe | 1.00 |
   | TTFT for a ~12.6k-token cold multimodal prompt | — | 4.2 s | StudyR1 single-request | — |

   R5's COLD escalation prompts (median 3.8–5.2k tokens, 53–61% cached) take 0.5–0.7 s TTFT. That is consistent
   with R1's 4.2 s for 12.6k uncached tokens: a smaller and mostly cached prefill.
2. **Physical plausibility.**
   - The fastest WARM TTFT (0.32 s) prefills about 5% of a ~3.8k prompt (about 200 tokens) plus decode setup.
   - Computed throughput peaks around 14k tok/s at D=32, within an H100's 32B prefill rate. That is the saturation
     point.
3. **Distribution sanity.** All cells report full distributions. The two WARM D8 repetitions differ by 0.14 s in
   median TTFT (0.38 vs 0.52 s) at the same hit rate, which is the run-to-run spread.
4. **Definitions.** As pre-registered:
   - "escalation token hit" (per-request `cached_tokens`) and "server prefix hit" (vLLM counters);
   - window = 15 minutes after warm-up, with in-window submits measured.
5. **Claim linkage.**
   - **Supports:** a shared cloud tier holding devices' histories warm cuts escalation latency only within a
     KV-capacity budget of about (KV tokens ÷ mean resident history) devices: here about 8–16 in bf16 and 16–32 in
     FP8.
   - **Beyond the budget, unmanaged warm-keeping is worse than none.** This is the warm-state analogue of StudyX's
     externality: residents' appends crowd out escalations.
6. **Proxy validity.**
   - Fixed-resolution image histories are a systems construction for token volume. They are not the R1 input
     format, and accuracy is not measured.
   - `cached_tokens` is vLLM's own accounting of prefix reuse, not a proxy.

## Caveats

- **One repetition per cell** (WARM D8 ×2). The spread of D8 median TTFT across reps is 0.14 s.
- **640-image limit.** One pool session is 20 minutes long (`9902221866524366`, 1,200 s). It exceeded the
  640-image-per-prompt limit, so its later appends and escalations were rejected with HTTP 400 in the D=32 cells:
  41 appends plus 4–5 escalations or warm-ups per cell. Rejections are immediate and add no GPU load, so they
  slightly *understate* D=32 load. 8–10 more requests per D=32 cell failed with connection `ReadError`s under
  overload.
- **The D=16 and D=32 WARM cells were not in steady state.** Queues grew throughout the window, so their latency
  figures depend on the window length (15 min). The direction is not in doubt.
- **No admission control or append shedding was tested.** The collapse is that of *unmanaged* appends; a policy
  that drops appends under pressure would behave differently.
- **Real-time replay (1×), not the 10× first proposed** (see Design).
- **The first, crashed attempt** (13:00–13:14: COLD D1 completed, then a bookkeeping crash) is kept as
  `study_r5_*_attempt1_crash_h100nvl.jsonl`. It was re-run cleanly.
- **The sweep paused 17:00–18:50** after a session-loading bug: string matching on a compacted manifest. Both D=1
  cells had loaded sessions before the bug and are valid. The sweep resumed from COLD D2.

## Files

- **Code (`experiments/cost/`):**
  - `study_r5_fleet.py` (vLLM venv)
  - `study_r5_analyse.py`
- **Data (`results/cost/study_r5/`):**
  - `study_r5_requests_h100nvl.jsonl.gz` (every request: kind, device, session, prompt/cached tokens, TTFT, latency)
  - `study_r5_metrics_h100nvl.jsonl.gz` (1 s `/metrics` timelines)
  - `study_r5_run_meta_h100nvl.json` (servers, KV capacity, probe, mechanism check, per-cell device plans)
  - `study_r5_results_h100nvl.json`
  - `study_r5_*_attempt1_crash_h100nvl.jsonl`
- **Logs:** `logs/queue4_r5_*.log`, `logs/r5_probe.log`, `logs/study_x_server_32BI_101[78]_*.log`
