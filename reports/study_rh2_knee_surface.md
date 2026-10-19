# StudyRH2 — latency surface near the knee, with partial warm state

(User's "H2". E-id RH2 because StudyH2 is taken by the S-EMBER audit series.)
Pre-registered 2026-10-18 (research/EXPERIMENTS.md, StudyRH2) before any GPU run. Run 2026-10-18 17:16 →
2026-10-19 02:09, h100nvl GPU 3, 27 cells. **Stack: vLLM 0.31.0+cu129 (venv `~/.venvs/fm-switching-vllm`, torch
2.13.0+cu129), FlashAttention 3, CUDA graphs, prefix caching ON, bf16 KV (65,280 tokens).** Systems construction;
accuracy is not measured. All latencies are this vLLM server; no HF numbers are pooled.

## Decision-rule outcomes and pre-stated expectations

| item (pre-registered) | result | outcome |
|---|---|---|
| MECHANISM CHECK (P-HALF D=8, rate 1.0) | see the list below | **PASSED** |
| runtime estimate ≤ 9 h | 7.6 h | full grid (27 cells), nothing dropped |
| expectation: bf16 knee between D=12 and D=16 for P-WARM | tails break at D=12, the median breaks at D=16 | **as expected** |
| expectation: P-HALF warm devices at D ≈ P-WARM at D/2 | holds at D = 16 and 24 (table below) | **as expected** |

Mechanism check details:
- Warm-device escalation hit was 0.95 (≥ 0.80 required).
- Cold devices had **0 / 36** escalations whose cached tokens exceeded the prompt of their own previous escalation.
- Each session's first cold escalation cached 16 tokens, which is the one shared chat-template and cell-header block.
  The pre-registered limit was ≤ 32.

## Answers

1. **Warm-set KV footprint, not the device count, sets the knee.**
   - Footprint = warm devices × mean history tokens ÷ 65,280.
   - **≤ 0.55× KV:** warm escalations hit 0.95, TTFT median 0.35–0.40 s, p99 ≤ 2 s.
   - **≈ 0.85×:** medians are still 0.4–0.8 s, but append hits fall to 0.66–0.83 and p99 reaches 5–20 s.
   - **1.15×** (P-WARM D=16): the knee. Median 7–8 s, p99 137–160 s, about 150 requests in flight at the window end.
   - **1.72×** (P-WARM D=24): collapse. Median 348–406 s, about 1,000 requests in flight, 14–15 min drain.
2. **Partial warm state avoids the collapse at the same D.**
   - P-HALF keeps half the devices warm. At D=24 (12 warm, footprint 0.84×) its warm devices escalate in
     **0.84 s / 0.64 s median** (rate 1.0 / 0.2), against P-WARM's 406 s / 348 s.
   - P-HALF at D=24 tracks P-WARM at D=12, at the same footprint (0.84 vs 0.86): hit 0.89 vs 0.94, p99 15 s vs
     18 s.
   - P-HALF at D=16 (8 warm, 0.51×) is indistinguishable from P-WARM at D=8 (0.55×).
3. **Cold devices pay for sharing a server with warm ones.**
   - In P-HALF, cold devices' median TTFT is 0.06–0.73 s above pure P-COLD at the same D and rate. Examples:
     D=24 rate 1.0 is 2.00 vs 1.41 s, and D=16 rate 0.2 is 1.66 vs 0.93 s.
   - From D=16 on, their own-prefix hit rate also falls (D=16: 0.25 vs 0.37; D=24: 0.04 vs 0.20; equal at D=12,
     slightly higher at D=8). The resident warm histories evict the previous-escalation prefixes that cold devices
     would otherwise reuse.
   - Below the knee a cold escalation stays under ~2 s median.
4. **The escalation rate barely moves the warm side.**
   - Appends are 90–99% of computed prompt tokens in P-WARM, so the knee and collapse are the same at 20% and 100%
     escalation.
   - The escalation rate matters only for cold devices' own-prefix hits (0.41 → 0.12 at D=12).
5. **What this gives the controller:**
   - Admit devices to the warm set while their summed history footprint stays below about 0.55× KV for clean
     tails, or about 0.85× if p99 ≈ 15–20 s is acceptable.
   - Serve everyone else cold, at ~1–2 s.
   - Never let the warm footprint exceed KV: past 1×, appends miss and re-prefill whole histories, and every
     device's latency explodes.

## Results

All cells are one repetition with seed 0, except D=12 rate 1.0, which was run twice. In-window escalations only.
TTFT is in seconds. Hit is token-weighted cached / prompt. Footprint = warm devices × mean in-window append prompt
tokens ÷ 65,280.

### P-WARM and P-COLD

| D | rate | policy | n esc | hit | TTFT med | p90 | p99 | max | footprint | append hit | computed tok/s | preempt | waiting max | in flight / drain s | errors |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 8 | 1.0 | COLD | 76 | 0.53 | 0.67 | 1.16 | 2.51 | 2.95 | — | — | 209 | 0 | 0 | 1 / 1 | 0 |
| 8 | 1.0 | WARM | 76 | 0.95 | 0.39 | 0.80 | 1.10 | 1.28 | 0.55 | 0.95 | 197 | 0 | 0 | 1 / 0 | 0 |
| 8 | 0.2 | COLD | 14 | 0.15 | 0.66 | 2.58 | 3.08 | 3.12 | — | — | 66 | 0 | 0 | 0 / 0 | 0 |
| 8 | 0.2 | WARM | 14 | 0.95 | 0.36 | 0.91 | 1.26 | 1.29 | 0.55 | 0.95 | 186 | 0 | 0 | 1 / 0 | 0 |
| 12 | 1.0 | COLD | 107 | 0.41 | 0.73 | 2.35 | 3.85 | 3.97 | — | — | 380 | 0 | 0 | 1 / 1 | 0 |
| 12 | 1.0 | COLD rep2 | 107 | 0.41 | 0.76 | 2.08 | 4.07 | 4.63 | — | — | 380 | 0 | 0 | 1 / 1 | 0 |
| 12 | 1.0 | WARM | 107 | 0.94 | 0.42 | 3.44 | 17.8 | 19.7 | 0.86 | 0.82 | 1,032 | 0 | 21 | 1 / 0 | 0 |
| 12 | 1.0 | WARM rep2 | 107 | 0.93 | 0.42 | 4.41 | 19.6 | 21.4 | 0.86 | 0.82 | 1,044 | 0 | 23 | 1 / 0 | 0 |
| 12 | 0.2 | COLD | 22 | 0.12 | 0.83 | 2.66 | 3.17 | 3.27 | — | — | 120 | 0 | 0 | 0 / 0 | 0 |
| 12 | 0.2 | WARM | 22 | 0.94 | 0.42 | 5.54 | 9.70 | 9.96 | 0.86 | 0.83 | 944 | 0 | 21 | 1 / 0 | 0 |
| 16 | 1.0 | COLD | 147 | 0.37 | 0.73 | 2.31 | 3.19 | 3.83 | — | — | 545 | 0 | 0 | 2 / 0 | 0 |
| 16 | 1.0 | WARM | 147 | 0.75 | **7.90** | 79.3 | 160 | 166 | 1.15 | 0.33 | 5,189 | 47 | 145 | 154 / 167 | 0 |
| 16 | 0.2 | COLD | 31 | 0.06 | 0.93 | 1.75 | 2.86 | 2.90 | — | — | 160 | 0 | 0 | 0 / 0 | 0 |
| 16 | 0.2 | WARM | 31 | 0.82 | **6.70** | 61.8 | 137 | 155 | 1.15 | 0.35 | 4,830 | 79 | 131 | 141 / 158 | 0 |
| 24 | 1.0 | COLD | 214 | 0.20 | 1.41 | 3.73 | 8.07 | 9.23 | — | — | 1,045 | 0 | 1 | 5 / 5 | 5 |
| 24 | 1.0 | WARM | 215 | 0.28 | **406** | 798 | 892 | 898 | 1.72 | 0.09 | 10,830 | 0 | 1,016 | 1,118 / 888 | 46 |
| 24 | 0.2 | COLD | 50 | 0.11 | 1.07 | 3.50 | 5.32 | 5.40 | — | — | 266 | 0 | 0 | 1 / 1 | 3 |
| 24 | 0.2 | WARM | 50 | 0.22 | **348** | 681 | 830 | 834 | 1.72 | 0.06 | 10,474 | 0 | 963 | 976 / 841 | 45 |

### P-HALF, warm and cold devices separately

| D | rate | warm devices (n, hit, TTFT med / p90 / p99) | cold devices (n, hit, TTFT med / p90 / p99) | footprint | append hit | computed tok/s | waiting max | errors |
|---|---|---|---|---|---|---|---|---|
| 8 | 1.0 | 40, 0.95, 0.35 / 0.67 / 1.06 | 36, 0.57, 1.02 / 1.94 / 3.28 | 0.24 | 0.94 | 208 | 0 | 0 |
| 8 | 0.2 | 8, 0.92, 0.23 / 0.44 / 0.57 | 6, 0.17, 0.75 / 3.30 / 3.42 | 0.24 | 0.94 | 132 | 0 | 0 |
| 12 | 1.0 | 60, 0.95, 0.38 / 0.72 / 1.49 | 47, 0.41, 0.79 / 2.46 / 3.63 | 0.37 | 0.94 | 343 | 0 | 0 |
| 12 | 1.0 rep2 | 60, 0.95, 0.39 / 0.75 / 2.00 | 47, 0.41, 0.79 / 2.44 / 3.62 | 0.37 | 0.94 | 344 | 2 | 0 |
| 12 | 0.2 | 10, 0.94, 0.33 / 0.48 / 0.97 | 12, 0.11, 1.09 / 3.25 / 3.42 | 0.37 | 0.94 | 222 | 0 | 0 |
| 16 | 1.0 | 76, 0.95, 0.40 / 0.79 / 2.14 | 71, 0.25, 0.86 / 2.37 / 3.54 | 0.51 | 0.95 | 526 | 1 | 0 |
| 16 | 0.2 | 17, 0.95, 0.37 / 0.59 / 0.77 | 14, 0.11, 1.66 / 3.33 / 5.83 | 0.51 | 0.95 | 252 | 0 | 0 |
| 24 | 1.0 | 113, 0.89, **0.84** / 6.63 / 15.1 | 102, 0.04, 2.00 / 6.71 / 12.2 | 0.84 | 0.66 | 2,486 | 19 | 4 |
| 24 | 0.2 | 28, 0.91, **0.64** / 4.45 / 4.87 | 22, 0.09, 1.15 / 5.36 / 6.28 | 0.84 | 0.81 | 1,171 | 3 | 4 |

### P-HALF at D vs P-WARM at D/2 (warm devices)

| P-HALF cell (warm devices) | footprint | hit | TTFT med / p99 | reference | footprint | hit | TTFT med / p99 |
|---|---|---|---|---|---|---|---|
| D=16, rate 1.0 (8 warm) | 0.51 | 0.95 | 0.40 / 2.14 | P-WARM D=8 rate 1.0 | 0.55 | 0.95 | 0.39 / 1.10 |
| D=16, rate 0.2 (8 warm) | 0.51 | 0.95 | 0.37 / 0.77 | P-WARM D=8 rate 0.2 | 0.55 | 0.95 | 0.36 / 1.26 |
| D=24, rate 1.0 (12 warm) | 0.84 | 0.89 | 0.84 / 15.1 | P-WARM D=12 rate 1.0 | 0.86 | 0.94 | 0.42 / 17.8 |
| D=24, rate 0.2 (12 warm) | 0.84 | 0.91 | 0.64 / 4.87 | P-WARM D=12 rate 0.2 | 0.86 | 0.94 | 0.42 / 9.70 |
| D=8, rate 1.0 (4 warm) | 0.24 | 0.95 | 0.35 / 1.06 | R5 P-WARM D=4 (R5 run) | — | 0.95 | 0.33 / — |

At D=24, P-HALF's warm medians are about 2× P-WARM D=12's. Its cold half adds about 1,450 tok/s of full-history
re-prefill (computed 2,486 vs 1,032 tok/s), so warm requests share the GPU with more work. Residency is nonetheless
the same, at append hit 0.66–0.81 vs 0.82.

### Append cost

- **Isolated calibration** (4 sessions, one request at a time):
  - A cold 301-frame upload (6,655 tokens) takes 1.96 s.
  - A +10-frame append (6,875 prompt, 6,640 cached) takes 0.36 s, and an escalation on top takes 0.35 s.
  - The fit is latency = 0.341 s + 0.244 ms × computed tokens.
- **The fixed 0.34 s dominates an append.** It covers resending and decoding the full PNG history on the API server
  plus scheduling, so "append GPU time" (Σ fit) is an isolated-cost upper bound, not GPU-exclusive time:
  - P-WARM: D=8 281 s, D=12 582 s, D=16 1,577 s, D=24 2,884 s per 900-s window.
  - P-HALF: D=24 759 s.
- **The summed contended append latency** explodes past the knee: 258 s (WARM D8), 2,055 s (D12), 48,022 s
  (D16), 907,788 s (D24).
- **The cleaner load measure is computed prompt tokens/s:**
  - The batched prefill capacity of this server is ≈ 5.0–5.6k tok/s (R1/RH1 batched).
  - P-WARM D=16 demands 5.2k (saturated) and D=24 demands 10.8k (2× over).
  - P-HALF D=24 demands 2.5k.

## Design (as pre-registered; one implementation fix, one restart)

- **Reused from R5 unchanged** (`study_r5_fleet` imported):
  - Server: 32B-I @0cfaf481, prefix caching ON, `--enable-prompt-tokens-details`, ≤ 640 images, image size bounds
    4,096–20,480 px, localhost-bound.
  - History: 1 fps frames at 160×128, 22 tokens/frame, each frame a separate image. A per-cell, device and session
    header leads each prompt.
  - Device plans: 234 videos shuffled with Random(0), dealt round-robin over D; offsets from the same Random(0).
  - Replay at 1× real time.
  - Appends every 10 s (header + all frames so far, max_tokens 1).
  - Escalations greedy, max_tokens 4.
  - 15-minute window; requests submitted in it are measured, then drained.
- **New in RH2:**
  - P-HALF: even device indices are warm (warm-up + appends); odd indices never append.
  - Rate 0.2 escalates a fixed per-device 20% of its questions (Random(0), depending only on D), so the subset is
    the same across policies.
  - rep2 uses the same seed, so it measures pure run-to-run variance.
  - Calibration stage.
  - A `warm_device` flag on every record.
- **Implementation fix (2026-10-18 22:58).**
  - The bug: after its last in-window event, a device whose remaining sessions had no events kept sleeping session
    by session, even past the window end. That is common for cold devices at rate 0.2.
  - The effect: no request was sent after the window end, because each event checks `window_end`. But cells with
    cold devices idled 8–40 min (COLD D16 rate 0.2 took 55 min of wall time).
  - The fix: a device returns once its next session would start after the window end.
  - It was applied after cell 16 (P-WARM D=16 rate 0.2) by restarting the chain. The cut-off P-HALF D=16 rate 0.2
    had just begun, recorded nothing, and was rerun in full.
  - Request schedules and measurements are unchanged by the fix.
- **Wall time:** 8.9 h (estimate 7.6 h). About 1.6 h is the idle time above, plus the restart.

## Mechanism verification

1. **Causal chain** (FORMULATION.md: reconstruction cost grows with context length; tier capacity is a memory
   budget).
   - A warm device's escalation prefills only the new tokens if its prefix is resident.
   - Residency requires the warm set's histories to fit in KV.
   - Past that, LRU eviction makes appends miss, and the misses re-prefill whole histories.
   - That compute queues every request, warm and cold. P-HALF halves the warm set at the same D.
2. **Instantiated quantities.**

   | link | quantity | value / range | varies as claimed? |
   |---|---|---|---|
   | warm set size | warm devices | 0 (COLD), D/2 (HALF), D (WARM) | yes, by policy |
   | resident demand | footprint / KV | 0.24 → 1.72 | yes, with warm devices (≈ 4.7k tok/device) |
   | residency | append hit | 0.94–0.95 (≤ 0.55×) → 0.66–0.83 (≈ 0.85×) → 0.33 (1.15×) → 0.06–0.09 (1.72×) | yes, monotone in footprint |
   | re-prefill load | computed prompt tok/s | 186–526 → 944–2,486 → 5,189 → 10,830 | yes |
   | queueing | waiting max / in flight at end | 0 → 19–23 → 145 / 154 → 1,016 / 1,118 | yes |
   | escalation latency | warm TTFT median / p99 | 0.4 / ≤ 2 → 0.4–0.8 / 5–20 → 7.9 / 160 → 406 / 892 s | yes |
   | cold devices' own-prefix reuse | cold hit (rate 1.0) | D8 0.53 vs 0.57, D12 0.41 vs 0.41, D16 0.37 vs 0.25, D24 0.20 vs 0.04 (COLD vs HALF-cold) | yes from D=16, as warm residency grows |

3. **Representative unit.** RH2_HALF_D8_r100, device 1 (cold), session 0.
   - The first escalation sends 22 tokens/frame × frames so far + header + question, and caches 16 tokens.
   - The next escalation of the same session caches at most the previous prompt's length (0 violations over 36).
   - Device 0 (warm): append k sends header + all frames to t=10k s and caches the previous append's prefix
     (append hit 0.94). The escalation at question time caches 0.95 of its prompt, and TTFT is 0.35 s vs 1.02 s for
     the cold devices.
   - No KV binding: kv usage max 0.02, preemptions 0. The outcome is the TTFT gap from cached prefill.
4. **Controls.**
   - **Negative: P-COLD.** With no warm state there is nothing to evict, and there is no collapse at any D (median
     ≤ 1.41 s at D=24, 0 preemptions, waiting ≤ 1).
   - **Positive (R5): FP8.** Doubling KV at the same append rate moved the knee from D=16 to D=32.
   - **Within RH2: P-HALF D=24 vs P-WARM D=24.** Same D, same escalations and same session load, but half the
     warm footprint: 0.84 s vs 406 s.
5. **Alternative explanation: append request rate rather than KV residency.**
   - P-HALF D=24 has the same append count as P-WARM D=12 (1,062 vs 1,067) *and* the same footprint (0.84 vs
     0.86), so RH2 alone cannot separate the two.
   - R5's FP8 control separates them: at bf16 D=16 vs FP8 D=16 the append rate is equal and the KV doubles, and FP8
     shows no knee.
   - Total compute is not the trigger below saturation either. P-HALF D=24 computes 2.4× P-WARM D=12's tokens and
     keeps the same residency.

## Results consistency check

1. **Cross-check against committed measurements (R5, same construction).**

   | quantity | RH2 | R5 | ratio |
   |---|---|---|---|
   | KV capacity (bf16) | 65,280 | 65,280 | 1.000 |
   | WARM D=8 hit / TTFT median | 0.95 / 0.39 s | 0.95 / 0.38 s | 1.00 / 1.03 |
   | COLD D=8 hit / TTFT median | 0.53 / 0.67 s | 0.53–0.61 / 0.53–0.68 s | ≈1 |
   | WARM D=16 hit / TTFT median | 0.75 / 7.90 s | 0.71 / 8.6 s | 1.06 / 0.92 |
   | WARM D=16 preemptions / in flight / drain | 47 / 154 / 167 s | 43 / 154 / 171 s | 1.09 / 1.00 / 0.98 |
   | WARM D=16 computed tok/s | 5,189 | 5,227 | 0.99 |
   | append hit WARM D=16 | 0.33 | 0.33 | 1.00 |

   Everything agrees to within 10%. The knee reproduces across runs a day apart.
2. **Physical plausibility.**
   - The isolated cold upload of 6,655 tokens in 1.96 s is 3.4k tok/s including image decoding. R1's single
     12.5k-token video request took 4.2 s (3.0k tok/s), so they agree.
   - Warm TTFT of 0.35 s for 6.9k prompt tokens with 6.86k cached means ≈ 90 computed tokens plus fixed overhead,
     consistent with the 0.34 s intercept. It is a caching effect by design, labelled warm.
   - The P-WARM D=16 load of 5.2k computed tok/s matches the batched prefill capacity (5.0–5.6k tok/s, R1/RH1)
     exactly where the knee appears.
3. **Distribution sanity.** Every cell reports median, p90, p99 and max, and p99/median ranges from 2.5 (P-HALF warm
   devices) to 47 (P-WARM D=12, tail onset). No constants: rep1 vs rep2 medians agree within 0.01–0.03 s, p99s differ by
   0.0–1.8 s.
4. **Definitions.**
   - Hit = Σ cached ÷ Σ prompt over in-window, error-free escalations (R5's).
   - Footprint = warm devices × mean in-window append prompt tokens ÷ KV. This is a time-average; instantaneous
     peaks are higher.
   - "Cold device" means no appends, but prefix caching stays on, so a cold device can reuse its own previous
     escalation (the R5 caveat). Cold here is not cold prefill.
   - `kv_cache_usage_perc` counts blocks held by running requests, not resident cached-but-free prefixes. That is
     why it reads 0.02–0.5 in healthy cells and why the WARM D24 max is 0.67, when far more requests were queued
     than could be admitted.
5. **Claim linkage.**
   - **Supports:** the physical component of Context Inertia (keeping state warm is worth ~2× TTFT only while it is
     resident) and the controller premise that *which* devices are kept warm is a capacity-allocation decision.
   - Partial warm-keeping dominates both all-warm (past 0.85× KV) and all-cold (warm devices are 2–3× faster).
6. **Proxy validity.**
   - Footprint uses mean append prompt tokens as the per-device resident size. That is a proxy for instantaneous
     residency, which is not observable through the API. It ranks cells monotonically with append hit.
   - "Append GPU time" is an isolated-latency proxy dominated by fixed per-request overhead. It is reported, and
     computed tok/s is used for the load argument instead.

## Caveats

- One repetition per cell except D=12 rate 1.0. Run-to-run variance there is small: medians within 0.03 s, hit
  within 0.013.
- **640-image limit.** One session in the D=24 plans exceeds 640 s.
  - 3–4 of its late escalations per D=24 cell are rejected with HTTP 400.
  - In P-WARM D=24, another 41 appends and 1 warm-up are rejected, so that device is effectively cold for the rest
    of its session.
  - 2 ReadErrors occurred, one in COLD D24 and one in HALF D24 rate 0.2.
  - No D ≤ 16 cell has errors.
- Preemptions are 47–79 at P-WARM D=16 but 0 at D=24. At D=24 the scheduler admits few requests (waiting
  > 1,000), so it never needs to preempt. Latency there is queueing, not thrashing.
- P-HALF splits by device index parity, not by any value signal. A controller choosing *which* devices to keep warm
  could do better.
- The wall time was 8.9 h, of which ~1.6 h was idle from the fixed harness bug.

## Files

- `experiments/cost/study_rh2_knee_surface.py` (vLLM venv), `experiments/cost/study_rh2_analyse.py` (.venv)
- `results/cost/study_rh2/`:
  - `study_rh2_requests_h100nvl.jsonl.gz`
  - `study_rh2_metrics_h100nvl.jsonl.gz`
  - `study_rh2_run_meta_h100nvl.json` (estimate, calibration, mechanism check, device plans, per-cell meta)
  - `study_rh2_results_h100nvl.json`
