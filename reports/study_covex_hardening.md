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

## 1b. GATE AMENDMENT, RULING D127, 2026-11-18

**Recorded here, ABOVE the results, and committed BEFORE round one was scored.** The ordering is
the point: a bar moved after a result is indistinguishable from fitting the bar to the outcome,
which is the failure this study's pre-registration discipline exists to prevent. This amendment
was ruled before any F5 or v1.2 result existed.

**The amendment.** In the offline screen, COVEX must be at least as good as the best SCHEDULING
baseline, meaning **edf and llf**, on BOTH the dashcam and the robot measure at EVERY size.
**`always-cloud-fcfs` remains REPORTED in every table but is NOT GATING.**

**The reason, as ruled.** The dry-run engine prices from the same committed curves COVEX's own
model uses, and it shows `always-cloud-fcfs` at 1.000 robot service where live contention is
expected. A comparison against an arm with no admission control is therefore not informative in a
screen of this kind. **COVEX against `always-cloud-fcfs` is judged only on live H100 runs.**

**What this does NOT change.** The **v1.1 gate result in section 5 stands exactly as it was
reported** under the criterion in force at the time, and is not re-scored or re-worded. For a
reader who wants the comparison, here is what v1.1 would have been under the amended criterion,
presented as a SEPARATE line and not as a revision:

| n | gating best, robot (edf, llf) | v1.1 robot | gating best, dashcam | v1.1 dashcam | amended verdict |
|---|---|---|---|---|---|
| 4 | 0.889 (edf) | 0.222 | 0.999 | 0.978 | still FAIL on both |
| 8 | 0.900 (llf) | 0.150 | 1.000 (llf) | 0.927 | still FAIL on both |
| 16 | 0.600 (llf) | 0.200 | 0.658 (llf) | 0.449 | still FAIL on both |

So the amendment does not soften the bar on current evidence: the robot axis is now judged against
llf's 0.778, 0.900 and 0.600 rather than always-cloud's 1.000, and v1.1 fails both axes at every
size either way.

## 2. Part 1 AUDITS

Run in an ISOLATED GIT WORKTREE pinned to commit `b2dbff2`, whose parent is session 1's
`13e357f`. **This matters: session 1 edits the same working tree, and my first audit pass ran
while 78 lines of its uncommitted edits to `rollout.py`, `coordinator.py`, `flags.py` and
`arms_policy.py` were present.** That pass was discarded and everything below was re-run against
the pinned checkout, so no result here mixes in half-finished code. Every switch OFF.

The channel decomposition is self-checked: `delta_j` equals the seven channels summed to within
**4.4e-16 over 27,589 candidates**, so the split below is arithmetic and not an estimate.

### 2.1 Blind-spot audit (1a). The fraction of candidates where a channel is EXACTLY zero

Fleet trace, seed 0, 8 devices, 600 s. Reads: 1.0 means the channel is exactly zero for every
candidate of that kind.

| candidate kind | n | DeltaJ == 0 | sh_own | sh_harm | rc_util | **z** | cont | **sv** | backlog |
|---|---|---|---|---|---|---|---|---|---|
| `piece_release` | 3,395 | 0.079 | 1.0 | 0.961 | **0.999** | **1.0** | **0.999** | **1.0** | 0.118 |
| `state_promote_rebuild` | 17,231 | 0.197 | 1.0 | 0.710 | **1.000** | **1.0** | **0.999** | **1.0** | 0.197 |
| `recall_admit` | 20 | 0.0 | 1.0 | 1.0 | 0.700 | **1.0** | 0.300 | **1.0** | 0.100 |
| `sh_admit` | 4,322 | 0.0 | 0.0 | 1.0 | 1.0 | **1.0** | 1.0 | **1.0** | 0.485 |
| `sh_dispatch` | 2,621 | 0.0 | 0.0 | 0.627 | 1.0 | **1.0** | 1.0 | **1.0** | 0.991 |

**F-A1 (HIGH). Every benefit channel is structurally dead for the robot-relevant kinds, while
both cost channels are live.** For `piece_release` and `state_promote_rebuild`, which together
are 20,626 of the 27,589 candidates, the deficit is exactly zero always, the state value is
exactly zero always, and the RC utility and continuation value are exactly zero in 99.9 percent
of candidates. The only channels that move are `sh_harm` and `backlog`, and both are COSTS.
**A decision assembled from live costs and dead benefits can only come out zero or negative.**
This is the whole robot failure in one table, and it is stronger than the per-term findings
already in `study_live2_coord.md`.

**F-A2 (HIGH). `sv_delta`, spec 5.3's state value, is exactly zero for EVERY candidate of EVERY
kind, 27,589 of 27,589.** The state value never differs between the two branches of any
counterfactual, so it cannot influence any decision at all. From the code: `_terminal` recomputes
`state_value` from `dev.history` and the device's demand, and no candidate action modifies either
within the horizon, so the two branches compute the same sum. Proposed fix for session 1: either
make a candidate's effect on residency visible to `state_value`, or record in the spec map that
5.3's state value is inert in round 1. **Not implemented here.**

**Corroborated at every size.** The two dead channels are not an artefact of one cell: `z` and
`sv_delta` are exactly zero for EVERY kind in all four cells, fleet traces at 4, 8 and 16 devices
and the 32-device synthetic fixture, which is **124,354 candidates in total** (13,175 + 27,589 +
46,374 + 37,216).

**F-A3 (HIGH). The deficit channel is exactly zero in 27,589 of 27,589 candidates**, confirming
session 1's V1 and V8.1 at every candidate kind rather than only for recall. With B1 on, `z`
rises on the device but `_z_term` aggregates only over the `opps` rows, and before the RC tail
those rows carry `task="SH"` only, so `(device, "RC")` never enters the sum.

### 2.2 Wiring and scale audit (1c)

**Erratum E1, against my own tool.** The first version of the dead-writer check used a negative
lookbehind on "." and therefore matched only bare calls, so it reported `bump_z` as having NO
production caller while session 1's B1 was calling `dev.bump_z(...)` from `arms_policy.py:307`.
The regex is corrected and the finding is restated below. The original wrong output is recorded
here rather than quietly replaced.

| writer | production callers | dead? |
|---|---|---|
| `Device.bump_z` | `live2/arms_policy.py:307` (B1), `policy/coordinator.py:719` | no |
| **`Coordinator.update_deficit`** | **none** | **yes** |

**F-A4 (medium). `Coordinator.update_deficit` is still dead.** `spec_map.py` names it as the code
that implements spec 3.3 and 7.6, and B1 wired the arm straight to `bump_z` instead, so the
documented entry point has no caller. Not a behaviour defect, since B1 does update the counter,
but the spec map now points at dead code. Proposed fix: either route B1 through
`update_deficit` or amend the spec map.

Fields READ but never WRITTEN in production (extending session 1's list, with its two now
resolved by F1 and B1):

| field | declaration | reads | note |
|---|---|---|---|
| `Device.controller` | `Any = None` | 1 | no controller is ever attached |
| `HistoryBelief.unsent_frames` | `int = 0` | 1 | pinned at zero |
| `Job.p_finish` | `float = 1.0` | 2 | both occurrences are documentation strings in `spec_map.py`, so nothing reads it in logic: a DEAD FIELD |

Fields WRITTEN but never READ:

| field | writes | note |
|---|---|---|
| **`Link.reachable`** | 3 | **F-A5 (medium).** Written in three places and read nowhere; the policy reads `p_reachable_within_hs` instead. Either the write is pointless or the wrong field is being read |
| `Opportunity.device_utility` | constructor only | set and never read |
| `Opportunity.served_by` | constructor only | set and never read |

**F-A6 (HIGH). Every DeltaJ term on one scale, which shows the benefits are dwarfed by one to
two orders of magnitude.** Absolute values, fleet trace at 8 devices:

| kind | term | p50 abs | p90 abs | max abs | range |
|---|---|---|---|---|---|
| `state_promote_rebuild` (17,231) | **backlog** | **1.084** | **2.071** | 2.596 | -2.596 to 0.078 |
| | rc_util | 0.0 | 0.0 | 0.083 | -0.083 to 0.0 |
| | cont | 0.0 | 0.0 | **0.035** | -0.035 to 0.035 |
| | sh_harm | 0.0 | 0.069 | 0.203 | -0.203 to 0.0 |
| | z, sv | 0.0 | 0.0 | **0.0** | dead |
| `recall_admit` (20) | **backlog** | 0.138 | **1.474** | 3.152 | -3.152 to 0.0 |
| | cont | **0.035** | 0.035 | 0.035 | 0 to 0.035 |
| | rc_util | 0.0 | 0.083 | 0.083 | 0 to 0.083 |
| `sh_admit` (4,322) | sh_own | **0.055** | 0.069 | 0.089 | 0.044 to 0.089 |
| | backlog | 0.205 | 0.205 | 0.205 | -0.205 to 0.143 |

**The median backlog charge on a rebuild promotion, 1.084, is 31 times the largest continuation
credit that exists (0.035) and 13 times the largest RC utility (0.083).** No deficit scaling at
these magnitudes can flip such a decision, which is the quantitative reason B1 changed nothing
and the RC tail moved only two or three questions. By contrast `sh_admit` has its own gain
(p50 0.055) within a factor of four of its backlog charge, and SH is served.

### 2.3 Assumption-versus-reality audit (1b)

| assumption in the model | reality | gap, where measurable |
|---|---|---|
| **`competing_s = 0`**: the continuation schedule assumes the job has the engine to itself | the engine is shared with up to 4,322 dashcam instants per 600 s | session 1 measured the consequence: `p_finish` is pinned at 1 and the PRIORITY class is unreachable, so A3 is inert. My S1-against-S2 pair bounds it: the SAME question is served on an idle engine and refused with 8 dashcams |
| **pi_0 progresses deferred jobs** in the reference branch | nothing in the live arm releases those pieces | session 1's trace: action progress `{}` against reference progress `{job: 2}`, `delta_j = -0.634` |
| the deficit reaches the objective | `_z_term` sums only over `opps` rows | zero in 27,589 of 27,589 candidates (F-A3) |
| spec 5.3's state value discriminates | it is identical in both branches | zero in 27,589 of 27,589 (F-A2) |
| `HistoryBelief.staleness_s` carries catch-up cost | it was never written before F2 | F2 now writes it; session 1 measured 316 and 353 decisions moving at 4 and 8 devices |
| a history can be believed HOST-WARM | I could not drive one from the trace interface | **S6 NOT REALISABLE: observed readiness stayed COLD under 12 dashcams of pressure.** Either host offload does not occur in a dry run, or it needs a condition the trace cannot express |
| eviction chooses between warm histories | no eviction occurred under my pressure | **S9 NOT REALISABLE** |

## 3. Part 2 RESULTS

Pass/fail against the expectations pre-registered in section 1, which were committed first and
are not restated here. `n/a` is a scenario reported NOT REALISABLE under its pre-registered
caveat, not a silent pass.

| id | v1.0 | v1.1 (all four switches) | what happened |
|---|---|---|---|
| S1 | **PASS** | **PASS** | released at 42.7 s against a 45.0 s deadline, idle engine |
| S2 | **FAIL** | **FAIL** | not served at all, AND dashcam releases are 888 against 888 in the paired run, so **the question cost nothing and gained nothing: it was simply invisible** |
| S3 | PASS | PASS | declined, with 1 decline recorded. Passes on the DISJUNCTIVE branch "declined at admission", not by serving |
| S4a | **FAIL** | **FAIL** | neither pieces nor a whole rebuild released, not served. MOT1 measured P2048 achieving 0 extra missed with the robot answered at 3.37 s |
| S4b | PASS | PASS | not served, no admit-then-starve. The pre-registered expectation allows this, since MOT1 shows no option serves both |
| S4c | **FAIL** | **FAIL** | roomy host (256 GiB), still not served and no session action taken. MOT1 measured HOST-WARM achieving 0 extra missed AND a 0.686 s answer |
| S5 | **FAIL** | **PASS** | v1.0 starved both questions; v1.1 serves both at 42.7 s. **The only scenario the v1.1 switches fix** |
| S6 | n/a | n/a | NOT REALISABLE: readiness stayed COLD |
| S7 | PASS | PASS | 27,031-token history, no release, no GPU charged |
| S8 | PASS | PASS | instants arriving after their own deadline: 0 of 120 sent |
| S9 | n/a | n/a | NOT REALISABLE: no eviction occurred |
| S10 | PASS | PASS | 40 dashcams and 3 robots: 830 decisions, 0 defers, no unbounded growth |
| S11 | PASS | PASS | preloaded history, served |
| S12 | PASS | PASS | deadline already passed, 0 releases |
| **totals** | **8 of 12 scored** | **9 of 12 scored** | 2 not realisable in both |

**The three remaining failures are all the same thing: a robot question is refused whenever
dashcams are present, at loads MOT1 measured as serving both.** S1 against S2 isolates it to the
load, not the history size, the deadline or the memory tier, since only the dashcam count differs
between them. S4c shows a roomy host does not help either.

**Two passes should be read narrowly.** S3 and S4b pass on the "declined at admission" branch of
a disjunctive expectation, which the pre-registration permits precisely because MOT1 shows no
option serves both at heavy load. They are not evidence of good service.

## 3. Part 2 RESULTS

Filled in below.

## 4. Part 3 OFFLINE COMPARISON

**A SCREEN, NOT EVIDENCE, and it is OPTIMISTIC FOR COVEX.** The dry run prices the engine from
the SAME committed cost curves COVEX's own model uses, so its predictions and the simulated world
cannot disagree. No baseline that does not model the engine is given that advantage. Nothing here
may be cited as a result.

Seed 0, 600 s, tight memory, 50 : 50, pinned commit `b2dbff2`. The committed scorer RAN without
refusing on these runs. Robot and dashcam figures below are RELEASE counts, a proxy for service.

| n | arm | robot on time | of | robot fraction | dashcam fraction | dashcam released |
|---|---|---|---|---|---|---|
| 4 | **policy-core v1.0** | 1 | 9 | **0.111** | 0.999 | 2,174 |
| 4 | **policy-core v1.1** | 2 | 9 | **0.222** | 0.978 | 2,128 |
| 4 | edf | 8 | 9 | 0.889 | 0.999 | 2,174 |
| 4 | llf | 7 | 9 | 0.778 | 0.999 | 2,174 |
| 4 | always-cloud-fcfs | 9 | 9 | **1.000** | 0.999 | 2,174 |
| 4 | device-only | 0 | 9 | 0.0 | 0.0 | 0 |
| 8 | **policy-core v1.0** | 0 | 20 | **0.000** | **0.487** | 2,107 |
| 8 | **policy-core v1.1** | 3 | 20 | **0.150** | 0.927 | 4,008 |
| 8 | edf | 11 | 20 | 0.550 | 0.999 | 4,322 |
| 8 | llf | 18 | 20 | 0.900 | 1.000 | 4,324 |
| 8 | always-cloud-fcfs | 20 | 20 | **1.000** | 1.000 | 4,324 |
| 16 | **policy-core v1.0** | 0 | 35 | **0.000** | **0.075** | 657 |
| 16 | **policy-core v1.1** | 7 | 35 | **0.200** | 0.449 | 3,910 |
| 16 | edf | 8 | 35 | 0.229 | 0.626 | 5,457 |
| 16 | llf | 21 | 35 | 0.600 | 0.658 | 5,732 |
| 16 | always-cloud-fcfs | 30 | 35 | **0.857** | 0.913 | 7,959 |
| 16 | device-only | 0 | 35 | 0.0 | 0.0 | 0 |

**F-A7 (HIGH, and the most serious finding in this study). policy-core is last among the cloud
arms on robot service at EVERY size, and at 8 and 16 devices it is also worse than every cloud
baseline on DASHCAMS.** v1.0 releases only 48.7 percent of dashcam instants at 8 devices and
**7.5 percent at 16**, against edf's 99.9 and 62.6 percent. v1.1 repairs much of that, to 92.7
and 44.9 percent, but remains below edf at both sizes. **So this is not a robots-against-dashcams
trade-off: at 8 and 16 devices COVEX is behind on both axes at once.** The earlier diagnosis
looked at robot service alone and so could not see this.

`llf` is the strongest deadline-aware baseline here, at 0.778, 0.900 and 0.600 robot fraction
while holding dashcams at or above edf.

**A caution about the screen's own generosity.** `always-cloud-fcfs`, which has no admission
control at all, comes out best or joint-best on both axes at every size. That is a property of
the dry run rather than of the arm: the modelled engine absorbs everything sent to it, so an arm
that sends everything cannot be punished. It is the clearest possible demonstration that this
comparison is a screen. It does not rescue COVEX, though, because COVEX loses to arms that are
disadvantaged in exactly the same way.

## 5. GATE (D124)

**Both halves of the gate FAIL.**

**Half one: are all behaviour tests passing for the latest v1.1 switch set? NO: 9 of 12 scored
scenarios pass, 3 fail.**

| scenario | v1.1 verdict |
|---|---|
| S1, S3, S4b, S5, S7, S8, S10, S11, S12 | PASS (9) |
| **S2** | **FAIL**, one robot question with 8 dashcams: not served, and the dashcams lose nothing, so the question was invisible |
| **S4a** | **FAIL**, MOT1 light_tight: no pieces released and not served, where MOT1 measured 0 extra missed with the robot answered at 3.37 s |
| **S4c** | **FAIL**, MOT1 heavy_roomy: not served even with a 256 GiB host, where MOT1 measured HOST-WARM achieving 0 extra missed AND a 0.686 s answer |
| S6, S9 | n/a, NOT REALISABLE under their pre-registered caveats |

**Half two: is the offline comparison at least as good as the best baseline at every size? NO,
at every size, on both axes.**

| n | best baseline robot fraction | policy-core v1.1 | verdict | best baseline dashcam fraction | policy-core v1.1 | verdict |
|---|---|---|---|---|---|---|
| 4 | 1.000 (always-cloud-fcfs) | 0.222 | **FAIL** | 0.999 | 0.978 | **FAIL** |
| 8 | 1.000 (always-cloud-fcfs) | 0.150 | **FAIL** | 1.000 | 0.927 | **FAIL** |
| 16 | 0.857 (always-cloud-fcfs) | 0.200 | **FAIL** | 0.913 | 0.449 | **FAIL** |

Against the strongest DEADLINE-AWARE baseline, `llf`, rather than the unconstrained one, the
verdict is the same at every size: 0.778 against 0.222, 0.900 against 0.150, 0.600 against 0.200.

**Recommendation to the user: v1.1-fast should not start.** Speed work preserves decisions by
construction, and the decisions are what is failing. Two of the three failing scenarios are cases
MOT1 MEASURED as serving both workloads, so they are not impossible trade-offs; and F-A7 shows
dashcam service is also behind, so there is no axis on which the current policy is ahead.

The findings I judge most urgent for session 1, in order: **F-A6** (benefits are 13 to 31 times
smaller than the costs they must overcome, which bounds what any further credit channel can
achieve), **F-A1 and F-A2** (every benefit channel is dead for the robot-relevant kinds, and
spec 5.3's state value is dead for all 27,589 candidates), and **F-A7** (the dashcam collapse at
8 and 16 devices, which no previous report measured).


---

# 6. BEFORE-GROUND for D126 gate round one, measured on the F3 switch set

HEAD **`6f7b784`**, isolated worktree, clean. Switch set **B1 + F2 + F3 + A3, with F1 (`rc_tail`)
and F4 OFF**, which is the set D125 and D126 specify for v1.2. **This is NOT a gate round:** F5a,
F5b, F5c and v1.2 had not landed when it was taken. It exists so that D126's before-and-after sits
on identical candidate populations.

## 6.1 The finding that matters most for v1.2's starting point

**With F1 OFF, policy-core v1.1 is IDENTICAL to v1.0 at every size on both axes.**

| n | policy-core v1.0 | policy-core v1.1 (F1 off) | edf | llf | always-cloud (REPORTED, NOT GATING) |
|---|---|---|---|---|---|
| 4 | 0.111 / 0.999 | **0.111 / 0.999** | 0.889 / 0.999 | 0.778 / 0.999 | 1.000 / 0.999 |
| 8 | 0.000 / 0.487 | **0.000 / 0.487** | 0.550 / 0.999 | 0.900 / 1.000 | 1.000 / 1.000 |
| 16 | 0.000 / 0.075 | **0.000 / 0.075** | 0.229 / 0.626 | 0.600 / 0.658 | 0.857 / 0.913 |
| 32 | 0.014 / 0.134 | **0.014 / 0.134** | 0.069 / 0.284 | 0.222 / 0.332 | 0.458 / 0.453 |

Each cell is robot pooled fraction / dashcam released fraction. **Completed after the first
commit of this section**, which recorded the two 32-device rows as unfinished: `always-cloud-fcfs`
is 0.458 / 0.453 and `device-only` is 0.0 / 0.0. No verdict changes, since `always-cloud-fcfs` is
not gating under D127 and `device-only` sends nothing.

Worth one note in D127's favour: at 32 devices `always-cloud-fcfs` finally degrades, from 1.000
robot service at 4 and 8 devices to 0.458, so the screen does begin to bite on the unconstrained
arm at the largest size. That does not make it gating, and it does not help COVEX, which is behind
edf and llf on both axes at 32 as well.

**So every gain I reported for v1.1 came from F1, the RC tail, and v1.2 turns F1 OFF.** The
earlier v1.1 numbers (0.222, 0.150, 0.200 robot and 0.978, 0.927, 0.449 dashcam) were measured
with `rc_tail` ON. Remove it and the arm returns exactly to v1.0. **F3 on its own moves neither
axis at any size.**

**Under the D127 criterion, this set fails both axes at every size**, against edf and llf as the
gating baselines: robot 0.111 against 0.889, 0.000 against 0.900, 0.000 against 0.600, 0.014
against 0.222; dashcam 0.999 against 0.999 (equal at n=4), 0.487 against 1.000, 0.075 against
0.658, 0.134 against 0.332.

## 6.2 What F3 did change, in the audit

Fleet trace at 8 devices, same decomposition, identity self-checked to 8.1e-14.

| kind | n, before F3 | n, with F3 | DeltaJ == 0, before | with F3 | backlog p50 abs, before | with F3 |
|---|---|---|---|---|---|---|
| `state_promote_rebuild` | 17,231 | **3,400** | 0.197 | **0.998** | **1.084** | **0.0** |
| `piece_release` | 3,395 | 3,395 | 0.079 | 0.079 | unchanged | unchanged |

F3 removes four fifths of the promote-rebuild candidates and drives almost all of the remainder to
an exact zero tie: the backlog charge that dominated them is now zero at the median, but no benefit
channel took its place, so the candidate became a no-op rather than a negative. **`piece_release`
is untouched.**

## 6.3 Two carried-forward facts that are STILL true, and both are gate-relevant for v1.2

**F-A2 stands: the state value is still exactly zero for every candidate of every kind.** The
`sv` column is 1.0 for all five kinds with F3 on. v1.2's Jhat counts "state value at T_r" and
ABANDON is defined as keeping "the state value of what is built", so **both uses are inert until
F5b lands.** P9 tests this explicitly in round two.

**F-A3 stands, and it has a consequence for v1.2 that is worth flagging before the code is
written.** The `z` column is 1.0 for all five kinds **even though B1 is ON here**: the deficit
counter rises on the device but cannot reach `_z_term`, whose aggregation only sees the `opps`
rows. The only mechanism that ever put RC rows into those is F1's `rc_tail_zrows`, and **D125
turns F1 OFF for v1.2**. v1.2's evaluation is specified to count "every device's deficit term from
the B1 realised-outcome counters credited at each opportunity's own deadline", so **unless v1.2
adds its own RC-row routing, that term will be inert too.** Reported now rather than discovered in
round two.

## 6.4 Gate status

**Round one (F5a, F5b, F5c) is NOT SCORED: those commits had not landed.** Its expectations and
falsifiers are pre-registered in `f5_round_one_preregistration.json`, committed before any F5
result existed. **Round two (v1.2 and its six ablations) is NOT SCORED** for the same reason; its
ten scenarios are pre-registered in `v12_scenario_preregistration.json`.

**No `harden GATE PASS v1.2` commit has been or will be emitted on this evidence.** Nothing has
passed; the F3 set fails both axes at every size.


## 6.5 F-A8 (HIGH, NEW): the measured cause of F-A7 is the SH ADMISSION TEST, not the backlog units

D126 asked for the cause of the dashcam deficit and judged a units mismatch the likely
explanation. **Session 1's V20 refutes that hypothesis from the spec side** (`mu` is utility per
GPU-second at `policy_spec_v4.md:151` and `busy` sums `pr.gpu_s`, so the product is already
utility). **My before-ground refutes it independently from the measurement side**, and that is
worth stating because the two arguments are separate: F3 drove the promote-rebuild backlog charge
from a median 1.084 to **0.0** and the dashcam fraction did not move at all, staying at 0.487 and
0.075. **Varying the backlog magnitude by its whole median left the dashcam axis untouched.**

The actual cause is arithmetical and exact. Every instant is evaluated as an `sh_admit` candidate,
and the fraction admitted equals the fraction released:

| n | `sh_admit` candidates | with DeltaJ > 0 | admitted fraction | **measured dashcam released fraction** |
|---|---|---|---|---|
| 4 | 2,174 | 2,174 | **1.000** | 0.999 |
| 8 | 4,322 | 2,107 | **0.488** | **0.487** |
| 16 | 8,709 | 657 | **0.075** | **0.075** |

The agreement is exact to the three digits reported, and it holds identically with every switch
off and with the F3 set on. **So the dashcam deficit IS the SH admission test: COVEX admits
exactly those instants whose DeltaJ is positive, and as load rises that is 48.8 percent of them
at 8 devices and 7.5 percent at 16.** edf releases essentially all of them.

**Why they score non-positive is the exchange rate on the SH side.** From the scale table,
`sh_admit` carries an own gain of p50 **0.055** against a backlog charge of p50 **0.205**, so a
single instant's calibrated gain is about a quarter of the price its own work is charged. This is
F-A6's mechanism appearing on the monitoring path rather than the recall path.

**The consequence for the gate, stated before round one is scored.** Nothing currently queued
addresses this. F5a is refuted, F5b wires the state value (a channel dead for other reasons and
unrelated to SH), F5c is a routing change intended to be byte-identical, and **v1.2 is RC-only
with SH monitoring explicitly unchanged**. F-A6, the exchange rate itself, is NOT ADOPTED per
D126. **So on current plans the dashcam half of the D127 gate cannot be passed at 8, 16 or 32
devices**, and since D127 requires BOTH axes at EVERY size, the gate cannot pass on either round
unless something addresses SH admission. I report this rather than wait to discover it twice.

**Status of my pre-registered F5 expectations, with no expectation altered.** G1a and G1b were
written conditional on the F5a fix landing, and each carried an explicit falsifier. The premise
has been refuted upstream, so the falsifiers apply as written: for G1a, "the units were already
consistent and F-A7 has another cause", which F-A8 now names; for G1b, "the exchange rate stands
as measured and v1.2 long-window structure is the only remaining route". **These are not errata:
the expectations were conditional and their falsifiers fired.** G1c, G1d and G1e remain open and
testable when F5b and F5c land.
