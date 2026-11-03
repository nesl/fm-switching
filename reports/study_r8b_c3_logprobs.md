# StudyR8b — cell C3 re-run with per-token logprobs (seeds 1, 2)

Pre-registered in `research/EXPERIMENTS.md` (StudyR8b, 2026-10-23) before any number here
was computed. Box: **flash / A6000** (`CUDA_VISIBLE_DEVICES=1`), llama.cpp server, F16 GGUF.

**Purpose.** Produce a device-side uncertainty signal for StudyR8a-v2 by re-running cell C3
exactly as committed, adding per-token logprobs (top-20). This study supplies a signal; it
does not test the escalation gate, which is StudyR8a's job.

**Contention.** R8b ran concurrently with R8a (CPU) and R8c (3090 Ti) under the user's
scheduling rule. **Every duration recorded in this study is contended and is not a latency
measurement.** `contended_duration_ms` and `elapsed_h` must never be used or compared as
latency. No latency claim appears in this report.

---

## STEP 0 gate (3 questions, run before the sweep)

| check | q1 | q2 | q3 |
|---|---|---|---|
| `n_entries == completion_tokens` | 954 / 954 ✅ | 74 / 74 ✅ | 286 / 286 ✅ |
| reasoning tokens covered | 950 ✅ | 70 ✅ | 282 ✅ |
| top-20 entries present | 20 ✅ | 20 ✅ | 20 ✅ |
| exact text match | ❌ | ❌ | ❌ |
| whitespace-normalised match | ✅ | ✅ | ✅ |

Reasoning tokens are covered, so R8b proceeded. The exact-match failure is explained in full
at sweep scale below; it is a boundary-marker artifact, not a coverage failure. It was reported
to the user as a declared deviation at the time, with the note that they may elect to treat it
as a STOP instead.

---

## Sweep gate at full scale (1,690 records = 845 questions × 2 seeds)

| check | result |
|---|---|
| per-record arrays (`text`, `chosen_lp`, `channel`) equal length | **1690 / 1690** ✅ |
| reassembled token text == `reasoning_text` + `</think>\n\n` + `answer_text` | **1690 / 1690** ✅ |
| `n_entries == completion_tokens` | 1680 / 1690 (99.4%) ⚠ |

**The two text-match caveats, resolved.**

*Boundary marker.* Reassembled token text is exactly **10 characters longer** than
`reasoning_text + answer_text` on 1,677 records, and equal on the 13 that hit the budget and
never closed the think block. The 10 characters are the `</think>` and `\n\n` tokens, which are
present in the token stream and stripped by `--reasoning-format deepseek`. The token stream is
therefore complete; the two text fields simply omit the separator. This is the same artifact
the Step-0 probe saw.

*Entry-count shortfall.* 10 of 1,690 records carry 1–2 fewer probability entries than
`usage.completion_tokens`, out of traces 1,500–4,000 tokens long. All 10 contain non-ASCII
characters (`≈ → — – é`); 513 records contain non-ASCII in total, so the condition is
necessary but not sufficient — consistent with llama-server merging a multi-byte UTF-8
character that spans a token boundary into one `generated_token_probs` entry while `usage`
counts the pieces. The recorded per-token arrays remain internally consistent and reassemble
the complete text, so the sequence is intact and the server's usage counter is the thing that
disagrees. **Prefix windows (k ≤ 100 reasoning tokens) are unaffected.** Recorded as a declared
deviation from the pre-registered "all questions match" wording.

---

## Results

| quantity | seed 1 | seed 2 | C3 (seed 0, committed) |
|---|---|---|---|
| n | 845 | 845 | 845 |
| accuracy | **32.31%** [29.24, 35.53] | **32.07%** [29.01, 35.29] | **33.37%** [30.3, 36.6] |
| inside C3's CI | ✅ | ✅ | — |
| median reasoning words | 243 | 241 | 237 |
| median reasoning tokens | 345 | 339 | not recorded |
| budget hits (`finish_reason == length`) | 16 | 17 | — |
| questions with >400 reasoning tokens (top-20 truncated) | 381 | 378 | — |
| mean chosen logprob | −0.3387 | −0.3491 | — |
| median chosen logprob | −0.0331 | −0.0342 | — |
| fraction of tokens with chosen logprob > −0.01 | 0.427 | 0.423 | — |

Both seeds land inside C3's pre-registered confidence interval and the median reasoning length
is within 3% of C3's 237 words. The arm reproduces.

**Per-question count of correct samples across C3, seed 1 and seed 2** (n = 845):

| correct samples | 0 | 1 | 2 | 3 |
|---|---|---|---|---|
| questions | **486** | 91 | 69 | **199** |

57.5% of questions are wrong on all three samples and 23.6% are right on all three; only 18.9%
are unstable. This is the better-powered device-failure target StudyR8a-v2 uses: "wrong on all
three samples" is a cleaner label than a single sample's correctness.

**Logprob distribution.** The chosen-token logprob is extremely peaked — the median token is at
−0.033 (96.7% probability) and 42.7% of tokens sit above −0.01. Mean and median differ by an
order of magnitude, so the signal lives in a thin tail of uncertain tokens, not in the bulk.

---

## Methodological note: R8b and R8c do not measure the same quantity

The pre-registered R8b Step-4 control was a temperature sweep, by analogy with R8c's. **It
tests the wrong thing here and was not used as a control.** llama-server computes probabilities
with `need_pre_sample_logits = n_probs > 0 && !post_sampling_probs`
(`server-context.cpp:1933`), so with `post_sampling_probs = false` it returns
**pre-sampling-chain** logprobs: the temperature / top-p / top-k chain is not applied to them.
A temperature sweep therefore cannot move them, and a probe at temperature 0 returned a mean
chosen logprob of −0.18 to −0.22, in the same range as the temperature-1.0 sweep.

R8c's entropy is computed **after** temperature and **before** top-k/top-p, and its Step-4
control does move (0.73 bits at T = 1.0 vs 0.037 bits at T = 0.1). The two studies' uncertainty
quantities are consequently **not the same quantity** and **are not pooled**. StudyR8a-v2 uses
−chosen_logprob on S-EMBER and entropy in bits on ERQA, orients both so that larger means less
certain, and reports them per workload only.

---

## Results consistency check

**1. Cross-check against committed measurements.**

| quantity | this run | prior run | source of prior | ratio | agree |
|---|---|---|---|---|---|
| C3 accuracy | 32.31 / 32.07% | 33.37% | `results/INDEX.md`, `reports/device_tier_accuracy_llamacpp.md` | 0.97 / 0.96 | ✅ |
| C3 median reasoning words | 243 / 241 | 237 | `reports/device_tier_accuracy_llamacpp.md` | 1.03 / 1.02 | ✅ |
| n questions | 845 | 845 | `results/INDEX.md` | 1.00 | ✅ |

No disagreement approaches 2×.

**2. Physical plausibility.** This study makes **no** latency, throughput or rate claim. All
durations were recorded under three-way host contention and are labelled as such in the meta
files and above. Nothing here may be compared against `results/cost/cost_matrix.csv`.
File sizes: largest shard 18.92 MB, under the 20 MB limit.

**3. Distribution sanity.** Spreads are reported, not just medians: the two seeds differ in
accuracy (32.31 vs 32.07), median reasoning words (243 vs 241), median chosen logprob (−0.0331
vs −0.0342) and budget hits (16 vs 17). No quantity is identical across seeds to suspicious
precision, and the per-question sample-count distribution is spread across all four cells. No
constants appear where distributions are expected.

**4. Definition audit.** C3 = the DEV-RECENT construction of the S-EMBER device arm,
4B-Thinking F16 GGUF, 845 questions, served by llama.cpp with
`--jinja --reasoning-format deepseek -ngl 99 -fa on -c 16384` — identical to the committed C3
run. Unchanged flags, unchanged construction, unchanged question set. A **reasoning token** is a
token whose channel is `r`, i.e. emitted before `</think>`; `n_think_tokens_real` counts those.
This matches the committed definition. The only additions are `logprobs: true` and
`top_logprobs: 20`; the generation parameters are untouched.

**5. Claim linkage.** This study produces an input to C5, not a test of it. Its only load-bearing
output is the per-token uncertainty series and the repeated-sample labels that StudyR8a-v2
consumes. The accuracy and length reproduction above **supports** the claim that C3 is a stable
arm; nothing here speaks for or against C5 directly.

**6. Proxy validity.** −chosen_logprob is used as a proxy for the device's token-level
uncertainty. It actually measures the model's pre-sampling-chain confidence in the token it
emitted, which is **not** the entropy of the distribution it sampled from and is invariant to
the sampling parameters. It is valid as a within-workload uncertainty ordering, and it is
**not** valid for comparison against R8c's entropy. Declared, and enforced by never pooling
the two workloads.

---

## Outputs

- `results/device/accuracy_C3_logprobs_s1_part{01,02}.jsonl.gz` + `_s1_meta.json`
- `results/device/accuracy_C3_logprobs_s2_part{01,02}.jsonl.gz` + `_s2_meta.json`
- `results/device/r8b_step0_probe.json`, `results/device/r8b_analysis.json`
- `results/device/llamaserver_810{1,2}.log.gz`
- `experiments/device/r8b_c3_logprobs.py`, `experiments/device/r8b_analyse.py`

Elapsed 4.72 h (seed 1) + 4.64 h (seed 2) = 9.36 h, inside the pre-registered 10 h stop rule.
