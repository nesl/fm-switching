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

## StudyB-baselines amendment 2 (2026-11-13)

**A4b: L is the configuration's own predicted delivery lag, and Eq. (2)'s recursion is not run
over it.** StudySIM1d section 1.2 showed what A4 cost: our `lag_s` is a CONSTANT hold shift
(0.50-1.00 s), and Eq. (2) is a BACKLOG recursion that adds the whole 10-s horizon each period,
so every cloud configuration was predicted 10.75 s behind and `U_cloud = -10.234` against
`U_local = +0.01043` on a quality gap of +0.0057 - the lag penalty was 1,800x the quality term.
The paper's L is a backlog that GROWS when a query is under-allocated; ours is a property of the
tier. Passing the configuration's own hold shift restores the paper's MEANING of L (how late
this configuration's answers are) instead of running a constant through a recursion that was
written for a quantity that accumulates. `alpha_l` is NOT changed: it stays at the paper's
template value of 1.0, so the correction is in the quantity and not in the weight.
`reconstructed/videostorm.py` keeps Eq. (2) exactly as the paper writes it and uses it whenever
`lag_by_config` is absent.

With the fix, on the StudySIM1d audit cell (balanced, F = 4, deadline 5 s, seed 0):

| configuration | Q | demand (GPU-s/s) | lag L | U = Q - max(L - 0.5, 0) |
|---|---|---|---|---|
| local | 0.01043 | 0.000 | 0.75 | **-0.23957** |
| cloud/32BI_N1@0.25 | 0.01690 | 0.270 | 0.50 | **+0.01690** |
| cloud/32BI_N1@0.5 | 0.01613 | 0.135 | 0.50 | +0.01613 |
| cloud/32BI_N1@1.0 | 0.01439 | 0.068 | 0.50 | +0.01439 |
| cloud/32BI_N3@0.25 | 0.01329 | 0.759 | 1.00 | -0.48671 |
| cloud/32BI_N3@0.5 | 0.01276 | 0.379 | 1.00 | -0.48724 |
| cloud/32BI_N3@1.0 | 0.01173 | 0.190 | 1.00 | -0.48827 |

**A5b: allocate the assigned configuration's DEMAND, not a partial delta, and read back the
CONFIGURATION.** A4b has a second consequence the first run exposed: utility no longer depends on
`a_k`, so the paper's delta-greedy loops stop at once - MaxSum's gain is exactly 0 at the first
step and allocates nothing, and MaxMin spends a single Delta on one query because it feeds the
worst query before testing improvement. In a DISCRETE configuration space the paper's capacity
semantics are kept by allocating each query the DEMAND `D_k(c)` of the configuration it is
assigned, with a configuration feasible only while the total allocated demand stays within `R`,
and by keeping each heuristic's own ordering: MaxMin improves the currently worst-utility query,
MaxSum takes the largest utility gain per unit of demand, and both stop when no feasible
improvement remains. A stream runs on the cloud iff its assigned configuration is a cloud one.
`allocate_maxmin` and `allocate_maxsum` are untouched; `allocate_discrete` is the new function
and is marked ADAPTATION A5b.

One epoch's arithmetic, four streams, R = budget / horizon = 2,664.75 / 10 = 266.475 GPU-s per
wall second: every query starts at `local` (demand 0, U = -0.23957); MaxMin picks the worst
(all tie, so the lowest `qid`), finds `cloud/32BI_N1@0.25` feasible (0.270 <= 266.475) and
improving (+0.01690 > -0.23957) and assigns it; the next worst is the next still-local query,
and so on until all four hold `cloud/32BI_N1@0.25` for a total demand of 1.080 GPU-s/s. MaxSum
reaches the same assignment by gain per unit demand: (0.01690 + 0.23957) / 0.270 = 0.950 per
GPU-s/s for the N1@0.25 step against 1.890 for N1@0.5 and 3.786 for N1@1.0 - it takes the
cheapest step first and then improves each query upwards while capacity allows. At a capacity of
0.3 GPU-s/s only the first query is upgraded and the other three stay local, which is the
capacity constraint doing its job.


## D130 live2 port note, added 2026-11-19 (measurement, not a change to this adaptation)

**Behavioural collapse measured in live2.** On seed 4 at 8 devices over 300 s, once the ignored `order` field is excluded, this arm's ACTION SEQUENCE is byte-identical to: `ekya`, `inar-vl`. The three arms emit the same streams, recall decisions and session actions at every one of 3,001 decision periods.

**The collapse is REGIME DEPENDENT, not structural.** At 16 devices the same arms DIVERGE (ekya and videostorm give different action sequences and different robot delivery, 18 of 21 against 19 of 21), so this is convergence under a non-binding capacity rather than two names for one mechanism.

**Consequence for any leaderboard.** Rows for these arms at a cell where they collapse are NOT independent witnesses, and counting them separately overstates the evidence. The measured count is in `results/orchestration/live2/baselines_published/arm_independence.json`.

`live2/coordinator.py` NEVER READS the action's `order` field: it contains zero references to it, and the two `.order` matches are `self.st.order`, a different object. Any part of this system's scheduling discipline expressed through `order` therefore CANNOT reach a decision in live2. This is a property of the live2 harness, not of the adaptation, and nothing in the adaptation was altered.
