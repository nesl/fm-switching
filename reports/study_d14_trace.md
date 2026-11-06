# StudyD14-trace: whole-clip score traces on the Nexar validation clips

**E-id:** StudyD14-trace (pre-registered 2026-11-05, before rendering or any GPU run; authorised by the user).

**Status:** finished 2026-11-05 14:37–17:21 on h100nvl GPU 2.
- 53,300 scored requests + 500 grey; 0 errors, 0 retries, 0 still failed, 0 neither-Yes-nor-No.

**Purpose and scope:** score traces for a later offline simulation of standing queries under shared capacity.
- **This job makes no policy claim.** No policy, threshold or tuned operating point was fitted or evaluated.
- CLAUDE.md mechanism verification applies to that later simulation. For this job, the input checks and the grey negative control are recorded below.
- No latency is reported: this was a batched run at concurrency 8.

**Sources (`results/dashcam/study_d14_trace/`):**

| file | contents |
|---|---|
| `d14_requests_manifest.jsonl.gz` | per (clip, t, N): labels, frame keys / pts / SHA-256, header |
| `frames_sha256_manifest.jsonl.gz` | |
| `d14_sample.json` | |
| `d14_requests_h100nvl.jsonl.gz` | raw rows, every attempt |
| `d14_trace_h100nvl.jsonl.gz` | **the trace for the simulation:** one row per arm × clip × t, with P(Yes), score, label, t, time_of_event, time_of_alert, duration, scene, light, weather |
| `d14_flow_features.csv.gz` | |
| `prompt_trace_N{1,3,9}.txt` | |
| `d14_run_meta_h100nvl.json` | |
| `d14_results_h100nvl.json` | |

**Frames:** outside the repo at `~/data/dashcam/d14_frames/small/`; 86,180 PNGs, 31.6 GB.

**Scripts:** `experiments/dashcam/d14_prepare.py`, `d14_infer_vllm.py` (reuses `d3_infer_vllm.py` unchanged), `d14_flow.py`, `d14_analyse.py`.

## Setup
- **Clips:** all 300 VALIDATION clips of `nexar_train_split_seed0.csv` (150 positive, 150 negative). The split was cross-checked against `d2_prepare.split` and durations against the probe record. No test or development clip was read.
- **Decision times:** t = 3, 4, …, floor(duration): 10,660 (clip, t). No reference time.
- **Input:** StudyD3's input at SMALL 768×432.
  - Window = last 3 s before t; latest decoded frame with pts ≤ target (PyAV).
  - N = 1 is the last frame; N = 3 / 9 are evenly spaced.
  - D3 header and query, separate images oldest first.
  - Every request has frames at or before t (asserted at build, and re-checked in analysis).
- **Arms, in run order:**

  | arm | rows |
  |---|---|
  | 4B-I @ebb281ec N = 1, N = 3 | 21,520 incl. grey |
  | 32B-I @0cfaf481 N = 1, N = 3, N = 9 | 32,280 incl. grey |

- **Stack:** D-series vLLM 0.31.0, FA3, prefix caching off, `--mm-processor-cache-gb 0`, greedy, max_tokens 8, logprobs top 20, seed 0, concurrency 8.
- **Score:** as StudyD3: P(Yes) = Yes / (Yes + No) first-token mass; score = log P(Yes) floored at 1e-12.
- **Flow:** unchanged `d2_flow.feats` (17 features) on each (clip, t)'s N = 9 prefix frames, CPU only. 10,660 rows, 0 non-finite.

## Input checks and negative control
| check | result |
|---|---|
| all frames at or before t | PASS (31,980 requests) |
| prompt trace per N (no digits besides the header's, no file name) | PASS: N = 1 / 3 / 9 at 378 / 1,062 / 3,090 tokens, as StudyD3 |
| identical frames across models per (clip, t, N) | N = 1 and N = 3: 10,660 / 10,660 compared, 0 frame-hash mismatches, 0 manifest mismatches |
| identical prompt tokens across models | 0 mismatches |
| grey-frame control (100 per arm) | Yes rate 0 in all 5 arms; median P(Yes) ≤ 1.3e-5 |

## Observations

### (b) AUROC: each positive clip's row at the whole-second t nearest time_of_event, against ALL negative rows of the arm
150 positive clips vs 5,196 negative rows (150 clips); 2,000-sample clip bootstrap, seed 0.

| arm | AUROC [95 % CI] | StudyD3 offset-0 AUROC (scored positives vs offset-0 negatives) |
|---|---|---|
| 4B-I N = 1 | 0.738 [0.687, 0.784] | 0.710 |
| 4B-I N = 3 | 0.773 [0.729, 0.814] | 0.722 |
| 32B-I N = 1 | 0.778 [0.733, 0.820] | 0.772 |
| 32B-I N = 3 | 0.841 [0.806, 0.873] | 0.805 |
| 32B-I N = 9 | 0.825 [0.788, 0.858] | 0.811 |

**The D3 column is NOT like-for-like:**
- Different clips: validation here vs development in D3.
- Different negatives: all negative-clip times here, vs negatives at one assigned reference time in D3.
- t here is rounded to the nearest whole second, so the frames end up to 0.5 s before or after the event.

### (a) Median score over time (log P(Yes))
Positives are aligned to the event (rel = t − time_of_event, nearest whole second); negatives are by clip time t.

| arm | pos −10 s | −5 | −3 | −2 | −1 | 0 | +1 | +2 | +3 | +5 | neg t = 3 / 10 / 20 / 30 / 40 s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 4B-I N1 | −10.8 | −10.3 | −10.3 | −9.8 | −7.8 | −6.3 | −7.8 | −8.0 | −9.3 | −9.6 | −11.0 / −11.6 / −11.3 / −12.5 / −12.3 |
| 4B-I N3 | −7.5 | −7.0 | −6.8 | −5.5 | −4.3 | −3.5 | −4.0 | −3.8 | −6.3 | −8.5 | −8.5 / −7.5 / −6.5 / −8.3 / −9.5 |
| 32B-I N1 | −16.1 | −15.5 | −14.8 | −14.4 | −11.0 | −9.1 | −11.3 | −12.0 | −13.0 | −14.7 | −17.2 / −16.4 / −16.5 / −17.5 / −17.5 |
| 32B-I N3 | −14.6 | −14.6 | −13.9 | −12.1 | −10.0 | −6.8 | −8.1 | −8.8 | −10.8 | −13.5 | −16.1 / −15.9 / −13.8 / −14.6 / −16.1 |
| 32B-I N9 | −14.9 | −15.5 | −14.3 | −13.5 | −11.9 | −9.0 | −8.4 | −10.3 | −12.3 | −14.4 | −16.6 / −16.0 / −14.9 / −16.0 / −16.6 |

- Bin 0 holds 153 rows: 150 clips, plus 3 clips with two t values rounding to the event second.
- Quartiles for every bin are in `d14_results_h100nvl.json`.

### Raw Yes on negative clips
P(Yes) > 0.5, one decision per second, 1.44 h of negative clip time per arm. **RAW: not a tuned false-alarm rate.**

| arm | Yes rows / 5,196 | raw Yes per hour | negative clips with ≥ 1 Yes (of 150) | Yes rate, all rows |
|---|---|---|---|---|
| 4B-I N1 | 103 | 71.4 | 32 | 2.5 % |
| 4B-I N3 | 291 | 201.6 | 85 | 5.5 % |
| 32B-I N1 | 56 | 38.8 | 27 | 2.3 % |
| 32B-I N3 | 70 | 48.5 | 39 | 1.7 % |
| 32B-I N9 | 32 | 22.2 | 14 | 0.9 % |

### Requests, errors, disk
- **Requests:** 10,660 per arm + 100 grey per arm = 53,800 rows. 0 error rows (so no retries), 0 still failed, 0 neither-Yes-nor-No.
- **Frames:** 31.6 GB outside the repo (86,180 unique PNGs; the 3 s windows overlap only partly at a 1 s step).
- **Repo results directory:** 40 MB; the largest file is 8.4 MB, so nothing needed splitting.

## Results consistency check
**1. Cross-check against committed measurements.**

| quantity | this run | prior | source | ratio | agree? |
|---|---|---|---|---|---|
| prompt tokens N = 1 / 3 / 9 | 378 / 1,062 / 3,090 | 378 / 1,062 / 3,090 | StudyD3, D4 | 1.00 | agree |
| grey Yes rate | 0 | 0 | StudyD2 / D3 | — | agree |
| 32B-I N9 event-time AUROC | 0.825 | 0.811 | StudyD3 offset 0 | 1.02 | agree (not like-for-like) |
| 4B-I N3 event-time AUROC | 0.773 | 0.722 | StudyD3 offset 0 | 1.07 | agree within 2× (not like-for-like) |

**2. Physical plausibility.** No latency or throughput measured; N/A.

**3. Distribution sanity.**
- Score medians vary over time and by label; quartiles reported.
- Grey scores are near-constant, as a control should be.
- Real-frame Yes rates are 0.9–5.5 %.
- No unexpected constants. **PASS.**

**4. Definition audit.**
- Window, frame choice, header, query and score are D3's.
- The only differences from D3 are those registered: validation clips and the whole-second grid.
- "Raw Yes per hour" = P(Yes) > 0.5 count per hour of 1-Hz decisions on negative clips. **PASS.**

**5. Claim linkage.**
- These are input data for a later simulation of standing queries under shared capacity (FORMULATION.md: which capability to provision, and when).
- **This job makes no claim.** The numbers are sanity checks of the traces only.

**6. Proxy validity.**
- time_of_event is Nexar's annotation.
- Negative clips stand in for event-free driving, but are short (≤ 58 s), so the raw per-hour rate is extrapolated from 1.44 h per arm.
- Stated as a limitation of the sanity numbers; it is not used for any claim.

## Interpretation (sanity only; no policy claim)
- **The traces behave as expected for the later simulation:**
  - Scores rise around the event and fall afterwards.
  - Negatives stay low.
  - Event-time ranking is in line with StudyD3's offset-0 values for every arm, despite different clips and negatives.
- **32B-I at N = 3 and N = 9 has the fewest raw Yes on negatives.** 4B-I at N = 3 has the most: 5.5 % of rows, 85 of 150 negative clips.
- Any operating point for the simulation must be fitted there, under its own mechanism verification, not read from this table.
