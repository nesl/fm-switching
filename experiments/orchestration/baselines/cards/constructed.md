<!-- StudyB-baselines (addendum). The constructed baselines are ours, not adaptations of a paper,
so there is no "faithful" column; what matters is that each is a REAL competitor and that every
design choice is visible. Fairness rules 1-6 hold and are checked by `interface.check_fairness`. -->

# Constructed baselines B3, B4, B6, B7, B8, B9 — case "constructed"

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
