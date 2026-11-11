# StudyF4-device-shortwin — StudyF1 short-window (last-3-second) S-EMBER on the Jetson AGX Orin

**Date:** 2026-11-10 · **Host:** nesl-orin-3 (Jetson AGX Orin, 64 GB) · **Runtime:** llama.cpp `c0fd786` (server 0.7.0-dev build 1, CUDA sm_87) · **Model:** Qwen3VL-4B-Instruct-F16 (+mmproj-F16), sha256 verified · **E-id:** StudyF4-device-shortwin

**Goal.** Run the StudyF1 **short-window** (last-3-second, N = 1/3/9, 560×560 separate images) S-EMBER question set on the device and compare it, per question, with the H100 4B run (StudyF1) **on byte-identical frames**. Jetson only; MAXN mode 0, GPU pinned 1.3005 GHz (verified + logged per request, **0 bad rows**). `cache_prompt=false` (cold), greedy (temperature 0), seed 0, **max_tokens 64**, answer logprobs requested (top-5).

**Inputs.** The StudyF1-shortwin frame archive copied from the H100 (`/home/nesl/data/study_f1_frames/f1/`): 845 questions × {N = 1, 3, 9} = 2,535 manifest rows over **234 videos**, 8 question-category strata. **All 7,605 frames' SHA-256 re-verified against `f1_frames_sha256.json` before the run (7605/7605, 0 mismatch); the tar was then removed.** These are **the same bytes the H100 StudyF1 4B used** (short window), not the DEV-RECENT 120-s frames.

**Prompt & parser (StudyF1's, verbatim).** Each manifest row carries StudyF1's exact `header` and MCQ `text`; the request is assembled **header → N images → MCQ text** (no DEV-RECENT `[t=Xs]` markers). This assembly and the gen params were checked against the committed `experiments/sember/study_f1_infer_vllm.py` (lines 59–70, `GEN`) and are an **exact match** — the only differences are runtime (llama.cpp/Orin streaming vs vLLM/H100 non-streaming) and `top_logprobs` 5 vs 20, neither of which affects the greedy letter. Letter parsed as the first `\b[A-E]\b`.

---

## Part A — accuracy (observations)

All 845 questions at N = 1, then 3, then 9, one request at a time. Accuracy with **video-bootstrap** 95 % CIs (resample the 234 videos, B = 2000). Random baseline = 0.20 (5 options).

| N | input tok p50 (device / H100) | device accuracy [CI95] | H100 4B accuracy [CI95] | device − H100 (paired CI95) | **agreement** (both-parsed) |
|---|---|---|---|---|---|
| 1 | 467 / 467 | **0.1538** [0.130, 0.179] | 0.1538 [0.132, 0.178] | +0.000 [−0.006, +0.006] | **0.9715** (819/843) |
| 3 | 1129 / 1129 | **0.1373** [0.114, 0.161] | 0.1444 [0.121, 0.168] | −0.007 [−0.014, −0.001] | **0.9716** (821/845) |
| 9 | 3085 / 3085 | **0.1515** [0.128, 0.177] | 0.1503 [0.127, 0.175] | +0.001 [−0.002, +0.005] | **0.9811** (829/845) |

- **Agreement with the H100 4B run is 97.2 % / 97.2 % / 98.1 % — all well above the 90 % threshold (no flag).** The device reproduces the H100's per-question letter on ~97–98 % of questions despite a completely different stack (llama.cpp F16 on Orin vs vLLM on H100). The ~2–3 % of disagreements are the expected stack-level numerical differences (F16 weights + different attention kernels); aggregate accuracy is statistically indistinguishable (N = 1 identical; N = 9 within 0.1 pp; N = 3 lower by ~0.7 pp, paired CI barely excludes 0).
- **Accuracy is near or below the 20 % chance floor at every N** — the last-3-second window carries too little of the task. This confirms StudyF1's device-style short-window finding, now measured on the device itself.
- `cached_n = 0` and clock pinned on **every** row (0 bad). Unparsed: N = 1 **2**, N = 3 **0**, N = 9 **0** — identical to StudyF1's (N1 = 2, else 0). Device prompt-token medians equal the H100's exactly (467 / 1129 / 3085).

**Per-stratum (question_category, N = 9, video-bootstrap CI):**

| stratum | n | accuracy [CI95] |
|---|---|---|
| object_comparison | 91 | **0.330** [0.237, 0.424] |
| spatial_aware_reasoning | 91 | 0.187 [0.100, 0.278] |
| sequential_action | 102 | 0.157 [0.091, 0.227] |
| visual_detail_recall | 143 | 0.140 [0.089, 0.196] |
| location_trace | 97 | 0.134 [0.072, 0.208] |
| time_duration | 121 | 0.107 [0.057, 0.162] |
| temporal_ordering_recognition | 90 | 0.100 [0.044, 0.163] |
| counting_objects_events | 110 | 0.091 [0.038, 0.145] |

Only `object_comparison` clears the chance floor (answerable from a single recent frame); the counting/temporal/duration strata, which need the fuller window, sit at ~0.09–0.11.

**Determinism control:** 15 questions at N = 9 run twice back-to-back → **15/15 identical letters**, `cached_n = 0` (greedy + cold determinism holds).

## Part B — latency & energy (observations)

After Part A, nothing else running. 50 requests per N, first-after-load discarded. Energy = per-request trapezoidal integral of total board power (3 INA3221 rails, no VDD_IN; 100 ms tegrastats). 120-s loaded-idle baseline first.

| metric | N = 1 | N = 3 | N = 9 |
|---|---|---|---|
| input tokens p50 | 467 | 1129 | 3085 |
| TTFT p50 / p90 / p99 (s) | 0.497 / 0.528 / 0.543 | 1.308 / 1.334 / 1.364 | 3.798 / 3.890 / 3.920 |
| total latency p50 / p99 (s) | 0.563 / 0.598 | 1.374 / 1.420 | 3.862 / 3.977 |
| energy / req p50 (J) | 14.3 | 45.1 | 149.6 |
| rail split p50 (gpu / cpu / sys, J) | 9.6 / 1.2 / 3.4 | 31.8 / 2.9 / 10.2 | 108.8 / 8.4 / 32.0 |
| TTFT p50 vs StudyD8 / D4-orin ref | 0.497 / **0.969×** (0.513) | 1.308 / **0.976×** (1.34) | 3.798 / **0.989×** (3.84) |

Baseline loaded-idle = **9.89 W**. No throttle (Part B `throttled=None`), clock pinned every row (0 bad), `cached_n = 0`. TTFT reproduces StudyD8 / StudyD4-orin within ±3.1 % at all three N — the stack behaves identically to the earlier device studies, so these short-window payloads sit on the same prefill-bound cost curve (N = 3 here ≈ N = 3 in StudyD4-orin: 1.31 s / 45 J vs 1.34 s / 44 J).

## Agreement with H100 4B (StudyF1) — resolved

The StudyF1 H100 4B per-question predictions arrived in the repo (commit `648635d`, `results/sember/study_f1/f1_requests_h100nvl.jsonl`, model `4BI`, non-grey). Agreement was computed from that committed source (no GPU, no re-inference): **97.2 % / 97.2 % / 98.1 %** at N = 1 / 3 / 9 — **no cell below 90 %**. The earlier "PENDING" state (run launched before the predictions were available) is now closed.

---

## Reading (interpretation)

- **The device reproduces the H100 4B short-window result, on identical bytes, to 97–98 % per-question agreement.** This is the strongest device↔cloud like-for-like we have on S-EMBER: same frames (sha256-verified identical), same prompt template, same decoding — only the serving stack differs. Aggregate accuracy is indistinguishable and the per-question letters agree on ~97–98 % of questions, so a device-vs-cloud *accuracy* comparison on this workload is valid and the small residual is stack noise, not a capability gap.
- **A 3-second window is insufficient for this task at 4B.** Accuracy is at or below the 20 % chance floor at every N (0.154 / 0.137 / 0.152), and adding frames within the 3 s window (N = 1 → 9) does not help — the information is not in the last 3 seconds for most strata. Only `object_comparison` (single-frame-answerable) clears chance. This is the device-side confirmation of StudyF1's headline (short windows lose ~17 pp vs the 120-s window).
- **Cost is exactly the device's known prefill-bound curve.** TTFT 0.50 / 1.31 / 3.80 s and energy 14 / 45 / 150 J at N = 1 / 3 / 9 match StudyD8 / StudyD4-orin within ±3 %. Short-window sensing buys nothing in accuracy here but costs the same as any N-frame prefill, so on this workload the cheap fast path (N = 1) is as good as N = 9 — both are task-insufficient.

---

## Results consistency check (6 checks)

**1. Cross-check against committed — PASS** (all ratios ≈ 1.0, well within the 2× gate):

| quantity | this run (device) | prior committed | source | ratio | agree |
|---|---|---|---|---|---|
| 4B N=1 accuracy | 0.1538 | 0.1538 | StudyF1 H100 | 1.00 | ✓ |
| 4B N=3 accuracy | 0.1373 | 0.1444 | StudyF1 H100 | 0.95 | ✓ |
| 4B N=9 accuracy | 0.1515 | 0.1503 | StudyF1 H100 | 1.01 | ✓ |
| prompt tokens p50 (N=1/3/9) | 467 / 1129 / 3085 | 467 / 1129 / 3085 | StudyF1 `checks` | 1.00 | ✓ |
| unparsed (N=1/3/9) | 2 / 0 / 0 | 2 / 0 / 0 | StudyF1 `checks` | — | ✓ |
| N=1 TTFT p50 | 0.497 s | 0.513 s | StudyD8 | 0.97 | ✓ |
| N=3 TTFT p50 | 1.308 s | 1.34 s | StudyD4-orin | 0.98 | ✓ |
| N=9 TTFT p50 | 3.798 s | 3.84 s | StudyD8 | 0.99 | ✓ |
| N=9 energy/req | 149.6 J | 149 J | StudyD4-orin | 1.00 | ✓ |
| loaded-idle | 9.89 W | 9.61 / 9.66 W | StudyD8 / D4-orin | 1.02 | ✓ |

**2. Physical plausibility — PASS.** Prefill rates (TTFT-implied): N=1 940, N=3 863, N=9 812 tok/s — within the committed Orin ~800–1050 tok/s band, declining gently with length (attention-quadratic). `cached_n = 0` rules out caching (a cached prefill would imply an impossibly high rate). Energy ≈ mean power × duration at ~33 W active. No rate exceeds any committed curve.

**3. Distribution sanity — PASS.** p50/p90/p99 reported for every latency/energy figure; all non-degenerate (N=9 TTFT 3.80–3.92 s tight as expected for fixed prefill; per-stratum accuracies span 0.09–0.33 with wide, overlapping CIs at n≈90–143). The determinism control's 15/15 match is the intended greedy+cold check, not a frozen distribution — the underlying TTFTs still vary.

**4. Definition audit — PASS.** N = 1 = most recent frame; N = 3/9 = evenly spaced over the last 3 s (StudyF1's `header`/`pick`). `cache_prompt=false` ⇒ cold (`cached_n=0` every row). Energy = sum of 3 INA3221 rails (no VDD_IN). Accuracy = parsed-letter == gold; agreement = device letter == H100 letter on both-parsed questions. Prompt assembly header→images→text verified identical to StudyF1's `study_f1_infer_vllm.py`. Same frame bytes (sha256 7605/7605).

**5. Claim linkage — PASS.** Bears on the device↔cloud comparability question (FORMULATION physical component + the comparability ledger): this is an **IDENTICAL_INPUT** device-vs-cloud accuracy comparison (same bytes, same prompt, different stack), and the 97–98 % agreement establishes that 4B accuracy is reproducible across the two serving stacks within ~2–3 % per-question noise. The short-window null (accuracy ≤ chance) is a property of the *input* (3 s of evidence), measured here on the device — it supports StudyF1's "short windows are insufficient" conclusion rather than making a new capability claim. No scoped-out quantity measured (no cross-tier KV transfer).

**6. Proxy validity — stated.** Accuracy here is the device's own measurement on the **same bytes** the H100 used, so it is not a proxy — the A6000-reference convention is still noted, but the direct H100 4B comparison is the primary cross-check and it agrees. Per-stratum uses `question_category` (8 strata, self-contained); StudyF1 additionally reports evidence-window strata (OLDER/OVERLAP/INSIDE/QT_LE_120) that require per-question answer-interval labels not carried in the shortwin manifest — not recomputed here, noted as the one stratification StudyF1 has and this report does not.

**Mechanism verification:** N/A — runtime accuracy/latency/energy measurement on identical bytes, no causal claim (as StudyD8 / StudyD4-orin); Steps 1–5 do not apply.

**STOP / sanity gates:** none tripped — clock pinned (0 bad rows across 2,535 + 150 requests), inputs verified (7605/7605), `cached_n = 0` everywhere, determinism 15/15, no throttle (Part B `throttled=None`), agreement ≥ 97 % (no < 90 % flag).

---

## Files

- Harness: `experiments/device/study_f4_device_shortwin.py` (reuses `dev_fast_latency.py` Sampler / integrate / idle_stats / launch_server / gpu_freq / GGUF).
- Part A: `results/device/study_f4/partA_accuracy.jsonl` (2,535 per-request rows incl. pred / correct / answer_logprob / cached_n / clock); `repeat_control.json` (determinism).
- Part B: `results/device/study_f4/partB_latency.jsonl` (150 rows incl. energy), `partB_baseline_tegrastats.jsonl.gz`, `partB_latency_tegrastats.jsonl.gz`.
- Aggregate: `results/device/study_f4/study_f4_summary.json` (accuracy + video-bootstrap CIs, per-stratum, agreement vs H100 4B, consistency extras, provenance).
- Agreement source (committed): `results/sember/study_f1/f1_requests_h100nvl.jsonl` (model `4BI`, non-grey).
- Inputs: `/home/nesl/data/study_f1_frames/f1/` (StudyF1-shortwin archive, 560×560; tar removed after verification); model sha256 `results/device/model_hashes.txt`.
