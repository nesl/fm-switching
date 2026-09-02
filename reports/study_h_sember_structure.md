# Study H — S-EMBER Benchmark Structure

**Status: STOPPED — two escalation conditions met (E1, E2). See §7.**

Date: 2026-08-31  
Machine: A6000 host (CPU work only; no model inference)  
Script: `experiments/sember/study_h_sember_structure.py`  
Outputs: `results/sember/study_h/`  

---

## §1 — Data Acquisition

### Download size

| item | size | status |
|---|---|---|
| `sember_grounding.jsonl` | 11.1 MB | **BLOCKED (E1)** |
| `sember_mcq.jsonl` | 10.6 MB | **BLOCKED (E1)** |
| Annotation total | 21.7 MB | — |
| Video files (3141 × mp4) | 396.2 GB | Not fetched (not required) |

Available disk: 3,213 GB free on `/mnt/ssd`. Video files would fit (396 GB < 3.2 TB), but are not required for this study.

### E1 — HuggingFace gated access (403)

The dataset `facebook/S-EMBER` is access-gated with form approval required. The account `psharma05` (the HF token on this machine) has not been approved. The download fails with `GatedRepoError: 403` for both JSONL files.

> "Access to dataset facebook/S-EMBER is restricted and you are not in the authorized list.  
> Visit https://huggingface.co/datasets/facebook/S-EMBER to ask for access."

The gating form requires: full name, affiliation, agreement to non-commercial use, and agreement to CC BY-NC 4.0. Once approved, rerun `study_h_sember_structure.py` and all annotation-level analyses (§B, §C, §D) will run to completion.

The GitHub codebase (`github.com/facebookresearch/S-EMBER`) is publicly accessible and was cloned for codebase analysis (§2, §5). Video metadata was retrieved from the HF API without downloading video files.

---

## §2 — Session Structure (Analysis A)

### 2.1 Video count and duration

Source: HuggingFace file metadata — video filenames encode `<uid>_start_<s>_end_<e>.mp4`. Durations extracted from all 3,141 video filenames without downloading video.

| metric | value |
|---|---|
| N videos | 3,141 |
| Matches paper | YES (3,141) |
| Total hours | 387.9 h |
| Paper-reported hours | 388 h |
| Min duration | 300.0 s |
| p10 | 300.2 s |
| Q1 | 317.4 s |
| **Median** | **367.4 s** |
| Q3 | 600.0 s |
| p90 | 600.1 s |
| Max | 1,212.7 s |
| **IQR** | **282.6 s** |

**Duration histogram:**

| range (s) | count | fraction |
|---|---|---|
| [300, 360) | 1,495 | 47.6% |
| [360, 420) | 287 | 9.1% |
| [420, 480) | 101 | 3.2% |
| [480, 540) | 87 | 2.8% |
| [540, 600) | 559 | 17.8% |
| [600, 700) | 579 | 18.4% |
| [700, 1300) | 33 | 1.1% |

Videos cluster at two durations: ≈300 s (47.6%) and ≈600 s (17.8% + 18.4%), with a tail up to 1,213 s. This bimodal pattern reflects the 5-minute and 10-minute recording clips used in data collection.

### 2.2 QA pairs per video

From the paper: 9,448 QA pairs over 3,141 videos → **mean 3.01 QA/video**.

**Annotation-level distribution not available (E1 — gated).** The full distribution (videos with 1 vs. several questions) requires the JSONL files. From the schema and examples, a "typical video contributes a handful of questions across multiple categories" (data/README.md). This will be computed on rerun after access approval.

### 2.3 Session model — critical finding

**Each question is evaluated independently. There is no shared accumulating stream.**

Evidence from three sources, quoted directly:

**`lmms_eval/tasks/sember/utils.py`, `sember_doc_to_visual` (line 59):**
```python
question_time = doc.get("question_time", None)
return [{"video_path": full_path, "video_end": question_time}]
```
Each call to the task doc-to-visual function returns the video trimmed to `question_time` for that specific question. There is no concept of a "session" — each QA pair is a standalone document.

**`lmms_eval/models/simple/qwen3_vl.py` (line 307–308):**
```python
if visual.get("video_end") is not None:
    video_kwargs["video_end"] = visual["video_end"]
```
The model wrapper passes `video_end` to the video loader, which discards all frames after `question_time`. Each model call is a fresh forward pass.

**`data/README.md` — Streaming Evaluation Contract:**
> "Each question carries a `question_time` in seconds. The evaluation respects Grounded Streaming Episodic Retrieval (GSER): the model is shown only the video segment `[0, question_time]`. Frames after `question_time` are never sampled, so the model cannot use future context. This is enforced inside the patched model wrappers in `lmms_eval/models/simple/internvl3.py` and `lmms_eval/models/simple/qwen3_vl.py`."

**Consequence for this project:** S-EMBER has no state to retain between questions. There is no "session" in the FM-switching sense — no accumulating KV cache, no growing context window that a retention policy could manage. The GSER contract deliberately makes each question stateless. A runtime state-retention study needs a workload where a shared accumulating stream grows over time and is consulted by multiple queries; S-EMBER does not have this property.

---

## §3 — Evidence Distance (Analysis B) — PARTIAL

**Full distribution requires annotation access (E1 — gated).**

### What is computable without annotations

The grounding schema (from `data/README.md`) defines:

| field | description |
|---|---|
| `question_time` | Seconds into video when question is triggered |
| `answer_start_time` | Start of annotated evidence window (s) |
| `answer_end_time` | End of annotated evidence window (s) |
| `memory_recency` | Pre-computed = `question_time - answer_end_time` (s) |
| `answer_range` | Pre-computed = `answer_end_time - answer_start_time` (s) |

From the worked example in `data/README.md`:
```json
{
  "question_time": 300.0,
  "answer_start_time": 146.0,
  "answer_end_time": 233.0,
  "memory_recency": 154.0,
  "answer_range": 87.0
}
```
Evidence distance (nearest end): 300.0 − 233.0 = **67.0 s** (= `question_time - answer_end_time`).  
Evidence distance (farthest start): 300.0 − 146.0 = **154.0 s** (= `memory_recency`).

The `memory_recency` field is the pre-computed evidence distance to the start of the evidence window. The study spec's "evidence distance" uses `question_time - answer_end_time` as primary (nearest end of window).

### What the paper reports

The paper (arXiv 2607.02689) introduces "memory recency" as a key axis. From the task description, questions span from very recent events (answer evidence seconds ago) to distant events (evidence hundreds of seconds in the past), and one goal of S-EMBER is to test this full range. However, whether the distribution is wide or narrow cannot be confirmed from annotations alone (E1 blocked).

### Histogram placeholder

The script produces `study_h_evidence_distance_hist.csv` when annotations are available. Columns: `lo_s, hi_s, count`. Log-spaced buckets: [0,1), [1,5), [5,15), [15,30), [30,60), [60,120), [120,300), [300+).

---

## §4 — Exclusion Check (Analysis C) — REQUIRES ANNOTATIONS

Counts require JSONL access (E1). The `counting_objects_events` category is one of 8 categories defined in `utils.py`:

```python
QUESTION_CATEGORIES = [
    "location_trace",
    "sequential_action",
    "counting_objects_events",
    "visual_detail_recall",
    "temporal_ordering_recognition",
    "time_duration",
    "object_comparison",
    "spatial_aware_reasoning",
]
```

The fraction of QA pairs in `counting_objects_events` and the remaining n after exclusion will be computed on rerun. Placeholder in `study_h_exclusion.json` once annotations are accessible.

---

## §5 — Answer Format and Scoring (Analysis D)

Determined from codebase (no annotation access required).

### MCQ task (`sember_mcq.yaml` + `utils.py`)

- **Output type:** `generate_until` — model generates text, truncated at max 16 tokens.
- **Scoring:** Exact letter match (A/B/C/D/E). No LLM judge.
- **Parsing:** `_parse_mcq_choice` extracts first valid letter from model response.
- **Metric:** `sember_mcq_accuracy` — fraction of correct letters, reported overall and per category.

```yaml
output_type: generate_until
generation_kwargs:
  max_new_tokens: 16
  temperature: 0
```

### Grounding task (`sember_grounding.yaml` + `utils.py`)

- **Output type:** `generate_until` — model generates answer text + time interval, max 256 tokens.
- **Scoring (primary, automatic):** Temporal IoU between predicted `[pred_start, pred_end]` and ground-truth `[answer_start_time, answer_end_time]`. No LLM judge required.
- **Scoring (optional, requires Gemini):** `tools/judge_grounding.py` uses Gemini (default: `gemini-3.1-flash`) to score free-text answer correctness. Prompt: CORRECT/WRONG binary judgment against multi-tier gold answers. **This component requires a GEMINI_API_KEY.**

```yaml
metric_list:
  - metric: sember_temporal_iou
    aggregation: !function utils.sember_aggregate_temporal_iou
```

**Answer format expected from model:**
```
Answer: <1-2 sentence answer>
Time: [<start_seconds>, <end_seconds>]
```

### LLM judge requirement

The primary evaluation (temporal IoU for grounding, letter match for MCQ) requires **no LLM judge**. The optional grounding answer-text correctness scoring requires a Gemini API key. The benchmark can be run to completion without an LLM judge; the judge adds a second accuracy metric on top.

---

## §6 — Feasibility (Analysis E)

**Qwen3-VL-8B-Instruct on A6000 (48 GB vRAM)**

Token formula (Study D): 324 vision tokens per 560×560 frame. Qwen3-VL: patch_size=16, merge_size=2 → 560/16=35 → 18×18 grid = 324 tokens.  
Ray-Ban Meta glasses: 1920×1080. Short-side 560 → 560×315 → 20×11 = 220 tokens (lower bound).  
KV bytes per token: 57,344 B (Study A/B, content-independent).  
Model weights: ~16 GB. Usable vRAM for KV+activations: ~32 GB.

| scenario | frames | tokens (upper) | KV GB (upper) | fits 48 GB? |
|---|---|---|---|---|
| median video (367s) @ 1fps | 367 | 118,908 | 6.8 | YES |
| median video (367s) @ 2fps | 734 | 237,816 | 13.6 | YES |
| median video (367s) @ 4fps | 1,469 | 475,956 | 27.3 | YES |
| max video (1213s) @ 1fps | 1,212 | 392,688 | 22.5 | YES |
| max video (1213s) @ 2fps | 2,425 | 785,700 | 45.1 | **OOM** |
| max video (1213s) @ 4fps | 4,850 | 1,571,400 | 90.1 | **OOM** |

**Practical ceiling:** For median-length videos (367 s), 1–4 fps fits comfortably. For the longest videos (≈1,213 s), 1 fps is the safe ceiling (22.5 GB KV). At 2 fps for a 1,213 s video, KV alone requires 45.1 GB, leaving only 2.9 GB margin — effectively OOM given activation memory overhead. The practical evaluation rate for S-EMBER would be **1 fps**, consistent with the lmms-eval defaults (`NUM_FRAME=64` on a 600s video = ~0.1 fps, much lower than 1 fps).

From `data/README.md`: "CUDA out of memory at 128 frames on a 24 GB card" — `NUM_FRAME=16 TOTAL_MAX_NUM=16` is the recommended fallback. At 600 s / 16 frames = 1 frame per 37.5 s. The intended evaluation framerate is much sparser than 1 fps.

---

## §7 — Sanity Checks

| check | status | note |
|---|---|---|
| SC1: QA count = 9,448 | **BLOCKED** (E1) | Requires grounding JSONL |
| SC2: Video count = 3,141 | **PASS** | 3,141 filenames parsed from HF metadata |
| SC3: All QA have valid grounding | **BLOCKED** (E1) | Requires grounding JSONL |
| SC4: No negative evidence distances | **BLOCKED** (E1) | Requires grounding JSONL |
| Video duration total ≈ 388 h | **PASS** | 387.9 h from filenames |
| Annotation size plausible | **PASS** | 11.1 + 10.6 = 21.7 MB from HF metadata |

SC1, SC3, SC4 will be computed on rerun after access approval.

---

## §8 — What Cannot Be Determined From Annotations Alone

Even with annotation access granted, the following cannot be determined without video:
- Frame rate of raw recordings (metadata not in JSONL; requires video container headers).
- Actual resolution (1920×1080 from paper, but individual clips may vary).
- Whether any video is corrupted or has A/V sync issues.
- Per-frame visual complexity (scene change rate, object density, motion blur).

---

## §9 — Plain Answers to the Four Required Questions

**1. Do questions within a video share an accumulating stream, or is each independent?**

**Each question is independent.** The GSER evaluation contract (documented in `data/README.md`, enforced in `utils.py` and model wrappers) gives each question a fresh forward pass over `video[0, question_time]`. There is no shared KV cache, no growing context window, and no state carried between questions from the same video. S-EMBER has no "session" in the FM-switching sense.

**2. Is the evidence-distance distribution wide, or do most answers ground within the last few seconds?**

**Cannot be confirmed (E1 — gated access).** The `memory_recency` field (pre-computed as `question_time - answer_end_time`) is present in annotations but those files are blocked. From the paper and one schema example: the example has `memory_recency = 154.0 s` (evidence starts 154 s before question time in a 300 s video), suggesting the benchmark intentionally spans wide distances. The paper positions memory recency as a key evaluation axis. Distribution statistics will be available on rerun.

**3. Do task types differ meaningfully in evidence distance, with numbers?**

**Cannot confirm (E1).** From task design: `time_duration` questions (e.g., "how long did I hold X?") require grounding a complete action interval, likely yielding longer evidence windows; `visual_detail_recall` may ground in recent frames. Numeric differences by category require JSONL access.

**4. After excluding counting, how many QA pairs remain and across how many videos?**

**Cannot confirm (E1).** Will be computed on rerun. Upper bound: 9,448 − (counting fraction × 9,448). From the 8 categories, if `counting_objects_events` is roughly 1/8 of all pairs, remaining ≈ 8,267 pairs; actual number depends on annotation distribution.

---

## §10 — Escalation Summary

### E1 — HF gated access blocked

**What to do:** Visit https://huggingface.co/datasets/facebook/S-EMBER, log in as `psharma05`, fill in the gated access form (full name, affiliation, agree to CC BY-NC 4.0 non-commercial use), and wait for approval. Then rerun `study_h_sember_structure.py` — all annotation-level analyses will run automatically.

### E2 — No shared accumulating stream (stop condition)

**Finding:** S-EMBER's evaluation protocol (GSER) makes each question a fresh, stateless forward pass. There is no accumulating session stream that a retention policy could manage.

**Implication for FM-switching:** S-EMBER cannot serve as the workload for a study on runtime state retention. The retention decision has nothing to bite on: there is no state to retain, no session to grow, and no policy that would differ between "retain full session" and "discard and rebuild." If S-EMBER videos were to be used, a custom evaluation harness would need to be built that processes questions about the same video sequentially (sharing a KV cache or rolling summary), which is not part of the existing benchmark protocol and would require separate annotation work to define the inter-question ordering and the session boundary.

**Recommendation:** Reject S-EMBER as the workload. The retention decision problem requires a benchmark where (a) a session accumulates over time, (b) multiple queries are posed against the same growing context, and (c) the session can be represented at different fidelities (full / window / summary). S-EMBER has none of these properties in its evaluation protocol.

---

## Provenance

```json
{
  "git_commit": "pre-provenance",
  "script": "study_h_sember_structure.py",
  "model": "none",
  "device": "cpu",
  "n": "3141 videos (filenames only; annotations blocked)",
  "timestamp": "2026-08-31",
  "sember_github": "github.com/facebookresearch/S-EMBER (cloned)",
  "sember_hf": "huggingface.co/datasets/facebook/S-EMBER (access blocked for psharma05)"
}
```
