# Re-ask lists for StudyORIN-REC REASK (D161 (3))

One JSONL per seed, seeds 4, 5, 6, 7 (never 1-3, held out). **398 rows total.** Produced by
`experiments/orchestration/live2/v5/reask_trace_proofs.py`; proofs in
`results/orchestration/live2/frozen_test/reask_trace_proofs.json`.

Row fields, per re-ask:

| field | meaning |
|---|---|
| `seed`, `device_id`, `session_id` | the cell and the robot session |
| `question_id` | the LH-REQ question, the SAME id as the original ask |
| `reask_time` | the re-ask instant, **run wall clock**, same clock as the trace |
| `reask_time_session` | the same instant as a session-local offset |
| `ask_time`, `ask_time_session` | the ORIGINAL ask, for the parity control |
| `reask_index` | 1-based index of this re-ask within its session |
| `history_tokens` | D2 cloud-side history at the re-ask, recomputed for the later time |
| `device_latency_s_warm` | the committed measured warm latency for this question |
| `opportunity_id`, `reask_of` | this re-ask's id and the original's id in the same trace |

**RECENT-window definition, confirmed as the Orin proposed it:** the committed 60-frame last-120 s
filter over the D2 frame list **ending at `reask_time`**, matching StudyORIN-REC part 1.

**Parity control:** at `ask_time` the recorded answer must reproduce part 1 / WARM for that
`question_id`. All 69 pool questions are present in the committed warm table, so a mismatch is a
real disagreement and not a lookup miss.

**Why this measurement is wanted:** the trace freezes a re-ask's device answer at the original
ask (the D87 table is keyed on `question_id` alone), so re-asks reuse a stale answer. The harness
models the device as holding growing history while its accuracy is fixed, which understates the
device and therefore overstates the benefit of escalating. Cells run before this record lands are
labelled **PROVISIONAL**; when it lands they are re-scored offline and the label is removed.

**What it does not fix:** the clustered effective n. Re-asks draw from questions already asked in
the same session, and 14 of 17 robot sessions at seed 4 hold exactly one question, so the cluster
count is the distinct-question count. Seeds are the lever that moves it: 20, 25, 20 and 22 distinct
at seeds 4, 5, 6, 7, **57 of the 69 pool over the four seeds, 82.6 percent coverage.**
