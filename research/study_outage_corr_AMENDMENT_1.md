# AMENDMENT 1 to StudyOUTAGE-CORR: THE 55,000-TOKEN HISTORY FIGURE IS NOT SUPPORTED BY ANY MEASURED QUANTITY, AND THE GRID'S POSITIVE CONDITIONS, NOT ITS NEGATIVE CONTROL, ARE WHAT IS NOW UNESTABLISHED

**Written BEFORE any cell has run.** No cell of this study exists; D242 requires a user ruling in the
morning before anything reaches the queue. **So this is a pre-cell amendment, not a bar moved around a
result**, and it is recorded beside the pre-registration rather than edited into it so that what was
pre-registered stays auditable.

## What was pre-registered, and why it was checked

`research/study_outage_corr_prereg.md` carries a robot history p50 of **about 55,000 tokens** as the user
stated it, and derives the grid from it: k = 1 fits the 62,944-token 1x pool by 2,634 tokens, k = 3 and
k = 5 exceed it. **The amendment exists because I went to confirm the k = 1 negative control, whose margin
was 4.8 percent of an unverified number.**

## *** THE MEASUREMENT: 55,000 MATCHES NOTHING IN THE CELL, AND IT IS TOO LARGE, NOT TOO SMALL ***

Measured on the rung-3 1x s4 condition, with each candidate quantity reported separately because they
differ by up to 3.6x and measure different things:

| quantity | p10 | **p50** | p90 | max | 55,000 is |
|---|---|---|---|---|---|
| **per-robot-session RESIDENT KV tokens** (the pool-commensurable one) | 1,145 | **4,217** | 9,337 | 11,385 | **13.0x the p50, 4.8x the largest history ever observed** |
| **fleet-wide sum of robot resident tokens** | 18,013 | **34,639** | 45,903 | **48,975** | **1.59x the p50 and 1.12x ABOVE the fleet maximum ever observed** |
| `prompt_tokens` (an UPPER bound: includes the question, system prompt and per-frame multimodal tokens) | 8,536 | **15,108** | 25,119 | 26,940 | 3.6x the p50, 2.0x its max |

*** THE CROSS-CHECK THAT MAKES THE BELIEF ROUTE TRUSTWORTHY: the fleet-wide maximum from the belief rows
is 48,975, WHICH IS EXACTLY THAT CELL'S OWN `memory_pressure.pressure.peak_tokens` OF 48,975. *** The two
agree to the token, and the sum over all sessions equals the sum over robot sessions, so in this cell the
resident pool is entirely robot history. **That also closes a thread from tonight: the `peak_tokens` field
we spent an evening explaining IS the resident KV total.**
**Independent corroboration from the repo's own code, not sought out:**
`experiments/cost/study_eng1_steptime.py:79` sizes its filler as "3 fresh **~26k** histories (~78k tokens
> 62,944-token pool)". **The committed cost studies' own working figure for a history is about 26k, matching
the measured `prompt_tokens` maximum of 26,940, not 55,000.**
**An obstacle recorded rather than worked around:** the per-session resident belief block is **EMPTY in all
16,895 decision rows of the originally requested cell** - ABSENT, not zero, and the probe fires decisively,
since **twelve of thirteen sibling cells have it populated in every row, 140,745 rows in total**. That cell
is the oldest of the set and predates the instrumentation. **The figure above therefore comes from the 1x
`_rep2` cell**, same seed, same condition, same trace, a stratum-B relative differing by 0.003992 in
attainment. **That substitution is flagged, not hidden.**

## *** THE RISK INVERTS: THE NEGATIVE CONTROL IS SAFE AND THE POSITIVE CONDITIONS ARE GONE ***

| reading | k = 1 | k = 3 | k = 5 |
|---|---|---|---|
| **as pre-registered** (one history of 55,000) | FITS by 2,634 | EXCEEDS by 8,256 | EXCEEDS by 18,966 |
| **measured, k histories, EMPTY pool** | FITS by 53,417 | **FITS by 34,093** | **FITS by 14,949** |
| **measured, OCCUPIED pool** (34,639 already resident, 7 robot sessions) | FITS by 18,778 | **EXCEEDS by 546** | **EXCEEDS by 19,690** |

**So the k = 1 negative control SURVIVES under every reading, by a margin of 42,526 to 53,417 tokens on
the central estimates rather than the 2,634 the pre-registration implied. It is far more robust than
declared.**
*** AND ON AN EMPTY POOL ALL THREE k VALUES FIT, WHICH WOULD LEAVE THE GRID WITH NO POSITIVE CONDITION AT
ALL AND NO CONTRAST TO MEASURE. *** The pre-registered fit/no-fit pattern reproduces **only** when the
baseline residency is counted. **So the load-bearing assumption has moved: it is no longer "a history is
55,000 tokens" but "the pool is already occupied at reconnection", and that is not what the
pre-registration rested on.** **And on that framing k = 3's margin is 546 tokens, 0.9 percent of the pool,
tighter than the 2,634 this amendment was written to investigate.**

## What needs the user's ruling before any cell runs

1. **Re-source or retire the 55,000 figure.** It matches no quantity in this condition and the repo's own
   cost studies use about 26k. If it came from another model, context length or condition, that provenance
   must be stated, because substituting it changes which k values exceed.
2. **State whether the pool is empty or occupied at reconnection.** This is now the grid's load-bearing
   assumption. Empty makes every k fit; occupied makes k = 3 and k = 5 exceed, with k = 3 at 546 tokens.
3. **If a tighter contrast is wanted, the grid itself may need changing rather than its rationale** - a
   larger k, a longer D, or a smaller pool. **D240 forbids the smaller pool: all outage work is 1x only.**

## Limits of this amendment

**Single-cell distributions at one seed**, so the p50s describe this cell and are not estimates with a
cross-seed spread. **The conclusion that 55,000 is too large by 3.6x to 13x is robust to that**, because
even the largest value of any candidate quantity in the cell is below 55,000. **The conclusion about which
k values fit is NOT robust to it**, since k = 3's margin on the occupied-pool framing is 546 tokens.
