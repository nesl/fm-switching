# D192 episodic scores: definitions, provenance, validation

One row per (arm, seed), seeds 4 to 7, full-memory final-workload cells (<arm>_n16_s<seed>_1200s_h27_3t_L3_epg_rq30), preferring the _rerun directory when present (which supplies always-cloud-fcfs s5, covex-v6-state s4, v5-rules s7). A device-only reference row per seed uses device answers only. CPU only, read-only on every input.

## Standing answer and thresholds

At each decision instant the STANDING answer is the cloud answer if it was delivered on time (within the 1.0 s alert deadline), otherwise the device answer (D165 B). Each tier is scored with its OWN score and its OWN FAR-10 threshold on DEV from StudySH-EP EP-G folds (sh_ep_results.json h2_earliness EP-G|far10): device 4BI threshold -2.578890 (achieved FAR 0.0536), cloud 32BI threshold -6.876021 (achieved FAR 0.0315). A standing score CROSSES when it is at or above its tier threshold (higher score = more yes). The EP-G calibration maps (score to probability) per tier are in each cell's calibration_knots.json and are available if a probability readout is wanted; the operating threshold is applied in score units.

## Step 1 dashcam, per task episode

Episodes are the workload's 21-frame episodes (episode_id from the committed per-seed trace table dashcam_instants.jsonl.gz, 712 to 714 per seed, matching d185_rung3_verdict.json). The device score and clip_pts per instant come from that table; the cloud on-time flag and cloud score come from the cell's outcomes.jsonl.gz, joined by opportunity_id (11764/11764 on seed 4). A CRASH episode is one whose clip is Nexar-positive AND whose clip_pts span contains the labelled event time ref (time_of_event), with an instant strictly before ref. Every other episode is a NO-CRASH episode; this includes negative clips and the pre/post-event segments of positive clips (dash_pos_nonevent_nocrash counts the latter, about 249 of 712 on seed 4). This labelling matches StudySH-EP calibrating FAR on non-event frames. A crash episode is CORRECT if its first standing crossing is at clip_pts < ref (lead = ref - clip_pts); a no-crash episode is CORRECT if there is no crossing, else it is a false alarm.

Per arm and seed: dash_detection_rate (crash episodes detected before the event / crash episodes), dash_false_alarm_rate (no-crash episodes with a crossing / no-crash episodes), dash_fraction_correct, dash_median_lead_s, and cost dash_cloud_req_per_episode and dash_gpu_s_per_episode (GPU seconds = 0.000182431 x uncached tokens, D174; uncached = prompt_tokens - cached_tokens, cached-absent recorded not zeroed).

## Step 2 early-exit headroom (design only, no claim)

dash_gpu_after_crossing and dash_gpu_fraction_after_crossing are the cloud GPU seconds spent on instants AFTER an episode's first standing crossing (the decision is already made), as a total and a fraction of all dashcam cloud GPU, split by crash vs no-crash (dash_gpu_after_crash / dash_gpu_after_nocrash).

## Step 3 robot, Step 4 single-shot, Step 5 unified

Robot: the committed scorer headline correct_answers_delivered_by_deadline x n_by_deadline, read from cell.json (cloud if on time within 3 s, else device). Single-shot: per asst opportunity, cloud correctness if the cloud answer was delivered within 2 s, else device correctness, from StudySS2 per-qid correctness (exact_match for realworldqa, point_accuracy >= 0.5 for refspatial) joined by question_id; 0 missing qids. Unified (Step 5): unified_pooled_frac is the pooled correct-in-time COUNT fraction over all units (dashcam episodes + robot questions + single-shot questions); no weights are invented, and the per-type fractions (dash_fraction_correct, robot_frac, ss_frac) are reported beside it.

## Validation (Step 7)

Robot correct-by-deadline reproduces the committed cell.json headline exactly for every cell (it is read from it). StudySS2 per-qid correctness aggregates to the committed compare files exactly for realworldqa (device 0.654902, cloud 0.712418) and to within half a question for refspatial (binary cut 0.5 vs the compare's fractional mean). Device-only episode detection is reported in the device-only rows for comparison with StudySH-EP EP-G device numbers; see d192_validation.json.

## Missing cells

- kvflow-prefetch s7

## Provenance

- runs dir last commit: 9fcef35b
- device-score traces last commit: da4427de
- device scores and clip_pts: results/orchestration/live2/frozen_test/traces/<trace>/dashcam_instants.jsonl.gz (regenerated deterministically by the committed generator on flash; provenance in traces/d192_device_scores_provenance.json)
- thresholds: results/dashcam/study_sh_ep/sh_ep_results.json; Nexar labels and event times: sh_ep_manifest_meta.json and nexar_check.json; SS2: results/casestudy/study_ss2/
- build is byte-deterministic given the inputs (no timestamp stamped); the git commit of this file is the build time of record.
