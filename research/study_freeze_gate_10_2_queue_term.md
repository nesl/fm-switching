# Freeze-gate 10.2, the hard-zero queue term: PREPARED, NOT APPLIED, and the decision count is ZERO for a measured reason

**Status: REPORT ONLY. Nothing applied, nothing pushed to `experiments/`.** D238 freezes the run path until
block A finishes, and changing `arms_v6state.py` alters the freeze candidate, which is the user's ruling.
Collected by a watchdog resume from an agent that completed its measurements and was stopped before it
could report; the four result files were recovered from its scratch tree.

## The answer the user asked for

**How many planner decisions would change? ZERO at 1x. And zero at kv0.5r, but that second zero is NOT
INTERPRETABLE.** Four dry runs of `covex-v6-fair-final` at seed 4, n16, 1200 s:

| run | tree | gpu_kv override | in force | digest | decisions | TOUCH | deviations |
|---|---|---|---|---|---|---|---|
| base 1x | base | None | 62,944 | `5a03c2807da3681a` | 60,920 | 2,954 | 2,960 |
| **fixed 1x** | fixtree | None | 62,944 | **`5a03c2807da3681a`** | 60,920 | 2,954 | 2,960 |
| base kv0.5r | base | 31,472 | 31,472 | `5a03c2807da3681a` | 60,920 | 2,954 | 2,960 |
| **fixed kv0.5r** | fixtree | 31,472 | 31,472 | **`5a03c2807da3681a`** | 60,920 | 2,954 | 2,960 |

**ONE distinct digest across all four runs.** Every stat is identical, to the last counter.

## Why the count is zero, measured rather than argued

*** THE QUANTITY THE HARD ZERO STANDS IN FOR IS ITSELF ZERO IN EVERY OBSERVATION. *** From the probe the
agent instrumented:
```
probe.ov_hist   (overlap)  {"0": 10606}            <- ALL 10,606 observations at overlap 0
probe.npend_hist (pending) {"0": 10181, "1": 425}
probe.calls                queued_behind_calls 61034, cache_refills 10606, nonempty_others 2314
harm_warm_no_queue         58,720 of 60,920 decisions = 96.4 percent have NO QUEUE AT ALL
```
So in **96.4 percent** of decisions there is nothing queued, and in the remaining 3.6 percent the measured
overlap is **still zero in all 10,606 refills**. **Supplying the real queue term cannot change a decision
because the real queue term is zero.**

**RULE 2 CLASSIFICATION: the fix is CORRECT and its effect is UNEXERCISED.** Not "fired and did not help",
and emphatically not "the defect is harmless". The mechanism the fix restores (a non-zero queued-ahead
overlap) **does not occur in this workload at all**.

*** AND THE READING TO GUARD AGAINST, WHICH IS THE WHOLE VALUE OF THIS NOTE: "zero decisions change" IS NOT
EVIDENCE THAT THE FIX IS UNNECESSARY. *** The hard zero is still wrong as code. It happens to coincide with
the true value in this workload, and it would diverge in any workload with real queueing. **A decision
count is the wrong test for this defect, and it returns the reassuring answer.**

## *** A SECOND AND MORE SERIOUS FINDING: THE kv0.5r OVERRIDE IS ALSO DECISION-NEUTRAL ON THIS HARNESS ***

The same digest appears with `gpu_kv_in_force` **31,472** and **62,944**. **The override reaches the config
and is read back correctly, and changes no decision.** So this dry harness **cannot distinguish the two
pools**, and the kv0.5r decision count the user asked for **is not answerable on this instrument**: the
zero is a property of the harness, not of the fix.
**This is the same class as the `-notouch` proof-2 failure earlier today, and the same remedy applies: the
committed pool-bearing dry numbers come from the `d210_kv025_one_cell.py` driver carrying the full live
recipe, not from this harness.** A pool override that is live at the config level and absent at the
decision level is this project's canonical shape: **written, read back, and changing nothing.**

## What is NOT established

- **No decision-log diff was obtainable**, because the logs are byte-identical; by the Step 2b rule
  identical logs are an **ABSENT LINK**, never a negative.
- **The one-factor assertion is moot** on a zero-difference result and was not completed.
- **Whether the fix matters in a queueing regime is untested**, and no committed cell in this project has a
  non-zero measured overlap, so there is currently no workload in which to test it.
- **The kv0.5r figure is unavailable**, as above. It should be taken from the `d210` driver if it is wanted.

## Recommendation, for the user

**Do not apply the fix on the strength of this result, and do not retire the defect on it either.** The
honest position is that `arms_v6state.py` passes a wrong constant that is numerically right in every
workload measured so far. **The decision that matters is whether the paper's claims depend on a regime with
queueing**; if they do, the fix is required and needs a workload that exercises it, and if they do not, the
defect can be recorded as latent with this measurement as the evidence.
