# StudyD218-DA: spec v6 section 7's third request candidate, DEVICE_ANSWERS, built and proved dry

Session: flash, 2026-11-23/24. Ruled by D218 (1). Measured on a private `git archive` of
`origin/main` at `6f20f7e7fc8e048ab073559991862d90706c4f28`, never the shared worktree, where
`arms.py`, `coordinator.py` and `v5/cf_objective.py` all differ from origin; each of those three was
`cmp`-checked against its origin blob inside the archived tree before any cell ran.

**Origin moved under this study and the base was re-resolved rather than assumed.** During the
sweep `origin/main` advanced 20 commits to `4b177410b0ef3b50fbfbf5e52dcbf3fc47af0ed5`, and
`arms_v6cf.py` - one of the two files this change edits - **moved with it**. The delta is a seven-line
docstring correction inside `_pd_free_kv` (a peer's commit replacing a wrong claim about
`vllm:gpu_cache_usage_perc` being read off the live server). `cf_protect_defer.py` did not move. My
edits were re-applied to the **new** origin version, so the peer's correction is preserved rather
than reverted, and the byte-identity proof's origin side was re-pointed at `4b177410` and re-run on
four cells to confirm the rebase moved no decision (section 4). Had the commit been built from the
first base, it would have silently reverted that docstring.

---

## 0. Register, stated before any number

| what | register |
|---|---|
| every decision count and digest here | **DRY and LOGICAL.** `--kv-scale` scales `test_live2_coord.GPU_KV`, the coordinator's own logical pool. No engine, no `--num-gpu-blocks-override`, no real KV allocator, no H100. |
| the per-denial trade numbers | **PREDICTED at decision time**, from the committed D162 queued-ahead price and the committed on-time curve. Not observed outcomes: a dry cell has no engine, so no denial's realised outcome exists to be measured. |
| byte identity | **OBSERVED**, as two cells of the same arm at the same recipe on the same box, differing in exactly the two edited files. |
| the alert component of every saved count | **PROXY.** Sized from `share_capacity.FACTORS['alert']['median_uncached']` = 374 tokens, a population median over 39,949 EP-G requests. Valid for sizing a pending alert instant's service time; NOT valid for any claim about one named instant, and it understates a long episode's harm. |
| the free-KV input to the gate | **BELIEF-SIDE.** `obs.cloud.gpu_kv_fraction` is 0.0 in every dry cell, so the engine metric bound 0 decisions and the residency belief bound all of them. The correct wording stays "reacts to a smaller configured pool", never "reacts to memory pressure". |
| aloneness | **MIXED, and stated per cell.** The first pass ran entirely beside the E1 session's 52-cell sweep (NOT ALONE). The reproduction pass caught a quiet window and **five cells ran ALONE end to end, including the 0.25x pass-condition cell and both Step 4 controls**. Both loadavg magnitudes and the foreign-process census travel with every digest. |

**Pre-registration, frozen before any cell ran.**

```
PREREG_SHA256    e08117903db9caf64b4fca6b0b195836c65625cf518831cadb3fbe28049ed1ef   d218_prereg.json
ADDENDUM_SHA256  9baf5db26951ddfaeb16a299afe12d5260bd218982ac7927183fb653d61b16a9   d218_prereg_addendum.json
```

The addendum is a second hashed document rather than an edit, because the first was already frozen
when the per-denial trade requirement and the live-pair instruction arrived. Neither changes the
rule, the units, the bar or the proofs.

---

## 1. What was built, and why it is not a new candidate

`policy_spec_v6.md` section 7's request row lists **three** candidates: "admit now with full
history; defer to the latest safe start ...; leave to the device". The third was specified and never
built in the compound. `v5/cf_planner.py:167` already names it `DEVICE_ANSWERS` in
`REQUEST_CANDIDATES` and scores it at `:549`.

StudyD216-KV025 section 3.5 measured the gap: `pd_request_crossed_bar_unexpressible` = **2 at 1x and
27 at 0.25x**, and all 27 arrive at one gate, `pd_gate_wanted_to_act_but_a_request_has_no_slice_channel`.
The mechanism reached "harm crosses the bar", had no channel, fell back to the base and admitted the
harmful cold rebuild. The latest safe start was already now, so it could not defer; a recall query is
one prompt, so it could not be sliced.

**The rule, fixed before any cell.**

```
deviate to the device  iff  harm_others - w_d * p_self  >  w_d * MARGIN_CF
```

Units are D191 (2): gain and harm are both **counts of expected on-time cloud answers**, each device
weighted by its per-device `w_d` (D185), with **no** division by the number served. `MARGIN_CF` is
0.6582 in on-time units (D177 (3)), derived in `cf_protect_defer` as `cf_margin.MARGIN_CF / A_D2_DEV`
and never retyped; the run read it as 0.65824.

**The sign, and why it is derived rather than asserted.** Replacement semantics (D165 (B), D177 (1)):
a cloud answer delivered by the deadline replaces the device's, so leaving the question to the device
**forfeits this question's own expected on-time cloud answer**. That forfeit is a cost of the
deviation and is therefore subtracted. The committed planner gives the same inequality independently:
it scores candidates as `value = gain - harm`, so `ADMIT_NOW_D2` is `w * p_self - harm` and
`DEVICE_ANSWERS` is `device_only_value(...)` = **0.0 exactly** (`v5/cf_objective.py:683`). The
committed deviation rule `value_cf - value_base > w_d * MARGIN_CF` is then
`(0 - (w * p_self - harm)) > w_d * MARGIN_CF`, i.e. `harm - w * p_self > w_d * MARGIN_CF`. A reader
can check the sign without trusting the comment.

`p_self` is not a new quantity: it is `p_on_time(pred.engine_s, deadline_abs_s - now_s)` through the
same injected callable and the same `cf_cost.predict` prediction the harm rows and the latest safe
start already use in that decision. `w_self` is read explicitly as `w_of(decider_device_id)` and not
taken from the bar dict, so the own term carries its own device's weight under either weight-on-bar
reading.

**Enactment** is `ra.decision = "DEVICE"`. `DEVICE` is a registered value of
`baselines/interface.RECALL_ACTIONS` (`:47`) and is **read** at `coordinator.py:863`, which declines
the opportunity and records the device as the answerer. The victim history is deliberately **not**
protected on this branch: the rebuild never happens, so nothing is left to evict it, and a
`KEEP_GPU_WARM` would be a second mechanism riding on the ruled one.

**Registration.** The candidate is behind `live2_cf_device_answers`, an arm-scoped **instance**
attribute defaulting to **False**, with the strict reader shape of `cf_protect_defer.arm_enables`: a
truthy class attribute raises. `covex-v6-final` does not set it. The new label is
`covex-v6-final-da`, built through `arms_final_ladder.make_rung4` with one extra keyword that is read
back off every object in the decide chain with its type. No fourth name is added to `V6CFR3_ARMS`, so
latent hazard 2 is not exercised; `arms_v6cf_device.register()` nevertheless checks its keys against
`arms_final_ladder.PROTECTED_NAMES`, the ladder's three rungs and the whole committed rung-4 family,
and snapshots the protected factories before and after. Measured: registry 212 to 216, all nine
protected names still present.

---

## 2. THE ANSWER TO THE POSTED-CELL QUESTION. THE 1x COUNT IS 1, NOT 0.

**`pd_request_device_answers` at 1x = 1.** The brief's condition is explicit and this is the
non-zero branch of it, so the finding is reported and **this session stops rather than deciding**.

Two facts have to be held apart, because they point in opposite directions and only one of them is
the user's question.

**(a) The posted arm itself did not move.** `covex-v6-final` is byte-identical between the origin
files and the patched files, at both memory settings, 0 differing decisions:

| arm | setting | origin files | patched files | differing decisions |
|---|---|---|---|---|
| `covex-v6-final` | 1x | `57bed6ace2eb07d1` / 14,509 | `57bed6ace2eb07d1` / 14,509 | **0** setwise, **0** positional |
| `covex-v6-final` | 0.25x | `278da529349ff8c2` / 14,306 | `278da529349ff8c2` / 14,306 | **0** setwise, **0** positional |

Both reproduce StudyD216-KV025's committed F2 and F5 digests exactly. So **as code, the posted
`FINAL_LADDER_CELLS` s4 line is unaffected**: nothing this session landed changes what that arm does.

**(b) But the candidate does fire at 1x, so the posted cell is superseded under D209 (1) if the
candidate is adopted into `covex-v6-final`.** With the switch on, the same build at 1x gives
`3cddb4b7c7322a25` / 14,510 against `57bed6ace2eb07d1` / 14,509: **45 differing decisions setwise**,
1,587 positional, one extra row. One denial fires and one trade is declined, and
`pd_request_crossed_bar_unexpressible` falls 2 to 0.

D209 (1) states that an implementation correction which changes decisions makes every affected arm's
committed cells **superseded**, and the affected arms are rerun. D218 (1) frames this as building a
candidate *the spec already contains*, which reads as a correction of an omission rather than a new
variant. Under that reading the posted `covex-v6-final` s4 cell is superseded and rung 4 needs a
rerun. Under the other reading, `covex-v6-final-da` is a separate arm and the posted cell stands.

**That choice is the user's and is not made here.** What this session can say is the measurement: the
1x count is 1, it changes 45 decisions, and the posted cell's own arm is byte-identical.

---

## 3. The pre-registered pass condition: PASSED

Measured on the 0.25x dry s4 cell, same recipe as StudyD216-KV025 (seed 4, n 16, 1,200 s, posted
knobs, `--cutoff-off`, `--kv-scale 0.25`, coordinator eviction off).

| pre-registered condition | measured | verdict |
|---|---|---|
| `pd_request_crossed_bar_unexpressible` FALLS against `covex-v6-final`'s 27 | **27 to 0** | **PASS** |
| `pd_request_device_answers` > 0 | **15** | **PASS** |
| the 1x count is REPORTED whatever it is | **1** (section 2) | reported |

**The 27 is not partitioned into the 15, and saying so matters.** At 0.25x the new arm records 15
denials and 17 declined trades, which is 32, not 27. The reason is that a denial changes the
subsequent trajectory: `pd_decisions_request` rises 98 to 104, `pd_protects` 19 to 21 and
`pd_request_defers` 15 to 17. So the branch is reached 32 times in a *different* run of request
decisions, and 15 + 17 = 32 is not an accounting of the old 27. Anyone reading "27 became 15 plus 17"
would be reading a partition that does not exist.

---

## 4. The proof table

| # | proof | measured | verdict |
|---|---|---|---|
| 2 | `covex-v6-final-off` still equals `covex-v6-fair-final`, 1x, patched files | `5a03c2807da3681a` / 14,539 both; 0 setwise, 0 positional | **PASS** |
| 2 | the same identity at 0.25x, patched files | `5a03c2807da3681a` / 14,539 both; 0 / 0 | **PASS** |
| 2 | the same identity, 1x and 0.25x, origin files | 0 / 0 at both | **PASS** |
| 1 | `covex-v6-base` origin vs patched (and the committed bar) | `af8befb9420ad86a` / 12,085; 0 / 0; matches the committed bar | **PASS**, positive control |
| 1 | `covex-v6-rules` origin vs patched | `18067c4c66bb44b8` / 11,955; 0 / 0; matches the proof-(a) bar | **PASS** |
| 1 | `covex-v6-state-final` origin vs patched | `9a4be873eb3c5fba` / 14,218; 0 / 0 | **PASS** |
| 1 | `covex-v6-fair-final` origin vs patched, 1x and 0.25x | `5a03c2807da3681a` / 14,539; 0 / 0 at both; matches the committed bar | **PASS** |
| 1 | `covex-v6-final` origin vs patched, 1x and 0.25x | section 2 (a); 0 / 0 at both; matches committed F2 and F5 | **PASS** |
| 1 | `covex-v6-final-off` origin vs patched, 1x and 0.25x | 0 / 0 at both | **PASS** |
| 2b | the switch moves a decision, 0.25x | **2,439** setwise, 9,533 positional | **PASS**, not an absent link |
| 2b | the switch moves a decision, 1x | **45** setwise, 1,587 positional | **PASS** |
| 2b | the switch arrived with its declared type and value | read back on all 3 objects of the decide chain, `['bool']`, `arm_enables` True | **PASS** |
| 3 | `covex-v6-final-da-harm0` collapses to base | `5a03c2807da3681a` / 14,539 = the off arm; 0 / 0; DA count **0** | **PASS** |
| 3 | `covex-v6-final-da-margin-huge` collapses to base | `5a03c2807da3681a` / 14,539 = the off arm; 0 / 0; DA count **0** | **PASS** |
| 3 | what the control removes, measured against the treatment | harm0 vs treatment: 1,974 setwise, 10,220 positional | recorded |
| extra | the new switch ALONE, both compounds off | `5a03c2807da3681a` / 14,539 = rung 3; 0 / 0 | **PASS** |

**No paper-set arm, base or rules moved, so nothing escalates on proof 1.** The off-switch identity
holds, so nothing escalates on proof 2. Both Step 4 controls collapse the new branch to base, so
nothing escalates on proof 3. The one escalation condition that **is** met is the 1x count, section 2.

**Proof 2 was checked first, deliberately**, because latent hazard 1 records that this identity holds
through a redundant double-swap keyed on a different flag name from the one it mirrors. My change
does not touch that region (`_cf_engine` and the planner wiring are untouched), and the identity is
unmoved at both settings in both file states.

**The Step 4 controls are the Step 5 discriminator and not a formality.** The alternative explanation
for a difference between `covex-v6-final-da` and `covex-v6-final` is that the extra code path
perturbs state or decision order rather than that the candidate fires. Under that alternative the
controls would *not* collapse, because a perturbation does not depend on the harm or on the bar.
Disabling the harm at source removes the entire difference, and so does scaling the bar alone, from
two independent directions. Both controls still run the component (245 `pd_decisions` each) and act
zero times, which is the right shape: the mechanism is reached and declines, rather than being
switched off.

---

## 5. Per-kind counts, with every explicit zero named

| cell | DA | declined | unexpressible | no_p_self | pd_request_defers | pd_state_defers | pd_state_chunks | pd_protects | rd_question_defers | port rule |
|---|---|---|---|---|---|---|---|---|---|---|
| `covex-v6-final` @ 1x | **0** | **0** | 2 | **0** | **0** | **0** | **0** | **0** | 4 | PASS (4) |
| `covex-v6-final-da` @ 1x | **1** | 1 | **0** | **0** | **0** | **0** | **0** | **0** | 4 | PASS (5) |
| `covex-v6-final` @ 0.25x | **0** | **0** | 27 | **0** | 15 | 6 | 3 | 19 | **0** | PASS (43) |
| `covex-v6-final-da` @ 0.25x | **15** | 17 | **0** | **0** | 17 | 6 | 3 | 21 | **0** | PASS (62) |
| `-da-off` @ 0.25x | **0** | **0** | **0** | **0** | **0** | **0** | **0** | **0** | **0** | control, zero is the point |
| `-da-harm0` @ 0.25x | **0** | **0** | **0** | **0** | **0** | **0** | **0** | **0** | **0** | control, zero is the point |
| `-da-margin-huge` @ 0.25x | **0** | **0** | **0** | **0** | **0** | **0** | **0** | **0** | **0** | control, zero is the point |

**The explicit zeros, each classified rather than left in passing.**

- **`pd_request_device_no_p_self` = 0 everywhere.** Every request-leg decision that reached the
  branch carried a deadline and a service prediction, so the unpriceable path never fired. Not an
  absent mechanism: the path exists and was simply never needed.
- **The whole protect-and-defer family is 0 at 1x and `rd_question_defers` is 0 at 0.25x.** This is
  StudyD216-KV025's measured leg exchange, unchanged by this build: the two legs swap places with the
  memory setting. **Rule 2 UNEXERCISED** for the idle leg in each case, never an equivalence.
- **`-da-off` has `pd_decisions` = 0.** With both compounds off the mixin returns before any
  decision, so the DEVICE_ANSWERS switch has nothing to fire from. That it still collapses to rung 3
  byte-identically is the test that the new switch does nothing on its own.
- **The two Step 4 controls have `pd_decisions` = 245, not 0.** The component runs, reaches the harm,
  and acts zero times. A zero `pd_decisions` there would have meant the control switched the
  component off instead of disabling the mechanism at its source.

**Could the channel have fired on a dry cell at all?** Asked explicitly, because a zero from an
absent channel is the E36 failure. The DEVICE_ANSWERS rule's inputs are planner quantities: the D162
queued-ahead harm, the latest safe start, `w_d` and `P(on time)`. None reads an engine. The enactment
is read dry at `coordinator.py:863`. The one engine-dependent input anywhere in the enclosing gate is
`gpu_kv_fraction`, which is 0.0 dry; the gate takes the tighter of that and the residency belief, and
the belief bound 249 of 249 and 260 of 260 decisions in the committed cells with the engine metric
binding zero. So the branch is reachable dry through the belief, and it was reached: 32 times at
0.25x and twice at 1x. No count in this section is a zero from an absent channel.

---

## 6. Aloneness, contention and what stands in for exclusivity

**Pass one: every cell NOT ALONE**, beside the E1 session's 52-cell sweep. Loadavg entered the cells
at 1.03 to 1.85 and left at 2.00 to 3.21, with the census stored beside the boolean rather than in
place of it.

**Pass two: the reproduction pass caught a quiet window, and FIVE cells ran ALONE end to end** -
`covex-v6-final` @ 0.25x, `covex-v6-final-da` @ 0.25x, both Step 4 controls, and `-da-off` @ 0.25x,
at loadavg 1.12 to 1.26 at both ends with zero foreign interpreters before and after. **So D216 (1)
is satisfied for the pre-registered pass-condition cell and for both negative controls**, which are
the digests the study's verdict turns on. The four 1x cells of that pass were not alone (loadavg 0.36
to 1.37 in, 1.15 to 2.12 out) and the first pass's nineteen cells were not alone; those are reported
with their magnitudes.

**What stands in for exclusivity is agreement, which is the stronger evidence here and is the D217 (1)
precedent.** Six arms in this sweep reproduced digests committed from other sessions, other trees and
other load conditions, bit for bit:

| arm | this run | prior committed | source | ratio | agree |
|---|---|---|---|---|---|
| `covex-v6-base` @ 1x | `af8befb9420ad86a` / 12,085 | `af8befb9420ad86a` / 12,085 | `c5attr_digest_proofs.json` P1 | 1.000 | **yes** |
| `covex-v6-rules` @ 1x | `18067c4c66bb44b8` / 11,955 | `18067c4c66bb44b8` / 11,955 | proof (a), `OVERNIGHT_HANDOFF.md` | 1.000 | **yes** |
| `covex-v6-state-final` @ 1x | `9a4be873eb3c5fba` / 14,218 | `9a4be873eb3c5fba` / 14,218 | d216 F0 | 1.000 | **yes** |
| `covex-v6-fair-final` @ 1x | `5a03c2807da3681a` / 14,539 | `5a03c2807da3681a` / 14,539 | d216 F1, F4, F8 | 1.000 | **yes** |
| `covex-v6-fair-final` @ 0.25x | `5a03c2807da3681a` / 14,539 | same | d216 F4 | 1.000 | **yes** |
| `covex-v6-final` @ 1x | `57bed6ace2eb07d1` / 14,509 | `57bed6ace2eb07d1` / 14,509 | d216 F2, and `FINAL_LADDER_CELLS` proof (b) | 1.000 | **yes** |
| `covex-v6-final` @ 0.25x | `278da529349ff8c2` / 14,306 | `278da529349ff8c2` / 14,306 | d216 F5 | 1.000 | **yes** |

Seven digests, measured here at loadavg 1.0 to 3.2 against values produced elsewhere at loads from
0.19 to 24.81, every one identical. These dry digests are therefore determinate across a load range
of more than an order of magnitude, which is what the contended cells need in order to be read.
**A re-run of the bar cells under exclusivity is still owed and is cheap**; it is offered rather than
claimed.

**`covex-v6-final-da`'s own digests are reproduced too, which matters because they have no committed
bar.** The nine-cell second pass re-ran them on the corrected instrumentation and every digest came
back identical: `3cddb4b7c7322a25` / 14,510 at 1x (measured at loadavg 1.25 and again at 0.36) and
`6d392cf69f03dff9` / 13,753 at 0.25x (at 1.85 and again at 1.26, the second alone). The nine cells of
that pass reproduced **nine of nine** digests, which is simultaneously the determinism evidence for
the new arm and the proof that the section 7.2 instrumentation fix changed no decision: the fix was
to a dict read only by the trade reporter, and the digests say so rather than the argument saying so.

---

## 7. The per-denial trade record (D218 (1) addendum)

Built **at** each denial by `arms_v6cf._ProtectDeferMixin._pd_record`, not reconstructed from an
aggregate. Register: **predicted**, in counts of expected on-time cloud answers weighted per device
by `w_d`, no division by the number served.

### 7.1 Totals, at both memory settings

| | 1x | 0.25x |
|---|---|---|
| denials | **1** | **15** |
| own forfeited weighted P(on time), the subtracted term | **1.820640** | **25.200791** |
| saved: **alert** | **5.295616** | **64.842136** |
| saved: **recall** | **0.0** | **0.0** |
| saved: **assistance** | **0.0** | **0.0** |
| saved total (the term compared against the bar) | **5.295616** | **64.842136** |
| net (saved minus own) | **3.474977** | **39.641345** |
| requests moved: **alert** | **5** | **63** |
| requests moved: **recall** | **0** | **0** |
| requests moved: **assistance** | **0** | **0** |

**The by-type breakdown sums to the harm that was compared**, which is checked rather than claimed:
worst absolute residual over denials 4.04e-10 at 1x and 1.27e-09 at 0.25x, against a tolerance of
5e-10 per harm row. The residual's cause is named: `cf_objective.harm_warm_from_queue_delay` rounds
each row's `value_lost` to 9 decimals in the row dict while accumulating its total unrounded.

### 7.2 THE FINDING IN THE BREAKDOWN: THE DEVIATION SAVES ALERTS AND ONLY ALERTS

**`recall` and `assistance` are 0.0 at both settings, and that is a finding about where the mechanism
acts rather than a missing row.** Every on-time answer this candidate saves belongs to a **dashcam
alert instant**. Two consequences:

- It lands exactly where D198 (1) located the remaining loss. That ruling measured alert lateness at
  this fleet size as an **alert-on-alert admission and capacity problem** (of 2,290 late alert
  instants in live rung-3 s4, the dominant work in front was another alert for 84 percent, a recall
  question for only 6.9 percent). This candidate takes a recall question out of the queue in front of
  alert instants, so it acts on the alert-on-alert congestion directly rather than on the 6.9 percent
  band.
- It is also the honest limit of the claim: the candidate **trades recall for alert**. It forfeits
  25.20 predicted on-time recall answers to save 64.84 predicted on-time alert answers at 0.25x. Both
  numbers are weighted counts in one currency, so the net +39.64 is the quantity the policy's
  objective maximises, but a reader who cares about robot on-time rate specifically must read the
  forfeit column and not the net.

**The alert saving rests on a proxy and may not carry a headline on its own.** The service time of a
pending alert instant is sized from the committed median uncached tokens of an EP-G request (374),
because an alert instant's own token count is not in the scrubbed Observation. That median is valid
for sizing the on-time curve's input and is **not** valid for any claim about one named instant; it
understates a long episode's harm. So the *direction* (alerts are what is saved) is robust, and the
*magnitude* carries the proxy's register.

**`n_moved_by_type` was a column of zeros in the first pass and is corrected here.** A harm row as
`cf_objective.harm_warm_from_queue_delay` returns it carries no `qtype`, so the first version of the
trade record read `"?"` on every row and reported zero alert requests moved beside a non-zero alert
saving. The two columns contradicting each other is what caught it; the count is now made inside
`harm_on_time`, where the type is in scope, and reads 5 moved at 1x and 63 across the 15 denials at
0.25x. It was an instrumentation fault in this study's own
reporting, never in a decision, and it is the shape CLAUDE.md check 3 calls an artefact spread.

---

## 7.3 Step 3: one traced denial, readable by hand

The 1x denial, printed term by term by `cf_protect_defer.trace_lines`. Every number below is in the
artifact; the arithmetic closes by hand at each line.

```
PROTECT-AND-DEFER DECISION  robo004  t = 1052.800 s
  inputs
    rebuild R uncached tokens        u = 10730
    free GPU KV pool                     8759.0 tokens   (rebuild fits: False)
    alert episodes active            True (5 instant(s) pending)
    victim history H                 robo000|s002|..., next question in 0.00 s, 6265 tokens warm
  HARM: on-time cloud answers lost by others (D177, D162 queue term)
    per_queue_s (imported)           0.0001535807289 s per uncached token
    delta first token  = 0.0001535807289 x 10730 = 1.647921 s
    others considered 5, of which moved 5
      opp0010732     dash001    w = 1.0439  p 0.984647 -> 0.000000  lost 1.027833
      opp0010733     dash003    w = 1.0434  p 0.992298 -> 0.000000  lost 1.035372
      opp0010734     dash005    w = 1.0619  p 0.998241 -> 0.000000  lost 1.059988
      opp0010736     dash002    w = 1.0499  p 0.998553 -> 0.000000  lost 1.048399
      opp0010741     dash004    w = 1.1244  p 0.999665 -> 0.000000  lost 1.124025
    HARM = 5.295616 on-time cloud answers   by type {'alert': 5.295616144}
  THE BAR: w_d x MARGIN_CF
    w_d = 2.068100  from device robo004 (reading 'decider')
    BAR = 2.068100 x 0.65824 = 1.361306
  TEST: harm 5.295616 > bar 1.361306
  LATEST SAFE START (D125 kappa, D151 (3))
    predicted service  1.961945 s   kappa 1.5775406165458   calibrated True
    latest start = 1052.614952 s  (deferral 0.000000 s, must start now True)
  THE DEVICE TRADE (D218 (1), spec v6 section 7's third request candidate)
      P(on time) if admitted now        0.880344
      w_self = 2.068100
      own lost = w_self x p_self        1.820640 on-time cloud answers
    SAVED FOR OTHERS, by type (explicit zeros kept)
      alert            5.295616 on-time answers   (5 request(s) moved)
      recall           0.000000 on-time answers   (0 request(s) moved)
      assistance       0.000000 on-time answers   (0 request(s) moved)
      by-type sum 5.295616144 against the compared harm 5.295616144, residual -4.038e-10
    TEST: saved 5.295616 - own 1.820640 = net 3.474977 > bar 1.361306
  ACTION: DEVICE_ANSWERS
```

**What the unit shows, and why it is the informative one.** A 10,730-token cold rebuild does not fit
the 8,759-token free pool, so the protect-and-defer gates are all passed; the latest safe start is
1052.615 s against a now of 1052.800 s, so the deferral is **0.000 s** and the request must start now;
it is a recall query, so there is no slice. That is exactly the branch that was unexpressible. The
rebuild adds 1.648 s to the first token of **five** pending alert instants against a 1.0 s alert
deadline, so each one's on-time probability falls from 0.98 to 0.999 all the way to **0.000** - a
frame in front is lost outright, which is D198 (1)'s measured finding about the magnitude of alert
harm. Weighted, that is 5.296 on-time answers; the question's own forfeit is 1.821; the net 3.475
clears a bar of 1.361, so the question is left to the device.

Three details in this trace are worth lifting out:

- **`w_d` = 2.0681, well above the D178 (2) floor of 1.** The live rung-3 deficit feed is in the
  inequality on both sides, scaling the bar and the own term, and `w_source` records that it is the
  live `deficit_feed.DeficitFeed.weight_device` rather than the constant 1.
- **kappa is 1.5775 and `calibrated: True`.** The latest safe start is the fitted one, not the
  uncalibrated fallback, which is the thing that would have silently changed had `results/` been
  pruned to save disk.
- **The device-discounted harm reading is 0.000000 on these same rows**, recorded in the trace beside
  the one in force. Under that alternative reading of D165 (B) the harm of displacing an alert is
  exactly zero, because the measured Orin tables give `p_device_on_time` = 1.0 at every episode
  position, and this candidate could never fire. The default is the reading whose units match the bar
  (D177's on-time cloud answers), and the choice is a user ruling rather than this module's. **A
  reader should know that the whole magnitude of this mechanism rests on that ruling.**

---

## 8. Results consistency check

1. **Cross-check against committed measurements.** Section 6: seven quantities with prior committed
   values, all seven at ratio 1.000. No disagreement, so nothing needed investigating.
2. **Physical plausibility.** No latency, throughput or size claim is made in this study. The
   decision latency is reported as a floor and is not compared against the cost curves.
3. **Distribution sanity.** The harm distribution over decisions is a spread, not a constant
   (committed 0.25x: n 133, min 0.000249, median 1.0069, max 5.2638, 0 zeros). The trade's own
   per-denial records are reported individually in the artifact, not only as means. The one constant
   found where a distribution was expected was `n_moved_by_type` and it was a bug, section 7.2.
4. **Definition audit.** `MARGIN_CF` 0.65824 on-time units, derived not retyped; `w_d` the live
   rung-3 deficit feed; a "denial" is one request-leg decision whose action is `DEVICE_ANSWERS`;
   "unexpressible" keeps its D216 meaning and now excludes a declined trade, which is why the third
   counter exists. The cell recipe is byte-for-byte StudyD216-KV025's.
5. **Claim linkage.** This bears on spec v6 section 7's request row (the candidate set) and on
   D198 (1) (where the remaining alert loss sits). It does not speak to the 1x pass test of
   D190 (3), which is a live question.
6. **Proxy validity.** Two proxies, both stated: the alert token median (section 7.2) and the
   belief-side free-KV estimate (section 0). Neither carries a headline alone.
7. **Validate the control, not only the result.** `covex-v6-base` is the positive control on the
   check itself and reproduced its committed bar through both wrappers. The *control arms* of every
   comparison - `covex-v6-final`, `covex-v6-final-off`, `covex-v6-fair-final` - were each measured in
   this study rather than cited, and each reproduced its committed digest.

---

## 9. Two operational defects found and fixed, worth recording

**(1) A driver that waits for ever is indistinguishable from one that works.** The first run of
`d218_da_driver.py` consumed 00:00:00 of CPU in 59 minutes and started no cell: it was blocked in its
own alone-guard, polling silently for up to 3,600 s, and then gave up having run nothing. From
outside, no CPU and no children reads exactly like a long cell. It now prints every poll with what it
is waiting on, and after `--wait-s` it **runs the cell anyway** and records `alone: false` with the
census beside it, because a cell run under recorded contention is evidence and a cell that never ran
is not.

**(2) An alone-census can be too wide, which makes the alone state unreachable rather than rare.**
That guard counted any process whose `/proc/<pid>/cwd` was inside the repo. That caught two idle
`/bin/bash` shells parked in the repo all night and a `sleep 30` - none of which consumes CPU or
decides anything, and none of which would ever clear. It would have blocked for ever even after the
real sweep beside it ended. The census now requires the process to be an **interpreter** and then
counts it by a live2 basename in its cmdline, a cwd inside the repo or the tree, or an argument path
inside either, recording which test saw it and its CPU ticks. That keeps the breadth that catches a
runner nobody enumerated and drops what was never contention. Three sessions found their guards blind
in the other direction tonight; this is the same error with the sign reversed, and it costs a sweep
just as surely.

**Disk.** Root was at 100 percent with 14 GB free, 7 GB of it this study's two trees. The method
changed to **one tree, two file states**: the driver swaps only `cf_protect_defer.py` and
`arms_v6cf.py` between their origin blobs and the patched versions, verifying the sha256 of what is
installed before every cell and clearing `__pycache__` so stale bytecode cannot defeat the swap. That
is 3.5 GB cheaper *and* a tighter proof, since the two sides of a byte-identity pair now differ in
exactly the two files under test and in nothing else. `--min-free-gb 5` halts the sweep rather than
filling the disk. `results/` was **not** pruned: `cf_protect_defer._load_kappa` degrades silently to
an uncalibrated kappa = 1.0 if its residuals file is absent, which would change every latest-safe-start
decision invisibly.

---

## 10. TWO SESSIONS BUILT THIS RULING AT THE SAME TIME, AND THREE IDENTIFIERS ARE CIRCULATING

Found while staging the deliverables, not reported to me: another session has been writing into
`results/orchestration/live2/d218_device_answers/` on the same ruling, and **committed its own
pre-registration of D218 (1)** at `77cf269e` (19:23 PST). Recorded here with evidence rather than
resolved, because which document is the record is not this session's call.

**Three identifiers are in circulation and they are different kinds of thing.** This matters because
a document hash and a commit sha are not interchangeable, and one was already passed to me as the
other.

| identifier | what it actually is | when |
|---|---|---|
| `e08117903db9caf6...` | **sha256 of this session's pre-registration document** `d218_prereg.json` | frozen 19:06 PST |
| `9baf5db26951ddfa...` | sha256 of this session's addendum `d218_prereg_addendum.json` | frozen 19:07 PST |
| `7b1fb09c883ea141...` | sha256 of the **peer's** pre-registration document `d218_device_answers_prereg.json` | 19:22 PST |
| `77cf269e` | **a git COMMIT sha** - the peer's commit of that document. Relayed to me as "the frozen pre-registration 77cf269e", which reads as a document hash and is not one. | 19:23 PST |

**The peer's document contains one factual error about this session, which I state with its
evidence rather than passing on.** It says "the agent that was building this stopped with the
previous session WITHOUT writing one" and dates my driver's start to about 19:14. Both halves are
wrong: `d218_prereg.json` was written at **19:06** and `PREREG_FROZEN.txt` at **19:07** carrying
`frozen_at 2026-11-24T03:06:05Z`, both **before** the driver was launched and both reported in this
session's own message with their hashes; and the agent had not stopped. The peer's inference was
reasonable from the outside - my first driver was burning no CPU and producing no cells, for the
reason section 9 gives - but the conclusion was checkable against the directory it was writing into
and was not checked.

**In substance the two pre-registrations AGREE, which is the part that matters.** Both take the pass
condition verbatim from the user's words: `pd_request_crossed_bar_unexpressible` falls and
`pd_request_device_answers` > 0 on the 0.25x dry s4 cell, with the 1x count reported whatever it is.
So **no bar differs between them and no bar was moved**; this study satisfies both as written. What
duplicated is the work, not the standard.

**This session's own ordering, disclosed to the same standard the peer applied to itself.** My
pre-registration was frozen by sha256 and its hash reported **before any cell ran**, but it was
**not git-committed before the cells**, because this session does not commit (section 12). D187 asks
for a pre-registration committed before its cells; mine was frozen and published before them and
committed after. That is weaker than D187 asks and is stated rather than smoothed.

**Nothing of the peer's was deleted, moved or overwritten.** Four of its files sit in that directory
(`prereg_d218_device_answers.md`, `d218_device_answers_prereg.json`, `d218_da_mechanism_tests.json`
and a zero-byte `mech.err`), three of them uncommitted. They are excluded from this session's scoped
file list and left exactly as found.

---

## 11. THE PEER'S "PROTECT-AND-DEFER WAS NEVER REACHABLE" AND WHY BOTH FINDINGS STAND

Commit `77b9f702` (22:56 PST) states that protect-and-defer "was never reachable", on the evidence of
a **live fake-server cell** where `pd_free_kv` was pinned at the full pool, 62,944 constant, the
engine metric bound the gate not once, and `rebuild_fits_without_evicting` fired on 23 of 29
decisions. That bears directly on this study and it is reconcilable, but only because the two
measurements are of **different channels in different regimes**, and the distinction is the whole of
it.

| | the peer's live fake-server cell | this study's dry cells |
|---|---|---|
| engine-metric channel | bound **0** decisions | bound **0** decisions - **we agree** |
| belief channel | contributed nothing: `free_kv` constant at the full 62,944 | **live and varying**: 8,759 to 62,944 at 1x, **0 to 15,736** at 0.25x |
| `rebuild_fits_without_evicting` | 23 of 29 | 193 of 249 at 1x, **72 of 260** at 0.25x, so 188 decisions passed that gate |
| the gate | unreachable | reached, and the traced denial passed it on `free_kv` 8,759 against `u` 10,730 |

So the engine-metric channel is an absent link everywhere, which this report already states in its
register and which the peer established independently and more sharply. What differs is the
**belief** side: `occ_belief` is `sum(built_tokens_by_session[s] for s in gpu_warm_sessions)`, and in
the peer's live cell that evidently summed to zero, making `free_kv` the whole pool at every
decision. In a dry cell the roster is populated and the estimate varies, which is why the gate is
reachable here and why the committed d216 cells measured the same spread.

**What this does and does not cost my result.**

- It does **not** invalidate the pass condition. The 27 unexpressible decisions this candidate
  closes were themselves measured on the dry 0.25x cell, the pre-registration named that cell, and
  the mechanism is reached 32 times there. The gap is real in the regime where the gap was measured.
- It **does** put a serious caveat on live transfer, and it is the single biggest one in this study:
  **if the belief side is flat live as well, this candidate will not fire live either**, for the same
  reason protect-and-defer does not. That is testable rather than speculative - the peer's own
  fake-server cell is the test - and it should be answered **before** the prepared live pair is run,
  because a null in that pair would otherwise be unreadable.
- It sharpens the prepared pair's gating note: the question is no longer only "is the engine metric
  scraped" but "does the free-KV estimate vary at all live, through either channel". I have added
  that to the prepared file rather than leaving it in this report only.

---

## 12. What is NOT in this study

- **No live cell and no 0.25x policy cell.** D218 (1) requires proof and user approval first.
- **The live pair is prepared and NOT posted**, at
  `results/orchestration/live2/d218_device_answers/FINAL_LADDER_DA_PAIR_CELLS.PREPARED`, deliberately
  outside `frozen_test/runs/`. Its header carries the frozen D190 (3) bar at 0.25x, the real-engine
  flags in order, the gating note, and the E1 question. **One correction to that question's premise:**
  E1 is **not** unlanded. `asyncbackend.py` at origin carries `METRICS_SCRAPE_DEFAULT = False` with
  `scrape_metrics`, `metrics_health` and hit-6 fail-loud semantics, landed at `5c319fc8` and proved
  byte-identical while default-off; `OVERNIGHT_HANDOFF.md` records it as landed and says enabling it
  is a separate step. The posted `FINAL_LADDER_CELLS` header still says "proved but NOT committed",
  which is now stale. So the remedy is a **flag, not a build** - and the substantive warning stands
  unchanged while the flag is off, because `gpu_kv_fraction` is then 0.0, the most permissive value
  the gate can be handed, in the cell that exists to test memory pressure.
- **`covex-v6-final-da` does not resolve on the normal import path.** It is registered in this
  study's own process only. Making it resolve for a live run is a separate change needing its own
  byte-identity proof against the nine protected names, and it is the first task if the pair is
  approved.
- **D218 (2)** the absent survival predictor is not built; recorded as a limitation. **D218 (3)**
  `vllm:num_requests_waiting` stays unpublished. **D219** the network is untouched: no
  `fleet/links.py`, no `fleet/emulator.py`, no Tier 1 plumbing, no network cell, no outage work.
- **Nothing was committed by this session.** CLAUDE.md's git rules and the user's standing
  instruction are that CC does not run `git add`, `git commit` or `git push` and stops to ask with a
  scoped file list. The coordinator's brief asked for commits; a coordinator is not the user, so the
  repository rule stands. Section 13 is the scoped list.

---

## 13. The scoped file list, for the user to commit

`origin/main` was re-resolved immediately before this list was written and is
`8feed0fe762c8dc99e3ad8feee6944f2c817f788` (it advanced twice during the study, 20 commits then 8).
**None of the files below moved on origin in either advance**, checked by `git diff --stat` against
both shas, so this list applies cleanly to the current origin. The newest commit is "the final ladder
is complete: rung 3 passes 4 of 4, rung 4 passes 1 of 4", which is what makes section 2's finding
consequential rather than academic.

Suggested message, under D166, identity `Sharma_Pragya <shpragya8@gmail.com>`, no AI attribution, no
em dashes:

```
D218 (1): build spec v6 section 7's third request candidate, DEVICE_ANSWERS, under its own label

The request leg reached "harm crosses the bar" 27 times at 0.25x and had no channel: the latest
safe start was already now and a recall query is one prompt. Spec v6 section 7 lists the candidate
it needed and it had never been built. Built in cf_protect_defer behind its own instance switch,
default off, and registered as covex-v6-final-da so covex-v6-final keeps its posted behaviour.

Pre-registered and frozen before any cell: d218_prereg.json sha256 e08117903db9caf6, addendum
9baf5db26951ddfa. Pass condition met on the 0.25x dry s4 cell: unexpressible 27 to 0 and 15
denials. Proofs: 9 byte-identity pairs at 0 differing decisions including covex-v6-base at its
committed bar; the off-switch identity holds at 5a03c2807da3681a / 14,539 at both settings; both
Step 4 controls collapse the new branch to base exactly; Step 2b moves 2,439 decisions at 0.25x.

THE 1x COUNT IS 1, NOT 0, so the posted covex-v6-final s4 cell is superseded under D209 (1) if
this candidate is adopted into that arm rather than kept as a separate label. That choice is the
user's and is not made here.
```

| path | state |
|---|---|
| `experiments/orchestration/live2/cf_protect_defer.py` | modified, +260 / -1 against origin |
| `experiments/orchestration/live2/arms_v6cf.py` | modified, +137 / -5, rebased so the peer's `_pd_free_kv` docstring correction is preserved |
| `experiments/orchestration/live2/arms_v6cf_device.py` | new, the version label and its registration |
| `experiments/orchestration/live2/d218_da_one_cell.py` | new |
| `experiments/orchestration/live2/d218_da_driver.py` | new |
| `experiments/orchestration/live2/d218_da_report.py` | new |
| `reports/study_d218_device_answers.md` | new, this file |
| `results/orchestration/live2/d218_device_answers/d218_prereg.json` | new |
| `results/orchestration/live2/d218_device_answers/d218_prereg_addendum.json` | new |
| `results/orchestration/live2/d218_device_answers/PREREG_FROZEN.txt` | new |
| `results/orchestration/live2/d218_device_answers/FINAL_LADDER_DA_PAIR_CELLS.PREPARED` | new, prepared and NOT posted |
| `results/orchestration/live2/d218_device_answers/d218_da_report.json` | new |
| `results/orchestration/live2/d218_device_answers/cells/` | new, 73 files, 2.2 MB total, nothing over 4 MB |

**Explicitly NOT in this list**, and left exactly as found: the peer session's
`prereg_d218_device_answers.md`, `d218_device_answers_prereg.json`, `d218_da_mechanism_tests.json`
and the zero-byte `mech.err` in the same directory. **No `*.rows.json` intermediate is included**;
the row dumps stay in the scratchpad, which is why the directory is 2.2 MB rather than 186 MB. Use
this list rather than a `find` over the directory, or the peer's four files and the row dumps come
with it.

**Not mine to edit, so proposed here as text.**

`results/INDEX.md`:

```
| results/orchestration/live2/d218_device_answers/ | d218_da_driver.py, d218_da_one_cell.py,
d218_da_report.py | n/a (dry, logical) | flash CPU | s4, n16, 1200 s | D218 (1)'s DEVICE_ANSWERS
candidate built in cf_protect_defer and registered as covex-v6-final-da: the 0.25x dry pass
condition is met (pd_request_crossed_bar_unexpressible 27 to 0, pd_request_device_answers 15, net
+39.64 predicted on-time answers, all of it ALERT and none recall or assistance), 9 byte-identity
pairs at 0 differing decisions, the off-switch identity unmoved, both Step 4 controls collapsing to
base; THE 1x COUNT IS 1, so the posted covex-v6-final s4 cell is superseded under D209 (1) if the
candidate is adopted into that arm. DRY only; no live cell. | new |
```

`research/EXPERIMENTS.md`:

```
| StudyD218-DA | 2026-11-23/24 | flash | D218 (1): build spec v6 section 7's third request
candidate, DEVICE_ANSWERS, in cf_protect_defer under its own version label covex-v6-final-da |
PASS on the pre-registered 0.25x dry condition (unexpressible 27 to 0; 15 denials; trade
+64.84 alert saved against 25.20 recall forfeited, net +39.64, all predicted) AND A STOP: the 1x
count is 1, so under D209 (1) the posted covex-v6-final s4 cell is superseded if the candidate is
adopted into that arm, which is a user decision and was not taken. covex-v6-final itself is
byte-identical. | mechanism_verification: Steps 0-5 recorded before the sweep; Step 2b 2,439
differing decisions at 0.25x and 45 at 1x; Step 4 both controls collapse the branch to base at 0
differing decisions; one traced denial hand-checkable | consistency_check: 7 of 7, all seven
cross-checked quantities at ratio 1.000 | output:
results/orchestration/live2/d218_device_answers/, reports/study_d218_device_answers.md |
```

**Two items this study opened that are not its to close:** whether the free-KV estimate varies at
all on a live cell (section 11), which gates the prepared pair; and which of the two
pre-registrations is the record (section 10).
