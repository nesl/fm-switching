# Scheduling policy: specification v5

Written 2026-11-20 from design-log decisions **D145 to D152 inclusive**, which are the source for
everything in this document. v5 supersedes v4 (`research/policy_spec_v4.md`, D59) for the parts it
restates and leaves every other part of v4 standing unchanged.

Nothing in this document is a result. It is a specification plus the value-reader design D149 and
D152 call for, with the arithmetic of that design checked offline in
`experiments/orchestration/live2/v5/value_readers.py` and
`results/orchestration/live2/v5/value_readers_checks.json`. Section 14 lists every place a gap was
recorded rather than filled, and section 15 lists what v5 needs from other work before it can run.

**Provenance of the source text.** The decisions D106 to D152, `reports/study_frozen_test.md`,
`reports/study_policy_v2_gate.md`, `reports/study_lh_req.md` and
`results/orchestration/live2/lh_req/lh_req_quality.json` were read from a detached worktree at
`origin/main`, first at `fd396d1` and then at `44052f2`. The flash working tree was at `17bdf15`
when this was written and does not contain them. Every quoted number below is from `44052f2`, and
`experiments/orchestration/live2/v5/value_readers.py` reproduces its own outputs identically at both
bases.

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

**The base policy is hybrid-F and it is EXECUTED BY DEFAULT.** The counterfactual runs beside it and
its choice is taken **only when its predicted gain beats the base's by a margin fixed in advance and
never tuned**. So v5 is never worse than hybrid-F up to cost-model error, which is the property
D151 (1) is buying, and the margin is what pays for it.

- The margin is a declared constant, `MARGIN_CF` in `v5/value_readers.py`, in units of the objective
  (expected correct on-time answers). Its current value, 0.05, is a **placeholder awaiting a ruling**
  and is recorded as gap G8. It is declared as a constant rather than a parameter precisely so that
  changing it is a visible edit and not a sweep.
- D151 (6) widens the margin if the cost model cannot pass its gate, **and that is where v5 stands
  today**: the gate does not pass and cannot pass on committed data (section 12).
- "Never tuned" is an auditable claim, not a promise. The v5 run report must show the margin's value
  and that it is the same value in every cell, and must not report a margin sweep as a result.

**What "never worse than hybrid-F" does and does not mean.** It is bounded by cost-model error, and
the cost model's decode term currently over-predicts the hybrids by 1.343 held out by arm
(`study_policy_v2_gate.md` section 3). A planner that over-estimates decode by a third defers work
it could have released. The guarantee is therefore conditional on section 12's gate, and v5 may not
claim it before the gate passes.

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

Episode context itself is fixed by D148: append-only KV, never a sliding window (which forces a full
recompute), refreshed with a fresh context after N seconds with no overlap, N from StudySH-EP
(EP-B 5 s against EP-G about 10 s), discarded on idle by LRU or timeout as vLLM already does.
Consequence carried into section 8: each dashcam holds persistent KV of about 3.4 to 6.8k tokens,
competing with robot histories for the 62,944-token GPU pool.

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

**The acceptance test as v5 must run it** is therefore: the same three perturbations applied inside a
live or trace-driven v5 arm, scored on correct answers delivered, with the number of decisions
changed **and** the change in the headline both reported. If decisions change and outcomes do not,
that is CLAUDE.md's `unscorable` or `fired and did not help`, and the report must say which. A v5 run
may not be read before this has run inside the arm.

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
cached-token count** corrects the belief. D150 names the specific defect to repair: the dead
`telemetry_cached_tokens` read is to be wired. Until it is, residency is a prediction with no
correction, and under CLAUDE.md's write-only-field rule an uncorrected belief is exactly the shape
that passes every surface check while implementing nothing. Recorded as gap G9; the file is owned by
session C.

**An external KV store (a KV connector) for hard guarantees is explicitly a later extension, not
v5.** v5 may not assume one and may not report a result that depends on one.

Capacity context, from D148: each dashcam's persistent episode KV of about 3.4 to 6.8k tokens
competes with robot histories for the 62,944-token GPU pool, so the memory sweep of section 12 is
where the warm-ahead conclusion of section 2 is actually tested.

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
- A decision that would exceed the budget **falls back to the base policy**, hybrid-F, which is
  already the default execution path under D151 (1). The fallback is therefore free of a second
  mechanism, and its firing count is a reported quantity: an arm whose planner times out often is an
  arm running as hybrid-F with extra steps, and the count is how a reader sees that.

Two-level fidelity (section 5.4) exists to meet this budget. If it cannot, the near-term exact window
shrinks and that is reported as a measured limit, not tuned away.

---

## 11. Evaluation: the robot headline (D152 (1))

**The robot headline is CORRECT ANSWERS DELIVERED**: the cloud's answer if it is on time, otherwise
the device's answer, **scored on the representation actually sent**, with **on-time reported beside
it**. Deficit counters stay on observable on-time (section 7.7).

The reason is measured, and it is the sharpest statement `study_frozen_test.md` produced (21.1, 21.3).
At a 3 s deadline, on post-fix cells, four seeds, 89 questions:

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
3. **The denominator is stated.** D147 leaves open whether the D133 feasible-question headline moves
   to all robot questions; 21.3 argues it should and that the accuracy column should move with it.
   At 3 s the feasible denominator is 48 of 70 (19.3), so a bar over feasible questions is a bar over
   a two-thirds subset chosen by history length. v5 reports **both denominators** until D147's pending
   item is settled, and marks which is which. Recorded as gap G13.

**The 26 against 25 figure is flagged, not reconciled.** D151 (3) describes RECENT as "rarely worth
it on LH-REQ: 26 % vs device 25 %". The committed DEV table gives cloud D2 0.250, cloud RECENT
0.107143 and device 0.107143; measured on EVAL, `study_frozen_test.md` 21.2 gives cloud RECENT 0.111
to 0.118 and cloud D2 0.619 to 0.650. 21.2 flagged the discrepancy rather than reconciling it,
because both figures are the user's, and v5 does the same. **The judgement D151 (3) draws from it,
that RECENT is rarely worth it on LH-REQ, is confirmed by a wider margin than the quoted figure
suggests**, so the discrepancy does not change any decision in this spec; it changes what may be
quoted. Recorded as gap G6.

---

## 12. Gates before any live v5 run (D151 (6))

D151 (6): the cost model must be recalibrated on live data **including warm paths and batching
interference**, passing a held-out predicted-versus-actual check (D63); if it cannot, **the margin
widens and that is reported**.

**As of `fd396d1` the gate does NOT pass and cannot pass on committed data**
(`reports/study_policy_v2_gate.md` section 0). Two failures:

1. **The warm path cannot be held out at all.** Of 304,867 committed cloud requests across 23
   sixteen-device cells, **720 are warm (0.236 percent)** and all 720 sit in two cells, `llf_n16_s4`
   and `edf_n16_s4`. Every held-out split contains **zero** warm requests. v5's whole premise is warm
   state, so its cost model is being asked to price a regime with no validation set.
2. **Cross-policy transfer on decode is 34 percent off.** Fitting on the non-hybrid arms and
   predicting the hybrids, the decode term over-predicts by **1.343**. Decode is the term that decides
   a 3 s deadline.

**Ordering constraint that v5's build order must carry** (gate report sections 4 and 5): the gate's
held-out warm set does not exist until the WARM-ALL plus LRU baseline arm has run, so **that arm must
run before the gate**, and it is a calibration instrument as well as a baseline. The alternative is to
split the gate explicitly into a cold half that passes now and a warm half that waits.

The decode convexity is a modelling fix available without new data (a piecewise or log term in
overlap, fitted on the six measured overlap buckets). The gate report deliberately has not made it,
because changing the model to improve a held-out ratio already seen is fitting to the test set. v5
adopts that discipline: the fix is **fitted on the cold data, held out by arm, and reported once
rather than tuned**.

**Until the gate passes, every v5 number is reported with the margin's value and the statement that
the never-worse-than-hybrid-F property is conditional.**

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
| residency belief corrected | `telemetry_cached_tokens` | currently **dead**; gap G9 is a stopping condition until it is wired |

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

| id | gap | status |
|---|---|---|
| **G1** | `experiments/orchestration/live2/hybrid/value_reader.py` did not exist at `origin/main` (`fd396d1`) when section 7 was written, so the reader design was derived from D149, D151, D152 and the committed table. It landed at `44052f2` during this session and section 7.2 has been reconciled against it: the two agree. **Closed, with one follow-up**: that module's docstring quotes the device at about 25 percent against the table's 0.107143 (G6). | reconciled; follow-up with session D |
| **G2** | The flash working tree (`17bdf15`) is behind `origin/main` (`fd396d1`) and lacks D106 to D152, `study_frozen_test.md`, `study_policy_v2_gate.md` and `lh_req_quality.json`. All reading was done from a detached worktree. | recorded; a pull is a working-tree action, not this session's |
| **G3** | The dashcam 1 s deadline is **D71 / `NEXAR_DEADLINE_S`**, already committed. D147 says the dashcam deadline is "to be settled with the short-horizon discussion" and does **not** set it. v5 uses 1.0 s and marks it provisional. | open, awaiting the short-horizon discussion |
| **G4** | **No accuracy band table by history length** (D149). 28 DEV questions, cloud RECENT Wilson [0.037, 0.272]; three bands would hold about nine questions each. None invented. P19 would make bands fittable. | open; blocked on P19 |
| **G5** | **No E-id exists for policy v5 or for these value readers** in `research/EXPERIMENTS.md`. CLAUDE.md requires one before a task proceeds; this session cannot create it because it does not own the file. | **blocking for any v5 sweep**; requested of session D |
| **G6** | D151 (3)'s "26 % vs device 25 %" does not match the committed DEV table (0.250 / 0.107143 / 0.107143) or the EVAL measurement (0.111 to 0.118 against 0.619 to 0.650). Flagged, not reconciled, as `study_frozen_test.md` 21.2 flagged it; both figures are the user's. | open, needs a ruling |
| **G7** | The device accuracy entry is a **declared substitution** (4B x RECENT standing in for device-on-D2, D87), and the DEV equality with cloud RECENT is arithmetic, not agreement (1 of 3 questions shared). | open; D146 already schedules the Orin replacement |
| **G8** | `MARGIN_CF = 0.05` is a **placeholder**. D151 (1) requires it fixed in advance and never tuned, which makes choosing it a ruling and not a sweep. | **blocking**; needs a user ruling before any v5 run |
| **G9** | The residency belief has **no correction** until the dead `telemetry_cached_tokens` read is wired (D150). An uncorrected belief is the write-only-field shape CLAUDE.md names. | open; session C owns `engine_actions.py` |
| **G10** | **The D151 (6) cost-model gate does not pass and cannot pass on committed data**: zero held-out warm requests, decode over-predicted 1.343 held out by arm. The WARM-ALL plus LRU arm must run first. | **blocking**; session C owns `arms_warmall.py` |
| **G11** | D149 (4)'s acceptance test is demonstrated **on the reader in isolation only**. It has not been run on outcomes inside an arm, which is what the decision asks for. | open; needs sessions B and C |
| **G12** | D148's episode refresh period N is **not fixed**: EP-B 5 s against EP-G about 10 s, pending StudySH-EP, which is pre-registered with no result. Whether episodes enter the workload at all follows StudySH-EP's pre-registered rule. | open; blocked on StudySH-EP |
| **G13** | D147's pending item, whether the D133 headline moves to all robot questions with cold feasibility reported as a description, is **not settled**. v5 reports both denominators meanwhile. | open, needs a ruling |
| **G14** | Deficit counters steer on observable **on-time** while the headline is **correct answers delivered** (D152 (1)). A deliberate mismatch, kept because correctness is not observable at run time, recorded because a counter that cannot see accuracy cannot steer toward it. | recorded by design |
| **G15** | The 32k context limit, about 10 minutes of frames, is **out of scope** (D152 (3)); LH-REQ histories reach about 21k and the 3 s cold feasibility threshold is 13,193 tokens, so the two bounds are closer than the scoping suggests. | recorded; out of scope by decision |
| **G16** | `P(on time)` has no per-question committed measurement, so section 7's checks sweep it over a **declared synthetic grid**. Only the accuracies are committed. | recorded; resolved by the section 12 cost model once it passes |

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
2. **Wire the dead `telemetry_cached_tokens` read** (G9). This is a Step 2 stopping condition.
3. `arms_warmall.py` (WARM-ALL plus LRU) is the only thing that produces warm requests in quantity,
   so it is a **calibration instrument as well as a baseline** and must run before the cost-model
   gate (G10). The cells the gate report asks for are listed in its section 4.

**Session D (`hybrid_arm.py`, the scorers, the reports, `EXPERIMENTS.md`, `INDEX.md`, `STATUS.md`).**

1. **An E-id row for policy v5 and for these value readers** (G5), and an `INDEX.md` row for
   `results/orchestration/live2/v5/value_readers_checks.json` and `value_readers_demo.json`, and the
   `STATUS.md` last-updated date. This session owns none of those files and did not edit them.
2. `hybrid/value_reader.py` landed at `44052f2` and agrees with section 7.2; the only follow-up is
   its docstring's "about 25 percent" device figure against the table's 0.107143 (G6). If the two
   ever diverge further, this spec is the thing to change, not the working code.
3. In the scorer, the robot headline as **correct answers delivered** with on-time beside it, scored
   on the representation actually sent and with **no accuracy table consulted at scoring time**
   (section 11, rule 2); and both denominators reported until G13 is settled.
4. A ruling on `MARGIN_CF` (G8) and on D151 (3)'s 26 against 25 figure (G6).

---

## 16. Traceability

| section | decision |
|---|---|
| 2 deadlines | D147; dashcam from D71, flagged under G3 |
| 3 three decision kinds | D151 (2) |
| 4 base and margin | D151 (1), D151 (6) |
| 5 request decisions, latest safe start, horizons, two-level fidelity | D151 (3), D151 (4) |
| 6, 7 value readers | D149 (1), (2), (3), (4); D152 (2) |
| 7.2 representation reader | D152 (2), D149 (2) |
| 7.6 episode continuity | D149 (3), D148 |
| 7.8 acceptance test | D149 (4) |
| 8 state under no-pin | D150 STATE |
| 9 sync and outages | D150 SYNC (1) to (5), D54 |
| 10 triggers and budget | D151 (5) |
| 11 robot headline | D152 (1), D146 |
| 12 gates | D151 (6), D63 |
| 13 mechanism verification | CLAUDE.md, and D149 (4) for Step 4 |
| supporting measurements | `study_frozen_test.md` 18 to 21, `study_policy_v2_gate.md`, `lh_req_quality.json` |

Artefacts: `experiments/orchestration/live2/v5/value_readers.py`,
`results/orchestration/live2/v5/value_readers_checks.json`,
`results/orchestration/live2/v5/value_readers_demo.json`.
