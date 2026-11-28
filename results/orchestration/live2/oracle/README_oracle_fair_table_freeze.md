# FAIR oracle table: freeze record (2026-11-27)

**Frozen file:** `results/orchestration/live2/oracle/oracle_fair_table.json`
- sha256: `f67be762b15762e44d0cb1bbad9924599f896cc07e3bb4b6cf0c91c4b408c562`
- git blob hash: `947ad92a102581a9fcf0e30f7ac936832a15f511`
- last changed in commit `d6b24cb9` (2026-11-25 12:44, "StudyORACLE D268 corrected: FAIR table conditioned on context sent, not cache state"); written by `experiments/analysis/oracle/oracle_fair_table.py` (a51c219a), model qwen3vl32b.

**Class accuracies (pooled across arms, seeds 4 to 7, n16 cells at 1x and `_kv0.5r`; WITH_HISTORY iff prompt_tokens >= 2,000):** recall|cloud|WITH_HISTORY 0.568799 (7,201 of 12,660); recall|cloud|WITHOUT_HISTORY 0.212222 (639 of 3,011); recall|device|NA 0.257732 (250 of 970); single_shot|cloud|COLD 0.621881 (648 of 1,042); single_shot|device|NA 0.547985 (571 of 1,042).

**Oracle total used by the scoring scripts:** robot rows x (0.568799 - 0.257732) + SS rows x (0.621881 - 0.547985), with the FULL row counts of the cell (SS rows, not the SS on-time count). Verified against the reported totals: n16 s4 67.44 (132 robot, 357 SS rows), n20 s4 105.55 (283, 237), n32 s4 164.82 (417, 475), B2 s4 88.82 (229, 238), n20 s5 86.79 (222, 240).

**FREEZE (user ruling, 2026-11-27):** the definition is unchanged (option (a)). Seeds 1 to 3 (post-freeze held-out) are scored with THESE EXACT dev-seed constants. The table must NOT be regenerated once held-out cells exist; if anything triggers a regeneration, STOP and report. Scoring scripts read the constants from this file (not hard-coded rounded values) and print the constants, this source path with its git hash and the robot and SS row counts used for the oracle total.
