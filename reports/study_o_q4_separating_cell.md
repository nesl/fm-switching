# Study O Q4 — the separating cell: 4B-I × RICH

**Date:** 2026-10-17
**Pre-registered:** `research/EXPERIMENTS.md`, row `StudyO-q4-sep`, written **before** the run
with all four contrasts and the decision rules fixed.
**Trials:** `results/sember/study_o/study_o_q4_trials_4bi_rich_fa2.jsonl` — 845, 0 errors.
**Script:** `experiments/sember/study_o_q4.py --cell 4B-I --state RICH --fa2`;
analysis `study_o_q4_analyze.py --sep`.
**Backend:** `flash_attention_2`, asserted at load, recorded on 845/845 rows.
**Compute:** 0.95 h wall (09:48 → 10:45), A6000 cuda:1.

---

## Why this cell exists

Study O Q4 compared local **4B-I × RECENT** against remote **8B-I × RICH**. Those differ in
**model size and frame selection at once**, so every gain and every difference-in-differences
in that study is a model+state effect with no cell to separate them. This runs the missing
corner of the 2×2.

**What "state" means here, measured from the trials at the matched ~12.6 k token budget:**

| arm | median frames | median tok/frame |
|---|---|---|
| RECENT | 121 | 103.0 |
| RICH | 231 | 54.8 |

RICH is **~1.9× the frames at ~0.53× the detail each**. It is a *reallocation* of a fixed token
budget from spatial detail to temporal coverage, not an increase in information.

---

## VERDICT — **STATE CARRIES IT** (pre-registered rule), with one conjunct underpowered

> **Contrast 1 — state at fixed model**, (4B-I × RICH) − (4B-I × RECENT), split by the local
> arm's `evidence_covered`: **DiD +15.4 pp, 95% CI [+3.8, +27.8]** — **excludes 0**.
>
> **Contrast 2 — model at fixed state**, (8B-I × RICH) − (4B-I × RICH), same split:
> **DiD +2.9 pp, 95% CI [−7.1, +13.4]** — **includes 0**.
>
> Pre-registered rule: C1 excludes 0 **and** C2 includes 0 → **STATE CARRIES IT.**

**The rule fired, and one half of it should not be leaned on.** C2's null is **INCONCLUSIVE
(underpowered)** under CLAUDE.md Rule 2, not a real negative: its MDE is **14.54 pp** while its
CI upper bound is **+13.4 pp**. A model-driven interaction almost as large as the state-driven
one we did detect would sit inside that interval undetected. **The correct statement is "state
is sufficient to produce the interaction", not "model contributes nothing."**

**C1 is also not comfortably powered.** Its MDE is **17.30 pp** against an observed DiD of
**15.4 pp** — the CI excludes zero, but the study had under 80% power for an effect of the size
it found, so the point estimate is subject to winner's-curse inflation. Treat +15.4 pp as
"positive, magnitude poorly determined", not as a calibrated effect size.

---

## 1. Contrast 3 — all four cells (Wilson 95% CIs)

| cell | correct | accuracy | Wilson 95% CI |
|---|---|---|---|
| 4B-I × RECENT (local) | 277/845 | **32.78%** | [29.70, 36.02] |
| **4B-I × RICH (new)** | 258/845 | **30.53%** | [27.52, 33.72] |
| 8B-I × RICH | 306/845 | **36.21%** | [33.04, 39.51] |
| 4B-T × RICH | 261/845 | **30.89%** | [27.86, 34.08] |

**Read the new cell carefully: RICH is *worse* than RECENT on average at fixed model**, 30.53%
vs 32.78%. All four Wilson intervals overlap heavily.

## 2. Contrast 1 — state effect at fixed model (the crossover)

| stratum | n | 4B-I × RECENT | 4B-I × RICH | gain |
|---|---|---|---|---|
| **uncovered** | 97 | 20.6% | **32.0%** | **+11.3 pp** |
| covered | 748 | 34.4% | 30.3% | **−4.0 pp** |

**DiD +15.4 pp, CI [+3.8, +27.8]**, excludes 0. Bootstrap SE 6.17 pp, MDE 17.30 pp.

**This is a crossover, not a gain.** Widening temporal coverage at the cost of per-frame detail
**helps by +11.3 pp when the evidence lies outside the recent window** and **hurts by −4.0 pp
when it lies inside it**. Both directions are what the reallocation predicts: if the evidence
is outside RECENT's 120 s window, no amount of per-frame detail recovers it and more frames is
the only thing that helps; if the evidence is already in the window, spending half the per-frame
budget on reaching further back is a straight loss of detail on the frames that mattered. The
7.7:1 population split (748 covered vs 97 uncovered) is why the average comes out negative while
the interaction is strongly positive.

## 3. Contrast 2 — model effect at fixed state

| stratum | n | 4B-I × RICH | 8B-I × RICH | gain |
|---|---|---|---|---|
| uncovered | 97 | 32.0% | 40.2% | +8.2 pp |
| covered | 748 | 30.3% | 35.7% | +5.3 pp |

**DiD +2.9 pp, CI [−7.1, +13.4]**, includes 0. Bootstrap SE 5.19 pp, MDE 14.54 pp.

Doubling model size helps **in both strata and by similar amounts** (+8.2 and +5.3 pp). That is
the signature of a main effect, not an interaction: the bigger model is simply better at these
questions, roughly independently of whether the retained frames contain the evidence. The
interaction that drives escalation value comes from the **state**, and the model adds a level
shift on top of it.

## 4. Contrast 4 — escalation with no model change

Remote = **4B-I × RICH**. Same model on both sides; only the state representation changes.

| e | (a) never | (b) always | (c) random | (d) P4 | (e) evidence oracle | (f) accuracy oracle | d − c |
|---|---|---|---|---|---|---|---|
| 0.1 | 32.78% | 30.53% | 32.56% | 33.25% | 33.61% | 39.29% | +0.70 pp |
| 0.2 | 32.78% | 30.53% | 32.33% | 32.78% | 34.56% | 39.29% | +0.45 pp |
| 0.3 | 32.78% | 30.53% | 32.11% | 32.54% | 35.03% | 39.29% | +0.44 pp |

**Evidence oracle vs random — significant at every e:**

| e | gain | 95% CI | excludes 0 |
|---|---|---|---|
| 0.1 | +1.05 pp | [+0.20, +2.11] | **YES** |
| 0.2 | **+2.22 pp** | **[+0.88, +3.61]** | **YES** |
| 0.3 | +2.92 pp | [+1.32, +4.34] | **YES** |

**P4 vs random — not significant at any e:** +0.70 [−0.32, +1.57], +0.45 [−0.81, +1.82],
+0.44 [−0.90, +1.91].

**This is the most important result in Part 2.** The escalation benefit **survives intact with
the larger model removed**: at e=0.2 the evidence oracle beats random by +2.22 pp
(CI [+0.88, +3.61]) against +2.39 pp (CI [+0.92, +3.86]) when the remote arm was 8B-I × RICH.
**Essentially all of the coverage-signal's value comes from switching state representation, not
from switching model.** A router that escalates to a richer temporal state on the *same local
model* captures nearly the whole benefit — which is a materially cheaper deployment story than
one requiring a larger remote model.

P4's failure to beat random replicates here, consistent with the underpowered-predictor finding
in the Part 1 audit rather than with any claim that coverage is uninformative — the evidence
oracle on this very data is significant at all three e values.

**Caveat on the accuracy-oracle column:** its headroom at e=0.2 is +6.96 pp, which is **below
the 14.6% run-to-run flip rate** measured in the Part 1 audit (§2d of the 845 report). Treat
"% of oracle gap closed" against this column as uninformative.

## 5. Runtime estimate vs actual

Per the `research/HOSTS.md` rule.

| | value |
|---|---|
| pre-registered estimate | 0.65 h, assuming **median 2 generated tokens** (greedy instruct), from this study's 4B-I × RECENT (2.29 s/trial) and 8B-I × RICH (3.27 s/trial) |
| claimed hard upper bound | 0.77 h |
| **actual** | **0.95 h** (4.05 s/trial) |

**The estimate missed by 1.46×, and the "hard upper bound" was violated.** The bound assumed
4B-I × RICH must be cheaper than 8B-I × RICH because it runs the same frames on half the
parameters. That reasoning is wrong: a large share of per-trial cost at 231 frames is video
decode and vision-tower work, which is **identical across the two and does not shrink with LLM
parameter count**, and the 8B-I reference figure was additionally measured with the RICH frames
already warm in page cache after 4B-T had just traversed the same videos. **Corollary for the
HOSTS rule: do not extrapolate a latency across model sizes without decomposing it into the
components that scale with parameters and those that do not.** The gate (2 h) was never at risk.

## 6. What this establishes

- **Established:** the evidence-coverage interaction is produced by the **state representation**
  — DiD +15.4 pp, CI excludes 0 — and it is a **crossover**: +11.3 pp where evidence is outside
  the window, −4.0 pp where it is inside.
- **Established:** the escalation benefit **does not require a larger model**. Evidence-oracle
  vs random is significant at all three e with the model held fixed (+2.22 pp at e=0.2).
- **Established:** RICH is *worse on average* than RECENT at fixed model (30.53% vs 32.78%);
  its value is entirely conditional on coverage.
- **NOT established — underpowered:** that the model contributes nothing to the interaction.
  C2's MDE (14.54 pp) exceeds its CI upper bound (+13.4 pp). **Inconclusive under Rule 2.**
- **NOT established:** the magnitude of the state interaction. C1's MDE (17.30 pp) exceeds the
  observed +15.4 pp, so the point estimate is likely inflated.
- **Not separable:** frame count from per-frame resolution. RICH changes both at once
  (1.9× frames, 0.53× tok/frame). A cell at matched frames and differing resolution, or vice
  versa, would separate them. Not run.
