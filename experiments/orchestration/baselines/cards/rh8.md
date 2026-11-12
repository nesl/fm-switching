<!-- StudyB-baselines. Written for a reviewer: everything faithful to the original is marked FAITHFUL, everything we changed is marked ADAPTATION with its reason. -->
# StudyRH8 demand-aware warm state — our own work, case A, **with an interface conflict**

**Source.** `reports/study_rh8_demand_aware_warm_state.md` and
`experiments/cost/study_rh8_demand_aware.py`. (The task text says `experiments/orchestration`;
the file actually lives under `experiments/cost/`.)

**Files.** `rh8_adapted.py` — **two** policies, deliberately.

## THE CONFLICT, reported rather than resolved silently

StudyRH8's winning arm is MIX-DEMAND, which keeps warm "exactly the high-demand devices". In the
code, `eager_set("MIX-DEMAND", D)` returns `high_demand(D)`, and `high_demand` is
`random.Random(0).sample(range(D), D//4)` — **the same draw that ASSIGNED the synthetic demand**.
The report's own 2026-11-03 audit says so:

> "MIX-DEMAND is given the ground-truth demand labels. Its eager set is *exactly* the high-demand
> device set, while MIX-RANDOM draws an independent set. The comparison therefore contrasts a
> policy with oracle knowledge of the synthetic demand assignment against one with none; it does
> not show that demand can be *predicted*."

Our interface forbids a policy from reading labels. So RH8's measured policy **cannot** enter the
suite unchanged. Rather than invent a hybrid, both readings ship, each labelled:

| policy | what it is | status |
|---|---|---|
| `RH8OracleDemand` | RH8's rule verbatim: warm = the known high-demand set | **UPPER BOUND.** Declares `reads_future = True`, is excluded from the causality check, and is reported like `naive.HindsightOracle` — never as a deployable baseline. |
| `RH8CausalDemand` | predict demand from each session's OWN observed recall arrivals (exponentially decayed count), keep the top `HIGH_FRAC` warm | **Deployable, but NOT what StudyRH8 measured.** No RH8 number may be attributed to it. |

## Mapping

| RH8 | our code | note |
|---|---|---|
| eager device ⇒ history kept warm | `KEEP_GPU_WARM` | FAITHFUL |
| lazy device ⇒ history reloaded on demand | `OFFLOAD_TO_HOST` | ADAPTATION A1 (RH8's lazy reloads from the device; ours from host KV, which StudyRH5 measured) |
| `HIGH_FRAC = 0.25` | `high_frac=0.25` | FAITHFUL |
| `LOW_RATE = 0.20` | not used (it generated RH8's synthetic demand, which we do not replay) | — |
| ground-truth demand set | `RH8OracleDemand` only | the conflict above |

## Other caveats carried from RH8's own audit

- **D96 is a single seed with synthetic demand**; demand was assigned, not measured, with no
  replication across seeds.
- **Eager's warm-up cost is excluded** from RH8's in-window metrics (as in RH7), so one arm pays
  a cost the other does not.
- **The margin depends on the exclusion rule**: +10.49 pp on all data, +6.25 pp excluding the
  first 120 s by wall clock, +12.09 pp by session time. Any quotation must state which.

## Hyperparameters and provenance

| name | value | from |
|---|---|---|
| `high_frac` | 0.25 | StudyRH8 `HIGH_FRAC` |
| `half_life_s` | 60 s | our own, for the causal demand estimate only |
