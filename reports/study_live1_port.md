# StudyLIVE1-port: the literature baselines, ported to the live harness

Pre-registered in `research/EXPERIMENTS.md` (StudyLIVE1-port) before anything was computed.
Engineering task on flash, **CPU only**: no GPU, no model server, no inference, and **no
baseline cell is measured in this row**. Code: `experiments/orchestration/live/`. Results:
`results/orchestration/live1/`.

**The decision this row records.** The HEADLINE evaluation will run LIVE on the H100 through the
StudySLICE1 harness. The simulator is secondary: StudySIM1d-validate failed its out-of-sample
check at 15/19 against an 80 % bar and its calibration gate stands at 19/29, so no simulator
number is a headline number.

**One sentence.** 33 of the 44 registry arms are
ORCHESTRATOR-LEVEL and now run unchanged inside a live loop through the same
`baselines/interface.py` contract the simulator uses; all 34 that were exercised
against a fake OpenAI-compatible server emitted only legal actions on an identical arrival trace
(0 failures), and the H100 plan costs
**39.9 GPU-hours** in full, of which the first two tiers are
**13.3**.

---

## 1. Which arms can run live, and which cannot

The test, stated before the classification: an arm is ORCHESTRATOR-LEVEL if it decides routing,
admission, deferral, rate or cadence, recall placement or session retention, because a process
outside the serving engine can enact all of that through the vLLM OpenAI API (what to send, when
to send it, how to chunk it, what to put in it) plus the existing host tier. It is ENGINE-LEVEL
if its mechanism lives inside the engine: scheduler internals, KV layout, or its own cache layer.

| count | |
|---|---|
| registry entries classified | 44 |
| orchestrator-level | 34 |
| engine-level | 2 |
| represented by a server configuration | 2 |
| not built | 6 |
| **run live** | **33** |

| arm | level | reason |
|---|---|---|
| `device-only` | ORCHESTRATOR-LEVEL | it decides routing only: every episodic call and every recall stays on the device, so the orchestrator simply sends nothing to the server. It is the floor of the live comparison. |
| `always-cloud-fcfs` | ORCHESTRATOR-LEVEL | every call goes to the server in arrival order, which is what the orchestrator does by default. It is the live reference. |
| `random-admission` | ORCHESTRATOR-LEVEL | admission only, 20 seeds; the orchestrator draws and sends or does not send. |
| `round-robin` | ORCHESTRATOR-LEVEL | an equal cloud share per stream is a sending decision. |
| `static-partition` | ORCHESTRATOR-LEVEL | a fixed cloud share per query class is a sending decision. |
| `edf-service-time` | ORCHESTRATOR-LEVEL | admission by a service-time estimate with EDF order: the orchestrator holds its own queue and submits in its own order. |
| `hindsight-oracle` | ORCHESTRATOR-LEVEL (EXCLUDED) | it is enactable, but it reads the future (`reads_future = True`), so it is an upper bound and is excluded from every deployable live comparison, exactly as in the simulator. |
| `videostorm` | ORCHESTRATOR-LEVEL | rate allocation across streams: cadence and frame count per stream are what the orchestrator puts in the request and how often it sends it. |
| `ekya` | ORCHESTRATOR-LEVEL | resource allocation across streams plus session demotion; both are sending and retention decisions. |
| `tuned-engine` | SERVER CONFIGURATION | it IS an engine configuration (StudyE10e's P1 flags). Live, it is not a policy at all: it is the server the cell is started with, and it may be run only as a config arm with every other arm held at E0. |
| `clockwork` | ORCHESTRATOR-LEVEL | admission from a predicted load time. The prediction reads the live TTFT history the harness already records; the decision is whether to send. |
| `confidence-cascade` | ORCHESTRATOR-LEVEL | device first, escalate on low confidence: the orchestrator runs the device answer and decides whether to send a cloud request. |
| `inar-vl` | ORCHESTRATOR-LEVEL | joint routing, cadence and frame count per stream. |
| `hybrid-llm` | ORCHESTRATOR-LEVEL | a query router: it decides device or cloud per episodic stream. |
| `routellm` | ORCHESTRATOR-LEVEL | a query router, as above. |
| `perllm` | ORCHESTRATOR-LEVEL | joint routing and rate selection under an SLO. |
| `attentionstore` | ENGINE-LEVEL | AttentionStore IS a host-side KV cache hierarchy with its own lookup, placement and prefetch inside the engine. An orchestrator can move a SESSION between tiers but cannot implement a cache layer under vLLM's attention, so what would run live is not AttentionStore. |
| `lmcache` | SERVER CONFIGURATION | LMCache is a CPU / disk KV cache layer under the engine. vLLM 0.31.0's native OffloadingConnector (`--kv-offloading-backend native --kv-offloading-size 256`, the KV-HOST configuration this suite already measures) is the same kind of thing, so live it is represented by that SERVER CONFIGURATION and never by a policy. Any claim is about vLLM's native offload, not about LMCache. |
| `pensieve` | ENGINE-LEVEL | its mechanism is MULTI-TIER PARTIAL RESIDENCY inside the KV manager - part of a session's cache resident, part not. The API exposes no partial residency, so only whole-session placement could be enacted, which is the mechanism removed rather than adapted. |
| `rh8-demand-aware` | ORCHESTRATOR-LEVEL | which sessions are kept warm, from demand. Keeping a session warm is an orchestrator action (hold it on the GPU, push it to the host tier, or drop it). |
| `r3-streaming` | ORCHESTRATOR-LEVEL | remember / respond / reason: representation choice, deferral and escalation are all sending decisions. |
| `flashback` | NOT BUILT | decided, not built |
| `covstream-PRE-ADDENDUM-SUPERSEDED` | NOT BUILT | superseded by the addendum entry |
| `tmo` | NOT BUILT | decided, not built |
| `eco-llm` | ORCHESTRATOR-LEVEL | joint tier, representation, cadence and frame-count selection under SLOs. |
| `streamscout` | ORCHESTRATOR-LEVEL | a recall-side cascade over increasingly deep views: each stage is a different request the orchestrator may or may not send. |
| `preble` | ORCHESTRATOR-LEVEL | cache-affinity-aware admission and ORDER. The orchestrator holds the queue and chooses what to submit next; LIMITATION, declared: once submitted, vLLM's own scheduler controls execution order, so the arm controls submission order and not engine order. |
| `mooncake` | ORCHESTRATOR-LEVEL | same as preble: prefix-affinity ordering of its own submissions. The paper's disaggregated prefill / decode architecture is NOT reproduced and no claim is made about it. |
| `kvflow` | ORCHESTRATOR-LEVEL | reuse-aware eviction and prefetch of SESSIONS: push to the host tier, hold on the GPU, or rebuild. All three are orchestrator actions here. |
| `uniscale` | ORCHESTRATOR-LEVEL | it scales the per-stream configuration, which is a sending decision. |
| `thinking-qwenvl-atdm` | ORCHESTRATOR-LEVEL | response timing: when to answer and when to defer. |
| `simplestream` | ORCHESTRATOR-LEVEL | a fixed recent window fed to the model: the window is what the orchestrator puts in the request. |
| `covstream` | ORCHESTRATOR-LEVEL | an edge / cloud split of where the session state lives, plus a heavy model on query only. Both are orchestrator decisions. |
| `route2look` | NOT BUILT | dropped (unverified) |
| `fairway` | NOT BUILT | dropped (unverified) |
| `querystream` | NOT BUILT | verified, not built (mechanism not fully specified) |
| `B3-best-static` | ORCHESTRATOR-LEVEL | a static configuration choice. |
| `B4-query-type-routing` | ORCHESTRATOR-LEVEL | routing by query type. |
| `B6-latency-aware-routing` | ORCHESTRATOR-LEVEL | routing from the measured latency estimate, which is live state the harness records. |
| `B7-edf-feasibility` | ORCHESTRATOR-LEVEL | EDF feasibility admission. |
| `B8-utility-per-gpu-second` | ORCHESTRATOR-LEVEL | utility-per-GPU-second admission. |
| `B9-best-of-breed` | ORCHESTRATOR-LEVEL | all four components are orchestrator-level, and live it runs FULL - with the real host tier - rather than as the no-host variant the simulator had to use. |
| `B10-blocking-aware-admission` | ORCHESTRATOR-LEVEL | it is StudySLICE1's P2, which the live harness already runs: hold the cold build while an episodic call is due, release on a gap or on slack. |
| `B11-naive-slicing` | ORCHESTRATOR-LEVEL | it is StudySLICE1's P3_2048, which the live harness already runs: the orchestrator chunks the build into prefix-chained requests. Live it CAN align each link, which the simulator's 1-s decision epoch could not. |

## 2. The adapter

`experiments/orchestration/live/adapter.py` is one loop that holds the SAME contract the
simulator holds: at every decision epoch it builds an `Observation` from LIVE state, calls the
policy - which validates its own `Action` through `interface.validate_action` - and enacts that
action against a backend. The arms are imported unchanged from
`experiments/orchestration/baselines/`.

| observation field | live source |
|---|---|
| `streams[].delivered_scores / _times_s` | what the application actually received: a cloud answer when its request completed, the device's own score otherwise |
| `streams[].cadence_s`, `frame_count`, `on_cloud` | the orchestrator's current setting for that stream |
| `cloud.queued_by_class`, `running_by_class` | the orchestrator's in-flight bookkeeping, cross-checked against the server's `/metrics` |
| `cloud.gpu_kv_fraction` | the server's `vllm:gpu_cache_usage_perc` |
| `cloud.gpu_warm_sessions`, `host_warm_sessions` | the harness's own session bookkeeping |
| `cloud.latency_estimate_s` | an EWMA of the MEASURED TTFTs of completed requests, per class |
| `recall[].readiness`, `readiness_tokens` | the same bookkeeping |
| `recall[].device_answer_confidence` | the committed per-question value, supplied only to an arm declaring `reads_device_answer`, with the device answer charged (StudyB-baselines amendment 2) |
| `budget_remaining_gpu_s` | the budget the harness meters, identical for every arm |

**What is enacted.** Device or cloud per episodic call (a device call is never sent to the
server; its delivery uses StudyD8's device latency); recall to DEVICE / CLOUD / DEFER / REJECT;
session KEEP_GPU_WARM / OFFLOAD_TO_HOST / EVICT; and MATERIALIZE with slices, **where each link
is a separate request**, which is the point of the port: live, a policy can hold or align each
link, which the simulator's 1-s decision epoch could not express (StudyB-baselines amendment 2,
item 8).

**What the orchestrator may not know.** It never sees the future schedule. It is given the
cadence-only model of StudySLICE1 Part D-b - each stream's past arrivals, its cadence and a
jitter margin, through `slice_rules.next_due_s` - and `interface.scrub` runs on every epoch, so a
future field cannot reach a policy even by accident. Any arm declaring `reads_future` (the
hindsight oracle, RH8's oracle reading) is excluded from the live set.

**Fairness, asserted rather than documented.** The per-cell arrival trace is built once and its
sha256 is asserted identical for every arm (`6d468569bdc40df14e863f05bb122e98` in this run, and
`all_digests_identical` is **True**); the server configuration is E0
unless the arm IS a configuration; the budget, the cold sessions and the warm plan are the same
for every arm.

## 3. The test without a GPU

`experiments/orchestration/live/fake_server.py` is an OpenAI-compatible stub speaking
`/v1/chat/completions` (streamed), `/v1/models` and `/metrics`. Its delay per request is drawn
from the COMMITTED StudySLICE1 distributions at the lowest load level of the matching kind
(`ttft_model.py`), and it serves through one FIFO queue, so queueing is produced by the stub
rather than being baked into the draw twice.

**Nothing from a stub run is a measurement.** The cell is also time-compressed
(20.0x) so that 600 trace-seconds run in about
30 s of wall time, which no measurement could
be. The stub's single FIFO server is strictly more blocking than vLLM's chunked-prefill
scheduler, so an on-time fraction from it says nothing about the H100.

What the run checks, per arm: every action was legal (an illegal one raises inside
`Policy.__call__` and the arm is recorded as failed); the trace digest is identical across arms;
no arm read the future; and a decision trace exists.

| arm | result | stream cloud | stream local | recall decisions | materializations | recall on time | epoch overruns |
|---|---|---|---|---|---|---|---|
| `B10-blocking-aware-admission` | ok | 0 | 0 | 96 | 4 | 0 | 0 |
| `B11-naive-slicing` | ok | 4802 | 0 | 7 | 2 | 0 | 0 |
| `B3-best-static` | ok | 4802 | 0 | 7 | 0 | 0 | 0 |
| `B4-query-type-routing` | ok | 4800 | 2 | 7 | 0 | 0 | 0 |
| `B6-latency-aware-routing` | ok | 4802 | 0 | 7 | 0 | 0 | 0 |
| `B7-edf-feasibility` | ok | 4802 | 0 | 7 | 0 | 0 | 0 |
| `B8-utility-per-gpu-second` | ok | 4802 | 0 | 7 | 0 | 4 | 0 |
| `B9-best-of-breed` | ok | 4764 | 38 | 7 | 2 | 2 | 0 |
| `always-cloud-fcfs` | ok | 4802 | 0 | 7 | 0 | 0 | 0 |
| `clockwork` | ok | 4802 | 0 | 7 | 0 | 6 | 0 |
| `confidence-cascade` | ok | 4800 | 2 | 7 | 0 | 5 | 0 |
| `covstream` | ok | 4802 | 0 | 7 | 2 | 0 | 0 |
| `device-only` | ok | 0 | 4802 | 7 | 0 | 7 | 0 |
| `eco-llm` | ok | 4802 | 0 | 7 | 0 | 0 | 0 |
| `edf-service-time` | ok | 4802 | 0 | 7 | 0 | 0 | 0 |
| `ekya` | ok | 4802 | 0 | 7 | 0 | 0 | 0 |
| `hybrid-llm` | ok | 0 | 4802 | 7 | 0 | 5 | 0 |
| `inar-vl` | ok | 4802 | 0 | 7 | 0 | 0 | 0 |
| `kvflow` | ok | 4802 | 0 | 7 | 0 | 0 | 0 |
| `mooncake` | ok | 4802 | 0 | 7 | 2 | 0 | 0 |
| `perllm` | ok | 20 | 4782 | 7 | 0 | 4 | 0 |
| `preble` | ok | 4802 | 0 | 7 | 2 | 2 | 0 |
| `r3-streaming` | ok | 0 | 4802 | 7 | 0 | 7 | 0 |
| `random-admission` | ok | 2442 | 2360 | 7 | 0 | 5 | 0 |
| `rh8-demand-aware-causal` | ok | 4802 | 0 | 7 | 4 | 0 | 0 |
| `round-robin` | ok | 4802 | 0 | 7 | 0 | 0 | 0 |
| `routellm` | ok | 4802 | 0 | 7 | 0 | 0 | 0 |
| `simplestream` | ok | 4802 | 0 | 7 | 0 | 0 | 0 |
| `static-partition` | ok | 2401 | 2401 | 7 | 0 | 4 | 0 |
| `streamscout` | ok | 4802 | 0 | 7 | 0 | 0 | 0 |
| `thinking-qwenvl-atdm` | ok | 4734 | 68 | 387 | 0 | 0 | 0 |
| `uniscale` | ok | 1840 | 2962 | 7 | 0 | 3 | 0 |
| `videostorm/maxmin` | ok | 4802 | 0 | 7 | 0 | 0 | 1 |
| `videostorm/maxsum` | ok | 4802 | 0 | 7 | 0 | 0 | 0 |

**34 of 34 arms ran; 0 failed.**
One decision trace per arm (up to 40 epochs each) is in
`results/orchestration/live1/live1_stub_runs.json` under `decision_trace`.

## 4. The H100 run plan - NOT RUN

The cost model uses committed numbers only: StudySLICE1 Part C measured 22 cells in 2 h 44 min
end to end (7.45 min per cell, each 30 s discard + 270 s
window + a drain of up to 300 s plus a server start), and its capacity walks averaged
2.44 cells per (policy, condition) pair.

Conditions: C1a = KV-GPU, k = 0 warm sessions, cold recall r = 0.05, C4a = KV-HOST, k = 8 warm sessions, cold recall r = 0.05, C1b = KV-GPU, k = 0, cold recall r = 0.1, C2 = KV-HOST, k = 8, no cold recall (warm only).
Ladder: the StudySLICE1 Part D-b stream ladder [1, 2, 3, 4, 5], the capacity walk
stopping at the first level whose episodic p99 misses the budget.

| order | tier | arm | GPU-hours | cumulative | why here |
|---|---|---|---|---|---|
| 1 | 0 | `always-cloud-fcfs` | 1.21 | 1.21 | the live reference; every other arm is read against it |
| 2 | 0 | `device-only` | 1.21 | 2.42 | the floor; it sends nothing, so it bounds what routing can win |
| 3 | 0 | `B10-blocking-aware-admission` | 1.21 | 3.63 | it IS StudySLICE1's P2, already measured in Part B, so it is the port's own validation cell: the live port must reproduce Part B's P2 numbers |
| 4 | 0 | `B11-naive-slicing` | 1.21 | 4.84 | it IS StudySLICE1's P3_2048, same validation argument, and live it can align each link, which the simulator could not express |
| 5 | 1 | `B9-best-of-breed` | 1.21 | 6.05 | the primary competitor, and live it runs FULL with the real host tier rather than the no-host variant the simulator was restricted to |
| 6 | 1 | `eco-llm` | 1.21 | 7.26 | the strongest joint routing arm in the simulator (challenge mAP 0.5263 on the audit cell) |
| 7 | 1 | `inar-vl` | 1.21 | 8.47 | the other strongest routing arm, same level |
| 8 | 1 | `B6-latency-aware-routing` | 1.21 | 9.68 | the constructed routing arm at the same level, and it reads the MEASURED latency estimate, which only exists live |
| 9 | 1 | `videostorm` | 1.21 | 10.89 | both objectives; after amendment 2 it routes to the cloud, so the live cell is the first that tests its allocation rather than its adapter |
| 10 | 1 | `B8-utility-per-gpu-second` | 1.21 | 12.10 | the admission arm the task names |
| 11 | 1 | `B7-edf-feasibility` | 1.21 | 13.31 | the deadline arm the task names; its self-fulfilling DEFER dynamic needs a live service time to be judged |
| 12 | 2 | `random-admission` | 1.21 | 14.52 | the remaining ported arms, in registry order |
| 13 | 2 | `round-robin` | 1.21 | 15.73 | the remaining ported arms, in registry order |
| 14 | 2 | `static-partition` | 1.21 | 16.94 | the remaining ported arms, in registry order |
| 15 | 2 | `edf-service-time` | 1.21 | 18.15 | the remaining ported arms, in registry order |
| 16 | 2 | `ekya` | 1.21 | 19.36 | the remaining ported arms, in registry order |
| 17 | 2 | `clockwork` | 1.21 | 20.57 | the remaining ported arms, in registry order |
| 18 | 2 | `confidence-cascade` | 1.21 | 21.78 | the remaining ported arms, in registry order |
| 19 | 2 | `hybrid-llm` | 1.21 | 22.99 | the remaining ported arms, in registry order |
| 20 | 2 | `routellm` | 1.21 | 24.20 | the remaining ported arms, in registry order |
| 21 | 2 | `perllm` | 1.21 | 25.41 | the remaining ported arms, in registry order |
| 22 | 2 | `rh8-demand-aware` | 1.21 | 26.62 | the remaining ported arms, in registry order |
| 23 | 2 | `r3-streaming` | 1.21 | 27.83 | the remaining ported arms, in registry order |
| 24 | 2 | `streamscout` | 1.21 | 29.04 | the remaining ported arms, in registry order |
| 25 | 2 | `preble` | 1.21 | 30.25 | the remaining ported arms, in registry order |
| 26 | 2 | `mooncake` | 1.21 | 31.46 | the remaining ported arms, in registry order |
| 27 | 2 | `kvflow` | 1.21 | 32.67 | the remaining ported arms, in registry order |
| 28 | 2 | `uniscale` | 1.21 | 33.88 | the remaining ported arms, in registry order |
| 29 | 2 | `thinking-qwenvl-atdm` | 1.21 | 35.09 | the remaining ported arms, in registry order |
| 30 | 2 | `simplestream` | 1.21 | 36.30 | the remaining ported arms, in registry order |
| 31 | 2 | `covstream` | 1.21 | 37.51 | the remaining ported arms, in registry order |
| 32 | 2 | `B3-best-static` | 1.21 | 38.72 | the remaining ported arms, in registry order |
| 33 | 2 | `B4-query-type-routing` | 1.21 | 39.93 | the remaining ported arms, in registry order |

| tier | arms | GPU-hours |
|---|---|---|
| 0 (references) | 4 | 4.8 |
| 1 (B9 and the strongest routing and admission arms) | 7 | 8.5 |
| 2 (the rest) | 22 | 26.6 |
| **total** | **33** | **39.9** |

Excluded from the plan, with the reason:

| arm | level | reason |
|---|---|---|
| `hindsight-oracle` | ORCHESTRATOR-LEVEL (EXCLUDED) | it is enactable, but it reads the future (`reads_future = True`), so it is an upper bound and is excluded from every deployable live comparison, exactly as in the simulator. |
| `tuned-engine` | SERVER CONFIGURATION | it IS an engine configuration (StudyE10e's P1 flags). Live, it is not a policy at all: it is the server the cell is started with, and it may be run only as a config arm with every other arm held at E0. |
| `attentionstore` | ENGINE-LEVEL | AttentionStore IS a host-side KV cache hierarchy with its own lookup, placement and prefetch inside the engine. An orchestrator can move a SESSION between tiers but cannot implement a cache layer under vLLM's attention, so what would run live is not AttentionStore. |
| `lmcache` | SERVER CONFIGURATION | LMCache is a CPU / disk KV cache layer under the engine. vLLM 0.31.0's native OffloadingConnector (`--kv-offloading-backend native --kv-offloading-size 256`, the KV-HOST configuration this suite already measures) is the same kind of thing, so live it is represented by that SERVER CONFIGURATION and never by a policy. Any claim is about vLLM's native offload, not about LMCache. |
| `pensieve` | ENGINE-LEVEL | its mechanism is MULTI-TIER PARTIAL RESIDENCY inside the KV manager - part of a session's cache resident, part not. The API exposes no partial residency, so only whole-session placement could be enacted, which is the mechanism removed rather than adapted. |
| `flashback` | NOT BUILT | decided, not built |
| `covstream-PRE-ADDENDUM-SUPERSEDED` | NOT BUILT | superseded by the addendum entry |
| `tmo` | NOT BUILT | decided, not built |
| `route2look` | NOT BUILT | dropped (unverified) |
| `fairway` | NOT BUILT | dropped (unverified) |
| `querystream` | NOT BUILT | verified, not built (mechanism not fully specified) |

## 5. Limitations, declared

1. **The stub is not a server.** Its delays are committed draws and its queue is one FIFO; vLLM
   batches and chunks prefill. Only the legality, the digest, the no-future property and the
   decision traces transfer from a stub run.
2. **Bodies are placeholders here.** `HttpBackend` sends a token-count placeholder and tells the
   stub how big it is; on the H100 the harness must inject the committed body builders
   (`study_slice1_live.build_cold` for a cold build, `d3_infer_vllm.body` for an episodic call).
   That injection point is the `Backend` protocol and is the ONE piece of integration work left.
3. **Submission order, not engine order.** preble and mooncake control the order in which the
   orchestrator submits; once submitted, vLLM's scheduler controls execution order. Any claim
   about either arm is about submission order.
4. **`tuned-engine` and `lmcache` are server configurations, not policies.** They may be run only
   as configuration arms with every other arm held at E0, and an LMCache claim is a claim about
   vLLM 0.31.0's native offload, not about LMCache.
5. **The device answer's latency is charged, its compute is not** (StudyB-baselines amendment 2):
   the budget meters the cloud replica only.
6. **Epoch overruns are recorded, not hidden.** A decision epoch that takes longer than the tick
   is counted per arm in the table above; the heavier arms (the ECO-LLM-style joint selections)
   are the ones that overrun on a compressed clock and will not on the H100's real one.

## 6. Files

| file | what |
|---|---|
| `experiments/orchestration/live/classify.py` | the orchestrator / engine classification, with the reason per arm |
| `experiments/orchestration/live/adapter.py` | the live loop: observation from live state, action enactment, fairness assertions, decision traces |
| `experiments/orchestration/live/ttft_model.py` | committed service-time distributions for the stub |
| `experiments/orchestration/live/fake_server.py` | the fake OpenAI-compatible server |
| `experiments/orchestration/live/run_live_cell.py` | the driver and the four checks |
| `experiments/orchestration/live/run_plan.py` | the H100 plan and the GPU-hour estimate |
| `results/orchestration/live1/live1_classification.json` | the classification |
| `results/orchestration/live1/live1_stub_runs.json` | one short cell per arm, with a decision trace each |
| `results/orchestration/live1/live1_run_plan.json` | the plan |
