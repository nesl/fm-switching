# StudyORIN1-dense (Jetson AGX Orin): dense device scores, controller overhead, warm recall latency

**Date:** 2026-11-15 (Parts 2 and 3); Part 1 completed 2026-11-16 · **Host:** Jetson AGX Orin (64 GB unified memory) · **Runtime:** llama.cpp `c0fd786` (server 0.7.0-dev, CUDA sm_87 aarch64) · **Model:** Qwen3-VL-4B-Instruct-F16 GGUF + mmproj-F16 (sha256 verified) · **E-id:** StudyORIN1-dense

No git history-altering command was run. Nothing else used the Orin GPU during the study. No network tests. (No em dashes are used in this report.)

## 0. Summary

- **Part 1 (dense scores): COMPLETE.** All **42,014** StudyD14b N=1 requests (0.25 s grid, 300 clips) were scored on the Orin, one request at a time, cold prompt. The dense frames arrived in two halves (139 then 161 clips) because the device disk cannot hold the full set; each half was sha256-verified against `frames_sha256_manifest.jsonl.gz` (0 missing, 0 mismatch) before scoring, and its fractional frames were deleted after scoring, with the 10,660 integer-second StudyD15 frames preserved throughout. The Orin reproduces StudyD15's scores **exactly** on the 10,660 integer-second overlap (Pearson 1.000000, max abs diff 0.0). Against the H100 4B D14b arm the device scores correlate strongly (Pearson 0.9426, Spearman 0.9416 over all 42,014) with a per-frame absolute-score offset (median abs diff 0.996 in log P(Yes) units), and on the challenge set the device and the H100 4B arm are statistically indistinguishable in average precision (Orin 0.5735, H100 0.5764, diff -0.0029, 95 percent CI [-0.0079, 0.0019], includes 0).
- **Part 2 (controller overhead): COMPLETE.** The device controller signals cost 8.4 / 19.3 / 80.0 microseconds mean per update (p99 9.3 / 20.2 / 85.4) for recent-window sizes 20 / 60 / 240. Against the 250,000 microsecond budget of a 4 Hz tick, the controller uses at most 0.034 percent of one tick. It is effectively free on the Orin CPU.
- **Part 3 (device recall latency on a warm D2 history): COMPLETE, and it refutes the project's assumed rule.** Answering an S-EMBER DEV question on a warm (KV-cached) D2 history is not near-free: TTFT p50 is **1.41 s at 11k tokens and 3.43 s at 28k tokens**, even though the history is cached and only the 123 question tokens are evaluated. The latency scales at about **0.12 ms per history token** and is dominated by client-side resend and parse of the full image payload (the StudyD15b mechanism), not by model compute (server prompt-eval is only 0.13 to 0.19 s).

## 1. Design and provenance

All three parts reuse the StudyD15 / StudyD15b / StudyE8 scripts, prompt, scoring, quantization and server settings verbatim.

**Stack (recorded for sanity).** llama.cpp `c0fd786`; weights `Qwen3VL-4B-Instruct-F16.gguf` sha256 `4a6fb1ed...2ec761`, mmproj `mmproj-Qwen3VL-4B-Instruct-F16.gguf` sha256 `256f3a43...985331` (both match the StudyF4 / StudyE8 committed hashes); server flags `-ngl 99 -fa on -c 57344 --jinja --reasoning-format deepseek -np 1`; MAXN mode 0; GPU pinned 1.3005 GHz (`cur_freq = 1300500000`, logged per request as `clock_ok`); greedy; seed 0.

**Scoring (Part 1).** Continuous `log P(Yes)`: the log of the first-token `Yes / (Yes + No)` top-20 probability mass, floored at 1e-12. Literal Yes/No strings are never used as the score. `cache_prompt = false` for scoring (cold prompt). This is StudyD15's `score_request` and `build_nexar_content` unchanged.

**Thermal and clock (Parts 2 and 3).** Part 2 is CPU-only. During Part 3 (tegrastats 100 ms, 1,841 samples) the GPU junction temperature peaked at **57.0 C** (mean 51.9 C), far below the 90 C throttle stop; GR3D busy peaked at 99 percent (mean 39 percent); peak RAM 27.7 GB of 64 GB. No throttled interval. GPU clock was pinned on every measured request.

## 2. Part 1: dense scores (COMPLETE)

StudyD14b defines the clip set, 0.25 s grid, request ids and N=1 frame selection. The request contract is byte-identical to StudyD15 / StudyD14 / StudyD3 (header "The following is 1 dashcam frame." then one SMALL 768x432 PNG then the Nexar query; prompt_tokens 378). The runner scores every D14b N=1 request cold (`cache_prompt = false`), warm model, one request at a time, resumable by clip.

**Batched landing (device disk constraint).** The 31,354 fractional frames plus the 10,660 integer-second frames exceed free space on the Orin, so the Mac transferred the clips in two halves. The procedure for each half: detect the clips whose dense frames are present (manifest driven, by comparing the fractional N=1 frame keys on disk to those scored), sha256-verify every required frame for those clips against `frames_sha256_manifest.jsonl.gz` and STOP on any missing or mismatch, score only those clips, then delete only the scored fractional frames (never any integer-second frame, guarded by an explicit protected-key set with a 0-collision check). Batch 1 was 139 clips (`00005` to `00906`, 20,000 N=1 requests: 14,929 dense + 5,071 integer); batch 2 was 161 clips (`00915` to `02137`, 22,014 requests: 16,425 dense + 5,589 integer). Both gates passed with 0 missing and 0 mismatch. The 10,660 integer-second StudyD15 frames were present and untouched throughout. The per-batch log is `results/dashcam/study_orin1/part1_batches.jsonl`.

**Coverage and sanity.** The final `orin1_dense_scores.jsonl` has **42,014** rows, one per N=1 request, no duplicates, covering all 300 clips exactly (0 missing, 0 extra). Clock was pinned on every row (`clock_ok` true x 42,014); 0 rows were "neither" (both Yes and No absent from the first-token top-20) and 0 scores were null.

**Result 1, D15 reproduction (the gate).** On the 10,660 integer-second requests shared with StudyD15 Part A, matched by `d14_request_id`, the Orin scores are **identical** to StudyD15: Pearson **1.000000**, max abs diff **0.0**. This is the expected outcome (same stack, same frames, same prompt, greedy, seed 0) and confirms the dense harness is the StudyD15 harness. Gate (>= 0.99) passes.

**Result 2, H100 4B agreement.** Matched by `request_id` to the H100 4B D14b arm (`d14b_trace_h100nvl`, model 4BI, n=1) over all 42,014 requests:

| quantity | value |
|---|---|
| Pearson | **0.9426** |
| Spearman | 0.9416 |
| median abs diff (log P(Yes)) | 0.996 |

The device and the H100 4B track each other closely in both linear and rank terms, with a per-frame absolute-score offset of about 1 log-unit. This is the StudyD15 cross-stack finding at dense resolution: the H100 arm is vLLM native BF16 and the device is llama.cpp F16 GGUF, byte-identical prompts but different numerics, so absolute `log P(Yes)` differs while the ordering is preserved.

**Result 3, challenge average precision (paired clip bootstrap, 2,000 resamples, seed 0, 300 clips).**

| arm | challenge AP |
|---|---|
| Orin 4B F16 (device) | **0.5735** |
| H100 4B BF16 (reference) | 0.5764 |
| difference (Orin minus H100) | **-0.0029**, 95 percent CI [-0.0079, 0.0019] |

The confidence interval includes 0, so on the dense challenge set the device and the H100 4B arm are **statistically indistinguishable in average precision**. The absolute-score offset in Result 2 does not cost the device detection quality: ordering within a clip, which is what AP depends on, is preserved.

**Finding.** The Orin reproduces StudyD15 exactly on the integer overlap, correlates strongly with the H100 4B arm at dense resolution (Pearson 0.94), and matches the H100 4B arm on challenge AP with no significant difference. The device is a faithful stand-in for the H100 4B detection arm on this task, with a known constant-offset caveat on absolute `log P(Yes)` that does not affect ranking or AP. The analysis is implemented in `study_orin1_analyse.py` (`part1_analysis`) and written to `study_orin1_analysis.json`.

## 3. Part 2: controller compute overhead

The device controller signals are computed over the device's own recent window of the continuous score stream (the committed StudyD15 Orin Nexar scores, a real device stream). Each 4 Hz update computes, in plain Python (`statistics` only):

- window **median** and **IQR** (p75 minus p25) of `log P(Yes)`;
- a robust **relative score** `(current - median) / (IQR + eps)`;
- **rise** `= score(t) - score(t - 2 s)` (StudyE1's definition; 8 frames at 4 Hz);
- **instability** `=` median absolute successive difference across the window.

5,000 updates per window size, each update timed with `perf_counter`:

| recent window (frames) | mean per update | p50 | p99 | max | share of a 4 Hz tick (250 ms) |
|---|---|---|---|---|---|
| 20 | 8.4 us | 8.3 us | 9.3 us | 40.8 us | 0.003 percent |
| 60 | 19.3 us | 19.2 us | 20.2 us | 29.8 us | 0.008 percent |
| 240 | 80.0 us | 79.9 us | 85.4 us | 98.5 us | 0.034 percent |

**Finding.** The controller is effectively free on the Orin CPU: even the 240-frame window costs 80 microseconds, three to four orders of magnitude under the per-tick budget, and far cheaper than the 0.261 s optical-flow signal StudyE1 charged on the same CPU. Controller compute is not a factor in device feasibility.

## 4. Part 3: device recall latency on a warm D2 history

This measures a quantity the project had only assumed: the device's answer latency when a D2 history is already warm (in context) and a recall question is asked. Setup is StudyE7's 4B-on-D2-history, append-only. The S-EMBER DEV split is StudyB-baselines amendment 2 (`sember_split.is_dev`, split by `sha256(video_id)`, lowest 30 percent DEV, stratified by video length). Intersecting with the 74 E7 D2 questions on disk gives **20 DEV questions** (54 EVAL, 0 outside the split); 20 is at least 20, so the DEV questions are used.

**Warm history substrate.** One representative long D2 session (the longest E7 video, 578 frames) is warmed to two target sizes, and each of the 20 DEV questions is answered on top of it. This gives 20 x 2 = 40 measurements. The question text is appended to the cached image history; the history is reused from cache (`cache_n` equals the history token count), so only the question tokens are evaluated. Latency is content-independent and no DEV question content enters any fitted accuracy table (this is a latency profile, not an accuracy measurement).

**Results (20 DEV questions per size; clock pinned on all 40).**

| target | history tokens (cached) | question tokens evaluated | answer tokens | TTFT p50 | TTFT p90 (min, max) | total p50 | server prompt-eval p50 |
|---|---|---|---|---|---|---|---|
| ~11k | 11,029 | 123 (79 to 225) | 2 | **1.415 s** | 1.444 s (1.386, 1.487) | 1.478 s | 125 ms |
| ~28k | 28,039 | 123 (79 to 225) | 2 | **3.431 s** | 3.477 s (3.307, 3.573) | 3.513 s | 188 ms |

Both sizes are held by the device (28k is well within the 57,344 context and the ~40k-token ceiling StudyE8 reported). No 28k stop was needed.

**Decomposition.** The server's prompt-eval (the model work to process the 123 question tokens over the cached prefix) is only 125 ms at 11k and 188 ms at 28k. The rest of TTFT, **1.29 s at 11k and 3.24 s at 28k**, is client-side: building and serializing the request and, above all, resending and re-parsing the full image payload on every call, because the llama.cpp OpenAI-compatible API carries all history images in the body even when their KV is cached. This is exactly StudyD15b's mechanism: at ~9.7 ms per held frame, 122 frames predict 1.18 s and 311 frames predict 3.02 s of handling, matching the 1.29 s and 3.24 s residuals here.

**Finding.** Warm recall on the device is not near-free. TTFT scales at about **0.12 ms per history token** (28k over 11k is 2.54x tokens and 2.43x TTFT), dominated by payload resend rather than compute. Any orchestration rule that treated a warm device recall as cheap, or constant-time, is wrong on the Orin: a warm 11k recall costs about 1.4 s and a warm 28k recall about 3.4 s, and the cost grows with the history the recall carries.

## 5. Mechanism verification

The causal object of each part is a measured device quantity, not a policy comparison, so the relevant check is that each measured quantity is the thing named and is non-degenerate.

- **Part 1.** The measured quantity is the device `log P(Yes)` per N=1 request. It is non-degenerate (score range about -21 to 0, median -11.2, no constant). The reproduction gate is the explicit control: scoring the same integer-second frames the same way must reproduce StudyD15, and it does (Pearson 1.0, diff 0.0), so the harness is the StudyD15 harness and the dense scores are produced by the same mechanism. The H100 comparison is matched on `request_id` (same frame, same query) so the only varying factor is the stack, which is the StudyD15 cross-stack effect, not a frame or prompt difference.
- **Part 2.** The signal values vary across the real score stream (median, IQR, rise and instability are all non-constant); the timed region is exactly the signal computation over the rolling window. The cost is non-zero (8 to 80 us) and grows with window size as a full-window recompute should. No degeneracy.
- **Part 3.** `cache_n` equals the history token count (11,029 / 28,039) and `evaluated` equals the question tokens (median 123), so the measurement is genuinely a warm answer (history cached, question evaluated), not a cold prefill. The negative control is implicit and present: the model compute (server prompt-eval) is isolated at 125 to 188 ms, yet TTFT is 1.4 to 3.4 s, so removing compute would not remove the latency; the driver is the resend path, confirmed independently by the StudyD15b per-frame rate.

## 6. Results consistency check (6 checks)

1. **Cross-check against committed measurements.** Part 1: the Orin integer-second scores reproduce StudyD15 Part A exactly (Pearson 1.000000, max abs diff 0.0 over 10,660 shared requests), the strongest possible agreement with a prior committed measurement. The H100 4B agreement (Pearson 0.9426, median abs diff about 1 log-unit) matches StudyD15's cross-stack characterization (vLLM BF16 versus llama.cpp F16: ordering preserved, absolute score offset). Server prompt-eval warm (125 to 188 ms) sits in StudyE8's warm prompt-eval range. Part 3 TTFT residual matches StudyD15b's 9.7 ms per held frame (122 and 311 frames predict 1.18 and 3.02 s versus measured 1.29 and 3.24 s, ratio 1.09 and 1.07, under 2x). Part 2 has no prior committed value; its magnitude is far below StudyE1's 0.261 s flow-signal cost on the same CPU, as expected for simple statistics. Model sha256 and clock match StudyF4 / StudyE8.
2. **Physical plausibility.** Warm recall implies no rate faster than any committed curve: 123 evaluated tokens in 125 to 188 ms server time is about 650 to 980 tokens/s, in line with the Orin 4B prompt-eval rate; the 1.4 to 3.4 s TTFT is transport and parse of a 22 to 56 MB body over localhost, consistent with StudyD15b. Nothing is faster than a committed curve.
3. **Distribution sanity.** Part 3 TTFT is tight but not constant (11k p50 1.415, min 1.386, max 1.487; 28k p50 3.431, min 3.307, max 3.573), varying with the per-question evaluated-token count (79 to 225); no three-decimal constant where a distribution is expected. Part 2 timings vary across updates (max exceeds p99).
4. **Definition audit.** DEV is the StudyB amendment-2 `sember_split.is_dev` membership (20 of 74 E7 questions). Warm history is the KV-cached image prefix (`cache_n` equals history tokens). Recall latency is TTFT and total for a DEV question answered on that warm history. Controller signals are as defined in section 3, with `rise` matching StudyE1's `score(t) - score(t - 2 s)`.
5. **Claim linkage.** Part 3 bears on the orchestration recall-latency assumption (FORMULATION physical component: reconstruction and answer latency grow with context): it replaces an assumed rule with a measurement and shows warm device recall costs 1.4 to 3.4 s at 11k to 28k. Part 2 bears on controller feasibility: the device can run the controller for free. Part 1 bears on the device-score stand-in and extends StudyD15 to the dense 0.25 s grid: it supports using the Orin 4B as the detection arm (challenge AP indistinguishable from the H100 4B arm), with the documented absolute-offset caveat. No scoped-out quantity is measured (no cross-tier KV transfer).
6. **Proxy validity.** Part 3 uses one representative long D2 session as the warm-history substrate at two controlled sizes rather than each question's own video, and uses DEV question text for latency only. This is an explicit latency proxy: it is valid for latency (which depends on prompt length and output length, not on semantic pairing) and it is not used for any accuracy claim. Stated as a limitation, not a headline accuracy result.

## 7. Files

New scripts:
- `experiments/dashcam/study_orin1_dense.py` (Parts 1, 2, 3 runner; reuses `study_d15_orin_nexar.py`, `study_e8_device_warm.py`, `dev_fast_latency.py`, `experiments/orchestration/baselines/sember_split.py`)
- `experiments/dashcam/study_orin1_analyse.py`

New results:
- `results/cost/study_orin1/orin1_controller_overhead.json` (Part 2)
- `results/cost/study_orin1/orin1_recall_latency.jsonl` (Part 3, 40 rows), `orin1_recall_latency_meta.json`, `part3_run.log`
- `results/dashcam/study_orin1/orin1_meta.json`, `study_orin1_analysis.json`, `server.log.gz`, `tegrastats.jsonl.gz`
- `results/dashcam/study_orin1/orin1_dense_scores.jsonl.gz` (Part 1, 42,014 rows), `orin1_part1_frame_gate.json` (last batch gate), `part1_batches.jsonl` (per-batch provenance), `part1_run.log`

New report:
- `reports/study_orin1_dense.md` (this file)

Updated registries:
- `research/EXPERIMENTS.md` (StudyORIN1-dense row), `results/INDEX.md`, `research/STATUS.md`

All three parts are complete. Part 1 scored all 42,014 N=1 requests across the two frame batches; the dense frames were deleted after scoring and the integer-second StudyD15 set was preserved.
