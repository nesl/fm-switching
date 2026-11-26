# `-q2m` READOUT (2026-11-26T04:10Z): 1x FAIL by one (a tie with rung 3), HALVED MEMORY FAIL on both conditions. Records and observations only; one seed per cell.
| s4 | arm | cbd | cloud + device | dashcam (worst) | TOUCH | HOLD_BACK | gate |
|---|---|---|---|---|---|---|---|
| 1x | rung 3 | 83 (`_rep2` 85) | 82 + 1 | 8,377 | 2,674 | 2 | comparator |
| 1x | `-q2m` | 85 | 84 + 1 | 8,365 (0.673) | 1,336 | 3 | FAIL by 1 (85 < 86), dashcam holds |
| 1x | `-q2` | 82 | 78 | 7,303 | 10,446 | 6 | FAIL |
| halved | rung 3 | 72 | 49 + 23 | 6,112 (0.454) | 1,434 | 4 | comparator |
| halved | `-q2m` | 69 | 54 + 15 | 5,475 (0.404) | 375 | 2 | FAIL: cbd 69 < 75, dashcam -637 |
| halved | `-q` | 77 | | 6,759 | 787 | 93 | PASS |
| halved | `-q2` | 65 | | 4,234 | 5,257 | 4 | FAIL |
**Observations (one seed per cell):**
1. **The margin was the cause of `-q2`'s over-touching: it alone took TOUCH from 10,446 to 1,336 at 1x (the dry predicted 1,667) and from 5,257 to 375 at halved memory (no dry prediction), restored 1x dashcam to within 12 of rung 3, and brought cbd to a tie with rung 3's replicate.**
2. **At halved memory it touches LEAST of all four arms (375, against 787 for `-q`, 1,434 for rung 3, 5,257 for `-q2`) and still loses to rung 3 on both cbd and dashcam.** So under pressure the touch count is not what separates the arms: the earlier ordering (fewer touches, better outcome; see the `-q2` readout) does not continue below rung 3. Cause not tested.
3. HOLD_BACK stays low (2, 3) with the exclusion on, so `-q`'s brake pathology stays removed; `-q` remains the only arm that passed the halved-memory gate.
4. The live margin is bounded and inferred (below 0.799, clearly above 0.3316, at least about 0.658), not read; the dry census (0.65824) is the build-side proof.
**Per D286: queue nothing; rung 3 stays the candidate; the `-q` pressure seeds stay held. Decisions for the user in the morning: whether the margin and touch-volume line stops here; the held `-q` pressure seeds; the C5 attribution and never-released findings (`research/study_c5_attribution_touch_check.md`, `research/study_q2_c5_cap_never_released_check.md`) as the open lead.**
