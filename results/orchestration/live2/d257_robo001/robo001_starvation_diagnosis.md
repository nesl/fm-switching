# D257 (2): WHY `robo001` GOT 4 OF 17, AND WHY IT COST ALMOST NOTHING

**CPU diagnosis from committed artefacts only. Nothing fixed. No GPU.** Cells: P1 =
`covex-v6-fair-final_n20_s4_..._preD249`; reference = the same arm's n16 s4 `_rep2`.

## *** THE CAUSE: A SINGLE TELEMETRY ZERO LATCHES A SESSION COLD, AND A REJECTION CANNOT UNLATCH IT ***

**`robo001|s001` lost its prefix in the engine's cache at t=743.9.** Two consecutive build pieces returned
`cached_tokens = 0` (t=743.94 pt=6,041; t=789.94 pt=7,031). The D150 telemetry corrector is in APPLY mode
and demoted the session's belief to COLD (`coordinator.py:1941-1951`), and **the belief is exactly what the
arm reads as readiness** (`cstate.py:669-683` builds each `RecallQuery` with `readiness = s.readiness()`,
the belief argmax at `cstate.py:245`). `residency.jsonl` shows `believed_tier = cold` from t=745.88 to
t=1065.85: **a 320-second unbroken cold span. ALL 12 of its remaining questions arrive inside it**
(t=833.86 to t=1029.51).
**With readiness COLD the feasibility test at `hybrid/hybrid_arm.py:412` fails the 3.0 s deadline, so the
arm returns `RecallAction(..., "REJECT")` at `:437`, which the coordinator turns into a device answer and a
`decline` row at `coordinator.py:998-1009`.** **The cell has 15 `recall_REJECT` and 12 OF THE 15 ARE
`robo001`; the other 3 are `robo006`, the only other robot with a sustained cold span.**

*** THE AMPLIFIER, AND IT IS THE FINDING: A REJECTION SENDS NOTHING, NOTHING SENT MEANS NOTHING RE-WARMS
THE PREFIX, SO THE NEXT QUESTION IS REJECTED TOO. ***
**The loop is breakable and one robot broke it: `robo004|s001` dropped once at t=770.83 and its NEXT build
piece at t=816.84 came back WARM (`ct=4,048`), after which its recall was served and it finished 28 of 28.**
**`robo001` received NO FURTHER REQUEST OF ANY KIND after t=789.94, for the remaining 276 s of the session.**
**Why `robo001` and not another: a 366-second question-free opening (session opened t=468.2, first question
t=833.9), so its prefix was the least-recently-useful in a 20-device cell.**
*** AND THE READINESS LABEL, NOT THE TOKEN COUNT, IS WHAT FLIPPED THESE: verified from `costs.py` -
16,654 tokens COLD = 3.70 s and 25,400 COLD = 6.68 s, both over the deadline; the SAME token counts
GPU-WARM = 0.55 s and 0.80 s, both inside. ***

## THE FIVE CHECKS: ONE CAUSE, FOUR CLEAN NEGATIVES

| # | check | verdict |
|---|---|---|
| 1 | deficit weight `w_d` | **NOT the cause.** `w_d = 2.477124`, the MAXIMUM recall weight in the cell. Trajectory reconstructed from the 17 raw outcomes lands on the committed value to six decimals. **Neither of the ruling's two readings holds**: not pinned near 1, not at 3 all run (it decayed to 1.222 while being served, then climbed 1.5 to 2.5 through the decline burst). *** AND ORDERING IS STRUCTURALLY INCAPABLE OF HELPING: the weight's only live consumer is a sort key, and these 12 never entered a queue - they were rejected at the arm's own feasibility branch before any release. *** |
| 2 | arrival timing against load | **NOT the cause, refuted by a zero-load decline.** The question at t=881.25 was declined with **0 requests in flight and 0 uncached tokens outstanding**, while the busiest instant in the table (10 in flight, 6,040 uncached) was **served on time**. |
| 3 | the 32,768 context limit | **NOT the cause, and the switch is proven ARMED rather than absent.** Largest history anywhere 25,576 tokens; the limit read live from the server's argv. `over_limit_infeasible` is ABSENT from `arm_stats`, i.e. never incremented, so this is "armed and never fired" and the D175 refused-request reading is excluded. |
| 4 | the decisions | *** THIS IS THE CAUSE. *** 4 on time, 1 late, **12 declined** via `hybrid/hybrid_arm.py:437`. **`release_infeasible` = 0 for recall**, confirming that all 3,191 in the cell are ALERT: the losses came by a DIFFERENT path and it is the arm-side REJECT. |
| 5 | is `robo001` also worst at n16? | *** NO, AND THIS IS THE DISCRIMINATING CHECK: THE LOAD DID IT. *** Verified independently: n16 `robo001` = 0.952, **mid-pack**; `robo006` = 0.867 is worst. **And n16 has ZERO declines** (`recall_REJECT` absent, `recall_CLOUD = 489`). |

**Not KV pressure: `kv_capacity_enforced: true`, `peak_tokens: 53,192` of 62,944, `epochs_over_cap: 0`,
`evicted: 0`, `offloaded: 0`. The cold belief came from the engine's own telemetry, not a placement action.**

## *** AND THE VALUE FINDING, WHICH CHANGES WHAT THE 4 OF 17 MEANS. VERIFIED INDEPENDENTLY. ***

| quantity | P1 (n20) | n16 `_rep2` |
|---|---|---|
| questions in pool | 17 | 21 |
| **distinct question ids behind them** | **3** | **2** |
| cloud on-time | 4 (0.235) | 20 (0.952) |
| *** cloud accuracy ON SERVED *** | *** 0 of 4 = 0.0000 *** | *** 0 of 20 = 0.0000 *** |
| device answers on time | 17 of 17 | 21 of 21 |

*** `robo001`'s CLOUD ANSWERS ARE WRONG WHETHER IT IS SERVED 4 TIMES OR 20. So the on-time collapse cost
essentially nothing in value. ***
**These are real letters, not the placeholder `"X"` of CLAUDE.md's motivating failure: gold E against cloud
C on `s000` in both cells, gold A against cloud D on n16's `s001`. The 12 declined questions carry
`cloud_letter = None` because no cloud answer was ever produced.**
*** REPORTING "4 OF 17" AS `robo001`'s FAILURE OVERSTATES THE HARM BY ROUGHLY AN ORDER OF MAGNITUDE,
BECAUSE THE 13 EXTRA ON-TIME ANSWERS IT WOULD HAVE GOT ARE, ON THIS EVIDENCE, 13 WRONG ANSWERS. That is
D257 (3) vindicated on the very question the ruling asked about. ***
**ONE FIGURE UNRECONCILED AND FLAGGED: the diagnosing agent reports `correct_by_deadline` = 1 of 17 (the
late-cloud question where the correct device answer stood); this session's independent read of the
`correct_by_deadline` field returned 0 of 17. The difference is one question and changes nothing, but it is
recorded as unreconciled rather than resolved by preference.**

## *** CORRECTION: THE DOSE-RESPONSE CLAIM IS WRONG. THERE ARE THREE SUSTAINED COLD SPANS, NOT TWO, AND THE THIRD HAS QUESTIONS INSIDE IT AND NO DECLINES. ***

**Recomputed from `residency.jsonl` with an explicit definition (a cold span = a maximal run of consecutive
rows for the SAME `session_id` with `believed_tier == "cold"`, and SUSTAINED means more than one row):**
```
robot      longest sustained span   questions INSIDE it   declines
robo001            320.0 s                 12               12
robo005            181.5 s                  8                0     <- NOT IN THE TABLE ABOVE
robo006            159.2 s                  3                3
all others           0.0 s                  0                0
```
*** SO THE STATEMENT ABOVE, "the only two robots with a sustained cold span are the only two with
declines", IS FALSE. `robo005` has the SECOND-LONGEST span, EIGHT questions arriving inside it, and ZERO
declines. The "perfect dose-response" is WITHDRAWN. ***

**AND THE OBVIOUS EXPLANATION IS REFUTED, BY ME, BEFORE BEING OFFERED.** The cold-feasibility threshold is
`recall_ttft_s(tok, COLD) = tok / 4500`, so a history under about 13,500 tokens clears 3.0 s even when
cold, which would spare a small-history robot. **`robo005`'s prompt tokens reach 25,150, well above that
threshold, so SIZE DOES NOT EXPLAIN IT.**
**ONE CANDIDATE REMAINS AND IS NOT ESTABLISHED: `robo005` issued 638 requests against `robo001`'s 24, and
all 606 `state_action` rows in the cell name `robo005|s001` alone, so it was the one session the state
planner was actively touching.** **That is CONSISTENT with the amplifier claim - traffic breaks the latch -
but it is NOT PROVED, because the history size AT the in-span question instants was not checked, only the
per-robot maximum. Reporting it as the cause would be the second guess after the first was refuted, so it
is recorded as a candidate and nothing more.**

*** WHAT SURVIVES UNCHANGED, AND IT IS THE PART THAT MATTERS FOR THE FIX: THE AMPLIFIER. A rejection sends
nothing, nothing sent re-warms the prefix. `robo001` had NO REQUEST OF ANY KIND for 276 s and lost 12 of
17. `robo004` dropped once, its next piece came back warm, and it finished 28 of 28. `robo005` is the
robot with the MOST traffic in the cell and has ZERO declines. All three point the same way. *** **The
three-condition story that would have replaced the dose-response is not established either, and is not
claimed.**

**ATTRIBUTION, CORRECTED: this census was built by this session's own diagnosing agent from
`residency.jsonl`. It was described to the accelerator box as that box's work, which it was not. The box
had computed the D253 `P(cold)` over idle 30-to-60-second questions with deciles, a different quantity.**

## WHAT THIS MEANS FOR D249

- *** DO NOT FIX THIS WITH ORDERING. The weight was already 1.5 to 2.5 on all 12 lost questions and the
  loss is UPSTREAM OF ANY SORT. ***
- *** THE ACTIONABLE SURFACE IS THE NON-RECOVERY LOOP, and the RECENT channel was feasible at every one of
  the 12 instants and was never offered: `recall_ttft_s(467, "COLD")` = 0.104 s, verified. *** A re-warm
  triggered by a rejection, or a RECENT fallback instead of a flat REJECT when readiness is COLD, addresses
  the actual mechanism.
- **WATCH THE BELIEF LABEL, NOT THE TOKEN COUNT.** The over-limit rule is irrelevant at this fleet size:
  nothing came within 6,000 tokens of it. **The binding quantity is a belief flipped by a single telemetry
  zero.**
- **DO NOT RANK ROBOTS BY CLOUD ON-TIME.** `robo001` is the worst robot on on-time at P1 and also one of
  the two LEAST VALUABLE robots in the cell.

## LIMITS, STATED

**`metrics_health.state = "never_scraped"` in this cell, so there is NO engine-side KV or cache-hit series
to corroborate the prefix-drop signal, and the diagnosis cannot say WHY the engine dropped it.** The
downstream chain (belief to COLD to REJECT) does not depend on the reason.
**The n16 chain's `prompt_tokens` is used as a proxy for P1's token trajectory at matched session age. Valid
for the order of magnitude, which is all the arithmetic needs, but the sessions are DIFFERENT ids with
different questions because the trace is regenerated per fleet size. So n16 establishes that zero declines
occurred and that a warm 16k-to-26k history clears 3.0 s; it does NOT establish that P1's specific 12
questions would have been answered, and emphatically not that they would have been answered CORRECTLY.**
