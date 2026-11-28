# Paper figure status (StudyFIG, placeholder set)

Scripts: `experiments/analysis/figures/` (`paperstyle.py` shared style, `figcommon.py` and `fig5_11_common.py` helpers, `gallery.py`).
Outputs: `figures/paper/FNN_<name>.{pgf,pdf,png,caption.txt,rows.json}`; review set `figures/paper/GALLERY.pdf`.
Status rules: FINAL = frozen arm on evaluation seeds (none yet); DEV = `covex-v6-fair-final-cand-tl`, `-cand-tl-sync` and
baselines on seeds 4-7; OLD = rung 3 `covex-v6-fair-final` stand-in, earlier rungs, provisional or superseded rows;
NO DATA = empty axes with "NO DATA YET". Data as of 2026-11-27.

| figure | status | source files | missing or OLD | what changes when the frozen arm and seeds 1-3 land |
|---|---|---|---|---|
| F01_intro_teaser | OLD DATA | reports/figdata/F1.csv, F1_units.csv.gz | COVEX is rung 3; eco-llm has no seed 5 | rerun with the frozen arm; add seeds 1-3 |
| F1_headline | OLD DATA | F1.csv (standard grid) | COVEX OLD; confidence-cascade has no dashcam cells ("n/a"); eco-llm lacks seed 5 | swap arm; pool extra seeds |
| F2_ontime_vs_correct | OLD DATA | F2.csv | COVEX OLD; device-only on-time NaN for robot and single-shot; no confidence-cascade rows | swap arm; add seeds |
| F3_latency_cdf | NO DATA | F3.csv.gz | no device-only rows; no delivered-answer latency field (only standing and cloud latency, each NaN for 16 to 33 percent of requests, plus composite stamps) | producer must add device-only rows and the delivered-answer latency |
| F4_per_device | OLD DATA | F4.csv (dashcam only) | no device-only per-device rows for robot or single-shot. Device-only dashcam attainment is 0.00 by definition: the metric counts on-time cloud alerts only (canon.py dash_attainment; device alerts are never added), while device-only mAP is 0.63 (F1.csv). Not missing rows, and the metric is not changed here | add device-only per-device rows for robot and single-shot; a device-side dashcam metric would be a definition change for the user to rule on |
| F05_ablation_ladder | OLD DATA | F1.csv seed 4 (rungs 0 to 3); committed cells via the committed scorer | seed 4 only; +S2 only under outage; counterfactual admission (-cf-a) has no outage cell; eager has no no-outage cell; no P-only or 0b-only arm | add seeds and CIs; swap rung 3 for frozen arm; full +S2 row |
| F06_timeline | DEV DATA | cand-tl n20 seed 4 normal and outage cells: decision.jsonl.gz, host_counters_d211.log, outcomes.jsonl | seed 4 only; warms and touches are 1:1 (one line); occupancy is engine-measured | swap to frozen arm; several seeds |
| F07_planner_decisions | NO DATA | F7.csv (0 rows); decision.jsonl has only state_action, touch, release, defer, decline | KEEP, RELOAD, HOLD_BACK and SLICE not logged | per-kind decision log at 1x and 0.5x |
| F08_memory | OLD DATA | F1.csv (1x), F8.csv (0.5x), cand-tl from committed n16 seed 4 cells | 0.5x tag chosen per arm (kv0.5r_h0.5, else kv0.5r, else kv0.5); dev arm seed 4 only | frozen arm and seeds 1-3 |
| F09_fleet_load | OLD DATA | F9.csv, F1.csv (n16), cand-tl n16 and n20 seed 4 | capacity line absent (column blank; build fails once values exist); many arms seed 4 only; F9 labels all cells 40:40:20 although c3-11-2 cells are 3:11:2 (drawn as a separate dashed series) | capacity line; missing n for baselines; frozen arm; fix the composition label in F9.csv |
| F10_robot_deadline | OLD DATA | F10.csv plus 3.0 s cells from F1.csv | 4 s and 5 s absent (shaded); 2.5 s lacks COVEX and SimpleStream; 1.5 s lacks LLF, Mooncake, device-only; no dev arm | four deadlines for all arms |
| F11_composition | NO DATA | F11.csv (0 rows) | needs dashcam-heavy, 3:11:2 sweep, rq10 and rq60, mixed robot cells; only rq30 and 40:40:20 exist | the composition and re-ask cells |
| F12_network | OLD DATA | frozen_test cells n20 seed 4, outage 407.5 to 595.5 s, outcomes.jsonl, cell.json, link_events.json | rung 3 and eager OLD; F0 no-S2 and F0+S2 DEV; seeds 5 to 7 outage cells not committed; no no-outage control for eager or F0+S2; controls only on dashcam panel | rerun on frozen arm, seeds 4 to 7, add controls. Note: READINESS.md says no network cells exist; the outage outcomes do exist |
| F13_gpu_efficiency | OLD DATA | F13.csv, standard grid (16 devices, 1x, 3 s, seeds 4 to 7) | COVEX rung 3; DEV arms absent from F13.csv; LMCache and Warm-all LRU have blank GPU fields (not drawn); Mooncake 1 of 4 seeds, ECO-LLM 3 of 4 | regenerate figdata with DEV and frozen arms |
| F14_decision_latency | OLD DATA | F14.csv (wall clock, stated in caption) | COVEX rung 3; larger fleets single seed (hollow); baselines only at 8 to 16 devices; dry latency not committed; decision logs look capped near 12,000 | frozen arm, larger fleets, dry latency |
| F15_ap_vs_time_to_event | no arm status (model-level) | reports/figures/early1_results.json (StudyEARLY1) | F15.csv is a gap row; device is the 4B model, cloud the 32B model; cloud delivery latency not charged | nothing unless system-level AP is wanted (StudyDSMAP) |
| F16_history_and_warm | no arm status (measurements) | (a) orin_rec_part2.jsonl, acc2_requests.jsonl, lh_req_definition.json (69 long-history questions); (b) study_rh5_results_h100nvl.json | (b) cold row from the GPU-only server (host-offload server has no cold rows); cost_matrix.csv not used | nothing |
| F17_real_deployment | NO DATA | none | no real-deployment data | real-deployment data when it exists |

Notes:
- Gallery figure numbers are assigned by LaTeX in file order (the caption prefixes read "Figure 1" to "Figure 18"), not by the paper's numbering.
- The device-only purple #7A4E9C is a PLACEHOLDER until the user supplies the exact Figure 3 purple (TODO in paperstyle.py).
- Gallery: each figure is on its own page (clearpage), because lost floats left blank pages and missing captions in the first build. 18 of 18 captions verified with pdftotext.
- Build logs (`figures/paper/preview/*.aux|log|blg|bbl|out`) are not committed.
