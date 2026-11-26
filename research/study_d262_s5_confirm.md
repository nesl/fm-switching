# D262 s5 CONFIRM (2026-11-26T18:41Z), as reported by the H100 (not re-scored): rung 3, 16 devices, `_c3-11-2`, s5 (`_preD249` name-only label); valid, SA OK, 0 errors, 0 ENOSPC, live2 a99fffa5; started 10:15. **The regime holds at s5: two of the three D253 conditions, as at s4.**
| D253 condition | s5 | s4 (P3) | verdict |
|---|---|---|---|
| (1) server kv_offload max at or above 0.99 | max 0.218 (0 samples >= 0.99); planner host peak 28,914 of 110,630; peak resident 63,069 against 62,944 (3 epochs over) | | **FAIL** |
| (2) idle-gap P(cold) above 0.10 | **0.12 on n = 25** (all 25 with a request); deciles 0, 0.199, 0.801, 0.841, 0.853, 0.879, 0.886, 0.908, 0.919, 0.93, 0.939: 0.5 sits in the empty gap 0.199 to 0.801 (width 0.60), not inside a mass | 0.179 (n = 39) | PASS |
| (3) planner evicted above 0 | 3 (server-side evictions not recordable) | 2 | PASS |
**Robot three together:** cloud on-time 143/182 | accuracy on served 0.399 | cbd 66 = cloud 57 + device 9 (standing 39). Single-shot 215/238. Dashcam 4,637/5,894 (worst 0.777). **Census both ways:** 16 robots, 14 sustained cold spans, 9 robot questions inside the spans (no-request proxy); decision-kind declines 12 total (8 inside spans) = recall_REJECT 12, release_infeasible_recall 0, budget_refusal_recall 0: closure holds.
