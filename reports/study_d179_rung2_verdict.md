# D179 (6) rung-2 verdict: the scorer, written before the cells

Study row: `StudyD179-SHARES` in `research/EXPERIMENTS.md` (IN PROGRESS).
Script: `experiments/orchestration/live2/d179_rung2_verdict.py`.
Registered result: `results/orchestration/live2/frozen_test/d179_rung2_verdict_prereg.json`.

**This report contains no shares result.** The four `covex-v6-state-shares` cells (16 devices,
seeds 4 to 7, tag `_L3_epg_rq30`) were running on the H100 when it was written. The scorer, the
definitions, the comparator pins and the positive control were all fixed first, deliberately:
writing the computation before the data exists is the only way the computation cannot be shaped by
the result. Section 7 is the verdict and it is empty until the script is run on the landed cells.

---

## 1. The three pre-registered checks

From the header of `results/orchestration/live2/frozen_test/runs/V6SHARES_CELLS`, which is the
pre-registration:

1. alert per-episode target attainment AT LEAST THE BASE'S
2. at least 90 percent of the committed rung-2 robot on-time GAIN OVER BASE retained
3. assistance within 2 s AT LEAST 90 percent

All three are reported **PER SEED** and never as a single pooled verdict. The pooled figure is
computed and sits beside the per-seed table under a name that says it is pooled. A pooled figure
can hide a per-seed failure, which is consistency check 3's "a real effect averaged into
undetectability".

---

## 2. The comparators, pinned by content before any shares cell landed

| role | arm | seeds | status in EXPERIMENTS.md |
|---|---|---|---|
| base | `hybrid-F-lhreq-noc3` (equivalently `covex-v6-base`) | 4, 5, 6, 7 | no INVALID mark |
| committed rung 2 | `covex-v6-state-uo` (the PLAIN arm) | 4, 5, 6, 7 | no INVALID mark |

Pinned at `origin/main` = `e9bb556d490a887cd9f4e7d8245b82be3bcef8d4`, and pinned again by
**git blob sha per file**, which is content-addressed and cannot move when the branch does. All 48
blob shas (8 cells x 6 files) are in the registered JSON under `pinned_comparators`, and the
files the positive control actually read were verified identical to those blobs, 48 of 48.

`origin/main` moved while this was being built, so the commit that registers this work has parent
`6eb1e34a03800d681ee64a85abdd2f193e9e9cca`, one commit later than the label above. All 48 pinned
blobs are unchanged at that commit, verified file by file, so the comparator CONTENT is the same
object under both. The discrepancy is recorded in the registered JSON under
`pin_commit_reconciliation` rather than quietly corrected: a sha in the wrong register is not a
wrong computation and would survive every arithmetic check.

The base identity is read, not assumed: `d181_share_floors.json`'s `source` field states
"hybrid-F-lhreq-noc3 (covex-v6-base) seeds 4 to 7", and only a single off-grid
`covex-v6-base_n16_s5_..._lpt2048` directory carries the `covex-v6-base` name on origin.

Excluded **by name**, so no reader has to infer it:

- `covex-v6-state-uo-c5attr` seeds 4 to 7, the C5-ATTR variant, which is not the committed rung 2.
- `covex-v6-state` seeds 4 and 5 (budget-mispriced) and 6 and 7 (held-code), per the
  `V6STATE_CELLS` header. Seed 5 of this arm is read once, for the committed episode numbers it
  published, and is a comparator for nothing.
- `covex-v6-base_n16_s5_..._lpt2048`.

Fields read: the committed `cell.json` -> `score.score.sweep[0]` block for `robot_pool_*`,
`ss_pool_*` and `dashcam_per_device[*]`; `outcomes.jsonl.gz` and `request.jsonl.gz` for the
independent recomputation; `coordinator_result.json` (`counts`, `arm_stats`) and
`decision.jsonl.gz` for the diagnostics.

### The committed comparator numbers, read not remembered

| seed | base robot | rung2 robot | gain | base asst | rung2 asst | base alert att. | rung2 alert att. |
|---|---|---|---|---|---|---|---|
| 4 | 35/132 = 0.2652 | 118/132 = 0.8939 | +0.6288 | 337/357 = 0.9440 | 344/357 = 0.9636 | 0.4425 | 0.1633 |
| 5 | 27/127 = 0.2126 | 115/127 = 0.9055 | +0.6929 | 343/356 = 0.9635 | 350/356 = 0.9831 | 0.3962 | 0.1750 |
| 6 | 41/121 = 0.3388 | 107/121 = 0.8843 | +0.5455 | 349/357 = 0.9776 | 342/357 = 0.9580 | 0.4655 | 0.2402 |
| 7 | 19/105 = 0.1810 | 83/105 = 0.7905 | +0.6095 | 354/359 = 0.9861 | 355/359 = 0.9889 | 0.5538 | 0.2168 |

"alert att." is the mean per-episode attainment at the flat-19 denominator under the committed
delivery rule. The robot pool is equal across arms at every seed (132, 127, 121, 105), as it must
be, because it is trace-determined; an inequality is a STOP in the scorer, not a rescaling.

The shape of the problem is in that table: the committed rung 2 bought +0.55 to +0.69 of robot
on-time and paid for it with roughly 0.28 of alert attainment. Check 1 asks shares to give the
alert side back and check 2 asks it to keep the robot side. Neither comparator passes both, which
is why neither is a trivial bar.

---

## 3. The definitions, with their justifications

Full text in the registered JSON under `definitions`. The load-bearing ones:

**On time, PRIMARY.** `t_delivered - t_opportunity <= deadline + 1e-9`, the committed scorer's
`score._within`, with both committed passes of `score.load` applied first: D144 (2) / D175 (1)
nulls a refused request's delivery (non-200 `http_status`, or no status with neither
`prompt_tokens` nor `output_tokens`), and D146 `DELIVERY="completion"` re-bases `t_delivered` onto
the request's `t_done` for `kind == "recall"` only, a monitor staying at first token plus the
forward hop. These two passes are **transcribed** into the scorer rather than imported, because
`score.load` needs the trace tree and this box holds only run directories. The transcription is
what the positive control exists to prove.

**On time, SECONDARY, reported beside and never mixed in.** `cloud_payload.on_time`, the
coordinator's own online flag, which is a FIRST-TOKEN reading. It is kept because the D178 deficit
feed reads exactly this field, so both the online mechanism's view and the offline score's view
are on the page. On `covex-v6-state-uo` seed 4 the two differ by 140 monitor instants, 2,209
against 2,349, which is `dashcam_ontime_reconcile.json`'s `late_at_forward_only` bucket exactly.
Every check is reported under both rules and a disagreement between the two verdicts is flagged.

**Cloud on-time answers only (D177).** `device_on_time` is never added to any numerator.

**Query type by DEVICE-ID PREFIX** (`dash` -> alert, `robo` -> recall, `asst` -> assistance),
which is `share_admission.type_of_device`. Not by request kind: `arms_v6fair.py:129` merges
assistance into recall by kind, and on every committed cell an `asst00x` completion arrives as
kind `recall` with `deadline_s` 2.0, so a kind-based split double-counts recall. The scorer
asserts the `(prefix, kind, deadline_s)` cross-tab is exactly
`{(dash, monitor, 1.0), (robo, recall, 3.0), (asst, recall, 2.0)}` on every cell.

**Alert per-episode attainment.** Episode key
`(play_id, int(round((t_local - 3.0) / 0.5)) // 21)`, which is the recipe
`d178_deficit_feed_proofs.json` -> `f_replay_committed_live_cell` -> `independent._how` uses. It is
chosen over the EP-G prompt-token law because it is readable from the outcome row alone and so
sees episodes the policy never served, which the token law cannot. 21 is `trace.EPG_CAP_FRAMES`;
`trace.EPG_MIN_FRAMES = 3` is why positions 0 and 1 are not decision instants.

The per-episode denominator is **19, a declared constant** (D178 (1)): positions 2 to 20 inclusive.
Verified on the committed cell at 714 episodes, instants per episode min 2 / median 19 / max 19,
the short ones being a play that ended mid-episode. The constant's bias is measured, not assumed:
on `covex-v6-state` seed 5 the true per-episode denominators give an alert shortfall of 0.1427 and
the flat 19 over the same episodes gives 0.1467, so the constant costs +0.0040 and both readings
are reported.

**Mean per-episode and pooled are both reported, and only the per-episode one answers check 1.**
On that same cell the per-episode alert shortfall is 0.1427 and the pooled shortfall over all
11,769 instants is 0.0411: a factor of 3.5, because 486 of 714 episodes are below target while the
type as a whole is only just below it.

**Attainment and shortfall are different numbers** and are reported separately, because each is
easy to quote for the other: `attainment_e = on_time_e / 19`,
`shortfall_e = max(0, 0.25 - attainment_e)`, and the mean of the clipped shortfall is NOT 0.25
minus the mean attainment. The 0.1427 and 0.0411 above are SHORTFALLS. The alert target is 0.25
per episode (D178 (1); also the committed scorer's `p_dash`).

**Robot on-time gain retained.** `gain = rung2 - base`, `retained = (shares - base) / gain`, over
each cell's own robot pool, which is every `robo00x` opportunity in the cell. Not the feasible
subset and not a distinct-question count: a D159 (C) re-ask is its own opportunity with its own
3.0 s deadline and counts again.

**No seed is ever silently dropped on a near-zero or negative denominator**, and a ratio there
means nothing, so each seed carries a `gain_class`:

| gain | class | what is scored |
|---|---|---|
| `>= +0.01` | NORMAL | the ratio, bar 0.90 |
| `\|gain\| < 0.01` | NO_GAIN_TO_RETAIN | the ratio is null, the check is VACUOUS for that seed and says so, and the absolute fallback applies |
| `<= -0.01` | NEGATIVE_GAIN | the ratio is reported but marked UNINTERPRETABLE, because its sign inverts and a "retention" above 0.9 would then mean shares is worse; the absolute fallback applies |

Absolute fallback: the shares on-time fraction must not fall more than 0.01 below the base's. On
the committed comparators every seed is NORMAL (+0.63, +0.69, +0.55, +0.61), so the guard does not
fire there; it exists because a shares cell can change which seeds have gain.

**Assistance within 2 s.** Deadline 2.0 s, which is both the type's deadline in every committed
cell and the committed scorer's `L_ss`; for assistance "within 2 s" and "on time" are the same
test. The denominator is **per device**, because D178 (1) sets the assistance unit to the device
("90 % of the device's questions within 2 s"), so the primary verdict is that every `asst00x`
device is at or above 0.90. The pooled fraction and the per-device minimum are reported beside it,
because a pooled 0.93 can sit on top of a device at 0.80.

The denominator is **offered, not delivered**: the count of assistance opportunities in the cell
(`ss_pool_n` = 357 on seed 4, against the 1,429 `d181_share_floors.json` records over the four
base cells). A denominator of completions reads 100 percent for a device whose questions are all
being declined, which is the exact case these checks exist to catch, and a share-admission arm is
the arm most able to produce it.

### What could not be pinned down, and what was assumed

Four things. Each is recorded in the registered JSON under `definitions_not_pinnable`, each is
reported both ways, and none is resolved by this report alone.

1. **Which delivery rule D179 (6) intended.** The pre-registration says "attainment" without
   naming a rule, and two committed rules exist. ASSUMED: the committed scorer's `t_delivered`
   rule is primary, because it is the rule every committed cell's dashcam on-time count uses and
   the one the positive control reproduces exactly. The first-token flag is reported beside.
2. **Whether check 3 is per device or pooled.** ASSUMED per device, from D178 (1)'s unit. Both
   reported.
3. **Whether check 1's "attainment" is the mean or the fraction of episodes at or above 0.25.**
   ASSUMED the mean, because "at least the base's" reads as a comparison of levels. The at-target
   fraction is reported beside it, and on the comparators the two readings are far apart (base
   0.4425 mean against 0.6053 at-target on seed 4), so they can disagree about a verdict.
4. **Hold time.** The coordinator logs one `share_hold` row per DISTINCT held instant, not one per
   100 ms period (`coordinator.py:1498-1506`), so a duration is not in the log. ASSUMED:
   `hold_s = t_submit (request log, same opportunity id) - t (hold row)`. A held instant never
   submitted is right-censored, counted under `never_submitted`, never dropped and never scored as
   a zero-length hold. The two BACKGROUND release sites key on `touch:<session>` /
   `build:<session>`, have no request join, and are counted separately rather than forced into a
   type's distribution. This is a diagnostic and bears on no pre-registered check.

---

## 4. The positive control: PASS, 8 of 8 cells, 48 of 48 counts exact

Consistency check 7. The scorer re-derives six committed counts per cell from
`outcomes.jsonl.gz` plus `request.jsonl.gz` and must match that cell's own `score.sweep[0]`
block EXACTLY, tolerance 0 counts:

`robot_pool_on_time`, `robot_pool_n`, `ss_pool_on_time`, `ss_pool_n`, dashcam `on_time` sum,
dashcam `n_instants` sum.

All 48 agree on all eight committed comparator cells. The script **refuses to score any
comparison** if this fails, and says that the scorer is broken and the cell is not. A broken
scorer passes every check applied to the treatment, because the treatment is fine, so the control
is read first.

Both sides of the comparison are audited, not just the treatment: the base and the committed
rung 2 are each re-derived from their own raw logs against their own committed numbers.
Arm-versus-arm checking cannot see a broken side of a comparison.

### Cross-check against committed measurements (consistency check 1)

| quantity | this run | prior | source of prior | ratio | agree |
|---|---|---|---|---|---|
| uo s4 dashcam on-time | 2209 | 2209 | `dashcam_ontime_reconcile.json` `buckets.on_time` | 1.0 | yes |
| uo s4 dashcam first-token reading | 2349 | 2349 | same, `d146_both_readings` | 1.0 | yes |
| state s5 alert per-episode shortfall, true denom | 0.1427 | 0.1427 | `d178_deficit_feed_proofs.json` `f_replay.independent.alert` | 1.0 | yes |
| state s5 alert per-episode shortfall, flat 19 | 0.1467 | 0.1467 | same, `alert_flat19_on_true_episodes` | 1.0 | yes |
| state s5 alert POOLED shortfall | 0.0411 | 0.0411 | same, `alert_pooled_shortfall` | 1.0 | yes |
| state s5 alert episodes detected | 714 | 714 | same, `episodes_independent` | 1.0 | yes |
| state s5 instants per episode min / med / max | 2 / 19 / 19 | 2 / 19 / 19 | `deficit_feed.py` denominator verification | 1.0 | yes |

No disagreement anywhere, so nothing exceeds the 2x bar.

---

## 5. End-to-end proof on committed cells

The comparison path cannot be exercised by a cell that does not exist, so it was exercised at its
two degenerate endpoints, where the answer is known in advance. A check returning the same verdict
at both endpoints would be a check that discriminates nothing, and the required positive control
alone would not catch that: an impossible success is as diagnostic as an impossible failure.

| stand-in shares arm | expected | observed |
|---|---|---|
| `covex-v6-state-uo` (shares := the committed rung 2) | retention exactly 1.0, check 2 passes | retained 1.0 on all four seeds, check 2 passes, check 1 FAILS on all four |
| `hybrid-F-lhreq-noc3` (shares := the base itself) | retention exactly 0.0, check 2 fails | retained 0.0 on all four seeds, check 2 fails, check 1 passes trivially on all four |

The checks discriminate and the two endpoints disagree in both directions, which is the point of
running both. Check 1 failing when shares is the committed rung 2 is not a surprise: it is the
alert loss shares exists to recover.

### 5b. One plumbing fault, found by the first landed cell before any verdict was read

Seed 4 of the shares arm landed while this was being written and the scorer was run on it once,
as a parse check and not as a verdict (three of four seeds were still missing). It found a fault
in this script, which was fixed:

The held instant travels in a decision row's `opportunity_ids`, **not** in a `key` field.
`_log_decision` takes `key` as a keyword but passes it only to the prediction lookup and never
into the `DecisionRecord` (`coordinator.py:1970-1991`), so `rec["key"]` does not exist. The
hold-time block read `key` and resolved **0 of 1,266** hold rows, so every per-type hold
distribution came out empty while every other number in the output looked right. That is the
write-only-field shape from the other side: a field that is READ and never written. After the fix,
1,252 deadline-type holds resolve, 14 background holds are counted separately, 0 rows are
unresolved, and no hold is negative.

This is why a parse check on one real cell is worth its minute. The fault produced no error, no
zero where a reader expects a number, and no effect at all on the three pre-registered checks: it
would have shown up as three empty hold distributions in a report whose verdict section was full.

---

## 6. What the scorer outputs per seed

Pre-registered checks, each with its verdict under BOTH delivery rules:

- **check 1**: mean per-episode alert attainment for base, committed rung 2 and shares; the
  delta shares minus base; the pass flag; the fraction of episodes at or above 0.25 beside it;
  the pooled attainment beside that; the true-denominator reading beside that; episode count and
  instants-per-episode min / median / max as a shape check.
- **check 2**: robot pool n for all three arms and whether they are equal (unequal is a STOP);
  on-time counts and fractions; `gain`; `delta`; `gain_class`; `retained_fraction`; the absolute
  fallback and which basis was used; the pass flag.
- **check 3**: per-device assistance fractions for all three arms; the per-device minimum;
  whether all devices clear 0.90; the pooled fraction and its own pass flag beside.

Diagnostics on the shares cell, which the user asked the H100 for and which are recomputed here so
the cross-check is independent of the H100's own reading:

- hold time p50, p90, min, max per type, with `never_submitted` right-censored holds counted
  separately, background holds counted separately, and a `negative_holds_FLAG`;
- `release_infeasible` per type with the in-cell `submitted_*` denominators beside it;
- planner abandonment: `decisions`, `abandoned_to_base`, fraction recomputed and as recorded, by
  decision kind, and a flag above 1 percent on any kind or overall;
- share admits, denies, hold instants and hold periods per type, every `share_reason_*`, and the
  **port rule**: an arm must make its characteristic decision at least once, so a shares cell
  whose gate never denies is flagged as having made no share decision whatever its proofs say;
- **the signature check**: any period where W exceeded `W_max` with no recall present. In the dry
  cell recall was present in all 18,476 overruns with no exception, because only the oversize
  exemption can push W past `W_max`, so an overrun without recall is new, no existing proof covers
  it, and it is flagged loudly on both the time basis and the per-gate-call basis.

**Register note on W, and it is why no bar is set on these numbers.** Live W is submit to FIRST
TOKEN; dry W is submit to SETTLE, because `on_first` is wired only when a real backend exists
(`procsplit.py:430-433`). The dry report's 13.43 percent of virtual time above `W_max` and its
3.56x high water are SETTLE-basis quantities, they size nothing, and no live figure here is
compared against them.

---

## 7. VERDICT: PENDING

Empty by design. The four `covex-v6-state-shares` cells had not landed when this was written.

To fill it, from the repo root with the landed cells in `<runs>`:

```
conda run -n fmtk python experiments/orchestration/live2/d179_rung2_verdict.py \
  --runs <runs dir> \
  --out results/orchestration/live2/frozen_test/d179_rung2_verdict.json \
  --report reports/study_d179_rung2_verdict_result.md \
  --pins results/orchestration/live2/frozen_test/d179_rung2_verdict_prereg.json
```

Read the positive control line first. If it is not `PASS (8/8 cells exact)` the scorer is broken
and the comparison must not be read.

If any of the three checks fails on any seed, the pre-registration's own consequence applies:
rung 2 adopts `c5attr` as a logged override of the D181 rule (user addendum 9 item A) and no
further C5 variants are built. Shares is judged on its own checks first, per seed.

Rule 2 applies to any null. A shares cell whose `share_deny_*` counters are all zero, or whose
gate made no decision, is an **ABSENT LINK** and not a negative, and the port-rule block in the
output is what says which.
