# StudyB1-h100: per-question accuracy of Qwen3-VL-32B Instruct and Thinking on OVO-Bench and RTV-Bench

**E-id:** StudyB1-h100 (pre-registered 2026-11-05 ~19:40, before any B1 inference; authorised by the user).

**Status:** IN PROGRESS. **SNAPSHOT 2026-11-06 ~13:20: 32B-Thinking RESUMED with no deadline at the user's request (10:09); still running.** The numbers below are from the 09:00 deadline-stopped state (32B-T 5,818 / 15,286 main questions). `b1_rows_32BT.jsonl.gz` in this commit already holds more rows (a mid-run snapshot), so `b1_results_h100nvl.json` does not yet reflect them. Final numbers replace this section when the resumed run ends. Sections written before inference are marked.

**Scope:** a descriptive capability pass at each benchmark's query time.
- **No time-shift, policy or latency claim.** Batched, concurrency 8; no latency is reported.
- HERBench and StreamingBench are not run: their videos are not on this host.

**Input code path:** `experiments/benchmarks/b1_common.py`.
- SHA-256 at registration: `50d3d54d39662302997250b80e2fb23bf47da731abec1a80cbb27d49676a8b19`.
- The SHA-256 at run time is recorded in the run meta.

## Query time (written before inference)
The query time t is the field a cited source identifies; it is used **unrounded**.

**OVO-Bench** (code @ `c34093f9`):
- t = `realtime` for every single-query entry (backward and real-time tasks, 1,468 entries).
- t = `test_info[j]["realtime"]` for every forward sub-query (REC 698, SSR 629, CRR 240), each evaluated at its own time.
- **Source:** `utils/chunk_videos.py` cuts the evaluation clip to `[0, ceil(realtime)]` per entry and per `test_info[j]`, and `utils/OVOBench.py` runs one inference per entry and per `test_info[j]` on that clip.
- README: "Real-Time Visual Perception: … events as they unfold at the current timestamp".
- **Unexplained gap:** the README reports a mean query timestamp of 263.42 s; the mean of these fields is 235.4 s (single queries) and 211.1 s (all). The source may average differently.
- **Upstream `ceil()`** lets the model see up to 1 s after `realtime`. Here no frame is later than t, so results are **not like-for-like** with published OVO-Bench numbers.

**RTV-Bench** (code @ `a928cbe8`, HF @ `62ec75f8`):
- t = `end_time`.
- **Sources:**
  - `scripts/infer/infer_model_rtv.py` with `scripts/utils/video_utils.crop_video_ffmpeg` gives the model the video `[0, end_time]` (`-ss 0 -t end_time`).
  - `prepare_rtv_clips.py` clips `[start_time, end_time]`, and `start_time` = 0 for all 4,608 items.
  - The README figure `asset/1_examples.png` shows "In the current scene, …" questions with answers labelled by timestamp.
- **This is a reading of the evaluation protocol, not a field documented as "query time".** Flash's notes leave RTV's query timestamp empty. Flagged for the user; the RTV results can be dropped if this reading is not accepted.

**Not covered by a cited query time:** nothing beyond the flags above. No part was skipped for an unknown meaning.

**Tasks requiring video after the query time:** none under the upstream protocols, so **none excluded**.
- OVO forward sub-queries are each asked at their own time.
- RTV Future-Prediction (FP) tasks ask for a prediction at `end_time`, and upstream gives no later video.
- Listed for review: RTV `*-FP` (586 items) and OVO `REC` / `SSR` / `CRR`.

**Edge cases (logged per request):**
- RTV: 12 items with `end_time` after the video's end; they get the last frames.
- RTV: 96 items with t < 3 s, giving a shorter RECENT span.
- OVO: 3 single queries with `realtime` after the video's end.

## Input (written before inference)
- **Frame choice:** PyAV decode timestamps. Each target takes the **latest decoded frame with pts ≤ target**: seek to the keyframe at or before the target and decode forward; re-seek earlier if the first decoded frame is after the target.
  - Equal to a full sequential decode on **72 / 72** checks, covering 24 (dataset, codec, height) groups, RECENT, HISTORY and short-span cases (`results/benchmarks/study_b1_h100/frame_selection_check.json`).
  - Every frame is at or before t (asserted per request).
- **Inputs:**
  - RECENT = 9 targets evenly spaced over [max(0, t − 3), t]; a shorter span when t < 3 is logged.
  - HISTORY = 37 targets evenly spaced over [0, t].
  - Requests with fewer distinct frames than N are logged (`n_distinct`).
- **Images:** LANCZOS to 768 × 432 (not aspect-preserving, as specified), lossless PNG (compress_level 1), SHA-256 per frame logged. No frames stored; a 256-entry in-memory cache per worker.
- **Versions:** PyAV 17.1.0, libavcodec 62.28.101, libavformat 62.12.101, PIL 12.3.0.
- HISTORY render time on the four longest videos (2.0–2.8 h): 1.6–6.5 s per request.
- **Template (one per dataset; exact wording):**
  ```
  The following are {N} frames from a video, in order from oldest to newest.
  <N images, separate, oldest first>
  Question: {question, verbatim}
  Options:
  A. {option, verbatim}
  ...
  Answer with the option's letter from the given choices directly.
  ```
  - Options are lettered as the annotation gives them: OVO list index → A, B, …; RTV dict keys, sorted.
  - **OVO forward tasks (REC / SSR / CRR) have no options in the annotation.** Their text is the upstream template (`constant.py`, read verbatim by parsing, not executing, the cloned file; SHA-256 in run meta), filled as `OVOBench.build_prompt` does, with its own answer instruction ("a single number" / "Yes" or "No").
  - The option-letter instruction cannot apply to these tasks: **a recorded deviation from "one fixed template"**.
  - No timestamps or file names appear in any prompt.

## Mechanism verification (Steps 1, 2 and 5 written before inference; Steps 3 and 4 from the `mv` step, before the sweep)
**Step 1: causal chain.**
- The claim is that, on identical causal input, model capability and reasoning mode change per-question correctness.
- Link to FORMULATION.md §Regime uncertainty / §Decisions: the system chooses which capability to provision for a query. That choice matters only if the capability tiers answer the same query differently.
- Chain: the same frames (identical SHA-256) and the same prompt reach every arm → the arms differ only in weights (4B vs 32B) or in reasoning mode and its decoding (Instruct greedy vs Thinking sampled with up to 16k reasoning tokens) → the generated answer differs → the upstream parser scores it differently → per-question correctness differs.

**Step 2: instantiate each link.**

| causal link | implementing quantity | value / range in this run | varies as expected? | evidence |
|---|---|---|---|---|
| identical input across arms | per-request frame SHA-256 lists and prompt tokens, compared across arms on matched (item, input) | 0 frame mismatches in 8,218 matched pairs; prompt tokens equal (4B vs 32B-I), +2 on every 32B-T (template prefix) | CONSTANT, as required | analysis check |
| arm differs | served model / revision; decoding settings | 4BI / 32BI / 32BT; greedy vs T 1.0 | yes, by construction | run meta |
| reasoning mode active | Thinking completion tokens; `</think>` closed | p50 133–150, p90 672–1,368, max 16,384; `</think>` closed on all but 2 / 5,818 | > 0 and varies by item: yes | rows |
| answer differs | per-question disagreement between arms on matched items | 32B-T vs 32B-I 13–18 %; 32B-I vs 4B-I 15–23 % | > 0 % repeat control: yes | rows |
| correctness differs | per-question correctness difference (matched) | 32B-T − 32B-I −0.019 to +0.024; 32B-I − 4B-I +0.007 to +0.077 | — | analysis |

**Step 3: trace one request** (`b1_mv_32BI.jsonl.gz`, recorded 2026-11-05 19:46, before any sweep). 32B-I, RECENT, RTV `rtv_2420_q-group-jigunncp6-2-option0` (Object-SP), video `embodied_perspective/EmbodiedPerspective_082.mp4`, t = `end_time` = 55.43 s.

| step | value |
|---|---|
| targets (9 over [52.43, 55.43]) | 52.430, 52.805, 53.180, 53.555, 53.930, 54.305, 54.680, 55.055, 55.430 |
| selected frame pts (latest ≤ target) | 52.400, 52.800, 53.167, 53.533, 53.900, 54.300, 54.667, 55.033, 55.400 (all ≤ t; 9 distinct; span 3.0 s) |
| frame SHA-256 (first two) | `0425ab27f5b53d09…`, `4e9f244e301b11c9…` (all 9 logged) |
| prompt text after the 9 images | "Question: How many cups/bowls are currently cleaned and placed in the basin?\nOptions:\nA. 4\nB. 5\nC. 6\nD. 7\nAnswer with the option's letter from the given choices directly." |
| prompt / completion tokens | 3,118 / 5 (finish `stop`) |
| response | "A. 4" (first-token top 3: A −0.40, B −1.28, C −3.03) |
| upstream parser (`extract_pred_letter`) | A; ground truth A → **correct** |
| strict parser | A (ok) |

- The same item under HISTORY (37 frames over [0, 55.43]; 12,583 prompt tokens) answered "B. 5", which is wrong.
- All 18 smoke requests:
  - completed with finish `stop` and 2–8 completion tokens;
  - had every frame ≤ t;
  - had prompt tokens of 3,106–3,193 (RECENT) and 12,571–12,658 (HISTORY).
- The 37-image server setting is in effect: `limit_mm_per_prompt {'image': 37, 'video': 0}` in the server log, and the first 37-image request succeeded.

**Step 4 result (recorded before the sweep):**
- **Repeat control:** 32B-I on identical input, the first 10 RECENT items of each part sent twice. **30 / 30 identical response texts, 30 / 30 identical correctness, 30 / 30 identical frame SHA-256 lists.** Disagreement with the arm difference disabled = 0 (accuracy 76.7 % in both runs).
- **Grey smoke:** 4 requests. CRR / SSR-type items answer "No"; the REC item answers "0".
- **PASS:** the mechanism collapses to the null when disabled, so any between-arm disagreement in the sweep is attributable to the arm, not to run-to-run noise.

**Recorded scorer caveat (before the sweep):** OVO-Bench's upstream multiple-choice scorer is `int(gt in response)`, a substring test.
- A wrong answer containing the ground-truth capital letter elsewhere (e.g. "C. A man …" with ground truth A) is scored correct.
- Upstream accuracy stays the registered primary.
- A strict-parser accuracy (exactly one valid letter, equal to the ground truth) is reported beside it.

**Step 4: negative control.** The arm difference is disabled by running the **same arm twice** on identical input: 32B-I, the first 10 RECENT items of each part, twice. Per-question disagreement must collapse to ~0. Grey frames (the visual input removed) must fall to about the guessing floor. (Filled before the sweep.)

**Step 5: alternative explanation.**
- A Thinking − Instruct difference could come from **answer-format compliance or truncation** rather than capability: Thinking may not close `</think>` within 16k tokens, or may phrase the answer so the upstream parser misses it.
- **Distinguishing data:**
  - truncation and unparsed rates per arm;
  - accuracy on parsed-only items;
  - the strict parser's ambiguity counts.
- A 4B vs 32B difference could likewise come from format compliance. The same split separates it.
- Thinking also changes decoding (sampled vs greedy), so **reasoning mode and decoding are confounded by design**. This cannot be separated here and is stated as a limitation.

## Run record (written after the run)
- **Host / GPU:** h100nvl GPU 2, vLLM 0.31.0, FlashAttention 3 for both the language model and the vision encoder (the same in all three server logs), prefix caching off, `--mm-processor-cache-gb 0`, `--limit-mm-per-prompt {"image": 37, "video": 0}`, max_model_len 32,768, concurrency 8.
- `b1_common.py` SHA-256 at the end of the run equals the registration SHA (`50d3d54d…8b19`), so the input code path did not change during the run.
- **Order run:**
  - mv (19:42);
  - 4B-I bridge (19:45–19:52, 1,400 requests);
  - 32B-I (19:54 → 02:47 Nov 6, 15,486 requests);
  - 32B-T (02:48 → deadline stop 09:00:05, 6,018 requests).
- **Errors:** 0 request errors and 0 still-failed requests in every arm. 0 `ERROR` / `Traceback` lines in any server log.
- **GPU 2:** no foreign process at any point; no stop rule fired. Free disk on the data volume stayed at 37–38 GB.
- **Stops:** one, the registered 09:00 deadline. 32B-T sent no request after 09:00:05 and drained in-flight requests by 09:01:02.

### Coverage

| arm | planned main requests | answered | coverage |
|---|---|---|---|
| 4B-I bridge | 1,200 (first 300 per dataset × input) + 200 grey | 1,400 | 100 % |
| 32B-I | 15,286 + 200 grey | 15,486 | 100 % |
| 32B-T | 15,286 + 200 grey | 6,018 (5,818 main + 200 grey) | 38 % of main |

- 32B-T covered:
  - the first 1,000 questions of each OVO part under both inputs;
  - the first 1,000 RTV questions under RECENT and 818 under HISTORY (the batch in progress at the deadline).
- These are the leading questions of the task-stratified seed-0 order, so each task appears in proportion (OVO 64–68 %, RTV 18–22 % per task).
- **Every 32B-T comparison below is on matched questions only.** The 32B-T rows are not a full-benchmark number.

## Observations (written after the run; no interpretation in this section)

### Accuracy by dataset, part, input and arm
- "floor" is the expected accuracy of a uniform guess over the options, averaged over the items that have one. **OVO REC (an open count) has no floor**, so the `ovo_forward` floor of 0.50 covers SSR and CRR only (`guess_floor_n` in the results JSON).
- "strict" is exactly one valid answer equal to the ground truth.
- Unparsed, empty and truncated answers are counted wrong in both columns.
- Per-task rows are in the appendix (36 tasks per arm × input).

| arm | cell | n | coverage | floor | accuracy (upstream) [video CI] | strict | trunc | unparsed | compl. tokens p50/p90/max |
|---|---|---|---|---|---|---|---|---|---|
| 4BI | ovo_bench/HISTORY | 300 | 1.00 | 0.35 | 0.573 [0.51, 0.63] | 0.550 | 0.000 | 0.030 | 2 / 11 / 23 |
| 4BI | ovo_bench/RECENT | 300 | 1.00 | 0.35 | 0.560 [0.49, 0.62] | 0.540 | 0.000 | 0.027 | 2 / 11 / 23 |
| 4BI | ovo_bench:ovo_forward/HISTORY | 155 | 1.00 | 0.50 | 0.523 [0.44, 0.60] | 0.523 | 0.000 | 0.000 | 2 / 2 / 3 |
| 4BI | ovo_bench:ovo_forward/RECENT | 155 | 1.00 | 0.50 | 0.439 [0.35, 0.53] | 0.439 | 0.000 | 0.000 | 2 / 2 / 2 |
| 4BI | ovo_bench:ovo_other/HISTORY | 145 | 1.00 | 0.27 | 0.628 [0.54, 0.71] | 0.579 | 0.000 | 0.062 | 7 / 14 / 23 |
| 4BI | ovo_bench:ovo_other/RECENT | 145 | 1.00 | 0.27 | 0.690 [0.61, 0.77] | 0.648 | 0.000 | 0.055 | 6 / 13 / 23 |
| 4BI | rtv_bench/HISTORY | 300 | 1.00 | 0.30 | 0.610 [0.56, 0.66] | 0.610 | 0.000 | 0.000 | 5 / 7 / 13 |
| 4BI | rtv_bench/RECENT | 300 | 1.00 | 0.30 | 0.670 [0.62, 0.73] | 0.670 | 0.000 | 0.000 | 5 / 7 / 11 |
| 32BI | ovo_bench/HISTORY | 3035 | 1.00 | 0.35 | 0.629 [0.60, 0.66] | 0.610 | 0.000 | 0.022 | 2 / 10 / 64 |
| 32BI | ovo_bench/RECENT | 3035 | 1.00 | 0.35 | 0.577 [0.54, 0.61] | 0.561 | 0.002 | 0.019 | 2 / 7 / 64 |
| 32BI | ovo_bench:ovo_forward/HISTORY | 1567 | 1.00 | 0.50 | 0.555 [0.50, 0.60] | 0.555 | 0.000 | 0.000 | 2 / 2 / 3 |
| 32BI | ovo_bench:ovo_forward/RECENT | 1567 | 1.00 | 0.50 | 0.412 [0.36, 0.46] | 0.412 | 0.000 | 0.000 | 2 / 2 / 3 |
| 32BI | ovo_bench:ovo_other/HISTORY | 1468 | 1.00 | 0.26 | 0.708 [0.68, 0.74] | 0.668 | 0.001 | 0.046 | 6 / 13 / 64 |
| 32BI | ovo_bench:ovo_other/RECENT | 1468 | 1.00 | 0.26 | 0.754 [0.73, 0.78] | 0.721 | 0.004 | 0.039 | 2 / 10 / 64 |
| 32BI | rtv_bench/HISTORY | 4608 | 1.00 | 0.30 | 0.600 [0.58, 0.62] | 0.599 | 0.001 | 0.003 | 2 / 6 / 64 |
| 32BI | rtv_bench/RECENT | 4608 | 1.00 | 0.30 | 0.687 [0.67, 0.70] | 0.686 | 0.002 | 0.003 | 2 / 6 / 64 |
| 32BT | ovo_bench/HISTORY | 2000 | 0.66 | 0.35 | 0.639 [0.61, 0.67] | 0.638 | 0.001 | 0.002 | 141 / 1368 / 16384 |
| 32BT | ovo_bench/RECENT | 2000 | 0.66 | 0.35 | 0.608 [0.57, 0.65] | 0.608 | 0.000 | 0.001 | 133 / 732 / 4802 |
| 32BT | ovo_bench:ovo_forward/HISTORY | 1000 | 0.64 | 0.50 | 0.595 [0.54, 0.65] | 0.595 | 0.001 | 0.001 | 237 / 2501 / 16384 |
| 32BT | ovo_bench:ovo_forward/RECENT | 1000 | 0.64 | 0.50 | 0.455 [0.40, 0.51] | 0.455 | 0.000 | 0.000 | 156 / 955 / 4802 |
| 32BT | ovo_bench:ovo_other/HISTORY | 1000 | 0.68 | 0.26 | 0.683 [0.65, 0.72] | 0.682 | 0.001 | 0.002 | 104 / 365 / 16384 |
| 32BT | ovo_bench:ovo_other/RECENT | 1000 | 0.68 | 0.26 | 0.761 [0.73, 0.79] | 0.760 | 0.000 | 0.001 | 116 / 420 / 3973 |
| 32BT | rtv_bench/HISTORY | 818 | 0.18 | 0.30 | 0.616 [0.59, 0.65] | 0.615 | 0.000 | 0.004 | 150 / 672 / 7012 |
| 32BT | rtv_bench/RECENT | 1000 | 0.22 | 0.30 | 0.691 [0.66, 0.72] | 0.690 | 0.000 | 0.005 | 139 / 722 / 6040 |

**Spread across tasks** (min–max accuracy over the 36 tasks):
- 32B-I: 0.17–0.97 (RECENT), 0.40–0.86 (HISTORY).
- 32B-T: 0.21–0.96 (RECENT), 0.43–0.83 (HISTORY).
- The minimum is OVO REC under RECENT in both arms.

### Truncation, unparsed answers and generated tokens (main questions)

| arm | cell | n | truncated | unparsed | of which ambiguous (strict) | no `</think>` answer region | accuracy on parsed only |
|---|---|---|---|---|---|---|---|
| 4B-I | OVO RECENT / HISTORY | 300 / 300 | 0 / 0 | 8 / 9 | 7 / 8 | — | 0.555 / 0.567 |
| 4B-I | RTV RECENT / HISTORY | 300 / 300 | 0 / 0 | 0 / 0 | 0 / 0 | — | 0.670 / 0.610 |
| 32B-I | OVO RECENT / HISTORY | 3,035 / 3,035 | 6 / 1 | 57 / 68 | 52 / 66 | — | 0.573 / 0.625 |
| 32B-I | RTV RECENT / HISTORY | 4,608 / 4,608 | 9 / 3 | 13 / 12 | 8 / 10 | — | 0.688 / 0.601 |
| 32B-T | OVO RECENT / HISTORY | 2,000 / 2,000 | 0 / 2 | 1 / 3 | 1 / 1 | 0 / 2 | 0.608 / 0.639 |
| 32B-T | RTV RECENT / HISTORY | 1,000 / 818 | 0 / 0 | 5 / 3 | 4 / 2 | 0 / 0 | 0.693 / 0.617 |

- **32B-I truncation:** the 64-token cap; at most 0.4 % per cell.
- **32B-T truncation:** the 16,384-token cap. 2 truncations in 5,818 main questions, both OVO HISTORY.
- **32B-T reasoning lengths:** p50 133–150 tokens per dataset × input; p90 672–1,368; max 16,384.
- **OVO multiple-choice "unparsed" for the Instruct arms is mostly ambiguous answers:** the response contains more than one option letter, e.g. "C. A man…". Under the upstream substring scorer these can still score correct, which is why upstream accuracy exceeds strict accuracy by up to 0.04 on OVO "other" and by 0 on RTV.

### Thinking − Instruct, HISTORY − RECENT, 32B − 4B (matched questions; video bootstrap, 2,000 resamples, seed 0)
- **Input, stack and decoding:**
  - **Same input in every row:** frame SHA-256 lists are identical on every matched request (0 mismatches: 4B|32B-I 1,200, 4B|32B-T 1,200, 32B-I|32B-T 5,818).
  - **Prompt tokens:** identical for 4B-I vs 32B-I; **exactly +2 on every 32B-T request** (7,018 of 7,018). This is the Thinking chat template's generation prefix, not an input difference.
  - **Same stack:** host, GPU, vLLM and backend are the same for every arm.
  - **Decoding differs** between Thinking and Instruct by design (sampled with up to 16k tokens vs greedy with 64), so reasoning mode and decoding are confounded.
  - **HISTORY − RECENT is a comparison of INPUTS** at a fixed frame count (37 frames over [0, t] vs 9 over the last 3 s): about 4× the prompt tokens (12.6k vs 3.1k). It is not a frame-budget-matched comparison.

| comparison | n | n videos | acc a | acc b | diff a−b [video CI] | disagree |
|---|---|---|---|---|---|---|
| 4BI/ovo_bench/HISTORY-RECENT | 300 | 210 | 0.573 | 0.560 | +0.013 [-0.041, +0.073] | 0.260 |
| 4BI/rtv_bench/HISTORY-RECENT | 300 | 235 | 0.610 | 0.670 | -0.060 [-0.108, -0.010] | 0.200 |
| 32BI/ovo_bench/HISTORY-RECENT | 3035 | 644 | 0.629 | 0.577 | +0.051 [+0.029, +0.073] | 0.244 |
| 32BI/rtv_bench/HISTORY-RECENT | 4608 | 552 | 0.600 | 0.687 | -0.087 [-0.101, -0.073] | 0.227 |
| 32BT/ovo_bench/HISTORY-RECENT | 2000 | 568 | 0.639 | 0.608 | +0.031 [+0.003, +0.061] | 0.252 |
| 32BT/rtv_bench/HISTORY-RECENT | 818 | 407 | 0.616 | 0.685 | -0.068 [-0.097, -0.040] | 0.220 |
| 32BT-32BI/ovo_bench/RECENT | 2000 | 568 | 0.608 | 0.584 | +0.024 [+0.009, +0.039] | 0.132 |
| 32BT-32BI/ovo_bench/HISTORY | 2000 | 568 | 0.639 | 0.631 | +0.007 [-0.014, +0.029] | 0.179 |
| 32BT-32BI/rtv_bench/RECENT | 1000 | 447 | 0.691 | 0.710 | -0.019 [-0.041, +0.004] | 0.137 |
| 32BT-32BI/rtv_bench/HISTORY | 818 | 407 | 0.616 | 0.612 | +0.004 [-0.020, +0.030] | 0.141 |
| 32BI-4BI/ovo_bench/RECENT | 300 | 210 | 0.603 | 0.560 | +0.043 [-0.006, +0.094] | 0.150 |
| 32BI-4BI/ovo_bench/HISTORY | 300 | 210 | 0.650 | 0.573 | +0.077 [+0.025, +0.128] | 0.223 |
| 32BI-4BI/rtv_bench/RECENT | 300 | 235 | 0.693 | 0.670 | +0.023 [-0.024, +0.073] | 0.183 |
| 32BI-4BI/rtv_bench/HISTORY | 300 | 235 | 0.617 | 0.610 | +0.007 [-0.045, +0.063] | 0.227 |
| 32BT-4BI/ovo_bench/RECENT | 300 | 210 | 0.633 | 0.560 | +0.073 [+0.020, +0.127] | 0.173 |
| 32BT-4BI/ovo_bench/HISTORY | 300 | 210 | 0.630 | 0.573 | +0.057 [+0.003, +0.110] | 0.257 |
| 32BT-4BI/rtv_bench/RECENT | 300 | 235 | 0.697 | 0.670 | +0.027 [-0.017, +0.072] | 0.160 |
| 32BT-4BI/rtv_bench/HISTORY | 300 | 235 | 0.653 | 0.610 | +0.043 [-0.014, +0.103] | 0.263 |

**Observed, matched:**
- **32B-T − 32B-I:**
  - +0.024 [+0.009, +0.039] on OVO RECENT;
  - +0.007 [−0.014, +0.029] on OVO HISTORY;
  - −0.019 [−0.041, +0.004] on RTV RECENT;
  - +0.004 [−0.020, +0.030] on RTV HISTORY.
  - Per-question disagreement is 13–18 %, against 0 % for the same arm run twice (repeat control).
- **HISTORY − RECENT** has the same sign in all three arms:
  - positive on OVO: 32B-I +0.051 [+0.029, +0.073];
  - negative on RTV: 32B-I −0.087 [−0.101, −0.073].
  - Within OVO, the HISTORY gain comes from the forward tasks (REC 0.17 → 0.42 and CRR 0.40 → 0.54 for 32B-I), while OVO "other" goes down (0.754 → 0.708).
- **32B-I − 4B-I** (n 300 per cell): +0.077 [+0.025, +0.128] on OVO HISTORY. The other three cells have CIs that include 0.

**OVO CRR below 0.5 under RECENT:**
- 32B-I scores 0.396 [0.37, 0.42] and 32B-T 0.425.
- CRR's ground truth is "Yes" on 144 / 240 questions.
- 32B-I answers "No" on 205 / 240 under RECENT and on 137 / 240 under HISTORY. 32B-T answers "No" on 127 / 153 and 112 / 153.
- Always answering "No" would score 0.40.

### Grey-frame control (visual input removed; first 50 questions of each dataset's order, the same 100 per arm × input)

| arm/input | n | accuracy | guessing floor | answers | unparsed | truncated |
|---|---|---|---|---|---|---|
| 4BI/RECENT | 100 | 0.34 | 0.32 | {'A': 35, 'No': 15, 'B': 15, 'D': 13, '0': 11, 'C': 11} | 0 | 0 |
| 4BI/HISTORY | 100 | 0.36 | 0.32 | {'A': 35, 'B': 17, 'No': 15, 'C': 12, '0': 11, 'D': 10} | 0 | 0 |
| 32BI/RECENT | 100 | 0.37 | 0.32 | {'A': 33, 'B': 17, 'No': 15, 'D': 12, '0': 11, 'C': 11, 'None': 1} | 1 | 1 |
| 32BI/HISTORY | 100 | 0.39 | 0.32 | {'A': 27, 'B': 20, 'No': 15, 'D': 15, '0': 11, 'C': 11, 'None': 1} | 1 | 1 |
| 32BT/RECENT | 100 | 0.35 | 0.32 | {'A': 27, 'B': 20, 'D': 17, 'No': 15, '0': 11, 'C': 9, 'None': 1} | 1 | 0 |
| 32BT/HISTORY | 100 | 0.31 | 0.32 | {'A': 24, 'B': 20, 'D': 17, 'No': 15, 'C': 13, '0': 11} | 0 | 0 |

- **Grey accuracy vs floor:** grey accuracy is 0.31–0.39 against a floor of 0.32 in every arm × input. The upper end is 0.07 above the floor.
- **Answers are skewed:** "A" is the most frequent letter, and every arm answers "No" to all 15 SSR / CRR items and "0" to all 11 REC items.
- **Real frames vs grey:** on the same 100 questions with real frames, 32B-I scores 0.67 under both RECENT and HISTORY.

### Other checks
- **Frames at or before t:** every frame of every request is at or before t (asserted per request and re-checked in the analysis; `frames_le_t` = true).
- **Fewer distinct frames than N:**
  - 32B-I: 194 RECENT and 136 HISTORY requests;
  - 32B-T: 129 and 57;
  - 4B-I: 21 and 12.
  - Causes: short videos, a low frame rate, or RTV t beyond the video end.
- **Short span:** 139 RECENT requests had t < 3 s, so their span was shorter than 3 s.
- **First target before the first frame:** 4,025 requests, mostly HISTORY, whose first target is 0. The first frame is used; it is still ≤ t.
- **Repeat control (mv):** 30 / 30 identical texts, correctness and frames.
- **Published numbers:** not compared. The input is not like-for-like with OVO-Bench or RTV-Bench published results:
  - upstream `ceil(t)` is not reproduced;
  - the frame count and resolution differ;
  - the prompt differs.

## Results consistency check (6 checks, before the interpretation)
1. **Cross-check against committed measurements.**

   | quantity | this run | prior run | source of prior | ratio | agree? |
   |---|---|---|---|---|---|
   | prompt tokens per 768×432 frame (Qwen3-VL) | ≈ 340 (RECENT 3,140 / 9; HISTORY 12,605 / 37, including text) | ≈ 336 | StudyD4-orin / StudyClean H100 byte-identical frames | 1.01 | agree |
   | 32B-I throughput, ~3.1k-token requests, conc 8 | ≈ 1.7 req/s (RECENT phase, wall-clock) | 1.8 req/s peak at N = 9 | StudyD7 (`reports/study_d7_capacity.md`) | 0.94 | agree |
   | Thinking − Instruct, 32B, matched vLLM stack | +0.004 to +0.024 (OVO), −0.019 to +0.004 (RTV) | pooled +0.5 pp [−2.6, +3.8] on images | StudyD9 | — (different benchmark) | same order, no > 2× conflict |
   | Thinking truncation at 16,384 | 0.03 % (2 / 5,818) | 25.8 % on STARK time series | StudyD12 | — (different task) | not comparable; noted |

   No disagreement > 2× on a like-for-like quantity.
2. **Physical plausibility.**
   - 32B-I HISTORY ran at ≈ 0.39 req/s × ≈ 12.6k prompt tokens ≈ 4.9k tokens/s prefill. RECENT ran at ≈ 1.7 × 3.1k ≈ 5.3k tokens/s.
   - Both are within the D7 / D4 32B H100 curves, with prefix caching off. Nothing is faster than the committed curves.
   - 32B-T: 6,018 requests in 6 h 12 m (0.27 req/s).
3. **Distribution sanity.**
   - Per-task accuracy spans 0.17–0.97, and completion tokens range 1–64 (Instruct) and up to 16,384 (Thinking).
   - Prompt tokens vary per request (3,106–3,196 RECENT; 12,571–12,661 HISTORY) with the question length. No constant appears where a distribution is expected.
   - The +2 prompt-token offset is constant by construction (template).
4. **Definition audit.**
   - **RECENT / HISTORY:** RECENT = 9 frames over [max(0, t − 3), t] and HISTORY = 37 frames over [0, t], at 768×432. These are defined in this study. **Name clash:** "RECENT" is also used in the D-series and StudyClean (K3 RECENT) with a different window. Here it always means the B1 definition.
   - **Query time:** as cited above; the RTV reading is flagged.
   - **Accuracy:** upstream scorer (primary), with strict beside it.
5. **Claim linkage.**
   - This bears on FORMULATION.md §Regime uncertainty / §Decisions: whether capability tiers answer the same query differently.
   - **Supports:** tiers disagree on 13–26 % of matched questions, far above the 0 % repeat-control floor.
   - **Does not speak to:** any policy, latency or time-shift claim, by design.
   - It does not measure anything scoped out.
6. **Proxy validity.**
   - **RTV `end_time` as the query time** is a reading of the evaluation protocol, not a documented field. The RTV rows are valid only under that reading; flagged for the user.
   - **The upstream OVO multiple-choice scorer (`gt in response`)** is a lenient proxy for "chose the right option". Strict accuracy is reported beside it; they differ by ≤ 0.05 per dataset / part cell (up to 0.17 on single small tasks, e.g. 4B-I OJR). Paired comparisons were computed on the upstream scorer only.

**Outcome:** no check failed. Two items are flagged for the user: RTV query-time reading, OVO forward-template deviation.

## Interpretation
- **Thinking vs Instruct (32B):** Thinking does not change per-question accuracy materially on these two benchmarks at their query time.
  - The largest matched difference is +2.4 pp (OVO RECENT), and three of four cells have CIs including 0, on 38 % coverage of the Thinking arm.
  - It does change which questions are answered correctly (13–18 % disagreement), at about 70× the generated tokens at the median (p50 ≈ 2 vs ≈ 140).
  - Reasoning mode and sampled decoding are confounded, so this is the difference between the two configurations, not between reasoning and no reasoning.
- **Inputs:**
  - Under these inputs, the full-history input helps OVO's forward-active-responding tasks, which ask about a state that develops over the video (REC counts, CRR clue arrival).
  - It hurts RTV and OVO's other tasks, which ask about the current scene. This matches the RTV-Bench examples ("In the current scene…").
  - These are inputs with different token budgets (≈ 4×), so the result does not separate "more frames" from "older frames".
- **4B vs 32B (bridge, n 300 per cell):** only OVO HISTORY separates (+7.7 pp). The bridge is too small to bound smaller gaps.
- **Low accuracies:**
  - The low REC and CRR accuracies under RECENT are what a 3-second window allows, since the count or clue may lie outside it.
  - CRR's below-0.5 score coincides with a "No" bias on a "Yes"-majority task. The cause of the bias is not tested here.
- **Grey control:** stays near the floor, with a letter-A / "No" bias. The visual input carries the accuracy above the floor.

## Appendix: per-task results (all arms)

| arm | cell | n | coverage | floor | accuracy (upstream) [video CI] | strict | trunc | unparsed | compl. tokens p50/p90/max |
|---|---|---|---|---|---|---|---|---|---|
| 4BI | ovo_bench/ACR/HISTORY | 11 | 1.00 | 0.25 | 0.636 [0.36, 0.91] | 0.636 | 0.000 | 0.091 | 9 / 10 / 14 |
| 4BI | ovo_bench/ACR/RECENT | 11 | 1.00 | 0.25 | 0.727 [0.45, 1.00] | 0.727 | 0.000 | 0.091 | 10 / 12 / 14 |
| 4BI | ovo_bench/ASI/HISTORY | 14 | 1.00 | 0.26 | 0.714 [0.50, 0.93] | 0.714 | 0.000 | 0.000 | 7 / 15 / 19 |
| 4BI | ovo_bench/ASI/RECENT | 14 | 1.00 | 0.26 | 0.500 [0.21, 0.79] | 0.500 | 0.000 | 0.000 | 5 / 13 / 19 |
| 4BI | ovo_bench/ATR/HISTORY | 12 | 1.00 | 0.25 | 0.583 [0.33, 0.83] | 0.583 | 0.000 | 0.000 | 5 / 9 / 11 |
| 4BI | ovo_bench/ATR/RECENT | 12 | 1.00 | 0.25 | 0.750 [0.50, 1.00] | 0.750 | 0.000 | 0.000 | 5 / 11 / 13 |
| 4BI | ovo_bench/CRR/HISTORY | 24 | 1.00 | 0.50 | 0.583 [0.43, 0.76] | 0.583 | 0.000 | 0.000 | 2 / 2 / 2 |
| 4BI | ovo_bench/CRR/RECENT | 24 | 1.00 | 0.50 | 0.542 [0.33, 0.73] | 0.542 | 0.000 | 0.000 | 2 / 2 / 2 |
| 4BI | ovo_bench/EPM/HISTORY | 29 | 1.00 | 0.31 | 0.655 [0.47, 0.82] | 0.586 | 0.000 | 0.069 | 6 / 10 / 15 |
| 4BI | ovo_bench/EPM/RECENT | 29 | 1.00 | 0.31 | 0.621 [0.41, 0.81] | 0.586 | 0.000 | 0.034 | 4 / 8 / 12 |
| 4BI | ovo_bench/FPD/HISTORY | 10 | 1.00 | 0.25 | 0.800 [0.55, 1.00] | 0.800 | 0.000 | 0.000 | 13 / 15 / 15 |
| 4BI | ovo_bench/FPD/RECENT | 10 | 1.00 | 0.25 | 0.700 [0.44, 0.90] | 0.700 | 0.000 | 0.000 | 13 / 15 / 17 |
| 4BI | ovo_bench/HLD/HISTORY | 18 | 1.00 | 0.28 | 0.167 [0.00, 0.38] | 0.167 | 0.000 | 0.000 | 6 / 7 / 8 |
| 4BI | ovo_bench/HLD/RECENT | 18 | 1.00 | 0.28 | 0.389 [0.17, 0.62] | 0.389 | 0.000 | 0.000 | 6 / 7 / 7 |
| 4BI | ovo_bench/OCR/HISTORY | 15 | 1.00 | 0.25 | 0.733 [0.50, 0.94] | 0.667 | 0.000 | 0.067 | 9 / 14 / 23 |
| 4BI | ovo_bench/OCR/RECENT | 15 | 1.00 | 0.25 | 0.867 [0.67, 1.00] | 0.800 | 0.000 | 0.067 | 9 / 14 / 23 |
| 4BI | ovo_bench/OJR/HISTORY | 18 | 1.00 | 0.25 | 0.833 [0.67, 1.00] | 0.667 | 0.000 | 0.222 | 7 / 13 / 14 |
| 4BI | ovo_bench/OJR/RECENT | 18 | 1.00 | 0.25 | 0.944 [0.81, 1.00] | 0.778 | 0.000 | 0.222 | 6 / 13 / 14 |
| 4BI | ovo_bench/REC/HISTORY | 69 | 1.00 | — | 0.362 [0.24, 0.50] | 0.362 | 0.000 | 0.000 | 2 / 2 / 3 |
| 4BI | ovo_bench/REC/RECENT | 69 | 1.00 | — | 0.174 [0.09, 0.27] | 0.174 | 0.000 | 0.000 | 2 / 2 / 2 |
| 4BI | ovo_bench/SSR/HISTORY | 62 | 1.00 | 0.50 | 0.677 [0.58, 0.78] | 0.677 | 0.000 | 0.000 | 2 / 2 / 2 |
| 4BI | ovo_bench/SSR/RECENT | 62 | 1.00 | 0.50 | 0.694 [0.57, 0.82] | 0.694 | 0.000 | 0.000 | 2 / 2 / 2 |
| 4BI | ovo_bench/STU/HISTORY | 18 | 1.00 | 0.26 | 0.611 [0.39, 0.82] | 0.556 | 0.000 | 0.056 | 10 / 13 / 17 |
| 4BI | ovo_bench/STU/RECENT | 18 | 1.00 | 0.26 | 0.778 [0.58, 0.95] | 0.722 | 0.000 | 0.056 | 10 / 13 / 17 |
| 4BI | rtv_bench/Action-FP/HISTORY | 24 | 1.00 | 0.36 | 0.542 [0.33, 0.74] | 0.542 | 0.000 | 0.000 | 4 / 7 / 8 |
| 4BI | rtv_bench/Action-FP/RECENT | 24 | 1.00 | 0.36 | 0.667 [0.48, 0.83] | 0.667 | 0.000 | 0.000 | 4 / 6 / 8 |
| 4BI | rtv_bench/Action-GU/HISTORY | 6 | 1.00 | 0.25 | 0.333 [0.00, 0.67] | 0.333 | 0.000 | 0.000 | 6 / 8 / 11 |
| 4BI | rtv_bench/Action-GU/RECENT | 6 | 1.00 | 0.25 | 0.500 [0.17, 0.83] | 0.500 | 0.000 | 0.000 | 5 / 6 / 6 |
| 4BI | rtv_bench/Action-IA/HISTORY | 22 | 1.00 | 0.36 | 0.818 [0.65, 0.95] | 0.818 | 0.000 | 0.000 | 4 / 8 / 10 |
| 4BI | rtv_bench/Action-IA/RECENT | 22 | 1.00 | 0.36 | 0.773 [0.57, 0.95] | 0.773 | 0.000 | 0.000 | 4 / 5 / 8 |
| 4BI | rtv_bench/Action-PU/HISTORY | 10 | 1.00 | 0.35 | 0.600 [0.30, 0.90] | 0.600 | 0.000 | 0.000 | 5 / 7 / 9 |
| 4BI | rtv_bench/Action-PU/RECENT | 10 | 1.00 | 0.35 | 0.900 [0.70, 1.00] | 0.900 | 0.000 | 0.000 | 4 / 7 / 9 |
| 4BI | rtv_bench/Action-SP/HISTORY | 15 | 1.00 | 0.33 | 0.667 [0.41, 0.93] | 0.667 | 0.000 | 0.000 | 5 / 5 / 7 |
| 4BI | rtv_bench/Action-SP/RECENT | 15 | 1.00 | 0.33 | 0.733 [0.50, 0.93] | 0.733 | 0.000 | 0.000 | 5 / 5 / 7 |
| 4BI | rtv_bench/Action-SR/HISTORY | 14 | 1.00 | 0.29 | 0.429 [0.20, 0.69] | 0.429 | 0.000 | 0.000 | 5 / 6 / 6 |
| 4BI | rtv_bench/Action-SR/RECENT | 14 | 1.00 | 0.29 | 0.571 [0.31, 0.85] | 0.571 | 0.000 | 0.000 | 5 / 6 / 6 |
| 4BI | rtv_bench/Action-TP/HISTORY | 11 | 1.00 | 0.30 | 0.364 [0.09, 0.70] | 0.364 | 0.000 | 0.000 | 4 / 9 / 10 |
| 4BI | rtv_bench/Action-TP/RECENT | 11 | 1.00 | 0.30 | 0.636 [0.30, 0.91] | 0.636 | 0.000 | 0.000 | 5 / 9 / 10 |
| 4BI | rtv_bench/Action-VP/HISTORY | 10 | 1.00 | 0.42 | 0.800 [0.58, 1.00] | 0.800 | 0.000 | 0.000 | 6 / 9 / 11 |
| 4BI | rtv_bench/Action-VP/RECENT | 10 | 1.00 | 0.42 | 0.700 [0.44, 1.00] | 0.700 | 0.000 | 0.000 | 6 / 8 / 11 |
| 4BI | rtv_bench/Event-FP/HISTORY | 8 | 1.00 | 0.25 | 0.625 [0.29, 0.88] | 0.625 | 0.000 | 0.000 | 5 / 7 / 8 |
| 4BI | rtv_bench/Event-FP/RECENT | 8 | 1.00 | 0.25 | 0.625 [0.33, 0.88] | 0.625 | 0.000 | 0.000 | 5 / 7 / 8 |
| 4BI | rtv_bench/Event-GU/HISTORY | 16 | 1.00 | 0.27 | 0.438 [0.19, 0.73] | 0.438 | 0.000 | 0.000 | 5 / 5 / 5 |
| 4BI | rtv_bench/Event-GU/RECENT | 16 | 1.00 | 0.27 | 0.188 [0.00, 0.40] | 0.188 | 0.000 | 0.000 | 4 / 5 / 5 |
| 4BI | rtv_bench/Event-IA/HISTORY | 8 | 1.00 | 0.34 | 0.750 [0.38, 1.00] | 0.750 | 0.000 | 0.000 | 5 / 8 / 9 |
| 4BI | rtv_bench/Event-IA/RECENT | 8 | 1.00 | 0.34 | 0.750 [0.38, 1.00] | 0.750 | 0.000 | 0.000 | 5 / 8 / 8 |
| 4BI | rtv_bench/Event-PU/HISTORY | 8 | 1.00 | 0.26 | 0.625 [0.29, 0.90] | 0.625 | 0.000 | 0.000 | 5 / 9 / 10 |
| 4BI | rtv_bench/Event-PU/RECENT | 8 | 1.00 | 0.26 | 0.625 [0.25, 0.91] | 0.625 | 0.000 | 0.000 | 5 / 9 / 10 |
| 4BI | rtv_bench/Event-SP/HISTORY | 7 | 1.00 | 0.29 | 0.286 [0.00, 0.57] | 0.286 | 0.000 | 0.000 | 5 / 7 / 8 |
| 4BI | rtv_bench/Event-SP/RECENT | 7 | 1.00 | 0.29 | 0.714 [0.43, 1.00] | 0.714 | 0.000 | 0.000 | 5 / 7 / 8 |
| 4BI | rtv_bench/Event-SR/HISTORY | 14 | 1.00 | 0.26 | 0.643 [0.33, 0.88] | 0.643 | 0.000 | 0.000 | 5 / 5 / 8 |
| 4BI | rtv_bench/Event-SR/RECENT | 14 | 1.00 | 0.26 | 0.643 [0.38, 0.87] | 0.643 | 0.000 | 0.000 | 5 / 5 / 6 |
| 4BI | rtv_bench/Event-TP/HISTORY | 7 | 1.00 | 0.37 | 0.714 [0.43, 1.00] | 0.714 | 0.000 | 0.000 | 5 / 7 / 8 |
| 4BI | rtv_bench/Event-TP/RECENT | 7 | 1.00 | 0.37 | 0.714 [0.29, 1.00] | 0.714 | 0.000 | 0.000 | 4 / 6 / 8 |
| 4BI | rtv_bench/Event-VP/HISTORY | 30 | 1.00 | 0.33 | 0.600 [0.44, 0.76] | 0.600 | 0.000 | 0.000 | 6 / 8 / 13 |
| 4BI | rtv_bench/Event-VP/RECENT | 30 | 1.00 | 0.33 | 0.667 [0.50, 0.82] | 0.667 | 0.000 | 0.000 | 6 / 7 / 9 |
| 4BI | rtv_bench/Object-FP/HISTORY | 6 | 1.00 | 0.35 | 1.000 [1.00, 1.00] | 1.000 | 0.000 | 0.000 | 4 / 6 / 6 |
| 4BI | rtv_bench/Object-FP/RECENT | 6 | 1.00 | 0.35 | 1.000 [1.00, 1.00] | 1.000 | 0.000 | 0.000 | 4 / 6 / 6 |
| 4BI | rtv_bench/Object-GU/HISTORY | 9 | 1.00 | 0.25 | 0.556 [0.22, 0.89] | 0.556 | 0.000 | 0.000 | 4 / 5 / 6 |
| 4BI | rtv_bench/Object-GU/RECENT | 9 | 1.00 | 0.25 | 0.556 [0.22, 0.89] | 0.556 | 0.000 | 0.000 | 4 / 5 / 6 |
| 4BI | rtv_bench/Object-IA/HISTORY | 5 | 1.00 | 0.27 | 0.200 [0.00, 0.60] | 0.200 | 0.000 | 0.000 | 4 / 5 / 5 |
| 4BI | rtv_bench/Object-IA/RECENT | 5 | 1.00 | 0.27 | 0.400 [0.00, 0.80] | 0.400 | 0.000 | 0.000 | 4 / 5 / 5 |
| 4BI | rtv_bench/Object-PU/HISTORY | 18 | 1.00 | 0.25 | 0.556 [0.33, 0.78] | 0.556 | 0.000 | 0.000 | 5 / 7 / 9 |
| 4BI | rtv_bench/Object-PU/RECENT | 18 | 1.00 | 0.25 | 0.667 [0.44, 0.86] | 0.667 | 0.000 | 0.000 | 5 / 7 / 9 |
| 4BI | rtv_bench/Object-SP/HISTORY | 13 | 1.00 | 0.27 | 0.923 [0.80, 1.00] | 0.923 | 0.000 | 0.000 | 4 / 6 / 7 |
| 4BI | rtv_bench/Object-SP/RECENT | 13 | 1.00 | 0.27 | 1.000 [1.00, 1.00] | 1.000 | 0.000 | 0.000 | 4 / 6 / 7 |
| 4BI | rtv_bench/Object-SR/HISTORY | 11 | 1.00 | 0.25 | 0.455 [0.25, 0.62] | 0.455 | 0.000 | 0.000 | 5 / 6 / 7 |
| 4BI | rtv_bench/Object-SR/RECENT | 11 | 1.00 | 0.25 | 0.545 [0.29, 0.80] | 0.545 | 0.000 | 0.000 | 5 / 6 / 7 |
| 4BI | rtv_bench/Object-TP/HISTORY | 19 | 1.00 | 0.26 | 0.684 [0.45, 0.89] | 0.684 | 0.000 | 0.000 | 4 / 6 / 7 |
| 4BI | rtv_bench/Object-TP/RECENT | 19 | 1.00 | 0.26 | 0.737 [0.52, 0.94] | 0.737 | 0.000 | 0.000 | 5 / 7 / 9 |
| 4BI | rtv_bench/Object-VP/HISTORY | 9 | 1.00 | 0.26 | 0.778 [0.55, 1.00] | 0.778 | 0.000 | 0.000 | 5 / 5 / 7 |
| 4BI | rtv_bench/Object-VP/RECENT | 9 | 1.00 | 0.26 | 0.778 [0.55, 1.00] | 0.778 | 0.000 | 0.000 | 5 / 5 / 7 |
| 32BI | ovo_bench/ACR/HISTORY | 109 | 1.00 | 0.25 | 0.706 [0.61, 0.80] | 0.706 | 0.009 | 0.009 | 10 / 14 / 64 |
| 32BI | ovo_bench/ACR/RECENT | 109 | 1.00 | 0.25 | 0.890 [0.83, 0.95] | 0.890 | 0.009 | 0.009 | 8 / 12 / 64 |
| 32BI | ovo_bench/ASI/HISTORY | 148 | 1.00 | 0.25 | 0.709 [0.64, 0.78] | 0.709 | 0.000 | 0.000 | 6 / 12 / 22 |
| 32BI | ovo_bench/ASI/RECENT | 148 | 1.00 | 0.25 | 0.622 [0.54, 0.70] | 0.622 | 0.007 | 0.007 | 2 / 8 / 64 |
| 32BI | ovo_bench/ATR/HISTORY | 116 | 1.00 | 0.25 | 0.862 [0.78, 0.93] | 0.853 | 0.000 | 0.000 | 6 / 11 / 16 |
| 32BI | ovo_bench/ATR/RECENT | 116 | 1.00 | 0.25 | 0.897 [0.84, 0.95] | 0.888 | 0.000 | 0.009 | 2 / 8 / 16 |
| 32BI | ovo_bench/CRR/HISTORY | 240 | 1.00 | 0.50 | 0.537 [0.48, 0.61] | 0.537 | 0.000 | 0.000 | 2 / 2 / 2 |
| 32BI | ovo_bench/CRR/RECENT | 240 | 1.00 | 0.50 | 0.396 [0.37, 0.42] | 0.396 | 0.000 | 0.000 | 2 / 2 / 2 |
| 32BI | ovo_bench/EPM/HISTORY | 297 | 1.00 | 0.27 | 0.677 [0.62, 0.74] | 0.643 | 0.000 | 0.044 | 6 / 10 / 15 |
| 32BI | ovo_bench/EPM/RECENT | 297 | 1.00 | 0.27 | 0.562 [0.51, 0.61] | 0.549 | 0.003 | 0.027 | 4 / 7 / 64 |
| 32BI | ovo_bench/FPD/HISTORY | 101 | 1.00 | 0.25 | 0.772 [0.69, 0.85] | 0.772 | 0.000 | 0.010 | 12 / 15 / 40 |
| 32BI | ovo_bench/FPD/RECENT | 101 | 1.00 | 0.25 | 0.772 [0.68, 0.85] | 0.772 | 0.000 | 0.010 | 2 / 14 / 41 |
| 32BI | ovo_bench/HLD/HISTORY | 186 | 1.00 | 0.28 | 0.527 [0.45, 0.61] | 0.522 | 0.000 | 0.022 | 6 / 7 / 11 |
| 32BI | ovo_bench/HLD/RECENT | 186 | 1.00 | 0.28 | 0.715 [0.65, 0.79] | 0.710 | 0.000 | 0.011 | 2 / 6 / 11 |
| 32BI | ovo_bench/OCR/HISTORY | 149 | 1.00 | 0.25 | 0.826 [0.76, 0.89] | 0.805 | 0.000 | 0.013 | 2 / 9 / 21 |
| 32BI | ovo_bench/OCR/RECENT | 149 | 1.00 | 0.25 | 0.966 [0.93, 0.99] | 0.960 | 0.007 | 0.000 | 2 / 7 / 64 |
| 32BI | ovo_bench/OJR/HISTORY | 184 | 1.00 | 0.25 | 0.761 [0.69, 0.83] | 0.565 | 0.000 | 0.223 | 6 / 11 / 18 |
| 32BI | ovo_bench/OJR/RECENT | 184 | 1.00 | 0.25 | 0.870 [0.81, 0.92] | 0.674 | 0.005 | 0.212 | 6 / 9 / 64 |
| 32BI | ovo_bench/REC/HISTORY | 698 | 1.00 | — | 0.421 [0.36, 0.49] | 0.421 | 0.000 | 0.000 | 2 / 2 / 3 |
| 32BI | ovo_bench/REC/RECENT | 698 | 1.00 | — | 0.170 [0.14, 0.21] | 0.170 | 0.000 | 0.000 | 2 / 2 / 3 |
| 32BI | ovo_bench/SSR/HISTORY | 629 | 1.00 | 0.50 | 0.709 [0.67, 0.75] | 0.709 | 0.000 | 0.000 | 2 / 2 / 2 |
| 32BI | ovo_bench/SSR/RECENT | 629 | 1.00 | 0.50 | 0.685 [0.64, 0.74] | 0.685 | 0.000 | 0.000 | 2 / 2 / 2 |
| 32BI | ovo_bench/STU/HISTORY | 178 | 1.00 | 0.25 | 0.657 [0.58, 0.73] | 0.618 | 0.000 | 0.034 | 8 / 16 / 31 |
| 32BI | ovo_bench/STU/RECENT | 178 | 1.00 | 0.25 | 0.742 [0.65, 0.83] | 0.713 | 0.006 | 0.022 | 2 / 14 / 64 |
| 32BI | rtv_bench/Action-FP/HISTORY | 365 | 1.00 | 0.35 | 0.633 [0.59, 0.68] | 0.633 | 0.000 | 0.000 | 2 / 6 / 13 |
| 32BI | rtv_bench/Action-FP/RECENT | 365 | 1.00 | 0.35 | 0.710 [0.66, 0.76] | 0.710 | 0.000 | 0.000 | 2 / 5 / 14 |
| 32BI | rtv_bench/Action-GU/HISTORY | 92 | 1.00 | 0.28 | 0.565 [0.48, 0.64] | 0.565 | 0.000 | 0.000 | 2 / 5 / 10 |
| 32BI | rtv_bench/Action-GU/RECENT | 92 | 1.00 | 0.28 | 0.685 [0.59, 0.79] | 0.685 | 0.000 | 0.000 | 2 / 5 / 11 |
| 32BI | rtv_bench/Action-IA/HISTORY | 339 | 1.00 | 0.34 | 0.640 [0.59, 0.69] | 0.637 | 0.000 | 0.003 | 2 / 6 / 11 |
| 32BI | rtv_bench/Action-IA/RECENT | 339 | 1.00 | 0.34 | 0.735 [0.69, 0.78] | 0.735 | 0.003 | 0.003 | 2 / 5 / 64 |
| 32BI | rtv_bench/Action-PU/HISTORY | 148 | 1.00 | 0.36 | 0.628 [0.57, 0.69] | 0.628 | 0.000 | 0.000 | 2 / 5 / 12 |
| 32BI | rtv_bench/Action-PU/RECENT | 148 | 1.00 | 0.36 | 0.770 [0.72, 0.82] | 0.770 | 0.000 | 0.000 | 2 / 5 / 12 |
| 32BI | rtv_bench/Action-SP/HISTORY | 225 | 1.00 | 0.33 | 0.516 [0.47, 0.56] | 0.516 | 0.000 | 0.000 | 2 / 5 / 10 |
| 32BI | rtv_bench/Action-SP/RECENT | 225 | 1.00 | 0.33 | 0.613 [0.55, 0.67] | 0.613 | 0.004 | 0.004 | 2 / 5 / 64 |
| 32BI | rtv_bench/Action-SR/HISTORY | 213 | 1.00 | 0.29 | 0.404 [0.34, 0.46] | 0.404 | 0.000 | 0.000 | 2 / 6 / 6 |
| 32BI | rtv_bench/Action-SR/RECENT | 213 | 1.00 | 0.29 | 0.526 [0.47, 0.59] | 0.526 | 0.000 | 0.000 | 2 / 5 / 6 |
| 32BI | rtv_bench/Action-TP/HISTORY | 170 | 1.00 | 0.32 | 0.435 [0.35, 0.52] | 0.435 | 0.000 | 0.000 | 2 / 9 / 10 |
| 32BI | rtv_bench/Action-TP/RECENT | 170 | 1.00 | 0.32 | 0.659 [0.59, 0.73] | 0.659 | 0.000 | 0.000 | 2 / 7 / 10 |
| 32BI | rtv_bench/Action-VP/HISTORY | 140 | 1.00 | 0.34 | 0.557 [0.48, 0.63] | 0.557 | 0.000 | 0.000 | 2 / 6 / 11 |
| 32BI | rtv_bench/Action-VP/RECENT | 140 | 1.00 | 0.34 | 0.700 [0.62, 0.78] | 0.700 | 0.000 | 0.000 | 2 / 5 / 11 |
| 32BI | rtv_bench/Event-FP/HISTORY | 119 | 1.00 | 0.30 | 0.630 [0.57, 0.69] | 0.630 | 0.000 | 0.000 | 4 / 6 / 10 |
| 32BI | rtv_bench/Event-FP/RECENT | 119 | 1.00 | 0.30 | 0.639 [0.56, 0.72] | 0.639 | 0.000 | 0.000 | 2 / 6 / 10 |
| 32BI | rtv_bench/Event-GU/HISTORY | 247 | 1.00 | 0.27 | 0.543 [0.49, 0.60] | 0.543 | 0.000 | 0.000 | 4 / 5 / 13 |
| 32BI | rtv_bench/Event-GU/RECENT | 247 | 1.00 | 0.27 | 0.534 [0.48, 0.59] | 0.534 | 0.000 | 0.000 | 2 / 5 / 9 |
| 32BI | rtv_bench/Event-IA/HISTORY | 126 | 1.00 | 0.34 | 0.627 [0.55, 0.72] | 0.627 | 0.000 | 0.000 | 2 / 8 / 12 |
| 32BI | rtv_bench/Event-IA/RECENT | 126 | 1.00 | 0.34 | 0.746 [0.66, 0.83] | 0.746 | 0.008 | 0.000 | 2 / 7 / 64 |
| 32BI | rtv_bench/Event-PU/HISTORY | 127 | 1.00 | 0.28 | 0.606 [0.54, 0.67] | 0.598 | 0.000 | 0.016 | 4 / 8 / 11 |
| 32BI | rtv_bench/Event-PU/RECENT | 127 | 1.00 | 0.28 | 0.669 [0.61, 0.72] | 0.669 | 0.000 | 0.008 | 2 / 7 / 11 |
| 32BI | rtv_bench/Event-SP/HISTORY | 112 | 1.00 | 0.28 | 0.598 [0.50, 0.70] | 0.598 | 0.000 | 0.000 | 4 / 8 / 12 |
| 32BI | rtv_bench/Event-SP/RECENT | 112 | 1.00 | 0.28 | 0.723 [0.64, 0.81] | 0.723 | 0.000 | 0.000 | 2 / 8 / 12 |
| 32BI | rtv_bench/Event-SR/HISTORY | 214 | 1.00 | 0.27 | 0.593 [0.53, 0.65] | 0.593 | 0.000 | 0.000 | 2 / 5 / 11 |
| 32BI | rtv_bench/Event-SR/RECENT | 214 | 1.00 | 0.27 | 0.650 [0.59, 0.71] | 0.645 | 0.009 | 0.009 | 2 / 5 / 64 |
| 32BI | rtv_bench/Event-TP/HISTORY | 114 | 1.00 | 0.29 | 0.605 [0.51, 0.71] | 0.605 | 0.000 | 0.000 | 4 / 6 / 15 |
| 32BI | rtv_bench/Event-TP/RECENT | 114 | 1.00 | 0.29 | 0.763 [0.67, 0.84] | 0.763 | 0.000 | 0.000 | 2 / 6 / 13 |
| 32BI | rtv_bench/Event-VP/HISTORY | 458 | 1.00 | 0.33 | 0.611 [0.56, 0.66] | 0.611 | 0.000 | 0.000 | 2 / 6 / 13 |
| 32BI | rtv_bench/Event-VP/RECENT | 458 | 1.00 | 0.33 | 0.712 [0.67, 0.76] | 0.712 | 0.000 | 0.000 | 2 / 5 / 13 |
| 32BI | rtv_bench/Object-FP/HISTORY | 102 | 1.00 | 0.35 | 0.696 [0.61, 0.79] | 0.696 | 0.000 | 0.000 | 2 / 5 / 9 |
| 32BI | rtv_bench/Object-FP/RECENT | 102 | 1.00 | 0.35 | 0.735 [0.67, 0.80] | 0.735 | 0.000 | 0.000 | 2 / 4 / 9 |
| 32BI | rtv_bench/Object-GU/HISTORY | 135 | 1.00 | 0.25 | 0.622 [0.56, 0.70] | 0.622 | 0.000 | 0.000 | 5 / 7 / 15 |
| 32BI | rtv_bench/Object-GU/RECENT | 135 | 1.00 | 0.25 | 0.556 [0.49, 0.62] | 0.556 | 0.000 | 0.000 | 2 / 7 / 12 |
| 32BI | rtv_bench/Object-IA/HISTORY | 87 | 1.00 | 0.28 | 0.540 [0.45, 0.63] | 0.540 | 0.034 | 0.034 | 2 / 6 / 64 |
| 32BI | rtv_bench/Object-IA/RECENT | 87 | 1.00 | 0.28 | 0.655 [0.59, 0.72] | 0.655 | 0.011 | 0.011 | 2 / 6 / 64 |
| 32BI | rtv_bench/Object-PU/HISTORY | 270 | 1.00 | 0.26 | 0.693 [0.65, 0.74] | 0.693 | 0.000 | 0.000 | 2 / 6 / 12 |
| 32BI | rtv_bench/Object-PU/RECENT | 270 | 1.00 | 0.26 | 0.763 [0.71, 0.81] | 0.759 | 0.011 | 0.011 | 2 / 6 / 64 |
| 32BI | rtv_bench/Object-SP/HISTORY | 200 | 1.00 | 0.29 | 0.725 [0.67, 0.78] | 0.725 | 0.000 | 0.000 | 2 / 5 / 6 |
| 32BI | rtv_bench/Object-SP/RECENT | 200 | 1.00 | 0.29 | 0.780 [0.73, 0.84] | 0.775 | 0.000 | 0.005 | 2 / 5 / 9 |
| 32BI | rtv_bench/Object-SR/HISTORY | 161 | 1.00 | 0.26 | 0.553 [0.49, 0.62] | 0.553 | 0.000 | 0.000 | 4 / 7 / 19 |
| 32BI | rtv_bench/Object-SR/RECENT | 161 | 1.00 | 0.26 | 0.634 [0.57, 0.70] | 0.634 | 0.000 | 0.000 | 2 / 6 / 19 |
| 32BI | rtv_bench/Object-TP/HISTORY | 303 | 1.00 | 0.28 | 0.667 [0.62, 0.72] | 0.663 | 0.000 | 0.010 | 4 / 6 / 11 |
| 32BI | rtv_bench/Object-TP/RECENT | 303 | 1.00 | 0.28 | 0.759 [0.71, 0.81] | 0.756 | 0.000 | 0.003 | 2 / 6 / 11 |
| 32BI | rtv_bench/Object-VP/HISTORY | 141 | 1.00 | 0.28 | 0.603 [0.52, 0.69] | 0.596 | 0.000 | 0.021 | 4 / 6 / 12 |
| 32BI | rtv_bench/Object-VP/RECENT | 141 | 1.00 | 0.28 | 0.709 [0.63, 0.79] | 0.702 | 0.000 | 0.014 | 2 / 6 / 16 |
| 32BT | ovo_bench/ACR/HISTORY | 74 | 0.68 | 0.25 | 0.689 [0.56, 0.80] | 0.689 | 0.000 | 0.000 | 113 / 386 / 2055 |
| 32BT | ovo_bench/ACR/RECENT | 74 | 0.68 | 0.25 | 0.878 [0.81, 0.94] | 0.878 | 0.000 | 0.000 | 122 / 288 / 3514 |
| 32BT | ovo_bench/ASI/HISTORY | 101 | 0.68 | 0.25 | 0.832 [0.75, 0.90] | 0.832 | 0.000 | 0.000 | 155 / 546 / 1927 |
| 32BT | ovo_bench/ASI/RECENT | 101 | 0.68 | 0.25 | 0.713 [0.62, 0.80] | 0.713 | 0.000 | 0.000 | 236 / 854 / 3440 |
| 32BT | ovo_bench/ATR/HISTORY | 80 | 0.69 | 0.25 | 0.762 [0.65, 0.87] | 0.762 | 0.000 | 0.000 | 78 / 201 / 370 |
| 32BT | ovo_bench/ATR/RECENT | 80 | 0.69 | 0.25 | 0.900 [0.83, 0.96] | 0.900 | 0.000 | 0.000 | 81 / 214 / 453 |
| 32BT | ovo_bench/CRR/HISTORY | 153 | 0.64 | 0.50 | 0.562 [0.48, 0.69] | 0.562 | 0.000 | 0.000 | 171 / 477 / 2134 |
| 32BT | ovo_bench/CRR/RECENT | 153 | 0.64 | 0.50 | 0.425 [0.37, 0.50] | 0.425 | 0.000 | 0.000 | 137 / 615 / 1879 |
| 32BT | ovo_bench/EPM/HISTORY | 203 | 0.68 | 0.28 | 0.626 [0.55, 0.70] | 0.626 | 0.005 | 0.005 | 90 / 279 / 16384 |
| 32BT | ovo_bench/EPM/RECENT | 203 | 0.68 | 0.28 | 0.631 [0.56, 0.70] | 0.631 | 0.000 | 0.000 | 107 / 446 / 1659 |
| 32BT | ovo_bench/FPD/HISTORY | 69 | 0.68 | 0.25 | 0.754 [0.64, 0.87] | 0.754 | 0.000 | 0.000 | 119 / 459 / 893 |
| 32BT | ovo_bench/FPD/RECENT | 69 | 0.68 | 0.25 | 0.710 [0.59, 0.83] | 0.710 | 0.000 | 0.000 | 138 / 311 / 1259 |
| 32BT | ovo_bench/HLD/HISTORY | 126 | 0.68 | 0.28 | 0.500 [0.41, 0.59] | 0.500 | 0.000 | 0.000 | 154 / 444 / 1611 |
| 32BT | ovo_bench/HLD/RECENT | 126 | 0.68 | 0.28 | 0.667 [0.57, 0.76] | 0.667 | 0.000 | 0.000 | 160 / 416 / 2019 |
| 32BT | ovo_bench/OCR/HISTORY | 101 | 0.68 | 0.25 | 0.832 [0.74, 0.91] | 0.832 | 0.000 | 0.000 | 68 / 198 / 2616 |
| 32BT | ovo_bench/OCR/RECENT | 101 | 0.68 | 0.25 | 0.960 [0.92, 0.99] | 0.960 | 0.000 | 0.000 | 76 / 204 / 3450 |
| 32BT | ovo_bench/OJR/HISTORY | 125 | 0.68 | 0.25 | 0.728 [0.63, 0.81] | 0.720 | 0.000 | 0.008 | 76 / 281 / 4449 |
| 32BT | ovo_bench/OJR/RECENT | 125 | 0.68 | 0.25 | 0.840 [0.77, 0.90] | 0.832 | 0.000 | 0.008 | 82 / 217 / 3973 |
| 32BT | ovo_bench/REC/HISTORY | 446 | 0.64 | — | 0.469 [0.39, 0.56] | 0.469 | 0.002 | 0.002 | 876 / 4094 / 16384 |
| 32BT | ovo_bench/REC/RECENT | 446 | 0.64 | — | 0.211 [0.17, 0.26] | 0.211 | 0.000 | 0.000 | 416 / 1718 / 4802 |
| 32BT | ovo_bench/SSR/HISTORY | 401 | 0.64 | 0.50 | 0.748 [0.70, 0.79] | 0.748 | 0.000 | 0.000 | 112 / 536 / 2416 |
| 32BT | ovo_bench/SSR/RECENT | 401 | 0.64 | 0.50 | 0.738 [0.69, 0.79] | 0.738 | 0.000 | 0.000 | 96 / 326 / 1448 |
| 32BT | ovo_bench/STU/HISTORY | 121 | 0.68 | 0.25 | 0.579 [0.48, 0.69] | 0.579 | 0.000 | 0.000 | 144 / 408 / 2065 |
| 32BT | ovo_bench/STU/RECENT | 121 | 0.68 | 0.25 | 0.736 [0.63, 0.83] | 0.736 | 0.000 | 0.000 | 129 / 451 / 3115 |
| 32BT | rtv_bench/Action-FP/HISTORY | 65 | 0.18 | 0.35 | 0.662 [0.57, 0.76] | 0.662 | 0.000 | 0.000 | 125 / 301 / 672 |
| 32BT | rtv_bench/Action-FP/RECENT | 79 | 0.22 | 0.34 | 0.734 [0.65, 0.82] | 0.734 | 0.000 | 0.000 | 140 / 494 / 2306 |
| 32BT | rtv_bench/Action-GU/HISTORY | 17 | 0.18 | 0.25 | 0.471 [0.24, 0.71] | 0.471 | 0.000 | 0.000 | 279 / 957 / 4648 |
| 32BT | rtv_bench/Action-GU/RECENT | 20 | 0.22 | 0.27 | 0.550 [0.32, 0.78] | 0.550 | 0.000 | 0.000 | 184 / 977 / 2633 |
| 32BT | rtv_bench/Action-IA/HISTORY | 61 | 0.18 | 0.34 | 0.689 [0.58, 0.79] | 0.689 | 0.000 | 0.000 | 133 / 485 / 2126 |
| 32BT | rtv_bench/Action-IA/RECENT | 74 | 0.22 | 0.34 | 0.757 [0.66, 0.85] | 0.757 | 0.000 | 0.000 | 174 / 583 / 1462 |
| 32BT | rtv_bench/Action-PU/HISTORY | 27 | 0.18 | 0.34 | 0.667 [0.52, 0.83] | 0.667 | 0.000 | 0.000 | 163 / 448 / 842 |
| 32BT | rtv_bench/Action-PU/RECENT | 32 | 0.22 | 0.35 | 0.906 [0.82, 1.00] | 0.906 | 0.000 | 0.000 | 118 / 465 / 1169 |
| 32BT | rtv_bench/Action-SP/HISTORY | 40 | 0.18 | 0.33 | 0.500 [0.34, 0.65] | 0.500 | 0.000 | 0.000 | 315 / 1183 / 2166 |
| 32BT | rtv_bench/Action-SP/RECENT | 49 | 0.22 | 0.34 | 0.673 [0.56, 0.79] | 0.673 | 0.000 | 0.000 | 200 / 475 / 2203 |
| 32BT | rtv_bench/Action-SR/HISTORY | 37 | 0.17 | 0.29 | 0.486 [0.36, 0.62] | 0.486 | 0.000 | 0.000 | 285 / 603 / 904 |
| 32BT | rtv_bench/Action-SR/RECENT | 46 | 0.22 | 0.29 | 0.522 [0.37, 0.68] | 0.522 | 0.000 | 0.000 | 340 / 845 / 2304 |
| 32BT | rtv_bench/Action-TP/HISTORY | 30 | 0.18 | 0.31 | 0.433 [0.30, 0.58] | 0.433 | 0.000 | 0.000 | 268 / 635 / 872 |
| 32BT | rtv_bench/Action-TP/RECENT | 37 | 0.22 | 0.31 | 0.730 [0.58, 0.86] | 0.730 | 0.000 | 0.000 | 128 / 1235 / 2231 |
| 32BT | rtv_bench/Action-VP/HISTORY | 25 | 0.18 | 0.39 | 0.480 [0.32, 0.64] | 0.480 | 0.000 | 0.000 | 207 / 889 / 1663 |
| 32BT | rtv_bench/Action-VP/RECENT | 30 | 0.21 | 0.36 | 0.600 [0.45, 0.77] | 0.600 | 0.000 | 0.000 | 132 / 624 / 901 |
| 32BT | rtv_bench/Event-FP/HISTORY | 21 | 0.18 | 0.26 | 0.714 [0.50, 0.89] | 0.714 | 0.000 | 0.000 | 220 / 446 / 1484 |
| 32BT | rtv_bench/Event-FP/RECENT | 26 | 0.22 | 0.27 | 0.692 [0.52, 0.86] | 0.692 | 0.000 | 0.000 | 127 / 672 / 2867 |
| 32BT | rtv_bench/Event-GU/HISTORY | 43 | 0.17 | 0.28 | 0.512 [0.37, 0.66] | 0.512 | 0.000 | 0.000 | 480 / 1746 / 7012 |
| 32BT | rtv_bench/Event-GU/RECENT | 54 | 0.22 | 0.28 | 0.444 [0.32, 0.57] | 0.444 | 0.000 | 0.000 | 401 / 1843 / 4478 |
| 32BT | rtv_bench/Event-IA/HISTORY | 22 | 0.17 | 0.32 | 0.591 [0.37, 0.78] | 0.591 | 0.000 | 0.000 | 116 / 362 / 411 |
| 32BT | rtv_bench/Event-IA/RECENT | 27 | 0.21 | 0.32 | 0.778 [0.57, 0.93] | 0.778 | 0.000 | 0.000 | 158 / 852 / 1687 |
| 32BT | rtv_bench/Event-PU/HISTORY | 22 | 0.17 | 0.28 | 0.591 [0.37, 0.77] | 0.591 | 0.000 | 0.000 | 104 / 710 / 1304 |
| 32BT | rtv_bench/Event-PU/RECENT | 27 | 0.21 | 0.28 | 0.593 [0.43, 0.75] | 0.593 | 0.000 | 0.000 | 109 / 560 / 1272 |
| 32BT | rtv_bench/Event-SP/HISTORY | 20 | 0.18 | 0.27 | 0.550 [0.29, 0.82] | 0.550 | 0.000 | 0.000 | 225 / 579 / 4134 |
| 32BT | rtv_bench/Event-SP/RECENT | 24 | 0.21 | 0.27 | 0.708 [0.48, 0.91] | 0.708 | 0.000 | 0.000 | 80 / 355 / 606 |
| 32BT | rtv_bench/Event-SR/HISTORY | 38 | 0.18 | 0.28 | 0.632 [0.51, 0.76] | 0.632 | 0.000 | 0.000 | 206 / 516 / 2315 |
| 32BT | rtv_bench/Event-SR/RECENT | 47 | 0.22 | 0.28 | 0.617 [0.50, 0.73] | 0.617 | 0.000 | 0.000 | 172 / 832 / 6040 |
| 32BT | rtv_bench/Event-TP/HISTORY | 21 | 0.18 | 0.31 | 0.810 [0.63, 0.95] | 0.810 | 0.000 | 0.000 | 80 / 312 / 355 |
| 32BT | rtv_bench/Event-TP/RECENT | 25 | 0.22 | 0.30 | 0.720 [0.53, 0.88] | 0.720 | 0.000 | 0.000 | 105 / 310 / 820 |
| 32BT | rtv_bench/Event-VP/HISTORY | 81 | 0.18 | 0.33 | 0.691 [0.59, 0.78] | 0.691 | 0.000 | 0.000 | 141 / 353 / 2325 |
| 32BT | rtv_bench/Event-VP/RECENT | 100 | 0.22 | 0.33 | 0.690 [0.60, 0.77] | 0.690 | 0.000 | 0.000 | 130 / 433 / 1588 |
| 32BT | rtv_bench/Object-FP/HISTORY | 18 | 0.18 | 0.34 | 0.833 [0.68, 1.00] | 0.833 | 0.000 | 0.000 | 140 / 240 / 313 |
| 32BT | rtv_bench/Object-FP/RECENT | 22 | 0.22 | 0.34 | 0.864 [0.71, 1.00] | 0.864 | 0.000 | 0.000 | 118 / 900 / 1410 |
| 32BT | rtv_bench/Object-GU/HISTORY | 23 | 0.17 | 0.25 | 0.739 [0.59, 0.89] | 0.739 | 0.000 | 0.000 | 160 / 870 / 1015 |
| 32BT | rtv_bench/Object-GU/RECENT | 29 | 0.21 | 0.26 | 0.655 [0.50, 0.80] | 0.655 | 0.000 | 0.000 | 135 / 1377 / 2047 |
| 32BT | rtv_bench/Object-IA/HISTORY | 16 | 0.18 | 0.27 | 0.438 [0.25, 0.64] | 0.438 | 0.000 | 0.000 | 300 / 816 / 1483 |
| 32BT | rtv_bench/Object-IA/RECENT | 19 | 0.22 | 0.27 | 0.474 [0.25, 0.69] | 0.474 | 0.000 | 0.000 | 263 / 988 / 1786 |
| 32BT | rtv_bench/Object-PU/HISTORY | 48 | 0.18 | 0.26 | 0.604 [0.49, 0.72] | 0.604 | 0.000 | 0.000 | 120 / 441 / 1624 |
| 32BT | rtv_bench/Object-PU/RECENT | 58 | 0.21 | 0.25 | 0.793 [0.69, 0.89] | 0.793 | 0.000 | 0.000 | 93 / 325 / 2628 |
| 32BT | rtv_bench/Object-SP/HISTORY | 36 | 0.18 | 0.28 | 0.778 [0.62, 0.91] | 0.750 | 0.000 | 0.028 | 88 / 333 / 2305 |
| 32BT | rtv_bench/Object-SP/RECENT | 43 | 0.21 | 0.28 | 0.884 [0.78, 0.96] | 0.860 | 0.000 | 0.047 | 79 / 350 / 1224 |
| 32BT | rtv_bench/Object-SR/HISTORY | 28 | 0.17 | 0.25 | 0.464 [0.34, 0.60] | 0.464 | 0.000 | 0.000 | 139 / 404 / 2127 |
| 32BT | rtv_bench/Object-SR/RECENT | 35 | 0.22 | 0.25 | 0.571 [0.41, 0.77] | 0.571 | 0.000 | 0.000 | 132 / 895 / 2505 |
| 32BT | rtv_bench/Object-TP/HISTORY | 54 | 0.18 | 0.27 | 0.630 [0.52, 0.76] | 0.630 | 0.000 | 0.019 | 134 / 837 / 2602 |
| 32BT | rtv_bench/Object-TP/RECENT | 66 | 0.22 | 0.27 | 0.742 [0.64, 0.85] | 0.742 | 0.000 | 0.030 | 124 / 494 / 1079 |
| 32BT | rtv_bench/Object-VP/HISTORY | 25 | 0.18 | 0.29 | 0.640 [0.48, 0.80] | 0.640 | 0.000 | 0.040 | 107 / 422 / 1472 |
| 32BT | rtv_bench/Object-VP/RECENT | 31 | 0.22 | 0.28 | 0.742 [0.63, 0.88] | 0.742 | 0.000 | 0.032 | 114 / 653 / 1241 |

## Files
- `results/benchmarks/study_b1_h100/`: `b1_rows_{4BI,32BI,32BT}.jsonl.gz` (one row per request, including the whole Thinking response and Instruct logprobs), `b1_mv_32BI.jsonl.gz`, `b1_run_meta_h100nvl.json`, `b1_results_h100nvl.json`, `frame_selection_check.json`.
- Scripts: `experiments/benchmarks/b1_common.py`, `b1_check_frames.py`, `b1_infer_vllm.py`, `b1_analyse.py`.
