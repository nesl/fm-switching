# StudyE10a-full: JPEG parity on all 845 S-EMBER questions

E-id: StudyE10a-full (`research/EXPERIMENTS.md`, pre-registered 2026-11-11). Host: h100nvl **GPU 2**. Batched; no latency claim. **StudyE10a's verdict (JPEG NOT acceptable at n = 100, 94 % agreement) stays on record unchanged; this is a new, larger, pre-registered test with its own rule.**

## 0. Mechanism verification (recorded BEFORE the sweep)

**Step 1, causal chain.**
- FORMULATION's physical component: transfer cost scales with payload bytes. JPEG q88 frames cut the S-EMBER request about 6× (E10a Job A: RECENT 33.4 → 5.5 MB; RICH 34.9 → 6.2 MB).
- JPEG is usable only if the model's answer does not depend on the lossy residual. Encoding changes pixel values (block artefacts, 4:2:0 chroma), so the vision encoder sees different input. The question is whether that changes accuracy on the full question set, for both the 120-s RECENT window (K3) and the up-to-256-frame RICH history (K1).

**Step 2, instantiate each link.**

| link | quantity | value | varies? | evidence |
|---|---|---|---|---|
| JPEG cuts bytes | video data-URL size, JPEG / PNG | about 0.17–0.18 (Job A) | yes | `e10a_sizes.json`; per-row `video_url_chars` |
| JPEG changes pixels | lossy q88 re-encoding of the final-size frames on the client | by construction; E10a changed 6 / 100 letters | yes | E10a |
| identical tokens | prompt tokens = R1's processor count | STOP on any mismatch | to be confirmed per row | rows |
| model output responds to input | R1 K1 / K3 accuracy | 0.383 (K3) / K1 per R1, both well above grey | yes | R1, F1 grey |

**Step 3, trace one unit.** One K3 and one K1 request are reported from the rows: bytes, tokens vs R1, letter vs R1.

**Step 4, negative control.**
- PNG-to-PNG reproduction was shown by StudyF2: K3's PNG request reproduced K3's letters on 167 / 167.
- E10a's Nexar PNG re-send was identical to D14 on 1,600 / 1,600 on this stack.
- So disagreement with R1 is the encoding plus a near-zero rerun term. A PNG re-send of all 1,690 requests is not repeated (time).

**Step 5, alternative explanation.**
- An accuracy difference could come from batch nondeterminism rather than JPEG. Step 4's evidence bounds that near 0.
- An accuracy null could come from a model that ignores the frames. R1's K1 > K3 gap and the grey floor show that it does not.

**Pre-registered rule (from the EXPERIMENTS row, unchanged).** JPEG is acceptable for S-EMBER iff, for EACH of K3 and K1, the paired accuracy difference (JPEG minus PNG, video bootstrap 2,000, seed 0) has a 95 % CI inside [−2, +2] pp. Letter agreement is reported but is not the criterion.

**Stack.**
- 32B-I @0cfaf481, vLLM 0.31.0, R1's server flags + `--mm-processor-cache-gb 0` + prompt-token details.
- Prefix caching OFF.
- R1's body (seed 42, temperature 0, max_tokens 512) with each final-size npz frame JPEG q88-encoded on the client, exactly as E10a's `sember32` stage.
- Concurrency 8.

## 1. Run (2026-11-11, 21:07–22:19)

- 1,690 requests (K3 845 + K1 845), all OK: 0 errors, 0 retried, 0 still failed.
- Prompt tokens equal R1's processor count on **845 / 845** in each cell (the STOP check never fired); cached tokens 0 on every row (prefix caching off, processor cache 0 — cold, as labelled).
- Unparsed letters: 0 (JPEG) and 0 (R1 PNG) in both cells.
- Median video data-URL: K3 7.3 MB, K1 8.0 MB (JPEG), vs the PNG request medians from E10a Job A (K3 33.4 MB).
- Subset control: on E10a's 100 questions, this run's K3 letters equal E10a's `sember32` JPEG letters on **100 / 100** (same stack, same encoding, rerun).

**Step 3, one traced unit** (question 003969ab…, video 690844827311979, 48 frames — a short video, so RECENT and RICH hold the same frames): K3 and K1 each sent a 3.86 M-character JPEG video URL; prompt tokens 11,801 = R1's 11,801; letter A (correct B) in both cells, finish `stop`, cached 0.

## 2. Result

| cell | PNG acc (R1) [video CI] | JPEG acc [video CI] | JPEG − PNG, pp [95 % CI] | inside ±2 pp? | letter agreement | changed letters: JPEG right / PNG right / both wrong |
|---|---|---|---|---|---|---|
| K3 (RECENT) | 38.34 % [34.8, 41.9] | 39.17 % [35.5, 42.7] | **+0.83 [−0.24, +2.01]** | **no** (upper +2.007) | 94.1 % (795 / 845) | 16 / 9 / 25 |
| K1 (RICH) | 39.53 % [36.1, 43.0] | 38.93 % [35.4, 42.5] | **−0.59 [−2.14, +0.84]** | **no** (lower −2.143) | 91.2 % (771 / 845) | 17 / 22 / 35 |

n = 845 questions, 234 videos per cell; video bootstrap 2,000, seed 0.

Per category (accuracy PNG → JPEG), largest moves only: K3 spatial reasoning 15.4 → 17.6 %, object comparison 36.3 → 39.6 %, counting 27.3 → 25.5 %; K1 visual-detail recall 58.0 → 55.2 %, temporal ordering 45.6 → 47.8 %, sequential action 45.1 → 43.1 %. Every category moves by ≤ 3.3 pp (n 90–143 each); no category is singled out.

## 3. Verdict (pre-registered rule)

**JPEG q88 is NOT acceptable for S-EMBER under the pre-registered rule.** Neither cell's 95 % CI lies inside [−2, +2] pp: K3's upper bound is +2.007 pp and K1's lower bound is −2.143 pp.

What this does and does not show:
- Both CIs contain 0, and the point estimates have opposite signs (+0.8, −0.6 pp). There is **no evidence that JPEG lowers accuracy**; the study cannot rule out a ±2 pp effect, which is what the rule asks for.
- Both misses are narrow (0.01 pp and 0.14 pp). The rule is applied as written; it is not relaxed after the fact.
- Letter agreement (91–94 %) is reported only, as registered: about 6–9 % of answers change, mostly between wrong answers (25 / 50 and 35 / 74).
- StudyE10a's n = 100 verdict (NOT acceptable) stands, and this full test agrees with it.

## 4. Consistency protocol (6 checks)

1. **Pre-registered and unchanged.** Rule, cells, encoding and bootstrap as in the EXPERIMENTS row; verdict applied as written.
2. **Controls pass.** Token parity 1,690 / 1,690 with R1; E10a subset 100 / 100 identical letters; PNG rerun term bounded by F2 (167 / 167) and E10a's Nexar re-send (1,600 / 1,600).
3. **Reproduces committed numbers.** The E10a subset (100 questions) reproduces E10a's JPEG letters 100 / 100; the PNG arm is R1's committed batched rows (845 per cell, no errors), not a rerun.
4. **Complete data.** 845 / 845 per cell, 0 failed, 0 unparsed.
5. **Caching state labelled.** Prefix caching off, processor cache 0, cached tokens 0 on every row — all cold. The PNG side is R1's committed batched rows, used as recorded.
6. **Scope.** Accuracy only, 32B-I, S-EMBER; batched on H100 GPU 2; no latency or transfer-time claim.
