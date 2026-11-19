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

## AMENDMENT 2026-11-12: wired to MATERIALIZE

The interface gained `MATERIALIZE(session, target_tokens, slice_tokens)`, which is the explicit act
of BUILDING a session's cloud-side state, as against `KEEP_GPU_WARM`, which only holds state that
already exists. StudyRH8's EAGER set is warmed by an explicit warm-up pass, which its own 2026-11-03 audit records as a cost EXCLUDED from RH8's in-window metrics (240 warm-up records moving 4,289 MB, present only in the EAGER cells). Both RH8 arms now emit `MATERIALIZE` for a session they warm that is not already GPU-warm, which makes that previously invisible build cost explicit in our suite.

`slice_tokens = None` (one monolithic prefill) — the paper warmed whole histories, never slices, so the monolithic form is the
faithful one. Whether SLICING helps is the property under test (fairness rule 4) and is tested by
B11, not here.

**What changed, and what did not.** What changed is what this baseline DECLARES. What did not
change is what it is charged: the harness already billed the first promotion of a session to
GPU-warm at the measured cold-prefill cost (fairness rule 3), and it bills `MATERIALIZE` on the
same path. The re-run smoke record is identical field for field apart from the new
`materialize_*` counters.

## StudyB-baselines amendment 2 (2026-11-13)

**Item 5: `host_offload_intent = "retain"`** on both RH8 arms - RH8's whole subject is which
sessions are warm, and the tier is how that is expressed, so in the no-host world the harness
keeps a retained session GPU-warm instead of evicting it (GPU KV capacity, LRU eviction, budget
and fairness rule 3 all still bind).

**Item 6: CEIL, not round, for the HIGH_FRAC warm-slot count.** `round(0.25 x n_sessions)` is 0
for every cell with fewer than two sessions, so RH8's own HIGH_FRAC kept nothing warm by
construction; `ceil` keeps at least one session warm whenever there is one. Measured consequence
on the representative cell: challenge mAP 0.5135 -> 0.5169 (ALL) for both arms.

## D134 item 5, added 2026-11-19: ported, and what Part A did and did not resolve

**Part A did not resolve the conflict above.** That conflict is about **labels**, and the card's
resolution stands unchanged: both readings ship, `RH8OracleDemand` as an upper bound and
`RH8CausalDemand` as deployable but carrying no RH8 number.

**What Part A resolved is a different blocker that was never written down, because nobody had
looked.** RH8 decides **only** `session_action`. Before Part A, `desired_tier` was written at
`coordinator.py` and read nowhere, so **RH8's entire mechanism was inert**: it could express its
decision and the system did nothing with it. Placement now reaches execution, so the arm acts.

**RH8 is the first arm whose correctness depends on a code path no previous arm exercised**, and
that is why the residency-costing defect survived undetected until Part A made placement live. A
path with no caller cannot be wrong in any way that shows. Worth stating because it predicts where
the next such defect will be: whichever live2 path is first exercised by a newly-unblocked arm.

> Corroborating census: covex-v13 emits **only `MATERIALIZE`**, never `KEEP_GPU_WARM` or
> `OFFLOAD_TO_HOST`. So the placement slot is **unexercised** for the incumbent, category 4,
> established before the placement slot is ever screened rather than after.

**Representation side, both readings: CHEAP and INJECTED.** Measured at 8 devices, seed 4, both
emit `CLOUD/None` on all 9 recalls and **enact** `CLOUD/RECENT`, because `apply_defaults` injects
`DEFAULTS["representation"] = "RECENT"`. On the two-axis rule that is: comparable with any arm
whose **effective** representation is RECENT, and entitled to **no credit** for the resulting
11.6x to 55x evidence discount, which neither reading requested. Neither may be compared against a
D2-effective arm such as the COVEX family.

**`RH8OracleDemand` cannot run in a scored cell.** It declares `reads_future = True` and live2
**refuses** such an arm (`coordinator.py:13`, `:184`). It is registered for completeness and is an
upper bound on paper only.

**`DEFAULTS["session_action"]` is never injected** — `apply_defaults` touches streams, recall,
`order` and `engine_config`, and contains no reference to `action.sessions`. Checked directly. So
RH8's placement behaviour is entirely its own and nothing is issuing offloads it did not request.
