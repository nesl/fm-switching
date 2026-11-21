# StudyV5-CF: the counterfactual engine, built and dry-proved

Session B of the policy v5 effort, flash, 2026-11-20. Artefacts:

- `experiments/orchestration/live2/v5/cf_margin.py` (the one declared margin constant, and the
  measured safety factor)
- `experiments/orchestration/live2/v5/cf_cost.py` (predicted service with decode, the delivery
  probability, the latest safe start, two-level fidelity)
- `experiments/orchestration/live2/v5/cf_objective.py` (the objective, deficit weighting, harm)
- `experiments/orchestration/live2/v5/cf_instrument.py` (per-decision wall clock, full distribution)
- `experiments/orchestration/live2/v5/cf_planner.py` (the three decision kinds and their candidate
  sets, horizons, base execution, margin gate, timeout fallback)
- `experiments/orchestration/live2/v5/cf_proofs.py` (every unit proof and the latency measurement)
- `results/orchestration/live2/v5/cf_service_residuals.json`
- `results/orchestration/live2/v5/cf_unit_proofs.json`
- `results/orchestration/live2/v5/cf_decision_latency.json`

Source decisions: D146 to D155, and `research/policy_spec_v5.md` sections 3, 4, 5, 7, 10, 12 and
15. Session C's interface note (`reports/study_engine_actions.md` section 1) is the contract the
engine-action side is built against. Everything was read from a detached worktree at `origin/main`
(`4c8c814`); the flash working tree is hundreds of commits behind and contains none of it (spec v5
gap G2, unchanged).

---

## 0. REGISTER, first, because this report holds numbers in three of them

| register | which numbers | what they are not |
|---|---|---|
| **MEASURED on committed data** | the cost-model coefficients, the held-out residual ratio distribution (p50 1.031, p90 1.578, p99 3.683), the p90 absolute service error 0.1817 s, the safety factor 1.5775 | not measurements of v5; they are reads of 345,066 committed requests through the committed gate model |
| **MEASURED on this CPU** | every per-decision wall clock, including the p99 at 8, 16 and 32 devices | not a measurement of the live harness: no coordinator state rebuild, no engine, no GPU, and the decision load is constructed |
| **CONSTRUCTED** | every decision grid and every fleet load in `cf_proofs.py` | not a workload, not a cell, not an arm comparison |

**Nothing in this report is a policy result, and that is not a hedge about quality, it is a
prohibition.** `MARGIN_CF` is UNSET (D154 (2)) and the D151 (6) cost-model gate FAILS, so spec v5
section 12.1 forbids any v5 cell. Every planner proof below therefore runs DRY: the margin is
supplied by an explicit override, every decision carries `scorable: false`, and the engine's only
scorable read raises `MarginUnset`. **No arm was compared to another arm on any outcome.**

**No E-id exists for policy v5** (spec v5 gap G5), and this session does not own
`research/EXPERIMENTS.md`. CLAUDE.md requires an E-id before a task proceeds; what is reported here
is a build with dry unit proofs and no sweep, which is the only thing that can be done before the
row exists. A draft row is in section 9. **The E-id is blocking for any v5 sweep and is not
blocking for this build.**

---

## 1. What was asked for, and what is in each file

Spec v5 section 15 lists five things from session B, plus the user's additions in the brief. Each
one, with the function that implements it and the proof that reads it:

| asked for | where | proof |
|---|---|---|
| three decision kinds, candidate set per kind (D151 (2)) | `cf_planner.Counterfactual.plan` dispatch; `REQUEST_CANDIDATES`, `STATE_CANDIDATES`, `SYNC_CANDIDATES` | 3.5, 3.7 |
| per-decision horizons (D151 (4)) | `cf_planner.HORIZONS`, and the horizon computed per decision in `plan_request` (own deadline plus the deadlines it displaces) | 3.4, 3.7 |
| two-level fidelity (D151 (4)) | `cf_cost.plan_queue` with `cf_cost.NEAR_EXACT_S` declared per kind | 3.4 |
| latest safe start, DECODE INCLUDED, re-plan on slip | `cf_cost.latest_safe_start`, `cf_cost.replan_on_slip`, consuming `ServicePrediction.total_s` | 3.2, 3.3 |
| objective: expected correct BY THE DEADLINE, harm to others included | `cf_objective.option_value`, `cf_objective.harm_to_others` | 3.6 |
| per-device deficit weighting | `cf_objective.DeficitCounters` | 3.6, section 4 |
| base `hybrid-F-lhreq-noc3` executed by default, deviate only beyond the margin | `cf_planner.base_request_choice`, and the margin gate in each `plan_*` | 3.5, 3.8 |
| `MARGIN_CF` from ONE declared constant | `cf_margin.MARGIN_CF`, read only by `cf_margin.resolve_margin` | 3.1 |
| planner-timeout-to-base fallback with a counter | the `Timing.over_budget` checks at candidate boundaries; `counts["timeout_fallback"]` | 3.8 |
| per-decision wall clock, FULL distribution | `cf_instrument.DecisionClock` | section 5 |
| the counterfactual maximises the SAME objective as the readers | `cf_objective` is the single implementation and `plan_state` reproduces reader 2's gain expression exactly | 3.6, 3.7 |

---

## 2. Mechanism verification (CLAUDE.md), recorded for the build

There is no sweep here, so this is the protocol applied to the mechanism the engine itself is: a
planner whose decisions must be shown to be driven by the quantities it claims to read.

**Step 0, what would make this run uninterpretable, asked before starting.** Four answers, two of
which changed what was built.

1. *Is the comparator about to change?* Yes, and it already had: D154 (3) moves the base to
   `hybrid-F-lhreq-noc3`, so the base surrogate was written with C3 off from the start rather than
   with a switch.
2. *Is a constant about to be set?* `MARGIN_CF` is the subject of an open ruling (G8). Setting it
   to anything, including the 0.05 placeholder that exists in `value_readers.py`, would have made
   every proof below a tuned result. The constant was left unset and the scorable path was made to
   raise. **This cost nothing and removed the only way this build could have produced an
   unreportable number.**
3. *Does a run I depend on key into my analysis?* Yes: the residual distribution is of the
   committed gate's model, and the gate's own `cost_model_gate.json` predates four `_L3` cells
   committed later the same day. Including them would have made the residuals residuals of a
   different cell set from the committed gate's, with nothing to reconcile. They are excluded and
   named; see check 1.
4. *Does the mechanism have a reachable path in this regime?* For warm-ahead, NO: session C's
   section 3 records that warm-ahead is not expressible in the committed action space. So the WARM
   candidate is scored only when a caller declares it expressible and is otherwise NOT SCORED,
   which keeps a harness blocker from being read as a policy decision.

**Step 1, the causal chain.** If predicted service is representation- and placement-dependent and
delivery is charged at completion (D146), then at a 3 s deadline (D147) the decision that matters
for a robot question is WHEN its decode is charged, not only whether its prefill fits
(`study_frozen_test.md` 18.7.3, 19.5). A planner that predicts first token AND decode
(spec v5 5.2) can compute a latest safe start that is `deadline minus predicted service times a
measured safety factor`; releasing at that moment rather than at arrival changes the overlap counts
the request and everyone else experience, which changes each one's `P(on time)` through a measured
residual distribution, which changes deficit-weighted expected correct answers delivered by the
deadline (D151 (4), D152 (1) as amended by D155 (3)); the counterfactual takes that choice only when
it beats the base by `MARGIN_CF` (D151 (1)), so the policy is never worse than
`hybrid-F-lhreq-noc3` up to cost-model error.

**Step 2, each link instantiated, with the READ that consumes it.**

| causal link | implementing quantity | value or range in this build | varies as expected | the READ that changes a decision |
|---|---|---|---|---|
| service is predicted with decode | `ServicePrediction.decode_s` | 0.0031 s to 0.3651 s; decode share 0.08 to 26.4 percent | yes, with overlap | `cf_cost.latest_safe_start` consumes `total_s`; `cf_planner.plan_request` candidate 2 starts at that time |
| the latest safe start moves with decode | `LatestSafeStart.decode_omission_error_s` | 0.0049 s to 0.1953 s over the proof grid | yes | the deferral start time passed to `_score`, which changes `p_on_time` |
| release time changes delivery probability | `PendingRequest.p_on_time` via `cf_cost.p_on_time` | 0.000 at 0.2 s slack to 0.997 at 10 s, monotone | yes | `cf_objective.option_value`, whose return is the candidate's value |
| displacement harms others | `cf_objective.harm_to_others` | non-zero in 118 of 56 decisions' rows on the Step 2b grid (multiple rows per decision); total 0.0127 flat, 0.0159 deficit-weighted on the proof cell | yes, and it changes with the weights | each candidate's `value = gain - harm` in `plan_request` |
| deficit weighting prioritises devices | `DeficitCounters.weight` | 1.000 for a device at target, 1.400 at a 0.4 shortfall | yes | the `w_j` inside `harm_to_others`, and `w_i` on the own-gain term |
| value decides representation | the committed DEV accuracy table | D2 0.250, RECENT 0.107143, device 0.071429 | yes | `option_value`'s `acc_cloud`, and the flat-table control moves 52 of 56 decisions |
| the margin gates the deviation | `cf_margin.MARGIN_CF` | **UNSET**; the scorable read raises | n/a | `plan_*`'s `delta > m.value` test; at an enormous margin deviations fall to 0 of 56 |

No link is zero, constant or write-only, with **two documented exceptions that are stopping
conditions for the claims they would support, and only for those**:

- **`P(device on time)` is CONSTANT at 1.0.** D155 (3) makes a device answer count only if it
  arrives by the deadline, and the only committed device-answer latency is
  `DEVICE_WAIT_RULE_S = 0.567` (labelled `proxy-0.567`, D154 (5)), while D155 (1) forbids wiring the
  StudyORIN-REC part 1 cold re-send latencies. 0.567 s is inside every robot deadline under test, so
  the restriction is live on the cloud side and **inert on the device side**. It is implemented and
  read so the measured warm per-question latencies can be dropped in without touching a decision
  path. **No v5 claim may rest on trading the device's delivery risk against the cloud's until they
  land.**
- **The deficit weight provably cannot change a within-device choice**, and that is a geometry fact,
  not a defect; section 4.

**Step 2b, the switch reaches a decision.** The counterfactual against the base it replaces, on the
same 56 declared decisions (7 history sizes x 4 queue depths x 2 readiness states), DRY at margin 0:

| | ADMIT_NOW_D2 | DEFER_TO_LATEST_SAFE_START | DEVICE_ANSWERS |
|---|---|---|---|
| base `hybrid-F-lhreq-noc3` surrogate | 48 | 0 | 8 |
| counterfactual | 40 | **12** | 4 |

**38 of 56 decisions differ.** The first difference is at 467 history tokens, 6 other requests in
flight, COLD: the base admits now, the counterfactual defers to its latest safe start, delta
+0.012671. The base can never choose a deferral to a latest safe start because it has no such
concept, so the deferral count is also the port-rule check: **the counterfactual's characteristic
decision occurs 12 times on the grid and 276 times in the 32-device latency load**, never zero.

**Step 3, one traced unit.** From `cf_unit_proofs.json::traced_unit`, readable by hand:

```
UNIT: one robot question, robo005, history 7,051 tokens (committed seed-4 trace value),
      deadline 3.0 s (D147), readiness COLD, 6 other robot requests in flight at t=0.
deficit: served 10, on time 7, rate 0.700, target 0.900, shortfall 0.200, w = 1 + 1.0 x 0.200 = 1.200
accuracy (committed DEV): D2 0.250000, RECENT 0.107143, device 0.071429
safety factor 1.577541 (p90 of held-out actual/predicted service, floored at 1.0)
predicted service 1.616062 s, of which decode 0.093607
latest safe start = 3.0 - 1.577541 x 1.616062 = 0.450597 s
prefill-only latest safe start would be 0.598266 s: an error of 0.147669 s in the planner's favour
  ADMIT_NOW_D2                value 0.272675  gain 0.291069  harm 0.018394  scored
  DEFER_TO_LATEST_SAFE_START  value 0.272027  gain 0.284716  harm 0.012689  scored
  SEND_RECENT                 value 0.115840  gain 0.128529  harm 0.012689  NOT scored (D155 (4))
  DEVICE_ANSWERS              value 0.085715  gain 0.085715  harm 0.000000  scored
base: prefill-only estimate 1.566889 s against slack 3.000000 s -> ADMIT_NOW_D2
counterfactual argmax ADMIT_NOW_D2, delta 0.0, margin 0.0 (DRY_OVERRIDE), chosen ADMIT_NOW_D2
binding constraint: the DEADLINE through P(on time). No KV cap and no accelerator ms are charged
here: this module decides and does not execute, and that accounting stays with the harness.
outcome register: PREDICTED values. There is no both_met / latency_miss because nothing ran.
```

**Step 4, negative controls**, each disabling one mechanism on the same 56 decisions:

| control | decisions changed | reading |
|---|---|---|
| decode zeroed | 8 of 56 | decode drives decisions; zeroing it is not a no-op |
| flat accuracy table (all 0.25) | **52 of 56** | value is load-bearing in the counterfactual, which is what D149 (4) asks for and what the in-arm test at C3's fallback slot could not show |
| no displacement (empty queue) | 12 of 56 | harm to others drives decisions |
| deficit weighting flattened (gain 0) | **0 of 56** | **the correct result, and it is predicted in advance**: every decision on this grid is for one device, and section 4 proves the weight cannot move a within-device argmax. The weighting is controlled cross-device in the harm rows instead (0.0127 against 0.0159) |
| margin enormous | 0 deviations, every choice equals base | the never-worse-than-base property, stated as a control |
| **positive control** | committed by-arm coefficients and request count reproduce exactly (345,066) | the check is sound, so the controls above may be read |

**Step 5, the alternative explanation.** When v5 does run, "v5 beats `hybrid-F-lhreq-noc3` on
correct answers delivered" is also produced by **pure timing**: the deferral putting answers into
quieter decode windows, which is what 18.7.3 already credits hybrid-F's advantage to and is not a
value mechanism. This build cannot distinguish them, because it produces no outcomes. What it does
do is make the distinguishing data recordable: the deferral count, the representation mix, and the
per-candidate value rows are all in the decision log, so the test spec v5 section 13 Step 5 asks for
(does the RECENT count fall toward zero while D2 on-time answers rise, or does the mix stay fixed
while the count rises) can be run without new instrumentation. **A second alternative is specific to
this build and is sharper**: the deferral could be winning on the gate's *errors* rather than on
decode, since the gate over-predicts decode by 25 to 32 percent and understates its convex tail. A
planner that defers because its model is wrong in a helpful direction looks exactly like one that
defers because decode is real. **Only the gate passing separates those two, which is another reason
section 12's ordering is not negotiable.**

---

## 3. The components, one by one, with their unit proofs

All numbers from `results/orchestration/live2/v5/cf_unit_proofs.json`.

### 3.1 The margin: one declared constant, unset, and it refuses

`cf_margin.MARGIN_CF = None`, and `resolve_margin()` is the only read in `cf_*`. It raises
`MarginUnset` with D154 (2)'s rule as its message. No `cf_*` function takes a margin argument on a
scorable path; the dry path requires an explicit value and marks every decision `scorable: false`.

`margin_declaration_audit()` greps the tree: **one declaration in `cf_margin.py`, and one conflict**
at `experiments/orchestration/live2/v5/value_readers.py:65`, `MARGIN_CF = 0.05`, a pre-D154
placeholder. `cf_*` never imports it. That file is not this session's; the conflict is reported in
section 8 and must be removed or deferred to `cf_margin` by its owner, otherwise "never tuned" stops
being checkable from the code the moment someone imports the other one.

**A second reason the margin cannot be set even by a gate that passes, which I believe is new.**
D154 (2) defines it as the gate's held-out p90 absolute prediction error **in the objective's
units**. The gate's error is in SECONDS (0.1817 s at p90, measured here); the objective is in
expected correct answers delivered by the deadline. **No committed rule converts one into the
other**, and the only defensible route (push the service error through the delivery-probability
curve and the accuracy table) makes the answer a function of which question population you push it
through: 0.18 s is worth nearly nothing at 2 s of slack and nearly the whole accuracy gap at the
edge. `cf_cost.service_error_to_objective_units` computes the seconds and **refuses to return the
objective-unit number**. Choosing the population after seeing the gate's ratios is exactly the
fitting D151 (1) forbids, so this needs a user ruling that names the population first.

### 3.2 Predicted service, with decode

From the committed `cost_model_gate.json`, **held out BY ARM** (fit on the non-hybrids, test on the
hybrids), because v5 is a policy no fitted arm produced and section 12 names that split as the one
that matters:

```
first_token = -0.022972 + 1.80598e-4 x uncached_tokens + 0.038005 x overlap_ft
decode      =  0.003098 + 0.015085 x overlap_decode
total       =  first_token + decode + 0.044 s link (live2/traces.py::RTT_MS)
```

Over the proof grid (5 history sizes x 4 overlap counts): decode 0.0031 to 0.3651 s, **non-zero
everywhere and varying**; decode share of predicted service 0.08 to 26.4 percent. The prefill-only
figure is still computed, as `total_prefill_only_s`, for one purpose only: so the proofs can show
what omitting decode costs. **Nothing in the planner reads it.**

### 3.3 The latest safe start, and the safety factor nobody chose

`latest_start = deadline - safety x predicted_service`, with the safety factor **derived, not
chosen**: the p90 of (actual engine service / predicted engine service) on the held-out-by-arm
split, floored at 1.0. Measured: **1.5775**. It is widened by construction while the gate fails,
because the gate's own residual spread is what sets it, which is what spec v5 5.2 asks for.

Omitting decode would move the latest safe start **later** by 0.0049 to 0.1953 s over the proof grid,
always in the planner's favour, which is the one-sided error 5.2 warns about. In token terms at 3 s,
the largest history still feasible is 10,396 tokens with decode and 10,413 without at zero overlap,
and 8,044 against 8,730 at eight overlaps. See check 1 for the reconciliation with spec v5 5.2's
"about 1,700 tokens".

`replan_on_slip` is the same function on new inputs and reports whether the deferral the planner was
holding has been overtaken by the clock (D151 (3)'s re-plan on slip).

### 3.4 Two-level fidelity

`NEAR_EXACT_S` is declared per decision kind: `request` is the horizon the caller computed (its own
deadline plus the deadlines it displaces), `state` 3.0 s, `sync` 3.0 s. The exact level COUNTS the
overlaps each request actually experiences, solved as a fixed point by 3 declared sweeps from zero
overlap; the coarse level prices requests at an offered-load forecast (Little's law on the offered
stream).

Proof: on a 12-request queue the two levels disagree on **12 of 12** requests; the first is `r00`,
exact `p_on_time` 0.9461 at 11 counted overlaps against coarse 0.9745 at the forecast's 4. **The
exact level is not decorative**, and the direction is the one that matters: the coarse level is
optimistic.

### 3.5 The three decision kinds, and the two that are refused

`request`, `state`, `sync` are planned. `dashcam_frame` and `single_shot` are **refused** with a
`RuleBased` marker naming the rule's owner (D151 (2)), and an unknown kind raises. This refusal is
why the 20 ms budget is affordable: the counterfactual is never asked to rank 13,193 monitor
instants.

Candidate sets: request `ADMIT_NOW_D2 / DEFER_TO_LATEST_SAFE_START / SEND_RECENT / DEVICE_ANSWERS`
(four and no others, spec v5 5.1, with "reject" meaning the device answers per D152 (2)); state
`WARM / TOUCH / KEEP / RELOAD / HOLD_BACK / SLICE`; sync `QUESTION_FIRST / WAIT / LEAVE_TO_DEVICE`.

**D155 (4) is imposed, not derived, and the imposition is counted.** `SEND_RECENT` is scored and then
suppressed. Under the superseded D87 device entry (0.107143) the no-RECENT rule fell out of the
arithmetic; the measured Orin entry (0.071429) breaks that tie, so the arithmetic alone would send
RECENT above about 0.667 delivery probability. `counts["recent_suppressed_by_rule"]` records every
decision where the arithmetic would have chosen RECENT and the rule overrode it: **6 of 56** on the
Step 2b grid, **11 of 480** request decisions in the 32-device load. The rule is therefore visible
in the log rather than silently built into the candidate set.

### 3.6 The objective

```
V_i(cloud o)   = w_i x [ P(o on time) x acc(o) + (1 - P(o on time)) x P(dev on time) x acc(dev) ]
V_i(DEVICE)    = w_i x P(dev on time) x acc(dev)
objective(o)   = V_i(o) - sum over other devices j of w_j x (V_j before - V_j after)
```

The second term of the first line is the whole of D155 (3): when the cloud's answer does not arrive,
the device's does, and it counts only inside the deadline. The harm term is a **difference of two
simulated queues**, not a penalty coefficient: `plan_queue` is run without the candidate and again
with it, and every other request's delivery probability is re-predicted. On the proof cell harm is
0.012689 with flat weights and 0.015862 with three of six neighbours short of target, so the
weighting changes the harm it is supposed to change.

**`v5/value_readers.py` prices the device at `p_on_time = 1.0`**, which was right under D152 (1) and
is not right under D155 (3). That module is not this session's; see section 8.

### 3.7 State and sync decisions

State, scored by reader 2's own expression `w x p_question x accuracy x (p_warm - p_cold) - harm`:
with no harm the engine chooses WARM; with harm 0.50 on the same inputs it chooses **HOLD_BACK**,
which is D150's "above all control what enters the GPU" appearing as an option in the same
comparison rather than as a separate mechanism. With `warm_expressible` left to the module's own
answer it is False (session C section 3), the WARM and SLICE candidates are **not scored**, and the
engine falls to KEEP.

Sync: with a 3 s deadline and an 8 s catch-up the engine chooses QUESTION_FIRST; with a 14 s
deadline and a 1 s catch-up it chooses **WAIT**. Getting that second branch to exist required a
decision worth flagging: **the three sync options must differ in accuracy as well as in P(on time),
and no committed accuracy exists for a question-first answer.** Priced at the full-history accuracy,
WAIT is dominated by construction (it starts later with more tokens, so its delivery probability can
never be higher), and the sync switch would reach no decision at all. The committed cloud RECENT
figure stands in as the closest measured truncated-history analogue, and every sync decision's trace
carries `accuracy_question_first_is_a_substitution: true`. **A v5 outage number may not be read until
that accuracy is measured or ruled.** This is a new gap; it is not in spec v5 section 14.

### 3.8 The timeout fallback

The budget is checked at candidate boundaries, so a slow plan abandons rather than overrunning and
being reported afterwards. At `budget_ms = 0` the fallback fires on **20 of 20** decisions, every
chosen action equals the base's, and 0 deviations occur; at a large budget it fires 0 times. The
fallback target is `hybrid-F-lhreq-noc3` and the proof asserts it ends in `noc3`, because a timeout
that fell back to C3-on hybrid-F would silently change the representation policy as well as the
timing policy.

---

## 4. The deficit counters: how the on-time versus correctness mismatch was resolved

The brief asks for per-device deficit weighting in the objective and notes what the assessment
found: the only deficit counters in the tree are the v1 artefact at `arms_policy.py:276`, DEFAULT
OFF, with `w = 1` for every task, steering on on-time while the headline is correctness (spec gap
G14). **Nothing of that one is reused.** `cf_objective.DeficitCounters` is a fresh implementation and
does not import the policy library.

**The resolution is to locate the mismatch in exactly one factor and then prove where that factor
can and cannot act.**

1. **The counter stays on on-time, because that is what D152 (1) rules and what is observable.**
   `observe(device, on_time)` is the only update; correctness never enters it. The shortfall is
   `max(target - realised on-time rate, 0)` against the committed D133 target of 0.90 per type, and
   the weight is `w_i = 1 + gain x shortfall` with `DEFICIT_GAIN = 1.0` declared and never swept.
2. **The quantity it multiplies is expected CORRECTNESS**, from the committed accuracy table. So the
   weight says *whose* answers matter more and the accuracy table says *which answer* is worth more.
   Neither is asked to do the other's job, and no coefficient converts between them.
3. **The weight is floored at 1.0.** A device ahead of its target is not worth *less* than a correct
   answer is worth, it is simply not worth more. Letting w fall below 1 would make the objective
   trade a correct answer for a fairness statistic, which D149 (1) forbids.
4. **The geometry, which is the part a report could easily get wrong.** `w_i` is a per-device scalar,
   so inside one device's own candidate set it multiplies every candidate equally and **cannot change
   the argmax**. `weight_is_within_device_invariant` proves it at weights 1.0, 1.5, 3.0 and 10.0:
   the argmax is constant. CLAUDE.md Rule 2 calls that shape **cancelled by geometry**, and it means
   the weighting's characteristic decision is **cross-device**: the harm term of a request decision,
   warm and keep selection, shedding, and backlog order. That is why the Step 4 control on the
   weighting correctly changes 0 of 56 single-device decisions and changes the harm total from
   0.012689 to 0.015862 when neighbours are short of target.

**So the honest statement of the mismatch is narrower than G14's and also harder to escape.** The
counters cannot steer toward correctness, and in this build they cannot even steer *within* a
device's representation choice; they steer **between** devices, on an on-time signal, while the
headline is correctness. If a device is behind on on-time because its questions are long (and long
histories are exactly where RECENT used to be sent, D152 (2)), the counter will push capacity toward
the device whose correctness is hardest to buy. **That is a real and unmeasured risk of the design,
not of the implementation**, and it belongs in the v5 report as a limitation beside G14 rather than
inside it.

---

## 5. The decision-latency distribution (D151 (5)), so the budget can be judged

Per-decision wall clock on a constructed load: 480 request, 240 state and 80 sync decisions per
fleet size over development seeds 0, 4, 5 and 6, with history tokens drawn from the committed seed-4
trace's own `recall_question` values. Full distributions, all samples and per-kind splits are in
`results/orchestration/live2/v5/cf_decision_latency.json`.

| devices | n | min | p25 | p50 | p90 | p95 | **p99** | p99.9 | max | over 20 ms | under 1 microsecond |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 8 | 800 | 0.0038 | 0.0056 | 0.0613 | 0.1998 | 0.2039 | **0.2096** | 0.2378 | 0.2667 | 0 | 0 |
| 16 | 800 | 0.0038 | 0.0050 | 0.0951 | 0.2805 | 0.3155 | **0.3292** | 0.4044 | 0.6549 | 0 | 0 |
| 32 | 800 | 0.0038 | 0.0052 | 0.1322 | 0.5651 | 0.6362 | **0.6714** | 0.6630 | 0.7373 | 0 | 0 |

All in milliseconds. **p99 at 32 devices is 0.67 ms against a 20 ms budget, about 30x of headroom.**

**The shape, reported because the p99 alone would hide it.** The distribution is bimodal: 282 of 800
samples at 32 devices fall below 0.01 ms and 419 fall above 0.1 ms. That is not a short-circuit, and
the per-kind split says why: request decisions run at p99 0.650 ms (three candidate scorings, each a
queue simulation), state at 0.009 ms and sync at 0.039 ms (closed-form expressions, no queue). **No
sample is under 1 microsecond**, which is the threshold at which a decision would be a return rather
than a plan. Had only the p99 been reported, a planner that short-circuited every state decision
would have looked identical to this one.

**Where the budget would bind, reported as a measured limit rather than tuned away** (spec v5
section 10). The exact level counts overlaps pairwise, so its cost grows with the number of requests
inside the window, not with fleet size as such:

| requests in the exact window | 8 | 16 | 32 | 64 | 128 | 256 |
|---|---|---|---|---|---|---|
| p99 ms | 0.39 | 0.78 | 1.87 | 5.17 | 16.4 | 56.1 |

**Read that as an order of magnitude and not a threshold**: this is a shared CPU and 128 has been
measured both inside and outside the budget across repeats. The exact level is comfortable to a few
tens of requests in the window and is not comfortable at a few hundred; if a live cell ever exceeds
that, `NEAR_EXACT_S` for the request kind shrinks and the shrink is reported.

**Three register caveats, each of which could make this table optimistic.** It measures the planner
alone: no coordinator state rebuild (D151 (5) specifies state is rebuilt per decision, with no
per-period mirror, and that rebuild is not in these numbers); no engine and no GPU; and a
constructed load whose queue depth is the robot share of the fleet. **The budget check is therefore
NECESSARY and not SUFFICIENT**, and the 30x headroom is the reason to think it will survive the
missing terms rather than a proof that it will.

---

## 6. Results consistency check (CLAUDE.md), all seven

**1. Cross-check against committed measurements.**

| quantity | this run | prior committed | source of prior | ratio | verdict |
|---|---|---|---|---|---|
| cost-model coefficients, by-arm split | first token -0.022972 / 1.80598e-4 / 0.038005; decode 0.003098 / 0.015085 | identical to 12 decimal places | `cost_model_gate.json` | 1.000 | agree (positive control) |
| requests in the fit | 345,066 over 26 cells | 345,066 over 26 cells | same | 1.000 | agree |
| held-out warm rows | 0 | 0 in the by-arm split | same | n/a | agree, and it is G10's confounding, not a shortage |
| cloud D2 / RECENT / device accuracy (DEV) | 0.250 / 0.107143 / 0.071429 | same | `lh_req_quality.json` via `value_readers.load_dev_table` | 1.000 | agree |
| device-answer wait | 0.567 s | 0.567 s | `fleet/data_sources.py` | 1.000 | agree, labelled `proxy-0.567` |
| link RTT | 0.044 s | 0.044 s | `live2/traces.py::RTT_MS` | 1.000 | agree |
| tokens the decode omission adds at 3 s | 17 at zero overlap, 686 at eight | "about 1,700" | spec v5 5.2, from `study_frozen_test.md` 19.3 | up to 2.5x | **investigated, reconciled, see below** |

**The 1,700-token reconciliation.** The omission shift is monotone in concurrency, so the two
figures are the same quantity at different loads, not a disagreement. This model's shift reaches
1,687 tokens at 20 concurrent requests and 1,854 at 22, and 19.3's figure is measured on the ACTUAL
MISSES, which are the loaded instants. The quiet rows are smaller **because the gate's decode term
is linear in overlap and therefore understates the convex tail the gate report itself measures**
(0.024 s at 0 to 3 overlaps rising to 1.403 s above 45). **That understatement biases the planner
toward deferring too late, which is the error direction spec v5 5.2 exists to prevent**, and it is
the second reason (after the 25 to 32 percent decode over-prediction) that nothing here may run
before the gate passes. The curve is in
`cf_unit_proofs.json::cost_and_latest_safe_start.reconciliation_with_spec_5_2`.

**2. Physical plausibility.** The first-token coefficient 1.80598e-4 s per uncached token implies
**5,537 tok/s**, against committed A6000 cold prefill of about 7,100 tok/s and `costs.py`'s
4,500 to 3,800 tok/s for 11k and 28k recalls. It is inside that range and **slower** than the
fastest committed curve, so it is not a caching artefact. The residual ratio p50 is 1.031, that is
actual service about 3 percent above predicted at the median, with p90 1.578 and p99 3.683: a
long right tail, which is what a queueing system looks like, and no rate anywhere implies service
faster than the committed curves. **Caching:** nothing here measures a model, so no prefix-cache
condition applies to the planner's own numbers; the residuals inherit the committed runs' own
conditions, in which the engine's `prefix_cache_hits` are zero for b7 and the hybrids and hundreds
of thousands for edf and llf, which is G10 and is why the warm side is unidentified.

**3. Distribution sanity.** Every median in section 5 is reported with min, p25, p90, p95, p99,
p99.9 and max, and the full sample arrays are in the artefact. The three fleet sizes do NOT agree to
excessive precision (p50 0.061 / 0.095 / 0.132 ms). The bimodality is explained by the per-kind
split rather than left as a curiosity, and the under-1-microsecond count is 0 at every size, which
is the short-circuit check. On the residuals: the ratio distribution is reported at p50, p90 and p99
rather than as a mean, and the absolute error at p50 0.0625 s, p90 0.1817 s, p99 1.3626 s, a 22x
spread that a mean would have hidden.

**4. Definition audit.** Every named object used here, with the definition used and its source:
`win-10` and `sum-200` are not used at all (this module decides placement and timing, not
representation formats beyond D2 and RECENT); `RECENT` is 467 tokens, `live2`'s committed
`RECENT_WINDOW_TOKENS` as `hybrid_arm.py:70` names it; a `request` is one cloud request as
`request.jsonl` logs it, with `first_token_s = t_first_token - t_submit` and
`decode_s = t_done - t_first_token`, which is `cost_model_gate.features`' own definition;
`service` is first token plus decode, and `total` adds the 0.044 s link, with the two kept apart in
code (`engine_s` against `total_s`) because the residuals are fitted on the former only; `on time`
is delivery by the question's own deadline under D146 completion delivery; the robot deadline is
3.0 s (D147) and the dashcam 1.0 s (D71, D154 (1)); `EP-G` is the append-only episode, mean 14.80
frames, and this module reads the frame list from the record and never reconstructs it. **One name
is used in two senses across the tree and is flagged rather than reconciled: `MARGIN_CF`**, 0.05 in
`value_readers.py` and unset in `cf_margin.py`.

**5. Claim linkage.** The build bears on D151 (1) to (5) directly, which spec v5 section 16 traces
to sections 4, 5 and 10. It supports nothing yet, because it produces no outcome: it makes the
D151 (5) budget **checkable** (the assessment records that no instrument existed), it makes the
D149 (4) acceptance test **able to discriminate** by placing the value comparison at admission over
the full candidate set rather than in C3's fallback slot (G11's known remedy), and it makes
D154 (2)'s margin **enforceable** rather than documented. Nothing here measures an object
FORMULATION.md scopes out: no KV is moved between tiers, no external KV store is assumed, and no
cross-architecture transfer is priced.

**6. Proxy validity.** Three proxies, declared:

- **`P(on time)` from the gate's held-out residual ratio.** It measures how far actual service ran
  from predicted service on committed `dashcam-1f` requests, almost all COLD. It is used as the
  delivery probability for a workload (EP-G) and a regime (warm) it does not cover. **Valid for
  wiring and for relative comparisons inside this build; NOT valid for a headline**, and the
  residual file says so in its own `_limitations`.
- **`DEVICE_WAIT_RULE_S = 0.567` as the device answer's latency.** It measures a cascade arm's fixed
  wait, not the Orin's measured per-question latency. Labelled `proxy-0.567` per D154 (5), and the
  consequence is the CONSTANT device term in Step 2.
- **cloud RECENT accuracy as the accuracy of a question-first answer.** A truncated history is not a
  RECENT window. Declared in every sync trace; **marks every sync result unvalidated**.

**7. Validate the control, not only the result.** The positive control is in section 2's Step 4
table: the residual summary refits the gate's model from the committed logs and must reproduce
`cost_model_gate.json`'s coefficients and its 345,066 request count exactly. It does, to 12 decimal
places. Had it not, the check would have been broken rather than the model, and nothing downstream
of it could be read. The base arm is the other side that needs auditing, and **it is not audited**:
`base_request_choice` is a surrogate written from the committed source, and its agreement with the
real `hybrid_arm` on real observations is not proved here. See section 8.

---

## 7. What in D151 could not be built, classified under Rule 2

| piece | status | Rule 2 class | why |
|---|---|---|---|
| the WARM and SLICE candidates of a state decision | built, scored only when a caller declares expressibility; the module's own answer is False | **unexpressible** | warm-ahead is not expressible in the committed action space (session C section 3): `validate_action` accepts MATERIALIZE only for a session already warm or holding a pending query, so the first warm-ahead for every session is rejected for ever. Scoring it anyway would read a harness blocker as a policy decision |
| RELOAD | built, counts its own firings, never fires | **unexercised** | across 39 committed 16-device cells the believed tier is cold 14,472, gpu 1,442, host NEVER. Zero reloads reports the state of the fleet, not a mechanism that failed |
| the deficit weight inside one request's candidate set | built and proved inert there | **cancelled by geometry** | a per-device scalar cannot move a within-device argmax; it acts cross-device, where it is controlled |
| D155 (3) on the DEVICE side | built, read, CONSTANT at 1.0 | **unexercised** | the only committed device latency is 0.567 s, inside every deadline under test; D155 (1) forbids the cold re-send numbers. The condition the amendment is about is never reached |
| any v5 outcome, including the never-worse-than-base property | **not built and must not be** | not a null | `MARGIN_CF` is unset (G8) and the gate fails (G10). Spec v5 12.1 forbids the cell |
| accuracy by history-length band | not built, none invented | n/a | G4, blocked on P19. History length enters only through `P(on time)` |
| the accuracy of a question-first answer | **missing, substituted** | n/a, a new gap | section 3.7 |
| the residency belief corrector | not mine | n/a | G9, session C owns it; the counterfactual consumes `cached_tokens` as an input to `predict` and makes no belief of its own |

**One thing I deliberately did not build.** The counterfactual does not charge KV bytes or
accelerator milliseconds, because it decides and does not execute; that accounting is the harness's.
A reader checking Step 3 against CLAUDE.md's template will notice the traced unit has no KV line for
that reason, and the trace says so at the point of use rather than leaving a blank.

---

## 8. What this needs from the sessions that own other files

Each item is a file this session does not own, with what is wrong and why it matters.

1. **`v5/value_readers.py:65`, `MARGIN_CF = 0.05`.** A pre-D154 placeholder, and a second
   declaration of the one constant whose whole purpose is to be single. `cf_*` never imports it.
   **Remove it or make it `from cf_margin import MARGIN_CF`**, otherwise "never tuned" stops being
   checkable the first time anyone imports the other one.
2. **`v5/value_readers.py`, the device option priced at `p_on_time = 1.0`.** Correct under
   D152 (1), wrong under D155 (3): a device answer now counts only inside the deadline. The reader's
   grid and its `step2b_switch_diff` are computed with the device as a free incumbent.
3. **`hybrid/hybrid_arm.py`: the base surrogate needs auditing against the real arm.** CLAUDE.md
   check 7 is explicit that an unaudited side of a comparison is the blindness arm-versus-arm
   checking cannot see. `cf_planner.base_request_choice` must be diffed against
   `hybrid-F-lhreq-noc3`'s own decisions on one committed cell, with the count of differing
   decisions reported, before any v5 cell is scored. **If they differ, the never-worse-than-base
   property is being measured against the wrong base.**
4. **`engine_actions.py`: `_warm_expressible` is a stub that answers False.** When an observation is
   available the planner should call `plan_warm_ahead` and read `n_warm_ahead` AND `unexpressible`
   together, as the interface note's point 1 requires. The hook is one function.
5. **`research/EXPERIMENTS.md`, `results/INDEX.md`, `research/STATUS.md`:** G5's E-id, and rows for
   the three artefacts here. Draft rows in section 9.
6. **A user ruling is needed on two things before v5 runs**, and neither is a measurement: the
   population `MARGIN_CF`'s p90 error is expressed over (section 3.1), and the accuracy of a
   question-first answer (section 3.7).

---

## 9. Draft rows for the files this session does not own

**`research/EXPERIMENTS.md`** (G5; the E-id itself is for the owner to allocate):

```
| StudyV5-CF | policy v5 counterfactual engine: three decision kinds, per-decision horizons,
two-level fidelity, latest safe start with decode, deficit-weighted by-deadline objective with harm
to others, single declared MARGIN_CF, timeout fallback, per-decision wall-clock instrument |
experiments/orchestration/live2/v5/cf_*.py | results/orchestration/live2/v5/cf_unit_proofs.json,
cf_decision_latency.json, cf_service_residuals.json | BUILT, DRY-PROVED, NOT RUN: no scored cell,
MARGIN_CF unset (G8) and the D151 (6) gate fails (G10) | mechanism_verification: Steps 0 to 5
recorded in reports/study_counterfactual.md section 2; Step 2b 38 of 56 decisions differ |
consistency_check: all seven, section 6; one >2x cross-check investigated and reconciled |
```

**`results/INDEX.md`:**

```
cf_service_residuals.json | cf_proofs.py --build-residuals | n/a | cpu | 345,066 | the committed
gate model's held-out residual ratio: p50 1.031, p90 1.578, p99 3.683; p90 absolute service error
0.1817 s; 0 warm rows held out (G10) | new
cf_unit_proofs.json | cf_proofs.py | n/a | cpu | 56 | every component unit proof: decode non-zero
and varying, two levels disagree 12 of 12, Step 2b 38 of 56, four negative controls plus a positive
control | new
cf_decision_latency.json | cf_proofs.py | n/a | cpu | 2,400 | planner p99 0.21 / 0.33 / 0.67 ms at
8 / 16 / 32 devices against D151 (5)'s 20 ms; full distributions; exact level binds between 128 and
256 requests in the window | new
```

**`research/STATUS.md`:** last-updated 2026-11-20, and the v5 line should say the counterfactual is
built and dry-proved while v5 remains blocked on G8 and G10.

---

## 10. How to reproduce every number in this report

```
git fetch origin && git worktree add --detach /tmp/sessB origin/main && cd /tmp/sessB
python3 -I experiments/orchestration/live2/v5/cf_proofs.py --build-residuals   # about 5 s
python3 -I experiments/orchestration/live2/v5/cf_proofs.py                     # about 6 s
python3 -I experiments/orchestration/live2/v5/cf_margin.py                     # the margin audit
```

Each module also runs standalone (`cf_cost.py` prints the committed model, `cf_objective.py` the
counters, `cf_instrument.py` a self test, `cf_planner.py` the candidate sets). The wall-clock
numbers are machine-dependent by nature; everything else is deterministic, and the residual build
reads committed logs only. CPU only throughout: nothing in this session touched a GPU, the H100 or
the Orin, and only development seeds 0, 4, 5 and 6 appear anywhere.

---

## 11. Addendum: D156 and D156a, which landed on origin during this session's push

Both were read after the artefacts above were produced, so this section is a reconciliation and
nothing above was changed to fit it.

**D156 confirms the refusal this build enforces, and narrows what it blocks.** The D151 (6)
cost-model gate applies to **counterfactual decisions only**, and a rules-only `v5-rules` (base
`hybrid-F-lhreq-noc3` plus warm-ahead as a RULE, plus EP-G, plus per-frame upload) makes no
counterfactual predictions and therefore needs no gate pass. Two consequences for this deliverable:

1. **`cf_margin`'s refusal is in exactly the right place.** Everything in `cf_*` is a counterfactual
   decision, so the gate and `MARGIN_CF` gate all of it, and `v5-rules` is unaffected by anything
   here. The claim "no v5 cell may run" in section 0 should be read as **no full-v5 (counterfactual)
   cell**; `v5-rules` cells are a different labelled version and are not blocked by G8 or G10.
2. **This build is not on `v5-rules`' critical path.** `v5-rules` needs warm-ahead expressible as a
   rule in `engine_actions.py` (session C), not the counterfactual. The one thing it should borrow
   from here is `cf_instrument.DecisionClock`, if a per-decision wall clock is wanted for the rules
   arm as well; it has no dependency on `cf_margin`, `cf_cost` or `cf_planner`.

**D156a (the EP-G budget charge, assessed and deferred) does not touch this module and lines up with
it.** `cf_*` charges no accelerator budget at all (section 7), so the deferral changes nothing here.
Where the two meet is the charge rule: D156a charges an episode's NEW tokens, trued up at completion
from the engine-reported `cached_tokens` so that what is charged is the uncached tokens actually
computed. `cf_cost.predict` already prices service on `max(tokens - cached_tokens, 0)`, which is the
same quantity, so when the true-up lands the planner's cost basis and the harness's charge basis
will agree by construction rather than by coincidence. **If the true-up changes what every arm can
spend, as D156a says it does, then the residual distribution in `cf_service_residuals.json` is
fitted on pre-true-up cells and must be rebuilt with the EP-G refit**, which is the same rebuild
D153 already requires. That is one rebuild, not two.
