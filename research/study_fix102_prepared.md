# Freeze-gate row 10.2: the hard-zero queue term, PREPARED NOT APPLIED

**Status: PREPARED IN A SCRATCH TREE. NOTHING APPLIED, NOTHING PUSHED to `experiments/`.** The file this
would change is in the freeze candidate, so changing it is the user's ruling. Read-only against a pinned
`origin/main`; the stale working tree was never read.

## 1. The defect is confirmed, and the read is LIVE

```
arms_v6state.py:273   warm = CC.predict(cf.model, int(est_tokens), int(built_tokens), 0, 0)
arms_v6state.py:274   cold = CC.predict(cf.model, int(est_tokens), 0, 0, 0)
arms_v6state.py:312   pr   = CC.predict(cf.model, tok, 0, 0, 0)
v5/cf_cost.py:182-184 def predict(model, tokens, cached_tokens=0, overlap_ft=0, overlap_decode=0, link_s=...)
```
The two trailing zeros at each site **are** `overlap_ft` and `overlap_decode`. `predict` multiplies them by
`per_overlap` (`cf_cost.py:188-190`), so **every prediction is of an empty engine.**

**The READ that changes a decision, traced end to end rather than asserted:** `:312` to `:316`
`engine_s` to `:321` to `_harm_warm:330` to `:339` `harm_warm_from_queue_delay` to
`v5/cf_objective.py:845,848,849` to `h.total` to `arms_v6state.py:355` to `:443/:445` to
`v5/cf_planner.py:660,686,697-700,710-719` where those values **are the candidates argmaxed**, to
`d.chosen`, to `arms_v6state.py:477-485` which emits `KEEP_GPU_WARM` or drops a MATERIALIZE ask. **So this
is not a `desired_tier`-shaped write-only field.**
**Probe-can-fire, measured by hand at overlap 0/1/2/5:** `engine_s` 1.253524 / 1.306614 / 1.359704 /
1.518972; `harm_warm` 0.3734 / 0.3156 / 0.2614 / 0.1408; **chosen = KEEP / KEEP / KEEP / SLICE.** A non-zero
queue term does reach and flip the decision.
*** AND THE SIGN IS THE OPPOSITE OF THE STORY TOLD ABOUT IT: `harm_warm` DECREASES as overlap rises,
because a request already predicted slow has less `p_on_time` left to lose. So honouring the queue term
makes HOLD_BACK cheaper to refuse and WARM, TOUCH and SLICE MORE attractive, not less. *** The rung-4 note's
"over-defers" framing points the other way.

## 2. *** THE RESULT: 0 DIFFERING DECISIONS. THIS IS AN ABSENT LINK, NOT A SUCCESSFUL MINIMAL CHANGE. ***

```
rows 14539 both sides   positional_differing 0   setwise_differing 0
digest before 5a03c2807da3681a = digest after    state_action 2954 both sides
```
**And the probe fires, so this is a fact about the data rather than a dead check.** Instrumented
`_queued_behind`, identical both sides: **61,034 calls, 10,606 cache refills,
`npend_hist = {0: 10,181, 1: 425}` - NEVER 2 or more - so `ov = 0` in 10,606 of 10,606.**
*** THEREFORE THE DEFECT AT `:312` IS NOT A WRONG VALUE IN A RIGHT EXPRESSION. IT IS THE WRONG ROW SOURCE,
WHICH IS A BIGGER CLAIM THAN ROW 10.2 AS WRITTEN MAKES. *** `obs.recall` is `cstate.visible`'s
arrived-and-**undecided** set and the arm decides every 0.1 s, so it structurally cannot hold two items.
**There is no queued-ahead work in that row set under ANY unit, count or tokens.** The real overlapping work
is the in-flight set, which `_queued_behind` never sees.

## 3. The correct source cannot be determined, and the repo already says so

Four candidates, none safe without a ruling: **(a)** uncached tokens into `predict` is **the documented
247.46x unit error** (`per_overlap` is 0.0380 s per overlapping REQUEST against D162's 0.0001536 s per
token; the file records 165.6 s predicted against 0.818 s observed); **(b)** `predict_d162` is **two-factor
and explicitly scoped out** by `arms_v6cfr3.py:450-453`, which leaves `cf.model` alone precisely because
`plan_state` prices with it and its arms have committed cells; **(c)** a request count over `obs.recall` is
unit-correct and precedented but **measured structurally zero** (section 2); **(d)**
`queued_by_class + running_by_class` is non-zero and varying (committed census: queued-episodic p50 958,
max 2,686) **but at 0.0380 s per request is about 37 s of predicted first token, orders of magnitude outside
the model's fitted range, collapsing every `p_on_time` to 0.**
**`conformance_matrix.md` section 10.16 already records this as a ruling and not a fix**, and
`freeze_gate_status.md` row 10.2 offers the alternative closure itself: **a D-row recording that rung 3's
state planner prices without a queue term. On this evidence that is the cheaper and more honest remedy.**
**`:273/:274` additionally cannot take a queue term without a signature change:** `_p_warm_cold` has no
`obs` in scope, has exactly one caller, and prices a **future** question, where the house convention is a
declared input (`plan_sync`'s `coarse_overlap_forecast: float = 0.0`). **So at those two sites the zero is
the planner's documented default, not obviously a defect.**

## 4. The one-factor assertion PASSES, and one leg FAILED ITS OWN POSITIVE CONTROL

One file differs, nothing else. Loaded-source check confirms the change reaches the object under test with
no stale bytecode. By MRO rather than by name, **72 of 229 registered arms resolve the changed function and
156 cannot see it.**
| cell | decisions changed | fraction |
|---|---|---|
| rung-3 **1x s4** | **0** | 0 of 67,676 |
| rung-3 **kv0.5r s4** | **NOT ESTABLISHED** | its zero is NOT reported |
*** The kv0.5r leg is withheld because it failed its control: the dry harness is KV-BLIND.
`cstate.py:474` defaults `kv_capacity_enforced = False` and `test_hybrid.dry` never sets it, while both
committed cells carry `True`. A control at GPU_KV = 2,000, one thirty-first of 1x, produced an IDENTICAL
digest. *** So both replays are the unenforced-KV condition and neither is the committed memory condition.
The structural reason for the zero is arrival and decision cadence rather than KV capacity, so a zero is
expected there too, **but it was not measured and is not claimed.**

## 5. Does any committed verdict move? NO. And two things that is not

The decision log is byte-identical on the audited cell, so no cell's outcome, score or digest changes.
1. **Row 10.2 does NOT close by this fix.** Applying it leaves the row where it is and buys nothing
   measurable.
2. *** THE LATENCY STAYS LATENT, AND THIS IS THE REAL RISK IN THE ROW: the 247x unit error is latent ONLY
   because `overlap_ft` is the hard zero. It becomes ACTIVE on the first commit that honours row 10.2 under
   source (a) or (d). *** The prepared fix does not activate it, because it passes a count and the count is
   zero. **A token-valued fix at these sites would.** So "fix the hard zero" is not a safe default: the
   zero is currently load-bearing.

## 6. Stale document rows found

`conformance_matrix.md:296` and section 10.2 cite `arms_v6cfr3.py:198-199` and say "not applied". **At this
sha the rung-4 site IS fixed, at `arms_v6cfr3.py:233`**, with `cf.model_d162` attached at `:454`. The matrix
was not updated.

## 7. Not established

The correct queue-term source (open user ruling). The kv0.5r decision count (harness is KV-blind; needs a
real enforced cell). Whether a live cell would also show 0, since the `d188` precedent warns a dry replay
bounds nothing about live. And `state_chosen_HOLD_BACK` is 0 in replay against 2 in the committed cell, so
**the two decisions where HOLD_BACK's value - which IS `harm_warm` - was decisive were not exercised**, and
that is the one place a live rerun could differ from this zero.
