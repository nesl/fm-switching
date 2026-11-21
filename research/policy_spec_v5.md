# Scheduling policy: specification v5

Written 2026-11-20 from design-log decisions **D145 to D153 inclusive**, which are the source for
everything in this document. v5 supersedes v4 (`research/policy_spec_v4.md`, D59) for the parts it
restates and leaves every other part of v4 standing unchanged.

**Amended 2026-11-20 (user amendments 1 to 4, base `8a8f592`).** Four changes, each marked in place:
the base policy is now **hybrid-F-lhreq-noc3** with C3 off (section 4); **D153 fixes the dashcam
format by the task** as the EP-G append-only episode context, with a minimum-frame floor (section
8b); four gaps close and two stay open (section 14); and the D151 (6) gate's failure is restated at
its real cause, warm confounded with arm (section 12).

**One consequence of D153 that a reader must carry into every table below.** Every committed
frozen-grid, post-fix, sweep, calibration and 3 s handful cell is labelled **`dashcam-1f`** by
D153's own labelling ruling: its dashcam devices send one frame per call, not EP-G. Those cells are
**sensitivity only and are never a headline**. Sections 2 and 11 quote them because they are the only
measurements that exist, and every such quote is tagged `dashcam-1f`. The EP-G numbers that replace
them do not exist yet.

Nothing in this document is a result. It is a specification plus the value-reader design D149 and
D152 call for, with the arithmetic of that design checked offline in
`experiments/orchestration/live2/v5/value_readers.py` and
`results/orchestration/live2/v5/value_readers_checks.json`. Section 14 lists every place a gap was
recorded rather than filled, and section 15 lists what v5 needs from other work before it can run.

**Provenance of the source text.** The decisions D106 to D152, `reports/study_frozen_test.md`,
`reports/study_policy_v2_gate.md`, `reports/study_sh_ep.md`, `reports/study_lh_req.md` and
`results/orchestration/live2/lh_req/lh_req_quality.json` were read from detached worktrees at
`origin/main`, at `fd396d1`, `44052f2` and then `8a8f592`. The flash working tree was at `17bdf15`
throughout and does not contain them. Every quoted number below is from `8a8f592`, and
`experiments/orchestration/live2/v5/value_readers.py` reproduces its own outputs identically at all
three bases.

**D153 is not in `research/policy_design_log.md` at `8a8f592`.** Its text reaches this spec through
the user amendment of 2026-11-20 and through the labelling ruling quoted at the head of
`reports/study_frozen_test.md`. The minimum-frame floor counts in section 8b were measured by the v5
coordination session on the committed EP-G data and are **not yet in a committed results file**. Both
are register marks, not doubts: the decision is the user's and the counts are measurements, but a
later reader should be able to find them, and today they cannot. Requested of session D in section 15.

---

## 1. What v5 is

v5 is the first specification in which **value reads a decision**. v4 carried a value objective
(D2, section 3) and the frozen policy built from it, hybrid-F, nonetheless made no value decision:
D149 (4) records that in hybrid-F and hybrid-F6 a flat value table and a 10,000x inverted one moved
**zero decisions**, because every decision those arms made was a timing decision. v5 exists to put
real alternatives in front of a value comparison and to prove, by the same negative control that
found the problem, that the comparison moves them.

Three things change at once and they are not separable.

1. **The deadlines come from the use case** (D147), and at a 3 s robot deadline a cold history
   essentially cannot be answered in time, so warming ahead stops being an optimisation and becomes
   the normal path (D152 (3)).
2. **Delivery is at completion** (D146), so an answer is late if its decode is late, and decode is
   set by how busy the engine is at that moment, not by how many tokens are emitted
   (`study_frozen_test.md` 18.7.2, 19.5).
3. **The robot headline is correct answers delivered** (D152 (1)), so an arm can no longer buy the
   headline by sending less evidence.

---

## 2. Deadlines (D147, D71)

| type | deadline | sensitivity sweep | source |
|---|---|---|---|
| long horizon (robot) | **3 s** | 2.5, 3, 4, 5 s | D147: single-shot plus 1 s. Was 5 s, a starting value chosen so cold rebuilds were feasible |
| single shot | **2 s** | 1.5 to 3 s | D147 |
| dashcam | **1 s** | not swept in v5 | D71, `NEXAR_DEADLINE_S = 1.0`, already committed in `scorer/score.py` and `arms_policy.py` |

**The dashcam 1 s is committed but is not settled by D147.** D147 says in terms that the dashcam
deadline is "to be settled with the short-horizon discussion". v5 therefore uses the committed 1.0 s
(D71) and marks it provisional; it is not a D147 value. Recorded as gap G3.

Consequence of the robot 3 s, measured, not assumed:

- At 3 s, over all robot questions and completion delivery, every committed arm fails a 0.9 bar; the
  best is hybrid-F post-fix at 0.5281 (`study_frozen_test.md` 19.1, 21.1).
- Of the 282 sent misses at 3 s, **282 had a COLD history and 0 had a warm one**. Warm first-token
  latency measured at 0.3963 s would have made 279 of the 282 (19.2).
- Cold feasibility with decode included falls from 70 of 70 at 5 s to **48 of 70 at 3 s**, and the
  history-token threshold falls from 19,500 to **13,193** (19.3).
- In the contention simulation at committed capacity, warming ahead absorbs the 3 s deadline
  completely, 65 of 65, while not warming gives 25 of 65 (19.4).

So **the gap between what the arms achieve at 3 s and what is achievable is warming, not the
deadline**. That is the fact v5's state decisions are built on.

---

## 3. The three decision kinds (D151 (2))

| kind | what it decides | rule-based or counterfactual | source |
|---|---|---|---|
| **request** | for a robot question: admit now with full history, defer to its latest safe start, send RECENT, or reject | **counterfactual** | D151 (2), (3) |
| request | for a dashcam frame: the C5 cap, episode continuity, deficit counters | **rule-based** | D151 (2) |
| request | for a single-shot question: feasibility | **rule-based** | D151 (2) |
| **state** | warm, touch, keep, reload, hold back or slice a cold rebuild | **counterfactual** | D151 (2), D150 STATE |
| **sync** | post-outage backlog ordering, and question-first vs wait vs leave-to-device | **counterfactual** | D151 (2), D150 SYNC (3) |
| sync | per-frame upload as captured | **rule-based**, not a decision at all | D150 SYNC (1) |

D151 (2) is exact about the split and v5 does not widen it. Dashcam frames and single-shot requests
stay rule-based **even though D149's value readers could rank them**, because the counterfactual is
the expensive path and D151 (5) gives it a p99 budget of 20 ms at 32 devices. Episode continuity
(D149 (3)) is a value preference expressed as a rule-based ordering, not a rollout; section 7.6.

---

## 4. Base policy and the counterfactual margin (D151 (1))

**The base policy is `hybrid-F-lhreq-noc3`, hybrid-F with C3 OFF, and it is EXECUTED BY DEFAULT**
(user amendment 1, per D152 (2)). The counterfactual runs beside it and its choice is taken **only
when its predicted gain beats the base's by a margin fixed in advance and never tuned**. So v5 is
never worse than `hybrid-F-lhreq-noc3` up to cost-model error, which is the property D151 (1) is
buying, and the margin is what pays for it.

**Why noc3 and not hybrid-F, stated so it cannot be read as an ablation chosen for convenience.**
C3 sent RECENT whenever the full history would not fit and RECENT would, a feasibility test that
never consulted whether the answer would be any good. **Taking C3 off is the decision the value rule
arrives at on its own**, and that is measured, not argued: on the dry seed-4 16-device cell
(`study_policy_v2_gate.md`, the value-reader section; proofs in
`results/orchestration/live2/frozen_test/value_reader_proofs.json`) the value reader's decision
digest is `5d3469549fead8ac`, **byte-identical to simply disabling C3**, and both release D2 372
times and RECENT 0 times where hybrid-F with C3 on releases RECENT 5 times under digest
`ec49e6d5a3b5454f`. The reason is section 7.2's arithmetic: on the committed DEV table cloud RECENT
(0.107143) exactly equals the device (0.107143) and ties go to the device, so the reader withholds
RECENT in every case C3 would have sent it.

So the base is not "hybrid-F minus a feature". It is the policy the reader's own comparison selects,
with the reader's conclusion already baked in so that the counterfactual is never credited for
removing a shortcut the base should not have had. The practical consequence for the evaluation is
that **v5's lead over its base can no longer come from declining RECENT**, because the base already
declines it; it has to come from timing, warming and placement.

- The margin is a declared constant, `MARGIN_CF` in `v5/value_readers.py`, in units of the objective
  (expected correct on-time answers). Its current value, 0.05, is a **placeholder awaiting a ruling**
  and is recorded as gap G8. It is declared as a constant rather than a parameter precisely so that
  changing it is a visible edit and not a sweep.
- D151 (6) widens the margin if the cost model cannot pass its gate, **and that is where v5 stands
  today**: the gate does not pass and cannot pass on committed data (section 12).
- "Never tuned" is an auditable claim, not a promise. The v5 run report must show the margin's value
  and that it is the same value in every cell, and must not report a margin sweep as a result.

**What "never worse than the base" does and does not mean.** It is bounded by cost-model error, and
the cost model's decode term **over-predicts by 25 to 32 percent in every held-out class**
(`study_policy_v2_gate.md`, the gate section at `8a8f592`). A planner that over-estimates decode by
a quarter to a third defers work it could have released. The guarantee is therefore conditional on
section 12's gate, and v5 may not claim it before the gate passes.

---

## 5. Request decisions for robot questions (D151 (3), (4))

### 5.1 The candidate set

Four candidates, and no others:

1. **admit now**, full history (D2);
2. **defer to its LATEST SAFE START**, defined as `deadline minus predicted service times a measured
   safety factor`, with a **re-plan on slip** (D151 (3), the v1.2 planner idea);
3. **RECENT**, which D151 (3) already calls rarely worth it on LH-REQ and which the value reader
   declines on the committed DEV table for every delivery probability (section 7.2);
4. **reject**, which under D152 (2) means the device answers.

**Slicing applies to background warming, not to deadline requests** (D151 (3)). That is a scoping
rule and v5 must not reach for a sliced release to rescue a late question.

### 5.2 Latest safe start

The deferral is the mechanism `study_frozen_test.md` 18.7.3 credits hybrid-F's advantage to: it
releases robot questions into an engine five to six times quieter than the one b7, mooncake and
eco-llm release into, and after normalising by each arm's own in-flight load the factor is still
about 2.6 (18.7.5). Deferral is therefore not a way of saving capacity, it is a way of choosing the
moment at which the answer's decode is charged.

The predicted service that sets the latest safe start must include **decode**, because at 3 s decode
is up to 47 percent of the budget and was 1.086 s at the median on the actual misses (19.5), and
because adding decode moves the cold feasibility threshold by about 1,700 tokens at 3 s (19.3).
Omitting it, which the committed feasibility formula does, is the difference between 48 and 42 of 70
feasible.

The safety factor is **measured**, not chosen, and comes from the held-out predicted-versus-actual
check of section 12. Until that check passes, the safety factor and the margin both widen, and the
run report says so.

### 5.3 Horizons, per decision (D151 (4))

| decision | horizon | note |
|---|---|---|
| robot request | its own deadline **plus the deadlines it displaces** | the displacement term is what makes the rollout a counterfactual rather than a feasibility test |
| warm or keep | until the history's **next likely question**, capped about **60 to 120 s** | the cap is declared, not fitted |
| post-outage backlog | **until caught up** | |

### 5.4 Two-level fidelity (D151 (4))

**Exact near-term simulation, coarse load forecast beyond.** The near-term level simulates the
engine's actual queue over the horizon that contains the decision's own deadline and the deadlines it
displaces; beyond that the rollout carries a forecast of offered load only. The split point is
declared per decision kind and is not a tuned parameter.

The reason for two levels rather than one is the 20 ms budget of section 10, and the reason exactness
is needed near-term is 19.5's 58-fold decode range: a coarse model of the next few hundred
milliseconds cannot tell a 0.024 s decode from a 1.40 s one, and that difference decides a 3 s
deadline on its own.

### 5.5 Objective

**Change in expected correct on-time answers, weighted per device by the deficit counters, with harm
to others included** (D151 (4)). This is the same quantity every reader in section 7 maximises, which
is deliberate: a counterfactual and a reader that optimise different objectives would disagree at the
margin and the disagreement would be invisible.

---

## 6. Value readers: why they exist

D149 (2) says that **within a type**, value decides between real alternatives, and names four:

- which robot histories to warm or keep;
- full history versus RECENT for a question, by **accuracy x P(on time)**;
- which same-type request to shed under overload;
- whose backlog to sync after an outage.

D149 (1) says that **across types and devices**, per-device targets enforced by deficit counters
decide who must be served, and **value is never a cross-type exchange rate**, because the units are
incomparable and per GPU-second it would shed robots first. v5 keeps those two statements strictly
apart: no reader in section 7 ever compares a robot to a dashcam.

The measured reason the representation reader is needed is `study_frozen_test.md` 21: at 3 s the
ranking by on time and the ranking by accuracy **nearly invert**. hybrid-F delivers 2.3 times b7's
on-time rate and ends with slightly fewer correct answers, because 18 of its 47 on-time answers were
RECENT at 0.111 correct against the device's own rate. 21.3 states the consequence plainly: a policy
tuned on on time will prefer RECENT, because RECENT is cheap and lands inside the deadline, and it
will be wrong nine times in ten when it does.

---

## 7. The value readers (D149, D151 (4), D152 (2))

Implemented in `experiments/orchestration/live2/v5/value_readers.py`. Pure functions, no GPU, no
model server, no coordinator. The accuracy table is a **committed input file**, read and never a
constant in the module, following the `lh_req_quality.json` convention already enforced in
`arms_policy._LhReqFittedProfiles`: refilling the table is a data update that leaves the readers
byte-identical.

### 7.1 The objective every reader maximises

    V = sum over devices i of  w_i * P(on time | option) * accuracy(option)   minus harm to others

`w_i` is device i's deficit weight (D149 (1)); accuracy is DEV-fitted (D6); `P(on time)` is supplied
by the cost model under completion delivery (D146). `harm` is the expected correct on-time answers
lost by other devices because of this option, which is the "harm to others included" of D151 (4).

### 7.2 Reader 1: representation and tier (D149 (2), D152 (2))

**Send a representation only if `w * P(on time) * accuracy` beats the device's own answer by
`MARGIN_SEND`; otherwise the device answers. The device is the incumbent and wins ties.**

D152 (2) says that for long-horizon questions the RECENT-only shortcut is not used: full history if
it can arrive in time, otherwise the device answers. **That rule is not written into the reader and
does not need to be.** It falls out of the comparison on the committed DEV table:

| quantity | DEV value | Wilson 95 percent | source |
|---|---|---|---|
| cloud D2 | 0.250 (7 of 28) | [0.127, 0.434] | `lh_req_quality.json` |
| cloud RECENT | 0.107143 (3 of 28) | [0.037, 0.272] | same |
| device (4B x RECENT) | 0.107143 (3 of 28) | [0.037, 0.272] | same |

Since cloud RECENT equals the device entry, `p * 0.107143 <= 1.0 * 0.107143` for every `p <= 1`,
with equality only at `p = 1`, and ties go to the device. **RECENT never strictly beats the device,
so the reader never sends it.** Verified over a declared synthetic grid of 121 delivery-probability
points in `value_readers_checks.json`: RECENT is chosen 0 times.

Three qualifications that must travel with that arithmetic.

- **The DEV equality is arithmetic, not agreement.** Cloud RECENT and the device both score 3 of 28
  and share only **1 of 3** questions (`lh_req_quality.json._dev_coincidence`). A reader could take
  the equality as corroboration that the device substitution is sound. It is not.
- **The device entry is a declared substitution.** No device-on-D2 result exists on these questions;
  the 0.107143 is the D87 4B x RECENT figure standing in. D146 already schedules its replacement by
  the Orin's measured values under StudyORIN-REC.
- **The equality is a property of this table, not a law.** If the device figure falls below cloud
  RECENT when it is measured properly, the reader will start sending RECENT, and that is the correct
  behaviour, not a regression. D152 (2)'s rule falling out of the reader means exactly that v5 does
  not hard-code the current table's accident.

**Agreement with the working implementation.** `experiments/orchestration/live2/hybrid/value_reader.py`
(session D, committed at `44052f2`) implements this same reader and this spec was reconciled against
it rather than the other way round. Both read the same committed DEV table, both refuse a table that
is not DEV-fitted, both compare with a strict inequality so the device wins ties, and both decline to
fit bands while leaving a band interface in place. Two differences, neither of them a disagreement:
that module carries no explicit `MARGIN_SEND` because a strict inequality is the zero-margin case, and
its inversion control reflects the table (`hi + lo - v`) where section 7.8 swaps the two cloud
representations. The run report should state which inversion it used. One thing to fix in that
module's prose and not in its arithmetic: its docstring quotes the device at "about 25 percent" while
the table it reads gives 0.107143. That is gap G6 appearing a second time, and the arithmetic is
unaffected because the module reads the table and not the docstring.

**Step 2b, the switch reaching a decision.** Run against the rule it replaces, the C3 degradation in
`hybrid/hybrid_arm.py` (send RECENT whenever a full-history recall is infeasible and a RECENT one is
feasible, accuracy never consulted), over the same 121 decisions:

| | D2 | RECENT | device |
|---|---|---|---|
| v5 reader | 66 | **0** | 55 |
| C3 rule | 66 | **30** | 25 |

**30 of 121 decisions differ**; the first is at `p_full = 0.0, p_recent = 0.5`, where C3 sends RECENT
and the reader lets the device answer. The two agree on every D2 decision, so the reader is not a
different feasibility test wearing a value costume: it changes exactly the decisions D152 (2) is
about, and nothing else.

### 7.3 Reader 2: warm and keep (D149 (2), D150 STATE)

    gain = w * P(question within horizon) * accuracy * (P(on time | warm) - P(on time | cold)) - harm

Horizon: the history's next likely question, capped about 60 to 120 s (D151 (4)).

The `harm` term is the part that cannot be dropped. `study_frozen_test.md` 19.4 shows warm-all
reaching 65 of 65 at committed capacity and 34 of 65 at 0.25x, so at a tight pool a warm that evicts
a history whose question is due is negative value, and a reader without `harm` would rank it
identically at both capacities. This is also the reader that implements D150's "above all control
what enters the GPU": holding back or slicing a large cold rebuild is a negative-`harm` option in
this same comparison, not a separate mechanism.

### 7.4 Reader 3: shedding under overload (D149 (2))

Shed the lowest `w * P(on time) * accuracy` per GPU-second first, **within one type**. The module
refuses to rank across types and records `single_type` in its output, because D149 (1) names exactly
this: per GPU-second a cross-type exchange rate sheds robots first. Which type gives way is decided
by the deficit counters, upstream of this reader.

### 7.5 Reader 4: post-outage backlog (D149 (2), D150 SYNC (3))

Order reconnecting devices by deficit-weighted recoverable value per GPU-second of prefill. Order
**within** a device oldest-first, which is not a value judgement but a constraint: an append-only KV
context (D148, D152 (3)) cannot prefill a later frame before an earlier one, because a token's KV
depends on everything before it and on its position.

For a question that arrives before catch-up, the three options D150 SYNC (3) allows are
**question-first** (pre-outage history plus recent frames, D54), **wait**, and **leave to the
device**. They enter reader 1 as three options with different `P(on time)` and different accuracy,
so the choice is the same comparison, not a fourth mechanism.

### 7.6 Reader 5: episode continuity (D149 (3), D148)

Frames of a dashcam episode already admitted and warm are prioritised over newly arriving episodes.
The justification in D149 (3) is a cost fact and a value fact together: an appended frame prefills
one frame onto a warm context while a cold start prefills an episode, and dropping an episode
mid-way wastes the warm context **and the trajectory evidence**. **Deficit counters prevent new
devices starving**, and in the module that is literal: a device flagged starving by its counter sorts
ahead of continuity. Continuity is therefore a tie-break with a counter above it, never a lock-in.

Episode context itself is fixed by D148 and D153: append-only KV, never a sliding window (which
forces a full recompute), refreshed with a fresh context after N seconds with no overlap, **N settled
as EP-G as run** (D153, closing G12), discarded on idle by LRU or timeout as vLLM already does.
Section 8b gives the format, the minimum-frame floor and its measured cost. Consequence carried into
section 8: each dashcam holds persistent KV competing with robot histories for the 62,944-token GPU
pool, and under EP-G's mean of 14.80 frames per request that is more KV than D148's own estimate.

### 7.7 Deficit weighting (D149 (1), D152 (1))

`w_i` comes from the per-device deficit counters, which **stay on observable on-time** (D152 (1)),
while the robot headline is correct answers delivered. That is a deliberate mismatch between what the
counters steer on and what the evaluation scores, and v5 keeps it because on-time is observable at
run time and correctness is not. It is recorded as gap G14 rather than smoothed, because a counter
that cannot see accuracy cannot steer toward it, and the whole of section 11 exists because those two
quantities came apart.

### 7.8 Acceptance test: value inversion (D149 (4))

D149 (4): **in v2, flattening or inverting the value table MUST change decisions and outcomes;
otherwise value is decorative.** This is CLAUDE.md's Step 4 negative control stated in the
decisions' own words, and it exists because the frozen policy failed it silently.

Run on the reader over 36 grid cells (`value_readers_checks.json`):

| perturbation | decisions changed |
|---|---|
| flat table (all accuracies 0.25) | 18 of 36 |
| representations inverted (D2 priced as RECENT and RECENT as D2) | 27 of 36 |
| full history devalued 10,000x | 18 of 36 |

**Every perturbation moves decisions, so value is load-bearing in the reader.** This is stated at the
register it was measured in: it is the reader **in isolation**, over a synthetic probability grid. It
is **not** evidence that value moves outcomes in a run, which is what D149 (4) finally asks for.

**It has since been run inside the arm, and it did not discriminate.** On the dry seed-4 cell
(`study_policy_v2_gate.md`, the value-reader section) `hybrid-Fv-lhreq`, `hybrid-Fv-flat-lhreq` and
`hybrid-Fv-invert-lhreq` all produce digest `5d3469549fead8ac`: flattening and inverting the table
change nothing. **That is a failure of the test, not a pass of the mechanism**, and the cause is
scope rather than decoration. Wired behind `c3_value_reader`, the reader is consulted only in C3's
old slot, which is reached only when the full history did not fit, so the only candidate ever offered
is RECENT and under all three tables the reader withholds it. A control whose every case lands the
same way under every treatment cannot detect anything. The gate report records it as **unexercised**
under CLAUDE.md Rule 2, which is the correct classification and not a negative.

That the reader can express a preference when it is offered a real choice is shown directly, outside
the arm, in that same section: with both D2 and RECENT fitting, the committed table sends D2 while
the flattened and inverted tables withhold.

**So the acceptance test as v5 must run it has a precondition, and the precondition is a design
change v5 was already making.** The reader must be consulted at **ADMISSION**, choosing among D2,
RECENT and the device, which is exactly where D151 (3) puts the robot decision and where section 5.1
puts it. A reader living in a fallback slot cannot be acceptance-tested at all. v5's requirement is
therefore:

1. the reader is called at admission with the full candidate set of section 5.1;
2. the three perturbations are applied inside the arm, scored on correct answers delivered, with the
   number of decisions changed **and** the change in the headline both reported;
3. if decisions change and outcomes do not, the report says whether that is `unscorable` or `fired
   and did not help`; if decisions do not change, it says `unexercised` and the v5 result is not read.

This is the clearest instance in v5 of CLAUDE.md's own warning: the in-arm control **passed every
surface check** (the arm ran, the reader fired, the digest was stable) while testing nothing, and
only the comparison of the three digests to each other showed it.

### 7.9 Accuracy by history-length band: asked for, not fitted

D149 asks for accuracy DEV-fitted **by history-length band**. **No band table is fitted and none is
invented.** The DEV split holds 28 questions and the aggregate Wilson interval for cloud RECENT is
already [0.037, 0.272], a width of 0.235. Three bands would hold about nine questions each, so each
band estimate would be noise given a shape, and a band table fitted on nine questions would be read
later as a measurement.

**What would make bands fittable: P19, the full S-EMBER device sweep on the Orin under vLLM, all
questions, RICH and RECENT, accuracy and latency.** With accuracy measured per question over the
whole set, bands are fitted on hundreds rather than on nine, and the device side of the comparison
stops being the D87 4B x RECENT substitution at the same time.

**Until then, history length enters v5 only through `P(on time)` and never through accuracy.** That
is not a neutral simplification and the spec says so: at 3 s the cold feasibility threshold is 13,193
tokens (19.3) and the questions actually sent as RECENT are the longest histories (D152 (2)), so
length and accuracy are correlated in the population the reader decides over. The reader's accuracy
term is therefore an aggregate standing in for a function of length, in a direction that is not
known. Any v5 result that turns on the representation choice must carry this as a limitation.

---

## 8. State decisions under vLLM's no-pin constraint (D150 STATE)

**vLLM cannot pin KV.** A running request's blocks are never evicted; a finished request's blocks are
LRU-evictable, spilling to the 27 GiB native host tier and then cold. v5 therefore owns no pin, no
reservation and no guarantee, and steers instead through four levers, all of which are options inside
reader 2:

1. **warm**, a prefill that puts a history on the GPU;
2. **touch**, a cheap request that sets recency so LRU keeps it;
3. **warm or reload just in time** before a likely question;
4. **control what enters the GPU**: hold back or slice a large cold rebuild that would evict a
   history whose question is due. D150 calls this one "above all", and it is the only lever that acts
   on the eviction of **someone else's** state.

**Residency is a belief and must be corrected by measurement.** The counterfactual predicts survival
from the measured step-function model (StudyENG1b, StudyENG1c), and the engine's **per-request
cached-token count** corrects the belief. D150 names `telemetry_cached_tokens` as the defect to
repair, and the gate report has since measured what that field actually is. The finding is sharper
than "unread" and it changes what session C is being asked for:

- `telemetry_cached_tokens` appears in **18,738 residency rows over 45 cells: absent in 16,934,
  exactly zero in 1,804, positive in NONE**.
- **That is not a broken write.** It is logged at `coordinator.py:756` on the **history-build path
  only**, so it never observes the dashcam monitor traffic where most of the reuse happens, and on
  the slice it does cover it is honestly zero. `backend.cached_tokens_of` is careful in the same
  direction, returning None rather than 0 when absent, with a comment that a zero "would be read as a
  confirmed cold path and D81's WARM / COLD tag would then be a fabrication".
- **So wiring the field will not by itself make the belief track residency.** A field that cannot see
  the traffic is not corrected by being read.
- **The phenomenon the correction is for is real and the committed code already names it**, at
  `coordinator.py:745-752`: a partially built history keeps a COLD readiness while "the already-built
  prefix is still reused on the wire as uuid references, so the request is cheap even while the
  readiness the arm sees says COLD; that gap is a limitation of the committed action space and is
  reported." **An arm can be told COLD on a request the engine serves cheaply**, and that, not a
  telemetry disagreement, is what v5's correction has to close.

v5's requirement is therefore stated as an outcome and not as an edit: **the belief must track
residency on partially built histories, and the proof is a measured belief-versus-engine comparison
over traffic that includes the dashcam path, not a non-null field.** Recorded as gap G9, restated;
the file is owned by session C and this is the first thing it should know.

**An external KV store (a KV connector) for hard guarantees is explicitly a later extension, not
v5.** v5 may not assume one and may not report a result that depends on one.

Capacity context, from D148: each dashcam's persistent episode KV competes with robot histories for
the 62,944-token GPU pool, so the memory sweep of section 12 is where the warm-ahead conclusion of
section 2 is actually tested. Under D153 that competition is larger than D148's estimate, because
EP-G carries a mean of 14.80 frames per request against the 3.4 to 6.8k tokens D148 projected from
the shorter EP-B; section 8b.

---

## 8b. The dashcam path is EP-G, fixed by the task (D153, D148)

**Every dashcam query, on the device and in the cloud, uses the append-only episode context of
D148, which is EP-G as run in StudySH-EP. Never one frame per call.** This is fixed **by the task**:
it is what a dashcam query is, and it is therefore not contingent on any experiment's verdict about
whether episode context improves detection.

**EP-G as run** (`reports/study_sh_ep.md` section 3): append-only from four seconds before the first
evaluated instant, capped at 21 frames, which is 10.0 s at 2 fps; frames carried per request
min 1, max 21, **mean 14.80**. Append-only means each new frame is prefilled onto the warm context
and never a sliding window, because a token's KV depends on everything before it and on its position,
so a window forces a full recompute (D148). Refresh with a fresh context after N seconds with no
overlap, discard on idle by LRU or timeout as vLLM already does.

**N is settled: EP-G as run** (D153). This closes gap G12, which previously read as pending between
EP-B at 5 s and EP-G at about 10 s.

### 8b.1 The minimum-frame floor

**Instants before an episode's third frame are not decision instants for ANY arm. They are excluded
identically across arms and counted.** The floor exists so that an arm is never scored on an instant
at which the episode format it is required to use does not yet exist, and "identically across arms
and counted" is the whole of its fairness: an exclusion applied to one arm is a different workload,
and an exclusion not counted is an undocumented denominator.

Cost of the floor, measured on the committed EP-G data by the v5 coordination session:

| floor | instants excluded | of | share | clips touched |
|---|---|---|---|---|
| **3 (adopted)** | 6 | 3,898 | **0.15 percent** | 3 of 300 |
| 6 (considered) | 26 | 3,898 | 0.67 percent | 8 of 300 |

**No clip loses every instant at either floor**, which is the check that matters: a floor that
emptied a clip would silently drop it from the population rather than trim it.

The floor is cheap because the manifest already pays for it. **EP-G gives each episode a 4.0 s
lead-in at 2 fps before anything is evaluated, so nine frames are already present at the first
decision instant in 287 of 300 clips.** The floor therefore binds only on the handful of clips whose
reference time sits close to the clip start, which is the same small set of short-lead clips
`study_sh_ep.md` section 2 already handles by clipping the window rather than dropping the clip.

### 8b.2 StudySH-EP is cited as a finding, not as the reason for the format

StudySH-EP is **not retracted** and v5 cites it as a result about models, not as a format decision:

- **Episode context did not improve the large model's challenge AP at any breadth tested.** No 32B
  condition differs from its own C1: C3 -0.028, C6 +0.002, EP-B +0.005, EP-G -0.032, all four CIs
  including zero (`study_sh_ep.md` 13.2).
- **Multi-frame input hurts the small model at the two highest frame counts** and helps the large one
  at none: the 4B degrades against its own C1 by **-0.060 at C6** and **-0.072 at EP-G**, both CIs
  excluding zero, and the 32B degrades significantly at neither (13.2, 13.3).
- The 32B beats the 4B in every condition, and the two largest gaps, C6 at +0.1622 and EP-G at
  +0.1409, sit on exactly the two conditions that most damage the model running on the device. The
  wider gap at EP-G **is entirely the 4B degrading** (13.1).
- H3 holds decisively: warm episode context costs **0.1324 s against one frame's 0.1302 s**, so the
  format is essentially free once the episode is warm. That is why fixing the format by the task
  costs nothing in latency and why the cost it does impose is in **KV occupancy**, which is section
  8's problem and not section 2's.

**The tension a reader will notice, resolved explicitly.** StudySH-EP's pre-registered decision rule
reads "otherwise dashcams stay one-frame", its verdict section says dashcams stay one-frame, and
`research/STATUS.md` at `8a8f592` carries that as its headline. **D153 does not overturn that
verdict.** The verdict answers the question the study asked, whether episode context buys better or
earlier detection, and the answer is no, classified `fired and did not help`. D153 answers a
different question, what a dashcam query **is**, and fixes the format by the task. The two coexist,
and the honest statement of the pair is: v5's dashcams use EP-G because that is the workload, while
knowing from StudySH-EP that the format buys the cloud model no accuracy and costs the device model
0.072 of challenge AP. **The device-side cost is a v5 limitation and must be reported as one**, since
D152 (1)'s headline credits the device's own answer whenever the cloud's does not arrive.

### 8b.3 What this invalidates, and what has to be redone

Every committed cell is `dashcam-1f` and is sensitivity only (D153's labelling ruling). Three
consequences v5 must carry rather than quietly inherit:

1. **Section 11's robot headline table is on `dashcam-1f` cells.** Its ordering and magnitudes stand
   as sensitivity and not as a v5 headline.
2. **Section 2's conclusion that the 3 s shortfall is warming and not the deadline was measured with
   one-frame dashcams.** EP-G adds persistent episode KV per dashcam to the same 62,944-token pool,
   so the memory pressure under which warming was shown sufficient is strictly greater than the
   pressure it was shown sufficient under. The direction of the conclusion is not in doubt; its
   margin is, and the memory sweep is where that is settled.
3. **The cost model must be refitted on the EP-G workload** (D153), not only on the cells section 12
   names. Added to section 12.

---

## 9. Sync decisions (D150 SYNC)

1. **Devices upload every frame as captured.** The network costs latency only, about 1 percent of the
   link, and uploading is **decoupled from the cloud-side warming decision**. Uploading is not a
   policy decision in v5.
2. **A question carries any frames the cloud lacks** (an on-demand delta).
3. **Outage.** The device answers alone and keeps its raw frames since the last confirmed sync; that
   last clause is a **stated assumption**, not a measurement. On reconnect the policy prioritises
   whose backlog to prefill by value plus deficit (reader 4), and a question arriving before
   catch-up chooses question-first (pre-outage history plus recent frames, D54), wait, or leave to
   the device, with backlog ordering oldest-first for append-only KV.
4. **Links are emulated in the harness per device** (bandwidth, RTT, outages), **identical across
   arms**, with a **synthetic** swept outage model: 10, 30, 60, 120 s, independent against
   correlated. D150 (4) labels it synthetic because **no outage traces exist** (P6). v5 carries that
   label into every outage number it reports; under CLAUDE.md check 6 a synthetic outage model is a
   declared construction and may not be reported as a census of real outages.
5. **Outage scenarios are evaluated AFTER the core v5 grid** (memory sweep, 3 s deadline). That is an
   ordering constraint from D150 (5), not a preference.

---

## 10. Triggers and the decision budget (D151 (5))

**Event-driven.** The counterfactual runs on: question arrival, completion, upload, memory pressure,
reconnect. There is **no per-period mirror**: state is rebuilt from the coordinator per decision.
That is a change from v4's 100 ms batched decision period (v4 section 9, D99) and it is what makes
the budget below meaningful, since a per-period mirror would amortise a slow planner invisibly.

**Budget: p99 < 20 ms at 32 devices, MEASURED.** Three things follow and v5 commits to all of them.

- The budget is a **measurement**, so the harness must instrument per-decision wall clock and the
  run report must carry the p99 **and the distribution**, not only the p99. Under CLAUDE.md check 3 a
  p99 reported alone hides the shape that would show a short-circuit.
- The budget is at **32 devices**, which is the size at which `study_covex_hardening.md` puts the
  idle-GPU feasibility ceiling at 0.8871, so the planner is being asked to be fast exactly where the
  problem is hardest.
- A decision that would exceed the budget **falls back to the base policy, `hybrid-F-lhreq-noc3`**,
  which is already the default execution path under D151 (1). The fallback is therefore free of a
  second mechanism, and its firing count is a reported quantity: an arm whose planner times out often
  is an arm running as `hybrid-F-lhreq-noc3` with extra steps, and the count is how a reader sees
  that. **The fallback must be to noc3 and never to C3-on hybrid-F**, because a timeout would
  otherwise re-enable a shortcut D152 (2) rules out, so a slow planner would silently change the
  representation policy as well as the timing policy.

Two-level fidelity (section 5.4) exists to meet this budget. If it cannot, the near-term exact window
shrinks and that is reported as a measured limit, not tuned away.

---

## 11. Evaluation: the robot headline (D152 (1))

**The robot headline is CORRECT ANSWERS DELIVERED**: the cloud's answer if it is on time, otherwise
the device's answer, **scored on the representation actually sent**, with **on-time reported beside
it**. Deficit counters stay on observable on-time (section 7.7).

The reason is measured, and it is the sharpest statement `study_frozen_test.md` produced (21.1, 21.3).
At a 3 s deadline, on post-fix cells, four seeds, 89 questions. **These are `dashcam-1f` cells
(D153), so the table is sensitivity and not a v5 headline**; what v5 takes from it is the shape of
the disagreement between the two columns, which does not depend on the dashcam format.

| arm | on time at 3 s | accuracy at 3 s |
|---|---|---|
| hybrid-F (post-fix) | **0.5281** | 0.3034 |
| eco-llm (post-fix) | 0.4270 | **0.2584**, last |
| hybrid-F6 (not redone) | 0.2809 | 0.3371 |
| b7-edf-feasibility | 0.2247 | **0.3146**, ahead of hybrid-F |
| mooncake | 0.2360 | 0.3146 |

**hybrid-F delivers 2.3 times b7's on-time rate and ends with slightly fewer correct answers.** Why:
of its 47 on-time cloud answers, 29 were D2 at 0.621 correct and **18 were RECENT at 0.111 correct**,
while b7 sends D2 only, so every on-time answer b7 delivers is a good one (21.2).

Three rules follow for every v5 report.

1. **On time alone is never the robot headline.** It is reported beside correct answers delivered,
   never instead of it.
2. **The representation actually sent is what is scored.** No accuracy table is consulted at scoring
   time; the cloud letter produced is compared to the gold letter (21.1). The table is a policy input,
   not a scorer input, and the two must not be allowed to meet.
3. **ONE DENOMINATOR: ALL ROBOT QUESTIONS.** D152 settles D147's pending item. The headline is over
   **all** robot questions and **cold feasibility is descriptive only**: it is reported as a
   description of the workload, never as a denominator and never as a bar. The two-denominator hedge
   an earlier draft of this spec carried is **withdrawn**, and G13 is closed. The description to
   report beside the headline is that at 3 s, 48 of 70 LH-REQ questions are feasible from cold with
   decode included and the history-token threshold is 13,193 (`study_frozen_test.md` 19.3), which
   tells a reader how much of the headline warming has to buy. It does not change what the headline
   divides by.

### 11.1 The 26 against 25 figure: reconciled, not a discrepancy (G6 CLOSED)

D151 (3) describes RECENT as "rarely worth it on LH-REQ: 26 % vs device 25 %". An earlier draft of
this spec flagged that as inconsistent with the committed DEV table, following
`study_frozen_test.md` 21.2. **It is not inconsistent. The numbers belong to different SPLITS, and
the confusion is entirely one of labelling.** All four quantities, with the split each belongs to:

| quantity | split | value | role |
|---|---|---|---|
| cloud D2 | **DEV** | 0.250 | what the reader consults |
| cloud RECENT | **DEV** | 0.107143 | what the reader consults |
| device 4B x RECENT | **DEV** | 0.107143 | what the reader consults |
| cloud RECENT | **EVAL** | **0.26087** | D151 (3)'s "26 %" |
| device 4B x RECENT | **EVAL** | **0.246377** | D151 (3)'s "device 25 %" |
| cloud D2 | EVAL | 0.536232 | measured, not read by the reader |
| cloud RECENT, live, questions actually sent as RECENT | EVAL subset | 0.111 to 0.118 | the selected longest histories, 21.2 |

So D151 (3) quotes the **EVAL** pair, 26.1 against 24.6, and the reader consults the **DEV** triple,
where cloud RECENT and the device are both 0.107143. **The reader is correct to use DEV**, because
D6 and D143 ruling A require the policy to be fitted on DEV while LH-REQ robots draw only from EVAL,
so no number the policy is fitted on is also a number it is scored on.

Three readings this closes:

- **There is nothing to reconcile and nothing was wrong.** D151 (3)'s figure, the DEV table and
  21.2's live 11 percent are three different quantities, and the only error was reading them as one.
- **The judgement D151 (3) draws is unchanged and holds on both splits.** On DEV cloud RECENT ties
  the device, on EVAL it exceeds it by only 1.5 pp, and on the questions actually sent as RECENT it
  falls to 11 percent. RECENT is rarely worth it on LH-REQ under every one of the three.
- **The rule for quoting, which is what this was always about:** never quote a RECENT or device
  accuracy without its split, and never place a DEV number beside an EVAL number in one comparison.
  The 11 percent is narrower still, an EVAL **subset** selected by history length, and must carry
  that too.

---

## 12. Gates before any live v5 run (D151 (6))

D151 (6): the cost model must be recalibrated on live data **including warm paths and batching
interference**, passing a held-out predicted-versus-actual check (D63); if it cannot, **the margin
widens and that is reported**.

**As of `8a8f592` the gate FAILS and v5 does not go live**
(`reports/study_policy_v2_gate.md`, the gate section, 345,066 committed requests over 26 cells).
Three findings, and the second is the one that governs the build order.

1. **Decode over-predicts by 25 to 32 percent in EVERY held-out class**: 1.298 by seed over all
   requests, 1.245 by seed on warm, 1.309 by seed on cold, 1.316 by arm. First token predicts
   acceptably out of sample, 0.94 to 1.07. **On the decode term alone the gate does not pass.**
2. **Warm is CONFOUNDED WITH ARM, and that is not a sample-size problem.** The visible figure is
   scarcity, 1,797 warm of 345,066 requests, 0.52 percent. The real finding is per cell:

   | cell | believed tier | engine `prefix_cache_hits` |
   |---|---|---|
   | `edf n16 s4` | gpu 358, cold 373 | 512,992 |
   | `llf n16 s4` | gpu 362, cold 373 | 424,224 |
   | `b7 n16 s4` | **cold 372, gpu 0** | **0** |
   | `hybrid-F-lhreq n16 s4` | **cold 372, gpu 0** | **0** |

   **Warm is not a condition that varies within an arm. It is a property of which arm is running.**
   edf and llf rebuild histories, reach a fully built state, take a GPU belief and show hundreds of
   thousands of engine prefix hits; b7 and the hybrids never rebuild, never take a GPU belief and
   show exactly zero. So the warm coefficient is **fitted entirely on edf and llf and would be
   applied to arms that never go warm**, and the zero held-out warm rows in the by-arm split are not
   a shortage, they are a statement that **the warm regime is unidentified out of arm**. The
   coordinator's belief and the engine's counters agree at cell level, which is itself reassuring.
3. **Therefore more cells of the existing arms cannot fix it.** Only an arm that goes **warm and
   cold under the same policy** can, which is exactly what **WARM-ALL plus LRU** is for. The
   ordering constraint stands and is now load-bearing rather than convenient: **WARM-ALL must run
   before the gate is retried.**

**And the gate must be refitted on the EP-G workload** (D153). Every cell in the current fit is
`dashcam-1f`, and EP-G changes both the request mix and the engine's occupancy, which is the
regressor the decode term reads. A gate passed on `dashcam-1f` would license a planner for a
workload v5 does not run.

The decode over-prediction has a modelling fix available without new data (a piecewise or log term in
overlap, fitted on the measured overlap buckets rather than as one line; the relation is convex,
0.024 s at 0 to 3 overlaps rising to 1.403 s above 45). The gate report deliberately has not made it,
because changing the model to improve a held-out ratio already seen is fitting to the test set. v5
adopts that discipline: the fix is **fitted on the cold data, held out by arm, and reported once
rather than tuned**.

### 12.1 v5 DOES NOT RUN BEFORE G8 IS RULED

D151 (6) says that if the cost model cannot pass, **the margin widens and that is reported**. That
provision does not apply yet, and the distinction matters:

**The gate cannot absorb G8.** D151 (1) requires the margin to be **fixed in advance and never
tuned**. A margin chosen after seeing the gate's held-out ratios is a margin fitted to the gate, and
a margin chosen to make v5 look safe is tuned by another name. So `MARGIN_CF` is a **user ruling**,
not a quantity the gate produces, and widening-on-failure can only move a margin that was already
ruled. **v5 does not run before G8 is ruled**, independently of whether the gate ever passes.

Two gates, then, and they are different kinds of thing:

| gate | kind | status |
|---|---|---|
| `MARGIN_CF` fixed by ruling (G8) | a decision, not a measurement | **OPEN, blocking** |
| D151 (6) cost model held out, incl. warm and EP-G | a measurement | **FAILS**, needs WARM-ALL first |

**Until both are cleared, every v5 number is reported with the margin's value and with the statement
that the never-worse-than-`hybrid-F-lhreq-noc3` property is conditional on cost-model error.**

---

## 13. Mechanism verification plan for the first v5 run

Recorded here so it is pre-registered, per CLAUDE.md, before any sweep.

**Step 1, the causal chain.** If maintenance of warm state is representation- and placement-dependent
(D150 STATE) and delivery is charged at completion (D146), then at a 3 s deadline (D147) a cold
history cannot be answered in time (19.2: 282 of 282 sent misses were cold), so a policy that warms
ahead by value (D149 (2)) raises `P(on time | D2)`, which raises the value of sending full history in
reader 1, which raises the count of on-time D2 answers at 0.62 correct and lowers the count of RECENT
answers at 0.11 correct (21.2), which raises **correct answers delivered** (D152 (1)).

**Step 2, the reads.** Every link must name the code that **uses** the value to change a decision,
not the place it is set. Six prior channels in live2 were found written and never read (`order`,
`desired_tier`, `RecallAction.representation` before `e924005`, B2's `z[RC]`, RCprio, and state value
that cancels between branches). The three reads v5 must exhibit:

| link | quantity | required read |
|---|---|---|
| value decides representation | `accuracy` from the committed table | the reader call whose return changes `RecallAction.representation` |
| value decides warm or keep | `gain` in reader 2 | the engine action actually issued, in session C's `engine_actions.py` |
| residency belief corrected | the engine's own reuse report | `telemetry_cached_tokens` is **not the right read**; see G9. Wiring it is necessary and not sufficient, and the stopping condition is the belief tracking residency, not the field being non-null |

**Step 2b, the switch.** Done for reader 1 in isolation (section 7.2: 30 of 121 decisions differ,
first difference named). **It must be re-run inside the arm, on one cell, before the sweep**, diffing
the decision logs of v5 against base hybrid-F and reporting the count and the first difference. If the
logs are identical the comparison has not been run and the result is an ABSENT LINK, never a negative.

**Step 3, the traced unit.** One robot question, end to end: history tokens, representation chosen,
reader values for every option, `P(on time)` predicted and realised, KV bytes and accelerator ms
charged, which budget bound the decision, completion timestamp, and the outcome as both on-time and
correct. If it cannot be produced, instrumentation comes before the sweep.

**Step 4, the negative controls.** Section 7.8's three perturbations inside the arm; plus `refresh_ms`
to zero, `kv_cap` to infinity and a flat `Q_TABLE` on one representative cell, per CLAUDE.md.

**Step 5, the alternative explanation.** The headline "v5 beats hybrid-F on correct answers delivered"
is also produced by **(b) pure timing**: v5's deferral putting answers into quieter decode windows,
which is exactly what 18.7.3 credits hybrid-F's existing advantage to and is **not** a value
mechanism. The data that distinguishes them is the **representation mix of the on-time answers**: the
value mechanism predicts the RECENT count falls toward zero while D2 on-time answers rise; pure timing
predicts the mix is unchanged and only the count rises. Both must be reported, and if the mix does not
move, the claimed mechanism is not the one operating.

---

## 14. Gaps recorded, not filled

**Amendment 2 status: G6, G12 and G13 CLOSED, G1 closed earlier, G3 and G8 STAY OPEN pending a user
ruling.** Four closures are recorded with their reconciliation rather than simply deleted, because a
gap that was flagged and then closed is the one a later reader is most likely to re-open by accident.

| id | gap | status |
|---|---|---|
| **G1** | `experiments/orchestration/live2/hybrid/value_reader.py` did not exist at `origin/main` (`fd396d1`) when section 7 was written, so the reader design was derived from D149, D151, D152 and the committed table. It landed at `44052f2` during this session and section 7.2 has been reconciled against it: the two agree. **Closed, with one follow-up**: that module's docstring quotes the device at about 25 percent against the table's 0.107143 (G6). | reconciled; follow-up with session D |
| **G2** | The flash working tree (`17bdf15`) is far behind `origin/main` (`8a8f592`) and lacks D106 to D152, `study_frozen_test.md`, `study_policy_v2_gate.md`, `study_sh_ep.md` and `lh_req_quality.json`. All reading was done from detached worktrees. **D153 is in no committed file at all**, and the section 8b floor counts are not yet in a committed results file. | recorded; a pull is a working-tree action, not this session's. D153's design-log row and the floor counts requested of session D |
| **G3** | The dashcam 1 s deadline is **D71 / `NEXAR_DEADLINE_S`**, already committed. D147 says the dashcam deadline is "to be settled with the short-horizon discussion" and does **not** set it. v5 **keeps 1.0 s** and marks it provisional. Note that D153 makes the deadline harder to leave unexamined: an EP-G instant carries a mean of 14.80 frames where a `dashcam-1f` instant carried one, so the 1.0 s was set against a workload v5 no longer runs. | **STAYS OPEN**, awaiting a user ruling |
| **G4** | **No accuracy band table by history length** (D149). 28 DEV questions, cloud RECENT Wilson [0.037, 0.272]; three bands would hold about nine questions each. None invented. P19 would make bands fittable. | open; blocked on P19 |
| **G5** | **No E-id exists for policy v5 or for these value readers** in `research/EXPERIMENTS.md`. CLAUDE.md requires one before a task proceeds; this session cannot create it because it does not own the file. | **blocking for any v5 sweep**; requested of session D |
| **G6** | **CLOSED, reconciled (section 11.1).** D151 (3)'s "26 % vs device 25 %" is the **EVAL** pair, cloud RECENT 0.26087 against device 0.246377. The reader consults the **DEV** triple, 0.250 / 0.107143 / 0.107143, and is correct to do so under D6 and D143 A. Different splits, not a discrepancy. The 21.2 live figure of 0.111 to 0.118 is a third quantity, an EVAL **subset** selected by history length. The standing rule that falls out: never quote a RECENT or device accuracy without its split, and never place a DEV number beside an EVAL number in one comparison. | **CLOSED** |
| **G7** | The device accuracy entry is a **declared substitution** (4B x RECENT standing in for device-on-D2, D87), and the DEV equality with cloud RECENT is arithmetic, not agreement (1 of 3 questions shared). | open; D146 already schedules the Orin replacement |
| **G8** | `MARGIN_CF = 0.05` is a **placeholder**. D151 (1) requires it fixed in advance and never tuned, which makes choosing it **a ruling and not something the gate can absorb**: a margin chosen after seeing the gate's held-out ratios is a margin fitted to the gate. **v5 DOES NOT RUN before G8 is ruled**, independently of whether the gate ever passes (section 12.1). | **STAYS OPEN, blocking**; needs a user ruling |
| **G9** | **RESTATED and harder than it looked.** `telemetry_cached_tokens` is positive in **none of 18,738** residency rows, and that is **not a broken write**: it is logged at `coordinator.py:756` on the history-build path only, so it never observes the dashcam traffic where the reuse happens, and is honestly zero on the slice it covers. **Wiring it will not by itself make the belief track residency.** The real phenomenon is already named in committed code at `coordinator.py:745-752`: a partially built history keeps a COLD readiness while its built prefix is reused on the wire, so an arm can be told COLD on a request the engine serves cheaply. The requirement is an outcome, a measured belief-versus-engine comparison over traffic including the dashcam path, not a non-null field. | **open and reframed**; session C owns `engine_actions.py` and should read this before wiring anything |
| **G10** | **RESTATED: the gate FAILS and the reason is CONFOUNDING, not scarcity.** Decode over-predicts by **25 to 32 percent in every held-out class**. Warm is 1,797 of 345,066 requests, but the governing fact is per cell: `edf n16 s4` has 358 gpu beliefs and 512,992 engine prefix hits, `llf` 362 and 424,224, while `b7` and `hybrid-F-lhreq` have **zero of both**. Arms that rebuild histories go warm; arms that do not, never do. So the warm coefficient is fitted entirely on edf and llf and applied to arms that never go warm, which is why the by-arm split has zero held-out warm rows: **the warm regime is unidentified out of arm**. **More cells of the existing arms cannot fix this.** Only an arm that goes warm and cold under the **same** policy can, which is WARM-ALL plus LRU. **And the gate must be refitted on the EP-G workload** (D153), since every cell in the current fit is `dashcam-1f`. | **blocking**; session C owns `arms_warmall.py` |
| **G11** | **SHARPENED: the in-arm acceptance test has now been run and DOES NOT DISCRIMINATE** (section 7.8). Flat, inverted and committed tables all give digest `5d3469549fead8ac`, because the reader sits in C3's fallback slot where the only candidate ever offered is RECENT. Classified **unexercised** under Rule 2, which is a failure of the test and not a pass of the mechanism. The precondition is the design change v5 was already making: **consult the reader at ADMISSION** over the full candidate set of section 5.1, which is where D151 (3) puts the robot decision. | open with a known remedy; needs sessions B and C |
| **G12** | **CLOSED by D153: N is EP-G as run** (append-only from 4 s before the first evaluated instant, capped at 21 frames = 10.0 s, mean 14.80 frames per request). Whether episodes enter the workload is no longer contingent on StudySH-EP either: D153 fixes the dashcam format **by the task** (section 8b). | **CLOSED** |
| **G13** | **CLOSED by D152: the headline is over ALL robot questions and cold feasibility is DESCRIPTIVE ONLY.** v5 reports **one** denominator; the two-denominator hedge an earlier draft carried is withdrawn (section 11, rule 3). | **CLOSED** |
| **G14** | Deficit counters steer on observable **on-time** while the headline is **correct answers delivered** (D152 (1)). A deliberate mismatch, kept because correctness is not observable at run time, recorded because a counter that cannot see accuracy cannot steer toward it. | recorded by design |
| **G15** | The 32k context limit, about 10 minutes of frames, is **out of scope** (D152 (3)); LH-REQ histories reach about 21k and the 3 s cold feasibility threshold is 13,193 tokens, so the two bounds are closer than the scoping suggests. | recorded; out of scope by decision |
| **G16** | `P(on time)` has no per-question committed measurement, so section 7's checks sweep it over a **declared synthetic grid**. Only the accuracies are committed. | recorded; resolved by the section 12 cost model once it passes |
| **G17** | **New, from D153.** Every committed cell is `dashcam-1f` and is sensitivity only, so **no EP-G measurement of any policy exists**. Section 11's robot table, section 2's warming conclusion and the section 12 cost-model fit are all on the superseded workload, and the EP-G numbers that replace them do not exist yet (section 8b.3). | open; the EP-G cells are scheduled in the frozen-test driver v8 |
| **G18** | **New, from StudySH-EP.** EP-G costs the **device** model 0.072 of challenge AP against its own one-frame condition, CI excluding zero, while buying the cloud model nothing (section 8b.2). D152 (1)'s headline credits the device's own answer whenever the cloud's does not arrive, so v5's dashcam format degrades the fallback it depends on. Fixed by the task under D153 and therefore not a choice v5 can make differently; it is a **limitation to report**, not a gap to close. | recorded by design |

---

## 15. What v5 needs from other work

**Session B (`experiments/orchestration/live2/v5/cf_*.py`, the counterfactual).**

1. Latest safe start as `deadline minus predicted service times a measured safety factor`, with
   **decode included** in predicted service (section 5.2), and re-plan on slip.
2. Per-decision horizons exactly as section 5.3, and two-level fidelity as section 5.4, with the
   split point declared per decision kind.
3. The margin taken from the single declared constant (`MARGIN_CF`), never from a per-cell argument,
   so "never tuned" is checkable from the code.
4. A per-decision wall-clock instrument emitting the **full distribution**, not only the p99, and a
   counter of planner-timeout fallbacks to base (section 10).
5. The counterfactual must maximise the **same** objective as the readers (section 7.1).

**Session C (`engine_actions.py`, `arms_warmall.py`).**

1. Expose warm, touch, and reload-just-in-time, plus hold-back and slicing of a cold rebuild, as
   actions reader 2 can score (section 8). Slicing applies to **background warming only**.
2. **Read G9 before wiring anything.** `telemetry_cached_tokens` is positive in none of 18,738
   residency rows because it is logged on the history-build path only (`coordinator.py:756`) and
   never sees the dashcam traffic where the reuse happens. Wiring it is necessary and **not
   sufficient**. What v5 needs is the outcome: the belief tracking residency on partially built
   histories, the case committed code already names at `coordinator.py:745-752`, proved by a measured
   belief-versus-engine comparison over traffic that includes the dashcam path.
3. `arms_warmall.py` (WARM-ALL plus LRU) is **the only arm that can go warm and cold under one
   policy**, which is what the gate's confounding (G10) requires and what no number of extra cells of
   the existing arms can supply. It is a **calibration instrument as well as a baseline** and must run
   before the cost-model gate is retried.
4. The WARM-ALL calibration cells and the gate refit must be on the **EP-G** workload (D153), not on
   `dashcam-1f`. The frozen-test driver v8 already switches at the next run boundary.

**Session D (`hybrid_arm.py`, the scorers, the reports, `EXPERIMENTS.md`, `INDEX.md`, `STATUS.md`).**

1. **An E-id row for policy v5 and for these value readers** (G5), and an `INDEX.md` row for
   `results/orchestration/live2/v5/value_readers_checks.json` and `value_readers_demo.json`, and the
   `STATUS.md` last-updated date. This session owns none of those files and did not edit them.
2. **A D153 row in `research/policy_design_log.md`**, and the section 8b minimum-frame floor counts
   in a committed results file. Both reach this spec only through the user amendment today (G2). As
   things stand, `research/STATUS.md` and `study_sh_ep.md` both read "dashcams stay one-frame" while
   this spec specifies EP-G, and a reader without D153 will take that as a contradiction rather than
   as the two different questions section 8b.2 shows them to be.
3. `hybrid/value_reader.py` landed at `44052f2` and agrees with section 7.2. Follow-up: its docstring
   quotes the device at "about 25 percent" beside a DEV table of 0.107143, which is exactly the
   split confusion section 11.1 closes, so the docstring should name the split. If the module and
   this spec ever diverge further, this spec is the thing to change, not the working code.
4. In the scorer, the robot headline as **correct answers delivered** with on-time beside it, scored
   on the representation actually sent and with **no accuracy table consulted at scoring time**
   (section 11, rule 2); **one denominator, all robot questions**, with cold feasibility reported as
   a description only (G13 closed by D152).
5. **Move the reader from C3's fallback slot to admission** in `hybrid_arm.py`, over the full
   candidate set of section 5.1. Until that happens D149 (4)'s acceptance test cannot discriminate
   and no v5 result may be read (G11, section 7.8).
6. A ruling on `MARGIN_CF` (G8) and on the dashcam deadline (G3). G6 needs no ruling any more.

---

## 16. Traceability

| section | decision |
|---|---|
| 2 deadlines | D147; dashcam from D71, still open under G3 |
| 3 three decision kinds | D151 (2) |
| 4 base = `hybrid-F-lhreq-noc3`, and the margin | D151 (1), D152 (2), D151 (6) |
| 5 request decisions, latest safe start, horizons, two-level fidelity | D151 (3), D151 (4) |
| 6, 7 value readers | D149 (1), (2), (3), (4); D152 (2) |
| 7.2 representation reader | D152 (2), D149 (2) |
| 7.6 episode continuity | D149 (3), D148 |
| 7.8 acceptance test, and why it does not yet discriminate | D149 (4), D151 (3) |
| 8 state under no-pin | D150 STATE |
| 8b dashcam path = EP-G, fixed by the task, and the minimum-frame floor | **D153**, D148; StudySH-EP (D145) cited as a finding |
| 9 sync and outages | D150 SYNC (1) to (5), D54 |
| 10 triggers and budget | D151 (5) |
| 11 robot headline, one denominator | D152 (1), D146, D152 closing D147's pending item |
| 11.1 the DEV / EVAL split reconciliation | D151 (3), D143 A, D6 |
| 12 gates, and 12.1 v5 does not run before G8 is ruled | D151 (6), D151 (1), D63, D153 |
| 13 mechanism verification | CLAUDE.md, and D149 (4) for Step 4 |
| supporting measurements | `study_frozen_test.md` 18 to 21 (all `dashcam-1f`), `study_policy_v2_gate.md` (the value-reader and gate sections at `8a8f592`), `study_sh_ep.md` 13, `lh_req_quality.json` |

Artefacts: `experiments/orchestration/live2/v5/value_readers.py`,
`results/orchestration/live2/v5/value_readers_checks.json`,
`results/orchestration/live2/v5/value_readers_demo.json`.
