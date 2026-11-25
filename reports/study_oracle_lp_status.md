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
