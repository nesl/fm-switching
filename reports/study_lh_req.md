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
