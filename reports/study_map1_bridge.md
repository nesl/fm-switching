# StudyMAP1-bridge: scoring live cells on the headline metric

Pre-registered in `research/EXPERIMENTS.md` (StudyMAP1-bridge) before anything was computed.
Offline analysis over committed measurements, on flash, **CPU only**: no GPU, no model server, no
inference. Code: `experiments/dashcam/map_bridge.py`. Results:
`results/dashcam/map1/map1_results.json`.

**One sentence.** The bridge works, its pre-registered validation gate passes, and applied to all
50 committed StudySLICE1 Part B and Part C cells it says that the episodic latency
differences those studies are about - a 9x spread in p99 delivery time across policies - move
Nexar challenge mAP by at most **0.0087**, with **every one
of the 27 paired bootstrap intervals including zero** and a per-cell CI width of about
**0.128**, which is twenty times the largest effect.

---

## 1. The mapping is exact, and was checked before anything was scored

A live request id is a StudyD14 1-s request id (`01040_t03_N1`). StudyD14b's own request manifest
carries that id on the coinciding 0.25-s grid point (`01040_t03.00_N1`, t = 3.0) in a field named
`d14_request_id`, so the mapping is a LOOKUP.

| check | result |
|---|---|
| distinct live episodic request ids | 1595 |
| mapped to a StudyD14b grid point | 1595 |
| unmapped | 0 |
| off the 0.25-s grid | 0 |
| interpolation used | **none** |

The pre-registered stop condition - different time bases with no exact mapping - **did not fire**.

## 2. The delivery model

For one episodic request, with the MEASURED server TTFT in place of StudyD7's constant:

```
L     = RTT (0.044 s) + request_bytes / uplink (13.6 Mbit/s) + measured TTFT     [StudyE9b (ii)]
read  = its own grid index + ceil(L / 0.25)        [the latency is never rounded; the READ is]
stream= hold the last value read, at every 0.25-s grid step                      [StudyE9b]
```

StudyE9b's RTT is a round trip, so the answer's downlink is already inside it. A request that
errored or produced no first token is not delivered and the application holds its previous value;
0 of 32142 rows
were skipped on that rule.

A DEVICE call - which no Part B or Part C cell makes, and which the future live baseline cells
will - uses the device arm's committed scores and StudyD8's latency through the same code path.

## 3. The validation gate, which is the pre-registered PASS

| check | expected | got | difference |
|---|---|---|---|
| delivered arrays identical to StudyE9d's `cloud_delivered`, per clip | 300 of 300 | **300 of 300** | - |
| device-fill arrays identical to the same function | 300 of 300 | **300 of 300** | - |
| challenge mAP, every TTFT = StudyE9b's constant cloud latency | 0.5675307471627267 | 0.5675307471627266 | **-1.11e-16** |
| challenge mAP, device fill | 0.4776042449177038 | 0.4776042449177038 | **5.55e-17** |

**PASS.** The delivery model reproduces StudyE9d's own arrays BIT FOR BIT on all 300 clips, which
is the exact reproduction the gate is about. The residual 1.1e-16 in the mAP is one unit in the
last place of a double: StudyE9c computed its committed number with scikit-learn's
`average_precision_score` and this bridge computes AP with StudyE9d's `ap_fast`, whose
equivalence StudyE9d control (d) verified on every real cell at a worst absolute difference of
exactly 1.1e-16. It is an AP implementation difference, not a delivery difference, and the pass
rule was stated in the code before the run.

## 4. Mechanism verification (CLAUDE.md Steps 1-5), recorded before the cells were scored

**Step 1 - the causal chain.** If a scheduling policy changes WHEN an episodic answer reaches the
application (FORMULATION.md "Objective": latency enters through whether a request meets its SLO,
and StudyE9b's delivery model is how a latency becomes an application-visible score), then the
application holds a stale score for longer, then the score it reads at the crop index of a
challenge event is an older one, then StudyE9c's challenge mAP falls. The bridge exists to turn
the first link - a measured TTFT - into the last - an mAP.

**Step 2 - every link instantiated.**

| causal link | implementing quantity | value / range in this run | varies as expected? | evidence |
|---|---|---|---|---|
| policy changes the delivery time | per-request `L` | mean 0.408 to 1.070 s, p99 0.497 to 4.711 s | YES, 9x across policies | the cell table below |
| a later delivery is read later | `ceil(L / 0.25)` shift | 2 to 20 grid steps | YES | section 2 |
| a later read changes what the application holds | fraction of grid steps whose held value differs from a zero-delay replay | median **0.467** of all grid steps | YES | per-cell `diagnostics` |
| a changed held value changes the crop score | challenge mAP | 0.4786 to 0.5090 over the cells | **weakly, and not reliably** | the headroom column |

No link is ABSENT or CONSTANT, so the protocol does not stop. The FOURTH link is the finding:
the delays change nearly half the grid and the metric barely moves.

**Step 3 - one unit traced.** `SLICE1B_P0_C1b_N1_L10`, request `01040_t03_N1`: content grid index
12 (t = 3.0 s on clip `01040.mp4`), measured TTFT from the committed row, L = 0.044 + 354,902 /
1,700,000 + TTFT, read index = 12 + ceil(L / 0.25), and the clip's held stream takes that
request's score from index `read` until the next request's read index. The whole cell is 350 such
requests over 12 clips; every other clip holds the device arm's own delivered stream.

**Step 4 - the negative control, as the row pre-registered it.** With ZERO added delay the bridge
must equal the no-delay reference: `zero_delay_control` builds both and they are
**identical** on every clip,
mAP 0.623358 against
0.623358.

**Step 5 - the alternative explanation.** A cell's mAP could move because the delivery times
moved (the claimed mechanism) or because the cell TOUCHED a different set of clips (more clips
means more of the metric comes from the cloud arm rather than the device fill). The two are
distinguished here: policies at the same condition and level issue the IDENTICAL request set -
Jaccard 1.000 over every committed Part C group - so a paired comparison holds the clip set fixed
and only the delivery times differ. The level-to-level rise in mAP (0.4832 at L10 to 0.5090 at
L40) is the alternative mechanism, and it is far larger than any policy difference.

---

## 5. Every committed cell

Full tables are in `results/dashcam/map1/map1_results.json`. Three groups are reproduced here.
"Headroom" is the mAP of replaying the SAME requests with zero added delay, minus the measured
mAP: it is the entire budget a latency policy has in that cell.

### StudySLICE1 Part B, C1a (KV-GPU, cold recall r = 0.05)

| policy | level % | challenge mAP | 95 % CI | streaming AP @0 | clips touched | mean delivery s | p99 delivery s | headroom |
|---|---|---|---|---|---|---|---|---|
| P0 | 10 | 0.4832 | [0.4329, 0.5606] | 0.01305 | 12 | 0.613 | 3.302 | -0.0033 |
| P1 | 10 | 0.4832 | [0.4329, 0.5606] | 0.01306 | 12 | 0.603 | 3.062 | -0.0033 |
| P2 | 10 | 0.4832 | [0.4329, 0.5606] | 0.01307 | 12 | 0.499 | 2.754 | -0.0033 |
| P3_1024 | 10 | 0.4832 | [0.4329, 0.5606] | 0.01306 | 12 | 0.419 | 0.650 | -0.0033 |
| P3_1024 | 20 | 0.4821 | [0.4351, 0.5602] | 0.01332 | 24 | 0.437 | 0.712 | +0.0006 |
| P3_2048 | 10 | 0.4832 | [0.4329, 0.5606] | 0.01306 | 12 | 0.423 | 0.807 | -0.0033 |
| P4 | 10 | 0.4832 | [0.4329, 0.5606] | 0.01307 | 12 | 0.408 | 0.497 | -0.0033 |
| P4 | 20 | 0.4793 | [0.4314, 0.5588] | 0.01332 | 24 | 0.425 | 0.649 | +0.0034 |
| P4 | 25 | 0.4820 | [0.4336, 0.5613] | 0.01351 | 27 | 0.420 | 0.594 | +0.0032 |
| P4 | 30 | 0.4900 | [0.4404, 0.5693] | 0.01377 | 33 | 0.429 | 0.610 | +0.0007 |
| P4 | 40 | 0.5046 | [0.4533, 0.5850] | 0.01462 | 44 | 0.453 | 0.769 | +0.0064 |

### StudySLICE1 Part B, C1b (KV-GPU, cold recall r = 0.1)

| policy | level % | challenge mAP | 95 % CI | streaming AP @0 | clips touched | mean delivery s | p99 delivery s | headroom |
|---|---|---|---|---|---|---|---|---|
| P0 | 10 | 0.4861 | [0.4364, 0.5639] | 0.01310 | 12 | 1.001 | 4.581 | -0.0062 |
| P1 | 10 | 0.4862 | [0.4364, 0.5640] | 0.01311 | 12 | 0.944 | 3.100 | -0.0062 |
| P2 | 10 | 0.4838 | [0.4335, 0.5613] | 0.01303 | 12 | 0.766 | 3.025 | -0.0038 |
| P3_1024 | 10 | 0.4834 | [0.4331, 0.5609] | 0.01307 | 12 | 0.448 | 0.676 | -0.0035 |
| P3_1024 | 20 | 0.4873 | [0.4381, 0.5666] | 0.01333 | 24 | 0.452 | 0.726 | -0.0046 |
| P3_2048 | 10 | 0.4860 | [0.4357, 0.5638] | 0.01309 | 12 | 0.449 | 0.836 | -0.0061 |
| P4 | 10 | 0.4832 | [0.4329, 0.5606] | 0.01307 | 12 | 0.411 | 0.516 | -0.0033 |
| P4 | 20 | 0.4786 | [0.4306, 0.5577] | 0.01331 | 24 | 0.426 | 0.608 | +0.0042 |
| P4 | 25 | 0.4855 | [0.4380, 0.5634] | 0.01351 | 27 | 0.455 | 0.872 | -0.0003 |

### StudySLICE1 Part C, C2 (KV-HOST k = 8, warm only)

| policy | level % | challenge mAP | 95 % CI | streaming AP @0 | clips touched | mean delivery s | p99 delivery s | headroom |
|---|---|---|---|---|---|---|---|---|
| P0 | 10 | 0.4832 | [0.4329, 0.5606] | 0.01307 | 12 | 0.417 | 0.532 | -0.0033 |
| P0 | 20 | 0.4831 | [0.4362, 0.5612] | 0.01332 | 24 | 0.435 | 0.604 | -0.0003 |
| P0 | 25 | 0.4846 | [0.4371, 0.5619] | 0.01352 | 27 | 0.433 | 0.603 | +0.0006 |
| P0 | 30 | 0.4899 | [0.4402, 0.5688] | 0.01377 | 33 | 0.442 | 0.628 | +0.0008 |
| P0 | 40 | 0.5088 | [0.4566, 0.5872] | 0.01462 | 44 | 0.464 | 0.750 | +0.0022 |
| P5 | 10 | 0.4832 | [0.4329, 0.5606] | 0.01307 | 12 | 0.426 | 0.557 | -0.0033 |
| P5 | 20 | 0.4822 | [0.4351, 0.5604] | 0.01332 | 24 | 0.432 | 0.595 | +0.0005 |
| P5 | 25 | 0.4846 | [0.4371, 0.5619] | 0.01352 | 27 | 0.433 | 0.611 | +0.0006 |
| P5 | 30 | 0.4909 | [0.4405, 0.5698] | 0.01377 | 33 | 0.441 | 0.642 | -0.0002 |
| P5 | 40 | 0.5080 | [0.4563, 0.5865] | 0.01462 | 44 | 0.462 | 0.767 | +0.0030 |

## 6. The paired comparisons

Clip bootstrap, 2,000 resamples, seed 0, paired across policies (the same resampled clips score
both arms), against P0 where the group has one.

| study | condition | level % | comparison | difference in mAP | 95 % CI | verdict |
|---|---|---|---|---|---|---|
| SLICE1B | C1a | 10 | P1 vs P0 | +0.0000 | [+0.0000, +0.0000] | includes 0 |
| SLICE1B | C1a | 10 | P2 vs P0 | +0.0000 | [+0.0000, +0.0000] | includes 0 |
| SLICE1B | C1a | 10 | P3_1024 vs P0 | +0.0000 | [+0.0000, +0.0000] | includes 0 |
| SLICE1B | C1a | 10 | P3_2048 vs P0 | +0.0000 | [+0.0000, +0.0000] | includes 0 |
| SLICE1B | C1a | 10 | P4 vs P0 | +0.0000 | [+0.0000, +0.0000] | includes 0 |
| SLICE1B | C1a | 20 | P4 vs P3_1024 | -0.0028 | [-0.0109, +0.0016] | includes 0 |
| SLICE1B | C1b | 10 | P1 vs P0 | +0.0000 | [+0.0000, +0.0002] | includes 0 |
| SLICE1B | C1b | 10 | P2 vs P0 | -0.0023 | [-0.0081, +0.0006] | includes 0 |
| SLICE1B | C1b | 10 | P3_1024 vs P0 | -0.0027 | [-0.0085, +0.0003] | includes 0 |
| SLICE1B | C1b | 10 | P3_2048 vs P0 | -0.0001 | [-0.0007, +0.0004] | includes 0 |
| SLICE1B | C1b | 10 | P4 vs P0 | -0.0029 | [-0.0087, +0.0003] | includes 0 |
| SLICE1B | C1b | 20 | P4 vs P3_1024 | -0.0087 | [-0.0260, +0.0000] | includes 0 |
| SLICE1B | C4 | 10 | P1 vs P0 | +0.0000 | [+0.0000, +0.0001] | includes 0 |
| SLICE1B | C4 | 10 | P2 vs P0 | -0.0024 | [-0.0082, +0.0006] | includes 0 |
| SLICE1B | C4 | 10 | P3_1024 vs P0 | -0.0027 | [-0.0085, +0.0003] | includes 0 |
| SLICE1B | C4 | 10 | P3_2048 vs P0 | -0.0001 | [-0.0007, +0.0004] | includes 0 |
| SLICE1B | C4 | 10 | P4 vs P0 | -0.0027 | [-0.0085, +0.0003] | includes 0 |
| SLICE1C | C2 | 10 | P5 vs P0 | +0.0000 | [+0.0000, +0.0000] | includes 0 |
| SLICE1C | C2 | 20 | P5 vs P0 | -0.0009 | [-0.0031, +0.0007] | includes 0 |
| SLICE1C | C2 | 25 | P5 vs P0 | +0.0000 | [+0.0000, +0.0001] | includes 0 |
| SLICE1C | C2 | 30 | P5 vs P0 | +0.0010 | [-0.0002, +0.0032] | includes 0 |
| SLICE1C | C2 | 40 | P5 vs P0 | -0.0008 | [-0.0027, +0.0003] | includes 0 |
| SLICE1C | C4 | 10 | P5 vs P4 | +0.0000 | [+0.0000, +0.0000] | includes 0 |
| SLICE1C | C4a | 10 | P4 vs P0 | +0.0000 | [+0.0000, +0.0000] | includes 0 |
| SLICE1C | C4a | 10 | P5 vs P0 | +0.0000 | [+0.0000, +0.0000] | includes 0 |
| SLICE1C | C4a | 10 | P5nc vs P0 | +0.0000 | [+0.0000, +0.0001] | includes 0 |
| SLICE1C | C4a | 20 | P5 vs P4 | -0.0009 | [-0.0032, +0.0007] | includes 0 |

**Not one interval excludes zero.** The largest difference in the whole set is
+0.0087 mAP.

## 7. What this says, and what it does not

1. **The bridge is correct and cheap.** It reproduces StudyE9c's committed arms through the same
   per-request code path a live cell uses, and it scores all 50 committed cells in
   about a minute of CPU.
2. **At these loads the headline metric cannot see the capacity story.** StudySLICE1's policies
   differ by 9x in p99 delivery time inside a single condition (C1b L10: P0 4.581 s against
   P4 0.516 s) and by at most 0.0087 mAP, against a per-cell
   CI width of 0.128. The headroom column says the same thing from the
   other side: replaying a cell with zero added delay changes its mAP by between
   -0.0062 and +0.0064, and the median headroom is **negative**
   (-0.0033), which is only possible if the differences are inside the
   metric's own resolution on these clip sets.
3. **Three structural reasons, all of them properties of the CELLS and not of the bridge.** A
   Part B or Part C cell walks StudyD14's manifest with one cursor, so it issues cloud requests
   for 12 to 44 of
   the 300 scored clips and the other 250-plus hold the device arm's value; the requests are
   StudyD14's 1-s grid, not the 0.5-s cadence StudyE9c's always-cloud arm uses; and the challenge
   crop reads ONE grid point per clip, so a delay only matters if it crosses that point.
4. **This is a measurement of these cells, not of the system.** The target system's cadence model
   (StudySLICE1 Part D-b: a fleet of streams at a fixed cadence with jitter) issues a request per
   stream per cadence period on clips it plays continuously. Part B and Part C stream counts and
   request schedules differ from it, which the row pre-registered as a limitation and which
   section 8 states again.
5. **What would make the metric resolve a latency policy**: more clips touched per cell (the
   cursor is the binding constraint), a cadence at or below 0.5 s so consecutive grid points are
   covered, and cells long enough for the crop points of many clips to fall inside the window.
   All three are properties of the Part D cell design, and all three are cheap to change there.

## 8. Results consistency check (CLAUDE.md, six checks)

**1. Cross-check against committed measurements.**

| quantity | this run | prior run | source of prior | ratio | agree |
|---|---|---|---|---|---|
| challenge mAP, always-cloud 32BI_N1 at measured@25 | 0.5675307472 | 0.5675307472 | StudyE9c `e9c_results.json` | 1.0000000000 | **agree (1 ulp)** |
| challenge mAP, device-only 4BI_N1 at measured@25 | 0.4776042449 | 0.4776042449 | StudyE9c | 1.0000000000 | **agree (1 ulp)** |
| delivered arrays | identical on 300 clips | StudyE9d `cloud_delivered` | StudyE9d | - | **agree, bit-exact** |
| episodic p99 delivery, C1b L10 P0 against P4 | 4.581 s against 0.516 s | StudySLICE1 Part B reports the same ordering and magnitude | `reports/study_slice1.md` | - | agree |

No disagreement above 2x anywhere.

**2. Physical plausibility.** Every delivery time is RTT + an uplink transfer of a committed
request size + a MEASURED TTFT, so nothing can be faster than the committed curves by
construction: the minimum possible L is 0.044 + 0.209 + min(TTFT) = 0.408 s at the mean, and the
observed means run from 0.408 to 1.070 s. No rate implied here exceeds a committed one.

**3. Distribution sanity.** Per-cell spreads are reported, not only medians: the mAP CI
(0.1277 wide at the median, 0.1244 to 0.1317), the
per-request latency mean and p99, and the fraction of the grid the delays change. Several cells
agree to four decimals - P0, P1 and P3_2048 at C1b L10, for instance - and that agreement is
EXPLAINED rather than assumed: those policies deliver the same scores at read indices that differ
by fewer grid steps than the crop spacing, and the diagnostics column shows the underlying
delivery times differing while the metric does not.

**4. Definition audit.** challenge mAP = StudyE9c's definition through StudyE9d's `Challenge`
class, one crop per clip at horizons 0.5 / 1.0 / 1.5 s, unweighted mean. streaming AP =
StudyE9b's `ApEngine` at horizons 0.0 / 0.5 / 1.0 / 1.5 s. Grid step 0.25 s (StudyD14b). Hold
shift = ceil(L / 0.25) (StudyE9b). Device latency 0.567 s and device cadence 0.75 s (StudyD8 /
StudyE9b). Every one of these is imported from the study that defined it, not re-implemented.

**5. Claim linkage.** The headline bears on FORMULATION.md's objective (the fraction of requests
meeting the latency SLO, and what that is worth in task value) and on CLAIMS.md's position that
placement and timing decisions change application value. It **weakens** the case that episodic
latency differences of the size StudySLICE1 produces are worth anything in challenge mAP ON THESE
CELLS, and it says nothing about the target system's cadence model, which this bridge has not yet
been applied to.

**6. Proxy validity.** Two proxies, both declared. (a) **The device fill**: clips a cell never
requested are scored with the device arm's own delivered stream, because the device always runs
in our system. It is valid for the LEVEL of a cell's mAP only to the extent that assumption holds,
and it is identical across policies, so it cannot create or hide a policy difference. (b) **The
request-to-grid identity**: a live request's content is StudyD14's 1-s request and its score is
StudyD14b's score at the coinciding grid point - the manifest says they are the same request, so
this is an identity rather than a proxy.

## 9. One command

```
python3 experiments/dashcam/map_bridge.py --out results/dashcam/map1/map1_results.json
# a future cell set, e.g. StudySLICE1 Part D or the first live baseline cells:
python3 experiments/dashcam/map_bridge.py --rows results/cost/study_slice1/slice1_partd_requests_h100nvl.jsonl \
    --out results/dashcam/map1/map1_partd.json
```

The validation gate and the mapping check run first on every invocation, and the command exits
2 without writing a score if either fails.

## 10. Files

| file | what |
|---|---|
| `experiments/dashcam/map_bridge.py` | the bridge: mapping, delivery model, scoring, paired bootstrap, validation gate, CLI |
| `results/dashcam/map1/map1_results.json` | the mapping check, the gate, the zero-delay control, 50 scored cells and 27 paired comparisons |
