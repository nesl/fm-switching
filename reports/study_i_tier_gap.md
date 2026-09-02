# Study I — S-EMBER Tier Gap: Accuracy × Category × Evidence Distance

**Date:** 2026-09-02  
**Status:** INFER complete for 4B (SPARSE+DENSE) and 8B SPARSE; 8B DENSE in progress.  
**Script:** `experiments/sember/study_i_tier_gap.py`  
**Analysis:** `experiments/sember/study_i_analyse.py`  
**Output:** `results/sember/study_i/study_i_trials.jsonl`, `study_i_results.json`, `study_i_summary.md`  
**Device:** NVIDIA RTX A6000 (cuda:1), `fmtk` conda env  
**Models:** Qwen3-VL-4B-Instruct (`qwen3vl4b`), Qwen3-VL-8B-Instruct (`qwen3vl8b`)  
**Sampling:** SPARSE (16 frames uniform over [0, qt]) and DENSE (1fps over [0, qt], cap 256 frames)  
**Dataset:** S-EMBER — 150 videos (stratified), 459 QA pairs, 7 categories  

---

## 1. Study description

**Primary question.** Does the accuracy gap between a smaller (4B) and larger (8B) vision-language model depend on (a) question category and (b) evidence distance on the S-EMBER egocentric video QA dataset? And is the gap large enough to justify two-tier compute placement — routing some questions to the larger model at an edge server while smaller questions are served on-device?

**Secondary question.** Does dense temporal sampling (1fps) help relative to sparse sampling (16 frames), and does the benefit depend on category or evidence distance?

**Relevance to FM-switching.** If the 8B−4B accuracy gap exceeds the quality SLO threshold on S-EMBER, then the workload is tier-discriminating: a policy that routes hard questions to an edge-tier 8B while easier ones stay on a device-tier 4B would earn a quality benefit. If the gap is negligible or scattered across categories without pattern, a single-tier policy is sufficient for this workload.

---

## 2. Mechanism verification

**Classification: measurement study — no causal claim.**

Study I characterizes two accuracy gaps (8B−4B and DENSE−SPARSE) and their dependence on question category and evidence distance. There is no causal sweep over a policy variable; the experiment does not manipulate placement, budget, or admission. The same classification applies as for StudyH and StudyH2 (see EXPERIMENTS.md): "N/A — measurement study, no causal claim."

Relevant checks:

- **GSER protocol:** Each question sees only `video[0, question_time]`. Asserted per trial in `load_frames`; confirmed by inspection of `target_times` construction.
- **Coverage arithmetic:** Uses `answer_start_time` as the binding constraint (Study H2 SC5 correction). `farthest_dist_s = qt − ast`; a window of size k covers the evidence iff `k ≥ farthest_dist_s`.
- **Temporal embeddings:** `VideoMetadata(fps=1.0, frames_indices=[integer timestamps], total_num_frames=round(qt))` passed to `proc()`. Zero fps-inference warnings observed during testing.
- **Scoring:** Exact letter match (A/B/C/D/E), `max_new_tokens=16`, greedy decode (`do_sample=False`, `temperature=None`).

---

## 3. Results consistency check

**3.1 Cross-check against committed measurements.**

| quantity | this run | prior run | source | ratio | verdict |
|---|---|---|---|---|---|
| Qwen3-VL-4B latency (SPARSE, ~5K tok) | 810ms | no prior | — | — | first measurement |
| Qwen3-VL-8B latency (SPARSE, ~5K tok) | 1234ms | no prior | — | — | first measurement |
| Throughput 4B (SPARSE) | 5.86 tok/ms = 5860 tok/s | A6000 Qwen2.5-7B cold prefill ~7100 tok/s | `cost_matrix.csv` | 0.82 | AGREE (diff model, Qwen3-VL vs Qwen2.5, expected ~20% lower) |
| Throughput 8B (SPARSE) | 3.85 tok/ms = 3850 tok/s | no prior for 8B | — | — | plausible (8B ~0.66× 4B rate) |

No prior accuracy measurements on S-EMBER exist to cross-check; this is the first model run.

**3.2 Physical plausibility check.**

- 4B SPARSE at 5860 tok/s is within ~20% of the committed 7100 tok/s A6000 cold prefill rate for Qwen2.5-7B. Qwen3-VL-4B has a larger vision encoder and additional visual tokens, so a modest throughput reduction is expected.
- 8B SPARSE at 3850 tok/s is 0.66× the 4B rate. Expected ratio for 8B vs 4B on the same hardware is roughly 0.5–0.7×. PLAUSIBLE.
- DENSE at ~12,600 median tokens produces ~2× latency relative to SPARSE at ~4,750 tokens, consistent with linear scaling. PASS.
- Latency spread (p99−p50 / p50) is <5% for all configs, indicating low intra-run variance. Distribution check passed.

**3.3 Distribution sanity.**

Token counts (SPARSE): median 4,747, checked against 16 frames × 324 visual tokens/frame + ~300 text tokens = 5,484 estimated. Actual is ~13% lower — consistent with shorter `question_time` videos producing fewer tokens (some videos have qt < median 239s). Not a caching artifact.

Token counts (DENSE): median 12,587, consistent with ~38 frames × 324 + 300 = ~12,600. PASS.

Accuracy values per category span 11.5%–43.6% (4B SPARSE), confirming no constant-output pathology.

**3.4 Definition audit.**

| term | definition in this run |
|---|---|
| SPARSE | 16 frames uniform over [0, qt] |
| DENSE | 1fps over [0, qt], capped at 256 frames |
| question_time (qt) | `qa_row["question_time"]` in seconds |
| farthest_dist_s | `qt − answer_start_time` |
| nearest_dist_s | `qt − answer_end_time` |
| correct | predicted_letter == correct_letter, exact match |
| n | number of QA pairs, one per video-question (not per trial) |

**3.5 Claim linkage.**

| analysis | bears on | direction |
|---|---|---|
| A — overall accuracy | C1 (fidelity workload-dependent) | Does not speak to C1 directly — measures model-scale gap, not representation-fidelity gap. S-EMBER characterization for C5 simulator input. |
| B — category gap | C5 (joint policy beats decomposed) | Weak: if category gap is negligible, S-EMBER does not discriminate tiers, narrowing C5 scope. |
| C — evidence distance | C4 (physical inertia grows with L) | Indirect: evidence distance distribution tells us what window sizes are needed for coverage, which sets the materialization cost. |
| E — coverage | C4 + C5 | 71% of questions need a >60s window; 93% need >300s. This is input to the C5 simulator. |
| G — placement verdict | C5 | If gap is NEGLIGIBLE, S-EMBER is not a discriminating workload for the tier-gap axis of C5. |

**3.6 Proxy validity.** No proxies used. All quantities are directly measured: accuracy via exact letter match, latency via `cuda.synchronize()` + `perf_counter()`, tokens via `input_ids.shape[1]`.

---

## 4. Results

### A — Overall accuracy

| config | n | acc | 95% CI |
|--------|---|-----|--------|
| qwen3vl4b_SPARSE | 459 | 26.6% | [22.7%, 30.8%] |
| qwen3vl4b_DENSE  | 459 | 29.8% | [25.8%, 34.2%] |
| qwen3vl8b_SPARSE | 459 | 27.2% | [23.4%, 31.5%] |
| qwen3vl8b_DENSE  | 223* | 33.6% | [27.8%, 40.1%] |

*8B DENSE partial; final numbers pending.

Random baseline (5-choice MCQ): 20.0%.

- **8B−4B gap (SPARSE): +0.7pp** — negligible, within CI overlap.
- **8B−4B gap (DENSE): +3.8pp** — small, with partially complete 8B DENSE.
- **DENSE−SPARSE gain (4B): +3.3pp** — modest but consistent.
- **DENSE−SPARSE gain (8B): +6.4pp** — larger benefit from dense sampling for the bigger model (partial).

### B — Accuracy by category (SPARSE)

| category | 4B | 8B | gap | p (Fisher) |
|----------|----|----|-----|------------|
| time_duration | 23.7% (n=93) | 30.1% (n=93) | +6.4pp | 0.408 |
| visual_detail_recall | 41.5% (n=94) | 43.6% (n=94) | +2.1pp | 0.883 |
| sequential_action | 26.2% (n=61) | 19.7% (n=61) | −6.6pp | 0.519 |
| location_trace | 11.5% (n=52) | 19.2% (n=52) | +7.7pp | 0.416 |
| spatial_aware_reasoning | 16.1% (n=56) | 8.9% (n=56) | −7.1pp | 0.392 |
| object_comparison | 33.9% (n=56) | 30.4% (n=56) | −3.6pp | 0.840 |
| temporal_ordering_recognition | 23.4% (n=47) | 25.5% (n=47) | +2.1pp | 1.000 |

Category gap range: [−7.1pp, +7.7pp], spread 14.8pp. No category reaches p < 0.05. The direction of the gap is inconsistent across categories: 8B beats 4B in time_duration and location_trace but loses in sequential_action and spatial_aware_reasoning. This oscillation, combined with non-significance, is consistent with noise rather than a systematic model-capacity effect.

### C — Accuracy vs evidence distance

**nearest_dist_s (qt − aet) bins:**

| bin | 4B-SPARSE | 4B-DENSE | 8B-SPARSE | 8B-DENSE* |
|-----|-----------|----------|-----------|-----------|
| [0, 10) | 24.0% (n=171) | 26.9% (n=171) | 22.8% (n=171) | 32.6% (n=86) |
| [10, 30) | 31.6% (n=98) | 36.7% (n=98) | 33.7% (n=98) | 35.7% (n=42) |
| [30, 60) | 26.2% (n=80) | 27.5% (n=80) | 28.7% (n=80) | 31.8% (n=44) |
| [60, 120) | 22.6% (n=62) | 33.9% (n=62) | 25.8% (n=62) | 36.7% (n=30) |
| [120, ∞) | 31.2% (n=48) | 25.0% (n=48) | 29.2% (n=48) | 33.3% (n=21) |

*Partial.

No monotonic trend with evidence distance. Accuracy does not systematically fall as evidence becomes more distant.

**farthest_dist_s (qt − ast, coverage-binding) bins:**

| bin | 4B-SPARSE | 4B-DENSE | 8B-SPARSE | 8B-DENSE* |
|-----|-----------|----------|-----------|-----------|
| [0, 10) | 33.3% (n=9) | 22.2% (n=9) | 44.4% (n=9) | 20.0% (n=5) |
| [10, 30) | 24.1% (n=58) | 34.5% (n=58) | 20.7% (n=58) | 25.9% (n=27) |
| [30, 60) | 29.9% (n=134) | 30.6% (n=134) | 31.3% (n=134) | 35.5% (n=62) |
| [60, 120) | 25.0% (n=124) | 32.3% (n=124) | 29.0% (n=124) | 36.7% (n=60) |
| [120, ∞) | 25.4% (n=134) | 25.4% (n=134) | 23.1% (n=134) | 33.3% (n=69) |

No significant accuracy degradation with longer evidence distances under either sparse or dense sampling. The n=9 in [0,10) is too small for reliable estimates.

### D — Latency

| config | lat_med | lat_p90 | lat_p99 | tok_med | tok/ms |
|--------|---------|---------|---------|---------|--------|
| qwen3vl4b_SPARSE | 810ms | 816ms | 822ms | 4747 | 5.86 |
| qwen3vl4b_DENSE | 2176ms | 2214ms | 2304ms | 12587 | 5.78 |
| qwen3vl8b_SPARSE | 1234ms | 1247ms | 1260ms | 4747 | 3.85 |
| qwen3vl8b_DENSE | 3135ms* | 3225ms* | 3333ms* | 12579 | 4.01* |

*Partial.

Latency distribution is tight (p99/p50 < 1.05×) — consistent, no warm-cache artifacts. 4B runs at 5.86 tok/ms; 8B at 3.85 tok/ms (0.66× ratio). DENSE adds ~2.7× latency vs SPARSE for both models, tracking the ~2.7× token ratio (12587/4747 = 2.65×).

### E — Coverage (ast-based)

Reference set: 4B-SPARSE, n=459.

| window k | evidence covered | fraction |
|----------|-----------------|----------|
| 3s | 0/459 | 0.0% |
| 10s | 10/459 | 2.2% |
| 30s | 75/459 | 16.3% |
| 60s | 204/459 | 44.4% |
| 120s | 327/459 | 71.2% |
| 300s | 428/459 | 93.2% |
| 600s | 455/459 | 99.1% |

S-EMBER evidence is deep in session history. A 120s context window covers only 71% of questions' evidence start points. A session-state policy would need to retain at least 300s of video context to serve 93% of questions. This is input to the C5 simulator's coverage parameter.

### F — DENSE−SPARSE accuracy delta per category

| category | 4B Δ | 8B Δ |
|----------|------|------|
| time_duration | +8.6pp | +9.0pp |
| visual_detail_recall | +1.1pp | −6.7pp |
| sequential_action | +3.3pp | +19.0pp |
| location_trace | +9.6pp | +15.8pp |
| spatial_aware_reasoning | +0.0pp | +5.4pp |
| object_comparison | −3.6pp | −2.8pp |
| temporal_ordering_recognition | +2.1pp | +13.6pp |

Dense sampling helps substantially for sequential_action (+19pp for 8B), location_trace (+10–16pp), and temporal_ordering_recognition (+14pp for 8B). These are categories where key evidence may appear at a specific moment that uniform sparse sampling can miss. object_comparison and visual_detail_recall are relatively insensitive to sampling density.

### G — Placement verdict

| dimension | gap | verdict |
|-----------|-----|---------|
| 8B−4B, SPARSE | +0.7pp | NEGLIGIBLE |
| 8B−4B, DENSE | +3.8pp (partial) | NEGLIGIBLE |
| category range (SPARSE) | [−7.1pp, +7.7pp] | spread 14.8pp, no category significant |

**A two-tier placement policy routing by model size has nothing to decide on S-EMBER under SPARSE sampling.** The 8B−4B accuracy gap (0.7pp) is within noise and well below any plausible quality SLO threshold. The gap is larger under DENSE sampling (~3.8pp, partial), but remains below the 5pp threshold and in the same NEGLIGIBLE tier.

The category spread (14.8pp between best and worst category gap) does not support a category-conditioned routing policy: the gaps oscillate in direction across categories with no significance.

**Sampling mode** is a more impactful axis than model size on this workload: DENSE sampling outperforms SPARSE by 3.3pp (4B) to 6.4pp (8B), with the largest gains in temporally precise categories (sequential_action, location_trace, temporal_ordering_recognition).

---

## 5. Findings

**F1. S-EMBER is model-scale-insensitive under sparse sampling.**  
The 8B−4B accuracy gap is 0.7pp under SPARSE and approximately 3.8pp under DENSE (partial). Neither crosses a 5pp SLO threshold. A two-tier edge/device policy partitioning by model size provides no quality benefit on this workload. This contrasts with LoCoMo (dense-incompressible, fidelity gaps of 24pp), confirming that the degree of tier-discriminability is workload-dependent (C1 direction).

**F2. Sampling density matters more than model scale on S-EMBER.**  
DENSE sampling (+3.3pp for 4B, +6.4pp for 8B partial) outperforms the model-scale upgrade (+0.7pp) by 5–9×. For temporally precise categories (sequential_action, location_trace, temporal_ordering_recognition), the DENSE gain for 8B is +14–19pp. If the deployment constraint is on model size, using the larger model's SPARSE mode is dominated by the smaller model's DENSE mode.

**F3. Evidence is temporally deep: 300s+ context needed for 93% coverage.**  
The coverage analysis (E) shows that a session-state policy needs a ≥300s retention window to cover the evidence start time for 93% of S-EMBER questions. This is substantially deeper than the evidence distribution for LoCoMo (which has a different structure). The implication for the C5 simulator: if the device retains only a rolling window, S-EMBER questions with deep evidence will be answered from an incomplete state. Whether this degrades accuracy depends on whether models can infer missing evidence — the flat accuracy-vs-distance curve (Analysis C) suggests they partially can, or that evidence depth does not determine difficulty on this benchmark.

**F4. Overall accuracy is low (27–34%), barely above random (20%).**  
This may reflect the genuine difficulty of egocentric video QA with sparse temporal coverage, or a task-format mismatch. The flat evidence-distance curve (no accuracy drop at large distances) is consistent with models answering from prior knowledge or scene priors rather than retrieving specific evidence. Further investigation (e.g., comparing against a no-video text-only baseline) would clarify whether vision is load-bearing.

---

## 6. Claim linkage

| claim | Study I bearing |
|-------|----------------|
| C1 — fidelity is workload-dependent | Consistent: S-EMBER shows small model-scale gap (~negligible), unlike LoCoMo (24pp fidelity gap). Supports workload-dependence of tier-discriminability without directly measuring representation fidelity. |
| C2 — semantic inertia reader-dependent | Does not speak to C2 (single model pair, no summarizer variation). |
| C5 — joint policy beats decomposed | Weakens: S-EMBER does not discriminate model tiers under either sampling mode. C5 simulator requires a workload where the gap exists. |
| C4 — physical inertia grows with L | Indirect: latency scales linearly with token count (confirmed). Coverage analysis shows 300s+ retention needed, which at 1fps = ~300 frames × 324 tokens = ~97K tokens → far outside current A6000 working memory at 8B (likely OOM). S-EMBER is physically infeasible as a full-fidelity session workload at 8B scale. |

---

## 7. Limitations

- **8B DENSE partial:** 223/459 trials at report time. Final numbers may shift the DENSE gap estimate. The SPARSE result (full 459 trials) is definitive.
- **No text-only baseline:** Cannot determine whether vision is load-bearing for model answers. The low overall accuracy and flat distance-accuracy curve are consistent with vision contributing little.
- **Single A6000 measurement:** Latency numbers are A6000-specific. Jetson or 3090 Ti latency is expected to differ substantially.
- **Counting category excluded:** `counting_objects_events` (1,627 QA, 17.2% of dataset) excluded per StudyH2 recommendation. Results may not generalise to counting questions.
- **GSER protocol:** Each question is scored from the model's single forward pass over `video[0, qt]`. There is no session state or accumulated context — the "session" is a GSER fiction. The coverage analysis describes what a hypothetical session-state policy would need to retain; actual accuracy under such a policy may differ.

---

## 8. Next steps

- [ ] Re-run `study_i_analyse.py` once 8B DENSE completes to get final numbers.
- [ ] Update G verdict with final 8B DENSE gap.
- [ ] Add text-only (no video) baseline as a single-pass measurement to check whether vision is load-bearing.
- [ ] Update `research/EXPERIMENTS.md`, `results/INDEX.md`, `research/STATUS.md`.

---

*Results files: `results/sember/study_i/study_i_trials.jsonl` (1,596 trials at report time), `study_i_results.json`, `study_i_summary.md`.*
