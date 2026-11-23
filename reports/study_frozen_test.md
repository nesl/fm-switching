# StudyFROZEN-test (H100, overnight 2026-11-19 to 20): frozen-policy test, StudySS1-32B and SS timing

**Status: IN PROGRESS. Last updated 2026-11-22 05:43.** Rules: D116 (no methodological change overnight; never seeds 1
to 3 or HOLDOUT; never INVALID results; GPU 2 exclusive; no em dashes). PROVISIONAL decisions are marked.

## 06:00 summary, 2026-11-22

H100 overnight from 18:50 (user's overnight brief; D106 / D116; commits per D166). Workload for every row below:
BASELINE_MATRIX tag `_L3_epg_rq30` = 16 devices, 1,200 s, robot deadline 3 s, EP-G dashcam episodes, per-frame robot upload,
rq30 re-asks. Robot = correct answers delivered BY THE DEADLINE (D155 headline, `robot_headline`) and robot on time / feasible;
SS = single-shot within 2 s / pool; dash = all dashcam deadlines met; load = uncached prompt tokens per second over the
run (request.jsonl, prompt minus cached, / 1200 s). **"Robot on time" and "SS within 2 s" count CLOUD deliveries only**: a device-served answer carries no delivery timestamp in outcomes.jsonl in any arm, so an arm that answers on the device (r3-streaming: all 132 robot and 357 SS on the device) shows 0 there while its device answers still count in "robot by deadline". **Read per seed only, never pooled**: the Orin re-ask device answers flip the
frozen-answer error's sign by seed (flash e016c230). Robot numbers still use the scorer's measured Orin WARM device latency
(default `orin_rec_warm`), which covers every scored robot row (flash 1c239d5e). Transition zone for saturation is about
4,500 to 4,750 uncached tok/s; a saturated cell is scored almost entirely on the device fallback answers, which are fixed by
the seed's trace, so **saturated arms at the same seed show identical scores by coincidence on shared inputs, not duplication** (CORRECTED 2026-11-22 ~15:30, flash cb9b9968: the shared base is `score.score.device_only.robot_accuracy`, the arm-independent device-only floor written into every cell of a seed, e.g. 0.0579 = 7 of 121 at s6; arms above it add identical cloud-standing wins, e.g. 0.0826 = floor + 3 wins on the same question ids)
(checked raw: always-cloud vs b7 s4, mooncake vs b7 vs llf s6, different request logs and routing splits).

### 1. Runs done overnight (since 18:50)

30 valid cells committed: b7 s5 to s7; covex-v6-state s4 (as `_rerun`), s5, s6 (HELD-CODE, see 4); always-cloud s4 to s7
(s5 as `_rerun`); simplestream s4 to s7; querystream-proactive s4 to s7; mooncake s4 to s7; attentionstore-prefetch s4 to s7;
warm-all-lru s4 to s7 (s7 ended 05:44, 22 x 400 on robo004|s000; its low 3,792 tok/s is because 6,814 dashcam requests went unsent, not because it was healthy). Paper core still to run (matrix order): hybrid-F-lhreq s4 to s7 (from 05:44), then old v5-rules s6 and s7, ending about 07:56.
INVALID / skipped (never used): covex-v6-state s4 first attempt (unknown arm, 19:42), covex-v6-state s7 and its rerun (stopped,
held code, 21:14 / 21:16), always-cloud s5 first attempt (preflight refused: orphaned server, 21:16). HTTP 400 counts overnight:
14 always-cloud s7, 16 querystream-proactive s7, 16 attentionstore-prefetch s7, 22 warm-all-lru s7, all on `robo004|s000` (see 4); every other
overnight cell 0. Transport errors with no status (not refusals) range 0 to 77 per cell.

### 2. Paper-core table (BASELINE_MATRIX cells run so far, all valid)

| arm | seed | robot by deadline | robot on time | SS within 2 s | dash | load tok/s | 400s |
|---|---|---|---|---|---|---|---|
| edf | 4 | 0.386 | 5/132 | 49/357 | fail | 4,668 | 0 |
| edf | 5 | 0.291 | 4/127 | 55/356 | fail | 4,657 | 0 |
| edf | 6 | 0.099 | 5/121 | 52/357 | fail | 4,660 | 0 |
| edf | 7 | 0.295 | 1/105 | 65/359 | meet | 4,593 | 14 |
| llf | 4 | 0.394 | 7/132 | 135/357 | meet | 4,551 | 0 |
| llf | 5 | 0.299 | 5/127 | 147/356 | meet | 4,494 | 0 |
| llf | 6 | 0.099 | 9/121 | 167/357 | meet | 4,556 | 0 |
| llf | 7 | 0.314 | 4/105 | 167/359 | meet | 4,513 | 0 |
| b7-edf-feasibility | 4 | 0.371 | 5/132 | 32/357 | fail | 6,163 | 0 |
| b7-edf-feasibility | 5 | 0.307 | 5/127 | 26/356 | fail | 5,202 | 0 |
| b7-edf-feasibility | 6 | 0.091 | 7/121 | 167/357 | meet | 5,004 | 0 |
| b7-edf-feasibility | 7 | 0.324 | 8/105 | 301/359 | meet | 4,531 | 0 |
| always-cloud-fcfs | 4 | 0.371 | 5/132 | 32/357 | fail | 5,491 | 0 |
| always-cloud-fcfs | 5 | 0.315 | 6/127 | 28/356 | fail | 5,663 | 0 |
| always-cloud-fcfs | 6 | 0.083 | 3/121 | 49/357 | fail | 5,352 | 0 |
| always-cloud-fcfs | 7 | 0.295 | 1/105 | 34/359 | fail | 5,931 | 14 |
| simplestream | 4 | 0.144 | 132/132 | 355/357 | meet | 4,426 | 0 |
| simplestream | 5 | 0.299 | 126/127 | 356/356 | meet | 4,430 | 0 |
| simplestream | 6 | 0.165 | 120/121 | 356/357 | meet | 4,431 | 0 |
| simplestream | 7 | 0.286 | 105/105 | 358/359 | meet | 4,422 | 0 |
| querystream-proactive | 4 | 0.371 | 5/132 | 28/357 | fail | 5,636 | 0 |
| querystream-proactive | 5 | 0.299 | 3/127 | 19/356 | fail | 5,608 | 0 |
| querystream-proactive | 6 | 0.083 | 3/121 | 48/357 | fail | 5,350 | 0 |
| querystream-proactive | 7 | 0.295 | 0/105 | 34/359 | fail | 5,332 | 16 |
| mooncake | 4 | 0.371 | 5/132 | 32/357 | fail | 5,663 | 0 |
| mooncake | 5 | 0.307 | 5/127 | 27/356 | fail | 5,950 | 0 |
| mooncake | 6 | 0.091 | 7/121 | 167/357 | meet | 5,152 | 0 |
| mooncake | 7 | 0.333 | 8/105 | 309/359 | meet | 4,523 | 0 |
| attentionstore-prefetch | 4 | 0.371 | 4/132 | 22/357 | fail | 5,880 | 0 |
| attentionstore-prefetch | 5 | 0.315 | 6/127 | 18/356 | fail | 5,682 | 0 |
| attentionstore-prefetch | 6 | 0.083 | 3/121 | 44/357 | fail | 4,848 | 0 |
| attentionstore-prefetch | 7 | 0.295 | 0/105 | 29/359 | fail | 6,005 | 16 |
| warm-all-lru | 4 | 0.371 | 3/132 | 23/357 | fail | 5,595 | 0 |
| warm-all-lru | 5 | 0.307 | 4/127 | 19/356 | fail | 5,902 | 0 |
| warm-all-lru | 6 | 0.074 | 2/121 | 30/357 | fail | 5,552 | 0 |
| warm-all-lru | 7 | 0.295 | 1/105 | 28/359 | fail | 3,792 | 22 |
| v5-rules (old, ablation ladder) | 4 | 0.439 | 40/132 | 170/357 | fail | 4,704 | 0 |
| v5-rules-2 = covex-v6-rules | 4 | 0.485 | 38/132 | 245/357 | fail | 4,729 | 0 |
| v5-rules-2 = covex-v6-rules | 5 | 0.331 | 37/127 | 258/356 | fail | 4,722 | 0 |
| v5-rules-2 = covex-v6-rules | 6 | 0.157 | 32/121 | 259/357 | fail | 4,718 | 0 |
| v5-rules-2 = covex-v6-rules | 7 | 0.390 | 23/105 | 266/359 | fail | 4,730 | 0 |
| hybrid-F-lhreq-noc3 = covex-v6-base | 4 | 0.470 | 35/132 | 337/357 | meet | 4,479 | 0 |
| hybrid-F-lhreq-noc3 = covex-v6-base | 5 | 0.339 | 27/127 | 343/356 | meet | 4,471 | 0 |
| hybrid-F-lhreq-noc3 = covex-v6-base | 6 | 0.248 | 41/121 | 349/357 | meet | 4,487 | 0 |
| hybrid-F-lhreq-noc3 = covex-v6-base | 7 | 0.381 | 19/105 | 354/359 | meet | 4,423 | 0 |

Reading it, per seed: (a) **most baselines saturate** (load above about 5,000 tok/s; SS 18 to 65 of about 357; dashcam fail):
b7 s4 / s5, always-cloud, querystream-proactive, mooncake s4 / s5, attentionstore-prefetch, warm-all-lru; edf sits in the
transition zone at all four seeds; llf just below it. (b) **simplestream is the opposite corner**: on time almost everywhere
(robot 105 to 132 of the pool, SS and dashcam near perfect) but robot correctness 0.14 to 0.30, because it sends robot questions
with about 650 tokens of bounded context (p50 653, max 782) against about 10,800 for noc3; cloud letters are real A to E, not a
placeholder. (c) **covex-v6-base (noc3) is the strongest balanced row**: SS 337 to 354, dashcam meets at every seed. (d)
**covex-v6-rules (v5-rules-2) fails dashcam at every seed**; its robot headline is not consistently above noc3 (ahead at s4, s7;
behind at s5, s6). Not in this table: cascade arms and kvflow-prefetch (held, see 5), r3-streaming and streamscout (released
on the measured device wait, matrix positions after the paper core), lmcache, the 'our versions' block beyond the pair.

### 3. Ladder rung results

**covex-v6-state (rung 2)**, posted by flash at 465273a / c68a186e (re-issued after the name fix), passed the operator gate
(harm_warm computed from the D162 model, never declared; pre-registration 2323a58 an ancestor; harm_warm_capped present).

| seed | robot by deadline | robot on time | SS within 2 s | dash | load | TOUCH issued | budget refusals | status |
|---|---|---|---|---|---|---|---|---|
| 4 | 0.508 | 92/132 | 264/357 | fail | 3,369 | 1,246 | 12,824 | old touch price |
| 5 | 0.433 | 116/127 | 347/356 | fail | 4,501 | 178 | 0 | old touch price |
| 6 | 0.140 | 12/121 | 75/357 | fail | 957 | 0 | 44,382 | **HELD-CODE (D173), not comparable** |
| 7 | | | | | | | | stopped and skipped (held code) |

What the two clean seeds establish (s4, s5): **TOUCH fires live** (1,438 and 178 chosen) although the dry cell predicted zero:
plan_state's gain crosses MARGIN_CF once robot history passes about 18,000 to 19,000 tokens with a question imminent, a
combination the dry cell never sampled (flash 397bdb54; the belief corrector cannot raise the gain, refuted by code path).
**Robot on time rises to 92 and 116** against noc3's 35 and 27. At s4 that gain is partly a **transfer**: touches were priced at
recall_gpu_s(whole prefix) while the planner scored them at harm 0 (flash b988ed6e, cf_planner.py:573-575), so 12,824 budget
refusals left 88 SS unsent (noc3 1) and dashcam on time fell to 1,786 (noc3 6,167). At s5, with 178 touches and 0 refusals,
SS is intact (350 vs 346) and robot is still 116, so **the robot gain does not need the transfer**; its cause (state pricing,
per-type host retention, or the touches) is NOT attributed. **Dashcam failure is rung 1's, not rung 2's**: dashcam on time
rung 1 (v5-rules-2) 773 / 1,219 at s4 / s5, rung 2 1,786 / 2,458, noc3 6,167 / 5,540; v5-rules-2 submits about half the
monitors with ZERO budget refusals in every cell, so the loss is in what the arm ASKS FOR, not what it is charged (flash
afbe7276); rung 2 submits 1.6x more monitors. Halving a deficit is not closing it; no cell of this rung is dashcam-neutral.
**Per-type host retention is live for the first time**: all 269 / 356 SS sends COLD (max_offload_tokens = 0). harm_warm was
priced on exactly one live decision per cell (capped once, correctly, above 18,106 uncached tokens): **no HOLD_BACK or SLICE
conclusion**. Not posted: covex-v6-fair (D165 objective unbuilt), covex-v6 (plan_sync, compounds, episode switch, D170 rule).

### 4. Incidents

1. **edf, always-cloud, querystream-proactive, attentionstore-prefetch and warm-all-lru at s7: 14, 14, 16, 16, 22 x HTTP 400**, all on
   `robo004|s000` with 378 to 587 images, over the 32,768-token context (seed 7 is the only seed with beyond-32k re-asks: 15,
   max history 52,861; flash over32k_s7_finding.json). D170 (user): in scope as a deployment constraint, no capping, seed 7
   kept, refusals are misses (D144 scores a non-200 as the device answer standing). llf, b7, mooncake, simplestream, noc3 and
   v5-rules-2 sent nothing over the limit at s7: the count is each arm's own send decision.
2. **Saturation**: see 2 (a). b7's s4 load of 6,163 tok/s is real, not an artefact: its dashcam requests miss the prefix cache
   far more (1,247 cold vs edf's 703) and its single-shot requests never hit it (all 244 cold).
3. **Offload-verify break (user-approved, 13:50, rc 0)**: positive control PASS (host reload served from host, 8,080 tokens);
   skip-retention (max_offload_tokens = 0) YES; host reload YES; forbid-reload max_load_tokens INCONCLUSIVE (its control was
   contaminated by the forbidden read's own recompute; fixed in the script afterwards); kv_load_tiers = [] NO (ignored). The
   first attempt at 13:28 never ran (my `timeout` wrapper tripped the pilot preflight).
4. **covex-v6-state s4, 19:40: unknown arm** in the harness process (names registered in another process only); then the
   crashed run's **server was orphaned** (start_server preceded make_arm) and the driver's rerun waited for GPU 2 from 19:42 to
   19:45 until I stopped it. flash fixed both: names register in arms.py (c821fc3), arm built before the server plus an atexit
   backstop (86ecf29c). My watch now alerts on a GPU held 2 min with no harness process.
5. **Held code, 20:30 to 21:15**: flash's 8733280 added a d162 pricing switch to covex-v6-state that DEFAULTED ON, so s6 ran the
   held first-token charge (its own D102 proof fails) and budget-starved at t = 264 s (44,382 refusals). I stopped s7 (D106
   blocker); flash set the default off (778a4e27). D173 labels s6 / s7 held-code.
6. **My error: SIGTERM orphaned two servers** when stopping s7 and its rerun (Python atexit does not run on SIGTERM); cost
   always-cloud s5's first attempt (preflight refused) and about 3 min of idle GPU. Rule now: stop a harness only with SIGINT.
7. **Touch is mispriced** (flash 9daceb59): measured warm touches are 1,246 / 1,246 WARM with 3 uncached tokens (p50) and 1
   output token; time to first token p50 0.53 s is 70 to 98 percent queueing by the D162 decomposition, while the charge
   scaled with prefix length (3.4x to 9.5x overcharge). The re-price was implemented and HELD: the first-token charge fails
   D102 (double-counts the queue term) and the work-only charge then fails D102's utilisation half (its per-request intercept
   bills 46 to 51 percent of the wall clock; utilisation 1.07 to 1.34 of wall). **The touch price must not be lowered to make
   dashcam recover; it changes only if a measurement says it is wrong.**
8. **D166 5 MB guard**: attentionstore-prefetch decision.jsonl.gz s4 (8.3 MB), s5 and s6 not committed, kept on disk.
9. **Counters missing**: coordinator_result.json has no `counts` in some cells (b7 s4 / s5, mooncake s4 to s6, warm-all-lru s4
   to s6, both n20 sweep cells), which is also why cell.json's n_requests / n_errors are null there; their budget refusals
   are NOT RECORDED, not zero. Scores, HTTP counts and loads come from other files and are unaffected.

### 5. PROVISIONAL decisions overnight (D106 / D116)

1. **covex-v6-state s6 and s7 skipped at 20:16, re-queued at 20:29**: skipped after flash withdrew them on the named touch
   defect; re-queued because s5 showed the robot gain without the budget transfer, so replication was the open question.
   (s6 then ran held code and s7 was stopped; see 4.5.)
2. **covex-v6-state s4 to s7 skipped as a blocker at 19:42, released at 19:46** after the name fix was proved through the
   harness's own entry point with a negative control.
3. **No diagnostic cells queued** (-notouch, -nobelief, -noprice): outside the brief; recommended for the user (notouch at
   s4 separates touch from the robot gain; noprice at s5 tests flash's hypothesis that state pricing explains the dashcam
   recovery, NOT established).
4. **Old-tag r3-streaming / streamscout gap-fill cells dropped** (user ruling ~16:15); cascade arms held until their
   pre-registered DEV threshold calibration; kvflow-prefetch held to the 2026-11-28 cutoff (characteristic decision
   unexpressible); thinking-qwenvl not a registered live2 arm.

**D179 shares rung (covex-v6-state-shares, `_L3_epg_rq30`, s4 to s7, 2026-11-22 16:17 to 17:43, all VALID, 0 errors)**. Operator reading of cell.json; flash's pre-registered scorer gives the committed figures. Base = `hybrid-F-lhreq-noc3` rq30 (original name, D172).

| seed | by_deadline shares / uo / base / floor | robot on time shares / uo / base | (1) dash pooled on-time shares / base | (2) robot on-time gain retained | (3) assistance within 2 s | alert hold p50 / p90 (s) | release_infeasible alert / recall / asst | W over W_max without recall |
|---|---|---|---|---|---|---|---|---|
| 4 | 0.545 / 0.614 / 0.470 / 0.371 | 60 / 118 / 35 of 132 | 0.744 / 0.509 PASS | 30 % FAIL | 96.4 % PASS | 0.149 / 0.358 | 2,685 / 70 / 12 | alert+assistance |
| 5 | 0.417 / 0.425 / 0.339 / 0.299 | 76 / 115 / 27 of 127 | 0.745 / 0.457 PASS | 56 % FAIL | 96.3 % PASS | 0.144 / 0.322 | 2,753 / 48 / 12 | alert alone, alert+assistance |
| 6 | 0.306 / 0.496 / 0.248 / 0.058 | 63 / 107 / 41 of 121 | 0.793 / 0.534 PASS | 33 % FAIL | 98.0 % PASS | 0.149 / 0.318 | 2,198 / 46 / 7 | alert alone, alert+assistance |
| 7 | 0.438 / 0.476 / 0.381 / 0.295 | 37 / 83 / 19 of 105 | 0.787 / 0.638 PASS | 28 % FAIL | 98.1 % PASS | 0.147 / 0.340 | 2,172 / 46 / 7 | alert+assistance |

Planner abandonment 0 at every seed. Shares fixes the alert side (alert hold p50 about 0.74 s under uo, about 0.15 s here; dashcam meets at every seed) and loses most of uo's robot gain; check (2) fails at all four seeds, so the pre-registered contingency (addendum 9 item A: rung 2 adopts c5attr as a logged override) is for the user's verdict. Dry cells showed recall in every W overrun; live, overruns without recall occur at every seed (flagged to flash).

**Port-rule status for the baseline table (flash cb9b9968, 2026-11-22 ~15:30)**: cascade-routing (0 robot escalations in both committed cells) and r3-streaming (0 in ALL FOUR committed cells, newly found) FAIL the port rule, so they sit exactly on the device-only floor by construction and are EXCLUDED from scored baselines, ruled by the user under D130 (reports/study_port_rule_exclusions.md, StudyPORT-EXCL at deb4e563); their cells are kept for provenance and listed with the reason. confidence-cascade PASSES (44 / 35 / 57 escalations at s4 / s5 / s6), but none of its s5 or s6 escalations arrived inside 3 s (n_cloud_standing 0; a live-timing rerun item under D154 (5)); its s6 0.0579 equals the floor, NOT below it (an earlier operator flag was a misread). A real below-floor effect exists in 10 of 127 cells: an ON-TIME but WRONG cloud answer replaces a correct device answer (worst simplestream s4 0.144 vs floor 0.371, streamscout s4 0.136); every such cell has n_cloud_standing > 0.

**C5 attribution candidate (covex-v6-state-uo-c5attr), scope declared before its cells**: of the cap halvings in the committed cells, the share the rule can reach (every slow monitor since the last adjustment overlapped a robot prefill the coordinator released with at least 200 uncached tokens) is 63.4 / 63.7 percent at rung 2 (covex-v6-state-uo s4 / s5: 142 of 224, 121 of 190) and 50.7 to 54.7 percent at rung 1. Out of reach by design: halvings on monitors that overlapped nothing of ours, and halvings where the EWMA exceeds 0.8 s while NO single pending monitor is slow (19.2 / 16.3 percent at rung 2, 30.5 to 37.6 at rung 1). The reachable share is very sensitive to the user's 200-token threshold (at 2,000 it is 14.3 / 19.0 percent at rung 2): most attributed prefills are small (median about 1,375 uncached), not the 3,071-token warm builds. The rule does move the cap (Step 2b on committed traces: 436 to 514 of 539 to 599 halvings prevented per rung-1 cell). An earlier figure of "8 to 9 in 10" classified monitors, not halvings, and is withdrawn (flash, c5attr_trip_attribution.json).

**Which on-time rule the dashcam counts use (flash C5-A)**: every dashcam "on time / late / unsent" count quoted in this summary and in the progress reports comes from outcomes.jsonl `cloud_payload.on_time` (the COORDINATOR's first-token flag) and `cloud_payload == null` for unsent. The committed scorer counts a monitor on `t_delivered` (first token plus a flat 0.0222 s forward hop), so its on-time figures are slightly lower, by about 94 to 181 instants per cell. The `dash` meet / fail column is the scorer's.

**Rulings D176-D178 (user, 2026-11-22 ~10:30)**: (1) the 18 over-limit robot questions (seed 7, `robo004|s000`) are EXCLUDED from headline robot results for every arm and reported separately; no run changes (the seed-7 rows above still include them and are to be re-scored). (2) Our arms count value in on-time cloud answers (accuracy not weighted at runtime) and use per-type guard thresholds; internal to our arms, matrix unaffected. (3) Targets: alert 25 % per episode, recall 90 %, assistance 90 %; pass / fail is computed OFFLINE, so baseline cells are re-scored, never rerun. Server engine confirmed from the installed dist-info (no host Python): vLLM 0.31.0+cu129, the live server runs from that venv.

**Device-wait arms (2026-11-22 morning)**: r3-streaming s4 / s5 and streamscout s4 / s5 ran on the MEASURED Orin device wait (released in runs/DEVWAIT_READY), but their run labels and headers say `device-wait-proxy-0.567`: drivers v17 to v23 stamped that label unconditionally. **Their label is wrong, the behaviour is the measured wait**; headers are left as committed and this note is the correction (driver v24 labels released arms `device-wait-measured`). Also stale, for the same reason, is the `proxy-0.567` stamp scorer/score.py cascade_device_wait() puts on every cascade score header (it compares two constants; the coordinator made 18,364 measured lookups on confidence-cascade with no fallback; left for the user, since fixing it relabels committed cells). **confidence-cascade** (seeds 4-7) is released with one DEV floor per confidence type (robot 0.800, ss_mcq 0.986, ss_free_form 0.985, ss_point 0.817; prereg d8b8861 before calibration 4cebda6); its episodic tau_trigger is UNEXPRESSIBLE in live2 (placeholder 0.0 stream scores), so its dashcam behaviour must not be attributed to a fitted threshold. **eco-llm** (seeds 4-7) is released because the calibration gate does NOT APPLY to it (no threshold, reads no confidence), not because it met one. **cascade-routing stays held** for the user: no cost budget B to calibrate lambda against, and it fails the port rule (0 of 489 characteristic decisions; lambda 0.02 vs 2.0 identical).

**E5 memory sweep (user ruling ~09:00, driver v23)**: after BASELINE_MATRIX, the paper core at `_kv0.5` (covex-v6-base, covex-v6-rules, edf, llf, b7, always-cloud, mooncake, attentionstore-prefetch, simplestream, querystream-proactive, warm-all-lru; seeds 4 and 5; same workload), from about 10:25. `_kv0.5` is the committed `_kv0.25` mechanism, `--gpu-kv-tokens 31472` = 62,944 / 2 with capacity enforcement on. **CAVEAT for every `_kv0.5` / `_kv0.25` row: it halves the HARNESS's LOGICAL pool (coordinator belief and enforcement); the engine's real vLLM KV pool is unchanged, so these cells test the policy under a smaller believed capacity, NOT vLLM under a smaller allocation.** The over-limit rule (D175) cannot move seeds 4 and 5 (histories top out near 26,900 tokens); covex-v6-rules is proved identical at s4, covex-v6-base at s4 requested of flash.

**For the user's ruling**: (a) touch pricing (first-token and work-only charges both fail D102; planner scores TOUCH at harm 0
regardless); (b) the rung-1 dashcam submission gap (flash's concurrency-limit hypothesis, untested; needs per-epoch visible but
unreleased monitors beside in-flight occupancy); (c) the optional diagnostics in 5.3; (d) where to keep the over-5 MB decision
logs.

## 06:00 SUMMARY (2026-11-21, H100 overnight; D156 (5) form)

**v5-rules table.** 3 s robot deadline, 16 devices, EP-G dashcam episodes + per-frame robot upload (`upload-pf`), race-fixed
path (flash 2b8714c), D155 headline = correct answers delivered BY THE DEADLINE. Dashcam is PROVISIONAL until the Orin's EP-G
device re-record. Excluded dashcam instants (D153 floor 3, identical for every arm at a seed): s4 1,429 of 13,193 (10.8 %),
s5 1,431 of 13,200 (10.8 %). `warm` = robot questions whose request hit a cached prefix (ENGINE-observed cache_path), over
robot questions released to the cloud. Errors = non-200 requests from request.jsonl.

| arm | seed | correct by deadline | device-only row | robot on time | SS within 2 s | dashcam all meet | errors | warm / released |
|---|---|---|---|---|---|---|---|---|
| **v5-rules** | 4 | **0.45** | 0.30 | 9/20 | **188/357** | **no** | 0 | 12/20 |
| hybrid-F-lhreq-noc3 (v5 base) | 4 | 0.45 | 0.30 | 8/20 | 351/357 | yes | 1 | 0/12 |
| b7-edf-feasibility | 4 | 0.40 | 0.30 | 7/20 | 330/357 | yes | 0 | 0/12 |
| mooncake | 4 | 0.40 | 0.30 | 7/20 | 330/357 | yes | 0 | 0/12 |
| eco-llm | 4 | 0.30 | 0.30 | 15/20 | 333/357 | yes | 5 | 0/20 |
| edf | 4 | 0.30 | 0.30 | 2/20 | 122/357 | yes | 0 | 3/4 |
| llf | 4 | 0.30 | 0.30 | 1/20 | 188/357 | yes | 0 | 1/1 |
| warm-all-lru (`_rf`) | 4 | 0.30 | 0.30 | 1/20 | 30/357 | no | 67 | 6/13 |
| **v5-rules** | 5 | **0.40** | 0.32 | 6/25 | **195/356** | **no** | 1 | 13/24 |
| hybrid-F-lhreq-noc3 (v5 base) | 5 | 0.36 | 0.32 | 8/25 | 353/356 | yes | 0 | 0/12 |
| b7-edf-feasibility | 5 | 0.36 | 0.32 | 2/25 | 326/356 | yes | 0 | 0/12 |
| mooncake | 5 | 0.36 | 0.32 | 2/25 | 326/356 | yes | 1 | 0/12 |
| eco-llm | 5 | 0.20 | 0.32 | 13/25 | 324/356 | yes | 0 | 0/24 |
| edf | 5 | 0.32 | 0.32 | 0/25 | 93/356 | yes | 0 | 1/1 |
| llf | 5 | 0.32 | 0.32 | 0/25 | 142/356 | yes | 0 | 0/0 |
| warm-all-lru (`_rerun`) | 5 | 0.32 | 0.32 | 0/25 | 21/356 | no | 52 | 3/20 |

**The rest of the EP-G handful at seed 4** (same workload; correct by deadline / robot on time / SS within 2 s / dashcam):
hybrid-F-lhreq WITH C3 0.35 / 16/20 / 351/357 / yes (against its C3-off twin's 0.45 / 8/20: the RECENT fallback buys
deliveries that are wrong, as flash pre-registered); simplestream 0.15 / 20/20 / 355/357 / yes; querystream-proactive
0.35 / 4/20 / 100/357 / yes, with the engine SATURATED (TTFT p50 about 35 s on every class; 6,230,473 uncached prompt
tokens, 17 percent more than b7, above the saturation knee flash bounds at 4,512 to 5,192 uncached tok/s);
r3-streaming 0.30 / 0/20 / 0/357 / NO (it declined all 376 recalls and released 3,905 of 11,764 monitors at 1,347 tok/s:
its dashcam failure is a DECISION, not a queue); cascade-routing 0.30 / 0/20 / 356/357 / yes (declined all 20 robot
questions, released every SS question; 4,356 tok/s). The two cascade arms' robot-side characteristic decision is ZERO
(Rule 2 unexercised), and their single-shot rows are set by each adapter's default on the MISSING device-confidence
field (cascade-routing defaults CLOUD, r3-streaming DEVICE), so they are NOT measurements of confidence-based routing
until the flagged confidence-injection wiring change is applied.

**Reading (flash's analysis: reports/study_v5_rules.md, study_cost_model_gate_d156.md; numbers above are the H100's).**
- v5-rules against its OWN base (noc3): correct by deadline 0.45 = 0.45 (s4), 0.40 against 0.36 (s5); pooled one discordant
  question of 45, McNemar exact p = 1.0, so NO gain. It costs 163 + 158 = 321 single-shot questions and the dashcam SLO
  (4,045 and 4,619 monitors released against about 11,000), through 3,253 / 2,894 warm-ahead pieces queuing ahead of them.
- The comparison is EXACT: v5-rules' extra releases are precisely the base's declines (8 of 8 at s4, 12 of 12 at s5). Of the
  20 extras, 16 ended on the device answer the base already had; of 4 cloud answers, 2 right where the device was wrong, 1
  wrong where the device was right. v5-rules escalates 44 of 45 robot questions, the base 24 of 45.
- Warm-ahead DOES reach the warm state (engine: 12/20 and 13/24 robot questions, about 57 %) and still converts to nothing:
  the prefills that buy warmth fill the queue that makes warm answers late. noc3's warm 0 is structural (0 pieces, post-fix).
  The arm's own belief counter (`release_at_GPU-WARM`) UNDER-reports warmth and was retracted as a source.
- warm-all-lru (warm everything) reaches LESS warmth (16 of 48, 33 %) than targeted v5-rules, and saturates the engine.
- SATURATION, by within-run 100 s windows (flash 939b300 and its later correction). Cells separate sharply in SEVERITY,
  with no cell at intermediate worst-window first-token latency, but run-mean uncached tok/s does NOT predict which side a
  cell falls on: between 4,670 and 4,707 tok/s both behaviours occur, across two independent cell sets (tonight's EP-G and
  CAL1F cells, and the 29 earlier gate cells), and no crossing criterion among 2.0, 5.0 and 10.0 s separates all 58. A
  bracketed threshold on this axis ([4,512, 4,686]) was claimed and WITHDRAWN (flash); the transition is a ZONE of roughly
  4,500 to 4,750 uncached tok/s and something other than run-mean load decides it. Past it, first-token latency is
  ACCUMULATED BACKLOG, not current rate. **The crossing cells' POOLED TTFT is not a property of the arm and must NOT be
  compared between them** (it reports where the median request fell on the ramp); compare their terminal 100 s window
  instead. The crossing cells: v5-rules s4 and s5, querystream-proactive s4 and s5, and the six warm-all-lru cells (1F,
  EP-G pre-fix, s5 rerun, s4 `_rf`, s4 kv0.25 `_rf`, and the s5 invalid first attempt). Pooled TTFT figures quoted for those
  cells elsewhere in this report are descriptive only; no scored result moves (deadline and on-time are per request).
- Per-frame upload hurts the rebuild-on-demand arms (edf, llf: SS 93 to 188 of 356); arms that do not rebuild are unchanged
  against their one-frame runs.

**Gate and v5.** 32B engine-action confirmation PASSED (M1, M3 in b685fbb; M2 in e77fa65, touch keeps T in GPU, U goes to
host, 3 of 3). The cost-model gate FAILS (flash 6dc49db: negative predicted TTFT on 52 % of fit and 62 % of held-out data,
held-out p90 error 31.9 s), so MARGIN_CF is unset and FULL v5 DID NOT RUN. Options are flash's, default leave-it.
Refit (flash 323dbd4, prediction pre-registered at 1a491f9) with the race-contaminated fit cell swapped for its race-fixed
rerun (warm-all-lru 1F `_cal1f_rf`, 0 HTTP 400 against 226): still FAIL and WORSE (intercept -2.37 to -2.87 s, held-out p90
error 31.9 to 41.2 s), so the failure is the model FORM, not the race. The 226 fast-failing 400s had MASKED that cell's
saturation (race-clean first-token p50 64.5 s against 31.9 s), a third race confound besides errors and suppressed warmth;
it is material only for that cell (flash's D159 (E) 400 census).

**Incidents.** (1) 5d7c084 broke `import hybrid` in every live run at 16:37 (llf n16 s6 lost its first attempt and orphaned
a server); fixed in run_live2_real.py (e2c8933) and in hybrid_arm (e7b4dda). (2) The SUBMISSION RACE: bytes marked sent at
submission, so warm-ahead pieces 0.12 s apart referenced unregistered images: 226 HTTP 400 on warm-all-lru CALIBRATION-1F,
then 4,244 on the EP-G held-out cell 1 (SATURATED, 29 %), with dashcam TTFT about 100 s; fixed by flash (2b8714c: bytes
count as sent only on HTTP 200), proven live (0 x 400 on every later warm-all cell). (3) warm-all-lru s5 first attempt
INVALID: one 21 s lateness burst at t = 1,138 to 1,159 s after a coordinator-link reset; the rerun was valid. (4) Score
failed on warm-all-lru 1F from scorer/data_sources version skew within one process (f1d32c7 pushed mid-run). (5) n_requests
and n_errors come back null in cell.json for warm-all and querystream cells (DEFECT; counts taken from request.jsonl).
(6) DEFECT: dashcam rows in request.jsonl carry `session_id` null (robot and single-shot rows are populated), so anything
keyed on dashcam session identity pools all dashcam devices silently (it voided one of flash's tests tonight); worth a grep
of the tree before any per-dashcam-session analysis. An engine-side cache log (per-session insertion and eviction) is the
INSTRUMENTATION GAP that keeps the cause of the knee crossing open.

**Labels and PROVISIONAL decisions.** `dashcam-1f` (sensitivity only) = every cell before the EP-G switch; `upload-30s` = every
cell before the per-frame cells; `race-affected` = piece-chaining cells before 2b8714c (warm-all-lru and -reactive 1F,
held-out cell 1 pre-fix, held-out -reactive); `proxy-0.567` = cascade arms before the Orin's warm latencies; `no-prefetch` =
mooncake (D155 (5)). PROVISIONAL: the EP-G sweep after the handful (the brief named only the handful); `_kv0.5` / `_kv0.25`
= the harness's LOGICAL pool (the engine pool is pinned); the D157 margin population is the four held-out cells, of which
-reactive and -off ran before the race fix (-off issues no pieces; -reactive did, with 0 errors): whether that counts as
"clean after the fix" under D158 (1) is the user's.

> **D153 LABEL (user decision 2026-11-20 17:10): every cell in this report up to the EP-G switch is `dashcam-1f`.** Its
> dashcam devices send ONE frame per call, not the append-only episode format (EP-G) that D153 makes the dashcam
> workload. These cells are SENSITIVITY ONLY and are never a headline. That covers the frozen grid, the post-fix redo, the
> 5 s sweep cells, the D151 calibration cells and the 3 s handful cells named `*_L3` without `_epg`. Cells named `*_epg`
> run the EP-G workload from flash's EP-G live-bodies commit; driver v8 switches to them at the first run boundary after
> that commit lands with its proofs. The driver also writes the workload into every cell's label and log line.

## HEADLINE (user form, 2026-11-20 08:05): pooled rates with paired-by-seed bootstrap CIs

16 devices, common support seeds 0, 4, 5 (every arm; seed 6 added when hybrid-F6's seed-6 run lands). Rates pooled over
the seeds; on time = delivered within the deadline (robot 5 s, SS 2 s) by an HTTP 200 request. 95 percent CIs from a
bootstrap PAIRED BY SEED: opportunities resampled within each seed, the same draw for every arm (all arms share each
seed's trace), B = 10,000; differences against b7 on the same draws. Measurability (D82): every run has >= 20 robot
questions (24, 20, 25); feasible counts 18, 15, 22. File: `results/orchestration/live2/frozen_test/frozen_headline_n16.json`
(script `experiments/orchestration/live2/frozen_headline.py`).

| arm | robot on time over FEASIBLE | minus b7 | SS on time at 2 s | minus b7 | dashcam all-meet |
|---|---|---|---|---|---|
| b7 | 50 of 55 = 0.909 [0.836, 0.982] | | 969 of 1,069 = 0.907 [0.889, 0.923] | | 3 of 3 runs |
| eco-llm | 49 of 55 = 0.891 [0.800, 0.964] | [-0.055, 0.000] | 890 of 1,069 = 0.833 [0.810, 0.855] | **[-0.090, -0.058]** | 3 of 3 |
| mooncake | 50 of 55 = 0.909 [0.836, 0.982] | [0.000, 0.000] | 970 of 1,069 = 0.907 [0.890, 0.924] | [-0.004, +0.006] | 3 of 3 |
| hybrid-F-lhreq | 53 of 55 = 0.964 [0.909, 1.000] | [-0.018, +0.127] | 1,023 of 1,069 = 0.957 [0.944, 0.968] | **[+0.034, +0.067]** | 3 of 3 |
| hybrid-F6-lhreq | 51 of 55 = 0.927 [0.855, 0.982] | [-0.055, +0.091] | 1,011 of 1,069 = 0.946 [0.932, 0.959] | **[+0.022, +0.057]** | 3 of 3 |

Reading: on SS on time, hybrid-F and hybrid-F6 are ahead of b7 and eco-llm behind it, with CIs excluding zero; mooncake
equals b7. On robot on time over feasible questions no arm differs from b7 with a CI excluding zero (55 feasible
questions). Capacity is not reported until 18 devices is run (user ruling). Per-run D133 verdicts are in the table below,
labelled: **per-run verdicts are fragile: 14-15 feasible questions per run tolerate at most one miss at 0.90.**

## HEADLINE AFTER D144 (2026-11-20 07:45)

D144 (user, 2026-11-20): sizes 16 and 18 (20 saturated: b7 n20 s0 delivered 2 of 28 robots); a dropped or
over-context request is a per-question MISS, the run counts (error count and requests offered recorded, saturated if
> 5 percent errored); seed 0 is back for every arm. Where a cell had a first attempt and a rule-5 rerun, the FIRST
attempt is the cell (PROVISIONAL); reruns kept and labelled. The scorer (41b0eae) already counts an undelivered
request as a miss with the device answer standing; only b7 n16 s0's first attempt needed rescoring (17 of 24, equal to
its rerun). Robot counts reconcile with the scorer in every run (`frozen_feasible.json`, all_match_scorer true).

**Common support, 16 devices, seeds 0, 4, 5 (seed 6 hybrids running):**

| arm | robots on time over FEASIBLE (of 55) | over all (of 69) | SS on time at 2 s (of 1,069) | request errors (s0, s4, s5) |
|---|---|---|---|---|
| b7 | 50 | 50 | 969 | 1, 0, 0 |
| eco-llm | 49 | 49 | 890 | 1, 0, 0 |
| mooncake | 50 | 50 | 970 | 0, 0, 0 |
| **hybrid-F-lhreq** | **53** | **53** | **1,023** | 1, 0, 0 |
| hybrid-F6-lhreq | 51 | 51 | 1,011 | 1, 0, 0 |

**Correction (2026-11-20 08:05, found by the A6000 session, re-derived here from the run files).** A request the server
REFUSED was still counted on time: `coordinator.py` stamps a cloud answer's `on_time` from its completion time alone,
and the scorer's `_within` reads `t_delivered`, so the HTTP 400 over-context request (opp0010837, history 33,781
tokens) scored as an on-time cloud answer with letter "X" in eco-llm, hybrid-F and hybrid-F6 at 16 devices seed 0.
Rule applied from here on (D144): **on time = delivered within the deadline by a request that returned HTTP 200.**
Effect: the all-questions figure drops by one in exactly those three cells (eco-llm 17 to 16, hybrid-F 18 to 17,
hybrid-F6 17 to 16 of 24); every other n16 cell has 0 such answers. The question is INFEASIBLE by the trace rule, so the
feasible column and every D133 verdict are unchanged. The harness is not changed mid-sweep; the rule is applied in
analysis to every cell.

**RECENT charged but not sent: precise description (2026-11-20 08:40; user ruling: fix before the first RECENT-using arm).**
- CHARGED: `coordinator._submit_recall` computes `tokens = cstate.tokens_for_representation(rep)`; for RECENT that is the
  recent window, `RECENT_WINDOW_TOKENS` = 467 (capped at the history). The GPU budget is charged
  `recall_gpu_s(tokens, readiness)` and the submission carries `est_tokens = tokens`.
- SENT: the body's frame list is built from `s.frames`, EVERY frame of the session (375 frames on the over-context
  question), whatever the representation. The server therefore prefills the full history.
- SCORED: what was sent. The delivery time is the full-history prefill's, the cloud letter is answered from the full
  history; nothing in scoring sees the 467-token charge. So a RECENT release behaved exactly like a D2 release on the wire
  while being priced as RECENT.
- TOUCHED (completed runs; RECENT releases per run): eco-llm n16 s0 5, s4 5, s5 3, s6 5, n14 s0 3; hybrid-F n16 s0 5, s4 5,
  s5 3, s6 5; hybrid-F6 n16 s0 7, s4 6, s5 4, s6 7 (reruns the same). b7 and mooncake never release RECENT (372 of 372 D2).
  These RECENT releases are mostly infeasible robot questions that b7 would reject and C3 / eco-llm convert; sent as true
  RECENT they would likely arrive on time with lower accuracy. They cannot be RESCORED (the true RECENT request was never
  made); they need REDOING if the user wants these arms measured with RECENT actually sent.
- FIX (prepared, applied with the driver stopped before simplestream, harness tests run with no server up): a RECENT
  release sends the session's most recent k frames, k = ceil(frames x charged tokens / history tokens), at least 1;
  every other representation's frame list is byte-identical. Scheduling arms before simplestream run unchanged.


Dashcams all meet in every cell. Seed 6 (baselines only so far): b7 14 of 14 feasible / 337 SS, eco-llm 13 of 14 /
301, mooncake 14 of 14 / 334. No run is saturated by the 5 percent rule.

**PER-RUN D133 VERDICTS (fragile: 14-15 feasible questions per run tolerate at most one miss at 0.90; capacity itself is reported only once 18 devices is run).** Corrected 2026-11-20: The earlier statement "no run meets capacity" was WRONG for D133:
it came from the scorer's `capacity_met`, which computes the robot target over ALL questions (`robot_pool_on_time /
robot_pool_n`, e.g. hybrid-F s4 15 of 20 = 0.75). Under D133 the robot target is p 0.90 within 5 s over FEASIBLE
questions (matched per opportunity_id, flash's feasibility rule); the all-questions figure is reported beside it and
does not decide capacity. Verdict per run = dashcams all meet AND robot feasible on-time >= 0.90 AND >= 20 pooled
robot questions (the D82 count of all robot questions in the run) AND SS on time >= 0.90 within 2 s. Every row below
states both denominators; the scorer's own flag (all-questions rule) was false in every row.

| run | dashcams | robot feasible | robot all (pool) | SS at 2 s | D133 verdict |
|---|---|---|---|---|---|
| b7 n16 s0 | meet | 17 of 18 (0.944) | 17 of 24 | 317 of 356 (0.890) | fails (SS) |
| b7 n16 s4 | meet | 14 of 15 (0.933) | 14 of 20 | 332 of 357 (0.930) | **MEETS** |
| b7 n16 s5 | meet | 19 of 22 (0.864) | 19 of 25 | 320 of 356 (0.899) | fails (robot, SS) |
| b7 n16 s6 | meet | 14 of 14 (1.000) | 14 of 20 | 337 of 357 (0.944) | **MEETS** |
| eco-llm n16 s0 | meet | 16 of 18 (0.889) | 16 of 24 | 292 of 356 (0.820) | fails |
| eco-llm n16 s4 | meet | 14 of 15 (0.933) | 14 of 20 | 294 of 357 (0.824) | fails (SS) |
| eco-llm n16 s5 | meet | 19 of 22 (0.864) | 19 of 25 | 304 of 356 (0.854) | fails |
| eco-llm n16 s6 | meet | 13 of 14 (0.929) | 13 of 20 | 301 of 357 (0.843) | fails (SS) |
| mooncake n16 s0 | meet | 17 of 18 (0.944) | 17 of 24 | 319 of 356 (0.896) | fails (SS) |
| mooncake n16 s4 | meet | 14 of 15 (0.933) | 14 of 20 | 332 of 357 (0.930) | **MEETS** |
| mooncake n16 s5 | meet | 19 of 22 (0.864) | 19 of 25 | 319 of 356 (0.896) | fails (robot, SS) |
| mooncake n16 s6 | meet | 14 of 14 (1.000) | 14 of 20 | 334 of 357 (0.936) | **MEETS** |
| hybrid-F n16 s0 | meet | 17 of 18 (0.944) | 17 of 24 | 341 of 356 (0.958) | **MEETS** |
| hybrid-F n16 s4 | meet | 15 of 15 (1.000) | 15 of 20 | 339 of 357 (0.950) | **MEETS** |
| hybrid-F n16 s5 | meet | 21 of 22 (0.955) | 21 of 25 | 343 of 356 (0.963) | **MEETS** |
| hybrid-F6 n16 s0 | meet | 16 of 18 (0.889) | 16 of 24 | 335 of 356 (0.941) | fails (robot) |
| hybrid-F6 n16 s4 | meet | 14 of 15 (0.933) | 14 of 20 | 334 of 357 (0.936) | **MEETS** |
| hybrid-F6 n16 s5 | meet | 21 of 22 (0.955) | 21 of 25 | 342 of 356 (0.961) | **MEETS** |
| eco-llm n14 s0 | meet | 11 of 11 | 12 of 15 | 315 of 357 | not measurable (pool 15 < 20) |
| mooncake n14 s0 | meet | 11 of 11 | 11 of 15 | 326 of 357 | not measurable (pool 15 < 20) |
| b7 n20 s0 | FAIL | 2 of 19 | 2 of 28 | 5 of 477 | fails (saturated size) |

At 16 devices, seeds 0, 4, 5: hybrid-F meets D133 in 3 of 3 runs, hybrid-F6 2 of 3, b7 and mooncake 1 of 3 (2 of 4
with seed 6), eco-llm 0. The binding constraint for the baselines is single-shot on time (b7 s0 misses at 0.890 by
four questions); for hybrid-F6 at s0 it is the robot feasible fraction (16 of 18). Several verdicts sit within one or
two questions of the 0.90 line.

## MORNING SUMMARY (2026-11-20 07:25)

**What ran overnight.** StudySS1-32B and StudySS2-32B (complete, numbers only, on origin); the SS timing measurement;
the D134 published-baseline queue (19:52 to 21:05, on MIXED, while waiting); then the THREE-TYPE frozen grid from
21:08 (1200 s, 40:40:20, LH-REQ EVAL robots, SS RefSpatial + RealWorldQA EVAL, tight 27 GiB, push-all, memory
enforcement on), baselines first and hybrid-F-lhreq / hybrid-F6-lhreq from 02:16 after "policy-F ready (frozen)".
The grid is still running (14-device cells now; 20 and 24 deferred, see decision 6).

**Headline table, 16 devices, common support (seeds 4 and 5 complete for every arm; all runs valid, 0 request errors,
dashcams all meet in every run, no run meets capacity). All-questions robot figure; feasible-question column to be
added offline (needs the trace-side feasibility rule, run when no driver is active).**

| arm | robots on time, s4 + s5 | SS on time at 2 s, s4 + s5 | robot answers sent as RECENT | seed 6 (robots / SS) |
|---|---|---|---|---|
| b7 | 33 of 45 | 652 of 713 | 0 of 36 | 14 of 20 / 337 of 357 |
| eco-llm | 33 of 45 | 598 of 713 | 8 of 44 | 13 of 20 / 302 of 357 |
| mooncake | 33 of 45 | 651 of 713 | 0 of 36 | 14 of 20 / 335 of 357 |
| **hybrid-F-lhreq** | **36 of 45** | **682 of 713** | 8 of 44 | queued (06:32 refusal) |
| hybrid-F6-lhreq | 35 of 45 | 676 of 713 | 9 of 44 | queued (06:32 refusal) |

Reading: on two seeds hybrid-F is ahead of every baseline by 3 robot questions of 45 and 30 SS questions of 713;
F6 does not improve on F. Two seeds and small margins: a direction, not a settled effect. mooncake equals b7 on
every seed: its 377 keep-warm actions find nothing resident (memory enforcement evicted nothing in any run; peak
GPU-resident history 0), an unexercised mechanism, not evidence about mooncake.

**hybrid-F6 caveat (decision period).** C6 is alive live (375 and 385 chooser calls, 13 and 12 decisions changed,
c6_scorer_error 0) but it breaches the 100 ms decision period: 322 and 323 of about 12,000 periods over 100 ms
(2.7 percent), p99 207 and 150 ms, max 670 and 517 ms; hybrid-F's p99 is 1.3 ms with 0 breaches. An F6 result is
therefore partly a late coordinator, reported beside it, not discarded.

**Skipped cells (INVALID twice, rule 5; data kept):** eco-llm, hybrid-F and hybrid-F6 at 16 devices seed 0 and
eco-llm at 14 devices seed 0 (one seed-0 LH-REQ question whose history reaches 33,839 tokens, over the 32,768
context; seed 0 only, every size); b7 at 20 devices seed 0 (127 and 111 transport ReadErrors: overload, 97 percent of
the committed 32B peak). Headline uses common support (seeds 4, 5, 6) so no arm is selected by its representation
choice; seed-0 b7 and mooncake are kept and marked excluded-from-headline.

**Incidents (not measurements, all set aside):** 21:05 every cell refused at preflight (single-shot images not
staged; fixed); 02:12 eleven cells refused (my own dry proof overlapped a boundary; repaired); 06:32 three cells
refused (an automatic git gc triggered by the driver's commits, up to 819 percent CPU; repo-local gc.auto disabled,
cells requeued).

**Decisions still needed from the user:** (1) grid sizes 16 and 20 (20 overloads the server) or 16 and 18; (2) do
transport errors invalidate a run or count as misses; (3) does an over-context request invalidate a run or count as
a miss (a miss restores seed 0 for every arm); (4) C6 does about 94 percent of its work on single-shot requests,
against D143 C's robot-only design; guarding it would change decisions.

## 0. Morning summary (kept current)

- **StudySS1-32B: DONE and on origin** (numbers only, no qualification verdict). VizWiz val 4,319 of 4,319 scored, mean
  VQA accuracy 0.665; EgoThink 700 of 700 scored, mean containment 0.477; 0 errors; manifest order verified; prefix
  cache verified cold (0 hits; positive control passed). flash runs the EgoThink judge and the device comparison.
- **SS timing: DONE.** 32B TTFT for one single-shot VizWiz request: idle p50 0.41 s / p90 0.67 s; 12-device b7
  background p50 0.66 s / p90 2.59 s; 16-device b7 background saturates the engine (TTFT 9.9 to 43 s on the 24
  requests served in the run window). Robots in both backgrounds were MIXED ("lh-req ready" was not on origin).
- **StudySS2-32B: DONE and on origin** (numbers only). RefSpatial-Bench 277 of 277, mean point-in-mask accuracy 0.371;
  RealWorldQA 765 of 765, exact match 0.712; 0 errors; manifest order verified; prefix cache 0 hits. CODA-LM was not
  in the kit (licence).
- **Policy grid: NOT STARTED.** It needs "lh-req ready" on origin (robots are LH-REQ only; nothing runs on MIXED for
  the grid). hybrid-F and hybrid-F6 need "policy-F ready". Neither commit was on origin at 18:55.

## 1. StudySS1-32B (D142 item 3)

Kit at 8492e02 (`experiments/casestudy/ss1_*`, files unchanged), run through `experiments/casestudy/ss1_cloud_run.py`,
which only manages the server. Outputs `results/casestudy/study_ss1/vizwiz_val_cloud32b.json` (92430ba) and
`egothink_cloud32b.json` (743a8b1).

| dataset | n | scored | errors | score (kit scorer) | TTFT p50 | run order |
|---|---|---|---|---|---|---|
| VizWiz val | 4,319 | 4,319 | 0 | mean VQA accuracy 0.665 | 0.31 s | manifest order, verified 4,319 of 4,319 |
| EgoThink | 700 | 700 | 0 | mean containment 0.477 (judge by flash) | | manifest order, verified 700 of 700 |

**Condition:** H100 NVL, vLLM 0.31.0+cu129, the live2 round-1 32B server (Qwen3-VL-32B-Instruct @ 0cfaf481, served as
32BI) started fresh for the run, idle, one request at a time, greedy (temperature 0, seed 0); image processor overridden
by the round-1 `--mm-processor-kwargs` (min area 4,096 px; the released default, used by the Orin, is 65,536).

**Implementation fix (reported):** vLLM 0.31.0 rejects a `cache_salt` containing '/', and the kit passes the question id
as the salt; the first attempt failed every request (HTTP 400) and wrote nothing. The wrapper's shim replaces '/' with
'_' in the salt only (it never reaches the model).

**Cache verification:**
- Prefix cache: 6.70M prompt tokens queried, 0 hits, on one server instance used only by the run (no probe reached it).
  **Positive control PASSED** on a fresh start with the same command
  (`results/orchestration/live2/ss_timing/prefix_cache_positive_control.json`): a unique-salt repeat of the same
  request read 0 cached tokens (3 of 3), a same-salt repeat read 1,232 to 1,248 of 1,238 to 1,250. The control's own
  first reader coerced an absent field to 0 (a vacuous-pass defect); it was fixed before the control ran (a peer review
  by the A6000 session) and the near-miss is recorded in the control's file.
- Multimodal encoder cache: keyed by image CONTENT, not by salt. Byte-identical photos under different file names: 34
  groups in VizWiz (36 repeat questions), 15 in EgoThink (16). Hits: VizWiz 36 of 36 candidates, EgoThink 16 of 16, at
  exactly the predicted positions (a census, no eviction). Lists: `vizwiz_shared_images.json`,
  `egothink_shared_images.json` (TTFT-only artifacts; accuracy unaffected).
- **Resolution difference against the device:** 28 VizWiz images are below the released 65,536-px minimum area (the
  smallest 23x30); the device upscales them and the H100 server does not, so those questions saw different pixels
  (accuracy AND TTFT; `vizwiz_below_min_pixels.json`). EgoThink has none. Full image sizes:
  `ss1_image_dims.jsonl`.

## 1b. StudySS2-32B

Kit at 1b8790c (`experiments/casestudy/ss2_*`, files unchanged), run through `experiments/casestudy/ss2_cloud_run.py`
exactly as StudySS1-32B (fresh round-1 server, idle, one request at a time, greedy, unique cache_salt with the same '/'
shim, the kit's own `_provenance` with device h100nvl). Data from the public sources (BAAI/RefSpatial-Bench,
xai-org/RealworldQA), decoded with the builder's own loops without rewriting the manifests; all 1,042 images match the
manifests' hashes and every question, object and reference matches. CODA-LM is skipped by the kit (images need a
non-commercial agreement).

| dataset | n | scored | errors | score (kit scorer) | run order | commit |
|---|---|---|---|---|---|---|
| RefSpatial-Bench | 277 | 277 | 0 | mean point-in-mask 0.371 (location 0.513, placement 0.286, unseen 0.299); 9 answers with no parsed point | manifest order, verified | 6f7abc4 |
| RealWorldQA | 765 | 765 | 0 | exact match 0.712 (MCQ 0.715 of 438; free-form 0.709 of 327) | manifest order, verified | cb79d82 |

**Cache:** prefix cache 0 hits on both (86,082 and 1,001,747 queried tokens, per-dataset deltas). Multimodal cache:
RefSpatial asks several questions per image (277 questions on 91 distinct images); **186 hits against 186 predicted
repeats** once the candidates are keyed on DECODED PIXELS. Keyed on the parquet's source bytes the prediction was 180:
6 images differ in bytes but not in pixels, and the content-keyed cache treats them as one. RealWorldQA 3 of 3.
Candidate lists `results/casestudy/study_ss2/*_shared_images.json` (TTFT-only; accuracy unaffected).

## 2. SS timing (D142 item 4)

`experiments/orchestration/live2/ss_timing.py`, driver `experiments/orchestration/study_ss_timing_driver.sh`. The same
100 VizWiz val questions (seed 0 sample, excluding the 70 on shared images) through the kit's body, one at a time,
unique salt each. Background: the live2 harness, b7, dashcam : robot 50:50, push-all, seed 0, 600 s, tight 27 GiB;
robots **MIXED** (labelled; "lh-req ready" was not on origin). The injector starts after the background run is
deciding and sends one request every 5 s from about t = 60 s.

| condition | served | TTFT p50 | p90 | max | background run |
|---|---|---|---|---|---|
| idle | 100 of 100 | 0.41 s | 0.67 s | 0.79 s | none |
| 12 devices, b7, MIXED | 100 of 100 | 0.66 s | 2.59 s | 5.39 s | valid, dashcams all meet |
| 16 devices, b7, MIXED | 24 of 100 | 22.5 s | 37.1 s | 43.3 s | valid, **dashcams fail, robots 2 of 35** |

At 16 devices b7 push-all saturates the engine: the injected requests' TTFT climbs from 9.9 s (t = 83 s) to 43 s, so
the one-at-a-time injector fell behind its 5-s schedule, served 24 within the run, and the other 76 failed after the
background server stopped (75 refused, 1 cut mid-stream). The 16-device figure therefore describes a saturated
engine, sampled 24 times, not a 100-request distribution. For the SS deadline (2 s proposed): idle and 12-device p50
are within it; the 12-device p90 (2.59 s) is not.

## 3. Policy grid (overnight plan items 2 to 4)

- **Workload:** THREE-TYPE (40 : 40 : 20, SS deadline 2 s) if the user rules by 21:00, else TWO-TYPE (50 : 50, labelled
  "two-type (no SS ruling by 21:00)"). Tight 27 GiB, push-all, memory enforcement on, 600 s.
- **Memory enforcement:** new runner flag `--kv-capacity-enforced` (sets `CoordState.kv_capacity_enforced`, recorded
  in the run header). Step 2b proof: section 4.
- **Arms:** b7, eco-llm, mooncake; hybrid-F and hybrid-F6 when "policy-F ready" lands (proofs checked on origin first).
  Sizes 12 and 16, seeds 0 and 4; then seeds 5 and 6; then 10 and 20, seeds 0 and 4.
- **Gate:** robots LH-REQ only. As of 18:55 neither "lh-req ready" nor "policy-F ready" is on origin, so no grid cell has
  run and GPU 2 is idle by rule.

## 4. Memory enforcement, Step 2b

**Dry proof: UNEXERCISED, not passed** (`results/orchestration/live2/frozen_test/kv_enforcement_step2b.json`). Decision
logs with `--kv-capacity-enforced` off vs on, 600-s dry runs on MIXED traces (LH-REQ not ready), b7, eco-llm and
mooncake at 12 and 16 devices: **0 differing decisions in all six pairs, and peak GPU-resident history 0 tokens in
every run**. The dry harness never builds GPU-resident history, so enforcement cannot fire there; this is an
unexercised link (CLAUDE.md Rule 2), not evidence that enforcement does nothing.

**Live instrumentation added (output only):** the runner now writes `memory_pressure` into
`coordinator_result.json`: the enforcement flag, `gpu_kv_tokens`, CoordState's pressure record (epochs, epochs over
cap, peak tokens, over-cap intervals) and the totals of `enact_placement`'s per-call counts (offloaded, kept warm,
**evicted**, resident), which cstate computes and previously discarded. Every grid cell therefore reports whether
enforcement evicted anything. The harness tests pass, including "a split run decides exactly as an in-process run"
(13 tests). Note from live residency logs: under b7 every robot history is believed cold to the end of a run, so for
b7 enforcement may have nothing to evict; the per-cell eviction count will show it.

## 4b. Overnight rules (user, 2026-11-19) and decisions taken

Rules: run length from flash's committed table (shortest of 600 / 900 / 1200 s with >= 20 pooled robot questions in
all 8 cells, 12 and 16 devices, seeds 0, 4, 5, 6, 40:40:20, EVAL-only LH-REQ robots), same for every arm, committed
before the grid; DEV-fitted tables on EVAL-only questions; if "policy-F ready" is not on origin by 01:30, b7, eco-llm
and mooncake start the three-type grid and hybrid-F / hybrid-F6 join at the next run boundary after it lands; a
component that does not move decisions is an ABSENT LINK and the freeze proceeds (only base-with-switches-off != b7
stops F and F6); INVALID = rerun once then skip and log; server crash = one restart then next cell; push conflict =
rebase unpushed only.

Decisions (PROVISIONAL unless ruled):
1. 19:52, by the user's instruction ("run some baselines, pick up bumped work"): the D134 published-baseline queue
   resumed on MIXED while waiting (ruled; later confirmed as a standing rule).
2. The D134 driver's placement watcher would have paused on flash's `a0f4159` (credit-axis hardening and pressure
   instrumentation); marked handled because it needs no H100 wiring (placement path applied since e924005).
   PROVISIONAL.
3. The grid will not run a substitute workload under the THREE-TYPE label: if, when it is due, the harness cannot yet
   express LH-REQ EVAL robots or the RefSpatial + RealWorldQA EVAL single-shot pool, or the run-length table is not
   committed, the D134 queue keeps GPU 2 busy and this is recorded here. PROVISIONAL.
4. As of 20:20: "policy-F built (not frozen)" (a3e3dd0) is on origin, not "policy-F ready"; the trace generator
   accepts the 40:40:20 ratio but its single-shot pool is still StudySS1's (VizWiz, EgoThink) and has no LH-REQ robot
   selection; no run-length table yet.

## 4c. The three-type grid as run (updated 2026-11-20 01:30)

**Setup:** `experiments/orchestration/study_frozen_grid_driver_v3.sh`; 1200 s (flash's committed run-length table);
40:40:20 dashcam : LH-REQ EVAL robot : single-shot (RefSpatial + RealWorldQA, EVAL part of the committed 30/70 split);
SS deadline 2 s, one per 10 s per assistive device; tight 27 GiB; push-all; `--kv-capacity-enforced`; runner flags
`--robot-question-set lh_req --ss-question-set ss2` (both cross-checked against flash's committed counts: n=16 seed 0
gives 24 robot and 356 SS questions). Started 21:08 on "ss2-pool ready" (user ruling), so the 01:30 rule-3 fallback
was already satisfied. Scored with flash's three-type scorer (41b0eae); pre-fix three-type numbers are never compared.

**Valid runs so far (all questions; feasible-question column to follow):**

| arm | n | seed | dashcams all meet | robots on time | SS on time (2 s) | capacity | mm gate (hits = same-ID repeats; SS repeats) |
|---|---|---|---|---|---|---|---|
| b7 | 16 | 0 | yes | 17 of 24 | 319 of 356 | no | 405 = 405; 0 |
| mooncake | 16 | 0 | yes | 17 of 24 | 319 of 356 | no | 405 = 405; 0 |
| b7 | 16 | 4 | yes | 14 of 20 | 332 of 357 | no | 285 = 285; 0 |
| eco-llm | 16 | 4 | yes | 14 of 20 | 294 of 357 | no | 345 = 345; 0 |
| mooncake | 16 | 4 | yes | 14 of 20 | 332 of 357 | no | 285 = 285; 0 |
| b7 | 16 | 5 | yes | 19 of 25 | 320 of 356 | no | 735 = 735; 0 |

**Skipped (INVALID twice, rule 5; data kept):** eco-llm n16 s0 (one request of 33,839 tokens exceeds the 32,768
context, deterministically: one LH-REQ session at seed 0 whose history reaches 33,781 tokens at t = 958 s; absent at
seed 4); b7 n20 s0 (127 and 111 transport ReadErrors).

**PROVISIONAL decisions taken (all overnight):**
5. Multimodal-cache gate redefined: the planned "total hits 0" cannot hold, because D84 deliberately lets robot recall
   resend a session's history frames under the same per-(device, frame) UUID. Pass condition used: mm_cache_hits delta
   equals the run's repeated-UUID references, AND 0 repeats among single-shot references; wire presence of the uuid
   key counted per image part (asyncbackend). Every valid run so far passes exactly (agreed with the A6000 session).
6. Sizes 20 and 24 deferred to the end of the queue (driver v3, `DEFER_SIZES`), no cell dropped: at 20 devices the
   offered dashcam load is 14.67 req/s, 97 percent of the committed 32B peak (StudyD7b, 15.10 req/s); b7 n20 s0 failed
   twice with transport ReadErrors starting at t = 510 s, the StudyMOT1 / StudyD7 overload signature (server log
   silent; client dispatch lag p90 1.2 to 1.3 s against 28 ms at 16 devices). eco-llm n20 s0 was stopped 4 minutes in
   and set aside. Pending the user's size ruling (the A6000 recommends 16 and 18: 73 and 85 percent of peak).
7. The 1,042 StudySS2 images were staged in the live frame store as the kit's own JPEG q90 bytes (they were absent, so
   the first launch at 21:05 was refused at preflight for every cell: not measurements, set aside).
8. hybrid-F / hybrid-F6 join only after "policy-F ready" and a check that base-with-switches-off is byte-identical to
   b7; every F6 cell must show c6_calls > 0 and c6_scorer_error == 0 or it is INVALID as not-F6 (the A6000 found a
   swallowed MissingEvidence that silently disabled C6 before its fix).

**Mechanism notes:** memory enforcement never evicted anything in any run (peak GPU-resident history 0): b7 and
eco-llm hold no resident history, and mooncake's 377 keep-warm state actions (n16 s4) find nothing resident, so its
outcomes match b7 on both seeds. Unexercised, not evidence. Single-shot accuracy is device-side only: cloud-served
SS answers are recorded but not scored in live2 (the StudySS2 scorers are not importable there).

**Pending user rulings:** grid sizes (16 and 20, or 16 and 18); whether transport errors invalidate a run or count as
misses; whether an over-context request invalidates a run or counts as a miss.

## 5. Incidents

- 17:10 to 17:16: the first StudySS1-32B attempt failed every request (cache_salt '/'), stopped, no answers written.
- Host Python while the StudySS1 server was measuring idle TTFT: a py_compile and short edit or read scripts (seconds
  each), recorded here; no measured request overlapped a heavy process.

## 6. A6000 morning summary, policy-F side (2026-11-20 07:30)

Written by the A6000 session, which owns the policy-F freeze and the dry proofs. The MORNING SUMMARY section,
section 0 and sections 4c and 5 remain the H100's; nothing above this line was edited. Everything here is DRY (the
live2 trace generator with `--dry`, no engine), so every number is a decision-log count, never a served request. The
live grid is the H100's.

### 6.1 What ran

Committed in `8f8e36c` "policy-F ready (frozen)", pushed from a worktree at origin/main and verified ANCESTOR and
EQUAL before the worktree was removed. Controls before the push: the fleet suite 234 of 234 through its own runner,
`test_hybrid.py` 7 of 7 through pytest, and 0 em dashes in everything added.

Four proofs, all on a three-type LH-REQ cell unless stated. Full output in
`results/orchestration/live2/hybrid/policy_f_proofs.json`; the narrative is `reports/study_policy_f.md` section 11.

**Proof 1, ruling B is inert on robots.** `hybrid-F` is byte-identical to the screened `hybrid2-c1c2k15c3c5` on all
four two-type cells: 6,554 / 8,087 / 6,472 / 7,872 decisions, matching digests, `ss_seen` 0 in each.

**Proof 2, Step 2b per component.** Each switch toggled alone against the full arm. Two metrics are reported because
they are different registers and the first one misled me:

| component | decisions moved (setwise) | log positions differing | verdict |
|---|---|---|---|
| C1 | 0 | 0 | **ABSENT LINK**, cancelled by geometry |
| C2 | 712 | 12,071 | moves decisions |
| C3 | 459 | 6,026 | moves decisions |
| C5 | 461 | 11,986 | moves decisions |
| C6 | 3 | 11,794 | moves decisions |

`_differing` counts log POSITIONS and is kept only for the identity proofs, where byte-identity including order is
the claim. One early divergence desynchronises the rest of the log, so C6 read 11,794 positional against 3 actual, a
3,931x gap, and C2 17x. `_differing_setwise` counts a multiset over `(t, kind, opportunity_ids, representation,
defer_s)` and is the right register for "did this switch move a decision". The register error was caught by the
negative control, not by inspection.

C1's zero is **cancelled by geometry**, not unexercised: dashcam items carry one constant `value` and one constant
`work`, so `idx` is monotone in slack which is monotone in deadline, making C1's dashcam order identically EDF order;
and `_cap_dashcam_only` keeps every recall item unconditionally (`hybrid_arm.py:436-437`), so C1 reaches only the
`order` channel, which the harness discards. That is two of the five null categories at once and neither is evidence
about the policy.

**Proof 3, dry smoke, 30 of 30 cells ran** (5 arms x {16, 20, 32} x seeds {0, 4}, decision counts):

| n | seed | F | F6 | b7 | eco-llm | mooncake |
|---|---|---|---|---|---|---|
| 16 | 0 | 13,564 | 13,582 | 13,623 | 13,621 | 14,001 |
| 16 | 4 | 13,525 | 13,525 | 13,570 | 13,570 | 13,947 |
| 20 | 0 | 16,361 | 16,362 | 16,382 | 16,343 | 16,885 |
| 20 | 4 | 16,504 | 16,542 | 16,512 | 16,475 | 17,010 |
| 32 | 0 | 15,863 | 16,123 | 16,150 | 16,353 | 16,910 |
| 32 | 4 | 15,977 | 15,983 | 16,236 | 16,436 | 16,985 |

F differs from F6 at five of the six (n, seed) pairs and is identical at n=16 seed 4 only, so the F6 arm is live
everywhere else. Per PROVISIONAL decision 8 in section 4c, a live F6 cell must also show `c6_calls > 0` and
`c6_scorer_error == 0`.

**Proof 4, value-term negative control, 0 decisions moved on all eight cells.** Four patch variants (a flat table
with every value equal, dashcam 100x, robot 100x, single-shot 1,000x) against both frozen arms. Setwise 0 everywhere;
the only non-zero positional cell, robot_100x at 2 of 16,361, is two `release_recall` rows swapping places at
t = 527.0 with both items released either way.

### 6.2 The three findings

**1. The value term is decision-inert in both frozen arms.** A flat table and a 10,000x inversion move nothing. So
D143 ruling A's LH-REQ swap, the 4.4x half-one correction and the SS ordering flip (refspatial 0.18742 over robot
0.13204) all change a quantity the frozen policy does not read. **The SS ordering must not be read as evidence about
single-shot work versus robot recall**; it is a quantity with no reader.

**2. C6 was dead in every `-lhreq` cell and I caused it.** `_LhReqFittedProfiles._DEV_KEY` mapped 4 of the 5
`(representation, tier)` conditions the escalation path reads, raising `MissingEvidence` on `cloud RICH` (4 of 12
question types map to RICH) and on `device N1`. `_c6_prepare`'s bare `except Exception` counted that into
`c6_scorer_error` and returned False, so `c6_live` was False on every period while `live2_describe` still reported
`c6=True`. Measured before the fix: `c6_scorer_error` 251 of 251 periods with recall, `c6_calls` 0, F6 byte-identical
to F at all six smoke cells. After re-raising `MissingEvidence` and declaring the two substitutions: `c6_calls` 254,
`c6_dev_send_to_hold` 6, `c6_scorer_error` 0. A swallowed exception counted into a counter is the same shape as the
write-only field: every surface sign said the arm was configured.

**3. C6 spends 94 percent of its work on requests D143 ruling C says it cannot act on, and breaches the decision
period at every size.** Call split by request type:

| n | SS-only periods | calls on SS | mixed or robot periods | calls on robot | deviations |
|---|---|---|---|---|---|
| 16 | 356 | 356 | 24 | 24 | 1 on robot |
| 20 | 476 | 478 | 28 | 28 | **1 on single-shot** (`c6_dev_send_to_hold`) |

Per-period `decide()` wall time against the 100 ms decision period:

| arm | n | all p50 | all p99 | SS-only p50 / p99 | robot p50 / p99 |
|---|---|---|---|---|---|
| F | 16 | 0.029 | 0.046 | 0.039 / 0.057 | 0.039 / 0.079 |
| F6 | 16 | 0.030 | 63.848 | 42.638 / 211.968 | 74.957 / 285.178 |
| F | 20 | 0.033 | 0.048 | 0.043 / 0.080 | 0.043 / 0.054 |
| F6 | 20 | 0.034 | 124.524 | 81.747 / 268.761 | 117.976 / 873.407 |
| F | 32 | 0.044 | 0.069 | 0.054 / 0.158 | 0.054 / 0.184 |
| F6 | 32 | 0.045 | 249.680 | 133.494 / 345.450 | 146.144 / 403.470 |

So the breach recorded at 32 devices exists at **every** size including the n=16 entry point, 2x to 9x over the
period at p99. Gating C6 to non-SS recall would cut roughly 42 s of C6 time per 1200 s cell to 3.3 s, a 92 percent
cut, but **it would delete the one SS decision at n=20**, so the speed fix is NOT decision-preserving under D108 and
D121 and I have not applied it. D143 ruling C's "C6 is robot-only by design" is false as implemented.

### 6.3 The over-context question, and why a per-arm skip is unsafe

LH-REQ session `1848337166005249` reaches 33,781 history tokens, which with the prompt is the H100's 33,839 against
the 32,768 context. Checked with the committed trace generator at all four development seeds:

| seed | max session tokens | worst question history | questions over 32,768 |
|---|---|---|---|
| 0 | 44,581 | 33,781 | 1, at n=16, 18 and 20 alike |
| 4 | 27,031 | 24,331 | 0 |
| 5 | 27,031 | 24,331 | 0 |
| 6 | 27,031 | 24,331 | 0 |

It is a seed-0 phenomenon only, the same session at every size, and seeds 4, 5 and 6 have 8,437 tokens of headroom
at their worst question. The p90 session history is about 1,800 tokens, so this is one session at 19x the p90.

**The selection effect.** The arms that hit the request (F, F6, eco-llm) are the ones that chose to send full
history; b7 and mooncake survive seed 0 because they did not. Skipping the cell per arm leaves a seed-0 panel
containing only the arms whose representation choice avoided the overflow, which is the thing the study measures.
Recommended instead: **common support**, seeds 4, 5 and 6 for every arm in the headline, with the seed-0 b7 and
mooncake cells kept as recorded and marked excluded-from-headline rather than deleted. Cost, which is the argument
for ruling the question a per-question miss instead: pooled robot questions at n=16 are 24 / 20 / 25 / 20 across
seeds 0, 4, 5, 6, so common support gives **65 against 89**, a 27 percent loss of the robot denominator on a study
already at the D82 minimum of 20 per cell.

### 6.4 Grid size, offered load against the committed peak

Offered dashcam load is a step function of the dashcam device count, against the committed 32B one-frame closed-loop
peak of 15.10 req/s (StudyD7b):

| n | dashcam devices | offered req/s | percent of peak |
|---|---|---|---|
| 14, 16 | 6 | 11.01 | 73 |
| 17, 18 | 7 | 12.83 | 85 |
| 19, 20 | 8 | 14.67 | 97 |
| 32 | 13 | 23.83 | 158 |

The ReadErrors at 20 devices match the StudyMOT1 and StudyD7 overload signature exactly (no HTTP status, no server
log line, client dispatch lag p90 1.2 to 1.3 s against 28 ms at 16 devices). StudyMOT1's own amended rule selected
66 percent of peak. The A6000 recommends **16 and 18**, and 18 holds the same pooled robot counts as 16
(24 / 20 / 25 / 20), so the second size costs no denominator.

### 6.5 PROVISIONAL decisions taken on this side (overnight rule)

1. **Two substitutions in the LH-REQ DEV fit**, because the escalation path reads five `(representation, tier)`
   conditions and the LH-REQ DEV split measures three. `("RICH", "cloud") -> cloud_D2` (D2 is the fullest measured
   cloud condition and RICH is at least as informative, so this credits the cloud with less) and
   `("N1", "device") -> device_4B_RECENT` (N1 is the device without history coverage, so its true accuracy is at most
   the covered device's, and using the covered number credits the device with more). Both understate the cross-tier
   gain, so neither can manufacture an escalation advantage. Declared in `_SUBSTITUTED` and asserted by
   `test_lh_req_dev_fit_covers_every_condition_the_policy_reads`.
2. **C1's value term left as the two-type constant** rather than moved to the DEV fit (0.13204 against 0.142857).
   Inert either way per proof 4, so this is a hygiene question, not a results question.
3. **The SS 30/70 split is stratified** by question source.
4. **SS on-time is deliberately NOT a third capacity conjunct**, because D64 defines capacity as dashcam-all-meet AND
   robot-pool-meets. Folding it in would be a post-freeze definition change under D79.
5. **Two metrics shipped for decision diffs**, positional for identity claims and setwise for move claims, rather
   than replacing the first. Both appear in every proof row so a reader cannot pick up the wrong register silently.

### 6.6 Open user rulings, in the order work is blocked on them

1. **The over-context counting rule** for session `1848337166005249`: miss, or run-invalidating. Now blocking the
   headline's seed panel and worth 27 percent of the robot denominator.
2. **C6: byte-identity or the speed fix.** The two cannot both hold. Keeping byte-identity keeps a 2x to 9x breach
   of the decision period at every size; taking the fix deletes one SS decision and requires a relabel under D79;
   making C6 robot-only is what D143 ruling C already states and is the A6000's recommendation.
3. **Grid size**, 16 and 20 as ruled, against 16 and 18.
4. **Whether an inert value term is acceptable in a frozen policy**, given that three separate corrections to it
   changed no decision.

## 12. Offline analysis of the overnight grid (A6000, 2026-11-20, user request)

CPU only, no new runs. Every number comes from the committed run directories under
`results/orchestration/live2/frozen_test/runs`; the script is
`experiments/orchestration/live2/offline_grid_analysis.py` and its output is
`results/orchestration/live2/frozen_test/offline_grid_analysis.json`.

REGISTERS, because the five answers mix them. MEASURED means read from a run's own logs. MODELLED
means computed with the committed cost curve (`costs.recall_ttft_s` at COLD) on measured inputs.
CONSTRUCTED means a counterfactual bound: what a different policy could have had, never what
happened. Each table says which it is.

One scope note. The seed-6 cells of hybrid-F and hybrid-F6 landed while this analysis was being
written, and both ARE included: every arm's pooled row now covers seeds 4, 5 and 6 at 16 devices,
65 robot questions each, so the per-arm columns are like for like on the seed set. They are not
like for like on what happened to the questions: b7 and mooncake reject far more robot questions
than the hybrids, so their "missed" rows are dominated by questions that never reached the cloud at
all, which is a different event from a question that was sent and was late. Section 12.3 numbers
are at seeds 4 and 5 only, because that is the pairing that existed when they were computed. And b7 and mooncake reject
far more robot questions than the hybrids, so their "missed" rows are dominated by questions that
never reached the cloud at all, which is a different event from a question that was sent and was
late.

### 12.1 Robot miss decomposition (item 1), 16 devices, seeds 4 to 6, seconds, p50

| arm | outcome | n | never sent | wait before release | engine queue (residual) | prefill (modelled) | after first token | arrival to first token |
|---|---|---|---|---|---|---|---|---|
| b7-edf-feasibility | on time | 47 | 0 | 0.1222 | 0.6166 | 2.1211 | 0.0222 | 3.0249 |
| b7-edf-feasibility | missed | 18 | 14 | 0.1027 | 2.1847 | 3.9287 | 0.0222 | 6.1382 |
| eco-llm | on time | 46 | 0 | 0.1169 | 0.7103 | 2.1211 | 0.0222 | 2.9238 |
| eco-llm | missed | 19 | 1 | 0.1218 | 1.0691 | 5.3568 | 0.0222 | 6.6661 |
| hybrid-F-lhreq | on time | 50 | 0 | 0.0984 | 0.5662 | 2.1211 | 0.0222 | 2.9429 |
| hybrid-F-lhreq | missed | 15 | 1 | 0.1073 | 0.5675 | 5.3621 | 0.0222 | 6.0820 |
| hybrid-F6-lhreq | on time | 49 | 0 | 0.2840 | 0.4798 | 2.1211 | 0.0222 | 3.2306 |
| hybrid-F6-lhreq | missed | 16 | 1 | 0.4620 | 0.6380 | 5.3621 | 0.0222 | 6.5444 |
| mooncake | on time | 47 | 0 | 0.1097 | 0.7655 | 2.1211 | 0.0222 | 3.1148 |
| mooncake | missed | 18 | 14 | 0.1131 | 2.1408 | 3.9287 | 0.0222 | 6.1632 |

How the split is formed. Waiting before release is `t_submit - t_opportunity`, MEASURED. Prefill is
MODELLED: the committed COLD curve on the measured uncached prompt, and the uncached prompt is the
whole prompt in every robot request in every cell (see 12.2). The engine queue is the RESIDUAL,
`(t_first_token - t_submit) - prefill`, clamped at zero, so it carries the model's error; the JSON
records how often the model exceeded the measured TTFT per cell. "After first token" is
`t_delivered - t_first_token`, MEASURED, and is a constant by construction (12.3).

The shape: waiting before release is 0.10 to 0.52 s and never the binding term. Prefill of the
history is, at 2.12 s on the questions that met the deadline and 3.93 to 6.42 s on those that
missed. The 5 s robot deadline is spent on rebuilding the history, not on scheduling it.

### 12.2 Is "peak GPU-resident history 0" an observation (item 2)

Three independent instruments, 16 devices, seeds 4 to 6:

| cell | robot requests | with cached_tokens > 0 | residency rows | believed tiers | prefix_cache_hits | prefix_cache_queries | mm_cache_hits | telemetry_cached_tokens non-null |
|---|---|---|---|---|---|---|---|---|
| b7 s4 | 15 | 0 | 372 | all cold | 0 | 5,458,622 | 285 | 0 |
| b7 s5 | 21 | 0 | 370 | all cold | 0 | 5,548,713 | 735 | 0 |
| b7 s6 | 15 | 0 | 372 | all cold | 0 | 5,494,250 | 180 | 0 |
| eco-llm s4 / s5 / s6 | 20 / 24 / 20 | 0 | 372 / 370 / 372 | all cold | 0 | 5,579,984 / 5,622,934 / 5,593,834 | 345 / 1,065 / 405 | 0 |
| hybrid-F s4 / s5 / s6 | 20 / 24 / 20 | 0 | 372 / 370 / 372 | all cold | 0 | 5,301,776 / 5,317,513 / 5,324,320 | 345 / 1,065 / 405 | 0 |
| hybrid-F6 s4 / s5 / s6 | 20 / 24 / 20 | 0 | 372 / 370 / 372 | all cold | 0 | 5,236,808 / 5,261,188 / 5,227,930 | 345 / 1,065 / 405 | 0 |
| mooncake s4 / s5 / s6 | 15 / 21 / 15 | 0 | 372 / 370 / 372 | all cold | 0 | 5,479,025 / 5,556,227 / 5,486,424 | 285 / 735 / 180 | 0 |

It is a REAL OBSERVATION, not an instrument that never reads, and it is corroborated twice over
from outside the policy's own belief: the engine reports 0 prefix-cache hits against 5.2 to 5.6
million queries in every cell, and every robot request carries `cached_tokens` 0, which is the
engine's own per-request number rather than the coordinator's model.

The read sites, per the Step 2 rule (a quantity written and never read is ABSENT):

- `coordinator.py:575`, `cost = C.recall_gpu_s(tokens, s.residency_readiness())`. A real read: the
  residency sets the GPU seconds the request is charged.
- `cstate.py:525-526`, which builds `obs.cloud.gpu_warm_sessions` and `host_warm_sessions`, the
  lists an arm reads to learn what is warm.
- `coordinator.py:481`, `if s.built_tokens < s.est_tokens and s.believed_tier() != "gpu"`, in the
  build path.

ONE READ IS DEAD, and it is the one that would close the loop. `residency.jsonl` carries
`telemetry_cached_tokens`, written at `coordinator.py:901`, and it is NULL in every row of every
cell: 372 of 372, in all 13 cells. So the engine's own `cached_tokens` never reaches the belief,
and the belief is never contradicted by the thing it models. In these runs the belief happens to
be right, which is exactly the condition under which a dead validation read goes unnoticed.

Why the zero is unsurprising rather than suspicious: D84 gives every device its own cache salt, so
no prompt prefix is shared BETWEEN devices by design, and 12.4 shows the median robot history is
asked exactly one question, so there is almost no reuse available WITHIN a device either. The
warm-state axis is close to unexercised in this workload, which is a statement about the workload,
not about the policies.

### 12.3 What the committed delivery stamp is worth (definition audit, consistency check 4)

The runs were launched with `forward_at = "first"` (recorded in every `run_meta.json`), so an
answer is stamped delivered at its FIRST TOKEN plus a constant wire delay. That delay is exactly
0.022176 s in 13,558 of 13,558 answers of b7 n16 s4, which is why the "after first token" column
in 12.1 is a constant rather than a distribution. The generation that follows is real and is
charged to no deadline: `t_done - t_first_token` has p50 0.058 s and max 2.715 s in the same cell.

How many questions would change verdict if delivery were stamped at COMPLETION instead (MEASURED,
same files, same deadlines of 5 s robot and 2 s single-shot; a refused request counts as a miss
under D144):

| cell | type | n | on time (committed stamp) | on time (at completion) | flip |
|---|---|---|---|---|---|
| b7 n16 s4 | robot | 15 | 14 | 11 | 3 |
| b7 n16 s4 | single-shot | 356 | 332 | 329 | 3 |
| b7 n16 s5 | robot | 21 | 19 | 11 | 8 |
| b7 n16 s5 | single-shot | 356 | 320 | 309 | 11 |
| eco-llm n16 s4 | robot | 20 | 14 | 10 | 4 |
| eco-llm n16 s4 | single-shot | 356 | 294 | 288 | 6 |
| eco-llm n16 s5 | robot | 24 | 19 | 10 | 9 |
| eco-llm n16 s5 | single-shot | 356 | 304 | 293 | 11 |
| hybrid-F n16 s4 | robot | 20 | 15 | 15 | 0 |
| hybrid-F n16 s4 | single-shot | 356 | 339 | 339 | 0 |
| hybrid-F n16 s5 | robot | 24 | 21 | 20 | 1 |
| hybrid-F n16 s5 | single-shot | 356 | 343 | 343 | 0 |
| hybrid-F6 n16 s4 | robot | 20 | 14 | 13 | 1 |
| hybrid-F6 n16 s4 | single-shot | 355 | 334 | 334 | 0 |
| hybrid-F6 n16 s5 | robot | 24 | 21 | 19 | 2 |
| hybrid-F6 n16 s5 | single-shot | 356 | 342 | 342 | 0 |
| mooncake n16 s4 | robot | 15 | 14 | 11 | 3 |
| mooncake n16 s4 | single-shot | 356 | 332 | 326 | 6 |
| mooncake n16 s5 | robot | 21 | 19 | 11 | 8 |
| mooncake n16 s5 | single-shot | 356 | 319 | 310 | 9 |

This is a DEFINITION, not a defect: for an MCQ letter the first token IS the answer, and the
runner exposes the alternative as a flag. But the definition is load-bearing and it is not neutral
between arms. At seed 5 the committed stamp puts the robot column at hybrid-F 21, hybrid-F6 21,
b7 19, eco-llm 19, mooncake 19, a spread of 2; stamping at completion puts it at hybrid-F 20,
hybrid-F6 19, b7 11, eco-llm 10, mooncake 11, a spread of 9 or 10. The arms that throttle hold the
engine at a load where generation stays fast, and the committed stamp does not count that. Nothing
here says which stamp is right; it says the choice decides the size of the effect, and the arms
whose decode is slow are the baselines, so the current convention UNDERSTATES the policy arms.
RefSpatial is the case where the first token is certainly not the answer, since its answer is a
coordinate pair.

### 12.4 Reuse per robot history (item 3), 16 devices, seeds 4 to 6

| arm | robot sessions with questions | questions per history p50 / max | gaps measured | constructed warm-prefix token fraction p50 | constructed fraction with any warm prefix |
|---|---|---|---|---|---|
| b7-edf-feasibility | 51 | 1 / 3 | 14 | 0.9778 | 0.9608 |
| eco-llm | 51 | 1 / 3 | 14 | 0.9867 | 0.9688 |
| hybrid-F-lhreq | 51 | 1 / 3 | 14 | 0.9867 | 0.9688 |
| hybrid-F6-lhreq | 51 | 1 / 3 | 14 | 0.9867 | 0.9688 |
| mooncake | 51 | 1 / 3 | 14 | 0.9778 | 0.9608 |

MEASURED: the median robot history is asked ONE question, and only 11 to 14 same-history gaps
exist across 34 to 51 sessions, so there is almost no question-to-question reuse to capture.

CONSTRUCTED, and this is the interesting half: if every 30 s upload batch had been prefilled on
arrival, 97.8 to 98.7 percent of a question's history tokens would already have been in the cache
at question time, and 96.1 to 97.7 percent of questions would have had some warm prefix. The
reuse available in this workload is not ACROSS questions, it is WITHIN one history's own growth,
and nothing in the current setup prefills a batch before a question asks for it. The frame cadence
used per session is its own measured one (`t_opportunity / frames_on_the_wire`), and the batch size
is the 30 s the question names.

### 12.5 Warming budget (item 4)

Prefilling each 30 s batch of every robot history, charged with the committed COLD curve on the
batch's NEW tokens only (MODELLED), against the 62,944-token GPU pool and the 27 GiB host tier
(110,592 tokens at the committed 262,144 bytes per token):

| cell | robot devices | sessions | warming GPU-s | share of the 1200 s run | peak resident tokens | x GPU pool | x host tier | x GPU plus host | GiB |
|---|---|---|---|---|---|---|---|---|---|
| n16 s4 | 7 | 13 | 38.1 | 3.2 % | 119,075 | 1.89 | 1.08 | 0.69 | 29.07 |
| n16 s5 | 7 | 15 | 49.5 | 4.1 % | 166,659 | 2.65 | 1.51 | 0.96 | 40.69 |
| n16 s6 | 7 | 13 | 35.7 | 3.0 % | 139,581 | 2.22 | 1.26 | 0.80 | 34.08 |
| n18 PROJECTED | 8 | n/a | 43.5 | 3.6 % | 159,521 | 2.53 | 1.44 | 0.92 | 38.95 |

The 18-device row is a PROJECTION by robot-device count from the 16-device median, not a
measurement: no 18-device cell exists yet.

The GPU time is affordable and the memory is not. Warming costs 3 to 4 percent of the run's GPU
budget, while holding every robot history needs 1.9x to 2.7x the GPU pool and 1.1x to 1.5x the
host tier on its own; at seed 5 it is 96 percent of the GPU and host tiers combined, and the
projection at 18 devices is 92 percent. So a warming policy in this setting is a PLACEMENT and
EVICTION problem, not a compute problem, and the peak above is an upper bound that keeps every
history of every session that asked a question and ignores the sessions that never asked.

### 12.6 Cross-type value per GPU-second (item 5)

Committed tables, with the GPU-seconds MODELLED by the COLD curve on the measured median prompt of
that type in these cells:

| axis | gain | median prompt tokens | modelled GPU-s | gain per GPU-s |
|---|---|---|---|---|
| dashcam (C1 value) | 0.09000 | 378 | 0.0840 | 1.0714 |
| SS refspatial | 0.18742 | 1,372 | 0.3049 | 0.6147 |
| SS realworldqa | 0.08297 | 1,372 | 0.3049 | 0.2721 |
| robot LH-REQ EVAL | 0.28986 | 9,623 | 2.1384 | 0.1355 |
| robot LH-REQ DEV | 0.14286 | 9,623 | 2.1384 | 0.0668 |

A shedding rule that maximised gain per GPU-second would shed ROBOT RECALL FIRST, by a factor of 8
against dashcam frames and 4.5 against RefSpatial, because the robot gain is the largest per
QUESTION and the smallest per GPU-SECOND: it buys 0.29 of accuracy for 2.14 GPU-s while a dashcam
frame buys 0.09 for 0.084 GPU-s. That is the arithmetic a value-based shedding rule would act on,
and it points away from the mechanism this study exists to test.

THE UNITS DO NOT MATCH, and the ranking is therefore a CONVENTION, not a measurement. The robot
gain is an MCQ-accuracy difference, dashcam is a challenge-mAP value, RefSpatial is a point-in-mask
fraction and RealWorldQA is exact match. `ss_quality.json _metric_incomparability` already records
this for C1's ordering, and it binds here for the same reason: a column that adds them is a
convention about what we are willing to trade, not evidence about what is worth more.

### 12.7 Why hybrid-F sends the 33,839-token history that b7 declines (report only)

Every arm's decision for the same opportunity (opp0010837, robo002, session 1848337166005249,
arriving at t 957.90 with 33,781 tokens of history), MEASURED at 16 devices seed 0:

| arm | sent to cloud | representation | tokens charged | image parts on the wire | HTTP | letter | on_time as recorded |
|---|---|---|---|---|---|---|---|
| b7-edf-feasibility | no | n/a | n/a | n/a | n/a | n/a | n/a |
| mooncake | no | n/a | n/a | n/a | n/a | n/a | n/a |
| eco-llm | yes | RECENT | 467 | 375 | 400 | X | true |
| hybrid-F-lhreq | yes | RECENT | 467 | 375 | 400 | X | true |
| hybrid-F6-lhreq | yes | RECENT | 467 | 375 | 400 | X | true |

Corroborated on the dry path, same cell, where the decision counts are: b7 CLOUD 375, DEFER 2,
REJECT 5; mooncake CLOUD 375, REJECT 4, DEVICE 1; hybrid-F CLOUD 375 plus 5 CLOUD-at-RECENT;
eco-llm CLOUD-at-D2 375 plus 5 CLOUD-at-RECENT. The five rescued questions are the same five.

The chain, with the read sites:

1. b7 and mooncake REJECT it. The feasibility test predicts a COLD prefill of the whole 33,781
   tokens against a 5 s deadline, which fails `est <= slack + defer_s`
   (`baselines/constructed.py:184-191`), so the question is answered on the device and never
   reaches the cloud.
2. hybrid-F's C3 converts exactly that rejection into a send. `hybrid_arm.py:315-318`: when the
   question is not CLOUD and is not single-shot, C3 re-tests it at the 467-token recent window,
   which the same curve says is feasible, and emits CLOUD at representation RECENT. eco-llm
   rescues the same five questions the same way.
3. THE PROMISE REACHES THE ACCOUNTING AND NOT THE PAYLOAD. `coordinator.py:574` charges
   `tokens_for_representation`, which is 467 for RECENT, while `coordinator.py:593-597` builds the
   request body from `s.frames`, the whole session: 375 image parts went on the wire and the server
   refused the request with HTTP 400 at 33,839 tokens. C3's RECENT is expressible in the cost and
   UNEXPRESSIBLE in the request, which is the same shape as the write-only field with one read
   added.
4. The refusal was then recorded as an on-time cloud answer with the placeholder letter X, because
   `coordinator.py:781` computes `ontime = delivered <= o.deadline_abs()` from the completion time
   alone, with no reference to the status or to whether an answer was parsed. D144 ruling 3 makes
   it a miss; the H100 has applied that rule and republished the headline.

No code was changed for this subsection. The defect it names is in the harness, not in any arm:
the policy asked for a cheap representation, was charged for a cheap representation, and sent an
expensive one.

## 13. Dry pre-screen of every live2 arm (A6000, 2026-11-20, user request)

One dry cell per registered arm: 40:40:20 dashcam : LH-REQ EVAL robot : SS2 EVAL single-shot,
1200 s, seed 4, 16 devices, stub bridge, no engine. SCREENING ONLY, never a result for any arm.
Script `experiments/orchestration/live2/baseline_prescreen.py`, output
`results/orchestration/live2/frozen_test/baseline_prescreen.json`, distinct-arm list written to
`results/orchestration/live2/frozen_test/runs/PRESCREEN_DISTINCT_ARMS`.

**118 registered arms, 0 errors, 60 distinct decision logs, 18 groups of two or more, 24 arms
channel-silent.**

### 13.1 What "identical" means here, and what it does not

Arms are grouped by the digest of the decision log, positionally, so a group means byte-identity
including order. The register matters more than the number: this is an OBSERVED coincidence at ONE
cell, not a constructed proof that two arms are the same policy. A cell that never reaches an arm's
branch cannot distinguish it from an arm that has no such branch.

The sharpest instance is our own: **hybrid-F, hybrid-F6, hybrid-F6r and their four `-lhreq` and
four `-c6` twins are all byte-identical at this cell**, twelve names in one group. They are not the
same arm. C6 moves 3 decisions at 20 devices seed 0, F differs from F6 at five of the six smoke
cells, and the robot-only gate moves 2 robot and 82 dashcam decisions at 16 devices seed 0. Seed 4
at 16 devices is simply the one cell where C6 changes nothing. Any reader who takes the grouping as
a dedup list deletes the comparison the study exists to make, which is why the control file carries
that warning above the names.

### 13.2 The groups of two or more

| arms | members |
|---|---|
| 12 | b7-edf-feasibility, builder-default, builder-s1-fairshare, builder-s1-feasible, builder-s1-lateness, builder-s2-value, builder-s4-adaptive, builder-s4-llf, builder-s6-decline, **clockwork**, **ekya**, hybrid-base |
| 12 | hybrid-F, hybrid-F-c6, hybrid-F-lhreq, hybrid-F-lhreq-c6, hybrid-F6, hybrid-F6-c6, hybrid-F6-lhreq, hybrid-F6-lhreq-c6, hybrid-F6r, hybrid-F6r-c6, hybrid-F6r-lhreq, hybrid-F6r-lhreq-c6 |
| 6 | hybrid2-all-k05, hybrid2-all-k05-c6, hybrid2-c1c2k05c3c5, hybrid2-c1c2k05c3c5-c3always, hybrid2-c1c2k05c3c5-c3always-c6, hybrid2-c1c2k05c3c5-c6 |
| 5 | always-cloud-fcfs, **inar-vl**, **routellm**, **videostorm**, **vllm-priority** |
| 4 | hybrid2-all-k15, hybrid2-all-k15-c6, hybrid2-c1c2k15c3c5, hybrid2-c1c2k15c3c5-c6 |
| 4 | hybrid-c1c2k05, hybrid-c1c2k1, hybrid-c1c2k15, hybrid-c1c2k2 |
| 4 | hybrid-c1c2k1c3, hybrid-c1c2k1c3-c6, hybrid-c1c2k2c3, hybrid-c1c2k2c3-c6 |
| 4 | hybrid-base-c6, hybrid-c1-c6, hybrid2-c1c5-c6, hybrid2-c5-c6 |
| 4 | hybrid-c1c2k05-c6, hybrid-c1c2k1-c6, hybrid-c1c2k15-c6, hybrid-c1c2k2-c6 |
| 3 | **kvflow**, **pensieve**, **rh8-demand-aware-oracle** |
| 3 | hybrid-c1, hybrid2-c1c5, hybrid2-c5 |
| 3 | hybrid2-c1c2k05, hybrid2-c1c2k05c5, hybrid2-c1c2k05c5-reserve |
| 2 each | builder-acfcfs + builder-s2-all; hybrid-all-k1 + its -c6; hybrid-all-k2 + its -c6; confidence-cascade + **streamscout**; hybrid2-c1c2k05c5-c6 + hybrid2-c1c2k05c5-reserve-c6; hybrid2-c1c2k15c3c5-c3always + its -c6 |

Published arms are in bold. Three readings worth stating plainly, each about THIS cell:

1. **Eleven arms decide exactly as b7 does**, including two published systems, clockwork and ekya,
   and nine of our own builder and hybrid-base variants. For the published pair this is the
   port-side question in CLAUDE.md: the port is legal and fairly treated and decides nothing b7
   does not.
2. **Four published arms decide exactly as always-cloud-fcfs**, and that group is channel-silent,
   so those four sent everything to the cloud and used no other channel.
3. **The k_r ladder is inert at this cell**: k_r 0.05, 0.1, 0.15 and 0.2 give one log in the
   `hybrid-c1c2k*` family, and the same collapse appears in the c3 and -c6 ladders. The screening
   that chose k_r cannot have been decided by this cell.

### 13.3 Channel-silent arms (24 of 118)

An arm is channel-silent here when it emitted the two unavoidable release kinds and used no other
decision channel: no non-default representation, no deferral, no decline, no piece split, no tier
request. This is the port-side rule's question, asked of every arm at once.

always-cloud-fcfs, builder-acfcfs, builder-s2-all, hybrid-base-c6, hybrid-c1-c6, hybrid-c1c2k05-c6,
hybrid-c1c2k1-c6, hybrid-c1c2k15-c6, hybrid-c1c2k2-c6, hybrid-llm, hybrid2-c1c2k05-c6,
hybrid2-c1c2k05c5-c6, hybrid2-c1c2k05c5-reserve-c6, hybrid2-c1c2k15-c6, hybrid2-c1c2k15c5-c6,
hybrid2-c1c2k15c5-reserve-c6, hybrid2-c1c5-c6, hybrid2-c5-c6, inar-vl, routellm,
thinking-qwenvl-atdm, uniscale, videostorm, vllm-priority.

Six of the 24 are published arms (inar-vl, routellm, thinking-qwenvl-atdm, uniscale, videostorm,
vllm-priority). The rest are our own `-c6` variants, which is itself informative: a `-c6` variant
that is channel-silent while its base arm is not has had its base arm's channel removed rather than
extended, and that is worth a look before any of them is cited.

Three more arms are nearly silent in a different way: device-only, hybrid-llm and perllm emit 377
decisions against 13,570 for b7, so they release no dashcam frames to the cloud at all at this cell.

### 13.4 Characteristic decision, where it is declared

A single channel read for every arm is exactly the failure CLAUDE.md records, so the characteristic
is declared per arm from that arm's own description, and the other 112 arms are reported as
UNDECLARED with their full census rather than as zeros. An undeclared characteristic is not a zero.

| arm | characteristic decision | count at this cell |
|---|---|---|
| b7-edf-feasibility | feasibility actions (decline plus defer) | 5 |
| eco-llm | non-default representation per request | 377 |
| mooncake | state action (keep-warm retention) | 377 |
| hybrid-F-lhreq | non-default representation (C3's RECENT) | 5 |
| hybrid-F6-lhreq | non-default representation (C3's RECENT) | 5 |
| hybrid-F6r-lhreq | non-default representation (C3's RECENT) | 5 |

Every one is non-zero, so no arm in the live comparison fails the port-side rule. The hybrid count
is a FLOOR, not a census: C1 acts through `order`, C2 through the dashcam throttle and C5 through
the cap, and `decision.jsonl` carries none of those three channels, which is the same
unexpressibility that section 11.4 of `study_policy_f.md` records for C1.

## 14. Four-seed headline at 16 devices, and the second-cell exclusion check (A6000, 2026-11-20)

D144 items 1 and 2. Computed on this box from the committed run directories on origin, with no live
run touched. Script: `experiments/orchestration/live2/frozen_headline.py`, which is the H100's
seed-0/4/5 script extended rather than forked, so the two agree by construction where they overlap.
Output `results/orchestration/live2/frozen_test/frozen_headline_n16_4seed.json`.

What changed in the script: a local trace fallback, because this box does not hold the H100's trace
tree; a robot-on-time column over ALL questions beside the feasible one; and a per-run D133 verdict
with its margin in questions and a fragile flag.

CONTROLS before any number below is read.
- The regenerated traces reproduce the H100's robot opportunity ids EXACTLY at every seed, and the
  script refuses a run whose trace and outcomes disagree on the robot question set rather than
  scoring it on a guess.
- The feasible counts from the local traces, 18 / 15 / 22 at seeds 0 / 4 / 5, equal the committed
  `frozen_feasible.json` counts to the question.
- Restricted to seeds 0, 4 and 5 this script reproduces the H100's committed three-seed headline.

THE RUNS ARE PRE-FIX, and this is the limit on everything in 14.1 to 14.3. The RECENT defect
described in 12.7 was present in every eco-llm, hybrid-F and hybrid-F6 run scored here: 3 to 7
RECENT releases per run were charged 467 tokens and sent the whole session. The H100 has staged the
fix (a RECENT release will send the session's most recent k frames, k = ceil(frames x charged /
history tokens), every other representation byte-identical), and the completed runs cannot be
rescored for it; redoing them is the user's call. So these numbers describe the arms as they ran,
not the arms as they are now specified.

### 14.1 Pooled four-seed rates, paired by seed (B = 10,000)

On time = delivered within the deadline (robot 5 s, single-shot 2 s) by a request that returned
HTTP 200, per D144. The bootstrap resamples opportunities WITHIN each seed and applies the same draw
to every arm, so the arms stay paired on the same questions; differences against b7 use the same
draws.

| arm | robot feasible on time | CI95 | difference vs b7 | robot all on time | difference vs b7 | SS on time | CI95 | difference vs b7 | dashcam all-meet |
|---|---|---|---|---|---|---|---|---|---|
| b7-edf-feasibility | 64 / 69 = 0.9275 | [0.8551, 0.9855] | reference | 64 / 89 = 0.7191 | reference | 1306 / 1426 = 0.9158 | [0.9011, 0.9299] | reference | 4 of 4 |
| eco-llm | 62 / 69 = 0.8986 | [0.8261, 0.9565] | [-0.0725, 0.0000] | 62 / 89 = 0.6966 | [-0.0562, 0.0000] | 1191 / 1426 = 0.8352 | [0.8163, 0.8541] | **[-0.0954, -0.0666]** | 4 of 4 |
| mooncake | 64 / 69 = 0.9275 | [0.8551, 0.9855] | [0.0000, 0.0000] | 64 / 89 = 0.7191 | [0.0000, 0.0000] | 1304 / 1426 = 0.9144 | [0.8997, 0.9285] | [-0.0063, 0.0035] | 4 of 4 |
| hybrid-F-lhreq | 67 / 69 = 0.9710 | [0.9275, 1.0000] | [-0.0145, 0.1014] | 67 / 89 = 0.7528 | [-0.0112, 0.0899] | 1372 / 1426 = 0.9621 | [0.9516, 0.9719] | **[0.0316, 0.0610]** | 4 of 4 |
| hybrid-F6-lhreq | 65 / 69 = 0.9420 | [0.8841, 0.9855] | [-0.0435, 0.0725] | 65 / 89 = 0.7303 | [-0.0337, 0.0562] | 1356 / 1426 = 0.9509 | [0.9390, 0.9621] | **[0.0196, 0.0505]** | 4 of 4 |

Read the two columns that exclude zero and the three that do not.

**The single-shot column separates the arms and the robot column does not.** hybrid-F is +3.2 to
+6.1 pp over b7 on single-shot on time and hybrid-F6 is +2.0 to +5.1 pp, both excluding zero;
eco-llm is -9.5 to -6.7 pp, also excluding zero. On the robot pool, hybrid-F's +4.4 pp point
estimate carries a CI of [-1.5, +10.1] pp and hybrid-F6's [-4.4, +7.3] pp: at 69 feasible questions
pooled over four seeds, the robot comparison cannot resolve a difference of this size. Mooncake is
indistinguishable from b7 on every axis, exactly as section 4c's mechanism note predicts, since its
377 keep-warm state actions find nothing resident.

So the measured advantage of the frozen policy at 16 devices is on SINGLE-SHOT timeliness, which is
the device type C6 cannot act on and C3 is deliberately not applied to. The robot axis, which is the
axis the study is about, is unresolved at this fleet size.

**Every on-time robot question was a feasible one, in all 20 runs.** The robot-all hits equal the
robot-feasible hits in every single cell (17 / 17, 14 / 14, 19 / 19, 14 / 14 for b7, and so on), so
no arm ever answered an infeasible question on time. The feasibility rule is not merely a filter
here, it is a perfect predictor on these 89 questions, which is the strongest support the D133
headline choice has had, and also the reason the "all questions" column tracks the feasible one.

### 14.2 Per-seed detail, including the seed-6 feasible counts

| arm | seed 0 feas | seed 4 | seed 5 | seed 6 | SS per seed | errors per seed |
|---|---|---|---|---|---|---|
| b7-edf-feasibility | 17 / 18 | 14 / 15 | 19 / 22 | 14 / 14 | 317, 332, 320, 337 of 356, 357, 356, 357 | 1, 0, 0, 0 |
| eco-llm | 16 / 18 | 14 / 15 | 19 / 22 | 13 / 14 | 292, 294, 304, 301 | 1, 0, 0, 1 |
| mooncake | 17 / 18 | 14 / 15 | 19 / 22 | 14 / 14 | 319, 332, 319, 334 | 0, 0, 0, 1 |
| hybrid-F-lhreq | 17 / 18 | 15 / 15 | 21 / 22 | 14 / 14 | 341, 339, 343, 349 | 1, 0, 0, 0 |
| hybrid-F6-lhreq | 16 / 18 | 14 / 15 | 21 / 22 | 14 / 14 | 335, 334, 342, 345 | 1, 0, 0, 0 |

Seed 6 contributes 14 feasible robot questions of 20 asked, the smallest feasible pool of the four
seeds; seed 5 the largest at 22 of 25. Pooled, 69 feasible of 89 asked. D82's 20-question minimum
is met per run on ALL questions (20 to 25) and is NOT met per run on the feasible pool (14 to 22),
which is why the feasible column is pooled and never read per cell.

### 14.3 Per-run D133 verdicts, every one of them fragile

A verdict is marked FRAGILE when one question would change it. The bar is `p_rob` 0.9 from each
run's own sweep block, so meeting it needs `ceil(0.9 x feasible)` on time.

| arm | seed 0 | seed 4 | seed 5 | seed 6 |
|---|---|---|---|---|
| b7-edf-feasibility | meets, margin +0 | meets, +0 | **fails, -1** | meets, +1 |
| eco-llm | **fails, -1** | meets, +0 | **fails, -1** | meets, +0 |
| mooncake | meets, +0 | meets, +0 | **fails, -1** | meets, +1 |
| hybrid-F-lhreq | meets, +0 | meets, +1 | meets, +1 | meets, +1 |
| hybrid-F6-lhreq | **fails, -1** | meets, +0 | meets, +1 | meets, +1 |

**All twenty verdicts are fragile.** The feasible pools are 14 to 22 questions against a 90 percent
bar, so one question is worth 4.5 to 7.1 pp and no verdict in this table has more than one
question of slack. hybrid-F is the only arm that meets the bar at all four seeds, and it does so by
exactly one question at three of them. A per-run D133 verdict at this fleet size is a coin landing
on its edge, and nothing in this study should rest on one.

DEFINITIONS, because two "robot pool meets" flags disagree on purpose. The verdict above is over
the D133 FEASIBLE pool. The `robot_pool_meets` flag inside each run's own scorer block is over ALL
robot questions, which is 0.70 to 0.75 against the same 0.9 bar, so it is False in all 20 runs. Both
are correct for what they measure and they must never be quoted as one number.

### 14.4 Second-cell exclusion check (D144 item 2)

The pre-screen in section 13 ran one cell, and the sweep list then excluded arms as duplicates of
another arm on that one cell. This re-runs the identical screen at a SECOND cell, seed 0 instead of
seed 4, same workload, and asks whether each excluded arm is still identical. Output
`results/orchestration/live2/frozen_test/baseline_prescreen_seed0_exclusions.json`.

**Three of the fourteen exclusions were wrong.** At seed 0:

| arm | excluded as identical to | verdict at the second cell | decisions |
|---|---|---|---|
| clockwork | b7-edf-feasibility | **SEPARATES** | 13,621 against 13,623 |
| ekya | b7-edf-feasibility | **SEPARATES** | 13,621 against 13,623 |
| builder-s2-value | b7-edf-feasibility | **SEPARATES** | 13,621 against 13,623 |

Identical at BOTH cells, so a representative plus an identical list is sound:

| representative | identical at both cells |
|---|---|
| b7-edf-feasibility | builder-default, builder-s1-fairshare, builder-s1-feasible, builder-s1-lateness, builder-s4-adaptive, builder-s4-llf, builder-s6-decline, hybrid-base |
| kvflow | pensieve, rh8-demand-aware-oracle |
| always-cloud-fcfs | inar-vl, routellm, videostorm, vllm-priority |

clockwork and ekya are two PUBLISHED systems that a one-cell screen would have dropped from the
sweep. They are restored. Two cells are not all cells either, so the lists above are support for
the grouping, not proof of it, and that is why the grouping is recorded with the cells it was
measured on rather than as a property of the arms.

### 14.5 hybrid-F6r and hybrid-F6rm: built, measured, not run live (D144 item 3)

Both arms are registered in `hybrid_arm.py` and neither runs live: C6 is to be redesigned as a
counterfactual for warming and shedding, and hybrid-F6 results stand as built.

- **hybrid-F6r** gates BOTH C6 consumers to non-single-shot recall: the per-request `_c6_one` and
  the per-period policy-core mirror in `_c6_prepare`, which is where 94 percent of the cost was.
- **hybrid-F6rm** gates only the per-request call and keeps advancing the mirror every period, so
  its robot decisions are identical to hybrid-F6 by construction and it saves nothing.

Why the cheap one is not a speed fix (setwise decision diffs against hybrid-F6, dry, three-type
LH-REQ cells):

| cell | robot decisions moved | single-shot | dashcam | total |
|---|---|---|---|---|
| n=16 seed 0 | 2 | 0 | 82 | 84 |
| n=16 seed 4 | 0 | 0 | 0 | 0 |
| n=20 seed 0 | 0 | 2 | 1 | 3 |
| n=20 seed 4 | 3 | 1 | 142 | 146 |
| **n=32 seed 0** | **12** | **30** | **10,327** | **10,369** |
| n=32 seed 4 | 2 | 8 | 6 | 16 |

All six cells are in `results/orchestration/live2/hybrid/policy_f6r_proofs.json`, with the two
further proofs D144 ruling 4 asks for.

THE CHARACTERISTIC DECISION STILL OCCURS in hybrid-F6r, which a gate that merely silenced C6 would
also have satisfied on the diff table above: `c6_calls` 20 to 52 per cell, `c6_scorer_error` 0 in
all six cells, and every call on a period that holds non-single-shot recall (prepare calls equal
robot-period prepare calls in every cell).

WHAT THE GATE BOUGHT, and it is more than the 92 percent I estimated from the 16-device p50. Wall
time inside the policy-core mirror per 1200 s cell, dry on this box, so a cost of the mirror and not
a live latency:

| cell | hybrid-F6 mirror ms | hybrid-F6r mirror ms | cut | F6 C6 calls | F6r C6 calls |
|---|---|---|---|---|---|
| n=16 seed 0 | 21,517 | 153 | 99.3 % | 371 | 23 |
| n=16 seed 4 | 16,917 | 193 | 98.9 % | 354 | 20 |
| n=20 seed 0 | 56,884 | 424 | 99.3 % | 498 | 26 |
| n=20 seed 4 | 63,664 | 420 | 99.3 % | 376 | 24 |
| n=32 seed 0 | 145,901 | 1,398 | 99.0 % | 788 | 52 |
| n=32 seed 4 | 153,664 | 875 | 99.4 % | 701 | 39 |

So hybrid-F6 spends 17 to 154 seconds of every 1200 second cell inside the mirror, and the gate
removes 99 percent of it. That is the size of the prize the redesign is aiming at, and it is why
the gate is tempting; the diff table above is why it cannot be taken as a relabel.

THE DEVIATIONS ARE NOT A SUBSET, which settles the question by itself. At 32 devices seed 0,
hybrid-F6 deviates 42 times (35 `c6_dev_send_to_hold`, 7 `c6_dev_send_to_recent`) and hybrid-F6r
deviates 10, of which one is a `c6_dev_recent_to_hold` that hybrid-F6 never makes anywhere. A
restriction that produces a deviation KIND the unrestricted arm never produces is not the same
policy with fewer decisions.

`_c6_prepare`'s own docstring says it advances the mirror TO THIS PERIOD, so the mirror carries
state across periods: skip the single-shot-only periods and the mirror reaches the next robot period
having never seen them. The divergence grows with fleet size because the skipped periods grow with
it, and at 32 devices the gate moves ten thousand decisions. **hybrid-F6r is a third policy, not a
faster hybrid-F6**, and only hybrid-F6rm can carry the label "hybrid-F6 with C6 restricted to
robots". Both are recorded here so the redesign starts from the measurement rather than from the
assumption that the gate was free.

The measured cost the gate was meant to remove is in section 6.2: C6's mirror put the F6 arm 2x to
9x over the 100 ms decision period at p99 at every fleet size, with 94 percent of its calls on
single-shot requests. A redesign that keeps the mirror per period pays that; one that does not pays
a different policy. That is the trade the C6 redesign inherits.

D144 item 4, the offline analysis that drives the redesign, is section 12 and was committed earlier
(`c6b6a02`, refreshed in `3faa91e`).

## 15. Offline warm-state study (A6000, 2026-11-20, design input for the C6 redesign)

CPU only, committed traces, no engine, no policy code, no arm. Script
`experiments/orchestration/live2/warm_state_offline.py`, output
`results/orchestration/live2/frozen_test/warm_state_offline.json`.

Section 12 established that no robot question in the entire grid was ever served warm (0
prefix-cache hits against 5.2 to 5.6 million queries per cell, `cached_tokens` 0 on every robot
request), that robot misses are dominated by history prefill, and that prefilling each 30 s upload
batch on arrival would have had 97.8 to 98.7 percent of a question's history in cache. This asks the
next two questions: under real memory capacities, how much of that is keepable, and how much does
choosing WHICH history to keep add over keeping the recent ones.

REGISTERS. **MEASURED: nothing here.** TRACE: session starts and ends with their declared durations,
the 30 s history batches with their own token counts, and each robot question's history tokens and
deadline, all from the committed trace (regenerated locally; the same regeneration reproduced the
H100's robot opportunity ids exactly, section 14). MODELLED: every time and cost, from the committed
curves (`costs.recall_ttft_s`, `recall_gpu_s`, StudyRH5). CONSTRUCTED: the policies, the capacities
below the committed pair, and the oracle.

The composition rule, the one modelling choice that is not just the committed curve: a history of h
tokens with c of them resident at tier X costs `recall_ttft_s(c, X) + recall_ttft_s(h - c, "COLD")`,
which reduces to the committed warm number at c = h and the committed cold number at c = 0. The
HOST-WARM curve already includes the reload, so a host hit is charged its reload.

Three ways the simulation is GENEROUS, so the numbers read as an upper bound on warming's value
rather than a prediction: the whole GPU pool and host tier are given to robot histories (in the live
runs they also hold the dashcam and single-shot working set); a batch prefill is charged its GPU
seconds but never queues; and on-time is TTFT against the 5 s deadline, with a second column adding
section 12.1's measured 0.74 s p50 of waiting plus queueing, with decode excluded in both.

POLICIES. **P0** no warming, as the grid ran. **P1** warm every batch, evict least recently used,
GPU to host to cold. **P2** warm every batch, evict the lowest P(question within T), T in 60, 120,
300 s. **P3** oracle: keeps the histories whose next question is soonest, an upper bound that reads
the future.

P2's hazard is fitted on SEED 0 only, which is not in the evaluation set (seeds 4, 5, 6), so fit and
score never share data (D6): two rates, 3.026e-3 per second for a session not yet asked (34 first
questions over 11,235 s of exposure) and 2.516e-3 for one already asked (14 later questions over
5,565 s). The horizon is clipped by the session's own declared remaining life, which `session_start`
carries. That clipping is what makes T read anything at all: with a two-rate hazard and no clipping
the ranking is monotone in the rate alone, every T gives the same order, and the parameter is inert.
P2 therefore uses one thing LRU does not have, the session's declared end, and that is an assumption
about what a deployed policy would know rather than a free lunch.

### 15.1 Results at 16 devices, seeds 4, 5, 6 pooled (65 robot questions)

Tier columns are where the question found its history. TTFT and on-time are MODELLED.

| capacity | policy | GPU | host | cold | TTFT p50 | p90 | on time of 65 | warming GPU-s per 3 cells |
|---|---|---|---|---|---|---|---|---|
| 1.00x | P0 (as run) | 0 | 0 | 65 | 2.607 | 5.621 | **51** | 0 |
| 1.00x | P1 LRU | 41 | 24 | 0 | 0.613 | 0.908 | **65** | 271 |
| 1.00x | P2 T=60 | 58 | 7 | 0 | 0.576 | 0.851 | **65** | 271 |
| 1.00x | P2 T=120 / 300 | 54 | 11 | 0 | 0.576 | 0.852 | **65** | 271 |
| 1.00x | P3 oracle | 65 | 0 | 0 | 0.562 | 0.829 | **65** | 317 |
| 0.50x | P0 | 0 | 0 | 65 | 2.607 | 5.621 | 51 | 0 |
| 0.50x | P1 LRU | 20 | 30 | 15 | 0.652 | 3.827 | **60** | 1,774 |
| 0.50x | P2 T=60 | 38 | 24 | 3 | 0.589 | 0.955 | **64** | 801 |
| 0.50x | P2 T=120 | 36 | 25 | 4 | 0.589 | 0.955 | 63 | 784 |
| 0.50x | P2 T=300 | 26 | 36 | 3 | 0.623 | 0.955 | 63 | 761 |
| 0.50x | P3 oracle | 65 | 0 | 0 | 0.562 | 0.829 | **65** | 924 |
| 0.25x | P0 | 0 | 0 | 65 | 2.607 | 5.621 | 51 | 0 |
| 0.25x | P1 LRU | 4 | 19 | 42 | 1.867 | 5.574 | **54** | 2,431 |
| 0.25x | P2 T=60 | 15 | 25 | 25 | 0.656 | 5.574 | **55** | 1,765 |
| 0.25x | P2 T=120 | 16 | 22 | 27 | 0.656 | 5.621 | 53 | 1,773 |
| 0.25x | P2 T=300 | 11 | 21 | 33 | 1.647 | 5.621 | 53 | 1,717 |
| 0.25x | P3 oracle | 37 | 28 | 0 | 0.562 | 0.944 | **65** | 1,837 |

**18 devices is the same table, exactly.** At 40:40:20 both 16 and 18 devices give SEVEN robot
devices (16 is 6 dashcam, 7 robot, 3 assistive; 18 is 7, 7, 4), so the robot sessions, batches and
questions are identical and the robot-side simulation cannot differ. That is worth stating for the
grid as well as for this study: moving from 16 to 18 devices buys ZERO additional robot questions,
it only adds dashcam and single-shot load.

Why the two on-time columns are identical in every row: no question's modelled TTFT lands in the
0.74 s window the queue allowance moves across (`in_queue_flip_window` is 0 in all 36 cells). The
TTFT distribution is bimodal, a few hundred milliseconds when warm and seconds when cold, so the
allowance has nothing to flip. The column is reported rather than dropped so that an equality is not
mistaken for a copy.

### 15.2 The control, which is the only thing tying this to reality

P0 is the condition the grid actually ran, so its modelled on-time is checkable against the measured
one. MODELLED 51 of 65. MEASURED at the same seeds: hybrid-F 50, hybrid-F6 49, b7 47, mooncake 47,
eco-llm 46 of 65. The model is optimistic by 1 question against the best arm and 4 against b7, in
the direction its own exclusions predict, since it charges no queueing and no decode. A model that
reproduced the measurement exactly would be the suspicious outcome here; one that is optimistic by
exactly the terms it leaves out is behaving.

### 15.3 What this says for the redesign

**1. At the committed capacity, warming closes the robot deadline completely and selection adds
nothing.** P0 51 of 65 becomes 65 of 65 under every warming policy, recovering all 14 misses, and
the P1 to P3 gap is ZERO questions. At 1.0x the histories simply fit: peak residency is 62,736 to
62,916 GPU tokens against the 62,944 pool with the remainder on host, so an LRU that keeps
everything is already optimal. The cost is 271 GPU-s across three 1200 s cells, 90 per cell, 7.5
percent of one cell's GPU budget.

**2. Selection is worth something only under memory pressure, and then it is worth a lot.** The P1
to P3 gap is 0 questions at 1.0x, **5 questions at 0.5x** (P1 60, P3 65) and **11 questions at
0.25x** (P1 54, P3 65). P2 captures 4 of the 5 at 0.50x (64 of 65) and 1 of the 11 at 0.25x. So a
cheap two-rate hazard plus a declared session end recovers most of what selection can give at half
capacity and almost none of it at quarter capacity, where the ranking problem gets hard.

**3. LRU thrashes, and the cost lands on the GPU budget.** Warming GPU-seconds for P1 rise from 271
to 1,774 to 2,431 across the three capacities, 9x, while the questions it saves fall from 14 to 9 to
3. At 0.25x that is 810 GPU-s per 1200 s cell, 68 percent of the budget, to recover 3 questions of
14, because a history demoted to cold is re-prefilled from scratch at its next batch. P2 does the
same work for 1,765 GPU-s and P3 for 1,837 with all 14 recovered, so **at tight capacity the
difference between selection policies is mostly a difference in wasted prefill, not in hit rate.**

**4. A shorter horizon is better, which is a design answer and a small one.** Under pressure T = 60
beats T = 300 by 1 question at 0.50x and 2 at 0.25x, and the ordering is the same at every capacity.
The parameter only reads anything because it is clipped by the session's declared remaining life, so
the useful signal here is NOT the length of the horizon, it is knowing when a session is over.

### 15.4 A MEASURED control that arrived after the simulation, and it inverts the reading

While this section was being written the H100 ran `edf` and `llf`, the first two arms of the
scheduling sweep. Both EMIT HISTORY BUILDS (359 and 363 of them at 16 devices seed 4, one per
session) where the five frozen-grid arms emit none, so for the first time in this study a robot
question meets a warm prefix. Everything in this subsection is MEASURED from those runs.

**The warming mechanism works, and by more than the model said.** All 16 of edf's warm robot recalls
were preceded by a build on the same session, so the build is what put the prefix in the cache.

| arm | robot requests | cache_path | cached fraction p50 | MEASURED TTFT p50 | mean | max |
|---|---|---|---|---|---|---|
| edf | 16 | WARM | 0.988 | **0.384** | 0.331 | 0.461 |
| edf | 3 | COLD | 0 | 4.448 | 4.945 | 6.257 |
| llf | 12 | WARM | 0.986 | **0.423** | 0.347 | 0.525 |
| llf | 3 | COLD | 0 | 4.568 | 4.961 | 6.247 |
| b7-edf-feasibility | 15 | COLD | 0 | 2.440 | 2.710 | 5.409 |
| hybrid-F-lhreq | 20 | COLD | 0 | 3.100 | 3.626 | 7.291 |

Against section 15.1's MODELLED numbers this is a clean pass in the conservative direction: modelled
warm TTFT p50 0.562 to 0.613 s against 0.384 to 0.423 s measured, and modelled cold 2.607 s against
2.44 to 3.10 s measured. The model understates the warm gain and lands on the cold cost.

**And the arm that gets the warm prefixes has the WORST robot on-time of the four.** Robot questions
on time at 16 devices seed 4: hybrid-F 15 of 20, b7 14, llf 10, **edf 5**. Decomposed as in 12.1:

| arm | wait before release p50 / max | queue residual p50 | prefill (modelled on measured uncached) p50 | arrival to delivered p50 | on time |
|---|---|---|---|---|---|
| edf | **5.483 / 11.741** | 0.376 | 0.027 | 6.839 | 5 of 20 |
| llf | 1.986 / 5.074 | 0.420 | 0.027 | 4.360 | 10 of 20 |
| b7-edf-feasibility | 0.115 / 0.156 | 0.530 | 1.824 | 2.617 | 14 of 20 |
| hybrid-F-lhreq | 0.104 / 0.333 | 0.538 | 2.277 | 3.238 | 15 of 20 |

edf's prefill is 0.027 s, essentially free, and its questions still miss, because each one WAITS
5.5 s at the median and up to 11.7 s before release, which is longer than the entire 5 s deadline.

**WHY it waits, measured rather than assumed.** An earlier draft of this subsection said the
questions queue behind the build traffic. That is WRONG and the right answer is sharper. edf emits
2,697 `defer` decisions where b7 emits none, 36 at the median per robot question and up to 42, and a
robot question is released **0.003 s at the median AFTER the last build completion for its own
session** (min -0.003 s, max 352 s). With `session_MATERIALIZE` 360 and `release_whole` 360 in the
same run, the sequence is: the question arrives, the cold prefill of its history is predicted to
miss the deadline, so the arm defers it in 0.5 s steps while materializing that session's history,
and releases it the instant the materialization lands. The engine queue residual over the same
questions is 0.376 s, so the engine was never the bottleneck.

**So edf warms REACTIVELY, at the question, and the question pays the whole warming latency.** That
is a different failure from the one I first wrote down, and it does not show that warming costs
on-time. It shows that WHEN you warm decides who pays: warming on demand puts the materialization
inside the deadline, warming ahead of arrival does not. The offline policies P1 to P3 all warm ahead
of arrival on batch events, so none of them has this cost, and edf is not a measurement of them.

What the live cells therefore do and do not control for in section 15. They DO confirm the
mechanism and the magnitudes: a build makes the next question on that session warm, and warm is
0.384 s against 2.44 to 3.10 s cold, better than the model's 0.562 s. They do NOT yet test the
model's second generosity, that warming is charged GPU-seconds but never queues, because in these
two arms the warming was serialised with the question by the arm's own deferral rather than
competing with it. Section 16 builds that contention in explicitly and calibrates it here.

Two things this does NOT say. It does not say edf's release discipline is warming's fault: edf is
plain EDF with no feasibility admission, so it releases badly in general, and the 5.5 s wait is a
property of the arm as much as of its builds. And it does not say the five frozen-grid arms could get
the warm prefixes for free: they emit no builds at all, so for them the warm path was never
reachable, which is what 12.2 measured.

SCOPE CORRECTION TO 12.2, which said no robot question in the grid was ever served warm. That is
exact for the five frozen-grid arms over the 13 cells it names, and it is NOT true of the grid as a
whole now that edf and llf have run: 16 of 19 and 12 of 15 of their served robot questions were warm
at 96.6 percent cached. The warm-state axis is not unexercisable in this harness; it is unexercised
by the arms that emit no builds.

**5. The honest limit of all five points.** The median robot history is asked exactly ONE question
(section 12.4), so every policy above is choosing what to keep for a single future event per
session, and the oracle's advantage is almost entirely the advantage of knowing which sessions those
are. A warming policy in this workload is a prediction problem about sparse one-shot demand, not a
caching problem about reuse. That is the shape the C6 redesign has to address, and it is the opposite
of what a counterfactual chooser tuned on repeated access would assume.

## 16. Warming that competes for the GPU, calibrated on the live cells (user addendum, 2026-11-20)

Section 15 charged warming its GPU-seconds and never queued it, which section 15.4 showed is the
exclusion that matters. This part builds the contention in: every request and every warming prefill
goes through one shared server model, and two warming DISCIPLINES are compared under every placement
policy. Script `experiments/orchestration/live2/warm_state_contention.py`, output
`results/orchestration/live2/frozen_test/warm_state_contention.json`.

**W1** warms immediately on arrival: a prefill joins ONE FIFO with deadline work, so a prefill that
arrived first holds a slot the next question waits for. **W2** warms only into spare capacity:
strict priority for deadline work, and a prefill may not start while anything queued is at risk,
using the policy's own committed test, laxity below 0.3 times the deadline (D143 ruling B). A prefill
is never preempted once started, because a prefill is not resumable. Placement policies are section
15's P1 LRU, P2 at T = 60 s and P3 oracle, with P0 (no warming) as the floor.

### 16.1 Calibration against the live edf and llf cells, and what it is worth

Two numbers, and only one is fitted.

**f, the interference factor, FITTED.** The committed curve gives a request's GPU-busy time in
isolation; measured TTFT at this load is larger because the engine batches. Fitted as the ratio of
measured median TTFT to modelled service on the two WARMING-FREE arms: **dashcam 3.18, single-shot
1.47, robot recall 1.38**. That the dashcam factor is the largest is itself informative: a 378-token
frame spends most of its TTFT waiting its turn inside the batch, not computing.

**c, the slot count, MEASURED not fitted.** The engine's own concurrency in the same cells, the sum
of measured TTFT over the run length: 7,008 s over 1,200 s, so **c = 5**.

Fit quality, with the two warming arms as pure validation (modelled over measured, so 1.00 is
perfect):

| arm | role | dashcam | single-shot | robot | build |
|---|---|---|---|---|---|
| b7-edf-feasibility | fit | 1.02 | 1.00 | 1.03 | n/a |
| hybrid-F-lhreq | fit | 0.98 | 1.00 | 1.03 | n/a |
| edf | **validation** | 0.99 | **0.27** | **1.38** | **0.65** |
| llf | **validation** | 1.00 | **0.26** | 0.95 | **0.66** |

**Where the fit holds and where it does not, stated rather than averaged.** Dashcam service
transfers to the validation arms within 1 percent, and llf's robot recalls within 5 percent. The
three bad cells are all on the WARM side, which is exactly the side the fit could not see: f was
fitted on arms whose every request is cold, so a warm single-shot request is modelled at 0.087 s
against 0.316 s measured (x0.27) and a build at 0.293 s against 0.448 s (x0.65). **So this model
UNDERSTATES the cost of warm service and of warming itself by roughly 1.5x on builds and 3.7x on
warm single-shot.** Every W1-versus-W2 difference below is therefore a LOWER BOUND on the contention
a real engine would show, and the on-time levels are not predictions: the model gives P0 43 of 65
robot questions against 46 to 50 measured, and 1,070 of 1,070 single-shot against 1,306 of 1,426
measured, because single-shot service here is one fixed prompt size with no decode. **Read the
columns against each other, never as levels.**

### 16.2 Results, 16 devices, seeds 4, 5, 6 pooled (65 robot, 1,070 single-shot)

| capacity | policy | W | robot on time | warm | robot queued (p90 / max s) | SS on time | SS queued (p90 / max s) | warming GPU-s |
|---|---|---|---|---|---|---|---|---|
| 1.00x | P0 | none | 43 / 65 | 0 | 9 (0.014 / 0.063) | 1070 / 1070 | 145 (0.021 / 0.153) | 0 |
| 1.00x | P1 | W1 | **65 / 65** | 65 | 10 (0.024 / 0.063) | 1070 / 1070 | 153 (0.023 / 0.157) | 271 |
| 1.00x | P1 | W2 | **65 / 65** | 65 | 10 (0.024 / 0.063) | 1070 / 1070 | 153 (0.019 / 0.157) | 271 |
| 1.00x | P2 / P3 | W1, W2 | 65 / 65 | 65 | 10 to 13 | 1070 / 1070 | 153 to 154 | 271 to 317 |
| 0.50x | P1 | W1 | 55 / 65 | 48 | 18 (0.054 / 0.486) | 1062 / 1070 | 328 (0.154 / **3.746**) | 1,764 |
| 0.50x | P1 | W2 | **56 / 65** | 49 | 20 (0.057 / 0.198) | **1069 / 1070** | 320 (0.118 / 1.589) | 1,756 |
| 0.50x | P2 | W1 | 63 / 65 | 62 | 12 (0.030 / 0.417) | 1068 / 1070 | 194 (0.053 / 2.116) | 801 |
| 0.50x | P2 | W2 | 63 / 65 | 62 | 12 (0.030 / 0.417) | 1068 / 1070 | 194 (0.049 / 2.046) | 801 |
| 0.50x | P3 | W1 | 65 / 65 | 65 | 13 (0.033 / 0.129) | 1070 / 1070 | 210 (0.056 / 1.083) | 924 |
| 0.50x | P3 | W2 | 65 / 65 | 65 | 13 (0.033 / 0.096) | 1070 / 1070 | 209 (0.053 / 0.902) | 924 |
| 0.25x | P1 | W1 | 47 / 65 | 22 | 23 (0.122 / 0.711) | 1059 / 1070 | 388 (0.264 / **3.746**) | 2,433 |
| 0.25x | P1 | W2 | 47 / 65 | 22 | 25 (0.087 / 0.491) | **1068 / 1070** | 383 (0.157 / 1.625) | 2,433 |
| 0.25x | P2 | W1 | 49 / 65 | 40 | 16 (0.072 / 0.491) | 1064 / 1070 | 309 (0.116 / 2.360) | 1,763 |
| 0.25x | P2 | W2 | 49 / 65 | 40 | 17 (0.072 / 0.491) | 1066 / 1070 | 303 (0.094 / 2.046) | 1,763 |
| 0.25x | P3 | W1 | **65 / 65** | 65 | 19 (0.080 / 0.711) | 1066 / 1070 | 303 (0.092 / 2.515) | 1,830 |
| 0.25x | P3 | W2 | **65 / 65** | 65 | 20 (0.080 / 0.491) | 1068 / 1070 | 302 (0.087 / 2.046) | 1,832 |

### 16.3 What the contention actually costs

**1. At the committed capacity there is no contention to manage.** Robot on-time is 65 of 65 under
every policy and both disciplines, 10 of 65 questions queue at all, and the worst wait in the whole
cell is 63 ms. The GPU has spare slots: deadline work needs about 3.1 of the 5 and warming 0.2 more.
**W1 and W2 are indistinguishable on outcomes here**, differing only in the single-shot queue p90
(0.019 s against 0.023 s). The binding resource at 1.0x is MEMORY, which is what section 15 found,
and adding GPU contention does not change that conclusion.

**2. Under memory pressure the discipline starts to pay, and it pays on SINGLE-SHOT, not robots.**
At 0.50x with LRU, W2 buys 1 robot question (56 against 55) and **7 single-shot questions (1,069
against 1,062)**, and cuts the worst single-shot queue wait from **3.746 s to 1.589 s**. At 0.25x it
buys 0 robot and **9 single-shot** (1,068 against 1,059), with the worst wait 1.625 s against
3.746 s. The reason is the deadline asymmetry: a single-shot request has 2 s and a robot 5 s, while a
warming prefill occupies a slot for 0.3 to 0.9 s, so an immediate prefill is a serious fraction of a
single-shot budget and a minor one of a robot's. **Warming traffic injures the tightest deadline
class first**, which is the class C6 was already unable to help (section 6.2).

**3. Why pressure creates contention at all, when the GPU is the same size.** Warming GPU-seconds
rise from 271 at 1.0x to 1,764 and 2,433 at 0.50x and 0.25x for LRU, because evicted histories are
re-prefilled, so the memory limit manufactures GPU load. At 0.25x that is 811 GPU-s per 1,200 s
cell. **Contention here is a SYMPTOM of thrashing, not an independent cost**, and the way to avoid it
is to keep the right histories, not to schedule the prefills better: P2 at 0.50x reaches 63 of 65
with 801 GPU-s where P1 reaches 55 with 1,764.

**4. Selection still dominates discipline.** At 0.50x, switching LRU to the hazard policy is worth 7
to 8 robot questions; switching W1 to W2 is worth 1. At 0.25x the oracle is worth 16 to 18 robot
questions over P2 and the discipline 0. If the redesign can afford one mechanism, it should be the
choice of WHAT to keep, not the scheduling of WHEN to prefill it.

**5. The one place the discipline is not optional.** W1's worst single-shot queue wait is 3.746 s
against a 2 s deadline, so an immediate-warming policy does not merely miss a few single-shot
deadlines, it misses them by more than the deadline itself. Given that the calibration understates
warm and build service by 1.5x to 3.7x (16.1), a real engine would show this worse than the table
does. **W2 is the safe default and W1 should not be built**, even though at the committed capacity
the two are equivalent: the cost of W1 appears exactly in the regime a deployment would hit first,
which is memory pressure.

## 17. KV-reuse debug: why prefix_cache_hits is 0 (A6000, 2026-11-20, user request)

OFFLINE. Committed request logs, committed metrics snapshots and committed code only. No GPU, no
model server, nothing touched on the H100, which was running StudySH-EP throughout. Worked example
`eco-llm_n16_s4_1200s_h27_3t`, cross-checked against its postfix twin and `hybrid-F-lhreq` at the same
cell.

**The answer in one line: the server was configured correctly and the workload has almost no reusable
prefix, and the three places where it does have one are separated by enough traffic to turn the KV pool
over at least twice.** No flag needs changing and nothing on the server needs fixing for this.

### 17.0 One definition first, because it changes the size of the puzzle

`prefix_cache_queries_total` counts **tokens queried, not requests**. This run's committed snapshot
delta is **5,579,984** and the sum of `prompt_tokens` over its 13,562 requests is **5,604,554**, which
agree to 0.4 percent, the snapshot window omitting the first and last ten seconds. So "0 of about 5.5M
queries" is 0 of 5.5M tokens offered over 13,562 requests, not 5.5M missed reuse opportunities. The
number of requests that had any earlier request to reuse at all is **3**.

### 17.1 The server was configured for reuse, and one cache proves it worked

Each run's own `header.json` records the server's full argv at `server.command`, 37 elements for this
cell. It passes `--no-enable-prefix-caching` at element 13 and `--enable-prefix-caching` at element 27,
and `--limit-mm-per-prompt` twice, at 14 and 20, with `--mm-processor-cache-gb` at 29. Last occurrence
wins in argparse, so prefix caching was ON, the image cap was the later 640 and the multimodal
processor cache was ON at 128 GB. The metrics agree: a disabled prefix cache does not report 5.6M
queries. `experiments/dashcam/sh_ep_server_h100.sh` reproduces the same command byte for byte, which is
how this section first recovered it, but the run record is the better citation and is used here.

**The multimodal cache hit exactly as often as it could have, which rules out the uuid path.** From the
committed `mm_gate.json`: `mm_cache_queries` 16,342 and `mm_cache_hits` **345**. Counting image-part
references in the request log gives 16,407 references over 16,062 distinct uuids, so **345 references
beyond the first**, and no uuid is referenced more than twice.

| quantity | from the request log | from the server's counters |
|---|---|---|
| image-part references | 16,407 | 16,342 queries (window omits ~20 s) |
| references beyond the first | **345** | **345 hits** |

Exact agreement. The D84 uuid mechanism resolves every repeated frame to a cache hit and never misses
one. So the multimodal path is not where the KV zero comes from, and this also corrects a reading I
sent the H100 earlier in the day: I had grepped `mm_cache_hits_total=0` out of the early snapshots and
generalised it to the run. The run's delta is 345, not 0, and the H100 was right to ask for the gate
file.

### 17.2 What the request stream actually offers

| requests | share | what two consecutive ones share |
|---|---|---|
| 13,186 single-frame dashcam monitors, all 378 tokens, one image each | 97.2 % | the chat wrapper and the header only, which is on the order of 12 to 18 tokens, against vLLM's 16-token block. Measurably zero blocks: 13,186 requests produced no hit |
| 376 recall requests over 373 sessions | 2.8 % | 370 sessions hold exactly ONE request |

So **3 requests in 13,562 have any earlier request on the same history**, and a perfect cache could have
hit on 3. All 16 cache salts are constant per device, one each, so the salt breaks nothing.

### 17.3 The three real opportunities, and why each was certainly evicted

All three are append-only with the same salt and the same leading frame refs in the same order, at 90
tokens per recall frame. The GPU KV pool is **62,944 tokens**, which is 3,934 blocks of 16.

| session | reuse on offer | separated by | pool turnover between them |
|---|---|---|---|
| robo004 s000, r1270 to r5281 | 60 frames, about 5,400 tokens | 350.0 s, 4,010 requests, 1,653,204 tokens | **26.3x** |
| robo002 s001, r7330 to r7719 | 180 frames, about 16,200 tokens | 34.1 s, 388 requests, 160,955 tokens | **2.6x** |
| robo003 s001, r7585 to r9532 | 105 frames, about 9,450 tokens | 170.0 s, 1,946 requests, 789,896 tokens | **12.5x** |

The whole run pushes 5,604,554 prompt tokens through a 62,944-token pool in 1,200 s, **89 pool
turnovers**. Even the closest pair has 2.6 turnovers between its two requests. Eviction before reuse is
not a hypothesis here, it is arithmetic, and it is the same mechanism section 15 measured offline: this
is the P0 no-warming case with LRU, observed on the real engine.

### 17.4 (b) Is the full-history body append-only?

**Append-only for every representation except RECENT.** `coordinator.py:606` builds the whole body as
`refs[idx0:]` with `idx0 = 0`, and the piece path (`:558`) sends `s.frames[:already]` as uuid-only
references followed by the new refs, so frames are never re-selected and never resampled: a longer
history is the shorter one plus a suffix, in the same order. The request log confirms it from the other
side, since the three repeated sessions share their leading uuids exactly.

**The one exception is prefix-breaking by construction**, and it is new. The RECENT-send fix of
2026-11-20 (`coordinator.py:597-604`) sets `idx0 = len(refs) - k`, so a RECENT release sends a **moving
suffix window** of the history. Its first frame changes as the session grows, so it shares nothing with
the full-history body beyond the header. That is the right behaviour for the charge it models, and it
is worth recording that it also forecloses prefix reuse for those requests. Count in the postfix cell:
`recent_window_sends` **5**, against 0 pre-fix.

### 17.5 (c) Does the harness abort late requests, or evict anything deliberately?

**No, and no.** There is no `abort` and no `.cancel(` anywhere in `experiments/orchestration/live2/*.py`.
The HTTP timeouts are 600 s (`asyncbackend.py:107`, `backend.py:85`), far above any request in this run,
so no request is dropped for lateness: a late request is scored late, not cancelled.

The only `evict` in the live2 tree is the **simulated** one. `cstate.enact_placement` counts
`offloaded / kept_warm / evicted / resident`, and `run_live2_real.py:52-53` says in terms what those
counts are: "Output-only: total enact_placement's per-call counts, which cstate returns and discards, so
a run records whether --kv-capacity-enforced ever evicted anything. **No decision reads it.**" So the
policy's model of KV residency never touches the engine's actual cache. Nothing in the harness evicts
anything from vLLM, and the eviction that produced the zero is vLLM's own LRU under the turnover in
17.3.

### 17.6 Most likely cause, and what the H100 should check when the grid server next comes up

**Cause, in order of contribution.** (1) 97.2 percent of requests are single-frame monitors with less
than one block of shared prefix, so most of the run cannot hit by construction. (2) The robot side
offers 3 reuse opportunities in 13,562 requests, because 370 of 373 sessions hold a single request.
(3) All 3 are separated by 2.6 to 26.3 pool turnovers, so they were evicted before reuse. Together
these account for the zero completely, with no server defect required.

**What is still worth one check, and it is small.** The arithmetic says those 3 were evicted, but it
does not prove the block hashes would have matched had they survived. When the frozen-grid server is
next up, and only then, the cheap test is a **back-to-back** pair rather than a forensic one: send one
recall body, then immediately resend it with one frame appended, same salt, same device, nothing in
between, and read `cached_tokens` on the second. StudySH-EP has in effect already run that test on the
same build and it passes, with `cached_tokens` 3,056 to 6,768 on appended requests, so the expected
result is a hit, and a miss would be the only genuinely new information available here.

Worth looking at on the server side when convenient, none of it implicated by the evidence above:
`--kv-offloading-backend native --kv-offloading-size 27`, in case the offload connector changes block
reuse.

**A correction to a recommendation this section first made.** It said the duplicated
`--no-enable-prefix-caching` then `--enable-prefix-caching`, and the two `--limit-mm-per-prompt`,
"should be reduced to a single flag" whenever the launcher is next edited. That was written without
checking what the flag list is, and the H100 pointed out what it is.
`experiments/orchestration/study_live2_pilot.py:80-83` builds the list from `E.COMMON` and then
**refuses to start** unless it matches the committed `DE_c38` server's flags element for element, with
only the host-tier size allowed to differ: `if diff != [("38", host_gib)] or len(ref) != len(flags):
raise SystemExit`. Deduplicating the list is therefore not a tidy-up of a launcher, it is a change to
the pinned configuration that every frozen-grid and sweep cell has run under, and it would also trip
the equality check itself. Under CLAUDE.md that is a methodological change and needs a ruling before
it is applied, not an edit at the next convenient moment. The StudySH-EP launcher copies the round-1
command byte for byte on purpose and stays as it is.

The underlying concern stands and is recorded here rather than acted on: the configuration is correct
today only because argparse takes the last occurrence, so a future reordering of a pinned list could
silently disable prefix caching in a run that would still look entirely normal. The cheap mitigation
that does NOT touch the pinned list is to record the engine's own RESOLVED cache setting beside the
argv.

A second correction, also the H100's, also to something this section asserted without checking.
It said no run record states the cache configuration. **The argv is recorded**, per run, at
`header.json` `server.command`, which is where 17.1 now cites it from; what is absent is the resolved
value, and `header.json`'s `server` block has no field of that kind. So a reader CAN establish from a
committed run that prefix caching was on, by applying the last-occurrence rule to the recorded argv,
and this section's first draft recovered the command from a launcher script when it could have read it
from the run directory it was already analysing. The residual gap is narrower than claimed and worth
closing anyway: one field carrying the engine's own `enable_prefix_caching=True` from its init log,
next to the argv, would spare every future reader the argparse reasoning on a list that deliberately
contradicts itself. That is a record addition rather than a pinned-list change, so it does not need
the ruling the dedup does, and the H100 will add it when a grid server next starts.

**What this is NOT.** It is not evidence that prefix caching fails on this engine, and it must not be
cited that way: the same build hits on appended requests in StudySH-EP. It is evidence that **the
frozen grid's own traffic has essentially no reuse to find**, which is a statement about the workload
and about the 62,944-token pool, and it is the live counterpart of section 15's finding that memory, not
the GPU, is the binding resource.

## 18. D146 item 1: completion delivery, re-scored (A6000, 2026-11-20)

OFFLINE. Committed `outcomes` and `request` logs only; no GPU, no model server, no rerun. Scripts
`completion_delivery_rescore.py` (the audit, 40 runs) and `frozen_headline.py` (the headline, now
delivery-aware). Old numbers are kept throughout and labelled **first-token delivery**.

### 18.1 The committed stamp is first-token based, verified in all 40 runs

`outcomes.t_cloud_done` equals the request log's `t_first_token` **exactly in all 40 runs, 0
mismatches**, and `t_delivered` is that plus a per-row forward delay which is the 0.0222 s constant
section 12.3 identified. The completion stamp is therefore

    t_delivered_completion = t_done + (t_delivered - t_cloud_done)

with the forward delay taken per row rather than assumed. A recall outcome with no matching cloud
request was never sent, so no delivery rule can change its status; those are excluded from the flip
count and reported separately.

### 18.2 Flips, 40 runs

| kind | outcomes | flips to late | flips to on time |
|---|---|---|---|
| robot | 880 | **132 (15.0 percent)** | 0 |
| single shot | 14,502 | **217 (1.5 percent)** | 0 |

Zero flips the other way, as the arithmetic requires: completion is never earlier than first token.
The robot side is ten times more affected than single shot, and 18.4 says why.

### 18.3 The four-seed headline at 16 devices, both rules

Seeds 0, 4, 5, 6; the same cells and the same paired-by-seed bootstrap as section 14.

| arm | robot feasible, first token | robot feasible, **completion** | robot all | SS | minus b7, completion |
|---|---|---|---|---|---|
| b7-edf-feasibility | 64/69 = 0.9275 | **42/69 = 0.6087** | 0.7191 to 0.4719 | 0.9158 to 0.8934 | reference |
| mooncake | 64/69 = 0.9275 | **42/69 = 0.6087** | 0.7191 to 0.4719 | 0.9144 to 0.8948 | [-0.0435, +0.0435] |
| eco-llm | 62/69 = 0.8986 | **39/69 = 0.5652** | 0.6966 to 0.4382 | 0.8352 to 0.8128 | [-0.1159, +0.0145] |
| hybrid-F6-lhreq | 65/69 = 0.9420 | **61/69 = 0.8841** | 0.7303 to 0.6854 | 0.9509 to 0.9481 | [+0.1739, +0.3913] |
| hybrid-F-lhreq | 67/69 = 0.9710 | **66/69 = 0.9565** | 0.7528 to 0.7416 | 0.9621 to 0.9600 | **[+0.2319, +0.4638]** |

**The delivery rule changes the study's conclusion, it does not merely move the numbers.** Under
first-token delivery the five arms sit within 7 points of each other on robot feasible on-time, which
is close to the noise floor at 69 questions. Under completion delivery they split into two groups 30
points apart, and hybrid-F minus b7 becomes **[+0.2319, +0.4638]**, an interval nowhere near zero.
hybrid-F loses **1** question of 69 where b7 and mooncake lose **22** each.

### 18.4 The mechanism, as first reported. WRONG; superseded by 18.7

The obvious explanation would be that arms which load the engine harder get slower decodes. **That is
measurably false here.** Over ALL requests at 16 devices, seed 4, decode p50 is 0.045 to 0.078 s for
every one of ten arms, and the correlation between an arm's total prompt tokens and its decode p50 is
**r = 0.06**. Contention does not explain it.

Decode time scales with **context length**. Pooled over every 16-device cell, 13,858 recall requests:

| prompt tokens | n | decode p50 | decode p90 |
|---|---|---|---|
| under 1,000 | 5,335 | **0.072 s** | 0.212 s |
| 1,000 to 3,000 | 7,812 | 0.100 s | 0.258 s |
| 3,000 to 8,000 | 216 | 0.295 s | 0.692 s |
| 8,000 to 15,000 | 276 | 0.971 s | 1.422 s |
| over 15,000 | 219 | **1.197 s** | 1.439 s |

A 16-fold longer prompt costs 16 times the decode **for the same two output tokens**, which is what
attention over a longer KV costs per step. So an arm that sends the whole history pays for it twice,
once in prefill and again in decode, and **the first-token stamp hid the second payment entirely**.
That is why the robot side flips ten times more often than single shot: robot prompts reach 21,720
tokens while single-shot prompts are around 1,372.

**Everything in this subsection after the binned table is wrong and is retracted in 18.7.** It is
left in place, struck through in substance rather than deleted, because the way it was wrong is worth
keeping: a pooled relation that looked like a clean monotone law was confounded by arm, and the test I
ran to rule out the alternative was the wrong test. The retracted claim was that hybrid-F's advantage
is a representation advantage, its RECENT window being shorter than the full history b7 and mooncake
send. It is not.

### 18.5 What is now the default, and the one thing I could not verify here

Completion delivery is the default in both scorers, with the old rule reachable for comparison:
`scorer/score.py` via `LIVE2_DELIVERY=first_token` and `frozen_headline.py` via
`FROZEN_HEADLINE_DELIVERY=first_token`. In `score.py` the rewrite sits beside the D144 pass that
nulls a failed request's delivery, for the same reason: `_within`, `robot_value` and the assistive
scoring all read `t_delivered`, so one rewrite reaches every downstream check.

**Register, stated plainly: `frozen_headline.py` was RUN here under both rules and its numbers are
above; `scorer/score.py` was NOT run here.** It requires the trace directory, which lives on the
H100 and not on this box, so what is verified for it is that it parses, that the rewrite is ordered
after `reqs` and `out` are bound and before the decision load, and that it joins on the `out` dict's
own key rather than on a field inside the row. Its arithmetic is the same expression that
`completion_delivery_rescore.py` and `frozen_headline.py` both compute independently and agree on.
**The gap is now CLOSED and `score.py` has been run here, both ways.** It took two steps and the
first failure was mine. The H100 committed the seed-4 three-type trace; with it in place `score.py`
still raised `ScoringRefused` under D86, because I had let it fall back to its DEFAULT calibration
argument, which is the INTERIM `orin2_calibration.json`, against a real `vllm` run. That refusal was
correct and the fix was to pass the dense refit the H100's own driver passes,
`results/orchestration/live2/calibration/live2_calibration_dense_jpeg.json`, which is tracked on
origin. Nothing was bypassed; the guard was right and I was using the wrong file.

With the dense refit, `b7-edf-feasibility_n16_s4` scored both ways:

| delivery rule | robot pool on time | fraction |
|---|---|---|
| first token | **14 of 20** | 0.70 |
| completion | **11 of 20** | 0.55 |

`completion_delivery_rescore.py` independently reported 14 to 11 with 3 flips for that same cell, so
**three implementations now agree on the same cell**: the audit script, the headline script and the
production scorer. No part of section 18 rests on an unexecuted code path any more.

This also answers a question the H100 raised about its own work: the refusal was caused by my
calibration argument, not by anything in its scoring setup, so its cells' scoring is not in question.

### 18.6 P20, which this raised

The committed robot recall cap is `max_tokens` 512, and the ruling preserves it. But **the realised
answer is 2 output tokens in every committed cell**, because the question is multiple choice and the
model stops at the letter, so the cap has never bound and completion currently charges the decode of
2 tokens only. A format whose answer is longer would make the cap bind and change this arithmetic by
orders of magnitude, given that 2 tokens already cost 1.197 s above 15,000 prompt tokens. P20 records
that the cap must be re-benchmarked against the answer length a chosen format actually produces,
before that format is adopted.


## 18.7 Correction to 18.4: the mechanism is per-request concurrency, not context length

The H100 challenged 18.4 on two specific grounds and **both challenges were right**. The claim is
retracted and replaced. Nothing in 18.1 to 18.3 changes: the flips, the headline and the conclusion
that the delivery rule separates the arms all stand. What was wrong is the explanation of WHY.

### 18.7.1 The two challenges, and what checking them showed

**Challenge 1: RECENT is too rare to carry the effect.** hybrid-F releases RECENT on only 3 to 5
robot questions per run, 5 / 5 / 3 / 5 at seeds 0 / 4 / 5 / 6, against a 21-question difference in
flips. Correct, and the measurement is worse for my claim than the counting argument suggested.

**Challenge 2: the headline cells are PRE-FIX.** Correct and decisive. `frozen_headline.main` builds
the path `{arm}_n{n}_s{seed}_1200s_h27_3t` exactly, with no `_postfix` suffix, so all four seeds of
all five arms are pre-fix cells. Pre-fix, a RECENT release **sent the whole history while charging
467 tokens**, which is the defect the RECENT-send fix repaired. So in these cells RECENT could not
have shortened anything, and my mechanism was impossible on its own cells.

**And the direct measurement refutes it outright.** Robot prompt tokens, p50, on the same questions:

| seed | b7 | mooncake | eco-llm | hybrid-F | hybrid-F6 |
|---|---|---|---|---|---|
| 0 | 11,587 | 11,587 | 12,927 | **13,588** | 12,927 |
| 4 | 8,207 | 8,207 | 10,248 | **10,248** | 10,248 |
| 5 | 9,623 | 9,623 | 12,228 | **12,228** | 12,228 |
| 6 | 9,566 | 9,566 | 11,602 | **11,602** | 11,602 |

**hybrid-F's robot prompts are the same as or LONGER than b7's at every seed**, while its decode is
four to six times shorter. And eco-llm sends prompts IDENTICAL to hybrid-F's at seeds 4, 5 and 6 with
a decode of 1.27 to 1.38 s against hybrid-F's 0.18 to 0.31 s. Same lengths, four to seven times the
decode. Context length cannot be the mechanism.

### 18.7.2 The actual mechanism: how busy the engine is during that request's decode

For each robot request, counting the other requests whose own `[t_submit, t_done]` interval overlaps
its decode window `[t_first_token, t_done]`:

| arm | robot requests | overlapping requests, p50 | decode p50 |
|---|---|---|---|
| eco-llm | 86 | **61** | 1.340 s |
| mooncake | 69 | **51** | 1.157 s |
| b7-edf-feasibility | 69 | **50** | 1.154 s |
| hybrid-F6-lhreq | 86 | **9** | 0.250 s |
| hybrid-F-lhreq | 87 | **9** | 0.253 s |

**Pearson r = 0.858** between overlapping requests and decode duration over all 397 robot requests,
against **r = 0.266** for prompt tokens on the same 397. Within every arm separately, concurrency is
the stronger predictor too: 0.864 against 0.713 for b7, 0.330 against 0.281 for hybrid-F.

So the binned table in 18.4 was a pooled relation **confounded by arm**: its long-prompt bins are
dominated by exactly the arms that are also the busiest at decode time. Binning made a weak,
mediated association, r = 0.266, look like a clean monotone law. Prompt length does matter within an
arm, partly because a longer request occupies the engine longer and so raises its own measured
overlap, but across arms it points the wrong way.

### 18.7.3 What the result actually says, which is a different claim

hybrid-F's advantage under completion delivery is a **timing advantage**: it releases robot questions
into an engine five to six times quieter than the one b7, mooncake and eco-llm release into. Its
deferral and release timing, which is what the policy exists to do, keeps its robot requests out of
the crowd, and the first-token stamp could not see the benefit because the crowd's cost is paid
during decode. That is a scheduling result, the opposite of the representation story I told, and it
is a better result for the policy thesis rather than a worse one: the mechanism credited is the one
the policy actually implements in these cells.

The delivery rule's standing is unchanged and so is every number in 18.1 to 18.3. What changes is
what the study may claim about why, and that claim is now attached to an r of 0.858 rather than to a
confounded bin table.

### 18.7.4 Two of my own tests were wrong, in opposite directions

Worth recording because the pair is instructive. To rule out contention I correlated each ARM's total
prompt tokens against its decode p50 over ALL requests and got r = 0.06, then reported that
contention does not explain it. That test could not have detected the effect: it averaged over
13,000 dashcam monitors whose decodes are 0.05 s, and it compared arm means, which discards the
within-run timing that is the whole mechanism. Having wrongly excluded contention, I accepted the
length relation on a binned plot without computing its correlation, which would have shown 0.266.

The right test, per-request overlap of the actual decode window, was neither of those and settles it.
A null from the wrong unit of analysis is not evidence, which is the same lesson CLAUDE.md records
for nulls from absent mechanisms.


### 18.7.5 Crediting the timing result: separating the discipline from the arm's own volume

The H100 cautioned that "the engine is quieter" conflates two things, since an arm's release
discipline and its own offered traffic both shape how busy the engine is when its robot answer
decodes. That is right in form, and it is separable here.

First, a fact that narrows the question: **each cell runs ONE arm**, so every request overlapping a
robot decode window is that arm's own traffic. "The engine is quieter" therefore means "this arm has
less of its OWN work in flight at that moment", which is a property of when it releases, not of who
else is present.

Second, volume contributes almost nothing. Over the four seeds:

| arm | total requests | requests per second | overlap at robot decode, p50 | overlap divided by the arm's OWN mean in-flight |
|---|---|---|---|---|
| b7-edf-feasibility | 54,270 | 11.31 | 50 | **5.5** |
| mooncake | 54,272 | 11.31 | 51 | **5.6** |
| eco-llm | 54,292 | 11.31 | 61 | **4.1** |
| hybrid-F-lhreq | 51,195 | 10.67 | 9 | **2.1** |
| hybrid-F6-lhreq | 50,305 | 10.48 | 9 | **2.0** |

hybrid-F sends **5.7 percent** fewer requests than b7 and has **82 percent** less overlap at its
robot decodes, so volume cannot be the explanation. The last column is the decomposition that
settles it: normalised by each arm's OWN average in-flight load, b7's robot answers decode when the
engine is **5.5 times busier than that arm's own average**, while hybrid-F's decode at **2.1 times**
its own average. Even after removing every difference in how much work an arm offers, hybrid-F's
robot answers land in relatively quieter moments by a factor of about 2.6.

So the credit stands with the release timing, and it is now stated at the right strength: of the
roughly fivefold difference in decode-window concurrency, about 6 percent is attributable to
offering less work and the remainder to offering it at different times.

## 19. D147: what a 3 s robot deadline would cost (A6000, 2026-11-20)

OFFLINE. Committed runs only; no GPU, no model server, no rerun. **Everything here is RE-SCORED and
every decision was made under 5 s**: no arm knew about a shorter deadline, so each chose what to
send, when to defer and what to decline against a 5 s bound. An arm that fails at 3 s below might
not fail if it had been allowed to plan for 3 s, and one that passes might have planned differently
and done better. Single-shot stays at 2 s and dashcams are untouched.

### 19.1 The answer to the question asked: at 3 s, every arm fails

Robot on time over **ALL** questions, completion delivery (D146), 16 devices, each arm pooled over
its own seeds. b7, eco-llm, mooncake and the two hybrids have seeds 0, 4, 5 and 6 (89 questions);
always-cloud-fcfs, edf and llf ran at seed 4 only (20 questions) and are marked.

| arm | seeds | n | L = 2.5 s | **L = 3 s** | L = 4 s | L = 5 s |
|---|---|---|---|---|---|---|
| hybrid-F-lhreq | 0,4,5,6 | 89 | 0.2584 | **0.3258** | 0.5281 | 0.7416 |
| hybrid-F6-lhreq | 0,4,5,6 | 89 | 0.1573 | **0.2809** | 0.4831 | 0.6854 |
| mooncake | 0,4,5,6 | 89 | 0.1685 | **0.2360** | 0.3034 | 0.4719 |
| b7-edf-feasibility | 0,4,5,6 | 89 | 0.1910 | **0.2247** | 0.3146 | 0.4719 |
| eco-llm | 0,4,5,6 | 89 | 0.1685 | **0.2247** | 0.3146 | 0.4382 |
| always-cloud-fcfs | 4 only | 20 | 0.2500 | 0.3500 | 0.3500 | 0.5000 |
| llf | 4 only | 20 | 0.2500 | 0.3500 | 0.3500 | 0.5000 |
| edf | 4 only | 20 | 0.2500 | 0.2500 | 0.2500 | 0.2500 |

**All eight arms fail at 3 s, and all eight already fail at 5 s on this basis.** D133's bar is
p_rob = 0.9 and the best arm reaches 0.3258 at 3 s and 0.7416 at 5 s. That is not a new failure
created by the deadline: D133 is defined over FEASIBLE questions, and over all questions no arm has
ever been close. What the deadline does is widen the shortfall, and it costs the best arm 41 points
(0.7416 to 0.3258) and the weakest 21 (0.4382 to 0.2247).

Ordering is preserved: hybrid-F leads at every deadline, and its lead over b7 grows from 27 points at
5 s to 10 at 3 s in absolute terms while remaining the largest at each. edf is flat at 0.25 across
all four deadlines, which is its own signature: it defers until its history materialises, so its
misses are already far past 5 s and tightening the bound changes nothing for it.

### 19.2 Why they miss at 3 s: the history is cold, and warming alone fixes almost all of it

The 330 robot questions missed at 3 s across the five four-seed arms. 48 were never sent (declined,
or answered on the device), leaving 282 sent misses.

| component of the 282 sent misses | p50 | p90 |
|---|---|---|
| wait before release | 0.128 s | 0.369 s |
| **first-token latency** | **4.001 s** | **6.473 s** |
| decode after the first token | 1.086 s | 1.434 s |
| requests overlapping the decode window | 44 | 81 |

**Every one of the 282 had a COLD history**: 282 COLD, 0 WARM. Waiting before release is never the
problem at 0.128 s, and the first-token latency alone is already over the 3 s budget at its median.

**The counterfactual the brief asks for.** Using the MEASURED warm first-token latency from the edf
and llf cells, **0.3963 s** over their 28 warm requests, plus each question's own measured decode:

| counterfactual | would make 3 s |
|---|---|
| warm history, measured decode as it actually was | **279 of 282** |
| warm history and an idle engine (decode 0.0242 s) | **282 of 282** |

So a 3 s deadline is not what defeats these arms. **A cold history is.** Warming ahead would recover
279 of the 282 sent misses without touching anything else, and the remaining 3 need the engine to be
quieter as well.

### 19.3 Cold feasibility at 3 s, with decode included

The committed feasibility formula is `recall_ttft_s(h, COLD) + recall_ttft_s(h, GPU-WARM) + link`,
which **omits decode**. At 3 s decode can decide a verdict, so the brief's definition is used here,
a cold rebuild plus decode on an idle engine, and both are reported.

| robot deadline | feasible, cold rebuild + decode | feasible, committed formula | history-token threshold, with decode |
|---|---|---|---|
| 5.0 s | **70 of 70** (1.000) | 70 of 70 | **19,500** |
| 4.0 s | 68 of 70 (0.971) | 58 of 70 | 17,693 |
| **3.0 s** | **48 of 70 (0.686)** | 42 of 70 | **13,193** |
| 2.5 s | 42 of 70 (0.600) | 37 of 70 | 10,943 |

The 5 s threshold comes out at 19,500 tokens with decode and 19,479 under the committed formula,
which confirms the brief's recollection of about 19.4k. **At 3 s the threshold falls to 13,193 tokens
and 22 of the 70 questions become infeasible cold even on an idle engine.** That is the number that
matters for redefining D133's headline: the feasible denominator would shrink from 70 to 48, so a
0.9 bar over feasible questions at 3 s is a bar over a two-thirds subset chosen by history length.

Adding decode moves the threshold by about 1,700 tokens at 3 s, which is why it cannot be left out
at this deadline even though it is nearly irrelevant at 5 s.

### 19.4 Warm-ahead at 3 s, from the section 15 and 16 simulation

MODELLED, with contention charged to the same GPU and the W2 discipline (warm only in spare
capacity). Robot questions on time of 65, 16 devices.

| capacity | P0 (as run) | P1 (warm all, LRU) | P2 (hazard) | P3 (oracle) |
|---|---|---|---|---|
| 1.00x committed | **25** (43 at 5 s) | **65** | **65** | 65 |
| 0.50x | 25 (43) | 51 (56) | 62 (63) | 65 |
| 0.25x | 25 (43) | 34 (47) | 41 (49) | 65 |

**At the committed capacity, warming ahead absorbs the 3 s deadline completely: P1, P2 and P3 all
reach 65 of 65, the same as at 5 s, while P0 falls from 43 to 25.** The deadline costs 18 of 65
questions if nothing is warmed and nothing at all if everything is. Under memory pressure it bites:
at 0.5x the tightening costs P1 five questions and P2 one, and at 0.25x it costs P1 thirteen and P2
eight.

So the simulation and 19.2 agree from different directions. The gap between what the arms achieve at
3 s, 0.33 at best, and what is achievable, 65 of 65, is **warming**, not the deadline.

**One inert switch caught before it was reported.** The first run of this at 3 s returned numbers
IDENTICAL to 5 s at every capacity and policy. That is the signature of a switch that never reached
a decision, not of a deadline that costs nothing, and it was: the trace records `deadline_s = 5.0` on
every robot question, and the model read `r.get("deadline_s") or ROB_L`, so the override was never
consulted. The override is explicit now and the table above is from the fixed run. Had the first
result been reported it would have been a null from an absent link, which CLAUDE.md names directly.

### 19.5 Answer length, and why decode matters at 3 s

A robot answer is **a single multiple-choice letter** (`cloud_payload.cloud_letter`: B, E and so on),
and the realised output is **2 tokens** in every committed cell against a committed cap of 512, so
the cap has never bound. That is P20.

Two tokens is not free, because decode time is set by how busy the engine is, not by how many tokens
are emitted (18.7.2). Measured on this grid, robot decode against the number of requests overlapping
its decode window:

| overlapping requests | n | decode p50 |
|---|---|---|
| 0 to 3 | 11 | **0.0242 s** |
| 3 to 6 | 37 | 0.1054 s |
| 6 to 12 | 164 | 0.2421 s |
| 12 to 25 | 32 | 0.3448 s |
| 25 to 45 | 48 | 0.7986 s |
| 45 and above | 139 | **1.4025 s** |

So the same two-token answer costs 0.024 s on an idle engine and 1.40 s in a crowd, a **58-fold**
range. At a 5 s deadline that spread is 28 percent of the budget at worst; **at 3 s it is 47
percent**, and on the actual misses decode was 1.086 s at the median, more than a third of the whole
3 s budget spent after the first token was already in hand. That is why decode belongs in the
feasibility rule at this deadline and why the answer format, not just the history, would need
re-benchmarking before a 3 s bound is adopted.

## 20. The completion headline on the POST-FIX cells (A6000, 2026-11-20, user request)

Section 18.3 scored the pre-fix cells for every arm, because `frozen_headline` built the exact cell
name. On the user's instruction it now scores **post-fix cells for eco-llm and hybrid-F-lhreq**,
which were redone after the RECENT-send fix, while **b7 and mooncake are unchanged** (they have no
post-fix cells) and **hybrid-F6-lhreq stays pre-fix and labelled**, since D145 ruled it is not
redone. `FROZEN_HEADLINE_CELLS=prefix` reproduces 18.3 for comparison.

### 20.1 The headline moves a long way, and on the ALL-questions basis most of all

Completion delivery, 16 devices, seeds 0, 4, 5, 6.

| arm | cells | robot feasible, pre to post | robot ALL, pre to post | SS, pre to post | minus b7, post |
|---|---|---|---|---|---|
| b7-edf-feasibility | pre, unchanged | 0.6087 | 0.4719 | 0.8934 | reference |
| mooncake | pre, unchanged | 0.6087 | 0.4719 | 0.8948 | [-0.0435, +0.0435] |
| hybrid-F6-lhreq | pre, not redone | 0.8841 | 0.6854 | 0.9481 | [+0.1739, +0.3913] |
| eco-llm | **POST** | 0.5652 to **0.6087** | 0.4382 to **0.6742** | 0.8128 to **0.8920** | [0.0, 0.0] |
| hybrid-F-lhreq | **POST** | 0.9565 to **0.9710** | 0.7416 to **0.9551** | 0.9600 to **0.9811** | **[+0.2464, +0.4783]** |

**The RECENT-send fix is worth far more on the ALL-questions basis than on the feasible one**: it
moves hybrid-F by 1.5 points on feasible questions and by **21.4 points** on all of them, and
eco-llm by 4.4 and **23.6** points respectively. That is what the fix should do. The pre-fix defect
sent the whole history while charging the RECENT price, so the questions it hurt most were the ones
whose histories were too long to be feasible at all, which sit outside the feasible denominator and
only show up in the all-questions column.

**Post-fix hybrid-F reaches 0.9551 robot on time over ALL robot questions**, which clears a 0.9 bar
on the harder of the two denominators. No arm had previously cleared 0.9 on all questions under any
delivery rule.

One oddity recorded rather than smoothed: eco-llm's post-fix difference against b7 over feasible
questions is **[0.0, 0.0]**, a degenerate interval, because post-fix eco-llm hits exactly the same 42
of 69 feasible questions b7 does. Every bootstrap resample therefore gives the same difference. It is
a real coincidence of outcome sets, not a computation failure, and it should not be read as a
confidence interval in the usual sense.

### 20.2 The 18.7 mechanism on the post-fix cells: concurrency still dominates, and representation acts through it

Robot requests, p50, four seeds:

| arm and cells | n | prompt tokens | decode | overlapping requests at decode |
|---|---|---|---|---|
| b7, pre (unchanged) | 69 | 9,573 | 1.1536 s | 50 |
| mooncake, pre (unchanged) | 69 | 9,573 | 1.1566 s | 51 |
| hybrid-F6, pre (not redone) | 86 | 12,228 | 0.2501 s | 9 |
| eco-llm, pre | 86 | 12,228 | 1.3397 s | 61 |
| **eco-llm, POST** | 87 | **8,210** | **0.9743 s** | **42** |
| hybrid-F, pre | 87 | 12,231 | 0.2532 s | 9 |
| **hybrid-F, POST** | 88 | **8,210** | **0.1376 s** | **8** |

**18.7's conclusion holds post-fix and is strengthened by the cleanest comparison available.**
Post-fix, eco-llm and hybrid-F send prompts of **identical** median length, 8,210 tokens, on the same
questions. Their decode differs **sevenfold**, 0.9743 s against 0.1376 s, and their overlap at decode
differs **fivefold**, 42 against 8. Prompt length is held constant by construction here and the
decode difference survives intact, so concurrency is the mechanism and length is not.

**But the fix also shows how representation acts: through occupancy, not directly.** Cutting the
prompt by 33 percent cut eco-llm's overlap by 31 percent, from 61 to 42, and its decode by 27
percent. A shorter prompt spends less time in flight, so it contributes less to the crowd that every
other request decodes into. For hybrid-F the same 33 percent cut moved overlap only from 9 to 8,
because it had little crowd to cut, yet its decode still halved, from 0.2532 to 0.1376 s.

So the two accounts are not rivals. Representation is a lever **on** concurrency, strong where an arm
is contributing to its own congestion and weak where it is not, and concurrency is what decode
actually reads. That is a better statement than either 18.4's retracted claim or 18.7's replacement
taken alone, and it is only visible because the post-fix cells hold prompt length constant across
two arms with very different release timing.

### 20.3 What this does not change

Sections 18.1 and 18.2 stand: the delivery stamp was first-token based in all 40 runs, and completion
flips 132 of 880 robot and 217 of 14,502 single-shot outcomes to late. Section 19's deadline sweep
used pre-fix cells for every arm, so its 3 s table understates the two redone arms; the sweep is
worth re-running on post-fix cells, and the direction is known from 20.1, both would improve.

## 21. The deadline sweep on post-fix cells, with robot ACCURACY beside on-time (A6000, 2026-11-20)

Section 19 re-run on post-fix cells for eco-llm and hybrid-F-lhreq (pre-fix for b7, mooncake and
hybrid-F6, which is not redone), with the column the user asked for: **robot accuracy**, scored as
the cloud's own answer when it arrives on time and the device's answer otherwise. A release made as
RECENT is scored as RECENT automatically, because the cloud letter actually produced is compared to
the gold letter and no accuracy table is consulted. `DEADLINE_SWEEP_CELLS=prefix` reproduces
section 19. Still re-scored with decisions made under 5 s.

### 21.1 On time and accuracy rank the arms differently

| arm | seeds | n | 2.5 s | 3 s | 4 s | 5 s |
|---|---|---|---|---|---|---|
| **hybrid-F-lhreq** on time | 0,4,5,6 | 89 | 0.4607 | **0.5281** | 0.7528 | **0.9551** |
| hybrid-F-lhreq accuracy | | 89 | 0.2809 | **0.3034** | 0.4157 | 0.4831 |
| **eco-llm** on time | 0,4,5,6 | 89 | 0.3708 | **0.4270** | 0.5056 | 0.6742 |
| eco-llm accuracy | | 89 | 0.2584 | **0.2584** | 0.2921 | 0.3708 |
| **hybrid-F6-lhreq** on time | 0,4,5,6 | 89 | 0.1573 | 0.2809 | 0.4831 | 0.6854 |
| hybrid-F6-lhreq accuracy | | 89 | 0.2697 | 0.3371 | 0.4494 | **0.4944** |
| **b7-edf-feasibility** on time | 0,4,5,6 | 89 | 0.1910 | 0.2247 | 0.3146 | 0.4719 |
| b7-edf-feasibility accuracy | | 89 | 0.3034 | **0.3146** | 0.3483 | 0.4270 |
| **mooncake** on time | 0,4,5,6 | 89 | 0.1685 | 0.2360 | 0.3034 | 0.4719 |
| mooncake accuracy | | 89 | 0.3146 | 0.3146 | 0.3371 | 0.4382 |
| edf on time / accuracy | 4,5 | 45 | 0.1333 / 0.3333 | 0.1556 / 0.3556 | 0.2000 / 0.3556 | 0.2667 / 0.3556 |
| llf on time / accuracy | 4 | 20 | 0.2500 / 0.3500 | 0.3500 / 0.4000 | 0.3500 / 0.4000 | 0.5000 / 0.5000 |
| always-cloud-fcfs on time / accuracy | 4 | 20 | 0.2500 / 0.4000 | 0.3500 / 0.4000 | 0.3500 / 0.4000 | 0.5000 / 0.5000 |

**The two columns do not agree, and at 3 s they nearly invert.** On time, hybrid-F leads at 0.5281
and b7 is next to last at 0.2247. On accuracy at the same deadline, **b7 (0.3146) is AHEAD of
hybrid-F (0.3034)**, and eco-llm, second on time at 0.4270, is **last on accuracy at 0.2584**.
hybrid-F delivers 2.3 times b7's on-time rate at 3 s and ends with slightly fewer correct answers.

The post-fix gain is also almost entirely an on-time gain: hybrid-F's 3 s on-time rose from 0.3258
pre-fix to 0.5281 post-fix, while at 5 s its accuracy is 0.4831 against hybrid-F6's **0.4944**, and
hybrid-F6 is the arm that was NOT redone.

### 21.2 Why: the extra on-time answers are RECENT, and RECENT is almost never right

Cloud answers delivered on time at 3 s, split by the representation actually sent:

| arm | on-time cloud answers | D2 | D2 correct | RECENT | **RECENT correct** |
|---|---|---|---|---|---|
| b7-edf-feasibility | 20 | 20 | 0.650 | 0 | n/a |
| eco-llm, post-fix | 38 | 21 | 0.619 | 17 | **0.118** |
| hybrid-F-lhreq, post-fix | 47 | 29 | 0.621 | 18 | **0.111** |

**A full-history answer is right about 62 to 65 percent of the time and a RECENT answer about 11
percent.** b7 sends D2 only, so every on-time answer it delivers is a good one. The post-fix hybrids
buy their extra on-time answers by sending RECENT, and those answers are right one time in nine.

So the RECENT-send fix did exactly what it was built to do, sending what it charges for, and the
consequence is that **meeting the deadline and answering the question have come apart**. An arm can
raise on time by sending less evidence, and less evidence answers the question wrongly. The 11.1 and
11.8 percent measured here sit right on D143's committed DEV figure for cloud RECENT, 10.714
percent, so this is the expected behaviour of that representation rather than a surprise about these
runs.

One number in the record does not match this. D151 (3) describes RECENT as "rarely worth it on
LH-REQ: 26 % vs device 25 %", which is a different pair of quantities from D143's committed cloud
D2 25.000, cloud RECENT 10.714 and device 10.714 on DEV. Measured on EVAL here, cloud RECENT is
0.111 to 0.118 and cloud D2 is 0.619 to 0.650, so the gap between the two representations is far
wider than "26 against 25" suggests. Flagged rather than reconciled, since both figures are the
user's.

### 21.3 What this says for the headline and for v2

**On time alone is the wrong headline for the robot type**, and this sweep is the clearest statement
of it the study has produced: the ranking by on time and the ranking by accuracy disagree at every
deadline, and at 3 s they nearly invert. A policy tuned on on time will prefer RECENT, because
RECENT is cheap and lands inside the deadline, and it will be wrong nine times in ten when it does.

This bears directly on D149. Its clause (2) already says value within a type must decide full
history against RECENT by "accuracy x P(on time)", and 21.2 is the measured version of exactly that
product: 0.62 x P(on time with D2) against 0.11 x P(on time with RECENT). On these questions RECENT
wins that product only when P(on time with D2) falls below about 18 percent of P(on time with
RECENT), which at 5 s it does not. **D151 (3)'s judgement that RECENT is rarely worth it on LH-REQ
is confirmed, and by a wider margin than the figure quoted there.**

It also sharpens D147's pending item. If the D133 headline moves to all robot questions, it should
carry the accuracy column with it, because the on-time column alone would rank an arm that answers
wrongly above one that answers correctly and late.

### 21.4 A regeneration check worth recording

Only seed 4's trace is committed, so gold letters and device correctness for seeds 0, 5 and 6 are
regenerated locally. That is safe here and the check is explicit: regenerating seed 4 reproduces the
committed `device_answers.jsonl` sha256 **exactly**. The regenerated `trace.jsonl` does NOT match,
and the reason is known and confined: the only differing field is `frame_bytes` on the 13,193
monitor records, where a measured run carries per-frame bytes from the encode manifest and a flash
regeneration falls back to the E10a median, which is D103 (h). Robot question ids, history tokens,
gold letters and device answers are identical.

So a locally regenerated trace is sound for robot-side quantities and **must never be used for an
uplink or dashcam quantity**. That applies to `frozen_headline.local_trace` as well, which is used
for feasibility and reads only history tokens.

## 22. Pre-registration for the 3 s handful (A6000, 2026-11-20, written BEFORE the cells land)

The H100 runs ten arms live at a 3 s robot deadline at 16 devices, seeds 4, 5 and 6. This section is
written before any of those cells exist, so the comparison below cannot be chosen after seeing it.

### 22.1 The confound, named first

`hybrid-F-lhreq-noc3` runs live at 3 s. **`hybrid-F-lhreq` itself is not in the handful**, so its 3 s
live twin does not exist until the rest-of-sweep pass about ten hours later. Until then the only
available comparison is against the OFFLINE 3 s re-score of hybrid-F's post-fix cells, which ran
live at 5 s. Those are not the same condition: hybrid-F's deferrals and rejections were decided
against a 5 s bound, so a difference between it and noc3 mixes the C3 change with the change in what
the arm was planning for.

**That confound is measurable rather than arguable, and it costs nothing to measure.** b7, eco-llm,
mooncake, edf and llf are in BOTH the handful and the offline re-score. Comparing live-at-3 s with
offline-rescored-at-3 s for the SAME arm isolates exactly one thing: what planning for 3 s does that
scoring at 3 s does not. b7 is the handful's first cell, so the estimate arrives before anything else.

### 22.2 The offline 3 s baseline on the handful's own support

Seeds 4, 5 and 6, 65 robot questions, completion delivery, post-fix cells where they exist. These are
the numbers the live cells will be compared against.

| arm | on time | **correct delivered** |
|---|---|---|
| hybrid-F-lhreq | 0.5385 | 0.2769 |
| eco-llm | 0.4462 | 0.2462 |
| hybrid-F6-lhreq | 0.3077 | 0.3385 |
| mooncake | 0.2462 | 0.3077 |
| b7-edf-feasibility | 0.2308 | **0.3077** |
| edf | 0.1556 | 0.3556 |
| llf, seed 4 only | 0.3500 | 0.4000 |
| always-cloud-fcfs, seed 4 only | 0.3500 | 0.4000 |

On this support the section 21 pattern holds and is if anything sharper: **b7 delivers more correct
answers than hybrid-F (0.3077 against 0.2769) while hybrid-F more than doubles its on-time rate.**

### 22.3 What I predict, so it can be wrong

1. **`hybrid-F-lhreq-noc3` loses on time against hybrid-F's 0.5385 and gains on correct delivered
   against its 0.2769.** It should land near b7's 0.3077 or above, because removing the RECENT
   fallback stops converting a device answer worth about 25 percent into a cloud answer worth about
   11 percent. If noc3 does NOT gain on correct delivered, section 21's diagnosis is wrong and the
   RECENT fallback was not what moved the headline.
2. **The control, b7 live at 3 s against b7 offline-rescored at 3 s, agrees within a few questions
   of 65.** b7 declines rather than defers, so planning for a shorter deadline should change little
   for it. If they differ substantially, the offline re-score is not a usable stand-in for a live
   3 s run, and every comparison in 22.2 needs its own live twin before it is read.
3. **edf and llf change most between offline and live.** They defer until their own builds complete,
   so a 3 s bound should change their deferral behaviour more than any other arm's. That makes them
   the upper bound on the confound and b7 the lower bound.

If prediction 2 fails, the right response is to ask for hybrid-F-lhreq at 3 s in the handful rather
than to read 22.2 as if it were live. That request is the user's to make, not mine or the H100's.

---

## 23. D155 (3): correct answers delivered BY THE DEADLINE, re-scored offline (A6000, 2026-11-20)

**The ruling.** D155 (3) amends D152 (1). The robot headline becomes **correct answers delivered by
the deadline, from either source**: the cloud's answer if it is delivered within the deadline,
otherwise the **device's answer if the device's answer also arrives within the deadline**, otherwise
no answer and the question is a miss. The D152 (1) behaviour, which credits a device answer
regardless of when it lands, stays and is reported **beside** it as **correct answers delivered at
any time**. The two are never mixed in one column or one sentence. The on-time-only tables of
sections 14, 18, 20 and 21 are untouched and stay labelled.

Nothing live was run. Nothing touched the H100 or the Orin. Everything below is an offline re-score
of committed cells on flash.

### 23.1 The device-latency source, stated before any number

This is the load-bearing disclosure, so it comes first.

The re-score used **the per-question `device_latency_s` field already committed in each cell's
`device_answers.jsonl`**. For a robot recall question the trace generator writes that field as
`data_sources.device_recall_latency_s(history_tokens)` (`fleet/trace.py:573`), which is **D87's
ORIN2 in-process harness cost**: 0.146 s at 11k history tokens and 0.225 s at 28k, linearly
interpolated between and **clamped** outside. Observed across the four committed seeds at n=16 the
values run **0.146 s to 0.225 s**, with the floor-pile at 0.146 s produced by the clamp.

**What was NOT used.** The device's own answer latency on the 97 LH-REQ questions, TTFT median
3.296 s and end-to-end median 6.651 s, is **not wired anywhere**. D155 (1) rules those the cold
re-send path and D61 (b) classifies the resend path as an API artifact and not the device baseline.
They appear in `scorer/score.py` only inside a comment that says they must not be used, and in the
`excluded` string of `device_delivery_rule()`, which every output now carries.

**Could a device answer be late under the source actually used? No, not once.** The committed robot
deadline in every one of these traces is **5.0 s** (`deadline_s`, read from the question and never
from a literal). A device answer is late iff `device_wait_s + device_latency_s > L`, which at
`device_wait_s = 0` needs `L < 0.225 s`. The headroom is **22.2x** at the committed maximum, and
still 11.1x at the D147 2.5 s end of the deadline sweep. **Device answers late: 0 of 89, in every
arm, in every cell.** This is the central fact of section 23 and the reason the headline does not
move. It is reported as a property of the latency source, not as a finding about any policy.

**The slot, so the measured warm value drops in.** `LIVE2_DEVICE_LATENCY` takes `trace` (the
default above) or `measured:<path to json>`, a table of measured warm per-question device latencies
keyed by `question_id` or `opportunity_id`. When StudyORIN-REC's warm path lands it is pointed at
through that variable and **nothing in either scorer changes**. `LIVE2_DEVICE_WAIT_S` exists beside
it for a cascade arm whose device waits on the cloud before starting. Both are read **once, at
module level, in `scorer/score.py` only**, and `frozen_headline.py` **imports** `device_within` and
`device_delivery_rule` from it rather than reading an environment variable of its own. This is
deliberate: the D146 `DELIVERY` switch was module-level in one scorer and local in the other, the
two disagreed, and it had to be hoisted by hand. There is now one definition and one read.

### 23.2 Mechanism verification, completed before the sweep

**Step 0, what would invalidate this run.** Is the comparator about to change? No: D155 (3) fixes
both columns and the on-time tables are frozen. Does a run I depend on key into the analysis? Yes,
the committed `frozen_headline_n16_4seed_d152.json` is the bar the any-time column must reproduce,
so it is checked as a positive control rather than assumed. **Does the mechanism have a reachable
path at this size and in this regime?** This is the question that mattered, it was asked before the
sweep, and the answer was **no**: 0.225 s against a 5.0 s deadline. The run went ahead because the
ruling is a scoring rule and the user asked explicitly whether a device answer could be late at
all, but the null was predicted before it was produced, not explained after.

**Step 1, the causal chain.** If a device answer takes a non-zero time to produce, then an
opportunity whose cloud answer misses the deadline is credited under D152 (1) with an answer that
may itself arrive after the deadline; charging the device its own latency removes that credit on
every question where the device is also late, which lowers the headline for whichever arms lean
hardest on the device fallback, and because arms lean on the fallback by different amounts (b7 and
mooncake fall back on roughly half their questions, hybrid-F on few), the ranking between arms can
change. Every link is in D152 (1), D155 (3) and D1 (the device always has an answer).

**Step 2, each link instantiated.**

| causal link | implementing quantity | value / range in this run | varies as expected? | evidence |
|---|---|---|---|---|
| device answer takes non-zero time | `device_answers.jsonl::device_latency_s` | 0.146 to 0.225 s over 89 questions, 11 distinct values at seed 4 | yes, non-zero and varies with `history_tokens` | `rows[].device_latency_s` in `d155_device_delivery_proofs.json` |
| that time is compared against the deadline | `score.device_within` | read at `score.py::_standing_by_deadline` and at `frozen_headline.py::run_flags`, both of which change a decision | **yes as code, NO as outcome** | the probe below moves 9 of 20 decisions; the committed source moves 0 |
| late device answers lose their credit | `standing_correct_by_deadline`, `source_by_deadline == "none"` | **0 of 89 questions**, every arm | **no, CONSTANT in this run** | `device_answers_late: 0`, `n_no_answer_by_deadline: 0` |
| the lost credit changes the arm ranking | pooled by-deadline minus any-time per arm | **0.0000 for all five arms** | **no, CONSTANT** | table 23.3 |

Links 3 and 4 are **CONSTANT**. Under the mandatory protocol that is a stopping condition for a
sweep that tests a causal claim, and it is recorded as one. It is **not** a stopping condition for
this task, because the task is to implement a scoring rule and report what it does to committed
numbers, and the user asked in advance whether the device could be late at all. The constant is the
answer to that question, and section 23.4 classifies it rather than reporting it as a finding.

**Step 2b, does the switch reach a decision?** Yes as a switch, no on this data. Both conditions
were run on one cell (`b7-edf-feasibility_n16_s4_1200s_h27_3t`) and the decision logs diffed. With
the committed source the by-deadline and any-time decisions are **identical on all 20 questions**.
With an artificial 9.999 s device latency injected through the `measured:` slot, **9 of 20
decisions differ**, the first being `opp0002118`, which moves from `device` to `none`, and the
by-deadline accuracy moves 0.5000 to 0.4000 while any-time stays at 0.5000. The switch arrives at
the object under test with its declared type and value and it changes an outcome. The 9.999 s is a
**switch proof, not a device-latency claim**, and is deliberately not the number D155 (1) excludes.

**Step 3, one traced unit.** The full 20-question trace for that cell is committed in
`results/orchestration/live2/frozen_test/d155_device_delivery_proofs.json` under
`step3_one_traced_unit`, with per question: `t_opportunity`, `t_delivered`, the cloud latency, the
deadline, `device_latency_s`, `device_on_time`, both sources, the cloud letter, the gold letter and
both correctness columns. Four lines of it, hand-checkable:

| opp | t_opp | t_del | cloud lat | dev lat | deadline | src any-time | src by-deadline | any | by-deadline |
|---|---|---|---|---|---|---|---|---|---|
| opp0000906 | 94.96 | 97.42 | 2.459 | 0.146 | 5.0 | cloud | cloud | True | True |
| opp0002118 | 200.42 | 206.16 | **5.746** | 0.149 | 5.0 | device | device | False | False |
| opp0003438 | 315.86 | none | none | 0.189 | 5.0 | device | device | True | True |
| opp0007718 | 689.20 | 696.12 | **6.922** | 0.179 | 5.0 | device | device | False | False |

`opp0002118` and `opp0007718` are exactly the shape the amendment was written for: the cloud blew
the 5 s deadline, so the device stands in. Under D152 (1) it stands in unconditionally. Under
D155 (3) it stands in because 0.149 s and 0.179 s are inside 5.0 s. Both answers happen to be
wrong, so neither column scores them, but the branch taken is the amended one.

**Step 4, negative control.** Two directions, both run on the same single cell.

- *Mechanism disabled:* with the committed latencies the mechanism is unreachable and the
  by-deadline column collapses exactly onto the any-time column, 0.5000 on both. That is the null.
- *Mechanism forced reachable:* with the 9.999 s probe the by-deadline column moves to 0.4000 and
  the any-time column does not move at all. **The result does change when the mechanism can fire**,
  so the collapse above is a property of the latency values and not a dead switch, a write-only
  field or a discarded channel.

**Step 5, alternative explanations for the headline result.** The headline result is "the ranking
does not change". It could be produced by (a) device answers genuinely always arriving in time
[the claimed mechanism], or (b) the by-deadline column never being computed, the device branch
never being reached, or the new field being written and never read [plumbing]. These are
distinguished by the Step 2b diff: under (b) the probe would also move nothing, and it moves 9 of
20 decisions. A third possibility, (c) the device latency source being wrong in a way that
understates it, is **not** ruled out by anything here and is the live risk; it is section 23.5.

### 23.3 The re-scored table: every committed cell x arm

Cells: the frozen grid at n=16, seeds 0, 4, 5 and 6, common support, completion delivery (D146),
post-fix cells for eco-llm and hybrid-F-lhreq and pre-fix for the other three (D145). Robot
deadline 5.0 s from the question. Denominator for both correctness columns is **all** robot
questions, because a question neither side answers in time stays in it as a miss.

**Per cell, cell x arm.**

| arm | seed | n | on-time | correct delivered BY DEADLINE | correct delivered ANY TIME | device answers late |
|---|---|---|---|---|---|---|
| b7-edf-feasibility | 0 | 24 | 10 (0.4167) | 12 (0.5000) | 12 (0.5000) | 0 |
| b7-edf-feasibility | 4 | 20 | 11 (0.5500) | 10 (0.5000) | 10 (0.5000) | 0 |
| b7-edf-feasibility | 5 | 25 | 11 (0.4400) | 11 (0.4400) | 11 (0.4400) | 0 |
| b7-edf-feasibility | 6 | 20 | 10 (0.5000) | 5 (0.2500) | 5 (0.2500) | 0 |
| eco-llm | 0 | 24 | 15 (0.6250) | 11 (0.4583) | 11 (0.4583) | 0 |
| eco-llm | 4 | 20 | 16 (0.8000) | 8 (0.4000) | 8 (0.4000) | 0 |
| eco-llm | 5 | 25 | 14 (0.5600) | 9 (0.3600) | 9 (0.3600) | 0 |
| eco-llm | 6 | 20 | 15 (0.7500) | 5 (0.2500) | 5 (0.2500) | 0 |
| mooncake | 0 | 24 | 11 (0.4583) | 12 (0.5000) | 12 (0.5000) | 0 |
| mooncake | 4 | 20 | 11 (0.5500) | 10 (0.5000) | 10 (0.5000) | 0 |
| mooncake | 5 | 25 | 11 (0.4400) | 11 (0.4400) | 11 (0.4400) | 0 |
| mooncake | 6 | 20 | 9 (0.4500) | 6 (0.3000) | 6 (0.3000) | 0 |
| hybrid-F-lhreq | 0 | 24 | 23 (0.9583) | 13 (0.5417) | 13 (0.5417) | 0 |
| hybrid-F-lhreq | 4 | 20 | 20 (1.0000) | 11 (0.5500) | 11 (0.5500) | 0 |
| hybrid-F-lhreq | 5 | 25 | 23 (0.9200) | 12 (0.4800) | 12 (0.4800) | 0 |
| hybrid-F-lhreq | 6 | 20 | 19 (0.9500) | 7 (0.3500) | 7 (0.3500) | 0 |
| hybrid-F6-lhreq | 0 | 24 | 15 (0.6250) | 13 (0.5417) | 13 (0.5417) | 0 |
| hybrid-F6-lhreq | 4 | 20 | 13 (0.6500) | 11 (0.5500) | 11 (0.5500) | 0 |
| hybrid-F6-lhreq | 5 | 25 | 19 (0.7600) | 13 (0.5200) | 13 (0.5200) | 0 |
| hybrid-F6-lhreq | 6 | 20 | 14 (0.7000) | 7 (0.3500) | 7 (0.3500) | 0 |

**Pooled over the four seeds, with paired-by-seed bootstrap CIs, B = 10,000.**

| arm | on-time, feasible pool | on-time, all questions | correct delivered BY DEADLINE (headline) | correct delivered ANY TIME (beside it) | by-deadline minus any-time |
|---|---|---|---|---|---|
| b7-edf-feasibility | 42/69 = 0.6087 [0.4928, 0.7246] | 42/89 = 0.4719 | **38/89 = 0.4270** [0.3258, 0.5281] | 38/89 = 0.4270 [0.3258, 0.5281] | 0.0000 |
| eco-llm | 42/69 = 0.6087 [0.4928, 0.7246] | 60/89 = 0.6742 | **33/89 = 0.3708** [0.2697, 0.4719] | 33/89 = 0.3708 [0.2697, 0.4719] | 0.0000 |
| mooncake | 42/69 = 0.6087 [0.4928, 0.7246] | 42/89 = 0.4719 | **39/89 = 0.4382** [0.3371, 0.5393] | 39/89 = 0.4382 [0.3371, 0.5393] | 0.0000 |
| hybrid-F-lhreq | 67/69 = 0.9710 [0.9275, 1.0] | 85/89 = 0.9551 | **43/89 = 0.4831** [0.3820, 0.5843] | 43/89 = 0.4831 [0.3820, 0.5843] | 0.0000 |
| hybrid-F6-lhreq | 61/69 = 0.8841 [0.7971, 0.9565] | 61/89 = 0.6854 | **44/89 = 0.4944** [0.3933, 0.5955] | 44/89 = 0.4944 [0.3933, 0.5955] | 0.0000 |

Paired differences against b7, identical under both rules: eco-llm [-0.1124, -0.0112], mooncake
[0.0000, 0.0337], hybrid-F [-0.0225, 0.1461], hybrid-F6 [0.0112, 0.1348].

### 23.4 Where the ranking changes, which is the whole point of the amendment

**It changes nowhere.** Under the device-latency source actually available, the by-deadline column
and the any-time column are **equal question by question, in all 89 questions, in all five arms, in
all four cells**. Not close, not equal to three decimals: the same integer hit counts. Every
ordering, every paired interval and every verdict is therefore identical under the two rules, and
the amendment changes no conclusion in sections 14, 18, 20, 21 or 22.

**Classified under Rule 2 this is INCONCLUSIVE, sub-case UNEXERCISED**, and it must not be read as
a real negative. The mechanism is present in both scorers, reachable, and demonstrably able to move
9 of 20 decisions on one cell, but **no condition in these runs reaches it**: the device-latency
source tops out at 0.225 s against a 5.0 s deadline, 22.2x of headroom. It is not "the device is
never late"; it is "under D87's ORIN2 in-process cost the device is never late". The precedent the
project keeps for exactly this shape is E36, E36b and E36c, where a quantity that was correctly and
consistently zero passed every consistency check, and the only thing that caught it was asking
whether the mechanism had a reachable path.

What the amendment has nevertheless done, and this is real: it removes a way the headline could
have over-credited the device without anyone noticing, and it puts the device's latency on the
critical path of the metric, where a measured warm value will now be felt. The ordering being
unchanged **today** is a fact about today's latency source and nothing more.

**The register.** "0 device answers late in 89 questions" is an **observed count** over the
committed cells at n=16 on seeds 0, 4, 5 and 6, not a **constructed bound** over the design space.
The bound that would generalise it is the separate statement "a device answer cannot be late while
`L >= 0.225 s`", which is a construction from the clamp ceiling and holds only for this source.

### 23.5 Results consistency check, all seven points, recorded before the conclusions above

**1. Cross-check against committed measurements.** Two positive controls, two cell selections.

| quantity | this run | prior run | source of prior | ratio | agree |
|---|---|---|---|---|---|
| b7 correct delivered, any time, pooled | 0.4270 (38/89) | 0.4270 (38/89) | `frozen_headline_n16_4seed_d152.json` | 1.000 | agree |
| eco-llm correct delivered, any time | 0.3708 (33/89) | 0.3708 (33/89) | same | 1.000 | agree |
| mooncake correct delivered, any time | 0.4382 (39/89) | 0.4382 (39/89) | same | 1.000 | agree |
| hybrid-F correct delivered, any time | 0.4831 (43/89) | 0.4831 (43/89) | same | 1.000 | agree |
| hybrid-F6 correct delivered, any time | 0.4944 (44/89) | 0.4944 (44/89) | same | 1.000 | agree |
| b7 robot feasible on-time, completion, pre-fix | 0.6087 | 0.6087 | D146 design-log row | 1.000 | agree |
| mooncake feasible on-time, completion, pre-fix | 0.6087 | 0.6087 | D146 | 1.000 | agree |
| eco-llm feasible on-time, completion, pre-fix | 0.5652 | 0.5652 | D146 | 1.000 | agree |
| hybrid-F6 feasible on-time, completion, pre-fix | 0.8841 | 0.8841 | D146 | 1.000 | agree |
| hybrid-F feasible on-time, completion, pre-fix | 0.9565 | 0.9565 | D146 | 1.000 | agree |
| hybrid-F minus b7 interval, pre-fix | [+0.2319, +0.4638] | [+0.2319, +0.4638] | D146 | 1.000 | agree |
| device recall latency at 11k / 28k tokens | 0.146 / 0.225 s | 0.146 / 0.225 s | D87 via `data_sources.ORIN_RECALL_TTFT_S` | 1.000 | agree |

No disagreement anywhere, let alone 2x. The pre-fix row set was produced by re-running with
`FROZEN_HEADLINE_CELLS=prefix` and is committed as `frozen_headline_n16_4seed_d155_prefix.json`;
the default run uses the D145 post-fix selection, which is why eco-llm reads 0.6087 and hybrid-F
reads 0.9710 there and 0.5652 and 0.9565 in the pre-fix control. Same quantity, two cell
selections, both labelled, neither mixed.

**2. Physical plausibility, and this one is flagged.** Read as a prefill rate, the device latency
implies 11,146 tokens in 0.146 s, about **76,000 tok/s**, against a committed A6000 cold prefill of
about 7,100 tok/s. That is roughly 10.7x faster than the committed curve and would be a caching
artefact if it were a prefill. **It is not a prefill, and the register is the point.** D61 (b)
states that on the Orin the in-process path does not resend the image history, and that the model
work there is 0.13 to 0.19 s at 11k and 28k tokens; the 0.146 s is that incremental warm model
work on a context the process already holds, not the cost of building the context. The figure is
therefore not comparable to a cold-prefill curve and the 10.7x is not a discrepancy between two
measurements of the same thing. It is recorded here because the by-deadline column depends on this
number and a reader must know which path it describes. The cloud-side latencies are untouched by
this section and were plausibility-checked in section 18.

**3. Distribution sanity.** Device latency is not a constant where a distribution is expected: 11
distinct values over 20 questions at seed 4, ranging 0.146 to 0.211 s and monotone in
`history_tokens`. There is a visible pile at exactly 0.146 s, which is the **clamp** at or below
11k tokens and not short-circuiting; it is documented in `device_recall_latency_s` and reproduced
here. Per-seed ranges: seed 0 [0.146, 0.225], seed 4 [0.146, 0.2109], seed 5 [0.146, 0.2117],
seed 6 [0.146, 0.2092]. The **artefact-spread** check applies in reverse here and is the reason
section 23.4 is worded as it is: the by-deadline column is not a plausible spread that could be
mistaken for a measurement, it is an exact integer-for-integer copy of the any-time column, which
advertises what happened rather than hiding it. The **averaged-out-effect** check: there is no
stratum on which the effect is concealed, because `device_answers_late` is 0 in every cell, every
arm and every seed, not 0 on average.

**4. Definition audit.** `correct_answers_delivered_by_deadline`: cloud answer if
`t_delivered - t_opportunity <= L`, else device answer if `device_wait_s + device_latency_s <= L`,
else miss; denominator all robot questions; `L = 5.0 s` from the question's own `deadline_s`;
`device_wait_s = 0.0`. `correct_answers_delivered_any_time`: identical except the device branch is
unconditional; this is D152 (1) verbatim and its expression in `frozen_headline.py` is unchanged
character for character. "On time": delivered within the deadline by an HTTP 200 request (D144),
stamped at completion, prefill plus decode (D146). "Robot question": n = 89 pooled, 24 / 20 / 25 /
20 by seed, same opportunity ids across arms by the same trace. No name is used here with two
definitions; the two rules carry two distinct names with the suffixes `_by_deadline` and
`_any_time`, and the ambiguous bare name `correct_answers_delivered` has been **removed** from the
scorer's output so it cannot be picked up by accident.

**5. Claim linkage.** The headline bears on **C5** (joint representation x placement x timing beats
decomposed policies under a quality SLO), which is the accept/reject claim and is status untested.
Under both rules hybrid-F-lhreq at 0.4831 and hybrid-F6-lhreq at 0.4944 sit above b7 at 0.4270,
with hybrid-F6's interval against b7 at [0.0112, 0.1348] and hybrid-F's at [-0.0225, 0.1461]. This
section does **not** move C5 in either direction, because it changes no number; it changes the
definition under which the number will be read once a measured device latency exists. Nothing
measured here is scoped out by FORMULATION.md.

**6. Proxy validity.** `device_latency_s` is an explicit **proxy** for the device's warm
per-question answer latency. What it actually measures: D87's ORIN2 in-process harness cost at two
history sizes, 11k and 28k, **linearly interpolated and clamped** at every other size, so for 18 of
the 20 questions at seed 4 it is a derived value and not a measurement. Is it valid for the claim?
For the narrow claim "no device answer is late at a 5 s deadline" it is robust, because the
conclusion survives any value up to 5.0 s and the proxy's own measured endpoints are 22x below
that. For the **by-deadline column itself as a headline number** it is **not yet validated**, and
that column is marked **unvalidated pending StudyORIN-REC's measured warm per-question latency**.
The cold re-send proxy is rejected outright under D155 (1) and D61 (b) and is not used.

**7. Validate the control, not only the result.** The control arm is **b7-edf-feasibility**, and it
was checked against its own committed values before the comparison was read, not after. Its
any-time correct-delivered reproduces its committed 0.4270 at 38 of 89 exactly; its feasible
on-time reproduces 0.6087 at 42 of 69 exactly; its single-shot on-time reproduces 0.8934 at 1274 of
1426 and its dashcam all-meet 4 of 4. **Positive control:** D146's committed pre-fix completion
numbers are a known-good committed arm set, and all five of them plus the hybrid-F minus b7
interval [+0.2319, +0.4638] reproduce exactly from this modified scorer. A scorer that had broken
the committed path would have failed there; it did not, so the zero in section 23.4 is a property
of the data and not of a broken check. The impossible-success side was also watched: had the
by-deadline column come back **better** than any-time anywhere, that would have been impossible by
construction, since the by-deadline rule can only remove credit, never add it. It did not.

### 23.6 Files

| file | what |
|---|---|
| `experiments/orchestration/live2/scorer/score.py` | `DEVICE_LATENCY_SOURCE`, `DEVICE_WAIT_S`, `device_latency_s`, `device_within`, `device_delivery_rule`, `_standing_by_deadline`; `robot_value` gains the by-deadline fields; `robot_headline` metric is now `correct_answers_delivered_by_deadline` with `beside_it_any_time`; a `robot_standing_accuracy_by_deadline` interval beside the committed one |
| `experiments/orchestration/live2/frozen_headline.py` | imports the device rule from `score.py` rather than re-implementing it; two correctness columns, per cell and pooled, paired on the same bootstrap draw |
| `results/orchestration/live2/frozen_test/frozen_headline_n16_4seed_d155.json` | the re-score, D145 post-fix selection |
| `results/orchestration/live2/frozen_test/frozen_headline_n16_4seed_d155_prefix.json` | the pre-fix control that reproduces D146 |
| `results/orchestration/live2/frozen_test/d155_device_delivery_proofs.json` | Step 3 traced unit, Step 2b diff, Step 4 both controls |

### 23.7 What should happen next

1. When StudyORIN-REC's **measured warm per-question** device latency lands, point
   `LIVE2_DEVICE_LATENCY` at it and re-run exactly the two commands in 23.6. No code changes. If
   any measured warm latency exceeds the deadline, section 23.4's "changes nowhere" expires on the
   spot and the ranking must be re-read, because the arms lean on the device fallback by very
   different amounts: b7 and mooncake fall back on about half their questions, hybrid-F on 4 of 89.
   That asymmetry is where a ranking change would come from, and it is already visible in the
   on-time column.
2. Do **not** carry section 23.4 forward as "the deadline rule makes no difference". It makes no
   difference **at 0.146 to 0.225 s**. The sentence without that clause is the error this section
   exists to prevent.

## 24. The 3 s handful under D155 (3), and section 22's confound measured

**A6000, offline, CPU only.** `frozen_headline.py` extended to score a deadline family of cells
(`FROZEN_HEADLINE_SUFFIX=_L3`) and to regenerate the 3 s trace locally, which needs
`DS.ROBOT_DEADLINE_S` set before generation because `generate_trace` takes no deadline argument
(`run_live2_real.py:447` does the same thing). Output
`results/orchestration/live2/frozen_test/frozen_headline_n16_s4_d155_L3.json`.

### 24.1 The three cells the H100 scored before D155 landed, re-scored under D155

The H100's driver scored b7, eco-llm and mooncake at 3 s seed 4 BEFORE `8e1dbbb`, so their
`cell.json` carries D152's `correct_answers_delivered` rather than D155's by-deadline figure. D155 (3)
forbids mixing the two, so they are re-scored here from the committed run dirs.

| arm | by deadline | any time | on time | device answers late |
|---|---|---|---|---|
| b7-edf-feasibility | **8/20 = 0.4000** | 8/20 = 0.4000 | 7/20 = 0.35 | 0 |
| eco-llm | **6/20 = 0.3000** | 6/20 = 0.3000 | 15/20 = 0.75 | 0 |
| mooncake | **8/20 = 0.4000** | 8/20 = 0.4000 | 7/20 = 0.35 | 0 |
| edf | **6/20 = 0.3000** | 6/20 = 0.3000 | 4/20 = 0.20 | 0 |

**The two rules agree on every cell at the latency the scorer used. THAT COLUMN IS PROVISIONAL AND
THE CONCLUSION I FIRST DREW FROM IT WAS NOT SAFE.** The scorer's device latency is 0.146 to 0.225 s,
which is D87's ORIN2 IN-PROCESS harness, and D146 (2) replaces exactly that substitution. It cannot
establish that device answers arrive on time: it is the superseded number. I had just installed the
MEASURED device ACCURACY in the value table while leaving the superseded device LATENCY in the
scorer, which is the same split-source error in two halves of one pipeline.

Under the measured COLD re-send path (end to end 6.65 s) every device answer at a 3 s deadline would
be late and the by-deadline column would differ from any-time on every cell. D155 (1) rules that
cold path an API artefact per D61 (b), so it is not the baseline either. **The Orin's WARM
measurement decides, and until it is wired the by-deadline column here is PROVISIONAL.** When it
lands, every 3 s cell is re-scored with per-question measured device completion latency under both
rules, and the report states HOW MANY device answers flip.

**This is also a cross-validation of the offline path, and a strong one.** All four arms reproduce
the H100's live driver scores EXACTLY: b7 0.40 and 7 of 20, eco-llm 0.30 and 15 of 20, mooncake 0.40
and 7 of 20, edf 0.30 and 4 of 20. The trace was REGENERATED locally rather than read from the
H100's tree, and `local_trace`'s own control (the regenerated robot opportunity ids must equal the
ids the run's outcomes carry, or the run is skipped rather than scored on a guess) passed on all
four. An offline re-score matching a live driver to the question, on a regenerated trace, is the
check that licenses every other offline number in this report.

### 24.2 Section 22's confound, now measured at both ends

Section 22 predicted that the offline 3 s re-score of a 5 s cell would stand in for a live 3 s run,
with b7 the lower bound on the error and edf and llf the upper bound, because b7 declines while edf
and llf defer.

| arm | offline 3 s re-score (decisions made at 5 s) | live 3 s | difference |
|---|---|---|---|
| b7 | on time 0.3500, correct 0.4000 | on time 0.3500, correct 0.4000 | **0 questions** |
| edf | on time 0.2500, correct 0.3500 | on time 0.2000, correct 0.3000 | **1 question of 20 on each** |

**Prediction 2 HOLDS exactly at the b7 end and prediction 3 holds directionally at the edf end.**
The confound is bounded at **one question of 20, about 5 pp**, on the arm predicted to move most.
So the offline table in section 22.2 IS a usable stand-in for a live 3 s run, with a 5 pp caveat on
deferring arms, and the live twin the H100 added for hybrid-F-lhreq is confirmation rather than a
correction. llf completes the upper bound when it lands.

## 25. StudyORIN-REC's measured WARM device latency wired into the D155 scorer, and the 3 s and 5 s families re-scored on it (A6000, offline, 2026-11-20)

**A6000, offline, CPU only.** Section 24.1 left the by-deadline column PROVISIONAL because it
rested on D87's ORIN2 in-process substitution, which D146 (2) replaces. The Orin's WARM
measurement has landed (`00a223d`), and this section wires it in, re-scores both deadline families
under both rules, and answers the question section 24.1 asked: how many device answers flip.

Outputs: `results/orchestration/live2/frozen_test/frozen_headline_n16_s4_d155_L3_measured_warm.json`,
`..._n16_4seed_d155_measured_warm.json`, proofs in `..._d155_measured_warm_proofs.json`. The
pre-measurement files are KEPT and reachable as `LIVE2_DEVICE_LATENCY=trace`, which now labels
every output it produces `superseded`.

### 25.1 What was wired, and the one register correction

`scorer/score.py`'s device-latency slot was already built. Two things changed. First, the
MEASURED table is now the **default** source (`LIVE2_DEVICE_LATENCY=orin_rec_warm`), read per
question from the committed `results/sember/study_orin_rec/orin_rec_warm.jsonl` through
`data_sources.device_recall_warm_latency_s`, so no later run can silently pick up the superseded
number; `trace` is something a run now has to ask for. A question present in the trace but absent
from the table still **REFUSES** (`ScoringRefused` at `score.py:254`), and that is proved rather
than asserted: dropping one in-trace question from the table stops the run and names the
`question_id` and `opportunity_id`. Dropping a question the run does not need scores normally, so
the refusal is keyed on what the run actually consumes.

Second, the cascade side, and here the brief's premise needs correcting. **`data_sources.py:191
DEVICE_WAIT_RULE_S = 0.567` is not what the five cascade arms pay.** It has exactly one reference
in the repository, its own declaration: it is a write-only constant and wiring a number into it
would change nothing. What they pay is `baselines/costs.py:37 DEV_LAT_S = 0.567`, read by
`coordinator.py:63 DEVICE_ANSWER_CHARGE_S` and applied at `coordinator.py:471` (the device
answer's service time) and `:505` (the earliest instant such an arm may act). Both are LIVE
decision-timing sites, so adopting the measured value **changes what the arm does and needs a
rerun, not a re-score** - which is exactly what D154 (5) queues. What is done here: the proxy is
kept and labelled superseded with the write-only finding recorded beside it;
`data_sources.DEVICE_WAIT_MEASURED_S = 0.2697` is added and **is read**, by
`score.py:cascade_device_wait()`, which stamps every score output with `proxy-0.567` or
`measured-warm` and a `measured_device_wait_applied` flag; and all five adapter cards carry the
charge, its site and its register. No per-arm `device_answer_wait_s` attribute was added on
purpose: nothing reads a per-arm wait, and a field written and never read is ABSENT by the Step 2
rule, so adding one would have manufactured the very write-only mechanism this paragraph reports.
No number in this section depends on that item: none of the five cascade arms is in either family.

### 25.2 The measured table and its spread, before any score

97 questions, keyed on `question_id`, joined to **89 of 89** robot questions across seeds 0/4/5/6
and **20 of 20** in the 3 s seed-4 cell, with zero misses.

| | min | p10 | p25 | p50 | p75 | p90 | max | IQR |
|---|---|---|---|---|---|---|---|---|
| completion_s (n=97) | 0.2503 | 0.2602 | 0.2638 | **0.2697** | 0.2781 | 0.2894 | 0.3108 | 0.0143 |
| ttft_s (n=97) | 0.1913 | 0.2016 | - | 0.2109 | - | 0.2303 | 0.2525 | 0.0140 |
| the 89 scored | 0.2503 | 0.2600 | 0.2638 | 0.2704 | 0.2781 | 0.2944 | 0.3065 | 0.0143 |

**It is near-constant, and so is the input, which is why that is expected rather than a caching
artefact.** Every part-1 RECENT request carries exactly 60 frames; `prompt_tokens` spans only
5,476 to 5,682 (3.8 percent) and `cached_tokens` is **5,392 on all 97**. A 22.4 percent latency
spread on a 3.8 percent input spread is a distribution, not a constant. The shape the protocol
warns about - values identical to three decimals across inputs that differ - does not occur here.

### 25.3 The 3 s family (`_L3`), n=16 seed 4, under BOTH rules on the measured latency

| arm | by deadline (D155 (3), headline) | any time (D152 (1), beside it) | on time, all questions | device answers late |
|---|---|---|---|---|
| b7-edf-feasibility | **8/20 = 0.4000** [0.20, 0.60] | 8/20 = 0.4000 [0.20, 0.60] | 7/20 = 0.35 | **0** |
| eco-llm | **6/20 = 0.3000** [0.10, 0.50] | 6/20 = 0.3000 [0.10, 0.50] | 15/20 = 0.75 | **0** |
| mooncake | **8/20 = 0.4000** [0.20, 0.60] | 8/20 = 0.4000 [0.20, 0.60] | 7/20 = 0.35 | **0** |
| edf | **6/20 = 0.3000** [0.10, 0.50] | 6/20 = 0.3000 [0.10, 0.50] | 4/20 = 0.20 | **0** |
| **DEVICE ONLY** (measured warm answers alone, no cloud) | **6/20 = 0.3000** | 6/20 = 0.3000 | - | **0** |

### 25.4 The 5 s family (un-suffixed), n=16 seeds 0/4/5/6, under BOTH rules on the measured latency

| arm | by deadline | any time | on time, all questions | device answers late |
|---|---|---|---|---|
| b7-edf-feasibility | **38/89 = 0.4270** [0.3258, 0.5281] | 38/89 = 0.4270 | 42/89 = 0.4719 | **0** |
| eco-llm | **33/89 = 0.3708** [0.2697, 0.4719] | 33/89 = 0.3708 | 60/89 = 0.6742 | **0** |
| mooncake | **39/89 = 0.4382** [0.3371, 0.5393] | 39/89 = 0.4382 | 42/89 = 0.4719 | **0** |
| hybrid-F-lhreq | **43/89 = 0.4831** [0.3820, 0.5843] | 43/89 = 0.4831 | 85/89 = 0.9551 | **0** |
| hybrid-F6-lhreq | **44/89 = 0.4944** [0.3933, 0.5955] | 44/89 = 0.4944 | 61/89 = 0.6854 | **0** |
| **DEVICE ONLY** (measured warm answers alone, no cloud) | **20/89 = 0.2247** | 20/89 = 0.2247 | - | **0** |

### 25.5 The answer to the question: by deadline EQUALS any time, and ZERO device answers flip

**The user's expectation holds, and it holds plainly: at a measured 0.2503 to 0.3065 s against a
3 s deadline, by-deadline equals any-time on every arm, and the number of device answers that flip
relative to the superseded 0.146 to 0.225 s source is ZERO - 0 of 20 at 3 s and 0 of 89 at 5 s.**
Every arm row is identical between the two sources, field for field.

**Classified under Rule 2 as INCONCLUSIVE / UNEXERCISED, and the reason is headroom.** The rule is
live and the switch reaches the decision - the per-question latency the scorer consumes moves from
min 0.1460 / p50 0.1532 / max 0.2250 to min 0.2503 / p50 0.2704 / max 0.3065, so the measured value
arrives at `device_within` with its declared type and value on all 89 questions. The decision does
not change because **the slowest measured device answer is 0.3065 s, 10.2 percent of a 3 s
deadline**; the deadline would have to fall below 0.2503 s, or the latency rise 9.8x, before the
by-deadline rule could bite. This is not a negative about the policy and not a settled finding
about the rule: it is a statement that the device side of the deadline is not where the pressure
is. **The pressure D147's 3 s introduces falls entirely on the cloud path.**

**Section 24.1's PROVISIONAL marking is now discharged.** The numbers it reported stand, and they
stand for a different reason than it could then give: not because the superseded latency happened
to be small, but because the measured one is small too.

### 25.6 Robot answers are 2 TOKENS, and where that bears on a conclusion

`completion_tokens == 2` on every one of the 97 measured questions. **P20's answer cap (512,
unchanged per D155 (2)) is therefore not the device's latency lever** - a 2-token answer cannot be
shortened, and no cap above 2 changes anything. D155a measures the split directly: post-first-token
time is 0.058 s cold and 0.059 s warm, so the measured 0.270 s warm completion is about 0.211 s of
prefill plus fixed overhead against 0.059 s of decode, and the 3.296 s cold TTFT is re-prefill of
frames the device already holds. **Where it bears on a conclusion:** any device-side latency lever
on this workload is a prefill or residency lever, never an answer-length one, and the 12.4x
cold-to-warm gap is the whole of it. This is the physical component of Context Inertia measured on
the device side of the robot workload, and it says the device's cost is in holding the context, not
in producing the answer.

### 25.7 Mechanism verification, completed BEFORE the sweep

Full record in `d155_measured_warm_proofs.json`. Summary.

- **Step 0** found the stop condition in advance: the measured range 0.2503 to 0.3065 s against a
  3 s deadline is not reachable by the by-deadline branch, so the null was **pre-classified as
  unexercised before the sweep ran** rather than explained after it. It also fixed the join order:
  question-id coverage was verified at 89 of 89 and 20 of 20 before any scoring.
- **Step 1**, the chain: if device answer latency is path-dependent, then D155 (3)'s rule differs
  from D152 (1)'s exactly on questions where device latency exceeds L, so swapping a superseded
  latency source for a measured one moves the by-deadline column on those questions and only those.
- **Step 2**: the implementing quantity is `device_recall_warm_latency_s()[question_id]`, 0.2503 to
  0.3065 s over 89 distinct values, **read** at `score.py:273 device_within`, which decides
  `_standing_by_deadline`'s second branch at `score.py:632`. Not zero, not constant, not
  write-only.
- **Step 2b**: both conditions run on the 3 s cell and the 5 s family. **0 differing decisions**,
  no first-differing decision - and that is reported as an UNEXERCISED link and not as a negative,
  because the switch demonstrably arrived: the latency column the scorer prints changes with it.
- **Step 4**, the negative control, on n=16 seed 4 at 3 s: `LIVE2_DEVICE_WAIT_S=2.8` puts device
  arrival at 3.05 to 3.11 s. All 20 answers go late, and by-deadline parts from any-time on every
  arm - b7 8/20 to 5/20, eco-llm 6/20 to 5/20, mooncake 8/20 to 5/20, edf 6/20 to 3/20, DEVICE
  ONLY 6/20 to **0/20** - while any-time is unchanged throughout, as the rule requires. **The
  mechanism is live and reachable; the null is a headroom null.**
- **Step 5**: the alternative explanation for two identical columns is that the branch is never
  evaluated (unexpressible), which would look the same in the output. Step 4 distinguishes them:
  removing the headroom rather than the mechanism moves the column on every arm, which an
  unevaluated branch could not do.

### 25.8 Results consistency check, all seven points

1. **Cross-check.** Device recall latency p50 **0.2704 s this run against 0.1532 s prior** (D87
   interpolation, the superseded source): ratio **1.725x**, under the 2x investigation bar. **State
   it plainly, because the whole by-deadline column turns on this quantity.** Per question the
   ratio runs 1.196 to **2.099**, and the single question above 2x is explained rather than chosen
   between: the two quantities have **different definitions** (see point 4), D87's clamping to
   0.146 at 11k tokens while the measured value does not track history length at all, so the ratio
   spread tracks the proxy's token indexing and not measurement noise. The loader's self-check
   against the committed `warm_summary` p50 0.2697 / p90 0.2894 agrees exactly.
2. **Physical plausibility, and the label is the point.** 0.270 s delivers 2 output tokens on a
   5,524-token prompt of which **5,392 tokens are cached**, so only about 110 to 290 tokens are
   actually prefilled. Taken end to end that is about 20,500 prompt-tok/s, which is **faster than
   the committed A6000 cold prefill of about 7,100 tok/s**. That is not a finding and not an
   error: **it is a WARM path and is labelled as one** - `cached_covers_frames_all` is true on all
   97 - so it must not be compared against a cold curve, and no such comparison is drawn. On the
   tokens actually computed the rate is about 410 to 1,070 tok/s, which is unremarkable for a 4B on
   an Orin. The cold counterpart on the same 97 is 3.354 s e2e / 3.296 s TTFT (D155a), 12.4x the
   warm figure, which is consistent rather than anomalous. **Register note:** the 11k to
   28k-token history is NOT the measured prompt - these are 60-frame RECENT requests at about
   5.5k tokens, and `r1_prompt_tokens` (the full-history comparator) is 11,399 to 12,830. The
   0.270 s is not a 28k-token prefill and is not reported as one.
3. **Distribution.** Full spread in 25.2 rather than p50 and p90 alone: n=97, min 0.2503, max
   0.3108, IQR 0.0143. Near-constant, and the input is near-constant too (60 frames every request,
   3.8 percent token spread, cached_tokens 5,392 on all 97), so this is expected. The artefact
   spread and averaged-out shapes are both checked: there is no spread in the by-deadline column to
   mistake for an effect (it is 0 flips), and the stratum where an effect would concentrate (the
   longest histories) **does not exist under the measured source**, because a RECENT prompt does
   not grow with history.
4. **Definition audit, and this is where the 2x outlier lives.** Same name, three differences.
   THIS RUN: measured WARM **completion** time (prefill + 2-token decode) on a 60-frame RECENT
   prompt, per question, Orin / qwen3vl4b / vLLM. PRIOR COMMITTED: D87's ORIN2 in-process **TTFT**,
   two points interpolated on **full history tokens** and clamped. Completion vs TTFT, measured vs
   interpolated, RECENT prompt vs full history. Reconciled by labelling, not by picking: the old
   source stays reachable and says `superseded` in its own header. Delivery is `completion` on both
   sides. The robot deadline is read per question from the trace (3.0 on `_L3`, 5.0 un-suffixed),
   never from a literal.
5. **Claim linkage.** The headline bears on the **physical component of Context Inertia**: it says
   the device side of that component is negligible against a 3 s deadline on this workload. It does
   not speak to the representation-vs-placement claim. Its real contribution is removing a
   confound from D152 (1): the device fallback that headline credits is now **known** to arrive in
   time rather than assumed to.
6. **Proxy validity.** The measured table applied by `question_id` is an identity, not a proxy -
   same question set, exact join. But the **DEVICE-ONLY row mixes sources** and is labelled as
   such: its correctness is still D87's 4B-I x RECENT StudyO-Q4 set, produced on the A6000 / H100,
   which StudyD15 Part A rejected as an exact numerical stand-in for the Orin. **The Orin's own
   warm run answers 16 of these 89 correctly against the proxy's 20, so a device-only row on
   measured correctness would read 0.1798 rather than 0.2247.** That affects the row's LEVEL and is
   reported as a limitation; it does not touch the flip count, which is a latency question.
   Changing the correctness source is a methodological change and is not made here.
7. **Validate the control, and a positive control.** Three, run **before** the comparison was read.
   (a) The 5 s family re-scored under `LIVE2_DEVICE_LATENCY=trace` reproduces the committed
   `frozen_headline_n16_4seed_d155.json` **identically on every field of every arm row**. (b) The
   3 s family likewise reproduces the committed `frozen_headline_n16_s4_d155_L3.json` identically.
   (c) **The positive control proper:** a quantity that *cannot* depend on device latency must be
   unmoved by the new source. The on-time tables are unmoved - 5 s b7 feas 42/69, all 42/89, SS
   1274/1426, hybrid-F 67/69 and 85/89 and 1399/1426, dash 4 of 4 for every arm; 3 s b7 7/10 and
   7/20, eco-llm 7/10 and 15/20, mooncake 7/10 and 7/20, edf 4/10 and 4/20. **Had any of these
   moved, the check would be broken and not the arm**, because device latency is not an input to an
   on-time table. (d) The **control arm's own numbers** were audited before any difference against
   it was read: b7 is the comparator for every `_minus_b7` interval, and its by-deadline 0.4270 and
   on-time 0.6087 at 5 s, and 0.4000 and 7/10 at 3 s, all equal its committed values.

### 25.9 B3: the robot deadline default moves to 3 s, with the trace name anchored at 5 s

**`DS.ROBOT_DEADLINE_S` is now 3.0** (D147: single-shot + 1 s, from the use case; 5.0 was a
starting value so cold rebuilds were feasible) and `run_live2_real.py --robot-deadline-s` defaults
to it rather than to a second literal.

**The naming decision, made deliberately.** `run_live2_real.py:167` tagged a trace `_L<x>` when the
deadline differed from the literal 5.0. That literal is now a named constant,
`DS.TRACE_NAME_ANCHOR_DEADLINE_S = 5.0`, and it **stays 5.0 and is NOT tied to the default**.
Anchoring on the default instead would have given one directory name two meanings - every
committed un-suffixed cell is 5 s, and a new defaulted cell would have been 3 s - which is the
definition-audit failure in its purest form. Consequence, stated rather than discovered later: a
run that now takes the 3 s **default** is tagged `_L3` exactly as an explicit `--robot-deadline-s
3` run is; committed `_L3` cells stay addressable under `FROZEN_HEADLINE_SUFFIX=_L3`; committed
un-suffixed cells stay addressable and stay 5 s.

**The required proof: no committed trace digest changes for cells that passed the flag
explicitly.**

| regenerated at | fairness_digest_A | fairness_digest_B | against |
|---|---|---|---|
| explicit 5.0 | `150289c5...161e18` | `42e47912...be366f` | committed `seed4_..._lh_req_ss2/trace_meta.json`: **both MATCH** |
| explicit 3.0 | `e49f0790...bbc4e6` | `415e3d29...98 0221` | committed `_L3` cells' `header.json` fairness_digest, all four arms: **MATCHES** |

`device_answers.jsonl` matches the committed sha256 byte for byte at 5.0. `trace.jsonl` differs in
**one field only**, `frame_bytes` on `monitor_opportunity` records (13,193 of 14,985 rows), which
is the pre-existing and already-documented D103 (h) median fallback recorded in
`frozen_headline.device_answers_for`; the fairness digests exclude monitor frames in pull mode and
both match exactly, so **this is not caused by B3**. And the proof is not vacuous: the 5.0 and 3.0
digests **differ**, so the deadline is live in the digest and a match at 5.0 is informative rather
than an instrument that cannot fail.

**A second-order bug B3 would have caused, found by that control and fixed.**
`frozen_headline.local_trace` left `DS.ROBOT_DEADLINE_S` alone when a directory name carried no
`_L` tag. With the default at 3.0 it would have regenerated **every un-suffixed (5 s) cell's trace
with 3 s deadlines written into its questions** and scored the whole committed 5 s family against
the wrong bound, with nothing looking wrong. The absent tag is now resolved explicitly to the 5.0
anchor. Positive control (a) is what caught it, which is the reason it was run before the
comparison rather than after.

`fleet/trace.py` and `coordinator.py` were not needed for B3 and were not touched. Live2 suite:
`test_live2_coord` 26/26, `d114` 16/16, `d118` 26/26, `fakeserver` 4/4, `fix` 16/16, `fix2` 22/22,
`harness` 33/33, `history_size` 9/9, all OK; `import hybrid` and `import arms` both clean.

### 25.10 What this does not settle

The **cascade arms are still `proxy-0.567`** and their rerun is still queued (25.1). The
**device-only row's correctness is still an A6000 proxy** (check 6), and resolving it would move
that row from 0.2247 to about 0.1798 at 5 s - it does not move any arm. And the 3 s family is
**one seed and four arms**; seeds 5 and 6 and the remaining `HANDFUL_L3` arms are not yet run, so
25.3 is a four-arm table at seed 4 and not a 3 s headline.
