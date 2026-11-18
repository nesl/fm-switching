# Scheduling policy: full specification v4

Status: v4, 2026-11-16. SUPERSEDES v3 (`claude/policy_spec.md`) and the v3.1 addendum (`claude/policy_spec_v3_1_addendum.md`); both are kept for history only. Decision record: `claude/policy_design_log.md` (D1-D59, approval tests T0-T4 and T0b, measurements M1-M6, hypotheses H1-H2, open question Q11, pinned items P1-P13). Where this document and the log disagree, the log is the record and this document must be corrected.

Scope: the entire policy, excluding only pinned items (D36). Nothing is cut. Mechanisms whose benefit is not yet established are fully specified with an explicit ENABLING CONDITION (D38) and are evaluated on and off.

Claimed contribution (D50): a non-learned, counterfactual coordinator for a shared cloud accelerator serving many devices, which jointly decides (1) admission of escalated inference, (2) release timing and execution granularity of cloud work, including multi-second historical reconstruction, and (3) management of execution readiness of per-device history across GPU, host and cold tiers under given memory capacities, according to each action's effect on application utility and per-device SLOs across the whole fleet. Conditional mechanisms are specified and evaluated but are not part of the central claim until their individual contributions are measured.

All tables, calibrations and estimates used by the policy are fitted on DEV data only (D6). Every committed result cited here is subject to the pending audit of results from StudyE6 onward (P4).

Marking used below: PROVISIONAL = depends on a measurement not yet completed (named); PLACEHOLDER = implemented with a stand-in value that must be replaced before evaluation; OPEN = undecided.

## Standing problem-setting rules (D56; apply everywhere in this document)

- Memory capacities (GPU KV pool C_gpu, host tier C_host) are INPUTS to the problem. The policy must work under any values. The H100's large host tier is platform specific and is never used to argue that a decision is trivial.
- Evidence that reaches the cloud is NEVER discarded. Every device history is in one of three readiness tiers: GPU-warm, host-warm, or COLD (raw frames on disk, rebuilt by prefill). "Drop" means demote to cold.
- Where each history is kept (GPU / host / cold) is a core decision under whatever capacities apply.

## Changes from v3.1

| # | change | sections | decisions |
|---|---|---|---|
| 1 | Problem statement written explicitly as SLO-constrained total-utility maximization (formulation (c)), so the formulation and the mechanism match | 3.1 | D2-D5, D37 |
| 2 | Memory capacities as inputs; three tiers with cold below host; evidence never discarded | 1, 2, 7 | D56 |
| 3 | Host tier modelled as written through from GPU with its own eviction rule; effective host capacity beyond the GPU pool; readiness steered through execution order and touches rather than placement | 1.3, 7.2-7.4 | D56, PROVISIONAL on M6 |
| 4 | Per-tier score calibration before any mixed-tier comparison, upgrade or gain estimate | 3.2, 4.1 | D57 |
| 5 | Unified escalation basis Ghat; three flows; complete-query default with question-first exception; delivered delay per path | 4 | D51-D54 |
| 6 | Partial-prefix survival: expected remaining work under deferral; rollout tracks the KV pool and host tier; verify on resume; piece sizing includes deferral risk | 6, 8.4 | D55 |
| 7 | Backlog term SUBTRACTED in terminal value (sign corrected by StudyPOL2, ambiguity A19); mu estimation status stated | 3.5, 6.3 | D43 |
| 8 | Measured inputs from StudyENG1 (step model, front end, admission stall, serial blocking) and StudyENG1b (prefix survival) | 6, 11 | M1, M5 |
| 9 | T0 outcome recorded; noise-aware T0b pre-registered | 12 | T0, T0b |
| 10 | Trigger evaluation against load, streaming AP primary | 8.7, 13 | D58 |
| 11 | Task-type names fixed: SH, SS, RC (the manuscript's "LH" is RC) | all | |

---

## 1. Setting and assumptions

### 1.1 System

- A fleet of devices i in I. Each runs its own small VLM (currently Qwen3-VL-4B) continuously on its own camera and keeps its own history locally. The device always answers.
- One shared cloud replica runs a large VLM (currently Qwen3-VL-32B) in an engine with continuous batching and chunked prefill (vLLM 0.31.0). GPU time, GPU KV memory (C_gpu) and host KV memory (C_host) are finite, shared, and inputs (D56). Cold storage of raw frames is unbounded for the policy's purposes.
- Each device reaches the cloud over its own link with time-varying bandwidth, round-trip time and outages. Links do not interfere with each other. The network's only cost is latency (D33). No device data or energy budget.
- KV cannot move between device and cloud (different models).

### 1.2 Task types and eligible opportunities (D19, D37)

| task type k | example | eligible opportunity (SLO denominator) | what an admitted escalation starts | value decay |
|---|---|---|---|---|
| SH, short horizon | cut-in, collision anticipation | every decision instant on the task's evaluation cadence while active, escalated or not | an EPISODE of cloud calls at cadence T_k until resolved or E_k calls | gradual with delivered delay |
| SS, single shot | where are my keys | every query | one call | cliff at L_SS |
| RC, historical recall (manuscript: long-horizon, LH) | question about events minutes ago | every question | one job needing the device's history on the cloud, possibly multi-second reconstruction | cliff at the deadline |

The device answers every opportunity locally and immediately; a cloud answer, when it arrives in time and improves the calibrated utility, upgrades it.

### 1.3 Three flows (A0)

| flow | what moves | mechanism |
|---|---|---|
| History sync (recall evidence) | the device's past frames into the cloud's stored (cold) history | predictor-driven BATCHED upload (8.11, conditional); not a continuous trickle |
| Monitoring trigger (SH) | the state of a stream, to decide whether to open an episode | device-side Ghat filter and/or cloud-initiated low-rate sampling; family OPEN (Q11) |
| Query (SS, RC) | the question plus whatever the cloud lacks | sent complete by default (4.3) |

### 1.4 Assumptions

- A2. Answer value falls with delivered delay (gradual for SH, cliff for SS and RC).
- A3. Making a history usable on the cloud costs GPU work that depends on its tier: none (GPU-warm), a reload (host-warm), or a rebuild by prefill (cold).
- A4. The engine does not preempt a submitted request, and a long prefill blocks requests arriving behind it almost completely (StudyENG1: 97-100 % of remaining work). How strongly one request delays others is given by the measured step model (M1).
- A5. KV is not portable between device and cloud.
- A6. Payload per call is fixed per task (D31).
- A7. Devices accept two small control messages (episode phase, escalation price), both for conditional mechanisms.
- A8. Residency cannot be commanded, on GPU or host (D44). Blocks computed on the GPU are written through to the host tier as they are computed (StudyENG1b, P_host 0.999 with a roomy host). Both tiers evict by their own rules from the same request stream. PROVISIONAL (M6, StudyENG1c Part A): from the vLLM 0.31.0 source, both are LRU, a host copy's recency is refreshed on store and when a request using it finishes, a request served from GPU still refreshes the host copies of its prefix, a host load refreshes only the chunks it loaded, misses refresh nothing, and within one history the tail is evicted first. Under these rules the host tier adds capacity only beyond the GPU pool: C_host_eff = max(0, C_host - C_gpu). The policy uses the rule StudyENG1c measures, not this prediction.
- NOT assumed: that the cloud answer is better. Cloud benefit is estimated per request on a calibrated scale and may be zero or negative (D39, D57).
- Scope restriction: RECENT evidence is handled on the device; cloud-side history concerns RICH and, conditionally, SUMMARY.

---

## 2. Entities and state

### 2.1 Per device i

- Link estimate: bandwidth b_i (constant ASSUMPTION until P6), RTT_i, reachable flag, short-term trend.
- Controller state per active SH task (8.7).
- Active episodes: task type, cadence T_k, phase (if enabled), calls issued, start time.
- Cloud-side history per representation rep in {RICH, SUMMARY (if enabled)}:
  - desired tier (from 7.4);
  - BELIEVED tier distribution over {GPU, HOST, COLD} (7.6);
  - staleness s(i, rep); unsent frames; size m(i, rep) in tokens and bytes.
- Demand estimates (D48), EWMA with DEV priors: lambda_i^rc(rep) for recall queries using rep; lambda_i^esc for escalations. Conditional recall rate not used (not computable from DEV, StudyPROF1).
- SLO deficit counters Z(i, k).

### 2.2 Cloud

- Engine state: requests in flight; per-step occupancy; cache telemetry (7.6).
- KV POOL model (D55): GPU occupancy, referenced vs unreferenced cached blocks, the engine's free-block order (recency).
- HOST TIER model (D56): occupancy, per-history host-resident chunks, recency under the eviction rule measured by M6.
- Pending set P of requests, jobs and pieces not yet released.
- Historical jobs: for each admitted RC job r, built prefix (tokens, believed tier of each part), remaining pieces, deadline D_r, feasibility class (8.3), continuation plan.
- Calendar C(t, t + H) of known and expected arrivals over the horizon H (D25).
- Per-tier calibration maps (D57).
- Terminal prices: mu (GPU backlog), nu_tier (memory, from 7.4).

---

## 3. Problem, objective and the action score

### 3.1 Problem statement (D2, D3, D4, D5, D37)

Choose admission, release timing and granularity, and readiness actions online to

    maximize   E[ sum over all eligible opportunities o of omega_k(o) * u_k(o)(answer actually used at o) ]

    subject to, for every device i and task type k it uses:
        fraction of i's eligible type-k opportunities whose used answer has quality >= q_k within latency L_k   >=   p_k

and to the engine's compute, C_gpu, C_host, link and timing constraints. The future (observations, arrivals, ground truth, correctness of unexecuted calls) is unknown. The constraints are handled through deficit counters (3.3); pure utility and pure constraint versions are ablations. No formal guarantee is claimed (D41).

### 3.2 Bounded, calibrated task utility (D40, D57)

Each task type k has a bounded utility u_k(answer, delivered delay) in [0, 1] from DEV-calibrated tables (section 5). Before ANY comparison between tiers (gain estimates, upgrades, mixed-tier ranking), each model's raw score is mapped by a DEV-fitted (on Nexar, cross-fitted) monotone calibration to a common probability scale (D57). Reason: StudyCTRL1b found the 32B's raw log P(Yes) about 5 log units below the 4B's, which made a perfect oracle score below device-only.

A cloud action's gain on opportunity r:

    g_r(x) = omega_k * ( u_k(cloud answer under x) - u_k(device answer) )

with omega_k from DEV (omega_SH = 1, omega_RC = 0.4246 provisional, StudyPROF1). g_r may be zero or negative.

### 3.3 Deficit counters: virtual-queue heuristic (D41)

Per device and task type, per eligible opportunity once its predicted outcome is known:

    Z(i, k) <- max( Z(i, k) + p_k - Shat_r , 0 )

### 3.4 Predicted vs measured success (D42)

Online: Shat_r from calibrated DEV tables. Offline: S_r measured against ground truth over all eligible opportunities. The gap is reported.

### 3.5 Action score: counterfactual marginal value under a common continuation policy (D43, D45, D46)

pi_0 is EDF over the pending set and calendar (deadline-ordered release, one unit at a time, same engine model), with episodic calls at their due times.

    Jhat_H(S_t, a; pi_0) = Uhat_H + sum over (i, k) of Z(i, k) * Phat_success_H(i, k) + TerminalValue(S_{t+H})

    TerminalValue(S_{t+H}) = sum over unfinished RC jobs r of ContValue_r(S_{t+H})          (6.4)
                           + sum over (i, rep) of StateValue(i, rep, S_{t+H})               (7.1, future questions only)
                           - mu * (GPU backlog at t + H not already in any job's continuation value)

    DeltaJ_H(a) = Jhat_H(S_t, a; pi_0) - Jhat_H(S_t, a_ref; pi_0)

The backlog term is SUBTRACTED: leftover work is a cost to the future (StudyPOL2, A19). mu is in utility units per GPU-second. mu estimation is OPEN (StudyPOL3 to state the options); until set, mu = 0 is a PLACEHOLDER, which silences the backlog channel and part of the deferral logic, so no evaluation may run with it.

Reference actions: admit vs decline; release a piece vs defer it to its next candidate slot; state action vs no change; dispatch an episode call vs hold to the next slot.

The scheduler is a ROLLOUT over pi_0: it changes the immediate decision only when the simulated future under pi_0 says so. With an approximate simulator no improvement guarantee holds; T0 measures the approximation. EDF is the first baseline (T2).

---

## 4. Escalation basis and query paths (D51-D54, D57)

### 4.1 Unified escalation basis (D51)

Every request of every type is escalated on one quantity, its estimated cloud gain on the calibrated scale:

    Ghat(r) = E[ u_cloud(r) - u_device(r) | observable features o_r ]

from DEV-fitted lookup tables (non-learned). No request type is routed to the cloud by rule. Determinants:

| insight | observable feature | effect on Ghat |
|---|---|---|
| the cloud holds more evidence | does the request reference time beyond the device's window | missing local evidence -> large gain |
| the cloud is a better model | task-type posterior P(type given o_r) | base gain per type (DEV table) |
| the device may be wrong | self-normalized uncertainty (instability, rise vs own history) | higher uncertainty -> more gain |
| timeliness | deadline vs predicted delivered delay on this link for the path actually used (4.3) | late answer -> gain to zero |

When the type is uncertain:

    Ghat(r) = sum over types tau of P(tau | o_r) * Ghat(r | tau, o_r)

P(type | o_r) comes from simple keyword and temporal-reference rules; the device model labelling the question is a fallback only if the rules prove too coarse on DEV (D53). Cloud admission uses the same Ghat inside DeltaJ_H, so device-side triggering and cloud admission share one formula. Escalation (worth asking) and admission (worth serving now, given everyone else) remain separate decisions.

### 4.2 Predictability test (A5)

The predictability-ceiling arm of the trigger studies measures how well Ghat can be estimated from observable features (a cross-fitted flexible model as the ceiling); a simple rule from its strongest features is the deployable version.

### 4.3 Query paths (D52 revised, D54)

- DEFAULT, COMPLETE QUERY: the device sends the whole query at once (question; for SS the current frame(s); for RC any history frames the cloud lacks, usually none because of batched sync). The cloud runs admission on arrival; a declined query is discarded and the device's answer stands. No extra round trip.
- EXCEPTION, QUESTION FIRST: only when an RC query's unsent history is large AND the uplink is contended by the device's own higher-value traffic. The cloud decides, then pulls the missing frames only if it admits.
- Delivered delay for the path actually used:

      complete query:  d = t_up(question + payload) + t_frontend + t_queue + t_compute + t_down
      question first:  d = t_up(question) + t_decide + RTT/2 + t_up(missing frames) + t_frontend + t_queue + t_compute + t_down

  t_decide is the measured coordinator decision latency (M4). t_frontend is the engine front end's serialized per-request preprocessing (StudyENG1: about 29.6 ms + 20.2 ms per MB when idle; requests are processed one after another).

---

## 5. Utility models per task type

Delivered delay (D30): t_up = payload_bytes / b_i + RTT_i / 2, t_down = RTT_i / 2, plus the path terms of 4.3.

### 5.1 SH

u_SH(cloud, d, m) from DEV curves on the calibrated scale (m frames; m > 1 only for a merged call, 8.9); u_SH(device). Per-call utility is a surrogate for Nexar challenge mAP; validation is T1 (P7). A call not answered in time is a device-only outcome.

### 5.2 SS

u_SS(cloud, d) = acc_SS^cloud if d <= L_SS, else the device's answer is used.

### 5.3 RC

    T_ready = t_upload(unsent, if needed) + t_restore(rep, believed tier) + t_catchup(rep, s) + t_answer(rep)
    u_RC = acc(qtype, rep) if T_ready + t_queue + t_down <= D_RC, else the device's answer is used

t_restore by tier (StudyENG1, 11,184-token history, time to first token): GPU 0.10 s, host 0.17 s, cold 2.74 s. Expected utility uses the predicted T_ready distribution and the believed-tier distribution (7.6).

---

## 6. Counterfactual accounting (D15, D16, D18, D43, D45, D46, D55, D56)

### 6.1 Horizon rollout

Jhat_H is computed by rolling the engine forward over H (about 0.5-1 s, swept):
- the candidate (or reference) action at t, then pi_0 for every later decision;
- requests in flight, calendar arrivals, expected unknown arrivals at estimated rates;
- engine model (M1, StudyENG1): step time = intercept 28.7 ms + about 0.074 ms per new token (up to 512) + 8.6 ms per image + 1.95 ms per (new tokens x cached context tokens)/1e6 + further fitted terms (results/cost/study_eng1/eng1_step_model.json; R^2 0.985); serial admission behind a running long prefill; front-end serialization (4.3); per-image admission stall (50 / 66 / 158 ms for 1 / 23 / 91 images); sub-linear batching;
- KV POOL and HOST TIER bookkeeping (2.2): allocations by every simulated request, release of references at completion, eviction order on GPU, write-through to host, host eviction under the M6 rule;
- outputs: predicted delivery times of affected opportunities; the state of every RC job at t + H, including which parts of each built prefix are on GPU, host or lost; believed tiers at t + H.

### 6.2 Fidelity requirement (T0, T0b)

Decisions rely on the rollout only to the extent T0 supports. Current status: section 12.

### 6.3 Terminal value: one rule

Each item left at the horizon is valued exactly once: unfinished RC jobs by continuation value (6.4); per-device readiness by state value for FUTURE questions (7.1), excluding a question whose job is valued in 6.4; residual GPU backlog not covered by any job's continuation value, subtracted at mu per GPU-second.

### 6.4 Job-level continuation value with prefix-loss risk (D45, D55)

For an unfinished RC job r at the horizon end:

    ContValue_r(S) = omega_RC * ( acc(qtype, rep) - acc^device(qtype) ) * Phat_r(finish by D_r | E[w_r], S, pi_0)
                     + Z(i(r), RC) * dPhat_success attributable to finishing r

The remaining work is an EXPECTATION that includes the risk of losing the built prefix while the job waits:

    E[w_r | defer for gap g] = w_left + P_loss(g) * [ P_host * w_reload(prefix) + (1 - P_host) * w_rebuild(prefix) ]

- w_left: unreleased pieces.
- P_loss(g): probability the unreferenced built prefix is evicted from GPU before the next piece runs. Read from the rollout's KV-pool bookkeeping (mechanistic), not set by hand. StudyENG1b: survival depends on KV allocated before the resume is scheduled, not on time: full below 1.0x the free pool, partial and tail-first between 1.0x and 1.25x, total above 1.25x; warm re-references shrink the effective free pool. Where the rollout does not reach the resume time, this measured step function is the fallback.
- P_host: probability that evicted blocks are recoverable from host. NOT a constant (D56): about 0.999 when the host tier has room (StudyENG1b); a function of host occupancy and the host eviction rule otherwise (PROVISIONAL, M6).
- w_reload, w_rebuild from the step model; StudyENG1b: resume +0.12 s after a host reload versus +2.15 s after a rebuild.
- The larger cost of deferral is usually QUEUEING: a resumed piece that arrives while competing work is still running waits behind it (StudyENG1b: 6-10 s). This is paid by the job and is captured by the rollout and the continuation schedule, not by P_loss.

Phat_r comes from a FEASIBLE CONTINUATION SCHEDULE: pi_0's planned release slots for r's remaining pieces, extended to D_r at reduced resolution with the same engine model. It is not estimated from tokens processed. Releasing a piece of r earns the increase in ContValue_r it causes.

### 6.5 Fallback approximation

When a full rollout is too expensive (M4), the closed-form channel approximation may be used (direct delay of overlapping requests from the step model times a load factor), with the backlog term applied only outside channel 1 and continuation value retained. The fallback must pass T0 itself.

---

## 7. Readiness management (D9, D12, D14, D26, D44, D47, D49, D55, D56)

The representation-related dimension currently supported by evidence is EXECUTION READINESS (GPU / HOST / COLD). Choosing between RICH and SUMMARY is exercised only if SUMMARY passes its enabling condition (8.10).

### 7.1 State value (future questions only)

    P_i^rep(need within H_s) = 1 - exp( - lambda_i^rc(rep) * H_s )

    StateValue(i, rep, S) = P_i^rep(need within H_s) * [ expected u_RC gain in this tier - expected u_RC gain in the next colder tier, or the device ]

Only recall queries that would use rep enter (D48). A partially rebuilt history contributes state value for future questions; the question whose job is in progress is valued only through 6.4. In-progress built prefixes are memory items whose value is their continuation value at risk plus their state value, each counted once (D55).

### 7.2 Capacities and what the policy can influence (D56)

- Capacities C_gpu and C_host are inputs. Working space for in-flight requests is reserved from C_gpu.
- Because GPU blocks are written through to host and both tiers evict from the same request stream, host residency is largely determined by recency of use, and the host tier holds histories beyond the GPU only within C_host_eff (PROVISIONAL, A8, M6).
- Consequently readiness is STEERED, not placed: through which requests run and when (execution order), how jobs are sized, which KV-heavy work is released, and, if M6 shows it works, small TOUCH requests that refresh a history's host recency. The policy never assumes a pin, on GPU or host.
- Cold is always available; demotion to cold loses no evidence, only readiness.

### 7.3 State actions

| action | effect | how enacted | status |
|---|---|---|---|
| PROMOTE (reload) | HOST -> GPU | a request reusing the prefix; confirmed by telemetry | core |
| PROMOTE (rebuild) | COLD -> GPU (and host by write-through) | prefix-chained pieces (8.4); confirmed by telemetry | core |
| CATCH UP | materialize newly synced frames | an append request | core |
| TOUCH | refresh a history's host (and GPU) recency so it is evicted later | a minimal request reusing the prefix | PROVISIONAL: only if M6 shows a touch keeps a history host-resident, separately for GPU-resident and host-only histories |
| LET AGE | allow a history to fall to a colder tier | no action; eviction is engine-driven | core |
| REFRESH SUMMARY | conditional (8.10) | a generation request | conditional |
| REQUEST UPLOAD | conditional (8.11) | device-side | conditional |

Each is scored by DeltaJ_H against "no change" and taken only if positive. Every state action consumes GPU work and shifts recency for other histories; both effects are in the rollout. Future-value credit only for CONFIRMED transitions (7.6).

### 7.4 Tier assignment: desired readiness

Greedy ranking of histories by StateValue gain per unit of the scarce tier, within C_gpu (after working space) and C_host_eff, gives the DESIRED tier per history. An approximation of a multiple-choice knapsack; evaluation compares it against a stronger offline allocation on recorded traces. nu_tier = gain per unit of the last history admitted to a full tier. The desired assignment is pursued only through state actions with DeltaJ_H > 0 (7.3); the gap between desired and believed tiers is reported. Re-solved on events and every few seconds.

### 7.5 Demand predictors (D48)

lambda_i^rc(rep): EWMA of recall queries per device, split by the representation each question type uses. lambda_i^esc: EWMA of escalations (calendar arrivals and controller load only, not history value).

### 7.6 Residency belief and verification (D44, D47, D55)

- Sources: per-interval cache telemetry separating LOCAL (GPU) from EXTERNAL (host connector) prefix hits, offload store and load activity, and each request's cached tokens; attribution by counter changes around each request. The engine's KV usage counter counts referenced blocks only and does not show unreferenced cached prefixes (StudyENG1b), so the policy keeps its own KV-pool and host-tier bookkeeping (6.1) as the primary belief and uses telemetry to correct it.
- Accuracy: StudyENG1 Part D: telemetry attribution correct 100 % at concurrency 1 and 40 % at concurrency 4. Belief is therefore a distribution over {GPU, HOST, COLD}; ambiguous evidence moves mass toward the colder tier.
- REQUESTED vs CONFIRMED transitions; only confirmed ones earn future value.
- VERIFY ON RESUME: before releasing the next piece of an RC job, check the believed residency of its built prefix. If part is lost, re-plan with the true remaining work (restore, then continue) and record requested continuation vs observed loss.

---

## 8. Decision procedures

### 8.0 Core and conditional mechanisms (D38, D50)

| mechanism | class | enabling condition |
|---|---|---|
| admission of escalations (8.1) | core | always on |
| coordinator with counterfactual release under pi_0 (8.2) | core | always on |
| historical jobs: continuation value with prefix-loss risk, feasibility (8.3) | core | always on |
| adaptive execution granularity (8.4) | core | always on; must pass T3 |
| readiness management under given capacities (7) | core | always on; T4 across a capacity sweep |
| per-tier calibration (3.2) | core | always on |
| outages (8.5) | core | always on |
| deficit counters (8.6) | core | always on |
| monitoring trigger (8.7) | core input | family OPEN (Q11) |
| TOUCH action (7.3) | conditional | M6 shows touches keep histories host-resident |
| escalation price (8.7) | conditional | DEV calibration shows a higher price suppresses the lowest-benefit escalations first |
| question-first path (4.3) | conditional | large unsent RC history and contended uplink |
| phase assignment (8.8) | conditional | predicted clustering gain exceeds capture-time shift cost |
| merging (8.9) | conditional | M3 shows merged-call utility exceeds the device's at the delays involved |
| summaries (8.10) | conditional | DEV quality competitive; refresh cost measured |
| predictive upload (8.11) | conditional | improves time-to-ready over on-demand upload |

### 8.1 Admission (core)

On arrival of a complete query or escalation r: build r's best plan (for RC, over {device, SUMMARY if enabled, RICH} given believed tiers, staleness, expected remaining work and feasibility); admit if DeltaJ_H(admit) > 0 against "decline". A declined request is discarded; the device's answer stands.

### 8.2 Coordinator (core) (D23, D25, D46)

On each event (arrival, completion, telemetry update, state re-solve, link change):
1. Update calendar, estimates, believed tiers, KV-pool and host bookkeeping, Z counters, job states and feasibility classes.
2. For each pending item p, compute DeltaJ_H(release p now) against "defer p to its next candidate slot", both under pi_0.
3. Release the item with the highest positive DeltaJ_H; re-score given the new in-flight set; repeat until none is positive. One release at a time.
4. No forced release. Approaching deadlines act through continuation value and deficits; feasibility rules bound waiting.
5. Commit only immediate releases; re-plan at the next event.

Decision cost (M4, StudyPOL2): 0.34 ms per DeltaJ_H evaluation; the release loop grows quadratically with the pending set (61.6 ms at 64 pending). Decision latency is reported as the scheduler's own overhead and enters t_decide (4.3). Keeping it bounded at large fleets is OPEN.

### 8.3 Historical jobs: feasibility and bounded waiting (D45, D46, D55)

Using the continuation schedule with EXPECTED remaining work (6.4):
- FEASIBLE: Phat_r(finish by D_r) under pi_0 above a threshold.
- FEASIBLE ONLY WITH PRIORITY: below under pi_0, above if r's pieces get priority over non-urgent background work (never over episodic work whose loss exceeds r's value).
- INFEASIBLE: below even with priority: stop spending GPU on r's answer; continue only pieces whose state value for future questions alone justifies them.
A job about to become infeasible within the next scheduling interval under the current ranking is promoted to the priority class.

### 8.4 Adaptive execution granularity (core; T3) (D17, D55)

Large work is split into prefix-chained pieces of whole frames reusing the cached prefix. For job r, the scheduler chooses among candidate sizes B_r (measured sizes plus whole-job):

    b_r* = argmax over b in B_r of Jhat_H(S_t, plan(r, b); pi_0)

Each plan includes its continuation value with prefix-loss risk, so exposure between pieces is part of the size choice. StudyENG1 (total delay imposed on all other requests): monolithic 11k rebuild 16.2-71.2 s; 2,048-token pieces 0.44-2.57 s; 1,024-token pieces 0.08-0.40 s; host reload 0.01-0.19 s. Remaining pieces are released only while DeltaJ_H stays positive.

### 8.5 Outages (core) (D32)

An unreachable device runs on its own model; its pending cloud work pauses; its StateValue and continuation values are discounted by P(reachable within H_s); its evidence on the cloud is kept (D56); on reconnect, backlog is caught up through the coordinator.

### 8.6 Deficit counters (core)

Updated per eligible opportunity (3.3); enter every DeltaJ_H.

### 8.7 Monitoring trigger (core input; family OPEN) and escalation price (conditional) (D20, D22, D34, D51, D52)

- The device computes Ghat (4.1) for each SH instant from self-normalized signals over its own recent window W_c (relative score z_t = (score_t - median) / IQR, rise score_t - score_{t - delta}, instability over n_c frames), never absolute confidence alone. It escalates when Ghat exceeds a DEV-fitted threshold, plus beta * pi(t) if the price is enabled.
- A cloud-initiated low-rate sampling (cadences up to about 10 s) may supplement or replace the device filter. Which family (device filter, cloud sampling, context-modulated sampling, or a combination) is OPEN (Q11). StudyCTRL1b could not decide it (score-scale confound); StudyCTRL1c decides it with calibrated scores and streaming AP (D58).
- Escalation price pi(t) = mu x (GPU-seconds of a typical first call), conditional as listed in 8.0. Because SLOs count all eligible opportunities, suppression cannot improve measured attainment by hiding difficult situations.
- Episode end: Ghat below threshold for K_c instants or E_k calls; the cloud may end an episode when DeltaJ_H of continuing is negative for K_e consecutive calls.

### 8.8 Phase assignment (conditional) (D21)

Follow-up calls of an admitted episode get a phase that clusters them with other episodes of the same cadence; the device sends its latest frame when the call fires. The one-time capture-time shift is charged in the rollout. Front-end serialization (4.3) reduces the clustering benefit and is modelled. Evaluated against unphased episodes. P10 out of scope.

### 8.9 Holding and merging episode calls (hold: core; merge: conditional) (D24)

A due follow-up call is dispatched or held by DeltaJ_H against "hold to next slot". Nothing is dropped on the device. With merging enabled, a held call still unsent at the next due time is sent with it (up to W_k frames); the earlier opportunity is a device-only outcome; the merged answer serves the later one with utility from M3 (StudyFRAMES1: a third frame bought nothing on EVAL).

### 8.10 Summaries (conditional) (D27, D49)

Generated by the cloud 32B when the GPU is idle, scored by DeltaJ_H as a state action; enabled only where DEV quality is competitive and refresh cost is measured (StudyF2 inconclusive).

### 8.11 Predictive batched upload (conditional) (D28, D32)

Batch upload when P_i^rep(need within H_up) >= theta_up, or the link is expected to degrade with unsent frames. Enabled when it improves time-to-ready over on-demand upload.

---

## 9. Main loop (pseudocode)

```
on event e at time t:
    update links, reachability, durations, demand rates (rc per rep, esc)
    update KV-pool and host-tier bookkeeping; correct believed tiers from telemetry; confirm or reject requested transitions
    for each eligible opportunity whose predicted outcome is known: update Z(i,k)
    if e is a query or escalation r:                       # complete query by default; question-first only by exception
        plan = best_plan(r)                                 # calibrated Ghat; expected remaining work incl. prefix loss; feasibility
        if DeltaJ_H(admit vs decline; pi_0) > 0: admit, add work; if SH and phasing enabled: assign phase
        else: decline (device answer stands)
    for each RC job: recompute expected remaining work, continuation schedule, Phat_r, feasibility class
    if state inputs changed or timer: desired tiers under C_gpu, C_host_eff; add state actions (promote, catch up, touch if enabled)
    if enabled and due: add upload / summary candidates

    calendar = build_calendar(t, t + H)
    choose piece sizes for large jobs by rollout over candidate sizes (deferral risk included)
    loop:
        for p in pending: DeltaJ_H(release p now vs defer p; pi_0)       # terminal value per 6.3, backlog subtracted
        p* = argmax; if DeltaJ_H(p*) <= 0: break
        if p* is the next piece of an RC job: verify its built prefix; if lost, re-plan and re-score
        release p*; add to in flight; update bookkeeping
    for each due episode call not released: hold; merge if enabled; else device-only outcome
    update mu (when estimable); if price enabled: broadcast pi
```

---

## 10. Parameters

| parameter | meaning | default / how set |
|---|---|---|
| (q_k, L_k, p_k) | per-task SLO | application parameters, swept |
| omega_k | class weights | DEV (omega_RC = 0.4246 provisional) |
| calibration maps | per-tier score to probability | DEV, cross-fitted on Nexar (StudyCTRL1c) |
| C_gpu, C_host | memory capacities | INPUTS, swept in evaluation |
| H | planning horizon | 0.5-1 s, swept |
| pi_0 | continuation policy | EDF over pending and calendar |
| mu | GPU backlog price | OPEN; PLACEHOLDER 0 must be replaced |
| P_host(occupancy) | host recoverability | measured (StudyENG1b roomy host; M6 for full host) |
| host eviction rule | which host copy is evicted | measured (M6); LRU is the code-reading prediction |
| continuation resolution | coarse extension to job deadlines | M4 |
| feasibility threshold | Phat_r cut-off | DEV, swept |
| H_s | state horizon | seconds, swept |
| candidate piece sizes | 8.4 | measured sizes plus whole-job |
| T_k, E_k, W_k | episode cadence, maximum length, window | per task |
| Ghat thresholds, beta, W_c, delta, n_c, K_c, K_e | trigger and episode end | DEV |
| H_up, theta_up | upload trigger | DEV |
| belief conservatism | mass toward colder tier when ambiguous | fixed, reported |

---

## 11. Evidence to date

All entries subject to the audit P4.

| study | what it establishes for the policy | limits |
|---|---|---|
| E9c | 32B over 4B on Nexar challenge mAP: +0.114 [0.061, 0.169] | single-tier numbers, unaffected by calibration |
| E9d | value-vs-delay curves; queueing a cloud call beats suspending to the device for windows up to about 4 s | always-on streams |
| E9b | device-triggered escalation captured 3-18 % | mixed-tier, CONFOUNDED by the score scale; recheck in StudyCTRL1c |
| E10b-E10f | a long prefill holds episodic requests until its first token; no engine setting removes it | vLLM 0.31.0 |
| SLICE1 A-D | prefix-chained pieces keep near-monolithic total work; independently released held work bunches; one coordinated lane removes bunching but piece size and timing still bind; known-schedule benefits shrink under jitter | jitter assumed (P6) |
| MAP1 | live-to-mAP bridge validated; a 9x p99 spread moved challenge mAP by at most 0.0087 | underpowered per cell |
| SIM1b-d | simulator engine model failed out of sample; host-tier per-request tax 0.0385 s | headline evaluation is live (D7) |
| PROF1 | omega_RC 0.4246; bandwidth held constant (ASSUMPTION) | conditional recall rate not computable |
| FRAMES1 | a third frame buys nothing on EVAL | |
| CTRL1b | always-cloud 0.5675 vs device-only 0.4776, gap +0.0899 [+0.036, +0.150]; no trigger separable from random; 32B scores about 5 log units below 4B's | mixed-tier rankings confounded (D57); challenge metric reads one crop per clip |
| ENG1 | serial blocking (rho 0.97-1.00); sub-linear batching; step model R^2 0.985; front end and admission stall; delay imposed on others per action (8.4); TTFT GPU 0.10 / host 0.17 / cold 2.74 s; telemetry 100 % / 40 % at concurrency 1 / 4 | 256 GiB host |
| ENG1b | prefix survival is a step function of KV allocated before resume; tail-first partial loss; P_host 0.999 with roomy host; reload +0.12 s vs rebuild +2.15 s; queueing behind running work 6-10 s; usage counter blind to unreferenced blocks | 256 GiB host |
| POL2 | v3.1 implemented, 120 tests; M4 0.34 ms per evaluation, release loop 61.6 ms at 64 pending; backlog sign corrected | placeholders mu = 0, P_host = 0 (being replaced in StudyPOL3) |
| T0 | see 12 | |

---

## 12. Approval tests

| test | what to establish | status |
|---|---|---|
| T0 cost-model fidelity | predicted delay imposed on others, job completion times, prefix-loss class match live measurement (pre-registered criteria: (i) delay within 1.5x or 0.1 s for >= 90 % of HOLDOUT triples; (ii) pairwise action ranking correct for >= 90 % of pairs differing > 2x; (iii) completion time median relative error <= 20 %; (iv) prefix-loss class correct >= 90 % on ENG1b, mechanistic) | RUN ONCE on the 174 ENG1 HOLDOUT triples (now spent). (i) FAIL: model 58.6 % against bar 90 % and measurement repeatability ceiling 83.9 %: a real fidelity gap, not only an over-strict bar. (ii)-(iv) and the diagnosis by action and load: report pending. A scoring-definition bug affecting 5 W25 cells is re-scored as a labelled secondary for (ii) only. |
| T0b noise-aware fidelity | (i-b) agreement rate (within 1.5x or 0.1 s) >= 0.9 x the repeat-vs-repeat agreement rate on the same conditions; (ii)-(iv) unchanged | pre-registered; to be evaluated ONLY on fresh held-out data (source TBD; ENG1c Part D HOLDOUT covers the host-full case) |
| T1 objective validity | online utility and predicted SLO success track measured task utility and attainment | pending (P7) |
| T2 coordinated release | beats EDF (its base policy), utility-per-cost, independent release, decomposed best-of-breed (live H100) | pending |
| T3 adaptive granularity | rollout-chosen piece size beats the best fixed size across load and jitter | pending |
| T4 joint readiness management | beats the strongest independent cache manager plus a good admission scheduler ACROSS A SWEEP OF C_gpu AND C_host, including host-full regimes | pending; requires M6 |

Until T0 or T0b passes, conclusions drawn from the rollout's absolute delay predictions are not relied on; if ranking (ii) passes while (i) fails, decisions may still be sound and the evaluation must say which.

Also reported: predicted vs measured attainment; greedy vs offline tier assignment; desired vs believed divergence; requested vs confirmed transitions; prefix-loss events per job, their cost, predicted vs observed P_loss, and how often deferral was chosen under pressure; feasibility classification accuracy.

---

## 13. Evaluation implications

- Application value: per-task utility over all eligible opportunities (Nexar challenge mAP as the SH headline and streaming AP alongside; deadline-qualified accuracy for RC; SS when available), with a powered design.
- Systems capacity: CONFIDENCE-AWARE capacity (D8): the largest fleet at which every device's SLO is met at a stated confidence, plus per-device SLO-margin distributions; tail latency, cold-rebuild frequency, utilization, freshness. Task utility at a fixed fleet size is the second axis.
- MEMORY-CAPACITY SWEEP (D56): C_host (and C_gpu where feasible) swept, including host smaller than, equal to and well beyond the GPU pool, and host-full regimes; never only the H100 default.
- Trigger results (D58): against LOAD (devices sharing the cloud), with budget as a secondary axis; streaming AP over all decision instants primary, challenge mAP secondary.
- Workload: aperiodic escalations from the trigger opening SH episodes; RC questions at real offsets with per-device arrivals; SS when available; trace-driven links with outages; always-on streams only as a stress case.
- Baselines: EDF; utility-per-cost admission; independently released background work; decomposed best-of-breed controller (B9 with audited fixes); strongest independent cache manager plus good admission (T4); absolute-confidence trigger; escalate-everything; always-on streams; tuned engine; device-only.
- Ablations (one off at a time): counterfactual scoring (FCFS; closed-form fallback); continuation value (none; tokens-processed proxy); prefix-loss term; feasibility rules; single coordinator; adaptive granularity (monolithic; each fixed size); deficit counters (fixed weights; pure utility; pure constraint); calibration (raw scores); tier assignment (LRU only; offline optimum as upper bound); telemetry-verified vs assumed residency; separate vs merged demand rates; every conditional mechanism on vs off; horizon sweep; known schedule vs cadence-only vs measured jitter.

---

## 14. Limitations, open items and pinned items

- OPEN: trigger family (Q11); mu estimation; bounding decision latency at large fleets; host eviction rule and touch effectiveness (M6).
- PROVISIONAL: host behaviour under A8 until M6.
- T0 criterion (i) failed; absolute delay predictions are not yet trustworthy (12).
- Per-device SLOs only (P1); single-shot workload pending (P2); one question type per device (P9); external-clock alignment out of scope (P10); controller context signals (P11); host-tier mode decision (P12); GPU price beyond backlog (P8); stronger VLM (P3); jitter assumed until measured (P6); F1 frames backup (P13).
- Online success is predicted; true attainment known only offline.
- SH utility is a surrogate for a pooled metric (T1).
- Residency is steered, not commanded; belief can be wrong and is reported.
- No formal guarantee for deficit counters or rollout improvement.
- Representation choice beyond readiness exercised only if SUMMARY passes its condition.
- The manuscript (Sections 4-5) must be reconciled with this version, including task names (LH = RC), the complete-query default, the SLO-constrained problem statement, calibration, prefix-loss risk, and the host-tier model.

---

## 15. Traceability

| section | decisions and measurements |
|---|---|
| header, rules, 8.0 | D36, D38, D50, D56 |
| 1 | D1, D19, D29, D31, D33, D37, D39, D44, D56; A0; M5, M6 |
| 2 | D12, D14, D26, D30, D44, D47, D48, D55, D56, D57 |
| 3 | D2-D5, D37, D40-D43, D45, D46, D57 |
| 4 | D51-D54, D57; A1-A5 |
| 5 | D5, D24, D30, D31, D39; M1 |
| 6 | D15, D16, D18, D43, D45, D46, D55, D56; M1, M5, M6; T0, T0b |
| 7 | D9, D12-D14, D26, D44, D47-D49, D55, D56; M5, M6 |
| 8 | D17, D20-D25, D27, D28, D32, D34, D38, D45, D46, D51, D52, D55, D58; M3, M4 |
| 10-13 | D6-D8, D56, D58; T0-T4, T0b; M1-M6; H1, H2; P7 |
