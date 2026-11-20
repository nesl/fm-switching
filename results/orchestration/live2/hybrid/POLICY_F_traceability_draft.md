# Draft traceability rows for StudyPOLICY-F (D142)

**DRAFT, NOT APPLIED.** `research/EXPERIMENTS.md` has no row for this work and none for the H100's
`StudyHYBRID-live` either, and `CLAUDE.md` says to stop and ask when no matching row exists rather
than invent one. These are proposed, for the user to place. They are also NOT applied because the
study is incomplete: no policy cell has been scored (LH-REQ blocker) and mechanism verification
Steps 3 and 4 have not been run.

## Proposed `research/EXPERIMENTS.md` row

| field | proposed value |
|---|---|
| E-id | `StudyPOLICY-F` |
| purpose | orchestration |
| claim | Joint representation x placement x timing under a quality SLO beats decomposed policies; the frozen policy is the arm that tests it. |
| script | `experiments/orchestration/live2/hybrid/hybrid_arm.py` (arms `hybrid-F`, `hybrid-F6`) |
| inputs | `results/orchestration/prof1/profiles_dev.json`; `results/orchestration/prof1/ss_quality.json` (PLACEHOLDER); `experiments/orchestration/policy/chooser.py` (70be641, read-only); LH-REQ trace **PENDING session 2** |
| outputs | `results/orchestration/live2/hybrid/policy_f_c6_profile.json`; `reports/study_policy_f.md` |
| hosts | flash (dry cells only; no GPU touched) |
| n / sweep | dry: 12/16/32 devices, seeds 0 and 4, 600 s, mixes 50:50 and 40:40:20 |
| verdict | **NO VERDICT. Build complete, scoring not started.** Byte-identity with SS absent PASS 6/6; `hybrid-F` byte-identical to the screened `hybrid2-c1c2k15c3c5`; C6 breaches the 100 ms decision period at 32 devices (p99 168.4 ms); two C6 links recorded CONSTANT and ABSENT. |
| status | IN PROGRESS, BLOCKED |
| consistency_check | DONE, 7 of 7 recorded in `reports/study_policy_f.md` s8; one 3-7x disagreement (dry vs live decision latency) investigated and explained |
| mechanism_verification | **INCOMPLETE.** Steps 0, 1, 2, 2b, 5 recorded; **Steps 3 and 4 NOT DONE**. Two stopping conditions recorded (C6 horizon CONSTANT, C6-on-SS ABSENT). |

## Proposed `results/INDEX.md` row

| file | script | model | device | n | headline | old name |
|---|---|---|---|---|---|---|
| `results/orchestration/live2/hybrid/policy_f_c6_profile.json` | `scratchpad/c6_profile.py` via `policy/audit/_harness.py` | n/a (dry, no server) | flash, no GPU | 12/16/32 dev, seed 0, 600 s | `hybrid-F` byte-identical to `hybrid2-c1c2k15c3c5`; `hybrid-F6` decision latency p99 168.4 ms at 32 devices, breaching the 100 ms period; C6 cost dominated by the mirror advance, not the rollouts | new |
| `results/orchestration/prof1/ss_quality.json` | hand-written declared input | n/a | n/a | 4,319 VizWiz + 700 EgoThink device rows | SS quality table as a declared INPUT; cloud accuracy is a PLACEHOLDER = measured device accuracy, which puts C1's SS value at 1/106 of a robot's | new |

## Proposed `research/STATUS.md` note

Frozen-policy build (D142) complete and uncommitted; scoring blocked on the LH-REQ trace
(session 2) and on mechanism-verification Steps 3 and 4. No E-id registered yet.
Last updated 2026-11-19.

## Provenance gap

`policy_f_c6_profile.json` was written by a scratchpad script and does **not** carry the
`_provenance` block `CLAUDE.md` requires (`git_commit`, `script`, `model`, `device`, `n`,
`timestamp`). It should be regenerated through a committed script under
`experiments/orchestration/live2/hybrid/` with `stamp(...)` before it is treated as a citable result.
