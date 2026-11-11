# StudyE7-d2-4b: 4B on the D2 append-only history, an Orin frame archive, 4B latency curves

E-id: StudyE7-d2-4b (`research/EXPERIMENTS.md`, pre-registered 2026-11-11). Host: h100nvl **GPU 2** (GPU-4f1d7e47-e769-a289-4860-e71c0d97267c; user decision 2026-11-11), localhost.

## 0. Mechanism verification (recorded BEFORE the sweep, 2026-11-11)

### Job A: 4B accuracy on D2

**Step 1, causal chain.**
- FORMULATION's semantic component: answer quality depends on the representation *and* on the model that reads it.
- RH4 showed that D2 (fixed 2-s stride, 352×256 separate images, append-only) carries the history evidence for 32B: on RECENT-miss questions D2 is +22.3 pp over K3.
- So D2's input holds evidence that the 120-s window lacks. Whether a *device-class* model can use it is a capability question at fixed input. If 4B can use long image histories, 4B D2 should beat 4B RECENT (H1) on OLDER / OVERLAP questions, as 32B D2 beats K3.
- If 4B cannot use them, 4B D2 ≈ H1 on those strata, and the D2 representation's value is model-dependent. That is the coupling FORMULATION's joint representation × placement choice rests on: the warmable format is only worth holding where the model reading it can use it.

**Step 2, instantiate each link (pre-sweep values).**

| causal link | implementing quantity | value | varies as expected? | evidence |
|---|---|---|---|---|
| D2 input holds history evidence | 32B D2 − K3 on RECENT-miss | +22.3 [+12.8, +32.6] pp | yes (≈ 0 on RECENT-cover: −1.7) | RH4 report |
| identical input across models | vLLM prompt tokens vs RH4's processor count | gate on 5 questions before the sweep; recorded on every row | to be confirmed (STOP if not equal) | `e7_run_meta_h100nvl.json` → parity |
| model capability varies | model size | 4B vs 32B, same family, same processor | yes, by design | pinned revisions |
| history length varies | D2 prompt tokens | 1.1k – 30.7k (feasible); 6 questions over context | yes | RH4 manifest |
| stratum separates evidence location | OLDER / OVERLAP / INSIDE / QT_LE_120 | 97 / 167 / 414 / 167 | yes | StudyClean definitions |

No link is ABSENT or CONSTANT.

**Step 3, trace one unit.** One request is reconstructed in the report from its row: images, prompt tokens vs RH4's count, body SHA-256, letter and letter mass. Job C re-derives the same body hash from the archive files.

**Step 4, negative control.** Grey frames on 100 feasible questions (seed 0): every image replaced by a uniform RGB 128 PNG of the same size; header, text and image count unchanged. If 4B's D2 accuracy comes from the frames, grey accuracy must fall to the text-prior level. Real − grey is reported.

**Step 5, alternative explanation.**
- A low 4B D2 score could come from *long-context degradation* (4B losing track in 20–30k-token inputs) rather than an inability to use history evidence.
- What distinguishes them: accuracy by prompt-token bin within the INSIDE stratum, where the evidence is recent, so history is not needed. A falling INSIDE accuracy with length points to degradation; a flat INSIDE accuracy with no OLDER gain points to the capability limit.
- A second alternative: the max_tokens change (64 vs RH4's 512) shortening answers. Checked via finish = length counts and first-token letter mass.

### Job B: 4B latency curves

**Step 1, causal chain.** FORMULATION's physical component: reconstruction cost grows with context. For a warmable append-only history, a prefix-cache hit removes the cached part's prefill, so the WARM cost should track *uncached* tokens. F3 measured this for 32B; Job B measures the same cells for 4B, the device-class model, on the same questions.

**Step 2, instantiate each link.**

| link | quantity | planned range | evidence |
|---|---|---|---|
| tokens drive prefill | prompt tokens | F3 cell c bins: 2.2k – 30.7k | `f3_plan.json` |
| cache state | cached_tokens | 0 on all COLD rows (STOP otherwise); > 0 on WARM later requests | rows |
| exclusivity | other jobs of ours | none (chain-enforced; 30-s monitor, VOID on overlap) | monitor log |

**Step 4, negative control.** COLD cached = 0. In WARM, each session's first request has only the header to reuse, so it must sit on the cold curve.

**Step 5, alternative explanation.** A WARM speed-up could come from host-state drift (clock or other tenants) rather than caching. The SM clock and other users' GPU activity are logged per request and every 30 s; COLD and WARM run back to back on the same card.

### Job C: archive

No causal claim. Integrity is checked: every archived request body must hash to Job A's recorded body SHA-256, rebuilt from the archive's own PNG files.

## 1. Job A: 4B on D2 (COMPLETE 2026-11-11 09:28, h100nvl GPU 2)

**Setup.**
- RH4's `body()` for cell D2, unchanged: header, 352×256 separate images at t = 0, 2, … ≤ qt, R1 question text, seed 42, greedy.
- max_tokens 64 (RH4 used 512); logprobs top 20; concurrency 8.
- Prefix and processor caches off.
- Stack: vLLM 0.31.0, 4B-Instruct @ebb281ec, RH4 image flags.

**Checks.**

| check | value |
|---|---|
| answered / infeasible / failed | 839 / **6** / 0. The infeasible six are RH4's own (qt 757, 1000, 1011, 1124, 1146, 1155 s), HTTP 400 on context length, never truncated. |
| parity gate (5 questions) | PASS; then **839 / 839** rows have vLLM prompt tokens = RH4's processor count |
| transport retries / unparsed / finish = length | 0 / 0 / 0 |
| cached_tokens ≠ 0 | 0 |
| prompt tokens | 511 – 30,701 (p50 10,584) |
| top-20 letter mass at the first token | min 0.99987, so the answer letter is the first token, and max_tokens 64 vs 512 cannot matter |
| predicted letters / gold | A 172, B 126, C 194, D 154, E 193 / A 182, B 173, C 167, D 166, E 151 |

**Step 3, traced unit.** Question 18C977EDB2 (qt 568 s, gold C):
- 285 images; prompt 25,824 tokens = RH4's count (and RH4 Part 0's trace).
- body SHA-256 b6fe4df5…
- 4B answers **A** (letter mass A 0.739, C 0.187); 32B D2 answered **C**.
- 2 completion tokens; finish stop.

### Accuracy (video bootstrap 2,000, seed 0)

| arm (model, input) | ALL | OLDER | OVERLAP | INSIDE | QT_LE_120 |
|---|---|---|---|---|---|
| **4B D2, all 845 (infeasible = wrong)** | **30.7** [27.6, 34.0] | 37.1 (97) | 25.1 (167) | 27.1 (414) | 41.3 (167) |
| **4B D2, paired 839** | **30.9** [27.8, 34.0] | 38.3 [27.9, 47.7] (94) | 25.5 [19.4, 31.9] (165) | 27.1 [22.7, 31.2] (413) | 41.3 [33.3, 49.4] (167) |
| 32B D2 (RH4), paired 839 | 39.6 [36.2, 43.0] | 47.9 | 32.1 | 35.4 | 52.7 |
| 4B H1 (RECENT 120 s video) | 32.7 [29.5, 35.8] | 21.3 | 22.4 | 34.9 | 43.7 |
| 4B H2 (RICH video) | 30.4 [27.1, 33.8] | 34.0 | 24.8 | 26.4 | 43.7 |
| 4B D11 U4 | 33.8 [30.6, 37.2] | 35.1 | 29.1 | 31.5 | 43.7 |

### Paired differences on the 839 (pp)

| | ALL | OLDER (94) | OVERLAP (165) | INSIDE (413) | QT_LE_120 (167) | agreement |
|---|---|---|---|---|---|---|
| 4B D2 − 32B D2 | **−8.7 [−12.4, −5.3]** | −9.6 [−19.3, 0.0] | −6.7 [−14.5, +1.3] | **−8.2 [−13.0, −3.4]** | **−11.4 [−19.7, −3.4]** | 51 % |
| 4B D2 − H1 | −1.8 [−4.9, +1.4] | **+17.0 [+6.7, +28.0]** | +3.0 [−4.9, +11.1] | **−7.7 [−11.9, −3.6]** | −2.4 [−7.7, +3.1] | 62 % |
| 4B D2 − H2 | +0.5 [−2.2, +3.2] | +4.3 [−4.3, +12.6] | +0.6 [−5.5, +6.9] | +0.7 [−3.1, +4.6] | −2.4 [−8.0, +3.5] | 69 % |
| 4B D2 − U4 | **−3.0 [−5.7, −0.2]** | +3.2 [−4.6, +11.8] | −3.6 [−10.1, +2.5] | **−4.4 [−8.3, −0.5]** | −2.4 [−8.2, +3.5] | 70 % |

- With infeasible questions counted wrong in both arms (all 845): 4B D2 − 32B D2 = −8.6 [−12.1, −5.2].
- For reference, RH4's 32B D2 − K3 on RECENT-miss was +22.3 pp; here 4B D2 − H1 on OLDER is +17.0 pp.

**Comparison match statements.**
- **vs 32B D2:** identical input (same images, header, text, seed; prompt tokens equal on 839/839), same stack version and greedy decoding. Different: model, max_tokens (64 vs 512, immaterial at a 1–2-token answer), GPU (2 vs 3).
- **vs H1 / H2 / U4:** same model (4B-I @ebb281ec), stack version and greedy decoding. Different input: video vs separate images, 120 s / RICH / U layouts, about 12.4k / 12.6k / 18.2k median tokens vs D2's 10.6k. These are REALLOCATED comparisons, not identical-input ones.

### Grey control (Step 4), 100 feasible questions, seed 0

| | grey | real (same 100) | real − grey |
|---|---|---|---|
| 4B D2 | 20.0 % [12.1, 28.6] | 36.0 % | **+16.0 [+5.0, +26.9]** |

- Grey letters: A 27, B 22, C 28, D 3, E 20.
- Grey prompt tokens equal the real ones on 100/100.
- **The control changes the result: the D2 frames carry the accuracy above the text-only level. Step 4 PASSES.**

### Step 5: long-context degradation vs capability (INSIDE, by D2 prompt-token tercile, same questions)

| tercile | tokens | 4B D2 | 32B D2 |
|---|---|---|---|
| T1 | 5,600 – 9,291 | 25.4 [18.0, 33.3] | 29.7 [22.2, 37.7] |
| T2 | 9,312 – 13,990 | 31.4 [24.1, 38.8] | 40.9 [33.3, 48.9] |
| T3 | 14,017 – 30,701 | 24.6 [17.2, 32.0] | 35.5 [28.3, 42.5] |

There is no monotone decline with length for 4B; all three CIs overlap and both models move together. Long-context degradation specific to 4B is not supported by this split.

## 2. Job C: Orin archive (COMPLETE 2026-11-11 09:30)

- **Path:** `~/.cache/fm-switching/e7_orin.tar`, **623,063,040 bytes**. Not copied anywhere.
- **Selection:** 234 videos have ≥ 2 questions. They were split into 4 equal-count length bins (300–322 s, 323–438 s, 439–600 s, 600–1,200 s), and 5 per bin were drawn with random.Random(0): **20 videos, 74 questions, 4,445 frames**.
- **Contents** (`e7/`):
  - `frames/<video_id>/t<tttt.t>.png`: the exact PNG bytes Job A sent, stored once per video from t = 0 to the last question time.
  - `requests/<question_id>.json`: header, ordered image paths, question text, generation parameters, seed 42, parser, over-context flag, H100 prompt tokens, body SHA-256 and its definition.
  - `letters_4b.jsonl`: Job A's 4B letters, gold, correctness and letter mass.
  - `videos.json`: the selection and bins.
  - `sha256_manifest.json`: 4,521 files.
- **Integrity:** every request's messages were rebuilt from the archive's own PNG files and hashed. **74 / 74 equal Job A's recorded body SHA-256**, so the archive reproduces the H100 requests byte for byte.
- The selection list and the SHA-256 manifest are also in `results/sember/study_e7/` (`e7_archive_summary.json`, `e7_archive_sha256_manifest.json`).

## 3. Job B: 4B latency curves (COMPLETE 2026-11-11 09:58, exclusive, **not VOID**)

**Run history.**
- **Attempt 1 (09:31:48) stopped before any server started.** Another user (gaofeng) had started a 78 GB vLLM process on GPU 2 at 09:30:52, 4 s after Job A's server stopped, and the pre-start idle check refused to start.
- **Relaunched at 09:46, once GPU 2 was free again** (the process had moved to GPU 3).
- The two monitor snapshots that saw the foreign process are both from attempt 1 (09:31:49 and 09:31:52). The measured run (09:46:09 – 09:58:52, 28 snapshots) had **0 foreign processes on GPU 2 and 0 processes of ours outside the job**.
- Other users throughout: liying on GPUs 0 and 1, gaofeng on GPU 3.
- SM clock at every send: 1,785 MHz.

| check | value |
|---|---|
| rows used / discarded warm-ups / errors | 101 / 2 / 0 |
| COLD rows with cached_tokens ≠ 0 | **0 / 60** |
| WARM later requests with cached_tokens = 0 | **0 / 31** |
| prompt tokens equal F3's 32B rows on the same questions | 60 / 60 (b1), 41 / 41 (b2); cached tokens also equal 41 / 41 |

### Cells (single request, localhost, max_tokens 8; seconds)

| cell | cache | n | prompt tokens p50 [range] | cached p50 | TTFT p50 / p90 / max | total p50 / p90 / max |
|---|---|---|---|---|---|---|
| b1 4B D2 | COLD | 60 | 15,703 [2,238 – 30,701] | 0 | 1.290 / 2.479 / 2.989 | 1.306 / 2.508 / 3.010 |
| b2 4B D2 | **WARM** | 41 (10 sessions) | 12,222 [2,278 – 25,905] | 6,784 | 0.810 / 1.528 / 2.005 | 0.821 / 1.539 / 2.033 |

**COLD per token bin** (F3 cell c's bins; TTFT p50 / p90 / max, s):

| bin | tokens p50 | 4B (this run) | 32B (F3, same questions) |
|---|---|---|---|
| 0 | 3,895 | 0.32 / 0.43 / 0.50 | 0.85 / 1.08 / 1.08 |
| 1 | 8,870 | 0.76 / 0.87 / 0.90 | 2.11 / 2.30 / 2.47 |
| 2 | 11,123 | 0.93 / 1.29 / 1.30 | 2.70 / 3.85 / 3.92 |
| 3 | 16,801 | 1.43 / 1.61 / 1.65 | 4.25 / 4.79 / 4.83 |
| 4 | 23,208 | 2.08 / 2.31 / 2.34 | 6.33 / 7.01 / 7.05 |
| 5 | 26,775 | 2.51 / 2.83 / 2.99 | 7.51 / 7.76 / 9.02 |

### Fits (never pooled across cache state; images only)

| model / format / cache | n | x | linear slope (ms per 1k) | intercept (s) | R² lin / quad | quad at 6k / 12.4k / 20k (s) |
|---|---|---|---|---|---|---|
| 4B / images / COLD | 60 | prompt tokens 2.2k – 30.7k | **95.7** | −0.10 | 0.989 / 0.995 | 0.50 / 1.02 / 1.76 |
| 4B / images / WARM | 41 | prompt tokens | 64.4 | 0.06 | 0.869 / 0.870 | 0.45 / 0.84 / 1.35 |
| 4B / images / WARM | 41 | **uncached** tokens 0.5k – 13.8k | 70.9 | 0.53 | **0.325** / 0.372 | — |
| 32B / images / COLD (F3, for reference) | 270 | prompt tokens | 270 | 0.09 | 0.997 / 0.999 | 1.36 / 2.96 / 5.18 |

- Paired with F3 on identical questions, 32B / 4B TTFT ratio: COLD **2.95×** p50 (2.14 – 3.14); WARM 1.92× p50 (1.04 – 2.79).

### WARM vs COLD (cell b2, labelled WARM)

- **First request of each session** (only the 32-token header cached): TTFT − cold-curve prediction = **+0.002 s** p50 (−0.042 to +0.050; n = 10). It sits on the cold curve. **The Step 4 negative control passes.**
- **Later requests** (cached 2,192 – 21,264 tokens, p50 10,384): TTFT − cold prediction = **−0.25 s** p50 (−0.80 to +0.20; n = 31).
- **Unlike 32B (F3: R² 0.78 vs uncached tokens), 4B WARM TTFT tracks uncached tokens poorly** (R² 0.33) and total tokens better (R² 0.87). The fit has a 0.53 s intercept at zero uncached tokens.
- The 4B prefix-cache saving is therefore smaller than its share of cached tokens would predict. Later requests save 0.25 s p50, while about 70 % of their tokens are cached.

## 4. Consistency check (6 checks)

| # | check | outcome |
|---|---|---|
| 1 | cross-check vs committed | PASS. 32B D2 on the paired 839 = 39.6 % (RH4: 39.57 %). H1 32.7 % on 839 vs 32.5 % on 845 (StudyClean). Prompt tokens equal RH4's on 839 / 839 and F3's on 101 / 101. Same 6 infeasible questions as RH4. 4B cold image slope 96 ms per 1k over 2.2k – 30.7k vs F3's 4B image fit 51 ms per 1k over 0.4k – 3.2k (ratio 1.9, < 2×; F3's range is short, where fixed costs dominate). At 12.4k tokens: 4B images 1.02 s here vs 4B U video 1.40 s (F3 bin 2), with images faster as F3 found for 32B. |
| 2 | physical plausibility | PASS. 4B cold prefill about 10.4k tok/s (96 ms per 1k); at 2 × 4.4e9 FLOPs per token that is about 92 TFLOP/s, about 11 % of the H100 NVL's about 835 TFLOP/s dense bf16. That is low but plausible for a small model plus the vision encoder at single-request size, and nowhere near a caching artefact. WARM later requests are never faster than their uncached tokens allow: the minimum later TTFT is 0.33 s, while the smallest uncached delta (529 tokens) needs only about 0.05 s at the cold rate. 32B / 4B = 2.95× against an about 7× parameter ratio. |
| 3 | distribution sanity | PASS. Letters spread over A – E; TTFT monotone in token bin; p90 / p50 ≤ 1.4× inside bins; no constants. |
| 4 | definition audit | D2 = RH4's cell D2 (stride 2 s, 352×256, RH4 header), unchanged. "Infeasible" = RH4's over-context set (HTTP 400). Strata = StudyClean's. COLD = prefix caching off; WARM = on, sessions = F3 cell d's. max_tokens 64 (accuracy) and 8 (latency) are spec values; RH4 used 512. |
| 5 | claim linkage | Semantic component and C5 (joint representation × placement): the warmable D2 format's value is model-dependent in level (−8.7 pp for 4B vs 32B on identical input) but not in direction (4B also gains +17 pp on OLDER over its own recent window). Physical component (C4): the 4B prefill curve and a smaller warm saving. |
| 6 | proxy validity | H100 4B stands in for the device 4B. F4 showed 97–98 % letter agreement between the H100 and the Orin for 4B on identical bytes (short window); the archive lets the user check that on D2. Latency here is H100 latency, not Orin latency. |

## 5. Observations

1. 4B on D2: 30.9 % (paired 839) / 30.7 % (all 845) vs 32B on the identical input 39.6 %: **−8.7 pp [−12.4, −5.3]**. Below 32B in every stratum (OLDER −9.6, CI touching 0).
2. 4B D2 vs 4B RECENT (H1): **+17.0 pp on OLDER [+6.7, +28.0]**, −7.7 on INSIDE, −1.8 overall (CI includes 0).
3. 4B D2 ≈ 4B RICH (H2) overall (+0.5) and in every stratum; −3.0 [−5.7, −0.2] vs U4.
4. Grey frames: 20 % vs 36 % real on the same 100 (+16 pp [+5, +27]).
5. Within INSIDE, 4B accuracy does not fall with prompt length (25 / 31 / 25 % by tercile).
6. 4B COLD prefill on D2: 96 ms per 1k tokens; 2.95× faster than 32B on the same questions.
7. 4B WARM: first-in-session on the cold curve (+0.002 s); later requests −0.25 s p50; TTFT tracks uncached tokens poorly (R² 0.33).

## 6. Interpretation (inference, labelled)

- **4B can use the D2 history.** Its gain over its own recent window on OLDER (+17 pp) has the same sign and similar size as 32B's (+22 pp), and the frames are causal (grey control). The 4B − 32B gap on D2 is a uniform capability gap at fixed input, not a failure specific to long histories. This is consistent with no length effect inside INSIDE.
- **Where 4B D2 loses** is recent evidence (INSIDE −7.7 vs H1). H1 sees the last 120 s as dense video, while D2 samples every 2 s at 352×256.
- **Device-side history as D2 therefore buys old-evidence coverage at the cost of recent detail,** netting about 0 for 4B overall. For 32B, D2 nets about +1 over K3 (RH4).
- **Possible cause of the weak 4B warm saving** (not tested): per-request work that a prefix hit does not remove, such as decoding and resizing all images in the request on the CPU. That work scales with total images, not uncached tokens, and is a larger share of a 4B request than of a 32B one.
