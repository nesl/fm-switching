# StudyORACLE — a provable upper bound on correct-in-time decisions (D220 (2), D228 (2))

PRE-REGISTERED 2026-11-24 before any value is computed. Owner: Orin, offline from committed
traces, no new runs. This file is the formulation and the upper-bound argument; the computed values
land in `reports/figures/oracle_results.json` and `reports/study_oracle_results.md` and must not be
written until this formulation is committed.

## What the oracle is
For each memory level and seed it is the maximum number of CORRECT decisions delivered in time that
ANY cloud-offload schedule could obtain on the SAME committed trace. A policy's position is its
SHARE of the achievable gain over the device-only floor:

    share = (policy_correct_in_time - device_floor) / (oracle_correct_in_time - device_floor)

in the D192 units, per type and pooled.

## Units and objective (D228 (2), user 2026-11-24)
No cross-type accuracy-gap weighting; a cross-type exchange rate is ruled out by D149 (1) and
D177. Units are the D192 units, each worth ONE:
- dashcam: one alert EPISODE (D192 / D197: the episode is correct if the alert is raised at the
  right time on a crash episode and no alert is raised on a no-crash episode, judged from the
  STANDING answer, cloud-if-delivered-else-device, over the episode's up to 21 decision instants);
- recall: one QUESTION; single-shot: one QUESTION.
- POOLED bound maximises the count of correct-in-time decisions summed across types, each unit
  worth one (no exchange rate).
- PER-TYPE bounds are each type's single-type maximum computed with the WHOLE GPU devoted to that
  type alone, reported SEPARATELY.
- FAIR (headline): the oracle knows arrivals, deadlines and service times perfectly but, for
  correctness, only the per-TYPE accuracy. A served cloud recall/single-shot unit is worth its own
  type's acc_cloud, an unserved one its own type's acc_device (a within-type expected value per
  unit, summed 1:1 across types, never a cross-type weight); the dashcam episode is valued by the
  max-over-subsets rule below, using D197 per-tier episode-threshold accuracies.
- HINDSIGHT (reference line): per-QUESTION actual outcomes for recall/single-shot (a served cloud
  unit worth 1 iff the cloud answer is actually correct, an unserved one 1 iff the device is
  actually correct); the dashcam episode by the max-over-subsets rule below on its actual
  per-instant answers. Knows outcomes; an unreachable reference, not the headline.

### Dashcam episode unit: the max-over-subsets rule (fix 1)
The LP values single queries, but a dashcam episode's correctness depends on WHICH of its instants
carry a cloud answer, and serving one bad instant (cloud wrong where device was right) can lower the
episode value, so episode value is NOT monotone in the served set and full-cloud does not provably
dominate every mixed cloud/device subset. I therefore do not use the simpler per-episode binary
(option a); I use the MAXIMUM OVER SUBSETS (option b) for BOTH FAIR and HINDSIGHT, which cannot
undercount any real schedule by construction. Per episode e, from the committed instants:
- v_e^dev = episode value with ALL instants device (no cloud served);
- v_e^max = MAX over every subset S of served instants of the episode value v_e(S)
  (FAIR: the D197 per-tier episode-threshold expected correctness with cloud on S, device elsewhere;
  HINDSIGHT: the actual episode correctness with the actual cloud/device answers on S);
- gain_e = v_e^max - v_e^dev;
- w_e = the MINIMUM work (tokens, as W_q below) over every IMPROVING subset S (v_e(S) > v_e^dev) of
  the total best-case work of the instants in S, each inside its own 1.0 s window.
The episode enters the LP as one unit (variable y_e in [0,1]) worth gain_e for work w_e. Validity:
for any real schedule serving subset S_e of episode e, set y_e = 1 wherever it IMPROVED the episode
(v_e(S_e) > v_e^dev) and y_e = 0 otherwise; that integer solution scores v_e^max >= v_e(S_e) per
episode and spends w_e <= cost(S_e) (w_e is the min work over all improving subsets, so it is no
larger than the work of the particular improving S_e), inside the same windows, hence it is feasible
under the same capacity and its value >= the real schedule's. So the integer optimum, and the LP
relaxation above it, are valid upper bounds. The episode-value function v_e(.) is evaluated exactly
per episode over the relevant subsets (the episode structure makes the decisive instants few, so the
enumeration is small and exact, not sampled).

## Memory levels (D223 (1))
Two levels only: 1x and 0.5x (the real-pool kv0.5r cells). 0.25x is removed; committed 0.25x cells
are kept for provenance and not reported.

## Per-query inputs (committed artifacts only; no reruns)
For each cloud-eligible opportunity q on the trace:
- arrival a_q = t_opportunity; deadline D_q = a_q + L_type (L_dash 1.0, L_rob 3.0, L_ss 2.0 from the
  cell sweep).
- GPU WORK W_q in tokens, FROM THE TRACE GENERATOR, not the request logs (fix 2). Request logs
  cover only what one arm actually sent and 29 cells dropped rows, so a per-arm W_q would not exist
  for every opportunity. The trace (`fleet/trace.py`, deterministic per seed) defines, for every
  opportunity, its question/prompt text and the frames attached to it. The minimum (most favourable
  cache) uncached work is:
      W_q = question_tokens(q) + sum over q's frames NOT already resident in the warmest possible
            prefix of frame_tokens, + the decode (answer) tokens.
  "Warmest possible prefix" = the frames of this session already sent to the cloud on an earlier
  in-window request are charged ZERO (cache hit); only genuinely new frames for q are charged. This
  is a strict lower bound on any arm's uncached work, so it keeps the oracle an upper bound (R2).
  VERIFICATION, recorded in the output: for every opportunity where a request-log row exists, the
  trace-derived W_q must be <= the logged uncached tokens (prompt_tokens - cached_tokens) + decode;
  any opportunity violating this is reported, not silently clamped.
- capacity T = the GPU's measured peak uncached-token throughput = 1 / 0.000182431 = 5481.6 uncached
  tokens/s, the inverse of the committed per-uncached-token GPU-second cost
  GPU_S_PER_UNCACHED_TOK = 0.000182431 (D174), source
  `experiments/analysis/episodic/episodic_lib.py:19` (the same slope as the D162 first-token model's
  per-uncached coefficient 0.000182), measured on host h100nvl serving Qwen3-VL-32B. The GPU does at
  most T uncached tokens per second. The exact value, source file and host are echoed in every
  output file.
- DECODE AT THE PREFILL RATE (fix 3): decode (output) tokens are charged at this same peak prefill
  rate T; real decode is slower than prefill per token, so charging decode at the prefill rate
  understates decode time and therefore keeps the bound an upper bound.
- minimum delivery net_q = RTT/2 at the committed link (13.6 Mbit/s / 44 ms RTT, D75); the GPU must
  finish q by D_q - net_q.
- memory eligibility: at 0.5x a query whose required prompt exceeds the level's max prompt is
  INELIGIBLE (x_q = 0).
Service TIME, for the constructive lower bound only, uses the gated D162 model
(first_token_s = 0.0678 + 0.000182 * uncached_prefill + 0.000154 * uncached_queued_ahead; D168
held-out ratio_p50 1.052) with real contention, NEVER the superseded cost_model_gate.json
per_overlap = 0.0380 s per REQUEST (a 247x unit error vs D162's per-token 0.0001536).

## The LP (pooled; per-type is the same LP restricted to one type)
A "unit" u is a recall question, a single-shot question, or a dashcam EPISODE (the episode's work
w_e and gain_e from the max-over-subsets rule above; its window is the union of its instants'
1.0 s windows). x_u in [0,1] = fraction of u served; f_{u,t} = GPU-tokens of u spent in slot t of
width dt.
  maximize   sum_u v_u * x_u
  s.t.       sum_u f_{u,t} <= T * dt         for all slots t            (capacity)
             sum_t f_{u,t} = W_u * x_u       for all u                   (work if served)
             f_{u,t} = 0  for t outside u's window                       (deadline window)
             0 <= x_u <= 1 ;  x_u = 0 if u memory-ineligible
For recall/single-shot: W_u = W_q, and v_u(FAIR) = acc_cloud(type) - acc_device(type) (within-type
expected gain of serving the question), with the device baseline sum_u acc_device(type) added back
so oracle_total = device_floor + LP_opt; v_u(HINDSIGHT) = [cloud correct and device wrong] - [cloud
wrong and device right]. For a dashcam episode: W_u = w_e and v_u = gain_e (FAIR or HINDSIGHT as
defined), baseline sum_e v_e^dev added back. Negative-value units are never served (x_u = 0).

## Why it is a provable UPPER BOUND (relaxation argument)
R1 x_q in [0,1] vs {0,1}: relaxing integrality can only raise the maximum.
R2 W_q is the minimum (best-case warm) work: a real schedule does at least W_q for q.
R3 net_q is the minimum delivery delay: the widest feasible window; a real window is no wider.
R4 capacity is a flat preemptible T with no batching / context-switch / setup overhead and
   arbitrary splitting: real GPU capacity <= this idealization.
R5 the KV-residency / eviction / host-tier contention constraint is DROPPED (kept only as the
   per-query prompt-length eligibility): dropping a real constraint can only raise the maximum. This
   is the constraint the D223 KV-occupancy study shows binds at 0.5x, so the 0.5x bound is
   deliberately looser.
Every LP constraint is a NECESSARY condition any real schedule satisfies, and every step above
enlarges the feasible region or objective, so LP_opt >= integer_opt >= any realizable schedule.
Hence oracle = device_floor + LP_opt is a valid upper bound. The LP is a continuous
transportation/flow program; it is solved to optimality (solver status recorded).

## Constructive feasible schedule (lower bound; shows looseness)
Greedy EDF against the REAL per-slot capacity using the D162 service time WITH contention: serve
pending queries in deadline order, skip one whose window cannot fit. Its realized correct-in-time
units are a valid LOWER bound on the oracle. The output reports [greedy, LP_opt] per type and
pooled so the gap is visible.

## Outputs and checks
- per seed s4..s7, at 1x and 0.5x; per arm; per type (single-type bounds) and pooled.
- share = (policy - device_floor)/(oracle - device_floor); paired bootstrap CIs clustered by
  question (recall/ss) / episode (dashcam), 2000 resamples, seed 0, pooled across seeds.
- Step 0 (what invalidates): T is the UNCACHED prefill rate; net_q the committed link; LP solved to
  optimality; device_floor from the SAME trace; D162 not the gated-out model.
- Step 2b (does the bound bind): confirm queries are rejected for capacity at 1x and MORE at 0.5x;
  if every query fits, the GPU is not the constraint and the ceiling is trivial - say so.
- positive control: HINDSIGHT >= FAIR >= every arm's realized units, per type and pooled.
- STOP gate: if any ARM's realized units exceed its oracle (share > 1) the bound is not a bound;
  stop and report. If the bound cannot be shown valid, stop and report.
