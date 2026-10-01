# Study M Smoke Test — T-OFF Results and NO-GO Decision

**Date:** 2026-10-01  
**Status:** COMPLETE — FLOOR CLAUSE FIRES → NO-GO  
**Pre-registered rule:** `research/EXPERIMENTS.md` row StudyM  
**T-OFF model:** Qwen3-8B snap `b968826d9c46dd6066d109eabc6255188de91218`  
**Trial file:** `results/ts/study_m_smoke/study_m_smoke_trials.jsonl`

---

## 1. Runtime Threshold Event

The original full smoke test (540 trials, T-OFF + T-ON) hit the pre-registered 12h stop condition at trial 10:

- Mean latency over first 10 trials: 87.5s (T-OFF ~0.8s, T-ON ~66–341s)
- Projected remaining: 530 trials × 87.5s = **12.9h > 12h threshold**
- Decision (per user instruction 2026-10-01): run T-OFF arm only; do not raise threshold; run T-ON only if floor clause does not fire

---

## 2. Scoring Sanity Check (pre-analysis)

Performed before T-OFF run on the 10 trials from the aborted full run.

**correct_index → letter mapping:** `chr(ord("A") + correct_index)` at `experiments/ts/study_m_smoke.py:234`. Confirmed correct: 0→A, 1→B, 2→C, 3→D.

**Bug (a) — special tokens in answer text:** `<|im_end|>` present in all 10 stored `raw_output` fields (from `skip_special_tokens=False` decoding). The `parse_answer()` regex `\b([A-D])\b` extracts the letter correctly regardless — all 10 `parsed_answer` and `correct` fields are correct; no re-scoring required. Fixed in script before T-OFF run: added post-decode stripping of `<|im_end|>`, `<|im_start|>`, `<|endoftext|>` from `answer_text` and `think_content`.

**Bug (b) — unclosed think with n_think_tokens=0:** None found (0 affected trials). ✓

---

## 3. T-OFF Results

**Trials:** 270 (30 series × 3 stages × 3 seeds). All `parse_status=ok` (0 parse failures). Wall time: ~6 min.

### 3a. Per-stage trial-level accuracy

| stage | correct | n | accuracy | 95% Wilson CI |
|---|---|---|---|---|
| what_happened | 16 | 90 | 17.8% | 11.2%–26.9% |
| how_happened | 18 | 90 | 20.0% | 13.0%–29.4% |
| suggested_fix | 31 | 90 | 34.4% | 25.4%–44.7% |
| **All** | **65** | **270** | **24.1%** | **19.2%–29.9%** |

Chance = 25%.

### 3b. Reasoning items (How + Fix) — pre-registered gate metric

**Item-level accuracy** (mean correctness over 3 seeds per item, 60 items):

| stage | item-level accuracy | 95% Wilson CI |
|---|---|---|
| how_happened | 20.0% | 9.5%–37.3% |
| suggested_fix | 34.4% | 20.1%–52.3% |
| **How+Fix pooled** | **27.2%** | **17.6%–39.6%** |

Pre-registered floor clause: NO-GO if T-OFF reasoning accuracy ≤ 30%.

**27.2% ≤ 30% → FLOOR CLAUSE FIRES.**

### 3c. Perception items (What Happened) — descriptive

Item-level accuracy: 17.8% (Wilson CI 8.0%–34.8%), n=30 items. Below chance (25%).

---

## 4. Answer-Letter Distribution (T-OFF)

| letter | count | share |
|---|---|---|
| A | 102 | 37.8% |
| B | 27 | 10.0% |
| C | 58 | 21.5% |
| D | 83 | 30.7% |

Expected at chance: 25% each. Notable A over-representation (+12.8pp) and B under-representation (−15.0pp). Letter bias does not affect the floor-clause determination (the clause is on accuracy, not on letter distribution).

By stage:
- what_happened: A=43, B=11, C=8, D=28
- how_happened: A=24, B=12, C=20, D=34
- suggested_fix: A=35, B=4, C=30, D=21

---

## 5. Seed Agreement (T-OFF)

Over 90 items (all stages):

| outcome | items | share |
|---|---|---|
| all 3 seeds correct | 16 | 17.8% |
| all 3 seeds wrong | 64 | 71.1% |
| mixed (seeds disagree) | 10 | 11.1% |
| **all 3 seeds agree** | **80** | **88.9%** |

Low seed noise: 88.9% of items have unanimous across-seed agreement. The 10 mixed items are not concentrated in any stage.

---

## 6. Verdict

**FLOOR CLAUSE FIRES: smoke test is NO-GO. T-ON not needed.**

T-OFF (Qwen3-8B, no thinking) achieves 27.2% item-level accuracy on reasoning items (How+Fix), which is ≤ 30% pre-registered floor. The model is performing near or below chance (25%) on all three stages. Running T-ON under these conditions would not be interpretable: if T-ON also performs near chance, the result is a null that cannot be attributed to the mechanism (thinking vs. no-think) rather than floor-level task performance by both arms. The pre-registered rule correctly excludes this case.

**Interpretation of the floor:** The SenTSR-Bench reasoning items require identifying causal fault mechanisms and remediation steps from raw sensor time series. T-OFF (instruct mode, text-only, 8B) cannot reliably perform these tasks. This is consistent with the prior repo gate findings (StudyK, StudyJ) where no-think performance on complex reasoning tasks was weak.

**Next step:** The smoke test design does not support a conclusion about whether thinking helps — the no-think baseline is too weak to constitute a meaningful comparison. Options: (1) use a stronger no-think baseline (e.g., few-shot CoT in the prompt, or a larger model), or (2) re-gate with a different workload where no-think is above floor. Neither is a decision for this session; record as INCONCLUSIVE in the sense that the mechanism was not tested, not as a settled negative.

---

## 7. What Was Not Run

- T-ON: not run (floor clause fired, T-ON not required by pre-registered rule)
- A1–A4 (flip structure, seed noise, variance decomposition, think-token analysis): not executable without T-ON trials
- Vision arms: deferred (full-scale plan)
- TSRBench: deferred (full-scale plan)

---

## 8. Implementation Issues Discovered

| issue | severity | status |
|---|---|---|
| `<|im_end|>` left in answer_text (cosmetic; parse and score unaffected) | cosmetic | fixed in script before T-OFF run |
| T-OFF answer_text sent to think_content instead of answer_text (parse_failed for all T-OFF trials in aborted run) | scoring bug | fixed; aborted trial file deleted; T-OFF re-run clean |
| 12h projection at trial 10 (T-ON think time 67–341s dominates mean) | design | recorded as threshold event; T-OFF-only decision made |
