# D266 ITEM 2: PRE-REGISTRATION OF THE NESTED-VICTIM FIXED-WINDOW OUTAGE

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

### 2.4 WHAT THIS MEANS, STATED BEFORE THE CELLS RATHER THAN AFTER

1. **PROCEED WITH SCOPE A.** The ruling stops the design only if every added-victim dose is zero at both
   seeds. No dose is zero: 1, 2, 1 and 3 distinct questions.
2. **IT IS A WEAK-DOSE CONDITION AND MUST BE LABELLED ONE WHEREVER IT IS QUOTED.** One to three distinct
   questions out of 229 robot questions, and a delta at low dose is not an effect size.
3. *** THE MISSED-EVIDENCE CHANNEL IS BOUNDED BY A SUB-SECOND DELAY, SO ON THE RULING'S OWN BUFFERED RULE
   ITS DOSE IS ZERO AT EVERY PAIR. The drain is 0.87 to 0.89 s and not one affected question is asked inside
   that interval. In this harness, at D = 120 s and this mix, no question is answered without evidence it
   would otherwise have had: the evidence arrives under a second after reconnect. Any residual effect must
   come from the CLOUD-SIDE handling of the burst, not from evidence being absent. ***
4. **THE SURVIVING CHANNEL IS THE RECONNECT BURST, AND IT HAS REAL MAGNITUDE.** 5,400 D2 tokens per victim
   arrive at one instant (60 frames x 90 tokens), 27,000 at k = 5. Under the committed D162 first-token model
   (`results/orchestration/live2/v5/cf_ontime_model_d162.json`: 0.06780 + 0.00018243 x uncached +
   0.00015358 x queued_ahead), one victim's backlog is worth about **1.05 s** of first token, and the fifth
   victim served behind the other four about **4.37 s**, against the **3 s** robot deadline. **THAT IS A
   MODEL-BASED SCREEN AND NOT A MEASUREMENT**, quoted here only to show the channel is not negligible; the
   cells are what would measure it.
5. **The dose remains collinear with k** by construction, so any k-effect is a k-and-dose effect. Breaking
   that needs D varied at fixed k, which this ruling does not order.

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
| forced device-only questions | 2, 1, 0, 0 instances | `robot_pool_on_time`: this is its arithmetic floor |
| **missed evidence** | **1, 2, 1, 3 distinct questions** (5, 9, 1, 22 instances) | `correct_by_deadline` |
| reconnect burst | about +10,700 D2 tokens per rung at both seeds | both, through first-token latency |

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
11. **A missed-evidence effect claimed without the drain beside it**: withdrawn. The harness buffers, the
    drain is 0.87 to 0.89 s, and the drain-bounded dose is zero at every pair, so a correctness effect
    attributed to absent evidence must first explain how the evidence was absent when the question was asked.

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
| `experiments/analysis/robot_idle/d262_dose_readings.py` | the added-victim dose under all three evidence readings, per question, with the drain bound |
| `experiments/orchestration/study_frozen_grid_driver_v42.sh` | the `_nest` tag token, its refusals, and the tightened trace validation |

**Every result file this study writes goes under `results/orchestration/live2/robot_idle/` or the frozen-test run
tree, with a `_provenance` stamp, and is indexed in `results/INDEX.md` with its E-id row in
`research/EXPERIMENTS.md`.**
