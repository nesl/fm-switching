# D245 ESTIMATE: wiring the D162 queued-ahead term into the state planner's pricing

**ESTIMATE ONLY, per user ruling D245 (2026-11-25 07:08, provisional). NOTHING BUILT, NOTHING APPLIED.**
Every figure below was verified against origin/main at the point of use, not carried from the report that
produced it.

## *** THE HEADLINE: THIS WORK HAS ALREADY BEEN DONE ONCE AND MEASURED ZERO DIFFERING DECISIONS ***

`research/study_fix102_prepared.md` is the prepared fix for freeze-gate row 10.2 **at exactly the three
sites D245 names**, built in a scratch tree and never applied. **Its Step 2b result, quoted from line 35:**
```
rows 14539 both sides   positional_differing 0   setwise_differing 0
digest before 5a03c2807da3681a = digest after    state_action 2954 both sides
```
**And its own verdict, line 85: "Row 10.2 does NOT close by this fix. Applying it leaves the row where it
is and buys nothing measurable."**
**The diagnosis is that the defect is not a wrong value in a right expression but the WRONG ROW SOURCE:
`obs.recall` is the arrived-and-UNDECIDED set and the arm decides every 0.1 s, so it structurally cannot
hold two items. Instrumented: 61,034 calls to `_queued_behind`, 10,606 cache refills, `npend_hist = {0:
10,181, 1: 425}`, never 2 or more. The queue term is zero in 10,606 of 10,606.**
*** SO THE LITERAL RULING IS A MEASURED ABSENT LINK, AND THE ESTIMATE MUST BE GIVEN IN TWO SCOPES. ***

## The estimate

| scope | what | hours | recommendation |
|---|---|---|---|
| **A** | the literal ruling at `:273`, `:274`, `:312` with the EXISTING row source | **4 to 6** | *** DO NOT BUILD. Already measured as a null. *** |
| **B** | a real in-flight row source published into `Observation` | **38 to 64**, about 2.5 to 4 session-days | **plus a 2 to 3 hour Step 0 / Step 2b reachability gate FIRST, which may stop the build** |

**Scope B files: `arms_v6state.py` (row source, `_p_warm_cold` signature, the three call sites),
`cstate.py` (publish a per-class in-flight TOKEN register; `kv_capacity_enforced` for the control),
`baselines/interface.py` (a new `CloudState` field plus the `scrub` / `FORBIDDEN_FIELDS` pass),
`coordinator.py` (expose `self._w` read-only), optionally `v5/cf_cost.py`, `v5/cf_planner.py`,
`v5/cf_objective.py`, a new proof driver, and the usual `research/` and `results/INDEX.md` records.**
**The correct quantity EXISTS and is live, but only inside the coordinator and never in the `Observation`
the arm sees: `coordinator.py:349` `self._w = SA.WTracker()` is submit-to-first-token uncached tokens,
which is the fit's own regressor. `self._uncached_in_flight` is the WRONG register: it drains at
COMPLETION and so includes decode, overstating the queue (`coordinator.py:1146`).**

**Twelve proofs are required and are named in full in the agent record. The three that decide the outcome:**
**Step 2b** (a non-zero differing-decision count with the first differing decision shown) **is the one
Scope A has already failed**; **a unit guard that fails loud** unless `per_queue_token` is the coefficient
applied; and **check 7, validating the control arm**, which already found the control disagreeing with
itself (`state_chosen_HOLD_BACK` is 0 in the dry replay against 2 in the committed cell, so the two
decisions where `harm_warm` was decisive were not exercised).

## The two freeze-gate rows

**ROW 10.2: PARTLY closes, and only under Scope B with a non-zero Step 2b.** The row offers two closures:
real queued-ahead work at the three sites, **or a D-row recording that rung 3's state planner prices
without a queue term.** **On the measured evidence the second is cheaper and more honest, and the prepared
file says so at line 60.**
*** ROW 10.16: DOES NOT CLOSE. Stated plainly because the ruling appears to expect it to. *** 10.16's
carried gap is about the **MODEL**, not the queue argument: `v5/cf_planner.py:367` loads
`CC.load_gate_model()`, whose own `GATE_STATUS` reads "FAILS (spec v5 section 12): decode over-predicts by
25 to 32 percent in every held-out class". **Wiring a queue term leaves `plan_state` on that failed model.**
Routing it through `predict_d162` would close the gap but re-bases every committed rung-2 and rung-3 cell;
**add 8 to 14 hours and a full comparator re-run, and it needs a ruling D228 (1) deliberately withheld.**

## *** PACING AGAINST DASHCAM HARM: NO, AND THE CURRENT STATE FITS NONE OF THE THREE LABELS CLEANLY ***

| part | state |
|---|---|
| the channel it would act through | **EXISTS and is ENACTED** (`arms_v6state.py:477-489`: `KEEP_GPU_WARM`, or `drop.add(sid)` removing the `MATERIALIZE`). **So NOT `unexpressible`.** |
| the objective that scores it | **EXISTS and is loudly sensitive** (`score.py:762-780`, `:826`, the 0.90 dashcam bar). **So NOT `unscorable`.** |
| the SIGNAL the planner reads | *** DOES NOT EXIST. `obs.recall` is built from RECALL OPPORTUNITIES ONLY; no dashcam row of the required shape (`device_id`, `engine_s`, `slack_s`) is constructible from `Observation` at all. `EpisodicStream` carries no deadline, no token count, no slack. *** |
**So the correct classification is a Step 2 ABSENT LINK ON THE INPUT SIDE. The nearest taxonomy label is
`unexercised` and it is a POOR FIT, because `unexercised` means reachable but not reached, and this is not
reachable at any condition.** **Calling it `unexpressible` or `unscorable` would both be wrong, in opposite
directions.**
**Scope A does not move it. Scope B is NECESSARY BUT NOT SUFFICIENT: two further blockers remain, neither in
the ruling.** **(i) THE CURRENCY: `option_value` returns "expected ON-TIME CLOUD ANSWERS", and a delayed
dashcam instant is not a cloud answer in that unit. (ii) THE WEIGHT: `PlannerDeficitWeights.weight`
resolves the device of the ROW, and rows are robot recall rows, so dashcam devices never get one.**

## *** THE FINDING THAT SHOULD CHANGE HOW THIS IS READ: THE HARD ZERO IS LOAD-BEARING ***

**`study_fix102_prepared.md:87-91`: "the 247x unit error is latent ONLY because `overlap_ft` is the hard
zero. It becomes ACTIVE on the first commit that honours row 10.2 ... the zero is currently
load-bearing."** **`predict`'s `overlap_ft` meets `per_overlap = 0.0380048 s per REQUEST`, while D162's
coefficient is `per_queue_token = 0.0001535807289339 s per TOKEN: a verified 247.5x difference in a
different unit.** **Passing a token count into that argument predicted 165.6 s against 0.818 s observed.**
**So "fix the hard zero" is NOT a safe default.**

**AND THE SIGN RUNS OPPOSITE TO THE STORY.** `harm_warm` **DECREASES** as overlap rises, because a request
already predicted slow has less `p_on_time` left to lose. **So honouring the queue term makes `HOLD_BACK`
cheaper to refuse and TOUCH MORE attractive, not less** - and more touching is exactly what D236 measured
costing **383 dashcam on-time instants** (6,781 against 6,398).
*** THE MISPRICING, VERIFIED: the planner prices a touch at 0.0001535807289339 x 15 = 2.30 MILLISECONDS of
harm to others, while the scorer measured touching costing 383 dashcam on-time instants. ***
**"The queue term improved the policy" and "the queue term loosened the harm bar and bought robot answers
by spending dashcam" make the SAME prediction on every population metric. The distinguishing data is
`dashcam_per_device` on-time reported BESIDE `robot_pool_on_time`, per device, never a single headline.**

## *** A BLOCKING STOP CONDITION: `research/FORMULATION.md` IS SILENT, SO CLAUDE.md STEP 1 CANNOT BE WRITTEN ***

**Verified directly: FORMULATION.md is 271 lines and a case-insensitive search returns ZERO hits for
`queue`, `queued`, `in-flight`, `contention`, `concurren`, `backlog` and `interference`.** Its `## Scoping`
section scopes out three things and none is this; its cost vocabulary is transfer / materialize / refresh /
Q(f, w) with a ready-capacity constraint, **with no queueing or contention term at all.**
**CLAUDE.md Step 1 requires every link traced to a specific claim in FORMULATION.md and says to stop and
ask if that cannot be done. It cannot be done here.** The de facto authorities are
`research/prereg_cost_model_gate_d162.md:55-61`, `reports/prereg_queue_register_r2.md:16-30` and
`research/policy_spec_v6.md:273`. *** A RULING ON WHICH DOCUMENT IS THE AUTHORITY IS NEEDED BEFORE ANY
BUILD, AND THIS IS A STOP CONDITION RATHER THAN A CAVEAT. ***

## Also not determined, and not inferred

- **No E-id exists for this work.** CLAUDE.md requires one before any task.
- **Whether a LIVE cell would also show 0 differing decisions is NOT established.** The dry replay bounds
  nothing about live, and `state_chosen_HOLD_BACK` is 0 in replay against 2 in the committed cell, so the
  two decisions where `harm_warm` was decisive were not exercised. **Those 2 decisions are the whole
  remaining uncertainty on the Scope A null.**
- **The kv0.5r differing-decision count is NOT established**, because the harness that would measure it is
  KV-blind (`cstate.py:474` defaults `kv_capacity_enforced = False` and `test_hybrid.dry` never sets it,
  while both committed cells carry `True`; a control at GPU_KV = 2,000, one thirty-first of 1x, gave an
  IDENTICAL digest).
- **Whether a new `CloudState` field disturbs the baselines' fairness digest was NOT tested.** It looks
  legal, since `FORBIDDEN_FIELDS` guards future knowledge and an in-flight count is present-time, but the
  38-configuration fairness suite was not run and no claim is made.
