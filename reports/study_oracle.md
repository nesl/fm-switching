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
- dashcam: one alert EPISODE (per-episode on-time attainment unit, D178/D179);
- recall: one QUESTION; single-shot: one QUESTION.
- POOLED bound maximises the count of correct-in-time decisions summed across types, each unit
  worth one (no exchange rate).
- PER-TYPE bounds are each type's single-type maximum computed with the WHOLE GPU devoted to that
  type alone, reported SEPARATELY.
- FAIR (headline): the oracle knows arrivals, deadlines and service times perfectly but, for
  correctness, only the per-TYPE accuracy. A served cloud unit is worth its own type's acc_cloud; an
  unserved unit is worth its own type's acc_device (a within-type expected value per unit, summed
  1:1 across types, never a cross-type weight).
- HINDSIGHT (reference line): per-QUESTION actual outcomes - a served cloud unit is worth 1 iff the
  cloud answer is actually correct, an unserved unit 1 iff the device is actually correct. Knows
  outcomes; an unreachable reference, not the headline.

## Memory levels (D223 (1))
Two levels only: 1x and 0.5x (the real-pool kv0.5r cells). 0.25x is removed; committed 0.25x cells
are kept for provenance and not reported.

## Per-query inputs (committed artifacts only; no reruns)
For each cloud-eligible opportunity q on the trace:
- arrival a_q = t_opportunity; deadline D_q = a_q + L_type (L_dash 1.0, L_rob 3.0, L_ss 2.0 from the
  cell sweep).
- GPU WORK W_q in tokens = uncached prefill tokens + decode (output) tokens, from the request log
  (prompt_tokens, cached_tokens / cached_fraction where present; decode = output_tokens). This is
  the BEST-CASE warm work (maximum cache hit), the minimum any real schedule can do.
- capacity T = the GPU's measured peak uncached-token throughput (cite results/cost/cost_matrix.csv
  / reports/phase1_cost_profiling.md; the exact tok/s and host are recorded in the output). The GPU
  does at most T tokens per second.
- minimum delivery net_q = RTT/2 at the committed link (13.6 Mbit/s / 44 ms RTT, D75); the GPU must
  finish q by D_q - net_q.
- memory eligibility: at 0.5x a query whose required prompt exceeds the level's max prompt is
  INELIGIBLE (x_q = 0).
Service TIME, for the constructive lower bound only, uses the gated D162 model
(first_token_s = 0.0678 + 0.000182 * uncached_prefill + 0.000154 * uncached_queued_ahead; D168
held-out ratio_p50 1.052) with real contention, NEVER the superseded cost_model_gate.json
per_overlap = 0.0380 s per REQUEST (a 247x unit error vs D162's per-token 0.0001536).

## The LP (pooled; per-type is the same LP restricted to one type)
x_q in [0,1] = fraction of q served on cloud; f_{q,t} = GPU-tokens of q spent in slot t of width dt.
  maximize   sum_q v_q * x_q
  s.t.       sum_q f_{q,t} <= T * dt         for all slots t            (capacity)
             sum_t f_{q,t} = W_q * x_q       for all q                   (work if served)
             f_{q,t} = 0  for t outside [a_q, D_q - net_q]               (deadline window)
             0 <= x_q <= 1 ;  x_q = 0 if q memory-ineligible
v_q(FAIR) = acc_cloud(type_q) - acc_device(type_q) (within-type expected gain of serving q); the
device baseline sum_q acc_device(type_q) is added back so oracle_total = device_floor + LP_opt.
v_q(HINDSIGHT) = [cloud correct and device wrong] - [cloud wrong and device right]; negative-value q
are never served (x_q = 0).

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
