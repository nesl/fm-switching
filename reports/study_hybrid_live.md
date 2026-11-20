# StudyHYBRID-live: the H100 hybrid, components, move proofs and live screening (D138 to D141)

**Status: INTERIM, 2026-11-19 16:35. Seed-0 screening complete; seed-4 repeats in progress (1 of 4 done); C6 cells
next. PILOT SCREENING, NOT A ROUND-1 RESULT.** Every live number below is an observed count from one 600-s run
(Qwen3-VL-32B, round-1 server, tight 27 GiB host tier, 50:50 traffic, push-all, mode A). Robot pools are 21
questions at 10 devices and 27 at 12 devices on seed 0, so **one question is 4.8 pp at 10 and 3.7 pp at 12**. No
confidence intervals are claimed and no difference here is a finding until the repeats and a seed-4 control land.

## 0. Headline so far

1. **With the corrected definitions (D140, D141), every hybrid configuration beats the b7 base by one or two robot
   questions per size, with every dashcam meeting its target, and C1+C2(k_r 1.5)+C5 PASSES the pilot verdict at both
   10 and 12 devices on seed 0** (19 of 21, 25 of 27; dashcams all meet). The base fails at both (18 of 21, 23 of
   27), as has every baseline run at 10 devices so far. C5, C1+C2(k 0.5)+C5 and C1+C2(k 1.5)+C3+C5 pass at 10 and
   miss at 12 by one question. One seed, margins of one question: this is a lead, not a finding.
2. **The first definitions were wrong, and the live runs showed it:** C5's in-flight cap, applied to every kind of
   work, starved robots (base 23 of 27 at 12 devices; old C5 10 of 27; old C1+C5 9 of 27). The decision logs showed
   the cause: robot releases fell from 25 to 6 and 183 robot questions were deferred to expiry, because deadline order
   fills the few free slots with dashcam instants (1 s deadline) ahead of robots (5 s). Making the cap
   dashcam-only (D140) removed the starvation (C5: 24 of 27).
3. **Two things are not yet known:** robot on-time over FEASIBLE questions (needs the D133 definition and each
   unreleased question's history size, which the decision logs do not record), and whether the margins survive a
   second seed, because **the seed-4 repeats have no seed-4 base to compare against** (section 6).

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

## 3. Live results, seed 0 (all runs valid, 0 request errors, emulator lateness p99 0.108 to 0.116 s)

**Corrected definitions (v2/v3):**

| configuration | robots on time, 10 dev (of 21) | 12 dev (of 27) | dashcams all meet | RECENT share of robot answers (10 / 12) | decision latency p50 / p99, ms (12 dev) |
|---|---|---|---|---|---|
| base (b7) | 18 | 23 | yes / yes | 0 / 0 | 0.81 / 1.17 |
| C5 (dashcam-only cap) | 19 | 24 | yes / yes | 0 / 0 | 0.88 / 1.26 |
| C1+C2(k 0.5)+C5 | 19 | 24 | yes / yes | 0 / 0 | 0.90 / 1.29 |
| **C1+C2(k 1.5)+C5** | 19 | **25** | yes / yes | 0 / 0 | 0.90 / 1.28 |
| **C1+C2(k 1.5)+C3+C5** | **20** | 24 | yes / yes | 1/21 / 2/27 | 0.91 / 1.28 |
| C3-always ablation (k 1.5), 12 dev only | | 24 | yes | 3/27 | 0.91 / 1.29 |

**First definitions (v1, "old at-risk / old cap"), kept for the record:**

| configuration | 10 dev (of 21) | 12 dev (of 27) | dashcams all meet |
|---|---|---|---|
| C5 (cap on all work) | 13 | 10 | yes / yes |
| C1+C5 | 13 | 9 | yes / yes |
| C1+C2(k 1.0)+C5 | 14 | 9 | yes / yes |
| C1+C2(k 2.0)+C5 | 16 | 11 | yes / yes |

**Seed 4 (in progress):** C1+C2(k 1.5)+C3+C5 at 10 devices: 24 of 27, dashcams all meet, RECENT 2 of 27.

**Pilot verdict (D97 rule, all dashcams meet and pooled robot on-time at least 90 percent, as computed in
`results/orchestration/live2/pilot/hybrid_live_summary.json`):**

| configuration | 10 devices | 12 devices |
|---|---|---|
| base (b7) | fail (85.7 %) | fail (85.2 %) |
| C5 | PASS (90.5 %) | fail (88.9 %) |
| C1+C2(k 0.5)+C5 | PASS (90.5 %) | fail (88.9 %) |
| **C1+C2(k 1.5)+C5** | **PASS (90.5 %)** | **PASS (92.6 %)** |
| C1+C2(k 1.5)+C3+C5 | PASS (95.2 %) | fail (88.9 %) |
| C3-always ablation | | fail (88.9 %) |
| every v1 configuration | fail | fail |

Capacity (largest passing size) is not measured: only 10 and 12 devices were run. A pass at 12 sits on the
threshold (25 of 27 passes, 24 of 27 fails), so it is one question from either verdict.

Decision latency rises from 0.81 to about 0.90 ms p50 with the components, far inside the 100-ms decision period.

## 4. Mechanism reading (provisional, one seed)

- The b7 base's robot misses at 10 and 12 devices are queueing behind dashcam traffic, not infeasible rebuilds:
  capping dashcam in-flight work alone (C5) recovers one robot question at each size while every dashcam still meets.
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

1. **Seed-4 control missing (needs a ruling):** the seed-4 repeats run the best two hybrids only. Without the base at
   seed 4 (10 and 12 devices, 2 runs, about 25 min) the repeats cannot show whether the hybrid's margin holds.
   Recommended: add `hybrid-base` at seed 4 before the C6 cells.
2. **On-time over feasible questions:** needs the D133 definition (provisional: unloaded lower bound, the committed
   cold rebuild for the history plus warm recall TTFT, at most 5 s) and each robot question's history size from the
   trace. Not computed yet.
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

Seed-4 repeats (3 remaining, to about 17:00), best + C6 at 10 and 12 devices (to about 17:25), StudySS1 32B answer
pass (about 70 min), OpenEQA when its kit lands, LH-REQ when "lh-req ready" lands (best hybrid and the top two
baselines at 10 and 12), then the D134 baselines.
