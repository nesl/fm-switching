# Study J — SDPA vs flash-attention-2 backend comparison

**Date:** 2026-10-16
**Re-run of:** StudyJ (`reports/study_j_signs.md`) — the 2,048-token reasoning gate on SiGNgapore2D
**Device:** a6000 (cuda:1) · flash_attn 2.6.3 · torch 2.4.1+cu118 · transformers 5.12.1
**Changed between runs:** the attention backend only. Same 162-sign recognition set, same model
snapshots, same prompt, same decoding, same `max_new_tokens=2048`, same seed=42.

`flash_attention_2` is asserted on all three towers of both model loads via
`experiments/lib/attn_guard.py` and recorded on every trial row.

Outputs: `results/signs/study_j/study_j_trials.jsonl` (SDPA, unmodified) ·
`results/signs/study_j/study_j_trials_fa2.jsonl` (new, 324 trials, 0 duplicates).

**Scope note.** `study_j_signs.py` defines three arms (INSTRUCT, THINKING × 3 seeds,
THINKING-QUICK × 3 seeds = 1,134 trials). The committed SDPA run only ever completed INSTRUCT
and THINKING seed=42. This re-run was stopped at the same boundary so the two files mirror each
other exactly; seeds 123/456 and THINKING-QUICK have no SDPA counterpart and cannot enter a
backend-matched comparison. Ten seed-123 rows generated before the stop are held outside the
repo and are not part of this result.

---

## 1. The gate verdict does not move

| quantity | SDPA | flash-attn-2 | paired |
|---|---|---|---|
| **THINKING truncated at 2,048** | **130/162 (80.2%)** | 125/162 (77.2%) | b=12, c=7, **exact p=0.359** |
| THINKING parsed ok | 32/162 | 37/162 | |
| INSTRUCT truncated | 0/162 | 0/162 | b=0, c=0 |
| INSTRUCT parsed ok | 162/162 | 162/162 | |

The committed headline — **80.2% truncation at 2,048** — reproduces exactly under SDPA, which is
the check that the pairing is sound. Under flash-attn it reads 3.0 pp lower, far from
significance. **StudyJ's gate-fail finding is unchanged.**

Nineteen signs changed truncation status, in both directions (12 one way, 7 the other). This is
the same bidirectional churn as StudyJ2 (b=7, c=4) and carries the same reading: the backend
perturbs logits, which on a sampled arm re-draws the trajectory. It is not evidence that
flash-attn makes signs terminable. See `reports/study_j2_fa2_backend.md` §2, where the same
effect is cross-checked against StudyJ4's seed-variance result.

**Accuracy is not comparable on this study and that is the finding, not a defect.** Only 32 (SDPA)
and 37 (FA2) of 162 trials parse, because 80% truncate before emitting an answer. A 2,048-token
budget does not leave a thinking model enough room to answer; that is what the gate measures.

---

## 2. Throughput — the cleanest backend measurement in this set

Because 118 trials hit the 2,048 cap under **both** backends, they generate essentially the same
number of tokens either way: **241,658 (SDPA) vs 241,662 (FA2)** — a 4-token difference across
118 trials, arising because the cap triggers at `len(generated) >= max_new_tokens` and a trial
can overshoot by a token. The re-drawn-generation-length confound that had to be corrected for in
StudyQ, StudyP, StudyS1 and StudyJ2 is therefore absent here by construction, and the ratio below
is a direct measurement of kernel speed.

| arm | bucket | n S/F | tok/s SDPA | tok/s FA2 | ratio |
|---|---|---|---|---|---|
| THINKING | <1k | 21/19 | 43.3 | 44.8 | 1.03× |
| THINKING | 1–2k | 11/18 | 40.8 | 44.5 | 1.09× |
| THINKING | ≥2k (cap) | 130/125 | 39.9 | 44.3 | 1.11× |
| **THINKING** | **capped under both** | **118** | **39.7** | **44.2** | **1.11×** |
| INSTRUCT | <1k (≈1 tok) | 162/162 | 42.4 | 42.5 | **1.00×** |

Wall clock on the paired set: THINKING 2.04 h → 1.84 h (1.11×); INSTRUCT 0.07 h → 0.07 h (1.00×).

### Relation to the other studies

StudyJ caps generation at 2,048 tokens and measures 1.11×; StudyJ2 caps at 24,576 and measures
1.76× aggregate with 2.26× in its >8k bucket, on the same model and the same dataset.

This is **consistent with** flash-attn's benefit growing with KV cache size, which is what the
attention-cost argument predicts. It is not a demonstration of that scaling: two budgets is two
points, and the two numbers were not obtained the same way — StudyJ2's required a
throughput normalisation to remove a re-drawn-length confound, while StudyJ's capped-both subset
has no such confound. They are not strictly like-for-like.

A **cap ladder** — the same 40-sign subset at 4k / 8k / 16k under both backends — would turn this
into a measured curve for a few GPU-hours. Recorded as a cheap future addition; not run.

What the two studies do jointly support, without needing the scaling claim, is narrower and still
useful: a single-number "flash-attn speedup" is not a property of the model or the hardware. The
same model on the same dataset gives 1.11× or 1.76× depending on the token budget, so any quoted
ratio has to state the generation-length regime it was measured in.

---

## 3. A schema defect in the committed SDPA file

The committed `study_j_trials.jsonl` mixes two script versions:

| arm | truncation field | answer field |
|---|---|---|
| INSTRUCT (SDPA) | `budget_hit` | `raw_answer` |
| THINKING (SDPA) | `truncated` | `answer_text` |
| both arms (FA2) | `truncated` | `answer_text` |

Same two concepts, two names, inside one committed result file — the arms were produced under
different versions of `study_j_signs.py`. This is the CLAUDE.md consistency-check-4 failure mode
(one named quantity, two definitions, no reconciliation) occurring *within* a single file rather
than across experiments, and it is not recorded anywhere else in the repo.

The semantics are equivalent (both are `len(generated) >= max_new_tokens`), so the analysis
normalises on read rather than rewriting the committed file. Flagged here; not repaired, because
editing a committed result file to fix a field name is a larger decision than this report.

---

## 4. Consistency checks

1. **Cross-check against committed measurements.** SDPA truncation 130/162 = 80.2% reproduces the
   committed StudyJ headline exactly.
2. **Physical plausibility.** 42–45 tok/s decode for a 4B model in bf16 on an A6000 matches the
   StudyJ2 flash-attn baseline (42.7 tok/s median) and the StudyJ6 run (42.5). No cell exceeds
   the committed curves.
3. **Distribution sanity.** Throughputs are medians over 11–162 trials per cell with n stated.
4. **Definition audit.** `truncated` = `len(generated) >= 2048`; identical in both files once the
   `budget_hit` alias in the SDPA INSTRUCT rows is normalised (§3).
5. **Claim linkage.** Bears on the 2,048-token reasoning gate. The gate-fail verdict is unchanged
   under flash-attn.
6. **Proxy validity.** `truncated` is a lower bound on non-termination, as in StudyJ2/J4 —
   budget-dependent by construction, which is the point of a gate study.

---

## 5. Verdict

**UNCHANGED.** The 2,048-token gate fails under both backends: 80.2% truncation under SDPA,
77.2% under flash-attn, b=12 c=7, p=0.359. Flash-attn delivers a **1.11× throughput gain** on
this workload — measured on 118 trials that generate the same token count under both backends —
and **1.00×** on the single-token instruct arm.
