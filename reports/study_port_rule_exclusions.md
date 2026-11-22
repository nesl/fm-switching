# Port-rule exclusions from the scored baselines (D130, user addendum 10 item 1)

User decision 2026-11-22: `cascade-routing` and `r3-streaming` are EXCLUDED from the scored
baselines under D130, which says an arm whose mechanism cannot be expressed in the live setting is
DOCUMENTED, not forced. The paper lists them with the reason. Their cells are kept for provenance
and are not deleted, not marked INVALID, and not recomputed.

The rule they fail is the citing rule in CLAUDE.md: a port's proofs must include that its
CHARACTERISTIC DECISION occurs at least once. Well-formedness and fairness checks establish that an
arm is legal and fairly treated; neither establishes that it does anything. Both arms pass the
former and fail the latter, which is why this needed a count rather than a review.

## cascade-routing

WHICH STEP FAILS: the port rule, the characteristic-decision count. Zero robot escalations in both
committed cells (20 of 20 and 25 of 25 decisions are declines).

WHY IT FAILS BY CONSTRUCTION: its card's routing method is inexpressible in this setting. The
sufficiency proxy the card specifies can never fire here, so the escalation branch is unreachable
rather than merely unvisited. This is the arm whose port already carried an open issue for the same
reason, and it is the motivating failure recorded in CLAUDE.md: a port that passed BOTH required
proofs perfectly, 0 illegal actions across 3,001 epochs and a fairness digest matching the
committed control, while producing ZERO decisions of its characteristic kind.

CONSEQUENCE IF IT WERE SCORED: it sits exactly on the arm-independent device-only floor in every
committed cell, so a table listing it as a baseline reports the device floor under an arm name.

CELLS KEPT FOR PROVENANCE: both committed cascade-routing cells, unchanged.

## r3-streaming

WHICH STEP FAILS: the same one, and it was NOT previously flagged. Zero robot escalations in ALL
FOUR committed cells: 19 of 20, 126 of 132, 25 of 25 and 127 of 127 decisions are declines, with no
`release_recall` emitted at all.

WHY IT FAILS BY CONSTRUCTION: its escalation test is never reached, so the arm never makes the
decision it exists to make. The remedy is in the arm body and its observation wiring, which is a
port question and not a scoring one.

CONSEQUENCE IF IT WERE SCORED: identical to cascade-routing, and the two together would have put
the device floor into the baseline table twice under two different names.

CELLS KEPT FOR PROVENANCE: all four committed r3-streaming cells, unchanged.

## What is NOT excluded, and why the distinction matters

`confidence-cascade` PASSES the port rule: 57 escalations at seed 6, 44 at seed 4, 35 at seed 5,
counted from the decision log and independently reconstructed offline from the committed StudyE7
confidence table plus the DEV-fitted floor, the two agreeing on every row. It stays in the scored
baselines. Its separate problem is that NONE of those 57 escalations was delivered inside the 3 s
deadline at seed 6, nor at seed 5, which is a live-timing matter already queued by D154 (5) as a
RERUN item and not a re-score and not an exclusion.

`streamscout` also passes, with 132 of 132 escalations.

## The observation that started this, and what it actually was

The flagged anomaly (confidence-cascade seed 6 scoring 0.0579 against peers at 0.0826) was a MISREAD
OF THE FLOOR, not a fault. The device floor is the arm-independent 0.057851, 7 of 121, written
identically into all 17 seed-6 rq30 cells including confidence-cascade's own, so that arm sits
exactly AT the floor and nothing is below it. The 0.0826 is the floor plus three cloud-standing
wins on question ids the three peers share exactly. The 7-versus-10 gap is ONE LH-REQ question
re-asked three times by rq30 at the same confidence 0.999966, weight 3 of 121: not a three-question
effect and not a direction.

A REAL below-floor effect does exist elsewhere, in 10 of 127 scanned cells, where an ON-TIME but
WRONG cloud answer legitimately replaces a correct device answer under the standing-answer rule
(worst: simplestream seed 4 at 0.1439 against the 0.3712 floor, with 132 of 132 cloud standing). So
an escalation CAN make a question worse than not asking, by being wrong rather than by being late.
Every such cell has n_cloud_standing above zero, which is the signature to look for. Full diagnosis:
`results/orchestration/live2/frozen_test/cascade_below_floor_diagnosis.json`.
