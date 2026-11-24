# D192 episodic scores: definitions, provenance, validation

One row per (arm, seed), seeds 4 to 7, full-memory final-workload cells (<arm>_n16_s<seed>_1200s_h27_3t_L3_epg_rq30), preferring the _rerun directory when present (which supplies always-cloud-fcfs s5, covex-v6-state s4, v5-rules s7). A device-only reference row per seed uses device answers only. CPU only, read-only on every input.

## Standing answer and thresholds

At each decision instant the STANDING answer is the cloud answer if it was delivered on time (within the 1.0 s alert deadline), otherwise the device answer (D165 B). A standing score CROSSES when it is at or above its tier threshold (higher score = more yes).

PRIMARY, EPISODE-LEVEL thresholds (D192 refinement). The per-instant FAR-10 thresholds, applied once per 21-frame episode, compounded to an episode false-alarm rate of 0.25 to 0.33 for every arm, so the episode metric was dominated by threshold compounding. The episode-level thresholds are set on the StudySH-EP DEV EP-G episodes ONLY (never EVAL): for each tier, the threshold is the one at which at most 10 percent of NO-CRASH DEV episodes (negative clips, no pre-event instant) have ANY instant crossing when that tier alone serves every instant. Device 4BI theta -0.201413 (achieved DEV episode FAR 0.1111 over 45 negative DEV episodes); cloud 32BI theta -2.929832 (achieved DEV episode FAR 0.1111). Source: sh_ep_requests_4BI_shep1.jsonl and h100/sh_ep_requests_32BI_shep2-EP-G.jsonl.gz, side == DEV, condition == EP-G.

BESIDE, INSTANT-LEVEL thresholds (kept for comparison, columns dash_inst_*): the committed StudySH-EP FAR-10 thresholds on negative instants, device -2.578890, cloud -6.876021 (sh_ep_results.json h2_earliness EP-G|far10). Both versions use the same episode definition and standing-answer rule; only the threshold differs. The EP-G calibration maps (score to probability) per tier are in each cell's calibration_knots.json if a probability readout is wanted.

CAVEATS, stated. The DEV calibration set is small (45 negative episodes, so the 10 percent target lands at 5 episodes and the achieved DEV FAR is 0.111). The DEV EP-G episodes carry about 13 instants each while the workload episodes carry up to 19, so a little residual compounding remains and the workload episode FAR can differ from 10 percent (it comes out near 0.08 on the base cell). 88 of the 90 DEV clips also appear in the workload (the workload samples the whole Nexar pool); the thresholds are still set on the DEV FOLD and never on EVAL, but the calibration and evaluation clip sets are not disjoint, which is noted rather than hidden.

## Step 1 dashcam, per task episode

Episodes are the workload's 21-frame episodes (episode_id from the committed per-seed trace table dashcam_instants.jsonl.gz, 712 to 714 per seed, matching d185_rung3_verdict.json). The device score and clip_pts per instant come from that table; the cloud on-time flag and cloud score come from the cell's outcomes.jsonl.gz, joined by opportunity_id (11764/11764 on seed 4). A CRASH episode CONTAINS a pre-event instant (its clip is Nexar-positive and it has an instant strictly before the labelled event time ref = time_of_event); every other episode is a NO-CRASH episode (negative clips and the post-event segments of positive clips, the latter counted by dash_pos_nonevent_nocrash). This is the SAME no-crash definition used to calibrate the episode-level DEV thresholds, so the two are consistent (on seed 4, 172 crash and 540 no-crash). A crash episode is CORRECT if its first standing crossing is at clip_pts < ref (lead = ref - clip_pts); a no-crash episode is CORRECT if there is no crossing, else it is a false alarm.

Per arm and seed: dash_detection_rate (crash episodes detected before the event / crash episodes), dash_false_alarm_rate (no-crash episodes with a crossing / no-crash episodes), dash_fraction_correct, dash_median_lead_s, and cost dash_cloud_req_per_episode and dash_gpu_s_per_episode (GPU seconds = 0.000182431 x uncached tokens, D174; uncached = prompt_tokens - cached_tokens, cached-absent recorded not zeroed).

## Step 2 early-exit headroom (design only, no claim)

dash_gpu_after_crossing and dash_gpu_fraction_after_crossing are the cloud GPU seconds spent on instants AFTER an episode's first standing crossing (the decision is already made), as a total and a fraction of all dashcam cloud GPU. It is split by crash vs no-crash (dash_gpu_after_crash / dash_gpu_after_nocrash) and, more usefully for the design, by the outcome that triggered the crossing: dash_gpu_after_true_detection (a crash episode whose crossing was before the event), dash_gpu_after_false_alarm (a no-crash episode that crossed), and dash_gpu_after_crash_crossing_not_before_event (a crash episode that crossed only at or after the event). These are the episode-level (primary) numbers.

## Step 3 robot, Step 4 single-shot, Step 5 unified

Robot: the committed scorer headline correct_answers_delivered_by_deadline x n_by_deadline, read from cell.json (cloud if on time within 3 s, else device). Single-shot: per asst opportunity, cloud correctness if the cloud answer was delivered within 2 s, else device correctness, from StudySS2 per-qid correctness (exact_match for realworldqa, point_accuracy >= 0.5 for refspatial) joined by question_id; 0 missing qids. Unified (Step 5): unified_pooled_frac is the pooled correct-in-time COUNT fraction over all units (dashcam episodes + robot questions + single-shot questions); no weights are invented, and the per-type fractions (dash_fraction_correct, robot_frac, ss_frac) are reported beside it. The dashcam term uses the PRIMARY episode-level thresholds; unified_inst_pooled_frac is the same pooled fraction with the instant-level dashcam term, kept beside for comparison.

## Validation (Step 7)

Robot correct-by-deadline reproduces the committed cell.json headline exactly for every cell (it is read from it). StudySS2 per-qid correctness aggregates to the committed compare files exactly for realworldqa (device 0.654902, cloud 0.712418) and to within half a question for refspatial (binary cut 0.5 vs the compare's fractional mean). Device-only episode detection is reported in the device-only rows for comparison with StudySH-EP EP-G device numbers; see d192_validation.json.

## Missing cells

- none (every arm has all four seeds)

## Provenance

- runs dir last commit: 1eae6bfb
- device-score traces last commit: da4427de
- device scores and clip_pts: results/orchestration/live2/frozen_test/traces/<trace>/dashcam_instants.jsonl.gz (regenerated deterministically by the committed generator on flash; provenance in traces/d192_device_scores_provenance.json)
- thresholds: results/dashcam/study_sh_ep/sh_ep_results.json; Nexar labels and event times: sh_ep_manifest_meta.json and nexar_check.json; SS2: results/casestudy/study_ss2/
- build is byte-deterministic given the inputs (no timestamp stamped); the git commit of this file is the build time of record.
