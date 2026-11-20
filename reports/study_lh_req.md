# LH-REQ: a workload of questions that actually need history

D139 Part 1. **Offline, read-only**, from committed StudyR1 and StudyACC2 records.

**Why this exists.** StudyEVNEED found `recent_covers_frac = 0.8852`: the recent window already
contains the evidence for 88.5 percent of S-EMBER questions, so "warm history rarely pays" may be
a property of **the question mix** rather than of the task. LH-REQ re-tests it on the questions
that need history.

---

## 1. DEFINITION, and a definition trap found on the way

**LH-REQ = the StudyR1 questions whose committed evidence offset lies OUTSIDE live2's 120 s RECENT
window: 97 of 845.**

**`evidence_covered` is a property of the REPRESENTATION, not of the question**, and reading it
from the wrong cell returns an empty set:

| cell | `evidence_covered` |
|---|---|
| K1 (RICH) | **True 900, False 0** - RICH covers from session start, so it is always True |
| K3 (RECENT, 120 s) | True 790, **False 110** |

**Defined off K1 the LH-REQ set is EMPTY**, which is what I first computed. It must come from K3.
StudyEVNEED's 97 was correct but arrived by accident: its loop read both cells and the K3 row
happened to be written last. **A field whose meaning depends on which row you read it from is the
same shape as `RecallQuery.category` carrying `"recall"`** - the name is right and the value is
conditional.

| | n |
|---|---|
| DEV | 28 |
| EVAL | 69 |
| **total** | **97** |

| category | n |
|---|---|
| visual_detail_recall | 29 |
| location_trace | 26 |
| sequential_action | 22 |
| temporal_ordering_recognition | 8 |
| time_duration | 4 |
| spatial_aware_reasoning | 4 |
| counting_objects_events | 2 |
| object_comparison | 2 |

**History tokens at arrival:** min 11,399, p25 12,458, **p50 12,614**, p75 12,648, max 12,830.

## 2. THE STOP CONDITION: PASSED

StudyACC2's **live-format** per-question correctness (`6b3a173`), `source = r1-instant`, keyed
`(question_id, rep, source)`. **Zero of 97 missing.**

| | accuracy |
|---|---|
| **D2** | **45.36 %** |
| **RECENT** | **21.65 %** |
| **gap** | **+23.71 pp, CI [+12.37, +35.05]** |

**The CI excludes zero and the gap is larger than the reference**: StudyEVNEED's recent-misses
stratum gave +17.53 pp for RICH against RECENT, and the population gave +1.18 pp with a CI
spanning zero. **The LH-REQ premise holds and the downstream work is justified.**

**Two things worth noting about the number itself.**

**It is measured on the DEPLOYABLE lever.** This is **D2 against RECENT**, which is what live2
can actually choose, not RICH against RECENT. That closes the mismatch StudyEVNEED had to state as
a limitation: the lever that was measured was not the lever available, and now it is.

**D2 beats RECENT here by MORE than RICH did (+23.71 against +17.53).** On questions that need
history, the live-format representation is not a degraded RICH - it is better than RICH was on the
same stratum. That is consistent with section 33.3's finding that representation quality is not
monotone in cost.

## 3. ONE PROPERTY THAT SHAPES WHAT LH-REQ CAN TEST

**Every LH-REQ history is well inside the feasibility breakeven.** The maximum is **12,830 tokens
against the D132 breakeven of 19,381**, so **all 97 questions are deliverable on an idle GPU**.

**So LH-REQ tests SCHEDULING, not feasibility.** A failure on this workload is an arm choosing
not to hold or rebuild history that it could have delivered, which is exactly the question the
directive asks. It is not a workload where arms are beaten by physics, and the `rescued by RECENT`
mechanism of StudyEVNEED section 3 does not apply to it.

## 4. THE TRACE OPTION: built, with the default path proved byte-identical

D142 item 1 requires robots in a live policy run to draw ONLY from the long-horizon questions, and
forbids MIXED for policy evaluation. D143 ruling A narrows that further: the table is fitted on the
DEV split and robots draw ONLY from EVAL. Both are now a named option on the trace generator rather
than a second filter written alongside the old one.

`DS.robot_sessions(question_set)` is the single entry point, so a caller cannot pick the session pool
and the question filter independently and end up with a mismatched pair.
`generate_trace(..., robot_question_set="eval"|"lh_req")` defaults to `"eval"`.

**The ids are READ, never re-derived.** `lh_req_question_ids()` reads
`results/orchestration/live2/lh_req/lh_req_definition.json`, folds case, and intersects with the
committed split module. A second independently written filter over the same 97 would differ
somewhere and nothing would catch it.

**The case trap, and the control that catches it.** Both id collections are mixed case: the split
module's EVAL set is 444 lower and 158 upper, LH-REQ is 63 lower and 34 upper. Folding ONE side and
calling the split module's plain set membership returns EVAL 43 / DEV 20 with 34 unmatched, and **34
is exactly the count of upper-case LH-REQ ids**, so the wrong answer looks plausible. Two sessions
walked into this independently. The function therefore asserts its result against the committed
`per_split` totals read from the same file, and raises rather than returning a plausible subset.
**It returns 69, which is the committed EVAL figure.**

### 4.1 Byte-identity on the default path

The option must not perturb any committed run. Five cells, digest over the full record list in
canonical order, against origin's `fleet/` built from `git show`:

| cell (seed, n, ratio, run_s) | records | digest, origin | digest, with the option | robot questions | identical |
|---|---|---|---|---|---|
| 0, 12, 40:40:20, 600 | 6,068 | `80b376c550007686` | `80b376c550007686` | 21 | yes |
| 4, 12, 40:40:20, 600 | 6,071 | `9bdb6450ea039e94` | `9bdb6450ea039e94` | 27 | yes |
| 0, 16, 40:40:20, 600 | 7,469 | `94c4193f5e51b1d3` | `94c4193f5e51b1d3` | 34 | yes |
| 0, 12, 50:50, 600 | 6,732 | `4cfb07914aa353df` | `4cfb07914aa353df` | 27 | yes |
| 4, 32, 50:50, 600 | 17,863 | `a0c69109477e5ebb` | `a0c69109477e5ebb` | 84 | yes |

**Positive control (check 7):** the n=12 robot counts of **21 at seed 0 and 27 at seed 4** reproduce
the committed figures in `study_hybrid_live.md`, so the control cells match their own committed
values rather than only matching each other.

`fleet/tests/test_live2_fleet.py` passes **234 of 234 checks**, including check (h), which asserts
that `count_only` stats are identical to the full build. Every count in section 4.3 is produced with
`count_only`, so that check is what makes those counts the run's counts.

### 4.2 What the pool becomes, and why it dominates everything downstream

| | EVAL (default) | LH-REQ x EVAL |
|---|---|---|
| questions | 602 | **69** |
| sessions | 164 | **51** |
| questions per session | up to 6 | 1 on 36 sessions, 2 on 12, 3 on 3 |
| session duration | | min 300 s, median 600 s, max 1,200 s |

Sessions carrying no LH-REQ question are dropped from the pool. Keeping them would have a robot play
a session that can never ask anything: the question count would be unchanged but the chain would get
through fewer sessions, so the two are not interchangeable and the choice is recorded rather than
implied.

**A robot earns about 1.35 questions per session played, and sessions are 600 s at the median.** That
single fact sets everything in 4.3: the pooled count is governed by how many sessions a device can
chain through, not by the fleet's size alone.

### 4.3 Per-cell pooled and DISTINCT counts, mix 40:40:20, seeds 0/4/5/6

`fleet/lh_req_counts.py`, output `results/orchestration/live2/lh_req/lh_req_cell_counts.json`.

**Repeats are ZERO in every one of the 84 cells measured.** Pooled equals distinct everywhere and
`asks_per_distinct_question` is 1.0 throughout, because sessions are dealt distinct-first (D84) and
no run gets through enough session plays to exhaust the 51-session pool. So the pooled count is not
inflated by re-asking, which is the thing the distinct column exists to detect. The label is
implemented and reports zero; that is a measurement, not an assumption.

At **600 s**, the length every committed cell has used, **24 of 28 cells are below D82's minimum of
20 pooled questions**. Only n=32 clears it, and only just:

| n | pooled by seed 0 / 4 / 5 / 6 | below 20 |
|---|---|---|
| 10 | 7 / 6 / 10 / 6 | all four |
| 12 | 8 / 9 / 12 / 8 | all four |
| 16 | 9 / 11 / 16 / 9 | all four |
| 20 | 14 / 15 / 20 / 17 | three of four |
| 24 | 17 / 19 / 22 / 20 | two of four |
| 28 | 22 / 20 / 23 / 21 | none |
| 32 | 22 / 21 / 20 / 20 | none |

**Pool coverage is the other limit.** Even the best 600 s cell touches only 0.32 of the 69 questions,
so a cell measures 20 to 22 distinct questions out of 69 and two arms compared at one cell are
compared on that subset.

### 4.4 Run length under overnight rule 1: 1200 s, with the fallback in force

Rule 1 fixes the candidate set at 12 and 16 devices, seeds 0/4/5/6, mix 40:40:20, and asks for the
shortest length at which all 8 cells reach 20 pooled questions.

| length | all 8 cells reach 20 | min pooled | cells below 20 |
|---|---|---|---|
| 600 s | **no** | 8 | all 8 |
| 900 s | **no** | 11 | 7 of 8 (only n=16 seed 5, at 22) |
| 1200 s | **no** | 15 | **3 of 8**: n=12 at seeds 0 (15), 4 (16) and 6 (17) |

**Even 1200 s fails**, so rule 1's fallback applies: **the chosen length is 1200 s** and the robot
result is labelled **not measurable** in the three failing cells. At 1200 s all four 16-device cells
clear it (24 / 20 / 25 / 20) and n=12 seed 5 lands exactly on 20.

**Supplementary, outside rule 1's fixed set and NOT applied.** Rule 1 fixed the candidates at 600 /
900 / 1200, so a longer run is the user's call and is reported rather than taken:

| length | n=12 | n=16 | n=24 | n=32 |
|---|---|---|---|---|
| 1200 s | 15 / 16 / 20 / 17 | 24 / 20 / 25 / 20 | 29 / 30 / 31 / 30 | 46 / 39 / 38 / 43 |
| **1800 s** | **27 / 24 / 27 / 21** | 33 / 31 / 35 / 33 | 46 / 42 / 44 / 46 | 65 / 58 / 59 / 61 |

**1800 s clears every cell at every size, 12 devices included, with a minimum of 21.** It is the
shortest length in evidence that would remove the not-measurable label from the 12-device robot
result entirely. At 1800 s and 32 devices the first repeats appear (pooled 65 against distinct 64),
which is also the first sign of the 69-question pool binding.

### 4.5 The quality table, as a committed input file

`results/orchestration/live2/lh_req/lh_req_quality.json`, fitted on DEV and drawn on EVAL per D143
ruling A, with Wilson intervals beside every point estimate as the user ruled.

| split | n | cloud D2 | cloud RECENT | device 4B+RECENT | cross-tier gain | representation gap |
|---|---|---|---|---|---|---|
| **DEV (the fit)** | 28 | **0.2500** [0.127, 0.434] | 0.1071 | 0.1071 | **+14.29 pp** | **+14.29 pp** |
| EVAL (the draw) | 69 | 0.5362 [0.420, 0.649] | 0.2609 | 0.2464 | +28.99 pp | +27.54 pp |
| all 97 (reference) | 97 | 0.4536 [0.358, 0.553] | 0.2165 | 0.2062 | +24.74 pp | +23.71 pp |

The EVAL and all-97 blocks are recorded for reference and are marked **must not be read by the
policy**.

**The DEV fit changes the size of the half-one correction, and the number in circulation is wrong for
it.** The 7.3x figure compared `TRACE_MIX`'s +3.23 pp representation gap against the **all-97**
aggregate's +23.71 pp. Under ruling A the policy is fitted on **DEV**, whose gap is **+14.29 pp**, so
the correction is **4.4x, not 7.3x**. The direction and the conclusion are unchanged, the magnitude
is not, and the freeze should carry the right one.

Four controls pass on this table: the all-97 cloud D2 and RECENT figures reproduce the committed
`d2_acc` 45.3608 and `recent_acc` 21.6495; the device filter reproduces D87 exactly at 845 questions
and 277 correct, 32.781 percent; and DEV 28 / EVAL 69 reproduce the committed `per_split` with zero
unmatched ids once BOTH sides are folded.

The DEV fit rests on 28 questions, with cloud D2 at 7 of 28 and cloud RECENT at 3 of 28, so its
intervals are wide and are carried in the file. Also recorded there: on DEV the device and the 32B
restricted to RECENT are **identical at 0.1071, three of 28 each**, so on these questions a 32B held
to the recent window is worth nothing over the 4B.

## 5. THE SS2 SINGLE-SHOT POOL, and D84 proved rather than assumed

D143: SS devices draw from RefSpatial-Bench and RealWorldQA, from the EVAL part of a seeded 30 / 70
split per dataset, with device answers from StudySS2 and a per-(device, opportunity) multimodal UUID.

`DS.ss_questions(question_set, part)` is the single entry point, so a caller cannot pair a dataset
family with the wrong split part. `generate_trace(..., ss_question_set="ss1"|"ss2")` defaults to
`"ss1"`.

### 5.1 The split is a committed file, not a derivation

`results/casestudy/study_ss2/ss2_dev_eval_split.json`, written by
`experiments/casestudy/ss2_make_split.py` and READ at use time. The LH-REQ work established why a
partition belongs in a file: two independently written derivations of the same split differ
somewhere and nothing catches it, whereas a file can be diffed. The seed is a fixed STRING, never
the run seed, so the DEV / EVAL boundary is identical in every run, at every size and under every
arm.

| dataset | n | DEV | EVAL | fraction | per subset (DEV, EVAL) |
|---|---|---|---|---|---|
| refspatial | 277 | 83 | 194 | 0.2996 | location (30, 70), placement (30, 70), unseen (23, 54) |
| realworldqa | 765 | 229 | 536 | 0.2993 | mcq (131, 307), free_form (98, 229) |
| **total** | 1,042 | **312** | **730** | | |

**STRATIFIED BY SUBSET, and that is PROVISIONAL.** The ruling asks for a seeded 30 / 70 split of
each dataset and does not say whether to stratify. An unstratified draw could leave RefSpatial
`unseen` (77 items) badly represented in either part, which would make the fitted SS value a
statement about a subset mix the EVAL part does not share. Unstratified is one line away if
preferred. Every question is in exactly one part, asserted, so the split is a census.

### 5.2 One substitution whose direction is now known

StudySS2 records no per-image byte count, so the committed S-EMBER D2 median still stands in for
assistive uplink bytes, as it did for SS1. **SS1 had to call the direction of error unknown; SS2
does not.** Both manifests carry width and height on every row: areas run 196,608 to 2,158,080 px
against S-EMBER D2's 352 x 256 = 90,112 px, so every SS2 image is **2.2x to 24x larger in area** and
the substitution almost certainly **understates** assistive uplink cost. Measuring the staged files
would remove it rather than bound it.

Provenance improves too. StudySS1's five artifacts carry no `_provenance` block and every row had to
say `device_host="unconfirmed"`. Both SS2 device files carry one naming `device: jetson_orin`, so the
tier is read from the file rather than taken on anyone's word.

The device files' `caching` string is NOT carried forward as fact. It claims "distinct image+task per
request so no warm reuse; cold single-shot", and section 10.6 of `study_ss2.md` measured the
opposite. Each pool row therefore carries `device_cold_per_image` stating what was measured, and
noting that the live harness does not inherit the problem because the D84 uuid replaces the content
key: **the committed SS2 TTFT numbers are not the live condition.**

### 5.3 D84 for single-shot: already satisfied by construction, and proved on the cases that would break it

The mechanism exists. `cachekeys.mm_uuid(run_tag, device_id, session_id, frame_ref)` REPLACES the
engine's computed multimodal hash in vLLM 0.31.0, and the SS trace gives every opportunity its own
`session_id` of the form `"<device>|ss<cursor>"`. So the uuid is unique per (device, opportunity)
**without any change to the harness**. Nothing was added; what follows is the check that it is.

This matters because of what StudySS2 measured. A repeated image IS served warm by the multimodal
encoder cache on both tiers, `cache_salt` does not prevent it because the salt isolates the text
prefix cache only, and RefSpatial repeats heavily: 61 images carry 247 of its 277 questions.

`fleet/ss2_uuid_proof.py`, output `results/orchestration/live2/lh_req/ss2_uuid_proof.json`, on three
cells at 1200 s with LH-REQ robots:

| cell | SS image submissions | distinct uuids | (a) same qid, two devices | (b) same qid, one device, twice | (c) identical CONTENT, different qids |
|---|---|---|---|---|---|
| n=16 | 356 | **356** | **UNEXERCISED** (0 qids) | **UNEXERCISED** (0 pairs) | **PASS** (31 groups, 73 submissions) |
| n=20 | 477 | **477** | **PASS** (49 qids, 98 submissions) | **UNEXERCISED** (0 pairs) | **PASS** (48 groups, 192 submissions) |
| n=32 | 717 | **717** | **PASS** (145 qids, 290 submissions) | **UNEXERCISED** (0 pairs) | **PASS** (48 groups, 191 submissions) |

Zero uuid collisions anywhere. **Two cases are labelled UNEXERCISED rather than passed**, which is
the distinction CLAUDE.md's taxonomy exists to force:

- **(a) at n=16 only.** No two SS devices draw the same qid at 16 devices, so cross-device sharing
  cannot arise there at all. It arises and passes at 20, which is the ruled grid size.
- **(b) at every size.** A device's cursor advances monotonically and the EVAL pool holds 730
  questions, so no device wraps around inside 1200 s. The case is unreachable in this regime, not
  confirmed.

**(c) is the load-bearing case and it fires everywhere**, because content is what the cache keys on.
StudySS1 taught this directly: by image id VizWiz val is 4,319 unique on 4,319 and passes clean,
while 34 groups of byte-identical photos sat under different filenames. An identifier-based check
would report (c) as nothing to test.

**Negative control, and it fails where it should.** Recomputing the uuids with device and session
dropped from the key, which is what a content-or-identifier-keyed scheme does, must produce
collisions, or the main result is vacuous:

| cell | colliding naive keys | max submissions on one naive key | control can fail |
|---|---|---|---|
| n=16 | 0 | 1 | **NO** |
| n=20 | 49 | 2 | yes |
| n=32 | 145 | 2 | yes |

**At n=16 the control cannot fail, so that cell's (a) and (b) passes carry no information**, and the
only informative result at 16 is (c). At 20 and 32 the control fires on 49 and 145 keys and the real
scheme still shows zero collisions, so the scheme is doing the work rather than the trace happening
to hold no repeats.

**Register: these are REQUEST BODIES, not server behaviour.** The server-side gate, `mm_cache_queries
delta > 0 AND mm_cache_hits delta == 0`, is the H100's and is separate; it has adopted the
non-vacuity condition, integer parsing with a per-key present flag so an absent key reads as
INSTRUMENT NOT REPORTING rather than pass, and the request-body grep on the first live cell
regardless of the total.

### 5.4 Byte-identity with the SS option added

Six cells, including two three-type cells and the 20-device 1200 s cell, against origin's `fleet/`:

| cell (seed, n, ratio, run_s) | records | digest, origin | digest, with both options | robot | SS |
|---|---|---|---|---|---|
| 0, 16, 40:40:20, 600 | 7,469 | `94c4193f5e51b1d3` | `94c4193f5e51b1d3` | 34 | 176 |
| 4, 16, 40:40:20, 600 | 7,442 | `a6331f90a331b1da` | `a6331f90a331b1da` | 39 | 177 |
| 0, 20, 40:40:20, 1200 | 20,014 | `54c183c4aed90496` | `54c183c4aed90496` | 74 | 477 |
| 0, 12, 50:50, 600 | 6,732 | `4cfb07914aa353df` | `4cfb07914aa353df` | 27 | 0 |
| 4, 32, 50:50, 600 | 17,863 | `a0c69109477e5ebb` | `a0c69109477e5ebb` | 84 | 0 |
| 5, 32, 40:40:20, 600 | 15,978 | `e9cb3b9852465f19` | `e9cb3b9852465f19` | 69 | 352 |

All six identical. `test_live2_fleet.py` **234 of 234**, check (h) included.

### 5.5 The ruled grid is fully measurable, and 16 is the entry point by measurement

The user's ruling fixes 1200 s with grid sizes 16 and 20. Against D82's minimum of 20 pooled robot
questions, seeds 0 / 4 / 5 / 6:

| n | robots | pooled by seed 0 / 4 / 5 / 6 | min | distinct = pooled | measurable at every seed |
|---|---|---|---|---|---|
| **16** | 7 | 24 / 20 / 25 / 20 | **20** | yes | **yes** |
| **20** | 8 | 28 / 24 / 29 / 26 | **24** | yes | **yes** |

**No cell at the ruled sizes needs the not-measurable label.** Section 4.4's fallback was driven
entirely by n=12, which the ruling drops from the grid, so overnight rule 1's fallback is recorded
but is **not in force for the grid that will actually run**.

**16 is the D97 entry point, measured rather than chosen.** The smallest size measurable at every
seed at 1200 s:

| n | robots | pooled by seed 0 / 4 / 5 / 6 | min | measurable |
|---|---|---|---|---|
| 12 | 5 | 15 / 16 / 20 / 17 | 15 | no |
| 13 | 5 | 15 / 16 / 20 / 17 | 15 | no |
| 14 | 5 | 15 / 16 / 20 / 17 | 15 | no |
| 15 | 6 | 20 / 18 / 22 / 21 | 18 | no |
| **16** | 7 | 24 / 20 / 25 / 20 | **20** | **yes** |

12, 13 and 14 give identical counts because the 40 percent robot share rounds to 5 robots at all
three. Two of the four 16-device cells sit exactly on 20, so the entry point has no margin: any
change that costs a robot one question makes 16 unmeasurable.

Coverage remains the standing limit. At the ruled sizes a cell touches 0.29 to 0.42 of the
69-question pool, so two arms compared at one cell are compared on 20 to 29 distinct questions.
