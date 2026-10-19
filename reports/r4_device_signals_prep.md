# R4 prep — device-side confidence signals on ERQA and MV-RoboBench

**E-id:** `StudyR4-prep` (pre-registered 2026-10-18 before running)
**Script:** `experiments/erqa/r4_device_signals.py`; analysis `experiments/erqa/r4_analyse.py`
**Host:** flash / NVIDIA GeForce RTX 3090 Ti (GPU 0), `CUDA_VISIBLE_DEVICES=0`
**Backend:** HF transformers, `attn_implementation="sdpa"`
**Outputs:** `results/erqa/r4_signals/r4_{erqa,mvrobo}_{instruct,thinking}.jsonl` + `_meta.json`

## Purpose

This is **preparation**, not a finished study. It collects the device-side signals an escalation
policy could condition on, and asks a single question with them: **does low device confidence
identify the questions a 32B cloud tier would get right?** If it does not, escalation on
confidence cannot work, and R4 proper needs a different trigger.

## Runs

| workload | arm | n | accuracy | Wilson 95% | elapsed |
|---|---|---|---|---|---|
| ERQA | 4B-Instruct | 400 | **42.0%** (168) | [37.3, 46.9] | 0.03 h |
| ERQA | 4B-Thinking | 400 | **45.0%** (180) | [40.2, 49.9] | 2.39 h |
| MV-RoboBench | 4B-Instruct | 401 | **36.9%** (148) | [32.3, 41.7] | 0.03 h |
| MV-RoboBench | 4B-Thinking | 401 | **43.6%** (175) | [38.9, 48.5] | 5.03 h |

**Decoding.** Instruct: greedy, `max_new_tokens=512`. Thinking: Study Q arm A decoding —
`temperature=0.6, top_p=0.95, top_k=20, min_p=0, max_new_tokens=8192, seed=42`.

**Backend choice (declared).** Study Q arm E and Study K INSTRUCT carry
`attn_implementation: None`, i.e. default **sdpa**. These runs therefore use sdpa, not FA2:
requesting FA2 would have changed the very predictions the consistency gate checks.

**Budget exhaustion — disclosed, not dropped.** ERQA-Thinking `think_closed` 395/400, **5 budget
hits**; MV-RoboBench-Thinking 391/401, **10 budget hits**. Median think tokens 472 (ERQA) and
1,470 (MV-RoboBench). **Zero OOM** at 8192 on the 24 GB card across all four runs (`n_oom: 0`).

## Signal extraction

For each trial we store, at the answer position, the per-option-letter probability (summed over
single-token variants `"A"`, `" A"`, `"\nA"`, `"**A"`), the normalized option distribution, its
entropy in bits, `option_margin_norm` (top1 − top2), `option_mass`, and the top-20 logprobs.

For **Instruct**, `output_scores=True` is affordable because generation stops in ~2 tokens. For
**Thinking** it is not — 8192 steps × 151k vocab × 4 bytes ≈ 5 GB would not fit alongside the
model in 24 GB. Scores are instead recovered by **one extra forward pass with
`logits_to_keep=1`** over `prompt + generated[:answer_pos]`, which reproduces the answer-position
logits exactly without materializing the full score tensor.

Thinking additionally stores the full reasoning text and three behavioural signals: hesitation
counts (`wait`, `but`), and letter changes (transitions in the sequence of option letters
mentioned in the reasoning).

---

## Consistency gate (pre-registered: ≥ 90%, else STOP)

> *"On 20 ERQA questions, 4B-Instruct predictions must match Study Q arm E / Study K INSTRUCT
> predictions for the same questions (greedy); report the match rate. If below 90%, STOP."*

Run on all 400, not just 20:

| comparison | n | prediction agreement | accuracy |
|---|---|---|---|
| Study Q arm E (sdpa) | 400 | **400/400 = 100.00%** | 42.0% vs 42.0% |
| Study K INSTRUCT (greedy) | 400 | **400/400 = 100.00%** | 42.0% vs 42.0% |
| Study Q arm E (**fa2**) | 400 | 387/400 = 96.75% | 42.0% vs 40.5% |

**GATE PASSED** at 100.00% against the matching-backend references. The fa2 row is shown to
quantify the backend's own effect (3.25% of predictions) and justifies the sdpa choice: had we
run FA2, the gate would have compared two things differing in backend *and* in run.

### MV-RoboBench agreement — 82.04%, investigated and explained

4B-Instruct here scores 148/401 = 36.9% against Study S1 arm I's 150/401 = 37.4%, but only
**329/401 = 82.04%** of predictions agree. This looked like a defect. It is not.

**Study S1 and Study S2 use different prompts for the same questions.** S1 labels images
`[head view]` and ends *"Answer with only the letter of the correct option and nothing else"*;
S2 uses `View 2 (head view):` and *"Answer with the option's letter from the given choices
directly."* Question text and options are identical. These runs use **S2's construction**, which
is correct, because the cloud pairing in §Escalation is against S2's 32B run.

McNemar exact two-sided on the discordant pairs: **b = 19, c = 21, p = 0.875** — no systematic
accuracy difference, just prompt-sensitivity noise on individual items.

---

## AUROC of each signal for device correctness

All signals oriented so **higher = more confident**. AUROC via Mann-Whitney U with tie-corrected
average ranks; 95% CI by bootstrap.

### ERQA / 4B-Instruct (n=400)

| signal | AUROC | 95% CI |
|---|---|---|
| neg_entropy_bits | 0.5734 | [0.5140, 0.6306] |
| max_option_prob | 0.5709 | [0.5130, 0.6323] |
| margin_norm | 0.5703 | [0.5121, 0.6303] |
| option_mass | 0.5171 | [0.4611, 0.5751] |

### ERQA / 4B-Thinking (n=400)

| signal | AUROC | 95% CI |
|---|---|---|
| **neg_hesitation_wait** | **0.6229** | [0.5690, 0.6747] |
| neg_hesitation_total | 0.6155 | [0.5598, 0.6701] |
| neg_think_tokens | 0.6002 | [0.5428, 0.6566] |
| max_option_prob | 0.5666 | [0.5135, 0.6238] |
| neg_entropy_bits | 0.5645 | [0.5053, 0.6194] |
| margin_norm | 0.5644 | [0.5070, 0.6220] |
| neg_letter_changes | 0.5640 | [0.5063, 0.6201] |
| option_mass | 0.5020 | [0.4432, 0.5581] |

### MV-RoboBench / 4B-Instruct (n=401)

| signal | AUROC | 95% CI |
|---|---|---|
| **option_mass** | **0.6145** | [0.5569, 0.6675] |
| neg_entropy_bits | 0.5913 | [0.5345, 0.6483] |
| max_option_prob | 0.5902 | [0.5315, 0.6482] |
| margin_norm | 0.5885 | [0.5307, 0.6467] |

### MV-RoboBench / 4B-Thinking (n=401)

| signal | AUROC | 95% CI |
|---|---|---|
| **margin_norm** | **0.6021** | [0.5450, 0.6575] |
| max_option_prob | 0.6012 | [0.5461, 0.6554] |
| neg_entropy_bits | 0.6010 | [0.5474, 0.6562] |
| neg_hesitation_wait | 0.5814 | [0.5246, 0.6369] |
| neg_hesitation_total | 0.5698 | [0.5131, 0.6261] |
| neg_think_tokens | 0.5421 | [0.4832, 0.5996] |
| neg_letter_changes | 0.5070 | [0.4513, 0.5587] |

**Every signal is weak.** The best is 0.62. All but `option_mass` on ERQA-Instruct and
`neg_letter_changes`/`option_mass` on MV-Robo-Thinking have CIs excluding 0.5, so they carry
*some* information, but nothing approaches a usable detector.

**On ERQA-Thinking the behavioural signals beat the logit signals** — `wait`-count (0.6229)
> entropy (0.5645), and the CIs barely overlap. How much the model hesitates says more about
whether it is right than how peaked its answer distribution is. This does **not** carry over to
MV-RoboBench, where `margin_norm` (0.6021) edges out `neg_hesitation_wait` (0.5814). So the
behavioural advantage is workload-specific, not a general property of reasoning traces.

---

## Escalation to the 32B cloud — the headline, and it is mostly negative

Device keeps the top-(1−e) by confidence; the bottom e fraction is escalated to the cloud tier.
Cloud = Study R arm D (ERQA) / Study S2 arm D (MV-RoboBench), Qwen3-VL-32B-Thinking on h100nvl.
"gap closed" = (signal − random) / (oracle − random).

| workload / arm | device | cloud | best signal | e=0.1 | e=0.2 | e=0.3 | e=0.5 |
|---|---|---|---|---|---|---|---|
| ERQA / Instruct | 42.0% | 48.8% | neg_entropy | **−0.261** | −0.171 | −0.115 | −0.015 |
| ERQA / Thinking | 45.0% | 48.8% | neg_hesitation_wait | +0.117 | +0.096 | +0.091 | +0.029 |
| MV-Robo / Instruct | 36.9% | 43.9% | option_mass | +0.145 | +0.072 | +0.030 | +0.166 |
| MV-Robo / Thinking | 43.6% | 43.9% | margin_norm | +0.117 | +0.100 | +0.113 | +0.095 |

**ERQA + Instruct is actively negative.** At e = 0.1 the signal-guided policy reaches 40.2%
against 42.7% for *random* escalation and 42.0% for not escalating at all — escalating the 10%
of questions the device is least confident about makes accuracy **worse than doing nothing**.

The reason is the central finding here: **low device confidence tracks intrinsic question
difficulty, not device-specific failure.** The questions a 4B model is unsure about are largely
the questions a 32B model also gets wrong. Confidence is a difficulty detector, and difficulty is
precisely the wrong thing to route on — the gain from escalation comes from questions the device
fails *and the cloud solves*, which is a different set.

The three positive rows are weak (≤ +0.17 gap closed) and non-monotone in e (MV-Robo/Instruct
dips to +0.030 at e=0.3 then returns to +0.166 at e=0.5), which is what small-sample noise on
400 items looks like rather than a stable policy.

**MV-Robo / Thinking has nowhere to go:** device 43.6% vs cloud 43.9%. The tiers are tied, so
escalation cannot help regardless of the trigger, and its +0.100 "gap closed" is closing a gap of
0.3 pp.

---

## Mechanism verification

**Step 1 — causal chain.** If a device-side signal is informative about device correctness
(FORMULATION.md, quality-aware placement), then escalating the least-confident fraction to a
stronger tier should raise accuracy at fixed escalation budget, *provided* the escalated set is
enriched in questions the cloud answers correctly and the device does not.

**Step 2 — instantiate each link.**

| causal link | implementing quantity | value / range | varies as expected? | evidence |
|---|---|---|---|---|
| signal is informative about device correctness | AUROC | 0.502 – 0.623 | **YES but weak** | §AUROC |
| device and cloud differ in accuracy | device vs cloud | 42.0 vs 48.8; 36.9 vs 43.9; 45.0 vs 48.8; **43.6 vs 43.9** | YES except MV-Robo/Thinking (**≈ CONSTANT**) | §Escalation |
| escalated set enriched in cloud-solvable items | gap closed vs random | **−0.261** to +0.166 | **NO — negative on ERQA/Instruct** | §Escalation |

The third link **fails**, and that failure is the result, not an obstacle to it: the signal does
select a set, but not a set the cloud is better at. For MV-Robo/Thinking the second link is
effectively CONSTANT (0.3 pp tier gap), so that cell cannot test the claim and is reported as
**uninformative by design**, not as a negative.

**Step 3 — representative unit.** Per-trial rows carry `qid`, `category`, `n_images`,
`option_letters`, `predicted_letter`, `correct_letter`, `correct`, `parse_status`, `oom`,
`n_input_tokens`, `n_generated`, `n_think_tokens`, `think_closed`, `budget_hit`, `answer_pos`,
`answer_pos_is_letter`, `lat_ms`, `peak_alloc_gb`, the full per-letter `option_prob` /
`option_prob_norm`, `option_mass`, `option_entropy_bits`, `option_margin_norm`, `top20`, and for
Thinking the complete `think_text`. Every number here is recomputable per question by hand.

**Step 4 — negative control.** The `random` escalation column **is** the control: it escalates
the same number of questions with the signal disabled. On ERQA/Instruct random *beats* the
signal at every e, which is a stronger-than-null control outcome — the mechanism is not merely
absent, it is anti-correlated with what escalation needs. The `oracle` column bounds what a
perfect trigger would achieve (52.0–61.0% on ERQA), confirming real headroom exists and the
signal simply fails to capture it.

**Step 5 — alternative explanation.** The negative could arise from (a) confidence tracking
intrinsic difficulty rather than device-specific failure [claimed], or (b) the cloud tier being
too weak to rescue anything, making all routing futile. Distinguishing datum: the **oracle**
column reaches 52.0% at e = 0.1 and 61.0% at e = 0.2 on ERQA/Instruct, far above both device
(42.0%) and random (42.7–43.3%). A well-chosen 10% escalation *can* add 10 pp. So the cloud is
strong enough and the headroom is real — explanation (b) is ruled out, leaving (a).

---

## Results consistency check

**1. Cross-check against committed measurements.**

| quantity | this run | prior run | source | ratio | agree? |
|---|---|---|---|---|---|
| ERQA 4B-Instruct accuracy | 42.0% (168/400) | 42.0% | Study Q arm E (sdpa) | 1.00× | agree (exact) |
| ERQA 4B-Instruct predictions | — | — | Study K INSTRUCT | 400/400 | agree (exact) |
| MV-Robo 4B-Instruct accuracy | 36.9% (148/401) | 37.4% (150/401) | Study S1 arm I | 0.99× | agree |
| ERQA cloud 32B-Thinking | 48.8% (195/400) | — | Study R arm D (fa2) | — | reused, not re-measured |
| MV-Robo cloud 32B-Thinking | 43.9% (176/401) | — | Study S2 arm D (fa2) | — | reused, not re-measured |

No disagreement above 2×. The two exact matches are the strongest form of agreement available.

**2. Physical plausibility.** ERQA-Thinking: 400 questions in 2.39 h with median 472 think tokens
→ ~21.5 s/question on a 3090 Ti for a 4B model, ≈ 22 tok/s decode. MV-Robo-Thinking: 401 in
5.03 h at median 1,470 think tokens → ~45 s/question, ≈ 33 tok/s. Both are in the expected band
for a 4B model under HF `generate` with sdpa on this card and consistent with Study F's finding
that HF-generate overhead dominates. Instruct runs (0.03 h for 400 at ~2 generated tokens) are
prefill-bound, ~0.29 s/question. **No rate exceeds a committed curve**, so no caching artifact.

**3. Distribution sanity.** Spreads reported throughout: Wilson intervals on all four accuracies,
bootstrap CIs on all 23 AUROCs, `think_closed` and `budget_hit` counts per run, median think
tokens per workload (472 vs 1470 — a 3.1× spread across workloads, no suspicious constancy). No
median is reported without its interval.

**4. Definition audit.** `correct` is exact-match of the parsed option letter against
`correct_letter`. The option-letter token set is `A:[32,362] B:[33,425] C:[34,356] D:[35,422]
E:[36,468]` — summed over single-token variants, the same convention throughout. Entropy is in
**bits** over the *normalized* option distribution (not the full vocabulary), so it is bounded by
log2(4) = 2 on ERQA and log2(5) ≈ 2.32 on MV-RoboBench; these are not comparable across workloads
without that normalization and are never compared across workloads here. `option_mass` is the
unnormalized probability on option letters and is the one signal whose scale differs between
workloads by construction. MV-RoboBench uses **Study S2's** prompt, not S1's — see the 82.04%
investigation above; same name, two prompts, reconciled explicitly.

**5. Claim linkage.** Bears on CLAIMS.md / FORMULATION.md tier-placement: that a device can
decide locally when to escalate. The escalation table **weakens** the confidence-triggered
version of that claim on ERQA/Instruct (actively negative) and fails to support it elsewhere
(≤ +0.17 gap closed). The AUROC table **does not speak to** placement directly — a signal can be
informative about correctness and still be useless for routing, which is exactly what is
observed. MV-Robo/Thinking does not bear on the claim at all (tiers tied).

**6. Proxy validity.** Three proxies, stated: (i) **`wait`/`but` counts as a hesitation measure**
— they actually measure token occurrences in reasoning text, and can be inflated by stylistic
repetition unrelated to uncertainty; this is the single best signal on ERQA-Thinking (0.6229), so
it is flagged as a **limitation on the one place it matters** and marked unvalidated. (ii)
**letter changes as a proxy for deliberation** — actually counts transitions between any capital
A–E tokens in the reasoning, which will catch option *enumeration* as well as genuine
reconsideration; AUROC 0.5640/0.5070, near chance, so nothing rests on it. (iii) **answer-position
logits as the model's confidence** — recovered by a second forward pass for Thinking; validated
by `answer_pos_is_letter`, which confirms the recovered position actually holds the answer letter.

---

## Conclusions

1. **The consistency gate passes exactly** — 400/400 against both sdpa references. The harness
   reproduces prior committed ERQA results bit-for-bit, so the signals are trustworthy.
2. **All confidence signals are weak.** Best AUROC 0.6229 (`wait`-count, ERQA-Thinking); most sit
   at 0.56–0.61.
3. **Behavioural signals beat logit signals on ERQA-Thinking, but not on MV-RoboBench** — the
   advantage is workload-specific.
4. **Confidence-triggered escalation does not work, and on ERQA/Instruct is worse than random.**
   Low device confidence tracks intrinsic difficulty, not device-specific failure.
5. **The headroom is real** — the oracle reaches 61.0% at e = 0.2 on ERQA against a device 42.0%.
   The problem is the trigger, not the tiering.

**Null classification (Rule 2).** The escalation negative on ERQA/Instruct, ERQA/Thinking and
MV-Robo/Instruct is a **real negative**: the mechanism was present (signals informative,
AUROC CIs exclude 0.5), exercised (escalation applied at four budgets), the control changed the
result (random differs from signal, and beats it on ERQA/Instruct), and the oracle confirms the
effect was detectable had it existed. MV-Robo/Thinking is **inconclusive** — the device–cloud gap
is 0.3 pp, so that cell could not have shown an effect either way.

## What this means for R4 proper

R4 should **not** use device confidence as the escalation trigger. The oracle gap says a good
trigger is worth ~10 pp at e = 0.2 on ERQA, so the question is live — but the trigger must
predict *tier disagreement* (device wrong AND cloud right), not device uncertainty. Those are
different targets and the data here shows they are close to orthogonal.

## Limitations

- n = 400/401 per cell; AUROC CIs are ±0.06 wide, so 0.56 vs 0.62 differences are suggestive, not
  established.
- Hesitation counts are an unvalidated proxy (check 6) and are the top signal on ERQA-Thinking.
- Thinking arms are single-sample at temperature 0.6 — no within-question variance estimate.
- 5 + 10 budget exhaustions are scored as incorrect; treating them as missing would shift
  Thinking accuracies upward by ≤ 2.5 pp.
- Cloud rows are reused from Study R / S2, not re-measured here, so any defect there propagates.
