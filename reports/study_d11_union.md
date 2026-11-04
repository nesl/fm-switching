# StudyD11: is "more evidence hurts" real, or caused by reallocating a fixed budget? (arms U and I)

**E-id:** StudyD11 (pre-registered 2026-11-04; arm I addendum pre-registered ~11:25 on 2026-11-04).

**Status: RUNNING.** The format was decided by the user on 2026-11-04 (option C′), and arm F was added. The pre-sweep checks below all passed before any arm request was sent.

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

## Mechanism verification

Steps 1–5 will be recorded here **after the format decision and before the sweep**. The negative control (qt ≤ 120: U = K3 = K1 in frames and letters; arm I = U) and the one-question trace with K3 / U / I frame hashes are part of those steps.

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
