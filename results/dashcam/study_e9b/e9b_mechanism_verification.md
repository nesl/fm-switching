# StudyE9b-dense — mechanism verification (CLAUDE.md Steps 1–5)

**Recorded 2026-11-12, BEFORE the sweep ran.** Every value below comes from probe runs made only to
instantiate the links (the input check, the threshold fit, the delivery arithmetic, zero-latency AP,
two always-on arms, one escalation cell and the Step 4 controls), not from the sweep. Offline replay
of committed StudyD14b / StudyD14 score traces; CPU only on the flash host; no GPU, no model server,
no inference. Every score is the continuous log P(Yes); no literal Yes/No answer is used anywhere.

## Step 0 — input check (recorded first, because it bounds everything else)

StudyD14b's committed claim is that its integer-t **P(Yes)** values are bit-identical to StudyD14's
on 42,640 / 42,640. That reproduces here. The derived field `score = log P(Yes)` is **not** quite
bit-identical: **21 of 42,640 integer-t scores differ by 1 ulp** (worst |Δ| = 1.78e-15), with
`p_yes` identical in every one of the 21. This is the log evaluation, not the model.

Consequence, fixed before any computation: **control (a) is run in two variants.**

- **a1** — input = StudyD14's own trace (the input StudyE9 and StudyE12 actually consumed). This is a
  pure check of *this code* and must be **exact**.
- **a2** — input = StudyD14b's integer-t rows. Agreement is bounded below by the 1-ulp input
  difference above, and the worst disagreement is reported rather than asserted to be zero.

## Step 1 — the causal chain

The experiment tests FORMULATION's placement decision `p_i` (§Decisions) under §Constraints 2
(*serving feasibility*: the serving node must answer within the latency SLO) and §Objective. The
chain is the same one StudyE9 tested, with one link that StudyE9 **could not exercise** restored:

**StudyD14b measured that on a 0.25-s grid the 32B model separates the seconds just before a crash
from normal driving better than the 4B model, and that most of that separation lives in the last
0.5 s before the event** (zero-latency AP at h = 0: 0.053 / 0.091 for 32B N1 / N3 against 0.028 for
4B N1; all arms within 1.4–3× chance from h = 0.75 s on). If that is true, then **when and how often
a score is delivered decides how much of that separation the application can still use.** A score
computed at frame time *t* is readable only from *t + L*; the application therefore acts on a *stale*
score, and the staler the score, the further back along the decaying AP-vs-horizon curve it sits.
Capability and delay trade against each other: the cloud is better per score but arrives later and
is called only at a cadence; the device is worse per score but is local. A device-triggered escalation
should therefore buy predictive quality exactly to the extent that the resolver's **delivered** score
is both better and not too much later than the device's own **delivered** score, and it should buy
fewer resolver invocations per episode to the extent that a better resolver reaches its alarm or
dismiss threshold sooner.

**The link StudyE9 could not exercise, and why this study exists.** StudyE9 and StudyE12 quantised
every latency to a whole second (`d = ceil(latency)`). The device's 0.567 s and the cloud's 0.395 s
both became 1 s, so *the delay difference between the two tiers was identically zero in every cell of
both studies*. Under CLAUDE.md's own rule that is a **CONSTANT link**: the quantity that implements
"the cloud delivers sooner than the device" could not vary, so neither study could test it. On the
0.25-s grid it varies (table in Step 2), which is the whole purpose of the re-run.

**A property of the design that bounds the effect, stated before the sweep.** As in StudyE9,
`tau_alarm`, `tau_dismiss` and `tau_trig` are quantiles of *each model's own* score distribution on
training-fold negative grid points, so all arms alarm on the same fraction of negative grid points by
construction. Any effect must come from the *ordering* of grid points within a clip and from positive
clips, not from a level difference. Two further bounds, both new to the dense grid and both recorded
here: (1) the dense grid has 3.94× the negatives per positive of the 1-s grid, so chance AP is
0.00728 against 0.0281 and **no AP may be compared across the two grids** — every AP in this report is
also given as a multiple of its own grid's chance rate; (2) StudyE9's decision rule 2 uses an
**absolute** tolerance of 0.01 AP, which on the dense grid is 1.4× the entire chance rate. The rule is
applied unchanged, as pre-registered, and a scale-matched variant (0.01 × 0.00728/0.0281 = 0.0026) is
reported beside it as a clearly labelled secondary, **not** as the rule.

## Step 2 — instantiate each link

| causal link | implementing quantity | value / range in the probe | varies as expected? | evidence |
|---|---|---|---|---|
| the grid can represent sub-second delay | grid step | 0.25 s; 42,014 points per arm (20,467 negative, 21,547 positive); chance rate 0.00728 | yes — 4 points per second where StudyE9 had 1 | StudyD14b trace |
| a score is readable only after its latency | sample-and-hold shift `D` = ceil(L / step) steps | device 3 steps (0.75 s); cloud 0 / 1 / 2 / 3 / 4 / 6 steps across the five latency settings and three resolvers | yes | delivery arithmetic from StudyD4 / D7 / D7b / D8 |
| **the cloud can deliver sooner than the device** (CONSTANT in StudyE9) | `D_cloud − D_device` in steps | **−1 step (32B N1 @25 %), 0 (32B N1 @75 %), +1 (32B N3 @25 %), +3 (32B N3 @75 %), −2 (jpeg 32B N1)** — against **0 in every cell of StudyE9** | **yes, and this is the link StudyE9 could not exercise** | delivery arithmetic |
| the device cannot poll faster than it computes | device cadence = max(1, ceil(L/step)) steps | 3 steps = 0.75 s, i.e. 1.33 Hz | yes; **FLAGGED**: StudyD8 measured sustained 1 Hz (arm A), so 0.75 s is a saturated-duty extrapolation, supported by D8's "no per-request penalty" finding and its back-to-back arm C | StudyD8 |
| staleness actually costs AP | delivered-stream AP vs zero-latency AP, h = 0 | device-only **0.0126** vs 0.0284 zero-latency; always-cloud 32B N1 **0.0384** vs 0.0530 | yes, strongly — about half the AP is lost to delay alone | probe |
| resolver capability differs | zero-latency AP at h = 0 / 0.5 s | 4B N1 0.0284 / 0.0189; 32B N1 0.0530 / 0.0415; 32B N3 0.0914 / 0.0437 | yes | probe |
| thresholds are matched across models | `tau_alarm` at 1 / 5 / 10 % FPR on negative grid points | 4B N1 −0.252 / −2.350 / −4.511; 32B N1 −0.693 / −4.883 / −8.000; 32B N3 −0.523 / −4.511 / −7.126 | yes, each model on its own scale at the same negative-grid-point rate | fitted thresholds |
| the device opens episodes at a controllable rate | `tau_trig` at 5 / 10 / 20 / 40 % | −2.350 / −4.511 / −7.001 / −10.750 | yes, monotone; it is the load knob | fitted thresholds |
| each fold has enough data to fit | training negative grid points per fold | 10,154 / 10,313 (of 20,467) | yes | fitted thresholds |
| resolver capability changes episode resolution | positive-clip episode outcomes, 32B N1 vs 4B N1, (ii) @25 %, cadence 0.5 s, FPR 5 %, trigger 10 % | alarm 425 vs 448, **dismiss 232 vs 175**, cap 5 vs 11, clip_end 33 vs 35 | yes — the 32B resolver resolves by dismissal far more often and runs to the cap half as often | probe |
| resolution → cloud work | resolver invocations per clip-hour, same cell | positives **1,708.2 (32B) vs 1,939.4 (4B)**; negatives 1,310.8 vs 1,447.2 | yes, in the direction the chain predicts | probe |
| latency consumes the episode | `D_cloud` against `L_max` = 40 steps | 2–6 steps under the measured settings; 40 steps in the Step 4 control | yes | probe |
| cadence is a charged knob | resolver calls per episode at cadence 0.25 / 0.5 / 1.0 s | swept; cloud work is charged per call | yes | design |

**No link is ABSENT or CONSTANT on the dense grid.** The link that was CONSTANT in StudyE9 and
StudyE12 — the delay difference between the tiers — is explicitly instantiated above and is the
reason for the re-run. The weakest link is the device's 0.75 s saturated cadence, which is an
extrapolation beyond StudyD8's measured 1 Hz operating point; it is flagged in the report body, not
buried, and the 1.0 s cadence row of every table is the conservative reading.

## Step 3 — trace one unit

The runner writes one instrumented episode on the dense grid to
`e9b_study1_results.json → trace_example`, on a positive clip chosen as the first one carrying both a
false dismissal before the event and a re-escalation. Per grid point it records: the grid time; the
time relative to the event; the device's compute index, its score and its **delivery time**; the
resolver call issued at that grid point (if any) with its own frame time and delivery time; the
**sample-and-hold value the application actually carries**; which tier it came from; whether an
episode is open; and the episode's outcome, invocations and GPU-seconds. The delivery times are the
unrounded measured latencies, so the arithmetic (`frame time + L ≤ grid time`) is checkable by hand.

## Step 4 — negative controls (run on a representative cell before the sweep)

1. **Zero latency ⇒ delivered stream equals compute stream.** Held stream == raw score array for
   **every arm and every one of the 300 clips**. PASS. (This is the pre-registered control (b).)
2. **Disable the delivery link and the result must collapse to device-only.** Escalation-32B N1,
   cadence 0.5 s, FPR 5 %, trigger 10 %, with `L_cloud` raised to 10 s (= `L_max`, so no resolver
   answer can ever arrive before the episode caps): AP at h = 0 / 0.25 / 0.5 / 0.75 / 1.0 / 1.5 s
   becomes **0.0126 / 0.0115 / 0.0104 / 0.0098 / 0.0102 / 0.0092**, which is device-only's curve
   **exactly**, against 0.0160 / 0.0118 / 0.0098 / 0.0103 / 0.0101 / 0.0095 at the measured
   `L_cloud` = 0.395 s. PASS: the mechanism, not the bookkeeping, drives the difference.
3. **Pre-registered and run with the sweep:** control (a) end-to-end reproduction of StudyE9 and
   StudyE12 (variants a1 and a2 of Step 0); StudyE9's own resolver-swap control (escalation-32B's code
   path with 4B N1 scores, thresholds and latency must equal escalation-4B exactly); StudyE9's
   within-clip resolver shuffle; and StudyE12's controls (budget 1.0 equals admit-all exactly, and a
   within-fold feature shuffle collapses P-trajectory to P-random).

**One control that is NOT an identity, recorded here so it is not later mistaken for a bug.**
Replacing the resolver's scores by the device's own scores at the device's own latency does *not*
reproduce device-only (worst stream difference 16.03), because the resolver's call schedule starts at
the trigger index while the device's compute schedule starts at the clip's first grid point, so the
two sample-and-hold grids are offset. Control 2 above is the delivery-link control; this one is not
used.

## Step 5 — alternative explanations

The headline this study can produce is "on a 0.25-s grid the cloud's escalation buys predictive
quality (or does not), where on the 1-s grid it did not (or did)". Three alternatives would produce
the same headline, and what separates them:

1. **Grid-scale artefact rather than delay resolution.** The dense grid has 3.94× the negatives per
   positive, so every AP falls. If a reader compares a dense AP with a 1-s AP, any arm will look
   worse. *Distinguished by:* never comparing across grids; reporting every AP as a multiple of its
   own chance rate; and by the 1.0-s-cadence rows, which keep the dense grid but restore StudyE9's
   call rate. If an effect appears only when the grid changes *and* disappears at cadence 1.0 s, it is
   cadence, not resolution.
2. **Cadence rather than delay.** On the dense grid the resolver is called every 0.25 / 0.5 / 1.0 s,
   so it produces up to 4× as many scores per episode as StudyE9's 1-s resolver. More scores alone
   improves a held stream, independently of any delay difference. *Distinguished by:* cadence is swept
   as its own axis at fixed latency, and cloud work is charged per call, so a cadence-driven gain
   shows up as a proportional GPU-second increase; a delay-driven gain does not.
3. **Horizon-grid alignment rather than earliness.** On the 1-s grid h = 0.25 and h = 0.75 round to a
   whole second and carry no new information; on the dense grid they are real. A gain that appears
   only at the two new horizons could be interpolation, not earliness. *Distinguished by:* the
   project's metric rule — earliness is read as the AP-curve horizon shift (StudyE9 §3.1), a property
   of the curves, now measured on a 0.25-s grid so the interpolation is 4× finer; and the shift is
   reported with its own clip-bootstrap CI.

If a reading survives none of these three, it is reported as an artefact of the grid or the cadence,
not as a finding about placement.
