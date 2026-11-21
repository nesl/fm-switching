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
