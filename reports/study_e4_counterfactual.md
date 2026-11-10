# StudyE4-counterfactual: decision headroom over static and per-type configurations on S-EMBER

**OFFLINE ANALYSIS OF EXISTING RESULTS.** CPU only, with no new inference. Instruct models, greedy decoding, no Thinking arms.
Script: `experiments/orchestration/study_e4_counterfactual.py` (dashcam venv). Results: `results/orchestration/study_e4/e4_results.json` (+ `e4_frame_bytes.json`).
Pre-registered row: StudyE4-counterfactual in `research/EXPERIMENTS.md` (2026-11-09).

## Prominent flags (read first)

1. **More than 50 % UNKNOWN in the primary analysis** (no measured or interpolated latency):

   | configuration | UNKNOWN |
   |---|---|
   | cl-4B-U | **685 / 845** |
   | cl-32B-U | **647 / 845** |
   | dev-4B-RICH and cl-4B-RICH | **471 / 845** each |
   | cl-32B-D2-WARM (secondary) | 463 / 845 |
   | cl-32B-D2 | 293 UNKNOWN + 6 INFEASIBLE (below 50 %) |
   | dev-4B-RECENT and cl-4B-RECENT | 125 |
   | cl-32B-RICH | 1 |
   | cl-32B-RECENT | 0 |

   - **Arm U is central to the question, but it is mostly unmeasured.** U prompts reach 23.9k tokens, while the cold curves end at 13.2k (32B) and 12.5k (4B).
   - In the primary analysis, UNKNOWN counts as *unavailable* (utility 0). This understates U and D2.
   - The EXTRAPOLATED table (§4.4) shows the result if U and D2 are assumed to keep scaling linearly.
   - 4B RICH misses mainly by a little: its median prompt is 12,597 tokens against a 12,501-token curve end.
2. **Device-runtime agreement is below 90 %.**
   - C1 (llama.cpp, DEV-RECENT) vs H1 (vLLM): **84.7 %** per-question agreement (accuracy 31.5 vs 32.5 %).
   - C2 vs H2: **82.6 %** (31.0 vs 30.2 %).
   - Device configurations use H1/H2 *answers* with Orin *latency*. About 15–17 % of device per-question outcomes would differ under the real device runtime. Format and runtime both differ (llama.cpp GGUF F16 vs vLLM).
   - This does not affect any headline: no device configuration exceeds 0.7 % utility at any cell, because Orin takes ~17 s at ~12k tokens.
3. **The cold 32B curve mixes formats.**
   - At ~12.4k tokens, R1 single (video format) takes ≈ 4.2 s, against ≈ 3.0 s for StudyClean H5 (images).
   - The interpolation through bin medians therefore has a kink there. Arms near 12–13k tokens inherit whichever source dominates the bin.
4. **The WARM D2 latency (RH4 timing5) is prefix caching ON.** It has only 5 points (10.8k–25.8k tokens) and is reported only in the secondary table, labelled WARM.
5. **167 of 845 questions have byte-identical inputs across RECENT, RICH and U** (early-in-video questions). Their answers are identical (167/167), which is the expected deterministic control.
   - Most of the 160 "all-latency-known" questions are of this kind.
   - So the all-known subset and the session "known questions only" variant are dominated by questions where the arms cannot differ in evidence.

## 1. Arm table

All arms are S-EMBER, 845 questions with the same question-set hash (6b1069d4…), Instruct, greedy, max 512 tokens. None is INVALID in `research/EXPERIMENTS.md` or in the ledger exclusions.

| arm | model | construction | source | runtime / host | prompt tokens (min / median / max) | accuracy | used as |
|---|---|---|---|---|---|---|---|
| K3 | 32B-I | RECENT, 121 frames, video | StudyR1 batched | vLLM 0.31.0, h100nvl GPU 3, prefix off | 1,810 / 12,437 / 12,734 | 38.34 % | cl-32B-RECENT |
| K1 | 32B-I | RICH, ≤ 256 frames at 1 fps, video | StudyR1 batched | same | 1,810 / 12,597 / 13,196 | 39.53 % | cl-32B-RICH |
| U32 | 32B-I | union of K3 and K1 frames, video | StudyD11 arm U | vLLM 0.31.0, h100nvl GPU 2 | 1,810 / 18,246 / 23,928 | 41.42 % | cl-32B-U |
| D2 | 32B-I | append-only, 352×256 every 2 s, separate images | StudyRH4 | vLLM 0.31.0, image server, cells prefix off | 511 / 10,584 / 30,701 | 39.57 % (n = 839) | cl-32B-D2 |
| D1 | 32B-I | 288×224 every 2 s | StudyRH4 | same | 411 / 7,706 / 32,758 | 36.74 % (n = 841) | **not used** (user decision; listed only) |
| H1 | 4B-I | K3 requests | StudyClean | vLLM 0.31.0, h100nvl **GPU 1** | as K3 | 32.54 % | cl-4B-RECENT, dev-4B-RECENT |
| H2 | 4B-I | K1 requests | StudyClean | same | as K1 | 30.18 % | cl-4B-RICH, dev-4B-RICH |
| U4 | 4B-I | union | StudyD11 arm U | vLLM 0.31.0, GPU 2 | as U32 | 33.61 % | cl-4B-U |
| F32 / F4 | 32B / 4B | D11 arm F (near-identical to K3) | StudyD11 | same | 12,214 / 12,450 / 12,736 (n = 678) | 34.07 / 29.20 % | noise floor only |
| I32 / I4 | — | D11 arm I (donor frames) | StudyD11 | — | — | 37.99 / 30.53 % | control only, not a configuration |
| C1 / C2 | 4B-I GGUF F16 | DEV-RECENT / DEV-RICH | StudyDevAcc | llama.cpp c0fd7862 (A6000) | — | 31.48 / 31.01 % | agreement check only |

**Match statements for between-arm comparisons:**
- K1 vs K3: same stack and decoding; the inputs differ (that is the arm).
- H vs K: same requests, same stack version, different GPU (1 vs 3), different model.
- U vs K: same stack version, different GPU (2) and a different construction.
- D2 vs K: same stack version, but separate images vs video format, and a different server process.
- Device configurations: H answers with Orin latency, so the runtime does not match (flag 2).

D2 lacks 6 questions (over context length). They are INFEASIBLE (utility 0), and all 845 questions are kept (user decision 3).

## 2. Setup

| item | definition used |
|---|---|
| configuration | (model, location, evidence arm). Device: Orin 4B RECENT and RICH. Cloud: H100 4B {RECENT, RICH, U} and 32B {RECENT, RICH, U, D2}. 9 primary configurations, + cl-32B-D2-WARM in the secondary table. |
| utility | correct AND (compute latency + upload + RTT) ≤ deadline; deadlines 1, 2, 5, 10 s |
| networks | 13.6 Mbit/s + 44 ms; 88 Mbit/s + 22 ms; 5 Mbit/s + 142 ms |
| frame bytes | PNG = median of 200 S-EMBER frames resized (PIL LANCZOS) per resolution, 35 resolutions measured; raw = W×H×3. Examples: 512×384 PNG 276,307 B / raw 589,824 B; 352×256 PNG 139,845 B / raw 270,336 B |
| upload | RECENT: all of its frames each question. RICH / U / D2, history held at the cloud: only frames newer than the previous question of the same video (assumption). Device: none. |
| per-type | category × qt bin (≤ 120, 120–480, > 480 s); best configuration per type, fit on half the videos and evaluated on the other (KFold 2, shuffle, seed 0); empty types fall back to static |
| static | best single configuration, cross-fitted the same way (the in-sample best is also reported) |
| oracle | best configuration per question |
| CI | video bootstrap, 2,000 resamples, seed 0 |

**Latency sources.** All curves are piecewise-linear through 100-token bin medians, used inside the measured range only.

| curve | sources | points | token range | caching |
|---|---|---|---|---|
| cold32 | StudyClean H5 32B-I + StudyR1 single mode (K1/K3) + StudyD10 images_I | 1,160 | 192 – 13,181 | cold. R1 single verified prefix caching **false** in `study_r1_run_meta`; H5 prefix + processor cache off; D10 off |
| cold4 | StudyClean H5 4B-I | 960 | 454 – 12,501 | cold |
| device4 | DevOne N1 + DevFast N9/N18/N37 (Orin, llama.cpp, cache_prompt off); token axis = vLLM counts | 477 | 454 – 12,501 | cold |
| warm32_D2 | StudyRH4 timing5 D2 | 5 | 10,845 – 25,824 | **WARM, prefix caching ON** |

## 3. Mechanism verification (CLAUDE.md Steps 1–5)

**Step 1, causal chain.**
- Per-question best decisions can differ from a fixed policy only if two things hold together:
  - (a) configurations disagree on correctness question by question (capability and evidence: FORMULATION's Q(f, w) varies by representation and model);
  - (b) their delivered latency differs, so that whichever configuration is correct and on time changes with network and deadline (FORMULATION's physical component: transfer and compute cost grow with context).
- Headroom over per-type exists only where (a) and (b) vary *within* a question type.

**Step 2, instantiate each link.**

| causal link | implementing quantity | value / range | varies as expected? | evidence |
|---|---|---|---|---|
| correctness differs across configurations | per-question disagreement between arms | 10.9 % (U32/K3) – 25.4 % (K1/H2) | yes | §6 reversals |
| it is not just noise | disagreement between near-identical arms | F32/K3 0.59 %, F4/H1 1.5 % | yes, 10–40× smaller | §6 |
| compute latency differs | cold32 / cold4 / device4 at ~12.4k tokens | 3.0 – 4.2 s / 1.0 s / ~17 s | yes | §2, trace |
| upload differs by representation and network | upload bytes per question | 0 (device) – 31.8 MB (RECENT PNG); D2 3.6 MB in the trace | yes, ×network ×format | trace, §4 |
| deadline binds | utility changes with deadline | 88/png oracle 0.038 → 0.554 from 1 s to 10 s | yes | §4.1 |

No link is ABSENT or CONSTANT. Two links are **partially unmeasured**: U and D2 latency, because of UNKNOWN (flag 1).

**Step 3, one-question trace.**
Question 28fc07ed…, video 1271720381302919, qt = 122 s, time_duration; 88 Mbit/s + 22 ms, PNG, 10 s deadline.

| config | answers | tokens | compute s | upload B | network s | total s | correct | utility |
|---|---|---|---|---|---|---|---|---|
| dev-4B-RECENT | H1 | 12,293 | 16.95 | 0 | 0 | 16.95 | no | 0 |
| dev-4B-RICH | H2 | 12,491 | 17.22 | 0 | 0 | 17.22 | no | 0 |
| cl-4B-RECENT | H1 | 12,293 | 1.00 | 31,838,730 | 2.92 | 3.92 | no | 0 |
| cl-4B-RICH | H2 | 12,491 | 1.04 | 13,419,630 | 1.24 | 2.28 | no | 0 |
| cl-4B-U | U4 | 12,493 | 1.04 | 13,419,630 | 1.24 | 2.28 | no | 0 |
| cl-32B-RECENT | K3 | 12,293 | 3.03 | 31,838,730 | 2.92 | 5.94 | yes | 1 |
| cl-32B-RICH | K1 | 12,491 | 3.73 | 13,419,630 | 1.24 | 4.98 | yes | 1 |
| cl-32B-U | U32 | 12,493 | 3.76 | 13,419,630 | 1.24 | 5.00 | yes | 1 |
| cl-32B-D2 | D2 | 5,755 | 1.28 | 3,635,970 | 0.35 | 1.63 | yes | 1 |

- Arithmetic check: 31,838,730 B × 8 / 88e6 = 2.894 s, + 0.022 s = 2.916 s.
- Here 32B's capability decides the outcome; no deadline binds at 10 s. At 2 s only D2 would deliver.

**Step 4, negative control.**
- The near-identical arm pairs F32/K3 and F4/H1 have the same latency and almost the same input. Their oracle headroom is **0.15 pp** and **0.44 pp**.
- The session-level analogue is **0.15 pp** (233 sessions).
- So when the mechanism (different evidence) is removed, headroom collapses to ≤ 0.44 pp, against the 6.7–20 pp headline values.

**Step 5, alternative explanation.**
- Oracle headroom is an *upper bound* that rewards any per-question disagreement, including disagreement that no observable signal predicts (a "lucky pick").
- The data cannot separate "predictable switching value" from "unpredictable per-question variance between different inputs": both produce oracle > per-type.
- What argues against pure noise is the noise floor: the same model on near-identical input disagrees on 0.6–1.5 % of questions, against 11–25 % between real arms.
- What remains unresolved is whether any *available* signal predicts the switch. The per-type cross-fit is the only realised policy tested, and it captures little of the gap.

## 4. Headroom tables

### 4.1 Primary (all 845; measured or interpolated latency only; UNKNOWN = unavailable)

Utility = fraction of 845 questions both correct and delivered on time. Headroom = oracle − policy. The noise floor is 0.0015 (32B) / 0.0044 (4B); "≈ noise" marks headroom ≤ 0.0044.

| network / format | deadline | oracle | static (cross-fit) | per-type (cross-fit) | headroom over static [95 % CI] | headroom over per-type [95 % CI] | in-sample best static |
|---|---|---|---|---|---|---|---|
| 13.6 Mbit/s / PNG | 1 s | 0.002 | 0.002 | 0.002 | 0 (≈ noise) | 0 (≈ noise) | cl-32B-D2 |
| | 2 s | 0.017 | 0.017 | 0.017 | 0 (≈ noise) | 0 (≈ noise) | cl-32B-D2 |
| | 5 s | 0.140 | 0.136 | 0.136 | 0.004 [0.000, 0.008] ≈ noise | 0.004 [0.000, 0.008] ≈ noise | cl-32B-D2 |
| | 10 s | 0.333 | 0.256 | 0.265 | **0.077** [0.060, 0.095] | **0.067** [0.051, 0.085] | cl-32B-D2 |
| 13.6 / raw | 5 s | 0.063 | 0.063 | 0.063 | 0 | 0 | cl-32B-D2 |
| | 10 s | 0.211 | 0.187 | 0.187 | 0.024 [0.014, 0.034] | 0.024 [0.014, 0.034] | cl-32B-D2 |
| 88 Mbit/s / PNG | 1 s | 0.038 | 0.037 | 0.037 | 0.001 ≈ noise | 0.001 ≈ noise | cl-32B-D2 |
| | 2 s | 0.143 | 0.124 | 0.118 | 0.019 [0.010, 0.029] | 0.025 [0.015, 0.036] | cl-32B-D2 |
| | 5 s | 0.453 | 0.284 | 0.310 | **0.169** [0.145, 0.195] | **0.143** [0.120, 0.166] | cl-4B-RECENT |
| | 10 s | 0.554 | 0.394 | 0.385 | **0.160** [0.135, 0.186] | **0.169** [0.145, 0.195] | cl-32B-RICH |
| 88 / raw | 2 s | 0.090 | 0.086 | 0.084 | 0.004 ≈ noise | 0.006 [0.001, 0.012] | cl-32B-D2 |
| | 5 s | 0.279 | 0.246 | 0.246 | 0.033 [0.022, 0.046] | 0.033 [0.022, 0.046] | cl-32B-D2 |
| | 10 s | 0.543 | 0.320 | 0.343 | **0.224** [0.195, 0.254] | **0.200** [0.172, 0.229] | cl-32B-RICH |
| 5 Mbit/s / PNG | ≤ 5 s | ≤ 0.030 | = oracle | = oracle | 0 | 0 | cl-32B-D2 |
| | 10 s | 0.135 | 0.122 | 0.122 | 0.013 [0.006, 0.021] | 0.013 [0.006, 0.021] | cl-32B-D2 |
| 5 / raw | 10 s | 0.049 | 0.041 | 0.041 | 0.007 [0.002, 0.014] | 0.007 [0.002, 0.014] | cl-32B-D2 |

All 1 s raw cells and the 5 Mbit/s raw cells at 1–5 s have oracle ≤ 0.017 and headroom 0 (full grid in the JSON).

Per-configuration utility at 88 Mbit/s / PNG:

| config | 5 s | 10 s |
|---|---|---|
| dev-4B-RECENT | 0.001 | 0.007 |
| dev-4B-RICH | 0.001 | 0.007 |
| cl-4B-RECENT | 0.284 | 0.284 |
| cl-4B-RICH | 0.149 | 0.149 |
| cl-4B-U | 0.084 | 0.084 |
| cl-32B-RECENT | 0.015 | 0.383 |
| cl-32B-RICH | 0.120 | 0.394 |
| cl-32B-U | 0.025 | 0.123 |
| cl-32B-D2 | 0.266 | 0.279 |

### 4.2 Restricted to questions every arm has (n = 839; user decision 3)

| cell | oracle | per-type | headroom over static | headroom over per-type [CI] |
|---|---|---|---|---|
| 13.6/png 10 s | 0.335 | 0.267 | 0.077 | 0.068 [0.051, 0.086] |
| 88/png 5 s | 0.455 | 0.311 | 0.170 | 0.144 [0.121, 0.167] |
| 88/png 10 s | 0.557 | 0.387 | 0.160 | 0.169 [0.145, 0.195] |
| 88/raw 10 s | 0.546 | 0.346 | 0.224 | 0.200 [0.172, 0.230] |

Within 0.001 of the 845-question table everywhere: the 6 infeasible D2 rows do not drive anything.

All-latency-known subset (n = 160, flag 5): 88/png 5 s headroom over per-type 0.137 [0.085, 0.195]; 10 s 0.169 [0.110, 0.231].

### 4.3 Secondary, with cl-32B-D2-WARM (WARM: RH4 timing5, prefix caching ON)

All results in this table depend on warm latency.

| cell | oracle | per-type | headroom over per-type [CI] |
|---|---|---|---|
| 13.6/png 5 s | 0.155 | 0.129 | 0.026 [0.016, 0.037] |
| 13.6/png 10 s | 0.370 | 0.256 | 0.115 [0.094, 0.138] |
| 88/png 5 s | 0.479 | 0.305 | 0.174 [0.150, 0.199] |
| 88/png 10 s | 0.564 | 0.385 | 0.180 [0.156, 0.205] |
| 88/raw 5 s | 0.328 | 0.232 | 0.096 [0.078, 0.116] |
| 88/raw 10 s | 0.555 | 0.343 | 0.212 [0.184, 0.241] |
| 5/png 10 s | 0.154 | 0.122 | 0.032 [0.021, 0.045] |

### 4.4 EXTRAPOLATED sensitivity (linear extrapolation beyond the measured range; never mixed into the tables above)

All cells in this table are EXTRAPOLATED.

| cell | oracle | static | per-type | headroom over static | headroom over per-type [CI] |
|---|---|---|---|---|---|
| 13.6/png 5 s | 0.169 | 0.136 | 0.128 | 0.033 | 0.041 [0.029, 0.054] |
| 13.6/png 10 s | 0.374 | 0.260 | 0.263 | 0.114 | 0.111 [0.092, 0.133] |
| 88/png 2 s | 0.199 | 0.124 | 0.160 | 0.075 | 0.039 [0.027, 0.052] |
| 88/png 5 s | 0.507 | 0.325 | 0.334 | 0.181 | 0.173 [0.147, 0.198] |
| 88/png 10 s | 0.588 | 0.395 | 0.393 | 0.193 | 0.195 [0.171, 0.222] |
| 88/raw 5 s | 0.361 | 0.246 | 0.225 | 0.115 | 0.136 [0.114, 0.160] |
| 88/raw 10 s | 0.579 | 0.316 | 0.340 | 0.263 | 0.239 [0.213, 0.266] |
| 5/png 10 s | 0.154 | 0.122 | 0.116 | 0.032 | 0.038 [0.026, 0.051] |

## 5. Classification of oracle-beats-per-type questions (primary, all 845)

- A question is counted when the oracle is 1 and the per-type choice is 0.
- A best configuration that differs from the per-type choice in exactly one factor names that factor:
  - capability = model;
  - evidence = arm (excluding RICH ↔ D2);
  - representation = RICH ↔ D2;
  - location = device vs cloud.
- "Interaction" means no single-factor alternative exists.
- "Exclusive" assigns each question to the first matching factor in spec order. "Any" counts every factor that applies.
- Noise floor: 0.15 pp (32B) / 0.44 pp (4B) of 845 ≈ **1.3 / 3.7 questions**. Classes with ≤ 4 questions are indistinguishable from noise.

| cell | n oracle > per-type | capability | evidence | representation | location | interaction | exclusive (cap / evid / repr / loc / inter) |
|---|---|---|---|---|---|---|---|
| 13.6/png 5 s | 3 (≈ noise) | 0 | 1 | 3 | 0 | 0 | 0 / 1 / 2 / 0 / 0 |
| 13.6/png 10 s | 57 | 1 | 1 | 45 | 0 | 11 | 1 / 1 / 44 / 0 / 11 |
| 13.6/raw 10 s | 20 | 0 | 1 | 17 | 0 | 3 | 0 / 1 / 16 / 0 / 3 |
| 88/png 2 s | 21 | 0 | 1 | 1 | 0 | 20 | 0 / 1 / 0 / 0 / 20 |
| 88/png 5 s | 121 | 0 | 14 | 9 | 0 | 101 | 0 / 14 / 6 / 0 / 101 |
| 88/png 10 s | 143 | 50 | 62 | 33 | 0 | 24 | 50 / 55 / 14 / 0 / 24 |
| 88/raw 5 s | 28 | 0 | 1 | 12 | 0 | 16 | 0 / 1 / 11 / 0 / 16 |
| 88/raw 10 s | 169 | 56 | 73 | 34 | 0 | 41 | 56 / 59 / 13 / 0 / 41 |
| 5/png 10 s | 11 | 0 | 1 | 9 | 0 | 2 | 0 / 1 / 8 / 0 / 2 |
| 5/raw 10 s | 6 | 0 | 0 | 4 | 0 | 2 | 0 / 0 / 4 / 0 / 2 |

**Location is never the deciding single factor.** No device configuration delivers in time where its cloud twin does not, because Orin takes ~17 s at ~12k tokens.

## 6. Noise floor and reversals (correctness only)

| pair | n | disagreement | oracle headroom of the pair |
|---|---|---|---|
| **F32 vs K3 (noise)** | 678 | 0.59 % | **0.15 pp** |
| **F4 vs H1 (noise)** | 678 | 1.47 % | **0.44 pp** |
| K1 vs K3 | 845 | 14.9 % | 6.9 pp |
| H2 vs H1 | 845 | 15.9 % | 6.7 pp |
| K3 vs H1 | 845 | 23.6 % | 8.9 pp |
| K1 vs H2 | 845 | 25.4 % | 8.0 pp |
| U32 vs K3 | 845 | 10.9 % | 3.9 pp |
| U4 vs H1 | 845 | 11.2 % | 5.1 pp |
| D2 vs K1 | 839 | 16.0 % | 7.9 pp |

## 7. Sessions (Part 4)

**Definitions.**
- Session = one S-EMBER video (234), questions ordered by qt. One retention policy is fixed per session.
- 32B policies: recent = K3 (re-uploads its frames every question); stride_D2 = D2 (continuous upload every 2 s); full_K1 = K1 (continuous at 1 fps); full_U = U32.
- 4B policies: recent = H1; full_H2 = H2; full_U = U4.
- Continuous-upload policies have only the newest frame pending at question time. A fixed policy uses only frames up to each question time, so no future information enters.
- The per-session best policy is an ex-post oracle (descriptive).
- Session type = most frequent category in the session.

**Correction from the first run.** The first implementation kept only sessions in which every policy had known latency on every question: 1 of 234 sessions. That was a code defect, not a methodological choice. The primary variant now treats UNKNOWN as unavailable, exactly as Part 1 does, with per-policy UNKNOWN counts shown. Two sensitivities are added.

Session noise floor: K3 vs F32 per-session choice, **0.15 pp** headroom (233 sessions, 678 questions). 1.7 % of sessions differ.

### 7.1 Primary (UNKNOWN = unavailable; 234 sessions, 845 questions)

UNKNOWN counts per policy: 32B recent 0 / stride_D2 293 / full_K1 1 / full_U 647; 4B recent 125 / full_H2 471 / full_U 685.

| model / cell | recent | stride or full_H2 | full_K1 | full_U | best single | per-session oracle | headroom [CI] | sessions with unique best | best differs from modal among same-type sessions |
|---|---|---|---|---|---|---|---|---|---|
| 32B 13.6/png 5 s | 0.002 | 0.279 | 0.393 | 0.123 | full_K1 | 0.428 | **0.036** [0.020, 0.051] | 113 | 9.8 % |
| 32B 13.6/png 10 s | 0.005 | 0.279 | 0.394 | 0.123 | full_K1 | 0.428 | 0.034 [0.020, 0.049] | 113 | 9.8 % |
| 32B 88/png 5 s | 0.015 | 0.279 | 0.394 | 0.123 | full_K1 | 0.428 | 0.034 [0.020, 0.049] | 113 | 9.8 % |
| 32B 88/png 10 s | 0.383 | 0.279 | 0.394 | 0.123 | full_K1 | 0.470 | **0.076** [0.056, 0.090] | 75 | 18.4 % |
| 4B 13.6/png 5–10 s | ≤ 0.005 | 0.149 | — | 0.084 | full_H2 | 0.149 | 0.000 | 52 | 0 % |
| 4B 88/png 5–10 s | 0.284 | 0.149 | — | 0.084 | recent | 0.299 | **0.015** [0.007, 0.025] | 116 | 5.1 % |

(The "stride or full_H2" column is stride_D2 for 32B and full_H2 for 4B.) All other network, format and deadline cells are in `e4_results.json` → `sessions`.

### 7.2 Sensitivities

| variant | 32B 88/png 10 s headroom [CI] | 4B 88/png 5 s headroom [CI] | note |
|---|---|---|---|
| known_questions_only (every policy known) | 0.076 [0.036, 0.106] over 142 sessions / 198 q | 0.000 over 121 / 160 q | 4B: all three policies identical on these 160 questions (identical inputs, flag 5) |
| recent_vs_full_known (recent vs full_K1 / full_H2 only) | 0.055 [0.038, 0.067], 234 sessions / 844 q | 0.035 [0.018, 0.049], 197 sessions / 344 q | the cleanest measured comparison |

Continuous-upload cost per hour of driving: PNG stride (D2) 251.7 MB, full 1 fps at 352×256 503.4 MB; raw 486.6 / 973.2 MB; recent 0 (it pays per question instead).

## 8. Results consistency check (6 checks)

| # | check | outcome |
|---|---|---|
| 1 | cross-check vs committed | PASS. K1 39.53 % and K3 38.34 % match StudyR1 (845, `study_r1_results_h100nvl.json`). D2 39.57 % (839) vs RH4-reported D2 − K1 −0.24 pp [−2.80, +2.41] on 839 paired: consistent. C1 31.48 % = StudyDevAcc 31.5 %. U old-frame count matches the D11 manifest on 845/845. No ratio > 2×. |
| 2 | physical plausibility | PASS. Implied prefill: 4B H100 12.3k tok / 1.00 s ≈ 12.3k tok/s; 32B 12.3k / 3.03 s ≈ 4.1k tok/s; Orin 12.3k / 17 s ≈ 725 tok/s, consistent with StudyD4-orin's ~1.2 ms/token TTFT (1.13–1.25). None faster than the committed curves, because the curves are those measurements. WARM D2 is labelled and kept separate. |
| 3 | distribution sanity | PASS with note. Per-config utility is identical across deadlines where compute + upload sits well below 5 s (e.g. cl-4B-RECENT 0.284 at 5 and 10 s), as expected for deadline-insensitive configurations. The 160-question all-known subset gives three identical 4B utilities (0.444), explained by identical inputs (167/167 identical answers), not caching. |
| 4 | definition audit | PASS with note. RECENT / RICH / U / D2 are the ledger cells (R1.K3, R1.K1, D11 U, RH4.D2). "Session" = one S-EMBER video, the same as StudyRH4's session notion. "Per-type" is new to this study (category × qt bin). |
| 5 | claim linkage | Bears on the coupling claim (joint representation × placement × timing beats decomposed policies): an *upper bound* on joint-over-decomposed value under measured latency. It does not show that a realisable policy reaches it. Location rarely matters at these deadlines (device too slow). Q(f, w) does not vary by node (FORMULATION §Scoping); here only model, representation and latency vary by node. |
| 6 | proxy validity | Flagged. (a) Device outcomes use H1/H2 answers as a proxy for the device runtime: agreement 84.7 / 82.6 %, below 90 % (flag 2). (b) "History held at the cloud uploads only new frames" is an assumption, not measured. (c) Video-format latency (R1) and image-format latency (H5, D10) share one cold32 curve (flag 3). (d) The oracle is an upper bound. |

## 9. Observations (data only)

1. With measured latency only, the oracle beats the best per-type policy by **0.143 [0.120, 0.166]** at 88 Mbit/s / PNG / 5 s and **0.169 [0.145, 0.195]** at 10 s; raw at 10 s, **0.200**. The per-type policy recovers only 0.026 (5 s) or −0.009 (10 s) of utility over static.
2. At 13.6 Mbit/s, headroom is 0 up to 5 s (≈ noise) and 0.067 at 10 s. At 5 Mbit/s it is ≤ 0.013. With 1 s deadlines, headroom is ≈ 0 everywhere.
3. cl-32B-D2 is the best static configuration in most low-bandwidth or short-deadline cells. cl-4B-RECENT wins at 88/png 5 s, and cl-32B-RICH at 88 Mbit/s 10 s.
4. Classes:
   - At 88 Mbit/s 10 s, the oracle-beats-per-type questions split across capability (50), evidence (55), representation (14) and interaction (24).
   - At 5 s they are mostly interaction (101 of 121).
   - At low bandwidth they are mostly representation (RICH ↔ D2).
   - Location: 0 in every cell.
5. The noise floor is 0.15 – 0.44 pp. Every headline headroom is 30–100× larger. The 13.6/png 5 s and 88/png 1 s headrooms are indistinguishable from noise.
6. Sessions:
   - With retention fixed per session, the ex-post best policy beats the best single policy by 0.034–0.076 (32B) and 0.015 (4B) at 88 Mbit/s.
   - Among sessions of the same type, the best policy differs from that type's modal best in 5–18 % of sessions.
   - full_K1 is the best single 32B policy in every primary cell shown.
7. Robust to the 6 D2 gaps (n = 839) and to the all-known subset. Larger with warm D2 (+0.011 to +0.063 over primary in the cells of §4.3) and with extrapolation (+0.014 to +0.103 in §4.4; +0.026 / +0.030 for the 88/png headline).

## 10. Interpretation (inference, labelled)

- **There is substantial upper-bound value in per-question switching at 88 Mbit/s and 5–10 s deadlines, and per-type routing captures almost none of it.**
  - The gap is not noise, since real arms disagree 10–40× more than near-identical ones.
  - Whether it is *capturable* is untested. The oracle uses correctness, and nothing available before the question has been shown to predict it.
- **At constrained uplinks (≤ 13.6 Mbit/s) and short deadlines, the answer is a single configuration (32B on D2, the cheapest upload).** There is little to switch between, because almost nothing else delivers.
- **Retention state matters at the session level less than per-question switching does.** Session headroom is a quarter to a half of question-level headroom, and the clean recent-vs-full comparison gives 0.055 (32B, 10 s).
- **Location is not a lever in this data**, because Orin's 4B is ~17 s at these prompt lengths.
- **U, the configuration with most evidence, is the least measured (> 75 % UNKNOWN).** Its value in the headroom is therefore understated in the primary tables. The extrapolated table moves the 88/png headline by ≤ 0.03 (raw 5 s by +0.10).

## 11. Files

- `experiments/orchestration/study_e4_counterfactual.py`
- `results/orchestration/study_e4/e4_results.json`
- `results/orchestration/study_e4/e4_frame_bytes.json`
- `reports/study_e4_counterfactual.md`
