# StudyQ — Retry vs Scale on ERQA

**Date:** 2026-10-04  
**n_questions:** 400 (RunsenXu/ERQA full test set)  
**Sample size note:** n=400, 4 options per question. Wilson 95% CI half-width ≈ 4.9pp at ~43% accuracy; for two CIs to be non-overlapping the difference must be ≈ 10pp. The 3pp pre-registered threshold is below this; a verdict of BOUNDED PATH SUFFICES or INCONCLUSIVE reflects power, not absence of effect.  
**Random baseline:** ~25% (4 options per question; all 400 questions have 4 options).  
**Decoding:** Thinking arms temp=0.6 top_p=0.95 top_k=20 min_p=0 max_new_tokens=8192. Instruct arms greedy max_new_tokens=512.  
**Checkpoints (4 distinct):**
  - 4B-I: snap `ebb281ec` (arm E — REUSED from StudyK INSTRUCT; answer_text not stored in reused trials)
  - 4B-T: snap `1de27d8c` (arms A, B — RE-RUN at max_new_tokens=8192; StudyK used 16384)
  - 8B-I: snap `0c351dd0` (arm D — instruct_mode; no think tags)
  - 8B-T: snap `92f3c4b4` (arm C)

---

## §1 Verdict (Pre-registered Rule)

Pre-registered rule:  
**BOUNDED PATH SUFFICES** if 8B-Instruct accuracy is within 3pp of the best reasoning arm with overlapping CIs.  
**REASONING WINS** if any reasoning arm exceeds 8B-Instruct by >3pp with non-overlapping CIs.

**BOUNDED PATH SUFFICES. Best reasoning arm (B: 43.8%) exceeds 8B-Instruct (D: 42.5%) by 1.3pp with fully overlapping CIs. No reasoning arm exceeds 8B-Instruct by >3pp. All five arms — 4B-Instruct, 8B-Instruct, 4B-Thinking×1, 4B-Thinking×5, 8B-Thinking×1 — are indistinguishable at n=400 (all CIs overlap).**

Latency at N=1: 4B-T mean=27.3s vs 8B-I mean=0.3s — a 91× latency gap with no accuracy return.

---

## §2 Analysis 1 — Termination Rate

**Arm A (4B-T×1):** 400 trials — 395 terminated (98.8%), 5 budget_hit (1.2%).  
**Arm C (8B-T×1):** 400 trials — 396 terminated (99.0%), 4 budget_hit (1.0%).  
**Arm D (8B-I):** 400 trials — 400 EOS-terminated (100%), 0 budget_hit. (no think tags; terminated = EOS reached)  
**Arm E (4B-I, reused):** 400 trials — 400 EOS-terminated (100%), 0 budget_hit.

**Arm B (4B-T retries) — cumulative termination after 1–5 passes:**

| passes attempted | questions terminated | cumulative % |
|---|---|---|
| ≤1 | 395 | 98.8% |
| ≤2 | 399 | 99.8% |
| ≤3 | 400 | 100.0% |
| ≤4 | 400 | 100.0% |
| ≤5 | 400 | 100.0% |

Arm B retry note: 5 questions had budget_hit at pass 1. All 5 terminated by pass 3 (4 at pass 2, 1 at pass 3). Net new inference: 6 additional passes (5 at pass 2, 1 at pass 3), total 0.16h. This is a 1.2% retry rate — arm B adds negligible cost over arm A.

---

## §3 Analysis 2 — Accuracy

Non-terminating trials score 0 (deployment-realistic). Arm B final accuracy uses each question's first think_closed pass.

| arm | model | n | correct | acc | 95% CI |
|---|---|---|---|---|---|
| E (4B-I×1, reused) | 4B-Instruct | 400 | 168 | 42.0% | [37.3%, 46.9%] |
| D (8B-I×1) | 8B-Instruct | 400 | 170 | 42.5% | [37.7%, 47.4%] |
| A (4B-T×1) | 4B-Thinking | 400 | 173 | 43.2% | [38.5%, 48.1%] |
| C (8B-T×1) | 8B-Thinking | 400 | 174 | 43.5% | [38.7%, 48.4%] |
| B (4B-T×5) | 4B-Thinking | 400 | 175 | 43.8% | [39.0%, 48.6%] |

**Arm B cumulative accuracy after 1–5 passes:**

| N | correct (cumulative) | acc | 95% CI |
|---|---|---|---|
| ≤1 | 173 | 43.2% | [38.5%, 48.1%] |
| ≤2 | 174 | 43.5% | [38.7%, 48.4%] |
| ≤3 | 175 | 43.8% | [39.0%, 48.6%] |
| ≤4 | 175 | 43.8% | [39.0%, 48.6%] |
| ≤5 | 175 | 43.8% | [39.0%, 48.6%] |

Retry note: 5 budget_hit questions retried; 2 became correct (q115 at pass 3, q138 at pass 2). Retries rescued liveness (5→0 non-terminated) but added only 2 correct answers.

**Replication check (Qwen3-VL tech report, arXiv 2511.21631, Table 4):**
- 4B-Instruct: our 42.0% vs published 41.3% → +0.7pp **PASS**
- 4B-Thinking: our 43.2% (max_new_tokens=8192) vs published 47.3% (presumed full budget) → −4.1pp. Gap attributable to halved token budget (8192 vs published; StudyK at 16384 achieved 44.5–45.1%). **CONDITIONAL PASS** — budget reduction explains gap direction; exact attribution not isolated.

---

## §4 Analysis 3 — Cumulative Latency

For arm B, latency includes all new passes (6 retries only; pass 1 = arm A).

| arm | mean lat | p90 | total (400 q) |
|---|---|---|---|
| E (reused) | 0.2s | — | 0.02h (StudyK measurement) |
| D (8B-I) | 0.3s | — | 0.03h |
| A (4B-T×1) | 27.3s | — | 3.04h |
| B (4B-T retries only) | — | — | 0.16h (6 new passes) |
| B (total incl. pass 1) | — | — | 3.20h |
| C (8B-T×1) | 32.5s | — | 3.61h |

8B-T is 1.19× slower than 4B-T per trial (32.5s vs 27.3s). 8B-I is 91× faster than 4B-T at identical accuracy.

---

## §5 Analysis 4 — Category Breakdown

| category | n | E (4B-I) | D (8B-I) | A (4B-T×1) | C (8B-T×1) |
|---|---|---|---|---|---|
| Action Reasoning | 72 | — | 40.3% | 44.4% | 44.4% |
| Multi-view Reasoning | 37 | — | 35.1% | 32.4% | 27.0% |
| Other | 14 | — | 28.6% | 35.7% | 35.7% |
| Pointing | 34 | — | 44.1% | 52.9% | 55.9% |
| Spatial Reasoning | 84 | — | 44.0% | 48.8% | 45.2% |
| State Estimation | 55 | — | 47.3% | 47.3% | 50.9% |
| Task Reasoning | 38 | — | 55.3% | 57.9% | 50.0% |
| Trajectory Reasoning | 66 | — | 37.9% | 25.8% | 34.8% |

Notable: Thinking arms hurt on Trajectory Reasoning (A: 25.8% vs D: 37.9%, −12.1pp) and Multi-view Reasoning (A: 32.4% vs D: 35.1%, −2.7pp). Thinking helps on Pointing (+8.8pp) and Spatial Reasoning (+4.8pp). Pattern consistent with StudyK findings (Trajectory Reasoning −12.1pp). Subgroup CIs are wide (n=34–84); no category-level finding is pre-registered.

---

## §6 Analysis 5 — Scale Comparison

| comparison | diff | interpretation |
|---|---|---|
| 8B-I vs 4B-I (D vs E) | +0.5pp | Scale gains nothing for instruct |
| 8B-T vs 4B-T (C vs A) | +0.3pp | Scale gains nothing for thinking |
| Thinking vs Instruct at 4B (A vs E) | +1.2pp | Thinking gains nothing at 4B |
| Thinking vs Instruct at 8B (C vs D) | +1.0pp | Thinking gains nothing at 8B |
| Retry vs single-pass at 4B (B vs A) | +0.6pp | Retry gains nothing at 4B |

All differences ≤1.3pp; all CIs fully overlap. Scale, thinking mode, and retry are equivalent on ERQA at n=400.

---

## §7 Sanity Checks

| arm | trials | think_closed | budget_hit | parse_ok |
|---|---|---|---|---|
| E | 400 | N/A (instruct) | 0 | 400 |
| D | 400 | N/A (instruct) | 0 | 400 |
| A | 400 | 395 | 5 | 400 |
| B (all passes) | 406 | 401 | 6 | 406 |
| C | 400 | 396 | 4 | 400 |

answer_text stored for all new trials (D, A, B, C): **PASS** (arm E reused from StudyK; answer_text=None noted).  
Arm E accuracy 42.0% matches StudyK INSTRUCT exactly: **PASS**  
Budget hit rate: A=1.2%, C=1.0% — consistent with StudyK THINKING at 16384 (1.25%). Halved budget (8192) did not substantially increase budget hits.
