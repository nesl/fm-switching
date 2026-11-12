<!-- StudyB-baselines. Written for a reviewer: everything faithful to the original is marked FAITHFUL, everything we changed is marked ADAPTATION with its reason. -->
# VideoStorm (NSDI 2017) — case D

**Paper.** H. Zhang, G. Ananthanarayanan, P. Bodik, M. Philipose, P. Bahl, M. J. Freedman,
"Live Video Analytics at Scale with Approximation and Delay-Tolerance", *NSDI 2017*, pp. 377–392.

**Code.** None found. Searched for an official or author-endorsed repository (USENIX page,
Microsoft Research project and publication pages, Princeton SNS group page, GitHub by title and
by author); none links code. No third-party reimplementation is author-linked either, so this is
**case D**: a faithful reconstruction plus an adapted version.

**Files.** `reconstructed/videostorm.py`, `reconstructed/test_videostorm_toy.py`,
`videostorm_adapted.py`.

## The paper's algorithm

| element | where | what it says |
|---|---|---|
| utility | **Eq. (1)**, §6.1 | `U(Q,L) = U^B + α^Q·(Q − Q^M)⁺ − α^L·(L − L^M)⁺`, with `(x)⁺` the positive part. `U^B` is the baseline utility for meeting both goals. |
| no lag bonus | §6.1, Fig. 6 | "there is no bonus for lag being below `L^M`" — the lag term is one-sided. |
| lag prediction | **Eq. (2)**, §6.2.1 | `L_{k,t+T}(a_k,c_k) = L_{k,t} + T − T·a_k/D_k(c_k)`; lag ACCUMULATES when allocation is below demand, which is why the scheduler is formulated as model-predictive control. |
| MaxSum | **Eq. (3)**, §6.2.2 | knapsack variant; greedy approximation preferring the largest `u_k/a_k`, in increments of "a small Δ (say, 1% of a core)", considering all `c_i ∈ P_i` each step. |
| MaxMin | **Eq. (4)**, §6.2.2 | start `a_k = 0`; each step pick `i = argmin_k U_k`, give it Δ, then set `c_i = argmax_c U_i`. |
| placement | §6.3 | mean of three scores in [0,1]: utilization `p` (weighted dot product), load balancing `b = 1 − (M+D)/M_max`, lag spreading `l`; migrate only if the score improves by more than τ. |
| wrong profile | §6.4 | running average mis-estimation `μ = R_k/D_k(c)` enters Eq. (2) as a `1/μ` factor. |

## Mapping, step by step

| paper | our code | note |
|---|---|---|
| `U(Q,L)` Eq. (1) | `reconstructed.videostorm.utility` | FAITHFUL |
| Eq. (2) + §6.4 `μ` | `predict_lag` | FAITHFUL |
| Eq. (3) greedy | `allocate_maxsum` | FAITHFUL |
| Eq. (4) greedy | `allocate_maxmin` | FAITHFUL |
| §6.3 score | `placement_score` | FAITHFUL (unused by the adapted policy: we have one cloud) |
| query `k` | one episodic stream | ADAPTATION A1 |
| profile `P_k` | `profiles.stream_profile` | ADAPTATION A2 |
| capacity `R` | budget GPU-s per wall second | ADAPTATION A3 |
| lag `L_{k,t}` | StudyE9b sample-and-hold shift | ADAPTATION A4 |
| allocation read-back | `a_k>0` and a cloud configuration ⇒ cloud at that `(c,N)` | ADAPTATION A5 |

## Adaptations, with reasons

- **A1 queries are streams.** VideoStorm's queries are independent video analytics queries with
  configuration knobs; our episodic streams are exactly that, with knobs (cadence `c`, frame
  count `N`). Nothing in Eq. (1)–(4) depends on what the knob physically is.
- **A2 the profile is measured, not profiled online.** §5's greedy profile EXPLORATION runs the
  query at many configurations, which needs inference. We substitute our committed
  resource-quality profile: `Q(c)` from StudyE9b's always-on AP (or StudyE9c's challenge mAP),
  `D_k(c)` = cloud GPU-seconds per wall second, both measured. **Consequence:** the profiler,
  which is half the paper, is not exercised; only the scheduler is.
- **A3 capacity is a GPU-second rate.** The paper allocates CPU cores; we allocate the cloud's
  GPU-seconds per second, which is the resource our budget meters.
- **A4 lag is a delivery shift, not a backlog.** VideoStorm's lag grows when a query is
  under-allocated. Our cloud does not queue per stream in this replay, so the irreducible lag is
  the tier's sample-and-hold shift (StudyE9b): 0.75 s on the device, 0.50–1.50 s on the cloud
  depending on `N` and load. Eq. (2) is still used for the horizon prediction, so a stream
  allocated below its demand still accumulates predicted lag. **This is the largest conceptual
  departure in this card.**
- **A5 recall queries use the documented defaults.** VideoStorm has no stateful jobs, so
  `recall_decision = CLOUD`, FCFS order, LRU host offload — exactly as the task specifies.

## Not reproduced, and why

- §5 profile exploration (needs inference).
- §6.4 multi-transform DAG allocation (our streams are single-transform).
- §6.3 placement and migration (one cloud replica; the function is reconstructed and tested but
  not called by the policy).
- §7's cluster implementation.

## Hyperparameters and provenance

| name | value | from |
|---|---|---|
| `Δ` | 0.01 of capacity | the paper's "1% of a core", §6.2.2 |
| horizon `T` | 10 s | our scheduling epoch scale; the paper says "a short time horizon" and runs "every few seconds" (§6.2) |
| `U^B`, `α^Q`, `Q^M` | 0, 1, 0 | the paper says these are "query-specific and set based on the application" (§6.1) and suggests a template set; ours is the neutral template (utility = quality) so the scheduler is not handed a preference we invented |
| `α^L`, `L^M` | 1 (per second), 0.5 s | same; `L^M` = 0.5 s is our own deadline scale, stated not fitted |
| objective | MaxMin and MaxSum both built | the paper reports both (§8.2.1, §8.2.2) |
