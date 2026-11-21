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

**RECENT-window definition. CORRECTED 2026-11-21 08:45; the first version of this line was wrong.**
The committed 60-frame last-120 s filter over the D2 frame list ends at **`reask_time_session`**,
the EPISODE clock, not at `reask_time`. The D2 frame store is episode-indexed, and the generator's
own history accounting uses the episode clock too (`DS.d2_frames_in(0.0, t_ask_session)`), so
`history_tokens` in these rows was always computed that way. My earlier prose said `reask_time` and
was simply wrong.

The Orin caught it and its **parity control is the proof**: ending the window at
`ask_time_session`, seed 4 reproduces part 1 on **19 of 20** (the single miss is the declared
prefix-cache near-tie drift, D81) and WARM on **20 of 20**, with `prompt_tokens` p50 5,510 inside
the committed 5,476 to 5,682 band and warm TTFT p50 0.209 s. On the wall clock the joined sessions,
whose episode origin is offset (one measured at -7.32 s), would have filtered the wrong frames and
parity would have failed on exactly those.

**So: `reask_time_session` for anything indexed on the episode; `reask_time` for anything on the
run wall clock.** The two differ by the session's episode origin, which is non-zero for a joined
session and which `t - t_ask_session` recovers.

**Measured consequence, which is why the PROVISIONAL label matters:** on seed 4, **34 percent of
re-asks get a different device answer** from their original. That is the size of the error the
frozen D87 table was carrying, and it is not a rounding effect.

**Parity control:** at `ask_time_session` the recorded answer must reproduce part 1 / WARM for
that `question_id`. Result on seed 4: 19 of 20 against part 1, 20 of 20 against WARM. All 69 pool questions are present in the committed warm table, so a mismatch is a
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

## Joining the Orin's record back

`results/sember/study_orin_rec/orin_rec_reask_seed{4,5,6,7}.jsonl` (StudyORIN-REC-REASK, first seed
at `cc24d56`). Each row carries `reask_time` and `reask_time_session` verbatim from these lists plus
the measured letter, `letter_prob` (logprob mass on the emitted letter), TTFT, completion, prompt
and cached tokens, `opportunity_id` and `reask_of`. **Join on `opportunity_id`.** Note that
`opportunity_id` is assigned in canonical trace order, so it is only valid within the same cell
build; the join holds because these lists and that record come from the same trace.
