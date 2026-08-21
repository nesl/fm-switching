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

**Model slugs:** `qwen7b` = Qwen/Qwen2.5-7B-Instruct · `smollm2` = HuggingFaceTB/SmolLM2-1.7B-Instruct · `qwen3b` = Qwen/Qwen2.5-3B-Instruct · `qwenvl3b` = Qwen/Qwen2.5-VL-3B-Instruct (or fine-tuned variant) · `qwenvl7b` = Qwen/Qwen2.5-VL-7B-Instruct · `mistral7b` = mistralai/Mistral-7B-Instruct-v0.2  
**Device slugs:** `a6000` = NVIDIA RTX A6000 (flash, GPU 1) · `rtx3090ti` = NVIDIA GeForce RTX 3090 Ti (flash, GPU 0) · `jetson_orin` = Jetson AGX Orin (separate SSH host) · `jetson` = legacy alias for `jetson_orin` (pre-reorganization files only)

**Simulator pin:** `simulator/cost_model.py` imports these six files by path at load time and must not be moved:
`results/frontier_qwen7b.json`, `results/frontier_qwen7b_perquestion.json`,
`results/frontier_smollm2.json`, `results/frontier_smollm2_perquestion.json`,
`results/inertia_smollm2_a6000.json`, `results/inertia_smollm2_jetson.json`.

---

## Active result files

| file | script | model | device | n | headline | old name |
|---|---|---|---|---|---|---|
| `frontier_qwen7b.json` | `representation_frontier.py` | qwen7b | a6000 | 500 | full=50.2%, summary-80≈full (47.0%), window-10≈full (50.6%) at 3× fewer tokens | `exp10_representation_frontier_500.json` |
| `frontier_qwen7b_perquestion.json` | `representation_frontier.py` | qwen7b | a6000 | 500 | per-question arrays for above | `exp10_per_question.json` |
| `frontier_smollm2.json` | `representation_frontier.py` | smollm2 | a6000 | 500 | full=38.4%, **summary-80 matches full** (38.8%) at 3.4× fewer tokens (385 vs 1290 tok) | `exp10_frontier_500_smollm2.json` |
| `frontier_smollm2_perquestion.json` | `representation_frontier.py` | smollm2 | a6000 | 500 | per-question arrays for above | `exp10_per_question_smollm2.json` |
| `framesweep_qwen7b.json` *(pinned at results/ root — referenced by frame_sweep.py default output and plots/fidelity/plot_frame_sweep.py default input)* | `frame_sweep.py` | qwen7b | a6000 | 150 | accuracy plateaus 16→32 frames; 16 is sufficient | `exp7_frame_sweep.json` |
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

## Caches (tracked in git — content-addressed, not regenerated per run)

`captions_cache.json`, `summaries_cache_80.json`, `summaries_cache_200.json`,
`locomo_summaries_80.json`, and `locomo_summaries_200.json` **are tracked in git**.
They are not regenerated on every run; a run that needs a cached value reads it,
and a run that generates new entries appends to the cache. Do not gitignore them.

| file | content | note |
|---|---|---|
| `captions_cache.json` | VLM captions for 500 EgoSchema clips (Qwen2.5-VL-3B, 16 frames) | Extended from 150→500 during frontier_qwen7b run |
| `summaries_cache_80.json` | LLM summaries ~80 tok per clip for EgoSchema (Qwen2.5-7B-Instruct) | Reused by smollm2 run |
| `summaries_cache_200.json` | LLM summaries ~200 tok per clip for EgoSchema (Qwen2.5-7B-Instruct) | New during frontier_qwen7b run |
| `locomo_summaries_80.json` | LLM summaries ~80 tok per LoCoMo conversation (Qwen2.5-7B-Instruct) | Generated during locomo_audit_scaled run |
| `locomo_summaries_200.json` | LLM summaries ~200 tok per LoCoMo conversation (Qwen2.5-7B-Instruct) | Generated during locomo_audit_scaled run |

## Appended rows (per-box, append-only to avoid cross-box edit conflicts)

| file | experiment | model | device | n | headline | source commit | old name |
|---|---|---|---|---|---|---|---|
| `inertia_smollm2_jetson.json` | `inertia_profile.py` | smollm2 | jetson | 5 reps × 7 depths (128–8192 tok) | re-prefill super-linear → 12.6 s @ 8k tok (0.34 s @ 128); KV residency linear 0.1875 MB/tok (1.5 GB @ 8k); D2H+serialize transfer 0.07 s → 4.06 s | pre-provenance (run 2026-06-10, predates convention) | `exp_inertia_jetson-edge_SmolLM2-1.7B.json` |
| `inertia_smollm2_a6000.json` | `inertia_profile.py` | smollm2 | a6000 | 5 reps × 7 depths (128–8192 tok) | prefill super-linear: 12.5 ms @ 128 tok → 469.5 ms @ 8192 tok; ~2× faster than Jetson at every depth | 68e6d734 | new (no old name) |
| `results/fidelity/frontier_locomo_qwen7b.json` | `frontier_locomo.py` | qwen7b | a6000 | 50 single-hop (cat=1) questions, 10 conversations | INCOMPRESSIBLE: full=26.0%, summary-80=6.0% (gap −20pp, p=0.016), summary-200=6.0% (gap −20pp, p=0.009). SmolLM2 'full' infeasible (2K ctx << 11K–23K history). | f6fb7d1 | new |
| `frontier_findingdory_qwenvl3b.json` | `frontier_findingdory_v2.py` | qwenvl3b (yali30/findingdory-qwen2.5-VL-3B-finetuned) | a6000 | 300 (30 ep/cat × 2 cats × 5 budgets {96,48,24,12,6}); authors' relaxed_match metric; video pathway; empty system msg | INCOMPRESSIBLE (cliff at b=48): temporal rm 0.790→0.087 (b96→b48), multi-goal 0.339→0.010; collapse is in REASONING set (gold_survived≥1, n=30 at b=48); OOD confound (model trained only on 96 frames); REASONING set non-monotonic b<48 due to selection bias. Gate: rm=0.565 at b=96 (parse_ok=100%, consistent with authors' ~52.4% Habitat HL-SR). | f6fb7d1 | overwrites prior v1 |
| `results/archive/locomo_audit_qwen7b.json` *(moved to archive 2026-08-19; superseded by locomo_audit_scaled_qwen7b.json n=282)* | `locomo_audit.py` | qwen7b | a6000 | 50 cat=1 single-hop (ceiling=282); omission judge=Qwen2.5-7B YES/NO presence; evidence distance via LoCoMo dia_id annotations | INCOMPRESSIBLE BY OMISSION: full=26%, sum80=6%, sum200=6% (all 50 q in FAR bin, avg 12K tok from end). 91% of sum80 failures = gold absent from summary (compression-omission); 9% = model reasoning failure. full−sum80 gap +0.20, spread across 12/50 questions (top-1=8%, top-3=25% of gap). Mechanism confirmed: summaries fail by discarding the sparse fact, not by failing to reason. | new | new |
| `results/fidelity/frontier_infinithor_qwen7b.json` | `frontier_infinithor.py` | qwen7b | a6000 | 60 multi-clue (NsiEH), 65/219 traj_ids shipped on HuggingFace; conditions blind/summary-80/full; lazy LLM judge | COMPRESSIBLE — gate FAIL: full=0.58, summary-80=0.55, blind=0.36 (non-salient). Full beats blind +0.22 (history used, anchors recoverable). Full−summary-80 gap only +0.03 on non-salient (threshold >0.05 not met). Distance: NEAR gap=+0.18 (n=11), MID gap=0.00 (n=5), FAR gap=−0.08 (n=13) — summary outperforms full at far distance. Dispersion: gap carried entirely by 3 trajectories, 18/21 non-salient trajs show zero or negative gap. Interpretation: at 873–2,149 tokens (mean 1,441) templated oracle logs, summary-80 captures relevant events; compressible structured-log regime. Reduced gate / orientation audit, not a benchmark characterisation. | new | new |
| `results/fidelity/locomo_audit_scaled_qwen7b.json` | `locomo_audit_scaled.py` | qwen7b | a6000 | 282 cat=1 single-hop (full ceiling); conditions blind/window-10/summary-80/summary-200/full; omission judge=Qwen2.5-7B; evidence distance via dia_id annotations | INCOMPRESSIBLE BY OMISSION (scaled, confirmed): full=34.0% [28.8,39.8%], summary-80=9.9% [7.0,14.0%], gap=−24.1pp (p<0.001***), summary-200=9.9% (gap=−24.1pp, p<0.001***), window-10=22.0% (gap=−12.1pp, p<0.001***). Omission: 92.3% of gap cases (72/78) = gold absent from summary; 7.7% = model reasoning failure. Dispersion: gap spread across 78/282 questions; top-1=1.5%, top-3=4.4% of gap — not an outlier artifact. Distance: 96.5% FAR (>20 turns), full−s80 gap at FAR = +0.243; confirms structurally far-distance sparse-fact retrieval failure. | new | new |
| `results/archive/geolife_microgate_qwen7b.json` | `geolife_audit.py` (micro-gate) | qwen7b | a6000 | 123 non-salient sequential-recall questions; 20 rich weeks; Users 000+052 (GeoLife, urban Beijing); conditions blind/window-5/summary-80/summary-200/full; T1 predecessor/T2 successor/T4 transport-mode templates | INCOMPRESSIBLE — MICRO-GATE PASS: full=58.5%, summary-80=22.0%, gap=+36.6pp (p<0.0001). blind=0.0% (no prior leakage), window-5=0.8% (far-distance confirmed). Two compression mechanisms: entity omission (gold entity absent from summary, 50% of gap cases) + ordering omission (gold entity present but sequential adjacency not recoverable from unordered summary inventory, 50%). T4 transport-mode: full=100%, s80=0%, gap=+100pp. Contexts 251–728 tokens. Physical-world sequential-ordering incompressibility: summaries are unordered inventories, cannot answer what came before/after X or what mode was used for leg N. | new | new |

## Phase 0a — Multi-model regime audit (appended from a6000, commit 9258061)

All phase0a files live under `results/fidelity/multimodel/`. Source script is `experiments/phase0a_*.py`
(post-migration: `experiments/fidelity/multimodel_*.py`). All runs: a6000, commit 9258061.
Subset membership: `data/audit_subsets/phase0a/` (tracked in git; IDs verified against result JSONs 2026-08-19).

| file | script | model | device | n | headline | source commit |
|---|---|---|---|---|---|---|
| `results/fidelity/multimodel/egoschema_qwen7b_n60.json` | `phase0a_egoschema.py` | qwen7b | a6000 | 60 | EgoSchema: full≈sum80≈sum200; gist-compressible under Qwen | 9258061 |
| `results/fidelity/multimodel/egoschema_mistral7b_n60.json` | `phase0a_egoschema.py` | mistral7b | a6000 | 60 | EgoSchema: full≈sum80≈sum200; gist-compressible under Mistral | 9258061 |
| `results/fidelity/multimodel/egoschema_sum80_mistral7b.json` | `phase0a_egoschema.py` | mistral7b | a6000 | 60 | per-condition summary-80 checkpoint for above | 9258061 |
| `results/fidelity/multimodel/egoschema_sum200_mistral7b.json` | `phase0a_egoschema.py` | mistral7b | a6000 | 60 | per-condition summary-200 checkpoint for above | 9258061 |
| `results/fidelity/multimodel/infinithor_qwen7b_n60.json` | `phase0a_infinithor.py` | qwen7b | a6000 | 60 (n57 excl 3 truncated) | Infini-THOR: Qwen SUMMARY≈FULL non-salient (gap +0.098 p=0.211); all-pool n57 gap +0.070 p=0.324 | 9258061 |
| `results/fidelity/multimodel/infinithor_mistral7b_n60.json` | `phase0a_infinithor.py` | mistral7b | a6000 | 60 (n57 excl 3 truncated) | Infini-THOR: Mistral FULL>>SUMMARY all-pool n57 (gap +0.140 p=0.033); non-salient gap +0.073 p=0.441 | 9258061 |
| `results/fidelity/multimodel/infinithor_qwen7b_n40.json` | `phase0a_infinithor.py` | qwen7b | a6000 | 40 | Infini-THOR non-salient subset (pre-expansion) | 9258061 |
| `results/fidelity/multimodel/infinithor_mistral7b_n40.json` | `phase0a_infinithor.py` | mistral7b | a6000 | 40 | Infini-THOR non-salient subset (pre-expansion) | 9258061 |
| `results/fidelity/multimodel/infinithor_sum80_qwen7b.json` | `phase0a_infinithor.py` | qwen7b | a6000 | 60 | per-condition summary-80 checkpoint | 9258061 |
| `results/fidelity/multimodel/infinithor_sum80_mistral7b.json` | `phase0a_infinithor.py` | mistral7b | a6000 | 60 | per-condition summary-80 checkpoint | 9258061 |
| `results/fidelity/multimodel/infinithor_sum200_qwen7b.json` | `phase0a_infinithor.py` | qwen7b | a6000 | 60 | per-condition summary-200 checkpoint | 9258061 |
| `results/fidelity/multimodel/infinithor_sum200_mistral7b.json` | `phase0a_infinithor.py` | mistral7b | a6000 | 60 | per-condition summary-200 checkpoint | 9258061 |
| `results/fidelity/multimodel/infinithor_truncated_rerun.json` | `phase0a_infinithor_rerun_trunc.py` | qwen7b+mistral7b | a6000 | 3 items | OOM (Qwen, 73K+ tok) and context_exceeded (Mistral, >32K); full condition irrecoverable; items permanently excluded (n=57) | pre-provenance (2026-08-16) |
| `results/fidelity/multimodel/locomo_qwen7b_n100.json` | `phase0a_locomo.py` | qwen7b | a6000 | 100 | LoCoMo: INCOMPRESSIBLE — full>>sum80 (gap p<0.001 under Qwen); Phase 0a gate | 9258061 |
| `results/fidelity/multimodel/locomo_mistral7b_n100.json` | `phase0a_locomo.py` | mistral7b | a6000 | 100 | LoCoMo: INCOMPRESSIBLE — full>>sum80 (gap p<0.001 under Mistral); Phase 0a gate passed | 9258061 |
| `results/fidelity/multimodel/locomo_sum80_mistral7b.json` | `phase0a_locomo.py` | mistral7b | a6000 | 100 | per-condition summary-80 checkpoint | 9258061 |
| `results/fidelity/multimodel/locomo_sum200_mistral7b.json` | `phase0a_locomo.py` | mistral7b | a6000 | 100 | per-condition summary-200 checkpoint | 9258061 |
| `results/fidelity/multimodel/phase0a_analysis.json` | `phase0a_analysis.py` | qwen7b+mistral7b | a6000 | — | computed statistics (regime table, contrasts, token distributions) for audit report | 9258061 |

## Phase 1 — Cost profiling (appended from a6000, commit 5870d45 + fix-up)

All phase1 cost-profile files live under `results/cost/`. Source scripts:
`experiments/phase1_cost_profile.py` → `experiments/cost/cost_profile.py` (post-migration);
`experiments/phase1_update_rerun.py` → `experiments/cost/cost_update_rerun.py`.
Analysis: `experiments/phase1_analysis.py` → `experiments/cost/cost_analysis.py`.

| file | script | model | device | n | headline | source commit |
|---|---|---|---|---|---|---|
| `results/cost/profiles/a6000_qwen7b.json` | `phase1_cost_profile.py` + update rerun | qwen7b | a6000 | 9 L-pts × 5 reps; sum80/200 update corrected (full-L input) | full-restore 165ms→21.7s (linear); warm-append 66ms→330ms; cold/warm ratio 68× at 64K; xC=8K; xB=~65K (corrected) | 5870d45 + fix-up |
| `results/cost/profiles/rtx3090ti_qwen7b.json` | `phase1_cost_profile.py` + update rerun | qwen7b | rtx3090ti | 9 L-pts × 5 reps; update OOM at L≥32K | full-restore OOM at L≥49K; xC=4K; xB=none_in_range (update OOMs before crossover) | 5870d45 + fix-up |
| `results/cost/cost_matrix.csv` | `phase1_analysis.py` | qwen7b | a6000+rtx3090ti | 100 rows | derived CSV: restore/update/transfer costs per representation per L per tier | 5870d45 + fix-up |
| `results/cost/profiles/jetson_orin_qwen7b.json` | `cost_profile.py` + `cost_update_rerun.py` | qwen7b | jetson_orin | 9 L-pts × 5 reps; capped + full-context update | full-restore 4.05s@1k→75.1s@16k, **infeasible ≥24,576** (120s time budget, never OOMs / 65.9 GB unified); cold/warm ratio 36.7× @16K; sum-80 full-update 31s@1k→plateau ~229s. Ran transformers 5.10.2/torch 2.8/SDPA no-flash-attn (vs 4.46.3/flash-attn on flash → tier gap carries a software-stack component). | 642a0b7 |

## E24 — Fidelity-provisioning coupling simulation (2026-08-19)

Script: `simulator/provisioning/sweep.py`. Inputs: Q-table from E05/E11/E13; costs from E21/E22. CPU only; no GPU.
Sweep: 5 capacity × 4 mobility × 3 regime_mix × 3 seeds × 7 policies = 1,260 runs.

| file | script | model | device | n | headline | source commit |
|---|---|---|---|---|---|---|
| `results/orchestration/e24_coupling/<cell>/cell.json` (60 files) | `sweep.py` | — (simulator) | CPU | 1,260 runs | Per-cell SLO fractions, miss-type breakdown, quality metrics for 7 policies | 2026-08-19 |
| `figures/orchestration/e24_phase_diagram.pdf` | `plots/orchestration/plot_e24.py` | — | CPU | 60 cells | Phase diagram: joint improvement over best non-joint baseline | 2026-08-19 |
| `figures/orchestration/e24_phase_diagram_vs_cv.pdf` | `plots/orchestration/plot_e24.py` | — | CPU | 60 cells | Phase diagram: joint improvement over cache_value specifically | 2026-08-19 |
| `reports/e24_coupling_falsification.md` | — | — | — | — | Coupling falsification: placement-aware policies +12pp vs reactive; joint +0–3pp vs cache_value; 7 kill criteria evaluated | 2026-08-19 |

## E24b — Stressed coupling falsification (2026-08-19)

Script: `simulator/provisioning/sweep_b.py`. Inputs: Q-table (E05/E11/E13); costs (E21/E22); 3-edge topology; relative tau ∈ {0.80,0.90,0.95}; drift_rate ∈ {0,20}; L_init=8192 turn_rate=880. CPU only; no GPU.
Sweep: 5 capacity × 4 mobility × 3 regime_mix × 3 tau × 2 drift × 9 policies × 3 seeds = 9,720 runs.

| file | script | model | device | n | headline | source commit |
|---|---|---|---|---|---|---|
| `results/orchestration/e24b_coupling/<cell>/cell.json` (360 files) | `sweep_b.py` | — (simulator) | CPU | 9,720 runs | Per-cell SLO fractions, L-band SLO, miss-type breakdown, p95/p99 latency for 9 policies | 2026-08-19 |
| `figures/orchestration/e24b_phase_diagram_vs_fidelity.pdf` | `plots/orchestration/plot_e24b.py` | — | CPU | 360 cells | Phase diagram: joint improvement over fidelity_only — negative in 52/60 cells | 2026-08-19 |
| `figures/orchestration/e24b_phase_diagram_vs_cv.pdf` | `plots/orchestration/plot_e24b.py` | — | CPU | 360 cells | Phase diagram: joint improvement over cache_value — positive in all cells (+18–40pp) | 2026-08-19 |
| `figures/orchestration/e24b_slo_summary.pdf` | `plots/orchestration/plot_e24b.py` | — | CPU | 360 cells | Mean SLO by policy × regime_mix: fidelity_only beats joint by 6–14pp | 2026-08-19 |
| `reports/e24b_coupling_falsification.md` | — | — | — | — | Null in stressed region: fidelity_only > joint; L-scaling and drift-scaling predictions falsified; thesis narrowed to placement-awareness at current serving node | 2026-08-19 |

## E24c — Final coupling test with shared solver (2026-08-19)

Script: `experiments/orchestration/sweep_e24c.py`. Shared ValueFunction + greedy_knapsack; containment assertion; 10 policies. CPU only; no GPU.
Sweep: 3 capacity × 2 mobility × 2 regime_mix × 2 tau × 2 drift × 10 policies × 3 seeds = 1,440 runs.

| file | script | model | device | n | headline | source commit |
|---|---|---|---|---|---|---|
| `results/orchestration/e24c_coupling/<cell>/cell.json` (48 files) | `sweep_e24c.py` | — (simulator) | CPU | 1,440 runs | Per-cell SLO fractions, refresh instrumentation, multi-fidelity diagnostic, 10 policies | 2026-08-19 |
| `figures/orchestration/e24c_gap_vs_best_decomposed_drift0.pdf` | `plots/orchestration/plot_e24c.py` | — | CPU | 48 cells | Gap heatmap: joint − best-decomposed; all ≤0; max deficit −17.2pp at tau=0.95 mixed | 2026-08-19 |
| `figures/orchestration/e24c_gap_vs_best_decomposed_drift20.pdf` | `plots/orchestration/plot_e24c.py` | — | CPU | 48 cells | Same with drift=20; same sign, smaller magnitude | 2026-08-19 |
| `figures/orchestration/e24c_refresh_cost.pdf` | `plots/orchestration/plot_e24c.py` | — | CPU | 12 cells | Total refresh cost by policy: joint/fidelity_first → inf; fidelity_first_lifecycle → finite (win+full only) | 2026-08-19 |
| `reports/e24c_coupling_final.md` | — | — | — | — | FALSIFIED: median gap −1.3pp; 0/48 cells joint wins by >5pp; fidelity_first_lifecycle beats joint in 38/48 cells; root cause: joint density metric selects sum200 over win, incurring infeasible refresh at large L | 2026-08-19 |
| `results/fidelity/e27_maintenance/e27_maintenance_qwen7b.json` | `experiments/fidelity/e27_maintenance.py` + `e27_merge_results.py` | `qwen7b` | a6000 | 10 LoCoMo convs + 60 EgoSchema clips; 5 modes × 2 budgets × 4 checkpoints | Outcome B: recursive token ratio 0.42 (LoCoMo), latency ratio 0.76; inversion vs window-10 = 86–153× (LoCoMo), 32–72× (EgoSchema); quality gap ≤ 0.01 at 100%; inversion is decode-dominated and structural | 2026-08-20 |
| `figures/fidelity/e27_drift_curves.pdf` | `plots/fidelity/plot_e27.py` | `qwen7b` | a6000 | 10 convs | LoCoMo accuracy vs session coverage: full_regen, recursive, periodic_5 at sum80/sum200; full history and window-10 as references | 2026-08-20 |
| `figures/fidelity/e27_lifecycle_cost.pdf` | `plots/fidelity/plot_e27.py` | `qwen7b` | a6000 | 10 convs + 60 clips | Refresh latency by mode × budget for LoCoMo and EgoSchema; window-10 warm-append reference at 0.066 s | 2026-08-20 |
| `reports/e27_maintenance_mechanism.md` | — | — | — | — | B (fallback): recursive does not kill the cost inversion; decode latency dominates; inversion structural at 7B scale | 2026-08-20 |
| `results/cost/vllm_calibration_a6000_qwen7b.json` | `experiments/cost/vllm_calibration.py` + `e26_diagnostic.py` | `qwen7b` | a6000 | L ∈ {1k,8k,32k,64k} × 5 reps; cold + decode (80,200 tok) + warm-append; YaRN for L≥32k | cold: vLLM 1.10–1.17× faster; warm-append: 1.59–2.55× faster; decode: 35–44 tok/s; within-vLLM window-vs-summary gap 75–181× (all L); HF plateau at L≥32k traced to [:8000]-char summariser bug | 2026-08-21 |

## E29 — Tier-heterogeneous fidelity audit (2026-08-21)

Scripts: `experiments/fidelity/e29_locomo.py`, `experiments/fidelity/e29_egoschema.py`, `experiments/fidelity/e29_analysis.py`. Models: qwen3b (device tier) + qwen7b (edge/cloud tier). Subsets: phase0a fixed seeds (locomo n=100, egoschema n=60). Conditions: blind, window-10, sum-80, sum-200, full (own) + cross (3B reading 7B summaries; 7B reading 3B summaries). GPU: A6000 (GPU 1).

| file | script | model | device | n | headline | source commit |
|---|---|---|---|---|---|---|
| `results/fidelity/e29_tier_heterogeneous/locomo_qwen3b_n100.json` | `e29_locomo.py` | qwen3b | a6000 | 100 | LoCoMo: full=0.230, sum80=0.090, sum200=0.120, win10=0.180, blind=0.030; dense-incompressible for device tier | 2026-08-21 |
| `results/fidelity/e29_tier_heterogeneous/locomo_qwen7b_n100.json` | `e29_locomo.py` | qwen7b | a6000 | 100 | LoCoMo: full=0.400 (SANITY PASS delta=0.000), sum80=0.120, sum200=0.120, win10=0.230, blind=0.080 | 2026-08-21 |
| `results/fidelity/e29_tier_heterogeneous/locomo_sum80_qwen3b.json` | `e29_locomo.py` | qwen3b | a6000 | 10 convs | qwen3b sum-80 summary cache for LoCoMo subset | 2026-08-21 |
| `results/fidelity/e29_tier_heterogeneous/locomo_sum200_qwen3b.json` | `e29_locomo.py` | qwen3b | a6000 | 10 convs | qwen3b sum-200 summary cache for LoCoMo subset | 2026-08-21 |
| `results/fidelity/e29_tier_heterogeneous/egoschema_qwen3b_n60.json` | `e29_egoschema.py` | qwen3b | a6000 | 60 | EgoSchema: full=0.450, sum80=0.400, sum200=0.433, win10=0.450, blind=0.300; gist-compressible for device tier | 2026-08-21 |
| `results/fidelity/e29_tier_heterogeneous/egoschema_qwen7b_n60.json` | `e29_egoschema.py` | qwen7b | a6000 | 60 | EgoSchema: full=0.567 (SANITY PASS delta=0.000), sum80=0.433, sum200=0.483, win10=0.500, blind=0.200 | 2026-08-21 |
| `results/fidelity/e29_tier_heterogeneous/egoschema_sum80_qwen3b.json` | `e29_egoschema.py` | qwen3b | a6000 | 60 | qwen3b sum-80 summary cache for EgoSchema subset | 2026-08-21 |
| `results/fidelity/e29_tier_heterogeneous/egoschema_sum200_qwen3b.json` | `e29_egoschema.py` | qwen3b | a6000 | 60 | qwen3b sum-200 summary cache for EgoSchema subset | 2026-08-21 |
| `results/fidelity/e29_tier_heterogeneous/e29_analysis.json` | `e29_analysis.py` | qwen3b+qwen7b | a6000 | — | Bootstrap CIs, paired contrasts, sufficiency table (τ=0.90/0.95), Q(fidelity,workload,model) table | 2026-08-21 |
| `figures/fidelity/e29_q_table.pdf` | `e29_analysis.py` | qwen3b+qwen7b | a6000 | — | Q(fidelity, workload, model) heatmap; sufficiency cells marked per τ threshold | 2026-08-21 |
| `figures/fidelity/e29_substitution.pdf` | `e29_followup.py` | qwen3b+qwen7b | CPU | — | Accuracy by (fidelity, model) with cross-tier substitution brackets; paired bootstrap significance annotations | 2026-08-21 |
| `reports/e29_tier_heterogeneous.md` | `e29_analysis.py` + `e29_followup.py` (follow-up, no new inference) | qwen3b+qwen7b | a6000 | — | Revised: paired substitution tests; absolute sufficiency table (q∈{0.20,0.30,0.40}); corrected sufficiency-disagreement interpretation; fidelity-sensitivity analysis | 2026-08-21 |
