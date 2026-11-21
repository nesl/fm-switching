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

## CORRECTION: the "tripwire" I reported here was wrong in its direction

The first version of this README said that exporting `LIVE2_DEVICE_LATENCY` would make the scorer
REFUSE on roughly 119 of 139 distinct robot qids. That is wrong, and the error was mine.

`score.py:209` reads `DEVICE_LATENCY_SOURCE = os.environ.get("LIVE2_DEVICE_LATENCY",
"orin_rec_warm")`: the measured Orin WARM table is the DEFAULT, not an opt-in. Coverage of the rows
the scorer actually reads, `device_answers` with `kind == "recall"`, is **132 of 132 with zero
refusals**. My 119-of-139 count was taken over `recall_question` TRACE RECORDS, which include
assistance questions and questions that never become a scored robot answer row, so it was simply
the wrong denominator.

The real exposure is the opposite of what I described, and smaller: setting
`LIVE2_DEVICE_LATENCY=trace` would DOWNGRADE first asks to the D87 ORIN2 interpolation, which
`score.py:212-213` already labels SUPERSEDED.

## Device-latency definitions: already identical in the scored quantity

Measured on seed 4 under the driver's rq30 arguments: 20 first asks and 112 re-asks, and the
scorer takes **all 132** from the warm table (20/20 and 112/112), median 0.2697 s and 0.2673 s.
Nothing needed fixing in the scorer.

The two definitions differ only in the trace's own `device_latency_s` field, which the scorer
ignores by default: `trace.py:773` writes the D87 interpolation for a first ask (median 0.1475 s)
while `trace.py:879` writes the warm value for a re-ask. **By-deadline outcomes changed: 0.**
132 of 132 are within the 3.0 s deadline under either source, with a maximum of 0.3065 s.

`trace.py:773` was deliberately NOT edited: changing the trace would move trace content and digests
under a running sweep, and the scorer, which is authoritative for the scored quantity, is already
correct. See `device_latency_definition_check.json`.

## Second-order, for whoever settles the robot device table

On the fallback path a RE-ASK's `device_latency_s` is the warm measurement (`trace.py:879`) while a
FIRST ask's is `device_recall_latency_s(hist_tok)`, which grows with history. The two asks of the
same question therefore carry latencies from two different definitions. That is the inconsistency
D161 (3) set out to remove, and it is currently removed for re-asks only. It should be settled
before the paired within-question analysis is read, because that comparison is exactly what
straddles the two definitions.
