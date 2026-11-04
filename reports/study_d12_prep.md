# StudyD12-prep — can Qwen3-VL run time-series tasks?

**Date:** 2026-11-04 · **Host:** flash · **E-id:** StudyD12-prep (`research/EXPERIMENTS.md`)
**Status: PREP COMPLETE / PILOT NOT RUN — blocked, awaiting user decision.**

Time series is the only modality with no valid Qwen3-VL result in this repo. This document
records dataset access, the task formulations, the two input arms, and the prepared 50-item
pilot sets. **No inference was run and no main sweep was started.**

> **Prior-record note.** `research/GRAVEYARD.md` closed sensor-stream time series
> (OhioT1DM / PMData / T1DEXI / LifeSnaps) on 2026-07-28, but for a different reason —
> contexts of 0.5–2K tokens give no compression pressure. That does not speak to whether a
> VL model can read a series at all, which is what this study screens. StudyM (text-only
> Qwen3-8B on SenTSR-Bench) remains PENDING and is a different model and modality.

---

## 1. Blockers — pilot not run

**B1 · Target GPU busy.** The task says to stop if the target GPU is busy. At 2026-11-04
11:04 the A6000 (GPU 1) was at **100 % utilisation, 11,161 MiB used**, by another user's work:

| PID | user | uptime | process |
|---|---|---|---|
| 2533262, 3516128, 3573144, 4005425, 4005575 | `nesl` | 6–7 days | 5 × `CarlaUE4-Linux-Shipping` (rpc-ports 2000–2400) |
| 2664227 | `root` | 23 min | `ollama llama-server` (6,634 MiB) |

None are mine. The RTX 3090 Ti (GPU 0) is **free** (188 MiB, 0 %, Xorg/gnome-shell only).

**B2 · No vLLM on flash can load Qwen3-VL.** The only vLLM here is **0.8.5** (envs
`vllm_calib`, `vllm_calib2`). Its registry has no `Qwen3VLForConditionalGeneration` — the
newest Qwen VL architecture it knows is `Qwen2_5_VLForConditionalGeneration`:

```
Qwen2VLForConditionalGeneration, Qwen2_5_VLForConditionalGeneration, Qwen2_5OmniModel, ...
-> 'Qwen3VLForConditionalGeneration' in supported_archs == False
```

The working alternative on this host is **HF transformers 5.12.1 / torch 2.4.1+cu118** in
env `fmtk` (verified: `Qwen3VLForConditionalGeneration` imports). That is the same stack
StudyR8c used for Qwen3-VL-4B-Thinking on the 3090 Ti. The task says to report a stack
change before running, so the pilot was not started.

**B3 · STARK cannot have a PLOT arm without editing its questions.** See §3.1. Not a
blocker I resolved; it needs your call.

Prompt length is **not** a blocker: the longest prepared prompt is 4,071 tokens, far inside
the model's context, so nothing was truncated or downsampled.

---

## 2. Dataset access and licence

All three are open; **none needs an account or approval**. Raw data is kept out of git at
`/mnt/ssd/hf_models/ts_raw/` (`/` is 99 % full, so the SSD is used).

| dataset | official source | licence | access check | size |
|---|---|---|---|---|
| **STARK** | HF `prquan/STARK_10k` (STARK-L) and `prquan/STARK_1k` (STARK-S); code `github.com/nesl/STARK_Benchmark` | **BSD-3-Clause** (HF `cardData.license`) | `gated: False`, `private: False`, HTTP 200 anonymous | 14,554 files (14,552 items) |
| **WISDM** | UCI id **507**, *Smartphone and Smartwatch Activity and Biometrics*, DOI 10.24432/C5HK59 | **CC BY 4.0** | HTTP 200 anonymous | 296 MB zip |
| **MIT-BIH** | PhysioNet `mitdb` 1.0.0, DOI 10.13026/C2F305 | **Open Data Commons Attribution v1.0** | HTTP 302 → `physionet-open.s3.amazonaws.com`, 200 | 48 records, 90 MB |

**One choice you should know about.** "WISDM" names two official releases: the 2019 UCI
dataset above (51 subjects, 18 activities, phone + watch, accel + gyro, clearly CC BY 4.0)
and the older Fordham/Actitracker 2011 v1.1 smartphone-accel files, whose licence is not
stated on the Fordham page and which a third-party index lists as CC BY-NC-SA 3.0. I used
the **UCI 2019 release** because its licence is unambiguous. Say the word if you meant the
Fordham one.

### 2.1 STARK structure (verified from the files)

Each CSV is **one item** with `query` and `answer` columns, so the benchmark's own questions
and answers are used **verbatim** — none were written. 26 task families over three tiers:

| tier | content | families |
|---|---|---|
| 1 state estimation | `loc_*` (range, bearing, range+bearing, region, event-spatio, event-temp), `track_*_online`, `spatial/temporal/spatiotemporal_impute`, `spatiotemporal_forecast` | 16 |
| 2 reasoning over states | temporal relations (`contains`, `during`, `meets`, `precedes`, …) and spatial relations (`Point_Point_equals`, `Linestring_Polygon_crosses`, …) | 3 relation types, exposed as many geometry-pair dirs |
| 3 world-knowledge | `landmark_questions`, `direction_questions`, `route_planning`, `travel_questions`, `subroute_duration`, `poi_pred`, `intent_pred` | 7 |

Answers come in three shapes, which **matters for the metric**:

- **continuous** — `loc_range` `[x, y]`, `spatial_impute` `[26.434…]`, `spatiotemporal_forecast` `[0.6, 2.6, 10.7]`. The paper scores these by **RMSE / RMSPE (trimmed 10 %)**, not accuracy. There is **no accuracy, no majority baseline and no chance level** for them.
- **binary 0/1** — `landmark_questions`, `intent_pred`, `poi_pred`, the relation families. Accuracy defined, chance 50 %.
- **8-way categorical** — `direction_questions` (compass octants). Accuracy defined, chance 12.5 %.

`Polygon_Point_within` does not exist upstream (only `contains`, `intersects`, `touches`);
I used `Polygon_Point_contains`.

---

## 3. Task formulations

### 3.1 STARK — the benchmark's own questions (not ours)

Used verbatim from the `query` column, answers from `answer`. **No PLOT arm was built**, and
this is the open question: in STARK the sensor readings live *inside the query text*
("The sensor readings are: 7.9879, 6.4950, 4.9292, 5.7589."). Building a plot arm means
deleting that block from the benchmark's own question and pointing at an image — an edit to
the question, which the task forbids. The three options, none of which I took:

1. **TEXT arm only for STARK** (what is prepared now) — keeps the questions pristine, but gives no form comparison on this dataset.
2. Replace only the readings block with the image, leaving every other character intact — a minimal, mechanical edit, but still an edit.
3. Restrict the plot arm to the `track_*_online` families, where the readings are a genuine time series and a line plot is the natural rendering.

### 3.2 WISDM — **our own formulation**

18-way activity classification, one window per item.

- **Window** 10.0 s = **200 samples** at 20 Hz, non-overlapping, phone accelerometer.
- **Channels** x, y, z linear acceleration, m/s², **2 dp**.
- **Options** all 18 activities, numbered 1–18 (numbered, not lettered, because WISDM's own class codes are letters A–S and letter options would collide).
- **Chance 1/18 = 5.56 %.** Pilot set is near-balanced (14 classes × 3 items, 4 × 2), so the **always-majority baseline is 3/50 = 6.0 %**.
- Subject ID is recorded per item for subject-disjoint reporting.

### 3.3 MIT-BIH — **our own formulation**

5-way beat classification using the database's own annotations.

- **Window** 1.0 s = **360 samples** at 360 Hz, centred on the annotated R peak (peak at sample 180).
- **Channel** lead **MLII** only, mV, **3 dp**. Records 102 and 104 carry no MLII and are skipped.
- **Classes** the standard **AAMI EC57** superclasses, mapped from the beat symbols: N ← N,L,R,e,j · S ← A,a,J,S · V ← V,E · F ← F · Q ← /,f,Q. Non-beat markers (`+` rhythm, quality) are dropped.
- **Chance 1/5 = 20 %.** The pilot set is exactly balanced (10 per class), so the **always-majority baseline is also 20 %**.

*Limitation to note in any main sweep:* a 1 s centred window carries no preceding-RR context,
which is the main discriminator for class S. Expect S to be the weakest class.

### 3.4 The two input arms

Same data window, same question text, differing in one clause:

- **TEXT** — `"The window is given below as numeric samples, one line per channel."` + the series.
- **PLOT** — `"The window is given as the attached line plot image, one coloured trace per channel, with time in seconds on the x axis and amplitude on the y axis."` + a PNG.

Plots are fixed-format for every item: 8.0 × 3.0 in at 100 dpi, same colours
(x/MLII blue, y red, z green), same grid, same legend position, axis labels `time (s)` and
`amplitude (unit)`, **no title and no class hint**.

---

## 4. Prepared pilot sets (seed 0, n = 50 each)

| dataset | items | strata | balance |
|---|---|---|---|
| WISDM | 50 | 18 activities | 3 × 14, 2 × 4 |
| MIT-BIH | 50 | 5 AAMI classes | 10 each (exact) |
| STARK | 50 | 41 task families across all 3 tiers | 1–2 each |

### Prompt tokens (Qwen3-VL-4B-Instruct processor, image tokens included)

| dataset | arm | median | min | max |
|---|---|---|---|---|
| WISDM | TEXT | **3,851** | 3,851 | 4,071 |
| WISDM | PLOT | **490** | 490 | 490 |
| MIT-BIH | TEXT | **2,785** | 2,785 | 2,785 |
| MIT-BIH | PLOT | **507** | 507 | 507 |
| STARK | TEXT | **535** | 151 | 2,118 |

**The clearest prep result: the PLOT arm costs ~8× fewer prompt tokens than TEXT**
(WISDM 490 vs 3,851; MIT-BIH 507 vs 2,785) for the same underlying window. Plot token counts
are constant across items, confirming the fixed format. Whether that cheaper input is as
*accurate* is exactly what the pilot would answer — and has not been measured.

---

## 5. Cost of a main sweep (projection, not measured)

Assuming the full STARK-L (14,552 items, TEXT only) and 2,000 items each for WISDM and
MIT-BIH in both arms — **22,552 requests, 23.05 M prompt tokens**:

| dataset | arm | n | × median | prompt tokens |
|---|---|---|---|---|
| STARK | TEXT | 14,552 | 535 | 7.79 M |
| WISDM | TEXT | 2,000 | 3,851 | 7.70 M |
| WISDM | PLOT | 2,000 | 490 | 0.98 M |
| MIT-BIH | TEXT | 2,000 | 2,785 | 5.57 M |
| MIT-BIH | PLOT | 2,000 | 507 | 1.01 M |
| **total** | | **22,552** | | **23.05 M** |

**H100 time.** The one committed anchor for Qwen3-VL-32B on the H100 is StudyClean H5:
12,420 prompt tokens → **3.015 s cold TTFT**, prefix caching off, vLLM 0.31.0, GPU 1
(`results/cost/study_clean/study_clean_results_h100nvl.json`, cell `32BI_N37`). That is
**≈ 4,120 prompt tok/s**, so 23.05 M prompt tokens ≈ **1.6 h of prefill** at concurrency 1.
Decode dominates: at ~50 output tokens per item and single-stream 32B decode, 22,552 requests
land near **8–9 h**; with vLLM batching at concurrency 16–32 the whole sweep is plausibly
**1.5–3 h**. The decode rate is **not** measured for this shape on the H100, so treat the
total as an order-of-magnitude figure, not a committed estimate.

Token counts are from the 4B processor. The 32B prompt-token count should be identical (same
tokenizer family, text-identical prompts) but **this was not verified** — worth one check
before budgeting.

---

## 6. Results consistency check

Not applicable in the usual form: **this stage produced no accuracy numbers**. What was
verified instead:

1. **Definition audit** — every named object is pinned in §3 (window lengths in samples and seconds, precision in dp, channel names, class mappings, option numbering). WISDM's 20 Hz and MIT-BIH's 360 Hz read from the files, not assumed.
2. **Proxy validity** — none. Both arms are rendered from the same array; the PLOT arm is a rendering of exactly the samples the TEXT arm prints.
3. **Physical plausibility** — plots inspected: the WISDM `walking` window shows clean ~1.8 Hz gait periodicity, and the MIT-BIH R peak sits exactly at t = 0.500 s as the prompt claims.
4. **Cross-check** — prompt-token medians recomputed from the manifest; the H100 rate is taken from a committed StudyClean cell, not re-derived.

Not measured and therefore absent from this report: **accuracy, Wilson intervals, failure
rate, empty-answer rate**. Those need the pilot.

---

## 7. Example prompts and plots

Two per dataset. Plots: `results/ts/study_d12_prep/plots/<dataset>/<item_id>.png`.

### wisdm / wisdm_000  (label=A, tokens={'text': 3927, 'plot': 490})

TEXT arm:
```
You are given a 10.0-second window of accelerometer data recorded by a smartphone in the subject's front trouser pocket, sampled at 20 Hz (200 samples per channel). The three channels are the x, y and z linear acceleration axes in m/s^2, rounded to 2 decimal places.
The window is given below as numeric samples, one line per channel.

x: -0.21, 0.52, 1.69, 2.66, 4.32, -1.63, 1.20, -0.23, -0.01, 2.61, 1.71, 2.46, 3.95, 5.06, 3.70, 0.27, -0.45, 2.46, 3.24, 1.00, -0.10, 0.26, 1.99, 2.53, 2.25, -0.66, 2.11, -0.21, -0.73, 1.60, 1.84, 3.49, 3.78, 3.06, 5.55, 2.00, -1.54, 2.05, 1.96, 0.69, -0.09, -0.50, 1.08, 3.45, 1.56, 1.65, -0.71, 0.45, -1.00, 1.42, 2.28, 3.07, 4.65, 4.09, 4.63, 0.81, -1.42, 2.39, 4.20, 0.67, -0.63, -0.31, 1.60, 2.77, 1.93, -0.33, 1.04, 0.27, -0.63, 1.32, 1.98, 3.14, 4.14, 4.32, 3.91, 0.66, -0.36, 2.45, 2.07, 0.14, -0.18, 0.27, 3.32, 0.39, -0.64, 2.25, 2.53, -0.50, 1.21, 1.39
```

PLOT arm (same text, series block replaced; image `plots/wisdm/wisdm_000.png`):
```
You are given a 10.0-second window of accelerometer data recorded by a smartphone in the subject's front trouser pocket, sampled at 20 Hz (200 samples per channel). The three channels are the x, y and z linear acceleration axes in m/s^2, rounded to 2 decimal places.
The window is given as the attached line plot image, one coloured trace per channel, with time in seconds on the x axis and amplitude on the y axis.

Which single activity below is the subject performing during this window?

1. walking
2. jogging
3. stairs
4. sitting
5. standing
6. typing
7. brushing teeth
8. eating soup
9. eating chips
10. eating pasta
11. drinking from a cup
12. eating a sandwich
13. kicking a soccer ball
14. playing catch with a tennis ball
15. dribbling a basketball
16. writing
17. clapping
18. folding clothes

Answer with the number of the single best option, in exactly this format:
[ANSWER] <number> [/A
```

### wisdm / wisdm_001  (label=B, tokens={'text': 4017, 'plot': 490})

TEXT arm:
```
You are given a 10.0-second window of accelerometer data recorded by a smartphone in the subject's front trouser pocket, sampled at 20 Hz (200 samples per channel). The three channels are the x, y and z linear acceleration axes in m/s^2, rounded to 2 decimal places.
The window is given below as numeric samples, one line per channel.

x: 19.25, 18.78, 12.94, 6.68, 5.55, 4.44, -1.55, -6.54, -7.74, -6.51, -4.75, -1.68, -1.03, 1.17, 2.60, 2.49, -2.86, -7.44, -5.50, -8.24, -8.96, -3.07, 8.54, 19.25, 18.87, 18.34, 19.25, 16.49, 11.25, 12.62, 10.11, 6.65, 2.32, 1.59, 3.27, 9.16, 17.56, 19.25, 15.95, 7.29, 2.75, 3.32, -0.18, -4.30, -6.17, -7.22, -6.12, -5.22, -4.54, -1.70, 2.39, 0.97, -5.02, -7.85, -6.40, -6.31, -8.81, -6.00, 6.78, 16.71, 19.25, -5.88, 3.65, 19.07, 13.63, 11.15, 12.90, 11.57, 5.88, 3.15, 3.20, 4.79, 9.64, 17.34, 19.25, 19.25, 5.46, -0.85, -1.62, -2.38, -3.82, -4.48, -4.18, -3.07
```

PLOT arm (same text, series block replaced; image `plots/wisdm/wisdm_001.png`):
```
You are given a 10.0-second window of accelerometer data recorded by a smartphone in the subject's front trouser pocket, sampled at 20 Hz (200 samples per channel). The three channels are the x, y and z linear acceleration axes in m/s^2, rounded to 2 decimal places.
The window is given as the attached line plot image, one coloured trace per channel, with time in seconds on the x axis and amplitude on the y axis.

Which single activity below is the subject performing during this window?

1. walking
2. jogging
3. stairs
4. sitting
5. standing
6. typing
7. brushing teeth
8. eating soup
9. eating chips
10. eating pasta
11. drinking from a cup
12. eating a sandwich
13. kicking a soccer ball
14. playing catch with a tennis ball
15. dribbling a basketball
16. writing
17. clapping
18. folding clothes

Answer with the number of the single best option, in exactly this format:
[ANSWER] <number> [/A
```

### mitdb / mitdb_000  (label=N, tokens={'text': 2785, 'plot': 507})

TEXT arm:
```
You are given a 1.0-second window of a single-lead electrocardiogram (lead MLII) sampled at 360 Hz (360 samples), in millivolts rounded to 3 decimal places. The window is centred on one annotated heartbeat: its R peak is at the midpoint of the window (sample 180 of 360).
The window is given below as numeric samples, one line per channel.

MLII: -0.190, -0.210, -0.225, -0.235, -0.215, -0.190, -0.180, -0.220, -0.240, -0.220, -0.215, -0.210, -0.210, -0.230, -0.235, -0.245, -0.255, -0.250, -0.250, -0.270, -0.300, -0.320, -0.310, -0.320, -0.320, -0.320, -0.340, -0.365, -0.350, -0.360, -0.365, -0.390, -0.400, -0.385, -0.370, -0.360, -0.340, -0.335, -0.375, -0.390, -0.385, -0.370, -0.370, -0.365, -0.350, -0.360, -0.350, -0.335, -0.335, -0.345, -0.355, -0.370, -0.340, -0.330, -0.320, -0.345, -0.370, -0.360, -0.355, -0.345, -0.335, -0.355, -0.380, -0.360, -0.340, -0.330, -0.325, -0.355, -0.365, -
```

PLOT arm (same text, series block replaced; image `plots/mitdb/mitdb_000.png`):
```
You are given a 1.0-second window of a single-lead electrocardiogram (lead MLII) sampled at 360 Hz (360 samples), in millivolts rounded to 3 decimal places. The window is centred on one annotated heartbeat: its R peak is at the midpoint of the window (sample 180 of 360).
The window is given as the attached line plot image, one coloured trace per channel, with time in seconds on the x axis and amplitude on the y axis.

Classify the heartbeat at the centre of this window into one of the AAMI EC57 classes below.

1. N - Normal beat, or left/right bundle-branch block beat, or nodal/atrial escape beat
2. S - Supraventricular ectopic beat (atrial or nodal premature, aberrated atrial premature)
3. V - Ventricular ectopic beat (premature ventricular contraction or ventricular escape)
4. F - Fusion of a ventricular and a normal beat
5. Q - Unclassifiable or paced beat

Answer with the number of t
```

### mitdb / mitdb_001  (label=S, tokens={'text': 2785, 'plot': 507})

TEXT arm:
```
You are given a 1.0-second window of a single-lead electrocardiogram (lead MLII) sampled at 360 Hz (360 samples), in millivolts rounded to 3 decimal places. The window is centred on one annotated heartbeat: its R peak is at the midpoint of the window (sample 180 of 360).
The window is given below as numeric samples, one line per channel.

MLII: -0.245, -0.230, -0.215, -0.205, -0.205, -0.190, -0.190, -0.200, -0.210, -0.215, -0.220, -0.215, -0.200, -0.190, -0.200, -0.180, -0.150, -0.115, -0.030, 0.055, 0.170, 0.280, 0.420, 0.570, 0.725, 0.920, 1.095, 1.230, 1.285, 1.235, 1.090, 0.865, 0.600, 0.300, 0.050, -0.125, -0.225, -0.250, -0.230, -0.195, -0.165, -0.150, -0.150, -0.190, -0.230, -0.265, -0.295, -0.305, -0.310, -0.300, -0.300, -0.310, -0.310, -0.305, -0.315, -0.305, -0.300, -0.290, -0.305, -0.320, -0.330, -0.345, -0.335, -0.320, -0.325, -0.315, -0.310, -0.310, -0.315, -0.320, -0.330, -
```

PLOT arm (same text, series block replaced; image `plots/mitdb/mitdb_001.png`):
```
You are given a 1.0-second window of a single-lead electrocardiogram (lead MLII) sampled at 360 Hz (360 samples), in millivolts rounded to 3 decimal places. The window is centred on one annotated heartbeat: its R peak is at the midpoint of the window (sample 180 of 360).
The window is given as the attached line plot image, one coloured trace per channel, with time in seconds on the x axis and amplitude on the y axis.

Classify the heartbeat at the centre of this window into one of the AAMI EC57 classes below.

1. N - Normal beat, or left/right bundle-branch block beat, or nodal/atrial escape beat
2. S - Supraventricular ectopic beat (atrial or nodal premature, aberrated atrial premature)
3. V - Ventricular ectopic beat (premature ventricular contraction or ventricular escape)
4. F - Fusion of a ventricular and a normal beat
5. Q - Unclassifiable or paced beat

Answer with the number of t
```

### stark / stark_000  (label=Linestring_Point_intersects, tokens={'text': 638})

STARK query, used VERBATIM (answer: [0.0]):
```

Help me answer question regarding spatial relationship in a 2D plane:

Given Information:
    You will be provided with geometric information involving three types of 2D geometries—Point, LineString, and Polygon—all defined using the ESRI (Environmental Systems Research Institute) geometric format. These geometries are expressed as lists of coordinates in a Cartesian plane.

    Point: A single coordinate location in space, defined as a tuple: 
    
    [(x, y)].

    LineString: A sequence of points that forms a continuous line. It is represented as an ordered list of coordinate pairs: 
    
    [(x_1, y_1), (x_2, y2), ... (x_n, y_n)].

   Polygon: A closed shape formed by a sequence of coordinate pairs where the first and last points are the same to close the loop:
    
    [(x_1, y_1), (x_2, y2), ... (x_n, y_n), (x_1, y_1)].

    Spatial Relationships (based on ArcGIS model) is as follows. During computation, you should account for floating-point precision with a numerical tolerance 1e-8. For instance, 'Equals' should return True not just for exact mathematical identity, but if two geometries are identical within this tolerance.

    ArcGIS defines spatial relationships as logical conditions between geometric objects:

    1. Equals: Returns True if two geometries represent the same shape and location.
    2. Intersects: Returns True if the geometries share any portion of s
```

### stark / stark_001  (label=Linestring_Polygon_crosses, tokens={'text': 752})

STARK query, used VERBATIM (answer: [0.0]):
```

Help me answer question regarding spatial relationship in a 2D plane:

Given Information:
    You will be provided with geometric information involving three types of 2D geometries—Point, LineString, and Polygon—all defined using the ESRI (Environmental Systems Research Institute) geometric format. These geometries are expressed as lists of coordinates in a Cartesian plane.

    Point: A single coordinate location in space, defined as a tuple: 
    
    [(x, y)].

    LineString: A sequence of points that forms a continuous line. It is represented as an ordered list of coordinate pairs: 
    
    [(x_1, y_1), (x_2, y2), ... (x_n, y_n)].

   Polygon: A closed shape formed by a sequence of coordinate pairs where the first and last points are the same to close the loop:
    
    [(x_1, y_1), (x_2, y2), ... (x_n, y_n), (x_1, y_1)].

    Spatial Relationships (based on ArcGIS model) is as follows. During computation, you should account for floating-point precision with a numerical tolerance 1e-8. For instance, 'Equals' should return True not just for exact mathematical identity, but if two geometries are identical within this tolerance.

    ArcGIS defines spatial relationships as logical conditions between geometric objects:

    1. Equals: Returns True if two geometries represent the same shape and location.
    2. Intersects: Returns True if the geometries share any portion of s
```


---

## 8. What I need from you

1. **GPU** — the A6000 is someone else's for now. Run the 4B pilot on the free RTX 3090 Ti instead, wait for the A6000, or ask `nesl` to free it?
2. **Stack** — approve HF transformers 5.12.1 / torch 2.4.1+cu118 (the StudyR8c stack) for the pilot, since vLLM 0.8.5 cannot load Qwen3-VL on this host?
3. **STARK PLOT arm** — option 1, 2 or 3 from §3.1?

Nothing is run until these are settled.
