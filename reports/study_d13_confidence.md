# StudyD13: does 4B answer confidence separate evidence-limited from capability-limited questions?

**E-id:** StudyD13 (pre-registered 2026-11-04, before any GPU run). **Host:** h100nvl GPU 2 (UUID GPU-4f1d7e47…), run 11:08–11:23 on 2026-11-04.

**Status:** COMPLETE. The gate passed, mechanism verification was recorded before the analysis, and the consistency checks pass.

**Strata are ORACLE labels:** they come from the MCQ answer interval and aren't observable when a request arrives. No E24/E24b/E24c or Thinking T0.6 result is used.

## Results (observations)

### Gate: rerun of H1 with logprobs

- **Letters:** 845/845 = **100.0 %** match StudyClean H1 (gate ≥ 99 %).
- **Prompt tokens:** 845/845 equal to H1.
- **Errors:** 0.
- **Letter logprobs:** every row has its answer letter at generated position 0, and that token is the predicted letter in 845/845. The A–E letters hold ≥ 0.99957 of the top-20 probability mass (median 0.99998), so renormalising over A–E changes almost nothing.

**Confidence** = p(predicted letter) renormalised over A–E. Range 0.256–1.000; mean 0.712.

**Mean confidence by stratum:**

| stratum | mean confidence |
|---|---|
| OLDER | 0.705 |
| OVERLAP | 0.680 |
| INSIDE | 0.709 |
| QT_LE_120 | 0.759 |

### AUROC of 4B confidence (video-clustered bootstrap, 2,000, seed 0)

An AUROC below 0.5 means *low* confidence predicts the positive class.

| target | n (pos) | AUROC [95 % CI] |
|---|---|---|
| OLDER vs rest, all 845 | 845 (97) | **0.487** [0.430, 0.545] |
| OLDER vs OVERLAP + INSIDE (qt > 120) | 678 (97) | **0.507** [0.445, 0.570] |
| 32B correct given 4B wrong (K3 ✓ among H1 ✗) | 570 (124) | **0.476** [0.418, 0.532] |

All three CIs contain 0.5.

### Within confidence quintiles (169 each)

- **32B gain** = K3 − H1.
- **History gain** = K1 − K3.
- **OLDER − INSIDE** uses the clustered bootstrap.

| Q | conf range | 4B acc | OLDER n: 32B gain / hist gain | INSIDE n: 32B gain / hist gain | OLDER−INSIDE 32B gain [CI] | OLDER−INSIDE hist gain [CI] |
|---|---|---|---|---|---|---|
| 1 | 0.256–0.499 | 21.9 % | 19: −21.1 / +10.5 | 85: +15.3 / −7.1 | **−36.3 [−58.6, −14.0]** | +17.6 [−10.1, +42.9] |
| 2 | 0.499–0.631 | 28.4 % | 19: +10.5 / +15.8 | 82: +6.1 / −6.1 | +4.4 [−10.7, +24.8] | +21.9 [−9.6, +52.4] |
| 3 | 0.633–0.802 | 22.5 % | 19: +21.1 / +15.8 | 90: +5.6 / −4.4 | +15.5 [−4.5, +38.9] | +20.2 [−2.2, +45.8] |
| 4 | 0.802–0.962 | 30.2 % | 28: +7.1 / +25.0 | 80: −2.5 / −1.3 | +9.6 [−7.3, +27.1] | **+26.3 [+5.9, +49.3]** |
| 5 | 0.963–1.000 | 59.8 % | 12: 0.0 / +16.7 | 77: 0.0 / −10.4 | 0.0 [−9.1, +8.5] | +27.1 [−6.0, +60.5] |

**Raw 32B win/loss counts behind the 0.0 gains in Q5:**
- **INSIDE:** 6 wins / 6 losses.
- **QT_LE_120:** 5 / 5.
- **OLDER:** 0 / 0; all 12 letters agree.

These are balanced counts, not a constant. In Q1 OLDER the counts are 0 wins / 4 losses (n = 19).

## Interpretation (separate from the observations)

1. **4B confidence does not separate the strata.** OLDER, the questions whose evidence lies outside the 4B's 120 s window, are as confident as INSIDE ones (AUROC 0.49–0.51). Confidence also does not identify the questions the 32B rescues (0.48). On this evidence, 4B confidence isn't a usable signal for "escalate for history" vs "escalate for capability".
2. **History gain is consistent across confidence levels.** OLDER − INSIDE history gain is positive in every quintile (+18 to +27 pp), but only Q4's CI excludes 0. This is the known OLDER-vs-INSIDE history effect (K1 − K3: +17.5 vs −5.8 pp) appearing at every confidence level; it isn't something confidence adds.
3. **One quintile cell clears zero: Q1 OLDER − INSIDE on 32B gain (−36 pp).** It comes from 19 OLDER questions (0 wins, 4 losses). Ten quintile × outcome cells were examined with no multiplicity correction, so this is not presented as a finding.
4. **Null classification (CLAUDE.md Rule 2): real negative** for the separation claim. The signal varies (0.26–1.00), the strata and outcomes vary, and the negative control behaves (Step 4). The signal was present and exercised; it doesn't separate.

## Mechanism verification (recorded before the analysis was run)

**Step 1, causal chain.** FORMULATION.md §Regime uncertainty requires the runtime to act on an implementable estimate ŵ (an online probe), with oracle labels as a ceiling only. The claim under test:

- If the 4B's answer distribution is flatter when the evidence is not in its input (an OLDER question, where it lacks the frames),
- then low confidence marks evidence-limited questions, where history (RICH; §State objects: fidelity decides which queries can be answered) should help more than a larger model;
- whereas confident-but-wrong answers mark capability-limited questions, where the 32B should help.

| causal link | implementing quantity | value / range | varies as expected? | evidence |
|---|---|---|---|---|
| 4B answer distribution | p(pred) over A–E at the first letter token | 0.256–1.000 | yes (non-constant) | quintile ranges above |
| evidence missing from the 4B input | oracle stratum OLDER (= K3 evidence_covered false, asserted) | 97 / 845 | yes | StudyClean assertion reused |
| history helps OLDER | K1 − K3 per question | OLDER +17.5, INSIDE −5.8 pp | yes | `study_d13_interaction` result |
| 32B helps capability-limited | K3 − H1 per question | ALL +5.8 pp | yes | StudyClean H1 − K3 |

No link is ABSENT or CONSTANT.

**Step 3, one traced request.** For `1e0f1f39…` (qt 78 s, QT_LE_120):
- **Input:** 79 frames at 608×480, 12,469 prompt tokens.
- **Output:** "C", with logprobs C −0.139, D −2.139, B −4.764, E −5.889, A −7.889.
- **Confidence:** 0.870.
- **Gains:** 32B gain = K3 − H1 on that question; history gain = 0 (identical inputs).

**Step 4, negative control.** In QT_LE_120, K1 and K3 send identical frames, so the history gain must be exactly 0 in every quintile. Observed: 0.0 in all five (n = 26/33/27/23/58). This passes, and shows the per-quintile machinery doesn't manufacture history effects.

**Step 5, alternative explanation.** A non-zero AUROC could have come from confidence tracking *question time* (longer videos → harder), not evidence location. Restricting to qt > 120 gives 0.507, ruling this out as a source of masked signal; it is also null.

## Results consistency check

| # | check | result |
|---|---|---|
| 1 | Cross-check | **PASS.** D13 accuracy and letters are identical to H1 (845/845); K1 − K3 by stratum reproduces the audit (+17.53 / +10.18 / −5.80). |
| 2 | Plausibility | **PASS.** Not a latency study; wall time 14 min for 845 requests at concurrency 8, consistent with StudyClean H1. |
| 3 | Distribution | **PASS.** Confidence spans 0.256–1.000; the zeros in Q5 are balanced win/loss counts (shown). |
| 4 | Definitions | **PASS.** Strata use StudyClean's `stratum()` with the asserted 97/167/414/167; K1/K3/H1 are the canonical cells. |
| 5 | Claim linkage | **PASS.** Bears on FORMULATION.md §Regime uncertainty (implementable ŵ). It weakens 4B self-confidence as that estimator for the history-vs-capability split. |
| 6 | Proxy validity | **PASS (with stated limit).** Confidence is used as a proxy for "evidence present"; the oracle stratum is the ground truth and isn't observable online. |

**Input / stack / decoding match:**
- D13 vs H1: identical in all three, except that D13 is a non-streaming request with logprobs.
- K1/K3 vs H1: same stack and decoding; K3 has identical input to H1; K1 has different input (RICH).

## Files

| file | contents |
|---|---|
| `experiments/cost/study_d13_vllm.py` | GPU rerun |
| `experiments/cost/study_d13_analyse.py` | analysis |
| `results/cost/study_d13/study_d13_requests_h100nvl.jsonl` | per-request rows with logprobs |
| `results/cost/study_d13/study_d13_run_meta_h100nvl.json` | run meta, including the gate |
| `results/cost/study_d13/study_d13_results_h100nvl.json` | analysis results |
