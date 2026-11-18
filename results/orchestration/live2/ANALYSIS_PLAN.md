# Live round 1: analysis plan

**APPROVED 2026-11-17 (D103), user may revisit.** Nothing in this file has been run. It fixes
what will be computed, on which units, with which intervals, before any measured run exists,
because D64 requires the analysis plan to be fixed before the run. Every rule below cites the
decision it comes from.

**D103 ruled on all eight CHOICE items this plan had left open**, and D101 replaced one of them
outright, so the items that were open questions are now decisions: (a) the target sweep grid is
kept and labelled **SENSITIVITY**, with the D71 / D82 starting values as the **headline**;
(b), (c) and (d) are accepted as written; (e) the AP bootstrap is raised to n = 1,000;
(f) no multiplicity correction is applied, with the **PRIMARY family fixed in advance**;
(g) is replaced by **D101** (robots join their first session part-way); (h) the committed E10a
median frame size is for **flash tests only** and a measured run reads per-frame bytes from the
Part-2 encode manifest (D91). **D99** (one fixed 100-ms decision period, coordinator latency
counted) and **D105** (the dense calibration refit, 5-fold cross-fitted by clip and applied
out of fold) are part of the plan as well. The change log at the end of this file records what
each edit changed.

Written by StudyLIVE2-fleet (devices, data, scorer) on flash, CPU only, 2026-11-17. The
coordinator side (arms, engine, run matrix execution) is StudyLIVE2-coord's.

---

## Decision index

One line per decision this plan encodes, with the decision row it implements. The eight items an
earlier draft marked **CHOICE** are now carried by **D101** and **D103**; each one keeps a note
of what it was, so the record shows what was chosen and by whom.

| # | decision | what the plan does | authority |
|---|---|---|---|
| 1 | what a target IS | on-time cloud SERVICE, not correctness | D71 |
| 2 | dashcam target | per device, L = 1.0 s, p = 0.25, minimum 200 instants | D71 |
| 3 | robot target | POOLED over robot devices, L = 5.0 s, p = 0.90, minimum 20 questions per run | D71, D82 |
| 4 | targets are inputs | L and p are grids; every cell is reported; the scorer never selects one | D71 |
| 5 | target sweep grid | L_dash {0.5, 0.75, 1.0, 1.5, 2.0}, p_dash {0.10, 0.25, 0.50, 0.75}, L_rob {2.5, 5.0, 10.0}, p_rob {0.75, 0.90, 1.00}, labelled **SENSITIVITY**; the headline cell is the D71 / D82 starting values | **D103 (a)**, was CHOICE a |
| 6 | capacity | largest fleet size where every eligible dashcam device meets its target AND the robot pool meets its target, reported next to the full ladder and a monotone flag | D64, D82 |
| 7 | dashcam task value | streaming AP over clip-PLAYS completed in the run, cut plays excluded for every arm, play-indexed, paired, pooled across seeds, labelled not comparable to the 300-clip AP | D85 |
| 8 | AP is not re-implemented | StudyE9b's own `ApEngine` / `ap_point` through `metrics.streaming_ap` | D85, repo convention |
| 9 | cadence onto the AP grid | the 0.5-s decision score is held forward one 0.25-s grid point; before a play's first standing answer, StudyE9b's MISSING | **D103 (b)**, was CHOICE b |
| 10 | cross-tier comparability | per-tier calibration maps applied before any mixed-tier score is used, each clip scored with the map from the folds that EXCLUDE it | D57, **D105** |
| 11 | calibration maps | INPUT files; a map is FINAL only if it declares `label: FINAL` and `fit_sample: dense`; an INTERIM map may not score a measured run | D86 |
| 12 | robot task value | accuracy of the STANDING answer; cloud correctness from the cloud's ACTUAL answers on JPEG input | D70, D82 |
| 13 | cache-path split | robot accuracy reported split WARM / COLD from the request log's `cache_path` | D81 |
| 14 | device-only arm | computed from recordings alone, with no run | D65 |
| 15 | device answers | the StudyR1 4B-I x RECENT set, 845 at 32.78 %, restricted to EVAL (602, 31.56 %), with the A6000 / H100 caveat | D87 |
| 16 | device recall cost | the ORIN2 in-process harness, 0.146 s at 11k and 0.225 s at 28k; the server re-send path is used nowhere | D87, repo D61 |
| 17 | cost between those two points | linear interpolation, clamped outside the measured range; DERIVED, and unexercised because no arm waits for the device answer | **D103 (c)**, was CHOICE c |
| 18 | combining the two task values | dashcam AP and robot accuracy are reported SEPARATELY and never summed | **D103 (d)**, was CHOICE d |
| 19 | interval method | paired bootstrap of policy minus baseline on the same resampled units, percentile 2.5 / 97.5, no margins | D64 |
| 20 | resampling units | devices (dashcam), questions (robot pool), label-stratified plays (AP), seeds (across runs) | D64, D82, D85 |
| 21 | AP bootstrap n | **1,000** for the AP difference; 2,000 elsewhere. Measured cost on flash: 0.13 s per AP difference at 120 plays, 0.24 s at 237 plays | **D103 (e)**, was CHOICE e |
| 22 | multiplicity | no correction applied and none claimed; intervals are descriptive. The **PRIMARY family** is fixed in advance: policy vs each of the 7 GPU baselines at the two break sizes, tight memory, 50:50, push-all (block 1). Everything else is labelled **EXPLORATORY** | **D103 (f)**, was CHOICE f |
| 23 | seed handling, reported set | the reported seed set for a main-sweep comparison is **{1, 2, 3}** | **D97** |
| 24 | seed handling, pilot | the pilot seed is 0 and is never used in a reported run; it never sets an entry point | D95 (7), D97 |
| 25 | robot measurability | a size enters a comparison only if its robot pool is eligible at EVERY reported seed; otherwise "robot part not measurable", never a pass; never made measurable by averaging or borrowing across seeds | **D97** |
| 26 | eligibility is pre-GPU | eligibility is a property of the trace and is fixed from traces before any GPU run | **D97** |
| 27 | pilot length | 600 s, the same as a main run | D95 (1) |
| 28 | pilot ladder and arms | policy and EDF at 4, 8, 16, 32, 64; always-cloud FCFS up to EDF's break; EDF + 1,024 pieces around and above the policy's break; policy at mu = EWMA, H = 0.5 s; one roomy policy and EDF run at the tight break size | D95 (3) to (6), D77 |
| 29 | main-sweep fleet-size rule | 5 sizes, from the smallest at which every arm meets its targets to the largest at which every arm fails, about 1.5x spacing, fixed in advance | D77 |
| 30 | pairing mechanism | seeds fix session and clip assignment, start offsets and order identically for every arm | D79 |
| 31 | opportunity identity | every opportunity carries an `opportunity_id` assigned by the trace generator and echoed unchanged | D96 (1) |
| 32 | fairness check | the canonical per-mode fairness digest; a mismatch invalidates the run | D96 (2) |
| 33 | block order and stop points | information order, blocks 0 to 7, STOP for review after blocks 0, 1, 2 and 3 | D79 |
| 34 | correction rule | a changed policy becomes a new version and ALL policy runs are redone; versions are never mixed | D79 |
| 35 | exclusion rules | the eight rules of section 7, applied identically to every arm | D71, D77, D82, D85, D86, D96, D97 |
| 36 | repeats | allowed because caches are isolated per device; counted and declared not independent samples | D84 |
| 37 | diagnostics | the D64 set, always reported | D64, D63, D73 |
| 38 | the stagger, and the part-way join | DASHCAM: the offset is applied in RUN time, window 30 s, and a clip play is never joined part-way (D85). ROBOT: the first session is JOINED PART-WAY at a seeded point in [0, 0.5 x session duration), the device starts at t = 0, a `history_preload` declares what the cloud already holds with no uplink charged, and questions before the join point are not emitted or counted | **D101**, replaces CHOICE g |
| 39 | frame bytes | the committed E10a median per frame, recorded as `frame_bytes_source`, for **flash tests only**; a MEASURED run reads per-frame bytes from the Part-2 encode manifest (D91) and the scorer REFUSES a measured run whose source is not the manifest | **D103 (h)**, was CHOICE h |
| 40 | downlink rate | 13.6 Mbit/s symmetric, with the sensitivity reported | ruling 9 of the StudyLIVE2-fleet brief |
| 41 | decision period | one fixed 100-ms decision period for every arm, events batched per period, separate from H; a cap K on full DeltaJ evaluations per period is reported as a setting if used; the coordinator's own latency is counted and reported, never netted out | **D99** |
| 42 | calibration applied OUT OF FOLD | both maps are Platt-fitted with 5-fold cross-fitting BY CLIP (D6) and each clip is scored, online by the policy and offline by the scorer, with the map from the folds that EXCLUDE it; the scorer takes the fold assignment from the calibration file and REFUSES a FINAL map that carries none | **D105** |

**The eight items that were open, and how each was settled.** Each one records what the choice
was, so a later reader can see what was decided and not only what is now in force.

- **a. The target sweep grid - D103 (a).** D71 fixes the starting values and orders a sweep, but
  names no grid. The grid above is kept and labelled **SENSITIVITY**; the **headline cell is the
  D71 / D82 starting values** (L_dash 1.0 s, p_dash 0.25, L_rob 5.0 s, p_rob 0.90). Every cell is
  still reported and the scorer still never selects one (D71's guard).
- **b. Cadence onto the AP grid - D103 (b).** The decision cadence is 0.5 s (StudyCTRL1c) and the
  AP grid is 0.25 s (StudyE9b), so something must fill the skipped point. **Accepted as written:**
  the 0.5-s score is held forward one grid point, which is StudyE9b's own delivery convention.
- **c. Device recall cost between 11k and 28k tokens - D103 (c).** D87 gives exactly two measured
  points and round 1 needs a cost at every history size. **Accepted as written:** linear
  interpolation, clamped outside the measured range, labelled DERIVED. It is unexercised, because
  no arm waits for the device's answer.
- **d. Whether the two task values may be combined - D103 (d).** **Accepted as written: they are
  not.** The D89 class weights (omega_SH = 1.0, omega_RC = 0.4246) are the ONLINE objective's
  weights, DEV-fitted for the scheduler's own decisions; using them to form one reported score
  would present a fitted weight as a measurement. A D89-weighted sum may appear only beside the
  pair, as a clearly labelled secondary summary.
- **e. The AP difference bootstrap n - D103 (e).** Raised from 200 to **n = 1,000**. AP is
  recomputed on every resample, so the cost was the reason for 200; measured on flash, one AP
  difference at n = 1,000 costs **0.13 s of CPU at 120 completed plays and 0.24 s at 237 plays**
  (against 0.026 s and 0.048 s at n = 200), so the whole primary family of differences is a
  matter of seconds and the old n was not buying anything. Elsewhere the bootstrap stays at
  2,000.
- **f. Multiplicity - D103 (f).** **No correction is applied and none is claimed**; the intervals
  are descriptive (D64). What D103 fixes instead is **which comparisons are primary**, in advance:
  the **PRIMARY family is policy vs each of the 7 GPU baselines at the two break sizes, tight
  memory, 50:50, push-all (block 1)**. Everything else is labelled **EXPLORATORY**. The break
  sizes come from the pilot (block 0) and are an INPUT to the labelling, so the family cannot be
  chosen after a result is seen; `scorer/score.py::classify_family` implements the label and
  refuses to call a comparison PRIMARY on a run header that does not record its memory setting.
- **g. The stagger reading - REPLACED BY D101.** The draft read D83's "staggered seeded offset"
  as an offset in run time for both classes, and recorded the mid-session reading as the
  alternative. **D101 settled it the other way for robots**: each robot joins its first session at
  a seeded point in [0, 0.5 x session duration), starts at t = 0, and the cloud already holds that
  session's earlier frames as COLD history, declared by a `history_preload` that charges no uplink
  time; questions before the join point are not emitted and not counted; later sessions in the
  chain start from zero (D83). Dashcam devices keep the run-time stagger and the complete-play
  rule (D85). The reason is cold-rebuild pressure: starting every history at zero removed the cost
  round 1 exists to test. D101 also ordered the D97 entry points recomputed from traces, which
  section 3.1 now carries.
- **h. Frame bytes - D103 (h).** The committed E10a median stands in for a distribution and is
  allowed for **flash tests only**. A **measured run reads per-frame bytes from the Part-2 encode
  manifest (D91)**, and the scorer **refuses** a measured run whose `frame_bytes_source` is not
  the manifest, rather than reporting uplink timings computed from a median. For the record, the
  E10a interquartile range for Nexar q90 is 49,810 to 75,682 B, so an individual frame's upload
  time is 29 to 44.5 ms rather than the median's 37.6 ms.

**Two further decisions this plan now carries.**

- **D99 - the decision period.** Every arm decides on the same fixed **100-ms decision period**,
  with the events of each period batched; the period is separate from the horizon H (spec 6.1, 9).
  Before the pilot the policy is sped up without changing any decision, verified by an equivalence
  test on small fleets; only if it is still too slow, a cap **K** on how many pending items get a
  full DeltaJ evaluation per period is applied and **reported as a setting**. The target is p99
  decision time under 100 ms at 128 devices on the flash fixture. **The coordinator's own latency
  stays in the results** (M4, spec section 14) and is never netted out; the scorer reports the
  period and the cap in the diagnostics of every run and says when a run header records neither.
- **D105 - the calibration refit, applied OUT OF FOLD.** Both maps are Platt-fitted with **5-fold
  cross-fitting by clip** (D6), and **each clip is scored with the map from the folds that exclude
  it**, online by the policy and offline by the scorer. **The scorer takes the fold assignment
  from the calibration file**, never invents one, and **refuses a FINAL map that carries no fold
  assignment** rather than applying it pooled, because a pooled FINAL map would score every clip
  in fold. The refit itself runs the 32B on the dense Orin set with the stored JPEGs (D91) and the
  exact monitoring request body the live coordinator sends, on the round-1 server configuration,
  against the per-instant labels the streaming AP uses (StudyE9b); the file declares label FINAL
  and fit_sample dense.

---

## 0. What round 1 is for

An early check of the design in a regime where the policy should matter: tight memory, mixed
traffic, load near capacity (D64). It is **not** the paper's results. Co-primary measures:

1. **CAPACITY** - the largest fleet size at which every device meets its targets.
2. **TOTAL TASK VALUE** at fixed fleet sizes.

Both are reported with confidence intervals against each baseline, and **no hard-coded pass /
fail margin exists** (D64). Effect sizes and intervals are measured and interpreted afterwards.

---

## 1. Units, and what is paired with what

| metric | unit of analysis | pairing across arms |
|---|---|---|
| dashcam on-time service | one dashcam DEVICE in one run | same device id, same clip order, same instants (D79) |
| robot on-time service | one QUESTION in the run's robot pool (D82) | same opportunity id |
| dashcam task value | one clip-PLAY completed in the run (D85) | same play id |
| robot task value | one QUESTION | same opportunity id |
| capacity | one (arm, fleet size) cell | same trace per fleet size |

Pairing is exact, not statistical: the seed fixes session assignment, clip assignment, start
offsets and order identically for every arm (D79), and every opportunity carries an
`opportunity_id` assigned by the trace generator and echoed unchanged by the coordinator
(**D96 (1)**), so a repeated clip or session can never be confused with another.

The emulator asserts the pairing by requiring its **fairness digest** to equal the trace's digest
for its mode. The canonical digest (**D96 (2)**) is an order-independent sha256 over sorted event
tuples covering `device_register`, `session_start`, `session_end`, `history_preload` (**D101**),
`history_append`,
`recall_question`, and `monitor_offer` in PULL mode or `monitor_frame` in PUSH mode. In pull mode
frames are EXCLUDED, because which frames exist depends on the arm's pulls, so digesting them
would make an arm that pulls less look like a different experiment. A mismatch stops the scorer.

---

## 2. Targets (inputs, swept, never selected)

| class | L | p | minimum | scope |
|---|---|---|---|---|
| dashcam | 1.0 s delivered | 0.25 of decision instants | 200 instants in the run | PER DEVICE (D71) |
| robot | 5.0 s delivered | 0.90 of questions | 20 questions in the run | POOLED over robot devices (D82) |

A target is **on-time cloud service**, not correctness (D71). A device or pool below its minimum
is excluded from the capacity count and reported. D82 makes the robot target pooled because no
S-EMBER EVAL session holds 20 questions (max 6, median 4, and the same maximum inside any 600 s
window), so a per-device minimum of 20 is unreachable at any run length.

**D71's guard.** Targets may be swept, stricter and looser in both L and p, and **every setting
is reported**. Changing a target because of a result and reporting only the favourable setting is
not allowed. The scorer takes L and p as grids and emits one row per cell; it never selects one.

Sweep grid, **approved as SENSITIVITY (D103 (a))**: L_dash in {0.5, 0.75, 1.0, 1.5, 2.0} s,
p_dash in {0.10, 0.25, 0.50, 0.75}, L_rob in {2.5, 5.0, 10.0} s, p_rob in {0.75, 0.90, 1.00}.
**The HEADLINE is the D71 / D82 starting values** - L_dash 1.0 s, p_dash 0.25, L_rob 5.0 s,
p_rob 0.90 - and every other cell is **sensitivity**, reported under that label.

---

## 3. Capacity

Per arm: **the largest fleet size at which EVERY ELIGIBLE DASHCAM DEVICE meets its own target AND
the ROBOT POOL meets its target** (D64, D82).

Reported alongside, always:

- the whole ladder, every fleet size with met / not met, because a single "largest" number is
  only meaningful next to the ladder;
- whether the ladder is **monotone**. A non-monotone ladder is itself a finding and the single
  number must not be read alone;
- the **worst-served robot device** and the per-device robot distribution (D82);
- which dashcam devices were excluded for being under the 200-instant minimum, and which runs had
  a robot pool under 20 questions and were therefore marked ineligible for the robot part.

**Fleet sizes (D77 as amended by D95).** The pilot uses the policy and EDF at every size, 50:50,
tight memory, uniform links, push-all, fleets 4, 8, 16, 32, 64; it measures where targets start
failing, minutes per run and emulator CPU use, and **pilot results are never reported as round-1
results**. The main sweep then uses **5 fleet sizes, from the smallest at which every arm meets
its targets to the largest at which every arm fails, with 3 sizes between, spaced about 1.5x**.
That rule is fixed now and is not re-chosen after seeing a result.

**PILOT LENGTH IS 600 s, THE SAME AS A MAIN RUN (D95 (1)).** A 180-s pilot cannot exercise what
it is meant to check: the pooled robot count is 4, 5 and 14 questions at 4, 8 and 16 devices, all
below D82's minimum of 20, and no EVAL session ends at all, because the shortest is exactly
300 s, so session chaining (D83) is never exercised. **The pilot seed is 0 and is never used in a
reported run (D95 (7)).**

**MEASURABILITY RULE (D95 (2)).** A fleet size enters the main sweep **only if its robot pool
reaches 20 questions at the main run length**. A smaller size is reported as **"robot part not
measurable"** and is **never** reported as a pass: an ineligible pool cannot satisfy the capacity
conjunct, and recording that as a met target would read an absence of evidence as a success.
**Fleet size 4 is kept as a harness sanity check**, not as a sweep point.

The pooled counts at 600 s over the pilot ladder, **recomputed under D101; design-log row pending (planner will log as D107)**, with the D82 minimum of 20 as the bar. The bold cell
is where each ratio and seed first reaches the bar; the pre-D101 counts are in the report's
amendment-3 section beside these:

| ratio | seed | 4 devices | 8 | 16 | 32 | 64 | enters from |
|---|---|---|---|---|---|---|---|
| 50:50 | 1 | 7 | **23** | 44 | 80 | 153 | 8 |
| 50:50 | 2 | 11 | **23** | 43 | 75 | 154 | 8 |
| 50:50 | 3 | 11 | **23** | 34 | 73 | 148 | 5 |
| 50:50 | 0 | 9 | **20** | 35 | 72 | 165 | 8 |
| 75:25 | 1 | 5 | 7 | **23** | 44 | 80 | 14 |
| 75:25 | 2 | 4 | 11 | **23** | 43 | 75 | 14 |
| 75:25 | 3 | 5 | 11 | **23** | 34 | 73 | 11 |
| 75:25 | 0 | 2 | 9 | **20** | 35 | 72 | 14 |
| 25:75 | 1 | 14 | **30** | 62 | 122 | 235 | 5 |
| 25:75 | 2 | 15 | **30** | 58 | 111 | 218 | 5 |
| 25:75 | 3 | **20** | 28 | 55 | 108 | 226 | 4 |
| 25:75 | 0 | 13 | **27** | 57 | 121 | 248 | 5 |

The "enters from" column is the per-seed entry point over every integer size from 4 to 128, not
only the ladder sizes, which is why it can be smaller than the first bold ladder cell.

**THE RULE (D97).** Robot-pool eligibility is a property of
the TRACE, so it is fixed from traces before any GPU run. **A fleet size enters a main-sweep
comparison only if its robot pool is eligible at EVERY seed that will be reported for that
comparison: seeds 1, 2 and 3.** The pilot (seed 0) only reports which of its sizes were
measurable at seed 0; **seed 0 never sets an entry point**. A size is **never** made measurable
by averaging or borrowing across seeds. This supersedes the two-option choice an earlier draft
left open, and `scorer/score.py::d97_sweep_sizes` and `d97_pilot_labels` implement the two modes;
the pilot function has no entry point to return.

### 3.1 The eligibility table (computed from traces, no server)

Every integer fleet size from 4 to 128, each ratio, 600-s runs, seeds 1, 2 and 3 plus seed 0 for
reference: 1,500 cells. **Recomputed under D101; design-log row pending (planner will log as D107)** in
`results/orchestration/live2/fleet/eligibility_join/robot_eligibility_4_to_128.csv` with the
per-ratio summary alongside; the pre-D101 table stays in `.../fleet/eligibility/` so the two can
be compared. Counting uses the trace generator's own control flow with record construction
skipped, and the equivalence is asserted by test (h). Each row now also carries what the join
removed (`questions_before_join`) and what the cloud already holds at t = 0 (`preloads_emitted`,
`preload_tokens_min / median / max / total`, `join_offset_min / median / max_s`).

The split rule for odd sizes is `n_dashcam = int(round(n_devices * d / (d + r)))` with Python's
**round-half-to-even**, so at 50:50 an odd size does not alternate regularly: 5 gives 2 dashcam
and 3 robot, 7 gives 4 and 3, 9 gives 4 and 5, 11 gives 6 and 5. The table states the actual
split for every size.

| ratio | D97 entry point (seeds 1, 2, 3) | sizes above it NOT eligible at all three | monotone | pooled questions at the entry point (s1 / s2 / s3) | last ineligible size below it | per-seed entry (s1 / s2 / s3) | seed-0 entry (reference only) | dashcam : robot split at the entry |
|---|---|---|---|---|---|---|---|---|
| 25:75 | **5** | none | yes | 23 / 23 / 23 | 4 (14 / 15 / 20) | 5 / 5 / 4 | 5 | 1 : 4 |
| 50:50 | **8** | none | yes | 23 / 23 / 23 | 7 (14 / 15 / 20) | 8 / 8 / 5 | 8 | 4 : 4 |
| 75:25 | **14** | none | yes | 23 / 23 / 23 | 13 (14 / 15 / 20) | 14 / 14 / 11 | 14 | 10 : 4 |

Four things this table settles:

1. **The D101 join did not move any entry point: 5 / 8 / 14 at 25:75, 50:50 and 75:25, exactly as
   before.** The join removes the questions before it and brings every later session forward by
   the same offset, and over a 600-s run the two effects very nearly cancel. What D101 did change
   is WHICH seed binds: seed 3 now enters earlier at every ratio (4 / 5 / 11), so the entry point
   is set by seeds 1 and 2.
2. **Eligibility is monotone in fleet size at every ratio over seeds 1 to 3.** No size above an
   entry point fails at all three seeds, so the non-monotone column is empty. That is an
   EMPIRICAL result for this seed set, not a property to rely on: the scorer still checks each
   size actually chosen, and `d97_sweep_sizes` reports any non-monotone size it finds.
3. **The entry point is still where the fleet first holds FOUR robot devices**, at every ratio: 4
   robot devices give 23 pooled questions at every reported seed and 3 give 14 to 20. So the
   binding quantity is the robot device count, not the fleet size, and the ratio only sets how
   large a fleet that takes.
4. **Seed 0 is no longer the strictest seed.** Before D101 its entry points were 7 / 12 / 20
   against the reported seeds' 5 / 8 / 14; under D101 they are 5 / 8 / 14, the same sizes. That
   changes nothing about the rule - **seed 0 still never sets an entry point (D95 (7), D97)** -
   but the old observation that the pilot seed would have excluded measurable sizes no longer
   holds and must not be repeated.

The **dashcam** minimum still never binds anywhere in the table: the smallest per-device instant
count over all 1,500 cells is 996 against D71's minimum of 200, and **0 of 1,500 cells** has a
dashcam device below it.

**What the cloud already holds at t = 0 (D101).** At each ratio's entry point the four robot
devices arrive holding 0 to 11,101 D2 tokens each (median 3,271 to 6,061 by seed, 15,303 to
20,464 in total), and at 64 devices the per-device maximum is 11,101 to 11,641 tokens with join
offsets spread from 1.3 s to 258.4 s. In **941 of the 1,500 cells** at least one robot joined
inside the first 2-s D2 stride and so held nothing at all, which is the bottom of the intended
spread and not an error. Across the whole table the join removed **36,648 questions** that the
pre-D101 traces would have asked before the join point.

Pool exhaustion, for the D84 repeat rule: the first size at which a clip play repeats is 23
devices at 75:25, 34 at 50:50 and 67 at 25:75, unchanged by D101; **sessions** now repeat from
**73 devices at 25:75 and 109 at 50:50** (before D101: only at 25:75, from 111), because a
joined first session ends sooner and the chain consumes more of the 164-session pool. At 128 devices and 75:25 the fleet still has 1,232 repeated clip
plays over all 300 clips and only 70 distinct sessions, so repeat counts must be read with any
result at the top of the ladder.

---

## 4. Task value

### 4.1 Dashcam: streaming AP over clip-plays (D85)

- Computed with StudyE9b's own `ApEngine` / `ap_point`, imported through
  `experiments/orchestration/sim/metrics.streaming_ap`, **never re-implemented**.
- Unit: the clip-**play**. Plays **cut by the run end are excluded for every arm**, so the play
  set is identical across arms.
- Horizons 0.0, 0.5, 1.0, 1.5 s, on StudyE9b's 0.25 s grid from t = 3.0 s. The decision cadence
  is 0.5 s (StudyCTRL1c), so a standing score is **held forward one grid point**; a grid point
  before a play's first standing answer is StudyE9b's MISSING sentinel.
- Scores are put on one scale first by the **per-tier calibration maps** (D57): the device map
  for a device answer, the cloud map for a cloud answer. **D105:** each clip is scored with the
  map from the **folds that exclude it**, the fold assignment taken from the calibration file; a
  FINAL map with no fold assignment is refused.
- **Labelled in every output: not comparable to the committed 300-clip AP** (D85). A 180 s pilot
  covers at most about 152 clip-plays at 32 dashcam devices and a 600 s run needs about 24
  dashcam devices before it can cover 300 distinct clips, so the 300-clip number cannot be
  computed at the smaller cells at all.
- Pooled across seeds for the summary (D85).
- The Nexar challenge mAP is **secondary** (D58) and is reported under its own name, never mixed
  with streaming AP: StudyE9c records the two differing by 56x in chance level.

### 4.2 Robot: accuracy of the standing answer

- **standing answer = the cloud's answer if delivered within L, else the device's answer.**
- Cloud correctness comes from **the cloud's actual answers** on JPEG input, not from a lookup
  table (D70 consequence 2).
- Reported **split WARM / COLD per arm** from the request log's `cache_path` (D81), with the
  caveat that arms answer the same question through different cache paths so path-dependent
  drift could differ by arm.
- The **device-only** arm is computed from the recordings alone, with no run (D65).
- Device answers are the exact 4B-I x RECENT set StudyR1 used as its device comparator, 845
  questions at 32.78 %, restricted to EVAL: 602 questions, 190 correct, 31.56 % (D87). Caveat
  in every output: produced by the 4B on the A6000 / H100, not the Orin.

### 4.3 What "total task value" is

Dashcam AP and robot accuracy are **reported separately and never summed**. There is no committed
exchange rate between an AP point and a recall-accuracy point; the class weights of D89
(omega_SH = 1.0, omega_RC = 0.4246) are the ONLINE objective's weights, fitted on DEV for the
scheduler's own decisions, and using them to form a single reported score would present a fitted
weight as a measurement. **D103 (d) accepted this as written:** the pair is reported, and a
D89-weighted sum may appear only beside it as a clearly labelled secondary summary.

---

## 5. Intervals

Paired bootstrap of **policy minus each baseline** on the same resampled units. No margins (D64).

| comparison | resampled unit | n |
|---|---|---|
| dashcam on-time service, within a run | dashcam devices | 2,000 |
| robot on-time service and accuracy, within a run | questions in the robot pool | 2,000 |
| dashcam AP | clip-plays, label-stratified | **1,000** (D103 (e); AP is recomputed per resample, measured at 0.13 s per difference over 120 plays and 0.24 s over 237 on flash) |
| anything, across runs | seeds | 2,000 |

Percentile intervals at 2.5 % and 97.5 %. The AP's own clip-stratified bootstrap inside
`ApEngine` (NB = 2,000, seed 0) is reported per arm; the policy-minus-baseline AP difference uses
the play resample above, because the engine's bootstrap is not paired across arms.

**Multiplicity, and the PRIMARY family (D103 (f)).** 7 baselines x 2 memory settings x 5 fleet
sizes is a large comparison family. **No correction is applied and none is claimed**: the
intervals are descriptive (D64) and every output says so. What is fixed in advance instead is
which comparisons are primary:

> **PRIMARY FAMILY:** policy vs **each of the 7 GPU baselines**, at the **two break sizes**,
> **tight memory**, **50:50**, **push-all** - that is, block 1. Nothing else.

**Everything outside that family is labelled EXPLORATORY** in every comparison the scorer emits,
and an exploratory interval is never reported as though it were a primary one. The break sizes
are an INPUT to the labelling, taken from the pilot (block 0), so the family cannot be chosen
after a result is seen; `scorer/score.py::classify_family` carries the rule, and it will not call
a comparison PRIMARY when the run header does not record its memory setting, its ratio or its
mode. The seven baselines are the non-policy arms of D65 as corrected by D90 - `device-only`,
`always-cloud-fcfs`, `edf`, `edf-piece1024`, `edf-piece2048`, `utility-per-cost`, `b9` - of which
`device-only` is scored from the recordings with no run at all (D65).

---

## 6. Seeds, blocks, order and stop points (D79)

Blocks are run in **information order**, and automatic analysis plus a **STOP for review** follows
blocks 0, 1, 2 and 3:

| block | content | seed |
|---|---|---|
| 0 | pilot (D77 as amended by D95): policy and EDF at every size, 50:50, tight, uniform, push-all, fleets 4/8/16/32/64, **600 s**; then always-cloud FCFS up to EDF's break and EDF + 1,024 pieces at 2 to 3 sizes around and above the policy's break; policy at mu = EWMA and H = 0.5 s, every EWMA run logging its time-averaged mu to fix D88's x0.5 and x2; one policy and one EDF run at roomy memory at the tight break size | **0** |
| 1 | tight memory, 50:50, push-all, policy vs all 7 GPU baselines, 2 fleet sizes nearest the break | 1 |
| 2 | the 7 other policy versions (mu x H) at the same sizes | 1 |
| 3 | roomy memory, all arms, same sizes | 1 |
| 4 | the other 3 fleet sizes, both memories, all arms | 1 |
| 5 | blocks 1, 3, 4 repeated | 2 |
| 6 | ratios 75:25 and 25:75 and pull mode; policy plus the 2 strongest core baselines, tight, 2 sizes near the break | 1 |
| 7 | blocks 2 and 6 repeated | 2 |
| - | seed 3 for the blocks whose comparisons are reported | **3, required by D97** |

STOP points are after blocks 0, 1, 2 and 3.

**D97 tightens D79 on the third seed.** D79 made a third seed conditional ("if time allows").
D97 fixes the reported seed set for a main-sweep comparison at {1, 2, 3}, so seed 3 is required
for any comparison whose sizes are claimed under D97. `d97_sweep_sizes` takes the reported set as
a parameter, so if seed 3 is in the end not run, the rule is applied to the set that IS reported
and the entry point is whatever that set gives; what is not allowed is claiming a {1, 2, 3} entry
point while reporting two seeds.

**Correction rule (D79).** If the policy is changed after any block, for a bug or a setting, it
becomes a new version (v1.1, ...) and **ALL policy runs are redone with it**; baselines are not
rerun; versions are never mixed in one comparison; each version and its reason are logged.

Seeds set session assignment, clip assignment, start offsets and order, **identical across arms**.
The trace generator is deterministic in the seed alone given (n_devices, ratio, run_s, stagger_s),
and `tests/test_live2_fleet.py` check (a) asserts it.

---

## 7. Exclusion rules

Fixed before the run. Every exclusion is applied **to every arm**, so no arm is scored on a
different set.

1. **Plays cut by the run end** are excluded from dashcam task value, for every arm (D85).
2. **Dashcam devices under 200 instants** are excluded from the capacity count and reported
   (D71).
3. **A robot pool under 20 questions in the run** marks the run ineligible for the robot part;
   it is reported, and the capacity conjunct cannot be met in that run (D82). Per **D95 (2) and
   D97** such a fleet size does not enter the main sweep at all, is reported as **"robot part not
   measurable"**, and is never reported as a pass. **D97:** the test is applied at EVERY reported
   seed, so a size eligible at some reported seeds and not others is excluded, and a size is
   never made measurable by averaging or borrowing across seeds. The pilot seed 0 labels its own
   sizes "measurable at seed 0" or "not measurable at seed 0" and never sets an entry point.
   Size 4 is retained only as a harness sanity check.
4. **A run whose p99 scheduling lateness exceeds 50 ms is INVALID** and is not scored. This is
   harness validity, not a result threshold: it says the emulator could not keep run-clock time
   at that fleet size on that host.
5. **A run whose fairness digest differs from the trace's digest for its mode is INVALID**: it
   did not see the same event stream as the other arms, so D69 fairness is broken. The digest is
   the canonical one of D96 (2); a LIVE1-port digest may appear only as `live1_trace_digest` and
   is never compared against it.
6. **No measured run may be scored with an INTERIM calibration map** (D86). Until the dense
   refit of both tiers exists, the committed maps in `orin2_calibration.json` are INTERIM and
   serve flash builds and tests only; the scorer refuses. **D105 adds the second half of this
   rule:** a map that declares FINAL must also carry its 5-fold assignment by clip and a map per
   held-out fold, and the scorer refuses a pooled FINAL map rather than scoring every clip in
   fold.
7. **Pilot results are never reported as round-1 results** (D77).
8. **A measured run whose `frame_bytes_source` is not the Part-2 encode manifest is refused**
   (D103 (h), D91). The committed E10a median is allowed for flash tests only.
9. **A run whose `history_preload` count differs from its trace's is refused** (D101): it did not
   start from the same cloud-side holding as the other arms, which is the same kind of break as a
   digest mismatch.
10. Nothing is excluded for being an outlier, a slow run, or an unexpected value.

---

## 8. Repeats are not independent samples (D84)

Devices never share cache entries: every request carries a per-device cache salt and a
multimodal UUID per (device, frame), and this is **verified on the H100 before any measured run**
(a clip repeated on another device must show 0 cached tokens). Repeats of clips and sessions
across devices are therefore allowed. Distinct clips and sessions are assigned first and repeat
only when the pool is exhausted; every play has its own play id; **repeat counts per trace are
reported and the report states that repeats are not independent samples**.

300 Nexar clips and 164 S-EMBER EVAL sessions bound how far a fleet can go before repeating.

---

## 9. Diagnostics reported in every run (D64)

- predicted vs actual per decision and per affected request, **by traffic mix** (D63), through
  the coordinator session's joiner;
- hold / decline rates of recall jobs;
- piece sizes chosen (n, p50, min, max);
- decision latency (p50, p99) from the coordinator's decision log;
- emulator CPU use, wall time, max RSS, and the scheduling-lateness distribution;
- per-device uplink queueing, because a history batch delays the frames offered behind it on the
  same uplink;
- cache-path counts (WARM / COLD) from the request log;
- **the decision period and the coordinator's own latency (D99):** the fixed 100-ms period, the
  cap K on full DeltaJ evaluations per period if one was used, and the decision-time
  distribution. The coordinator's latency is counted in the results and never netted out, and
  the scorer says so when a run header records no period;
- **the D101 join and preload:** the per-device join offsets, how many preloads the run
  presented, and the preload sizes in D2 tokens (min / median / max). A run whose preload count
  differs from its trace's is refused, because a different holding at t = 0 is a different
  experiment;
- every placeholder setting with its value and the words "not tuned" (D73).

---

## 10. Caveats that appear in every output header

1. **D85 / D84** - dashcam AP is over clip-plays, not comparable to the committed 300-clip AP;
   repeats are not independent samples.
2. **D87** - robot device answers were produced by the 4B on the A6000 / H100, not the Orin.
3. **D70** - the wire format is JPEG and S-EMBER q88 parity is not proven within the
   pre-registered +/- 2 pp rule; about 6 % of letters change.
4. **D81** - the prefix-cache path is not output-identical to recompute, so accuracy is split
   WARM / COLD.
5. **D86 / D105** - the calibration maps in use, their sha256, their INTERIM / FINAL label, and
   whether they were applied **out of fold**: a FINAL map must carry its 5-fold assignment by
   clip and each clip is scored with the map from the folds that exclude it.
5b. **D103 (h)** - the `frame_bytes_source`. A measured run must read per-frame bytes from the
   Part-2 encode manifest (D91); the committed E10a median is for flash tests only.
5c. **D101** - robots joined their first session part-way, so the robot pool of a run is not the
   pool the pre-D101 traces produced; the D97 entry points were recomputed under D101; design-log row pending (planner will log as D107).
6. The downlink rate is an **assumption**: no committed downlink exists and the committed
   cloud-latency convention charges the upload only. 13.6 Mbit/s symmetric is used, and the
   sensitivity is reported (1 to 100 Mbit/s moves a 300 B answer delivery by 2.4 ms).

---

## 11. What this plan does not cover

- The arms, the engine, the cost model and the run matrix execution: StudyLIVE2-coord.
- The mixed-link setting, time-varying links and outages: a later round (D75, P6).
- The disk-KV tier: out of round 1, pending Q12 after StudyENG1f-disk (D78).
- The confidence-aware target form (D8): the full evaluation, not round 1 (D71).
- Mechanism verification and the results consistency check of `CLAUDE.md`: they attach to the
  measured runs and must be recorded before any conclusion is written. The flash build has no
  result to check.

---

## 12. Change log

Every edit to this file, what it changed, and the authority for it. The plan is fixed before any
measured run (D64), so this log is how a later reader tells an approved edit from a drift.

| date | edit | authority |
|---|---|---|
| 2026-11-17 | First version, DRAFT FOR USER APPROVAL: units, targets, capacity, task value, intervals, blocks, exclusions, diagnostics, caveats, with eight items marked CHOICE and resolved nowhere. | StudyLIVE2-fleet brief |
| 2026-11-17 | Amendment 2: the D97 robot-measurability rule written into sections 3, 3.1 and 7, with the first eligibility table over sizes 4 to 128 at seeds 0 to 3. | D95, D97 |
| 2026-11-17 | Amendment 3, this edit. Header DRAFT -> APPROVED (D103), user may revisit. (a) the target sweep grid is kept and labelled SENSITIVITY with the D71 / D82 starting values as the headline; (b), (c), (d) accepted as written; (e) the AP-difference bootstrap raised from 200 to 1,000, timed on flash at 0.13 s per difference over 120 plays and 0.24 s over 237; (f) no multiplicity correction, with the PRIMARY family fixed in advance as policy vs each of the 7 GPU baselines at the two break sizes, tight memory, 50:50, push-all, everything else EXPLORATORY; (g) replaced by D101; (h) the E10a median confined to flash tests, a measured run reading per-frame bytes from the Part-2 manifest and refused otherwise. D99 (100-ms decision period, coordinator latency counted) and D105 (dense refit, 5-fold by clip, applied out of fold) added. Section 3.1's eligibility table recomputed under D101. This change log added. | D99, D101, D103, D105 |
