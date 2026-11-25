# AMENDMENT 2 to StudyOUTAGE-CORR: THE D244 GRID, AND TWO CONFLICTS WITH THE STANDING PRE-REGISTRATION THAT ARE FLAGGED RATHER THAN RESOLVED HERE

**Status: PROVISIONAL, written before any cell runs, per user ruling D244 (2026-11-25 07:08).** This
amendment registers the grid the ruling names and records, in advance, two places where that grid departs
from `study_outage_corr_prereg.md`. **Neither departure is applied silently and neither is reversed by me:
the ruling governs, and the conflicts are stated so a reader of the results knows they were known
beforehand.**

## The registered grid, as ruled

| field | value |
|---|---|
| outage | correlated multi-robot, **1x memory only** (D240: never at kv0.5r) |
| k | **{3, 5}** |
| D | **120 s**, one window per episode, mid-episode, deterministic from the seed |
| arms | `covex-v6-fair-final`, `covex-v6-fair-final-stateoff`, `llf`, `mooncake`, `simplestream` |
| seeds | **4 and 5** |
| cells | **5 arms x 2 k x 2 seeds = 20** (arithmetic checked: matches the ruling's figure) |
| tag | `_L3_epg_rq30_out-k3-d120` form, so outage cells NEVER pool with no-outage cells |
| excluded | the `-outage` and `-outage-fifo` ordering arms are NOT in this run, per the ruling |

**Prediction on the record, from the Orin screen `f07c3d8f` ("D242 correlated multi-robot outage screen",
2026-11-24 21:33, which resolves in this clone):** **rung 3 keeps offline histories; the baselines and
`-stateoff` lose them.**
**Per-robot reporting, as ruled and additional to the attainment metrics: history cached at the FIRST
POST-RECONNECT QUESTION, and the number of DEVICE-ONLY QUESTIONS during the window.**

## *** CONFLICT 1 IS RESOLVED BY D251, AND THIS AMENDMENT'S RECOMMENDATION IS WITHDRAWN ***

**D251 (2026-11-25): RECORD ALL METRICS AND CHOOSE THE HEADLINE AT PLOTTING TIME.** *** SO "WHICH ROBOT
METRIC IS PRIMARY" IS NOT DECIDED AT RUN TIME AT ALL, AND THIS AMENDMENT'S RECOMMENDATION THAT THE
HISTORY-CACHED OBSERVABLE BE MADE PRIMARY IS WITHDRAWN. *** **Every cell records robot cloud on-time,
correct-by-deadline, dashcam on-time, single-shot AND the per-robot history-cached observable, and none is
ranked above another while the cells run.**
**WHAT SURVIVES, because it is a measurement fact and not a ranking: the device-only questions have NO cloud
payload and NO request rows, BOTH robot metrics are blind to them in OPPOSITE directions, and `t_local` is
null on every robot row. So they are UNMEASURABLE and must be reported as a COUNT whichever metric is later
chosen as the headline.**

## THE SUPERSEDED CONFLICT, KEPT FOR THE RECORD

## *** CONFLICT 1, AND IT IS THE ONE THAT MATTERS: THE RULING'S PRIMARY METRIC IS THE ONE THE PRE-REGISTRATION SAYS CANNOT WORK ***

**The standing prereg's metrics section is titled "Metrics, and the one that cannot work", and it says:**
> **PRIMARY: robot correct-by-deadline**, because it counts device answers.
> *** SECONDARY AND NOT SUFFICIENT ALONE: robot cloud on-time. `robot_value.n_cloud_standing` counts rows
> whose `source == "cloud"`, so it is BLIND TO DEVICE ANSWERS BY CONSTRUCTION. An outage forces questions
> device-only, which depresses that number for EVERY arm identically whatever the policy does. Quoting it
> alone would show an outage effect and no policy effect, on any arm. ***

**D244 makes robot cloud on-time the PRIMARY metric, with correct-by-deadline beside it and the device half
noted as inert.** **So the two documents disagree about which robot metric can carry this experiment, and
they disagree for mechanical reasons on both sides:**
- **the prereg's reason:** cloud on-time cannot see device answers, and an outage pushes questions
  device-only, so it falls for every arm identically.
- **the ruling's reason:** during an outage the device half of correct-by-deadline is inert, so that metric
  is compromised too.
*** IF BOTH REASONS HOLD, THEN BOTH ROBOT ATTAINMENT METRICS ARE COMPROMISED UNDER OUTAGE, AND NEITHER CAN
DISCRIMINATE THE ARMS. That is a real risk to the run and it is recorded here before the run, not after. ***

**WHAT I RECOMMEND, AND IT IS A RECOMMENDATION, NOT A CHANGE I HAVE MADE.** **The ruling already orders the
quantity that tests the prediction directly: "history cached at the first post-reconnect question", per
robot.** **That is an OBSERVABLE OF THE THING PREDICTED, not a proxy for it** - the prediction is that rung
3 keeps offline histories and the baselines lose them, and a per-robot cached/not-cached count at the first
post-reconnect question measures exactly that. **I therefore recommend that the history-cached observable
be the PRIMARY measure for the headline prediction, with cloud on-time and correct-by-deadline both
reported and neither load-bearing alone.** **Under the ruling as written, cloud on-time stays primary; this
amendment does not override it and the cells will be scored as ruled.** **The user's ruling is requested on
this point and the run can proceed either way, because every one of these quantities is reported regardless
of which is called primary.**

## CONFLICT 2: THE PRE-REGISTERED NEGATIVE CONTROL k = 1 IS NOT IN THE GRID, AND SOMETHING ELSE MUST SERVE

**The standing prereg says of k = 1: "k = 1 should show no ordering pressure at all, and is therefore a
negative control rather than a data point."** **The D244 grid is k in {3, 5}, so that control is absent.**
*** BUT ITS ROLE DOES NOT TRANSFER, AND THE REASON IS CLEAN: k = 1 was a control for ORDERING PRESSURE, and
the ordering arms are explicitly excluded from this run. A control for a mechanism that is not being tested
is not a control this run needs. ***
**The negative control this run DOES need is the OUTAGES-OFF condition, and it is already proved rather
than owed:** with outages off, all five arms are byte-identical to their unpatched selves, proved at the
300 s cell and at the posted 1,200 s cell, with a positive control (`llf`) showing the check can fail.
**That is recorded as this study's Step 4 control.** **It is a stronger control than k = 1 would have been,
because it is an identity rather than an expected-null.**

## *** AND A FINDING THAT RESOLVES BOTH OF D242's BLOCKERS RATHER THAN LEAVING THEM PENDING ***

**D242 was reported blocked on two grounds. BOTH DISSOLVE UNDER THIS GRID, and the reason is the same for
each: both concerned the ORDERING ARMS, which this run excludes.**
- **Blocker 1, "the ordering is a pure permutation":** no gate refuses on KV tokens at 1x, so reordering
  reconnection service changes no admission decision. **That is a statement about `-outage` versus
  `-outage-fifo`, and neither arm is in this run.**
- **Blocker 2, the unsupported 55,000-token history premise (AMENDMENT 1):** it mattered because ORDERING
  pressure requires the pool to be exceeded, and AMENDMENT 1 found that on an empty pool all three k values
  fit, leaving the grid with no positive condition. **This run does not need the pool to be exceeded at
  all: it asks whether histories SURVIVE a disconnection, which does not depend on pool pressure.**
*** SO THE D244 REDESIGN DOES NOT WORK AROUND THE TWO BLOCKERS, IT MAKES THEM INAPPLICABLE. I am recording
that explicitly because I reported those blockers as open four hours ago and a reader should not have to
reconcile the two statements themselves. ***

## Carried forward from the standing prereg, unchanged and binding

- **Dose beside every delta.** Every outage cell reports its characteristic-decision count. **A cell with a
  low count is a weak-dose condition and is labelled one; a ZERO count makes the cell an ABSENT LINK, never
  a negative.** *(Precedent on these exact two seeds: a one-factor ablation fired 2,966 times at s4 and 140
  at s5, a 21-fold difference, with the sign flipping between them. A delta at low dose is not an effect
  size.)*
- **Denominators are read from each cell's own sweep row and never carried between seeds** (robot 132 at s4
  and 127 at s5; single-shot 357 and 356; dashcam instants 11,764 and 11,769). *(This rule was broken three
  times in the session that wrote this amendment, each time by carrying one seed's denominator onto
  another's figure.)*
- **Episodes may NOT be pooled across seeds**, because episode structure is invariant within a seed and not
  across seeds.
- **Channel identity: "alert" IS the dashcam devices** (`PREFIX_TO_TYPE` maps `dash` to `alert`), so alert
  attainment and dashcam on-time are one quantity and only one needs quoting.
- **No 0.25x. Never seeds 1 to 3. Disk refusal below 15 GB. Outage work at 1x only, never stacked with
  reduced memory (D240).**

## *** ADDED 2026-11-25 08:4x, BEFORE ANY k-EFFECT IS READ: k = 5's OUTAGE IS NOT k = 3's OUTAGE PLUS TWO ROBOTS ***

**Measured on the first two gate cells, both `covex-v6-fair-final` at seed 4:**
```
k = 3   victims robo003, robo005, robo006      window  786.901505 - 906.901505 s   deferred 180
k = 5   victims robo001, robo002, robo003,     window  509.505651 - 629.505651 s   deferred 299
                robo004, robo005
```
*** THE VICTIM SETS DO NOT NEST - `robo006` is a victim at k = 3 and NOT at k = 5 - AND THE WINDOWS DO NOT
OVERLAP AT ALL, being 157 s apart. *** **The cause is in the committed code: `trace.py`'s
`rng_stream_key` is `"outage|<seed>|<offset>|<k>|<D>"`, so k is part of the placement draw and changing k
re-draws BOTH the victims and the window.**
**CONSEQUENCE: ANY k = 3 AGAINST k = 5 CONTRAST CHANGES THREE THINGS AT ONCE - the number of robots, which
robots, and WHEN IN THE RUN the outage falls.** **The third may matter as much as the first: a different
window means a different episode phase and a different cache state.** *** SO NO k-EFFECT MAY BE READ FROM
THIS GRID. k = 3 and k = 5 are two separate conditions, not two doses of one. ***
**This is the same shape as the dose-and-seed confound recorded for the touch ablation, and it is recorded
here BEFORE any cell is scored rather than after a difference is seen.**

**WHAT IS NOT AFFECTED, and it is the study's actual question: THE ARM-VERSUS-ARM CONTRAST IS CLEAN.** All
five arms at a given k share the same seed, the same victims and the same window - confirmed on the k = 3
gate cell, whose victims and window reproduce the dry run's to six decimals across five arms. **The
prediction under test is "rung 3 keeps offline histories, baselines and `-stateoff` lose them", which is an
arm contrast within a k. That contrast is unharmed.**
*** RESOLVED FORWARD BY D253, WITHOUT DISTURBING THIS GRID: THE NEXT DESIGN USES A FIXED WINDOW WITH
NESTED VICTIMS, SO A k-EFFECT WILL BE READABLE THERE. THE D244 k5 CELLS ARE **NOT** RE-RUN. *** **So the bar
above is PERMANENT for THIS grid and FIXED for the next one, which is the cheapest available resolution: no
accelerator time is spent correcting a design whose cells already exist.**

**A FIX EXISTS IF THE USER WANTS A k-EFFECT: drop k from the placement key so the window is shared and the
victim sets nest. It is a code change plus a re-run of the k = 5 cells, and it is the user's call, not
mine.**

## *** THE DOSE IN THIS GRID IS NOT A VARIABLE: IT IS k x (D / 2), FIXED BY CONSTRUCTION ***

**Measured on all three gate cells and explained from the trace design:**
```
in per-frame mode every robot streams ONE FRAME EVERY 2 s, so a D-second outage defers D/2 records per
victim robot, and the dose is k x (D / 2):
   k = 3, D = 120  ->  predicted 180   observed 180 (60 / 60 / 60), at seed 4 AND at seed 5
   k = 5, D = 120  ->  predicted 300   observed 299 (60 / 60 / 60 / 59 / 60)
```
*** SO `deferred_history_records` IS CONSTANT ACROSS SEEDS AND ACROSS ARMS. THREE CONSEQUENCES, ALL
RECORDED BEFORE SCORING: ***
1. **The carried-forward prereg rule "a cell whose count is low is a WEAK-DOSE condition and is labelled
   one" CAN NEVER FIRE in this grid.** **There are no weak-dose cells, and nobody should look for dose
   variation or explain a seed difference by dose.** *(This is the OPPOSITE of the touch ablation, where
   the dose varied 15-fold across these same two seeds and the sign flipped with it.)*
2. **The dose is COLLINEAR WITH k, so it cannot serve as a covariate either.** **With k already confounded
   with window placement, that leaves NOTHING to regress a k-effect on, which reinforces the no-k-effect
   bar above rather than softening it.**
3. **The zero-count stopping rule still stands and is still meaningful**, because a zero would mean the
   outage did not fire at all, which is a different condition from a small dose.
**`CONTRACT.md`'s "`history_append` every 30 s per robot session" is a DIFFERENT QUANTITY from the
per-frame stream and must not be used to predict this count.**
**Side effect worth recording so it is not re-flagged: the non-victim in-window count (275) and the victim
whole-run count (1,797) are IDENTICAL at seed 4 and seed 5 despite different victims and different windows.
That is structural, not a coincidence, for the same reason.**

## THE METRIC CONFLICT, SHARPENED BY THE FIRST GATE CELL'S RUN-LEVEL DATA

**On `covex-v6-fair-final` k = 3 s4: the 132 robot rows are 128 cloud (121 within L, 7 late) and EXACTLY 4
with no cloud payload. Those 4 are all `robo003`, all inside the window, and they have ZERO request rows -
never sent to the cloud, as the outage requires.**
*** AND THEY COUNT AGAINST CLOUD ON-TIME BY CONSTRUCTION: 121 of 132 includes them in the denominator.
AMENDMENT 2's Conflict 1 is therefore CONFIRMED on data rather than argued from the schema. ***
**But the sharpening matters and runs in the policy's favour: the outage is IDENTICAL across all five arms
at a given k, so those 4 are a COMMON penalty, not a bias. A common additive penalty shifts every arm down
equally and does NOT destroy discrimination between arms.** **So cloud on-time can still rank the arms on
the other 128 questions.**
*** WHAT IT CANNOT DO IS SEE THE DEVICE-ONLY PATH AT ALL, and `t_local` IS NULL ON EVERY ROBOT ROW, so the
device answer is not timestamped either. BOTH ROBOT METRICS ARE BLIND TO THOSE 4 QUESTIONS, in opposite
ways. *** **Therefore: the 4 device-only questions are UNMEASURABLE in this grid and must be reported as a
count, never scored as successes or failures. The discriminating signal has to come from the
history-cached observable on the POST-RECONNECT questions, which is exactly why that observable is
collected.**

## What would invalidate a run of this grid, declared in advance

1. **A zero characteristic-decision count in any cell**: that cell is an ABSENT LINK and is not a negative.
2. **No frames withheld during the window, or no burst at reconnect, or no device-only questions**: the
   outage did not fire and the cell is void. **This is why the ruling orders a dry run per arm BEFORE the
   20 cells, and that dry run is a gate, not a formality.**
3. **An outage cell pooled with a no-outage cell**: the tag exists to prevent it and any pooled figure is
   withdrawn rather than corrected.
4. **Both robot metrics moving identically across all five arms**: that is the failure Conflict 1 predicts,
   and if it occurs the run has measured the outage and not the policy. **In that case the history-cached
   observable is the only thing that can rescue the study, which is the second reason to collect it.**
