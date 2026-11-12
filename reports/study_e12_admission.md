# StudyE12-admission — which device-triggered escalations to admit when the cloud can only take a fraction

**OFFLINE ANALYSIS OF COMMITTED RESULTS.** CPU only on the flash host: no GPU was used, no model server was started, and no inference was run. Every score is read from StudyD14's committed trace; every latency and byte count is read from a committed StudyD4 / StudyD7 / StudyD7b / StudyD8 measurement, through `experiments/dashcam/study_e9_episodes.py`.

**E-id:** `StudyE12-admission`, pre-registered in `research/EXPERIMENTS.md` on 2026-11-11 (later) **before any number in this report was computed** (user-authorized row).  
**Scripts:** `experiments/dashcam/study_e12_admission.py`, `experiments/dashcam/study_e12_report.py` (this file).  
**Results:** `results/dashcam/study_e12/e12_results.json`, `e12_mechanism_verification.md`.  
**Metric rule (fixed, never varied):** predictive quality is the Nexar metric — AP at h = 0 / 0.5 / 1 / 1.5 / 2 s on the **continuous** score (log P(Yes)), exactly as StudyE5 Part G and StudyE9. **No literal Yes/No answer is used anywhere**; alarm, dismiss and trigger are thresholds on the continuous score. The per-episode utility defined in §3 is a **training target for the admission ranking only** and is never an evaluation metric.  
**No INVALID result is used.**

## Prominent flags (read first)

1. **The trajectory predictor works on the training target and still does not move the metric.** Cross-fitted AUROC for *benefit > 0* is 0.667–0.734 at 32B N = 1, so the device's own score trajectory genuinely predicts which escalations are worth a slot. The pre-registered decision rule is nonetheless **not met** (§8): at h = 0.5 s no paired CI against P-score excludes 0 at two of three budgets for either resolver.
2. **The stronger pre-registered null fires too: on AP, admission *ranking* has no signal on this workload.** P-score beats P-random with a paired CI excluding 0 in only **1 of 6** resolver × budget cells — every point estimate favours P-score (+0.0006 to +0.0060 at h = 0) and none separates. Per the pre-registration that is the reading to state plainly: *which* escalations are admitted does not move AP. The alarm behaviour is a different matter — flag 8.
3. **At h = 0.5 s the two endpoints are indistinguishable, but selection can still beat both — so the rule was not asking for the impossible.** Admitting every escalation scores 0.0411 against 0.0416 for admitting none (escalation is marginally *behind* there in the committed StudyE9 numbers, flagged in Step 2 before the sweep), yet `P-oracle` at a quarter budget reaches 0.0461 — above both. Admission is a selection problem, not an interpolation between the endpoints.
4. **Where admission does pay is cloud work, not AP.** At B = 0.5 with 32B N = 1, P-score reaches 0.0578 AP at h = 0 — 39 % of the way from admit-none to admit-all — for 43 % of admit-all's GPU-seconds.
5. **The oracle shows the headroom is real but small.** P-oracle at B = 0.5 scores 0.0477 at h = 0.5 s against P-score's 0.0420 — a gap of +0.0057 that a budget-respecting oracle could win. Neither causal policy captures any of it: the better of `P-trajectory` and `P-trajectory-work` takes +0.0000 of it. So the headroom exists and is not reachable from the device's own trajectory.
6. **Both negative controls pass.** (a) At budget 1.0 all seven policies equal admit-all exactly in 168 checked cells. (b) Shuffling the features across triggers inside each fold moves P-trajectory to P-random's level (§11).
7. **The one large, repeatable selection effect is on alarms, not on AP.** At B = 0.50 with 32B N = 1, P-score raises 79.7 false alarms per clip-hour against P-random's 115.6 at the same budget, and alarms on 0.467 of positive clips against 0.558. AP is computed on the continuous score stream, not on the alarm decisions, so it does not see this.
8. **admit-all and admit-none reproduce StudyE9 exactly** — AP to the last bit at every horizon, invocations, positives alarmed and false alarms per clip-hour (§13 check 1). The one difference is admit-none's *alarm count*, and it is structural, not numerical: §13 explains it.

## 1. Setup

**Data.** StudyD14's committed trace, 150 positive and 150 negative Nexar VALIDATION clips, 5,464 positive and 5,196 negative clip-seconds per arm. Base rate 0.0281. Device arm **4BI N = 1** (the Orin sustains N = 1 at 1 Hz, StudyD8 arm A). Resolver **32B at N = 1 and N = 3**, both reported.

**Episode rules.** StudyE9's primary configuration, unchanged: k = 2, dismiss quantile 75 %, L_max = 10 s, cooldown 0 s; thresholds fitted by 2-fold cross-fitting by clip, stratified by label, seed 0, on the training fold's negative seconds only. Alarm FPR 5 % primary (1 % and 10 % secondary); trigger rate 20 % primary (10 % secondary); latency setting (ii) at 25 % load primary, (i) zero secondary.

**Admission.** Every trigger that would open an episode is either

- **admitted** — the 32B resolver scores each following second, exactly as StudyE9's `escalation-32B`; or
- **kept local** — the device's own 4B score continues inside the episode and alarms on the device's own `tau_alarm`, with **zero** cloud invocations.

**Budget.** B is the fraction of triggers admitted, enforced **per fold by a ranking-score cutoff fitted on training clips** to admit B of training triggers. The realized fraction on test clips is reported in every table. Because the benefit label is discrete — mostly exactly 0 — a plain quantile cutoff admits every trigger at or above 0 and the budget is *not* enforced for P-oracle; a deterministic per-(clip, second) tiebreak (CRC32 of `seed|clip|second`, magnitude 1e-09) is therefore added to every ranking score, identically when the cutoff is fitted and when the decision is made. This was found by inspecting the realized fractions, and it is the only change to the pre-registered procedure.

**Why a trigger's label does not depend on the policy.** The admitted and local paths are rolled out **in isolation from the trigger second**, so a trigger's benefit and work labels are properties of that trigger alone. Were they measured along a whole-clip trajectory they would depend on the admission decisions taken at earlier triggers, and the label would no longer be well defined. Triggers are enumerated along the admit-all trajectory for fitting; a trigger that only some policies reach is labelled on demand by the same isolated rollout.

## 2. Mechanism verification (CLAUDE.md Steps 1–5)

Recorded in `results/dashcam/study_e12/e12_mechanism_verification.md` **before the sweep ran** and reproduced here in full.

>
> **Recorded 2026-11-11 (later), BEFORE the StudyE12 sweep ran.** Every quantity below is read from
> StudyD14's committed trace or from StudyE9's committed results; none comes from a StudyE12 policy
> run. Offline analysis of committed results; CPU only on the flash host; no GPU, no model server,
> no inference. Scores are continuous log P(Yes) throughout; no literal Yes/No answer is used
> anywhere.
>
> ## Step 1 — the causal chain
>
> FORMULATION §Constraints 2 (*serving feasibility*: the serving node must answer within the latency
> SLO) and §Decisions (`p_i`, which node serves a session, decided online) give the chain this
> experiment tests. When the cloud can absorb only a fraction B of device-triggered escalations, the
> placement decision stops being per-session and becomes a **selection** problem: the device must
> decide, at the trigger second and from information it already has, which triggers are worth the
> scarce resolver slot. The chain is:
>
> *If* a device-triggered escalation's value varies across triggers — that is, if the gain from
> replacing the device's own score stream with the 32B resolver's is larger for some triggers than
> for others — *and if* that variation is visible in the device's own score trajectory before the
> escalation is issued, *then* a ranking function over trajectory features admits a higher-value
> subset than ranking by the instantaneous device score, and at a fixed budget the application's
> AP rises. Two things can break the chain independently: the value may not vary (every trigger
> equally worth escalating, so any ranking is as good as any other), or it may vary but be invisible
> at the trigger second (the variation is driven by what the resolver sees afterwards, which no
> causal predictor can know).
>
> The counter-chain this experiment must leave room for is that the **instantaneous device score is
> already a sufficient statistic** for whatever signal the trajectory carries, in which case
> P-score is unbeatable and the correct conclusion is that the device score alone is the admission
> signal.
>
> ## Step 2 — instantiate each link
>
> | causal link | implementing quantity | value / range in this run | varies as expected? | evidence |
> |---|---|---|---|---|
> | triggers exist and are numerous enough to select among | triggers per clip at `tau_trig` = 20 % under the primary configuration | StudyE9 measured 3.17 re-escalations per positive clip at this cell, i.e. ~4 episodes per positive clip, and 2,194 + 1,600 resolver invocations across 300 clips | **yes** — selection is not vacuous; there are several triggers per clip to rank | StudyE9 `escalation-32B/32BI_N1/measured@25/far5/trig20` |
> | the resolver is better than the device at the same second | AP at h = 0 / 0.5 s, always-cloud 32B N=1 vs device-only, measured latency @25 % | 0.0748 / 0.0493 against 0.0528 / 0.0416 | **yes**, non-zero and in the claimed direction | StudyE9 output 1 |
> | escalating changes the application's stream | escalation-32B AP vs device-only AP at the same cell | h = 0: 0.0654 vs 0.0528; h = 0.5: 0.0411 vs 0.0416 | **yes** at h = 0; note it is already **negative** at h = 0.5 in the committed numbers, which bounds what admission can win — recorded here, before the sweep | StudyE9 cells |
> | episode value varies across triggers | per-episode utility U = 1[alarm on a positive clip ≥ h* before the event] − λ·(false alarms), λ = 150/5,196 = **0.0288684** | U can take the values −λ·n (false alarms only), 0 and 1 − λ·n, so the per-trigger benefit U(admit) − U(local) is bounded in roughly [−1, +1] and is **not** constant by construction: StudyE9 found 112–143 of 150 positive clips carry an episode dismissed before the event while 0.527 of positive clips alarm, so both outcomes occur in quantity | **yes** — both components are realised in the committed data, not merely definable | StudyE9 outputs 2 and 4 |
> | the device's trajectory carries information at the trigger second | device score at t and its 3 s / 5 s mean, max, least-squares slope, std | the device arm's own AP at h = 0 is 0.1023 at zero latency and 0.0528 under measured latency, i.e. the device score is informative about the event, so its trajectory is not noise | **yes** | StudyE5 Part G, StudyE9 §13 check 1 |
> | the budget binds | realized admitted fraction of test triggers at B ∈ {0.25, 0.5, 0.75} | enforced per fold by a cutoff fitted on training triggers; the realized test fraction is reported for every cell and is a stopping condition if it cannot be enforced | **yes**, by construction, and checked rather than assumed | this run |
> | cloud work responds to the budget | resolver invocations and GPU-s per clip-hour | admit-all is 3,794 invocations over 300 clips at this cell; admit-none is 0 | **yes**, and the decision rule's 10 % GPU-s guard is measured against it | StudyE9 cells |
>
> **No link is ABSENT or CONSTANT.** One link is instantiated but **already adverse in the committed
> data and flagged here before the sweep**: at h = 0.5 s — the horizon the pre-registered decision
> rule is written on — StudyE9's escalation-32B (0.0411) is already marginally *below* device-only
> (0.0416) at this cell. Admission selects a subset of exactly those escalations, so the quantity the
> decision rule asks about starts from a base where escalating at all is not winning at that horizon.
> This is a property of the committed numbers, not a prediction about the result.
>
> ## Step 3 — trace one representative unit
>
> The unit of this experiment is **one trigger**. The sweep writes `trace_example` to
> `e12_results.json`: one clip's triggers with, per trigger, the trigger second, every causal feature
> value, the fitted cutoff, each policy's ranking score, whether it was admitted, and then **both
> paths rolled out** — the admitted path's resolver seconds, alarm or dismissal and invocation count,
> and the local path's device seconds and outcome — with the per-episode utility of each path, the
> resulting benefit label, and the work label. The arithmetic from feature to admission decision to
> utility is checkable by hand from that table.
>
> ## Step 4 — negative controls (both pre-specified, run in the sweep)
>
> - **(a) Budget 1.0.** With every trigger admitted, the admission ranking cannot matter: all seven
>   policies must equal admit-all exactly, and admit-all must equal StudyE9's committed
>   `escalation-32B` cell. If any policy differs from admit-all at B = 1.0, the budget is not being
>   enforced where the code thinks it is.
> - **(b) Features shuffled across triggers within a fold.** The feature vectors are permuted among
>   triggers inside each fold, leaving the marginal feature distribution, the labels, the cutoff
>   procedure and the budget untouched. P-trajectory must then fall to P-random's level. If it does
>   not, its apparent advantage is coming from the budget mechanics or from the label distribution,
>   not from the features.
>
> ## Step 5 — alternative explanations
>
> 1. **"P-trajectory beats P-score because the trajectory carries extra information"** (the claimed
>    mechanism) versus **"it beats P-score because it is fitted on the benefit label, so it inherits
>    the base rate of positive clips rather than any trajectory signal."** Distinguished by control
>    (b): a shuffled-feature predictor keeps the label distribution and the fitted cutoff but loses
>    the feature–label association, so it isolates the second explanation.
> 2. **"Ranking matters"** versus **"only the admitted count matters."** Distinguished by P-random at
>    the same budget: if P-score does not beat P-random, no ranking signal exists on this workload
>    and every policy difference is budget arithmetic. This is the pre-registered null and it is
>    reported as such.
> 3. **"The trajectory predicts episode value"** versus **"the trajectory predicts the number of
>    triggers already seen in the clip, which correlates with position in the clip, which in Nexar
>    correlates with the event."** This is why elapsed time since clip start is **excluded** from the
>    feature set. The earlier-trigger count is nonetheless requested by the pre-registration and is
>    kept; it is monotone in clip position and is therefore the one feature that could carry a
>    positional proxy. Its fitted coefficient and the predictor's AUROC with and without it are
>    reported as a diagnostic, so the reader can see whether the signal rests on it.
> 4. **An artefact of the utility proxy.** The benefit label is a hand-specified utility, not the
>    evaluation metric; a policy could win on the proxy and lose on AP. Ruled out by construction:
>    the proxy is used only for training and ranking, every reported outcome is the Nexar AP on the
>    application's continuous score stream, and the λ sensitivity {0.5, 1, 2} shows whether the
>    ranking depends on the proxy's one free constant.
>

## 3. The training target

Per episode, U = 1[alarm on a positive clip at least h\* = 0.5 s before the event] − λ · (false alarms in the episode), with **λ = 150 / 5,196 = 0.0288684** — one false alarm costs what the base rate implies. `benefit` = U(admit) − U(local); `work` = resolver invocations until the episode closes, including re-escalations within 10 s. Sensitivity over λ × {0.5, 1, 2} is in §10.

| cell | triggers | fold | training triggers | benefit > 0 rate | AUROC (benefit > 0) | work R² (train) | mean work |
|---|---|---|---|---|---|---|---|
| 32BI_N1 | 1,026 | fold0 | 488 | 0.1045 | 0.734 | 0.157 | 8.66 |
| 32BI_N1 | 1,026 | fold1 | 538 | 0.1022 | 0.667 | 0.198 | 8.92 |
| 32BI_N3 | 1,007 | fold0 | 484 | 0.1364 | 0.737 | 0.150 | 9.06 |
| 32BI_N3 | 1,007 | fold1 | 523 | 0.1071 | 0.771 | 0.214 | 8.98 |

**These are diagnostics, not results.** An AUROC above 0.5 says the features predict the training proxy; whether that converts into AP is what §6–§8 measure, and it is a separate question.

## 4. Features, and what is deliberately excluded

All features are computed **at the trigger second from information already available there** — the device-visible score stream (delayed by `d_device`) and the episode outcomes already closed. Nothing after the trigger second enters any feature.

| feature | definition |
|---|---|
| `dev_score_t` | the device score the application carries at the trigger second |
| `mean_3s` | mean of the device-visible scores over the last 3 s |
| `max_3s` | maximum of the device-visible scores over the last 3 s |
| `slope_3s` | least-squares slope of the device-visible scores over the last 3 s |
| `std_3s` | standard deviation of the device-visible scores over the last 3 s |
| `mean_5s` | mean of the device-visible scores over the last 5 s |
| `max_5s` | maximum of the device-visible scores over the last 5 s |
| `slope_5s` | least-squares slope of the device-visible scores over the last 5 s |
| `std_5s` | standard deviation of the device-visible scores over the last 5 s |
| `n_prior_triggers` | triggers already seen in this clip |
| `n_prior_alarm` / `n_prior_dismiss` / `n_prior_cap` | outcomes of episodes already closed in this clip |
| `d_cloud` | the current latency setting's whole-second cloud delay |

**Excluded:** elapsed time since clip start; time since the standing query began; clip metadata (scene, light, weather) - primary predictor. In Nexar the event time is fixed relative to the clip, so any feature monotone in clip position leaks the label into a fitted policy. `n_prior_triggers` is the one requested feature that is monotone in clip position; its fitted coefficient is reported below so the reader can see whether the signal rests on it.

| feature | fold 0 coefficient (32B N = 1, primary) | fold 1 coefficient |
|---|---|---|
| `dev_score_t` | 0.873 | 0.313 |
| `mean_3s` | -0.501 | 0.482 |
| `max_3s` | -0.007 | 0.296 |
| `slope_3s` | -0.488 | 0.103 |
| `std_3s` | 0.096 | 0.558 |
| `mean_5s` | -0.361 | 0.096 |
| `max_5s` | 0.257 | -0.674 |
| `slope_5s` | 0.195 | -0.299 |
| `std_5s` | -0.392 | 0.148 |
| `n_prior_triggers` | -0.344 | -0.258 |
| `n_prior_alarm` | -0.627 | -0.314 |
| `n_prior_dismiss` | 0.315 | 0.050 |
| `n_prior_cap` | -0.258 | -0.048 |
| `d_cloud` | 0.000 | 0.000 |

## 5. Policy table — primary configuration (alarm FPR 5 %, trigger 20 %, latency (ii) @25 %)

**Resolver 32B N = 1**

| budget | policy | realized admitted | AP h = 0 | AP h = 0.5 | AP h = 1.0 | positives alarmed | false alarms / clip-h | invocations / clip-h | GPU-s / clip-h | % of admit-all GPU-s |
|---|---|---|---|---|---|---|---|---|---|---|
| 0.25 | `admit-none` | 0.000 | 0.0528 | **0.0416** | 0.0386 | 0.533 | 169.7 | 0 | 0.0 | 0 % |
| 0.25 | `P-random` | 0.253 | 0.0542 | **0.0413** | 0.0382 | 0.543 | 139.8 | 349 | 23.6 | 27 % |
| 0.25 | `P-score` | 0.283 | 0.0550 | **0.0405** | 0.0369 | 0.467 | 88.0 | 292 | 19.7 | 23 % |
| 0.25 | `P-trajectory` | 0.220 | 0.0546 | **0.0427** | 0.0367 | 0.487 | 122.6 | 297 | 20.1 | 23 % |
| 0.25 | `P-trajectory-work` | 0.211 | 0.0538 | **0.0419** | 0.0362 | 0.493 | 131.6 | 285 | 19.3 | 22 % |
| 0.25 | `P-oracle` | 0.293 | 0.0604 | **0.0461** | 0.0423 | 0.567 | 83.8 | 392 | 26.4 | 31 % |
| 0.25 | `admit-all` | 1.000 | 0.0654 | **0.0411** | 0.0358 | 0.527 | 83.8 | 1,281 | 86.5 | 100 % |
| | | | | | | | | | | |
| 0.50 | `admit-none` | 0.000 | 0.0528 | **0.0416** | 0.0386 | 0.533 | 169.7 | 0 | 0.0 | 0 % |
| 0.50 | `P-random` | 0.508 | 0.0564 | **0.0407** | 0.0370 | 0.558 | 115.6 | 664 | 44.8 | 52 % |
| 0.50 | `P-score` | 0.502 | 0.0578 | **0.0420** | 0.0371 | 0.467 | 79.7 | 556 | 37.5 | 43 % |
| 0.50 | `P-trajectory` | 0.460 | 0.0576 | **0.0419** | 0.0362 | 0.507 | 106.0 | 616 | 41.6 | 48 % |
| 0.50 | `P-trajectory-work` | 0.441 | 0.0580 | **0.0420** | 0.0367 | 0.533 | 111.5 | 599 | 40.5 | 47 % |
| 0.50 | `P-oracle` | 0.510 | 0.0679 | **0.0477** | 0.0439 | 0.593 | 70.0 | 659 | 44.5 | 51 % |
| 0.50 | `admit-all` | 1.000 | 0.0654 | **0.0411** | 0.0358 | 0.527 | 83.8 | 1,281 | 86.5 | 100 % |
| | | | | | | | | | | |
| 0.75 | `admit-none` | 0.000 | 0.0528 | **0.0416** | 0.0386 | 0.533 | 169.7 | 0 | 0.0 | 0 % |
| 0.75 | `P-random` | 0.753 | 0.0606 | **0.0408** | 0.0368 | 0.551 | 97.6 | 964 | 65.1 | 75 % |
| 0.75 | `P-score` | 0.758 | 0.0620 | **0.0433** | 0.0384 | 0.480 | 82.4 | 917 | 61.9 | 72 % |
| 0.75 | `P-trajectory` | 0.744 | 0.0616 | **0.0408** | 0.0358 | 0.513 | 90.1 | 985 | 66.5 | 77 % |
| 0.75 | `P-trajectory-work` | 0.722 | 0.0603 | **0.0414** | 0.0366 | 0.520 | 90.8 | 948 | 64.0 | 74 % |
| 0.75 | `P-oracle` | 0.767 | 0.0638 | **0.0458** | 0.0411 | 0.600 | 64.4 | 971 | 65.5 | 76 % |
| 0.75 | `admit-all` | 1.000 | 0.0654 | **0.0411** | 0.0358 | 0.527 | 83.8 | 1,281 | 86.5 | 100 % |
| | | | | | | | | | | |

**Resolver 32B N = 3**

| budget | policy | realized admitted | AP h = 0 | AP h = 0.5 | AP h = 1.0 | positives alarmed | false alarms / clip-h | invocations / clip-h | GPU-s / clip-h | % of admit-all GPU-s |
|---|---|---|---|---|---|---|---|---|---|---|
| 0.25 | `admit-none` | 0.000 | 0.0528 | **0.0416** | 0.0386 | 0.533 | 169.7 | 0 | 0.0 | 0 % |
| 0.25 | `P-random` | 0.253 | 0.0561 | **0.0429** | 0.0394 | 0.557 | 128.5 | 347 | 65.8 | 27 % |
| 0.25 | `P-score` | 0.282 | 0.0567 | **0.0425** | 0.0394 | 0.493 | 73.4 | 321 | 60.9 | 25 % |
| 0.25 | `P-trajectory` | 0.210 | 0.0564 | **0.0440** | 0.0408 | 0.480 | 100.5 | 270 | 51.2 | 21 % |
| 0.25 | `P-trajectory-work` | 0.211 | 0.0569 | **0.0445** | 0.0411 | 0.487 | 101.2 | 262 | 49.8 | 20 % |
| 0.25 | `P-oracle` | 0.264 | 0.0658 | **0.0484** | 0.0432 | 0.573 | 62.4 | 365 | 69.2 | 28 % |
| 0.25 | `admit-all` | 1.000 | 0.0593 | **0.0438** | 0.0388 | 0.547 | 72.1 | 1,292 | 245.1 | 100 % |
| | | | | | | | | | | |
| 0.50 | `admit-none` | 0.000 | 0.0528 | **0.0416** | 0.0386 | 0.533 | 169.7 | 0 | 0.0 | 0 % |
| 0.50 | `P-random` | 0.508 | 0.0566 | **0.0429** | 0.0393 | 0.570 | 105.3 | 668 | 126.7 | 52 % |
| 0.50 | `P-score` | 0.505 | 0.0598 | **0.0436** | 0.0389 | 0.527 | 70.7 | 592 | 112.2 | 46 % |
| 0.50 | `P-trajectory` | 0.483 | 0.0557 | **0.0430** | 0.0392 | 0.493 | 76.2 | 625 | 118.6 | 48 % |
| 0.50 | `P-trajectory-work` | 0.478 | 0.0555 | **0.0428** | 0.0391 | 0.527 | 81.1 | 608 | 115.3 | 47 % |
| 0.50 | `P-oracle` | 0.489 | 0.0715 | **0.0508** | 0.0463 | 0.587 | 52.7 | 673 | 127.6 | 52 % |
| 0.50 | `admit-all` | 1.000 | 0.0593 | **0.0438** | 0.0388 | 0.547 | 72.1 | 1,292 | 245.1 | 100 % |
| | | | | | | | | | | |
| 0.75 | `admit-none` | 0.000 | 0.0528 | **0.0416** | 0.0386 | 0.533 | 169.7 | 0 | 0.0 | 0 % |
| 0.75 | `P-random` | 0.752 | 0.0584 | **0.0437** | 0.0395 | 0.564 | 84.8 | 965 | 183.1 | 75 % |
| 0.75 | `P-score` | 0.743 | 0.0644 | **0.0458** | 0.0408 | 0.533 | 72.1 | 915 | 173.6 | 71 % |
| 0.75 | `P-trajectory` | 0.721 | 0.0641 | **0.0466** | 0.0404 | 0.527 | 75.5 | 922 | 174.8 | 71 % |
| 0.75 | `P-trajectory-work` | 0.739 | 0.0620 | **0.0449** | 0.0402 | 0.540 | 75.5 | 937 | 177.7 | 72 % |
| 0.75 | `P-oracle` | 0.737 | 0.0691 | **0.0494** | 0.0431 | 0.593 | 49.9 | 975 | 184.9 | 75 % |
| 0.75 | `admit-all` | 1.000 | 0.0593 | **0.0438** | 0.0388 | 0.547 | 72.1 | 1,292 | 245.1 | 100 % |
| | | | | | | | | | | |

`admit-all` and `admit-none` do not depend on the budget and are repeated in each block for reading; their numbers are identical across budgets by construction.

## 6. Paired contrasts (clip bootstrap, 2,000 resamples, seed 0, stratified by label)

Differences in AP, policy minus reference, on the same bootstrap resamples, so the contrasts are paired. `*` marks a CI excluding 0 on the favourable side.

**vs `P-score`**

| resolver | budget | policy | Δ AP h = 0 | Δ AP h = 0.5 | Δ AP h = 1.0 | GPU-s ratio |
|---|---|---|---|---|---|---|
| 32B N = 1 | 0.25 | `P-trajectory` | -0.0004 [-0.0057, +0.0092] | +0.0022 [-0.0021, +0.0099] | -0.0001 [-0.0042, +0.0053] | 1.017 |
| 32B N = 1 | 0.25 | `P-trajectory-work` | -0.0012 [-0.0070, +0.0084] | +0.0014 [-0.0029, +0.0086] | -0.0007 [-0.0046, +0.0044] | 0.977 |
| 32B N = 1 | 0.25 | `P-oracle` | +0.0054 [-0.0014, +0.0139] | +0.0055 [+0.0008, +0.0131]* | +0.0054 [+0.0012, +0.0118]* | 1.341 |
| 32B N = 1 | 0.25 | `P-random` | -0.0008 [-0.0059, +0.0034] | +0.0007 [-0.0023, +0.0047] | +0.0013 [-0.0012, +0.0050] | 1.195 |
| 32B N = 1 | 0.50 | `P-trajectory` | -0.0002 [-0.0061, +0.0091] | -0.0001 [-0.0042, +0.0058] | -0.0009 [-0.0044, +0.0030] | 1.109 |
| 32B N = 1 | 0.50 | `P-trajectory-work` | +0.0003 [-0.0076, +0.0109] | +0.0000 [-0.0045, +0.0064] | -0.0003 [-0.0041, +0.0042] | 1.078 |
| 32B N = 1 | 0.50 | `P-oracle` | +0.0101 [+0.0027, +0.0230]* | +0.0057 [+0.0008, +0.0152]* | +0.0068 [+0.0021, +0.0154]* | 1.185 |
| 32B N = 1 | 0.50 | `P-random` | -0.0013 [-0.0081, +0.0044] | -0.0013 [-0.0054, +0.0021] | -0.0000 [-0.0028, +0.0030] | 1.194 |
| 32B N = 1 | 0.75 | `P-trajectory` | -0.0004 [-0.0061, +0.0085] | -0.0025 [-0.0065, +0.0012] | -0.0026 [-0.0059, -0.0001] | 1.075 |
| 32B N = 1 | 0.75 | `P-trajectory-work` | -0.0017 [-0.0071, +0.0075] | -0.0019 [-0.0060, +0.0024] | -0.0018 [-0.0052, +0.0012] | 1.034 |
| 32B N = 1 | 0.75 | `P-oracle` | +0.0018 [-0.0055, +0.0103] | +0.0025 [-0.0023, +0.0109] | +0.0027 [-0.0014, +0.0105] | 1.059 |
| 32B N = 1 | 0.75 | `P-random` | -0.0014 [-0.0068, +0.0041] | -0.0025 [-0.0061, +0.0004] | -0.0016 [-0.0045, +0.0012] | 1.052 |
| 32B N = 3 | 0.25 | `P-trajectory` | -0.0003 [-0.0081, +0.0075] | +0.0015 [-0.0020, +0.0078] | +0.0014 [-0.0014, +0.0068] | 0.840 |
| 32B N = 3 | 0.25 | `P-trajectory-work` | +0.0003 [-0.0074, +0.0084] | +0.0020 [-0.0016, +0.0088] | +0.0018 [-0.0012, +0.0081] | 0.817 |
| 32B N = 3 | 0.25 | `P-oracle` | +0.0091 [+0.0020, +0.0206]* | +0.0059 [+0.0000, +0.0171]* | +0.0038 [-0.0011, +0.0121] | 1.137 |
| 32B N = 3 | 0.25 | `P-random` | -0.0006 [-0.0067, +0.0039] | +0.0004 [-0.0026, +0.0046] | -0.0000 [-0.0024, +0.0038] | 1.080 |
| 32B N = 3 | 0.50 | `P-trajectory` | -0.0041 [-0.0158, +0.0022] | -0.0005 [-0.0063, +0.0033] | +0.0003 [-0.0026, +0.0034] | 1.057 |
| 32B N = 3 | 0.50 | `P-trajectory-work` | -0.0043 [-0.0168, +0.0032] | -0.0007 [-0.0070, +0.0033] | +0.0002 [-0.0024, +0.0029] | 1.027 |
| 32B N = 3 | 0.50 | `P-oracle` | +0.0117 [+0.0008, +0.0252]* | +0.0073 [-0.0003, +0.0201] | +0.0074 [+0.0013, +0.0200]* | 1.137 |
| 32B N = 3 | 0.50 | `P-random` | -0.0032 [-0.0147, +0.0027] | -0.0006 [-0.0053, +0.0027] | +0.0004 [-0.0021, +0.0038] | 1.129 |
| 32B N = 3 | 0.75 | `P-trajectory` | -0.0003 [-0.0059, +0.0080] | +0.0008 [-0.0027, +0.0067] | -0.0004 [-0.0034, +0.0059] | 1.007 |
| 32B N = 3 | 0.75 | `P-trajectory-work` | -0.0024 [-0.0079, +0.0037] | -0.0009 [-0.0043, +0.0036] | -0.0006 [-0.0039, +0.0060] | 1.024 |
| 32B N = 3 | 0.75 | `P-oracle` | +0.0047 [-0.0014, +0.0145] | +0.0036 [-0.0021, +0.0155] | +0.0023 [-0.0031, +0.0142] | 1.065 |
| 32B N = 3 | 0.75 | `P-random` | -0.0060 [-0.0158, -0.0008] | -0.0021 [-0.0063, +0.0009] | -0.0013 [-0.0042, +0.0031] | 1.055 |

**vs `P-random`**

| resolver | budget | policy | Δ AP h = 0 | Δ AP h = 0.5 | Δ AP h = 1.0 | GPU-s ratio |
|---|---|---|---|---|---|---|
| 32B N = 1 | 0.25 | `P-trajectory` | +0.0004 [-0.0037, +0.0083] | +0.0015 [-0.0012, +0.0061] | -0.0014 [-0.0043, +0.0015] | 0.852 |
| 32B N = 1 | 0.25 | `P-trajectory-work` | -0.0004 [-0.0042, +0.0075] | +0.0006 [-0.0020, +0.0050] | -0.0020 [-0.0049, +0.0009] | 0.818 |
| 32B N = 1 | 0.25 | `P-oracle` | +0.0062 [+0.0012, +0.0128]* | +0.0048 [+0.0016, +0.0096]* | +0.0042 [+0.0012, +0.0082]* | 1.123 |
| 32B N = 1 | 0.25 | `P-score` | +0.0008 [-0.0034, +0.0059] | -0.0007 [-0.0047, +0.0023] | -0.0013 [-0.0050, +0.0012] | 0.837 |
| 32B N = 1 | 0.50 | `P-trajectory` | +0.0011 [-0.0035, +0.0093] | +0.0013 [-0.0023, +0.0062] | -0.0009 [-0.0039, +0.0022] | 0.929 |
| 32B N = 1 | 0.50 | `P-trajectory-work` | +0.0016 [-0.0036, +0.0110] | +0.0013 [-0.0019, +0.0062] | -0.0003 [-0.0031, +0.0028] | 0.903 |
| 32B N = 1 | 0.50 | `P-oracle` | +0.0114 [+0.0043, +0.0235]* | +0.0070 [+0.0026, +0.0154]* | +0.0068 [+0.0030, +0.0138]* | 0.993 |
| 32B N = 1 | 0.50 | `P-score` | +0.0013 [-0.0044, +0.0081] | +0.0013 [-0.0021, +0.0054] | +0.0000 [-0.0030, +0.0028] | 0.838 |
| 32B N = 1 | 0.75 | `P-trajectory` | +0.0010 [-0.0033, +0.0077] | -0.0000 [-0.0026, +0.0034] | -0.0010 [-0.0031, +0.0010] | 1.022 |
| 32B N = 1 | 0.75 | `P-trajectory-work` | -0.0003 [-0.0044, +0.0068] | +0.0006 [-0.0023, +0.0045] | -0.0002 [-0.0027, +0.0024] | 0.983 |
| 32B N = 1 | 0.75 | `P-oracle` | +0.0031 [-0.0030, +0.0108] | +0.0050 [+0.0009, +0.0132]* | +0.0043 [+0.0007, +0.0113]* | 1.007 |
| 32B N = 1 | 0.75 | `P-score` | +0.0014 [-0.0041, +0.0068] | +0.0025 [-0.0004, +0.0061] | +0.0016 [-0.0012, +0.0045] | 0.950 |
| 32B N = 3 | 0.25 | `P-trajectory` | +0.0003 [-0.0060, +0.0081] | +0.0011 [-0.0022, +0.0050] | +0.0014 [-0.0016, +0.0049] | 0.778 |
| 32B N = 3 | 0.25 | `P-trajectory-work` | +0.0009 [-0.0055, +0.0092] | +0.0016 [-0.0017, +0.0063] | +0.0018 [-0.0011, +0.0058] | 0.756 |
| 32B N = 3 | 0.25 | `P-oracle` | +0.0098 [+0.0043, +0.0193]* | +0.0056 [+0.0015, +0.0132]* | +0.0038 [+0.0001, +0.0094]* | 1.052 |
| 32B N = 3 | 0.25 | `P-score` | +0.0006 [-0.0039, +0.0067] | -0.0004 [-0.0046, +0.0026] | +0.0000 [-0.0038, +0.0024] | 0.926 |
| 32B N = 3 | 0.50 | `P-trajectory` | -0.0009 [-0.0071, +0.0062] | +0.0001 [-0.0036, +0.0036] | -0.0001 [-0.0038, +0.0029] | 0.936 |
| 32B N = 3 | 0.50 | `P-trajectory-work` | -0.0011 [-0.0074, +0.0067] | -0.0001 [-0.0039, +0.0029] | -0.0002 [-0.0037, +0.0023] | 0.910 |
| 32B N = 3 | 0.50 | `P-oracle` | +0.0149 [+0.0062, +0.0295]* | +0.0079 [+0.0021, +0.0196]* | +0.0070 [+0.0019, +0.0170]* | 1.007 |
| 32B N = 3 | 0.50 | `P-score` | +0.0032 [-0.0027, +0.0147] | +0.0006 [-0.0027, +0.0053] | -0.0004 [-0.0038, +0.0021] | 0.886 |
| 32B N = 3 | 0.75 | `P-trajectory` | +0.0058 [-0.0002, +0.0181] | +0.0029 [-0.0007, +0.0099] | +0.0009 [-0.0016, +0.0051] | 0.955 |
| 32B N = 3 | 0.75 | `P-trajectory-work` | +0.0036 [-0.0019, +0.0137] | +0.0012 [-0.0022, +0.0062] | +0.0007 [-0.0020, +0.0051] | 0.970 |
| 32B N = 3 | 0.75 | `P-oracle` | +0.0107 [+0.0033, +0.0260]* | +0.0057 [+0.0006, +0.0181]* | +0.0037 [-0.0007, +0.0138] | 1.010 |
| 32B N = 3 | 0.75 | `P-score` | +0.0060 [+0.0008, +0.0158]* | +0.0021 [-0.0009, +0.0063] | +0.0013 [-0.0031, +0.0042] | 0.948 |

## 7. Fraction of the oracle's headroom over P-score that each causal policy captures

At each horizon, (policy − P-score) / (P-oracle − P-score). A negative entry means the policy is behind P-score; `—` means the oracle itself is not ahead of P-score there, so the ratio has no meaning.

| resolver | budget | policy | h = 0 | h = 0.5 | h = 1.0 |
|---|---|---|---|---|---|
| 32B N = 1 | 0.25 | `P-trajectory` | -8 % | +40 % | -2 % |
| 32B N = 1 | 0.25 | `P-trajectory-work` | -21 % | +25 % | -12 % |
| 32B N = 1 | 0.50 | `P-trajectory` | -2 % | -1 % | -13 % |
| 32B N = 1 | 0.50 | `P-trajectory-work` | +3 % | +0 % | -5 % |
| 32B N = 1 | 0.75 | `P-trajectory` | -23 % | -101 % | -95 % |
| 32B N = 1 | 0.75 | `P-trajectory-work` | -95 % | -75 % | -65 % |
| 32B N = 3 | 0.25 | `P-trajectory` | -3 % | +25 % | +36 % |
| 32B N = 3 | 0.25 | `P-trajectory-work` | +3 % | +33 % | +46 % |
| 32B N = 3 | 0.50 | `P-trajectory` | -35 % | -8 % | +4 % |
| 32B N = 3 | 0.50 | `P-trajectory-work` | -37 % | -10 % | +3 % |
| 32B N = 3 | 0.75 | `P-trajectory` | -6 % | +22 % | -17 % |
| 32B N = 3 | 0.75 | `P-trajectory-work` | -52 % | -26 % | -27 % |

## 8. The pre-registered decision rule

> The trajectory signal is useful if **P-trajectory or P-trajectory-work beats P-score on AP at h = 0.5 s with a paired CI excluding 0 at 2 of 3 budgets** (primary configuration, 32B N = 1 or N = 3), **without increasing cloud GPU-s by more than 10 %**. If not, the device score alone is the admission signal: say so plainly. If P-score does not beat P-random, say that admission ranking has no signal on this workload.

| resolver | policy | budget | Δ AP h = 0.5 vs P-score | CI excludes 0? | GPU-s vs P-score | within +10 %? | counts toward the rule? |
|---|---|---|---|---|---|---|---|
| 32B N = 1 | `P-trajectory` | 0.25 | +0.0022 [-0.0021, +0.0099] | no | 1.017 | yes | no |
| 32B N = 1 | `P-trajectory` | 0.50 | -0.0001 [-0.0042, +0.0058] | no | 1.109 | no | no |
| 32B N = 1 | `P-trajectory` | 0.75 | -0.0025 [-0.0065, +0.0012] | no | 1.075 | yes | no |
| 32B N = 1 | `P-trajectory-work` | 0.25 | +0.0014 [-0.0029, +0.0086] | no | 0.977 | yes | no |
| 32B N = 1 | `P-trajectory-work` | 0.50 | +0.0000 [-0.0045, +0.0064] | no | 1.078 | yes | no |
| 32B N = 1 | `P-trajectory-work` | 0.75 | -0.0019 [-0.0060, +0.0024] | no | 1.034 | yes | no |
| 32B N = 3 | `P-trajectory` | 0.25 | +0.0015 [-0.0020, +0.0078] | no | 0.840 | yes | no |
| 32B N = 3 | `P-trajectory` | 0.50 | -0.0005 [-0.0063, +0.0033] | no | 1.057 | yes | no |
| 32B N = 3 | `P-trajectory` | 0.75 | +0.0008 [-0.0027, +0.0067] | no | 1.007 | yes | no |
| 32B N = 3 | `P-trajectory-work` | 0.25 | +0.0020 [-0.0016, +0.0088] | no | 0.817 | yes | no |
| 32B N = 3 | `P-trajectory-work` | 0.50 | -0.0007 [-0.0070, +0.0033] | no | 1.027 | yes | no |
| 32B N = 3 | `P-trajectory-work` | 0.75 | -0.0009 [-0.0043, +0.0036] | no | 1.024 | yes | no |

| resolver | policy | budgets counting | rule met (≥ 2 of 3)? |
|---|---|---|---|
| 32B N = 1 | `P-trajectory` | 0 / 3 | no |
| 32B N = 1 | `P-trajectory-work` | 0 / 3 | no |
| 32B N = 3 | `P-trajectory` | 0 / 3 | no |
| 32B N = 3 | `P-trajectory-work` | 0 / 3 | no |

**Verdict: the rule is NOT met.** Neither P-trajectory nor P-trajectory-work beats P-score on AP at h = 0.5 s with a paired CI excluding 0 at two of three budgets, for either resolver. Taking the pre-registered wording as written: **on this workload the device score alone is the admission signal.** The trajectory features predict the training proxy (AUROC 0.667–0.734) and that does not convert into AP at the horizon the rule is written on.

**And the second clause of the rule.** P-score vs P-random: a CI excluding 0 at h = 0 or h = 0.5 s in 0 of 3 budgets at 32B N = 1 and 1 of 3 at N = 3. So **admission ranking has no signal on this workload**: P-score does not separate from random, and every policy difference in §5 is budget arithmetic.

## 9. Secondary configurations (point AP, no bootstrap)

The bootstrap is run only in the primary configuration, which is where the decision rule lives; the secondary cells carry point AP. Policies at budget 0.50.

| resolver | latency | alarm FPR | trigger | `P-score` h = 0 | `P-trajectory` h = 0 | `P-score` h = 0.5 | `P-trajectory` h = 0.5 | `admit-all` h = 0.5 | `admit-none` h = 0.5 |
|---|---|---|---|---|---|---|---|---|---|
| 32B N = 1 | (ii) @25 % | 1 % | 10 % | 0.0574 | 0.0532 | 0.0416 | 0.0396 | 0.0397 | 0.0416 |
| 32B N = 1 | (ii) @25 % | 1 % | 20 % | 0.0612 | 0.0545 | 0.0432 | 0.0406 | 0.0421 | 0.0416 |
| 32B N = 1 | (ii) @25 % | 5 % | 10 % | 0.0575 | 0.0552 | 0.0415 | 0.0431 | 0.0405 | 0.0416 |
| 32B N = 1 | (ii) @25 % | 5 % | 20 % | 0.0578 | 0.0576 | 0.0420 | 0.0419 | 0.0411 | 0.0416 |
| 32B N = 1 | (ii) @25 % | 10 % | 10 % | 0.0566 | 0.0540 | 0.0413 | 0.0415 | 0.0397 | 0.0416 |
| 32B N = 1 | (ii) @25 % | 10 % | 20 % | 0.0578 | 0.0588 | 0.0437 | 0.0434 | 0.0396 | 0.0416 |
| 32B N = 1 | (i) zero | 1 % | 10 % | 0.1172 | 0.1244 | 0.0689 | 0.0734 | 0.0820 | 0.0624 |
| 32B N = 1 | (i) zero | 1 % | 20 % | 0.1328 | 0.1391 | 0.0919 | 0.0937 | 0.0948 | 0.0624 |
| 32B N = 1 | (i) zero | 5 % | 10 % | 0.1095 | 0.1094 | 0.0716 | 0.0616 | 0.0795 | 0.0624 |
| 32B N = 1 | (i) zero | 5 % | 20 % | 0.1241 | 0.1159 | 0.0828 | 0.0774 | 0.0950 | 0.0624 |
| 32B N = 1 | (i) zero | 10 % | 10 % | 0.1133 | 0.1015 | 0.0770 | 0.0626 | 0.0796 | 0.0624 |
| 32B N = 1 | (i) zero | 10 % | 20 % | 0.1158 | 0.1064 | 0.0838 | 0.0706 | 0.0936 | 0.0624 |
| 32B N = 3 | (ii) @25 % | 1 % | 10 % | 0.0575 | 0.0581 | 0.0427 | 0.0443 | 0.0427 | 0.0416 |
| 32B N = 3 | (ii) @25 % | 1 % | 20 % | 0.0569 | 0.0545 | 0.0428 | 0.0417 | 0.0424 | 0.0416 |
| 32B N = 3 | (ii) @25 % | 5 % | 10 % | 0.0585 | 0.0569 | 0.0431 | 0.0437 | 0.0438 | 0.0416 |
| 32B N = 3 | (ii) @25 % | 5 % | 20 % | 0.0598 | 0.0557 | 0.0436 | 0.0430 | 0.0438 | 0.0416 |
| 32B N = 3 | (ii) @25 % | 10 % | 10 % | 0.0590 | 0.0573 | 0.0436 | 0.0432 | 0.0441 | 0.0416 |
| 32B N = 3 | (ii) @25 % | 10 % | 20 % | 0.0575 | 0.0577 | 0.0436 | 0.0433 | 0.0422 | 0.0416 |
| 32B N = 3 | (i) zero | 1 % | 10 % | 0.1281 | 0.1196 | 0.0681 | 0.0730 | 0.0831 | 0.0624 |
| 32B N = 3 | (i) zero | 1 % | 20 % | 0.1615 | 0.1498 | 0.0919 | 0.0816 | 0.1047 | 0.0624 |
| 32B N = 3 | (i) zero | 5 % | 10 % | 0.1316 | 0.1419 | 0.0786 | 0.0874 | 0.0845 | 0.0624 |
| 32B N = 3 | (i) zero | 5 % | 20 % | 0.1388 | 0.1417 | 0.0900 | 0.0897 | 0.1017 | 0.0624 |
| 32B N = 3 | (i) zero | 10 % | 10 % | 0.1281 | 0.1076 | 0.0875 | 0.0631 | 0.0866 | 0.0624 |
| 32B N = 3 | (i) zero | 10 % | 20 % | 0.1422 | 0.1226 | 0.0926 | 0.0747 | 0.1006 | 0.0624 |

## 10. λ sensitivity (primary configuration, 32B N = 1 and N = 3)

λ is the one free constant in the training proxy. Re-fitting the predictor at λ × {0.5, 1, 2} and re-running admission:

| resolver | λ × | budget | policy | AP h = 0 | AP h = 0.5 | realized admitted | GPU-s / clip-h |
|---|---|---|---|---|---|---|---|
| 32B N = 1 | 0.5 | 0.25 | `P-trajectory` | 0.0546 | 0.0427 | 0.220 | 20.1 |
| 32B N = 1 | 0.5 | 0.25 | `P-trajectory-work` | 0.0538 | 0.0419 | 0.211 | 19.3 |
| 32B N = 1 | 0.5 | 0.50 | `P-trajectory` | 0.0576 | 0.0419 | 0.460 | 41.6 |
| 32B N = 1 | 0.5 | 0.50 | `P-trajectory-work` | 0.0580 | 0.0420 | 0.441 | 40.5 |
| 32B N = 1 | 0.5 | 0.75 | `P-trajectory` | 0.0616 | 0.0408 | 0.744 | 66.5 |
| 32B N = 1 | 0.5 | 0.75 | `P-trajectory-work` | 0.0603 | 0.0414 | 0.722 | 64.0 |
| 32B N = 1 | 1.0 | 0.25 | `P-trajectory` | 0.0546 | 0.0427 | 0.220 | 20.1 |
| 32B N = 1 | 1.0 | 0.25 | `P-trajectory-work` | 0.0538 | 0.0419 | 0.211 | 19.3 |
| 32B N = 1 | 1.0 | 0.50 | `P-trajectory` | 0.0576 | 0.0419 | 0.460 | 41.6 |
| 32B N = 1 | 1.0 | 0.50 | `P-trajectory-work` | 0.0580 | 0.0420 | 0.441 | 40.5 |
| 32B N = 1 | 1.0 | 0.75 | `P-trajectory` | 0.0616 | 0.0408 | 0.744 | 66.5 |
| 32B N = 1 | 1.0 | 0.75 | `P-trajectory-work` | 0.0603 | 0.0414 | 0.722 | 64.0 |
| 32B N = 1 | 2.0 | 0.25 | `P-trajectory` | 0.0546 | 0.0427 | 0.220 | 20.1 |
| 32B N = 1 | 2.0 | 0.25 | `P-trajectory-work` | 0.0538 | 0.0419 | 0.211 | 19.3 |
| 32B N = 1 | 2.0 | 0.50 | `P-trajectory` | 0.0576 | 0.0419 | 0.460 | 41.6 |
| 32B N = 1 | 2.0 | 0.50 | `P-trajectory-work` | 0.0580 | 0.0420 | 0.441 | 40.5 |
| 32B N = 1 | 2.0 | 0.75 | `P-trajectory` | 0.0616 | 0.0408 | 0.744 | 66.5 |
| 32B N = 1 | 2.0 | 0.75 | `P-trajectory-work` | 0.0603 | 0.0414 | 0.722 | 64.0 |
| 32B N = 3 | 0.5 | 0.25 | `P-trajectory` | 0.0564 | 0.0440 | 0.210 | 51.2 |
| 32B N = 3 | 0.5 | 0.25 | `P-trajectory-work` | 0.0569 | 0.0445 | 0.211 | 49.8 |
| 32B N = 3 | 0.5 | 0.50 | `P-trajectory` | 0.0557 | 0.0430 | 0.483 | 118.6 |
| 32B N = 3 | 0.5 | 0.50 | `P-trajectory-work` | 0.0555 | 0.0428 | 0.478 | 115.3 |
| 32B N = 3 | 0.5 | 0.75 | `P-trajectory` | 0.0641 | 0.0466 | 0.721 | 174.8 |
| 32B N = 3 | 0.5 | 0.75 | `P-trajectory-work` | 0.0620 | 0.0449 | 0.739 | 177.7 |
| 32B N = 3 | 1.0 | 0.25 | `P-trajectory` | 0.0564 | 0.0440 | 0.210 | 51.2 |
| 32B N = 3 | 1.0 | 0.25 | `P-trajectory-work` | 0.0569 | 0.0445 | 0.211 | 49.8 |
| 32B N = 3 | 1.0 | 0.50 | `P-trajectory` | 0.0557 | 0.0430 | 0.483 | 118.6 |
| 32B N = 3 | 1.0 | 0.50 | `P-trajectory-work` | 0.0555 | 0.0428 | 0.478 | 115.3 |
| 32B N = 3 | 1.0 | 0.75 | `P-trajectory` | 0.0641 | 0.0466 | 0.721 | 174.8 |
| 32B N = 3 | 1.0 | 0.75 | `P-trajectory-work` | 0.0620 | 0.0449 | 0.739 | 177.7 |
| 32B N = 3 | 2.0 | 0.25 | `P-trajectory` | 0.0564 | 0.0440 | 0.210 | 51.2 |
| 32B N = 3 | 2.0 | 0.25 | `P-trajectory-work` | 0.0569 | 0.0445 | 0.211 | 49.8 |
| 32B N = 3 | 2.0 | 0.50 | `P-trajectory` | 0.0557 | 0.0430 | 0.483 | 118.6 |
| 32B N = 3 | 2.0 | 0.50 | `P-trajectory-work` | 0.0555 | 0.0428 | 0.478 | 115.3 |
| 32B N = 3 | 2.0 | 0.75 | `P-trajectory` | 0.0641 | 0.0466 | 0.721 | 174.8 |
| 32B N = 3 | 2.0 | 0.75 | `P-trajectory-work` | 0.0620 | 0.0449 | 0.739 | 177.7 |

## 11. Negative controls

**(a) Budget 1.0 — every policy must equal admit-all exactly.** At budget 1.0 every policy must equal admit-all exactly (AP at h=0, invocations, fraction of positives alarmed, false alarms per clip-hour).

Cells checked: **168**. All equal: **PASS**.

**(b) Features shuffled across triggers within a fold.** each trigger's feature vector is replaced by one drawn uniformly from that fold's pool of trigger feature vectors (seed 0), which breaks the feature-label association while preserving the marginal feature distribution. Labels, cutoff procedure and budget are unchanged. P-trajectory must fall to P-random's level.

| cell | budget | AP h = 0.5: shuffled | real `P-trajectory` | `P-random` | realized admitted | GPU-s / clip-h |
|---|---|---|---|---|---|---|
| 32B N = 1 | 0.25 | 0.0420 | 0.0427 | 0.0413 | 0.251 | 23.4 |
| 32B N = 1 | 0.50 | 0.0423 | 0.0419 | 0.0407 | 0.496 | 44.1 |
| 32B N = 1 | 0.75 | 0.0418 | 0.0408 | 0.0408 | 0.766 | 66.0 |
| 32B N = 3 | 0.25 | 0.0393 | 0.0440 | 0.0429 | 0.220 | 61.2 |
| 32B N = 3 | 0.50 | 0.0422 | 0.0430 | 0.0429 | 0.504 | 127.6 |
| 32B N = 3 | 0.75 | 0.0436 | 0.0466 | 0.0437 | 0.733 | 178.6 |

Shuffled P-trajectory sits 0.0001–0.0036 from P-random at h = 0.5 s, against 0.0000–0.0029 for the real predictor.

**PASS on the condition as written — and UNINFORMATIVE, which is the more useful thing to say.** The control requires the shuffled predictor to fall to P-random's level, and it does. But the *unshuffled* predictor is already at P-random's level (§8), so there was nothing for the shuffle to destroy and this control cannot discriminate between the two explanations it was written to separate. Per CLAUDE.md Rule 2 this is recorded as **inconclusive, not a real negative**: it tells us the §8 result is not an artefact of the budget mechanics or of the label distribution — a shuffled predictor behaves the same, so no part of the setup secretly favours a fitted ranking — and it tells us nothing about whether the features carry signal, which §3's out-of-sample AUROC answers separately and affirmatively.

## 12. One instrumented trigger trace

Cell `32BI_N3|measured@25|far5|trig20`. Clip `00005.mp4` (positive), event at 20.874 s, duration 40.099 s, fold 0. `d_device` = 1 s, `d_cloud` = 1 s. τ_trigger -7.0009, τ_alarm cloud -4.6347, τ_alarm device -2.5789. λ = 0.0288684, h\* = 0.5 s. `P-trajectory` cutoffs: B = 0.25 → 0.176425, B = 0.50 → 0.108389, B = 0.75 → 0.075070.

| trigger t | t − event | dev score | mean 5 s | slope 5 s | prior trig | predicted benefit > 0 | predicted work | true benefit | true work | admitted at B = 0.25 / 0.50 / 0.75 |
|---|---|---|---|---|---|---|---|---|---|---|
| 4 | -16.9 s | -3.288 | -3.288 | +0.000 | 0 | 0.2774 | 14.13 | +1.0000 | 16 | yes / yes / yes |
| 8 | -12.9 s | -5.504 | -5.114 | -0.393 | 1 | 0.0765 | 10.46 | +1.0000 | 12 | no / no / yes |
| 11 | -9.9 s | -6.252 | -6.352 | -0.250 | 2 | 0.0567 | 9.52 | +0.0000 | 12 | no / no / no |
| 16 | -4.9 s | -6.252 | -7.951 | +0.075 | 3 | 0.0531 | 7.96 | +0.0000 | 19 | no / no / no |
| 23 | +2.1 s | -4.018 | -7.954 | +1.621 | 4 | 0.0557 | 7.16 | +0.0000 | 12 | no / no / no |
| 25 | +4.1 s | -4.264 | -5.960 | +1.521 | 5 | 0.0542 | 6.88 | +0.0000 | 16 | no / no / no |
| 30 | +9.1 s | -5.504 | -4.879 | -0.612 | 6 | 0.0576 | 8.45 | +0.0000 | 11 | no / no / no |
| 32 | +11.1 s | -4.264 | -5.406 | +0.348 | 7 | 0.0452 | 6.86 | +0.0000 | 9 | no / no / no |
| 35 | +14.1 s | -4.511 | -3.922 | +0.444 | 8 | 0.0135 | 6.31 | +0.0000 | 6 | no / no / no |
| 38 | +17.1 s | -5.007 | -3.687 | -0.523 | 9 | 0.0112 | 5.81 | +0.0000 | 3 | no / no / no |

Both paths, rolled out in isolation from each trigger second:

| trigger t | admitted path: outcome | alarm t | invocations | local path: outcome | alarm t | invocations |
|---|---|---|---|---|---|---|
| 4 | alarm | 7 | 4 | cap | — | 0 |
| 8 | alarm | 9 | 2 | cap | — | 0 |
| 11 | dismiss | — | 3 | dismiss | — | 0 |
| 16 | alarm | 22 | 7 | dismiss | — | 0 |
| 23 | alarm | 24 | 2 | alarm | 27 | 0 |
| 25 | alarm | 29 | 5 | alarm | 27 | 0 |
| 30 | alarm | 31 | 2 | alarm | 34 | 0 |
| 32 | alarm | 34 | 3 | alarm | 34 | 0 |
| 35 | alarm | 37 | 3 | alarm | 37 | 0 |
| 38 | clip_end | — | 3 | clip_end | — | 0 |

The benefit label is U(admit) − U(local) on these two rollouts, with U = 1[alarm on a positive clip at or before event − 0.5 s] − λ · (false alarms). The admission decision compares the predicted benefit against the fold's fitted cutoff; nothing in the feature columns uses a second later than the trigger.

## 13. Results consistency check (CLAUDE.md, 6 checks)

**1. Cross-check against committed measurements.** `admit-all` must reproduce StudyE9's committed `escalation-32B` cell at the same configuration, and `admit-none`'s score stream is the device-only stream, so its AP must reproduce StudyE9's `device-only` baseline.

| quantity | this run | prior run | source of prior | ratio | agree |
|---|---|---|---|---|---|
| `admit-all` AP, all 5 horizons, 32B N = 1 | max abs difference 0.000000000000 | — | StudyE9 `escalation-32B / 32BI_N1 / measured@25 / far5 / trig20 / q75 / k2 / L10 / c0` | 1.000000 | agree |
| `admit-all` resolver invocations, 32B N = 1 | 3,794 | 3,794 | StudyE9 same cell | 1.000000 | agree |
| `admit-all` fraction of positives alarmed | 0.526667 | 0.526667 | StudyE9 same cell | 1.000000 | agree |
| `admit-all` false alarms / clip-hour | 83.833718 | 83.833718 | StudyE9 same cell | 1.000000 | agree |
| `admit-all` AP, all 5 horizons, 32B N = 3 | max abs difference 0.000000000000 | — | StudyE9 `escalation-32B / 32BI_N3 / measured@25 / far5 / trig20 / q75 / k2 / L10 / c0` | 1.000000 | agree |
| `admit-all` resolver invocations, 32B N = 3 | 3,827 | 3,827 | StudyE9 same cell | 1.000000 | agree |
| `admit-all` fraction of positives alarmed | 0.546667 | 0.546667 | StudyE9 same cell | 1.000000 | agree |
| `admit-all` false alarms / clip-hour | 72.055427 | 72.055427 | StudyE9 same cell | 1.000000 | agree |
| `admit-none` AP, all 5 horizons | max abs difference 0.000000000000 | — | StudyE9 `device-only / measured@25 / far5` | 1.000000 | agree |
| `admit-none` resolver invocations | 0 | 0 | StudyE9 device-only | — | agree |
| λ | 0.0288684 | 150 / 5,196 = 0.0288684 | pre-registration | 1.000000 | agree |
| negative decision seconds | 5,196 | 5,196 | StudyD14 / StudyE5 Part G | 1.000 | agree |
| base rate | 0.0281 | 0.0281 | StudyE5 Part G | 0.9985 | agree |

**PASS.** The two reference policies reproduce StudyE9 to the last bit (worst disagreement 0.000000000000 across 15 AP comparisons), so every admission contrast in this report sits on StudyE9's scale. Nothing is near the 2× investigation gate.

**One deliberate difference, stated rather than reconciled.** `admit-none` raises 169.7 false alarms per clip-hour against StudyE9 device-only's 96.3, although their AP is identical. The reason is structural: StudyE9's device-only arm counts up-crossings over the whole clip, so a sustained above-threshold run is one alarm, whereas a locally-kept **episode** re-arms at each episode boundary, so the same run can alarm once per episode. The *score stream* is identical — which is why AP matches exactly — and only the alarm-event bookkeeping differs. Alarm counts are therefore comparable **between policies in this report** and are not comparable with StudyE9's device-only row; AP is comparable with both.

**2. Physical plausibility.** No new latency, throughput or size is measured here: every delay is StudyE9's committed `d = ceil(latency)` and every byte count is StudyD4's, imported from `study_e9_episodes.py` rather than restated. The only new rates are counts — invocations and GPU-seconds — and they are bounded above by `admit-all` and below by `admit-none` in every cell, which §5 shows. GPU-seconds use StudyE9's 5,600 tok/s saturated 32B prefill and its committed prompt-token counts. **PASS.**

**3. Distribution sanity.** The ranking scores are continuous and the realized admitted fractions in §5 differ across policies at the same budget, so no cell is a constant where a distribution is expected. The benefit label, by contrast, **is** mostly exactly 0 (benefit > 0 rate 0.1022–0.1045), which is a property of the utility definition and is the reason the deterministic tiebreak in §1 is needed; it was found by inspecting the realized fractions, not assumed. P-random's numbers are means over 20 seeds, not a single draw. **PASS.**

**4. Definition audit.**

| object | definition in this run | matches prior? |
|---|---|---|
| AP at horizon h | positives = the stream value at the whole second nearest event − h clamped to the grid; negatives = all 5,196 negative-clip seconds | yes — StudyE5 Part G and StudyE9, unchanged |
| episode | trigger opens, resolver scores each second, alarm / dismiss after k consecutive / cap at L_max / clip end | yes — StudyE9's primary configuration, unchanged |
| trigger | device score ≥ `tau_trig`, no episode open, cooldown elapsed | yes — StudyE9 |
| thresholds | quantiles of each arm's **own** training-fold negative seconds | yes — StudyE9 |
| admitted episode | resolver = 32B, delay `d_cloud`, invocations charged per wall second open | yes — identical to StudyE9 `escalation-32B` |
| locally-kept episode | resolver = the device's own 4B score, delay `d_device`, **zero** cloud invocations, device's own `tau_alarm` and `tau_dismiss` | new in this study; it is StudyE9's `escalation-4B` structure with the device as its own resolver |
| benefit | U(admit) − U(local) on **isolated** rollouts from the trigger second | new; §1 states why it is not measured along a trajectory |
| work | resolver invocations to episode close plus admitted re-escalations within 10 s | new |
| budget B | fraction of **triggers** admitted, cutoff fitted on training clips per fold | new |

**PASS.** No name is used with two definitions inside this study. One name is used differently *across* studies and is flagged above rather than reconciled: an "alarm" is an episode-scoped up-crossing here and a whole-clip up-crossing in StudyE9's device-only baseline.

**5. Claim linkage.** This bears on FORMULATION §Decisions (`p_i`, which node serves a session, decided online) and §Constraints 2 (serving feasibility within the latency SLO). It **weakens** the claim that a richer device-side signal improves the placement decision under a capacity constraint: the trajectory predicts the training proxy and does not improve AP over the instantaneous score. It **weakens** it twice over, in fact: no admission ranking separates from random admission on AP across this budget grid, so nothing here supports choosing *which* escalation to admit on AP grounds — only that admitting more of them helps at h = 0. It does **not** speak to the coupling claim (§The coupling claim), nor does AP measure the alarm-rate selection effect of flag 8 — this is a single-stream study with a budget expressed as a fraction of triggers, not a modelled server; StudyD7/D7b and StudyRH8 are the capacity studies. **PASS with the scope note.**

**6. Proxy validity.**

| proxy | what it actually measures | valid for the claim? |
|---|---|---|
| the per-episode utility U (λ = 0.0288684) standing in for application value | a hand-specified trade between one timely alarm and one false alarm | **used for training and ranking only, never for evaluation.** Every reported outcome is the Nexar AP. §10's λ × {0.5, 1, 2} sweep shows whether the ranking depends on the constant |
| the device arm's *accuracy* = the H100 4B N = 1 score | the cloud 4B's answer on byte-identical frames, not the Orin's | **flagged, inherited from StudyE9 §13 check 6.** StudyF4 measured 97–98 % per-question agreement on a different task; it has never been measured on Nexar. Every device number in this study carries that uncertainty and is marked UNVALIDATED |
| `n_prior_triggers` as a trajectory feature | a count that is monotone in clip position, and in Nexar the event time is fixed relative to the clip | **flagged in the mechanism verification before the sweep** (Step 5, alternative 3). Its fitted coefficients are in §4; elapsed time itself is excluded for exactly this reason |
| budget as a fraction of triggers | a capacity constraint expressed per-trigger, with no server queue, no concurrency and no admission latency | stated; this is a selection study, not a capacity study. StudyD7b's measured peak (15.1 req/s at 32B N = 1) is what a real budget would come from |

## 14. Observations (data only, no interpretation)

1. 32B N = 1, budget 0.50: AP at h = 0.5 s is 0.0420 for `P-score`, 0.0419 for `P-trajectory`, 0.0420 for `P-trajectory-work`, 0.0407 for `P-random`.
2. 32B N = 3, budget 0.50: AP at h = 0.5 s is 0.0436 for `P-score`, 0.0430 for `P-trajectory`, 0.0428 for `P-trajectory-work`, 0.0429 for `P-random`.
3. Admitting every escalation scores 0.0654 at h = 0 and 0.0411 at h = 0.5 s; admitting none scores 0.0528 and 0.0416. The whole span available to any admission policy is +0.0126 at h = 0 and -0.0005 at h = 0.5 s.
4. Cross-fitted AUROC for *benefit > 0* is 0.667–0.734; the work model's training R² is 0.157–0.198.
5. Realized admitted fractions track the targets: at B = 0.25 / 0.50 / 0.75 with 32B N = 1, `P-score` admits 0.283 / 0.502 / 0.758 and `P-trajectory` 0.220 / 0.460 / 0.744.
6. `P-score` raises markedly fewer false alarms than `P-random` at the same budget (79.7 vs 115.6 per clip-hour at B = 0.50, 32B N = 1) and alarms on fewer positive clips (0.467 vs 0.558).
7. Negative control (a) passes in 168 of 168 cells. Negative control (b) leaves the shuffled predictor at P-random's level, which is the condition as written; the unshuffled predictor is also at that level, so the control is uninformative here (§11).
8. `admit-all` and `admit-none` reproduce StudyE9's committed numbers with a worst AP disagreement of 0.000000000000 over 15 comparisons.

## 15. Interpretation (inference, labelled as such)

- **The answer to the study's question is no, and plainly: on this workload the device score alone is the admission signal.** A predictor built from the device's own score trajectory does not choose better than ranking by the instantaneous device score — not at any of the three budgets, for either resolver, at the horizon the rule was written on. That is a pre-registered negative, not a failure to find an effect: the predictor was fitted, cross-validated and does separate the training target (AUROC 0.667–0.734).
- **The prize at h = 0.5 s is not zero, and that makes the negative sharper rather than weaker.** Admitting every escalation (0.0411) and admitting none (0.0416) sit within 0.0005 of each other at that horizon — which the mechanism verification flagged before the sweep (Step 2) — so there is nothing to be had by *interpolating* between them. But selection is not interpolation: `P-oracle` at a quarter budget reaches 0.0461, +0.0045 above admit-none and +0.0050 above admit-all, on 31 % of admit-all's GPU-seconds. Choosing *which* escalations to admit can therefore beat both endpoints, and the available margin is of the same order as the effect the rule was asked to detect. What fails is that no causal policy here finds any of it.
- **And the stronger null fires with it: on AP, no admission ranking separates from random.** P-score — the baseline the trajectory was supposed to beat — itself beats random admission with a CI excluding 0 in only 1 of 6 resolver × budget cells, with every point estimate favouring it (+0.0006 to +0.0060 at h = 0) and none separating. The pre-registered wording for this case is explicit and is adopted: **admission ranking has no signal on this workload**, as measured by AP. The budget itself matters — admit-all is ahead of admit-none at h = 0 — but the *ordering* within a budget does not.
- **The selection effect that does exist is about alarms, not about AP.** `P-score` admits the triggers the device is most confident about, the 32B resolver dismisses many of them, and the result is markedly fewer false alarms *and* fewer positive clips alarmed than random admission at the same budget. That is a real, repeatable selection effect on the application's behaviour; it simply does not show up in AP, which is computed on the continuous score stream and not on the alarm decisions.
- **CLAUDE.md Rule 2 classification: REAL NEGATIVE for the trajectory claim and for admission ranking on AP.** The mechanism was present and instantiated (Step 2: every link non-zero and varying), it was exercised (the predictor separates benefit > 0 out of sample), the action space is shared and the budget is enforced and verified (negative control (a) is exact), and the headroom it was asked to capture demonstrably exists — `P-oracle` beats both endpoints at h = 0.5 s. The mechanism operated as specified and did not produce the claimed effect. Negative control (b) is **uninformative here rather than confirmatory**: the unshuffled predictor is already at P-random's level, so the shuffle had nothing to destroy; §11 records that, and this classification does not rest on it. For completeness, at h = 0 the endpoints are +0.0126 apart and §6 reports that column too, but h = 0.5 s was the pre-registered horizon and no rule is re-written here after seeing the results.
- **What this does not show.** It does not show that admission ranking is worthless in deployment: the alarm-rate differences above are large and an application that acts on alarms would feel them, while AP — the metric this project fixed in advance and did not vary — is blind to them. It does not show that no trajectory feature could help — only that these features, fitted this way, on this trace, do not. It does not establish the device arm's accuracy, which remains an H100 measurement standing in for an Orin run never done on Nexar. And the budget here is a fraction of triggers, not a server: nothing in it models a queue, concurrency or admission latency.

## 16. Files

- `experiments/dashcam/study_e12_admission.py`
- `experiments/dashcam/study_e12_report.py`
- `results/dashcam/study_e12/e12_results.json`
- `results/dashcam/study_e12/e12_mechanism_verification.md`
- `reports/study_e12_admission.md (this file)`

