# P3 IS THE FIRST CELL IN THE PRESSURE PILOT WHERE ANY D253 CONDITION HAS FIRED, AND IT REFUTES THE FINDING THAT WAS PRE-WRITTEN FOR IT

**P3 = `covex-v6-fair-final` n16 1x s4 `_c3-11-2` (ratio 3:11:2, so ELEVEN robots of sixteen against six in
the reference) `_preD249`, ended 11:30:51, valid, 6,980 requests, 0 errors, `source_agreement` OK.**
**Run by user ruling REGARDLESS of P2's result, on the user's reasoning that "rung 3 sheds dashcam plays,
not robots, and robots are what it keeps in host memory, so P3 is the one demand direction your mechanism
does not cover."**

## SCORED AGAINST THE RULE PRE-REGISTERED AT `b7a0b3f5`, BEFORE ANY CELL WAS SCORED

| condition | definition | P3 | verdict |
|---|---|---|---|
| 1 | SERVER `vllm:kv_offload_cpu_cache_usage_perc` reaching about 1.0 | **0.163** (planner `host_peak` 9,337 tokens against header 110,630) | **FAILS** |
| 2 | P(cold) on idle-gap robot questions, cold = `cached_fraction` < 0.5 | **0.179 on 39** | *** PASSES *** |
| 3 | `memory_pressure.enact_placement_totals.evicted` > 0 | **2** | *** PASSES *** |

**P1 n20, P1 n24 and P2 all returned 0 of 18 on condition 2 and `evicted` 0. P3 is the FIRST non-zero on
either.**
*** SO THE USER WAS RIGHT AND I WAS WRONG. ROBOT-HEAVY DEMAND DOES PRODUCE MEMORY PRESSURE. THE FINDING THE
USER PRE-WROTE FOR A P3 FAILURE - "rung 3 converts added demand into shedding, not memory pressure" - IS
REFUTED BY P3 AND IS NOT RECORDED. ***
**My own mechanism, confirmed on three cells and stated as a monotone shedding signature, was confirmed only
in the directions that load the ALERT channel. P3 loaded the ROBOT channel and the signature broke. The
three confirmations were not three tests of one claim; they were three tests of the same direction.**

## THE PRE-REGISTERED THRESHOLD CAUTION IS DISCHARGED, AND IN THE GOOD DIRECTION

The rule required the full distribution beside P(cold), so the threshold could be moved later without a
re-run, and required me to say plainly if 0.5 fell inside a cluster, **because a threshold inside a mass is
a bad threshold.**
```
min 0.000 | p10 0.167 |  <-- 0.5 falls in this gap, width 0.460, NO points in it -->  | p20 0.627
p30 0.768 | p40 0.819 | p50 0.830 | p60 0.866 | p70 0.882 | p80 0.903 | p90 0.925 | max 0.955
```
*** 0.5 IS NOT INSIDE A MASS. A COLD CLUSTER OF ABOUT SEVEN QUESTIONS SITS BELOW 0.17 AND THE WARM MASS
BEGINS AT 0.63, SO ANY THRESHOLD FROM ABOUT 0.2 TO ABOUT 0.6 RETURNS THE SAME COUNT. THE RESULT IS
THRESHOLD-INSENSITIVE OVER A THREEFOLD RANGE. ***

## *** A DENOMINATOR SUBTLETY THAT RUNS IN OUR FAVOUR, SO IT IS STATED AND NOT MERGED ***

**There were 42 idle-gap questions. `cached_fraction` is defined only on the 39 that had a cloud request, so
the reported P(cold) is 7 of 39 = 0.179. THE OTHER THREE WERE NEVER SERVED AT ALL.**
*** THOSE THREE CANNOT BE SCORED AS WARM. If an unserved idle question counts as a failure of warmth the
figure is 10 of 42 = 0.238. BOTH ARE REPORTED AND THEY ARE NOT MERGED, because the three may be unserved
for reasons unrelated to coldness. The point of recording it is that the smaller figure is the conservative
one and the exclusion silently favours the policy. ***

## MAGNITUDE, KEPT HONEST

*** TWO EVICTIONS IS NOT A REGIME. IT IS THE FIRST EVIDENCE THAT THE PATH EXISTS. *** Condition 1 still
fails at 0.163 against about 1.0, so the server tier is nowhere near capacity and the policy-visible
pressure is small. **What P3 establishes is REACHABILITY in the robot-heavy direction, not a regime in it.**

## THE ROBOT METRICS, THREE TOGETHER PER D257 (3), AND THEY TELL ONE STORY WITH THE ABOVE

| cell | robot cloud on time | cloud accuracy on served | correct by deadline |
|---|---|---|---|
| P2, `_rq10`, 6 robots | 342 of 355 | 0.666667 | 0.645070 |
| **P3, `_c3-11-2`, 11 robots** | **176 of 229** | **0.608** | **0.555** |

**Single-shot and dashcam: SS 222 of 238; dashcam 4,770 of 5,869. `release_infeasible` 776, ALL alert, with
recall 0 and `budget_refusal_recall` 0, so the census's decline proxy and the decision kind coincide
exactly: declines 21 = `recall_REJECT` 21, and 10 of the 21 fall inside sustained cold spans.**
*** MORE ROBOTS, WORSE ON EVERY ROBOT METRIC, AND MEMORY PRESSURE APPEARS. THAT IS ONE COHERENT STORY
RATHER THAN TWO, AND IT IS THE FIRST TIME THE PRESSURE AND THE DEGRADATION HAVE MOVED TOGETHER. ***
