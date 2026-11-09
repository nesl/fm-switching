# StudyE1-nexar-lead: does cloud 32B raise a correct alarm earlier than device 4B?

**E-id:** StudyE1-nexar-lead (pre-registered 2026-11-09 ~15:20, before any computation; authorised by the user).

**Status:** COMPLETE 2026-11-09.

**Label:** **OFFLINE ANALYSIS OF EXISTING SCORES.** It uses StudyD14-trace's validation score traces only. No new inference, CPU only, and no test clip was read.

**Question:** per event, how much earlier does cloud 32B raise a correct alarm than device 4B? This is asked at deployable false-alarm rates, after delivery latency, and for several escalation signals.

**Script:** `experiments/orchestration/study_e1_nexar_lead.py` (run with the dashcam venv for scikit-learn).

**Results:** `results/orchestration/study_e1/e1_results.json`.

## Data and definitions
- **Source:** `results/dashcam/study_d14_trace/` (StudyD14-trace, COMPLETE).
  - 300 validation clips (150 positive, 150 negative); one decision per second, t = 3 … floor(duration); 10,660 decision seconds.
  - Arms: 4B-I N = 1 / 3 and 32B-I N = 1 / 3 / 9. Score = log P(Yes).
- **Input, stack and decoding:** for matched N, the two models saw identical frames and prompt tokens (D14 check: 0 frame-hash and 0 prompt-token mismatches). Same vLLM stack, greedy decoding. 32B N = 9 vs 4B N = 3 differs in frame count (9 vs 3 frames); this is stated wherever it is compared.
- **Cross-fitting:** 2 folds by clip, stratified by label, seed 0 (StratifiedKFold); 150 / 150 clips, 75 positives per test fold. Every threshold is fit on the training fold and evaluated on the other fold, then the folds are swapped and pooled.
- **Alarm rule (primary):** the rule fires at a second whose score is ≥ the threshold; the first alarm is a clip's first firing second. **Secondary:** 2 of the last 3 consecutive seconds ≥ threshold.
- **False alarm (pre-registered definition):** a negative-clip decision second at which the rule fires. FA / h = count / hours of negative decision time.
  - Negative time is 1.44 h in total, about 0.72 h per fold. The lowest training-fold FA target, 1 / h, therefore allows 0 training false alarms.
- **Part B latency:**
  - Device: Orin 4B total 0.555 / 1.394 / 3.926 s (N = 1 / 3 / 9).
  - Cloud: H100 32B total 0.162 / 0.285 / 0.640 s + upload + RTT.
  - Upload = request image bytes × 8 / uplink, with raw RGB 995,328 B per frame, and PNG / JPEG q90 at the D4 medians.
  - TCP slow start is ignored. **JPEG accuracy was never measured**, so JPEG rows assume unchanged scores.
- **Network values cited:**
  - 13.6 Mbit/s uplink and 44 ms latency: Ookla H2 2025 US 5G median;
  - 12 Mbit/s: Khan et al. 2024, Bay Area 5G median;
  - 88 Mbit/s: Oslo;
  - 22 ms median and 55–65 ms tail: the ICCCN paper.
  - Sweep: uplink 5 / 12 / 13.6 / 25 / 88 Mbit/s × RTT 22 / 44 / 142 ms.
- **Part C escalation:**
  - Signals: 4B P(Yes); 4B log P(Yes) rise over the last 2 s; flow LR; random.
  - The flow LR is a standardised logistic regression on D2's 17 flow features. y = 1 for positive-clip seconds in [event − 3, event + 2] and y = 0 for negative-clip seconds; it is fit on the training fold only.
  - Budget = share of seconds escalated (5 / 10 / 25 / 50 %), set by the training-fold signal quantile. The 32B threshold is fit on training-fold escalated negative seconds for 5 FA / h overall.
  - **Latency added:** 4B-based signals add the device 4B latency. The flow signal adds 0.261 s (D4-orin Part C d2_flow cost on the Orin CPU, measured at 384 × 216). Random adds 0. Cloud latency is computed at 13.6 Mbit/s, 44 ms, raw frames.
- **Sign convention:** all differences are **32B − 4B** in seconds; negative = 32B earlier.

## Sanity checks (all run first)
| check | result |
|---|---|
| reproduce D14 event-time AUROCs (positive at round(event) vs all negative rows) within 0.002 | **PASS, exact** (|diff| = 0.000 for all 5 arms: 0.738 / 0.773 / 0.778 / 0.841 / 0.825) |
| grey rows excluded | the trace contains no grey rows (0 found) |
| every positive has time_of_event | 150 / 150 |
| FA target met within ×2 on held-out folds | **shortfall in 4 of 30 Part A cells, all at the 1 / h target:** primary 32BI_N9 2.8 / h; 2-of-3 4BI_N3 4.8, 32BI_N3 6.9, 32BI_N9 3.5 / h. All Part C policies and baselines are within ×2 of 5 / h (2.1–9.0) |

## Observations (no interpretation in this section)

### Part A tables

**Primary rule (first second ≥ threshold); thresholds cross-fitted.**

| arm | FA target / h | held-out FA / h (≤ 2× target?) | detected / 150 | median first alarm − event (s) [p25, p75] | median − alert (s) | timing: early < −3 s / near [−3, +2] / late > +2 s / none |
|---|---|---|---|---|---|---|
| 4BI_N1 | 1 | 0.7 (yes) | 5 (3.3 %) | 0.43 [0.30, 0.51] | 1.77 | 1 / 4 / 0 / 145 |
| 4BI_N3 | 1 | 0.7 (yes) | 5 (3.3 %) | 0.10 [-0.43, 0.10] | 0.84 | 1 / 4 / 0 / 145 |
| 32BI_N1 | 1 | 0.7 (yes) | 11 (7.3 %) | 0.95 [0.20, 7.65] | 2.62 | 2 / 4 / 5 / 139 |
| 32BI_N3 | 1 | 0.7 (yes) | 7 (4.7 %) | 0.10 [0.03, 0.34] | 1.24 | 0 / 7 / 0 / 143 |
| 32BI_N9 | 1 | 2.8 (**NO**) | 4 (2.7 %) | -0.16 [-2.53, 0.14] | 0.75 | 1 / 3 / 0 / 146 |
| 4BI_N1 | 5 | 3.5 (yes) | 9 (6.0 %) | 0.30 [-7.42, 0.51] | 1.30 | 3 / 5 / 1 / 141 |
| 4BI_N3 | 5 | 3.5 (yes) | 10 (6.7 %) | 0.18 [-0.30, 0.40] | 1.14 | 1 / 7 / 2 / 140 |
| 32BI_N1 | 5 | 4.8 (yes) | 13 (8.7 %) | 0.30 [-0.42, 2.79] | 1.77 | 2 / 6 / 5 / 137 |
| 32BI_N3 | 5 | 3.5 (yes) | 9 (6.0 %) | 0.10 [-0.30, 0.25] | 1.03 | 1 / 8 / 0 / 141 |
| 32BI_N9 | 5 | 3.5 (yes) | 4 (2.7 %) | -0.16 [-2.53, 0.14] | 0.75 | 1 / 3 / 0 / 146 |
| 4BI_N1 | 20 | 19.4 (yes) | 25 (16.7 %) | 0.30 [-4.90, 2.03] | 1.62 | 7 / 11 / 7 / 125 |
| 4BI_N3 | 20 | 23.6 (yes) | 28 (18.7 %) | 0.10 [-0.34, 0.64] | 1.27 | 5 / 18 / 5 / 122 |
| 32BI_N1 | 20 | 18.0 (yes) | 29 (19.3 %) | 0.37 [-0.43, 3.20] | 1.62 | 6 / 14 / 9 / 121 |
| 32BI_N3 | 20 | 18.0 (yes) | 27 (18.0 %) | 0.20 [-0.66, 1.80] | 1.30 | 4 / 16 / 7 / 123 |
| 32BI_N9 | 20 | 17.3 (yes) | 29 (19.3 %) | 0.47 [-0.05, 4.83] | 1.62 | 2 / 17 / 10 / 121 |

**Secondary rule (2-of-3 consecutive).**

| arm | FA target / h | held-out FA / h | detected / 150 | median first alarm − event (s) |
|---|---|---|---|---|
| 4BI_N1 | 1 | 1.4 | 3 | 0.43 |
| 4BI_N3 | 1 | 4.8 | 8 | 0.90 |
| 32BI_N1 | 1 | 1.4 | 7 | 8.53 |
| 32BI_N3 | 1 | 6.9 | 8 | 0.89 |
| 32BI_N9 | 1 | 3.5 | 3 | 1.10 |
| 4BI_N1 | 5 | 9.7 | 6 | 0.84 |
| 4BI_N3 | 5 | 9.7 | 9 | 0.70 |
| 32BI_N1 | 5 | 3.5 | 10 | 4.00 |
| 32BI_N3 | 5 | 8.3 | 8 | 0.70 |
| 32BI_N9 | 5 | 3.5 | 4 | 0.84 |
| 4BI_N1 | 20 | 15.2 | 11 | 1.25 |
| 4BI_N3 | 20 | 27.0 | 15 | -0.05 |
| 32BI_N1 | 20 | 20.1 | 23 | 0.95 |
| 32BI_N3 | 20 | 17.3 | 21 | 1.25 |
| 32BI_N9 | 20 | 18.7 | 17 | 1.47 |

**Paired recognition lead, 32B − 4B first-alarm time (s; negative = 32B earlier), clips detected by both; clip bootstrap 2,000.**

| rule | target | pair | input / stack / decoding | both detected | only 32B | only 4B | mean diff [CI] | median diff [CI] | 32B earlier |
|---|---|---|---|---|---|---|---|---|---|
| first | 1 | 32BI_N1-4BI_N1 | same frames, stack, greedy | 3 | 8 | 2 | 0.00 [0.00, 0.00] | 0.00 [0.00, 0.00] | 0.00 |
| first | 1 | 32BI_N3-4BI_N3 | same frames, stack, greedy | 4 | 3 | 1 | 0.00 [0.00, 0.00] | 0.00 [0.00, 0.00] | 0.00 |
| first | 1 | 32BI_N9-4BI_N3 | 9 vs 3 frames; same stack, greedy | 4 | 0 | 1 | 0.00 [0.00, 0.00] | 0.00 [0.00, 0.00] | 0.00 |
| first | 5 | 32BI_N1-4BI_N1 | same frames, stack, greedy | 5 | 8 | 4 | 1.40 [0.00, 4.20] | 0.00 [0.00, 7.00] | 0.00 |
| first | 5 | 32BI_N3-4BI_N3 | same frames, stack, greedy | 7 | 2 | 3 | 0.14 [0.00, 0.43] | 0.00 [0.00, 0.00] | 0.00 |
| first | 5 | 32BI_N9-4BI_N3 | 9 vs 3 frames; same stack, greedy | 4 | 0 | 6 | 0.00 [0.00, 0.00] | 0.00 [0.00, 0.00] | 0.00 |
| first | 20 | 32BI_N1-4BI_N1 | same frames, stack, greedy | 15 | 14 | 10 | -1.47 [-6.67, 3.33] | 0.00 [0.00, 1.00] | 0.27 |
| first | 20 | 32BI_N3-4BI_N3 | same frames, stack, greedy | 13 | 14 | 15 | 1.00 [-0.23, 3.23] | 0.00 [0.00, 0.00] | 0.08 |
| first | 20 | 32BI_N9-4BI_N3 | 9 vs 3 frames; same stack, greedy | 17 | 12 | 11 | 2.71 [0.06, 5.88] | 0.00 [0.00, 1.00] | 0.12 |
| 2of3 | 1 | 32BI_N1-4BI_N1 | same frames, stack, greedy | 1 | 6 | 2 | 0.00 [0.00, 0.00] | 0.00 [0.00, 0.00] | 0.00 |
| 2of3 | 1 | 32BI_N3-4BI_N3 | same frames, stack, greedy | 5 | 3 | 3 | 0.00 [-0.60, 0.60] | 0.00 [-1.00, 1.00] | 0.20 |
| 2of3 | 1 | 32BI_N9-4BI_N3 | 9 vs 3 frames; same stack, greedy | 3 | 0 | 5 | 0.00 [0.00, 0.00] | 0.00 [0.00, 0.00] | 0.00 |
| 2of3 | 5 | 32BI_N1-4BI_N1 | same frames, stack, greedy | 2 | 8 | 4 | 0.50 [0.00, 1.00] | 0.50 [0.00, 1.00] | 0.00 |
| 2of3 | 5 | 32BI_N3-4BI_N3 | same frames, stack, greedy | 5 | 3 | 4 | 1.00 [-0.60, 3.60] | 0.00 [-1.00, 6.00] | 0.20 |
| 2of3 | 5 | 32BI_N9-4BI_N3 | 9 vs 3 frames; same stack, greedy | 4 | 0 | 5 | 1.50 [0.00, 4.50] | 0.00 [0.00, 6.00] | 0.00 |
| 2of3 | 20 | 32BI_N1-4BI_N1 | same frames, stack, greedy | 7 | 16 | 4 | -4.57 [-11.43, 1.86] | 0.00 [-15.00, 2.00] | 0.43 |
| 2of3 | 20 | 32BI_N3-4BI_N3 | same frames, stack, greedy | 7 | 14 | 8 | 6.29 [1.00, 12.00] | 2.00 [0.00, 15.00] | 0.00 |
| 2of3 | 20 | 32BI_N9-4BI_N3 | 9 vs 3 frames; same stack, greedy | 8 | 9 | 7 | 3.75 [1.00, 7.62] | 1.50 [0.50, 7.00] | 0.00 |

**D3 reference only: event-relative AUROC curve (positive row at round(event)+k vs all negative rows).**

| arm | AUROC at k = −3 / −2 / −1 / 0 / +1 | first k with AUROC ≥ 0.70 | first k ≥ 0.75 |
|---|---|---|---|
| 4BI_N1 | 0.571 / 0.613 / 0.682 / 0.738 / 0.713 | 0 | None |
| 4BI_N3 | 0.563 / 0.614 / 0.688 / 0.773 / 0.750 | 0 | 0 |
| 32BI_N1 | 0.610 / 0.645 / 0.748 / 0.778 / 0.751 | -1 | 0 |
| 32BI_N3 | 0.591 / 0.661 / 0.748 / 0.841 / 0.808 | -1 | 0 |
| 32BI_N9 | 0.590 / 0.634 / 0.729 / 0.825 / 0.831 | -1 | 0 |

### Part B table (target 20 FA/h, where the most clips are detected by both; RTT 44 ms; other RTTs and targets in `e1_results.json`)

| pair | format | uplink Mbit/s | cloud latency (s) | device latency (s) | both detected | recognition mean diff (s) | delivered mean diff [CI] (s) | uplink for zero mean (Mbit/s) |
|---|---|---|---|---|---|---|---|---|
| 32BI_N1-4BI_N1 | raw | 5 | 1.80 | 0.555 | 15 | -1.47 | -0.22 [-5.16, 4.51] | 4.4 |
| 32BI_N1-4BI_N1 | raw | 12 | 0.87 | 0.555 | 15 | -1.47 | -1.15 [-6.42, 3.45] | 4.4 |
| 32BI_N1-4BI_N1 | raw | 13.6 | 0.79 | 0.555 | 15 | -1.47 | -1.23 [-6.16, 3.70] | 4.4 |
| 32BI_N1-4BI_N1 | raw | 25 | 0.52 | 0.555 | 15 | -1.47 | -1.50 [-6.43, 3.64] | 4.4 |
| 32BI_N1-4BI_N1 | raw | 88 | 0.30 | 0.555 | 15 | -1.47 | -1.73 [-6.59, 3.34] | 4.4 |
| 32BI_N1-4BI_N1 | png | 5 | 0.77 | 0.555 | 15 | -1.47 | -1.25 [-6.25, 3.49] | 1.6 |
| 32BI_N1-4BI_N1 | png | 12 | 0.44 | 0.555 | 15 | -1.47 | -1.58 [-6.51, 3.15] | 1.6 |
| 32BI_N1-4BI_N1 | png | 13.6 | 0.41 | 0.555 | 15 | -1.47 | -1.61 [-6.61, 3.53] | 1.6 |
| 32BI_N1-4BI_N1 | png | 25 | 0.32 | 0.555 | 15 | -1.47 | -1.70 [-6.77, 3.23] | 1.6 |
| 32BI_N1-4BI_N1 | png | 88 | 0.24 | 0.555 | 15 | -1.47 | -1.78 [-6.72, 3.22] | 1.6 |
| 32BI_N1-4BI_N1 | jpeg_q90 | 5 | 0.30 | 0.555 | 15 | -1.47 | -1.72 [-6.92, 3.15] | 0.3 |
| 32BI_N1-4BI_N1 | jpeg_q90 | 12 | 0.25 | 0.555 | 15 | -1.47 | -1.78 [-6.78, 3.42] | 0.3 |
| 32BI_N1-4BI_N1 | jpeg_q90 | 13.6 | 0.24 | 0.555 | 15 | -1.47 | -1.78 [-6.65, 3.02] | 0.3 |
| 32BI_N1-4BI_N1 | jpeg_q90 | 25 | 0.23 | 0.555 | 15 | -1.47 | -1.80 [-7.13, 2.94] | 0.3 |
| 32BI_N1-4BI_N1 | jpeg_q90 | 88 | 0.21 | 0.555 | 15 | -1.47 | -1.81 [-6.81, 3.12] | 0.3 |
| 32BI_N3-4BI_N3 | raw | 5 | 5.11 | 1.394 | 13 | 1.00 | 4.71 [3.48, 6.94] | 367.5 |
| 32BI_N3-4BI_N3 | raw | 12 | 2.32 | 1.394 | 13 | 1.00 | 1.93 [0.69, 4.16] | 367.5 |
| 32BI_N3-4BI_N3 | raw | 13.6 | 2.09 | 1.394 | 13 | 1.00 | 1.69 [0.46, 3.92] | 367.5 |
| 32BI_N3-4BI_N3 | raw | 25 | 1.28 | 1.394 | 13 | 1.00 | 0.89 [-0.34, 3.12] | 367.5 |
| 32BI_N3-4BI_N3 | raw | 88 | 0.60 | 1.394 | 13 | 1.00 | 0.21 [-1.02, 2.44] | 367.5 |
| 32BI_N3-4BI_N3 | png | 5 | 2.02 | 1.394 | 13 | 1.00 | 1.63 [0.40, 3.86] | 130.2 |
| 32BI_N3-4BI_N3 | png | 12 | 1.03 | 1.394 | 13 | 1.00 | 0.64 [-0.59, 2.87] | 130.2 |
| 32BI_N3-4BI_N3 | png | 13.6 | 0.95 | 1.394 | 13 | 1.00 | 0.56 [-0.67, 2.79] | 130.2 |
| 32BI_N3-4BI_N3 | png | 25 | 0.67 | 1.394 | 13 | 1.00 | 0.27 [-0.96, 2.50] | 130.2 |
| 32BI_N3-4BI_N3 | png | 88 | 0.43 | 1.394 | 13 | 1.00 | 0.03 [-1.20, 2.26] | 130.2 |
| 32BI_N3-4BI_N3 | jpeg_q90 | 5 | 0.61 | 1.394 | 13 | 1.00 | 0.22 [-1.01, 2.45] | 21.9 |
| 32BI_N3-4BI_N3 | jpeg_q90 | 12 | 0.45 | 1.394 | 13 | 1.00 | 0.05 [-1.18, 2.28] | 21.9 |
| 32BI_N3-4BI_N3 | jpeg_q90 | 13.6 | 0.43 | 1.394 | 13 | 1.00 | 0.04 [-1.19, 2.27] | 21.9 |
| 32BI_N3-4BI_N3 | jpeg_q90 | 25 | 0.39 | 1.394 | 13 | 1.00 | -0.01 [-1.24, 2.22] | 21.9 |
| 32BI_N3-4BI_N3 | jpeg_q90 | 88 | 0.35 | 1.394 | 13 | 1.00 | -0.05 [-1.28, 2.18] | 21.9 |
| 32BI_N9-4BI_N3 | raw | 5 | 15.02 | 1.394 | 17 | 2.71 | 16.33 [13.74, 19.56] | never (recognition already later) |
| 32BI_N9-4BI_N3 | raw | 12 | 6.66 | 1.394 | 17 | 2.71 | 7.97 [5.44, 10.97] | never (recognition already later) |
| 32BI_N9-4BI_N3 | raw | 13.6 | 5.95 | 1.394 | 17 | 2.71 | 7.27 [4.74, 10.38] | never (recognition already later) |
| 32BI_N9-4BI_N3 | raw | 25 | 3.55 | 1.394 | 17 | 2.71 | 4.86 [2.33, 8.16] | never (recognition already later) |
| 32BI_N9-4BI_N3 | raw | 88 | 1.50 | 1.394 | 17 | 2.71 | 2.81 [0.16, 5.87] | never (recognition already later) |
| 32BI_N9-4BI_N3 | png | 5 | 5.79 | 1.394 | 17 | 2.71 | 7.10 [4.51, 10.16] | never (recognition already later) |
| 32BI_N9-4BI_N3 | png | 12 | 2.81 | 1.394 | 17 | 2.71 | 4.12 [1.53, 7.36] | never (recognition already later) |
| 32BI_N9-4BI_N3 | png | 13.6 | 2.56 | 1.394 | 17 | 2.71 | 3.87 [1.34, 7.05] | never (recognition already later) |
| 32BI_N9-4BI_N3 | png | 25 | 1.70 | 1.394 | 17 | 2.71 | 3.02 [0.37, 6.43] | never (recognition already later) |
| 32BI_N9-4BI_N3 | png | 88 | 0.97 | 1.394 | 17 | 2.71 | 2.29 [-0.30, 5.40] | never (recognition already later) |
| 32BI_N9-4BI_N3 | jpeg_q90 | 5 | 1.53 | 1.394 | 17 | 2.71 | 2.84 [0.20, 5.90] | never (recognition already later) |
| 32BI_N9-4BI_N3 | jpeg_q90 | 12 | 1.04 | 1.394 | 17 | 2.71 | 2.35 [-0.24, 5.41] | never (recognition already later) |
| 32BI_N9-4BI_N3 | jpeg_q90 | 13.6 | 1.00 | 1.394 | 17 | 2.71 | 2.31 [-0.34, 5.31] | never (recognition already later) |
| 32BI_N9-4BI_N3 | jpeg_q90 | 25 | 0.85 | 1.394 | 17 | 2.71 | 2.17 [-0.48, 5.23] | never (recognition already later) |
| 32BI_N9-4BI_N3 | jpeg_q90 | 88 | 0.73 | 1.394 | 17 | 2.71 | 2.04 [-0.60, 5.16] | never (recognition already later) |

**RTT effect** (uplink for zero mean, raw / PNG / JPEG, by RTT 22 / 44 / 142 ms), target 20:

| pair | RTT (s) | raw | PNG | JPEG q90 |
|---|---|---|---|---|
| 32BI_N1-4BI_N1 | 0.022 | 4.3 | 1.5 | 0.3 |
| 32BI_N1-4BI_N1 | 0.044 | 4.4 | 1.6 | 0.3 |
| 32BI_N1-4BI_N1 | 0.142 | 4.6 | 1.7 | 0.3 |
| 32BI_N3-4BI_N3 | 0.022 | 274.6 | 97.2 | 16.3 |
| 32BI_N3-4BI_N3 | 0.044 | 367.5 | 130.2 | 21.9 |
| 32BI_N3-4BI_N3 | 0.142 | never | never | never |
| 32BI_N9-4BI_N3 | 0.022 | never | never | never |
| 32BI_N9-4BI_N3 | 0.044 | never | never | never |
| 32BI_N9-4BI_N3 | 0.142 | never | never | never |

### Part C tables (5 FA/h targets; delivered at 13.6 Mbit/s, 44 ms, raw frames)

**Baselines.**

| policy | latency (s) | held-out FA / h | detection [CI] | median delivered − event (s) [CI] |
|---|---|---|---|---|
| device-only 4BI_N1 | 0.56 | 3.5 | 0.060 [0.027, 0.100] | 0.86 [-7.38, 2.09] |
| device-only 4BI_N3 | 1.39 | 3.5 | 0.067 [0.033, 0.113] | 1.57 [0.92, 2.73] |
| cloud-always 32BI_N1 | 0.79 | 4.8 | 0.087 [0.047, 0.133] | 1.09 [0.37, 3.58] |
| cloud-always 32BI_N3 | 2.09 | 3.5 | 0.060 [0.027, 0.100] | 2.19 [1.65, 2.52] |
| cloud-always 32BI_N9 | 5.95 | 3.5 | 0.027 [0.007, 0.053] | 5.79 [-2.86, 6.21] |

**Escalation policies** (4B N → 32B N / signal / budget).

| policy | latency (s) | escalation rate | held-out FA / h | detection [CI] | median delivered − event (s) [CI] |
|---|---|---|---|---|---|
| 4BI_N1->32BI_N1/conf/5% | 1.35 | 0.050 | 4.2 | 0.073 [0.033, 0.113] | 1.65 [0.93, 4.14] |
| 4BI_N1->32BI_N1/conf/10% | 1.35 | 0.100 | 4.8 | 0.080 [0.040, 0.127] | 1.55 [0.92, 3.93] |
| 4BI_N1->32BI_N1/conf/25% | 1.35 | 0.249 | 4.8 | 0.087 [0.047, 0.140] | 1.65 [0.93, 4.14] |
| 4BI_N1->32BI_N1/conf/50% | 1.35 | 0.501 | 4.8 | 0.087 [0.047, 0.133] | 1.65 [0.93, 4.14] |
| 4BI_N1->32BI_N1/rise/5% | 1.35 | 0.050 | 2.8 | 0.053 [0.020, 0.093] | 1.58 [-6.40, 1.86] |
| 4BI_N1->32BI_N1/rise/10% | 1.35 | 0.102 | 3.5 | 0.067 [0.033, 0.113] | 1.75 [-3.75, 12.87] |
| 4BI_N1->32BI_N1/rise/25% | 1.35 | 0.250 | 3.5 | 0.120 [0.073, 0.173] | 1.68 [0.92, 4.14] |
| 4BI_N1->32BI_N1/rise/50% | 1.35 | 0.523 | 4.8 | 0.087 [0.047, 0.133] | 1.65 [0.93, 4.14] |
| 4BI_N1->32BI_N1/flow/5% | 1.05 | 0.050 | 4.8 | 0.073 [0.033, 0.113] | 1.92 [1.31, 2.57] |
| 4BI_N1->32BI_N1/flow/10% | 1.05 | 0.101 | 5.5 | 0.107 [0.060, 0.160] | 1.67 [1.15, 1.89] |
| 4BI_N1->32BI_N1/flow/25% | 1.05 | 0.250 | 9.0 | 0.100 [0.053, 0.147] | 1.31 [0.75, 1.92] |
| 4BI_N1->32BI_N1/flow/50% | 1.05 | 0.505 | 4.2 | 0.067 [0.033, 0.113] | 1.23 [0.63, 1.70] |
| 4BI_N1->32BI_N1/random/5% | 0.79 | 0.049 | 2.8 | 0.060 [0.027, 0.100] | 8.89 [1.61, 12.72] |
| 4BI_N1->32BI_N1/random/10% | 0.79 | 0.100 | 2.8 | 0.087 [0.040, 0.133] | 3.99 [0.33, 8.89] |
| 4BI_N1->32BI_N1/random/25% | 0.79 | 0.249 | 4.8 | 0.147 [0.093, 0.207] | 2.27 [1.16, 6.04] |
| 4BI_N1->32BI_N1/random/50% | 0.79 | 0.500 | 3.5 | 0.060 [0.027, 0.100] | 1.39 [0.37, 12.72] |
| 4BI_N1->32BI_N3/conf/5% | 2.64 | 0.050 | 8.3 | 0.087 [0.040, 0.133] | 2.71 [1.74, 2.94] |
| 4BI_N1->32BI_N3/conf/10% | 2.64 | 0.100 | 3.5 | 0.060 [0.027, 0.100] | 2.74 [2.21, 3.07] |
| 4BI_N1->32BI_N3/conf/25% | 2.64 | 0.249 | 3.5 | 0.060 [0.027, 0.100] | 2.74 [2.21, 2.90] |
| 4BI_N1->32BI_N3/conf/50% | 2.64 | 0.501 | 3.5 | 0.060 [0.027, 0.093] | 2.74 [2.21, 3.07] |
| 4BI_N1->32BI_N3/rise/5% | 2.64 | 0.050 | 3.5 | 0.033 [0.007, 0.067] | 2.84 [2.74, 3.07] |
| 4BI_N1->32BI_N3/rise/10% | 2.64 | 0.102 | 4.2 | 0.033 [0.007, 0.067] | 2.84 [2.74, 3.07] |
| 4BI_N1->32BI_N3/rise/25% | 2.64 | 0.250 | 4.2 | 0.060 [0.027, 0.100] | 2.74 [2.21, 2.93] |
| 4BI_N1->32BI_N3/rise/50% | 2.64 | 0.523 | 3.5 | 0.053 [0.020, 0.093] | 2.67 [2.21, 2.89] |
| 4BI_N1->32BI_N3/flow/5% | 2.35 | 0.050 | 6.2 | 0.120 [0.073, 0.173] | 2.95 [2.50, 3.85] |
| 4BI_N1->32BI_N3/flow/10% | 2.35 | 0.101 | 8.3 | 0.167 [0.107, 0.227] | 3.15 [2.55, 3.93] |
| 4BI_N1->32BI_N3/flow/25% | 2.35 | 0.250 | 2.8 | 0.113 [0.067, 0.167] | 2.64 [2.45, 3.81] |
| 4BI_N1->32BI_N3/flow/50% | 2.35 | 0.505 | 3.5 | 0.120 [0.067, 0.173] | 2.50 [2.11, 2.71] |
| 4BI_N1->32BI_N3/random/5% | 2.09 | 0.049 | 2.8 | 0.047 [0.013, 0.087] | 2.91 [1.19, 11.04] |
| 4BI_N1->32BI_N3/random/10% | 2.09 | 0.100 | 4.2 | 0.087 [0.047, 0.133] | 3.67 [2.15, 11.04] |
| 4BI_N1->32BI_N3/random/25% | 2.09 | 0.249 | 4.2 | 0.067 [0.027, 0.107] | 2.40 [1.91, 5.94] |
| 4BI_N1->32BI_N3/random/50% | 2.09 | 0.500 | 6.2 | 0.100 [0.053, 0.153] | 2.65 [2.15, 3.34] |
| 4BI_N1->32BI_N9/conf/5% | 6.51 | 0.050 | 5.5 | 0.080 [0.040, 0.127] | 6.59 [5.84, 6.88] |
| 4BI_N1->32BI_N9/conf/10% | 6.51 | 0.100 | 4.8 | 0.073 [0.033, 0.120] | 6.61 [5.61, 6.94] |
| 4BI_N1->32BI_N9/conf/25% | 6.51 | 0.249 | 2.8 | 0.060 [0.027, 0.100] | 6.61 [6.08, 6.98] |
| 4BI_N1->32BI_N9/conf/50% | 6.51 | 0.501 | 3.5 | 0.027 [0.007, 0.053] | 6.34 [-2.31, 6.76] |
| 4BI_N1->32BI_N9/rise/5% | 6.51 | 0.050 | 4.8 | 0.053 [0.020, 0.093] | 6.68 [4.46, 13.34] |
| 4BI_N1->32BI_N9/rise/10% | 6.51 | 0.102 | 2.8 | 0.047 [0.013, 0.080] | 6.94 [6.61, 20.08] |
| 4BI_N1->32BI_N9/rise/25% | 6.51 | 0.250 | 2.8 | 0.040 [0.013, 0.073] | 6.54 [1.88, 6.85] |
| 4BI_N1->32BI_N9/rise/50% | 6.51 | 0.523 | 2.8 | 0.040 [0.013, 0.073] | 6.54 [1.88, 6.85] |
| 4BI_N1->32BI_N9/flow/5% | 6.21 | 0.050 | 5.5 | 0.147 [0.093, 0.207] | 6.76 [6.49, 7.34] |
| 4BI_N1->32BI_N9/flow/10% | 6.21 | 0.101 | 9.0 | 0.187 [0.127, 0.247] | 6.71 [6.44, 7.29] |
| 4BI_N1->32BI_N9/flow/25% | 6.21 | 0.250 | 4.2 | 0.133 [0.080, 0.193] | 7.12 [6.73, 7.66] |
| 4BI_N1->32BI_N9/flow/50% | 6.21 | 0.505 | 5.5 | 0.133 [0.080, 0.187] | 6.58 [5.97, 6.94] |
| 4BI_N1->32BI_N9/random/5% | 5.95 | 0.049 | 4.8 | 0.093 [0.047, 0.147] | 11.58 [7.45, 15.08] |
| 4BI_N1->32BI_N9/random/10% | 5.95 | 0.100 | 4.8 | 0.080 [0.040, 0.127] | 7.49 [6.27, 11.58] |
| 4BI_N1->32BI_N9/random/25% | 5.95 | 0.249 | 4.2 | 0.060 [0.027, 0.100] | 7.42 [6.02, 11.91] |
| 4BI_N1->32BI_N9/random/50% | 5.95 | 0.500 | 3.5 | 0.067 [0.027, 0.107] | 6.98 [6.29, 12.79] |
| 4BI_N3->32BI_N1/conf/5% | 2.19 | 0.052 | 2.1 | 0.080 [0.040, 0.127] | 2.39 [1.21, 4.17] |
| 4BI_N3->32BI_N1/conf/10% | 2.19 | 0.100 | 3.5 | 0.080 [0.040, 0.127] | 2.39 [1.76, 4.17] |
| 4BI_N3->32BI_N1/conf/25% | 2.19 | 0.250 | 4.2 | 0.080 [0.040, 0.127] | 2.39 [1.76, 4.76] |
| 4BI_N3->32BI_N1/conf/50% | 2.19 | 0.502 | 4.8 | 0.080 [0.040, 0.127] | 2.39 [1.76, 4.76] |
| 4BI_N3->32BI_N1/rise/5% | 2.19 | 0.050 | 2.1 | 0.080 [0.040, 0.127] | 2.59 [-1.31, 6.18] |
| 4BI_N3->32BI_N1/rise/10% | 2.19 | 0.100 | 3.5 | 0.107 [0.060, 0.160] | 2.69 [2.29, 6.31] |
| 4BI_N3->32BI_N1/rise/25% | 2.19 | 0.250 | 4.2 | 0.100 [0.053, 0.147] | 2.62 [2.14, 4.98] |
| 4BI_N3->32BI_N1/rise/50% | 2.19 | 0.500 | 3.5 | 0.100 [0.053, 0.147] | 2.62 [2.14, 4.98] |
| 4BI_N3->32BI_N1/flow/5% | 1.05 | 0.050 | 4.8 | 0.073 [0.033, 0.113] | 1.92 [1.31, 2.57] |
| 4BI_N3->32BI_N1/flow/10% | 1.05 | 0.101 | 5.5 | 0.107 [0.060, 0.153] | 1.67 [1.15, 1.90] |
| 4BI_N3->32BI_N1/flow/25% | 1.05 | 0.250 | 9.0 | 0.100 [0.053, 0.153] | 1.31 [0.72, 2.01] |
| 4BI_N3->32BI_N1/flow/50% | 1.05 | 0.505 | 4.2 | 0.067 [0.027, 0.107] | 1.23 [0.63, 1.64] |
| 4BI_N3->32BI_N1/random/5% | 0.79 | 0.049 | 2.8 | 0.060 [0.027, 0.100] | 8.89 [1.61, 12.72] |
| 4BI_N3->32BI_N1/random/10% | 0.79 | 0.100 | 2.8 | 0.087 [0.047, 0.133] | 3.99 [0.33, 8.89] |
| 4BI_N3->32BI_N1/random/25% | 0.79 | 0.249 | 4.8 | 0.147 [0.093, 0.207] | 2.27 [1.16, 6.04] |
| 4BI_N3->32BI_N1/random/50% | 0.79 | 0.500 | 3.5 | 0.060 [0.027, 0.100] | 1.39 [0.37, 12.72] |
| 4BI_N3->32BI_N3/conf/5% | 3.48 | 0.052 | 2.8 | 0.060 [0.027, 0.100] | 3.58 [3.05, 3.73] |
| 4BI_N3->32BI_N3/conf/10% | 3.48 | 0.100 | 3.5 | 0.060 [0.027, 0.100] | 3.58 [3.05, 3.91] |
| 4BI_N3->32BI_N3/conf/25% | 3.48 | 0.250 | 3.5 | 0.060 [0.027, 0.100] | 3.58 [3.05, 3.91] |
| 4BI_N3->32BI_N3/conf/50% | 3.48 | 0.502 | 3.5 | 0.060 [0.027, 0.100] | 3.58 [3.18, 3.91] |
| 4BI_N3->32BI_N3/rise/5% | 3.48 | 0.050 | 4.8 | 0.040 [0.013, 0.073] | 3.44 [-3.13, 7.10] |
| 4BI_N3->32BI_N3/rise/10% | 3.48 | 0.100 | 2.8 | 0.047 [0.013, 0.080] | 3.68 [3.58, 3.77] |
| 4BI_N3->32BI_N3/rise/25% | 3.48 | 0.250 | 4.8 | 0.053 [0.020, 0.093] | 3.71 [3.58, 3.91] |
| 4BI_N3->32BI_N3/rise/50% | 3.48 | 0.500 | 3.5 | 0.060 [0.027, 0.100] | 3.58 [3.05, 3.91] |
| 4BI_N3->32BI_N3/flow/5% | 2.35 | 0.050 | 6.2 | 0.120 [0.067, 0.173] | 2.95 [2.50, 3.85] |
| 4BI_N3->32BI_N3/flow/10% | 2.35 | 0.101 | 8.3 | 0.167 [0.113, 0.227] | 3.15 [2.55, 3.93] |
| 4BI_N3->32BI_N3/flow/25% | 2.35 | 0.250 | 2.8 | 0.113 [0.067, 0.167] | 2.64 [2.45, 3.81] |
| 4BI_N3->32BI_N3/flow/50% | 2.35 | 0.505 | 3.5 | 0.120 [0.073, 0.173] | 2.50 [2.17, 2.71] |
| 4BI_N3->32BI_N3/random/5% | 2.09 | 0.049 | 2.8 | 0.047 [0.013, 0.080] | 2.91 [1.19, 11.04] |
| 4BI_N3->32BI_N3/random/10% | 2.09 | 0.100 | 4.2 | 0.087 [0.047, 0.133] | 3.67 [2.15, 11.04] |
| 4BI_N3->32BI_N3/random/25% | 2.09 | 0.249 | 4.2 | 0.067 [0.033, 0.107] | 2.40 [1.91, 5.94] |
| 4BI_N3->32BI_N3/random/50% | 2.09 | 0.500 | 6.2 | 0.100 [0.053, 0.153] | 2.65 [2.15, 3.34] |
| 4BI_N3->32BI_N9/conf/5% | 7.35 | 0.052 | 2.8 | 0.060 [0.027, 0.100] | 7.45 [6.91, 7.78] |
| 4BI_N3->32BI_N9/conf/10% | 7.35 | 0.100 | 3.5 | 0.027 [0.007, 0.053] | 7.18 [-1.47, 7.60] |
| 4BI_N3->32BI_N9/conf/25% | 7.35 | 0.250 | 3.5 | 0.027 [0.007, 0.053] | 7.18 [-1.47, 7.60] |
| 4BI_N3->32BI_N9/conf/50% | 7.35 | 0.502 | 3.5 | 0.027 [0.007, 0.053] | 7.18 [-1.47, 7.60] |
| 4BI_N3->32BI_N9/rise/5% | 7.35 | 0.050 | 5.5 | 0.107 [0.060, 0.160] | 7.75 [5.92, 14.33] |
| 4BI_N3->32BI_N9/rise/10% | 7.35 | 0.100 | 3.5 | 0.093 [0.047, 0.140] | 7.63 [6.45, 11.15] |
| 4BI_N3->32BI_N9/rise/25% | 7.35 | 0.250 | 2.8 | 0.053 [0.020, 0.093] | 7.69 [7.45, 7.93] |
| 4BI_N3->32BI_N9/rise/50% | 7.35 | 0.500 | 3.5 | 0.047 [0.013, 0.087] | 7.45 [6.91, 7.78] |
| 4BI_N3->32BI_N9/flow/5% | 6.21 | 0.050 | 5.5 | 0.147 [0.093, 0.207] | 6.76 [6.47, 7.32] |
| 4BI_N3->32BI_N9/flow/10% | 6.21 | 0.101 | 9.0 | 0.187 [0.127, 0.253] | 6.71 [6.44, 7.29] |
| 4BI_N3->32BI_N9/flow/25% | 6.21 | 0.250 | 4.2 | 0.133 [0.080, 0.187] | 7.12 [6.73, 7.66] |
| 4BI_N3->32BI_N9/flow/50% | 6.21 | 0.505 | 5.5 | 0.133 [0.087, 0.187] | 6.58 [5.78, 6.94] |
| 4BI_N3->32BI_N9/random/5% | 5.95 | 0.049 | 4.8 | 0.093 [0.047, 0.140] | 11.58 [7.71, 14.99] |
| 4BI_N3->32BI_N9/random/10% | 5.95 | 0.100 | 4.8 | 0.080 [0.040, 0.127] | 7.49 [6.27, 11.58] |
| 4BI_N3->32BI_N9/random/25% | 5.95 | 0.249 | 4.2 | 0.060 [0.027, 0.100] | 7.42 [6.02, 11.91] |
| 4BI_N3->32BI_N9/random/50% | 5.95 | 0.500 | 3.5 | 0.067 [0.033, 0.107] | 6.98 [6.38, 12.79] |

**Signal vs 4B-confidence at the same (4B N, 32B N, budget): paired detection difference [CI]; cells whose CI excludes 0.**

| policy | vs | detection diff [CI] | median delivered-time diff (both detected) |
|---|---|---|---|
| 4BI_N1->32BI_N1/random/25% | 4BI_N1->32BI_N1/conf/25% | +0.060 [+0.007, +0.120] | 0.45 (n 8) |
| 4BI_N1->32BI_N3/rise/5% | 4BI_N1->32BI_N3/conf/5% | -0.053 [-0.093, -0.013] | 0.00 (n 4) |
| 4BI_N1->32BI_N3/flow/10% | 4BI_N1->32BI_N3/conf/10% | +0.107 [+0.047, +0.173] | -0.29 (n 4) |
| 4BI_N1->32BI_N3/flow/25% | 4BI_N1->32BI_N3/conf/25% | +0.053 [+0.013, +0.093] | -0.29 (n 8) |
| 4BI_N1->32BI_N3/flow/50% | 4BI_N1->32BI_N3/conf/50% | +0.060 [+0.027, +0.100] | -0.29 (n 9) |
| 4BI_N1->32BI_N9/flow/10% | 4BI_N1->32BI_N9/conf/10% | +0.113 [+0.047, +0.180] | -0.29 (n 6) |
| 4BI_N1->32BI_N9/flow/25% | 4BI_N1->32BI_N9/conf/25% | +0.073 [+0.040, +0.120] | -0.29 (n 9) |
| 4BI_N1->32BI_N9/flow/50% | 4BI_N1->32BI_N9/conf/50% | +0.107 [+0.060, +0.160] | -0.29 (n 4) |
| 4BI_N1->32BI_N9/random/50% | 4BI_N1->32BI_N9/conf/50% | +0.040 [+0.013, +0.073] | 0.45 (n 4) |
| 4BI_N3->32BI_N1/random/25% | 4BI_N3->32BI_N1/conf/25% | +0.067 [+0.007, +0.127] | 0.61 (n 7) |
| 4BI_N3->32BI_N3/flow/10% | 4BI_N3->32BI_N3/conf/10% | +0.107 [+0.047, +0.173] | -1.13 (n 4) |
| 4BI_N3->32BI_N3/flow/25% | 4BI_N3->32BI_N3/conf/25% | +0.053 [+0.013, +0.093] | -1.13 (n 8) |
| 4BI_N3->32BI_N3/flow/50% | 4BI_N3->32BI_N3/conf/50% | +0.060 [+0.027, +0.100] | -1.13 (n 9) |
| 4BI_N3->32BI_N9/rise/10% | 4BI_N3->32BI_N9/conf/10% | +0.067 [+0.027, +0.113] | 0.00 (n 3) |
| 4BI_N3->32BI_N9/flow/5% | 4BI_N3->32BI_N9/conf/5% | +0.087 [+0.027, +0.153] | -1.13 (n 3) |
| 4BI_N3->32BI_N9/flow/10% | 4BI_N3->32BI_N9/conf/10% | +0.160 [+0.093, +0.227] | -1.13 (n 2) |
| 4BI_N3->32BI_N9/flow/25% | 4BI_N3->32BI_N9/conf/25% | +0.107 [+0.060, +0.160] | -1.13 (n 4) |
| 4BI_N3->32BI_N9/flow/50% | 4BI_N3->32BI_N9/conf/50% | +0.107 [+0.060, +0.160] | -1.13 (n 4) |
| 4BI_N3->32BI_N9/random/10% | 4BI_N3->32BI_N9/conf/10% | +0.053 [+0.013, +0.100] | -1.39 (n 2) |
| 4BI_N3->32BI_N9/random/50% | 4BI_N3->32BI_N9/conf/50% | +0.040 [+0.013, +0.073] | -0.39 (n 4) |

### Key observations
- **Detection at deployable false-alarm rates is low for both models.**
  - At 1–5 FA / h, 2.7–8.7 % of positive clips get any alarm; at 20 / h, 16.7–19.3 %.
  - At 5 / h: 4B N = 1 and N = 3 detect 6.0 % and 6.7 %; 32B N = 1 / 3 / 9 detect 8.7 / 6.0 / 2.7 %.
- **Recognition lead (Part A):** on clips both models detect (3–17 per cell), the median 32B − 4B first-alarm difference is **0 s in every cell**.
  - Means range from −1.47 s (32B N = 1, 20 / h) to +2.71 s (32B N = 9 vs 4B N = 3, 20 / h; CI [+0.06, +5.88], i.e. later).
  - Many clips are detected by one model only, in both directions (e.g. 20 / h, N = 1: 14 only-32B, 10 only-4B).
- **First alarms near the event:** where alarms occur, the median first alarm is within about ±0.5 s of time_of_event for most cells, and 0.8–2.6 s after time_of_alert.
  - Some first alarms are earlier than event − 3 s (1–7 clips per cell). These fall in the pre-event part of positive clips and are listed, not removed.
- **AUROC-threshold reference (D3 comparison only):** event-relative AUROC first reaches 0.70 at k = −1 s for all three 32B arms and at k = 0 for 4B. This is a 1 s ranking lead, in the direction D3 reported (0.97–1.05 s), and is not an alarm-time lead.
- **Delivery (Part B):**
  - **Matched N = 1:** recognition mean −1.47 s (n 15). The delivered mean stays −0.2 to −1.8 s across all formats and uplinks, but every CI spans 0.
  - **N = 3:** recognition +1.0 s (32B later, n 13). Delivered at 13.6 Mbit/s and 44 ms: raw +1.69 [+0.46, +3.92], PNG +0.56, JPEG +0.04 s. The mean reaches 0 only at ≈ 368 (raw) / 130 (PNG) / 22 (JPEG) Mbit/s.
  - **32B N = 9 vs 4B N = 3:** recognition +2.71 s, so 32B is never earlier at any uplink. Raw N = 9 upload alone is 5.3 s at 13.6 Mbit/s.
- **Escalation (Part C, 5 FA / h, 13.6 Mbit/s, 44 ms, raw):**
  - **Baselines:** device-only 4B detects 6.0–6.7 %, median delivered +0.9 / +1.6 s. Cloud-always 32B detects 8.7 / 6.0 / 2.7 %, median +1.1 / +2.2 / +5.8 s for N = 1 / 3 / 9.
  - **Escalation policies:** detection 2.7–18.7 %. The highest are flow-signal policies to 32B N = 9 (14.7–18.7 %) and N = 3 (11.3–16.7 %), with median delivered times +6.6 to +7.1 s and +2.5 to +3.2 s after the event.
  - **Signal vs 4B confidence (paired, same 4B N, 32B N and budget):** 20 of 72 comparisons have a detection CI excluding 0. Flow is better in 13 of them (+0.05 to +0.16). **Random escalation is also better than 4B confidence in 5 cells (+0.04 to +0.07)**, and rise is better in 1 and worse in 1.
  - **Delivered time:** 11 cells (9 flow, 2 random) have a median delivered-time difference vs confidence whose CI excludes 0, all earlier: −0.29 to −2.1 s.
    - These gains are mostly exactly the latency the signal does not wait for: 1.394 − 0.261 = 1.133 s for 4B N = 3, and 0.555 − 0.261 = 0.294 s for 4B N = 1.
    - **They are a property of the assumed signal cost, not of earlier recognition.**

## Results consistency check
1. **Cross-check against committed measurements:** the D14 AUROCs are reproduced exactly; latency inputs are taken verbatim from the D4 reports; the D3 ranking lead (~1 s) agrees in direction with the AUROC-threshold reference here (1 s). No > 2× disagreement.
2. **Physical plausibility:** cloud latency 0.21–15.0 s, and the upload term dominates for raw / PNG at N ≥ 3. Raw N = 9 is 9 × 995,328 B = 8.96 MB, which takes 5.27 s at 13.6 Mbit/s. Device latencies are as measured on the Orin. Nothing is faster than measured.
3. **Distribution sanity:** first-alarm times are reported as median and p25 / p75 plus a timing breakdown. Paired medians of exactly 0 come from whole-second decision times (alarms on the same second), not a constant artifact; mean differences vary across cells.
4. **Definition audit:**
   - The FA / h definition (per firing second) is pre-registered.
   - "Detection" = any alarm on a positive clip, including alarms before event − 3 s; the breakdown is reported.
   - Thresholds are fit only on training folds.
   - Scores = D14 log P(Yes), unchanged.
5. **Claim linkage:** FORMULATION.md §Decisions (which tier to provision for a standing query). The results **weaken** the case that cloud 32B gives an earlier correct alarm than device 4B at deployable FA rates on these traces: detection is low in both, there is no recognition lead at the median, and delivery latency removes any small mean lead at realistic uplinks. They do not speak to rates above 20 FA / h.
6. **Proxy validity:**
   - **Negative-clip seconds stand in for normal driving time.** That is valid for the per-hour FA rate only to the extent these clips are representative, and 1.44 h is a small sample: the 1 / h target allows 0 training false alarms.
   - **JPEG rows** assume unchanged scores (never measured).
   - **The flow signal's cost** is the Orin CPU measurement at 384 × 216, not at 768 × 432.

**Outcome:** the sanity checks passed. Flagged: a held-out FA shortfall in 4 of 30 Part A cells, all at 1 / h. Small n: 3–17 clips detected by both models per paired cell.

## Interpretation
- **No recognition lead at deployable rates:** on these validation traces, at 1–20 false alarms per hour, 32B does not raise its first correct alarm earlier than 4B at the median. Both detect only a small fraction of events at these rates.
  - The 1-second ranking lead seen in AUROC (and in D3) does not turn into an alarm-time lead once thresholds are set for deployable false-alarm rates.
- **Delivery:** network delivery makes the cloud alarm later still unless frames are compressed and the uplink is fast. With raw or PNG frames at N ≥ 3, typical 5G uplinks make 32B's delivered alarm later than the device's.
- **Escalation:** flow-gated escalation detects more events than confidence-gated escalation in several cells. But random escalation also beats confidence-gated escalation in some cells, so this does not identify a good escalation signal. It mainly shows that gating on 4B confidence correlates with 32B's own errors.
  - **No best-signal claim is made:** the delivered-time gains over confidence are the assumed signal latency (no 4B call to wait for), and the detection gains come with multiplicity (72 comparisons) and small n.

