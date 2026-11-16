# StudyFRAMES1: what an extra frame per call is worth, against delivery delay

Pre-registered in `research/EXPERIMENTS.md` (StudyFRAMES1) before anything was computed. CPU only on flash: no GPU, no model server, no inference. Every score is a committed StudyD14b trace and the metric is StudyE9c's challenge AP through StudyE9d's own code.

**One sentence.** At matched delivery delay the third frame buys nothing measurable on the 210 held-out EVAL clips (32B: +0.0017 at zero delay, +0.0006 at 1 s, and increasingly NEGATIVE beyond that), and once N = 3 is charged its own upload it is **-0.0291 mAP behind N = 1** with a CI of [-0.0989, +0.0285], so on this workload frames are the wrong way to spend either capacity or delay.

---

## 1. The arms and their real cost

| arm | measured latency, setting (ii) | hold shift | note |
|---|---|---|---|
| `32BI_N1` | 0.3950 s | 2 steps (0.50 s) | RTT 0.044 s + payload / 13.6 Mbit/s + TTFT |
| `32BI_N3` | 0.9304 s | 4 steps (1.00 s) | RTT 0.044 s + payload / 13.6 Mbit/s + TTFT |
| `4BI_N1` | 0.3355 s | 2 steps (0.50 s) | RTT 0.044 s + payload / 13.6 Mbit/s + TTFT |
| `4BI_N3` | NOT AVAILABLE | n/a | NOT AVAILABLE: StudyD7 / D7b measured the 4B at N = 1 only, so this arm has no committed serving latency and none is estimated here |

The 32B's third and second frame cost **0.5354 s** of extra delivery delay (0.9304 against 0.3950 s), which is the whole economic question: three frames must earn more than half a second of staleness. **There is no committed serving latency for the 4B at N = 3** (StudyD7 and D7b measured the 4B at N = 1 only), so nothing is estimated for it and that arm appears only where no latency is needed.

## 2. Primary: the gain from extra frames at MATCHED total delivery delay

Both columns are held at the same total hold shift, so the only difference is what the model saw. Cadence 0.5 s. Challenge mAP, with 2,000-resample paired clip-bootstrap CIs at seed 0; an asterisk marks an interval that excludes zero.

### 2.1 EVAL (210 clips)

| total delay (s) | 32B N=1 | 32B N=3 | 32B gain | 4B N=1 | 4B N=3 | 4B gain |
|---|---|---|---|---|---|---|
| 0.00 | 0.5780 | 0.5797 | +0.0017 | 0.5171 | 0.4819 | -0.0351 |
| 0.25 | 0.5502 | 0.5526 | +0.0024 | 0.4913 | 0.4711 | -0.0201 |
| 0.50 | 0.5420 | 0.5337 | -0.0083 | 0.4729 | 0.4524 | -0.0205 |
| 0.75 | 0.5158 | 0.5131 | -0.0026 | 0.4588 | 0.4334 | -0.0255 |
| 1.00 | 0.5123 | 0.5129 | +0.0006 | 0.4609 | 0.4293 | -0.0315 |
| 1.25 | 0.5145 | 0.5013 | -0.0132 | 0.4729 | 0.4369 | -0.0360 |
| 1.50 | 0.5133 | 0.4837 | -0.0296 | 0.4732 | 0.4200 | -0.0531 |
| 1.75 | 0.5202 | 0.4835 | -0.0367 | 0.4708 | 0.4290 | -0.0418 |
| 2.00 | 0.5340 | 0.4952 | -0.0388 | 0.4784 | 0.4326 | -0.0458 |
| 2.25 | 0.5446 | 0.5014 | -0.0432 | 0.4805 | 0.4295 | -0.0510 |
| 2.50 | 0.5464 | 0.5056 | -0.0407 | 0.4838 | 0.4248 | -0.0590* |
| 2.75 | 0.5368 | 0.4821 | -0.0548 | 0.4879 | 0.4208 | -0.0671* |
| 3.00 | 0.5211 | 0.4809 | -0.0402 | 0.4759 | 0.4130 | -0.0629* |

### 2.2 DEV (90 clips), the fitted side, shown for contrast only

| total delay (s) | 32B N=1 | 32B N=3 | 32B gain | 4B N=1 | 4B N=3 | 4B gain |
|---|---|---|---|---|---|---|
| 0.00 | 0.6032 | 0.6975 | +0.0943 | 0.5125 | 0.5663 | +0.0538 |
| 0.25 | 0.5623 | 0.6400 | +0.0778 | 0.4881 | 0.5306 | +0.0426 |
| 0.50 | 0.5481 | 0.6153 | +0.0672 | 0.5012 | 0.5211 | +0.0199 |
| 0.75 | 0.5447 | 0.5907 | +0.0460 | 0.5012 | 0.4958 | -0.0053 |
| 1.00 | 0.5344 | 0.5532 | +0.0188 | 0.5127 | 0.4875 | -0.0252 |
| 1.25 | 0.5171 | 0.5126 | -0.0045 | 0.4984 | 0.4742 | -0.0242 |
| 1.50 | 0.5161 | 0.4923 | -0.0238 | 0.4995 | 0.4755 | -0.0241 |
| 1.75 | 0.4960 | 0.4839 | -0.0121 | 0.4940 | 0.4732 | -0.0207 |
| 2.00 | 0.4995 | 0.4716 | -0.0279 | 0.4672 | 0.4508 | -0.0165 |
| 2.25 | 0.4932 | 0.4472 | -0.0460 | 0.4761 | 0.4555 | -0.0205 |
| 2.50 | 0.4745 | 0.4181 | -0.0564* | 0.4530 | 0.4319 | -0.0211 |
| 2.75 | 0.4808 | 0.4228 | -0.0579* | 0.4576 | 0.4353 | -0.0223 |
| 3.00 | 0.4750 | 0.4101 | -0.0649* | 0.4410 | 0.4167 | -0.0243 |

**The shape, on EVAL.** The gain is at best indistinguishable from zero at short delay and becomes clearly negative as delay grows: 32B +0.0017 at 0 s, -0.0296 at 1.5 s, -0.0402 at 3 s; 4B -0.0351 at 0 s and -0.0629 at 3 s, the last excluding zero. Extra frames do not merely fail to pay, they make a stale answer worse, which is what one expects if the third frame mostly adds redundant context while the delivered score ages.

**DEV says the opposite at short delay** (32B +0.0943 at 0 s, +0.0672 at 0.5 s) and that disagreement is itself a result: on 45 positive and 45 negative clips a 0.09 mAP swing is within sampling noise, so a profile table fitted on DEV would carry a frame bonus that the held-out clips do not show. StudyPROF1-dev's u_SH(cloud, d, m) entry is marked accordingly.

## 3. Secondary: each arm at its own measured latency

StudyE9d's own parameterization, that is each arm at its base hold shift plus an added delay. This is the deployable comparison: N = 3 pays for its own upload.

| side | tier | N=3 hold shift | N=1 hold shift | N=3 minus N=1 | CI | excludes zero |
|---|---|---|---|---|---|---|
| EVAL | 32BI | 1.00 s | 0.50 s | -0.0291 | [-0.0989, +0.0285] | no |
| EVAL | 4BI | NOT AVAILABLE | - | - | - | - |
| DEV | 32BI | 1.00 s | 0.50 s | +0.0051 | [-0.0885, +0.0916] | no |
| DEV | 4BI | NOT AVAILABLE | - | - | - | - |

On EVAL the 32B at N = 3 is -0.0291 mAP behind N = 1 when each is charged its own latency. The interval includes zero, so the honest statement is: **there is no evidence that the extra frames pay for their upload, and the point estimate says they cost.** This agrees with StudyE9b's committed conclusion that more frames is the wrong way to spend capability, reached there on the 1-s grid with streaming AP.

Both cadences are in `frames1_results.json`; the 1.0-s cadence shows the same ordering.

## 4. The pre-registered limitation, and what it does and does not license

**N = 3 in StudyD14b is three CONSECUTIVE frames at the trace's own stride**, captured together at one instant. Spec 7.9's merge rule is different: it merges two calls that are a CADENCE apart, so a merged call carries frames separated by T (0.5 s here), covering a window rather than an instant.

**Does the difference matter for the merge rule? Yes, and in the direction that makes this study a BOUND rather than a measurement.** Three consecutive frames are the most redundant arrangement of three frames: they are the case where the second and third frame add least. Cadence-spaced frames cover 1.0 s of motion and could plausibly add more. So:

* What this study licenses: **a frame budget spent on consecutive frames is not worth its delay** on this workload, at any delay in StudyE9d's grid, for either tier. The merge rule must not be enabled on the strength of a frame-count benefit that only DEV shows.
* What it does NOT license: a claim that merging two cadence-spaced calls is worthless. That arrangement is not in any committed trace.
* What would close it: **one measurement run** scoring 32B and 4B on PAIRS of frames spaced exactly one cadence apart (0.5 s and 1.0 s), at the same 0.25-s decision grid, on the same 300 clips, so that u_SH(cloud, d, m) can be read for a merged call rather than inferred. That is a GPU job and is out of scope for this CPU-only row; it belongs with StudyENG1's run.

Until then, spec 7.9's merge mechanism should stay behind its enabling condition (spec D38), and the policy should treat m > 1 as having NO measured benefit rather than a fitted one.

## 5. Results consistency check, 6 of 6

| # | check | outcome |
|---|---|---|
| 1 | cross-check against committed measurements | **PASS.** The same pipeline reproduces StudyE9c's all-300 always-cloud 32BI N=1 @0.5 s to -1.11e-16 and device-only to +5.55e-17 (recorded in `results/dashcam/ctrl1/ctrl1_consistency.json`). The arm latencies are StudyE9b's own function: 32B N=1 0.3950 s and N=3 0.9304 s, matching StudyE9d's committed cloud entries (hold shifts 2 and 4 steps) exactly. |
| 2 | physical plausibility | **PASS.** Nothing is timed here. The only rates are the committed uplink (13.6 Mbit/s), the committed frame bytes (354,902 and 1,057,532 B) and the committed TTFTs; the implied hold shifts are 2 and 4 grid steps. |
| 3 | distribution sanity | **PASS.** Every gain carries a 2,000-resample paired CI, and the curve is reported at all 13 delays rather than at a single point. No value repeats to suspicious precision across delays. |
| 4 | definition audit | **PASS.** `cloud_delivered`, `Challenge`, `ap_fast` and the 0.5 / 1.0 / 1.5 s horizons are imported from StudyE9d. One definitional difference from StudyE9d is explicit: StudyE9d adds delay ON TOP of each arm's base shift, which is this report's section 3, while section 2 holds the TOTAL shift equal across arms. Both are labelled wherever they appear. |
| 5 | claim linkage | **PASS.** This bears on spec 4.1's u_SH(cloud, d, m) and on spec 7.9's merge rule. It WEAKENS any claim that more frames per call buy utility, and it does not speak to representation choice for RC or to warm-state continuity. |
| 6 | proxy validity | **PASS with the pre-registered proxy declared.** Consecutive frames stand in for a merged cadence-spaced call; section 4 states the direction of the bias (they are the most redundant arrangement) and marks the merge-rule conclusion as a bound, not a measurement. |

## 6. Files

| file | what |
|---|---|
| `experiments/dashcam/frames1_utility.py` | the whole study |
| `results/dashcam/frames1/frames1_results.json` | both parameterizations, both tiers, both cadences, 13 delays, DEV and EVAL, with paired CIs on every gain |

