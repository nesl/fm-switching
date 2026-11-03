# StudyR8a — do device reasoning PREFIXES improve the escalation decision?

**E-id:** `StudyR8a` (pre-registered in `research/EXPERIMENTS.md` on 2026-10-23, before any
number in this report was computed)
**Scripts:** `experiments/escalation/study_r8a_prefix_signals.py` (compute),
`study_r8a_report.py` (tables), `study_r8a_analyse.py` (figures)
**Host:** flash, **CPU only** — no GPU was used and no inference was run. R8a ran concurrently
with StudyR8b (A6000) and StudyR8c (3090 Ti) under the user's scheduling rule; **it measures no
latency of its own**, and every decision latency quoted here comes from the Orin's standalone,
uncontended token timings.
**Outputs:** `results/escalation/study_r8a/` (`study_r8a_results.json`, `study_r8a_tables.md`,
per-workload `oof_scores_*.npz`), `figures/escalation/r8a_*.png`
**Runtime:** 0.11 h

---

## GATE OUTCOME: **NOT SHOWN** — detection partly succeeds, utility fails

Pre-registered rule: *PARTIAL REASONING ADDS VALUE* iff, held out, the best **query+prefix**
router at some **k ≤ 100** beats the **query-only** router at **e = 0.2** by **≥ 2 pp with a 95%
CI excluding 0**, on S-EMBER or ERQA.

| workload | best query+prefix router, k ≤ 100 | acc @ e=0.2 | Δ vs query-only | 95% CI | passes |
|---|---|---|---|---|---|
| S-EMBER (n=845) | `query+prefix_hand_k100`, by predicted gain | 35.86% | **+0.95 pp** | [−0.12, +2.22] | no |
| ERQA (n=400) | `query+prefix_hand_k50`, by predicted gain | 47.25% | **+1.75 pp** | [−0.25, +3.75] | no |

Neither clears 2 pp, and both CIs include 0. The verdict is **NOT SHOWN**.

The rule also requires naming which leg failed. **It is utility, not detection.**

- **Detection succeeds on S-EMBER.** At k = 100 the prefix raises held-out AUROC for
  device-incorrect from the query-only router's 0.6204 to **0.6400**, a paired
  **+0.0195 [+0.0075, +0.0327]** — CI excludes 0. And for *evidence outside the recent window*
  the prefix is not merely better, it is the only thing that works at all: the query-only router
  sits at chance (**0.4741 [0.4150, 0.5318]**) while `prefix_hand_k100` reaches
  **0.6247 [0.5658, 0.6835]**, a paired **+0.1506 [+0.0770, +0.2244]**. The first 100 reasoning
  tokens carry information about whether the device's window dropped the evidence that the
  question text simply does not contain.
- **Detection fails on ERQA.** `query+prefix_hand_k100` is 0.5725 against query-only's 0.5707,
  a paired **+0.0018 [−0.0398, +0.0413]** — indistinguishable.
- **Utility fails on both.** A detection gain of ~0.02 AUROC does not move the escalation
  frontier: it reorders questions inside a band where the cloud is barely better than the device
  (S-EMBER always-local 33.37% vs always-cloud 39.53%; ERQA 45.00% vs 46.75%), so at e = 0.2 the
  best achievable movement is small and the bootstrap cannot separate it from zero.

---

## Setup

| | S-EMBER | ERQA |
|---|---|---|
| device arm (the trace we read) | C3, 4B-Thinking × DEV-RECENT, A6000 llama.cpp F16 | `r4_erqa_thinking`, 4B-Thinking, **RTX 3090 Ti** HF sdpa |
| cloud arm | R1 K1, 32B-Instruct × RICH, H100 vLLM | StudyR arm C, 32B-Instruct, H100 HF fa2 |
| n | 845 | 400 |
| device / cloud accuracy | 33.37% / 39.53% | 45.00% / 46.75% |
| escalation gain g = cloud − device | −1: 102, 0: 589, **+1: 154** | −1: 57, 0: 279, **+1: 64** |
| splits | GroupKFold by `video_id`, 5 folds | KFold by question, 5 folds, seed 0 |
| CIs | video-clustered bootstrap, 2,000, seed 0 | paired question bootstrap, 2,000, seed 0 |

Every vectoriser, scaler, logistic regression and Ridge is fitted **inside training folds only**;
all reported numbers are pooled out-of-fold predictions. The sentence-embedding model
(`sentence-transformers/all-MiniLM-L6-v2`, CPU) is frozen — only the logistic regression on top
of it is fitted.

Device↔cloud pairings are **BACKEND-MISMATCHED** on both workloads (device llama.cpp F16 or HF
sdpa; cloud vLLM or HF fa2), as the source reports already label them.

### Decision latency, from the Orin's standalone run

| k (reasoning tokens) | 0 | 25 | 50 | 100 | 200 | 400 | full trace |
|---|---|---|---|---|---|---|---|
| median s to the k-th reasoning token | 0.00 | **18.69** | 20.20 | 23.20 | 29.16 | 37.50 | 38.25 |

n = 120 Orin questions (`results/device/tokens_4bt_f16_F16.jsonl.gz`; timestamps are seconds from
submit and already include prefill, so no TTFT is added). k = 0 is 0 s because the decision can be
made before generation starts.

**This is the number that matters most in this report.** Reaching even the 25th reasoning token
costs 18.7 s on the Orin, because the device's TTFT alone is 17.2 s. StudyR1's clean
single-request 32B latency is 4.28 s. **Any prefix router is strictly dominated on latency by
simply sending the question to the cloud** — it spends more than four cloud round-trips deciding
whether to make one. A prefix trigger can only ever be interesting if the device would have run
the trace anyway for its own answer, which is a different policy from "decide, then route".

---

## Part 1 — held-out AUROC at each prefix length

### Target (a) device incorrect

| router | k | AUROC | 95% CI | Δ vs query-only | paired 95% CI |
|---|---|---|---|---|---|
| **S-EMBER** | | | | | |
| `query_only` | — | 0.6204 | [0.5790, 0.6623] | — | — |
| `query+prefix_tfidf_k100` | 100 | 0.6400 | [0.5985, 0.6821] | **+0.0195** | **[+0.0075, +0.0327]** |
| `query+prefix_tfidf_k200` | 200 | 0.6489 | [0.6097, 0.6893] | **+0.0284** | **[+0.0133, +0.0440]** |
| `query+prefix_tfidf_kfull` | full | 0.6495 | [0.6106, 0.6887] | **+0.0291** | **[+0.0120, +0.0460]** |
| `query+prefix_hand_k100` | 100 | 0.6346 | [0.5962, 0.6728] | +0.0141 | [−0.0117, +0.0394] |
| `query+prefix_emb_k100` | 100 | 0.5160 | [0.4752, 0.5568] | −0.1044 | [−0.1543, −0.0544] |
| **ERQA** | | | | | |
| `query_only` | — | 0.5707 | [0.5123, 0.6286] | — | — |
| `query+prefix_hand_k100` | 100 | 0.5725 | [0.5140, 0.6293] | +0.0018 | [−0.0398, +0.0413] |
| `query+prefix_hand_k200` | 200 | 0.6208 | [0.5617, 0.6767] | +0.0501 | [−0.0027, +0.0979] |

The frozen MiniLM embedding router is **worse than query-only** on S-EMBER
(−0.1044 [−0.1543, −0.0544]). A 384-dimensional general-purpose sentence embedding of a partial
reasoning trace is not a useful representation for this target at n = 845; TF-IDF of the same text
is. This is reported, not dropped.

### Target (c) evidence outside the recent window — S-EMBER only

| router | k | AUROC | 95% CI | Δ vs query-only | paired 95% CI |
|---|---|---|---|---|---|
| `query_only` | — | 0.4741 | [0.4150, 0.5318] | — | — |
| `prefix_hand_k50` | 50 | 0.6160 | [0.5537, 0.6753] | **+0.1418** | **[+0.0660, +0.2167]** |
| `prefix_hand_k100` | 100 | **0.6247** | [0.5658, 0.6835] | **+0.1506** | **[+0.0770, +0.2244]** |
| `prefix_hand_k200` | 200 | 0.6004 | [0.5401, 0.6620] | +0.1263 | [+0.0468, +0.2098] |

This is the clearest positive result in the study. The question text is at chance for predicting
whether the recent window dropped the answer's evidence; 50–100 tokens of the device's own
reasoning are not. It is also the one place the handcrafted features beat TF-IDF, which is what
the mechanism predicted: the hesitation and missing-evidence markers are exactly the surface form
of "the evidence is not in what I was shown".

Full tables for every router, target and budget: `results/escalation/study_r8a/study_r8a_tables.md`.

---

## Part 2 — escalation utility

Baselines at e = 0.2:

| workload | random | perfect oracle | always-local | always-cloud |
|---|---|---|---|---|
| S-EMBER | 34.60 | 51.60 | 33.37 | 39.53 |
| ERQA | 45.42 | 61.00 | 45.00 | 46.75 |

Selected cells at e = 0.2 (full table in `study_r8a_tables.md`):

| workload | router | k | latency s | rank by | acc % | Δ vs query-only | 95% CI |
|---|---|---|---|---|---|---|---|
| S-EMBER | `query_only` | — | 0.0 | gain | 34.91 | — | — |
| S-EMBER | `query+prefix_hand_k100` | 100 | 23.2 | gain | 35.86 | +0.95 | [−0.12, +2.22] |
| S-EMBER | `query+prefix_tfidf_kfull` | full | 38.2 | gain | 36.80 | +1.89 | [+0.00, +3.50] |
| S-EMBER | `prefix_hand_kfull` | full | 38.2 | failure | 36.09 | **+2.60** | **[+0.81, +4.68]** |
| S-EMBER | **`length_only_kfull`** | full | 38.2 | failure | 36.21 | **+2.72** | **[+0.82, +4.85]** |
| ERQA | `query_only` | — | 0.0 | gain | 45.50 | — | — |
| ERQA | `query+prefix_hand_k50` | 50 | 20.2 | gain | 47.25 | +1.75 | [−0.25, +3.75] |
| ERQA | `query+prefix_tfidf_k400` | 400 | 37.5 | failure | 47.50 | +2.00 | [+0.25, +4.00] |
| ERQA | `answer_confidence` (final-answer option probs) | full | 38.2 | — | 45.00 | −0.50 | [−3.50, +2.75] |

Two routers do clear 2 pp with a CI excluding 0 on S-EMBER — but **only at k = 400 or the full
trace**, outside the gate's k ≤ 100 window, and at a decision latency of 37–38 s. And the best of
them is `length_only`. See Step 5.

The final-answer confidence baseline (the device's own option-letter distribution, available only
after the whole trace) is **−0.50 pp [−3.50, +2.75]** on ERQA: no better than query-only. This
reproduces StudyR4's negative escalation result with a different cloud arm.

---

## Part 3 — rescue matrix (S-EMBER)

Of 845 questions the device (C1, 4B-Instruct × DEV-RECENT) answers **579 incorrectly**. What
would fix them?

| category | definition | n |
|---|---|---|
| history-rescuable (either tier) | device C1 wrong & C2 right, **or** cloud K3 wrong & K1 right | 106 |
| — device side (C1 wrong, C2 right) | | 57 |
| — cloud side (K3 wrong, K1 right) | | 68 |
| capability-rescuable | C1 wrong, K3 right | 137 |
| both needed | C1, C2, K3 wrong, K1 right | 38 |
| **neither** | none of the above | **367** |

Overlaps: history ∩ capability 20; history ∩ both-needed 38; capability ∩ both-needed 0.

**63% of the device's failures (367/579) are not fixed by more history, by a 32B model, or by
both.** This is the ceiling the whole escalation programme runs into, and it is why Part 2's
headroom is so thin: the perfect oracle at e = 0.2 reaches only 51.6% against always-local 33.4%,
and a real trigger has to find the 154 g = +1 questions among 845.

**No signal tells the two rescue types apart.** Among the 579 device failures, the best AUROC for
capability-rescuable versus the rest is **0.5464** (`length_only_k50`); every prefix router is at
or below that. The device cannot tell "I need a bigger model" from "I need the history I threw
away", which is precisely the discrimination a representation-aware escalation policy would need.

---

## Mechanism verification

**Step 1 — causal chain.** Recorded in `research/EXPERIMENTS.md` before any scoring. In short:
the 4B-Thinking trace carries surface markers of the failure modes escalation can fix (hesitation,
repetition, answer churn, explicit statements that evidence is missing); those markers are readable
from the first k tokens; ranking by them separates g = +1 from the rest; escalating the top-e by
that ranking beats a query-only ranking at the same budget.

**Step 2 — instantiating each link.**

| link | quantity | value / range | varies? | evidence |
|---|---|---|---|---|
| markers exist in the trace | `hesitation_total`, `n_letter_changes`, `rep3_total`, `missing_evidence_total` | non-zero and varying from k = 25 upward | yes | feature audit, `study_r8a_tables.md` |
| readable from a prefix | handcrafted features at k ∈ {25…400} | 31 of 34 features CONSTANT at k = 0 (by construction), 21 at k = 25, 13 at k = 100, 8 at k = 400 | yes, from k = 25 | feature audit |
| separates g = +1 | held-out AUROC for device-incorrect | S-EMBER +0.0195 [+0.0075, +0.0327] at k = 100; ERQA +0.0018 [−0.0398, +0.0413] | **S-EMBER yes, ERQA no** | Part 1 |
| moves the budgeted decision | accuracy at e = 0.2 | +0.95 / +1.75 pp, both CIs include 0 | **no** | Part 2 |

**CONSTANT entries, reported not hidden.** At k = 0 all 31 prefix-derived features are constant —
that is the designed control, not a failure. From k = 25 the counting features vary. Several
pre-registered missing-evidence phrases **never fire on either workload at any k** —
`cannot see`, `before the clip`, `before the video`, `do not see`, `no visible` — so those
individual features contribute nothing; the composite `missing_evidence_total` does vary. The
phrase list was fixed before scoring and is reported as written, including the dead entries.

**Step 3 — one traced unit.** `study_r8a_tables.md` traces one S-EMBER question (device wrong,
cloud right, g = +1) at every k: prefix token count, each non-zero feature, the predicted gain,
its rank among 845, and whether it was escalated at e = 0.2.

**Step 4 — negative controls. Both behave exactly as pre-registered.**

| control | prediction | S-EMBER | ERQA |
|---|---|---|---|
| k = 0 prefix (`query+prefix_tfidf_k0`) | must equal query-only by construction | Δ = +0.00 pp, CI [0.00, 0.00]; AUROC Δ = 0.0000 | Δ = +0.00 pp, CI [0.00, 0.00] |
| prefix features shuffled within training folds | must collapse to query-only | Δ = −0.24 pp [−1.31, +0.61]; AUROC Δ = −0.0264 [−0.0383, −0.0136] | Δ = +0.50 pp [−1.00, +1.75] |

The shuffled control lands slightly **below** query-only, which is what adding noise features to a
logistic regression should do. The mechanism is therefore present and is doing the work where
Part 1 says it is.

**Step 5 — alternative explanation, and it is currently winning.** A prefix router could beat
query-only merely because *longer traces mark harder questions* — a quantity the query cannot see
but trace length alone captures. The pre-registered discriminator is a **length-only** router
(prefix token count + whether the trace closed by k). On S-EMBER at e = 0.2, `length_only_kfull`
is the **single best router in the study** (+2.72 pp [+0.82, +4.85]), ahead of every content-based
router including the full-trace TF-IDF one (+1.89 pp). On the pre-registered rule, **the S-EMBER
utility signal is trace length, not trace content.**

The one place content clearly beats length is Part 1 target (c): `prefix_hand_k100` reaches 0.6247
for evidence-outside-window where `length_only_k100` does not come close. So the trace *does*
carry content-specific information about the history gap — it just does not convert into
escalation accuracy at a 20% budget.

---

## Results consistency check

**1. Cross-check against committed measurements.** Every input reproduces its source exactly.

| quantity | this run | prior | source | ratio | agree |
|---|---|---|---|---|---|
| S-EMBER device C3 accuracy | 33.37% | 33.4% | `device_tier_accuracy_llamacpp.md` §A | 1.00 | yes |
| S-EMBER device C1 accuracy | 31.48% | 31.5% | same | 1.00 | yes |
| S-EMBER cloud K1 accuracy | 39.53% | 39.53% | `study_r1_cloud32b_sember.md` | 1.00 | yes |
| S-EMBER cloud K3 accuracy | 38.34% | 38.34% | same | 1.00 | yes |
| RECENT evidence misses | 97 / 845 | 97 / 845 | same | 1.00 | yes |
| ERQA device 4B-Thinking | 45.00% | 45.0% | `r4_device_signals_prep.md` | 1.00 | yes |
| ERQA cloud arm C | 46.75% | 46.8% | `study_r_device_vs_cloud.md` | 1.00 | yes |

**2. Physical plausibility.** The only rates here are the Orin's decision latencies. Median time to
the 25th reasoning token is 18.69 s against a committed median TTFT of 17.22 s and a median full
response of 38.31 s (`device_latency_sember.md`: 17.2 s and 38.3 s) — the prefix times sit inside
that envelope and the full-trace figure (38.25 s) reproduces the committed total. No rate is faster
than a committed curve.

**3. Distribution sanity.** No bare medians: every AUROC and every utility delta carries a
2,000-resample CI, and the feature audit reports mean, sd and non-zero count per feature per k.
Nothing agrees to more precision than its inputs vary; the one exact zero (the k = 0 control,
Δ = 0.00 with CI [0.00, 0.00]) is exact **by construction** and is the control, not a measurement.

**4. Definition audit.**
- *prefix of k tokens* — the first k tokens of the device's reasoning text under the **4B-Thinking
  tokenizer** (`Qwen3-VL-4B-Thinking`, snapshot `1de27d8c`), decoded back to text. Traces shorter
  than k contribute their whole trace, flagged by `trace_closed_by_k`.
- *device* — S-EMBER C3 (the arm that produced the trace), **not** C1. Part 3 uses C1/C2 because
  the rescue matrix is defined on the Instruct arm, exactly as pre-registered. These are two
  different device definitions in one report and are labelled at every use.
- *`evidence_covered`* — R1 K3's field, which is StudyO's D4 definition (any sampled frame inside
  the annotated interval); 97/845 misses, identical to the count in StudyO and StudyR1.
- *`n_think_tokens`* in C3 is a whitespace **word** count, not tokens; this report never uses it,
  and cuts prefixes with the real tokenizer instead.

**5. Claim linkage.** C5 (joint representation × placement × timing beats decomposed policies).
Part 1 target (c) **supports** the representation-awareness half: the trace detects a history gap
the query cannot. Part 2 **weakens** the timing half as stated: a partial-reasoning trigger does not
beat a zero-latency query-only trigger at a 20% budget, and costs 18.7–38.2 s to evaluate. Part 3
**bounds** the whole programme: 63% of device failures are outside the reach of history, capability
or both.

**6. Proxy validity.** Two proxies, both declared.
- **ERQA decision latency is a proxy.** ERQA was never run on the Orin; the latency axis on the
  ERQA figure reuses the Orin's **S-EMBER** token-time curve. ERQA prompts are images, not 37-frame
  video windows, so its TTFT is almost certainly different. The ERQA latency axis is therefore
  **unvalidated** and no ERQA conclusion in this report rests on it — the ERQA gate result is an
  accuracy comparison at matched k, not at matched seconds.
- **`evidence_covered` is an annotation-interval proxy** for "the answer is visible in what was
  sampled", inherited unchanged from StudyO; its limits are documented there.

---

## Limits

1. **The gate is a null, and it is an informative one, not a design failure.** Mechanism
   verification Step 2 found no ABSENT link and Step 4's controls moved the result, so by Rule 2
   this is a **real negative** for utility at k ≤ 100 — not inconclusive. Detection at k ≤ 100 on
   S-EMBER is a real positive.
2. **The escalation headroom is small by construction.** Cloud − device is +6.2 pp on S-EMBER and
   +1.8 pp on ERQA. With a gap that thin, a 2 pp improvement at e = 0.2 demands a near-oracle
   trigger; the study is better powered to reject than to confirm.
3. **One device arm, one cloud arm per workload.** No seed variance in v1 — that is what StudyR8b
   and StudyR8c add, and R8a-v2 re-runs this analysis with their per-token entropy features and
   repeated-sample labels under the same gate.
4. **Latency dominates everything.** On the Orin the cheapest prefix decision costs 18.7 s against
   a 4.28 s cloud round trip. Unless the device runs the trace for its own answer regardless, a
   prefix trigger is the wrong shape of policy.

---
---

# StudyR8a-v2 — the same question with the device's own uncertainty

Run 2026-10-24, after StudyR8b and StudyR8c delivered per-token uncertainty. v1 above remains
the canonical pre-registered run; this section is the pre-registered v2 re-run.

## What changed

**1. Uncertainty features (the point of the exercise).** Each prefix now also carries summaries
of the device's own per-token uncertainty over the first k reasoning tokens: mean, sd, max,
min, last, sum, slope, first-half and second-half means, token count, and the fraction of
tokens above 0.1 / 0.5 / 1.0 / 2.0. On S-EMBER the per-token quantity is **−chosen_logprob**
(StudyR8b); on ERQA it is **full-vocabulary entropy in bits** (StudyR8c). Both are oriented so
larger means less certain. As StudyR8b establishes, these are **not the same quantity** — one
is pre-sampling-chain and temperature-invariant, the other is post-temperature and
pre-truncation — so they are never pooled across workloads. Two new router families follow:
`unc` (uncertainty alone) and `handunc` (hand features + uncertainty).

**2. Device arm changed, out of necessity.** v1's S-EMBER device arm was C3 (seed 0) and its
ERQA arm was `r4_erqa_thinking` (seed 42). v2 uses **R8b seed 1** and **R8c seed 1**. This is
forced, not chosen: per-token uncertainty belongs to a specific generation, and seed-1 logprobs
cannot be attached to a seed-0 trace. Trace text, uncertainty series and device label must come
from one sample. **This change is load-bearing for the result below and is why v2 was run twice,
on seed 1 and seed 2.**

**3. Repeated-sample labels.** Three samples per question are now available (S-EMBER: C3 + s1 +
s2; ERQA: R4 + s1 + s2). Two uses: a better-powered detection target `wrong_on_all_samples`,
and a utility metric using **expected** device accuracy (correct samples / 3) in place of a
single binary outcome.

**4. `unc_min` is CONSTANT** at every k and is dropped automatically by the zero-variance
filter. It is 1 of 14 uncertainty features, not a causal link, so by Step 2 this is not a
stopping condition; it is recorded here because the audit flags it.

## GATE — fires on both v2 seeds by the letter of the rule, and does not replicate

| | v1 (C3 seed 0) | v2 seed 1 | v2 seed 2 |
|---|---|---|---|
| S-EMBER gate | NOT SHOWN | **FIRES** `query+prefix_hand_k50` **+2.012** [0.369, 3.114] | **FIRES** `query+prefix_hand_k100` **+2.130** [0.228, 3.345] |
| ERQA gate | NOT SHOWN | NOT SHOWN (best +1.00) | NOT SHOWN (best +1.00) |

Taken cell by cell, each v2 seed satisfies the pre-registered gate. Taken together, the two
seeds disagree about which cell, and **no cell clears 2 pp in more than one of the three
samples**:

| S-EMBER, e = 0.2, by_gain, Δ vs query-only (pp) | v1 | v2 s1 | v2 s2 |
|---|---|---|---|
| `query+prefix_hand_k25` | +0.12 [−0.94, 1.19] | +0.35 [−0.71, 0.94] | +0.59 [−0.58, 1.42] |
| `query+prefix_hand_k50` | **−0.24** [−1.39, 0.94] | **+2.01** [0.37, 3.11] ✅ | +0.71 [−1.06, 1.76] |
| `query+prefix_hand_k100` | +0.95 [−0.12, 2.22] | +0.83 [−0.36, 1.83] | **+2.13** [0.23, 3.35] ✅ |

The winner in each seed is null in the other two. `hand_k50` moves from **−0.24** to **+2.01**
and back to **+0.71**; `hand_k100` from +0.95 to +0.83 to **+2.13**. The only thing that changed
between these columns is which sample of the same device arm was drawn. **Resampling the device
alone moves this statistic by more than the 2 pp the gate asks for, so the gate threshold sits
inside the noise floor of its own measurement.**

Two further facts make the artifact reading the strong one:

- **The winning router contains no uncertainty features.** `hand` is v1's feature set verbatim.
  Nothing that fired is attributable to the information R8b and R8c were run to produce.
- **The gate's search family grew.** v1 searched 24 candidate cells per workload (12 routers ×
  2 rankings at k ≤ 100); v2 searches **40**. The pre-registered gate contains no multiplicity
  correction and no replication requirement. One cell in forty clearing 2.0 by 0.012, at a
  different k in each seed, is what that search predicts under the null.

The better-powered **expected-device-accuracy** utility metric shows the identical instability
and never reaches 2 pp: `hand_k50` is +1.58 [0.12, 2.65] on seed 1 but +0.67 [−0.93, 1.61] on
seed 2; `hand_k100` is +0.83 [−0.36, 1.67] on seed 1 but +1.85 [0.15, 2.97] on seed 2.

**Verdict recorded: the gate FIRES on each v2 seed under the pre-registered rule as written, and
the effect is NOT REPRODUCIBLE across seeds.** Per the repository rule on methodological
changes, the gate is not being redefined after the fact to absorb this. The pre-registered rule
is reported as it reads, together with the replication evidence that defeats it, and the
decision whether to amend the registry with a replication requirement is left to the user. On
the evidence, partial reasoning should **not** be treated as shown.

## The uncertainty signal adds nothing

This is the clearest result in v2 and it is a **real negative**, not an inconclusive one: the
mechanism is present (Step 2 passed — the uncertainty features vary as specified, and R8c's
Step-4 control showed entropy collapses 22× when disabled), it was measured, and it does not
produce the claimed effect.

| S-EMBER, device-incorrect AUROC Δ vs query-only | v2 s1 | v2 s2 |
|---|---|---|
| `query+prefix_unc_k100` | +0.0138 [−0.0095, +0.0362] | +0.0101 [−0.0148, +0.0343] |
| `query+prefix_unc_k25` | −0.0124 [−0.0226, −0.0018] | **−0.0224** [−0.0364, −0.0087] |
| `prefix_unc_k100` (alone) | **−0.0507** [−0.1002, −0.0023] | −0.0429 [−0.0958, +0.0070] |

| ERQA, device-incorrect AUROC Δ | v2 s1 | v2 s2 |
|---|---|---|
| `query+prefix_unc_k25` | **−0.0417** [−0.0656, −0.0187] | −0.0211 [−0.0565, +0.0164] |
| `query+prefix_unc_k100` | +0.0139 [−0.0173, +0.0460] | −0.0246 [−0.0607, +0.0126] |
| `prefix_unc_k100` (alone) | −0.0331 [−0.1103, +0.0485] | **−0.0796** [−0.1537, −0.0058] |

Uncertainty alone is **worse** than the query on both workloads — significantly so in
S-EMBER seed 1 and ERQA seed 2 — and adding it to the query changes nothing whose CI excludes 0
in the same direction twice. The only uncertainty results that are significant in both seeds
are negative ones. R8c's entropy profile
predicted this: within-trace variation is 4× across-question variation, and entropy is *lowest*
over the first 50 steps (0.358 bits) and highest over the last 50 (0.587) — a k ≤ 100 prefix
samples the flattest, most confident, least informative stretch of the trace.

## What does replicate: detecting evidence outside the device's window

v1's strongest result holds up, at k = 50 rather than k = 100.

| S-EMBER, `evidence_outside_window`, prefix-only AUROC Δ vs query-only | v1 | v2 s1 | v2 s2 |
|---|---|---|---|
| `prefix_hand_k25` | +0.1059 [0.020, 0.194] ✅ | +0.0624 [−0.013, 0.139] | +0.0145 [−0.079, 0.110] |
| `prefix_hand_k50` | **+0.1418** [0.066, 0.217] ✅ | **+0.1290** [0.061, 0.204] ✅ | +0.0670 [−0.007, 0.145] |
| `prefix_hand_k100` | +0.1506 [0.077, 0.224] ✅ | +0.0705 [−0.006, 0.149] | −0.0348 [−0.112, 0.047] |
| `prefix_unc_k100` | — | −0.0043 [−0.084, 0.078] | −0.0213 [−0.105, 0.060] |

At **k = 50** the delta is positive in all three samples and significant in two, against a
query-only router pinned at chance (AUROC 0.474 / 0.473). **v1's headline k = 100 figure does
not survive** — it falls to +0.07 and then to −0.03. The honest anchor is k = 50, and the honest
effect size is ≈ +0.13 AUROC, not v1's +0.15 at k = 100. The signal is in the hand-crafted text
features — the model saying it cannot see something — not in its uncertainty.

## Controls

The **shuffled-prefix control** behaves correctly in v2: on the evidence target it gives
−0.0104 / +0.0147 / −0.0113 across the three samples, every CI spanning 0, against the real
prefix's +0.13 at k = 50. On the device-incorrect target the two seeds disagree: in seed 1 the
control's delta (+0.0101 [−0.0113, +0.0328]) is indistinguishable from the real prefix's
(+0.0052 [−0.0190, +0.0274]) — but both are null there, so there is no effect to collapse — while
in seed 2 the control collapses as intended (−0.0212 [−0.0384, −0.0046]). The control is
therefore informative on the evidence target, where there is a real effect, and uninformative
on the device-incorrect target, where there is none. v1's cleanly negative control on the
device-incorrect target (−0.0264) is arm-specific and should not be quoted as general. The **k = 0 control** is exact in both seeds: `query+prefix_*_k0` Δ = 0.000, CI
[0.00, 0.00].

## Results consistency check (v2)

**1. Cross-check.** S-EMBER device arm 32.31% (s1) / 32.07% (s2) vs C3's 33.37% — ratios 0.97 /
0.96, agree. ERQA 45.75 / 45.25 vs R4's 45.00 — 1.02 / 1.01, agree. Cloud arms unchanged from
v1 to the digit (S-EMBER K1 39.527%, ERQA arm C 46.75%). A full re-run of v1 after the v2 code
changes reproduced the canonical v1 JSON with **one** difference — the added `v2_seed` key —
every number identical to within 1e-9, confirming the v2 additions did not perturb v1.

**2. Physical plausibility.** v2 is CPU-only and measures no latency. Decision latency is
unchanged from v1 (Orin standalone, uncontended): k = 25 → 18.69 s, k = 50 → 20.20 s,
k = 100 → 23.20 s, against StudyR1's 4.28 s cloud single-request latency. The conclusion from
v1 stands and is strengthened: a prefix trigger costs four cloud round-trips to decide whether
to make one.

**3. Distribution sanity.** Spreads are reported throughout, and the headline of this section is
itself a spread: the same statistic across three device samples. Nothing is constant where a
distribution is expected except `unc_min`, which is declared above.

**4. Definition audit.** k, e, the fold scheme (GroupKFold by video on S-EMBER, KFold seed 0 on
ERQA, 5 folds, everything fitted in-fold), the bootstrap (2,000 resamples, video-clustered on
S-EMBER) and the gate are unchanged from v1. The device arm changed as declared above. A
"reasoning token" on S-EMBER is a channel-`r` token from R8b; on ERQA it is a pre-answer step
from R8c. Both match their source studies.

**5. Claim linkage.** C5. The utility half is **not** supported: the gate's pass is not
reproducible, and the device's own uncertainty adds nothing at any k on either workload. The
representation-awareness half is **supported but narrowly**: the prefix detects an
evidence-outside-window condition the query cannot see, at k = 50, replicated across two of
three samples. Part 3's bound is unchanged (63% of device failures are rescued by neither
history nor capability).

**6. Proxy validity.** Three proxies, all declared: v1's two, plus the uncertainty proxies —
−chosen_logprob (pre-sampling-chain, temperature-invariant) on S-EMBER and pre-truncation
entropy on ERQA. They are valid as within-workload uncertainty orderings and are never
compared to each other or pooled.

## v2 outputs

- `results/escalation/study_r8a/study_r8a_results_v2.json`, `study_r8a_results_v2s2.json`
- `results/escalation/study_r8a/oof_scores_{sember,erqa}_v2.npz`, `_v2s2.npz`
- `results/escalation/study_r8a/study_r8a_tables_v2.md`, `study_r8a_tables_v2s2.md`
- `figures/escalation/r8a_{utility,auroc}_{sember,erqa}_v2.png` and `_v2s2.png`,
  `r8a_rescue_matrix_v2.png`, `_v2s2.png`
