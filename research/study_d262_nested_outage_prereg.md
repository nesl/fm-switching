# StudyD266-NESTOUT: PRE-REGISTRATION OF THE NESTED-VICTIM, TRUE-OUTAGE CONDITION

*** AMENDED UNDER USER RULING D273 (1), 2026-11-25: NESTOUT MOVES TO TRUE OUTAGE SEMANTICS.
Frames a victim captures during the outage are LOST TO THE CLOUD, not buffered and not drained on
reconnect; THE DEVICE STILL HOLDS THEM. The buffered variant that this file first pre-registered is
NOT deleted and NOT wrong: it is the other semantics, it is the CLOSED ALTERNATIVE recorded at
commit `722c449f`, and it is still the DEFAULT everywhere else in the harness. D = 120 s, the
centred window at 540.0 to 660.0 s, and the nested victims are UNCHANGED. ***
**Re-resolved for this amendment: `origin/main` = `f8ae560d80e69f9028517f8bae08dede625089ba`,
47 commits past the sha the build was read through, and all five files the build changes are still
byte-identical at it, so nothing needs rebasing.**

**Ruling: user, D266 item 2, 2026-11-25 12:25. Estimate it implements: `research/study_d262_nested_outage_estimate.md`
(commit `523b350d`), APPROVED. Built as specified; nothing redesigned.**
**Written BEFORE any cell runs. Every number below was measured on flash CPU with no GPU, no engine and no cell,
read through the literal sha `2ddb69f3ed0e7b26b508a0883814b67c9f80a59f`, in a scratch tree. The repo was not
edited.**
**RE-RESOLVED AFTER THE BUILD, AND CHECKED RATHER THAN ASSUMED. `origin/main` moved during the build and is now
`9b9c1160c6996076fe7ebaf8137921566e471166`, 23 commits past the sha this build was read through. Nothing needs
rebasing, and that is a checked statement and not a hope: the approved estimate's blob is IDENTICAL at `523b350d`,
`2ddb69f3` and `9b9c1160` (`df9194ac`); ALL FIVE files this build changes are BYTE-IDENTICAL at `2ddb69f3` and
`9b9c1160`; the five committed `out-k3` / `out-k5` cells are the same five and no new outage cell has landed; no
`study_frozen_grid_driver_v42.sh` exists on `origin/main`, so the new driver name does not collide; and
`research/EXPERIMENTS.md` at `9b9c1160` still has NO row for this study.**
**THIS DESIGN ADDS NO HOST-TIER-CONDITIONED TERM OF ANY KIND. 1x only, no memory token, as ruled, and the driver's
D240 stack refusal (tested) refuses any tag carrying an outage together with `_kv0.5`, `_kv0.25` or `_h0.<f>`. The
D250 duplicated-flag incident is cited in section 4 ONLY as the SHAPE of a last-wins argv hazard, which is a
statement about how a repeated flag resolves and not a claim about what the host size did or did not drive.**
**E-ID: `StudyD266-NESTOUT`.** The user is writing the row and committing this file.
**THREE POINTS SETTLED BY THE USER AFTER THE BUILD, recorded here because each one closes something this
document had open:**
1. **SEQUENCING (what section 7 lists as the comparator risk) IS SETTLED: the outage cells run AFTER the D265
   push with `-q` OFF.** The byte-identical proof is what makes rung 3 comparable to P3 and to the `_preD249`
   references. `-q` gets its own outage cells ONLY if it passes its own gate.
2. **NO SEPARATE TWO-CELL KEYING GATE.** Its cells are the first two of scope A, and the abandon check runs
   on them.
3. **The cells queue behind D250 and the D249 gate cell, so there is no accelerator pressure on this study.**

**THIS DOCUMENT IS NOT A LICENCE TO RUN; it is what must be true before a cell is launched.**

---

## 1. THE DESIGN, AS RULED

| | |
|---|---|
| mix | **`_c3-11-2`** (robot-heavy, 3 dashcam : 11 robot : 2 assistive at n=16) |
| memory | **1x ONLY. NO memory token** anywhere in this design (D240: never stacked). No `kv0.5r`, no `kv0.25`, no `_h0.5` cell. |
| outage | correlated, robot-only, one window per run, `D = 120 s` |
| placement | **FIXED at the centre of the committed band**: `t_start = (run_s - D)/2 = 540.0 s`, window **540.0 to 660.0 s**. The committed band is `[0.25, 0.75] x (run_s - D) = [270, 810]`, so this is a POINT OF THE EXISTING RULE and not an extrapolation. |
| victims | **NESTED ACROSS k**: the first `k` of ONE k-independent permutation of the robot ids, with the whole permutation recorded in `trace_meta.json` as `victim_permutation` |
| k ladder | **{1, 3, 5}**, with k=1 the nested floor that restores the standing one-device-at-a-time direction |
| seeds | **4 and 5** (never 1 to 3) |
| scope A | 2 arms x k{3,5} x s{4,5} = **8 cells**, run FIRST, with the abandon check on the first two |
| scope B | 5 arms x k{3,5} x s{4,5} = 20 cells, plus the k=1 rung, **30 cells in all**. **Baselines run in the new condition.** |
| comparator | **P3 and the in-regime regime-gate cells. NEVER the existing 40:40:20 outage grid.** `w_d`'s definition is unchanged but its value moves, because the pooled robot denominator moves from 132 to 229 (confirmed below: 229 robot questions at this mix). |

---

## 1b. *** THE SEMANTICS SWITCH, AND WHY THE RULING CHANGED IT ***

| | |
|---|---|
| switch | `outage_semantics`, **DEFAULT `buffered`** (the committed D242 behaviour, verbatim) |
| this condition | `outage_semantics=true`: the victim's in-window `history_batch` records are REMOVED, so those frames never reach the cloud and no reconnect drains them |
| cell tag | **`_lost`**, on an outage-tagged cell, refused unless the flag is in the launch arguments and unless the cell's own `trace_meta` records frames actually lost at 90 tokens per frame |
| meta | `outage.semantics`, plus an `outage.lost` block with the records, frames, tokens, per-session split and the header re-attribution |
| the device | **UNTOUCHED.** `device_answers` is built before the outage block and never read by it |

**WHY: the buffered semantics closed the mechanism this study exists to test.** Measured before any
cell: the deferred frames are 60 records and 1,449,630 bytes per victim, which serialise in 0.853 s
on the committed 13.6 Mbps uplink with one queue per device, so the whole backlog has landed 0.87
to 0.89 s after reconnect, and **not one affected question is asked inside that sub-second
interval**, making the drain-bounded dose zero at every pair. Under true semantics there is no
drain, so **the bounded columns are NOT APPLICABLE and must never be read as zeros.**

## 2. THE CAUSAL CHAIN, THE DOSE, AND WHAT THE HARNESS ACTUALLY DOES WITH THE WITHHELD FRAMES

*** THE DOSE WAS WRONG IN THE FIRST VERSION OF THIS FILE AND THE USER RULING CORRECTED IT. The first
version counted questions ASKED INSIDE the window. That is a real channel but it is not this design's
effect. THE EFFECT IS MISSED EVIDENCE: frames a victim captures during the outage are not uploaded, and a
LATER question whose ground truth depends on that interval is answered without it, or after a backlog. A
question asked long after the window still counts if its evidence sits inside it. The corrected dose is
below and it is NON-ZERO AT BOTH SEEDS AND BOTH RUNGS, where the wrong quantity was zero at seed 5. ***

### 2.1 The evidence field, named, with every candidate that could have stood for it

**CHOSEN: `[answer_start_time, answer_end_time]`** from `results/sember/study_h/data/sember_mcq.jsonl`. Every
question carries both, in the SAME session-time coordinate as `question_time`, which
`fleet/data_sources.py:454` loads as `Question.t_ask` and the trace writes as `t_ask_session`. So the
evidence interval and the ask time are comparable with one subtraction and no rescaling: the run time of a
play's session-time zero is `t - t_ask_session`. **Chosen because it is the ruling's own quantity (the
ground-truth event time) and because it is an ANNOTATION OF THE DATA rather than a property of the harness:
it does not move if the upload contract changes.** **The join is COMPLETE: 229 of 229 robot questions have an
evidence interval.** (A pooled join rate would read 49 percent, because the 238 assistive single-shot
questions are VizWiz and EgoThink and have no S-EMBER interval by construction. The rate is reported split
by device type so that a correct complete join cannot look like a half-failed one.)

**ALSO REPORTED, because more than one field could stand for "the evidence this answer requires":**

| reading | definition | why it is reported |
|---|---|---|
| **R1** | the annotated interval overlaps the window | the ruling's quantity. **CHOSEN** |
| **R2** | a D2 CAPTURE INSTANT falls inside the overlap | the operational form: what is physically withheld is frames, not seconds. D2 runs at one frame per 2.000 s, so an overlap shorter than that can contain no frame at all. Never larger than R1 |
| **R3** | every question asked after the window start, because its prompt is the cumulative history `DS.d2_frames_in(0, t_ask)` | the MAXIMAL reading, defensible and reported as an upper bound |

**NOT USABLE, and said rather than omitted:** `question_time` / `t_ask_session` is the ASK time, which is the
quantity the first version wrongly used; `history_tokens` is HOW MUCH history the cloud holds at the ask and
cannot localise evidence in time at all.

### 2.2 *** THE FRAMES ARE BUFFERED, NOT DROPPED, AND THAT IS READ OFF THE CODE ***

**`experiments/orchestration/live2/fleet/trace.py:1037-1047`**: a victim's in-window `history_batch` has its
offer time set to the reconnect instant (`r["t"] = round(t_out1, 6)`) and **NO RECORD IS DELETED**.
**`:1048-1056`**: a `recall_question` gains `t_offer` and keeps its ask time. The committed
`UplinkQueue` (**`fleet/links.py:112-120`**) then takes `t_start = max(t_offer, free_at)`.
**So the evidence is DELAYED, not lost.** Per the ruling, the dose's upper edge is then the drain, and the
drain is COMPUTED and not assumed, by replaying that same committed arithmetic:

| quantity | value |
|---|---|
| deferred `history_batch` records per victim | **60** (120 s of D2 at one frame per 2 s) |
| bytes per victim | **1,449,630** (p50 frame 24,570 B) |
| uplink | **13.6 Mbps**, `fleet/links.py:38`, ONE QUEUE PER DEVICE (`fleet/emulator.py:310`), so victims drain in parallel |
| serialisation | **0.853 s** |
| **drain after reconnect** | **0.87 to 0.89 s** |

### 2.3 THE DOSE TABLE, measured before any cell runs

Per ADDED victim, robot questions asked at or after the window start whose evidence falls inside the window.
`instances` counts asks; `distinct` counts questions. **With `robot_reask_mean_s=30` the same question is
re-asked about every 30 s with the same `question_id` and so the same evidence interval, so one affected
question can appear as eleven affected instances. READ THE DISTINCT COLUMN.**

| pair | added victims | R1 instances | **R1 distinct questions** | R2 instances | R3 instances | R1 bounded by the drain | old wrong dose |
|---|---|---|---|---|---|---|---|
| s4, k 1 to 3 | robo003, robo009 | 5 | **1** | 0 | 31 | **0** | 2 |
| s4, k 3 to 5 | robo004, robo010 | 9 | **2** | 9 | 15 | **0** | 1 |
| s5, k 1 to 3 | robo007, robo009 | 1 | **1** | 1 | 11 | **0** | 0 |
| s5, k 3 to 5 | robo006, robo008 | 22 | **3** | 22 | 22 | **0** | 0 |

Per affected question, with its overlap and the frames inside it:

| pair | victim | evidence interval, run s | overlap with the window | D2 frames in the overlap | instances |
|---|---|---|---|---|---|
| s4 k1-3 | robo009 | 531.0 to 541.0 | **1.02 s** | **0** | 5 |
| s4 k3-5 | robo004 | 599.7 to 608.7 | 9.00 s | 4 | 6 |
| s4 k3-5 | robo004 | 590.7 to 593.7 | 3.00 s | 2 | 3 |
| s5 k1-3 | robo007 | 351.8 to 667.8 | **120.00 s, the whole window** | **60** | 1 |
| s5 k3-5 | robo008 | 573.2 to 576.2 | 3.00 s | 1 | 11 |
| s5 k3-5 | robo006 | 656.5 to 671.5 | 3.51 s | 2 | 6 |
| s5 k3-5 | robo008 | 654.2 to 687.2 | 5.77 s | 3 | 5 |

**R1 and R2 disagree at exactly one pair and for the right reason:** robo009's single affected question at
s4 overlaps the window by 1.02 s, which is shorter than the 2.000 s D2 frame period, so **no capture instant
lies inside the overlap and nothing was physically withheld for it.** That is why both readings are reported.

### 2.3b THE DOSE IN THE CONDITION THAT WILL ACTUALLY RUN (`outage_semantics=true`)

**The dose is unchanged by the semantics, because an evidence overlap does not depend on what
happens to the frames. What changes is that NOTHING BOUNDS IT.**

| pair | added victims | **R1 DISTINCT questions** | R1 instances | R2 | R3 | drain bound |
|---|---|---|---|---|---|---|
| s4, k 1 to 3 | robo003, robo009 | **1** | 5 | 0 | 31 | **NOT APPLICABLE** |
| s4, k 3 to 5 | robo004, robo010 | **2** | 9 | 9 | 15 | **NOT APPLICABLE** |
| s5, k 1 to 3 | robo007, robo009 | **1** | 1 | 1 | 11 | **NOT APPLICABLE** |
| s5, k 3 to 5 | robo006, robo008 | **3** | 22 | 22 | 22 | **NOT APPLICABLE** |

**NO DOSE IS ZERO, SO SCOPE A PROCEEDS.** The stop condition was every added-victim dose zero at
both seeds.

### 2.3c WHAT THE SWITCH ACTUALLY LOSES, PROVED ON THE ARTEFACT

`experiments/analysis/robot_idle/d273_true_outage_proofs.py`, both halves, at all six cells
(seeds 4 and 5 x k in {1, 3, 5}):

| cell | lost frames | lost tokens | 90 per frame exactly | questions whose cloud history fell |
|---|---|---|---|---|
| s4 k1 | 60 | 5,400 | yes | 4 |
| s4 k3 | 180 | 16,200 | yes | 23 |
| s4 k5 | 298 | 26,820 | yes | 38 |
| s5 k1 | 60 | 5,400 | yes | 8 |
| s5 k3 | 180 | 16,200 | yes | 14 |
| s5 k5 | 299 | 26,910 | yes | 36 |

The lost counts equal the buffered variant's deferred counts exactly, which cross-checks the two
semantics against each other.

**AND THE D2 HEADER IS NOT A FRAME.** Found by the proof rather than assumed: at this design point
some victim sessions START INSIDE the window, so the batch carrying the session's one-off 31-token
D2 header is itself lost. The cut is therefore **90 tokens per lost FRAME** and the header is
**re-attributed to the first surviving batch**, because the ruling asks for exactly the frames to go
and a header is not a frame. The affected sessions and the re-attribution are listed in the meta.

### 2.4 WHAT THIS MEANS, STATED BEFORE THE CELLS RATHER THAN AFTER

1. **PROCEED WITH SCOPE A.** The ruling stops the design only if every added-victim dose is zero at both
   seeds. No dose is zero: 1, 2, 1 and 3 distinct questions.
2. **IT IS A WEAK-DOSE CONDITION AND MUST BE LABELLED ONE WHEREVER IT IS QUOTED.** One to three distinct
   questions out of 229 robot questions, and a delta at low dose is not an effect size.
3. *** UNDER THE BUFFERED SEMANTICS THE CHANNEL WAS CLOSED BY A SUB-SECOND DRAIN, WHICH IS WHY D273 (1)
   MOVED THIS STUDY TO TRUE SEMANTICS. That finding stands as the record of the closed alternative
   (commit `722c449f`) and is NOT a finding about this condition: here the frames never arrive, so every
   affected question is affected for the rest of the run and no drain bounds anything. ***
4. **THE SURVIVING CHANNEL IS THE RECONNECT BURST, AND IT HAS REAL MAGNITUDE.** 5,400 D2 tokens per victim
   arrive at one instant (60 frames x 90 tokens), 27,000 at k = 5. Under the committed D162 first-token model
   (`results/orchestration/live2/v5/cf_ontime_model_d162.json`: 0.06780 + 0.00018243 x uncached +
   0.00015358 x queued_ahead), one victim's backlog is worth about **1.05 s** of first token, and the fifth
   victim served behind the other four about **4.37 s**, against the **3 s** robot deadline. **THAT IS A
   MODEL-BASED SCREEN AND NOT A MEASUREMENT**, quoted here only to show the channel is not negligible; the
   cells are what would measure it.
5. **The dose remains collinear with k** by construction, so any k-effect is a k-and-dose effect. Breaking
   that needs D varied at fixed k, which this ruling does not order.

## 2b. *** THE PRIMARY READOUT IS PER AFFECTED QUESTION, MATCHED. THE FLEET TOTALS ARE CONTEXT. ***

**User ruling, prompted by the dose table above and binding before the first scope A cell is scored.**

> "The doses are 1, 2, 1 and 3 distinct affected questions, BELOW THE ROBOT cbd SAME-CODE OBSERVATION OF 2,
> SO THE FLEET TOTAL CANNOT CARRY THE RESULT. Pre-register the primary readout as PER AFFECTED QUESTION,
> matched across the nested cells that share it: answered or not, correct or not, on time or not, and
> whether it was served by the CLOUD (window evidence missing) or the DEVICE (evidence complete). Fleet
> robot cbd and cloud-correct are reported BESIDE it, not used as the verdict."

**So the verdict is the per-question readout. `correct_answers_delivered_by_deadline` and
`cloud_accuracy_on_served` are reported beside it as CONTEXT and are not the verdict.** Section 3's abandon
check keeps them as its own classification, because its question is different: whether a metric separates
k at all. **The study's verdict is section 2b.**

### 2b.1 WHY THIS IS STRONGER THAN SEVEN INDEPENDENT OBSERVATIONS, said explicitly

*** BECAUSE THE VICTIM SETS NEST, AN AFFECTED QUESTION APPEARS IN A CELL WHERE ITS DEVICE IS A VICTIM AND
IN A CELL WHERE IT IS NOT, AT THE SAME WINDOW, THE SAME ARM, THE SAME SEED AND THE SAME TRACE STRUCTURE. SO
EACH QUESTION IS ITS OWN CONTROL AND THE READOUT IS A WITHIN-QUESTION, WITHIN-ARM, ACROSS-k MATCHED
COMPARISON. The between-question variance that would otherwise swamp seven observations is differenced
away, which is why seven matched questions can carry a large effect where seven unmatched ones could not.
THIS IS EXACTLY THE QUANTITY THE NESTING WAS BUILT TO CREATE, and before the keying change it did not exist
at all: the committed grid's k=3 and k=5 victim sets were disjoint with windows 157 s apart, so no question
had a control. ***

### 2b.2 THE MATCHING KEY, AND THE PROOF THAT THE MATCH IS COMPLETE

**KEY: `(question_id, device_id)` against victim membership against k.** Victim membership is never
re-derived: it is read from the cell's own recorded `outage.victim_permutation`, and the device's index in
it plus one is the k at which it first becomes a victim. **Because victims are the permutation PREFIX, that
one number fixes every cell's role for that question:**

| | |
|---|---|
| `k < first_victim_k` | **CONTROL** cell: the device is not a victim, its evidence is COMPLETE |
| `k >= first_victim_k` | **TREATED** cell: the device is a victim, the window's frames are MISSING |

**THE MATCH IS PROVED COMPLETE BEFORE ANY OUTCOME IS READ**, by
`experiments/analysis/robot_idle/d273_per_question_readout.py`, which refuses rather than scoring a partial
match. It checks: every matched question present in every cell of its ladder; one permutation and one window
across the ladder; one semantics; equal per-question row counts; every cell `run_valid`; and the victim
membership each cell records agreeing with the census. **A cell whose `header.json` carries no `outage`
block is REFUSED by name rather than crashed on** (the committed D244 cells are that case, since the header
gained the block only with D266 item 2, and they are not part of this design).

### 2b.3 THE FOUR FIELDS, EXACTLY AS RULED, AND WHERE EACH COMES FROM

Each from the cell's own committed per-question row, `cell.json` at `/score/score/robot_rows`, written by
`scorer/score.py:890-902`. **Nothing is recomputed, so the readout cannot disagree with the scored cell.**

| field | source | expressibility, per invalidation condition 13 |
|---|---|---|
| **answered** | `source_by_deadline != "none"` | **EXPRESSIBLE**: needs only an arm reacting to a smaller cloud history |
| **correct** | `standing_correct_by_deadline` | **EXPRESSIBLE** |
| **on time** | `source_by_deadline != "none"`, which is delivery within the deadline by construction (D155 (3)); `device_on_time` reported beside it | **EXPRESSIBLE** |
| **served by CLOUD or DEVICE** | `source_by_deadline` | **EXPRESSIBLE**, and it is the one that carries the mechanism |

*** THE FOURTH FIELD CARRIES THE MECHANISM. Under this ruling the DEVICE history is COMPLETE and the
cloud's is SHORT, so a question served by the device is answered from full evidence and one served by the
cloud is not. And routing to the device is FULLY EXPRESSIBLE: `RECALL_ACTIONS` includes `DEVICE`
(`baselines/interface.py:47`) and the coordinator honours it at `live2/coordinator.py:998-1009`. So the
cloud-against-device split is the reading most likely to show anything at all. ***
**NONE of the four readings requires an arm to RECOGNISE the outage, which is unexpressible (condition 13):
every one of them needs only an arm reacting to a smaller cloud history, which it does see through
`readiness_tokens` (`cstate.py:669-683`, fed from `cum_tokens` at `fleet/emulator.py:233-240`).** **Any
reading that would require recognition is out of scope before the run, not after it.**

### 2b.4 THE CENSUS, COMPUTED. SEVEN MATCHED QUESTIONS, AND NONE IS SHARED

`experiments/analysis/robot_idle/d273_matched_power.py`. **Scope A as designed, seeds 4 and 5, ladder
{1, 3, 5}: 10 affected questions, of which 7 ARE MATCHED and 3 are not.** The 7 reproduce the ruling's
1 + 2 + 1 + 3 exactly, by an independent route (first-victim-k off the permutation rather than per-pair
added victims).

| seed | device | question | first victim at k | CONTROL cells | TREATED cells | ask instances | evidence overlap |
|---|---|---|---|---|---|---|---|
| 4 | robo009 | `71b5dc7d` | 3 | k1 | k3, k5 | 5 | 1.02 s |
| 4 | robo004 | `faedddfd` | 5 | k1, k3 | k5 | 6 | 9.00 s |
| 4 | robo004 | `eaf0abfe` | 5 | k1, k3 | k5 | 3 | 3.00 s |
| 5 | robo007 | `441041f7` | 3 | k1 | k3, k5 | 1 | **120.00 s, the whole window** |
| 5 | robo008 | `b0f9b6a0` | 4 | k1, k3 | k5 | 11 | 3.00 s |
| 5 | robo008 | `b07b787c` | 4 | k1, k3 | k5 | 5 | 5.77 s |
| 5 | robo006 | `b513bc6c` | 5 | k1, k3 | k5 | 6 | 3.51 s |

**NO QUESTION IS SHARED between pairs or between seeds**, so the 7 are 7 and not fewer. A question affected
at two rungs is ONE question with one control set and one or two treated cells, and is counted once.
**THREE AFFECTED QUESTIONS ARE UNMATCHED** because their device is a victim at the lowest rung in the
ladder, so that seed has no control cell for them: they are reported as a census and never as a comparison.
**THE k = 1 RUNG IS LOAD-BEARING, NOT A DECORATION: it is the only control cell for the two questions whose
device becomes a victim at k = 3.**

### 2b.5 THE MINIMUM DETECTABLE EFFECT, AS A COUNT OF DISCORDANT PAIRS

The test is the exact sign test on discordant pairs, which is McNemar's exact form, and each matched
question contributes AT MOST ONE discordant pair per comparison.

| | |
|---|---|
| matched questions | **7** |
| discordant pairs needed, one-sided 0.05 | **5** (`0.5^5 = 0.031`) |
| discordant pairs needed, two-sided 0.05 | **6** (`2 x 0.5^6 = 0.031`) |
| p if ALL SEVEN flip one way | **0.0078** |

*** SAID PLAINLY: WITH SEVEN MATCHED QUESTIONS, NOTHING SMALLER THAN FIVE OF THE SEVEN CHANGING OUTCOME
ALL IN THE SAME DIRECTION CAN EVER REACH ONE-SIDED p <= 0.05, AND SIX OF SEVEN FOR TWO-SIDED. That is 71
and 86 percent of the affected questions. ANY DISCORDANT COUNT BELOW THAT IS A CENSUS AND MUST BE REPORTED
AS ONE, never as a difference between arms. ***
**AND THE EFFECTIVE n MAY BE BELOW SEVEN.** A question whose outcome cannot move in either cell, because it
was never answered in either, contributes no discordant pair. The readout reports
`n_matched_questions_readable` per field, and that number, not 7, is the denominator. **The first two cells
of scope A reveal it, and it is to be read before any comparison.**

### 2b.6 THE INVERSION: WHAT WOULD BE NEEDED, ON BOTH AXES, PRICED

**The yields are MEASURED, not extrapolated.** Matched questions per seed on the {1, 3, 5} ladder:
**s4 = 3, s5 = 4, s6 = 2, s7 = 0**, mean **2.25**. *** THE YIELD IS HIGHLY VARIABLE AND A SEED CAN
CONTRIBUTE NOTHING: seed 7 yields ZERO matched questions. So any seed count below is a mean and not a
guarantee, and the seed axis must be bought in blocks with the yield checked as it goes. ***

Marginal matched questions by rung, measured per seed:

| seed | k1 | k3 | k5 | k7 | k9 | k11 |
|---|---|---|---|---|---|---|
| 4 | 1 | 1 | 2 | **0** | **0** | 2 |
| 5 | 2 | 1 | 1 | **0** | 1 | 0 |
| 6 | 0 | 0 | 0 | 1 | 0 | 2 |
| 7 | 1 | 0 | 0 | 1 | 0 | 1 |

*** THE NEWLY EXPRESSIBLE k = 7 AND k = 9 RUNGS ARE NEARLY EMPTY AT THE TWO RULED SEEDS: they add 0 and 0
at seed 4 and 0 and 1 at seed 5. Buying them at seeds 4 and 5 would buy almost no matched questions. ***

**At 80 percent power, 1,295 s per cell, 2 arms, ladder of 3 rungs:**

| effect per question | matched questions needed | SEED AXIS: seeds | cells | hours | RUNG AXIS at s4+s5: top rung | cells | hours |
|---|---|---|---|---|---|---|---|
| 0.8 | 7 | 4 | 24 | **8.63** | **k = 5** | 12 | **4.32** |
| 0.6 | 10 | 5 | 30 | **10.79** | **k = 11** | 24 | **8.63** |
| 0.5 | 12 | 6 | 36 | 12.95 | **unreachable** | | |
| 0.4 | 16 | 8 | 48 | 17.27 | **unreachable** | | |
| 0.3 | 21 | 10 | 60 | 21.58 | **unreachable** | | |
| 0.2 | 33 | 15 | 90 | **32.38** | **unreachable** | | |

Scope B at 5 arms is 2.5 times the cell count and the hours.

**THE ANSWER TO THE RULING'S QUESTION, PLAINLY. The design is NOT closed by this: a feasible number does
reach a useful effect. But the price is specific and it should be bought knowingly.**
1. **The design as ruled (7 matched questions) can only ever read an effect of 71 percent or larger per
   affected question.** It is the right first spend because it is already paid for, and a large effect is
   exactly what a lost-evidence condition might produce; but it cannot read a moderate one.
2. **THE RUNG AXIS ALONE CANNOT GO BELOW 0.6, EVER.** At the two ruled seeds the whole ladder to k = 11,
   the ceiling at this mix, yields 10 matched questions. k = 7 and k = 9 are nearly empty there. So adding
   victims is the cheaper axis (8.63 h to reach 0.6) and it dead-ends.
3. **Only the SEED axis reaches a moderate effect, and 15 seeds / 90 cells / 32.4 hours at 2 arms is what
   a 0.2 per-question effect costs.** Seeds 1 to 3 are excluded, so that is seeds 4 to 18, and the measured
   yield variance (0 to 4 per seed) means the count is a mean.
4. **If the first two cells show the effective n below seven**, because the affected questions' outcomes
   cannot move, then the readout cannot separate arms at any price on this axis and that IS the finding, in
   the same register as the host-awareness line: an effect that the harness cannot express is reported as
   unexpressible, not as absent.

## 3. THE ABANDON CHECK. ITS CRITERIA ARE FIXED HERE AND ARE NOT NEGOTIABLE AFTERWARDS

**Why it exists:** the committed 40:40:20 grid gives `robot_pool_on_time` = **121/132 at BOTH k=3 and k=5**, with
disjoint victim sets and windows 157 s apart. Re-read independently here: rung 3 121/132 at k=3 and 121/132 at k=5,
`-stateoff` 66/132, `llf` 4/132. The runs differ genuinely, so the headline robot metric is not separating the doses.
Under nesting the two cells differ by exactly two robots at one identical window, which is a SMALLER difference.

**Not in the estimate and found here: the OTHER robot metric does separate those committed cells.**
`correct_answers_delivered_by_deadline` reads **0.621212 at k=3 and 0.666667 at k=5** (n=132 both), so
correct-by-deadline is not flat where cloud on-time is. The abandon check therefore classifies **every** recorded
robot metric, per D251, and not only the ruling's primary one.

*** AND THE THREE CHANNELS BEAR ON DIFFERENT METRICS, WHICH IS WHY ONE FLOOR CANNOT SERVE FOR ALL OF THEM.
A question forced device-only is invisible to a cloud-on-time count, so the device-only count is the
arithmetic floor FOR THAT METRIC and for no other. A question answered without the evidence its ground truth
needs is a CORRECTNESS effect, so the missed-evidence dose is the dose for `correct_by_deadline`. The
reconnect burst is a LATENCY effect and shows up in both. A check that applied the device-only floor to
every metric would mislabel two of the three. ***

| channel | dose at the ruled design point | the metric it bears on |
|---|---|---|
| forced device-only questions | 2, 1, 0, 0 instances | `robot_pool_on_time` only, and that metric DECIDES NOTHING under D273 (1) |
| **missed evidence (THE DECIDING DOSE)** | **1, 1, 2, 3 distinct questions** (5, 1, 9, 22 instances) | **`correct_answers_delivered_by_deadline` AND `cloud_accuracy_on_served`** |
| reconnect burst | does NOT apply under true semantics: there is no burst, the frames are gone | none |

*** AND SECTION 2b IS THE STUDY'S VERDICT, NOT THIS SECTION. The abandon check answers a different
question - whether a FLEET metric separates k at all - and the user ruling has taken the verdict off the
fleet totals entirely. What follows decides whether scope B is worth running; it does not decide the study.
***

*** D273 (1): THE ABANDON CHECK IS SCORED ON ROBOT `correct_answers_delivered_by_deadline` AND
`cloud_accuracy_on_served`, NEVER ON `robot_pool_on_time`, which read 121/132 at BOTH k in the
committed cells. `robot_pool_on_time` is still reported, marked `DECIDES_NOTHING`, so the record
shows what it did without anything being read off it. `cloud_accuracy_on_served` (with its own
`cloud_answers_available` denominator, `scorer/score.py:931-933`) is the sharpest of the two here:
it is the accuracy of the CLOUD's own answers on the questions it served, so a cloud answering with
frames missing shows in it with no intact device half to dilute it. ITS DENOMINATOR IS ARM-DEPENDENT
AND MUST BE QUOTED BESIDE IT. ***

**Script:** `experiments/analysis/robot_idle/d262_abandon_check.py`, run on the FIRST TWO CELLS of scope A,
with `experiments/analysis/robot_idle/d262_dose_readings.py` for the dose under every reading.

- `--predict` needs no cells. It computes the forced-miss floor and the backlog delta from the traces alone. The
  floor is a **CONSTRUCTED BOUND, not an observed count** (it assumes every added device-only question was on time at
  the smaller k), and is marked as such in its own output.
- `--score` reads the two cells and classifies each metric:

| class | condition | what happens next |
|---|---|---|
| **PASS-WITH-A-POLICY-CHANNEL** | the metric moves, by MORE than the floor | proceed with the remaining six scope-A cells |
| **PASS-BY-CONSTRUCTION-ONLY** | the metric moves, by at most the floor | proceed, but the separation IS the forced-miss arithmetic and may NOT be read as a policy effect. Say so in the report. |
| **ABANDON** | delta is 0 while the floor is strictly positive | **STOP BEFORE SCOPE B AND REPORT.** The metric is blind to a dose it is arithmetically required to see. |
| **ABANDON-ON-THE-BACKLOG-CHANNEL** | delta is 0, floor is 0, backlog delta is non-zero | a null on the backlog channel AT THAT CELL. Weaker than ABANDON, stronger than UNEXERCISED. Do not generalise it to a direction. **This is the expected class at seed 5.** |
| **UNEXERCISED** | delta is 0 and both channels are 0 | nothing was tested |
| **INCOHERENT** | the count ROSE with more victims, or the denominators differ, or the artefact does not show nesting at one window | **STOP.** Nothing is read off the cells. |

**The whole-check rule:** if every recorded robot attainment metric is ABANDON or ABANDON-ON-THE-BACKLOG-CHANNEL,
**scope B is not run**, the k-effect is UNSCORABLE on those metrics, and the design rests entirely on the
history-cached observable.

**The control is read before the comparison (CLAUDE.md check 7).** Denominators come from each cell's OWN sweep row
and are never carried between seeds; the two cells' denominators must be equal, because under nesting they share one
trace structure (confirmed on the traces: 229 robot questions at both k, at both seeds); the arms and seeds must
match; both cells must be `run_valid`; and the nesting and window equality are read from the ARTEFACT, never assumed
from the tag. A no-outage reference for the same arm, seed and mix is compared when one is given, because outage
cells that do not sit below it mean the outage did not bite and neither cell is a treatment.

---

## 4. THE FALLBACK OBSERVABLE, AND IT IS NOW BUILT

`experiments/analysis/robot_idle/d262_outage_history_cached.py`. **The committed record orders this quantity and
nothing computed it**: `git grep -l cached_fraction` over `experiments/` has no outage consumer at `2ddb69f3`.

**Definition, committed and not new:** `cache_path` is WARM iff `cached_tokens > 0`, with
`cached_fraction = cached_tokens / prompt_tokens` (`live2/CONTRACT.md:129`, D81), both from the engine's own
per-request usage report and never from the coordinator's belief. The ask time is the `recall_question` record's `t`
in `trace.jsonl`, which the outage does NOT move; only `t_offer` moves.

**PREFIX CACHING IS RESTATED, NOT ASSUMED, BECAUSE THE WHOLE OBSERVABLE IS ZERO WITHOUT IT.** In the committed grid
the flag is passed **TWICE** in the server argv, `--no-enable-prefix-caching` at index 13 and
`--enable-prefix-caching` at index 27, and only argparse's last-wins makes it ON. That is the same duplicated-flag
shape that gave a wrong host size under D250. Two independent readings are required in every cell and the script
reads both: `header.json` `server.resolved.flags_set_twice["--enable-prefix-caching"].argv_last_wins` and
`server.resolved.engine_reported.enable_prefix_caching`, which reads `"True"` in the committed cells. **If no request
row in a cell reports `cached_tokens > 0`, that cell is declared UNSCORABLE on this observable and its zeros are not
reported as a finding.**

**Three controls, none optional:** a non-victim CONCURRENT control (same quantity, same instant, robots that were not
victims); a within-robot BEFORE control (the same victim's last pre-outage question); and the prefix-caching proof
above.

**Measured now on the committed 40:40:20 cells, so the observable is known to be live and arm-discriminating before
any new cell runs** (victims cached at the first post-reconnect question / readable n; non-victims; pre-outage):

| committed cell | victims | non-victims | pre-outage control | device-only |
|---|---|---|---|---|
| `covex-v6-fair-final` k3 s4 | **3/3** | 3/6 | 3/3 | 4 |
| `covex-v6-fair-final` k5 s4 | **5/5** | 2/5 | 5/5 | 6 |
| `covex-v6-fair-final` k3 s5 | **2/2** | 3/6 | 3/3 | 5 |
| `covex-v6-fair-final-stateoff` k3 s4 | **2/3** | 2/6 | **0/3** | 4 |
| `llf` k3 s4 | **0 readable** | 3/3 | 0/3 | 4 |

The device-only count of 4 at k=3 s4 reproduces AMENDMENT 2's committed figure exactly, which is this build's
cross-check that the window and victims it reconstructs are the ones the cells ran.

**TWO LIMITS ON THIS OBSERVABLE, REGISTERED BEFORE IT IS USED FOR ANYTHING.**

1. **THE DENOMINATOR IS k AND IT CAN BE ZERO.** The ruling's object is the FIRST post-reconnect question, but a robot
   question has a request row only if the arm sent it, so that object is UNREADABLE for any robot whose first
   post-reconnect question was never sent. On `llf` at k=3 it is unreadable for **all three** victims, which makes the
   observable an **ABSENT LINK for that arm**, not a null. The script reports both the ruling's object and the first
   post-reconnect question that does have a row, and the second is conditioned on the arm's own behaviour and is
   therefore not a fair cross-arm denominator. Neither may carry a cross-arm headline without its n beside it.
2. **PROXY VALIDITY IS OPEN (CLAUDE.md check 6).** WARM at the first post-reconnect question can be produced by
   (a) the offline history surviving in cache, which is the claimed mechanism, or by (b) the reconnect burst having
   just prefilled that prefix, which would make WARM a consequence of the outage rather than of the policy. The
   committed numbers are consistent with both: rung 3's victims are MORE cached than its own non-victims (3/3 against
   3/6). **What distinguishes them**: under (a) the victim's pre-outage question is also WARM and the fraction is
   continuous across the window, which is what rung 3 shows (3/3 before, 3/3 after); under (b) the pre-outage question
   is cold and only the post-reconnect one is warm. `-stateoff` shows 0/3 before and 2/3 after, which is the (b)
   signature. **Until this is settled on the new cells, the observable is reported with the before-control beside
   every after-number, and no headline is taken from the after-number alone.**

---

## 5. THE FIVE INVALIDATION RISKS THE ESTIMATE NAMED

| # | risk | status |
|---|---|---|
| 1 | the metric may not separate k | **ADDRESSED IN CODE**: the abandon check above, with its criteria fixed here, runnable on the first two cells. Its `--predict` half already ran and found the forced-miss floor is 2, 1, 0, 0. |
| 2 | **the trace-dir cache serves the old placement while every gate passes** | **FIXED IN CODE**: the placement rule is now part of the trace-directory token (`..._outk3d120pcentre`). The default rule adds nothing, so every committed trace name stays addressable. Asserted in `d262_nested_switch_proofs.py` proof (D), not assumed. |
| 3 | the driver validates a DIFFERENT cell's meta | **FIXED IN CODE**: the glob and `ls -t ... | head -1` are gone. The harness now writes the RESOLVED `trace_dir` into its own `header.json` and the driver reads that exact path, then asserts k, D, the placement, AND `robots == sorted(victim_permutation[:k])` on the artefact. |
| 4 | the comparator may move (`_preD249`) | **SETTLED BY THE USER, not by code: the outage cells run AFTER the D265 push with `-q` OFF, and the byte-identical proof is what makes rung 3 comparable to P3 and the `_preD249` references.** `-q` gets its own outage cells only if it passes its gate. |
| 5 | no E-id | **SETTLED: `StudyD266-NESTOUT`.** The user is writing the row. Verified independently at `origin/main` before it was assigned that no existing row covered this study: the only outage rows are `StudyOUTAGE-SURVEY` (read-only, E-id proposed not confirmed) and `StudyOUTAGE-HEADROOM` (model-based, no cells, DO NOT PLOT). |
| + | prefix caching via a duplicated last-wins flag | **RESTATED IN FULL IN SECTION 4**, with both readings named and the refusal that fires if they disagree. |

---

## 6. OFF BY DEFAULT, AND PROVED SO

**The claim:** with the outage off, every arm's decisions are unchanged.

**The instrument:** `hybrid/test_hybrid.dry` with `realtime=False` through
`live2/d223_dry_digest_identity.py`, the project's own deterministic CPU instrument for exactly this claim, with the
committed strip set `("arm", "decision_latency_ms", "decision_id")`, every module taken from the tree under test, and
the instrument's OWN determinism measured on one arm in BOTH trees before any comparison is read. It is non-vacuous
for this patch: `dry()` calls `TR.generate_trace` at `test_hybrid.py:59`, so the patched generator is the generator
under test. **A realtime cell cannot carry this claim** and the reason is committed: running one tree twice through
`run_live2_real.py` moved 169 rows on `t` and real decision fields on dozens more, because that path races a wall
clock. The per-cell numbers in this study are accelerator measurements; the IDENTITY is a CPU claim and is made on a
CPU instrument.

**What is NOT reached by it**, said here rather than discovered later: the `procsplit.py` hand-off, which only a
split-mode run builds, and the realtime emulator's own timing. Both are outside the patch.

**Scope of the claim:** per arm, per mix. 40:40:20 is the committed workload and the committed claim; 3:11:2 is the
mix these cells run, and a mix the proof never ran is a mix the proof says nothing about, so `--ratio` was added and
the proof is run on both.

*** AND ONE ARM'S ROW IS A VACUOUS PASS, WHICH IS SAID HERE RATHER THAN LEFT TO BE NOTICED.
`covex-v6-fair-final` and `covex-v6-fair-final-stateoff` return the IDENTICAL stripped decision digest on this
instrument at both mixes, because the dry path emits ZERO `state_action` rows for either arm (measured: both arms
give release_piece 37, release_monitor 2308, release_recall 115, release_infeasible 345, defer 4, decline 5 and
nothing else at 40:40:20, 300 s). So `-stateoff`'s own characteristic decision never fires here. Its identity row is
a valid check of the SHARED path and is NOT evidence about its own mechanism, which is exactly the port-side
distinction CLAUDE.md draws: the required proof establishes that an arm is legal and fairly treated, never that it
does anything. ***

---

## 7. WHAT WOULD INVALIDATE A RUN OF THIS GRID, DECLARED IN ADVANCE

Carried forward from the standing prereg and AMENDMENT 2, unchanged and binding, plus what this design adds.

1. **A zero characteristic-decision count in any cell**: that cell is an ABSENT LINK and is not a negative.
2. **No frames withheld during the window, no burst at reconnect, or no device-only questions**: the outage did not
   fire and the cell is void.
3. **An outage cell pooled with a no-outage cell**: the tag exists to prevent it and any pooled figure is withdrawn
   rather than corrected.
4. **A `_c3-11-2` outage cell pooled with or differenced against the existing 40:40:20 outage grid**: refused. The
   pooled robot denominator moves from 132 to 229 and the dashcam fleet total halves. Dashcam PER DEVICE is
   effectively unchanged (1,956.3 against 1,960.7, 0.2 percent apart) and may be compared per device, never as a
   fleet total.
5. **A cell whose `trace_meta.json` does not show `robots == sorted(victim_permutation[:k])` at the recorded
   placement**: VOID. Nesting is the one property the keying change exists to provide.
6. **Both robot metrics moving identically across all arms**: the failure Conflict 1 predicts. The run has then
   measured the outage and not the policy.
7. **Denominators carried between seeds**: any figure built that way is withdrawn. Robot 229 at this mix must be read
   from each cell's own row.
8. **Episodes pooled across seeds**: refused; episode structure is invariant within a seed and not across seeds.
9. **No 0.25x. Never seeds 1 to 3. Disk refusal below 15 GB. Outage work at 1x only, never stacked with reduced
   memory (D240).**
10. **A missed-evidence figure quoted as INSTANCES rather than distinct questions**: withdrawn. The re-ask
    mechanism multiplies one affected question by up to eleven, and an instance count reads as an effect size
    while being a re-ask count.
11. **A missed-evidence effect claimed under BUFFERED semantics without the drain beside it**: withdrawn.
    That is the closed alternative, where the drain is 0.87 to 0.89 s and the bounded dose is zero.
12. **A `_lost` cell whose `trace_meta` shows no frames lost, or lost tokens that are not 90 per frame**:
    VOID. The driver refuses it before the cell is scored. A true-outage cell that lost nothing is an
    ABSENT LINK wearing a lost-frames name.
13b. **A fleet total quoted as the verdict**: withdrawn. The verdict is the per-question matched readout
    (section 2b); robot cbd and cloud-correct are context. The dose is 1 to 3 distinct questions per pair,
    below the robot-cbd same-code observation of 2.
13c. **A per-question comparison read before the match-completeness proof passes**: refused by the tool,
    and any figure produced another way is withdrawn.
13d. **A discordant count below 5 of 7 reported as a difference between arms**: withdrawn. Below that
    threshold the readout is a CENSUS and is reported as one.
13e. **The denominator taken as 7 when the readable n is lower**: withdrawn. A question whose outcome
    cannot move contributes no discordant pair, and `n_matched_questions_readable` is the denominator.
13. **A result that depends on an ARM RECOGNISING the outage**: UNEXPRESSIBLE, and known so before the run.
    `research/study_d273_policy_visibility.md` shows that nothing in `Observation` says frames were lost,
    that the one declared epoch for it (`connectivity_change`) is never emitted on the run path, and that
    `NetworkState.connected` is hard-coded `True` at `cstate.py:662`. What IS expressible is an arm reacting
    to a SMALLER cloud history, which it does see through `readiness_tokens` (`cstate.py:669-683`, fed from
    `cum_tokens` at `fleet/emulator.py:233-240`), and routing to the device, which is in the action space
    (`interface.py:47`) and honoured at `coordinator.py:998-1009`. Any NESTOUT claim must say which of the
    two it rests on.

---

## 8. THE ARTEFACTS THIS DESIGN WRITES

| file | what |
|---|---|
| `experiments/orchestration/live2/fleet/trace.py` | the `outage_placement` rule, window first, k-independent permutation prefix, `victim_permutation` in the meta |
| `experiments/orchestration/live2/run_live2_real.py` | `--outage-placement`, the placement rule in the trace-dir token, `trace_dir` and `outage` in `header.json` |
| `experiments/orchestration/live2/hybrid/test_hybrid.py` | the outage switches forwarded through `dry()`, so Step 2b is a CPU proof |
| `experiments/orchestration/live2/d223_dry_digest_identity.py` | `--ratio`, so the identity claim can be made per mix |
| `experiments/orchestration/live2/d262_nested_switch_proofs.py` | nesting, window invariance, the band-rule positive control, Step 2b, and the switch's arrival with its declared type and value |
| `experiments/analysis/robot_idle/d262_outage_history_cached.py` | the history-cached observable, with its three controls |
| `experiments/analysis/robot_idle/d262_abandon_check.py` | the abandon check, `--predict` and `--score`, with the missed-evidence dose and the computed drain |
| `experiments/analysis/robot_idle/d262_dose_readings.py` | the added-victim dose under all three evidence readings, per question, with the drain bound and a `--semantics` flag |
| `experiments/analysis/robot_idle/d273_true_outage_proofs.py` | both halves of the true-outage proof, against the NO-OUTAGE baseline, with an off-against-off negative control |
| `research/study_d273_policy_visibility.md` | what the policy can and cannot see after a reconnect, read-only, no policy code changed |
| `experiments/analysis/robot_idle/d273_matched_power.py` | the per-question matched census, the minimum detectable effect as a count of discordant pairs, and the priced inversion on the seed and rung axes |
| `experiments/analysis/robot_idle/d273_per_question_readout.py` | **THE PRIMARY READOUT**: the four fields per affected question, matched across cells, with the match-completeness proof that refuses rather than scoring a partial match |
| `experiments/orchestration/study_frozen_grid_driver_v42.sh` | the `_nest` tag token, its refusals, and the tightened trace validation |

**Every result file this study writes goes under `results/orchestration/live2/robot_idle/` or the frozen-test run
tree, with a `_provenance` stamp, and is indexed in `results/INDEX.md` with its E-id row in
`research/EXPERIMENTS.md`.**

## AMENDMENT 2026-11-26T00:05Z, BEFORE ANY SCOPE A CELL: scope A INCLUDES THE k=1 RUNG (user ruling).
Scope A is now 2 arms x k{1,3,5} x s{4,5} = **12 cells**, not 8 (about 4.3 h at 1,295 s). Reason: the census needs the k=1 control cell for 2 of the 7 matched questions, so without it only 5 are matched and a 5-of-5 flip would be required. The scope is HELD pending the link-state and sync build, and the semantics will be superseded by it; this amendment fixes the cell set for whichever semantics runs. The two arms are not named in the original text and are still to be fixed by the user.
