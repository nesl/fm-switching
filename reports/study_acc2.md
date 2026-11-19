# StudyACC2: per-question 32B accuracy by evidence choice, including long histories, both splits

**Status: COMPLETE, 2026-11-19. GPU run 11:13 to 12:21 (1,819 requests, 1,812 answered, 7 rejected by the engine as
longer than the 32,768-token context). Analysis run 12:28 (CPU, light, pinned to 3 cores at nice 19, during a live
hybrid screening cell under the D138 "light work during live cells" rule). All numbers below are observed counts on
this run; CIs are 10,000-resample bootstraps by question (paired where two representations are compared).**

## 0. Headline

1. **Does history help more on long histories? No.** The net benefit of the full D2 history over the 120-s RECENT
   window (questions D2 answers right and RECENT wrong, minus the reverse) is positive and significant in the 10k to
   19.4k token buckets (+6.5 pp [+1.3, +11.7] and +7.2 pp [+2.1, +13.4]) and **not detectable above 19.4k tokens**
   (-1.7 pp [-9.3, +5.9], n = 118). The long-history prompts built from the live traces say the same (above 19.4k:
   +2.1 pp [-10.4, +14.6], n = 48). Above 19.4k, history changes the answer as often as at 10k to 19.4k (17 % of
   questions), but it hurts as often as it helps.
2. **Overall: D2 0.375 [0.343, 0.409] (n = 839) vs RECENT 0.339 [0.307, 0.370] (n = 845)**; net D2 over RECENT
   +3.5 pp [+1.2, +5.7] (helps 63, hurts 34 of 839 pairs). EVAL +4.7 pp [+2.0, +7.4]; DEV +0.4 pp [-3.7, +4.9].
3. **The policy's committed quality table overstates what live2 serves, for both representations** (section 6,
   check 1): 32B-D2 is StudyRH4's D2 cell (PNG frames from t = 0), 0.420 on DEV, against 0.370 on the same 243
   questions as live2 sends them (JPEG q88, frames from t = 2 s); paired discordant 13 vs 1 on DEV, 33 vs 16 overall.
   32B-RECENT is StudyR1's K3, a different object (121 frames at 103 tokens per frame, median 12.4k tokens) from live2's
   RECENT (60 frames of D2, median 5.5k tokens), 0.387 vs 0.366 on DEV. **This is a request to flash**, who owns the
   quality model: the C3 / RECENT decisions are priced against a RECENT that is better than the one the coordinator
   sends.
4. Idle cold TTFT matches the committed cold curve within 0.96x to 1.18x in every bucket (check 2).

## 1. Why

flash's StudyEVNEED: history vs recent-only changes the 32B's answer on 14.9 % of S-EMBER questions (helps 8.05 %,
hurts 6.86 %, net +1.18 pp), sending RECENT would remove about 96 % of recall GPU time, but none of StudyR1's 845
questions reaches the history lengths the fleet traces carry (above about 19.4k tokens), and the policy's quality
table (StudyRH4, DEV, n = 243, smallest cell 16) was never checked on EVAL.

## 2. Design as run

- Qwen3-VL-32B, the round-1 server configuration, stored D91 JPEG frames in D2 format (352x256, q88), the exact live
  recall body (`live2/bodies.py::build_body`, the coordinator's `HEADER_TEXT` and `RECALL_GEN`), greedy.
- **Caching:** every request COLD and isolated: a fresh run tag per request, so a fresh cache_salt and fresh image
  uuids (no prefix or multimodal reuse); one request at a time on an otherwise idle engine; TTFT to the first content
  token. Verified: cached tokens 0 on all 1,812 answered requests.
- Questions: all 845 StudyR1 questions (602 EVAL, 243 DEV, by the committed split).
- Representations: **D2** (every 2-s D2 frame from t = 2 s to the question, as live2's `d2_frames_in` builds a
  history) and **RECENT** (the last 120 s, as D2 frames). **D2-LIVE-TRACE**: 129 prompts built as the live traces
  carry the history at question arrival (seeds 0, 4, 5, 6 at 64 devices, 600 s), for every question whose trace
  history exceeds its StudyR1 history, deduplicated; EVAL only. 1,819 requests.
- Code: `experiments/sember/study_acc2.py`, `study_acc2_analyse.py`. Outputs `results/sember/study_acc2/`
  (`acc2_requests.jsonl`, `acc2_plan.json`, `acc2_results.json`, `acc2_run.log`).
- Join key note (flash, 104fbd2): rows are unique by (question_id, rep, source); D2-LIVE-TRACE is never merged into
  D2. The analysis keeps the three apart.

## 3. Decisions (posted with defaults; no reply by 10:58, so all are PROVISIONAL defaults)

1. RICH = D2 in the live request format; StudyR1's K1 is the RICH reference.
2. RECENT = the last 120 s as D2 frames.
3. D2 history = every D2 frame from session start to the question.
4. Long set as above (EVAL only, because the fleet traces use EVAL sessions only).
5. Idle, cold, one request at a time.
6. DEV / EVAL from the committed split; bootstrap CIs with 10,000 resamples by question.
7. DEV D2 frames encoded into the D91 store with the Part-1 recipe (`study_rh3_inputs.load(path, (352, 256))`, JPEG
   q88), store-once, marked `acc2_dev`: 13,427 frames for 70 DEV sessions. Size and orientation mix matches the EVAL
   store (checked: 12,528 at 256x352 and 899 at 352x256, against 36,776 and 1,828).

## 4. Results

### 4.1 Accuracy by representation (observed, 95 % CI)

| representation | all | DEV (n) | EVAL (n) |
|---|---|---|---|
| D2 | 0.375 [0.343, 0.409] (839) | 0.370 [0.313, 0.432] (243) | 0.378 [0.339, 0.416] (596) |
| RECENT | 0.339 [0.307, 0.370] (845) | 0.366 [0.305, 0.428] (243) | 0.327 [0.291, 0.365] (602) |
| D2-LIVE-TRACE | 0.305 [0.227, 0.391] (128) | none | 0.305 (128) |
| StudyR1 K1 (32B, RICH capped), committed | 0.395 (845) | 0.403 (243) | 0.392 (602) |
| StudyR1 K3 (32B, R1 RECENT), committed | 0.383 (845) | 0.387 (243) | 0.382 (602) |
| StudyRH4 D2 (policy table 32B-D2), committed | | 0.420 (243) | |

D2 n is 839, not 845: six D2 prompts exceed the context (section 5).

### 4.2 HELPS / HURTS, D2 vs RECENT, by D2 history length (paired; net = helps minus hurts)

| D2 history tokens | n | helps | hurts | changes | net pp [95 % CI] |
|---|---|---|---|---|---|
| 0 to 5k | 147 | 0 | 0 | 0 % | 0 (identical prompts, see check 3) |
| 5k to 10k | 246 | 19 | 10 | 11.8 % | +3.7 [-0.4, +8.1] |
| 10k to 15k | 231 | 27 | 12 | 16.9 % | +6.5 [+1.3, +11.7] |
| 15k to 19.4k | 97 | 8 | 1 | 9.3 % | +7.2 [+2.1, +13.4] |
| **above 19.4k** | **118** | **9** | **11** | **17.0 %** | **-1.7 [-9.3, +5.9]** |
| all | 839 | 63 | 34 | 11.6 % | +3.5 [+1.2, +5.7] |

Live-trace long prompts against RECENT of the same question: 10k to 15k +15.0 [+2.5, +27.5] (n 40); 15k to 19.4k
+5.0 [-5, +15] (n 40); above 19.4k +2.1 [-10.4, +14.6] (n 48).

By split: EVAL +4.7 [+2.0, +7.4] (n 596); DEV +0.4 [-3.7, +4.9] (n 243).

### 4.3 By category (EXPLORATORY; n 88 to 141 per category, no CIs claimed)

| category | n | helps | hurts | net pp |
|---|---|---|---|---|
| sequential_action | 101 | 19 | 2 | +16.8 |
| visual_detail_recall | 141 | 13 | 5 | +5.7 |
| object_comparison | 91 | 7 | 3 | +4.4 |
| temporal_ordering_recognition | 88 | 7 | 4 | +3.4 |
| counting_objects_events | 109 | 5 | 4 | +0.9 |
| time_duration | 121 | 3 | 2 | +0.8 |
| spatial_aware_reasoning | 91 | 1 | 3 | -2.2 |
| location_trace | 97 | 8 | 11 | -3.1 |

### 4.4 Idle cold TTFT vs history tokens (D2 and D2-LIVE-TRACE)

| bucket | n | median tokens | median TTFT s | committed cold curve s | ratio |
|---|---|---|---|---|---|
| 0 to 5k | 147 | 3,111 | 0.663 | 0.691 | 0.96 |
| 5k to 10k | 246 | 7,248 | 1.653 | 1.611 | 1.03 |
| 10k to 15k | 271 | 12,775 | 3.142 | 2.839 | 1.11 |
| 15k to 19.4k | 137 | 16,844 | 4.422 | 3.743 | 1.18 |
| above 19.4k | 166 | 23,712 | 6.602 | 6.240 | 1.06 |

## 5. Run record

- Prep 11:10 (server down). Server up 11:13:41. Requests 11:13:42 to 12:21:57, server stopped 12:21:57, exit 0.
- 7 requests REJECTED, HTTP 400 "Input length exceeds model's maximum context length (32768)": 6 D2 (34,109 to
  52,009 tokens) and 1 D2-LIVE-TRACE (44,715). The live fleet cannot send such a history either. They are excluded
  from the accuracy denominators and reported here; above-19.4k results are therefore conditional on fitting the
  context.
- 1 frame missing from the store, for one question (video 1076706311253108, D2 and RECENT rows).
- During the run I also ran short dry-run CPU proofs for the hybrid (nice 19, pinned to cores 100 to 110), which may
  have perturbed idle TTFT slightly; the TTFT ratios in 4.4 are within 1.18x of the committed curve.

## 6. Results consistency check

1. **Cross-check against committed measurements.**

   | quantity | this run | prior | source | ratio | agree? |
   |---|---|---|---|---|---|
   | 32B D2 accuracy, DEV | 0.370 | 0.420 | StudyRH4 D2, `profiles_dev.json` 32B-D2 | 0.88 | within 2x; explained below |
   | 32B D2 accuracy, all (paired 839) | 0.375 | 0.396 | StudyRH4 D2 batched | 0.95 | yes |
   | 32B RECENT accuracy, DEV | 0.366 | 0.387 | StudyR1 K3, `profiles_dev.json` 32B-RECENT | 0.95 | different object (check 4) |
   | 32B RICH-like, all | D2 0.375 | K1 0.395 | StudyR1 | 0.95 | different object |
   | history changes answer | 11.6 % (D2 vs RECENT) | 14.9 % (K1 vs K3) | StudyEVNEED | 0.78 | different pair of objects |
   | idle cold TTFT | 0.96x to 1.18x | committed curve | `costs.recall_ttft_s(.., "COLD")` | | yes |

   **The D2 gap is explained by an input difference, not a fault.** Paired over the 839 shared questions, StudyRH4's
   D2 prompts are exactly 118 tokens longer on every question (one 90-token frame at t = 0, which live2's
   `data_sources.d2_frames_in` excludes, plus the header), and StudyRH4 sends each frame as lossless PNG
   (`img_url`), while live2 and this study send the stored JPEG q88. 737 of 839 answers are identical; discordant:
   RH4 only 33, ACC2 only 16 (DEV 13 vs 1, EVAL 20 vs 15). I checked the DEV encode for a fault (size and orientation
   mix match the EVAL store); none found. The DEV-concentrated asymmetry is unexplained beyond the input difference
   (DEV has fewer sessions, so per-video clustering is likely). StudyACC2 is the measurement of what live2 actually
   sends.
2. **Physical plausibility.** TTFT within 1.18x of the committed cold curve, never faster than 0.96x; cold confirmed by
   cached tokens 0.
3. **Distribution sanity.** The 0-to-5k bucket shows zero changes: there the 120-s window covers the whole history, and
   D2 and RECENT prompts have identical token counts (147 of 147) and identical answers (147 of 147, greedy). This
   constant is expected and explained. The population net (+3.5 pp) mixes a +6.5 to +7.2 pp effect at 10k to 19.4k
   with a null above 19.4k and an identity below 5k; the strata are reported beside the mean.
4. **Definition audit.** D2 = 2-s stride, 352x256, JPEG q88, frames t = 2, 4, ... up to the question (live2), vs
   StudyRH4 D2 = the same stride and size but PNG and from t = 0. RECENT = last 120 s of D2 frames (median 60 frames,
   5,524 tokens) here, vs StudyR1 K3 = 121 frames at 103 tokens per frame (median 12,437 tokens). The policy table
   32B-RECENT uses the latter. Two different objects share the name RECENT.
5. **Claim linkage.** Bears on the representation-choice claim (cheaper RECENT vs full history under load): history
   helps at 10k to 19.4k and does not help detectably above 19.4k, which weakens "send full history for long
   histories" and supports degrading long histories to RECENT when capacity binds.
6. **Proxy validity.** Accuracy on S-EMBER MCQ is the quality measure the project already uses; idle TTFT is a lower
   bound on loaded TTFT, not a loaded measurement.
7. **Control.** StudyR1 K1 / K3 and StudyRH4 D2 are the committed controls; the paired comparison above is the check
   of the D2 control, and it found the input difference rather than a broken arm.

## 7. Requests to flash (owner of the quality model)

1. 32B-D2 in `profiles_dev.json` is measured on PNG frames from t = 0; live2 sends JPEG q88 from t = 2 s, measured here
   at 0.370 on the same DEV questions (vs 0.420). Consider replacing it, or adding the live-format measurement.
2. 32B-RECENT is StudyR1 K3 (12.4k tokens of richer frames), not live2's RECENT (5.5k tokens of D2 frames): 0.387 vs
   0.366 on DEV and 0.383 vs 0.339 overall. Any decision that sends RECENT is priced against the wrong RECENT.
3. The EVAL per-category accuracies (`acc2_results.json`, `quality_model_vs_acc2`) are available for the EVAL check
   StudyRH4 never had.
