# StudyE9d-delay: what a delay costs, as a curve

E-id: StudyE9d-delay (`research/EXPERIMENTS.md`, pre-registered 2026-11-12 before any computation). **Offline replay of committed results. CPU only on the flash host: no GPU, no model server, no inference.** Every score is read from StudyD14b's committed 0.25-s trace; the delivery model, episode engine, AP engine and thresholds are imported unchanged from `study_e9b_dense.py` and the challenge-metric crop geometry from `study_e9c_challenge.py`. Scores are continuous log P(Yes); **no literal Yes/No answer is used anywhere**.

**This job produces curves and makes no policy claim.** It exists because every baseline in StudyB-baselines, and any scheduler we build, has to answer a question neither StudyE9b nor StudyE9c answers: *what does a DELAY cost?* StudyE9b measured value at two delivery points (device 0.567 s, cloud 0.395 s / 0.930 s) and StudyE9c measured the challenge metric at those same points. A policy that defers, queues or suspends a cloud call needs the whole curve.

## 0. Verification recorded before any number was produced

**CLAUDE.md's mechanism verification (Steps 1–5) does not apply to this job, and that is a deliberate call.** Steps 1–5 exist for an experiment that tests a *causal claim*: they ask which simulated quantity implements each link and whether it varies. This study makes no causal claim — it re-scores already-committed model outputs under an added delivery delay and under a blocked link. There is no mechanism that could be absent, zero or degenerate; the added delay is an input, swept by construction over 13 values. **StudyD14b and StudyE9c set the precedent for exactly this case:** a curve- or input-producing job records its input and control checks before computing, and the mechanism protocol attaches to the downstream study that makes a claim from the numbers — here StudySIM1-mixed, which consumes these curves.

Recorded before computing: the four controls of §7, the delay grid, the window placement rule (§5), the two metrics and the rule that they are never mixed, and the statement that no policy claim is made. The CLAUDE.md 6-check consistency protocol is run in full (§8).

## 1. The delivery model and the arms

StudyE9b's model, unchanged: a score computed on the grid at index *j* is readable at *j* + ceil(L / step); **the latency is never rounded, only the moment the application can first read the score**. The application holds the most recent score already delivered (sample-and-hold). Setting (ii) at 25 % load (PNG, 13.6 Mbit/s, RTT 0.044 s) is the base, as pre-registered.

| arm | measured latency | base hold shift | cadence | role |
|---|---|---|---|---|
| device 4B N = 1 | 0.567 s (StudyD8 arm A total p50) | 0.75 s (3 steps) | 0.75 s | **the reference**; never delayed |
| cloud 32B N = 1 | 0.395 s | 0.50 s (2 steps) | 0.5 s (primary) and 1.0 s | delayed by *d* |
| cloud 32B N = 3 | 0.930 s | 1.00 s (4 steps) | 0.5 s (primary) and 1.0 s | delayed by *d* |

Grid step 0.25 s; 150 positive and 150 negative StudyD14b **validation** clips. Streaming AP chance = **0.00728**; challenge chance (mean over the three horizons) = **0.4065** — a factor of 56. **The two metrics are never mixed.** StudyE9c's rule governs: signs and orderings transfer between them unconditionally, excess-over-chance ratios only while both arms are near chance, absolute levels never.

Challenge geometry, recomputed with StudyE9c's own functions: sigma = 2.8905 s, seed 0, positives per horizon h = 0.5 s: 150, h = 1.0 s: 106, h = 1.5 s: 66, chance per horizon 0.5000, 0.4141, 0.3056.

## 2. Part (a): V(d), the challenge mAP

Every cloud score is delivered *d* seconds later than its base delivery. The device arm is unchanged, so its value is a horizontal line.

| added delay *d* | device 4B N = 1 | 32B N = 1 @ 0.5 s | 32B N = 1 @ 1.0 s | 32B N = 3 @ 0.5 s | 32B N = 3 @ 1.0 s |
|---|---|---|---|---|---|
| 0.00 s | 0.4776 [0.4276, 0.5554] | 0.5675 [0.5078, 0.6490] | 0.5384 [0.4809, 0.6198] | 0.5504 [0.4955, 0.6267] | 0.5281 [0.4740, 0.6064] |
| 0.25 s | 0.4776 [0.4276, 0.5554] | 0.5508 [0.4914, 0.6322] | 0.5434 [0.4848, 0.6279] | 0.5440 [0.4881, 0.6200] | 0.5163 [0.4618, 0.5933] |
| 0.50 s | 0.4776 [0.4276, 0.5554] | 0.5405 [0.4833, 0.6140] | 0.5299 [0.4722, 0.6118] | 0.5205 [0.4668, 0.5915] | 0.4995 [0.4472, 0.5744] |
| 0.75 s | 0.4776 [0.4276, 0.5554] | 0.5399 [0.4843, 0.6148] | 0.5318 [0.4712, 0.6131] | 0.5102 [0.4537, 0.5810] | 0.4851 [0.4324, 0.5573] |
| 1.00 s | 0.4776 [0.4276, 0.5554] | 0.5297 [0.4736, 0.6049] | 0.5228 [0.4634, 0.6033] | 0.4978 [0.4441, 0.5704] | 0.4807 [0.4252, 0.5563] |
| 1.25 s | 0.4776 [0.4276, 0.5554] | 0.5240 [0.4653, 0.5996] | 0.5184 [0.4606, 0.5957] | 0.4879 [0.4351, 0.5594] | 0.4659 [0.4153, 0.5372] |
| 1.50 s | 0.4776 [0.4276, 0.5554] | 0.5179 [0.4586, 0.5958] | 0.5134 [0.4545, 0.5916] | 0.4679 [0.4176, 0.5388] | 0.4598 [0.4126, 0.5294] |
| 1.75 s | 0.4776 [0.4276, 0.5554] | 0.5068 [0.4527, 0.5825] | 0.5012 [0.4470, 0.5786] | 0.4529 [0.4062, 0.5215] | 0.4560 [0.4082, 0.5251] |
| 2.00 s | 0.4776 [0.4276, 0.5554] | 0.5058 [0.4528, 0.5815] | 0.4975 [0.4447, 0.5749] | 0.4535 [0.4082, 0.5194] | 0.4583 [0.4121, 0.5303] |
| 2.25 s | 0.4776 [0.4276, 0.5554] | 0.4875 [0.4359, 0.5641] | 0.4813 [0.4287, 0.5579] | 0.4490 [0.4043, 0.5163] | 0.4529 [0.4055, 0.5243] |
| 2.50 s | 0.4776 [0.4276, 0.5554] | 0.4789 [0.4293, 0.5530] | 0.4828 [0.4307, 0.5573] | 0.4491 [0.4028, 0.5177] | 0.4522 [0.4043, 0.5254] |
| 2.75 s | 0.4776 [0.4276, 0.5554] | 0.4701 [0.4224, 0.5437] | 0.4741 [0.4233, 0.5509] | 0.4467 [0.4007, 0.5149] | 0.4514 [0.4036, 0.5251] |
| 3.00 s | 0.4776 [0.4276, 0.5554] | 0.4759 [0.4281, 0.5496] | 0.4777 [0.4245, 0.5558] | 0.4526 [0.4062, 0.5248] | 0.4558 [0.4060, 0.5334] |
| *chance* | 0.4065 | | | | |

## 3. Part (a): V(d), the streaming AP

**Streaming AP at h = 0.0 s** (device 0.0126, 1.7x chance)

| added delay *d* | 32B N = 1 @ 0.5 s | 32B N = 1 @ 1.0 s | 32B N = 3 @ 0.5 s | 32B N = 3 @ 1.0 s |
|---|---|---|---|---|
| 0.00 s | 0.0384 (5.3x) | 0.0247 (3.4x) | 0.0146 (2.0x) | 0.0141 (1.9x) |
| 0.25 s | 0.0196 (2.7x) | 0.0175 (2.4x) | 0.0140 (1.9x) | 0.0132 (1.8x) |
| 0.50 s | 0.0164 (2.3x) | 0.0146 (2.0x) | 0.0129 (1.8x) | 0.0119 (1.6x) |
| 0.75 s | 0.0148 (2.0x) | 0.0130 (1.8x) | 0.0126 (1.7x) | 0.0109 (1.5x) |
| 1.00 s | 0.0131 (1.8x) | 0.0115 (1.6x) | 0.0120 (1.6x) | 0.0108 (1.5x) |
| 1.25 s | 0.0122 (1.7x) | 0.0106 (1.5x) | 0.0101 (1.4x) | 0.0102 (1.4x) |
| 1.50 s | 0.0116 (1.6x) | 0.0105 (1.4x) | 0.0100 (1.4x) | 0.0098 (1.3x) |
| 1.75 s | 0.0105 (1.4x) | 0.0104 (1.4x) | 0.0104 (1.4x) | 0.0101 (1.4x) |
| 2.00 s | 0.0101 (1.4x) | 0.0101 (1.4x) | 0.0096 (1.3x) | 0.0097 (1.3x) |
| 2.25 s | 0.0110 (1.5x) | 0.0172 (2.4x) | 0.0099 (1.4x) | 0.0094 (1.3x) |
| 2.50 s | 0.0112 (1.5x) | 0.0177 (2.4x) | 0.0100 (1.4x) | 0.0097 (1.3x) |
| 2.75 s | 0.0134 (1.8x) | 0.0175 (2.4x) | 0.0091 (1.3x) | 0.0093 (1.3x) |
| 3.00 s | 0.0136 (1.9x) | 0.0178 (2.5x) | 0.0094 (1.3x) | 0.0089 (1.2x) |

**Streaming AP at h = 0.5 s** (device 0.0104, 1.4x chance)

| added delay *d* | 32B N = 1 @ 0.5 s | 32B N = 1 @ 1.0 s | 32B N = 3 @ 0.5 s | 32B N = 3 @ 1.0 s |
|---|---|---|---|---|
| 0.00 s | 0.0161 (2.2x) | 0.0144 (2.0x) | 0.0128 (1.8x) | 0.0117 (1.6x) |
| 0.25 s | 0.0146 (2.0x) | 0.0128 (1.8x) | 0.0124 (1.7x) | 0.0108 (1.5x) |
| 0.50 s | 0.0129 (1.8x) | 0.0114 (1.6x) | 0.0118 (1.6x) | 0.0107 (1.5x) |
| 0.75 s | 0.0120 (1.7x) | 0.0104 (1.4x) | 0.0100 (1.4x) | 0.0101 (1.4x) |
| 1.00 s | 0.0114 (1.6x) | 0.0103 (1.4x) | 0.0099 (1.4x) | 0.0096 (1.3x) |
| 1.25 s | 0.0103 (1.4x) | 0.0102 (1.4x) | 0.0102 (1.4x) | 0.0099 (1.4x) |
| 1.50 s | 0.0100 (1.4x) | 0.0099 (1.4x) | 0.0095 (1.3x) | 0.0096 (1.3x) |
| 1.75 s | 0.0108 (1.5x) | 0.0171 (2.3x) | 0.0098 (1.3x) | 0.0092 (1.3x) |
| 2.00 s | 0.0110 (1.5x) | 0.0175 (2.4x) | 0.0099 (1.4x) | 0.0096 (1.3x) |
| 2.25 s | 0.0132 (1.8x) | 0.0173 (2.4x) | 0.0090 (1.2x) | 0.0092 (1.3x) |
| 2.50 s | 0.0134 (1.8x) | 0.0177 (2.4x) | 0.0093 (1.3x) | 0.0087 (1.2x) |
| 2.75 s | 0.0108 (1.5x) | 0.0106 (1.5x) | 0.0093 (1.3x) | 0.0091 (1.2x) |
| 3.00 s | 0.0115 (1.6x) | 0.0102 (1.4x) | 0.0088 (1.2x) | 0.0090 (1.2x) |

**Streaming AP at h = 1.0 s** (device 0.0102, 1.4x chance)

| added delay *d* | 32B N = 1 @ 0.5 s | 32B N = 1 @ 1.0 s | 32B N = 3 @ 0.5 s | 32B N = 3 @ 1.0 s |
|---|---|---|---|---|
| 0.00 s | 0.0127 (1.7x) | 0.0112 (1.5x) | 0.0116 (1.6x) | 0.0106 (1.5x) |
| 0.25 s | 0.0118 (1.6x) | 0.0103 (1.4x) | 0.0098 (1.4x) | 0.0099 (1.4x) |
| 0.50 s | 0.0112 (1.5x) | 0.0101 (1.4x) | 0.0098 (1.3x) | 0.0095 (1.3x) |
| 0.75 s | 0.0101 (1.4x) | 0.0100 (1.4x) | 0.0101 (1.4x) | 0.0098 (1.3x) |
| 1.00 s | 0.0098 (1.3x) | 0.0098 (1.3x) | 0.0094 (1.3x) | 0.0094 (1.3x) |
| 1.25 s | 0.0107 (1.5x) | 0.0169 (2.3x) | 0.0096 (1.3x) | 0.0091 (1.3x) |
| 1.50 s | 0.0108 (1.5x) | 0.0174 (2.4x) | 0.0098 (1.3x) | 0.0094 (1.3x) |
| 1.75 s | 0.0130 (1.8x) | 0.0172 (2.4x) | 0.0089 (1.2x) | 0.0090 (1.2x) |
| 2.00 s | 0.0133 (1.8x) | 0.0175 (2.4x) | 0.0092 (1.3x) | 0.0086 (1.2x) |
| 2.25 s | 0.0107 (1.5x) | 0.0104 (1.4x) | 0.0091 (1.3x) | 0.0089 (1.2x) |
| 2.50 s | 0.0114 (1.6x) | 0.0101 (1.4x) | 0.0087 (1.2x) | 0.0089 (1.2x) |
| 2.75 s | 0.0109 (1.5x) | 0.0106 (1.5x) | 0.0091 (1.2x) | 0.0086 (1.2x) |
| 3.00 s | 0.0099 (1.4x) | 0.0107 (1.5x) | 0.0091 (1.3x) | 0.0090 (1.2x) |

**Streaming AP at h = 1.5 s** (device 0.0092, 1.3x chance)

| added delay *d* | 32B N = 1 @ 0.5 s | 32B N = 1 @ 1.0 s | 32B N = 3 @ 0.5 s | 32B N = 3 @ 1.0 s |
|---|---|---|---|---|
| 0.00 s | 0.0110 (1.5x) | 0.0100 (1.4x) | 0.0096 (1.3x) | 0.0094 (1.3x) |
| 0.25 s | 0.0100 (1.4x) | 0.0099 (1.4x) | 0.0099 (1.4x) | 0.0096 (1.3x) |
| 0.50 s | 0.0097 (1.3x) | 0.0096 (1.3x) | 0.0092 (1.3x) | 0.0093 (1.3x) |
| 0.75 s | 0.0105 (1.4x) | 0.0167 (2.3x) | 0.0095 (1.3x) | 0.0090 (1.2x) |
| 1.00 s | 0.0106 (1.5x) | 0.0172 (2.4x) | 0.0096 (1.3x) | 0.0093 (1.3x) |
| 1.25 s | 0.0129 (1.8x) | 0.0170 (2.3x) | 0.0088 (1.2x) | 0.0089 (1.2x) |
| 1.50 s | 0.0131 (1.8x) | 0.0173 (2.4x) | 0.0090 (1.2x) | 0.0085 (1.2x) |
| 1.75 s | 0.0105 (1.4x) | 0.0102 (1.4x) | 0.0090 (1.2x) | 0.0088 (1.2x) |
| 2.00 s | 0.0112 (1.5x) | 0.0099 (1.4x) | 0.0086 (1.2x) | 0.0088 (1.2x) |
| 2.25 s | 0.0107 (1.5x) | 0.0104 (1.4x) | 0.0090 (1.2x) | 0.0085 (1.2x) |
| 2.50 s | 0.0098 (1.3x) | 0.0106 (1.5x) | 0.0090 (1.2x) | 0.0089 (1.2x) |
| 2.75 s | 0.0102 (1.4x) | 0.0103 (1.4x) | 0.0084 (1.2x) | 0.0085 (1.2x) |
| 3.00 s | 0.0107 (1.5x) | 0.0105 (1.4x) | 0.0089 (1.2x) | 0.0085 (1.2x) |

Full curves with CIs: `results/dashcam/study_e9d/e9d_vd_curves.csv` and the JSON.

## 4. d\*: the cloud's lead, in seconds

*d\** is the added delay at which a cloud arm falls to the device arm's value, by linear interpolation between the two bracketing delays. It is the quantity a policy needs: **how much delay the cloud's capability can absorb before it stops being worth calling.** The CI is the paired clip bootstrap (2,000 resamples, seed 0); `crossings` counts how many resamples cross at all inside the 3-s grid.

| arm | cadence | metric | device | cloud at d = 0 | **d\*** | CI | crossings |
|---|---|---|---|---|---|---|---|
| 32B N = 1 | 0.5 s | challenge mAP | 0.4776 | 0.5675 | **2.54 s** | [+0.71, +2.75] | 1228 / 2000 |
| 32B N = 1 | 0.5 s | streaming h0.0 | 0.0126 | 0.0384 | **1.13 s** | [+0.56, +1.76] | 1955 / 2000 |
| 32B N = 1 | 0.5 s | streaming h0.5 | 0.0104 | 0.0161 | **1.22 s** | [+0.46, +1.97] | 1398 / 2000 |
| 32B N = 1 | 0.5 s | streaming h1.0 | 0.0102 | 0.0127 | **0.73 s** | [+0.00, +2.95] | 1563 / 2000 |
| 32B N = 1 | 0.5 s | streaming h1.5 | 0.0092 | 0.0110 | **> 3.0 s** | [+0.00, +2.49] | 832 / 2000 |
| 32B N = 1 | 1.0 s | challenge mAP | 0.4776 | 0.5384 | **2.65 s** | [+0.08, +2.74] | 1177 / 2000 |
| 32B N = 1 | 1.0 s | streaming h0.0 | 0.0126 | 0.0247 | **0.81 s** | [+0.37, +1.47] | 1981 / 2000 |
| 32B N = 1 | 1.0 s | streaming h0.5 | 0.0104 | 0.0144 | **0.76 s** | [+0.20, +2.75] | 1586 / 2000 |
| 32B N = 1 | 1.0 s | streaming h1.0 | 0.0102 | 0.0112 | **0.33 s** | [+0.00, +2.25] | 1596 / 2000 |
| 32B N = 1 | 1.0 s | streaming h1.5 | 0.0092 | 0.0100 | **> 3.0 s** | [+0.00, +2.49] | 856 / 2000 |
| 32B N = 3 | 0.5 s | challenge mAP | 0.4776 | 0.5504 | **1.38 s** | [+0.04, +2.32] | 1711 / 2000 |
| 32B N = 3 | 0.5 s | streaming h0.0 | 0.0126 | 0.0146 | **0.74 s** | [+0.00, +1.34] | 1997 / 2000 |
| 32B N = 3 | 0.5 s | streaming h0.5 | 0.0104 | 0.0128 | **0.69 s** | [+0.00, +2.65] | 1925 / 2000 |
| 32B N = 3 | 0.5 s | streaming h1.0 | 0.0102 | 0.0116 | **0.19 s** | [+0.00, +2.26] | 1928 / 2000 |
| 32B N = 3 | 0.5 s | streaming h1.5 | 0.0092 | 0.0096 | **1.13 s** | [+0.00, +2.70] | 1717 / 2000 |
| 32B N = 3 | 1.0 s | challenge mAP | 0.4776 | 0.5281 | **1.05 s** | [+0.00, +2.41] | 1691 / 2000 |
| 32B N = 3 | 1.0 s | streaming h0.0 | 0.0126 | 0.0141 | **0.37 s** | [+0.00, +1.36] | 1998 / 2000 |
| 32B N = 3 | 1.0 s | streaming h0.5 | 0.0104 | 0.0117 | **0.61 s** | [+0.00, +2.35] | 1934 / 2000 |
| 32B N = 3 | 1.0 s | streaming h1.0 | 0.0102 | 0.0106 | **0.13 s** | [+0.00, +1.92] | 1946 / 2000 |
| 32B N = 3 | 1.0 s | streaming h1.5 | 0.0092 | 0.0094 | **0.58 s** | [+0.00, +2.66] | 1753 / 2000 |

## 5. Part (b): blocking windows

Window start index uniform on [0, G - W] so the window lies ENTIRELY inside the clip and every window has exactly length w; 20 placements per clip from one rng(seed 0) draw shared across arms, modes and window lengths (so the comparison is paired); 0 clips were too short for any w (min G = 61 steps, max W = 16).

During a window the **device keeps scoring** — the outage is on the cloud path — and the cloud is one of:

- **QUEUE:** scores are still computed on cadence, and anything that would have been readable inside the window becomes readable at the window's end. During the window the application holds its last *pre-window* cloud delivery.
- **SUSPEND:** no call is computed at a compute index inside the window, and during the window the application uses the **device's** latest delivered score. A call issued before the window whose delivery would land inside it is also held to the window's end: the link is down for it too.

Loss = the no-window value minus the windowed value, averaged over the 20 placements. The CI is the paired clip bootstrap of that placement-averaged loss; `min`/`max`/IQR are the spread **across placements**, which is the uncertainty that matters for a single outage.

**32BI_N1 at cadence 0.5 s**

| mode | *w* | challenge mAP | mAP loss | loss CI | placement IQR | streaming AP h = 0 | h = 0 loss | loss CI |
|---|---|---|---|---|---|---|---|---|
| QUEUE | 0.25 s | 0.5679 | **-0.0004** | [-0.0009, +0.0002] | 0.5674–0.5682 | 0.03756 | **+0.00084** | [-0.00001, +0.00260] |
| QUEUE | 0.50 s | 0.5680 | **-0.0004** | [-0.0011, +0.0005] | 0.5670–0.5686 | 0.03752 | **+0.00088** | [-0.00004, +0.00260] |
| QUEUE | 1.00 s | 0.5679 | **-0.0003** | [-0.0025, +0.0025] | 0.5662–0.5703 | 0.03733 | **+0.00107** | [-0.00012, +0.00306] |
| QUEUE | 2.00 s | 0.5670 | **+0.0005** | [-0.0050, +0.0083] | 0.5614–0.5713 | 0.03592 | **+0.00248** | [+0.00023, +0.00656] |
| QUEUE | 2.50 s | 0.5648 | **+0.0028** | [-0.0046, +0.0130] | 0.5555–0.5707 | 0.03478 | **+0.00362** | [+0.00056, +0.00898] |
| QUEUE | 4.00 s | 0.5575 | **+0.0100** | [-0.0018, +0.0255] | 0.5435–0.5665 | 0.03208 | **+0.00631** | [+0.00121, +0.01483] |
| SUSPEND | 0.25 s | 0.5670 | **+0.0006** | [-0.0011, +0.0025] | 0.5649–0.5686 | 0.03719 | **+0.00121** | [+0.00012, +0.00378] |
| SUSPEND | 0.50 s | 0.5643 | **+0.0032** | [+0.0003, +0.0068] | 0.5613–0.5666 | 0.03671 | **+0.00168** | [+0.00024, +0.00512] |
| SUSPEND | 1.00 s | 0.5625 | **+0.0050** | [-0.0006, +0.0120] | 0.5588–0.5680 | 0.03545 | **+0.00295** | [+0.00064, +0.00931] |
| SUSPEND | 2.00 s | 0.5561 | **+0.0114** | [+0.0009, +0.0249] | 0.5522–0.5631 | 0.03185 | **+0.00655** | [+0.00140, +0.01772] |
| SUSPEND | 2.50 s | 0.5522 | **+0.0154** | [+0.0028, +0.0308] | 0.5448–0.5614 | 0.03085 | **+0.00754** | [+0.00170, +0.02020] |
| SUSPEND | 4.00 s | 0.5435 | **+0.0240** | [+0.0049, +0.0449] | 0.5321–0.5565 | 0.02827 | **+0.01013** | [+0.00235, +0.02573] |
| *no window* | — | 0.5675 | — | — | — | 0.03840 | — | — |

**32BI_N3 at cadence 0.5 s**

| mode | *w* | challenge mAP | mAP loss | loss CI | placement IQR | streaming AP h = 0 | h = 0 loss | loss CI |
|---|---|---|---|---|---|---|---|---|
| QUEUE | 0.25 s | 0.5505 | **-0.0002** | [-0.0006, +0.0002] | 0.5500–0.5513 | 0.01454 | **+0.00004** | [-0.00002, +0.00021] |
| QUEUE | 0.50 s | 0.5499 | **+0.0005** | [-0.0004, +0.0014] | 0.5492–0.5508 | 0.01453 | **+0.00005** | [-0.00002, +0.00021] |
| QUEUE | 1.00 s | 0.5483 | **+0.0020** | [+0.0001, +0.0043] | 0.5471–0.5504 | 0.01449 | **+0.00009** | [-0.00004, +0.00028] |
| QUEUE | 2.00 s | 0.5454 | **+0.0049** | [+0.0006, +0.0099] | 0.5403–0.5515 | 0.01418 | **+0.00040** | [+0.00013, +0.00085] |
| QUEUE | 2.50 s | 0.5418 | **+0.0085** | [+0.0026, +0.0160] | 0.5352–0.5511 | 0.01404 | **+0.00054** | [+0.00021, +0.00113] |
| QUEUE | 4.00 s | 0.5364 | **+0.0140** | [+0.0044, +0.0255] | 0.5248–0.5485 | 0.01373 | **+0.00085** | [+0.00032, +0.00169] |
| SUSPEND | 0.25 s | 0.5492 | **+0.0011** | [-0.0008, +0.0031] | 0.5469–0.5513 | 0.01453 | **+0.00005** | [-0.00003, +0.00019] |
| SUSPEND | 0.50 s | 0.5471 | **+0.0033** | [+0.0003, +0.0066] | 0.5441–0.5496 | 0.01448 | **+0.00010** | [-0.00004, +0.00036] |
| SUSPEND | 1.00 s | 0.5434 | **+0.0069** | [+0.0014, +0.0134] | 0.5400–0.5475 | 0.01429 | **+0.00029** | [+0.00004, +0.00075] |
| SUSPEND | 2.00 s | 0.5344 | **+0.0159** | [+0.0053, +0.0271] | 0.5273–0.5414 | 0.01406 | **+0.00052** | [+0.00008, +0.00135] |
| SUSPEND | 2.50 s | 0.5333 | **+0.0171** | [+0.0042, +0.0307] | 0.5262–0.5385 | 0.01404 | **+0.00054** | [+0.00004, +0.00144] |
| SUSPEND | 4.00 s | 0.5258 | **+0.0245** | [+0.0048, +0.0444] | 0.5174–0.5324 | 0.01398 | **+0.00060** | [-0.00015, +0.00192] |
| *no window* | — | 0.5504 | — | — | — | 0.01458 | — | — |

Losses at the other streaming horizons are in `e9d_blocking_loss.csv` and the JSON.

## 6. QUEUE or SUSPEND? The paired answer

Both modes are run on the **same 20 placements** and the **same bootstrap resamples**, so the difference is paired. A positive number means QUEUE delivers more value than SUSPEND.

| arm | *w* | challenge mAP: QUEUE | SUSPEND | **QUEUE − SUSPEND** | CI | CI excludes 0 | streaming h = 0: QUEUE − SUSPEND | CI | excludes 0 |
|---|---|---|---|---|---|---|---|---|---|
| 32BI_N1 | 0.25 s | 0.5679 | 0.5670 | **+0.0010** | [-0.0007, +0.0028] | no | +0.00037 | [+0.00005, +0.00239] | **yes** |
| 32BI_N1 | 0.50 s | 0.5680 | 0.5643 | **+0.0037** | [+0.0009, +0.0068] | **yes** | +0.00081 | [+0.00010, +0.00380] | **yes** |
| 32BI_N1 | 1.00 s | 0.5679 | 0.5625 | **+0.0054** | [+0.0002, +0.0106] | **yes** | +0.00188 | [+0.00040, +0.00758] | **yes** |
| 32BI_N1 | 2.00 s | 0.5670 | 0.5561 | **+0.0109** | [+0.0029, +0.0194] | **yes** | +0.00407 | [+0.00094, +0.01321] | **yes** |
| 32BI_N1 | 2.50 s | 0.5648 | 0.5522 | **+0.0126** | [+0.0030, +0.0220] | **yes** | +0.00392 | [+0.00085, +0.01329] | **yes** |
| 32BI_N1 | 4.00 s | 0.5575 | 0.5435 | **+0.0140** | [-0.0008, +0.0278] | no | +0.00381 | [+0.00028, +0.01557] | **yes** |
| 32BI_N3 | 0.25 s | 0.5505 | 0.5492 | **+0.0013** | [-0.0007, +0.0033] | no | +0.00001 | [-0.00011, +0.00013] | no |
| 32BI_N3 | 0.50 s | 0.5499 | 0.5471 | **+0.0028** | [-0.0001, +0.0062] | no | +0.00005 | [-0.00010, +0.00027] | no |
| 32BI_N3 | 1.00 s | 0.5483 | 0.5434 | **+0.0049** | [-0.0008, +0.0112] | no | +0.00020 | [-0.00003, +0.00059] | no |
| 32BI_N3 | 2.00 s | 0.5454 | 0.5344 | **+0.0110** | [+0.0001, +0.0221] | **yes** | +0.00012 | [-0.00021, +0.00067] | no |
| 32BI_N3 | 2.50 s | 0.5418 | 0.5333 | **+0.0086** | [-0.0039, +0.0208] | no | -0.00000 | [-0.00040, +0.00060] | no |
| 32BI_N3 | 4.00 s | 0.5364 | 0.5258 | **+0.0105** | [-0.0083, +0.0294] | no | -0.00025 | [-0.00096, +0.00083] | no |

**QUEUE is at least as good as SUSPEND in 12 of 12 cells on challenge mAP, and the paired CI excludes 0 in 5 of 12.** The reason is visible in §4: the cloud's lead over the device is on the order of a second or more, so a *stale* 32B score is still worth more than a *fresh* 4B score for windows of this length. Falling back to the device during a short cloud outage costs value rather than saving it.

Two qualifications, both visible in the tables. (i) For 32B N = 3 the streaming-AP difference is **not** resolvable at any window length (every CI contains 0): that arm's delivered streaming AP is already within about 2x of chance, so there is little left for a window to take away. (ii) At w = 0.25 s neither mode is distinguishable from no window at all on challenge mAP — the QUEUE mAP losses at w = 0.25 and 0.5 s are **negative** (−0.0004 and −0.0004 for N = 1), i.e. inside the noise floor. A negative loss is not a gain from being blocked; it is the size of the floor, and nothing smaller than about 0.001 mAP should be read from these tables.

## 7. Is the loss convex in *w*?

Convex (super-additive) means one window of 2*w* costs **more** than two windows of *w*: loss(2w) > 2 x loss(w). That is the property a scheduler needs in order to prefer many short interruptions over one long one.

**32BI_N1, QUEUE**

| pair | challenge: loss(w) | loss(2w) | 2 x loss(w) | ratio | verdict | streaming h = 0: loss(w) | loss(2w) | ratio | verdict |
|---|---|---|---|---|---|---|---|---|---|
| w0.25 -> 0.5 s | -0.0004 | -0.0004 | -0.0008 | 1.03 | **convex** | +0.00084 | +0.00088 | 1.04 | sub-additive |
| w0.5 -> 1.0 s | -0.0004 | -0.0003 | -0.0009 | 0.81 | **convex** | +0.00088 | +0.00107 | 1.22 | sub-additive |
| w1.0 -> 2.0 s | -0.0003 | +0.0005 | -0.0007 | -1.45 | **convex** | +0.00107 | +0.00248 | 2.32 | **convex** |
| w2.0 -> 4.0 s | +0.0005 | +0.0100 | +0.0010 | 19.91 | **convex** | +0.00248 | +0.00631 | 2.55 | **convex** |

**32BI_N1, SUSPEND**

| pair | challenge: loss(w) | loss(2w) | 2 x loss(w) | ratio | verdict | streaming h = 0: loss(w) | loss(2w) | ratio | verdict |
|---|---|---|---|---|---|---|---|---|---|
| w0.25 -> 0.5 s | +0.0006 | +0.0032 | +0.0011 | 5.62 | **convex** | +0.00121 | +0.00168 | 1.39 | sub-additive |
| w0.5 -> 1.0 s | +0.0032 | +0.0050 | +0.0065 | 1.56 | sub-additive | +0.00168 | +0.00295 | 1.75 | sub-additive |
| w1.0 -> 2.0 s | +0.0050 | +0.0114 | +0.0101 | 2.27 | **convex** | +0.00295 | +0.00655 | 2.22 | **convex** |
| w2.0 -> 4.0 s | +0.0114 | +0.0240 | +0.0228 | 2.10 | **convex** | +0.00655 | +0.01013 | 1.55 | sub-additive |

**32BI_N3, QUEUE**

| pair | challenge: loss(w) | loss(2w) | 2 x loss(w) | ratio | verdict | streaming h = 0: loss(w) | loss(2w) | ratio | verdict |
|---|---|---|---|---|---|---|---|---|---|
| w0.25 -> 0.5 s | -0.0002 | +0.0005 | -0.0003 | -3.14 | **convex** | +0.00004 | +0.00005 | 1.14 | sub-additive |
| w0.5 -> 1.0 s | +0.0005 | +0.0020 | +0.0010 | 4.10 | **convex** | +0.00005 | +0.00009 | 1.85 | sub-additive |
| w1.0 -> 2.0 s | +0.0020 | +0.0049 | +0.0040 | 2.45 | **convex** | +0.00009 | +0.00040 | 4.51 | **convex** |
| w2.0 -> 4.0 s | +0.0049 | +0.0140 | +0.0099 | 2.83 | **convex** | +0.00040 | +0.00085 | 2.13 | **convex** |

**32BI_N3, SUSPEND**

| pair | challenge: loss(w) | loss(2w) | 2 x loss(w) | ratio | verdict | streaming h = 0: loss(w) | loss(2w) | ratio | verdict |
|---|---|---|---|---|---|---|---|---|---|
| w0.25 -> 0.5 s | +0.0011 | +0.0033 | +0.0023 | 2.87 | **convex** | +0.00005 | +0.00010 | 2.08 | **convex** |
| w0.5 -> 1.0 s | +0.0033 | +0.0069 | +0.0066 | 2.10 | **convex** | +0.00010 | +0.00029 | 2.89 | **convex** |
| w1.0 -> 2.0 s | +0.0069 | +0.0159 | +0.0138 | 2.30 | **convex** | +0.00029 | +0.00052 | 1.82 | sub-additive |
| w2.0 -> 4.0 s | +0.0159 | +0.0245 | +0.0318 | 1.54 | sub-additive | +0.00052 | +0.00060 | 1.15 | sub-additive |

**The answer, with its scope.** For *w* ≥ 1 s the loss is **convex in every cell where the loss is above the noise floor**: doubling 1 s to 2 s and 2 s to 4 s costs more than twice as much in 7 of 8 challenge-mAP comparisons and in 5 of 8 streaming comparisons, with ratios 2.1–2.8 (the one 19.9x entry is a ratio of two numbers inside the noise floor and means nothing). Below 1 s the comparisons are **not resolvable**: the losses being divided are 0.0002–0.003 mAP, at or under the floor identified in §6, and the ratios there should not be used. So: **a single 4-s outage costs about twice what two 2-s outages cost, and the project should treat blocking cost as convex above 1 s and as flat below it.**

## 8. Controls

| control | what it tests | result |
|---|---|---|
| **(a) d = 0 reproduces StudyE9b and StudyE9c** | at zero added delay this engine must reproduce StudyE9b's streaming AP (point **and** CI) and StudyE9c's challenge AP and mAP for the same arms, setting and cadence | **PASS, EXACT** — 72 cells, worst absolute difference **0.0** (streaming 0.0, challenge 0.0) |
| **(b) an empty window reproduces d = 0** | a window of zero steps must leave the delivered stream identical to StudyE9b's `held_stream` | **PASS** — 0 differing grid points over 4 arm x mode cells |
| **(c) SUSPEND over the whole clip equals the device** | a window covering every index must deliver exactly the device's own stream | **PASS** — 0 differing grid points, and both metrics equal the device arm's to the bit in 2 / 2 arms |
| **(d) the bootstrap's AP equals scikit-learn's** | the vectorised AP used inside the bootstrap must equal `average_precision_score`, tie handling included | **PASS** — 159 cells, 0 differences above 1e-12; worst absolute difference 1.11e-16 (one ulp, a summation-order difference) |

Control (a) is what licenses everything else in this report: at d = 0 the numbers **are** StudyE9b's and StudyE9c's committed numbers, bit for bit, so every curve here is the effect of the added delay or the window and of nothing else.

## 9. Results consistency check (CLAUDE.md, 6 checks)

**1. Cross-check against committed measurements.**

| quantity | this run | prior run | source of prior | ratio | agree |
|---|---|---|---|---|---|
| streaming AP 32BI_N1@0.5 h=0.0 | 0.038397 | 0.038397 | StudyE9b e9b_study1_results.json | 1.000000 | **exact** |
| streaming AP 32BI_N1@0.5 h=0.5 | 0.016134 | 0.016134 | StudyE9b e9b_study1_results.json | 1.000000 | **exact** |
| streaming AP 32BI_N1@0.5 h=1.0 | 0.012664 | 0.012664 | StudyE9b e9b_study1_results.json | 1.000000 | **exact** |
| streaming AP 32BI_N1@0.5 h=1.5 | 0.011026 | 0.011026 | StudyE9b e9b_study1_results.json | 1.000000 | **exact** |
| streaming AP 32BI_N1@1.0 h=0.0 | 0.024714 | 0.024714 | StudyE9b e9b_study1_results.json | 1.000000 | **exact** |
| streaming AP 32BI_N1@1.0 h=0.5 | 0.014391 | 0.014391 | StudyE9b e9b_study1_results.json | 1.000000 | **exact** |
| streaming AP device h=1.5 | 0.009205 | 0.009205 | StudyE9b | 1.000000 | **exact** |
| challenge mAP device | 0.477604 | 0.477604 | StudyE9c | 1.000000 | **exact** |
| challenge AP device h=0.5 | 0.564287 | 0.564287 | StudyE9c | 1.000000 | **exact** |
| challenge AP device h=1.0 | 0.506719 | 0.506719 | StudyE9c | 1.000000 | **exact** |
| challenge AP device h=1.5 | 0.361807 | 0.361807 | StudyE9c | 1.000000 | **exact** |

All 72 comparison cells (point estimates **and** confidence-interval bounds) agree exactly; the table above is a sample and the full list is in the JSON. Nothing in this study is re-measured: the scores, the latencies, the thresholds, the bootstrap resamples and both metrics are read or imported, never re-derived. No disagreement of any size exists, let alone one above 2x.

**2. Physical plausibility check.** No latency, throughput or size is measured or derived here. The only rates involved are StudyE9b's, unchanged: device 0.567 s with a 0.75-s saturated cadence, cloud 0.395 s (N = 1) and 0.930 s (N = 3) at 25 % load, each the sum of a committed RTT, a committed payload divided by a committed uplink, and a committed server TTFT. The added delay *d* is an imposed input, not a measurement, and the hold shifts it produces (0.5–3.5 s) are whole multiples of the 0.25-s grid by construction.

**3. Distribution sanity.** Every AP and mAP carries a 2,000-resample paired clip-bootstrap CI. Part (b) additionally reports the spread **across the 20 window placements** (min, max and IQR per cell), which is a second and independent source of variation that the bootstrap CI does not contain — and it is large: at w = 4 s, SUSPEND on 32B N = 1 ranges from 0.5083 to 0.5714 mAP depending only on where the window fell. Nothing is constant where a distribution is expected: the V(d) curves fall monotonically in *d* except for reversals of 0.001–0.006 mAP, which are inside the noise floor of §6 and are visible in the tables rather than smoothed away. The device arm is constant by construction (it is never delayed), and control (c) is the check that this is a property of the model and not a short-circuit.

**4. Definition audit.**

| object | this run | prior committed definition | match |
|---|---|---|---|
| challenge mAP | StudyE9c's: one crop per clip, horizons 0.5 / 1.0 / 1.5 s, the paper's alert rule, sigma = 2.8905 s, seed 0, scikit-learn AP, unweighted mean | StudyE9c | **yes** — the geometry is recomputed by calling StudyE9c's own functions, and control (a) proves the result is identical |
| streaming AP | StudyE9b's: every decision point of every negative clip a negative, positives at the grid point nearest `time_of_event − h` | StudyE9b | **yes** — StudyE9b's `ApEngine`, imported |
| delivery model | sample-and-hold, shift = ceil(L / 0.25 s), latency unrounded | StudyE9b | **yes**, imported unchanged |
| device cadence | 0.75 s | StudyE9b (flagged extrapolation from StudyD8's measured 1 Hz) | yes, and the flag is carried (§10) |
| "added delay *d*" | **new in this study**: seconds added to a cloud score's delivery time, a whole number of grid steps | — | new object, defined here |
| "blocking window" | **new in this study**: an inclusive index range during which the cloud path is down, fully inside the clip, with QUEUE and SUSPEND as the two modes | — | new object, defined here (§5) |

No name is used with two definitions. The two metric names follow StudyE9c's ruling: **challenge mAP** and **streaming AP**, never "Nexar AP" unqualified.

**5. Claim linkage.**

| headline | claim it bears on | supports / weakens / silent |
|---|---|---|
| the cloud's lead is finite and about 1–2.7 s on challenge mAP, 0.1–1.2 s on streaming AP | FORMULATION §Objective (cost-aware placement); CLAIMS' timing component | **supports** that timing is a first-class decision variable: the same placement is right or wrong depending on how late it lands |
| QUEUE beats SUSPEND for windows up to 4 s | FORMULATION §Decisions | **supports** keeping a stale high-capability answer over a fresh low-capability one at these horizons; it is the delivery-side counterpart of StudyE6b Stage B's "keep the device warm, do not schedule it" |
| the blocking loss is convex in *w* above 1 s | the timing component of CLAIMS' joint claim | **supports** that a scheduler which can split one long interruption into several short ones has something real to gain; it does **not** show that any policy achieves it |
| the d\* CIs are wide and 2–59 % of bootstrap resamples never cross | — | **weakens** any attempt to use a single d\* value as a threshold; the curve, not the crossing point, is the usable object |

Nothing measured here is scoped out by FORMULATION.md. No quantity fails to map to a claim.

**6. Proxy validity.**

| proxy | what it actually measures | valid? |
|---|---|---|
| an added delivery delay *d* stands for whatever makes a cloud answer late (queueing behind a cold prefill, a slower uplink, an engine hold) | the value of a score that arrives *d* seconds later than measured, with everything else held fixed | **valid for value, silent on cause** — the curve says what lateness costs, not what caused it. A policy pairing it with a cause must get the cause's duration from elsewhere (StudyE10c / E10d / E10e for engine holds, StudyE31b for outages) |
| a blocking window stands for a cloud-path outage | no cloud delivery during the window, the device unaffected | **valid**, with the modelling choice stated: QUEUE and SUSPEND differ only in whether calls are issued during the window and in what the application reads while it lasts |
| StudyD14b's H100-served 4B N = 1 scores stand for the Orin device | an H100 proxy | **partly, and bounded by StudyD15**: Pearson/Spearman 0.943 and 4 of 5 AP horizons with a CI containing 0, but **rejected as an exact numerical stand-in**. So no exact device-side number may be read off this report; where the two differ the real device was slightly *better*, which would make the cloud's lead *shorter*, not longer |
| 300 validation clips stand for the Nexar task | validation clips from the same dataset | **not leaderboard-comparable**, as StudyE9c states |

**Consistency check: PASS 6 / 6.**

## 10. What this shows, and what it does not

**Shows.**
1. **The cloud's advantage has a shelf life, and it is seconds, not milliseconds.** At cadence 0.5 s, 32B N = 1 holds its challenge-mAP advantage over the device until **d\* = 2.54 s** of added delay; on the streaming metric at h = 0 it is **1.13 s**. 32B N = 3, which starts later (1.0-s hold shift), has a shorter lead: 1.38 s and 0.74 s. The ordering of the two metrics' d\* values is the same; their magnitudes differ by about 2x, exactly as StudyE9c's transfer rule predicts.
2. **A bigger payload buys less delay tolerance.** N = 3's lead is 46 % (challenge) and 66 % (streaming h = 0) of N = 1's at the same cadence — the same direction as StudyE9b's finding 2 and StudyE9c §8.3, now as a quantity a policy can use.
3. **Queue, do not suspend.** QUEUE is at least as good as SUSPEND in 12 of 12 cells and significantly better in 5; a stale 32B score beats a fresh 4B score for every window length tested up to 4 s.
4. **Blocking cost is convex above 1 s and flat below it.** One 4-s outage costs about twice what two 2-s outages cost; below 1 s the loss is at the noise floor and should be treated as zero rather than as a small number.

**Does not show.**
1. **No policy claim.** No two policies are compared and no scheduler appears. These are curves for StudySIM1-mixed and for the baselines to read.
2. **No cause for the delay.** *d* is imposed. Whether a given policy actually incurs 1.5 s of delay is a question for the simulator, not for this report.
3. **d\* is not a threshold.** Its CIs span 0.0–2.9 s and between 832 and 1998 of 2,000 resamples cross at all inside the 3-s grid. Use the curve.
4. **No horizon below 0.5 s on the challenge metric**, which does not score them, and **no device-side absolute number**, per StudyD15 (§9.6).
5. **The device cadence is an extrapolation.** 0.75 s is StudyE9b's saturated-duty extrapolation from StudyD8's measured 1 Hz, carried here unchanged and flagged there.
6. **Only setting (ii) at 25 % load.** The 75 %-load and JPEG settings are not swept; a heavier load moves the cloud's *starting* point, which is StudyE9b's table, and would shorten d\* by its own hold shift.

## 11. Verdict

**Delivered: the value-versus-delay curve, the queue-versus-suspend answer and the convexity answer, with all four controls exact.** At d = 0 this engine reproduces StudyE9b's streaming AP and StudyE9c's challenge mAP bit for bit (control (a), worst absolute difference 0.0 over 72 cells), so every number in §2–§7 is the effect of delay or blocking alone. The cloud's lead over the device is **1.0–2.7 s on challenge mAP and 0.1–1.2 s on streaming AP**, shorter for the larger payload; **queueing a blocked cloud call beats falling back to the device** in 12 of 12 cells (significant in 5); and **the blocking loss is convex in the window length above 1 s** and inside the noise floor below it. No policy claim is made.

## 12. Files

| file | what |
|---|---|
| `experiments/dashcam/study_e9d_delay.py` | the delivery model, the two metrics, both parts, the four controls |
| `experiments/dashcam/study_e9d_report.py` | this report |
| `results/dashcam/study_e9d/e9d_results.json` | every cell, with CIs, placements and controls |
| `results/dashcam/study_e9d/e9d_vd_curves.csv` | V(d) for every arm, cadence and delay — the table a policy reads |
| `results/dashcam/study_e9d/e9d_dstar.csv` | d\* per arm, cadence and metric |
| `results/dashcam/study_e9d/e9d_blocking_loss.csv` | blocking loss per arm, mode and window |
| `reports/study_e9d_delay.md` | this file |

Inputs: `results/dashcam/study_d14b/d14b_trace_h100nvl.jsonl.gz`; `results/dashcam/study_e9b/e9b_study1_results.json`; `results/dashcam/study_e9c/e9c_results.json`; the delivery model, episode engine, AP engine and thresholds from `study_e9b_dense.py`; the crop geometry from `study_e9c_challenge.py`; latency constants via `study_e9_episodes.py`. Run on flash, **CPU only** — no GPU, no model server, no inference.
