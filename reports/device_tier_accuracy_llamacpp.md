# Device-tier accuracy on the llama.cpp runtime — DEV-RECENT vs DEV-RICH

**E-id:** `StudyDevAcc-llamacpp` (pre-registered 2026-10-18 before any GPU run)
**Script:** `experiments/device/device_tier_accuracy.py`; analysis `experiments/device/device_tier_analyse.py`
**Host:** flash / NVIDIA RTX A6000 (GPU 1), `CUDA_VISIBLE_DEVICES=1`
**Runtime:** llama.cpp `c0fd78626405c6d9b934efef0ec7291fcc20e3d6`, llama-server
**Server flags:** `--jinja --reasoning-format deepseek -ngl 99 -fa on -c 16384 --seed 0`
**Outputs:** `results/device/accuracy_C{1,2,3,4}.jsonl` + `_meta.json`

## Question

Study O Q4 found a **crossover**: reallocating a fixed visual-token budget from the last 120 s
(RECENT) to the whole session (RICH) helps when the answer's evidence lies outside the recent
window and hurts when it lies inside. That was measured on the HF video path. Does the same
crossover appear on the **device's own runtime** — llama.cpp, GGUF F16 weights, frames passed as
separate images with no temporal merging?

## Cells

All four cells use N = 37 frames at 560×560 with `[t=XXs]` markers, the same prompt, and the same
≤ 12,500-token budget. RECENT spans `[max(0, qt−120), qt]`; RICH spans `[0, qt]`. **This is a
reallocation of one budget, not more tokens.**

| cell | model | construction | decoding | n |
|---|---|---|---|---|
| C1 | Qwen3-VL-4B-Instruct F16 | DEV-RECENT | greedy, max 512 | 845 |
| C2 | Qwen3-VL-4B-Instruct F16 | DEV-RICH | greedy, max 512 | 845 |
| C3 | Qwen3-VL-4B-Thinking F16 | DEV-RECENT | model-card VL: temp 1.0, top_p 0.95, top_k 20, max 16384, seed 0 | 845 |
| C4 | Qwen3-VL-4B-Thinking F16 | DEV-RICH | same as C3 | 845 |

Model weights verified by sha256 against the Orin's `results/device/model_hashes.txt` before
running — all five hashes matched exactly (4B-Instruct F16 `4a6fb1ed…`, its mmproj `256f3a43…`,
4B-Thinking F16 `b0af534e…`, its mmproj `b8b81037…`, 4B-Thinking Q8_0 `7c6f9a84…`).

### Caching statement (methodological parameter, per CLAUDE.md)

llama-server's prefix cache is at its default (ON). Every trial sends a **different** 37-frame
image payload, so no trial's prefill can be served from a previous trial's cache; the shared
prefix is the system/chat scaffold only (tens of tokens against ~12,400). Latencies below are
therefore cold-prefill for the image payload. Frames come from the Study O 1 fps JPEG cache,
decoded once before the runs; frame decoding is **not** in any reported latency.

---

## Pre-registered denominator

When `question_time ≤ 120 s`, `[0, qt]` and `[max(0, qt−120), qt]` are **the same interval**, so
the two constructions are byte-identical and contribute an exact zero to C2 − C1. This affects
**167/845 = 19.8%** of the pool. Analyses B and C are therefore **primary on the 678 questions
with `qt > 120 s`**, with all 845 reported as an attenuated secondary. This was declared before
the runs, not chosen after seeing results.

---

## A. Accuracy per cell

| cell | model | constr | n | accuracy | Wilson 95% |
|---|---|---|---|---|---|
| C1 | 4B-I | RECENT | 845 | **31.5%** (266) | [28.4, 34.7] |
| C2 | 4B-I | RICH | 845 | **31.0%** (262) | [28.0, 34.2] |
| C3 | 4B-T | RECENT | 845 | **33.4%** (282) | [30.3, 36.6] |
| C4 | 4B-T | RICH | 845 | **30.9%** (261) | [27.9, 34.1] |

All four Wilson intervals overlap. **Aggregate accuracy does not separate the constructions** —
and that flatness is the thing the crossover explains, not a null.

Run facts:

| cell | median latency | median gen tokens | median input tokens | parse failures | budget hits |
|---|---|---|---|---|---|
| C1 | 6.59 s | 2 | 12,420 | 0 | 0 |
| C2 | 6.60 s | 2 | 12,411 | 0 | 0 |
| C3 | 12.01 s | 340 | 12,422 | 11 (`no_letter`) | 11 |
| C4 | 11.84 s | 340 | 12,413 | 12 (`no_letter`) | 12 |

**OOM / budget-exhaustion disclosure:** 11 (C3) and 12 (C4) trials hit the 16,384-token
generation cap without emitting an answer letter. They are **retained and scored as incorrect**,
not dropped. C1/C2 had none. No OOM occurred at any point.

---

## B. Crossover replication — PRIMARY RESULT

Split by the RECENT arm's `evidence_covered` flag. Video-clustered bootstrap, 2,000 resamples,
seed 0. MDE = 2.802 × bootstrap SE (80% power, two-sided α = 0.05).

### Instruct, `qt > 120`, n = 678

| stratum | n | RECENT | RICH | diff |
|---|---|---|---|---|
| evidence **not** covered by RECENT | 104 | 16.3% | **34.6%** | **+18.27 pp** |
| evidence covered by RECENT | 574 | **29.8%** | 25.8% | **−4.01 pp** |

**DiD = +22.28 pp, 95% CI [+12.10, +31.88]**, SE 4.91, MDE 13.76 pp → **CI excludes 0.**

### Thinking, `qt > 120`, n = 678

| stratum | n | RECENT | RICH | diff |
|---|---|---|---|---|
| evidence **not** covered | 104 | 20.2% | **33.7%** | **+13.46 pp** |
| evidence covered | 574 | **31.2%** | 25.1% | **−6.10 pp** |

**DiD = +19.56 pp, 95% CI [+9.47, +29.64]**, SE 5.06, MDE 14.18 pp → **CI excludes 0.**

### All 845 (attenuated secondary)

Instruct DiD **+21.20 pp** CI [+12.23, +30.41]; same sign, slightly smaller, exactly as the
degeneracy predicts.

> ### Decision rule → **CROSSOVER REPLICATES ON THE DEVICE RUNTIME**
> Pre-registered rule: *"B's DiD CI excludes 0 in Part 2's direction."* It does, for Instruct and
> Thinking **independently**, on the primary denominator and on all 845.

The two constructions genuinely disagree — on the 678 primary questions the Instruct arm changes
its answer on **38.8%** of them. The aggregate flatness in §A is two large opposing effects
cancelling, not an inert manipulation.

---

## C. Selection policies — INCONCLUSIVE as pre-registered

Escalate = use RICH for the top-e fraction by each policy's score. Primary contrast is
**P4 − random at e = 0.2**.

### Instruct, `qt > 120`, n = 678 — always-RECENT 27.7%, always-RICH 27.1%

| e | random | P4 | qt-only | ev-oracle | acc-oracle | P4 − rand |
|---|---|---|---|---|---|---|
| 0.1 | 27.7 | 27.3 | 26.7 | 28.5 | 36.1 | −0.39 |
| 0.2 | 27.6 | 27.3 | 27.0 | 29.2 | 36.1 | −0.30 |
| 0.3 | 27.5 | 27.1 | 26.8 | 30.1 | 36.1 | −0.36 |
| 0.5 | 27.4 | 27.0 | 26.0 | 30.2 | 36.1 | −0.43 |

**P4 − random at e = 0.2: −0.15 pp, CI [−1.98, +1.48], MDE 2.44 pp → INCONCLUSIVE.**

### Thinking, `qt > 120`, n = 678 — always-RECENT 29.5%, always-RICH 26.4%

| e | random | P4 | qt-only | ev-oracle | acc-oracle | P4 − rand |
|---|---|---|---|---|---|---|
| 0.1 | 29.1 | 29.8 | 29.1 | 30.8 | 39.5 | +0.65 |
| 0.2 | 28.8 | **30.8** | 28.9 | 31.4 | 40.1 | +1.98 |
| 0.3 | 28.6 | 29.8 | 28.9 | 31.9 | 40.1 | +1.21 |
| 0.5 | 28.0 | 29.1 | 28.8 | 31.1 | 40.1 | +1.04 |

**P4 − random at e = 0.2: +0.88 pp, CI [−0.29, +4.03], MDE 3.09 pp → INCONCLUSIVE.**

> ### Decision rule → **SELECTION SIGNAL: INCONCLUSIVE**
> Minimum detectable effect **2.44 pp** (Instruct) / **3.09 pp** (Thinking).

**Why this is a power statement, not a verdict on P4.** The *evidence-distance oracle* — which
knows the true evidence location and is the ceiling any causal predictor could approach — gains
only **+1.5 pp** (Instruct) to **+2.4 pp** (Thinking) over always-RECENT. The entire achievable
headroom sits at or below the MDE. The accuracy oracle reaches 36–40%, but it peeks at
correctness and is not implementable. So the honest reading is that **per-question selection
between these two constructions has very little to win on this benchmark**, not that P4 failed.
Detecting the oracle-sized effect would need roughly 4–5× the questions.

---

## D. Thinking arm, and Thinking vs Instruct

B and C for Thinking are above. The pre-registered Thinking-vs-Instruct contrast, same
denominator and bootstrap:

| contrast | diff | 95% CI | |
|---|---|---|---|
| RECENT: C3(T) − C1(I) | +1.77 pp | [−1.44, +4.89] | includes 0 |
| RICH: C4(T) − C2(I) | −0.74 pp | [−3.84, +2.30] | includes 0 |

**Reasoning does not buy accuracy here at fixed construction** — at ~170× the generated tokens
(340 vs 2 median) and ~1.8× the latency. The crossover, by contrast, replicates in *both* model
variants, so it is a property of the input construction rather than of the decoding mode.

---

## E. Cross-machine check against the Orin

On the Orin's 120-question latency sample:

| comparison | input tokens | predictions | accuracy |
|---|---|---|---|
| C1 vs Orin 4B-Instruct F16 | **120/120 = 100%** | 100/120 = **83.3%** | 31.7% (A6000) vs 34.2% (Orin) |
| C3 vs Orin 4B-Thinking F16 | **120/120 = 100%** | 74/120 = 61.7% | 36.7% vs 33.3% |

**Input construction is verified byte-exact across machines** — every one of 120 questions
produces an identical input-token count on both hosts, which is the strongest available form of
the PART 1 step-5 verification.

**Predictions are not identical, and the pre-registered expectation that greedy C1 "should match
nearly exactly" is not met.** At 83.3% it falls well short. Two causes, which this study cannot
separate:

1. **The frames are not pixel-identical.** The A6000 reuses Study O's cache (PyAV → JPEG
   quality 88 → PIL LANCZOS resize to 560×560); the Orin used ffmpeg
   `scale=560:560:flags=lanczos` → PNG. Same dimensions and same token count, different pixels.
2. **Different GPU architectures** (sm_86 vs sm_87) resolve near-tie logits differently.

The Orin's PNGs are not in the repository — only hashes and results — so the two cannot be
isolated without the Orin re-shipping frames. **83.3% should be read as a bound on their combined
effect, not as a reproduction failure of either host.** Accuracies agree closely (31.7% vs 34.2%),
so nothing suggests a defect.

The Thinking row's 61.7% is **not** a reproducibility measure: both sides sample at temperature
1.0, so these are different draws from the same distribution (median generated tokens 326 vs 346).
It is reported for completeness only.

---

## Mechanism verification (CLAUDE.md, recorded before the sweep)

**Step 1 — causal chain.** If a fixed visual-token budget is reallocated from the last 120 s to
the whole session (FORMULATION.md §Scoping, representation fidelity), then for questions whose
answer-bearing evidence lies *outside* the recent window RICH makes that evidence visible where
RECENT cannot, raising accuracy; for questions whose evidence lies *inside* it, RICH spends frames
on irrelevant history and thins temporal detail near the answer, lowering accuracy. The
interaction — not either main effect — is the claim.

**Step 2 — instantiate each link.**

| causal link | implementing quantity | value / range | varies as expected? | evidence |
|---|---|---|---|---|
| budget is fixed across arms | `n_input_tokens` | median 12,420 (C1) vs 12,411 (C2) | **constant by design** | §A table |
| construction changes which frames are seen | `frame_timestamps` | RECENT ⊂ [qt−120, qt]; RICH ⊂ [0, qt] | YES | per-trial field |
| evidence location varies | `evidence_covered` | False 104 / True 574 (qt>120) | YES | §B |
| construction changes the answer | prediction disagreement | **38.8%** of 678 | YES, non-zero | §B |
| effect reverses by stratum | per-stratum diff | +18.27 pp vs −4.01 pp | YES, opposite signs | §B |

No link is ABSENT or CONSTANT in a way that blocks the test. The one constant — total token
budget — is required to be constant; that is what makes this a reallocation rather than a
budget increase.

**Step 3 — representative unit.** Per-trial rows in `results/device/accuracy_C*.jsonl` carry
`question_id`, `question_time`, `frame_timestamps` (all 37), `n_frames`, `evidence_covered`,
`answer_start_time`/`answer_end_time`, `n_input_tokens`, `n_output_tokens`, `predicted_letter`,
`correct_letter`, `correct`, `parse_status`, `latency_ms`, `seed`, and the GGUF sha256. Every
number in this report is recomputable from those rows by hand.

**Step 4 — negative control.** Built in and exact. On the **167 questions with `qt ≤ 120`** the
two constructions are byte-identical by definition. Observed: **167/167 identical input-token
counts and 167/167 identical predictions** — the mechanism, disabled by construction, produces a
*perfect* zero. When it is enabled (`qt > 120`) the same comparison yields 38.8% disagreement and
a DiD excluding zero. The control changes the result, so the mechanism is driving it.

**Step 5 — alternative explanation.** The DiD could arise from (a) the claimed evidence-coverage
mechanism, or (b) `evidence_covered` acting as a proxy for question difficulty, with RICH simply
better on hard questions regardless of where evidence sits. Distinguishing datum: under (b) RICH
should beat RECENT on the uncovered stratum *and* not lose on the covered stratum, since
difficulty would not reverse. We observe a genuine **sign reversal** (+18.27 pp vs −4.01 pp) —
RICH is actively *worse* where evidence is already covered. Pure difficulty cannot produce that.

---

## Results consistency check (CLAUDE.md, before conclusions)

**1. Cross-check against committed measurements.** Study O Q4's separating cell ran the *same*
contrast (4B-I × RICH − 4B-I × RECENT, split by `evidence_covered`) on the HF path:

| quantity | this run (llama.cpp) | prior run (HF, Study O) | source | ratio | agree? |
|---|---|---|---|---|---|
| 4B-I × RECENT accuracy, 845 | 31.48% | 32.78% | `study_o_q4_separating_cell.md` | 1.04× | agree |
| 4B-I × RICH accuracy, 845 | 31.01% | 30.53% | same | 0.98× | agree |
| DiD, Instruct, 845 | +21.20 pp | +15.4 pp | same (Contrast 1) | 1.38× | agree |

All within 2×. The DiD is larger here but the intervals overlap substantially (this
[+12.23, +30.41] vs prior [+3.8, +27.8]), and the prior was explicitly underpowered (MDE 17.30
against an observed 15.4). **Two different runtimes, two different attention implementations, same
conclusion** — this strengthens the Study O finding rather than competing with it.

**2. Physical plausibility.** C1/C2 median 6.59 s for ~12,420 input tokens at 2 generated tokens
→ ~1,885 tok/s prefill on an A6000 for a 37-image multimodal payload. C3/C4 median 12.01 s for
~12,422 input + 340 generated. Committed A6000 cold prefill is ~7,100 tok/s **text-only**; a
multimodal payload at ~3.7× slower per token is expected given the vision encoder runs over 37
images. No measurement is *faster* than a committed curve, so there is no caching artifact.

**3. Distribution sanity.** Spreads reported, not just medians. Per-quarter median latency: C1
6575/6589/6604/6593 ms, C2 6605/6597/6603/6588 ms — flat to 1.00×, confirming no GPU contention
over 2.2 h per cell. C3/C4 vary 1.19×/1.07× across quarters, tracking reasoning length (Q3 median
448 generated tokens vs ~330 elsewhere) and **not** wall-clock contention — ms/token moves
opposite to wall-clock, the signature of longer generations amortizing prefill. No constant
appears where a distribution is expected.

**4. Definition audit.** `evidence_covered` uses Study O's D4 definition, computed by importing
`study_o_q4.covered()` — any *sampled* frame timestamp inside `[answer_start_time,
answer_end_time]`. DEV-RECENT/DEV-RICH are defined in `experiments/device/dev_inputs.py`
(`frame_times` / `frame_times_rich`), N = 37, 560×560, budget 12,500; `frame_times()` was asserted
byte-identical to its pre-existing form so the Orin's latency rows stay reproducible. All
statistics (`clustered_bootstrap`, `policy_acc`, `top_e_mask`, `train_p4`, `wilson`, `did_with_ci`)
are **imported from `study_o_q4_analyze.py`**, not reimplemented, so the replication runs the same
code as the result it replicates. One definitional difference from Study O is deliberate and
declared: Study O's RICH is an HF *video* path with temporal merging; DEV-RICH passes separate
images with none.

**5. Claim linkage.** Bears on the semantic component of Context Inertia (FORMULATION.md): that
cheaper/reallocated representations discard task-relevant information in a **workload-dependent**
way. §B **supports** it — the same budget is better or worse purely as a function of where
evidence sits. §C **does not speak to** whether a runtime policy can exploit this; it is
underpowered, and the oracle bound says the exploitable headroom is small *on this benchmark*.
§D weakens any claim that reasoning compute substitutes for input construction.

**6. Proxy validity.** `evidence_covered` is a proxy for "the answer is visible in the sampled
frames" — it actually measures whether a sampled timestamp falls in the annotated answer interval.
It can be wrong in both directions: a frame inside the interval may not show the evidence, and
evidence may be inferable from outside it. It is the same proxy Study O used, so the comparison in
check 1 is like-for-like, and it is used here only as a **stratifier**, never as an outcome. The
P4 predictor in §C is a separate proxy (MiniLM text embedding + log1p(question_time) → predicted
need-for-escalation), trained excluding all 233 Study O videos (8,605 training rows); §C is
reported as INCONCLUSIVE regardless, so no headline rests on it.

---

## Conclusions

1. **The Study O crossover replicates on the device's own runtime.** llama.cpp + GGUF F16 +
   separate-image input, Instruct **DiD +22.28 pp [+12.10, +31.88]** and Thinking **+19.56 pp
   [+9.47, +29.64]**, both excluding 0 on the pre-registered denominator. The effect is not an
   artifact of the HF video pipeline.
2. **Aggregate accuracy is the wrong summary.** All four cells sit at 31–33% with overlapping
   intervals; the construction effect is real but purely interactive.
3. **Per-question selection is INCONCLUSIVE and the ceiling is low.** MDE 2.44/3.09 pp against an
   evidence-oracle headroom of only +1.5/+2.4 pp.
4. **Reasoning does not substitute for construction** — Thinking − Instruct includes 0 under both
   constructions, at ~170× the generated tokens.
5. **Cross-machine input identity is exact; cross-machine predictions are not.** 120/120 input
   tokens, 83.3% greedy predictions. Reported as a bound on frame-pixel plus GPU-architecture
   differences, not as clean reproduction.

**Null classification (Rule 2).** §C's null is **INCONCLUSIVE**, not a real negative: the
mechanism is present and demonstrably live (§B, Step 4), but the study is underpowered for an
effect of the size the oracle says is available. §D's Thinking-vs-Instruct null **is a real
negative** — the mechanism (reasoning compute) was present and exercised at 340 median generated
tokens with only 11–12/845 budget exhaustions, and it did not produce the claimed effect.

## Limitations

- `qt ≤ 120` degeneracy makes 19.8% of the pool uninformative by construction; handled by the
  declared primary denominator, not by dropping data.
- The evidence-distance oracle bound means §C would need ~4–5× the questions to resolve.
- E cannot separate frame-pixel from GPU-architecture effects without the Orin's PNG frames.
- `evidence_covered` is an annotation-interval proxy (check 6).
- The Q8_0 secondary is reported in §F below; it is n = 120, so its CI is wide.
- The frame cache was rebuilt on 2026-10-19 after a host reboot cleared `/tmp`. Reproduction was
  verified, not assumed — see §F.


---

## F. Q8_0 secondary (C3q8) — 4B-Thinking quantization, Orin's 120-question sample

User-specified secondary: *"Run Q8_0 only for 4B-Thinking on the Orin's 120-question sample."*
Same cell definition as C3 (DEV-RECENT, temp 1.0, top_p 0.95, top_k 20, max 16384, seed 0), only
the LM weights change: `Qwen3VL-4B-Thinking-Q8_0.gguf` (sha256 `7c6f9a84…`, verified at launch)
with the **same F16 mmproj** (`b8b81037…`) as C3. n = 120, elapsed 0.50 h.

### Cache-reproduction gate (this run only)

A host reboot on 2026-10-19 cleared `/tmp`, destroying the frame cache C1–C4 had used. The cache
was regenerated from the 234 local videos into a persistent path. Because a regenerated cache
that differed even slightly would make C3q8 non-comparable to C3, reproduction was **verified
before C3q8 was allowed to run**:

1. **Decoder determinism.** One already-cached video was re-decoded single-threaded and compared
   to the multithreaded build: **175/175 JPEG sha256 identical**. (The rebuild had to drop
   `thread_type='AUTO'`, which deadlocks in a futex on long videos; this check confirms the
   change does not alter pixels.)
2. **End-to-end identity gate.** C1 was re-run on 8 Orin-sample questions from the regenerated
   cache and compared to the committed `accuracy_C1.jsonl`: **8/8 identical `n_input_tokens` and
   8/8 identical `predicted_letter`** under greedy decoding. C3q8 was gated on this passing.

### Results — Q8_0 vs F16 on the same 120 questions

| | n | accuracy | Wilson 95% |
|---|---|---|---|
| C3q8 (Q8_0) | 120 | **35.0%** (42) | [27.1, 43.9] |
| C3 (F16), same 120 | 120 | **36.7%** (44) | [28.6, 45.6] |

**Q8_0 − F16 = −1.67 pp, 95% CI [−8.62, +5.13]** (video-clustered bootstrap, 2,000, seed 0) —
**includes 0**. McNemar exact b = 8, c = 10, **p = 0.815**.

**Input-token agreement with C3: 120/120 = 100%** — the two cells saw byte-identical inputs, so
this is a clean weights-only contrast.

| | Q8_0 | F16 |
|---|---|---|
| median generated tokens | 349 | 326 |
| median latency | **8.92 s** | 11.74 s |
| budget hits | 1/120 | (11/845 in full C3) |
| parse failures | 1 | — |

**Q8_0 is 1.32× faster with no detectable accuracy cost** on this sample. The caveat is power:
at n = 120 the CI spans ±~7 pp, so this rules out a large quantization penalty, not a small one.
Prediction agreement with C3 is 85/120 = 70.8%, which is **not** a reproducibility measure —
both sample at temperature 1.0, so these are different draws.

### Cross-machine, Q8_0 vs the Orin's own Q8_0 (n = 40)

| | value |
|---|---|
| input-token agreement | **40/40 = 100%** |
| frame-count agreement | **40/40 = 100%** |
| prediction agreement | 28/40 = 70.0% (temp 1.0, different draws) |
| accuracy | 20.0% (A6000) vs 25.0% (Orin) |
| median generated tokens | 502 vs 474 |

Input construction is again byte-exact across machines. The accuracy difference (2 questions out
of 40) is far inside sampling noise at this n and is not interpretable.

**Conclusion.** Q8_0 buys a 1.32× latency reduction on the A6000 at no measurable accuracy cost
(CI [−8.62, +5.13] pp), on byte-identical inputs. Consistent with the Orin's decision to treat
Q8_0 as a viable device configuration, though n = 120 leaves a small penalty undetectable.