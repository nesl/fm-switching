# D249 DEV BUILD 1: the mechanism is REACHABLE and REACHES DECISIONS, but the headline may NOT be asserted

*** STATUS: FIRST DEV BUILD OF A DEVELOPMENT LOOP (user ruling D249, provisional). NOTHING IS COMMITTED TO
`experiments/`; the build lives in the session scratchpad and this file is its record. NO LIVE GATE CELL WAS
RUN. ***

## THE THREE THINGS TO READ FIRST

**1. STEP 0 PASSES, and it is the first time this mechanism has been shown reachable.** One instrumented dry
run, both row sources measured in the SAME run so it is one instrument and not a new one applied to a new
source:
```
EXISTING obs.recall source : {0: 58,607, 1: 2,313}  NEVER 2 OR MORE   (reproduces D245's shape)
REAL in-flight source      : NON-ZERO IN 96.3 PCT of 60,920 decision instants
                             uncached tokens p50 168, p90 11,586, max 75,634
```
**Caveat that is load-bearing for how this reads: in a DRY cell W is submit-to-SETTLE, not
submit-to-first-token (`share_admission.py:24-33`), so this census is an UPPER BOUND on live occupancy. A
zero would have bounded live at zero; a non-zero does NOT establish the live count.**

**2. THE SWITCH REACHES A DECISION. Step 2b passes: 12,344 positional and 3,977 setwise differing
decisions**, first differing decision given as a key present only in OFF. **The read sites are named to the
argmax that IS the decision (`cf_planner.py:732`), so this is not a write-only field.**

*** 3. AND THE HEADLINE MAY NOT BE ASSERTED. "The planner now paces against contention" IS FALSE FOR THIS
BUILD, and one line of algebra shows why. ***
```
deviation requires      best.value > w_d x 0.65824
TOUCH's value is        w_d x p_question x (p_warm - p_cold) - harm_touch
so THE WEIGHT CANCELS:  p_question x (p_warm - p_cold) > 0.65824 + harm/w
largest (p_warm - p_cold) ANYWHERE in the ON run = 0.593996, and p_question <= 1
0.593996 < 0.65824  ->  TOUCH IS UNREACHABLE AT EVERY DECISION, by 0.06424
```
**So `state_chosen_TOUCH` goes 2,954 -> 0 and all 68 remaining deviations are HOLD_BACK.** *** THE CAUSE IS
THE GAIN SIDE COLLAPSING, NOT THE HARM SIDE. That is exactly the direction hazard 2 said to check: a
harm-driven effect would have produced MORE touching, and this produced NONE. ***

## WHY THE GAIN SIDE COLLAPSES: THE D249 PRICING PATH IS UNCAPPED WHERE THE HARM PATH IS NOT

```
added delay on the ON arm, 61,678 priced decisions:
   p50 25.8 ms    p90 2.654 s    p99 7.748 s    max 15.705 s
9.31 pct (5,740) EXCEED HEALTHY_FIRST_TOKEN_BOUND_S = 2.781 s
6.97 pct add MORE DELAY THAN THE WHOLE 3.0 s ROBOT DEADLINE
```
*** THE ASYMMETRY, VERIFIED IN THE COMMITTED CODE: `cf_objective.py:792` DEFINES that bound and `:838-839`
CAPS the HARM path at it ("the cap, never silent") because D160 (2) does not trust the model across the
saturation transition. THE D249 (b) PRICING PATH HAS NO SUCH CAP. *** **So the same model is trusted
further on the pricing side than its own authors trust it on the harm side, and the gain term is computed
from delays the cost model is on record as not covering.**

## THREE REMEDIES, EACH A RULING AND NOT AN IMPLEMENTATION CHOICE. NONE IS APPLIED.

1. **Cap the pricing path at `HEALTHY_FIRST_TOKEN_BOUND_S` and COUNT the cap**, matching the harm path.
2. **Price only the deadline-bearing fraction** of the queued-ahead delay.
3. **Refuse to price outside the fit and COUNT the refusal**, so an out-of-range decision is visible rather
   than silently priced.
**Each changes what the arm means, so each is the user's call.**

## AND A CONSEQUENCE FOR D246 THAT SHOULD BE SAID PLAINLY

**D246 KEPT touches: `covex-v6-fair-final` stays the freeze candidate WITH touches.** **This arm does not
REMOVE the touch feature - it PRICES IT OUT OF REACH, so touching falls to zero through the margin test
rather than through an ablation.** **A reader comparing `covex-v6-fair-final-q` against the candidate would
be comparing "touches on" against "touches unreachable", which is NOT the comparison D249 was built to
make.**

## PROOFS, AS RUN

| proof | result |
|---|---|
| **1. switch OFF, identical to rung 3** | **PASS** 14,539 rows both, digest `5a03c2807da3681a` both, positional 0, setwise 0 - and it lands on the MULTIPLY-COMMITTED bar |
| **4. positive control** | `llf` before/after ALSO identical (14,075, `961be8fe4942d86b`), so the new `CloudState` field disturbs a committed baseline not at all; and `llf` vs fair-final differs at **row 0**, so IDENTICAL is not vacuous |
| **2. switch ON, Step 2b** | **PASS** 12,344 positional / 3,977 setwise differing; first differing decision quoted |
| **3. unit tests** | **20 of 20 PASS** |

*** THE 247.5x UNIT HAZARD IS UNREACHABLE BY CONSTRUCTION, WHICH IS BETTER THAN GUARDED: the build KEEPS
the literal `0, 0` at every `CC.predict(` call site and adds the queue IN SECONDS instead. A static scan
fails if any call site loses its literal zeros. *** For the record, 11,586 tokens price at **1.7794 s**
through `per_queue_token` and would price at **440.3 s** through `per_overlap`.
**Hazard 2 measured BOTH ways: per row `harm_warm` FALLS with contention (0.074996 -> 0.000389 as tokens
ahead go 0 -> 11,586) and RISES with row count (0 -> 0.600 as n goes 0 -> 8).**
**Margin: `MARGIN_CF` is 0.16456 and the planner's bar is ALREADY `attainment_margin(MARGIN_CF)` = 0.65824
scaled by `w_d`, so D255's reading is confirmed in the code. NOTHING WAS RECALIBRATED.**

## NOT DONE, AND NOT INFERRED

- **NO LIVE GATE CELL**, as instructed. All numbers are dry.
- **NO E-id** exists for this work; CLAUDE.md requires one before it is cited.
- **KV IS NOT ENFORCED in this harness** (`kv_capacity_enforced` defaults False and `test_hybrid.dry` never
  sets it, while both committed cells carry True), so **no kv0.5r claim may be made from any of it.**
- **`state_chosen_HOLD_BACK` is 0 in the OFF dry replay against 2 in the committed live cell**, so the two
  live decisions where `harm_warm` was decisive are STILL UNEXERCISED.
- **The 38-configuration fairness suite was not run**; what exists instead is `llf` byte-identity plus
  `scrub` and `check_fairness` passing on every ON epoch.
- **Row 10.16 untouched**: `plan_state` still prices through the failed-gate model, not `predict_d162`.
- A mid-build correction is recorded: the rows' `slack_s` was aligned to the committed definition
  (`deadline - now - LINK_RTT_S`) after first publishing the raw `deadline - now`. It moved
  `harm_warm_nonzero` from 21,955 to 24,336 and **changed NO decision** (same rows, same digest).

---
---

# THE AGENT'S FULL RECORD FOLLOWS, 424 LINES, UNEDITED

# D249 FIRST DEV BUILD: queue and harm visibility in the state planner

**BUILT IN A SCRATCH TREE. NOTHING APPLIED TO THE REPOSITORY, NOTHING COMMITTED, NOTHING PUSHED.**
Read-only against `origin/main` pinned to `d7aa473e99c886f2c27f3e95523ed8256d604152`; the local
working tree was never read for code. Arm name `covex-v6-fair-final-q` (rung 3 plus D249), default
OFF everywhere else, touches left ON (D246).

Trees: `before/` is a clean archive of that sha; `after/` is the same archive plus this build.

## STEP 0, THE REACHABILITY GATE: PASSES, AND IT REPRODUCES THE COMMITTED ZERO BESIDE IT

One instrumented dry run of the posted cell (seed 4, n16, 1200 s, 40:40:20, lh_req, ss2, epg,
per-frame, rq30) on `covex-v6-fair-final`, 14,539 decision rows, 60,920 `plan_state` calls.

| source | measured at the 60,920 decision instants |
|---|---|
| **EXISTING** `obs.recall` minus the planned session | `{0: 58,607, 1: 2,313}`, **never 2 or more** |
| **REAL in-flight** (other devices), count | `{0: 2,253, 1: 11,010, 2: 13,736, 3: 14,660, 4: 11,526, 5: 5,662, 6: 1,777, 7: 228, 8: 13, 9: 37, 10: 18}` |
| **REAL in-flight, non-zero fraction** | **96.3 percent** (58,667 of 60,920) |
| **REAL in-flight uncached tokens** | p50 168, p90 11,586, max 75,634 |
| in-flight type mix over all calls | alert 144,563, recall 22,447, assistance 2,741 |

The existing-source histogram reproduces the D245 shape (`{0: 10,181, 1: 425}`) in the same run, so
this is one instrument measuring both sources and not a fresh instrument measuring a new one.

**DRY-CELL DEFINITION CAVEAT, which decides how the number may be read.** In a LIVE cell W is
submit to FIRST TOKEN; in a DRY cell it is submit to SETTLE, because `on_first` is wired only
behind a real backend (`share_admission.py:24-33`). The dry quantity is the LARGER of the two, so
this census is an **upper bound** on live occupancy: a zero here would have bounded live at zero,
and a non-zero here does NOT establish the live count.

**VERDICT: STEP 0 PASSES.** A queue term fed from the real in-flight source is non-zero at 96.3
percent of decision instants, carries up to 75,634 uncached tokens, and at 8,437 tokens already
moves `p_on_time_warm` from 0.982 to 0.637 (traced unit below). The build proceeded.

## THE BUILD

| file | +/- | what |
|---|---|---|
| `baselines/interface.py` | +37 / -0 | `InFlightWork` dataclass; `CloudState.in_flight_work = ()` default |
| `live2/share_admission.py` | +11 / -0 | `WTracker.items()`, a read-only copy of the tracked set |
| `live2/cstate.py` | +8 / -1 | `CoordState.inflight_work` published register, copied into `CloudState` |
| `live2/coordinator.py` | +62 / -0 | D249 switch; `_d249_inflight_rows`; publish in `_epoch` before the observation |
| `live2/arms_v6state.py` | +157 / -6 | row source, queued-ahead token count, `_p_warm_cold` signature, counters, describe |
| `live2/arms_final_ladder.py` | +28 / -0 | `RUNG3_D249`, `_set_d249`, `make_rung3(d249_queue_visibility=...)` |
| `live2/arms_v6cfr3.py` | +7 / -0 | `covex-v6-fair-final-q` on the normal `arms.make_arm` path |
| `live2/d249_queue_visibility.py` | NEW 134 | the switch, the FAIL-LOUD unit guard, `queue_delay_s` |
| `live2/d249_queue_unit_proofs.py` | NEW 254 | the unit tests |

### THE NAMED READ SITE THAT CHANGES A DECISION

Two, traced end to end rather than asserted, both in the `after` tree:

**(1) the queued-ahead TOKEN COUNT, which changes the warm/cold pair.**
```
arms_v6state.py:572   qa = self._d249_queued_ahead_tokens(obs)      # READS obs.cloud.in_flight_work
arms_v6state.py:573   p  = self._p_warm_cold(int(est.get(sid, b) or b), b, qa)
arms_v6state.py:420   ... CC.p_on_time(cf.residuals, warm.engine_s + q_s, ...)   q_s = QV.queue_delay_s(qa)
arms_v6state.py:598   d  = cf.plan_state(..., p_on_time_warm=p["warm"], p_on_time_cold=p["cold"], ...)
v5/cf_planner.py:686  Candidate("TOUCH", value=gain(p_on_time_warm, p_on_time_cold, harm_touch))
v5/cf_planner.py:732  best = max(scored, key=...)        <- the argmax that IS the decision
arms_v6state.py:629   emits SessionAction(KEEP_GPU_WARM)   /   :633 drop.add(sid) removes the MATERIALIZE
```
**(2) the in-flight HARM ROWS, which change `harm_warm` and `harm_touch`.**
```
arms_v6state.py:462-468   the rows are appended to _queued_behind's output
arms_v6state.py:590,598   _harm_warm(...) -> cf_objective.harm_warm_from_queue_delay
v5/cf_objective.py:849,859  pa = p_on_time(eng, slack - dt);  total += vb - va
v5/cf_planner.py:686 (TOUCH harm) and :710 (HOLD_BACK value IS harm_warm) -> :732 argmax -> as above
```
Neither field is write-only: the ON/OFF decision logs differ in 3,977 decisions (setwise) and the
counters move as section "PROOF 2" records.

## THE LIGHT PROOFS

Instrument: `hybrid/test_hybrid.dry`, `realtime=False`, every module taken from the tree under
test, ONE CELL PER PROCESS. Strip set `("arm", "decision_latency_ms", "decision_id")` plus
`arm_version`; both digests are recorded because the narrow one is what the committed bar was
taken with and the same arm carries the same `arm_version` either way.

### PROOF 1, the OFF-switch identity: PASS, and it lands on the committed bar

| leg | rows | digest (wide strip) | digest (narrow strip) |
|---|---|---|---|
| `covex-v6-fair-final`, BEFORE tree | 14,539 | `5a03c2807da3681a` | `987c2b98784d2dc7` |
| `covex-v6-fair-final`, AFTER tree | 14,539 | `5a03c2807da3681a` | `987c2b98784d2dc7` |

`positional_differing 0`, `setwise_differing 0`, digests equal. **The committed bar is 14,539 rows
and digest prefix `5a03c2807da3681a`, and the wide-strip digest IS that prefix.**

### PROOF 4, the positive control on proof 1: PASS, twice over

| leg | rows | digest (wide) |
|---|---|---|
| `llf`, BEFORE tree | 14,075 | `961be8fe4942d86b` |
| `llf`, AFTER tree | 14,075 | `961be8fe4942d86b` |

- `llf` before vs after: `positional 0`, `setwise 0` - a committed baseline on a path this build
  does not touch does not move, and the new `CloudState` field does not disturb it. (It also means
  `interface.scrub` and `check_fairness` ran on every epoch with the new field present and raised
  nothing.)
- `llf` vs `covex-v6-fair-final` on the SAME machinery: 14,075 against 14,539 rows, digests differ,
  `positional_differing 14,539`, `setwise_differing 12,362`, **first differing row index 0**
  (`release_piece` against `release_monitor`). So an IDENTICAL verdict in proof 1 is not vacuous:
  this instrument does detect a difference when there is one.

### PROOF 2, Step 2b with the switch ON: the decision moves, and it moves a long way

| leg | rows | digest (wide) |
|---|---|---|
| `covex-v6-fair-final` (OFF) | 14,539 | `5a03c2807da3681a` |
| `covex-v6-fair-final-q` (ON) | 11,386 | `b7bb6e018b6e1d27` |

- **positional differing 12,344; setwise differing 3,977** (the setwise register is the right one
  for "did the switch move a decision": one early divergence desynchronises the positional count).
- **first differing decision**, in the setwise register, is the key `(233.3, "release_piece", [],
  None, None)` present only in the OFF log: at t = 233.3 s the OFF arm releases a build piece the
  ON arm does not. Positionally the first differing row is index 2,195: OFF `release_piece` at
  t = 233.3 against ON `release_recall` at t = 233.4 (`opp0002253`).
- differing fields over the whole log: `opportunity_ids` 9,167, `t` 9,151, `traffic_mix` 7,654,
  `kind` 4,053, `note` 2,587, `desired_tier` 1,911, `representation` 633, `piece_tokens` 159.

**WHAT MOVED IN THE PLANNER'S OWN COUNTERS** (OFF against ON, same cell):

| counter | OFF | ON |
|---|---|---|
| `state_decisions` | 60,920 | 61,678 |
| `state_chosen_TOUCH` / `state_touch_emitted` | 2,954 / 2,954 | **0 / 0** |
| `state_chosen_WARM` | 6 | 0 |
| `state_chosen_HOLD_BACK` / `state_hold_back_enacted` | 0 / 0 | **68 / 68** |
| `state_deviations` | 2,960 | 68 |
| `harm_warm_priced` / `harm_warm_nonzero` | 2,314 / 1,607 | 59,314 / 24,336 |
| `harm_warm_no_queue` | 58,720 | 2,477 |
| `harm_warm_max_milli` | 998 | 5,442 |
| `gain_TOUCH_over_margin` | 2,960 | 0 |
| `gain_TOUCH_milli_sum` | 15,000,066 | 5,082,455 |
| `d249_rows_appended` | 0 | 163,236 |
| `d249_pwc_queue_priced` / max | 0 | 60,723 / 15,705 ms |
| `d249_queued_ahead_max` (tokens) | 0 | 102,258 |
| `submitted_piece` | 163 | 94 |
| `release_infeasible_alert` | 1,878 | 1,767 |
| planner timeouts or abandons | 0 | 0 |

No `timeout_fallback`, no `state_skipped_unpriced`: the TOUCH collapse is a pricing outcome and
not a budget or exception artefact.

### PROOF 3, the unit tests: 20 checks, 20 PASS, 0 FAIL

`experiments/orchestration/live2/d249_queue_unit_proofs.py`, output in `d249_unit_proofs.json`.

**The unit guard (hazard 1).** `assert_queue_unit` accepts `per_queue_token`
= 0.0001535807289338535, REFUSES `cf_cost`'s `per_overlap` = 0.038004811772727576 in the per-token
slot, REFUSES a 1 percent drift, and checks the ratio is the measured 247.4582. A static test
scans every `CC.predict(` call in `arms_v6state.py` with a balanced-paren parse and fails unless
the third and fourth arguments are literal zeros: **the hard zero is kept, deliberately**, and the
queue is added in SECONDS instead. For the record, 11,586 queued-ahead tokens price at 1.7794 s
through `per_queue_token` and at 440.3 s through `per_overlap`.

**The pricing arithmetic.** `queue_delay_s`: 0 tokens 0 s; 15 tokens (a touch) 2.3037 ms, which is
the 2.30 ms mispricing the D245 estimate names; 168 tokens (the measured p50) 25.80 ms; 11,586
(p90) 1.7794 s; 75,634 (max) 11.6159 s. Monotone. At zero queued-ahead tokens the ON arm's
`_p_warm_cold` returns EXACTLY the committed rung-3 pair (the per-quantity negative control).

**Hazard 2, measured in both directions.** Per row, `harm_warm` FALLS as the queue ahead of that
row grows: 0.074996 at 0 queued-ahead tokens, 0.066528 at 168, 0.035157 at 1,108, 0.000389 at
11,586 - a request already predicted slow has less `p_on_time` left to lose. Across rows it RISES
with the row count: 0, 0.074996, 0.149992, 0.299985, 0.599969 at n = 0, 1, 2, 4, 8. The new source
supplies rows (1 to 10 of them), so the two effects run against each other and the net sign is an
empirical question, not a deducible one.

**The margin (hazard 3).** `MARGIN_CF` = 0.16456 (correctness units); the planner's bar is already
`cf_objective.attainment_margin(MARGIN_CF)` = 0.65824 on-time answers, read once per decision in
`v5/cf_planner.py::Counterfactual._margin` and then scaled by `w_d`. So D249's "MARGIN_CF
(0.6582)" is the value of `MARGIN_CF_ON_TIME` AND is the bar the code already applies: **this build
changes no margin and recalibrates nothing.** In the traced unit the effective bar is
0.65824 x 1.888889 = 1.2433.

**The switch.** Default OFF on rung 3; ON only on `covex-v6-fair-final-q`; a truthy CLASS attribute
raises `D249SwitchError`; one instance attribute serves both the coordinator's publisher and the
planner's consumer, so "publisher on, consumer off" is not expressible.

## STEP 3, ONE TRACED UNIT (the unit is one `plan_state` decision)

`d249_trace_unit.json`, decision `st:robo005|s000|...:2`, t = 34.9 s + 0.2 s, device `robo005`,
ON arm, same posted cell. The SHADOW column is the same decision's inputs recomputed on the same
arm instance with the switch flipped off, so the two columns differ in the switch and nothing else.

```
INPUTS      p_question 0.0052098   next_question_s 62.878   tokens_to_build 7287
            warm_expressible False   host_warm False
            queued_ahead_tokens (D249) 8437  ->  8437 x 0.0001535807289338535 = 1.295761 s
            in-flight harm rows: 3 (all dashcam, qtype alert)   rows from obs.recall: 0
PRICES ON   p_on_time_warm 0.637276   p_on_time_cold 0.549444   harm_warm 0.0
            harm_touch 0.00085264  (15 uncached tokens -> 2.3037 ms taken off 3 rows' slack)
PRICES OFF  p_on_time_warm 0.982345   p_on_time_cold 0.973370   harm_touch 0.0
BUDGETS     KV bytes: not charged by a state decision.  Accelerator: the harm IS the charge, in
            expected on-time cloud answers, and it is 0.00085264 of one answer.
BOUND BY    THE MARGIN. best = TOUCH at value 1.169e-05; bar = 0.65824 x w_d 1.888889 = 1.2433422
OUTCOME     chosen KEEP, deviated False, delta 1.1693e-05
```
Hand check: `0.0052098 x 1.888889 x (0.637276 - 0.549444) = 8.641e-04`; minus `harm_touch`
8.5264e-04 leaves 1.169e-05, which is `delta`. The queue term is doing real work here - it moved
`p_on_time_warm` by 0.345 - and the decision is still bound by the margin, not by the queue.

Three traced units are in the file. In the ON trajectory the shadow comparison found **0**
decisions where the OFF-priced TOUCH value crossed the bar while the ON-priced one did not; the
2,954 OFF touches belong to the OFF TRAJECTORY, which diverges after t = 233.3 s (fewer build
pieces, 94 against 163), so a within-ON shadow cannot recover them. The ON/OFF log diff, not the
shadow, is the Step 2b evidence.

NOTE ON THE TRACE RUN'S COUNTERS: the probe itself calls `_d249_rows` a second time per decision,
so `d249_rows_built` in that file is exactly doubled (326,199 against 163,236). The decision log is
unaffected - the trace run reproduces 11,386 rows and digest `b7bb6e018b6e1d27`.

## MECHANISM VERIFICATION, Steps 1, 2, 4, 5

**Step 0** is above and is the ruling's own gate. It passed.

**Step 1, the causal chain, traced to `research/FORMULATION.md` section "D249 DRAFT: QUEUE AND HARM
VISIBILITY IN THE STATE PLANNER".** That section's VALUE OF A STATE ACTION is
`w_d x P(question soon) x (P(on time | warm) - P(on time | cold))` and its HARM OF A STATE ACTION is
a sum over "the queued or running requests the action would delay" of
`w_type x (P(on time now) - P(on time | + queued-ahead tokens))`, the delay taken from the D162
model at `per_queue_token` seconds per queued-ahead token and measured against EACH REQUEST'S OWN
DEADLINE SLACK, with the DECISION RULE "deviate from KEEP only if value - harm > margin". The chain
this build tests: IF the coordinator publishes the requests it is actually serving, with their
device, type, uncached tokens and own deadline slack, THEN (i) the harm sum has a non-empty index
set at the instants the planner decides, where before it was empty, so a state action's harm is
non-zero; AND (ii) `P(on time | warm)` and `P(on time | cold)` are evaluated behind that same
queued-ahead work rather than against an empty engine; THEREFORE `value - harm` moves on both
terms, the DECISION RULE's comparison against the margin changes outcome where the queue is
non-zero, and the change is expressed through the committed channels (emit `KEEP_GPU_WARM`, or
remove the MATERIALIZE ask). Every link is in that section; the section was committed at
`58e09e12` precisely because Step 1 could not be written before it.

**Step 2, each link instantiated.**

| causal link | implementing quantity | value / range in this run | varies as expected? | evidence (the READ, not the write) |
|---|---|---|---|---|
| the engine's in-flight work exists and is visible | `CloudState.in_flight_work`, from `WTracker.items()` joined to `futures` | 1 to 10 rows, non-zero at 96.3 pct of 60,920 decisions; 0 to 102,258 uncached tokens | YES, and the OLD source is flat at `{0, 1}` and never 2 | read `arms_v6state.py:572` (tokens) and `:462-468` (rows) |
| queued-ahead tokens become seconds at the D162 coefficient | `QV.queue_delay_s` | 0 to 15.705 s added; priced on 60,723 of 61,678 decisions | YES | read `arms_v6state.py:420` inside `_p_warm_cold` |
| the warm/cold pair responds | `p_on_time_warm`, `p_on_time_cold` | 0.982 -> 0.637 and 0.973 -> 0.549 on the traced unit | YES | read `v5/cf_planner.py:686` in `gain()` |
| harm has a non-empty index set | `harm_warm_from_queue_delay` rows | priced 2,314 -> 59,314; non-zero 1,607 -> 24,336; max 0.998 -> 5.442 | YES | read `v5/cf_objective.py:849,859` |
| the comparison against the margin changes outcome | `plan_state` argmax | TOUCH 2,954 -> 0; HOLD_BACK 0 -> 68; deviations 2,960 -> 68 | YES | read `v5/cf_planner.py:732`, enacted `arms_v6state.py:629,633` |
| the margin itself | `attainment_margin(MARGIN_CF)` x `w_d` | 0.65824 x w, unchanged by this build | CONSTANT BY DESIGN (no recalibration in this build, per the ruling) | `v5/cf_planner.py:_margin` |

No link is ABSENT, zero or constant except the margin, which is constant deliberately.

**Step 4, the negative control.** The mechanism disabled is the OFF arm, and it collapses to rung 3
BYTE-IDENTICALLY on the full posted cell (proof 1: 14,539 rows, digest `5a03c2807da3681a`,
0 differing decisions). Per quantity: with `queued_ahead_tokens = 0` the ON arm's `_p_warm_cold`
returns exactly the committed pair, and with no rows `harm_warm` returns the counted real zero.
The control is on one cell (seed 4, n16, 1200 s, the posted workload), as the protocol allows.

**Step 5, the alternative explanation, and it is NOT ruled out.**
The claimed mechanism is "the planner now prices state work against real contention". A second
mechanism makes the same prediction on every population metric: **the queued-ahead delay is
UNCAPPED and reaches far outside the range the D162 model was fitted on.** `cf_objective`'s own
harm path caps its added delay at `HEALTHY_FIRST_TOKEN_BOUND_S = 2.781 s` and counts the cap,
because D160 (2) does not trust the model across the saturation transition; the D249 (b) pricing
path has no such cap and added up to **15.705 s** of predicted first token in this cell. A
`p_on_time` driven to zero by an extrapolation is not a contention price. The distinguishing data
is the fraction of priced decisions whose added delay exceeds 2.781 s, measured in
`d249_range_probe.json`, together with the direction check: hazard 2's measured sign says a
harm-driven effect would produce MORE touching, and this build produced NONE, which points at the
GAIN side (both `p_on_time` terms collapsing) rather than at the harm side. On this evidence the
headline "the planner paces against contention" may NOT be asserted from this dev build.

## RESULTS CONSISTENCY CHECK

**1. Cross-check against committed measurements.**

| quantity | this run | prior run | source of prior | ratio | agree |
|---|---|---|---|---|---|
| rung-3 1x s4 dry decision rows | 14,539 | 14,539 | `study_fix102_prepared.md:35` | 1.000 | agree |
| its digest prefix (wide strip) | `5a03c2807da3681a` | `5a03c2807da3681a` | same | - | agree |
| `state_action` / touches on that cell | 2,954 | 2,954 | same | 1.000 | agree |
| `llf` rows / digest | 14,075 / `961be8fe4942d86b` | 14,075 / `961be8fe4942d86b` | the posted positive control | 1.000 | agree |
| existing row source, non-zero share | 2,313 / 60,920 = 3.80 pct | 425 / 10,606 = 4.01 pct | D245 `npend_hist` | 0.95 | agree (different denominators, same shape; never 2 either time) |
| `per_queue_token` (s per token) | 0.0001535807289338535 | same | `d162_price.PER_QUEUE_S`, gate 68a2b47 | 1.000 | agree |
| `per_overlap` (s per request) | 0.038004811772727576 | same | `cost_model_gate.json` | 1.000 | agree |
| the unit factor between them | 247.4582 | "about 247.5", "247.46x" | D245 estimate, fix102 | 1.000 | agree |
| a touch's priced harm delay | 2.3037 ms | 2.30 ms | D245 estimate | 1.000 | agree |
| `MARGIN_CF_ON_TIME` | 0.65824 | 0.6582 | D177 (3), `cf_protect_defer.py:277` | 1.000 | agree |

No disagreement above 2x anywhere.

**2. Physical plausibility.** `per_queue_token` implies 1 / 0.0001536 = 6,511 queued tokens per
second of induced first-token delay, which is the same order as the committed A6000 cold prefill
of about 7,100 tok/s: the queue coefficient says the engine serialises queued prefill at roughly
prefill throughput. Nothing in this build implies a rate FASTER than a committed curve. The 15.705 s
maximum added delay is 102,258 / 6,511 = 15.7 s and is therefore internally consistent - and far
outside the regime the fit covers, which is the Step 5 problem, not an arithmetic one.

**3. Distribution sanity.** Spreads are reported beside every median (in-flight count histogram
over all 60,920 decisions; token percentiles p50 168, p90 11,586, max 75,634; delay percentiles in
`d249_range_probe.json`). One constant appears where a distribution might be expected: the four
dashcam rows in the traced unit all carry `engine_s` 0.02244965291809938 exactly. That is correct
rather than short-circuited - all four are `monitor` requests charged 42 uncached tokens, so a
one-feature linear model must return the same number; the varying field across those rows is
`slack_s` (0.5560, 0.5613, 0.7820, 0.7580), which is the field the harm term reads.

**4. Definition audit.**
- **in-flight** = the `WTracker` tracked set, submit to FIRST TOKEN in a live cell and submit to
  SETTLE in a dry cell (`share_admission.py:24-33`). The dry definition is the larger. NOT
  `_uncached_in_flight`, which drains at completion and includes decode.
- **uncached tokens** = `_uncached_last_charged` at submit, the same number W was given and the
  same number the D174 budget charge used; never recomputed.
- **slack** = `deadline_abs - now - LINK_RTT_S`, for BOTH row kinds. The coordinator publishes the
  raw `deadline - now` and the arm subtracts the link term where the committed recall rows do, so
  one name carries one quantity. (Before that alignment the D249 rows omitted the link term; it
  changed `harm_warm_nonzero` from 21,955 to 24,336 and changed NO decision - same 11,386 rows,
  same digest `b7bb6e018b6e1d27`.)
- **queued-ahead tokens** = the sum over ALL published rows, background included, because a build
  piece occupies the engine ahead of a question exactly as a deadline request does.
- **a decision** = one `plan_state` call. **A differing decision** = a differing stripped row of
  `decision.jsonl`, counted both positionally and setwise.

**5. Claim linkage.** Every headline here bears on `research/FORMULATION.md`'s D249 section, which
is the authority the ruling named, and on freeze-gate row 10.2 (whether rung 3's state planner can
price with a real queue term). It does NOT yet bear on `CLAIMS.md`'s coupling claim, and no
quantity measured here is scoped out by `FORMULATION.md :: Scoping` (nothing moves KV between
tiers; nothing crosses architectures). Row 10.16 is untouched: `plan_state` still prices through
`CC.load_gate_model()`, whose `GATE_STATUS` records decode over-predicting by 25 to 32 percent, and
this build does not route it through `predict_d162`.

**6. Proxy validity.** Two proxies, both stated and neither used for a headline:
(a) **dry W as live in-flight** - it is submit-to-settle, so it is an upper bound; valid for
"can the term be non-zero" and NOT valid for sizing the live queue. (b) **total in-flight tokens
minus the row's own, as the queue ahead of that row** - the published register is a SET and carries
no submit order, so this over-estimates for the request at the head of the queue. Both are marked
unvalidated for any policy conclusion.

**7. Validate the control, not only the result.** The control arm in proof 1 is the BEFORE tree's
own rung 3, and its numbers were cross-checked against its committed values (14,539 rows, digest
`5a03c2807da3681a`) BEFORE the comparison was read; a "before" condition that had destroyed the arm
would have shown up there. The positive control `llf` reproduced its posted 14,075 rows and digest
`961be8fe4942d86b` on both trees and differs from rung 3 at row index 0, so the instrument can see
a difference. As a control on the CHECK rather than the arm: the pre-existing unit suites
`tests/test_live2_coord.py` (errors=4) and `tests/test_live2_fix.py` (errors=6) fail IDENTICALLY on
the before and after trees once the same committed inputs are present, so those failures are the
partial scratch tree and not this build; `tests/test_cf_objective_d177.py` (30/30) and
`cf_pd_tests.py` (36/36) pass identically on both.

## *** THE RANGE FINDING, AND THE ONE LINE OF ALGEBRA THAT EXPLAINS THE WHOLE ON RESULT ***

`d249_range_probe.json`, instrumentation only, same cell, ON arm, 61,678 priced decisions:

| quantity | value |
|---|---|
| queued-ahead tokens | p10 84, p50 168, p90 17,280, p99 50,452, max 102,258 |
| added first-token delay | p10 12.9 ms, p50 25.8 ms, **p90 2.654 s**, p99 7.748 s, **max 15.705 s** |
| above `HEALTHY_FIRST_TOKEN_BOUND_S` = 2.781 s | **5,740 of 61,678 = 9.31 pct** |
| above the whole 3.0 s robot deadline | 4,297 = 6.97 pct |
| `p_on_time_warm - p_on_time_cold` | p50 0.00981, p90 0.2407, **max 0.593996** |
| pairs where both terms hit zero | 299 |

**THE ALGEBRA.** `plan_state` deviates iff `best.value > w_d x MARGIN_CF_ON_TIME`, and TOUCH's value
is `w_d x p_question x (p_warm - p_cold) - harm_touch`. The weight CANCELS: the test is
`p_question x (p_warm - p_cold) - harm_touch / w_d > 0.65824`. With `p_question <= 1` by
construction, the condition requires `p_warm - p_cold > 0.65824`. **In the ON run the LARGEST
`p_warm - p_cold` anywhere in 61,678 decisions is 0.593996, which is below the bar.** So TOUCH is
not merely unattractive under D249 on this cell, it is UNREACHABLE: the queued-ahead delay
compresses the warm-cold gap under the fixed bar at every single decision. That, and not a harm
term, is why `state_chosen_TOUCH` is exactly 0 and `gain_TOUCH_over_margin` is exactly 0.

**WHY THIS MATTERS FOR HOW THE RESULT IS READ.** The headline "the queue term stops the planner
touching" is TRUE of this cell and its cause is the GAIN side collapsing, not the harm side. Nine
percent of those prices are extrapolations past the bound the project's own harm path refuses to
cross, and seven percent add more delay than the entire robot deadline. Three remedies exist and
each is a RULING, not an implementation choice: cap the added delay at
`HEALTHY_FIRST_TOKEN_BOUND_S` and count the cap as `harm_warm_from_queue_delay` already does;
price only the deadline-bearing fraction of the queue; or refuse to price a decision whose queue is
outside the fit and count the refusal. **None is applied here.** This build reports the uncapped
number because capping it silently would be the same class of mistake as the 247x unit error: a
number from outside the fit wearing a fitted number's clothes.

## WHAT WAS NOT DONE, AND WHAT IS NOT ESTABLISHED

- **Nothing is committed, pushed or applied.** Both trees are in the session scratchpad. The
  repository's `research/EXPERIMENTS.md`, `results/INDEX.md` and `research/STATUS.md` were NOT
  updated, because nothing may be written to the real tree under this brief.
- **No E-id exists for this work.** CLAUDE.md requires one before any task and the D245 estimate
  recorded the same gap. This build ran under the explicit ruling instead; the row still has to be
  created before any of this is cited.
- **The live gate cell was NOT run**, as instructed. Every number here is a DRY cell
  (`realtime=False`, simulated clock, `dry_run=True`, no engine). The d188 precedent warns a dry
  replay bounds nothing about live, and `state_chosen_HOLD_BACK` is 0 in the OFF dry replay against
  2 in the committed live cell, so the two decisions where `harm_warm` was decisive in the live
  cell are still not exercised by this instrument.
- **KV capacity is NOT enforced in this harness.** `cstate.py` defaults `kv_capacity_enforced`
  False and `test_hybrid.dry` never sets it, while both committed cells carry True. Every number
  here is the unenforced-KV condition. No kv0.5r claim is made.
- **The 38-configuration baseline fairness suite was not run.** What was measured instead: `llf`
  is byte-identical before and after, and `interface.scrub` plus `check_fairness` ran on every
  epoch of the ON cell with the new field present and raised nothing.
- **Row 10.16 does not close** and this build does not touch it: `plan_state` still prices through
  the failed `cost_model_gate` model rather than `predict_d162`.
- **`arm_version` was deliberately NOT bumped**, so both arms report `covex-v6-state-1.0` and the
  widened strip set is belt and braces rather than load-bearing on this comparison.
- **The margin is NOT recalibrated**, per the ruling. The code's bar is already 0.65824 x w_d.
- **No score, no quality or on-time metric, and no per-device dashcam reading is reported.** D236
  measured more touching costing 383 dashcam on-time instants; this build touches LESS (2,954 -> 0),
  so the D236 direction is not the risk here, but nothing in a dry cell licenses any claim about
  dashcam on-time, and `dashcam_per_device` beside `robot_pool_on_time` is what a live reading
  would have to report.

## FILES (session scratchpad; nothing in the repository)

```
.../scratchpad/d249/before/                 clean archive of origin/main d7aa473e
.../scratchpad/d249/after/                  the same plus this build
.../scratchpad/d249/out/d249.diff           the full diff, 56,617 bytes
.../scratchpad/d249/out/step0_full_1200.json        STEP 0 reachability census
.../scratchpad/d249/out/d249_unit_proofs.json       20 unit checks, 20 PASS
.../scratchpad/d249/out/diff_proof1_offidentity.json
.../scratchpad/d249/out/diff_poscontrol_llf_identity.json
.../scratchpad/d249/out/diff_poscontrol_llf_vs_r3.json
.../scratchpad/d249/out/diff_proof2_step2b.json
.../scratchpad/d249/out/d249_trace_unit.json        STEP 3 traced units
.../scratchpad/d249/out/d249_range_probe.json       the fitted-range finding
.../scratchpad/d249/out/cell_*.json.gz              the five dry cells' stripped logs
.../scratchpad/d249/drv/*.py                        the drivers
```
