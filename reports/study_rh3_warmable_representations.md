# StudyRH3 — accuracy of warmable history representations (H100, vLLM)

**Stack:**
- vLLM 0.31.0+cu129 (venv `~/.venvs/fm-switching-vllm`, torch 2.13.0+cu129), FlashAttention 3, CUDA graphs, gmu 0.90, max_model_len 32768.
- Qwen3-VL-32B-Instruct @0cfaf481 on h100nvl GPU 3; no foreign process on the GPU during the run.
- Builder and analysis: original `.venv` (transformers 5.10.2), CPU.
- All numbers are vLLM numbers. R1 (K1, K3) and RH1 (H1a, H1b) were run on the same stack, so no cross-stack caveat applies.

**Pre-registration:** research/EXPERIMENTS.md, StudyRH3, written 2026-10-19 before any GPU run.

**Run:** Part 0 13:11–13:14; cells A/B/C 13:14–14:46 (A 15.2 min, B 36.0 min, C 36.3 min). The estimate was 1.36 h; the actual time was 1.5 h.

## Part 0 — can a one-video history be kept warm? **No.**

**Server:** R1's server (video input, one video per prompt) with `--enable-prefix-caching --enable-prompt-tokens-details`. KV capacity 64,624 tokens.

**Procedure:**
- Five questions: the first five in R1 order with an uncapped 1 fps RICH input.
- For each, three requests:
  - **BASE:** R1's request cut to its first n−10 frames.
  - **Control:** BASE again.
  - **EXT:** the full n-frame request, with the same text and R1's own pixels for the shared frames.
- This is the most cache-friendly case possible. In a live system the processor's total-pixel budget would also rescale every frame as the video grows.

| question | frames BASE→EXT | BASE prompt / cached | control repeat cached | EXT prompt / **cached** | common token-id prefix BASE vs EXT | tokens before the video |
|---|---|---|---|---|---|---|
| 0CBF46C2FA | 164→174 | 11,519 / 0 | 11,504 (99.9%) | 12,219 / **0** | 11,429 | 3 |
| cc04a5dca7 | 88→98 | 10,310 / 0 | 10,304 (99.9%) | 11,460 / **0** | 10,119 | 3 |
| 7DFCAA7D06 | 240→250 | 11,941 / 0 | 11,936 (99.9%) | 12,431 / **0** | 11,709 | 3 |
| 7a8ab842e0 | 206→216 | 12,240 / 0 | 12,224 (99.9%) | 12,830 / **0** | 12,103 | 3 |
| D4918FA56B | 226→236 | 11,115 / 0 | 11,104 (99.9%) | 11,605 / **0** | 11,023 | 3 |

**What this shows:**
- Prefix caching works: the identical repeat is served from cache down to the last partial 16-token block.
- Extending the video reuses **nothing**, even though the first 10–12k token ids are identical.
- vLLM keys every cache block that contains part of a multimodal item on that item's hash. A longer video is a different item, so reuse stops at the video start, which is token 3, inside the first block. This matches the pre-registered expectation.

**Consequence:** a one-video history (K1, K3, H1a, H1b) cannot be kept warm by appending. Each escalation is a cold prefill of the whole video. Warm-state continuity needs a separate-image history, which is what Parts A–C measure.

## Decision table

Accuracy is over the same 845 questions, paired.

**Definitions used in the table:**
- **History tokens:** prompt tokens minus the same chat with no history (R1's question text only; mean 142). This is what a device keeps warm.
- **Warm devices:** floor(threshold × KV / mean history tokens), using RH2's footprint rule. Thresholds are 0.55× (clean tails) and 0.85× (degraded tails). KV is 65,280 tokens for bf16 and 129,280 for FP8.
- **Append-only:** reusable prefix after a 10 s step. This is the post-hoc check below; it was **not pre-registered**.

| cell | representation | mean history tok | accuracy [Wilson 95%] | Δ vs K1 [95% CI] | RECENT-miss (97) / cover (748) | warm devices bf16 0.55× / 0.85× | FP8 0.55× / 0.85× | append-only? |
|---|---|---|---|---|---|---|---|---|
| K1 | RICH, one video (R1) | 12,127 | 39.53 [36.3, 42.9] | — | 42.3 / 39.2 | 2 / 4 | 5 / 9 | no (Part 0) |
| K3 | RECENT 120 s, one video (R1) | 12,113 | 38.34 [35.1, 41.7] | −1.18 | 24.7 / 40.1 | 2 / 4 | 5 / 9 | no |
| H1a | RICH 50%, one video (RH1) | 6,062 | 32.54 [29.5, 35.8] | −6.98 [−9.42, −4.53] | 32.0 / 32.6 | 5 / 9 | 11 / 18 | no |
| H1b | RICH 25%, one video (RH1) | 3,048 | 30.06 [27.1, 33.2] | −9.47 | 24.7 / 30.7 | 11 / 18 | 23 / 36 | no |
| **A** | R5/RH2 images, 1 fps, 160×128, ≤640 | **5,594** | **30.30 [27.3, 33.5]** | **−9.23 [−12.46, −6.07]** | 33.0 / 29.9 | **6 / 9** | **12 / 19** | **yes**: 93% reusable, median 220 new tokens per 10 s |
| **B** | R1's RICH frames as images, 288×224 | **12,612** | **40.24 [37.0, 43.6]** | **+0.71 [−2.27, +3.56]** | 46.4 / 39.4 | **2 / 4** | **5 / 8** | **only while the session is ≤ 256 s**; past the 256-frame cap the uniform re-spacing changes almost every frame (42% of questions reuse ≤ 10%) |
| **C** | last 120 s at 1 fps, 384×288, + 1 per 8 s older at 160×128 | **12,725** | **39.88 [36.6, 43.2]** | **+0.36 [−2.65, +3.26]** | 27.8 / 41.4 | **2 / 4** | **5 / 8** | **no**: the 120 s window slides, so the median reusable share is 4% (13.3k tokens recomputed per escalation) |

**Pre-registered contrasts** (video-clustered bootstrap, 2,000 resamples, seed 0):

| contrast | overall | RECENT-miss (97) | RECENT-cover (748) | DiD (miss − cover) |
|---|---|---|---|---|
| A − K1 | **−9.23 [−12.46, −6.07]** | −9.28 [−17.31, −1.19] | −9.22 [−12.65, −5.77] | −0.05 [−8.25, +8.57] |
| B − K1 | +0.71 [−2.27, +3.56] | +4.12 [−4.40, +13.04] | +0.27 [−2.80, +3.24] | +3.86 [−4.93, +13.30] |
| C − K1 | +0.36 [−2.65, +3.26] | **−14.43 [−24.47, −4.65]** | +2.27 [−0.82, +5.28] | **−16.71 [−26.87, −6.25]** |
| C − K3 | +1.54 [−1.08, +4.13] | +3.09 [−4.76, +11.71] | +1.34 [−1.46, +4.01] | +1.76 [−6.39, +10.29] |

**Secondary contrasts** (named in the pre-registration; the CIs for these are in the results JSON):

| contrast | difference (pp) | 95% CI |
|---|---|---|
| B − A | +9.94 | [+7.38, +12.50] |
| C − B | −0.36 overall | — |
| C − B, RECENT-miss | −18.56 | [−28.16, −9.47] |
| A − H1a | −2.25 | [−5.25, +0.49] |
| A − H1b | +0.24 | [−2.70, +3.30] |

## What this means

1. **The separate-image format costs nothing at K1's frames and tokens.**
   - B (same frames and timestamps as K1, ≈12.6k tokens) scores 40.24% vs 39.53%: +0.71 [−2.27, +3.56], with 72% answer agreement.
   - Temporal merging and timestamp tokens, which only the video path has, do not buy accuracy here.
   - The representation itself is not the problem.
2. **RH2's latency format (A) is 9.2 pp below K1.** This holds evenly across RECENT-miss and RECENT-cover questions (DiD −0.05).
   - A uses the RH2 image format at 160×128 and 1 fps, about 5.6k history tokens.
   - It sits at H1b's level (30.06%, 3.0k tokens) and slightly below H1a (32.54%, 6.1k; −2.25 [−5.25, +0.49]).
   - At about 22 tokens per frame, many low-resolution frames lose as much as a halved or quartered video.
   - **The RH2 latency surface therefore describes a representation that is 9 pp less accurate than R1's cloud.**
3. **C (recent-dense plus sparse-old) matches K1 overall but is a RECENT construction.**
   - It loses 14.4 pp where RECENT misses the evidence (DiD −16.7) and is indistinguishable from K3 (+1.54 [−1.08, +4.13]).
   - The sparse 1-per-8-s old frames at 160×128 recover little of the old evidence.
   - Of the 19 questions whose kept frames miss the evidence, C answers 10.5% correctly.
4. **Accuracy and warmability pull against each other.** Among the three image formats:
   - Only A is strictly append-only, and A is the least accurate.
   - B reaches K1's accuracy but stops being append-only once a session passes 256 s. That is 373 of 845 questions in this pool, and every long session.
   - C is not append-only at all.
   - Nothing measured here is both K1-accurate and warmable for long sessions. An append-only format at B's frame density and resolution would hit the 256-frame cap or the 32k context. Its history would grow at 65 tokens per frame.
5. **Warm capacity at K1-level accuracy is 2 devices (bf16) or 5 (FP8) for clean tails.**
   - That compares with 6 and 12 at A's accuracy.
   - FP8 KV (RH1: parity, −0.83 pp) doubles every count in the table at no measured accuracy cost.

**For the controller:**
- The warm-state lever, as built in RH2, buys sub-second escalations at a 9-pp accuracy discount relative to a cold full-history escalation. Each cold escalation costs about 4 s of prefill at 12–17k tokens (RH2 calibration: 0.34 s + 0.244 ms/token; measured here as B/C sequential latency of 3.1–3.9 s).
- To keep both the accuracy and the warmth, a long-session append-only format at about 65 tokens per frame is needed, with a fixed stride rather than uniform re-spacing. This has not been measured; it is a candidate next cell, not run.

## Mechanism verification (Steps 1–5 written before the sweep; results added after)

**Step 1 — causal chain.**
- Warm-state continuity lowers escalation latency only if the cloud can keep a device's history in the prefix cache and extend it without recomputing it (FORMULATION.md: warm state, refresh and reconstruction cost).
- That requires a history representation whose prefix is unchanged when new frames arrive. Part 0 tests this for R1's one-video format.
- A warmable representation has two costs:
  - its per-device token footprint, which sets how many devices fit in KV (RH2's footprint rule);
  - its fidelity, the accuracy the 32B model reaches with it (FORMULATION.md: representation-dependent semantic loss).
- RH3 measures the fidelity side for three separate-image representations at two footprints. The controller's choice can then be priced on accuracy and on warm capacity from the same representation.

**Step 2 — instantiate each link.**

| causal link | implementing quantity | value / range in this run | varies as expected? | evidence |
|---|---|---|---|---|
| one-video extension invalidates the cache | `cached_tokens` of EXT after BASE, vs the common token-id prefix | EXT 0 / 0 / 0 / 0 / 0 vs common prefix 10.1k–12.1k; control 99.9% | yes: the control hits, the extension does not | Part 0 table |
| representation → footprint | history tokens per cell | A 5,594; B 12,612; C 12,725 | yes (A ≈ 0.44× B; B ≈ C by design) | 2,535/2,535 requests: vLLM prompt_tokens == HF count |
| representation → accuracy | per-question correctness | 30.30 / 40.24 / 39.88% | yes (not constant; answer agreement 64–73% with K1) | results table |
| footprint → warm devices | floor(thr × KV / history tokens) | 2–6 (bf16 0.55×) … 5–19 (FP8) | yes | warm-device columns (derived, not measured) |
| representation → appendability (post hoc) | reusable prefix after 10 s | A 93%, B 52% (bimodal), C 19% | yes | post-hoc table |

No link is ABSENT or CONSTANT.

**Step 3 — trace of one unit.** Question 2EA41E4F62, qt = 379 s, gold A. Batched records:

| cell | images | sizes | timestamps | evidence covered | HF expected = vLLM prompt tokens | completion | prediction | latency (concurrency 8) |
|---|---|---|---|---|---|---|---|---|
| A | 380 | 160×128 | 0, 1, 2 … 378, 379 | yes | 8,529 = 8,529 | 2 | D ✗ | 5.6 s |
| B | 256 | 288×224 | 0, 1, 3 … 378, 379 (RICH cap) | yes | 16,812 = 16,812 | 2 | C ✗ | 21.3 s |
| C | 154 | 33 × 160×128 (0, 8 … 256) + 121 × 384×288 (259 … 379) | | yes | 14,221 = 14,221 | 2 | C ✗ | 14.7 s |

No budget binds: prefix caching is OFF, prompts are ≤ 17.1k against the 32,768 limit, and the image count is ≤ 640. The outcome is correctness only; latency is not a measured quantity in A–C.

**Step 4 — negative controls.**
- **Part 0:** the identical repeat hit 99.9% on all 5 questions. Caching was on, so EXT's zero is the mechanism and not a disabled cache.
- **Parts A–C:** exact prompt-token parity on every request shows the histories differ as specified.
- No zero-history cell was pre-registered, so a "no history" accuracy floor is not measured here.

**Step 5 — alternative explanations.**
- **B ≈ K1.** This could mean that temporal merging and timestamps neither help nor hurt. It could also mean that their loss is offset by B's 4% more tokens or by the header. The two are not separable here, but the difference is null either way.
- **A < K1.** Two explanations fit:
  - per-frame resolution: 160×128 is a 20-token image;
  - frame density without resolution: 1 fps vs RICH's ≤256 frames.
- A − H1b ≈ 0 at 1.8× the tokens suggests that spending tokens on many tiny frames is no better than spending fewer on larger ones. RH3 does not vary A's resolution, so this is not established.
- **C vs B.** The difference on RECENT-miss questions mixes frame selection with resolution. The C ≈ K3 result says selection dominates.

## Results consistency check

1. **Cross-check against committed measurements.**

   | quantity | this run | prior | source | ratio | agree? |
   |---|---|---|---|---|---|
   | tokens per 160×128 image | 22 (20 + 2) | 22 | R5 probe / RH2 | 1.00 | agree |
   | K1 / K3 / H1a / H1b accuracy | reused, not re-run | 39.53 / 38.34 / 32.54 / 30.06 | R1, RH1 results JSON | — | same files |
   | KV capacity, video server with prefix caching | 64,624 | 64,624 | RH1 bf16 server | 1.00 | agree |
   | KV capacity, image server (640 images, no prefix caching) | 62,944 | 65,280 | RH2 image server (prefix caching ON) | 0.96 | agree; the warm-device projection uses 65,280 as pre-registered |
   | A history at question time | 5,594 | ≈4.7k mean resident history | RH2 | 1.19 | agree; RH2's figure is a time-average over the replay, while question-time histories are later and longer |
   | sequential latency at 12.6k (K1-like) | B 3.4–3.9 s at 15.5–16.8k | K1 3.4–3.8 s at 11.7–12.7k | R1 timing5 | ≈1 | agree; images vs video preprocessing, see 2 |

2. **Physical plausibility.**
   - RH2's isolated calibration predicts 0.341 + 0.244 ms × tokens: B at 16.8k → 4.4 s (measured 3.8–3.9 s); C at 14.2k → 3.8 s (measured 3.1–3.3 s); A at 8.6k → 2.4 s (measured 1.9 s).
   - These are 13–20% faster than the calibration and well under 2×.
   - Prefix caching was OFF for A–C, so no cache artifact is possible.

3. **Distribution sanity.**
   - Prompt tokens per cell: A 298–14,383 (median 5,256); B 602–17,074 (median 15,218; mean below median because short sessions have fewer than 256 frames); C 930–16,467 (median 13,802).
   - Answer agreement with K1 is 64–73%, with no suspicious identity.
   - There were 0 unparsed answers and 0 length finishes; completion is 2 tokens throughout.

4. **Definition audit.**
   - **A:** R5's frame cache, size, orientation rule, 640-image cap and header format. The tag `RH3_A` replaces the cell tag.
   - **RECENT-miss split:** R1's RECENT `evidence_covered` (97/748), as in R1 and RH1.
   - **evidence_covered:** StudyO's definition.
   - **History tokens:** defined above and new to RH3. RH2's "mean history tokens" is a replay time-average of the same object, not the question-time value. The two are not the same number (see 1).
   - **"Warmable":** used by the spec for all three formats. The post-hoc check shows that B is warmable only up to 256 s and C is not warmable.

5. **Claim linkage.**
   - **C1** (fidelity is representation- and workload-dependent): supported. Representations differ by up to 9.9 pp at fixed workload, and the B-vs-C difference is concentrated on old-evidence questions.
   - **C5** (joint representation × placement × timing): bears on it. The warm-capacity and accuracy prices now come from the same representation, and they conflict: the warmable format is the inaccurate one.
   - **C4** (physical inertia): Part 0 adds that one-video histories have no warm path in vLLM at all.

6. **Proxy validity.**
   - Warm-device counts are a **projection** from RH2's footprint rule applied to question-time history sizes, not a latency measurement. They are labelled as derived.
   - `evidence_covered` saturates for A and B (843/845 and 845/845), so it cannot explain A's loss.
   - The post-hoc reusable-prefix fraction is computed from the selection rules (the B rule reproduces the manifest for 845/845 questions). Its premise, that vLLM reuses a block only while every earlier image is identical, is the behaviour RH2 measured. It is not re-measured here.

## Deviations and notes

- **Post-hoc analysis.** The reusable-prefix analysis was added after seeing that B and C are not append-only by construction. It is labelled as such and changes no pre-registered number.
- **Prompt wording.** R1's question text ("Watch the video carefully…") was kept verbatim for A–C, as specified, although the history is images.
- **Headers.** B's and C's headers describe their sampling (pre-registered); A uses R5's header format.
- **640-image cap.** It truncates 7/845 questions in A (0.8%, under the 10% STOP). Two of them lose the evidence; both answered wrong.
- **Size choices.**
  - B is 288×224 (aspect 1.29 vs 4:3), 65 tokens per image, mean prompt 12.75k.
  - C's recent frames are 384×288 (exact 4:3), 110 tokens per image, mean prompt 12.87k.
  - Both are 4–5% above K1's 12.27k, as fixed in the pre-registration.
- **Build.** The CPU input build was restarted once, from 2 completed questions, after torch thread oversubscription. Inputs are unaffected; the restart resumes per question.

## Files

- `experiments/sember/study_rh3_inputs.py`: builder (.venv).
- `experiments/sember/study_rh3_warmable.py`: Part 0 and cells A–C (vLLM venv).
- `experiments/sember/study_rh3_analyse.py`: analysis.
- `results/sember/study_rh3/`:
  - `study_rh3_inputs_manifest.jsonl.gz` (423 KB)
  - `study_rh3_part0_h100nvl.json`
  - `study_rh3_parity_h100nvl.json`
  - `study_rh3_requests_h100nvl.jsonl.gz` (207 KB)
  - `study_rh3_run_meta_h100nvl.json` (server flags, KV, FA version, timing, estimate)
  - `study_rh3_results_h100nvl.json`
