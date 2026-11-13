<!-- StudyB-baselines (addendum). The constructed baselines are ours, not adaptations of a paper,
so there is no "faithful" column; what matters is that each is a REAL competitor and that every
design choice is visible. Fairness rules 1-6 hold and are checked by `interface.check_fairness`. -->

# Constructed baselines B3, B4, B6, B7, B8, B9, B10, B11 — case "constructed"

**File.** `constructed.py`. These exist to give the scheduler honest competition at every level of
sophistication, from "you did not need a scheduler" (B3) to "four modern mechanisms, each the best
of its kind" (B9).

| id | what it is | decides | experiments |
|---|---|---|---|
| **B3** | the best STATIC configuration for the scenario, chosen on development data, then never adapted | episodic mode, cadence, N, recall tier, representation | A, B, C |
| **B4** | query-type routing: single-shot → cheapest feasible tier; short-horizon → local with a fixed escalation rule; long-horizon → cloud history | episodic mode, recall tier, representation | C |
| **B6** | latency-aware routing: highest estimated quality subject to the predicted deadline | episodic mode, cadence, N, recall tier, representation | C |
| **B7** | EDF + feasibility admission: DEFER what can still make it, REJECT what cannot | recall tier, defer, order | C |
| **B8** | utility-per-GPU-second admission: admit in order of expected incremental utility ÷ estimated cloud work | episodic mode, cadence, N, recall tier | A, C |
| **B9** | the independent best-of-breed controller — **the primary competitor** | everything except the engine configuration | C |
| **B10** | blocking-aware admission, **no slicing**: defer a recall whose non-preemptive engine time would hold an episodic stream past StudyE9d's d\*, unless its deadline slack is exhausted | recall tier, defer, session placement, order | C |
| **B11** | naive slicing: every materialization chained in fixed 2,048-token slices, FCFS, **no awareness of episodic timing** — the ablation of slicing without scheduling | recall tier, session placement, engine configuration | B, C |

## B3 — best static configuration

Chosen by taking the highest-quality configuration in the measured profile whose demand fits the
scenario's GPU-second-per-second budget. **The choice is made on the development split and then
frozen**, so B3 is the honest answer to "would a fixed setting have done just as well?". Its
scenario budget is a constructor argument, so one B3 exists per workload scenario.

## B4 — query-type routing

The type is read from the query's `category`, which is observable. The escalation threshold for
short-horizon work is StudyD3's development-split `tau_trigger` at a 20 % trigger rate
(**−7.0009**), not an evaluation-fitted one. Long-horizon work takes the richest representation
the session actually holds.

## B6 — latency-aware routing

For each query, enumerate the (tier, representation) options the session holds, drop those whose
predicted StudyRH5 service time exceeds the remaining slack, and take the highest-quality
survivor; for streams, the highest-quality configuration whose delivery hold shift fits the
episodic deadline (0.75 s by default, the device's own cadence).

## B7 — EDF + feasibility

Differs from `naive.edf-service-time` deliberately: that one falls back to the device, while B7
uses the full action space — **DEFER** when a wait would still make the deadline, **REJECT** when
nothing would. This is the Clockwork-style admission the addendum asks for, expressed in our
actions.

## B8 — utility per GPU-second

Every candidate piece of cloud work — a stream configuration or a recall query — is scored by
(expected utility gain) ÷ (estimated GPU-seconds) and admitted in that order while the budget
lasts. The gain for a stream is its measured quality above the local arm's; for a recall query it
is the cloud-over-device margin. This is the classic ratio rule and is the baseline any cost-aware
scheduler must beat.

## B9 — the independent best-of-breed controller (PRIMARY COMPETITOR)

Four mechanisms run on the same physical resources, **each given the same trained estimators, the
same measured cost curves and the same host-offload facilities our scheduler will get**:

| component | choice made | why this choice |
|---|---|---|
| (i) model / evidence routing | **ECO-LLM-style** joint (tier, representation, cadence, N) selection under SLOs, over the measured profile | the addendum offers ECO-LLM-style *or* the calibrated query-type router; ECO-LLM-style is strictly more informed, because it optimises over the *joint* space rather than a per-type rule |
| (ii) streaming readiness + rate | **VideoStorm MaxMin** (Eq. 4) rate allocation across streams, gated by an **R3-Streaming-style readiness** test | the addendum asks for both; MaxMin is chosen over MaxSum because it protects the worst stream, which is the fairer competitor, and StudyE9b / E9c show rate allocation — not escalation — is the episodic lever |
| (iii) SLO-aware cloud scheduling | **utility-per-GPU-second** admission (B8's rule) with **EDF** ordering among the admitted | the addendum offers EDF *or* utility-per-cost; using both — ratio for admission, EDF for order — is strictly stronger than either alone |
| (iv) KV management | **host offload** + **Preble-style cache-affinity** admission under load + **KVFlow-style reuse-aware eviction** on the CAUSAL inter-arrival estimate | the three modern mechanisms this suite has, composed; the reuse estimate is causal because rule 5 forbids the workflow lookahead KVFlow actually uses |

**The point of B9 is that the four are INDEPENDENT.** Each optimises its own objective from the
shared observation and none sees another's choice. Where two would touch the same field, a
**fixed, documented precedence** resolves it rather than a joint optimisation:

```
episodic mode / cadence / N  : (ii) sets the rate; (i) may only DOWNGRADE it to a cheaper
                               configuration when its SLO check fails — never upgrade
recall tier / representation : (i) chooses; (iii) may REFUSE on budget; (iv) may REFUSE on cache
                               affinity under load
session placement            : (iv) alone
request order                : (iii) alone
```

That precedence is exactly what a jointly-optimising scheduler is supposed to beat. It is stated
here so the comparison is honest: B9 is not a weak composition, it is the strongest *independent*
one this suite can build, and any advantage our scheduler shows over it must come from
coordinating the four decisions rather than from having better components.

### B9-noHost — the labelled variant run in StudySIM1c-scoped

StudySIM1c-scoped runs the baselines in a declared world with **no host-offload tier** (the
scoped gate of StudySIM1 passes only there; see `reports/study_sim1c_scoped.md` section 0).
B9 uses host offload as ONE component among four, so it is not excluded; it runs there as the
labelled variant **B9-noHost**.

| what was disabled | what was NOT changed |
|---|---|
| component (iv)'s **host offload**: the HOST-WARM readiness state does not exist in that world and OFFLOAD_TO_HOST is mapped to EVICT by the harness's availability flag | everything else in (iv) - Preble-style cache-affinity admission under load and KVFlow-style reuse-aware eviction on the causal inter-arrival estimate - runs unchanged |
| | components (i), (ii) and (iii) are untouched |
| | the precedence order above is untouched |
| | every hyperparameter below is untouched |

The disabling is done by the **harness**, not by editing B9: `run.py` sets
`HOST_AVAILABLE = False` and maps the action. B9's own code is byte-identical in both worlds, and
its file hash is recorded at the start and the end of that study.

**This variant says nothing about B9 with host offload**, which is the configuration this card
otherwise describes.

## Hyperparameters and provenance

| name | value | from |
|---|---|---|
| B3 scenario budget | 0.2 GPU-s per wall second | our own scenario definition, stated |
| B4 `tau` | −7.0009 | StudyD3 development split, 3,000 negative scores, 20 % trigger rate |
| B6 episodic deadline | 0.75 s | the device's own saturated cadence (StudyE9b) |
| B7 `defer_s` | 0.5 s | our own, stated |
| B8 / B9 utility gains | measured quality differences from `profiles` (StudyE9b / E9c) and the ordinal recall weights of `cards/ecollm.md` A3 | committed measurements + one ordinal assumption, flagged there |
| B9 `readiness_threshold` | 0.35 | our own, stated |
| B9 `max_load_pressure` | 0.9 | as `cards/preble.md` |
| B9 `gpu_warm_slots` | 4 | StudyE10b's measured warm-session operating point |
| B9 EWMA `alpha` | 0.3 | as `cards/kvflow.md` |

## AMENDMENT 2026-11-12: B10 and B11

Added with the StudyB-baselines amendment, which also gave the interface
`MATERIALIZE(session, target_tokens, slice_tokens)` and per-stream `SUSPEND_UNTIL(t)`.

### B10 — blocking-aware admission (no slicing)

**The mechanism it tests is measured, not assumed.** Two committed results supply it:

1. **The hold is real and is one unit.** StudyE10c §6 found that an episodic request is not queued
   behind a cold recall but *released at its first token*; StudyE10d located the unsplittable unit
   as the LM prefill of the recall's ~12.6k tokens (the 40 MB body and the vision encoder only
   lengthen the window); StudyE10e found that capping the per-step tokens cuts the hold by 19–30 %
   and **does not remove it** (p99 stays 4–8× the budget).
2. **Lateness has a price curve.** StudyE9d measured V(d) and d\*: the added delivery delay at
   which a cloud episodic stream falls to the device's own value — 2.54 s on challenge mAP and
   1.13 s on streaming AP at h = 0 for 32B N = 1 at cadence 0.5 s.

**The rule**, per pending query, in EDF order:

```
T        = costs.recall_ttft_s(readiness_tokens, readiness)      # predicted non-preemptive time
affected = connected streams with a call due inside T (cadence <= T)
d*       = profiles.d_star_s(arm, cadence)                       # StudyE9d
if slack <= T:        ADMIT        # a deadline is never sacrificed to a stream
elif T >= min(d*):    DEFER by min(0.25 s, slack - T)
else:                 ADMIT
```

**Component choices, each stated.**

| choice | value | why, and what it rests on |
|---|---|---|
| predicted engine time | `recall_ttft_s(tokens, readiness)` | StudyRH5 Part A's measured TTFT at 11k and 28k, **linearly interpolated between them** — a stated RULE, not a measurement (`costs.INTERPOLATION_RULES`) |
| which streams are affected | every **connected** stream whose cadence ≤ T | B10 does not decide placement, so `DEFAULTS["episodic_mode"] = "cloud"` applies to all of them. Reading `on_cloud` instead would silently exempt every stream in a replay where the harness has not yet put one on the cloud, and the rule would never fire |
| the tolerance | StudyE9d's d\* for that arm and cadence | the only committed answer to "how late is too late". **StudyE9d's own warning is carried**: d\* has a wide CI and is not a threshold, so B10 is a baseline built on a point estimate and says so |
| no crossing inside the 3-s grid | read as 3.0 s | the measured grid's maximum, never extrapolated |
| defer quantum | 0.25 s, the StudyD14b decision step | bounded and causal: the query is re-decided every step and the slack-exhaustion escape guarantees it is eventually admitted |
| KV management | B9's component (iv) verbatim | the causal inter-arrival estimate ranks sessions for 4 GPU-warm slots; no future knowledge |
| readiness | whatever the session actually has | COLD / HOST-WARM / GPU-WARM is never upgraded for free (fairness rule 3) |
| slicing | **none** (`slice_tokens = None`) | declared via `restricts_action_space`; slicing is the property under test and B11 is its ablation |

### B11 — naive slicing

Every materialization is chained in **fixed 2,048-token slices**, FCFS, with no awareness of
episodic timing; everything else is the tuned-engine always-cloud baseline (StudyE10e's **P1**,
the engine the user chose on 2026-11-12). 2,048 is StudyE10c's E2 step budget — a documented vLLM
0.31.0 value rather than a tuned one.

**The per-slice overhead is NOT measured.** StudySIM1 sweeps it over {0.02, 0.05, 0.1, 0.2, 0.47}
s and **every B11 result is labelled parametric** until StudySLICE1 measures it. This is the one
free parameter in the suite, and it is exposed rather than buried.

### Why both exist

B10 schedules without slicing; B11 slices without scheduling. A policy that beats both is doing
something neither mechanism does alone — which is the comparison the scheduler has to win, and the
reason the amendment asked for the pair.

### What the smoke replay does and does not exercise

`smoke/replay.py` keeps both of its sessions HOST-WARM, so B10's predicted engine time is
0.46–1.00 s, always under d\* = 2.54 s: **it admits everything and its deferral rule never
fires there**, and the smoke record shows 0 deferrals and 0 materializations. That is a property
of the 10-minute replay, not of the policy, and it is exactly the kind of silently-unexercised
mechanism CLAUDE.md's protocol exists to catch. The rule is therefore exercised explicitly in
`reconstructed/test_constructed_amendment_toy.py`, which asserts 24 named behaviours including
that B10 defers a COLD 28k query with slack (T = 7.40 s > d\* = 2.54 s), admits the same query
once its slack is exhausted, admits a HOST-WARM 11k query (T = 0.46 s), and that B11 slices at
2,048 tokens and runs engine P1. All 24 pass.
