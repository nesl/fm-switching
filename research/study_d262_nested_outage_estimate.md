# D262 PART 3: THE NESTED-VICTIM OUTAGE ESTIMATE. AND A STEP 0 FINDING THAT COULD INVALIDATE THE WHOLE DESIGN BEFORE IT IS BUILT.

**ESTIMATE ONLY, per the ruling. Nothing built, no cell run, no GPU, repo untouched.**

## *** THE FINDING THAT MATTERS MOST, AND IT IS ALREADY VISIBLE IN COMMITTED DATA ***

| committed cell, `covex-v6-fair-final` n16 s4 | `robot_pool_on_time` |
|---|---|
| `_out-k3-d120` | **121 / 132** |
| `_out-k5-d120` | **121 / 132** |

*** THE HEADLINE ROBOT METRIC GIVES THE IDENTICAL VALUE AT k=3 AND k=5, WITH DISJOINT VICTIM SETS AND
WINDOWS 157 s APART. The runs differ genuinely, so this is the METRIC FAILING TO SEPARATE THE DOSES, not a
caching artefact. IF IT DOES NOT SEPARATE THEM WITH NESTED VICTIMS EITHER, THE k-EFFECT IS **UNSCORABLE**
ON CLOUD ON-TIME IN RULE 2's SENSE, AND THE DESIGN RESTS ENTIRELY ON THE HISTORY-CACHED OBSERVABLE - FOR
WHICH NO SCORER EXISTS. *** **Checkable on the gate cell plus one k=5 cell BEFORE the sweep, which is why
the scope order below runs the small scope first.**

**Verified independently here by enumerating every committed outage cell rather than taking a glob's first
match, which matters because the first match was a DIFFERENT ARM (`-stateoff`, 66/132) and would have had
me contradict a correct finding. `llf` under the same outage reads 4/132.**

## THE RULING'S KEYING CHANGE IS A REORDER, NOT ONLY A KEY EDIT

`fleet/trace.py:957-961` is three statements and the ruling touches all three.
- **`:957-958` is where k enters the RNG key.** Removing it is one edit.
- *** BUT `:961` DRAWS THE WINDOW FROM THE SAME STREAM, AFTER `:959` HAS CONSUMED k DRAWS. With k out of the
  key the victims would nest and THE WINDOW WOULD STILL MOVE, because the uniform draw starts from a
  different stream position at k=3 than at k=5. The two statements must be INVERTED: window first, victims
  second. ***
- **`:959` `random.sample` happens to be prefix-consistent in k at this fleet size, so nesting would hold BY
  AN UNDOCUMENTED CPython INTERNAL rather than by construction. Replace with an explicit k-independent
  permutation prefix and record the order in the meta so nesting is auditable from the artefact.**
- **FIXED window reads as `(run_s - D)/2` = 540.0 s, window 540.0 to 660.0 s, which is the exact centre of
  the committed band `[0.25, 0.75] x (run_s - D)` = `[270, 810]`. So it is INSIDE the existing rule, not an
  extrapolation.**
- **Already true and needing no change: not randomised per arm (no arm in the key); robot-only (the draw is
  from `rob_ids` alone, so dashcam and assistive can never be victims). 1x only is enforced MECHANICALLY by
  the driver, which refuses any tag carrying both an outage and a memory token, and this costs nothing
  because P3's pressure appeared at 1x with no memory token at all.**

## HOURS, SPLIT THREE WAYS AND NOT MERGED

| | cells | hours |
|---|---|---|
| **flash build, CPU only** | 0 | **14.5 to 23.0** |
| **accelerator, GATE (old against new keying, k=3 s4)** | 2 | **0.72** |
| accelerator, SWEEP scope A (2 arms x k{3,5} x s{4,5}) | 8 | 2.88 |
| accelerator, SWEEP scope B (5 arms x k{3,5} x s{4,5}) | 20 | 7.19 |
| **scope B plus a k=1 rung** | 30 | **10.79** |

**At 1,295 s per cell, the measured median start-to-start over six consecutive cells, against the committed
1,284 s. Reference cells are NOT charged, because the handoff already queues the in-regime no-outage
references under D262 items 1 and 2.**
**Recommended: scope B with the k=1 rung, run as A then the remainder, so the design can be abandoned after
8 cells if the unscorability above is confirmed. The k=1 rung restores the standing one-device-at-a-time
direction as a nested FLOOR and makes k a three-level ladder.**

## REACHABILITY AT ELEVEN ROBOTS, AND WHAT IT BREAKS

- **Room for k=5: yes, and more than before. The ceiling was k=7 at 40:40:20 and is k=11 here; k=5 is 45 pct
  of robots where it was 71 pct. k=7 and k=9 rungs become newly expressible.**
- **`w_d`'s DEFINITION is unchanged, but its VALUE moves, because the robot target is POOLED and the pooled
  denominator moves 132 to 229.** *** SO `_c3-11-2` OUTAGE CELLS MAY NOT BE POOLED WITH OR DIFFERENCED
  AGAINST THE EXISTING 40:40:20 OUTAGE GRID. THE COMPARATOR IS P3 AND THE REGIME-GATE CELLS, NEVER THE OLD
  GRID. ***
- **Dashcam per device is effectively unchanged, 1,956.3 against 1,960.7, 0.2 pct apart, and all three
  dashcams clear the 200 floor about tenfold. So the dashcam side stays comparable PER DEVICE while the
  fleet total halves and must never be quoted across mixes.**
- **The deferred-history dose stays `k x (D/2)` and is unchanged by the mix. What rises is the device-only
  QUESTION dose. Per-victim question counts span 12 to 32, SO THE QUESTION DOSE IS NOT FIXED BY k and each
  victim's own count must be reported beside it.**

## WHAT IT ESTABLISHES, AND WHAT IT DOES NOT

**Removed: victim identity and run phase. The existing grid compared k=3 victims {robo003, robo005, robo006}
at 786.90 to 906.90 s against k=5 {robo001 to robo005} at 509.51 to 629.51 s, with `robo006` a victim at
k=3 and not at k=5 and the windows 157 s apart.**
*** NEWLY IDENTIFIABLE, which is the concrete gain beyond "one confound removed": because the k=5 set
contains the k=3 set at the same instant in the same trace, the two ADDED victims can be differenced
against their own rows in the k=3 cell. THE MARGINAL COST OF ADDING ONE SPECIFIC ROBOT TO A CORRELATED
OUTAGE BECOMES A MEASURABLE PER-DEVICE QUANTITY, unavailable at any k in the existing grid. ***
**NOT removed: the dose is `k x (D/2)` by construction, so it stays EXACTLY COLLINEAR WITH k. Any k-effect
is a k-and-dose effect, and breaking that needs D varied at fixed k, which this ruling does not order.**
**NOT touched: the existing amendment's Conflict 1 stands verbatim. Device-only questions have no payload
and no request rows, so they remain unmeasurable and reportable only as a count.**

## FOUR MORE WAYS THESE CELLS COULD BE UNINTERPRETABLE, EACH CHECKED AGAINST CODE

1. *** THE TRACE-DIR CACHE SERVES THE OLD PLACEMENT WHILE EVERY GATE PASSES. The directory name is built
   from seed, n, run_s, mode, ratio, question sets, L, epg, perframe, rq and `outk<K>d<D>` - AND NOTHING
   ABOUT THE PLACEMENT RULE - and the trace is regenerated only if `trace.jsonl` is absent. No collision in
   this regime today, because the ratio token differs from every committed outage trace, BUT THE FIRST
   FIXED-WINDOW CELL AT 40:40:20 WOULD LAND ON AN EXISTING PATH. The driver's own check reads only the argv,
   and its assertion covers only k and D, both of which are present in the stale meta. This is the
   write-only-field shape in a filesystem cache. ***
2. **The driver validates a DIFFERENT cell's meta: its glob covers the ratio token and takes the newest
   match, so it can match a committed 40:40:20 trace, log the wrong victims and window, AND STILL PASS.**
3. **The comparator may move. P3 and every reference carry `_preD249`; baselines never do. If D249 lands
   between the gate and the sweep, the outage cells are no longer comparable to P3. A SEQUENCING QUESTION TO
   SETTLE BEFORE THE GATE CELL.**
4. **No E-id exists: zero rows match the outage-correlation study. A stopping condition for the build, not
   for this estimate.**
**Also: prefix caching is ON, via a duplicated last-wins flag, which the history-cached observable requires
and which is EXACTLY the duplicated-flag hazard found on the D250 host size. It must be restated in the
prereg rather than assumed.**
