# ONE PAGE FOR THE MORNING (D129), written by session 2

**Read this first.**

## THE PROVISIONAL FLAG MOVED, AND THEN CAME OFF. The trail, so the correction is visible

**What I first wrote, and it was wrong.** The H100 refused `d944361` and ran nothing, failing
`test_pieces_partition_the_history_with_no_gap_and_no_overlap` at C_inflight 8, and its report said
the defect affects `covex-v13` itself. On that basis I flagged **every covex row** in this report
as provisional.

**First correction, from session 1's direct test.** `covex-v13` does NOT have the defect: 5
sessions checked, 0 out of order, 0 overlapping. I verified the mechanism rather than taking the
result on trust. `PolicyCoreArm.decide` builds its session list as
`sorted(mat.items())` (`arms_policy.py:800`), one materialize per session per epoch, while the
piece machinery (`piece_tokens`) lives in `Pi0Edf`, which `LlfArm` subclasses. So the defect is
structurally in the **Pi0Edf family, which is my BASELINE set**, the opposite of what the H100
report said and of what I had flagged.

**Second correction, which is mine and goes further.** Moving the flag onto llf and edf would also
have been wrong. The arms I actually score are `edf`, `edf@8`, `edf@4` and `llf`, all of which run
with `piece_tokens = None` and therefore rebuild WHOLE. Measured on seed 4 at 16 devices, their
decision logs contain:

| arm | `release_whole` | `release_piece` |
|---|---|---|
| llf | 13 | **0** |
| edf C=8 | 14 | **0** |
| edf C=4 | 11 | **0** |

Not one piece decision in any of them. A whole rebuild is a single-element partition and cannot be
out of order with itself, so **the assertion that fails for `edf-piece1024` and `edf-piece2048`
cannot be exercised by any arm in my tables.** I have never scored a piece arm.

**So the flag comes off, candidate and baselines alike.** The 16-device table in section 13 that
reproduced session 1's figures exactly stands as measured. The authoritative confirmation is still
session 1's serialisation delta run, and if it shows dry-run numbers moving for the piece arms that
does not reach my rows, because my rows contain no pieces.

**What WOULD have been at risk if the first correction had stood**, and it is worth recording:
llf is the comparator the D127 gate is stated against and the arm that took seed 6 on both axes at
16 devices. A baseline re-run would have moved the gate itself, not just a column.

**Also still true: the dry-run screen is NOT uniformly optimistic for COVEX, and at 8 devices it
inverts the ranking against edf.**

## The headline: the screen is calibrated now, and it was misleading us at 8 devices

Applying the SAME delivery definition to the committed LIVE H100 pilot cells and to my dry runs,
seed 0, 600 s, tight memory:

| arm | n | dashcam dry to LIVE | robot dry to LIVE | the dry run |
|---|---|---|---|---|
| edf | 4 | 0.9991 to **0.9821** | 0.889 to **1.000** | OVERSTATES dashcam by 0.017 |
| edf | 8 | 0.9854 to **0.9267** | 0.000 to **0.100** | OVERSTATES dashcam by 0.059 |
| edf | 16 | 0.0172 to **0.0663** | 0.000 to 0.000 | UNDERSTATES by 0.049 |
| policy-core | 4 | 0.9991 to **0.9991** | 0.111 to 0.111 | matches exactly |
| **policy-core** | **8** | **0.4871 to 0.9478** | 0.000 to 0.000 | **UNDERSTATES by 0.461** |
| policy-core | 16 | 0.0747 to **0.0723** | 0.000 to 0.000 | matches |

**The ranking test at 8 devices, dashcam delivery:**

- **DRY: edf 0.9854 against policy-core 0.4871, edf ahead by 0.498.**
- **LIVE: edf 0.9267 against policy-core 0.9478, POLICY-CORE AHEAD by 0.021.**

**So the dry screen's dashcam verdict at 8 devices is an artefact.** It is pessimistic for
policy-core by 0.46 absolute and optimistic for edf by 0.06, and the two errors point in opposite
directions, which is what flips the order. **Every dashcam conclusion I drew at 8 devices from the
dry run, including my own F-A7 headline, does not survive this calibration.** The likely reason is
consistent with F-A9: COVEX's admission conditions on PREDICTED congestion, the dry engine is
slower than the real one, so COVEX sees congestion that is not there and refuses work. edf does not
condition on congestion, so it is barely affected.

**What this does NOT excuse.** The ROBOT gap is real and confirmed live: at 4 devices live edf
answers **9 of 9** robot questions on time and live policy-core answers **1 of 9**. At 8 devices
live edf answers 2 of 20 and policy-core 0 of 20. **The robot axis is a genuine failure, measured
on the H100, not a screen artefact.**

## VERSION KEY, so the tables below are not read against the wrong code

Session 1 has moved faster than my scoring. Every table in this report carries the version it was
measured on, and they are not interchangeable:

| label | switch set | commit scored | where |
|---|---|---|---|
| v1.0 / v1.1 | pre-planner | `7dbb448` and earlier | sections 2 to 7 |
| **v1.2** | planner_rc + plan_latest + replan + B1 + F2 + F3 | `9fd423a` | sections 8 to 11, **including the leaderboard** |
| **v1.3-scarcity** | v1.2 + `mu_mode="scarcity"` (CLIPPED form), derived kappa, edf default 8 | `ed8ef56`, re-based to `700f248` | section 12, **INCONCLUSIVE** |
| v1.3-regraded | the scarcity price normalised by measured service, verified to vary 0.5 to 0.889 | `0c2c22e` | session 1's, the real negative |
| **v1.3-fast (RELEASE)** | v1.2 planner, **mu = 0**, `honour_job_priority` ON, `write_staleness` OFF, `admit_floor_c` 8 | **`d944361`** | **section 13** |

Three different objects carry the name "v1.3" and they give different answers. Section 12 is NOT a
verdict on the release.

**Everything headed "policy-core" or "v1.2" below section 8 is v1.2.** It is NOT a verdict on
v1.3, which section 12 scores separately.

## THE RECONCILIATION: the price is GRADED on dashcam and BINARY on robots

**Updated by the control in section 15, which falsified my first attribution.** The same price cut
that lifted 16-device dashcam from 0.1230 to 0.5857 and 0.0624 to 0.4943 bought **zero** extra
robot deliveries. The code change at `700f248` contributes essentially nothing: five of six
control cells are identical. So the price is a graded control on one axis and a threshold on the
other, and **a single scalar price cannot be tuned for both**. That is the finding.

## How the robot half of that works

Two results of mine and session 1's looked contradictory overnight. They are not, and together
they say more than either does alone.

- I measured that cutting the price roughly tenfold, from an EWMA whose p50 reached 9.835 to a cap
  of 1.0, bought **ZERO** additional robot deliveries.
- Session 1 measured that removing the price **to exactly 0** buys **8 of 20** robot answers at 8
  devices, with dashcam 0.9330 against the EWMA's 1 of 20 and 0.7998. Better on BOTH axes.

Both are right. At a price of 1.0 a 2.41 GPU-second rebuild is still charged about 2.41 against a
maximum available credit near 1.835, so it still loses. At 0 it is free and clears. **The robot
axis needs the charge at or near zero, and any plausible nonzero price blocks it.** It is not a
graded tradeoff: it is a threshold. That is the exchange rate again, now triangulated from three
independent directions, and it is why session 1's release sets mu = 0 rather than tuning a price.

**What this does NOT license:** "pricing predicted backlog at all is worse than not pricing it" is
established for the robot axis against THESE deadlines and THIS credit scale. It is not a general
result about scarcity pricing, and the saturation episode is the reason to be careful: the first
form's numbers looked like a verdict on pricing and were a verdict on a constant.

## F-A2 IS SETTLED and it closes a v1.2/v1.3 design question

The state-value channel is substantively non-zero in 96.6 percent of branches and **cancels
EXACTLY between them**, 12,898 of 12,898 candidates, max absolute difference 0.0, at both commits
and under both F2 settings. It contributes nothing to any decision. The cancellation is structural:
state value is computed for FUTURE arrivals from `device.history[rep]`, which a dispatch action
does not change, so both branches evaluate the identical prefix.

**So v1.2 and v1.3 both count "state value at T_r" inertly, and ABANDON reduces to declining the
remainder.** Anything that wants ABANDON to differ has to make the retained prefix differ BETWEEN
branches. Section 14 reconciles all three disputed readings; the short version is that `state_value`
is a caching wrapper whose cache hides 94 percent of calls, and the two call sites bind it
differently so a patch on one module silently misses the other.

## D131 HEADLINE: the crossover is at 10 to 12 devices, and COVEX now loses at EVERY size

Two things I reported earlier are WITHDRAWN here rather than left standing beside the new numbers.

**1. The crossover is LOCATED and SHARP, and this is the result worth keeping.** Across sizes 4, 8,
10, 12, 14, 16 and 32 on all four seeds, the baselines hold a robot fraction of 0.81 to 0.89 at 10
devices and fall to 0.41 to 0.60 at 12 (llf) and 0.17 to 0.50 (edf C=8). One step, all four seeds
together, no graceful region. **COVEX has no crossover because it has no collapse**: it is roughly
flat, 0.35 to 0.56 at 10 and 0.24 to 0.42 at 16. It does not improve under load, it simply fails to
degrade while the baselines fall past it. This confirms section 18's queueing prediction at its most
specific point, and it says the interesting regime is NARROW and just above 10 devices.

**2. I WITHDRAW the 32-device win, and the capacity column.** My "wide margin win at 32 devices"
was measured against edf and llf only. With the published arms in the bar per D131, at 32 devices
mooncake matches COVEX on dashcam (0.4527 to 0.4463) and more than doubles it on robots (0.454 to
0.202), and the published field leads COVEX on robots at every size. On the D71/D82 conjunct,
**v1.3-fast meets capacity in ZERO of 28 cells** while the published arms meet it in 12 of 28. I
also predicted capacity would fail everywhere for everyone; it does not, 30 of 196 cells pass, so
that prediction was wrong too.

**The honest summary: COVEX does not beat the best baseline at any size on either axis, and meets
the capacity target nowhere.** No GATE PASS string is emitted and none is close.

## THE MECHANISM FINDING THAT STANDS: the robot axis is a QUEUEING problem, not a GPU-budget problem

I flagged the published field as uncitable until its cost accounting was checked. **It is checked
and it is clean**: a recall rebuild costs eco-llm 2.404 s against llf's 2.420 s, and a monitor
release costs every arm 0.395 s exactly. No uncharged work, no E36 free lunch. The numbers stand.

What the check revealed is better than a defect. llf, edf and eco-llm issue the **same 38 recall
requests** and are charged the **same service**. They differ only in delay against a 5.0 s deadline:

| arm | recall delay p50 | on time |
|---|---|---|
| edf C=8 | 6.36 s | 3 of 38 |
| llf | 5.81 s | 9 of 38 |
| **eco-llm** | **2.34 s** | **35 of 38** |

And llf's delays are packed against the deadline: relaxing it to 6.0 s gives 20 on time and 7.0 s
gives 29. **Two seconds triples the deliveries.**

**This explains the "binary price" from the other side.** The robot axis looked like a threshold in
the price because the delay distribution is a spike at the deadline, not because the price is a
threshold. So: **COVEX does not need a better price, it needs recall released earlier relative to
the monitor stream.** `honour_job_priority` does this and the release already has it ON, which is
why it reaches 13 to 17 robots where v1.2 reached 1 to 2. The target is now a number: **get the
median recall delivery under 5.0 s.**

## Best version so far, and its standing

**The release is `d944361`, "v1.3-fast": the v1.2 planner with the price of GPU time set to ZERO,
`honour_job_priority` on, `write_staleness` OFF and `admit_floor_c` 8.** Scored on all four dev
seeds and all four sizes in section 13, pinned and scored BY NAME. Session 1's 16-device table
**reproduces exactly**, to four decimal places on dashcam and exactly on robot counts, for the
candidate and both baselines.

| n | gate verdict, D127, on delivery |
|---|---|
| 4 | **FAIL** both axes, four seeds |
| 8 | **FAIL** both axes (dashcam here is UNRELIABLE per my own calibration, E6) |
| 16 | **FAIL**. Dashcam loses in all four seeds; robots win 3 of 4 and LOSE seed 6 |
| 32 | **PASS** on the letter, both axes, all four seeds, by a wide margin |

**No GATE PASS string is emitted: the release fails at three of four sizes.**

**Two things to carry into the morning.** First, **seed 6 breaks the pattern at 16 devices**: llf
wins it outright on both axes, 10 robots to 9 and 0.9792 dashcam to 0.9085. "Robots double the
baseline on every seed" is 3 of 4, not 4 of 4, and the spread 14, 13, 17, 9 is wider than three
seeds showed. That is the second time tonight that adding seed 6 changed a conclusion.

Second, **at 32 devices the release wins both axes in all four seeds by a wide margin**, dashcam 25
to 35 times the baselines and 12 to 21 robots against 0 to 2. I am not calling it a pass, because
the majority of dashcam frames still miss and the baselines are collapsed. What it establishes is
that **COVEX's value appears under heavy overload, where work-conserving schedulers collapse** -
which is exactly what the queueing account above predicts.

The two tables below this line are OLDER OBJECTS, kept for the audit trail:
**v1.2** (planner_rc + plan_latest + replan + B1 + F2 + F3; F1 and F4 off), at `9fd423a`.

| n | robot delivered, v1.2 / edf / llf | dashcam delivered, v1.2 / edf / llf | gate |
|---|---|---|---|
| 4 | 2 of 9 / 8 of 9 / 7 of 9 | 0.9977 / 0.9991 / 0.9991 | FAIL both |
| 8 | 1 of 20 / 0 of 20 / 4 of 20 | 0.7998 / 0.9854 / 0.9942 | FAIL both, **dashcam unreliable per the calibration** |
| 16 | 1 of 35 / 0 of 35 / 0 of 35 | 0.3687 / 0.0172 / 0.0294 | **PASS both** |

**What changed to get there:** the two-timescale planner decides once at admission over the job
lifetime instead of re-scoring each piece every period. Its measured benefit comes mainly from what
it REFUSES: declining cold rebuilds outright lowers engine occupancy, which lowers the queue
backlog charge on every monitoring candidate, which raised SH admission from 0.4871 to 0.8003 at 8
devices. That is a queueing effect expressed through the admission test.

**What still fails:** the robot axis at every size, live and dry. Every cold-rebuild plan scores
between -0.598 and -2.521 and is declined, so the exchange rate is the binding constraint. mu is
the mechanism: it rises 6.8 times from 4 to 16 devices while engine occupancy FALLS threefold, so
refusing work raises the price of work (F-A9).

**Release commit:** none. **Neither gate round passes and no `harden GATE PASS v1.2` string has
been emitted.**

## THE SECOND HEADLINE: raising edf's release bound beats the entire planner

Leaderboard on seeds 4, 5 and 6 (section 11). **edf at C_inflight = 8, which D128 makes its
default, beats v1.2 in EVERY cell on BOTH axes**: dashcam 0.999 against 0.49 to 0.92 at 8 devices
and 0.96 against 0.06 to 0.59 at 16, robot 15 to 18 of about 19 against v1.2's 1 to 4.

**This withdraws my own earlier verdict.** The "v1.2 passes both axes at 16 devices" result was
measured against edf at C_inflight = 4, which collapses to 0.0105 to 0.0130 dashcam delivery at 16
devices where the same scheduler at C_inflight = 8 delivers 0.9558 to 0.9654. **The release bound,
not the policy, dominated that comparison.**

**And v1.2 is far less stable.** Across seeds 4, 5 and 6 its 16-device dashcam delivery ranges
0.062 to 0.590, a tenfold spread, while edf C=8 ranges 0.9558 to 0.9654. **A candidate this
seed-sensitive cannot be judged on seed 0 alone.**

**The actionable line for session 1: a one-parameter change to a trivial scheduler outperforms the
two-timescale planner everywhere tested.** Before more structure goes into COVEX, it is worth
measuring COVEX at a larger release bound, since F-A8 and F-A9 both say its problem is refusing
work under predicted congestion and C_inflight is the other lever on work in flight.

## What is NOT yet done, stated plainly

The D129 leaderboard now covers seeds 4, 5 and 6 at 8 and 16 devices (section 11). Seed 0 at
32 devices, and the published-system field from session 3 (D130), are NOT built. No session-1 candidate had
landed when this was written, so I spent the time on the calibration instead, which D129 ranks
highest and which turned out to invalidate a dry-run conclusion. No session-1 candidate had landed all night, so the time went to the calibration and the
seed sweep. No `baselines-published ready:` commit from session 3 had landed either, so the
published field is empty rather than missing.

---

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


---

# 7. DEFINITION AUDIT: DISPATCH against DELIVERY. The contradiction resolved, and two errata against me

HEAD **`58a1abb`**, isolated worktree. Both readings computed from the SAME dry run, so the
difference cannot be a fixture, a device mix or a HEAD difference. **The answer is (a): the two
numbers measure different things, and both are arithmetically correct.**

## 7.1 The two definitions

| name | definition | what it says |
|---|---|---|
| **dispatch** | a RELEASE decision carries the question's `opportunity_id` before its own deadline (`_harness.released_before_deadline`) | work was DISPATCHED in time |
| **delivery** | `outcomes.jsonl`: `t_delivered` is set and `t_delivered <= t_opportunity + deadline_s` | SERVICE: an answer reached the application in time |

My offline comparison reported **dispatch**. Session 1 read **delivery**. A release at 4.9 s
against a 5 s deadline counts as dispatch-on-time even though the rebuild then takes seconds and
the answer lands late, which is exactly what happens.

## 7.2 Both numbers, side by side, same runs

Robot questions:

| n | arm | dispatched | dispatch before deadline | answered at all | **ANSWERED ON TIME** |
|---|---|---|---|---|---|
| 4 | policy-core | 1 | 1 | 1 | **1** |
| 4 | edf | 9 | 8 | 9 | **8** |
| 4 | llf | 7 | 7 | 7 | **7** |
| 8 | policy-core | 0 | 0 | 0 | **0** |
| 8 | **edf** | **19** | **11** | **19** | **0** |
| 8 | llf | 18 | 18 | 18 | **4** |
| 16 | policy-core | 0 | 0 | 0 | **0** |
| 16 | **edf** | 19 | 8 | 19 | **0** |
| 16 | **llf** | 21 | 21 | 21 | **0** |

**Session 1 is right, and my 0.550 for edf at 8 devices was a dispatch count.** 11 of 20 were
dispatched before their deadlines and **none of the 19 answered arrived in time.** Session 1's llf
figure of 4 reproduces exactly.

Dashcam instants, the same distinction applied, which I had not done before:

| n | policy-core | edf | llf |
|---|---|---|---|
| 4 | 0.9991 | 0.9991 | 0.9991 |
| 8 | **0.4871** | 0.9854 | 0.9942 |
| 16 | **0.0747** | **0.0172** | **0.0294** |

## 7.3 ERRATUM E2, against my own labelling

**My gate and comparison tables are headed "robot on time" and "dashcam fraction" while reporting
DISPATCH counts.** The JSON carried the caveat ("RELEASE counts, a proxy for service, not scored
outcomes"), but the table headings overstated what was measured, and the gate was scored on them.
The pre-registered expectations are untouched; this is a labelling error in how I reported the
measurement, and the corrected figures are in 7.2.

## 7.4 ERRATUM E3: F-A7 is REVERSED at 16 devices under delivery

I reported F-A7 as the most serious finding in this study: that COVEX is also worse on dashcams.
**Under the delivery metric that is true at 8 devices and FALSE at 16 devices.** At 16 devices
policy-core delivers **0.0747** of instants on time against edf's **0.0172** and llf's **0.0294**,
so it is ahead by a factor of four. The reason is visible in the same table: edf and llf dispatch
5,453 and 5,728 instants but only 150 and 256 arrive in time, because they flood an engine that
cannot keep up, while policy-core dispatches 657 and delivers 651 of them.

**F-A7 stands at 8 devices (0.487 against 0.985 and 0.994) and is withdrawn at 16 devices.** F-A8's
mechanism is unchanged and now explains both directions: COVEX admits only what scores positive,
which costs it at 8 devices and protects it at 16.

## 7.5 Which metric the gate should be judged on

**Delivery, and not dispatch.** The gate asks whether COVEX serves the workload, D82's pooled
robot metric is a service metric, and a dispatch that misses its deadline is not service. My own
JSON already called dispatch a proxy. **I state this before scoring, and I am not choosing the
reading that favours any arm**: delivery is worse for COVEX at 8 devices on dashcams and better at
16, and it lowers the robot bar for COVEX at 8 and 16 while raising it at 4.

## 7.6 The consequence D127's gate now has to carry, flagged explicitly

**edf delivers ZERO robot answers on time at 8 AND 16 devices, and llf delivers zero at 16.** So
"at least as good as the best scheduling baseline" on the robot axis is a bar of **0.20 at 8
devices (llf's 4 of 20) and 0.0 at 16 devices**. Against a baseline scoring zero, that half of the
gate is satisfied by scoring zero.

The gate under the delivery metric, as it stands today on the F3 set:

| n | robot: policy / best scheduling | verdict | dashcam: policy / best scheduling | verdict |
|---|---|---|---|---|
| 4 | 0.111 / **0.889** (edf) | **FAIL** | 0.9991 / 0.9991 | PASS (equal) |
| 8 | 0.000 / **0.200** (llf) | **FAIL** | 0.4871 / 0.9942 | **FAIL** |
| 16 | 0.000 / 0.000 (both) | PASS, trivially, both are zero | 0.0747 / 0.0294 | **PASS** |

**Overall: still FAIL**, because D127 requires both axes at every size and 4 and 8 fail. But the
shape is different from what I reported: COVEX is behind at the small and middle sizes and ahead
on dashcams at the largest, and the robot bar at 8 and 16 is near zero because the baselines
themselves deliver almost nothing.

**A recommendation I owe the user, given 7.6.** A gate that can be passed by delivering zero
because the baseline delivers zero is not measuring what it is meant to measure. The robot axis
may need an absolute floor, for example D82's own pooled target, rather than only a
relative-to-baseline test. That is a methodological change, so it is proposed and NOT applied.


---

# 8. GATE ROUND ONE, scored on the F5 set that exists

HEAD **`4f91e8d`** for the backlog decomposition, **`fd3bcd7`** and its parent **`7f83546`** for
the F5c equivalence test. Isolated worktrees, clean.

| item | state | my pre-registered expectation | verdict |
|---|---|---|---|
| **F5a** backlog units | **REFUTED, no change made.** Spec 3.5 puts both mu and the backlog in utility per GPU-second, and the term fires in 6 of 5,016 rollouts | G1a, G1b | **FALSIFIERS FIRED** (recorded at `58a1abb`, before this round) |
| **F5b** state value | **NOT IMPLEMENTED and escalated.** Session 1 stopped it and retracted its own claim: `_state_value` returns 0.009216 on all 1,365 calls and is not broken; F2 is what zeroes the sum | G1c | **NOT TESTABLE as written**: there is no new wiring to test |
| **F5c** deficit routing | **LANDED** at `fd3bcd7`; `_z_resolve` now calls `Coordinator.update_deficit`, so spec 3.3 and 7.6's named entry point has a production caller for the first time | G1e | **PASS**, verified independently |

## 8.1 G1e verified independently, not accepted on report

`fd3bcd7` against its parent `7f83546`, B1 on, 8 devices, seed 0, 600 s:

| quantity | F5c | parent | |
|---|---|---|---|
| decisions differing | **0 of 2,220** | | **byte-identical** |
| `z_updates` | 4,338 | 4,338 | identical |
| `z_successes` | 2,107 | 2,107 | identical |
| `z_misses` | 2,231 | 2,231 | identical |

**G1e PASSES exactly as pre-registered.** Session 1's own figure was 0 of 1,157 on its fixture;
mine is 0 of 2,220 on the seed-0 fleet trace, so the result holds on both. I note that F5c
deliberately carries no switch, on the ground that a switch over provably identical behaviour
would be dead by construction, and my measurement supports that reasoning.

## 8.2 F-A2 and session 1's retraction are BOTH right, and the synthesis matters for F5b

This needs stating carefully, because it looked like a contradiction and is not.

- **Session 1 measures the state-value SUM PER BRANCH.** With B1 and F3 it is median 0.009216 and
  exactly zero in 28.1 percent of evaluations; adding F2 makes it exactly zero in 100 percent.
- **I measure `sv_delta`, the DIFFERENCE between the two branches of a candidate's own
  counterfactual.** That is exactly zero in 124,354 of 124,354 candidates.

Both are true because they are different quantities. **And the synthesis is the decision-relevant
one: with F2 OFF the state value is non-zero per branch (0.009216) and STILL CANCELS in DeltaJ.**
My v1.0 audit had every switch off, F2 included, and `sv_delta` was exactly zero for every kind
there too.

**So making the state value non-zero per branch would not, on its own, make it influence a single
decision.** What a decision sees is the difference, and the difference is zero whether F2 is on or
off. **P9's status is updated accordingly: it must test BOTH that the value is non-zero per branch
AND that it DIFFERS between branches, and the second is the one that decides whether the channel
can affect anything.** F5b as conceived targets the first.

This also sharpens what F2's escalated semantics ruling is about. F2 zeroes a per-branch quantity
that was already decision-irrelevant, so on my measurement the F2 question is about the
correctness of the staleness figure (150.7 s of staleness for a 6,781-token history against a 10 s
RC deadline) rather than about recovering a channel that could change decisions.

## 8.3 THE DECISIVE QUESTION ANSWERED: `a6_backlog` contributes NOTHING to `sh_admit`

`Rollout._terminal` (`rollout.py:712-713`) prices
`mu_term = -mu * (max(busy - H, 0) + a6_backlog)`. Decomposed per branch and as a delta over every
`sh_admit` candidate, with the two parts checked against `mu_term` to an identity error of
**exactly 0.0**:

| n | `sh_admit` | mu p50 | **queue delta** non-zero | queue delta p50 abs | **a6 delta** non-zero | a6 CANCELS | `a6_backlog` itself non-zero |
|---|---|---|---|---|---|---|---|
| 4 | 2,174 | 1.444 | 0.025 | 0.0 | **0.000** | **1.000** | **0.000** |
| 8 | 4,322 | 4.278 | 0.516 | **0.205** | **0.000** | **1.000** | **0.000** |
| 16 | 8,709 | 9.835 | 0.926 | **0.471** | **0.000** | **1.000** | **0.000** |

**The queue part is the ENTIRE backlog charge on `sh_admit`. The A6 part contributes nothing, and
it is stronger than cancelling: `a6_backlog` is itself exactly ZERO in BOTH branches of every
`sh_admit` candidate at every size.** `_prefix_risk` produces restore work only for at-risk RC
jobs, and an SH admission neither creates nor endangers one.

**So the escalated `a6_backlog` units defect cannot explain F-A8 and would not help the dashcam
axis at all. It is worth the user's attention for RECALL only.** That is the single number the
coordinator asked for, and it settles the question against the more valuable of the two
possibilities.

## 8.4 What the decomposition adds to F-A8: mu grows with load, and that is the amplifier

The same table shows the mechanism of F-A8 completely, and it was not visible before:

| n | mu p50 | fraction of `sh_admit` with a non-zero queue charge | queue charge p50 abs | **fraction REFUSED** |
|---|---|---|---|---|
| 4 | 1.444 | 0.025 | 0.0 | 0.000 |
| 8 | 4.278 | 0.516 | 0.205 | 0.512 |
| 16 | 9.835 | 0.926 | 0.471 | 0.925 |

**The fraction carrying a non-zero queue charge tracks the fraction refused to within 0.004 at
every size.** A non-zero queue backlog charge is very nearly necessary and sufficient for refusal.
And **the EWMA mu itself rises from 1.44 to 9.84 as load grows**, so the same queue excess is
priced almost seven times higher at 16 devices than at 4, while the per-instant gain stays at
p50 0.055. That is the amplifier: not one term being wrong, but mu rising with load while the gain
per instant does not.

**None of this is a defect I can point to**, which is worth saying plainly. The units are correct
(F5a), A6 does not reach it (8.3), and mu's estimator is off limits under D124. On the measurement,
the dashcam deficit at 8 devices is the designed objective working as specified, with the
exchange rate F-A6 described and D126 declined to adopt.

## 8.5 ROUND ONE VERDICT

**FAIL, and not close on the gating axes at 4 and 8 devices.** F5c is byte-identical by design and
changes nothing; F5a was refuted and changed nothing; F5b does not exist. **So round one's
measured state is the F3 before-ground of section 6, scored on DELIVERY in section 7.6:** fail at 4
on robots, fail at 8 on both, pass at 16 on both with the robot half passing only because every
arm delivers zero.

**No `harden GATE PASS v1.2` commit is emitted.**


---

# 9. GATE ROUND TWO: v1.2, scored on DELIVERY at 4, 8 and 16 devices

HEAD **`f19e04d`** (my round-one commit on top of session 1's v1.2 at `9fd423a`). Isolated
worktree, clean. Switch set `planner_rc + plan_latest + replan + deficit_update + write_staleness
+ realistic_competing`, F1 and F4 off, `kappa` at its default.

**The 8 and 16 device cells session 1 could not finish are filled in here**, which was the single
most valuable gap. All figures are DELIVERY, per section 7.5.

## 9.1 The gate, both axes, every size

**Robot questions answered on time, out of the pooled total:**

| n | **v1.2** | edf | llf | best scheduling | verdict |
|---|---|---|---|---|---|
| 4 | 2 of 9 = **0.222** | 8 of 9 = 0.889 | 7 of 9 = 0.778 | 0.889 | **FAIL** |
| 8 | 1 of 20 = **0.050** | **0 of 20 = 0.000** | 4 of 20 = 0.200 | 0.200 | **FAIL** |
| 16 | 1 of 35 = **0.029** | **0 of 35 = 0.000** | **0 of 35 = 0.000** | **0.000** | **PASS** |

**Dashcam instants delivered on time, as a fraction of those offered:**

| n | **v1.2** | edf | llf | best scheduling | verdict |
|---|---|---|---|---|---|
| 4 | **0.9977** | 0.9991 | 0.9991 | 0.9991 | **FAIL**, by 0.0014 |
| 8 | **0.7998** | 0.9854 | 0.9942 | 0.9942 | **FAIL** |
| 16 | **0.3687** | 0.0172 | 0.0294 | 0.0294 | **PASS**, 12.5x ahead |

**ROUND TWO VERDICT: FAIL overall, because D127 requires both axes at every size. But v1.2
PASSES BOTH AXES AT 16 DEVICES**, and that is the first time COVEX has been ahead of both
scheduling baselines on both measures at any size.

## 9.2 What v1.2 actually bought, against the F3 before-ground on identical ground

| n | dashcam delivery: F3 set to v1.2 | robot delivery: F3 set to v1.2 |
|---|---|---|
| 4 | 0.9991 to 0.9977, a small loss | 1 to 2 of 9 |
| 8 | 0.4871 to **0.7998**, a large gain | 0 to 1 of 20 |
| 16 | 0.0747 to **0.3687**, a 4.9x gain | 0 to 1 of 35 |

**v1.2 improves the DASHCAM axis substantially at 8 and 16 devices, which is not what the design
note predicted.** v1.2 is RC-only and SH monitoring is explicitly unchanged, so the gain is
indirect: the planner declines most RC plans, which leaves engine capacity for monitoring. It also
confirms session 1's own reading from the other side, that the plans score negative and are mostly
declined. **The clearest statement is that v1.2's measured benefit on this screen comes mainly
from what it refuses to do, not from what it plans to do.**

## 9.3 F-A9 (HIGH, NEW): mu moves OPPOSITE to scarcity, and that is a feedback loop

The coordinator asked whether mu tracks scarcity. Measured over a full run, mu beside an
in-flight occupancy proxy (the same quantity the release bound reads; it is NOT true GPU
utilisation and is labelled as a proxy):

| n | mu p50 | mu p90 | in-flight mean | **fraction of periods with ANY work in flight** | GPU KV fraction p50 |
|---|---|---|---|---|---|
| 4 | 1.445 | 1.661 | 1.090 | **0.773** | 0.0 |
| 8 | 2.178 | 4.278 | 1.054 | **0.464** | 0.0 |
| 16 | **9.835** | 9.835 | **0.332** | **0.092** | 0.0 |

**mu rises 6.8 times from 4 to 16 devices while occupancy FALLS by a factor of three.** At 16
devices the engine has nothing in flight in 90.8 percent of periods and the KV cache is empty at
the median, yet GPU-seconds are priced almost seven times higher than at 4 devices where the
engine is busy 77 percent of the time.

**So mu is not a scarcity price, and the measurement confirms the hypothesis as stated.** mu is an
EWMA of the realised marginal utility per GPU-second of the last released item, which is the price
of the BEST USE. The consequence is a positive feedback loop, and it is the mechanism underneath
F-A8:

1. load rises, so more candidates carry a non-zero queue backlog charge (0.025, 0.516, 0.926);
2. admission falls (1.000, 0.488, 0.075), so only the highest-value items are released;
3. the realised marginal utility per GPU-second of those items is therefore HIGHER;
4. mu, being an EWMA of exactly that, rises (1.445, 2.178, 9.835);
5. the higher mu prices the next candidate's work higher, so admission falls further.

**Refusing work raises the price of work.** That is a spiral rather than a static exchange rate,
and it explains why the deficit at 16 devices is so much worse than a linear reading of F-A6
would predict. It is a measurement; mu is untouched and no fix is proposed here.

## 9.4 Ablations, and the identity session 1 asked me to report rather than skip

Reported as measured. Session 1 found F2 on and off identical and both of its ablations identical,
attributing it to there being little for them to act on when most plans are declined. **My
comparison reproduces the same insensitivity**: the v1.2 switch set with `write_staleness` on
gives the figures above, and section 6's F3 before-ground already showed F2 changing no outcome
measure. I ran the v1.2 set as one configuration rather than the six separate ablations, because
with plans declined in 6 of 8 and 9 of 10 evaluations the ablations differ only in paths that are
not taken; **that is a limitation of this round and I state it rather than claim coverage I do not
have.** The six ablations remain pre-registered and unrun.

## 9.5 Three PROVISIONAL settings I am reporting as unvalidated

Session 1 recorded these as overnight provisional decisions and I carry them into the gate record:

1. **`kappa = 1.0` with NO committed source.** No FIT/DEV completion-time residual set was found,
   so the safety factor the latest-start rule depends on is an **unvalidated setting, not a fitted
   value**. Every `PIECES(b)-LATEST` result in this round rests on it.
2. **State value at `T_r` wired as specified but inert while F2 is on** (100 percent zero against
   28.1 percent without F2). Combined with my section 8.2 synthesis, the channel is
   decision-irrelevant either way, since it cancels between branches.
3. **ABANDON reduces to declining the remainder** where the retained state value is zero, which by
   point 2 is always, on this configuration.

## 9.6 ROUND TWO GATE, in plain pass and fail

| | 4 devices | 8 devices | 16 devices |
|---|---|---|---|
| robot axis | **FAIL** | **FAIL** | **PASS** |
| dashcam axis | **FAIL** | **FAIL** | **PASS** |

**NEITHER ROUND PASSES. No `harden GATE PASS v1.2` commit is emitted, and emitting one would be
wrong on this evidence.**

The honest summary for the morning: **v1.2 is a real improvement on the dashcam axis at 8 and 16
devices and the first configuration to lead both scheduling baselines on both axes at any size,
and it is still far behind them at 4 and 8.** The binding obstacle is the exchange rate, now
measured to be self-reinforcing through mu (F-A9), which D124 and D126 put off limits.


## 9.7 ERRATUM E4: F-A8's MECHANISM survives, its CONSEQUENCE claim is FALSIFIED

I wrote in section 6.5 that because v1.2 is RC-only and SH is explicitly unchanged, "the dashcam
half of the D127 gate cannot be passed at 8, 16 or 32 devices" on current plans. **The measurement
falsifies that.** v1.2 raised dashcam delivery from 0.4871 to 0.7998 at 8 devices and from 0.0747
to 0.3687 at 16, touching no SH code.

**My error was an inference, not a measurement.** I reasoned that a change which edits no SH code
cannot affect SH admission. That ignores the coupling through SHARED ENGINE OCCUPANCY: `busy` is
fleet-wide, so RC work raises the queue backlog charge on every `sh_admit` candidate.

**The mechanism half of F-A8 survives, and the arithmetic forces it.** F-A8's identity is that the
dashcam delivered fraction EQUALS the `sh_admit` positive fraction, measured to three digits at 4,
8 and 16 devices in two switch sets. An instant cannot be delivered unless it was admitted, so
delivery is bounded above by admission. v1.2 delivers 0.7998 at 8 devices, therefore **its
`sh_admit` positive fraction must be at least 0.7998 and cannot be the 0.488 of v1.0.** The
coordinator's proposed test, "`sh_admit`'s positive fraction unchanged while delivery rises",
describes a state that cannot exist: **admission necessarily rose, and it rose because the input
to the test changed.**

The route is the one section 8.3 already isolated. The queue part `-mu * max(busy - H, 0)` is the
ENTIRE backlog charge on `sh_admit`, with `a6_backlog` contributing exactly nothing. v1.2 declines
most cold rebuilds at admission instead of admitting them and dithering per piece, so less RC work
reaches the engine, `busy` falls, `max(busy - H, 0)` falls, more instants score positive, and more
are admitted and delivered. **That is a queueing effect expressed through the valuation, not a
change in how instants are valued.**

**The corrected statement of F-A8**, which I adopt and which matches the coordinator's reframing:
*the SH admission test gates dashcam service, through the queue backlog charge; because that
charge is fleet-wide, anything that reduces engine occupancy relieves it, including an RC-only
change.* The exchange rate on the robot axis is untouched by this and remains the binding
constraint there, with every cold-rebuild plan still scoring between -0.598 and -2.521.

**Empirical confirmation, now recorded.** The arithmetic bound required the `sh_admit` positive
fraction under v1.2 at 8 devices to be at least 0.7998. Measured from the release counts on the
same runs, where F-A8 established that the released-monitor count equals the `sh_admit` positive
count exactly at every size:

| n = 8 | monitor instants offered | released, hence ADMITTED | fraction |
|---|---|---|---|
| v1.0 | 4,326 | 2,107 | **0.4871** |
| **v1.2** | 4,326 | **3,462** | **0.8003** |

**0.8003 satisfies the bound of 0.7998, and admission rose by 1,355 instants.** So the direct
number confirms the inference rather than contradicting it: **admission rose, and the dashcam gain
is expressed THROUGH the SH admission test, not around it.** This is inferred from release counts
under F-A8's identity rather than from a fresh candidate-level audit; that audit was stopped once
the release counts gave the same quantity at a fraction of the cost, since the planner's
long-window rollouts under capture were taking longer than the answer was worth.

## 9.8 ERRATUM E5, against my own instrumentation again

My `capture_delta_j` wrapper declared the v1.1 signature of `Rollout.run` by name. v1.2's planner
calls `rollout.run(fleet, horizon_s=..., rc_rows=True)`, so every planner evaluation raised
`TypeError` and the first v1.2 audit produced nothing. The wrapper now passes arguments through
unchanged. **This is the second time my instrumentation, rather than the policy, produced the
anomaly**, after E1's regex, and both are recorded rather than quietly fixed. It is also why the
v1.2 audit in 9.7 is late rather than missing.


---

# 10. CALIBRATION OF THE SCREEN AGAINST THE LIVE H100 (D129 item 4)

Read-only over the committed live pilot cells in
`results/orchestration/live2/pilot/runs3/`, which their own study labels PILOT and not round-1
results; nothing here changes that label. The SAME delivery definition is applied to both sides,
so the two are comparable: `t_delivered` set and `t_delivered <= t_opportunity + deadline_s`.

## 10.1 Every live cell, measured

| cell | n | window | dashcam delivered | robot delivered |
|---|---|---|---|---|
| edf | 4 | 600 s | 0.9821 | 9 of 9 |
| edf | 8 | 600 s | 0.9267 | 2 of 20 |
| edf | 16 | 600 s | 0.0663 | 0 of 35 |
| policy-core | 4 | 600 s | 0.9991 | 1 of 9 |
| policy-core | 8 | 600 s | 0.9478 | 0 of 20 |
| policy-core | 16 | 600 s | 0.0723 | 0 of 35 |
| always-cloud-fcfs | 8 | 120 s | 0.8320 | 6 of 6 |
| b9 | 8 | 120 s | 0.8477 | 5 of 6 |
| utility-per-cost | 8 | 120 s | 0.8294 | 6 of 6 |
| edf | 8 | 120 s | 0.8698 | 0 of 6 |
| edf-piece1024 | 8 | 120 s | 0.9792 | 0 of 6 |
| edf-piece2048 | 8 | 120 s | 0.9622 | 0 of 6 |
| policy-core | 8 | 120 s | 0.9961 | 0 of 6 |
| device-only | 8 | 120 s | 0.0 | 0 of 6 |

The 120 s step-1 cells are a different window and are not compared against my 600 s dry runs, but
they corroborate the direction: at 8 devices over 120 s live policy-core delivers 0.9961 of
instants against live edf's 0.8698.

## 10.2 The correction factor to apply when reading the leaderboard

| axis and size | dry error | how to read a dry result |
|---|---|---|
| dashcam, n = 4 | dry overstates by about 0.017 for edf, exact for policy-core | a dry win under 0.02 is not a win |
| **dashcam, n = 8** | **dry understates policy-core by 0.461 and overstates edf by 0.059** | **the dry run cannot rank COVEX against edf at this size at all** |
| dashcam, n = 16 | dry understates edf by 0.049, matches policy-core | a dry edf figure here is pessimistic |
| robot, n = 4 | dry understates edf by 0.111, exact for policy-core | dry is pessimistic for edf |
| robot, n = 8 | dry understates edf by 0.100, exact for policy-core | dry is pessimistic for edf |
| robot, n = 16 | exact for both | usable |

**The single rule for reading the leaderboard: at 8 devices, treat the dashcam axis as
uninformative about the COVEX-against-edf ordering until a live cell confirms it.** The errors at
that size are large and of opposite sign for the two arms.

## 10.3 ERRATUM E6: the direction of the screen's bias was assumed, not measured, and the
assumption was wrong at the size that mattered

Every version of this report, following the brief, carried the label that the screen is
"OPTIMISTIC FOR COVEX" because the dry run prices the engine from the same curves COVEX's model
uses. **That reasoning is sound for the VALUE a candidate can claim, and it is wrong for the
SERVICE it actually delivers.** The dry engine is slower than the live one, so a policy whose
admission conditions on predicted congestion refuses work it would have served live. The label
stays on the value side and is corrected here on the service side.

This is the fourth erratum against my own work tonight and the most consequential, because it was
carried through every earlier gate verdict at 8 devices. **It does not change the 16-device
results, where dry and live agree to within 0.003 for policy-core, nor the robot axis, which live
confirms.**


---

# 11. LEADERBOARD, seeds 4, 5 and 6 (D129). edf at C_inflight 8 WINS EVERY CELL

HEAD **`554fe95`**, pinned worktree. Delivery, 600 s, tight, 8 and 16 devices. Seeds 1, 2 and 3
are reserved for round 1 and the harness refuses them by name. **The candidate column is v1.2**,
not v1.3; see the version key at the top and section 12.

**Why these edf columns are trustworthy, and session 1's own may not have been.** Session 1's
`700f248` records that before that commit `make_arm` silently DISCARDED kwargs for every
non-policy arm, so `make_arm("edf", c_inflight=8)` quietly returned the DEFAULT arm. My harness
does not go through `make_arm` for these columns: it constructs `A.Pi0Edf(None, c_inflight=N)`
directly (`_harness.py:155`), which is why the C=8 against C=4 separation below is a real
measurement and not an artefact. Any edf-with-C_inflight number produced through `make_arm`
before `700f248` is a default-arm number wearing a C_inflight label.

**dashcam delivered / robot delivered on time:**

| seed | n | **v1.2** | **edf C=8** | edf C=4 | llf |
|---|---|---|---|---|---|
| 4 | 8 | 0.586 / 1 of 21 | **0.9993 / 18 of 21** | 0.9986 / 1 | 0.9977 / 4 |
| 5 | 8 | 0.9219 / 4 of 17 | **0.9993 / 15 of 17** | 0.9867 / 2 | 0.9842 / 5 |
| 6 | 8 | 0.4853 / 1 of 17 | **0.9991 / 15 of 17** | 0.9844 / 0 | 0.9920 / 2 |
| 4 | 16 | 0.5904 / 1 of 41 | **0.9609 / 3 of 41** | 0.0128 / 0 | 0.0189 / 1 |
| 5 | 16 | 0.1230 / 1 of 41 | **0.9558 / 8 of 41** | 0.0130 / 1 | 0.0203 / 0 |
| 6 | 16 | 0.0624 / 2 of 37 | **0.9654 / 4 of 37** | 0.0105 / 0 | pending |

## 11.1 Three findings, and the second one invalidates an earlier verdict of mine

**1. edf at C_inflight = 8 beats v1.2 in EVERY cell on BOTH axes.** Not narrowly: 0.999 against
0.49 to 0.92 on dashcams at 8 devices, and 0.96 against 0.06 to 0.59 at 16. On robots, 15 to 18 of
17 to 21 against v1.2's 1 to 4.

**2. The earlier "v1.2 passes both axes at 16 devices" was measured against a CRIPPLED baseline.**
edf at C_inflight = 4 collapses to 0.0105 to 0.0130 dashcam delivery at 16 devices, while the same
scheduler at C_inflight = 8 delivers 0.9558 to 0.9654. **The release bound, not the policy, was
the dominant factor in that comparison.** D128 makes 8 the default, so the correct baseline is the
one v1.2 loses to everywhere. **I withdraw the 16-device pass**: it stands only against edf C=4 on
seed 0, and that is not the gating baseline any more.

**3. v1.2 is far less STABLE than edf, which only the extra seeds could show.** Across seeds 4, 5
and 6, v1.2's dashcam delivery ranges 0.485 to 0.922 at 8 devices and **0.062 to 0.590 at 16**,
a tenfold spread. edf C=8 ranges 0.9991 to 0.9993 and 0.9558 to 0.9654. **A candidate this
seed-sensitive cannot be evaluated on seed 0 alone**, which is exactly what D129 asked these seeds
to reveal.

## 11.2 The most actionable thing I can tell session 1 tonight

**Raising the in-flight release bound from 4 to 8 outperforms the entire two-timescale planner, on
both axes, at every size and seed tested.** edf C=8 is a one-parameter change to a trivial
scheduler. Before more structure is added to COVEX, it is worth knowing what COVEX does at a
larger release bound, since F-A8 and F-A9 both say its problem is that it refuses work under
predicted congestion, and C_inflight is the other lever that governs how much work is in flight.

**Caveat, stated so it is not over-read:** these are dry-run numbers, and section 10 showed the dry
screen misranks COVEX against edf on the dashcam axis at 8 devices specifically. The 16-device
column is the trustworthy one (dry and live agree to within 0.003 for policy-core there), and that
is where the gap is widest.

# 12. The v1.3 SCARCITY-PRICE build, scored. CLASSIFIED INCONCLUSIVE, not a negative

**READ THE CLASSIFICATION FIRST.** This section scores the FIRST scarcity form, at `700f248`.
Section 12.4 shows its price sat at its cap at the median and at p90 at 8 and 16 devices. Session
1 probed the same thing directly and measured the cap in **92.9 percent of busy calls across five
distinct values**, then relabelled that whole run **INCONCLUSIVE rather than a negative**, on the
ground this section raises: a constant channel cannot test the claim, and these delivery numbers
are confounded with the tenfold price cut that came with it.

**So the delivery table below is NOT a settled verdict on pricing.** Under CLAUDE.md Rule 2 it is
the Inconclusive case: a design failure, not evidence that the mechanism does not exist. The
settled negative is session 1's REGRADED run, where mu was verified to vary over 0.5 to 0.889 with
nothing at the cap and COVEX still delivered 0 of 20 at 16 devices. The RELEASE, `d944361`
"v1.3-fast", is a third object again and is scored in section 13.

## 12.0 What this section still establishes

HEAD **`700f248`** (v1.3 at `ed8ef56` plus the work-conserving release floor), pinned worktree.
Delivery, 600 s, tight, seeds 4, 5 and 6. Predictions for this run were pre-registered BLIND in
`results/orchestration/live2/covex_harden/v13_preregistration.json`, committed at `edd5a0a`
before the result file existed.

**dashcam delivered / robot delivered on time:**

| seed | n | **v1.3** | v1.2 (was, at `554fe95`) | **edf C=8** | **llf (now C=8)** | edf C=4 |
|---|---|---|---|---|---|---|
| 4 | 8 | 0.8424 / 0 of 21 | 0.5860 / 1 | **0.9993 / 18** | **0.9993 / 18** | 0.9986 / 1 |
| 5 | 8 | 0.9803 / 4 of 17 | 0.9219 / 4 | **0.9993 / 15** | **0.9993 / 15** | 0.9867 / 2 |
| 6 | 8 | 0.4729 / 1 of 17 | 0.4853 / 1 | **0.9991 / 15** | **0.9991 / 15** | 0.9844 / 0 |
| 4 | 16 | 0.5907 / 1 of 41 | 0.5904 / 1 | 0.9609 / 3 | **0.9730 / 9** | 0.0128 / 0 |
| 5 | 16 | 0.5857 / 2 of 41 | 0.1230 / 1 | 0.9558 / 8 | **0.9684 / 9** | 0.0130 / 1 |
| 6 | 16 | 0.4943 / 1 of 37 | 0.0624 / 2 | 0.9654 / 4 | **0.9792 / 10** | 0.0105 / 0 |

## 12.1 GATE VERDICT, D127 criterion: FAIL in every cell, on both axes

v1.3 does not match the best scheduling baseline in any of the six cells. Dashcam: its best cell
is 0.9803 against 0.9993. Robot: it delivers 0, 4, 1, 1, 2 and 1 where the best baseline delivers
18, 15, 15, 9, 9 and 10. **No `harden GATE PASS` string is emitted.**

## 12.2 The baseline bar MOVED between my two scorings, and the cause is my own finding

`C_INFLIGHT_DEFAULT` changed from **4 to 8** at `700f248`, and `LlfArm` subclasses `Pi0Edf`, so it
inherits the change. That single default is the whole of llf's move at 16 devices, from 0.0189 to
0.9730 on seed 4. The `llf` column in section 11 is C=4 and the `llf` column above is C=8. Same
name, two settings. They must not be read against each other, and I have labelled both.

The honest consequence: **the gate got harder between v1.2 and v1.3 because session 1 adopted my
C_inflight finding as the default.** llf at C=8 is now the strongest arm at 16 devices, beating
edf C=8 on both axes in all three seeds. The bar v1.3 has to clear is higher than the bar v1.2
was measured against, and that is a real effect, not a regression in v1.3.

## 12.3 P2 is FALSIFIED, and it was my prediction

I pre-registered that capping the price at 1.0, against an EWMA price whose p50 reached 9.835 at
16 devices, is a roughly tenfold cut in the backlog charge, so cold rebuilds should move toward
admissible and **the robot axis should improve most at 16 devices**.

It did not. Robot at 16 devices went 1 to 1, 1 to 2, and 2 to 1. At 8 devices seed 4 went 1 to 0,
which is the wrong direction. The tenfold price cut did not buy a single additional robot
delivery. Whatever is binding the robot axis, it is not the magnitude of the backlog charge, and
that rules out the mechanism I expected as well as the one the change was motivated by.

**Where the gain actually landed:** the dashcam axis at 16 devices, on the two seeds that were
collapsed. Seed 5 went 0.1230 to 0.5857 and seed 6 went 0.0624 to 0.4943. Seed 4, which was not
collapsed, did not move at all, 0.5904 to 0.5907. That pattern is a floor being lifted, not a
uniform improvement, and it is consistent with the work-conserving release floor in `700f248`
rather than with the price change. Section 12.4 separates the two.

## 12.4 P1 CONFIRMED. The scarcity price is CLIPPED TO ITS CEILING exactly where capacity binds

Measured mu under `mu_mode="scarcity"` at `700f248`, 6,000 decision periods per size:

| n | mu p50 | mu p90 | mu min | mu max | in-flight mean | periods busy |
|---|---|---|---|---|---|---|
| 4 | **0.304** | 1.0 | 0.0 | 1.0 | 1.090 | 0.772 |
| 8 | **1.000** | 1.0 | 0.0 | 1.0 | 1.900 | 0.921 |
| 16 | **1.000** | 1.0 | 0.0 | 1.0 | 2.698 | 0.962 |

At 8 and 16 devices mu sits at its ceiling of 1.0 at the median AND at p90. The price is pinned.
It varies only at 4 devices, where the engine is idle 23 percent of periods and a single in-flight
request's predicted service is often under H = 0.5 s.

**This is the CONSTANT stopping condition of CLAUDE.md Step 2, in the two sizes that matter.** The
causal link "scarcity rises, so the price rises, so the policy declines less valuable work" cannot
be exercised at 8 or 16 devices, because the price has no headroom left to rise into. v1.3 may
NOT be credited with a scarcity MECHANISM at those sizes. The dashcam gain in 12.3 is real as a
number, but it is not evidence for the mechanism the change was motivated by, and section 12.3
already shows the gain has the signature of the release floor rather than the price.

**P3 does NOT fire, and this part is a genuine repair.** Under the EWMA price I measured mu rising
1.445, 2.178, 9.835 while occupancy FELL 1.090, 1.054, 0.332 (F-A9). Under the scarcity price mu
is non-decreasing in occupancy by construction and occupancy now RISES 1.090, 1.900, 2.698. The
positive feedback loop of F-A9, where refusing work raised the price of work, is broken. That is
the real achievement of v1.3 and it should be stated as such.

**The actionable defect, and it is one line.** `mu = mu_scale * min(1, busy_ahead / H)` divides by
the DISPATCH period H = 0.5 s, while the quantity in the numerator is the predicted service of
what is in flight, which is order 1 s for a single request. The ratio is therefore at or above 1
whenever anything at all is outstanding, and the clip discards everything above that. The fix is
not to raise `mu_scale`, which rescales a constant and leaves it constant. Either drop the clip,
or divide by a horizon on the scale of the deadlines being protected rather than the scale of the
dispatch period. As measured, in-flight mean reaches 2.698 at 16 devices, so an unclipped ratio
would still carry a usable two-to-threefold range across the sizes.

**Also dead here:** `gpu_kv_fraction` is p50 0.0 and max 0.0 at every size. KV is never a binding
resource in any of these cells, so no KV-pressure channel is being exercised at all.

# 14. F-A2 SETTLED. My original finding is confirmed, and all three readings now reconcile

Measured on ONE candidate population per condition, at two commits, with BOTH F2 settings, in
`state_value_entrypoints.py`. Outputs: `sv_entrypoints_82f178a.json`, `sv_entrypoints_700f248.json`.

**First, the three readings were never three readings of one quantity.** `state_value` is a
CACHING WRAPPER over `_state_value`, and its shadow mode asserts the two agree, so they cannot
differ in value. What differ are the call site and the quantity summarised:

| call site | binding | does a patch on `readiness` reach it? |
|---|---|---|
| `rollout.py:701` inside `_terminal` | imported INSIDE the function | **yes**, resolved at call time |
| `coordinator.py:21` used at `:544` | `from .readiness import state_value` at MODULE level | **no**, bound at import time |

Patching one module catches one call site and silently misses the other. This is the same trap my
`delta_j` capture already patches both bindings for.

**Second, the cache hides 94 percent of calls.** At 8 devices over 300 s the wrapper is called
105,852 times from the rollout and `_state_value` computes only 6,157 of them: **99,695 cache
hits**. An instrument on `_state_value` sees six percent of the traffic. Any call count like 1,365
is a cache-miss count, not a call count.

## 14.1 The three quantities, side by side

At `82f178a` (F2 fixed), identical in BOTH F2 conditions:

| quantity | result |
|---|---|
| per-call value, rollout site | 6,157 calls, 19.21 percent exactly zero, **exactly two distinct values: 0.0 and 0.009216** |
| per-call value, coordinator site | 9,359 calls, 12.62 percent exactly zero, same two values |
| per-branch SUM | 25,796 branches, **3.4 percent** exactly zero, so the channel is substantively ALIVE per branch |
| **between-branch DIFFERENCE** | **12,898 of 12,898 exactly zero, max absolute difference 0.0** |

At `700f248` (before the F2 fix):

| condition | per-call zero, rollout | per-branch SUM zero | between-branch DIFFERENCE zero |
|---|---|---|---|
| F2 off | 0.1921 | 0.034 | **1.0**, max abs 0.0 |
| F2 on | **1.0** | **1.0** | **1.0**, max abs 0.0 |

## 14.2 What this settles

**F-A2 is CONFIRMED and session 1's correction of it was a correction of a different quantity.**
The between-branch difference is exactly zero in every candidate at both commits in both F2
conditions, max absolute difference 0.0. Nothing I reported under F-A2 needs withdrawing.

**Session 1's FIRST reading reproduces, at the pre-fix commit only.** Its "100 percent zero with
F2 on" is exactly what I measure at `700f248` with F2 on, for the per-call value AND the
per-branch sum. Its "28.1 percent zero with F2 off" sits beside my 19.21 percent at the rollout
site and 12.62 percent at the coordinator site: a different sampling of the same two-valued
distribution, not a different phenomenon. The value 0.009216 it reported is the non-zero one of
the two values I see.

**Session 1's NEW reading does not reproduce at either commit.** I measure 19.21 and 12.62 percent
zero at `82f178a` in both F2 conditions, not 100 percent. The likeliest cause is instrumentation,
either a patched binding that the coordinator call site does not use, or a probe that saw only
cache misses. It is the anomaly, and the question it left open is answered by the two tables above.

**The F2 fix removed F2's effect on state value entirely.** At `700f248` turning F2 on drove every
per-call value to zero; at `82f178a` the two F2 conditions are byte-identical in every number. So
the earlier "F2 zeroes the sum" result was a symptom of the double charge that `82f178a` fixed.

## 14.3 The consequence for v1.2 and v1.3, which is the point of asking

**The state-value channel contributes EXACTLY NOTHING to any decision, at every commit tested,
under both F2 settings.** It is not zero because it is broken: it is substantively non-zero in 96.6
percent of branches and it CANCELS EXACTLY between them. The cancellation is structural, not a
staleness artefact, which is why the F2 fix moved the per-call values and left the difference at
exactly 0.0.

The mechanism is visible in the function's own docstring: state value is computed for FUTURE
ARRIVALS from `device.history[rep]`, and a dispatch action does not change that history, so both
branches evaluate the identical prefix and the identical `p_need`. The term is a constant offset
added to both sides of a comparison.

**Therefore v1.2 and v1.3 both count "state value at T_r" inertly, and ABANDON, defined as "keep
the state value of what is built", reduces to declining the remainder.** That is now measured
rather than argued, and it holds whatever F2 is set to. Any design that wants ABANDON to differ
from declining the remainder has to make the retained prefix differ BETWEEN branches; valuing it
identically on both sides cannot do it.

# 15. The v1.2 switch-set control, which FALSIFIES my own attribution in 12.3

I speculated in 12.3 that the 16-device dashcam gain had "the signature of the release floor
rather than the price". The control says otherwise and I withdraw the claim.

v1.2's switch set run on v1.3's code at `700f248`, against v1.2 at `554fe95` and the scarcity run:

| seed | n | v1.2 at `554fe95` | **v1.2 switches at `700f248`** | v1.3-scarcity at `700f248` |
|---|---|---|---|---|
| 4 | 8 | 0.5860 / 1 | 0.5860 / 1 | 0.8424 / 0 |
| 5 | 8 | 0.9219 / 4 | 0.9219 / 4 | 0.9803 / 4 |
| 6 | 8 | 0.4853 / 1 | 0.4853 / 1 | 0.4729 / 1 |
| 4 | 16 | 0.5904 / 1 | 0.5904 / 1 | 0.5907 / 1 |
| 5 | 16 | 0.1230 / 1 | 0.1230 / 1 | 0.5857 / 2 |
| 6 | 16 | 0.0624 / 2 | 0.1937 / 1 | 0.4943 / 1 |

Five of six cells are IDENTICAL between the two commits under the same switches. The code change
at `700f248`, release floor included, contributes essentially nothing to the candidate. **The
16-device dashcam gain is attributable to the SWITCH change, which is the price cut.**

**This sharpens the binary-price finding rather than contradicting it.** The same price cut that
bought 0.1230 to 0.5857 and 0.1937 to 0.4943 on the dashcam axis bought ZERO additional robot
deliveries. So the price is **graded on the dashcam axis and binary on the robot axis**. The two
axes do not respond to the same control in the same way, and a single scalar price cannot be tuned
for both. That is a stronger statement than either my P2 falsification or the mu = 0 result alone,
and it is the version that belongs in the morning page.

# 16. THE PUBLISHED FIELD (D130), reported and NOT gating, and it needs checking before it is believed

Seed 4, 8 and 16 devices, delivery, at `700f248`. All 19 ported arms resolve and NONE errored.

**Fairness digest: no porting defect.** Twenty-three arms share one digest at 8 devices and the
same twenty-three share a second digest at 16 devices. The digest groups by FLEET SIZE, which is
correct because it is a property of the trace and the trace differs with fleet size. Within every
cell all arms are on identical ground. (My digest is the full 64-hex `fairness_digest` from
`run_meta.json`; the 16-character `85251b9b8ce7115b` quoted in D130 is a different rendering or a
different cell, so the two strings are not comparable and neither is evidence of a defect.)

**dashcam delivered / robot delivered on time, seed 4:**

| arm | n=8 | n=16 | in card scope? |
|---|---|---|---|
| **llf (gating)** | 0.9993 / 18 of 21 | 0.9730 / 9 of 41 | gate baseline |
| **edf C=8 (gating)** | 0.9993 / 18 of 21 | 0.9609 / 3 of 41 | gate baseline |
| b7-edf-feasibility | 0.9993 / 19 | 0.9045 / **34** | yes |
| eco-llm | 0.9993 / 19 | 0.8680 / **35** | yes |
| mooncake | 0.9993 / 19 | 0.9045 / **34** | yes |
| ekya | 0.9993 / 19 | 0.8982 / **33** | yes |
| routellm | 0.9993 / 19 | 0.8770 / **33** | yes |
| inar-vl | 0.9993 / 19 | 0.8770 / **33** | yes |
| clockwork | 0.9993 / 16 | 0.9558 / **26** | yes |
| preble | 0.9993 / 17 | 0.9780 / 12 | yes |
| uniscale | 0.5477 / 19 | 0.5239 / 33 | yes |
| attentionstore | 0.9993 / 18 | 0.9723 / 34 | **no, B-recall** |
| lmcache | 0.9993 / 18 | 0.9723 / 34 | **no, B-recall** |
| kvflow | 0.9993 / 19 | 0.8770 / 33 | **no, B-recall** |
| pensieve | 0.9993 / 19 | 0.8770 / 33 | **no, B-recall** |
| videostorm | 0.9993 / 19 | 0.8725 / 34 | **no, A-episodic** |
| r3-streaming | 0.0175 / 0 | 0.0174 / 0 | **no, A-episodic** |
| confidence-cascade | 0.0517 / 0 | 0.0695 / 0 | **no, A-episodic** |
| hybrid-llm | 0.0000 / 19 | 0.0000 / 36 | zero monitor decisions BY DESIGN |
| perllm | 0.0000 / 19 | 0.0000 / 36 | zero monitor decisions BY DESIGN |
| b10-blocking-aware | 0.0000 / 0 | 0.0000 / 1 | yes |

The two 0.0000 dashcam rows for `hybrid-llm` and `perllm` are the documented by-design behaviour
and are NOT failures. The three near-zero rows are all out-of-card-scope arms being run outside the
regime their card claims, which is what D130 said would happen.

## 16.1 The thing I will NOT report as a result until it is checked

**Seven in-scope published arms deliver 33 to 35 of 41 robot answers at 16 devices where the best
gating baseline delivers 9 and COVEX v1.3-fast delivers 14.** That is roughly four times llf on the
axis that has been the hard one all night, and it arrives the same evening the arms were ported.

I am flagging it, not reporting it. An identical fairness digest proves the arms saw the identical
TRACE. It does NOT prove they were charged the identical COSTS. The whole point of the mechanism
protocol is that a quantity which is correctly and consistently zero passes every consistency
check, and "the rebuild was never charged to the accelerator budget" is precisely the failure that
E36, E36b and E36c are precedent for. A four-times jump on the axis where every COVEX variant has
been stuck needs its cost accounting verified before anyone treats it as a bar.

**The specific check**, and it is the same one I ran on COVEX: instrument the accelerator-ms and
KV-bytes charged per released item for one of these arms and for llf on the same cell, and confirm
a cold rebuild costs the published arm what it costs llf. If it does, this is a real and important
result and the gate conversation changes. If it does not, it is a porting defect in the cost path
rather than a finding. **Until that check is recorded, no number in this section may be cited as a
bar that COVEX has to clear.** It is in section 17 as the next thing I run.

# 17. 32 DEVICES, on the SCARCITY build. Everything collapses together

Seeds 4, 5, 6 at `700f248`. **This is the superseded scarcity build, not the release.** Recorded
because it is the only 32-device candidate data until the release grid lands.

| seed | **v1.3-scarcity** | edf C=8 | edf C=4 | llf |
|---|---|---|---|---|
| 4 | **0.3459** / 2 of 84 | 0.0169 / 0 | 0.0029 / 0 | 0.0157 / 2 |
| 5 | **0.1243** / 3 of 79 | 0.0147 / 2 | 0.0035 / 0 | 0.0150 / 1 |
| 6 | **0.1571** / 0 of 75 | 0.0123 / 0 | 0.0021 / 0 | 0.0122 / 0 |

On the letter of the D127 criterion this is a PASS in all three seeds: COVEX is ahead of the best
scheduling baseline on dashcam by 8 to 20 times and is never behind on robots.

**I am not claiming it as a pass and no GATE PASS string is emitted.** Dashcam at 0.12 to 0.35
means two thirds to seven eighths of dashcam frames MISS, and the baselines are at 0.012 to 0.017.
Every arm is broken in this regime; the ranking among broken arms is not evidence that the SLO can
be met. I withdrew a 16-device pass once already for being a ranking inside a collapsed regime and
I am not going to repeat it at 32. It is also the wrong build.

# 18. THE PUBLISHED FIELD CHECKED. No porting defect, and the robot axis is decided by 3.5 SECONDS OF QUEUEING

Section 16.1 said no published number could be cited until the cost accounting was verified. It is
verified. The answer is better than a defect would have been.

## 18.1 Costs ARE charged identically. The flag is cleared

Per-request service charged on seed 4 at 16 devices, split by request kind:

| arm | `release_monitor` mean | `release_recall` reqs | `release_recall` mean | total latency s |
|---|---|---|---|---|
| llf | 0.395 s | 38 | **2.420 s** | 3440.3 |
| edf C=8 | 0.395 s | 38 | **2.420 s** | 3406.0 |
| eco-llm (published) | 0.395 s | 38 | **2.404 s** | 3063.1 |
| b7-edf-feasibility | 0.395 s | 34 | 2.082 s | 3167.3 |

A recall rebuild costs the published arms what it costs llf, to three significant figures, and a
monitor release costs every arm 0.395 s exactly. There is no uncharged work and no E36-style free
lunch. **The published numbers are sound and may now be cited.**

## 18.2 What actually separates them, and it is not GPU time

llf, edf and eco-llm all issue the SAME 38 recall requests and are charged the SAME service. They
differ only in when the answer comes back, against a recall deadline of **5.0 s**:

| arm | recall delivery delay, p50 | min | max | on time |
|---|---|---|---|---|
| edf C=8 | 6.36 s | 4.29 | 11.69 | **3** of 38 |
| llf | 5.81 s | 3.00 | 9.73 | **9** of 38 |
| eco-llm | **2.34 s** | 0.39 | 6.83 | **35** of 38 |

The work is identical. The queueing delay is not. eco-llm returns the median recall answer in 2.34
s where llf takes 5.81 s, and the deadline sits at 5.0 s between them.

## 18.3 The cliff, which explains the "binary price" from the other side

llf's recall delays are packed right against the deadline:

| deadline | llf recalls on time |
|---|---|
| 5.0 s (actual) | 9 of 38 |
| 5.5 s | 13 |
| 6.0 s | 20 |
| 6.5 s | 27 |
| 7.0 s | 29 |

**Two seconds of relaxation triples the deliveries.** The population is concentrated at the
deadline, so any control that shifts the delay distribution a little moves a lot of items across
at once, and any control that shifts it slightly the wrong way moves none.

That is the same cliff the price reconciliation found from the other direction. The robot axis
looked BINARY in the price because the delay distribution is a spike at the deadline, not because
the price itself is a threshold. **The robot axis is a queueing-delay problem, not a GPU-budget
problem.** Spending less GPU does not help and pricing it differently barely moves it; releasing
recall work sooner, ahead of the monitor stream, is what moves it. eco-llm issues 910 fewer
monitor requests than llf and buys 26 robot answers with the room.

## 18.4 What this means for the gate and for session 1

The bar is real and it is higher than llf. Seven in-scope published arms deliver 33 to 35 of 41 at
16 devices on honestly charged work.

The actionable statement: **COVEX does not need a better price, it needs recall work released
earlier relative to the monitor stream.** `honour_job_priority` is the switch that does this and
the release `d944361` already has it ON, which is consistent with it reaching 13 to 17 robots where
v1.2 reached 1 to 2. The published field says the remaining headroom to 33 to 35 is also queueing,
and the measurement above gives the target directly: get the median recall delivery under 5.0 s.

# 13. THE RELEASE `d944361` SCORED, all four dev seeds, all four sizes. INDEPENDENT REPRODUCTION

Pinned worktree at **`d944361`**, candidate scored BY NAME as `covex-v13` from its own
`V13_RELEASE` block rather than by reconstructing switches. Delivery, 600 s, tight. Seeds 0, 4, 5,
6. No cell errored. Output: `leaderboard_v13fast_release.json`.

**dashcam delivered / robot delivered on time:**

| n | seed | **v1.3-fast** | llf (C=8) | edf C=8 | edf C=4 |
|---|---|---|---|---|---|
| 4 | 0 | 0.9812 / 4 of 9 | 0.9991 / 7 | 0.9991 / 8 | 0.9991 / 8 |
| 4 | 4 | 0.9860 / 2 of 8 | 0.9991 / 8 | 0.9991 / 8 | 0.9991 / 8 |
| 4 | 5 | 0.9950 / 4 of 11 | 0.9991 / 8 | 0.9991 / 8 | 0.9991 / 8 |
| 4 | 6 | 0.9936 / 4 of 13 | 0.9991 / 11 | 0.9991 / 11 | 0.9991 / 11 |
| 8 | 0 | 0.9346 / 8 of 20 | 0.9991 / 18 | 0.9991 / 19 | 0.9854 / 0 |
| 8 | 4 | 0.9506 / 9 of 21 | 0.9993 / 18 | 0.9993 / 18 | 0.9986 / 1 |
| 8 | 5 | 0.9794 / 7 of 17 | 0.9993 / 15 | 0.9993 / 15 | 0.9867 / 2 |
| 8 | 6 | 0.9667 / 6 of 17 | 0.9991 / 15 | 0.9991 / 15 | 0.9844 / 0 |
| 16 | 0 | 0.8164 / **14** of 35 | 0.9633 / 6 | 0.9508 / 4 | 0.0172 / 0 |
| 16 | 4 | 0.8751 / **13** of 41 | 0.9730 / 9 | 0.9609 / 3 | 0.0128 / 0 |
| 16 | 5 | 0.8422 / **17** of 41 | 0.9684 / 9 | 0.9558 / 8 | 0.0130 / 1 |
| 16 | 6 | 0.9085 / 9 of 37 | 0.9792 / **10** | 0.9654 / 4 | 0.0105 / 0 |
| 32 | 0 | **0.4588 / 13** of 72 | 0.0130 / 0 | 0.0127 / 0 | 0.0055 / 0 |
| 32 | 4 | **0.4323 / 17** of 84 | 0.0157 / 2 | 0.0169 / 0 | 0.0029 / 0 |
| 32 | 5 | **0.4227 / 21** of 79 | 0.0150 / 1 | 0.0147 / 2 | 0.0035 / 0 |
| 32 | 6 | **0.4713 / 12** of 75 | 0.0122 / 0 | 0.0123 / 0 | 0.0021 / 0 |

## 13.1 Session 1's table REPRODUCES EXACTLY

Session 1 reported 16-device seeds 0, 4 and 5. Every figure matches mine to four decimal places and
every robot count matches exactly, for the candidate AND for both baselines: 0.8164 / 14, 0.8751 /
13, 0.8422 / 17, with llf at 6, 9, 9 and edf C=8 at 4, 3, 8. Two independent harnesses, one pinned
and scoring by name. **No disagreement to report.**

## 13.2 SEED 6 BREAKS THE PATTERN, and session 1's three seeds could not show it

"Robots roughly double the best baseline on every seed" holds on 0, 4 and 5. **It fails on seed 6,
where llf delivers 10 and v1.3-fast delivers 9, and llf also wins dashcam 0.9792 to 0.9085.** llf
wins seed 6 outright on both axes at 16 devices.

So the 16-device robot advantage is three seeds out of four, not four out of four. The spread
across seeds, 14, 13, 17, 9, is wider than three seeds suggested. This is exactly why the
leaderboard runs four seeds, and it is the second time this session that adding seed 6 changed a
conclusion.

## 13.3 GATE, D127 criterion, on delivery

| n | verdict |
|---|---|
| 4 | **FAIL** both axes, all four seeds |
| 8 | **FAIL** both axes, all four seeds (dashcam ranking here is UNRELIABLE, see below) |
| 16 | **FAIL**. Dashcam loses in all four seeds. Robots win 3 of 4 and LOSE seed 6 |
| 32 | **PASS** on the letter, both axes, all four seeds, by a wide margin |

**No `harden GATE PASS` string is emitted.** The release fails at three of four sizes.

**The 8-device dashcam rows carry my own calibration warning (E6, section 10).** Applying the
delivery definition to the committed live H100 cells showed the dry screen UNDERSTATES COVEX's
dashcam by 0.461 at 8 devices and inverts its ranking against edf. **No 8-device dashcam ranking
against edf in the table above may be claimed without a live cell.** The robot rows at 8 devices
are not subject to that warning.

## 13.4 The 32-device result is the real one, and it is consistent with section 18

At 32 devices v1.3-fast leads dashcam by 25 to 35 times (0.42 to 0.47 against 0.012 to 0.017) and
delivers 12 to 21 robots against 0 to 2, in all four seeds. That is a large, consistent,
four-seed win on both axes.

I am stating it more strongly than the scarcity build's 32-device rows in section 17, and the
reason is that those sat at 0.12 to 0.35 dashcam while these sit at 0.42 to 0.47, and the robot
margin is 12 to 21 against 0 to 2 rather than 0 to 3 against 0 to 2. The baselines are still
collapsed, so this remains a ranking in a regime where the SLO is missed by the majority of
dashcam frames, and I am not calling it a gate pass. **What it does establish is that COVEX's
value appears under heavy overload, where work-conserving schedulers collapse entirely.**

This is the same mechanism as section 18 seen from the other end. At 32 devices the monitor stream
saturates the engine, so llf's recall answers queue behind it and arrive after the 5.0 s deadline,
giving 0 to 2. v1.3-fast releases recall ahead of that stream via `honour_job_priority` and gets 12
to 21. The queueing account predicts exactly this crossover: the baselines win where there is
slack and lose where there is not.

# 19. D131. THE CROSSOVER LOCATED, THE CAPACITY CONJUNCT, AND TWO OF MY OWN CLAIMS OVERTURNED

196 cells, no errors. Sizes 4, 8, 10, 12, 14, 16, 32 on seeds 0, 4, 5, 6. Candidate scored BY NAME
at `d944361`. Published arms now GATING per D131. Capacity from the committed scorer's own
`attainment`, targets not restated on my side. Output: `leaderboard_d131_crossover.json`.

## 19.1 THE CROSSOVER IS BETWEEN 10 AND 12 DEVICES, AND IT IS SHARP

Robot on-time fraction, per seed, across the transition:

| n | llf: seeds 0 / 4 / 5 / 6 | edf C=8: seeds 0 / 4 / 5 / 6 | v1.3-fast: seeds 0 / 4 / 5 / 6 |
|---|---|---|---|
| 8 | 0.900 / 0.857 / 0.882 / 0.882 | 0.950 / 0.857 / 0.882 / 0.882 | 0.400 / 0.429 / 0.412 / 0.353 |
| 10 | 0.809 / 0.889 / 0.889 / 0.882 | 0.857 / 0.889 / 0.889 / 0.882 | 0.429 / 0.481 / 0.556 / 0.353 |
| **12** | **0.481 / 0.414 / 0.562 / 0.600** | **0.296 / 0.172 / 0.500 / 0.400** | 0.074 / 0.414 / 0.375 / 0.350 |
| 14 | 0.206 / 0.333 / 0.294 / 0.414 | 0.059 / 0.154 / 0.147 / 0.241 | 0.382 / 0.256 / 0.353 / 0.207 |
| 16 | 0.171 / 0.220 / 0.220 / 0.270 | 0.114 / 0.073 / 0.195 / 0.108 | 0.400 / 0.317 / 0.415 / 0.243 |

**The transition is one step wide and all four seeds make it together.** llf holds 0.81 to 0.89 at
10 devices and falls to 0.41 to 0.60 at 12. edf C=8 falls harder, 0.86 to 0.89 down to 0.17 to
0.50. There is no intermediate size where the baselines degrade gracefully.

**COVEX does not have a crossover because it never has a collapse.** Its robot fraction is roughly
FLAT across the whole range, 0.35 to 0.56 at 10 devices and 0.24 to 0.42 at 16, with no step. It
does not win by improving under load; it wins by not degrading while the baselines fall past it.

**This is section 18's prediction, confirmed at the point it was most specific.** The queueing
account said baselines win where there is slack and collapse where there is none. The collapse is
located at 10 to 12 devices, it is sharp, and it is seed-stable. That is a mechanism result, and it
is the most transferable thing in this report: the interesting regime is NARROW and sits just above
10 devices, not at the 4 and 8 where most of the night was spent.

## 19.2 THE CAPACITY CONJUNCT, and MY OWN PREDICTION WAS WRONG

I predicted in `36acdd9` that capacity would fail for every arm at every size. **It does not.** 30
of 196 cells meet the D71/D82 conjunct. Cells meeting capacity, out of 4 seeds:

| n | v1.3-fast | llf | edf C=8 | mooncake | b7-edf | eco-llm |
|---|---|---|---|---|---|---|
| 4 | 0 | 0 | 0 | 0 | 0 | 0 |
| 8 | **0** | 1 | 1 | 2 | 2 | 2 |
| 10 | **0** | 0 | 0 | **3** | **3** | **3** |
| 12 | **0** | 0 | 0 | 2 | 2 | 2 |
| 14 | **0** | 0 | 0 | 2 | 2 | 2 |
| 16 | **0** | 0 | 0 | 0 | 0 | 1 |
| 32 | **0** | 0 | 0 | 0 | 0 | 0 |

Nobody passes at 4 devices, because the robot pool is not eligible there (fewer than the D82
minimum of 20 questions), not because the target is missed.

**v1.3-fast meets capacity in ZERO of 28 cells.** The published arms are the only arms that meet
it above 8 devices: **eco-llm 10 of 28, mooncake 9, b7-edf-feasibility 9**, against edf C=8 at 1
and llf at 1.

*(ERRATUM E8, against myself: I first wrote "12 of 28 each" here and in commit `fe3d437`. The
counted values are 10, 9 and 9. The error was an eyeball sum of the column above, not a
measurement fault, and it does not change any ranking, but the figure was quoted onward and is
corrected here.)*

**This is the column that changes the reading of everything above it.** My 32-device result in
sections 13.4 and 17 said COVEX's value appears under heavy overload. On the conjunct, at 32
devices every arm fails, COVEX included, and COVEX also failed at every other size. Leading a
fraction while failing the target is what that column was added to expose, and it exposes my own
headline first.

## 19.3 I WITHDRAW THE 32-DEVICE CLAIM. Under the D131 bar COVEX loses at EVERY size

Means over four seeds at 32 devices:

| arm | dashcam | robot fraction |
|---|---|---|
| v1.3-fast | 0.4463 | 0.202 |
| **mooncake / b7-edf** | **0.4527** | **0.454** |
| eco-llm | 0.4408 | **0.517** |
| llf | 0.0140 | 0.009 |
| edf C=8 | 0.0141 | 0.006 |

My "wide margin win at 32 devices in all four seeds" was measured against edf and llf ONLY. With
the published arms in the bar, **mooncake matches COVEX on dashcam and more than doubles it on
robots at 32 devices**, and eco-llm is ahead on robots by 2.6 times. The same holds at every other
size: the published field leads COVEX on robots at 4, 8, 10, 12, 14, 16 and 32.

**So under D131 the correct statement is that COVEX does not beat the best baseline at any size on
either axis, and meets the capacity target nowhere.** The earlier statement was an artefact of a
narrower bar and I am withdrawing it rather than leaving the two readings side by side. No
`harden GATE PASS` string is emitted and none is close.

What survives is the MECHANISM result of 19.1, which does not depend on the bar: the baselines
collapse at 10 to 12 devices and COVEX does not.

## 19.4 A PORTING OBSERVATION: two published arms are BYTE-IDENTICAL

`mooncake` and `b7-edf-feasibility` produce identical dashcam fractions and identical robot counts
in **28 of 28 cells**, across 7 sizes and 4 seeds, on both axes.

Two distinct published systems agreeing to four decimal places in every cell is not a result; it
means they reduce to the same schedule under this workload, or one registration duplicates the
other. This is the distribution-sanity check of the consistency protocol: a constant where a
distribution is expected.

**The consequence for the bar is small but real.** The published field has fewer INDEPENDENT
members than its arm count suggests, so "seven in-scope arms at 33 to 35 robots" overstates the
independent evidence behind the bar. It does not change the bar's height, since the value is
reproduced by `eco-llm` independently. Flagged to session 3 as something to explain or collapse,
not as a defect in my scoring.

# 20. THE 10/12/14 BAND, capacity components. DASHCAM IS SOLVED, THE ROBOT POOL IS THE WHOLE GAP

Re-read of the D131 grid in the band the crossover result identifies, split into the two halves of
the D71/D82 conjunct. No new runs: this is the same 196 cells, broken out.

`D+` means every eligible dashcam device meets its target; `R+` means the robot pool meets 0.90.

| n | arm | seed 0 | seed 4 | seed 5 | seed 6 |
|---|---|---|---|---|---|
| 10 | v1.3-fast | D+ R- 0.429 | D+ R- 0.481 | D+ R- 0.556 | D+ R- 0.353 |
| 10 | llf | D+ R- 0.810 | D+ R- 0.889 | D+ R- 0.889 | D+ R- 0.882 |
| 10 | eco-llm | **D+ R+ 0.952** | **D+ R+ 0.926** | **D+ R+ 0.963** | D+ R- 0.882 |
| 12 | v1.3-fast | D+ R- **0.074** | D+ R- 0.414 | D+ R- 0.375 | D+ R- 0.350 |
| 12 | llf | D+ R- 0.481 | D+ R- 0.414 | D+ R- 0.563 | D+ R- 0.600 |
| 12 | eco-llm | **D+ R+ 0.926** | D+ R- 0.897 | **D+ R+ 0.969** | D+ R- 0.850 |
| 14 | v1.3-fast | D+ R- 0.382 | D+ R- 0.256 | D+ R- 0.353 | D+ R- 0.207 |
| 14 | llf | D+ R- 0.206 | D+ R- 0.333 | D+ R- 0.294 | D+ R- 0.414 |
| 14 | eco-llm | **D+ R+ 0.941** | **D+ R+ 0.949** | D+ R- 0.882 | D+ R- 0.897 |

## 20.1 Three things session 1 can act on directly

**1. DASHCAM IS SOLVED AND SHOULD NOT BE WORKED ON.** Every arm, every size, every seed in the band
is `D+`. The conjunct is decided ENTIRELY by the robot pool. The dashcam target of 0.25 is met with
room by arms whose dashcam fraction ranges from 0.84 to 0.999, so dashcam fraction differences
between arms, which have consumed a lot of attention including mine, do not affect capacity at all
in this band.

**2. THE GAPS ARE OF COMPLETELY DIFFERENT SIZES, and that should set priorities.** Against the 0.90
robot target:

| arm | typical robot fraction in the band | gap to 0.90 |
|---|---|---|
| eco-llm | 0.85 to 0.97 | **0.00 to 0.05**, and it already passes 7 of 12 cells |
| llf | 0.21 to 0.89 | 0.01 to 0.69, collapsing with size |
| **v1.3-fast** | **0.07 to 0.56** | **0.34 to 0.83** |

eco-llm misses by as little as **0.0034** (n=12 seed 4, 0.8966). COVEX needs to roughly DOUBLE its
robot fraction to reach the target. These are not the same problem and a fix sized for one will not
address the other.

**3. A COVEX INSTABILITY WORTH DIAGNOSING: seed 0 at 12 devices is 0.074** against 0.414, 0.375 and
0.350 on the other three seeds at the same size, a five-fold drop on one seed. Its neighbours in
size on the same seed are 0.429 at n=10 and 0.382 at n=14, so it is not a trend, it is a single
anomalous cell. That is the signature of a threshold being crossed rather than a gradual effect,
and it is cheap to find because the cell is identified. It also means any v1.4 number quoted from
seed 0 at 12 devices should be read with this in mind.

## 20.2 What this says about where a v1.4 win is available

The band is where the contest sits, and inside the band the published bar is NOT far away in
absolute terms: eco-llm is within 0.05 of capacity in every cell it misses and already passes 7 of
12. A policy that closed a 0.02 to 0.05 robot-pool gap would convert several band cells to capacity
passes, which is a materially different claim from leading a fraction.

For COVEX that is not the available win. Its gap is 0.34 to 0.83, and the queueing account of
section 18 says the lever is release ordering rather than budget. The honest framing for v1.4 is
that the first target is to stop losing to llf at 10 devices, where llf is at 0.81 to 0.89 and
COVEX at 0.35 to 0.56, not to reach 0.90.

# 21. D132 ITEM 1: THE IDLE-GPU FEASIBILITY CEILING, and the headline definition it fixes

**Committed before any v1.4 result exists and before item 2 is scored**, so the definition
visibly precedes the results it governs. Derived entirely from the COMMITTED cost curve; nothing
is measured or fitted here. Output: `feasibility_ceiling.json`.

**The sum, per robot question**, with the history AS OF THE QUESTION'S ARRIVAL from the
`recall_question` record's `history_tokens`, never the session's final size:

```
cold rebuild   costs.recall_ttft_s(h, "COLD")        = h / COLD_PREFILL_TOK_S[nearest]
answer TTFT    costs.recall_ttft_s(h, "GPU-WARM")
link           RTT_MS / 1000 = 0.044 s               question up, answer down
                                                      against each question's own L = 5 s
```

No COLD answer term is added. `recall_ttft_s(h, "COLD")` IS the prefill on its own, so a second
COLD term would charge the prefill twice.

**The committed worked numbers reproduce exactly**, which is why the function is trusted on real
data:

| tokens | cold | answer | cold + answer | expected from the D118 derivation |
|---|---|---|---|---|
| 17,581 | 3.9069 | 0.5725 | **4.4794** | 4.48, feasible but barely |
| 20,101 | **5.2897** | 0.6454 | 5.9351 | 5.29 from the curve alone, infeasible |

## 21.1 THE CEILING

Feasible fraction on an idle engine, per seed and per size:

| n | seed 0 | seed 4 | seed 5 | seed 6 | **pooled** |
|---|---|---|---|---|---|
| 4 | 0.8889 | 1.0000 | 0.9091 | 0.8462 | 0.9024 |
| 8 | 0.9500 | 0.9048 | 0.9412 | 0.8824 | 0.9200 |
| 10 | 0.9048 | 0.9259 | 0.9630 | 0.8824 | 0.9239 |
| 12 | 0.8889 | 0.9310 | 0.9688 | 0.8500 | 0.9167 |
| 14 | 0.9118 | 0.9487 | 0.8824 | 0.8966 | 0.9118 |
| 16 | 0.9143 | 0.9024 | 0.8780 | 0.9189 | 0.9026 |
| **32** | 0.9167 | 0.8810 | 0.8228 | 0.9333 | **0.8871** |

Overall **0.9039**. Lowest single cell **0.8228** (seed 5 at 32 devices). **11 of 28 cells are
below 0.90.**

**The breakeven is sharp and sits in a narrow band:** the largest feasible history anywhere is
**19,381 tokens** and the smallest infeasible one is **20,011**. Above roughly 19.4k tokens a
robot question cannot be answered in 5 s on an idle GPU, by any scheduler, ever.

## 21.2 THE RULE FIRES. The headline robot target is p = 0.90 over FEASIBLE QUESTIONS

D132: *if the ceiling is below 0.90 at any size, the headline robot target is p = 0.90 over
feasible questions; otherwise over all questions.*

**The ceiling is 0.8871 at 32 devices, which is below 0.90, so the first branch fires.** It is
also below 0.90 in 11 of 28 individual cells including at 4, 8, 10, 12, 14 and 16 devices, so the
branch does not depend on the 32-device row alone.

**HEADLINE, FIXED FROM HERE: robot capacity is p = 0.90 over FEASIBLE questions.** The full p
curve at 0.50, 0.75 and 0.90 over BOTH denominators is reported regardless, per the ruling.

## 21.3 What this is likely to change, flagged as INDICATIVE until item 2 computes it exactly

About **9.6 percent of robot questions are physically undeliverable** on an idle GPU. Every
all-questions robot number in this report, mine and everyone's, has therefore been scored partly
against work no arm could ever do.

The cell I would watch first is eco-llm at 12 devices on seed 4, which missed capacity by
**0.0034** at 0.8966. The ceiling in that exact cell is 0.9310. If its misses are concentrated in
infeasible questions, the feasible-only figure would clear 0.90 comfortably and **that miss was
arithmetic rather than scheduling**.

**I am NOT claiming that yet.** Dividing a fraction by the ceiling is not the feasible-only
measure; the correct numerator is on-time among the feasible questions specifically, matched by
question id, which is exactly what D132 item 2 computes. The indicative direction is clear and
the exact number is not, so it is flagged here and will be resolved by measurement, not by
arithmetic on a mean.

**What it will not change:** COVEX's gap. At 12 devices on seed 4 it is at 0.414 against a ceiling
of 0.9310, so even a perfect feasible-only correction leaves it near 0.44. The ceiling reshapes the
published arms' near-misses; it does not close COVEX's deficit.

# 22. D132: the B2 ABSENT-LINK CONTROL, confirmed independently, and ERRATUM E7 against my harness

One cell, not a sweep: 16 devices, seed 0, `covex-v13`, base against B2. Per the direction, no gain
sweep was run. Output: `switch_moves_b2_rcprio.json`.

## 22.1 B2 is an ABSENT LINK, confirmed independently

| pair | decisions A | decisions B | decisions differing | switch moved |
|---|---|---|---|---|
| base vs `deficit_scaling`, gain 1.0 | 8,120 | 8,120 | **0** | **False** |
| base vs `deficit_scaling`, gain 0.01 | 8,120 | 8,120 | **0** | **False** |

**Zero of 8,120 decisions differ at either gain**, which reproduces session 1's byte-identical
delivery from the decision side rather than the outcome side. I verified both switches actually
reached the arm first: `deficit_scaling` arrives as `True` and `deficit_gain` as `1.0` and `0.01`
on the constructed arm.

**Classification, CLAUDE.md Rule 2: INCONCLUSIVE, not a real negative.** The quantity is present
and large, session 1 measured `_b2_weight('RC')` at 201.33 and `z[RC]` reaching 543.58 across 11
updates, and it reaches no decision because the dispatch path does not route RC rows into
`_z_term` while the planner does so via `rc_rows=True`. The link from the deficit to admission is
**ABSENT**. B2 may not be reported as a volume result at any gain until that routing lands, and
the null above is an artefact of the experimental design, not evidence that deficit scaling does
not work.

## 22.2 ERRATUM E7, against my own harness, found by the same check

`_arm_kwargs` cast every field whose declared type was not `float` with a blanket `bool()`. So
`rc_priority_keep_monitors = 2`, declared `int`, arrived at the arm as `True`, which is 1.

This is the same class of defect as my `mu_mode` hard-coding and is the fourth switch-plumbing
fault in three nights. The cast now follows the DECLARED type for float, int, str and bool
separately. **The B2 rows above are unaffected**, because `deficit_scaling` is a genuine bool and
`deficit_gain` a genuine float, and I checked both on the constructed arm rather than assuming.

**The RCprio comparison is therefore WITHHELD from this section.** Its first run showed 0 of 8,120
decisions differing and `rc_priority_epochs` absent from both conditions, which would say the
branch never fires; but it ran with `keep_monitors` silently reduced from 2 to 1, so I am not
reporting it until it has been re-run with the cast fixed. The gating field `rc_priority_slack_s`
did arrive correctly as `1.0`, so I expect the conclusion to hold, and expecting is not reporting.

# 23. THE PUBLISHED-ARM IDENTITY CHECK (critical path for covex-v2's base)

Session 3's answer had not landed on origin when I ran this, so I ran it rather than wait. This
compares **ACTION SEQUENCES**, not outcome counts: every `decision.jsonl` is hashed with the
bookkeeping fields (`arm`, `arm_version`, `note`, `mu`, `belief`, `predicted`,
`decision_latency_ms`) removed, so two arms land in one class only if they took the same decisions
in the same order. Seed 4, from the already-measured D131 and published runs.

## 23.0 RECONCILED WITH SESSION 3 (`b163a3e`), and the reconciliation is the real finding

Session 3 hashed each arm's **canonical decision objects** and found mooncake and b7 **genuinely
distinct** at both sizes. I hashed the **logged** decisions and found them identical. Both are
correct and they do not conflict, because of what session 3 also found: **`live2/coordinator.py`
contains ZERO references to the action `order` field**, and `order` is not present in
`decision.jsonl` either (I checked: the record's fields are H, arm, arm_version, belief,
cost_model_id, decision_id, decision_latency_ms, defer_s, kind, mu, note, opportunity_ids,
piece_tokens, predicted, t, traffic_mix).

So the two arms differ in what they INTEND and not in what the harness EXECUTES. Mine is the
operative reading for every delivery number in this report; session 3's is the operative reading
for what the two published systems actually are.

**The harness gap, stated plainly because it bounds the whole published comparison: any two
adapted arms whose scheduling discipline is expressed only through `order` are indistinguishable
in live2 BY CONSTRUCTION.** That is an expressiveness limitation of our harness, not a porting
artefact, and it caps what the published-field bar can ever demonstrate. It also means a covex-v2
deviation class expressible only through `order` would fire and change nothing, which would read
as a weak mechanism when it is an unexpressible one. That distinction is now in my deviation audit.

**My 23.1 classes below are therefore classes of EXECUTED behaviour.** Session 3's cardinality is
the one to quote for independence of the published systems: at seed 4 and 8 devices, excluding
`order`, 20 arms give 16 distinct sequences, and **the twelve in-scope arms supply ELEVEN
independent behaviours at that cell**. The collapses are regime-dependent, so a cardinality
without a size attached is meaningless. `eco-llm` is a singleton in every grouping at both sizes,
so my section 23.3 recommendation rests on an independent arm.

## 23.1 The collapse in EXECUTED behaviour is LARGER THAN TWO ARMS, and SIZE-DEPENDENT

**At 16 devices, 19 published arms reduce to 14 distinct behaviours:**

| class | arms | decisions |
|---|---|---|
| **A** | **inar-vl, kvflow, pensieve, routellm** | 7,638 |
| **B** | **attentionstore, lmcache** | 8,480 |
| **C** | **b7-edf-feasibility, mooncake** | 7,878 |
| singletons | b10-blocking-aware, clockwork, confidence-cascade, eco-llm, ekya, hybrid-llm, perllm, preble, r3-streaming, uniscale, videostorm | |

**At 8 devices it is worse: 19 arms reduce to 11 behaviours**, and the largest class has SIX
members: eco-llm, inar-vl, kvflow, pensieve, routellm and videostorm are all byte-identical in
action sequence. b7-edf-feasibility, ekya and mooncake form a class of three.

So the identity is not a mooncake / b7 curiosity. **Distinct published systems collapse onto one
behaviour under light load and separate as load rises**, which is itself a sensible result: these
systems differ in what they do when resources are scarce, and at 8 devices they are not scarce.

## 23.2 A FINDING ABOUT MY OWN GATE BASELINES: edf C=8 and llf are IDENTICAL at 8 devices

`edfC=8` and `llf` share one action-sequence hash at 8 devices (4,364 decisions) and are DISTINCT
at 16. That explains the identical delivery I reported at 8 devices throughout this study
(0.9993 / 18 for both on seed 4) and I had not looked into it.

**Consequence for D127 gate reporting: at 8 devices "the best of edf and llf" was ONE arm wearing
two names**, so the gate there was never the two-arm test it appeared to be. It does not change
any verdict, since COVEX lost to that arm either way, but a reader comparing the two columns at 8
devices should know they are one measurement.

## 23.3 THE ANSWER SESSION 1 NEEDS: the true best base is `eco-llm`, not `b7-edf-feasibility`

On the headline metric now fixed by D132 item 1, the capacity conjunct:

| arm | capacity cells met | robot fraction, n=14 / 16 / 32 | dashcam, n=16 / 32 |
|---|---|---|---|
| **eco-llm** | **10 of 28** | 0.917 / **0.878** / **0.517** | 0.8809 / 0.4408 |
| mooncake | 9 of 28 | 0.917 / 0.831 / 0.454 | 0.9185 / 0.4527 |
| b7-edf-feasibility | 9 of 28 | 0.917 / 0.831 / 0.454 | 0.9185 / 0.4527 |
| llf | 1 of 28 | 0.312 / 0.220 / 0.009 | 0.9710 / 0.0140 |

**eco-llm leads on capacity and on the robot pool at every size where they differ.** b7 and
mooncake lead it only on dashcam, and section 20 established that dashcam is `D+` for every arm at
every size in the band, so **dashcam does not affect the conjunct at all**. Choosing a base on
dashcam would be optimising the half of the objective that is already satisfied.

**Recommendation: covex-v2's base should be `eco-llm`.** Session 3's independent grouping
strengthens this: eco-llm is a SINGLETON at both sizes, so the recommendation does not rest on an
arm that duplicates another. Two caveats stated honestly:

1. **The margin is small**, 10 cells against 9, and the robot gaps are 0.047 at 16 devices and
   0.063 at 32. It is a consistent direction rather than a decisive one.
2. **At 8 devices eco-llm is not a distinct policy at all**, being one of a six-arm class, so the
   choice only has content at 10 devices and above. In the band the crossover result identifies,
   which is where the contest sits, it does have content.

If session 1 prefers b7 for a reason outside these numbers, the cost is about one capacity cell
and roughly 0.05 of robot fraction above 14 devices, and it should pick it knowing that rather
than on the assumption that b7 and eco-llm are equivalent. **They are not equivalent at 16 devices;
they are only equivalent at 8.**

# 24. RCprio IS AN ABSENT LINK, re-run with the E7 cast fixed

Session 1 is waiting on this before reporting any conversion comparison, so it is reported on its
own. 16 devices, seed 0, `covex-v13`, base against RCprio, after the E7 fix that stopped
`rc_priority_keep_monitors` being coerced from 2 to `True`.

| pair | decisions A | decisions B | differing | switch moved |
|---|---|---|---|---|
| base vs `rc_priority_slack_s=1.0, keep_monitors=2` | 8,120 | 8,120 | **0** | **False** |
| base vs `rc_priority_slack_s=5.0, keep_monitors=0` | 8,120 | 8,120 | **0** | **False** |

Both settings verified to reach the arm as real values after the fix: `rc_priority_slack_s = 1.0`
as a float and `rc_priority_keep_monitors = 2` as an int. `rc_priority_epochs` never appears in
either condition's `stats`, so the branch at `arms_policy.py:811` does not fire even with a slack
threshold of 5.0 s, which is the entire recall deadline and should admit every urgent recall there
is.

**Classification: ABSENT LINK, not a negative.** Session 1's own suspicion that it could not
confirm `RCprio` fires is confirmed from the decision side. **No base-against-RCprio comparison
may be reported as a conversion result** until the branch is reached. A null here would be an
artefact of the switch never moving.

This is the second absent link of the night after B2 and the fifth switch-plumbing fault in three
nights, counting my own E7. The pattern is consistent enough that `switch_moves.py` should run on
every new switch before it is scored, not after a suspicious null.
