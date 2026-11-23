# StudyRUNG4: the counterfactual rung on the rung-3 base - PRE-REGISTRATION

D190 (3), D191 items 0 to 2. Written and **committed before any cell of this rung is posted**, which
is what D190 (3) requires. Every bar below was **supplied by the user** and is recorded verbatim;
none of it is recomputed here, and nothing in it may be moved after a cell runs.

Arm family: `experiments/orchestration/live2/arms_v6cfr3.py`. Names are recorded in
`research/arm_name_map.md`.

---

## 1. What rung 4 is

**The ladder is CUMULATIVE.** Rung 4 is rung 3 plus the counterfactual decisions, not rung 2 plus
them.

| rung | arm | what it adds |
|---|---|---|
| 2 | `covex-v6-state-uo-c5attr` | the C5 attribution rule |
| 3 | `covex-v6-fair-c5attr` | the D178 (2) deficit feed; on this base the ORDERING consumer is the whole of it |
| 4 | `covex-v6-cf-c5attr` | **two** counterfactual decisions of spec v6 section 7 |

The two decisions, reported separately throughout:

* **protect-and-defer** (`cf_protect_defer`, D165 (D)) - when an alert episode is active and a
  recall **rebuild or warm** is large and not urgent, protect the victim history and defer or chunk
  the rebuild to its latest safe start if its predicted harm exceeds the margin.
* **question-deferral** (`cf_request_defer`, D151 (3), scoped into rung 4 by **D191 item 2**)  - 
  defer a recall **question** to its latest safe start when an alert episode is active and the
  deferral's predicted harm saving exceeds the margin.

Why both: see section 2. `covex-v6-cf-pd-c5attr` (another family) is protect-and-defer over a
**rung-2** base, where the deficit weight is the constant 1.0 by that family's own record. This rung
is a different arm and a different question.

## 2. Why the second decision is in rung 4 at all, and why that is a scope ruling and not a tuning

Measured here, dry, seed 4, 16 devices, posted knobs, **1x memory**, on the rung-3 base:
protect-and-defer moved **zero** decisions and **not one** of its decisions reached the harm
computation. The gate mix is the diagnosis: every decision stopped at `no_active_alert_episode` or
`rebuild_fits_without_evicting`, and `pd_free_kv` was the constant 62,944 over every decision.

Under CLAUDE.md Rule 2 that is **UNEXERCISED** - the mechanism is reachable but no condition in the
run reaches it - and it is **an absent link, not a negative about the policy**. The user's diagnosis
is the one the gate mix supports: large non-urgent rebuilds rarely occur while histories stay warm,
so the remaining loss sits behind recall **question** prefills, which are neither rebuilds nor
evictions. A 6,000-token recall prompt delays an alert instant's first token through exactly the
same D162 queued-ahead term whether or not anything is evicted.

So the eviction gate is not a safety check that needs relaxing, it is **the wrong question**.
Protect-and-defer is therefore **left exactly as it is** - not loosened, not re-thresholded, not
re-run until it fires - and a second, differently-gated decision is added beside it. This is
recorded here so that it cannot later be read as a threshold having been moved after a null.

## 3. The inequality, in D191 item 1's ruled units

Gain and harm are both **counts of expected on-time cloud answers**, each device weighted by its own
`w_d`. **There is no division by the number served**: the target normalisation already lives inside
`w_d`. One comparison decides; any secondary key breaks only exact ties.

    defer iff   ( weighted gain  -  weighted harm )  >  w_R * MARGIN_CF ,   MARGIN_CF = 0.65824

For the question-deferral the two sides are named and both are inside the inequality:

* **gain** = the harm the deferral SAVES others, computed **per row**: a pending request whose own
  deadline has passed by the time the deferred prefill starts is saved; a row still ahead of it is
  not. `n_rows_saved` and `n_rows_still_harmed` travel on every decision, because "all the harm goes
  away" is the optimistic reading that makes a deferral look free.
* **harm** = the decider's **own loss**. Deferring to `deadline - kappa * service` leaves
  `kappa * service` of slack instead of the slack it has now, so the decider's own on-time
  probability falls, by `w_R * (p(engine, slack_now) - p(engine, kappa * service))`, on the same
  committed curve as every harm row. It is charged **before** the bar is consulted.

`w_j`, the harmed device's weight, sits **inside** the saving sum, one weight per row. `w_R`, the
decider's weight, scales **the bar**. Putting the harmed type's weight on the bar is the sign error
`cf_protect_defer` documents: harm and bar would scale together, the deciding ratio would not move,
and the deficit weight would be inert - Rule 2's `cancelled by geometry`.

`kappa = 1.5775406165458339`, the committed q90 of actual over predicted service, read through
`cf_margin.safety_factor(cf_cost.load_residuals())` - the same factor `v5/cf_planner.py:357` uses.
**Never chosen, never swept.** Its two committed caveats travel with every latest-start time: its
split is held-out-BY-ARM, not D125's "FIT/DEV", and the residual summary itself carries
`gate_status: FAILS`.

### 3a. The two pricing requirements, both binding before Step 2b is trusted

**REQUIREMENT 1, `u` is computed by the D186 / r1 correction and not by `built_tokens` alone.**

    u = tokens                                    if readiness is COLD
      = max(tokens - max(built, telemetry), 0)     otherwise

`last_telemetry_cached_tokens` is the engine's own report of the prefix it holds, trusted **only**
while the session is not believed COLD, because it is never reset on eviction (the `e9569009`
guard); `built_tokens` is the other source, and the **max** of the two is taken because each is a
lower bound on the true prefix and each exists when the other may not. All three inputs are carried
to the arm on the roster as `uncached_inputs_by_session` (additive; no committed arm reads it).

Why this is not a nicety: `built_tokens` alone priced recall **15.6x too high** under shares
(predicted median `u` 14,712 at s4 against the engine's own 1,050 on the same opportunity), which
refused 57 of 70 recall releases. In **this** module `u` multiplies the queued-ahead price, so 15.6x
too high **over-prices the harm of sending now and therefore OVER-DEFERS**, and that failure would
look exactly like the mechanism working: more deferrals, each justified by a harm that was never
there. The dry report shows `u` under the rule in force **against** `u` under `built_tokens` alone,
per candidate, so the two are compared and not assumed equal.

**REQUIREMENT 2, the safety factor is the MEASURED D162 under-prediction**, not the committed
service-residual kappa.

| | value | source |
|---|---|---|
| in force on this path | **1.8721** | `d190_recall_lag_diagnosis.json`, `devices.*.D162_positive_control_on_sent_rows[].observed_over_predicted`, **q90 by nearest rank over n = 5** |
| measured range | 1.3856 to 1.8721 | the five recall questions actually **sent** in the committed `covex-v6-fair-c5attr` cells at seeds 5 and 7 |
| q90 by linear interpolation, for comparison | 1.74398 | the same five values |
| the committed kappa this replaces here | 1.5775406165458339 | `cf_margin.safety_factor(cf_cost.load_residuals())`, q90 on a held-out-BY-ARM split |

The committed kappa **covers** the 1.3856 low end and **does not cover** the 1.8721 high end. That
is the gap the measured factor closes, and it closes it in the only safe direction: a larger factor
puts the latest safe start **earlier**.

**Why this is not tuning, and it is the provenance of the data that settles it.** The ratios come
from the committed cells of the **base rung 4 is built on**, not from rung 4's own cells. That is
the same practice D180 to D182 used to derive the D179 floors from committed `covex-v6-base` cells.
**n = 5 is stated first, not in a footnote:** at that n the nearest-rank q90 **is** the maximum, and
five rows is a real limitation on how well the tail is characterised. It is not presented as more
than it is.

**Scope of the change.** `cf_protect_defer.KAPPA` is left **exactly as committed** at
1.5775406165458339, because its arms (`covex-v6-cf-pd-*`) have a posted cell list owned by another
session and changing their safety factor would silently change what those cells measure. The tree
therefore holds two safety factors on purpose, and each one records which it is. That is a declared
divergence, not an oversight.

**And the column this buys.** Because the factor is now the measured bias, the self-inflicted-loss
question becomes arithmetic rather than a guess: a deferral's overrun under a bias `b` is exactly
`(b - safety_factor) * predicted_service`, so it is at or below zero for every `b` at or below the
factor. **How many deferred questions would have missed the 3 s deadline under the measured bias** is
computed on every candidate and reported at the measured worst bias, the measured best bias, and the
committed kappa this path no longer uses, so the three can be compared rather than argued about.

## 4. PRE-REGISTERED PASS AND FAILURE, at 1x, seeds 4 to 7

**Supplied by the user. Not recomputed, not negotiable after a cell.**

PASS requires **both** conjuncts, per seed:

1. **mean per-episode alert attainment ABOVE rung 3's**, which is

   | seed | 4 | 5 | 6 | 7 |
   |---|---|---|---|---|
   | rung 3 | 0.441 | 0.427 | 0.436 | 0.475 |

2. **robot on-time retention >= 0.90 of rung 3's gain over base.**

   | seed | 4 | 5 | 6 | 7 |
   |---|---|---|---|---|
   | base (`hybrid-F-lhreq-noc3`) | 35 | 27 | 41 | 19 |
   | rung 3 (`covex-v6-fair-c5attr`) | 122 | 114 | 109 | 84 |
   | rung 3's gain over base | 87 | 87 | 68 | 65 |
   | 0.90 of that gain | 78.3 | 78.3 | 61.2 | 58.5 |
   | **required rung-4 robot on time** | **>= 113.3** | **>= 105.3** | **>= 102.2** | **>= 77.5** |

   The required figure is `base + 0.90 * gain`, stated to one decimal so no rounding choice is made
   later. A count at or above it passes the conjunct.

**Reported beside it, every seat of it, and the third one may not be omitted:**

* **LATE ALERT FRAMES** - alert instants sent and answered after 1 s. The hypothesis is that they
  **fall**.
* **RECALL DEFERRALS** - count, and slack used (the deferral in seconds, as a distribution and not
  only a mean).
* **ANY RECALL MADE LATE BY A DEFERRAL** - D191 names this as the column that can turn a pass into a
  self-inflicted loss. The live figure is the scorer's. The dry arm also reports its own prediction
  of it (`rd_defer_own_p_after_zero`, `rd_defer_latest_start_infeasible`); the two are reported side
  by side and **neither is substituted for the other**.

**FAILURE CONDITION.** If the deferrals do not reduce late alert frames, protect-and-defer and
question-deferral are **REPORTED AS NOT WORKING**. They are **never tuned**. No threshold, no gate
and no horizon in either module is changed in response to a result.

**HARM BOUND**, carried forward unchanged from every cell of this grid: **robot late at most 10 per
seed**, flagged at once if exceeded, because deferring work can push the deferred work past its own
deadline.

**PORT RULE (CLAUDE.md "Citing results"), checked FIRST and before any score is read.** The count of
rung 4's characteristic decision - a question deferral, a rebuild deferral or a chunk - must be
**non-zero**. Zero is an **ABSENT LINK** and is reported as such, never as a negative about the
policy.

## 4a. FAIL-FAST: THE DRY s4 REPORT IS A GATE, AND s4 IS POSTED ALONE

User ruling, recorded here **before any cell is posted**. It adds to the pre-registration and
changes none of the bars in section 4.

### Gate A, the dry s4 report. Before ANY cell is posted it must show, and be read:

1. the number of recall questions **DEFERRED**;
2. **SLACK USED** per deferral, median and p90;
3. **PREDICTED u AGAINST ENGINE-REPORTED u** for the deferral candidates;
4. **how many deferred questions WOULD HAVE MISSED 3 s** under the measured D162 under-prediction
   (1.39x to 1.87x on the rung-3 sent cells).

**If the would-have-missed count is MATERIAL: STOP AND REPORT. NO CELLS.**

**On "material", and this is written down so it cannot be argued past later.** No threshold is
chosen here, because a threshold chosen by the party that wants to proceed is not a gate. The
report gives the **raw count** and its **ratio to the deferral count**, and if the figure is
anything that could move the verdict, the run **STOPS**. When in doubt, stop and report rather than
decide. A deferral that makes a recall late is a **self-inflicted loss**, and this gate exists to
catch it before GPU is spent.

**A tautology does not pass this gate.** The safety factor in force (1.8721) IS the maximum of the
five measured biases, so the overrun at that bias is identically zero by construction and a
"0 of N would miss" reading there is an arithmetic identity, not a measurement. The report must
therefore also give the **sensitivity**: the bias at which deferrals begin to miss, and the count
and worst overrun at biases above the measured maximum. A zero that flips to N of N just above the
assumed worst case is **material**.

### Gate B, two stages. s4 is posted ALONE, not s4 to s7.

After s4 lands it is scored against rung 3 s4, and s5, s6 and s7 are posted **only if BOTH** hold:

| conjunct | bar at s4 |
|---|---|
| mean per-episode alert attainment | **above 0.441** (rung 3's s4 value) |
| robot on-time retention >= 0.90 of rung 3's gain over base | **at least 113.3, i.e. 114 or more as an integer count** |

The robot bar in absolute terms, supplied so it is not re-derived: rung 3 s4 robot on time is 122,
base is 35, the gain is 87, ninety percent of 87 is 78.3, and 35 + 78.3 = 113.3. The report gives
the **raw count** and the **computed retention** beside it.

**Otherwise: STOP, diagnose FROM THE LOGGED DECISIONS, and report to the user before spending more
GPU.** s5 to s7 are not posted on a hope that a later seed recovers it.

This two-stage rule is in this file **before s4 runs**, so the stopping condition is on record
rather than decided afterwards.

## 4b. PRE-REGISTERED REPORTED SECONDARIES. These are NOT GATES.

Four quantities, declared here **before any of them exists as a number**, to be computed by the
Orin's **D192 episodic scorer** once it lands, against rung 3 at each seed:

| secondary | unit | expected direction |
|---|---|---|
| dashcam **episodes** correct: detections on crash episodes, false alarms on no-crash episodes | per episode | **no worse than rung 3** |
| robot correct by 3 s | per question | **no worse than rung 3** |
| single-shot correct within 2 s | per question | **no worse than rung 3** |
| cost per dashcam episode | GPU-seconds per episode | **no worse than rung 3** |

**They are secondaries and they stay secondaries.** None of them may be promoted to a gate after
the fact, and none of them may be quietly dropped: the whole point of pre-registering a secondary is
that its direction was declared before the number existed. Whatever comes out is reported.

**Why they exist, stated plainly because it is a real tension and not a formality.** Rung 4's gate in
section 4 is specified on **timeliness** quantities: mean per-episode alert attainment, and robot
on-time retention. D192 (2) makes the project's combined figure a **correctness** unit: correct
decisions delivered in time, per natural unit. Gating on one quantity while presenting the work by
another would mean rung 4 was judged by a different measure than it is shown by, and a reader would
have no way to see the substitution. The resolution is to keep the gate exactly as the user set it
and to add the D192 quantities as **declared secondaries**, so both appear side by side and neither
replaces the other.

## 4c. WHERE THE LINE AROUND RUNG 4 IS, NOW THAT IT HAS MOVED ONCE

Rung 4's scope widened once today: **D191 item 2** added the counterfactual request decision
(question-deferral) to what had been protect-and-defer alone. It does not widen again here.

**The D192 (3) episode early exit is NOT part of `covex-v6-cf-c5attr`.** When it is built it is a
separate switch or a separate arm on top of rung 4, with its own pre-registration and its own
verdict. Rung 4's definition and rung 4's verdict are **fixed** as of this file. A reader who met
the earlier, narrower description of rung 4 needs to be able to see exactly where the boundary now
sits, which is what this section is for.

## 5. What is reported separately and must not be folded in

**Protect-and-defer at 0.25x is a memory-pressure result and is reported on its own.** It is not
folded into the 1x verdict, and it may not be quoted beside a 1x number without the memory setting
attached. A mechanism that fires only under memory pressure is a **finding**, stated that way.

## 6. The framing this rung has to beat

Every rule-based fix so far - the share floors, r1's release re-check, the C5 attribution rule,
rung 3's deficit ordering - lands somewhere on **one** alert-versus-recall trade-off curve: alert
attainment bought with recall on-time, or the reverse. Rung 4's claim is that a counterfactual that
prices the trade explicitly and defers in **time** rather than choosing in **priority** moves **off**
that curve: both axes at once, because the deferred work is not dropped, it is moved to slack that
was going to be wasted. If rung 4 lands on the same curve, it is a non-contribution however good one
axis looks, and it is reported as one.

## 7. Caveats fixed in advance

* **The 0.25x engine setting.** Any 0.25x cell of this rung is **REAL-ENGINE**
  (`--num-gpu-blocks-override 984 --max-model-len 15744`, in that exact order; the allowlist in
  `study_live2_pilot.py` is an exact list match and the same flags transposed still STOP), per the
  user's D189 ruling, with a **matched-memory `-off` control** alongside. A logical-only `_kv0.25`
  tag is not this condition and is labelled as a different one.
* **Dry cells do not exercise price.** The charge mode is unexercised dry (`covex-v6-rules` and
  `covex-v6-rules-wo` are byte-identical dry), so a dry cell proves the arithmetic is live and the
  switch reaches a decision; it says nothing about magnitude against a real engine.
* **The dry 0.25x control is degenerate.** The dry harness's `gpu_kv_fraction` comes from a live
  server and is identically 0.0, so dry evidence cannot substitute for the live matched control.
* **D188 freezes stand.** Floors and `W_max` frozen, `live2_qcache_key_fix` NOT enabled, and the
  `id(obs)` cache-key fix stays **OFF** (D190 (6): applied only when the final ladder is rerun
  together).
