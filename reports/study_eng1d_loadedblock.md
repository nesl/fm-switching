# StudyENG1d-loadedblock: how long a request waits behind a long prefill on a server already under load

Pre-registered in `research/EXPERIMENTS.md` (row StudyENG1d-loadedblock, written 2026-11-17 before any run).
Machine: h100nvl GPU 2, exclusive. Scripts: `experiments/cost/study_eng1d_loadedblock.py` (runner),
`experiments/cost/study_eng1d_analyse.py` (analysis). Data: `results/cost/study_eng1d/`.

Sections 1 and 2 (design, smoke, mechanism verification Steps 1 to 5) were written after the smoke and BEFORE the
sweep, as CLAUDE.md requires; sections 3 onward after the run.

## Summary

- **Run:** 2026-11-17 08:05 to 10:07 (2.0 h), not VOID. Both gates passed: unloaded control within ENG1 Part B,
  P40 mono11k total imposed delay 44.9 s within ENG1 Part C's 22.5 to 64.4 s. 180 FIT pairs and 36 repeats; 60
  HOLDOUT pairs recorded and not analysed. 0 cached-token mismatches over 13,149 compared requests. Derived step
  attribution conserved the action's tokens exactly in 180 of 180 trials.
- **Verdict: H1 in 11 of 12 cells, and stronger than H1.** An arrival during a long prefill waits out ALL of the
  action's remaining prefill, then waits again for the requests queued ahead of it. rho_b (25 to 75 % offsets) is
  1.17 to 1.43 for mono11k and rises with load (S2 < P25 < P40 < S4); 0.91 to 1.44 for piece2048; 0.82 to 1.07 for
  piece1024. S2 piece1024 is PARTIAL by rule (0.66, n = 6, trial CI 0.33 to 0.98).
- **H2 is rejected by the step evidence.** Of the arrivals that came during the action's prefill, only 3 to 6 % (mono11k)
  and 0 % (pieces) got their first token in one of the action's own steps. Other prefill inside the action's steps
  comes only from requests already queued before the action's last chunk was scheduled.
- **Two channels beyond rho = 1:**
  - **Front-end window ("pre_fe").** Arrivals during the action's front-end preprocessing (0.66 to 0.71 s for
    mono11k under load, 0.16 to 0.19 s for piece2048, about 0.10 s for piece1024) wait the whole engine span. This
    bin carries 22 to 36 % of mono11k's imposed delay and 26 to 57 % of the pieces'.
  - **Post-action catch-up.** The excess over the remaining work grows by 0.034 to 0.042 s per request in flight at
    arrival (mono11k, R^2 0.57 to 0.67). That is about one N=1 episodic prefill in ENG1's step model, so it is the
    catch-up of the queue.
- **ENG1 Part C replication (FIT only):** same verdicts in all 12 cells, rho_b within 0.09 of this run in 10 of 12
  cells.
- **Machine:** GPUs 0, 1 and 3 (other users) were active in 99 to 100 % of samples, so every trial is flagged on
  the GPU criterion and the "without flagged" tables are empty. Host CPU never exceeded 3.1 % (trial mean), so no
  trial is flagged on CPU and the CPU-unflagged tables equal the main tables.

## 1. Design (as pre-registered; user answers 2026-11-17, points 1 to 6)

- Stack: StudyENG1 Part C E0 exactly (Qwen3-VL-32B-Instruct @0cfaf481, vLLM 0.31.0, StudySLICE1 E0 flags, prefix
  caching ON, --enable-log-requests, --enable-logging-iteration-details, the fixed ENG1 stat-logger plugin). The
  flag list is compared at every server start with ENG1's server C_P40_E0 and must be identical. No host tier.
- Loaded cells: loads P25 / P40 / S2 / S4 (ENG1 Part C generator; trace, injection-time and clip seeds = ENG1's +
  900,000) x actions mono11k / piece2048 / piece1024; 20 paired with / without trials per cell, independent repeat of
  the without run on the first 3 FIT trials; HOLDOUT 5 of 20 per cell, written before any run
  (`eng1d_holdout_split.json`, 07:55:20), recorded and not analysed.
- Unloaded control: ENG1 Part B procedure, mono11k and piece2048, offsets 25 / 50 / 75 % of D_L after the long
  request's submission, 5 repetitions.
- Caching: every background image and every mono11k history carries a per-run uuid namespace, so background requests
  and mono11k are cold in both arms; pieces run on their own ~11k prefix built in the setup of the same run (cached on
  GPU, about 10,900 cached tokens); 0 cached-token mismatches between paired arms are required (the run stops on any).
- rho_b (PRIMARY) = (TTFT with - TTFT without) / (time from the request's arrival to the end of the action's last
  prefill step, with-arm). rho_a (SECONDARY) = same numerator / (remaining action prefill tokens at arrival x the
  action's unloaded per-token prefill time). Arrival = client submit. Offset = fraction of the action's engine prefill
  span (scheduled to last prefill step end); "pre" (before scheduling, i.e. during the action's front-end work) and
  "post" bins get no rho but count in the total imposed delay.
- Decision rule (rho_b, offsets 25 to 75 %, pieces' 75-100 % bin excluded): median >= 0.8 H1 (serial blocking under
  load); median <= 0.6 with other work in >= 50 % of the action's steps H2 (load-dependent admission); else PARTIAL.
- Gates: unloaded control within ENG1 Part B p10 to p90 widened by 0.05 (mono11k 25 / 50 / 75 %, piece2048 25 %);
  P40 mono11k FIT median total imposed delay within ENG1 Part C FIT p10 to p90 (22.5 to 64.4 s).

### 1.1 Implementation notes decided after the smoke (before the sweep)

1. **Exclusivity monitor race (first smoke VOID at 07:56:23).** The shared monitor lists processes before it builds our
   process tree; py-cpuinfo's start-up probe (`<our venv>/site-packages/cpuinfo/cpuinfo.py --json`, a child of our
   own vLLM start) exited in between and was reported as "ours outside the job". GPU 2 was exclusive throughout (GPUs
   0 and 1: another user's training job; GPU 3: another user's vLLM). The runner now uses a copy of the monitor that
   exempts only that probe, only from our venv, only if it has already exited or is inside our tree; any other process
   still VOIDs. The VOID smoke's files are kept as `eng1d_smokevoid1_*`, not used.
2. **Derived step attribution uses the step rows' own first-output tokens.** Each plugin row carries the step's
   context tokens ('it') and the computed prompt tokens of requests whose first output came from that step ('pts');
   other prefill in an action step = pts computed minus the action's computed tokens on its last step.
3. **rho_a's remaining tokens prorate the in-progress step** by the time left in it (counting a mostly finished
   8,192-token step in full made rho_a 0.28 where rho_b was 0.92 on the control). The first action step's duration is
   clamped to start at the action's scheduling time (on an idle engine the previous output row can be seconds
   earlier). After both fixes rho_a, rho_b and ENG1 Part B's rho agree on the control (smoke table below).
4. **The plugin's waiting count is read at the next step boundary after the arrival**: rows exist only at step ends,
   so the row before an arrival inside a 2-s step is stale. It still read 0 at the next boundary for every smoke
   arrival (the stats are taken before requests that arrived during the step reach the scheduler), so it does not
   measure the queue and is reported only as a diagnostic. The client
   in-flight count (submitted, no first token yet) is the primary queue length.
5. **Excess = delta - R_b** is added per request: it separates waiting out the action from the inflated batch step
   that follows.

## 2. Smoke (SMK_E0, 08:00 to 08:03) and mechanism verification

Smoke: server flags identical to ENG1 C_P40_E0; control 2 solo references + 1 repetition per (long, offset); one
FIT pair per action at P40 plus a repeat. 0 cached-token mismatches over 176 compared background requests; derived
token conservation exact (error 0) in all 3 trials and all 6 control injections.

| control (n = 1 each) | rho ENG1 Part B definition | rho_b | rho_a | gate band |
|---|---|---|---|---|
| mono11k 25 % | 0.942 | 0.935 | 0.952 | 0.906 to 1.067 |
| mono11k 50 % | 0.929 | 0.967 | 0.930 | 0.909 to 1.127 |
| mono11k 75 % | 0.847 | 0.925 | 0.932 | 0.869 to 1.122 (outside at n = 1; the gate is the 5-rep median) |
| piece2048 25 % | 0.839 | 0.857 | 0.852 | 0.791 to 0.958 |
| piece2048 50 % | 0.812 | 0.792 | 0.797 | (reported, not gated) |
| piece2048 75 % | 0.579 | 0.578 | 0.580 | (reported, not gated) |

Solo references: episodic 0.135 s (ENG1 0.141), mono11k D_L 2.703 s (ENG1 2.673), piece2048 0.547 s (ENG1 0.564).

**Step 1, causal chain.** FORMULATION.md section Constraints (2, serving feasibility) and Objective make latency per
request the binding term, and the policy's rollout (POLICY_SPEC_v3 section 5.2, tested by StudyT0-fidelity) predicts
the delay an action imposes on other requests from a step model plus an admission rule. The chain tested here: a long
prefill occupies the engine's token budget for its steps (8,192 tokens per step, chunked); a request that arrives
during it either (H1) waits until the action's last prefill step ends, because the running request is scheduled first
and fills the budget, or (H2) is admitted into the action's steps because the budget left after the action's chunk (or
decode slots) takes it; its added TTFT relative to the without-arm therefore equals (H1) or is a small fraction of (H2)
the action's remaining wall time; summed over all arrivals this is the imposed delay T0 compares, so the rollout's
queue representation is right under H1 and must model load-dependent admission under H2.

**Step 2, instantiate each link.**

| causal link | implementing quantity | value in the smoke | varies as expected? | evidence |
|---|---|---|---|---|
| action occupies the budget | derived action tokens per step | mono11k 8,192 + 3,104; piece2048 2,090 in 1 step; piece1024 1,010 | yes, by action | step rows, conservation error 0 |
| other work enters action steps | other prefill tokens / decodes in action steps | mono11k P40: 1,134 other tokens (3 requests) in its last step, 0 in its first; pieces: 0 other prefill, decodes in 1 of 2 piece1024 steps | yes, depends on the step's leftover budget | step rows |
| arrival waits for remaining action work | rho_b per request | mono11k P40, arrivals in the first step: 0.94 to 0.97; in the last step: 1.27 to 2.08 | yes, by offset | per-request rows |
| imposed delay | sum of with - without TTFT | 26.4 s (mono11k), 3.09 s (piece2048), 0.51 s (piece1024) | yes, by action | pairs |
| noise | sum of repeat - without | 0.05 / 0.24 / 1.56 s | the piece1024 repeat had a front-end stall (below) | repeats |

No link is ABSENT or CONSTANT.

**Step 3, one traced unit (P40 mono11k, trial 8, with-arm; times relative to the action's scheduling).** Action
11,296 computed tokens, engine prefill 2.662 s. Step 1: 8,192 tokens, 91 images, 2.155 s, no other prefill, no
decodes. Step 2: 4,238 context tokens = 3,104 action + 1,134 other (three 378-token episodic requests admitted with
the action's last chunk), 35 images, 1.101 s (row interval; includes the admission stall). Background request 24
arrives at offset 0.27 (inside step 1), 8 requests in flight: TTFT with 2.010 s vs without 0.143 s, delta 1.867 s,
remaining action time R_b 1.933 s, rho_b 0.966, rho_a 0.88, waited 3 steps. Request 26 arrives at offset 0.66
(inside step 2), 10 in flight: delta 1.155 s, R_b 0.912 s, rho_b 1.27, excess 0.24 s: it waits out the action's last
step and then shares a batch step with the requests queued behind the action. Requests 17 to 19 arrive 0.07 to 0.11 of
the span BEFORE the action is scheduled (during its ~0.5-s front-end work): delta 2.65 to 2.82 s, larger than the
whole engine span: they reach the engine after the action. Trial total 26.43 s (pre bin 8.21 s from 20 requests).

**Step 4, negative control.** Disabling the mechanism = removing the action: the without-arm repeat gives the null.
Trial totals with the action 26.4 / 3.09 / 0.51 s vs the repeat-minus-without totals 0.05 / 0.24 / 1.56 s. The
piece1024 repeat's 1.56 s is a single front-end stall: background requests 35 to 39 (arrivals 6.2 to 6.6 s) reached
the engine about 0.2 s late while the engine was idle (no step rows, host CPU 2.4 %); so at piece1024 the action's
effect is not distinguishable from noise in this one pair. The full run's 3 repeats per cell quantify this; cells
whose effect is within the repeat noise will be flagged. The unloaded control is the second control: with no load,
rho matches ENG1 Part B (table above).

**Step 5, alternative explanation.** rho_b near or above 1 under load could come from (i) serial blocking behind the
action (H1) or (ii) front-end serialization: the action's body (91 images for mono11k) occupies the API server's
preprocessing and holds back requests submitted during it, independent of engine scheduling. They are separated by
the timing: (ii) acts only before the action is scheduled (the "pre" bin, reported separately), while rho_b is computed
only for arrivals after scheduling, when the front end is free (frontend 'Added' times are logged for every request).
A third alternative, (iii) GPU contention from other users, is excluded because GPU 2 is exclusive; host CPU and PCIe
are shared, so every trial carries the host-CPU and other-GPU flags and the main tables are reported with and without
flagged trials. Note: GPUs 0, 1 and 3 were at 100 % in every smoke sample, so every trial is flagged on the GPU
criterion; the informative split is by host CPU (2.2 to 25.7 %, median 2.6 % in the smoke).

## 3. Run record

| stage | finished | elapsed (h) | result |
|---|---|---|---|
| K_E0 (unloaded control) | 08:09 | 0.03 | gate PASS |
| L_P40_E0 | 08:38 | 0.53 | 60 pairs + 9 repeats; cross-check gate PASS (44.867 s over 15 FIT pairs) |
| L_S4_E0 | 09:08 | 1.03 | 60 pairs + 9 repeats |
| L_P25_E0 | 09:37 | 1.51 | 60 pairs + 9 repeats |
| L_S2_E0 | 10:07 | 2.00 | 60 pairs + 9 repeats |

At every start the server flags were identical to ENG1 C_P40_E0, GPU 2 was idle, and MemAvailable was at least
1,462 GiB. VOID: no. The monitor exemption (section 1.1) never fired in the full run. Cached-token mismatches:
0 / 13,149. HOLDOUT: 60 pairs (6,794 rows) recorded, all in the pre-registered split. The analysis asserts that no
FIT row belongs to a HOLDOUT trial and reads nothing else from HOLDOUT rows.

## 4. Unloaded control (gate) and the rho definitions

5 repetitions per cell; median (p10 to p90 for the gated statistic).

| cell | rho, ENG1 Part B definition | rho_b | rho_a | ENG1 Part B band (gate) | gate |
|---|---|---|---|---|---|
| mono11k 25 % | 0.989 (0.968 to 1.007) | 0.936 | 0.978 | 0.906 to 1.067 | pass |
| mono11k 50 % | 1.013 (0.973 to 1.048) | 0.967 | 0.974 | 0.909 to 1.127 | pass |
| mono11k 75 % | 1.082 (0.966 to 1.163) | 0.941 | 0.948 | 0.869 to 1.122 | pass |
| piece2048 25 % | 0.844 (0.834 to 0.891) | 0.858 | 0.855 | 0.791 to 0.958 | pass |
| piece2048 50 % | 0.825 | 0.798 | 0.806 | (not gated) | |
| piece2048 75 % | 0.707 | 0.633 | 0.650 | (not gated) | |

Solo references: episodic 0.135 s, mono11k D_L 2.639 s, piece2048 D_L 0.551 s. Unloaded per-token prefill time
(engine prefill / computed tokens): mono11k 0.185 ms, piece2048 0.210 ms, piece1024 0.221 ms (from ENG1 Part B solo
pieces, because this control has no piece1024). As expected, rho_a and rho_b agree on an idle engine (within
0.05).

## 5. rho by load x action (FIT, rho_b PRIMARY)

Verdict statistic: rho_b over arrivals at offsets 25 to 75 % of the action's engine span. The CI is a bootstrap over
trials. "admitted" = in-window arrivals whose first token came out of one of the action's own steps.

| cell | rho_b 25-75 % (trial CI 95 %) | n | rho_a 25-75 % | admitted | verdict |
|---|---|---|---|---|---|
| P25 mono11k | 1.257 (1.158 to 1.309) | 72 | 1.518 | 5 / 142 | **H1** |
| P25 piece2048 | 1.113 (0.958 to 1.293) | 11 | 1.121 | 0 / 20 | **H1** |
| P25 piece1024 | 0.821 (0.650 to 0.965) | 7 | 0.902 | 0 / 11 | **H1** |
| P40 mono11k | 1.369 (1.279 to 1.472) | 112 | 2.118 | 15 / 235 | **H1** |
| P40 piece2048 | 1.310 (1.037 to 1.625) | 25 | 1.371 | 0 / 47 | **H1** |
| P40 piece1024 | 1.071 (0.886 to 1.467) | 18 | 1.183 | 0 / 33 | **H1** |
| S2 mono11k | 1.166 (1.154 to 1.174) | 69 | 1.444 | 7 / 136 | **H1** |
| S2 piece2048 | 0.914 (0.870 to 0.955) | 15 | 0.877 | 0 / 27 | **H1** |
| S2 piece1024 | 0.657 (0.325 to 0.979) | 6 | 0.725 | 0 / 15 | **PARTIAL** (rule) |
| S4 mono11k | 1.434 (1.416 to 1.460) | 162 | 2.333 | 10 / 306 | **H1** |
| S4 piece2048 | 1.436 (1.395 to 1.562) | 33 | 1.541 | 0 / 58 | **H1** |
| S4 piece1024 | 0.953 (0.817 to 1.283) | 17 | 1.000 | 0 / 37 | **H1** |

S2 piece1024 is PARTIAL by the pre-registered rule. Its median of 0.66 lies between 0.6 and 0.8, its trial CI spans
0.33 to 0.98, and it rests on 6 arrivals. Its step evidence points to H1: none of its 15 in-window arrivals was
admitted into the piece's step. Its whole span is 0.24 s, against a per-request noise of a few tens of ms. The
cell is underpowered rather than evidence for H2.

rho_a exceeds rho_b everywhere under load (mono11k 1.44 to 2.33). This is expected: under load the action's
remaining wall time is longer than its remaining compute at the unloaded rate, because its steps also carry other
prefill and the admission stalls (section 6). This is why the user made rho_b primary.

### 5.1 By offset bin (rho_b median; excess = delta - R_b, median s)

| cell | 0-25 % | 25-50 % | 50-75 % | 75-100 % | excess 0-25 / 25-50 / 50-75 / 75-100 |
|---|---|---|---|---|---|
| P25 mono11k | 1.118 | 1.194 | 1.393 | 2.958 | 0.23 / 0.25 / 0.32 / 0.41 |
| P40 mono11k | 1.127 | 1.271 | 1.621 | 3.095 | 0.26 / 0.42 / 0.64 / 0.76 |
| S2 mono11k | 1.094 | 1.134 | 1.248 | 2.088 | 0.18 / 0.19 / 0.22 / 0.37 |
| S4 mono11k | 1.249 | 1.347 | 2.135 | 4.327 | 0.56 / 0.58 / 0.98 / 1.05 |
| P40 piece2048 | 1.134 | 1.258 | 1.569 | 1.781 | 0.05 / 0.07 / 0.09 / 0.07 |
| S4 piece2048 | 1.037 | 1.413 | 1.557 | 3.753 | 0.02 / 0.13 / 0.13 / 0.20 |
| P40 piece1024 | 0.838 | 0.914 | 1.476 | 4.078 | -0.04 / -0.01 / 0.04 / 0.08 |
| S4 piece1024 | 0.842 | 1.153 | 0.932 | 2.401 | -0.03 / 0.02 / -0.01 / 0.03 |

rho_b rises with offset because the excess is roughly constant or rising while the remaining span shrinks. In the
75-100 % bin the denominator approaches 0, so rho_b is not a useful statistic there; the excess is the stable
quantity. Pieces' 75-100 % bins are excluded from the verdict, as pre-registered. The other cells' bins are in
`eng1d_results.json` (cells_all, by_bin).

### 5.2 By queue length at arrival (client in-flight count, rho_b over all in-window arrivals)

| cell | 1-2 | 3-5 | 6-10 | > 10 |
|---|---|---|---|---|
| P25 mono11k | 1.04 (14) | 1.16 (35) | 1.30 (56) | 2.14 (37) |
| P40 mono11k | - | 0.97 (11) | 1.13 (60) | 1.71 (164) |
| S2 mono11k | - | 1.10 (31) | 1.16 (75) | 2.28 (30) |
| S4 mono11k | - | 0.94 (1) | 1.25 (61) | 1.59 (244) |
| P40 piece2048 | 0.95 (13) | 1.45 (27) | 1.63 (7) | - |
| S4 piece2048 | 1.37 (12) | 1.50 (40) | 4.37 (6) | - |
| P40 piece1024 | 0.86 (12) | 1.47 (19) | 3.68 (2) | - |
| S4 piece1024 | 0.89 (21) | 1.32 (16) | - | - |

With 1 to 2 requests in flight, rho_b is about 1, the serial value. It rises steadily with the queue.

**Excess vs in-flight count (OLS per cell, all in-window arrivals):** mono11k slope 0.034 (P25), 0.042 (P40), 0.036
(S2), 0.040 (S4) s per request, R^2 0.57 to 0.67, intercepts -0.08 to 0.07 s. Pieces: 0.023 to 0.049 s per request,
R^2 0.12 to 0.92 (fewer arrivals, a narrower in-flight range). For comparison, one N=1 episodic prefill (378 tokens, 1 image) costs about 0.04 s in ENG1's step
model. So each request queued ahead adds about one more prefill to the catch-up after the action.

The plugin's waiting count is not used. It reads 0 at the step boundary after the arrival even when 10 or more
requests are in flight (section 1.1, item 4).

## 6. Step-composition evidence (DERIVED)

DERIVED per step = context tokens minus the computed tokens of other requests whose first output came from that step.
Conservation: 180 / 180 loaded with-arm trials have |sum of derived action tokens - action computed tokens| <= 64
(also 180 / 180 at 512; the error is 0 in all). No trial was excluded.

| cell | action steps (median) | action share of step tokens (median) | other prefill tokens in action steps (median) | steps with other prefill | steps with decodes | engine span (s) |
|---|---|---|---|---|---|---|
| P25 mono11k | 2 | 0.936 | 756 | 0.37 | 0.00 | 2.21 |
| P40 mono11k | 2 | 0.833 | 2,268 | 0.50 | 0.00 | 2.57 |
| S2 mono11k | 2 | 0.907 | 1,134 | 0.50 | 0.00 | 2.34 |
| S4 mono11k | 2 | 0.829 | 2,268 | 0.50 | 0.00 | 2.60 |
| P25 / P40 / S2 / S4 piece2048 | 1 to 2 | 1.000 | 0 | 0.00 to 0.19 | 0.18 to 0.46 | 0.45 to 0.48 |
| P25 / P40 / S2 / S4 piece1024 | 1 to 2 | 1.000 | 0 | 0.04 to 0.29 | 0.42 to 0.61 | 0.24 to 0.26 |

**Reading:** a mono11k prefill is 2 chunks: 8,192 tokens with 91 images, then about 3,100 tokens with 33 images.
The first chunk is never shared. The second carries 2 to 6 other N=1 prefills (378 tokens each). These are the requests
already waiting when the last chunk was scheduled, which are the front-end-window arrivals of section 7. Arrivals
during the first chunk reach the scheduler only after the last chunk has been scheduled (asynchronous scheduling
prepares the next step while the current one runs), so they never share it. Pieces run alone in their own step (action share
1.000 in every cell). The other prefill and decodes counted in a piece's window come from the steps around it
(the admission step before it, and requests queued before it), not from its own step. Under every load, about 94 to 100 % of in-window arrivals
waited out the action. The load-dependent change is the length of the queue that drains after it, not admission
into the action. That is H1.

## 7. Total imposed delay per cell, decomposition, and noise ceiling

Sum over background requests of TTFT(with) - TTFT(without), FIT pairs (n = 15 per cell), median (p10 to p90). Noise
= |sum over requests of repeat - without| on the first 3 FIT trials (median).

| cell | ENG1d total (s) | ENG1 Part C FIT median | ratio | noise | pre_fe share | in-window share | post share |
|---|---|---|---|---|---|---|---|
| P25 mono11k | 16.69 (6.25 to 30.10) | 16.2 | 1.03 | 0.03 | 0.22 | 0.74 | 0.04 |
| P25 piece2048 | 0.653 (-0.02 to 1.73) | 0.49 | 1.33 | 0.04 | 0.57 | 0.41 | 0.02 |
| P25 piece1024 | 0.132 (0.03 to 0.39) | 0.10 | 1.32 | 0.04 | 0.51 | 0.37 | 0.10 |
| P40 mono11k | 44.87 (32.12 to 71.60) | 32.9 | 1.36 | 0.18 | 0.30 | 0.58 | 0.12 |
| P40 piece2048 | 2.00 (0.37 to 4.54) | 0.91 | 2.20 | 0.22 | 0.30 | 0.55 | 0.16 |
| P40 piece1024 | 0.775 (0.11 to 1.71) | 0.39 | 1.99 | 0.07 | 0.33 | 0.45 | 0.20 |
| S2 mono11k | 20.90 (19.01 to 22.27) | 19.0 | 1.10 | 0.08 | 0.36 | 0.61 | 0.03 |
| S2 piece2048 | 0.712 (0.29 to 1.11) | 0.62 | 1.15 | 0.02 | 0.41 | 0.58 | 0.02 |
| S2 piece1024 | 0.110 (0.02 to 0.35) | 0.08 | 1.37 | 0.05 | 0.53 | 0.62 | -0.02 |
| S4 mono11k | 69.87 (63.84 to 76.45) | 71.2 | 0.98 | 0.02 | 0.23 | 0.59 | 0.17 |
| S4 piece2048 | 2.85 (1.98 to 3.60) | 2.57 | 1.11 | 0.07 | 0.26 | 0.52 | 0.21 |
| S4 piece1024 | 0.375 (0.05 to 0.85) | 0.40 | 0.94 | 0.05 | 0.27 | 0.69 | 0.01 |

Shares are of the summed delay over all 15 trials; pre_inj (arrivals before the action was submitted) is the
within-trial control. Its share is 0.00 for mono11k and -0.13 to 0.03 elsewhere (noise), and its median per-request
delta is under 1 ms in every cell (-0.8 to +0.3 ms).

- **Noise ceiling:** mono11k effects are 250 to 3,700x the repeat noise; piece2048 9 to 40x; piece1024 2 to 10x.
  P25 and S2 piece1024 are within about 3x of noise and are flagged.
- **ENG1 cross-check:** the pre-registered cell is P40 mono11k: 44.9 s, inside ENG1's 22.5 to 64.4 s. P40 piece2048
  is 2.2x ENG1's median, the only ratio over 2. It lies inside ENG1's p10 to p90 (0.32 to 2.49). Its new traces
  were more congested where it matters: 4.4 vs 3.2 arrivals per trial in the action's window, median 3 vs 2 in
  flight. The per-arrival blocking is the same (rho_b 1.31 here vs 1.22 in ENG1's FIT replication). So the total
  differs because of the trace draw, not the engine.

### 7.1 Front-end window ("pre_fe", user point 3)

| action | front-end window, action submission to scheduling (median, all loads) | arrivals in it per trial (P40 / S4) | median delta of those arrivals (s) | share of the cell's imposed delay |
|---|---|---|---|---|
| mono11k | 0.66 to 0.71 s (idle ENG1: 0.50 to 0.53 s) | 5.3 / 5.9 | 2.48 to 2.73 | 0.22 to 0.36 |
| piece2048 | 0.16 to 0.19 s | 1.3 / 1.4 | 0.48 to 0.53 | 0.26 to 0.57 |
| piece1024 | 0.10 to 0.11 s | 1.1 / 0.5 | 0.22 to 0.24 | 0.27 to 0.53 |

An arrival in this window is held behind the action twice. First the API server is still parsing and rendering
the action's body (ENG1 section 7: front-end work is serial and scales with body size). Then, once handed over, it
waits for the whole engine span plus the catch-up. Its delta (about 2.5 to 2.7 s for mono11k) is larger than the
engine span itself (2.2 to 2.6 s). The window is 25 to 40 % longer under load than idle, because the background
requests' own bodies also pass through the same front end.

**For StudyPOL4-engine's burst4 question.** The front-end channel exists for every image-bearing action and grows
with the action's image count (0.10 s at 11 frames, 0.18 s at 23, 0.7 s at about 124 images). A burst of 4 N=1 calls puts 4
bodies through the front end back to back. This study does not measure burst4, so it can only say the channel is
real and large for long bodies, not how much of burst4's over-prediction it explains.

## 8. ENG1 Part C replication (FIT only, labelled FIT; HOLDOUT rows dropped before analysis)

The same analysis on ENG1's 2026-11-15 Part C FIT pairs (14 per cell; steps from ENG1's own plugin rows). It is
not an independent sample of the engine (same stack), but it is an independent sample of traces and runs.

| cell | ENG1d rho_b | ENG1 FIT rho_b (trial CI) | ENG1 verdict | ENG1 total (s) |
|---|---|---|---|---|
| P25 mono11k | 1.257 | 1.172 (1.130 to 1.281) | H1 | 16.23 |
| P40 mono11k | 1.369 | 1.292 (1.198 to 1.361) | H1 | 32.92 |
| S2 mono11k | 1.166 | 1.163 (1.159 to 1.178) | H1 | 19.04 |
| S4 mono11k | 1.434 | 1.458 (1.423 to 1.525) | H1 | 71.21 |
| P25 piece2048 | 1.113 | 1.207 (0.806 to 1.362) | H1 | 0.49 |
| P40 piece2048 | 1.310 | 1.220 (1.100 to 1.457) | H1 | 0.91 |
| S2 piece2048 | 0.914 | 0.937 (0.859 to 0.964) | H1 | 0.62 |
| S4 piece2048 | 1.436 | 1.493 (1.458 to 1.584) | H1 | 2.57 |
| P25 piece1024 | 0.821 | 1.056 (n = 5, no CI) | H1 | 0.10 |
| P40 piece1024 | 1.071 | 0.995 (0.851 to 1.161) | H1 | 0.39 |
| S2 piece1024 | 0.657 | 0.606 (0.073 to 0.786) | PARTIAL | 0.08 |
| S4 piece1024 | 0.953 | 0.964 (0.857 to 1.209) | H1 | 0.40 |

Derived conservation on ENG1's rows: 168 / 168. ENG1's totals reproduce its published FIT medians (16.2, 32.9,
19.0, 71.2 for mono11k). Verdicts are identical in all 12 cells, and rho_b agrees within 0.09 in 10 of 12 (the 2 small-n
cells differ by 0.09 and 0.24).

**Reconciliation with StudyPOL4-engine Part 1b section 2A.6.** POL4 estimated rho = delta / (action first token -
arrival) over arrivals from the action's submission onward, which includes the front-end window, on ENG1 Part C FIT
with W25 included. It found mono11k 1.149 (CI 1.123 to 1.206), piece2048 0.969, piece1024 0.679. The same definition
on this study's data gives mono11k 1.262 (trial CI 1.230 to 1.286, 1,057 arrivals), piece2048 1.084 (0.994 to 1.174),
piece1024 0.839 (0.768 to 0.881). On ENG1 FIT without W25 it gives 1.246 / 1.060 / 0.777. Same direction and
ordering. The remaining gap of 0.10 to 0.11 is consistent with POL4 pooling W25, the lightest load, and with its
arrival timestamp. POL4's reading 1 ("blocking exceeds the action's remaining work under load, because the action
lengthens the queue") is confirmed and now measured on fresh traces. Its reading 2 ("short actions: arrivals join the
running batch") is not supported: for pieces, 0 of 248 in-window arrivals joined the piece's step. Their lower rho
comes from the short span and the admission stall around it, not from sharing.

## 9. Machine monitor and flags (user requirement)

1,398 samples at 5 s:
- GPU 0, 1 and 3 had utilization above 5 % in 99.1 / 99.9 / 100 % of samples. These belong to two other users:
  a training job on GPUs 0 and 1, and a vLLM server on GPU 3. GPU 2 had no foreign process at any snapshot.
- Host CPU (all cores) had a median of 2.5 % (p90 2.9 %, max 25.4 % in one sample). The trial-window mean was at most
  3.1 %.
- Load average 2.5 to 6.4. MemAvailable was at least 1,403.7 GiB.

All 180 trials are flagged on the other-GPU criterion and none on the host-CPU criterion. The "without flagged
trials" tables are therefore empty and the "without CPU-flagged trials" tables equal the main ones; both are in
`eng1d_results.json` (`cells_unflagged`, `cells_cpu_ok`). Shared host resources other than CPU (memory bandwidth,
PCIe) are not separately monitored. With CPU at about 2.5 % and the control matching ENG1's 2026-11-15 values (when
only GPU 3 was busy), there is no sign of host contention in the latency data.

## 10. Results consistency check (CLAUDE.md, six checks)

1. **Cross-check against committed measurements.**

| quantity | this run | prior | source | ratio | agree |
|---|---|---|---|---|---|
| solo episodic TTFT | 0.135 s | 0.141 s | ENG1 Part B | 0.96 | yes |
| mono11k solo D_L | 2.639 s | 2.673 s | ENG1 Part B | 0.99 | yes |
| piece2048 solo D_L | 0.551 s | 0.564 s | ENG1 Part B | 0.98 | yes |
| control rho (ENG1 Part B definition), mono11k 25 / 50 / 75 % | 0.989 / 1.013 / 1.082 | 0.982 / 0.997 / 0.974 | ENG1 Part B | 1.01 / 1.02 / 1.11 | yes |
| total imposed delay, 12 cells | see section 7 | ENG1 Part C FIT | ENG1 report section 9 | 0.94 to 2.20 | yes for 11; P40 piece2048 2.20, explained (section 7) |
| loaded rho, POL4 definition, mono11k | 1.262 | 1.149 | POL4 Part 1b section 2A.6 | 1.10 | yes |

2. **Physical plausibility.** mono11k: 11,296 computed tokens in an engine span of 2.2 to 2.6 s under load (2.66 s
   unloaded). That is 4,300 to 5,100 tokens/s including the encoding of 124 images, against StudySLICE1's 2.70 s
   for the same history. The catch-up slope of 0.034 to 0.042 s per queued request matches ENG1's step model (about
   0.04 s per N=1 prefill). No rate is faster than the committed curves.
3. **Distribution sanity.** Spreads are reported for every median: p10 to p90 and trial CIs. The control's rho_b is
   tight within an offset (p10 to p90 range about 0.003 at mono11k 25 %). That is expected for a deterministic idle
   engine with identical inputs, and rho_b varies across offsets and actions, so it is not a constant.
4. **Definition audit.** Loads, actions, trace generator, injection window (3 to 4 s into a 10-s trace) and pairing
   are ENG1 Part C's; only the seeds differ (+900,000). "rho" has three definitions, stated wherever used:
   - ENG1 Part B: wait / (D_L x (1 - offset)), from the long request's submission.
   - rho_b and rho_a (this study): from the action's engine scheduling.
   - POL4 2A.6: from the action's submission to its first token.

   The control shows that ENG1 Part B's rho and rho_b agree on an idle engine.
5. **Claim linkage.** This study bears on CLAIMS C5 through the rollout cost model that T0 / T0b test (POLICY_SPEC_v3
   section 5.2). It supports the model's serial-blocking rule as a lower bound, and it weakens any representation
   of loaded blocking as rho < 1 (sharing). It does not speak to C1 to C4 or C6. FORMULATION.md: Constraints 2
   (serving feasibility, latency) and the Objective's latency term. Nothing measured here is scoped out.
6. **Proxy validity.**
   - Step composition is DERIVED from aggregate step rows. It is valid here: conservation is exact in 180 / 180
     trials, and on the control it reproduces the known chunking.
   - Client in-flight count is the queue proxy. It counts requests submitted but not yet first-token, so it
     includes requests still in the front end; that is the queue an arrival actually waits behind.
   - The plugin waiting count is NOT a valid queue proxy (section 1.1) and is used for nothing.
   - rho_b in the 75-100 % bin is numerically unstable (its denominator approaches 0) and is not used for any verdict.

Result: PASS 6 / 6, with one explained >2x ratio (P40 piece2048, trace draw) and the corrections of section 1.1
disclosed.

## 11. Verdicts

- **H1 vs H2, per load and action:** H1 in 11 of 12 cells. S2 piece1024 is PARTIAL by rule; it is underpowered (n = 6),
  and its step evidence points to H1. H2 is not supported in any cell: under load, arrivals are not admitted into
  the long prefill's steps (3 to 6 % for mono11k, 0 % for pieces).
- **Under load the blocking exceeds serial (rho_b > 1)** for mono11k at every load and for piece2048 at P25, P40 and
  S4. The excess is the catch-up of the queue that built up behind the action, about 0.035 to 0.04 s per request
  ahead.
- **Gates:** both passed. **Noise ceiling:** all mono11k and piece2048 cells are far above noise; P25 and S2
  piece1024 are within 3x.
- **Replication:** ENG1 Part C FIT gives the same verdicts in all 12 cells.
- **HOLDOUT:** 60 pairs recorded and untouched, reserved for StudyT0b.

## 12. Implications (separate from the measurements; not tested here)

1. **The rollout's serial rule (rho = 1 from the action's scheduling) is the right kind of rule, and it is a lower
   bound under load.** Following the pre-registered reading of H1, the model's error does not come from charging a
   blocked arrival for more of the action than it really waits. T0's over-prediction of mono11k (median ratio
   1.48) therefore has to come from elsewhere: how many arrivals the model places behind the action, or how it
   prices the queue after the action. Both are things this study can now quantify.
2. **Three terms describe a loaded long prefill's cost to others, all measured here:**
   - (a) arrivals during the action's front-end window wait for the whole engine span. The window is about 0.7 s
     for a 124-image mono11k under load, against 0.5 s idle.
   - (b) arrivals during the engine span wait for the rest of it.
   - (c) every waiting arrival also pays about 0.035 to 0.04 s per request queued ahead of it in the catch-up.

   Term (c) is the "queue amplification". Its size is about one N=1 prefill per queued request, so it should follow
   from the step model if the catch-up steps are simulated with the queue's actual composition.
3. **The front-end window is a separate serial resource.** It accounts for a quarter to a half of the delay that
   short pieces impose. A model that starts blocking at the action's engine scheduling misses it; one that starts
   at submission (as POL4's estimator does) mixes it into rho.
4. **For StudyT0b:** the 60 HOLDOUT pairs here are a fresh out-of-sample set for the same 12 cells, with every
   step row kept. Nothing in sections 4 to 8 was fitted, so the HOLDOUT is unspent and uncontaminated. If a model
   change is made from these FIT results, it should be frozen before T0b reads the HOLDOUT.

## 13. Files

- `experiments/cost/study_eng1d_loadedblock.py` (new; runner).
- `experiments/cost/study_eng1d_analyse.py` (new; analysis + ENG1 replication).
- `results/cost/study_eng1d/`:
  - Split: `eng1d_holdout_split.json`.
  - Requests: `eng1d_partB_requests_h100nvl.jsonl` (control), `eng1d_partC_requests_h100nvl.jsonl` (loaded,
    including the HOLDOUT rows), `eng1d_frontend_requests_h100nvl.jsonl`.
  - Steps, monitors and meta: `eng1d_steps/*.jsonl.gz`, `eng1d_machine_h100nvl.jsonl`,
    `eng1d_monitor_h100nvl.jsonl`, `eng1d_run_meta_h100nvl.json`.
  - Analysis outputs: `eng1d_results.json`, `eng1d_requests_derived.jsonl`, `eng1d_trials_derived.jsonl` (FIT
    only), `eng1d_eng1_replication.json`.
  - Smoke and VOID smoke: `eng1d_smoke_*` and `eng1d_smokevoid1_*`.
- `reports/study_eng1d_loadedblock.md` (this file).
- `research/EXPERIMENTS.md`, `results/INDEX.md`, `research/STATUS.md` (one insertion each).
