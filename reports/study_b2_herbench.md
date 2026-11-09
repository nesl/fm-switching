# StudyB2-herbench: Qwen3-VL 4B / 8B / 32B, Instruct and Thinking, on HERBench (Lite-v2 first, then the full set)

**E-id:** StudyB2-herbench (pre-registered 2026-11-08 ~06:45, before any HERBench inference; authorised by the user).

**Status:** STOPPED by the user on 2026-11-09 15:27, at an arm boundary, for a CPU-only job.
- **Complete:** Lite-v2 on all six arms. The shard 0 full-set questions (5,354) on 4BI, 8BI, 32BI, 4BT and 8BT.
- **Not run:** 32BT on the shard 0 full set, the latency sample, and shards 1–9.
- **Data state:** shard 1 is prepared (all 17 tar parts verified, 28 videos extracted). The shard 0 and shard 1 videos and the tar parts remain on disk; none were deleted, since their arms are not all finished.

**Purpose:** descriptive per-question rows for the full 6-arm matrix. No policy, threshold or time-shift claim.

## Data (written before inference)
- **Source:** HF `DanBenAmi/HERBench` @ `30b42e97180f2c7c0fdc3f2aed412ae04f0366ca`; code `DanBenAmi/HERBench` @ `fe66f377fd4a4a1689b97837129edbaacd489ebe` (local clone); flash's manifest `results/datasets/download_manifest.json`.
- **Videos come only from the split tar** (`videos/videos.tar.part.00`–`16`), pulled from flash with `fmpull`.
  - Every part must match **HERBench's published `videos.tar.checksums.txt` and the HF LFS sha256 and size** at the pinned commit before use (`experiments/datasets/her_prepare_shard.py`; hashes cached in `results/datasets/her_parts_check_h100.json`).
  - Videos are extracted per shard with `tar --ignore-zeros` (as flash did), and every video is ffprobed against flash's `ffprobe.jsonl`.
- **Annotation sets:**
  - **Lite-v2:** `herbench_annotations_lite_v2.json`, 1,971 questions on 68 videos, all runnable.
  - **Full:** `herbench_annotations.json`, 27,631 questions; 27,566 runnable. 65 questions on one video absent upstream are not runnable (listed; flash's crosscheck shows the same).
  - **Lite-v2 is not a subset of the full set:** 1,429 Lite-v2 question ids also occur in the full set, and only 736 of those are identical (question, choices, answer, video); 542 ids are Lite-v2 only.
  - **Recorded interpretation of "Lite-v2 first, then the remaining full set":** the Lite-v2 questions are run as given. The 736 full-set questions identical to a Lite-v2 question are not run twice; their Lite-v2 rows stand for them (`duplicate_of`). The other 26,830 runnable full-set questions are run.
  - **Annotation check:** the full set equals flash's index on all 27,566 runnable questions (question, options, gold, task, video, `required_timestamps`): **0 mismatches**. Lite-v2 has no flash index; its file is checked against the HF hash (`results/datasets/annotations_check_h100.json`).
- **No query time:** HERBench has none. **t = the video's duration** (first video stream, flash's ffprobe), and the input is **HISTORY only**: 37 frames over [0, t], every frame ≤ t.
  - `required_timestamps` (question metadata, 20,919 full-set questions) is **carried into every row as `item_meta` for offline analysis and never used at runtime**.
- **Shards** (disk: all 17 tar parts, 159 GiB, must stay until the last shard; floor 20 GiB):

  | shard | videos | video GiB | questions to run |
  |---|---|---|---|
  | 0 | the 68 Lite-v2 videos (all in parts 00–03) | 34.3 | 1,971 Lite-v2 + 5,354 full |
  | 1–9 | the remaining 266 videos in seed-0 random order, ≤ 16 GiB each | 1.5–15.9 each | 2,449 / 2,549 / 3,443 / 2,102 / 2,332 / 3,062 / 2,332 / 2,989 / 218 |

  - Shard 0 runs Lite-v2 first, all six arms, then the shard's full-set questions, all six arms.
  - Each later shard: extract → six arms → delete that shard's videos. The tar parts are deleted after the last shard.
- **Order:** seed-0 random order stratified by task (b1_common's algorithm) within each set and shard, in batches of 200, so any stopping point is a valid sample.
- **Grey control:** the first 100 questions of the full set's fixed order, HISTORY, per arm (run with shard 0).

## Matrix and controls (written before inference)
- **Arms, decoding, stack and input pipeline:** exactly as StudyB2-ovo-rtv and StudyB2-streamingbench.
  - 4BI / 8BI / 32BI greedy 64 with logprobs; 4BT / 8BT / 32BT card VL sampling, 16,384 tokens, seed 0.
  - `b1_common.py` unchanged (SHA verified); 768 × 432 PNG; StudyB1's fixed template (5 lettered options A–E; 13 questions have 4).
- **Upstream scorer:** `evaluation/model_wrappers/base_vlm.py` `extract_answer_choice`, ported verbatim (`b2_her.py`; 'ERROR' / no match = wrong). Thinking is scored after `</think>`.
- **Strict scorer:** exactly one standalone option letter. Truncated, empty and unparsed responses are reported separately.
- **Online checks:**
  - frame SHA-256 lists vs this dataset's 4BI rows (mismatch → HALT);
  - smoke runs (every arm);
  - Step 4 repeat control: 4BI, 30 pairs, < 99 % → HALT.
- **Latency sample (deviation recorded 2026-11-08 07:30, before any HERBench latency request):** StudyD10's method, 50 per arm (HISTORY).
  - It runs **after shard 0's matrix** (Lite-v2 and shard 0 full, all six arms), not after the whole HERBench matrix, on **the first 50 full-set questions of the fixed order whose videos are in shard 0**.
  - **Reason (disk):** the first 50 of the full order use 45 videos (24.2 GiB) spread over all 10 shards. With the 17 tar parts (159 GiB) on disk until the last shard, keeping or re-extracting them at the end would cross the 20 GiB floor.
  - Isolation and method are unchanged.
- **Stop rules:** as before.
  - A frame that cannot be decoded is recorded as a failed request (`RenderError`), never dropped.
  - Another user on GPU 2 (observed 2026-11-08 01:19–02:06) stops the queue, which resumes automatically when the GPU is free.

## Mechanism verification (Steps 1, 2 and 5 before inference; Steps 3 and 4 from smoke and repeat control before the sweep)
**Step 1: causal chain.** As in StudyB2-ovo-rtv:
- On identical input, size and mode change per-question correctness (FORMULATION.md §Regime uncertainty / §Decisions).
- Identical frames and prompt → arms differ in weights or mode and decoding → answers differ → scored differently.

**Step 2: instantiate each link** (filled from the rows).

| causal link | implementing quantity | value / range in this run | varies as expected? | evidence |
|---|---|---|---|---|
| identical input across arms | frame SHA-256 vs 4BI; prompt tokens | to be filled | CONSTANT (+2 Thinking) | online check + analysis |
| arm differs | revision / decoding | 6 arms | by construction | run meta |
| reasoning mode active | Thinking completion tokens; `</think>` closed | to be filled | > 0, varies | rows |
| answer differs | per-question disagreement | to be filled | > repeat control | rows |
| correctness differs | matched difference, both scorers | to be filled | — | analysis |

**Step 3: trace one request per arm** (`b2_smoke_<arm>.jsonl.gz`, 2026-11-08 06:28–06:38, before any sweep).

The request: Lite-v2 `AC_6266` (Action Counting), video `HD_EPIC/P01/P01-20240204-152537.mp4`, t = duration 445.8 s, HISTORY. "How many times does the action-object pair 'brush strainer' occur in this video?", A. 2 / B. 3 / C. 4 / D. 5 / E. 1, gold E. `required_timestamps` ['2:15:240'] is in the row, not in the prompt.
- **Frames:** 37 targets over [0, 445.8]; pts 0.00, 12.37, 24.77, 37.13 … 445.77; 37 distinct; all ≤ t.
  - SHA-256 `dae2d4810c40db60…`, …
  - **Identical in all six arms; 8 / 8 smoke requests per arm equal 4BI's frames.**

| arm | prompt / completion tokens | finish | response (answer region) | upstream | strict |
|---|---|---|---|---|---|
| 4BI | 12,591 / 5 | stop | "E. 1" | correct | E |
| 8BI | 12,591 / 2 | stop | "E" | correct | E |
| 32BI | 12,591 / 5 | stop | "E. 1" | correct | E |
| 4BT | 12,593 / 1,745 | stop, `</think>` closed | "…So three times … So option B.3.\n</think>\n\nB" → "B" | wrong | B |
| 8BT | 12,593 / 438 | stop, `</think>` closed | "…maybe the action occurs twice … the answer is A.\n</think>\n\nA" → "A" | wrong | A |
| 32BT | 12,593 / 1,799 | stop, `</think>` closed | "…So total 2 times. Hence, answer A.\n</think>\n\nA" → "A" | wrong | A |

- **All 8 smoke requests per arm** (3 Lite-v2 + 3 full + 2 grey, HISTORY) completed with finish `stop` and 0 errors.
- **Prompt tokens:** 12,588–12,806 (Instruct); +2 Thinking.
- **Thinking completion tokens:** 83–5,374. `</think>` closed on every smoke request.
- On this counting question the Thinking arms count occurrences across the 37 frames and disagree with the Instruct arms. This is the per-question disagreement the study records.

**Step 4: negative control.**
- 4BI twice on identical input: the first 30 Lite-v2 questions of the fixed order, HISTORY (`b2_mv_4BI.jsonl.gz`, `b2_repeat_control_mv_4BI.json`, 06:40, before the sweep).
- **30 / 30 identical answers, texts, correctness and frame lists. PASS** (gate 99 %).

**Step 5: alternative explanations.**
- **Format compliance:** a size or mode difference could come from answer format rather than capability. HERBench's extractor accepts many formats but returns 'ERROR' for any response containing "ERROR". Distinguishing data: unparsed, ambiguous and parsed-only accuracy, and both scorers.
- **Sparse sampling:** HERBench videos are long (up to 75 min; median 3 min) and many questions need several distant moments (`required_timestamps`). 37 frames may miss them, so low accuracy can reflect the input's sampling rather than capability. `required_timestamps` lets this be checked offline.
- **Confounded by design:** mode and decoding, as before. Thinking uses seed 0 only.

## Lite-v2 results (written 2026-11-08 ~22:00, after all six arms on Lite-v2; observations only, interpretation at the end of the study)
- **Runs** (shard 0, Lite-v2 part, 2,071 requests per arm = 1,971 questions + 100 grey, HISTORY):
  - 4BI 06:40–06:59, 8BI → 07:27, 32BI → 09:01, 4BT → 11:20, 8BT → 13:40, 32BT → 21:31.
  - 0 errors, 0 still failed, no GPU contention.
- **Frame identity:** online check vs 4BI 2,071 / 2,071 per arm; analysis 0 mismatches over 15 arm pairs. Prompt tokens equal within a mode, +2 Thinking.
- **Accuracy** (upstream `extract_answer_choice` [video-bootstrap 95 % CI, 68 videos]; strict; floor 0.20):

  | arm | upstream | strict | truncated | no answer region | ambiguous (strict) | completion tokens p50 / p90 / max |
  |---|---|---|---|---|---|---|
  | 4BI | 0.537 [0.504, 0.571] | 0.525 | 0 | — | 24 | 4 / 16 / 55 |
  | 8BI | 0.538 [0.509, 0.571] | 0.538 | 0 | — | 0 | 2 / 2 / 62 |
  | 32BI | 0.550 [0.516, 0.583] | 0.538 | 0 | — | 25 | 5 / 13 / 33 |
  | 4BT | 0.474 [0.445, 0.504] | 0.474 | 6 | 6 | 0 | 1,382 / 5,763 / 16,384 |
  | 8BT | 0.489 [0.459, 0.520] | 0.489 | 2 | 2 | 0 | 1,271 / 4,082 / 16,384 |
  | 32BT | 0.509 [0.482, 0.537] | 0.509 | 17 | 17 | 0 | 776 / 3,252 / 16,384 |

- **Paired (matched questions; upstream [CI] / strict):**
  - **32B − 4B:** Instruct +0.013 [−0.008, +0.034] / +0.013; Thinking +0.035 [+0.016, +0.055] / +0.035.
  - **32B − 8B:** Instruct +0.012 [−0.008, +0.031] / −0.001; Thinking +0.020 [−0.001, +0.040] / +0.020.
  - **8B − 4B:** Instruct +0.002 / +0.013; Thinking +0.015, both CIs including 0.
  - **Thinking − Instruct:** 4B −0.063 [−0.086, −0.040] / −0.051; 8B −0.049 [−0.071, −0.030] / −0.049; 32B −0.041 [−0.058, −0.026] / −0.029. **Negative at every size under both scorers.**
  - **Per-question correctness disagreement:** 16–26 % (repeat control 0 / 30).
- **Grey (the first 100 full-set questions, grey pixels; floor 0.20):**
  - 4BI 0.21, 8BI 0.21, 32BI 0.20, 4BT 0.29, 8BT 0.22, 32BT 0.23.
  - Answers spread over A–E. 4BT leans to E (36 / 100).
- **Thinking reasoning length:** median 776–1,382 tokens, 4–9× its length on OVO / RTV / StreamingBench. The 25 truncations at 16,384 are all Thinking (0.1–0.9 % per arm) and are counted wrong.
- **Per task** (upstream accuracy; n per task 32–328):

| task (Lite-v2, HISTORY) | n | floor | 4BI | 8BI | 32BI | 4BT | 8BT | 32BT |
|---|---|---|---|---|---|---|---|---|
| Action Counting | 144 | 0.20 | 0.750 | 0.792 | 0.806 | 0.514 | 0.569 | 0.674 |
| Action Sequence Integrity Identification | 154 | 0.20 | 0.656 | 0.747 | 0.708 | 0.591 | 0.669 | 0.565 |
| Appearance-Grounded Attribute Recognition | 32 | 0.20 | 0.906 | 0.844 | 0.938 | 0.844 | 0.844 | 0.875 |
| Appearance-Grounded Behavior & Interactions | 87 | 0.20 | 0.920 | 0.943 | 0.954 | 0.943 | 0.954 | 0.943 |
| Appearance-Grounded Localization & Trajectory | 182 | 0.20 | 0.797 | 0.808 | 0.819 | 0.764 | 0.769 | 0.758 |
| False Action Memory | 158 | 0.20 | 0.652 | 0.633 | 0.608 | 0.589 | 0.614 | 0.589 |
| False Object Memory | 159 | 0.20 | 0.635 | 0.566 | 0.591 | 0.591 | 0.610 | 0.579 |
| Multi-Entities Grounding and Localization | 231 | 0.20 | 0.325 | 0.281 | 0.329 | 0.294 | 0.268 | 0.294 |
| Multi-Person Duration Reasoning | 196 | 0.20 | 0.367 | 0.342 | 0.413 | 0.357 | 0.357 | 0.429 |
| Region Localized People Counting | 148 | 0.20 | 0.358 | 0.331 | 0.345 | 0.277 | 0.257 | 0.311 |
| Scene Verification & Arrangement | 328 | 0.20 | 0.515 | 0.546 | 0.524 | 0.335 | 0.421 | 0.503 |
| Temporal Shot Ordering | 152 | 0.20 | 0.145 | 0.171 | 0.178 | 0.296 | 0.178 | 0.151 |

- **Largest Thinking − Instruct gaps by task:** Action Counting (4BT 0.514 vs 4BI 0.750) and Scene Verification & Arrangement (4BT 0.335 vs 4BI 0.515). Temporal Shot Ordering is the only task where 4BT exceeds every Instruct arm (0.296 vs ≤ 0.178).
- Not yet run in this section: the full-set questions (shard 0 full started 21:31) and the latency sample.
