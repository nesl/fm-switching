# StudyD2-nexar pilot: is the Nexar task non-trivial, and what is the frozen input?

**E-id:** StudyD2-nexar (pre-registered 2026-11-04 ~15:30, before any rendering or inference).

**Status: COMPLETE.** The three stop-and-ask flags (see "Flags") were resolved by the user on 2026-11-04:
1. The `EngineDeadError` at 32B shutdown is accepted as a shutdown artifact.
2. The grey frames do not meet the stop condition.
3. The ~1e-9 grey-score variation for 32B SMALL is accepted.
- Inputs rendered.
- Mechanism verification recorded below, BEFORE inference.
- Inference ran on h100nvl GPU 2 on 2026-11-04 (4B 17:58–18:06; 32B 18:06–18:48).

**PILOT ONLY.** Development clips only, no test-set frame read, no test result, and no main run.

## Frozen input (as built)

| item | value |
|---|---|
| split | Nexar train (1,500), seed 0, by clip, stratified by label × scene, largest remainder. Dev 751 (376 pos / 375 neg); val 300; test 450. `nexar_train_split_seed0.csv` |
| pilot sample | 75 pos + 75 neg dev clips, seed 0, scene-stratified. Every quota filled. Pos: Urban 48, Highway 17, Sub-urban 8, Other 2. Neg: Urban 31, Highway 21, Sub-urban 20, Rural 1, Industrial 1, Other 1 |
| reference time | Pos: `time_of_event` (observed). Neg: **ASSIGNED**, sampled (seed 0) from dev-positive `time_of_event` in the same duration bin, then clipped to [3, D − 2]; 0 negatives needed clipping |
| reference-time check (pos vs neg, within bin) | 18–20 s: n 3 / 7, median 10.16 / 9.56 s, KS p 0.85. 38–42 s: 68 / 64, 19.86 / 19.96 s, KS p 0.51. Other: 4 / 4, 19.44 / 19.71 s, KS p 0.77. Matched |
| offsets | −3, −1.5, −1, −0.5, 0, +1, +2 s from the reference |
| frames | N = 9 targets evenly spaced over [e − 3, e]. Each takes the latest decoded frame with pts ≤ target (PyAV decode timestamps) |
| causality | Last frame ≤ offset: asserted for **1,050/1,050** requests |
| short span | 1 clip: `01799.mp4` (negative, ref 3.921 s) at offsets −3 / −1.5 / −1 (spans 0.92 / 2.42 / 2.92 s). Same N, logged |
| resolutions | **native** 1280×720 (Qwen3-VL resizes to 1280×704: **880 image tokens/frame**). **SMALL** 768×432 (LANCZOS; resized to 768×448: **336 tokens/frame**). StudyDevFast's 560×560 is 324 + marker ≈ 332 |
| storage | 7,053 unique frames, lossless PNG, at `/home/pragya/data/dashcam/d2_frames/{native,small}` (4.7 GB / 2.4 GB). SHA-256: `frames_sha256_manifest.jsonl.gz`; per-request hashes: `pilot_requests.jsonl` |
| ground truth (1,050 requests) | 398 positive (prefix end ≥ `time_of_alert`), 525 negative, 127 unscored (positive clip before alert) |

**Ground truth by offset:**

| offset | positive | negative | unscored |
|---|---|---|---|
| −3 | 5 | 75 | 70 |
| −1.5 | 36 | 75 | 39 |
| −1 | 60 | 75 | 15 |
| −0.5 | 72 | 75 | 3 |
| 0, +1, +2 | 75 each | 75 each | 0 |

**Prompt** (one user turn, the same for every clip):
1. `The following are 9 consecutive dashcam frames covering 3 seconds, oldest first.`
2. Nine images, oldest first.
3. `Is a collision or near-collision involving the camera vehicle happening or about to happen? Answer only Yes or No.`

**Traced prompt** (`prompt_trace.txt`, 4B, SMALL, request `00701_-3.0`, 3,090 tokens):
`<|im_start|>user\n` + header + 9 × (`<|vision_start|>` `<|image_pad|>`×336 `<|vision_end|>`) + query + `<|im_end|>\n<|im_start|>assistant\n`.
**No digits appear outside the header ("9", "3"), and no file name appears: no-absolute-time check PASSED.**

**Prompt tokens (equal for every request in a resolution, and for both models):**
- **SMALL:** 3,090 = 9 × (336 + 2) + 48 text.
- **Native:** 7,986 = 9 × (880 + 2) + 48. Far below the 32,768 limit.

## Mechanism verification (recorded 2026-11-04, BEFORE inference)

**Step 1: causal chain.**
- FORMULATION.md §Motivating scenario and §Regime uncertainty frame the question as which capability (device 4B vs cloud 32B) to provision when the requirement isn't known in advance.
- The chain tested: **as the 3 s window moves closer to and past the event, the frames contain more of the event itself** (approach, contact, evasive motion). **A model that can read that evidence should raise P(Yes) on positives relative to negatives**, so AUROC changes with offset. How much it changes, and when, may differ between 4B and 32B, which is what bears on the capability choice.
- *Grounding caveat:* FORMULATION.md is written for session-state provisioning, not visual event detection. The link is through the device-vs-cloud capability question, not a formula in that document.

**Step 2: instantiate each link (pre-inference evidence from the inputs).**

| causal link | implementing quantity | value / range | varies as expected? | evidence |
|---|---|---|---|---|
| window moves with offset | frames per request | consecutive offsets share 0.83 frames on average (max 5 of 9) | yes | `pilot_requests.jsonl` hashes |
| more event content near / after the event | flow magnitude, frame differencing (same 9 frames) | positives: median mean flow 3.30 → 3.88 (−3 → 0), max frame difference 19.1 → 22.6 (−3 → +1). Negatives: 2.95 → 3.27, 15.9 → 17.8 | yes. A positive − negative gap exists and widens toward 0 / +1 | `flow_features.csv` |
| ground truth defined per prefix | gt by offset | positives scored 5 → 75 from −3 to 0 | yes | table above |
| model evidence use | P(Yes) by gt × offset | **measured by the run** | — | analysis below |

**Step 3: one traced request** (`00701_-3.0`; positive clip, unscored at this offset):
- **Times:** ref 19.300 s, end 16.300 s, `time_of_alert` 18.433 s.
- **Frame pts (s):** 13.300, 13.667, 14.033, 14.400, 14.800, 15.167, 15.533, 15.900, 16.300. All ≤ 16.300.
- **First SMALL frame sha256:** `254d0b151327…`.
- Prompt tokens and P(Yes) are recorded per request by the run (`d2_requests_h100nvl.jsonl`).

**Step 4: negative control (mechanism disabled).** Grey frames remove all visual evidence, so the score must be one constant across 100 identical requests, and its Yes rate must not approach the real-frame rate (STOP if it does). A second control within the data: negatives contain no event, so their Yes rate should not rise with offset the way positives' does.

**Step 5: alternative explanations and what separates them.**
1. **Generic motion or scene busyness, not collision evidence.** Separated by the optical-flow baseline (same 9 frames) and by negatives' Yes rate across offsets.
2. **Scene or weather priors.** Separated by the metadata baseline. *Pre-run preview (out-of-fold):* pooled AUROC 0.52, about chance.
3. **Reference-time placement.** Negatives' references are matched to positives within duration bins (KS p 0.51–0.85), so the position in the clip carries no label.
4. **Flow baseline preview:** pooled AUROC 0.64, by offset 0.42 / 0.58 / 0.56 / 0.55 / 0.60 / 0.69 / 0.73. So simple motion features carry some signal that rises after the event. A model must beat this to show more than motion sensitivity.

## Results (observations)

All 4,600 requests answered (1,050 real × 2 resolutions + 100 grey × 2, per model): 0 errors, 0 transport retries, every request on attempt 1.

### Checks

| check | result |
|---|---|
| neither Yes nor No at the first token | **0 / 4,200** real requests (all four model × resolution cells); 0 / 400 grey |
| causality (last frame ≤ offset) | 1,050 / 1,050 |
| identical input across models | frame sha256 equal 1,050 / 1,050 per resolution (and equal to the manifest); prompt tokens equal 1,050 / 1,050 |
| reference-time match within duration bins | KS p 0.85 / 0.51 / 0.77 (18–20 s, 38–42 s, other) |

### Grey-frame control (100 identical requests per model × resolution)

| model / res | Yes rate (≥ 0.5) | distinct P(Yes) values | grey P(Yes) | real requests with P(Yes) > grey | real Yes rate (≥ 0.5), all 1,050 |
|---|---|---|---|---|---|
| 4B / SMALL | 0 % | 1 | 1.1e-7 | 93.1 % | 5.5 % |
| 4B / native | 0 % | 1 | 1.4e-6 | 68.5 % | 4.5 % |
| 32B / SMALL | 0 % | **3** (97 × 4.36e-9, 2 × 3.40e-9, 1 × 3.85e-9) | 4.4e-9 | 86.8 % | 2.1 % |
| 32B / native | 0 % | 1 | 1.3e-8 | 82.0 % | 2.6 % |

### AUROC [95 % CI, cluster bootstrap by clip] and accuracy at 0.5, by model × resolution × offset

| offset | n (pos/neg) | 4B SMALL | 4B native | 32B SMALL | 32B native | flow-LR | metadata-LR |
|---|---|---|---|---|---|---|---|
| −3 | 5 / 75 | 0.592 [0.327, 0.833] | 0.600 [0.294, 0.851] | 0.547 [0.308, 0.813] | 0.608 [0.407, 0.825] | 0.421 | 0.423 |
| −1.5 | 36 / 75 | 0.689 [0.579, 0.789] | 0.658 [0.549, 0.760] | 0.717 [0.614, 0.811] | 0.707 [0.605, 0.804] | 0.583 | 0.455 |
| −1 | 60 / 75 | 0.686 [0.595, 0.776] | 0.701 [0.611, 0.785] | 0.744 [0.658, 0.821] | 0.736 [0.647, 0.816] | 0.564 | 0.500 |
| −0.5 | 72 / 75 | 0.720 [0.637, 0.800] | 0.727 [0.644, 0.807] | 0.759 [0.680, 0.832] | 0.754 [0.676, 0.827] | 0.550 | 0.524 |
| 0 | 75 / 75 | 0.747 [0.666, 0.820] | 0.752 [0.671, 0.828] | **0.820 [0.751, 0.883]** | 0.812 [0.742, 0.878] | 0.602 | 0.534 |
| +1 | 75 / 75 | 0.776 [0.697, 0.848] | 0.776 [0.698, 0.849] | 0.787 [0.709, 0.853] | 0.774 [0.694, 0.842] | 0.694 | 0.534 |
| +2 | 75 / 75 | 0.739 [0.655, 0.816] | 0.747 [0.663, 0.823] | 0.799 [0.726, 0.868] | 0.785 [0.709, 0.857] | 0.731 | 0.534 |
| pooled | 398 / 525 | 0.735 [0.670, 0.795] | 0.739 [0.674, 0.800] | 0.783 [0.723, 0.837] | 0.777 [0.719, 0.833] | 0.642 [0.570, 0.712] | 0.519 [0.423, 0.612] |

**Accuracy at 0.5 (pooled):** 4B 0.618 / 0.606; 32B 0.592 / 0.597 (SMALL / native); always-Yes 0.431; metadata-LR 0.535. By offset, accuracy tracks the class balance: e.g. 0.938 at −3, where 75 of 80 are negatives, because the models almost always say No.

**Yes rates (≥ 0.5) on positives / negatives, pooled** (FPR = negatives):
- 4B SMALL 13 % / 1 %; 4B native 10 % / 1 %.
- 32B SMALL 5 % / 0 %; 32B native 7 % / 0 %.
- By offset, the 4B Yes rate on positives peaks at +1 (23 % SMALL).

**Early-response rate** (Yes on unscored positive prefixes): 0.8 % (1 / 127) for every cell.

**32B − 4B AUROC (INDICATIVE):**
- **SMALL:** pooled +0.048 [−0.002, +0.101]. By offset −0.045, +0.028, +0.058, +0.039, **+0.073 [+0.009, +0.136] at 0**, +0.010, +0.060.
- **Native:** pooled +0.039 [−0.012, +0.093]. By offset +0.008, +0.049, +0.036, +0.026, +0.060 [−0.000, +0.127], −0.002, +0.038.

**4B vs 32B disagreement at 0.5:** 0–11 % per offset (pooled 5.2 % SMALL, 4.3 % native).

**Within Urban / Highway (AUROC):**

| model / res | Urban pooled (463) | Highway pooled (241) | at 0: Urban (79) | at 0: Highway (38) |
|---|---|---|---|---|
| 4B SMALL | 0.676 [0.58, 0.76] | 0.747 [0.62, 0.85] | 0.667 | 0.782 |
| 32B SMALL | 0.726 [0.63, 0.81] | 0.809 [0.70, 0.90] | 0.724 | 0.905 |
| 4B native | 0.663 | 0.775 | — | — |
| 32B native | 0.711 | 0.803 | — | — |

The full table, including +2, is in the results JSON.

**Examples** (SMALL, threshold 0.5; first five request_ids in sorted order; listed only, not selected):
- **Both right:** 00085 @0, 00103 @0, 00103 @+1, 00103 @+2, 00170 @0.
- **Both wrong:** 00000 @0, @+1, @+2, @−1, @−1.5.
- **32B right, 4B wrong:** 00019 @0, 00218 @+1, 00388 @+2, 00475 @+2, 00543 @0.
- **4B right, 32B wrong:** 00000 @−0.5, 00019 @+1, 00065 @0, 00065 @−1, 00085 @+1.

### Flags (stop-and-ask conditions hit or arguably hit; reported, not resolved)

1. **Server-log ERROR at 32B shutdown.** `AsyncLLM output_handler failed … EngineDeadError` (7 lines, 18:48:24). It appeared AFTER all 2,300 32B requests had completed (last 18:48:24.16, 0 errors) and after "API server: shutdown triggered" from the runner's own stop, while vLLM force-killed the EngineCore. The queue stopped on the rule; D2 was the last job.
2. **Grey vs real Yes RATE.** At the 0.5 threshold, the real-frame Yes rate is itself low (2.1–5.5 %) and grey is 0 %. On the Yes-rate measure the two are therefore close, because both models answer "No" almost always. On P(Yes) itself, grey sits below 68.5–93.1 % of real requests, and AUROC on real frames is 0.73–0.82.
3. **Grey scores not identical for 32B SMALL.** 3 distinct values (97 / 2 / 1 of 100; 3.4e-9 to 4.4e-9) for byte-identical requests. The other three cells were identical. The variation is about 1e-9 in probability and changes no Yes / No decision.

## Interpretation (separate from the observations)

- **The task is non-trivial and discriminable.** Both models rank positives above negatives well above every baseline:
  - pooled AUROC 0.74 (4B) and 0.78 (32B), vs flow-LR 0.64 and metadata-LR 0.52;
  - at the event (offset 0): 0.75 / 0.82 vs flow 0.60.
- **AUROC rises from early offsets to the event, as the mechanism predicts.** For 32B SMALL it goes 0.72 at −1.5 to 0.82 at 0. After the event it does not keep rising (0.79–0.80 at +1 / +2), while the flow baseline catches up at +2 (0.73).
- **The calibrated decision is not usable as-is.** At 0.5 both models almost never say Yes (5–13 % on positives), so accuracy at 0.5 reflects a strong "No" prior. Ranking (AUROC) is where the signal is. This pilot fits no threshold (as pre-registered).
- **32B vs 4B: 32B ranks better by about +0.04–0.05 AUROC pooled** (CI touching 0), with the clearest gap at offset 0. Indicative only; no time-shift claim is made.
- **Resolution matters little.** SMALL (336 tokens/frame) ≈ native (880 tokens/frame) for both models. For a frozen input, SMALL costs 39 % of the tokens with no measured loss.
- **Highway is easier than Urban** for both models. The CIs overlap.
- **Mechanism verification, Step 4:** grey frames collapse P(Yes) to a single near-zero value (flag 3 aside), and negatives' Yes rate stays at ≤ 3 % across offsets while positives' rises toward the event.
- **Mechanism verification, Step 5:** the flow baseline shows that simple motion carries part of the signal, especially after the event. The models exceed it at every offset up to +1.

## Results consistency check

| # | check | result |
|---|---|---|
| 1 | Cross-check | **PASS.** Prompt tokens equal the per-frame counts computed offline with the HF processor (336 / 880 + 2 per image), and are identical across models. |
| 2 | Plausibility | n/a (accuracy only; latency deliberately not reported from batched requests). |
| 3 | Distribution | **FLAGGED.** The Yes rate is low everywhere (reported); grey 32B SMALL has 3 distinct values (reported). AUROC varies by offset and model. |
| 4 | Definitions | **PASS.** Ground truth exactly as pre-registered (prefix end vs `time_of_alert`; negatives all offsets; unscored separate). Score = normalised P(Yes) at the first token. |
| 5 | Claim linkage | Device (4B) vs cloud (32B) capability on a visual-evidence task (FORMULATION.md §Motivating scenario / §Regime uncertainty); a loose link, stated. |
| 6 | Proxy validity | `time_of_alert` is a human annotation used as "evidence available". Negatives' reference times are ASSIGNED (matched in distribution) and are not events. |

**Frozen input proposed for a main run** (decision is the user's): SMALL 768×432, N = 9 over 3 s by decode timestamp, the header and query above, score = normalised P(Yes); evaluated by AUROC per offset; no threshold.
