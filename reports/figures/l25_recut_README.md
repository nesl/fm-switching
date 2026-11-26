# L2.5 vs 3 s twin: robot correct-by-deadline change decomposition

One row per _L2.5_epg_rq30 cell with a committed _L3_epg_rq30 twin (same arm, seed, n). Offline, read-only, CPU only. Seeds 4 to 7.

## What is counted and how

device_answers_in_2p5_3p0: robot device answers whose measured WARM latency per question (device_latency_s in the committed robot_rows, Orin WARM table orin_rec_warm) is in [2.5, 3.0) s. These are the device answers that are on time at the 3 s deadline but late at 2.5 s, so they are the only device answers a deadline re-cut can flip; the device answers are identical across the two cells (device latency is per question, not per arm).

The robot correct-by-deadline (CBD) count is the committed rule: the cloud answer if delivered within the deadline, else the device answer if it also arrives within the deadline, else a miss. Per-question answers, correctness and WARM device latency are read from cell.json robot_rows; re-scoring at a different deadline reuses those answers with the committed cloud delivery rule (D146 completion rebasing). The re-cut at 3 s reproduces the twin's committed per-question CBD exactly (positive_control_at_3s_pass); a cell that fails is dropped and listed under notes, never reported.

## The split

- total_change = CBD(L2.5 cell at 2.5) - CBD(twin at 3.0).
- a_scoring_recut = CBD(twin re-scored at 2.5) - CBD(twin at 3.0): the part offline re-scoring captures, holding the arm's answers fixed. a_recut_device_part re-cuts only the device side (cloud on-time status held at 3 s); a_recut_cloud_part is the remainder of the re-cut, the twin's own cloud deliveries re-cut at 2.5.
- b_arm_decisions = CBD(L2.5 cell at 2.5) - CBD(twin re-scored at 2.5): the remainder, which is what the arm did differently under the tighter deadline. a_scoring_recut + b_arm_decisions == total_change by construction.

This is the decomposition EXPERIMENTS.md (StudyEDGE-DL-LOAD) calls for when it states the 2.5 s cells exist because the DEADLINE changes what the arms DO, which D178 (1)'s offline re-scoring cannot capture: a_scoring_recut is exactly the offline-capturable part, and b_arm_decisions is the part it cannot.

## Result

| arm | seed | in [2.5,3.0) | total | (a) re-cut (dev / cloud) | (b) arm |
|---|---|---|---|---|---|
| llf | 4 | 0 | -4 | 0 (0 / 0) | -4 |
| mooncake | 4 | 0 | 1 | 0 (0 / 0) | 1 |

Device WARM latencies are about 0.25 to 0.31 s on the cells seen so far, far below 2.5 s, so no device answer falls in [2.5, 3.0) and the device re-cut is zero: the whole CBD change is the arm's different decisions under the tighter deadline, which is the point of running the 2.5 s cells rather than re-scoring the 3 s grid.

## Missing or dropped cells

- covex-v6-base_n16_s4_1200s_h27_3t_L2.5_epg_rq30: twin covex-v6-base_n16_s4_1200s_h27_3t_L3_epg_rq30 absent
- covex-v6-base_n16_s5_1200s_h27_3t_L2.5_epg_rq30: twin covex-v6-base_n16_s5_1200s_h27_3t_L3_epg_rq30 absent
- covex-v6-rules_n16_s4_1200s_h27_3t_L2.5_epg_rq30: twin covex-v6-rules_n16_s4_1200s_h27_3t_L3_epg_rq30 absent
- covex-v6-rules_n16_s5_1200s_h27_3t_L2.5_epg_rq30: twin covex-v6-rules_n16_s5_1200s_h27_3t_L3_epg_rq30 absent

## Provenance

- runs dir last commit: 1ba49e04
- WARM table last commit: 00a223d1
- inputs: each cell's cell.json (robot_rows, robot_headline), outcomes.jsonl.gz and request.jsonl.gz; delivery rule experiments/orchestration/live2/d179_rung2_verdict.py
- build is byte-deterministic given the inputs; the git commit of this file is the build time of record.
