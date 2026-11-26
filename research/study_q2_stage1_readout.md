# `-q2` STAGE 1 READOUT (2026-11-26T02:18Z): BOTH GATES FAIL, ON BOTH CONDITIONS. Records and observations only; nothing is proposed or applied overnight.

| s4 | arm | cbd | dashcam | TOUCH | HOLD_BACK | gate |
|---|---|---|---|---|---|---|
| 1x | rung 3 | 83 | 8,377 | 2,674 | 2 | comparator |
| 1x | `-q` | 79 | 8,719 | 906 | 87 | FAIL (D276 amended rule) |
| 1x | `-q2` | 82 | 7,303 | 10,446 | 6 | FAIL: cbd 82 < 86, dashcam -1,074 |
| `_kv0.5r_h0.5` | rung 3 | 72 | 6,112 | 1,434 | 4 | comparator |
| `_kv0.5r_h0.5` | `-q` | 77 | 6,759 | 787 | 93 | PASS |
| `_kv0.5r_h0.5` | `-q2` | 65 | 4,234 | 5,257 | 4 | FAIL: cbd 65 < 75, dashcam -1,878 |
**Observations (one seed per cell; correlational across arms, NOT a tested cause):**
1. **The exclusion did what it was built to do on its own target: HOLD_BACK fell from 87 and 93 to 6 and 4, so the pathology the diagnosis found is removed.**
2. **TOUCH tracks the arm in the same order in both conditions: `-q` 906 and 787, rung 3 2,674 and 1,434, `-q2` 10,446 and 5,257 (3.9x and 3.7x rung 3).**
3. **Dashcam falls monotonically with the TOUCH count in all six points (1x: 8,719, 8,377, 7,303; halved memory: 6,759, 6,112, 4,234).** Under pressure robot cbd also falls monotonically with it (77, 72, 65); at 1x it does not (79, 83, 82).
4. **So the two conditions agree on one pattern: the arm that touches least did best under pressure and the arm that touches most did worst. `-q` passes under pressure partly because it under-touches; `-q2` removed the brake that was throttling touches and over-touched. The worst dashcam device fell to 0.279, close to the 0.25 target.**
**Per the pre-registered prediction the margin (0.331566) is the next suspect and it is NOT re-derived (D259 stands). Whether the harmful axis is touch volume itself is untested: the dry replay showed the halved margin raises rung 3's own touches from 2,956 to 9,484, which would also over-touch.**
**Decisions for the user (nothing applied): whether the `-q2` line stops here; whether a touch-volume or margin intervention is worth a new pre-registered gate; the held `-q` pressure seeds s5-s7 (`-q2` does not pass, so by the standing rule the user decides).**
