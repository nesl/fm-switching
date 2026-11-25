# D244's per-robot history-cached observable: NO BUILD NEEDED, it is derivable from committed artefacts, and here is the join proved on a real cell

**Status: measured, not proposed.** D244 requires, per robot and per cell, **"history cached at the first
post-reconnect question"** and **"the number of device-only questions during the window"**. **There is NO
`history_cached` field and none is needed.**

## *** THE FIELD DOES NOT EXIST AND MUST NOT BE WAITED FOR ***

`git grep` over `experiments/orchestration/live2` returns **ZERO** hits for `history_cached` or
`cached_history`. The committed 1x s4 cell has no hist/cache key at top level, in `counts`, or in
`robot_value`. **D242 item B built `Observation.last_arrival_s`, which is an ARRIVAL-TIME observable and
not a cache observable.** **So anyone waiting for a named field will wait forever; the quantity is
derived.**

## THE DERIVATION, with the join proved on `covex-v6-fair-final_n16_s4_1200s_h27_3t_L3_epg_rq30`

| step | artefact | fields |
|---|---|---|
| 1. each robot's reconnect time | the new trace outage schedule | per-device window start and end |
| 2. its first post-reconnect question | `outcomes.jsonl.gz` | `device_id`, `t_opportunity`, `opportunity_id`, `kind` |
| 3. whether that question's history was cached | `request.jsonl.gz` | **joined on `opportunity_id`**: `cached_tokens`, `cached_fraction`, `prompt_tokens` |

*** THE JOIN IS CLEAN: 132 ROBOT OUTCOME ROWS, 132 MATCHED, 0 UNMATCHED. ***
```
device    kind      t_opp   cached_tokens  cached_fraction   prompt_tokens
robo005   recall     6.81            992   0.1366            7,262
robo005   recall    34.83          7,024   0.8242            8,522
robo005   recall    66.06          8,272   0.8304            9,962
robo002   recall    94.96          2,976   0.3709            8,024
```
*** AND `cached_fraction` IS A REAL DISTRIBUTION, NOT A CONSTANT: over 132 robot requests, min 0.0000,
median 0.9243, max 0.9998, with 131 DISTINCT VALUES out of 132. SO IT CAN DISCRIMINATE ARMS. *** **That is
consistency check 3 (distribution sanity) passed BEFORE the run rather than after it: a near-constant here
would have meant the observable could not carry the comparison, and it would have been found only after 20
cells.**
**`cached_fraction` is the right notion for the prediction: it measures how much of the post-reconnect
prompt was served from cache, so a rung that KEPT the offline history reads high and one that LOST it reads
low. Note explicitly that this requires PREFIX CACHING ENABLED, which it is, and which is the mechanism
under test rather than a confound.**

## *** A DEFINITIONAL TRAP THAT WOULD SILENTLY WRECK EVERY ROBOT FIGURE: `kind` DOES NOT SEPARATE ROBOT FROM SINGLE-SHOT ***

```
outcome rows by (kind, device prefix), s4 cell:
   kind=monitor  prefix=dash   11,764      <- dashcam instants, matches the committed denominator
   kind=recall   prefix=asst      357      <- SINGLE-SHOT, matches the committed denominator
   kind=recall   prefix=robo      132      <- ROBOT, matches the committed denominator
```
**All three committed denominators reproduce EXACTLY from this log, which is what validates the derivation
path.**
*** BUT `kind == "recall"` COVERS BOTH ROBOT AND SINGLE-SHOT: 132 + 357 = 489. A robot metric computed over
all 489 recall rows takes a denominator 3.70x TOO LARGE and silently mixes two channels. THE SCORER MUST
FILTER ON DEVICE PREFIX, NOT ON `kind`. ***
**This is the same shape as the channel-identity trap recorded earlier (`PREFIX_TO_TYPE` maps `dash` to
`alert`, so "alert" IS the dashcam channel): the type name and the channel are not in one-to-one
correspondence, and the prefix is the authority.**

## Device-only questions during the window

Derivable from the same two files: a robot question whose `outcomes` row falls inside its device's outage
window, with `cloud_payload.cloud_letter` null and no matching `request.jsonl.gz` row, was answered without
the cloud. **This one is stated as a METHOD rather than as proved, because the cell used for the join above
has no outage in it and so has no in-window questions to test against. It must be verified on the dry-run
cells before the 20 cells are scored.** **Recorded as owed rather than passed.**

## What this changes for D244

- **The reporting requirement in D244 item 2 is NOT blocked and needs no new instrumentation.** It is
  post-processing over artefacts every cell already writes, which per D190 is the Orin's half.
- **It matters most if AMENDMENT 2's Conflict 1 bites.** If both robot attainment metrics are compromised
  under outage and move identically across all five arms, this observable is the only thing that can
  discriminate them, **and it is now known to be available and known to be a distribution.**
