# D190 off-critical-path figures: one claim per figure

All five figures are built by figures/d190/make_figures.py from reports/figures/frontier_data.csv
(built by figures/d190/build_frontier.py, which CALLS the committed scorers rather than
reimplementing any score). Seeds 4 to 7, EP-G rq30 cells, full memory unless stated. Colours and
markers per arm are fixed across figures and are colour-blind-safe (Okabe-Ito and Tol palettes, with
a distinct marker and dash per arm so identity never rests on colour alone). No em dashes. PDF + PNG
beside this file under figures/d190/.

A reading note that governs F1 and F3 together: "on time" is a DELIVERY-TIMING rate (the cloud's
answer arrived within the deadline), NOT a correctness rate. An arm that streams every query to the
cloud reaches a high on-time rate with wrong answers. Robot correctness is the separate
correct-by-deadline accuracy in F3. The two must be read together.

## F1 frontier (F1_frontier)

Claim: across seeds 4 to 7 the covex policy family spans a robot-on-time vs alert-attainment
frontier that the decomposed baselines do not reach on BOTH axes at once WITH correct answers: the
shares arms hold high alert attainment (about 0.65) at moderate robot on-time, the fair and state-uo
+C5 arms hold high robot on-time (about 0.85 to 0.92) near the 0.25 alert target, and the base sits
inside the frontier. The stream-all baselines (simplestream, streamscout) sit at the top-right of
these two timing axes but deliver low-accuracy answers (robot correct-by-deadline 0.14 to 0.29, F3),
so their apparent dominance is a timing artefact and is annotated as such.
Source: reports/figures/frontier_data.csv, columns robot_on_time_frac and
alert_mean_per_episode_attain, 1x rows.

## F2 ablation ladder (F2_ablation_ladder)

Claim: along the rungs base, rules, state (state-uo), state+C5 (state-uo-c5attr), fair (fair-c5attr),
the three D179 pre-registered checks move as the mechanism is added. The rules rung alone fails all
three (alert attainment collapses to about 0.10, it retains almost none of the rung-2 robot gain, and
its worst assistance device falls below 0.90). The state rung restores full robot-gain retention
(about 1.0) and assistance above 0.90; the C5 and fair rungs then lift alert attainment back toward
the base level while holding retention and assistance. Each check is shown per seed, never pooled, so
a per-seed failure cannot hide.
Source: frontier_data.csv columns alert_mean_per_episode_attain,
retention_rung2_gain_over_base, assist_perdev_min, 1x rows.

## F3 baseline comparison (F3_baseline_comparison)

Claim: at the main operating point our arm (fair +C5) is the only arm that clears all three
currencies at once. On robot correct-by-deadline ACCURACY it reaches about 0.50 (with state-uo), well
above the device-only floor, while every decomposed baseline sits at or below that floor (the
stream-all baselines at about 0.20); on assistance within 2 s it holds about 0.96 (above 0.90); and
on alert attainment it holds about 0.44 (above the 0.25 target). The baselines each win at most one
currency and lose the others.
Source: frontier_data.csv columns robot_by_deadline_acc (with device_only_robot_floor),
assist_within2s_pooled, alert_mean_per_episode_attain, 1x rows.

## F4 mechanism, seed 5 (F4_mechanism_s5)

Claim: the shares mechanism works by converting LATE alert deliveries into on-time ones through a
short hold. From engine-flag (state-uo) to +C5 attr to shares, the alert on-time bucket rises from
20 percent to 31 percent to 75 percent while the late bucket collapses from 51 percent to about 1
percent; the unsent bucket stays near a quarter (a capacity limit the hold cannot remove). The hold
that does this is small: the shares arm holds alert instants at p50 about 0.12 s and p90 about 0.22
s, and the two non-shares arms record no share-hold rows at all.
Source: the three seed-5 cells covex-v6-state-uo, covex-v6-state-uo-c5attr, covex-v6-state-shares;
buckets computed with the committed delivery functions (D._committed_delivery, D._within); hold times
from the D179 scorer's hold_times block.

## F5 memory sweep (F5_memory_sweep)

Claim: halving the KV pool (1x to 0.5x) leaves robot on-time and alert attainment essentially
unchanged for every arm that has both cells at seeds 4 and 5, so at this 16-device fleet the KV pool
is not the binding resource. Only base, rules, and the baselines carry a 0.5x cell today; the covex
state, C5 and shares arms have no 0.5x cell yet, and the 0.25x column is added automatically when the
KV025 cells land.
Source: frontier_data.csv, 1x and 0.5x rows at seeds 4 and 5.

## Provenance and known gaps

- Source commit, scorers and build time are in frontier_data_README.md.
- D190 is not yet a row in research/EXPERIMENTS.md (it is named only in the H100 handoff commit
  c9fc3ea). This task's write scope is figures/ and reports/figures/ only, so the EXPERIMENTS row is
  left for the owning box to add; it is flagged here, not silently skipped.
- Unparsable or missing cells are listed in frontier_data_README.md: five preflight-only stubs
  (always-cloud-fcfs s5; covex-v6-state s4, s6, s7; v5-rules s7). covex-v6-state therefore has only
  seed 5 at full memory. kvflow-prefetch is absent; lmcache and streamscout have no seed 7;
  r3-streaming is present but was not in the D190 arm list and is drawn as a baseline.
