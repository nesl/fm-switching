# D250's HEADLINE IS 2.5x DIFFERENT DEPENDING ON ONE OPEN DEFINITIONAL QUESTION: WHETHER DEVICE ANSWERS COUNT AS CORRECT-BY-DEADLINE

**Gate cell: `covex-v6-fair-final` n16 s4 `_kv0.5r_h0.5_L3_epg_rq30_preD249`, ended 12:00:19, VALID, SA OK,
8,760 requests, 0 errors, 0 ENOSPC, digests equal. Both memory halves proven live (`c6fe754d`).**

## HOW THIS WAS FOUND, BECAUSE THE ROUTE MATTERS

**The reported `correct_by_deadline` of 0.545 EQUALLED the cell's robot cloud on-time fraction of 72/132 =
0.5455 exactly, and the relation `cbd = on_time_fraction x accuracy_on_served` - which fits all four
committed reference cells to within 0.006 - predicted 0.3715 instead.** **That relation was INFERRED from
four points, not read from the scorer, so it was raised as a discrepancy to settle from the source rather
than asserted as an error.** *** THE SOURCE SETTLED IT AGAINST THE INFERENCE, AND THE INFERENCE WAS
INCOMPLETE RATHER THAN THE FIGURE BEING WRONG. ***

**The real definition, `robot_headline.definition` per D155 (3): "the cloud's answer when it is delivered
within the deadline, otherwise THE DEVICE'S ANSWER IF THE DEVICE'S ANSWER ALSO ARRIVES WITHIN THE DEADLINE,
otherwise no answer." The inferred relation omitted the DEVICE term.**
```
GATE CELL  cloud 72 x 0.68056 = 49 correct ; device standing by deadline 60, of which 23 correct
           (49 + 23) / 132 = 0.5455, which equals the on-time fraction ONLY because 49 + 23 = 72
rep2       cloud 125 x 0.656  = 82 correct ; device 3 of 7 ; (82 + 3) / 132 = 0.6439, as reported
```
**The relation held on the references only because device fallback there is SEVEN questions. Here it is
SIXTY. So the five running baselines carry no defect.**

## *** THE CONSEQUENCE: THE 25 pp WAS REAL AND IT IS HIDDEN INSIDE cbd ***

| reading | gate cell | rep2 reference | delta |
|---|---|---|---|
| **cbd as defined, WITH device credit** | **0.545** | 0.644 | **-9.9 pp, looks MILD** |
| *** CLOUD-ONLY correct-by-deadline *** | *** 49/132 = 0.371 *** | *** 82/132 = 0.621 *** | *** -25.0 pp, looks SEVERE *** |

*** THE SAME CELL AND THE SAME DATA GIVE TWO HEADLINES 2.5x APART, DECIDED BY ONE DEFINITIONAL CHOICE. The
device credit recovers 17.4 pp of a 25.0 pp cloud-side collapse. ***

## WHY THE CREDIT IS NOT NEUTRAL, WHICH IS WHAT MAKES THIS A USER QUESTION

**The device answers are not equivalent to the cloud answers they replace:**
- **cloud accuracy on served 0.681 against device accuracy 0.371, so the device is 54 pct as accurate.**
- **60 of 132 questions, 45 pct, fall back to the device in this cell, against 7 of 132, 5 pct, in the
  reference.** *** SO THE CREDIT IS SMALL AND HARMLESS IN EVERY CELL MEASURED SO FAR AND LARGE EXACTLY HERE,
  IN THE CELL THE MEMORY RULING EXISTS TO MEASURE. ***
- Device latency 0.25 to 0.31 s with 0 late, so every one of the 60 arrives in time. The credit is earned
  under the metric as written; the question is whether the metric should grant it.

**`research/EXPERIMENTS.md` records device credit in robot on-time as an OPEN USER QUESTION. This cell is
where it decides the answer rather than decorating it.**

## WHAT IS BEING REPORTED GOING FORWARD

**Cloud-correct, device-standing and device-correct are carried BESIDE cbd in the six-baseline table, so
both readings are visible and neither is the default.** **This is the same discipline as D257 (3): a single
robot number cannot carry the result, and here even the composite cannot.**

## TWO OTHER CORRECTIONS RECORDED ON THIS CELL

1. *** THE ENGINE POOL WAS NEVER HALVED. 1,968 blocks x 16 = 31,488 tokens is the PINNED engine pool in
   EVERY cell, and the logical cap is what varies: kv1.0 = 62,944, kv0.5 = 31,472, kv0.25 = 15,736. SO AT 1x
   THE LOGICAL CAP SITS AT 2.00x THE PHYSICAL POOL AND CANNOT BIND. kv0.5r IS NOT "HALF THE MEMORY OF 1x";
   IT IS THE CONDITION WHERE THE CAP FIRST EQUALS THE HARDWARE. Every 1x-versus-kv0.5r comparison in the
   corpus reads as "cap above the hardware" against "cap at the hardware". ***
2. **ACCURACY ON SERVED RISING IS SURVIVORSHIP, NOT IMPROVEMENT: 0.681 here against about 0.653 in the
   references, while 50 fewer questions are served. The survivors are the warmer, easier ones. This is
   precisely why D257 (3) forbids quoting on-time alone.**
3. **The 0.5 cold threshold is NOT robust on this cell, unlike P3. P3 had an empty gap of width 0.460 around
   it; here the nearest point below is 0.448, so moving the threshold to 0.4 changes P(cold) from 0.40 to
   0.35. ON THIS CELL THE COLD COUNT TURNS ON ONE QUESTION.** Pressure readings: server kv_offload max
   0.311 with 0 samples at capacity; planner host peak 28,011 of 55,315 with 0 epochs over; GPU logical
   epochs over cap 5; **evicted 6**.
