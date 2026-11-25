# s6 recall device-accuracy verification (before oracle stage 3)

CPU only, read-only. Recomputed from the committed robot gold grading (the trace generator's
`device_answers`, graded `device_correct == (device_answer == gold_letter)`), independent of the
scorer.

## Verdict: GENUINE PROPERTY OF THE s6 QUESTION SET, not an extraction error. s6 may be fed into the bound (as a flagged outlier).

## Numbers (per seed, pooled over re-asks and over distinct questions)

| seed | pooled correct / n | pooled acc | distinct correct / n | distinct acc |
|---|---|---|---|---|
| 4 | 49 / 132 | 0.371212 | 6 / 20 | 0.300 |
| 5 | 38 / 127 | 0.299213 | 8 / 25 | 0.320 |
| **6** | **7 / 121** | **0.057851** | **1 / 20** | **0.050** |
| 7 | 31 / 105 | 0.295238 | 6 / 22 | 0.273 |

The 0.057851 is byte-identical across EVERY committed s6 cell and arm, 1x and kv0.5r (device
answers do not depend on the policy), so it is not a per-cell artifact. At s6 the device answers only
1 of its 20 DISTINCT robot questions correctly: question_id `0a99c448aeb577d0`, re-asked 7 times,
giving 7 of 121 pooled.

## Why it is a property and not an error (three independent checks)

1. **Grading is internally consistent.** `device_correct` equals `(device_answer == gold_letter)`
   for all 121 s6 rows (and all 132 s4 rows): 0 mismatches. The boolean is not independently
   corrupted.
2. **Per-question grading is seed-invariant.** Across seeds 4-7 there are 23 robot question_ids that
   appear in two or more seeds; every one has an IDENTICAL `(device_answer, gold_letter)` in every
   seed it appears in (0 inconsistent). A misalignment (device answers paired with the wrong
   question's gold) would have shown up as a seed-dependent pair for a shared question_id; none
   does. So s6's low accuracy cannot come from a question/answer or gold misalignment.
3. **The device answers are real, varied letters.** s6 device-answer distribution is B 31, C 22,
   A 24, D 28, E 16 (not a constant, not empty, not malformed); gold is D 31, B 23, C 35, A 12,
   E 20. The device simply picks the wrong option on 19 of s6's 20 distinct questions.

The union device accuracy over all 57 distinct robot questions drawn across seeds 4-7 is 0.2281; s6
drew a 20-question subset on which the device is far below that (0.05), while s4/s5/s7 drew subsets
near or above it. s6 is a genuine low-tail draw of the small (20-25 distinct) per-seed robot
question set, not a bug.

## Consequence for the oracle
s6 is sound to include, but it is an OUTLIER: its real device floor is 0.058, so its recall FAIR
gain acc_cloud - acc_device is large (0.550 - 0.058 = 0.492) and rests on a single correct distinct
question. Under D240/D238 the oracle is reported PER SEED and never pooled across seeds, so s6's
outlier status is visible rather than hidden; its per-seed share will carry a wide CI from the
20-distinct-question count. Recommendation: feed s6 into the bound with this outlier flag recorded,
not drop it, since 0.058 is a true measurement of the committed s6 device answers.
