# StudyE12-admission — mechanism verification (CLAUDE.md Steps 1–5)

**Recorded 2026-11-11 (later), BEFORE the StudyE12 sweep ran.** Every quantity below is read from
StudyD14's committed trace or from StudyE9's committed results; none comes from a StudyE12 policy
run. Offline analysis of committed results; CPU only on the flash host; no GPU, no model server,
no inference. Scores are continuous log P(Yes) throughout; no literal Yes/No answer is used
anywhere.

## Step 1 — the causal chain

FORMULATION §Constraints 2 (*serving feasibility*: the serving node must answer within the latency
SLO) and §Decisions (`p_i`, which node serves a session, decided online) give the chain this
experiment tests. When the cloud can absorb only a fraction B of device-triggered escalations, the
placement decision stops being per-session and becomes a **selection** problem: the device must
decide, at the trigger second and from information it already has, which triggers are worth the
scarce resolver slot. The chain is:

*If* a device-triggered escalation's value varies across triggers — that is, if the gain from
replacing the device's own score stream with the 32B resolver's is larger for some triggers than
for others — *and if* that variation is visible in the device's own score trajectory before the
escalation is issued, *then* a ranking function over trajectory features admits a higher-value
subset than ranking by the instantaneous device score, and at a fixed budget the application's
AP rises. Two things can break the chain independently: the value may not vary (every trigger
equally worth escalating, so any ranking is as good as any other), or it may vary but be invisible
at the trigger second (the variation is driven by what the resolver sees afterwards, which no
causal predictor can know).

The counter-chain this experiment must leave room for is that the **instantaneous device score is
already a sufficient statistic** for whatever signal the trajectory carries, in which case
P-score is unbeatable and the correct conclusion is that the device score alone is the admission
signal.

## Step 2 — instantiate each link

| causal link | implementing quantity | value / range in this run | varies as expected? | evidence |
|---|---|---|---|---|
| triggers exist and are numerous enough to select among | triggers per clip at `tau_trig` = 20 % under the primary configuration | StudyE9 measured 3.17 re-escalations per positive clip at this cell, i.e. ~4 episodes per positive clip, and 2,194 + 1,600 resolver invocations across 300 clips | **yes** — selection is not vacuous; there are several triggers per clip to rank | StudyE9 `escalation-32B/32BI_N1/measured@25/far5/trig20` |
| the resolver is better than the device at the same second | AP at h = 0 / 0.5 s, always-cloud 32B N=1 vs device-only, measured latency @25 % | 0.0748 / 0.0493 against 0.0528 / 0.0416 | **yes**, non-zero and in the claimed direction | StudyE9 output 1 |
| escalating changes the application's stream | escalation-32B AP vs device-only AP at the same cell | h = 0: 0.0654 vs 0.0528; h = 0.5: 0.0411 vs 0.0416 | **yes** at h = 0; note it is already **negative** at h = 0.5 in the committed numbers, which bounds what admission can win — recorded here, before the sweep | StudyE9 cells |
| episode value varies across triggers | per-episode utility U = 1[alarm on a positive clip ≥ h* before the event] − λ·(false alarms), λ = 150/5,196 = **0.0288684** | U can take the values −λ·n (false alarms only), 0 and 1 − λ·n, so the per-trigger benefit U(admit) − U(local) is bounded in roughly [−1, +1] and is **not** constant by construction: StudyE9 found 112–143 of 150 positive clips carry an episode dismissed before the event while 0.527 of positive clips alarm, so both outcomes occur in quantity | **yes** — both components are realised in the committed data, not merely definable | StudyE9 outputs 2 and 4 |
| the device's trajectory carries information at the trigger second | device score at t and its 3 s / 5 s mean, max, least-squares slope, std | the device arm's own AP at h = 0 is 0.1023 at zero latency and 0.0528 under measured latency, i.e. the device score is informative about the event, so its trajectory is not noise | **yes** | StudyE5 Part G, StudyE9 §13 check 1 |
| the budget binds | realized admitted fraction of test triggers at B ∈ {0.25, 0.5, 0.75} | enforced per fold by a cutoff fitted on training triggers; the realized test fraction is reported for every cell and is a stopping condition if it cannot be enforced | **yes**, by construction, and checked rather than assumed | this run |
| cloud work responds to the budget | resolver invocations and GPU-s per clip-hour | admit-all is 3,794 invocations over 300 clips at this cell; admit-none is 0 | **yes**, and the decision rule's 10 % GPU-s guard is measured against it | StudyE9 cells |

**No link is ABSENT or CONSTANT.** One link is instantiated but **already adverse in the committed
data and flagged here before the sweep**: at h = 0.5 s — the horizon the pre-registered decision
rule is written on — StudyE9's escalation-32B (0.0411) is already marginally *below* device-only
(0.0416) at this cell. Admission selects a subset of exactly those escalations, so the quantity the
decision rule asks about starts from a base where escalating at all is not winning at that horizon.
This is a property of the committed numbers, not a prediction about the result.

## Step 3 — trace one representative unit

The unit of this experiment is **one trigger**. The sweep writes `trace_example` to
`e12_results.json`: one clip's triggers with, per trigger, the trigger second, every causal feature
value, the fitted cutoff, each policy's ranking score, whether it was admitted, and then **both
paths rolled out** — the admitted path's resolver seconds, alarm or dismissal and invocation count,
and the local path's device seconds and outcome — with the per-episode utility of each path, the
resulting benefit label, and the work label. The arithmetic from feature to admission decision to
utility is checkable by hand from that table.

## Step 4 — negative controls (both pre-specified, run in the sweep)

- **(a) Budget 1.0.** With every trigger admitted, the admission ranking cannot matter: all seven
  policies must equal admit-all exactly, and admit-all must equal StudyE9's committed
  `escalation-32B` cell. If any policy differs from admit-all at B = 1.0, the budget is not being
  enforced where the code thinks it is.
- **(b) Features shuffled across triggers within a fold.** The feature vectors are permuted among
  triggers inside each fold, leaving the marginal feature distribution, the labels, the cutoff
  procedure and the budget untouched. P-trajectory must then fall to P-random's level. If it does
  not, its apparent advantage is coming from the budget mechanics or from the label distribution,
  not from the features.

## Step 5 — alternative explanations

1. **"P-trajectory beats P-score because the trajectory carries extra information"** (the claimed
   mechanism) versus **"it beats P-score because it is fitted on the benefit label, so it inherits
   the base rate of positive clips rather than any trajectory signal."** Distinguished by control
   (b): a shuffled-feature predictor keeps the label distribution and the fitted cutoff but loses
   the feature–label association, so it isolates the second explanation.
2. **"Ranking matters"** versus **"only the admitted count matters."** Distinguished by P-random at
   the same budget: if P-score does not beat P-random, no ranking signal exists on this workload
   and every policy difference is budget arithmetic. This is the pre-registered null and it is
   reported as such.
3. **"The trajectory predicts episode value"** versus **"the trajectory predicts the number of
   triggers already seen in the clip, which correlates with position in the clip, which in Nexar
   correlates with the event."** This is why elapsed time since clip start is **excluded** from the
   feature set. The earlier-trigger count is nonetheless requested by the pre-registration and is
   kept; it is monotone in clip position and is therefore the one feature that could carry a
   positional proxy. Its fitted coefficient and the predictor's AUROC with and without it are
   reported as a diagnostic, so the reader can see whether the signal rests on it.
4. **An artefact of the utility proxy.** The benefit label is a hand-specified utility, not the
   evaluation metric; a policy could win on the proxy and lose on AP. Ruled out by construction:
   the proxy is used only for training and ranking, every reported outcome is the Nexar AP on the
   application's continuous score stream, and the λ sensitivity {0.5, 1, 2} shows whether the
   ranking depends on the proxy's one free constant.
