# Pre-registration: DEV calibration of the three cascade arms' decision thresholds

**Written and committed BEFORE any threshold was computed.** D164 (BASELINE_MATRIX, "AFTER
CALIBRATION") requires each cascade arm's threshold to be set on DEV by its OWN card's procedure,
per confidence type, pre-registered before fitting. User ruling 2026-11-22, priority item 2.

Arms: `confidence-cascade`, `cascade-routing`, `eco-llm`.
Standing rules that bind this work: D6 (fit on DEV, metric on EVAL), D143 A (robot DEV split is
the LH-REQ DEV 28; single-shot DEV is the committed seeded 30/70 per dataset), D168 / D155 (5)
(device-waiting arms read the measured Orin warm latency per question, never the 0.567 s proxy),
D135 (2) / D137 (3) (eco-llm plans with the cost it is charged, on the measured quality table).
Development seeds 0, 4, 5, 6, 7 only. Never EVAL for fitting, never HOLDOUT.

## 0. What this pre-registration will NOT do

Requirement 1 of the ruling is that the calibration method is the one the arm's own card or paper
specifies. Where a card specifies no method for a quantity, or where the quantity the card's
method calibrates against does not exist in live2, **no threshold is invented**: the arm is
reported as not calibratable for that quantity and is NOT marked ready. A refusal is a result
here, not a failure to finish.

## 1. The confidence types that exist

These are signals of different kinds on different scales. A single threshold across them is wrong,
so one threshold is fitted per type. The types, with the committed table each comes from:

| id | signal | source table | key space |
|---|---|---|---|
| `episodic` | the dashcam stream's application-visible DELIVERED score | StudyD3 device-arm scores (`devsplit`) | clip / frame |
| `robot` | per-question device answer probability, letter-probability mass on the letter the 4B emitted | StudyE7 Job A (`device_confidence._load_primary`) | 64-hex question digest |
| `ss_mcq` | the same letter-mass rule, single shot | StudySS2 re-record, rule `mcq_chosen_letter_mass` | `<dataset>/<id>` |
| `ss_free_form` | geometric mean token probability | StudySS2 re-record, rule `geometric_mean_token_prob`, `signal_strength = primary` | `<dataset>/<id>` |
| `ss_point` | the same geometric-mean rule over the digits of a coordinate | StudySS2 re-record, `signal_strength = weak` | `<dataset>/<id>` |

`ss_point` is declared **WEAK** by its own source (`ss2_device_confidence.json`: "token confidence
in the digits of a coordinate is not confidence that the point is right") and by D164's own
wording. Per CLAUDE.md check 6 it may be fitted and reported, but it may not carry a headline and
any analysis resting on it is marked unvalidated.

The type of a query is resolved at decision time from `RecallQuery.question_id` (the field D171
(3) added, live and read) against the same committed row that supplies the confidence value. The
rule and the value come from one row: supplying the value without its rule is the defect
`device_confidence.source_of` exists to prevent. The harness's own `RecallQuery.category` carries
the DATASET for single-shot questions (`realworldqa`, `refspatial`) but not the SUBSET, so it
cannot separate `ss_mcq` from `ss_free_form`; that is why the type is resolved from the table.

## 2. Per arm: the method its card specifies, and the quantity thresholded

### 2.1 `confidence-cascade` (FrugalGPT TMLR 2024 + AutoMix NeurIPS 2024), `cards/cascade.md`

The card specifies two procedures, and both are quantile statistics of a committed signal over a
DEV population:

- **episodic**: `tau_trigger` = the `(1 - trigger_rate)` quantile of the DEVICE arm's score
  distribution on DEVELOPMENT-split negatives, `trigger_rate = 0.20` (card mapping row 5,
  adaptation A2, hyperparameter table). Quantity thresholded: `StreamState.latest_score()`.
- **recall**: `confidence_floor` = the **median** committed device confidence over DEV questions
  (card, amendment 2 of 2026-11-13). Quantity thresholded:
  `RecallQuery.device_answer_confidence`. Rule as committed:
  `c is None -> DEVICE; c < floor -> CLOUD; else DEVICE`.

**Operating point rule, fixed here**: the median, i.e. the 0.50 quantile, of the committed
confidence over the DEV population **of that type**, computed with
`statistics.median` on the committed values with no smoothing, no clipping and no re-weighting.
The card's procedure is unchanged; only the POPULATION is partitioned by confidence type, which is
requirement 3 of the ruling.

**Populations, fixed here**:

- `robot`: the LH-REQ DEV questions. The committed LH-REQ definition is 97 ids, `per_split`
  DEV 28 / EVAL 69; DEV is `lower(lh_req ids) - lower(sember_split eval_questions)`, case-folded
  on BOTH sides (the folding trap recorded in `data_sources.lh_req_question_ids`), intersected
  with the questions that have a committed StudyE7 value. The robots in a live cell draw only from
  LH-REQ EVAL, so this is the matched DEV population. This CHANGES the committed floor, which was
  the median over ALL S-EMBER DEV questions: that is DEV-only and D6-clean, but it is not the
  population D143 A names.
- `ss_mcq`, `ss_free_form`, `ss_point`: the DEV part of the committed
  `ss2_dev_eval_split.json` (seeded, stratified, 30 percent), intersected with that type's rule
  rows. SS devices draw from the EVAL part.
- `episodic`: unchanged from the card, StudyD3 development-split negatives at `trigger_rate`
  0.20. It is recomputed and reported, not re-specified.

### 2.2 `cascade-routing` (Dekoninck, Baader, Vechev, ICML 2025), `cards/cascade_routing.md`

The card's calibrated quantity is **lambda**, and the method is the paper's: "lambda set so an
expected cost budget B is met", calibrated OFFLINE. The card states this explicitly in its
2026-11-19 note, and uses it to justify deriving the budget cap from what the arm has observed
rather than adding a field to the shared schema. There is **no fitted confidence threshold** in
this arm: the escalation test is `q_cloud - (Q_DEVICE + (1 - Q_DEVICE) * conf) - lambda * c_cloud
> 0`, whose implied confidence threshold is a CONSEQUENCE of the quality priors and the cost, not
a free parameter.

**Pre-registered check, before any fit**: does an expected cost budget B exist in live2? The
check is on `coordinator.gpu_budget_s` and its provenance. If the harness budget is physical
capacity rather than a cost budget, and if committed cells record no budget refusals, then the
quantity the paper calibrates lambda against **does not exist here**, the method is not
expressible, and per section 0 no lambda is fitted. In that case the arm is reported as not
calibratable and `lambda_base` stays at its committed 0.02, labelled as an unfitted constant.
A per-confidence-type lambda is NOT in scope either way: the paper specifies one lambda for the
query stream, and a per-type lambda would be a departure from the method.

### 2.3 `eco-llm` (arXiv:2507.09003), `cards/ecollm.md`

**The card specifies no threshold calibration, and this arm reads no confidence at all.** It does
not declare `reads_device_answer`; its decision rule is `select = max(feasible, key=(quality,
-cost))` under `SLO(max_latency_s = the query's own deadline, max_cost_gpu_s = the remaining
budget, min_quality = None)`. The SLOs are "user-defined" in the paper and are taken from the
observation here; the quality table is the committed measured one (D137 (3)) and is consumed only
as an ORDER, which the card establishes cannot move a decision. There is therefore no quantity for
a DEV fit to set. Per section 0, nothing is invented. The grouping of eco-llm with the other two
under "these three escalate on a device-confidence threshold" in BASELINE_MATRIX is checked and,
if wrong, reported.

What IS verified for eco-llm instead, because D135 (2) and D137 (3) are standing requirements:
that it plans with the cost it is charged (`_rep_tokens` reads the offered `EvidenceItem.tokens`),
that `USE_MEASURED_QUALITY` is in force, and that its characteristic decision occurs.

## 3. Data, and what is never touched

| purpose | data | split used |
|---|---|---|
| fit `episodic` | StudyD3 device-arm scores, negatives | DEV clips |
| fit `robot` | StudyE7 Job A letter-probability mass | LH-REQ DEV 28 |
| fit the three `ss_*` | StudySS2 re-recorded confidences | `ss2_dev_eval_split.json` DEV part |
| proofs (characteristic decision, Step 2b) | dry live2 cells | the POSTED workload below |

EVAL is never fitted on. HOLDOUT is never read. Seeds 1, 2 and 3 are never run.

The proof cell is the posted D164 workload: `n = 16`, `ratio 40:40:20`,
`robot_question_set = lh_req`, `ss_question_set = ss2`, `dashcam_format = epg`,
`robot_upload = per-frame`, `robot_reask_mean_s = 30`, seed 4 (seed 5 as a second cell where a
proof needs one). A proof cell is EVAL data and is used only to count decisions and to show a
threshold moves one, never to choose a threshold.

Harness defect respected: a dry cell does not reproduce across runs inside one process, so **every
dry cell runs in its own subprocess**, and an identity control runs the same configuration in two
separate processes and must produce the same digest. If that control fails, no A-versus-B
comparison from these cells may be read (CLAUDE.md check 7: validate the control, not only the
result).

## 4. Proofs required before any arm is marked ready

1. **Characteristic decision, non-zero** (CLAUDE.md port rule). For `confidence-cascade` the
   decision kind it exists to make is the confidence-gated one, and BOTH halves must occur: at
   least one CLOUD escalation on a confidence below its type's floor, and at least one DEVICE stop
   on a confidence at or above it. A cell in which every confidence-bearing query goes the same
   way is a saturated threshold and counts as a FAILURE of this proof, not a pass.
2. **Step 2b, the switch reaches a decision.** For each fitted type, two dry cells differing only
   in that type's floor (0.0 = never escalate on confidence, 1.0 = always) must differ in at least
   one decision; the count of differing decisions and the first difference are recorded. Setwise
   comparison on the decision key, not positional.
3. **Device wait.** The arm's device-answer wait must be the measured per-question value with
   `device_wait_no_measured_value_*` counters at zero; any arm still taking the 0.567 s proxy on
   any request of the proof cell is reported and NOT marked ready.
4. **Instantiated link.** Each fitted threshold must have a named READ in the code that uses it to
   change a decision, with file and line. A threshold that is set and never read is ABSENT and the
   arm is not marked ready.

## 5. What would make this calibration FAIL

Stated before fitting, so that a failure cannot be reinterpreted afterwards:

- **Too little DEV data for a type.** Fewer than 10 DEV items carrying a committed confidence for
  that type: the type is reported as not calibratable and no floor is fitted for it.
- **A degenerate operating point.** The fitted floor sits at or beyond the extreme of the signal's
  own DEV range such that one branch is unreachable (floor <= min, or floor > max). Reported as a
  saturated threshold, not written into the arm.
- **A constant where a distribution is expected** (CLAUDE.md check 3). The quantity thresholded is
  the same value for every item in the proof cell. This is the specific risk for `episodic`: the
  live2 delivered score may be a placeholder rather than a score. If the thresholded quantity is
  constant, the link is **unexpressible** in live2 and no operating point exists; the card's own
  fitted value stands for the A-episodic setting where it was measured, and live2 behaviour is
  reported as independent of it.
- **An unmoved decision.** Step 2b shows zero differing decisions for a type that has queries of
  that type in the cell: ABSENT LINK, never a negative, and the arm is not marked ready.
- **Saturation.** The characteristic decision occurs in only one direction. This is the failure
  mode D164 cites (`reports/study_saturation_knee.md`: 4 of 5 cascade arms saturated on the robot
  side under an uncalibrated threshold), and it is the thing this exercise exists to remove.
- **A prior disagreement.** The fitted value disagrees by more than 2x with a committed value for
  the same quantity (CLAUDE.md check 1) and the disagreement cannot be explained. The committed
  comparator here is the card's `confidence_floor = 0.7358` and `tau_trigger = -7.0009`.

## 6. Readiness rule, fixed here

An arm is marked ready in `BASELINE_MATRIX` only if: its card specifies a calibration method for
every quantity its live2 decisions threshold; that method was applied on DEV, per confidence type;
proofs 1 to 4 of section 4 pass for every EXPRESSIBLE type; and any type found unexpressible is
declared in the matrix comment so that no reader attributes live2 behaviour to a threshold that
cannot act there. An arm whose card is silent is NOT marked ready: releasing it is a user ruling,
not a calibration outcome, and this file records that distinction rather than resolving it.

Only the three cascade cell blocks are touched in `BASELINE_MATRIX`. No other cell line changes.
