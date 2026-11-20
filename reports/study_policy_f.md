# StudyPOLICY-F: the frozen policy (hybrid-F, hybrid-F6) under D142

**Status: BUILD COMPLETE, SCORING BLOCKED. NOT COMMITTED, NOT FROZEN.** The two arms are defined and
their components are wired, including the single-shot device type. Scoring cannot start: D142 item 1
requires robots to draw only from LH-REQ and forbids MIXED for live policy evaluation, and the LH-REQ
trace option is session 2's deliverable, which has not landed (no `lh-req ready` on origin, no LH-REQ
path in `fleet/trace.py`). Nothing below is a policy finding; the measurements here are properties of
the traces, the cost curves and the committed chooser.

## 0a. Test suites, final tree

`policy` **482 passed**, `live2` **152 passed** (6 min 17 s), both matching their committed counts, run
as one clean pass after every Python edit was final. `live2/hybrid/test_hybrid.py` collects **zero**
tests and reports success, which is a gap, not a pass: see section 7.5.

## 0. What is frozen, and what the freeze means

`hybrid-F` and `hybrid-F6` are registered in `experiments/orchestration/live2/hybrid/hybrid_arm.py`.

| | hybrid-F | hybrid-F6 |
|---|---|---|
| C1 ordering | on | on |
| C2 at-risk + dashcam throttle | on, `k_r` 1.5 s, floor 2, at-risk dashcam exempt | same |
| C3 degrade to RECENT | default only (rebuild predicted infeasible), **not** `c3_always` | same |
| C4 retention | inert (`c4=False`) | inert |
| C5 AIMD cap | dashcam-only, 4..8 | dashcam-only, 4..8 |
| C6 chooser | off | **on**, flash's `policy/chooser.py` (70be641), `delta = 0.0` |
| definitions | `defs="v2"` (D140) | `defs="v2"` |

The two differ in exactly one switch (`c6`), verified by comparing the constructed arms.

`c4=False` rather than `True`: D141 recorded all-on as byte-identical to C1+C2+C3+C5 because C4 emits
no session action, so the two spell the same policy today. `False` is the one that cannot later
diverge if C4 ever stops being inert.

`delta = 0.0` is **recorded, not tuned**, and no tuning happens after the freeze. The comparison is
`> delta`, so C6 deviates only on a strict improvement and a tie keeps the component's proposal. With
no committed scale for the objective's units, any non-zero delta would be an invented number inside a
frozen policy.

## 1. The single-shot quality table is a DECLARED INPUT, not policy code

**`results/orchestration/prof1/ss_quality.json`**, merged into the read path by `load_profiles()`
(`policy/profiles.py`). This is the point of the design: replacing the placeholder with the measured
32B values is a **data update** that leaves the frozen policy byte-identical. A table written into
policy code would make every swap a new labelled version with every policy cell redone under D79.

It lands in the path `rc_accuracy` and `representation_for` actually read, which is also what closes
the second half of the D136 two-part dependency: those functions RAISE on a question type with no
committed entry, so the policy family could not execute an SS question at all. A constant inside the
SS module would not have fixed that. Verified: `representation_for("vizwiz")` now returns `D2` where
it previously raised. The SS question **types** come from the same file, so even the set of categories
that count as single-shot is data rather than policy code.

**The 32B comparison has NOT run, so the placeholder stands.** `compare_gates.json` on origin
(`3aac01d`) states the 32B answers are not on origin: commit `01e5395` adds only a 54-line server
wrapper, and the expected `vizwiz_val_cloud32b.json` and `egothink_cloud32b.json` do not exist. The
table is built to be refilled as a data update the moment they land.

**The placeholder rule.** `cloud_accuracy` = the measured DEVICE accuracy for that dataset. That is
conservative (it never values an SS cloud request above what the device already achieves) and it is
measured rather than invented. It is still a placeholder: the real cloud accuracy is unknown and could
go either way.

| dataset | metric | device accuracy | n | source |
|---|---|---|---|---|
| vizwiz | `vqa_accuracy` | 0.6587 [0.6454, 0.6720] | 4,319 | `results/casestudy/study_ss1/vizwiz_val_device_summary.json` |
| egothink | `containment` | 0.4714 [0.4343, 0.5071] | 700 | `results/casestudy/study_ss1/egothink_device_summary.json` |

**Device condition, corrected.** The first version of the input file recorded the device answer host
as "unconfirmed". `compare_gates.json` resolves it: **Orin, vLLM, idle, one request at a time, cold
per image**, established by the user's statement plus the Orin session's own report at `8492e02` and
**not** by a `_provenance` block, since those five artifacts still carry none. The attribution is as
good as the user's word and no better, which is stated rather than implied.

**A stack distinction that must be carried.** The SS device numbers come from the **ORIN3 vLLM**
stack; the committed device baseline for robot recall is the **ORIN2 in-process harness** (D87,
unexercised per D103 item c). The two never meet in a live number today and must not be joined in
one. Both are labelled; nothing is rerun.

**THE CONSEQUENCE, which must be read before any SS number is reported.** Because the placeholder
sets cloud = device, the gain is zero and C1's value term for an SS request falls to the floor:

| device type | C1 value | source |
|---|---|---|
| robot | 0.10627 | 32B-D2 minus 4B-D2, EVAL-mix weighted |
| dashcam | 0.09000 | committed cloud SH gain |
| single-shot | **0.00100** | PLACEHOLDER floor |

That is about **106 to 1** against a robot, so **C1 ranks every single-shot request last**. The frozen
policy's SS behaviour is therefore set by a stand-in number, not by evidence. An SS on-time or accuracy
figure measured under this placeholder is **not a finding about the policy**; it is the expected
artifact of valuing SS at the floor. When the 32B values land, C1's SS ordering changes and every SS
cell must be rerun. The robot and dashcam axes are unaffected: their value terms do not read this file.

## 1b. Both workloads: both robot sets selectable, SS switchable

The "both workloads" instruction is ambiguous between the two robot question sets (LH-REQ, MIXED) and
the two device-type configurations (SS present, SS absent). **Both readings are supported**, which is
the union and costs nothing:

| axis | how it is selected | arms |
|---|---|---|
| robot question set | arm kwarg `workload` in `("mixed", "lh_req")`, which drives C1's value weighting | `hybrid-F` / `hybrid-F6` (MIXED) and `hybrid-F-lhreq` / `hybrid-F6-lhreq` |
| single-shot devices | the trace mix: `40:40:20` includes them, `50:50` omits them; every SS branch is gated on `q.category in self._ss_types` | the same arms, either way |

**The reading taken, stated so nobody has to guess: the workload axis is the robot question set, and
the device-type axis is covered too.** The workload is in the arm NAME rather than inferred, so a
later reader can see which one a cell used.

**The tension between D142 item 1 and item 5, recorded rather than resolved.** Item 1 says live policy
evaluation never uses MIXED; item 5 wants the policy to run correctly on both. These are consistent:
**MIXED is a built capability, LH-REQ is the evaluation.** The bare `hybrid-F` / `hybrid-F6` pair
carries the MIXED weighting and exists so the policy demonstrably runs on that workload; the `-lhreq`
pair is what gets scored. A later reader finding MIXED support inside a frozen policy should read it
as capability, not as an evaluated configuration.

**Item 2, the workload's own trace-weighted table.** The accuracy table is the same committed
`32B-D2` minus `4B-D2` per-category table for both workloads; only the **weights** differ, which is
what "the workload's own trace-weighted table" means. LH-REQ's weights are the `per_category` counts
in the committed `results/orchestration/live2/lh_req/lh_req_definition.json` (1acbe36), read directly:

| | C1 recall value | weights |
|---|---|---|
| mixed | 0.10627 | EVAL session mix |
| **lh_req** | **0.13204** | 97 questions: visual_detail_recall 29, location_trace 26, sequential_action 22, temporal_ordering 8, time_duration 4, spatial_aware 4, counting 2, object_comparison 2 |

The switch moves the quantity by **+24 %**, so it reaches a decision-relevant value rather than
sitting inert. All eight LH-REQ categories have an entry in the committed table, so no entry is
missing and no value is invented **here** - but see section 1c, which qualifies this in two ways: two
of those entries carry n = 2 and are uninformative, and the table itself is measured on a question set
that is not LH-REQ, which makes this a reweighting approximation rather than the workload's own table.

**I did not write a question filter.** The 97 are not re-derived here; the definition file is the one
source of truth for the set, and the trace option that selects them is owned elsewhere. As of origin
`3aac01d` no code under `live2` or `policy` carries an LH-REQ filter, so the trace option does not yet
exist and no LH-REQ cell has been run.

## 1c. Four facts from the committed LH-REQ definition, checked

Checked against committed files rather than accepted. Two of them change what section 1b claims.

**(1) Every LH-REQ question is feasible, so "over feasible" and "over all" are the same number.**
Committed `history_tokens` runs min 11,399 to max 12,830; the D132 breakeven is 19,381 feasible
against 20,011 infeasible, so the **worst** LH-REQ question clears the ceiling by **6,551 tokens**.
Expected feasible fraction **1.000**, with none of the 0.887 to 0.924 band and none of the 11-of-28
cells below 0.90 that D133 exists to handle. This is favourable: on this workload the headline
ambiguity disappears. **The two columns will be reported only with an explicit statement that they
are arithmetically identical and why** - two columns presenting as a robustness check when they are
the same number reads as corroboration and is not. To be **recomputed in-trace**, not inherited,
because D101 part-way joining and D83 chaining change the history a question actually sees.

**(2) The 97 includes DEV: the split is DEV 28, EVAL 69, and EVAL-only weights are NOT COMPUTABLE
FROM THIS FILE.** D142 item 1 says the 97, D139 says both splits, D6 says metrics on EVAL only; that
tension is the user's. The concrete obstruction for my side: `lh_req_question_ids` is a **flat list of
97 content hashes with no split field**, and `per_split` gives only the two totals. So the
per-category counts cannot be decomposed into DEV and EVAL, and **`_lh_req_mix()` can only produce the
all-97 weighting today.** If the ruling is EVAL-only, the weights change and a split-to-question
mapping has to come from somewhere; I have not invented one. There is also a leakage question if a
DEV-fitted quality table is scored on DEV questions. Any result will state its denominator.

**(3) The `history_tokens` field is NOT cited as a per-question history size.** 97 questions from
sessions of differing lengths spanning 11,399 to 12,830 with an **IQR of 190 tokens** has the shape of
a quantity computed at a fixed point, not per question: check 3, a near-constant where a distribution
is expected. It is used in fact (1) only as a **bound** - even the 11,399 floor clears 19,381 - which
survives either reading. It is cited nowhere else in this report.

**(4) Category concentration, and the reversal worry does NOT materialise.** 77 of 97 sit in three
categories; `counting_objects_events` and `object_comparison` are **n = 2 each**. **My earlier claim
that "all eight categories are present in the quality table, so nothing is missing and no value is
invented" was about table COVERAGE and should not be read as reassurance about informativeness:
present at n = 2 is present and uninformative.** D135 item 5 already bars per-category values on the
mixed table at n = 16 to 39, and LH-REQ is worse, so trace-mix weighting is the only defensible option
here rather than a preference.

On the specific worry - that RECENT might beat D2 on `location_trace`, putting 26 of 97 against the
headline - the committed tables say **it does not**, and the reason is that the figure in question
belongs to a different pair:

| category | LH-REQ weight | D2 | RECENT | D2 - RECENT | D2 | RICH | D2 - RICH |
|---|---|---|---|---|---|---|---|
| visual_detail_recall | 29 | 0.5263 | 0.5000 | **+0.0263** | 0.5263 | 0.6053 | -0.0789 |
| location_trace | 26 | 0.4828 | 0.4483 | **+0.0345** | 0.4828 | 0.3103 | **+0.1724** |
| sequential_action | 22 | 0.5556 | 0.4074 | **+0.1481** | 0.5556 | 0.5185 | +0.0370 |
| temporal_ordering_recognition | 8 | 0.4848 | 0.4242 | **+0.0606** | 0.4848 | 0.5152 | -0.0303 |
| time_duration | 4 | 0.4359 | 0.3846 | **+0.0513** | 0.4359 | 0.3846 | +0.0513 |
| spatial_aware_reasoning | 4 | 0.2400 | 0.2800 | **-0.0400** | 0.2400 | 0.2000 | +0.0400 |
| counting_objects_events | 2 | 0.2222 | 0.2500 | **-0.0278** | 0.2222 | 0.2500 | -0.0278 |
| object_comparison | 2 | 0.3750 | 0.3750 | 0.0000 | 0.3750 | 0.3750 | 0.0000 |

**The +17.2 pp `location_trace` figure is the D2-vs-RICH pair** (0.4828 against 0.3103), where the
cheaper representation wins on 4 of 8 categories. That is the comparison CLAUDE.md's motivating
failure refers to, and **it does not transfer**: on D2-vs-RECENT, the only pair live2 can select at all
(RICH is in `REPRESENTATIONS` but not selectable), `location_trace` favours D2 by +3.45 pp. The
reversals on D2-vs-RECENT are `spatial_aware_reasoning` (-4.00 pp) and `counting_objects_events`
(-2.78 pp), together **6 of 97 = 6.2 % of the workload's weight**. So the exposure is small, and it is
reported with its weight rather than as a direction.

**A 4.3x DISAGREEMENT THAT FLAGS MY OWN IMPLEMENTATION (check 1).** Trace-weighting the committed
per-category table by the LH-REQ counts gives a D2-minus-RECENT gap of **+5.56 pp**. The committed
LH-REQ aggregate in `lh_req_definition.json` is **+23.71 pp [12.37, 35.05]**. Same named quantity,
**4.3x apart**, and the explanation is not an error but a definition:

> The committed +23.71 pp is measured **on the 97 LH-REQ questions**, which are selected precisely
> because their evidence lies outside the recent window, so RECENT scores 21.65 % on them against
> roughly 45 % on those categories as a whole. The per-category table is measured over **all**
> questions in each category, most of which are not LH-REQ. The selection is **within** category, not
> across categories, so reweighting a non-LH-REQ table by LH-REQ category counts **cannot** reproduce
> the LH-REQ gap.

**The correction to section 1b** (refined in section 1d, which splits this in two): what I implemented is the workload's own **WEIGHTS** applied to the
general **TABLE**, not "the workload's own table". D142 item 2 asks for the LH-REQ-measured table; for
D2-vs-RECENT that exists only as an aggregate (45.36 against 21.65) with no per-category breakdown,
and for the cloud-minus-device gain that C1 actually uses it **does not exist at all**. So
`workload="lh_req"` is a **category-reweighting approximation**, and the 4.3x gap on the neighbouring
quantity is direct evidence that the approximation is not equivalent to the real thing. It is flagged
here rather than presented as item 2 satisfied, and it is a question for the user: C1's LH-REQ value
term is currently derived from a table measured on an easier question set.

## 1d. The check-1 failure splits in two, and half one closes with a committed number

**Where the quantity is actually consumed.** The hybrid arm **never calls `rc_accuracy`** - verified by
grep. C3 degrades on **feasibility alone** (`recall_ttft_s(RECENT_TOKENS) <= slack`), not on quality,
and C1's value comes from `_quality_values()` reading `profiles_dev.json` directly. The D2-versus-RECENT
comparison enters **only** through C6, via the policy-core mirror's rollout, at `rollout.py:609-610`:

```
acc_c = self.pf.rc_accuracy(job.qtype, job.rep, "cloud")   <- the representation axis  (HALF ONE)
acc_d = self.pf.rc_accuracy(job.qtype, "D2",    "device")  <- the device comparator    (HALF TWO)
```

So the two halves are **two arguments of one expression**, and the whole question affects
**`hybrid-F6` only**. `hybrid-F` is untouched by it.

**HALF ONE: yes, the architecture already accepts a mix-weighted pair, so this closes with no new
measurement.** `_MixWeightedProfiles.rc_accuracy` (`arms_policy.py:133`) **ignores `qtype` entirely**
and memoises on `(rep, tier)`: it is already a per-representation scalar, not a per-category lookup.
That is D135 item 5 in code. Substituting the committed LH-REQ aggregate for the cloud side is
therefore a **drop-in with no structural change** - the consumer cannot tell the difference.

And it matters, because the three candidate numbers are far apart:

| cloud side, mix-weighted | D2 | RECENT | D2 - RECENT |
|---|---|---|---|
| `TRACE_MIX`, which is **policy-core's live default** | 0.4286 | 0.3963 | **+3.23 pp** |
| LH-REQ `per_category` weights on the general table | 0.4929 | 0.4373 | +5.56 pp |
| **committed LH-REQ aggregate, measured on the 97** | 0.4536 | 0.2165 | **+23.71 pp** |

**The model's live weighting understates the representation gap on this workload by 7.3x**
(23.71 against 3.23). This is not hypothetical: C6 **already chose `send` to `RECENT-now` 14 times**
at 32 devices (section 7.3). So C6 is pricing a RECENT degrade at about 3 pp when the measured cost on
LH-REQ is about 24 pp, which would make it far too willing to degrade. **Using the committed
aggregate satisfies item 2 on this axis with no approximation label.**

`TRACE_MIX` is also simply the wrong weighting for LH-REQ, independent of which table is used:

| category | LH-REQ weight | `TRACE_MIX` | ratio |
|---|---|---|---|
| location_trace | 0.268 | 0.058 | **4.62x** |
| sequential_action | 0.227 | 0.110 | 2.06x |
| visual_detail_recall | 0.299 | 0.227 | 1.32x |
| temporal_ordering_recognition | 0.082 | 0.097 | 0.85x |
| spatial_aware_reasoning | 0.041 | 0.097 | 0.43x |
| time_duration | 0.041 | 0.169 | 0.24x |
| counting_objects_events | 0.021 | 0.097 | 0.21x |
| object_comparison | 0.021 | 0.143 | **0.14x** |

**HALF TWO: a real gap that cannot be closed from committed data.** The rollout's `acc_d` is
cross-tier - 32B cloud on `job.rep` against the **device** on D2 - whereas `d2_acc` and `recent_acc`
are **the same model on two representations**. D87 fixes the device comparator at 4B x RECENT, 32.78 %
over **845 questions of the mixed set, not the 97**. Mix-weighting the committed device table gives
0.3231 under `TRACE_MIX` and 0.3609 under LH-REQ weights, but **neither is measured on the 97**. So no
LH-REQ-specific device accuracy exists and the cross-tier gain **cannot be constructed** from what is
committed. This needs either a device-side run on the 97 or an explicit, stated substitution.

**HALF TWO IS CLOSED FROM COMMITTED DATA. This supersedes the StudyR1 search recorded below, whose
conclusion - "needs a device-side run on the 97 or a declared substitution" - was WRONG.** My error
was searching by study name: D87's device comparator points at **StudyO-Q4**, not StudyR1, and
`live2/fleet/data_sources.py:177` names it outright as `DEVICE_RECALL_SET =
results/sember/study_o/study_o_q4_trials_fa2.jsonl` with `DEVICE_RECALL_N = 845` and
`DEVICE_RECALL_CORRECT = 277`. A grep for `DEVICE_RECALL` would have found it; a search for
"StudyR1 per-question" could not.

Verified independently rather than accepted:

| check | result |
|---|---|
| committed sha256 of the trials file | **matches** `data_sources.DEVICE_RECALL_SET_SHA256` |
| rows / fields | 2,535 rows carrying `question_id`, `model_arm`, `state_arm`, `question_category`, boolean `correct` |
| **CONTROL:** filter to `4B-I x RECENT` | **n = 845, correct = 277, acc 32.781 %** - identical to committed D87, so the filter is right rather than merely plausible |
| all 97 LH-REQ ids present in that arm | **yes, 0 missing** |
| `sember_split.split()` reproduces `per_split` | **yes: DEV 28, EVAL 69, zero unmatched** |

**Device accuracy measured ON the 97**, reported with intervals because the denominator is small:

| subset | n | correct | device acc | Wilson 95 % | cloud 32B-D2, SAME subset | paired cross-tier gain |
|---|---|---|---|---|---|---|
| all 97 | 97 | 20 | **20.619 %** | [13.76, 29.71] | 45.361 % (44 / 97) | **+24.74 pp** |
| **EVAL only** | 69 | 17 | **24.638 %** | [15.99, 35.96] | **53.623 % (37 / 69)** | **+28.99 pp** |
| DEV only | 28 | 3 | 10.714 % | [3.71, 27.20] | 25.000 % (7 / 28) | **+14.29 pp** |

So the cross-tier gain C1 consumes is **constructible now, with no device run and no declared
substitution**.

**CORRECTION, and it reverses the direction this section first reported.** The first version of this
table gave EVAL +20.72 pp and DEV +34.65 pp. Both subtracted a split-subset DEVICE figure from the
cloud's **all-97 aggregate** of 45.361 %, so the two sides of each gain were measured on different
question sets. The cloud side per split comes from
`results/sember/study_acc2/acc2_requests.jsonl`, which carries `question_id`, `rep`, `split` and
`correct` on each of its 1,819 rows, so both sides are computable on the same questions; ids join on a
60-character prefix, 97 of 97 found. Paired, the gain is **larger on EVAL (+28.99 pp) and smaller on
DEV (+14.29 pp)**, because EVAL is the easier subset for the cloud (53.623 % against 25.000 %). The
denominator ruling therefore moves the gain between **+14.29 and +28.99 pp**, not between +20.72 and
+34.65. Two further facts fall out: the all-97 cloud figure of 45.361 % **reproduces the committed
`d2_acc` exactly**, which validates the join; and on DEV the device and the 32B restricted to RECENT
are **identical at 10.714 %, 3 of 28 each**, so on hard history-needing questions a 32B held to the
recent window is worth nothing over the 4B.

The mismatched-denominator error is the register rule at the point of use: every arithmetic check on
those two numbers passed, because the arithmetic was right and the denominators were not.

**A case-folding trap worth recording, because I walked straight into it after being warned.** Both id
collections are mixed-case: `sember_split`'s eval set is 444 lower and 158 upper, LH-REQ is 63 lower
and 34 upper, and the StudyO-Q4 device arm is 633 lower and 212 upper. Lower-casing **one** side and
calling `is_eval()` on it - which does plain set membership on the raw id - gave me **EVAL 43, DEV 20,
34 unmatched**, and **34 is exactly the count of upper-case LH-REQ ids**. Only the committed 28/69
totals caught it. Both sides must be folded; the committed totals are the control that proves the fold
is right.

### The project's thesis, now measured across both tiers on the same 97 questions

| | accuracy on the 97 |
|---|---|
| 4B + RECENT (device) | **20.62 %** |
| 32B + RECENT | **21.65 %** |
| 32B + D2 (cloud) | **45.36 %** |

**Changing the MODEL at fixed representation buys +1.03 pp. Changing the REPRESENTATION at fixed model
buys +23.71 pp: a ratio of 23 to 1.** On history-needing questions the gap is about the history, not
the model size, and that is now a measurement rather than an argument. It is also the cleanest
available answer to "why not just use a bigger device model".

It bears on the half-one recommendation: the cross-tier gain (+24.74 pp) and the within-model
representation gap (+23.71 pp) are **nearly identical on this workload**, because the device's
disadvantage is almost entirely representational. So filling C1's gain term and fixing half one's 7.3x
mispricing **move the same quantity in the same direction** - relevant since the user is prioritising
between them.

**The superseded StudyR1 search, kept for the record.** The proposed
construction was the symmetric one that produced half one's numbers: filter StudyR1's 845 device rows
to the 97 LH-REQ ids. It fails on the load-bearing requirement.

| requirement | finding |
|---|---|
| StudyR1 committed per-question arrays | **NO.** `study_r1_results_h100nvl.json` carries aggregates only: `studyo["4B-IxRECENT"]` = `{n: 845, acc: 0.32781, wilson95: [0.2970, 0.3602]}`. No per-question array, no ids. `study_r1_p4_scores.json` holds three summary keys; `run_meta` holds none. No `*_perquestion.json` exists for StudyR1 anywhere under `results/`. |
| id spaces reconcile | **YES, and this is worth keeping.** The only per-question ids in the StudyR1 directory are in the parity files: 20 rows, 10 unique, 64-char hex in UPPER case against `lh_req_question_ids` in lower. After case-folding, **1 of 10 is in the 97** - not a coincidence at 64 hex characters, so the two are the same content-hash space and a join WILL work once device rows exist. |
| per-question device SCORES exist | **NO.** The 20 parity rows carry `vllm_prompt_tokens`, `rel_diff`, `frames_sent`, `ids_exact_match_builder` and no accuracy, score or correctness field at all. They are prompt-token parity checks, not scored answers. |

StudyR1 does indeed hold only aggregates - that part was right - but it was **the wrong place to
look**, and the conclusion drawn from it is **retracted**: the device rows exist under StudyO-Q4, as
shown above.

**On the n:** 97, or 69 on EVAL only, is a small denominator and the interval will be wide - the 845
aggregate's own Wilson interval is already [0.2970, 0.3602]. It should be reported **with its
interval, not as a point**. Measured on the right questions beats precise on the wrong ones.

**THE DIRECTION OF THE BIAS, WHICH MATTERS MORE THAN ITS SIZE.** The sign is known on both axes, so a
pre-fix `hybrid-F6` LH-REQ number is not noisy, it is **directionally wrong**. C6 prices a RECENT
degrade at about 3 pp against a measured 24 pp, so it **degrades too readily**; RECENT is cheaper to
serve, so the expected effect is to **inflate on-time service while depressing accuracy**. That is
exactly the failure mode the D133 headline exists to catch, in its own terms: so that cheap
recent-frames answers cannot win on timeliness alone. A pre-fix F6 that looks good on on-time should
be read as a symptom, not a result.

**THE CONTAMINATION IS ONE-SIDED, WHICH DAMAGES THE F-VERSUS-F6 COMPARISON SPECIFICALLY.** The hybrid
arm never calls `rc_accuracy`, so **`hybrid-F` is clean and `hybrid-F6` is mispriced**. The two arms
differ in exactly one switch, and **that switch is the one carrying the 7.3x error**, so every
F-versus-F6 margin - including the `delta = 0.0` threshold that decides whether C6 deviates at all -
is measured with one side wrong. Together with the decision-period breach at 32 devices (section 7.3),
**`hybrid-F6` has two independent reasons not to be frozen.** `hybrid-F` has neither.

**WHY STEP 2 COULD NOT HAVE CAUGHT THIS, AND CHECK 1 DID.** Worth recording because it shows the two
protocols are complementary rather than overlapping. The mispriced quantity is **read** (three call
sites in `rollout.py`), **non-zero**, **varies across conditions**, and **reaches a decision that fires
14 times**. Step 2 asks whether a link is absent, zero or constant; **this link is alive and carrying
the wrong magnitude**, which every Step 2 check passes. What caught it was **check 1, the cross-check
against committed measurements**: the same named quantity measured before, 7.3x apart. That is check 1
doing precisely the job the E30-versus-E32 precedent was written for, where win-10 was 400 tokens in
one experiment and 7,117 in another. **A quantity can be perfectly alive and still wrong, and only the
cross-check sees it.**

**Not applied.** Changing the source of the quality model is a methodological change, which CLAUDE.md
requires be flagged and discussed rather than applied, and it would alter `hybrid-F6` before the
freeze. Half one is a one-line drop-in whenever the user rules; half two needs a measurement or a
declared substitution.

## 2. C2 for a single-shot request: the rule, and why this mechanism

Stated before coding, as D142 item 3 requires.

**Rule.** An SS request is at risk when `laxity = deadline - now - predicted remaining work < k_r`,
the **same** laxity test and the **same** `k_r = 1.5 s` as the robot flag. No new threshold.

**Mechanism.** The consumer is the **dashcam throttle**: while any SS request is at risk, no new
dashcam frame is submitted beyond the floor of 2 in flight, and an at-risk dashcam device stays exempt.
This is the one C2 consumer D141 proved moves decisions (3,570 differing) where the reserved slot was
an ABSENT LINK (0 differing at both `k_r`). Reusing it means the SS path is live on arrival instead of
needing its own move proof from zero. Implementation note: `pending_risk` is gated on the generic
`risk` flag, so an at-risk SS request feeds the throttle through the existing path rather than a
parallel one.

The SS deadline is 2 s against the dashcam's 1 s and the robot's 5 s, so SS sits between them in
deadline order and is throttled into contention with dashcams. That is the behaviour to watch.

**C3 is deliberately NOT applied to an SS request.** An SS request carries no history, so RECENT and
D2 are the same single image: degrading buys no quality (the declared input records them as equal, not
ordered) while the coordinator would charge `RECENT_WINDOW_TOKENS = 467` and answer on a truncated
image prompt. The representation axis does not exist for this device type.

## 2b. The measured SS cloud gain, and why the at-risk flag fires

**The placeholder's BEHAVIOUR is confirmed; its VALUE was still unjustified when I shipped it.** The
VizWiz device-versus-cloud comparison is committed at `07d78a3`: clean denominator **4,291**, device
**0.6584**, cloud **0.6656**, paired difference **+0.0072 with 95 % CI [-0.0035, +0.0180]** - the
interval **includes zero**. The 2x2 is nearly symmetric (cloud-only 380 against device-only 349, the
off-diagonals within 35 to 42 of each other at every cut from 0.3 to 1.0). By stratum the only
interval excluding zero is `unanswerable` at +0.0245; answerable-only is **-0.0010** [-0.0144,
+0.0124].

So the cloud-minus-device gain for single-shot is about **+0.7 pp and not distinguishable from zero**,
against **+23.71 pp** for robot LH-REQ: a factor of roughly **33**.

Section 1 reported that the placeholder puts SS at **1/106 of a robot's C1 value, so C1 ranks every SS
request last**, and flagged it as an artifact to be fixed. **The measured numbers say that ranking is
correct**: the cloud buys almost nothing on these questions. 1/106 against a measured ratio near 1/33
is the same order and the same direction.

**This is a prediction confirmed, not a defect resolved, and the two claims must stay separate.** The
placeholder was **unjustified when it shipped** - its value came from a conservative rule, not from
evidence - and it **happens to land in approximately the right place**. The second does not
retroactively justify the first. The practical consequence: filling the SS half of the table from this
comparison will change C1's **magnitude** for SS and **not its ordering**.

**Priority, which follows from that.** The SS value term is now measured and small, so **the SS quality
table is the least urgent of the table questions**. Half one's 7.3x mispricing (section 1d) is a live
error on the robot-recall axis affecting a decision that fires 14 times; the SS placeholder is an
arbitrary number that lands about right. They should not queue at the same priority.

**WHY 55 OF 118 SS REQUESTS ARE FLAGGED AT RISK: THRESHOLD GEOMETRY, NOT DELIVERY RISK.** Measured
TTFT runs **cloud p50 0.3225 s against device p50 0.8618 s** (both labelled unverified-cold), so the
H100 32B answers **faster** than the Orin 4B and both sit far inside a 2 s deadline. There is real
headroom and the flag is not reporting its absence. Working the test through:

> at risk <=> laxity < k_r <=> (deadline - now) - work < 1.5 s <=> **slack < 1.5 + work**

| SS prompt tokens | work from the committed curve | fires when | share of a 2 s lifetime |
|---|---|---|---|
| 1,550 (VizWiz committed median) | 0.3444 s | slack < 1.84 s | **92.2 %** |
| 2,072 (EgoThink committed median) | 0.4604 s | slack < 1.96 s | **98.0 %** |
| 2,500 | 0.5556 s | slack < 2.06 s | **100 %**, on at birth |
| 3,000 | 0.6667 s | slack < 2.17 s | **100 %**, on at birth |

**The at-risk window covers 92 to 100 percent of an SS request's life.** The flag switches on after
roughly **0.1 s of queueing**, so the 55 of 118 I measured is a lower bound set by how soon each
question happened to be evaluated, not by any delivery risk. A threshold whose window spans almost the
whole lifetime of a device type is **not a risk detector for that type; it is effectively a constant**
- CLAUDE.md check 3, a near-constant where a distribution is expected, concentrated on the SS stratum.

This is independent of the `k_r` question in section 7.4 but points the same way, and it **replaces**
the looser explanation given there ("`k_r` chosen against a 5 s deadline"): the quantified reason is
that `k_r = 1.5 s` against a 2 s deadline leaves only ~0.1 s of un-flagged life once the committed
cost curve's work is subtracted.

## 3. The C6 horizon: the link is CONSTANT, and sufficient

D142 asks that each candidate be simulated to its own deadline or completion, not a fixed H. The
committed chooser does take a per-candidate `deadline_s` and converts it in `horizon_for`. But it
clamps to `[MIN_HORIZON_S, MAX_HORIZON_S] = [5.0, 60.0]`, and **every deadline in the fleet is at or
below 5 s** (dashcam 1, single-shot 2, robot 5). Measured over the whole realistic range:

| candidate | slack tested | horizon |
|---|---|---|
| dashcam, deadline 1 s | 1.00, 0.50, 0.10 | 5.00, 5.00, 5.00 |
| single-shot, deadline 2 s | 2.00, 1.00, 0.10 | 5.00, 5.00, 5.00 |
| robot, deadline 5 s | 5.00, 2.50, 0.10 | 5.00, 5.00, 5.00 |

Distinct horizons across the range: **{5.0}**.

- **Satisfied:** no candidate is truncated before its deadline, so the H = 0.5 s geometry cancellation
  that flattened COVEX's objective cannot recur. A 5 s span covers the whole life of every candidate,
  which is the property C6 needed.
- **Not present:** "simulated to its own deadline" as a quantity that **varies** per candidate. It does
  not vary; it is 5.0 s throughout. Under CLAUDE.md Step 2 that link is **CONSTANT**, and under check 3
  it is a constant where the wording implied a distribution.

`MIN_HORIZON_S` is in flash's committed chooser, read-only to me, and lowering it is a methodological
change to discuss rather than apply. Recorded, not fixed.

## 4. Unique-question coverage per cell (never computed before)

The coordinator's condition 3: the accuracy denominator. Three-type traces, mix 40:40:20, 600 s.
Question identity is `question_id`, a content hash, confirmed to be the pool identity rather than a
per-opportunity id.

| n | seed | dashcam / robot / SS devices | robot questions | unique robot | repeats | SS questions |
|---|---|---|---|---|---|---|
| 12 | 0 | 5 / 5 / 2 | 21 | 21 | 0 | 118 |
| 12 | 4 | 5 / 5 / 2 | 27 | 27 | 0 | 118 |
| 16 | 0 | 6 / 7 / 3 | 34 | 34 | 0 | 176 |
| 16 | 4 | 6 / 7 / 3 | 39 | 39 | 0 | 177 |
| 32 | 0 | 13 / 13 / 6 | 58 | 58 | 0 | 357 |
| 32 | 4 | 13 / 13 / 6 | 63 | 63 | 0 | 352 |

**There are no repeats**, so the denominator equals the count. The consequence stands anyway: against
the 97-question LH-REQ pool, a 12-device cell touches **21 to 27 questions, about a quarter of the
pool**, and 32 devices still only reach 58 to 63. A CI over 21 unique questions is wide and **must not
be read as equivalence**; one question is 4.8 pp at 21 and 1.6 pp at 63. Every accuracy figure in this
study will carry its unique-question denominator beside it.

**EgoThink is UNEXERCISED at the sizes that matter.** The SS dataset mix:

| n | vizwiz | egothink |
|---|---|---|
| 12 | 118 | **0** |
| 16 | 176 / 177 | **0** |
| 32 | 323 / 318 | 34 (9.6 %) |

The pool is consumed in `SS1_SOURCES` order with VizWiz's 4,319 rows first, so devices work through
VizWiz sequentially and only reach EgoThink at 32 devices. So at 12 and 16 devices **any "SS accuracy"
is a VizWiz-only `vqa_accuracy` number** and the `egothink` table entry is dead. Category 4
(unexercised), not a negative.

**The three accuracy axes use three different metrics** and none is comparable to another: VizWiz
`vqa_accuracy` (consensus over 10 human answers), EgoThink `containment` (judge), robot exact-match
letter. An SS accuracy figure may not be averaged across the two SS datasets, and SS accuracy may not
be pooled with robot accuracy. Check 4; recorded in the declared input.

## 5. Offered load against the budget: tighter than any measured cell

The coordinator's condition 4, confirmed and worse than predicted. Offered accelerator work at the
committed idle-engine cost curves, against the 600 GPU-s budget:

| n | seed | robot GPU-s | SS GPU-s | dashcam GPU-s | total | vs 600 |
|---|---|---|---|---|---|---|
| 12 | 0 | 60.4 | 40.8 | 2148.2 | 2249.4 | **3.7x** |
| 12 | 4 | 97.2 | 40.6 | 2147.8 | 2285.6 | **3.8x** |
| 16 | 0 | 106.1 | 62.9 | 2584.3 | 2753.2 | **4.6x** |
| 16 | 4 | 147.2 | 63.3 | 2569.6 | 2780.2 | **4.6x** |
| 32 | 0 | 189.4 | 127.6 | 5577.7 | 5894.7 | **9.8x** |
| 32 | 4 | 235.6 | 125.5 | 5569.0 | 5930.2 | **9.9x** |

The accelerator budget binds hard in every three-type cell. **One correction to the expected story:**
single-shot dominates question COUNT (118 of 139 at 12 devices, 85 %) but contributes only about
**1.8 %** of offered GPU-s, because each SS request is one image where a robot question is a long
history: 0.35 GPU-s per SS question against 2.9 per robot question. Dashcam remains 95 % of the
offered load, as before. So adding the SS type multiplies the number of deadlines to miss far more
than it multiplies the work.

## 6. Mechanism verification (CLAUDE.md Steps 0 to 5)

Recorded **before** any sweep, as the protocol requires. It is **INCOMPLETE**: Steps 3 and 4 have not
been run, which is an independent reason not to score cells even once LH-REQ lands.

**Step 0: what would make this run uninterpretable.** Asked before running, and it changed what I
did twice. (a) *Is the comparator about to change?* Yes: `hybrid-F` would be meaningless if it were not
the configuration already screened, so section 6.2 proves it byte-identical first. (b) *Does a run I
depend on key into my analysis?* Yes: the robot pool must be LH-REQ, which does not exist, so no cell
is scored. (c) *Is a default about to be restored?* The SS quality table is a placeholder that will be
replaced, which is why it is a declared input rather than policy code. (d) *Concurrent load?* The C6
decision-latency numbers are a measurement, so the test suites were held until that run finished
rather than run alongside it.

**Step 1: the causal chain.** If quality is representation-dependent and reconstruction cost grows
with context length (`FORMULATION.md` on Context Inertia's physical and semantic components), then on
a fleet where offered work exceeds the accelerator budget (section 5: 3.7x to 9.9x) a policy that
(i) orders work by value over urgency over work (C1), (ii) detects a request whose remaining work will
not fit its deadline (C2 laxity) and protects it by withholding competing cheap work (the dashcam
throttle), (iii) sends a cheaper representation when the full rebuild is predicted infeasible (C3),
and (iv) caps the cheap traffic that would otherwise fill every slot (C5), will deliver more
deadline-meeting answers than a policy ordering by deadline alone, **without** losing the dashcam
all-meet requirement.

**Step 2: each link instantiated.**

| causal link | implementing quantity | value / range in this run | varies as expected? | evidence |
|---|---|---|---|---|
| offered work exceeds budget | offered GPU-s vs 600 | 2,249 to 5,930 vs 600 | yes, 3.7x to 9.9x by size | section 5 |
| C1 orders by value/urgency/work | `idx(it)` in `decide` | robot 0.10627, dashcam 0.09000, SS 0.00100 | yes by type, **but SS is a placeholder** | section 1 |
| C2 detects infeasible-by-deadline | `laxity < k_r` | at risk 55/118 SS, ~2 robots at n=12 | yes, **but dominated by SS**, see 6.4 | section 6.4 |
| C2 protects by withholding | `c2_throttled_dash` | 1,516 / 2,083 / 14,919 | yes, grows with size | section 6.4 |
| C3 sends cheaper representation | `c3_recent` | 1 / 2 / 3 | yes, non-zero at every size | section 6.4 |
| C5 caps cheap traffic | AIMD cap 4..8, dashcam-only | reached, D140 proof 6,797 differing | yes | handover s2 |
| C6 improves on the component choice | chooser `deviations` | 0 / 1 / 42 | yes at 32, **CONSTANT 0 at 12** | section 6.3 |
| C6 horizon = own deadline | `horizon_for` | **5.0 s for every candidate** | **no: CONSTANT** | section 3 |
| C6 acts on SS requests | `c6_no_pending` | 118 of 118, 177 of 176 | **no: ABSENT** | section 6.4 |

**Two stopping conditions are recorded here.** The C6 horizon link is **CONSTANT** (section 3) and the
C6-on-SS link is **ABSENT** (section 6.4). Under Step 2 either is a stopping condition for the part of
the claim it implements: `hybrid-F6` may not be scored as "C6 simulates each candidate to its own
deadline", and no C6 result may be read as bearing on single-shot requests. The remaining C6 claim,
that a rollout over a baseline with a margin beats the baseline, is still testable at 32 devices
where deviations are non-zero, subject to the decision-period breach in 6.3.

**Step 2b: the switch reaches a decision.** Run on one cell before any scoring, as required.
`hybrid-F` against `hybrid-F6`, SS absent: **identical logs, 0 of 6,554 differing**, with the chooser
at 21 calls and 0 deviations. Per the rule this is an **ABSENT LINK at that cell, not a negative**. On
three-type cells C6 moves decisions at 16 (1 deviation) and 32 (42). The SS switch reaches a decision:
`ss_seen` 118 to 378 and `ss_at_risk` 55 to 196, with the throttle firing 337 to 1,374 periods. Each
switch arrived with its declared type and value: the constructed arms were inspected and `hybrid-F`
and `hybrid-F6` differ in exactly `c6`, with `k_r=1.5` (float), `defs="v2"`, `throttle_floor=2`
(int), `c3_always=False`.

**Step 3: trace one representative unit. NOT DONE.** No per-request trace showing every cost and
constraint charged, which budget bound the decision and the resulting outcome has been produced for a
three-type cell. The quantities exist in the dry-cell logs but are not assembled into a
hand-checkable unit trace. **This must be added before any sweep**, per the protocol's own terms.

**Step 4: negative control. NOT DONE.** The controls that apply here are: set all SS `cloud_accuracy`
equal to device accuracy and confirm C1's SS ordering collapses (partly implied, since that IS the
placeholder, so the run already sits at the control point: the uncontrolled condition does not exist
yet); set `kv_cap` to infinity and confirm admission-based policies converge; disable the throttle and
confirm the dashcam figures move. None has been run. **This must be run before any sweep.**

**Step 5: the alternative explanation.** "hybrid-F beats b7 on robot on-time" could be produced by
(a) C2 and C5 protecting at-risk robot work from dashcam contention, the claimed mechanism, or (b) C5
simply reducing total dashcam load so that robots queue behind less work, regardless of any at-risk
detection, which `hybrid2-c5` alone also does. The handover data already favours (b) over (a) on seed
0: **C5 alone recovers the same one feasible question per size** (19 of 19 and 24 of 24) that the full
C1+C2+C5 configuration recovers, so on that seed the at-risk machinery adds nothing measurable and the
cap explains the whole effect. What would distinguish them is a cell where the at-risk flag fires on a
robot and the throttle changes which robot completes, with C5 held fixed. Section 6.4 shows the flag
now fires almost entirely on SS requests, so on three-type cells the two explanations are **not yet
distinguished**, and the one-question margins the handover reports will not distinguish them either.

## 7. Proofs

### 7.1 Byte-identity with SS devices absent

Required before the freeze. Two-type cells (`ratio 50:50`, no SS devices), n=12, seed 0, 600 s dry,
digest over `decision.jsonl` ignoring `decision_latency_ms`, `t`, `arm`, `arm_version`, `note`, plus a
separate digest over the emitted representation map.

The "before" tree is HEAD with both changed files replaced by `git show HEAD:<path>` (only
`hybrid/hybrid_arm.py` and `policy/profiles.py` are modified), caches cleared between the two, and the
working tree restored afterwards. **PASS: 6 of 6 arms identical on all three observables.**

| arm | decisions before / after | digest before / after | rep digest before / after | identical |
|---|---|---|---|---|
| hybrid-base | 6,569 / 6,569 | `41787ba4154c7544` / `41787ba4154c7544` | `55698c595019d36d` / same | yes |
| hybrid2-c1c2k15c5 | 6,554 / 6,554 | `7a24269775f29070` / `7a24269775f29070` | `55698c595019d36d` / same | yes |
| hybrid2-c1c2k15c3c5 | 6,554 / 6,554 | `fe765bf9e62475ec` / `fe765bf9e62475ec` | `2abefea6cbdb136b` / same | yes |
| b7-edf-feasibility | 6,569 / 6,569 | `41787ba4154c7544` / `41787ba4154c7544` | `55698c595019d36d` / same | yes |
| eco-llm | 6,569 / 6,569 | `182b40f6f79ad7ff` / `182b40f6f79ad7ff` | `2abefea6cbdb136b` / same | yes |
| mooncake | 6,596 / 6,596 | `8521ce937d9b8c7e` / `8521ce937d9b8c7e` | `55698c595019d36d` / same | yes |

So the SS wiring and the profiles merge are inert when no SS device is present, which is what the
freeze requires. The structural reason is that every new branch is gated on
`q.category in self._ss_types` and the merge only ADDS keys to
`question_type_to_representation`; the run is the proof, not the reason.

**Positive control (check 7).** `hybrid-base` and `b7-edf-feasibility` carry the identical digest at
6,569 decisions, and 6,569 is the committed decision count from the handover report's identity proof
on this cell. So the control arm reproduces its committed value rather than only agreeing with its
treatment.

### 7.2 hybrid-F is a pure renaming of the screened configuration

Same cell, SS absent. `hybrid-F` must not be a new policy, only a new name for the configuration D140
and D141 already screened.

| arm | decisions | digest |
|---|---|---|
| hybrid2-c1c2k15c3c5 | 6,554 | `fe765bf9e62475ec` |
| **hybrid-F** | 6,554 | `fe765bf9e62475ec` |
| hybrid-F6 | 6,554 | `fe765bf9e62475ec` |

**PASS for hybrid-F:** byte-identical to the screened configuration, so every seed-0 and seed-4 number
in the handover report applies to `hybrid-F` unchanged.

**hybrid-F6 carries the SAME digest on this cell**, and the chooser's own counters say why: 21 calls,
**0 deviations, 21 defaults kept**. So C6 ran, scored its candidates and never beat the default here.
Under Step 2b an identical log is an **ABSENT LINK, never a negative**, but the distinction matters:
the plumbing is live (calls > 0, candidates scored), the mechanism simply moved no decision at this
cell. That is **category 4, unexercised, scoped to this cell and size**, not evidence about C6. It is
exercised at larger sizes (section 6.3).

### 7.3 C6 cost profile, and a decision-period breach at 32 devices

Three-type cells (40:40:20), seed 0, 600 s dry. **The robot pool here is MIXED, so these are cost and
mechanism numbers, not policy results**; D142 item 1 forbids MIXED for policy evaluation.

| n | arm | chooser calls | deviations | rollouts/call p50 | chooser p99 ms | decision p50 / p99 / max ms |
|---|---|---|---|---|---|---|
| 12 | hybrid-F | n/a | n/a | n/a | n/a | 0.121 / 0.153 / 0.304 |
| 12 | hybrid-F6 | 21 | 0 | 3 | 2.893 | 0.122 / **21.892** / 69.115 |
| 16 | hybrid-F | n/a | n/a | n/a | n/a | 0.142 / 0.176 / 0.323 |
| 16 | hybrid-F6 | 34 | 1 | 3.0 | 4.586 | 0.144 / **52.795** / 195.846 |
| 32 | hybrid-F | n/a | n/a | n/a | n/a | 0.273 / 0.308 / 0.466 |
| 32 | hybrid-F6 | 142 | 42 | 3.0 | 14.13 | 0.274 / **168.426** / 658.922 |

**hybrid-F6 breaches the 100 ms decision period at 32 devices**: p99 168.4 ms and a maximum of 658.9
ms, against the period the handover report calls "far inside" at 0.90 ms for the non-C6 arms. At 16
devices p99 is 52.8 ms with a maximum of 195.8 ms, so the maximum already exceeds the period there
too. `hybrid-F` stays at 0.27 to 0.31 ms at every size. **C6 as configured is not viable at 32
devices**, and this is a cost property, not a quality question.

**The cost is not the rollouts.** Rollouts per call are a flat 3 at every size and the chooser's own
p99 is only 14.13 ms at 32 devices, against a 168.4 ms decision p99. The missing ~154 ms is
`_c6_prepare`, which advances the policy-core mirror by calling `self._scorer.decide(obs)` once per
period. So C6's cost is dominated by maintaining the mirror, not by evaluating candidates, and
reducing the candidate set would not help.

**The at-risk candidates become live at 32 devices.** Deviations by kind: send to hold 24, **send to
RECENT-now 14, send to longer-throttle 4**. The handover reported RECENT-now and longer-throttle were
never chosen in its 12-device cell, which this reproduces (0 deviations at 12). They are chosen at 32.

### 7.4 The single-shot path fires, and two consequences

C2's SS rule reaches a decision, which is what section 2 claimed it would:

| n | SS questions seen | SS at risk | throttle periods | dashcam submissions throttled | exempt dashcams |
|---|---|---|---|---|---|
| 12 | 118 | 55 | 337 | 1,516 | 16 |
| 16 | 176 | 60 | 380 | 2,083 | 16 |
| 32 | 357 | 175 | 1,374 | 14,919 | 181 |

**Consequence 1, and it is a problem with MY rule, not with the data.** At 12 devices 55 of 118 SS
requests are flagged at risk, and `c2_robots_at_risk_while_throttling` is 57 against 55 SS, so **only
about 2 of the at-risk entities are robots: the throttle is now driven almost entirely by single-shot
requests.** The cause is quantified in section 2b: `k_r = 1.5 s` against a 2 s deadline leaves only about 0.1 s
of un-flagged life once the committed curve's work is subtracted, so the at-risk window covers 92 to
100 percent of an SS request's lifetime. Measured TTFT (cloud p50 0.3225 s) shows the headroom is
real, so the flag is geometry, not risk. Throttle periods rise from the handover's 47 (no SS, k 1.5) to 337, about 7x, and 1,516
dashcam submissions are held at 12 devices.

Dashcam all-meet is a headline requirement, so this is a predicted risk to it. I am **not** silently
changing the threshold: I stated the rule as "the same `k_r`, no new threshold" before coding and that
is what was built and measured. The alternative, scaling `k_r` to each device type's deadline (for
example `k_r = 0.3 x deadline`, giving 1.5 s for a robot and 0.6 s for SS), is a policy design choice
that belongs to you, and it must be settled **before** the freeze because afterwards it costs a new
labelled version and every cell redone under D79.

**Consequence 2: C6 cannot act on a single-shot request at all.** `c6_no_pending` is 118 at 12 devices
and 177 at 16, matching `ss_seen` of 118 and 176 almost exactly: the mirror holds no pending pieces for
an SS job, so C6 bails before proposing candidates. C6 is **robot-only in practice** and the SS half of
`hybrid-F6` is an ABSENT LINK. This is not fixable by tuning; it is what the mirror represents.

### 7.5 There is no pytest coverage of the hybrid arm, and the gap reads as a pass

`experiments/orchestration/live2/hybrid/test_hybrid.py` is **not a pytest file**: it is a CLI script
(`python test_hybrid.py identity | moves`) whose functions are `dry`, `identity`, `moves` and `pairs`,
none matching `test_*`. Pytest therefore collects **zero tests from it and exits reporting success**:

```
=== hybrid ===
no tests ran in 0.11s
```

This is the shape CLAUDE.md warns about under check 7: a check that cannot fail. Anyone running the
suites over `live2/hybrid/` sees no failure and concludes the arm is covered, when **nothing in the
pytest suites exercises `hybrid_arm.py` at all** - including the 78 lines of SS wiring and the
workload switch added here. The byte-identity and move proofs in this report are run by hand, not by
the suite, so they do not run on anybody else's change.

I did **not** run the script in its CLI mode: `identity()` writes into
`results/orchestration/live2/hybrid/`, which would overwrite the H100's committed proof files
(`hybrid_identity.json`, `hybrid_moves.json`, `hybrid_pairs.json`) with a regeneration from a modified
tree. The identity property it checks is already covered, and more strongly, by section 7.1, which
compares against HEAD rather than only against b7 in the same tree.

**Recommended before the freeze:** either rename the file so pytest stops claiming to cover it, or add
real `test_*` functions wrapping the base-identity and SS-absent-identity assertions so the freeze is
protected by the suite rather than by this report.

### 7.6 Still to run

- Step 2b per component on a **three-type LH-REQ cell**: blocked on LH-REQ.
- C6 rollouts per call and decision latency at 12, 16 and 32 devices: runnable, not yet run.
- Dry-run smoke cells (three-type, 12/16/32, seeds 0 and 4) for hybrid-F, hybrid-F6, b7, eco-llm,
  mooncake: blocked on LH-REQ for the robot pool.

## 8. Results consistency check

**1. Cross-check against committed measurements.**

| quantity | this run | prior committed | source of prior | ratio | agree |
|---|---|---|---|---|---|
| hybrid-base decisions, n=12 seed 0 600 s | 6,569 | 6,569 | `study_hybrid_live.md` identity proof | 1.00 | agree |
| b7 decisions, same cell | 6,569 | 6,569 | same | 1.00 | agree |
| hybrid2-c1c2k15c3c5 decisions | 6,554 | 6,554 (implied by the 6,569-of-6,569 base proof) | same | 1.00 | agree |
| decision latency p50, non-C6 arm | 0.121 to 0.273 ms | 0.81 to 0.91 ms (12 dev, LIVE run) | `study_hybrid_live.md` s3 | 0.15 to 0.34x | **see note** |
| robot questions, n=12 seed 0 | 21 | 21 | `study_hybrid_live.md` s0 | 1.00 | agree |
| robot questions, n=12 seed 4 | 27 | 27 | same | 1.00 | agree |
| VizWiz device accuracy | 0.6587 | 0.6587 | `vizwiz_val_device_summary.json` | 1.00 | agree |
| EgoThink device accuracy | 0.4714 | 0.4714 | `egothink_device_summary.json` | 1.00 | agree |

*Note on decision latency, a 3 to 7x disagreement, investigated and explained:* the committed 0.81 to
0.91 ms are from **live** 600 s runs against a real 32B server; these are **dry** cells with no server
and no GPU. A dry cell does strictly less work per decision, so a faster number is expected and the
direction is right. The two are **not comparable** and the dry figures are used only to compare
`hybrid-F` against `hybrid-F6` within this run, never against the committed live numbers. The 100 ms
breach in section 6.3 is therefore a **lower bound**: on live hardware the C6 arm would be slower
still.

**2. Physical plausibility.** Rollouts per call is 3 at every size, matching the candidate count for a
non-at-risk robot (default plus send/hold/decline minus the default's duplicate). Chooser latency
scales 2.9 to 14.1 ms p99 across 12 to 32 devices, roughly linear in calls (21 to 142), which is the
expected shape. Offered load in section 5 uses the committed `costs.py` curves directly.

**3. Distribution sanity.** Rollouts/call p50 is a **constant 3.0** at all three sizes. That is
expected, not a short-circuit: the candidate set is fixed by the component's proposal and only grows
for an at-risk robot, and `c6_offered_recent_and_throttle` is 4, 7 and 57, a small minority of calls.
Decision latency is reported as p50, p99 and max precisely because the p50 (0.274 ms at n=32) conceals
the p99 (168 ms): **a population median below the signal, with the effect concentrated on the C6
periods.** Reporting only the median here would have read as "C6 is free", which is wrong by three
orders of magnitude on the stratum that matters.

**4. Definition audit.** `RECENT` = `RECENT_WINDOW_TOKENS` = 467 tokens (live2 `cstate`), the same
value the coordinator charges and the same one the handover report used. "At risk" = laxity < `k_r`
with laxity = deadline - now - predicted remaining work including a cold rebuild of the believed
un-built history (`defs="v2"`, D140), unchanged. A "question" is one `recall_question` record keyed by
`question_id`, a content hash, confirmed in section 4 to be pool identity rather than a per-opportunity
id. **One name now carries two meanings and is flagged:** `c2_robots_at_risk_while_throttling` counts
single-shot requests as well as robots, because the counter sits on the generic `risk` flag. At 12
devices 55 of its 57 are SS. The name is wrong; the quantity is right.

**5. Claim linkage.** Nothing here bears on a `CLAIMS.md` claim yet, because no policy cell has been
scored. Sections 4, 5 and 6 are properties of the traces, the committed cost curves and the committed
chooser. The one result that will bear on a claim is the C6 decision-period breach, which bears on
whether a rollout-based policy is deployable at fleet scale at all, independent of quality.

**6. Proxy validity.** Two proxies, both stated and neither used for a conclusion. (a) **Device
accuracy as a proxy for cloud accuracy** in the SS quality table: this is the placeholder, it is
flagged in the file and in section 1, and its consequence (C1 ranking SS last) is recorded. It may not
support any SS conclusion. (b) **A dry cell as a proxy for a live cell** for decision latency: valid
as a lower bound only, as explained in check 1.

**7. Validate the control, not only the result.** The control is `hybrid-base`. It reproduces its own
committed value, 6,569 decisions and a digest equal to `b7-edf-feasibility` on the same cell, so the
control is not broken. The **positive control** for the byte-identity check is that four arms with no
SS code path at all (b7, eco-llm, mooncake, hybrid-base) must come out identical: they did, 4 of 4, so
the check is capable of returning "identical" and the identical results for the hybrid arms are not an
artifact of a check that always passes. The **negative** direction is also exercised:
`hybrid2-c1c2k15c5` and `hybrid2-c1c2k15c3c5` carry different digests (`7a24269775f29070` against
`fe765bf9e62475ec`), so the same check does distinguish arms that genuinely differ.

## 9. Blockers

1. **The LH-REQ trace option does not exist.** D142 item 1 requires robots to draw only from the 97
   LH-REQ questions and forbids MIXED for live policy evaluation. What is on origin is the
   stop-condition study and the question-set definition (`reports/study_lh_req.md` and
   `results/orchestration/live2/lh_req/lh_req_definition.json`); no code under `live2` or `policy`
   carries an LH-REQ filter. Ownership of the trace option has moved and it is **not** mine; I have
   not written a second filter, because two independently written filters over the same 97 would
   differ somewhere and nothing would catch it. The policy side is READY for it: the `-lhreq` arms
   exist, weighted from the committed definition file, and all eight LH-REQ categories are confirmed
   present in the quality table. Every robot-pool number waits on the trace option.
2. **The SS cloud quality table is a placeholder**, with the ordering consequence in section 1. The SS
   half of the headline is not measurable as a policy result until StudySS1-32B lands.
3. **No E-id.** `CLAUDE.md` "Before any task" requires finding or requesting an E-id in
   `research/EXPERIMENTS.md` and stopping to ask if no matching row exists. There is **no row for this
   work and none for the H100's `StudyHYBRID-live` either**: `grep` finds no `StudyPOLICY`, no
   `StudyHYBRID` and no `D142` in `EXPERIMENTS.md` or `STATUS.md`. The gap predates this session but
   the rule applies here. I have not invented a row. **`StudyPOLICY-F` needs registering before any
   cell is scored**, and the hybrid lineage arguably needs one too.
4. **`policy-F ready` not committed.** `CLAUDE.md` forbids CC from running `git add`, `git commit` or
   `git push` and requires stopping to ask. Raised rather than resolved; the tree is left uncommitted.

## Seeds and data

Development seeds 0 and 4 only. No seed 1, 2 or 3. No HOLDOUT.

## 10. D143 rulings A and B applied, and the SS table filled

### 10.1 Ruling B: k_r scales with each type's deadline

`k_r_frac = 0.3`, so the threshold is 0.3 x each item's own deadline: **1.5 s for a robot, 0.6 s for
a single-shot request.** `k_r` stays recorded at 1.5. `k_r_frac = None` keeps the committed flat
scalar, so every legacy arm and every run before this parameter existed is unchanged.

**Robots are unchanged exactly, not approximately.** `0.3 * 5.0` is `1.5` in float64 with no
representation error, both being 3/2, so every robot comparison is bit-identical to the flat
threshold and the entire effect of the ruling is confined to single-shot. That is what makes
byte-identity with SS absent the right proof for it, and section 11.1 runs it.

**THE FIRST IMPLEMENTATION OF THIS RULING WAS WRONG, and the proof is what caught it.** The deadline
horizon is `deadline_s` MINUS `arrival_s`, not `deadline_s`. On the policy's `RecallQuery`,
`deadline_s` is an ABSOLUTE time on the run clock, as `slack_s(now) = deadline_s - now` shows, while
the TRACE RECORD's field of the same name is the duration L. **Same name, two definitions, which is
exactly what check 4 exists to find and I did not run it before coding.** Multiplying the absolute
time made `k_r` grow with the clock: by t = 300 s the robot threshold was about 91 s against a 5 s
deadline, so effectively every robot was flagged at risk for the whole run.

The size of the break is the useful part of the record:

| cell | screened decisions | frozen decisions | differing |
|---|---|---|---|
| seed 0, n=12 | 6,554 | 6,431 | **6,253** |
| seed 0, n=16 | 8,087 | 8,026 | 7,691 |
| seed 4, n=12 | 6,472 | 6,365 | 6,398 |
| seed 4, n=16 | 7,872 | 7,837 | 7,808 |

Nearly every decision differed and the decision COUNTS diverged, so this was not a threshold
boundary effect that could be argued about. The control is what made it readable: the screened arm
gave **6,554** decisions at seed 0 n=12, its own committed figure from section 7.2, so the control
reproduced its committed value and the change was unambiguously mine.

The fix derives the horizon from the item's own two fields, `deadline_s - arrival_s`, which gives
exactly 5.0 for a robot and 2.0 for a single-shot request at any point in the run, so no new
constant and no per-type table is introduced. A non-positive horizon falls back to the flat scalar
and is COUNTED (`k_r_horizon_nonpositive`), rather than silently yielding a threshold of zero, which
would read as "never at risk".

**This is the register trap in its most ordinary form: a field can be correct and still be the wrong
quantity for the question.** `deadline_s` was the right name, present, typed, non-zero and varying
by condition, so Step 2 would have passed it. Only a byte-identity proof against a control with a
committed value caught it.

What it fixes, restated with the measurement that motivated it: against a 2 s SS deadline the flat
1.5 s made the at-risk test fire once slack fell below 1.84 to 2.06 s depending on prompt size,
which is **92 to 100 percent of an SS request's whole life**, while measured cloud TTFT p50 was
0.3225 s. At 12 devices 55 of 118 SS requests were flagged while only about **2** of the at-risk
entities were robots, holding **1,516** dashcam submissions. At 0.3 x deadline an SS request keeps
about 1.05 s of un-flagged life instead of about 0.1 s.

### 10.2 Ruling A: rc_accuracy reads the LH-REQ table, fitted on DEV

`_LhReqFittedProfiles` in `arms_policy.py`, selected by `quality_fit="lh_req_dev"` on the `-lhreq`
arms only, because the LH-REQ table is the right source only when robots actually draw from LH-REQ.
The bare `hybrid-F` / `hybrid-F6` pair keeps the trace-mix fit, which is correct for the MIXED
workload it names.

| quantity | trace-mix (before) | LH-REQ DEV fit (after) |
|---|---|---|
| cloud D2 | 0.4286 | **0.2500** [0.127, 0.434] |
| cloud RECENT | 0.3963 | **0.1071** [0.037, 0.272] |
| **representation gap** | **+3.23 pp** | **+14.29 pp** |

**The correction is 4.4x, not 7.3x.** The 7.3x figure in circulation compared trace-mix's +3.23 pp
against the **all-97** aggregate's +23.71 pp. Ruling A fits on **DEV**, whose gap is +14.29 pp, so
the ratio is 4.4x. Direction and conclusion are unchanged; the freeze carries 4.4x.

**The quantity reaches the consumer with its declared type and value, checked rather than assumed.**
Step 2 asks for the READ, not the place a value is set, so the mirror was inspected after configure:

| arm | mirror profiles class | cloud D2 | cloud RECENT | device D2 | gap |
|---|---|---|---|---|---|
| `hybrid-F6-lhreq` | **`_LhReqFittedProfiles`** | 0.250000 | 0.107143 | 0.107143 | **+14.29 pp** |
| `hybrid-F6` (MIXED) | `_MixWeightedProfiles` | 0.428600 | 0.396294 | 0.323078 | +3.23 pp |

So the selection is live on the arm that needs it and inert on the one that does not. The device
figures are worth noting beside each other: 0.3231 under trace-mix against 0.1071 on LH-REQ, because
the LH-REQ questions are far harder for the device, which is the whole reason the workload needs its
own table.

**Selected at configure time, never swapped after.** `arms_policy.live2_configure` builds the
engine, rollout and coordinator from `self.pf`, so swapping profiles afterwards leaves a hybrid
object. That was measured once and produced dashcam 0.0821 with 0 recalls served at 16 devices
against a true baseline of 0.8164 and 14 of 35, which is not the pre-fix policy but a broken one.

**An unmeasured (representation, tier) RAISES rather than falling back.** A silent fallback to the
trace-mix value would mix two question populations inside one comparison, which is the failure this
class exists to remove. Verified: `RICH` at tier `cloud` raises.

**THE DEVICE ENTRY IS A DECLARED SUBSTITUTION.** The consumer, `rollout.py:609-610`, asks for device
accuracy on **D2**. No device-on-D2 result exists on these questions: StudyO-Q4 holds exactly three
device arms, **4B-I x RECENT, 4B-T x RICH and 8B-I x RICH**, and D87 fixes the comparator at
4B-I x RECENT. So the ruled 0.1071 is the 4B x RECENT figure standing in for device-on-D2. It is
labelled in the table and in the class, not implied.

**One coincidence that must not be read as corroboration.** On DEV, cloud RECENT and the device both
score **3 of 28**. They are **not the same three questions**: the overlap is **1 of 3**. So the
aggregates agree and the items do not, and the equality is arithmetic rather than agreement. The
statement that does hold is the aggregate one, which is what the policy consumes: a 32B restricted
to the recent window scores the same as the 4B on these questions, so model size buys nothing at
fixed representation here. "The two models agree" is not supported.

### 10.3 Two numbers for one axis, reported rather than reconciled

| consumer | robot quality value | source |
|---|---|---|
| **C1's ordering index** | **0.13204** | `_quality_values("lh_req")`: the committed RC table re-weighted by the LH-REQ category mix, per **D142 item 2** |
| **C6's mirror** | **0.142857** | the **DEV-fitted LH-REQ** cross-tier gain, per **D143 ruling A** |

One policy now carries **two numbers for the robot quality axis**, from two different question
populations, differing by 1.08x. This is left as the two rulings specify and marked **PROVISIONAL**:
ruling A names `rc_accuracy` specifically, and D142 item 2 already ruled on C1's table, so moving C1
as well would be overriding D142 item 2 rather than applying D143. **Worth settling**, but it does
not change any ordering, and 1.08x is far smaller than the 4.4x the ruling removed.

### 10.4 The SS quality table, filled from the SS2 DEV split

`results/orchestration/prof1/ss_quality.json`, still a declared input file, so this was a data update
and the policy code did not change. `refspatial` and `realworldqa` entries were **required**, not
optional: an SS question's `category` is its dataset name, `_ss_types` is built from this file's
keys, and `representation_for` RAISES on an unknown type, so without them the SS branch never fires
and an SS question cannot execute at all.

| dataset | metric | n (DEV) | device | cloud 32B | **gain (DEV fit)** | gain on held-out EVAL | DEV / EVAL |
|---|---|---|---|---|---|---|---|
| refspatial | point-in-mask | 83 | 0.2048 | 0.3922 | **+0.1874** | +0.0919 | **2.04x** |
| realworldqa | exact match | 229 | 0.6419 | 0.7249 | **+0.0830** | +0.0466 | **1.78x** |

**The DEV fit overstates what the held-out part shows, by about 2x on both datasets.** That is a
property of fitting on 83 and 229 questions, not a defect in the split, and it means C1 values an SS
request above what EVAL supports. It is reported rather than corrected, because correcting it with
the EVAL number would be fitting on the scored set, which D6 forbids. The EVAL figures are recorded
in the file under a key marked **not for the policy**.

`vizwiz` and `egothink` are **retained but unused**, and say so: D143 fixes the pool at RefSpatial
and RealWorldQA, so an SS category is never `vizwiz` or `egothink` unless `ss_question_set="ss1"` is
selected, in which case those entries are still **placeholders** and anything reading them must say
so. `_placeholder` is now False with an explicit `_placeholder_scope`, because the part of the table
the policy draws from is measured while two retained entries are not.

### 10.5 The SS ordering has flipped, and the metric incomparability now binds

| device type | C1 value, before (placeholder) | C1 value, now |
|---|---|---|
| robot | 0.10627 | 0.13204 |
| dashcam | 0.09000 | 0.09000 |
| SS refspatial | **0.00100** (floor) | **0.18742** |
| SS realworldqa | **0.00100** (floor) | **0.08297** |

Under the placeholder, cloud equalled device, the gain was 0, C1's SS value fell to the 1e-3 floor
and **C1 ranked every single-shot request last at about 106 to 1 against a robot.** With the measured
DEV values the gains are positive and **refspatial now outranks a robot.** Every SS cell measured
under the placeholder is superseded, exactly as predicted when the placeholder shipped.

**Check 4 now changes an ORDERING rather than only a reported number.** C1's index compares these
four values as if they shared a unit, and they do not: the robot and dashcam terms are MCQ-accuracy
and challenge-mAP differences, refspatial is a point-in-mask fraction, realworldqa is exact match. A
+0.187 point-in-mask gain is **not** "more valuable" than a +0.132 MCQ-accuracy gain in any measured
sense; it is a different quantity. **The ordering C1 produces is therefore a convention, and it must
not be reported as evidence that single-shot work matters more than robot recall.** That caveat was
already in the file as `_metric_incomparability` while the SS value sat on the floor and the
ordering was insensitive to it. Filling the table is what made it bind.

### 10.6 test_hybrid.py is now real pytest, and the gap that read as a pass is closed

Five `test_*` functions, all passing in 6.2 s, every one writing only to pytest's `tmp_path`:

| test | what it asserts |
|---|---|
| `test_base_identity_matches_b7` | **the one property that stops the freeze**: `hybrid-base` byte-identical to committed `b7-edf-feasibility` on seed 0 n=6 and seed 4 n=8 |
| `test_ss_absent_identity` | at ratio 50:50 the SS wiring is inert: `ss_seen == 0` and zero differing decisions against an emptied SS table |
| `test_frozen_configs_registered_and_construct` | all four frozen arms in `CONFIGS` and `arms.ARMS`, constructing with the frozen settings |
| `test_frozen_config_moves_decisions` | Step 2b: `hybrid-F` differs from `hybrid-base`, **80 differing decisions** at seed 0 n=6 |
| `test_lh_req_workload_changes_the_value_term` | the workload switch reaches the value term: 0.10627 mixed against 0.13204 lh_req, both non-zero and unequal, unknown workload raises |

**The defect this closes.** The file's functions were `dry`, `identity`, `moves` and `pairs`, none
matching `test_*`, so pytest collected **zero tests and exited reporting success**. Anyone running
the suites over `live2/hybrid/` saw no failure and concluded the arm was covered, when nothing in
the pytest suites exercised `hybrid_arm.py` at all, including the SS wiring and the workload switch.
A check that cannot fail.

**The committed CLI still works unchanged**, so no driver script breaks: `identity`, `moves` and
`pairs` keep their `out_dir` default and their existing behaviour, with the shared work refactored
into helpers that take an output directory. The CLI's `identity()` was **not** run against its
default, because that writes into `results/orchestration/live2/hybrid/` and would overwrite the
H100's committed `hybrid_identity.json`, `hybrid_moves.json` and `hybrid_pairs.json` with a
regeneration from a modified tree. Exercised with the output redirected instead: all four committed
CLI cells identical, 773 / 1,212 / 978 / 1,538 decisions.

Two scope limits, stated rather than left to inference. The pytest tests do not cover the C6 chooser
beyond construction and a smoke call, and they do not cover the three-class 40:40:20 ratio with SS
devices present; an SS-present move proof needs a cell large enough to deal assistive devices, and
it is section 11.2's job rather than the unit suite's. Separately, the CLI `pairs()` reports 0
differing for all five v1 screening comparisons at a tiny cell (seed 0, n=6) where the committed
proof used n=12, so **small cells are not sufficient for the v1 pair proofs** and the unit test
asserts only on `hybrid-F` against base, where the difference is present at n=6.

`fleet/tests/test_live2_fleet.py` still reports **234 of 234**.

## 11. The freeze proofs, and three findings that change what the freeze means

Four proofs, in `experiments/orchestration/live2/hybrid/policy_f_proofs.py`, output in
`results/orchestration/live2/hybrid/policy_f_proofs.json`. Every cell here is a DRY run: no GPU, no
server, stub bridge. They are decision-path proofs, so no timing or quality number in this section
is a measurement of anything.

Proof 4 did not exist when this section was planned. It was added because proof 2's C1 row came back
zero, and the only honest way to classify that zero was to test it.

### 11.1 Proof 1: ruling B is inert on robots

`hybrid-F` against the screened `hybrid2-c1c2k15c3c5`, two-type cells (50:50, no SS), seeds 0 and 4,
n = 12 and 16, 600 s. **All four byte-identical**: same decision counts (6,554 / 8,087 / 6,472 /
7,872), same digests, 0 differing, `ss_seen` 0 in every cell.

0.3 x 5.0 is exactly 1.5 in float64, so a robot's at-risk threshold is bit-identical under the
ruling and the whole effect is confined to single-shot. This is what lets the screened seed-0 and
seed-4 numbers carry over to the frozen arm unchanged. The comparison is order-sensitive on purpose:
byte-identity including log order is the claim being made.

### 11.2 Proof 2: Step 2b per component, on a three-type LH-REQ cell

`hybrid-F6-lhreq`, seed 0, n = 20, 1200 s, 40:40:20, LH-REQ robots and SS2 single-shot. Each
component switched off against the full arm, 16,361 decisions in the base log.

| component | decisions moved | positional mismatch | reading |
|---|---|---|---|
| C1 ordering | **0** | 0 | ABSENT LINK, cancelled by geometry. See 11.4 |
| C2 at-risk and throttle | 712 | 12,071 | moves decisions |
| C3 representation | 459 | 6,026 | moves decisions |
| C5 cap and AIMD | 461 | 11,986 | moves decisions |
| C6 counterfactual chooser | **3** | 11,794 | moves decisions, barely. See 11.3 |

**The two columns are different quantities and only the first answers Step 2b.** `differing` is a
multiset difference over (period, action kind, opportunities, representation, defer_s): a
reordering scores 0, and an admit that became a defer scores 2. `differing_positional` is the
original order-sensitive count, which counts log positions that stopped lining up, so one early
divergence desynchronises everything after it. The two differ by 17x on C2 and by 3,931x on C6. The
positional count is kept beside the setwise one only to show how far apart they are; it is the right
metric for 11.1 and the wrong metric here.

That defect was mine and it was found by proof 4, not by inspection: the value control's only
non-zero cell, 2 of 16,361, turned out to be two `release_recall` rows swapping places at t = 527.0
with both items released either way. A number that survives every arithmetic check while answering a
different question is the failure this report has hit three times now.

C3's first difference is a genuine kind change (`release_recall` with representation RECENT against
`defer` at defer_s 0.5, same opportunity `opp0002665`), so C3's move proof does not rest on the
count alone.

### 11.3 C6 was dead in every -lhreq cell, and the cause was ruling A plus a swallowed exception

Before the fix, on this cell: `c6_scorer_error` **251 of 251** periods that had recall work,
`c6_calls` **0**, and `hybrid-F6-lhreq` byte-identical to `hybrid-F-lhreq` at all six dry smoke
cells, while `live2_describe` still reported `c6=True` and the arm still carried the F6 name.

The exception being thrown away:

```
MissingEvidence: the LH-REQ DEV fit carries no entry for representation 'N1' at tier 'device',
and this class deliberately does NOT fall back to the trace-mix table
```

`_LhReqFittedProfiles` (section 10.2) mapped four (representation, tier) pairs. The escalation path
reads **five**: cloud RICH, cloud RECENT, cloud D2, device D2, device N1. Four of the twelve
question types map to RICH (`counting_objects_events`, `object_comparison`,
`temporal_ordering_recognition`, `visual_detail_recall`), and `_device_accuracy` asks for N1 at the
device tier whenever a question's temporal reference falls outside the device's window. The class
raises on both by design, to refuse mixing two question populations inside one comparison.
`_c6_prepare` caught that in a bare `except Exception`, counted it, and returned False, so `c6_live`
was False on every period.

**This is the declaration-read-as-observation family seen from the other side.** The usual shape is
a field that is written and never read. Here the component was configured, named, described and
counted, and the thing that disabled it was recorded in a counter nobody had asked for. The arm
reported itself as F6 throughout.

Two fixes. `MissingEvidence` is now re-raised rather than counted: a missing committed quantity is a
configuration error, not a transient, and swallowing it is what converted a bug into a non-event.
And the two missing conditions resolve, by substitution (11.5).

After the fix, same cell: `c6_calls` **254**, `c6_dev_send_to_hold` **6**, `c6_scorer_error`
**0**, and C6 moves **3** decisions.

**Three decisions in 1200 s, for a full policy-core mirror evaluation every period.** C6 clears
Step 2b and it clears the port rule that an arm's characteristic decision must occur at least once
(254 calls, 6 deviations). It does not clear any bar about being worth its cost, and section 7.3
already recorded a decision-period breach at 32 devices. Whether to pay that cost for 3 decisions is
a design question for the user, and it bears directly on whether the `_c6_prepare` speed fix is
worth doing at all.

Two regression tests now exist, in `test_hybrid.py`:

- `test_c6_actually_fires_on_the_lh_req_workload`: asserts `c6_scorer_error == 0`, `c6_calls > 0`,
  and that F6 differs from F. This is the port rule applied to a component.
- `test_lh_req_dev_fit_covers_every_condition_the_policy_reads`: iterates `_RC_TABLE_NAME`, requires
  every one of the five conditions to resolve, and requires every stand-in to be declared in
  `_SUBSTITUTED`. This one would have caught the defect at the first cell.

### 11.4 Proof 4: the value term is decision-inert, so ruling A prices nothing

The value and quality tables are written at `hybrid_arm.py:260` (dashcam) and `:311-312` (recall and
SS), and read in exactly one place: C1's ordering index at `:317`. So if C1 cannot move a decision,
ruling A has no path to one. Four perturbations, seed 0, n = 20, 1200 s, both frozen arms:

| perturbation | decisions moved (F) | decisions moved (F6) |
|---|---|---|
| every value equal (0.1) | **0** | **0** |
| dashcam 100x the others | **0** | **0** |
| robot 10,000x dashcam | **0** (2 positional) | **0** (2 positional) |
| SS 1000x | **0** | **0** |

Flattening the whole table to one constant is the canonical Step 4 control for a quality-driven
claim, and it moves nothing. The 2 positional entries are the transposition described in 11.2.

**Why it cancels, structurally rather than at this cell.** Dashcam items all carry one constant
value (`values["dashcam"]`) and one constant work (`epi_s`), so the index
`value / max(slack, 0.1) / work` is a monotone function of slack, and slack is monotone in the
deadline: C1's dashcam order is IDENTICALLY EDF order, and the tiebreak `(dl, id)` is the same on
both branches. Every recall item is kept unconditionally by `_cap_dashcam_only` (`:436-437`) and
never consumes the dashcam budget, so C1's placement of robot and SS items reaches only the emitted
action sequence, the `order` channel already recorded in this project as unexpressible.

So the classification is **cancelled by geometry** on the dashcam axis and **unexpressible** on the
recall axis, not unexercised. The first draft of proof 2 labelled it "category 4, unexercised"; that
was text, not a measurement, and it was wrong.

**What this costs.** Three things recorded earlier in this report describe a quantity the frozen
policy does not read:

- ruling A's swap of `rc_accuracy` to the LH-REQ DEV fit (10.2);
- the 4.4x correction to the half-one mispricing, which the freeze was to carry;
- the SS ordering flip that put refspatial (0.18742) above a robot (0.13204) (10.5).

None of them can change a decision in `hybrid-F` or `hybrid-F6`. The ordering flip in particular
must not be read as evidence that single-shot work matters more than robot recall: it is a
convention attached to an inert axis, and 10.5's warning now has a measurement behind it.

Making the value term bind is a policy change, not a data update: C1's index would have to reach a
selection that is actually contested. That is the user's decision and nothing here anticipates it.

### 11.5 Two substitutions, PROVISIONAL

The LH-REQ DEV split measures three conditions (cloud_D2 25.000 %, cloud_RECENT 10.714 %,
device_4B_RECENT 10.714 %, all on 28 questions). The policy reads five. The two stand-ins:

| condition | stands in as | direction of the error |
|---|---|---|
| cloud RICH | cloud_D2 | D2 is the fullest cloud condition measured and RICH is at least as informative, so this credits the cloud with LESS |
| device N1 | device_4B_RECENT | N1 is the device WITHOUT history coverage, so its true accuracy is at most the covered device's: this credits the device with MORE |

Both lean the same way, toward a smaller cross-tier gain, so neither can manufacture an escalation
advantage. That is the same direction `escalation.py:158-160` argues for its own coverage default.
Recorded in `_SUBSTITUTED` and asserted by the test in 11.3. The alternative is for the LH-REQ fit
to measure RICH and the uncovered device, which is new measurement rather than a mapping.

Given 11.4, these substitutions currently feed only the C6 mirror, since the hybrid arm's own value
table is inert.

### 11.6 Proof 3: dry smoke, 30 of 30 cells

16 / 20 / 32 devices x seeds 0 and 4 x `hybrid-F-lhreq`, `hybrid-F6-lhreq`, `b7-edf-feasibility`,
`eco-llm`, `mooncake`, all at 1200 s and 40:40:20. Every cell ran; no errors. **Dry-run screening,
not a result.**

F and F6 differ at five of six cells by 18, 1, 38, 260 and 6 positional decisions. They are
identical at **n = 16, seed 4**, so C6 is an absent link AT THAT CELL. That is a per-cell statement
and not the global one the pre-fix run appeared to show.

### 11.7 The SS at-risk flag is now constant at never

`ss_at_risk` is **0** in all six smoke cells, against 356 to 717 SS requests seen per cell.

Ruling B set the SS threshold to 0.3 x 2.0 s = 0.6 s. The flag the ruling was written to fix was
constant at always-on over 92 to 100 % of an SS request's life; it is now constant at never. A
constant where a distribution is expected is consistency check 3, and this is the same defect with
the sign reversed. C2's single-shot path (D142 item 3) exists to throttle dashcam frames for a
near-deadline SS request, and at 0.6 s against a 2 s deadline it does not fire.

Nothing was changed in response: the ruling is the user's and the finding is recorded rather than
acted on.

### 11.8 Controls and what is still open

`fleet/tests/test_live2_fleet.py` **234 of 234** through its own runner, so the two-type path,
including its scorer and attainment checks, is unchanged by everything in this section.
`test_hybrid.py` **7 of 7**, after fixing an import-order fragility in
`test_lh_req_workload_changes_the_value_term` that let it pass only when another test had already
inserted the hybrid directory into `sys.path`.

Open for the user, each affecting what this freeze means rather than whether it holds:

1. **Grid size.** 20 devices offers 14.67 req/s of dashcam monitor load, 97 % of the committed
   15.10 req/s one-frame closed-loop peak (StudyD7b); 16 offers 11.01 req/s, 73 %. The H100's
   transport errors at 20 are an overload signature with two precedents (StudyMOT1, StudyD7), not a
   harness defect. 16 and 18 (7 dashcam devices, 12.83 req/s, 85 %) would both be feasible, and 18
   holds the same pooled robot counts as 16 (24 / 20 / 25 / 20 at seeds 0 / 4 / 5 / 6). The size axis
   was fixed from question counts alone, which is the demand half of D97 and not the capacity half.
2. **Over-context counting.** One LH-REQ session (1848337166005249) carries 33,781 history tokens at
   a question, above the 32,768 context, at seed 0 at both ruled sizes and at neither size at seed 4.
   StudyRH8 and StudyRH5 excluded such questions from the denominator, but did so because they were
   identical in every policy; here they are not, because the arm chooses the representation.
3. **Whether an inert value term is acceptable in a frozen policy** (11.4).
