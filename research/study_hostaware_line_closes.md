# THE HOST-AWARENESS LINE CLOSES AT THE D250 CONDITION. BOTH LEVERS FAIL THE BAR, AND THE REASON IS NOT HOST AWARENESS AT ALL.

**CPU, committed artefacts, read-only. No code changes, nothing fixed. Ordered before any survival lever was
to be built.**

## *** THE VERDICT, AND THE ONE NUMBER THAT CARRIES IT ***

**On the EXACT 34 declined opportunities in the D250 gate cell, measured on the same questions:**
```
the DEVICE is right          14 of 34 = 0.4118
a RECENT cloud answer is right 2 of 34 = 0.0588
*** THE DEVICE IS 7.0x BETTER THAN THE REPRESENTATION THE LEVER WOULD SEND ***
```
| lever | expected correct-by-deadline on the 34 | delta | beats the bar of 3? |
|---|---|---|---|
| (a) device fallback as now | **14.00** | baseline | |
| **(b) C3 RECENT on** | **2.00** | *** -12.0, and -9.0 at the most generous RECENT source *** | **NO, IT IS NEGATIVE** |
| (c) mixture prior, at a warm-tier bound the gate cell does not have | 17.24 | +3.24 | only at that bound |
| **(c) mixture prior, at THIS CELL's own cold regime** | **14.70** | **+0.71** | **NO** |

*** SO NEITHER LEVER BEATS THE DEVICE FALLBACK BY MORE THAN THE SAME-CODE OBSERVATION, AND BY THE RULING'S
OWN TERMS THE LINE CLOSES. AND THE REASON IS NOT HOST AWARENESS: IT IS THAT ON THESE QUESTIONS THE DEVICE'S
OWN ANSWER IS BETTER THAN ANY DEGRADED REPRESENTATION THE CLOUD CAN SEND. ***

## THE BAR, COMPUTED FROM THE REPLICATES RATHER THAN ASSUMED

**`kv0.5r` triple: 82 / 85 / 83, range 3, sd 1.53. All five same-arm s4 27 GiB cells pooled: 82, 83, 84, 85,
85, range 3, sd 1.30. BOTH GIVE 3, so the bar does not depend on which replicate set is taken.**
**Caveat named: the three `kv0.5r` cells ran on three different repo heads, so this is a SAME-ARM
SAME-CONDITION replicate spread, not a strict same-tree spread. It carries the caveat the D250 diagnosis
already recorded for the gate and `_rep2` pair.**

## *** AND IT CORRECTS MY YARDSTICK A SECOND TIME, DOWNWARD AGAIN ***

**I committed a ceiling of 13 for any decline-converting lever, from 85 minus 72. THAT IS THE WHOLE-CELL
GAP.** *** ON THE SAME 34 DECLINES THE GATE CELL SCORES 14 AND `_rep2` SCORES 17. SO THE DECLINE-CONVERTING
CEILING IS +3, WHICH **IS** THE BAR. The other 10 of the 13 comes from the 98 SENT questions scoring better
in the warm cell, not from the declines at all. *** **A lever aimed at the declines was never competing for
13; it was competing for 3, against a noise floor of 3.**

## MY STRUCTURAL CLAIM WAS HALF WRONG, IN THE SIGN-DECIDING HALF

**I argued that sending weakly dominates declining, because a late cloud send falls back to the device.**
`score.py:847-857`:
- **CONFIRMED: a LATE cloud send is NOT a forfeit.** `:856` consults the device, which always arrives here
  (0.25 to 0.31 s against 3.0 s), so declining and sending-and-being-late score identically.
- *** REFUTED, AND THIS DECIDES THE SIGN: AN ON-TIME CLOUD SEND **PRE-EMPTS** THE DEVICE. `:854` returns the
  cloud's answer before `:856` is reached, and the device's own correctness is never consulted. SO THE LEVERS
  DO NOT WEAKLY DOMINATE. THEY ARE BETS, and sending trades the device's answer for the cloud's whenever the
  cloud is on time, which is 34 of 34 for RECENT. ***
**The break-evens therefore collapse exactly as I had written them: "is `acc_RECENT` above `acc_device`" and
"is `acc_full` above `acc_device`". Only the phrase "weakly dominate" was wrong.**

## THE ANSWER WAS ALREADY HALF-WRITTEN INTO THE POLICY'S OWN CODE

**Three independent sources agree on the ordering RECENT < device < D2, on the same questions:**
| source | D2 | device | RECENT |
|---|---|---|---|
| in-cell, the s4 pool's 20 questions | 0.650 | | 0.250 |
| in-cell, the 10 decline questions | 0.700 | 0.300 | 0.100 |
| the committed policy input's DEV fit | 0.250000 | 0.071429 | 0.107143 |
*** AND `value_reader.py`'s OWN DOCSTRING ALREADY RECORDS THAT THE C3 FALLBACK "WAS CONVERTING A BETTER
ANSWER INTO A WORSE ONE AND COUNTING IT AS A SAVE BECAUSE IT ARRIVED ON TIME". THE ESTIMATE THIS RULING
ASKED FOR WAS ALREADY DOCUMENTED IN THE CODE THAT IMPLEMENTS THE THING BEING ESTIMATED. ***

## THE CELLS, IN FULL, AND THE PROOF THEY ARE THE SAME QUESTIONS

**503 committed live2 run directories were enumerated; 74 carry robot answers with
`cloud_payload.representation == "RECENT"`. The decisive cell:**
```
results/orchestration/live2/frozen_test/runs/hybrid-F-lhreq_n16_s4_1200s_h27_3t_L3_epg_rq30
```
**It runs the SAME TRACE DIRECTORY as the gate cell, confirmed from both `cell.json` files, so its 132 robot
opportunity ids ARE the gate cell's 132 and the comparison is on identical questions rather than rate
against rate. ALL 34 of the gate cell's declined opportunities were sent as RECENT in it, and
`arm_stats.c3_recent = 76` shows the branch fired as a counted decision rather than a dead field.**

## THE FLEET COST: THE BUDGET IS BOUNDABLE AND NOT BINDING. THE QUEUE IS NOT SIGNABLE.

```
gate cell budget  1200.0 GPU-s , spent 815.42 , utilisation 0.6795
34 RECENT sends   +  3.53 GPU-s  -> 0.6825   (+0.3 pp)
34 full sends     +105.78 GPU-s  -> 0.7677   (+8.8 pp)
```
**So the accelerator budget is NOT the binding resource and neither lever makes it one.**
*** BUT THE 3,141 `release_infeasible` EVENTS HAPPEN AT 68 PERCENT MEAN UTILISATION, SO WHAT FAILS IS THE
INSTANTANEOUS FEASIBILITY TEST AND NOT THE BUDGET. Robot recall TTFT is p50 1.463 and p90 5.084 s with a max
of 14.132, and 26 of the 98 sends ALREADY missed the 3 s deadline. WHETHER 34 MORE ARRIVALS PUSH THOSE
FURTHER OUT CANNOT BE SIGNED FROM AGGREGATES. ONLY A RUN CAN SETTLE THE QUEUE EFFECT. *** **It does not
change the verdict, because the per-question arithmetic rules both levers out before the fleet term is
reached.**

## THE LIMITATION THAT IS LARGER THAN THE BAR, STATED AS SUCH

*** THE 34 DECLINES ARE ONLY **10 DISTINCT QUESTION IDS**, with multiplicities 5, 5, 5, 5, 4, 3, 3, 2, 1, 1,
AND THE DEVICE'S 14 CORRECT COME FROM **3 DISTINCT QUESTIONS**. Every accuracy here is opportunity-weighted
over a 10-question base. A different sampling of the 69 EVAL questions would move it, AND THAT UNCERTAINTY
IS LARGER THAN THE BAR OF 3. ***
**So the SIGN is safe and the MAGNITUDE is not: the device beating RECENT by 7x survives any reweighting,
and the mixture prior's +0.7 against a bar of 3 does not.**
**A second disagreement recorded rather than reconciled: in-cell RECENT accuracy is 0.0588 to 0.0921 against
a committed offline EVAL figure of 0.2609, which is above the 2x bar. They are not the same estimand, one
being opportunity-weighted over 10 questions and the other one answer per question over 69. BOTH ARE BELOW
THE DEVICE ON THE SAME QUESTIONS, which is the only comparison the ruling turns on, so the gap moves the
margin and not the sign.**
**And an attribution disagreement with no consequence: this analysis reads the gate cell as 72 = 50 cloud +
22 device where the committed diagnosis says 49 + 23. The TOTAL agrees exactly, so one opportunity sits on
the delivery boundary and is attributed differently. It moves no figure here.**

## CONTROLS, RUN BEFORE THE COMPARISON WAS READ
**Correct-by-deadline recomputed from raw outcomes plus the trace's device answers reproduces the committed
value EXACTLY on every cell: gate 72, un-suffixed 82, `_rep2` 85, `_rep3` 83. In-cell D2 accuracy per
distinct question in `_rep2` is 13/20 and the independent offline table on the same 20 questions is ALSO
13/20, an exact match across two unrelated artefacts, which is the positive control on the accuracy join.**
*** AND ONE HANDED-DOWN FIGURE IS CORRECTED AT ITS REGISTER: the robot TTFT p50 1.463 / p90 5.084 reproduces
only on the 98 RECALL SENDS. Over all 1,623 `robo` requests, which include per-frame release traffic, it is
p50 0.851 / p90 8.599. IT IS A RECALL-SEND STATISTIC AND MUST NOT BE QUOTED AS A ROBOT-REQUEST STATISTIC. ***
**Caching: prefix caching was ENABLED in every cell read, so every latency is a warm-serving number and no
warm figure is compared to a cold one. Device latencies are the measured WARM table.**
