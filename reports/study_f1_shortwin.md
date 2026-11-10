# StudyF1-shortwin: device-style short windows on the cloud stack

E-id: StudyF1-shortwin (`research/EXPERIMENTS.md`, pre-registered 2026-11-10). Host: h100nvl **GPU 1** (user decision 2026-11-10; the brief said GPU 2, which was held by another user).

## 0. Mechanism verification (recorded BEFORE the sweep, 2026-11-10)

**Step 1, causal chain.**
- A device that keeps only the last 3 s of frames can answer a question only if the evidence lies in those 3 s, or if the question and options alone suffice (text priors). FORMULATION's semantic component: a cheaper representation discards task-relevant information in a workload-dependent way.
- So accuracy should fall as the evidence moves out of the window. The order should be: INSIDE/OVERLAP questions whose evidence touches [qt − 3, qt] > the rest > OLDER (never covered).
- A larger model reading the *same* input can only gain where some evidence or a usable prior is present (capability at fixed input).

**Step 2, instantiate each link (pre-sweep values).**

| causal link | implementing quantity | value in this run | varies as expected? | evidence |
|---|---|---|---|---|
| window holds the evidence | answer interval ∩ [qt − 3, qt] ≠ ∅ | OLDER 0/97 (0 %), OVERLAP 95/167 (57 %), INSIDE 149/414 (36 %), QT_LE_120 47/167 (28 %) | yes: varies by stratum and is 0 where it must be | manifest × `sember_mcq.jsonl` |
| frames span the window | first / last frame pts − qt | N = 3, 9: first = −3.000 s; last −0.083 – 0 s; N = 1: −0.083 – 0 s | yes | `f1_inputs_manifest.jsonl` |
| input grows with N | prompt tokens | measured in the sweep (one prompt trace per model × N) | to be confirmed | `prompt_trace_*.txt` |
| text priors | grey-frame accuracy | measured (100 real questions × model × N) | negative control | §Step 4 |

No link is ABSENT or CONSTANT before the sweep.

**Step 3, trace one unit.** One full prompt per model × N is written by the runner before that model's sweep: `results/sember/study_f1/prompt_trace_<model>_N<n>.txt`, with prompt tokens and image pads per frame. It is checked to contain no video id and no frame timestamp.

**Step 4, negative control.** Grey frames (RGB 128, 560×560) with the real question text and header. If accuracy on real frames is driven by the frames, grey accuracy must fall to the text-prior level. Real − grey is reported per model × N.

**Step 5, alternative explanation.**
- (a) A 32B − 4B gap at fixed input could come from better *text priors* rather than better reading of the frames. The grey control separates them: compare 32B − 4B on grey vs on real frames.
- (b) Lower accuracy than K3/H1 could come from the different *format* (separate 560×560 images vs a 121-frame video at 512×384) rather than the shorter window. This is not separable here; it is reported as REALLOCATED + FORMAT_DIFFERENT, not as a pure window effect.

## Setup

- **Frames:** decoded from the S-EMBER mp4s at their native 12 fps. Kept if the decode timestamp is in [qt − 3, qt]: 36–37 frames per window.
  - N = 1: the last frame with pts ≤ qt.
  - N = 3 and 9: evenly spaced targets mapped to the nearest decoded frame.
- **Resize:** 560×560 PIL LANCZOS, aspect not preserved, as StudyDevFast / DevOne. Lossless PNG: 7,605 unique files, 3.0 GB, SHA-256 in `results/sember/study_f1/f1_frames_sha256.json`.
- **Header:** "The following are N camera frames evenly spaced over the last 3 seconds, oldest first." For N = 1: "The following is the most recent camera frame."
- **Message:** header, then images, then R1's question text; R1's parser.
- **Stack:** vLLM 0.31.0, pinned revisions, prefix and processor caches off, greedy, max_tokens 64, logprobs top 20, concurrency 8.
- **Orin archive:** `~/.cache/fm-switching/f1_orin.tar` (3,215,022,080 bytes), containing the frames, the manifest and the SHA-256 list. Not copied.

## 1. Status and checks

**COMPLETE** 2026-11-10 12:52, h100nvl GPU 1.

| check | 4B | 32B |
|---|---|---|
| rows (845 × 3 N + 100 grey × 3 N) | 2,835 / 2,835 | 2,835 / 2,835 |
| errors / transport retries | 0 / 0 | 0 / 0 |
| unparsed (X) / finish = length | 2 / 1 (N = 1) | 0 / 1 (N = 3) |
| cached_tokens ≠ 0 | 0 | 0 |
| frame SHA-256 = manifest | all | all |
| prompt tokens (median N = 1 / 3 / 9) | 467 / 1,129 / 3,085 | identical (2,535 / 2,535 equal to 4B) |
| prompt trace | no video id, no pts (`prompt_trace_*_N*.txt`) | same |

- **Tokens per 560×560 frame on vLLM:** exactly 327.25, i.e. 324 image pads + vision delimiters + the per-frame share of the template. That is (N9 − N1)/8 on the same question, identical on all 845. The llama.cpp count with the "[t=XXs]" marker was ~332.
- **Top-20 letter mass at the first token:** median ≥ 0.9996 in every cell, so the answer letter is the first token.
- **Orin archive:** `~/.cache/fm-switching/f1_orin.tar`, 3,215,022,080 bytes. It contains `f1/frames/<video_id>/<frame_index>.png` (7,605 PNGs), `f1/f1_inputs_manifest.jsonl` and `f1/f1_frames_sha256.json`.

## 2. Accuracy (video bootstrap 2,000, seed 0)

| model | N = 1 | N = 3 | N = 9 | RECENT 120 s on the same 845 (K3 / H1) |
|---|---|---|---|---|
| 4B-I | 15.4 % [13.2, 17.8] | 14.4 % [12.1, 16.8] | 15.0 % [12.7, 17.5] | H1 32.5 % [29.4, 35.8] |
| 32B-I | 17.8 % [15.3, 20.4] | 15.4 % [13.1, 17.8] | 15.7 % [13.6, 18.1] | K3 38.3 % [34.7, 41.8] |

Chance is 20 % (5 options).

**Paired 32B − 4B (same input):**

| N | ALL | OLDER | OVERLAP | INSIDE | QT_LE_120 |
|---|---|---|---|---|---|
| 1 | +2.4 [−0.1, +4.8] | +4.1 [−3.1, +11.5] | +1.8 [−4.2, +7.7] | +1.4 [−2.1, +5.1] | +4.2 [−1.7, +9.8] |
| 3 | +0.9 [−1.5, +3.4] | +5.2 [−1.1, +11.8] | +0.6 [−4.8, +5.6] | 0.0 [−3.7, +3.7] | +1.2 [−4.4, +6.9] |
| 9 | +0.7 [−1.8, +3.2] | +6.2 [−1.1, +13.7] | +3.0 [−3.0, +9.0] | −2.2 [−6.0, +1.4] | +2.4 [−3.0, +7.3] |

**Short window − RECENT 120 s, same model, same questions (pp):**

| | ALL | OLDER (97) | OVERLAP (167) | INSIDE (414) | QT_LE_120 (167) |
|---|---|---|---|---|---|
| 4B N1 − H1 | −17.2 [−20.8, −13.5] | −5.2 [−14.3, +3.3] | −6.0 [−12.1, +0.6] | −18.8 [−24.2, −13.2] | −31.1 [−39.6, −22.6] |
| 4B N9 − H1 | −17.5 [−21.3, −13.9] | −7.2 [−15.9, +1.2] | −7.2 [−13.4, −0.6] | −19.3 [−24.8, −14.0] | −29.3 [−38.2, −20.8] |
| 32B N1 − K3 | −20.6 [−24.2, −16.8] | −5.2 [−12.8, +2.0] | −7.8 [−13.8, −1.8] | −22.5 [−28.0, −17.3] | −37.7 [−47.9, −27.6] |
| 32B N9 − K3 | −22.6 [−26.7, −19.0] | −5.2 [−13.7, +2.9] | −7.8 [−14.5, −1.3] | −26.6 [−32.0, −20.8] | −37.7 [−47.5, −28.3] |

N = 3 lies between these rows (`f1_results.json` → `vs_recent120`).

**Comparison match statements:**
- Short window vs K3/H1: same model, stack version and decoding (greedy), and the same question text and parser.
- **Different:** window (3 s vs 120 s), frame count (1–9 vs ≤ 121), format (separate 560×560 images vs one video at 512×384), GPU (1 vs 3 for K3), max_tokens (64 vs 512).
- Ledger class: REALLOCATED_BUDGET + FORMAT_DIFFERENT. This is not a pure window effect.

## 3. Negative control (grey frames, 100 real questions per model × N)

| | grey acc | real acc (same 100) | real − grey [CI] |
|---|---|---|---|
| 4B N1 / N3 / N9 | 19 / 14 / 16 % | 16 / 21 / 18 % | −3 [−13, +6] / +7 [−3, +17] / +2 [−7, +11] |
| 32B N1 / N3 / N9 | 13 / 11 / 10 % | 15 / 14 / 14 % | +2 [−6, +10] / +3 [−6, +12] / +4 [−3, +11] |

- 5 distinct letters and 5 distinct responses per grey cell, so this is not a constant-answer artefact (cf. StudyB1's defective control).
- **Grey 32B − 4B:** −6 / −3 / −6 pp; every CI includes 0.

**Step 4 outcome.** With the frames removed, accuracy does *not* measurably change: every real − grey CI includes 0. The short-window frames carry no detectable accuracy above the text-only level on S-EMBER. Under CLAUDE.md Rule 2, the 32B-vs-4B null at fixed short input is therefore **INCONCLUSIVE (mechanism absent)**. Neither model receives usable evidence, so capability has nothing to act on. It is not a real negative about capability.

## 4. Consistency check (6 checks)

| # | check | outcome |
|---|---|---|
| 1 | cross-check vs committed | PASS. 4B N = 1 = 15.4 % vs StudyDevOne N = 1 (Orin, llama.cpp, the most recent frame of the 120 s window, n = 120) 12.5 % [7.7, 19.6]: inside its CI. K3 38.34 % and H1 32.54 % reproduce the ledger. 560×560 tokens 327 vs 332 (llama.cpp, with marker), ratio 0.99. |
| 2 | physical plausibility | n/a (no latency claim; batched). |
| 3 | distribution sanity | PASS. Predictions spread over all five letters in every cell (e.g. 32B N1: A 110, B 218, C 230, D 109, E 178; gold A 185, B 176, C 167, D 166, E 151). Accuracies differ across strata and N; no constants. |
| 4 | definition audit | "Short window" = last 3 s at native 12 fps, new to this study. Not the same object as DevFast's N = 9, which is 9 frames over 120 s. Strata = StudyClean's (counts 97 / 167 / 414 / 167, equal). |
| 5 | claim linkage | Bears on the device-tier capability input to the coupling claim: a 3-s device window gives near-text-only accuracy on S-EMBER, and a bigger model on the same window does not help. It does not speak to placement. |
| 6 | proxy validity | The cloud run stands in for the device run on byte-identical PNGs. Runtime differs (vLLM vs llama.cpp); 4B parity on the Orin is to be measured by you with the archive. |

## 5. Observations

1. **Accuracy is 14–18 % for every model and N, below the 20 % chance level and indistinguishable from grey frames.**
2. Going from 1 to 9 frames does not raise accuracy (4B 15.4 → 15.0 %, 32B 17.8 → 15.7 %).
3. 32B − 4B on identical short inputs: +0.7 to +2.4 pp; all CIs include 0.
4. Against RECENT 120 s, the loss is largest where the 120 s window holds the evidence (QT_LE_120 −29 to −38 pp, INSIDE −19 to −27 pp). It is smallest on OLDER (−5 to −7 pp, CIs include 0), where neither window holds it.

## 6. Interpretation (inference, labelled)

- S-EMBER questions are about earlier events ("where did I put…"). The last 3 s overlap the annotated answer interval for 0 % (OLDER) to 57 % (OVERLAP) of questions, 34 % overall. Even where they overlap, 3 s of an interaction rarely shows the queried state, since real − grey is ≈ 0 in every N.
- The below-chance level, with predictions spread over all letters, suggests the distractors are often consistent with the *current* scene.
- A device-only short window is not a usable answer path for this workload at any model size. Its value can only be as a trigger or summary feeder, not as the answering input.
