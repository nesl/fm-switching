# StudyE8-device-warm — cost of keeping a 4B D2 history warm on the Jetson Orin

**Status: COMPLETE (2026-11-11, jetson_orin).** Pre-registered row in `research/EXPERIMENTS.md`.
Stack: llama.cpp **c0fd786** (server 0.7.0-dev build 1, verified), `Qwen3VL-4B-Instruct-F16` +
mmproj-F16 (sha256 verified vs `results/device/model_hashes.txt`), MAXN mode 0, GPU pinned
1.3005 GHz (logged per request, 0 bad across all requests), greedy (temp 0), seed 0, max_tokens 64,
**n_ctx = 57344** (one slot, `cache_prompt` true = warm / false = cold). Inputs = StudyE7-d2-4b Job C
archive (RH4_D2 history, one 352×256 frame every 2 s from session start); **4,521/4,521 frames
SHA-256 verified**, and every question body's `body_sha256` recomputed and **matched** — device
inputs are byte-identical to the H100 StudyE7 4B, which produced the parity letters.

---

## Headline

1. **The warm mechanism is present on this runtime (Part 0 PASS).** llama.cpp c0fd786 reuses the
   image KV prefix across requests: a one-frame append evaluates ~95 tokens and reuses the rest,
   and a question tail is correctly dropped (not the history) on the next append.
2. **Warm answering is ~16× faster and ~35× cheaper than cold** on the same question+history
   (median over 30 matched questions), rising to **27× / 88×** at a 52 k-token history, with
   **identical letters** on 29/30.
3. **Warm is not constant-time.** Because each new frame still attends over the whole cached KV,
   append and warm-question latency grow ~linearly with history (0.28 s → 4.93 s as history goes
   534 → 40,944 tokens).
4. **Keep-warm cannot keep up with a 2 s frame cadence once the session is long.** Append latency
   crosses the 2 s real-time budget at **167 frames ≈ 15,069 tokens ≈ 334 s** into the session; in
   the 10-min real-time run 95 of 266 appends ran over 2 s.
5. **Parity is exact:** device warm **68/68** and cold **27/27** agree with the H100 StudyE7 4B on
   the comparable (non-over_context) questions; no flag (threshold 90 %).

---

## Part 0 — mechanism gate (PASS)

Session `1067129222293667…` (30-frame history), `cache_prompt` true, one slot:

| request | prompt tok | evaluated | reused (cache_n) | TTFT |
|---|---|---|---|---|
| R1 history (30 frames) | 2739 | 2739 | 0 | 5.25 s (cold) |
| R2 + 1 frame | 2829 | **95** | **2734** | 0.59 s |
| R3 + question | 2921 | 97 | 2824 | 0.45 s |
| R4 + 1 frame (after the question) | 2919 | **95** | **2824** | 0.60 s |

R2 reuses the entire image prefix (evaluates ≈ one frame's ~90 tokens); R4 proves the question
tail from R3 is dropped while the image history is retained. **Gate passed → Parts A–D ran.**
Memory for the 57,344-token slot (Orin unified memory, no discrete VRAM): server RSS **18.3 GiB**
after load, **33.3 GiB** at the longest (52 k-token) history; tegrastats peak RAM 42.2 GiB.

---

## Part A — warm replay (20 sessions, 4,445 appends + 74 questions)

Each new frame always evaluates **95 tokens** (one frame + template tail) and reuses the rest
(median reused fraction **0.991**); no session reached the n_ctx ceiling (max history 52,127 <
57,344). Latency and energy nonetheless grow with history because the new frame attends over the
whole KV.

**Append cost vs history size** (per-request, median):

| history tokens (med) | n | evaluated | TTFT p50 | TTFT p90 | energy p50 (J) |
|---|---|---|---|---|---|
| 534 | 200 | 95 | 0.281 s | 0.366 s | 9.5 |
| 1,974 | 440 | 95 | 0.426 s | 0.532 s | 11.4 |
| 4,494 | 680 | 95 | 0.717 s | 0.895 s | 15.0 |
| 7,959 | 862 | 95 | 1.137 s | 1.422 s | 20.1 |
| 13,629 | 1,210 | 95 | 1.856 s | 2.389 s | 29.0 |
| 23,529 | 565 | 95 | 2.970 s | 3.390 s | 42.6 |
| 40,944 | 488 | 95 | 4.929 s | 5.949 s | 66.6 |

**Warm-question cost vs history size** (evaluated ≈ question-text tokens, ~160–207; history reused):

| history tokens (med) | n | TTFT p50 | total p50 | energy p50 (J) |
|---|---|---|---|---|
| 4,648 | 15 | 0.777 s | 0.837 s | 18.2 |
| 8,453 | 16 | 1.083 s | 1.147 s | 22.0 |
| 12,816 | 24 | 1.730 s | 1.799 s | 28.3 |
| 25,264 | 9 | 2.956 s | 3.033 s | 42.3 |
| 45,699 | 7 | 5.657 s | 5.750 s | 80.6 |

Warm question TTFT overall: p50 1.38 s, p90 3.47 s, p99 6.27 s.

---

## Part B — cold reference (30 questions, `cache_prompt` false, reused = 0 on all)

Cold TTFT rises from 3.24 s (761 tok) to 162.8 s (52,127 tok). The curve is **super-linear**: the
LLM prefill rate falls from **647 tok/s** at small contexts to **336 tok/s** at 52 k (O(n²)
attention), and the client TTFT additionally carries the vision-encode of every D2 frame (≈ 2 s for
7 frames at 761 tok; server prompt-eval alone is 1.18 s there).

A single linear fit over 761–52,127 tok gives 3,022 ms / 1k (R² 0.984) but an **unphysical −8.5 s
intercept** — confirming the curve is not linear.

**vs StudyD4-orin / F4 (FLAGGED > 2×, explained):** F4's device cold curve (≤ 3,085 tok, 1/3/9
large 560×560 frames) has slope ≈ 1,261 ms / 1k; E8's linear slope is 2.4× that. The gap is a
**format + range effect, not a stack regression**: (i) D2 packs many small 352×256 frames (7–578
per question) so client TTFT carries far more vision-encode; (ii) E8's token range is 17× wider, so
the O(n²) attention term dominates where F4 never reached. E8's pure LLM-prefill throughput
(647 tok/s at small contexts) is within ~1.3× of F4's 812–940 tok/s on the same stack.

---

## Part C — sustained keep-warm (one 1,200 s session, real time, 10 min after 120 s idle)

| quantity | value |
|---|---|
| loaded-idle board power (120 s baseline) | **9.94 W** |
| mean board power while keeping warm | **15.14 W** |
| **warm − idle delta** | **5.21 W** |
| energy per warm-hour | **15.1 Wh/h** (mean W) |
| appends in 10 min | 266 |
| append TTFT p50 / p90 / max | 1.58 / 2.74 / 3.13 s |
| appends over the 2 s cadence | **95 / 266** |
| **2 s crossover** | **167 frames ≈ 15,069 tok ≈ 334 s into the session** |

Append total latency grows from 0.21 s (session start) to 3.13 s (end, 23,979-tok history), so a
device keeping a 4B D2 history warm at a real 2 s frame cadence **keeps up only for the first
~5.6 min**; past ~167 frames it falls behind and ingests frames slower than they arrive. The
warm−idle delta (5.21 W) cancels the constant `jtop` monitor draw noted in the run and is the clean
keep-warm power figure.

---

## Part D — parity (device vs H100 StudyE7 4B, identical bytes)

| comparison | n comparable | agree | agreement |
|---|---|---|---|
| **device WARM vs H100 4B** | 68 | 68 | **1.000** |
| **device COLD vs H100 4B** | 27 | 27 | **1.000** |
| device WARM vs device COLD | 30 | 29 | 0.967 (1 mismatch) |

No cell below 90 % — **no flag**. The 6 `over_context` questions (45 k–52 k tok) the H100 could not
answer are excluded from agreement; the device answered all 6 (device-only letters recorded). The
one warm↔cold device mismatch is question `F1C02E4A357E` (45,699 tok, over_context): warm **E** vs
cold **D** — a floating-point divergence between the KV-reuse and full-prefill paths at ~45 k
context, on a question with no H100 reference. The archive's `letters_4b.jsonl` cross-validates
**68/68** against the newly committed `results/sember/study_e7/e7_requests_h100nvl.jsonl`.

**Warm vs cold, matched (same question + history) — the core answer:** median TTFT speedup
**16.0×** (21.6× at 761 tok → 27.0× at 52,127 tok); median energy ratio (cold/warm) **35.2×**
(10.5× → 87.7×). Accuracy on the Job C subset (small n): device warm 0.216 (74 q, incl. 6
device-only), cold 0.300 (30-q sample), H100 on comparable 0.235 — all modestly above the 0.20
chance floor; accuracy is not the headline here (cost and parity are).

---

## Sanity checks

- **Cold reused = 0** on all 30 Part B requests. ✓
- **Clock pinned** 1.3005 GHz, 0 bad across Part A (4,519) + Part B (30) + Part C (269). ✓
- **No throttling:** tj_max 69.5 °C over the whole run (stop gate 90 °C never approached). ✓
- **Determinism:** 10 repeated cold question requests → identical letter (B×10). ✓
- **Parsing:** 0 unparsed (`X`) in warm or cold. ✓
- **Inputs byte-identical:** `body_sha256` matched 74/74; device prompt-token counts equal the
  H100's exactly (74/74, ratio 1.000). ✓

---

## Results consistency check (CLAUDE.md, 6 checks) — PERFORMED

1. **Cross-check vs committed.** Parity `letters_4b` vs committed `e7_requests_h100nvl.jsonl` 68/68
   match; device prompt tokens = H100 `expected_prompt_tokens` exactly (74/74, ratio 1.000); warm
   68/68 and cold 27/27 letters = H100. All ratios 1.0; nothing near the 2× gate except Part B's
   cold-TTFT *slope* vs F4 (2.4×), investigated and explained (format + range, not stack — LLM
   prefill 647 tok/s is within 1.3× of F4).
2. **Physical plausibility.** LLM prefill 336–647 tok/s, declining with length (O(n²)), inside the
   committed StudyF3/F4 Orin band; warm append always evaluates 95 tokens (one 352×256 D2 frame ≈
   90 tok); warm-vs-cold speedup (16×) and energy ratio (35×) follow directly from reusing the KV
   and prefilling only the question tail. No rate exceeds the committed curves.
3. **Distribution sanity.** Per-bin TTFT/energy spreads reported (non-degenerate, widen with
   history); the 10/10 determinism is the intended greedy+cold check, not a frozen distribution.
4. **Definition audit.** warm = `cache_prompt` true + KV reuse (evaluated ≈ 1 frame, reused ≈
   history); cold = `cache_prompt` false (reused 0); D2 = 352×256 frames ~90 tok (vs F4's 560×560 ~
   327 tok); energy = 3 INA3221 rails (no VDD_IN), 100 ms tegrastats, trapezoid; prompt assembly
   header→images→text verified byte-identical to StudyE7 (`body_sha256` 74/74).
5. **Claim linkage.** Measures the **physical component of Context Inertia** — the cost of holding a
   warm history and the reconstruction cost it avoids. Keep-warm append cost grows with history and
   crosses the 2 s cadence at ~15 k tokens; warm answering is 16×/35× cheaper than cold. This
   unblocks **StudyE6b Stage B** (device-warm history link, previously ABSENT, pending StudyE7 and
   StudyE8). No scoped-out quantity measured (single model per tier; no cross-tier KV transfer).
6. **Proxy validity.** None — direct measurement on byte-identical inputs; parity is the device's
   own letters vs the H100's on the same bytes, not a proxy.

**Mechanism verification (Steps 1–5):** Part 0 **is** the mechanism gate and ran before Parts A–D.
Step 1 chain: *if* llama.cpp reuses the image KV prefix across requests (the mechanism), *then* an
append re-encodes only the new frame, so keeping a history warm costs ~one frame per append and a
warm answer reuses the whole prefix. Step 2: the quantity is `evaluated`/`reused` per request —
non-zero and varying exactly as claimed (evaluated 95 constant; reused rising to 52 k). Step 3: the
R1–R4 trace above. Step 4 negative control: Part B (`cache_prompt` false) disables the mechanism and
the warm advantage collapses (reused 0, cold TTFT; the 16×/35× warm-vs-cold gap is the control
delta). Step 5 alternative: a false "reuse" from identical short prompts is ruled out because
`reused` scales with the (distinct) history length and letters match cold on identical bytes.

---

## Files

- `reports/study_e8_device_warm.md` — this report.
- `results/device/study_e8/part0_mechanism.json` — R1–R4 gate trace + verdict.
- `results/device/study_e8/partA_warm.jsonl` — 4,519 rows (append + question; evaluated/reused/
  TTFT/total/clock/wall + per-request letters).
- `results/device/study_e8/partB_cold.jsonl` — 30 cold question requests.
- `results/device/study_e8/partC_keepwarm.jsonl` — 269 rows (10-min real-time keep-warm).
- `results/device/study_e8/tegrastats.jsonl.gz` — continuous 3-rail power (101,755 samples).
- `results/device/study_e8/study_e8_summary.json` — stack, kv_mem, Part 0, Part C, determinism.
- `results/device/study_e8/study_e8_analysis.json` — all tables (A–D), fits, parity, sanity.
- `experiments/device/study_e8_device_warm.py` — runner (reuses `dev_fast_latency.py`).
- `experiments/device/study_e8_analyse.py` — analysis.
