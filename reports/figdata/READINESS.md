# Figure-data readiness (StudyFIGDATA, D214)

Pipeline sha (D209 canonical scorer): `b5264100`. Generated 2026-11-23. Tables in `reports/figdata/`. NO FIGURES until the user says plot.

## Arm coverage (standard grid: 1x memory, 16 devices, robot deadline 3.0 s, rq30)

| arm | policy_version | rung | seeds present | status |
|---|---|---|---|---|
| fair-c5attr-rr | development-best | rung3 | [4, 5, 6, 7] | provisional |
| fair-c5attr | development | rung3 | [4, 5, 6, 7] | provisional |
| state-uo-c5attr | development | rung2 | [4, 5, 6, 7] | provisional |
| base | development | rung0 | [4, 5, 6, 7] | provisional |
| rules | development | rung1 | [4, 5, 6, 7] | provisional |
| edf | baseline | - | [4, 5, 6, 7] | valid |
| llf | baseline | - | [4, 5, 6, 7] | valid |
| b7-edf-feasibility | baseline | - | [4, 5, 6, 7] | valid |
| always-cloud-fcfs | baseline | - | [4, 5, 6, 7] | valid |
| simplestream | baseline | - | [4, 5, 6, 7] | valid |
| querystream-proactive | baseline | - | [4, 5, 6, 7] | valid |
| mooncake | baseline | - | [4, 5, 6, 7] | valid |
| attentionstore-prefetch | baseline | - | [4, 5, 6, 7] | valid |
| warm-all-lru | baseline | - | [4, 5, 6, 7] | valid |
| hybrid-F-lhreq | baseline | - | [4, 5, 6, 7] | valid |
| v5-rules | baseline | - | [4, 5, 6, 7] | valid |
| lmcache | baseline | - | [4, 5, 6, 7] | valid |
| streamscout | baseline | - | [4, 5, 6, 7] | valid |
| eco-llm | baseline | - | [4, 5, 6, 7] | valid |
| kvflow-prefetch (port-limited) | baseline | - | [4, 5, 6, 7] | valid |
| device-only | baseline | - | [4, 5, 6, 7] | valid |

## Gaps until reruns land

- **cascade-routing**: no scored cell yet (H100 filler, D212); when it lands it is the device-only-floor baseline (its sufficiency proxy cannot fire here)
- **confidence-cascade**: superseded cells (D205 constant-0.0 reader); gap until the D205 rerun lands
- **final ladder** (covex-v6-state-final / -fair-final / -final): not present; when cells land they are added as policy_version=final and the development rows are kept as status=superseded-by-final. Producer: H100 (flash gates the list).

## Condition coverage (F8-F12)

- F8 memory: present ['0.25x', '0.5x'] (targets 0.25x, 0.5x).
- F9 fleet: present [12]; capacity (largest fleet meeting all three D178 targets) needs a fleet sweep, column left blank until it lands. Producer: flash/H100.
- F10 deadline: present ['2.5'] (target 2.5 s).
- F11 composition/reask: present NONE beyond rq30 / 40:40:20.
- F12 network: present NONE (no network-condition cells exist).

## Network / uplink operating point (corrected label, user 2026-11-23)

The standard-grid cells DO apply the committed D75 link model (fleet/links.py, applied in fleet/emulator.py: deliver_s = RTT/2 + payload/downlink on every answer; upload_s = bytes*8/uplink + RTT/2 on every frame). header.json does not record the link, so cond_network is established from the OUTCOME TIMESTAMPS, not the header: every delivered cloud answer has t_delivered - t_cloud_done = 0.02218 s (RTT/2 + payload at 13.6 Mbit/s), and each dashcam frame carries 27 to 229 ms uplink (median ~60 ms = RTT/2 + JPEG bytes at 13.6 Mbit/s).

- cond_network for every link-verified standard-grid cell: "uniform 13.6 Mbit/s / 44 ms RTT (best-performing US carrier's 5G median, Ookla H2 2025)".
- Tier-1 uplink values are the committed StudyE1 sweep: 5 / 12 / 13.6 / 25 / 88 Mbit/s and RTT 22 / 44 / 142 ms, each with its cited uplink source; never the Irish 5G downlink percentiles.
- Per-arm verification (one standard cell per arm; an arm's rows are relabelled only if its 22.2 ms downlink signature holds):

| arm | cell | seed | downlink median (s) | n answers | verified |
|---|---|---|---|---|---|
| always-cloud-fcfs | results/orchestration/live2/frozen_test/runs/always-cloud-fcfs_n16_s4_1200s_h27_3t_L3_epg_rq30 | 4 | 0.02218 | 8175 | yes |
| attentionstore-prefetch | results/orchestration/live2/frozen_test/runs/attentionstore-prefetch_n16_s4_1200s_h27_3t_L3_epg_rq30 | 4 | 0.02218 | 7752 | yes |
| b7-edf-feasibility | results/orchestration/live2/frozen_test/runs/b7-edf-feasibility_n16_s4_1200s_h27_3t_L3_epg_rq30 | 4 | 0.02218 | 8175 | yes |
| base | results/orchestration/live2/frozen_test/runs/hybrid-F-lhreq-noc3_n16_s4_1200s_h27_3t_L3_epg_rq30 | 4 | 0.02218 | 10153 | yes |
| covex-v6-fair-final | results/orchestration/live2/frozen_test/runs/covex-v6-fair-final_n16_s4_1200s_h27_3t_L3_epg_rq30 | 4 | 0.02218 | 9370 | yes |
| covex-v6-state-final | results/orchestration/live2/frozen_test/runs/covex-v6-state-final_n16_s4_1200s_h27_3t_L3_epg_rq30 | 4 | 0.02218 | 9317 | yes |
| device-only | results/orchestration/live2/frozen_test/runs/hybrid-F-lhreq-noc3_n16_s4_1200s_h27_3t_L3_epg_rq30 | 4 | 0.02218 | 10153 | yes |
| eco-llm | results/orchestration/live2/frozen_test/runs/eco-llm_n16_s4_1200s_h27_3t_L3_epg_rq30 | 4 | 0.02218 | 8562 | yes |
| edf | results/orchestration/live2/frozen_test/runs/edf_n16_s4_1200s_h27_3t_L3_epg_rq30 | 4 | 0.02218 | 7839 | yes |
| fair-c5attr | results/orchestration/live2/frozen_test/runs/covex-v6-fair-c5attr_n16_s4_1200s_h27_3t_L3_epg_rq30 | 4 | 0.02218 | 8844 | yes |
| fair-c5attr-rr | results/orchestration/live2/frozen_test/runs/covex-v6-fair-c5attr-rr_n16_s4_1200s_h27_3t_L3_epg_rq30 | 4 | 0.02218 | 9412 | yes |
| hybrid-F-lhreq | results/orchestration/live2/frozen_test/runs/hybrid-F-lhreq_n16_s4_1200s_h27_3t_L3_epg_rq30 | 4 | 0.02218 | 9913 | yes |
| kvflow-prefetch | results/orchestration/live2/frozen_test/runs/kvflow-prefetch_n16_s4_1200s_h27_3t_L3_epg_rq30 | 4 | 0.02218 | 8597 | yes |
| llf | results/orchestration/live2/frozen_test/runs/llf_n16_s4_1200s_h27_3t_L3_epg_rq30 | 4 | 0.02218 | 10167 | yes |
| lmcache | results/orchestration/live2/frozen_test/runs/lmcache_n16_s4_1200s_h27_3t_L3_epg_rq30 | 4 | 0.02218 | 7460 | yes |
| mooncake | results/orchestration/live2/frozen_test/runs/mooncake_n16_s4_1200s_h27_3t_L3_epg_rq30 | 4 | 0.02218 | 8298 | yes |
| querystream-proactive | results/orchestration/live2/frozen_test/runs/querystream-proactive_n16_s4_1200s_h27_3t_L3_epg_rq30 | 4 | 0.02218 | 7429 | yes |
| rules | results/orchestration/live2/frozen_test/runs/v5-rules-2_n16_s4_1200s_h27_3t_L3_epg_rq30 | 4 | 0.02218 | 5276 | yes |
| simplestream | results/orchestration/live2/frozen_test/runs/simplestream_n16_s4_1200s_h27_3t_L3_epg_rq30 | 4 | 0.02218 | 12247 | yes |
| state-uo-c5attr | results/orchestration/live2/frozen_test/runs/covex-v6-state-uo-c5attr_n16_s4_1200s_h27_3t_L3_epg_rq30 | 4 | 0.02218 | 9511 | yes |
| streamscout | results/orchestration/live2/frozen_test/runs/streamscout_n16_s4_1200s_h27_3t_L3_epg_rq30 | 4 | 0.02218 | 12244 | yes |
| v5-rules | results/orchestration/live2/frozen_test/runs/v5-rules_n16_s4_1200s_h27_3t_L3_epg_rq30 | 4 | 0.02218 | 3742 | yes |
| warm-all-lru | results/orchestration/live2/frozen_test/runs/warm-all-lru_n16_s4_1200s_h27_3t_L3_epg_rq30 | 4 | 0.02218 | 8129 | yes |

## Instrumentation gaps by field

- **F3 latency stamps**: request.jsonl records t_submit, t_first_token, t_done only, so only two composite stamps exist (queue+prefill, decode). ABSENT: upload, coordinator hold, engine queue (separate), return hop. Producer: the live runner (flash/H100) would need to emit them.
- **F13 GPU busy**: present (coordinator_result.budget_spent_gpu_s). Uncached-token charge (D174) and output tokens present from request.jsonl.
- **F14 dry decision latency** at 16/24/32/48 devices: ABSENT (live p50/p99 present). Producer: flash dry sweep.
- **F6 series**: KV pool (residency.jsonl), host load, decisions, late alerts present on the candidate cells; the series are read at plot time, not dumped here.
- **F7 counterfactual decisions**: ABSENT (covex-v6-cf* not in the figure arm set, D210; dry cells on flash).
- **F15/F16**: pointer rows only; the history-matters and cold-vs-warm series live in StudyEARLY1 / phase1 cost profiling and are transcribed on request.
- **F17**: placeholder, no real-deployment data exists.
- **dashcam delivered-stream mAP cross-fitted ALL**: present.

## Table row counts

- F1: 115 rows
- F2: 276 rows
- F3: 1078264 rows
- F4: 1408 rows
- F6: 16 rows
- F7: 0 rows
- F8: 30 rows
- F9: 3 rows
- F10: 5 rows
- F11: 0 rows
- F12: 0 rows
- F13: 122 rows
- F14: 122 rows
- F15: 1 rows
- F16: 1 rows
- F17: 0 rows
- F1_units: 43899 rows
