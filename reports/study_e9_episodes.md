# StudyE9-episodes — device-triggered cloud escalation: does capability shorten episodes, and what does escalation keep per unit of cloud work?

**OFFLINE ANALYSIS OF COMMITTED RESULTS.** CPU only on the flash host: no GPU was used, no model server was started, and no inference was run. Every score is read from StudyD14's committed trace; every latency and byte count is read from a committed StudyD4 / StudyD7 / StudyD7b / StudyD8 measurement.

**E-id:** `StudyE9-episodes`, pre-registered in `research/EXPERIMENTS.md` on 2026-11-11 **before any number in this report was computed** (user-authorized row).  
**Scripts:** `experiments/dashcam/study_e9_episodes.py`, `experiments/dashcam/study_e9_report.py` (this file).  
**Results:** `results/dashcam/study_e9/e9_results.json`, `e9_mechanism_verification.md`.  
**Metric rule (fixed, never varied):** predictive quality is the Nexar metric — AP at fixed horizons on the **continuous** score (log P(Yes)), exactly as StudyE5 Part G. **No literal Yes/No answer is used anywhere**; alarm, dismiss and trigger are thresholds on the continuous score.  
**No INVALID result is used.**

## Prominent flags (read first)

1. **One second of end-to-end latency costs about as much AP as standing one second further from the event.** Always-cloud 32B N=1 scores 0.1473 at h = 0 with zero latency and 0.0724 at h = 1 s; under the measured setting its h = 0 value is 0.0748. The device arm behaves the same way (0.1023 → 0.0528). Every measured-latency number below is a horizon-shifted version of the zero-latency one, and that is the dominant effect in this study.
2. **Decision rule 1 is MET, but only at N = 1.** With the 32B resolver at N = 1 under latency setting (ii), escalation-32B uses fewer resolver invocations per clip-hour than escalation-4B with a paired CI excluding 0 in 2 of 3 alarm-FPR levels at trigger rates 5 %, 10 % and 20 %. At N = 3 the effect is marginal and at **N = 9 it reverses sharply** — the 32B resolver uses *more* cloud work, because its 2.6–3.9 s end-to-end latency wastes invocations inside a 10 s episode.
3. **Decision rule 2 is MET**, in 20 of the 108 (latency × N × alarm-FPR × trigger) cells, including under both latency settings. The cheapest is 32B N = 3 at 10 % alarm FPR and a 5 % trigger rate under setting (ii): AP within 0.0098 of always-cloud at every horizon ≤ 1 s with overlapping CIs, for **11 % of always-cloud's cloud work**.
4. **The two rules disagree about N, and the reason is latency, not capability.** Rule 1 wants N = 1 (short prompts, small delay); rule 2's best cells are N = 3. N = 9 is the clearest loss: it costs 794 GPU-s per clip-hour against 86 for N = 1, and under measured latency its always-cloud AP at h = 0 (0.0391) is **below the device-only arm's** (0.0528).
5. **False dismissals are common and re-escalation is the norm, not the exception.** At N = 1, measured @25 %, 5 % alarm FPR, 20 % trigger: 120 episodes on positive clips are dismissed before the event, and the device re-escalates 3.17 times per positive clip. The first-trigger-to-final-resolution span is 22 s (median) against a 10 s cap, because a clip holds several episodes.
6. **Escalation alarms on fewer crashes than always-cloud but raises fewer false alarms**, as it must: at N = 1, measured @25 %, 5 % FPR, 20 % trigger, 0.527 of positive clips alarm against 0.707 for always-cloud, at 83.8 vs 109.5 false alarms per clip-hour.
7. **Negative control (b) is uninformative under latency setting (ii), by construction.** Under setting (i) shuffling the resolver scores collapses AP at h = 0 from 0.13–0.16 to 0.04–0.05, which is the intended result. Under setting (ii) the real AP has already fallen to roughly that level, so the control cannot discriminate — a consequence of flag 1, not a defect in the control.
8. **The oracle is not in this study.** Every policy here is implementable from information available at the second it acts; no threshold is fitted on a clip it is then evaluated on (2-fold cross-fitting by clip, stratified by label, seed 0).

## 1. Setup

**Data.** StudyD14's committed trace, 150 positive and 150 negative Nexar VALIDATION clips, one score per arm × clip × second (t = 3 … floor(duration)): 5,464 positive and 5,196 negative clip-seconds per arm. The trace was checked for missing seconds before anything was computed — **every clip-arm is contiguous from t = 3**, so no episode boundary is affected (a STOP condition that did not fire). Base rate 150 / (150 + 5,196) = 0.0281.

**Device arm = 4BI N = 1.** The Jetson Orin sustains N = 1 at 1 Hz indefinitely (StudyD8 arm A: 1,800 requests in 1,800 s, 0 missed, no drift, no throttle). 4BI N = 3 is reported only as a **labelled secondary** in §12, because the Orin cannot sustain it at 1 Hz.

**Episode model.** A trigger (device score ≥ `tau_trig`) opens an episode at second `t0` when none is open; the resolver scores every second from `t0`; ALARM when a resolver score ≥ `tau_alarm`; DISMISS after `k` consecutive resolver scores < `tau_dismiss`; CAP at `L_max` seconds (dismissed); clip end closes it. After a dismissal the device keeps monitoring and a later trigger opens a new episode, subject to a cooldown `c`. **Resolver invocations are counted for every wall second the episode is open**, including requests whose result arrives after the episode closes — they were computed, so they are charged.

**Thresholds**, fitted by 2-fold cross-fitting by clip, stratified by label, seed 0, on the training fold's negative seconds only (2,578 of 5,196 per fold), evaluated on the held-out fold and pooled:

| arm | tau_alarm @ 1 / 5 / 10 % FAR | tau_dismiss @ 50 / 75 % | tau_trig @ 5 / 10 / 20 / 40 % |
|---|---|---|---|
| `4BI_N1` | -0.299 / -2.579 / -4.511 | -12.250 / -7.750 | -2.579 / -4.511 / -7.001 / -10.750 |
| `32BI_N1` | -0.693 / -4.883 / -7.963 | -17.500 / -13.250 | -4.883 / -7.963 / -12.000 / -16.000 |
| `32BI_N3` | -0.445 / -4.635 / -7.126 | -15.625 / -11.750 | -4.635 / -7.126 / -10.500 / -14.250 |
| `32BI_N9` | -1.655 / -6.608 / -9.000 | -16.000 / -12.531 | -6.608 / -9.000 / -11.625 / -14.875 |

(Fold 0's values are shown; fold 1's are in `e9_results.json → thresholds`.)

**Timing.** A score computed from second `t` is available at `t + latency`; the integer rule is `d = ceil(latency)`, so the score the application carries at wall second `t` is the one computed from second `t − d`. Two settings, labelled everywhere:

| setting | arm | device latency | RTT | upload | server TTFT | cloud latency | d_device | d_cloud |
|---|---|---|---|---|---|---|---|---|
| (i) zero | 32B N = 1 | 0.000 s | 0.000 s | 0.000 s | 0.000 s | 0.000 s | 0 s | **0 s** |
| (i) zero | 32B N = 3 | 0.000 s | 0.000 s | 0.000 s | 0.000 s | 0.000 s | 0 s | **0 s** |
| (i) zero | 32B N = 9 | 0.000 s | 0.000 s | 0.000 s | 0.000 s | 0.000 s | 0 s | **0 s** |
| (i) zero | 4B N = 1 (counterfactual resolver) | 0.000 s | 0.000 s | 0.000 s | 0.000 s | 0.000 s | 0 s | **0 s** |
| (ii) measured @25 % load | 32B N = 1 | 0.567 s | 0.044 s | 0.209 s | 0.142 s | 0.395 s | 1 s | **1 s** |
| (ii) measured @25 % load | 32B N = 3 | 0.567 s | 0.044 s | 0.622 s | 0.264 s | 0.930 s | 1 s | **1 s** |
| (ii) measured @25 % load | 32B N = 9 | 0.567 s | 0.044 s | 1.875 s | 0.635 s | 2.554 s | 1 s | **3 s** |
| (ii) measured @25 % load | 4B N = 1 (counterfactual resolver) | 0.567 s | 0.044 s | 0.209 s | 0.083 s | 0.335 s | 1 s | **1 s** |
| (ii) measured @75 % load | 32B N = 1 | 0.567 s | 0.044 s | 0.209 s | 0.298 s | 0.550 s | 1 s | **1 s** |
| (ii) measured @75 % load | 32B N = 3 | 0.567 s | 0.044 s | 0.622 s | 0.592 s | 1.258 s | 1 s | **2 s** |
| (ii) measured @75 % load | 32B N = 9 | 0.567 s | 0.044 s | 1.875 s | 1.980 s | 3.900 s | 1 s | **4 s** |
| (ii) measured @75 % load | 4B N = 1 (counterfactual resolver) | 0.567 s | 0.044 s | 0.209 s | 0.136 s | 0.389 s | 1 s | **1 s** |

Sources: device = StudyD8 arm A sustained 1 Hz N = 1 total latency p50 0.567 s; RTT 0.044 s; upload = StudyD4's median PNG request bytes (354,902 / 1,057,532 / 3,188,243 B at N = 1 / 3 / 9) at 13.6 Mbit/s; server = StudyD7b (N = 1) and StudyD7 (N = 3, N = 9) open-loop TTFT p50 measured from the scheduled arrival at 25 % and 75 % of peak.

**Comparison match statements.** All five arms read **byte-identical frames** at every (clip, t, N) — StudyD14 verified 10,660 / 10,660 frame-hash comparisons and identical prompt-token counts across models — on one stack (vLLM 0.31.0, FA3, prefix caching off, processor cache 0 GB), with identical greedy decoding. 32B vs 4B at the same N is therefore `IDENTICAL_INPUT`; comparisons across N are `REALLOCATED_BUDGET`. The device arm's *accuracy* is the H100 4B N = 1 score, used as a proxy for the Orin's (see §13 check 6); its *latency and energy* are the Orin's own.

## 2. Mechanism verification (CLAUDE.md Steps 1–5)

Recorded in `results/dashcam/study_e9/e9_mechanism_verification.md` **before the sweep ran**, and reproduced here in full.

> # StudyE9-episodes — mechanism verification (CLAUDE.md Steps 1–5)
>
> **Recorded 2026-11-11, BEFORE the sweep ran.** The values below come from probe runs made only to
> instantiate the links (threshold fitting, delay arithmetic, and four escalation cells), not from the
> sweep. Offline analysis of committed StudyD14 score traces; CPU only; no GPU, no server, no
> inference. Every score is the continuous log P(Yes); no literal Yes/No answer is used anywhere.
>
> ## Step 1 — the causal chain
>
> A device that must decide every second whether to call the cloud is making FORMULATION's placement
> decision `p_i` online (§Decisions), under §Constraints 2 (*serving feasibility*: the serving node
> must answer within the latency SLO) and §Objective (maximise the fraction of requests meeting the
> SLO, with cloud work reported as an explanatory cost, not folded into the objective). The chain the
> experiment tests is:
>
> **StudyE5 Part G measured that 32B separates the seconds just before a crash from normal driving
> better than 4B at a fixed horizon (AP 0.147 vs 0.102 at h = 0, CI excluding 0 up to h = 1 s).** If
> that is true, then inside an escalation episode a 32B resolver reaches its alarm threshold or its
> dismiss threshold *sooner* than a 4B resolver whose thresholds are set at the same per-second
> false-alarm rate on negatives. Sooner resolution means fewer resolver invocations per episode; and
> because a wrong dismissal on a positive clip sends the device back to monitoring and a later trigger
> re-opens an episode, better resolution also means fewer re-escalations. Both reduce total cloud work
> per clip-hour at the same trigger rate and the same alarm false-alarm rate. Separately, the score
> stream the application sees (resolver inside episodes, device outside) should keep more of
> always-cloud's AP the more often the resolver is running — which is the predictive-quality side of
> the same trade.
>
> **A property of the design that bounds the effect, stated before the sweep:** `tau_alarm` and
> `tau_dismiss` are fitted as quantiles of *each model's own* score distribution on training-fold
> negative seconds. By construction, therefore, both resolvers alarm on the same fraction of negative
> seconds and fall below their dismiss threshold on the same fraction of negative seconds. Any
> capability effect on episode length must come from the *ordering* of seconds within a clip and from
> positive clips, not from a level difference. This caps how large the effect can be and is carried
> into Step 5.
>
> ## Step 2 — instantiate each link
>
> | causal link | implementing quantity | value / range in the probe | varies as expected? | evidence |
> |---|---|---|---|---|
> | the device opens episodes at a controllable rate | `tau_trig`, device 4B N1 quantiles on training negatives | −2.579 / −4.511 / −7.001 / −10.750 at trigger rates 5 / 10 / 20 / 40 % | yes, monotone and it is the load knob | fitted thresholds |
> | thresholds are matched across models | `tau_alarm` at 1 / 5 / 10 % FAR | 4B N1 −0.299 / −2.579 / −4.511; 32B N1 −0.693 / −4.883 / −7.963; 32B N3 −0.445 / −4.635 / −7.126; 32B N9 −1.655 / −6.608 / −9.000 | yes, each model on its own scale at the same negative-second rate | fitted thresholds |
> | each fold has enough data to fit | training negative seconds per fold | 2,578 (of 5,196) | yes | fitted thresholds |
> | resolver capability changes episode resolution | episodes ending in `dismiss` on positive clips, 32B N1 vs 4B N1, zero latency, trigger 10 %, FAR 5 % | **134 vs 81**; `alarm` 341 vs 376; `cap` 10 vs 20 | yes — 32B resolves by dismissal more often and 4B runs to the cap twice as often | probe |
> | resolution time → cloud work | resolver invocations per positive clip-hour, same cell | **766.9 (32B) vs 856.5 (4B)**; negatives 604.2 vs 620.1 | yes, and in the direction the chain predicts | probe |
> | re-escalation after a wrong dismissal | episodes per clip | 503 vs 504 episodes on 150 positive clips at trigger 10 %; 818 vs 668 at trigger 20 % | yes, and it is not monotone in the model — reported, not assumed | probe |
> | latency consumes the episode | `d_cloud` in whole seconds | zero setting 0 everywhere; measured 1 (32B N1, both loads), 1–2 (N3), **3 (N9 @25 %) and 4 (N9 @75 %)** against `L_max` = 10 | yes, strongly at N = 9 | delay arithmetic from StudyD4 / D7 / D7b / D8 |
> | latency changes cloud work | invocations per positive clip-hour, 32B N1, trigger 10 %, FAR 5 % | 766.9 (zero) → 852.6 (measured @25 %) | yes | probe |
>
> **No link is ABSENT or CONSTANT.** The weakest is re-escalation, whose direction is not fixed by the
> chain; it is reported as measured.
>
> ## Step 3 — trace one unit
>
> The runner writes one instrumented episode trace to `e9_results.json → trace_example`: a positive
> clip, chosen as the first one that contains both a false dismissal before the event and a
> re-escalation. It records, per second: the wall second, the second relative to the event, which
> frame-second the device score came from, which frame-second the resolver score came from, the score
> the application stream carries and its source, and whether an episode was open — together with the
> three fitted thresholds, `k`, `L_max`, the cooldown, every episode's open/close second and outcome,
> the invocation count and the GPU-seconds. The arithmetic is checkable by hand from those columns.
>
> ## Step 4 — negative controls
>
> - **(a) Swap the resolver.** Running escalation-32B's code path with 4B N1 resolver scores, 4B N1
>   thresholds and 4B N1 cloud latency must reproduce escalation-4B exactly, cell for cell. This tests
>   the implementation, not the data: if it fails, the two arms differ by something other than the
>   resolver.
> - **(b) Shuffle the resolver scores across seconds within each clip.** The resolver then carries the
>   same marginal distribution but no timing information, so AP at h ≤ 1 s must fall toward the base
>   rate (0.0281). If it does not, the alarm timing is not coming from the resolver's within-clip
>   signal.
>
> Both are pre-registered and are run on the primary configuration.
>
> ## Step 5 — alternative explanations
>
> 1. **"32B shortens episodes because it is better" vs "32B shortens episodes because its score
>    distribution has a different shape."** The thresholds are matched on negative-second rates, which
>    equalises the *level* but not the *shape* (skew, within-clip autocorrelation). The two are
>    separated by negative control (b): shuffling destroys within-clip ordering while preserving the
>    marginal distribution, so whatever survives the shuffle is shape, not timing.
> 2. **"Escalation keeps AP because the resolver is good" vs "escalation keeps AP because the device
>    score alone already carries it."** Separated by the escalation-4B arm, whose resolver *is* the
>    device model: any AP that escalation-32B has over escalation-4B at the same trigger rate is the
>    resolver's.
> 3. **"Cloud work falls because episodes are shorter" vs "cloud work falls because fewer episodes
>    open."** The trigger threshold is fitted on the device arm only and is identical across the two
>    escalation arms at a given trigger rate, so the number of *opening* triggers is the same input;
>    episodes per clip and invocations per episode are reported separately so the two cannot be
>    confused.
> 4. **Latency as a confounder.** A longer `d_cloud` both delays the first usable resolver result and
>    wastes invocations issued before it arrives. N = 9 at 75 % load has `d_cloud` = 4 s against
>    `L_max` = 10 s, so at most 7 of its 10 charged invocations can influence the outcome. Both latency
>    settings are reported for every cell, and the zero setting is labelled as pure capability.
> 5. **The matched-rate construction itself.** As stated in Step 1, matching thresholds on negative
>    seconds means negative-clip episode behaviour is equalised by design. If the measured capability
>    effect turns out to live almost entirely on positive clips, that is the expected consequence of
>    the design and not evidence of a larger effect; the report splits positives and negatives for
>    exactly this reason.

## 3. Output 1 — predictive quality (Nexar AP at fixed horizons)

AP is computed on the score stream the application actually sees: the resolver's score inside an episode, the device's outside. Positives are each positive clip's stream value at the whole second nearest event − h; negatives are all 5,196 negative-clip seconds. Clip bootstrap, 2,000 resamples, seed 0, stratified by label, with the **same resample indices shared by every cell**, so differences are paired.

**Latency setting (i) zero, alarm FPR 5 %, primary episode configuration (k = 2, dismiss q = 0.75, L_max = 10 s, cooldown = 0 s)**

| policy | h = 0 | h = 0.5 | h = 1.0 | h = 1.5 | h = 2.0 | cloud invocations / clip-hour |
|---|---|---|---|---|---|---|
| device-only (4B N = 1) | 0.1023 [0.068, 0.152] | 0.0624 [0.048, 0.090] | 0.0513 [0.041, 0.070] | 0.0401 [0.033, 0.052] | 0.0374 [0.031, 0.047] | 0 |
| always-cloud 32B N = 1 | 0.1473 [0.099, 0.207] | 0.1074 [0.077, 0.157] | 0.0724 [0.056, 0.099] | 0.0476 [0.039, 0.062] | 0.0411 [0.034, 0.052] | 3,600 |
| always-cloud 32B N = 3 | 0.1822 [0.128, 0.250] | 0.1130 [0.081, 0.157] | 0.0667 [0.054, 0.086] | 0.0485 [0.040, 0.061] | 0.0428 [0.036, 0.053] | 3,600 |
| always-cloud 32B N = 9 | 0.1505 [0.103, 0.217] | 0.0876 [0.067, 0.129] | 0.0606 [0.049, 0.080] | 0.0455 [0.038, 0.058] | 0.0398 [0.034, 0.050] | 3,600 |
| escalation-32B N = 1, trigger 5 % | 0.1131 [0.074, 0.164] | 0.0772 [0.055, 0.117] | 0.0546 [0.044, 0.074] | 0.0402 [0.033, 0.052] | 0.0395 [0.032, 0.054] | 356 |
| escalation-32B N = 1, trigger 10 % | 0.1222 [0.078, 0.178] | 0.0795 [0.056, 0.123] | 0.0551 [0.044, 0.074] | 0.0402 [0.033, 0.052] | 0.0382 [0.031, 0.051] | 688 |
| escalation-32B N = 1, trigger 20 % | 0.1333 [0.087, 0.191] | 0.0950 [0.066, 0.143] | 0.0638 [0.049, 0.087] | 0.0425 [0.035, 0.057] | 0.0373 [0.031, 0.049] | 1,214 |
| escalation-32B N = 1, trigger 40 % | 0.1397 [0.093, 0.198] | 0.1013 [0.072, 0.151] | 0.0689 [0.053, 0.094] | 0.0449 [0.036, 0.059] | 0.0387 [0.032, 0.050] | 2,024 |
| escalation-32B N = 3, trigger 5 % | 0.1232 [0.082, 0.175] | 0.0879 [0.060, 0.129] | 0.0578 [0.046, 0.079] | 0.0413 [0.035, 0.052] | 0.0402 [0.033, 0.054] | 376 |
| escalation-32B N = 3, trigger 10 % | 0.1379 [0.091, 0.197] | 0.0845 [0.058, 0.125] | 0.0585 [0.046, 0.079] | 0.0454 [0.037, 0.059] | 0.0394 [0.033, 0.050] | 698 |
| escalation-32B N = 3, trigger 20 % | 0.1606 [0.109, 0.225] | 0.1017 [0.071, 0.146] | 0.0667 [0.052, 0.089] | 0.0478 [0.039, 0.062] | 0.0414 [0.035, 0.052] | 1,224 |
| escalation-32B N = 3, trigger 40 % | 0.1693 [0.119, 0.232] | 0.1043 [0.074, 0.146] | 0.0661 [0.052, 0.087] | 0.0485 [0.039, 0.062] | 0.0417 [0.035, 0.052] | 2,026 |
| escalation-32B N = 9, trigger 5 % | 0.1214 [0.078, 0.182] | 0.0714 [0.052, 0.115] | 0.0533 [0.043, 0.076] | 0.0404 [0.034, 0.051] | 0.0402 [0.033, 0.055] | 356 |
| escalation-32B N = 9, trigger 10 % | 0.1160 [0.075, 0.175] | 0.0686 [0.051, 0.107] | 0.0555 [0.044, 0.077] | 0.0416 [0.035, 0.054] | 0.0382 [0.032, 0.049] | 678 |
| escalation-32B N = 9, trigger 20 % | 0.1355 [0.089, 0.201] | 0.0821 [0.060, 0.127] | 0.0644 [0.050, 0.089] | 0.0451 [0.037, 0.059] | 0.0393 [0.033, 0.051] | 1,199 |
| escalation-32B N = 9, trigger 40 % | 0.1449 [0.099, 0.210] | 0.0848 [0.064, 0.127] | 0.0614 [0.048, 0.084] | 0.0450 [0.037, 0.059] | 0.0405 [0.034, 0.052] | 2,007 |
| escalation-4B N = 1, trigger 5 % | 0.1023 [0.068, 0.152] | 0.0624 [0.048, 0.090] | 0.0513 [0.041, 0.070] | 0.0401 [0.033, 0.052] | 0.0374 [0.031, 0.047] | 214 |
| escalation-4B N = 1, trigger 10 % | 0.1023 [0.068, 0.152] | 0.0624 [0.048, 0.090] | 0.0513 [0.041, 0.070] | 0.0401 [0.033, 0.052] | 0.0374 [0.031, 0.047] | 741 |
| escalation-4B N = 1, trigger 20 % | 0.1023 [0.068, 0.152] | 0.0624 [0.048, 0.090] | 0.0513 [0.041, 0.070] | 0.0401 [0.033, 0.052] | 0.0374 [0.031, 0.047] | 1,314 |
| escalation-4B N = 1, trigger 40 % | 0.1023 [0.068, 0.152] | 0.0624 [0.048, 0.090] | 0.0513 [0.041, 0.070] | 0.0401 [0.033, 0.052] | 0.0374 [0.031, 0.047] | 2,005 |

**Latency setting (ii) measured @25 % load, alarm FPR 5 %, primary episode configuration (k = 2, dismiss q = 0.75, L_max = 10 s, cooldown = 0 s)**

| policy | h = 0 | h = 0.5 | h = 1.0 | h = 1.5 | h = 2.0 | cloud invocations / clip-hour |
|---|---|---|---|---|---|---|
| device-only (4B N = 1) | 0.0528 [0.042, 0.072] | 0.0416 [0.034, 0.054] | 0.0386 [0.032, 0.049] | 0.0376 [0.031, 0.048] | 0.0368 [0.029, 0.055] | 0 |
| always-cloud 32B N = 1 | 0.0748 [0.058, 0.102] | 0.0493 [0.040, 0.064] | 0.0423 [0.035, 0.054] | 0.0405 [0.034, 0.050] | 0.0445 [0.033, 0.063] | 3,600 |
| always-cloud 32B N = 3 | 0.0674 [0.054, 0.087] | 0.0497 [0.041, 0.063] | 0.0435 [0.037, 0.053] | 0.0412 [0.034, 0.052] | 0.0359 [0.031, 0.045] | 3,600 |
| always-cloud 32B N = 9 | 0.0391 [0.033, 0.053] | 0.0349 [0.030, 0.042] | 0.0328 [0.029, 0.039] | 0.0315 [0.028, 0.037] | 0.0312 [0.027, 0.037] | 3,600 |
| escalation-32B N = 1, trigger 5 % | 0.0592 [0.046, 0.085] | 0.0410 [0.034, 0.052] | 0.0377 [0.031, 0.047] | 0.0390 [0.032, 0.050] | 0.0411 [0.030, 0.061] | 401 |
| escalation-32B N = 1, trigger 10 % | 0.0593 [0.046, 0.084] | 0.0405 [0.034, 0.051] | 0.0371 [0.031, 0.046] | 0.0384 [0.032, 0.050] | 0.0415 [0.030, 0.062] | 755 |
| escalation-32B N = 1, trigger 20 % | 0.0654 [0.049, 0.094] | 0.0411 [0.034, 0.053] | 0.0358 [0.031, 0.044] | 0.0367 [0.031, 0.047] | 0.0443 [0.030, 0.069] | 1,281 |
| escalation-32B N = 1, trigger 40 % | 0.0634 [0.048, 0.088] | 0.0445 [0.036, 0.058] | 0.0393 [0.033, 0.050] | 0.0364 [0.030, 0.046] | 0.0445 [0.031, 0.068] | 2,052 |
| escalation-32B N = 3, trigger 5 % | 0.0573 [0.046, 0.080] | 0.0418 [0.035, 0.052] | 0.0384 [0.032, 0.047] | 0.0394 [0.033, 0.052] | 0.0421 [0.031, 0.063] | 423 |
| escalation-32B N = 3, trigger 10 % | 0.0631 [0.048, 0.092] | 0.0438 [0.036, 0.058] | 0.0377 [0.032, 0.046] | 0.0386 [0.032, 0.050] | 0.0423 [0.030, 0.064] | 771 |
| escalation-32B N = 3, trigger 20 % | 0.0593 [0.047, 0.079] | 0.0438 [0.036, 0.056] | 0.0388 [0.033, 0.049] | 0.0390 [0.033, 0.053] | 0.0437 [0.032, 0.067] | 1,292 |
| escalation-32B N = 3, trigger 40 % | 0.0601 [0.048, 0.080] | 0.0447 [0.038, 0.056] | 0.0404 [0.034, 0.050] | 0.0372 [0.031, 0.048] | 0.0415 [0.030, 0.063] | 2,071 |
| escalation-32B N = 9, trigger 5 % | 0.0566 [0.044, 0.084] | 0.0412 [0.034, 0.052] | 0.0394 [0.033, 0.050] | 0.0387 [0.032, 0.049] | 0.0412 [0.030, 0.061] | 491 |
| escalation-32B N = 9, trigger 10 % | 0.0549 [0.043, 0.081] | 0.0413 [0.034, 0.053] | 0.0396 [0.033, 0.050] | 0.0395 [0.033, 0.050] | 0.0402 [0.029, 0.059] | 884 |
| escalation-32B N = 9, trigger 20 % | 0.0598 [0.046, 0.092] | 0.0372 [0.031, 0.047] | 0.0344 [0.030, 0.042] | 0.0375 [0.032, 0.047] | 0.0396 [0.029, 0.058] | 1,439 |
| escalation-32B N = 9, trigger 40 % | 0.0542 [0.042, 0.076] | 0.0386 [0.032, 0.049] | 0.0326 [0.028, 0.040] | 0.0322 [0.027, 0.040] | 0.0369 [0.027, 0.055] | 2,224 |
| escalation-4B N = 1, trigger 5 % | 0.0528 [0.042, 0.072] | 0.0416 [0.034, 0.054] | 0.0386 [0.032, 0.049] | 0.0376 [0.031, 0.048] | 0.0368 [0.029, 0.055] | 431 |
| escalation-4B N = 1, trigger 10 % | 0.0528 [0.042, 0.072] | 0.0416 [0.034, 0.054] | 0.0386 [0.032, 0.049] | 0.0376 [0.031, 0.048] | 0.0368 [0.029, 0.055] | 821 |
| escalation-4B N = 1, trigger 20 % | 0.0528 [0.042, 0.072] | 0.0416 [0.034, 0.054] | 0.0386 [0.032, 0.049] | 0.0376 [0.031, 0.048] | 0.0368 [0.029, 0.055] | 1,319 |
| escalation-4B N = 1, trigger 40 % | 0.0528 [0.042, 0.072] | 0.0416 [0.034, 0.054] | 0.0386 [0.032, 0.049] | 0.0376 [0.031, 0.048] | 0.0368 [0.029, 0.055] | 2,034 |

**Latency setting (ii) measured @75 % load, alarm FPR 5 %, primary episode configuration (k = 2, dismiss q = 0.75, L_max = 10 s, cooldown = 0 s)**

| policy | h = 0 | h = 0.5 | h = 1.0 | h = 1.5 | h = 2.0 | cloud invocations / clip-hour |
|---|---|---|---|---|---|---|
| device-only (4B N = 1) | 0.0528 [0.042, 0.072] | 0.0416 [0.034, 0.054] | 0.0386 [0.032, 0.049] | 0.0376 [0.031, 0.048] | 0.0368 [0.029, 0.055] | 0 |
| always-cloud 32B N = 1 | 0.0748 [0.058, 0.102] | 0.0493 [0.040, 0.064] | 0.0423 [0.035, 0.054] | 0.0405 [0.034, 0.050] | 0.0445 [0.033, 0.063] | 3,600 |
| always-cloud 32B N = 3 | 0.0451 [0.038, 0.056] | 0.0422 [0.035, 0.054] | 0.0366 [0.031, 0.046] | 0.0344 [0.030, 0.041] | 0.0337 [0.029, 0.040] | 3,600 |
| always-cloud 32B N = 9 | 0.0338 [0.029, 0.040] | 0.0321 [0.028, 0.037] | 0.0321 [0.028, 0.038] | 0.0338 [0.029, 0.040] | 0.0322 [0.028, 0.039] | 3,600 |
| escalation-32B N = 1, trigger 5 % | 0.0592 [0.046, 0.085] | 0.0410 [0.034, 0.052] | 0.0377 [0.031, 0.047] | 0.0390 [0.032, 0.050] | 0.0411 [0.030, 0.061] | 401 |
| escalation-32B N = 1, trigger 10 % | 0.0593 [0.046, 0.084] | 0.0405 [0.034, 0.051] | 0.0371 [0.031, 0.046] | 0.0384 [0.032, 0.050] | 0.0415 [0.030, 0.062] | 755 |
| escalation-32B N = 1, trigger 20 % | 0.0654 [0.049, 0.094] | 0.0411 [0.034, 0.053] | 0.0358 [0.031, 0.044] | 0.0367 [0.031, 0.047] | 0.0443 [0.030, 0.069] | 1,281 |
| escalation-32B N = 1, trigger 40 % | 0.0634 [0.048, 0.088] | 0.0445 [0.036, 0.058] | 0.0393 [0.033, 0.050] | 0.0364 [0.030, 0.046] | 0.0445 [0.031, 0.068] | 2,052 |
| escalation-32B N = 3, trigger 5 % | 0.0548 [0.044, 0.078] | 0.0428 [0.035, 0.057] | 0.0404 [0.033, 0.053] | 0.0401 [0.033, 0.052] | 0.0353 [0.030, 0.045] | 473 |
| escalation-32B N = 3, trigger 10 % | 0.0538 [0.043, 0.075] | 0.0408 [0.034, 0.052] | 0.0389 [0.032, 0.050] | 0.0389 [0.032, 0.050] | 0.0347 [0.030, 0.043] | 836 |
| escalation-32B N = 3, trigger 20 % | 0.0522 [0.043, 0.070] | 0.0412 [0.034, 0.054] | 0.0380 [0.032, 0.049] | 0.0370 [0.031, 0.048] | 0.0331 [0.028, 0.040] | 1,384 |
| escalation-32B N = 3, trigger 40 % | 0.0490 [0.040, 0.065] | 0.0407 [0.034, 0.053] | 0.0377 [0.032, 0.047] | 0.0370 [0.031, 0.046] | 0.0333 [0.029, 0.040] | 2,161 |
| escalation-32B N = 9, trigger 5 % | 0.0525 [0.042, 0.073] | 0.0405 [0.034, 0.052] | 0.0382 [0.032, 0.047] | 0.0392 [0.032, 0.050] | 0.0410 [0.030, 0.061] | 535 |
| escalation-32B N = 9, trigger 10 % | 0.0533 [0.042, 0.077] | 0.0407 [0.034, 0.053] | 0.0372 [0.031, 0.046] | 0.0367 [0.031, 0.046] | 0.0406 [0.030, 0.060] | 940 |
| escalation-32B N = 9, trigger 20 % | 0.0455 [0.037, 0.064] | 0.0353 [0.030, 0.043] | 0.0326 [0.028, 0.039] | 0.0344 [0.029, 0.042] | 0.0398 [0.029, 0.059] | 1,480 |
| escalation-32B N = 9, trigger 40 % | 0.0431 [0.035, 0.058] | 0.0359 [0.031, 0.044] | 0.0340 [0.029, 0.041] | 0.0358 [0.030, 0.043] | 0.0411 [0.030, 0.061] | 2,306 |
| escalation-4B N = 1, trigger 5 % | 0.0528 [0.042, 0.072] | 0.0416 [0.034, 0.054] | 0.0386 [0.032, 0.049] | 0.0376 [0.031, 0.048] | 0.0368 [0.029, 0.055] | 431 |
| escalation-4B N = 1, trigger 10 % | 0.0528 [0.042, 0.072] | 0.0416 [0.034, 0.054] | 0.0386 [0.032, 0.049] | 0.0376 [0.031, 0.048] | 0.0368 [0.029, 0.055] | 821 |
| escalation-4B N = 1, trigger 20 % | 0.0528 [0.042, 0.072] | 0.0416 [0.034, 0.054] | 0.0386 [0.032, 0.049] | 0.0376 [0.031, 0.048] | 0.0368 [0.029, 0.055] | 1,319 |
| escalation-4B N = 1, trigger 40 % | 0.0528 [0.042, 0.072] | 0.0416 [0.034, 0.054] | 0.0386 [0.032, 0.049] | 0.0376 [0.031, 0.048] | 0.0368 [0.029, 0.055] | 2,034 |

### 3.1 AP-curve horizon shift, 32B vs 4B N = 1

> CURVE SHIFT, NOT a per-event time: at the AP the 4B arm reaches at horizon h, this is how much further ahead the 32B arm reaches the same AP, by linear interpolation of the AP-vs-horizon curve. It says nothing about when either model first notices a given crash.

| arm pair | latency | h = 0 | h = 0.5 | h = 1.0 | h = 1.5 | h = 2.0 |
|---|---|---|---|---|---|---|
| 32B N = 1 vs 4B N = 1 | (i) zero | +0.57 s [+0.12, +1.12] | +0.70 s [+0.30, +1.00] | +0.43 s [+0.11, +1.00] | +0.50 s [-0.03, +0.50] | +0.00 s [-0.28, +0.00] |
| 32B N = 3 vs 4B N = 1 | (i) zero | +0.62 s [+0.27, +1.02] | +0.62 s [+0.26, +1.10] | +0.42 s [-0.03, +1.00] | +0.50 s [-0.07, +0.50] | +0.00 s [-0.39, +0.00] |
| 32B N = 9 vs 4B N = 1 | (i) zero | +0.38 s [+0.03, +0.89] | +0.47 s [-0.01, +0.95] | +0.31 s [-0.18, +1.00] | +0.47 s [-0.19, +0.50] | +0.00 s [-0.55, +0.00] |
| 32B N = 1 vs 4B N = 1 | (ii) measured @25 % load | +0.43 s [+0.12, +1.12] | +0.69 s [-0.03, +1.50] | +1.00 s [-0.27, +1.00] | +0.50 s [-0.78, +0.50] | +0.00 s [-1.60, +0.00] |
| 32B N = 3 vs 4B N = 1 | (ii) measured @25 % load | +0.41 s [+0.00, +1.39] | +0.92 s [-0.09, +1.50] | +0.75 s [-0.41, +1.00] | +0.34 s [-0.74, +0.50] | -0.09 s [-1.64, +0.00] |
| 32B N = 9 vs 4B N = 1 | (ii) measured @25 % load | +0.00 s [+0.00, +0.01] | -0.50 s [-0.50, +0.29] | -0.95 s [-1.00, +0.34] | -1.33 s [-1.50, +0.50] | -1.73 s [-2.00, +0.00] |
| 32B N = 1 vs 4B N = 1 | (ii) measured @75 % load | +0.43 s [+0.12, +1.12] | +0.69 s [-0.03, +1.50] | +1.00 s [-0.27, +1.00] | +0.50 s [-0.78, +0.50] | +0.00 s [-1.60, +0.00] |
| 32B N = 3 vs 4B N = 1 | (ii) measured @75 % load | +0.00 s [+0.00, +0.58] | +0.06 s [-0.50, +1.26] | -0.18 s [-1.00, +1.00] | -0.59 s [-1.50, +0.50] | -1.02 s [-2.00, +0.00] |
| 32B N = 9 vs 4B N = 1 | (ii) measured @75 % load | +0.00 s [+0.00, +0.00] | -0.50 s [-0.50, -0.46] | -1.00 s [-1.00, -0.17] | -1.50 s [-1.50, +0.50] | -2.00 s [-2.00, +0.00] |

Read this as: at the AP the 4B arm reaches at horizon h, the 32B arm reaches the same AP this much further ahead of the event. **It is a property of the two AP-vs-horizon curves, not a claim that 32B notices any particular crash earlier** — StudyE5's within-clip rise analysis found no earliness advantage, and nothing here contradicts that. The shift is bounded above by the 0.5 s horizon grid and below by it as well, so values pinned at exactly ±0.5 / ±1.0 / ±2.0 are at a grid edge.

## 4. Output 2 — alarm timing

An alarm is a distinct event: for the escalation policies it is an episode that ends in ALARM; for device-only and always-cloud it is an up-crossing of `tau_alarm` (a second at or above the threshold whose predecessor was below it). `alarm − event` is in seconds, negative = before the event. Only the **first** alarm of a positive clip is timed.

**Latency setting (i) zero, alarm FPR 5 %, primary configuration**

| policy | positives alarmed | alarm − event p25 / p50 / p75 (s) | alarmed by h = 0 | 0.5 | 1.0 | 1.5 | 2.0 | false alarms / clip-hour |
|---|---|---|---|---|---|---|---|---|
| device-only (4B N = 1) | 0.540 | -11.42 / -2.30 / +1.10 | 0.340 | 0.327 | 0.300 | 0.280 | 0.280 | 100.5 |
| always-cloud 32B N = 1 | 0.707 | -13.21 / -1.27 / +1.22 | 0.480 | 0.447 | 0.373 | 0.347 | 0.340 | 112.9 |
| always-cloud 32B N = 3 | 0.787 | -7.27 / -0.43 / +0.69 | 0.467 | 0.380 | 0.327 | 0.307 | 0.293 | 124.0 |
| always-cloud 32B N = 9 | 0.753 | -7.90 / -0.33 / +1.70 | 0.420 | 0.367 | 0.313 | 0.280 | 0.273 | 119.9 |
| escalation-32B N = 1, trigger 10 % | 0.500 | -8.32 / -0.65 / +1.18 | 0.293 | 0.260 | 0.220 | 0.200 | 0.193 | 115.7 |
| escalation-32B N = 1, trigger 20 % | 0.613 | -10.57 / -0.86 / +0.84 | 0.393 | 0.353 | 0.287 | 0.260 | 0.253 | 146.2 |
| escalation-32B N = 3, trigger 10 % | 0.540 | -2.05 / +0.10 / +2.79 | 0.260 | 0.213 | 0.167 | 0.147 | 0.140 | 87.3 |
| escalation-32B N = 3, trigger 20 % | 0.613 | -4.28 / -0.19 / +1.85 | 0.327 | 0.273 | 0.227 | 0.193 | 0.180 | 115.7 |
| escalation-32B N = 9, trigger 10 % | 0.513 | -2.05 / +0.29 / +2.79 | 0.227 | 0.213 | 0.160 | 0.133 | 0.133 | 81.1 |
| escalation-32B N = 9, trigger 20 % | 0.593 | -3.47 / -0.47 / +1.70 | 0.320 | 0.293 | 0.233 | 0.207 | 0.193 | 109.5 |
| escalation-4B N = 1, trigger 10 % | 0.540 | -11.42 / -2.30 / +1.10 | 0.340 | 0.327 | 0.300 | 0.280 | 0.280 | 179.4 |
| escalation-4B N = 1, trigger 20 % | 0.540 | -11.42 / -2.30 / +1.10 | 0.340 | 0.327 | 0.300 | 0.280 | 0.280 | 179.4 |

**Latency setting (ii) measured @25 % load, alarm FPR 5 %, primary configuration**

| policy | positives alarmed | alarm − event p25 / p50 / p75 (s) | alarmed by h = 0 | 0.5 | 1.0 | 1.5 | 2.0 | false alarms / clip-hour |
|---|---|---|---|---|---|---|---|---|
| device-only (4B N = 1) | 0.533 | -10.65 / -1.50 / +2.03 | 0.300 | 0.280 | 0.280 | 0.267 | 0.253 | 96.3 |
| always-cloud 32B N = 1 | 0.707 | -12.21 / -0.27 / +2.22 | 0.373 | 0.347 | 0.340 | 0.340 | 0.333 | 109.5 |
| always-cloud 32B N = 3 | 0.787 | -6.27 / +0.57 / +1.69 | 0.327 | 0.307 | 0.293 | 0.287 | 0.287 | 119.2 |
| always-cloud 32B N = 9 | 0.740 | -5.03 / +2.53 / +4.60 | 0.247 | 0.247 | 0.233 | 0.233 | 0.227 | 106.0 |
| escalation-32B N = 1, trigger 10 % | 0.420 | -4.89 / +0.77 / +5.07 | 0.173 | 0.153 | 0.153 | 0.147 | 0.140 | 64.4 |
| escalation-32B N = 1, trigger 20 % | 0.527 | -6.86 / +0.47 / +3.34 | 0.227 | 0.207 | 0.207 | 0.200 | 0.193 | 83.8 |
| escalation-32B N = 3, trigger 10 % | 0.447 | -0.05 / +2.03 / +5.02 | 0.120 | 0.107 | 0.100 | 0.093 | 0.093 | 56.1 |
| escalation-32B N = 3, trigger 20 % | 0.547 | -0.72 / +1.47 / +5.19 | 0.153 | 0.140 | 0.133 | 0.133 | 0.133 | 72.1 |
| escalation-32B N = 9, trigger 10 % | 0.380 | +1.95 / +3.77 / +5.79 | 0.080 | 0.080 | 0.080 | 0.080 | 0.073 | 38.8 |
| escalation-32B N = 9, trigger 20 % | 0.460 | +1.05 / +3.77 / +5.10 | 0.100 | 0.100 | 0.093 | 0.093 | 0.087 | 47.1 |
| escalation-4B N = 1, trigger 10 % | 0.413 | -4.84 / +1.26 / +3.37 | 0.153 | 0.140 | 0.140 | 0.127 | 0.120 | 85.2 |
| escalation-4B N = 1, trigger 20 % | 0.447 | -6.99 / +0.48 / +2.29 | 0.207 | 0.187 | 0.187 | 0.167 | 0.160 | 98.4 |

## 5. Output 3 — cloud work

GPU-seconds = invocations × prompt tokens / measured saturated prefill rate (32B 5,600 tok/s from StudyD7; 4B 29,500 tok/s from StudyD7b). Prompt tokens are 378 / 1,062 / 3,090 at N = 1 / 3 / 9. Totals are per clip-hour of the stated label and **include re-escalations**.

**Latency setting (i) zero, alarm FPR 5 %, primary configuration**

| policy | pos: invocations / clip-h | pos: GPU-s / clip-h | neg: invocations / clip-h | neg: GPU-s / clip-h | all: invocations / clip-h | all: GPU-s / clip-h | % of always-cloud |
|---|---|---|---|---|---|---|---|
| always-cloud 32B N = 1 | 3,600 | 243.0 | 3,600 | 243.0 | 3,600 | 243.0 | 100 % |
| always-cloud 32B N = 3 | 3,600 | 682.7 | 3,600 | 682.7 | 3,600 | 682.7 | 100 % |
| always-cloud 32B N = 9 | 3,600 | 1,986.4 | 3,600 | 1,986.4 | 3,600 | 1,986.4 | 100 % |
| escalation-32B N = 1, trigger 5 % | 390 | 26.3 | 319 | 21.6 | 356 | 24.0 | 10 % |
| escalation-32B N = 1, trigger 10 % | 767 | 51.8 | 604 | 40.8 | 688 | 46.4 | 19 % |
| escalation-32B N = 1, trigger 20 % | 1,351 | 91.2 | 1,071 | 72.3 | 1,214 | 82.0 | 34 % |
| escalation-32B N = 1, trigger 40 % | 2,235 | 150.9 | 1,802 | 121.6 | 2,024 | 136.6 | 56 % |
| escalation-32B N = 3, trigger 5 % | 424 | 80.3 | 326 | 61.8 | 376 | 71.3 | 10 % |
| escalation-32B N = 3, trigger 10 % | 800 | 151.7 | 590 | 111.9 | 698 | 132.3 | 19 % |
| escalation-32B N = 3, trigger 20 % | 1,388 | 263.1 | 1,052 | 199.5 | 1,224 | 232.1 | 34 % |
| escalation-32B N = 3, trigger 40 % | 2,240 | 424.8 | 1,801 | 341.5 | 2,026 | 384.2 | 56 % |
| escalation-32B N = 9, trigger 5 % | 405 | 223.6 | 304 | 167.8 | 356 | 196.4 | 10 % |
| escalation-32B N = 9, trigger 10 % | 779 | 429.7 | 572 | 315.4 | 678 | 374.0 | 19 % |
| escalation-32B N = 9, trigger 20 % | 1,343 | 741.3 | 1,048 | 578.0 | 1,199 | 661.7 | 33 % |
| escalation-32B N = 9, trigger 40 % | 2,216 | 1,223.0 | 1,788 | 986.3 | 2,007 | 1,107.6 | 56 % |
| escalation-4B N = 1, trigger 5 % | 248 | 3.2 | 179 | 2.3 | 214 | 2.7 | 6 % |
| escalation-4B N = 1, trigger 10 % | 857 | 11.0 | 620 | 7.9 | 741 | 9.5 | 21 % |
| escalation-4B N = 1, trigger 20 % | 1,476 | 18.9 | 1,145 | 14.7 | 1,314 | 16.8 | 37 % |
| escalation-4B N = 1, trigger 40 % | 2,203 | 28.2 | 1,797 | 23.0 | 2,005 | 25.7 | 56 % |

**Latency setting (ii) measured @25 % load, alarm FPR 5 %, primary configuration**

| policy | pos: invocations / clip-h | pos: GPU-s / clip-h | neg: invocations / clip-h | neg: GPU-s / clip-h | all: invocations / clip-h | all: GPU-s / clip-h | % of always-cloud |
|---|---|---|---|---|---|---|---|
| always-cloud 32B N = 1 | 3,600 | 243.0 | 3,600 | 243.0 | 3,600 | 243.0 | 100 % |
| always-cloud 32B N = 3 | 3,600 | 682.7 | 3,600 | 682.7 | 3,600 | 682.7 | 100 % |
| always-cloud 32B N = 9 | 3,600 | 1,986.4 | 3,600 | 1,986.4 | 3,600 | 1,986.4 | 100 % |
| escalation-32B N = 1, trigger 5 % | 446 | 30.1 | 354 | 23.9 | 401 | 27.1 | 11 % |
| escalation-32B N = 1, trigger 10 % | 853 | 57.5 | 652 | 44.0 | 755 | 50.9 | 21 % |
| escalation-32B N = 1, trigger 20 % | 1,446 | 97.6 | 1,109 | 74.8 | 1,281 | 86.5 | 36 % |
| escalation-32B N = 1, trigger 40 % | 2,243 | 151.4 | 1,851 | 125.0 | 2,052 | 138.5 | 57 % |
| escalation-32B N = 3, trigger 5 % | 481 | 91.2 | 362 | 68.7 | 423 | 80.2 | 12 % |
| escalation-32B N = 3, trigger 10 % | 884 | 167.6 | 653 | 123.8 | 771 | 146.2 | 21 % |
| escalation-32B N = 3, trigger 20 % | 1,461 | 277.1 | 1,115 | 211.4 | 1,292 | 245.1 | 36 % |
| escalation-32B N = 3, trigger 40 % | 2,262 | 428.9 | 1,870 | 354.6 | 2,071 | 392.7 | 58 % |
| escalation-32B N = 9, trigger 5 % | 538 | 296.7 | 441 | 243.5 | 491 | 270.8 | 14 % |
| escalation-32B N = 9, trigger 10 % | 992 | 547.5 | 770 | 425.1 | 884 | 487.8 | 25 % |
| escalation-32B N = 9, trigger 20 % | 1,594 | 879.4 | 1,276 | 704.2 | 1,439 | 794.0 | 40 % |
| escalation-32B N = 9, trigger 40 % | 2,396 | 1,321.9 | 2,044 | 1,127.8 | 2,224 | 1,227.3 | 62 % |
| escalation-4B N = 1, trigger 5 % | 482 | 6.2 | 378 | 4.8 | 431 | 5.5 | 12 % |
| escalation-4B N = 1, trigger 10 % | 937 | 12.0 | 699 | 9.0 | 821 | 10.5 | 23 % |
| escalation-4B N = 1, trigger 20 % | 1,482 | 19.0 | 1,148 | 14.7 | 1,319 | 16.9 | 37 % |
| escalation-4B N = 1, trigger 40 % | 2,214 | 28.4 | 1,844 | 23.6 | 2,034 | 26.1 | 56 % |

**Latency setting (ii) measured @75 % load, alarm FPR 5 %, primary configuration**

| policy | pos: invocations / clip-h | pos: GPU-s / clip-h | neg: invocations / clip-h | neg: GPU-s / clip-h | all: invocations / clip-h | all: GPU-s / clip-h | % of always-cloud |
|---|---|---|---|---|---|---|---|
| always-cloud 32B N = 1 | 3,600 | 243.0 | 3,600 | 243.0 | 3,600 | 243.0 | 100 % |
| always-cloud 32B N = 3 | 3,600 | 682.7 | 3,600 | 682.7 | 3,600 | 682.7 | 100 % |
| always-cloud 32B N = 9 | 3,600 | 1,986.4 | 3,600 | 1,986.4 | 3,600 | 1,986.4 | 100 % |
| escalation-32B N = 1, trigger 5 % | 446 | 30.1 | 354 | 23.9 | 401 | 27.1 | 11 % |
| escalation-32B N = 1, trigger 10 % | 853 | 57.5 | 652 | 44.0 | 755 | 50.9 | 21 % |
| escalation-32B N = 1, trigger 20 % | 1,446 | 97.6 | 1,109 | 74.8 | 1,281 | 86.5 | 36 % |
| escalation-32B N = 1, trigger 40 % | 2,243 | 151.4 | 1,851 | 125.0 | 2,052 | 138.5 | 57 % |
| escalation-32B N = 3, trigger 5 % | 544 | 103.1 | 399 | 75.7 | 473 | 89.7 | 13 % |
| escalation-32B N = 3, trigger 10 % | 948 | 179.8 | 718 | 136.1 | 836 | 158.5 | 23 % |
| escalation-32B N = 3, trigger 20 % | 1,546 | 293.1 | 1,213 | 230.1 | 1,384 | 262.4 | 38 % |
| escalation-32B N = 3, trigger 40 % | 2,355 | 446.6 | 1,958 | 371.3 | 2,161 | 409.9 | 60 % |
| escalation-32B N = 9, trigger 5 % | 595 | 328.3 | 471 | 260.0 | 535 | 295.0 | 15 % |
| escalation-32B N = 9, trigger 10 % | 1,054 | 581.3 | 820 | 452.3 | 940 | 518.4 | 26 % |
| escalation-32B N = 9, trigger 20 % | 1,645 | 907.8 | 1,307 | 721.0 | 1,480 | 816.7 | 41 % |
| escalation-32B N = 9, trigger 40 % | 2,480 | 1,368.4 | 2,122 | 1,171.0 | 2,306 | 1,272.2 | 64 % |
| escalation-4B N = 1, trigger 5 % | 482 | 6.2 | 378 | 4.8 | 431 | 5.5 | 12 % |
| escalation-4B N = 1, trigger 10 % | 937 | 12.0 | 699 | 9.0 | 821 | 10.5 | 23 % |
| escalation-4B N = 1, trigger 20 % | 1,482 | 19.0 | 1,148 | 14.7 | 1,319 | 16.9 | 37 % |
| escalation-4B N = 1, trigger 40 % | 2,214 | 28.4 | 1,844 | 23.6 | 2,034 | 26.1 | 56 % |

Positive and negative clips carry comparable load (5,464 vs 5,196 seconds), and at every cell **positive clips dominate invocations per clip-hour** — they trigger more often and their episodes run longer. The threshold construction is the reason the negative side is so similar between the two resolvers: `tau_alarm` and `tau_dismiss` are quantiles of each model's own negative-second distribution, so both models alarm and fall below dismiss on the same fraction of negative seconds by construction. This was recorded in Step 1 before the sweep.

## 6. Output 4 — episode outcomes

**Latency setting (i) zero, alarm FPR 5 %, trigger 20 %, primary configuration**

| policy | label | episodes | alarm | dismiss | cap | clip-end | invocations / episode | episode length (s, mean) | re-escalations / clip |
|---|---|---|---|---|---|---|---|---|---|
| escalation-32B N = 1 | positive | 818 | 484 | 285 | 22 | 27 | 2.51 | 2.51 | 4.58 |
| escalation-32B N = 1 | negative | 554 | 211 | 305 | 11 | 27 | 2.79 | 2.79 | 2.93 |
| escalation-32B N = 3 | positive | 762 | 324 | 384 | 13 | 41 | 2.76 | 2.76 | 4.21 |
| escalation-32B N = 3 | negative | 554 | 167 | 350 | 9 | 28 | 2.74 | 2.74 | 2.93 |
| escalation-32B N = 9 | positive | 765 | 300 | 421 | 8 | 36 | 2.67 | 2.67 | 4.23 |
| escalation-32B N = 9 | negative | 566 | 158 | 379 | 6 | 23 | 2.67 | 2.67 | 3.01 |
| escalation-4B N = 1 | positive | 668 | 376 | 212 | 32 | 48 | 3.35 | 3.35 | 3.58 |
| escalation-4B N = 1 | negative | 491 | 259 | 180 | 28 | 24 | 3.36 | 3.36 | 2.51 |

| policy | false dismissals on positive clips before the event | first trigger → final resolution (s): mean / p50 / max |
|---|---|---|
| escalation-32B N = 1 | 142 | 21.5 / 22 / 54 |
| escalation-32B N = 3 | 186 | 21.6 / 22 / 54 |
| escalation-32B N = 9 | 206 | 21.5 / 22 / 54 |
| escalation-4B N = 1 | 92 | 21.7 / 23 / 54 |

**Latency setting (ii) measured @25 % load, alarm FPR 5 %, trigger 20 %, primary configuration**

| policy | label | episodes | alarm | dismiss | cap | clip-end | invocations / episode | episode length (s, mean) | re-escalations / clip |
|---|---|---|---|---|---|---|---|---|---|
| escalation-32B N = 1 | positive | 604 | 274 | 261 | 25 | 44 | 3.63 | 3.63 | 3.17 |
| escalation-32B N = 1 | negative | 422 | 121 | 257 | 9 | 35 | 3.79 | 3.79 | 2.05 |
| escalation-32B N = 3 | positive | 578 | 209 | 311 | 13 | 45 | 3.84 | 3.84 | 2.99 |
| escalation-32B N = 3 | negative | 429 | 104 | 286 | 10 | 29 | 3.75 | 3.75 | 2.10 |
| escalation-32B N = 9 | positive | 443 | 122 | 242 | 20 | 59 | 5.46 | 5.46 | 2.09 |
| escalation-32B N = 9 | negative | 343 | 68 | 218 | 12 | 45 | 5.37 | 5.37 | 1.53 |
| escalation-4B N = 1 | positive | 527 | 211 | 235 | 32 | 49 | 4.27 | 4.27 | 2.65 |
| escalation-4B N = 1 | negative | 394 | 142 | 193 | 26 | 33 | 4.21 | 4.21 | 1.87 |

| policy | false dismissals on positive clips before the event | first trigger → final resolution (s): mean / p50 / max |
|---|---|---|
| escalation-32B N = 1 | 120 | 21.2 / 22 / 53 |
| escalation-32B N = 3 | 143 | 21.3 / 22 / 53 |
| escalation-32B N = 9 | 112 | 21.9 / 23 / 53 |
| escalation-4B N = 1 | 103 | 21.2 / 22 / 53 |

A *false dismissal* is an episode on a positive clip that ends in DISMISS or CAP at a second before the annotated event time; the event then happens anyway. *First trigger → final resolution* spans every episode in the clip, so it exceeds `L_max` whenever the clip re-escalates — which it usually does.

## 7. Decision rule 1 — does capability shorten episodes?

> **Pre-registered:** capability shortens episodes if escalation-32B has lower total cloud invocations per clip-hour than escalation-4B at matched `tau_trig` and matched alarm FPR, with a paired clip-bootstrap CI excluding 0, in at least 2 of the 3 alarm FPR levels, under latency setting (ii).

Paired difference, escalation-32B − escalation-4B, invocations per clip-hour over all 300 clips (negative = 32B uses fewer). Clip bootstrap, 2,000 resamples, seed 0. `*` marks a CI excluding 0 on the favourable side.

**(ii) measured @25 % load**

| resolver | alarm FPR | trigger 5 % | trigger 10 % | trigger 20 % | trigger 40 % |
|---|---|---|---|---|---|
| 32B N = 1 | 1 % | -45.3 [-71.8, -17.9]* | -38.5 [-65.8, -12.2]* | +4.1 [-21.8, +30.1] | +42.6 [+20.3, +65.3] |
| 32B N = 1 | 5 % | -30.1 [-55.9, -5.3]* | -66.2 [-95.2, -38.3]* | -37.8 [-64.3, -11.2]* | +18.2 [-2.0, +38.0] |
| 32B N = 1 | 10 % | -10.1 [-29.6, +9.1] | -20.6 [-49.6, +5.8] | -48.0 [-73.0, -23.7]* | -1.0 [-19.7, +18.0] |
| 32B N = 3 | 1 % | -25.3 [-57.1, +7.2] | -11.8 [-43.9, +19.3] | +31.7 [+3.4, +61.8] | +83.4 [+56.6, +110.4] |
| 32B N = 3 | 5 % | -8.1 [-37.2, +23.2] | -50.0 [-80.6, -21.2]* | -26.7 [-50.6, -1.4]* | +37.1 [+15.0, +59.0] |
| 32B N = 3 | 10 % | -5.4 [-24.4, +14.8] | -6.1 [-37.5, +21.3] | -39.8 [-66.2, -14.4]* | +1.4 [-19.6, +22.2] |
| 32B N = 9 | 1 % | +25.0 [-6.4, +58.1] | +88.1 [+55.7, +120.6] | +153.3 [+120.5, +186.7] | +231.0 [+200.0, +262.7] |
| 32B N = 9 | 5 % | +59.4 [+31.4, +89.5] | +63.2 [+32.2, +92.4] | +119.9 [+90.2, +151.3] | +190.5 [+164.2, +218.6] |
| 32B N = 9 | 10 % | +74.6 [+52.2, +97.9] | +110.8 [+81.3, +139.6] | +115.5 [+87.4, +144.9] | +165.5 [+140.2, +191.1] |

Per trigger rate, the count of alarm-FPR levels at which 32B wins with a CI excluding 0:

| resolver | trigger 5 % | trigger 10 % | trigger 20 % | trigger 40 % | rule met at ≥ 2 of 3? |
|---|---|---|---|---|---|
| 32B N = 1 | 2 / 3 | 2 / 3 | 2 / 3 | 0 / 3 | **yes**, at 5 %, 10 %, 20 % |
| 32B N = 3 | 0 / 3 | 1 / 3 | 2 / 3 | 0 / 3 | **yes**, at 20 % |
| 32B N = 9 | 0 / 3 | 0 / 3 | 0 / 3 | 0 / 3 | no |

**(ii) measured @75 % load**

| resolver | alarm FPR | trigger 5 % | trigger 10 % | trigger 20 % | trigger 40 % |
|---|---|---|---|---|---|
| 32B N = 1 | 1 % | -45.3 [-71.8, -17.9]* | -38.5 [-65.8, -12.2]* | +4.1 [-21.8, +30.1] | +42.6 [+20.3, +65.3] |
| 32B N = 1 | 5 % | -30.1 [-55.9, -5.3]* | -66.2 [-95.2, -38.3]* | -37.8 [-64.3, -11.2]* | +18.2 [-2.0, +38.0] |
| 32B N = 1 | 10 % | -10.1 [-29.6, +9.1] | -20.6 [-49.6, +5.8] | -48.0 [-73.0, -23.7]* | -1.0 [-19.7, +18.0] |
| 32B N = 3 | 1 % | +10.8 [-20.9, +44.0] | +41.5 [+7.9, +74.3] | +110.4 [+82.2, +141.6] | +170.5 [+141.2, +201.2] |
| 32B N = 3 | 5 % | +41.9 [+12.9, +74.1] | +14.9 [-16.2, +45.7] | +64.5 [+39.3, +91.8] | +127.7 [+102.3, +154.8] |
| 32B N = 3 | 10 % | +43.9 [+23.1, +66.8] | +63.2 [+31.5, +94.5] | +63.8 [+38.4, +89.3] | +93.2 [+69.9, +116.1] |
| 32B N = 9 | 1 % | +62.8 [+30.1, +96.1] | +137.4 [+103.6, +172.5] | +192.8 [+160.5, +226.8] | +301.9 [+265.0, +337.1] |
| 32B N = 9 | 5 % | +103.3 [+72.1, +135.3] | +118.5 [+85.3, +150.6] | +161.1 [+130.6, +193.6] | +271.9 [+238.1, +306.7] |
| 32B N = 9 | 10 % | +127.7 [+101.3, +155.4] | +179.7 [+144.5, +214.6] | +165.8 [+134.4, +198.5] | +243.2 [+210.9, +274.6] |

Per trigger rate, the count of alarm-FPR levels at which 32B wins with a CI excluding 0:

| resolver | trigger 5 % | trigger 10 % | trigger 20 % | trigger 40 % | rule met at ≥ 2 of 3? |
|---|---|---|---|---|---|
| 32B N = 1 | 2 / 3 | 2 / 3 | 2 / 3 | 0 / 3 | **yes**, at 5 %, 10 %, 20 % |
| 32B N = 3 | 0 / 3 | 0 / 3 | 0 / 3 | 0 / 3 | no |
| 32B N = 9 | 0 / 3 | 0 / 3 | 0 / 3 | 0 / 3 | no |

**Verdict: the rule is MET at N = 1 and only at N = 1.** Under both load levels, 32B N = 1 beats the 4B counterfactual at 2 of 3 alarm-FPR levels at trigger rates 5 %, 10 % and 20 %. At N = 3 the effect survives only at the lighter load, and at N = 9 it reverses with large, decisive CIs on the wrong side. The separation is not about capability — it is that the 32B resolver's end-to-end latency grows from 1 s (N = 1) to 4 s (N = 9 at 75 % load) against a 10 s episode cap, so a larger-N resolver spends most of its episode issuing requests whose answers arrive too late to close it.

Positive and negative clips, separately, at the primary configuration and alarm FPR 5 %:

| resolver | latency | trigger | pos: 32B − 4B / clip-h | neg: 32B − 4B / clip-h | which dominates |
|---|---|---|---|---|---|
| 32B N = 1 | (ii) measured @25 % load | 10 % | -84.3 [-132.2, -40.4] | -47.1 [-88.0, -6.4] | positive |
| 32B N = 1 | (ii) measured @25 % load | 20 % | -36.2 [-76.7, +6.0] | -39.5 [-72.7, -5.6] | negative |
| 32B N = 3 | (ii) measured @25 % load | 10 % | -53.4 [-97.2, -9.1] | -46.4 [-90.0, -9.6] | positive |
| 32B N = 3 | (ii) measured @25 % load | 20 % | -20.4 [-56.4, +16.9] | -33.3 [-66.6, -2.1] | negative |
| 32B N = 9 | (ii) measured @25 % load | 10 % | +55.3 [+7.9, +103.0] | +71.4 [+34.1, +105.3] | negative |
| 32B N = 9 | (ii) measured @25 % load | 20 % | +112.0 [+66.2, +156.4] | +128.2 [+87.2, +170.0] | negative |
| 32B N = 1 | (ii) measured @75 % load | 10 % | -84.3 [-132.2, -40.4] | -47.1 [-88.0, -6.4] | positive |
| 32B N = 1 | (ii) measured @75 % load | 20 % | -36.2 [-76.7, +6.0] | -39.5 [-72.7, -5.6] | negative |
| 32B N = 3 | (ii) measured @75 % load | 10 % | +11.2 [-36.0, +56.6] | +18.7 [-21.2, +53.9] | negative |
| 32B N = 3 | (ii) measured @75 % load | 20 % | +63.9 [+25.2, +103.5] | +65.1 [+29.5, +98.6] | negative |
| 32B N = 9 | (ii) measured @75 % load | 10 % | +116.6 [+63.6, +169.3] | +120.6 [+80.7, +161.3] | negative |
| 32B N = 9 | (ii) measured @75 % load | 20 % | +163.4 [+119.8, +209.4] | +158.7 [+113.6, +205.2] | positive |

## 8. Decision rule 2 — is escalation efficient?

> **Pre-registered:** escalation is efficient if it keeps AP within 0.01 of always-cloud at h ≤ 1 s (CIs overlapping) while using ≤ 50 % of always-cloud's cloud work, at some `tau_trig`.

**Verdict: MET, in 20 of the 108 (latency × N × alarm-FPR × trigger) cells**, under both latency settings. Every cell that satisfies all three conditions:

| latency | resolver | alarm FPR | trigger | AP gap h = 0 | h = 0.5 | h = 1.0 | invocations / clip-h | % of always-cloud | GPU-s / clip-h |
|---|---|---|---|---|---|---|---|---|---|
| (i) zero | 32B N = 9 | 1 % | 20 % | +0.0096 | +0.0050 | -0.0011 | 1,316 | 37 % | 726.0 |
| (i) zero | 32B N = 9 | 10 % | 20 % | +0.0091 | +0.0057 | -0.0031 | 1,115 | 31 % | 615.3 |
| (ii) measured @25 % load | 32B N = 1 | 5 % | 20 % | +0.0094 | +0.0083 | +0.0064 | 1,281 | 36 % | 86.5 |
| (ii) measured @25 % load | 32B N = 3 | 1 % | 5 % | +0.0099 | +0.0083 | +0.0054 | 491 | 14 % | 93.2 |
| (ii) measured @25 % load | 32B N = 3 | 1 % | 10 % | +0.0076 | +0.0070 | +0.0062 | 859 | 24 % | 162.9 |
| (ii) measured @25 % load | 32B N = 3 | 1 % | 20 % | +0.0093 | +0.0073 | +0.0057 | 1,367 | 38 % | 259.3 |
| (ii) measured @25 % load | 32B N = 3 | 5 % | 10 % | +0.0043 | +0.0060 | +0.0058 | 771 | 21 % | 146.2 |
| (ii) measured @25 % load | 32B N = 3 | 5 % | 20 % | +0.0081 | +0.0060 | +0.0048 | 1,292 | 36 % | 245.1 |
| (ii) measured @25 % load | 32B N = 3 | 10 % | 5 % | +0.0098 | +0.0070 | +0.0042 | 380 | 11 % | 72.1 |
| (ii) measured @25 % load | 32B N = 3 | 10 % | 10 % | +0.0062 | +0.0057 | +0.0049 | 723 | 20 % | 137.1 |
| (ii) measured @25 % load | 32B N = 3 | 10 % | 20 % | +0.0093 | +0.0076 | +0.0057 | 1,236 | 34 % | 234.4 |
| (ii) measured @75 % load | 32B N = 1 | 5 % | 20 % | +0.0094 | +0.0083 | +0.0064 | 1,281 | 36 % | 86.5 |
| (ii) measured @75 % load | 32B N = 3 | 1 % | 5 % | -0.0092 | +0.0004 | -0.0022 | 528 | 15 % | 100.0 |
| (ii) measured @75 % load | 32B N = 3 | 1 % | 10 % | -0.0066 | +0.0030 | -0.0010 | 912 | 25 % | 173.0 |
| (ii) measured @75 % load | 32B N = 3 | 1 % | 20 % | -0.0054 | +0.0034 | +0.0011 | 1,446 | 40 % | 274.2 |
| (ii) measured @75 % load | 32B N = 3 | 5 % | 5 % | -0.0097 | -0.0005 | -0.0038 | 473 | 13 % | 89.7 |
| (ii) measured @75 % load | 32B N = 3 | 5 % | 10 % | -0.0088 | +0.0014 | -0.0023 | 836 | 23 % | 158.5 |
| (ii) measured @75 % load | 32B N = 3 | 5 % | 20 % | -0.0072 | +0.0010 | -0.0014 | 1,384 | 38 % | 262.4 |
| (ii) measured @75 % load | 32B N = 3 | 10 % | 10 % | -0.0076 | +0.0026 | -0.0011 | 792 | 22 % | 150.2 |
| (ii) measured @75 % load | 32B N = 3 | 10 % | 20 % | -0.0064 | +0.0020 | +0.0001 | 1,340 | 37 % | 254.1 |

A positive gap means always-cloud is ahead. Several measured-latency cells have **negative** gaps: escalation is *better* than always-cloud there, which satisfies the rule's intent and is itself a consequence of flag 1 — always-cloud at a large N pays its full latency on every second, while escalation spends most seconds on the low-latency device score.

### 8.1 The AP-vs-cloud-work frontier over `tau_trig` (alarm FPR 5 %, primary configuration)

**(i) zero**

| resolver | policy | invocations / clip-h | % of always-cloud | AP h = 0 | AP h = 0.5 | AP h = 1.0 |
|---|---|---|---|---|---|---|
| — | device-only (4B N = 1) | 0 | 0 % | 0.1023 | 0.0624 | 0.0513 |
| 32B N = 1 | escalation, trigger 5 % | 356 | 10 % | 0.1131 | 0.0772 | 0.0546 |
| 32B N = 1 | escalation, trigger 10 % | 688 | 19 % | 0.1222 | 0.0795 | 0.0551 |
| 32B N = 1 | escalation, trigger 20 % | 1,214 | 34 % | 0.1333 | 0.0950 | 0.0638 |
| 32B N = 1 | escalation, trigger 40 % | 2,024 | 56 % | 0.1397 | 0.1013 | 0.0689 |
| 32B N = 1 | always-cloud | 3,600 | 100 % | 0.1473 | 0.1074 | 0.0724 |
| 32B N = 3 | escalation, trigger 5 % | 376 | 10 % | 0.1232 | 0.0879 | 0.0578 |
| 32B N = 3 | escalation, trigger 10 % | 698 | 19 % | 0.1379 | 0.0845 | 0.0585 |
| 32B N = 3 | escalation, trigger 20 % | 1,224 | 34 % | 0.1606 | 0.1017 | 0.0667 |
| 32B N = 3 | escalation, trigger 40 % | 2,026 | 56 % | 0.1693 | 0.1043 | 0.0661 |
| 32B N = 3 | always-cloud | 3,600 | 100 % | 0.1822 | 0.1130 | 0.0667 |
| 32B N = 9 | escalation, trigger 5 % | 356 | 10 % | 0.1214 | 0.0714 | 0.0533 |
| 32B N = 9 | escalation, trigger 10 % | 678 | 19 % | 0.1160 | 0.0686 | 0.0555 |
| 32B N = 9 | escalation, trigger 20 % | 1,199 | 33 % | 0.1355 | 0.0821 | 0.0644 |
| 32B N = 9 | escalation, trigger 40 % | 2,007 | 56 % | 0.1449 | 0.0848 | 0.0614 |
| 32B N = 9 | always-cloud | 3,600 | 100 % | 0.1505 | 0.0876 | 0.0606 |

**(ii) measured @25 % load**

| resolver | policy | invocations / clip-h | % of always-cloud | AP h = 0 | AP h = 0.5 | AP h = 1.0 |
|---|---|---|---|---|---|---|
| — | device-only (4B N = 1) | 0 | 0 % | 0.0528 | 0.0416 | 0.0386 |
| 32B N = 1 | escalation, trigger 5 % | 401 | 11 % | 0.0592 | 0.0410 | 0.0377 |
| 32B N = 1 | escalation, trigger 10 % | 755 | 21 % | 0.0593 | 0.0405 | 0.0371 |
| 32B N = 1 | escalation, trigger 20 % | 1,281 | 36 % | 0.0654 | 0.0411 | 0.0358 |
| 32B N = 1 | escalation, trigger 40 % | 2,052 | 57 % | 0.0634 | 0.0445 | 0.0393 |
| 32B N = 1 | always-cloud | 3,600 | 100 % | 0.0748 | 0.0493 | 0.0423 |
| 32B N = 3 | escalation, trigger 5 % | 423 | 12 % | 0.0573 | 0.0418 | 0.0384 |
| 32B N = 3 | escalation, trigger 10 % | 771 | 21 % | 0.0631 | 0.0438 | 0.0377 |
| 32B N = 3 | escalation, trigger 20 % | 1,292 | 36 % | 0.0593 | 0.0438 | 0.0388 |
| 32B N = 3 | escalation, trigger 40 % | 2,071 | 58 % | 0.0601 | 0.0447 | 0.0404 |
| 32B N = 3 | always-cloud | 3,600 | 100 % | 0.0674 | 0.0497 | 0.0435 |
| 32B N = 9 | escalation, trigger 5 % | 491 | 14 % | 0.0566 | 0.0412 | 0.0394 |
| 32B N = 9 | escalation, trigger 10 % | 884 | 25 % | 0.0549 | 0.0413 | 0.0396 |
| 32B N = 9 | escalation, trigger 20 % | 1,439 | 40 % | 0.0598 | 0.0372 | 0.0344 |
| 32B N = 9 | escalation, trigger 40 % | 2,224 | 62 % | 0.0542 | 0.0386 | 0.0326 |
| 32B N = 9 | always-cloud | 3,600 | 100 % | 0.0391 | 0.0349 | 0.0328 |

**(ii) measured @75 % load**

| resolver | policy | invocations / clip-h | % of always-cloud | AP h = 0 | AP h = 0.5 | AP h = 1.0 |
|---|---|---|---|---|---|---|
| — | device-only (4B N = 1) | 0 | 0 % | 0.0528 | 0.0416 | 0.0386 |
| 32B N = 1 | escalation, trigger 5 % | 401 | 11 % | 0.0592 | 0.0410 | 0.0377 |
| 32B N = 1 | escalation, trigger 10 % | 755 | 21 % | 0.0593 | 0.0405 | 0.0371 |
| 32B N = 1 | escalation, trigger 20 % | 1,281 | 36 % | 0.0654 | 0.0411 | 0.0358 |
| 32B N = 1 | escalation, trigger 40 % | 2,052 | 57 % | 0.0634 | 0.0445 | 0.0393 |
| 32B N = 1 | always-cloud | 3,600 | 100 % | 0.0748 | 0.0493 | 0.0423 |
| 32B N = 3 | escalation, trigger 5 % | 473 | 13 % | 0.0548 | 0.0428 | 0.0404 |
| 32B N = 3 | escalation, trigger 10 % | 836 | 23 % | 0.0538 | 0.0408 | 0.0389 |
| 32B N = 3 | escalation, trigger 20 % | 1,384 | 38 % | 0.0522 | 0.0412 | 0.0380 |
| 32B N = 3 | escalation, trigger 40 % | 2,161 | 60 % | 0.0490 | 0.0407 | 0.0377 |
| 32B N = 3 | always-cloud | 3,600 | 100 % | 0.0451 | 0.0422 | 0.0366 |
| 32B N = 9 | escalation, trigger 5 % | 535 | 15 % | 0.0525 | 0.0405 | 0.0382 |
| 32B N = 9 | escalation, trigger 10 % | 940 | 26 % | 0.0533 | 0.0407 | 0.0372 |
| 32B N = 9 | escalation, trigger 20 % | 1,480 | 41 % | 0.0455 | 0.0353 | 0.0326 |
| 32B N = 9 | escalation, trigger 40 % | 2,306 | 64 % | 0.0431 | 0.0359 | 0.0340 |
| 32B N = 9 | always-cloud | 3,600 | 100 % | 0.0338 | 0.0321 | 0.0321 |

## 9. Negative controls

**(a) Swap the resolver to 4B N = 1.** escalation-32B's code path run with 4B N1 resolver scores, 4B N1 thresholds and 4B N1 cloud latency must equal escalation-4B exactly. Checked in 36 cells (3 latency settings × 3 alarm FPRs × 4 trigger rates, primary configuration): **all equal — PASS**.

**(b) Shuffle the resolver scores across seconds within each clip** (alarm FPR 5 %, trigger 20 %, primary configuration). The marginal distribution is preserved and the within-clip timing is destroyed, so AP at h ≤ 1 s must fall toward the base rate (0.0281).

| resolver | latency | AP h = 0 real → shuffled | h = 0.5 | h = 1.0 |
|---|---|---|---|---|
| 32BI_N1 | (i) zero | 0.1333 → 0.0528 | 0.0950 → 0.0621 | 0.0638 → 0.0538 |
| 32BI_N3 | (i) zero | 0.1606 → 0.0454 | 0.1017 → 0.0552 | 0.0667 → 0.0518 |
| 32BI_N9 | (i) zero | 0.1355 → 0.0410 | 0.0821 → 0.0481 | 0.0644 → 0.0450 |
| 32BI_N1 | (ii) measured @25 % load | 0.0654 → 0.0535 | 0.0411 → 0.0464 | 0.0358 → 0.0464 |
| 32BI_N3 | (ii) measured @25 % load | 0.0593 → 0.0526 | 0.0438 → 0.0405 | 0.0388 → 0.0398 |
| 32BI_N9 | (ii) measured @25 % load | 0.0598 → 0.0552 | 0.0372 → 0.0437 | 0.0344 → 0.0421 |
| 32BI_N1 | (ii) measured @75 % load | 0.0654 → 0.0535 | 0.0411 → 0.0464 | 0.0358 → 0.0464 |
| 32BI_N3 | (ii) measured @75 % load | 0.0522 → 0.0555 | 0.0412 → 0.0425 | 0.0380 → 0.0419 |
| 32BI_N9 | (ii) measured @75 % load | 0.0455 → 0.0534 | 0.0353 → 0.0399 | 0.0326 → 0.0334 |

**PASS under latency setting (i)**: at h = 0 the three resolvers fall from 0.1333 / 0.1606 / 0.1355 to 0.0528 / 0.0454 / 0.0410, i.e. to within 0.02 of the 0.0281 base rate, and the h ≤ 1 s values collapse with them. **Uninformative under setting (ii)**, and stated as such: there the real AP has already fallen to 0.045–0.065 because of the latency shift, so shuffling has almost nothing left to destroy. That is flag 1 showing up in the control, not a failure of the control.

## 10. One instrumented episode trace

Clip `00005.mp4` (positive), event at 20.874 s, duration 40.099 s. Resolver 32BI_N1, latency (ii) measured @25 % load, `d_device` = 1 s, `d_cloud` = 1 s. Thresholds: trigger -7.0009, alarm -4.8826, dismiss -13.25; k = 2, L_max = 10 s, cooldown = 0 s. Total resolver invocations 35, 2.3625 GPU-seconds.

**Episodes in this clip:**

| # | opened at t | closed at t | outcome | invocations | closed before the event? |
|---|---|---|---|---|---|
| 1 | 4 | 5 | **alarm** | 2 | yes |
| 2 | 6 | 7 | **alarm** | 2 | yes |
| 3 | 8 | 9 | **alarm** | 2 | yes |
| 4 | 11 | 20 | **cap** | 10 | yes |
| 5 | 22 | 23 | **alarm** | 2 | no |
| 6 | 24 | 25 | **alarm** | 2 | no |
| 7 | 26 | 27 | **alarm** | 2 | no |
| 8 | 28 | 29 | **alarm** | 2 | no |
| 9 | 30 | 31 | **alarm** | 2 | no |
| 10 | 32 | 33 | **alarm** | 2 | no |
| 11 | 34 | 35 | **alarm** | 2 | no |
| 12 | 36 | 37 | **alarm** | 2 | no |
| 13 | 38 | 39 | **alarm** | 2 | no |
| 14 | 40 | 40 | **clip_end** | 1 | no |

**Per second** (device frame-second / resolver frame-second show which second's frames the score came from, after the latency shift):

| t | t − event (s) | episode open | device score seen (from second) | resolver score seen (from second) | stream score | source |
|---|---|---|---|---|---|---|
| 3 | -17.874 | no | — | — | — | none |
| 4 | -16.874 | yes | -3.288 (3) | — | -3.288 | device |
| 5 | -15.874 | yes | -6.751 (4) | -0.974 (4) | -0.974 | resolver |
| 6 | -14.874 | yes | -3.773 (5) | — | -3.773 | device |
| 7 | -13.874 | yes | -6.252 (6) | -3.896 (6) | -3.896 | resolver |
| 8 | -12.874 | yes | -5.504 (7) | — | -5.504 | device |
| 9 | -11.874 | yes | -5.753 (8) | -0.826 (8) | -0.826 | resolver |
| 10 | -10.874 | no | -8.000 (9) | — | -8.000 | device |
| 11 | -9.874 | yes | -6.252 (10) | — | -6.252 | device |
| 12 | -8.874 | yes | -8.500 (11) | -14.125 (11) | -14.125 | resolver |
| 13 | -7.874 | yes | -6.751 (12) | -8.250 (12) | -8.250 | resolver |
| 14 | -6.874 | yes | -7.750 (13) | -12.000 (13) | -12.000 | resolver |
| 15 | -5.874 | yes | -10.500 (14) | -9.625 (14) | -9.625 | resolver |
| 16 | -4.874 | yes | -6.252 (15) | -12.000 (15) | -12.000 | resolver |
| 17 | -3.874 | yes | -9.250 (16) | -15.250 (16) | -15.250 | resolver |
| 18 | -2.874 | yes | -8.750 (17) | -9.625 (17) | -9.625 | resolver |
| 19 | -1.874 | yes | -12.250 (18) | -16.375 (18) | -16.375 | resolver |
| 20 | -0.874 | yes | -6.252 (19) | -9.875 (19) | -9.875 | resolver |
| 21 | +0.126 | no | -10.750 (20) | — | -10.750 | device |
| 22 | +1.126 | yes | -6.502 (21) | — | -6.502 | device |
| 23 | +2.126 | yes | -4.018 (22) | -0.127 (22) | -0.127 | resolver |
| 24 | +3.126 | yes | -4.264 (23) | — | -4.264 | device |
| 25 | +4.126 | yes | -4.264 (24) | -4.759 (24) | -4.759 | resolver |
| 26 | +5.126 | yes | -4.759 (25) | — | -4.759 | device |
| 27 | +6.126 | yes | -2.127 (26) | -2.018 (26) | -2.018 | resolver |
| 28 | +7.126 | yes | -5.255 (27) | — | -5.255 | device |
| 29 | +8.126 | yes | -6.751 (28) | -0.974 (28) | -0.974 | resolver |
| 30 | +9.126 | yes | -5.504 (29) | — | -5.504 | device |
| 31 | +10.126 | yes | -5.255 (30) | -0.576 (30) | -0.576 | resolver |
| 32 | +11.126 | yes | -4.264 (31) | — | -4.264 | device |
| 33 | +12.126 | yes | -4.264 (32) | -0.313 (32) | -0.313 | resolver |
| 34 | +13.126 | yes | -1.313 (33) | — | -1.313 | device |
| 35 | +14.126 | yes | -4.511 (34) | -0.693 (34) | -0.693 | resolver |
| 36 | +15.126 | yes | -5.255 (35) | — | -5.255 | device |
| 37 | +16.126 | yes | -2.350 (36) | -0.387 (36) | -0.387 | resolver |
| 38 | +17.126 | yes | -5.007 (37) | — | -5.007 | device |
| 39 | +18.126 | yes | -4.264 (38) | -1.406 (38) | -1.406 | resolver |
| 40 | +19.126 | yes | -5.007 (39) | — | -5.007 | device |

Every row is checkable by hand: a trigger fires when the device score seen is ≥ the trigger threshold; the resolver's first result arrives `d_cloud` seconds after the episode opens; the stream carries the resolver's score whenever one is available and the device's otherwise; and the episode closes on the first resolver score ≥ alarm, or after k consecutive scores < dismiss, or at the cap.

## 11. Sensitivities: k, dismiss quantile, L_max and cooldown

Escalation-32B N = 1, latency setting (ii) @25 %, alarm FPR 5 %, trigger 20 %. The primary configuration (k = 2, q = 0.75, L_max = 10, c = 0) is marked.

| dismiss q | k | L_max | cooldown | invocations / clip-h | episodes | invocations / episode | false dismissals | positives alarmed | false alarms / clip-h |
|---|---|---|---|---|---|---|---|---|---|
| 50 % | 1 | 5 s | 0 s | 1,226.9 | 1102 | 3.30 | 139 | 0.527 | 81.8 |
| 50 % | 1 | 5 s | 2 s | 923.0 | 800 | 3.42 | 117 | 0.487 | 57.5 |
| 50 % | 1 | 10 s | 0 s | 1,326.5 | 972 | 4.04 | 92 | 0.527 | 84.5 |
| 50 % | 1 | 10 s | 2 s | 1,057.7 | 730 | 4.29 | 78 | 0.507 | 61.7 |
| 50 % | 1 | 20 s | 0 s | 1,357.3 | 918 | 4.38 | 78 | 0.533 | 88.0 |
| 50 % | 1 | 20 s | 2 s | 1,108.0 | 695 | 4.72 | 66 | 0.520 | 65.8 |
| 50 % | 2 | 5 s | 0 s | 1,292.4 | 1033 | 3.70 | 122 | 0.527 | 81.1 |
| 50 % | 2 | 5 s | 2 s | 985.1 | 771 | 3.78 | 107 | 0.493 | 58.2 |
| 50 % | 2 | 10 s | 0 s | 1,440.7 | 871 | 4.90 | 68 | 0.540 | 87.3 |
| 50 % | 2 | 10 s | 2 s | 1,167.1 | 671 | 5.15 | 61 | 0.527 | 65.1 |
| 50 % | 2 | 20 s | 0 s | 1,508.6 | 796 | 5.61 | 45 | 0.567 | 90.8 |
| 50 % | 2 | 20 s | 2 s | 1,264.4 | 624 | 6.00 | 40 | 0.553 | 67.9 |
| 50 % | 3 | 5 s | 0 s | 1,327.2 | 1019 | 3.86 | 119 | 0.527 | 83.8 |
| 50 % | 3 | 5 s | 2 s | 1,012.8 | 759 | 3.95 | 103 | 0.500 | 60.3 |
| 50 % | 3 | 10 s | 0 s | 1,491.7 | 831 | 5.32 | 53 | 0.553 | 90.8 |
| 50 % | 3 | 10 s | 2 s | 1,224.5 | 641 | 5.66 | 49 | 0.533 | 67.2 |
| 50 % | 3 | 20 s | 0 s | 1,597.4 | 734 | 6.44 | 19 | 0.587 | 94.2 |
| 50 % | 3 | 20 s | 2 s | 1,364.7 | 574 | 7.04 | 16 | 0.587 | 70.7 |
| 75 % | 1 | 5 s | 0 s | 1,120.2 | 1283 | 2.59 | 202 | 0.513 | 77.6 |
| 75 % | 1 | 5 s | 2 s | 790.9 | 886 | 2.64 | 150 | 0.460 | 50.6 |
| 75 % | 1 | 10 s | 0 s | 1,136.7 | 1236 | 2.72 | 186 | 0.513 | 80.4 |
| 75 % | 1 | 10 s | 2 s | 824.7 | 863 | 2.83 | 134 | 0.480 | 54.7 |
| 75 % | 1 | 20 s | 0 s | 1,138.1 | 1231 | 2.74 | 185 | 0.513 | 81.1 |
| 75 % | 1 | 20 s | 2 s | 828.4 | 858 | 2.86 | 133 | 0.480 | 55.4 |
| 75 % | 2 | 5 s | 0 s | 1,227.2 | 1105 | 3.29 | 146 | 0.533 | 80.4 |
| 75 % | 2 | 5 s | 2 s | 925.7 | 811 | 3.38 | 121 | 0.480 | 55.4 |
| 75 % | 2 | 10 s | 0 s **(primary)** | 1,281.3 | 1026 | 3.70 | 120 | 0.527 | 83.8 |
| 75 % | 2 | 10 s | 2 s | 998.6 | 764 | 3.87 | 94 | 0.500 | 58.9 |
| 75 % | 2 | 20 s | 0 s | 1,288.7 | 1006 | 3.79 | 117 | 0.533 | 85.2 |
| 75 % | 2 | 20 s | 2 s | 1,015.5 | 754 | 3.99 | 92 | 0.507 | 61.0 |
| 75 % | 3 | 5 s | 0 s | 1,298.5 | 1037 | 3.71 | 127 | 0.527 | 83.1 |
| 75 % | 3 | 5 s | 2 s | 989.2 | 772 | 3.79 | 109 | 0.493 | 58.9 |
| 75 % | 3 | 10 s | 0 s | 1,385.3 | 926 | 4.43 | 87 | 0.540 | 89.4 |
| 75 % | 3 | 10 s | 2 s | 1,102.0 | 704 | 4.63 | 71 | 0.520 | 63.0 |
| 75 % | 3 | 20 s | 0 s | 1,404.2 | 888 | 4.68 | 75 | 0.547 | 90.8 |
| 75 % | 3 | 20 s | 2 s | 1,136.7 | 682 | 4.94 | 61 | 0.547 | 64.4 |

The cooldown is the single most effective load knob here: `c = 2 s` cuts invocations per clip-hour by about 22 % at every (q, k, L_max) while costing 2–5 pp of positives alarmed. Raising `k` and `L_max` trades cloud work against false dismissals in the expected direction, and the dismiss quantile moves both at once — `q = 75 %` dismisses more eagerly, so it halves invocations per episode and roughly doubles false dismissals.

## 12. Labelled secondary: 4B N = 3 as the device arm

> LABELLED SECONDARY. The Jetson Orin cannot sustain 4B N=3 at 1 Hz (StudyD4-orin: N=3 total latency p99 1.448 s, so its registered cadence is 2 s). These rows replay the arm at 1 Hz anyway, which is counterfactual, and charge StudyD4-orin's measured N=3 total p50 of 1.394 s as the device latency. They are not used for any decision rule.

| latency | d_device | AP h = 0 | h = 0.5 | h = 1.0 | h = 1.5 | h = 2.0 | positives alarmed | false alarms / clip-h |
|---|---|---|---|---|---|---|---|---|
| (i) zero | 0 s | 0.1413 [0.096, 0.201] | 0.0792 [0.058, 0.120] | 0.0537 [0.042, 0.073] | 0.0402 [0.033, 0.055] | 0.0378 [0.032, 0.046] | 0.560 | 124.0 |
| (ii) measured @25 % load | 2 s | 0.0398 [0.034, 0.049] | 0.0387 [0.033, 0.048] | 0.0337 [0.029, 0.041] | 0.0326 [0.028, 0.039] | 0.0314 [0.027, 0.038] | 0.540 | 113.6 |
| (ii) measured @75 % load | 2 s | 0.0398 [0.034, 0.049] | 0.0387 [0.033, 0.048] | 0.0337 [0.029, 0.041] | 0.0326 [0.028, 0.039] | 0.0314 [0.027, 0.038] | 0.540 | 113.6 |

With zero latency this arm would be a better device than 4B N = 1 (AP 0.1413 vs 0.1023 at h = 0). With its own measured latency it is **worse** (0.0398 vs 0.0528), because 1.394 s of device compute costs two whole seconds of horizon. Combined with the fact that the Orin cannot run it at 1 Hz at all, a richer device window is not a free improvement on this workload.

## 13. Results consistency check (CLAUDE.md, 6 checks)

**1. Cross-check against committed measurements.** The required cross-check is that always-cloud and device-only reproduce StudyE5 Part G, which they must, because at zero latency those two policies *are* the Part G arms.

| arm | horizon | this run (zero latency) | StudyE5 Part G | ratio | agree |
|---|---|---|---|---|---|
| `4BI_N1` | h = 0.0 | 0.1023 | 0.102 | 1.003 | agree |
| `4BI_N1` | h = 0.5 | 0.0624 | 0.062 | 1.006 | agree |
| `4BI_N1` | h = 1.0 | 0.0513 | 0.051 | 1.005 | agree |
| `4BI_N1` | h = 1.5 | 0.0401 | 0.040 | 1.002 | agree |
| `4BI_N1` | h = 2.0 | 0.0374 | 0.037 | 1.011 | agree |
| `32BI_N1` | h = 0.0 | 0.1473 | 0.147 | 1.002 | agree |
| `32BI_N1` | h = 0.5 | 0.1074 | 0.107 | 1.004 | agree |
| `32BI_N1` | h = 1.0 | 0.0724 | 0.072 | 1.005 | agree |
| `32BI_N1` | h = 1.5 | 0.0476 | 0.048 | 0.991 | agree |
| `32BI_N1` | h = 2.0 | 0.0411 | 0.041 | 1.003 | agree |
| `32BI_N3` | h = 0.0 | 0.1822 | 0.182 | 1.001 | agree |
| `32BI_N3` | h = 0.5 | 0.1130 | 0.113 | 1.000 | agree |
| `32BI_N3` | h = 1.0 | 0.0667 | 0.067 | 0.995 | agree |
| `32BI_N3` | h = 1.5 | 0.0485 | 0.048 | 1.010 | agree |
| `32BI_N3` | h = 2.0 | 0.0428 | 0.043 | 0.994 | agree |
| `32BI_N9` | h = 0.0 | 0.1505 | 0.150 | 1.003 | agree |
| `32BI_N9` | h = 0.5 | 0.0876 | 0.088 | 0.995 | agree |
| `32BI_N9` | h = 1.0 | 0.0606 | 0.061 | 0.993 | agree |
| `32BI_N9` | h = 1.5 | 0.0455 | 0.045 | 1.010 | agree |
| `32BI_N9` | h = 2.0 | 0.0398 | 0.040 | 0.994 | agree |

**PASS, and unusually strong: all 20 values reproduce StudyE5 Part G to the published three decimals.** The alarm-FPR column does not enter AP (AP is computed on the continuous score), so these rows are identical at every FPR level. Nothing in this study is within 2× of a disagreement.

| other quantity | this run | prior committed | source | ratio |
|---|---|---|---|---|
| negative decision seconds | 5,196 | 5,196 | StudyD14 / StudyE5 Part G | 1.000 |
| base rate | 0.0281 | 0.028 | StudyE5 Part G | 1.002 |
| prompt tokens N = 1 / 3 / 9 | 378 / 1,062 / 3,090 | 378 / 1,062 / 3,090 | StudyD3 / D4 / D14 | 1.000 |
| 32B saturated prefill | 5,600 tok/s | ~5.6k–5.7k tok/s | StudyD7 §check 2, StudyD7b | 1.000 |
| 4B saturated prefill | 29,500 tok/s | ~29.5k–31.7k tok/s | StudyD7b, StudyD7 | 1.000 |
| device N = 1 total latency | 0.567 s | 0.567 s (arm A p50) | StudyD8 | 1.000 |

**2. Physical plausibility.** Every latency is a committed measurement or a sum of committed measurements; none is computed from a curve. The upload term is arithmetic: 354,902 B at 13.6 Mbit/s is 0.209 s, 3,188,243 B is 1.875 s. GPU-seconds use the saturated prefill rates measured under load, not single-request rates, so they are the conservative (larger-throughput) choice: at N = 1 one invocation is 378 / 5,600 = 0.0675 GPU-s on 32B. Always-cloud's 3,600 invocations per clip-hour is 1 Hz by definition, and at N = 9 that is 1,987 GPU-s per clip-hour, i.e. **0.55 of a full H100 per stream** — consistent with StudyD7's finding that 32B N = 9 supports about 1.8 req/s at peak. **PASS.**

**3. Distribution sanity.** Every AP carries a 2,000-resample clip-bootstrap CI; alarm times are reported as p25 / p50 / p75; episode outcomes are reported as four separate counts rather than a single rate; the sensitivity table shows the full 36-cell grid rather than a summary. The one place a constant legitimately appears is always-cloud's invocation count, which is 1 Hz by construction. **PASS.**

**4. Definition audit.**

| object | definition used here | matches prior? |
|---|---|---|
| score | log P(Yes), P(Yes) = Yes/(Yes+No) first-token mass, floored at 1e-12 | StudyD3 / D14, unchanged |
| AP at horizon h | positives = stream value at the whole second nearest event − h clamped to the grid; negatives = all 5,196 negative seconds | StudyE5 Part G, unchanged |
| alarm | an up-crossing of `tau_alarm` (baselines) or an episode ending in ALARM (escalation) | new to this study, stated |
| false alarm | an alarm event on a negative clip | new to this study, stated |
| false dismissal | an episode on a positive clip ending in DISMISS or CAP before the event second | new to this study, stated |
| resolver invocation | one request per wall second the episode is open, including requests whose answer arrives after it closes | new to this study, stated |
| GPU-second | invocations × prompt tokens / saturated prefill rate | StudyD7's rate, applied as the brief specifies |
| cloud latency | RTT + upload of N PNG frames at 13.6 Mbit/s + open-loop server TTFT p50 | assembled from StudyD4 / D7 / D7b |
| d | ceil(latency), in whole seconds | new to this study, stated |

**PASS**, with one name carrying two meanings across the literature and disambiguated here: StudyD14's *raw Yes per hour* counts P(Yes) > 0.5 seconds and is explicitly **not** a tuned false-alarm rate; this study never uses it, and its `tau_alarm` is a fitted quantile.

**5. Claim linkage.** The results bear on FORMULATION §Decisions (`p_i`, which node serves the session, decided online), §Constraints 2 (serving feasibility within the latency SLO) and §Objective (handoff latency as the binding term; cloud work reported as an explanatory metric, not folded into the objective). They **support** the claim that placement must be decided against a deadline rather than on capability alone: the 32B advantage StudyE5 Part G measured survives only at N = 1, and is erased at N = 9 by that arm's own latency. They **do not** speak to the coupling claim (§The coupling claim), which concerns fidelity and placement failing to decompose across a fleet; this is a single-stream study. **Scope note:** FORMULATION §Scoping assumes one model per deployment and this study runs 4B on the device and 32B in the cloud — the scoped-to-discussion heterogeneous case. No cross-tier KV transfer is modelled (the payload is PNG frames), so §Scoping's KV-portability exclusion is respected. **PASS with the scope note.**

**6. Proxy validity.**

| proxy | what it actually measures | valid for the claim? |
|---|---|---|
| device 4B N = 1 *accuracy* = the H100 4B N = 1 score | the cloud 4B's answer on byte-identical frames, not the Orin's | **flagged**. StudyF4 measured 97.2–98.1 % per-question agreement between Orin llama.cpp and H100 vLLM 4B on byte-identical frames in a different task, which is the best evidence available; it has **not** been measured on Nexar. Every device number in this study inherits that uncertainty |
| device *latency* = StudyD8 arm A (0.567 s) | the Orin's sustained 1 Hz N = 1 total latency on the DEV-RECENT payload (~443–468 tokens), not Nexar SMALL N = 1 (378 tokens) | **flagged**, and conservative: the proxy payload is ~20 % longer, so the real Nexar latency would be slightly lower. It would not change `d_device` = 1 s |
| 13.6 Mbit/s fixed uplink | a single rate with no variability and no outages | stated; uplink variation is not modelled anywhere in this study |
| negative clips as event-free driving | 1.44 h of short clips (≤ 58 s) | the per-clip-hour rates are extrapolated from 1.44 h, as StudyD14 already flagged. They are comparable **between** policies, which is what every decision rule needs, but they are not absolute deployment rates |
| `time_of_event` | Nexar's annotation | taken as ground truth, as in StudyD3 / D14 / E5 |

The first row is the one that matters: **the device arm's accuracy is a cloud measurement**. It is marked unvalidated on this dataset and carried into every conclusion below.

**Seconds with no score available.** Under latency setting (ii) the first `d` seconds of each clip carry no score and are ranked below every observed value. No positive clip's target second at any horizon falls in that window (0 of 750 checked at every d from 0 to 4), so AP's positive side is unaffected; on the negative side it removes `d` × 150 seconds from contention (150 of 5,196 at d = 1, 600 at d = 4), which mildly favours the larger-`d` arms. The effect is identical for device-only, always-cloud and escalation at the same `d`, so within-setting comparisons are fair; comparisons **across** N under setting (ii) carry it and are flagged here rather than corrected.

## 14. Observations (data only, no interpretation)

1. Zero-latency AP reproduces StudyE5 Part G exactly for all five arms at all five horizons.
2. Under latency setting (ii) every arm's AP at h = 0 falls to approximately its own zero-latency value at h = d: always-cloud 32B N = 1 0.1473 → 0.0748 (zero-latency h = 1 is 0.0724).
3. Under latency setting (ii), always-cloud 32B N = 9 scores 0.0391 at h = 0, **below** device-only's 0.0528.
4. Decision rule 1 is met at N = 1 at trigger rates 5 %, 10 % and 20 % under both load levels; it is not met at N = 9 at any cell, where the sign reverses with CIs excluding 0.
5. Decision rule 2 is met in 20 of 108 cells, under both latency settings; the cheapest is 11 % of always-cloud's cloud work.
6. At N = 1, measured @25 %, 5 % FPR, 20 % trigger, escalation-32B issues 1,281 invocations per clip-hour against always-cloud's 3,600 and escalation-4B's 1,319.
7. At the same cell, 120 episodes on positive clips are dismissed before the event, and positive clips re-escalate 3.17 times each.
8. Negative control (a) passes exactly in 36 of 36 cells. Negative control (b) passes under setting (i) and is uninformative under setting (ii).
9. The cooldown `c = 2 s` reduces invocations per clip-hour by about 22 % at every (q, k, L_max) combination tested.
10. The 4B N = 3 secondary device arm is better than 4B N = 1 with zero latency (0.1413 vs 0.1023 at h = 0) and worse with its own measured latency (0.0398 vs 0.0528).

## 15. Interpretation (inference, labelled as such)

- **The study's first question gets a qualified yes.** Capability does shorten episodes and does reduce cloud work — but only when the capable model is also the *fast* one. At N = 1 the 32B resolver reaches a decision sooner than the 4B counterfactual at matched trigger and alarm rates, and the paired CIs exclude zero at two of three FPR levels at three of four trigger rates. At N = 9 the same model, given nine times the evidence, loses decisively on the same metric. The capability that StudyE5 Part G measured is real and it survives into this design; what does not survive is the assumption that more evidence is free.
- **The second question gets a clear yes, and the answer is cheap.** Escalation keeps always-cloud's AP to within 0.01 at every horizon ≤ 1 s for 11–40 % of its cloud work, in 20 pre-specified cells. On this workload a device-triggered design is a good trade: most seconds are uninteresting, and a 4B trigger finds the interesting ones well enough that running 32B on all of them buys very little.
- **Latency, not capability, is the governing variable in this design, and it acts like a horizon.** A score that takes `d` seconds to produce is a score about `d` seconds ago, so a policy with `d` seconds of latency competing at horizon h is really competing at horizon h + d. That single fact explains the N = 9 reversal, the collapse of negative control (b) under setting (ii), and why the secondary 4B N = 3 device arm is worse than 4B N = 1 despite being a better model on the same frames. It is also why the two decision rules disagree about N.
- **Re-escalation is where the design actually spends its budget.** The cap is 10 s, but the median first-trigger-to-final-resolution span is about 22 s, because a clip typically opens two to three episodes. Any accounting that charges one episode per alarm understates cloud work by roughly a factor of three on this data, which is exactly why the pre-registration required re-escalations to be included.
- **The false-dismissal rate is the uncomfortable number.** At the primary configuration between 112 and 143 episodes on 150 positive clips are dismissed before the event happens. That is not a failure of escalation specifically — the same thresholds dismiss on negative clips at the rate they were fitted for — but it says the dismiss rule as specified is too eager for a safety application, and the k / L_max / dismiss-quantile sensitivity table shows the price of fixing it (k = 3, L_max = 20 s, q = 50 % cuts false dismissals to 19 for +24 % cloud work).
- **What this does not show.** It does not show that 32B notices any individual crash earlier: the horizon shift in §3.1 is a property of two AP curves, and StudyE5's within-clip analysis found no earliness advantage. It does not establish the device arm's accuracy — that is a cloud measurement standing in for an Orin run that has not been done on Nexar. And it is a single-stream study: nothing here speaks to what happens when many devices escalate at once, which is StudyD7's and StudyRH8's territory.

**CLAUDE.md Rule 2.** Both pre-registered rules returned a positive finding, so no null classification is required. The one component that behaves like a null — negative control (b) under latency setting (ii) — is **inconclusive, not a real negative**: the mechanism it tests (within-clip timing information in the resolver's score) was already removed by the latency shift before the control was applied, so the control had nothing to disable. It is reported as uninformative there and passing under setting (i), where the mechanism is present.

## 16. Files

- `experiments/dashcam/study_e9_episodes.py`
- `experiments/dashcam/study_e9_report.py`
- `results/dashcam/study_e9/e9_results.json`
- `results/dashcam/study_e9/e9_mechanism_verification.md`
- `reports/study_e9_episodes.md (this file)`

