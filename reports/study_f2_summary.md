# StudyF2-summary: generic history summary plus recent frames

E-id: StudyF2-summary (`research/EXPERIMENTS.md`, pre-registered 2026-11-10). Host: h100nvl **GPU 1** (user decision 2026-11-10).

## 0. Mechanism verification (recorded BEFORE the sweep, 2026-11-10)

**Step 1, causal chain.**
- K3 (RECENT) sees only the last 120 s, so on OLDER questions the evidence is outside its input.
- A text summary of earlier video can restore part of that evidence at a fraction of the token cost of frames. FORMULATION's representation choice: a summary is a cheaper representation whose fidelity is workload-dependent.
- So adding the summary to K3 should help where the summarised span holds the evidence (OLDER, and the older part of OVERLAP). It should do nothing where the summary is empty (QT_LE_120: identical input). On INSIDE it may cost, if the added text distracts.
- The gain is bounded by what a generic, question-blind caption keeps: the caption prompt never sees the question.

**Step 2, instantiate each link (pre-sweep values).**

| causal link | implementing quantity | value | varies as expected? | evidence |
|---|---|---|---|---|
| summary spans the evidence | answer start < end of last summarised chunk | OLDER 91/97 (94 %), OVERLAP 143/167 (86 %), INSIDE 0/414, QT_LE_120 0/167 | yes: non-zero exactly where the claim needs it, 0 where it must be | `sember_mcq.jsonl` × chunk plan |
| summary length grows with history | chunks per question (median / max) | OLDER 6 / 34, OVERLAP 5 / 34, INSIDE 4 / 29, QT_LE_120 0 / 0 | yes | chunk plan |
| captions exist for every reachable chunk | captioned chunks | 1,974 planned over 231 videos; runner asserts every reachable chunk is captioned | to be confirmed | `f2_captions_h100nvl.jsonl` |
| caption carries task-relevant facts | caption content | unknown until built (generic prompt); 10-chunk sample reported | **at risk** | §captions |

The last link cannot be checked before the sweep. A caption that never mentions the queried object makes the mechanism absent for that question; the sample and per-stratum results will show it.

**Step 3, trace one unit.** One request per model is reconstructed in the report: summary text, its token count, K3's tokens, the total, and the letter.

**Step 4, negative control.** At qt ≤ 120 the summary is empty and the request is K3's own body (same npz frames, transport, text and seed). Letters must equal K3 (32B) and H1 (4B), and prompt tokens must match, on all 167 questions. The runner stops on any mismatch.

**Step 5, alternative explanation.** A gain on OLDER could come from *any* extra text that makes the model favour some options (a length or format effect) rather than from the caption content. What distinguishes them: the gain should be concentrated where the summary spans the evidence (OLDER / OVERLAP) and absent on INSIDE, where the summary also adds text but cannot hold the evidence. A similar change on INSIDE would point to the alternative.

## Setup

- **Captions:** built once per chunk, before any answer was seen.
  - 30 s chunks, built only where the chunk end ≤ the video's latest qt − 120 s: 1,974 chunks over 231 videos.
  - 8 evenly spaced frames from the 1 fps cache, each a separate 352×256 image (RH4 D2 size).
  - Fixed question-blind prompt; 32B-I; max_tokens 128; greedy.
- **Summary per question:** captions of all chunks ending ≤ qt − 120, oldest first, each prefixed with its time range ("Summary of earlier video:\n[0–30 s] …").
- **Message:** the summary text block, then K3's video unchanged (same npz frames, transport, seed 42), then R1's question text; R1's parser.
- **Answers:** 4B-I and 32B-I, max_tokens 64, logprobs top 20, concurrency 8, prefix and processor caches off.
- **Length check:** worst estimated total 17,448 tokens ≤ 32,768. Nothing was truncated.
- **Comparison match statement.** F2 vs K3 (32B) and vs H1 (4B): same model, stack version, decoding, video frames, question text and parser; only the summary text block is added. GPU 1 here; K3 ran on GPU 3. vs K1/H2 and D11 U/U4: same model and decoding, but a different history representation (frames rather than text), so this is a REALLOCATED comparison.

## 1. Status and checks

**COMPLETE** 2026-11-10 14:08, h100nvl GPU 1.

| check | 4B | 32B |
|---|---|---|
| rows | 845 / 845 | 845 / 845 |
| errors / retried rows | 0 / 0 | 0 / 0 |
| unparsed (X) / finish = length | 0 / 0 | 0 / 0 |
| cached_tokens ≠ 0 | 0 | 0 |
| **negative control** (qt ≤ 120: the request equals K3's) | 167 / 167 letters equal H1; 0 prompt-token mismatches | 167 / 167 letters equal K3; 0 prompt-token mismatches |
| captions | 1,974 / 1,974; 0 errors; every reachable chunk captioned (asserted) | — |

**FLAG: captions are truncated.** 1,971 of 1,974 captions (99.8 %) hit the spec's 128-token cap (finish = length). The 32B model writes a per-frame list, and the cap cuts it after about frames 1–3 of 8 (see the sample). The parameter was not changed, per the spec. This weakens Step 2's last link ("the caption carries task-relevant facts"); see §5.

**Step 3, traced unit** (32B, question B058EEFB…, qt 236 s, OLDER):
- 3 chunks (0–90 s); summary 413 tokens.
- K3's expected prompt is 12,428 tokens; the F2 prompt measured 12,841 tokens (= 12,428 + 413).
- Prediction C (wrong).
- Across all questions, F2 prompt tokens − K3 prompt tokens equals the summary token estimate exactly.

## 2. Accuracy (video bootstrap 2,000, seed 0)

| model / arm | ALL | OLDER (97) | OVERLAP (167) | INSIDE (414) | QT_LE_120 (167) |
|---|---|---|---|---|---|
| 32B F2 | **37.9** [34.4, 41.4] | 22.7 [14.1, 31.5] | 28.7 [22.6, 35.5] | 38.4 [33.7, 43.1] | 54.5 |
| 32B K3 (RECENT) | 38.3 [34.9, 42.1] | 24.7 | 26.3 | 39.9 | 54.5 |
| 32B K1 (RICH) | 39.5 [36.1, 43.0] | 42.3 | 36.5 | 34.1 | 54.5 |
| 32B D11 U | 41.4 [38.0, 45.0] | 42.3 | 34.7 | 38.6 | 54.5 |
| 4B F2 | **31.2** [28.1, 34.5] | 18.6 [11.2, 26.7] | 22.8 [16.5, 28.8] | 32.6 [28.2, 37.1] | 43.7 |
| 4B H1 (RECENT) | 32.5 [29.5, 35.7] | 20.6 | 22.8 | 34.8 | 43.7 |
| 4B H2 (RICH) | 30.2 [26.9, 33.4] | 33.0 | 24.6 | 26.3 | 43.7 |
| 4B D11 U4 | 33.6 [30.3, 36.9] | 34.0 | 28.7 | 31.4 | 43.7 |

**Paired F2 − reference (pp, same questions):**

| | ALL | OLDER | OVERLAP | INSIDE | QT_LE_120 |
|---|---|---|---|---|---|
| 32B F2 − K3 | −0.5 [−2.5, +1.4] | −2.1 [−8.4, +4.1] | +2.4 [−2.4, +7.6] | −1.4 [−4.1, +1.0] | 0 (identical) |
| 32B F2 − K1 | −1.7 [−4.3, +1.0] | **−19.6 [−30.2, −8.9]** | −7.8 [−14.2, −1.8] | +4.3 [+0.2, +8.3] | 0 |
| 32B F2 − U32 | **−3.6 [−5.7, −1.3]** | **−19.6 [−28.9, −10.8]** | −6.0 [−11.8, 0.0] | −0.2 [−3.2, +2.6] | 0 |
| 4B F2 − H1 | −1.3 [−3.3, +0.5] | −2.1 [−10.1, +6.5] | 0.0 [−4.4, +4.3] | −2.2 [−5.1, +0.7] | 0 |
| 4B F2 − H2 | +1.1 [−1.6, +3.7] | **−14.4 [−25.5, −4.1]** | −1.8 [−8.3, +4.6] | +6.3 [+2.9, +9.8] | 0 |
| 4B F2 − U4 | **−2.4 [−4.6, −0.4]** | **−15.5 [−25.0, −5.4]** | −6.0 [−11.6, −0.6] | +1.2 [−1.7, +4.0] | 0 |

- Letter agreement with K3 is 88 % (32B) and with H1 85 % (4B), so the summary does change answers, but not net accuracy.
- QT_LE_120 rows are identical by construction (the negative control).

## 3. Tokens per question

| stratum | chunks (median) | summary tokens (median / max) | F2 prompt (median / max) | K3 prompt (median) |
|---|---|---|---|---|
| ALL | 3 | 414 / 4,720 | 12,896 / 17,380 | 12,437 |
| OLDER | 6 | 829 / 4,716 | 13,270 / 17,380 | 12,441 |
| OVERLAP | 5 | 691 / 4,720 | 13,209 / 17,181 | 12,458 |
| INSIDE | 4 | 551 / 4,025 | 12,986 / 16,512 | 12,449 |
| QT_LE_120 | 0 | 0 | 12,010 | 12,010 |

- The summary adds a median of +3.3 % tokens over K3.
- D11 U uses a median of 18,246 prompt tokens on the same questions (+47 % over K3).

## 4. Caption cost (32B-I, h100nvl GPU 1)

| | value |
|---|---|
| chunks / videos | 1,974 / 231 |
| caption prompt tokens (median) | 752 (8 × 352×256 images + prompt) |
| caption output tokens | 128 median, p90 and max (cap hit 1,971 / 1,974) |
| batched build, concurrency 8 | 1,052.6 s wall → **0.53 GPU-s per chunk amortised**, **64 GPU-s per video-hour** (120 chunks / h) |
| serial (30 requests, first discarded) | **3.00 s per chunk** median (p90 3.01) → 360 GPU-s per video-hour; cached tokens 0 |

The serial time is dominated by decoding: prefill of 752 tokens is about 0.24 s on F3's cold image curve, which leaves about 2.76 s for 128 output tokens (about 21.5 ms per token). The amortised batched figure is the cost to provision.

## 5. Caption sample (10 chunks, seed 0, text cut at 200 characters here; full text in `f2_results.json` → `caption_sample`)

| chunk | range | caption (start) |
|---|---|---|
| 726821053589221#0 | 0–30 s | "The video takes place inside a clothing store, likely a department or discount retailer, with bright fluorescent lighting and multiple clothing racks… **Frame 1**: A wide shot of the store interior…" |
| 1517700072558199#3 | 90–120 s | "…a person unboxing a "Merry & Bright Cat Toys" advent calendar in a home gym setting, with a dog observing. **Frame 1**: The person holds two discount coupons ($10 and $15 off)…" |
| 672963545696130#11 | 330–360 s | "…a dining or living area with a wooden table set for a meal… A black tray of loaded fries… a closed silver laptop, a brown leather wallet, a white power bank…" |
| 766026939144588#0 | 0–30 s | "…domestic activities in a home, primarily in the kitchen and dining area, with a black dog present. **Frame 1**: A kitchen counter with a black coffee maker…" |
| 1691081251514235#4 | 120–150 s | "…a person working at a cluttered art or craft desk… **Frame 1**: A person's right hand, adorned with a bracelet, reaches toward a black corded device…" |
| 1023758566050401#4 | 120–150 s | "…the interior of a modern electronics retail store… **People**: A person in a black t-shirt is visible in the foreground…" |
| 1290745635792905#0 | 0–30 s | "…a person moving through a library or bookstore… **Frame 1**: A close-up of a decorative, black-framed, glass-paneled lamp… a book titled *Privacy and Digital Security*…" |
| 2211104685971437#8 | 240–270 s | "…a city street scene, likely in a downtown area during the holiday season… a line of blue and silver public bicycles is docked at a station…" |
| 1945027152963275#4 | 120–150 s | "…a person preparing a meal in a kitchen, focusing on making a salad and cooking bacon. **Frame 1**: A hand wipes a white kitchen countertop…" |
| 1665695840762798#6 | 180–210 s | "…a person shopping in a store aisle dedicated to baby and toddler products… **Initial frames (1–4)**: The camera pans across shelves…" |

All ten are 128 tokens and stop mid-list. They name salient objects (wallet, laptop, coupons, book title), but only for the first few frames of each chunk.

## 6. Mechanism verification, post-sweep

| link | outcome |
|---|---|
| summary spans the evidence | as pre-registered (OLDER 94 %, OVERLAP 86 %, INSIDE / QT_LE_120 0 %) |
| summary length grows with history | confirmed (median chunks 6 / 5 / 4 / 0) |
| captions exist | confirmed (1,974 / 1,974) |
| caption carries task-relevant facts | **WEAKENED.** 99.8 % of captions are cut at 128 tokens and cover about the first 1–3 of 8 frames, so about 60–85 % of each chunk's sampled frames are not described. |
| Step 4 negative control | **PASS** (334 / 334 identical letters and tokens) |
| Step 5 alternative | No change concentrated on OLDER / OVERLAP, and none on INSIDE either. The alternative (a text-length effect) has nothing to explain. |

## 7. Consistency check (6 checks)

| # | check | outcome |
|---|---|---|
| 1 | cross-check vs committed | PASS. K3 38.3 %, K1 39.5 %, H1 32.5 %, H2 30.2 %, U32 41.4 %, U4 33.6 % reproduce the ledger and E4. At qt ≤ 120, F2 equals K3 / H1 letter for letter on a different GPU (1 vs 3). |
| 2 | physical plausibility | PASS. Serial caption 3.0 s = about 0.24 s prefill (752 tokens, F3 curve) + 128 × about 21.5 ms decode. A 32B bf16 model (about 64 GB of weights) read once per token at the H100's about 3.3 TB/s needs at least about 19 ms, so 21.5 ms is consistent. |
| 3 | distribution sanity | PASS. 0 unparsed; 85–88 % agreement with the RECENT arm; accuracies differ by stratum. |
| 4 | definition audit | "Summary" = question-blind 30-s captions of history older than qt − 120 s (new). Strata = StudyClean's. |
| 5 | claim linkage | Representation choice: a cheap text summary as a substitute for history frames. It bears on whether "evidence" can be shipped as text. |
| 6 | proxy validity | FLAGGED. The truncated captions are a weaker summary than the spec intended to test; the result is about *this* summary. |

## 8. Observations

1. Adding the summary to K3 changes accuracy by −0.5 pp (32B) and −1.3 pp (4B) overall; every per-stratum CI vs K3/H1 includes 0.
2. On OLDER, where the summary spans the evidence for 94 % of questions, F2 stays at the RECENT level (22.7 vs 24.7 %, 32B). History *frames* (K1, U) reach 42.3 %, i.e. F2 is 19.6 pp below them.
3. On INSIDE, F2 is above RICH (K1 +4.3, H2 +6.3 pp), because it keeps K3's dense recent frames.
4. F2 costs +414 tokens per question (median) over K3, versus +5.8k for U.
5. The caption build costs 64 GPU-s per video-hour amortised (batched) or 360 s serial.

## 9. Interpretation (inference, labelled)

- **As specified,** the generic summary does not recover any of the history benefit that frames give. Verdict for this configuration: **NEGATIVE** (F2 ≈ K3, and below U/K1 on OLDER).
- **For the general question** "can a text summary replace history frames", the result is **INCONCLUSIVE (mechanism weakened):** the captions were cut at 128 tokens and describe only the start of each chunk.
- A fair test needs captions that cover all 8 frames, e.g. a larger cap or a shorter-form prompt. That would be a definition change, so it is listed as follow-up and not done here.
