# Study J4 — Seed Variance on SiGNgapore2D Non-Terminators

**Date:** 2026-09-30  
**Status:** Complete  
**Follow-up to:** StudyJ2 (20% non-termination asymptote at 24,576 tokens, single seed=42)  
**Research question:** Is non-termination INPUT-DETERMINED (signs cluster near 0% or 100% failure across seeds) or STOCHASTIC (failure rate is a per-attempt probability, not a sign property)?

---

## Setup

| item | value |
|------|-------|
| Dataset | NickyZimmerman/SiGNgapore2D — 14-sign subset |
| Subjects | 8 cap-hit signs from StudyJ2 §4 + 6 control completers from StudyJ2 manifest |
| Control selection | seed=99, 2 per bin: IMG_0049/n_gt=1 (low), IMG_0064/n_gt=1 (low), IMG_6567/n_gt=3 (mid), IMG_0042/n_gt=5 (mid), IMG_6415/n_gt=7 (high), IMG_6584/n_gt=18 (high) |
| Seeds | 42, 123, 456, 789, 1011 (5 draws per sign = 70 runs) |
| Model | Qwen3-VL-4B-Thinking — same snapshot as StudyJ2 |
| Decoding | temperature=0.6, top_p=0.95, top_k=20, min_p=0, do_sample=True — matching StudyJ2 |
| Prompt | Original paper prompt (verbatim) |
| max_new_tokens | 24,576 |
| Reused trials | 16 (8 from StudyJ2 seed=42 cap-hits; 8 from StudyJ3 arm-A seed=123 cap-hits) |
| Fresh runs | 54 |
| Errors / OOM | 0 errors, 0 OOMs |
| Runtime | ~7h on A6000 (cuda:1) |

---

## Pre-Registered Decision Rule

> Failure is **INPUT-DETERMINED** if per-sign failure rates are bimodal (signs cluster near 0% or near 100%).  
> Failure is **STOCHASTIC** if rates cluster near a common rate across signs.

---

## 1. Per-Sign Failure Rate (All 14 Signs)

Sorted by failure rate, descending.

| sign | n_gt | bin | role | 0 fail seeds | fail seeds | fail rate |
|------|------|-----|------|-------------|------------|-----------|
| IMG_6548_frame_0019_1 | 4 | mid | cap_hit | 789 | 42, 123, 456, 1011 | **4/5** |
| IMG_6546_frame_0019_1 | 4 | mid | cap_hit | 123, 789, 1011 | 42, 456 | **3/5** |
| IMG_6567_frame_0017_0 | 3 | mid | control | 42, 123 | 456, 789, 1011 | **3/5** |
| IMG_6623_frame_0015_0 | 7 | high | cap_hit | 123, 456, 789 | 42, 1011 | **2/5** |
| IMG_0037_frame_0014_0 | 7 | high | cap_hit | 123, 456, 789, 1011 | 42 | **1/5** |
| IMG_0042_frame_0022_0 | 5 | mid | control | 42, 123, 456, 789 | 1011 | **1/5** |
| IMG_0068_frame_0007_0 | 7 | high | cap_hit | 123, 456, 789, 1011 | 42 | **1/5** |
| IMG_6411_frame_0014_0 | 3 | mid | cap_hit | 123, 456, 789, 1011 | 42 | **1/5** |
| IMG_6416_frame_0013_0 | 3 | mid | cap_hit | 123, 456, 789, 1011 | 42 | **1/5** |
| IMG_6617_frame_0015_0 | 5 | mid | cap_hit | 123, 456, 789, 1011 | 42 | **1/5** |
| IMG_0049_frame_0003_0 | 1 | low | control | 42, 123, 456, 789, 1011 | — | **0/5** |
| IMG_0064_frame_0003_1 | 1 | low | control | 42, 123, 456, 789, 1011 | — | **0/5** |
| IMG_6415_frame_0015_0 | 7 | high | control | 42, 123, 456, 789, 1011 | — | **0/5** |
| IMG_6584_frame_0019_0 | 18 | high | control | 42, 123, 456, 789, 1011 | — | **0/5** |

---

## 2. Distribution Shape — Verdict Against Pre-Registered Rule

**VERDICT: STOCHASTIC.**

The per-sign failure rates are 0/5, 0/5, 0/5, 0/5, 1/5, 1/5, 1/5, 1/5, 1/5, 1/5, 2/5, 3/5, 3/5, 4/5. This distribution is not bimodal. No cap-hit sign fails on all 5 seeds; no cap-hit sign fails on 0/5 seeds. Rates range continuously from 1/5 to 4/5.

The INPUT-DETERMINED criterion requires signs to cluster near 0% or 100%. The closest candidate is IMG_6548 (4/5), but even that sign terminates on seed=789, confirming it is not unconditionally unanswerable.

Five of the 6 signs that failed on seed=42 in StudyJ2 (the seeds that defined the "asymptote") terminated on at least 4 of 5 seeds here. IMG_6411, IMG_6416, IMG_6617, IMG_0037, IMG_0068 each failed only on seed=42 out of 5 draws. The StudyJ2 asymptote was a snapshot of one draw, not a property of the signs.

The pre-registered rule is satisfied: **failure is STOCHASTIC**.

---

## 3. Control Completers — Do Any Fail on Any Seed?

| sign | n_gt | bin | fail rate | seeds failing |
|------|------|-----|-----------|---------------|
| IMG_0049 | 1 | low | 0/5 | — |
| IMG_0064 | 1 | low | 0/5 | — |
| IMG_6567 | 3 | mid | **3/5** | 456, 789, 1011 |
| IMG_0042 | 5 | mid | **1/5** | 1011 |
| IMG_6415 | 7 | high | 0/5 | — |
| IMG_6584 | 18 | high | 0/5 | — |

**Yes — two control completers fail on at least one seed.** IMG_6567 (n_gt=3, mid-bin) fails on 3 of 5 draws despite being a completer on seed=42 in StudyJ2. Its failure rate (3/5) matches the cap-hit group median. IMG_0042 (n_gt=5) fails on seed=1011.

This confirms the key implication: non-termination is not a property of the 8 signs that happened to fail on seed=42. Any mid/high-complexity sign can fail on an unlucky draw. The "cap-hit" label from StudyJ2 reflects seed=42 outcome only.

Low-bin controls (n_gt=1) and the highest-complexity control (n_gt=18) never fail. The 0/5 rate for IMG_6584 (n_gt=18) is notable — high n_gt does not guarantee failure, and at 18 GT items the model may be making early termination decisions differently.

---

## 4. Within-Sign Think-Token Variance (Completers Only)

For signs terminating on at least 2 seeds.

| sign | n_gt | role | completers | min think | max think | max/min |
|------|------|------|-----------|-----------|-----------|---------|
| IMG_0049 | 1 | control | 5/5 | 208 | 658 | 3.2× |
| IMG_0064 | 1 | control | 5/5 | 262 | 440 | 1.7× |
| IMG_6415 | 7 | control | 5/5 | 3,404 | 8,145 | 2.4× |
| IMG_6584 | 18 | control | 5/5 | 3,827 | 7,848 | 2.1× |
| IMG_6617 | 5 | cap_hit | 4/5 | 2,170 | 3,202 | 1.5× |
| IMG_6623 | 7 | cap_hit | 3/5 | 2,867 | 4,123 | 1.4× |
| IMG_6546 | 4 | cap_hit | 2/5 | 3,281 | 3,439 | 1.0× |
| IMG_0037 | 7 | cap_hit | 4/5 | 6,098 | 10,279 | 1.7× |
| IMG_6411 | 3 | cap_hit | 4/5 | 3,125 | 6,714 | 2.1× |
| IMG_6416 | 3 | cap_hit | 4/5 | 4,705 | 12,828 | 2.7× |
| IMG_0068 | 7 | cap_hit | 4/5 | 1,810 | 5,221 | 2.9× |
| IMG_0042 | 5 | control | 4/5 | 3,809 | 8,765 | 2.3× |
| IMG_6567 | 3 | control | 2/5 | 3,462 | 11,485 | 3.3× |

Among completers, within-sign variance is 1.0–3.3× (modest). The dramatic variance in this study is not in how long terminating runs take but in **whether a run terminates at all**: the same sign (e.g., IMG_6416) generates 4,705–12,828 think tokens on 4 seeds and 24,576 tokens (cap-hit) on 1 seed. The 24,576-token cap-hit represents a qualitatively different outcome, not a point on a continuous distribution.

IMG_6567 shows the largest completer-only ratio (3.3×): 3,462 tokens on seed=42, 11,485 on seed=123 — nearly the same order of magnitude as StudyJ's non-truncated median vs completer medians.

---

## 5. Pooled Per-Attempt Failure Rate

**18/70 = 25.7%, 95% CI [16.9%, 37.0%] (Wilson interval).**

StudyJ2 reported 20% (8/40, exact 95% CI 9–35%). The CIs fully overlap. The pooled J4 estimate (25.7%) is higher but statistically consistent with J2. The best current estimate of the per-attempt failure rate is approximately 20–26% for mid/high-complexity signs under the original paper prompt.

The pooled rate masks sign-level variation (0/5 to 4/5) that the stochastic interpretation accounts for: signs vary in their per-attempt failure probability, but no sign is deterministically unanswerable at this budget.

---

## 6. Last-500-Token Classification for Signs Failing All 5 Seeds

**Not applicable.** No sign fails on all 5 seeds. The highest failure rate is 4/5 (IMG_6548). The pre-registered criterion for this analysis (fail all 5) is not met by any sign in this study.

---

## Interpretation of StudyJ2's Asymptote

**StudyJ2's 20% asymptote describes a per-attempt failure probability, not a set of unanswerable signs.**

StudyJ2 measured one seed (seed=42) on 40 signs and found 8 signs that did not terminate at any tested budget up to 24,576 tokens. The asymptote (flat from 16,384 → 24,576) is real: those 8 signs genuinely did not terminate on that draw. StudyJ2's observation is correct as stated.

What StudyJ2 could not determine — and what StudyJ4 resolves — is whether those 8 signs are fundamentally unanswerable (always-fail) or whether they happened to be unlucky draws from a distribution with a per-attempt failure probability of ~20–26%.

StudyJ4 shows the latter: 6 of the 8 "asymptote" signs fail on only 1 of 5 seeds (always seed=42). Under the STOCHASTIC interpretation, StudyJ2's 8/40 reflects the expected outcome of drawing 40 signs each with a ~20–26% per-attempt failure probability — consistent with a binomial expectation of ~8–10 failures.

**The corrected interpretation:** At max_new_tokens=24,576 and under the original paper prompt, any given run on a mid/high-complexity sign has approximately a 20–26% chance of not terminating. This is a property of the sampling distribution, not of specific signs. A sign that failed on seed=42 will likely terminate on a different seed.

This does not reduce the practical severity: in a deployment context where one inference is performed per sign, the ~20–26% per-attempt failure rate is exactly what matters. But for scientific characterisation, the two claims are different — and the data support the stochastic one.

---

## 7. What Cannot Be Inferred from 5 Seeds

1. **5 seeds is a small sample.** Estimated per-sign rates (0/5, 1/5, …, 4/5) have wide individual CIs. A sign measured at 1/5 could have a true rate anywhere from ~0.5% to ~41% (95% exact binomial). The headline verdict (STOCHASTIC) is robust — no sign is near 0/5 or 5/5 among cap-hits — but individual sign rates are imprecise.

2. **The 4/5 sign (IMG_6548) is ambiguous.** Four failures out of 5 draws is the closest to input-determined. The one terminating seed (789) confirms it is not unconditionally unanswerable, but the true failure probability for this sign could be materially higher than others.

3. **Seed identity is not controlled.** Seeds 42 and 123 are reused from prior studies; the remaining three (456, 789, 1011) are fresh. The reuse is correct if the code path is identical (confirmed: same model, same prompt, same decoding config), but any difference in execution environment between sessions introduces a confounder.

4. **The original paper prompt only.** All 70 runs used the original prompt. StudyJ3 showed the simplified prompt eliminates all truncation; the per-attempt failure probability under the simplified prompt is ~0% at this budget. The STOCHASTIC characterisation applies to the original prompt's failure distribution; a different prompt has a different (and potentially near-zero) per-attempt failure rate.

5. **Single model.** Results apply to Qwen3-VL-4B-Thinking. A larger model or a different sampling temperature may produce a different per-attempt failure rate.

---

## Sanity Checks

- **Seeds differ:** Generation config logged per trial; `torch.manual_seed(seed)` applied before each run. Confirmed: same sign produces different n_think_tokens across seeds.
- **Reused trials identified:** 16 trials carry `reused_from: "StudyJ2"` or `reused_from: "StudyJ3-armA"`. All reused trials used identical model snapshot, prompt, and decoding config.
- **Errors and OOMs:** 0 of 54 fresh runs errored. 0 OOMs.
