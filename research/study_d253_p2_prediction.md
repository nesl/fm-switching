# D253 P2 (rq10): A PRE-REGISTERED PREDICTION, WRITTEN BEFORE THE CELL RUNS

**Written 2026-11-25 while P1 cell 2 (n24) was still running and BEFORE any P2 cell started. The commit
timestamp is the proof of ordering.** **P2 runs as D253 rules; this does not change the queue. It makes a
prediction falsifiable instead of leaving a story to be told afterwards.**

## What P1 established

**P1 n20 FAILED all three D253 conditions** (server host max 0.135 with zero samples at capacity; idle-robot
P(cold) 1 of 28 = 0.036; planner evictions 0). **And the shedding signature asked for in advance CONFIRMED
on both committed cells, n16 `_rep2` against n20:**
```
release_infeasible   1,979 (16.8% of instants) -> 3,191 (20.4%)   ALL ALERT, no recall component
unsent dashcam       2,899 (24.6%)             -> 7,080 (45.2%)
unsent robot             0                     ->    15
guard_shed_warming_epochs 68                   ->     76
SERVER host peak         0.221                 ->  0.135          <- FELL
```
**Shedding rose on every count while host occupancy FELL.**

## *** THE MECHANISM, SHARPENED BY THE FINDING THAT ALL REFUSALS ARE ALERTS ***

**The relief valve is the ALERT channel, not the robot channel: there is no recall component in
`release_infeasible` in either cell.** **And per D148 the alert episodes are precisely the PERSISTENT-KV
holders, about 3.4 to 6.8k tokens each, competing with robot histories for the pool.**
*** AN EPISODE'S KV GROWS WITH THE FRAMES ACTUALLY SENT. SO SHEDDING INSTANTS MEANS SHORTER EPISODES, LESS
KV PER DASHCAM, AND TOTAL OCCUPANCY THAT CAN FALL EVEN AS THE DASHCAM COUNT RISES: eight short episodes
hold less than six long ones. ***
**That is why adding devices raises REFUSALS rather than OCCUPANCY, and why the policy's own feasibility
checks act as the relief valve that keeps memory from ever filling.**

## *** THE MECHANISM IS CORRECTED BY THE SECOND SIGNATURE: NOT SHORTER EPISODES, BUT FEWER EPISODES WITH ANY KV AT ALL ***

**The second signature was computed, and it HOLDS independently of the refusal counts, but it REFUTES half
of the mechanism stated above.** Grouped by `play_id` (the episode key; `session_id` is null on every
dashcam outcome row):
```
size        plays  instants  SERVED  mean served/play
n16 _rep2     189    11,764   8,323          44.04
n20           253    15,673   8,069          31.89
n24           316    19,590   7,106          22.49      a 49 pct fall
instants per play p50 = 67 AT ALL THREE SIZES
n24 deciles of served/play: 0 0 0 0 12 22 28 35 44 52 86
```
*** PLAY LENGTH IS UNCHANGED. What falls is SERVED instants per play. AND THE DISTRIBUTION SAYS MORE THAN
THE MEAN: at n24 the first four deciles are ZERO, so ABOUT 40 PERCENT OF PLAYS GET NOTHING SERVED, while
the top decile still reaches 86. ***
**SO THE SHEDDING IS NOT UNIFORM THINNING. It is WHOLE PLAYS DROPPED while others are served nearly in
full.** *** THEREFORE THE MEMORY CONSEQUENCE IS PLAYS THAT NEVER BUILD KV AT ALL, NOT PLAYS THAT BUILD
LESS. The sentence above about shorter episodes holding less KV is WRONG as a mechanism, and is corrected
here rather than edited away. ***
**WHAT SURVIVES UNCHANGED: total resident dashcam KV still falls as devices rise, and the relief valve is
still the alert channel. The CONCLUSION is the same and the ROUTE is different, which matters because the
two predict different things about a smaller pool: fewer-episodes-with-KV says the pool is never pressed
because work is refused at episode granularity, which is a sharper claim than shorter episodes.**

## TWO REGISTER CORRECTIONS, BOTH MINE

**1. My n16 anchor was the WRONG CELL.** I quoted mean 44.33 and max 84; those are the ORIGINAL
`covex-v6-fair-final_n16_s4_..._L3_epg_rq30` cell (8,378 served). **The reference in use everywhere is
`_rep2`, which is 44.04 and max 82 (8,323 served).** I read the un-suffixed path because it looked
canonical. **All n16 figures in this file now use `_rep2`.**
**2. THE THREE-SIZE COMPARISON CROSSES A CODE BOUNDARY AND I CANNOT SIZE IT.** The three cells carry three
different commits (`da24cee4` original, `629f2c7a` `_rep2`, `d80d4dcd` P1 n20), and P1 ran on the
post-`9e38d937` live2 subtree that NEITHER n16 cell has. **The outages-OFF byte-identity proof bridges the
OUTAGE BUILD specifically, since P1 carries no outage; it does NOT license the whole interval between those
commits, and I could not compute that interval because both shas are UNRESOLVABLE in this clone.**
*** SO THE n16 ANCHOR IS LABELLED CROSS-CODE. The n20-to-n24 leg is the part that can be read without that
caveat, and it alone shows the direction on every count. ***
## THE PREDICTION, for P2 (`covex-v6-fair-final` n16 s4 1x `_L3_epg_rq10_preD249`)

*** P2 WILL FAIL ALL THREE D253 CONDITIONS, with refusals RISING and the server host peak FLAT OR FALLING
against the n16 rq30 reference's 0.221. ***
**Reason: rq10 adds DEMAND (three times the robot question rate), and demand is what the shedding valve
absorbs. It does not add RESIDENT KV.**
**Stated so it can be wrong: if P2 PASSES any of the three conditions, or if its host peak RISES above
0.221, this mechanism is wrong and the pilot's premise survives. That outcome would be more informative
than the predicted one.**
**A SECOND, SHARPER SIGNATURE, falsifiable independently: MEAN FRAMES PER SERVED EPISODE should FALL from
the n16 reference to any higher-demand cell. If refusals rise while frames-per-episode stays flat, the
episode-length half of the mechanism is wrong even if the refusal half holds.**

## THE CONSEQUENCE FOR THE PILOT, stated as a question for the user and not as a decision

**P1, P2, P3 and P4 ALL WORK BY ADDING DEMAND** (device count, question rate, robot-heavy mix,
dashcam-heavy mix). **If the mechanism holds, all four fail for the same structural reason and the pilot
cannot find a memory-contesting regime by any of its four directions.**
*** D250, WHICH IS NEXT IN THE QUEUE AFTER P1 REGARDLESS, IS THE ONE QUEUED CONDITION THAT ATTACKS
OCCUPANCY DIRECTLY: it HALVES the GPU KV pool AND the host tier rather than adding demand. It reduces
SUPPLY where the pilot's four directions raise DEMAND. *** **So the memory question may be answered by D250
and not by the pilot at all.**
**If a demand direction is still wanted after D250, the directions that would raise RESIDENT KV rather than
demand are longer sessions, more robots per device, or a smaller pool. Naming one is the user's ruling, not
a fifth direction from the same family.**
