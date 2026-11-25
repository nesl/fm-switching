# THE NESTED-OUTAGE READOUT IS PER AFFECTED QUESTION, THERE ARE SEVEN OF THEM, AND IT CAN READ ONLY AN EFFECT OF 71 PERCENT OR LARGER. THE PRICE OF READING A MODERATE ONE IS 32 HOURS.

**Pre-registered BEFORE any scope A cell is scored, as ruled. CPU only, no cells scored, nothing committed
to `experiments/`.**

## WHY THE FLEET TOTAL WAS DROPPED
**The doses are 1, 2, 1 and 3 distinct affected questions, BELOW the robot cbd same-code observation of 2,
so the fleet total cannot carry the result. The primary readout is now PER AFFECTED QUESTION, matched across
the nested cells that share it, with fleet robot cbd and cloud-correct reported BESIDE it and NOT used as
the verdict.**

## THE CENSUS: SEVEN MATCHED QUESTIONS, DERIVED THE OTHER WAY ROUND
**Not re-used from the per-pair counts. The census works from `first_victim_k`, the device's index in the
recorded permutation plus one, which is EXACT because the victims are a prefix. It returns 7 MATCHED of 10
AFFECTED and reproduces the 1 + 2 + 1 + 3 dose from the opposite direction.**
| seed | device | first victim at k | control cells | treated cells | evidence overlap |
|---|---|---|---|---|---|
| 4 | robo009 | 3 | k1 | k3, k5 | 1.02 s |
| 4 | robo004 | 5 | k1, k3 | k5 | 9.00 s |
| 4 | robo004 | 5 | k1, k3 | k5 | 3.00 s |
| 5 | robo007 | 3 | k1 | k3, k5 | **120.00 s, the whole window** |
| 5 | robo008 | 4 | k1, k3 | k5 | 3.00 s |
| 5 | robo008 | 4 | k1, k3 | k5 | 5.77 s |
| 5 | robo006 | 5 | k1, k3 | k5 | 3.51 s |
- **NO question is shared between pairs or seeds, so the seven are seven.** A question affected at two rungs
  is ONE question with one control set and two treated cells, counted once.
- **THREE affected questions are UNMATCHED**, their device being a victim at the lowest rung so that seed has
  no control cell. *** THEY ARE A CENSUS, NEVER A COMPARISON. ***
- *** THE k = 1 RUNG IS LOAD-BEARING AND NOT A DECORATION: it is the ONLY control for the two questions whose
  device becomes a victim at k = 3. ***
- **Matching key: `(question_id, device_id)` against victim membership against k, with membership READ from
  the recorded permutation and never re-derived.**

## *** WHY THE MATCHED DESIGN BEATS SEVEN INDEPENDENT OBSERVATIONS ***
**Because the victim sets NEST, an affected question appears in a cell where its victim IS a victim AND in a
cell where it is NOT. EACH QUESTION IS ITS OWN CONTROL, and the readout is a within-question, within-arm,
across-k matched comparison. That is exactly the quantity the nesting was built to create.**

## THE MINIMUM DETECTABLE EFFECT, AS A COUNT OF DISCORDANT PAIRS
```
matched questions                 7
needed one-sided 0.05             5    0.5^5      = 0.0312    71 pct of the affected questions
needed two-sided 0.05             6    2 x 0.5^6  = 0.0312    86 pct
p if all seven flip one way       7    0.5^7      = 0.0078
```
*** SO NOTHING SMALLER THAN FIVE OF SEVEN CHANGING OUTCOME IN THE SAME DIRECTION CAN EVER REACH ONE-SIDED
p <= 0.05. ANY DISCORDANT COUNT BELOW THAT IS A CENSUS, AND THE PREREG NOW WITHDRAWS IT IF IT IS REPORTED AS
A DIFFERENCE. ***
**And one addition the build made on its own judgement, which could make the real n SMALLER than seven: a
question whose outcome cannot move in either cell, because it was never answered in either, CONTRIBUTES NO
DISCORDANT PAIR. The readout reports `n_matched_questions_readable` PER FIELD and THAT, not seven, is the
denominator. The first two scope A cells reveal it and the prereg says to read it before any comparison.**

## THE INVERSION, PRICED ON MEASURED YIELDS ACROSS FOUR SEEDS RATHER THAN EXTRAPOLATED FROM TWO
```
matched questions per seed on the {1,3,5} ladder:  s4 = 3 , s5 = 4 , s6 = 2 , s7 = 0 , mean 2.25
```
*** SEED 7 YIELDS ZERO MATCHED QUESTIONS. SO THE YIELD RUNS 0 TO 4, ANY SEED COUNT IS A MEAN AND NOT A
GUARANTEE, AND THE SEED AXIS MUST BE BOUGHT IN BLOCKS WITH THE YIELD CHECKED AS IT GOES. ***
*** AND THE NEWLY EXPRESSIBLE k = 7 AND k = 9 RUNGS ARE NEARLY EMPTY AT THE TWO RULED SEEDS: 0 AND 0 AT
SEED 4, 0 AND 1 AT SEED 5. BUYING THEM THERE WOULD BUY ALMOST NOTHING. ***
| effect per question | matched needed | seeds | cells | hours | rung axis at s4+s5 |
|---|---|---|---|---|---|
| **0.8** | 7 | 4 | 24 | 8.63 | **k = 5, 12 cells, 4.32 h** |
| **0.6** | 10 | 5 | 30 | 10.79 | **k = 11, 24 cells, 8.63 h, THEN IT DEAD-ENDS** |
| 0.5 | 12 | 6 | 36 | 12.95 | **unreachable** |
| 0.4 | 16 | 8 | 48 | 17.27 | **unreachable** |
| 0.3 | 21 | 10 | 60 | 21.58 | **unreachable** |
| **0.2** | 33 | 15 | **90** | **32.38** | **unreachable** |
**Scope B at five arms is 2.5x the cells and hours.**

## THE ANSWER TO THE RULING'S CLOSING QUESTION: THE DESIGN IS **NOT** CLOSED, AND THE PRICE IS SPECIFIC
1. **As ruled it reads ONLY an effect of 71 percent or larger per affected question. It is the right first
   spend because it is already paid for, and a lost-evidence condition might well produce an effect that
   large, BUT IT CANNOT READ A MODERATE ONE.**
2. *** THE RUNG AXIS ALONE CAN NEVER GO BELOW 0.6. The whole ladder to k = 11, the ceiling at this mix,
   yields ten matched questions at the two ruled seeds. It is the cheaper way to reach 0.6 at 8.63 h AND IT
   DEAD-ENDS THERE. ***
3. **ONLY THE SEED AXIS REACHES A MODERATE EFFECT: 15 seeds, 90 cells, 32.4 hours at two arms for a 0.2
   per-question effect, using seeds 4 to 18 since 1 to 3 are excluded.**
4. *** IF THE FIRST TWO CELLS SHOW THE READABLE n BELOW SEVEN, THE READOUT CANNOT SEPARATE ARMS AT ANY PRICE
   ON THIS AXIS, AND THAT IS THE FINDING, IN THE SAME REGISTER AS THE HOST-AWARENESS LINE: UNEXPRESSIBLE,
   NOT ABSENT. ***

## THE FOUR FIELDS, AND ALL FOUR ARE EXPRESSIBLE
**Each comes from the cell's OWN committed per-question row, 132 rows per cell, so the readout CANNOT
disagree with the scored cell: answered, correct, on time with `device_on_time` beside it, and SERVED BY
cloud or device.**
*** PER INVALIDATION CONDITION 13, ALL FOUR ARE EXPRESSIBLE: every one needs only an arm reacting to a
SMALLER CLOUD HISTORY, which it sees through `readiness_tokens`, and NONE requires the arm to RECOGNISE the
outage, which is the unexpressible part. And the fourth carries the mechanism, because the device history is
COMPLETE while the cloud's is short and routing to the device is fully expressible, so the cloud-against-
device split is the reading most likely to show anything. ***
**The match is proved complete BEFORE any outcome is read, and the tool REFUSES rather than scoring a
partial match.**

## A DEFECT THE COMMITTED CELLS CAUGHT, RECORDED BECAUSE THE DISTINCTION IS THE POINT
*** THE FIRST VERSION OF THE READOUT **CRASHED** ON A CELL WHOSE HEADER CARRIES NO OUTAGE BLOCK, INSTEAD OF
REFUSING. A CRASH IS NOT A REFUSAL. *** It now refuses by name and lists what is missing, and the refusal
path is exercised as a NEGATIVE CONTROL on the committed outage cells rather than assumed to work.

## FIVE NEW INVALIDATION CONDITIONS
**A fleet total quoted as the verdict; a comparison read before the match proof passes; a discordant count
below five of seven reported as a difference; the denominator taken as seven when the readable n is lower;
and condition 13 carried into each reading.** **Section 3 now opens by saying the abandon check answers a
DIFFERENT question and DOES NOT DECIDE THE STUDY.**
