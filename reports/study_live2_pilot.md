# StudyLIVE2-pilot (round 1, block 0): PILOT, NOT A ROUND-1 RESULT

Status: **STOPPED AT STEP 1 (2026-11-18 08:47)**: the first real-server cell failed the harness lateness requirement
(emulator p99 lateness 511.6 ms > 50 ms), which the prompt makes a Step 1 failure; the pilot stopped there and the
ladder (Step 2) did not run. Everything in this report is labelled PILOT, NOT A ROUND-1 RESULT; nothing here is a
measurement for round 1.

## 1. Preconditions (all held at 08:39)

- P1: StudyLIVE2-pre Part 1 manifests PASS; Part 2 calibration `results/orchestration/live2/calibration/
  live2_calibration_dense_jpeg.json` label FINAL, fit_sample dense, CTRL1c fold map (5 folds, 300 clips), body check
  vs the live coordinator PASSED; Part 3 cache isolation PASS.
- P2: origin/main contains StudyLIVE2-fix (0616c0f; "644 checks green"; D98 checks (a) to (d) pass; D99 equivalence
  identical in 6 of 6 cells) and StudyLIVE2-fix2 (5f6d01f; 22 tests all passing); `research/policy_design_log.md` md5
  b885ab9f2cf396a8d6fbafda86f1b6c3 with rows D98 to D105. `git pull --ff-only`: already up to date (HEAD 4e6de56).
- P3: GPU 2 idle and exclusive. The saved prompt contains both checked lines (restart before every run; score after the
  server stops).

## 2. What ran

Runner `experiments/orchestration/study_live2_pilot.py` (glue only; flash's live2 code unchanged): per run, restart
the round-1 server (the LIVE2-pre Part 2 command: ENG1c KV-HOST flags, host 27 GiB; flag diff vs DE_c38 `[('38',
'27')]`), generate the fleet trace (`fleet/trace.py`, seed 0, 50 : 50, mode A, per-frame bytes from the Part-1
manifests: `frame_bytes_source` "Part-2 manifest ..."), build the arm and `Live2Coordinator` as `run_live2_cell.py`
does (FINAL calibration, pol4, mu EWMA and H = 0.5 s for the policy, decision period 0.1 s, default GPU budget, D71 /
D82 targets), drive it with the real-time `FleetEmulator` through `bridge.EmulatorBridge` (the wiring of fix2's
end-to-end test), stop the server, score with `scorer/score.py`. Adapters, implementation only: a directory of
symlinks named by frame_ref pointing at the stored JPEGs (the coordinator resolves `frames_root / frame_ref`); the
bridge instance carries `kind = "vllm"` and `run_meta` is annotated with the memory setting; device-only runs without
a server.

| run | server restart | window | result |
|---|---|---|---|
| device-only, 8 devices (4 + 4), tight | none (sends nothing) | 120 s | lateness p99 0.48 ms, digest equal, scored |
| edf, 8 devices (4 + 4), tight | 08:42 to 08:43 (startup 63.7 s) | 120 s | **lateness p99 511.6 ms (INVALID)**; everything else passed |
| policy-core | started 08:47, stopped before its window | | not run (pilot stopped) |
| always-cloud-fcfs, edf-piece1024, edf-piece2048, utility-per-cost, b9 | | | not run |

## 3. Step 1 checks on the edf cell

| requirement | result |
|---|---|
| HTTP errors 0 | 0 errors, 725 of 725 completed requests HTTP 200 (727 submitted) |
| every request carries cache_salt and mm uuids | 725 of 725 |
| cached_tokens reported, WARM / COLD tags present | 725 of 725 report cached_tokens; 720 COLD, 5 WARM |
| fairness_digest equals the emulator's sent-stream digest and is identical across arms | equal (85251b9b...), identical to the device-only run |
| emulator p99 lateness <= 50 ms | **FAIL: p50 0.11 ms, p90 171 ms, p99 511.6 ms, max 1,434 ms over 2,317 actions** |
| the scorer runs and refuses nothing | ran, no refusal (capacity conjunct not met at n = 8: dashcam all-meet true, robot pool not measurable at seed 0 at this size, D97) |

Diagnosis (facts; the cause is NOT verified): the coordinator was idle (decision latency p50 0.58 ms, p99 0.70 ms, max
1.67 ms; 0 epoch overruns; CPU 4.7 %), the emulator process used 4.6 % CPU, and the same pipeline without a server
(device-only) had p99 0.48 ms. So the lateness comes from the real-request path blocking the single emulator loop, not
from decision cost. Candidate, untested: the emulator, bridge, coordinator and request-body building share one Python
process; building large bodies on the loop thread (a robot's cold-history rebuild carries every frame base64-encoded)
and the 64 response-reading threads contend for the GIL with the wall-clock loop. A fix belongs in the harness (body
building off the loop thread, or the emulator in its own process) and is flash's to make; nothing was changed here.

## 4. Not produced (pilot stopped)

Break sizes, minutes per run beyond Step 1, time-averaged mu and the D88 fixed values, the predicted-vs-actual sample by
traffic mix, the D77 main-sweep sizes and the mechanism-verification Steps 1 to 3 for block 1 all require Step 2 and
were not produced. The cache-isolation result is LIVE2-pre's Part 3 (PASS). Block 1 was not started.

## 5. Files

New: `experiments/orchestration/study_live2_pilot.py`, `reports/study_live2_pilot.md`,
`results/orchestration/live2/pilot/` (`pilot_runs.jsonl`, `pilot.log`, `runs/device-only_n8_tight/`,
`runs/edf_n8_tight/` with header, run_meta, outcomes, request / decision / residency logs, coordinator result; `runs/policy-core_n8_tight/` holds only what was written before the stop interrupted its server start, no requests and no data). Traces
and frame symlinks under `~/data/live2/` (regenerable: `fleet/trace.py --seed 0 --devices 8 --ratio 50:50 --run-s 120
--mode A --frame-manifest ~/data/live2/jpeg/combined_manifest.jsonl`). Changed: `research/EXPERIMENTS.md`,
`results/INDEX.md`, `research/STATUS.md`.

## 6. Rerun 2026-11-18 with flash's run_live2_real.py: STOPPED AT STEP 1 AGAIN

User ruling 2026-11-18: rerun the pilot now with `experiments/orchestration/live2/run_live2_real.py` (StudyLIVE2-harness,
22808d0: coordinator in its own process, async streaming client, frame cache, emulator ticking the coordinator on the
wall clock), preconditions as before (all held: calibration FINAL with the scorer's fold schema, cache isolation PASS,
StudyLIVE2-fix and fix2 with tests passing, design log md5 b885ab9f..., GPU 2 idle; the S-EMBER D2 store now reaches
every session's end, closing the harness report's open issue 2), server restarted before every run, git HEAD aa3a2d8
recorded in every header. Driver `experiments/orchestration/study_live2_pilot2_driver.sh`; outputs `results/orchestration/live2/pilot/runs2/`.

| cell | lateness p50 / p90 / p99 / max (ms) | requests | HTTP errors | digest equal | scored | Step 1 |
|---|---|---|---|---|---|---|
| device-only, 8 devices, 120 s (no server) | 0.10 / 0.10 / 0.11 / 0.13 | 0 | 0 | yes | yes (no refusal) | pass |
| edf, 8 devices, 120 s | 0.10 / 32.8 / **728.1** / 1,464.8 | 720 | 0 | yes | yes (no refusal) | **FAIL (p99 > 50 ms)** |

The driver stopped at the first failing cell, as Step 1 requires; policy-core and the other five arms did not run, and
the ladder did not start. Facts: the emulator process used 1.9 % CPU over the 120 s (the same as the device-only run,
2.0 %); the coordinator process's decision latency was p50 0.53 ms, p99 0.74 ms, max 2.8 ms, with 0 epoch overruns and
9.3 % CPU; frame-cache hit fraction 0.48. So neither process was busy, and the lateness appears only when real requests
flow. Candidate (NOT tested): the emulator waits for the coordinator process's reply to each event, and the
coordinator's single event loop is intermittently held by the real streaming responses; flash's fake streaming server
(p99 0.26 ms on flash) does not reproduce the H100's response volume or timing. The run_meta of this runner does not
record the per-kind lateness the harness report used, so the late actions cannot be attributed from these outputs.
Pilot results remain PILOT, NOT ROUND-1 RESULTS.

## 7. INTERIM PILOT REPORT on the D114 build (2026-11-18 17:08 to 20:55). PILOT RESULTS, NEVER ROUND-1 RESULTS

Build: D114 work-conserving EDF (530958f) with the history-size fix (79f2d38), D115 decision-time instrumentation and
the vllm-priority wiring; per-run HEAD in every header (f792269 at Step 1 through 5425776 at the last run; flash's
fa50dfc (D119 switch default-off, byte-identical default path by flash's 48-cell check) entered from edf at 8 devices
on). Round-1 server (27 GiB unless noted) restarted before every run, preflight every-ref check passed before every
run, seed 0, 50 : 50, mode A, uniform links, FINAL calibration, decision period 100 ms, mu EWMA, H = 0.5 (policy-core
only). Drivers `experiments/orchestration/study_live2_pilot3_driver.sh` (Step 1, ladder to D123) and
`study_live2_pilot3b_driver.sh` (D123). Outputs `results/orchestration/live2/pilot/runs3/`, per-run summary
`pilot3_summary.json`, per-question tables `prelim/`.

**Rulings applied tonight.** Up-front defaults with the user's two changes (Step 1: a failure of a non-pilot arm
does not stop; policy-core and edf at every base size 4 to 64, per-arm doubling above 64, per-arm breaks). D123 (about
18:45): policy-core v1.0 SUPERSEDED (D122); its remaining ladder skipped; only policy-independent runs. D125: the
policy rerun waits for "v1.2-fast release". **Policy-core v1.0 rows below are labelled SUPERSEDED.**

### 7.1 All runs (valid runs only; one invalid run listed in 7.6)

| run | requests | dashcams all meet | robot on time / pooled | robot measurable (D97) | verdict | decision wall p50 / p99 ms | decision CPU p99 ms | wall / CPU p99 | submit delay p99 ms | other users' CPU, cores p50 / p99 | whole builds covering history |
|---|---|---|---|---|---|---|---|---|---|---|---|
| always-cloud-fcfs_n4_600s_h27 | 2183 | true | 8/9 | false | pass | 0.3549 / 0.4047 | 0.3972 | 1.0407 | 7.0051 | 2.364 / 3.258 | 0/0 |
| always-cloud-fcfs_n8_120s_h27_step1 | 773 | true | 6/6 | false | pass | 0.5596 / 0.6704 | 0.6634 | 1.0427 | 8.7563 | 3.436 / 7.158 | 0/0 |
| always-cloud-fcfs_n8_600s_h27 | 4344 | true | 18/20 | true | pass | 0.5687 / 0.6527 | 0.6455 | 1.0304 | 16.3347 | 2.381 / 3.409 | 0/0 |
| b9_n8_120s_h27_step1 | 751 | true | 5/6 | false | pass | 1.0641 / 1.4452 | 1.4277 | 1.038 | 14.5566 | 3.383 / 4.21 | 0/0 |
| device-only_n8_120s_h27_step1 | 0 | false | 0/6 | false | fail | 0.5503 / 0.6379 | 0.6309 | 1.0393 | null | 2.479 / 3.65 | 0/0 |
| edf-piece1024_n8_120s_h27_step1 | 783 | true | 0/6 | false | pass | 0.6092 / 1.0061 | 0.9984 | 1.033 | 6.2412 | 3.417 / 4.328 | 0/0 |
| edf-piece2048_n8_120s_h27_step1 | 774 | true | 0/6 | false | pass | 0.6036 / 0.7284 | 0.7218 | 1.0343 | 6.9362 | 3.397 / 4.448 | 0/0 |
| edf_n16_600s_h27 | 6025 | false | 0/35 | true | fail | 1.0584 / 1.5004 | 1.4819 | 1.0216 | 34.1288 | 2.392 / 3.367 | 13/13 |
| edf_n32_600s_h27 | 5663 | false | 0/72 | true | fail | 1.3328 / 2.4104 | 2.381 | 1.0431 | 33.6079 | 2.365 / 3.562 | 22/22 |
| edf_n4_600s_h27 | 2171 | true | 9/9 | false | pass | 0.3824 / 0.4982 | 0.4914 | 1.0309 | 7.4215 | 3.388 / 4.31 | 5/5 |
| edf_n64_600s_h27 | 4602 | false | 0/165 | true | fail | 1.63 / 4.3566 | 4.3158 | 1.2042 | 2385.5037 | 2.369 / 3.247 | 19/19 |
| edf_n8_120s_h27_step1 | 712 | true | 0/6 | false | pass | 0.6055 / 0.803 | 0.796 | 1.0362 | 7.8532 | 3.471 / 5.462 | 5/5 |
| edf_n8_600s_h27 | 4165 | true | 2/20 | true | fail | 0.6121 / 0.7663 | 0.7579 | 1.0275 | 17.3087 | 2.405 / 4.205 | 10/10 |
| edf_n8_600s_h27_cinflight8 | 4208 | true | 18/20 | true | pass | 0.6134 / 0.7743 | 0.7675 | 1.0291 | 17.3196 | 2.368 / 3.289 | 9/9 |
| llf_n16_600s_h27_informative | 6377 | false | 0/35 | true | fail | 1.0839 / 1.5171 | 1.4916 | 1.0197 | 32.5196 | 2.411 / 3.444 | 10/10 |
| llf_n32_600s_h27_informative | 6317 | false | 1/72 | true | fail | 1.3348 / 2.4612 | 2.434 | 1.0474 | 36.3012 | 2.373 / 3.251 | 14/14 |
| llf_n4_600s_h27_informative | 2169 | true | 7/9 | false | pass | 0.4028 / 0.5205 | 0.5135 | 1.0382 | 7.5993 | 2.361 / 3.249 | 5/5 |
| llf_n64_600s_h27_informative | 5689 | false | 2/165 | true | fail | 1.6273 / 4.2711 | 4.2265 | 1.3651 | 897.9453 | 2.372 / 3.27 | 21/21 |
| llf_n8_600s_h27_informative | 4161 | true | 12/20 | true | fail | 0.6431 / 0.7579 | 0.7513 | 1.0203 | 16.6722 | 2.375 / 3.858 | 9/9 |
| policy-core_n16_600s_h27 | 663 | false | 0/35 | true | fail | 15.3086 / 27.3858 | 26.7645 | 1.014 | 82.4583 | 2.363 / 3.307 | 0/0 |
| policy-core_n4_600s_h27 | 2176 | true | 1/9 | false | pass | 2.3111 / 8.1636 | 8.156 | 1.0213 | 16.4405 | 3.402 / 5.093 | 1/1 |
| policy-core_n8_120s_h27_step1 | 767 | true | 0/6 | false | pass | 4.1766 / 18.5182 | 18.493 | 1.0212 | 21.6055 | 3.463 / 4.616 | 0/0 |
| policy-core_n8_600s_h27 | 4101 | true | 0/20 | true | fail | 6.9653 / 33.2855 | 31.9883 | 1.02 | 61.7535 | 3.383 / 4.269 | 0/0 |
| utility-per-cost_n8_120s_h27_step1 | 772 | true | 6/6 | false | pass | 0.6272 / 0.809 | 0.8024 | 1.0319 | 9.2292 | 3.384 / 4.361 | 0/0 |
| vllm-priority_n8_120s_h27_priority_smoke | 773 | true | 6/6 | false | pass | 0.5866 / 0.9442 | 0.9378 | 1.0363 | 8.9444 | 2.379 / 3.301 | 0/0 |

"Verdict" = every eligible dashcam meets L = 1.0 s / p = 25 % AND, where the robot pool is measurable at seed 0, the
pooled robot target L = 5 s / p = 90 % (D95 / D97). All 25 valid runs: 0 HTTP errors, digests equal, emulator
lateness p99 0.11 to 0.14 ms with no action kind over 50 ms.

### 7.2 The ladders and the breaks

| arm | 4 | 8 | 16 | 32 | 64 | first failing size |
|---|---|---|---|---|---|---|
| edf (C_inflight 4, D114 default) | pass (robot 9 / 9, not measurable) | **fail** (robot 2 / 20) | fail (dashcams and robot) | fail | fail | **8** |
| policy-core v1.0, SUPERSEDED | pass (robot 1 / 9) | fail (robot 0 / 20) | fail (mu locked, 7.5) | crashed, see 7.6 | not run (D123) | 8 (v1.0) |
| always-cloud-fcfs | pass | **pass (robot 18 / 20)** | n/a (only up to edf's break) | | | none up to 8 |
| edf at C_inflight 8 (D114 sensitivity) | | **pass (robot 18 / 20)** | | | | |
| llf (INFORMATIVE, NOT PART OF D95) | pass (7 / 9) | fail (12 / 20) | fail | fail | fail | 8 |

Robot measurability at seed 0 (D97, >= 20 pooled questions): not measurable at 4 devices (9 questions), measurable
at 8 (20), 16 (35), 32 (72) and 64 (165).

### 7.3 Findings (pilot observations, not round-1 results)

1. **edf's break at 8 devices is set by D114's in-flight limit, not by the GPU** (one sensitivity run): at 8 devices
   edf with C_inflight = 4 answers 2 of 20 robot questions within 5 s, with C_inflight = 8 it answers 18 of 20 and
   passes, the same as always-cloud-fcfs (18 / 20), all three with every dashcam meeting its target. With 4 in
   flight the robot rebuilds queue behind dashcam calls; the request counts are the same (4,165 / 4,208 / 4,344).
2. **Above 8 devices every arm fails on the dashcams as well**, and edf's and llf's request counts fall with fleet
   size past 16 (edf 6,025 -> 5,663 -> 4,602 at 16 / 32 / 64); candidate, not tested: the engine saturates and more of
   its time goes to cold rebuilds (robot pooled questions grow 35 -> 165).
3. **Policy-core v1.0 (SUPERSEDED) declined or deferred almost every robot question**: at 4 devices it released 1 of
   9 (answered in 1.2 s) and declined 6 at once, two of them on a history it believed GPU-warm, deferring 2 until the
   deadline; at 8 devices it released none of 20 (9 declines, 11 deferred to the deadline). Per-question tables:
   `prelim/*_robot_questions.jsonl`; raw decision logs `prelim/policy-core_n{4,8}_600s_h27_decision.jsonl.gz`. The
   deficit counter Z is not in the decision log (no field), so it could not be reported.
4. **Policy-core v1.0's mu estimate has an absorbing state** (16 devices): mu (EWMA of the realized marginal utility
   of the LAST RELEASED unit, `arms_policy.py`) jumped from about 1.2 to 18.18 after its first rebuild piece at 67 s,
   after which no monitoring instant was admitted, nothing completed, and mu never updated again; 659 monitoring
   releases, all before 67 s, 663 requests in the run. At 4 and 8 devices mu stayed within 0 to 1.86.
5. **Decision time on this CPU**: policy-core v1.0 decision wall p99 8.2 / 33.3 / 27.4 ms at 4 / 8 / 16 devices with
   wall / CPU p99 at most 1.04 (no contention); EDF-family p99 0.4 to 4.4 ms. Other users' processes used 2.4 to 3.5
   cores (p50) throughout; host-load percentiles per run in `run_meta.json` (`host_load`).
6. **History-size fix holds in every run**: 143 of 143 whole rebuilds cover their history (prompt / trace cumulative
   size 0.87 to 1.00); policy-core's piece chains reach 0.996.
7. **vllm-priority smoke** (8 devices, 120 s, server started with `--scheduling-policy priority`, confirmed in the
   server command and vLLM's own config log): VALID, 773 requests, 0 HTTP errors (every send passed the pre-send
   assertion), 4,802 priorities emitted, lateness p99 0.13 ms, digests equal. Validity only, as ruled.

### 7.4 Step 1 (D104), all 8 arms at 8 devices, 120 s: all valid, all with 0 requests missing cache_salt, mm uuids,
cached_tokens or cache_path; every arm but device-only met the dashcam target; robot not measurable in 120 s.

### 7.5 Not run, and why

Policy-core v1.0 at 32 and 64 devices and its policy-dependent extras (edf-piece1024 around its break, roomy checks):
superseded (D123); they run on v1.2-fast once its release commit lands (D125). MOT2: parked (D113).

### 7.6 Invalid or stopped

`policy-core_n32_600s_h27` (v1.0, SUPERSEDED): crashed after 4.5 s, `ValueError: action names unknown session
'robo008|s000|1150662047093052_start_0.0_end_330.256'` (the arm named a session the coordinator had not registered;
reported to flash); its rerun was stopped at about one minute when D123 arrived (not published). Marked
`SUPERSEDED_INVALID.txt`.
