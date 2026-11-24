# D190 frontier data: definitions and provenance

One row per (arm, seed, memory). Full memory (1x) and the 0.5x KV sweep (the _kv0.5 tag).
Seeds 4 to 7 only. CPU only, read-only on every input. No row is guessed: a cell with no
outcomes.jsonl.gz is a preflight-only stub and is marked scorable=false with blank metrics.

## How each quantity is produced

Every score is READ from the committed cell.json (written by the committed scorer at run
time) or COMPUTED by calling the pre-registered D179 scorer; none is reimplemented here.

- robot_on_time, robot_pool_n, robot_on_time_frac: cell.json score.sweep[0] robot_pool_on_time / robot_pool_n / robot_pool_fraction. Cloud on-time only (D177); the device side is never added. On time = t_delivered - t_opportunity <= L + 1e-9 with the two committed delivery passes (D144/D175 refusal nulling, D146 completion re-basing), L_rob 3.0 s.
- retention_rung2_gain_over_base: (arm_frac - base_frac) / (rung2_frac - base_frac) per seed, 1x only. base = hybrid-F-lhreq-noc3, rung2 = covex-v6-state-uo (the D179 check 2 comparators). Blank at 0.5x because the rung2 comparator has no 0.5x cell.
- robot_by_deadline_acc: cell.json robot_headline.correct_answers_delivered_by_deadline (D155 (3)). This is an ACCURACY, not an on-time rate, and admits the device side; it is reported BESIDE the on-time rate, never substituted for it. device_only_robot_floor is the device-only robot accuracy (D87 proxy, valid for ordering not as an exact Orin number).
- assist_within2s_pooled: cell.json ss_pool_fraction, assistance within 2.0 s pooled over offered opportunities. assist_perdev_min: the lowest per-device assistance fraction (the D179 check 3 unit is the DEVICE, so the pooled figure can hide a starved device).
- alert_mean_per_episode_attain and alert_frac_episodes_ge_0p25: the D186 primary statistic, computed by the D179 scorer's _alert_episode_block from outcomes.jsonl.gz. Episode key = (play_id, round((t_local - 3.0)/0.5) // 21); per-episode denominator = 19 (D178 (1) declared constant, positions 2 to 20 of 21); target 0.25. mean_attain is the mean of on_time_e / 19 over episodes; frac_episodes_ge_0p25 is the fraction of episodes at or above 0.25. Both are reported because the two readings of target attainment can disagree. alert_pooled_attain is the pooled reading BESIDE them (it understates the deficit by about 3.5x and is never the verdict).
- late_alert_frames: alert instants offered minus alert instants on time (recomputed recall rule for alert). This lumps delivered-but-late with never-delivered; the on-time / late / unsent split is drawn only in F4, where it is computed with the committed delivery functions.

## Positive control (consistency check 7)

For every scorable cell the D179 scorer re-derives the counts from the raw logs. The HEADLINE counts, robot on-time, robot pool, assistance on-time and assistance pool, must EQUAL the cell's own committed counts exactly; control_robot_ss_exact records this and is true on all 117 scorable cells. The committed d179_rung2_verdict.json records the same control as PASS on all 8 comparator cells, and this builder reproduces base seed 4 at mean_attain 0.44249 and rung2 seed 4 at 0.163291, matching that file exactly. crosstab_ok requires the (prefix, kind, deadline) cross-tab to be exactly {(dash, monitor, 1.0), (robo, recall, 3.0), (asst, recall, 2.0)}; a false value means the cell must not be read. The pooled dashcam on-time count drifts by 1 to 2 instants out of about 11,764 on some baselines (dashcam_committed_minus_recomputed), a delivery-boundary micro-tie at the <= L + 1e-9 edge; it is below 0.02 percent, does not touch the per-episode attainment, and is recorded as a diagnostic rather than a gate. The alert figures are taken from the recompute throughout so they are internally consistent.

## Arm families present (scorable)

always-cloud-fcfs, attentionstore-prefetch, b7-edf-feasibility, base, cascade-routing, covex-v6-fair-c5attr-rr, covex-v6-fair-final, covex-v6-final, covex-v6-state-final, eco-llm, edf, fair-c5attr, fair-c5attr-gain0, joint-c3, kvflow-prefetch, llf, lmcache, mooncake, querystream-proactive, r3-streaming, rules, shares, shares-r1, shares-r2, simplestream, state, state-uo, state-uo-c5attr, streamscout, v5-rules-old, warm-all-lru

base and rules each cover two raw arm names at different memory: base = hybrid-F-lhreq-noc3 (1x) and covex-v6-base (0.5x); rules = v5-rules-2 (1x) and covex-v6-rules (0.5x). v5-rules-old is the superseded rules arm, kept separate. joint-c3 is hybrid-F-lhreq (the joint policy with C3), kept beside the noc3 base. The rule-based C5 fix family, drawn as one family in F1, is the -c5attr arms (state-uo-c5attr, fair-c5attr, fair-c5attr-gain0).

## Missing or unparsable cells

- always-cloud-fcfs_n16_s5_1200s_h27_3t_L3_epg_rq30: preflight-only stub, absent: cell.json, outcomes.jsonl.gz
- confidence-cascade_n16_s4_1200s_h27_3t_kv0.25_L3_epg_rq30: name did not match the rq30 cell pattern
- confidence-cascade_n16_s4_1200s_h27_3t_kv0.5r_L3_epg_rq30: name did not match the rq30 cell pattern
- confidence-cascade_n8_s4_1200s_h27_3t_L3_epg_rq30: name did not match the rq30 cell pattern
- covex-v6-base_n12_s4_1200s_h27_3t_L3_epg_rq30: name did not match the rq30 cell pattern
- covex-v6-base_n12_s5_1200s_h27_3t_L3_epg_rq30: name did not match the rq30 cell pattern
- covex-v6-base_n16_s4_1200s_h27_3t_L2.5_epg_rq30: name did not match the rq30 cell pattern
- covex-v6-base_n16_s4_1200s_h27_3t_kv0.25_L3_epg_rq30: name did not match the rq30 cell pattern
- covex-v6-base_n16_s4_1200s_h27_3t_kv0.5r_L3_epg_rq30: name did not match the rq30 cell pattern
- covex-v6-base_n16_s5_1200s_h27_3t_L2.5_epg_rq30: name did not match the rq30 cell pattern
- covex-v6-base_n20_s4_1200s_h27_3t_L3_epg_rq30: name did not match the rq30 cell pattern
- covex-v6-base_n20_s5_1200s_h27_3t_L3_epg_rq30: name did not match the rq30 cell pattern
- covex-v6-rules_n12_s4_1200s_h27_3t_L3_epg_rq30: name did not match the rq30 cell pattern
- covex-v6-rules_n12_s5_1200s_h27_3t_L3_epg_rq30: name did not match the rq30 cell pattern
- covex-v6-rules_n16_s4_1200s_h27_3t_L2.5_epg_rq30: name did not match the rq30 cell pattern
- covex-v6-rules_n16_s4_1200s_h27_3t_kv0.25_L3_epg_rq30: name did not match the rq30 cell pattern
- covex-v6-rules_n16_s4_1200s_h27_3t_kv0.5r_L3_epg_rq30: name did not match the rq30 cell pattern
- covex-v6-rules_n16_s5_1200s_h27_3t_L2.5_epg_rq30: name did not match the rq30 cell pattern
- covex-v6-rules_n20_s4_1200s_h27_3t_L3_epg_rq30: name did not match the rq30 cell pattern
- covex-v6-rules_n20_s5_1200s_h27_3t_L3_epg_rq30: name did not match the rq30 cell pattern
- covex-v6-state_n16_s4_1200s_h27_3t_L3_epg_rq30: preflight-only stub, absent: cell.json, outcomes.jsonl.gz
- covex-v6-state_n16_s6_1200s_h27_3t_L3_epg_rq30: preflight-only stub, absent: outcomes.jsonl.gz
- covex-v6-state_n16_s7_1200s_h27_3t_L3_epg_rq30: preflight-only stub, absent: cell.json, outcomes.jsonl.gz
- eco-llm_n16_s4_1200s_h27_3t_kv0.25_L3_epg_rq30: name did not match the rq30 cell pattern
- eco-llm_n16_s4_1200s_h27_3t_kv0.5r_L3_epg_rq30: name did not match the rq30 cell pattern
- llf_n16_s4_1200s_h27_3t_L2.5_epg_rq30: name did not match the rq30 cell pattern
- llf_n16_s4_1200s_h27_3t_kv0.25_L3_epg_rq30: name did not match the rq30 cell pattern
- llf_n16_s4_1200s_h27_3t_kv0.5r_L3_epg_rq30: name did not match the rq30 cell pattern
- mooncake_n16_s4_1200s_h27_3t_L2.5_epg_rq30: name did not match the rq30 cell pattern
- mooncake_n16_s4_1200s_h27_3t_kv0.25_L3_epg_rq30: name did not match the rq30 cell pattern
- mooncake_n16_s4_1200s_h27_3t_kv0.5r_L3_epg_rq30: name did not match the rq30 cell pattern
- simplestream_n16_s4_1200s_h27_3t_kv0.25_L3_epg_rq30: name did not match the rq30 cell pattern
- simplestream_n16_s4_1200s_h27_3t_kv0.5r_L3_epg_rq30: name did not match the rq30 cell pattern
- v5-rules_n16_s7_1200s_h27_3t_L3_epg_rq30: preflight-only stub, absent: cell.json, outcomes.jsonl.gz

## Provenance

- runs dir last commit: b8d5600a
- scorer score.py last commit: 9803dca0
- d179_rung2_verdict.py last commit: 35b5bc85
- build time is deliberately NOT stamped here: the output is byte-deterministic given the input, so the D190 poll commits only on a real data change. The git commit of this file is the build time of record.
- source data: results/orchestration/live2/frozen_test/runs/<cell>/cell.json and outcomes.jsonl.gz; scorers experiments/orchestration/live2/scorer/score.py and experiments/orchestration/live2/d179_rung2_verdict.py
