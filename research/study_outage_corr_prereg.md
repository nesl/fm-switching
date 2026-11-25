# StudyOUTAGE-CORR pre-registration: correlated multi-robot outage at 1x

**D242, user ruling 2026-11-24 21:23, provisional.** Written **BEFORE the build**, not after, so the
expectations below cannot be fitted to whatever gets built. The user's ordering listed this item last with
the constraint "before any cell"; writing it first satisfies that constraint strictly and is the only
ordering under which a pre-registration does its job. **Nothing is built at the time of writing. No cell
runs without a user ruling in the morning.**

## The experiment

**k of the 7 robots lose the uplink together for D seconds, then reconnect.** Grid **k in {1, 3, 5}**,
**D = 120 s** with **60 s as an anchor**, one outage window per episode, start chosen deterministically
from the seed and placed mid-episode. **Seeds 4 and 5.** **1x memory only, per D240: never at kv0.5r.**

## Why this is the regime where the policy must choose

On reconnect the reloads compete for a fixed pool. **Arithmetic verified rather than accepted**, with the
1x pool at **62,944** tokens and the stated history p50 of about **55,000** (rung-3 1x s4):

| k | backlog (k x 60 frames x 90 tokens) | history + backlog | against the 62,944 pool |
|---|---|---|---|
| 1 | 5,400 | 60,400 | **FITS** |
| 3 | 16,200 | 71,200 | **EXCEEDS** |
| 5 | 27,000 | 82,000 | **EXCEEDS** |

**So the fit/no-fit boundary lies between k = 1 and k = 3, not at k = 5.** That is a pre-registered
structural expectation and it is the grid's whole point: **k = 1 should show no ordering pressure at all,
and is therefore a negative control rather than a data point.** If k = 1 shows an ordering effect, either
the arithmetic above is wrong or something other than pool pressure is driving the ordering.
**300 s is excluded** on the user's figure that 33 to 37 percent of robot questions would exceed the
context limit once the backlog is included. **Recorded as the user's reason; I have not reproduced that
percentage, and the note says so rather than implying I checked it.**

## Arms

`covex-v6-fair-final` (rung 3, plain), **`covex-v6-fair-final-outage`**,
**`covex-v6-fair-final-outage-fifo`** (the one-factor control, identical except the order is
first-reconnected-first), `simplestream`, `llf`. **Both new arms default OFF everywhere else.**

## Metrics, and the one that cannot work

**PRIMARY: robot correct-by-deadline**, because **it counts device answers**.
*** SECONDARY AND NOT SUFFICIENT ALONE: robot cloud on-time. `robot_value.n_cloud_standing` counts rows
whose `source == "cloud"`, so it is BLIND TO DEVICE ANSWERS BY CONSTRUCTION. An outage forces questions
device-only, which depresses that number for EVERY arm identically whatever the policy does. Quoting it
alone would show an outage effect and no policy effect, on any arm. *** Also secondary: dashcam on-time and
single-shot.
**Note the channel identity established tonight: "alert" IS the dashcam devices** (`PREFIX_TO_TYPE`
maps `dash` to `alert`), so alert attainment and dashcam on-time are one quantity in per-episode and pooled
form, and only one of the two needs quoting.

## Floors, as they stand tonight, for the metrics this study will use

| metric | floor | provenance |
|---|---|---|
| robot correct-by-deadline | **2 opportunities** | the first in-condition same-code pair, n=1 |
| robot cloud on-time | **2 opportunities** | same pair; the historic cross-regime figure was 1 |
| dashcam on-time | **2 pooled instants, up to 3** | same pair; the "up to 3" allows one kind-2 loss |
| alert attainment (= dashcam, per-episode) | 0.000148 fixed-19 / 0.002434 true-denom | same pair |
| single-shot | **4 of 357** | same pair |
**All are n = 1 and license the MEAN only.** That pair disagreed on 78 to 84 percent of episodes.
**And the robot floor transfers as an absolute COUNT, not as a fraction**: 1 of 132 is 0.0076 and 1 of 127
is 0.0079, so denominators must be read per cell and never carried between seeds.

## Pre-registered expectations

- **k = 1: no ordering effect.** The pool is not exceeded, so `-outage` and `-outage-fifo` should be
  indistinguishable. **This is the negative control.**
- **k = 3 and k = 5: ordering pressure exists**, so if the state planner's ranking is worth anything,
  `-outage` should beat `-outage-fifo` on **robot correct-by-deadline**, and the margin should be larger at
  k = 5 than at k = 3.
- **If `-outage` and `-outage-fifo` are indistinguishable at k = 5, that is a real negative about the
  ranking**, provided the characteristic-decision count is non-zero.
- **With outages OFF both new arms must equal rung 3 exactly**, byte-identically in the decision log.

## What would invalidate a run, declared in advance

**The dose must be reported beside every delta.** Tonight the one-factor TOUCH ablation fired 2,966 times
at s4 and **140 times at s5, a 21-fold difference, and its sign flipped between the two seeds.** A delta
obtained at a low dose is not an effect size. **So every outage cell reports its characteristic-decision
count, and a cell whose count is low is a weak-dose condition and is labelled one.**
**A zero characteristic-decision count makes the cell an ABSENT LINK, never a negative.**
**Denominators are read from each cell's own sweep row**, never carried: all three pool denominators move
with seed (robot 132 at s4 and 127 at s5, single-shot 357 and 356, dashcam instants 11,764 and 11,769).
**Episode structure is invariant WITHIN a seed across arms and kv settings and NOT across seeds**, so
episodes may not be pooled across seeds.

## Build items and their proof obligations

**A. Trace-level correlated outage, default OFF.** New args `outage_robots_k`, `outage_duration_s`,
`outage_seed_offset`. During the window frames are not offered; their OFFER time shifts to the reconnect
instant and `fleet/links.py`'s `UplinkQueue` produces the burst and records `queue_s`. Questions inside the
window go device-only through the existing `device_answers` path. The schedule is recorded in `trace_meta`.
**PROOF: with outages OFF the trace is byte-identical, `SHA256SUMS` and `fairness_digest()` equal to the
committed values.**
**B. The observable.** A per-device last-arrival time maintained by the coordinator, carried in the schema,
exposed on `obs`. *** PROOF: NAME THE READ SITE THAT CHANGES A DECISION, with file and line. A write-only
field FAILS the build. *** This project's canonical failure is exactly that shape.
**C. The policy branch.** `-outage` ranks reconnecting robots by the state planner's existing score,
`w_d x p(question within horizon) x (p_warm - p_cold)` minus harm to others, and issues chunked catch-up in
that order within the pool. `-outage-fifo` is identical but first-reconnected-first. **PROOF: the
characteristic decision, orderings that differ from FIFO, counted and at least 1 on a dry run with outages
on.**
**D. Proofs.** Switch read-back with types; one-factor assertion between the two new arms; byte-identity of
every other `arms_*.py`; a decision-log diff showing both new arms equal rung 3 exactly with outages OFF;
and reachability at k = 5, D = 120 on a dry run.

## Scope and constraints

**Build in a scratch tree. No pushes to `experiments/orchestration` or `experiments/lib` until block A
finishes, about 23:40, and then only with proofs passing. Nothing reaches the H100 queue without a user
ruling in the morning. The D238 queue is unchanged and has priority for anything shared.**
**If a step needs a methodological choice not covered by the ruling, that step stops, the options are
written down, and the next step continues.**
