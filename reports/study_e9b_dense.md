# StudyE9b-dense: StudyE9 and StudyE12 re-run on a 0.25-s grid with an explicit delivery model

E-id: StudyE9b-dense (`research/EXPERIMENTS.md`, pre-registered 2026-11-12 before any computation). **Offline replay of committed results. CPU only on the flash host: no GPU, no model server, no inference.** Every score is read from StudyD14b's committed 0.25-s trace; every latency and byte count is read from a committed StudyD4 / StudyD7 / StudyD7b / StudyD8 measurement. Scores are the continuous log P(Yes); **no literal Yes/No answer is used anywhere** — alarm, dismiss and trigger are thresholds on the continuous score.

## 0. What this re-run changes, and the one thing it does not

**Why.** StudyE9 and StudyE12 replayed latency on StudyD14's 1-s decision grid with `d = ceil(latency)`. The device's 0.567 s and the cloud's 0.395 s both round to 1 s, so in every cell of both studies *the delay difference between the two tiers was identically zero*. Under CLAUDE.md's own mechanism rule that is a **CONSTANT link**: neither study could test whether the cloud delivers sooner than the device. StudyD14b supplies the same 300 clips at a 0.25-s step, with integer-t scores bit-identical to StudyD14, and shows most of the model-to-model separation lives in the last 0.5 s before the event — exactly where a whole-second grid cannot resolve anything.

**The delivery model (replaces `d = ceil(latency)`).** Every score has a compute time *t* (its frame time) and a delivery time *t + L*, with **L the measured latency, not rounded**. The application's score at grid time *u* is the most recent score whose delivery time is at or before *u* (sample-and-hold). Because compute times sit on the grid, this is an index shift of `ceil(L / 0.25)` steps: **the latency is never rounded; only the moment the application can first read a score is quantised to its own 0.25-s decision grid.**

| tier | latency L | source | cadence | hold shift on the 0.25-s grid | `d` on StudyE9's 1-s grid |
|---|---|---|---|---|---|
| device 4B N = 1 (Jetson Orin) | 0.567 s | StudyD8 arm A total p50 | 0.75 s (it can start a new score only when the previous one completes) | 3 steps = 0.75 s | 1 s |
| cloud 32B N = 1, (ii) measured @25 % load | 0.3950 s | RTT 0.044 + upload 0.2088 + TTFT 0.1422 | resolver cadence c, swept | 2 steps = 0.50 s | 1 s |
| cloud 32B N = 3, (ii) measured @25 % load | 0.9304 s | RTT 0.044 + upload 0.6221 + TTFT 0.2643 | resolver cadence c, swept | 4 steps = 1.00 s | 1 s |
| cloud 4B N = 1, (ii) measured @25 % load | 0.3355 s | RTT 0.044 + upload 0.2088 + TTFT 0.0827 | resolver cadence c, swept | 2 steps = 0.50 s | 1 s |
| cloud 32B N = 1, (ii) measured @75 % load | 0.5504 s | RTT 0.044 + upload 0.2088 + TTFT 0.2976 | resolver cadence c, swept | 3 steps = 0.75 s | 1 s |
| cloud 32B N = 3, (ii) measured @75 % load | 1.2576 s | RTT 0.044 + upload 0.6221 + TTFT 0.5915 | resolver cadence c, swept | 6 steps = 1.50 s | 2 s |
| cloud 4B N = 1, (ii) measured @75 % load | 0.3887 s | RTT 0.044 + upload 0.2088 + TTFT 0.1359 | resolver cadence c, swept | 2 steps = 0.50 s | 1 s |
| cloud 32B N = 1, (iii) JPEG @25 % load | 0.2213 s | RTT 0.044 + upload 0.0351 + TTFT 0.1422 | resolver cadence c, swept | 1 steps = 0.25 s | 1 s |
| cloud 32B N = 3, (iii) JPEG @25 % load | 0.4129 s | RTT 0.044 + upload 0.1046 + TTFT 0.2643 | resolver cadence c, swept | 2 steps = 0.50 s | 1 s |
| cloud 4B N = 1, (iii) JPEG @25 % load | 0.1618 s | RTT 0.044 + upload 0.0351 + TTFT 0.0827 | resolver cadence c, swept | 1 steps = 0.25 s | 1 s |
| cloud 32B N = 1, (iii) JPEG @75 % load | 0.3767 s | RTT 0.044 + upload 0.0351 + TTFT 0.2976 | resolver cadence c, swept | 2 steps = 0.50 s | 1 s |
| cloud 32B N = 3, (iii) JPEG @75 % load | 0.7401 s | RTT 0.044 + upload 0.1046 + TTFT 0.5915 | resolver cadence c, swept | 3 steps = 0.75 s | 1 s |
| cloud 4B N = 1, (iii) JPEG @75 % load | 0.2150 s | RTT 0.044 + upload 0.0351 + TTFT 0.1359 | resolver cadence c, swept | 1 steps = 0.25 s | 1 s |

**The link StudyE9 could not exercise, now instantiated.** Cloud hold shift minus device hold shift, in seconds — zero in every cell of StudyE9 by construction:

| latency setting | 32B N = 1 | 32B N = 3 | 4B N = 1 (counterfactual resolver) |
|---|---|---|---|
| (ii) measured @25 % load | -0.25 s | +0.25 s | -0.25 s |
| (ii) measured @75 % load | +0.00 s | +0.75 s | -0.25 s |
| (iii) JPEG @25 % load | -0.50 s | -0.25 s | -0.50 s |
| (iii) JPEG @75 % load | -0.25 s | +0.00 s | -0.50 s |

A negative number means **the cloud's answer is readable before the device's own**, which the 1-s grid made arithmetically impossible.

**What this re-run does NOT change.** The metric, the episode model, the threshold procedure, the bootstrap, the policies, the budgets, the features and both studies' decision rules are StudyE9's and StudyE12's, unchanged. Two consequences of the grid are stated once and carried through every table:

1. **AP is not comparable across the two grids.** The dense grid has 20,467 negative grid points against StudyE9's 5,196, so chance AP is **0.00728** against **0.0281** — a factor of 3.86. Every AP below is also given as a multiple of *this* grid's chance rate, and no number in this report may be compared with a number in `study_e9_episodes.md` or `study_e12_admission.md`.
2. **StudyE9's decision rule 2 uses an absolute 0.01 AP tolerance**, which on this grid is 1.37x the entire chance rate. The rule is applied **unchanged**, as pre-registered. A scale-matched tolerance (0.0026 = 0.01 x the chance-rate ratio) is reported beside it as a **labelled secondary**, not as the rule.

**One flagged extrapolation.** The device's 0.75 s cadence is saturated duty: StudyD8 measured the 4B N = 1 arm at a *scheduled* 1 Hz (arm A, 1,800 / 1,800 ticks, 0.567 s total p50). Running it back-to-back at 1.33 Hz is supported by StudyD8's finding that a standing query carries no per-request penalty and by its own back-to-back arm C (N = 9, saturated, no throttling, tj 65.7 C), but it was not itself measured. Board power would rise from 28.2 W at 1 Hz to about 9.6 W resident + 1.33 x 16.0 J/s = 30.9 W. **The cadence-1.0 s rows of every table are the conservative reading.** This is a limitation, not a finding.

**Scale of the run.** 150 positive and 150 negative clips; 21,547 positive and 20,467 negative grid points per arm (42,014 total, matching StudyD14b). Study 1: 540 escalation cells at the primary episode configuration, 150 baseline cells, 108 sensitivity cells. Study 2: 672 admission cells. Clip-clustered bootstrap, 2,000 resamples, seed 0, stratified by label, shared across policies so every difference is paired.

## 1. Mechanism verification (CLAUDE.md Steps 1–5)

Recorded in `results/dashcam/study_e9b/e9b_mechanism_verification.md` **before the sweep ran**, and reproduced here in full.

> # StudyE9b-dense — mechanism verification (CLAUDE.md Steps 1–5)
>
> **Recorded 2026-11-12, BEFORE the sweep ran.** Every value below comes from probe runs made only to
> instantiate the links (the input check, the threshold fit, the delivery arithmetic, zero-latency AP,
> two always-on arms, one escalation cell and the Step 4 controls), not from the sweep. Offline replay
> of committed StudyD14b / StudyD14 score traces; CPU only on the flash host; no GPU, no model server,
> no inference. Every score is the continuous log P(Yes); no literal Yes/No answer is used anywhere.
>
> ## Step 0 — input check (recorded first, because it bounds everything else)
>
> StudyD14b's committed claim is that its integer-t **P(Yes)** values are bit-identical to StudyD14's
> on 42,640 / 42,640. That reproduces here. The derived field `score = log P(Yes)` is **not** quite
> bit-identical: **21 of 42,640 integer-t scores differ by 1 ulp** (worst |Δ| = 1.78e-15), with
> `p_yes` identical in every one of the 21. This is the log evaluation, not the model.
>
> Consequence, fixed before any computation: **control (a) is run in two variants.**
>
> - **a1** — input = StudyD14's own trace (the input StudyE9 and StudyE12 actually consumed). This is a
>   pure check of *this code* and must be **exact**.
> - **a2** — input = StudyD14b's integer-t rows. Agreement is bounded below by the 1-ulp input
>   difference above, and the worst disagreement is reported rather than asserted to be zero.
>
> ## Step 1 — the causal chain
>
> The experiment tests FORMULATION's placement decision `p_i` (§Decisions) under §Constraints 2
> (*serving feasibility*: the serving node must answer within the latency SLO) and §Objective. The
> chain is the same one StudyE9 tested, with one link that StudyE9 **could not exercise** restored:
>
> **StudyD14b measured that on a 0.25-s grid the 32B model separates the seconds just before a crash
> from normal driving better than the 4B model, and that most of that separation lives in the last
> 0.5 s before the event** (zero-latency AP at h = 0: 0.053 / 0.091 for 32B N1 / N3 against 0.028 for
> 4B N1; all arms within 1.4–3× chance from h = 0.75 s on). If that is true, then **when and how often
> a score is delivered decides how much of that separation the application can still use.** A score
> computed at frame time *t* is readable only from *t + L*; the application therefore acts on a *stale*
> score, and the staler the score, the further back along the decaying AP-vs-horizon curve it sits.
> Capability and delay trade against each other: the cloud is better per score but arrives later and
> is called only at a cadence; the device is worse per score but is local. A device-triggered escalation
> should therefore buy predictive quality exactly to the extent that the resolver's **delivered** score
> is both better and not too much later than the device's own **delivered** score, and it should buy
> fewer resolver invocations per episode to the extent that a better resolver reaches its alarm or
> dismiss threshold sooner.
>
> **The link StudyE9 could not exercise, and why this study exists.** StudyE9 and StudyE12 quantised
> every latency to a whole second (`d = ceil(latency)`). The device's 0.567 s and the cloud's 0.395 s
> both became 1 s, so *the delay difference between the two tiers was identically zero in every cell of
> both studies*. Under CLAUDE.md's own rule that is a **CONSTANT link**: the quantity that implements
> "the cloud delivers sooner than the device" could not vary, so neither study could test it. On the
> 0.25-s grid it varies (table in Step 2), which is the whole purpose of the re-run.
>
> **A property of the design that bounds the effect, stated before the sweep.** As in StudyE9,
> `tau_alarm`, `tau_dismiss` and `tau_trig` are quantiles of *each model's own* score distribution on
> training-fold negative grid points, so all arms alarm on the same fraction of negative grid points by
> construction. Any effect must come from the *ordering* of grid points within a clip and from positive
> clips, not from a level difference. Two further bounds, both new to the dense grid and both recorded
> here: (1) the dense grid has 3.94× the negatives per positive of the 1-s grid, so chance AP is
> 0.00728 against 0.0281 and **no AP may be compared across the two grids** — every AP in this report is
> also given as a multiple of its own grid's chance rate; (2) StudyE9's decision rule 2 uses an
> **absolute** tolerance of 0.01 AP, which on the dense grid is 1.4× the entire chance rate. The rule is
> applied unchanged, as pre-registered, and a scale-matched variant (0.01 × 0.00728/0.0281 = 0.0026) is
> reported beside it as a clearly labelled secondary, **not** as the rule.
>
> ## Step 2 — instantiate each link
>
> | causal link | implementing quantity | value / range in the probe | varies as expected? | evidence |
> |---|---|---|---|---|
> | the grid can represent sub-second delay | grid step | 0.25 s; 42,014 points per arm (20,467 negative, 21,547 positive); chance rate 0.00728 | yes — 4 points per second where StudyE9 had 1 | StudyD14b trace |
> | a score is readable only after its latency | sample-and-hold shift `D` = ceil(L / step) steps | device 3 steps (0.75 s); cloud 0 / 1 / 2 / 3 / 4 / 6 steps across the five latency settings and three resolvers | yes | delivery arithmetic from StudyD4 / D7 / D7b / D8 |
> | **the cloud can deliver sooner than the device** (CONSTANT in StudyE9) | `D_cloud − D_device` in steps | **−1 step (32B N1 @25 %), 0 (32B N1 @75 %), +1 (32B N3 @25 %), +3 (32B N3 @75 %), −2 (jpeg 32B N1)** — against **0 in every cell of StudyE9** | **yes, and this is the link StudyE9 could not exercise** | delivery arithmetic |
> | the device cannot poll faster than it computes | device cadence = max(1, ceil(L/step)) steps | 3 steps = 0.75 s, i.e. 1.33 Hz | yes; **FLAGGED**: StudyD8 measured sustained 1 Hz (arm A), so 0.75 s is a saturated-duty extrapolation, supported by D8's "no per-request penalty" finding and its back-to-back arm C | StudyD8 |
> | staleness actually costs AP | delivered-stream AP vs zero-latency AP, h = 0 | device-only **0.0126** vs 0.0284 zero-latency; always-cloud 32B N1 **0.0384** vs 0.0530 | yes, strongly — about half the AP is lost to delay alone | probe |
> | resolver capability differs | zero-latency AP at h = 0 / 0.5 s | 4B N1 0.0284 / 0.0189; 32B N1 0.0530 / 0.0415; 32B N3 0.0914 / 0.0437 | yes | probe |
> | thresholds are matched across models | `tau_alarm` at 1 / 5 / 10 % FPR on negative grid points | 4B N1 −0.252 / −2.350 / −4.511; 32B N1 −0.693 / −4.883 / −8.000; 32B N3 −0.523 / −4.511 / −7.126 | yes, each model on its own scale at the same negative-grid-point rate | fitted thresholds |
> | the device opens episodes at a controllable rate | `tau_trig` at 5 / 10 / 20 / 40 % | −2.350 / −4.511 / −7.001 / −10.750 | yes, monotone; it is the load knob | fitted thresholds |
> | each fold has enough data to fit | training negative grid points per fold | 10,154 / 10,313 (of 20,467) | yes | fitted thresholds |
> | resolver capability changes episode resolution | positive-clip episode outcomes, 32B N1 vs 4B N1, (ii) @25 %, cadence 0.5 s, FPR 5 %, trigger 10 % | alarm 425 vs 448, **dismiss 232 vs 175**, cap 5 vs 11, clip_end 33 vs 35 | yes — the 32B resolver resolves by dismissal far more often and runs to the cap half as often | probe |
> | resolution → cloud work | resolver invocations per clip-hour, same cell | positives **1,708.2 (32B) vs 1,939.4 (4B)**; negatives 1,310.8 vs 1,447.2 | yes, in the direction the chain predicts | probe |
> | latency consumes the episode | `D_cloud` against `L_max` = 40 steps | 2–6 steps under the measured settings; 40 steps in the Step 4 control | yes | probe |
> | cadence is a charged knob | resolver calls per episode at cadence 0.25 / 0.5 / 1.0 s | swept; cloud work is charged per call | yes | design |
>
> **No link is ABSENT or CONSTANT on the dense grid.** The link that was CONSTANT in StudyE9 and
> StudyE12 — the delay difference between the tiers — is explicitly instantiated above and is the
> reason for the re-run. The weakest link is the device's 0.75 s saturated cadence, which is an
> extrapolation beyond StudyD8's measured 1 Hz operating point; it is flagged in the report body, not
> buried, and the 1.0 s cadence row of every table is the conservative reading.
>
> ## Step 3 — trace one unit
>
> The runner writes one instrumented episode on the dense grid to
> `e9b_study1_results.json → trace_example`, on a positive clip chosen as the first one carrying both a
> false dismissal before the event and a re-escalation. Per grid point it records: the grid time; the
> time relative to the event; the device's compute index, its score and its **delivery time**; the
> resolver call issued at that grid point (if any) with its own frame time and delivery time; the
> **sample-and-hold value the application actually carries**; which tier it came from; whether an
> episode is open; and the episode's outcome, invocations and GPU-seconds. The delivery times are the
> unrounded measured latencies, so the arithmetic (`frame time + L ≤ grid time`) is checkable by hand.
>
> ## Step 4 — negative controls (run on a representative cell before the sweep)
>
> 1. **Zero latency ⇒ delivered stream equals compute stream.** Held stream == raw score array for
>    **every arm and every one of the 300 clips**. PASS. (This is the pre-registered control (b).)
> 2. **Disable the delivery link and the result must collapse to device-only.** Escalation-32B N1,
>    cadence 0.5 s, FPR 5 %, trigger 10 %, with `L_cloud` raised to 10 s (= `L_max`, so no resolver
>    answer can ever arrive before the episode caps): AP at h = 0 / 0.25 / 0.5 / 0.75 / 1.0 / 1.5 s
>    becomes **0.0126 / 0.0115 / 0.0104 / 0.0098 / 0.0102 / 0.0092**, which is device-only's curve
>    **exactly**, against 0.0160 / 0.0118 / 0.0098 / 0.0103 / 0.0101 / 0.0095 at the measured
>    `L_cloud` = 0.395 s. PASS: the mechanism, not the bookkeeping, drives the difference.
> 3. **Pre-registered and run with the sweep:** control (a) end-to-end reproduction of StudyE9 and
>    StudyE12 (variants a1 and a2 of Step 0); StudyE9's own resolver-swap control (escalation-32B's code
>    path with 4B N1 scores, thresholds and latency must equal escalation-4B exactly); StudyE9's
>    within-clip resolver shuffle; and StudyE12's controls (budget 1.0 equals admit-all exactly, and a
>    within-fold feature shuffle collapses P-trajectory to P-random).
>
> **One control that is NOT an identity, recorded here so it is not later mistaken for a bug.**
> Replacing the resolver's scores by the device's own scores at the device's own latency does *not*
> reproduce device-only (worst stream difference 16.03), because the resolver's call schedule starts at
> the trigger index while the device's compute schedule starts at the clip's first grid point, so the
> two sample-and-hold grids are offset. Control 2 above is the delivery-link control; this one is not
> used.
>
> ## Step 5 — alternative explanations
>
> The headline this study can produce is "on a 0.25-s grid the cloud's escalation buys predictive
> quality (or does not), where on the 1-s grid it did not (or did)". Three alternatives would produce
> the same headline, and what separates them:
>
> 1. **Grid-scale artefact rather than delay resolution.** The dense grid has 3.94× the negatives per
>    positive, so every AP falls. If a reader compares a dense AP with a 1-s AP, any arm will look
>    worse. *Distinguished by:* never comparing across grids; reporting every AP as a multiple of its
>    own chance rate; and by the 1.0-s-cadence rows, which keep the dense grid but restore StudyE9's
>    call rate. If an effect appears only when the grid changes *and* disappears at cadence 1.0 s, it is
>    cadence, not resolution.
> 2. **Cadence rather than delay.** On the dense grid the resolver is called every 0.25 / 0.5 / 1.0 s,
>    so it produces up to 4× as many scores per episode as StudyE9's 1-s resolver. More scores alone
>    improves a held stream, independently of any delay difference. *Distinguished by:* cadence is swept
>    as its own axis at fixed latency, and cloud work is charged per call, so a cadence-driven gain
>    shows up as a proportional GPU-second increase; a delay-driven gain does not.
> 3. **Horizon-grid alignment rather than earliness.** On the 1-s grid h = 0.25 and h = 0.75 round to a
>    whole second and carry no new information; on the dense grid they are real. A gain that appears
>    only at the two new horizons could be interpolation, not earliness. *Distinguished by:* the
>    project's metric rule — earliness is read as the AP-curve horizon shift (StudyE9 §3.1), a property
>    of the curves, now measured on a 0.25-s grid so the interpolation is 4× finer; and the shift is
>    reported with its own clip-bootstrap CI.
>
> If a reading survives none of these three, it is reported as an artefact of the grid or the cadence,
> not as a finding about placement.

## 2. Control (a) — end-to-end reproduction of StudyE9 and StudyE12 (the gate)

> **Pre-registered STOP condition:** on integer-t rows only, with `d = ceil(latency)` and 1-s cadences, this code must reproduce StudyE9's and StudyE12's committed numbers exactly. If it does not, stop and ask.

The same engine runs the dense study and this control; only the step, the cadences and the delivery mode change. Two input variants were fixed **before any computation**, for the reason given in Step 0 of the mechanism verification: StudyD14b's integer-t `p_yes` values are bit-identical to StudyD14's on 42,640 / 42,640, but **21 of them differ by 1 ulp in the derived `score = log P(Yes)`** (worst abs(diff) 1.78e-15).

| variant | input | what it checks |
|---|---|---|
| **a1** | StudyD14's own trace | a pure check of *this code* — must be exact |
| **a2** | StudyD14b's integer-t rows | bounded below by the 1-ulp input difference; the worst disagreement is reported, not asserted to be zero |

**a1 (input StudyD14)**

| study | comparisons | worst AP abs(diff) | worst CI abs(diff) | worst scalar relative abs(diff) | mismatches |
|---|---|---|---|---|---|
| StudyE9 (Study 1): 9 baseline arms x 3 settings + 108 escalation cells | 675 AP+CI, 972 exact counts | **0.000000000000** | **0.000000000000** | — | **0** |
| StudyE12 (Study 2): 672 of 672 committed cells | 672 cells x 5 horizons + 8 scalars each | **0.000000000000** | **0.000000000000** | **0.000e+00** | **0** |

**a2 (input StudyD14b integer rows)**

| study | comparisons | worst AP abs(diff) | worst CI abs(diff) | worst scalar relative abs(diff) | mismatches |
|---|---|---|---|---|---|
| StudyE9 (Study 1): 9 baseline arms x 3 settings + 108 escalation cells | 675 AP+CI, 972 exact counts | **0.000000000000** | **0.000000000000** | — | **0** |
| StudyE12 (Study 2): 672 of 672 committed cells | 672 cells x 5 horizons + 8 scalars each | **0.000000000000** | **0.000000000000** | **0.000e+00** | **0** |

**Control (a) verdict: a1 is EXACT for both studies** — Study 1 PASS, Study 2 PASS. The engine reproduces every committed episode count, outcome histogram, invocation total, alarm count, false dismissal, AP point estimate and bootstrap CI of both prior studies, bit for bit. Everything below is therefore the delivery model and the grid, not a different implementation.

**Variant a2 is also exact.** The 21 one-ulp differences in `score` do not propagate: feeding StudyD14b's integer-t rows through the same code reproduces both studies to 0.000000000000 as well. The two variants were separated in advance because they *could* have differed, not because they did — the threshold comparisons and AP rankings are simply not sensitive at 1e-15.

The fitted predictors also reproduce: trigger counts, per-fold training sizes, AUROC for benefit > 0 and the work model's training R^2 match StudyE12 in 24 of 24 diagnostic cells.

## 3. Study 1, output 1 — predictive quality (Nexar AP at fixed horizons)

AP at h = 0, 0.25, 0.5, 0.75, 1, 1.5 s on the 0.25-s grid; positives are each positive clip's **application-visible** score at the grid point nearest `time_of_event − h`, negatives are every grid point of every negative clip. Clip bootstrap 2,000, seed 0, stratified. **Chance AP on this grid is 0.00728**; the multiple of chance is given under each table. AP does not depend on the alarm threshold for the always-on arms.

### 3.1 Always-on arms: what the delivery model costs

Resolver cadence 0.5 s for the cloud arms; the device runs at its own 0.75 s saturated cadence throughout.

**(i) zero latency**

| arm | h = 0 s | h = 0.25 s | h = 0.5 s | h = 0.75 s | h = 1 s | h = 1.5 s |
|---|---|---|---|---|---|---|
| device-only 4B N = 1 | 0.0284 [0.0160, 0.0500] | 0.0364 [0.0178, 0.0638] | 0.0189 [0.0136, 0.0311] | 0.0147 [0.0117, 0.0201] | 0.0131 [0.0105, 0.0178] | 0.0105 [0.0087, 0.0135] |
| always-cloud 32B N = 1 | 0.0451 [0.0267, 0.0779] | 0.0432 [0.0255, 0.0773] | 0.0380 [0.0218, 0.0704] | 0.0192 [0.0149, 0.0286] | 0.0159 [0.0126, 0.0227] | 0.0125 [0.0101, 0.0166] |
| always-cloud 32B N = 3 | 0.0820 [0.0480, 0.1288] | 0.0484 [0.0291, 0.0844] | 0.0403 [0.0230, 0.0722] | 0.0186 [0.0143, 0.0281] | 0.0142 [0.0114, 0.0192] | 0.0124 [0.0103, 0.0157] |
| always-cloud 4B N = 1 (counterfactual resolver) | 0.0222 [0.0160, 0.0366] | 0.0199 [0.0144, 0.0318] | 0.0167 [0.0127, 0.0254] | 0.0139 [0.0112, 0.0186] | 0.0123 [0.0099, 0.0163] | 0.0098 [0.0082, 0.0126] |
| *multiple of chance* | 3.9/6.2/11.3/3.1x | 5.0/5.9/6.7/2.7x | 2.6/5.2/5.5/2.3x | 2.0/2.6/2.6/1.9x | 1.8/2.2/1.9/1.7x | 1.4/1.7/1.7/1.3x |

**(ii) measured @25 % load**

| arm | h = 0 s | h = 0.25 s | h = 0.5 s | h = 0.75 s | h = 1 s | h = 1.5 s |
|---|---|---|---|---|---|---|
| device-only 4B N = 1 | 0.0126 [0.0102, 0.0165] | 0.0115 [0.0094, 0.0151] | 0.0104 [0.0086, 0.0137] | 0.0098 [0.0081, 0.0132] | 0.0102 [0.0084, 0.0137] | 0.0092 [0.0078, 0.0115] |
| always-cloud 32B N = 1 | 0.0384 [0.0222, 0.0711] | 0.0195 [0.0152, 0.0291] | 0.0161 [0.0128, 0.0230] | 0.0145 [0.0117, 0.0191] | 0.0127 [0.0102, 0.0168] | 0.0110 [0.0091, 0.0138] |
| always-cloud 32B N = 3 | 0.0146 [0.0117, 0.0197] | 0.0139 [0.0114, 0.0175] | 0.0128 [0.0106, 0.0160] | 0.0123 [0.0102, 0.0156] | 0.0116 [0.0097, 0.0147] | 0.0096 [0.0082, 0.0118] |
| always-cloud 4B N = 1 (counterfactual resolver) | 0.0170 [0.0130, 0.0258] | 0.0141 [0.0114, 0.0189] | 0.0125 [0.0101, 0.0167] | 0.0111 [0.0092, 0.0146] | 0.0100 [0.0083, 0.0129] | 0.0103 [0.0085, 0.0133] |
| *multiple of chance* | 1.7/5.3/2.0/2.3x | 1.6/2.7/1.9/1.9x | 1.4/2.2/1.8/1.7x | 1.4/2.0/1.7/1.5x | 1.4/1.7/1.6/1.4x | 1.3/1.5/1.3/1.4x |

**(ii) measured @75 % load**

| arm | h = 0 s | h = 0.25 s | h = 0.5 s | h = 0.75 s | h = 1 s | h = 1.5 s |
|---|---|---|---|---|---|---|
| device-only 4B N = 1 | 0.0126 [0.0102, 0.0165] | 0.0115 [0.0094, 0.0151] | 0.0104 [0.0086, 0.0137] | 0.0098 [0.0081, 0.0132] | 0.0102 [0.0084, 0.0137] | 0.0092 [0.0078, 0.0115] |
| always-cloud 32B N = 1 | 0.0196 [0.0153, 0.0293] | 0.0163 [0.0129, 0.0232] | 0.0146 [0.0118, 0.0192] | 0.0128 [0.0103, 0.0170] | 0.0118 [0.0096, 0.0151] | 0.0100 [0.0083, 0.0126] |
| always-cloud 32B N = 3 | 0.0129 [0.0107, 0.0162] | 0.0125 [0.0103, 0.0159] | 0.0118 [0.0098, 0.0149] | 0.0099 [0.0084, 0.0121] | 0.0098 [0.0083, 0.0119] | 0.0092 [0.0079, 0.0114] |
| always-cloud 4B N = 1 (counterfactual resolver) | 0.0170 [0.0130, 0.0258] | 0.0141 [0.0114, 0.0189] | 0.0125 [0.0101, 0.0167] | 0.0111 [0.0092, 0.0146] | 0.0100 [0.0083, 0.0129] | 0.0103 [0.0085, 0.0133] |
| *multiple of chance* | 1.7/2.7/1.8/2.3x | 1.6/2.2/1.7/1.9x | 1.4/2.0/1.6/1.7x | 1.4/1.8/1.4/1.5x | 1.4/1.6/1.3/1.4x | 1.3/1.4/1.3/1.4x |

**(iii) JPEG @25 % load**

| arm | h = 0 s | h = 0.25 s | h = 0.5 s | h = 0.75 s | h = 1 s | h = 1.5 s |
|---|---|---|---|---|---|---|
| device-only 4B N = 1 | 0.0126 [0.0102, 0.0165] | 0.0115 [0.0094, 0.0151] | 0.0104 [0.0086, 0.0137] | 0.0098 [0.0081, 0.0132] | 0.0102 [0.0084, 0.0137] | 0.0092 [0.0078, 0.0115] |
| always-cloud 32B N = 1 | 0.0434 [0.0257, 0.0776] | 0.0382 [0.0220, 0.0707] | 0.0193 [0.0151, 0.0288] | 0.0160 [0.0127, 0.0228] | 0.0144 [0.0116, 0.0189] | 0.0117 [0.0095, 0.0149] |
| always-cloud 32B N = 3 | 0.0407 [0.0233, 0.0726] | 0.0189 [0.0145, 0.0286] | 0.0144 [0.0116, 0.0195] | 0.0137 [0.0113, 0.0173] | 0.0126 [0.0104, 0.0159] | 0.0115 [0.0095, 0.0146] |
| always-cloud 4B N = 1 (counterfactual resolver) | 0.0201 [0.0146, 0.0320] | 0.0169 [0.0128, 0.0256] | 0.0140 [0.0113, 0.0188] | 0.0124 [0.0100, 0.0165] | 0.0110 [0.0091, 0.0145] | 0.0099 [0.0082, 0.0128] |
| *multiple of chance* | 1.7/6.0/5.6/2.8x | 1.6/5.2/2.6/2.3x | 1.4/2.7/2.0/1.9x | 1.4/2.2/1.9/1.7x | 1.4/2.0/1.7/1.5x | 1.3/1.6/1.6/1.4x |

**(iii) JPEG @75 % load**

| arm | h = 0 s | h = 0.25 s | h = 0.5 s | h = 0.75 s | h = 1 s | h = 1.5 s |
|---|---|---|---|---|---|---|
| device-only 4B N = 1 | 0.0126 [0.0102, 0.0165] | 0.0115 [0.0094, 0.0151] | 0.0104 [0.0086, 0.0137] | 0.0098 [0.0081, 0.0132] | 0.0102 [0.0084, 0.0137] | 0.0092 [0.0078, 0.0115] |
| always-cloud 32B N = 1 | 0.0384 [0.0222, 0.0711] | 0.0195 [0.0152, 0.0291] | 0.0161 [0.0128, 0.0230] | 0.0145 [0.0117, 0.0191] | 0.0127 [0.0102, 0.0168] | 0.0110 [0.0091, 0.0138] |
| always-cloud 32B N = 3 | 0.0191 [0.0146, 0.0287] | 0.0145 [0.0116, 0.0196] | 0.0138 [0.0114, 0.0174] | 0.0127 [0.0105, 0.0160] | 0.0123 [0.0101, 0.0156] | 0.0097 [0.0082, 0.0119] |
| always-cloud 4B N = 1 (counterfactual resolver) | 0.0201 [0.0146, 0.0320] | 0.0169 [0.0128, 0.0256] | 0.0140 [0.0113, 0.0188] | 0.0124 [0.0100, 0.0165] | 0.0110 [0.0091, 0.0145] | 0.0099 [0.0082, 0.0128] |
| *multiple of chance* | 1.7/5.3/2.6/2.8x | 1.6/2.7/2.0/2.3x | 1.4/2.2/1.9/1.9x | 1.4/2.0/1.7/1.7x | 1.4/1.7/1.7/1.5x | 1.3/1.5/1.3/1.4x |

The multiple-of-chance row lists the four arms in table order, separated by `/`.

Two readings of these tables, and one thing not to read:

- **Under (i) zero latency the arms order by capability** (32B N = 3 > 32B N = 1 > 4B N = 1 at h = 0), and **under (ii) measured latency they do not**: 32B N = 3 falls from the top of the table to 0.0146, below both 32B N = 1 and even the counterfactual 4B cloud resolver, because its hold shift is 1.00 s against their 0.50 s.
- **device-only is identical in all four non-zero settings**, as it must be: the device's latency and cadence do not depend on the cloud. Likewise (iii) JPEG @75 % reproduces (ii) @25 % for 32B N = 1 exactly, because both land on a 0.50 s hold shift.
- **Do not read the h = 0.25 s column as a rise.** Several arms score higher at h = 0.25 s than at h = 0 s (device-only at zero latency: 0.0364 against 0.0284). StudyD14b saw the same thing and did not interpret it: with 150 positives and one decision per clip the CIs overlap heavily. It is not interpreted here either.

### 3.2 Zero latency against measured latency: the cost of delay alone

Same scores, same cadence; the only difference is whether the application must wait for them.

| arm | h = 0 s, (i) zero | h = 0 s, (ii) @25 % | lost to delay | h = 0.5 s, (i) | h = 0.5 s, (ii) | lost to delay |
|---|---|---|---|---|---|---|
| device-only 4B N = 1 | 0.0284 | 0.0126 | **-0.0158** | 0.0189 | 0.0104 | **-0.0085** |
| always-cloud 32B N = 1 | 0.0451 | 0.0384 | **-0.0067** | 0.0380 | 0.0161 | **-0.0218** |
| always-cloud 32B N = 3 | 0.0820 | 0.0146 | **-0.0675** | 0.0403 | 0.0128 | **-0.0275** |

### 3.3 Resolver cadence

Always-cloud 32B N = 1 under (ii) @25 % load, AP and cloud work against the cadence. Cloud work is charged per call, so a cadence-driven gain is paid for proportionally — this is the axis that separates 'the cloud delivers sooner' from 'the cloud is simply asked more often' (Step 5, alternative 2).

| cadence | h = 0 s | h = 0.25 s | h = 0.5 s | h = 0.75 s | h = 1 s | h = 1.5 s | calls / clip-h | GPU-s / clip-h |
|---|---|---|---|---|---|---|---|---|
| 0.25 s | 0.0420 | 0.0205 | 0.0169 | 0.0174 | 0.0140 | 0.0111 | 14,400.0 | 972.0 |
| 0.5 s | 0.0384 | 0.0195 | 0.0161 | 0.0145 | 0.0127 | 0.0110 | 7,231.2 | 488.1 |
| 1.0 s | 0.0247 | 0.0173 | 0.0144 | 0.0127 | 0.0112 | 0.0100 | 3,653.6 | 246.6 |

### 3.4 Escalation

Escalation-32B and escalation-4B at the primary episode configuration (k = 2, dismiss quantile 75 %, L_max = 10 s, cooldown 0 s), (ii) @25 % load, cadence 0.5 s, alarm FPR 5 %. Device-only and always-cloud are repeated for reference.

| policy | trigger | h = 0 s | h = 0.25 s | h = 0.5 s | h = 0.75 s | h = 1 s | h = 1.5 s | calls / clip-h | GPU-s / clip-h |
|---|---|---|---|---|---|---|---|---|---|
| device-only | — | 0.0126 | 0.0115 | 0.0104 | 0.0098 | 0.0102 | 0.0092 | 0 | 0.0 |
| escalation-32B 32B N = 1 | 5 % | 0.0134 | 0.0124 | 0.0111 | 0.0102 | 0.0114 | 0.0100 | 777.7 | 52.5 |
| escalation-32B 32B N = 1 | 10 % | 0.0160 | 0.0118 | 0.0098 | 0.0103 | 0.0101 | 0.0095 | 1,514.6 | 102.2 |
| escalation-32B 32B N = 1 | 20 % | 0.0159 | 0.0122 | 0.0105 | 0.0098 | 0.0106 | 0.0094 | 2,591.8 | 174.9 |
| escalation-32B 32B N = 1 | 40 % | 0.0172 | 0.0137 | 0.0118 | 0.0110 | 0.0112 | 0.0098 | 4,382.0 | 295.8 |
| always-cloud 32B N = 1 | — | 0.0384 | 0.0195 | 0.0161 | 0.0145 | 0.0127 | 0.0110 | 7,231.2 | 488.1 |
| escalation-32B 32B N = 3 | 5 % | 0.0137 | 0.0120 | 0.0107 | 0.0099 | 0.0101 | 0.0093 | 856.2 | 162.4 |
| escalation-32B 32B N = 3 | 10 % | 0.0119 | 0.0115 | 0.0107 | 0.0103 | 0.0106 | 0.0097 | 1,606.4 | 304.6 |
| escalation-32B 32B N = 3 | 20 % | 0.0136 | 0.0118 | 0.0104 | 0.0095 | 0.0104 | 0.0097 | 2,719.7 | 515.8 |
| escalation-32B 32B N = 3 | 40 % | 0.0123 | 0.0110 | 0.0104 | 0.0101 | 0.0115 | 0.0102 | 4,498.2 | 853.0 |
| always-cloud 32B N = 3 | — | 0.0146 | 0.0139 | 0.0128 | 0.0123 | 0.0116 | 0.0096 | 7,231.2 | 1,371.3 |
| escalation-4B 4B N = 1 | 5 % | 0.0132 | 0.0118 | 0.0105 | 0.0098 | 0.0106 | 0.0100 | 978.5 | 12.5 |
| escalation-4B 4B N = 1 | 10 % | 0.0139 | 0.0120 | 0.0107 | 0.0102 | 0.0101 | 0.0097 | 1,699.7 | 21.8 |
| escalation-4B 4B N = 1 | 20 % | 0.0138 | 0.0126 | 0.0108 | 0.0099 | 0.0098 | 0.0097 | 2,486.9 | 31.9 |
| escalation-4B 4B N = 1 | 40 % | 0.0146 | 0.0130 | 0.0115 | 0.0104 | 0.0098 | 0.0099 | 4,175.3 | 53.5 |
| always-cloud 4B N = 1 | — | 0.0170 | 0.0141 | 0.0125 | 0.0111 | 0.0100 | 0.0103 | 7,231.2 | 92.7 |

### 3.5 AP-curve horizon shift, 32B against the 4B device arm

> CURVE SHIFT, NOT a per-event time: at the AP the 4B device arm reaches at horizon h, this is how much further ahead the 32B arm reaches the same AP, by linear interpolation of the AP-vs-horizon curve on the 0.25-s grid. It says nothing about when either model first notices a given crash.

Per the project's metric rule, **earliness is read here and only here**: it is a property of the AP curves, now measured on a 0.25-s grid, so the interpolation is 4x finer than StudyE9's.

| latency | resolver | cadence | at h = 0 s | at h = 0.25 s | at h = 0.5 s | at h = 0.75 s | at h = 1 s | at h = 1.5 s |
|---|---|---|---|---|---|---|---|---|
| (i) zero latency | 32B N = 1 | 0.5 s | +0.63 [+0.00, +1.11] | +0.27 [-0.25, +0.59] | +0.27 [+0.11, +0.84] | +0.42 [-0.00, +0.75] | +0.40 [-0.07, +0.50] | +0.00 [-0.05, +0.00] |
| (i) zero latency | 32B N = 3 | 0.5 s | +0.64 [+0.20, +0.94] | +0.29 [-0.09, +0.57] | +0.25 [+0.10, +0.67] | +0.22 [-0.03, +0.75] | +0.30 [-0.21, +0.50] | +0.00 [-0.24, +0.00] |
| (ii) measured @25 % load | 32B N = 1 | 0.5 s | +1.02 [+0.53, +1.50] | +1.10 [+0.47, +1.25] | +1.00 [+0.46, +1.00] | +0.75 [+0.25, +0.75] | +0.50 [-0.05, +0.50] | +0.00 [-0.01, +0.00] |
| (ii) measured @25 % load | 32B N = 3 | 0.5 s | +0.59 [+0.00, +1.43] | +0.77 [-0.25, +1.25] | +0.80 [-0.11, +1.00] | +0.70 [-0.28, +0.75] | +0.35 [-0.75, +0.50] | +0.00 [-0.44, +0.00] |
| (ii) measured @75 % load | 32B N = 1 | 0.5 s | +0.79 [+0.30, +1.47] | +0.83 [+0.23, +1.25] | +0.88 [+0.22, +1.00] | +0.75 [+0.05, +0.75] | +0.43 [-0.29, +0.50] | +0.00 [-0.27, +0.00] |
| (ii) measured @75 % load | 32B N = 3 | 0.5 s | +0.19 [+0.00, +0.74] | +0.28 [-0.25, +1.14] | +0.18 [-0.50, +1.00] | +0.13 [-0.73, +0.75] | -0.29 [-1.00, +0.50] | +0.00 [-0.95, +0.00] |

A positive shift means the 32B arm reaches the 4B arm's AP that many seconds earlier.

## 4. Study 1, output 2 — alarm timing

An alarm is an up-crossing of `tau_alarm` on the application's score stream (baselines) or an episode closing with outcome `alarm` (escalation). Timing is relative to `time_of_event`; negative means before the event.

**(ii) @25 % load, cadence 0.5 s, alarm FPR 5 %.**

| policy | trigger | positives alarmed | alarm time rel. event (p25 / p50 / p75) | alarmed by h = 0 s | alarmed by h = 0.25 s | alarmed by h = 0.5 s | alarmed by h = 0.75 s | alarmed by h = 1 s | alarmed by h = 1.5 s | false alarms / clip-h |
|---|---|---|---|---|---|---|---|---|---|---|
| device-only 4B N = 1 | — | 84 / 150 (0.560) | -11.87 / -3.38 / +1.16 | 0.327 | 0.320 | 0.307 | 0.300 | 0.293 | 0.287 | 118.2 |
| always-cloud 32B N = 1 | — | 120 / 150 (0.800) | -12.99 / -1.06 / +0.95 | 0.507 | 0.453 | 0.440 | 0.427 | 0.407 | 0.393 | 173.1 |
| always-cloud 32B N = 3 | — | 134 / 150 (0.893) | -8.46 / +0.34 / +1.33 | 0.413 | 0.400 | 0.387 | 0.380 | 0.373 | 0.367 | 204.0 |
| escalation-32B 32B N = 1 | 5 % | 51 / 150 (0.340) | -7.42 / +0.27 / +3.35 | 0.153 | 0.147 | 0.140 | 0.133 | 0.133 | 0.133 | 101.3 |
| escalation-32B 32B N = 1 | 10 % | 78 / 150 (0.520) | -7.94 / +0.31 / +4.33 | 0.207 | 0.207 | 0.207 | 0.200 | 0.193 | 0.173 | 144.2 |
| escalation-32B 32B N = 1 | 20 % | 91 / 150 (0.607) | -9.82 / -0.03 / +1.65 | 0.307 | 0.287 | 0.287 | 0.280 | 0.260 | 0.253 | 182.2 |
| escalation-32B 32B N = 1 | 40 % | 107 / 150 (0.713) | -12.77 / -3.10 / +0.95 | 0.427 | 0.420 | 0.393 | 0.393 | 0.373 | 0.367 | 228.7 |
| escalation-32B 32B N = 3 | 5 % | 57 / 150 (0.380) | +0.07 / +1.95 / +4.02 | 0.093 | 0.093 | 0.087 | 0.087 | 0.087 | 0.087 | 52.1 |
| escalation-32B 32B N = 3 | 10 % | 77 / 150 (0.513) | -0.43 / +1.62 / +3.23 | 0.140 | 0.140 | 0.127 | 0.127 | 0.127 | 0.127 | 85.8 |
| escalation-32B 32B N = 3 | 20 % | 101 / 150 (0.673) | -3.22 / +1.05 / +2.80 | 0.200 | 0.200 | 0.180 | 0.180 | 0.180 | 0.180 | 121.7 |
| escalation-32B 32B N = 3 | 40 % | 117 / 150 (0.780) | -4.27 / +1.00 / +2.52 | 0.267 | 0.260 | 0.247 | 0.240 | 0.233 | 0.220 | 168.2 |
| escalation-4B 4B N = 1 | 5 % | 63 / 150 (0.420) | -9.07 / +0.22 / +2.22 | 0.200 | 0.193 | 0.187 | 0.187 | 0.187 | 0.187 | 149.2 |
| escalation-4B 4B N = 1 | 10 % | 76 / 150 (0.507) | -9.39 / +0.12 / +2.96 | 0.233 | 0.233 | 0.227 | 0.213 | 0.207 | 0.200 | 205.4 |
| escalation-4B 4B N = 1 | 20 % | 77 / 150 (0.513) | -9.55 / +0.10 / +2.93 | 0.253 | 0.247 | 0.240 | 0.240 | 0.233 | 0.233 | 237.8 |
| escalation-4B 4B N = 1 | 40 % | 87 / 150 (0.580) | -9.72 / -0.17 / +1.26 | 0.313 | 0.287 | 0.280 | 0.273 | 0.267 | 0.260 | 254.7 |

## 5. Study 1, output 3 — cloud work, episode outcomes, false dismissals, re-escalations

(ii) @25 % load, cadence 0.5 s, alarm FPR 5 %. Episode outcomes are counted over the 150 positive clips. `calls answered after close` counts resolver calls that were issued (and charged) but whose answer arrived after the episode had already closed — a cadence-against-latency waste that StudyE9's 1-s grid could not represent.

| resolver | trigger | episodes (pos) | alarm | dismiss | cap | clip_end | false dismissals before event | re-escalations / clip | calls / clip-h | calls answered after close | GPU-s / clip-h |
|---|---|---|---|---|---|---|---|---|---|---|---|
| escalation-32B 32B N = 1 | 5 % | 390 | 274 | 96 | 2 | 18 | 41 | 2.04 | 777.7 | 648 (28.6%) | 52.5 |
| escalation-32B 32B N = 1 | 10 % | 695 | 425 | 232 | 5 | 33 | 106 | 3.86 | 1,514.6 | 1,171 (26.5%) | 102.2 |
| escalation-32B 32B N = 1 | 20 % | 1156 | 616 | 479 | 7 | 54 | 218 | 6.82 | 2,591.8 | 1,946 (25.7%) | 174.9 |
| escalation-32B 32B N = 1 | 40 % | 1914 | 819 | 1006 | 11 | 78 | 478 | 11.77 | 4,382.0 | 3,377 (26.4%) | 295.8 |
| escalation-32B 32B N = 3 | 5 % | 295 | 166 | 110 | 1 | 18 | 47 | 1.41 | 856.2 | 969 (38.8%) | 162.4 |
| escalation-32B 32B N = 3 | 10 % | 525 | 239 | 249 | 0 | 37 | 107 | 2.73 | 1,606.4 | 1,808 (38.6%) | 304.6 |
| escalation-32B 32B N = 3 | 20 % | 900 | 339 | 504 | 2 | 55 | 229 | 5.11 | 2,719.7 | 3,135 (39.5%) | 515.8 |
| escalation-32B 32B N = 3 | 40 % | 1474 | 438 | 949 | 1 | 86 | 459 | 8.83 | 4,498.2 | 5,285 (40.3%) | 853.0 |
| escalation-4B 4B N = 1 | 5 % | 465 | 351 | 89 | 6 | 19 | 33 | 2.54 | 978.5 | 775 (27.1%) | 12.5 |
| escalation-4B 4B N = 1 | 10 % | 669 | 448 | 175 | 11 | 35 | 75 | 3.69 | 1,699.7 | 1,156 (23.3%) | 21.8 |
| escalation-4B 4B N = 1 | 20 % | 909 | 480 | 359 | 18 | 52 | 157 | 5.17 | 2,486.9 | 1,593 (22.0%) | 31.9 |
| escalation-4B 4B N = 1 | 40 % | 1596 | 524 | 976 | 19 | 77 | 438 | 9.65 | 4,175.3 | 2,897 (23.8%) | 53.5 |

**Episode length and invocations per episode** (same cell, trigger 20 %, positive clips):

| resolver | episodes | mean episode length | invocations / episode | first trigger to final resolution (mean / p50 / max) |
|---|---|---|---|---|
| escalation-32B 32B N = 1 | 1156 | 1.670 s | 3.824 | 21.22 / 22.75 / 46.75 s |
| escalation-32B 32B N = 3 | 900 | 2.312 s | 5.109 | 21.58 / 23.00 / 46.75 s |
| escalation-4B 4B N = 1 | 909 | 2.085 s | 4.647 | 21.02 / 22.88 / 46.75 s |

## 6. Decision rule 1 — does capability shorten episodes?

> **Pre-registered (StudyE9, unchanged):** capability shortens episodes if escalation-32B has lower total cloud invocations per clip-hour than escalation-4B at matched tau_trig and matched alarm FPR, with a paired clip-bootstrap CI excluding 0, in at least 2 of the 3 alarm FPR levels, under latency setting (ii).

Paired difference, escalation-32B − escalation-4B, invocations per clip-hour over all 300 clips (negative = 32B uses fewer). Clip bootstrap 2,000, seed 0. `*` marks a CI excluding 0 on the favourable side.

**(ii) measured @25 % load, cadence 0.25 s**

| resolver | alarm FPR | trigger 5 % | trigger 10 % | trigger 20 % | trigger 40 % |
|---|---|---|---|---|---|
| 32B N = 1 | 1 % | -183.7 [-284.4, -86.8]* | -78.1 [-192.8, +37.5] | +323.2 [+216.1, +434.4] | +289.6 [+213.9, +368.3] |
| 32B N = 1 | 5 % | -186.1 [-273.0, -103.4]* | -292.4 [-403.4, -186.1]* | +100.4 [+18.0, +184.8] | +212.5 [+150.0, +280.2] |
| 32B N = 1 | 10 % | -14.4 [-49.2, +22.2] | -247.8 [-324.6, -175.2]* | -111.0 [-175.8, -46.7]* | +71.6 [+29.3, +111.7] |
| 32B N = 3 | 1 % | -38.0 [-146.2, +72.9] | +209.8 [+74.2, +354.0] | +689.6 [+584.0, +808.3] | +761.6 [+673.0, +854.3] |
| 32B N = 3 | 5 % | +2.4 [-75.6, +75.4] | -35.6 [-153.9, +76.5] | +426.7 [+344.3, +511.8] | +634.4 [+563.3, +703.2] |
| 32B N = 3 | 10 % | +226.6 [+173.6, +282.3] | +91.2 [+13.9, +169.4] | +281.0 [+217.3, +351.5] | +506.2 [+445.4, +569.0] |

**(ii) measured @25 % load, cadence 0.5 s**

| resolver | alarm FPR | trigger 5 % | trigger 10 % | trigger 20 % | trigger 40 % |
|---|---|---|---|---|---|
| 32B N = 1 | 1 % | -124.8 [-177.2, -75.5]* | -28.4 [-85.3, +29.1] | +232.4 [+182.2, +284.0] | +236.5 [+197.3, +276.7] |
| 32B N = 1 | 5 % | -200.8 [-256.5, -150.7]* | -185.1 [-244.9, -127.8]* | +104.9 [+59.7, +151.2] | +206.7 [+168.1, +248.2] |
| 32B N = 1 | 10 % | -48.7 [-78.1, -21.5]* | -243.3 [-295.5, -194.2]* | -63.4 [-105.3, -21.6]* | +131.3 [+98.5, +167.2] |
| 32B N = 3 | 1 % | -51.4 [-110.0, +8.3] | +78.8 [+10.7, +150.3] | +422.9 [+361.7, +490.8] | +441.5 [+390.9, +489.4] |
| 32B N = 3 | 5 % | -122.4 [-178.3, -69.8]* | -93.2 [-159.1, -24.8]* | +232.7 [+180.4, +288.9] | +322.9 [+275.7, +368.8] |
| 32B N = 3 | 10 % | +33.9 [-1.0, +67.0] | -154.9 [-210.1, -99.1]* | +25.7 [-19.6, +72.9] | +161.4 [+115.7, +206.6] |

**(ii) measured @25 % load, cadence 1.0 s**

| resolver | alarm FPR | trigger 5 % | trigger 10 % | trigger 20 % | trigger 40 % |
|---|---|---|---|---|---|
| 32B N = 1 | 1 % | -54.8 [-80.9, -31.3]* | -9.9 [-45.0, +24.3] | +73.3 [+45.2, +102.0] | +98.7 [+76.0, +120.8] |
| 32B N = 1 | 5 % | -108.0 [-139.0, -80.0]* | -104.5 [-140.1, -72.5]* | +16.5 [-9.6, +45.3] | +101.5 [+76.2, +126.2] |
| 32B N = 1 | 10 % | -46.6 [-67.9, -26.7]* | -180.6 [-218.2, -146.1]* | -62.7 [-88.0, -36.9]* | +59.6 [+38.3, +81.3] |
| 32B N = 3 | 1 % | +23.3 [-3.1, +50.4] | +109.0 [+72.5, +145.1] | +299.6 [+264.2, +336.1] | +448.3 [+417.0, +480.4] |
| 32B N = 3 | 5 % | -13.0 [-41.9, +14.4] | +47.0 [+12.7, +80.8] | +254.0 [+221.9, +288.8] | +477.8 [+443.4, +512.0] |
| 32B N = 3 | 10 % | +79.2 [+53.5, +104.8] | +8.2 [-21.8, +38.1] | +208.7 [+179.7, +240.1] | +482.6 [+446.3, +519.1] |

**(ii) measured @75 % load, cadence 0.5 s**

| resolver | alarm FPR | trigger 5 % | trigger 10 % | trigger 20 % | trigger 40 % |
|---|---|---|---|---|---|
| 32B N = 1 | 1 % | -160.7 [-220.3, -105.4]* | -115.5 [-177.8, -51.3]* | +59.6 [+3.2, +117.0] | -137.4 [-183.1, -94.8]* |
| 32B N = 1 | 5 % | -256.4 [-323.8, -199.4]* | -296.1 [-365.5, -226.9]* | -119.6 [-178.4, -59.5]* | -287.2 [-337.7, -234.4]* |
| 32B N = 1 | 10 % | -114.5 [-156.0, -76.7]* | -378.0 [-448.4, -311.1]* | -340.0 [-405.7, -276.7]* | -476.8 [-533.4, -420.6]* |
| 32B N = 3 | 1 % | -9.3 [-69.4, +50.7] | +171.0 [+100.1, +246.2] | +514.8 [+451.5, +584.3] | +523.0 [+469.0, +575.0] |
| 32B N = 3 | 5 % | -79.9 [-139.6, -25.4]* | -30.8 [-100.0, +41.2] | +284.1 [+229.9, +344.0] | +373.2 [+321.1, +425.7] |
| 32B N = 3 | 10 % | +88.8 [+50.7, +126.1] | -91.5 [-147.3, -36.5]* | +72.0 [+20.7, +124.6] | +175.1 [+118.7, +231.1] |

**Rule outcome** — counting alarm-FPR levels won with a CI excluding 0, under (ii), at each cadence. The rule needs at least 2 of 3.

| latency | resolver | cadence | trigger 5 % | trigger 10 % | trigger 20 % | trigger 40 % | rule met at this resolver / cadence |
|---|---|---|---|---|---|---|---|
| (ii) measured @25 % load | 32B N = 1 | 0.25 s | 2 / 3 | 2 / 3 | 1 / 3 | 0 / 3 | **MET** (2 of 4 trigger rates) |
| (ii) measured @25 % load | 32B N = 1 | 0.5 s | 3 / 3 | 2 / 3 | 1 / 3 | 0 / 3 | **MET** (2 of 4 trigger rates) |
| (ii) measured @25 % load | 32B N = 1 | 1.0 s | 3 / 3 | 2 / 3 | 1 / 3 | 0 / 3 | **MET** (2 of 4 trigger rates) |
| (ii) measured @25 % load | 32B N = 3 | 0.25 s | 0 / 3 | 0 / 3 | 0 / 3 | 0 / 3 | **not met** (0 of 4 trigger rates) |
| (ii) measured @25 % load | 32B N = 3 | 0.5 s | 1 / 3 | 2 / 3 | 0 / 3 | 0 / 3 | **MET** (1 of 4 trigger rates) |
| (ii) measured @25 % load | 32B N = 3 | 1.0 s | 0 / 3 | 0 / 3 | 0 / 3 | 0 / 3 | **not met** (0 of 4 trigger rates) |
| (ii) measured @75 % load | 32B N = 1 | 0.25 s | 2 / 3 | 0 / 3 | 0 / 3 | 0 / 3 | **MET** (1 of 4 trigger rates) |
| (ii) measured @75 % load | 32B N = 1 | 0.5 s | 3 / 3 | 3 / 3 | 2 / 3 | 3 / 3 | **MET** (4 of 4 trigger rates) |
| (ii) measured @75 % load | 32B N = 1 | 1.0 s | 3 / 3 | 3 / 3 | 2 / 3 | 2 / 3 | **MET** (4 of 4 trigger rates) |
| (ii) measured @75 % load | 32B N = 3 | 0.25 s | 0 / 3 | 0 / 3 | 0 / 3 | 0 / 3 | **not met** (0 of 4 trigger rates) |
| (ii) measured @75 % load | 32B N = 3 | 0.5 s | 1 / 3 | 1 / 3 | 0 / 3 | 0 / 3 | **not met** (0 of 4 trigger rates) |
| (ii) measured @75 % load | 32B N = 3 | 1.0 s | 1 / 3 | 2 / 3 | 0 / 3 | 0 / 3 | **MET** (1 of 4 trigger rates) |

## 7. Decision rule 2 — is escalation efficient?

> **Pre-registered (StudyE9, unchanged):** escalation is efficient if it keeps AP within 0.01 of always-cloud at h <= 1 s (CIs overlapping) while using <= 50% of always-cloud's cloud work, at some tau_trig.

> **Scale note, recorded before the sweep:** On this grid chance AP is 0.00728 against 0.02806 on StudyE9's 1-s grid, so the unchanged 0.01 tolerance is 1.37x the entire chance rate. The rule is applied UNCHANGED as pre-registered; the scale-matched column is a LABELLED SECONDARY and is not the rule.

**Verdict: MET, in 154 of 360 (latency x resolver x cadence x alarm-FPR x trigger) cells** under the unchanged 0.01 tolerance. Under the labelled scale-matched tolerance (0.0026) it is met in **40** cells.

Every cell that satisfies all three conditions under the **unchanged** rule, cheapest first:

| latency | resolver | cadence | alarm FPR | trigger | AP gap h = 0 s | AP gap h = 0.25 s | AP gap h = 0.5 s | AP gap h = 0.75 s | AP gap h = 1 s | calls / clip-h | % of always-cloud work | GPU-s / clip-h |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| (ii) measured @75 % load | 32B N = 1 | 0.25 s | 10 % | 5 % | +0.0079 | +0.0052 | +0.0065 | +0.0037 | +0.0012 | 1,139.6 | 8% | 76.9 |
| (iii) JPEG @75 % load | 32B N = 3 | 0.25 s | 10 % | 5 % | +0.0089 | +0.0039 | +0.0030 | +0.0030 | +0.0013 | 1,166.7 | 8% | 221.3 |
| (ii) measured @75 % load | 32B N = 1 | 0.5 s | 10 % | 5 % | +0.0064 | +0.0044 | +0.0035 | +0.0023 | +0.0010 | 619.7 | 9% | 41.8 |
| (ii) measured @25 % load | 32B N = 3 | 0.25 s | 10 % | 5 % | +0.0028 | +0.0018 | +0.0025 | +0.0018 | +0.0016 | 1,248.6 | 9% | 236.8 |
| (iii) JPEG @75 % load | 32B N = 3 | 0.5 s | 10 % | 5 % | +0.0049 | +0.0020 | +0.0028 | +0.0027 | +0.0018 | 636.5 | 9% | 120.7 |
| (ii) measured @75 % load | 32B N = 1 | 0.25 s | 5 % | 5 % | +0.0077 | +0.0048 | +0.0066 | +0.0038 | +0.0012 | 1,294.9 | 9% | 87.4 |
| (iii) JPEG @75 % load | 32B N = 3 | 0.25 s | 5 % | 5 % | +0.0090 | +0.0043 | +0.0034 | +0.0034 | +0.0011 | 1,295.2 | 9% | 245.6 |
| (ii) measured @25 % load | 32B N = 3 | 0.25 s | 5 % | 5 % | +0.0031 | +0.0018 | +0.0026 | +0.0017 | +0.0015 | 1,380.2 | 10% | 261.7 |
| (ii) measured @75 % load | 32B N = 3 | 0.25 s | 10 % | 5 % | +0.0007 | +0.0005 | +0.0016 | +0.0006 | -0.0002 | 1,384.3 | 10% | 262.5 |
| (ii) measured @75 % load | 32B N = 1 | 1 s | 10 % | 5 % | +0.0039 | +0.0023 | +0.0016 | +0.0008 | -0.0007 | 364.0 | 10% | 24.6 |
| (ii) measured @75 % load | 32B N = 1 | 0.5 s | 5 % | 5 % | +0.0062 | +0.0037 | +0.0034 | +0.0023 | +0.0009 | 722.2 | 10% | 48.7 |
| (iii) JPEG @75 % load | 32B N = 3 | 0.5 s | 5 % | 5 % | +0.0059 | +0.0025 | +0.0033 | +0.0026 | +0.0018 | 729.0 | 10% | 138.3 |
| (ii) measured @75 % load | 32B N = 3 | 0.25 s | 5 % | 5 % | +0.0009 | +0.0006 | +0.0015 | +0.0006 | -0.0002 | 1,501.2 | 10% | 284.7 |
| (iii) JPEG @75 % load | 32B N = 3 | 1 s | 10 % | 5 % | +0.0023 | +0.0012 | +0.0019 | +0.0017 | +0.0003 | 384.9 | 11% | 73.0 |
| (ii) measured @25 % load | 32B N = 3 | 0.5 s | 10 % | 5 % | +0.0008 | +0.0017 | +0.0019 | +0.0024 | +0.0015 | 768.1 | 11% | 145.7 |
| (ii) measured @75 % load | 32B N = 1 | 0.25 s | 1 % | 5 % | +0.0078 | +0.0045 | +0.0066 | +0.0043 | +0.0018 | 1,547.5 | 11% | 104.5 |
| (ii) measured @25 % load | 32B N = 3 | 0.25 s | 1 % | 5 % | +0.0037 | +0.0025 | +0.0032 | +0.0022 | +0.0016 | 1,620.1 | 11% | 307.2 |
| (ii) measured @75 % load | 32B N = 3 | 0.5 s | 10 % | 5 % | -0.0001 | +0.0011 | +0.0016 | +0.0001 | -0.0008 | 822.9 | 11% | 156.1 |
| (ii) measured @75 % load | 32B N = 1 | 1 s | 5 % | 5 % | +0.0040 | +0.0022 | +0.0021 | +0.0011 | -0.0003 | 428.1 | 12% | 28.9 |
| (ii) measured @25 % load | 32B N = 3 | 0.5 s | 5 % | 5 % | +0.0009 | +0.0019 | +0.0021 | +0.0024 | +0.0015 | 856.2 | 12% | 162.4 |
| (ii) measured @75 % load | 32B N = 1 | 0.5 s | 1 % | 5 % | +0.0062 | +0.0038 | +0.0035 | +0.0028 | +0.0013 | 858.2 | 12% | 57.9 |
| (iii) JPEG @75 % load | 32B N = 3 | 1 s | 5 % | 5 % | +0.0033 | +0.0017 | +0.0026 | +0.0016 | +0.0002 | 440.4 | 12% | 83.5 |
| (ii) measured @75 % load | 32B N = 3 | 0.25 s | 1 % | 5 % | +0.0015 | +0.0010 | +0.0016 | +0.0010 | +0.0000 | 1,740.8 | 12% | 330.1 |
| (iii) JPEG @75 % load | 32B N = 3 | 0.5 s | 1 % | 5 % | +0.0062 | +0.0026 | +0.0037 | +0.0032 | +0.0023 | 889.8 | 12% | 168.7 |
| (ii) measured @75 % load | 32B N = 3 | 0.5 s | 5 % | 5 % | +0.0002 | +0.0012 | +0.0019 | +0.0003 | -0.0006 | 898.7 | 12% | 170.4 |
| (ii) measured @75 % load | 32B N = 3 | 1 s | 10 % | 5 % | -0.0015 | -0.0009 | +0.0000 | +0.0001 | -0.0008 | 456.9 | 13% | 86.6 |
| (i) zero latency | 32B N = 1 | 0.5 s | 10 % | 5 % | +0.0049 | -0.0053 | +0.0058 | +0.0020 | +0.0007 | 959.0 | 13% | 64.7 |
| (ii) measured @25 % load | 32B N = 3 | 0.5 s | 1 % | 5 % | +0.0017 | +0.0026 | +0.0028 | +0.0029 | +0.0017 | 967.6 | 13% | 183.5 |
| (ii) measured @75 % load | 32B N = 3 | 1 s | 5 % | 5 % | -0.0015 | -0.0010 | +0.0001 | +0.0006 | -0.0004 | 501.1 | 14% | 95.0 |
| (ii) measured @75 % load | 32B N = 1 | 1 s | 1 % | 5 % | +0.0036 | +0.0019 | +0.0019 | +0.0013 | +0.0001 | 505.9 | 14% | 34.1 |
| (ii) measured @75 % load | 32B N = 3 | 0.5 s | 1 % | 5 % | +0.0007 | +0.0015 | +0.0020 | +0.0007 | -0.0004 | 1,009.7 | 14% | 191.5 |
| (ii) measured @25 % load | 32B N = 3 | 1 s | 10 % | 5 % | -0.0001 | +0.0009 | +0.0010 | +0.0013 | +0.0006 | 521.7 | 14% | 98.9 |
| (iii) JPEG @75 % load | 32B N = 3 | 1 s | 1 % | 5 % | +0.0035 | +0.0018 | +0.0028 | +0.0021 | +0.0009 | 523.7 | 14% | 99.3 |
| (iii) JPEG @25 % load | 32B N = 1 | 1 s | 1 % | 5 % | +0.0074 | +0.0097 | +0.0050 | +0.0035 | +0.0017 | 545.3 | 15% | 36.8 |
| (ii) measured @25 % load | 32B N = 3 | 1 s | 5 % | 5 % | +0.0001 | +0.0010 | +0.0012 | +0.0010 | +0.0004 | 551.8 | 15% | 104.6 |
| (i) zero latency | 32B N = 1 | 0.5 s | 5 % | 5 % | +0.0047 | -0.0051 | +0.0053 | +0.0021 | +0.0008 | 1,105.0 | 15% | 74.6 |
| (ii) measured @75 % load | 32B N = 3 | 1 s | 1 % | 5 % | -0.0008 | -0.0005 | +0.0001 | +0.0004 | -0.0005 | 562.8 | 15% | 106.7 |
| (i) zero latency | 32B N = 1 | 0.25 s | 10 % | 10 % | +0.0044 | +0.0064 | +0.0099 | +0.0042 | +0.0024 | 2,277.9 | 16% | 153.8 |
| (iii) JPEG @75 % load | 32B N = 3 | 0.25 s | 10 % | 10 % | +0.0093 | +0.0048 | +0.0029 | +0.0028 | +0.0015 | 2,320.0 | 16% | 440.0 |
| (ii) measured @25 % load | 32B N = 3 | 1 s | 1 % | 5 % | +0.0009 | +0.0017 | +0.0017 | +0.0014 | +0.0005 | 590.2 | 16% | 111.9 |
| (ii) measured @75 % load | 32B N = 1 | 0.25 s | 10 % | 10 % | +0.0080 | +0.0056 | +0.0064 | +0.0039 | +0.0019 | 2,342.3 | 16% | 158.1 |
| (ii) measured @25 % load | 32B N = 3 | 0.25 s | 10 % | 10 % | +0.0036 | +0.0014 | +0.0025 | +0.0020 | +0.0019 | 2,441.7 | 17% | 463.1 |
| (iii) JPEG @75 % load | 32B N = 3 | 0.5 s | 10 % | 10 % | +0.0057 | +0.0022 | +0.0023 | +0.0022 | +0.0020 | 1,252.0 | 17% | 237.4 |
| (ii) measured @75 % load | 32B N = 1 | 0.5 s | 10 % | 10 % | +0.0069 | +0.0051 | +0.0038 | +0.0028 | +0.0018 | 1,264.4 | 17% | 85.3 |
| (ii) measured @75 % load | 32B N = 1 | 0.25 s | 5 % | 10 % | +0.0081 | +0.0051 | +0.0067 | +0.0040 | +0.0017 | 2,569.5 | 18% | 173.4 |
| (ii) measured @25 % load | 32B N = 3 | 0.25 s | 5 % | 10 % | +0.0040 | +0.0024 | +0.0027 | +0.0018 | +0.0014 | 2,626.8 | 18% | 498.2 |
| (ii) measured @75 % load | 32B N = 3 | 0.25 s | 10 % | 10 % | +0.0012 | +0.0006 | +0.0015 | +0.0006 | +0.0001 | 2,662.4 | 18% | 504.9 |
| (i) zero latency | 32B N = 1 | 0.25 s | 5 % | 10 % | +0.0056 | +0.0069 | +0.0096 | +0.0049 | +0.0023 | 2,762.5 | 19% | 186.5 |
| (iii) JPEG @75 % load | 32B N = 3 | 0.5 s | 5 % | 10 % | +0.0060 | +0.0029 | +0.0031 | +0.0027 | +0.0016 | 1,388.5 | 19% | 263.3 |
| (ii) measured @75 % load | 32B N = 1 | 0.5 s | 5 % | 10 % | +0.0070 | +0.0051 | +0.0041 | +0.0027 | +0.0016 | 1,403.5 | 19% | 94.7 |
| (ii) measured @75 % load | 32B N = 1 | 0.25 s | 1 % | 10 % | +0.0077 | +0.0052 | +0.0064 | +0.0043 | +0.0020 | 2,808.1 | 20% | 189.5 |
| (iii) JPEG @75 % load | 32B N = 3 | 1 s | 10 % | 10 % | +0.0038 | +0.0023 | +0.0024 | +0.0021 | +0.0004 | 720.1 | 20% | 136.6 |
| (ii) measured @75 % load | 32B N = 3 | 0.25 s | 5 % | 10 % | +0.0013 | +0.0006 | +0.0016 | +0.0008 | +0.0002 | 2,838.9 | 20% | 538.4 |
| (ii) measured @75 % load | 32B N = 1 | 1 s | 10 % | 10 % | +0.0053 | +0.0037 | +0.0026 | +0.0016 | +0.0001 | 738.6 | 20% | 49.9 |
| (ii) measured @25 % load | 32B N = 3 | 0.25 s | 1 % | 10 % | +0.0044 | +0.0024 | +0.0031 | +0.0022 | +0.0018 | 2,959.9 | 21% | 561.3 |
| (ii) measured @25 % load | 32B N = 3 | 0.5 s | 10 % | 10 % | +0.0017 | +0.0013 | +0.0016 | +0.0027 | +0.0010 | 1,487.5 | 21% | 282.1 |
| (ii) measured @75 % load | 32B N = 1 | 0.5 s | 1 % | 10 % | +0.0065 | +0.0049 | +0.0040 | +0.0030 | +0.0018 | 1,521.8 | 21% | 102.7 |
| (i) zero latency | 32B N = 3 | 1 s | 10 % | 5 % | -0.0095 | -0.0019 | +0.0020 | -0.0015 | -0.0036 | 777.0 | 21% | 147.4 |
| (ii) measured @75 % load | 32B N = 3 | 0.5 s | 10 % | 10 % | +0.0002 | +0.0012 | +0.0012 | -0.0002 | -0.0005 | 1,550.9 | 21% | 294.1 |
| (ii) measured @25 % load | 32B N = 1 | 1 s | 10 % | 10 % | +0.0094 | +0.0049 | +0.0042 | +0.0031 | +0.0013 | 784.2 | 21% | 52.9 |
| (iii) JPEG @75 % load | 32B N = 1 | 1 s | 10 % | 10 % | +0.0094 | +0.0049 | +0.0042 | +0.0031 | +0.0013 | 784.2 | 21% | 52.9 |
| (iii) JPEG @75 % load | 32B N = 3 | 0.5 s | 1 % | 10 % | +0.0055 | +0.0031 | +0.0034 | +0.0029 | +0.0023 | 1,569.1 | 22% | 297.6 |
| (i) zero latency | 32B N = 3 | 1 s | 5 % | 5 % | -0.0104 | -0.0034 | +0.0027 | -0.0012 | -0.0031 | 793.1 | 22% | 150.4 |
| (ii) measured @75 % load | 32B N = 3 | 0.25 s | 1 % | 10 % | +0.0018 | +0.0009 | +0.0018 | +0.0010 | +0.0000 | 3,162.5 | 22% | 599.7 |
| (iii) JPEG @75 % load | 32B N = 3 | 1 s | 5 % | 10 % | +0.0043 | +0.0029 | +0.0026 | +0.0019 | +0.0003 | 804.8 | 22% | 152.6 |
| (ii) measured @25 % load | 32B N = 3 | 0.5 s | 5 % | 10 % | +0.0027 | +0.0023 | +0.0021 | +0.0021 | +0.0011 | 1,606.4 | 22% | 304.6 |
| (ii) measured @75 % load | 32B N = 1 | 1 s | 5 % | 10 % | +0.0055 | +0.0040 | +0.0030 | +0.0017 | +0.0001 | 812.6 | 22% | 54.9 |
| (i) zero latency | 32B N = 3 | 1 s | 1 % | 5 % | -0.0093 | +0.0015 | +0.0081 | +0.0001 | -0.0015 | 817.1 | 22% | 155.0 |
| (i) zero latency | 32B N = 1 | 0.25 s | 1 % | 10 % | +0.0045 | +0.0061 | +0.0083 | +0.0048 | +0.0018 | 3,255.0 | 23% | 219.7 |
| (i) zero latency | 32B N = 1 | 1 s | 10 % | 5 % | -0.0002 | -0.0214 | -0.0002 | +0.0002 | -0.0019 | 826.4 | 23% | 55.8 |
| (ii) measured @75 % load | 32B N = 3 | 0.5 s | 5 % | 10 % | +0.0005 | +0.0011 | +0.0018 | +0.0002 | -0.0003 | 1,668.8 | 23% | 316.5 |
| (ii) measured @25 % load | 32B N = 1 | 1 s | 5 % | 10 % | +0.0099 | +0.0059 | +0.0046 | +0.0033 | +0.0013 | 852.7 | 23% | 57.6 |
| (iii) JPEG @75 % load | 32B N = 1 | 1 s | 5 % | 10 % | +0.0099 | +0.0059 | +0.0046 | +0.0033 | +0.0013 | 852.7 | 23% | 57.6 |
| (ii) measured @75 % load | 32B N = 3 | 1 s | 10 % | 10 % | -0.0004 | -0.0008 | +0.0004 | +0.0007 | -0.0000 | 853.1 | 23% | 161.8 |
| (i) zero latency | 32B N = 1 | 1 s | 1 % | 5 % | -0.0080 | -0.0118 | +0.0087 | +0.0012 | +0.0000 | 863.7 | 24% | 58.3 |
| (ii) measured @25 % load | 32B N = 3 | 0.5 s | 1 % | 10 % | +0.0030 | +0.0025 | +0.0024 | +0.0028 | +0.0017 | 1,716.1 | 24% | 325.4 |
| (i) zero latency | 32B N = 1 | 1 s | 5 % | 5 % | -0.0006 | -0.0118 | +0.0041 | +0.0008 | -0.0015 | 869.2 | 24% | 58.7 |
| (ii) measured @75 % load | 32B N = 1 | 1 s | 1 % | 10 % | +0.0053 | +0.0036 | +0.0024 | +0.0014 | +0.0002 | 882.9 | 24% | 59.6 |
| (iii) JPEG @75 % load | 32B N = 3 | 1 s | 1 % | 10 % | +0.0046 | +0.0031 | +0.0031 | +0.0020 | +0.0009 | 894.6 | 24% | 169.6 |
| (ii) measured @25 % load | 32B N = 1 | 1 s | 1 % | 10 % | +0.0096 | +0.0054 | +0.0043 | +0.0028 | +0.0013 | 912.7 | 25% | 61.6 |
| (iii) JPEG @75 % load | 32B N = 1 | 1 s | 1 % | 10 % | +0.0096 | +0.0054 | +0.0043 | +0.0028 | +0.0013 | 912.7 | 25% | 61.6 |
| (ii) measured @75 % load | 32B N = 3 | 0.5 s | 1 % | 10 % | +0.0007 | +0.0015 | +0.0020 | +0.0006 | -0.0000 | 1,808.3 | 25% | 342.9 |
| (ii) measured @75 % load | 32B N = 3 | 1 s | 5 % | 10 % | -0.0006 | -0.0006 | +0.0006 | +0.0007 | -0.0002 | 915.5 | 25% | 173.6 |
| (i) zero latency | 32B N = 3 | 0.5 s | 10 % | 10 % | +0.0059 | +0.0043 | +0.0081 | +0.0017 | -0.0017 | 1,829.9 | 25% | 347.0 |
| (i) zero latency | 32B N = 1 | 0.5 s | 10 % | 10 % | -0.0023 | -0.0127 | +0.0091 | +0.0036 | +0.0018 | 1,860.8 | 26% | 125.6 |
| (i) zero latency | 32B N = 3 | 0.5 s | 5 % | 10 % | +0.0038 | +0.0039 | +0.0088 | +0.0006 | -0.0016 | 1,922.4 | 27% | 364.6 |
| (ii) measured @25 % load | 32B N = 3 | 1 s | 10 % | 10 % | +0.0020 | +0.0016 | +0.0011 | +0.0009 | +0.0002 | 973.0 | 27% | 184.5 |
| (ii) measured @75 % load | 32B N = 3 | 1 s | 1 % | 10 % | +0.0000 | -0.0000 | +0.0007 | +0.0008 | -0.0001 | 992.2 | 27% | 188.2 |
| (ii) measured @25 % load | 32B N = 3 | 1 s | 5 % | 10 % | +0.0022 | +0.0020 | +0.0014 | +0.0011 | +0.0006 | 1,004.2 | 27% | 190.4 |
| (i) zero latency | 32B N = 1 | 0.5 s | 5 % | 10 % | -0.0001 | -0.0115 | +0.0063 | +0.0040 | +0.0014 | 1,997.5 | 28% | 134.8 |
| (ii) measured @25 % load | 32B N = 3 | 1 s | 1 % | 10 % | +0.0026 | +0.0024 | +0.0017 | +0.0016 | +0.0010 | 1,031.7 | 28% | 195.6 |
| (i) zero latency | 32B N = 3 | 0.5 s | 1 % | 10 % | +0.0079 | +0.0077 | +0.0084 | -0.0001 | -0.0018 | 2,101.7 | 29% | 398.6 |
| (iii) JPEG @75 % load | 32B N = 3 | 0.25 s | 10 % | 20 % | +0.0085 | +0.0045 | +0.0025 | +0.0028 | +0.0014 | 4,232.9 | 29% | 802.7 |
| (i) zero latency | 32B N = 3 | 0.25 s | 10 % | 20 % | +0.0096 | +0.0028 | +0.0069 | +0.0039 | +0.0002 | 4,240.1 | 29% | 804.1 |
| (ii) measured @75 % load | 32B N = 1 | 0.25 s | 10 % | 20 % | +0.0074 | +0.0050 | +0.0062 | +0.0039 | +0.0018 | 4,257.6 | 30% | 287.4 |
| (i) zero latency | 32B N = 1 | 0.25 s | 10 % | 20 % | +0.0013 | +0.0046 | +0.0056 | +0.0049 | +0.0021 | 4,267.5 | 30% | 288.1 |
| (ii) measured @25 % load | 32B N = 3 | 0.25 s | 10 % | 20 % | +0.0028 | +0.0015 | +0.0024 | +0.0023 | +0.0022 | 4,362.4 | 30% | 827.3 |
| (iii) JPEG @75 % load | 32B N = 3 | 0.5 s | 10 % | 20 % | +0.0049 | +0.0018 | +0.0022 | +0.0027 | +0.0024 | 2,219.6 | 31% | 420.9 |
| (ii) measured @75 % load | 32B N = 1 | 0.25 s | 5 % | 20 % | +0.0076 | +0.0045 | +0.0063 | +0.0040 | +0.0019 | 4,450.5 | 31% | 300.4 |
| (ii) measured @75 % load | 32B N = 1 | 0.5 s | 10 % | 20 % | +0.0063 | +0.0048 | +0.0029 | +0.0026 | +0.0019 | 2,261.4 | 31% | 152.6 |
| (ii) measured @25 % load | 32B N = 3 | 0.25 s | 5 % | 20 % | +0.0032 | +0.0018 | +0.0022 | +0.0021 | +0.0017 | 4,549.9 | 32% | 862.9 |
| (i) zero latency | 32B N = 3 | 0.25 s | 5 % | 20 % | +0.0075 | +0.0023 | +0.0062 | +0.0041 | +0.0003 | 4,586.2 | 32% | 869.7 |
| (ii) measured @75 % load | 32B N = 1 | 0.25 s | 1 % | 20 % | +0.0068 | +0.0044 | +0.0061 | +0.0041 | +0.0018 | 4,622.9 | 32% | 312.0 |
| (iii) JPEG @75 % load | 32B N = 3 | 0.5 s | 5 % | 20 % | +0.0053 | +0.0027 | +0.0022 | +0.0030 | +0.0028 | 2,347.1 | 32% | 445.1 |
| (i) zero latency | 32B N = 1 | 0.25 s | 5 % | 20 % | +0.0017 | +0.0048 | +0.0057 | +0.0049 | +0.0020 | 4,702.8 | 33% | 317.4 |
| (ii) measured @75 % load | 32B N = 1 | 0.5 s | 5 % | 20 % | +0.0064 | +0.0045 | +0.0032 | +0.0024 | +0.0019 | 2,367.3 | 33% | 159.8 |
| (ii) measured @75 % load | 32B N = 3 | 0.25 s | 10 % | 20 % | +0.0015 | +0.0008 | +0.0013 | +0.0001 | +0.0001 | 4,718.2 | 33% | 894.8 |
| (iii) JPEG @75 % load | 32B N = 3 | 0.25 s | 1 % | 20 % | +0.0088 | +0.0044 | +0.0030 | +0.0029 | +0.0017 | 4,722.7 | 33% | 895.6 |
| (ii) measured @25 % load | 32B N = 3 | 0.25 s | 1 % | 20 % | +0.0035 | +0.0020 | +0.0027 | +0.0023 | +0.0020 | 4,818.6 | 33% | 913.8 |
| (ii) measured @75 % load | 32B N = 3 | 0.25 s | 5 % | 20 % | +0.0018 | +0.0006 | +0.0015 | -0.0001 | +0.0004 | 4,853.6 | 34% | 920.4 |
| (ii) measured @75 % load | 32B N = 1 | 0.5 s | 1 % | 20 % | +0.0055 | +0.0044 | +0.0027 | +0.0028 | +0.0020 | 2,449.9 | 34% | 165.4 |
| (iii) JPEG @75 % load | 32B N = 3 | 1 s | 10 % | 20 % | +0.0031 | +0.0023 | +0.0014 | +0.0015 | +0.0005 | 1,249.0 | 34% | 236.9 |
| (ii) measured @75 % load | 32B N = 1 | 1 s | 10 % | 20 % | +0.0042 | +0.0031 | +0.0019 | +0.0014 | -0.0002 | 1,269.5 | 35% | 85.7 |
| (iii) JPEG @75 % load | 32B N = 3 | 0.5 s | 1 % | 20 % | +0.0046 | +0.0024 | +0.0026 | +0.0031 | +0.0028 | 2,527.4 | 35% | 479.3 |
| (i) zero latency | 32B N = 1 | 0.25 s | 1 % | 20 % | +0.0021 | +0.0033 | +0.0047 | +0.0042 | +0.0016 | 5,077.1 | 35% | 342.7 |
| (i) zero latency | 32B N = 3 | 0.25 s | 1 % | 20 % | +0.0076 | +0.0037 | +0.0068 | +0.0022 | +0.0005 | 5,078.8 | 35% | 963.2 |
| (ii) measured @75 % load | 32B N = 3 | 0.25 s | 1 % | 20 % | +0.0021 | +0.0008 | +0.0014 | -0.0000 | +0.0001 | 5,160.0 | 36% | 978.6 |
| (i) zero latency | 32B N = 3 | 1 s | 1 % | 10 % | -0.0059 | -0.0059 | +0.0067 | +0.0001 | -0.0013 | 1,314.8 | 36% | 249.3 |
| (ii) measured @75 % load | 32B N = 1 | 1 s | 5 % | 20 % | +0.0039 | +0.0031 | +0.0018 | +0.0009 | +0.0002 | 1,323.3 | 36% | 89.3 |
| (ii) measured @25 % load | 32B N = 3 | 0.5 s | 10 % | 20 % | +0.0008 | +0.0018 | +0.0017 | +0.0033 | +0.0016 | 2,627.1 | 36% | 498.2 |
| (iii) JPEG @75 % load | 32B N = 3 | 1 s | 5 % | 20 % | +0.0028 | +0.0021 | +0.0016 | +0.0017 | +0.0008 | 1,329.8 | 36% | 252.2 |
| (i) zero latency | 32B N = 3 | 1 s | 5 % | 10 % | -0.0085 | -0.0073 | +0.0063 | +0.0001 | -0.0016 | 1,346.6 | 37% | 255.4 |
| (i) zero latency | 32B N = 1 | 1 s | 1 % | 10 % | -0.0134 | -0.0053 | +0.0089 | +0.0018 | -0.0011 | 1,347.3 | 37% | 90.9 |
| (ii) measured @75 % load | 32B N = 3 | 0.5 s | 10 % | 20 % | +0.0013 | +0.0019 | +0.0019 | +0.0004 | -0.0003 | 2,673.4 | 37% | 507.0 |
| (iii) JPEG @25 % load | 32B N = 3 | 1 s | 10 % | 20 % | +0.0086 | +0.0031 | +0.0027 | +0.0028 | +0.0011 | 1,355.2 | 37% | 257.0 |
| (ii) measured @25 % load | 32B N = 1 | 1 s | 10 % | 20 % | +0.0097 | +0.0046 | +0.0033 | +0.0033 | +0.0016 | 1,368.6 | 37% | 92.4 |
| (iii) JPEG @75 % load | 32B N = 1 | 1 s | 10 % | 20 % | +0.0097 | +0.0046 | +0.0033 | +0.0033 | +0.0016 | 1,368.6 | 37% | 92.4 |
| (ii) measured @75 % load | 32B N = 1 | 1 s | 1 % | 20 % | +0.0037 | +0.0027 | +0.0011 | +0.0013 | +0.0006 | 1,373.4 | 38% | 92.7 |
| (ii) measured @25 % load | 32B N = 3 | 0.5 s | 5 % | 20 % | +0.0010 | +0.0021 | +0.0024 | +0.0028 | +0.0013 | 2,719.7 | 38% | 515.8 |
| (i) zero latency | 32B N = 3 | 1 s | 10 % | 10 % | -0.0091 | -0.0069 | +0.0043 | -0.0009 | -0.0016 | 1,390.2 | 38% | 263.6 |
| (ii) measured @75 % load | 32B N = 3 | 0.5 s | 5 % | 20 % | +0.0014 | +0.0019 | +0.0019 | +0.0005 | +0.0001 | 2,771.1 | 38% | 525.5 |
| (iii) JPEG @25 % load | 32B N = 3 | 1 s | 5 % | 20 % | +0.0083 | +0.0039 | +0.0024 | +0.0027 | +0.0001 | 1,407.6 | 39% | 266.9 |
| (ii) measured @25 % load | 32B N = 1 | 1 s | 5 % | 20 % | +0.0078 | +0.0047 | +0.0034 | +0.0029 | +0.0018 | 1,407.6 | 39% | 95.0 |
| (iii) JPEG @75 % load | 32B N = 1 | 1 s | 5 % | 20 % | +0.0078 | +0.0047 | +0.0034 | +0.0029 | +0.0018 | 1,407.6 | 39% | 95.0 |
| (iii) JPEG @75 % load | 32B N = 3 | 1 s | 1 % | 20 % | +0.0037 | +0.0026 | +0.0023 | +0.0020 | +0.0012 | 1,418.3 | 39% | 269.0 |
| (ii) measured @25 % load | 32B N = 1 | 1 s | 1 % | 20 % | +0.0080 | +0.0043 | +0.0029 | +0.0018 | +0.0016 | 1,419.6 | 39% | 95.8 |
| (iii) JPEG @75 % load | 32B N = 1 | 1 s | 1 % | 20 % | +0.0080 | +0.0043 | +0.0029 | +0.0018 | +0.0016 | 1,419.6 | 39% | 95.8 |
| (ii) measured @25 % load | 32B N = 3 | 0.5 s | 1 % | 20 % | +0.0015 | +0.0021 | +0.0027 | +0.0032 | +0.0020 | 2,813.2 | 39% | 533.5 |
| (ii) measured @75 % load | 32B N = 3 | 1 s | 10 % | 20 % | -0.0004 | -0.0001 | +0.0004 | +0.0004 | -0.0002 | 1,441.6 | 39% | 273.4 |
| (i) zero latency | 32B N = 1 | 1 s | 5 % | 10 % | -0.0002 | -0.0136 | +0.0056 | +0.0026 | +0.0004 | 1,452.2 | 40% | 98.0 |
| (iii) JPEG @25 % load | 32B N = 3 | 1 s | 1 % | 20 % | +0.0098 | +0.0043 | +0.0029 | +0.0025 | +0.0012 | 1,461.1 | 40% | 277.1 |
| (ii) measured @75 % load | 32B N = 3 | 0.5 s | 1 % | 20 % | +0.0021 | +0.0021 | +0.0020 | +0.0006 | +0.0003 | 2,905.1 | 40% | 550.9 |
| (ii) measured @75 % load | 32B N = 3 | 1 s | 5 % | 20 % | -0.0005 | -0.0003 | +0.0005 | +0.0002 | -0.0004 | 1,484.8 | 41% | 281.6 |
| (i) zero latency | 32B N = 1 | 1 s | 10 % | 10 % | -0.0036 | -0.0139 | +0.0042 | +0.0010 | -0.0003 | 1,519.0 | 42% | 102.5 |
| (ii) measured @75 % load | 32B N = 3 | 1 s | 1 % | 20 % | +0.0002 | +0.0005 | +0.0011 | +0.0007 | +0.0001 | 1,548.9 | 42% | 293.7 |
| (iii) JPEG @25 % load | 32B N = 1 | 1 s | 5 % | 20 % | +0.0011 | +0.0096 | +0.0044 | +0.0029 | +0.0014 | 1,558.1 | 43% | 105.2 |
| (i) zero latency | 32B N = 3 | 0.5 s | 10 % | 20 % | -0.0011 | -0.0003 | +0.0047 | -0.0009 | -0.0014 | 3,147.1 | 44% | 596.8 |
| (i) zero latency | 32B N = 3 | 0.5 s | 5 % | 20 % | -0.0049 | -0.0003 | +0.0035 | +0.0004 | +0.0002 | 3,174.5 | 44% | 602.0 |
| (i) zero latency | 32B N = 3 | 0.5 s | 1 % | 20 % | -0.0018 | +0.0030 | +0.0048 | -0.0004 | +0.0004 | 3,235.8 | 45% | 613.7 |
| (ii) measured @25 % load | 32B N = 3 | 1 s | 10 % | 20 % | +0.0011 | +0.0019 | +0.0015 | +0.0016 | +0.0011 | 1,640.0 | 45% | 311.0 |
| (ii) measured @25 % load | 32B N = 3 | 1 s | 5 % | 20 % | +0.0015 | +0.0020 | +0.0017 | +0.0013 | +0.0009 | 1,645.2 | 45% | 312.0 |
| (ii) measured @25 % load | 32B N = 3 | 1 s | 1 % | 20 % | +0.0022 | +0.0021 | +0.0019 | +0.0015 | +0.0014 | 1,645.9 | 45% | 312.1 |
| (i) zero latency | 32B N = 1 | 0.5 s | 5 % | 20 % | -0.0038 | -0.0143 | +0.0049 | +0.0047 | +0.0029 | 3,260.2 | 45% | 220.1 |
| (i) zero latency | 32B N = 1 | 0.5 s | 10 % | 20 % | -0.0052 | -0.0146 | +0.0065 | +0.0045 | +0.0022 | 3,275.6 | 45% | 221.1 |

**Where the rule fails.** The three conditions separately, at (ii) @25 % load, cadence 0.5 s, alarm FPR 5 %:

| resolver | trigger | AP gap h = 0 s | AP gap h = 0.25 s | AP gap h = 0.5 s | AP gap h = 0.75 s | AP gap h = 1 s | all CIs overlap? | work fraction | <= 50 %? | met (unchanged) | met (scale-matched) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 32B N = 1 | 5 % | +0.0250 | +0.0071 | +0.0051 | +0.0043 | +0.0013 | no | 11% | yes | no | no |
| 32B N = 1 | 10 % | +0.0224 | +0.0077 | +0.0063 | +0.0042 | +0.0025 | no | 21% | yes | no | no |
| 32B N = 1 | 20 % | +0.0225 | +0.0072 | +0.0056 | +0.0047 | +0.0020 | yes | 36% | yes | no | no |
| 32B N = 1 | 40 % | +0.0212 | +0.0057 | +0.0044 | +0.0035 | +0.0015 | yes | 61% | no | no | no |
| 32B N = 3 | 5 % | +0.0009 | +0.0019 | +0.0021 | +0.0024 | +0.0015 | yes | 12% | yes | **MET** | MET |
| 32B N = 3 | 10 % | +0.0027 | +0.0023 | +0.0021 | +0.0021 | +0.0011 | yes | 22% | yes | **MET** | no |
| 32B N = 3 | 20 % | +0.0010 | +0.0021 | +0.0024 | +0.0028 | +0.0013 | yes | 38% | yes | **MET** | no |
| 32B N = 3 | 40 % | +0.0022 | +0.0029 | +0.0023 | +0.0022 | +0.0001 | yes | 62% | no | no | no |

## 8. Episode-configuration sensitivity (k and the dismiss quantile)

(ii) @25 % load, cadence 0.5 s. The primary configuration is k = 2, dismiss quantile 75 %. AP point estimates only (no CI); these cells exist to show the primary choice is not load-bearing.

| resolver | trigger | config | h = 0 s | h = 0.25 s | h = 0.5 s | h = 0.75 s | h = 1 s | h = 1.5 s | calls / clip-h |
|---|---|---|---|---|---|---|---|---|---|
| 32B N = 1 | 20 % | primary (k = 2, q = 75 %) | 0.0159 | 0.0122 | 0.0105 | 0.0098 | 0.0106 | 0.0094 | 2,591.8 |
| 32B N = 1 | 20 % | k = 1 | 0.0142 | 0.0119 | 0.0108 | 0.0103 | 0.0103 | 0.0094 | 2,372.8 |
| 32B N = 1 | 20 % | k = 3 | 0.0155 | 0.0125 | 0.0112 | 0.0098 | 0.0099 | 0.0090 | 2,775.9 |
| 32B N = 1 | 20 % | q = 50 % | 0.0161 | 0.0135 | 0.0117 | 0.0107 | 0.0105 | 0.0097 | 3,019.9 |
| 32B N = 3 | 20 % | primary (k = 2, q = 75 %) | 0.0136 | 0.0118 | 0.0104 | 0.0095 | 0.0104 | 0.0097 | 2,719.7 |
| 32B N = 3 | 20 % | k = 1 | 0.0124 | 0.0110 | 0.0104 | 0.0097 | 0.0101 | 0.0091 | 2,545.6 |
| 32B N = 3 | 20 % | k = 3 | 0.0133 | 0.0116 | 0.0104 | 0.0096 | 0.0101 | 0.0098 | 2,866.4 |
| 32B N = 3 | 20 % | q = 50 % | 0.0134 | 0.0127 | 0.0108 | 0.0101 | 0.0103 | 0.0101 | 3,047.0 |

## 9. Latency setting (iii) — JPEG upload (SENSITIVITY)

> (iii) JPEG upload, SENSITIVITY: model scores are the PNG scores; JPEG accuracy parity for S-EMBER was NOT established by StudyE10a-full, and Nexar ranking parity is cited from StudyE10a only.

**No score in this study was recomputed on JPEG frames.** Setting (iii) replaces only the upload time of setting (ii) with the time to send StudyD4's JPEG q90 request bytes over the same uplink, with the same RTT, the same server TTFT and the same device latency. StudyE10a-full tested JPEG q88 on all 845 S-EMBER questions and found it **NOT acceptable** under its pre-registered ±2 pp rule (K3 +0.83 pp [−0.24, +2.01], K1 −0.59 pp [−2.14, +0.84]: no evidence of a drop, but ±2 pp not excluded), so parity remains unestablished for that workload; Nexar ranking parity is cited from StudyE10a. Setting (iii) therefore stays a labelled sensitivity.

What changes is the hold shift. At cadence 0.5 s, alarm FPR 5 %:

| load | arm | hold shift (ii) | hold shift (iii) | AP h = 0 s, (ii) → (iii) | AP h = 0.5 s, (ii) → (iii) | AP h = 1 s, (ii) → (iii) |
|---|---|---|---|---|---|---|
| 25 % | always-cloud 32B N = 1 | 0.50 s | 0.25 s ** | 0.0384 → 0.0434 | 0.0161 → 0.0193 | 0.0127 → 0.0144 |
| 25 % | always-cloud 32B N = 3 | 1.00 s | 0.50 s ** | 0.0146 → 0.0407 | 0.0128 → 0.0144 | 0.0116 → 0.0126 |
| 75 % | always-cloud 32B N = 1 | 0.75 s | 0.50 s ** | 0.0196 → 0.0384 | 0.0146 → 0.0161 | 0.0118 → 0.0127 |
| 75 % | always-cloud 32B N = 3 | 1.50 s | 0.75 s ** | 0.0129 → 0.0191 | 0.0118 → 0.0138 | 0.0098 → 0.0123 |

`**` marks a changed hold shift. **On the dense grid every arm's hold shift changes under JPEG**, where StudyE9's 1-s grid left five of its eight cells unchanged — the finer grid resolves a transport saving the whole-second rule rounded away. The invariant that does hold is across settings: any two settings landing on the same hold shift must give bit-identical AP (for example (iii) JPEG @75 % and (ii) @25 % for 32B N = 1, both 0.50 s), and that equality is check 1 in §14.

**This is the one place where setting (iii) would change a conclusion, which is why its unmeasured parity matters.** Cutting the upload by a factor of six drops 32B N = 3's hold shift from 1.00 s to 0.50 s, and its AP at h = 0 rises from 0.0146 to 0.0407 — from *below* 32B N = 1's 0.0384 to roughly level with it, recovering 39% of the gap between delivered and zero-latency N = 3. **If JPEG parity held, the 'more frames is the wrong way to spend capability' finding of §15 would weaken substantially.** It is not established: this row is a sensitivity, and the measurement that would settle it is a Nexar JPEG accuracy check on these arms, not StudyE10a-full's S-EMBER test.

## 10. One instrumented episode on the dense grid

Clip `00005.mp4` (positive, event at 20.874 s, duration 40.099 s), resolver 32B N = 1 under (ii) measured @25 % load at cadence 0.5 s, alarm FPR 5 %, trigger 20 %, primary episode configuration. Chosen as the first positive clip carrying both a false dismissal before the event and a re-escalation.

- device: L = 0.567 s, cadence 0.75 s, hold shift 0.75 s
- cloud: L = 0.3950 s, hold shift 0.50 s
- `tau_trigger` -7.0009, `tau_alarm` -4.8826, `tau_dismiss` -13.25; k = 2, L_max 10 s, cooldown 0 s
- 30 episodes, 77 resolver calls, 5.1975 GPU-s

The 24 grid points around the first dismissal. `frame t` is the decision's frame time, `delivered at` is `frame t + L` (unrounded), and the application's value is the most recent score already delivered. Arithmetic is checkable by hand: a score is readable at the first grid point at or after its delivery time.

| grid t | rel. event | device frame t | device score | device delivered at | age | resolver call at | its delivery | resolver score delivered (frame t) | application score | source | episode open |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 7.75 | -13.124 | 6.75 | -6.2519 | 7.317 | 1.00 s | 7.75 | 8.145 | -1.2234 (7.25) | -1.2234 | resolver | yes |
| 8.0 | -12.874 | 6.75 | -6.2519 | 7.317 | 1.25 s | 8.0 | 8.395 | — | -6.2519 | device | yes |
| 8.25 | -12.624 | 7.5 | -2.1269 | 8.067 | 0.75 s | — | — | *dropped: frame 7.75* | -2.1269 | device | yes |
| 8.5 | -12.374 | 7.5 | -2.1269 | 8.067 | 1.00 s | 8.5 | 8.895 | -0.8259 (8.0) | -0.8259 | resolver | yes |
| 8.75 | -12.124 | 7.5 | -2.1269 | 8.067 | 1.25 s | 8.75 | 9.145 | — | -2.1269 | device | yes |
| 9.0 | -11.874 | 8.25 | -6.0025 | 8.817 | 0.75 s | — | — | *dropped: frame 8.5* | -6.0025 | device | yes |
| 9.25 | -11.624 | 8.25 | -6.0025 | 8.817 | 1.00 s | 9.25 | 9.645 | -6.5015 (8.75) | -6.5015 | resolver | yes |
| 9.5 | -11.374 | 8.25 | -6.0025 | 8.817 | 1.25 s | — | — | — | -6.5015 | resolver | yes |
| 9.75 | -11.124 | 9.0 | -8.0003 | 9.567 | 0.75 s | 9.75 | 10.145 | -7.0009 (9.25) | -7.0009 | resolver | yes |
| 10.0 | -10.874 | 9.0 | -8.0003 | 9.567 | 1.00 s | — | — | — | -7.0009 | resolver | yes |
| 10.25 | -10.624 | 9.0 | -8.0003 | 9.567 | 1.25 s | 10.25 | 10.645 | -9.3751 (9.75) | -9.3751 | resolver | yes |
| 10.5 | -10.374 | 9.75 | -3.5298 | 10.317 | 0.75 s | — | — | — | -9.3751 | resolver | yes |
| 10.75 | -10.124 | 9.75 | -3.5298 | 10.317 | 1.00 s | 10.75 | 11.145 | -8.6252 (10.25) | -8.6252 | resolver | yes |
| 11.0 | -9.874 | 9.75 | -3.5298 | 10.317 | 1.25 s | — | — | — | -8.6252 | resolver | yes |
| 11.25 | -9.624 | 10.5 | -8.7502 | 11.067 | 0.75 s | 11.25 | 11.645 | -14.375 (10.75) | -14.375 | resolver | yes |
| 11.5 | -9.374 | 10.5 | -8.7502 | 11.067 | 1.00 s | — | — | — | -14.375 | resolver | yes |
| 11.75 | -9.124 | 10.5 | -8.7502 | 11.067 | 1.25 s | 11.75 | 12.145 | -14.75 (11.25) | -14.75 | resolver | yes |
| 12.0 | -8.874 | 11.25 | -8.0003 | 11.817 | 0.75 s | — | — | — | -8.0003 | device | no |
| 12.25 | -8.624 | 11.25 | -8.0003 | 11.817 | 1.00 s | — | — | *dropped: frame 11.75* | -8.0003 | device | no |
| 12.5 | -8.374 | 11.25 | -8.0003 | 11.817 | 1.25 s | — | — | — | -8.0003 | device | no |
| 12.75 | -8.124 | 12.0 | -6.7512 | 12.567 | 0.75 s | 12.75 | 13.145 | — | -6.7512 | device | yes |
| 13.0 | -7.874 | 12.0 | -6.7512 | 12.567 | 1.00 s | — | — | — | -6.7512 | device | yes |

Episodes on this clip (first eight):

| t0 | t_close | length | outcome | resolver calls |
|---|---|---|---|---|
| 3.75 | 4.25 | 0.75 s | alarm | 2 |
| 4.5 | 5.0 | 0.75 s | alarm | 2 |
| 5.25 | 6.25 | 1.25 s | alarm | 3 |
| 6.5 | 7.0 | 0.75 s | alarm | 2 |
| 7.25 | 7.75 | 0.75 s | alarm | 2 |
| 8.0 | 8.5 | 0.75 s | alarm | 2 |
| 8.75 | 11.75 | 3.25 s | dismiss | 7 |
| 12.75 | 16.25 | 3.75 s | dismiss | 8 |

## 11. Study 2 — admission under a cloud capacity budget (StudyE12 re-run)

StudyE12's design unchanged on the dense grid and delivery model: resolver cadence 0.5 s, (ii) measured @25 % load primary. Each trigger that would open an episode is either **admitted** (the 32B resolver runs, as in Study 1) or **kept local** (the device's own 4B score continues and alarms on its own `tau_alarm`). Budget B is the fraction of triggers admitted, enforced per fold by a ranking-score cutoff fitted on training clips; the realized test fraction is reported.

- Features (strictly causal, trigger grid point only): the device's **delivered** score at t; mean / max / least-squares slope / std over the last 12 and 20 grid points (= 3 s and 5 s); earlier triggers and earlier episode outcomes in the clip; the current cloud hold shift. **Excluded:** elapsed time since clip start; time since the standing query began; clip metadata (scene, light, weather) - primary predictor.
- Training target (ranking only, never evaluation): per-episode utility U = 1[alarm on a positive clip at least h* = 0.5 s before the event] − lambda x (false alarms in the episode), **lambda = 0.0073289**. lambda = positives per negative grid point on THIS grid (150 / 20467). StudyE12's 1-s-grid lambda was 150 / 5196 = 0.0288684, which is 3.9390x this value and is covered by the last sensitivity multiplier.
- P-random is the mean over 20 seeds.

**Resolver 32B N = 1, primary configuration (alarm FPR 5 %, trigger 20 %, (ii) measured @25 % load).**

| budget | policy | realized admitted | AP h = 0 s | AP h = 0.25 s | AP h = 0.5 s | AP h = 0.75 s | AP h = 1 s | AP h = 1.5 s | GPU-s / clip-h | positives alarmed | false alarms / clip-h |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0.25 | admit-none | 0.000 | 0.0126 [0.0102, 0.0165] | 0.0115 [0.0094, 0.0151] | 0.0104 [0.0086, 0.0137] | 0.0098 [0.0081, 0.0132] | 0.0102 [0.0084, 0.0137] | 0.0092 [0.0078, 0.0115] | 0.0 | 0.560 | 225.1 |
| 0.25 | P-random | 0.255 | 0.0129 [0.0104, 0.0171] | 0.0118 [0.0097, 0.0154] | 0.0106 [0.0088, 0.0137] | 0.0100 [0.0083, 0.0132] | 0.0103 [0.0085, 0.0137] | 0.0094 [0.0079, 0.0117] | 38.3 | 0.596 | 212.3 |
| 0.25 | P-score | 0.420 | 0.0132 [0.0107, 0.0172] | 0.0121 [0.0098, 0.0158] | 0.0113 [0.0092, 0.0151] | 0.0103 [0.0085, 0.0134] | 0.0105 [0.0087, 0.0135] | 0.0099 [0.0083, 0.0124] | 48.9 | 0.500 | 172.4 |
| 0.25 | P-trajectory | 0.265 | 0.0129 [0.0104, 0.0171] | 0.0122 [0.0099, 0.0162] | 0.0107 [0.0088, 0.0141] | 0.0100 [0.0083, 0.0135] | 0.0107 [0.0087, 0.0145] | 0.0093 [0.0078, 0.0116] | 36.5 | 0.593 | 199.8 |
| 0.25 | P-trajectory-work | 0.257 | 0.0128 [0.0103, 0.0170] | 0.0119 [0.0096, 0.0159] | 0.0104 [0.0085, 0.0138] | 0.0097 [0.0080, 0.0132] | 0.0105 [0.0085, 0.0143] | 0.0092 [0.0078, 0.0115] | 36.5 | 0.607 | 204.0 |
| 0.25 | P-oracle | 0.250 | 0.0139 [0.0111, 0.0184] | 0.0127 [0.0104, 0.0168] | 0.0119 [0.0098, 0.0156] | 0.0112 [0.0091, 0.0153] | 0.0117 [0.0094, 0.0162] | 0.0102 [0.0086, 0.0130] | 38.2 | 0.627 | 147.8 |
| 0.25 | admit-all | 1.000 | 0.0159 [0.0121, 0.0239] | 0.0122 [0.0100, 0.0157] | 0.0105 [0.0088, 0.0136] | 0.0098 [0.0083, 0.0126] | 0.0106 [0.0086, 0.0139] | 0.0094 [0.0080, 0.0117] | 174.9 | 0.607 | 182.2 |
| 0.50 | admit-none | 0.000 | 0.0126 [0.0102, 0.0165] | 0.0115 [0.0094, 0.0151] | 0.0104 [0.0086, 0.0137] | 0.0098 [0.0081, 0.0132] | 0.0102 [0.0084, 0.0137] | 0.0092 [0.0078, 0.0115] | 0.0 | 0.560 | 225.1 |
| 0.50 | P-random | 0.507 | 0.0134 [0.0107, 0.0180] | 0.0121 [0.0099, 0.0158] | 0.0108 [0.0089, 0.0141] | 0.0102 [0.0084, 0.0134] | 0.0105 [0.0086, 0.0138] | 0.0094 [0.0079, 0.0117] | 77.7 | 0.617 | 202.8 |
| 0.50 | P-score | 0.583 | 0.0141 [0.0112, 0.0190] | 0.0120 [0.0099, 0.0157] | 0.0104 [0.0088, 0.0132] | 0.0102 [0.0085, 0.0134] | 0.0103 [0.0085, 0.0132] | 0.0096 [0.0081, 0.0121] | 76.0 | 0.533 | 165.3 |
| 0.50 | P-trajectory | 0.542 | 0.0132 [0.0105, 0.0183] | 0.0112 [0.0092, 0.0144] | 0.0098 [0.0082, 0.0126] | 0.0096 [0.0080, 0.0131] | 0.0108 [0.0088, 0.0149] | 0.0088 [0.0075, 0.0109] | 84.7 | 0.587 | 198.4 |
| 0.50 | P-trajectory-work | 0.496 | 0.0139 [0.0108, 0.0207] | 0.0115 [0.0094, 0.0152] | 0.0104 [0.0085, 0.0142] | 0.0100 [0.0082, 0.0139] | 0.0110 [0.0089, 0.0154] | 0.0091 [0.0077, 0.0113] | 78.5 | 0.633 | 203.3 |
| 0.50 | P-oracle | 0.497 | 0.0153 [0.0120, 0.0208] | 0.0131 [0.0106, 0.0173] | 0.0116 [0.0095, 0.0152] | 0.0112 [0.0090, 0.0154] | 0.0122 [0.0097, 0.0170] | 0.0102 [0.0085, 0.0130] | 76.0 | 0.647 | 144.2 |
| 0.50 | admit-all | 1.000 | 0.0159 [0.0121, 0.0239] | 0.0122 [0.0100, 0.0157] | 0.0105 [0.0088, 0.0136] | 0.0098 [0.0083, 0.0126] | 0.0106 [0.0086, 0.0139] | 0.0094 [0.0080, 0.0117] | 174.9 | 0.607 | 182.2 |
| 0.75 | admit-none | 0.000 | 0.0126 [0.0102, 0.0165] | 0.0115 [0.0094, 0.0151] | 0.0104 [0.0086, 0.0137] | 0.0098 [0.0081, 0.0132] | 0.0102 [0.0084, 0.0137] | 0.0092 [0.0078, 0.0115] | 0.0 | 0.560 | 225.1 |
| 0.75 | P-random | 0.753 | 0.0143 [0.0112, 0.0199] | 0.0124 [0.0101, 0.0161] | 0.0109 [0.0090, 0.0143] | 0.0102 [0.0084, 0.0136] | 0.0108 [0.0087, 0.0144] | 0.0095 [0.0080, 0.0118] | 121.2 | 0.629 | 192.5 |
| 0.75 | P-score | 0.771 | 0.0155 [0.0119, 0.0234] | 0.0118 [0.0098, 0.0153] | 0.0100 [0.0084, 0.0126] | 0.0099 [0.0082, 0.0131] | 0.0100 [0.0082, 0.0129] | 0.0094 [0.0080, 0.0120] | 115.2 | 0.573 | 164.6 |
| 0.75 | P-trajectory | 0.786 | 0.0158 [0.0120, 0.0242] | 0.0125 [0.0100, 0.0165] | 0.0108 [0.0088, 0.0145] | 0.0100 [0.0083, 0.0138] | 0.0109 [0.0088, 0.0150] | 0.0092 [0.0079, 0.0112] | 138.6 | 0.607 | 184.3 |
| 0.75 | P-trajectory-work | 0.774 | 0.0158 [0.0120, 0.0242] | 0.0125 [0.0101, 0.0165] | 0.0112 [0.0090, 0.0155] | 0.0104 [0.0085, 0.0145] | 0.0111 [0.0090, 0.0153] | 0.0093 [0.0079, 0.0116] | 137.1 | 0.613 | 188.6 |
| 0.75 | P-oracle | 0.746 | 0.0158 [0.0123, 0.0215] | 0.0129 [0.0105, 0.0169] | 0.0115 [0.0095, 0.0151] | 0.0111 [0.0090, 0.0154] | 0.0118 [0.0095, 0.0163] | 0.0096 [0.0081, 0.0120] | 117.7 | 0.687 | 139.3 |
| 0.75 | admit-all | 1.000 | 0.0159 [0.0121, 0.0239] | 0.0122 [0.0100, 0.0157] | 0.0105 [0.0088, 0.0136] | 0.0098 [0.0083, 0.0126] | 0.0106 [0.0086, 0.0139] | 0.0094 [0.0080, 0.0117] | 174.9 | 0.607 | 182.2 |

**Resolver 32B N = 3, primary configuration (alarm FPR 5 %, trigger 20 %, (ii) measured @25 % load).**

| budget | policy | realized admitted | AP h = 0 s | AP h = 0.25 s | AP h = 0.5 s | AP h = 0.75 s | AP h = 1 s | AP h = 1.5 s | GPU-s / clip-h | positives alarmed | false alarms / clip-h |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0.25 | admit-none | 0.000 | 0.0126 [0.0102, 0.0165] | 0.0115 [0.0094, 0.0151] | 0.0104 [0.0086, 0.0137] | 0.0098 [0.0081, 0.0132] | 0.0102 [0.0084, 0.0137] | 0.0092 [0.0078, 0.0115] | 0.0 | 0.560 | 225.1 |
| 0.25 | P-random | 0.255 | 0.0128 [0.0104, 0.0166] | 0.0117 [0.0096, 0.0152] | 0.0105 [0.0088, 0.0134] | 0.0099 [0.0083, 0.0131] | 0.0103 [0.0085, 0.0138] | 0.0093 [0.0079, 0.0115] | 126.2 | 0.602 | 186.1 |
| 0.25 | P-score | 0.388 | 0.0130 [0.0106, 0.0170] | 0.0118 [0.0098, 0.0154] | 0.0105 [0.0088, 0.0132] | 0.0097 [0.0082, 0.0120] | 0.0103 [0.0085, 0.0138] | 0.0091 [0.0078, 0.0111] | 161.8 | 0.527 | 117.5 |
| 0.25 | P-trajectory | 0.244 | 0.0126 [0.0102, 0.0166] | 0.0115 [0.0094, 0.0150] | 0.0104 [0.0087, 0.0133] | 0.0096 [0.0080, 0.0119] | 0.0105 [0.0085, 0.0145] | 0.0094 [0.0080, 0.0118] | 109.4 | 0.540 | 144.9 |
| 0.25 | P-trajectory-work | 0.212 | 0.0126 [0.0102, 0.0166] | 0.0114 [0.0093, 0.0151] | 0.0103 [0.0086, 0.0133] | 0.0098 [0.0081, 0.0129] | 0.0103 [0.0084, 0.0140] | 0.0092 [0.0078, 0.0114] | 98.9 | 0.573 | 181.5 |
| 0.25 | P-oracle | 0.260 | 0.0138 [0.0112, 0.0181] | 0.0125 [0.0102, 0.0163] | 0.0115 [0.0094, 0.0151] | 0.0110 [0.0089, 0.0152] | 0.0116 [0.0093, 0.0160] | 0.0102 [0.0085, 0.0130] | 126.9 | 0.633 | 95.7 |
| 0.25 | admit-all | 1.000 | 0.0136 [0.0110, 0.0183] | 0.0118 [0.0098, 0.0147] | 0.0104 [0.0088, 0.0128] | 0.0095 [0.0080, 0.0124] | 0.0104 [0.0087, 0.0137] | 0.0097 [0.0083, 0.0119] | 515.8 | 0.673 | 121.7 |
| 0.50 | admit-none | 0.000 | 0.0126 [0.0102, 0.0165] | 0.0115 [0.0094, 0.0151] | 0.0104 [0.0086, 0.0137] | 0.0098 [0.0081, 0.0132] | 0.0102 [0.0084, 0.0137] | 0.0092 [0.0078, 0.0115] | 0.0 | 0.560 | 225.1 |
| 0.50 | P-random | 0.508 | 0.0129 [0.0105, 0.0169] | 0.0117 [0.0096, 0.0150] | 0.0105 [0.0088, 0.0132] | 0.0098 [0.0083, 0.0128] | 0.0103 [0.0085, 0.0137] | 0.0095 [0.0081, 0.0116] | 247.6 | 0.637 | 160.1 |
| 0.50 | P-score | 0.558 | 0.0122 [0.0101, 0.0155] | 0.0114 [0.0095, 0.0146] | 0.0106 [0.0089, 0.0131] | 0.0104 [0.0086, 0.0136] | 0.0104 [0.0086, 0.0136] | 0.0092 [0.0078, 0.0111] | 242.7 | 0.567 | 111.9 |
| 0.50 | P-trajectory | 0.493 | 0.0130 [0.0106, 0.0168] | 0.0118 [0.0096, 0.0150] | 0.0104 [0.0088, 0.0129] | 0.0098 [0.0083, 0.0121] | 0.0106 [0.0088, 0.0141] | 0.0094 [0.0080, 0.0116] | 230.0 | 0.620 | 113.3 |
| 0.50 | P-trajectory-work | 0.448 | 0.0127 [0.0103, 0.0166] | 0.0118 [0.0096, 0.0156] | 0.0105 [0.0088, 0.0133] | 0.0097 [0.0081, 0.0119] | 0.0104 [0.0085, 0.0139] | 0.0094 [0.0080, 0.0117] | 210.7 | 0.633 | 137.2 |
| 0.50 | P-oracle | 0.476 | 0.0139 [0.0112, 0.0182] | 0.0131 [0.0106, 0.0172] | 0.0118 [0.0096, 0.0154] | 0.0113 [0.0092, 0.0158] | 0.0116 [0.0093, 0.0161] | 0.0103 [0.0086, 0.0130] | 230.2 | 0.640 | 83.7 |
| 0.50 | admit-all | 1.000 | 0.0136 [0.0110, 0.0183] | 0.0118 [0.0098, 0.0147] | 0.0104 [0.0088, 0.0128] | 0.0095 [0.0080, 0.0124] | 0.0104 [0.0087, 0.0137] | 0.0097 [0.0083, 0.0119] | 515.8 | 0.673 | 121.7 |
| 0.75 | admit-none | 0.000 | 0.0126 [0.0102, 0.0165] | 0.0115 [0.0094, 0.0151] | 0.0104 [0.0086, 0.0137] | 0.0098 [0.0081, 0.0132] | 0.0102 [0.0084, 0.0137] | 0.0092 [0.0078, 0.0115] | 0.0 | 0.560 | 225.1 |
| 0.75 | P-random | 0.754 | 0.0131 [0.0107, 0.0171] | 0.0118 [0.0097, 0.0149] | 0.0105 [0.0088, 0.0129] | 0.0097 [0.0081, 0.0124] | 0.0103 [0.0086, 0.0136] | 0.0095 [0.0081, 0.0117] | 373.5 | 0.672 | 139.5 |
| 0.75 | P-score | 0.763 | 0.0133 [0.0109, 0.0168] | 0.0120 [0.0098, 0.0151] | 0.0107 [0.0090, 0.0132] | 0.0103 [0.0085, 0.0134] | 0.0109 [0.0090, 0.0143] | 0.0097 [0.0083, 0.0120] | 358.4 | 0.653 | 109.1 |
| 0.75 | P-trajectory | 0.757 | 0.0129 [0.0106, 0.0163] | 0.0116 [0.0096, 0.0145] | 0.0102 [0.0086, 0.0124] | 0.0093 [0.0079, 0.0113] | 0.0104 [0.0086, 0.0135] | 0.0094 [0.0081, 0.0116] | 372.9 | 0.640 | 112.6 |
| 0.75 | P-trajectory-work | 0.732 | 0.0131 [0.0106, 0.0179] | 0.0118 [0.0097, 0.0150] | 0.0104 [0.0089, 0.0129] | 0.0096 [0.0081, 0.0118] | 0.0106 [0.0088, 0.0140] | 0.0095 [0.0081, 0.0117] | 356.2 | 0.653 | 118.9 |
| 0.75 | P-oracle | 0.736 | 0.0140 [0.0113, 0.0182] | 0.0129 [0.0104, 0.0168] | 0.0113 [0.0093, 0.0149] | 0.0106 [0.0085, 0.0146] | 0.0112 [0.0090, 0.0154] | 0.0107 [0.0089, 0.0135] | 361.3 | 0.707 | 77.4 |
| 0.75 | admit-all | 1.000 | 0.0136 [0.0110, 0.0183] | 0.0118 [0.0098, 0.0147] | 0.0104 [0.0088, 0.0128] | 0.0095 [0.0080, 0.0124] | 0.0104 [0.0087, 0.0137] | 0.0097 [0.0083, 0.0119] | 515.8 | 0.673 | 121.7 |

## 12. Study 2 — decision rule (StudyE12's, unchanged, at h = 0.25 s and h = 0.5 s)

> **Pre-registered (StudyE12, unchanged; both horizons pre-registered here):** the trajectory signal is useful if P-trajectory or P-trajectory-work beats P-score on AP at the stated horizon with a paired clip-bootstrap CI excluding 0 at 2 of 3 budgets (primary configuration, 32B N = 1 or N = 3), **without increasing cloud GPU-s by more than 10 %**. If not, the device score alone is the admission signal and this report says so plainly. If P-score does not beat P-random, admission ranking has no signal on this workload.

**Primary clause — P-trajectory and P-trajectory-work against P-score** (paired difference, positive favours the trajectory policy; `*` = CI excludes 0 on the favourable side):

| horizon | resolver | policy | B = 0.25 | B = 0.50 | B = 0.75 | GPU-s ratio vs P-score (max) | budgets won | rule |
|---|---|---|---|---|---|---|---|---|
| 0.25 s | 32B N = 1 | P-trajectory | +0.0002 [-0.0009, +0.0014] | -0.0008 [-0.0027, +0.0007] | +0.0007 [-0.0010, +0.0028] | 1.203 | 0 / 3 | not met |
| 0.25 s | 32B N = 1 | P-trajectory-work | -0.0002 [-0.0012, +0.0011] | -0.0005 [-0.0023, +0.0012] | +0.0007 [-0.0010, +0.0029] | 1.190 | 0 / 3 | not met |
| 0.25 s | 32B N = 3 | P-trajectory | -0.0003 [-0.0012, +0.0006] | +0.0003 [-0.0003, +0.0012] | -0.0004 [-0.0013, +0.0003] | 1.040 | 0 / 3 | not met |
| 0.25 s | 32B N = 3 | P-trajectory-work | -0.0004 [-0.0013, +0.0007] | +0.0004 [-0.0006, +0.0020] | -0.0002 [-0.0012, +0.0007] | 0.994 | 0 / 3 | not met |
| 0.5 s | 32B N = 1 | P-trajectory | -0.0006 [-0.0017, +0.0002] | -0.0006 [-0.0018, +0.0005] | +0.0009 [-0.0004, +0.0030] | 1.203 | 0 / 3 | not met |
| 0.5 s | 32B N = 1 | P-trajectory-work | -0.0009 [-0.0020, -0.0001] | +0.0000 [-0.0012, +0.0020] | +0.0013 [+0.0000, +0.0038] | 1.190 | 0 / 3 | not met |
| 0.5 s | 32B N = 3 | P-trajectory | -0.0000 [-0.0007, +0.0009] | -0.0002 [-0.0008, +0.0004] | -0.0006 [-0.0013, +0.0000] | 1.040 | 0 / 3 | not met |
| 0.5 s | 32B N = 3 | P-trajectory-work | -0.0001 [-0.0008, +0.0009] | -0.0001 [-0.0009, +0.0011] | -0.0003 [-0.0010, +0.0004] | 0.994 | 0 / 3 | not met |

- **h = 0.25 s: the rule is NOT MET** (best 0 of 3 budgets).
- **h = 0.5 s: the rule is NOT MET** (best 0 of 3 budgets).

**Second clause — P-score against P-random** (does admission ranking have any signal at all?):

| resolver | horizon | B = 0.25 | B = 0.50 | B = 0.75 | favourable |
|---|---|---|---|---|---|
| 32B N = 1 | 0 s | +0.0003 [-0.0007, +0.0011] | +0.0007 [-0.0006, +0.0024] | +0.0012 [-0.0003, +0.0046] | 0 / 3 |
| 32B N = 1 | 0.25 s | +0.0003 [-0.0005, +0.0011] | -0.0000 [-0.0011, +0.0008] | -0.0005 [-0.0018, +0.0004] | 0 / 3 |
| 32B N = 1 | 0.5 s | +0.0007 [+0.0002, +0.0017]* | -0.0004 [-0.0015, +0.0003] | -0.0010 [-0.0022, -0.0001]† | 1 / 3 |
| 32B N = 3 | 0 s | +0.0002 [-0.0005, +0.0011] | -0.0007 [-0.0020, +0.0001] | +0.0002 [-0.0011, +0.0011] | 0 / 3 |
| 32B N = 3 | 0.25 s | +0.0001 [-0.0008, +0.0009] | -0.0003 [-0.0011, +0.0005] | +0.0002 [-0.0004, +0.0009] | 0 / 3 |
| 32B N = 3 | 0.5 s | -0.0001 [-0.0008, +0.0005] | +0.0001 [-0.0007, +0.0007] | +0.0003 [-0.0003, +0.0008] | 0 / 3 |

P-score separates from P-random with a CI excluding 0 **in the favourable direction in 1 of 18** (resolver x horizon x budget) cells, and **in the unfavourable direction in 1**. The point estimates change sign across budgets within the same resolver and horizon, so there is no consistent ordering signal: at the 5 % level one would expect about 0.9 cells to separate by chance alone in each direction. **Per the pre-registered wording, admission ranking has no signal on this workload** as measured by AP.

**Predictor diagnostics** (out-of-sample separation of the *training target*, never a conclusion):

| cell | triggers | fold | training triggers | benefit > 0 rate | AUROC (benefit > 0) | work model train R^2 |
|---|---|---|---|---|---|---|
| 32BI_N1 / measured@25 / far5 / trig20 | 1,946 | fold0 | 919 | 0.127 | 0.764 | 0.178 |
| 32BI_N1 / measured@25 / far5 / trig20 | 1,946 | fold1 | 1,027 | 0.096 | 0.648 | 0.187 |
| 32BI_N3 / measured@25 / far5 / trig20 | 1,580 | fold0 | 755 | 0.139 | 0.665 | 0.156 |
| 32BI_N3 / measured@25 / far5 / trig20 | 1,580 | fold1 | 825 | 0.112 | 0.713 | 0.176 |

**What admission buys that AP does not see** — cloud work and alarm behaviour at B = 0.50, primary configuration:

| resolver | policy | GPU-s / clip-h | % of admit-all | positives alarmed | false alarms / clip-h |
|---|---|---|---|---|---|
| 32B N = 1 | admit-none | 0.0 | 0% | 0.560 | 225.1 |
| 32B N = 1 | P-random | 77.7 | 44% | 0.617 | 202.8 |
| 32B N = 1 | P-score | 76.0 | 43% | 0.533 | 165.3 |
| 32B N = 1 | P-trajectory | 84.7 | 48% | 0.587 | 198.4 |
| 32B N = 1 | P-trajectory-work | 78.5 | 45% | 0.633 | 203.3 |
| 32B N = 1 | P-oracle | 76.0 | 43% | 0.647 | 144.2 |
| 32B N = 1 | admit-all | 174.9 | 100% | 0.607 | 182.2 |
| 32B N = 3 | admit-none | 0.0 | 0% | 0.560 | 225.1 |
| 32B N = 3 | P-random | 247.6 | 48% | 0.637 | 160.1 |
| 32B N = 3 | P-score | 242.7 | 47% | 0.567 | 111.9 |
| 32B N = 3 | P-trajectory | 230.0 | 45% | 0.620 | 113.3 |
| 32B N = 3 | P-trajectory-work | 210.7 | 41% | 0.633 | 137.2 |
| 32B N = 3 | P-oracle | 230.2 | 45% | 0.640 | 83.7 |
| 32B N = 3 | admit-all | 515.8 | 100% | 0.673 | 121.7 |

## 13. Controls

| control | what it tests | result |
|---|---|---|
| **(b) zero latency ⇒ delivered = compute** | under setting (i) the sample-and-hold stream must equal the raw score array | **PASS** — 4 arms x 300 clips |
| **(StudyE9's resolver swap)** | escalation-32B's code path with 4B N = 1 scores, thresholds and latency must equal escalation-4B exactly | **PASS** — 180 cells, 0 mismatches |
| **(Step 4) disable the delivery link** | with `L_cloud` = 10 s (= L_max) no resolver answer can arrive before the episode caps, so escalation must collapse to device-only | **PASS** — identical at all 6 horizons |
| **(StudyE9's within-clip shuffle)** | resolver scores permuted across grid points within each clip; AP must fall toward chance | **PASS at zero latency, UNINFORMATIVE under measured latency** — see below |
| **(c1) budget 1.0 = admit-all** | at B = 1.0 every admission policy must equal admit-all exactly | **PASS** — 168 cells, 0 mismatches |
| **(c2) feature shuffle within fold** | each trigger's features replaced by a draw from the fold's pool; P-trajectory must fall to P-random's level | see table below |
| **(a) end-to-end reproduction** | reproduce StudyE9 and StudyE12 exactly on integer-t rows with `d = ceil(latency)` | **PASS** (§2) |

**The within-clip shuffle, in full** — and an honest classification of it:

| cell | AP h = 0, real | AP h = 0, shuffled | multiple of chance, shuffled | informative? |
|---|---|---|---|---|
| 32BI_N1 / measured@25 | 0.0159 | 0.0122 | 1.7x | **NO — nothing to destroy** |
| 32BI_N1 / zero | 0.0489 | 0.0166 | 2.3x | **yes — AP collapses toward chance** |
| 32BI_N3 / measured@25 | 0.0136 | 0.0135 | 1.9x | **NO — nothing to destroy** |
| 32BI_N3 / zero | 0.0870 | 0.0107 | 1.5x | **yes — AP collapses toward chance** |

**Under zero latency the control does its job** (32B N = 3: 0.0870 → 0.0107, 1.5x chance), confirming that escalation's AP comes from the *ordering* of the resolver's scores within a clip and not from a level effect. **Under measured latency it is PASS-as-written but uninformative** (0.0136 → 0.0135): the unshuffled escalation arm is already within 1.9x of chance, so permuting the resolver's scores has almost nothing left to destroy. That is not a defect of the control — it is the same fact as finding 7 in §15, seen from the other side: once the device's stale score gates the episodes, the application barely uses the resolver's ordering at all. Classified per CLAUDE.md Rule 2 the zero-latency cells are informative and the measured cells are not, and no conclusion in this report rests on the measured cells of this control.

**Control (c2) in detail** (primary configuration, AP at the rule horizons):

| cell | budget | realized admitted | P-trajectory h = 0.25 | shuffled h = 0.25 | P-random h = 0.25 | P-trajectory h = 0.5 | shuffled h = 0.5 | P-random h = 0.5 |
|---|---|---|---|---|---|---|---|---|
| 32BI_N1 / measured@25 / far5 / trig20 | B25 | 0.308 | 0.0122 | 0.0120 | 0.0118 | 0.0107 | 0.0107 | 0.0106 |
| 32BI_N1 / measured@25 / far5 / trig20 | B50 | 0.504 | 0.0112 | 0.0119 | 0.0121 | 0.0098 | 0.0108 | 0.0108 |
| 32BI_N1 / measured@25 / far5 / trig20 | B75 | 0.741 | 0.0125 | 0.0124 | 0.0124 | 0.0108 | 0.0109 | 0.0109 |
| 32BI_N3 / measured@25 / far5 / trig20 | B25 | 0.219 | 0.0115 | 0.0117 | 0.0117 | 0.0104 | 0.0104 | 0.0105 |
| 32BI_N3 / measured@25 / far5 / trig20 | B50 | 0.475 | 0.0118 | 0.0120 | 0.0117 | 0.0104 | 0.0112 | 0.0105 |
| 32BI_N3 / measured@25 / far5 / trig20 | B75 | 0.743 | 0.0116 | 0.0116 | 0.0118 | 0.0102 | 0.0101 | 0.0105 |

**lambda sensitivity** (training target only; the evaluation metric is unchanged). AP at the rule horizons for the two trajectory policies:

Cell `32BI_N1 / measured@25 / far5 / trig20`:

| lambda multiplier | budget | policy | AP h = 0.25 s | AP h = 0.5 s | realized admitted | GPU-s / clip-h |
|---|---|---|---|---|---|---|
| 0.5 | B25 | P-trajectory | 0.0122 | 0.0107 | 0.265 | 36.5 |
| 0.5 | B25 | P-trajectory-work | 0.0119 | 0.0104 | 0.257 | 36.5 |
| 0.5 | B50 | P-trajectory | 0.0112 | 0.0098 | 0.542 | 84.7 |
| 0.5 | B50 | P-trajectory-work | 0.0115 | 0.0104 | 0.496 | 78.5 |
| 0.5 | B75 | P-trajectory | 0.0125 | 0.0108 | 0.786 | 138.6 |
| 0.5 | B75 | P-trajectory-work | 0.0125 | 0.0112 | 0.774 | 137.1 |
| 1 | B25 | P-trajectory | 0.0122 | 0.0107 | 0.265 | 36.5 |
| 1 | B25 | P-trajectory-work | 0.0119 | 0.0104 | 0.257 | 36.5 |
| 1 | B50 | P-trajectory | 0.0112 | 0.0098 | 0.542 | 84.7 |
| 1 | B50 | P-trajectory-work | 0.0115 | 0.0104 | 0.496 | 78.5 |
| 1 | B75 | P-trajectory | 0.0125 | 0.0108 | 0.786 | 138.6 |
| 1 | B75 | P-trajectory-work | 0.0125 | 0.0112 | 0.774 | 137.1 |
| 2 | B25 | P-trajectory | 0.0122 | 0.0107 | 0.265 | 36.5 |
| 2 | B25 | P-trajectory-work | 0.0119 | 0.0104 | 0.257 | 36.5 |
| 2 | B50 | P-trajectory | 0.0112 | 0.0098 | 0.542 | 84.7 |
| 2 | B50 | P-trajectory-work | 0.0115 | 0.0104 | 0.496 | 78.5 |
| 2 | B75 | P-trajectory | 0.0125 | 0.0108 | 0.786 | 138.6 |
| 2 | B75 | P-trajectory-work | 0.0125 | 0.0112 | 0.774 | 137.1 |
| 3.93899 | B25 | P-trajectory | 0.0122 | 0.0107 | 0.265 | 36.5 |
| 3.93899 | B25 | P-trajectory-work | 0.0119 | 0.0104 | 0.257 | 36.5 |
| 3.93899 | B50 | P-trajectory | 0.0112 | 0.0098 | 0.542 | 84.7 |
| 3.93899 | B50 | P-trajectory-work | 0.0115 | 0.0104 | 0.496 | 78.5 |
| 3.93899 | B75 | P-trajectory | 0.0125 | 0.0108 | 0.786 | 138.6 |
| 3.93899 | B75 | P-trajectory-work | 0.0125 | 0.0112 | 0.774 | 137.1 |

## 14. Results consistency check (CLAUDE.md, 6 checks)

**1. Cross-check against committed measurements.**

| quantity | this run | prior run | source of prior | ratio | agree |
|---|---|---|---|---|---|
| StudyE9: every baseline and primary-config escalation cell (AP, CIs, episode counts, outcomes, invocations, alarms, false dismissals) | reproduced | committed | `results/dashcam/study_e9/e9_results.json` | worst abs(diff) 0.000000000000 | **yes** |
| StudyE12: 672 admission cells (AP, CIs, invocations, admitted, episodes, alarms, GPU-s, realized fraction) | reproduced | committed | `results/dashcam/study_e12/e12_results.json` | worst abs(diff) 0.000000000000 | **yes** |
| dense zero-latency AP, 4B N1 (device-only at zero latency scores every grid point, so it must equal StudyD14b's zero-latency 4B N1 arm) | 0.0284 / 0.0364 / 0.0189 / 0.0147 / 0.0131 / 0.0105 | 0.028 / 0.036 / 0.019 / 0.015 / 0.013 / 0.011 | `reports/study_d14b_dense.md` §2 (3 d.p.) | 5 / 6 equal at the published 3 d.p.; worst abs(diff) 0.0005 (4.9%) | **yes** |
| dense zero-latency AP, 32B N1 (always-cloud at zero latency and cadence 0.25 s scores every grid point) | 0.0530 / 0.0613 / 0.0415 / 0.0201 / 0.0166 / 0.0137 | 0.053 / 0.061 / 0.042 / 0.020 / 0.017 / 0.014 | `reports/study_d14b_dense.md` §2 (3 d.p.) | 5 / 6 equal at the published 3 d.p.; worst abs(diff) 0.0005 (2.4%) | **yes** |
| dense zero-latency AP, 32B N3 (always-cloud at zero latency and cadence 0.25 s scores every grid point) | 0.0914 / 0.0530 / 0.0437 / 0.0217 / 0.0161 / 0.0129 | 0.091 / 0.053 / 0.044 / 0.022 / 0.016 / 0.013 | `reports/study_d14b_dense.md` §2 (3 d.p.) | 6 / 6 equal at the published 3 d.p.; worst abs(diff) 0.0004 (1.4%) | **yes** |
| device latency | 0.567 s | 0.567 s | StudyD8 arm A, sustained 1 Hz N = 1, total p50 | 1.00 | yes |
| cloud latency 32B N = 1 @25 % | 0.3950 s | identical decomposition | StudyD4 PNG bytes + 13.6 Mbit/s + StudyD7b TTFT, via `study_e9_episodes.py` | 1.00 | yes |
| any two latency settings with the same hold shift must give bit-identical AP | 3 such (arm, setting-pair) combinations | — | internal invariant of the delivery model | 54 / 54 bit-equal | **yes** |

**Nothing disagrees by anything approaching the 2x investigation threshold**, and the two reproductions — which are the point of control (a) — are bit-exact. One residual is reported rather than smoothed over: against StudyD14b's dense zero-latency table, 16 of 18 values are equal at the three decimal places StudyD14b publishes, and the remaining 2 differ by at most 0.0005 AP (4.9% relative, against a 2x = 100 % threshold). **The cause cannot be pinned down from the committed artefacts**: StudyD14b published its dense AP only to 3 d.p. in its report and committed no AP JSON, so there is no bit-level value to compare against. Three candidate explanations were tested and ruled out — rounding the positive target index on the absolute grid, on the clip-relative grid, and with numpy's rounding instead of Python's all give identical results here, and none changes a single target index. What *is* bit-exact is the stronger overlapping check: on the 1-s subsample this code reproduces StudyE9's committed zero-latency baselines exactly (control (a)), and StudyD14b itself reports that its 1-s subsample does the same. The residual is therefore confined to StudyD14b's dense-grid table and does not touch any number used in this report.

**2. Physical plausibility check.** No latency, throughput or size is *measured* here; all are read from committed measurements and only recombined.

| derived rate | value | committed reference | plausible |
|---|---|---|---|
| device score rate | 1.33 Hz (0.75 s cadence) | StudyD8 arm A measured 1 Hz at 0.567 s total p50; saturated duty is an extrapolation, flagged in §0 | yes, with the §0 flag |
| peak cloud call rate (cadence 0.25 s, always-cloud) | 14,400 calls / clip-hour = 4 calls/s per clip | a per-clip rate, not a server rate; capacity is NOT modelled here (StudyD7 / D7b TTFT is an open-loop p50 at 25 % and 75 % of peak) | yes, with the scope note in §16 |
| GPU-s per call, 32B N = 1 | 0.06750 s (378 prompt tokens / 5,600 tok/s) | StudyD7 saturated 32B prefill; StudyD3 / D14 prompt tokens | yes |
| GPU-s per call, 32B N = 3 | 0.18964 s | same | yes |

Nothing here implies a rate faster than a committed curve: every rate *is* a committed curve, reused.

**3. Distribution sanity.** Spreads are reported wherever a central value is: every AP carries a 2,000-resample clip-bootstrap CI; alarm timing carries p25 / p50 / p75; episode length and invocations per episode are means over hundreds of episodes; the horizon shift carries its own CI. Two specific checks:

- **Not constant where it should vary:** always-cloud 32B N = 1 at h = 0 across the three cadences is 0.0420 / 0.0384 / 0.0247, and across the five latency settings (cadence 0.5 s) 0.0451 / 0.0384 / 0.0196 / 0.0434 / 0.0384.
- **Constant exactly where the model says it must be:** device-only is independent of the resolver cadence and of the cloud setting, so its AP is identical under (ii) @25 %, @75 %, (iii) @25 % and @75 % — 0.0126 / 0.0126 / 0.0126 / 0.0126. That is the delivery arithmetic, not a short circuit: the device's latency is the same in all four.

**4. Definition audit.**

| object | definition in this run | prior committed definition | match |
|---|---|---|---|
| decision grid | t = 3.0, 3.25, ... , step 0.25 s; 42,014 points per arm | StudyD14b, identical | yes |
| `d` / delay | **CHANGED BY DESIGN:** hold shift = ceil(L / 0.25) grid steps, L unrounded | StudyE9 / E12: `d = ceil(L)` whole seconds | **deliberately different — this is the experiment**; control (a) runs the old definition and reproduces both studies exactly |
| AP at horizon h | positives = each positive clip's application-visible score at the grid point nearest `time_of_event − h`; negatives = every grid point of every negative clip | StudyE5 Part G / StudyE9 / StudyD14b, same rule on a finer grid | yes |
| chance / base rate | 0.00728 (150 / (150 + 20,467)) | StudyE9: 0.0281 (150 / (150 + 5,196)) | **same formula, different grid** — never compared across grids |
| `tau_alarm` / `tau_dismiss` / `tau_trig` | quantiles of each arm's own score distribution over the negative grid points of the training fold; 2-fold cross-fit by clip, stratified, seed 0 | StudyE9, identical procedure | yes |
| episode `L_max` | 10 s of **wall clock** = 40 grid steps | StudyE9: 10 seconds = 10 grid steps | yes, same wall-clock bound |
| dismiss run `k` | 2 consecutive **delivered resolver scores** below `tau_dismiss` (not grid points: a held score repeated between deliveries does not count twice) | StudyE9: 2 consecutive seconds, which at a 1-s cadence is the same thing | yes, and the generalisation is exact at step = 1 s (control (a)) |
| cooldown | 0 s = next grid point | StudyE9: 0 s = next second | yes |
| an invocation | one resolver call **issued** while an episode is open, charged whether or not its answer arrives before the episode closes | StudyE9: one open second | yes at a 1-s cadence; the dense grid separates the two and both are reported (§5) |
| feature windows | the last 12 and 20 grid points = 3 s and 5 s | StudyE12: 3 and 5 seconds | yes, same wall-clock windows |
| lambda | 0.0073289 = positives per negative grid point on **this** grid | StudyE12: 0.0288684 on the 1-s grid | **same definition, recomputed on this grid**; StudyE12's value is 3.939x and is covered by the last sensitivity multiplier |

One name is used with two definitions across experiments, and it is the one this study exists to change: **`d`**. StudyE9's `d` is a whole-second delay; this study's is a grid-quantised sample-and-hold shift of an unrounded latency. Control (a) runs StudyE9's definition inside this code and reproduces its numbers exactly, so the two are reconciled rather than merely renamed.

**5. Claim linkage.**

| headline | claim it bears on | supports / weakens / silent |
|---|---|---|
| On a 0.25-s grid under measured latency the cloud's **delivered** 32B N = 1 score is better than the device's at every horizon reported, where StudyE9's 1-s grid showed them within 0.0005 at h = 0.5 s | FORMULATION §Constraints 2 (serving feasibility within the latency SLO) and §Decisions (the placement decision `p_i`) | **supports** that placement is decidable at this scale, and corrects an artefact of the earlier grid |
| 32B N = 3 loses its capability advantage to its own upload: best at zero latency, near the device once delivered | FORMULATION §Objective (cost-aware placement) and the physical component of Context Inertia | **supports** — the representation that wins offline is not the one that wins delivered |
| Resolver cadence buys AP sub-linearly and is charged per call | §Objective (cloud work as an explanatory cost) | **supports** |
| StudyE9's decision rule 2 is met in many more cells here, because its absolute 0.01 AP tolerance is loose relative to this grid's chance rate | none — this is a **scale artefact of the rule**, which is why the scale-matched column is reported beside it | **silent**; reported, not claimed |
| Admission ranking from the device's own trajectory | FORMULATION §Decisions (which requests to place remotely under capacity) | see §12 verdict |

Nothing measured here is scoped out by FORMULATION.md. No KV cache moves between tiers; no cross-architecture transfer is modelled.

**6. Proxy validity.**

| proxy | what it actually measures | valid for the claim? |
|---|---|---|
| StudyD14b's batched H100 scores stand for what a 32B server would return in deployment | model output on the same frames, same prompt, same decoding, prefix caching OFF; **no latency was measured in that run** | yes for *what* the cloud would say; latency comes separately from StudyD7 / D7b, and the two are never conflated |
| the 0.75 s device cadence stands for a saturated Orin | StudyD8 measured a *scheduled* 1 Hz arm (0.567 s total p50, no throttling) and a back-to-back N = 9 arm | **partly** — the duty is extrapolated, flagged in §0, and the cadence-1.0 s rows are the conservative reading |
| StudyD7 / D7b open-loop TTFT at 25 % and 75 % of peak stands for server queueing | TTFT from scheduled arrival at two fixed load points | yes for a load point; **no capacity limit is modelled** here, and §16 says so |
| the per-episode utility stands for what admission should optimise | a training target only | yes, and it is **never** an evaluation metric: evaluation is AP throughout |
| setting (iii) stands for JPEG operation | transport time only; **no score was recomputed on JPEG frames** | **no** — reported as a labelled sensitivity, never as a result (§9) |

## 15. What this shows

1. **The delay difference between the tiers is real and the 1-s grid hid it.** Under (ii) measured @25 % load the cloud's 32B N = 1 answer is readable 0.25 s *before* the device's own, and the application-visible AP follows: **0.0384 against the device's 0.0126 at h = 0** (3.0x, 5.3x chance against 1.7x), and the cloud is ahead at every horizon reported. On StudyE9's 1-s grid the same two arms were within 0.0005 of each other at h = 0.5 s, because both delays rounded to 1 s.
2. **Delay costs about as much as capability buys.** Zero latency to measured latency at h = 0: device 0.0284 → 0.0126 (-56%); cloud 32B N = 1 0.0451 → 0.0384 (-15%). The device loses a larger fraction, because its 0.75 s saturated cadence makes its held score older than the cloud's.
3. **More frames is the wrong way to spend capability once the payload must cross the uplink.** At zero latency 32B N = 3 is the best arm in the study (0.0820 at h = 0, against 0.0451 for N = 1). Delivered under (ii) @25 % it falls to 0.0146 — below N = 1's 0.0384 — because its PNG payload is 3x larger and its hold shift is 1.00 s against N = 1's 0.50 s. **The representation that wins offline is not the representation that wins delivered.**
4. **A quarter to two fifths of all resolver calls are answered after their episode has already closed, and are still charged.** At (ii) @25 %, cadence 0.5 s, trigger 20 %: 32B N = 1 25.7% (1,946 calls), 32B N = 3 39.5% (3,135 calls), 4B N = 1 22.0% (1,593 calls). The mechanism is visible in the delivery arithmetic: with a hold shift of 1.00 s against a 0.5 s cadence, 32B N = 3 always has two calls in flight when an episode resolves, so it wastes half again as much as N = 1. **StudyE9's 1-s grid could not represent this at all**, because there a call and its answer occupied the same second. It is a direct argument for matching the resolver cadence to the measured latency rather than to the decision grid.
5. **The gain is not merely 'the cloud is asked more often' (Step 5, alternative 2).** At cadence 1.0 s — StudyE9's own call rate — the cloud still reaches 0.0247 against the device's 0.0126 at h = 0 (2.0x). Raising the cadence from 1.0 s to 0.5 s adds +0.0137 AP for 2.0x the cloud work, and from 0.5 s to 0.25 s adds +0.0036 for another 2x. Cadence is a real but sub-linear knob, charged in full.
6. **Server load moves the whole picture, through the hold shift alone.** At 75 % of peak the 32B N = 1 hold shift rises from 0.50 s to 0.75 s — equal to the device's — and its AP at h = 0 falls from 0.0384 to 0.0196, still above the device but by much less.
7. **On this grid the bottleneck is the trigger, not the resolver.** Device-triggered escalation keeps only a fraction of the gap between device-only and always-cloud while paying most of its cost: at (ii) @25 %, cadence 0.5 s, FPR 5 %, escalation-32B N = 1 captures 3% of the span for 11% of the calls at trigger 5 %, 13% of the span for 21% of the calls at trigger 10 %, 13% of the span for 36% of the calls at trigger 20 %, 18% of the span for 61% of the calls at trigger 40 %. The reason is visible in the same tables: the trigger is a threshold on the **device's delivered** score, which is itself 0.75–1.25 s stale and only 1.7x chance, so the device cannot tell *when* the cloud is worth asking. Swapping the resolver barely matters — escalation-4B at the same trigger reaches 0.0146 against escalation-32B's 0.0172 — which is what one expects when the gate, not the answerer, is binding. This is the Study 1 result that most directly anticipates Study 2.
8. **Decision rule 1 reproduces StudyE9's shape: met at N = 1, not at N = 3.** Under (ii), escalation-32B uses fewer invocations per clip-hour than escalation-4B with a CI excluding 0 in 40 of 72 (cadence x FPR x trigger) cells at N = 1, against 8 of 72 at N = 3 (§6).
9. **Decision rule 2 is met far more widely than in StudyE9, and that is a property of the rule, not of the system.** 154 of 360 cells pass the unchanged absolute 0.01 AP tolerance, which on this grid is 1.37x the entire chance rate; only 40 pass the scale-matched 0.0026. **Read the scale-matched column.** This was pre-registered before the sweep precisely so the looser count could not be presented as a finding.

## 16. What this does not show

1. **It does not show anything about any individual crash.** Earliness is reported as the AP-curve horizon shift (§3.5), per the project's metric rule; it is a property of the AP curves measured on a 0.25-s decision grid. No Yes/No-commitment or within-clip-rise analysis is used, because the models are Yes/No-biased.
2. **No number here may be compared with StudyE9's or StudyE12's.** This grid's chance AP is 0.00728 against 0.0281 — 3.86x. Comparisons are within this grid, or as multiples of chance.
3. **No capacity limit is modelled.** StudyD7 / D7b TTFT enters at two fixed load points, and the cloud is treated as able to accept a call every cadence period per clip with no queueing beyond that TTFT. At cadence 0.25 s that is 14,400 calls per clip-hour, which a real fleet could not serve; StudyD7's capacity ladders and StudyE10b / E10c's interference results are where that question lives. Study 2's budget is a *fraction of triggers*, not a server-side admission controller.
4. **The device's 0.75 s cadence was not measured.** StudyD8 measured 1 Hz scheduled. The saturated duty is an extrapolation (§0); the cadence-1.0 s rows are the conservative reading, and no claim here depends on the 0.75 s figure alone.
5. **Setting (iii) is transport only.** No score was recomputed on JPEG frames, and StudyE10a-full did **not** establish S-EMBER JPEG parity under its ±2 pp rule. Section 9 is a labelled sensitivity.
6. **The 4B resolver is counterfactual.** escalation-4B runs the 4B model as a *cloud* resolver at the same cadence and its own measured cloud latency, which is how StudyE9 defined it and what decision rule 1 needs (a matched call rate, so the contrast is capability). It is not a claim that anyone would deploy a 4B cloud resolver.
7. **No energy is reported.** Running the Orin at a saturated 0.75 s duty would raise board power from StudyD8's 28.2 W at 1 Hz to roughly 31 W; this study charges cloud GPU-seconds only and does not price the device side.

## 17. Verdict

**Control (a) passes exactly, so the dense re-run is a change of delivery model and nothing else.** The engine reproduces StudyE9's committed baselines and all 108 primary-config escalation cells, and StudyE12's 672 admission cells, bit for bit (worst AP abs(diff) 0.000000000000, zero mismatches).

**Study 1 — the link StudyE9 could not test is real.** On a 0.25-s grid with unrounded latency and sample-and-hold delivery, the cloud's 32B N = 1 score reaches the application 0.25 s earlier than the device's own and carries 3.0x its AP at h = 0 (0.0384 against 0.0126; 5.3x chance against 1.7x). The advantage survives at StudyE9's own 1.0 s call rate, so it is delay resolution and not call volume. It does **not** survive a larger payload: 32B N = 3, the strongest arm at zero latency, falls to 0.0146 delivered. Decision rule 1 is **MET at N = 1 and not at N = 3**, as in StudyE9. Decision rule 2 is met in 154 of 360 cells under its unchanged absolute tolerance and 40 under the scale-matched one; **the scale-matched count is the one to read**, and the discrepancy is a property of a rule written for a 4x coarser grid.

**But escalation itself stays weak, because the gate is the device's own stale score.** Device-triggered escalation-32B N = 1 captures only 3%/13%/13%/18% of the device-only → always-cloud AP span at h = 0 (trigger 5 %/10 %/20 %/40 %) for 11%/21%/36%/61% of always-cloud's calls, and swapping the resolver for the 4B barely moves it. **The binding constraint on this workload is when to ask, not who answers.** Decision rule 2's unchanged tolerance hides this; its scale-matched form does not.

**Study 2 — the admission decision rule is NOT MET at either pre-registered horizon.** Neither P-trajectory nor P-trajectory-work beats P-score on AP at h = 0.25 s or h = 0.5 s with a paired CI excluding 0 at 2 of 3 budgets, at either resolver, within the 10 % GPU-s allowance. **Per the pre-registered wording: on this workload the device score alone is the admission signal.** P-score separates from P-random in 1 of 18 (resolver x horizon x budget) cells in the favourable direction and 1 in the unfavourable one, with the sign changing across budgets within the same resolver and horizon, so the stronger pre-registered null also fires: **admission ranking has no signal on this workload** as measured by AP. The predictor is not the problem — it separates its training target out of sample (AUROC 0.648–0.764) and P-oracle shows real headroom (§12).

**Classification under CLAUDE.md Rule 2.** Study 2's null is a **real negative**, not inconclusive: Step 2 instantiated every link non-zero and varying on this grid, the Step 4 delivery-link control changes the result, control (c1) confirms the budget is the only difference between the policies at B = 1.0, and the predictor measurably separates its training target out of sample. Study 1 is a positive result on the link StudyE9 carried as CONSTANT.

## 18. Files

| file | what |
|---|---|
| `experiments/dashcam/study_e9b_dense.py` | delivery model, episode engine, AP engine, Study 1 |
| `experiments/dashcam/study_e9b_admission.py` | Study 2 (StudyE12's design on the dense grid) |
| `experiments/dashcam/study_e9b_control_a.py` | control (a), both input variants |
| `experiments/dashcam/study_e9b_report.py` | this report |
| `results/dashcam/study_e9b/e9b_mechanism_verification.md` | Steps 1–5, recorded before the sweep |
| `results/dashcam/study_e9b/e9b_study1_results.json` | Study 1 cells, baselines, sensitivity, rules, controls, trace |
| `results/dashcam/study_e9b/e9b_study2_results.json` | Study 2 cells, diagnostics, controls, trace |
| `results/dashcam/study_e9b/e9b_control_a.json` | control (a) comparison report |
| `results/dashcam/study_e9b/e9b_control_a_study2_d14.json`, `..._d14b.json` | control (a) Study 2 raw runs |
| `reports/study_e9b_dense.md` | this file |

Inputs: `results/dashcam/study_d14b/d14b_trace_h100nvl.jsonl.gz`; `results/dashcam/study_e9/e9_results.json`; `results/dashcam/study_e12/e12_results.json`; StudyD4 / D7 / D7b / D8 latency constants via `experiments/dashcam/study_e9_episodes.py`. Run on flash, **CPU only** — no GPU, no model server, no inference.

