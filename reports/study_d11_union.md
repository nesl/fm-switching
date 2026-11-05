# StudyD11: is "more evidence hurts" real, or caused by reallocating a fixed budget? (arms U and I)

**E-id:** StudyD11 (pre-registered 2026-11-04; arm I addendum pre-registered ~11:25 on 2026-11-04).

**Status: COMPLETE** (2026-11-04, h100nvl GPU 2). The format was decided by the user (option C′), and arm F was added. The pre-sweep checks below all passed before any arm request was sent. Strata are ORACLE labels. Bootstrap: video-clustered paired, 2,000 resamples, seed 0.

## Pre-sweep results (2026-11-04, before the U / I / F sweeps)

1. **Transport.** vLLM 0.31's jpeg-sequence transport (R1's) takes ONE `frames_indices` list per request and requires its length to equal each video's frame count (`vllm/multimodal/media/video.py: load_base64`). So two videos with their own timestamps can't be sent that way.

   Each video is therefore sent as a lossless npz (its own uint8 frames + `frames_indices`, fps 1, `total_num_frames`) through a registered loader (`experiments/cost/d11_npz_video_loader.py`, loaded into the server by `d11_site/sitecustomize.py`). On CPU it returns byte-identical frames and identical metadata to R1's path (one K3 request: 122 frames 512×384, all keys equal).
2. **Server config.** Video limit 2 and `--mm-processor-cache-gb 0`. All other flags are R1's.
3. **Gate: 30 K3 requests (R1 order) on the new config, 32B.**
   - R1's jpeg transport: letters **30/30**, prompt tokens **30/30** equal to K3.
   - npz transport (one video): letters **30/30**, tokens **30/30**.
   - The same gates run for 4B against H1 before its sweep.
4. **Token fit.** Upper bound per question = K1 + K3 prompt tokens (U / I send a subset of K1's frames plus K3's video). Max **25,731** < 32,768; 0 over. Nothing was truncated.
5. **How timing reaches the model.** One complete prompt, as tokenised by the server: `results/cost/study_d11/study_d11_prompt_trace.txt` (question `4DF0872F…`, qt 387 s, 176 + 122 frames, 20,997 tokens).
   - Each video opens with `<|vision_start|>`.
   - Each 2-frame temporal patch is preceded by its own absolute timestamp text `<t seconds>` (mean of the pair's `frames_indices` / fps).
   - **Video 1** (K1 older frames, 88 tokens per patch at K1's size) runs `<1.0 seconds>` … `<265.0 seconds>`.
   - **Video 2** (K3, 192 tokens per patch) runs `<267.5 seconds>` … `<387.0 seconds>`; qt − 120 = 267.
   - Timestamps are therefore absolute and monotonic across the two videos.
   - *Display artifact:* the trace collapses repeated identical tokens as `TOKEN×N`, so repeated digit tokens also collapse (e.g. `<25×2.5 seconds>` is `<255.5 seconds>`).
6. **Inputs** (`experiments/cost/study_d11_inputs.py`; `study_d11_inputs_check.json`; `study_d11_reconstruction.json`):
   - **Reconstruction gate:** R1's pipeline, rebuilt with each question's own frames, reproduces K1's stored older frames **byte-for-byte on 30/30** (Random(0) sample). Donor frames therefore get identical processing.
   - **qt ≤ 120:** 167/167 have no older frames, so U = I = K3 (one video).
   - **qt > 120:** 678/678 have ≥ 1 older frame.
   - **Arm F:** split at k = even index nearest the middle (ties to lower): **pairs preserved in all 678**.
7. **Arm I donors** (seed 0, `random.Random(0)` over R1 order; recorded per question in the manifest):
   - **Size:** always the **same exact native frame size** as the question's video (size groups 720×404: 3, 720×540: 16, 720×954–966: 215 across 5 sizes).
   - **Metadata:** S-EMBER has **no participant or location field**. `video_category_broad` / `video_category` are the only scene-like metadata.
   - **Preference:** a different `video_category_broad` was possible for **678/678**; 0 share the `video_category`.
   - **Duration:** 672 donors are long enough for U's timestamps. **6** use the too-short rule (the longest same-size candidate, donor time = t × T_donor / t_max, order kept, frames may repeat).
   - **Every donor is a different video (and a different source recording).** That does not mean the donor can't contain related content (same kind of activity or place); no such claim is made.

## Pre-sweep check 1: how frame timing reaches the model (observations)

**How K1 and K3 send frames** (`experiments/sember/study_r1_vllm.py: body`):
- Each request is **one video**, with frames at that question's `final_hw`.
- `VideoMetadata` uses fps 1.0 with `frames_indices = round(t)`.
- vLLM's Qwen3-VL processor fuses **consecutive frame pairs** into one temporal patch (`temporal_patch_size` 2).
- Each pair is labelled with a text timestamp equal to the mean of its two indices / fps (`vllm/model_executor/models/qwen3_vl.py: _calculate_timestamps`).

K1 and K3 are each uniformly spaced, so every pair spans one constant stride.

`experiments/cost/study_d11_format_check.py` → `results/cost/study_d11/study_d11_format_check.json`:

| quantity | value |
|---|---|
| questions where K3 and K1 frames have **the same size** | 183 / 845. In the other 662, K3 is larger, e.g. 512×384 vs 352×256 in 397 questions |
| qt > 120 questions whose sorted union is non-uniformly spaced | 371 / 678 |
| temporal pairs in a single union video that join a RICH-only frame with a RECENT frame | 349 of 82,246 |

**Options:**

| option | frame size | timing | tokens (max / p50 / > 32,768) | problem |
|---|---|---|---|---|
| A: one union video at K1's size | one size per request | text timestamps correct per pair; 349 pairs fuse frames of unequal spacing | 16,352 / 12,355 / 0 | K3's RECENT frames are **downscaled in 662 questions**, so U no longer contains K3's input. This reallocates resolution, the very confound D11 is meant to remove |
| B: one union video at K3's size | K3's | as A | 34,552 / 23,034 / **6** | 6 questions exceed `--max-model-len`, and the rule is no truncation or dropping |
| C: two videos, K1's video then K3's, each byte-identical | each its own | exact; each video is uniform | 24,774 / 23,733 / 0 | frames in the last 120 s appear twice; at qt ≤ 120, K1 = K3, so U would be a duplicated video ≠ K3 (breaks the negative control unless qt ≤ 120 sends one video); needs `video: 2` |
| **C′ (recommended): two videos: (1) K1's RICH frames older than qt − 120, at K1's size and stride; (2) K3's video byte-identical** | each its arm's own | exact (absolute `frames_indices` per video; each video uniform) | ≤ C | needs `video: 2`. At qt ≤ 120, video 1 is empty, so U = K3 = K1 exactly and the negative control holds by construction. This is the sorted union (older part first), with no duplicates and no resizing |
| D: separate images with `[t=Xs]` markers (RH4 style) | any | exact | not estimated | a different input format from K1/K3 (images vs video), which confounds format |

**For arm I (addendum)** under C′: video 1 is replaced by donor frames at the same `frames_indices` and K1's size; video 2 (K3) is unchanged.

S-EMBER native sizes are not uniform. Across all 234 videos: 720×404 (3), 720×540 (16), and portrait 720×954–966 (215). A donor from another size class would need a different resize, which is a stop-and-ask item. Proposed rule: the donor comes from the **same native size class**.

There is no source-recording leakage: 234 videos come from 234 distinct sources (`video_id` prefix), so a different `video_id` is always a different recording.

## Pre-sweep check 2: token fit

Every option except B fits under 32,768. Estimate = visual tokens `(n+1)//2 · (h/32)(w/32)` + K3's text tokens. The exact count will be checked per request against vLLM's `prompt_tokens` before the sweep.

## Results (observations)

### Accuracy contrasts (pp) [95 % CI]

Reference arms (same stack, greedy, max 512): 32B → K3 (RECENT), K1 (RICH), from StudyR1; 4B → H1, H2, from StudyClean.

| contrast | format-matched? | ALL | OLDER (97) | OVERLAP (167) | INSIDE (414) | QT ≤ 120 (167) |
|---|---|---|---|---|---|---|
| **32B U − I** (primary addendum) | **yes** | **+3.43 [+1.22, +5.62]** | **+16.49 [+6.73, +26.32]** | +5.99 [−0.59, +12.73] | +0.72 [−2.32, +3.72] | 0 |
| **4B U − I** (primary addendum) | **yes** | **+3.08 [+0.91, +5.23]** | **+14.43 [+3.41, +25.25]** | **+7.19 [+1.19, +13.42]** | 0.00 [−2.95, +2.95] | 0 |
| 32B U − K3 | no | +3.08 [+0.92, +5.24] | +17.53 [+7.84, +27.37] | +8.38 [+2.35, +14.37] | −1.21 [−4.07, +1.60] | 0 |
| 4B U − H1 | no | +1.07 [−1.14, +3.28] | +13.40 [+2.06, +24.51] | +5.99 [−0.61, +12.21] | **−3.38 [−6.13, −0.49]** | 0 |
| 32B U − K1 | no | +1.89 [+0.12, +3.79] | 0.00 [−5.56, +5.77] | −1.80 [−4.94, +1.21] | **+4.59 [+1.43, +7.76]** | 0 |
| 4B U − H2 | no | +3.43 [+1.54, +5.31] | +1.03 [−3.26, +5.43] | +4.19 [0.00, +8.59] | **+5.07 [+1.49, +8.45]** | 0 |
| 32B I − K3 | no | −0.36 [−2.10, +1.44] | +1.03 [−5.83, +8.08] | +2.40 [−2.47, +7.14] | −1.93 [−4.71, +0.96] | 0 |
| 4B I − H1 | no | **−2.01 [−3.66, −0.35]** | −1.03 [−6.86, +5.05] | −1.20 [−6.25, +3.59] | **−3.38 [−6.14, −0.48]** | 0 |
| 32B F − K3 (format control) | — | −0.29 [−0.88, +0.29] | 0.00 [0.00, 0.00] | 0.00 [0.00, 0.00] | −0.48 [−1.47, +0.47] | n/a |
| 4B F − H1 (format control) | — | −0.59 [−1.49, +0.29] | 0.00 [−3.09, +3.03] | 0.00 [−2.44, +2.33] | **−0.97 [−2.02, −0.23]** | n/a |

**Accuracies (U / I):**

| model | ALL | OLDER | OVERLAP | INSIDE | QT ≤ 120 |
|---|---|---|---|---|---|
| 32B | 41.42 / 37.99 % | 42.27 / 25.77 | 34.73 / 28.74 | 38.65 / 37.92 | 54.49 / 54.49 |
| 4B | 33.61 / 30.53 % | 34.02 / 19.59 | 28.74 / 21.56 | 31.40 / 31.40 | 43.71 / 43.71 |

**Format control F:**
- **Letter agreement with the reference:** 32B 0.985 overall (OLDER 97/97 identical, OVERLAP 0.982, INSIDE 0.983); 4B 0.969.
- **Prompt tokens:** F = reference + 2 on every question (the second video's `<|vision_start|>` / `<|vision_end|>`).
- **Why the 32B OLDER / OVERLAP cells are exactly 0.0:** 97/97 letters are identical in OLDER, and in OVERLAP the 3 changed letters are balanced in correctness.

### Interactions (big = 32B, small = 4B; pp and logit) [95 % CI]

| interaction | ALL | OLDER | OVERLAP | INSIDE |
|---|---|---|---|---|
| model × arm (U32 − I32) − (U4 − I4) | +0.36 [−2.23, +2.87]; logit +0.002 [−0.110, +0.112] | +2.06 [−9.47, +14.29] | −1.20 [−9.09, +6.86] | +0.72 [−3.29, +4.64] |
| model × input (U32 − K3) − (U4 − H1) | +2.01 [−0.48, +4.57]; logit +0.080 [−0.027, +0.191] | +4.12 | +2.40 | +2.17 |
| model × input (U32 − K1) − (U4 − H2) | −1.54 [−3.75, +0.71]; logit −0.079 [−0.177, +0.018] | −1.03 | **−5.99 [−11.38, −1.13]** (logit −0.291 [−0.555, −0.049]) | −0.48 |

### Checks

- **Negative control (qt ≤ 120):** U is K3's own single video, so U letters must equal the reference. Observed: **167/167** for both models; tokens 167/167 equal; I letters = U letters 167/167.
- **I vs U prompt tokens:** identical on **845/845** for both models; the pre-registered bound is within 1 %.
- **U vs K3 prompt tokens (qt > 120):** U adds a mean of 5,032 tokens (max 11,264).
- **Trace question** `4DF0872F…` (qt 387 s, 176 older frames). The first two frames' sha256 (16 hex) show no overlap between U's and I's video 1:
  - K3: `9646d1d2…`, `16411f6f…`
  - U video 1: `81c22c38…`, `99af494a…`
  - I video 1: `599feb00…`, `545502f7…` (donor `658657526933765…`, donor times 0 … 266 s)
- **Errors and retries (4B only; 32B had none).** Every error was a client-side `httpx.ReadError` (the connection dropped while the client read the response). The server logs show no error, exception or out-of-memory message, and every request the servers received returned 200. **Cause UNCONFIRMED.**
  - **U4:** 13/845 failed on the first pass (16:56–17:10). The queue stopped on the 1 % rule. The user approved retrying only those 13. All 13 succeeded on attempt 2, with prompt tokens equal to U32's (the manifest-equivalent check).
  - **I4:** 4 transport errors, retried automatically (user rule), all succeeded on attempt 2.
  - **F4:** 6 transport errors, all succeeded on attempt 2.
  - **Retried questions by stratum:** U4: INSIDE 9, QT ≤ 120 3, OLDER 1. I4: INSIDE 4. F4: INSIDE 4, OVERLAP 2. All strata are hit, in rough proportion to their size (INSIDE is 49 % of questions), so there's no sign of a systematic gap.
  - **Concurrency:** 8 for every arm; the 4-concurrency fallback was not needed. Failed attempts remain in the log as separate rows with attempt numbers; the analysis uses each question's successful attempt.

## Interpretation (separate from the observations)

1. **The real-information effect is large and format-matched.** U − I compares the same videos, frame counts, sizes, timestamps and token counts, with only the content of the older frames real vs donor. It is **+16.5 pp (32B) and +14.4 pp (4B) on OLDER**, where the evidence lies before the last 120 s, and **about 0 on INSIDE** (+0.7 / 0.0), where the evidence is already in K3. The model × arm interaction is ≈ 0 (+0.4 pp ALL): both models use real older frames about equally.
2. **"More evidence hurts" (K1 < K3 on INSIDE) looks like reallocation, not more evidence.**
   - When the older frames are ADDED without taking anything from K3 (U), INSIDE does not drop for 32B: −1.2 [−4.1, +1.6], vs K1 − K3 = −5.8.
   - U beats K1 on INSIDE by +4.6 (32B) and +5.1 (4B), i.e. giving back K3's dense, larger recent frames recovers the loss.
3. **For 4B, extra frames of any kind cost about 3 pp on INSIDE.** U − H1 = −3.4 and I − H1 = −3.4 (both CIs exclude 0), and U − I = 0.0. Irrelevant frames cost as much as real ones, so this part of 4B's INSIDE loss is a token, length or format effect, not an information effect. The format control alone (F − H1, INSIDE −1.0 [−2.0, −0.2]) accounts for part of it. For 32B these costs are not distinguishable from 0.
4. **Irrelevant frames do not help.** I − K3 ≈ 0 (32B) and I − H1 = −2.0 (4B). So the U gains are not a format or token artifact. Had irrelevant frames helped as much as real ones, it would have been reported as one.
5. **Contrasts not format-matched:** U − K3, U − H1, U − K1, U − H2, I − K3 and I − H1. Arm F bounds the pure two-video format effect at ≤ 1 pp (32B −0.3, 4B −0.6 ALL).

## Mechanism verification

**Recorded after the sweep: a protocol deviation, reported as such.** The checks the protocol relies on all ran before the sweep:
- Steps 2 and 4 evidence: the transport gates, the reconstruction gate, the token bound and the prompt trace.
- The negative-control gate: built into the runner, which would have stopped before arm I.

The written Steps were not recorded before the sweep as promised above.

**Step 1: causal chain.**
- FORMULATION.md §State objects defines fidelity as "what subset of future queries the object can answer".
- Chain: adding the older frames that hold the answer (U over K3) should raise accuracy only where the evidence is older than the recent window (OLDER / OVERLAP). Replacing exactly those frames with another video's (I) should remove that gain while keeping every token and format cost. Taking dense recent frames away (K1) should cost accuracy where the evidence is recent (INSIDE).

**Step 2: instantiate each link.**

| causal link | implementing quantity | value / range | varies as expected? | evidence |
|---|---|---|---|---|
| older frames carry evidence | U vs I video 1 content | 678 questions with 1–229 older frames; 0 at qt ≤ 120 | yes | inputs manifest |
| same token cost | I − U prompt tokens | 0 on 845/845 | constant **by design** (that is the control) | tokens table |
| recent window intact in U | K3 video byte-identical | k3_sha256 per question | yes | manifest |
| accuracy responds | U − I by stratum | OLDER +16.5 / +14.4; INSIDE ≈ 0 | yes | table above |

**Step 3: one traced request.**
- Question `4DF0872F…`, qt 387 s.
- U = 176 older K1 frames (88 tokens per pair, absolute timestamps 1.0 … 265.0 s) + K3's 122 frames (192 tokens per pair, 267.5 … 387.0 s) = 20,997 prompt tokens.
- I = the same with donor `658657526933765…` frames at the same `frames_indices`.
- `study_d11_prompt_trace.txt` shows the full prompt.

**Step 4: negative control.**
- qt ≤ 120: no older frames, so U = I = K3 and the effect must vanish. Observed: 167/167 identical letters for both models, contrasts exactly 0.
- Arm I: the donor content disables the information while keeping the format. The OLDER gain collapses from +17.5 (U − K3) to +1.0 (I − K3) for 32B.

**Step 5: alternative explanation.** A token-count or format effect would produce U − K3 gains without information. It is separated by:
- U − I (format-matched): the gain remains.
- F (pure format): ≈ 0.
- I − K3: ≈ 0.

Both explanations make different predictions here, and the data favour information on OLDER and token / format costs on 4B INSIDE.

**Null classification:** the INSIDE U − I ≈ 0 result is a **real negative** for "older frames help when the evidence is recent". The mechanism is present (Step 2), and the control changed the result (Step 4).

## Results consistency check

| # | check | result |
|---|---|---|
| 1 | Cross-check | **PASS.** At qt ≤ 120, U reproduces K3 / H1 exactly (167/167). F reproduces K3 / H1 within 0.6 pp with 97–98.5 % letters. K1 − K3 per stratum is as in the audit. |
| 2 | Plausibility | n/a (accuracy only; no latency claims). |
| 3 | Distribution | **PASS.** Contrasts vary by stratum. The two exact zeros (32B F OLDER / OVERLAP) are explained by identical letters (OLDER 97/97) and balanced swaps (OVERLAP). |
| 4 | Definitions | **PASS.** Strata use StudyClean's `stratum()` (asserted 97 / 167 / 414 / 167). U, I, F are as pre-registered. |
| 5 | Claim linkage | Bears on FORMULATION.md §State objects (fidelity = answerable query subset). It supports the claim that a richer history representation answers more queries only when the evidence lies outside the cheap window, and weakens the reading that "more context hurts". |
| 6 | Proxy validity | Strata are oracle labels (stated). Donor frames are a proxy for "no information". They come from a different video and recording, with a different broad category in 678/678. The donor can still contain related content (similar activities or places); this is not claimed otherwise. |

## Exploratory (computed after the data were seen; not pre-registered)

`experiments/cost/study_d13_interaction.py` → `results/cost/study_d11/study_d13_interaction_exploratory_h100nvl.json`.

**Definition:** the 2×2 model × input interaction on canonical cells: (K1 − K3) − (H2 − H1), with 32B in K1/K3 and 4B in H1/H2. Same vLLM stack and decoding; inputs are identical within each column. Strata are oracle labels; video-clustered bootstrap, 2,000 resamples, seed 0.

| stratum | n | 32B gain RICH − RECENT | 4B gain | interaction pp [95 % CI] | interaction logit [95 % CI] |
|---|---|---|---|---|---|
| ALL | 845 | +1.18 | −2.37 | **+3.55 [+0.59, +6.40]** | +0.160 [+0.027, +0.286] |
| OLDER | 97 | +17.53 | +12.37 | +5.15 [−4.44, +15.24] | +0.161 [−0.312, +0.666] |
| OVERLAP | 167 | +10.18 | +1.80 | **+8.38 [+1.20, +16.17]** | +0.373 [−0.005, +0.784] |
| INSIDE | 414 | −5.80 | −8.45 | +2.66 [−2.52, +7.60] | +0.151 [−0.093, +0.380] |
| QT_LE_120 | 167 | 0.00 | 0.00 | 0.00 (identical inputs) | 0.000 |

**Observation:** the 4B loses more from RICH than the 32B does, overall and in every qt > 120 stratum. The overall pp interaction excludes 0; the per-stratum ones do not, except OVERLAP on the pp scale.

**Interpretation is deferred** to the U / I arms, since this table can't separate an information effect from a budget-reallocation effect.
