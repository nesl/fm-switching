# StudyORACLE LP: build status (2026-11-25, Orin, CPU, no plots)

Progress on the provable upper bound of reports/study_oracle.md. No oracle bound is written to
reports/figures/oracle_results.json yet: per the pre-registration, each stage is verified before any
value is emitted, and D240 keeps 1x and kv0.5r separate throughout.

## Verified
- **Stage 1 (trace W_q):** the committed s4 trace is reproduced on Orin and its fairness digest
  matches the committed `96c1a0b4...`; the warm-prefix minimum work W_q is built from it.
- **Stage 2 (W_q <= logged):** the warm-prefix W_q is <= the logged uncached (prompt_tokens -
  cached_tokens) for every opportunity with a request row - single-shot 356/356, recall 54/54,
  dashcam 9743/9743, zero violations at s4 1x - after correcting the dashcam text charge (the EPG
  42-token scaffold is charged ONCE, not per instant; charging it per instant made W_q exceed the
  logged uncached by 6-14 tokens, which would have broken the lower-bound property and made the
  oracle NOT an upper bound).
- **LP transportation core (`experiments/analysis/oracle/oracle_lp.py`):** the event-breakpoint LP
  (value maximization under one preemptible capacity T, per-unit work and deadline windows) plus the
  greedy-EDF lower bound, with a self-contained UNIT TEST that passes 6 hand-checked cases: exact
  value maximization, Step-2b capacity-binding detection, fractional serving, disjoint-window
  non-competition, greedy <= LP (the relaxation direction), and negative-value units never served.
  This is the correctness-critical piece and it is proven before any real units feed it.

## Remaining (staged, built on the verified core; no bound emitted until each is verified)
- Per-type FAIR valuation: single-shot has clean acc_cloud 0.622 / acc_device 0.548 from the SS2
  box; recall needs acc_cloud wired (device floor 0.371 is in hand) from the committed robot gold
  grading, not the by-deadline mix.
- Dashcam episode max-over-subsets valuation (pre-reg fix 1, D197 per-tier episode-threshold
  accuracies): v_e^dev, v_e^max, gain_e, w_e = min work over improving subsets. This is the piece
  that makes the POOLED bound non-trivial (single-shot or recall alone never bind capacity), and it
  is the one that must be built carefully because a wrong episode-value function silently invalidates
  the bound.
- HINDSIGHT valuation (per-question / per-instant actual outcomes), reported beside FAIR.
- The LP at T and 1.10 x T with the capacity-bind (Step 2b) check; device floor from the same trace;
  per-type (single-type maxima) and pooled; across s4-s7 x {1x, kv0.5r} (D240 separate).
- Per-arm share = (policy - floor)/(oracle - floor) with clustered bootstrap CIs (question / episode
  clusters, 2000 resamples, seed 0).
- Positive control HINDSIGHT >= FAIR >= every arm, and the STOP gate: if any arm's realized units
  exceed its oracle (share > 1) at 1.10 x T, the bound is not a bound - stop and report.

The LP core landing now de-risks the hard correctness dependency; the valuation stages follow on top
of it.

## 2026-11-25 stage progress (D254 (4))

- **Stage 1 (per-type FAIR valuation) VERIFIED** (`oracle_valuation.py`,
  `results/orchestration/live2/oracle/oracle_fair_valuation.json`): single-shot FAIR gain acc_cloud
  - acc_device = 0.621881 - 0.547985 = 0.073896 (SS2 box, n 1042); recall FAIR gain per seed (1x) s4
  0.279582, s5 0.122275, s6 0.491699, s7 0.300000 (kv0.5r within 0.004), from the rung-3
  robot_headline cloud_accuracy_on_served and device_only_accuracy. acc_cloud is "on served" by the
  highest-delivery arm (stated limitation). acc_cloud >= acc_device at every seed; no flags.
- **Stage 2 (dashcam episode max-over-subsets) MACHINERY VERIFIED** (`oracle_dashcam.py`): the
  standing-crossing episode-value function and the exact decisive-instant subset enumeration pass a
  5-case UNIT TEST on hand-built episodes - crash rescue (device misses, cloud detects: gain 1),
  no-crash no-serve (cloud would false-alarm so it is NOT served: gain 0, non-monotonicity handled),
  no-crash suppress (cloud fixes a device false alarm: gain 1), min-work improving subset (picks the
  30-token instant over the 70-token one), and already-correct (gain 0). Built and unit-tested
  BEFORE touching live data, per D254 (4).
- **Still to do in stage 2:** apply the machinery to the live episodes by joining the committed
  DENSE per-instant 32BI (cloud) and 4BI (device) scores (the live2 dense calibration has
  n_unscored_32b = 0, so a cloud score exists for all 42,014 instants) against the D197 episode-level
  thresholds (`dashcam_episodic.thresholds_episode`), FAIR using per-tier episode-threshold expected
  correctness. Then stages 3 (HINDSIGHT), 4 (LP at T and 1.10 x T, per type and pooled, s4-s7 x
  {1x, kv0.5r}), 5 (shares + clustered bootstrap), 6 (positive control + STOP gate). No bound is
  written until each stage verifies.

## 2026-11-25 additional rulings and gates

- **Per-seed robot variance (D254 (4)):** each seed draws only 20 to 25 DISTINCT robot questions, so
  per-seed robot accuracy and FAIR gain vary widely - device accuracy ranges 0.058 (s6) to 0.371
  (s4), while over all 57 distinct questions drawn across seeds it is 0.228. Per-seed recall numbers
  are therefore high-variance and are reported per seed, never pooled across seeds (D240).
- **s6 is a flagged OUTLIER:** its device accuracy 0.058 is a genuine low-tail draw (the device
  answers 1 of its 20 distinct questions correctly, qid 0a99c448..., re-asked 7 times); verified a
  property of the s6 question set, not an extraction error
  (`reports/study_s6_device_accuracy_check.md`). s6 stays in the bound with this single-question flag
  carried into every per-seed table.
- **Dashcam dense cloud-score source (stage 2-live):** the per-instant 32BI cloud score is
  ARM-INDEPENDENT (`reports/study_cloud_score_arm_independence.md`: 278,609 shared instants, >=99.85
  percent exactly equal, decision flips 1 in 278,609 = 0.0004 percent across the D197 cloud
  threshold, representation identical, score invariant to traffic_mix). simplestream (99.9 to 100
  percent coverage of dashcam instants across all 8 cells) is therefore used as the dense per-instant
  cloud-score source; the 5 to 8 instants per cell without a simplestream cloud score are treated as
  device-only (conservative, cannot raise the bound). Stated in every dashcam/pooled bound table.

## 2026-11-25 BOUND WRITTEN (D268-corrected)
- Control PASSES: no share>1; HINDSIGHT oracle >= FAIR oracle (pooled + per seed, within bootstrap CI); share<0 reported as genuine worse-than-device (dashcam), not blocking (user ruling, dashcam verification passed: same instant thresholds both tiers, 0 imputed device scores of 47098, cloud false-alarm excess +5-7pp/seed).
- oracle_results.json = THE BOUND. FAIR conditioned on context sent (recall cloud WITH_HISTORY 0.569 / WITHOUT 0.212 / device 0.258); dashcam on instant-threshold score_cell (device TPR 0.247/TNR 0.741, cloud TPR 0.377/TNR 0.676).
- Pooled-over-seeds (1x): rung3 recall FAIR 0.911 HIND 0.619, ss FAIR 0.990 HIND 0.358, dashcam FAIR -0.402 HIND -0.152, pooled FAIR 0.583 HIND 0.149. Best baseline state-uo pooled FAIR 0.628 (edges rung3: rung3 over-serves dashcam cloud). simplestream recall FAIR -0.146 (D268 fix: stateless serving worse than device).
- Fix: oracle_lp_run.recall_correctness now ORs cloud correctness across arms (cloud correctness is context-dependent, not arm-independent; oracle must credit best achievable), removing an impossible policy>oracle on kv0.5r s6.
