# StudyD14b-dense: sub-second Nexar score trace (0.25-s grid)

E-id: StudyD14b-dense (`research/EXPERIMENTS.md`, pre-registered 2026-11-11). Host: h100nvl **GPU 2** (GPU-4f1d7e47-e769-a289-4860-e71c0d97267c). Batched; **no latency is measured**.

## 0. Purpose and verification recorded before the sweep

**Why.** StudyE9 and StudyE12 replay D14's 1-s decision grid, so every latency rounds up to a whole second. That makes device (0.567 s) and cloud (about 0.4 s) deliver equally late, and at h = 0.5 s under measured latency both sit near chance. A 0.25-s grid removes that confound.

**This job produces input data and makes no policy claim.** As with D14, CLAUDE.md's mechanism verification applies to the later simulation that consumes the trace. For this job, the checks recorded before the sweep are the input checks, the determinism control and the grey negative control.

**Preparation (CPU, done before any GPU run).** `d14b_prepare.py`:
- the same 300 VALIDATION clips (150 / 150) as D14;
- t = 3.0, 3.25, … up to each clip's last full 0.25-s step: **42,014 decisions** (10,660 of them integer t);
- D14's frame rule and renderer.

| check | result |
|---|---|
| all frames at or before t | PASS (84,028 requests) |
| integer-t requests byte-identical to D14's (frame SHA-256 + header) | **21,320 / 21,320** |
| unique frames | 45,614: 43,551 hard-linked from D14's PNGs (byte-identical, no extra disk), 2,063 newly rendered (0.75 GB) |
| frames directory (outside the repo) | `~/data/dashcam/d14b_frames/small/` (16.7 GB logical, 0.75 GB new on disk) |

**Controls during the sweep (STOP conditions, set in advance):**
- **Determinism.** Per arm, the integer-t requests run first, and their P(Yes) must equal D14's committed value exactly on ≥ 99 %. Otherwise the run STOPs before any sub-second request. If it passes, any sub-second difference is input, not stack.
- **Grey control.** 100 uniform-grey requests per arm, as D14. The Yes rate must be ≈ 0.
- Transport retries: 2.
- STOP if > 1 % remain failed, on a server-log error, if > 1 % of rows have neither Yes nor No, or if a foreign process appears on GPU 2.

**Run plan.**
- 4B-I N = 1 (server 1).
- 32B-I N = 1 and N = 3 (server 2).
- After StudyE10a-full: 4B-I N = 3, **secondary**.
- Estimated GPU time: 13 + 53 + 136 min, + 25 min secondary (D14's throughput per arm).

## 1. Run (2026-11-11, 17:39–22:46)

| arm | server | requests (decisions + grey) | ok | errors / retried / still failed | neither Yes nor No | prompt tokens | determinism (integer t = D14) |
|---|---|---|---|---|---|---|---|
| 4B-I N = 1 | 4B @ebb281ec | 42,014 + 100 | 42,114 | 0 / 0 / 0 | 0 | 378 (all) | **10,660 / 10,660** |
| 32B-I N = 1 | 32B @0cfaf481 | 42,014 + 100 | 42,114 | 0 / 0 / 0 | 0 | 378 (all) | **10,660 / 10,660** |
| 32B-I N = 3 | 32B @0cfaf481 | 42,014 + 100 | 42,114 | 0 / 0 / 0 | 0 | 1,062 (all) | **10,660 / 10,660** |
| 4B-I N = 3 (**secondary**) | 4B @ebb281ec | 42,014 + 100 | 42,114 | 0 / 0 / 0 | 0 | 1,062 (all) | **10,660 / 10,660** |

- Stack: vLLM 0.31.0, torch 2.13.0+cu129, prefix caching OFF, processor cache 0, temperature 0, max_tokens 8, seed 0, top-20 logprobs, concurrency 8 — D14 / D3's request form, unchanged.
- **Determinism: 42,640 / 42,640 integer-t P(Yes) values are bit-identical to D14's committed trace** (threshold was ≥ 99 %). Every sub-second difference in the trace is therefore input (the frame at that time), not stack.
- **Grey control: Yes rate 0 / 100 in every arm** (median P(Yes): 4B N1 1.3e-5, 32B N1 8.2e-9, 32B N3 3.0e-9, 4B N3 6.8e-8).
- Prompt-trace check (header text, no digits outside the header) passed for N = 1 and N = 3.
- All 300 clips have complete 0.25-s trajectories in every arm.

**Trace.** `results/dashcam/study_d14b/d14b_trace_h100nvl.jsonl.gz` (168,056 rows = 4 arms × 42,014; D14's row format with `t` a float on the 0.25-s grid, plus `d14_request_id` for integer t). Raw rows `d14b_requests_h100nvl.jsonl.gz`; meta `d14b_run_meta_h100nvl.json`; summary `d14b_results_h100nvl.json`.

## 2. Zero-latency AP (E5 Part G / E9 method)

Positive = each positive clip's decision at round((time_of_event − h) / step) on the absolute grid (E9's rule, clipped to the clip's range); negatives = every decision on every negative clip; clip bootstrap 2,000, seed 0, stratified by label (one resample per draw, shared across horizons). 150 positives in both grids.

**Integer-1 s subsample (= D14's grid; 5,196 negatives, base rate 0.0281).** Reproduces StudyE9's committed zero-latency baselines **exactly, point estimates and CIs** (device-only = 4B N1; always-cloud 32B N1 / N3) — an end-to-end check of the trace writer and the AP code.

| arm | h = 0 | 0.25 | 0.5 | 0.75 | 1.0 | 1.5 | 2.0 |
|---|---|---|---|---|---|---|---|
| 4B N1 | 0.102 [0.068, 0.152] | 0.073 [0.054, 0.115] | 0.062 [0.048, 0.090] | 0.060 [0.046, 0.087] | 0.051 [0.041, 0.070] | 0.040 [0.033, 0.052] | 0.037 [0.031, 0.047] |
| 32B N1 | 0.147 [0.099, 0.207] | 0.120 [0.081, 0.173] | 0.107 [0.077, 0.157] | 0.092 [0.068, 0.133] | 0.072 [0.056, 0.099] | 0.048 [0.039, 0.062] | 0.041 [0.034, 0.052] |
| 32B N3 | 0.182 [0.128, 0.250] | 0.146 [0.104, 0.205] | 0.113 [0.082, 0.157] | 0.090 [0.066, 0.125] | 0.067 [0.054, 0.086] | 0.049 [0.040, 0.061] | 0.043 [0.036, 0.053] |
| 4B N3 (secondary) | 0.141 [0.096, 0.201] | 0.107 [0.073, 0.159] | 0.079 [0.058, 0.120] | 0.068 [0.051, 0.100] | 0.054 [0.043, 0.073] | 0.040 [0.033, 0.055] | 0.038 [0.032, 0.046] |

On the 1-s grid, h = 0.25 and 0.75 are rounded to a whole second (banker's rounding on the absolute grid), so those columns are not new information.

**Dense 0.25-s grid (20,467 negatives, base rate 0.0073 — chance AP is about 4× lower than on the 1-s grid).**

| arm | h = 0 | 0.25 | 0.5 | 0.75 | 1.0 | 1.5 | 2.0 |
|---|---|---|---|---|---|---|---|
| 4B N1 | 0.028 [0.016, 0.050] | 0.036 [0.018, 0.064] | 0.019 [0.014, 0.031] | 0.015 [0.012, 0.020] | 0.013 [0.011, 0.018] | 0.011 [0.009, 0.014] | 0.010 [0.008, 0.014] |
| 32B N1 | 0.053 [0.028, 0.089] | 0.061 [0.033, 0.100] | 0.042 [0.025, 0.073] | 0.020 [0.016, 0.029] | 0.017 [0.013, 0.024] | 0.014 [0.011, 0.019] | 0.011 [0.009, 0.014] |
| 32B N3 | 0.091 [0.052, 0.143] | 0.053 [0.033, 0.088] | 0.044 [0.026, 0.075] | 0.022 [0.016, 0.033] | 0.016 [0.013, 0.023] | 0.013 [0.011, 0.017] | 0.011 [0.010, 0.014] |
| 4B N3 (secondary) | 0.062 [0.035, 0.114] | 0.028 [0.020, 0.048] | 0.021 [0.015, 0.036] | 0.016 [0.012, 0.029] | 0.015 [0.012, 0.020] | 0.011 [0.009, 0.014] | 0.010 [0.008, 0.012] |

**Reading (descriptive; this job makes no policy claim).**
1. **AP is not comparable across the two grids.** The dense grid has 3.9× as many negatives per positive, so every AP falls; compare arms within a grid, or as a multiple of chance. As multiples of chance at h = 0: 1-s grid 3.6× / 5.2× / 6.5× (4B N1 / 32B N1 / 32B N3); dense grid 3.9× / 7.3× / 12.6×.
2. **Arm ordering at h = 0 is the same on both grids** (32B N3 > 32B N1 > 4B N1; 4B N3 between). CIs overlap between neighbouring arms.
3. **Signal decays faster than the 1-s grid suggested.** On the dense grid, every arm is within about 1.4–3× chance from h = 0.75 s on, and all four arms' CIs overlap from h = 0.75 s. Most of the separation lives in the last 0.5 s before the labelled event.
4. **h = 0.25 is above h = 0 for 4B N1 and 32B N1** (0.036 vs 0.028; 0.061 vs 0.053). CIs overlap heavily; with 150 positives one decision per clip, this is within noise. Not interpreted.
5. This is the input the later latency simulation needs: device (0.567 s) and cloud (about 0.4 s) delivery now land on different 0.25-s decisions instead of the same whole second.

## 3. Consistency protocol (6 checks)

1. **Pre-registered and unchanged.** Grid, arms, request form, determinism threshold, grey control and AP method are as in the EXPERIMENTS row; nothing was changed after seeing results.
2. **Controls pass.** Determinism 42,640 / 42,640 (≥ 99 % required); grey 0 / 400 Yes; all-causal frames; integer-t inputs byte-identical to D14 (21,320 / 21,320).
3. **Reproduces committed numbers.** Integer-grid AP and CIs equal StudyE9's zero-latency baselines exactly (4B N1, 32B N1, 32B N3) and E9's secondary 4B N3 arm.
4. **Complete data.** 168,456 / 168,456 rows OK, 0 retried, 0 still failed, 0 neither; 300 / 300 complete trajectories per arm.
5. **Caching state labelled.** Prefix caching OFF, processor cache 0, every arm; warm and cold are not mixed (no timing measured).
6. **Scope.** Batched throughput run on H100 GPU 2; no latency, no device claim. 4B N3 is labelled secondary (the Orin cannot sustain N = 3 at 1 Hz, StudyD4-orin).

## 4. Verdict

**Complete — trace delivered, controls pass.** The 0.25-s Nexar trace exists for 4B N1, 32B N1 and 32B N3 (plus secondary 4B N3) on all 300 D14 clips, with integer-t scores bit-identical to D14. No policy claim is made here; the dense trace is input for re-running StudyE9 / StudyE12's latency replay without whole-second rounding.
