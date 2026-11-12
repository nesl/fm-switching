# StudyE10a-jpeg: is JPEG an acceptable wire format?

E-id: StudyE10a-jpeg (`research/EXPERIMENTS.md`, pre-registered 2026-11-11). Host: h100nvl **GPU 2** (GPU-4f1d7e47-e769-a289-4860-e71c0d97267c; user decision 2026-11-11). Job A is CPU only; Job B is batched GPU inference with no latency claim.

## 0. Mechanism verification (recorded BEFORE Job B's sweep, 2026-11-11)

Job A is descriptive (bytes) and has no causal claim. Job B tests one.

**Step 1, causal chain.**
- FORMULATION's physical component: transfer cost scales with payload bytes. JPEG cuts bytes several-fold (Job A), so it would lower uplink time and move the device-vs-cloud crossover.
- It is only usable if the model's output does not depend on the lossy residual. JPEG q90 / q88 changes pixel values (block artefacts, 4:2:0 chroma), so the vision encoder sees different input. The question is whether that changes:
  - the Nexar decision score (a continuous logit-like quantity, so sensitive to small input changes), or
  - the S-EMBER letter (a discrete argmax, so less sensitive).

**Step 2, instantiate each link.**

| link | quantity | value | varies? | evidence |
|---|---|---|---|---|
| JPEG cuts bytes | bytes per frame, JPEG q90 / PNG | Nexar and S-EMBER ratios measured in Job A (§1) | yes | `e10a_sizes.json` |
| JPEG changes pixels | decoded JPEG ≠ PNG pixels | lossy at q88 / q90 by construction; body URL sizes differ per request | yes | Job B rows (`image_url_chars`) |
| identical tokens | prompt tokens PNG vs JPEG | same pixel size, so tokens must be equal; recorded per row; S-EMBER rows must equal R1's count (STOP otherwise) | to be confirmed | rows |
| model output responds to input | Nexar score spread; S-EMBER accuracy above grey | D14: AUROC 0.74–0.84, grey Yes rate 0; R1 K3 38.3 % vs grey near the floor | yes | D14, F1 / B-series |

**Step 3, trace one unit.** One Nexar request per arm (PNG and JPEG): bytes, prompt tokens, P(Yes) and score. One S-EMBER request: tokens vs R1, letter vs K3. Both are reported from the rows.

**Step 4, negative control.** The PNG re-send is the mechanism switched off: same pixels, same stack. Its scores must reproduce D14's committed scores on the same requests up to batch nondeterminism. That gives the floor of score movement that is *not* due to JPEG. The JPEG effect is read against that floor: the fraction of abs(Δscore) > 1 for PNG-resend vs D14 against JPEG vs PNG.

**Step 5, alternative explanation.**
- A JPEG − PNG difference could come from run-to-run nondeterminism (batching changes the kernels) rather than encoding. The Step 4 floor separates them.
- For S-EMBER, the reference is K3's committed letters. StudyF2's negative control showed that K3's PNG request reproduces K3's letters exactly (167 / 167) on another GPU, so disagreement measures encoding plus a small rerun term.

**Step 3, trace (from the Job B rows).** Nexar `00005_t19_N1` (positive), 32B N = 1:
- PNG: data URL 543,078 chars, 378 prompt tokens, 0 cached, P(Yes) 5.14e-5, score (log P(Yes)) −9.875.
- JPEG q90: 97,131 chars (0.18×), 378 tokens, 0 cached, P(Yes) 1.40e-4, score −8.875 (Δ = +1.00; same rank side).

S-EMBER `037f0a41…` (video `1435659120847247…`): 11,655 prompt tokens, equal to R1's count; letter E (K3 also E), correct A.

**Mechanism verdict: all four links instantiated, none ABSENT or CONSTANT.**
- Bytes drop 5–9×.
- Pixels change: |Δscore| > 0 on most rows.
- Tokens are equal: 1,600 / 1,600 Nexar pairs and 100 / 100 S-EMBER rows vs R1.
- The model responds to the input.

## 1. Job A: payload sizes (CPU, `e10a_sizes.json`)

**Nexar**: 500 random D14 SMALL frames (768×432, pool 86,180), bytes per frame:

| encoding | p25 | median | p75 | median / PNG |
|---|---|---|---|---|
| stored (on disk) | 317,985 | 376,528 | 431,018 | 1.11 |
| PNG (re-encoded, as sent by D3 / D14) | 275,118 | 342,065 | 397,332 | 1.00 |
| JPEG q75 | 29,176 | 38,156 | 45,525 | 0.112 |
| JPEG q85 | 39,207 | 50,954 | 60,566 | 0.149 |
| JPEG q90 | 49,810 | 63,898 | 75,682 | **0.187** |
| JPEG q95 | 73,044 | 91,684 | 107,879 | 0.271 |

**S-EMBER**: 200 frames (40 videos × 5) from the 1 fps JPEG q88 cache, resized to each arm's resolution.

Per frame at the main resolutions (median bytes):

| resolution (arm, requests using it) | PNG | JPEG q75 | q85 | q88 | q90 | q90 / PNG |
|---|---|---|---|---|---|---|
| RECENT 512×384 (642 of 845) | 273,875 | 30,474 | 40,197 | 45,421 | 49,990 | 0.183 |
| RICH 352×256 (397 of 845; RICH has 48 sizes, all in `e10a_sizes.json`) | 139,656 | 16,684 | 22,044 | 24,872 | 27,248 | 0.195 |
| D2 352×256 (180 / 200 sampled) | 138,838 | 16,574 | 21,839 | 24,570 | 27,000 | 0.194 |

Per request (all 845 questions, median bytes; frames per request p50 122 / 232 / 116):

| arm | PNG | JPEG q75 | q85 | q88 | q90 | q88 / PNG |
|---|---|---|---|---|---|---|
| RECENT | 33.41 MB | 3.72 MB | 4.90 MB | 5.54 MB | 6.10 MB | 0.166 |
| RICH | 34.91 MB | 4.16 MB | 5.50 MB | 6.20 MB | 6.80 MB | 0.178 |
| D2 | 16.11 MB | 1.92 MB | 2.53 MB | 2.85 MB | 3.13 MB | 0.177 |

**S-EMBER mp4 source bitrate** (234 videos): p5 1.17, p50 **2.10**, p95 3.53 Mbit/s (min 0.64, max 5.69); duration p50 443 s.
- At 2.10 Mbit/s, 120 s of source video is about 31.5 MB, close to the PNG RECENT request (33.4 MB) and about 5.7× the JPEG q88 one.

## 2. Job B: accuracy parity (H100 GPU 2, vLLM 0.31.0, batched)

**Input / stack / decoding match.**
- Each PNG/JPEG pair has the same request, model revision, server flags (D3's flags + prompt-token details), seed and greedy 1-token decoding.
- Only the image bytes differ: JPEG q90 is re-encoded from the same PNG pixels, so the pixel size is identical.
- Prefix caching is off; cached tokens are 0 on all 3,200 rows.
- Batch composition is the same per arm. No latency is claimed.

**Run health.** 3,200 Nexar rows, 0 errors, 0 rows with neither Yes nor No in the top logprobs, 0 cached. 100 S-EMBER rows, 0 errors, 0 unparsed.

### 2.1 Nexar (400 decisions: 200 positive within 3 s of the event and 200 negative, 230 clips)

| model / N | Pearson | Spearman | abs Δscore median / p90 / max | frac abs Δscore > 1 | Yes flips | AUROC PNG → JPEG, Δ [95 % CI] | AP PNG → JPEG, Δ [95 % CI] |
|---|---|---|---|---|---|---|---|
| 4B / 1 | 0.964 | 0.963 | 0.75 / 2.50 / 5.23 | 0.395 | 1.0 % | 0.693 → 0.688, −0.005 [−0.021, +0.010] | 0.659 → 0.652, −0.008 [−0.027, +0.011] |
| 4B / 3 | 0.969 | 0.964 | 0.75 / 1.83 / 4.19 | 0.310 | 3.3 % | 0.695 → 0.699, +0.004 [−0.012, +0.021] | 0.678 → 0.676, −0.001 [−0.020, +0.017] |
| 32B / 1 | 0.985 | 0.982 | 0.63 / 1.75 / 3.75 | 0.303 | 1.0 % | 0.712 → 0.715, +0.002 [−0.008, +0.014] | 0.705 → 0.713, +0.009 [−0.006, +0.023] |
| 32B / 3 | 0.985 | 0.983 | 0.63 / 1.75 / 3.87 | 0.303 | 2.5 % | 0.749 → 0.743, −0.006 [−0.016, +0.004] | 0.718 → 0.714, −0.004 [−0.021, +0.010] |

Paired clip bootstrap, 2,000 resamples, seed 0. Score = log P(Yes). Prompt tokens are equal on 400 / 400 pairs in every cell. JPEG / PNG data-URL size median: 0.168.

**Negative control (Step 4), the determinism floor.** The PNG re-send reproduces D14's committed scores **exactly on 1,600 / 1,600 requests** (Pearson 1.000, fraction abs Δ > 1 = 0.000, median abs Δ = 0).
- So none of the JPEG score movement is run-to-run noise: all of it is the encoding.
- Encoding moves individual scores a lot: 30–40 % of decisions move by more than 1 nat (a factor e in P(Yes)).
- Ranking is preserved: Spearman 0.96–0.98, and **every AUROC and AP difference CI includes 0**.

### 2.2 S-EMBER (100 questions, 32B K3, JPEG q88 frames vs K3's committed letters)

- Prompt tokens equal R1's on 100 / 100.
- **Letter agreement 94 / 100 = 0.94.** The six disagreements, as K3 → JPEG with the correct letter:
  - D → C (correct D), PNG right;
  - E → C (C), JPEG right;
  - E → C (D), both wrong;
  - C → B (A), both wrong;
  - D → E (D), PNG right;
  - B → A (E), both wrong.
- Accuracy: JPEG 0.34 vs K3 0.35. Paired difference −0.010 [−0.047, +0.021] (video bootstrap).
- Median JPEG video data URL: 7.30 M chars.

### 2.3 Verdict (pre-registered rule, unchanged)

The rule: JPEG is acceptable iff every model × N AUROC and AP difference CI includes 0 AND S-EMBER letter agreement ≥ 95 %.
- Nexar clause: **met**, 8 / 8 CIs include 0.
- S-EMBER clause: **not met**, 94 % < 95 %.
- **Verdict: JPEG is NOT acceptable under the pre-registered rule.**

Notes, not changing the verdict:
- The miss is one question. A 95 % binomial interval on 94 / 100 is about [0.87, 0.98], so the experiment cannot tell 94 % from 95 %.
- The accuracy difference is −1 pp with a CI spanning 0. JPEG costs no measurable S-EMBER accuracy at n = 100; what it does is change some letters.
- The StudyF2 control (K3 PNG reproduced K3 167 / 167) and this run's Nexar floor (1,600 / 1,600 identical) put the rerun term near 0. All six disagreements are therefore attributable to encoding.
- StudyE9 §16's JPEG setting (iii) stays **UNVALIDATED** as far as S-EMBER is concerned. The Nexar side supports it: ranking metrics are unchanged, but individual scores are not.

## 3. Results consistency check (6 checks)

1. **Cross-check against committed measurements.** All agree; no disagreement > 2×.

   | quantity | this run | prior | source | ratio | agree? |
   |---|---|---|---|---|---|
   | Nexar PNG scores, same 1,600 requests | identical | D14 trace | `d14_trace_h100nvl.jsonl.gz` | 1.000 | agree |
   | Nexar prompt tokens N = 1 / 3 | 378 / 1,062 | 378 / 1,062 | D3 / D7 | 1.00 | agree |
   | Nexar JPEG q90 bytes per frame | 63,898 (median) | 59,601 (N = 1 request) | StudyD4 via E9 §16 | 1.07 | agree |
   | S-EMBER K3 prompt tokens | = R1 on 100 / 100 | R1 | `study_r1_requests_h100nvl.jsonl.gz` | 1.00 | agree |
   | S-EMBER 32B K3 accuracy, this subset | 0.35 (PNG ref) / 0.34 | 0.383 (all 845) | R1 | 0.91 | agree (subset) |
   | Nexar AUROC (32B N = 1 / 3) | 0.712 / 0.749 | 0.74–0.84 | D14 (all decisions) | about 0.9 | agree (this sample is near-event positives vs negatives, a harder subset; the scores themselves are identical) |

2. **Physical plausibility.**
   - Nexar PNG is 342 kB for 995 kB of raw RGB (0.34×); JPEG q90 is 1.54 bits/px.
   - S-EMBER 352×256 JPEG q90 is 2.4 bits/px; PNG is 12.3 bits/px (noisy dash video, near lossless-coding limits).
   - No rate claim (batched, no latency).

3. **Distribution sanity.** Quartiles are reported for every size. Δscore is reported as median / p90 / max, and the scores are not constant.
   - The medians 0.75 / 0.63 reflect bf16 logprob quantisation: scores move in steps of 0.125.
   - The PNG re-send being identical to D14 is expected (same bytes, same stack, deterministic batch), not a short-circuit: the JPEG arm on the same server differs on most rows.

4. **Definition audit.**
   - "Score" = log P(Yes) from the top-20 logprobs, as D14.
   - "Positive" = a decision within 3 s before the event (spec), not D14's all-positive-clip label.
   - "Agreement" = exact letter match with R1 K3 batched.
   - JPEG = PIL quality q, 4:2:0 subsampling, as D4.
   - "D2", "RECENT" and "RICH" resolutions come from each arm's own resize rule.

5. **Claim linkage.**
   - Bears on FORMULATION's physical component: transfer bytes enter the uplink term.
   - Bears on the StudyE9 §16 sensitivity: JPEG bytes with PNG scores.
   - Supports a 5–9× byte reduction on the wire. For Nexar ranking, JPEG q90 is supported. For S-EMBER letters, it is not established at the pre-registered bar.

6. **Proxy validity.** None used. Bytes are measured directly, and parity is measured on the same requests.

**Consistency check: PASS 6 / 6.**

## 4. Deviations

- **JPEG q90 bytes for Nexar** are re-encoded from the PNG-decoded pixels, as the spec says. They are not taken from the stored on-disk JPEG (1.11× PNG; it is the D14 frame cache, not a wire format).
- **S-EMBER JPEG frames** are R1's final-size frames (the K3 request's npz frames, already resized to the request resolution), JPEG q88-encoded on the client by `study_e10a_parity_vllm.jpeg_b64`, as specified. The K3 reference sent the same final-size frames PNG-encoded, so the comparison is "JPEG q88 vs lossless PNG of the same final-size pixels". *(Wording corrected 2026-11-11 under StudyE10a-full; an earlier version said "the q88 cache bytes sent directly", which does not describe the code. No number or verdict changed.)*
- Run metadata records GPU 2 and UUID GPU-4f1d7e47… (nvidia-smi index 2).

## 5. Outputs

- `results/cost/study_e10/e10a_sizes.json`
- `e10a_nexar_requests_h100nvl.jsonl`
- `e10a_sember_requests_h100nvl.jsonl`
- `e10a_run_meta_h100nvl.json`
- `e10a_results.json`

Scripts: `experiments/cost/study_e10a_sizes.py`, `study_e10a_parity_vllm.py`, `study_e10a_analyse.py`.
