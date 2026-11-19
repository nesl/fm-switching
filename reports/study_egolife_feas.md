# StudyEGOLIFE-feas: EgoLifeQA annotation-only feasibility check for D139

Date: 2026-11-19
Machine: flash (CPU only, no GPU, no inference)
Script: `experiments/datasets/egolife_feasibility.py`
Output: `results/datasets/egolife_feas.json`
Annotation copy: `results/datasets/egolife/EgoLifeQA_A1_JAKE.json`
Scope: **annotation-only. No video downloaded.** Bytes fetched: 27 MB. Disk 51 GB free before and after.

---

## HEADLINE: THE USABLE COUNT IS 3. OFFLINE CORROBORATION ONLY.

The decision rule as written: **gap > 2 min, D2 history <= 19,400 tokens, `need_audio` false,
`need_name` false**, over the same-day single-target analysis set.

| step | count | denominator |
|---|---|---|
| same-day single-target analysis set | 281 | 500 rows read |
| after gap > 2 min | 281 | 281 (the minimum gap in the set is 292 s, so this filter removes nothing) |
| after D2 history <= 19,400 tokens | **20** | 281 |
| after `need_audio` false | **15** | 281 |
| after `need_name` false | **3** | 281 |

**USABLE COUNT = 3 of 281. The threshold is 50. 3 < 50, so the rule fires:
OFFLINE CORROBORATION ONLY.**

The three are IDs **216, 243, 423** (EventRecall 2, EntityLog 1).

**This is not a borderline call and it does not depend on the exclusions.** A constructed upper
bound, repairing every excluded multi-target row in the most favourable way available (nearest
parseable target, same day, all four filters still applied), adds **1**, for **4**. Relaxing the
token threshold from 19,400 to 32,768 gives **5**. **Every variant is under 50 by more than an
order of magnitude.** EgoLifeQA can corroborate a D139 finding offline; it cannot support a
trace-driven workload.

**`need_name` is the binding filter, not the token budget.** It removes 12 of the 15 that survive
everything else: 197 of 281 analysis-set questions require identity recognition. `need_audio`
removes 5 of 20, and is the more fundamental objection, since a question requiring audio is not
answerable from D2 frames at all.

---

## 0. Step 0: what would invalidate this run

Asked before any download. Five answers:

1. **Wrong artefact.** `lmms-lab/EgoLife` also ships `EgoIT/EgoLife_QA.json`, which is named like
   the benchmark and is not it. Checked (§6).
2. **A download that pulls video.** The repository is 512 GB and 32,001 of its 32,817 files are
   mp4. Mitigated by fetching named files by path, never a snapshot, and checking `x-linked-size`
   before each fetch.
3. **A success signal that is not success.** Every fetch was verified by parsing the artefact, not
   by curl's exit code (§1).
4. **A naive time parser.** This one fired. 13 rows pack several timestamps into the single `time`
   string (§2.2). A reader that takes the first 8 characters gets a plausible number from a
   malformed field and never notices.
5. **A count reported without its coverage.** Addressed by making the four buckets in §2 exhaustive
   and reporting every later figure against the bucket it came from.

Disk before: **51 GB free**. Disk after: **51 GB free**. The 15 GB stop condition was never
approached.

---

## 1. Licence and gating, recorded first

| field | value |
|---|---|
| repository | `lmms-lab/EgoLife` (HuggingFace datasets) |
| revision read | `143fb319be7aa5ae210c936bf4f0f3a86092afb0`, lastModified 2025-03-13T17:47:56Z |
| `gated` | **`false`** |
| `private` / `disabled` | `false` / `false` |
| licence tag | **`license:mit`** |
| language tag | `zh` |
| EgoLifeQA files in the release | **exactly one: `EgoLifeQA/EgoLifeQA_A1_JAKE.json`** |

Card front matter, verbatim:

```
---
language:
- zh
license: mit
task_categories:
- video-text-to-text
tags:
- video
---

Data cleaning, stay tuned! Please refer to https://egolife-ai.github.io/ first for general info.

Checkout the paper EgoLife (https://arxiv.org/abs/2503.03803) for more information.

Code: https://github.com/egolife-ai/EgoLife
```

**No access agreement, no signup wall, no approval queue. The StudyOEQA licence gate does not
fire.** Caveat: the MIT declaration is a HuggingFace card tag only. There is no LICENSE file in the
repository and the README text does not restate it.

Contrast with S-EMBER for calibration: `facebook/S-EMBER` returned `GatedRepoError: 403` and
required a signed CC BY-NC 4.0 form (`reports/study_h_sember_structure.md` §E1). EgoLife is the
opposite position.

### Integrity, verified rather than assumed

| file | declared `x-linked-size` | bytes received | verified how |
|---|---|---|---|
| `EgoLifeQA/EgoLifeQA_A1_JAKE.json` | 591,255 | 591,255 | parsed as JSON, 500 objects, expected key set |
| `README.md` | 315 | 315 | read in full, reproduced above |
| `EgoLifeCap/DenseCaption/A1_JAKE/DAY1/A1_JAKE_DAY1_11000000.srt` | 87,852 | 87,852 | parsed, 2,956 caption blocks |
| `EgoIT/EgoLife_QA.json` | 26,844,531 | 26,844,531 | parsed as JSON, 33,352 objects |

`sha256(EgoLifeQA_A1_JAKE.json) = 688ae079f458132f13150711b7e099fbe4fdedd97f19f5a33bdebb7bfde74a52`.
No upstream checksum is published, so this is recorded for our own reproducibility and is **not** a
verification against the publisher.

### The GRAVEYARD entry, recorded and set aside

EgoLife is closed in `research/GRAVEYARD.md` (`3f2002c`). **That closure was answering a different
question: whether EgoLife isolates context compression as the failure mode. This check is for
D139, questions that need history.** The closure is recorded here and not re-litigated.

Two facts from it do bear on D139 and are carried forward rather than re-argued:

- **Recurring failure mode 2 names EgoLife directly**: captioning-pipeline datasets need a working
  perception layer, and a captioner that degrades at reduced frame budgets confounds the signal.
  This check found that concern **aggravated, not merely untested: the dense caption layer is
  Chinese-only** (matching the card's `language: zh`), while the QA carries parallel English. That
  is the FindingDory failure exactly, and annotation availability does not touch it.
- For the record, the closure's own stated reason is now **half out of date**: `EgoLifeCap/` carries
  407 DenseCaption and 402 Transcript SRT files covering **all six participants and all seven
  days**, 49.61 MB, about one caption per 1.2 s. What remains missing is the **QA**: 1 of 6
  participants, 500 of the paper's 3,000 questions, absent from GitHub too. Noted, not pursued.

---

## 2. Parsing, and the four exhaustive buckets

**Gap = `query_time` minus `target_time`, HHMMSSff.** The `ff` sub-second field is **dropped**, so
every gap in this report has 1 s resolution. **Same-day single-target rows only.**

### 2.1 Coverage. Every one of the 500 rows lands in exactly one bucket.

| bucket | n | share of 500 |
|---|---|---|
| **analysis set** (same day, single target, parseable, positive gap) | **281** | **56.2 %** |
| excluded: `time_list` (several evidence timestamps) | 36 | 7.2 % |
| excluded: cross-day (target on an earlier day than the query) | 170 | 34.0 % |
| excluded: malformed | 13 | 2.6 % |
| total | **500** | 100 % |

**281 of 500 is the denominator for every count in §3, §4 and the headline.** 43.8 percent of the
file is excluded, and the exclusions are not uniform: cross-day rows are long-gap by construction
(median wall-clock gap 120,938 s, 33.6 h), so excluding them removes almost entirely from the
`> 30 min` bin and barely touches the short-gap bins the decision rule cares about.

### 2.2 The 13 malformed rows are a parser trap, not an empty field

All 13 pack **several timestamps into the single `time` string** with embedded day markers, for
example:

```
{"date": "DAY1", "time": "11153417DAY1_11181201"}
{"date": "DAY4", "time": "17044917DAY4_20593813DAY6_19483807"}
```

These are multi-target rows serialized into the single-target field. **A reader that takes the
first 8 characters returns a plausible gap from a malformed field and raises nothing.** Counting
them with the 36 declared `time_list` rows, the real multi-target population is **49 of 500, 9.8
percent**, of which **13 are undeclared**.

Other defects found, all reported rather than silently handled:

- 1 row writes the date as `Day1` rather than `DAY1`; parsed case-insensitively.
- `time_list` lengths: 2 (31 rows), 3 (3), 6 (1), 7 (1). The single `date` applies to the whole
  list, which for ID 484's seven timestamps spanning 12:07 to 20:46 is possible but unverifiable.
- `type_chinese` has two spellings for EntityLog (`实体日志` 117, `实体日记` 8) where `type` has
  one, so a category table built on the Chinese field differs from §3.2.
- 0 rows in the analysis set have a non-positive gap.

---

## 3. Counts (denominator: 281 analysis-set questions, A1_JAKE, 1 of 6 participants)

Register: **observed count** throughout this section.

### 3.1 By gap

| bin | n | share of 281 |
|---|---|---|
| **up to 7 min** | **18** | 6.4 % |
| **7 to 15 min** | **28** | 10.0 % |
| **15 to 30 min** | **28** | 10.0 % |
| **over 30 min** | **207** | **73.7 %** |

Spread: min 292 s, p25 1,495 s, **median 6,375 s (1 h 46 m)**, p75 19,140 s, max 42,303 s (11.8 h).

**EgoLifeQA is a multi-hour benchmark, not a minutes-scale one.** This is a statement about the
dataset's fit to our cost model, not about its quality. Over the full 500 rows including the
cross-day exclusions the skew is sharper still: 419 of 500 have evidence more than 30 min back,
median 5 h 52 m, max 6.0 days, and **the median question across all 500 would need 951,241 D2
tokens, 49x our budget**.

### 3.2 By type

| type | n | up to 7 | 7-15 | 15-30 | over 30 |
|---|---|---|---|---|---|
| RelationMap | 76 | 8 | 6 | 4 | 58 |
| EventRecall | 76 | 2 | 3 | 7 | 64 |
| EntityLog | 66 | 4 | 13 | 10 | 39 |
| TaskMaster | 42 | 3 | 5 | 5 | 29 |
| HabitInsight | 21 | 1 | 1 | 2 | 17 |
| **total** | **281** | **18** | **28** | **28** | **207** |

EntityLog is the only type with a usable mass at 15 min or less (17 of 66). The smallest cell is 1,
so nothing here is powered for a per-type conclusion.

### 3.3 With and without `need_audio` and `need_name`

Each split carries its own denominator of 281.

| | n | up to 7 | 7-15 | 15-30 | over 30 |
|---|---|---|---|---|---|
| `need_audio` **true** | 137 | 5 | 7 | 12 | 113 |
| `need_audio` **false** | **144** | 13 | 21 | 16 | 94 |
| `need_name` **true** | 197 | 11 | 18 | 20 | 148 |
| `need_name` **false** | **84** | 7 | 10 | 8 | 59 |

Joint, over 281:

| | `need_name` false | `need_name` true |
|---|---|---|
| `need_audio` false | **34** | 110 |
| `need_audio` true | 50 | 87 |

**Only 34 of 281 (12.1 percent) require neither audio nor identity recognition**, before any gap or
token filter. That is the ceiling the decision rule is working against, and it is why the usable
count is 3 rather than 20.

---

## 4. D2 history tokens, from live2's own accounting

**Taken from live2, not estimated.** `experiments/datasets/egolife_feasibility.py` imports
`d2_batch_tokens` and `d2_frames_in` read-only from
`experiments/orchestration/live2/fleet/data_sources.py` (StudyRH4 constants: 2.0 s stride, 352x256,
**90 tokens per image**, **31-token header** on the first batch). Nothing was re-derived.

**Denominator: the 46 analysis-set questions at 15 min or less** (18 at up to 7 min + 28 at 7-15).

| | value |
|---|---|
| tokens, min / median / max over the 46 | 13,171 / 20,146 / 39,991 |
| tokens at a flat 900 s window | 40,531 |
| **fit under 19,400** | **20 of 46** |
| fit under 19,381 (the committed D132 breakeven) | **20 of 46**, the same set |
| **fit under 32,768** | **39 of 46** |
| largest gap under 19,400 | 430.4 s = **7 min 10 s** |
| largest gap under 32,768 | 727.5 s = **12 min 8 s** |

**The 19.4k budget buys 7 min 10 s of D2 history and the 32k context buys 12 min 8 s.** So the
19.4k threshold cuts almost exactly at the brief's "up to 7 min" bin boundary: all 18 of the
up-to-7-min questions fit, plus 2 of the 28 in the 7-15 band. Raising the threshold to 32k adds 19
more, which is the single largest available lever on the token filter, and it still leaves the
usable count at 5 because `need_audio` and `need_name` bind harder.

---

## 5. Disk for the needed windows

Basis: **the brief's 30 s clips at 14.5 MB each**, which implies 483 kB/s. For calibration, the
rate I measured independently from HuggingFace file metadata (818 exactly-30-s-spaced A1_JAKE DAY1
segments, median size / 30 s) is **526 kB/s**, so the brief's figure is 0.92x mine and the two
agree well inside the 2x flag. The brief's figure is used for every number below.

Clips are counted on the release's own 30 s grid and **deduplicated**, because nearby questions
share video.

| set | denominator | clips, summed | clips, deduplicated | GB summed | **GB deduplicated** |
|---|---|---|---|---|---|
| all 46 at 15 min or less | 46 | 821 | 672 | 11.90 | **9.74** |
| **the 3 usable questions** | 3 | 38 | 38 | 0.55 | **0.55** |

**The headline disk figure is 0.55 GB for the 3 usable questions, and 9.74 GB if the whole
15-minutes-or-less band were fetched.** Neither was fetched. 9.74 GB against 51 GB free on a disk
at 99 percent with another session's sweep growing is a fifth of remaining headroom, which is
affordable but would not be spent for a workload the decision rule has already ruled out.

Annotation-only layer for comparison: 89.8 MB in total (QA 0.59 MB, DenseCaption 21.19 MB,
Transcript 28.42 MB, EgoIT 39.63 MB), of which **27 MB was actually downloaded**.

---

## 6. EgoIT is not the benchmark

`EgoIT/EgoLife_QA.json`, 26.8 MB, 33,352 items, was checked because its name invites confusion. It
is **training data**: each item is a `conversations` pair over a single 30 s mp4 with
`start_frame` / `end_frame` inside that clip, open-ended rather than multiple choice, gold answer
paraphrased from a caption in the `source` field. It covers all six participants but 91.2 percent
of items are DAY1. **The gap is bounded by the clip, so it cannot carry a long-horizon certificate
at all**, and it does not restore the five missing participants.

---

## 7. S-EMBER option count and chance accuracy on the LH-REQ 97

**A live check on a result in flight, so every number carries its denominator and register.**
Sources: `results/sember/study_h/data/sember_mcq.jsonl` (committed, 9,448 rows) and
`results/orchestration/live2/lh_req/lh_req_definition.json` (committed, n = 97).

| quantity | value | register |
|---|---|---|
| S-EMBER MCQ rows | 9,448 | observed |
| **options per question, all 9,448 rows** | **5 (A-E), no exceptions** | observed |
| **options per question, the LH-REQ 97** | **5, all 97 resolved, 0 missing** | observed |
| **chance accuracy** | **1/5 = 20.00 %** | exact |
| key distribution over all 9,448 | A 1,892 / B 1,937 / C 1,853 / D 1,885 / E 1,881 | observed |
| key distribution over the 97 | A 22 / B 22 / C 17 / D 17 / E 19 | observed |
| best fixed-letter guesser on the 97 | 22.68 % | constructed |

| arm | accuracy | correct / 97 | expected at chance | one-sided exact binomial P(X >= observed), p = 0.2 |
|---|---|---|---|---|
| **RECENT** | **21.65 %** | **21** | **19.4** | **0.381** |
| **D2** | **45.36 %** | **44** | 19.4 | 1.53e-8 |

**The premise behind the question does not hold: S-EMBER is five-option, so chance is 20.00
percent, not 25. RECENT at 21.65 percent is therefore 1.65 pp ABOVE chance, not at or below it.**

It is nonetheless **statistically indistinguishable from guessing**: 21 correct against 19.4
expected, p = 0.381 one-sided. A best-fixed-letter guesser would score 22.68 percent on this set,
*higher* than RECENT, so against that adversarial floor RECENT is 1.03 pp below. Both floors are
reported because the choice between them is a modelling decision, not a measurement.

**So the intended conclusion survives its arithmetic premise failing.** The accurate statement:

> On LH-REQ, D2 is far above chance (45.36 percent against 20.00 percent, p = 1.5e-8) while RECENT
> is not distinguishable from guessing (21.65 percent, p = 0.381). The +23.71 pp gap is better
> described as "D2 is above chance where RECENT is not" than as "RECENT is degraded".

**Do not round this to "RECENT is below chance."** It is above chance by 1.65 pp, a difference of
one and a half questions.

Scope: n = 97 pooled, 28 DEV and 69 EVAL, not split. The 20.00 percent figure assumes a uniform
guesser.

---

## 8. Mechanism verification

**Not applicable: this study tests no causal claim.** It is a dataset availability and sizing audit,
in the same register as StudyS0's pre-registration audits, which recorded "N/A (pre-registration
audit, no causal claim tested)". No sweep was run, no policy compared, no null reported, so
CLAUDE.md Rules 1 and 2 on null classification do not engage.

The two inferential statements, the exact binomials in §7, are closed form over a committed
per-question record, not a simulation, so there is no mechanism to disable.

---

## 9. Results consistency check

**1. Cross-check against committed measurements.**

| quantity | this run | prior run | source of prior | ratio | agree |
|---|---|---|---|---|---|
| S-EMBER MCQ rows | 9,448 | 9,448 | `reports/study_h_sember_structure.md` | 1.000 | agree |
| LH-REQ n | 97 | 97 | `reports/study_lh_req.md` §1 | 1.000 | agree |
| LH-REQ D2 accuracy | 45.3608 % | 45.36 % | `reports/study_lh_req.md` §2 | 1.000 | agree |
| LH-REQ RECENT accuracy | 21.6495 % | 21.65 % | same | 1.000 | agree |
| D2 tokens per image / stride / header | 90 / 2.0 s / 31 | 90 / 2.0 s / 31 | imported from `live2/fleet/data_sources.py` (StudyRH4) | 1.000 | agree, by import rather than by copy |
| feasibility breakeven | 19,381 tok | 19,381 tok | `reports/study_covex_hardening.md:2014` | 1.000 | agree |
| clip byte rate | 483 kB/s (brief) | 526 kB/s (measured here from HF metadata) | HF file metadata, 818 segments | 0.918 | agree, inside 2x |
| EgoLife scale | 10.9 h recorded in A1 DAY1 | 300 h over 6 participants x 7 days | arXiv 2503.03803 abstract | ~1.0 | agree |

**No EgoLife quantity has been measured in this repository before**, so every EgoLifeQA count in
§2, §3 and §4 is a first measurement with no prior to disagree with. Stated rather than hidden:
these numbers have had no independent confirmation.

**2. Physical plausibility.** 14.5 MB per 30 s is 483 kB/s = 3.9 Mbit/s, plausible for
glasses-grade continuous capture. Against the repository's own video handling, the committed
S-EMBER corpus is 396.2 GB over 387.9 h = 283 kB/s, so EgoLife is **1.71x** that, under the 2x flag
and in the expected direction (glasses-native continuous capture against clipped video). D2 at 45
tokens per second of video is identical to the committed constant by construction, since it is
imported. **No flag.**

**3. Distribution sanity.** Gaps are reported with full spread (min 292, p25 1,495, median 6,375,
p75 19,140, max 42,303 s) and the bin table, not as a bare median. Token counts over the 46 are
reported min / median / max (13,171 / 20,146 / 39,991), a 3.0x span, as expected from a 3.1x span in
gap. The one exact-looking constant, 40,531 tokens at 900 s, **is exact because the window is a
constant by construction**, and is flagged rather than reported as a finding. The two 20s in §4
(19,400 and 19,381 admitting the same set) are explained rather than waved through: nothing lies in
the 19-token gap between the thresholds, and the **smallest non-admitted question is 19,561 tokens**,
only 161 above the budget, which is **4 seconds of video**. So the 20 is a knife-edge count, not a
plateau, and a small change in stride or header accounting would move it.

**4. Definition audit.**

| object | definition used in this run | matches prior? |
|---|---|---|
| D2 | 2.0 s stride, 352x256, 90 tok/img, 31 tok header | yes, and **imported** from `live2/fleet/data_sources.py` rather than restated |
| 19.4k threshold | 19,400 tok; 19,381 (D132 breakeven) reported alongside | consistent, both reported |
| 32k threshold | **32,768**, admitting 39 of 46. 32,000 would admit **38**: one question sits at 725 s / 32,611 tokens, between the two. Reported because the choice of 32k spelling changes the count by one. | new in this study |
| 30 s clip | 30.0 s, equal to live2's `HISTORY_BATCH_S` | consistent by coincidence of value, stated |
| LH-REQ | the 97 StudyR1 questions whose evidence is outside the 120 s RECENT window, read off the K3 cell | yes, `lh_req_definition.json` |
| **gap** | **`query_time` minus `target_time`, same-day single-target only, 1 s resolution** | **NEW OBJECT. It is NOT S-EMBER's `evidence offset`**, which is measured within one video by `study_o_q4.covered`. Same intuition, different measurement, different exclusion rules. **The two must not be pooled or compared directly.** |

**5. Claim linkage.** This study bears on **C5** only by way of workload supply: can EgoLifeQA serve
as a second workload for D139 alongside S-EMBER. The answer is the §0 headline. It **does not
test** C1 to C4 or C6 and produces no evidence for or against any of them. §7 bears on the LH-REQ
headline in `reports/study_lh_req.md` and **sharpens rather than weakens** it, by establishing that
the comparator arm is at chance. Nothing measured here is scoped out by `research/FORMULATION.md`.

**6. Proxy validity.**

| proxy | what it actually measures | valid for the claim? |
|---|---|---|
| `need_audio` / `need_name` as answerability flags | the annotators' judgment that the question needs speech or identity, **not** a measured failure of a vision-only reader | **adequate and conservative for a feasibility screen.** It is the dataset's own declaration, and it is used to *exclude*, so an over-inclusive flag can only shrink the usable count. It is **not** validated as a predictor of model accuracy and must not be used that way. |
| 14.5 MB per 30 s clip for every window | an assumed constant rate | **limitation.** My own measurement gives 526 kB/s with p10 409 / p90 676, so the GB figures are roughly ±30 percent. Immaterial at 0.55 GB. |
| gap as the history a reader would need | the distance to the annotated evidence, assuming history must be contiguous back to it | **this is the load-bearing proxy.** It is the right object for a D2 arm, which carries a contiguous fixed-stride window, and it would overstate the need for a retrieval arm that could jump to the evidence. Valid for the D2 token question asked here, **not** valid as a general statement about what the question needs. |
| filename timestamp gaps (the calibration rate only) | spacing of segment start times, not decoded duration | adequate for a byte-rate cross-check; 818 of the 827 DAY1 inter-segment gaps are exactly 30 s. |
| key-balance as a bound on guessable priors | leakage through the answer key only | **not valid** as a test of guessable priors; a blind run would be needed and was not done. EgoLifeQA is 4-option with key A118/B126/C128/D128 of 500, so a key-prior guesser gets 25.6 % against 25.0 % chance. Marked unvalidated. |

---

## 10. Scope conditions on the verdict

- **Size.** One participant, 500 rows, 281 in the analysis set, 46 at 15 min or less, 3 usable. The
  smallest per-type cell is 1. Nothing here supports a per-type conclusion.
- **Coverage.** 43.8 percent of rows are excluded and the exclusions are **not** random with
  respect to gap: cross-day rows are long-gap by construction. The usable count is therefore
  robust to the exclusions in the direction that matters, which the §0 upper bound of 4 confirms.
- **Regime.** The token arithmetic is D2 at 0.5 fps. The fit scales with stride: 19.4k buys 430 s
  at a 2 s stride and would buy 1,722 s at 8 s. **"20 of 46 fit" is a property of our frame rate,
  not of EgoLife.**
- **Representation.** The gap-as-contiguous-history assumption is specific to a D2-style window
  (§9 check 6). A retrieval arm would be bounded differently.
- **Release.** Read at revision `143fb319`, which the card says is still being cleaned, so the
  1-of-6 and the malformed-row counts are statements about this revision and may expire.

## 11. Recommendation

**OFFLINE CORROBORATION ONLY**, by the rule as written: usable count 3, threshold 50.

EgoLifeQA at this revision can be used to **corroborate** a D139 finding offline, on a handful of
questions, with the limitation that the three usable items are too few for any interval worth
quoting. It **cannot support a trace-driven workload.** The binding constraints, in order, are
`need_name` (197 of 281 require identity recognition), the D2 token budget (20 of 46 at 15 min or
less), and `need_audio` (137 of 281). The token budget is the only one we control, and lifting it
to 32k moves the usable count from 3 to 5.

**No new dataset is proposed and nothing is implemented.** Per CLAUDE.md this is the gap
description, not a request to adopt. EgoLife remains closed in `research/GRAVEYARD.md`.
