# rq30 question-id coverage against the measured warm-latency table

Produced on flash (A6000) 2026-11-21 at the H100's request, to clear SEED 7 before the D164
baseline matrix reached its 13 seed-7 cells. Dry trace generation only: no GPU, no server.

Arguments, the H100 driver's exact rq30 cell set: `robot_question_set=lh_req`,
`ss_question_set=ss2`, `dashcam_format=epg`, `robot_upload=per-frame`,
`robot_reask_mean_s=30`, ratio `40:40:20`, `n=16`, `run_s=1200`, mode A, seeds 4, 5, 6, 7.

## What was asked, and the answer

Whether every RE-ASKED question_id is present in `device_recall_warm_latency_s()`, since
`fleet/trace.py:879` does `float(warm_lat[qid])` and would raise. **It is, at all four seeds**:
0 uncovered re-ask rows at seeds 4, 5, 6 and 7 (112 / 102 / 101 / 83 re-asks). No table fix is
needed and nothing had to be worked around with a fallback.

## Why an earlier run of mine raised KeyError

`robot_question_set` defaulting to `eval`, which the driver never passes. Reproduced deliberately:
`eval` at seed 4 raises `KeyError '1d0e5d7328...'`; `lh_req` at seed 4 generates cleanly. The
H100's hypothesis was right; the harness is not at fault for its cells.

A first pass of mine also over-reported 357 "missing" ids. They are `realworldqa/*`, single-shot
ASSISTANCE questions that never pass through `warm_lat` at all. `rq30_robot_qid_gap.json` is the
narrower count, over robot rows only.

## The tripwire this exposed (condition matters)

Under `lh_req` each seed draws about 139 to 143 DISTINCT robot question_ids, of which about 118 to
119 are absent from the 97-entry warm table (the `lh_req` id set itself is 69). Re-asks are
unaffected. First asks are covered only because `scorer/score.py:246-248` consults the measured
table ONLY IF `device_latency_table()` is not None, i.e. only when `LIVE2_DEVICE_LATENCY` is set;
otherwise it falls back to the trace's own `device_latency_s`, which every answer row carries.

So committed cells are fine because they take the fallback path. If `LIVE2_DEVICE_LATENCY` is ever
exported to score against the measured table, which is where D155 and D161 (3) point, the scorer
will REFUSE on roughly 119 of 139 distinct robot qids per seed. It refuses rather than guesses, so
this surfaces as a stopped score, not a quiet wrong number.

## Second-order, for whoever settles the robot device table

On the fallback path a RE-ASK's `device_latency_s` is the warm measurement (`trace.py:879`) while a
FIRST ask's is `device_recall_latency_s(hist_tok)`, which grows with history. The two asks of the
same question therefore carry latencies from two different definitions. That is the inconsistency
D161 (3) set out to remove, and it is currently removed for re-asks only. It should be settled
before the paired within-question analysis is read, because that comparison is exactly what
straddles the two definitions.
