# Results Index — FM-switching

Machine-readable provenance is embedded in each JSON as `_provenance`. This index is the human-readable cross-box correctness trail. One row per result file.

## Naming schema

| type | pattern | example |
|---|---|---|
| Accuracy frontier | `frontier_<model>.json` | `frontier_qwen7b.json` |
| Per-question arrays | `frontier_<model>_perquestion.json` | `frontier_smollm2_perquestion.json` |
| Frame sweep | `framesweep_<model>.json` | `framesweep_qwen7b.json` |
| Inertia curve | `inertia_<model>_<device>.json` | `inertia_smollm2_jetson.json` |
| Premise / pilot | `premise_<model>_<tag>.json` | `premise_qwen7b_n150.json` |
| Historical sweep | `representation_sweep_<model>_<tag>.json` | `representation_sweep_qwen7b_n150.json` |
| Caches | `captions_cache.json`, `summaries_cache_80.json`, `summaries_cache_200.json` | — |

**Model slugs:** `qwen7b` = Qwen/Qwen2.5-7B-Instruct · `smollm2` = HuggingFaceTB/SmolLM2-1.7B-Instruct  
**Device slugs:** `a6000` = NVIDIA RTX A6000 · `jetson` = Jetson AGX Orin 15W · `a5000` = NVIDIA RTX A5000

---

## Active result files

| file | script | model | device | n | headline | old name |
|---|---|---|---|---|---|---|
| `frontier_qwen7b.json` | `representation_frontier.py` | qwen7b | a6000 | 500 | full=50.2%, summary-80≈full (47.0%), window-10≈full (50.6%) at 3× fewer tokens | `exp10_representation_frontier_500.json` |
| `frontier_qwen7b_perquestion.json` | `representation_frontier.py` | qwen7b | a6000 | 500 | per-question arrays for above | `exp10_per_question.json` |
| `frontier_smollm2.json` | `representation_frontier.py` | smollm2 | a6000 | 500 | full=38.4%, **summary-80 matches full** (38.8%) at 3.4× fewer tokens (385 vs 1290 tok) | `exp10_frontier_500_smollm2.json` |
| `frontier_smollm2_perquestion.json` | `representation_frontier.py` | smollm2 | a6000 | 500 | per-question arrays for above | `exp10_per_question_smollm2.json` |
| `framesweep_qwen7b.json` | `frame_sweep.py` | qwen7b | a6000 | 150 | accuracy plateaus 16→32 frames; 16 is sufficient | `exp7_frame_sweep.json` |
| `frontier_skipped_clips.json` | `representation_frontier.py` | — | a6000 | — | CUDA-failed clips during Phase 1 captioning | `exp10_skipped_clips.json` |

## Superseded / pilot files (kept for lineage)

| file | script | model | device | n | status | old name |
|---|---|---|---|---|---|---|
| `premise_qwen7b_n150.json` | `premise_egoschema.py` | qwen7b | a6000 | 150 | **SUPERSEDED** by frontier_qwen7b (500-clip); premise GO verdict still valid | `exp7_premise.json` |
| `representation_sweep_qwen7b_n150.json` | `representation_sweep_n150.py` | qwen7b | a6000 | 150 | **SUPERSEDED** by frontier_qwen7b (summary condition now in full 8-condition set) | `exp7_representation_sweep.json` |
| `premise_qwen7b_smoke.json` | `premise_egoschema.py` | qwen7b | a6000 | 5 | **SMOKE TEST ONLY** — no statistical value | `exp7_smoke.json` |

## Pending (not yet generated)

| file | script | model | device | status |
|---|---|---|---|---|
| `inertia_smollm2_jetson.json` | `inertia_profile.py` | smollm2 | jetson | **PENDING** — Jetson AGX Orin run required |
| `inertia_qwen7b_a5000.json` | `inertia_profile.py` | qwen7b | a5000 | **PENDING** — A5000 run required |

## Caches (not tracked in git — regenerable)

| file | content | note |
|---|---|---|
| `captions_cache.json` | VLM captions for 500 EgoSchema clips (Qwen2.5-VL-3B, 16 frames) | Extended from 150→500 during frontier_qwen7b run |
| `summaries_cache_80.json` | LLM summaries ~80 tok per clip (Qwen2.5-7B-Instruct) | Reused by smollm2 run |
| `summaries_cache_200.json` | LLM summaries ~200 tok per clip (Qwen2.5-7B-Instruct) | New during frontier_qwen7b run |
