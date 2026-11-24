# D226 (3) rescore: corrected refusal rule, re-derived from committed cells

Scorer id (content hash of score.py + this driver): `score.py:2d8cc8f034d1+d226_rescore.py:766677949203`

Re-derivation (no reruns; frozen-grid traces absent on this host). Refusal rule unified with `score.py::refused_request_ids`: http_status != 200, or no status with no prompt/output tokens. A ROWLESS cloud answer (request id with no request-log row, D226 (3) user rule) is classified from the outcome: a real delivered answer (parsed A-E letter, cloud score/p_yes, or compute time beyond the ~17 ms D175 refusal signature) is KEPT as delivered; the refusal signature is nulled; undetermined stays fail-loud in score.py and is nulled-and-flagged here.

- cells rescored: **288**  (skipped 49: seeds 1-3 / no logs)
- rowless cloud answers: **delivered 1993, refused 0, undetermined 0** (across 115 cells)
- cells whose on-time or correct-by-deadline CHANGES under the rule: **43**
- cells where recomputed_old != committed (capture-time scorer mis-scored a PRESENT refusal): **43**
- robot correct-by-deadline count changed: **0** cells
- single-shot correct-by-deadline score changed: **1** cells
- dashcam cells needing an AP (mAP) refresh (monitor on-time set moved): **32**

## On-time changes (per type)

| cell | type | committed | recomputed_old | new | pool_n | null_rowless | null_ref |
|---|---|---|---|---|---|---|---|
| always-cloud-fcfs_n16_s4_1200s_h27_3t_L3_epg_rq30 | dashcam | 829 | 828 | 828 | 11764 | 0 | 1 |
| always-cloud-fcfs_n16_s6_1200s_h27_3t_L3_epg_rq30 | dashcam | 1421 | 1419 | 1419 | 11786 | 0 | 2 |
| always-cloud-fcfs_n16_s7_1200s_h27_3t_L3_epg_rq30 | dashcam | 959 | 957 | 957 | 11779 | 0 | 2 |
| always-cloud-fcfs_n16_s7_1200s_h27_3t_L3_epg_rq30 | robot | 1 | 0 | 0 | 105 | 0 | 1 |
| attentionstore-prefetch_n16_s4_1200s_h27_3t_L3_epg_rq30 | dashcam | 803 | 802 | 802 | 11764 | 0 | 1 |
| attentionstore-prefetch_n16_s7_1200s_h27_3t_L3_epg_rq30 | dashcam | 932 | 929 | 929 | 11779 | 0 | 3 |
| b7-edf-feasibility_n16_s0_1200s_h27_3t | dashcam | 11064 | 11063 | 11063 | 13242 | 0 | 1 |
| b7-edf-feasibility_n16_s4_1200s_h27_3t_L3 | dashcam | 12468 | 12467 | 12467 | 13193 | 0 | 1 |
| b7-edf-feasibility_n16_s4_1200s_h27_3t_L3_epg_rq30 | dashcam | 816 | 814 | 814 | 11764 | 0 | 2 |
| b7-edf-feasibility_n16_s6_1200s_h27_3t_L3_epg | dashcam | 10553 | 10552 | 10552 | 11786 | 0 | 1 |
| eco-llm_n14_s0_1200s_h27_3t | robot | 12 | 11 | 11 | 15 | 0 | 1 |
| eco-llm_n14_s0_1200s_h27_3t_rerun | robot | 12 | 11 | 11 | 15 | 0 | 1 |
| eco-llm_n16_s0_1200s_h27_3t | robot | 17 | 16 | 16 | 24 | 0 | 1 |
| eco-llm_n16_s0_1200s_h27_3t_rerun | robot | 16 | 15 | 15 | 24 | 0 | 1 |
| eco-llm_n16_s4_1200s_h27_3t_L3 | dashcam | 12461 | 12460 | 12460 | 13193 | 0 | 1 |
| eco-llm_n16_s4_1200s_h27_3t_L3_epg | dashcam | 10151 | 10150 | 10150 | 11764 | 0 | 1 |
| eco-llm_n16_s6_1200s_h27_3t | dashcam | 10264 | 10263 | 10263 | 13214 | 0 | 1 |
| edf_n16_s5_1200s_h27_3t | ss | 260 | 283 | 283 | 356 | 0 | 0 |
| hybrid-F-lhreq-noc3_n16_s4_1200s_h27_3t_L3_epg | dashcam | 8110 | 8109 | 8109 | 11764 | 0 | 1 |
| hybrid-F-lhreq_n16_s0_1200s_h27_3t | robot | 18 | 17 | 17 | 24 | 0 | 1 |
| hybrid-F-lhreq_n16_s0_1200s_h27_3t_rerun | robot | 18 | 17 | 17 | 24 | 0 | 1 |
| hybrid-F-lhreq_n16_s4_1200s_h27_3t_L3_epg | dashcam | 8450 | 8449 | 8449 | 11764 | 0 | 1 |
| hybrid-F-lhreq_n16_s6_1200s_h27_3t_postfix | dashcam | 11839 | 11838 | 11838 | 13214 | 0 | 1 |
| hybrid-F6-lhreq_n16_s0_1200s_h27_3t | robot | 17 | 16 | 16 | 24 | 0 | 1 |
| hybrid-F6-lhreq_n16_s0_1200s_h27_3t_rerun | robot | 18 | 17 | 17 | 24 | 0 | 1 |
| llf_n16_s4_1200s_h27_3t_L3 | dashcam | 12692 | 12691 | 12691 | 13193 | 0 | 1 |
| llf_n16_s5_1200s_h27_3t | ss | 300 | 320 | 320 | 356 | 0 | 0 |
| mooncake_n16_s4_1200s_h27_3t_L3_epg_rq30 | dashcam | 806 | 805 | 805 | 11764 | 0 | 1 |
| mooncake_n16_s5_1200s_h27_3t_L3_epg | dashcam | 9147 | 9146 | 9146 | 11769 | 0 | 1 |
| mooncake_n16_s5_1200s_h27_3t_L3_epg_rq30 | dashcam | 673 | 671 | 671 | 11769 | 0 | 2 |
| mooncake_n16_s6_1200s_h27_3t | dashcam | 11599 | 11598 | 11598 | 13214 | 0 | 1 |
| mooncake_n16_s6_1200s_h27_3t_L3_epg_rq30 | dashcam | 4835 | 4834 | 4834 | 11786 | 0 | 1 |
| querystream-proactive_n16_s5_1200s_h27_3t_L3_epg | dashcam | 2205 | 2203 | 2203 | 11769 | 0 | 2 |
| querystream-proactive_n16_s6_1200s_h27_3t_L3_epg_rq30 | dashcam | 1434 | 1433 | 1433 | 11786 | 0 | 1 |
| querystream-proactive_n16_s7_1200s_h27_3t_L3_epg_rq30 | dashcam | 970 | 969 | 969 | 11779 | 0 | 1 |
| simplestream_n16_s5_1200s_h27_3t_L3_epg | dashcam | 10722 | 10721 | 10721 | 11769 | 0 | 1 |
| v5-rules_n16_s7_1200s_h27_3t_L3_epg_rq30_rerun | ss | 215 | 214 | 214 | 359 | 0 | 1 |
| warm-all-lru-reactive_n16_s5_1200s_h27_3t_L3_epg_ls16 | dashcam | 10392 | 10390 | 10390 | 11769 | 0 | 2 |
| warm-all-lru_n16_s4_1200s_h27_3t_L3_cal1f_rf | dashcam | 361 | 360 | 360 | 13193 | 0 | 1 |
| warm-all-lru_n16_s4_1200s_h27_3t_L3_epg | dashcam | 699 | 698 | 698 | 11764 | 0 | 1 |
| warm-all-lru_n16_s4_1200s_h27_3t_L3_epg_rf | dashcam | 858 | 857 | 857 | 11764 | 0 | 1 |
| warm-all-lru_n16_s4_1200s_h27_3t_L3_epg_rq30 | dashcam | 584 | 582 | 582 | 11764 | 0 | 2 |
| warm-all-lru_n16_s5_1200s_h27_3t_L3_epg_rerun | dashcam | 589 | 588 | 588 | 11769 | 0 | 1 |
| warm-all-lru_n16_s6_1200s_h27_3t_L3_epg_rq30 | dashcam | 914 | 913 | 913 | 11786 | 0 | 1 |

## Robot correct-by-deadline changes

(none - no robot correct-by-deadline count moved)

## Single-shot correct-by-deadline changes

| cell | old_score | new_score | flipped_opps |
|---|---|---|---|
| v5-rules_n16_s7_1200s_h27_3t_L3_epg_rq30_rerun | 72.0 | 73.0 | opp0010435 |
