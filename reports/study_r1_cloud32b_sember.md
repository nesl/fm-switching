# StudyR1 — the 32B cloud tier on S-EMBER (accuracy + single-request latency)

**Host:** h100nvl (`sn4622120321`), **GPU 3**, exclusive (session watchdog; only our processes ever appeared) ·
**Run:** 2026-10-17 13:49 → 16:29 · **Pre-registered:** `research/EXPERIMENTS.md` row StudyR1, written before any GPU run.

**Stack (all 32B numbers):** vLLM 0.31.0+cu129, torch 2.13.0+cu129, transformers 5.17.0 (venv
`~/.venvs/fm-switching-vllm`). Server settings, as StudyX:
- FLASH_ATTN (FA3), CUDA graphs, bf16;
- `gpu_memory_utilization` 0.90, `max_model_len` 32,768;
- **prefix caching OFF**;
- added for video: `--limit-mm-per-prompt {"image":0,"video":1}`, `--mm-processor-kwargs {"fps":1.0,"do_sample_frames":false}`,
  `--trust-request-mm-kwargs`, bound to `127.0.0.1`.

**Models:** Qwen3-VL-32B-Instruct @`0cfaf481`, Qwen3-VL-32B-Thinking @`7edd10ff`.

**Comparison rows** (4B/8B) are StudyO's committed `study_o_q4_trials_fa2.jsonl`: HF transformers 5.10.2,
flash_attention_2, on the **A6000**. Every 32B-vs-StudyO difference is therefore **cross-stack and cross-host**,
labelled so throughout.

## Decision-rule outcomes (pre-registered)

All differences are paired on the 845 questions, with a video-clustered bootstrap (2,000 resamples, seed 0,
234 videos).

| test | estimate | 95% CI | outcome |
|---|---|---|---|
| **CLOUD HELPS:** K1 (32B-I × RICH) − 4B-I × RECENT | **+6.75 pp** | [+3.13, +10.54] | **HOLDS** (CI excludes 0) |
| CLOUD HELPS (Thinking): K2 (32B-T × RICH) − 4B-I × RECENT | +1.07 pp | [−2.36, +4.48] | does not hold |
| **HISTORY GATES THE CLOUD:** DiD of (K1 − K3), RECENT misses minus RECENT covers | **+18.46 pp** | [+8.02, +29.36] | **HOLDS** |
| — K1 − K3 where RECENT misses the evidence (n = 97) | +17.53 pp | [+7.14, +28.13] | |
| — K1 − K3 where RECENT covers it (n = 748) | −0.94 pp | [−3.56, +1.64] | null (control) |
| **CAPABILITY GAP** (substitute): K1 − 8B-I × RICH (same frames) | **+3.31 pp** | [+0.12, +6.57] | positive overall |
| — where RECENT misses / covers | +2.06 / +3.48 pp | [−8.14, +12.77] / [+0.00, +6.86] | |
| — DiD (misses − covers) | −1.41 pp | [−12.39, +9.51] | **no evidence the size gain depends on coverage** |
| Capability gap vs 4B-I × RICH (as specified) | — | — | **NOT AVAILABLE**: StudyO never ran 4B-I × RICH |
| Escalation (remote = K1), e = 0.2: P4 top-e − random | +0.43 pp | [−1.40, +1.89] | P4 does **not** beat random |
| — question_time top-e − random | +0.54 pp | [−1.34, +1.87] | does not beat random |

**Reading:**
- **The two gains are separable.** The history gain (RICH vs RECENT at the *same* 32B model) is concentrated
  entirely in the 11.5% of questions whose evidence the last 120 s miss: +17.5 pp there, −0.9 pp elsewhere.
- **Size alone is small and uniform.** 32B vs 8B on the same RICH frames gives +3.3 pp, with no detectable
  dependence on coverage.
- **This reproduces StudyO's finding at 32B.** StudyO's 8B-I RICH − 4B-I RECENT was +19.6 pp on misses vs +1.3 pp on
  covers in this pool (StudyO reported +15.4 pp). The history effect is about the same size at 32B (K1 − K3:
  +17.5 / −0.9).
- **Model size adds a level shift, not a history interaction.**
- **32B-Thinking at the model card's VL sampling is worse than 32B-Instruct:** K2 − K1 = −5.68 pp, CI
  [−8.72, −2.62].

## Accuracy

| cell | stack | n | accuracy | Wilson 95% | RECENT misses (n = 97) | RECENT covers (n = 748) |
|---|---|---|---|---|---|---|
| **K1** 32B-I × RICH (greedy, 512) | vLLM / H100 | 845 | **39.53%** | 36.3–42.9 | **42.3%** | 39.2% |
| **K3** 32B-I × RECENT (greedy, 512) | vLLM / H100 | 845 | **38.34%** | 35.1–41.7 | **24.7%** | 40.1% |
| **K2** 32B-T × RICH (card VL sampling, 16,384) | vLLM / H100 | 845 | **33.85%** | 30.7–37.1 | 32.0% | 34.1% |
| 4B-I × RECENT (local) | HF fa2 / A6000 | 845 | 32.78% | 29.7–36.0 | 20.6% | 34.4% |
| 8B-I × RICH | HF fa2 / A6000 | 845 | 36.21% | 33.0–39.5 | 40.2% | 35.7% |
| 4B-T × RICH (CFG-A, 8,192) | HF fa2 / A6000 | 845 | 30.89% | 27.9–34.1 | 26.8% | 31.4% |
| 4B-I × RICH | — | — | **not available** | | | |

`evidence_covered` comes from the RECENT construction (identical to StudyO's 4B-I × RECENT field for all 845). RICH
covers the evidence for 100% of questions.

**K2 detail:**
- **Settings:** model card "Generation Hyperparameters / VL" verbatim: `top_p=0.95`, `top_k=20`,
  `repetition_penalty=1.0`, `presence_penalty=0.0`, `temperature=1.0`. The card's `out_seq_length=40960` was replaced
  by `max_tokens` 16,384, as specified. Seed 42 on every request.
- **Termination:** 840 of 845 closed `</think>`. 5 hit 16,384 unclosed, and each is scored wrong.
- **Lengths:** think tokens median 135, p90 455; completion tokens median 139.
- **Accuracy:** 34.0% on the closed traces alone.

## Escalation policies (local = 4B-I × RECENT, remote = K1)

End-to-end accuracy at escalation rate e. "random" is analytic, as in `study_o_q4_analyze.py`. P4 scores were
recomputed with StudyO's own `train_p4` (unchanged; StudyO videos excluded from training). They reproduce StudyO's
published policy (d) = 33.85% at e = 0.2 exactly.

| e | never | always | random | P4 top-e | question_time top-e | evidence oracle | accuracy oracle |
|---|---|---|---|---|---|---|---|
| 0.1 | 32.78 | 39.53 | 33.46 | 33.96 | 33.37 | 34.20 | 42.72 |
| **0.2** | 32.78 | 39.53 | 34.13 | **34.56** | 34.67 | 36.57 | 51.01 |
| 0.3 | 32.78 | 39.53 | 34.80 | 35.38 | 33.73 | 37.87 | 51.01 |

- **No practical router captures the gain.** Escalating everything gains +6.75 pp, but P4 and question_time top-e
  stay within noise of random escalation.
- **There is plenty of headroom.** The accuracy oracle reaches 42.7–51.0%; even the evidence oracle (which knows
  the true evidence distance) adds only +2.4 pp over random at e = 0.2.
- This is StudyO's K4 conclusion again, now with a 32B remote.
- With remote = K2 (Thinking), P4 − random at e = 0.2 is +1.56 pp, CI [−0.14, +3.07]. That doesn't hold either.

## Clean single-request latency (first 50 questions, one request at a time, prefix caching off)

Request bodies were built before the clock started. TTFT is from request submit to the first streamed token, and
includes HTTP transfer of the PNG frames, server-side image decode, vision encoding and prefill.

| | prompt tokens median (min–max) | TTFT median / p90 / max (s) | total latency median / p90 (s) | generated |
|---|---|---|---|---|
| K1 (RICH, ≤256 frames) | 12,610 (11,460–13,181) | **4.24** / 4.43 / 4.86 | 4.28 / 4.47 | 2 |
| K3 (RECENT, ≤121 frames) | 12,436 (11,460–12,558) | **4.18** / 4.32 / 4.47 | 4.21 / 4.35 | 2 |

**Reading:**
- **Latency is set by prompt size, not frame count.** RICH and RECENT prompts are the same size: StudyO's processor
  budget gives RECENT larger frames. So a 32B escalation of either construction costs about 4.2 s, almost all of
  it before the first token.
- **Batched throughput** (concurrency 8): K1 845 requests in about 35 min, about 2.4 s per request.

## Parity (inputs identical to StudyO)

- **Gate:** passed on 10 + 10 questions. vLLM prompt tokens equal StudyO's `n_input`, frame counts are equal, and
  vLLM's returned prompt token ids equal the HF pipeline's exactly (`study_r1_parity_h100nvl.json`).
- **Every request:** all 2,650 R1 requests had `prompt_tokens` equal to the builder's expected count.
- **How:** `experiments/sember/study_r1_inputs.py` runs StudyO's own code (cache_video, select, build_messages,
  process_vision_info, processor with StudyO's min/max pixels and VideoMetadata). It applies the processor's final
  resize in StudyO's stack and sends the frames losslessly (PNG) at final size.
- **Pixel-level difference vs StudyO:**
  - **Cause:** StudyO's processor received float frames, while vLLM decodes images to uint8, so bicubic overshoot
    outside [0, 255] is clipped.
  - **Size:** mean |Δ| = 0.0018 in normalised units (about 0.2/255), max 0.128 at clipped pixels.
- **Three earlier gate attempts** failed with HTTP 400 *before any token count*. vLLM 0.31 rejects per-request
  `mm_processor_kwargs` / `media_io_kwargs` without `--trust-request-mm-kwargs`, and its `video/jpeg` loader keeps
  only 32 frames unless `num_frames = -1`. These were harness fixes, kept as `study_r1_parity_attempt{1,2,3}_http400_*.json`.

## Mechanism verification (history gating)

1. **Causal chain.**
   - The cloud tier holds the device's full history (RICH). The device's pruned window (RECENT) loses evidence older
     than 120 s.
   - FORMULATION.md: the semantic component of Context Inertia is that cheaper representations discard
     task-relevant information in a workload-dependent way.
   - Where the window misses the evidence, the cloud's history should raise accuracy. Where it doesn't, history
     should add nothing.
2. **Instantiated quantities.**

   | link | quantity | value | varies? |
   |---|---|---|---|
   | window loses evidence | RECENT `evidence_covered` | 0 for 97 / 845 (11.5%) | yes |
   | cloud keeps it | RICH `evidence_covered` | 845 / 845 | yes, by construction |
   | accuracy responds | K1 − K3 | +17.5 pp (misses) vs −0.9 pp (covers) | yes |

3. **Trace of one unit.** Question 42CFFFAF… (video 1001141161985610, qt 300 s):
   - **RICH:** 256 frames (0–300 s), 12,617 prompt tokens, grid 128 × 22 × 16.
   - **RECENT:** 121 frames (180–300 s), 12,442 tokens, grid 61 × 32 × 24.
   - The same text and answer extraction apply to both; per-request rows are in `study_r1_requests_h100nvl.jsonl.gz`.
4. **Negative control.** On covered questions the mechanism is absent, and K1 − K3 = −0.94 pp (CI includes 0). The
   effect collapses to the null where it should.
5. **Alternative explanation.** RICH could help simply because it has more frames. But RECENT has *more tokens per
   frame* and the same total budget, and the effect is absent on covered questions. Frame count therefore doesn't
   explain it; evidence coverage does.

## Results consistency check

1. **Cross-check against committed measurements.**

   | quantity | StudyR1 | prior | source | ratio |
   |---|---|---|---|---|
   | prompt tokens (RICH / RECENT) | identical ids | StudyO `n_input` | parity gate | 1.000 |
   | evidence_covered (RECENT) | 748 / 845 | 748 / 845 | StudyO 4B-I × RECENT | 1.00 |
   | history effect on misses (RICH − RECENT) | +17.5 pp (32B-I, same model) | +19.6 pp (8B-I RICH − 4B-I RECENT) | StudyO fa2 | 0.89 |
   | P4 policy (d) at e = 0.2, remote 8B-I | 33.85% | 33.85% | `reports/study_o_q4_results_845_fa2.md` | 1.000 |
   | 32B-I answer drift vs HF | — | 5% (ERQA) | StudyX drift check | — |

   K1 and 8B-I × RICH give the same answer letter on 60% of questions.
2. **Physical plausibility.** About 12.6k prompt tokens with 256 frames in 4.2 s is about 3k tok/s end to end, plus
   vision encoding and image transfer. For a 32B model that is within prefill compute (about 0.8 PFLOP for the LM
   prefill alone). It is not a caching artifact: prefix caching is off and every prompt is unique.
3. **Distribution sanity.** Latencies range 3.6–4.9 s across 50 requests. Accuracies have Wilson CIs. K2's lengths
   range from tens of tokens to 16,384.
4. **Definitions.**
   - RICH, RECENT, `evidence_covered` and answer extraction are StudyO's (code reused).
   - Correct = predicted letter equals the key and, for K2, the thinking closed.
   - The question pool is StudyO's 845.
5. **Claim linkage.**
   - **Supports:** the cloud's value on S-EMBER is dominated by *history the device has pruned*; model size adds
     about 3 pp. That means the device/cloud decision is a state-placement question more than a capability one.
   - **Weakens:** routing by question text or time (P4, question_time); neither beats random.
6. **Proxy validity.** `evidence_covered` (any sampled frame inside the annotated answer interval) is a proxy for
   "the input contains the evidence". It is StudyO's definition, used unchanged.

## Caveats

- **Cross-stack and cross-host.** 32B rows are vLLM on H100; 4B/8B rows are HF on A6000. StudyX measured 5% answer
  drift between these stacks for 32B-I on ERQA, so paired differences of a few pp carry that noise. The history
  effect is *within* the 32B stack (K1 vs K3) and is not affected.
- **4B-I × RICH is not available,** so the specified capability-gap test is replaced by K1 − 8B-I × RICH. That is a
  4× size step, not 8×.
- **K2 uses temperature 1.0** (card) and one seed. 5 runaways at 16,384 are scored wrong.
- **The misses subset is n = 97,** so its CIs are wide.
- **Latency** is HTTP-to-localhost with PNG frames and one request at a time. It is not a loaded-server latency
  (that is R5).

## Files

- **Code (`experiments/sember/`):**
  - `study_r1_fetch_videos.py`
  - `study_r1_inputs.py` (original `.venv`)
  - `study_r1_vllm.py` (vLLM venv)
  - `study_r1_p4_scores.py` (isolated venv `~/.venvs/fm-switching-p4`: sentence-transformers 5.1.1, sklearn 1.7.2,
    torch 2.8.0+cpu)
  - `study_r1_analyse.py`
- **Data (`results/sember/study_r1/`):**
  - `study_r1_requests_h100nvl.jsonl.gz` (2,650 requests incl. timing and latency, full text)
  - `study_r1_inputs_manifest.jsonl.gz` (1,690 question × construction rows)
  - `study_r1_parity_h100nvl.json` (+ 3 HTTP-400 attempt files)
  - `study_r1_p4_scores.json`
  - `study_r1_run_meta_h100nvl.json`
  - `study_r1_results_h100nvl.json`
- **Not in the repo:**
  - videos: 30.2 GB, `~/.cache/fm-switching/sember_videos`
  - 1 fps frame cache: 11 GB, `~/.cache/fm-switching/sember_frames`
  - per-request frame arrays: 78 GB, `~/.cache/fm-switching/r1_inputs`
- **Logs:** `logs/queue4_*`, `logs/r1_*`, `logs/study_x_server_32B{I,T}_1017_*.log`
