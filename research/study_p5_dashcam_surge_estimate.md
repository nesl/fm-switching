# P5 ESTIMATE: a mid-run dashcam surge (rate multiplier over a window), default OFF

**ESTIMATE ONLY per user ruling D254 part D (2026-11-25 09:29, provisional). NOTHING BUILT.** Every
load-bearing claim below was re-verified against origin/main and against the committed artefact at the
point of use, not carried from the agent report that produced it.

## *** THE FINDING THAT CONSTRAINS THE WHOLE IDEA: THE MULTIPLIER CAN ONLY EVER BE 2 ***

**The dashcam rate is not a free parameter. It is capped at exactly 2x by the committed device-score grid,
and there is no other lever.**
```
fleet/data_sources.py:39-41   NEXAR_INSTANT_CADENCE_S = 0.5   NEXAR_GRID_STEP_S = 0.25   T0 = 3.0
fleet/trace.py:580-584        if key not in orin: raise DS.MissingInput(
                                "no committed Orin device score for instant ...; the dense StudyORIN1
                                 set does not cover this clip at this cadence")
MEASURED from results/dashcam/study_orin1/orin1_dense_scores.jsonl.gz:
    42,014 rows, 300 clips, inter-sample steps {0.25: 41,714}, first t = 3.0 on every clip
    -> max multiplier = 0.5 / 0.25 = 2.0 EXACTLY
```
**Every instant REQUIRES a committed Orin score at `(clip, round(t_local, 6))` or the generator RAISES. So
m = 2 is the only multiplier with real per-instant device answers and latencies.** *** m = 3 OR MORE WOULD
EITHER CRASH ON `MissingInput` OR REQUIRE DUPLICATING OR INTERPOLATING DEVICE ANSWERS, WHICH IS A FABRICATED
INPUT AND A METHODOLOGICAL CHANGE, NOT AN IMPLEMENTATION DETAIL. ***
**Consequences: there is no m-sweep, no dose-response in m, and no m-effect readable at all.** **Plays run
back to back with one play per device and a fixed device set, so there is no gap to shrink, no device to
add and no second play to overlap: the cadence is the only rate lever that exists.**
**If a larger multiplier is wanted, the ASSISTIVE SINGLE-SHOT stream already has `ss_period_s` and a bursty
variant (`SS_BURST_N = 4`, `SS_BURST_GAP_S = 0.5`). That is a different experiment and a user choice, not a
substitution made here.**

## Hours and files

**9 to 11 hours at m = 2**, with a surge window of the outage's shape (one window per run, dedicated seeded
RNG stream, default OFF).
| file | change |
|---|---|
| `fleet/trace.py` | **+170 to +220 / -2 to -6** - DEARER than the outage's +144 |
| `run_live2_real.py` | **+24 / -1** - same shape as the outage, line for line |
| `fleet/emulator.py` | **0 to +6, probably ZERO** - CHEAPER: no new read site is needed |
| NEW `d254_surge_proofs.py` | ~150 lines |
| audited, no edit expected | `scorer/score.py`, `fleet/data_sources.py` (`nexar_instants` already takes `cadence_s`) |

**CHEAPER than the outage in three ways:** no emulator read site (the extra records replay through the
committed path, so the write-only-field hazard on that side disappears), no new data-source code, and the
placement idiom is directly copyable.
*** DEARER IN ONE WAY THAT MATTERS: THE OUTAGE WAS A POST-HOC PASS AND A SURGE CANNOT BE. *** The outage ran
AFTER the records existed and changed one field on one kind. **The instants a surge needs DO NOT EXIST YET,
so it must act inside the dashcam generation loop (`trace.py:534-607`), the hot path, where four things are
index-sequential and will be perturbed: `_epg_episode(play_id, play_refs, idx)` is a function of the CAPTURE
INDEX, the `pending_b` byte accumulator, the `play_refs` list, and the `st.epg_*` counters.**
*** SO THE SURGE CHANGES EPISODE CONTENT, NOT ONLY ARRIVAL TIMING: inserting instants shifts every
subsequent `episode_index` and `episode_frames` and MOVES THE 21-FRAME CYCLE BOUNDARY (`EPG_CAP_FRAMES =
21`, no carry-over) for the remainder of each straddled play. The outage touched no episode field at all. ***

## *** A METRIC-DEFINITION ISSUE THAT NEEDS A RULING, NOT A FIX ***

`scorer/score.py:996-1039` holds the standing score forward one grid point because "the decision cadence is
0.5 s and the AP grid is 0.25 s" (`arr[i] = v; arr[i+1] = v`). **At a 0.25 s cadence the next instant
OVERWRITES that held point with its own value.** **No code change is strictly required and nothing crashes -
the denser answer supersedes the hold, which is arguably correct - BUT the MEANING of streaming AP then
differs inside the window from outside it: in-window instants get full-grid credit and out-of-window
instants get held credit.** **Per CLAUDE.md a metric-definition change must be flagged and discussed, not
applied. This is the largest hidden cost and it has no counterpart in the outage.**

## *** THE DECIDING QUESTION, ANSWERED: THE FAIRNESS DIGEST DOES COVER DASHCAM ARRIVALS. A SURGE IS NOT DIGEST-NEUTRAL. ***

**`CONTRACT.md:152` covers "`monitor_frame` in PUSH mode (A)"; `trace.py:147-149` has
`DIGEST_KINDS = (..., "monitor_opportunity")`; `_digest_tuple` emits a row for every one. AND THESE RUNS ARE
MODE A (`run_live2_real.py:104` defaults `--mode A`, confirmed in a committed cell header). So the pull-mode
exclusion does not apply and every dashcam arrival is a digest row.**
| | outage ON | surge ON |
|---|---|---|
| rows changed | ~180 to 300 moved rows of 14,539 | **every** monitor row at or after the window, plus new rows |
| `n_records` | **unchanged** (records move, none added) | **CHANGES** |
| `opportunity_id` | **unchanged by design** | *** RENUMBERED for every opportunity at or after the window *** |
| `device_answers_sha256` | unchanged | **CHANGES** |
*** THE COST, PLAINLY: ANY ANALYSIS THAT JOINS A SURGE CELL TO A COMMITTED CELL BY `opportunity_id` IS
INVALID BY CONSTRUCTION, NOT MERELY IMPRECISE. *** D218's device-answer work and anything keyed on a
committed `device_answers_sha256` will not line up across the surge boundary.
**Mitigation already exists and must be used: the `extra +=` directory-tag rule gives a surge trace its own
directory, digest and run tag, and AMENDMENT_2's rule that a pooled figure is WITHDRAWN rather than
corrected extends to surge cells unchanged.** **Arm-versus-arm WITHIN a surge cell stays clean, which is the
study's actual question.**
**Note for honesty: the OUTAGE is also not digest-neutral when ON, since it rewrites `r["t"]` on
`history_batch`, which maps to a covered row. All the outage identity claims are OFF-PATH claims. The
difference is one of degree and it is large.**

## *** HOW THIS COULD PASS EVERY PROOF AND TEST NOTHING: THE SURGE IS UNANNOUNCED ***

**`cstate.py:78` declares `cadence_s: float = 0.5`, and the arms compute when the next instant is due FROM
THAT FIELD, not from the trace (`arms.py:217-218`, `:524-525`, `arms_builder.py:152-153`). The ONLY writer of
`.cadence_s` is `coordinator.py:941`, which is the ARM SETTING IT ON ITSELF. NO TRACE FIELD UPDATES IT.**
*** SO THE SHAPE OF THE FAILURE: the trace emits 2x the records, the counts come back exactly 2x, the digest
moves, the OFF-path identity passes, the positive control fails as required - AND EVERY ARM STILL PLANS
AGAINST A 0.5 s CADENCE IT WAS NEVER TOLD HAD CHANGED. The extra arrivals are dropped past the 1.0 s
deadline or absorbed with no change to any action. Every count is non-zero and the mechanism reaches no
decision. *** **That is the `desired_tier` shape exactly: instrumented, varying by condition, read nowhere
that changes a decision.**
**Second form, the outage's own blocker recurring: the binding gates are `budget.can_spend` on GPU SECONDS
and the D179 share gate, NOT a KV-token cap. If the surge's extra load at 1x sits below what those refuse,
no gate refuses, all arms behave identically, and the result is CANCELLED BY GEOMETRY for the same reason
the outage ordering was.** **A surge is MORE likely than an outage to move a GPU-second gate because it ADDS
work rather than deferring it, but whether it does at 1x is NOT determinable from the code and must be
measured.**

## The dry-run gate: declare these five counts BEFORE any cell

| # | count | predicted at m = 2 | zero means |
|---|---|---|---|
| **S1** | extra in-window monitor records, per device and total | `+2D` per dashcam device before losses; +240 at D = 120 | the surge did not fire: **ABSENT LINK, never a negative** |
| **S2** | in-window / out-of-window instant ratio per device, against a matched window | exactly 2, minus edge effects | the multiplier did not apply |
| **S3** | in-window dashcam uplink `queue_s`, p50 and max, against out-of-window | strictly greater, non-zero | the extra records cost nothing: a counting artefact |
| **S4** | in-window deadline misses AND coordinator refusals, each against out-of-window | non-zero and greater in-window | **nothing was refused, so no decision changed** |
| **S5** | instants whose `episode_frames` / `episode_index` differ from the no-surge trace | non-zero by construction | recorded as an acknowledged SIDE EFFECT, not a success criterion |
**Plus the Step 2b bar: the surge-ON against surge-OFF decision-log diff must be NON-ZERO with the first
differing decision quoted; and the in-window gate-refusal count must EXCEED the out-of-window count. If
either is zero the cell is an ABSENT LINK under Rule 1 and no sweep runs.**

**THE DOSE WARNING CARRIES OVER VERBATIM: the surge dose is `n_dash x (m - 1) x 2D`, also FIXED BY
CONSTRUCTION, so there are no weak-dose cells and dose cannot be a covariate.**
*** AND ONE FREE DESIGN CHOICE THAT IS EXPENSIVE LATER: KEY THE SURGE RNG STREAM ON (seed, offset, D) ONLY
AND **NOT** ON m. The outage keyed on k and so re-drew both victims and window when k changed, which is why
no k-effect can be read from the D244 grid. Keying on m would reproduce that confound exactly. ***

## Open, and not inferred

1. *** WHETHER THE 0.25-GRID JPEGs EXIST ON THE RUN HOST, AND IT FAILS SILENTLY. `FrameCache.data_url`
   returns `None` when a frame is not on the host, so a surge whose extra frames have no JPEG would send
   bodies with MISSING IMAGES and the run would NOT error. *** **One command on the H100; an unrecoverable
   confound if skipped. CHECK IT BEFORE THE DRY RUN.**
2. **Whether mixed-cadence streaming AP is acceptable as a metric** (as opposed to not crashing) is a user
   ruling, not a code fact.
3. **The outage build's true wall-clock cost is not recorded**, so these hours are built from proof timings
   plus code surface rather than anchored on a measured duration.
4. **The proof harness `proof_identity.py` is NOT COMMITTED** - it exists only in a scratch directory a
   reboot can clear. **Budget the proof driver as new work or recover that file first.**
