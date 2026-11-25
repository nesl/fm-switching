AMENDMENT 4 TO d231_ptg_prereg.json: BAR 1 NEEDS A TOLERANCE. NOT YET LANDED.

STATUS: PREPARED BY THE ptg BUILD SESSION, NOT PUSHED. CC may not commit or push (CLAUDE.md "Git
rules (read-only from CC)"). This must be landed by whoever holds the push window, and it must land
BEFORE the covex-v6-fair-final-ptg s4 cell is scored, not after.

WHY. The committed pre-registration (in 42aa4fbe) pins bar 1 as:
    "ptg mean per-episode alert attainment >= 0.619234"
D234 (3), committed at 79321e14, measured the metric's own reproducibility over n = 8 same-code
replicate pairs: max observed |diff| 0.027752, median 0.001953. **The pinned threshold is finer
than the instrument's reproducibility by a factor of about three.** As written, bar 1 cannot
discriminate, and the committed file does not say so. That is a pre-registration asserting a
precision the measurement cannot deliver, which is the same defect class as a bar in the wrong
register: self-consistent, and wrong about what it can decide.

THE AMENDMENT TO MAKE, in place, with the original wording kept (D185 (2) convention):

  bar 1 becomes THREE-VALUED against rung 3's 0.619234 at the same seed, with the floor from
  D234 (3) at 79321e14:
    PASS            ptg attainment >= 0.619234 + 0.027752
    NO DIFFERENCE   |ptg attainment - 0.619234| < 0.027752   <- NOT a pass and NOT a fail
    FAIL            ptg attainment <= 0.619234 - 0.027752
  A difference under about 0.028 on bar 1 IS NOT A RESULT and must be reported as "inside the
  floor", never as a pass, a fail, or a null about the guard.

THE TWO CAVEATS THE FLOOR CARRIES, from the session that measured it, and both must be copied in:
  1. n = 8 CANNOT CARRY A p95. The interpolated p95 (0.020615) is set entirely by one pair whose
     difference is 3.8x the next largest. The defensible statements are "max observed 0.027752"
     and "7 of 8 pairs at or below 0.0074". Use the MAX as the tolerance, not the p95.
  2. THERE IS NO SAME-CODE REPLICATE IN THE L3_epg_rq30 CONDITION. Every same-code pair is
     pre-EP-G. The code-changed stratum gives a larger spread (max 0.0858) as an upper bound.
     Both strata put the floor at or above 0.02, so 0.027752 is the tolerance and 0.0858 is the
     number to quote if anyone asks how much worse it could be in this condition.

WHAT THE FLOOR DOES NOT DO, so the tolerance is not read as defeatism: the state-channel ablation
lost 0.170831 of attainment, 6.2x the floor, with 627 of 712 episodes moving. The floor separates
real effects from ones being read into noise; it does not flatten everything.

BARS 2 AND 3 ARE UNAFFECTED BY THIS AMENDMENT. Bar 2 is a COUNT of robot on-time answers
(>= 116.9 at s4, from base 35 plus 0.90 x (126 - 35)) and bar 3 is a PERCENTAGE of single-shot
questions within 2 s. Neither is per-episode alert attainment and neither inherits this floor.
**Do not apply 0.027752 to them.** If a floor is wanted for those, it has to be measured on those
metrics; D234 (3) did not measure it and this amendment does not invent one.

ALSO WORTH RECORDING IN THE SAME AMENDMENT, since it bears on how bar 1 is computed: the committed
scorer's own check 1 compares attainment to the BASE (0.442), not to rung 3, so its printed verdict
is not bar 1. That warning is already in amendment 3 and should be restated beside the tolerance,
because the two traps compound: a scorer comparing to the wrong arm, and a threshold finer than the
instrument.
