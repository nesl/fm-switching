# E27 — Maintenance-Mechanism Kill Test

**Date:** 2026-08-20  
**Model:** Qwen/Qwen2.5-7B-Instruct (`qwen7b`)  
**Device:** NVIDIA RTX A6000 (flash, GPU 1)  
**Outcome: B** — recursive summarization does not kill the cost inversion; output-generation latency dominates regardless of input-token savings.

---

## 1. Motivation

E24c found that window-10 warm-append costs ~0.066 s while summary-200 full-history regeneration costs ~78 s at L = 32 k tokens — an ~80× lifecycle-cost inversion. E27 asks: is this inversion an artifact of regenerating from full conversation history each time, or is it structural? Specifically, if we switch to *recursive* summarization (compress [prev\_summary + new turns] instead of the full history), the input shrinks from O(L) to O(summary + delta). If recursive reduces input below ~20 % of full-history, the inversion might narrow to the point where summary state becomes cost-competitive.

**Decision rules (pre-registered):**  
- **A:** recursive cheap (token ratio < 0.20) AND quality holds (accuracy gap ≤ 0.03) → inversion narrows, summary competitive  
- **B:** recursive cheap AND quality drifts (gap > 0.03) → token savings real but quality costs them  
- **C:** periodic-K dominates → even simpler approach better than recursive  
- Fallback B: inversion structural (recursive not cheap enough, quality mostly holds)

---

## 2. Experiment design

**Workloads:** LoCoMo (n = 282 cat=1 questions, 10 conversations, 19–32 sessions each) and EgoSchema (60 clips, 16 captions each).

**Modes:** `full_regen`, `recursive`, `periodic_2`, `periodic_5`, `periodic_10` × budgets `sum80` and `sum200` = 10 conditions.

**Checkpoints:** 25 / 50 / 75 / 100 % of session age. LoCoMo uses evidence-gating (question included at checkpoint k only if all D\_N have N ≤ k). EgoSchema checkpoints at [4, 8, 12, 16] captions.

**Recursive protocol:** input = [previous summary + new sessions since last checkpoint]; output = updated summary at target budget.

**Sanity gate:** `full_regen` accuracy at 100 % must be within ±0.05 of phase0a reference (sum80 = sum200 = 0.099).

---

## 3. Sanity check

| Budget | Accuracy @100 % | Reference | Diff | Status |
|--------|----------------|-----------|------|--------|
| sum80  | 0.120 | 0.099 | +0.021 | **PASS** |
| sum200 | 0.120 | 0.099 | +0.021 | **PASS** |

Both within tolerance. The +0.021 uplift vs phase0a is within expected sampling variance across the 10-conv subset run order.

---

## 4. LoCoMo accuracy by session coverage

| Mode / Budget | 25 % | 50 % | 75 % | 100 % |
|---------------|------|------|------|-------|
| full history | 0.308 | 0.469 | 0.397 | **0.400** |
| window-10 | 0.308 | 0.469 | 0.241 | **0.230** |
| full\_regen sum80 | 0.077 | 0.063 | 0.069 | **0.120** |
| recursive sum80 | 0.077 | 0.063 | 0.069 | **0.120** |
| periodic\_2 sum80 | 0.077 | 0.063 | 0.069 | **0.120** |
| periodic\_5 sum80 | 0.077 | 0.063 | 0.069 | **0.120** |
| periodic\_10 sum80 | 0.077 | 0.063 | 0.069 | **0.090** |
| full\_regen sum200 | 0.308 | 0.125 | 0.069 | **0.120** |
| recursive sum200 | 0.308 | 0.094 | 0.138 | **0.110** |
| periodic\_2 sum200 | 0.308 | 0.125 | 0.069 | **0.120** |
| periodic\_5 sum200 | 0.308 | 0.125 | 0.069 | **0.120** |
| periodic\_10 sum200 | 0.308 | 0.125 | 0.069 | **0.090** |
| blind | — | — | — | **0.080** |

**Key reading:** recursive and full\_regen are indistinguishable at 100 % for sum80 (gap = 0.000) and within noise for sum200 (gap = 0.010, within ±0.03 tolerance). periodic\_10 shows slight quality degradation (0.09 vs 0.12) — caching stale summaries for ≥10 sessions loses facts.

---

## 5. Lifecycle cost analysis (LoCoMo)

| Mode × Budget | Mean input tokens | Token ratio vs full\_regen | Mean measured latency (s) | Latency ratio |
|---|---|---|---|---|
| full\_regen sum80 | 11,644 | 1.000 | 8.57 | 1.000 |
| full\_regen sum200 | 11,648 | 1.000 | 13.38 | 1.000 |
| recursive sum80 | 4,806 | **0.413** | 5.67 | **0.661** |
| recursive sum200 | 4,882 | **0.419** | 10.12 | **0.756** |
| periodic\_2 sum80 | 11,644 | 1.000 | 8.57 | 1.000 |
| periodic\_2 sum200 | 11,648 | 1.000 | 13.38 | 1.000 |
| periodic\_5 sum80 | 11,745 | 1.009 | 8.66 | 1.011 |
| periodic\_5 sum200 | 11,749 | 1.009 | 13.53 | 1.011 |
| periodic\_10 sum80 | 9,589 | 0.823 | 7.65 | 0.893 |
| periodic\_10 sum200 | 9,593 | 0.823 | 11.44 | 0.855 |

**Window-10 warm-append reference: 0.066 s**

Recursive reduces input tokens by **~58 %** (ratio 0.42) but reduces measured latency by only **24–34 %** (ratio 0.66–0.76). This is because output-generation (decoding ~300 tokens for sum200) costs ~9–11 s regardless of input length; the input-prefill saving (~3–4 s) is partially recovered but decode dominates.

**Inversion ratio (recursive vs window-10):**  
- sum200: 10.12 / 0.066 = **153×**  
- sum80: 5.67 / 0.066 = **86×**

The lifecycle-cost inversion survives recursive summarization. Even with 58 % fewer input tokens, the refresh cost is 86–153× higher than window-10 warm-append.

---

## 6. EgoSchema results

### Accuracy at 100 % (16 captions)

| Mode / Budget | Accuracy |
|---|---|
| full history | 0.367 |
| blind | 0.150 |
| full\_regen sum80 | 0.367 |
| recursive sum80 | **0.450** |
| periodic\_5 sum80 | 0.400 |
| periodic\_10 sum80 | 0.367 |
| full\_regen sum200 | 0.450 |
| recursive sum200 | 0.400 |
| periodic\_5 sum200 | 0.350 |
| periodic\_10 sum200 | 0.450 |

Notable: recursive sum80 (0.450) matches or exceeds full\_regen sum200 (0.450) — the more compact recursive summary at sum80 budget performs as well as a larger full-history summary, suggesting EgoSchema captions are more compressible than LoCoMo dialogue.

### Lifecycle cost (EgoSchema)

| Mode × Budget | Mean input tokens | Token ratio | Mean measured latency (s) | Latency ratio |
|---|---|---|---|---|
| full\_regen sum80 | 681 | 1.000 | 2.45 | 1.000 |
| full\_regen sum200 | 688 | 1.000 | 5.19 | 1.000 |
| recursive sum80 | 340 | **0.499** | 2.12 | **0.865** |
| recursive sum200 | 403 | **0.586** | 4.78 | **0.921** |
| periodic\_5 sum80 | 551 | 0.809 | 2.38 | 0.971 |
| periodic\_5 sum200 | 558 | 0.811 | 4.90 | 0.944 |
| periodic\_10 sum80 | 682 | 1.001 | 2.35 | 0.959 |
| periodic\_10 sum200 | 689 | 1.001 | 5.00 | 0.963 |

EgoSchema captions are short (688 tokens total for 16 captions), so all modes start with small inputs. Recursive achieves 2× token reduction (ratio 0.50–0.59) but only 8–14 % latency reduction — output generation still dominates. The inversion vs window-10 (0.066 s) is 2.12/0.066 = **32×** for recursive sum80 and 4.78/0.066 = **72×** for recursive sum200.

---

## 7. Decision

**Token ratio for recursive sum200 = 0.419 > 0.20 threshold → is\_cheap = False.**  
**Quality gap at 100 %: sum80 = 0.00, sum200 = 0.01 → quality\_holds = True.**  
**Periodic\_10 token ratio = 0.82 > recursive ratio (0.42) → C does not apply.**

**Outcome: B (fallback)** — recursive reduces tokens 2.4× but cannot reach the 5×+ threshold where prefill savings would dominate. Decode time (output generation of 300-token summaries) is roughly constant at 7–B scale regardless of input length. The inversion is *structural*: any approach that generates a new summary token-for-token costs 86–153× more than window appending, independent of how the input is assembled.

---

## 8. Implications for the thesis

E24c showed that lifecycle-aware fidelity selection (fidelity\_first\_lifecycle) beats joint placement-aware policies because it accounts for the 80× cost inversion between window-10 and summary refresh. E27 confirms this inversion is not an implementation artifact:

1. **Recursive summarization does not rescue summary state** — the output side, not the input side, dominates refresh cost.
2. **The inversion is decode-bound**: at 7B scale, generating a 300-token summary takes ~9–13 s; this is fixed regardless of whether the input is 4 k (recursive) or 12 k (full-history) tokens.
3. **Quality is preserved by recursive** (gap ≤ 0.01 at 100 % checkpoint) — so there is no quality excuse for not using recursive. But recursive doesn't change the cost landscape enough to flip the inversion.
4. **Periodic-K is not a shortcut**: periodic\_10 saves 18 % of tokens but loses 2–3 pp accuracy (0.09 vs 0.12 at 100 %), and its refresh events still cost 7.65–11.44 s.

The practical consequence: summary state maintenance cannot be made cost-competitive with window-10 via summarizer engineering alone, at 7B scale on A6000 hardware. Window-10 remains the only regime where session-state refresh is cheap enough for high-frequency placement flexibility.

---

## 9. Files

| File | Description |
|---|---|
| `experiments/fidelity/e27_maintenance.py` | Experiment script (resume logic, fixed lifecycle cost) |
| `experiments/fidelity/e27_merge_results.py` | Post-hoc merge script for LoCoMo + EgoSchema results |
| `results/fidelity/e27_maintenance/e27_maintenance_qwen7b.json` | Main result (merged, corrected lifecycle cost) |
| `results/fidelity/e27_maintenance/per_step/locomo_{conv_id}.json` | Per-conv summarization data (10 files) |
| `results/fidelity/e27_maintenance/quality/locomo_{conv_id}_cp{0-3}.json` | Per-checkpoint QA results (40 files) |
| `results/fidelity/e27_maintenance/per_step/ego_{clip_id}.json` | Per-clip EgoSchema data (60 files) |
| `figures/fidelity/e27_drift_curves.pdf` | LoCoMo accuracy drift curves |
| `figures/fidelity/e27_lifecycle_cost.pdf` | Refresh cost bar chart by mode × budget |
