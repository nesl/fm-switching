# A saturation knee in offered prefill work, and why it explains tonight

**Source** nine committed EP-G and CAL1F cells, `run_valid` true, read with the committed
`live2/cost_model_gate.py` `features()`. CPU only, no new run.
**Result** `results/orchestration/live2/frozen_test/saturation_knee.json`

This started as the H100's question about `querystream-proactive`, whose engine saturated
(dashcam TTFT p50 35.8 s) while `b7` on the same workload stayed sub-second. Its hypothesis was
that querystream's **requests** are heavier than b7's. **They are not, and the real answer is more
useful.**

## The hypothesis is refuted: identical bodies, fewer requests

| | requests | dashcam prompt tokens p50 | max | single-shot p50 | output tokens |
|---|---|---|---|---|---|
| b7-edf-feasibility | 12,126 | **3,760** | **7,140** | 1,372 | 2 |
| querystream-proactive | **10,439** | **3,760** | **7,140** | 1,372 | 2 |

**The monitor bodies are the same size, and querystream sends 14 percent FEWER requests.** Its
recall bodies are heavier (prompt tokens p50 11,752 against 7,930, max 25,023 against 11,822) but
there are only 19 of them. Total uncached prompt tokens over the run: **6,230,473 against
5,331,925, a 17 percent difference.**

So querystream does 17 percent more work and has **81x** the first-token latency. That is not a
weight story.

## The knee, over nine cells, four arms and two workloads

Offered work is total uncached prompt tokens divided by the 1,200 s run length.

| offered uncached tok/s | TTFT p50 | overlap p50 | cell |
|---|---|---|---|
| 4,412 | **0.446 s** | 10 | `warm-all-lru-reactive` EP-G |
| 4,443 | **0.449 s** | 10 | `b7-edf-feasibility` EP-G |
| 4,443 | **0.452 s** | 10 | `warm-all-lru-off` EP-G |
| 4,512 | **0.266 s** | 6 | `warm-all-lru-reactive` CAL1F |
| | | | |
| 5,192 | **35.911 s** | 672 | `querystream-proactive` EP-G |
| 5,476 | **31.890 s** | 969 | `warm-all-lru` CAL1F |
| 5,711 | **138.555 s** | 2,529 | `warm-all-lru` EP-G `kv0.25` |
| 5,732 | **134.629 s** | 2,171 | `warm-all-lru` EP-G seed 5 |
| 5,831 | **99.507 s** | 2,048 | `warm-all-lru` EP-G `_rf` |

**Four cells below 4,512 tok/s are all sub-second. Five cells above 5,192 tok/s are all 32 to 139
seconds. No cell lies in between, and the gap in offered work is 15 percent while the gap in
latency is 70x to 300x.** This is a phase transition, not a curve.

**The control that makes it a statement about load rather than about arms or workloads:** CAL1F
appears on **both** sides (`-reactive` at 4,512 below, `warm-all-lru` at 5,476 above) and EP-G
appears on **both** sides (`b7` and `-off` below, `warm-all-lru` and `querystream` above). **The
same workload lands on either side depending on the arm, and the same arm lands on either side
depending on the workload.** So neither identity explains it; offered work does.

**Sustained prefill capacity on this stack is therefore bounded at 4,512 to 5,192 uncached prompt
tokens per second** (H100 round-1 server, 32B multimodal, EP-G bodies). Consistency check 2: the
committed A6000 cold-prefill curve is about 7,100 tok/s for a text model, so a 32B multimodal model
with a vision encoder sitting below that is physically ordinary rather than suspicious.

## Why this explains the gate failure mechanically

`reports/study_cost_model_gate_d156.md` diagnosed the gate's failure as load confounded with arm
inside the fit set: the two CAL1F fit cells differ 160x in overlap. **The knee says what that
actually is. Those two cells sit on opposite sides of a phase transition** (4,512 and 5,476 tok/s),
and the gate fits **one linear overlap coefficient across it.**

A linear model cannot span a knee, and the way OLS fails is diagnostic: it splits the difference,
which forces the intercept negative to accommodate the sub-second side while the slope chases the
saturated side. **That is exactly the -2.37 s intercept and the 52 percent negative in-sample
predictions.** So the gate's failure is now explained rather than merely located, and it tells us
the remedy is not a better fit set: **a linear-in-overlap form cannot work on either side of this
knee, let alone across it.**

## Why it explains the three proactive arms, which is the night's unifying result

Three arms were measured tonight that submit work ahead of demand, and all three saturated:

| arm | how it adds work | offered tok/s | TTFT p50 |
|---|---|---|---|
| `v5-rules` warm-ahead | 83,961 prefills at seed 5 | above the knee | dashcam FAIL |
| `warm-all-lru` | prefills every batch on arrival | 5,476 to 5,831 | 32 to 139 s |
| `querystream-proactive` | proactive submission | 5,192 | 35.9 s |

**The workload sits just below the knee, so any arm that adds work tips the engine over it.** b7 at
4,443 tok/s is 1.5 percent under `-reactive`'s 4,512 and two orders of magnitude away in latency
from querystream's 5,192.

**This reframes every proactive result tonight.** The negative for warm-ahead is not that
prefetching is a bad idea, and not that the warm state is unreachable (it is reached 57 percent of
the time). It is that **on a workload already at 85 to 95 percent of the engine's sustained prefill
capacity, the work a proactive policy spends to create warmth is the work that pushes the engine
past its knee, and past the knee nothing arrives by any deadline.** The policy wins in the register
of cache residency and loses in the register of queueing delay, and the exchange rate between them
is set by how close the workload already sits to saturation.

**It also says what would change the answer, concretely and with a number**: a workload offering
under about 4,500 uncached tokens per second, which at these body sizes means roughly 12 devices
rather than 16, or EP-G bodies capped below 21 frames. **That is a testable prediction and not a
scoping excuse**, because it names the quantity and the threshold.

## Register and limits, stated

- **The knee is BOUNDED, not LOCATED**: between 4,512 and 5,192 tok/s, because no cell lies in the
  gap. Locating it needs a controlled load sweep, which is a GPU run and is not done here.
- **The x axis is a MEAN over the run**, so it conflates offered rate with burstiness. Two arms at
  the same mean rate could differ in pattern. What defends the reading is that four cells below and
  five above are cleanly separated across different arms and both workloads, not that the axis is
  the only possible one.
- **n = 9 cells, observational across arms**, not a designed sweep. Direction and separation are
  measured; the threshold's position is an interval.
- The dashcam "meet TRUE" in querystream's cell alongside a 35 s cloud TTFT is almost certainly
  device answers carrying the metric. Dashcam scoring on EP-G is PROVISIONAL anyway pending the
  Orin's re-record, and it is not read here.
- `n_requests` and `n_errors` are **null** in `cell.json` for querystream too, so the defect
  recorded for the warm-all cells is **not warm-all-specific**.

## What this does not touch

The four settled items stand unchanged: the race fix proved on a valid cell, `noc3` as a structural
mechanism-absent comparator, MARGIN_CF unset, and targeted warming reaching warm more often than
unconditional warming. The knee strengthens the last of these: `warm-all-lru` is above the knee and
`v5-rules` is a selective arm, so part of unconditional warming's lower warm share is its own queue
evicting and delaying what it warmed.

## r3-streaming adds the low anchor, and it sharpens the knee's shape

`r3-streaming_n16_s4_1200s_h27_3t_L3_epg`: **1,347 uncached tok/s, TTFT p50 0.146 s**, 0 non-200.
A fifth below-side point, at a third of the load of the other four. It does not locate the knee,
as the H100 said, but it does measure the shape of the side it is on:

| | load change | TTFT change |
|---|---|---|
| **below** the knee, 1,347 to 4,443 tok/s | **3.30x** | **3.08x** |
| **across** the knee, 4,443 to 5,192 tok/s | **1.17x** | **80.0x** |

**Below the knee, first-token latency is roughly proportional to offered work. Across it, a 17
percent load increase costs 80x.** So the curve is not merely steep somewhere; it is near-linear and
cheap up to a threshold and then explodes, which is the shape that makes the cost model's single
linear coefficient impossible rather than merely imprecise.

## r3-streaming's own row must NOT be read as a result about r3-streaming

The H100 asked whether declining everything is intended behaviour before its row is read. **It is
not the proxy device latency, which was its guess. The escalate-on-low branch is unreachable on
this data, for two independently measured reasons.**

Measured in this cell (`decision.jsonl`, 4,284 rows):

| kind | n |
|---|---|
| `release_monitor` | 3,905 of 11,764 eligible (**33.2 percent**) |
| `decline` | **376** |
| `defer` | 3 |
| **`release_recall`** | **ZERO, of 377 recall opportunities** |

Measured earlier on the same arm, in the device-confidence wiring proof
(`device_conf_wiring_proof.json`): **confidence present on 24 of 381 recalls, absent on 357;
decline-on-high 19; escalate-on-low 0.**

**So both paths lead to decline and neither is a fault:**

1. **Where device confidence exists, it is far too high to trigger an escalation.** StudySS2
   recorded the device's MCQ letter-mass median at **0.986**. A cascade that escalates on LOW
   confidence correctly declines at 0.986, which is the 19 decline-on-high events.
2. **Where it does not exist, which is 357 of 381, the arm defaults to decline.** STATUS already
   records why the field is absent: the re-recorded single-shot confidences are **not injected into
   the harness query objects**, because that is a separate methodological wiring change that was
   flagged for the user and deliberately not applied overnight.

**Under Rule 2 this is UNEXERCISED: the mechanism is reachable but no condition in the run reaches
it.** It is not a negative about r3-streaming and it is not evidence about confidence cascades.
**Under the port rule it is the explicit failure case: the arm's characteristic decision, routing a
query on low device confidence, occurred zero times, so its row is not a measurement of the arm.**
The decline rows carry `note: null`, so the log alone cannot distinguish branch 1 from branch 2;
that is a logging gap worth closing before any cascade arm is scored.

**One distinction this cell earns.** Its dashcam SLO fails with only a third of eligible monitors
released, so **its dashcam failure is a DECISION, not a queue.** Every other dashcam failure
measured tonight was a queue at or above the knee. r3-streaming sits at 1,347 tok/s with a 0.146 s
TTFT and fails anyway because it declines to look. Those two failure modes share a column in the
results table and have nothing else in common, and the table should not let them.

**Whether releasing 33.2 percent of eligible monitors is intended is a question for the arm's
card, not for the data**, and I am not guessing at it: it is consistent with a streaming policy that
samples on a cadence, and inconsistent with the full-coverage behaviour of `b7` and `mooncake` on
the same workload. Flagged for the user rather than resolved.

## CORRECTION: my explanation of the cascade declines was wrong, and the real one is sharper

I told the H100 that the cascade arms decline because "device confidence is high where present,
absent otherwise". **The first half is wrong as a family explanation and I withdraw it.** The
committed `device_conf_wiring_proof.json` settles it, and it says something more useful.

**All five cascade arms see the IDENTICAL confidence range on the present cases,
`[0.386991, 0.999972]`.** What differs is where each arm's threshold sits and what it does when the
field is missing:

| arm | present | decisions on PRESENT confidence | absent | **default on ABSENT** | discriminates? |
|---|---|---|---|---|---|
| `confidence-cascade` | 20 | DEVICE 13, CLOUD 7 | 357 | DEVICE | **YES, 13 / 7** |
| `cascade-routing` | 20 | **DEVICE 20** | 357 | **CLOUD** | no, all read HIGH |
| `streamscout` | 20 | **CLOUD 20** | 357 | DEVICE | no, all read LOW |
| `r3-streaming` | 24 | DEVICE 19, DEFER 5 | 357 | DEVICE | no, all read HIGH |
| `thinking-qwenvl-atdm` | 47 | CLOUD 17, DEFER 30 | 357 | **CLOUD** | no, all read LOW |
| `b7` (control) | 0 | none | 377 | CLOUD 372, REJECT 5 | n/a, no confidence rule |

**So confidence level is not the explanation. `cascade-routing` and `streamscout` read the SAME
twenty confidences and make exactly OPPOSITE decisions on all twenty.** Four of the five arms have
a threshold lying entirely outside the observed range, so each routes every robot question one way,
and which way depends only on which side its threshold falls. **Only `confidence-cascade`
discriminates at all.**

### The larger problem: a missing-data default decides 94 percent of every cascade arm's recalls

**357 of about 381 recall decisions in every cascade arm are made by its behaviour on a MISSING
field, not by its published mechanism.** Three arms default to DEVICE, two to CLOUD, and that
single adapter choice determines the arm's entire single-shot result:

- `cascade-routing` defaults to CLOUD, released 357 SS recalls, scored **SS 356 of 357**.
- `r3-streaming` defaults to DEVICE, released 0, scored **SS 0 of 357**.

**Those two numbers are the full span of the SS metric, and they differ by nothing but the default.**
Reporting them as two cascade policies' performance would be reporting a coin flip inside our
adapter. Neither is a measurement of confidence-based routing.

The field is missing because the re-recorded single-shot confidences are **not injected into the
harness query objects**, which STATUS records as a methodological wiring change flagged for the user
and deliberately not applied overnight. **That one unapplied change is now the largest single
determinant of five arms' headline numbers.**

### A pre-registered prediction, committed before the cells run

If the default is what drives the SS column, then for the two cascade arms not yet run tonight:

- **`thinking-qwenvl-atdm` (default CLOUD) should score SS at or near 356 of 357.**
- **`streamscout` (default DEVICE) should score SS at or near 0 of 357.**

Both follow from the absent-case default alone and from nothing about either paper's mechanism.
**This is recorded before the cells run so it can fail.** If either lands in between, the default is
not the whole story and this section is wrong.

### Revised classification, narrower than what I proposed

I proposed that "the whole cascade family is unexercised". **The H100's narrower framing is the
correct one and I adopt it: the cascade family's ROBOT-side characteristic decision is zero in both
cells measured tonight**, `cascade-routing` 0 of 20 and `r3-streaming` 0 of 377. But
`cascade-routing`'s escalation fires 357 times on single-shot, so the arm is not inert; it is
**driven by its default on the side where it acts and threshold-saturated on the side where it does
not.** Rule 2 **unexercised** applies to the robot side only, and the single-shot side is not a null
at all but an unmeasured mechanism with a default standing in for it.

---

## The within-run instrument: the knee narrows to 3.9 percent, and the pooled TTFT of every crossing cell has been read wrong

The H100 sent `querystream-proactive_n16_s5` as a point that does not fit: 5,550 uncached tok/s,
above the knee, but TTFT p50 7.87 s rather than the 31.9 s to 138.6 s the other above-knee cells
showed. It is not a counterexample. It is the knee being crossed in the middle of a run, and
measuring it dissolved the discrepancy, narrowed the knee bound by a factor of four, and refuted
my own first explanation of it.

### What the run-mean axis was hiding

`querystream-proactive_n16_s5`, dashcam first-token p50 by 100 s window of submit time, against
offered uncached tokens per second in the same window:

| t_submit (s) | offered unc tok/s | n | non-200 | ft p50 (s) | ft p90 (s) |
|---|---|---|---|---|---|
| 0 to 100 | 4,039.2 | 869 | 0 | 0.458 | 3.026 |
| 100 to 200 | 4,660.4 | 1,037 | 0 | 0.670 | 2.637 |
| 200 to 300 | 4,927.5 | 1,018 | 1 | 3.246 | 5.323 |
| 300 to 400 | 4,799.7 | 1,020 | 0 | 1.540 | 4.128 |
| 400 to 500 | 6,169.2 | 1,037 | 0 | 1.829 | 8.005 |
| 500 to 600 | 9,954.5 | 1,017 | 0 | 41.527 | 80.630 |
| 600 to 700 | 9,108.2 | 1,028 | 0 | 98.003 | 108.520 |
| 700 to 800 | 8,986.6 | 1,019 | 1 | 161.483 | 167.579 |
| 800 to 900 | 8,398.9 | 1,028 | 0 | 177.354 | 218.758 |
| 900 to 1000 | 4,862.1 | 621 | 10 | 228.227 | 245.443 |
| 1000 to 1100 | 697.1 | 59 | 0 | 198.688 | 219.128 |
| 1100 to 1200 | 0.0 | 7 | 7 | n/a | n/a |

Run mean 5,550.3 uncached tok/s, one x-coordinate for a run whose offered load ranges 0 to 9,954.

The pooled p50 of 7.88 s is the median of a monotone ramp from 0.46 s to 228 s. It reports
approximately the TTFT at the moment the median request was submitted. **It is a mixture of two
regimes, and it is not a level this arm ever sat at.** This cell's own last window is 198.7 s,
squarely inside the above-knee band. The discrepancy was in the summary statistic, not the cell.

Two further readings from the same table, both of which matter beyond this cell:

- **TTFT does not track instantaneous load.** Offered load falls back to 4,862 and then 697, which
  are below-knee rates, and TTFT does not recover: 228 s and 199 s. Above the knee, TTFT is set by
  accumulated backlog, not by the current rate. The knee is a threshold in the rate; the level above
  it is an integral.
- **The 19 non-200 are not the submission race.** All 19 are dashcam, all carry `http_status` null
  rather than an HTTP code, 17 of 19 are at t > 900 s, and 7 of them are the last 7 requests of the
  run. These are the null-status transport class (0.57 percent, already on tomorrow's list), and
  they are the tail of a collapsing run. They cannot be biasing the pooled p50 downward: 19 of
  9,760, all in the slow half, so excluding them raises the late p50 if anything.

### The same instrument on all 29 cells, which narrows the knee

Criterion declared in advance of reading the result: a cell **crosses** if the first-token p50 in
any 100 s window of submit time exceeds 2.0 s. The below-side cells sit at 0.27 s to 0.54 s pooled
and the above-side at 31.9 s and up, so 2.0 s is more than an order of magnitude from either. The
5.0 s and 10.0 s thresholds are reported alongside as a sensitivity check.

| group | n | run-mean unc tok/s | pooled ft p50 (s) | crosses at 2.0 s? |
|---|---|---|---|---|
| never crosses | **19** | 4,356.0 to **4,511.7** | 0.27 to 0.54 | **none, 0 of 19** |
| crosses | **10** | **4,685.8** to 5,830.8 | 0.81 to 373.39 | **all, 10 of 10** |

**Zero misclassifications in 29 cells.** The knee was bounded between 4,511.7 and 5,192.1 tok/s by
the gap between cells; the within-run criterion bounds it between **4,511.7 and 4,685.8**, a 3.9
percent interval rather than 15 percent. REGISTER: this is an **observed partition over 29 cells**,
not a fitted threshold, and the bound is the gap between the highest non-crossing cell and the
lowest crossing one.

The narrowing came from `v5-rules`, which no cell-level reading could have placed. Both seeds are
just above the bound and both show the **weakest** crossings in the set: s5 crosses at 400 s and
reaches only 5.93 s in its last window, and s4 crosses the 2.0 s threshold at 200 s but never the
5.0 s one and ends at 0.61 s, so s4 crosses **transiently and recovers**. The cells nearest the
boundary showing the mildest and least sustained crossings is the consistency check on the boundary
itself.

The control from the earlier section still holds across the new bound: the highest non-crossing cell
is **CAL1F** (`warm-all-lru-reactive`, 4,511.7) and the lowest crossing cell is **EP-G** (`v5-rules`
s5, 4,685.8), so the bracket is spanned by two different workloads and is not a workload artefact.

### My explanation of the spread above the knee was wrong, by my own instrument

On seeing querystream s5 cross later in its run than warm-all-lru s5, which crosses in its first
window, I formed the
hypothesis that **crossing time** explains the pooled spread, since the two cells are 1.0 percent
apart in load and 47x apart in pooled p50. Spearman correlations over the 10 crossing cells:

| y | vs run-mean load | vs crossing time |
|---|---|---|
| pooled ft p50 | **+0.77** | -0.43 |
| last-window ft p50 | **+0.84** | **-0.13** |

**Crossing time explains essentially nothing about severity (rho -0.13 on the terminal window), and
load explains it monotonically (+0.84).** My hypothesis is refuted. What crossing time explains is
only how much of a run is spent on each side, which is why it correlates with the *pooled* statistic
and not with the severity.

The controlled pair is the clearest way to see it. Those two cells are 1.0 percent apart in load:

| cell | load | crosses at | pooled ft p50 | last-window ft p50 |
|---|---|---|---|---|
| `querystream-proactive` s5 | 5,550.3 | 200 s | **7.88 s** | **198.69 s** |
| `warm-all-lru` s5 epg | 5,603.6 | 100 s | **373.39 s** | **377.10 s** |

On the pooled statistic they differ 47x. On the terminal window they differ 1.9x. **The 47x was the
summary statistic, not the system.**

### Consequence for the frozen-test table

For the 19 non-crossing cells the pooled first-token p50 is a fair summary: those runs are in one
regime throughout, and their first and last windows agree to within 0.2 s.

For the **10 crossing cells the pooled p50 is not a property of the arm.** It is a function of where
in its own ramp the median request happened to land, and it moves 47x between two cells that are 1
percent apart in load. Any row of `study_frozen_test.md` whose cell appears in the crossing group
should be read as a mixture, and the severity comparison between two crossing arms should use the
terminal window or an explicitly post-crossing statistic. This does not change any arm's **deadline
or on-time** score, which is computed per request and never pooled across the regimes, so no scored
result moves. It changes only how the TTFT column may be compared.

One exception worth recording against the "backlog does not drain" reading: 9 of the 10 crossing
cells end above their crossing threshold, but `warm-all-lru` CAL1F pools 31.89 s and ends at 4.51 s,
so that run does partly drain. The non-recovery is the common case tonight, not a law.

### Status

PROVISIONAL, consistent with the overnight brief: the 2.0 s crossing criterion and the terminal
window as the severity statistic are both unforeseen decisions taken to read a result, not
methodological changes to any scored quantity. Neither is used to compute a score. The knee bound
and the partition are MEASURED over 29 cells; the mechanism behind the threshold is not established
here, and the cache-tail observation below is the open lead.

The cache side, recorded as a lead and not a finding: in querystream s5 the median request's
uncached token count is flat at 372 to 378 across the crossing, while the mean cached fraction falls
0.80 to 0.68. The offered-rate rise is therefore carried by a **tail** of badly-missing requests
rather than by a shift in the typical request, and the queue spreads that tail's cost over the whole
population. Whether the cache tail causes the crossing or follows from it is not established by
these data: both move together within one 25 s window at t = 475. The measurement that would
separate them is the residency and eviction log, which is on disk (`residency.jsonl`) and unread.

---

## The cache lead, pursued: three mechanism hypotheses tested, all three fail, and one of my own tests retracted

`residency.jsonl` is not the file I said it was. On
`querystream-proactive_n16_s5_1200s_h27_3t_L3_epg` it holds 370 rows, one per single-shot or robot
session, **no dashcam rows at all**, `believed_tier` = `cold` in **370 of 370**, and
`telemetry_cached_tokens` **null in every row**. It is the coordinator's belief at admission, not an
engine eviction log, so it cannot separate the two causal directions and I was wrong to point the
H100 at it. Noted separately under check 3: a belief column that is constant across 370 rows with
its telemetry field never populated is an unfed channel, which is consistent with the earlier
finding that `release_at_GPU-WARM` beliefs run conservative. REGISTER: one cell.

The request log can be pushed further than the belief log, and it kills more than it settles.

### What is real: the cold share, not an eviction

Dashcam engine-observed `cache_path` = COLD, by 100 s window of submit time:

| t_submit (s) | n | COLD | P(COLD) |
|---|---|---|---|
| 0 to 400 | 3,816 | 234 | **0.059 to 0.063, flat** |
| 400 to 500 | 1,003 | 74 | 0.074 |
| 500 to 600 | 986 | 147 | **0.149** |
| 600 to 700 | 995 | 175 | **0.176** |
| 700 to 900 | 1,983 | 229 | 0.126 then 0.105 |
| 900 to 1100 | 651 | 103 | 0.150 then 0.241 |

Flat for the first four windows, then nearly triples at the crossing. Decomposing the mean
cached-fraction fall across the crossing at t = 475 into composition and within-stratum parts:

| | mean cached_fraction |
|---|---|
| actual, pre-crossing | 0.8026 |
| actual, post-crossing | 0.6922 |
| post-crossing **reweighted to the pre-crossing mix** | **0.7549** |

So **57 percent of the fall is composition** (dashcam COLD share 5.9 to 13.6 percent, while the
warm dashcam count is flat at 4,288 then 4,184, meaning about 400 *extra* fully-cold requests) and
**43 percent is within-stratum** (warm dashcam cached fraction 0.8832 to 0.8308). Both are real and
neither dominates. A fully-cold dashcam request carries about 3,760 uncached tokens against about
400 for a warm one, so roughly 400 extra cold requests over the 725 s post-crossing window is on
the order of 1,900 extra uncached tok/s, a large share of the rise from about 4,600 to about 8,600.

### What fails: every mechanism I proposed for it

**Hypothesis 1, LRU pressure on resident prefixes. REFUTED, and wrongly signed.** Per-request
Spearman against `cached_fraction`:

| | pre-crossing (n=4,569) | post-crossing (n=4,872) |
|---|---|---|
| backlog at submit | +0.043 | +0.157 |
| gap since the same session's previous submit | +0.068 | +0.053 |
| intervening distinct sessions | +0.030 | +0.161 |

LRU pressure predicts **negative** correlations: more backlog and more interleaving should mean
fewer hits. Every coefficient is near zero and the two non-trivial ones are **positive**. The
per-request cache hit is essentially independent of backlog, and what sign there is runs the wrong
way.

**Hypothesis 2, queue to cold: a request goes COLD because its own predecessor had not finished and
so was not yet inserted. RETRACTED, the test is void.** `session_id` is **null on all 9,434 dashcam
request rows**, so grouping by session pooled 6 devices into a single pseudo-session keyed on
`None`, put 9,361 of 9,433 requests in one conditioning cell, and left the contrast arm at n = 72.
This is not an underpowered null, it is a broken grouping, and it is the register error in a new
place: I keyed an analysis on a field without checking it was populated. The result it produced
(risk ratio 0.7x) should not be cited.

**Hypothesis 3, composition.** The COLD share rising is 57 percent of the arithmetic, but it is a
restatement of what needs explaining, not a cause.

The gate is **not** affected by the null `session_id`. `cost_model_gate.features()` takes `kind`
from `outcomes.jsonl` joined on `opportunity_id`, not from the request rows, and its `overlap`
counts are cell-wide interval counts by construction with no session key. Checked directly rather
than assumed, because the gate's FAIL verdict partly rests on the overlap spread. The kind splits
in the sections above are also unaffected, since a null `session_id` falls through to the dashcam
branch, which is correct.

### Where this leaves the lead

The cold share rises at the crossing, by enough work to account for much of the rate rise, and
**the cause is unresolved**: the one belief-side file cannot see it, the eviction hypothesis is
refuted at request level with the wrong sign, and the queue-to-cold hypothesis is untestable from
this log because dashcam requests carry no session identity. The measurement that would resolve it
does not exist yet: a per-dashcam-session cache log, or any engine-side insertion and eviction
trace. That is a concrete instrumentation ask rather than a file to go read, and it is the honest
end of the lead tonight.

**DEFECT to report, beside the null `n_requests` and `n_errors` in `cell.json`:** dashcam rows in
`request.jsonl` carry `session_id: null` while robot and single-shot rows are populated. Anything
keyed on dashcam session identity is silently impossible, and it fails by pooling rather than by
erroring, which is the shape that survives checks.
