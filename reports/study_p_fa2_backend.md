# Study P — SDPA vs flash-attention-2 backend comparison

**Date:** 2026-10-16
**Re-run of:** StudyP (`reports/study_p_retry_vs_scale.md`)
**Device:** a6000 (cuda:1) · flash_attn 2.6.3 · torch 2.8.0+cu128 · transformers 5.10.2
**Changed between runs:** the attention backend only. Same 40 signs, same model snapshots, same prompt, same decoding, same budgets, same seed.

All four model loads assert `flash_attention_2` on every tower via `experiments/lib/attn_guard.py`; every trial row carries the asserted value.

Outputs: `results/signs/study_p/study_p_trials.jsonl` (SDPA) · `results/signs/study_p/study_p_trials_fa2.jsonl` (new).
Arms: A = 4B-Thinking ×1 · B = 4B-Thinking + retry · C = 8B-Thinking ×1 · D = 8B-Instruct ×1.

---

## 0. Report-file incident (2026-10-16)

`study_p_retry_vs_scale.py` writes its own report to a hard-coded `REPORT_PATH`. The `--fa2`
flag redirected the trials JSONL but not the report, so **the FA2 run overwrote the committed
SDPA report in place** — accuracy, termination and latency numbers were silently replaced with
FA2 values under the original filename.

Fixed: `reports/study_p_retry_vs_scale.md` has been restored from git HEAD and is once again the
SDPA report. The script now also redirects `REPORT_PATH` to `*_fa2_autogen.md` under `--fa2`. The
overwriting FA2 autogen output is preserved outside the repo tree; its numbers are reproduced
below from the JSONL. No committed SDPA number was lost — the file was restored, not reconstructed.

---

## 1. Throughput by generated length

Raw latency cannot be compared across backends on arms A, B and C: they are sampled, so the
backend change re-draws the trajectory and the generation length with it. Below, per-trial
throughput with **each backend bucketed by its own generated token count**, so no pairing
confound remains. Pass 1 only (arm B's later passes are reruns of arm A's prompt).

| arm | bucket | n S / F | med gen tok S / F | tok/s SDPA | tok/s FA2 | ratio |
|---|---|---|---|---|---|---|
| A (4B-Thinking) | <2k | 11 / 12 | 430 / 428 | 43.7 | 45.0 | **1.03×** |
| A | 2k–8k | 17 / 17 | 4,261 / 4,245 | 35.4 | 42.7 | 1.21× |
| A | >8k | 12 / 11 | 8,192 / 8,192 | 30.1 | 40.1 | **1.33×** |
| C (8B-Thinking) | <2k | 20 / 13 | 1,094 / 421 | 29.4 | 30.4 | **1.04×** |
| C | 2k–8k | 16 / 22 | 3,598 / 2,890 | 27.0 | 29.9 | 1.11× |
| C | >8k | 4 / 5 | 8,192 / 8,192 | 23.1 | 28.2 | 1.22× |
| D (8B-Instruct) | <2k | 40 / 40 | 56 / 56 | 28.5 | 28.5 | **1.00×** |

Same-trial paired ratio (same sign under both backends, median of per-trial tok/s ratios):
**arm A 1.19×, arm C 1.05×, arm D 1.00×** (n=40 each).

Aggregate throughput: A 32.1 → 41.2 tok/s (1.28×); C 25.3 → 29.1 tok/s (1.15×); D 28.8 → 29.0
tok/s (1.01×).

Flash-attn is never slower in any cell. The gain is monotone in generated length and absent on
the instruct arm, which generates ~56 tokens and has no KV cache worth the kernel's trouble.

---

## 2. Correction — the 59× → 42× cost ratio is wall-clock-per-arm, not a backend speedup

**Dated correction, 2026-10-16.** The headline "4B-Thinking costs 59× the 8B-Instruct arm, 42×
under flash-attn" was reported as though the change were a backend effect. It is not, or not
only. It is the ratio of mean wall time per sign between two arms, and on a sampled arm that
quantity moves when the backend re-draws the generation length.

| arm | mean wall latency | mean generated tokens | throughput |
|---|---|---|---|
| A | 143.94 s → 104.50 s (0.73×) | 4,618 → 4,303 (0.93×) | 32.1 → 41.2 tok/s (1.28×) |
| C | 118.67 s → 108.09 s (0.91×) | 3,002 → 3,141 (1.05×) | 25.3 → 29.1 tok/s (1.15×) |
| D | 2.44 s → 2.49 s (1.02×) | 70 → 72 (1.03×) | 28.8 → 29.0 tok/s (1.01×) |

Decomposing the A/D ratio exactly:

```
59.0×  ×  0.932 (arm A drew 6.8% fewer tokens)
       ÷  1.283 (arm A ran 28% faster per token)
       ×  0.982 (arm D wall time drifted 1.8%)
       =  42.0×
```

Roughly two thirds of the drop is the real kernel speedup and one third is the sampled arm
happening to draw shorter sequences this time. **59× is the correct figure to cite for the SDPA
run and 42× for the flash-attn run** — both are honest statements of what the arm cost to
execute. Neither is a measurement of flash-attn, and the difference between them should not be
quoted as one. The backend-isolated number is the throughput ratio, 1.28×.

The qualitative conclusion is untouched under either backend: the bounded instruct path is
cheaper by a factor in the tens with no accuracy cost that this n can resolve.

---

## 3. Numbers that did not need recomputing

Accuracy, termination and the scale-buys-termination comparison are counts, not timings, and
carry no bucketing artifact. They are reported in §4 below unchanged from the JSONL and are not
revised by this correction.

| quantity | SDPA | FA2 |
|---|---|---|
| arm A terminated | 28/40 (70.0%) | 30/40 (75.0%) |
| arm C terminated | 36/40 (90.0%) | 35/40 (87.5%) |
| arm D terminated | 40/40 (100%) | 40/40 (100%) |
| arm A accuracy | 27.5% [16.1, 42.8] | 22.5% [12.3, 37.5] |
| arm C accuracy | 30.0% [18.1, 45.4] | 27.5% [16.1, 42.8] |
| arm D accuracy | 30.0% [18.1, 45.4] | 32.5% [20.1, 48.0] |
| arm B cumulative acc at N=5 | 30.0% | 25.0% |

All intervals overlap heavily at n=40. Scale-buys-termination reads 70→90% under SDPA and
75→87.5% under FA2; the direction holds, the magnitude is not resolvable at this n. No verdict
flips. The pre-registered rule ("4B×N MATCHES 8B×1") is satisfied under both backends — at N=1
under SDPA and N=2 under FA2, a difference that is itself within sampling noise.

**Standing discrepancy, unrelated to the backend:** the registry's 85× cost ratio for this study
does not reproduce from this data under either backend (59× SDPA, 42× FA2). Flagged previously;
not resolved here.
