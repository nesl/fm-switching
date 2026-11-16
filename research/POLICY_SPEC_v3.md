# Scheduling policy: full specification (v3, frozen for building pending review)

Status: v3, 2026-11-15. Revises v2 after the second external review. Decision record: `claude/policy_design_log.md` (D1-D50, approval tests T0-T4, measurements M1-M4, hypothesis H1, pinned items P1-P12). Where this document and the log disagree, the log is the record and this document must be corrected.

Scope: the entire policy, excluding only pinned (deferred) items (D36). Nothing is cut. Mechanisms whose benefit is not yet established are fully specified but carry an explicit ENABLING CONDITION (D38) and are evaluated on and off.

Claimed contribution (D50): a non-learned, counterfactual coordinator for a shared cloud accelerator serving many devices, which jointly decides (1) admission of escalated inference, (2) release timing and execution granularity of cloud work, including multi-second historical reconstruction, and (3) management of execution readiness of per-device history, according to each action's effect on application utility and per-device SLOs across the whole fleet. Conditional mechanisms (escalation price, phase assignment, merging, summaries, predictive upload) are specified and evaluated but are not part of the central claim until their individual contributions are measured.

All tables and estimates used by the policy are fitted on DEV data only (D6). Every committed result cited here is subject to the pending audit of results from StudyE6 onward (P4).

## Changes from v2

| # | change | sections |
|---|---|---|
| 1 | Job-level CONTINUATION VALUE for partially completed historical reconstruction, estimated from a feasible continuation schedule; kept separate from state value for future questions | 3.5, 5.3, 5.4 |
| 2 | Common CONTINUATION POLICY pi_0 (EDF over pending work and the calendar) for both sides of every comparison; the scheduler is a rollout over that base policy | 3.5, 5.1 |
| 3 | FEASIBILITY classification of historical jobs (feasible / feasible only with priority / infeasible) with bounded waiting for feasible jobs and loss-cutting for infeasible ones | 7.3 |
| 4 | Believed residency verified from engine TELEMETRY (local vs external cache hits, offload activity, evictions where available), conservative probabilistic belief when ambiguous; REQUESTED vs CONFIRMED transitions | 6.5 |
| 5 | SEPARATE demand rates per device: recall-query rate (per representation) vs escalation rate; state value uses only queries that use that representation | 2.1, 6.1, 6.4 |
| 6 | Execution READINESS is the representation-related dimension currently supported by evidence; SUMMARY selection is exercised only if SUMMARY passes its enabling condition | 6, 7.10, 13 |
| 7 | CONFIDENCE-AWARE capacity metric and per-device SLO-margin distributions | 12 |
| 8 | Claimed contribution stated explicitly (core only) | header, 7.0 |

---

## 1. Setting and assumptions

### 1.1 System

- A fleet of devices i in I. Each runs its own small VLM (currently a 4B) continuously on its own camera and keeps its own history locally. The device always answers and always holds its own state.
- One shared cloud replica runs a large VLM (currently a 32B) in an engine with continuous batching and chunked prefill (vLLM). GPU time and GPU memory for held context (KV) are finite and shared. A host-memory tier is always available (D29).
- Each device reaches the cloud over its own link with time-varying bandwidth, round-trip time and outages. Links do not interfere with each other. The network's only cost in the policy is latency (D33).
- KV cannot move between device and cloud (different model sizes).

### 1.2 Task types and eligible opportunities (D19, D37)

| task type k | example | eligible opportunity (SLO denominator) | what an admitted escalation starts | value decay |
|---|---|---|---|---|
| SH, short horizon | cut-in, collision anticipation | every decision instant on the task's evaluation cadence while the task is active, escalated or not | an EPISODE of repeated cloud calls at cadence T_k until resolved or E_k calls | gradual with delivered delay |
| SS, single shot | where are my keys, identify a sign | every query | one call | cliff at L_SS |
| RC, long-horizon recall | question about events minutes ago | every question | one job needing the device's history on the cloud (possibly multi-second reconstruction) | cliff at the deadline |

The device answers every opportunity locally and immediately; a cloud answer, when it arrives in time, upgrades it.

### 1.3 Assumptions

- A2. Answer value falls with delivered delay (gradual for SH, cliff for SS and RC).
- A3. Making a device's history usable on the cloud costs GPU work whose size depends on readiness (rebuilt from stored frames, reloaded from host, or already on the GPU).
- A4. The engine cannot preempt a submitted request; how strongly one request delays others depends on how the engine shares each step (M1).
- A5. KV is not portable between device and cloud.
- A6. Payload per call is fixed per task (D31).
- A7. Devices accept two small control messages (episode phase, escalation price), both for conditional mechanisms.
- NOT assumed: that the cloud answer is better. Cloud benefit is estimated per request and may be zero or negative (D39).
- Scope restriction to be stated in the manuscript: RECENT evidence is handled on the device; cloud-side history management concerns RICH and (conditionally) SUMMARY.

---

## 2. Entities and state

### 2.1 Per device i

- Link estimate: bandwidth b_i, RTT_i, reachable flag u_i, short-term trend.
- Controller state per active task (7.7).
- Active episodes: task type, cadence T_k, phase phi_e (if enabled), calls issued, start time.
- Cloud-side history per representation rep in {RICH, SUMMARY (if enabled)}:
  - desired tier (from 6.3);
  - BELIEVED tier distribution over {GPU, HOST, STORED} (6.5);
  - staleness s(i, rep); unsent frames f_unsent(i); size m(i, rep).
- Demand estimates (D48), all EWMA with DEV priors:
  - lambda_i^rc(rep): rate of recall queries that would use representation rep (from question-type mix);
  - lambda_i^esc: rate of escalations (SH episodes, SS calls);
  - optional conditional recall rate during episodes, used ONLY if DEV data shows recall questions concentrate around episodes.
- SLO deficit counters Z(i, k).

### 2.2 Cloud

- Engine state: requests in flight; per-step occupancy; engine cache telemetry (6.5).
- Pending set P of requests, jobs and pieces not yet released.
- Historical jobs: for each admitted RC job r, remaining work w_r (pieces left, predicted time), deadline D_r, feasibility class (7.3), and its continuation plan.
- Calendar C(t, t + H) of known and expected arrivals over the planning horizon H (D25).
- Terminal prices for effects beyond the horizon: mu (GPU backlog), nu_tier (memory).

---

## 3. Objective, SLOs and the action score

### 3.1 SLOs over eligible opportunities (D37)

For each device i and task type k it uses, an SLO (q_k, L_k, p_k): at least a fraction p_k of the device's eligible opportunities of type k receive an answer (the one the application actually used) with quality at least q_k within latency L_k. A suppressed or declined escalation counts as a device-only outcome. Cloud-admission success is reported separately.

### 3.2 Bounded task utility (D40)

Each task type k has a bounded utility u_k(answer, delivered delay) in [0, 1] from DEV-calibrated tables (section 4). A cloud action's gain on opportunity r:

    g_r(x) = omega_k * ( u_k(cloud answer under x) - u_k(device answer) )

with class weights omega_k calibrated on DEV. g_r may be zero or negative.

### 3.3 Deficit counters: virtual-queue heuristic (D41)

Per device and task type, updated per eligible opportunity when its outcome is known:

    Z(i, k) <- max( Z(i, k) + p_k - Shat_r , 0 )

No formal guarantee is claimed.

### 3.4 Predicted vs measured success (D42)

Online: Shat_r from DEV tables conditioned on what is observable. Offline: S_r measured against ground truth over all eligible opportunities. The gap is reported.

### 3.5 The action score: counterfactual marginal value under a common continuation policy (D43, D45, D46)

Let S_t be the observable state, A_t the feasible actions, H the planning horizon, and pi_0 the CONTINUATION POLICY used for every decision after the candidate action inside the rollout. pi_0 is EDF over the pending set and the calendar (deadline-ordered release, one unit at a time, using the same engine model), with episodic calls at their due times.

    Jhat_H(S_t, a; pi_0) = Uhat_H + sum over (i, k) of Z(i, k) * Phat_success_H(i, k) + TerminalValue(S_{t+H})

    TerminalValue(S_{t+H}) = sum over unfinished RC jobs r of ContValue_r(S_{t+H})       (5.4)
                           + sum over (i, rep) of StateValue(i, rep, S_{t+H})            (6.1, future questions only)
                           + mu * (GPU backlog at t + H not already in a job's continuation value)

    DeltaJ_H(a) = Jhat_H(S_t, a; pi_0) - Jhat_H(S_t, a_ref; pi_0)

Reference actions: admission vs decline; release a piece vs defer it to its next candidate slot; state action vs no change; episode call dispatch vs hold to the next slot.

Interpretation: the scheduler is a ROLLOUT over the base policy pi_0. It changes the immediate decision only when the simulated future under pi_0 says the change is better. With an exact simulator, rollout cannot do worse than its base policy; ours is approximate, so no guarantee is claimed and T0 measures the approximation. EDF is therefore also the first baseline the scheduler must beat (T2).

---

## 4. Utility models per task type

Delivered delay (D30):

    d = t_up + t_queue + t_compute + t_down,   t_up = payload_bytes_k / b_i + RTT_i / 2,   t_down = RTT_i / 2

### 4.1 SH

u_SH(cloud, d, m) from DEV curves (m frames; m > 1 only for a merged call, 7.9); u_SH(device). Per-call utility is a surrogate for Nexar challenge mAP; validation is T1 (P7). A call not answered in time is a device-only outcome; a later merged call cannot serve an earlier opportunity.

### 4.2 SS

u_SS(cloud, d) = acc_SS^cloud if d <= L_SS, else the device's answer is used.

### 4.3 RC

    T_ready = t_upload(f_unsent, if needed) + t_restore(rep, believed tier) + t_catchup(rep, s) + t_answer(rep)
    u_RC = acc(qtype, rep) if T_ready + t_queue + t_down <= D_RC, else the device's answer is used

Expected utility uses the predicted distribution of T_ready and the believed-tier distribution (6.5).

---

## 5. Counterfactual accounting (D15, D16, D18, D43, D45, D46)

### 5.1 Horizon rollout

Jhat_H is computed by rolling the engine forward over H:
- the candidate action (or the reference action) at time t, then pi_0 for every later decision inside the horizon;
- requests in flight, calendar arrivals, expected unknown arrivals at their estimated rates (expected-value rollout; optionally a few sampled scenarios);
- engine model: the measured step-time and admission model (M1);
- outputs: predicted delivery times of every affected opportunity, the state of every RC job at t + H, believed tiers at t + H.

### 5.2 Fidelity requirement (T0)

Before decisions rely on the rollout, T0 must show that predicted delays imposed on others match live measurements within a stated tolerance across evaluation conditions. The simulator's engine model failed out-of-sample on slice-versus-episodic interactions (SIM1d, 10), which is why T0 precedes building.

### 5.3 Terminal value: one rule

Everything inside the horizon is accounted for by the rollout. Only what the horizon leaves behind is valued, each item exactly once:
- unfinished RC jobs: continuation value (5.4);
- per-device readiness: state value for FUTURE questions (6.1), excluding the question whose job is already valued in 5.4;
- residual GPU backlog not covered by any job's continuation value: mu per GPU-second.

### 5.4 Job-level continuation value (D45)

For an unfinished RC job r at the horizon end, with remaining work w_r and deadline D_r:

    ContValue_r(S) = omega_RC * ( acc(qtype, rep) - acc^device(qtype) ) * Phat_r(finish by D_r | w_r, S, pi_0)
                     + Z(i(r), RC) * dPhat_success attributable to finishing r

Phat_r is estimated from a FEASIBLE CONTINUATION SCHEDULE: pi_0's planned release slots for r's remaining pieces, given the calendar and expected arrivals beyond the horizon (a coarse extension of the rollout to D_r using the same engine model at reduced resolution). It is not estimated from tokens processed. Releasing a piece of r earns the increase in ContValue_r it causes; this is what makes multi-second jobs schedulable under a short horizon without over-crediting partial work that cannot finish in time.

### 5.5 Fallback approximation

When a full rollout is too expensive (M4), the closed-form channel approximation may be used (direct delay of overlapping requests from the step model times a load factor from step occupancy), with mu applied only to work not in channel 1 and the continuation value of 5.4 retained. The fallback must itself pass T0.

---

## 6. State management (D9, D12, D14, D26)

The representation-related dimension currently supported by evidence is EXECUTION READINESS (GPU / HOST / STORED). Choosing between representations (RICH vs SUMMARY) is exercised only if SUMMARY passes its enabling condition (7.10) (D49).

### 6.1 State value (future questions only)

    P_i^rep(need within H_s) = 1 - exp( - lambda_i^rc(rep) * H_s )

    StateValue(i, rep, S) = P_i^rep(need within H_s) * [ expected u_RC gain from this readiness state
                                                         - expected u_RC gain from the next colder state or the device ]

Only recall queries that would use rep enter (D48). Escalation activity does not raise history value unless the DEV-validated conditional recall rate applies. A partially rebuilt history contributes state value for future questions; the question whose job is in progress is valued only through its continuation value (5.4).

### 6.2 State actions

| action | effect | how enacted on the current stack |
|---|---|---|
| PROMOTE (reload) | HOST -> GPU | a request reusing the prefix; transition confirmed by telemetry (6.5) |
| PROMOTE (rebuild) | STORED -> GPU (or HOST via the offload connector) | prefix-chained requests; confirmed by telemetry |
| DEMOTE | GPU -> HOST, or drop KV (frames kept) | partially enforceable (offload is engine-driven; explicit eviction may not be exposed) |
| CATCH UP | materialize stale frames | an append request |
| REFRESH SUMMARY | conditional (7.10) | a generation request |
| REQUEST UPLOAD | conditional (7.11) | device-side |

Each is scored by DeltaJ_H against "no change" and taken only if positive. Future-value credit is given only for CONFIRMED transitions (6.5).

### 6.3 Tier assignment: approximate

Greedy promotion by StateValue gain per byte of the scarce tier, within GPU capacity (after reserving working space for in-flight requests) and host capacity. An approximation of a multiple-choice knapsack; evaluation compares it against a stronger offline allocation on recorded traces. nu_tier = gain per byte of the last promotion into a full tier. Re-solved on events and every few seconds; moves happen only through state actions with DeltaJ_H > 0.

### 6.4 Demand predictors (D48)

- lambda_i^rc(rep): EWMA of recall queries per device, split by the representation each question type uses (DEV question-type mix).
- lambda_i^esc: EWMA of escalations per device (used for calendar arrivals and controller load, not for history value).
- Conditional recall rate during episodes: only if DEV data supports it.

### 6.5 Residency verification from engine telemetry (D44, D47)

- Sources: the engine's per-interval cache telemetry, separating LOCAL (GPU) prefix-cache hits from EXTERNAL (host-connector) hits, plus offload-load activity, preemption and eviction counters where the engine exposes them, and each request's reported cached tokens. Per-request attribution uses counter changes around that request.
- Belief: each (i, rep) holds a distribution over {GPU, HOST, STORED}. Unambiguous telemetry sets it; ambiguous telemetry keeps a CONSERVATIVE belief (probability mass toward the colder tier) rather than assuming the warmest.
- REQUESTED vs CONFIRMED transitions: a promotion or demotion is recorded as requested when issued and confirmed only when telemetry shows the expected state (for example, a later request's hits come from the local cache). State value and planning use confirmed belief; unconfirmed promotions receive no future-value credit.
- Divergence between desired and believed tiers is reported.

---

## 7. Decision procedures

### 7.0 Core and conditional mechanisms (D38, D50)

| mechanism | class | enabling condition |
|---|---|---|
| admission of escalations (7.1) | core | always on |
| coordinator with counterfactual release under pi_0 (7.2) | core | always on |
| historical jobs: continuation value and feasibility (7.3) | core | always on |
| adaptive execution granularity (7.4) | core | always on; must pass T3 |
| readiness management and tier assignment (6) | core | always on |
| outages (7.5) | core | always on |
| deficit counters (7.6) | core | always on |
| device controller (7.7) | core input | the source of escalations |
| escalation price (7.7) | conditional | trigger threshold calibrated on DEV against estimated benefit; evaluated separately from admission |
| phase assignment (7.8) | conditional | predicted clustering gain exceeds capture-time shift cost; evaluated against unphased |
| merging (7.9) | conditional | M3 shows merged-call utility exceeds the device's at the delays involved |
| summaries (7.10) | conditional | DEV quality competitive for some question types; refresh cost measured |
| predictive upload (7.11) | conditional | improves time-to-ready over on-demand upload under measured links |

### 7.1 Admission (core)

On escalation r: build r's best plan (for RC, best option over {device, SUMMARY if enabled, RICH} given believed tiers, staleness and feasibility, 7.3); admit if DeltaJ_H(admit) > 0 against "decline".

### 7.2 Coordinator (core) (D23, D25, D46)

On each event (arrival, completion, off-schedule call, telemetry update, state re-solve, link change):
1. Update calendar, estimates, believed tiers, Z counters, job states and feasibility classes.
2. For each pending item p, compute DeltaJ_H(release p now) against "defer p to its next candidate slot", both under pi_0, given work in flight.
3. Release the item with the highest positive DeltaJ_H; re-score given the new in-flight set; repeat until none is positive. One release at a time, so nothing bunches.
4. No forced release. Approaching deadlines enter through continuation value and deficits; feasibility rules (7.3) bound waiting.
5. Commit only the immediate releases; re-plan at the next event. H is about 0.5-1 s and swept.

### 7.3 Historical jobs: feasibility and bounded waiting (D45, D46)

At admission and at every event, each RC job r is classified using its continuation schedule:
- FEASIBLE: Phat_r(finish by D_r) under pi_0 is above a threshold.
- FEASIBLE ONLY WITH PRIORITY: below threshold under pi_0, above it if r's remaining pieces are given priority over non-urgent background work (never over episodic work whose own loss would exceed r's value).
- INFEASIBLE: below threshold even with priority.

Rules:
- Feasible jobs: no special treatment; as slack shrinks, ContValue_r and the device's deficit raise DeltaJ_H of r's pieces, so a feasible job wins before it becomes infeasible. A per-job bounded-waiting check verifies this: if r is feasible with priority but would become infeasible within the next scheduling interval under the current ranking, r is promoted to the priority class.
- Feasible only with priority: r's pieces are compared with competing work by their DeltaJ_H including the priority continuation; episodic work is never sacrificed when its loss exceeds r's expected value.
- Infeasible: stop spending GPU time on r's answer (the device's answer is used); continue only pieces whose StateValue for future questions alone justifies them.

### 7.4 Adaptive execution granularity (core; T3) (D17)

Large work is split into prefix-chained pieces of whole frames reusing the cached prefix. Piece size is chosen per job by the rollout among candidate sizes (measured sizes plus whole-job), maximizing DeltaJ_H of the job's plan including its continuation value. The closed form k* = tau (A (beta_e - 1) / c)^(1 / beta_e) may seed the candidate set; it is not a foundational claim. Between pieces, remaining pieces are released only while DeltaJ_H stays positive (D18).

### 7.5 Outages (core) (D32)

Unreachable device: runs on its own model; its pending cloud work is paused; StateValue is discounted by P(reachable within H_s); its jobs' continuation values use that probability; on reconnect, backlog is caught up through the coordinator.

### 7.6 Deficit counters (core)

Updated per eligible opportunity (3.3); enter every DeltaJ_H.

### 7.7 Device controller (core input) and escalation price (conditional) (D20, D22, D34)

On the device, per active task, never using absolute confidence. Self-normalized signals over the device's own recent window W_c: relative score z_t = (score_t - median) / IQR, rise score_t - score_{t - delta}, instability over n_c frames. Escalate when

    max(z_t, rise_t, instability_t) > theta_k + beta * pi(t)

- theta_k: DEV-fitted base threshold on self-normalized signals.
- pi(t) (conditional): one number broadcast by the cloud saying how expensive help is right now, pi = mu x (GPU-seconds of a typical first call), in utility units; enabled only if beta is calibrated on DEV so a higher price suppresses the lowest-benefit escalations first; evaluated separately. Because SLOs count all eligible opportunities, suppression cannot improve measured attainment by hiding difficult situations.
- Episode end: signal below theta_k for K_c frames or E_k calls; the cloud may end an episode when DeltaJ_H of continuing is negative for K_e consecutive calls.

### 7.8 Phase assignment (conditional) (D21)

Follow-up calls of an admitted episode get a phase that clusters them with other episodes of the same cadence. The device sends its latest frame when the call fires; nothing is held at the cloud. The one-time capture-time shift is charged in the rollout. Enabled per cadence class when clustering gain exceeds that cost; evaluated against unphased episodes. Active episodes are not re-phased. P10 out of scope.

### 7.9 Holding and merging episode calls (hold: core; merge: conditional) (D24)

A due follow-up call is dispatched or held by DeltaJ_H against "hold to next slot". With merging enabled, a held call still unsent at the next call's due time is sent together with it (up to W_k frames); the earlier opportunity is a device-only outcome; the merged answer serves the later opportunity with utility from M3.

### 7.10 Summaries (conditional) (D27, D49)

Generated by the cloud 32B when the GPU is idle, scored by DeltaJ_H as a state action. Enabled only for question types where DEV quality is competitive and refresh cost is measured (StudyF2 inconclusive). Until then the representation choice is not exercised and the evaluation says so.

### 7.11 Predictive batched upload (conditional) (D28, D32)

Batch upload requested when P_i^rep(need within H_up) >= theta_up for some representation, or the link is expected to degrade with unsent frames. Enabled when it improves time-to-ready over on-demand upload. Continuous and on-demand upload are comparison points.

---

## 8. Main loop (pseudocode)

```
on event e at time t:
    update links, reachability, duration estimates, demand rates (rc per rep, esc)
    update believed tiers from engine telemetry; confirm or reject requested transitions
    for each eligible opportunity whose outcome is known: update Z(i,k)
    if e is escalation r:
        plan = best_plan(r)                                  # includes feasibility for RC
        if DeltaJ_H(admit vs decline; pi_0) > 0: admit, add work; if SH and phasing enabled: assign phase
        else: decline
    for each RC job: recompute continuation schedule, Phat_r, feasibility class (7.3)
    if state inputs changed or timer: greedy tier assignment; add state actions
    if enabled and due: add upload / summary candidates

    calendar = build_calendar(t, t + H)
    choose piece sizes for large jobs by rollout over candidate sizes
    loop:
        for p in pending: DeltaJ_H(release p now vs defer p; pi_0), terminal value per 5.3-5.4
        p* = argmax; if DeltaJ_H(p*) <= 0: break
        release p*; add to in flight
    for each due episode call not released: hold; merge if enabled; else device outcome
    update mu; if price enabled: broadcast pi
```

---

## 9. Parameters

| parameter | meaning | default / how set |
|---|---|---|
| (q_k, L_k, p_k) | per-task SLO | application parameters, swept |
| omega_k | class weights | DEV-calibrated |
| H | planning horizon | 0.5-1 s, swept |
| pi_0 | continuation policy | EDF over pending and calendar |
| continuation resolution | coarse extension of the rollout to job deadlines | set by M4 |
| feasibility threshold | Phat_r cut-off for feasible / priority / infeasible | DEV, swept |
| H_s | state horizon | seconds, swept |
| rollout mode | expected-value or sampled scenarios | T0, M4 |
| candidate piece sizes | 7.4 | measured sizes plus whole-job |
| T_k, E_k, W_k | episode cadence, maximum length, temporal window | per task |
| theta_k, beta, W_c, delta, n_c, K_c, K_e | controller and episode end | DEV |
| H_up, theta_up | upload trigger | DEV |
| N_sum | summary refresh trigger | DEV |
| belief conservatism | mass assigned to colder tier when telemetry is ambiguous | fixed, reported |

---

## 10. Evidence to date and remaining inputs

All entries are subject to the pending audit of results from StudyE6 onward (P4).

### 10.1 Committed evidence relevant to the policy

| study | what it establishes for the policy | limits |
|---|---|---|
| E9c | 32B over 4B on Nexar challenge mAP: +0.114 [0.061, 0.169]; delivered cloud vs device +0.090 (25 % load) and +0.073 (75 %) | always-on-stream delivery model |
| E9d | value-vs-delay curves; queueing a cloud call beats suspending to the device for windows up to about 4 s; blocking loss within noise below about 1 s and convex above | always-on streams; use the curve, not a threshold |
| E10b-E10f | a long prefill holds episodic requests until its first token; no engine setting tested removes it | vLLM 0.31.0 |
| SLICE1 Part A | a cold append-only history can be rebuilt as prefix-chained requests with near-monolithic total engine work at 1-2k-token pieces, with the longest engine unit a fraction of a second | 11k and 28k histories |
| SLICE1 Part B | slicing plus gap-hold (P4) raised episodic capacity at C1a from below 10 % to 30 % with 94.4 % of recalls within 10 s; holding alone and slicing alone did not | known future schedule |
| SLICE1 Part C | independently released held work bunches and does not restore capacity; 1,024-token slices with hold reached 25 % at C1b | known schedule |
| SLICE1 Part D | one coordinated lane removed bunching (90 to 0 units) but C4a capacity stayed at 10 % (2,048-token slice remained binding); warm-only capacity rose to 40 % only when escalations were allowed to slow; the known-schedule benefit of 2,048-token policies disappears under the assumed jitter | jitter assumed (P6) |
| MAP1 | the live-to-mAP bridge is exact and validated; across SLICE1 B/C cells a 9x spread in p99 delivery moved challenge mAP by at most 0.0087, all 27 paired intervals including zero | per-cell interval width about 0.128 (underpowered); always-on cells; p99 touches about 1 % of calls |
| SIM1d | the simulator's engine model fails out-of-sample on slice-versus-episodic interactions; an overlap cost of about 0.05 s per concurrent warm request exists in both KV modes; no sub-linear batching in the step model | motivates M1 and T0 |
| E10c metrics | the engine exposes separate local and external prefix-cache hit counters | basis for 6.5 telemetry |

Implications: a single coordinator is necessary but not sufficient; piece size and timing still need evidence; tail latency alone is not task value; the largest measured application-value lever is whether an opportunity gets the cloud at all (admission and capacity).

### 10.2 Remaining inputs

| input | used in | source |
|---|---|---|
| step-time and admission model | 5.1, 5.4, 7.4 | M1 (H100) |
| episode statistics under the controller | workload, 7.7-7.9 | M2 (offline) |
| utility vs frames per call | 7.9 | M3 |
| coordinator, rollout and continuation overhead | 5.5, feasibility | M4 |
| per-request cache-tier attribution from telemetry | 6.5 | to be validated alongside M1 |
| u_SH tables, acc tables, omega_k, question-type-to-representation map | 3-4, 6 | DEV |
| durations: answer, reload, rebuild per token, catch-up per frame, summary | 4.3, 6.2 | committed profiles + running estimates |
| link model, outage durations | 4, 7.5, 7.11 | trace-driven; measured trace when available (P6) |

---

## 11. Approval tests

| test | what to establish | why decisive |
|---|---|---|
| T0 cost-model fidelity | the rollout's (and fallback's) predicted delay imposed on others, and its predicted job completion times, match live measurements within a stated tolerance | every decision rests on it |
| T1 objective validity | online utility and predicted SLO success track measured task utility (adequately powered) and measured attainment | optimizing the right quantity (P7) |
| T2 coordinated release | the scheduler beats its own base policy (EDF), utility-per-cost, independent release, and the decomposed best-of-breed controller on the live H100 | basic algorithmic benefit |
| T3 adaptive granularity | rollout-chosen piece size beats the best fixed size across load and jitter | adaptive sizing matters |
| T4 joint readiness management | adding readiness allocation beats the strongest independent cache manager plus a good admission scheduler | the claimed coupling; if matched, it is not claimed |

Also reported: predicted vs measured attainment; greedy vs offline tier assignment; desired vs believed residency divergence; requested vs confirmed transitions; feasibility classification accuracy (jobs classified feasible that missed, and vice versa).

---

## 12. Evaluation implications

Two tracks:
- Application value: per-task utility metrics over all eligible opportunities (Nexar challenge mAP and streaming AP for SH; deadline-qualified accuracy for RC; SS when available), with a design powered for the effect sizes targeted (pooled clips across cells and seeds; stated minimum detectable effect).
- Systems capacity: CONFIDENCE-AWARE capacity (D8 revised): the largest fleet size at which every device's SLO is met at a stated confidence level, using paired seeds and a minimum number of eligible opportunities per device; plus the distribution of per-device SLO margins (attainment minus target, with intervals); tail latency, cold-reconstruction frequency, utilization, state freshness. Task utility at a fixed fleet size remains the smoother second axis.

Workload: aperiodic escalations from the device controller opening SH episodes (from committed device score traces, M2); RC questions at real offsets with per-device arrival processes; SS when available; trace-driven links with outages; always-on streams only as a stress case.

Baselines: EDF (the base policy); utility-per-cost admission; independently released background work; the decomposed best-of-breed controller (B9 with audited fixes); the strongest independent cache manager plus a good admission scheduler (T4); absolute-confidence trigger; escalate-everything; always-on periodic streams; tuned engine; device-only.

Ablations (one mechanism off): counterfactual scoring (FCFS; closed-form fallback); continuation value (none; tokens-processed proxy); feasibility rules; single coordinator; adaptive granularity (monolithic; each fixed size); deficit counters (fixed weights; pure utility; pure constraint); tier assignment (LRU; offline optimum as upper bound); telemetry-verified residency vs assumed residency; separate vs merged demand rates; every conditional mechanism on vs off; horizon sweep; known schedule vs cadence-only vs measured jitter.

---

## 13. Limitations and pinned items

- Per-device SLOs only (P1); single-shot workload pending (P2); one question type per device to start (P9); external-clock alignment out of scope (P10); controller context signals pinned (P11); host-tier mode decision pinned (P12); GPU price beyond backlog pricing pinned (P8); stronger VLM pinned (P3); jitter assumed until measured (P6).
- Online success is predicted; true attainment known only offline.
- SH utility is a surrogate for a pooled metric (T1).
- Residency is influenced, not commanded; belief can be wrong and is reported.
- No formal guarantee for the deficit counters or for rollout improvement under an approximate simulator.
- The representation choice beyond execution readiness is exercised only if SUMMARY passes its enabling condition.
- The manuscript's system model is to be reconciled later, including the scope restriction that RECENT is handled on the device.

---

## 14. Traceability

| section | decisions |
|---|---|
| header, 7.0 | D36, D38, D50 |
| 1 | D1, D19, D29, D31, D33, D37, D39 |
| 2 | D12, D14, D26, D30, D44, D47, D48 |
| 3 | D2-D5, D37, D40-D43, D45, D46 |
| 4 | D5, D24, D30, D31, D39 |
| 5 | D15, D16, D18, D43, D45, D46 |
| 6 | D9, D10, D12-D14, D26, D44, D47, D48, D49 |
| 7 | D17, D20-D25, D27, D28, D32, D34, D38, D45, D46 |
| 9-12 | D6, D7, D8, T0-T4, M1-M4, H1, P7 |
