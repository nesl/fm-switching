# Cascade threshold calibration: one threshold per confidence type, on DEV, per card

D164 and the user ruling of 2026-11-22 item 2. **Pre-registration committed BEFORE any threshold
was computed**: `research/prereg_cascade_calibration.md`, commit `d8b88619`, pushed before the fit
ran (the fit's own `_provenance.git_commit` is `d8b8861`, which is the audit trail for the order).

Code `experiments/orchestration/live2/cascade_threshold_calibration.py`. Results
`results/orchestration/live2/cascade_calibration/` (`cascade_thresholds.json`,
`cascade_calibration_proofs.json`, `cascade_calibration_audit.json`). CPU only, dry cells, no GPU
and no new measurement.

---

## 0. Headline

**One of the three arms could be calibrated as its card specifies, and it passed every proof.**

| arm | card's method for a threshold | calibrated? | ready? |
|---|---|---|---|
| `confidence-cascade` | median committed device confidence over DEV questions (amendment 2); the (1 - rate) quantile of DEV negatives for `tau_trigger` (A2) | **YES, four types on DEV** | **YES** |
| `cascade-routing` | lambda fitted OFFLINE so expected cost meets a cost budget B | **NO: there is no B in live2** | **NO**, and it also fails the port rule |
| `eco-llm` | none; the card specifies no threshold and the arm reads no confidence | **NOTHING TO CALIBRATE** | **NO** (the gate is inapplicable; release is a user ruling) |

Two of the three outcomes are refusals, and both are reportable results rather than unfinished
work: section 0 of the pre-registration fixed in advance that a silent card or a missing target
quantity would produce a refusal and not an invented number.

---

## 1. The confidence types, and which are expressible

| type | signal | source | expressible in live2? |
|---|---|---|---|
| `robot` | letter-probability mass on the emitted letter, 4B-D2 | StudyE7 Job A | yes |
| `ss_mcq` | the same rule, single shot | StudySS2 re-record | yes |
| `ss_free_form` | geometric mean token probability | StudySS2 re-record | yes |
| `ss_point` | the same, over coordinate digits, **WEAK** | StudySS2 re-record | yes, flagged |
| `episodic` | `StreamState.latest_score()` | StudyD3 DEV negatives | **NO, see section 4** |

They are not one scale. The robot and mcq values are a probability mass on one token; the
free-form and point values are a geometric mean over several. A single floor across them is not a
stricter or a looser operating point, it is a different one per type by accident, which is what
D164 asked to remove.

The type is resolved at decision time by `device_confidence.kind_of(q.question_id)`, from the same
committed row that supplies the value. The harness's `RecallQuery.category` carries the DATASET for
a single-shot question but not the SUBSET, so it cannot separate `ss_mcq` from `ss_free_form`.

## 2. The fitted values

| type | DEV population | n | min | median = **floor** | max |
|---|---|---|---|---|---|
| `robot` | LH-REQ DEV (D143 A), 28 ids, 28 with a value | 28 | 0.365808 | **0.800338** | 0.999748 |
| `ss_mcq` | StudySS2 committed 30/70 DEV part | 131 | 0.333333 | **0.985936** | 1.0 |
| `ss_free_form` | the same | 98 | 0.588367 | **0.984783** | 1.0 |
| `ss_point` | the same, WEAK | 83 | 0.693107 | **0.817276** | 0.879621 |
| `episodic` | StudyD3 DEV negatives, rate 0.20 | 3,000 | -20.25 | **-7.000911** (`tau_trigger`) | -0.005234 |

No prereg failure condition fired for any type: every n is at or above the pre-registered
minimum of 10, no floor sits at or below its own DEV minimum or above its maximum, and no DEV
signal is constant (distinct values 28 / 121 / 94 / 74 / 2,853).

**Cross-check against committed values (consistency check 1).**

| quantity | this run | prior committed | source | ratio | agree |
|---|---|---|---|---|---|
| `tau_trigger` | -7.000911 | -7.0009 | cards/cascade.md hyperparameter table | 1.000 | yes |
| recall floor, S-EMBER DEV scalar | 0.735834 | 0.7358 | cards/cascade.md amendment 2 | 1.000 | yes |
| recall floor, robot type | 0.800338 | 0.7358 (different population) | the same | 1.088 | explained |

The third row is the one change, and it is a POPULATION change, not a method change: amendment 2
took the median over all S-EMBER DEV questions, while D143 A fits the robot table on LH-REQ DEV,
the DEV counterpart of the LH-REQ EVAL questions a live cell's robots actually draw from. The
committed scalar reproducing to four decimals through the same code path is the **positive
control** on this pipeline (consistency check 7): the check that would have caught a broken
reader did not fire.

## 3. Proofs, on the posted D164 workload

Cell: 16 devices, ratio 40:40:20, `lh_req` + `ss2`, EP-G dashcam, per-frame upload, rq30 re-asks,
seed 4, 1,200 s, dry. **One cell per process**, because a dry cell does not reproduce twice inside
one process.

**P0, the identity control, ran BEFORE any comparison was read.** The same configuration in two
separate processes: digest `b9290071679f1baa` both times, 12,253 rows both times. So the
cross-process comparison register is sound, and a digest difference below means a decision moved.

**P1, the characteristic decision, non-zero IN BOTH DIRECTIONS.** 489 confidence-bearing recall
decisions, 0 with no confidence, 0 of unresolved type:

| type | escalate CLOUD (confidence below floor) | stop DEVICE (at or above) |
|---|---|---|
| `robot` | 44 | 88 |
| `ss_mcq` | 74 | 70 |
| `ss_free_form` | 44 | 50 |
| `ss_point` | 61 | 58 |
| **total** | **223** | **266** |

This is the proof D164 asked for. The saturation it was imposed to prevent
(`reports/study_saturation_knee.md`: 4 of 5 cascade arms saturated on the robot side) does not
occur for any type.

**P2, Step 2b, per type.** Two cells differing only in that one type's floor, 0.0 (never escalate
on confidence) against 1.0 (always):

| type | differing decisions, setwise | first difference | counts lo -> hi |
|---|---|---|---|
| `robot` | 264 | `(1014.9, 'decline', ('opp0010346',))` | 0/132 -> 132/0 |
| `ss_mcq` | 262 | `(1011.0, 'decline', ('opp0010302',))` | 0/144 -> 131/13 |
| `ss_free_form` | 178 | `(1001.0, 'decline', ('opp0010201',))` | 0/94 -> 89/5 |
| `ss_point` | 238 | `(1003.8, 'decline', ('opp0010228',))` | 0/119 -> 119/0 |

Every type moves decisions, so no fitted threshold is a write-only field. The table also carries
an unplanned **per-type isolation control**: when one type's floor moves, the other three types'
counts are unchanged to the unit, so the per-type dispatch routes each query to its own floor and
to no other. The two cases that do not reach 0 at a floor of 1.0 are the questions whose committed
confidence is exactly 1.0 (13 mcq, 5 free-form), where `c < 1.0` is false; that is the rule
behaving as written, on a signal that saturates at 1.

## 4. `tau_trigger` is UNEXPRESSIBLE in live2, and the instrumented quantity says so

The quantity the episodic threshold is compared against is `StreamState.latest_score()`, which in
live2 is a **placeholder**: `coordinator._device_answer` appends `(t, 0.0)` and the cloud path
appends `(delivered, 0.0)`, with the comment "the SCORES here are placeholders: task value is
scored offline from the recordings (D85, D87)". Instrumented on the proof cell, the arm saw
exactly two distinct values in 72,000 stream reads: `None` 1,156 times and `0.0` 70,844 times.

Since `-7.0009 < 0.0`, the test `v >= tau_trigger` is TRUE for every stream that has delivered
anything, so the episodic side escalates unconditionally and **no value of `tau_trigger` below
zero changes it**. Under CLAUDE.md Rule 2 this is **unexpressible**, not a negative: the mechanism
fires and the harness discards the channel it acts through. It is a constant where a distribution
is expected (consistency check 3), and the pre-registration named this exact risk before the run.

The card's `-7.0009` stands for the A-episodic setting where it was measured. A reader must not
attribute live2 episodic behaviour to it. This arm's card claims A-episodic only, so live2 rows for
it are already outside its claimed scope, which `arms_published.OUT_OF_CARD_SCOPE` publishes.

## 5. `cascade-routing`: not calibratable as its card specifies, and it fails the port rule

**(a) The method cannot be expressed.** The card's calibrated quantity is lambda and the method is
the paper's: lambda is set OFFLINE so that expected cost meets a cost budget B. The card says so
explicitly, and uses it to justify not adding B to the shared observation schema. **live2 has no
such B**: `coordinator.py:321` sets `gpu_budget_s = window_s x 1.0` GPU-second per second and its
own comment calls this the PHYSICAL CAPACITY which "never binds artificially" (D58: round 1 has no
fixed budget); D174 (1)'s census found budget refusals ZERO in every committed cell. The quantity
the paper's calibration targets does not exist here, so no lambda was fitted and `lambda_base`
stays at its committed 0.02, labelled an UNFITTED CONSTANT. A per-confidence-type lambda was also
out of scope by pre-registration: the paper specifies one lambda for the query stream.

**(b) It has no fitted confidence threshold at all.** Its escalation test is
`q_cloud - (Q_DEVICE + (1 - Q_DEVICE) * conf) - lambda * c_cloud > 0`. The implied confidence
threshold is a consequence of the committed quality priors and the cost curves, not a parameter.

**(c) Its characteristic decision occurs ZERO times.** On the same posted cell, all **489** recall
decisions are `cascade_stopped_posthoc`, and `route_cloud_direct = 0`,
`route_device_stop = 0`, `cascade_started = 0`, `cascade_escalated = 0`, `cloud_infeasible = 0`.
The arm's reason to exist is the skip-or-cascade CHOICE over the three supermodels, and that
ex-ante branch is **never reached**: since D159 (D) the harness supplies a committed device
confidence for every question, robot and single-shot alike, so `conf is not None` on arrival and
the post-hoc branch takes every query. It then stops on the device every time.

Why it always stops, which is a scale mismatch and not a tuning question:
`q_dev_post = Q_DEVICE + (1 - Q_DEVICE) * conf` maps a CONFIDENCE onto the same axis as an
ACCURACY prior. At a typical committed confidence of about 0.85 that yields an implied device
accuracy near 0.90, against `Q_CLOUD_RICH = 0.3953`, so the marginal gain is large and negative
whatever lambda is. **Step 2b on lambda confirms it: `lambda_base` 0.02 against 2.0 gives the
identical digest `2af9400f672aa1c1` and 0 differing decisions.** So lambda is both unfitted and
inert, and the saturation is structural.

Under CLAUDE.md's port rule ("a port's proofs must include that its characteristic decision occurs
at least once") this arm **may not be scored**. It is NOT marked ready, and the remedy is a design
question for the user, not a calibration: re-scaling the post-hoc update, or supplying the ex-ante
branch with queries that have no confidence yet, would both be changes to the method the card
declares.

## 6. `eco-llm`: the card specifies no threshold, and the matrix's premise is wrong for it

**Its characteristic decision does occur**, and is recorded here so the ruling has the number:
on the same audit cell it makes 240 joint (tier, representation) recall selections, 210 CLOUD/D2
and **30 CLOUD/RECENT**, so both representations are selected and the selection is not degenerate.
It is not blocked by anything this session found.

`cards/ecollm.md` specifies no threshold calibration, and the arm **does not declare
`reads_device_answer`**, so it never receives a device confidence. Its rule is
`select = max(feasible, key=(quality, -cost))` under `SLO(max_latency_s = the query's own
deadline, max_cost_gpu_s = the remaining budget, min_quality = None)`. The SLOs are "user-defined"
in the paper and are taken from the observation here. There is no quantity for a DEV fit to set,
and per section 0 nothing was invented.

So BASELINE_MATRIX's "These three escalate on a device-confidence threshold" is **wrong for
eco-llm**: it escalates on nothing of the kind, and the gate that blocks its cells is inapplicable
rather than unmet. Releasing it is therefore a one-line user ruling and not a calibration outcome,
which is why this session did not uncomment it.

The two standing requirements on it were re-verified rather than assumed: `USE_MEASURED_QUALITY`
is True, so D137 (3)'s committed measured table is in force (RECENT 0.3963, D2 0.4286, RICH
0.4255), and `_rep_tokens` reads the offered `EvidenceItem.tokens`, so D135 (2) holds, it plans
with the price it is charged. Both are still subject to the card's own limitation, that quality is
consumed only as an ORDER and price reaches a decision only through feasibility.

## 7. The device wait (D168 / D155 (5))

Verified rather than trusted. `coordinator.DEVICE_WAIT_MEASURED` is True and `_device_wait_s`
resolves a MEASURED value by type (dashcam EP-G warm-append by episode position, robot ORIN-REC
WARM per question, single-shot StudySS2 per question), with every fallback path counted
separately. The coordinator instance of one dry cell per arm was captured and its own counters
read (`cascade_calibration_audit.json`; the same posted workload at seed 4, **600 s**, so these
counts are smaller than section 3's 1,200 s cell):

| arm | measured lookups | dashcam | robot | single shot | any `no_measured_value_*` counter |
|---|---|---|---|---|---|
| `confidence-cascade` | 18,364 | 18,223 | 46 | 95 | **absent, so zero** |
| `cascade-routing` | 18,463 | 18,223 | 63 | 177 | **absent, so zero** |
| `eco-llm` | n/a | n/a | n/a | n/a | n/a: it does not wait for a device answer |

**No cascade arm reads the superseded 0.567 s proxy on any request of this cell**: not one of the
four `device_wait_no_measured_value_*` counters appears at all, which is the zero the counter was
added to make visible. So the D168 / D155 (5) blocker is clear for both device-waiting arms, and
what held them was only the threshold calibration, exactly as `runs/DEVWAIT_READY` states.

**One stale label found and NOT changed.** `scorer/score.py:cascade_device_wait()` computes
`measured_device_wait_applied` as `abs(C.DEV_LAT_S - DS.DEVICE_WAIT_MEASURED_S) <= 1e-9`, which
compares two CONSTANTS and so still reports `proxy-0.567` even though the coordinator now takes
the measured per-question table. The label is wrong in the direction of understating the fix, it
affects every cascade-style arm's score header equally, and changing it would relabel committed
cells, so it is reported here for the user rather than edited.

## 8. Mechanism verification, Steps 1 to 5

**Step 0, what would make this run uninterpretable.** Asked before the run: is the comparator
about to change (no), does a default get restored (no), is the thresholded quantity constant in
this regime (**yes for the episodic type**, which is why it was named as a failure condition in the
pre-registration and measured in section 4), and does the harness reproduce a cell (**no inside one
process**, hence one cell per process and the P0 control).

**Step 1, the causal chain.** If the device's answer confidence is informative and its scale
differs by confidence type (StudySS2's own `rule` field: letter mass against geometric mean token
probability), then a cascade whose escalation floor is fitted per type on DEV will escalate the
queries whose own-type confidence is low and stop on the device for the rest, so both branches of
FrugalGPT's stop rule occur, and the arm's cloud load reflects its confidence signal rather than a
missing-data default. Each link is grounded in `cards/cascade.md` (the scorer's role and the
median-on-DEV procedure) and in D159 (D) (the confidence is supplied per question).

**Step 2, the links instantiated.**

| causal link | implementing quantity | value / range | varies as expected? | evidence |
|---|---|---|---|---|
| confidence exists per query | `RecallQuery.device_answer_confidence` | 489 of 489 supplied, 0 absent | yes | P1, `no_confidence_device = 0` |
| the type is known | `device_confidence.kind_of` | 4 types, 0 unresolved | yes | P1, `unknown_type = 0` |
| the floor differs by type | `confidence_floors` | 0.800338 / 0.985936 / 0.984783 / 0.817276 | yes | section 2 |
| the floor decides | `_floor_for` read in `decide` | 223 CLOUD, 266 DEVICE | yes | P1, P2 |
| the episodic score decides | `StreamState.latest_score()` | **CONSTANT 0.0** (2 values, one of them None) | **NO** | section 4, **UNEXPRESSIBLE** |

The episodic row is a stopping condition for the episodic claim, and is reported as such rather
than being folded into the result. The four recall rows pass.

**Step 3, one traced unit.** The per-type tally of section 3 is the unit-level trace for the
recall side: each of the 489 decisions is one query, with its type, its committed confidence, its
type's floor and its CLOUD-or-DEVICE outcome, and the two directions sum to the total with no
residue (223 + 266 = 489, 0 unclassified).

**Step 4, the negative control.** Setting a type's floor to 0.0 disables escalation for that type
and the result collapses to the null for that type exactly: `robot` 44 CLOUD -> 0,
`ss_mcq` 74 -> 0, `ss_free_form` 44 -> 0, `ss_point` 61 -> 0, with the other three types unchanged
each time. For `cascade-routing` the control is the lambda sweep, and it does NOT change the
result (0 differing decisions), which is how section 5 concludes that lambda is not driving
anything there.

**Step 5, the alternative explanation.** "Both branches now occur" could be produced by (a) the
per-type floors landing near the middle of each type's own distribution [the claimed mechanism], or
(b) any floor whatever, if the confidence distribution happened to straddle it. These are
distinguished by the Step 2b table: at 0.0 and at 1.0 the arm saturates in one direction, so the
split is a property of where the fitted floor sits inside its own type's distribution, which is
what a median operating point is. What the experiment canNOT distinguish is whether the median is
the BEST operating point: it is the card's procedure, and no accuracy outcome is measured in a dry
cell.

## 9. Results consistency check

1. **Cross-check against committed values**: section 2, three rows, one explained 1.088x
   difference, nothing above 2x.
2. **Physical plausibility**: no latency, throughput or size is measured here; the only timing
   quantity consumed is the committed measured device wait, which is read and not re-derived.
3. **Distribution sanity**: per-type min, p25, median, p75, max and distinct counts are in
   `cascade_thresholds.json`; the one CONSTANT found is the episodic delivered score, reported as
   a breakage in section 4 rather than as a value.
4. **Definition audit**: `robot` DEV = LH-REQ DEV = 28 ids, asserted against the committed
   `per_split` DEV and case-folded on both sides; single-shot DEV = the committed
   `ss2_dev_eval_split.json` DEV part, read from the file and never re-derived; `median` is the
   0.50 quantile by `statistics.median`; `tau_trigger` is the 0.80 quantile of DEV negatives.
5. **Claim linkage**: this work bears on no accuracy or latency claim. It makes three published
   baselines legible as baselines, which is a precondition for the comparison the next gate needs.
   It produces no evidence for or against any FORMULATION claim, and nothing here may be cited as
   such.
6. **Proxy validity**: `ss_point` is a DECLARED WEAK proxy (token confidence in the digits of a
   coordinate is not confidence that the point is right). It is fitted and reported, and may not
   carry a headline. The episodic delivered score is a FAILED proxy and is reported as such.
7. **Validate the control**: P0 (same configuration, two processes, identical digest) and the
   positive control of section 2 (the committed 0.7358 scalar reproduces through the same reader)
   both pass. The committed `b_smoke_results.json` was re-run as a regression check and 40 of 40
   baselines still pass the StudyB smoke harness; its other diffs are pre-existing drift unrelated
   to this change, so the committed file was RESTORED rather than overwritten.

## 10. What was NOT done

- No threshold was invented for `cascade-routing` or `eco-llm`.
- `tau_trigger` was not re-fitted and not re-specified: it is unexpressible in live2 and its
  committed value stands for the setting where it was measured.
- The stale `measured_device_wait_applied` label in `scorer/score.py` was not changed.
- No EVAL or HOLDOUT data was fitted on, and no seed outside 0, 4, 5, 6, 7 was run.
