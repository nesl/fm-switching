"""The spec-section-to-code table and EVERY ambiguity found in spec v3 AND the v3.1 addendum,
with the choice made.

`SPEC_MAP` is checked by the test suite: every section listed must name a symbol that exists.
`AMBIGUITIES` is the list the brief asks for. An entry here is a place where the spec (or the
brief) could be read two ways and the readings differ in BEHAVIOUR; a choice recorded here is
reversible by changing one named place in the code.
"""
from __future__ import annotations

from typing import Any, Dict, List

SPEC_MAP: List[Dict[str, str]] = [
    dict(section="1.2 eligible opportunities", code="rollout.Rollout._opportunity_utility",
         note="every decision instant on the task cadence is scored, escalated or not; D98 "
              "credits each SH instant at its OWN deadline c_i + L_SH (v4 5.1, 6.3), retiring "
              "the display-freshness rule"),
    dict(section="2.1 per-device state", code="state.Device, state.HistoryBelief, state.Link",
         note="the believed tier is a DISTRIBUTION, not a tier"),
    dict(section="2.2 cloud state", code="state.Fleet", note="pending set, jobs, calendar"),
    dict(section="3.1 SLOs over eligible opportunities", code="params.Params.p_k, params.Params.q_k, params.Params.L_k",
         note="application parameters, swept; the denominator is the opportunity list"),
    dict(section="3.2 bounded task utility and gain", code="utility.gain",
         note="g_r may be zero or negative (D39)"),
    dict(section="3.3 deficit counters", code="state.Device.bump_z, coordinator.Coordinator."
                                              "update_deficit"),
    dict(section="3.4 predicted versus measured success", code="rollout.Rollout._z_term",
         note="Phat only; the measured S_r is an offline quantity the harness reports"),
    dict(section="3.5 action score", code="rollout.delta_j, rollout.Rollout.run",
         note="the four reference actions are the only ones delta_j accepts"),
    dict(section="4.1 u_SH", code="utility.u_sh_cloud, utility.u_sh_device"),
    dict(section="4.2 u_SS", code="utility.u_ss", note="raises: no committed SS accuracy"),
    dict(section="4.3 u_RC and T_ready", code="utility.t_ready_s, utility.u_rc"),
    dict(section="5.1 horizon rollout", code="rollout.Rollout.run"),
    dict(section="5.2 T0 fidelity", code="t0_harness.T0Harness"),
    dict(section="5.3 terminal value, one rule", code="rollout.Rollout._terminal"),
    dict(section="5.4 job continuation value", code="continuation.continuation_value, "
                                                    "continuation.continuation_schedule"),
    dict(section="5.5 closed-form fallback", code="rollout.Rollout.closed_form",
         note="behind the fallback flag, which is off"),
    dict(section="6.1 state value", code="readiness.state_value",
         note="future questions only; the in-progress question is excluded"),
    dict(section="6.2 state actions", code="readiness.state_actions"),
    dict(section="6.3 tier assignment", code="readiness.tier_assignment",
         note="greedy by value per byte; refuses a zero capacity"),
    dict(section="6.4 demand predictors", code="demand.Demand",
         note="separate rc-per-representation and escalation rates"),
    dict(section="6.5 residency verification", code="telemetry.ResidencyBelief"),
    dict(section="7.0 core versus conditional", code="flags.Flags, flags.CONDITIONAL"),
    dict(section="7.1 admission", code="coordinator.Coordinator._admission, coordinator.Coordinator._plan"),
    dict(section="7.2 coordinator", code="coordinator.Coordinator._release_loop"),
    dict(section="7.3 feasibility and bounded waiting", code="continuation.classify, "
                                                             "continuation.bounded_waiting_breach"),
    dict(section="7.4 adaptive granularity", code="params.Params.piece_sizes_tokens, "
                                                  "coordinator.Coordinator._plan",
         note="piece size is chosen among measured sizes plus whole-job by the rollout"),
    dict(section="7.5 outages", code="coordinator.Coordinator.on_outage, coordinator.Coordinator.on_reconnect"),
    dict(section="7.6 deficit counters", code="coordinator.Coordinator.update_deficit"),
    dict(section="7.7 device controller and price", code="controller.DeviceController, "
                                                         "coordinator.Coordinator.price"),
    dict(section="7.8 phase assignment", code="coordinator.Coordinator._phase",
         note="conditional, off"),
    dict(section="7.9 hold and merge", code="coordinator.Coordinator.hold_or_merge",
         note="hold is core, merge is conditional and off"),
    dict(section="7.10 summaries", code="readiness.state_actions",
         note="conditional, off; REFRESH_SUMMARY appears only with the flag"),
    dict(section="7.11 predictive upload", code="readiness.state_actions",
         note="conditional, off; REQUEST_UPLOAD appears only with the flag"),
    dict(section="8 main loop", code="coordinator.Coordinator.on_event"),
    dict(section="9 parameters", code="params.Params, params.PROVENANCE"),
    dict(section="v3.1 A1 unified escalation basis Ghat", code="escalation.ghat, "
         "escalation.GhatTables",
         note="one formula for SH, SS and RC; the same Ghat enters DeltaJ_H"),
    dict(section="v3.1 A1 evidence coverage", code="escalation.evidence_coverage",
         note="in-window 4B-D2 against out-of-window device-N1-orin, both committed"),
    dict(section="v3.1 A1 timeliness gate", code="coordinator.Coordinator."
         "predicted_delivered_delay_s", note="a late cloud answer has Ghat exactly zero"),
    dict(section="v3.1 A0 three flows kept distinct", code="flags.CONDITIONAL, "
         "escalation.FAMILIES, coordinator.Coordinator.escalate",
         note="history sync is the batched predictive upload (conditional, off), monitoring is "
              "the trigger family, a query is sent complete"),
    dict(section="v3.1 A6.1 expected remaining work under deferral",
         code="continuation.expected_remaining_work, continuation.restore_costs_s",
         note="w_left + P_loss x [P_host x reload + (1 - P_host) x rebuild], in engine seconds"),
    dict(section="v3.1 A6.1 in the continuation value and feasibility",
         code="continuation.continuation_value, continuation.classify, continuation.p_finish",
         note="all three take extra_work_s, so they price the same risk"),
    dict(section="v3.1 A6.2 KV pool", code="kvpool.KVPool, rollout.Rollout._build_pool",
         note="occupancy, referenced versus unreferenced, free-block order by recency"),
    dict(section="v3.1 A6.2 P_loss from predicted eviction",
         code="kvpool.KVPool.predict_loss, rollout.Rollout._prefix_risk",
         note="read from the rollout's own predicted eviction, never set by hand"),
    dict(section="v3.1 A6.2 beyond-horizon survival curve", code="kvpool.survival_p_loss",
         note="pluggable, absent until M5, and flagged rather than filled in"),
    dict(section="v3.1 A6.3 in-progress prefix in the memory decision",
         code="readiness.prefix_items, rollout.Rollout.continuation_value_at_risk",
         note="continuation value at risk plus state value for future questions, never pinned"),
    dict(section="v3.1 A6.3 single counting", code="readiness.assert_single_counting",
         note="asserted on every rollout, not merely intended"),
    dict(section="v3.1 A6.4 verify on resume",
         code="coordinator.Coordinator.verify_prefix_before_release",
         note="checks believed residency before releasing the next piece, re-plans and logs"),
    dict(section="v3.1 A6.5 piece sizing with deferral risk",
         code="coordinator.Coordinator.choose_piece_size",
         note="candidate sizes scored with the exposure each one implies"),
    dict(section="v3.1 A6 reporting", code="coordinator.Coordinator.prefix_loss_events",
         note="prefix-loss events per job, their cost, and predicted versus observed loss"),
    dict(section="v3.1 A2 query paths (revised)", code="escalation.choose_path, "
         "coordinator.Coordinator.escalate, coordinator.Coordinator.pull_payload",
         note="COMPLETE by default; question-first only when the unsent history exceeds the "
              "threshold AND higher-value traffic is in flight"),
    dict(section="v3.1 A2 discard on decline", code="coordinator.Coordinator._discard",
         note="a declined query leaves no pending item, no job and no in-flight work"),
    dict(section="v3.1 A2 delivered delay per path",
         code="coordinator.Coordinator.predicted_delivered_delay_s",
         note="question-first adds the control round trip and the M4 decision latency"),
    dict(section="v3.1 A2 higher-value traffic test",
         code="coordinator.Coordinator.higher_value_in_flight"),
    dict(section="v3.1 A2 trigger families (Q11)", code="escalation.DeviceFilter, "
         "escalation.CloudTrickle, escalation.ContextModulatedTrickle",
         note="interchangeable; the choice comes from StudyCTRL1b"),
    dict(section="v3.1 A3 task-type posterior", code="escalation.type_posterior",
         note="non-learned keyword and temporal-reference rules"),
    dict(section="v3.1 A1 Ghat inside DeltaJ_H", code="rollout.Rollout._rc_utility",
         note="the rollout uses the request's own Ghat when the basis has already estimated it"),
    dict(section="D56 three tiers, both warm tiers bounded, evidence never deleted",
         code="tiers.HostPool, tiers.TieredStore, rollout.Rollout._build_store",
         note="GPU and host sizes are INPUTS (params.H100NVL_KV_POOL_TOKENS is a named constant, "
              "never a default); a prefix that leaves both warm tiers is COLD, not lost"),
    dict(section="D56 P_host as a function of host occupancy",
         code="tiers.p_host_from_occupancy, params.Params.p_host_for",
         note="StudyENG1b's measured 0.999 with room; the host eviction rule's kept fraction "
              "when the host tier is full; 0.0 with no host tier (StudyENG1b's E0 server)"),
    dict(section="D56 host eviction rule, pluggable, default LRU",
         code="tiers.lru_rule, tiers.largest_first_rule, params.Params.host_eviction_callable",
         note="ASSUMPTION until StudyENG1c measures it (tiers.EVICTION_RULE_ASSUMPTION)"),
    dict(section="D56 bounded capacity in the memory decision",
         code="readiness.tier_assignment",
         note="both warm tiers bounded, the remainder demoted to COLD; 'denied' kept as an "
              "alias of 'cold' so no reader silently changes quantity"),
    dict(section="D57 per-tier score calibration",
         code="calibration.TierCalibration, calibration.MonotoneMap, calibration.load",
         note="monotone raw score to probability, loaded from a file, fitted on DEV by "
              "StudyCTRL1c; identity is the default and is NOT a calibration"),
    dict(section="D57 loud failure on an uncalibrated cross-tier comparison",
         code="calibration.require_calibrated, calibration.rank_across_tiers",
         note="raises unless a calibration exists or the caller is a test using "
              "calibration.identity_for_tests"),
    dict(section="D57 the cloud upgrading the device's answer",
         code="calibration.upgrade_decision, coordinator.Coordinator.upgrade_device_answer",
         note="compared on the common calibrated probability scale, never on raw scores"),
    dict(section="StudyENG1b mechanistic prefix loss, tail first",
         code="kvpool.PrefixEntry.head_tokens, kvpool.KVPool.make_room, kvpool.KVPool.allocate",
         note="the surviving part is the prefix's HEAD; allocation is the only thing that "
              "evicts, which is StudyENG1b's verdict"),
    dict(section="StudyENG1b staircase as the A6 point 2 long-gap fallback ONLY",
         code="kvpool.eng1b_long_gap_curve, kvpool.ENG1B_STAIRCASE",
         note="not used by predict_loss and not used by T0, whose question is whether the "
              "bookkeeping reproduces the staircase"),
    dict(section="StudyENG1b queueing behind running work at resume",
         code="rollout.Rollout._prefix_risk",
         note="resume_queue_s is read off the rollout's own engine timeline, not a constant"),
    dict(section="spec 8 mu estimator chosen explicitly",
         code="params.Params.mu_estimator, coordinator.Coordinator._update_mu",
         note="'none' by default, which holds mu at the PLACEHOLDER 0 and says so; the spec "
              "does not determine an estimator"),
    dict(section="11 approval tests T0", code="t0_harness.T0Harness"),
    dict(section="11 approval tests T0, the measured engine model",
         code="eng1_engine.Eng1Engine, eng1_engine.StepModel",
         note="StudyENG1's committed step model, front-end serialization and admission stall; "
              "no coefficient is refitted here"),
    dict(section="11 approval tests T0, one-shot holdout mode",
         code="t0_harness.T0Harness.run_holdout_once, t0_harness.FrozenState",
         note="requires the frozen hashes, logs timestamp and hashes, and refuses a second run "
              "once a result file exists"),
    dict(section="11 approval tests T0, trace replay of the recorded trials",
         code="trace_replay.load_part_c_trials, trace_replay.predict_trial, "
              "trace_replay.predict_eng1b_trial",
         note="the trial's ACTUAL recorded arrivals, sizes and timing are replayed"),
    dict(section="12 evaluation implications", code="m4.measure_decision_time",
         note="this row measures M4 only; the two evaluation tracks belong to the live study"),
]

AMBIGUITIES: List[Dict[str, Any]] = [
    dict(id="A1", where="spec 3.5 Jhat_H", question="Is Uhat_H an absolute utility or a gain "
         "against the device's own answer?",
         choice="GAINS, so device-only is exactly zero.",
         why="Spec 3.2 defines the quantity the policy optimizes as a GAIN. The two readings "
             "differ by a constant that is identical in both rollouts of a DeltaJ, so no decision "
             "changes; the gain reading makes an action's sign readable on its own.",
         reversible_at="rollout.Rollout._opportunity_utility"),
    dict(id="A2", where="spec 4.1 u_SH(cloud, d, m)", question="What delay d does an opportunity "
         "served by an older held answer carry?",
         choice="d = opportunity instant minus the serving answer's CAPTURE time.",
         why="This is StudyE9b's own sample-and-hold semantics, which every committed Nexar "
             "number uses; measuring d from the delivery instead would make a held answer "
             "eternally fresh.",
         reversible_at="rollout.Rollout._opportunity_utility"),
    dict(id="A3", where="spec 8 'update mu'", question="Spec 3.5 and 8 use mu as a GPU-backlog "
         "price but give no update rule.",
         choice="An EWMA of the realized marginal utility per GPU-second of the last released "
                "item, floored at zero, with alpha a PLACEHOLDER parameter.",
         why="Spec 6.3 defines nu_tier the same way (the gain per byte of the last promotion "
             "into a full tier), so the analogous rule for GPU time is the one the spec's own "
             "style implies. It carries no evidence and is marked PLACEHOLDER.",
         reversible_at="coordinator.Coordinator._update_mu"),
    dict(id="A4", where="spec 5.4 Phat_r", question="The expected-value rollout produces a "
         "schedule, not a distribution, so what is the PROBABILITY of finishing?",
         choice="The indicator of the continuation schedule meeting the deadline, multiplied by "
                "P(reachable within H_s).",
         why="Spec 5.1 makes the expected-value rollout the default and sampled scenarios "
             "optional (flag off). An indicator is the honest reading of a deterministic "
             "schedule; with the sampling flag on it becomes a frequency over draws.",
         reversible_at="continuation.p_finish"),
    dict(id="A5", where="spec 7.3 'competing work'", question="How much competing engine time "
         "does pi_0 put ahead of a job's remaining pieces?",
         choice="An explicit `competing_s` argument, zero by default, supplied by the caller from "
                "the calendar and the arrival rates.",
         why="The spec describes the quantity but not its estimator. Making it an argument keeps "
             "the estimator outside the feasibility rule, so a better estimator does not change "
             "the classification code.",
         reversible_at="continuation.continuation_schedule"),
    dict(id="A6", where="spec 4.3 durations", question="StudyRH5 measured 11k and 28k histories "
         "only; what rate applies at other sizes?",
         choice="The committed rate at the NEAREST measured size, never an extrapolation outside "
                "the measured pair.",
         why="The profile states a linear interpolation rule between the two sizes for warm "
             "states; outside them there is no evidence, and this repository's own failures "
             "(E30 versus E32) came from carrying a rate past its measurement.",
         reversible_at="profiles.Profiles.seconds_per_token"),
    dict(id="A7", where="spec 6.1 'the next colder state or the device'",
         question="Which is the comparison when the belief is a distribution over three tiers?",
         choice="max(expected utility of the next colder tier, the device's own accuracy), under "
                "the same belief distribution.",
         why="Spec 6.1 writes 'or the device', and the device is always available (spec 1.1), so "
             "the fallback is whichever is better; using the colder tier alone would credit "
             "readiness for beating an option no one would take.",
         reversible_at="readiness.state_value"),
    dict(id="A8", where="spec 7.7 'instability over n_c frames'",
         question="Variance or answer flips?",
         choice="Both, selected on DEV, exactly as StudyCTRL1-episodes implemented it (its A2).",
         why="The policy must accept whichever reading the DEV fit chose, or the fitted "
             "parameters are not transferable.",
         reversible_at="controller.DeviceController.signal"),
    dict(id="A9", where="spec 7.7 rise term", question="The rise is written unnormalized while "
         "all three signals are called self-normalized.",
         choice="Rise and instability are divided by the same window IQR as z.",
         why="A raw log-unit rise and a dimensionless z cannot share one threshold without a unit "
             "error; this matches StudyCTRL1-episodes (its A1), so the fitted theta transfers.",
         reversible_at="controller.DeviceController.signal"),
    dict(id="A10", where="spec 7.2 step 3", question="How many releases may one event commit?",
         choice="Repeat while some pending item has positive DeltaJ_H, bounded by a configurable "
                "max_releases, and re-score after every release.",
         why="Spec 7.2 says one release at a time, re-score, repeat until none is positive, and "
             "spec 7.2 step 5 says commit only the immediate releases. The bound exists so a "
             "pathological state cannot spin; it is not a policy parameter.",
         reversible_at="coordinator.Coordinator._release_loop"),
    dict(id="A11", where="spec 3.1 and 3.3", question="A declined or suppressed escalation counts "
         "as a device-only OUTCOME; does it count as a FAILURE for Z?",
         choice="It counts as an opportunity whose outcome is the device's, and it meets the SLO "
                "only if the device's own answer does.",
         why="Spec 3.1 says exactly this ('a suppressed or declined escalation counts as a "
             "device-only outcome') and notes that suppression therefore cannot improve measured "
             "attainment by hiding difficult situations.",
         reversible_at="rollout.Rollout._opportunity_utility"),
    dict(id="A12", where="the brief's oracle arm (StudyCTRL1b)", question="Can an oracle that "
         "escalates only before positive events be an upper bound on any trigger?",
         choice="No, and both readings are reported. See StudyCTRL1b's B2b.",
         why="The two tiers' scores are on different scales, so a label-correlated escalation "
             "pattern moves a rank metric by itself. This is the measured reason spec 4.1's u_SH "
             "must be a CALIBRATED utility and not a raw tier score, and the policy reads u_SH "
             "from the DEV table rather than from any score.",
         reversible_at="utility.u_sh_cloud and the profile's mapping entry"),
    dict(id="A14", where="v3.1 A1 device uncertainty", question="The addendum makes the device's "
         "self-normalized uncertainty a determinant of Ghat, but no committed DEV table maps "
         "uncertainty to gain.",
         choice="The multiplier is IDENTITY and marked PLACEHOLDER; the slot is a single "
                "callable.",
         why="Inventing a monotone function here would put an unmeasured curve inside every "
             "escalation decision. Addendum A4 names the measurement that fills it, "
             "StudyCTRL1b's predictability-ceiling arm, and a test asserts that filling the slot "
             "changes Ghat without touching any other code.",
         reversible_at="escalation.GhatTables.uncertainty_multiplier"),
    dict(id="A15", where="v3.1 A1 evidence coverage", question="Which device accuracy applies "
         "when the request references evidence outside the device's window?",
         choice="In window, the committed 4B-D2 table (StudyE7 Job A); out of window, the "
                "committed device-N1-orin table (StudyF4 Part A).",
         why="Those are the two committed measurements of the device answering WITH and WITHOUT "
             "its history, so their gap is the measured value of the cloud holding more "
             "evidence. No new number is introduced.",
         reversible_at="escalation._device_accuracy"),
    dict(id="A16", where="v3.1 A3 task-type posterior", question="What is the posterior when the "
         "keyword and temporal-reference rules match nothing?",
         choice="Ghat REFUSES to score the request (MissingEvidence) rather than assuming a "
                "uniform posterior.",
         why="A uniform posterior over eight question types is a fabricated belief that would "
             "flow straight into an admission decision. Addendum A3's own fallback is the device "
             "model labelling the question, and no committed measurement of that labelling "
             "accuracy exists, so the honest state is a refusal that names what is missing.",
         reversible_at="escalation.type_posterior and escalation.ghat"),
    dict(id="A17", where="v3.1 A1 versus spec 13 P2", question="The addendum says every type is "
         "escalated on one rule, but there is no committed SS accuracy at all.",
         choice="SS is refused by the EVIDENCE gap, never by a type rule: ghat raises because the "
                "SS table is missing, exactly as it would for an RC type with no committed "
                "accuracy.",
         why="This keeps the addendum's requirement literally true, that no type is routed by "
             "rule, while not inventing an SS accuracy. The refusal message names the missing "
             "table rather than the task type.",
         reversible_at="profiles.Profiles.omega and the SS rows of the profile"),
    dict(id="A18", where="v3.1 A2 (Q11)", question="Which SH trigger family is the default while "
         "the question is open?",
         choice="DeviceFilter with threshold 0, that is escalate when Ghat is positive at all.",
         why="Zero is the only threshold that carries no fitted content: it says escalate exactly "
             "when the estimated gain is positive. The family is an injected object, so "
             "StudyCTRL1b's measured winner replaces it with one assignment.",
         reversible_at="coordinator.Coordinator.sh_trigger"),
    dict(id="A19", where="spec 3.5 terminal value", question="Spec 3.5 writes "
         "'+ mu * (GPU backlog at t + H)' while mu is described everywhere else as a PRICE "
         "(spec 7.7: pi = mu x GPU-seconds, how expensive help is right now). Taken literally, "
         "backlog would RAISE terminal value.",
         choice="Backlog SUBTRACTS: the term is -mu * residual_backlog_s.",
         why="A price that rewards backlog would make every admission look better the more work "
             "it leaves behind, which inverts the mechanism mu exists for and contradicts spec "
             "6.3's nu_tier, defined as the gain per byte of the last promotion into a full "
             "tier. A unit test (a declined query under a large mu) is what surfaced the "
             "literal reading as untenable.",
         reversible_at="rollout.Rollout._terminal"),
    dict(id="A20", where="v3.1 A2 as revised (the user's message of 2026-11-15)",
         question="At the time of StudyPOL2-build, did the addendum file carry the superseded "
                  "'METADATA escalation request' wording for queries?",
         choice="The code implements the revision: queries complete by default, question-first "
                "as an exception. RESOLVED 2026-11-16 by StudyPOL3-update: the committed "
                "research/POLICY_SPEC_v3_1_ADDENDUM.md carries the CURRENT A2 (a query is sent "
                "COMPLETE by default) and A6 titled Partial-prefix survival, so the file and "
                "the code AGREE and the POL2 report's claim of a live discrepancy was stale. "
                "The entry is kept as the record of how the revision reached the code.",
         why="The user confirmed the pasted file is the latest and directed the change "
             "explicitly. Keeping the entry rather than deleting it preserves the provenance of "
             "the choice; the stale sentence in reports/study_pol2_build.md was corrected in "
             "place and says what it used to say.",
         reversible_at="coordinator.Coordinator.escalate and escalation.choose_path"),
    dict(id="A21", where="v3.1 A2 as revised, ordering",
         question="The path choice needs Ghat (to judge 'higher-value traffic') and Ghat's "
                  "timeliness term needs the path. Which is computed first?",
         choice="Ghat on the COMPLETE path first, that value decides the exception, and if the "
                "path switches Ghat is RECOMPUTED on the path actually used.",
         why="The default path is the one to score first, and recomputing is cheap (one Ghat is "
             "about 4 microseconds by M4), so the reported Ghat and deadline check always "
             "describe the real path rather than the default.",
         reversible_at="coordinator.Coordinator.escalate"),
    dict(id="A22", where="v3.1 A2 as revised, delivered delay",
         question="The revised A2 is cited for 'A2 formulas', but the file contains no formula "
                  "for either query path.",
         choice="Spec 4's delivered-delay definition per path: COMPLETE is "
                "up(question) + up(payload) + compute + down; QUESTION-FIRST adds one CONTROL "
                "ROUND TRIP (the device's own RTT) and the coordinator's measured decision "
                "latency from M4, and REFUSES to quote a delay when M4 is unmeasured.",
         why="Spec 4 is the only committed delivered-delay definition, and the two extra terms "
             "are exactly what the user's instruction names. Refusing rather than defaulting to "
             "zero keeps the path from being quoted as cheaper than it is.",
         reversible_at="coordinator.Coordinator.predicted_delivered_delay_s"),
    dict(id="A23", where="v3.1 A6.2", question="P_loss is 'the probability the built prefix is "
         "evicted'. With a deterministic predicted eviction, is that an indicator?",
         choice="The FRACTION of the prefix's blocks the predicted demand frees.",
         why="A partial eviction is the common case and it costs a partial restore, so a "
             "fraction carries the information an indicator throws away, and it multiplies "
             "cleanly by the restore cost in A6.1's formula.",
         reversible_at="kvpool.KVPool.predict_loss"),
    dict(id="A24", where="v3.1 A6.1 P_host", question="A6 assigns P_host to M5, which has not "
         "been run.",
         choice="Default 0.0, the CONSERVATIVE extreme: assume evicted blocks are NOT "
                "recoverable and a full rebuild is needed.",
         why="It never understates the cost of deferring, and it matches spec 6.5's own "
             "convention that ambiguity resolves toward the colder tier. A measured M5 value "
             "replaces one parameter.",
         reversible_at="params.Params.p_host"),
    dict(id="A25", where="v3.1 A6.2 beyond the horizon", question="A6 extends P_loss with the "
         "measured survival curve where the rollout does not reach the resume time; no such "
         "curve exists.",
         choice="The curve is a pluggable callable defaulting to NONE, the beyond-horizon part "
                "of the gap then contributes zero, and every affected result carries "
                "`beyond_horizon_unmeasured`.",
         why="Zero is the only value that adds no unmeasured content, and the flag stops the "
             "result being read as if the long-gap case had been modelled.",
         reversible_at="params.Params.survival_curve and kvpool.survival_p_loss"),
    dict(id="A26", where="v3.1 A6.1 versus spec 5.4", question="How does the expected restore "
         "work change a DeltaJ when the job still meets its deadline?",
         choice="Through spec 5.3's third terminal item: the restore work is GPU backlog not "
                "covered by any job's continuation value, priced at mu.",
         why="Phat_r is an indicator (A4), so restore work that still fits before the deadline "
             "cannot move the continuation value at all; without this channel A6 would be "
             "invisible to release timing. THE CONSEQUENCE IS STATED RATHER THAN HIDDEN: mu is a "
             "PLACEHOLDER at 0, so with the shipped default this channel is SILENT and A6 "
             "reaches decisions only through feasibility and the memory decision. A test pins "
             "that fact.",
         reversible_at="rollout.Rollout._terminal"),
    dict(id="A27", where="v3.1 A6.1 'for the defer branch'", question="Which demand can evict "
         "the prefix, all of the horizon's or only part?",
         choice="Only the competing work released AFTER this job's prefix was last referenced, "
                "that is inside the exposure window.",
         why="A6's mechanism is that the prefix is unreferenced BETWEEN pieces. Charging a "
             "job's own released piece for the risk it removes made deferring look cheaper than "
             "releasing, which inverts A6; scoping the demand to the exposure window is what "
             "makes release strictly safer than deferral, as the spec intends.",
         reversible_at="rollout.Rollout._prefix_risk"),
    dict(id="A28", where="v3.1 A6.4 'observed or believed likely'", question="What makes a loss "
         "'likely'?",
         choice="P_loss at or above `Params.prefix_loss_replan_threshold`, default 0.5, swept.",
         why="The spec gives no number. 0.5 is the neutral reading of 'likely' and is a declared "
             "PLACEHOLDER rather than a fitted value.",
         reversible_at="params.Params.prefix_loss_replan_threshold"),
    dict(id="A29", where="v3.1 A6.1 units", question="A6 writes w_left as 'the job's unreleased "
         "pieces', a count, while the restore terms are costs.",
         choice="Everything is converted to ENGINE SECONDS through the engine model.",
         why="A count and a cost cannot be added. Engine seconds is the unit the continuation "
             "schedule and the step model already use, so the sum composes with both.",
         reversible_at="continuation.expected_remaining_work"),
    dict(id="A13", where="spec 7.4", question="Which piece sizes are candidates?",
         choice="The committed measured sizes (1,024 and 2,048 tokens) plus whole-job, with the "
                "closed form k* available only as a seed.",
         why="Spec 7.4 says measured sizes plus whole-job and that the closed form is not a "
             "foundational claim; SLICE1 Parts A-D measured exactly those two sizes.",
         reversible_at="params.Params.piece_sizes_tokens"),
    dict(id="A30", where="D56 P_host when the host tier is FULL",
         question="StudyENG1b measured P_host = 0.999 WITH room on the host tier and says "
                  "nothing about a full one. What is P_host at full occupancy?",
         choice="P_host = 0.999 times the fraction the HOST EVICTION RULE keeps, and the result "
                "is flagged measured = false.",
         why="The 0.999 is a property of the write-through connector, which is unaffected by "
             "occupancy; what occupancy changes is how much the host tier can still hold. "
             "Splitting it that way keeps the measured part measured and puts the unmeasured "
             "part behind the eviction rule, where StudyENG1c will replace it.",
         reversible_at="tiers.p_host_from_occupancy"),
    dict(id="A31", where="D56 host eviction order",
         question="In what order does the offloading connector's host tier evict?",
         choice="LRU, labelled ASSUMPTION in code and in the report.",
         why="StudyENG1 Part D found vLLM 0.31.0 exposes eviction only as sampled lifetime and "
             "idle histograms and no counter for cached-but-unreferenced blocks, so the order "
             "was never observed. LRU mirrors the GPU pool's own free-block order, which is the "
             "one order this engine is known to use. D56 assigns the measurement to StudyENG1c "
             "and the rule is a pluggable callable.",
         reversible_at="params.Params.host_eviction_rule"),
    dict(id="A32", where="D57 what the default calibration should be",
         question="With StudyCTRL1c's maps not yet delivered, should the default identity map "
                  "be permitted for a cross-tier comparison?",
         choice="NO. A cross-tier comparison under identity maps RAISES "
                "(calibration.CalibrationMissing); a comparison inside one tier is allowed; a "
                "test opts in explicitly through calibration.identity_for_tests.",
         why="The brief says to fail loudly outside tests, and StudyCTRL1b measured that the "
             "two tiers' raw scores are on different scales (ambiguity A12). An identity map is "
             "the ABSENCE of a calibration, and a silent absence is the failure mode this "
             "repository's record is made of. A single-tier comparison needs no calibration "
             "because a monotone map preserves order.",
         reversible_at="calibration.require_calibrated"),
    dict(id="A33", where="spec 8 'update mu', revisited for StudyPOL3-update",
         question="The brief asks for the estimator THE SPEC DEFINES. Does spec v3 define one?",
         choice="NO. Spec 8 says only 'update mu', spec 3.5 and 5.3 define what mu PRICES, spec "
                "7.7 defines what mu is MULTIPLIED BY, and spec 9's parameter table does not "
                "list mu at all. So mu stays at the PLACEHOLDER 0 and the ESTIMATOR IS NOW AN "
                "EXPLICIT PARAMETER (Params.mu_estimator, default 'none'), with the options and "
                "their consequences written out in reports/study_pol3_update.md.",
         why="POL2's ambiguity A3 implemented an EWMA and left it running, so mu would have "
             "drifted off its placeholder without anyone choosing it. The brief forbids "
             "choosing silently in either direction, so the choice is now a named parameter "
             "whose default does nothing and says so.",
         reversible_at="params.Params.mu_estimator"),
    dict(id="A34", where="StudyENG1b's staircase versus A6 point 2's 'survival curve'",
         question="A6 point 2 extends P_loss with a measured survival curve for gaps the "
                  "rollout does not reach. StudyENG1b's verdict is that survival is a step "
                  "function of ALLOCATED KV and that gap LENGTH matters only through "
                  "allocation. Is the curve a function of seconds or of allocation?",
         choice="OF ALLOCATION, as a fraction of the free pool "
                "(kvpool.eng1b_long_gap_curve), and a caller with a long gap converts the gap "
                "to predicted allocation itself. It is NOT the default and is NOT used in T0.",
         why="A curve in seconds would be a curve in the wrong variable: StudyENG1b's "
             "episodic-only loads never evicted the prefix at gaps up to 20 s, while f >= 1.0 "
             "loads lost it at 10 s. Keeping it out of predict_loss is what makes T0 a test of "
             "the bookkeeping rather than a test of the curve against itself.",
         reversible_at="params.Params.survival_curve and kvpool.eng1b_long_gap_curve"),
    dict(id="A35", where="T0's unit of comparison",
         question="StudyENG1 Part C measures the imposed delay as a DIFFERENCE between a paired "
                  "with-run and without-run. Should T0 predict absolute TTFTs or the paired "
                  "difference?",
         choice="THE PAIRED DIFFERENCE, simulated the same way the measurement was taken: the "
                "same recorded arrival schedule is replayed twice, once with the action and "
                "once without, and the predicted imposed delay is the difference of the two "
                "simulated TTFT sums.",
         why="That is literally the measured quantity, and any error common to both arms "
             "cancels in exactly the way it cancels in the measurement. Predicting absolute "
             "TTFTs and differencing afterwards would be a different and harder quantity that "
             "StudyENG1 did not report.",
         reversible_at="trace_replay.predict_trial"),
]


def check() -> Dict[str, Any]:
    """Every SPEC_MAP symbol must resolve. The test suite calls this."""
    import importlib
    missing = []
    for row in SPEC_MAP:
        for sym in row["code"].split(","):
            sym = sym.strip()
            if not sym:
                continue
            mod, _, rest = sym.partition(".")
            try:
                m = importlib.import_module("." + mod, package=__package__)
            except ModuleNotFoundError:
                missing.append(sym)
                continue
            obj: Any = m
            ok = True
            for part in [p for p in rest.split(".") if p]:
                if hasattr(obj, part):
                    obj = getattr(obj, part)
                    continue
                fields = getattr(obj, "__dataclass_fields__", {})
                if part in fields:
                    obj = fields[part]
                    continue
                ok = False
                break
            if not ok:
                missing.append(sym)
    return dict(n_sections=len(SPEC_MAP), n_ambiguities=len(AMBIGUITIES), missing=missing,
                ok=not missing)
