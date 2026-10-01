# Study M — Plan: Reasoning Gate on Sensor Time-Series

**Date:** 2026-10-01  
**Status:** PENDING APPROVAL — do not run inference until approved  
**Pre-registered:** `research/EXPERIMENTS.md` row StudyM  
**Research question:** Does reasoning mode (thinking on) improve accuracy on a real CPS sensor time-series workload vs instruct/no-think at deployable 8B scale?

---

## STOP CONDITIONS TRIGGERED

Two stop conditions from the spec apply before inference can begin:

**STOP 1 — ECG excluded from text arms (encoding budget exceeded)**  
TSRBench `qualitative_decision` (ECG) contains 12-channel × 1000-sample series → ~70,000 tokens when text-serialized. Qwen3-8B has a 32K context window; this exceeds it by 2×. ECG is excluded from T-OFF and T-ON arms. It remains usable for vision arms (V-INS/V-THK) via rendered plot. This is a methodological scoping decision requiring approval before proceeding.

**STOP 2 — GPU time projection exceeds 24 hours**  
With the feasible scope (SenTSR-Bench 330 items + TSRBench physical-sensor text-feasible 450 items = 780 text items; 1,115 vision items), GPU time for 4 arms × 3 seeds is estimated at 80–207h (see §5). Even with SenTSR-Bench alone, the T-ON and V-THK arms with 16K max_new_tokens may exceed 24h depending on actual think-token rate, which is unknown for this workload. A calibration pilot (see §6) is proposed to resolve this uncertainty before the full run.

---

## 1. Dataset Audit

### 1.1 SenTSR-Bench

| field | value |
|---|---|
| arXiv | 2602.19455 (AISTATS 2026) |
| License | CC-BY-NC-4.0 |
| Download | HuggingFace `ZLHe0/SenTSR-Bench` — publicly available, no login required |
| Series | 110 multivariate industrial sensor time series |
| Channels | 3: Acceleration, Velocity, Temperature |
| Series length | 123–170 hourly samples (range across series; typical 154–170) |
| Questions | 330 total: 4-option MCQ (A/B/C/D), `correct_index` ∈ {0,1,2,3} |
| Stage split | 110 What Happened + 110 How Happened + 110 Suggested Fix (one triplet per series) |
| Source domain | Real-world, de-identified warehouse machine monitoring operations |

**Text serialization token estimate:** ~1,132–1,260 tokens per series (3 channels × ~168 values × "ChannelName: v1, v2, ... vN\n" format at 4dp). Within budget for all text arms.

### 1.2 TSRBench

| field | value |
|---|---|
| arXiv | 2601.18744 (ICML 2026) |
| Download | HuggingFace `umd-zhou-lab/TSRBench` — publicly available, no login required |
| Total problems | 4,125 across 15 tasks |

**Physical-sensor tasks (confirmed from data files):**

| task file | dimension | domain field | n | sensor type | text tokens (per series) | text-feasible |
|---|---|---|---|---|---|---|
| `etiological_reasoning.jsonl` | Reasoning | Human Activity | 150 | Tri-axial accelerometer, 30 samples, UCI HAR | ~52–62 | ✓ |
| `causal_reasoning.jsonl` | Reasoning | Nature | 300 | River runoff sensors, 5 channels, Elbe Flood dataset | ~1,531–1,695 | ✓ |
| `qualitative_decision.jsonl` | Decision | (no domain field) | 335 | ECG (PTB-XL), 12 leads × 1000 samples | ~70,000 | **NO** — exceeds 32K ctx |

**Non-physical-sensor tasks (excluded):**

| task | domain | reason for exclusion |
|---|---|---|
| `quantitative_decision` | Finance | not physical sensor |
| `perception` | generic (no domain) | not physical sensor (synthetic/algorithmic patterns) |
| `etiological_reasoning / Astrophysics` | Astrophysics | telescope, not CPS sensor |
| `abductive_reasoning` | NBA game data | not physical sensor |
| `deductive_reasoning` | Chaotic Physics | synthetic |
| `inductive_reasoning` | Astronomy / Meteorology | ambiguous provenance, excluded per spec |
| `numerical_reasoning` | Agriculture, Traffic, Energy, etc. | ambiguous provenance, excluded per spec |
| `temporal_relation_reasoning` | Economic indicators | not physical sensor |
| `time_series_forecasting` | Finance | not physical sensor |
| `event_prediction` | Weather | ambiguous (model output not direct sensor) |

**Note on FoG (Freezing of Gait):** The paper abstract mentions FoG as a physical-sensor domain, but no `FoG` or `freezing` domain label appears in any JSONL. The 150 "Human Activity" entries are tri-axial accelerometer (HAR). FoG is absent or merged into HAR without a separate label — included in the 150 HAR count.

---

## 2. Model Availability

| arm | model | cached | snapshot hash |
|---|---|---|---|
| T-OFF | Qwen3-8B (text) | **NOT CACHED** | — |
| T-ON | Qwen3-8B (text) | **NOT CACHED** | — |
| V-INS | Qwen3-VL-8B-Instruct | ✓ | `0c351dd01ed87e9c1b53cbc748cba10e6187ff3b` |
| V-THK | Qwen3-VL-8B-Thinking | ✓ | `92f3c4b4feadd3a016ef468d103bb5f58b2a2c6b` |

**Action required:** Qwen3-8B (HuggingFace `Qwen/Qwen3-8B`) must be downloaded before inference (~16 GB). Approve download as part of this plan.

---

## 3. Encoding

### Text arms (T-OFF, T-ON)

Series serialized as:
```
{ChannelName}: {v1:.4f}, {v2:.4f}, ..., {vN:.4f}
```
One line per channel, newline-separated. This is identical for all text arms — encoding never depends on the question.

| dataset | channels | samples | est. tokens | within budget |
|---|---|---|---|---|
| SenTSR-Bench | 3 | 123–170 | 1,132–1,260 | ✓ (Qwen3-8B 32K ctx) |
| TSRBench HAR | 1 (tri-axial stacked) | 30 | 52–62 | ✓ |
| TSRBench River | 5 | ~100 | 1,531–1,695 | ✓ |
| TSRBench ECG | 12 | 1000 | ~70,000 | **EXCLUDED** — exceeds context |

No downsampling is applied to the text-feasible series; their lengths are within budget as-is. ECG exclusion from text arms is a stop-and-report condition (STOP 1 above).

### Vision arms (V-INS, V-THK)

Rendered as stacked line subplots, shared time axis, grid on, series names labeled, 100 PPI, figure width 10 in, height 2 in per channel. Follows TSRBench rendering convention. ECG (12 leads) rendered as a standard 12-lead clinical layout. All four tasks (SenTSR + HAR + River + ECG) are feasible for vision arms.

---

## 4. Trial Count

**Text arms (T-OFF, T-ON):**

| dataset | items | × 3 seeds | trials per arm |
|---|---|---|---|
| SenTSR-Bench | 330 | × 3 | 990 |
| TSRBench HAR | 150 | × 3 | 450 |
| TSRBench River | 300 | × 3 | 900 |
| **Total text per arm** | **780** | | **2,340** |

**Vision arms (V-INS, V-THK):**

| dataset | items | × 3 seeds | trials per arm |
|---|---|---|---|
| SenTSR-Bench | 330 | × 3 | 990 |
| TSRBench HAR | 150 | × 3 | 450 |
| TSRBench River | 300 | × 3 | 900 |
| TSRBench ECG | 335 | × 3 | 1,005 |
| **Total vision per arm** | **1,115** | | **3,345** |

**Grand total across all 4 arms: 4,680 (text) + 6,690 (vision) = 11,370 trials.**

---

## 5. GPU Time Estimate

Hardware: A6000 (GPU 1). Committed throughput reference: Qwen3-VL-8B ~32–35 tok/s decode from Study F.

Think-token rate for sensor QA is **unknown** — no prior repo experiment on this workload. The range below spans from short reasoning (~1,000 think tokens, optimistic) to moderate (~4,000 tokens, conservative):

| arm | trials | per-trial time (opt/cons) | total GPU hours (opt/cons) |
|---|---|---|---|
| T-OFF | 2,340 | 5 / 8 s | 3.3 / 5.2 h |
| T-ON | 2,340 | 30 / 110 s | 19.5 / 71.5 h |
| V-INS | 3,345 | 12 / 18 s | 11.2 / 16.7 h |
| V-THK | 3,345 | 30 / 110 s | 27.9 / 102.2 h |
| **Total** | **11,370** | | **61.9 / 195.6 h** |

**STOP CONDITION FIRES.** Even the optimistic estimate (62h) exceeds the 24h threshold. The conservative estimate is 196h. The think-token rate is the dominant uncertainty.

---

## 6. Proposed Resolution: Calibration Pilot

Before committing to the full run, run a calibration pilot to measure actual think-token rates:

- **Scope:** 10 items from SenTSR-Bench (stratified: 3–4 per stage), all 4 arms, 3 seeds = 120 trials
- **Purpose:** measure actual think-token distribution for T-ON and V-THK on this workload
- **Estimated time:** ~2–4h depending on think-token rate
- **Decision rule after pilot:**
  - If T-ON median think tokens ≤ 2,000: full run estimated ≤ 50h → SenTSR-Bench only, 2 text arms is feasible (~14h)
  - If T-ON median think tokens > 4,000: full run infeasible; reduce to SenTSR-Bench only, subsample n=60–80, present power analysis

This pilot requires approval and a separate EXPERIMENTS.md row (StudyM-pilot or StudyM0).

---

## 7. Pre-Registered Arms and Prompts

*(Prompts to be finalized after pilot; template quoted here)*

**T-OFF / T-ON prompt template (SenTSR-Bench):**
```
You are a sensor time series analysis expert for industrial warehouse monitoring.

The following multivariate time series records sensor readings over time:

{CHANNEL_NAME}: {v1:.4f}, {v2:.4f}, ..., {vN:.4f}
[... repeat for each channel ...]

Question: {QUESTION_TEXT}

Options:
A. {option_A}
B. {option_B}
C. {option_C}
D. {option_D}

Answer with a single letter (A, B, C, or D) on its own line.
```

**V-INS / V-THK prompt template:**  
Same question + options text, with the rendered plot image prepended. Image format: PNG, 100 PPI, stacked subplots, shared time axis, grid on, channel names labeled.

**Thinking budget instruction** (T-ON and V-THK only, appended):  
No explicit budget instruction — per repo finding (StudyJ3 §1), budget-awareness instructions are counterproductive. `enable_thinking=True` / Thinking model alone controls the thinking mode.

---

## 8. Decoding Parameters

| arm | model | temperature | top_p | top_k | max_new_tokens | thinking |
|---|---|---|---|---|---|---|
| T-OFF | Qwen3-8B | 0.7 | 0.9 | — | 1,024 | enable_thinking=False |
| T-ON | Qwen3-8B | 0.6 | 0.95 | 20 | 16,384 | enable_thinking=True |
| V-INS | Qwen3-VL-8B-Instruct | 0.9 | 0.95 | — | 1,024 | n/a (Instruct) |
| V-THK | Qwen3-VL-8B-Thinking | 0.6 | 0.95 | 20 | 16,384 | Thinking model |

*T-OFF and V-INS decoding parameters are from the respective model cards (Qwen3-8B non-thinking: temp=0.7, top_p=0.9; Qwen3-VL-8B-Instruct: temp=0.9, top_p=0.95). Confirm against model cards before running.*

---

## 9. Questions for Approval

Before proceeding:

1. **STOP 1:** Approve ECG exclusion from text arms (T-OFF/T-ON). ECG remains in vision arms.
2. **STOP 2 / GPU time:** Approve calibration pilot (10 SenTSR items × 4 arms × 3 seeds = 120 trials) before committing to full run scope?
3. **Qwen3-8B download:** Approve download of `Qwen/Qwen3-8B` (~16 GB) to `/mnt/ssd/hf_models/`.
4. **Vision arms:** Confirm that V-INS and V-THK arms should use Qwen3-VL-8B models (not pure Qwen3-8B with vision). The Qwen3-VL-8B-Instruct/Thinking models are already cached. This is the natural pairing for the vision arms.
5. **T-OFF decoding:** Qwen3-8B non-thinking model card specifies temperature=0.7, top_p=0.9 (no top_k). Confirm these over greedy.

---

## 10. Pre-Registered Decision Rule

*(From EXPERIMENTS.md, recorded before any inference)*

**PASS:** In at least one model family (text: T-ON vs T-OFF; vision: V-THK vs V-INS), thinking beats no-think on **reasoning items** (SenTSR How+Fix stages and TSRBench Reasoning/Decision dimensions) by ≥ 5 pp with BH-adjusted p < 0.05, **and** the no-think baseline is not at floor (within 5 pp of chance = 25% for 4-option MCQ).

**FAIL:** No family meets this. Report plainly; do not search for subsets after the fact.

Any post-hoc subgroup analysis must be labeled exploratory.

---

## 11. Output Files

| file | when created |
|---|---|
| `reports/study_m_plan.md` | Step 0 (this file) |
| `experiments/ts/study_m.py` | After approval |
| `results/ts/study_m/study_m_trials.jsonl` | After inference |
| `reports/study_m_results.md` | After analysis |
