# COVEX policy specification v6

**Status:** current specification, 2026-11-21. Supersedes `policy_spec_v4.md` and the repository's `research/policy_spec_v5.md`. Every rule cites the design-log row it comes from (`policy_design_log.md`, D1 to D166, P1 to P21). Where this document and an earlier spec disagree, this one holds. Items marked **PENDING** await a user ruling and carry a default.

**How to use it:** every component that is built is checked against the section that defines it, and the fidelity table in section 12 is filled in (IMPLEMENTED / PARTIAL / MISSING, with file:line) before any result from that build is read as a result of this policy.

---

## 1. Problem

Many CPS devices share one cloud accelerator running a large VLM (Qwen3-VL-32B on an H100 under vLLM 0.31.0). Every device runs its own small model (Qwen3-VL-4B on a Jetson Orin under vLLM, default Jetson configuration, D145, deployment defaults never changed) and **always has its own answer** (D19, D87). The device answer is the **incumbent**: the cloud is used only when doing so is expected to change the outcome (D149 (2), D152 (2)).

**Answer semantics: replacement** (D152 (1), D155 (3), D165 (B)). If the cloud's answer is delivered by the deadline it REPLACES the device's answer; otherwise the device's answer stands. There is no per-question selection between the two answers. So the realised gain of escalating one query is +1 (device wrong, cloud right), -1 (device right, cloud wrong) or 0, and its EXPECTATION, which is what the policy estimates, is P(cloud on time) x [acc_cloud - acc_device], from type-level DEV accuracies (D149). The joint split into corrective and harmful flips affects variance, not the expectation; it is reported, not estimated online. Per-question selection between answers (cascade-style) and accuracy bands by history length (not fittable on 28 DEV questions, G4) are out of scope.

The binding resource is **evidence readiness**: whether a device's accumulated evidence (its history or episode, as KV) is ready on the accelerator when a query arrives. Making it ready consumes the same accelerator that serves deadlines, and the KV pool cannot hold every device's evidence at once (D56, D150, D160).

**Decisions the coordinator makes** (D1, D151):
- **request:** for each query, admit now, defer to a planned time, or leave it to the device;
- **state:** where each device's evidence lives (GPU, host, cold) and when to warm, touch, reload, or let it go;
- **sync:** how frames reach the cloud, and catch-up after an outage.

**Objective: lexicographic, SLO-constrained** (D2, D41, D149, D151 (4), D165 (A)):
1. **Across types**, actions are compared ONLY by deficit-weighted target attainment: J(a) = sum over affected devices d of Z_d x (change in d's on-time target attainment under a), each change normalised by the device's own target window so sparse and dense devices are comparable (D122 B2). Deficit counters Z_d act as approximate shadow prices on the unmet per-device targets (virtual queues); no optimality guarantee is claimed.
2. **Within a type**, among actions whose J differs by less than the margin, expected correctness decides: which recall history to warm or keep, full history vs leaving it to the device, which same-type request to shed (D149 (2)).
Deficits are therefore an exchange rate across types, but in target-attainment units set online by how far each device is from its target, never a fixed value ratio between a correct answer of one type and of another.

**Memory capacities are inputs, not constants** (D56): GPU KV pool (62,944 tokens on the H100), host tier (27 GiB native write-through offload). Evidence that reaches the cloud is never deleted; "drop" means demoted to cold (raw frames, rebuilt by prefill).

---

## 2. Query types (taxonomy)

One query type per device (D148, D136; mixed types per device out of scope, P9, P17). Names follow the advisor's suggestion to name tasks by purpose (**PENDING** final names, deferred to the paper per D166; working names below).

| type | purpose | dataset | evidence | deadline | target |
|---|---|---|---|---|---|
| **alert** (short horizon, dashcam) | is a crash happening / coming | Nexar, 2 fps | the current episode: append-only, up to 21 frames | 1.0 s (D71, D154 (1)) | per episode (D166 (2)) |
| **recall** (long horizon, robot) | did I see X a while ago | S-EMBER LH-REQ, 69 EVAL questions whose evidence lies outside the 120 s recent window (D139) | the device's full history (D2 format), growing; device keeps only its recent window | 3.0 s (D147) | headline: correct answers delivered by the deadline (D152 (1), D155 (3)) |
| **assistance** (single shot) | answer about the current view | RefSpatial + RealWorldQA, EVAL 70 % split (D136, D142) | one image, no history | 2.0 s (D142) | 90 % within the deadline |

**Workload** (D142, D159 (C)): 16 devices (6 alert, 7 recall, 3 assistance), 1,200 s runs, seeds 4 to 7 (seeds 1 to 3 never used in development). Recall questions are re-asked on the same session's history after their original ask time (Poisson, mean 30 s), identical for every arm; gold is unchanged because the evidence is already in the past. Analysis is repeated-measures within question, paired across arms, clustered by question (D161).

**Delivery** (D146): an answer counts at completion (prefill plus decode); an alert Yes/No may count at first token.

---

## 3. Inputs to the coordinator

| input | what it is | source | rule |
|---|---|---|---|
| **deficit counters** | per device, how far below its target it is | live, from the **realised on-time** outcome at each opportunity's deadline (observable online) | D149 (1), D151 (4), D122 B; must be FED (`observe()` called by the coordinator) |
| **cost model** | predicted first-token and completion time from uncached tokens and uncached tokens queued ahead | profiled; fitted and tested on **healthy-regime** requests only | D162; non-negative form; never trusted across the saturation transition (D160 (2)) |
| **residency belief** | per session: GPU-warm, host-warm, cold | coordinator bookkeeping **corrected by engine telemetry**, including host hits | D44, D47, D150; PATCH 2 in mutate mode for full v5 |
| **quality table** | accuracy by type and representation, device vs cloud | profiled on DEV (D6) | D149; device entry = measured Orin values (D146 (2), D155) |
| **device latency** | per question | measured on the Orin, warm path (0.27 s median for recall) | D155, D161 (3) |
| **question-rate estimate** | per device, expected time to next query | causal EWMA over queries already seen | D11, D48, D160 (1); never the trace's future |
| **engine health** | first-token lag of deadline requests, deadline work queued | live | D160 (2) |
| **link state** | per-device bandwidth, RTT, outage | emulated per device, identical across arms | D150 SYNC (4); uniform 13.6 Mbit/s for the core grid |

Every number is tagged as profiled, live, use case, or design constant; design constants are fixed before evaluation and swept as sensitivity (D99, D71).

---

## 4. Decision loop

- Decision period 100 ms for every arm, events batched (D99 (1)).
- The counterfactual runs **event-gated** within the period: query arrival, completion, upload, memory pressure, reconnect, episode end (D151 (5)).
- Budget: decision p99 < 20 ms at 32 devices, measured with the decision-latency instrument (D151 (5)); a decision over budget falls back to the base rules.
- Order within a period: (1) saturation guard; (2) base rules; (3) counterfactual on the decisions it owns, deviating from the base only beyond the margin.

---

## 5. Base rules (executed by default)

The base is **hybrid-F-lhreq-noc3** (D152 (2), D154 (3)) plus D160's warming and guard (the v5-rules-2 rule set):

- **Feasibility (b7):** admit a request only if it can be delivered by its deadline on predicted load.
- **C1 ordering, C2 laxity-triggered alert throttle** (k_r = 0.3 x deadline, floor 2, at-risk alert exemption), **C5 alert-only in-flight cap** (AIMD 4 to 8).
- **No recent-frames shortcut for recall** (D152 (2), imposed as a user rule, D155 (4)): full history if it can arrive in time, otherwise the device answers.
- **Chunked just-in-time warming** (D160 (1)): a recall session's unwarmed tail is prefilled when a new chunk of uploaded material (2,048 tokens) has accumulated, or once early when a question is expected within the horizon (at most one early warm per session per expected-question cycle).
- **Saturation guard** (D160 (2)): fires when observed first-token lag of deadline requests exceeds 2.0 s or deadline work queued exceeds 100 (both declared from committed cells); while active, background warming is shed first and nothing else changes. **Exit with hysteresis** (D166 (3)): the guard exits only after both signals stay below 0.5x their entry thresholds for 2 s, so delayed observations cannot oscillate warming on and off; the lag signal's update rate (it is an EWMA over completions) is measured and reported.
- **Episode continuity** (D149 (3)): frames of an alert episode already admitted come before a new episode.

---

## 6. State management by query type

The three types have different reuse lifetimes, so evidence state is managed by type, not by a type-blind LRU (D150, user 2026-11-21).

| type | lifetime | GPU | host | on end |
|---|---|---|---|---|
| assistance | single use | used, then ages out | **not retained** (`max_offload_tokens: 0`; forbid-reload NOT used, D167) | nothing to keep |
| alert episode | at most one episode (up to 21 frames, 10.5 s) | kept warm by its own traffic (touched every 0.5 s) | **not retained** (dead episodes must not flush the host tier) | episode KV abandoned at episode end (section 8) |
| recall history | minutes, reused at every question | warmed and touched by the policy | **retained**; reload from host allowed (about 15x faster than rebuild, M3) | never deleted; demoted to cold only by capacity |

**Actuation** (what vLLM 0.31.0 allows; VERIFIED live on the H100 2026-11-21, `results/orchestration/live2/offload_verify/offload_verify_h100.json`): per request, skip host retention (`max_offload_tokens: 0`, honoured) and forbid host reload (`max_load_tokens: 0`, honoured; `kv_load_tiers: []` is NOT honoured and must not be used). There is no per-episode delete (only a full-cache reset). The only other actuator is sending a request (warm, touch, reload all act through requests, D150). Policy tier markings that do not reach the engine are not actions (fidelity audit c66bad4).

**State actions** (D150, D59):
- **warm:** prefill a recall session's unwarmed tail (chunked, section 5);
- **touch:** a minimal request reusing a warm prefix, to keep a recall history ahead of LRU (M2 confirmed on the 32B); priced by predicted cache state;
- **reload:** serve an evicted recall history from host;
- **hold back / slice:** limit what enters the GPU so a large cold rebuild does not evict a history whose question is due;
- every action is priced by **predicted cache state** (GPU, host, cold), never by slice size: a warm's token cost depends on whether its prefix survived (5,480 vs 471 uncached tokens, D160 analysis).

Baselines run vLLM defaults; the per-type controls are policy actions (D164).

---

## 7. The counterfactual

**Role:** decide the trade-offs whose consequences land beyond the current decision period, which rules cannot see (D151, D163): which recall histories to keep ready, when to warm or touch, whether to admit a cold rebuild that would harm others, and post-outage catch-up.

**Structure:** receding-horizon rollout over the base rules (standard; not claimed as new, D163). The base is executed by default; a counterfactual choice is taken only if its predicted gain beats the base by **MARGIN_CF** (D151 (1)), so the policy is never worse than the base up to cost-model error.

| decision kind | candidates | horizon |
|---|---|---|
| **request** (recall) | admit now with full history; defer to the latest safe start (deadline minus predicted service x a measured safety factor, re-plan on slip); leave to the device | until its own deadline plus the deadlines it displaces |
| **state** | for each recall history: warm, touch, reload, hold, let go cold | until the history's next likely question (capped 60 to 120 s) |
| **sync** | backlog order after reconnect; question-first vs wait vs leave to the device (D54) | until caught up |

Alerts and assistance stay rule-based (D151 (2)).

**Compound candidates** (D165 (D)), from the coupling measured on the live engine (eviction):
- **protect and defer:** warm or touch recall history H AND defer cold rebuild R to its latest safe start, when R's allocation would evict H before H's expected question;
- **keep-ready set:** touch the top-k recall histories by expected value of their next question and let the rest go cold (the keep-ready selection as one candidate);
- **admit with protected victim:** admit recall query q now AND touch the history its rebuild would otherwise evict.

**What a rollout represents (stated, not overclaimed):** single deviations evaluated against the base continuation for everything else (so an action's effect on other devices' default behaviour is captured), the named compounds above, and greedy sequential composition of committed deviations within a period. General joint optimisation over all devices' actions is NOT claimed.

**Fidelity of the horizon:** exact step-level simulation only over the near term (the current deadlines in flight); beyond it, future demand is valued from the causal question-rate estimate and a coarse load forecast. A 60 to 120 s state horizon is a valuation of expected future questions, not a detailed simulation of future engine execution.

**Objective** (D151 (4), D165 (A)): the lexicographic rule of section 1, harm to other devices included (D15, D152 (1)).

**Healthy regime only** (D160 (2)): candidates are evaluated only inside the healthy regime; if the guard is active, the counterfactual defers to it.

**Margin** (D154 (2), D157 (2), D158 (1)): set once, after the D162 gate passes, as the p90 of a_D2_DEV (0.250) x abs(P_hat(on time) - 1[on time]) over robot questions in the held-out cells, P_hat frozen and hashed first; identical in every cell; never swept. No full-v5 cell runs before it is set.

**Gate** (D151 (6), D162): cost model fitted and tested on healthy-regime requests (window first-token p50 <= 2.781 s), non-negative NNLS form, held-out split contains warm rows, pass if held-out ratio_p50 in 0.80 to 1.25 (warm 0.70 to 1.43). Fit data: a load sweep of warm-all-lru-reactive at 4 to 20 devices, seeds 4 and 5.

**What it must demonstrate** (D163): its gain concentrates on decisions with delayed consequences (warming, keep-ready selection, cold rebuilds), near zero where rules suffice.

---

## 8. Alert episodes end to end (D164, D165 (C), D166 (1) and (2))

- An alert device is asked at every decision instant on its growing episode context (EP-G, D153).
- This is a **cloud-context lifecycle policy**: it changes only how long the cloud keeps an episode's context, never the stream, the opportunities or the ground truth (D165).
- An episode **ends** at the EARLIER of: the cloud's calibrated P(yes) crossing a DEV-fitted threshold (operating point: matched false-alarm rate 10 %, swept 5 % and 20 %, D166 (1)), or the 21-frame cap. Only cloud-SERVED instants can trigger a crossing; an episode the cloud does not serve ends at the cap. The next frame starts a new episode, from the same device.
- It must earn its place: full v5 is run with and without the rule (a switch in the ablation ladder) and the rule is claimed only if it measurably helps; otherwise it is reported as an implementation detail of the readiness lifecycle, not as a separate contribution.
- At episode end: the episode's KV is abandoned (not retained on host; ages out of the GPU), its per-episode target restarts, and the coordinator, queue and counters treat the next episode as a new instance.
- Instants before an episode's third frame are not decision instants for any arm (D153), counted per run.
- Calibration and thresholds are fitted on the episode format for both tiers from StudySH-EP DEV folds (the one-frame maps D86 / D105 do not apply).
- **Target** (D166 (2)): per episode, enough cloud-served instants before the episode ends; the deficit restarts with each episode.
- This is a policy mechanism (our insight). Baselines run the workload's default EP-G (fixed 21-frame refresh). In policy runs the device keeps its default episodes and the cloud's context is a policy choice over the same frames.
- Note for reporting: the data supports that the 32B **detects crashes the 4B misses**, not that it detects earlier (StudySH-EP: lead time not different at matched FAR in 14 of 15 cells).

---

## 9. Sync and network (D150 SYNC)

- Devices upload every frame as captured (per-frame upload, D154 (4)); upload is decoupled from warming.
- A query carries any frames the cloud lacks (question-time delta).
- Outage: the device answers alone and keeps its raw frames since the last confirmed sync; on reconnect the counterfactual orders the backlog (section 7).
- Links are emulated per device, identical across arms; core grid uniform; synthetic outage sweep (10 / 30 / 60 / 120 s) and 5G uplink percentiles after the core grid (D150 (5), D75).

---

## 10. Evaluation (summary)

- Baselines run once on the final workload (D164): EDF (8 in flight), LLF, b7, always-cloud, eco-llm, confidence-cascade, cascade-routing (thresholds calibrated per card), SimpleStream, QueryStream-proactive, R3-Streaming, StreamScout, Mooncake, AttentionStore and KVFlow (with published prefetch), an LRU-contrast arm (the lmcache adapter), warm-all-lru, device-only (offline).
- Ablation ladder (D172 names; `research/arm_name_map.md` maps every old name to its rung):

| rung | name | adds | implemented by | status |
|---|---|---|---|---|
| 0 | `covex-v6-base` | the hybrid-F-lhreq-noc3 rules | `hybrid-F-lhreq-noc3` | READY, 6 committed cells |
| 1 | `covex-v6-rules` | chunked just-in-time warming + saturation guard | `v5-rules-2` | READY, 4 committed cells |
| 2 | `covex-v6-state` | per-type host retention, TOUCH chosen by `plan_state`, belief from telemetry, state pricing | none yet | NOT BUILT |
| 3 | `covex-v6-fair` | deficit feed + value reader | none yet | NOT BUILT |
| 4 | `covex-v6` | the counterfactual: request, state, sync, compounds, episode-rule switch | `v5-full` | runnable, ZERO cells |

  `v5-rules` is NOT rung 1 under another name: it is the superseded naive per-frame warm-ahead
  design, and `v5-rules-2` replaced it with a different mechanism. A rung that is not built
  RAISES rather than resolving to the rung below (`arm_names_v6.py`), so no cell can run a lower
  rung under a higher name. Cell lists: `V6STATE_CELLS`, `V6FAIR_CELLS`, `V6_CELLS` (which
  supersedes `V5FULL_CELLS`).
- Metrics: recall correct by deadline (paired, clustered), assistance within 2 s, alert challenge mAP and per-episode target, per-device target attainment, capacity, decision latency.
- Sweeps after the core grid: memory (1x, 0.5x, 0.25x), deadline (recall 2.5 to 5 s), fleet size, re-ask rate, network.
- Real-device validation (P21) only after the policy works.

---

## 11. Out of scope (stated)

Mixed query types per device (P9, P17); identifying query type from a continuous stream; contexts beyond 32k tokens (D152 (3)); a disk-KV tier (D78, Q12); intermediate offload of embeddings (KV is not portable across models); energy as an objective (D33); a better alert trigger (P14, D62).

---

## 12. Fidelity table (fill before reading any result)

Paths are relative to `experiments/orchestration/live2/`. Status is as of 2026-11-21 after full-v5 component 1. A row is IMPLEMENTED only where the quantity is READ by code that changes a decision; a definition with no production caller is MISSING, however complete it looks (the write-only-field rule).

| element | section | D-rows | status | file:line |
|---|---|---|---|---|
| deficit counters fed from realised on-time | 3 | D149 (1), D151 (4) | **MISSING** | `v5/cf_objective.py:140` defines `observe()`; its ONLY callers are `v5/cf_proofs.py` (test code), so no production path feeds it |
| cost model, healthy-regime, non-negative | 3, 7 | D160 (2), D162 | **PARTIAL** | pre-registered at `research/prereg_cost_model_gate_d162.md` (9bd6793); refit awaits the seed-5 load-sweep cells |
| residency belief corrected incl. host hits | 3 | D150 | **PARTIAL** | `cstate.py:123` reads `telemetry_cached_tokens`, but the field is NULL in every committed residency row, so the correction never fires; PATCH 2 still observe-mode |
| measured device answers and latency | 3 | D155, D161, D168 | **IMPLEMENTED** | robot warm latency `data_sources.device_recall_warm_latency_s`; dashcam EP-G warm-append by episode position and single-shot per question `data_sources.dashcam_append_ttft_s` / `single_shot_total_s` over `results/device/study_devlat/orin_device_latency_tables.json`; READ in the live wait at `coordinator.py:_device_wait_s`, fallback counter 0 on all four device-waiting arms. Re-ask device ANSWERS are still frozen at the original ask and labelled PROVISIONAL (D161 (3)) |
| causal question-rate estimate | 3 | D11, D160 (1) | **IMPLEMENTED** | `arms_v5rules2.py:132` |
| base rules (b7, C1, C2, C5, no RECENT) | 5 | D140 to D155 | **IMPLEMENTED** | `hybrid/` config `hybrid-F-lhreq-noc3` |
| chunked JIT warming, one early warm per cycle | 5 | D160 (1) | **IMPLEMENTED** | chunk trigger `arms_v5rules2.py:237`; JIT cap `arms_v5rules2.py:139` |
| saturation guard | 5 | D160 (2) | **IMPLEMENTED** | `arms_v5rules2.py:81` |
| guard exit with hysteresis | 5 | D165, D166 (3) | **MISSING** | not built; default confirmed (both signals below 0.5x entry for 2 s) |
| per-type host retention / reload controls | 6 | D150, D164, D167 | **IMPLEMENTED + VERIFIED** | rule `offload_policy.py:30-52`; the READ that puts it on the wire `coordinator.py:836`; arm-scoped switch `coordinator.py:113`; wire placement `bodies.py:226-230`. D167: alert and single-shot carry `max_offload_tokens: 0`, recall carries nothing (engine default retention plus native reload); forbid-reload not used. Engine honouring VERIFIED live 2026-11-21: skip-retention gave COLD against the positive control's HOST-WARM (external 8,080, 0.123 s vs 1.4 s cold). Proved on the actual wire bodies per device type (`offload_proofs.json` P7): flag present on exactly dashcam and assistive, absent on robot, absent everywhere with the switch off. Baselines unchanged: base `a8f482b791fb99c3`/16,649 and warm-all-lru `ec3519072614c534`/8,073 |
| touch | 6 | D150, M2 | **IMPLEMENTED (unexercised in v5-full)** | request `coordinator.py:698` `_submit_touch`, dispatched from the `KEEP_GPU_WARM` branch `coordinator.py:513`, switch `coordinator.py:118`; rule and M6 guard `touch_policy.py:49-77`. The pre-existing `engine_actions.touch():230` only set `desired_tier`, which steers the COORDINATOR's eviction order and sends nothing to the engine, so it could not move vLLM's LRU recency. Proved live on a constructed coordinator (`touch_proofs.json`); UNEXERCISED in v5-full until `plan_state` chooses it (component 6), because the v5-rules base emits no `KEEP_GPU_WARM` (`arms_v5rules.py:18`) |
| reload from host | 6 | D150, M3 | **MISSING** | component 1 permits it per request; no explicit reload action exists |
| actions priced by predicted cache state | 6, 7 | D160 | **IMPLEMENTED** | touch `touch_policy.py:71`; warm and reload `touch_policy.py:103` `build_price_gpu_s`, read at `coordinator.py:783` in `_advance_build`, switch `coordinator.py:120`. The committed charge was `recall_gpu_s(piece, "COLD")`, the new slice only, which omitted the cost of re-presenting the built prefix; that term is now priced by predicted state (2,048 new tokens on an 11k prefix: GPU 0.455 s, host 0.914 s, cold 2.900 s, and the prefix term is 0 / 0.459 / 2.444 s). Touch at 11k: GPU 0.382 s, host 0.459 s, cold 2.444 s |
| value reader at admission and warm / keep | 7 | D149 | **MISSING** | `v5/value_readers.py` exists and is imported by `v5/cf_planner.py:299`, but only from `plan_state`, which has no production caller, so it is unreachable in a live run |
| counterfactual: request | 7 | D151 | **IMPLEMENTED** | `arms_v5full.py:209` |
| counterfactual: state | 7 | D151, D163, D172 | **IMPLEMENTED** | `arms_v6state.V6StateArm.decide` is `plan_state`'s first caller outside the proofs; before it the kind implemented no causal link in any run (Step 2: ABSENT). 44,300 decisions on a dry 16-device cell, KEEP on every one: the argmax prefers a non-KEEP candidate on 44,299 and the margin rule overrides it back, max gain 0.151 against 0.16456, ceiling 0.250. Rule 2: FIRED AND DID NOT HELP. `v6state_attribution.json` |
| per-type host retention | 6 | D164, D167, D172 | **IMPLEMENTED, UNEXERCISED in dry** | `offload_policy.RULE` (alert and single-shot `max_offload_tokens: 0`; robot retained), emitted at `coordinator.py:996` when the arm declares `live2_offload_controls`. It acts through `kv_transfer_params` to vLLM, so a dry cell has nothing to receive it and `-noretain` is byte-identical to the full rung there. The dry null is a harness property and carries no information about the mechanism; `V6STATE_CELLS` is the test |
| belief corrected from engine telemetry | 6 | D44, D47, D150 PATCH 2, D172 | **IMPLEMENTED, UNEXERCISED in dry** | `coordinator.py` belief-apply, now ARM-SCOPED (`live2_belief_apply`) rather than a process-wide env switch, which had made every arm in a run share one setting. Driven by the engine's own `cached_tokens`, which a dry cell does not produce, so `-nobelief` is byte-identical to the full rung there, exactly as the coordinator's own comment says it must be |
| state-based pricing | 6 | D160, D172 | **IMPLEMENTED** | `touch_policy.build_price_gpu_s` behind `live2_state_priced_costs`. The SOLE cause of covex-v6-state's difference from covex-v6-rules at 16 devices, by one-factor ablation: `-noprice` returns to `ae997d6af16a2ef4` exactly and no other ablation does. 17,050 decision rows fall to 15,734. Byte-identical at 8 devices, because pricing can only matter once the budget binds |
| budget charged as engine WORK | 9 | D102, D173 (1), (2), D174 (1) | **IMPLEMENTED** | `live2/d162_price.py`. D174 (1) rules the charge UNCACHED TOKENS ONLY: `0.0001824312597782467 x uncached`, no 0.0678 s intercept (per-request OCCUPANCY, not work) and no queue term (delay SUFFERED, not work). Both excluded terms stay in the planner's harm to others, where they are the right quantity. Read arm-scoped at all four coordinator charge sites, and the MODE is arm-scoped too (`live2_charge_mode`, read through `d162_price.arm_charge_mode`), because a module global that any path can move is how covex-v6-state s6 ran an unruled charge. D102 BOTH HALVES PASS: no-artificial-binding, 0 refusals on a dry probe cell with 2,038 state decisions and 4,376 rows against covex-v6-rules' 4,376 (work-only gave 298 and 4,317; the full formula 10,612 and plan_state silenced); utilisation-tracks-measured-busy, per-uncached 737.5 s against measured 721.9 s (s4) and 985.3 against 964.5 s (s5), ratio 1.022 both, implied 5,482 tok/s against the committed 5,600, utilisation 0.61 and 0.82 of wall against busy fractions 0.60 and 0.80, nothing oversubscribed. Work-only reached 1.07 and 1.34 and FAILED this half. Posted as `covex-v6-state-uo` seeds 4 to 7; the rung-1 rerun is SKIPPED per D174 (1). `one_price_proofs.json`, `d174_proofs.json` |
| budget refusals in the committed cells | 9 | D173 (4) | **IMPLEMENTED** | `budget_refusal` is ABSENT, i.e. ZERO, in every committed v5-rules and v5-rules-2 cell and in covex-v6-state s5. D173 (4)'s conditional does not fire: the warming finding is NOT a budget-accounting artefact. v5-rules-2 submits HALF the dashcam monitors the base does (4,829 against 9,745 at s4; 5,182 against 9,812 at s5) with zero refusals, so the rung-1 dashcam loss is a SUBMISSION gap and correcting the charge cannot fix it. Single-shot loss IS budget: the 88 unsent at covex-v6-state s4 are touch-driven refusals, and single-shot is intact at s5. `budget_refusal_census.json` |
| rung-1 dashcam SUBMISSION gap, diagnosed | 9 | D174 (2) | **IMPLEMENTED** | `live2/rung1_submission_gap.py`, read-only from the committed cells (no new cells). Identical opportunity streams (11,764 monitor opportunities at s4 in both arms); released fraction 0.41 to 0.46 at rung 1 against the base's 0.83 to 0.89 across seeds 4 to 7. The ruling's two hypotheses both fail. (a) SLOT COMPETITION is not the per-epoch mechanism and cannot be: C5 subtracts only `running_by_class['episodic']` and cstate classes piece and whole builds under 'recall', and 59 to 70 percent of the epochs where a monitor goes unreleased have NO build in flight (156 to 180 builds per cell, under one in flight on average). (b) C2 FIRING MORE is REFUTED WITH THE OPPOSITE SIGN: epochs with a robot inside k_r = 0.9 s are 261 to 562 at rung 1 against the BASE's 578 to 711, because warming is what stops a question being at risk, and they touch 2 to 6 percent of the gap epochs. (c) THE MECHANISM, not in the ruling's list: C5's AIMD cap COLLAPSES. The few long builds push monitor first-token p90 from 0.65 to 0.71 s to 1.39 to 1.65 s, and the share above C5's 0.8 s trip from 4 to 6 percent to 21 to 27; each trip HALVES the cap (floor 4) and recovery is +1 per 5 s, so the cap sits at its floor for 7,544 to 8,428 of 12,000 epochs against the base's 1,844 to 2,989, and the release budget (cap minus episodic in flight) is zero in 87 to 93 percent of the gap epochs. The hysteresis is why (a) reads as absent per epoch: the damage outlives the build. POSITIVE CONTROL: the reconstructed AIMD trajectory reproduces the base arm's own `c5_decrease` and `c5_increase` exactly on all four base cells (154/154, 112/111, 118/117, 92/92; 97/97, 106/106, 97/97, 77/77). The C2 test is a declared PROXY (arrival and release times inside k_r, not the arm's predicted remaining work), an upper bound on at-risk periods, because v5-rules-2's `arm_stats` reports only its own warming counters and no committed cell surfaces the inner hybrid's `c2_throttle_periods`, `c2_throttled_dash` or `c5_dash_held`. CONSEQUENCE: the loss is the base policy's own controller reacting to a latency signal warming moves, so repricing could not have fixed it; any fix is a change to C5's AIMD rule or to how warming yields, which is a POLICY change for the user. `rung1_submission_gap.json` |
| 32,768-token context limit as a feasibility rule | 9 | D170, D144 (3), D175 (2) | **IMPLEMENTED at EVERY covex-v6 rung, OFF on the old names and baselines** | `hybrid/hybrid_arm.py` `CONTEXT_LIMIT_TOKENS = 32768` and the arm-scoped `over_limit_infeasible` switch: a recall whose predicted prompt exceeds the limit is INFEASIBLE and the question is the device's, counted as `over_limit_infeasible` with `over_limit_tokens_max`. D175 (2): ON at EVERY covex-v6 rung, the base included, and OFF on every old committed name and every baseline. Committed rung 0 to 2 cells stay reusable because the rule moves no decision, proved ONE CELL PER PROCESS at seed 7 where the 18 over-limit questions exist: covex-v6-base cdfafa48342b7e6a/12,157, covex-v6-rules a3c000f4ae2f37f5/12,179 and covex-v6-state 6a109870301df3e5/12,734, each identical with the rule off and on, and covex-v6-rules at seed 4 reproducing the committed v5-rules-2 digest ae997d6af16a2ef4 exactly, so the alias is still an alias WITH the rule on (`d175_digest_proofs.json`). THE RULE IS NOT REDUNDANT WITH THE TIME TEST, which is what the positive control establishes: a 32,769-token query on a GPU-WARM prefix has a SMALL predicted service time, so `est <= slack` ADMITS it (decision CLOUD on the ablation) and only the rule declines it (REJECT). That is the case warming creates, and rung 1 and above warm ahead. REPORTED PER ARM AND SEED as D170 asks: 18 recall questions exceed the limit, ALL AT SEED 7 (34,051 to 52,861 tokens; seeds 4 to 6 top out at 26,671 to 26,941, so a zero there is UNEXERCISED and says nothing). No arm of ours sent one; they are declined on TIME, not on the limit, which is b7's behaviour inherited through the base. `simplestream` released all 18 as a 467-token short representation, which is a representation decision and not an over-limit send. `always-cloud-fcfs` sent two (38,821 and 48,811 tokens) and both came back with no prompt_tokens, no http_status and the 'X' no-letter sentinel, one of them recorded as delivered ON TIME 17 ms after submission, which is impossible for a 38,821-token prefill. THE SCORER then lets that refusal REPLACE the device's answer (`cloud_stands = on_time and cloud_letter`), which contradicts D170's 'the device answer stands' while matching D144 (3)'s 'a per-question MISS for whichever arm sends it'. Measured impact on every committed number: ZERO, because that question's device answer is also wrong. The conflict is REAL IN THE RULES and UNEXERCISED IN THE DATA, and it is the user's to settle. `d170_overlimit.json`, `d170_rule_proofs.json` |
| a refused request never replaces the device answer | 9 | D165 B, D144 (2), (3), D175 (1) | **IMPLEMENTED** | TWO SCORERS DISAGREED and the headline reader was right. `frozen_headline.py` tests `http_status != 200`, which is True for `None`, so a refusal was already excluded from `ont` and `cloud_stands` was already False: NO HEADLINE NUMBER MOVES. `scorer/score.py` tested `http_status is not None and != 200`, which is False for `None`, so its D144 pass skipped a request that never got a status and the per-cell score block let the refusal replace the device answer. Fixed by `score.refused_request_ids`: a non-200 status, OR no status with no `prompt_tokens` and no `output_tokens`. The test is the REQUEST, not the letter, because `'X'` is StudyR1's no-letter sentinel that a genuinely delivered answer can also produce. The second clause is narrow by measurement over the 49 committed rq30 cells: 441,023 requests at 200 with tokens, 3,568 at 200 with no token fields (KEPT, they answered), 700 with no status and no tokens (the hole), 82 non-200 (already caught). IMPACT: 23 cells touched, 21 outcomes lose an on-time cloud answer (20 monitor, 1 recall), 0 dashcam device target verdicts change, and ZERO cells of ours are affected. The one recall is always-cloud-fcfs s7 opp0006097 and its standing answer does not change either, because that question's device answer is also wrong, so the D144 (3) against D175 (1) conflict stays UNEXERCISED in the data. `d175_rescore.json` |
| arm counters reported from the whole delegation chain | 9 | D174 (2) follow-up | **IMPLEMENTED** | `coordinator._arm_stats` merges every Counter in the arm's `_rules` / `_base` / `_scorer` chain, prefixing a colliding name by its holder's class rather than summing it. Before it, `arm_stats` was `arm.stats` alone, so a v6 ladder arm reported the WRAPPER's counters and nothing from the base HybridArm that actually decides: every committed v5-rules-2 cell carries `warm_ahead_emitted` and `guard_active_epochs` and carries NO `c2_throttle_periods`, `c2_throttled_dash` or `c5_dash_held`, although the base counts all three every period. That is what forced the D174 (2) diagnosis through a reconstruction and a declared proxy, and it is the write-only-field failure wearing the other mask: the counter was written and never read. Found again from the other side while proving D170's rule, where the same gap reported 0 firings while the decision had already changed. Implementation fix; it adds keys to future cells and changes no decision. |
| planner time limit: proved OFF, run ON, counted per cell | 9 | D99 (3), D151 (5), user ruling 2026-11-22 | **IMPLEMENTED** | `cf_instrument.over_budget` is a WALL-CLOCK limit, `budget_ms = 20.0`. PROOFS patch it off, so a decision digest is a property of the arm; LIVE cells run with it on, because abandoning to base when the clock runs out is a real cost. `cf_planner.note_abandon` records decisions and abandonments BY DECISION KIND plus the `budget_ms` in force, wired at the rung-2 `plan_state` site and the rung-4 request site through one helper; `coordinator._planner_time_limit_summary` derives the fraction per kind into every cell and sets `flag` above 1 percent. Measured on flash, dry, 16 devices, seed 4: 1 to 2 abandonments out of 44,300 state decisions (0.002 to 0.005 percent), all of kind `state`. That is a LOWER BOUND for a live cell: the H100 host CPU is about 2.2x slower (D115 (1)), so the flash rate must never be quoted for one. ALSO SETTLED BY ITS OWN COUNTER: the time limit is NOT the cause of rung 2's irreproducible dry decisions, which was my first hypothesis and was wrong. `V6STATE_CELLS` states the budget and requires the rate from the first live cell |
| dry decisions do not reproduce across runs IN ONE PROCESS | 9 | found 2026-11-22 | **OPEN DEFECT, protocol in place** | `covex-v6-state` on one dry cell gave 15,871 rows then 16,109 in the SAME process, with `state_decisions` itself moving 44,300 to 45,337; `v5-rules-2` and `covex-v6-state-off`, which have no planner, reproduce exactly. RULED OUT: the planner time limit (1 to 2 abandonments in 44,300, and two fresh-process runs agree whether it is on or off), `PYTHONHASHSEED` (fixed at 0, still drifts), and the registration context (the arm's config, switches, cap, k_r, chunk and slice sizes and MARGIN_CF are byte-identical across contexts). Separate processes with identical setup DO reproduce exactly. PROTOCOL until it is found: every byte-identity proof runs ONE dry cell per process (`d175_digest_proofs.py`). CONSEQUENCE FOR A NUMBER ALREADY CITED: `v6state_attribution.json`'s "-noprice returns to the rung below's digest exactly" was taken with several arms in one process, so the word EXACTLY does not hold; the attribution it supports (state pricing is the sole cause of the rung-2 difference) is unaffected, because the arms it compares either have no planner or differ by far more than the drift |
| harm_warm computed, not declared | 7 | D172 follow-up | **IMPLEMENTED** | `cf_objective.harm_warm_from_queue_delay`, pre-registered in `research/prereg_harm_warm_d172.md` BEFORE any grid was rerun. Takes the warm's uncached tokens through the committed D162 `per_queue_token` 0.00015358 (NOT `per_uncached_token` 0.00018243) to a per-request delay, through the same `p_on_time` curve, valued by the same `option_value` as `harm_to_others`, so gain and harm stay in one currency under D171 (2). Capped at 2.781 s with `harm_warm_capped` counted. 527 of 2,035 decisions priced on a dry 8-device cell, mean over priced 0.1039, max 0.120, capped 0 |
| deficit feed (`observe()` called) | 7 | D149 (1), D151 (4), D122 B, D172 | **IMPLEMENTED** | `arms_v6fair.V6FairArm.live2_completed` feeds the counters from the coordinator's completion hook, which now carries `deadline_abs_s`, `cloud_on_time`, `device_wait_s` and `device_on_time`. Before it, `served == 0` made `weight()` return exactly 1.0 for every device forever, so every deficit-weighted quantity was multiplied by one in every run. 15,587 observations at 16 devices, ALL on time, so weights are still 1.0: now inert because the fleet meets its target, not because the counter is unfed. BLIND SPOT, counted: declined opportunities never reach the hook, so a device whose requests are declined has its shortfall UNDERCOUNTED (`deficit_feed_unseen_declines`) |
| counterfactual: sync | 7 | D151 | **MISSING** | `v5/cf_planner.py:619` defines `plan_sync`; only caller is `v5/cf_proofs.py` |
| lexicographic objective (J across types, correctness within) | 1, 7 | D165 (A) | **MISSING** | not built |
| replacement answer semantics | 1 | D152 (1), D165 (B), D171 (2) | **IMPLEMENTED** | BOTH sides of the subtraction now. Gain: `v5/cf_objective.py::option_value`. Harm: `v5/cf_objective.py::harm_to_others` prices each displaced device's own answer, `w_o x (p_before - p_after) x (acc_cloud_o - acc_dev_o x p_dev_on_time_o)`, behind `cf_planner.HARM_REPLACEMENT_SEMANTICS`. It had passed `acc_dev = 0.0`, which charged a displaced request its FULL cloud accuracy and OVERSTATED harm. A/B on the dry grid: all 118 non-zero harm terms shrink (mean |harm| 0.009395 to 0.006711), none grows, and 0 of 56 decisions change, which is UNEXERCISED under Rule 2 and not a null. `v5/d171_proofs.py::P2` |
| margin weighted by the deciding device's deficit weight | 7 | D171 (1) | **IMPLEMENTED** | `deviate iff (value_cf - value_base) > w_d x MARGIN_CF`, one helper `v5/cf_planner.py::effective_margin` read at all three comparison sites (request, state, sync), behind `cf_planner.MARGIN_WEIGHTED_BY_DEFICIT`. The gain is weighted by `w_d` and MARGIN_CF was measured UNWEIGHTED per question, so without this a device at w = 2 would clear the model-error bar at half the true gain. Deficit weights keep their roles in ranking and in `harm_to_others`. PROVED byte-identical to the pre-D171 rule on the dry grid at w = 1, and at w = 1.40 the bar rises 0.16456 to 0.230384. `v5/d171_proofs.py::P1` |
| device model in the counterfactual | 1, 7 | D155 (3), D171 (3) | **IMPLEMENTED** | `v5/cf_objective.py::DeviceLatency` reads the measured Orin tables through the SAME `fleet/data_sources.py` accessors `coordinator.py::_device_wait_s` reads; the 0.567 proxy is off the decision path and survives only as the value a fallback would return. 3,577 lookups on the dry grid, FALLBACK 0. The term varies ACROSS types (single-shot mean 0.8791, refspatial 0.5451 with 126 of 277 at zero against the 2.0 s deadline) and is CONSTANT AT 1.0 WITHIN the robot type, because every measured robot warm latency (0.2503 to 0.3108 s) is inside every robot deadline: now constant because the device is FAST, a measured fact, not because the input was flat. UNEXERCISED on today's robot-only cells. `v5/d171_proofs.py::P3` |
| compound candidates (protect and defer, keep-ready set, protected victim) | 7 | D165 (D) | **MISSING** | not built |
| episode rule as switch, cap when unserved | 8 | D164, D165 (C) | **MISSING** | unblocked by D166; built after state / deficit / value / planning |
| margin set once from the gate | 7 | D154, D157, D158, D169 | **IMPLEMENTED** | MARGIN_CF = **0.16456**, set once from the D169 population (rq30 v5-rules-2 and hybrid-F-lhreq-noc3 pair, seeds 4 to 7, robot questions released in healthy windows): n 476 overall and 271 warm, both above the 40 minimum; p90 warm 0.1503, cold 0.1732. P_hat rebuilt on the D162 model and frozen BEFORE scoring (`cf_ontime_model_d162.json`, `cf-ontime-d162-1.0`, payload 8fa0c7fe, code df6863b0). `v5/margin_cf_d169.py` |
| episode end on calibrated threshold, cap 21 | 8 | D164, D166 (1) | **MISSING** | operating point confirmed (FAR 10 %, swept 5 / 20 %) |
| EP-G calibration for both tiers | 8 | D164 | **PARTIAL** | 32B and 4B DEV-fold fits computed (32B pooled a = 0.045048, b = +0.580874); AUC verification unfinished, and TPR approximately equals FAR at every operating point, so discrimination is not yet established. Live EP-G scoring still uses the ONE-FRAME map `live2_calibration_dense_jpeg.json` (a = 0.13203687653187707, b = -2.214426984591406), whose `body_check` raises unless exactly one frame is sent: a confirmed fidelity gap |
| per-episode alert target | 8 | D164, D166 (2) | **MISSING** | default confirmed; deficit restarts per episode |
| per-frame upload, question-time delta | 9 | D150, D154 | **IMPLEMENTED** | `fleet/trace.py` per-frame upload; question-time delta in the submission path |
| decision latency instrument, p99 < 20 ms | 4 | D151 (5) | **PARTIAL** | instrument present in `arms_v5full.py`; p99 at 32 devices not yet measured |
