# D226 (3) rescore: corrected refusal rule, re-derived from committed cells

Scorer id (content hash of score.py + this driver): `score.py:c8de6f8965e2+d226_rescore.py:171f75eb1163`

Re-derivation (no reruns; frozen-grid traces absent on this host). Refusal rule unified with `score.py::refused_request_ids`: http_status != 200, or no status with no prompt/output tokens. An outcome whose standing cloud request is absent from the request log is UNVERIFIABLE and nulled (device stands, else no answer).

- cells rescored: **286**  (skipped 48: seeds 1-3 / no logs)
- cells whose on-time or correct-by-deadline CHANGES under the rule: **98**
- cells where recomputed_old != committed (capture-time scorer mis-scored a PRESENT refusal): **43**
- robot correct-by-deadline count changed: **0** cells
- single-shot correct-by-deadline score changed: **5** cells
- dashcam cells needing an AP (mAP) refresh (monitor on-time set moved): **82**

## On-time changes (per type)

| cell | type | committed | recomputed_old | new | pool_n | null_abs | null_ref |
|---|---|---|---|---|---|---|---|
| always-cloud-fcfs_n16_s4_1200s_h27_3t | dashcam | 10240 | 10240 | 10239 | 13193 | 1 | 0 |
| always-cloud-fcfs_n16_s4_1200s_h27_3t_L3_epg_rq30 | dashcam | 829 | 828 | 828 | 11764 | 0 | 1 |
| always-cloud-fcfs_n16_s6_1200s_h27_3t_L3_epg_rq30 | dashcam | 1421 | 1419 | 1419 | 11786 | 0 | 2 |
| always-cloud-fcfs_n16_s7_1200s_h27_3t_L3_epg_rq30 | dashcam | 959 | 957 | 957 | 11779 | 0 | 2 |
| always-cloud-fcfs_n16_s7_1200s_h27_3t_L3_epg_rq30 | robot | 1 | 0 | 0 | 105 | 0 | 1 |
| attentionstore-prefetch_n16_s4_1200s_h27_3t_L3_epg_rq30 | dashcam | 803 | 802 | 802 | 11764 | 0 | 1 |
| attentionstore-prefetch_n16_s7_1200s_h27_3t_L3_epg_rq30 | dashcam | 932 | 929 | 929 | 11779 | 0 | 3 |
| b7-edf-feasibility_n16_s0_1200s_h27_3t | dashcam | 11064 | 11063 | 11063 | 13242 | 0 | 1 |
| b7-edf-feasibility_n16_s0_1200s_h27_3t | robot | 17 | 17 | 16 | 24 | 1 | 0 |
| b7-edf-feasibility_n16_s0_1200s_h27_3t_rerun | robot | 17 | 17 | 16 | 24 | 1 | 0 |
| b7-edf-feasibility_n16_s4_1200s_h27_3t_L3 | dashcam | 12468 | 12467 | 12465 | 13193 | 2 | 1 |
| b7-edf-feasibility_n16_s4_1200s_h27_3t_L3_epg | dashcam | 10168 | 10168 | 10167 | 11764 | 1 | 0 |
| b7-edf-feasibility_n16_s4_1200s_h27_3t_L3_epg_rq30 | dashcam | 816 | 814 | 814 | 11764 | 0 | 2 |
| b7-edf-feasibility_n16_s5_1200s_h27_3t_L3_epg | dashcam | 9201 | 9201 | 9198 | 11769 | 3 | 0 |
| b7-edf-feasibility_n16_s6_1200s_h27_3t | dashcam | 11633 | 11633 | 11632 | 13214 | 1 | 0 |
| b7-edf-feasibility_n16_s6_1200s_h27_3t_L3_epg | dashcam | 10553 | 10552 | 10552 | 11786 | 0 | 1 |
| cascade-routing_n16_s5_1200s_h27_3t_L3_epg_rq30 | dashcam | 11630 | 11630 | 11629 | 11769 | 1 | 0 |
| cascade-routing_n16_s6_1200s_h27_3t_L3_epg_rq30 | dashcam | 11741 | 11741 | 11740 | 11786 | 1 | 0 |
| covex-v6-base_n12_s4_1200s_h27_3t_L3_epg_rq30 | dashcam | 8646 | 8646 | 8645 | 9826 | 1 | 0 |
| covex-v6-base_n16_s5_1200s_h27_3t_L2.5_epg_rq30 | dashcam | 6642 | 6642 | 6641 | 11769 | 1 | 0 |
| covex-v6-fair-c5attr-gain0_n16_s6_1200s_h27_3t_L3_epg_rq30 | dashcam | 3401 | 3401 | 3400 | 11786 | 1 | 0 |
| covex-v6-fair-c5attr-rr_n16_s4_1200s_h27_3t_L3_epg_rq30 | dashcam | 8463 | 8463 | 8462 | 11764 | 1 | 0 |
| covex-v6-fair-c5attr_n16_s4_1200s_h27_3t_L3_epg_rq30 | dashcam | 5969 | 5969 | 5967 | 11764 | 2 | 0 |
| covex-v6-fair-c5attr_n16_s7_1200s_h27_3t_L3_epg_rq30 | ss | 354 | 354 | 353 | 359 | 1 | 0 |
| covex-v6-fair-final_n16_s5_1200s_h27_3t_L3_epg_rq30 | dashcam | 8311 | 8311 | 8310 | 11769 | 1 | 0 |
| covex-v6-final_n16_s4_1200s_h27_3t_L3_epg_rq30 | ss | 354 | 354 | 353 | 357 | 1 | 0 |
| covex-v6-rules_n12_s4_1200s_h27_3t_L3_epg_rq30 | dashcam | 5613 | 5613 | 5611 | 9826 | 2 | 0 |
| covex-v6-state-final_n16_s4_1200s_h27_3t_L3_epg_rq30 | ss | 339 | 339 | 338 | 357 | 1 | 0 |
| covex-v6-state-shares-r1_n16_s4_1200s_h27_3t_L3_epg_rq30 | dashcam | 9119 | 9119 | 9117 | 11764 | 2 | 0 |
| covex-v6-state-shares-r1_n16_s5_1200s_h27_3t_L3_epg_rq30 | dashcam | 8774 | 8774 | 8773 | 11769 | 1 | 0 |
| covex-v6-state-shares_n16_s4_1200s_h27_3t_L3_epg_rq30 | ss | 344 | 344 | 343 | 357 | 1 | 0 |
| covex-v6-state-uo-c5attr_n16_s6_1200s_h27_3t_L3_epg_rq30 | dashcam | 3904 | 3904 | 3903 | 11786 | 1 | 0 |
| eco-llm_n14_s0_1200s_h27_3t | dashcam | 11151 | 11151 | 11150 | 13242 | 1 | 0 |
| eco-llm_n14_s0_1200s_h27_3t | robot | 12 | 11 | 11 | 15 | 0 | 1 |
| eco-llm_n14_s0_1200s_h27_3t_rerun | robot | 12 | 11 | 11 | 15 | 0 | 1 |
| eco-llm_n16_s0_1200s_h27_3t | robot | 17 | 16 | 15 | 24 | 1 | 1 |
| eco-llm_n16_s0_1200s_h27_3t_postfix | robot | 22 | 22 | 21 | 24 | 1 | 0 |
| eco-llm_n16_s0_1200s_h27_3t_rerun | robot | 16 | 15 | 14 | 24 | 1 | 1 |
| eco-llm_n16_s4_1200s_h27_3t | dashcam | 10245 | 10245 | 10244 | 13193 | 1 | 0 |
| eco-llm_n16_s4_1200s_h27_3t_L3 | dashcam | 12461 | 12460 | 12458 | 13193 | 2 | 1 |
| eco-llm_n16_s4_1200s_h27_3t_L3_epg | dashcam | 10151 | 10150 | 10149 | 11764 | 1 | 1 |
| eco-llm_n16_s4_1200s_h27_3t_postfix | dashcam | 11839 | 11839 | 11837 | 13193 | 2 | 0 |
| eco-llm_n16_s5_1200s_h27_3t_L3_epg | dashcam | 9094 | 9094 | 9093 | 11769 | 1 | 0 |
| eco-llm_n16_s5_1200s_h27_3t_postfix | dashcam | 10794 | 10794 | 10793 | 13200 | 1 | 0 |
| eco-llm_n16_s6_1200s_h27_3t | dashcam | 10264 | 10263 | 10263 | 13214 | 0 | 1 |
| edf_n16_s4_1200s_h27_3t_L3 | dashcam | 11962 | 11962 | 11961 | 13193 | 1 | 0 |
| edf_n16_s5_1200s_h27_3t | dashcam | 11623 | 11623 | 11620 | 13200 | 3 | 0 |
| edf_n16_s5_1200s_h27_3t | ss | 260 | 283 | 283 | 356 | 0 | 0 |
| edf_n16_s6_1200s_h27_3t | dashcam | 11946 | 11946 | 11945 | 13214 | 1 | 0 |
| edf_n16_s6_1200s_h27_3t_L3_epg_rq30 | dashcam | 3021 | 3021 | 3020 | 11786 | 1 | 0 |
| hybrid-F-lhreq-noc3_n16_s4_1200s_h27_3t_L3_epg | dashcam | 8110 | 8109 | 8109 | 11764 | 0 | 1 |
| hybrid-F-lhreq-noc3_n16_s7_1200s_h27_3t_L3_epg_rq30 | dashcam | 7513 | 7513 | 7509 | 11779 | 4 | 0 |
| hybrid-F-lhreq_n16_s0_1200s_h27_3t | robot | 18 | 17 | 17 | 24 | 0 | 1 |
| hybrid-F-lhreq_n16_s0_1200s_h27_3t_rerun | robot | 18 | 17 | 17 | 24 | 0 | 1 |
| hybrid-F-lhreq_n16_s4_1200s_h27_3t | dashcam | 10620 | 10620 | 10618 | 13193 | 2 | 0 |
| hybrid-F-lhreq_n16_s4_1200s_h27_3t_L3_epg | dashcam | 8450 | 8449 | 8446 | 11764 | 3 | 1 |
| hybrid-F-lhreq_n16_s4_1200s_h27_3t_postfix | dashcam | 11815 | 11815 | 11814 | 13193 | 1 | 0 |
| hybrid-F-lhreq_n16_s5_1200s_h27_3t_L3_epg | dashcam | 7483 | 7483 | 7482 | 11769 | 1 | 0 |
| hybrid-F-lhreq_n16_s6_1200s_h27_3t_postfix | dashcam | 11839 | 11838 | 11838 | 13214 | 0 | 1 |
| hybrid-F6-lhreq_n16_s0_1200s_h27_3t | robot | 17 | 16 | 15 | 24 | 1 | 1 |
| hybrid-F6-lhreq_n16_s0_1200s_h27_3t_rerun | robot | 18 | 17 | 17 | 24 | 0 | 1 |
| hybrid-F6-lhreq_n16_s6_1200s_h27_3t | dashcam | 10259 | 10259 | 10258 | 13214 | 1 | 0 |
| llf_n16_s4_1200s_h27_3t_L2.5_epg_rq30 | dashcam | 8108 | 8108 | 8107 | 11764 | 1 | 0 |
| llf_n16_s4_1200s_h27_3t_L3 | dashcam | 12692 | 12691 | 12690 | 13193 | 1 | 1 |
| llf_n16_s4_1200s_h27_3t_L3_epg | dashcam | 9372 | 9372 | 9371 | 11764 | 1 | 0 |
| llf_n16_s5_1200s_h27_3t | dashcam | 12176 | 12176 | 12174 | 13200 | 2 | 0 |
| llf_n16_s5_1200s_h27_3t | ss | 300 | 320 | 320 | 356 | 0 | 0 |
| llf_n16_s5_1200s_h27_3t_L3_epg_rq30 | dashcam | 7774 | 7774 | 7773 | 11769 | 1 | 0 |
| mooncake_n16_s0_1200s_h27_3t | robot | 17 | 17 | 16 | 24 | 1 | 0 |
| mooncake_n16_s4_1200s_h27_3t | dashcam | 11819 | 11819 | 11817 | 13193 | 2 | 0 |
| mooncake_n16_s4_1200s_h27_3t_L3 | dashcam | 12473 | 12473 | 12471 | 13193 | 2 | 0 |
| mooncake_n16_s4_1200s_h27_3t_L3_epg | dashcam | 9716 | 9716 | 9715 | 11764 | 1 | 0 |
| mooncake_n16_s4_1200s_h27_3t_L3_epg_rq30 | dashcam | 806 | 805 | 805 | 11764 | 0 | 1 |
| mooncake_n16_s5_1200s_h27_3t_L3_epg | dashcam | 9147 | 9146 | 9145 | 11769 | 1 | 1 |
| mooncake_n16_s5_1200s_h27_3t_L3_epg_rq30 | dashcam | 673 | 671 | 671 | 11769 | 0 | 2 |
| mooncake_n16_s6_1200s_h27_3t | dashcam | 11599 | 11598 | 11597 | 13214 | 1 | 1 |
| mooncake_n16_s6_1200s_h27_3t_L3_epg_rq30 | dashcam | 4835 | 4834 | 4834 | 11786 | 0 | 1 |
| mooncake_n16_s7_1200s_h27_3t_L3_epg_rq30 | dashcam | 9276 | 9276 | 9274 | 11779 | 2 | 0 |
| querystream-proactive_n16_s5_1200s_h27_3t_L3_epg | dashcam | 2205 | 2203 | 2203 | 11769 | 0 | 2 |
| querystream-proactive_n16_s6_1200s_h27_3t_L3_epg_rq30 | dashcam | 1434 | 1433 | 1433 | 11786 | 0 | 1 |
| querystream-proactive_n16_s7_1200s_h27_3t_L3_epg_rq30 | dashcam | 970 | 969 | 969 | 11779 | 0 | 1 |
| simplestream_n16_s4_1200s_h27_3t_L3_epg_rq30 | dashcam | 10840 | 10840 | 10837 | 11764 | 3 | 0 |
| simplestream_n16_s4_1200s_h27_3t_kv0.5_L3_epg_rq30 | dashcam | 10866 | 10866 | 10865 | 11764 | 1 | 0 |
| simplestream_n16_s5_1200s_h27_3t_L3_epg | dashcam | 10722 | 10721 | 10719 | 11769 | 2 | 1 |
| simplestream_n16_s5_1200s_h27_3t_L3_epg_rq30 | dashcam | 10382 | 10382 | 10379 | 11769 | 3 | 0 |
| simplestream_n16_s5_1200s_h27_3t_kv0.5_L3_epg_rq30 | dashcam | 10318 | 10318 | 10315 | 11769 | 3 | 1 |
| streamscout_n16_s4_1200s_h27_3t_L3_epg_rq30 | ss | 357 | 357 | 356 | 357 | 1 | 0 |
| streamscout_n16_s5_1200s_h27_3t_L3_epg_rq30 | dashcam | 8388 | 8388 | 8386 | 11769 | 2 | 0 |
| streamscout_n16_s7_1200s_h27_3t_L3_epg_rq30 | dashcam | 9630 | 9630 | 9628 | 11779 | 2 | 0 |
| v5-rules_n16_s7_1200s_h27_3t_L3_epg_rq30_rerun | ss | 215 | 214 | 214 | 359 | 0 | 1 |
| warm-all-lru-off_n16_s4_1200s_h27_3t_L3_epg | dashcam | 10153 | 10153 | 10152 | 11764 | 1 | 0 |
| warm-all-lru-reactive_n12_s4_1200s_h27_3t_L3_epg_ls12 | dashcam | 9770 | 9770 | 9769 | 9826 | 1 | 0 |
| warm-all-lru-reactive_n16_s4_1200s_h27_3t_L3_cal1f | dashcam | 12984 | 12984 | 12982 | 13193 | 2 | 0 |
| warm-all-lru-reactive_n16_s4_1200s_h27_3t_L3_epg | dashcam | 10656 | 10656 | 10655 | 11764 | 1 | 0 |
| warm-all-lru-reactive_n16_s4_1200s_h27_3t_L3_epg_ls16 | dashcam | 10770 | 10770 | 10769 | 11764 | 1 | 0 |
| warm-all-lru-reactive_n16_s5_1200s_h27_3t_L3_epg_ls16 | dashcam | 10392 | 10390 | 10388 | 11769 | 2 | 2 |
| warm-all-lru-reactive_n8_s4_1200s_h27_3t_L3_epg_ls08 | dashcam | 5865 | 5865 | 5864 | 5869 | 1 | 0 |
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
| covex-v6-final_n16_s4_1200s_h27_3t_L3_epg_rq30 | 1.0 | 2.0 | opp0012248 |
| covex-v6-state-final_n16_s4_1200s_h27_3t_L3_epg_rq30 | 9.0 | 10.0 | opp0012248 |
| covex-v6-state-shares_n16_s4_1200s_h27_3t_L3_epg_rq30 | 6.0 | 7.0 | opp0012248 |
| streamscout_n16_s4_1200s_h27_3t_L3_epg_rq30 | 0.0 | 1.0 | opp0012248 |
| v5-rules_n16_s7_1200s_h27_3t_L3_epg_rq30_rerun | 72.0 | 73.0 | opp0010435 |
