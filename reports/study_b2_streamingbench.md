# StudyB2-streamingbench: Qwen3-VL 4B / 8B / 32B, Instruct and Thinking, on StreamingBench

**E-id:** StudyB2-streamingbench (pre-registered 2026-11-07 ~11:10, before any StreamingBench inference; authorised by the user).

**Status:** COMPLETE 2026-11-08 06:05 (all six arms, three shards, plus the latency sample). Final deletion is recorded at the end.

**Purpose:** descriptive per-question rows for the full 6-arm matrix. No policy, threshold or time-shift claim.

## Data (written before inference)
- **Source:**
  - HF `mjuicem/StreamingBench` @ `48872fa707124474ce4c5172ddc58efb8bc88058`;
  - code `THUNLP-MT/StreamingBench` @ `89299232c4cc1cc3721951173c5f107b48cf6877` (local clone at that commit);
  - flash's manifest `results/datasets/download_manifest.json`.
- **Pulled from flash's verified copy with `fmpull`** (fmnet-flash alias), as zips. Each zip is verified against the HF LFS sha256 and size in flash's `preflight.json` before use (`experiments/datasets/sb_prepare_shard.py`).
- **Extraction:** only the `sample_N/video.mp4` members are extracted (CRC-32 checked), into flash's layout `extracted_by_task/<task>/sample_N/`.
- **ffprobe:** every video is probed and compared with flash's `ffprobe.jsonl`.
- **Annotations:** identical to flash's index (`results/benchmarks/study_b1_flash/index/streaming_bench.jsonl`) on all 3,250 runnable questions (question text, options, gold, time_stamp, task, video): **0 mismatches** (checked 2026-11-07).
- **Skipped tasks (not run), with upstream reasons:**

  | file | questions | reason |
  |---|---|---|
  | Omni_Source_Understanding.csv | 1,000 | requires audio by upstream definition (README.md:39 "integrate visual and audio inputs") |
  | Proactive_Output.csv | 250 | upstream scoring cannot be applied unchanged: `StreamingBenchProactive.py` polls the model once per second up to `ground_truth_time_stamp` + 4, and `count.py:43-57` scores the output time within ±2 s. It also needs video after the query time |
  | Proactive_Output_50.csv | 50 | same |

  The 502 questions whose video is missing upstream (flash's crosscheck) are all in these skipped files, so every runnable question has its video.
- **Runnable:** Real_Time_Visual_Understanding 2,500 + Contextual_Understanding 500 (Anomaly 250, Misleading 250) + Sequential_Question_Answering 250 = **3,250 questions**.
- **Query time:** t = `time_stamp` (HH:MM:SS → seconds), cited from `src/benchmark/StreamingBench.py:41-50` and `src/utils/video_execution.py:4,23-25`, which cut the clip [0, t]. Same definition as flash's `temporal_field_semantics.json`. No runnable task needs video after t.
- **Options:** the CSV list. A "<letter>." prefix gives the letter (flash's rule, so annotations match). Two upstream anomalies are kept as given:
  - `Sequential_Question_Answering_sample_14_1` has a name starting "A." (shown as A "Lebrun.").
  - `Sequential_Question_Answering_sample_41_5` is lettered A, B, B, D (shown verbatim; gold A; floor 1/4).
- **Shards by upstream archive** (the disk cannot hold every zip plus its extraction at once):

  | shard | archives (zips) | questions |
  |---|---|---|
  | 1 | Sequential QA 1–25 and 26–50, Anomaly, Misleading, Real-Time 1–50 / 51–100 / 101–150 / 201–250 | 1,750 |
  | 2 | Real-Time 151–200 / 251–300 / 301–350 | 750 |
  | 3 | Real-Time 351–400 / 401–450 / 451–500 | 750 |

  - Each shard: pull → verify → extract → ffprobe → all six arms → delete that shard's zips and videos.
  - **Exception:** the 49 videos needed by the latency sample are kept until it has run (25 in shard 1, 8 in shard 2, 16 in shard 3).

## Matrix, input and controls (written before inference)
- **Arms, decoding, stack and input:** exactly as StudyB2-ovo-rtv (`reports/study_b2_ovo_rtv.md`).
  - 4BI / 8BI / 32BI greedy, max_tokens 64, logprobs top 20.
  - 4BT / 8BT / 32BT card VL sampling (T 1.0, top_p 0.95, top_k 20, repetition 1.0, presence 0.0), max_tokens 16,384, seed 0.
  - Pinned revisions as listed there.
  - `b1_common.py` unchanged (SHA verified every step).
  - RECENT 9 frames over [max(0, t − 3), t]; HISTORY 37 over [0, t]; 768 × 432 PNG.
  - StudyB1's fixed template.
- **Here, unlike OVO / RTV, 32BI and 32BT are run** (all six arms).
- **Order:**
  - Within each shard: Instruct 4B → 8B → 32B, then Thinking 4B → 8B → 32B.
  - Each arm runs batches of 200 alternating RECENT then HISTORY across the three parts, in a seed-0 task-stratified order over all 3,250 questions (`b2_sb.fixed_order`, b1_common's algorithm). Any stopping point is a valid sample.
- **Grey control:** the first 100 questions of that order (grey pixels, real question and options), per arm and input, run with shard 1.
- **Scorers:**
  - **Upstream:** `src/data/count.py:65-72`, `response[0] == answer`.
    - **Recorded deviation:** the answer region is left-stripped of whitespace first, because a Thinking answer region begins with "\n\n" after `</think>`. Case is not changed.
    - Upstream drops empty responses from its denominator; here they count wrong and are reported separately.
  - **Strict:** exactly one standalone option letter.
  - Thinking is scored after `</think>`. Truncated, empty and unparsed responses are reported separately.
- **Frame identity:** every arm's frame SHA-256 lists are compared online with this dataset's 4BI rows (mismatch → HALT), and across all arm pairs in the analysis.
- **Repeat control (Step 4):**
  - Before the sweep, 4BI runs the first 10 RECENT questions of each part twice (30 pairs).
  - Below 99 % answer agreement, or any frame difference, halts the queue.
- **Latency sample:**
  - After the full matrix, with nothing else of ours running.
  - 50 per arm × input, the first 50 of the fixed order, StudyD10's method (cold, single request, first per load discarded, neighbour steps flagged). Localhost.
- **Stop rules:** as StudyB2-ovo-rtv.

## Mechanism verification (Steps 1, 2 and 5 before inference; Steps 3 and 4 from smoke and repeat control before the sweep)
**Step 1: causal chain.** The same as StudyB2-ovo-rtv:
- On identical causal input, model size and reasoning mode change per-question correctness.
- FORMULATION.md §Regime uncertainty / §Decisions.
- Identical frames and prompt → arms differ only in weights or mode and decoding → answers differ → the upstream (and strict) scorer scores them differently → correctness differs.

**Step 2: instantiate each link** (filled from the rows).

| causal link | implementing quantity | value / range in this run | varies as expected? | evidence |
|---|---|---|---|---|
| identical input across arms | frame SHA-256 list per (item, input, grey) vs 4BI; prompt tokens | 0 mismatches over 15 pairs × 6,496; prompt tokens equal within a mode, +2 Thinking | CONSTANT by design (+2 Thinking prefix) | online check + analysis |
| arm differs | revision / decoding | 6 arms | yes, by construction | run meta |
| reasoning mode active | Thinking completion tokens; `</think>` closed | p50 152–180 (RECENT), p90 720–1,370 (HISTORY), max 16,384; no answer region on 4 of 3 × 6,496 | > 0 and varies | rows |
| answer differs | per-question disagreement on matched items | correctness 9–17 %, answers 14–29 % (repeat control 0 / 30) | > repeat-control disagreement | rows |
| correctness differs | matched difference, both scorers | size +0.024 to +0.058 (upstream); mode −0.016 to +0.011 (upstream), up to +0.081 (strict) | — | analysis |

**Step 3: trace one request per arm** (`b2_smoke_<arm>.jsonl.gz`, 2026-11-07 11:05–11:17, before any sweep).

The request: `Real-Time Visual Understanding_sample_123_5` (Text-Rich Understanding), t = `time_stamp` 00:09:31 = 571 s, RECENT. "What benchmark score is being displayed for the time spy?", A. 13,001. / B. 10,000. / C. 11,380. / D. 13,300., gold A.
- **Frames:** targets 568.0 … 571.0 (9 over [568, 571]).
  - Selected pts: 567.984, 568.368, 568.735, 569.119, 569.486, 569.869, 570.236, 570.620, 570.987, all ≤ t.
  - Frame SHA-256: `2a29a9caa7f87bad…`, `370c224e8f6b83b6…`, …
  - **Identical in all six arms; 22 / 22 smoke requests per arm have frame lists equal to 4BI's.**

| arm | prompt / completion tokens | finish | response (answer region) | upstream (first char) | strict |
|---|---|---|---|---|---|
| 4BI | 3,134 / 11 | stop | "A. 13,001." | correct | A (ok) |
| 8BI | 3,134 / 2 | stop | "A" | correct | A (ok) |
| 32BI | 3,134 / 2 | stop | "A" | correct | A (ok) |
| 4BT | 3,136 / 40 | stop, `</think>` closed | "…shown in the top left as 13 001. So the answer should be A.\n</think>\n\nA" → "A" | correct | A (ok) |
| 8BT | 3,136 / 83 | stop, `</think>` closed | "…Option A is 13,001. So the answer is A.\n</think>\n\nA" → "A" | correct | A (ok) |
| 32BT | 3,136 / 44 | stop, `</think>` closed | "…It says 13001. So the correct option is A.\n</think>\n\nA" → "A" | correct | A (ok) |

- **All 22 smoke requests per arm** (3 per input × part plus 2 grey per input) completed with finish `stop` and 0 errors.
- **Prompt tokens:** Instruct 3,114–3,261 (RECENT) and 12,579–12,726 (HISTORY); Thinking +2 on each.
- **Thinking completion tokens:** 40–2,262 (4BT), 65–4,149 (8BT), 44–1,379 (32BT). `</think>` closed on every smoke request.
- The Thinking answer region begins with "\n\n", which is why the upstream first-character scorer is applied after left-stripping whitespace (recorded deviation).

**Step 4: negative control.**
- 4BI on identical input twice: the first 10 RECENT questions of each part, 30 pairs (`b2_mv_4BI.jsonl.gz`, `b2_repeat_control_mv_4BI.json`, 2026-11-07 11:18, before the sweep).
- **30 / 30 identical answers, 30 / 30 identical texts, 30 / 30 identical correctness, 30 / 30 identical frame lists. PASS** (gate 99 %).
- With the arm difference disabled, per-question disagreement is 0, so between-arm disagreement in the sweep is attributable to the arm.

**Step 5: alternative explanations.**
- **First-character scorer:** it is sensitive to response format. An arm that starts its answer with anything other than the letter ("The answer is B") scores wrong under upstream.
  - Distinguishing data: strict-parser accuracy, unparsed and ambiguous counts, and parsed-only accuracy per arm.
- **Confounded by design:** mode and decoding, as before.
- **Seed noise:** Thinking samples with seed 0 only; no Thinking repeat control.
- **Video length:** StreamingBench videos are long (median ≈ 600 s), so HISTORY's 37 frames are sparser than on OVO / RTV. HISTORY − RECENT is a comparison of inputs, not of history value.

## Shard 1 (written 2026-11-07 ~21:20, after shard 1's six arms; observations only, full analysis after shard 3)
- **Data:** 8 / 8 zips sha256 = HF LFS (`results/datasets/sb_shard1_check_h100.json`).
  - 350 / 350 videos extracted and ffprobed.
  - Sizes equal to flash's on 350 / 350; codec and dims equal on 350 / 350.
  - Duration differs from flash's ffprobe by up to 0.137 s on 343 videos (bytes identical). The same ffprobe-version gap as OVO / RTV; reported, not resolved.
- **Runs** (2026-11-07):
  - smoke × 6: 22 / 22 each, 0 errors;
  - repeat control: 30 / 30;
  - 4BI 11:18–11:40, 8BI 11:40–12:11, 32BI 12:11–13:55, 4BT 13:56–15:06, 8BT 15:06–16:39, 32BT 16:39–20:56.
- **Coverage:** every arm 3,700 / 3,700 (1,750 main questions × 2 inputs + 100 grey × 2); 0 errors; 0 still failed.
- **Frame identity:** 0 mismatches over 15 arm pairs × 3,500 matched requests (online check vs 4BI: 3,700 / 3,700 per arm). Prompt tokens are equal within a mode, +2 for Thinking.
- **Shard 1 accuracy (upstream / strict), RECENT · HISTORY:**
  - 4BI 0.683 / 0.617 · 0.640 / 0.577;
  - 8BI 0.695 / 0.694 · 0.637 / 0.631;
  - 32BI 0.730 / 0.687 · 0.685 / 0.634;
  - 4BT 0.692 / 0.692 · 0.629 / 0.629;
  - 8BT 0.696 / 0.696 · 0.627 / 0.627;
  - 32BT 0.726 / 0.726 · 0.694 / 0.694.
- **Unparsed (strict) answers:** 5–9 % for 4BI and 32BI (they echo option text, e.g. "C. A man…", which the strict parser marks ambiguous), ≤ 1 % for the other arms.
- **Deletion:** see the next section.

### Shard 1 deletion (2026-11-07 ~21:25, per the user's DELETION rule; `experiments/datasets/b2_delete_shard.py`)
- **Checks passed before deleting:**
  - every arm had an error-free row for every shard 1 question × input and the 100 grey × input (6 × 3,700);
  - this report section existed;
  - flash's manifest records HF `48872fa7` and preflight lists every shard 1 zip;
  - every path resolved under `/home/pragya/data/datasets/streaming_bench/`.
- **Deleted:** 333 files, 108,767,284,765 bytes (101.3 GiB): 8 zips under `streaming_bench/hf/` and 325 `video.mp4` under `streaming_bench/extracted_by_task/`. Every path and size is in `results/datasets/deletion_h100_streaming_bench_shard1.json`.
- **Kept until the latency sample has run:** 25 shard 1 videos (listed in the same file).
- **Free disk:** 62 GiB before, 163 GiB after.

## Shard 2: undecodable upstream video (2026-11-07 21:24–21:55)
- **Data verification passed:** 3 / 3 zips sha256 = HF; 150 / 150 videos extracted, ffprobe OK, sizes equal flash's (`results/datasets/sb_shard2_check_h100.json`).
- **First attempt failed in every arm (21:23–21:30):**
  - PyAV raised `InvalidDataError: Invalid data found when processing input: 'avcodec_send_packet()'` while decoding frames from `Real-Time Visual Understanding/sample_332/video.mp4`.
  - The exception crashed the runner. The 23 transport-error rows of that attempt are its in-flight requests (client closed); 2 rows completed.
- **Located:** rendering every shard 2 request (1,500) on CPU found exactly **4 failing requests on that one video**: `sample_332_4` (t = 329 s) and `sample_332_5` (t = 500 s), under both inputs. Its bytes equal flash's copy (zip sha256 and CRC verified), so the defect is in the upstream file.
- **Implementation fix:** `b2_infer_vllm.py` now records a frame-decode failure as an error row (`RenderError: …`, counted as failed, never dropped) and continues. `b2_delete_shard.py` treats such requests as recorded unrunnable requests.
  - The FAILED markers of the first attempt are kept in `logs/failed_markers/`.
  - The arms reran from 21:50.
- **These 4 requests (2 questions × 2 inputs) fail in every arm.** They are reported as failed (0.13 % of the shard's 3,000 requests; below the 1 % arm stop rule).

## Shard 2 (written 2026-11-08 ~01:20, after shard 2's six arms)
- **Runs** (rerun after the fix, 2026-11-07 21:50 → 2026-11-08 00:45): 4BI → 22:03, 8BI → 22:16, 32BI → 23:00, 4BT → 23:16, 8BT → 23:41, 32BT → 00:45.
- **Coverage per arm (shards 1 + 2):** 5,196 error-free of 5,200 requests. The 4 failed requests are the undecodable `sample_332_4` / `sample_332_5` × RECENT / HISTORY (RenderError rows), the same in every arm. Shard 2 alone: 1,496 / 1,500.
- **Frame identity:** checked online vs 4BI on every shard 2 request of every arm (1,488–1,493 per arm; 0 mismatches).

### Shard 2 deletion (2026-11-08 ~01:20; `b2_delete_shard.py`)
- **Checks passed:** every arm had error-free rows for 1,496 / 1,500 shard 2 requests, and the remaining 4 are recorded RenderError rows; this section existed; the manifest and preflight are complete; all paths are under the dataset directory.
- **Deleted:** 145 files, 104582279276 bytes (97.4 GiB): 3 zips under `streaming_bench/hf/` and 142 videos. Listed in `results/datasets/deletion_h100_streaming_bench_shard2.json`.
- **Kept for the latency sample:** 8 shard 2 videos. The undecodable `sample_332` video was deleted with the shard; it is not in the latency sample.

## Shard 3 (written 2026-11-08 ~06:30)
- **Data:** 3 / 3 zips sha256 = HF; 150 / 150 videos extracted, ffprobe OK, sizes equal flash's (`results/datasets/sb_shard3_check_h100.json`). The decode check of all 1,500 requests found 0 failures. Prep and decode check ran on CPU at 01:25–01:31, while GPU 2 was held by another user.
- **GPU contention:**
  - 01:19: user `nesl`'s on-demand `vlm_proxy.py` (GPU list includes GPU 2) started a vLLM engine on GPU 2 during the idle gap between shards.
  - 01:36: our queue restarted at the same moment as that engine came back, and the watchdog stopped it; no request was affected.
  - The supervisor resumed at 02:06, after 5 free minutes.
- **Runs:** 4BI 02:06–02:16, 8BI → 02:29, 32BI → 03:12, 4BT → 03:28, 8BT → 03:51, 32BT → 04:58.
- **Latency sample:** 04:58–06:05.

## Run record and coverage (all shards)
- **Every arm:** 6,696 error-free of 6,700 requests (6,496 / 6,500 main + 200 / 200 grey). 0 server errors.
- **The 4 failed requests** are the undecodable `sample_332_4` / `sample_332_5` × RECENT / HISTORY (RenderError, every arm). The other error rows in the files are earlier attempts of the same requests and the in-flight rows of shard 2's crashed first attempt; every one was later answered or is one of the 4.
- **Frame identity:** 0 mismatches over 15 arm pairs × 6,496 matched main requests. Prompt tokens are equal within a mode, +2 Thinking.
- **Repeat control:** 30 / 30 (Step 4). **Smoke:** 22 / 22 × 6 arms.

## Observations (written after the run; no interpretation in this section)

### Accuracy (upstream first-character scorer [video-bootstrap 95 % CI]; strict below). Floor = 1 / 4.

| cell | floor | 4BI | 8BI | 32BI | 4BT | 8BT | 32BT |
|---|---|---|---|---|---|---|---|
| streaming_bench/RECENT | 0.25 | 0.760 [0.74, 0.78] | 0.764 [0.75, 0.78] | 0.792 [0.77, 0.81] | 0.763 [0.74, 0.78] | 0.763 [0.74, 0.78] | 0.787 [0.77, 0.80] |
| streaming_bench:sb_realtime/RECENT | 0.25 | 0.808 [0.79, 0.83] | 0.809 [0.79, 0.83] | 0.827 [0.81, 0.84] | 0.809 [0.79, 0.83] | 0.807 [0.79, 0.83] | 0.821 [0.80, 0.84] |
| streaming_bench:sb_contextual/RECENT | 0.25 | 0.646 [0.59, 0.70] | 0.654 [0.60, 0.70] | 0.714 [0.67, 0.76] | 0.660 [0.61, 0.70] | 0.654 [0.61, 0.70] | 0.728 [0.68, 0.77] |
| streaming_bench:sb_sequential/RECENT | 0.25 | 0.500 [0.44, 0.56] | 0.536 [0.47, 0.60] | 0.600 [0.54, 0.66] | 0.504 [0.43, 0.57] | 0.544 [0.47, 0.61] | 0.564 [0.50, 0.63] |
| streaming_bench/HISTORY | 0.25 | 0.717 [0.70, 0.74] | 0.711 [0.69, 0.73] | 0.749 [0.73, 0.77] | 0.702 [0.68, 0.72] | 0.704 [0.68, 0.73] | 0.760 [0.74, 0.78] |
| streaming_bench:sb_realtime/HISTORY | 0.25 | 0.802 [0.78, 0.82] | 0.793 [0.77, 0.81] | 0.823 [0.80, 0.84] | 0.782 [0.76, 0.80] | 0.793 [0.78, 0.81] | 0.835 [0.82, 0.85] |
| streaming_bench:sb_contextual/HISTORY | 0.25 | 0.424 [0.38, 0.47] | 0.414 [0.37, 0.46] | 0.488 [0.44, 0.54] | 0.408 [0.36, 0.45] | 0.364 [0.32, 0.41] | 0.492 [0.44, 0.54] |
| streaming_bench:sb_sequential/HISTORY | 0.25 | 0.460 [0.40, 0.51] | 0.480 [0.42, 0.54] | 0.536 [0.48, 0.59] | 0.488 [0.43, 0.54] | 0.492 [0.42, 0.56] | 0.544 [0.48, 0.60] |

Strict scorer:

| cell | 4BI | 8BI | 32BI | 4BT | 8BT | 32BT |
|---|---|---|---|---|---|---|
| streaming_bench/RECENT | 0.682 | 0.762 | 0.728 | 0.763 | 0.763 | 0.787 |
| streaming_bench:sb_realtime/RECENT | 0.731 | 0.806 | 0.752 | 0.809 | 0.807 | 0.821 |
| streaming_bench:sb_contextual/RECENT | 0.536 | 0.654 | 0.686 | 0.660 | 0.654 | 0.728 |
| streaming_bench:sb_sequential/RECENT | 0.484 | 0.536 | 0.576 | 0.504 | 0.544 | 0.564 |
| streaming_bench/HISTORY | 0.640 | 0.703 | 0.679 | 0.702 | 0.704 | 0.760 |
| streaming_bench:sb_realtime/HISTORY | 0.723 | 0.784 | 0.745 | 0.782 | 0.793 | 0.835 |
| streaming_bench:sb_contextual/HISTORY | 0.332 | 0.412 | 0.438 | 0.408 | 0.364 | 0.492 |
| streaming_bench:sb_sequential/HISTORY | 0.436 | 0.480 | 0.500 | 0.488 | 0.492 | 0.544 |

- **Task spread** (min–max upstream accuracy over tasks × input): 4BI 0.40–0.92; 8BI 0.41–0.91; 32BI 0.43–0.92; 4BT 0.40–0.91; 8BT 0.34–0.90; 32BT 0.42–0.92.
  - The lowest cells are Misleading / Anomaly Context under HISTORY and Counting under RECENT.

### Truncation, unparsed answers and generated tokens

| arm | cell | n | truncated | unparsed | ambiguous | empty | no answer region | parsed-only acc | completion tokens p50 / p90 / max |
|---|---|---|---|---|---|---|---|---|---|
| 4BI | streaming_bench/RECENT | 3248 | 1 | 313 | 308 | 0 | 0 | 0.754 | 7 / 21 / 64 |
| 4BI | streaming_bench/HISTORY | 3248 | 7 | 320 | 320 | 0 | 0 | 0.710 | 8 / 23 / 64 |
| 8BI | streaming_bench/RECENT | 3248 | 5 | 17 | 10 | 0 | 0 | 0.766 | 2 / 6 / 64 |
| 8BI | streaming_bench/HISTORY | 3248 | 0 | 32 | 32 | 0 | 0 | 0.710 | 2 / 7 / 39 |
| 32BI | streaming_bench/RECENT | 3248 | 8 | 244 | 239 | 0 | 0 | 0.787 | 6 / 12 / 64 |
| 32BI | streaming_bench/HISTORY | 3248 | 0 | 294 | 294 | 0 | 0 | 0.747 | 7 / 16 / 63 |
| 4BT | streaming_bench/RECENT | 3248 | 0 | 0 | 0 | 0 | 0 | 0.763 | 180 / 1231 / 9526 |
| 4BT | streaming_bench/HISTORY | 3248 | 0 | 0 | 0 | 0 | 0 | 0.702 | 152 / 1161 / 9876 |
| 8BT | streaming_bench/RECENT | 3248 | 0 | 0 | 0 | 0 | 0 | 0.763 | 164 / 1163 / 7524 |
| 8BT | streaming_bench/HISTORY | 3248 | 3 | 3 | 0 | 0 | 3 | 0.705 | 146 / 1370 / 16384 |
| 32BT | streaming_bench/RECENT | 3248 | 0 | 0 | 0 | 0 | 0 | 0.787 | 152 / 707 / 7839 |
| 32BT | streaming_bench/HISTORY | 3248 | 1 | 1 | 0 | 0 | 1 | 0.760 | 130 / 720 / 16384 |

- **Strict-unparsed rate:**
  - 4BI 9.6–9.9 % and 32BI 7.5–9.1 %: these arms often answer "<letter>. <option text>", and the strict parser marks an answer ambiguous when the option text contains another option letter.
  - 8BI ≤ 1 %; Thinking arms ≤ 0.1 %.
- **Truncation:** at most 8 per cell (Instruct, 64-token cap); 0–3 per cell (Thinking, 16,384 cap).

### Paired comparisons (matched questions; video bootstrap; both scorers)

| comparison | n | n videos | upstream diff [video CI] | strict diff [video CI] | correctness disagree | answer disagree |
|---|---|---|---|---|---|---|
| 4BI/streaming_bench/HISTORY-RECENT | 3248 | 650 | -0.042 [-0.059, -0.024] | -0.041 [-0.059, -0.025] | 0.199 | 0.257 |
| 8BI/streaming_bench/HISTORY-RECENT | 3248 | 650 | -0.054 [-0.071, -0.036] | -0.059 [-0.077, -0.041] | 0.217 | 0.284 |
| 32BI/streaming_bench/HISTORY-RECENT | 3248 | 650 | -0.043 [-0.059, -0.025] | -0.049 [-0.067, -0.031] | 0.192 | 0.244 |
| 4BT/streaming_bench/HISTORY-RECENT | 3248 | 650 | -0.061 [-0.078, -0.043] | -0.061 [-0.078, -0.044] | 0.214 | 0.273 |
| 8BT/streaming_bench/HISTORY-RECENT | 3248 | 650 | -0.059 [-0.078, -0.040] | -0.059 [-0.079, -0.040] | 0.240 | 0.298 |
| 32BT/streaming_bench/HISTORY-RECENT | 3248 | 650 | -0.026 [-0.044, -0.009] | -0.026 [-0.045, -0.009] | 0.203 | 0.247 |
| 32BI-4BI/streaming_bench/RECENT | 3248 | 650 | +0.032 [+0.019, +0.046] | +0.046 [+0.032, +0.062] | 0.132 | 0.183 |
| 32BI-4BI/streaming_bench/HISTORY | 3248 | 650 | +0.032 [+0.018, +0.046] | +0.039 [+0.025, +0.052] | 0.157 | 0.223 |
| 32BI-8BI/streaming_bench/RECENT | 3248 | 650 | +0.027 [+0.015, +0.040] | -0.034 [-0.050, -0.018] | 0.116 | 0.204 |
| 32BI-8BI/streaming_bench/HISTORY | 3248 | 650 | +0.038 [+0.024, +0.052] | -0.024 [-0.041, -0.007] | 0.153 | 0.258 |
| 8BI-4BI/streaming_bench/RECENT | 3248 | 650 | +0.005 [-0.007, +0.018] | +0.080 [+0.065, +0.096] | 0.119 | 0.232 |
| 8BI-4BI/streaming_bench/HISTORY | 3248 | 650 | -0.006 [-0.020, +0.007] | +0.063 [+0.047, +0.079] | 0.147 | 0.274 |
| 32BT-4BT/streaming_bench/RECENT | 3248 | 650 | +0.024 [+0.012, +0.036] | +0.024 [+0.012, +0.036] | 0.124 | 0.157 |
| 32BT-4BT/streaming_bench/HISTORY | 3248 | 650 | +0.058 [+0.044, +0.072] | +0.058 [+0.044, +0.072] | 0.167 | 0.211 |
| 32BT-8BT/streaming_bench/RECENT | 3248 | 650 | +0.024 [+0.012, +0.035] | +0.024 [+0.013, +0.034] | 0.111 | 0.143 |
| 32BT-8BT/streaming_bench/HISTORY | 3248 | 650 | +0.056 [+0.042, +0.070] | +0.056 [+0.042, +0.071] | 0.169 | 0.219 |
| 8BT-4BT/streaming_bench/RECENT | 3248 | 650 | +0.000 [-0.012, +0.012] | +0.000 [-0.011, +0.013] | 0.123 | 0.155 |
| 8BT-4BT/streaming_bench/HISTORY | 3248 | 650 | +0.002 [-0.010, +0.015] | +0.002 [-0.011, +0.016] | 0.146 | 0.204 |
| 4BT-4BI/streaming_bench/RECENT | 3248 | 650 | +0.003 [-0.008, +0.015] | +0.081 [+0.066, +0.097] | 0.110 | 0.227 |
| 4BT-4BI/streaming_bench/HISTORY | 3248 | 650 | -0.016 [-0.029, -0.001] | +0.061 [+0.045, +0.079] | 0.156 | 0.292 |
| 8BT-8BI/streaming_bench/RECENT | 3248 | 650 | -0.002 [-0.013, +0.011] | +0.001 [-0.011, +0.013] | 0.121 | 0.157 |
| 8BT-8BI/streaming_bench/HISTORY | 3248 | 650 | -0.007 [-0.020, +0.006] | +0.001 [-0.013, +0.015] | 0.159 | 0.214 |
| 32BT-32BI/streaming_bench/RECENT | 3248 | 650 | -0.005 [-0.015, +0.005] | +0.058 [+0.045, +0.072] | 0.089 | 0.177 |
| 32BT-32BI/streaming_bench/HISTORY | 3248 | 650 | +0.011 [-0.000, +0.023] | +0.081 [+0.066, +0.096] | 0.112 | 0.223 |

**Size:**
- 32B − 4B and 32B − 8B are positive in all 8 cells under the upstream scorer (+0.024 to +0.058, every CI excluding 0).
- Under strict, 32BI − 8BI is **negative** (−0.034 RECENT, −0.024 HISTORY), because 32BI's ambiguous answers are scored wrong by strict and not by upstream.
- 8B − 4B is ≈ 0 under upstream in both modes. Under strict it is +0.06 / +0.08 for Instruct (4BI's ambiguous answers) and ≈ 0 for Thinking.

**Thinking − Instruct:**
- Upstream: −0.016 to +0.011 at every size, with 9–16 % per-question correctness flips (0 / 30 in the repeat control).
- Strict: +0.06 to +0.08 for 4B and 32B and ≈ 0 for 8B. **The sign and size of Thinking − Instruct depend on the scorer here.**

**HISTORY − RECENT** (a comparison of inputs):
- Negative in all six arms under both scorers (−0.026 to −0.061, every CI excluding 0).
- By part, the drop is concentrated in Contextual (Anomaly / Misleading): RECENT 0.65–0.73 vs HISTORY 0.36–0.49. Real-Time is ≈ unchanged (0.78–0.84 both).

### Grey-frame control (the first 100 questions of the fixed order; real question and options, grey pixels)

| arm/input | n | upstream acc | strict acc | floor | answers | unparsed | truncated |
|---|---|---|---|---|---|---|---|
| 4BI/RECENT | 100 | 0.39 | 0.37 | 0.25 | {'A': 39, 'C': 27, 'D': 16, 'B': 13, 'None': 5} | 5 | 1 |
| 4BI/HISTORY | 100 | 0.40 | 0.36 | 0.25 | {'A': 40, 'C': 30, 'B': 13, 'D': 10, 'None': 7} | 7 | 0 |
| 8BI/RECENT | 100 | 0.42 | 0.42 | 0.25 | {'C': 33, 'D': 24, 'B': 24, 'A': 15, 'None': 4} | 4 | 0 |
| 8BI/HISTORY | 100 | 0.37 | 0.36 | 0.25 | {'B': 34, 'C': 29, 'A': 19, 'D': 17, 'None': 1} | 1 | 0 |
| 32BI/RECENT | 100 | 0.43 | 0.43 | 0.25 | {'C': 29, 'A': 27, 'B': 21, 'D': 18, 'None': 5} | 5 | 3 |
| 32BI/HISTORY | 100 | 0.43 | 0.42 | 0.25 | {'B': 30, 'C': 29, 'A': 22, 'D': 14, 'None': 5} | 5 | 1 |
| 4BT/RECENT | 100 | 0.37 | 0.37 | 0.25 | {'C': 33, 'B': 28, 'D': 22, 'A': 17} | 0 | 0 |
| 4BT/HISTORY | 100 | 0.40 | 0.40 | 0.25 | {'C': 30, 'D': 27, 'B': 23, 'A': 20} | 0 | 0 |
| 8BT/RECENT | 100 | 0.39 | 0.39 | 0.25 | {'C': 34, 'B': 29, 'D': 24, 'A': 12, 'None': 1} | 1 | 1 |
| 8BT/HISTORY | 100 | 0.44 | 0.44 | 0.25 | {'C': 31, 'B': 26, 'D': 24, 'A': 19} | 0 | 0 |
| 32BT/RECENT | 100 | 0.45 | 0.45 | 0.25 | {'B': 29, 'A': 29, 'D': 22, 'C': 20} | 0 | 0 |
| 32BT/HISTORY | 100 | 0.46 | 0.46 | 0.25 | {'A': 28, 'B': 25, 'C': 24, 'D': 23} | 0 | 0 |

- **Grey accuracy is 0.37–0.46 in every arm × input, against a floor of 0.25, i.e. 12–21 points above it.** On OVO / RTV the grey control was at the floor.
- Answer letters are spread across A–D (no single-letter collapse).

### Latency sample (StudyD10 method; localhost, no network; cold; first request per load discarded)
- Isolation: 144 checks, not VOID. Cache counters unchanged. `cached_tokens` 0 on every request. No neighbour-flagged request.

Warm-ups discarded: 6; isolation VOID = False (144 checks); cache counters grew: never.

| arm / sub-dataset / input | n | TTFT p50 / p90 / max (s) | total p50 / p90 / max (s) | prompt tok p50 | completion tok p50 / max | GPU-2 SM MHz median (p50 of requests) | neighbour-flagged | truncated |
|---|---|---|---|---|---|---|---|---|
| 32BI/streaming_bench/HISTORY | 50 | 3.00 / 3.04 / 3.08 | 3.16 / 3.32 / 3.54 | 12594 | 7 / 23 | 975 | 0 | 0 |
| 32BI/streaming_bench/RECENT | 50 | 0.64 / 0.66 / 0.77 | 0.76 / 0.87 / 1.02 | 3129 | 6 / 15 | 1035 | 0 | 0 |
| 32BT/streaming_bench/HISTORY | 50 | 3.07 / 3.11 / 3.25 | 5.81 / 26.21 / 93.64 | 12596 | 114 / 3708 | 1260 | 0 | 0 |
| 32BT/streaming_bench/RECENT | 50 | 0.66 / 0.69 / 0.74 | 4.01 / 23.21 / 59.23 | 3131 | 144 / 2533 | 1286 | 0 | 0 |
| 4BI/streaming_bench/HISTORY | 50 | 0.98 / 1.01 / 1.10 | 1.04 / 1.09 / 1.19 | 12594 | 8 / 42 | 1740 | 0 | 0 |
| 4BI/streaming_bench/RECENT | 50 | 0.24 / 0.26 / 0.33 | 0.27 / 0.29 / 0.37 | 3129 | 7 / 23 | 1631 | 0 | 0 |
| 4BT/streaming_bench/HISTORY | 50 | 0.99 / 1.03 / 1.19 | 1.67 / 5.75 / 20.49 | 12596 | 136 / 3905 | 1778 | 0 | 0 |
| 4BT/streaming_bench/RECENT | 50 | 0.25 / 0.27 / 0.36 | 1.45 / 5.59 / 13.70 | 3131 | 271 / 2954 | 1785 | 0 | 0 |
| 8BI/streaming_bench/HISTORY | 50 | 1.21 / 1.24 / 1.28 | 1.23 / 1.28 / 1.31 | 12594 | 2 / 12 | 1215 | 0 | 0 |
| 8BI/streaming_bench/RECENT | 50 | 0.29 / 0.30 / 0.35 | 0.30 / 0.33 / 0.36 | 3129 | 2 / 8 | 1492 | 0 | 0 |
| 8BT/streaming_bench/HISTORY | 50 | 1.22 / 1.26 / 1.63 | 2.10 / 11.59 / 31.90 | 12596 | 120 / 4291 | 1402 | 0 | 0 |
| 8BT/streaming_bench/RECENT | 50 | 0.30 / 0.31 / 0.50 | 1.80 / 5.95 / 18.84 | 3131 | 220 / 2856 | 1770 | 0 | 0 |

- **TTFT** RECENT / HISTORY: 4B ≈ 0.24 / 0.98 s; 8B ≈ 0.29 / 1.21 s; 32B ≈ 0.65 / 3.0 s. These are the same as on OVO / RTV, since prompt sizes are the same.
- **Thinking total:** p50 1.5–5.8 s; max 93.6 s (32BT, HISTORY).

## Results consistency check (6 checks)
1. **Cross-check against committed measurements.**
   - TTFT by size and input equals StudyB2-ovo-rtv's within 5 % (e.g. 32B 0.65 vs 0.64 s RECENT, 3.00 vs 3.0 s HISTORY; 4B 0.24 vs 0.22 s). The prompt sizes are equal (≈ 3.13k / 12.59k tokens).
   - Accuracy has no like-for-like prior. Flash's StudyB1-flash ran 4B / 8B on the same 3,250 questions on another host, template and scorer port; not compared.
   - No > 2× disagreement.
2. **Physical plausibility.** Prefill rates as StudyB2-ovo-rtv (32B ≈ 4.2–4.8k tokens/s; nothing faster than the committed curves).
3. **Distribution sanity.**
   - Task accuracies span 0.34–0.92; tokens vary per request; latency spreads are reported per cell.
   - The grey control is a distribution across A–D, not a constant.
4. **Definition audit.**
   - RECENT / HISTORY, template and strict scorer are as StudyB1.
   - The upstream scorer is StreamingBench's first character, with whitespace stripped (recorded deviation). It is a different upstream scorer from OVO / RTV's, so accuracy is not comparable across benchmarks.
5. **Claim linkage.**
   - FORMULATION.md §Regime uncertainty / §Decisions.
   - **Supports:** tiers answer the same queries differently (9–17 % correctness flips), and 32B is more accurate than 4B / 8B under the upstream scorer.
   - **Does not speak to:** policy or time-shift.
6. **Proxy validity.**
   - **The upstream first-character scorer is a format-sensitive proxy for "chose the right option".** The strict scorer is a different proxy that penalises answers echoing option text.
   - Size and HISTORY − RECENT directions agree under both scorers, except 32BI − 8BI. **Thinking − Instruct does not agree, so no headline claim about mode is made on StreamingBench.**
   - **The grey control above the floor** means part of the accuracy does not need the video. Accuracy above 0.25 is not all visual.

**Outcome:** no check failed. Flags:
- scorer-dependent Thinking − Instruct and 32BI − 8BI;
- grey control above the floor;
- one undecodable upstream video (4 requests);
- the first-character whitespace deviation.

## Interpretation
- **Size:** on StreamingBench, as on OVO / RTV, 32B answers more questions correctly than 4B and 8B under the benchmark's own scorer (+2.4 to +5.8 pp). 8B ≈ 4B.
- **Reasoning mode:** under the benchmark's scorer Thinking changes accuracy by about ±1.5 pp. The apparent +6–8 pp under strict scoring is a format effect: Instruct arms that restate the option are penalised by strict, not a capability effect. Mode and decoding remain confounded.
- **Inputs:** 37 frames over the whole (long, median ≈ 10 min) video hurt the Contextual tasks badly and leave Real-Time tasks unchanged. This is an input comparison at a fixed frame count, and the history frames are sparse on long videos.
- **Grey control above the floor:** a sizeable share of these multiple-choice questions is answerable from the text alone. Any capability comparison here includes that text-prior component.


## Final deletion (2026-11-08 ~06:45, after the latency sample; `b2_delete_shard.py`)
| step | files | bytes | record |
|---|---|---|---|
| shard 1 (2026-11-07 21:25) | 333 (8 zips + 325 videos) | 108,767,284,765 | `results/datasets/deletion_h100_streaming_bench_shard1.json` |
| shard 2 (2026-11-08 01:20) | 145 (3 zips + 142 videos) | 104,582,279,276 | `…_shard2.json` |
| shard 3 (06:45; includes its 16 latency videos) | 153 (3 zips + 150 videos) | 99,274,338,663 | `…_shard3.json` |
| shard 1 latency videos (06:45) | 25 | 4,635,696,914 | `…_shard1_latency_videos.json` |
| shard 2 latency videos (06:45) | 8 | 3,123,661,384 | `…_shard2_latency_videos.json` |
| **total** | **664** | **320,383,261,002 (298.4 GiB)** | |

- The same checks as for every shard: rows complete (or recorded RenderError), report section present, manifest pinned, paths under the dataset directory, no wildcard.
- **Kept:** annotations (`hf/StreamingBench/*.csv`), HF README / .gitattributes, the code clone (including its own `figs/example.mp4`), ffprobe logs, logs.
- **Free disk on the data volume:** 197 GiB after.

## Appendix: per-task results (all arms)

| arm | cell | n | floor | upstream [video CI] | strict | trunc | unparsed | tokens p50 / p90 / max |
|---|---|---|---|---|---|---|---|---|
| 4BI | streaming_bench/Action Perception/HISTORY | 352 | 0.25 | 0.778 [0.73, 0.82] | 0.770 | 0.000 | 0.011 | 10 / 14 / 18 |
| 4BI | streaming_bench/Action Perception/RECENT | 352 | 0.25 | 0.804 [0.76, 0.85] | 0.795 | 0.000 | 0.014 | 10 / 14 / 18 |
| 4BI | streaming_bench/Anomaly Context Understanding/HISTORY | 250 | 0.25 | 0.448 [0.39, 0.51] | 0.296 | 0.000 | 0.292 | 22 / 39 / 61 |
| 4BI | streaming_bench/Anomaly Context Understanding/RECENT | 250 | 0.25 | 0.656 [0.58, 0.73] | 0.452 | 0.000 | 0.292 | 19 / 35 / 61 |
| 4BI | streaming_bench/Attribute Perception/HISTORY | 311 | 0.25 | 0.875 [0.83, 0.91] | 0.846 | 0.000 | 0.029 | 5 / 10 / 34 |
| 4BI | streaming_bench/Attribute Perception/RECENT | 311 | 0.25 | 0.910 [0.87, 0.95] | 0.878 | 0.000 | 0.032 | 5 / 10 / 17 |
| 4BI | streaming_bench/Causal Reasoning/HISTORY | 128 | 0.25 | 0.727 [0.65, 0.80] | 0.727 | 0.000 | 0.000 | 12 / 18 / 27 |
| 4BI | streaming_bench/Causal Reasoning/RECENT | 128 | 0.25 | 0.656 [0.58, 0.73] | 0.656 | 0.000 | 0.000 | 2 / 15 / 27 |
| 4BI | streaming_bench/Clips Summarize/HISTORY | 317 | 0.25 | 0.864 [0.83, 0.90] | 0.808 | 0.000 | 0.066 | 21 / 27 / 34 |
| 4BI | streaming_bench/Clips Summarize/RECENT | 317 | 0.25 | 0.915 [0.88, 0.95] | 0.864 | 0.000 | 0.057 | 18 / 26 / 34 |
| 4BI | streaming_bench/Counting/HISTORY | 188 | 0.25 | 0.553 [0.47, 0.65] | 0.553 | 0.000 | 0.000 | 6 / 6 / 7 |
| 4BI | streaming_bench/Counting/RECENT | 188 | 0.25 | 0.420 [0.34, 0.51] | 0.420 | 0.000 | 0.021 | 6 / 6 / 6 |
| 4BI | streaming_bench/Event Understanding/HISTORY | 158 | 0.25 | 0.772 [0.71, 0.84] | 0.690 | 0.000 | 0.082 | 9 / 14 / 22 |
| 4BI | streaming_bench/Event Understanding/RECENT | 158 | 0.25 | 0.741 [0.66, 0.81] | 0.677 | 0.000 | 0.070 | 8 / 14 / 22 |
| 4BI | streaming_bench/Misleading Context Recognition/HISTORY | 250 | 0.25 | 0.400 [0.34, 0.47] | 0.368 | 0.028 | 0.056 | 16 / 45 / 64 |
| 4BI | streaming_bench/Misleading Context Recognition/RECENT | 250 | 0.25 | 0.636 [0.56, 0.70] | 0.620 | 0.004 | 0.024 | 2 / 35 / 64 |
| 4BI | streaming_bench/Object Perception/HISTORY | 369 | 0.25 | 0.840 [0.80, 0.88] | 0.534 | 0.000 | 0.355 | 7 / 10 / 25 |
| 4BI | streaming_bench/Object Perception/RECENT | 369 | 0.25 | 0.854 [0.82, 0.89] | 0.542 | 0.000 | 0.352 | 7 / 10 / 23 |
| 4BI | streaming_bench/Prospective Reasoning/HISTORY | 108 | 0.25 | 0.843 [0.78, 0.91] | 0.843 | 0.000 | 0.000 | 9 / 13 / 20 |
| 4BI | streaming_bench/Prospective Reasoning/RECENT | 108 | 0.25 | 0.787 [0.70, 0.87] | 0.787 | 0.000 | 0.000 | 9 / 13 / 17 |
| 4BI | streaming_bench/Sequential Question Answering/HISTORY | 250 | 0.25 | 0.460 [0.40, 0.51] | 0.436 | 0.000 | 0.028 | 7 / 8 / 16 |
| 4BI | streaming_bench/Sequential Question Answering/RECENT | 250 | 0.25 | 0.500 [0.44, 0.56] | 0.484 | 0.000 | 0.032 | 7 / 8 / 16 |
| 4BI | streaming_bench/Spatial Understanding/HISTORY | 246 | 0.25 | 0.732 [0.68, 0.79] | 0.585 | 0.000 | 0.167 | 9 / 11 / 23 |
| 4BI | streaming_bench/Spatial Understanding/RECENT | 246 | 0.25 | 0.809 [0.76, 0.86] | 0.667 | 0.000 | 0.167 | 9 / 11 / 23 |
| 4BI | streaming_bench/Text-Rich Understanding/HISTORY | 321 | 0.25 | 0.882 [0.84, 0.92] | 0.863 | 0.000 | 0.022 | 8 / 14 / 27 |
| 4BI | streaming_bench/Text-Rich Understanding/RECENT | 321 | 0.25 | 0.885 [0.85, 0.92] | 0.869 | 0.000 | 0.022 | 7 / 13 / 30 |
| 8BI | streaming_bench/Action Perception/HISTORY | 352 | 0.25 | 0.739 [0.69, 0.78] | 0.739 | 0.000 | 0.000 | 2 / 12 / 17 |
| 8BI | streaming_bench/Action Perception/RECENT | 352 | 0.25 | 0.793 [0.75, 0.84] | 0.793 | 0.000 | 0.003 | 2 / 8 / 34 |
| 8BI | streaming_bench/Anomaly Context Understanding/HISTORY | 250 | 0.25 | 0.420 [0.36, 0.48] | 0.416 | 0.000 | 0.008 | 2 / 2 / 35 |
| 8BI | streaming_bench/Anomaly Context Understanding/RECENT | 250 | 0.25 | 0.644 [0.57, 0.72] | 0.644 | 0.012 | 0.012 | 2 / 2 / 64 |
| 8BI | streaming_bench/Attribute Perception/HISTORY | 311 | 0.25 | 0.871 [0.83, 0.91] | 0.871 | 0.000 | 0.000 | 2 / 6 / 15 |
| 8BI | streaming_bench/Attribute Perception/RECENT | 311 | 0.25 | 0.910 [0.88, 0.94] | 0.910 | 0.000 | 0.000 | 2 / 5 / 15 |
| 8BI | streaming_bench/Causal Reasoning/HISTORY | 128 | 0.25 | 0.734 [0.67, 0.81] | 0.734 | 0.000 | 0.000 | 2 / 15 / 21 |
| 8BI | streaming_bench/Causal Reasoning/RECENT | 128 | 0.25 | 0.695 [0.62, 0.77] | 0.695 | 0.000 | 0.000 | 2 / 14 / 19 |
| 8BI | streaming_bench/Clips Summarize/HISTORY | 317 | 0.25 | 0.855 [0.81, 0.90] | 0.855 | 0.000 | 0.000 | 2 / 2 / 23 |
| 8BI | streaming_bench/Clips Summarize/RECENT | 317 | 0.25 | 0.899 [0.87, 0.93] | 0.899 | 0.003 | 0.006 | 2 / 2 / 64 |
| 8BI | streaming_bench/Counting/HISTORY | 188 | 0.25 | 0.564 [0.46, 0.66] | 0.564 | 0.000 | 0.000 | 6 / 6 / 7 |
| 8BI | streaming_bench/Counting/RECENT | 188 | 0.25 | 0.436 [0.35, 0.53] | 0.436 | 0.000 | 0.000 | 6 / 6 / 7 |
| 8BI | streaming_bench/Event Understanding/HISTORY | 158 | 0.25 | 0.766 [0.69, 0.84] | 0.766 | 0.000 | 0.000 | 2 / 11 / 22 |
| 8BI | streaming_bench/Event Understanding/RECENT | 158 | 0.25 | 0.722 [0.65, 0.80] | 0.722 | 0.000 | 0.000 | 2 / 2 / 12 |
| 8BI | streaming_bench/Misleading Context Recognition/HISTORY | 250 | 0.25 | 0.408 [0.34, 0.48] | 0.408 | 0.000 | 0.004 | 2 / 2 / 39 |
| 8BI | streaming_bench/Misleading Context Recognition/RECENT | 250 | 0.25 | 0.664 [0.59, 0.74] | 0.664 | 0.004 | 0.004 | 2 / 2 / 64 |
| 8BI | streaming_bench/Object Perception/HISTORY | 369 | 0.25 | 0.846 [0.81, 0.88] | 0.799 | 0.000 | 0.057 | 2 / 6 / 15 |
| 8BI | streaming_bench/Object Perception/RECENT | 369 | 0.25 | 0.862 [0.83, 0.89] | 0.846 | 0.000 | 0.022 | 2 / 2 / 14 |
| 8BI | streaming_bench/Prospective Reasoning/HISTORY | 108 | 0.25 | 0.843 [0.76, 0.91] | 0.843 | 0.000 | 0.000 | 2 / 2 / 15 |
| 8BI | streaming_bench/Prospective Reasoning/RECENT | 108 | 0.25 | 0.824 [0.75, 0.90] | 0.824 | 0.000 | 0.000 | 2 / 2 / 11 |
| 8BI | streaming_bench/Sequential Question Answering/HISTORY | 250 | 0.25 | 0.480 [0.42, 0.54] | 0.480 | 0.000 | 0.000 | 2 / 6 / 7 |
| 8BI | streaming_bench/Sequential Question Answering/RECENT | 250 | 0.25 | 0.536 [0.46, 0.60] | 0.536 | 0.000 | 0.000 | 2 / 6 / 7 |
| 8BI | streaming_bench/Spatial Understanding/HISTORY | 246 | 0.25 | 0.691 [0.63, 0.75] | 0.667 | 0.000 | 0.028 | 2 / 11 / 17 |
| 8BI | streaming_bench/Spatial Understanding/RECENT | 246 | 0.25 | 0.793 [0.74, 0.84] | 0.785 | 0.000 | 0.008 | 2 / 8 / 14 |
| 8BI | streaming_bench/Text-Rich Understanding/HISTORY | 321 | 0.25 | 0.891 [0.86, 0.92] | 0.888 | 0.000 | 0.003 | 2 / 5 / 16 |
| 8BI | streaming_bench/Text-Rich Understanding/RECENT | 321 | 0.25 | 0.897 [0.86, 0.93] | 0.897 | 0.000 | 0.000 | 2 / 5 / 13 |
| 32BI | streaming_bench/Action Perception/HISTORY | 352 | 0.25 | 0.801 [0.76, 0.85] | 0.793 | 0.000 | 0.014 | 10 / 14 / 27 |
| 32BI | streaming_bench/Action Perception/RECENT | 352 | 0.25 | 0.821 [0.78, 0.86] | 0.812 | 0.003 | 0.017 | 10 / 14 / 64 |
| 32BI | streaming_bench/Anomaly Context Understanding/HISTORY | 250 | 0.25 | 0.484 [0.42, 0.55] | 0.388 | 0.000 | 0.188 | 2 / 28 / 40 |
| 32BI | streaming_bench/Anomaly Context Understanding/RECENT | 250 | 0.25 | 0.708 [0.64, 0.77] | 0.648 | 0.008 | 0.092 | 2 / 21 / 64 |
| 32BI | streaming_bench/Attribute Perception/HISTORY | 311 | 0.25 | 0.881 [0.84, 0.92] | 0.849 | 0.000 | 0.032 | 5 / 10 / 17 |
| 32BI | streaming_bench/Attribute Perception/RECENT | 311 | 0.25 | 0.913 [0.88, 0.95] | 0.884 | 0.000 | 0.029 | 5 / 9 / 17 |
| 32BI | streaming_bench/Causal Reasoning/HISTORY | 128 | 0.25 | 0.875 [0.82, 0.93] | 0.875 | 0.000 | 0.000 | 10 / 17 / 22 |
| 32BI | streaming_bench/Causal Reasoning/RECENT | 128 | 0.25 | 0.742 [0.68, 0.80] | 0.742 | 0.008 | 0.008 | 2 / 11 / 64 |
| 32BI | streaming_bench/Clips Summarize/HISTORY | 317 | 0.25 | 0.896 [0.86, 0.93] | 0.858 | 0.000 | 0.041 | 2 / 24 / 31 |
| 32BI | streaming_bench/Clips Summarize/RECENT | 317 | 0.25 | 0.918 [0.89, 0.94] | 0.893 | 0.000 | 0.028 | 2 / 18 / 29 |
| 32BI | streaming_bench/Counting/HISTORY | 188 | 0.25 | 0.569 [0.48, 0.66] | 0.569 | 0.000 | 0.000 | 6 / 6 / 7 |
| 32BI | streaming_bench/Counting/RECENT | 188 | 0.25 | 0.431 [0.34, 0.52] | 0.431 | 0.005 | 0.005 | 6 / 6 / 64 |
| 32BI | streaming_bench/Event Understanding/HISTORY | 158 | 0.25 | 0.778 [0.71, 0.85] | 0.703 | 0.000 | 0.076 | 9 / 15 / 22 |
| 32BI | streaming_bench/Event Understanding/RECENT | 158 | 0.25 | 0.785 [0.71, 0.85] | 0.741 | 0.000 | 0.044 | 7 / 13 / 22 |
| 32BI | streaming_bench/Misleading Context Recognition/HISTORY | 250 | 0.25 | 0.492 [0.42, 0.56] | 0.488 | 0.000 | 0.016 | 2 / 26 / 63 |
| 32BI | streaming_bench/Misleading Context Recognition/RECENT | 250 | 0.25 | 0.720 [0.65, 0.79] | 0.724 | 0.004 | 0.004 | 2 / 22 / 64 |
| 32BI | streaming_bench/Object Perception/HISTORY | 369 | 0.25 | 0.851 [0.81, 0.89] | 0.531 | 0.000 | 0.390 | 7 / 10 / 23 |
| 32BI | streaming_bench/Object Perception/RECENT | 369 | 0.25 | 0.870 [0.83, 0.90] | 0.550 | 0.003 | 0.363 | 7 / 9 / 64 |
| 32BI | streaming_bench/Prospective Reasoning/HISTORY | 108 | 0.25 | 0.824 [0.74, 0.90] | 0.824 | 0.000 | 0.000 | 2 / 12 / 16 |
| 32BI | streaming_bench/Prospective Reasoning/RECENT | 108 | 0.25 | 0.806 [0.73, 0.88] | 0.806 | 0.000 | 0.000 | 2 / 9 / 16 |
| 32BI | streaming_bench/Sequential Question Answering/HISTORY | 250 | 0.25 | 0.536 [0.48, 0.59] | 0.500 | 0.000 | 0.040 | 7 / 8 / 16 |
| 32BI | streaming_bench/Sequential Question Answering/RECENT | 250 | 0.25 | 0.600 [0.54, 0.66] | 0.576 | 0.000 | 0.024 | 7 / 7 / 10 |
| 32BI | streaming_bench/Spatial Understanding/HISTORY | 246 | 0.25 | 0.748 [0.70, 0.80] | 0.618 | 0.000 | 0.175 | 8 / 11 / 23 |
| 32BI | streaming_bench/Spatial Understanding/RECENT | 246 | 0.25 | 0.821 [0.77, 0.87] | 0.675 | 0.004 | 0.167 | 8 / 11 / 64 |
| 32BI | streaming_bench/Text-Rich Understanding/HISTORY | 321 | 0.25 | 0.891 [0.86, 0.92] | 0.872 | 0.000 | 0.019 | 6 / 11 / 24 |
| 32BI | streaming_bench/Text-Rich Understanding/RECENT | 321 | 0.25 | 0.907 [0.87, 0.93] | 0.888 | 0.000 | 0.019 | 5 / 10 / 24 |
| 4BT | streaming_bench/Action Perception/HISTORY | 352 | 0.25 | 0.756 [0.71, 0.80] | 0.756 | 0.000 | 0.000 | 105 / 344 / 3635 |
| 4BT | streaming_bench/Action Perception/RECENT | 352 | 0.25 | 0.818 [0.78, 0.86] | 0.818 | 0.000 | 0.000 | 151 / 699 / 5456 |
| 4BT | streaming_bench/Anomaly Context Understanding/HISTORY | 250 | 0.25 | 0.408 [0.34, 0.47] | 0.408 | 0.000 | 0.000 | 548 / 1987 / 5288 |
| 4BT | streaming_bench/Anomaly Context Understanding/RECENT | 250 | 0.25 | 0.656 [0.59, 0.73] | 0.656 | 0.000 | 0.000 | 684 / 2059 / 6269 |
| 4BT | streaming_bench/Attribute Perception/HISTORY | 311 | 0.25 | 0.871 [0.83, 0.91] | 0.871 | 0.000 | 0.000 | 70 / 239 / 3662 |
| 4BT | streaming_bench/Attribute Perception/RECENT | 311 | 0.25 | 0.907 [0.87, 0.94] | 0.907 | 0.000 | 0.000 | 77 / 297 / 1533 |
| 4BT | streaming_bench/Causal Reasoning/HISTORY | 128 | 0.25 | 0.719 [0.64, 0.80] | 0.719 | 0.000 | 0.000 | 208 / 457 / 1595 |
| 4BT | streaming_bench/Causal Reasoning/RECENT | 128 | 0.25 | 0.703 [0.61, 0.80] | 0.703 | 0.000 | 0.000 | 260 / 757 / 2466 |
| 4BT | streaming_bench/Clips Summarize/HISTORY | 317 | 0.25 | 0.820 [0.78, 0.86] | 0.820 | 0.000 | 0.000 | 184 / 604 / 2018 |
| 4BT | streaming_bench/Clips Summarize/RECENT | 317 | 0.25 | 0.883 [0.84, 0.92] | 0.883 | 0.000 | 0.000 | 211 / 987 / 3238 |
| 4BT | streaming_bench/Counting/HISTORY | 188 | 0.25 | 0.564 [0.48, 0.65] | 0.564 | 0.000 | 0.000 | 1371 / 6295 / 9876 |
| 4BT | streaming_bench/Counting/RECENT | 188 | 0.25 | 0.404 [0.32, 0.50] | 0.404 | 0.000 | 0.000 | 372 / 2418 / 5321 |
| 4BT | streaming_bench/Event Understanding/HISTORY | 158 | 0.25 | 0.734 [0.66, 0.81] | 0.734 | 0.000 | 0.000 | 124 / 663 / 5596 |
| 4BT | streaming_bench/Event Understanding/RECENT | 158 | 0.25 | 0.741 [0.67, 0.81] | 0.741 | 0.000 | 0.000 | 180 / 1359 / 4185 |
| 4BT | streaming_bench/Misleading Context Recognition/HISTORY | 250 | 0.25 | 0.408 [0.35, 0.47] | 0.408 | 0.000 | 0.000 | 678 / 2355 / 6086 |
| 4BT | streaming_bench/Misleading Context Recognition/RECENT | 250 | 0.25 | 0.664 [0.60, 0.72] | 0.664 | 0.000 | 0.000 | 1048 / 4598 / 9526 |
| 4BT | streaming_bench/Object Perception/HISTORY | 369 | 0.25 | 0.821 [0.78, 0.86] | 0.821 | 0.000 | 0.000 | 85 / 346 / 3388 |
| 4BT | streaming_bench/Object Perception/RECENT | 369 | 0.25 | 0.894 [0.86, 0.93] | 0.894 | 0.000 | 0.000 | 90 / 423 / 2949 |
| 4BT | streaming_bench/Prospective Reasoning/HISTORY | 108 | 0.25 | 0.806 [0.72, 0.89] | 0.806 | 0.000 | 0.000 | 170 / 902 / 5724 |
| 4BT | streaming_bench/Prospective Reasoning/RECENT | 108 | 0.25 | 0.815 [0.74, 0.89] | 0.815 | 0.000 | 0.000 | 236 / 869 / 6156 |
| 4BT | streaming_bench/Sequential Question Answering/HISTORY | 250 | 0.25 | 0.488 [0.43, 0.55] | 0.488 | 0.000 | 0.000 | 431 / 1519 / 4506 |
| 4BT | streaming_bench/Sequential Question Answering/RECENT | 250 | 0.25 | 0.504 [0.43, 0.58] | 0.504 | 0.000 | 0.000 | 288 / 829 / 3708 |
| 4BT | streaming_bench/Spatial Understanding/HISTORY | 246 | 0.25 | 0.720 [0.67, 0.78] | 0.720 | 0.000 | 0.000 | 101 / 570 / 4687 |
| 4BT | streaming_bench/Spatial Understanding/RECENT | 246 | 0.25 | 0.776 [0.72, 0.83] | 0.776 | 0.000 | 0.000 | 110 / 439 / 5096 |
| 4BT | streaming_bench/Text-Rich Understanding/HISTORY | 321 | 0.25 | 0.857 [0.82, 0.89] | 0.857 | 0.000 | 0.000 | 80 / 381 / 4401 |
| 4BT | streaming_bench/Text-Rich Understanding/RECENT | 321 | 0.25 | 0.869 [0.83, 0.90] | 0.869 | 0.000 | 0.000 | 98 / 501 / 4319 |
| 8BT | streaming_bench/Action Perception/HISTORY | 352 | 0.25 | 0.747 [0.69, 0.80] | 0.747 | 0.000 | 0.000 | 105 / 553 / 4799 |
| 8BT | streaming_bench/Action Perception/RECENT | 352 | 0.25 | 0.827 [0.79, 0.87] | 0.827 | 0.000 | 0.000 | 132 / 544 / 4602 |
| 8BT | streaming_bench/Anomaly Context Understanding/HISTORY | 250 | 0.25 | 0.340 [0.28, 0.40] | 0.340 | 0.000 | 0.000 | 627 / 2142 / 7218 |
| 8BT | streaming_bench/Anomaly Context Understanding/RECENT | 250 | 0.25 | 0.676 [0.60, 0.74] | 0.676 | 0.000 | 0.000 | 558 / 1870 / 4935 |
| 8BT | streaming_bench/Attribute Perception/HISTORY | 311 | 0.25 | 0.852 [0.81, 0.89] | 0.852 | 0.000 | 0.000 | 70 / 280 / 3163 |
| 8BT | streaming_bench/Attribute Perception/RECENT | 311 | 0.25 | 0.897 [0.86, 0.93] | 0.897 | 0.000 | 0.000 | 71 / 212 / 4052 |
| 8BT | streaming_bench/Causal Reasoning/HISTORY | 128 | 0.25 | 0.766 [0.69, 0.85] | 0.766 | 0.000 | 0.000 | 162 / 454 / 2871 |
| 8BT | streaming_bench/Causal Reasoning/RECENT | 128 | 0.25 | 0.719 [0.63, 0.80] | 0.719 | 0.000 | 0.000 | 222 / 678 / 2003 |
| 8BT | streaming_bench/Clips Summarize/HISTORY | 317 | 0.25 | 0.836 [0.79, 0.88] | 0.836 | 0.000 | 0.000 | 180 / 567 / 2200 |
| 8BT | streaming_bench/Clips Summarize/RECENT | 317 | 0.25 | 0.893 [0.86, 0.92] | 0.893 | 0.000 | 0.000 | 210 / 893 / 3594 |
| 8BT | streaming_bench/Counting/HISTORY | 188 | 0.25 | 0.628 [0.54, 0.71] | 0.628 | 0.000 | 0.000 | 967 / 5797 / 9426 |
| 8BT | streaming_bench/Counting/RECENT | 188 | 0.25 | 0.415 [0.32, 0.52] | 0.415 | 0.000 | 0.000 | 330 / 1778 / 3802 |
| 8BT | streaming_bench/Event Understanding/HISTORY | 158 | 0.25 | 0.766 [0.69, 0.84] | 0.766 | 0.000 | 0.000 | 127 / 1010 / 5881 |
| 8BT | streaming_bench/Event Understanding/RECENT | 158 | 0.25 | 0.734 [0.66, 0.81] | 0.734 | 0.000 | 0.000 | 155 / 1203 / 7524 |
| 8BT | streaming_bench/Misleading Context Recognition/HISTORY | 250 | 0.25 | 0.388 [0.32, 0.46] | 0.388 | 0.008 | 0.008 | 750 / 2934 / 16384 |
| 8BT | streaming_bench/Misleading Context Recognition/RECENT | 250 | 0.25 | 0.632 [0.57, 0.70] | 0.632 | 0.000 | 0.000 | 824 / 3568 / 6135 |
| 8BT | streaming_bench/Object Perception/HISTORY | 369 | 0.25 | 0.808 [0.77, 0.84] | 0.808 | 0.000 | 0.000 | 76 / 276 / 3714 |
| 8BT | streaming_bench/Object Perception/RECENT | 369 | 0.25 | 0.848 [0.81, 0.88] | 0.848 | 0.000 | 0.000 | 79 / 374 / 2558 |
| 8BT | streaming_bench/Prospective Reasoning/HISTORY | 108 | 0.25 | 0.833 [0.75, 0.91] | 0.833 | 0.000 | 0.000 | 158 / 375 / 3315 |
| 8BT | streaming_bench/Prospective Reasoning/RECENT | 108 | 0.25 | 0.778 [0.68, 0.87] | 0.778 | 0.000 | 0.000 | 227 / 838 / 3696 |
| 8BT | streaming_bench/Sequential Question Answering/HISTORY | 250 | 0.25 | 0.492 [0.43, 0.56] | 0.492 | 0.000 | 0.000 | 422 / 1622 / 5497 |
| 8BT | streaming_bench/Sequential Question Answering/RECENT | 250 | 0.25 | 0.544 [0.48, 0.61] | 0.544 | 0.000 | 0.000 | 344 / 1087 / 6678 |
| 8BT | streaming_bench/Spatial Understanding/HISTORY | 246 | 0.25 | 0.736 [0.68, 0.79] | 0.736 | 0.004 | 0.004 | 109 / 1014 / 16384 |
| 8BT | streaming_bench/Spatial Understanding/RECENT | 246 | 0.25 | 0.801 [0.75, 0.85] | 0.801 | 0.000 | 0.000 | 99 / 516 / 3816 |
| 8BT | streaming_bench/Text-Rich Understanding/HISTORY | 321 | 0.25 | 0.882 [0.84, 0.92] | 0.882 | 0.000 | 0.000 | 72 / 297 / 2644 |
| 8BT | streaming_bench/Text-Rich Understanding/RECENT | 321 | 0.25 | 0.879 [0.84, 0.91] | 0.879 | 0.000 | 0.000 | 85 / 375 / 4841 |
| 32BT | streaming_bench/Action Perception/HISTORY | 352 | 0.25 | 0.824 [0.78, 0.86] | 0.824 | 0.000 | 0.000 | 91 / 215 / 2728 |
| 32BT | streaming_bench/Action Perception/RECENT | 352 | 0.25 | 0.807 [0.77, 0.84] | 0.807 | 0.000 | 0.000 | 132 / 393 / 3084 |
| 32BT | streaming_bench/Anomaly Context Understanding/HISTORY | 250 | 0.25 | 0.440 [0.37, 0.50] | 0.440 | 0.004 | 0.004 | 306 / 1329 / 16384 |
| 32BT | streaming_bench/Anomaly Context Understanding/RECENT | 250 | 0.25 | 0.732 [0.67, 0.80] | 0.732 | 0.000 | 0.000 | 376 / 1187 / 2846 |
| 32BT | streaming_bench/Attribute Perception/HISTORY | 311 | 0.25 | 0.900 [0.86, 0.93] | 0.900 | 0.000 | 0.000 | 73 / 248 / 3273 |
| 32BT | streaming_bench/Attribute Perception/RECENT | 311 | 0.25 | 0.920 [0.89, 0.95] | 0.920 | 0.000 | 0.000 | 71 / 239 / 2174 |
| 32BT | streaming_bench/Causal Reasoning/HISTORY | 128 | 0.25 | 0.836 [0.76, 0.91] | 0.836 | 0.000 | 0.000 | 160 / 350 / 1476 |
| 32BT | streaming_bench/Causal Reasoning/RECENT | 128 | 0.25 | 0.734 [0.67, 0.80] | 0.734 | 0.000 | 0.000 | 206 / 569 / 1436 |
| 32BT | streaming_bench/Clips Summarize/HISTORY | 317 | 0.25 | 0.877 [0.84, 0.91] | 0.877 | 0.000 | 0.000 | 167 / 303 / 2322 |
| 32BT | streaming_bench/Clips Summarize/RECENT | 317 | 0.25 | 0.912 [0.88, 0.94] | 0.912 | 0.000 | 0.000 | 183 / 373 / 2006 |
| 32BT | streaming_bench/Counting/HISTORY | 188 | 0.25 | 0.644 [0.56, 0.73] | 0.644 | 0.000 | 0.000 | 413 / 4470 / 9222 |
| 32BT | streaming_bench/Counting/RECENT | 188 | 0.25 | 0.415 [0.32, 0.51] | 0.415 | 0.000 | 0.000 | 244 / 1287 / 4748 |
| 32BT | streaming_bench/Event Understanding/HISTORY | 158 | 0.25 | 0.772 [0.70, 0.84] | 0.772 | 0.000 | 0.000 | 114 / 811 / 5581 |
| 32BT | streaming_bench/Event Understanding/RECENT | 158 | 0.25 | 0.759 [0.68, 0.83] | 0.759 | 0.000 | 0.000 | 158 / 1146 / 4342 |
| 32BT | streaming_bench/Misleading Context Recognition/HISTORY | 250 | 0.25 | 0.544 [0.47, 0.62] | 0.544 | 0.000 | 0.000 | 406 / 1674 / 7161 |
| 32BT | streaming_bench/Misleading Context Recognition/RECENT | 250 | 0.25 | 0.724 [0.66, 0.78] | 0.724 | 0.000 | 0.000 | 426 / 2757 / 7839 |
| 32BT | streaming_bench/Object Perception/HISTORY | 369 | 0.25 | 0.848 [0.81, 0.88] | 0.848 | 0.000 | 0.000 | 78 / 297 / 1814 |
| 32BT | streaming_bench/Object Perception/RECENT | 369 | 0.25 | 0.867 [0.83, 0.90] | 0.867 | 0.000 | 0.000 | 82 / 251 / 1700 |
| 32BT | streaming_bench/Prospective Reasoning/HISTORY | 108 | 0.25 | 0.843 [0.79, 0.90] | 0.843 | 0.000 | 0.000 | 145 / 338 / 3291 |
| 32BT | streaming_bench/Prospective Reasoning/RECENT | 108 | 0.25 | 0.843 [0.78, 0.90] | 0.843 | 0.000 | 0.000 | 191 / 411 / 7319 |
| 32BT | streaming_bench/Sequential Question Answering/HISTORY | 250 | 0.25 | 0.544 [0.48, 0.60] | 0.544 | 0.000 | 0.000 | 262 / 1065 / 3055 |
| 32BT | streaming_bench/Sequential Question Answering/RECENT | 250 | 0.25 | 0.564 [0.50, 0.63] | 0.564 | 0.000 | 0.000 | 245 / 698 / 3063 |
| 32BT | streaming_bench/Spatial Understanding/HISTORY | 246 | 0.25 | 0.789 [0.73, 0.85] | 0.789 | 0.000 | 0.000 | 94 / 424 / 3153 |
| 32BT | streaming_bench/Spatial Understanding/RECENT | 246 | 0.25 | 0.817 [0.77, 0.86] | 0.817 | 0.000 | 0.000 | 93 / 310 / 4073 |
| 32BT | streaming_bench/Text-Rich Understanding/HISTORY | 321 | 0.25 | 0.907 [0.87, 0.94] | 0.907 | 0.000 | 0.000 | 78 / 250 / 4985 |
| 32BT | streaming_bench/Text-Rich Understanding/RECENT | 321 | 0.25 | 0.894 [0.86, 0.93] | 0.894 | 0.000 | 0.000 | 90 / 317 / 3804 |
