# D190 frontier data: definitions and provenance

One row per (arm, seed, memory). Full memory (1x) and the 0.5x KV sweep (the _kv0.5r tag).
Seeds 4 to 7 only. CPU only, read-only on every input, NO images written. No row is guessed:
a cell with no outcomes.jsonl.gz is a preflight-only stub, marked scorable=false with blank
metrics.

## Columns new in the D232-era fix (2026-11-24)

- memory: 1x (no kv tag) or 0.5x (the _kv0.5r real-pool halved-budget tag). The old parser
  used the token _kv0.5 (no r), matched no 0.5x cell, and dropped every one; it is fixed.
- is_rerun / supersedes: a _rerun cell is kept and supersedes names the plain cell it
  replaces for that (arm, seed, memory).
- source_agreement: the header.json source_agreement.verdict, or ABSENT when the key is
  missing. A cell whose verdict starts with INVALID is NEVER used (listed below), per the
  project rule; an ABSENT cell is kept and marked, never dropped.

## How each quantity is produced

Every score is READ from the committed cell.json (written by the committed scorer at run
time) or COMPUTED by calling the pre-registered D179 scorer; none is reimplemented here.

- robot_on_time, robot_pool_n, robot_on_time_frac: cell.json score.sweep[0] robot_pool_on_time / robot_pool_n / robot_pool_fraction. Cloud on-time only (D177); the device side is never added. On time = t_delivered - t_opportunity <= L + 1e-9 with the two committed delivery passes (D144/D175 refusal nulling, D146 completion re-basing), L_rob 3.0 s.
- retention_rung2_gain_over_base: (arm_frac - base_frac) / (rung2_frac - base_frac) per seed, 1x only. base = hybrid-F-lhreq-noc3, rung2 = covex-v6-state-uo (the D179 check 2 comparators). Blank at 0.5x because the rung2 comparator has no 0.5x cell.
- robot_by_deadline_acc: cell.json robot_headline.correct_answers_delivered_by_deadline (D155 (3)). This is an ACCURACY, not an on-time rate, and admits the device side; it is reported BESIDE the on-time rate, never substituted for it. device_only_robot_floor is the device-only robot accuracy (D87 proxy, valid for ordering not as an exact Orin number).
- assist_within2s_pooled: cell.json ss_pool_fraction, assistance within 2.0 s pooled over offered opportunities. assist_perdev_min: the lowest per-device assistance fraction (the D179 check 3 unit is the DEVICE, so the pooled figure can hide a starved device).
- alert_mean_per_episode_attain and alert_frac_episodes_ge_0p25: the D186 primary statistic, computed by the D179 scorer's _alert_episode_block from outcomes.jsonl.gz, per-episode denominator per D178 / D232 (2); target 0.25. alert_pooled_attain is the pooled reading BESIDE them and is never the verdict.
- late_alert_frames: alert instants offered minus alert instants on time. This lumps delivered-but-late with never-delivered; the split is drawn only in F4.

## Positive control (consistency check 7)

For every scorable cell the D179 scorer re-derives the counts from the raw logs. The HEADLINE counts, robot on-time, robot pool, assistance on-time and assistance pool, must EQUAL the cell's own committed counts exactly; control_robot_ss_exact records this. crosstab_ok requires the (prefix, kind, deadline) cross-tab to be exactly {(dash, monitor, 1.0), (robo, recall, 3.0), (asst, recall, 2.0)}; a false value means the cell must not be read.

## Arm families present (scorable)

always-cloud-fcfs, attentionstore-prefetch, b7-edf-feasibility, base, cascade-routing, covex-v6-fair-c5attr-rr, covex-v6-fair-final, covex-v6-fair-final-notouch, covex-v6-fair-final-ptg, covex-v6-fair-final-q, covex-v6-fair-final-q2, covex-v6-fair-final-q2m, covex-v6-fair-final-q4, covex-v6-fair-final-q4b, covex-v6-fair-final-q5, covex-v6-fair-final-q5b, covex-v6-fair-final-q5c, covex-v6-fair-final-stateoff, covex-v6-fair-final-unlatch, covex-v6-final, covex-v6-final-nqd, covex-v6-state-final, eco-llm, edf, fair-c5attr, fair-c5attr-gain0, joint-c3, kvflow-prefetch, llf, lmcache, mooncake, querystream-proactive, r3-streaming, rules, shares, shares-r1, shares-r2, simplestream, state, state-uo, state-uo-c5attr, streamscout, v5-rules-old, warm-all-lru

base and rules each cover two raw arm names at different memory: base = hybrid-F-lhreq-noc3 (1x) and covex-v6-base (0.5x); rules = v5-rules-2 (1x) and covex-v6-rules (0.5x).

## _rerun cells kept and the cell each supersedes

- covex-v6-fair-final-stateoff s4 0.5x: supersedes covex-v6-fair-final-stateoff_n16_s4_1200s_h27_3t_kv0.5r_L3_epg_rq30

## 1x _rerun cells AVAILABLE but NOT folded in (would change committed 1x values; user 2d)

These 1x arms have a scorable _rerun cell. The committed 1x frontier is built from the PLAIN
cells, and folding the _rerun in would move those 1x rows, which this task forbids (task 2d:
any 1x value change is a bug). They are listed here for a separate decision, not applied.

- always-cloud-fcfs s5: always-cloud-fcfs_n16_s5_1200s_h27_3t_L3_epg_rq30_rerun
- covex-v6-final s4: covex-v6-final_n16_s4_1200s_h27_3t_L3_epg_rq30_rerun
- covex-v6-state s4: covex-v6-state_n16_s4_1200s_h27_3t_L3_epg_rq30_rerun
- eco-llm s4: eco-llm_n16_s4_1200s_h27_3t_L3_epg_rq30_rerun
- eco-llm s6: eco-llm_n16_s6_1200s_h27_3t_L3_epg_rq30_rerun
- eco-llm s7: eco-llm_n16_s7_1200s_h27_3t_L3_epg_rq30_rerun
- simplestream s4: simplestream_n16_s4_1200s_h27_3t_L3_epg_rq30_rerun
- simplestream s5: simplestream_n16_s5_1200s_h27_3t_L3_epg_rq30_rerun
- simplestream s6: simplestream_n16_s6_1200s_h27_3t_L3_epg_rq30_rerun
- simplestream s7: simplestream_n16_s7_1200s_h27_3t_L3_epg_rq30_rerun
- v5-rules s7: v5-rules_n16_s7_1200s_h27_3t_L3_epg_rq30_rerun

## Cells EXCLUDED as INVALID (header source_agreement.verdict starts with INVALID; never used)

- covex-v6-fair-final-stateoff_n16_s4_1200s_h27_3t_kv0.5r_L3_epg_rq30: INVALID torn_lazy_import

## Cells with no source_agreement key (kept, marked ABSENT)

- always-cloud-fcfs s4 1x
- always-cloud-fcfs s5 1x
- always-cloud-fcfs s6 1x
- always-cloud-fcfs s7 1x
- attentionstore-prefetch s4 1x
- attentionstore-prefetch s5 1x
- attentionstore-prefetch s6 1x
- attentionstore-prefetch s7 1x
- b7-edf-feasibility s4 1x
- b7-edf-feasibility s5 1x
- b7-edf-feasibility s6 1x
- b7-edf-feasibility s7 1x
- cascade-routing s4 1x
- cascade-routing s5 1x
- cascade-routing s6 1x
- cascade-routing s7 1x
- covex-v6-base s4 0.5x
- covex-v6-fair-c5attr s4 1x
- covex-v6-fair-c5attr s5 1x
- covex-v6-fair-c5attr s6 1x
- covex-v6-fair-c5attr s7 1x
- covex-v6-fair-c5attr-gain0 s4 1x
- covex-v6-fair-c5attr-gain0 s5 1x
- covex-v6-fair-c5attr-gain0 s6 1x
- covex-v6-fair-c5attr-gain0 s7 1x
- covex-v6-fair-c5attr-rr s4 1x
- covex-v6-fair-c5attr-rr s5 1x
- covex-v6-fair-c5attr-rr s6 1x
- covex-v6-fair-c5attr-rr s7 1x
- covex-v6-fair-final s4 0.5x
- covex-v6-fair-final s4 1x
- covex-v6-fair-final s5 0.5x
- covex-v6-fair-final s5 1x
- covex-v6-fair-final s6 1x
- covex-v6-fair-final s7 1x
- covex-v6-final s4 1x
- covex-v6-final s5 1x
- covex-v6-final s6 1x
- covex-v6-final s7 1x
- covex-v6-rules s4 0.5x
- covex-v6-state s4 1x
- covex-v6-state s5 1x
- covex-v6-state s6 1x
- covex-v6-state s7 1x
- covex-v6-state-final s4 1x
- covex-v6-state-final s5 1x
- covex-v6-state-final s6 1x
- covex-v6-state-final s7 1x
- covex-v6-state-shares s4 1x
- covex-v6-state-shares s5 1x
- covex-v6-state-shares s6 1x
- covex-v6-state-shares s7 1x
- covex-v6-state-shares-r1 s4 1x
- covex-v6-state-shares-r1 s5 1x
- covex-v6-state-shares-r1 s6 1x
- covex-v6-state-shares-r1 s7 1x
- covex-v6-state-shares-r2 s4 1x
- covex-v6-state-shares-r2 s5 1x
- covex-v6-state-shares-r2 s6 1x
- covex-v6-state-shares-r2 s7 1x
- covex-v6-state-uo s4 1x
- covex-v6-state-uo s5 1x
- covex-v6-state-uo s6 1x
- covex-v6-state-uo s7 1x
- covex-v6-state-uo-c5attr s4 1x
- covex-v6-state-uo-c5attr s5 1x
- covex-v6-state-uo-c5attr s6 1x
- covex-v6-state-uo-c5attr s7 1x
- eco-llm s4 0.5x
- eco-llm s4 1x
- eco-llm s5 1x
- eco-llm s6 1x
- eco-llm s7 1x
- edf s4 1x
- edf s5 1x
- edf s6 1x
- edf s7 1x
- hybrid-F-lhreq s4 1x
- hybrid-F-lhreq s5 1x
- hybrid-F-lhreq s6 1x
- hybrid-F-lhreq s7 1x
- hybrid-F-lhreq-noc3 s4 1x
- hybrid-F-lhreq-noc3 s5 1x
- hybrid-F-lhreq-noc3 s6 1x
- hybrid-F-lhreq-noc3 s7 1x
- kvflow-prefetch s4 1x
- kvflow-prefetch s5 1x
- kvflow-prefetch s6 1x
- kvflow-prefetch s7 1x
- llf s4 0.5x
- llf s4 1x
- llf s5 1x
- llf s6 1x
- llf s7 1x
- lmcache s4 1x
- lmcache s5 1x
- lmcache s6 1x
- lmcache s7 1x
- mooncake s4 0.5x
- mooncake s4 1x
- mooncake s5 1x
- mooncake s6 1x
- mooncake s7 1x
- querystream-proactive s4 1x
- querystream-proactive s5 1x
- querystream-proactive s6 1x
- querystream-proactive s7 1x
- r3-streaming s4 1x
- r3-streaming s5 1x
- simplestream s4 0.5x
- simplestream s4 1x
- simplestream s5 1x
- simplestream s6 1x
- simplestream s7 1x
- streamscout s4 1x
- streamscout s5 1x
- streamscout s6 1x
- streamscout s7 1x
- v5-rules s4 1x
- v5-rules s5 1x
- v5-rules s6 1x
- v5-rules s7 1x
- v5-rules-2 s4 1x
- v5-rules-2 s5 1x
- v5-rules-2 s6 1x
- v5-rules-2 s7 1x
- warm-all-lru s4 1x
- warm-all-lru s5 1x
- warm-all-lru s6 1x
- warm-all-lru s7 1x

## Missing or unparsable cells

- always-cloud-fcfs_n16_s4_1200s_h27_3t_kv0.5_L3_epg_rq30: name did not match the rq30 cell pattern
- always-cloud-fcfs_n16_s5_1200s_h27_3t_L3_epg_rq30: preflight-only stub, absent: cell.json, outcomes.jsonl.gz
- always-cloud-fcfs_n16_s5_1200s_h27_3t_kv0.5_L3_epg_rq30: name did not match the rq30 cell pattern
- attentionstore-prefetch_n16_s4_1200s_h27_3t_kv0.5_L3_epg_rq30: name did not match the rq30 cell pattern
- attentionstore-prefetch_n16_s5_1200s_h27_3t_kv0.5_L3_epg_rq30: name did not match the rq30 cell pattern
- b7-edf-feasibility_n16_s4_1200s_h27_3t_kv0.5_L3_epg_rq30: name did not match the rq30 cell pattern
- b7-edf-feasibility_n16_s5_1200s_h27_3t_kv0.5_L3_epg_rq30: name did not match the rq30 cell pattern
- confidence-cascade_n12_s4_1200s_h27_3t_L3_epg_rq30: name did not match the rq30 cell pattern
- confidence-cascade_n16_s4_1200s_h27_3t_kv0.25_L3_epg_rq30: name did not match the rq30 cell pattern
- confidence-cascade_n16_s4_1200s_h27_3t_kv0.5r_h0.5_L3_epg_rq30: name did not match the rq30 cell pattern
- confidence-cascade_n16_s5_1200s_h27_3t_kv0.5r_h0.5_L3_epg_rq30: name did not match the rq30 cell pattern
- confidence-cascade_n16_s6_1200s_h27_3t_kv0.5r_h0.5_L3_epg_rq30: name did not match the rq30 cell pattern
- confidence-cascade_n16_s7_1200s_h27_3t_kv0.5r_h0.5_L3_epg_rq30: name did not match the rq30 cell pattern
- confidence-cascade_n8_s4_1200s_h27_3t_L3_epg_rq30: name did not match the rq30 cell pattern
- covex-v6-base_n12_s4_1200s_h27_3t_L3_epg_rq30: name did not match the rq30 cell pattern
- covex-v6-base_n12_s5_1200s_h27_3t_L3_epg_rq30: name did not match the rq30 cell pattern
- covex-v6-base_n16_s4_1200s_h27_3t_L2.5_epg_rq30: name did not match the rq30 cell pattern
- covex-v6-base_n16_s4_1200s_h27_3t_kv0.25_L3_epg_rq30: name did not match the rq30 cell pattern
- covex-v6-base_n16_s4_1200s_h27_3t_kv0.5_L3_epg_rq30: name did not match the rq30 cell pattern
- covex-v6-base_n16_s4_1200s_h27_3t_kv0.5r_h0.5_L3_epg_rq30: name did not match the rq30 cell pattern
- covex-v6-base_n16_s5_1200s_h27_3t_L2.5_epg_rq30: name did not match the rq30 cell pattern
- covex-v6-base_n16_s5_1200s_h27_3t_kv0.5_L3_epg_rq30: name did not match the rq30 cell pattern
- covex-v6-base_n16_s5_1200s_h27_3t_kv0.5r_h0.5_L3_epg_rq30: name did not match the rq30 cell pattern
- covex-v6-base_n16_s6_1200s_h27_3t_kv0.5r_h0.5_L3_epg_rq30: name did not match the rq30 cell pattern
- covex-v6-base_n16_s7_1200s_h27_3t_kv0.5r_h0.5_L3_epg_rq30: name did not match the rq30 cell pattern
- covex-v6-base_n20_s4_1200s_h27_3t_L3_epg_rq30: name did not match the rq30 cell pattern
- covex-v6-base_n20_s5_1200s_h27_3t_L3_epg_rq30: name did not match the rq30 cell pattern
- covex-v6-base_n8_s4_1200s_h27_3t_L3_epg_rq30: name did not match the rq30 cell pattern
- covex-v6-fair-final-q2_n16_s4_1200s_h27_3t_kv0.5r_h0.5_L3_epg_rq30: name did not match the rq30 cell pattern
- covex-v6-fair-final-q2m_n16_s4_1200s_h27_3t_kv0.5r_h0.5_L3_epg_rq30: name did not match the rq30 cell pattern
- covex-v6-fair-final-q4_n16_s4_1200s_h27_3t_kv0.5r_h0.5_L3_epg_rq30: name did not match the rq30 cell pattern
- covex-v6-fair-final-q4b_n16_s4_1200s_h27_3t_kv0.5r_h0.5_L3_epg_rq30: name did not match the rq30 cell pattern
- covex-v6-fair-final-q5_n16_s4_1200s_h27_3t_kv0.5r_h0.5_L3_epg_rq30: name did not match the rq30 cell pattern
- covex-v6-fair-final-q5b_n16_s4_1200s_h27_3t_kv0.5r_h0.5_L3_epg_rq30: name did not match the rq30 cell pattern
- covex-v6-fair-final-q5c_n16_s4_1200s_h27_3t_kv0.5r_h0.5_L3_epg_rq30: name did not match the rq30 cell pattern
- covex-v6-fair-final-q_n16_s4_1200s_h27_3t_c3-11-2_L3_epg_rq30: name did not match the rq30 cell pattern
- covex-v6-fair-final-q_n16_s4_1200s_h27_3t_kv0.5r_h0.5_L3_epg_rq30: name did not match the rq30 cell pattern
- covex-v6-fair-final-unlatch_n16_s4_1200s_h27_3t_kv0.5r_h0.5_L3_epg_rq30: name did not match the rq30 cell pattern
- covex-v6-fair-final_n20_s4_1200s_h27_3t_c3-11-2_L3_epg_rq30: name did not match the rq30 cell pattern
- covex-v6-fair-final_n24_s4_1200s_h27_3t_c3-11-2_L3_epg_rq30: name did not match the rq30 cell pattern
- covex-v6-fair-final_n32_s4_1200s_h27_3t_c3-11-2_L3_epg_rq30: name did not match the rq30 cell pattern
- covex-v6-rules_n12_s4_1200s_h27_3t_L3_epg_rq30: name did not match the rq30 cell pattern
- covex-v6-rules_n12_s5_1200s_h27_3t_L3_epg_rq30: name did not match the rq30 cell pattern
- covex-v6-rules_n16_s4_1200s_h27_3t_L2.5_epg_rq30: name did not match the rq30 cell pattern
- covex-v6-rules_n16_s4_1200s_h27_3t_kv0.25_L3_epg_rq30: name did not match the rq30 cell pattern
- covex-v6-rules_n16_s4_1200s_h27_3t_kv0.5_L3_epg_rq30: name did not match the rq30 cell pattern
- covex-v6-rules_n16_s5_1200s_h27_3t_L2.5_epg_rq30: name did not match the rq30 cell pattern
- covex-v6-rules_n16_s5_1200s_h27_3t_kv0.5_L3_epg_rq30: name did not match the rq30 cell pattern
- covex-v6-rules_n20_s4_1200s_h27_3t_L3_epg_rq30: name did not match the rq30 cell pattern
- covex-v6-rules_n20_s5_1200s_h27_3t_L3_epg_rq30: name did not match the rq30 cell pattern
- covex-v6-rules_n8_s4_1200s_h27_3t_L3_epg_rq30: name did not match the rq30 cell pattern
- covex-v6-state_n16_s4_1200s_h27_3t_L3_epg_rq30: preflight-only stub, absent: cell.json, outcomes.jsonl.gz
- covex-v6-state_n16_s6_1200s_h27_3t_L3_epg_rq30: preflight-only stub, absent: outcomes.jsonl.gz
- covex-v6-state_n16_s7_1200s_h27_3t_L3_epg_rq30: preflight-only stub, absent: cell.json, outcomes.jsonl.gz
- eco-llm_n16_s4_1200s_h27_3t_kv0.25_L3_epg_rq30: name did not match the rq30 cell pattern
- eco-llm_n16_s4_1200s_h27_3t_kv0.5r_h0.5_L3_epg_rq30: name did not match the rq30 cell pattern
- eco-llm_n16_s5_1200s_h27_3t_kv0.5r_h0.5_L3_epg_rq30: name did not match the rq30 cell pattern
- eco-llm_n16_s6_1200s_h27_3t_kv0.5r_h0.5_L3_epg_rq30: name did not match the rq30 cell pattern
- eco-llm_n16_s7_1200s_h27_3t_kv0.5r_h0.5_L3_epg_rq30: name did not match the rq30 cell pattern
- eco-llm_n8_s4_1200s_h27_3t_L3_epg_rq30: name did not match the rq30 cell pattern
- edf_n16_s4_1200s_h27_3t_kv0.5_L3_epg_rq30: name did not match the rq30 cell pattern
- edf_n16_s5_1200s_h27_3t_kv0.5_L3_epg_rq30: name did not match the rq30 cell pattern
- llf_n12_s4_1200s_h27_3t_L3_epg_rq30: name did not match the rq30 cell pattern
- llf_n16_s4_1200s_h27_3t_L2.5_epg_rq30: name did not match the rq30 cell pattern
- llf_n16_s4_1200s_h27_3t_kv0.25_L3_epg_rq30: name did not match the rq30 cell pattern
- llf_n16_s4_1200s_h27_3t_kv0.5_L3_epg_rq30: name did not match the rq30 cell pattern
- llf_n16_s4_1200s_h27_3t_kv0.5r_h0.5_L3_epg_rq30: name did not match the rq30 cell pattern
- llf_n16_s5_1200s_h27_3t_kv0.5_L3_epg_rq30: name did not match the rq30 cell pattern
- llf_n16_s5_1200s_h27_3t_kv0.5r_h0.5_L3_epg_rq30: name did not match the rq30 cell pattern
- llf_n16_s6_1200s_h27_3t_kv0.5r_h0.5_L3_epg_rq30: name did not match the rq30 cell pattern
- llf_n16_s7_1200s_h27_3t_kv0.5r_h0.5_L3_epg_rq30: name did not match the rq30 cell pattern
- llf_n8_s4_1200s_h27_3t_L3_epg_rq30: name did not match the rq30 cell pattern
- mooncake_n16_s4_1200s_h27_3t_L2.5_epg_rq30: name did not match the rq30 cell pattern
- mooncake_n16_s4_1200s_h27_3t_kv0.25_L3_epg_rq30: name did not match the rq30 cell pattern
- mooncake_n16_s4_1200s_h27_3t_kv0.5_L3_epg_rq30: name did not match the rq30 cell pattern
- mooncake_n16_s4_1200s_h27_3t_kv0.5r_h0.5_L3_epg_rq30: name did not match the rq30 cell pattern
- mooncake_n16_s5_1200s_h27_3t_kv0.5_L3_epg_rq30: name did not match the rq30 cell pattern
- mooncake_n16_s5_1200s_h27_3t_kv0.5r_h0.5_L3_epg_rq30: name did not match the rq30 cell pattern
- mooncake_n16_s6_1200s_h27_3t_kv0.5r_h0.5_L3_epg_rq30: name did not match the rq30 cell pattern
- mooncake_n16_s7_1200s_h27_3t_kv0.5r_h0.5_L3_epg_rq30: name did not match the rq30 cell pattern
- mooncake_n8_s4_1200s_h27_3t_L3_epg_rq30: name did not match the rq30 cell pattern
- querystream-proactive_n16_s4_1200s_h27_3t_kv0.5_L3_epg_rq30: name did not match the rq30 cell pattern
- querystream-proactive_n16_s5_1200s_h27_3t_kv0.5_L3_epg_rq30: name did not match the rq30 cell pattern
- simplestream_n12_s4_1200s_h27_3t_L3_epg_rq30: name did not match the rq30 cell pattern
- simplestream_n16_s4_1200s_h27_3t_L1.5_epg_rq30: name did not match the rq30 cell pattern
- simplestream_n16_s4_1200s_h27_3t_kv0.25_L3_epg_rq30: name did not match the rq30 cell pattern
- simplestream_n16_s4_1200s_h27_3t_kv0.5_L3_epg_rq30: name did not match the rq30 cell pattern
- simplestream_n16_s4_1200s_h27_3t_kv0.5r_h0.5_L3_epg_rq30: name did not match the rq30 cell pattern
- simplestream_n16_s5_1200s_h27_3t_kv0.5_L3_epg_rq30: name did not match the rq30 cell pattern
- simplestream_n16_s5_1200s_h27_3t_kv0.5r_h0.5_L3_epg_rq30: name did not match the rq30 cell pattern
- simplestream_n16_s6_1200s_h27_3t_kv0.5r_h0.5_L3_epg_rq30: name did not match the rq30 cell pattern
- simplestream_n16_s7_1200s_h27_3t_kv0.5r_h0.5_L3_epg_rq30: name did not match the rq30 cell pattern
- simplestream_n8_s4_1200s_h27_3t_L3_epg_rq30: name did not match the rq30 cell pattern
- v5-rules_n16_s7_1200s_h27_3t_L3_epg_rq30: preflight-only stub, absent: cell.json, outcomes.jsonl.gz
- warm-all-lru_n16_s4_1200s_h27_3t_kv0.5_L3_epg_rq30: name did not match the rq30 cell pattern
- warm-all-lru_n16_s5_1200s_h27_3t_kv0.5_L3_epg_rq30: name did not match the rq30 cell pattern

## Provenance

- runs dir last commit: 56b8d0ae
- scorer score.py last commit: cb9120cc
- d179_rung2_verdict.py last commit: cd580554
- build time is deliberately NOT stamped here: the output is byte-deterministic given the input. The git commit of this file is the build time of record.
- source data: results/orchestration/live2/frozen_test/runs/<cell>/cell.json and outcomes.jsonl.gz; scorers experiments/orchestration/live2/scorer/score.py and experiments/orchestration/live2/d179_rung2_verdict.py
