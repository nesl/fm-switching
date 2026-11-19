# StudyEVNEED: how often does a robot question actually need history?

Session 2, D134 follow-on. **Offline and read-only**: no policy code changed, no GPU used, every
number from committed per-question records. Prefix `evidence-need`.

**Why now.** `RecallAction.representation` is read and charged as of `e924005`, so evidence
selection is finally expressible. Part A made it possible; this study asks whether it is worth
anything.

---

## 0. DATA INVENTORY, and one gap that bounds item 3

| resolution | pairs that exist | n |
|---|---|---|
| **per-question** | K1 = 32B-I x RICH, K3 = 32B-I x RECENT, K2 = 32B-T x RICH | 845 each |
| **per-category** | 32B-RICH, 32B-RECENT, **32B-D2**, 4B-D2, device-N1-orin | 8 categories |
| aggregate only | 4B-I x RECENT 0.3278, 4B-T x RICH 0.3089, 8B-I x RICH 0.3621 | 845 each |
| **ABSENT** | **4B-I x RICH** (StudyR1 records "NOT AVAILABLE, no StudyO run exists"); **32B x D2 PER-QUESTION** | - |

**Join validated before anything was built on it: 845 of 845 question ids carry BOTH K1 and K3.
Zero missing.**

**The gap that bounds item 3:** no intermediate window and no summary representation exists at
per-question resolution. Only the two endpoints, RECENT and RICH, plus D2 at category resolution.
So this study can size the endpoint choice and cannot size a graded ladder.

---

## 1. THE 2x2. The net delta hides flows SIX TIMES its size

845 questions, bootstrap CIs at 2,000 resamples.

| outcome | n | share |
|---|---|---|
| both right | 266 | 31.5 % |
| both wrong | 453 | 53.6 % |
| **RECENT right, RICH wrong (history HURTS)** | **58** | **6.9 %** |
| **RECENT wrong, RICH right (history HELPS)** | **68** | **8.0 %** |

| quantity | value | 95 % CI |
|---|---|---|
| history HELPS | **8.05 %** | [6.27, 9.94] |
| history HURTS | **6.86 %** | [5.21, 8.52] |
| net (`K1_minus_K3`) | **+1.18 %** | [-1.42, +3.79] |

**The headline: representation changes the answer on 14.9 percent of questions, and it changes it
in BOTH directions at nearly equal rates.** The committed net of +1.18 pp, which does not exclude
zero, is the small residue of two large and opposing flows. **Every delta reported in this project
so far has been that residue.**

## 1.1 HELPS is coverage-dependent. HURTS is NOT

| split | n | HELPS | HURTS | net |
|---|---|---|---|---|
| RECENT window COVERS the evidence | 748 | **5.88 %** | 6.82 % | -0.94 |
| RECENT window MISSES the evidence | 97 | **24.74 %** | **7.22 %** | +17.53 |

**History helps four times more often when the recent window misses the evidence, exactly as
expected. But history HURTS at a flat ~7 percent whether the window covers the evidence or not.**

That asymmetry is the structural result of item 1. The benefit of history is predictable from
coverage; **the cost of history is not predictable from coverage at all.** Any rule built on
"does the recent window cover the evidence" can capture the upside and is blind to the downside.

## 1.2 By question type, the net runs BOTH WAYS

| category | n | HELPS | HURTS | net |
|---|---|---|---|---|
| sequential_action | 102 | 15.69 | 8.82 | **+6.86** |
| temporal_ordering_recognition | 90 | 14.44 | 8.89 | +5.56 |
| visual_detail_recall | 143 | 6.99 | 4.20 | +2.80 |
| object_comparison | 91 | 6.59 | 4.40 | +2.20 |
| time_duration | 121 | 4.13 | 2.48 | +1.65 |
| spatial_aware_reasoning | 91 | 3.30 | 3.30 | 0.00 |
| counting_objects_events | 110 | 6.36 | 7.27 | -0.91 |
| **location_trace** | 97 | 8.25 | **17.53** | **-9.28** |

**`location_trace` is the strongest signal in the study and it points the WRONG way: sending the
full history costs 9.3 pp net, with history actively hurting on 17.5 percent of its questions.**

**This independently corroborates the non-monotonicity result from the committed per-category
tables, where D2 beat RICH on `location_trace` by +17.2 pp.** Two different measurements, one
per-question and one per-category, agree that this category is harmed by more history. That is a
real property of the workload, not an artefact of either table.

## 1.3 By history size: a LIMITATION, not a result

| bucket | n |
|---|---|
| under 5k tokens | 4 |
| 5k to 11k | 18 |
| 11k to 19,381 | 823 |
| **above 19,381, the D132 feasibility breakeven** | **0** |

**No StudyR1 question has a history above the feasibility breakeven.** So the question item 3 was
to answer, how many physically infeasible questions become answerable on time with RECENT and at
what accuracy, **cannot be answered from committed accuracy data at all**. The timing half is
computable from the cost curve; the accuracy half has no evidence. This is stated as a gap rather
than filled.
