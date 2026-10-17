# Multiplier provenance audit

**Date:** 2026-10-16 · **Scope:** every committed file under `reports/*.md`
**Method:** extract every `N×` / `Nx` figure; check whether the report cites at least one
`results/...` path that exists on disk. **Provenance only — this does not re-derive any value.**
A report marked **NO** is *unverifiable from the report alone*; several such figures have been
checked by hand and are correct.

**Nothing in this audit was fixed.** Reporting only, per instruction.

## Why this exists

Two failures of the same kind prompted it:

- **The "85×" that never existed.** A cost ratio attributed to the registry for StudyP. The
  string appears nowhere in `research/EXPERIMENTS.md`, `results/INDEX.md` or any report. It was
  introduced in conversation, never had a source, and is not a lost measurement. Retracted in
  `reports/study_p_fa2_backend.md`.
- **The bucketing artifact.** "Flash-attn is 23–35% slower on short generations" propagated
  across four backend reports. It came from bucketing raw latency by one backend's token counts
  on *sampled* arms, where the other backend re-draws a different generation length. Corrected to
  throughput; flash-attn is never slower.

Both were confident numbers from a derivation nobody could retrace. This audit finds where else
that is possible.

## Totals

| | |
|---|---|
| committed reports containing a multiplier | **58** |
| multipliers found | **605** |
| reports citing **no** existing results file | **27** |
| multipliers inside those 27 reports | **178** |
| citations to a results path not on disk | **1** |

The single broken citation: `study_j2_survival.md` → `results/gemini/recogntion_results.json`.
The file it means lives at `/tmp/sign-understanding/recognition_results/gemini/recogntion_results.json`,
outside the repo.

## Caveats on reading this

1. **NO means unverifiable, not wrong.** `h100_night_summary.md` carries 20 multipliers and
   cites no results file, yet its three headline cost ratios (198.8× / 91.6× / 76.1×) were
   recomputed from the trial files on 2026-10-16 and are correct. The defect is provenance.
2. **Simulator reports may legitimately have no result file.** The `e24*` and `e36*` fleet-policy
   reports are simulation sweeps whose outputs live under `results/orchestration/` but are not
   named inline. That is a different category from a measurement report with no provenance.
3. **The count is of `N×` tokens, not distinct claims.** `phase1_cost_profiling.md` has 92,
   mostly table cells, and does cite its sources.

## Per-report

| report | multipliers | cites an existing results file |
|---|---|---|
| `study_d2_thinking.md` | 21 | **NO** |
| `h100_night_summary.md` | 20 | **NO** |
| `study_j4_seed_variance.md` | 15 | **NO** |
| `e36c_fleet_policy.md` | 10 | **NO** |
| `study_g2_transfer_cost.md` | 10 | **NO** |
| `study_i_diagnostic.md` | 10 | **NO** |
| `study_q_retry_vs_scale_erqa.md` | 10 | **NO** |
| `e24b_coupling_falsification.md` | 9 | **NO** |
| `e38_slide_figures.md` | 9 | **NO** |
| `e24c_coupling_final.md` | 7 | **NO** |
| `e36g_marginal_admission.md` | 7 | **NO** |
| `study_i3_budget.md` | 7 | **NO** |
| `e24_coupling_falsification.md` | 6 | **NO** |
| `e36b_fleet_policy.md` | 6 | **NO** |
| `study_d_thinking.md` | 5 | **NO** |
| `study_g_transfer_cost.md` | 4 | **NO** |
| `e36d_fleet_policy.md` | 3 | **NO** |
| `e36h_ablation.md` | 3 | **NO** |
| `oxford_av_feasibility.md` | 3 | **NO** |
| `study_i2_budget.md` | 3 | **NO** |
| `e30_capacity_arithmetic.md` | 2 | **NO** |
| `e36f_neff_policy.md` | 2 | **NO** |
| `related_work_verification.md` | 2 | **NO** |
| `e32_staleness_cost.md` | 1 | **NO** |
| `study_h_sember_structure.md` | 1 | **NO** |
| `study_j_signs.md` | 1 | **NO** |
| `study_p_retry_vs_scale.md` | 1 | **NO** |
| `phase1_cost_profiling.md` | 92 | yes |
| `study_p_fa2_backend.md` | 44 | yes |
| `study_s1_fa2_backend.md` | 37 | yes |
| `e34b_corrected_catchup.md` | 34 | yes |
| `e34_maintenance_semantics.md` | 31 | yes |
| `study_e_orin_cost.md` | 28 | yes |
| `study_q_fa2_backend.md` | 26 | yes |
| `study_s1_competent_categories.md` | 17 | yes |
| `study_j2_fa2_backend.md` | 16 | yes |
| `e27_maintenance_mechanism.md` | 11 | yes |
| `e31b_network_characterization.md` | 11 | yes |
| `e33a_definition_audit_and_ledger.md` | 10 | yes |
| `study_f_orin_diagnostic.md` | 10 | yes |
| `study_i_tier_gap.md` | 10 | yes |
| `a6000_night_summary.md` | 7 | yes |
| `study_o_q4_results.md` | 7 | yes |
| `study_i3_reanalysis.md` | 6 | yes |
| `e31_network_characterization.md` | 5 | yes |
| `e36_fleet_policy.md` | 5 | yes |
| `study_r_device_vs_cloud.md` | 4 | yes |
| `study_c_difficulty.md` | 3 | yes |
| `study_a_scene_content.md` | 2 | yes |
| `study_b_vision_kv.md` | 2 | yes |
| `study_f_a6000_diagnostic.md` | 2 | yes |
| `advisor_plots_manifest.md` | 1 | yes |
| `e36e_fleet_capacity.md` | 1 | yes |
| `study_c_rescore.md` | 1 | yes |
| `study_h2_sember_annotations.md` | 1 | yes |
| `study_j2_survival.md` | 1 | yes |
| | | cited but missing: `results/gemini/recogntion_results.json` |
| `study_s2_mvrobobench_32b.md` | 1 | yes |
| `study_t_signs_32b.md` | 1 | yes |

## Suggested remediation, not applied

Add a **Sources** line to each report naming the result files its numbers come from. For the 27
reports above that is a one-line edit each. A `make check-provenance` target running this audit
would keep it from regressing — the audit script is ~25 lines and is reproduced in this repo's
session scratchpad.
