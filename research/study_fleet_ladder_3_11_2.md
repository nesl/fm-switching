# FLEET LADDER, rung 3, `_c3-11-2` mix, 1x memory, s4, no outage (2026-11-26T19:45Z). PROVISIONAL; the H100's cell figures plus my CPU rescoring; one point per size, one seed.
**B1, n20 `_c3-11-2` (the knee check; `covex-v6-fair-final_n20_s4_1200s_h27_3t_c3-11-2_L3_epg_rq30`; 11:22:46 to about 11:44; valid, SA OK, n_errors 1, 0 ENOSPC; live2 a99fffa5):** robot pool 283; cloud on-time 124/283 (0.438); accuracy on served 0.718; cloud-correct 89; harness cbd 131 = 89 + device 42 (standing 159); **cbd_expected at the D281 credit 0.257732 = 89 + 0.257732 x (283 - 124) = 130.0 (0.459)**; single-shot 163/237; dashcam 3,748/7,850 (0.477), worst device 0.448; opportunities 8,370; budget_spent_gpu_s 632.6; release_infeasible 3,093; recall_REJECT 62; peak resident 64,084 against 62,944 (12 epochs over); host peak 46,738; planner evicted 12; belief_to_cold 66; TOUCH 3,134; HOLD_BACK 2; pieces 333; emulator lateness p99 0.155 ms, MAX 77.7 ms (above the 50 ms limit at the max; only p99 is limited).
| 3:11:2, rung 3, s4, 1x | robots | robot cloud on-time | dashcam on-time | peak resident / 62,944 | evictions | rejects |
|---|---|---|---|---|---|---|
| n16 | 11 | 0.77 | 0.81 | 63,215 (100%) | 2 | 21 |
| **n20** | **14** | **0.438** | 0.477 | 64,084 (102%) | 12 | 62 |
| n24 | 17 | 0.314 | 0.392 | 64,385 (102%) | 19 | 103 |
| n32 | 22 | 0.127 | 0.134 | 65,775 (105%) | 33 | 170 |
**The collapse is steep between 11 and 14 robots (0.77 to 0.44), then flattens (0.44, 0.31, 0.13): the knee, if healthy-near-the-cap means within about 10 points of n16, lies BELOW n20 (a fleet of 12 or 13 robots would be the untested candidate); n20 already evicts and rejects 62 asks.** Peak resident is within 5 percent of the cap at every size from n16 up, so the cap is reached at about 11 robots and the service collapse follows the evictions and rejects, not the resident level alone. (n20 and n24 at 40:40:20 had no evictions and robots at 85 to 87 percent.)

## USER DECISIONS AND TRACKING, 2026-11-26T19:51Z
(1) **No n17 or n18 cell now.** The ladder above (n16 0.77, n20 0.438, n24 0.314, n32 0.127 robot cloud on-time) is the rung 3 BASELINE CURVE for F9; **the evaluation is whether the new layers move it to the right.** **The step-1 cell list is now: n16 1x (no-harm), `_kv0.5r_h0.5`, n20 `_c3-11-2` (replaces "knee fleet"), n32 `_c3-11-2`.** (2) The outage tests use the n16 `_c3-11-2` control and outage cells as already ruled. (3) 0b: rewire to book from P's cached fraction (no last-cached-fraction scaling); the share-check feed is decided after the Phase A validation; the 0b + B push is HELD until P's open decision is settled (see the P note).
## EMULATOR LATENESS MAX PER CELL (limit 50 ms; p99 is the limited quantity and is far below it in every cell, 0.15 to 0.19 ms; flagged if the MAX keeps rising at larger fleets)
| cell | max lateness (ms) | p99 (ms) | note |
|---|---|---|---|
| n16 40:40:20 | about 23 | | earlier job (rising to 80 at n24 in that series) |
| n24 40:40:20 | 79.8 | 0.19 | above 50 ms at the max |
| n20 3:11:2 | **77.7** | 0.155 | above 50 ms at the max |
| n24 3:11:2 | 25.2 | 0.185 | under 50 |
| n32 3:11:2 | **58.5** | 0.153 | above 50 ms at the max |
**Reading: the max is NOT monotone in fleet size** (n20 3:11:2 77.7, n24 3:11:2 25.2, n32 3:11:2 58.5; n24 40:40:20 79.8); it looks like isolated host-contention spikes (the H100 host CPU was shared with other users in the n32 and n16 1x cells), not a trend; it will be tracked per cell and flagged if a larger fleet raises it persistently; every cell is still valid (only the p99 is limited).
