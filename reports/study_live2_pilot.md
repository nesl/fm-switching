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
