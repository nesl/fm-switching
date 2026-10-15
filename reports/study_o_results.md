# Study O — HALTED at the §8 sample check

**Date:** 2026-10-14
**Plan:** `reports/study_o_plan.md` (defects D1–D4 fixed in place, this date)
**Pre-check script:** `experiments/sember/study_o_precheck.py`
**Inference run:** **NOT STARTED** — halted before launch, as §8 specifies.

---

## Verdict

> **HALTED. §8.2 Q1 cell balance FAILS and cannot be repaired by choosing a different sample.**
>
> 12 of 24 (category × distance_bin) cells have fewer than 20 questions. Full balance needs
> ~480 questions; only **520** exist on this machine, and they are unevenly distributed, so even
> using *every* locally-available question the check still fails.

The plan states: *"Report both checks in the script's pre-run output; halt if either fails."*
No GPU time was spent on inference.

---

## 1. Defect verification — all four were UNFIXED

None of the four defects flagged on 2026-10-03 had been fixed. All four are now fixed in
`reports/study_o_plan.md`.

| defect | state found | action |
|---|---|---|
| **D1** (critical) | **unfixed** — line 51 still read `4B-T … Qwen/Qwen3-VL-4B-Instruct (thinking mode)` | corrected to `Qwen/Qwen3-VL-4B-Thinking`; all three snapshots resolved and verified distinct |
| **D2** | **unfixed** — no decoding specified anywhere in the plan | frozen to CFG-A; vendor deviation disclosed |
| **D3** | **unfixed** — no `max_new_tokens` for the thinking arm | set to 8192; `think_closed`/`budget_hit` now required per trial |
| **D4** | **unfixed** — line 69 read verbatim as flagged | redefined and recomputed; see §2 |

### D1 — resolved snapshots

| arm | HF id | snapshot |
|---|---|---|
| 4B-I | `Qwen/Qwen3-VL-4B-Instruct` | `ebb281ec70b05090aa6165b016eac8ec08e71b17` |
| 8B-I | `Qwen/Qwen3-VL-8B-Instruct` | `0c351dd01ed87e9c1b53cbc748cba10e6187ff3b` |
| 4B-T | `Qwen/Qwen3-VL-4B-Thinking` | `1de27d8c51f12e819435303b9e84c4e25ba8401e` |

All three present on flash and distinct. The original plan would have run the 4B-I checkpoint
twice and reported one of the runs as a thinking arm.

---

## 2. D4 — the substantive finding, and it changes the design's premise

`evidence_covered` was coded 1 for RICH and UNIFORM "since they span [0, qt]". Spanning is not
covering. Recomputed from each arm's **actual sampled frame timestamps** — does any sampled frame
fall within `[answer_start_time, answer_end_time]` — over the 520 locally-available questions:

| arm | OLD (defective) | NEW (sampled) | delta |
|---|---|---|---|
| RECENT | 68.8% | **90.4%** | **+21.5pp** |
| UNIFORM | 100.0% | **85.4%** | **−14.6pp** |
| RICH | 100.0% | **99.6%** | −0.4pp |

**The correction inverts the ordering of the arms.** This matters more than the magnitudes:

- Under the **old** coding, RECENT was the *only* arm with any uncovered questions (68.8% against
  100% and 100%). `evidence_covered` was therefore very nearly a relabelling of "is this the
  RECENT arm", and Q1's `model_arm × evidence_covered` interaction would largely have been
  re-estimating the state-arm main effect under another name.
- Under the **corrected** coding, **UNIFORM is the worst-covered arm at 85.4%**, *below* RECENT at
  90.4%. The variable now carries information that is not collinear with arm identity.

**Mechanism.** The UNIFORM inter-frame gap is 15.9 s at the median and up to 77 s, while the
evidence window is 29 s at the median and 10 s at p25. **31.5% of questions have an evidence
window narrower than their own UNIFORM sampling gap**, so the evidence can fall entirely between
two samples. RECENT scores *higher* than the old coding implied because it samples at 1 fps and
the evidence *window* frequently extends into [qt−120, qt] even when its farthest point lies
outside — the old rule tested only the farthest point, not the window.

This confirms the prediction in the defect report (RICH high, UNIFORM materially lower) and adds
one that was not predicted: RECENT outranks UNIFORM.

**Q1's entire interaction test rests on this variable**, so this correction would have changed the
study's primary result regardless of the halt. It is the most useful output of this task.

---

## 3. §8.1 — Q4 power check

| quantity | value |
|---|---|
| questions with farthest > 120 s | **31.2%** |
| H2 expectation | ~29.7% |

Consistent with expectation. **This check does not fail.**

---

## 4. §8.2 — Q1 cell balance check: **FAIL**

Requirement: ≥ 20 questions per (category × distance_bin) cell. Counts over all 520
locally-available questions (`!` marks cells below 20):

| category | ≤60s | 60–120s | >120s |
|---|---|---|---|
| counting_objects_events | 9 ! | 22 | 30 |
| location_trace | 28 | 13 ! | 11 ! |
| object_comparison | 23 | 16 ! | 17 ! |
| sequential_action | 32 | 22 | 7 ! |
| spatial_aware_reasoning | 17 ! | 10 ! | 29 |
| temporal_ordering_recognition | 10 ! | 15 ! | 22 |
| time_duration | 37 | 29 | 27 |
| visual_detail_recall | 57 | 18 ! | 19 ! |

**12 of 24 cells below threshold.**

### Why this cannot be fixed by sampling

The root cause is **data availability, not sample size**:

- The grounding set references **3,141 videos**; only **150** are present on this machine
  (`results/sember/study_i/videos`, 19 GB).
- That restricts Study O to **520 questions** of the 9,448 in the grounding file.
- Full balance needs ~480 questions *evenly spread* across 24 strata. The 520 available are
  unevenly spread, so the check fails even at n = 520 — the entire local pool.

Drawing a smaller stratified sample makes this strictly worse. The only repair is **more videos**:
roughly 400 GB for the full set, which is outside the scope of a night queue and was not
authorised.

---

## 5. What was not done, and what is still open

**Not done:** no inference, no runtime projection (nothing was launched), no Q1/Q2/Q3/Q4 analysis.

**Worth a decision before the next attempt:** the §8 halt is triggered by the **Q1** cell-balance
requirement, which exists for the mixed-effects model. **Q4 — the question that matters for the
paper — does not depend on cell balance**, and its own power check (§8.1) passed. A Q4-only run
on the 520 local questions may therefore be viable where the full factorial is not.

I have **not** run that, because the instruction was to halt if either check fails and the plan
says the same. Authorising a Q4-only variant is a scope decision. Note two things that bear on it:

1. Q4 needs the `4B-I × RECENT`, `8B-I × RICH` and `4B-T × RICH` cells — 3 of the 9, not all
   nine — so it is roughly a third of the compute.
2. Q4's predictor-retraining step requires excluding Study O `video_id`s from N2's training
   folds. With only 150 videos available and N2 trained on 3,141, that exclusion is small and
   feasible.

---

## 6. Files

| path | status |
|---|---|
| `experiments/sember/study_o_precheck.py` | new — §8 checks and D4 recomputation |
| `reports/study_o_plan.md` | modified — D1–D4 fixed in place, each marked |
| `reports/study_o_results.md` | this file |
| `results/sember/study_o/` | **not created** — no inference run |
