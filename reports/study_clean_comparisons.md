# StudyClean — comparisons that were never clean

_Pre-registered 2026-11-03 (research/EXPERIMENTS.md, StudyClean). Host: **h100nvl GPU 1** (GPU 3 was held by another user; the references K1, K3 and RH4 ran on GPU 3). Stacks: vLLM 0.31.0 venv `~/.venvs/fm-switching-vllm` (FA3, prefix caching off) for SAN, H1, H2, H3, H5; HF `.venv` (transformers 5.10.2, torch 2.8.0+cu128, SDPA) for H4. vLLM and HF numbers are never pooled._

## Results

Ran 2026-11-03 on h100nvl GPU 1:
- **Accuracy cells:** 11:36–12:26.
- **H5 pass 1:** 12:26–12:43.
- **Watchdog kill:** at 12:50:04, user liying started a process on GPU 1 during the 30-minute gap. The watchdog killed our chain session; nothing of ours was on the GPU at that moment, so no data was lost.
- **H5 pass 2:** after GPU 1 was released, 13:13:31–13:32:20, more than 30 minutes after pass 1.

Every cell had **0 errors**, and every pre-registered gate passed:
- **Sanity:** 30/30 K3 letters match on GPU 1, with identical prompt tokens.
- **H5 inputs:** all 4,380 frames match the Orin manifest's sha256, and the question texts match too.
- **H5 cache checks:** cached_tokens never above 0, and vLLM's prefix-cache and multimodal-cache hit counters never grew.
- **Total runtime:** about 1.5 h, against an estimate of 3.83 h.

Before citing any reference, its status in `research/EXPERIMENTS.md` was checked. None is INVALID:
- **StudyR1** (K1, K3): canonical.
- **StudyRH3 and StudyRH4:** canonical.
- **StudyS2:** the audit marks it CONFOUNDED for the Thinking arm D only; arm C, used here, is unaffected.
- **StudyDevFast and StudyDevOne:** canonical.

### S-EMBER: 4B vs 32B on identical requests, and history at a fixed model

All values are percentage points, A − B, with a video-clustered paired bootstrap (2,000 resamples, seed 0) giving the 95 % CI. Strata as user-confirmed: 97 / 167 / 414 / 167, and OLDER is exactly R1 K3's uncovered set (both asserted).

| contrast (input · stack · decoding) | ALL | OLDER | OVERLAP | INSIDE | qt ≤ 120 |
|---|---|---|---|---|---|
| **H1 − K3**: 4B-I − 32B-I on K3's exact 845 RECENT requests (input identical, tokens 845/845 equal · vLLM 0.31.0 FA3 · greedy 512) | **−5.80** [−9.19, −2.61] (32.54 vs 38.34) | −4.12 [−11.65, +3.74] | −3.59 [−10.53, +3.57] | −5.07 [−9.54, −0.71] | −10.78 [−19.19, −2.27] |
| **H2 − K1**: 4B-I − 32B-I on K1's exact 845 RICH requests (input identical, 845/845 · same stack · greedy 512) | **−9.35** [−12.56, −6.11] (30.18 vs 39.53) | −9.28 [−19.00, +1.03] | −11.98 [−19.43, −4.65] | −7.73 [−12.44, −2.59] | −10.78 [−19.19, −2.27] |
| **D2 − H3**: 32B-I whole-session vs last-120-s history (same model, stride, size, format, header · same stack · greedy 512; RH4 paired set n = 839) | +1.79 [−0.48, +4.08] (39.57 vs 37.78) | **+21.28** [+9.57, +32.97] (n 94) | +4.85 [−1.20, +10.91] (n 165) | **−3.15** [−6.10, −0.27] (n 413) | **0.00** [0.00, 0.00] (n 167; identical input) |

- **4B costs accuracy on identical input.** It loses 5.8 pp on the RECENT requests and 9.4 pp on the RICH requests.
  - The gap is largest at qt ≤ 120 (−10.8 pp). There the two constructions are byte-identical, so H1 and H2 give the same answers.
  - On RICH input, 4B gains less from the longer history than 32B does. The context contrasts below show the difference is concentrated in INSIDE.
- **Same model, same format: history is worth +21 pp where the evidence is older than 120 s, and costs −3 pp where it is already inside the window.**
  - Overall the difference is +1.8 pp, and its CI includes 0.
  - This is the same opposite-sign pattern the audit found for K1 − K3 (video input), now on the append-only separate-image format at a fixed stride and frame size.
- **Built-in null:** at qt ≤ 120, H3 and D2 have the same frames, tokens and letters on all 167 questions.

**Context contrasts** (not pre-registered as contrasts; same stack, identical decoding):

| contrast | ALL | OLDER | OVERLAP | INSIDE | qt ≤ 120 |
|---|---|---|---|---|---|
| K1 − K3 (32B RICH − RECENT, GPU 3) | +1.18 [−1.52, +3.89] | +17.53 [+7.29, +28.26] | +10.18 [+3.55, +16.77] | −5.80 [−9.49, −2.11] | 0.00 |
| H2 − H1 (4B RICH − RECENT, GPU 1) | −2.37 [−5.11, +0.35] | +12.37 [+0.98, +24.33] | +1.80 [−5.49, +8.59] | −8.45 [−12.53, −4.30] | 0.00 |

### MV-RoboBench: 32B vs 4B on an identical stack

| contrast (input · stack · decoding) | n | A | B | A − B [95 % paired bootstrap] |
|---|---|---|---|---|
| **arm C (StudyS2, GPU 3) − H4 (GPU 1)**. Input: StudyS2 prompt and manifest, input tokens 401/401 equal. Stack: HF transformers 5.10.2, torch 2.8.0+cu128, SDPA asserted, batch 1, bf16. Decoding: greedy 512. | 401 | 47.88 | 37.66 | **+10.22** [+4.48, +15.96] |

- **By category:**
  - spatial_distance_judgement: 50.7 vs 41.8.
  - robotic_trajectory_selection: 45.0 vs 33.5.
- **Every H4 answer parsed** ("direct" on all 401).
- **The audit's cross-stack number agrees:** it reported +10.97 for 32B-I vs an R4 4B-I run. The identical-stack gap is +10.22.

### H5 latency: Orin vs H100 on identical payloads (shared host, GPU 1, localhost, no network)

Payloads are byte-identical to the Orin's: every PNG's sha256 matches the manifest, as do the `[t=Xs]` markers and the question text. Prompt tokens match too: the vLLM medians equal the Orin's llama.cpp counts. Requests were serial, one at a time, with prefix caching and the processor cache off, greedy, max_tokens 512. TTFT runs from immediately before sending a pre-serialized body to the first content token. The **Orin** is 4B-I F16 on llama.cpp: StudyDevFast for N = 37/18/9 and StudyDevOne (cold) for N = 1. Its warm rows (input_tokens = 1) are excluded, as listed below.

| N | prompt tokens (median) | Orin 4B-I TTFT | H100 4B-I TTFT pass 1 / pass 2 | H100 32B-I TTFT pass 1 / pass 2 | Orin / H100 4B (pass 1) | contention-sensitive (4B / 32B) | accuracy, indicative n = 120: Orin 4B / H100 4B p1 / H100 32B p1 |
|---|---|---|---|---|---|---|---|
| 37 | 12420 (Orin 12422) | 16.985 s | 1.016 s / 0.984 s | 3.015 s / 2.986 s | 16.7x | no (3.2 %) / no (1.0 %) | 34.2 / 35.8 / 46.7 % |
| 18 | 6123 (Orin 6123) | 7.760 s | 0.489 s / 0.491 s | 1.360 s / 1.353 s | 15.9x | no (0.3 %) / no (0.5 %) | 30.8 / 30.8 / 35.0 % |
| 9 | 3130 (Orin 3131) | 3.796 s | 0.241 s / 0.244 s | 0.663 s / 0.664 s | 15.8x | no (1.2 %) / no (0.2 %) | 28.3 / 29.2 / 35.8 % |
| 1 | 468 (Orin 468) | 0.506 s | 0.071 s / 0.070 s | 0.147 s / 0.146 s | 7.1x | no (1.0 %) / no (0.9 %) | 12.5 / 13.3 / 25.8 % |

**Per-cell detail** (TTFT p10–p90, total-latency median, GPU 1 SM clock median and minimum over the request, number of requests flagged for a neighbour load change, the median TTFT without them, and errors):

| cell | pass | TTFT median [p10, p90] | total median | SM MHz median (min) | flagged | median unflagged | errors | letter agreement p1 vs p2 |
|---|---|---|---|---|---|---|---|---|
| 32BI_N37 | 1 | 3.015 [2.930, 3.067] | 3.050 | 960 (472) | 5/120 | 3.013 | 0 | 1.000 |
| 32BI_N37 | 2 | 2.986 [2.912, 3.038] | 3.020 | 960 (487) | 120/120 | nan | 0 | 1.000 |
| 32BI_N18 | 1 | 1.360 [1.325, 1.393] | 1.387 | 975 (600) | 8/120 | 1.357 | 0 | 1.000 |
| 32BI_N18 | 2 | 1.353 [1.320, 1.380] | 1.380 | 975 (0) | 111/120 | 1.353 | 0 | 1.000 |
| 32BI_N9 | 1 | 0.663 [0.645, 0.680] | 0.687 | 960 (480) | 0/120 | 0.663 | 0 | 1.000 |
| 32BI_N9 | 2 | 0.664 [0.647, 0.683] | 0.689 | 960 (487) | 96/120 | 0.664 | 0 | 1.000 |
| 32BI_N1 | 1 | 0.147 [0.139, 0.160] | 0.171 | 1222 (540) | 0/120 | 0.147 | 0 | 1.000 |
| 32BI_N1 | 2 | 0.146 [0.134, 0.159] | 0.170 | 1185 (540) | 83/120 | 0.147 | 0 | 1.000 |
| 4BI_N37 | 1 | 1.016 [0.967, 1.063] | 1.029 | 1740 (555) | 47/120 | 1.021 | 0 | 1.000 |
| 4BI_N37 | 2 | 0.984 [0.939, 1.040] | 1.006 | 1725 (555) | 86/120 | 0.982 | 0 | 1.000 |
| 4BI_N18 | 1 | 0.489 [0.469, 0.514] | 0.498 | 1740 (562) | 97/120 | 0.496 | 0 | 1.000 |
| 4BI_N18 | 2 | 0.491 [0.464, 0.522] | 0.503 | 1732 (562) | 7/120 | 0.490 | 0 | 1.000 |
| 4BI_N9 | 1 | 0.241 [0.231, 0.254] | 0.245 | 1620 (592) | 86/120 | 0.241 | 0 | 1.000 |
| 4BI_N9 | 2 | 0.244 [0.227, 0.262] | 0.247 | 1605 (727) | 13/120 | 0.242 | 0 | 1.000 |
| 4BI_N1 | 1 | 0.071 [0.067, 0.079] | 0.075 | 1785 (1770) | 65/120 | 0.070 | 0 | 1.000 |
| 4BI_N1 | 2 | 0.070 [0.061, 0.080] | 0.074 | 1785 (1770) | 0/120 | 0.070 | 0 | 1.000 |

Orin warm rows excluded (input_tokens = 1, served from llama.cpp's prompt cache): N = 37: 32f09b7e814c; N = 18: 32f09b7e814c; N = 9: 32f09b7e814c; N = 1: none.


## Mechanism verification (Steps 1, 4, 5 recorded 2026-11-03 11:40, before any GPU cell; Steps 2–3 after the sanity gate)

**Step 1 — causal chain.** Earlier comparisons between device and cloud mixed two causes. The model differed (4B on the device, 32B in the cloud), and so did the input: the history, the frame format and sometimes the stack. StudyClean changes one factor at a time.
- **Capability, input held fixed:** H1 vs K3, H2 vs K1 and arm C − H4. Same requests or prompts, same stack; only 4B vs 32B changes. This is the reader-model dependence of semantic fidelity (FORMULATION.md §State objects: fidelity × materialization; CLAIMS C2).
- **Value of history, model held fixed:** D2 vs H3. Same 32B model, stride, frame size and format; only the history length changes, from the whole session to the last 120 s. The effect should be concentrated in OLDER (evidence outside the 120 s window) and be about zero in qt ≤ 120, where the inputs coincide (CLAIMS C1, workload-dependent fidelity).
- **Latency, input held fixed (H5):** identical payload bytes to the Orin (sha256-verified), so Orin vs H100 TTFT isolates the hardware/stack gap per N (CLAIMS C4 physical inertia: prefill cost grows with input tokens).

**Step 4 — negative control.** The value-of-history contrast has a built-in null. In the qt ≤ 120 stratum, H3 keeps every frame D2 has: frames with t ≥ qt − 120 ≥ 0 cover the whole session. The two inputs are therefore identical, and D2 − H3 there must be about 0, up to batching non-determinism. For capability, the sanity cell is the null: the same model on the same requests on a different GPU must reproduce K3's letters (≥ 29/30). For H5, the null is cached-token counts and the cache-hit counters staying at 0. If any request were served from cache, the TTFT would not be a cold prefill.

**Step 5 — alternative explanations.**
- **Capability vs. prompt-token drift.** If 4B-I's prompt had different tokens from 32B-I's, H1 − K3 would mix in an input change. This is ruled out by the per-question prompt-token check (within 1 %).
- **Value of history vs. the header.** H3 keeps D2's header, which says "one frame every 2 s from the session start". For H3 that is false, since its history starts at qt − 120. A header effect would show up in qt ≤ 120 as a non-zero difference, but there the header is true and the input identical. So the header cannot be separated from history in the other strata. This is stated as a limitation.
- **Latency: neighbour contention vs. hardware.** Other users' jobs on GPUs 0, 2 and 3 share CPU and PCIe, so TTFT could reflect contention rather than the GPU. Distinguished by the two passes ≥ 30 min apart (cells whose medians differ by > 10 % are flagged contention-sensitive), the per-request GPU 1 SM clock, and the per-second neighbour record.

**Step 2 — instantiate each link** (sanity gate 11:41; values from the full run).

| causal link | implementing quantity | value in this run | varies as expected? | evidence |
|---|---|---|---|---|
| same stack reproduces the reference | SAN letters vs K3 (GPU 1 vs GPU 3) | 30/30 letters, 30/30 prompt tokens | — (null holds) | `sanity` in run meta |
| capability, input fixed | H1/H2 prompt tokens vs K3/K1 | 845/845 and 845/845 exact (max rel. diff 0) | constant by design | `input_identity` |
| capability → accuracy | H1 − K3, H2 − K1 | −5.80, −9.35 pp | yes (non-zero, CI excludes 0) | results |
| history length → input | H3 vs D2 tokens | INSIDE 5,622 vs 12,710; OLDER 5,603 vs 14,857; qt ≤ 120 3,505 = 3,505 | yes (equal only where history ≤ 120 s) | `tokens` |
| history → accuracy | D2 − H3 per stratum | OLDER +21.3, OVERLAP +4.9, INSIDE −3.2, qt ≤ 120 0.0 | yes (largest where evidence is old; 0 where inputs coincide) | results |
| identical bytes → H100 vs Orin latency | frame sha256; prompt tokens | 4,380/4,380 frames; N = 37 median 12,420 on both stacks | constant by design | `h5_input_identity` |
| input size → TTFT | TTFT vs N | 32B 3.02 → 0.15 s; 4B 1.02 → 0.07 s (pass 1) | yes (monotone in N) | H5 table |
| cold prefill (no cache) | cached_tokens; cache-hit counters | 0 on every request; counters never grew | — (null holds) | `h5_cache_checks` |

No link is ABSENT or CONSTANT where the claim needs it to vary.

**Step 3 — trace one unit.** H5, 32B-I, N = 37, pass 1, first manifest question `32f09b7e…`:
- **Payload:** 37 frames at 560×560 (t = 86 … 206 s), each preceded by its `[t=Xs]` marker, then the device prompt. The body is 22,248,103 bytes, pre-serialized.
- **Server side:** prompt 12,397 tokens, cached 0.
- **Timing:** TTFT 2.956 s, total 2.990 s (2 completion tokens: "D"; correct is B).
- **GPU 1 SM clock:** 945 MHz at send; median 1,005 MHz over the request (148 samples, min 810).
- **Cost bound:** prefill on a power-capped GPU (see check 2).
- **Orin, same question:** this is one of the Orin's excluded warm rows (input_tokens = 1, TTFT 1.44 s), so it does not enter the Orin reference.
- **H1, first R1 question `B058EEFB…`:** the 4B-I request is K3's own, 121 frames as one video. Prompt 12,428 = K3's 12,428 expected tokens. Predicted C, correct A.

## Results consistency check

1. **Cross-check against committed measurements.**

| quantity | this run | prior | source | ratio | agree? |
|---|---|---|---|---|---|
| K3 letters, first 30 questions (32B-I) | 30/30 identical | K3 | R1 (GPU 3) | — | yes |
| K1 − K3 per stratum | +17.53 / +10.18 / −5.80 | +17.53 / +10.18 / −5.80 | `reports/audit_2026_11_03.md` | 1.00 | yes |
| D2 accuracy on the paired set | 39.57 % | 39.57 % | RH4 | 1.00 | yes |
| 4B-I MV-RoboBench (H4) | 37.66 % | 37.4 % (StudyS1 arm I, A6000, cross-study) | StudyS2 report | 1.01 | yes |
| 32B-I − 4B-I MV-RoboBench | +10.22 pp | +10.97 pp (R4 4B-I, different stack) | audit | 0.93 | yes |
| prompt tokens, N = 37 | 12,420 (vLLM) | 12,420 (llama.cpp) | StudyDevFast | 1.00 | yes |
| 32B single-request TTFT at ~12.4k tokens | 3.02 s (37 separate 560² images, GPU 1) | 4.18 s (K3 single, 121 frames as one video, GPU 3) | R1 `single` mode | 0.72 | yes (< 2×; the video path processes 121 frames) |
| Orin 4B-I TTFT at N = 9 | — | 3.80 s / 3.88 s | StudyDevFast / StudyDevOne control | — | reference only |

2. **Physical plausibility.**
   - **32B-I, N = 37:** 12,420 tokens in 3.02 s, about 4.1k tok/s, including the decoding of 37 PNGs. That is below RH5–RH7's 4.5–5k tok/s 32B prefill.
   - **4B-I:** about 12.2k tok/s, 3× the 32B rate for an 8× smaller model. Not faster than the committed curves allow.
   - **SM clock:** during the 32B cells GPU 1's SM clock was about 960 MHz (max 1,785). The per-second monitor shows 396 W at 930 MHz against the card's 400 W limit, with throttle reason 0x1 active. That is the power cap: a property of this card under 32B prefill, recorded per request, and not an artefact. 4B ran at about 1,740 MHz.
   - **No result is faster than the committed curves. PASS.**
3. **Distribution sanity.**
   - **H5:** p10–p90 is within about ±5 % of the median in every cell (per-cell table).
   - **H5 minimum values** come from questions with fewer available frames (for example 14 frames, 4,738 tokens, 0.98 s at N = 37), not from caching. cached_tokens was 0 on all of them.
   - **Accuracy:** answer agreement between the arms is 0.53–0.83, not 1.00, except in the identical-input stratum (1.00), which is the intended null.
   - **PASS.**
4. **Definition audit.**
   - **Strata:** user-confirmed geometric definitions. Counts 97 / 167 / 414 / 167. OLDER is identical to R1 K3 `evidence_covered == false` and to the audit's OLDER (the audit defines it via K3 coverage; same partition).
   - **RECENT and RICH requests** are identical for all 167 qt ≤ 120 questions (frames, tokens, text).
   - **H3:** RH4's D2 frames with t ≥ qt − 120, keeping D2's header, whose "from the session start" is literally false for H3 when qt > 120.
   - **Orin reference:** StudyDevFast (cache_prompt default) minus its 1 warm row per N; StudyDevOne N = 1 is cold (cache_prompt false).
   - **PASS (header noted).**
5. **Claim linkage.**
   - **H1/H2/H4** (capability on identical input) bear on CLAIMS C2 (semantic fidelity depends on the reader model). They support it: 4B loses 5.8–10.2 pp to 32B with input held fixed.
   - **D2 − H3** bears on C1 (fidelity is workload-dependent). It supports it: the value of history changes sign across strata.
   - **H5** bears on C4 (physical inertia grows with context). It supports it on both tiers: TTFT is monotone in N.
6. **Proxy validity.**
   - **"Evidence older than 120 s"** uses the annotated answer interval, the StudyO/R1/audit definition, as a proxy for "needs pruned history".
   - **H5 TTFT** is end-to-end localhost latency, including API-server image decoding. It is not GPU-only prefill, and it is not an isolated-host measurement.
   - **Accuracy in H5** is n = 120, labelled indicative.

## Deviations and notes

- **GPU 1, not GPU 3** (user instruction). The references K1, K3 and RH4 ran on GPU 3, and arm C of StudyS2 also ran on GPU 3. The sanity cell (30/30) shows the change of card does not move greedy letters.
- **Watchdog kill at 12:50:04.** liying's process appeared on GPU 1 during the H5 inter-pass wait. The chain session was killed as pre-registered; no request was in flight (the "in-flight" line in the log is the last finished cell). Pass 2 started at 13:13:31, once GPU 1 was released, and pass 1 data was kept. At 13:39:16, after the chain had completed (13:32:20), the watchdog logged a second liying process on GPU 1; nothing of ours was running. The monitoring summary lists H4's own HF process (pid 3095566, 9.0–9.6 GiB, inside H4's window) as "foreign in windows", because its own-pid detection reads only vLLM logs. It was ours, and the session watchdog did not fire.
- **H4 reuses StudyS2's script unchanged.** Only the output paths changed. Its `_provenance.script` reads `study_s2_mvrobobench_32b.py`; the wrapper is `experiments/cost/study_clean_h4.py`.
- **vLLM image flags.** H5 used `--mm-processor-cache-gb 0` and `--enable-prompt-tokens-details`, and no custom image size. vLLM's Qwen3-VL processor and llama.cpp give the same token counts (12,420 at N = 37).
- **Not pre-registered (reported, not decisive):** K1 − K3 and H2 − H1 context contrasts; per-category MV-RoboBench; flagged-vs-unflagged H5 medians.

## Files

- `experiments/cost/study_clean_vllm.py` (vLLM venv), `experiments/cost/study_clean_h4.py` (`.venv`), `experiments/cost/study_clean_analyse.py` (`.venv`, CPU)
- `results/cost/study_clean/`: `study_clean_requests_h100nvl.jsonl.gz` (SAN, H1, H2, H3), `study_clean_h4_trials_h100nvl.jsonl.gz`, `study_clean_h4_run_meta_h100nvl.json`, `study_clean_h5_requests_h100nvl.jsonl.gz`, `study_clean_h5_snapshots_h100nvl.jsonl.gz`, `study_clean_host_record_h100nvl.tar.gz` (1-s all-GPU / load / dmon PCIe record), `study_clean_run_meta_h100nvl.json`, `study_clean_results_h100nvl.json`
- logs (not committed): `logs/clean_chain.log`, `logs/clean_gpus.csv`, `logs/clean_dmon.log`, `logs/clean_loadavg.log`, `logs/clean_gpu_procs.csv`
