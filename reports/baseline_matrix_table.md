# The baseline matrix: the bar for the D179 shares result

Assembled READ-ONLY from committed cells on `1fd244ad83a4dc62fd4dd89016cca44c574104e2` (`1fd244ad83a4dc62fd4dd89016cca44c574104e2`) by `experiments/orchestration/live2/baseline_matrix_table.py`. No cell was run, no arm was changed, nothing was recomputed from a working tree: every number is read through `git show` out of the cell's own `cell.json`, `header.json` and `run_meta.json`.

Grid: `_1200s_h27_3t_L3_epg_rq30`, 16 devices, 1200.0 s, host tier 27.0 GiB, ratio 40:40:20, robot deadline 3.0 s, robot question set `lh_req`, single-shot set `ss2`. Seeds 4, 5, 6, 7; seed 0 has NO cell in this grid (see below).

Columns, with the field each is read from:

- **robot correct-answers-delivered-by-deadline** - `cell.json -> score.score.robot_headline.correct_answers_delivered_by_deadline (and .n_by_deadline)`
- **hits/n** - `counted from cell.json -> score.score.robot_rows[].standing_correct_by_deadline, and checked to reproduce the headline rate`
- **robot on-time** - `cell.json -> score.score.sweep[0].robot_pool_on_time / .robot_pool_n`
- **single-shot (assistance) on-time** - `cell.json -> score.score.sweep[0].ss_pool_on_time / .ss_pool_n, at the 2.0 s single-shot deadline`
- **dashcam verdict** - `cell.json -> score.score.sweep[0].dashcam_all_meet, rendered MEETS / FAIL`
- **device-only floor (arm-independent)** - `cell.json -> score.score.device_only.robot_accuracy (and .robot_n)`
- **n_cloud_standing** - `cell.json -> score.score.robot_value.n_cloud_standing`
- **capacity** - `cell.json -> score.score.sweep[0].capacity_met`
- **sha** - `the commit that last touched that cell's cell.json on this rev`

## Positive control, run before the table was trusted

4 known-good committed arms checked, 4 reproduced EXACTLY. PASS.

| cell | field | prior | this run | ratio | hits/n prior | hits/n this run | floor prior | floor this run | cloud standing prior | cloud standing this run | agree |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `confidence-cascade_n16_s6_1200s_h27_3t_L3_epg_rq30` | robot_headline.correct_answers_delivered_by_deadline | 0.0579 | 0.0579 | 1.0000 | 7 of 121 | 7 of 121 | 0.0579 | 0.0579 | 0 | 0 | yes |
| `always-cloud-fcfs_n16_s6_1200s_h27_3t_L3_epg_rq30` | robot_headline.correct_answers_delivered_by_deadline | 0.0826 | 0.0826 | 1.0000 | 10 of 121 | 10 of 121 | 0.0579 | 0.0579 | 3 | 3 | yes |
| `simplestream_n16_s4_1200s_h27_3t_L3_epg_rq30` | robot_headline.correct_answers_delivered_by_deadline | 0.1439 | 0.1439 | 1.0000 | 19 of 132 | 19 of 132 | 0.3712 | 0.3712 | 132 | 132 | yes |
| `streamscout_n16_s4_1200s_h27_3t_L3_epg_rq30` | robot_headline.correct_answers_delivered_by_deadline | 0.1364 | 0.1364 | 1.0000 | 18 of 132 | 18 of 132 | 0.3712 | 0.3712 | 132 | 132 | yes |

## Floor identity, verified per seed rather than assumed

The device-only floor is ARM-INDEPENDENT: `score.score.device_only.robot_accuracy`, written identically into every cell of a seed. Checked across ALL cells of each seed in this grid, the two EXCLUDED arms included, because the claim is a property of the cells and not of the arms.

| seed | cells | floor | hits/n | distinct floor values | arm-independent | cells disagree |
|---|---|---|---|---|---|---|
| 4 | 21 | 0.3712 | 49 of 132 | 0.3712 | yes | no |
| 5 | 20 | 0.2992 | 38 of 127 | 0.2992 | yes | no |
| 6 | 17 | 0.0579 | 7 of 121 | 0.0579 | yes | no |
| 7 | 15 | 0.2952 | 31 of 105 | 0.2952 | yes | no |

Verified, not assumed, and verified over ALL cells of the seed INCLUDING the two excluded arms, because the identity is a property of the cells. At seed 6 it is 0.057851 (7 of 121) across all 17 cells, which is the committed value. No seed's cells disagree about their own floor.

## The scored baseline matrix

20 scored arms over 70 cells. `floor` repeats the seed's arm-independent device-only floor on every row ON PURPOSE: several arms sit exactly on it, and a reader who cannot see the floor cannot tell a working arm from an inert one. `cloud std` is `n_cloud_standing`: an arm with zero cloud standing is scoring the device floor whatever its mechanism did.

Of those 70 cells, **21 sit exactly ON their seed's floor**, 44 are above it and 5 are below it (below is flagged in its own section). **5 have ZERO cloud standing**: `attentionstore-prefetch_n16_s7_1200s_h27_3t_L3_epg_rq30`, `confidence-cascade_n16_s5_1200s_h27_3t_L3_epg_rq30`, `confidence-cascade_n16_s6_1200s_h27_3t_L3_epg_rq30`, `confidence-cascade_n16_s7_1200s_h27_3t_L3_epg_rq30`, `querystream-proactive_n16_s7_1200s_h27_3t_L3_epg_rq30`. These cells score the DEVICE FLOOR whatever their mechanism did: no cloud answer stands, so the headline cannot differ from the arm-independent floor. That is not by itself a port-rule failure (an arm may have escalated and had every answer arrive late, which is `confidence-cascade`'s case and is a RERUN item under D154 (5)), but it IS the signature that a number carries no information about the arm.

| arm | seed | by_deadline | hits/n | floor | floor hits/n | vs floor | rel | cloud std | robot on-time | SS on-time | dashcam | capacity | run_valid | sha |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `always-cloud-fcfs` | 4 | 0.3712 | 49 of 132 | 0.3712 | 49 of 132 | +0.0000 | at | 5 | 5 of 132 (0.0379) | 32 of 357 (0.0896) | FAIL | not met | True | `1f546ea6` |
| `always-cloud-fcfs` | 6 | 0.0826 | 10 of 121 | 0.0579 | 7 of 121 | +0.0248 | above | 3 | 3 of 121 (0.0248) | 49 of 357 (0.1373) | FAIL | not met | True | `9f3504a6` |
| `always-cloud-fcfs` | 7 | 0.2952 | 31 of 105 | 0.2952 | 31 of 105 | +0.0000 | at | 1 | 1 of 105 (0.0095) | 34 of 359 (0.0947) | FAIL | not met | True | `a0533b6a` |
| `attentionstore-prefetch` | 4 | 0.3712 | 49 of 132 | 0.3712 | 49 of 132 | +0.0000 | at | 4 | 4 of 132 (0.0303) | 22 of 357 (0.0616) | FAIL | not met | True | `1707f867` |
| `attentionstore-prefetch` | 5 | 0.3150 | 40 of 127 | 0.2992 | 38 of 127 | +0.0157 | above | 6 | 6 of 127 (0.0472) | 18 of 356 (0.0506) | FAIL | not met | True | `9261a52e` |
| `attentionstore-prefetch` | 6 | 0.0826 | 10 of 121 | 0.0579 | 7 of 121 | +0.0248 | above | 3 | 3 of 121 (0.0248) | 44 of 357 (0.1232) | FAIL | not met | True | `d08bae51` |
| `attentionstore-prefetch` | 7 | 0.2952 | 31 of 105 | 0.2952 | 31 of 105 | +0.0000 | at | 0 | 0 of 105 (0.0000) | 29 of 359 (0.0808) | FAIL | not met | True | `37a610cb` |
| `b7-edf-feasibility` | 4 | 0.3712 | 49 of 132 | 0.3712 | 49 of 132 | +0.0000 | at | 5 | 5 of 132 (0.0379) | 32 of 357 (0.0896) | FAIL | not met | True | `cbcc7486` |
| `b7-edf-feasibility` | 5 | 0.3071 | 39 of 127 | 0.2992 | 38 of 127 | +0.0079 | above | 5 | 5 of 127 (0.0394) | 26 of 356 (0.0730) | FAIL | not met | True | `3f615980` |
| `b7-edf-feasibility` | 6 | 0.0909 | 11 of 121 | 0.0579 | 7 of 121 | +0.0331 | above | 7 | 7 of 121 (0.0579) | 167 of 357 (0.4678) | MEETS | not met | True | `d1d54c10` |
| `b7-edf-feasibility` | 7 | 0.3238 | 34 of 105 | 0.2952 | 31 of 105 | +0.0286 | above | 8 | 8 of 105 (0.0762) | 301 of 359 (0.8384) | MEETS | not met | True | `757ac58b` |
| `confidence-cascade` | 4 | 0.3939 | 52 of 132 | 0.3712 | 49 of 132 | +0.0227 | above | 3 | 3 of 132 (0.0227) | 55 of 357 (0.1541) | MEETS | not met | True | `1d3571f6` |
| `confidence-cascade` | 5 | 0.2992 | 38 of 127 | 0.2992 | 38 of 127 | +0.0000 | at | 0 | 0 of 127 (0.0000) | 36 of 356 (0.1011) | FAIL | not met | True | `c80562c9` |
| `confidence-cascade` | 6 | 0.0579 | 7 of 121 | 0.0579 | 7 of 121 | +0.0000 | at | 0 | 0 of 121 (0.0000) | 27 of 357 (0.0756) | FAIL | not met | True | `622bd591` |
| `confidence-cascade` | 7 | 0.2952 | 31 of 105 | 0.2952 | 31 of 105 | +0.0000 | at | 0 | 0 of 105 (0.0000) | 14 of 359 (0.0390) | FAIL | not met | True | `2a7039c4` |
| `covex-v6-state` | 5 | 0.4331 | 55 of 127 | 0.2992 | 38 of 127 | +0.1339 | above | 116 | 116 of 127 (0.9134) | 347 of 356 (0.9747) | FAIL | not met | True | `6acdee05` |
| `covex-v6-state` | 6 | 0.1405 | 17 of 121 | 0.0579 | 7 of 121 | +0.0826 | above | 12 | 12 of 121 (0.0992) | 75 of 357 (0.2101) | FAIL | not met | True | `bc2cca4e` |
| `covex-v6-state-uo` | 4 | 0.6136 | 81 of 132 | 0.3712 | 49 of 132 | +0.2424 | above | 118 | 118 of 132 (0.8939) | 344 of 357 (0.9636) | FAIL | not met | True | `24ca4fcf` |
| `covex-v6-state-uo` | 5 | 0.4252 | 54 of 127 | 0.2992 | 38 of 127 | +0.1260 | above | 115 | 115 of 127 (0.9055) | 350 of 356 (0.9831) | FAIL | not met | True | `033c9787` |
| `covex-v6-state-uo` | 6 | 0.4959 | 60 of 121 | 0.0579 | 7 of 121 | +0.4380 | above | 107 | 107 of 121 (0.8843) | 342 of 357 (0.9580) | MEETS | not met | True | `f9c1c612` |
| `covex-v6-state-uo` | 7 | 0.4762 | 50 of 105 | 0.2952 | 31 of 105 | +0.1810 | above | 83 | 83 of 105 (0.7905) | 355 of 359 (0.9889) | FAIL | not met | True | `2d526af6` |
| `covex-v6-state-uo-c5attr` | 4 | 0.5985 | 79 of 132 | 0.3712 | 49 of 132 | +0.2273 | above | 117 | 117 of 132 (0.8864) | 338 of 357 (0.9468) | FAIL | not met | True | `7264a69a` |
| `covex-v6-state-uo-c5attr` | 5 | 0.4252 | 54 of 127 | 0.2992 | 38 of 127 | +0.1260 | above | 115 | 115 of 127 (0.9055) | 344 of 356 (0.9663) | MEETS | met | True | `f996533a` |
| `covex-v6-state-uo-c5attr` | 6 | 0.4628 | 56 of 121 | 0.0579 | 7 of 121 | +0.4050 | above | 105 | 105 of 121 (0.8678) | 327 of 357 (0.9160) | MEETS | not met | True | `cc025f82` |
| `covex-v6-state-uo-c5attr` | 7 | 0.4762 | 50 of 105 | 0.2952 | 31 of 105 | +0.1810 | above | 83 | 83 of 105 (0.7905) | 350 of 359 (0.9749) | MEETS | not met | True | `116abf5d` |
| `eco-llm` | 4 | 0.3712 | 49 of 132 | 0.3712 | 49 of 132 | +0.0000 | at | 6 | 6 of 132 (0.0455) | 32 of 357 (0.0896) | FAIL | not met | True | `0ec18c48` |
| `eco-llm` | 5 | 0.3071 | 39 of 127 | 0.2992 | 38 of 127 | +0.0079 | above | 7 | 7 of 127 (0.0551) | 28 of 356 (0.0787) | FAIL | not met | True | `ce5cd680` |
| `edf` | 4 | 0.3864 | 51 of 132 | 0.3712 | 49 of 132 | +0.0152 | above | 5 | 5 of 132 (0.0379) | 49 of 357 (0.1373) | FAIL | not met | True | `b1b0d452` |
| `edf` | 5 | 0.2913 | 37 of 127 | 0.2992 | 38 of 127 | -0.0079 | below | 4 | 4 of 127 (0.0315) | 55 of 356 (0.1545) | FAIL | not met | True | `38f93ac3` |
| `edf` | 6 | 0.0992 | 12 of 121 | 0.0579 | 7 of 121 | +0.0413 | above | 5 | 5 of 121 (0.0413) | 52 of 357 (0.1457) | FAIL | not met | True | `d05e094c` |
| `edf` | 7 | 0.2952 | 31 of 105 | 0.2952 | 31 of 105 | +0.0000 | at | 1 | 1 of 105 (0.0095) | 65 of 359 (0.1811) | MEETS | not met | True | `48f4b6d5` |
| `hybrid-F-lhreq` | 4 | 0.3409 | 45 of 132 | 0.3712 | 49 of 132 | -0.0303 | below | 111 | 111 of 132 (0.8409) | 336 of 357 (0.9412) | MEETS | not met | True | `5f198df5` |
| `hybrid-F-lhreq` | 5 | 0.3228 | 41 of 127 | 0.2992 | 38 of 127 | +0.0236 | above | 109 | 109 of 127 (0.8583) | 344 of 356 (0.9663) | MEETS | not met | True | `fa706dd3` |
| `hybrid-F-lhreq` | 6 | 0.3058 | 37 of 121 | 0.0579 | 7 of 121 | +0.2479 | above | 108 | 108 of 121 (0.8926) | 352 of 357 (0.9860) | MEETS | not met | True | `324e6b99` |
| `hybrid-F-lhreq` | 7 | 0.3619 | 38 of 105 | 0.2952 | 31 of 105 | +0.0667 | above | 99 | 99 of 105 (0.9429) | 355 of 359 (0.9889) | MEETS | met | True | `faa7c131` |
| `hybrid-F-lhreq-noc3` | 4 | 0.4697 | 62 of 132 | 0.3712 | 49 of 132 | +0.0985 | above | 35 | 35 of 132 (0.2652) | 337 of 357 (0.9440) | MEETS | not met | True | `b21d1918` |
| `hybrid-F-lhreq-noc3` | 5 | 0.3386 | 43 of 127 | 0.2992 | 38 of 127 | +0.0394 | above | 27 | 27 of 127 (0.2126) | 343 of 356 (0.9635) | MEETS | not met | True | `f1727ccd` |
| `hybrid-F-lhreq-noc3` | 6 | 0.2479 | 30 of 121 | 0.0579 | 7 of 121 | +0.1901 | above | 41 | 41 of 121 (0.3388) | 349 of 357 (0.9776) | MEETS | not met | True | `61ea567f` |
| `hybrid-F-lhreq-noc3` | 7 | 0.3810 | 40 of 105 | 0.2952 | 31 of 105 | +0.0857 | above | 19 | 19 of 105 (0.1810) | 354 of 359 (0.9861) | MEETS | not met | True | `ee92fbdf` |
| `llf` | 4 | 0.3939 | 52 of 132 | 0.3712 | 49 of 132 | +0.0227 | above | 7 | 7 of 132 (0.0530) | 135 of 357 (0.3782) | MEETS | not met | True | `e68b6958` |
| `llf` | 5 | 0.2992 | 38 of 127 | 0.2992 | 38 of 127 | +0.0000 | at | 5 | 5 of 127 (0.0394) | 147 of 356 (0.4129) | MEETS | not met | True | `870f1e12` |
| `llf` | 6 | 0.0992 | 12 of 121 | 0.0579 | 7 of 121 | +0.0413 | above | 9 | 9 of 121 (0.0744) | 167 of 357 (0.4678) | MEETS | not met | True | `cf6caf05` |
| `llf` | 7 | 0.3143 | 33 of 105 | 0.2952 | 31 of 105 | +0.0190 | above | 4 | 4 of 105 (0.0381) | 167 of 359 (0.4652) | MEETS | not met | True | `3fe6b233` |
| `lmcache` | 4 | 0.3712 | 49 of 132 | 0.3712 | 49 of 132 | +0.0000 | at | 3 | 3 of 132 (0.0227) | 22 of 357 (0.0616) | FAIL | not met | True | `469929a1` |
| `lmcache` | 5 | 0.2992 | 38 of 127 | 0.2992 | 38 of 127 | +0.0000 | at | 4 | 4 of 127 (0.0315) | 19 of 356 (0.0534) | FAIL | not met | True | `181c9d10` |
| `mooncake` | 4 | 0.3712 | 49 of 132 | 0.3712 | 49 of 132 | +0.0000 | at | 5 | 5 of 132 (0.0379) | 32 of 357 (0.0896) | FAIL | not met | True | `3cb062ee` |
| `mooncake` | 5 | 0.3071 | 39 of 127 | 0.2992 | 38 of 127 | +0.0079 | above | 5 | 5 of 127 (0.0394) | 27 of 356 (0.0758) | FAIL | not met | True | `a01e439b` |
| `mooncake` | 6 | 0.0909 | 11 of 121 | 0.0579 | 7 of 121 | +0.0331 | above | 7 | 7 of 121 (0.0579) | 167 of 357 (0.4678) | MEETS | not met | True | `83f0f50a` |
| `mooncake` | 7 | 0.3333 | 35 of 105 | 0.2952 | 31 of 105 | +0.0381 | above | 8 | 8 of 105 (0.0762) | 309 of 359 (0.8607) | MEETS | not met | True | `b2cd2102` |
| `querystream-proactive` | 4 | 0.3712 | 49 of 132 | 0.3712 | 49 of 132 | +0.0000 | at | 5 | 5 of 132 (0.0379) | 28 of 357 (0.0784) | FAIL | not met | True | `51d9f5e5` |
| `querystream-proactive` | 5 | 0.2992 | 38 of 127 | 0.2992 | 38 of 127 | +0.0000 | at | 3 | 3 of 127 (0.0236) | 19 of 356 (0.0534) | FAIL | not met | True | `03db92bb` |
| `querystream-proactive` | 6 | 0.0826 | 10 of 121 | 0.0579 | 7 of 121 | +0.0248 | above | 3 | 3 of 121 (0.0248) | 48 of 357 (0.1345) | FAIL | not met | True | `6921f6cc` |
| `querystream-proactive` | 7 | 0.2952 | 31 of 105 | 0.2952 | 31 of 105 | +0.0000 | at | 0 | 0 of 105 (0.0000) | 34 of 359 (0.0947) | FAIL | not met | True | `e997f459` |
| `simplestream` | 4 | 0.1439 | 19 of 132 | 0.3712 | 49 of 132 | -0.2273 | below | 132 | 132 of 132 (1.0000) | 355 of 357 (0.9944) | MEETS | met | True | `b889da40` |
| `simplestream` | 5 | 0.2992 | 38 of 127 | 0.2992 | 38 of 127 | +0.0000 | at | 126 | 126 of 127 (0.9921) | 356 of 356 (1.0000) | MEETS | met | True | `ada052d1` |
| `simplestream` | 6 | 0.1653 | 20 of 121 | 0.0579 | 7 of 121 | +0.1074 | above | 120 | 120 of 121 (0.9917) | 356 of 357 (0.9972) | MEETS | met | True | `f36c4673` |
| `simplestream` | 7 | 0.2857 | 30 of 105 | 0.2952 | 31 of 105 | -0.0095 | below | 105 | 105 of 105 (1.0000) | 358 of 359 (0.9972) | MEETS | met | True | `3c7258ca` |
| `streamscout` | 4 | 0.1364 | 18 of 132 | 0.3712 | 49 of 132 | -0.2348 | below | 132 | 132 of 132 (1.0000) | 357 of 357 (1.0000) | MEETS | met | True | `37b2438b` |
| `streamscout` | 5 | 0.2992 | 38 of 127 | 0.2992 | 38 of 127 | +0.0000 | at | 126 | 126 of 127 (0.9921) | 355 of 356 (0.9972) | MEETS | met | True | `1f557752` |
| `v5-rules` | 4 | 0.4394 | 58 of 132 | 0.3712 | 49 of 132 | +0.0682 | above | 40 | 40 of 132 (0.3030) | 170 of 357 (0.4762) | FAIL | not met | True | `b5fe931e` |
| `v5-rules` | 5 | 0.3701 | 47 of 127 | 0.2992 | 38 of 127 | +0.0709 | above | 44 | 44 of 127 (0.3465) | 158 of 356 (0.4438) | FAIL | not met | True | `bdcd1aaa` |
| `v5-rules` | 6 | 0.2149 | 26 of 121 | 0.0579 | 7 of 121 | +0.1570 | above | 35 | 35 of 121 (0.2893) | 205 of 357 (0.5742) | FAIL | not met | True | `a1585fc6` |
| `v5-rules-2` | 4 | 0.4848 | 64 of 132 | 0.3712 | 49 of 132 | +0.1136 | above | 38 | 38 of 132 (0.2879) | 245 of 357 (0.6863) | FAIL | not met | True | `08a7ee19` |
| `v5-rules-2` | 5 | 0.3307 | 42 of 127 | 0.2992 | 38 of 127 | +0.0315 | above | 37 | 37 of 127 (0.2913) | 258 of 356 (0.7247) | FAIL | not met | True | `9f7fca97` |
| `v5-rules-2` | 6 | 0.1570 | 19 of 121 | 0.0579 | 7 of 121 | +0.0992 | above | 32 | 32 of 121 (0.2645) | 259 of 357 (0.7255) | FAIL | not met | True | `5793543d` |
| `v5-rules-2` | 7 | 0.3905 | 41 of 105 | 0.2952 | 31 of 105 | +0.0952 | above | 23 | 23 of 105 (0.2190) | 266 of 359 (0.7409) | FAIL | not met | True | `48c5c82f` |
| `warm-all-lru` | 4 | 0.3712 | 49 of 132 | 0.3712 | 49 of 132 | +0.0000 | at | 3 | 3 of 132 (0.0227) | 23 of 357 (0.0644) | FAIL | not met | True | `b5823b5c` |
| `warm-all-lru` | 5 | 0.3071 | 39 of 127 | 0.2992 | 38 of 127 | +0.0079 | above | 4 | 4 of 127 (0.0315) | 19 of 356 (0.0534) | FAIL | not met | True | `4c233212` |
| `warm-all-lru` | 6 | 0.0744 | 9 of 121 | 0.0579 | 7 of 121 | +0.0165 | above | 2 | 2 of 121 (0.0165) | 30 of 357 (0.0840) | FAIL | not met | True | `1940dbd1` |
| `warm-all-lru` | 7 | 0.2952 | 31 of 105 | 0.2952 | 31 of 105 | +0.0000 | at | 1 | 1 of 105 (0.0095) | 28 of 359 (0.0780) | FAIL | not met | True | `3be6cc1a` |

Per-arm seed coverage, with its denominator, because coverage is UNEVEN:

| arm | seeds | n | in the scored table |
|---|---|---|---|
| `always-cloud-fcfs` | 4, 6, 7 | 3 | yes |
| `attentionstore-prefetch` | 4, 5, 6, 7 | 4 | yes |
| `b7-edf-feasibility` | 4, 5, 6, 7 | 4 | yes |
| `confidence-cascade` | 4, 5, 6, 7 | 4 | yes |
| `covex-v6-state` | 5, 6 | 2 | yes |
| `covex-v6-state-shares` | 4 | 1 | yes |
| `covex-v6-state-uo` | 4, 5, 6, 7 | 4 | yes |
| `covex-v6-state-uo-c5attr` | 4, 5, 6, 7 | 4 | yes |
| `eco-llm` | 4, 5 | 2 | yes |
| `edf` | 4, 5, 6, 7 | 4 | yes |
| `hybrid-F-lhreq` | 4, 5, 6, 7 | 4 | yes |
| `hybrid-F-lhreq-noc3` | 4, 5, 6, 7 | 4 | yes |
| `llf` | 4, 5, 6, 7 | 4 | yes |
| `lmcache` | 4, 5 | 2 | yes |
| `mooncake` | 4, 5, 6, 7 | 4 | yes |
| `querystream-proactive` | 4, 5, 6, 7 | 4 | yes |
| `r3-streaming` | 4, 5 | 2 | **no, EXCLUDED by the port rule** |
| `simplestream` | 4, 5, 6, 7 | 4 | yes |
| `streamscout` | 4, 5 | 2 | yes |
| `v5-rules` | 4, 5, 6 | 3 | yes |
| `v5-rules-2` | 4, 5, 6, 7 | 4 | yes |
| `warm-all-lru` | 4, 5, 6, 7 | 4 | yes |

COVERAGE IS UNEVEN and is reported with its denominator rather than pooled over. An arm's absence at a seed is a GAP, not a result: it is either a seed that was never run for that arm or a directory that holds no scored cell (see `unscored_grid_dirs`). No column in this table is pooled across seeds, so no gap is averaged into a number here, but a reader who pools must pool over COMMON SUPPORT.

### Grid directories that hold NO scored cell (4 of 77), reported not dropped

REPORTED, not silently dropped. These directories are NOT cells: they carry no `cell.json`, so they have no headline, no on-time count and no floor, and nothing can be read from them. They are not marked INVALID either; they are unscored. the grid is UNEVEN, so an arm's absence at a seed is a GAP and not a result, and the per-seed arm count differs. Per-arm seed coverage is reported beside the matrix for exactly this reason.

| directory | arm | seed | what is committed | kind |
|---|---|---|---|---|
| `always-cloud-fcfs_n16_s5_1200s_h27_3t_L3_epg_rq30` | always-cloud-fcfs | 5 | `frames_preflight.json`, `mm_gate.json`, `mm_uuid_check.json` | PREFLIGHT STUB: only the preflight / mm-gate artefacts are committed, so no run was scored |
| `covex-v6-state_n16_s4_1200s_h27_3t_L3_epg_rq30` | covex-v6-state | 4 | `frames_preflight.json`, `mm_gate.json`, `mm_uuid_check.json` | PREFLIGHT STUB: only the preflight / mm-gate artefacts are committed, so no run was scored |
| `covex-v6-state_n16_s7_1200s_h27_3t_L3_epg_rq30` | covex-v6-state | 7 | `calibration_knots.json`, `decision.jsonl`, `frames_preflight.json`, `header.json`, `metrics_snapshots.log`, `metrics_snapshots.log.tmp`, `mm_gate.json`, `mm_uuid_check.json`, `request.jsonl`, `residency.jsonl` | PARTIAL RUN: logs are committed but no `cell.json`, so the run was never scored |
| `v5-rules_n16_s7_1200s_h27_3t_L3_epg_rq30` | v5-rules | 7 | `frames_preflight.json`, `mm_gate.json`, `mm_uuid_check.json` | PREFLIGHT STUB: only the preflight / mm-gate artefacts are committed, so no run was scored |

## HELD OUT of the baselines as the ARM UNDER TEST (not a port-rule exclusion)

Arms held out: `covex-v6-state-shares`, `covex-v6-fair-shares`. These are the ARM UNDER TEST for StudyD179-SHARES. This table is the BAR they are read against, so they are held OUT of the baselines rather than listed among them: an arm in its own control is not a control. This is NOT a port-rule exclusion and NOT a verdict on the arm. Its cells are named here with the bar for their seed; reading them against that bar belongs to StudyD179-SHARES, not to this assembly.

| cell | arm | seed | run_valid | code rev | sha |
|---|---|---|---|---|---|
| `covex-v6-state-shares_n16_s4_1200s_h27_3t_L3_epg_rq30` | covex-v6-state-shares | 4 | True | `8942baa7` | `91c876a5` |

Its headline, on-time and dashcam numbers are **deliberately not copied here**. They are the RESULT; this page is the bar. Reading one against the other belongs to StudyD179-SHARES, and doing it here would hand that study its own comparator pre-read.

The bar for each seed a held-out cell is present at:

| seed | device-only floor | floor hits/n | baseline cells | baseline by_deadline min | max | best baseline arm | baselines meeting dashcam | baselines meeting capacity |
|---|---|---|---|---|---|---|---|---|
| 4 | 0.3712 | 49 of 132 | 19 | 0.1364 | 0.6136 | `covex-v6-state-uo` | 6 of 19 | 2 of 19 |

A held-out cell is comparable ONLY with the baseline cells of its OWN seed, and only if its input, stack and decoding keys match theirs. Those keys are carried per row in `matrix`; the held-out cell's own code rev is given above so the check can be made rather than assumed.

## EXCLUDED from the scored baselines by the port rule, listed with the reason

USER DECISION 2026-11-22 (addendum 10 item 1) under D130: an arm whose mechanism cannot be expressed in the live setting is DOCUMENTED, not forced. Recorded in `reports/study_port_rule_exclusions.md` and the StudyPORT-EXCL row of `research/EXPERIMENTS.md`.

The rule they fail is the CLAUDE.md citing rule: a port's proofs must include that its CHARACTERISTIC DECISION occurs at least once. The required well-formedness and fairness checks establish that an arm is legal and fairly treated; neither establishes that it does anything. Both arms pass the former and fail the latter, which is why this needed a COUNT rather than a review.

### `cascade-routing`

- WHICH STEP FAILS: the port rule, the characteristic-decision count: a port's proofs must include that its characteristic decision occurs at least once
- ESCALATIONS: [0, 0] in every committed cell (20 of 20; 25 of 25 declines)
- WHY IT FAILS BY CONSTRUCTION: its card's routing method is inexpressible in this setting: the sufficiency proxy the card specifies can never fire here, so the escalation branch is UNREACHABLE rather than merely unvisited
- CONSEQUENCE IF IT WERE SCORED: it sits exactly on the ARM-INDEPENDENT device-only floor in every committed cell, so a table listing it as a baseline reports the device floor under an arm name; the two together would have put the device floor into the baseline table twice under two different names
- CELLS KEPT FOR PROVENANCE: 2, unchanged, not deleted, not marked INVALID, not recomputed.

No cell in THIS grid: its committed cells are `_L3_epg`, a different workload, so its numbers are never set beside this table's. Cells: `cascade-routing_n16_s4_1200s_h27_3t_L3_epg`, `cascade-routing_n16_s5_1200s_h27_3t_L3_epg`.

### `r3-streaming`

- WHICH STEP FAILS: the port rule, the characteristic-decision count: a port's proofs must include that its characteristic decision occurs at least once
- ESCALATIONS: [0, 0, 0, 0] in every committed cell (19 of 20; 126 of 132; 25 of 25; 127 of 127 declines)
- WHY IT FAILS BY CONSTRUCTION: its escalation test is never reached and no `release_recall` is emitted at all, so the arm never makes the decision it exists to make; NOT previously flagged
- CONSEQUENCE IF IT WERE SCORED: it sits exactly on the ARM-INDEPENDENT device-only floor in every committed cell, so a table listing it as a baseline reports the device floor under an arm name; the two together would have put the device floor into the baseline table twice under two different names
- CELLS KEPT FOR PROVENANCE: 4, unchanged, not deleted, not marked INVALID, not recomputed.

| cell | seed | by_deadline | hits/n | floor | vs floor | cloud std | robot on-time | SS on-time | dashcam | sha |
|---|---|---|---|---|---|---|---|---|---|---|
| `r3-streaming_n16_s4_1200s_h27_3t_L3_epg_rq30` | 4 | 0.3712 | 49 of 132 | 0.3712 | +0.0000 | 0 | 0 of 132 | 0 of 357 | FAIL | `aa4294f6` |
| `r3-streaming_n16_s5_1200s_h27_3t_L3_epg_rq30` | 5 | 0.2992 | 38 of 127 | 0.2992 | +0.0000 | 0 | 0 of 127 | 0 of 356 | FAIL | `ef4a963a` |

### What is NOT excluded, and why the distinction matters

- `confidence-cascade`: PASSES the port rule: 57 / 44 / 35 escalations at seeds 6 / 4 / 5, counted from the decision log and independently reconstructed offline from the committed StudyE7 confidence table plus the DEV-fitted floor. Its separate problem, that none of the 57 was delivered inside the 3 s deadline at seed 6 or seed 5, is a live-timing matter already queued by D154 (5) as a RERUN item, not a re-score and not an exclusion.
- `streamscout`: PASSES the port rule with 132 of 132 escalations at seed 4.

## FLAGGED: cells whose by_deadline is BELOW their seed's device-only floor

10 cells of 131 scanned at seeds 0, 4, 5, 6, 7, 5 of them inside this table. Prior committed census: 10 of 127 (results/orchestration/live2/frozen_test/cascade_below_floor_diagnosis.json step6_grid, at rev 622bd591177110605eddd3b119c8c7926bf94e24); the two sets are identical by NAME and not only by count: True. Every one has `n_cloud_standing` above zero: True.

FLAGGED, NOT a fault and NOT excluded. Listed so a reader meets them here rather than discovering them in the table. LEGITIMATE under the standing-answer rule (`scorer/score.py`, the standing answer by deadline): an ON-TIME but WRONG cloud answer REPLACES a correct device answer. So an escalation can make a question worse than not asking, by being WRONG rather than by being LATE; a late answer never stands. Every such cell has n_cloud_standing above zero, which is the signature to look for.

| cell | arm | seed | by_deadline | n | floor | vs floor | cloud std | cloud acc on served | in this table |
|---|---|---|---|---|---|---|---|---|---|
| `eco-llm_n16_s5_1200s_h27_3t_L3_epg` | eco-llm | 5 | 0.2000 | 25 | 0.3200 | -0.1200 | 13 | 0.1538 | no |
| `edf_n16_s5_1200s_h27_3t_L3_epg_rq30` | edf | 5 | 0.2913 | 127 | 0.2992 | -0.0079 | 4 | 0.0000 | yes |
| `hybrid-F-lhreq_n16_s4_1200s_h27_3t_L3_epg_rq30` | hybrid-F-lhreq | 4 | 0.3409 | 132 | 0.3712 | -0.0303 | 111 | 0.2973 | yes |
| `hybrid-F-lhreq_n16_s5_1200s_h27_3t_L3_epg` | hybrid-F-lhreq | 5 | 0.2800 | 25 | 0.3200 | -0.0400 | 21 | 0.2381 | no |
| `simplestream_n16_s4_1200s_h27_3t_L3` | simplestream | 4 | 0.2000 | 20 | 0.3000 | -0.1000 | 20 | 0.2000 | no |
| `simplestream_n16_s4_1200s_h27_3t_L3_epg` | simplestream | 4 | 0.1500 | 20 | 0.3000 | -0.1500 | 20 | 0.1500 | no |
| `simplestream_n16_s4_1200s_h27_3t_L3_epg_rq30` | simplestream | 4 | 0.1439 | 132 | 0.3712 | -0.2273 | 132 | 0.1439 | yes |
| `simplestream_n16_s5_1200s_h27_3t_L3_epg` | simplestream | 5 | 0.2400 | 25 | 0.3200 | -0.0800 | 24 | 0.2083 | no |
| `simplestream_n16_s7_1200s_h27_3t_L3_epg_rq30` | simplestream | 7 | 0.2857 | 105 | 0.2952 | -0.0095 | 105 | 0.2857 | yes |
| `streamscout_n16_s4_1200s_h27_3t_L3_epg_rq30` | streamscout | 4 | 0.1364 | 132 | 0.3712 | -0.2348 | 132 | 0.1364 | yes |

A cell exactly AT its floor is a different thing and is NOT flagged here: it is what an arm that never escalates, or whose escalations never stand, scores by construction. The `relation_to_floor` column names it per row.

## Comparability: which comparisons are input, stack and decoding matched

| seed | cells | input | stack | decoding | distinct decoding signatures | decoding unverifiable | fairness digests equal | code revs |
|---|---|---|---|---|---|---|---|---|
| 4 | 21 | match | match | match where readable | 1 | 2 of 21 | yes | 21 |
| 5 | 20 | match | match | match where readable | 1 | 4 of 20 | yes | 20 |
| 6 | 17 | match | match | match where readable | 1 | 1 of 17 | yes | 17 |
| 7 | 15 | match | match | match where readable | 1 | 2 of 15 | yes | 15 |

- seed 4: INPUT AND STACK MATCH; decoding matches on every cell whose code rev is readable on this box and is UNVERIFIABLE on 2 of 21 (their revs are not in this box's object store), which is DECLARED and not assumed. Unverifiable: `lmcache_n16_s4_1200s_h27_3t_L3_epg_rq30`, `r3-streaming_n16_s4_1200s_h27_3t_L3_epg_rq30`.
- seed 5: INPUT AND STACK MATCH; decoding matches on every cell whose code rev is readable on this box and is UNVERIFIABLE on 4 of 20 (their revs are not in this box's object store), which is DECLARED and not assumed. Unverifiable: `covex-v6-state-uo_n16_s5_1200s_h27_3t_L3_epg_rq30`, `r3-streaming_n16_s5_1200s_h27_3t_L3_epg_rq30`, `streamscout_n16_s5_1200s_h27_3t_L3_epg_rq30`, `v5-rules_n16_s5_1200s_h27_3t_L3_epg_rq30`.
- seed 6: INPUT AND STACK MATCH; decoding matches on every cell whose code rev is readable on this box and is UNVERIFIABLE on 1 of 17 (their revs are not in this box's object store), which is DECLARED and not assumed. Unverifiable: `v5-rules_n16_s6_1200s_h27_3t_L3_epg_rq30`.
- seed 7: INPUT AND STACK MATCH; decoding matches on every cell whose code rev is readable on this box and is UNVERIFIABLE on 2 of 15 (their revs are not in this box's object store), which is DECLARED and not assumed. Unverifiable: `covex-v6-state-uo-c5attr_n16_s7_1200s_h27_3t_L3_epg_rq30`, `hybrid-F-lhreq_n16_s7_1200s_h27_3t_L3_epg_rq30`.

- ACROSS SEEDS: **NOT matched.** a seed is a DIFFERENT TRACE: the robot pool size differs by seed (132 at s4, 127 at s5, 121 at s6, 105 at s7) and so does the device-only floor, so an arm's cell at one seed is NOT comparable with another arm's cell at another seed. Compare WITHIN a seed, or pool with the pairing held by seed as `frozen_headline.py` does.
- ACROSS TRACE FAMILIES: **NOT matched.** the `_L3_epg` cells and the `_L3_epg_rq30` cells are DIFFERENT WORKLOADS: rq30 adds the D159 / D161 re-asks, so the robot pool is 105 to 132 questions against 20 to 25 without it. `cascade-routing`'s two committed cells are `_L3_epg` ONLY and have no cell in this grid at all, so its numbers are never set beside this table's; only its port-rule COUNT is. The same holds for the `_L3`, `_3t`, `_rerun`, `_postfix` and `REFUSED_preflight` families, none of which this table reads.
- Decoding is not a per-cell field. The live2 request bodies fix it in code (`experiments/orchestration/live2/bodies.py`, temperature=0.0, greedy, with the seed read from a committed constant), so two cells share decoding exactly when that file's SAMPLING LINES agree at the code rev their own header records. Those lines are extracted per cell AT its own rev, so the claim is checked and not asserted. Keying on the whole-file blob was tried FIRST and was WRONG: the two blobs present in this grid differ only in the D150 / D164 `kv_transfer_params` host-offload plumbing, not in any sampling parameter, so a blob-level check reports a decoding mismatch where there is none.
- The cells whose code rev is NOT in this box's object store cannot have their sampling lines read at all, so their decoding is UNVERIFIABLE rather than matched. Each such cell is named per seed. Their own headers record `git_working_tree.dirty` false, so the rev is a clean commit that simply never reached this box; that is a reason to expect a match, not evidence of one, and it is reported as a declared limitation.

## Status of every cell cited

Checked in `research/EXPERIMENTS.md` on the same rev (`439864e8`). 9 rows in that registry carry an INVALID marker; none of them names any cell or any arm in this table.

- The frozen-test grid is NOT registered one row per cell. It is carried by the study rows that cite `results/orchestration/live2/frozen_test/`: StudyPOLICY-V5, StudyV5-ENGINE, StudyC5-ATTR, StudyD179-SHARES and StudyPORT-EXCL. NONE of those rows carries an INVALID marker, and no row marked INVALID names any frozen-test cell or any arm in this table. The rows that ARE marked INVALID are the E24 family, StudyD / StudyD2, StudyI2 / StudyI3 and StudyJ, none of which this table reads.
- Cell-level unusability in this tree is carried by the cell, not the registry: a `REFUSED_preflight` directory name or `run_valid` false. Both are checked per row below. No cell in this grid carries either.
- Rows marked INVALID in the registry: `E24 **[INVALID — audit 2026-11-03]**`, `E24b **[INVALID — audit 2026-11-03]**`, `E24c **[INVALID — audit 2026-11-03]**`, `StudyD **[INVALID — audit 2026-11-03]**`, `StudyD2 **[INVALID — audit 2026-11-03]**`, `StudyI2 **[INVALID (SPATIAL + TEMPORAL arms) — audit 2026-11-03; SPARSE unaffected]**`, `StudyI3 **[INVALID (TEMPORAL arm) — audit 2026-11-03; SPARSE unaffected]**`, `StudyI3-reanalysis **[INVALID (TEMPORAL arm) — audit 2026-11-03]**`, `StudyJ **[INVALID AS A GATE — audit 2026-11-03]**`.

## Consistency check

**1 cross-check against committed measurements.** PASS. 4 of 4 known-good committed arms reproduced EXACTLY (ratio 1.000000 on every one), and the below-floor census reproduces the prior committed count: 10 below out of 131 scanned here against 10 out of 127 at results/orchestration/live2/frozen_test/cascade_below_floor_diagnosis.json step6_grid, at rev 622bd591177110605eddd3b119c8c7926bf94e24. The scan set grew by 4 cells because cells have been committed since that rev. The two censuses are compared by NAME and not only by count, so a swap could not have passed as an agreement: the sets are identical: True, with 0 cells below here that were not in the prior census and 0 in the prior census that are not below here. Separately, 4 of the 77 grid DIRECTORIES hold no `cell.json` and so are not cells; they are listed rather than dropped, because dropping them silently would have changed the arm count per seed with nothing looking wrong.

**2 physical plausibility.** NOT APPLICABLE, and said so rather than skipped. This table MEASURES NOTHING: it copies committed per-cell fields. It states no latency, throughput or size, derives no rate, and so has no implied rate to compare against the committed cost curves.

**3 distribution sanity.** PASS, with one constant EXPLAINED rather than trusted. The `floor` column is CONSTANT within a seed. That is not short-circuiting: it is the same arm-independent `device_only.robot_accuracy` written into every cell of the seed, which is exactly the identity discipline 4 verifies, and the per-seed distinct-value count is reported beside it. The scored columns are NOT constant: by_deadline spreads across arms within every seed and the spread is reported per row rather than as a median.

**4 definition audit.** PASS. `by_deadline` is `robot_headline.correct_answers_delivered_by_deadline` under D155 (3): the cloud's answer when delivered within the deadline, otherwise the device's. The `floor` is `device_only.robot_accuracy`, the ARM-INDEPENDENT device-only number, which is the definition the committed diagnosis settled after 'device-answer floor' had been used for two different things. On-time is delivery within the deadline by a request that returned HTTP 200, at the `delivery_rule` each cell records (`completion`). The robot deadline is 3.0 s (the `_L3` tag) even though the cells' `targets.robot.L_s` still reads 5.0; the SWEEP setting, which is what the on-time columns are read from, is L_rob = 3.0 in every cell. The robot pool size is NOT one number: 132 at s4, 127 at s5, 121 at s6, 105 at s7, which is why no column is pooled across seeds here.

**5 claim linkage.** This table bears on the baseline suite's PORT RULE and on the standing-answer rule, and it is the bar for StudyD179-SHARES. It is an ASSEMBLY of committed cells, not a test of a claim, so it supports and weakens nothing on its own. It measures no object that FORMULATION.md scopes out.

**6 proxy validity.** Two proxies, both declared. (i) The ESCALATION counts in the exclusion section are taken from the committed diagnosis, which read them from the decision log rather than the arms' unpersisted stats; that proxy was closed there by an independent offline reconstruction agreeing on every row, and no count is recomputed here. (ii) The per-cell SHA is the commit that last touched the cell's `cell.json`, which is a proxy for 'when this cell was committed' and is exact for a cell written once and never amended; the cell's OWN code rev, which is what matters for comparability, is carried separately as `code_git_commit` from its header.

**7 validate the control, not only the result.** PASS, and this is the check the table is built around. The CONTROL here is the device-only floor, and it is audited in its own right in two ways rather than assumed: its arm-independence is verified across every cell of every seed (s4 0.3712 over 21 cells; s5 0.2992 over 20 cells; s6 0.0579 over 17 cells; s7 0.2952 over 15 cells), and four known-good committed arms must reproduce their headline, hits/n, floor and cloud-standing EXACTLY before the table is written, with the run REFUSING to write a table if one of them does not. A known-good arm failing would mean the READER is broken, not the arm.

## Caveats carried from the cells

- D85: dashcam task value is streaming AP over the clip-PLAYS completed in the run, indexed by play id and paired across arms. It is NOT comparable to the committed 300-clip AP. D84: repeated clips or sessions across devices are separate plays and are NOT independent samples.
- D87: robot device answers are the 4B-I x RECENT set of StudyO-Q4 (845 questions, 32.78 %), restricted to EVAL. They were produced by the 4B on the A6000 / H100, NOT on the Orin. StudyD15 Part A rejected the H100-for-Orin proxy as an exact numerical stand-in, so these answers are valid for ordering and first-order value, not as exact device numbers.
- D70: the wire format is JPEG. S-EMBER q88 parity is NOT proven within the pre-registered +/- 2 pp rule (K3 +0.83 pp [-0.24, +2.01], K1 -0.6 pp with lower bound -2.14, about 6 % of letters change). S-EMBER cloud accuracy here is the cloud's actual answers on JPEG input.
- D81: vLLM's prefix-cache path is not output-identical to recompute (StudyORIN3 Part 2: first-token drift p50 0.22, max 0.45 nats; 39 / 40 answers agree). Robot accuracy is reported split WARM / COLD from the request log's cache_path.

