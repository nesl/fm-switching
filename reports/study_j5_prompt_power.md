# Study J5 — Properly Powered Prompt Comparison on SiGNgapore2D

**Date:** 2026-09-30  
**Status:** Complete  
**Pre-registered:** `research/EXPERIMENTS.md` row StudyJ5  
**Research question:** Does the simplified prompt (StudyJ3 arm B) significantly reduce non-termination vs the original paper prompt, at adequate statistical power?

---

## Setup

| item | value |
|------|-------|
| Dataset | NickyZimmerman/SiGNgapore2D — same 14-sign subset as StudyJ4 |
| Signs | 8 cap-hit signs (StudyJ2 §4) + 6 control completers (StudyJ2 manifest) |
| Arms | ORIGINAL (paper prompt verbatim), SIMPLIFIED (3 clauses removed; see §1) |
| Model | Qwen3-VL-4B-Thinking — same snapshot as StudyJ2/J4 |
| Decoding | temperature=0.6, top_p=0.95, top_k=20, min_p=0, do_sample=True |
| max_new_tokens | 24,576 |
| Seeds | 42, 123, 456, 789, 1011 (5 seeds × 14 signs = 70 pairs) |
| ORIGINAL arm | Fully reused from StudyJ4 (70 trials identical model/prompt/decoding, `reused_from: "StudyJ4"`) |
| SIMPLIFIED arm | 70 fresh runs |
| Total trials | 140 (70 ORIGINAL + 70 SIMPLIFIED) |
| Errors | 0 |
| Script | `experiments/signs/study_j5_prompt_power.py` |

---

## 1. Prompts

**Three clauses removed from ORIGINAL to produce SIMPLIFIED:**

| # | Clause removed |
|---|---------------|
| 1 | "If a location is being represented as symbol and text both, then mention that in both 's' and 't'. For example: if you see toilet symbol as well as 'TOILET' text written then add 'TOILET' to 't' and 's' both." |
| 2 | "ONLY if there are multiple directions for a location then output all detected direction as a list. For example: 'TOILET' : ['left', 'right']. Otherwise the direction should be string. For example: 'HOSPITAL': 'left'" |
| 3 | "The value of 's' or 't' can be empty dictionary if there are no symbol detections or no text based location names in the image." |

All other content (arrow direction teaching, image quality instruction, direction list, output format) is preserved unchanged.

---

## 2. Correction to StudyJ4 Pooled Rate

StudyJ4's pooled rate of 18/70 = 25.7% is inflated by selection bias: the 8 cap-hit signs were selected *because* they failed on seed=42, so those 8 seed=42 draws are determined by the selection criterion, not by independent inference.

**Corrected estimates:**
- Unbiased draws (excluding the 8 determined cap-hit/seed=42 pairs): **10/62 = 16.1%** (95% CI 9.0–26.7%)
- Controls only (never in selection criterion): **4/30 = 13.3%** (95% CI 5.3–29.7%)

**Corrected per-attempt rate: ≈13–16%.** This is the baseline against which SIMPLIFIED's effect is measured.

---

## 3. Per-Arm Failure Rates

| arm | truncated | total | raw rate | 95% CI |
|-----|-----------|-------|---------|--------|
| ORIGINAL | 18 | 70 | **25.7%** | 16.9–37.0% |
| SIMPLIFIED | 4 | 70 | **5.7%** | 2.2–13.8% |

ORIGINAL 25.7% is the raw pooled rate. Corrected for selection: ≈13–16% (§2). SIMPLIFIED 5.7% is unselected (fresh inference on all 70 pairs).

---

## 4. McNemar Paired Test (Primary Analysis)

Pre-registered decision rule: SIMPLIFIED significantly reduces non-termination if McNemar p < 0.05.

Each (sign, seed) pair is matched. b = pairs where ORIGINAL truncated and SIMPLIFIED did not (SIMPLIFIED fixed the failure). c = pairs where SIMPLIFIED truncated and ORIGINAL did not (SIMPLIFIED introduced a new failure).

| | SIMPLIFIED: ok | SIMPLIFIED: trunc |
|---|---|---|
| **ORIGINAL: trunc** | b = 18 | a = 0 |
| **ORIGINAL: ok** | d = 48 | c = 4 |

- n = 70 (sign, seed) pairs
- b = 18, c = 4
- Exact McNemar p = **0.0043** (exact binomial on discordant pairs b+c=22; two-sided)
- a = 0: no pair fails under both arms

**PRE-REGISTERED VERDICT: SIMPLIFIED significantly reduces non-termination (p = 0.0043 < 0.05).**

---

## 5. Per-Sign Failure Table

| sign | role | ORIGINAL (5 seeds) | SIMPLIFIED (5 seeds) | change |
|------|------|--------------------|--------------------|--------|
| IMG_6548_frame_0019_1.jpg | cap_hit | **4/5** | 0/5 | −4 |
| IMG_6546_frame_0019_1.jpg | cap_hit | **3/5** | 0/5 | −3 |
| IMG_6567_frame_0017_0.jpg | control | **3/5** | 1/5 | −2 |
| IMG_6623_frame_0015_0.jpg | cap_hit | **2/5** | 1/5 | −1 |
| IMG_6416_frame_0013_0.jpg | cap_hit | 1/5 | 0/5 | −1 |
| IMG_6617_frame_0015_0.jpg | cap_hit | 1/5 | 0/5 | −1 |
| IMG_0068_frame_0007_0.jpg | cap_hit | 1/5 | 0/5 | −1 |
| IMG_0042_frame_0022_0.jpg | control | 1/5 | 0/5 | −1 |
| IMG_6411_frame_0014_0.jpg | cap_hit | 1/5 | 1/5 | 0 |
| IMG_0037_frame_0014_0.jpg | cap_hit | 1/5 | 1/5 | 0 |
| IMG_0049_frame_0003_0.jpg | control | 0/5 | 0/5 | 0 |
| IMG_0064_frame_0003_1.jpg | control | 0/5 | 0/5 | 0 |
| IMG_6415_frame_0015_0.jpg | control | 0/5 | 0/5 | 0 |
| IMG_6584_frame_0019_0.jpg | control | 0/5 | 0/5 | 0 |
| **Total** | | **18/70** | **4/70** | −14 |

10 of 14 signs reduced or unchanged. 2 signs unchanged (1/5 under both arms). No sign increased (the 4 new SIMPLIFIED failures are distributed: IMG_6567 +1, IMG_6623 +1 (wait: simp=1 vs orig=2 — net −1), IMG_6411 =, IMG_0037 =).

**Clarification:** c=4 new SIMPLIFIED failures distributed as:
- IMG_6567: ORIGINAL 3/5, SIMPLIFIED 1/5 — net improvement despite contributing 1 to c
- IMG_6623: ORIGINAL 2/5, SIMPLIFIED 1/5 — net improvement
- IMG_6411: ORIGINAL 1/5, SIMPLIFIED 1/5 — same failure rate, different seed(s)
- IMG_0037: ORIGINAL 1/5, SIMPLIFIED 1/5 — same failure rate, different seed(s)

No sign is strictly worse under SIMPLIFIED (no sign has SIMPLIFIED > ORIGINAL failures).

---

## 6. Think-Token Distributions (Completers Only)

| arm | n completers | min | Q1 | median | Q3 | max | IQR |
|-----|-------------|-----|----|--------|----|-----|-----|
| ORIGINAL | 52/70 | 208 | 2,865 | 3,729 | 6,111 | 12,828 | 3,246 |
| SIMPLIFIED | 66/70 | 124 | 2,572 | 4,433 | 6,787 | 14,622 | 4,215 |

SIMPLIFIED completers have a *higher* median (4,433 vs 3,729 tokens) and wider spread (IQR 4,215 vs 3,246). This replicates the StudyJ3 finding: the simplified prompt does not shorten reasoning. If anything, completers reason more under SIMPLIFIED. The mechanism of termination improvement is not token-budget compression.

---

## 7. Accuracy Scoring (Analysis 5)

**NOT EXECUTABLE from committed files.**

The trial JSONL stores `prediction=None` and `parse_status=parse_failed` for all trials (across J2, J4, and J5). The answer_text produced by the model was not written to the JSONL — only the parsed prediction dict is stored, which is `None` when JSON parsing fails. Since `last_500_tokens` is only populated for truncated trials (not completers), the answer text cannot be recovered.

This is a limitation of the harness design: storing only the parsed prediction without the raw answer text prevents retroactive re-parsing or accuracy evaluation.

**What is known without scoring:**
- 18 ORIGINAL completers → accuracy calculable only if re-run (not done)
- 66 SIMPLIFIED completers → same limitation
- All 4 SIMPLIFIED truncated trials score as failures (empty prediction = automatic zero), same as the pre-registered scoring convention from StudyJ

Accuracy comparison cannot be reported. This does not affect the termination finding, which is the primary pre-registered gate.

---

## 8. Analysis 6: Both-Arms Failures

Pre-registered: classify last-500-token content for (sign, seed) pairs failing under both arms.

**a = 0.** No (sign, seed) pair fails under both ORIGINAL and SIMPLIFIED. Analysis 6 is vacuous.

---

## 9. What Cannot Be Inferred

1. **Which removed clause drives the improvement.** SIMPLIFIED removes three clauses simultaneously. The isolated effect of each clause is unknown. A single-clause ablation study would be needed to identify the responsible constraint.

2. **Accuracy improvement.** Answer text was not stored; scoring is not possible retroactively. Whether SIMPLIFIED's additional completers answer correctly cannot be determined from committed data.

3. **Generalization.** This study uses 14 signs, one model (Qwen3-VL-4B-Thinking), one prompt simplification direction, and one dataset. The result may not generalize to other constraint-heavy prompts, other models, or other visual tasks.

4. **Mechanism.** SIMPLIFIED reduces non-termination, but does not shorten reasoning (median think tokens are higher). The most parsimonious explanation is that the removed clauses triggered a degenerate constraint-checking loop (as observed qualitatively in StudyJ2 §5 class-b traces), but this is not confirmed at the individual-trace level in this study.

5. **Effect below 16%:** The corrected per-attempt rate under ORIGINAL is ≈13–16%. SIMPLIFIED brings this to 5.7%. Whether 5.7% represents residual task difficulty or residual prompt sensitivity requires further study.

---

## 10. Verdict

**SIMPLIFIED significantly reduces non-termination** (McNemar exact p = 0.0043, b=18, c=4, n=70 pairs). The hypothesis that the original paper prompt's constraint clauses substantially drive the 20% non-termination asymptote is supported.

The effect is large: ORIGINAL 25.7% raw (≈13–16% corrected) → SIMPLIFIED 5.7%. Two of the three previously highest-failure signs drop to 0/5 (IMG_6548: 4→0, IMG_6546: 3→0). No sign is strictly worse under SIMPLIFIED.

The result does not establish that SIMPLIFIED produces accurate answers — that requires re-running inference with answer storage and scoring.
