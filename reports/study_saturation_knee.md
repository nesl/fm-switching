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
