# Figure-data readiness (StudyFIGDATA, D214)

Pipeline sha (D209 canonical scorer): `b5264100`. Generated 2026-11-23. Tables in `reports/figdata/`. NO FIGURES until the user says plot.

## Arm coverage (standard grid: 1x memory, 16 devices, robot deadline 3.0 s, rq30)

| arm | policy_version | rung | seeds present | status |
|---|---|---|---|---|
| fair-c5attr-rr | development-best | rung3 | [4, 5, 6, 7] | provisional |
| fair-c5attr | development | rung3 | [4, 5, 6, 7] | provisional |
| state-uo-c5attr | development | rung2 | [4, 5, 6, 7] | provisional |
| base | development | rung0 | [4, 5, 6, 7] | provisional |
| rules | development | rung1 | [4, 5, 6, 7] | provisional |
| edf | baseline | - | [4, 5, 6, 7] | valid |
| llf | baseline | - | [4, 5, 6, 7] | valid |
| b7-edf-feasibility | baseline | - | [4, 5, 6, 7] | valid |
| always-cloud-fcfs | baseline | - | [4, 5, 6, 7] | valid |
| simplestream | baseline | - | [4, 5, 6, 7] | valid |
| querystream-proactive | baseline | - | [4, 5, 6, 7] | valid |
| mooncake | baseline | - | [4, 5, 6, 7] | valid |
| attentionstore-prefetch | baseline | - | [4, 5, 6, 7] | valid |
| warm-all-lru | baseline | - | [4, 5, 6, 7] | valid |
| hybrid-F-lhreq | baseline | - | [4, 5, 6, 7] | valid |
| v5-rules | baseline | - | [4, 5, 6, 7] | valid |
| lmcache | baseline | - | [4, 5, 6, 7] | valid |
| streamscout | baseline | - | [4, 5, 6, 7] | valid |
| eco-llm | baseline | - | [4, 5, 6, 7] | valid |
| kvflow-prefetch (port-limited) | baseline | - | [4, 5, 6, 7] | valid |
| device-only | baseline | - | [4, 5, 6, 7] | valid |

## Gaps until reruns land

- **cascade-routing**: no scored cell yet (H100 filler, D212); when it lands it is the device-only-floor baseline (its sufficiency proxy cannot fire here)
- **confidence-cascade**: superseded cells (D205 constant-0.0 reader); gap until the D205 rerun lands
- **final ladder** (covex-v6-state-final / -fair-final / -final): not present; when cells land they are added as policy_version=final and the development rows are kept as status=superseded-by-final. Producer: H100 (flash gates the list).

## Condition coverage (F8-F12)

- F8 memory: present ['0.25x', '0.5x'] (targets 0.25x, 0.5x).
- F9 fleet: present NONE beyond 16; capacity (largest fleet meeting all three D178 targets) needs a fleet sweep, column left blank until it lands. Producer: flash/H100.
- F10 deadline: present ['2.5'] (target 2.5 s).
- F11 composition/reask: present NONE beyond rq30 / 40:40:20.
- F12 network: present NONE (no network-condition cells exist).

## Instrumentation gaps by field

- **F3 latency stamps**: request.jsonl records t_submit, t_first_token, t_done only, so only two composite stamps exist (queue+prefill, decode). ABSENT: upload, coordinator hold, engine queue (separate), return hop. Producer: the live runner (flash/H100) would need to emit them.
- **F13 GPU busy**: present (coordinator_result.budget_spent_gpu_s). Uncached-token charge (D174) and output tokens present from request.jsonl.
- **F14 dry decision latency** at 16/24/32/48 devices: ABSENT (live p50/p99 present). Producer: flash dry sweep.
- **F6 series**: KV pool (residency.jsonl), host load, decisions, late alerts present on the candidate cells; the series are read at plot time, not dumped here.
- **F7 counterfactual decisions**: ABSENT (covex-v6-cf* not in the figure arm set, D210; dry cells on flash).
- **F15/F16**: pointer rows only; the history-matters and cold-vs-warm series live in StudyEARLY1 / phase1 cost profiling and are transcribed on request.
- **F17**: placeholder, no real-deployment data exists.
- **dashcam delivered-stream mAP cross-fitted ALL**: present.

## Table row counts

- F1: 105 rows
- F2: 252 rows
- F3: 980240 rows
- F4: 1280 rows
- F6: 16 rows
- F7: 0 rows
- F8: 30 rows
- F9: 0 rows
- F10: 5 rows
- F11: 0 rows
- F12: 0 rows
- F13: 112 rows
- F14: 112 rows
- F15: 1 rows
- F16: 1 rows
- F17: 0 rows
- F1_units: 40071 rows
