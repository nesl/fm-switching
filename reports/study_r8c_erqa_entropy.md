# StudyR8c — ERQA 4B-Thinking re-run with per-token entropy (seeds 1, 2)

Pre-registered in `research/EXPERIMENTS.md` (StudyR8c, 2026-10-23) before any number here was
computed. Box: **flash / RTX 3090 Ti** (`CUDA_VISIBLE_DEVICES=0`), HF transformers, sdpa.

**Purpose.** Produce a device-side uncertainty signal for StudyR8a-v2 by re-running
`r4_device_signals.py`'s 4B-Thinking ERQA arm with a `LogitsProcessor` that records
full-vocabulary entropy at every generation step. This study supplies a signal; it does not
test the escalation gate.

**Contention.** R8c ran concurrently with R8a (CPU) and R8b (A6000). **Every duration recorded
in this study is contended and is not a latency measurement**, including
`contended_duration_ms` and `elapsed_h`. No latency claim appears in this report.

**Deliberate change vs R4, recorded in advance.** Sampling follows the model card —
**temperature 1.0**, where R4 used 0.6. Accuracy drift was expected and is bounded below. The
device arm is on the **RTX 3090 Ti**, matching R4's 4B arms (and not the A6000, which carries
the 8B StudyQ arms).

---

## Entropy definition and why the processor applies the sampling chain itself

Entropy is the **full-vocabulary Shannon entropy in bits of `softmax(logits / T)`, computed
after temperature and before top-k and top-p.** HF merges a custom `LogitsProcessor` *after*
its own default warpers, so a processor that simply read the incoming logits would see a
distribution already truncated by top-k = 20 and top-p = 0.95, and would report the entropy of
20 surviving tokens rather than of the model's belief. `EntropyRecorder` therefore applies
temperature, then measures, then applies top-k and top-p itself, so the recorded quantity is
pre-truncation by construction.

---

## Gates

| gate | seed 1 | seed 2 | smoke (20 q) |
|---|---|---|---|
| `n_steps == n_generated` | ✅ | ✅ | ✅ |
| reassembled text == generated text | ✅ | ✅ | ✅ |
| `truncated_input_steps` | **0** | **0** | **0** |
| OOM | 0 | 0 | 0 |
| gate mismatches | **0** | **0** | **0** |

All gates pass at full scale on both seeds. The 20-question smoke ran first, as pre-registered.

---

## Results

| quantity | seed 1 | seed 2 | R4 (seed 42, T = 0.6) |
|---|---|---|---|
| n | 400 | 400 | 400 |
| accuracy | **45.75%** [40.93, 50.65] | **45.25%** [40.44, 50.15] | **45.00%** [40.2, 49.9] |
| overlaps R4's CI | ✅ (Δ +0.75 pp) | ✅ (Δ +0.25 pp) | — |
| median generated tokens | 592 | 642 | — |
| median reasoning tokens | 588 | 638 | — |
| budget hits | 4 | 1 | — |
| recorded steps | 440,907 | 460,096 | — |

Raising the temperature from 0.6 to 1.0 moved accuracy by **under 1 pp** in both seeds, well
inside R4's interval. The deliberate change did not disturb the arm.

**Entropy.**

| statistic | seed 1 | seed 2 |
|---|---|---|
| mean | **0.7293 bits** | **0.7334 bits** |
| median | 0.4487 bits | 0.4587 bits |
| median within-trace sd | 0.7426 | 0.7527 |
| sd across questions | 0.1807 | 0.1834 |
| mean over first 50 steps | 0.3581 | 0.3570 |
| mean over last 50 steps | 0.5863 | 0.5913 |

The two seeds agree to roughly 0.005 bits on every statistic. **Within-trace variation
(sd ≈ 0.74) is four times the across-question variation (sd ≈ 0.18)**: entropy is mostly a
property of *where you are in a trace*, not of *which question you asked*. Entropy also rises
from the opening of a trace (0.36 bits over the first 50 steps) to its close (0.59 bits over
the last 50) — the model is most confident while restating the problem and least confident
while committing to an answer. This is the mechanism StudyR8a-v2 tests for escalation value: a
k ≤ 100 prefix samples the *low*-entropy opening of the trace.

**Step 4 — negative control (pre-registered).** One cell, 20 questions, temperature 0.1:

| | T = 1.0 | T = 0.1 | ratio |
|---|---|---|---|
| mean entropy | 0.804 bits | **0.037 bits** | **22×** |
| median entropy | — | 0.000 bits | — |

Entropy collapses when the mechanism is disabled, so the recorded quantity is the temperature-
scaled distribution it claims to be and is not an artifact of the instrumentation. **Control
passes.**

**Per-question count of correct samples across R4, seed 1 and seed 2** (n = 400):

| correct samples | 0 | 1 | 2 | 3 |
|---|---|---|---|---|
| questions | **173** | 47 | 43 | **137** |

43.3% wrong on all three, 34.3% right on all three, 22.5% unstable. Note the three samples are
**not** drawn at one temperature: R4 is at 0.6 and the R8c seeds at 1.0. The count is used as a
better-powered device-failure label, not as a variance estimate at a fixed temperature.

---

## Results consistency check

**1. Cross-check against committed measurements.**

| quantity | this run | prior run | source of prior | ratio | agree |
|---|---|---|---|---|---|
| ERQA 4B-Thinking accuracy | 45.75 / 45.25% | 45.00% | `results/INDEX.md`, StudyR4 | 1.017 / 1.006 | ✅ |
| n | 400 | 400 | `results/INDEX.md` | 1.00 | ✅ |
| device GPU | RTX 3090 Ti | RTX 3090 Ti | `reports/r4_device_signals_prep.md:5`, `r4_*_meta.json` | — | ✅ |

No disagreement approaches 2×.

**2. Physical plausibility.** This study makes **no** latency, throughput or rate claim; all
durations were recorded under three-way host contention and are labelled as such. Nothing here
may be compared against `results/cost/cost_matrix.csv`. Entropy is dimensionless (bits) and is
bounded by log2(vocab) ≈ 17.3 bits; the observed mean of 0.73 bits and max-per-trace values sit
far inside that bound, as expected for a model mid-trace. File sizes: largest shard 13 MB.

**3. Distribution sanity.** Spreads are reported throughout: within-trace sd (0.74), across-
question sd (0.18), median vs mean (0.45 vs 0.73, a right-skewed distribution as expected when
most tokens are near-deterministic), and first-50 vs last-50 means. The two seeds differ in
median generated tokens (592 vs 642) and budget hits (4 vs 1). Nothing is constant where a
distribution is expected, and no two quantities agree to more precision than their inputs vary.

**4. Definition audit.** The ERQA arm is the 400-question 4B-Thinking arm of
`r4_device_signals.py`, re-run through the same code path — this script imports
`r4_device_signals` as `R4S` and reuses its prompt construction, parsing and signal
extraction verbatim, so "question", "category", "think_text" and the hesitation counts keep
their committed definitions. A **reasoning token** is a step before the answer position;
`n_think_tokens_in_steps` counts those and indexes the entropy series directly, since the step
index *is* the token index. Two definitions differ from R4 deliberately and are recorded in the
meta: **temperature 1.0** (R4: 0.6) and **entropy measured pre-truncation** (R4 recorded no
entropy).

**5. Claim linkage.** This study produces an input to C5, not a test of it. Its load-bearing
output is the per-step entropy series StudyR8a-v2 consumes. The accuracy reproduction
**supports** the claim that the ERQA device arm is stable under the model-card temperature.
The entropy profile — low at the opening, higher at the close — **bears directly** on whether a
short prefix can carry escalation signal, and is pessimistic for it; StudyR8a-v2 settles that.

**6. Proxy validity.** Full-vocabulary entropy is used as a proxy for the device's per-step
uncertainty. It actually measures the spread of the temperature-scaled distribution *before*
truncation, which is not the distribution the token was sampled from (top-k = 20, top-p = 0.95
were applied afterwards). It is valid as a within-workload uncertainty ordering and is the
quantity the Step-4 control verifies. It is **not** comparable to R8b's −chosen_logprob, which
is pre-sampling-chain and temperature-invariant on a different stack; the two are never pooled.

---

## Outputs

- `results/erqa/r8c_signals/r8c_erqa_thinking_s{1,2}_part01.jsonl.gz` + `_meta.json`
- `results/erqa/r8c_signals/r8c_erqa_thinking_s1_smoke_*` (20-question smoke)
- `results/erqa/r8c_signals/r8c_erqa_thinking_s1_t01control_*` (Step-4 control, T = 0.1)
- `results/erqa/r8c_signals/r8c_analysis.json`
- `experiments/erqa/r8c_erqa_entropy.py`, `experiments/erqa/r8c_analyse.py`

Elapsed 2.45 h (seed 1) + 2.61 h (seed 2) = 5.06 h, inside the pre-registered 8 h stop rule.
