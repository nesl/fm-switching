# D258 part 2: device-latency rescore

Rescore of every committed cell with the measured per-item Orin device latency charged to each
type's deadline, re-derived from committed `cell.json` + `request.jsonl` (the committed scorer is not
changed). Module `experiments/analysis/devlat_rescore.py`; output
`results/device/study_devlat/devlat_rescore.json`. CPU, read-only, no plots.

## Measured latency vs deadline

| type | deadline | measured source | measured range | can it miss the deadline? |
|---|---|---|---|---|
| recall | 3 s (completion) | `data_sources.device_recall_latency_s(history_tokens)` | 0.146 to 0.221 s (clamped at 28k tok) | no, 14x margin |
| single-shot | 2 s (completion) | `single_shot_total_s[question_id]` | 0.281 to 3.409 s | yes, 126 of 1042 questions over 2 s |
| dashcam (EP-G) | 1 s (first token) | append ttft | 0.235 to 0.366 s | no, append is 3x under |

## Finding

The rescore changes nothing not already in the committed numbers, so the D250 verdict is robust to
measured device latency.

- **Recall: device-late = 0 in all 177 cells** (max recall latency 0.221 s against the 3 s
  deadline), so robot cbd is identical committed vs rescored in every cell. The committed scoring
  left recall `n_device_late` uncomputed (None); the rescore confirms it is 0, not merely unlisted.
- **Single-shot: rescored device-late equals committed device-late in every cell** (0 mismatches).
  The committed scoring already charged the measured per-item single-shot latency (committed
  `device_latency_s` equals `single_shot_total_s` exactly, and refspatial questions over 2 s already
  carry `device_within_deadline=False`). 126 questions exceed 2 s, but they only cost an arm when the
  device is its standing source and the cloud did not cover; where they bite, the committed numbers
  already reflect it.
- **Dashcam (EP-G): device-late = 0** by bound. The warm append path tops out at 0.366 s against the
  1 s first-token deadline. (A full re-send / start path reaches 3.13 s and would miss, but every
  committed cell here is `_epg_` append.)

## D250 margin (robot cbd, rung 3 against best baseline), kv0.5r_h0.5 s4

| arm | robot cbd committed | robot cbd rescored |
|---|---|---|
| confidence-cascade | 0.4242 (56/132) | 0.4242 |
| covex-v6-base (best baseline) | 0.4621 (61/132) | 0.4621 |
| rung 3 covex-v6-fair-final | 0.5455 (72/132) | 0.5455 |

**Margin rung 3 minus best baseline = +0.0833 under both.** No cell in the D250 set or the
1x / kv0.5r s4-s7 grid changes its winner under the measured device latency.

## Consistency

- Robot cbd rescored equals committed by construction (recall device-late 0), so the margin cannot
  move; cross-check against the committed D250 figure holds trivially.
- Latencies are physically consistent with `orin_device_latency_tables.json` (recall 0.15-0.22 s
  warm TTFT; single-shot 0.28-3.41 s completion; dashcam 0.24-0.37 s append TTFT).
- Positive control: single-shot rescored device-late reproduces the committed device-late in every
  cell (0 mismatches), so the rescore machinery agrees with the committed scorer where the latter
  already charges latency.
