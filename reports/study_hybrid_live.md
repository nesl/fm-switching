# StudyHYBRID-live: the H100 hybrid, components, move proofs and live screening (D138 to D141)

**Status: CLOSED BY D142 (2026-11-19 17:10): MIXED screening stopped after the b7 seed-4 control; the module is handed
to flash. PILOT SCREENING, NOT A ROUND-1 RESULT.** Every live number below is an observed count from one 600-s run
(Qwen3-VL-32B, round-1 server, tight 27 GiB host tier, 50:50 traffic, push-all, mode A). Robot pools are 21
questions at 10 devices and 27 at 12 devices on seed 0, so **one question is 4.8 pp at 10 and 3.7 pp at 12**. No
confidence intervals are claimed and no difference here is a finding until the repeats and a seed-4 control land.

## 0. Headline so far

1. **Under the ruled D133 headline (robot p 0.90 within 5 s over FEASIBLE questions, per opportunity_id; feasibility
   from flash's `feasibility_ceiling.py`), the b7 base AND every corrected hybrid pass at 10 and 12 devices on seed 0.**
   The base misses one feasible question at each size (18 of 19, 23 of 24); every corrected hybrid configuration
   delivers every feasible question on time (19 of 19, 24 of 24), with every dashcam meeting its target. **The
   hybrid's edge on seed 0 is therefore one feasible question per size, not a pass-or-fail difference.** Over all
   questions (reported beside it), the base is 18 of 21 and 23 of 27 and the best hybrid 19 or 20 of 21 and 25 of 27;
   the remaining misses are questions no scheduler can deliver on an idle engine (2 of 21 and 3 of 27 are infeasible).
   (An earlier version of this report read the all-questions figure as the verdict, under which only the hybrids
   passed; that reading is superseded by the D133 ruling.)
2. **The first definitions were wrong, and the live runs showed it:** C5's in-flight cap, applied to every kind of
   work, starved robots (base 23 of 27 at 12 devices; old C5 10 of 27; old C1+C5 9 of 27). The decision logs showed
   the cause: robot releases fell from 25 to 6 and 183 robot questions were deferred to expiry, because deadline order
   fills the few free slots with dashcam instants (1 s deadline) ahead of robots (5 s). Making the cap
   dashcam-only (D140) removed the starvation (C5: 24 of 27).
3. **Not yet known:** whether the one-question edge survives other seeds. The b7 base at seed 4 and the base and
   C1+C2(k 1.5)+C5 at seeds 5 and 6 are now queued (user ruling), so the comparison is paired per seed.

## 1. What was built (code: `experiments/orchestration/live2/hybrid/`)

`HybridArm` is registered through `make_arm` (importing the package adds the `hybrid-*` and `hybrid2-*` names to
`arms.ARMS`; the two runner files import it before `make_arm`). Flash-owned code is used read-only: `costs.py`
curves, b7's feasibility rule, the RC quality tables, and `policy/chooser.py` (70be641).

**Base:** every switch off returns `B7EDFFeasibility.decide` unchanged. Proved byte-identical to
`b7-edf-feasibility` on decision logs at seed 0 n8, seed 0 n12, seed 4 n10, seed 5 n16 (120 s dry), and again at
seed 0 n12, 600 s, after each later change (6,569 of 6,569 decisions identical). Positive control: the committed b7
run at 10 devices, seed 0 (runs4) scored 18 of 21 robots; `hybrid-base` at the same cell scored 18 of 21.

| component | definition as now run (v2/v3, D140 and D141) | first definition (v1, labelled "old at-risk / old cap") |
|---|---|---|
| C1 ordering | index = value x urgency / remaining work; urgency 1/max(slack, 0.1 s); work from the committed cost curve; value from the committed RC table (recall) and the SH cloud gain (dashcam) | same |
| C2 protect-then-fill | robot at risk when LAXITY < k_r (laxity = deadline - now - predicted remaining work, including a cold rebuild of the believed un-built history), k_r in {0.5, 1.5} s; dashcam at risk when its 60-s on-time fraction < 0.25 + m_d (m_d 0.05). **Consumer of the robot flag (D141): a dashcam throttle**: while any robot is at risk, no new dashcam frames beyond a floor of 2 in flight; an at-risk dashcam device is exempt | robot at risk when slack < k_r or laxity < 0, k_r in {1.0, 2.0}; consumer: a reserved in-flight slot |
| C3 degradation | default: an at-risk robot that b7 would defer or reject (rebuild infeasible) is sent as RECENT. Ablation switch "C3-always": every at-risk robot to RECENT | same default, no ablation |
| C4 retention | built inert (no session action is ever emitted; confirmed by flash's dry screen) | same |
| C5 in-flight limit | AIMD cap 4..8 applied to **dashcam traffic only**; robot work is never held. The reserved slot is a separate switch (ablation) | cap applied to all work |
| C6 chooser | flash's `choose(candidates, state)` per robot question on a policy-core mirror (its own decisions never executed): default = the C2/C3 choice; alternatives send now (full D2), hold, decline; **for an at-risk robot also "RECENT now" and "longer dashcam throttle"** (throttle floor 0 until that robot completes) | send, hold, decline only |

Note (D141 item 5): **C1 ordering is inert for robots** (the coordinator re-sorts submissions by deadline and robots
are never held), so any C1 effect is on which dashcam instants are admitted under the cap.

## 2. Move proofs (CLAUDE.md Step 2b), before scoring

All on 600-s dry cells, seed 0, 12 devices unless stated. Files: `results/orchestration/live2/hybrid/hybrid_*proof*.json`,
`hybrid_moves.json`, `hybrid_pairs.json`.

| comparison | differing decisions | verdict |
|---|---|---|
| base vs b7 | 0 of 6,569 | identical (required) |
| v1: C1 alone vs base | 0 | ABSENT LINK (C1 needs a cap; flash confirmed independently, e9503c2) |
| v1: C5 vs base (120-s dry cell) | 1,135 of 1,212 | moves |
| v2 fix 2: dashcam-only cap vs old cap | 6,797 | moves |
| v2 fix 1: laxity vs old at-risk test, no cap | 0 at both k_r | **ABSENT LINK: no decision read the robot flag**, which led to the D141 throttle |
| v2: C1 under the dashcam cap vs C5 | 0 | ABSENT LINK (C1 inert for robots, see note) |
| v2: reserve switch on vs off | 0 | ABSENT LINK in this cell |
| v3: throttle k_r 0.5 vs no C2 | 44 | moves (12 dashcam submissions throttled) |
| v3: throttle k_r 1.5 vs no C2 | 3,570 | moves |
| v3: k_r 0.5 vs 1.5 | 3,534 | moves |
| v3: C3 default (k 0.5) | 11 | moves |
| v3: C3-always vs C3 (k 0.5) | 0 | ABSENT LINK at k 0.5 |
| v3: C3-always vs C3 (k 1.5) | 3,535 | moves (1 robot sent as RECENT; throttle 47 to 6 periods, throttled dashcams 260 to 35) |
| C6 on vs off (k 1.5, with the at-risk candidates) | 3,109 | moves, but only by decline-to-send (2); RECENT-now and longer-throttle were never chosen in that cell |
| v1 all-on vs C1+C2+C3+C5 | 0 | identical (C4 inert), so all-on was not run |

## 3. Live results (all runs valid, 0 request errors, emulator lateness p99 0.108 to 0.116 s)

**Robot headline (D133, ruled 2026-11-19): on time within 5 s over FEASIBLE questions, matched per opportunity_id**;
the all-questions figure beside it. Feasibility is a property of the trace (cold rebuild of the history at question
time + warm answer + link <= the question's deadline, flash's `policy/audit/feasibility_ceiling.py`, 0cb1195),
applied per question by `experiments/orchestration/live2/hybrid/feasible_on_time.py`. Checks: its per-cell counts
equal the committed `feasibility_ceiling.json` in all four cells (seed 0: 19 of 21 and 24 of 27 feasible; seed 4: 25
of 27 and 27 of 29), and its all-questions count equals the run scorer's `robot_pool_on_time` in every run (on time =
DELIVERED within the deadline). Per-run file: `results/orchestration/live2/hybrid/hybrid_feasible.json`.

**Corrected definitions (v2/v3), seed 0:**

| configuration | 10 dev: feasible (of 19) | 10 dev: all (of 21) | 12 dev: feasible (of 24) | 12 dev: all (of 27) | dashcams all meet | RECENT share of robot answers (10 / 12) | decision latency p50 / p99, ms (12 dev) |
|---|---|---|---|---|---|---|---|
| base (b7) | 18 (94.7 %) | 18 | 23 (95.8 %) | 23 | yes / yes | 0 / 0 | 0.81 / 1.17 |
| C5 (dashcam-only cap) | **19** | 19 | **24** | 24 | yes / yes | 0 / 0 | 0.88 / 1.26 |
| C1+C2(k 0.5)+C5 | **19** | 19 | **24** | 24 | yes / yes | 0 / 0 | 0.90 / 1.29 |
| C1+C2(k 1.5)+C5 | **19** | 19 | **24** | 25 | yes / yes | 0 / 0 | 0.90 / 1.28 |
| C1+C2(k 1.5)+C3+C5 | **19** | 20 | **24** | 24 | yes / yes | 1/21 / 2/27 | 0.91 / 1.28 |
| C3-always ablation (k 1.5) | | | **24** | 24 | yes | 3/27 | 0.91 / 1.29 |

Where "all" exceeds "feasible", an idle-engine-infeasible question was delivered on time anyway (its history was
already partly built, which the idle bound does not credit): one such question in each of C1+C2(k 1.5)+C5 at 12 and
C1+C2(k 1.5)+C3+C5 at 10.

**First definitions (v1, "old at-risk / old cap"), seed 0, kept for the record:**

| configuration | 10 dev: feasible (of 19) | 10 dev: all (of 21) | 12 dev: feasible (of 24) | 12 dev: all (of 27) | dashcams all meet |
|---|---|---|---|---|---|
| C5 (cap on all work) | 13 | 13 | 10 | 10 | yes / yes |
| C1+C5 | 13 | 13 | 9 | 9 | yes / yes |
| C1+C2(k 1.0)+C5 | 14 | 14 | 9 | 9 | yes / yes |
| C1+C2(k 2.0)+C5 | 16 | 16 | 11 | 11 | yes / yes |

**Seed 4 (the paired control, D142), all runs valid, dashcams all meet:**

| configuration | 10 dev: feasible (of 25) | 10 dev: all (of 27) | 12 dev: feasible (of 27) | 12 dev: all (of 29) |
|---|---|---|---|---|
| base (b7) | 21 (84.0 %, fail) | 21 | 20 (74.1 %, fail) | 20 |
| C1+C2(k 1.5)+C3+C5 | **24 (96.0 %, PASS)** | 24 | 22 (81.5 %, fail) | 22 |

The C3 combination's first 12-device seed-4 run was INVALID (one dashcam request failed with a transport `ReadError`
at t = 246.5 s, the unresolved harness issue first seen at 16 devices in D134); it is excluded and the valid rerun is
the one shown. C1+C2(k 1.5)+C5 at seed 4, the C6 cells, and seeds 5 and 6 were NOT run: D142 stopped all MIXED
screening after the b7 seed-4 control.

**Seed 0 and seed 4 side by side (feasible-question headline; margin = hybrid minus base):**

| | 10 devices | 12 devices |
|---|---|---|
| seed 0: base / best hybrid | 18 of 19 / 19 of 19 (+1) | 23 of 24 / 24 of 24 (+1) |
| seed 4: base / C1+C2(k 1.5)+C3+C5 | 21 of 25 / 24 of 25 (+3) | 20 of 27 / 22 of 27 (+2) |

On both seeds the hybrid delivers more feasible robot questions on time than b7 at both sizes, with every dashcam
meeting; the margin is larger on the harder seed (seed 4, where b7 fails at both sizes). Two seeds, margins of one to
three questions: a consistent direction, not yet a settled effect.

**Verdict under the D133 headline (all dashcams meet AND feasible robot on-time at least 90 percent):** every
corrected configuration and the base PASS at 10 and 12 devices on seed 0; every v1 configuration fails (the old cap
starved robots). Capacity (largest passing size) is not measured: only 10 and 12 devices were run.

Decision latency rises from 0.81 to about 0.90 ms p50 with the components, far inside the 100-ms decision period.

## 4. Mechanism reading (provisional, one seed)

- Of the base's robot misses, 2 of 3 at 10 devices and 3 of 4 at 12 are infeasible questions no scheduler can serve;
  the one feasible miss at each size is queueing behind dashcam traffic, and capping dashcam in-flight work alone
  (C5) recovers it while every dashcam still meets.
- The throttle at k_r 1.5 fires (3,570 differing decisions) and adds one more robot at 12 devices; at k_r 0.5 it
  almost never fires (44 decisions) and changes nothing live.
- C3 sends 1 to 2 robots per run as RECENT and adds one robot at 10 devices but not at 12. On MIXED, RECENT costs about
  3.5 pp of accuracy (StudyACC2: D2 0.375 vs RECENT 0.339), so a RECENT answer that arrives on time is not
  necessarily a better outcome than a late full answer; the scorer counts on-time only.
- **The margins are one or two questions.** Two seeds will not separate configurations that differ by one question;
  they can only show whether the hybrid's advantage over the base holds.

## 5. Incidents (none affects a reported number)

- 14:05, operator error: stopping the driver for the D140 fixes aborted the run that had just started
  (`hybrid-c1c2k2c5_n12`, old definitions) and stopped the server; set aside as `_ABORTED_operator_kill`, rerun
  14:14 under the old definitions. GPU 2 idle about 2 min at 14:26 while the proofs finished.
- 14:39: `hybrid2-c5_n12` refused twice at preflight (the GPU-exclusivity check counts any of my processes with
  "python" in the command line, and the operator's dry-run proofs were running); not a measurement, set aside as
  `_REFUSED_preflight`, rerun at 14:40. Since then, proofs run only inside a live run, after its preflight.

## 6. Open items and requests

1. **Seed controls (ruled):** b7 at seed 4 (10, 12), then C1+C2(k 1.5)+C5 at seed 4, then the C6 cells, then the base
   and C1+C2(k 1.5)+C5 at seeds 5 and 6 (10, 12). C6 runs on C1+C2(k 1.5)+C5 (PROVISIONAL choice: the configuration
   the follow-up seeds use; it and the C3 combination tie on seed 0).
5. **Transport ReadError:** a single dashcam request failure invalidated a 12-device run; the harness issue is still
   unresolved (ruling pending since D134).
2. **On-time over feasible questions:** done (D133 ruled), section 3.
3. **Requests to flash (quality model):** the committed 32B-D2 table is PNG frames from t = 0 (0.420 DEV) while live2
   sends JPEG q88 from t = 2 s (0.370 measured, StudyACC2); 32B-RECENT is StudyR1 K3 (12.4k tokens), not live2's
   RECENT (5.5k tokens). C1's value term and C6's "RECENT now" candidate are priced against these tables.
4. **vLLM priority** (D141 item 4): wiring kept, not used; a separate experiment with the base rerun under the same flag.

## 7. Other work since D138

- **StudyACC2 complete** (`reports/study_acc2.md`, 6b3a173): history help is significant at 10k to 19.4k tokens
  (+6.5 and +7.2 pp) and not detectable above 19.4k (-1.7 pp [-9.3, +5.9]).
- **StudySS1 (P2) prepared:** VizWiz val (4,319 questions, all images present, references match `val.json`) and
  EgoThink (700 images, all hash-match the manifest) staged on the H100 from the public sources. The 32B answer pass
  runs after the C6 cells (about 17:25); the A6000 runs the Mistral-7B judge on both tiers (parser fix 614c0d9).

## 8. Next (queue)

Seed-4: the C3 combination at 12 (rerun), b7 at 10 and 12, C1+C2(k 1.5)+C5 at 10 and 12; C6 on C1+C2(k 1.5)+C5 at 10
and 12; the base and C1+C2(k 1.5)+C5 at seeds 5 and 6 (8 runs); about 19:30 in all. Then the StudySS1 32B answer
pass (about 70 min), OpenEQA when its kit lands, LH-REQ when "lh-req ready" lands (best hybrid and the top two
baselines at 10 and 12), then the D134 baselines.

## 9. Hand-over to flash (D142, 2026-11-19)

flash now owns `experiments/orchestration/live2/hybrid/`. The H100 makes no further edits there. State left:

- **Committed and pushed, nothing uncommitted** (last H100 commit to the module: the C6 offer counter, fdbe03d era;
  `feasible_on_time.py` added in 493ad96). Configurations: `hybrid-*` (v1, "old at-risk / old cap"), `hybrid2-*`
  (v2/v3: laxity at-risk with the D141 dashcam throttle, floor 2; dashcam-only C5 cap; reserve switch; C3 default and
  the C3-always ablation), and a `-c6` variant of every configuration.
- **Proofs on origin:** base byte-identical to b7 (several seeds and sizes, and after every change), Step 2b move proofs
  for every switch (`results/orchestration/live2/hybrid/hybrid_*proof*.json`).
- **Open items and known issues:**
  1. **C6 is wired but its at-risk candidates were never chosen**: in the one dry proof cell (seed 0, 12 devices) the
     chooser deviated only decline-to-send (2 of 21 calls); "RECENT now" and "longer dashcam throttle" were offered
     (counter `c6_offered_recent_and_throttle`) but never won. Half the chooser calls find no pending pieces in the
     policy-core mirror (`c6_no_pending`). C6 was never run live.
  2. **The mirror is approximate**: it runs policy-core's own admission and release on the same observations but never
     sees the hybrid's actual releases or completions (forwarding completions trips policy-core's F-4 assertion), so
     its in-flight model is its own, not the executed one.
  3. **Quality tables:** C1's value and C6's "RECENT now" are priced with the committed 32B-D2 (PNG, from t = 0) and
     32B-RECENT (StudyR1 K3, 12.4k tokens) tables, which overstate what live2 sends (StudyACC2).
  4. **C4 is inert** (no session action is ever emitted); **C1 is inert for robots** (the coordinator re-sorts by
     deadline and robots are never held), so C1 acts only on dashcam admission under the cap.
  5. **k_r 0.5** almost never fires the throttle (44 decision rows); **C3-always at k 0.5** is identical to C3.
  6. **Transport `ReadError`** (harness, not the module) invalidated one 12-device run; ruling still pending.
  7. **The `live2_completed` hook** on the hybrid is consumed only by the v2 throttle and the C6 long-throttle store;
     the base is still byte-identical to b7 with it present (proved after adding it).
  8. `feasible_on_time.py` reproduces the scorer's on-time rule (delivery within the deadline) and reconciles with
     `feasibility_ceiling.json`; it reads `outcomes.jsonl` and the run's trace directory.
