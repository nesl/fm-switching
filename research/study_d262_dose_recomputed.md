# THE DOSE WAS RECOMPUTED AND THE RULING'S CORRECTION WORKED. BUT THE MECHANISM THE RULING NAMED IS CLOSED BY BUFFERING IN 0.88 SECONDS, AND THE LIVE CHANNEL IS A DIFFERENT ONE.

**CPU only, no cells, nothing committed to `experiments/`. D and the window are UNTOUCHED, still D = 120 s
fixed at 540.0 to 660.0 s.**

## 1. THE RULING WAS RIGHT AND MY ZEROS WERE ZEROS OF THE WRONG QUANTITY

**The first dose counted questions asked INSIDE the window and gave 2, 1, 0, 0. The corrected dose counts
questions asked AT OR AFTER the window start whose EVIDENCE falls inside it.**
| pair | added victims | **R1 distinct questions** | old wrong dose |
|---|---|---|---|
| s4, k 1 to 3 | robo003, robo009 | **1** | 2 |
| s4, k 3 to 5 | robo004, robo010 | **2** | 1 |
| **s5, k 1 to 3** | robo007, robo009 | **1** | **0** |
| **s5, k 3 to 5** | robo006, robo008 | **3** | **0** |
*** SO THE CORRECTION REMOVED BOTH SEED-5 ZEROS, EXACTLY AS THE RULING PREDICTED IT WOULD. ***
**The field chosen is the annotated ground-truth interval in the S-EMBER data, in the same session-time
coordinate as the ask time, so one subtraction maps it to run time. THE JOIN IS COMPLETE: 229 of 229 robot
questions have an interval.** **A pooled rate reads 49 percent, which looks like a half-failed join; the
other half is the 238 assistive single-shot questions, which have no such interval BY CONSTRUCTION. The tool
now splits the rate by device type so a complete join cannot be mistaken for a broken one.**
**Two candidate fields were rejected and named: the ASK time, which is what the first dose wrongly used, and
`history_tokens`, which says how MUCH history and not WHEN, so it cannot localise evidence in time.**
*** AND READ THE DISTINCT COLUMN, NOT THE INSTANCE COLUMN: with a 30 s re-ask mean a re-ask carries the SAME
question id and therefore the same evidence interval, so ONE affected question appears as up to ELEVEN
affected instances. The instance counts are 5, 9, 1, 22. ***

## *** 2. BUT THE FRAMES ARE BUFFERED, NOT DROPPED, AND THE DRAIN IS UNDER A SECOND ***

**`fleet/trace.py:1037-1047`: a victim's in-window history batch has its offer time set to the RECONNECT
INSTANT and NO RECORD IS DELETED. `:1048-1056` keeps a question's ask time. The committed uplink queue at
`fleet/links.py:112-120` then takes `t_start = max(t_offer, free_at)`.**
**The drain was computed from that same committed arithmetic rather than assumed: 60 deferred records per
victim at one frame per 2.000 s, 1,449,630 bytes, 13.6 Mbps, ONE QUEUE PER DEVICE so victims drain in
PARALLEL. Serialisation 1,449,630 x 8 / 13.6 Mbps = 0.8527 s, verified independently here.**
```
                         R1 distinct   R1 BOUNDED BY THE 0.88 s DRAIN
s4 k1-3                       1                      0
s4 k3-5                       2                      0
s5 k1-3                       1                      0
s5 k3-5                       3                      0
```
*** SO ON THE BUFFERED RULE THE MISSED-EVIDENCE DOSE IS **ZERO AT EVERY PAIR**. NOT ONE AFFECTED QUESTION IS
ASKED INSIDE THE 0.88 s DRAIN. IN THIS HARNESS, AT D = 120 s AND THIS MIX, NO QUESTION IS ANSWERED WITHOUT
EVIDENCE IT WOULD OTHERWISE HAVE HAD: THE EVIDENCE LANDS UNDER A SECOND AFTER RECONNECT. ***
**The build flagged this itself rather than reporting the unbounded 5 / 9 / 1 / 22 as the dose, because the
unbounded reading would rest the design on a mechanism the harness closes in 0.88 s.**

## *** 3. THE CONFLICT THIS CREATES IS THE USER'S TO SETTLE ***
```
the stop rule as written : STOP if every added-victim dose is ZERO at both seeds
R1 distinct              : 1, 2, 1, 3   NOT zero  ->  PROCEED
R1 bounded by the drain  : 0, 0, 0, 0   ZERO      ->  STOP
```
**Both are the same quantity under two readings of what counts as missed. R1 ignores that the frames arrive
0.88 s later; the bounded reading does not.** *** THE BOUNDED READING IS THE PHYSICALLY CORRECT DOSE FOR THE
MECHANISM THE RULING NAMED, AND IT IS ZERO EVERYWHERE. *** **The build's own reading applies the rule
literally to R1 and says PROCEED. This record does not choose.**

## 4. AND THE CHANNEL THAT SURVIVES IS NOT THE ONE THE RULING NAMED

**The reconnect burst is live and scales with k: 5,400 D2 tokens per victim at one instant, 27,000 at k=5.**
Under the committed D162 first-token model, verified here:
```
one victim        uncached  5,400  queued      0  ->  1.053 s   under the 3 s deadline
the fifth served  uncached  5,400  queued 21,600  ->  4.370 s   *** OVER the 3 s deadline ***
```
*** SO THE DESIGN MAY STILL WORK, THROUGH LATENCY ON THE RECONNECT BURST RATHER THAN THROUGH MISSED
EVIDENCE. THAT IS A MODEL-BASED SCREEN AND NOT A MEASUREMENT, quoted only to show the channel is not
negligible. ***
**And the three channels bear on DIFFERENT metrics, so one floor cannot serve all of them: forced
device-only questions are the arithmetic floor for `robot_pool_on_time` AND NOTHING ELSE; missed evidence is
a CORRECTNESS dose belonging to `correct_by_deadline`; the burst is latency and shows in both. The abandon
check now keeps them apart rather than applying the device-only floor to every metric, which would have
mislabelled two of three.**

## 5. THE DOSE IS WEAK WHEREVER IT IS QUOTED
**One to three distinct questions out of 229.** *** A DELTA AT THIS DOSE IS NOT AN EFFECT SIZE, AND THE
PREREG NOW CARRIES TWO INVALIDATION CONDITIONS FOR IT: a missed-evidence figure quoted as INSTANCES rather
than DISTINCT QUESTIONS is withdrawn, and a missed-evidence effect claimed WITHOUT THE DRAIN BESIDE IT is
withdrawn. ***
**R1 and R2 disagree at exactly one pair for the right reason: robo009's one affected question overlaps the
window by 1.02 s, SHORTER than the 2.000 s frame period, so no capture instant lies inside the overlap and
nothing was physically withheld for it. Both readings are reported.**
