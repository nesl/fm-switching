# THE 1.5 s ROBOT DEADLINE IS NOT A NULL TEST. IT IS THE DEADLINE AT WHICH WARM-VERSUS-COLD BECOMES DECISIVE.

**Previewed by the H100 on a COMMITTED cell before the gate runs: `covex-v6-fair-final` n16 1x s4 `_rep2`,
which ran at a 3 s robot deadline. Robot QUESTIONS only (request rows joined to the 132 robot opportunity
ids in `outcomes`), history uploads excluded since they are the other ~2,800 robot rows. All 132 had a cloud
request.**

## THE TWO BOUNDS, CONVERTED TO SECONDS AT THE COMMITTED COLD RATE

`recall_ttft_s(tok, COLD) = tok / 4500`, so a 1.5 s deadline buys **6,750 tokens** of admissible work.
```
PROMPT tokens (the COLD cost)        p10  8,522 = 1.89 s   p50 15,124 = 3.36 s   p90 25,130 = 5.58 s
UNCACHED tokens (AS SERVED at 3 s)                         p50  1,177 = 0.26 s   p90  5,048 = 1.12 s
                                                                                 max 15,119 = 3.36 s
```
| bound | questions over 6,750 tokens | share |
|---|---|---|
| **if every question were COLD** | **129 of 132** | **97.7 pct** |
| **as the cache actually stood at 3 s** | **8 of 132** | **6.1 pct** |

*** SO THE ANSWER TO "DOES THE GATE MEASURE THE DEADLINE OR THE POLICY" IS: IT MEASURES THE DEADLINE ONLY
INSOFAR AS THE POLICY LETS HISTORIES GO COLD. That is the robo001 latch again, promoted from a diagnosis to
the deciding variable. ***

## *** AND 1.5 s IS ALMOST EXACTLY THE p90 OF THE AS-SERVED COST (1.12 s), WHICH IS WHAT MAKES IT A GOOD
GATE RATHER THAN A BROKEN ONE. *** It is the deadline at which warm-versus-cold flips from irrelevant to
decisive: a warm history clears it with room, a cold one cannot clear it at all.

## A CONTRAST I HAD NOT COMPUTED, AND IT CHANGES HOW THE EXISTING CELLS READ

**3 s buys 13,500 tokens, and the p50 PROMPT is 15,124.** *** SO EVEN AT 3 s, MORE THAN HALF THE QUESTIONS
ARE COLD-INFEASIBLE. THE CACHE IS WHAT MADE THE 3 s CELLS WORK AT ALL, NOT THE DEADLINE. *** Every committed
robot on-time figure in this project rests on cache hits, and nothing in the reporting says so.

## *** THE REGISTER POINT, WHICH IS THE LIMIT ON ALL OF THE ABOVE ***

**6.1 pct IS AN OBSERVATION ON A 3 s CELL. IT IS NOT A PREDICTION FOR A 1.5 s CELL.** `cached_fraction` at
3 s is a function of how the policy behaved *at 3 s*. **And the latch runs the wrong way: a tighter deadline
causes declines, declines leave histories cold, cold raises the prompt cost, which causes more
infeasibility and more declines. SELF-REINFORCING, in the bad direction.**
*** SO 97.7 pct AND 6.1 pct BRACKET THE 1.5 s CELL. WHERE IT LANDS BETWEEN THEM IS THE MEASUREMENT, AND IT
CAN DRIFT TOWARD THE COLD END DURING THE CELL. A single end-of-run figure will not show that drift; the
count must be reported over time, or at least split across the run's halves. ***

## WHAT THE GATE REPORTS PER CELL

**Both bounds, beside the three robot metrics (cloud on-time, cloud accuracy on served, correct-by-deadline,
per D257 (3)): questions with PROMPT over 6,750 (the cold bound) AND questions with UNCACHED over 6,750 (as
served). Unsent questions have no prompt row and are counted separately.**
