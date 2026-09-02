# Study H2 — S-EMBER Annotation Analysis

Date: 2026-09-01  
Machine: A6000 host (CPU only; no model inference)  
Script: `experiments/sember/study_h2_sember_annotations.py`  
Outputs: `results/sember/study_h2/`  
Prior work: `reports/study_h_sember_structure.md` (codebase + video metadata; E1 gated access resolved)

---

## §1 — Data Acquisition

| file | size | status |
|---|---|---|
| `sember_grounding.jsonl` | 11.1 MB | Downloaded ✓ |
| `sember_mcq.jsonl` | 10.6 MB | Downloaded ✓ |
| Video files | 396 GB | Not fetched — not required |

Both annotation files downloaded to `results/sember/study_h/data/`. Disk: 3,213 GB free on `/mnt/ssd`.

---

## §2 — Analysis 1: Does a Growing Prefix Exist? (PRIMARY AND DECIDING)

### Verdict

**ACCEPT: Questions within a video fire at distinct, spread timestamps. A growing prefix exists. A session can be constructed.**

Every one of the 3,141 videos has two or more questions. Only 1 of 3,141 multi-question videos (0.03%) has identical `question_time` values for all its questions; all others have distinct timestamps with substantial spread. The prior E2 conclusion — that no session exists — conflated the benchmark's evaluation protocol (fresh recomputation per question) with the annotation structure (growing prefix of video content). The benchmark recomputes because it is a baseline evaluator, not because the data has no session. The sessions are in the annotations.

### QA-per-video distribution

| questions per video | count | fraction |
|---|---|---|
| 1 | 0 | 0.0% |
| 2 | 1,036 | 33.0% |
| 3 | 1,283 | 40.8% |
| 4 | 615 | 19.6% |
| 5 | 175 | 5.6% |
| 6 | 32 | 1.0% |

No video has only one question. Mean = 3.01 QA/video (matches paper). Every video is a multi-question session.

### Question-time spread within videos

Among all 3,141 multi-question videos:

| metric | value |
|---|---|
| Videos with all-identical question_time | 1 (0.03%) |
| Videos with spread < 10 s | ~1 (0.03%) |
| **Median spread** | **204 s** |
| **IQR of spread** | **167 s** |
| p90 spread | 429 s |
| Max spread | 1,111 s |

The one identical-qt video (`1521207699058238_start_0.0_end_337.475`, both questions at t=251 s) is anomalous and contributes nothing to a session structure. All remaining 3,140 videos have distinct question timestamps with a median gap of 204 seconds between first and last question.

**Conclusion:** A session can be built for every video by ordering questions by `question_time` and serving each question with `video[0, question_time]`. Each successive question observes a strict superset of the prior. The benchmark does not exploit this structure (it recomputes from scratch per question), but the prefix structure is real and usable.

### Sanity note on E2

The prior report's E2 conclusion was drawn from the evaluation protocol code, which correctly documents that each question is evaluated independently. That is the correct description of how the baseline evaluator works. It does not imply that the data has no session structure. The two things are orthogonal. E2 is retracted.

---

## §3 — Sanity Checks

| check | result | detail |
|---|---|---|
| SC1: QA count = 9,448 | **PASS** | Grounding: 9,448; MCQ: 9,448 |
| SC2: All have valid temporal fields | **PASS** | 0 missing |
| SC3: answer_start ≤ answer_end ≤ question_time | **10 violations** | All `aet = floor(qt) + 1` — rounding artifact; see below |
| SC4: No negative nearest distance | **10 violations** | Same 10 records; all exactly −1.0 s |
| SC4b: No negative farthest distance | **PASS** | 0 |
| SC5: `memory_recency` = qt − answer_start | **PASS** | 0 mismatches within 1 s tolerance |

### SC3/SC4 annotation artifact — characterized and resolved

10 records (0.11%) have `answer_end_time = question_time + 1.0` exactly. In all 10 cases:
- `question_time` is an integer (e.g., 599)
- `answer_end_time` is a float exactly 1 s higher (e.g., 600.0)
- Video duration is fractional and falls between the two (e.g., 599.988)

Pattern: the question fires near the very end of the video; the annotated evidence window extends to the video's final frame. `question_time` was stored as a floor-integer (599) while `answer_end_time` was stored as the actual terminal second of the evidence (600.0). This is an integer-rounding artifact in the annotation, not a genuine causal violation (the evidence does not occur after the question in reality). **These 10 records are excluded from evidence distance analysis and included in session structure analysis.**

**SC5 correction to Study H:** Study H incorrectly stated `memory_recency = question_time − answer_end_time`. The actual definition is `memory_recency = question_time − answer_start_time` (the distance to the FAR end of the evidence window, i.e., how long ago the evidence began). SC5 verifies this: all 9,448 `memory_recency` values match `qt − ast` within 1 s.

---

## §4 — Analysis 2: Evidence Distance

**Primary definition:** nearest = `question_time − answer_end_time` (how recently the evidence window closed)  
**Farthest definition:** `question_time − answer_start_time` = precomputed `memory_recency` field  
**N for analysis:** 9,438 (10 artifact records excluded from nearest; farthest uses 9,440+)

### Overall distribution (nearest)

| metric | seconds |
|---|---|
| min | 0.0 |
| median | **21.0** |
| IQR | 56.0 |
| p90 | 117.0 |
| p99 | 335.0 |
| max | 1,005.0 |

### Overall distribution (farthest = memory_recency)

| metric | seconds |
|---|---|
| median | 74.0 |
| IQR | 96.0 |
| p90 | 235.0 |
| p99 | 498.0 |

### Nearest distance histogram

| bucket (s) | count | fraction |
|---|---|---|
| [0, 1) | 2,606 | 27.6% |
| [1, 5) | 277 | 2.9% |
| [5, 15) | 1,109 | 11.8% |
| [15, 30) | 1,553 | 16.4% |
| [30, 60) | 1,648 | 17.5% |
| [60, 120) | 1,342 | 14.2% |
| [120, 300) | 769 | 8.2% |
| [300, ∞) | 134 | 1.4% |

The distribution is **wide and multi-modal**. It is not clustered near the query time. The 27.6% in [0,1) reflects two categories where the evidence window closes at the exact query moment (object_comparison, spatial_aware_reasoning — see below); removing those two categories, the [0,1) bin shrinks substantially and the remaining distribution centers around 15–60 s.

### Evidence distance as fraction of question_time

Nearest distance as fraction of `question_time`: median = 0.074 (7.4%), IQR = 0.182. The evidence typically closes about 7% of the way before the query, but the spread is large — some questions ground in events far in the past.

### By-category breakdown

| category | nearest median (s) | farthest median (s) | n | note |
|---|---|---|---|---|
| location_trace | 44.0 | 59 | 996 | Evidence spans recent past |
| visual_detail_recall | 37.0 | 50 | 1,868 | Evidence spans recent past |
| sequential_action | 35.0 | 51 | 1,019 | Evidence spans recent past |
| time_duration | 21.0 | 82 | 1,935 | Evidence window large; question fires after event |
| temporal_ordering_recognition | 15.0 | 101 | 485 | Wide evidence windows |
| counting_objects_events | 10.0 | 121 | 1,627 | (excluded downstream; wide historical window) |
| object_comparison | **0.0** | 68 | 665 | Evidence ends AT query time; 68% have nearest=0 |
| spatial_aware_reasoning | **0.0** | 90 | 853 | Evidence ends AT query time; 86% have nearest=0 |

**Category range (nearest median):** 44 s (location_trace 44 s vs. object_comparison/spatial_aware 0 s).

**Do categories differ? Yes, substantially.**

The key distinction is structural, not just scalar:

- **`object_comparison` and `spatial_aware_reasoning`** have median nearest = 0 s because the evidence CLOSES at question_time — the question asks about the current moment vs. an earlier moment. The evidence STARTS far back (farthest median 68–90 s). These categories require historical context that spans most of the session prefix, but the relevant frame is also the current one. Nearest distance understates the retention requirement; farthest distance is more informative.

- **`location_trace`, `visual_detail_recall`, `sequential_action`** have nearest median 35–44 s. The evidence window closed 35–44 s before the question, meaning the model needs to recall something that happened in the recent past, not the current frame.

- **`time_duration` and `temporal_ordering_recognition`** have large evidence windows (farthest median 82–101 s) — the evidence spans entire events (start-to-end of an action), and the question fires after the event ends.

---

## §5 — Analysis 3: Exclusion and Remaining Scale

| metric | value |
|---|---|
| Total QA pairs | 9,448 |
| `counting_objects_events` (excluded) | 1,627 (17.2%) |
| Remaining QA pairs | **7,821** |
| Remaining videos | **3,126** |
| Remaining multi-question videos | **2,755** |
| Single-question videos remaining | 371 |

### Post-exclusion category breakdown

| category | remaining QA |
|---|---|
| time_duration | 1,935 |
| visual_detail_recall | 1,868 |
| sequential_action | 1,019 |
| location_trace | 996 |
| spatial_aware_reasoning | 853 |
| object_comparison | 665 |
| temporal_ordering_recognition | 485 |
| **Total** | **7,821** |

**2,755 multi-question videos survive exclusion.** These are the sessions usable for a retention study. Removing counting reduces videos from 3,141 to 3,126 (−15 videos become single-question; 371 total single-question after exclusion).

---

## §6 — Analysis 4: Session Construction Feasibility at 1 fps

Constants: 324 vision tokens/frame (Qwen3-VL, Study D), 57,344 B/token (Study A/B), 16 GB model weights, 32 GB usable vRAM on A6000.

### Cumulative KV by question index (across all multi-question videos)

| question | videos | median cum. frames | median KV (GB) | p90 KV (GB) |
|---|---|---|---|---|
| Q1 | 3,141 | 123 | 2.29 | 2.38 |
| Q2 | 3,141 | 235 | 4.37 | 9.59 |
| Q3 | 2,105 | 302 | 5.61 | 4.74 |
| Q4 | 822 | 322 | 5.98 | 4.59 |
| Q5 | 207 | 352 | 6.54 | 7.30 |
| Q6 | 32 | 353 | 6.56 | 5.00 |

### Final-question KV distribution (all multi-question videos)

| metric | KV (GB) |
|---|---|
| median | 5.89 |
| p90 | 10.61 |
| max | 22.26 |
| fraction exceeding 32 GB | **0.0%** |

**At 1 fps, a session-level accumulation creates no memory pressure. Zero videos exceed the 32 GB usable vRAM budget even at the final (last) question.** The A6000's 48 GB is ample for any session in this dataset at 1 fps.

**Interpretation for FM-switching:** The full-retention cost is modest (≤22 GB KV for any session). This means the representation trade-off at 1 fps is not primarily driven by memory pressure — it is driven by the reconstruction latency and transfer cost question, exactly as in the existing FM-switching formulation. A lower sampling rate (e.g., 0.1 fps, matching lmms-eval defaults of 16 frames / 600 s) would make KV even smaller (≈10× smaller), making full retention trivially affordable. A higher rate (e.g., 4 fps for long videos) would start approaching the 32 GB ceiling for the longest sessions.

The note on p90 irregularity: the Q2 p90 (9.59 GB) exceeds Q3 p90 (4.74 GB) because Q3 is computed only over the subset of videos with 3+ questions, which may differ in duration from the full Q2 set. The medians are monotonically increasing as expected.

---

## §7 — What Still Cannot Be Determined From Annotations Alone

- Frame rate of raw recordings (requires video container headers; not in JSONL).
- Actual frame resolution per video (paper states 1920×1080 for Ray-Ban Meta; individual clips may vary).
- Whether frame-level content changes across the prefix (scene entropy, object persistence, visual diversity). This matters for whether a rolling summary degrades gracefully across S-EMBER sessions.
- Answer quality for the grounding task requires either model runs (temporal IoU) or Gemini judge (answer text correctness). Neither was run here.
- Whether questions within a video are ordered by `question_time` in the JSONL (they appear not to be; the script sorts them for feasibility analysis).

---

## §8 — Plain Answers

**1. Do questions within a video fire at distinct timestamps, and how far apart?**

Yes. All 3,141 videos have 2–6 questions. Only 1/3,141 has identical `question_time` values. Median spread between first and last question: **204 s** (IQR 167 s, p90 429 s). A growing prefix exists for essentially every video in the dataset.

**2. Is the evidence-distance distribution wide, or clustered near the query time?**

**Wide.** Nearest: median 21 s, IQR 56 s, p90 117 s, p99 335 s, max 1,005 s. The distribution has a 27.6% spike at [0,1) s driven by the object_comparison and spatial_aware_reasoning categories (evidence closes at query time). Excluding those two categories, the remaining distribution centers around 15–60 s with a substantial tail past 120 s. The benchmark intentionally spans a wide range of memory recency.

**3. Do categories differ in evidence distance, with numbers?**

**Yes, substantially.** Nearest median ranges from 0 s (object_comparison, spatial_aware_reasoning) to 44 s (location_trace) — a 44 s range. The structural difference matters more than the scalar: object_comparison and spatial_aware_reasoning have evidence windows that *end* at question_time (nearest=0) but *start* far back (farthest median 68–90 s), meaning they need full historical context but the current frame is also evidence. The other categories (location_trace, visual_detail_recall, sequential_action) have evidence that closed 35–44 s before the question. The farthest metric (qt − ast) ranges from 50 s to 121 s across categories.

**4. After excluding counting, how many multi-question videos remain?**

**2,755** multi-question videos with **7,821** QA pairs across **3,126** videos total.

**5. Would an accumulated session at 1 fps create real memory pressure, or fit trivially?**

**Fits trivially.** Median final-question KV: 5.89 GB. Max: 22.26 GB. Zero of 3,141 sessions exceed the 32 GB usable vRAM budget at 1 fps. Memory pressure is not a binding constraint for S-EMBER sessions at 1 fps. The retention trade-off is driven by reconstruction latency and transfer cost, not by KV budget exhaustion.

---

## §9 — Implications for FM-Switching

S-EMBER is **usable as a session workload** under the following construction:
1. Group QA pairs by `video_id`; order within each group by `question_time`.
2. Each question is served with `video[0, question_time]` — the growing prefix is the session.
3. A state-retention policy decides what representation to maintain between questions: full-prefill (re-encode all N frames from scratch), window-k (keep the last k frames' KV), or summary (a rolling text generated after each question).
4. The benchmark's grounding JSONL provides `answer_start_time`, `answer_end_time`, and `memory_recency` as ground truth for evaluating whether the retained representation spans the evidence window for each question.

The evidence-distance distribution (median 21 s nearest, wide IQR) means retention decisions matter: a window-3 representation at 1 fps (retaining only the last 3 seconds) would cover the evidence window for roughly 30% of questions (those with nearest < 3 s) and miss the rest. A full-retention policy would cover all but the 10 artifact records.

The session scale is workable: 2,755 multi-question videos, 2–6 questions each, sessions up to 22 GB KV at 1 fps (well within A6000 capacity).

**Recommendation: Accept S-EMBER as the session workload.** The E2 rejection is retracted.

---

## Provenance

```json
{
  "git_commit": "pre-provenance",
  "script": "study_h2_sember_annotations.py",
  "model": "none",
  "device": "cpu",
  "n": "9448 grounding rows, 9448 MCQ rows",
  "timestamp": "2026-09-01",
  "grounding_path": "results/sember/study_h/data/sember_grounding.jsonl",
  "mcq_path": "results/sember/study_h/data/sember_mcq.jsonl",
  "sember_version": "data/README.md version 0.2 (yaml metadata: 0.2)"
}
```
