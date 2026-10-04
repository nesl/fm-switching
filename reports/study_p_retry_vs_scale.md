# StudyP — Retry vs Scale on SiGNgapore2D

**Date:** 2026-10-03  
**n_signs:** 40 (40-sign StudyJ2 subset)  
**Sample size note:** n=40 limits detection to large effects. Wilson 95% CI half-width ≈ 14–15pp at ~40% accuracy; for two CIs to be non-overlapping the difference must be ≈ 29pp. The 3pp pre-registered threshold is well below this; verdicts of MATCHES or INCONCLUSIVE reflect insufficient power, not absence of an effect.  
**Scorer validation:** Gemini-2.0-Flash 40.7% (target 40.7%) — PASS
**Decoding asymmetry:** Thinking arms temp=0.6 top_p=0.95 top_k=20 min_p=0; arm D (8B-I) greedy (do_sample=False).
**Checkpoints (3 distinct):**
  - 4B-T: hidden=2560, snap `1de27d8c` (1de27d8c)
  - 8B-T: hidden=4096, snap `92f3c4b4` (92f3c4b4)
  - 8B-I: hidden=4096, snap `0c351dd0` (0c351dd0)

## §1 Verdict (Pre-registered Rule)

Pre-registered rule: **4B×N MATCHES 8B×1** if 4B accuracy at some N≤5 is within 3pp of 8B×1 with overlapping CIs. **SCALE WINS** if 8B×1 exceeds 4B×5 by >3pp.

****4B×N MATCHES 8B×1** at N=1 (within 3pp, overlapping CIs) — indistinguishable at n=40.**

Latency at N=1: 4B×1 mean=143.9s, 8B×1 mean=118.7s, ratio=1.21×.

---

## §2 Analysis 1 — Termination Rate

**Arm A:** 40 trials — 28 terminated (70.0%), 12 non-terminated (30.0%), 28 parsed ok (70.0%).
**Arm C:** 40 trials — 36 terminated (90.0%), 4 non-terminated (10.0%), 36 parsed ok (90.0%).
**Arm D:** 40 trials — 40 EOS-terminated (100.0%), 0 budget-hit (0.0%), 40 parsed ok (100.0%). (no think tags; terminated = EOS reached)

**Arm B (4B-T retries) — cumulative termination after 1–5 passes:**

| passes attempted | signs terminated | cumulative % |
|---|---|---|
| ≤1 | 28 | 70.0% |
| ≤2 | 39 | 97.5% |
| ≤3 | 39 | 97.5% |
| ≤4 | 40 | 100.0% |
| ≤5 | 40 | 100.0% |

## §3 Analysis 2 — Accuracy

Non-terminating trials score 0 (deployment-realistic).

| arm | n_signs | correct | acc | 95% CI |
|---|---|---|---|---|
| A (4B-T×1) | 40 | 11 | 27.5% | [16.1%, 42.8%] |
| C (8B-T×1) | 40 | 12 | 30.0% | [18.1%, 45.4%] |
| D (8B-I×1) | 40 | 12 | 30.0% | [18.1%, 45.4%] |

**Arm B (4B-T) cumulative accuracy after 1–5 passes:**

| N | correct (cumulative) | acc | 95% CI |
|---|---|---|---|
| ≤1 | 11 | 27.5% | [16.1%, 42.8%] |
| ≤2 | 12 | 30.0% | [18.1%, 45.4%] |
| ≤3 | 12 | 30.0% | [18.1%, 45.4%] |
| ≤4 | 12 | 30.0% | [18.1%, 45.4%] |
| ≤5 | 12 | 30.0% | [18.1%, 45.4%] |

**Retry note:** retries rescued 12 non-terminating signs into terminating ones but gained only 1 additional correct answer(s). Retry restores liveness, not accuracy.

## §4 Analysis 3 — Cumulative Latency

For arm B, mean total latency = sum of all passes attempted per sign.

**Arm A:** mean=143.9s  median=124.4s  p90=276.0s  total=1.60h
**Arm C:** mean=118.7s  median=75.1s  p90=350.6s  total=1.32h
**Arm D:** mean=2.4s  median=1.9s  p90=4.9s  total=0.03h
**Arm B:** mean=203.6s/sign  median=124.4s/sign  total=2.26h

## §5 Sanity Checks

| arm | trials | think_closed | budget_hit | parse_ok | parse_failed |
|---|---|---|---|---|---|
| A | 40 | 28 | 12 | 28 | 12 |
| B (all passes) | 54 | 40 | 14 | 40 | 14 |
| C | 40 | 36 | 4 | 36 | 4 |
| D | 40 | N/A | N/A | 40 | 0 |

answer_text non-empty for all terminating trials: **PASS**

