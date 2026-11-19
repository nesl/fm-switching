# COVEX v1.2: two-timescale design (job planner for recall, short-horizon dispatch for monitoring)

Status: approved by the user 2026-11-18 for overnight implementation (D125). Amends spec v4 sections 3.5, 6.4, 8.1, 8.3, 8.4 for RC jobs only. SH (monitoring) is unchanged.

## 1. Why

The pilot (StudyLIVE2-pilot, seed 0) and the flash diagnosis series found that v1.0 / v1.1 cannot value recall work.
- A recall answer arrives 1-5 s after the decision, outside the 0.5 s rollout horizon H.
- The continuation value is a saturated 0/1 indicator: a constant 0.0354 at any slack.
- The deficit term never sees a recall outcome inside H.
- The continuation schedule assumes the job has the engine to itself (competing_s = 0).

Patches (the RC tail, A3, B1) moved robot service from 0 of 20 to 3 of 20 at 8 devices, against edf's 11 of 20 (dry run). The root cause is structural: a multi-second job with a deadline is a planning problem, while a monitoring instant is a dispatch problem. Spec 6.4 already intended a per-job continuation schedule; v1.2 implements that intent as an explicit plan.

## 2. Design

### 2.1 Two timescales
- **Dispatch (unchanged):** every 100 ms period (D99), monitoring instants and released units are scored by the existing short-horizon rollout (H = 0.5 s, D98 per-instant SH value).
- **Planning (new, RC only):** each recall question gets a JOB PLAN, chosen once at admission and revised only on re-plan events. The plan is chosen by the same counterfactual rule (fleet-wide DeltaJ against declining), evaluated over the JOB'S LIFETIME, not H.

### 2.2 Candidate plans for question r (deadline D_r, history m_r tokens, believed readiness)
| plan | meaning |
|---|---|
| DECLINE | reference: no cloud work; the device answer stands |
| WARM | answer now (history GPU-warm) |
| RELOAD | answer with a host reload (history believed host-warm) |
| ONE-GO-NOW | rebuild whole, then answer, starting now |
| PIECES(b)-NOW | prefix-chained pieces of b tokens, b in {1024, 2048}, starting now |
| PIECES(b)-LATEST | the same pieces, first piece at the latest safe start t_ls(b) |

The candidate set is limited to plans whose readiness preconditions hold. Piece sizes are the measured ones (D17); no new sizes.

t_ls(b) is the latest first-piece time at which the plan's predicted completion, inflated by the safety factor kappa, still meets D_r. kappa is the q90 ratio of measured to predicted job completion time on committed FIT/DEV data. Its source and value are pre-registered before use. No HOLDOUT is touched.

### 2.3 Evaluating a plan
- Roll the fleet forward from now to T_r = max(D_r, predicted plan completion) + one decision period. The plan's units are executed as RESERVED releases at their planned times. Everything else is under pi_0 (work-conserving EDF, D117), using the same engine model, KV / host bookkeeping, calendar and expected arrivals as spec 6.1.
- Jhat over that window counts:
  - SH per-instant values (D98);
  - the recall answer's omega_RC x u_RC at D_r;
  - every device's deficit term from realised-outcome counters (B1), credited at each opportunity's own deadline;
  - state value at T_r;
  - the backlog at T_r priced by mu.
- DeltaJ(plan) = Jhat(plan) - Jhat(DECLINE). Choose the argmax over feasible plans. Admit only if DeltaJ > 0. Ties keep the cheaper plan in GPU-seconds.
- F3's realistic competing work (the rollout's own busy state) supplies the occupancy the plan sees.

### 2.4 Reservation and dispatch
- An admitted plan's units enter the pending set with planned release times and are released AT those times. Releasing a unit earlier, when the GPU is idle, is allowed only if the short-horizon rollout scores it strictly better.
- Short-horizon SH decisions see reserved future units as calendar items, so their harm to the plan, and the plan's harm to them, is priced.
- v1.1's per-piece release scoring (the source of the 72 % zero ties) does not apply to planned RC units.

### 2.5 Re-planning (never silent deferral)
Re-plan question r when:
(a) a unit completes later than planned and the predicted completion with kappa now exceeds D_r;
(b) verify-on-resume finds prefix loss (D55);
(c) the believed readiness of r's history changes tier.
A re-plan re-runs 2.2-2.3 from the current state with the built prefix (D100). ABANDON (decline the remainder, keep the state value of what is built) is one of its options. Every re-plan is logged with its cause.

### 2.6 What v1.2 supersedes
- For RC: the per-piece continuation value (6.4), the feasibility classes (8.3; the plan's feasibility replaces them) and per-candidate piece sizing (8.4; the size is part of the plan).
- The RC tail (F1) and probabilistic p_finish (F4) are not used in v1.2. Their switches stay, OFF.
- B1 (realised-outcome deficits) and F2 (staleness) stay ON. B2 scaling stays shelved: decide it from v1.2's measured deficit-term magnitudes.

### 2.7 Cost
- Plan evaluation is |plans| (at most 6) long rollouts per recall question. Questions arrive at about 0.01 per second per robot device, so the cost is small on average but spiky. Measure it on seed-0 fleet traces at 16, 32 and 64 devices.
- Plan evaluation may be deferred within the arrival period. It must complete before the next period's dispatch.

## 3. Ablations the paper will report
- planner off (v1.1 behaviour);
- a single fixed plan type (always PIECES(1024)-NOW; always ONE-GO-NOW);
- no LATEST-start option;
- no re-planning;
- kappa = 1 (no safety factor).

## 4. Acceptance (D124 gate)
- Session 2's pre-registered behaviour scenarios pass, including MOT1's measured cells.
- The offline comparison (dry run, seed 0, 4 / 8 / 16 / 32 devices) is at least as good as the best baseline (edf, llf, always-cloud) at every size, on both dashcam and robot measures, labelled screening.
- Speed-ups (D121) are then applied as v1.2-fast: byte-identical decisions to v1.2's reference path.
- Development data only (seed 0, pilot traces, synthetic fixtures). No tuning of omega, targets, H, mu or kappa beyond its pre-registered DEV/FIT source.
