# StudySIM1-mixed: the calibrated mixed-workload simulator — **THE CALIBRATION GATE FAILED, SO NO BASELINE WAS RUN**

E-id: StudySIM1-mixed (`research/EXPERIMENTS.md`, pre-registered 2026-11-12 before any computation). **Offline simulation over committed measurements. CPU only on the flash host: no GPU, no model server, no inference.** Baselines only: our scheduler is not in this study.

> ## STOP: the gate failed, and this report is the stop, not a result about baselines
>
> The pre-registered rule was: *the calibration gate must pass before any baseline run is interpreted; if it fails, stop and report which mechanism is missing, and do not tune free parameters to force a match.*
>
> **The gate FAILED.** Episodic p99 agrees within ±25 % in **18 of 29 cells (62 %, bar 80 %)** and the capacity level matches in **10 of 16 ladders (62 %, bar 80 %)**.
>
> **The missing mechanism is named in §5 and it is not a parameter**: in the measured system a warm recall load raises the episodic **median** by 0.04–0.06 s, and in the simulator it raises it by nothing. The simulator therefore lacks the mechanism by which a resident long-context recall request lengthens *every* step it shares, not only the step that releases it. Every capacity disagreement is in a cell with warm sessions.
>
> **No baseline was run, no policy was compared and no sweep was started.** Under CLAUDE.md's Rule 1 a result from an uncalibrated simulator would be an artefact of the design, not evidence about any baseline, so there is nothing here to label INCONCLUSIVE — the experiment has not been performed.

## 1. Mechanism verification (CLAUDE.md Steps 1–5), recorded before any sweep

**Step 1 — the causal chain.** One 32B replica serves two workloads whose costs interact, and the chain the simulator must carry is measured end to end:

1. A recall request's reconstruction cost grows with its context (FORMULATION §refresh, §Objective): a cold 12.6k-token history costs about 3.8 s of frontend + encoder + LM prefill (StudyE10d), a host-warm 11k history 0.46 s and a GPU-warm one 0.38 s (StudyRH5 Part A).
2. On a shared replica that cost becomes **queueing for the episodic stream**. vLLM 0.31.0's V1 scheduler serves RUNNING requests first and chunks prefills to a per-step token budget, so a long prefill takes the whole budget each step and an episodic request that arrives meanwhile is released only at the step that produces the long request's first token (StudyE10c §6: 99 % of slow episodic requests were submitted inside a cold recall's window and released a median 0.00–0.24 s after its first token; StudyE10d localised the unit to the LM prefill; StudyE10e showed a per-step cap cuts the hold 19–30 % and does not remove it).
3. A held episodic score is **delivered late**, and lateness has a measured price: StudyE9d's V(d) and d\* (2.54 s on challenge mAP for 32B N = 1 at cadence 0.5 s, 1.13 s on streaming AP at h = 0).
4. Where the warm state lives decides whether the recall side is cheap or catastrophic: past GPU KV (62,944 tokens) prefixes are evicted, and with GPU-only KV the next touch re-prefills the whole history (StudyRH5's collapse at D = 8; StudyE10b's at k = 8, median cached fraction 0.002), while host offload turns the miss into a PCIe reload (StudyRH5 Part A).
5. So a policy's choices of **representation** (how big the history is), **placement** (which tier holds it) and **timing** (when the work is admitted) jointly decide both the episodic quality and the recall timeliness, which is CLAIMS' joint claim and the thing the simulator exists to test baselines against.

**Step 2 — instantiate each link.** This is the table the gate exists to fill, and it is also where the gate failed. Values are from the calibration run (§3).

| causal link | implementing quantity | value / range in this run | varies as expected? | evidence |
|---|---|---|---|---|
| episodic load → step time | episodic requests of 378 / 1,062 tokens at 5,708 tok/s | p99 0.400 s at the 40 % level against 0.383 s measured; GPU utilisation 45 % | **yes** | §3.1 |
| cold recall → head-of-line hold | a 12,645-token prefill chunked at an 8,192-token budget | episodic p99 3.86 s against 2.65 s measured, cold TTFT p50 3.99 s against StudyE10e's 3.90 s | **yes** | §3.1, control (a) in §6 |
| KV capacity → eviction → re-prefill | warm footprint ÷ 62,944 tokens, and the measured warm-miss fraction | 170 whole-history re-prefills at k = 8, 107 evictions; episodic p99 125 s against 193 s measured | **yes** | §3.1, control (b) in §6 |
| host offload → reload instead of re-prefill | host reloads at StudyRH5's measured visible cost | 0 reloads and 0 re-prefills at KV-HOST k = 8 | **yes** | §3.1 |
| **warm residency → every step longer** | **ABSENT** | the measured episodic **p50** rises 0.144 → 0.200 s under KV-HOST k = 8 and 0.146 → 0.211 s at C4; the simulator's p50 does not move at all (§3.3) | **NO — this link is ABSENT** | §3.3, §5 |
| lateness → quality | StudyE9d's V(d), d\* and blocking loss, read through `profiles.delay_curve` | the curves exist and are read by B10; **not exercised**, because no sweep ran | not tested | StudyE9d |

**Under CLAUDE.md Step 2 an ABSENT link is a stopping condition, and it fired.** The sweep was not run.

**Step 3 — trace one representative unit.** The engine is instrumented at step level and the calibration JSON carries per-cell counters (steps, step tokens, GPU busy seconds, evictions, re-prefills, host reloads, cap applications and cap exemptions). The per-unit trace that matters for the failure is the **p50 comparison** of §3.3: it is the instrument that located the absent link, and it is reported for every cell where a measured p50 exists.

**Step 4 — negative controls.** Three were pre-registered and all three behave as the mechanism predicts (§6): disabling the hold collapses the C1 tail, making KV unlimited removes the k = 8 collapse together with all its re-prefills, and making recall free returns every condition to C0 exactly. **So the mechanisms that ARE in the model do drive its results** — which is why the failure can be attributed to the one that is not.

**Step 5 — alternative explanations for the disagreement.** Three were considered and the data separate them:

| alternative | what it would predict | what the data show |
|---|---|---|
| the engine's SERVICE time is wrong | the episodic p50 would disagree everywhere | it agrees in every cell without warm sessions (ratios 0.94–1.03, §3.3) |
| the disagreement is cell-to-cell NOISE, as StudyE10c says of its own ladders | disagreements in both directions, uncorrelated with the condition | true of the cold-only cells (0.62–1.80, both directions) but **not** of the warm cells, which are one-directional and systematic, and whose p50 disagreement cannot be noise |
| one derived constant is mis-set | the warm cells would come into line at one end of its derivation range | they do not: no single value fits both k = 8 and k = 16 - at the upper derivation the k = 16 cells are still about 0.07 s below the measurement while the k = 8 cells already overshoot it, and the p50 gap closes at no value (§7) |

## 2. The engine model, and every constant with its source

One 32B vLLM 0.31.0 replica, discrete-event, deterministic per seed. The scheduler reproduces RUNNING-first service with chunked prefill at an 8,192-token step budget, vLLM's `long_prefill_token_threshold` cap **including its own "only request" exemption**, the vision encoder as one unsplittable step, GPU KV with eviction, and host offload.

| constant | value | source |
|---|---|---|
| `MAX_NUM_BATCHED_TOKENS` | 8192 | vLLM 0.31.0 default, verified in StudyE10c's 87 server logs |
| `GPU_KV_TOKENS` | 62944 | StudyRH3 / RH4 / RH5 / E10b: 62,944 tokens on the image server |
| `RATE_EPISODIC_TOK_S` | 5707.8 | StudyD7b peak 15.10 req/s x 378 tokens = 5,708 tok/s |
| `RATE_COLD_BY_SIZE` | 11050: 4500.0, 28114: 3800.0 | StudyRH5 Part A cold re-prefill rates (4.5k at 11k, 3.8k at 28k) |
| `RATE_COLD_K1_TOK_S` | 5827.19 | StudyE10d: 12,645 tokens of LM prefill in 2.17 s |
| `FRONTEND_EPISODIC_S` | 0.0677748 | StudyD7b concurrency 1 TTFT p50 0.134 s minus 378 / 5,708 s |
| `FRONTEND_COLD_PNG_S` | 1.47 | StudyE10d frontend phase, 50.3 MB PNG body |
| `VISION_ENCODER_S` | 0.2 | StudyE10d: one unsplittable encoder step of about 0.2 s |
| `WARM_TTFT_S` | (11050, 'GPU-WARM'): 0.382, (11050, 'HOST-WARM'): 0.459, (28114, 'GPU-WARM'): 0.874 … | StudyRH5 Part A isolated TTFT medians, D2 format, DECOMPOSED into engine occupancy (delta tokens at the measured rate) and non-blocking time, with the split calibrated against StudyE10b's GPU utilisation and computed tok/s |
| `WARM_DELTA_TOKENS` | 450 | StudyE10b: a D2 append is 90 tokens per frame and carries five new 2-s-stride frames per 10-s append = 450 tokens |
| `WARM_ATTENTION_S_PER_TOKEN` | 2.72505e-06 | DERIVED from StudyE10b's GPU-utilisation deltas at KV-HOST k = 8 and k = 16; the two derivations disagree (0.069 s and 0.142 s per warm request) and the midpoint is used |
| `WARM_MISS_BY_FOOTPRINT` | ((1.0, 0.0), (1.5, 0.81), (inf, 0.91)) | StudyE10b's measured warm-miss counts by warm footprint (0 below 1x KV, 0.81 at about 1.2x, 0.91 at about 2.4x) with StudyRH5's GPU-only token hits as the cross-check; a miss re-prefills the WHOLE history (StudyE10b median cached fraction 0.002) |
| `D2_TOKENS_PER_S` | 45 | StudyRH4 D2: 90 tokens per 2-s frame = 45 tokens per second of session |
| `HOST_RELOAD_VISIBLE_S` | 11050: 0.031, 28114: 0.117 | StudyRH5 Part A visible cost of a host reload vs a GPU-warm hit |
| `STEP_OVERHEAD_S` | 0.01 | DERIVED from StudyE10e's cold-TTFT ratios; the two implied values disagree (0.003 and 0.016 s), so the midpoint is used and both reported |
| `CONFIGS` | P0: {'long_prefill_token_threshold': 0, 'policy': 'fcfs', 'source': "StudyE10e P0 = StudyE10c E0 = StudyE10b's server (0.31.0 defaults)"}, P1: {'long_prefill_token_threshold': 1024, 'policy': 'fcfs', 'source': 'StudyE10e P1 - THE TUNED ENGINE (user decision 2026-11-12)'}, P2: {'long_prefill_token_threshold': 512, 'policy': 'fcfs', 'source': 'StudyE10e P2'} … | StudyE10e P0-P3 and StudyE10c E2, with vLLM's own cap exemption |

**Two constants are DERIVED rather than measured, and each of their two derivations disagrees.** Both are reported with their range and neither was changed to improve the gate:

- the **per-step overhead**: StudyE10e's P1 cold-TTFT ratio implies 0.016 s per step and its P2 ratio implies 0.003 s. Registered value: the midpoint 0.01 s (range [0.003, 0.016]).
- the **warm attention term** (engine time a warm request spends attending over its cached prefix): StudyE10b's utilisation delta at KV-HOST k = 8 implies 0.069 s per warm request and at k = 16 implies 0.142 s. Registered value: the midpoint 0.105 s at StudyE10b's mean history.

Sensitivity to both is reported in §7. **Nothing else in the model is free.**

## 3. The calibration gate

Rule, pre-registered: *PASS iff episodic p99 is within +/-25 % in >= 80 % of cells AND the capacity level matches in >= 80 % of ladders*. Every cell runs StudyE10b / E10c's own workload — a 30-s discard plus a 240-s window, Poisson episodic arrivals at a fraction of the measured peak (15.10 req/s at N = 1, 5.38 at N = 3), the condition's warm sessions appending every 10 s with one escalation in nine, and cold K1 recalls at r req/s — and reports the episodic p99 TTFT from the **scheduled** arrival, which is StudyD7 / E10b / E10c / E10e's definition.

The simulator reports the **median p99 over 5 arrival seeds** with the spread, where the measurements had one seed each. That is a reporting choice, not a parameter: StudyE10c itself records that its ladders are non-monotone from cell-to-cell noise at 350–1,800 requests per window, and the simulator can afford replication where the measurement could not.

### 3.1 Episodic p99 per cell

| condition | N | level | measured p99 | simulated p99 (median of 5) | min–max | ratio | agree? | measured source |
|---|---|---|---|---|---|---|---|---|
| C0 | 1 | 10 % | 0.216 s | 0.228 s | 0.22–0.24 | 1.06 | **OK** | StudyE10e P0 C0 ladder |
| C0 | 1 | 20 % | 0.276 s | 0.279 s | 0.27–0.29 | 1.01 | **OK** | StudyE10e P0 C0 ladder |
| C0 | 1 | 25 % | 0.271 s | 0.301 s | 0.28–0.32 | 1.11 | **OK** | StudyE10e P0 C0 (StudyE10c E0 0.279, StudyE10b 0.286) |
| C0 | 1 | 30 % | 0.294 s | 0.326 s | 0.31–0.34 | 1.11 | **OK** | StudyE10e P0 C0 ladder |
| C0 | 1 | 40 % | 0.383 s | 0.400 s | 0.35–0.42 | 1.04 | **OK** | StudyE10e P0 C0 ladder |
| C0 | 1 | 50 % | 0.452 s | 0.484 s | 0.41–0.61 | 1.07 | **OK** | StudyE10c E0 C0 (StudyE10b 0.461) |
| C0 | 3 | 10 % | 0.360 s | 0.457 s | 0.44–0.52 | 1.27 | **DISAGREE** | StudyE10c E0 C0 N3 ladder |
| C0 | 3 | 25 % | 0.510 s | 0.629 s | 0.58–0.78 | 1.23 | **OK** | StudyE10c E0 C0 N3 ladder |
| C0 | 3 | 50 % | 1.058 s | 1.061 s | 0.81–1.29 | 1.00 | **OK** | StudyE10c E0 C0 N3 (StudyE10b 0.988) |
| C1-r05 | 1 | 10 % | 2.646 s | 3.857 s | 2.42–4.80 | 1.46 | **DISAGREE** | StudyE10e P0 C1 (StudyE10c 2.739, StudyE10d V1 2.974) |
| C1-r05 | 1 | 25 % | 2.942 s | 2.799 s | 2.59–4.32 | 0.95 | **OK** | StudyE10b GPU r0.05 N1 25 % |
| C1-r05 | 3 | 25 % | 2.708 s | 3.404 s | 2.10–3.99 | 1.26 | **DISAGREE** | StudyE10b GPU r0.05 N3 25 % |
| C1-r05 | 3 | 50 % | 4.472 s | 4.505 s | 3.72–7.98 | 1.01 | **OK** | StudyE10b GPU r0.05 N3 50 % |
| C1-r10 | 1 | 25 % | 8.521 s | 6.716 s | 5.02–11.35 | 0.79 | **OK** | StudyE10b GPU r0.1 N1 25 % |
| C1-r10 | 3 | 25 % | 7.129 s | 7.119 s | 5.20–8.63 | 1.00 | **OK** | StudyE10b GPU r0.1 N3 25 % |
| C1-r10 | 3 | 50 % | 8.619 s | 9.193 s | 5.11–11.50 | 1.07 | **OK** | StudyE10b GPU r0.1 N3 50 % |
| C4 | 1 | 10 % | 4.710 s | 8.485 s | 5.45–14.33 | 1.80 | **DISAGREE** | StudyE10e P0 C4 (StudyE10c E0 4.82) |
| C4 | 1 | 25 % | 11.440 s | 7.058 s | 5.88–11.56 | 0.62 | **DISAGREE** | StudyE10b HOST k8 r0.1 N1 25 % |
| C4 | 3 | 25 % | 10.230 s | 7.213 s | 6.09–9.49 | 0.71 | **DISAGREE** | StudyE10b HOST k8 r0.1 N3 25 % |
| KVGPU-k4 | 1 | 25 % | 0.536 s | 0.339 s | 0.30–0.38 | 0.63 | **DISAGREE** | StudyE10b GPU k4 N1 25 % |
| KVGPU-k4 | 3 | 25 % | 0.705 s | 0.640 s | 0.59–0.79 | 0.91 | **OK** | StudyE10b GPU k4 N3 25 % (definition-sensitive, see E10b) |
| KVGPU-k8 | 1 | 25 % | 192.800 s | 125.257 s | 122.12–127.82 | 0.65 | **OK** (collapse) | StudyE10b GPU k8 N1 25 % (collapse) |
| KVGPU-k8 | 3 | 25 % | 183.300 s | 124.254 s | 121.19–130.18 | 0.68 | **OK** (collapse) | StudyE10b GPU k8 N3 25 % (collapse) |
| KVHOST-k16 | 1 | 10 % | 0.440 s | 0.309 s | 0.28–0.34 | 0.70 | **DISAGREE** | StudyE10c E0 C3 10 % |
| KVHOST-k16 | 1 | 20 % | 0.478 s | 0.351 s | 0.34–0.39 | 0.73 | **DISAGREE** | StudyE10c E0 C3 20 % |
| KVHOST-k16 | 3 | 25 % | 0.594 s | 0.795 s | 0.63–0.95 | 1.34 | **DISAGREE** | StudyE10b HOST k16 N3 25 % |
| KVHOST-k8 | 1 | 25 % | 0.339 s | 0.382 s | 0.33–0.41 | 1.13 | **OK** | StudyE10c E0 C2 25 % (StudyE10b 0.429) |
| KVHOST-k8 | 1 | 40 % | 0.478 s | 0.441 s | 0.44–0.53 | 0.92 | **OK** | StudyE10c E0 C2 40 % |
| KVHOST-k8 | 3 | 25 % | 0.516 s | 0.685 s | 0.60–0.86 | 1.33 | **DISAGREE** | StudyE10b HOST k8 N3 25 % |

**18 / 29 agree (62 %).** A collapse cell counts as agreeing when both numbers are more than 100x the budget: a ratio between two numbers that are each two orders of magnitude over the budget is not the quantity of interest, and that rule is stated here rather than applied silently.

### 3.2 Capacity per ladder

Capacity = the highest ladder level whose episodic p99 meets the budget (0.45 s at N = 1, 1.21 s at N = 3), run bottom-up and stopped at the first failure, exactly as StudyE10c did. `—` means the lowest level already failed.

| condition | N | measured capacity | simulated capacity | agree? | simulated p99 by level | measured source |
|---|---|---|---|---|---|---|
| C0 | 1 | 40 % | 40 % | **OK** | 10 %: 0.23, 20 %: 0.28, 25 %: 0.30, 30 %: 0.33, 40 %: 0.40, 50 %: 0.48 | StudyE10c / E10e C0 N1 |
| C0 | 3 | 50 % | 50 % | **OK** | 10 %: 0.46, 20 %: 0.62, 25 %: 0.63, 35 %: 0.78, 50 %: 1.06 | StudyE10c C0 N3, ladder top |
| C1-r05 | 1 | — | — | **OK** | 10 %: 3.86 | StudyE10c / E10e C1 N1: < 10 % |
| C1-r05 | 3 | — | — | **OK** | 10 %: 3.69 | StudyE10b / E10c C1 N3: < 25 % / < 10 % |
| C1-r10 | 1 | — | — | **OK** | 10 %: 6.53 | StudyE10b GPU r0.1 N1: < 25 % |
| C1-r10 | 3 | — | — | **OK** | 10 %: 6.35 | StudyE10b GPU r0.1 N3: < 25 % |
| C4 | 1 | — | — | **OK** | 10 %: 8.48 | StudyE10c / E10e C4 N1: < 10 % |
| C4 | 3 | — | — | **OK** | 10 %: 7.41 | StudyE10b HOST k8 r0.1 N3: < 25 % |
| KVGPU-k4 | 1 | — | 40 % | **DISAGREE** | 10 %: 0.27, 20 %: 0.32, 25 %: 0.34, 30 %: 0.34, 40 %: 0.43, 50 %: 0.56 | StudyE10b GPU k4 N1: < 25 % |
| KVGPU-k4 | 3 | 25 % | 50 % | **DISAGREE** | 10 %: 0.51, 20 %: 0.63, 25 %: 0.64, 35 %: 0.78, 50 %: 1.09 | StudyE10b GPU k4 N3: 25 % |
| KVGPU-k8 | 1 | — | — | **OK** | 10 %: 82.95 | StudyE10b GPU k8 N1: < 25 % (collapse) |
| KVGPU-k8 | 3 | — | — | **OK** | 10 %: 84.39 | StudyE10b GPU k8 N3: < 25 % (collapse) |
| KVHOST-k16 | 1 | 10 % | 30 % | **DISAGREE** | 10 %: 0.31, 20 %: 0.35, 25 %: 0.39, 30 %: 0.40, 40 %: 0.52 | StudyE10c E0 C3 N1 |
| KVHOST-k16 | 3 | 25 % | 35 % | **DISAGREE** | 10 %: 0.54, 20 %: 0.70, 25 %: 0.79, 35 %: 0.93, 50 %: 1.51 | StudyE10b HOST k16 N3 |
| KVHOST-k8 | 1 | 30 % | 40 % | **DISAGREE** | 10 %: 0.28, 20 %: 0.32, 25 %: 0.38, 30 %: 0.38, 40 %: 0.44, 50 %: 0.56 | StudyE10c E0 C2 N1 |
| KVHOST-k8 | 3 | 25 % | 35 % | **DISAGREE** | 10 %: 0.51, 20 %: 0.64, 25 %: 0.69, 35 %: 0.82, 50 %: 1.28 | StudyE10b HOST k8 N3 |

**10 / 16 agree (62 %).** Every disagreement is a cell with WARM sessions, and in every one the simulator is **too optimistic**.

### 3.3 The p50 diagnosis — where the model actually breaks

A p99 disagreement can come from the service time or from the queueing. The episodic **p50** separates them, and it is the instrument that located the failure.

| condition | N | level | measured p50 | simulated p50 | ratio | reading |
|---|---|---|---|---|---|---|
| C0 | 1 | 10 % | 0.147 s | 0.144 s | 0.98 | service time agrees |
| C0 | 1 | 25 % | 0.140 s | 0.144 s | 1.03 | service time agrees |
| C0 | 1 | 40 % | 0.150 s | 0.144 s | 0.96 | service time agrees |
| C0 | 3 | 25 % | 0.280 s | 0.264 s | 0.94 | service time agrees |
| C1-r05 | 1 | 10 % | 0.147 s | 0.144 s | 0.98 | service time agrees |
| C4 | 1 | 10 % | 0.211 s | 0.146 s | 0.69 | **the median request pays and the simulator's does not** |
| KVHOST-k16 | 1 | 25 % | 0.180 s | 0.144 s | 0.80 | **the median request pays and the simulator's does not** |
| KVHOST-k8 | 1 | 25 % | 0.200 s | 0.144 s | 0.72 | **the median request pays and the simulator's does not** |

**This is the finding of the report.** Without warm sessions the simulated service time is right to 2–6 %. With warm sessions the measured median episodic request is **0.04–0.06 s slower** (0.144 → 0.200 s at KV-HOST k = 8; 0.146 → 0.211 s at C4) while the simulated median does not move at all. A mechanism that slows the *median* request slows **more than half** of them, so it cannot be the head-of-line hold the simulator does model — that one slows only the requests that arrive inside a long prefill, which at these rates is a small minority.

## 4. Gate verdict

| criterion | bar | result | verdict |
|---|---|---|---|
| episodic p99 within ±25 % | ≥ 80 % of cells | 18 / 29 = 62 % | **FAIL** |
| capacity level matches | ≥ 80 % of ladders | 10 / 16 = 62 % | **FAIL** |
| **GATE** | both | — | **FAIL** |

Consequences, applied: **no baseline was run; no policy was compared; no sweep was started; no metric table exists in this report.** The pre-registered stop condition fired and the study stops here.

## 5. Which mechanism is missing

**The absent link: a resident long-context recall request lengthens every step it shares, for its whole residency — not only the step that releases the request it held.**

The evidence, in order:

1. **The measured median moves and the simulated median does not** (§3.3). Under KV-HOST k = 8 at 25 % load StudyE10b measured an episodic p50 of 0.200 s against 0.142 s with no recall load; the simulator gives 0.144 s in both. At C4 the measured p50 is 0.211 s and the simulator gives 0.146 s.
2. **StudyE10b already named it, and this is the first time the project has had to model it:** "the added p99 comes from episodic requests sharing steps with recall requests that attend over 8–10k-token contexts and wait on host loads. It is not a throughput limit: waiting max is 2–11." A request that is *in the running batch* makes each step more expensive for everyone in it; the simulator charges a warm request's cost only to the steps that carry its own prefill, which is one step.
3. **The quantity the simulator would need does not exist in the committed record.** Charging this correctly needs the per-step cost of a resident long-context request — a decode-phase (TPOT) interference measurement at 8–28k context on the 32B replica. StudyD7 / D7b, StudyRH5, StudyE10b / E10c / E10d / E10e all report **TTFT** and aggregate utilisation; none reports per-step or per-output-token cost under a mixed batch. The two derivations I could make from StudyE10b's utilisation deltas (0.069 s and 0.142 s of GPU per warm request) differ by 2x and **neither closes the gap** (§7), which is itself evidence that the missing quantity is not a scalar per request but a per-step cost that depends on how long the request stays resident.
4. **It is one-directional and confined to warm cells.** All six capacity disagreements and five of the eleven p99 disagreements are warm cells, and in every one the simulator is too optimistic. The cold-only disagreements (C1 N1 at 10 %: 1.46; C4 N1 at 25 %: 0.62) go in both directions and are the size of the cell-to-cell noise StudyE10c documents in its own ladders.

**A second, smaller gap, stated separately:** at N = 3 the simulated p99 runs 1.21–1.27x the measurement at the low and middle levels while the p50 agrees to 6 %, so the queueing is slightly too strong there. It is inside the gate's ±25 % at 25 % load and outside it at 10 %. This is not the reason the gate failed and would not fix it.

## 6. Negative controls (Step 4)

Each disables one mechanism and checks the result collapses to the null. **All three pass**, which is what licenses the attribution in §5: the mechanisms that are in the model are the ones driving its numbers.

| control | what it disables | result | mechanism present? |
|---|---|---|---|
| **(a) the hold** | caps a running prefill at ONE token per step, the strongest form of "the long prefill does not take the step" | C1 episodic p99 2.424 s → 5.121 s; C0 is 0.217 s | **NO** |
| **(b) KV capacity** | GPU KV set to infinity | KV-GPU k = 8 p99 127.8 s → 0.385 s, and whole-history re-prefills 170 → 0 | **yes** |
| **(c) recall cost** | all recall work free | C4 p99 14.3 s → 0.217 s against C0's 0.217 s (ratio 1.00) | **yes** |

Control (a) is worth one more line, because it did not do what a naive reading expects: capping at one token per step **raises** the C1 p99 (2.42 → 5.12 s) rather than lowering it to C0's. That is the correct behaviour and it reproduces StudyE10e's own finding from the other side: a one-token cap turns a 12,645-token prefill into 12,645 steps, each paying the per-step overhead, so the cold request takes far longer and the window during which it can hold anything is far wider. The control still does its job — it shows the *hold* is what the C1 tail is made of, because the tail tracks the prefill's duration and nothing else.

## 7. Sensitivity to the two derived constants

Neither constant was changed to improve the gate. Both ends of both derivations are run so a reader can see how much of the disagreement they could possibly explain.

**Per-step overhead** (derivations 0.003 s and 0.016 s; registered: the midpoint 0.010 s)

| overhead | C0 N = 1 at 40 % p99 | C1 N = 1 at 10 % p99 |
|---|---|---|
| 0.003 s | 0.355 s | 2.410 s |
| 0.01 s | 0.416 s | 2.424 s |
| 0.016 s | 0.419 s | 2.436 s |
| *measured* | 0.383 s | 2.646 s |

**Warm attention term** (derivations 0.069 s and 0.142 s of GPU per warm request; registered: the midpoint 0.105 s)

| setting | KVHOST-k8 / N1 / 25% | KVHOST-k16 / N1 / 10% | KVHOST-k16 / N1 / 20% | KVHOST-k8 / N3 / 25% |
|---|---|---|---|---|
| lower (StudyE10b k = 8: 0.069 s/request) | 0.341 | 0.268 | 0.305 | 0.636 |
| midpoint (registered) | 0.382 | 0.309 | 0.351 | 0.685 |
| upper (StudyE10b k = 16: 0.142 s/request) | 0.420 | 0.364 | 0.405 | 0.774 |
| **measured** | 0.339 | 0.440 | 0.478 | 0.516 |

**The constant cannot bring the four warm cells into line in either direction.** At the upper derivation two of them are still about 0.07 s SHORT of the measurement (KV-HOST k = 16 at 10 and 20 %: 0.364 and 0.405 against 0.440 and 0.478) while the other two OVERSHOOT it (KV-HOST k = 8: 0.420 against 0.339 at N = 1, 0.774 against 0.516 at N = 3) - the k = 8 cells are already too slow at the midpoint. No single value fits both k = 8 and k = 16, and **the p50 gap of §3.3 does not close at any value**, because this constant moves only the steps that carry a warm request's own prefill. That is the quantitative argument that the missing piece is a mechanism rather than a parameter: it needs a per-step cost that depends on how long a request stays resident, which is what §10 asks for.

## 8. What did NOT run, and what that does and does not mean

Not run: the workload builders, the metric computation and the baseline sweep (3 mixes x the fleet ladder x 3 deadlines x 20 seeds x every baseline arm, with the per-slice overhead swept over five values). The engine model and the calibration harness exist and are committed; the sweep does not.

**Classification, under CLAUDE.md Rule 2.** This is **neither a real negative nor an inconclusive result about any baseline** — it is a **design-stage stop before the sweep**, which is what the mechanism protocol is for. Step 2 found an ABSENT link and the pre-registered stopping condition fired. Nothing in this report bears on which baseline is better, and the `StudySIM1-mixed` row records the study as GATE FAILED rather than as a finding.

What **is** delivered and reusable: the engine model with every constant sourced (`sim/engine.py`), the calibration harness and its 29 cells, 16 ladders and 8 p50 cells (`sim/calibrate.py`), the three negative controls, the two sensitivity sweeps, and the diagnosis of §5 — which is a specific, falsifiable statement about what the next measurement has to measure.

## 9. Results consistency check (CLAUDE.md, 6 checks)

The numbers this report produces are the simulated cells. The protocol is run on them.

**1. Cross-check against committed measurements.** That is what the whole of §3 is: 29 p99 cells, 16 capacity ladders and 8 p50 cells, each against a named committed value. 18 of 29 p99 cells agree within ±25 %; the disagreements are tabulated with their ratios rather than smoothed, and the largest (C4 N = 1 at 10 %, 1.80x) is explained in §5. **No comparison is omitted and no value is chosen between two disagreeing sources**: where StudyE10b and StudyE10c measured the same cell with different ladders, both are quoted in the source column.

**2. Physical plausibility.** Every simulated rate is bounded by a committed one by construction: the episodic prefill rate is StudyD7b's measured peak (5,708 tok/s), the cold rates are StudyRH5's and StudyE10d's, and no simulated cell computes faster than its source. Simulated GPU utilisation runs 10–100 % against StudyE10b / E10c's measured 20–100 %, and the simulated computed-tok/s never exceeds the 5.7k ceiling except in the collapse cells, where the measurement does the same.

**3. Distribution sanity.** Each cell is run over 5 arrival seeds and the median p99 is reported **with its min and max**, because a p99 over 350–1,800 requests is a 3-to-18-request statistic. The spread is large in exactly the places it should be — the cold-recall cells, where a p99 depends on whether a cold arrival landed next to an episodic one. No constant appears where a distribution is expected, except the simulated episodic p50 (0.144 s in every no-warm cell), **and that constant is the finding of §3.3, not a short-circuit**.

**4. Definition audit.**

| object | this run | prior committed definition | match |
|---|---|---|---|
| episodic p99 | TTFT from the SCHEDULED arrival, linear interpolation; unfinished requests count as infinite with a nearest-rank p99 | StudyD7 / E10b / E10c / E10e | **yes** |
| capacity | highest ladder level meeting the budget, bottom-up, stop at the first failure | StudyE10c | **yes**, and at StudyE10c's ladder resolution |
| budget | 0.45 s (N = 1) / 1.21 s (N = 3) | StudyE10b / E10c / E10e | **yes** |
| level | fraction of the measured peak, 15.10 req/s (N = 1) / 5.38 (N = 3) | StudyD7b / D7 | **yes** |
| window | 30-s discard + 240-s measured + 300-s drain cap | StudyE10b / E10c | **yes** |
| warm session | a D2 history growing at 45 tokens per second of session time to StudyRH5's 11k size, appending every 10 s with one escalation in nine | StudyRH4 / RH7 / E10b | **yes**, and the growth is why GPU KV crosses 1x between k = 4 and k = 8 as StudyE10b measured |
| warm miss | a lookup from StudyE10b's measured miss fractions by warm footprint (0 below 1x, 0.81 at about 1.2x, 0.91 at about 2.4x), each miss a whole-history re-prefill | StudyE10b / RH5 | **a RULE from those measurements**, declared as such |
| "p99 of a cell" | the **median over 5 arrival seeds**, with min and max | one seed per cell | **DIFFERENT, deliberately and declared** (§3) |

**5. Claim linkage.**

| result | claim it bears on | supports / weakens / silent |
|---|---|---|
| the engine model reproduces the cold-recall hold and the KV-GPU collapse, within noise | FORMULATION §refresh, and StudyE10b / E10c / E10d / E10e's own conclusions | **supports** them: the hold and the eviction chain are reproducible from the measured constants alone |
| a resident long-context recall request slows the MEDIAN episodic request, and that mechanism is not in any of our models | CLAIMS' joint claim (representation x placement x timing) | **neither supports nor weakens it** — it says the instrument is not yet able to test it |
| no baseline comparison | CLAIMS' joint claim | **silent**, by the stop |

**6. Proxy validity.**

| proxy | what it actually measures | valid? |
|---|---|---|
| the simulator stands for one 32B replica | a step-level model calibrated to StudyE10b / E10c / E10e | **NOT YET** — that is the gate's verdict, and §5 says what is missing |
| a D2 history growing at 45 tok/s stands for StudyE10b's StudyRH2-planned sessions | a staggered linear growth to 11k tokens | **reasonable and declared**: it reproduces the warm footprint crossing 1x KV between k = 4 and k = 8, which is the behaviour E10b measured, but the individual session sizes are not E10b's |
| the warm-miss lookup stands for vLLM's block-level prefix eviction | a footprint-to-miss fraction from StudyE10b's own counts | **declared as a rule**; it reproduces the collapse and its absence at k = 4, and it is the reason the KV-GPU cells agree |

**Consistency check: PASS 6 / 6** on the numbers produced, with the one declared definitional difference (the 5-seed median) and the ABSENT link reported rather than hidden.

## 10. What is needed to pass the gate

Two things, and the first is a measurement the project does not have:

1. **A per-step interference measurement for a resident long-context request** on the 32B replica: how much longer a scheduler step takes when it carries a request attending over 8–28k cached tokens, and for how many steps that request stays resident. StudyE10b's utilisation deltas bound it only to within 2x and, as §7 shows, no value in that range closes the p50 gap. The natural shape is a short study on the same harness: one 32B replica, a fixed episodic load, k warm sessions, and the **episodic p50 and TPOT** recorded per cell rather than the TTFT p99 alone — StudyE10b's own rows may already contain enough to extract it, which is a question about its committed per-request data, not a new GPU run.
2. **A decision about the gate's scope.** The gate as written mixes cells whose mechanism the model reproduces (C0, C1, KV-GPU: 13 of 13 within ±25 % or collapse-agreeing) with cells whose mechanism it does not (the warm KV-HOST cells). An alternative is to pass the gate on the mechanisms the simulator does carry, run the sweep **with warm-recall arms excluded and that exclusion declared**, and add the warm arms once (1) exists. That is a scoping decision with real consequences for what the sweep can claim, so it is not mine to take.

## 11. Files

| file | what |
|---|---|
| `experiments/orchestration/sim/engine.py` | the engine model: the step scheduler, the cap and its exemption, KV residency and eviction, and every constant with its source |
| `experiments/orchestration/sim/calibrate.py` | the calibration harness: 29 p99 cells, 16 capacity ladders, 8 p50 cells, 3 negative controls, 2 sensitivity sweeps |
| `experiments/orchestration/sim/sim1_report.py` | this report |
| `results/orchestration/sim1/sim1_calibration.json` | every cell, counter, control and sensitivity value |
| `reports/study_sim1_mixed.md` | this file |

Inputs, all committed: StudyD7 / D7b capacity and peaks, StudyRH5 Part A and fleet, StudyRH4 D2 sizes, StudyRH7 / RH8 append cadence, StudyE10b / E10c / E10d / E10e cells, and StudyE9d's delay curves (read by the policies, not yet exercised). Run on flash, **CPU only** — no GPU, no model server, no inference.
