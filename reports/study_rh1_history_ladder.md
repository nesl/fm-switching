# StudyRH1 — 32B cloud accuracy vs history size, and FP8-KV parity (S-EMBER)

(User's "H1". E-id RH1 because StudyH1/H2 are taken by the S-EMBER audit series.)
Pre-registered 2026-10-18 (research/EXPERIMENTS.md, StudyRH1) before any GPU run. Run 2026-10-18 16:15→17:16,
h100nvl GPU 3. **Stack: vLLM 0.31.0+cu129 (venv `~/.venvs/fm-switching-vllm`, torch 2.13.0+cu129), FlashAttention 3
(FLASH_ATTN backend, LM and ViT), CUDA graphs, prefix caching OFF.** All rows here, R1's K1/K3 included, are the same
vLLM/H100 stack, so no HF numbers are pooled in.

## Decision-rule outcomes

| rule (pre-registered) | result | outcome |
|---|---|---|
| H1c PARITY GATE: prompt ids exact and prompt tokens = R1 K1 | 10/10 ids exact; **845/845** H1c prompts = K1's | **PASSED** |
| FP8 PARITY: \|H1c − K1\| ≤ 1.5 pp and 95% CI includes 0 | **−0.83 pp [−2.06, +0.47]** | **FP8 PARITY** |
| runtime estimate ≤ 4 h | 1.13 h (actual 61 min) | ran in full |

## Answers

1. **Thinning the full history costs a lot, and it costs it everywhere.**
   - Half the frames (H1a, ~6.2k tokens) loses **−6.98 pp [−9.42, −4.53]** vs K1. A quarter (H1b, ~3.2k) loses
     **−9.47 pp [−12.46, −6.48]**.
   - The loss is not concentrated on the questions RECENT misses:
     - H1a − K1: −10.3 pp on RECENT-miss and −6.6 pp on RECENT-cover; DiD −3.8 [−12.9, +5.4].
     - H1b − K1: DiD −9.1 [−19.4, +1.1].
   - It is not explained by losing the evidence frame. H1a keeps an evidence frame on 842/845 questions, and on
     those it scores 32.7% vs K1's 39.7%.
2. **A thinned full history is worse than the recent window overall, but keeps part of the old-evidence benefit.**
   - Overall: H1a − K3 is −5.80 pp [−8.63, −3.05] and H1b − K3 is −8.28 pp.
   - On the 97 questions RECENT misses, H1a beats K3 by +7.2 pp (CI −1.9 to +16.5), vs +17.5 pp for full K1.
     The DiD vs K3 still holds: **+14.7 pp [+5.4, +24.7]**.
   - On the 748 questions RECENT covers, H1a is 7.5 pp below K3.
   - So the old-evidence advantage halves, and the density loss on everything else outweighs it.
3. **FP8 KV is accuracy-neutral at the pre-registered resolution.**
   - H1c 38.70% vs K1 39.53%: −0.83 pp [−2.06, +0.47].
   - The answer letter agrees on 93.7% of questions (53 differ: 9 FP8-only right, 16 bf16-only right).
   - For scale, bf16 K1 re-run single vs batched on the first 50 questions was 100% identical in text. So FP8 does
     change individual answers, about 6% of them, but with no measurable net accuracy effect.
   - FP8 also doubles KV capacity: 64,624 → 129,280 tokens on this server.
4. **For the controller:**
   - FP8 is the capacity lever with no detectable accuracy cost.
   - Frame thinning is not a free lever. Halving history tokens costs ~7 pp, which is more than K1's whole
     advantage over RECENT (+1.2 pp).

## Accuracy vs prompt tokens (845 questions each; Wilson 95%)

| cell | input | frames (median) | prompt tokens (mean; median; min–max) | accuracy | RECENT-miss (97) | RECENT-cover (748) |
|---|---|---|---|---|---|---|
| H1b | RICH 25%, R1 per-frame res. (352×256 typ.) | 58 | 3,190; 3,239; 544–3,532 | **30.06%** [27.1, 33.2] | 24.7 | 30.7 |
| H1a | RICH 50%, R1 per-frame res. | 116 | 6,204; 6,351; 966–6,783 | **32.54%** [29.5, 35.8] | 32.0 | 32.6 |
| K3 (R1) | RECENT 120 s, higher res. (512×384 typ.) | 121 | 12,256; 12,437; 1,810–12,734 | **38.34%** [35.1, 41.7] | 24.7 | 40.1 |
| K1 (R1) | RICH full (≤ 256), bf16 KV | 231 | 12,269; 12,597; 1,810–13,196 | **39.53%** [36.3, 42.9] | 42.3 | 39.2 |
| H1c | RICH full, **FP8 KV** | 231 | identical to K1 | **38.70%** [35.5, 42.0] | 42.3 | 38.2 |

Along the RICH ladder, accuracy rises monotonically with tokens: 30.1 → 32.5 → 39.5. The 6.2k → 12.3k step is worth
7 pp, and the 3.2k → 6.2k step 2.5 pp (H1a − H1b +2.49 [−0.23, +5.18]). K3 shows that spending the same 12.3k
tokens on 2× the resolution of the last 120 s gets within 1.2 pp of K1.

## Paired tests (video-clustered bootstrap, 2,000 resamples, seed 0; pp)

| contrast | overall | RECENT misses | RECENT covers | DiD (miss − cover) |
|---|---|---|---|---|
| H1a − K1 | **−6.98 [−9.42, −4.53]** | −10.31 [−19.27, −2.02] | −6.55 [−9.20, −3.94] | −3.76 [−12.93, +5.40] |
| H1b − K1 | **−9.47 [−12.46, −6.48]** | −17.53 [−27.89, −7.59] | −8.42 [−11.47, −5.35] | −9.10 [−19.43, +1.05] |
| H1c − K1 | −0.83 [−2.06, +0.47] | 0.00 [0, 0] | −0.94 [−2.31, +0.53] | +0.94 [−0.53, +2.31] |
| H1a − K3 | **−5.80 [−8.63, −3.05]** | +7.22 [−1.92, +16.50] | −7.49 [−10.29, −4.62] | **+14.70 [+5.40, +24.73]** |
| H1b − K3 | **−8.28 [−11.34, −5.42]** | 0.00 [−9.00, +9.46] | −9.36 [−12.64, −6.32] | +9.36 [−0.14, +19.35] |
| H1c − K3 | +0.36 [−2.48, +3.13] | +17.53 [+7.14, +28.13] | −1.87 [−4.54, +0.81] | +19.40 [+8.91, +30.15] |

Own-construction evidence coverage (any kept frame inside the annotated interval):
- H1a loses it on 3 questions; neither H1a nor K1 gets any of them right.
- H1b loses it on 19 questions: H1b 15.8% vs K1 26.3% on those, and 30.4% vs 39.8% on the 826 it keeps. The H1b
  loss is therefore almost entirely on questions whose evidence it still has.
- This split was pre-registered as underpowered (3 and 19 questions).

## Design (as pre-registered)

- **Server and requests are R1's, imported unchanged** (`study_r1_vllm`):
  - Qwen3-VL-32B-Instruct @0cfaf481; gmu 0.90, max_model_len 32768, `--limit-mm-per-prompt {image 0, video 1}`,
    engine-level `{fps 1.0, do_sample_frames false}`, `--trust-request-mm-kwargs`, localhost-bound.
  - Frames go as one video of lossless PNGs with per-request `media_io_kwargs` (frames_indices, total_num_frames,
    num_frames −1).
  - Greedy, max_tokens 512, seed 42, closed loop at concurrency 8, R1's answer parsing. Same 845 questions in R1
    order.
- **Subsampling.** Keep k = max(1, round(n·f)) of R1's n RICH frames at round(i·(n−1)/(k−1)), StudyO's own
  RICH-cap rule. Order is kept, and the set is padded to even with the last frame, as qwen_vl_utils does.
- **Resolution held at R1's** (fixed in advance; it is what makes the token count halve):
  - The pixels are R1's final-size uint8 frames, indexed.
  - Rerunning StudyO's pipeline on fewer frames would let the processor's total-pixel budget upscale each frame,
    as RECENT shows (121 frames at 512×384 vs RICH's 352×256), and the prompt would stay near 12.5k.
- **Expected ids** (`study_rh1_inputs.py`, .venv, transformers 5.10.2, CPU):
  - The HF processor runs on exactly the frames vLLM receives.
  - Given all frames it reproduces R1's expected ids exactly (3/3 checked).
  - Grid h,w is asserted equal to R1's for every question.
- **H1c** is R1's RICH request byte-for-byte with `--kv-cache-dtype fp8`. vLLM warns that FP8 without calibrated
  scales may cost accuracy; no scales were supplied (default 1.0), and that is the configuration tested.
- **Wall time:** H1a 16.0 min, H1b 8.0 min, H1c 32.5 min (R1 K1 bf16: 34.3 min).

## Mechanism verification

1. **Causal chain.**
   - FORMULATION.md's semantic component of Context Inertia: cheaper representations discard task-relevant
     information in a workload-dependent way.
   - Here the cheaper representation is the cloud's history at fewer frames, which means fewer tokens and less KV
     and reconstruction cost.
   - Fewer frames lower both the chance that an evidence frame is kept and the temporal density around it, so
     accuracy should fall.
   - If K1's value were only the old evidence, the fall should concentrate on RECENT-miss questions.
   - FP8 KV halves per-token KV and should leave answers unchanged if quantisation noise is benign.
2. **Instantiated quantities.**

   | link | quantity | value / range | varies as claimed? |
   |---|---|---|---|
   | representation cost | prompt tokens (mean) | 12,269 → 6,204 → 3,190 | yes (×0.51, ×0.26) |
   | evidence retention | own evidence_covered | 845 → 842 → 826 | yes, but barely |
   | temporal density | frames (median) | 231 → 116 → 58 | yes |
   | accuracy | correct | 39.5 → 32.5 → 30.1% | yes |
   | KV precision | KV dtype / capacity | bf16 64,624 vs fp8 129,280 tokens | yes, by flag |
   | prompt identity across KV dtypes | prompt tokens H1c vs K1 | equal on 845/845 | constant, by design |

3. **Representative unit.** Question 42CFFFAF… (video 1004154028515092, qt 568 s):
   - K1: 256 frames, 12,617 tokens.
   - H1a: 128 frames (every other), 6,369 tokens, ids exact.
   - H1b: 64 frames, 3,244 tokens, ids exact.
   - Each request is one video and one text block. The KV used is the whole prompt (no prefix caching), and the
     outcome is the parsed letter vs the key.
4. **Controls.**
   - **H1c is the path control.** Same server code, same frames as K1, only the KV dtype changes, and accuracy is
     unchanged (−0.8 pp, CI incl. 0). That rules out a regression of the harness or server between R1 and RH1 as the
     cause of H1a/H1b's drop.
   - **bf16 batch-composition noise.** K1 single vs batched: 50/50 identical.
5. **Alternative explanations for the H1a/H1b drop.**
   - (a) **Temporal density per se.** The model needs consecutive views to track actions and locations: the largest
     category drops are sequential_action 45 → 31% and location_trace 31 → 23%.
   - (b) **Qwen3-VL's temporal patch (2).** It merges frame pairs into one token group. At half density each pair
     spans ~4 s instead of ~2 s, so the merged representation blurs motion.
   - (c) **The timestamp tokens** interleaved per group now carry a different cadence.
   - None of (a)–(c) is "losing the evidence frame", which (2) above excludes. This experiment cannot separate
     (a) from (b) or (c). Repeating the frames to keep pairs 1 s apart would.

**Null classification.** The FP8 result is a *real negative* for an accuracy effect: the mechanism is present
(KV precision changed, 6.3% of answers changed), the paired test has ±1.3 pp resolution, and no net effect appears.

## Results consistency check

1. **Cross-check against committed measurements.**

   | quantity | RH1 | prior | source | ratio |
   |---|---|---|---|---|
   | KV capacity bf16 (R1 server config) | 64,624 | 64,624 | R1 run meta (all 7 servers) | 1.000 |
   | KV capacity fp8 | 129,280 | 130,720 (R5 config, image limits) | R5 | 0.99 |
   | full-RICH prompt tokens | = K1 on 845/845 | K1 | R1 requests | 1.000 |
   | full-RICH accuracy (fp8 vs bf16) | 38.70% | 39.53% | R1 K1 | 0.98 |
   | batched wall time, full RICH | 32.5 min (fp8) | 34.3 min (bf16) | R1 log | 0.95 |

   R5's FP8 capacity (130,720) differs by 1% because R5 used image inputs (encoder-cache profiling differs).
2. **Physical plausibility.**
   - Batched throughput is 845 × 6,204 tokens in 16.0 min ≈ 5.5k prompt tok/s (H1a), and 845 × 3,190 in 8.0 min ≈
     5.6k tok/s (H1b), vs 845 × 12,269 in 34.3 min ≈ 5.0k tok/s (K1).
   - Wall time scales linearly with tokens, as expected without prefix caching. The sequential 5-question latency
     is 1.7 s (H1a) and 0.8 s (H1b) vs 3.7 s (K1), also linear.
3. **Distribution sanity.**
   - Prompt tokens spread 966–6,783 (H1a) and 544–3,532 (H1b).
   - Predicted-letter distributions match K1's (no letter collapse; no unparsable answers).
   - Category-level H1a − K1 changes range from −2 to −14 pp, with spatial_aware_reasoning +4 pp, rather than a uniform shift.
4. **Definitions.**
   - RICH, RECENT, `evidence_covered` and answer parsing are StudyO's/R1's (code reused).
   - "50% of the frames" means round(n/2) of R1's capped list, so a 67-frame question keeps 34.
   - Prompt tokens are vLLM's `usage.prompt_tokens`.
5. **Claim linkage.**
   - **Supports** the semantic component of Context Inertia: the cheaper history representation discards
     task-relevant information. On S-EMBER the discard is broad, not confined to old evidence.
   - **Bears on the controller's representation choice:**
     - A thinned full history is dominated by the recent window at higher resolution, which is more accurate at
       2× tokens, while thinning saves 2× tokens for a −5.8 pp loss vs RECENT.
     - FP8 KV is a free 2× capacity lever.
6. **Proxy validity.** `evidence_covered` (any kept frame inside the annotated interval) is StudyO's proxy for "the
   input contains the evidence". Here it saturates (842 and 826 of 845), so it cannot explain H1a/H1b; it is
   reported, not used for a headline.

## Caveats

- One run per cell, greedy. bf16 run-to-run noise on this stack is ≈0 (50/50 identical), so the CIs are
  sampling-only.
- H1a/H1b are a *uniform* thinning at fixed resolution. Other representations at the same token budget are not
  measured here: higher resolution × fewer frames, keyframe selection, or a recent window plus sparse older frames.
  K3 suggests resolution matters.
- FP8 was tested at default (uncalibrated) scales, on full RICH only.

## Files

- `experiments/sember/study_rh1_inputs.py` (.venv), `study_rh1_history_ladder.py` (vLLM venv),
  `study_rh1_analyse.py` (.venv)
- `results/sember/study_rh1/`:
  - `study_rh1_inputs_manifest.jsonl(.gz)`
  - `study_rh1_requests_h100nvl.jsonl.gz`
  - `study_rh1_parity_{bf16,fp8}_h100nvl.json`
  - `study_rh1_run_meta_h100nvl.json`
  - `study_rh1_results_h100nvl.json`
- Frame indices and expected ids are in `~/.cache/fm-switching/rh1_inputs` (outside the repo, 37 MB); pixels are
  R1's inputs.
