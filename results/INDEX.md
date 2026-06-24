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
**Device slugs:** `a6000` = NVIDIA RTX A6000 · `jetson` = Jetson AGX Orin 15W

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
| `inertia_qwen7b_a6000.json` | `inertia_profile.py` | qwen7b | a6000 | optional — heterogeneous-tier extension only (not MVP) |

(`inertia_smollm2_jetson.json` was pending; now **generated** on the Jetson — see the appended-rows table below.)

## Caches (not tracked in git — regenerable)

| file | content | note |
|---|---|---|
| `captions_cache.json` | VLM captions for 500 EgoSchema clips (Qwen2.5-VL-3B, 16 frames) | Extended from 150→500 during frontier_qwen7b run |
| `summaries_cache_80.json` | LLM summaries ~80 tok per clip (Qwen2.5-7B-Instruct) | Reused by smollm2 run |
| `summaries_cache_200.json` | LLM summaries ~200 tok per clip (Qwen2.5-7B-Instruct) | New during frontier_qwen7b run |

## Appended rows (per-box, append-only to avoid cross-box edit conflicts)

| file | experiment | model | device | n | headline | source commit | old name |
|---|---|---|---|---|---|---|---|
| `inertia_smollm2_jetson.json` | `inertia_profile.py` | smollm2 | jetson | 5 reps × 7 depths (128–8192 tok) | re-prefill super-linear → 12.6 s @ 8k tok (0.34 s @ 128); KV residency linear 0.1875 MB/tok (1.5 GB @ 8k); D2H+serialize transfer 0.07 s → 4.06 s | pre-provenance (run 2026-06-10, predates convention) | `exp_inertia_jetson-edge_SmolLM2-1.7B.json` |
| `inertia_smollm2_a6000.json` | `inertia_profile.py` | smollm2 | a6000 | 5 reps × 7 depths (128–8192 tok) | prefill super-linear: 12.5 ms @ 128 tok → 469.5 ms @ 8192 tok; ~2× faster than Jetson at every depth | 68e6d734 | new (no old name) |
| `frontier_locomo_qwen7b.json` | `frontier_locomo.py` | qwen7b | a6000 | 50 single-hop (cat=1) questions, 10 conversations | INCOMPRESSIBLE: full=26.0%, summary-80=6.0% (gap −20pp, p=0.016), summary-200=6.0% (gap −20pp, p=0.009). SmolLM2 'full' infeasible (2K ctx << 11K–23K history). | f6fb7d1 | new |
| `frontier_findingdory_qwenvl3b.json` | `frontier_findingdory_v2.py` | qwenvl3b (yali30/findingdory-qwen2.5-VL-3B-finetuned) | a6000 | 300 (30 ep/cat × 2 cats × 5 budgets {96,48,24,12,6}); authors' relaxed_match metric; video pathway; empty system msg | INCOMPRESSIBLE (cliff at b=48): temporal rm 0.790→0.087 (b96→b48), multi-goal 0.339→0.010; collapse is in REASONING set (gold_survived≥1, n=30 at b=48); OOD confound (model trained only on 96 frames); REASONING set non-monotonic b<48 due to selection bias. Gate: rm=0.565 at b=96 (parse_ok=100%, consistent with authors' ~52.4% Habitat HL-SR). | f6fb7d1 | overwrites prior v1 |
| `locomo_audit_qwen7b.json` | `locomo_audit.py` | qwen7b | a6000 | 50 cat=1 single-hop (ceiling=282); omission judge=Qwen2.5-7B YES/NO presence; evidence distance via LoCoMo dia_id annotations | INCOMPRESSIBLE BY OMISSION: full=26%, sum80=6%, sum200=6% (all 50 q in FAR bin, avg 12K tok from end). 91% of sum80 failures = gold absent from summary (compression-omission); 9% = model reasoning failure. full−sum80 gap +0.20, spread across 12/50 questions (top-1=8%, top-3=25% of gap). Mechanism confirmed: summaries fail by discarding the sparse fact, not by failing to reason. | new | new |
| `frontier_infinithor_qwen7b.json` | `frontier_infinithor.py` | qwen7b | a6000 | 60 multi-clue (NsiEH), 65/219 traj_ids shipped on HuggingFace; conditions blind/summary-80/full; lazy LLM judge | COMPRESSIBLE — gate FAIL: full=0.58, summary-80=0.55, blind=0.36 (non-salient). Full beats blind +0.22 (history used, anchors recoverable). Full−summary-80 gap only +0.03 on non-salient (threshold >0.05 not met). Distance: NEAR gap=+0.18 (n=11), MID gap=0.00 (n=5), FAR gap=−0.08 (n=13) — summary outperforms full at far distance. Dispersion: gap carried entirely by 3 trajectories, 18/21 non-salient trajs show zero or negative gap. Interpretation: at 873–2,149 tokens (mean 1,441) templated oracle logs, summary-80 captures relevant events; compressible structured-log regime. Reduced gate / orientation audit, not a benchmark characterisation. | new | new |
| `locomo_audit_scaled_qwen7b.json` | `locomo_audit_scaled.py` | qwen7b | a6000 | 282 cat=1 single-hop (full ceiling); conditions blind/window-10/summary-80/summary-200/full; omission judge=Qwen2.5-7B; evidence distance via dia_id annotations | INCOMPRESSIBLE BY OMISSION (scaled, confirmed): full=34.0% [28.8,39.8%], summary-80=9.9% [7.0,14.0%], gap=−24.1pp (p<0.001***), summary-200=9.9% (gap=−24.1pp, p<0.001***), window-10=22.0% (gap=−12.1pp, p<0.001***). Omission: 92.3% of gap cases (72/78) = gold absent from summary; 7.7% = model reasoning failure. Dispersion: gap spread across 78/282 questions; top-1=1.5%, top-3=4.4% of gap — not an outlier artifact. Distance: 96.5% FAR (>20 turns), full−s80 gap at FAR = +0.243; confirms structurally far-distance sparse-fact retrieval failure. | new | new |
| `geolife_microgate_qwen7b.json` | `geolife_audit.py` (micro-gate) | qwen7b | a6000 | 123 non-salient sequential-recall questions; 20 rich weeks; Users 000+052 (GeoLife, urban Beijing); conditions blind/window-5/summary-80/summary-200/full; T1 predecessor/T2 successor/T4 transport-mode templates | INCOMPRESSIBLE — MICRO-GATE PASS: full=58.5%, summary-80=22.0%, gap=+36.6pp (p<0.0001). blind=0.0% (no prior leakage), window-5=0.8% (far-distance confirmed). Two compression mechanisms: entity omission (gold entity absent from summary, 50% of gap cases) + ordering omission (gold entity present but sequential adjacency not recoverable from unordered summary inventory, 50%). T4 transport-mode: full=100%, s80=0%, gap=+100pp. Contexts 251–728 tokens. Physical-world sequential-ordering incompressibility: summaries are unordered inventories, cannot answer what came before/after X or what mode was used for leg N. | new | new |
