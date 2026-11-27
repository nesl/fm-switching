# StudyORACLE feasibility: feasibility-aware bound, capacity window, infeasibility counts

Status: analysis note, CPU, committed data, read-only. Not a new study. Recorded in the StudyORACLE row of research/EXPERIMENTS.md (addendum). No plots. Output: results/orchestration/live2/oracle/oracle_feasible_bound.json (new file). Committed oracle files were not overwritten.

## 1. Why the capacity constraint never binds (oracle_lp_d270)

- Capacity: one preemptible rate T = 17,945.2 tok/s (oracle_lp_run.py:30, D230 (12) measured peak), applied per time slot as sum of flows <= T x slot width (oracle_lp.py:78-89).
- Per-unit work W (oracle_lp.py:8, oracle_lp_run.py:163): robot recall W = min uncached tokens across arms (min_recall_uncached, oracle_lp_run.py:75) + DECODE (2 tokens, line 33). The warmest prefix is charged, so the mean robot W is about 174 tokens. Single-shot W = history tokens + DECODE (line 174), the full context.
- Windows [arrival, deadline - NET] (oracle_lp_run.py:171, 181), NET = 0.022 s (line 31). Each question must fit its own window.
- Total committed demand at the warm charge is about 456k tokens over 1,200 s, against capacity of about 21.5M tokens (T x 1,200 s). Capacity cannot bind in value. Sensitivity check: the pooled LP value is 94.314 for every T from 1,000 tok/s to 1e9, so the pooled capacity_binds flag marks a tight constraint, not a moved objective. The value first falls below about 1,000 tok/s.
- Charge mode: d162_price.py:149 CHARGE_MODE = "uncached-only" (D174 (1)). Policies are charged the same uncached work, so the LP and the policies share one cache-discounted cost model. The LP is therefore consistent with the committed accounting, and under that accounting capacity does not bind.

## 2. Feasibility-aware bound (B_feas): definition and result

Definition. A robot question is cloud-servable only if the best-case first-token time plus RTT plus upload of its question text stays within the 3.0 s recall deadline. Best tier = GPU-WARM (costs.py:106 recall_ttft_s, interpolated linearly in tokens between the 11k and 28k measurements, costs.py:71-76). Prompt size = the question's actual context sent (request log prompt_tokens, the same D268 state). RTT = 0.044 s (v5/cf_ontime_d162.py:53). Upload = 1200 B at 13.6 Mbit/s = 0.71 ms (traces.py:41, fleet/emulator.py:73). A single-shot question is servable only if its best committed cloud completion latency (t_delivered - t_opportunity, min over the committed arms at the condition) is within 2.0 s; a question with no committed cloud latency stays servable and is counted separately. Infeasible questions get oracle value = device floor.

Result (all 106 computed cells, which are the n16 1x and kv0.5r_h0.5 s4 arms):
- Robot rows (one per arm-cell question, summed over the 106 cells): 12,685. Infeasible in isolation under the GPU-WARM best tier: **0**. The best-tier TTFT spans 0.38 to 0.87 s, so no prompt in the committed range is too large for the 3.0 s deadline.
- Single-shot: 0 infeasible, 0 unevaluated.
- Therefore B_feas equals the ideal bound at 1x: no robot question is infeasible on its own at the warm cache tier.

Sensitivity (not the bound): under a cold-tier readiness (no cache hit) the same test marks some robot rows infeasible. The trace-based and rung-3 fractions per condition are in section 2b.

Robot rows infeasible under the cold-tier sensitivity, rung 3:

| cell | robot rows | robot rows infeasible, best tier | robot rows infeasible, cold tier | single-shot rows | single-shot infeasible |
|---|---|---|---|---|---|
| 1x / rung 3 / s4 | 132 | 0 | 77 | 357 | 0 |
| 1x / rung 3 / s5 | 127 | 0 | 78 | 356 | 0 |
| 1x / rung 3 / s6 | 121 | 0 | 66 | 357 | 0 |
| 1x / rung 3 / s7 | 105 | 0 | 61 | 359 | 0 |
| h0.5 / rung 3 / s4 | 132 | 0 | 41 | 357 | 0 |

Limit: the test uses first-token time, as specified. Completion adds decode (about 0.1 s at 2 tokens), so the 3.0 s test is slightly optimistic; a completion-based test would only remove rows, not add any.

### 2b. Cold-tier fraction per condition

Robot questions whose cold-tier first token + RTT + upload exceeds 3.0 s, divided by the robot questions. The left column is computed from the trace population (trace history_tokens, `trace_cold_fraction.py`) and does not depend on any policy. The right column uses each rung-3 cell's own request prompt_tokens; it depends on the policy's own context choice, and rung 3 sends smaller contexts under pressure, so it understates the policy-independent fraction. Both are in `results/orchestration/live2/oracle/cold_tier_fractions.json` (`trace_based` and `conditions`). Seed 4 unless stated.

| condition | trace-based fraction (policy-independent) | rung 3 fraction (depends on the policy's own context choice) |
|---|---|---|
| n16 1x s4 | 74 / 132 = 0.561 | 77 / 132 = 0.583 |
| n16 1x s4 to s7 | 297 / 485 = 0.612 | 282 / 485 = 0.581 |
| h0.5 s4 | 74 / 132 = 0.561 | 41 / 132 = 0.311 |
| n20 s4 (c3-11-2) | 185 / 283 = 0.654 | 123 / 283 = 0.435 |
| n32 s4 (c3-11-2) | 284 / 417 = 0.681 | 109 / 417 = 0.261 |


## 3. Capacity-window bound (B_cap)

Two charges, both committed. Cold charge: every recall re-prefilled with its full history (trace history_tokens + DECODE), greedy feasible schedule at T = 3,800 tok/s (costs.py:81, committed cold rate at 28k) as a lower bound, and LP relaxation at the same rate as an upper bound, for that charge. Warm charge: the committed uncached work at T = 17,945.2 tok/s, LP relaxation.

Capacity fraction alpha = constrained value / uncapacitated value, trace population, seeds 4 to 7, 1x:

| type | alpha, warm charge (UB) | alpha, cold charge LP (UB) | alpha, cold charge greedy (LB) |
|---|---|---|---|
| recall, FAIR | 1.000 | 0.644 | 0.237 |
| single-shot, FAIR | 1.000 | 1.000 | 1.000 |
| pooled, FAIR | 1.000 | 0.779 | 0.541 |

Interpretation, and why the cold-charge bracket is NOT a bound. Under the cold charge the LP relaxation would cap recall at alpha = 0.64, yet the committed rung 3 already reaches a recall FAIR share of 0.91 (pooled 1x). The cold-charge bound would then put rung 3 above its own ceiling. The cold charge assumes no prefix reuse, which the policies exploit, so an upper bound computed under it does not bound them. The valid capacity bound is the warm charge, with alpha = 1.0, which equals the ideal. Capacity therefore does not tighten the ideal bound with any committed quantity. A tighter valid capacity bound needs a measured per-question prefix-hit rate for the cold path, which is new modelling and is not claimed here.

Capacity-window shares (cold-charge scenario, for reference only, NOT a bound; S / alpha):

| arm | recall FAIR (cold-scenario range) | pooled FAIR (cold-scenario range) |
|---|---|---|
| fair-final-rung3 | +1.415 to +3.843 | +1.211 to +1.744 |
| base | +0.390 to +1.061 | +0.706 to +1.017 |
| state-uo | +1.354 to +3.678 | +1.175 to +1.692 |
| simplestream | -0.227 to -0.616 | +0.418 to +0.602 |
| streamscout | -0.218 to -0.593 | +0.422 to +0.607 |

Values above 1 under the cold scenario are the evidence for the point above: the cold scenario is not an upper bound.

## 4. Shares, 1x n16 seeds 4 to 7 pooled, ideal and B_feas (identical at 1x)

Recall, single-shot and pooled (robot + single-shot) shares, FAIR / HINDSIGHT. Pooled weights the two types by their accuracy gain (the pooled share sums each type's gain over the common floor, so the type with larger gain dominates). Positive control: rung 3 pooled FAIR reproduces the committed 0.9438 under the ideal bound.

| arm | recall FAIR / HIND | single-shot FAIR / HIND | pooled FAIR / HIND (ideal) | pooled FAIR / HIND (B_feas) |
|---|---|---|---|---|
| fair-final-rung3 | +0.911 / +0.619 | +0.990 / +0.358 | +0.944 / +0.475 | +0.944 / +0.475 |
| fair-c5attr-rr | +0.909 / +0.624 | +0.990 / +0.358 | +0.943 / +0.478 | +0.943 / +0.478 |
| fair-c5attr | +0.884 / +0.604 | +0.965 / +0.342 | +0.918 / +0.460 | +0.918 / +0.460 |
| state-uo | +0.872 / +0.594 | +0.978 / +0.350 | +0.916 / +0.460 | +0.916 / +0.460 |
| fair-c5attr-gain0 | +0.870 / +0.579 | +0.967 / +0.342 | +0.910 / +0.449 | +0.910 / +0.449 |
| state-uo-c5attr | +0.866 / +0.564 | +0.959 / +0.337 | +0.904 / +0.440 | +0.904 / +0.440 |
| state-shares-r1 | +0.775 / +0.510 | +0.992 / +0.362 | +0.864 / +0.429 | +0.864 / +0.429 |
| state-shares-r2 | +0.740 / +0.455 | +0.985 / +0.354 | +0.841 / +0.400 | +0.841 / +0.400 |
| state-shares | +0.487 / +0.411 | +0.973 / +0.366 | +0.687 / +0.386 | +0.687 / +0.386 |
| base | +0.252 / +0.247 | +0.978 / +0.366 | +0.550 / +0.312 | +0.550 / +0.312 |
| rules | +0.268 / +0.203 | +0.762 / +0.236 | +0.471 / +0.221 | +0.471 / +0.221 |
| streamscout | -0.141 / -0.094 | +0.999 / +0.366 | +0.329 / +0.159 | +0.329 / +0.159 |
| simplestream | -0.146 / -0.119 | +0.999 / +0.366 | +0.326 / +0.147 | +0.326 / +0.147 |
| confidence-cascade | +0.177 / +0.198 | +0.451 / +0.126 | +0.290 / +0.159 | +0.290 / +0.159 |
| llf | +0.051 / +0.050 | +0.542 / +0.134 | +0.254 / +0.096 | +0.254 / +0.096 |
| eco-llm | +0.020 / +0.069 | +0.491 / +0.162 | +0.216 / +0.119 | +0.216 / +0.119 |
| mooncake | +0.051 / +0.045 | +0.391 / +0.122 | +0.191 / +0.087 | +0.191 / +0.087 |
| b7-edf-feasibility | +0.051 / +0.040 | +0.385 / +0.110 | +0.189 / +0.078 | +0.189 / +0.078 |
| edf | +0.032 / +0.030 | +0.196 / +0.020 | +0.100 / +0.025 | +0.100 / +0.025 |
| kvflow-prefetch | +0.034 / +0.030 | +0.106 / -0.012 | +0.064 / +0.007 | +0.064 / +0.007 |
| always-cloud-fcfs | +0.029 / +0.025 | +0.108 / -0.012 | +0.062 / +0.004 | +0.062 / +0.004 |
| querystream-proactive | +0.024 / +0.015 | +0.098 / -0.029 | +0.055 / -0.009 | +0.055 / -0.009 |
| attentionstore-prefetch | +0.028 / +0.025 | +0.085 / -0.037 | +0.052 / -0.009 | +0.052 / -0.009 |
| lmcache | +0.021 / +0.015 | +0.087 / -0.037 | +0.049 / -0.013 | +0.049 / -0.013 |
| warm-all-lru | +0.021 / +0.015 | +0.073 / -0.016 | +0.043 / -0.002 | +0.043 / -0.002 |

Full 25-arm table in the JSON (shares, ideal and B_feas, with bootstrap CIs under "shares").

## 5. h0.5 (kv0.5r_h0.5), s4 only

Pooled FAIR / HINDSIGHT, ideal and B_feas:

| arm | ideal | B_feas |
|---|---|---|
| fair-final-rung3 | +0.679 / +0.325 | +0.679 / +0.325 |
| simplestream | +0.301 / -0.044 | +0.301 / -0.044 |

## 6. Not computed in this pass

- n20 _c3-11-2 (7 cells), n32 _c3-11-2 (8 cells), and the B2 outage/control cells (la-er, la-er-pwire, la-er-cu/cup/cupx, 0b-er; 17 cells in total). Their populations come from a different device count (20 or 32), and oracle_lp_run.build_units and this script hard-code 16 devices. Extending the population needs each cell's own trace parameters (cell.json n_devices and trace settings). The feasibility test itself would transfer unchanged.
- kv0.5r (retired) and dashcam (out of the robot + single-shot scope) are not included.

## 7. Suggested wording (matches the definitions)

Abstract: "Against an ideal-resource bound (every robot and single-shot question answered by the cloud, on time, with no capacity constraint), rung 3 attains 0.94 of the accuracy gain over on-device inference, pooled over robot and single-shot questions at 1x, seeds 4 to 7. The bound is an ideal-resource bound: no committed question is infeasible on its own at the warm cache tier, and the warm-charge capacity bound does not bind. The bound assumes each robot's context stays resident in KV memory, which is not modelled. Without a warm cache, a fraction of robot questions (0.56 to 0.68 by trace across the conditions in section 2b) would miss the 3 s deadline."

Results text: "The 0.94 is the FAIR share of the robot-and-single-shot accuracy gain over on-device inference, against an oracle that serves every question from the cloud with its history, on time and without resource limits. The n20, n32 and h0.5 shares are against a bound known to be loose under pressure."

## 8. Recommendation

- At 1x, headline the ideal-resource bound. It is an upper bound, it equals B_feas here, and the warm capacity bound is non-binding, so the ideal is also the tightest bound this data supports.
- Under pressure (n32, B2 outage), keep the ideal as the upper bound, but report the feasibility count beside it. The ideal is loose under pressure, and the trace-based cold-tier fraction in section 2b is the policy-independent measure of how much of the headroom depends on residency; a cold-charged capacity bound is not valid and is not reported as a bound.
- Do not headline a capacity-window bound until a measured cold-path prefix-hit rate exists for the policies, so that the cold scenario becomes a real bound on them.

## 9. Generalised populations: n20, n32 (tag c3-11-2) and the B2 arms

Method: `experiments/analysis/oracle/oracle_feasible_pop.py N TAG SEEDS`. The cell pattern, the trace call and the trace device mix are read from the cell (tag c3-11-2 is device mix 3:11:2, confirmed by run_meta.json `ratio` and by exact row counts: the trace at N = 20 gives 283 robot and 237 single-shot questions, the rung 3 cell has 283 and 237; at N = 32 the trace gives 417 and 475, the cell 417 and 475). The n16 committed modules are not modified; the substitution is made in the module source at load time.

Scope: n20 and n32 cells exist for seed 4 only, so their shares are seed-4 values. The n16 B2 arms are seed 4 only as well (the arm names listed in section 9.3).

### 9.1 Infeasibility and capacity, per condition

| condition | robot rows | best-tier infeasible | trace cold-tier fraction (rung 3 in parentheses) | capacity alpha, cold greedy (LB) | capacity alpha, cold LP (UB) | capacity alpha, warm LP (UB) |
|---|---|---|---|---|---|---|
| n16 1x (s4 to s7, reference) | 12,685 (all arms, 4 seeds) | 0 | 0.612 (297 / 485; rung 3 0.581) | 0.534 | 0.768 | 1.000 |
| n20 c3-11-2 (s4) | 283 (rung 3) | 0 | 0.654 (185 / 283; rung 3 0.435) | 0.313 | 0.595 | 1.000 |
| n32 c3-11-2 (s4) | 417 (rung 3) | 0 | 0.681 (284 / 417; rung 3 0.261) | 0.333 | 0.575 | 1.000 |

The cold-tier counts are the sensitivity only (no cache hit); they are not bounds. Pooled capacity alphas are seed-4 values for n20 and n32. Raw totals in the JSON files, with what each sums over: n16 cold-tier infeasible rows 2,433 summed over 49 arm-cells at seed 4 (oracle_feasible_pop_n16.json); n20 543 summed over 7 arm-cells (oracle_feasible_pop_n20_c3-11-2.json); n32 396 summed over 6 arm-cells (oracle_feasible_pop_n32_c3-11-2.json); 3,598 summed over all 106 computed cells (oracle_feasible_bound.json). The warm LP is non-binding at every condition; the cold charge binds at every condition, as in section 3.

### 9.2 Shares at n20 c3-11-2 (seed 4): ideal equals B_feas

| arm | pooled FAIR | pooled HIND |
|---|---|---|
| covex-v6-fair-final-la-er-pwire | +0.680 | +0.458 |
| covex-v6-fair-final-la | +0.548 | +0.381 |
| covex-v6-fair-final-la-er | +0.546 | +0.381 |
| covex-v6-fair-final | +0.481 | +0.271 |
| mooncake | +0.307 | +0.232 |
| confidence-cascade | +0.239 | +0.187 |
| simplestream | +0.044 | -0.058 |

### 9.3 Shares at n32 c3-11-2 (seed 4): ideal equals B_feas

| arm | pooled FAIR | pooled HIND |
|---|---|---|
| covex-v6-fair-final-la | +0.302 | +0.174 |
| covex-v6-fair-final-la-er | +0.293 | +0.170 |
| covex-v6-fair-final | +0.165 | +0.077 |
| confidence-cascade | +0.110 | +0.105 |
| simplestream | +0.098 | +0.008 |
| mooncake | +0.025 | -0.004 |

### 9.4 B2 arms at n16 (seed 4 only, default tag)

Rung 3 family, seed 4 only (the four-seed rung 3 pooled share is 0.9438): covex-v6-fair-final-0b-er 0.966; covex-v6-fair-final-la-er 0.939; covex-v6-fair-final-la-er-pwire 0.950; covex-v6-fair-final-la 0.930; covex-v6-fair-final 0.966. B_feas equals ideal for every B2 arm. Full list in `results/orchestration/live2/oracle/oracle_feasible_pop_n16.json`.

Reading. At n20 and n32, the la-er arms and pwire rank above rung 3 on FAIR (n20: pwire 0.680, la-er 0.546, rung 3 0.481). This is a seed-4 comparison of arms on different device mixes and is not a result; it is not yet a paper claim. The feasibility test still changes no question at these conditions at the best tier. Infeasibility at scale appears only through the cache: a cold readiness makes a fraction of robot questions miss the 3 s deadline.

## 10. KV residency (not in the bounds)

Every bound here charges recall prefill as the cheapest committed case: the warm uncached work (ideal and B_cap warm charge) or GPU-WARM first-token time (B_feas). Both assume the robot's prior context is resident in KV memory when the question arrives. None of the bounds models KV capacity, eviction or host-tier spill. The cold-tier sensitivity is the case in which residency fails. Without a cache hit, the trace-based fraction of robot questions that miss the 3 s deadline is 0.61 at 1x (297 of 485, seeds 4 to 7), 0.56 at h0.5 seed 4 (74 of 132), 0.65 at n20 (185 of 283) and 0.68 at n32 (284 of 417). The rung-3 fractions in section 2b are lower, because rung 3 sends smaller contexts; they are not evidence of less dependence on residency, and the policy-independent fraction is the one to report. The host tier size used elsewhere in this project (27 GiB, 110,592 tokens, from the run addendum for the host-tier turnover study) is not an input to these bounds, so any claim that a bound holds under memory pressure needs the residency study first. The paper should state that the bounds assume residency and that the residency assumption is measured separately.
