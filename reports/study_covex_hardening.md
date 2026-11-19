# StudyCOVEX-harden: audits, behaviour tests and an offline comparison (D124)

Flash, CPU only, 2026-11-18. **Session 2 of two.** Session 1 edits policy code; this study writes
NEW FILES ONLY and never edits policy, arm, coordinator, cstate or fleet code. Every hook here is
a wrapper or a monkeypatch installed from inside `policy/audit/` and removed afterwards.

**Development data only (D124): seed 0 fleet traces, the pilot settings, and the committed
synthetic fixtures. Round-1 seeds 1, 2 and 3 are never generated, run or inspected.** The harness
enforces this: `_harness.assert_dev_seed` refuses any fleet seed but 0.

**Nothing in this study is a result.** Every number is a dry run with no GPU, no model server and
no engine, priced from the frozen pol4 cost curve. It is screening.

## 0. Decisions taken up front, PROVISIONAL

Posted as the required single message of foreseeable decisions. No answer had arrived when the
work was done, so these are the defaults and are marked PROVISIONAL.

1. **Channel decomposition.** `delta_j` is split into seven channels: own SH gain, SH harm to
   others, RC utility, deficit term, continuation value, state value, and the backlog charge at
   mu. Own against harm is split by device: rows for the candidate's own device against the rest.
   The backlog term is recovered as `terminal - cont - sv`, exactly, rather than re-deriving mu
   and busy. **A self-check asserts the seven channels sum to `delta_j`**, so the decomposition
   cannot be silently wrong.
2. **"Exactly zero" means `abs(x) <= 1e-12`**, and a channel is FLAGGED as a blind spot when it
   is exactly zero in at least 99 percent of a kind's candidates. The 99 percent bar is stated
   rather than tuned; it separates "structurally absent" from "usually small".
3. **Candidate kinds** are labelled from the action kind and the resolved item kinds:
   `sh_admit`, `sh_dispatch`, `sh_release`, `sh_hold`, `recall_admit`, `piece_release`,
   `piece_defer`, `state_promote_rebuild`, `state_materialize`, `state_other`. A `release`,
   `defer` or `dispatch` action carries `item_id` and not `items`, so the item is resolved
   through `fleet.pending` and `fleet.in_flight`; without that every such candidate's device is
   invisible, which is the error session 1 recorded against itself.
4. **Scenario traces are crafted event lists** built with the committed `schema.make`, not
   `traces.synthetic`, because the scenarios need exact control of history size, device count and
   deadlines. `history_append.est_tokens` is CUMULATIVE, per the committed contract.
5. **Scenario verdicts are observable outcomes**, not internal values: released before its own
   deadline, declined at admission, or never released. That keeps a scenario's expectation
   independent of how COVEX happens to be instrumented.
6. **The offline comparison is a screen and is optimistic for COVEX**, stated again at Part 3,
   because the dry run prices the engine from the SAME committed curves COVEX's own model uses.

## 1. Part 2 PRE-REGISTRATION: scenario expectations

**Committed BEFORE COVEX was run against any of them.** The rule is that no expectation may be
adjusted after seeing a result; if one proves wrong it is recorded as an ERRATUM with its reason,
and the original stays visible.

Committed constants these expectations rest on: `DASHCAM_L_S = 1.0 s` and `ROBOT_L_S = 5.0 s`
(D71, D82), dashcam cadence 0.5 s, history batches every 30 s (D68), D2 at 90 tokens per frame
plus a 31-token header (StudyRH4), uplink 13.6 Mbit/s and RTT 44 ms (D75), tight memory
`GPU_KV = 62,944` and host 27 GiB (D76). The committed cold-prefill curve gives 1.19 s at 5,341
tokens, 2.47 s at 11,101 and 5.29 s at 20,101 (`baselines/costs.py`, StudyRH5 Part A).

| id | scenario | PRE-REGISTERED expectation | justification |
|---|---|---|---|
| S1 | one robot question, no dashcams, cold 11k history, 5 s deadline | **released before its deadline** | the committed curve rebuilds 11k tokens in about 2.47 s against a 5 s deadline on an idle engine, so there is no resource reason to decline |
| S2 | the same with 8 dashcams (light load) | **released before its deadline, with few or no dashcam instants lost** against the paired no-question run | MOT1 light_tight measured pieces at 0 extra missed instants with the robot answered at 3.37 s, so both are achievable together at this load |
| S3 | 20 dashcams (heavy load), tight host | **either served knowingly, reporting the dashcam cost, OR declined AT ADMISSION. NEVER admitted and then deferred past its deadline** | admit-then-starve is the failure the pilot showed; MOT1 heavy_tight shows no option serves both, so a knowing trade-off is the honest outcome |
| S4a | MOT1 light_tight reproduced | COVEX chooses **pieces** (a MATERIALIZE with a slice), the measured best at 0 extra missed | MOT1 grid_2x2 light_tight: P2048 and P1024 both 0 extra missed; ONE-GO costs 11, HOST-WARM costs 8 |
| S4b | MOT1 heavy_tight reproduced | **no option serves both, so COVEX makes a knowing trade-off and it is reported.** Either outcome passes provided it is not admit-then-starve | MOT1 heavy_tight: P1024 gives 0 extra missed but a 6.79 s robot TTFT, over the 5 s deadline; ONE-GO and HOST-WARM answer in 3.47 s and 2.62 s but cost 57 and 44 missed instants |
| S4c | MOT1 heavy_roomy reproduced | COVEX **keeps the history resident or reloads from host** rather than rebuilding | MOT1 heavy_roomy: HOST-WARM alone achieves 0 extra missed AND a 0.686 s robot TTFT, so it dominates every rebuild there |
| S5 | two robot questions at once, both cold | **neither is starved**: either both released before their deadlines, or one is declined at admission with the other served. A sensible order means the one that can still make its deadline goes first | starving both is the pilot failure; declining one knowingly is legitimate |
| S6 | a robot question whose history is host-warm | **reload, not rebuild**: the released work is a host reload and the question is served | StudyRH5 Part A puts a host reload at 0.669 s for 17.6k tokens against 3.91 s to rebuild it cold, so rebuilding a host-warm history is strictly wasteful |
| S7 | a robot question infeasible even on an idle engine (about 27k tokens, 5 s deadline) | **declined at admission, and no GPU work charged to it** | the committed curve needs about 7.1 s for 27k tokens, so it cannot be served in 5 s; spending the engine on it harms the dashcams for nothing |
| S8 | a dashcam instant whose calibrated cloud gain is zero or negative | **not sent** | spec 3.2's scale is a GAIN against the device answer, so a non-positive gain cannot justify engine time |
| S9 | memory pressure where keeping one history warm evicts another | **keeps the higher expected value**, and the two values are reported | spec 5.3's state value is what the eviction choice is supposed to compare |
| S10 | sustained overload above engine capacity | **bounded queues and no unbounded deferral**: the pending set does not grow without limit over the run | spec 7.3's bounded-waiting rule exists precisely to stop a job waiting forever |
| S11 | a question arriving with its history already fully built (GPU-warm) | **served, and no rebuild work released for it** | there is nothing to rebuild, so any rebuild released would be pure waste |
| S12 | a question whose deadline has already passed when it is first seen | **not released at all** | serving it cannot earn credit and the engine time harms others |

Two scenarios carry a stated realisability caveat, recorded now rather than after the fact:

- **S6** needs the coordinator to BELIEVE the history is host-warm, and that belief is produced by
  the coordinator's own residency machinery rather than by anything the trace can declare. The
  scenario drives it by building the history early and then applying memory pressure. **If the
  observed readiness is not HOST-WARM, the scenario is reported as NOT REALISABLE from the trace
  interface rather than being scored.**
- **S9** likewise depends on eviction actually occurring. If no eviction happens under the
  pressure applied, it is reported as NOT REALISABLE.

## 2. Part 1 AUDITS

Filled in below from `results/orchestration/live2/covex_harden/audits_v10.json`.

## 3. Part 2 RESULTS

Filled in below.

## 4. Part 3 OFFLINE COMPARISON

Filled in below.

## 5. GATE (D124)

Filled in below.
