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
| `results/cost/profiles/jetson_orin_qwen3b.json` | `cost_profile.py` | qwen3b | jetson_orin | L∈{1k,4k,8k,16k} × 5 reps | 3B/7B device-tier ratio (same box/stack as E23): cold-prefill 0.475@1k→0.542@16k (rises with L), warm-append 0.59–0.71, peak-mem ~0.42. Replaces E36 A1 (0.43–1.00) → **use 0.48–0.54 (≈0.54 @ ~20k); 1.00 refuted (3B 1.85–2.1× faster at prefill)**. All L feasible (peak 8.16 GB). KV 36,864 B/tok. Also appends 24 qwen3b/jetson_orin rows to `cost_matrix.csv`. | c19f9a4 |

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

## E30 — Capacity Arithmetic (2026-08-21)

Script: `experiments/cost/e30_capacity.py`. CPU only; reads committed cost measurement files.

| file | script | model | device | n | headline | source commit |
|---|---|---|---|---|---|---|
| `results/cost/e30_capacity/memory_capacity.csv` | `e30_capacity.py` | qwen7b/qwen3b | CPU | 3 tiers × 4 fidelities × 4 L-pts | Sessions by memory: sum-80 supports 7,106 sessions on A6000 (L-independent); full supports 8–69 sessions (L-dependent) | 2026-08-21 |
| `results/cost/e30_capacity/accelerator_demand.csv` | `e30_capacity.py` | qwen7b | CPU | 4 fidelities × 4 L-pts × 5 ri | Sessions by accelerator: win-10 supports 32–7,556; sum-80 supports 0–97 | 2026-08-21 |
| `results/cost/e30_capacity/sessions_supported.csv` | `e30_capacity.py` | qwen7b/qwen3b | CPU | 3 tiers × 4 fidelities × 4 L-pts × 5 ri | Combined binding constraint (min of memory, accelerator) with binding label per cell | 2026-08-21 |
| `results/cost/e30_capacity/binding_crossover.csv` | `e30_capacity.py` | qwen7b | CPU | 55 accelerator-bound cells | Cells where accelerator binds before memory; all sum-80/sum-200 rows across all ri | 2026-08-21 |
| `figures/cost/e30_capacity_binding.pdf` | `e30_capacity.py` | qwen7b/qwen3b | CPU | — | Six-panel: (rows) memory-limit, accel-limit at ri=60s; (cols) A6000, 24-GB GPU, Jetson | 2026-08-21 |
| `reports/e30_capacity_arithmetic.md` | `e30_capacity.py` | — | — | — | Parts A–D: memory capacity, accelerator demand sweep, binding crossover, realism check; assumption table; Part D answer | 2026-08-21 |
| `reports/e29_tier_heterogeneous.md` | `e29_analysis.py` + `e29_followup.py` (follow-up, no new inference) | qwen3b+qwen7b | a6000 | — | Revised: paired substitution tests; absolute sufficiency table (q∈{0.20,0.30,0.40}); corrected sufficiency-disagreement interpretation; fidelity-sensitivity analysis | 2026-08-21 |

## E31 — Network Characterization (2026-08-22)

Script: `experiments/cost/e31_network.py`. CPU only; uses downloaded public traces (no GPU, no model inference).
Datasets: Irish 5G driving (uccmisl/5Gdataset, GPL-3.0), herolab indoor RSSI (GitHub, license not stated).
Limitation: driving mobility (not pedestrian); State=I proxy for disconnection; netem requires sudo tc (not run — loopback socket rate-limiting used).

| file | script | model | device | n | headline | source commit |
|---|---|---|---|---|---|---|
| `results/cost/e31_network/reachability_series.csv` | `e31_network.py` | n/a | CPU | 28,551 s × 16 sessions | Irish 5G driving: 83% connected (State=D); 35.4 handovers/session mean | 2026-08-22 |
| `results/cost/e31_network/bandwidth_series.csv` | `e31_network.py` | n/a | CPU | 23,102 D-state rows | Irish 5G driving DL_bitrate (kbps→Mbps): p10=0.9, p50=9.6, p90=102.9 Mbps | 2026-08-22 |
| `results/cost/e31_network/predictability_metrics.csv` | `e31_network.py` | n/a | CPU | 16 sessions | Persistence 0.75 at H=10,30,60s; P(D→D)=0.85; BW autocorr: 0.39→0.08 (H=10→60s) | 2026-08-22 |
| `results/cost/e31_network/transfer_latency.csv` | `e31_network.py` | n/a | CPU | 4 reps × 3 profiles | At p50 BW: sum-80=3.8s, win-10=19.2s, full-8k=392s(theoretical); KV transfer infeasible at median BW for full | 2026-08-22 |
| `results/cost/e31_network/e31_summary.json` | `e31_network.py` | n/a | CPU | — | Summary JSON with BW profiles, connectivity fraction, predictability metrics | 2026-08-22 |
| `figures/cost/e31_reachability.pdf` | `e31_network.py` | n/a | CPU | — | Three panels: reachability time series, handover histogram, DL_bitrate distribution | 2026-08-22 |
| `figures/cost/e31_predictability.pdf` | `e31_network.py` | n/a | CPU | — | Two panels: persistence+BW autocorr at H={10,30,60}s; Markov matrix at H=60s | 2026-08-22 |
| `reports/e31_network_characterization.md` | — | — | — | — | Parts A–D: dataset selection, reachability/BW series, predictability, transfer latency; prefetch decision implications | 2026-08-22 |

## E32 — Staleness Cost (2026-08-22)

Script: `experiments/fidelity/e32_staleness.py`. Modes: quality (HF), latency (vLLM V0, VLLM_USE_V1=0), analysis (CPU).
Workloads: LoCoMo n=100 (primary staleness), EgoSchema n=60 (truncation control only). Model: qwen7b.
N sweep: {0,1,5,10,20,50,100} turns for LoCoMo; {0,1,5} for EgoSchema.

| file | script | model | device | n | headline | source commit |
|---|---|---|---|---|---|---|
| `results/fidelity/e32_staleness/locomo_quality_qwen7b.json` | `e32_staleness.py --mode quality` | qwen7b | a6000 | 100 q × 7 N | Sanity N=0: 0/100 disagree vs E29. Quality flat across N for all fidelities within noise; outside-evidence questions drop to 0.13–0.28 accuracy at N=50–100 | 2026-08-22 |
| `results/fidelity/e32_staleness/egoschema_quality_qwen7b.json` | `e32_staleness.py --mode quality` | qwen7b | a6000 | 60 q × 3 N | Truncation control. Sanity N=0: 0/60 disagree. Gist-compressible; N=1,5 negligible effect | 2026-08-22 |
| `results/fidelity/e32_staleness/locomo_latency_qwen7b.json` | `e32_staleness.py --mode latency` | qwen7b | a6000 | 10 conv × 6 N × 4 variants | full/win10 warm-append: 59–89 ms (all budgets met); sum200 recursive: 4.6–5.1 s (background only); sum200 full-regen: 8.8 s (no budget) | 2026-08-22 |
| `results/fidelity/e32_staleness/analysis_qwen7b.json` | `e32_staleness.py --mode analysis` | — | CPU | — | Tradeoff table: (fidelity, N) → acc + latency + TTFT budget verdicts | 2026-08-22 |
| `results/fidelity/e32_staleness/caches/locomo_sum200_stale.json` | `e32_staleness.py --mode quality` | qwen7b | a6000 | 10 conv × 6 N | Stale sum200 summaries for N∈{1,5,10,20,50,100} | 2026-08-22 |

## E34 — Maintenance Semantics + Corrected Catch-up Latency (2026-08-23)

Script: `experiments/cost/e34_maintenance_semantics.py`. Model: qwen7b. Device: A6000 (GPU 1). vLLM 0.8.5 V1, enforce\_eager=True, YaRN for L≥32k.
Part A: update semantics per object under WARM (prefix\_caching=True) and COLD (prefix\_caching=False). Part B: corrected catch-up latency (replaces E32 Part B) — 10 LoCoMo convs × N∈{1,5,10,20,50,100} × fidelity∈{full,win10,sum200} × {WARM,COLD} × 5 reps. Part C: CPU-only analysis.
Three implementation bugs fixed: CUDA graph deadlock (enforce\_eager=True), vLLM V1 subprocess OOM (explicit shutdown), slide WARM pre-caching (removed new\_text warm-up).

| file | script | model | device | n | headline | source commit |
|---|---|---|---|---|---|---|
| `results/cost/e34_maintenance_semantics/part_a_full.json` | `e34_maintenance_semantics.py --part A` | qwen7b | a6000 | 12 L×k pairs × 5 reps × 2 conditions | Full WARM/COLD: 30–132× ratio across L=8k–65k; WARM is cache-hit fast; COLD at committed prefill rate | 4da0eb9d |
| `results/cost/e34_maintenance_semantics/part_a_win10.json` | `e34_maintenance_semantics.py --part A2` | qwen7b | a6000 | 10 LoCoMo convs × {growth,slide} × 2 conditions × 5 reps | Growth WARM=36ms (27× vs COLD=962ms); Slide COLD=0.975s (reliable); Slide WARM=vLLM V1 block-reuse artifact (documented, not used) | 4da0eb9d |
| `results/cost/e34_maintenance_semantics/part_b_catchup.json` | `e34_maintenance_semantics.py --part B` | qwen7b | a6000 | 10 convs × 6 N × 3 fidelities × 2 conditions × 5 reps = 1800 measurements | COLD N-invariant: full=3.62s, win10=1.045s, sum200=0.037s (all within 2× of committed 5,984 tok/s). WARM cache-hit: 25–65ms all fidelities all N | 4da0eb9d |
| `results/cost/e34_maintenance_semantics/part_c_analysis.json` | `e34_maintenance_semantics.py --part C` | — | CPU | — | Win10 amortized=652ms (65.7% slides); sum200 restore=32ms but update=9,565ms; full COLD 3,620ms fails interactive budget | 4da0eb9d |
| `results/cost/e34_maintenance_semantics/e34_summary.json` | `e34_maintenance_semantics.py` | — | CPU | — | Summary metadata | 4da0eb9d |
| `reports/e34_maintenance_semantics.md` | — | — | — | — | Full 3-part report with 6-check consistency protocol | 2026-08-23 |
| `figures/fidelity/e32_staleness_quality.pdf` | `e32_staleness.py --mode analysis` | — | CPU | — | Three panels: accuracy vs N for all/ev-inside/ev-outside splits per fidelity | 2026-08-22 |
| `figures/fidelity/e32_staleness_latency.pdf` | `e32_staleness.py --mode analysis` | — | CPU | — | Catch-up latency vs N per fidelity/variant; TTFT budget reference lines | 2026-08-22 |
| `reports/e32_staleness_cost.md` | — | — | — | — | Parts A–C + synthesis: staleness is a latency problem for sum200, not a quality problem for any fidelity at N≤20; quality threshold at N≈50 (~2 sessions) | 2026-08-22 |

## E31b — Network Characterization Corrected (2026-08-23)

Script: `experiments/cost/e31b_network.py`. CPU-only. Supersedes E31 Parts C and D.
Corrected signals: cell_id=-1 (no-cell state) for Irish 5G; RSSI threshold sweep for herolab.
Lumos5G + CRAWDAD not obtained (IEEE DataPort registration required; deviation documented).

| file | script | model | device | n | headline | source commit |
|---|---|---|---|---|---|---|
| `results/cost/e31b_network/e31b_summary.json` | `e31b_network.py` | none | CPU | 28,551 Irish 5G + 16,562 herolab | All metrics; corrected reachability, RSSI thresholds, predictability, text payload table | 2026-08-23 |
| `results/cost/e31b_network/irish5g_corrected_reachability.csv` | `e31b_network.py` | — | CPU | 16 sessions | Per-session: duration, n_real_handovers, no_cell_s | 2026-08-23 |
| `results/cost/e31b_network/herolab_rssi_thresholds.csv` | `e31b_network.py` | — | CPU | 16,562 samples | Fraction below −65/−70/−75/−80/−85/−90 dBm | 2026-08-23 |
| `results/cost/e31b_network/predictability_corrected.csv` | `e31b_network.py` | — | CPU | 28,551 timesteps | Persistence + Markov metrics at H={10,30,60}s × 2 corrected signals | 2026-08-23 |
| `results/cost/e31b_network/text_payload_transfer.csv` | `e31b_network.py` | — | CPU | — | Transfer time at p10/p50/p90 BW for text payloads (4B/tok) vs cold prefill; ratio 43–528× | 2026-08-23 |
| `results/cost/e31b_network/kv_appendix.csv` | `e31b_network.py` | — | CPU | — | KV transfer times for same-model migration (appendix only; not applicable in our setting) | 2026-08-23 |
| `figures/cost/e31b_reachability_by_environment.pdf` | `e31b_network.py` | — | CPU | — | Three panels: CellID pie (85.6% reachable), duration-filter pie (97.6% reachable), herolab RSSI bar (<1% below −75 dBm) | 2026-08-23 |
| `figures/cost/e31b_predictability.pdf` | `e31b_network.py` | — | CPU | — | Two panels: persistence accuracy by signal+H; text transfer vs cold prefill log-bar chart | 2026-08-23 |
| `reports/e31b_network_characterization.md` | — | — | — | — | Parts 1–6: acquisition failures, corrected Irish 5G, herolab RSSI, premise check, predictability, text payload table; key finding: text transfer 43–528× faster than cold prefill at p50 BW | 2026-08-23 |
| `results/audit/definitions.csv` | `e33a` (analysis only) | — | CPU | — | Machine-readable definition table for all named objects (win-10, sum-80, sum-200, full, blind, turn, session, reachable, stale-by-N, cold-prefill, warm-append, refresh, materialize); flags definition conflicts and superseded values | 2026-08-23 |
| `results/audit/evidence_ledger.csv` | `e33a` (analysis only) | — | CPU | — | Machine-readable evidence ledger: quantity, value, source, how obtained, conditions, cross-check, status (VERIFIED/SUPERSEDED/DISPUTED/INVALID/ESTIMATED), claim linkage | 2026-08-23 |
| `reports/e33a_definition_audit_and_ledger.md` | — | — | — | — | Three-part audit: (1) definition conflicts for all named objects including win-10 18× discrepancy and corrected E30 capacity; (2) evidence ledger with status codes; (3) supported vs disputed claims and priority rerun list | 2026-08-23 |

## E35 (E34b) — Corrected WARM Catch-up Latency and Maintenance Ordering (2026-08-23)

Script: `experiments/cost/e34b_catchup.py`. A6000, vLLM 0.8.5 V1. Supersedes E34 Parts B and C.
Fixes: (1) warm-up bug in E34 Part B (current_text pre-cached); (2) COLD relabeled as restore; (3) full maintenance cost corrected to warm-append (66ms, E26).
Key findings: full WARM 67ms(N=1)→681ms(N=100); win10 intra-session 41–77ms, inter-session ~1031ms (sharp jump at N~22 turns); sum200 TTFT 25ms; sum200 recursive 5.8–6.2s; full regen distribution 7.8–10.3s (E32 constant artifact confirmed).

| file | script | model | device | n | headline | source commit |
|---|---|---|---|---|---|---|
| `results/cost/e34b_catchup/part1_warm_catchup.json` | `e34b_catchup.py` | qwen7b | a6000 | 10 convs × 6N × 2 fidelities × 2 reps | Full WARM: 67ms(N=1)→681ms(N=100); win10 bimodal: 41-77ms intra-session, ~1031ms inter-session with jump at N~22 turns | 2026-08-23 |
| `results/cost/e34b_catchup/part2_sum200.json` | `e34b_catchup.py` | qwen7b | a6000 | 10 convs × 6N × 2 reps per variant | sum200 TTFT 25ms (flat); recursive 5.8-6.2s (decode-dominated); full regen 7.8-10.3s distribution (E32 constant artifact confirmed) | 2026-08-23 |
| `results/cost/e34b_catchup/part3_maintenance.json` | `e34b_catchup.py` | — | CPU | — | Corrected ordering: sum200-restore(32ms) < full-warm-append(66ms) < win10-amortized(653ms) < sum200-recursive(5822ms) | 2026-08-23 |
| `reports/e34b_corrected_catchup.md` | — | — | — | — | Full report with 6-check consistency protocol; corrects E34 Parts B and C defects | 2026-08-23 |

## E36 — Maintenance-Aware Fleet Admission and Representation Policy (2026-08-23)

Script: `experiments/orchestration/e36_fleet.py`. CPU (pure simulation, no GPU). flash.
Stage 0: corrected headroom gate (LoCoMo=warm-append, EgoSchema=cold-restore-per-query).
Stage 1: 3,024 runs (7 policies × 2 workloads × 3 q-SLOs × fleet configs × 2 A1 bounds × 3 seeds).
Stage 2: per-cell policy ranking; K2 check.
K2 FAIL: 3/36 cells (locomo/1000ms/s=0.43) gap=+0.7pp vs ≥5pp threshold.
K2 passes at s=1.00 (+14.2pp). A1 assumption pending Jetson qwen3b measurement.

| file | script | model | device | n | headline | source commit |
|---|---|---|---|---|---|---|
| `results/orchestration/e36_fleet/stage0_headroom.json` | `e36_fleet.py` | qwen3b (Jetson, A1) + qwen7b (edge) | CPU sim | 18 cells × 2 A1 bounds | K1 PASS: 22% non-discriminating; LoCoMo warm-append failure: 87.3%/97.1% at 300ms, 12.1%/70.2% at 1000ms (s=0.43/1.00) | 2026-08-23 |
| `results/orchestration/e36_fleet/stage1_sweep.json` | `e36_fleet.py` | qwen3b (device) + qwen7b (edge) | CPU sim | 3,024 runs | Policy sweep: edge policies +10–57pp vs device_only in most cells | 2026-08-23 |
| `results/orchestration/e36_fleet/stage2_analysis.json` | `e36_fleet.py` | — | CPU sim | 36 cells | K2 FAIL: 3 cells locomo/1000ms/s=0.43 (+0.7pp); K2 PASS at s=1.00 (+14.2pp) | 2026-08-23 |
| `reports/e36_fleet_policy.md` | — | — | — | — | Full report with 6-check consistency protocol and K2 violation analysis | 2026-08-23 |

## E37b — A1 Ratio Resolution + E36 K2 Consequence Analysis (2026-08-24)

Analysis only. Inputs: committed E37 (jetson_orin_qwen3b.json) and E23 (jetson_orin_qwen7b.json).
Key finding: incr_warm ratio 0.593@1k→0.705@16k (median 0.684 across LoCoMo turns).
Device_only fails 46.5% of LoCoMo 1s queries at measured ratio.
K2 PASSES at measured device speed (gap ≈11pp). E36's K2 violation was a lower-bound artifact.

| file | script | model | device | n | headline | source commit |
|---|---|---|---|---|---|---|
| `results/cost/a1_ratio_table.csv` | analysis (no script) | qwen3b vs qwen7b | jetson_orin | 4 L-points × 7 ops | incr_warm ratio 0.593–0.705 (rises with L); full_restore 0.475–0.542; summary restore ~0.587 (flat) | 2026-08-24 |
| `reports/phase1_cost_profiling.md §Measured A1 ratio` | — | — | — | — | K2 consequence: 46.5% device failure at 1s budget; K2 PASSES at measured ratio; device sum-update infeasible (11.9–21.2s) | 2026-08-24 |

## E36b — Fleet Policy Simulation with Measured A1 Ratio (2026-08-24)

E36 re-run using measured 3B/7B incr_warm ratio (0.593–0.705, L-dependent, E37).
K1 PASS (22% non-discriminating). K2 PASS all 18 cells (min +6.8pp, max +57.0pp).
lifecycle_aware co-ranks with edge_full_lru at all LoCoMo cells.

| file | script | model | device | n | headline | source commit |
|---|---|---|---|---|---|---|
| `results/orchestration/e36b_fleet/stage0_headroom.json` | `e36b_fleet.py` (rewrite) | qwen3b (measured A1) + qwen7b (edge) | CPU sim | 18 cells | K1 PASS 22% non-discriminating; device 46.5% fail at 1s/LoCoMo | 2026-08-24 |
| `results/orchestration/e36b_fleet/stage1_sweep.json` | `e36b_fleet.py` (rewrite) | qwen3b + qwen7b | CPU sim | 2520 runs | 7-policy corrected sweep; admissibility constraint quality model | 2026-08-24 |
| `results/orchestration/e36b_fleet/stage2_analysis.json` | `e36b_fleet.py` (rewrite) | — | CPU sim | 18 cells | Kill (b)/(c)/(d) fire; maintenance_aware≡always_full; fp_ranked beats maint at egoschema/300ms by 81.5pp | 2026-08-24 |
| `results/orchestration/e36b_fleet/binding_diagnostic.json` | `e36b_fleet.py` (rewrite) | — | CPU sim | 35 rows (7 pol × 5 fleet) | Accel never binds (kill d); KV-memory-bound fraction by policy/fleet | 2026-08-24 |
| `reports/e36b_fleet_policy.md` | — | — | — | — | Full report with 6-check consistency protocol (rewrite, supersedes prior e36b) | 2026-08-24 |

## E36c — Fleet Policy with Fixed KV Capacity and Corrected Maintenance-Aware (2026-08-24)

E36b corrected again: KV capacity fixed (not fleet-scaled); maintenance_aware redesigned as fleet-level greedy knapsack.
Kill conditions (b)/(c) still fire; fleet system claim falsified. Accel binds at ti=5 s (kill d does not fire).

| file | script | model | device | n | headline | source commit |
|---|---|---|---|---|---|---|
| `results/orchestration/e36c_fleet/stage0_headroom.json` | `e36c_fleet.py` | qwen3b (E37b ratio) + qwen7b (E29) | CPU sim | 18 cells | K1 PASS 22% non-discriminating | 2026-08-24 |
| `results/orchestration/e36c_fleet/stage1_sweep.json` | `e36c_fleet.py` | qwen3b + qwen7b | CPU sim | 8,064 runs | fixed-KV sweep; fleet-level knapsack; turn_interval sweep | 2026-08-24 |
| `results/orchestration/e36c_fleet/stage2_analysis.json` | `e36c_fleet.py` | — | CPU sim | 18 cells | Kill (b)/(c) fire; fleet claim falsified; ma within 5pp of fp_ranked in all 18 cells | 2026-08-24 |
| `results/orchestration/e36c_fleet/binding_diagnostic.json` | `e36c_fleet.py` | — | CPU sim | rows per (policy, fleet, kv_cap, turn_interval) | Accel binds at ti=5s (maint_aware only, up to 4.3%); kill (d) no-fire | 2026-08-24 |
| `reports/e36c_fleet_policy.md` | — | — | — | — | Full report with 6-check consistency protocol | 2026-08-24 |
| `figures/orchestration/e36c_gap_vs_fleetsize.pdf` | `plots/orchestration/e36c_figures.py` | — | — | — | both_met vs fleet size (kv=9 GiB, ti=30 s) | 2026-08-24 |
| `figures/orchestration/e36c_binding_resource.pdf` | `plots/orchestration/e36c_figures.py` | — | — | — | Binding resource: KV vs accel per policy/kv_cap/turn_interval | 2026-08-24 |
| `figures/orchestration/e36c_kv_occupancy.pdf` | `plots/orchestration/e36c_figures.py` | — | — | — | KV p50/max occupancy vs kv_cap | 2026-08-24 |

## E36e — Fleet Capacity Relationship: Proactive Maintenance Model (2026-08-24)

Script: `experiments/orchestration/e36e_fleet.py`. CPU (no GPU). Proactive model: maintenance consumed from epoch budget, never on serving critical path. Part A: analytic P1–P4. Part A2: P1b non-monotone, batching sensitivity, refresh policy axis. Part B: 8,064 conditions × 30 epochs.

| file | script | model | device | n | headline | source commit |
|---|---|---|---|---|---|---|
| `results/orchestration/e36e_fleet/e36e_part_a.json` | `e36e_fleet.py --part A` | — (analytic) | CPU | — | P1 PASS: memory ordering inverted vs accelerator ordering. P2 PASS: win10 crossover ti≈17s. P3 PASS: fp_ranked selects 6 sessions, maint_ranked selects 8 (delta=2, ti=5s, kv=9GiB). P4 PASS: delta collapses with maint=0. | 2026-08-24 |
| `results/orchestration/e36e_fleet/e36e_part_a2.json` | `e36e_fleet.py --part A2` | — (analytic) | CPU | — | P1b PASS: win10 maximizes N_eff at ti≥15s (non-monotone). Batching: 3-way collapses at B=4 ti=60s; 2-way (LoCoMo) immune to batching. Refresh: 3-way collapses at periodic-5; 2-way immune. | 2026-08-24 |
| `results/orchestration/e36e_fleet/e36e_part_b.json` | `e36e_fleet.py --part B` | — (simulator) | CPU | 8,064 runs × 30 epochs | Fleet simulation with steady-state initialization (session_idx uniform random). Mechanism activated: both_met drops from 1.000 (bug) to 0.57–0.90 range. | 2026-08-24 |
| `results/orchestration/e36e_fleet/e36e_part_b_analysis.json` | `e36e_fleet.py --part B` | — | CPU | 288 cells | S1 PASS (regime-dependent). S2 FAIL (2/16 cells, kv=18GiB ti≥30s, regret +12.8–13.5pp). S3 PASS (+7–26pp, 4/4 kv cells at ti=5s). S4: 40/288 activating. | 2026-08-24 |
| `results/orchestration/e36e_fleet/e36e_part_b_init_report.json` | `e36e_fleet.py --part B` | — | CPU | n=50, seed=42 | Initialization state: epoch 0 L_mean=9520 tok, 16/50 robots above 12K TTFT threshold. Final epoch: L_mean=10692 tok, 18/50 above threshold. Session-end behavior: clamped at n_sess-1, no restart, no churn. | 2026-08-24 |
| `results/orchestration/e36e_fleet/e36e_part_b_null_diagnosis.md` | — | — | CPU | — | INCONCLUSIVE classification of first Part B run (session_idx=0 bug: context_L=382 tok, device TTFT=344ms, mechanism absent). Fix: uniform random session_idx. | 2026-08-24 |
| `figures/orchestration/e36e_sessions_supported.pdf` | `e36e_fleet.py` | — | CPU | — | Sessions supported vs ti for full/win10/sum200 with memory ceiling lines (kv=9GiB) | 2026-08-24 |
| `figures/orchestration/e36e_effective_capacity_vs_turnrate.pdf` | `e36e_fleet.py` | — | CPU | — | N_eff = min(N_mem, N_accel) by representation; non-monotone win10 argmax; batching sensitivity for sum200 | 2026-08-24 |
| `figures/orchestration/e36e_policy_gap.pdf` | `e36e_fleet.py` | — | CPU | — | both_met by policy × ti (n=50, kv=9GiB, locomo, q=0.20, ttft=1000ms); maint_aware vs fp_ranked gap | 2026-08-24 |
| `figures/orchestration/e36e_s3_gap_heatmap.pdf` | `e36e_fleet.py` | — | CPU | — | S3 gap (maint_aware − fp_ranked) vs kv_cap at ti=5s | 2026-08-24 |
| `reports/e36e_fleet_capacity.md` | — | — | — | — | Full report: mechanism verification (5 steps), 6-check consistency, Part A/A2/B results, S2 structural diagnosis, assumption table, kill condition verdicts | 2026-08-24 |

## E36f — N_eff-ranked Policy: S2 Re-verification (2026-08-24)

Script: `experiments/orchestration/e36f_neff.py`. CPU (no GPU). Adds neff_ranked policy (argmax N_eff = min(N_mem, N_accel)) to E36e's fleet simulation.
All constants identical to E36e; no new measurements.
S2: FAIL in 3 cells (kv=4.5,9,36 GiB, ti=5s; regret +6.8–9.9pp) — new ti=5s failure from dynamic-L mixed-fleet effect; E36e's kv=18GiB ti≥30s cells now PASS.
S3: PASS at all kv_caps (neff_ranked ≥ fp_ranked at ti=5s, gap +0.2–16.4pp).
Distinguishability: 0/16 cells selection-distinguishable; 11/16 outcome-distinguishable. Honest activation: 11/16.
Design rule: choose full at ti≤6s (N_accel(win10)=6 < N_eff(full)≥7); choose win10 at ti>crossover.

| file | script | model | device | n | headline | source commit |
|---|---|---|---|---|---|---|
| `results/orchestration/e36f_neff/e36f_sweep.json` | `e36f_neff.py` | — (simulator) | CPU | 1152 runs (6 pol × 4 kv × 4 ti × 2 wl × 2 q × 3 seeds) × 30 epochs | Full policy sweep with neff_ranked added; both_met per cell per seed | 2026-08-24 |
| `results/orchestration/e36f_neff/e36f_analysis.json` | `e36f_neff.py` | — | CPU | 16–64 cells (analyzed) | S2/S3 tables, distinguishability, activation region (honest 11/16) | 2026-08-24 |
| `results/orchestration/e36f_neff/e36f_analysis_log.txt` | `e36f_neff.py` | — | CPU | — | Full text output of analysis: regime trace, circularity defense, 6 required items | 2026-08-24 |
| `figures/orchestration/e36f_selection_vs_turnrate.pdf` | `e36f_neff.py` | — | CPU | — | 4-panel: selection fraction (full/win10) + both_met vs ti, per kv_cap; crossover marked | 2026-08-24 |
| `reports/e36f_neff_policy.md` | — | — | — | — | Full report: mechanism verification (5 steps), 6-check consistency, S2/S3 re-verification, distinguishability, regime trace, circularity defense, activation region (honest denominator) | 2026-08-24 |

## E36h — Two-part Rule Ablation (2026-08-25)

Script: `experiments/orchestration/e36h_ablation.py`. CPU (no GPU). Adds always_full_mb, always_window_mb, footprint_ranked_mb baselines; renames oracle → greedy_upper. 12 policies, 2,304 runs.
Decomposition: best_fixed (no MB, no N_eff) → best_fixed_mb (MB only) → neff_marginal (both parts).
admission_gain = best_fixed_mb − best_fixed; representation_gain = neff_marginal − best_fixed_mb.
Mean admission_gain = +9.62 pp; mean representation_gain = +0.48 pp. rep_gain positive in 2/16 cells; zero in 14/16.

| file | script | model | device | n | headline | source commit |
|---|---|---|---|---|---|---|
| `results/orchestration/e36h_ablation/e36h_sweep.json` | `e36h_ablation.py` | — (simulator) | CPU | 2,304 runs × 30 epochs | Full policy sweep; 12 policies including always_full_mb, always_window_mb, footprint_ranked_mb, greedy_upper | 2026-08-25 |
| `results/orchestration/e36h_ablation/e36h_fidelity_mix.json` | `e36h_ablation.py` | — | CPU | 48 (kv,ti) cells × 3 seeds | Per-epoch fidelity counts (full/win10 fraction) for neff_marginal, locomo q=0.20 | 2026-08-25 |
| `results/orchestration/e36h_ablation/e36h_analysis.json` | `e36h_ablation.py` | — | CPU | 5 analysis sections | Decomp table, representation_gain regions, fidelity-mix diagnostic, S3 corrected, greedy_upper comparison | 2026-08-25 |
| `results/orchestration/e36h_ablation/e36h_analysis_log.txt` | `e36h_ablation.py` | — | CPU | — | Full text output of all analysis sections | 2026-08-25 |
| `figures/orchestration/e36h_gain_decomposition.pdf` | `e36h_ablation.py` | — | CPU | — | 4-panel stacked bar: admission_gain (blue) and representation_gain (orange) per turn interval per kv_cap | 2026-08-25 |
| `reports/e36h_ablation.md` | — | — | — | — | Full report: mechanism verification (5 steps), 6-check consistency, 5 required items (decomp table, rep_gain regions, fidelity-mix diagnostic, S3 corrected, greedy_upper renaming) | 2026-08-25 |

## E36g — Marginal-benefit Admission Ordering (2026-08-24)

Script: `experiments/orchestration/e36g_marginal.py`. CPU (no GPU). Adds neff_marginal (two-part rule) and oracle policies to E36f's fleet simulation (8 total).
All constants identical to E36e/E36f; no new measurements. DEVICE_TTFT_1000MS_THRESHOLD = 11,800 tokens (analytic from E23 × E37).
S2: PASS (0/16 cells for neff_marginal); S3: PASS (+0.159–0.360 pp vs fp_ranked at ti=5s, all kv_caps). Distinguishable 13/16 cells.
E36f mixed-fidelity diagnosis superseded: actual cause = N_eff ordering admits small-L (zero marginal benefit) robots first. Two-part rule separates representation selection (Part 1 = argmax N_eff) from admission ordering (Part 2 = marginal benefit DESC).

| file | script | model | device | n | headline | source commit |
|---|---|---|---|---|---|---|
| `results/orchestration/e36g_marginal/e36g_sweep.json` | `e36g_marginal.py` | — (simulator) | CPU | 1,536 runs (8 pol × 4 kv × 4 ti × 2 wl × 2 q × 3 seeds) × 30 epochs | Full policy sweep with neff_marginal and oracle added; both_met per cell per seed | 2026-08-24 |
| `results/orchestration/e36g_marginal/e36g_diag_detail.json` | `e36g_marginal.py` | — | CPU | 3 cells × 4 policies × epoch 0 | Diagnosis: context_L, marginal_benefit per admitted robot at kv=4.5/9/36 GiB, ti=5s | 2026-08-24 |
| `results/orchestration/e36g_marginal/e36g_analysis.json` | `e36g_marginal.py` | — | CPU | 32–128 cells (analyzed) | S2/S3 tables for neff_marginal alongside neff_ranked; distinguishability; oracle comparison | 2026-08-24 |
| `results/orchestration/e36g_marginal/e36g_analysis_log.txt` | `e36g_marginal.py` | — | CPU | — | Full text output of analysis: S2/S3 tables, diagnosis, distinguishability, oracle cell | 2026-08-24 |
| `figures/orchestration/e36g_admitted_by_context_length.pdf` | `e36g_marginal.py` | — | CPU | — | 3-panel histogram: context_L distribution of admitted robots at ti=5s per policy (kv=4.5/9/36 GiB); diagnosis figure | 2026-08-24 |
| `figures/orchestration/e36g_policy_comparison.pdf` | `e36g_marginal.py` | — | CPU | — | 4-panel: both_met vs ti per kv_cap, all 8 policies; neff_marginal vs neff_ranked gap visible at ti=5s | 2026-08-24 |
| `reports/e36g_marginal_admission.md` | — | — | — | — | Full report: mechanism verification (5 steps), 6-check consistency, 5 required items (S2 alongside neff_ranked, diagnosis check, S3, distinguishability, oracle comparison), two-part rule summary | 2026-08-24 |

## E36d — Fleet Policy with Maintenance Charged to Accelerator via FIFO Queue (2026-08-24)

Script: `experiments/orchestration/e36d_fleet.py`. CPU (no GPU). Supersedes E36c.
Two defects fixed: (1) refresh_ms now charges full=66ms, win10=36/1031ms, sum200=5822ms; (2) FIFO queue model enforces accel budget for all policies. Serve=warm-decode-only (double-count removed).
Realized slide fraction: 63.0% (committed 65.7%). Mechanism verification PASS (all 4 steps). 6-check consistency PASS.

| file | script | model | device | n | headline | source commit |
|---|---|---|---|---|---|---|
| `results/orchestration/e36d_fleet/e36d_stage0_headroom.json` | `e36d_fleet.py` | qwen3b (E37b) + qwen7b (E29) | CPU sim | 18 cells | K1 PASS: admissibility gate; LoCoMo q=0.20 admits full+win10; q≥0.30 admits full only | 2026-08-24 |
| `results/orchestration/e36d_fleet/e36d_stage1_sweep.json` | `e36d_fleet.py` | qwen3b + qwen7b | CPU sim | 8,064 runs | Full policy sweep; FIFO queue TTFT model; maintenance charged to all policies | 2026-08-24 |
| `results/orchestration/e36d_fleet/e36d_stage2_analysis.json` | `e36d_fleet.py` | — | CPU sim | 72 cells | maint_aware +12.6–17.8pp vs fp_ranked (LoCoMo q=0.20 @ 1000ms); 0pp EgoSchema; 0pp q≥0.30 | 2026-08-24 |
| `results/orchestration/e36d_fleet/e36d_binding_diagnostic.json` | `e36d_fleet.py` | — | CPU sim | n=50, kv=9GiB diagnostic | maint_aware: kv_bd=36.0%, ac_bd=0%; fp_ranked: kv_bd=39.9%, ac_bd=15.7% at ti=5s | 2026-08-24 |
| `results/orchestration/e36d_fleet/mechanism_verification.txt` | `e36d_mechanism_verification.py` | — | CPU | Steps 1–4 | All steps PASS; negative control: maint=real gap=+11; maint=0 gap=−1 (reversal confirms mechanism) | 2026-08-24 |
| `reports/e36d_fleet_policy.md` | — | — | — | — | Full report: mechanism verification, 6-check consistency, main results table, kill conditions, binding diagnostic, two-path mechanism interpretation | 2026-08-24 |

## E38 — Slide Figures (2026-08-25)

Script: `experiments/figures/e38_slide_figures.py`. CPU (no GPU). Plotting only; all values from committed result files. Three advisor-presentation figures at slide legibility (≥14pt labels, ≥16pt titles). Both PDF and PNG for each figure.

| file | script | model | device | n | headline | source commit |
|---|---|---|---|---|---|---|
| `figures/slides/e38_fig1_maintenance_cost.{pdf,png}` | `e38_slide_figures.py` | — | CPU | analytic | Horizontal bar (log x): full=66ms, win10_growth=36ms, win10_amortized=653ms (E34), sum200_recursive=5822ms (E35). vLLM 1.10–1.17× faster cold; 1.59–2.55× faster warm-append (E26). | 2026-08-25 |
| `figures/slides/e38_fig2_inversion.{pdf,png}` | `e38_slide_figures.py` | — | CPU | analytic | Two-panel: KV footprint (sum200=9.2MB, win10=417MB, full=1.15GB) vs maintenance (sum200=5822ms, win10=653ms, full=66ms). Ascending footprint = descending maintenance. | 2026-08-25 |
| `figures/slides/e38_fig3_effective_capacity.{pdf,png}` | `e38_slide_figures.py` | — | CPU | analytic | N_eff=min(N_mem,N_accel) vs ti (1–65s) at kv=9GiB: full=8 (always mem-bound), win10 rises 6→23 (crossover at ti≈17.2s), sum200 rises 0→10. Dashed=accel limit; dotted=mem limit; solid=N_eff. | 2026-08-25 |
| `reports/e38_slide_figures.md` | — | — | — | — | Full provenance report: every plotted value with source file, two flagged discrepancies (win10 amortized 653 vs 689.7 ms; sum200 KV 9.2 vs 11.5 MB), 6-check consistency protocol | 2026-08-25 |

## Study A — Scene Content Cost (2026-08-30)

Script: `experiments/vision/study_a_scene_content.py`. A6000 (cuda:1), qwenvl7b (Qwen2.5-VL-7B-Instruct), bfloat16. 12 images at 560×560. N=3 reps + warmup + repeat-control. Cross-model check: qwenvl3b token count only.
Key finding: vision token count, KV bytes, and output token count are all content-independent at fixed pixel dimensions. Prefill latency 145–148 ms (run-order confounded, cannot attribute spread to content).

| file | script | model | device | n | headline | source commit |
|---|---|---|---|---|---|---|
| `results/vision/study_a/study_a_results.json` | `study_a_scene_content.py` | qwenvl7b + qwenvl3b (cross-model) | a6000 (cuda:1) | 12 images × 3 reps; 3 repeat-control reps | All 12 images → 400 vision tokens (both models). KV=24.9 MB, ratio=1.000. Output=2 tok uniform. Prefill 145–148 ms (2.83 ms spread, run-order confounded). H1 CONFIRMED; H2 falsified. | 2026-08-30 |
| `results/vision/study_a/study_a_trials.csv` | `study_a_scene_content.py` | qwenvl7b | a6000 | per-trial raw values | Per-image per-rep: vision_tokens, prefill_ms, kv_bytes_measured, n_generated, kv_ratio | 2026-08-30 |
| `results/vision/study_a/img_*.png` (12 files) | `study_a_scene_content.py` | — | — | — | 12 test images (9 synthetic + 3 natural photos resized to 560×560) | 2026-08-30 |
| `reports/study_a_scene_content.md` | — | — | — | — | Full report: code inspection finding, raw measurements, 5 sanity checks, what can/cannot be inferred | 2026-08-30 |

## Study B — Vision KV State Reduction (2026-08-30)

Script: `experiments/vision/study_b_vision_kv.py`. A6000 (cuda:1), qwenvl7b (Qwen2.5-VL-7B-Instruct), bfloat16.
Three conditions: full retention (all N frames), windowed (k=3 most recent), summary (real generation call per frame, text context for query).
N sweep: {1, 3, 6, 12, 24, 36, 48}. N=2 reps per (N, condition). KV per-token cost: 57,344 B/token (identical to text, SC4 ratio=1.000).
Key finding: cost ordering differs from text case. Vision window (377 ms constant) << full (6,332 ms at N=48) << summary construction (27,854 ms at N=48). Text ordering is full < window < summary (warm-append dominates text). H4 confirmed for ordering/magnitudes; H3 confirmed only for per-token KV byte cost.

| file | script | model | device | n | headline | source commit |
|---|---|---|---|---|---|---|
| `results/vision/study_b/study_b_results.json` | `study_b_vision_kv.py` | qwenvl7b | a6000 (cuda:1) | 7 N-points × 3 conditions × 2 reps | Full: KV 24.9 MB→1,108 MB linear; construction 207→6,332 ms. Window k=3: KV=71 MB constant; construction 377 ms flat (N≥k). Summary: construction 777→27,854 ms growing; query TTFT 29→177 ms (text-only context). All SC4 ratios=1.000. | 2026-08-30 |
| `results/vision/study_b/study_b_trials.csv` | `study_b_vision_kv.py` | qwenvl7b | a6000 | per-trial raw values | Per-(N,condition,rep): state_construction_ms, query_ttft_ms, kv_bytes_measured, peak_mem_bytes, n_generated, kv_ratio | 2026-08-30 |
| `reports/study_b_vision_kv.md` | — | — | — | — | Full report: conditions, N sweep, raw measurement tables, 4 sanity checks, inferences, limitations | 2026-08-30 |

## Study C — Difficulty Scaling: 3B vs 7B VLM Accuracy (2026-08-30)

Script: `experiments/vision/study_c_difficulty.py`. A6000 (cuda:1), qwenvl7b + qwenvl3b (Qwen2.5-VL, bfloat16).
COCO val2017, person category. Difficulty = annotated person count: L1=1, L2=2-3, L3=4-7, L4=8+. 30 images/level, 3 reps each. Two prompt modes: direct (max 30 tokens) and stepwise chain-of-thought (max 512 tokens). Greedy decoding, fixed seed 42. Trial order randomized per model.
Key findings: (RQ1) stepwise token count scales monotonically with difficulty for both models (7B: 69→140 tok, 3B: 75→126 tok). (RQ2) accuracy gap is non-monotone and reverses at high difficulty in stepwise mode. (RQ3) chain-of-thought hurts both models at high difficulty; 7B-stepwise-L4=0.000. Neither the gap-widening nor the CoT-benefit hypothesis is supported.

| file | script | model | device | n | headline | source commit |
|---|---|---|---|---|---|---|
| `results/vision/study_c/study_c_results.json` | `study_c_difficulty.py` | qwenvl7b + qwenvl3b | a6000 (cuda:1) | 1,440 trials (16 cells × 90 each) | Per-cell: acc, token median [p25,p75], budget_hit_frac, unparseable_frac, latency_median_ms. SC2 PASS (stepwise >20× more tokens). SC3 PASS (max budget 3.3%). SC4 warning: 3B-stepwise-L1 6.7% unparseable. | 2026-08-30 |
| `results/vision/study_c/study_c_trials.csv` | `study_c_difficulty.py` | qwenvl7b + qwenvl3b | a6000 | 1,440 rows | Per-trial: model, image_id, level, n_persons_gt, mode, rep, n_input, n_generated, latency_ms, budget_hit, parsed_answer, parse_status, correct | 2026-08-30 |
| `results/vision/study_c/study_c_selection.json` | `study_c_difficulty.py` | — | — | 120 images | Per-image: image_id, n_persons_gt, level, width, height; no bytes stored | 2026-08-30 |
| `figures/vision/study_c_difficulty.{pdf,png}` | `study_c_difficulty.py` | — | — | — | Two-panel: accuracy vs difficulty (all 4 model×mode curves) and stepwise token count vs difficulty | 2026-08-30 |
| `reports/study_c_difficulty.md` | — | — | — | — | Full report: what was run, raw measurements with spread, sanity checks, RQ1-RQ3 inferences, what cannot be inferred | 2026-08-30 |

## Study D — Reasoning Compute vs Parameters (partial; 2026-08-30)

Script: `experiments/vision/study_d_thinking.py`. A6000 (cuda:1), bfloat16, greedy. Same 120 COCO images as Study C.
Models run: qwen3vl4b (Instruct) and qwen3vl4b_t (Thinking). 8B models not run — stop condition fired at qwen3vl4b_t/L4 (30% budget hit > 5% threshold).
Key findings: think tokens scale monotonically 54→1626 L1→L4. 4B-Thinking beats 4B-Instruct at L2–L4; L3 gap most reliable (+0.233, no budget hits). L4 lower-bound only (truncated). Rerun needed with max_new_tokens=8192 for 8B models and reliable L4 Thinking values.

| file | script | model | device | n | headline | source commit |
|---|---|---|---|---|---|---|
| `results/vision/study_d/study_d_trials.csv` | `study_d_thinking.py` | qwen3vl4b + qwen3vl4b_t | a6000 (cuda:1) | 720 rows (8 cells × 90) | Instruct acc L1–L4: 0.967/0.700/0.167/0.033. Thinking acc: 0.933/0.800/0.400/0.100†(†truncated). Think tokens median: 54/78/396/1626. | 2026-08-30 |
| `results/vision/study_d/study_d_results.json` | `study_d_thinking.py` | qwen3vl4b + qwen3vl4b_t | CPU | 8 cells | Per-cell: acc, n_generated, n_think median/p25/p75, budget hits, unparseable | 2026-08-30 |
| `figures/vision/study_d_thinking.{pdf,png}` | `study_d_thinking.py` | — | — | 8 cells | Two-panel: accuracy vs difficulty (4 model×mode curves) and token count vs difficulty | 2026-08-30 |
| `reports/study_d_thinking.md` | — | — | — | — | Full report: stop condition, SC1–SC5, per-cell table, RQ1–RQ3 answers, what cannot be inferred, next steps | 2026-08-30 |

## Study C Re-scoring — Tolerance-Based Accuracy and Error Analysis (2026-08-30)

Scripts: `experiments/vision/study_c_rescore.py` (CPU only, no new inference), `experiments/vision/study_c_rescore_plots.py` (plotting).
Input: `results/vision/study_c/study_c_trials.csv` (1,440 rows). All sanity checks PASS.
Key findings: near-zero exact-match accuracy at L3–L4 is substantially a scoring artifact — within-1 accuracy is 2–3× higher (e.g., 7B-direct-L3: exact=0.367, within-1=0.800). Models track count ordinally (pooled Spearman 0.70–0.88). Systematic undercount at L2–L3 (~1 person); massive stepwise undercount at L4 (~4.5 persons, CoT collapse). Difficulty axis is usable at L3 under within-1; exact-match should be retired for L3+.

| file | script | model | device | n | headline | source commit |
|---|---|---|---|---|---|---|
| `results/vision/study_c/study_c_rescore.json` | `study_c_rescore.py` | qwenvl7b + qwenvl3b | CPU (no GPU) | 1,440 rows (16 cells) | Per-cell: exact_conservative, within-1/2_conservative, rt25, mean/median error, MAE, Spearman. SC1–SC4 PASS. | 2026-08-30 |
| `figures/vision/study_c_rescore_accuracy.{pdf,png}` | `study_c_rescore_plots.py` | — | CPU | 16 cells | Accuracy vs difficulty under exact / within-1 / within-2 tolerance; 4 model×mode curves per panel | 2026-08-30 |
| `figures/vision/study_c_rescore_errors.{pdf,png}` | `study_c_rescore_plots.py` | — | CPU | 16 cells | Signed error scatter + median diamond per (model, level, mode); zero-line reference | 2026-08-30 |
| `figures/vision/study_c_rescore_scatter.{pdf,png}` | `study_c_rescore_plots.py` | — | CPU | 4 panels (model × mode) | Parsed vs GT scatter; identity line; ±1 band; pooled Spearman in title | 2026-08-30 |
| `reports/study_c_rescore.md` | — | — | — | — | Full report: what was recomputed, 4 sanity checks, per-cell metric table, 7B−3B gap table, pooled Spearman, RQ1–RQ3 answers, usability verdict | 2026-08-30 |

## Study D2 — Reasoning Compute vs Parameters, Full 4-Model Run (2026-08-30)

Scripts: `experiments/vision/study_d2_thinking.py`. A6000 (cuda:1), bfloat16, greedy decoding. Same 120 COCO images as Study C/D. transformers 5.12.1 · torch 2.4.1+cu118. Main matrix: L1–L3 × 4 models × 3 reps. L4 probe: 10 images × 1 rep × 2 Thinking models (termination classification only).

Key finding: At L3 under within-1, 4B-Thinking (0.767) = 8B-Thinking (0.767) > 4B-Instruct (0.733) = 8B-Instruct (0.733). 4B-T beats 8B-I under exact-match (+0.067) at 62× latency cost (8693ms vs 140ms). Think-token IQR/median=1.84 at L3 — not predictable within the level. L4 probe: non_termination=20% (4B-T) / 30% (8B-T); verbose_bounded=0% for both — budget failure at L4 is always reasoning non-convergence, never post-answer verbosity.

| file | script | model | device | n | headline | date |
|------|--------|-------|--------|---|---------|------|
| `results/vision/study_d2/study_d2_trials.csv` | `study_d2_thinking.py` | qwen3vl4b + qwen3vl8b + qwen3vl4b_t + qwen3vl8b_t | a6000 (cuda:1) | 1,280 rows (1260 main + 20 probe) | Per-trial: model, mode, probe, image_id, level, n_persons_gt, rep, n_input, n_generated, n_think_tokens, n_answer_tokens, latency_ms, tokens_per_second, budget_hit, think_closed, termination_class, parsed_answer, parse_status, correct | 2026-08-30 |
| `results/vision/study_d2/study_d2_results.json` | `study_d2_thinking.py` | all 4 models | CPU | 12 main cells + 2 probe entries | Per-cell: exact/within-1/within-2/rt25 accuracy; think-token median/p25/p75/min/max/IQR-ratio; latency; tps; point-biserial r; think/GT ratio. Probe: termination class counts. | 2026-08-30 |
| `figures/vision/study_d2_thinking.{pdf,png}` | `study_d2_thinking.py` | — | — | 3 panels | Panel 1: accuracy (exact + within-1 dotted) vs L1–L3. Panel 2: think-token median ± IQR shading vs difficulty. Panel 3: latency (s) vs difficulty. | 2026-08-30 |
| `reports/study_d2_thinking.md` | — | — | — | — | Full report: what was run, raw measurements (accuracy × 4 tolerances, latency, budget hits, L4 probe), SC1–SC7, analyses A–E (accuracy, decisive comparison, think-token distributions, within-cell point-biserial r, token growth vs object count), two key questions answered, what cannot be inferred | 2026-08-30 |

## Study F — A6000 Diagnostic Arm (2026-08-31)

Scripts: `experiments/vision/study_f_a6000_diagnostic.py`. Device: **A6000 (cuda:1, 48 GB)**, bfloat16, flash-attn 2.6.3. torch 2.4.1+cu118 · transformers 5.12.1.

Part 1: Qwen3-VL-4B-I vs 8B-I decode rate under 3 conditions (C1 dynamic cache, C2 static cache, C3 torch.compile). Fixed decode 256 tokens, EOS suppressed, 5 reps. Roofline = A6000 768 GB/s ÷ weight bytes.  
Part 2: Qwen2.5-VL-7B phase-level memory at N=1,3,6,12 (Study B setup). Reset peak counters between phases.

Key: 4B separates from 8B on A6000 (48.5 vs 32.0 tok/s C1; 54.8 vs 35.0 C2); C3 failed both (flash-attn not traceable with fullgraph=True). Phase 2: weights ~97% of peak; vision delta <0.3%; KV matches Study B (ratio 1.000). A6000 N=6 peak = 17.4 GB.

| file | script | model(s) | device | n | headline | date |
|---|---|---|---|---|---|---|
| `results/vision/study_f_a6000/study_f_environment.json` | `study_f_a6000_diagnostic.py` | — | a6000 | — | Stack: torch 2.4.1+cu118, transformers 5.12.1, flash-attn 2.6.3, CUDA 11.8, driver 550.163.01 | 2026-08-31 |
| `results/vision/study_f_a6000/study_f_part1_decode.csv` | `study_f_a6000_diagnostic.py` | qwen3vl4b_i + qwen3vl8b_i | a6000 (cuda:1) | 20 rows (5 reps × 2 models × 2 conditions; C3 skipped) | Per-rep: model, condition, weight_gb, n_input, n_output, prefill_ms, decode_ms, decode_tok_per_s, peak_mem, attn_impl, compile_ok, is_warmup | 2026-08-31 |
| `results/vision/study_f_a6000/study_f_part1_decode.json` | `study_f_a6000_diagnostic.py` | qwen3vl4b_i + qwen3vl8b_i | a6000 (cuda:1) | 2 models | Rooflines (86.5 / 43.8 tok/s), per-condition median/mean/std/pct-RL, c3_error string | 2026-08-31 |
| `results/vision/study_f_a6000/study_f_part2_memory.csv` | `study_f_a6000_diagnostic.py` | qwen2.5-VL-7B | a6000 (cuda:1) | 4 rows (N=1,3,6,12) | Per-N: after-load/after-vision/after-prefill alloc+reserved GB, peak alloc+reserved, KV analytical GB, encode_batched | 2026-08-31 |
| `results/vision/study_f_a6000/study_f_part2_memory.json` | `study_f_a6000_diagnostic.py` | qwen2.5-VL-7B | a6000 (cuda:1) | 4 N-values | Same as CSV plus model metadata (image_size, tokens_per_frame, kv_bytes_per_token) | 2026-08-31 |
| `reports/study_f_a6000_diagnostic.md` | — | — | — | — | Full report: stack config, raw measurements, SC1–SC6, Part 1 separation verdict, Part 2 phase attribution. N=1 GC artifact documented. | 2026-08-31 |

## Study E — Device-Side Cost on Jetson AGX Orin (2026-08-31)

Scripts: `experiments/vision/study_e_orin_cost.py` (Part 1 inference), `study_e_state_cost.py` (Part 2 state construction), `thermal_sampler.py` (Part 3). Device: **jetson_orin (nesl-orin-3, 64 GB, MAXN, cuda:0)**, bfloat16, greedy. transformers 5.10.2 · torch 2.8.0 · CUDA 12.6 · **SDPA, no flash-attn** (vs A6000 flash-attn — gaps carry a software-stack component).

| file | script | model(s) | device | n | headline | source commit |
|---|---|---|---|---|---|---|
| `results/vision/study_e/study_e_part1_trials.csv` + `study_e_part1_results.json` | `study_e_orin_cost.py` | qwen3vl4b/8b Instruct+Thinking | jetson_orin | 4 models × L2/L3 × 15 img × 3 reps = 360 | Decode ~9.4 tok/s for all models (overhead-bound, 4B=8B); 8B cost in TTFT (434 vs 280 ms) + mem (17.7 vs 9 GB). Orin ~4× A6000 Instruct latency, ~3–5× slower Thinking decode. No throttle. | uncommitted |
| `results/vision/study_e/study_e_part2_trials.csv` + `study_e_part2_results.json` | `study_e_state_cost.py` | qwen2.5-VL-7B (=Study B model) | jetson_orin | N∈{1,3,6,12} × {full,window-k3,summary} × 2 reps | Full-retention ceiling **N=6** (peak 53.4 GB; OOM at N=12) vs A6000 N≥48 — O(L²) SDPA memory, no flash-attn, despite 64 GB unified. KV ratio 1.000, vision tokens 400 (match Study B). | uncommitted |
| `results/vision/study_e/study_e_thermal.csv` | `thermal_sampler.py` | — | jetson_orin | 10,345 samples / 14.5 h | Sustained load: **no throttling** (max tj 65 °C, GPU pinned 1.3005 GHz, 0 throttle samples); throughput flat 9.17→9.40 tok/s. | uncommitted |
