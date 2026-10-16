# StudyQ under flash-attention-2 — backend-matched re-run

**Date:** 2026-10-15 · **Host:** flash, A6000 (GPU 1) · **Backend:** `flash_attention_2`, asserted per load
**Trials:** `results/erqa/study_q/study_q_trials_fa2.jsonl` (2,002 rows) · SDPA originals untouched

## Why this run exists

Every `experiments/erqa/` script loaded Qwen3-VL without `attn_implementation`, so the
transformers 5.12.1 default (`sdpa`) was used throughout, while the committed S-EMBER and
vision cost studies requested `flash_attention_2` explicitly. Same named quantities,
two configurations. This run holds questions, decoding, seeds and manifests fixed and
changes only the backend.

Enforcement: `experiments/lib/attn_guard.py` aborts the run unless the top-level, text and
vision configs all report `flash_attention_2` after loading. The asserted value is written
into every trial row as `attn_implementation`.

## Verdict: UNCHANGED — BOUNDED PATH SUFFICES

No arm's verdict flips. All five arms remain within a narrow band, and the bounded
(instruct) path still matches the thinking path at a large cost advantage.

| arm | n | SDPA | FA2 | delta | b | c | sign p | lat SDPA | lat FA2 | ratio |
|---|---|---|---|---|---|---|---|---|---|---|
| E 4B-Instruct | 400 | 42.00% | 40.50% | −1.50 | 2 | 8 | 0.109 | 0.20s | 0.20s | 1.00 |
| D 8B-Instruct | 400 | 42.50% | 43.00% | +0.50 | 3 | 1 | 0.625 | 0.31s | 0.31s | 1.00 |
| A 4B-Thinking | 400 | 43.25% | 46.25% | +3.00 | 38 | 26 | 0.169 | 27.32s | 22.44s | 0.82 |
| B 4B-T +retry | 400 | 43.25% | 46.25% | +3.00 | 38 | 26 | 0.169 | 27.32s | 22.44s | 0.82 |
| C 8B-Thinking | 400 | 43.50% | 47.25% | +3.75 | 35 | 20 | 0.058 | 32.50s | 30.77s | 0.95 |

Headline cost ratio: 8B-Instruct vs 4B-Thinking was **88×** under SDPA (27.32/0.31) and is
**72×** under flash-attn (22.44/0.31). Same conclusion, smaller number.

Both are **mean-of-means** — arm A's mean per-trial latency over arm D's. Carried to full
precision they are 89.5× and 73.3×; the committed StudyQ report states the same SDPA quantity as
**91×** (27.3/0.3), so 88× and 91× are the same number rounded differently, not two measurements.
The **median-of-medians** version is quite different — **46.7× → 43.6×** — because arm A's
latency distribution is long-tailed. StudyS1's headline 226× is median-of-medians, so it is not
on the same basis as this one.

The thinking arms' latency ratios (0.82, 0.95) are mean wall time over the fixed 400-question
set, which is the right number for "what does this arm cost to run". It is not a clean backend
speedup: on a sampled arm the backend change also re-draws the generation length. See the
throughput section below for the kernel effect isolated from the length effect.

## Greedy arms are NOT bitwise reproducible across backends

Arm E shifted −1.50pp, which trips a naive ±1pp "greedy must be deterministic" rule.
It is not a defect. Probing the top-2 logit margin at the decision point under both
backends in one process:

| set | n | median top-2 logit margin |
|---|---|---|
| questions whose predicted letter flipped | 13 | **0.0000** |
| questions that were stable | 40 | **2.5000** |

Every flip sits within 0–0.75 of a tie, where 0.25 is one bf16 quantisation step at that
magnitude; several are exact ties. Stable questions sit an order of magnitude away. Both
backends also emit an identical first token on all 53 probed questions, so divergence is
later-sequence, not at load. FA2 and SDPA are mathematically equivalent; their floating-point
reduction orders differ, and argmax is unstable only where the top-2 are tied.

**Consequence for the tripwire.** With 13 near-tie questions out of 400, each equally likely
to land either way, the numerics floor alone is **±1.77pp** (95%). A ±1pp rule fires on noise.
The observed −1.50pp is inside that band and the sign test on the discordant pairs (b=2, c=8)
gives p=0.109. This floor is workload-specific and must be recomputed per study, not assumed.

Sampled (thinking) arms re-draw token sequences regardless of backend; at n=400, p≈0.45 the
95% noise band is ±6.6pp. All three thinking deltas (+3.00, +3.00, +3.75) are inside it.
Arm C's p=0.058 is the closest to significance and is read as noise: there is no mechanism by
which an attention kernel improves answer quality.

## Speedup scales with generation length

**Correction (2026-10-16).** An earlier version of this section bucketed *raw latency* by
generated-token count and reported flash-attn as "23–35% slower on short generations". That was
an artifact. Arms A and C are sampled (temp=0.6), so the backend change re-draws the trajectory
and the generation length along with it — the short bucket's FA2 trials generate a median 329
tokens against SDPA's 287. Comparing their wall times measures the length difference, not the
backend. The table below compares per-trial **throughput**, with each backend bucketed by its own
generated length so no pairing confound remains. Flash-attn is never slower.

| arm | bucket | n SDPA / FA2 | med gen tok S / F | tok/s SDPA | tok/s FA2 | ratio |
|---|---|---|---|---|---|---|
| A (4B-Thinking) | short <1k | 284 / 291 | 287 / 329 | 43.7 | 44.5 | **1.02×** |
| A | med 1–4k | 94 / 90 | 1,728 / 1,748 | 41.0 | 44.7 | 1.09× |
| A | long >4k | 22 / 19 | 5,522 / 4,831 | 33.4 | 42.1 | **1.26×** |
| C (8B-Thinking) | short <1k | 292 / 295 | 240 / 259 | 29.6 | 30.0 | **1.01×** |
| C | med 1–4k | 96 / 89 | 1,738 / 1,688 | 28.4 | 30.4 | 1.07× |
| C | long >4k | 12 / 16 | 5,423 / 6,208 | 25.0 | 28.8 | 1.15× |
| E (4B-Instruct, greedy) | 1 token | 400 / 400 | 1 / 1 | 5.9 | 5.9 | 1.00× |
| D (8B-Instruct, greedy) | 1 token | 400 / 400 | 1 / 1 | 3.8 | 3.8 | 0.99× |

Aggregate throughput: arm A 37.9 → 43.6 tok/s (**1.15×**, wall 3.04 h → 2.49 h); arm C 27.5 → 29.7
tok/s (1.08×, 3.61 h → 3.42 h). The instruct arms are deterministic single-token generations and
are unaffected to two decimal places — they are the only arms where a raw-latency comparison was
ever safe, and they agree with the throughput view.

The effect is monotone in context length and modest here because ERQA is short-generation
dominated: 284 of 400 arm-A questions finish under 1k tokens, where there is almost no KV cache
for the kernel to help with. On StudyJ2's signs workload, where 12 of 40 runs exceed 8k tokens,
the same comparison gives 2.26× in the long bucket and 1.76× aggregate. Flash-attn does not make
the model faster by a fixed factor; it removes a penalty that only appears at length.

## Implementation note — a reuse confound that had to be removed first

StudyQ's arm E does not run a model in the original script: it copies StudyK's INSTRUCT rows
verbatim, `total_latency_ms` included. Under `--fa2` that would have injected 400 SDPA trials
into the backend comparison. Arm E is now run natively (4B-Instruct greedy) whenever `--fa2`
is passed; the SDPA path is unchanged.

Arm B is likewise not independent work: its pass-1 rows are byte-identical copies of arm A
(400/400 verified) and only budget-hit questions are re-generated — 2 under FA2, 5 under SDPA.
Arm B's cost is therefore arm A's cost, not an additional 3.19h.

## Scope

Questions, decoding (CFG-A thinking: temp 0.6 / top_p 0.95 / top_k 20 / min_p 0;
instruct greedy), seeds, budgets and manifests are identical to the SDPA run. Only the
attention backend changed.
