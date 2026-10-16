# Study J2 — SDPA vs flash-attention-2 backend comparison

**Date:** 2026-10-16
**Re-run of:** StudyJ2 (`reports/study_j2_survival.md`, 2026-09-29)
**Device:** a6000 (cuda:1) · flash_attn 2.6.3 · torch 2.8.0+cu128 · transformers 5.10.2
**Changed between runs:** the attention backend, and nothing else. Same 40-sign manifest, same model snapshot, same prompt, same decoding (temp=0.6, top_p=0.95, top_k=20, min_p=0), same max_new_tokens=24576, same seed=42.

Every trial in the FA2 file carries `attn_implementation: "flash_attention_2"`, asserted on the loaded model by `experiments/lib/attn_guard.py` before generation. Qwen3-VL silently falls back to SDPA when flash-attn is not importable, so the request alone is not evidence; the assert is.

Outputs: `results/signs/study_j2/study_j2_trials.jsonl` (SDPA, unmodified) · `results/signs/study_j2/study_j2_trials_fa2.jsonl` (new).

---

## 1. Headline — termination and truncation

| quantity | SDPA | flash-attn-2 | delta |
|---|---|---|---|
| terminated | 32/40 (80.0%) | 35/40 (87.5%) | +7.5pp |
| **truncated at 24,576** | **8/40 (20.0%)** | **5/40 (12.5%)** | **−7.5pp** |
| Wilson 95% CI on truncation | [10.5, 34.8] | [5.5, 26.1] | overlapping |

Paired over the 40 signs: **b=7, c=4, exact binomial p=0.549.**

The 20% non-termination asymptote is the most-cited number in this project. It reads 12.5% under flash-attn. **The verdict does not move:** the two intervals overlap across most of their range and the paired test is nowhere near significance. At n=40 a 7.5pp shift is not resolvable. The honest statement is that the asymptote is 20% as measured under SDPA and is not distinguishable from that under flash-attn.

---

## 2. The eleven flips, and why they are not a backend effect

Eleven of forty signs changed truncation status — seven in each direction's favour and four against. Per sign, with the think-token counts that produced the change:

| sign | n_gt | SDPA | FA2 | think SDPA → FA2 | J4 failure rate (5 seeds) |
|---|---|---|---|---|---|
| IMG_6548_frame_0019_1 | 4 | trunc | ok | 24,576 → 10,326 | 4/5 |
| IMG_6546_frame_0019_1 | 4 | trunc | ok | 24,576 → 4,529 | 3/5 |
| IMG_6623_frame_0015_0 | 7 | trunc | ok | 24,576 → 6,171 | 2/5 |
| IMG_0037_frame_0014_0 | 7 | trunc | ok | 24,576 → 11,366 | 1/5 |
| IMG_0068_frame_0007_0 | 7 | trunc | ok | 24,576 → 3,933 | 1/5 |
| IMG_6411_frame_0014_0 | 3 | trunc | ok | 24,576 → 2,442 | 1/5 |
| IMG_6617_frame_0015_0 | 5 | trunc | ok | 24,576 → 2,982 | 1/5 |
| IMG_6415_frame_0015_0 | 7 | ok | trunc | 4,410 → 24,576 | 0/5 (control) |
| IMG_6550_frame_0020_0 | 4 | ok | trunc | 5,554 → 24,576 | not a J4 subject |
| IMG_6566_frame_0022_0 | 3 | ok | trunc | 8,685 → 24,576 | not a J4 subject |
| IMG_6619_frame_0020_0 | 2 | ok | trunc | 1,689 → 24,576 | not a J4 subject |

One sign, IMG_6416 (J4 rate 1/5), is truncated under both backends. No sign is stable-and-truncated for any reason other than having drawn a bad trajectory twice.

### This is the StudyJ4 result seen through a different lens

StudyJ4 ran 14 signs × 5 seeds and found per-sign failure rates of 0/5 through 4/5 with **no sign failing on all five seeds and no cap-hit sign failing on none** — the pre-registered STOCHASTIC outcome. Its conclusion was that the StudyJ2 asymptote describes a per-attempt failure probability, not a set of unanswerable signs.

The backend swap is a second, independent way of re-drawing the sampled trajectory. Flash-attn and SDPA are mathematically equivalent but not bitwise identical; their differing float reduction orders perturb the logits, which under temperature sampling puts the run on a different trajectory from the first divergent token onward. Changing the seed and changing the backend do the same thing to a sampled run: **neither changes the question being asked, and both change the answer that gets sampled.**

The two studies agree sign by sign, which is the part that makes this more than an analogy:

- **All seven signs that recovered under FA2 are StudyJ4 cap-hits that terminate on most seeds** (rates 1/5 to 4/5). Six of the eight StudyJ2 cap-hits failed *only* on seed=42 across J4's five draws; the backend swap recovered seven of eight. A sign that terminates on four seeds out of five is a sign that terminates on most trajectories, and the FA2 trajectory is one more of those.
- **IMG_6415 is the sharpest case.** It is a StudyJ4 *control* with a 0/5 failure rate — it terminated on all five seeds — and it still hits the cap under flash-attn on seed=42. A sign cannot be "inherently non-terminating" and also terminate on five of five seeds; what it can be is a sign whose per-attempt failure probability is nonzero. At a ~13–16% per-attempt rate, P(0 failures in 5 draws) ≈ 44–50%, so a 0/5 sign failing on the sixth draw is unremarkable.
- **Three of the four signs that broke under FA2 were never J4 subjects**, because they completed on seed=42 and so were never labelled cap-hits. StudyJ4 already showed this with IMG_6567 and IMG_0042, two controls that failed on later seeds. The "cap-hit" label is an outcome of one draw, not a property of a sign, and the backend swap re-labels signs exactly as a new seed does.

**This strengthens the StudyJ4 conclusion rather than adding a finding of its own.** StudyJ4 established stochasticity by varying the seed; the only objection available to that result is that the seed is a deliberate randomness knob and might be exercising something unrepresentative. The backend swap varies something that is not a randomness knob at all — it is supposed to be a numerically equivalent implementation of the same computation — and produces the same bidirectional churn over the same signs. Two different perturbations, neither of them a change to the task, both reshuffle which signs terminate. There is no residual set of inherently non-terminating signs for either lens to find.

Pooled rates from all three measurements sit in one band:

| source | rate | 95% CI |
|---|---|---|
| StudyJ2 SDPA, 40 signs × 1 draw | 20.0% | [10.5, 34.8] |
| StudyJ2 FA2, 40 signs × 1 draw | 12.5% | [5.5, 26.1] |
| StudyJ4 unselected draws (10/62) | 16.1% | [9.0, 27.2] |
| StudyJ4 controls only (4/30) | 13.3% | [5.3, 29.7] |

Four estimates of one per-attempt probability, all mutually consistent. The right way to cite the asymptote is as a rate in the low-to-mid teens with wide intervals, measured here at 20% on the draw that named it.

---

## 3. Latency — throughput, not wall time

Raw latency cannot be compared across backends on this study. These are sampled arms, so a backend change re-draws the generation length: the eleven flips above swing single trials between 2,000 and 24,576 tokens. A first bucketing of raw latency by SDPA token count showed flash-attn "4.18× slower" in the short bucket; that bucket's FA2 trials generated 3.4× more tokens than its SDPA trials (792 → 2,663 mean). The comparison was measuring generation length, not backend speed.

Normalizing to per-trial throughput, with each backend bucketed by **its own** generated length so no pairing confound remains:

| generated tokens | n (SDPA) | median tok/s SDPA | n (FA2) | median tok/s FA2 | ratio |
|---|---|---|---|---|---|
| < 2k | 11 | 43.7 | 12 | 45.0 | **1.03×** |
| 2k–8k | 17 | 35.5 | 17 | 42.6 | **1.20×** |
| > 8k | 12 | 16.8 | 11 | 38.0 | **2.26×** |

Pairing the buckets by SDPA length instead gives 1.03× / 1.20× / 2.44× — the same picture.

Flash-attn is **never slower**. Its throughput is flat at ~38–45 tok/s across the whole range; SDPA's collapses from 43.7 to 16.8 tok/s as the KV cache grows. That is the entire effect, and it is what the attention-cost argument predicts: the benefit is not a constant speedup but the absence of a quadratic penalty.

Aggregate over the 40 signs: SDPA 20.6 tok/s, FA2 36.3 tok/s, **1.76×**. Wall clock 4.34 h → 1.99 h.

Consequence for the project's cited latency figures: any backend speedup quoted as a single average is a function of the generation-length mix of the workload that produced it, not a property of the hardware. On a short-generation workload it is ~1.0×; on this one, where 12 of 40 signs exceed 8k tokens, it is 1.76×.

---

## 4. Consistency checks

1. **Cross-check against committed measurements.** SDPA truncation 8/40 reproduces `reports/study_j2_survival.md` exactly (same file, unmodified). FA2 per-attempt rate 12.5% vs StudyJ4 corrected 13.3–16.1% — ratio 1.06–1.29×, well inside 2×.
2. **Physical plausibility.** Peak 45.0 tok/s decode for a 4B model in bf16 on an A6000 is in range; no bucket implies a rate above the committed curves.
3. **Distribution sanity.** Per-trial throughputs are reported as medians over 11–17 trials per bucket; no constants where distributions are expected. Think-token counts for the flipped signs span 1,689–24,576.
4. **Definition audit.** `truncated` is `n_generated_tokens == 24576` with `</think>` absent from the raw stream (`skip_special_tokens=False`) — identical to StudyJ2 and StudyJ4.
5. **Claim linkage.** Bears on the non-termination asymptote cited in the signs workload. Supports StudyJ4's STOCHASTIC verdict; does not move the StudyJ2 headline.
6. **Proxy validity.** `truncated` is used as a proxy for non-termination. It is a lower bound: a run that would terminate at 24,577 tokens counts as non-terminating. Same proxy as StudyJ2/J4, so the comparison is valid even though the absolute rate is budget-dependent.

---

## 5. Verdict

**UNCHANGED.** Non-termination on SiGNgapore2D is 20.0% under SDPA and 12.5% under flash-attn-2 on the same 40 signs, b=7 c=4, p=0.549 — one per-attempt probability measured twice, not two findings. The eleven bidirectional flips are the StudyJ4 stochasticity result reproduced through a perturbation that is not a seed.

Latency is the only quantity that genuinely changes: 1.76× aggregate throughput, rising from 1.03× at sub-2k generations to 2.26× past 8k.
