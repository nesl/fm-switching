# StudyPOL2-build: the v3 policy core as a library

Pre-registered in `research/EXPERIMENTS.md` (StudyPOL2-build) before anything was built. CPU only on flash: no GPU, no model server, no inference. Both prerequisites the brief names are in place and were moved into `research/` with a filesystem `mv`, uncommitted, for the user: `research/POLICY_SPEC_v3.md` (454 lines, v3) and `research/POLICY_SPEC_v3_1_ADDENDUM.md` (82 lines, v3.1, sections A0 to A6, decisions D51-D55). v3.1 = v3 plus the addendum, and where they conflict the ADDENDUM WINS, which is how it is implemented. Step 0 of the brief was verified against the file: A0, A1, A2, A3, A4, A5 and A6 are all present, A2 says a query is sent COMPLETE by default and no longer mentions a metadata escalation request, and A6 is titled Partial-prefix survival.

**One sentence.** Spec v3's whole decision path is implemented and tested: 58 spec sections map to named code, 120 unit and property tests pass, every one of the 8 conditional mechanisms is behind a flag that defaults OFF and carries its unmet enabling condition in code, the engine model is pluggable behind one protocol, and one DeltaJ_H evaluation costs 0.34 ms at a 0.75-s horizon, which makes the release loop's cost the thing to watch rather than the rollout's.

This row builds a mechanism and makes NO evaluation claim. It tunes nothing, fits nothing and reports no policy comparison. Mechanism verification is therefore marked NOT APPLICABLE here and attaches to T0-T4 and the live evaluation, with one acceptance criterion carried in this row: every mechanism must be instrumented well enough that Step 2 and Step 3 of that later verification can be done at all, which section 6 addresses.

---

## 1. What was built

| module | spec | what it holds |
|---|---|---|
| `flags.py` | 7.0 | every conditional mechanism, its enabling condition and why that condition is NOT met today |
| `params.py` | 9 | every parameter with its provenance: COMMITTED, DEV-FITTED or PLACEHOLDER |
| `profiles.py` | 4, 10.2 | the StudyPROF1-dev tables, and a `MissingEvidence` raise wherever a quantity does not exist |
| `engine.py` | 5.1, 10.2 | the `EngineModel` protocol plus a committed-evidence placeholder that flags every out-of-sample prediction |
| `state.py` | 2 | devices, links, believed-tier distributions, episodes, jobs, the pending set and the calendar |
| `utility.py` | 3.2, 4 | u_SH, u_SS, u_RC, T_ready and the gain g_r |
| `demand.py` | 6.4 | separate per-representation recall rates and the escalation rate, EWMA with DEV priors |
| `telemetry.py` | 6.5 | residency belief from engine counters, conservative when ambiguous, REQUESTED versus CONFIRMED |
| `continuation.py` | 5.4, 7.3 | the continuation schedule, P(finish), the three feasibility classes and the bounded-waiting check |
| `readiness.py` | 6.1-6.3 | state value for future questions, greedy tier assignment, nu_tier and the state-action table |
| `controller.py` | 7.7 | the device controller, self-normalized, with the price term behind its flag |
| `rollout.py` | 3.5, 5 | pi_0, the horizon rollout, terminal value and DeltaJ_H |
| `coordinator.py` | 7, 8, v3.1 A2 | admission, the query paths and the discard of declined queries, the release loop, hold and merge, outages and deficits |
| `t0_harness.py` | 5.2, 11 | the T0 fidelity harness, which REFUSES holdout data |
| `m4.py` | 10.2 | the decision-time measurement |
| `kvpool.py` | v3.1 A6.2 | the KV pool: occupancy, referenced versus unreferenced blocks, the engine's free-block order, and P_loss read from predicted eviction |
| `escalation.py` | v3.1 A1-A3 | the unified escalation basis Ghat, the non-learned type posterior, evidence coverage, and the three pluggable SH trigger families |
| `spec_map.py` | 14 | the section-to-code table and the ambiguity list, both checked by tests |

Run the tests with `cd experiments/orchestration && python3 -m unittest discover -s policy/tests -t .` (120 tests, 0 failures, 0 errors).

## 2. Spec section to code

All 58 entries resolve to symbols that exist; `spec_map.check()` is itself a test, so the table cannot rot silently.

| spec section | code | note |
|---|---|---|
| 1.2 eligible opportunities | `rollout.Rollout._opportunity_utility` | every decision instant on the task cadence is scored, escalated or not |
| 2.1 per-device state | `state.Device, state.HistoryBelief, state.Link` | the believed tier is a DISTRIBUTION, not a tier |
| 2.2 cloud state | `state.Fleet` | pending set, jobs, calendar |
| 3.1 SLOs over eligible opportunities | `params.Params.p_k, params.Params.q_k, params.Params.L_k` | application parameters, swept; the denominator is the opportunity list |
| 3.2 bounded task utility and gain | `utility.gain` | g_r may be zero or negative (D39) |
| 3.3 deficit counters | `state.Device.bump_z, coordinator.Coordinator.update_deficit` |  |
| 3.4 predicted versus measured success | `rollout.Rollout._z_term` | Phat only; the measured S_r is an offline quantity the harness reports |
| 3.5 action score | `rollout.delta_j, rollout.Rollout.run` | the four reference actions are the only ones delta_j accepts |
| 4.1 u_SH | `utility.u_sh_cloud, utility.u_sh_device` |  |
| 4.2 u_SS | `utility.u_ss` | raises: no committed SS accuracy |
| 4.3 u_RC and T_ready | `utility.t_ready_s, utility.u_rc` |  |
| 5.1 horizon rollout | `rollout.Rollout.run` |  |
| 5.2 T0 fidelity | `t0_harness.T0Harness` |  |
| 5.3 terminal value, one rule | `rollout.Rollout._terminal` |  |
| 5.4 job continuation value | `continuation.continuation_value, continuation.continuation_schedule` |  |
| 5.5 closed-form fallback | `rollout.Rollout.closed_form` | behind the fallback flag, which is off |
| 6.1 state value | `readiness.state_value` | future questions only; the in-progress question is excluded |
| 6.2 state actions | `readiness.state_actions` |  |
| 6.3 tier assignment | `readiness.tier_assignment` | greedy by value per byte; refuses a zero capacity |
| 6.4 demand predictors | `demand.Demand` | separate rc-per-representation and escalation rates |
| 6.5 residency verification | `telemetry.ResidencyBelief` |  |
| 7.0 core versus conditional | `flags.Flags, flags.CONDITIONAL` |  |
| 7.1 admission | `coordinator.Coordinator._admission, coordinator.Coordinator._plan` |  |
| 7.2 coordinator | `coordinator.Coordinator._release_loop` |  |
| 7.3 feasibility and bounded waiting | `continuation.classify, continuation.bounded_waiting_breach` |  |
| 7.4 adaptive granularity | `params.Params.piece_sizes_tokens, coordinator.Coordinator._plan` | piece size is chosen among measured sizes plus whole-job by the rollout |
| 7.5 outages | `coordinator.Coordinator.on_outage, coordinator.Coordinator.on_reconnect` |  |
| 7.6 deficit counters | `coordinator.Coordinator.update_deficit` |  |
| 7.7 device controller and price | `controller.DeviceController, coordinator.Coordinator.price` |  |
| 7.8 phase assignment | `coordinator.Coordinator._phase` | conditional, off |
| 7.9 hold and merge | `coordinator.Coordinator.hold_or_merge` | hold is core, merge is conditional and off |
| 7.10 summaries | `readiness.state_actions` | conditional, off; REFRESH_SUMMARY appears only with the flag |
| 7.11 predictive upload | `readiness.state_actions` | conditional, off; REQUEST_UPLOAD appears only with the flag |
| 8 main loop | `coordinator.Coordinator.on_event` |  |
| 9 parameters | `params.Params, params.PROVENANCE` |  |
| v3.1 A1 unified escalation basis Ghat | `escalation.ghat, escalation.GhatTables` | one formula for SH, SS and RC; the same Ghat enters DeltaJ_H |
| v3.1 A1 evidence coverage | `escalation.evidence_coverage` | in-window 4B-D2 against out-of-window device-N1-orin, both committed |
| v3.1 A1 timeliness gate | `coordinator.Coordinator.predicted_delivered_delay_s` | a late cloud answer has Ghat exactly zero |
| v3.1 A0 three flows kept distinct | `flags.CONDITIONAL, escalation.FAMILIES, coordinator.Coordinator.escalate` | history sync is the batched predictive upload (conditional, off), monitoring is the trigger family, a query is sent complete |
| v3.1 A6.1 expected remaining work under deferral | `continuation.expected_remaining_work, continuation.restore_costs_s` | w_left + P_loss x [P_host x reload + (1 - P_host) x rebuild], in engine seconds |
| v3.1 A6.1 in the continuation value and feasibility | `continuation.continuation_value, continuation.classify, continuation.p_finish` | all three take extra_work_s, so they price the same risk |
| v3.1 A6.2 KV pool | `kvpool.KVPool, rollout.Rollout._build_pool` | occupancy, referenced versus unreferenced, free-block order by recency |
| v3.1 A6.2 P_loss from predicted eviction | `kvpool.KVPool.predict_loss, rollout.Rollout._prefix_risk` | read from the rollout's own predicted eviction, never set by hand |
| v3.1 A6.2 beyond-horizon survival curve | `kvpool.survival_p_loss` | pluggable, absent until M5, and flagged rather than filled in |
| v3.1 A6.3 in-progress prefix in the memory decision | `readiness.prefix_items, rollout.Rollout.continuation_value_at_risk` | continuation value at risk plus state value for future questions, never pinned |
| v3.1 A6.3 single counting | `readiness.assert_single_counting` | asserted on every rollout, not merely intended |
| v3.1 A6.4 verify on resume | `coordinator.Coordinator.verify_prefix_before_release` | checks believed residency before releasing the next piece, re-plans and logs |
| v3.1 A6.5 piece sizing with deferral risk | `coordinator.Coordinator.choose_piece_size` | candidate sizes scored with the exposure each one implies |
| v3.1 A6 reporting | `coordinator.Coordinator.prefix_loss_events` | prefix-loss events per job, their cost, and predicted versus observed loss |
| v3.1 A2 query paths (revised) | `escalation.choose_path, coordinator.Coordinator.escalate, coordinator.Coordinator.pull_payload` | COMPLETE by default; question-first only when the unsent history exceeds the threshold AND higher-value traffic is in flight |
| v3.1 A2 discard on decline | `coordinator.Coordinator._discard` | a declined query leaves no pending item, no job and no in-flight work |
| v3.1 A2 delivered delay per path | `coordinator.Coordinator.predicted_delivered_delay_s` | question-first adds the control round trip and the M4 decision latency |
| v3.1 A2 higher-value traffic test | `coordinator.Coordinator.higher_value_in_flight` |  |
| v3.1 A2 trigger families (Q11) | `escalation.DeviceFilter, escalation.CloudTrickle, escalation.ContextModulatedTrickle` | interchangeable; the choice comes from StudyCTRL1b |
| v3.1 A3 task-type posterior | `escalation.type_posterior` | non-learned keyword and temporal-reference rules |
| v3.1 A1 Ghat inside DeltaJ_H | `rollout.Rollout._rc_utility` | the rollout uses the request's own Ghat when the basis has already estimated it |
| 11 approval tests T0 | `t0_harness.T0Harness` |  |
| 12 evaluation implications | `m4.measure_decision_time` | this row measures M4 only; the two evaluation tracks belong to the live study |

## 2b. The v3.1 addendum: one escalation basis

The addendum replaces v3's per-type escalation conditions with a single quantity, Ghat(r) = E[u_cloud - u_device | observable features], computed from DEV lookup tables and used BOTH by the device's filter and inside the cloud's DeltaJ_H. That is implemented in `escalation.py` and `Coordinator.escalate`, and the four features are wired to committed tables as follows.

| addendum feature | implementation | table it reads |
|---|---|---|
| evidence coverage | `escalation.evidence_coverage` | COMMITTED: in window the device answers from its D2 history (StudyE7 Job A, 4B-D2), out of window from one frame (StudyF4 Part A, Jetson Orin N=1). The GAP between those two committed tables is the measured value of the cloud holding more evidence; no new number was introduced |
| task-type posterior | `escalation.type_posterior` | NON-LEARNED keyword and temporal-reference rules (A3), with the per-type base gain from the committed DEV RC tables |
| device uncertainty | `GhatTables.uncertainty_multiplier` | NONE EXISTS. The multiplier is IDENTITY and marked PLACEHOLDER; addendum A4 names StudyCTRL1b's predictability-ceiling arm as the measurement that fills it, and a test asserts that filling the one callable changes Ghat without touching other code |
| timeliness | `Coordinator.predicted_delivered_delay_s` | committed link constants and TTFT tables; a cloud answer that cannot arrive before the deadline has Ghat EXACTLY zero |

**The two query paths of A2, as revised.** A query is sent COMPLETE by default: the question plus whatever payload the cloud lacks, which for SS is the current frame and for RC is only the history frames the cloud does not already hold. The cloud runs admission on arrival and DISCARDS a declined query, leaving the device's answer standing. QUESTION-FIRST is an exception path and takes BOTH of its conditions: the request is an RC query whose unsent history exceeds `Params.question_first_history_bytes`, AND the device's uplink already carries higher-value traffic (`Coordinator.higher_value_in_flight`, which the revised A2 names episode calls as the case for). Only then does the question travel alone and the cloud pull the missing frames on admission.

| | COMPLETE (default) | QUESTION-FIRST (exception) |
|---|---|---|
| what travels first | the question AND the payload the cloud lacks | the question alone |
| delivered delay | up(question) + up(payload) + compute + down | the same PLUS one control round trip PLUS the coordinator's decision latency |
| on decline | discarded; nothing was pulled | discarded; nothing was pulled |
| when taken | always, unless both exception conditions hold | RC only, big unsent history AND higher-value traffic in flight |

**The delivered delay is computed for the path actually used, and it gates both Ghat's timeliness term and the deadline check.** The question-first path's two extra terms are the device's own RTT for the control round trip and the coordinator's decision latency read back from THIS ROW'S OWN M4 measurement (0.3950 ms, the p50 of one DeltaJ_H at the nearest measured cell). When M4 has not been run the question-first path REFUSES to quote a delivered delay rather than quoting one that omits the term the path exists to pay, and a test asserts the refusal.

One ordering point, because the two quantities depend on each other: the path choice needs Ghat to judge what counts as higher-value traffic, and Ghat's timeliness term needs the path. Ghat is therefore computed on the complete path first, that value decides the exception, and if the path switches the Ghat is RECOMPUTED on the path actually used (ambiguity A21). Recomputing costs about 5 microseconds by M4, so nothing is traded away for it.

SH keeps a local filter, and the trigger family is an injected object with three interchangeable implementations (`DeviceFilter`, `CloudTrickle`, `ContextModulatedTrickle`), so whichever family StudyCTRL1b's comparison selects is dropped in with one assignment. That is the addendum's open question Q11 and the code leaves it open rather than guessing.

**A discrepancy the next reader must not be misled by.** `research/POLICY_SPEC_v3_1_ADDENDUM.md` ON DISK still carries the SUPERSEDED A2 wording, in which a query sends a metadata request with no frames and the cloud pulls the payload on admission. The revision implemented here came from the user's instruction of 2026-11-15, confirmed after they were shown that the file and the instruction disagree. The file was not edited by this row. This is recorded as ambiguity A20 and in the EXPERIMENTS verdict.

**No type is routed by rule, and this is tested rather than asserted.** `tests/test_escalation.py` checks it four ways: every escalation of every type increments the Ghat counter exactly once; a request whose Ghat is zero is never admitted, whatever its type; the decision records `basis = ghat` for every type; and the source of the escalation path is scanned for a branch that admits or declines on the task type, because a behavioural test cannot see a rule that is never exercised. The one type that cannot be scored, SS, is refused by the EVIDENCE gap (no committed single-shot accuracy, spec 13 P2) and the refusal message names the missing table, not the task type. One further test pins the addendum's central requirement numerically: Ghat for an SH instant at delivered delay d equals the rollout's own per-opportunity gain at that delay to 12 decimal places, so the device's filter and the cloud's admission cannot drift apart.

## 2c. A6, partial-prefix survival

A6's problem in one line: between pieces NO request holds a reconstruction job's built prefix, so its blocks are cached but UNREFERENCED and the engine frees those first; the prefix cannot be pinned (D44), so deferring the next piece risks losing work already done.

| A6 part | function | what it does |
|---|---|---|
| A6.1 expected remaining work | `continuation.expected_remaining_work` | w_left + P_loss x [P_host x reload + (1 - P_host) x rebuild], in engine seconds (ambiguity A29) |
| A6.1 restore costs | `continuation.restore_costs_s` | committed StudyRH5 host-reload and cold-rebuild rates; M1's step model does not exist, so nothing else is used |
| A6.1 into 5.4 and 7.3 | `continuation.continuation_value`, `continuation.classify`, `continuation.p_finish` | all three take `extra_work_s`, so the risk is priced identically in the continuation value and the feasibility class |
| A6.2 the pool | `kvpool.KVPool` | occupancy, referenced flags, free-block order (unreferenced first, least recently used first) |
| A6.2 P_loss | `kvpool.KVPool.predict_loss`, `rollout.Rollout._prefix_risk` | read from the rollout's own predicted eviction, never set by hand |
| A6.2 pool construction | `rollout.Rollout._build_pool` | seeded from each in-progress job's built prefix (unreferenced) and each history believed to be on the GPU |
| A6.2 beyond the horizon | `kvpool.survival_p_loss` | pluggable curve, ABSENT until M5, flagged rather than filled in |
| A6.3 prefix as a memory item | `readiness.prefix_items`, `rollout.Rollout.continuation_value_at_risk` | continuation value at risk plus state value for future questions |
| A6.3 single counting | `readiness.assert_single_counting` | asserted on EVERY rollout |
| A6.4 verify on resume | `coordinator.Coordinator.verify_prefix_before_release` | checks believed residency before releasing the next piece, inserts restore work, re-plans and logs |
| A6.5 piece sizing | `coordinator.Coordinator.choose_piece_size` | candidate sizes scored with the exposure the gaps imply |
| A6 reporting | `coordinator.Coordinator.prefix_loss_events` | per-job loss events, their cost, and requested continuation versus observed loss |

**What the model actually does to a decision.** The same job, the same piece, the same deadline; only the KV capacity changes.

| case | capacity (tokens) | P_loss if deferred | P_loss if released | expected restore (s) | DeltaJ of deferring, pool ON | pool OFF |
|---|---|---|---|---|---|---|
| high pressure | 12,000 | 1.00 | 0.00 | 1.365 | -1.7991 | -0.4338 |
| zero pressure | 100,000,000 | 0.00 | 0.00 | 0.000 | +0.0000 | +0.0000 |
| high pressure, mu = 0 | 12,000 | 1.00 | 0.00 | 1.365 | +0.0000 | +0.0000 |

That is the asymmetry A6 exists to create: under pressure the prefix is predicted fully lost if the piece is deferred and fully safe if it is released, so deferring costs -1.7991 against -0.4338 without the model. At zero pressure every A6 term is exactly zero and the result is bit-identical to the pre-A6 path, which is the brief's test (iv).

**One consequence stated plainly rather than buried.** Phat_r is an indicator (ambiguity A4), so restore work that still fits before the deadline cannot move the continuation value at all. A6's cost therefore reaches a RELEASE decision through spec 5.3's third terminal item, the GPU backlog priced at mu. mu is a PLACEHOLDER at 0, so WITH THE SHIPPED DEFAULTS THIS CHANNEL IS SILENT: the third row above shows DeltaJ identical with and without the pool when mu = 0. A6 then acts only through the feasibility class and the memory decision. A test pins this fact so it cannot be discovered by accident later (ambiguity A26).

**Piece sizing with the exposure included** (A6.5), for an 8,192-token job:

| size (tokens) | pieces | gaps | work (s) | expected restore (s) | expected total (s) |
|---|---|---|---|---|---|
| 8192 | 1 | 0 | 1.820 | 0.000 | 1.820 |
| 2048 | 4 | 3 | 1.820 | 1.365 | 3.186 |
| 1024 | 8 | 7 | 1.820 | 1.593 | 3.413 |

**Two A6 inputs do not exist yet and are declared, not defaulted quietly.** P_host is assigned to M5 by A6 itself; it is held at the CONSERVATIVE extreme 0.0, assume a full rebuild, which never understates the cost of deferring and matches spec 6.5's own convention that ambiguity resolves toward the colder tier (ambiguity A24). The beyond-horizon survival curve is also M5's; with none supplied the beyond-horizon part of a gap contributes zero and every affected result carries `beyond_horizon_unmeasured` (ambiguity A25).

**No code path assumes a prefix is pinned.** `prefix_items` marks every prefix item `pinned: false`, and the only protection in the model is the one that physically exists: a referenced prefix is not freed, so protection acts through scheduling choices (finishing sooner, larger pieces, not releasing competing KV-heavy work), exactly as A6.3 requires.

## 3. The conditional mechanisms, all OFF

Spec 7.0 (D38) says a mechanism whose benefit is not established is fully specified but carries an explicit enabling condition. Each is implemented, each defaults off, and the reason its condition is unmet is in the code rather than in prose only.

| mechanism | spec | default | enabling condition | status today |
|---|---|---|---|---|
| `escalation_price` | 7.7 | OFF | beta calibrated on DEV so a higher price suppresses the lowest-benefit escalations first; evaluated separately from admission | NOT MET: no committed DEV calibration of beta exists |
| `phase_assignment` | 7.8 | OFF | predicted clustering gain exceeds the capture-time shift cost | NOT MET: requires M1's step model to predict clustering gain |
| `merging` | 7.9 | OFF | M3 shows merged-call utility exceeds the device's at the delays involved | NOT MET AND WEAKENED: StudyFRAMES1 and StudyCTRL1b found no measurable m = 3 benefit on held-out clips and a negative point estimate once m = 3 pays its own upload; the DEV-positive m = 3 entries in profiles_dev.json are marked DEV-OPTIMISTIC and must not be used to enable this |
| `summaries` | 7.10 | OFF | DEV quality competitive for some question types and refresh cost measured | NOT MET: StudyF2 inconclusive; no committed SUMMARY recall table |
| `predictive_upload` | 7.11 | OFF | improves time-to-ready over on-demand upload under measured links | NOT MET: no measured bandwidth series exists (StudyPROF1-dev link_model marks bandwidth an ASSUMPTION), so the comparison cannot be made |
| `conditional_recall_rate` | 6.4 | OFF | DEV data shows recall questions concentrate around episodes | NOT COMPUTABLE: StudyPROF1-dev found no committed trace carrying escalations and recall questions on one stream, so the conservative default applies and the rate is not used |
| `sampled_scenarios` | 5.1 | OFF | T0 and M4 show sampling is affordable and more faithful than the expected-value rollout | NOT MET: T0 has not been run |
| `closed_form_fallback` | 5.5 | OFF | the fallback itself passes T0 | NOT MET: T0 has not been run |

Two of those statuses are stronger than 'not yet measured' and are worth stating plainly. MERGING is not merely unsupported but WEAKENED: StudyFRAMES1 and StudyCTRL1b found no held-out benefit from a third frame and a negative point estimate once it pays its own upload, so `utility.u_sh_cloud` REFUSES to read the m = 3 table unless merging is explicitly enabled, and the profile's own note travels with the refusal. The CONDITIONAL RECALL RATE is not computable at all from committed data, so `demand.Demand` keeps the ratio at 1 and `readiness.state_value` reports `conditional_rate_used = false` on every call.

## 4. Every ambiguity, and the choice taken

These are the places where spec v3 or the brief could be read two ways AND the readings differ in behaviour. Each names the one place in the code where the choice is reversed.

**A1. spec 3.5 Jhat_H**

* Question: Is Uhat_H an absolute utility or a gain against the device's own answer?
* Choice: GAINS, so device-only is exactly zero.
* Why: Spec 3.2 defines the quantity the policy optimizes as a GAIN. The two readings differ by a constant that is identical in both rollouts of a DeltaJ, so no decision changes; the gain reading makes an action's sign readable on its own.
* Reversible at: `rollout.Rollout._opportunity_utility`

**A2. spec 4.1 u_SH(cloud, d, m)**

* Question: What delay d does an opportunity served by an older held answer carry?
* Choice: d = opportunity instant minus the serving answer's CAPTURE time.
* Why: This is StudyE9b's own sample-and-hold semantics, which every committed Nexar number uses; measuring d from the delivery instead would make a held answer eternally fresh.
* Reversible at: `rollout.Rollout._opportunity_utility`

**A3. spec 8 'update mu'**

* Question: Spec 3.5 and 8 use mu as a GPU-backlog price but give no update rule.
* Choice: An EWMA of the realized marginal utility per GPU-second of the last released item, floored at zero, with alpha a PLACEHOLDER parameter.
* Why: Spec 6.3 defines nu_tier the same way (the gain per byte of the last promotion into a full tier), so the analogous rule for GPU time is the one the spec's own style implies. It carries no evidence and is marked PLACEHOLDER.
* Reversible at: `coordinator.Coordinator._update_mu`

**A4. spec 5.4 Phat_r**

* Question: The expected-value rollout produces a schedule, not a distribution, so what is the PROBABILITY of finishing?
* Choice: The indicator of the continuation schedule meeting the deadline, multiplied by P(reachable within H_s).
* Why: Spec 5.1 makes the expected-value rollout the default and sampled scenarios optional (flag off). An indicator is the honest reading of a deterministic schedule; with the sampling flag on it becomes a frequency over draws.
* Reversible at: `continuation.p_finish`

**A5. spec 7.3 'competing work'**

* Question: How much competing engine time does pi_0 put ahead of a job's remaining pieces?
* Choice: An explicit `competing_s` argument, zero by default, supplied by the caller from the calendar and the arrival rates.
* Why: The spec describes the quantity but not its estimator. Making it an argument keeps the estimator outside the feasibility rule, so a better estimator does not change the classification code.
* Reversible at: `continuation.continuation_schedule`

**A6. spec 4.3 durations**

* Question: StudyRH5 measured 11k and 28k histories only; what rate applies at other sizes?
* Choice: The committed rate at the NEAREST measured size, never an extrapolation outside the measured pair.
* Why: The profile states a linear interpolation rule between the two sizes for warm states; outside them there is no evidence, and this repository's own failures (E30 versus E32) came from carrying a rate past its measurement.
* Reversible at: `profiles.Profiles.seconds_per_token`

**A7. spec 6.1 'the next colder state or the device'**

* Question: Which is the comparison when the belief is a distribution over three tiers?
* Choice: max(expected utility of the next colder tier, the device's own accuracy), under the same belief distribution.
* Why: Spec 6.1 writes 'or the device', and the device is always available (spec 1.1), so the fallback is whichever is better; using the colder tier alone would credit readiness for beating an option no one would take.
* Reversible at: `readiness.state_value`

**A8. spec 7.7 'instability over n_c frames'**

* Question: Variance or answer flips?
* Choice: Both, selected on DEV, exactly as StudyCTRL1-episodes implemented it (its A2).
* Why: The policy must accept whichever reading the DEV fit chose, or the fitted parameters are not transferable.
* Reversible at: `controller.DeviceController.signal`

**A9. spec 7.7 rise term**

* Question: The rise is written unnormalized while all three signals are called self-normalized.
* Choice: Rise and instability are divided by the same window IQR as z.
* Why: A raw log-unit rise and a dimensionless z cannot share one threshold without a unit error; this matches StudyCTRL1-episodes (its A1), so the fitted theta transfers.
* Reversible at: `controller.DeviceController.signal`

**A10. spec 7.2 step 3**

* Question: How many releases may one event commit?
* Choice: Repeat while some pending item has positive DeltaJ_H, bounded by a configurable max_releases, and re-score after every release.
* Why: Spec 7.2 says one release at a time, re-score, repeat until none is positive, and spec 7.2 step 5 says commit only the immediate releases. The bound exists so a pathological state cannot spin; it is not a policy parameter.
* Reversible at: `coordinator.Coordinator._release_loop`

**A11. spec 3.1 and 3.3**

* Question: A declined or suppressed escalation counts as a device-only OUTCOME; does it count as a FAILURE for Z?
* Choice: It counts as an opportunity whose outcome is the device's, and it meets the SLO only if the device's own answer does.
* Why: Spec 3.1 says exactly this ('a suppressed or declined escalation counts as a device-only outcome') and notes that suppression therefore cannot improve measured attainment by hiding difficult situations.
* Reversible at: `rollout.Rollout._opportunity_utility`

**A12. the brief's oracle arm (StudyCTRL1b)**

* Question: Can an oracle that escalates only before positive events be an upper bound on any trigger?
* Choice: No, and both readings are reported. See StudyCTRL1b's B2b.
* Why: The two tiers' scores are on different scales, so a label-correlated escalation pattern moves a rank metric by itself. This is the measured reason spec 4.1's u_SH must be a CALIBRATED utility and not a raw tier score, and the policy reads u_SH from the DEV table rather than from any score.
* Reversible at: `utility.u_sh_cloud and the profile's mapping entry`

**A14. v3.1 A1 device uncertainty**

* Question: The addendum makes the device's self-normalized uncertainty a determinant of Ghat, but no committed DEV table maps uncertainty to gain.
* Choice: The multiplier is IDENTITY and marked PLACEHOLDER; the slot is a single callable.
* Why: Inventing a monotone function here would put an unmeasured curve inside every escalation decision. Addendum A4 names the measurement that fills it, StudyCTRL1b's predictability-ceiling arm, and a test asserts that filling the slot changes Ghat without touching any other code.
* Reversible at: `escalation.GhatTables.uncertainty_multiplier`

**A15. v3.1 A1 evidence coverage**

* Question: Which device accuracy applies when the request references evidence outside the device's window?
* Choice: In window, the committed 4B-D2 table (StudyE7 Job A); out of window, the committed device-N1-orin table (StudyF4 Part A).
* Why: Those are the two committed measurements of the device answering WITH and WITHOUT its history, so their gap is the measured value of the cloud holding more evidence. No new number is introduced.
* Reversible at: `escalation._device_accuracy`

**A16. v3.1 A3 task-type posterior**

* Question: What is the posterior when the keyword and temporal-reference rules match nothing?
* Choice: Ghat REFUSES to score the request (MissingEvidence) rather than assuming a uniform posterior.
* Why: A uniform posterior over eight question types is a fabricated belief that would flow straight into an admission decision. Addendum A3's own fallback is the device model labelling the question, and no committed measurement of that labelling accuracy exists, so the honest state is a refusal that names what is missing.
* Reversible at: `escalation.type_posterior and escalation.ghat`

**A17. v3.1 A1 versus spec 13 P2**

* Question: The addendum says every type is escalated on one rule, but there is no committed SS accuracy at all.
* Choice: SS is refused by the EVIDENCE gap, never by a type rule: ghat raises because the SS table is missing, exactly as it would for an RC type with no committed accuracy.
* Why: This keeps the addendum's requirement literally true, that no type is routed by rule, while not inventing an SS accuracy. The refusal message names the missing table rather than the task type.
* Reversible at: `profiles.Profiles.omega and the SS rows of the profile`

**A18. v3.1 A2 (Q11)**

* Question: Which SH trigger family is the default while the question is open?
* Choice: DeviceFilter with threshold 0, that is escalate when Ghat is positive at all.
* Why: Zero is the only threshold that carries no fitted content: it says escalate exactly when the estimated gain is positive. The family is an injected object, so StudyCTRL1b's measured winner replaces it with one assignment.
* Reversible at: `coordinator.Coordinator.sh_trigger`

**A19. spec 3.5 terminal value**

* Question: Spec 3.5 writes '+ mu * (GPU backlog at t + H)' while mu is described everywhere else as a PRICE (spec 7.7: pi = mu x GPU-seconds, how expensive help is right now). Taken literally, backlog would RAISE terminal value.
* Choice: Backlog SUBTRACTS: the term is -mu * residual_backlog_s.
* Why: A price that rewards backlog would make every admission look better the more work it leaves behind, which inverts the mechanism mu exists for and contradicts spec 6.3's nu_tier, defined as the gain per byte of the last promotion into a full tier. A unit test (a declined query under a large mu) is what surfaced the literal reading as untenable.
* Reversible at: `rollout.Rollout._terminal`

**A20. v3.1 A2 as revised (the user's message of 2026-11-15)**

* Question: The addendum FILE still carries the superseded 'METADATA escalation request' wording for queries; the revision exists only in the user's instruction.
* Choice: The code implements the revision: queries complete by default, question-first as an exception, and this is stated in the report and the EXPERIMENTS row.
* Why: The user confirmed the pasted file is the latest and directed the change explicitly after being shown that the file and the instruction disagree. The discrepancy is recorded rather than silently resolved so the next reader is not misled by the file.
* Reversible at: `coordinator.Coordinator.escalate and escalation.choose_path`

**A21. v3.1 A2 as revised, ordering**

* Question: The path choice needs Ghat (to judge 'higher-value traffic') and Ghat's timeliness term needs the path. Which is computed first?
* Choice: Ghat on the COMPLETE path first, that value decides the exception, and if the path switches Ghat is RECOMPUTED on the path actually used.
* Why: The default path is the one to score first, and recomputing is cheap (one Ghat is about 4 microseconds by M4), so the reported Ghat and deadline check always describe the real path rather than the default.
* Reversible at: `coordinator.Coordinator.escalate`

**A22. v3.1 A2 as revised, delivered delay**

* Question: The revised A2 is cited for 'A2 formulas', but the file contains no formula for either query path.
* Choice: Spec 4's delivered-delay definition per path: COMPLETE is up(question) + up(payload) + compute + down; QUESTION-FIRST adds one CONTROL ROUND TRIP (the device's own RTT) and the coordinator's measured decision latency from M4, and REFUSES to quote a delay when M4 is unmeasured.
* Why: Spec 4 is the only committed delivered-delay definition, and the two extra terms are exactly what the user's instruction names. Refusing rather than defaulting to zero keeps the path from being quoted as cheaper than it is.
* Reversible at: `coordinator.Coordinator.predicted_delivered_delay_s`

**A23. v3.1 A6.2**

* Question: P_loss is 'the probability the built prefix is evicted'. With a deterministic predicted eviction, is that an indicator?
* Choice: The FRACTION of the prefix's blocks the predicted demand frees.
* Why: A partial eviction is the common case and it costs a partial restore, so a fraction carries the information an indicator throws away, and it multiplies cleanly by the restore cost in A6.1's formula.
* Reversible at: `kvpool.KVPool.predict_loss`

**A24. v3.1 A6.1 P_host**

* Question: A6 assigns P_host to M5, which has not been run.
* Choice: Default 0.0, the CONSERVATIVE extreme: assume evicted blocks are NOT recoverable and a full rebuild is needed.
* Why: It never understates the cost of deferring, and it matches spec 6.5's own convention that ambiguity resolves toward the colder tier. A measured M5 value replaces one parameter.
* Reversible at: `params.Params.p_host`

**A25. v3.1 A6.2 beyond the horizon**

* Question: A6 extends P_loss with the measured survival curve where the rollout does not reach the resume time; no such curve exists.
* Choice: The curve is a pluggable callable defaulting to NONE, the beyond-horizon part of the gap then contributes zero, and every affected result carries `beyond_horizon_unmeasured`.
* Why: Zero is the only value that adds no unmeasured content, and the flag stops the result being read as if the long-gap case had been modelled.
* Reversible at: `params.Params.survival_curve and kvpool.survival_p_loss`

**A26. v3.1 A6.1 versus spec 5.4**

* Question: How does the expected restore work change a DeltaJ when the job still meets its deadline?
* Choice: Through spec 5.3's third terminal item: the restore work is GPU backlog not covered by any job's continuation value, priced at mu.
* Why: Phat_r is an indicator (A4), so restore work that still fits before the deadline cannot move the continuation value at all; without this channel A6 would be invisible to release timing. THE CONSEQUENCE IS STATED RATHER THAN HIDDEN: mu is a PLACEHOLDER at 0, so with the shipped default this channel is SILENT and A6 reaches decisions only through feasibility and the memory decision. A test pins that fact.
* Reversible at: `rollout.Rollout._terminal`

**A27. v3.1 A6.1 'for the defer branch'**

* Question: Which demand can evict the prefix, all of the horizon's or only part?
* Choice: Only the competing work released AFTER this job's prefix was last referenced, that is inside the exposure window.
* Why: A6's mechanism is that the prefix is unreferenced BETWEEN pieces. Charging a job's own released piece for the risk it removes made deferring look cheaper than releasing, which inverts A6; scoping the demand to the exposure window is what makes release strictly safer than deferral, as the spec intends.
* Reversible at: `rollout.Rollout._prefix_risk`

**A28. v3.1 A6.4 'observed or believed likely'**

* Question: What makes a loss 'likely'?
* Choice: P_loss at or above `Params.prefix_loss_replan_threshold`, default 0.5, swept.
* Why: The spec gives no number. 0.5 is the neutral reading of 'likely' and is a declared PLACEHOLDER rather than a fitted value.
* Reversible at: `params.Params.prefix_loss_replan_threshold`

**A29. v3.1 A6.1 units**

* Question: A6 writes w_left as 'the job's unreleased pieces', a count, while the restore terms are costs.
* Choice: Everything is converted to ENGINE SECONDS through the engine model.
* Why: A count and a cost cannot be added. Engine seconds is the unit the continuation schedule and the step model already use, so the sum composes with both.
* Reversible at: `continuation.expected_remaining_work`

**A13. spec 7.4**

* Question: Which piece sizes are candidates?
* Choice: The committed measured sizes (1,024 and 2,048 tokens) plus whole-job, with the closed form k* available only as a seed.
* Why: Spec 7.4 says measured sizes plus whole-job and that the closed form is not a foundational claim; SLICE1 Parts A-D measured exactly those two sizes.
* Reversible at: `params.Params.piece_sizes_tokens`

## 5. Parameters: what carries evidence and what does not

22 of the 36 parameters are PLACEHOLDERS, meaning no committed study sets them. The policy does not pretend otherwise: `Params.placeholders()` lists them and the test suite asserts every field has a provenance entry.

| kind | parameters |
|---|---|
| COMMITTED | `allow_whole_job_piece`, `decision_latency_s`, `episode_cadence_grid_s`, `kv_pool_model`, `piece_sizes_tokens` |
| DEV-FITTED | `E_k`, `K_c`, `T_k`, `W_c`, `delta`, `instability_mode`, `n_c`, `omega`, `theta_k` |
| PLACEHOLDER | `H`, `H_s`, `H_up`, `K_e`, `L_k`, `N_sum`, `W_k`, `belief_conservatism`, `beta`, `continuation_resolution_s`, `feasibility_threshold`, `gpu_kv_capacity_tokens`, `host_kv_capacity_tokens`, `mu`, `mu_ewma_alpha`, `p_host`, `p_k`, `prefix_loss_replan_threshold`, `q_k`, `question_first_history_bytes`, `survival_curve`, `theta_up` |

Two placeholders are refusals rather than guesses. `gpu_kv_capacity_tokens` and `host_kv_capacity_tokens` default to 0 and `readiness.tier_assignment` RAISES on a zero capacity, because a silently wrong capacity changes every allocation it makes. Likewise `omega['SS']` is None and any attempt to plan a single-shot escalation raises, since no committed SS accuracy pair exists (spec 13, P2).

## 6. The engine model is pluggable, and says when it is out of sample

The policy only ever calls one protocol, `EngineModel.predict`. `PlaceholderEngine` implements it from committed evidence alone: StudySIM1d overlap cost and no sub-linear batching; StudyRH5 prefill and readiness TTFT; StudyD7 / D7b episodic TTFT; SLICE1 Part A near-monolithic prefix-chained total work.

Its known failure is carried in the object: StudySIM1d failed out of sample on slice-versus-episodic interactions, which is why T0 precedes any reliance on this. Every prediction returns an `in_sample` flag, `Rollout` propagates it to the rollout result, `DeltaJ` reports it, and the T0 harness counts out-of-sample cases per condition. That is the instrumentation the later mechanism verification needs: Step 2 can read each causal link's quantity off the rollout result and Step 3 can print one decision's full arithmetic from `Decision.detail`.

Overlap cost 0.050 s per concurrent warm request, prefill rates [3800, 4500] tok/s, sub-linear batching NOT modelled, because StudySIM1d measured none. Replacing this with M1 means passing a different object; no policy module changes.

## 7. M4: what a decision costs

One DeltaJ_H is two rollouts over the horizon. Spec 7.2's release loop scores every pending item per event and re-scores after each release, so the per-event cost is the product.

| horizon (s) | pending items | one DeltaJ p50 (ms) | p95 (ms) | one full release loop (ms) |
|---|---|---|---|---|
| 0.50 | 1 | 0.638 | 0.806 | 0.6 |
| 0.50 | 4 | 0.389 | 0.579 | 1.6 |
| 0.50 | 16 | 0.497 | 0.521 | 8.0 |
| 0.50 | 64 | 0.935 | 1.004 | 59.9 |
| 0.75 | 1 | 0.342 | 0.369 | 0.3 |
| 0.75 | 4 | 0.395 | 0.437 | 1.6 |
| 0.75 | 16 | 0.513 | 0.529 | 8.2 |
| 0.75 | 64 | 0.963 | 1.004 | 61.6 |
| 1.00 | 1 | 0.343 | 0.372 | 0.3 |
| 1.00 | 4 | 0.397 | 0.427 | 1.6 |
| 1.00 | 16 | 0.519 | 0.570 | 8.3 |
| 1.00 | 64 | 0.962 | 1.014 | 61.6 |

**The reading.** One decision is cheap and nearly horizon-independent (0.34 ms at 1 pending item, 0.96 ms at 64), because the rollout's work is set by the number of items it simulates rather than by H. The release LOOP is the cost that matters: it grows as the square of the pending set, 61.6 ms at 64 items, which is 8 % of a 0.75-s horizon. Spec 7.2's design (score all, release one, re-score) is therefore the thing M4 constrains, not the rollout, and the fallback of spec 5.5 exists for exactly this. A deployment at this pending-set size needs either the closed-form fallback or an incremental re-score, and both must pass T0 first.

**The addendum's Ghat is free by comparison.** One Ghat, including the non-learned type posterior and the predicted delivered delay on the device's link, costs 0.0046 ms for an SH instant, 0.0046 ms for a query of known type and 0.0080 ms when the type is unknown and the expectation runs over the posterior. That is three to four orders of magnitude below one DeltaJ_H, so putting a Ghat in front of every request (addendum A1) changes nothing about where the decision cost lives.

Caveat, stated as the measurement carries it: a lower bound on deployment cost: this is pure Python on committed tables, and the real decision also pays for telemetry reads and the engine's own admission path

## 8. T0: built, exercised, and fenced off from the holdout

The harness compares the delay the rollout predicts it will impose on others, and each job's predicted completion time, against live measurements, per condition, with a stated tolerance (0.050 s on delay, 0.250 s on completion).

**It refuses holdout data and the refusal is not overridable.** `T0Harness.run` raises `HoldoutRefused` for any split named holdout, eval or test, AND for any split name it does not recognize, so a T0 result can never have unknown provenance. The reason is that T0 is a model-fidelity check: a model corrected against the held-out traces is fitted on them, and every later comparison on those traces becomes in-sample.

The dry run is on a SYNTHETIC replay and its verdict is PASS over 8 cases. That verdict means only that the harness computes what it claims: SYNTHETIC: the 'measurement' is the model itself plus 0.000 s, so this exercises the harness and NOT the engine model

## 9. Results consistency check

| # | check | outcome |
|---|---|---|
| 1 | cross-check against committed measurements | **PASS.** The only committed quantities this row reads are the StudyPROF1-dev tables, and the test suite asserts them exactly: u_SH(device) = 0.4922174586396322, omega_RC = 0.42463109124188936, RTT 0.044 s, uplink 1,700,000 B/s. The M4 timings are new and have no prior. |
| 2 | physical plausibility | **PASS.** The rates the engine model implies are the committed ones by construction (4,500 and 3,800 tok/s prefill, 0.05 s overlap per concurrent warm request); nothing is faster than its committed curve because nothing is computed from a new measurement. The M4 numbers are pure-Python decision times on one CPU core and are reported as a lower bound. |
| 3 | distribution sanity | **PASS.** Every M4 row carries mean, p50, p95, min and max over 15 repeats rather than a single number, and the values vary across repeats as expected for a CPU timing. |
| 4 | definition audit | **PASS, with one SIGN CORRECTED.** Spec 3.5 writes the terminal backlog term as `+ mu * backlog` while mu is a PRICE everywhere else (spec 7.7: pi = mu x GPU-seconds, how expensive help is right now). Implemented literally, backlog RAISED terminal value, which a unit test surfaced; it now SUBTRACTS, recorded as ambiguity A19. Four names are used with ONE definition each and the definitions are the committed ones: an eligible opportunity is spec 1.2's decision instant on the task cadence; delivered delay is measured from the serving answer's CAPTURE time, which is StudyE9b's sample-and-hold (ambiguity A2); u_SH is StudyE9c challenge mAP under the identity mapping; a piece is a prefix-chained whole-frame unit at SLICE1's measured sizes. |
| 5 | claim linkage | **PASS.** This row bears on spec D50's claimed contribution by making it executable, and on nothing else. It SUPPORTS no claim by itself: a library is not evidence. It does WEAKEN one thing, in that `utility.u_sh_cloud` now refuses the m = 3 table by default, which makes spec 7.9's merge rule harder to enable by accident. |
| 6 | proxy validity | **PASS with the proxy declared.** The placeholder engine model is a PROXY for M1's measured step model. It is valid for building and for M4, and NOT valid for any capacity or delay conclusion: StudySIM1d's model failed out of sample on exactly the slice-versus-episodic mixtures a fleet produces. The proxy is labelled in code, every prediction carries `in_sample`, and T0 exists to retire it. |

## 10. What this row does NOT establish

* **No T0.** The rollout's fidelity is unmeasured. Until T0 runs on the live H100, every DeltaJ_H is a prediction from a model that is known to fail out of sample on mixtures.
* **No T1 to T4.** No baseline comparison, no capacity number, no claim that the coordinator beats EDF. EDF is implemented as pi_0, which is also the first baseline it must beat.
* **No learning and no tuning.** Every parameter is either committed, DEV-fitted elsewhere, or a declared placeholder.
* **The conditional half of the spec is unexercised by design.** All five conditional mechanisms are off, and summaries and predictive upload cannot be turned on usefully today for want of a SUMMARY recall table and a measured bandwidth series.

## 11. Files

| file | what |
|---|---|
| `experiments/orchestration/policy/` | the library, 18 modules |
| `experiments/orchestration/policy/tests/` | 120 unit and property tests |
| `experiments/orchestration/policy/run_pol2.py` | runs the tests, writes the three JSONs |
| `results/orchestration/pol2/pol2_spec_map.json` | the section-to-code table, the ambiguity list, the flag audit, the parameter provenance and the engine description |
| `results/orchestration/pol2/pol2_m4_decision_time.json` | M4, swept over horizon and pending-set size, plus the Ghat cost |
| `results/orchestration/pol2/pol2_a6_prefix_survival.json` | the A6 demonstration: P_loss and DeltaJ of deferring under pressure, at zero pressure and at mu = 0, plus the piece-size table |
| `results/orchestration/pol2/pol2_t0_harness_dryrun.json` | the T0 harness exercised on a synthetic replay |

