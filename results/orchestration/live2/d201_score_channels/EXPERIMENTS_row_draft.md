# Draft EXPERIMENTS.md row for D201 / D205 (A DRAFT, NOT APPLIED; `research/*.md` is the main session's)

No E-id exists for this fix. The defect was found under `StudyEXIT-EP` (section 6), whose own row
says `E-id PROPOSED, NOT YET CONFIRMED` and `STEP 2 STOPPED IT`, and the D205 rulings created work
that is not that study. Per CLAUDE.md ("Find or request an E-id ... If no matching row exists, stop
and ask"), **an E-id is requested before any rerun is scored.** Nothing in the committed artefacts
claims one.

Separately and already reported: `research/EXPERIMENTS.md` has **no E-id row for
StudyFROZEN-test**, which owns `baseline_prescreen.json`, `baseline_prescreen_seed0_exclusions.json`
and `baseline_matrix_table.json`, the three files holding the constant-decision evidence. They are
indexed in `results/INDEX.md` only.

| field | draft value |
|---|---|
| E-id | **requested** (suggest `StudySCORECHAN`) |
| purpose | orchestration |
| claim | the live2 harness and the v1 live adapter never delivered a device or cloud score to a deciding arm, so every arm that reads a score VALUE decided on a literal `0.0`, which is the MAXIMUM of `log P(Yes)` and therefore escalation on every instant; with real scores delivered and the window sliced to the episode, the arms that read scores change and the arms that do not are byte-identical |
| status | code and proofs COMMITTED AND PUSHED in five commits (`de23b354`, `9b49801a`, `13e9978c`, `8986f593`, `2487e345`). **The result is not a settled finding: two of the three fixed arms did not move, and that is an open stop condition, not a negative about either policy.** |
| mechanism_verification | Step 2 PASS: the census goes from 215,996 values with ONE distinct value (`0.0`) to 211,737 device-channel values with 921 distinct, range -20.6513 to -0.0231. Step 2b PASS for the switch: the decision logs differ, and they differ for exactly the arms that read a score value. **Step 2 FAILS at the LAST link for two arms:** the quantity is live and varies and the decision does not move (inar-vl 1.0 to 1.0, hybrid-llm 0.0 to 0.0), so for those two the chain is CANCELLED BY GEOMETRY / a threshold question and the experiment cannot yet discriminate. Step 4 negative control: `confidence-cascade` 0.9165 to 0.284 shows the mechanism drives a result where it can act. |
| consistency_check | check 7 is the headline and it FAILED on the intended bar: the committed 2026-11-20 `baseline_prescreen.json` (`_provenance.git_commit` `62edb7fd`) is separated from the work sha by 875 commits, 59 of them on the decision path, and already disagreed with pristine code at that sha for `confidence-cascade` (13,564 / `7212c388684ed51d` against 13,570 / `88fbe5619f9abe74`) among others. It is NOT a valid before side for any change made after 2026-11-20, and both sides of the diff were therefore run from two trees at ONE sha. check 3 PASS: a constant where a distribution was expected is exactly what was found, and the distribution after the fix is reported with its range. |
| output | `results/orchestration/live2/d201_score_channels/` (six JSONs plus `reports/study_score_consumers.md`) |
| superseded | the live2 cells of SEVEN arms, not the two D201 named. The authoritative list is `d201_superseded_cells.json`, and `results/INDEX.md`'s header carries the exclusion line for the Orin's figure runs. |
| open | an E-id; the two arms that did not move; and `routellm`, which D205 (1) puts in NEITHER the fix list nor the drop list although its behaviour changed with this patch (it does `from hybrid_llm_adapted import _features` at `routellm_adapted.py:32`). |
