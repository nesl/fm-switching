# D190 (5) TRACK C: why the lagging recall devices miss in RUNG 3

Read-only diagnosis. No policy code written, no live cell run, no cell list posted.

- origin/main read at the single literal sha `c9fc3eacfa065e7828c2824f3c9418ded2f3a452`.
- Result file: `results/orchestration/live2/frozen_test/d190_recall_lag_diagnosis.json`.
- Question: in RUNG 3 (`covex-v6-fair-c5attr`) some recall devices sit at 0.17 on-time at seed 5
  and 0.14 at seed 7. Diagnose them, and say what a keep-ready policy would have to change.

## Cells used, and why these

`d185_rung3_verdict.json` `per_seed[].cells.shares` names the rung-3 arm cells directly
(`arms.shares = covex-v6-fair-c5attr`):

- seed 5: `results/orchestration/live2/frozen_test/runs/covex-v6-fair-c5attr_n16_s5_1200s_h27_3t_L3_epg_rq30`
- seed 7: `results/orchestration/live2/frozen_test/runs/covex-v6-fair-c5attr_n16_s7_1200s_h27_3t_L3_epg_rq30`

The sibling `..._rerun` directories at both seeds hold only `mm_gate.json` and
`mm_uuid_check.json`, i.e. preflight stubs with no `outcomes.jsonl.gz`, `request.jsonl.gz` or
`decision.jsonl.gz`, so they are not the scored cells. Every reader in this diagnosis asserts the
file exists and is non-empty and raises on a missing or empty file rather than falling back to an
empty dict; `coordinator_result.json` is present and non-empty in both cells (both are plain
`.json`, not `.json.gz`).

`research/EXPERIMENTS.md` at that sha carries no INVALID mark on `covex-v6-fair-c5attr`,
`covex-v6-state-uo-c5attr`, `hybrid-F-lhreq-noc3`, `always-cloud-fcfs` or `edf`. Nothing marked
INVALID is cited or recomputed from.

**Register on the comparison.** The two cells are the same arm, the same code revision and the
same posted knobs at two different seeds, so this is not an arm-versus-arm comparison and no
input/stack/decoding difference is claimed. Where another arm is cited
(`always-cloud-fcfs_n16_s7`, `edf_n16_s7`) it is used only as an independent reading of
`history_tokens`, which is trace-determined and therefore identical across arms by construction.

## The lagging devices

| seed | device | sessions asked | n questions | on time | fraction | fairness weight w_d |
|---|---|---|---|---|---|---|
| 5 | `robo001` | `s000` (1 Q), `s001` (4 Q), `s002` (1 Q) | 6 | 1 | 0.166667 | 2.555556 |
| 7 | `robo004` | `s000` (18 Q), `s001` (3 Q) | 21 | 3 | 0.142857 | 2.682540 |

OBSERVED from each cell's own `cell.json` `score.score.sweep[0].robot_per_device`. Both devices
were the cell's `robot_worst_device`. Both carried near the maximum fairness weight, so the
ordering consumer was pushing them to the FRONT of the queue and they still missed.

**Positive control on the cell choice, not only on the result.** `cell.json`
`robot_pool_on_time` / `robot_pool_n` is 114 / 127 at seed 5 and 84 / 105 at seed 7, which
reproduces `d185_rung3_verdict.json` `check_2_robot_retention.on_time_counts.shares` and
`robot_pool_n.shares` exactly at both seeds. A wrong directory would not have reproduced the
committed verdict.

## Why each question missed

OBSERVED CENSUS over all 23 misses (5 + 18), not a sample and not a construction.

| bucket | count | evidence |
|---|---|---|
| (a) b7 feasibility decline of a cold rebuild | **3** | seed 5 `d6206` / `d6265` / `d6303`, `kind=decline`; BELIEF tier COLD and `telemetry_cached_tokens` 0 at all three; `hybrid_arm.py:401` `est = recall_ttft_s(history, COLD)` = 6.190 / 6.285 / 6.356 s against 2.946 s of slack, so `hybrid_arm.py:425-426` returns REJECT. `arm_stats.over_limit_infeasible` is absent (0) in this cell, so these are not bucket (b). |
| (b) over the 32,768-token limit (D170) | **18** | seed 7: all 18 declines in the cell, one-to-one with the 18 trace-determined over-limit opportunity ids, and `arm_stats.over_limit_infeasible = 18` with `over_limit_tokens_max = 52861`. `hybrid_arm.py:410-420` fires on `readiness_tokens > CONTEXT_LIMIT_TOKENS` (`hybrid_arm.py:157` = 32768). |
| (c) share or oversize denial (`oversize_wait_for_own_type`) | **0** | ABSENT BY CONSTRUCTION on the c5attr base. The reader is `coordinator.py:1319` `_share_ok(kind='recall')`, gated at `coordinator.py:343` on `SA.arm_enables(arm)`. In both cells `arm_stats` has no `share_admission` key, which `coordinator.py:1506-1507` adds iff the gate is enabled, and `counts` has no `share_*` key. Prior: `d185_fair_c5attr_gate.json` measured the split consumer at exactly 0 differing decisions on this base. |
| (d) queue: sent but answered after the 3 s deadline | **1** | seed 5 `opp0008040`, released `d5831` at t=791.76, `r5831` first token at 797.102, TTFT 5.3166 s. |
| (e) release-time infeasibility re-check (D179 (4)) | **0** | SWITCH OFF. `release_infeasible_events_total = 0` in both `coordinator_result.json`, and a census of the decision-kind field over 9,237 rows at seed 5 and 13,775 rows at seed 7 contains no `release_infeasible` row. |
| (f) late for another reason, named: **run-horizon truncation** | **1** | seed 5 `opp0012248`, released `d9231` at t=1199.76 from a GPU-WARM belief. It is in `counts.recall_CLOUD` (480) and not in `counts.completed_recall` (479), the single difference in the cell. The window is 1200.0 s and `t_opportunity + deadline` is 1202.65 s, so no policy could have been observed answering it. Falls identically on every arm. |

**First cause where two buckets could apply.** `opp0008040` is bucket (d) by the taxonomy (sent,
answered late), but the first cause in time is the residency state at release: the arm released on
a GPU-WARM BELIEF while the ENGINE reported 5,840 of 20,356 prompt tokens cached, 71.3 percent
uncached. The D162 decomposition of its predicted 3.7216 s is own-uncached 2.6477 s (71 percent),
queue 1.0056 s (27 percent), intercept 0.0678 s. Primary classification (d); first cause partial
residency.

## History size and residency at each question

`history_tokens` is OBSERVED from the deterministic trace, re-generated read-only with
`trace.generate_trace` on the posted cell args. The `trace.py` used has blob sha
`c3b90970f1f18ec0f639abb03cd1e4f2d5e9e5f2`, byte-identical to
`c9fc3eac:experiments/orchestration/live2/fleet/trace.py`. No cell was run.

The residency column is the coordinator's BELIEF (`residency.jsonl` `believed_tier`), beside the
ENGINE-REPORTED cached tokens. Where the question was actually sent, the ENGINE's own
`prompt_tokens - cached_tokens` is given and is the figure used; where it was declined there is no
engine row, and that is stated rather than papered over with the belief.

### seed 5, `robo001`

| opp | t | session | history (trace) | BELIEF | telemetry cached (engine) | uncached (engine) | queued ahead (engine) | TTFT | outcome |
|---|---|---|---|---|---|---|---|---|---|
| `opp0003224` | 326.80 | s000 | 15,061 | gpu | 5,936 | 8,215 of 15,143 | 2,873 | 2.7819 | ON TIME |
| `opp0008040` | 791.66 | s001 | 20,281 | gpu | 7,376 | 14,516 of 20,356 | 6,548 | 5.3166 | MISS (d) |
| `opp0008804` | 865.01 | s001 | 23,521 | **cold** | **0** | not sent | 8,838 | n/a | MISS (a) |
| `opp0008886` | 873.46 | s001 | 23,881 | **cold** | **0** | not sent | 368 | n/a | MISS (a) |
| `opp0008925` | 878.31 | s001 | 24,151 | **cold** | **0** | not sent | 1,056 | n/a | MISS (a) |
| `opp0012248` | 1199.65 | s002 | 11,641 | gpu | 4,048 | not completed | 745 | n/a | MISS (f) |

Three of the four s001 questions are re-asks of `opp0008040` (`reask_of` in the trace).

### seed 7, `robo004`

All 18 misses are in one session, `robo004|s000|1848337166005249_start_0.0_end_1199.976`, the
longest robot session in the cell. `history_tokens`, in order of `t_opportunity`: 34,051 / 34,591
/ 35,131 / 35,221 / 38,101 / 38,821 / 39,271 / 39,991 / 40,171 / 43,771 / 46,831 / 48,811 /
50,521 / 50,611 / 51,601 / 51,781 / 52,501 / 52,861. Eighteen distinct, strictly increasing
values, so this is not a constant standing in for a distribution. 15 of the 18 are re-asks, which
is exactly `over32k_s7_finding.json`'s `robot_reasks_beyond_32k = 15`. The BELIEF at all 18 was
**gpu**, with ENGINE `telemetry_cached_tokens` rising 9,904 to 13,856. **The session was being
kept warm and the questions were still unanswerable.** The three on-time questions are in
`s001` at 7,141 / 7,321 / 9,121 history tokens with engine-uncached 4,181 / 313 / 1,921.

**Belief against engine, which is the distinction this diagnosis exists to make.** On
`opp0008040` the BELIEF tier GPU-WARM feeds `hybrid_arm.py:401`
`recall_ttft_s(20,281, 'GPU-WARM') = 0.6506 s`, and the observed first token was 5.3166 s, 8.17x
the arm's own estimate. D186 recorded rung-2 recall at a median 1,177 to 1,438 engine uncached
tokens against the base's cold 7,717; `robo001`'s two sends are 8,215 and 14,516, that is 5.7x and
10.1x the rung-2 median and 1.1x and 1.9x the base's cold figure. No disagreement to reconcile:
same quantity, different stratum, consistent direction. These laggards are exactly the sessions
whose history was not held resident.

## The counterfactual: would a warm history have made the question feasible

Model, as instructed and as committed in
`cost_model_gate_d162.json` `model.first_token`:
`first_token = 0.0678 + 0.000182 x uncached + 0.000154 x uncached_queued_ahead`
(exactly 0.06779759059832724, 0.0001824312597782467, 0.0001535807289338535).

- **uncached fed, warm case: 80 tokens. CONSTRUCTED.** On the only two engine-reported `robo001`
  sends, `prompt_tokens - history_tokens` was 82 and 75, so a fully resident history leaves about
  80 uncached question tokens. This is the IDEAL keep-ready case and therefore an upper bound on
  what keep-ready can buy.
- **uncached fed, cold case: the trace `history_tokens`.** OBSERVED.
- **`uncached_queued_ahead`: PROXY, declared.** The committed model's queue term is the engine's
  own running total (`coordinator.py:1293` passes `queued_uncached_ahead=self._w.total()`), which
  is not in the per-cell logs. It is reconstructed here from `request.jsonl.gz` as the sum of
  `prompt_tokens - cached_tokens` over requests submitted at or before the decision instant whose
  `t_first_token` had not yet arrived. Valid for this claim (built from engine-reported counts and
  real stamps, monotone in the quantity it estimates) and used only inside the counterfactual,
  never as a headline measurement.
- **Budget.** 3.0 s minus the observed median robot submit delay (0.0884 s at seed 5, 0.0618 s at
  seed 7) minus the forward hop (0.022176 s) gives a 2.889 / 2.916 s first-token budget. The
  committed PRIMARY on-time rule scores COMPLETION, not first token (D146), so a completion-basis
  budget is reported beside it: 2.847 / 2.871 s, using the cell's own observed median robot decode
  (0.0428 / 0.0454 s). Both bases are reported because the instruction names the first token and
  the committed scorer names the completion.

**Positive control on the model, run on these very devices before trusting it.** D162 against the
five rows that WERE sent:

| opp | uncached (engine) | queued ahead | predicted | observed TTFT | observed / predicted |
|---|---|---|---|---|---|
| `opp0003224` | 8,215 | 2,873 | 2.0077 | 2.7819 | 1.3856 |
| `opp0008040` | 14,516 | 6,548 | 3.7216 | 5.3166 | 1.4286 |
| `opp0011227` | 4,181 | 2,624 | 1.2335 | 1.8596 | 1.5075 |
| `opp0011265` | 313 | 378 | 0.1830 | 0.3425 | 1.8721 |
| `opp0011680` | 1,921 | 1,473 | 0.6445 | 1.0001 | 1.5518 |

The committed fit reports `ratio_p50` 1.0261 over 33,401 rows; in this multi-thousand-uncached
tail it under-predicts by 1.39x to 1.87x. Every conversion below is therefore also reported with
the worst observed factor applied as a stress.

### The split, which is the finding

| | count | share of 23 |
|---|---|---|
| a warm or kept-ready history CONVERTS the miss | **4** | 17.4 % |
| would have missed ANYWAY because of queued work ahead | **0** | 0 % |
| above the 32,768-token limit: keep-ready is irrelevant at any residency | **18** | 78.3 % |
| run-horizon truncation: unobservable for every arm | **1** | 4.3 % |

The four conversions, all seed 5, all `robo001`:

| opp | queued ahead (observed) | predicted warm first token | stressed x1.4286 | first-token budget | completion budget | converts |
|---|---|---|---|---|---|---|
| `opp0008040` | 6,548 | 1.088 | 1.554 | 2.889 | 2.847 | yes |
| `opp0008804` | 8,838 | 1.440 | 2.057 | 2.889 | 2.847 | yes |
| `opp0008886` | 368 | 0.139 | 0.198 | 2.889 | 2.847 | yes |
| `opp0008925` | 1,056 | 0.245 | 0.349 | 2.889 | 2.847 | yes |

All four survive the stress, the tightest at 2.057 s against 2.889 s, and all four survive the
completion-basis budget. **Nothing in these 23 misses is doomed by the queue**: the largest queue
term among the misses is 0.0678 + 0.000154 x 8,838 = 1.429 s, well inside the budget, so the
engine being busy is never on its own sufficient to miss. The cold-basis predictions for the same
four rows are 4.773 / 5.716 / 4.481 / 4.636 s, i.e. the own-history term is what breaks them.

**Do not average this.** The convertible misses are concentrated on ONE device-session,
`robo001|s001`, inside the 87 s window t=791.8 to t=878.4. Mixing weight: 4 of 13 recall-pool
misses at seed 5 (30.8 percent of that seed's misses) and 0 of 21 at seed 7, so 4 of 34
(11.8 percent) across the two seeds. The pooled 11.8 percent reads as "warming barely matters" and
is wrong about both seeds in opposite directions.

## What a keep-ready policy would have to change

**1. Hold the session across the gap.** `robo001|s001` residency, OBSERVED: cold at t=388.23, gpu
from t=434.76 with `telemetry_cached_tokens` climbing 992 to 7,376 by t=756.54, **COLD with
telemetry 0 at t=843.49**, gpu again at t=925.21 with telemetry 21,232. The three declines at
t=865.06 / 873.56 / 878.36 sit inside that cold window, and the history read fully resident
**46.85 s after the last question that needed it**. Worse, the re-prefill was already paid for: the
touch `r6067` at t=837.79 reports `prompt_tokens` 21,251, `cached_tokens` 0, `cache_path` COLD
(engine-reported), so 21k tokens were re-prefilled 27 s before the first decline and the arm
declined three questions on a belief that had already been overtaken.

**2. The maintenance channel is rate-limited below the rate at which the history grows.** Touch
cadence is one per 46.00 s (nine consecutive gaps of 45.99 to 46.01 s on `robo001|s001`), each
adding 990 prompt tokens and 11 frames: a build rate of 21.5 tokens/s per session (CONSTRUCTED).
The robot history grows at 44.9 tokens/s (CONSTRUCTED from the trace's own `history_tokens` on
`robo004|s000`: (52,861 - 34,051) / (916.67 - 499.25)). The built prefix therefore never catches
the history: `robo004|s000` reached 52,861 trace tokens with 14,861 built (28.1 percent),
`robo001|s001` reached 20,281 with 8,921 built (44.0 percent). A keep-ready policy that only keeps
the EXISTING prefix hot does not fix this. It has to raise the build rate (larger or more frequent
touches) or stop promising full-history answers.

**3. The feasibility test reads a tier where it needs a resident token count.** Reader:
`hybrid_arm.py:401` `est = C.recall_ttft_s(max(q.readiness_tokens, 1), q.readiness)`, consumed by
the CLOUD / DEFER / REJECT branch at `hybrid_arm.py:421-426`. That is a read which changes a
decision, not a write-only field. Writer: `cstate.py:138` `residency_readiness()`, returning one of
three TIER LABELS from `cstate.py:135` `believed_tier()`. The estimate prices the FULL
`readiness_tokens` at the tier's warm rate, so GPU-WARM at 44 percent resident and GPU-WARM at
28 percent resident cost the same. **The quantity that would have caught it already exists and
does not reach the gate:** `hybrid_arm.py:526-534` `_unbuilt_rebuild_s` reads
`roster['built_tokens_by_session']` and prices the unbuilt remainder as a cold prefill, but its
only consumer is the C2 risk flag at `hybrid_arm.py:404-409`. On `opp0008040` it would have
returned (20,281 - 8,921) / 3,800 = 2.989 s, giving work = 0.6506 + 2.989 = 3.640 s against
2.8995 s of slack. The arm held a quantity that predicted the miss and spent it on throttling
dashcam frames. So: gate the recall send on `est + _unbuilt_rebuild_s(q)`; decide keep-ready on
resident tokens, not on a tier label; and treat a telemetry `cached_tokens` of 0 as evidence about
the instant it was taken, not about the future.

**4. What keep-ready cannot fix.** 78.3 percent of these misses are above the 32,768-token limit
and 4.3 percent are the run horizon. For the over-limit stratum the only levers are a shorter
REPRESENTATION (`simplestream` released all 18 at 467 tokens, per `d170_overlimit.json`) or a
larger max-model-len. D170 already ruled that the harness must COUNT and not truncate, so this is
a policy axis, not a harness fix.

**5. Where the next counterfactual should be scored.** On seed 5, and on the per-device minimum,
not the pool fraction. The seed-5 pool fraction is 114 / 127 = 0.8976 and already passes check 2
at retention 0.9886; the whole lag is five questions on one device, which the pool number cannot
see. At seed 7 the per-device floor of 0.1429 on `robo004` is immovable by residency: a keep-ready
arm scored there has headroom of 0 of 21 misses.

**Pre-registered warning for that run (CLAUDE.md Rule 2).** If a keep-ready arm is scored on seed 7
robot on-time it will produce a NULL, and that null would be INCONCLUSIVE - UNEXERCISED, not a real
negative, because 18 of the 21 misses there have no reachable path for the mechanism. On seed 5 the
ceiling is 4 convertible questions on one device, which is where a power calculation has to start.
Both figures are recorded here BEFORE the run.

## Alternative explanations

1. *The seed-5 declines are the arm's `defer_s` being too short, not an eviction.* Distinguished:
   the BELIEF tier and the ENGINE telemetry both read COLD / 0 at all three declines while the same
   session read gpu / 7,376 seventy-three seconds earlier and gpu / 21,232 forty-seven seconds
   later. The input to the arithmetic changed, not the arithmetic.
2. *`robo004`'s seed-7 lag is a queue or fairness-ordering effect, the over-limit declines
   incidental.* Distinguished: the fairness feed gave `robo004` the LARGEST recall weight in the
   cell (2.68254, against 1.0 for the four devices at or above 0.9), so ordering was pushing it to
   the front, and it still missed 18. The 18 declines are one-to-one with the 18 trace-determined
   over-limit ids and with `arm_stats.over_limit_infeasible = 18`. No ordering can serve a prompt
   the engine refuses.
3. *The warm conversions are an artefact of D162 being optimistic in the tail.* Partially
   distinguished: the worst observed under-prediction on these devices' own sent rows (1.4286x at
   seed 5, 1.8721x at seed 7) is applied as a stress and all four conversions survive it. They do
   not survive an arbitrary 3x, which is stated rather than hidden.

## Consistency checks

1. **Cross-check against committed measurements.**

| quantity | this run | prior run | source of prior | ratio | agree |
|---|---|---|---|---|---|
| over-limit recall opportunities, seed 7 | 18 | 18 | `d170_overlimit.json`, `over32k_s7_finding.json` | 1.00 | agree (ids set-identical) |
| max history tokens, seed 7 | 52,861 | 52,861 | `d170_overlimit.json`, `over32k_s7_finding.json`, this cell's `arm_stats.over_limit_tokens_max` | 1.00 | agree |
| `history_tokens` `opp0006097` | 38,821 | 38,821 | `always-cloud-fcfs_n16_s7` `tokens_charged` (OBSERVED, different arm) | 1.00 | agree |
| `history_tokens` `opp0008403` | 48,811 | 48,811 | same | 1.00 | agree |
| beyond-32k re-asks, seed 7 | 15 | 15 | `over32k_s7_finding.json` `robot_reasks_beyond_32k` | 1.00 | agree |
| `robo001` n questions / on time, seed 5 | 6 / 1 | 6 / 1 | this cell's `cell.json`, reproduced in `d185_rung3_verdict.json` pool counts | 1.00 | agree |
| `robo004` n questions / on time, seed 7 | 21 / 3 | 21 / 3 | same | 1.00 | agree |
| recall engine-uncached tokens, lagging stratum | 8,215 / 14,516 | 1,177 to 1,438 (rung-2 median), 7,717 (base cold) | D186 | 5.7x / 10.1x vs median | agree: different stratum, consistent direction, and this is the point of the diagnosis |

No disagreement above 2x on the same stratum.

2. **Physical plausibility.** The smallest predicted warm first token is 0.139 s, which is the
D162 intercept plus two linear terms, not a measured rate. The implied prefill rate of the
uncached term is 1 / 0.000182 = 5,488 tok/s, BELOW the committed A6000 cold prefill of about
7,100 tok/s, so no result implies a faster-than-measured rate. The cold rebuild estimates use
`costs.COLD_PREFILL_TOK_S` = 4,500 tok/s at 11k and 3,800 tok/s at 28k, also below the committed
curve. No flag.

3. **Distribution sanity.** The 18 seed-7 history sizes are 18 distinct strictly increasing values,
no constant where a distribution belongs. The spread is real but it cannot carry the meaning
"keep-ready would help", because every value is above the context limit; it says only how far
above. Medians are reported with their min/max: robot decode 0.0097 / 0.0428 / 1.3685 s at seed 5
and 0.0081 / 0.0454 / 1.3549 s at seed 7; robot submit delay 0.051 / 0.0884 / 0.1258 s at seed 5
and 0.0583 / 0.0618 / 0.081 s at seed 7. The concentration of the effect on one device-session is
reported with its mixing weight above.

4. **Definition audit.** `history_tokens` = the trace's full-history token count for a recall
question, the same field `d170_overlimit.json` reads and the same quantity `hybrid_arm.py` sees as
`readiness_tokens`. `uncached` = engine `prompt_tokens - cached_tokens`, the D179 (6) /
D186 definition. The 32,768 limit is `hybrid_arm.py:157` `CONTEXT_LIMIT_TOKENS`, the same number as
the server's `--max-model-len`. "on time" PRIMARY is the committed completion-delivery rule
(D146); the per-device fractions quoted are the cells' own committed score blocks, so the
definition is the scorer's, not this diagnosis's. First token versus completion is marked at every
use. No name is used here with two definitions.

5. **Claim linkage.** This bears on the physical component of Context Inertia: reconstruction
latency grows with context length. It SUPPORTS that for the seed-5 laggard (6.19 to 6.36 s of cold
rebuild against a 3.0 s deadline; 14,516 engine-uncached tokens on the one send). It does NOT speak
to the semantic component; nothing here measures fidelity. Nothing measured is cross-tier KV
transfer, which FORMULATION.md section Scoping puts out of scope: all residency here is one
engine's own prefix cache.

6. **Proxy validity.** Two proxies, both declared at point of use: `uncached_queued_ahead`
reconstructed from `request.jsonl.gz` (valid, engine-reported inputs, used only inside the
counterfactual, never as a headline), and the 80-token warm `uncached` figure (CONSTRUCTED from two
engine rows; an upper bound on keep-ready's benefit, which is the conservative direction for a
build/do-not-build decision). `built_tokens` for the `_unbuilt_rebuild_s` arithmetic is taken from
the last touch's engine `prompt_tokens` because the roster is not in the committed logs; it is
marked CONSTRUCTED wherever used.

7. **Validate the control, not only the result.** Two positive controls, both reported above and
both passing: the committed score block of each cell reproduces the committed verdict's pool
counts exactly (so the cell choice is audited, not assumed), and the read-only trace regeneration
reproduces two independently OBSERVED `tokens_charged` figures from a DIFFERENT arm
(`always-cloud-fcfs_n16_s7`: 38,821 and 48,811) plus the committed `max_history_tokens` of 52,861
and the committed 18-id set. An impossible success would have been as diagnostic as a failure: if
the trace had reproduced those to the token while disagreeing with the committed id set, the read
would have been wrong, not the cells.

## Registers

- **OBSERVED COUNT, not a constructed bound:** the 23 misses, the 3 and 18 decline counts, the
  bucket table, the 18 over-limit ids, every `history_tokens`, every belief tier, every engine
  `prompt_tokens` / `cached_tokens` / stamp.
- **CONSTRUCTED:** the 80-token warm `uncached` figure, every D162 prediction, the 21.5 and
  44.9 tokens/s rates, the `_unbuilt_rebuild_s` arithmetic, the reconstructed queued-ahead term.
- **ONE TRACED UNIT, not a full table:** the `robo001|s001` residency narrative is one session over
  one 540 s stretch; it is not claimed to generalise to the other six robots.
- **A FULL TABLE:** the bucket counts and the warm-counterfactual split are a census of all 23
  misses on these two devices, and nothing else.
