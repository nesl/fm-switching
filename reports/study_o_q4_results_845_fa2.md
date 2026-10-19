# Study O — Q4 re-run on the 845-question pool (flash-attn)

**Date:** 2026-10-17
**Trials:** `results/sember/study_o/study_o_q4_trials_fa2.jsonl` — **2,535** (3 cells × 845)
**Scripts:** `experiments/sember/study_o_q4.py --fa2`, `study_o_q4_analyze.py --fa2`
**Backend:** `flash_attention_2`, asserted on all three towers at every model load and recorded
per trial (`attn_implementation` is `flash_attention_2` on 2,535/2,535 rows).
**Compute:** 6.05 h wall (23:06 → 05:09), 4.92 h summed in-trial latency, A6000 (flash, cuda:1).

---

## THIS RUN DOES NOT REPRODUCE THE COMMITTED Q4 RESULT

The committed Q4 (`reports/study_o_q4_results.md`, 2026-10-15) ran on a **520-question pool**.
This run uses an **845-question pool**. **The pool changed; this is not a replication of the
committed numbers, and nothing here supersedes them.**

**Why it changed.** The committed Study O was halted at the §8.2 cell-balance gate because 12 of 24
(category × distance_bin) cells were under-filled and the required S-EMBER videos were absent
from disk. A greedy set cover identified the minimum repair — **84 videos, 9.97 GB** — fetched
2026-10-16. With those videos present the question pool built by the same deterministic
constructor grows from 520 to 845 and every cell clears the gate. Q1–Q3 are no longer blocked.

**Correction (2026-10-17, external audit).** An earlier draft of this report stated the gate
threshold as n≥30. That is wrong. **The plan's §8.2 gate is n≥20** (`reports/study_o_plan.md`
line 196: "ensure ≥ 20 questions per (category × distance_bin × state_arm) cell"). **30 was the
*fetch target*, not the gate** — `study_o_fetch_videos.py` defaults `--target 30` to leave margin
above the gate, and its own `--target` help string says "§8.2 needs >=20". The two numbers were
conflated in the earlier text. Nothing downstream depends on which was used, because the fetch
cleared the higher of the two, but the gate is 20.

**The 84 videos were not sampled at random.** They were chosen by greedy set cover *to fill the
specific under-filled (category × distance_bin) strata* — at each step the video covering the
most still-deficient cells was taken. The added questions are therefore **deliberately enriched
in the strata the 520 pool was short of**, which is the point of the repair but also means the
845 pool is not a random superset of the 520 pool. Any 520-vs-845 difference in a
stratum-sensitive quantity is partly this enrichment by construction.
Q4 was re-run on the same enlarged pool so the Study O cells stay internally consistent with
each other rather than split across two pools.

**The 520 result stays in the record.** `reports/study_o_q4_results.md` and
`results/sember/study_o/study_o_q4_trials.jsonl` are unmodified and remain the committed Q4.

**Comparison rule applied throughout this report:** no figure from the 845 pool is placed next
to a figure from the 520 pool without this sentence attached — *these come from different
question pools (845 vs 520) and are not a before/after measurement of anything.* The two runs
also differ in attention backend (flash-attn here, SDPA there), so any pairwise difference below
has **two** uncontrolled factors, not one.

---

## VERDICT — K4 fired as pre-registered; the interpretation is corrected

> **K4 FIRES, as pre-registered.** Primary test, remote = 8B-I × RICH, e = 0.2:
> **acc(d) − acc(c) = +0.38 pp, 95% CI [−1.20, +1.69]** (clustered bootstrap, 2,000 resamples,
> 234 video clusters). **CI includes 0**, and the point estimate is under the 1 pp threshold.
> Both conjuncts of the rule hold.
>
> **The predictor-vs-random result is INCONCLUSIVE (underpowered), not a real negative:**
> the MDE at e=0.2 is **2.01 pp** and K4's threshold is **1.00 pp — half of it** (§2c).
>
> **The coverage signal is NOT orthogonal to which-arm-is-right.** Two results on this same
> data contradict that reading: escalation gains **+19.6 pp where the local arm lacks the
> evidence vs +1.3 pp where it has it** (DiD **+18.3 pp, CI [+6.3, +31.5]**, §2a), and the
> evidence-distance oracle beats random by **+2.39 pp, CI [+0.92, +3.86]** (§2b) — CI excludes
> zero on both pools.
>
> The Study N2 runtime-signal claim is **not** refuted at the accuracy level by this run. What
> this run shows is that *the particular P4-ranked top-e policy* did not beat random in *this
> design*, which is underpowered for the threshold it tests.

**Correction notice (2026-10-17, external audit).** An earlier draft of this report argued that
the shift from K4 reason (i) to reason (ii) made this "a stronger negative — the test was live
and the signal lost it." **That argument is withdrawn.** It rested on reason (ii) being a
finding, and it is not: the reason is selected by a hard-coded 2 pp threshold at
`study_o_q4_analyze.py:209` and tests nothing (§2c). The signal did not lose; the aggregate test
averaged a +19.6 pp stratum together with a +1.3 pp stratum across a 7.7:1 population split and
reported the mean. Earlier numbers are retained above and below, unaltered.

**Classification under CLAUDE.md Rule 2 — corrected 2026-10-17 (external audit).** An earlier
draft classified this null **Real negative**. That classification is **withdrawn**. The
predictor-vs-random result is **INCONCLUSIVE (underpowered)**: the minimum detectable effect at
e=0.2 is **2.01 pp** (80% power, two-sided α=0.05, from the video-clustered bootstrap SE of
0.72 pp), while **K4's own firing threshold is 1.00 pp — half the MDE**. A true effect exactly
at the threshold the rule tests would be detected less than 80% of the time, so K4 could fire on
a real effect. The observed +0.38 pp CI [−1.20, +1.69] is consistent with no effect *and* with
effects up to the K4 threshold; the design cannot separate them.

**K4 fired as pre-registered, and that stands.** The rule was fixed in advance, its inputs were
computed as specified, and both conjuncts hold. What does not follow is the inference that the
coverage signal is useless — see §2b and §2c, which contradict it.

---

## 1. Cells

| cell | role | n | accuracy | D4 coverage | frames (med) | input tok (med) | latency (med) | budget_hit | think_closed |
|---|---|---|---|---|---|---|---|---|---|
| 4B-I × RECENT | local | 845 | **32.78%** | 88.5% | 121 | 12,437 | 2.31 s | 0 | n/a (instruct) |
| 8B-I × RICH | remote (Instruct) | 845 | **36.21%** | 100.0% | 231 | 12,597 | 3.31 s | 0 | n/a (instruct) |
| 4B-T × RICH | remote (Thinking) | 845 | **30.89%** | 100.0% | 231 | 12,599 | 8.47 s | 5 | 840/845 |

D1–D4 fixes are as applied in the committed run and were verified present in this script before
launch, not re-implemented.

Coverage split on the local cell: `evidence_covered` trials score **34.4%** (n=748), uncovered
trials **20.6%** (n=97). Coverage does predict accuracy at the item level; what it fails to do
is predict *where the remote model wins*, which is what the router needs.

## 2. Policy grid

**Remote = 8B-I × RICH** (paired n = 845, 234 video clusters)

| e | (a) never | (b) always | (c) random | (d) predictor | (e) evidence oracle | (f) accuracy oracle | **d − c** | gap_closed |
|---|---|---|---|---|---|---|---|---|
| 0.1 | 32.78% | 36.21% | 33.12% | 33.96% | 33.73% | 42.72% | +0.84 pp | 8.8% |
| **0.2** | 32.78% | 36.21% | 33.47% | **33.85%** | 35.86% | 46.75% | **+0.38 pp** | **2.9%** |
| 0.3 | 32.78% | 36.21% | 33.81% | 33.85% | 37.16% | 46.75% | +0.04 pp | 0.3% |

**Remote = 4B-T × RICH** (paired n = 845)

| e | (a) never | (b) always | (c) random | (d) predictor | (e) evidence oracle | (f) accuracy oracle | **d − c** | gap_closed |
|---|---|---|---|---|---|---|---|---|
| 0.1 | 32.78% | 30.89% | 32.59% | 33.61% | 33.49% | 42.72% | +1.02 pp | 10.0% |
| **0.2** | 32.78% | 30.89% | 32.40% | **33.73%** | 34.44% | 45.21% | **+1.33 pp** | 10.4% |
| 0.3 | 32.78% | 30.89% | 32.21% | 34.08% | 34.67% | 45.21% | +1.87 pp | 14.4% |

Primary (e=0.2): +1.33 pp, 95% CI **[−0.17, +2.59]**, CI includes 0.

**K4 does not fire on this configuration, and that must not be read as a positive result.** K4
is a conjunction — (d)−(c) < 1 pp **and** CI includes 0 — and only the first conjunct fails.
The CI still includes zero, so there is no evidence the predictor beats random here either. The
same non-firing-but-not-positive pattern appeared on the 520 pool. *(Different pools; not a
measured change.)* Escalating to 4B-T is also escalating to a **worse** model overall (30.89% vs
the local 32.78%), so the policy's apparent lift is being produced on top of a remote arm that
loses on average, which is the opposite of the setting the escalation claim describes.

## 2a. Interaction: where does the remote model actually help? (audit, 2026-10-17)

Split by the **local arm's** `evidence_covered` flag. Remote = 8B-I × RICH.

| stratum | n | local | remote | gain |
|---|---|---|---|---|
| **uncovered** | 97 | 20.6% | **40.2%** | **+19.6 pp** |
| covered | 748 | 34.4% | 35.7% | +1.3 pp |

**Difference-in-differences = +18.3 pp, 95% CI [+6.3, +31.5]** (2,000 video-clustered
resamples, seed 0). **CI excludes 0.**

On the 520 pool the same split gives uncovered n=50 24.0% → 36.0% (+12.0 pp), covered n=470
34.9% → 33.0% (−1.9 pp), **DiD +13.9 pp, CI [−2.3, +31.3]** — same sign and similar magnitude,
CI includes 0 at that n. *(Different pools; the 845 figure is not a measured change from the
520 figure, and the 845 pool is stratum-enriched by construction — see the pool-change section.)*

**This is the result that matters, and the headline test missed it.** When the local arm's
retained frames do not contain the evidence, escalating nearly **doubles** accuracy, 20.6% →
40.2%. When they do, escalation buys +1.3 pp. The remote model helps precisely where coverage
says it should. An aggregate test that averages these two strata together dilutes a +19.6 pp
effect with a +1.3 pp effect across a 7.7:1 population split and reports +3.43 pp.

Split by `farthest > 120 s` instead: near n=581 gain −1.7 pp, far n=264 gain +14.8 pp,
**DiD −16.5 pp CI [−24.7, −8.2]**, excludes 0. (Sign is negative because this stratifier is
oriented the other way: "far" is the hard stratum, where `evidence_covered = False` is the easy
one to be in.) Both stratifiers agree: **the remote arm's advantage is concentrated entirely in
the hard stratum.**

## 2b. Evidence-distance oracle vs random (audit, 2026-10-17)

Policy (e) ranks by the **true** farthest-evidence distance — perfect knowledge of the quantity
the P4 predictor estimates. Paired, video-clustered CI, seed 0, remote = 8B-I × RICH.

| e | (e) oracle − (c) random | 95% CI | excludes 0 |
|---|---|---|---|
| 0.1 | +0.60 pp | [−0.45, +1.78] | no |
| **0.2** | **+2.39 pp** | **[+0.92, +3.86]** | **YES** |
| 0.3 | +3.35 pp | [+1.53, +5.04] | YES |

520 pool, e=0.2: **+1.85 pp, CI [+0.19, +3.72]**, also excludes 0.

**This contradicts the orthogonality claim directly.** A ranking built from the evidence-distance
signal alone beats random escalation by a margin whose CI excludes zero, on both pools. The
signal is *not* orthogonal to which-arm-is-right. It carries real, statistically resolvable
information about where escalation pays — the earlier report's central interpretive claim was
wrong.

## 2c. Predictor quality and the power of the test (audit, 2026-10-17)

| quantity | 845 pool | 520 pool |
|---|---|---|
| AUROC, P4 predictor, target `farthest > 120 s` | 0.736 | 0.761 |
| AUROC, `question_time` alone | 0.724 | 0.706 |
| N2's reported OOF AUROC | 0.766 | 0.766 |

The predictor transfers to Study O roughly intact (0.736–0.761 vs 0.766). Note that
**`question_time` alone reaches 0.724–0.706** — on the 845 pool the MiniLM sentence embedding
adds only **+0.012 AUROC** over a single scalar feature. Whatever P4 contributes beyond
"later questions need more history" is small.

**Minimum detectable effect, predictor vs random at e=0.2:** bootstrap SE 0.72 pp →
**MDE = 2.01 pp** at 80% power, two-sided α=0.05 (520 pool: SE 0.87 pp, MDE 2.43 pp).

**K4's threshold is 1.00 pp, which is 0.50× the MDE.** The rule asks whether an effect smaller
than the design can reliably detect is absent. It will fire on a true 1 pp effect most of the
time. This is why the predictor-vs-random result is relabelled INCONCLUSIVE above.

**K4's *reason* is not a test either.** At `experiments/sember/study_o_q4_analyze.py:209` the
choice between reason (i) and reason (ii) is a hard-coded `abs(acc_b - acc_a) < 0.02` threshold.
No hypothesis about the predictor's coverage ranking is evaluated at that line. The label
"reason (ii)" is a branch of an if-statement, and nothing in it distinguishes "the ranking does
not correlate" from "the test was underpowered to tell". The script now prints a warning to that
effect alongside the label.

## 2d. Run-to-run flip rate — the accuracy-oracle noise floor (audit, 2026-10-17)

The two existing 4B-T runs share 520 questions:

| | accuracy |
|---|---|
| run A (520 pool, SDPA) | 30.00% |
| run B (845 pool, FA2) | 30.00% |

**Flips: 76/520 = 14.6%**, with B-rescues 38 and B-breaks 38 — net **+0.00 pp**. Identical
aggregate accuracy, 14.6% of individual items reshuffled. (The two runs differ in pool *and*
backend, so this is an **upper bound** on per-attempt stochasticity, not a clean seed replicate.)

**Consequence for the oracle headroom.** The accuracy-oracle gap this report quotes as available
headroom is **+13.28 pp** (8B-I) and **+12.80 pp** (4B-T) — both **below the 14.6% flip rate of
a single sampled arm**. The accuracy oracle is defined by escalating where the remote arm
happened to be right and the local arm happened to be wrong *on this draw*; a large part of that
set is items that would flip on a re-run. **The oracle headroom is substantially noise, and no
policy — however good its signal — can capture the part of it that is.** Any claim of the form
"the predictor closes only X% of the oracle gap" inherits this, including the 2.9% and 10.4%
figures in §2 of this report, which should be read as fractions of a partly-illusory denominator.

## 2e. What the remote arm actually changes (audit disclosure, 2026-10-17)

**The remote arm is not "the same thing with more compute".** Local is 4B-I × **RECENT**; remote
is 8B-I × **RICH**. Model size and frame selection change **together**. Every "remote gain" and
every DiD above is therefore a **model + state** effect against local, **not a state effect**
and not a model effect. The design contains no cell that separates them.

Measured from this run's own trials, at the matched ~12.6 k token budget:

| arm | median frames | median input tokens | **median tokens/frame** |
|---|---|---|---|
| 4B-I × RECENT | 121 | 12,437 | **103.0** |
| 8B-I × RICH | 231 | 12,597 | **54.8** |

**RICH frames carry 0.53× the tokens per frame of RECENT** — about half. The two arms spend a
near-identical token budget, but RICH buys ~1.9× as many frames at ~half the spatial detail each.
So "RICH vs RECENT" is simultaneously a temporal-coverage increase and a per-frame-resolution
decrease, and the interaction in §2a is a joint effect of all three changes (model size, frame
count, per-frame resolution). The separating cell — **4B-I × RICH** — was not run.

## 2f. Predictor value over elapsed time alone (audit addition, 2026-10-17)

N2 selected P4 (MiniLM sentence embedding + log(1+question_time)) over P1 (**elapsed time
alone**, `feat_elapsed` in `study_n2_escalation.py`). The margin between them is the entire
case for using question *text* at runtime. Measured on each population, target
`farthest > 120 s`:

| population | n | P4 / text+time | question_time alone | **margin** |
|---|---|---|---|---|
| **N2**, full S-EMBER (OOF, L=120) | 9,448 | **0.766** | **0.696** | **+0.070** |
| Study O, 520 pool | 520 | 0.761 | 0.706 | +0.055 |
| Study O, **845 pool** | 845 | **0.736** | **0.724** | **+0.012** |

*(N2 figures are `reports/study_n2_results.md` §2, L=120 OOF column: P4 0.7656, P1 0.6961.)*

**The margin shrinks monotonically as the population becomes more distance-stratified, and on
the 845 pool it is essentially gone (+0.012).** That ordering is not evidence that the text
predictor degrades. It is most likely an artifact of how the 845 pool was built: the 84 added
videos were chosen by greedy set cover **to fill under-filled (category × distance_bin)
strata**, which enriches the pool in exactly the distance contrast that `question_time` is
good at predicting. Raising the informativeness of the elapsed-time baseline compresses the
margin any text feature can add on top of it.

**Consequence, stated plainly: the text predictor's added value on an unstratified population
is untested here.** The 845 number is a lower bound distorted downward by the stratification,
the 520 number is intermediate, and N2's +0.070 is the only one measured on an unselected
population. None of the three is a clean estimate of what P4 buys over elapsed time on the
workload a deployed router would see. Deciding whether the embedding is worth its cost needs a
measurement on a population that was not selected on distance.

## 3. Results consistency check (CLAUDE.md, six checks)

**1. Cross-check against committed measurements.**

| quantity | this run (845, FA2) | prior (520, SDPA) | source | ratio | agree? |
|---|---|---|---|---|---|
| 4B-I × RECENT accuracy | 32.78% | 33.85% | `study_o_q4_results.md` §1 | 0.97× | agree (different pool) |
| 8B-I × RICH accuracy | 36.21% | 33.27% | ditto | 1.09× | agree (different pool) |
| 4B-T × RICH accuracy | 30.89% | 30.00% | ditto | 1.03× | agree (different pool) |
| median input tokens | 12,437 / 12,597 / 12,599 | 12,439 / 12,599 / 12,601 | ditto | 1.00× | agree |
| K4 on primary config | FIRES | FIRES | ditto | — | agree |

All within 2×. The accuracy rows are **not** a backend or pool comparison — the pool and the
backend both changed — and are tabulated only to confirm nothing moved by an implausible margin.
The median-input-token row is the informative one: it is the quantity that should be invariant
to both changes, and it is, to within 2 tokens.

**2. Physical plausibility.** 4B-T generates at a median 206 tokens in a median 8.47 s including
prefill of ~12.6 k input tokens. Backing out prefill at the committed A6000 curve (~7,100 tok/s
→ ~1.8 s) leaves ~6.7 s for 206 tokens ≈ 31 tok/s decode, against the committed 26.9 tok/s
measured on the n=10 sizing trials of this same cell — 1.15×, under the 2× flag. No result here
is faster than the committed curves.

**3. Distribution sanity.** Latency is reported as median with mean alongside: 4B-T median 8.47 s
vs mean 15.43 s, a 1.8× mean/median ratio reflecting a long right tail (5 trials hit the 8,192
budget). No constant-where-a-distribution-is-expected: all three cells show per-trial spread, and
accuracy varies across the e-grid.

**4. Definition audit.** `evidence_covered` is D4's definition — computed per trial from the
timestamps actually sampled, not from the nominal window — identical to the committed run.
A "trial" is one (question, cell) pair; the pool is the deterministic `(video_id, question_id)`
sort over questions whose video is present on disk. **The pool definition is unchanged; only its
membership grew**, because the set of videos present on disk grew. That is the one definitional
quantity that differs between the two runs and it is stated everywhere it bears on a number.

**5. Claim linkage.** Bears on the Study N2 runtime-signal claim (`research/CLAIMS.md`). The
result **weakens** any extension of that claim from coverage prediction to end-to-end accuracy
routing. It does not speak to Q1–Q3.

**6. Proxy validity.** The P4 predictor's `P(needs_escalation)` is a proxy for "this question
needs the remote model". What it actually measures is predicted evidence coverage. The §1
coverage split shows it is a valid proxy for item difficulty (34.4% vs 20.6%) and the policy grid
shows it is **not** a valid proxy for local-vs-remote advantage. That distinction is the finding,
not a limitation of it.

## 4. Runtime estimate vs actual — the estimate missed

Stated per the `research/HOSTS.md` runtime-estimate rule.

| | estimate | actual |
|---|---|---|
| basis | 11.8 s/trial mean, **median 327 generated tokens**, measured on the first **10 trials of the 4B-T × RICH cell of this same run** | — |
| 4B-T cell | 2.74 h | **4.03 h** |
| all three cells | 3.9 h, ±30% → **2.7–5.1 h** | **6.05 h** |

**The actual fell outside the stated band, 1.19× above its upper edge.** Cause: the n=10 sizing
sample had mean 11.8 s against the full cell's mean 15.43 s. The sample's median generated
length (327) was *higher* than the cell's (206), so the miss was not a token-count error — it was
tail undersampling. Ten trials cannot estimate a mean whose distribution has a 1.8× mean/median
ratio; the ±30% band was set from the n=10 range and the true tail is wider than that range
showed. The band was honest about direction and too narrow in width. Recorded here so the next
sizing run uses a tail-aware quantile rather than a range over ten points.

## 5. What is and is not established

- **Established:** K4 fired as pre-registered on the 845 pool. The predictor-driven policy did
  not beat random escalation at e=0.2 in this design.
- **NOT established, and withdrawn 2026-10-17:** that this is a *Real negative*. It is
  **INCONCLUSIVE (underpowered)** — the K4 threshold is half the minimum detectable effect.
- **Established:** the coverage signal predicts item difficulty (34.4% vs 20.6%) **and**
  predicts where escalation pays — DiD +18.3 pp CI [+6.3, +31.5] (§2a), and the
  evidence-distance oracle beats random with a CI excluding zero (§2b).
- **Established:** the design cannot separate model size from frame selection; the remote arm
  changes both at once, and RICH frames carry 0.53× the tokens per frame of RECENT (§2e).
- **Established:** 14.6% of 4B-T items flip between runs, which exceeds the ~13 pp
  accuracy-oracle headroom — so that headroom is substantially noise (§2d).
- **Not established:** anything about the 520 pool from these numbers, or anything about the
  attention backend — both changed together and neither was isolated here.
- **Not addressed:** Q1, Q2, Q3. They are now unblocked at the data level but were not run.
