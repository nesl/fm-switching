# Policy component comparisons and ablations

Status: living record, started 2026-11-17. Covers every comparison of alternatives run since the scheduling-policy design began (2026-11-15). Decision record: `claude/policy_design_log.md`. Specification: `claude/policy_spec_v4.md`.

Scope note: sections A to D compare alternatives for the policy's INPUTS (engine cost model, memory rules, escalation, device stack). Section E lists ablations of the POLICY ITSELF (mechanisms switched off in live runs, T2 to T4), none of which has been run yet. Evidence strength is stated per row: held-back one-shot, out-of-sample, cross-fitted, measured, or in-sample.

Update rule: add a row when a study that compares alternatives lands; move section E rows from planned to done with results.

## A. Engine behaviour and the timing formula (cost model)

| study | alternatives compared | result | evidence strength | implication for the policy |
|---|---|---|---|---|
| StudyENG1 | rebuild in one go vs 2,048-token pieces vs 1,024-token pieces vs host reload vs warm append vs burst of 4 | total delay imposed on others: one go 16.2-71.2 s; 2,048 pieces 0.44-2.57 s; 1,024 pieces 0.08-0.40 s; reload 0.01-0.19 s; append 0.03-0.18 s; burst 0.06-0.60 s | measured, noise from repeats | core motivation: the shape of the work matters |
| StudyENG1 | default engine (E0) vs tuned setting meant to let short requests in (T1) | T1 changes only the 25 %-offset cell (rho 0.78 vs 0.97-1.00) | measured | an engine flag does not solve blocking; a scheduler is needed |
| StudyENG1 | 16 requests separately vs batched | batched costs 0.51 (N = 1) to 0.73 (N = 3) of separate | measured | sub-linear batching must be modelled |
| StudyENG1b | host tier on vs off for a paused, partly built history | reload +0.12 s vs rebuild +2.15 s; P_host 0.999 when the host has room | measured | the host tier is valuable when it has room |
| StudyENG1d | H1 (arrivals blocked for the whole remaining action) vs H2 (arrivals admitted into the action's steps) under load | H1 in 11 of 12 cells; H2 rejected (0-6 % of arrivals inside the action's steps); rho_b 1.17-1.43 mono, 0.91-1.44 piece2048, 0.82-1.07 piece1024 | measured, replicated on ENG1 Part C FIT | the serial blocking rule is right and slightly low (queue catch-up) |
| StudyENG1d | blocking measured from submission vs from scheduling | from scheduling is correct; from submission mixes in the front-end window | measured | explains StudyPOL4 Part 1b's wrong rho ~0.7 |
| StudyT0 to StudyPOL4 | original formula vs + host-KV transfer term, + long-prefill correction, + batching term | on ENG1 Part C FIT: delay criterion 0.64 to 0.76, ranking 0.97 to 0.98, completion error 0.16 to 0.13 | in-sample | keep all three terms |
| StudyPOL4 Part 1b | with vs without the batching term (pol4_nobatch) | keep it: Part 1's penalty sign came from a bug (frame count instead of encoder units) | in-sample, by mechanism | keep |
| StudyPOL4 practice run | original vs fixed formula on ENG1c Part D FIT (unseen setup) | (i-b) 0.33 to 0.62; mono11k within tolerance 0.41 to 0.91; pieces still over-predicted 1.57-1.71x | out-of-sample | fixes generalize to monolithic rebuilds, not to chains |
| StudyPOL5 | pol4 vs + one-step asynchronous scheduling lag vs + one prefill per step | both made FIT worse (piece1024 ratio 1.74 to 2.42 and 3.25); rejected; second rule rested on a misread log field | in-sample | the chain error is not these mechanisms |
| StudyPOL5 | pol4 front-end vs image-aware front-end; host transfer 50.14 GB/s vs 44.69 GB/s plus 53 ms overhead | image-aware front end R^2 0.985 on 58,085 windows; host rate reconciled | measured fits | kept for a later formula version (pol4 remains frozen) |
| StudyT0b | frozen pol4 on chained rebuilds (ENG1c HOLDOUT, 120 pairs) vs single actions (ENG1d HOLDOUT, 60 pairs) | (i-b) 0.61 FAIL vs 0.82 FAIL (0.91 PASS on TTFT); ranking 0.95 / 1.00 PASS; completion error 4 % / 7 % PASS | held-back, one-shot | ranking trustworthy; harm of chains over-stated, so the policy is too cautious with recall jobs; bias runs against pieces |
| StudyPOL6 Part A | inter-piece gaps vs in-step behaviour as the cause of the chain over-prediction | in-step 89 % of the error, gaps 10 %; the engine splits each piece into about 1.8 steps and co-schedules other prefills in them, pol4 does neither | in-sample, diagnostic | gap hypothesis rejected; StudyENG1e measures the in-step mechanism |

## B. Memory: where each history lives

| study | alternatives compared | result | evidence strength | implication for the policy |
|---|---|---|---|---|
| StudyENG1c Part A | host eviction rules: FIFO by store, LRU by any access, LRU by host access only, engine code-reading rule | code-reading rule 92 / 95 (95 / 95 with the observed touch path, post hoc); LRU-any 77; LRU-host-only 83; FIFO 68 | in-sample (rule finalized on this data) | identified the actual rule |
| StudyENG1c Part A | touching a history: host-only vs GPU-resident vs half on each | host-only kept 15 / 15; GPU-resident kept only if served wholly from GPU (12 / 12, else 0 / 3); half on each LOST 0 / 15 | measured | a touch must follow the rule or it destroys the history |
| StudyENG1c Part B | host occupancy vs tokens written since last use, as the predictor of survival | write volume after the history decides it; simulator correct on 298 / 300; older occupancy harmless (20 / 20) | measured | predict from write volume |
| StudyENG1c Part C | per-request cached tokens vs aggregate counters as telemetry | per-request correct at concurrency 1, 4, 8; aggregate fails above 1 | measured | use per-request values; host-warm unstable under concurrent cold rebuilds in a small host window |
| StudyENG1c Part D | cold rebuild in one go vs 2,048 vs 1,024 pieces with the host full | imposed about 14 s vs 6 s vs 3 s; job TTFT 2.2 vs 2.9 vs 3.3 s | measured | pieces cut harm 2-5x for about 1 s of job delay |
| StudyENG1c Part E | host empty vs full | no detectable slowdown (at most +0.5 % step time) | measured | no host-full surcharge |
| StudyRES1 | identified rule vs FIFO, LRU-any, LRU-host-only, occupancy-only, constant cold | rule 0.9946; ties LRU-any 0.9942 (2 differing predictions in 2,573); beats FIFO +0.018, LRU-host-only +0.005, occupancy-only +0.578, constant cold +0.625 | out-of-sample | plain recency bookkeeping on both tiers suffices; treat near-boundary histories as possibly cold |

## C. Escalation: which moments go to the cloud

| study | alternatives compared | result | evidence strength | implication for the policy |
|---|---|---|---|---|
| StudyCTRL1b | always-cloud vs device-only | +0.0899 [+0.036, +0.150] challenge mAP | cross-fitted | the cloud helps on monitoring |
| StudyCTRL1b | five causal triggers vs random | none beat random; positives-only oracle 0.391 below device-only 0.478 | cross-fitted but invalid (score-scale mismatch) | led to D57 (per-tier calibration) |
| StudyCTRL1c | calibration: per-fold cross-fitted vs one common map vs D3-DEV-fitted map | D3-DEV map primary; oracle now above device-only, artefact confirmed | cross-fitted | calibration required |
| StudyCTRL1c | five causal triggers vs random, streaming AP primary | none reliably beats random; one claimed cell (cloud trickle 10 %) not credible; minimum detectable difference 82 to about 290 points of capture | cross-fitted, underpowered | D62: monitoring is capacity-based; better trigger pinned (P14) |
| StudyCTRL1c | StudyE9b device trigger vs random, recalibrated | capture 3-18 % became 12-49 %, not separable from random | cross-fitted | old E9b result superseded |

## D. Device stack

| study | alternatives compared | result | evidence strength | implication for the policy |
|---|---|---|---|---|
| StudyORIN1-dense | Orin 4B (llama.cpp F16) vs H100 4B (vLLM BF16) on detection | challenge AP 0.5735 vs 0.5764, difference CI includes 0; Pearson 0.94 | measured | the Orin is a valid device |
| StudyORIN2-stack | Orin calibration map vs H100 4B map | a 0.1149 / b 1.174 vs a 0.1146 / b 1.141; calibrated Orin minus 32B -0.017 (DEV), -0.016 (dense) | measured | per-stack calibration, small difference |
| StudyORIN2-stack | on-device warm recall: HTTP server re-sending images vs in-process harness | TTFT 1.42 / 3.43 s vs 0.146 / 0.225 s at 11k / 28k | measured, equivalence-checked | the device baseline is the efficient path; re-send path reported as sensitivity |
| StudyORIN3-vllm (running) | llama.cpp vs vLLM on the Orin | pending | | device numbers should not depend on the serving stack |

## E. Ablations of the policy itself (live; none run yet)

Planned (spec v4 sections 12-13; tests T2-T4):
- Baselines: EDF (the base policy); utility-per-cost admission; independently released background work; decomposed best-of-breed controller (B9 with audited fixes); strongest independent cache manager plus good admission (T4); escalate-everything; device-only; tuned engine.
- One core mechanism off at a time: counterfactual scoring (FCFS; closed-form fallback); continuation value (none; tokens-processed proxy); prefix-loss term; feasibility rules; single coordinator; adaptive granularity (monolithic; each fixed size); deficit counters (fixed weights; pure utility; pure constraint); calibration (raw scores); residency bookkeeping (LRU only; offline optimum as upper bound); telemetry-verified vs assumed residency; separate vs merged demand rates.
- Every conditional mechanism on vs off; horizon sweep; memory-capacity sweep (D56).
- Cost-model check on mixed traffic in the live run (D63): predicted vs actual per decision, by traffic mix.

## Patterns so far

1. The shape of the work (one go vs pieces, cold vs warm) is the strongest and best-replicated effect (ENG1, ENG1c, ENG1d, T0b).
2. Simple input rules usually tie complex ones (plain LRU bookkeeping; no trigger beats random). Novelty has to come from the scheduler, not these components.
3. The weakest link is the size of predicted harm for chained piece rebuilds (StudyENG1e and StudyPOL6 in progress; live check under D63).
4. Several early conclusions were overturned by better-designed checks (StudyPOL4's batching sign, the rho ~0.7 estimate, the inter-piece gap hypothesis, the Orin "1 log unit" offset), so held-back data and pre-registration are earning their keep.
