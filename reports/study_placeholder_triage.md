# StudyPLACEHOLDER-TRIAGE: the 26 unruled D201 placeholder consumers, ranked for one pass of rulings

**D206 follow-up. READ-ONLY: no code written, no cell run, no file in another session's scope touched.**
Data: `results/orchestration/live2/placeholder_triage/d206_placeholder_triage.json`.

Source: `results/orchestration/live2/d201_score_channels/AUDIT_placeholder_consumers.md` (28 CONFIRMED
hits, written against `78a96ce9`), with `reports/study_score_consumers.md` as the D205 report.

## Register and reading conventions

Every claim below is marked **OBSERVED** (read in the code at the pinned sha, or counted by a grep
census over it) or **CONSTRUCTED** (reasoned from types, naming or a committed report). Each hit's
entry in the JSON carries its own register.

**All line numbers are at `origin/main` = `e022bf1a03a3f0c3a47fd0b4f64db77cdce813ac`**, not at the
audit's `78a96ce9` and not in the working tree. This matters more than it sounds: the local HEAD
`17bdf159` is **not an ancestor of origin/main**, and its `live2/` tree is stale to the point that
`live2/hybrid/` does not exist on disk at all. Anyone rechecking a line number must use `git show`
against the sha above. The audit's own line numbers have drifted by up to 340 lines in `cstate.py`.
That sha is code-identical to this commit's parent `6749ef89` under `experiments/orchestration/`
(`git diff --stat` between the two is empty there), so every line number holds at both.

## The headline is not a hit, it is a structural fact about the ladder

**S1 (OBSERVED). The reported covex-v6 ladder never enters `policy/` or `arms_policy.py`.**
`git grep 'from policy'` over `live2/v5/`, `arms_v6cf.py`, `arms_v6state.py`, `arms_v6c5.py` and
`arms_v6fair.py` returns nothing. The one route from the hybrid/v6 family into the policy library is
C6 (`hybrid_arm.py:320-325`, `A.make_arm('policy-core')`), and C6 is False in `CONFIGS['hybrid-F']`
(`hybrid_arm.py:809-810`), which `covex-v6-base = hybrid-F-lhreq-noc3` inherits. The other caller is
`arms_covex_v2.py:129`, and covex-v2 is not in the reported set.

Five audit hits live in that tree: **10, 12, 13, 21 and 23, including the 8x bandwidth error**. None
of them can reach an arm in the reported set. They reach `policy-core` (recorded superseded at
`results/INDEX.md:928`), `covex-v2`, `covex-v13` and the `hybrid-F6` family.

**This is the one judgment here that could reorder the whole list, and it rests on an import census
rather than a decision-log diff.** If any committed `policy-core` or `covex-v2` cell is still cited
in the paper, hit 23 goes straight to the top.

**S2 (OBSERVED). `live/adapter.py` is not a dead v1 harness; it is live inside live2.**
`live2/backend.py:29,50` does `from adapter import HttpBackend` / `class Live2Backend(HttpBackend)`,
and `coordinator.py:489` calls `self.be.metrics()`, which is `adapter.py:137-144`. That is why hit 6
is ranked first rather than dismissed.

**S3 (OBSERVED). Three of the 28 are already ruled, not two.** Hit 11 (`DeficitCounters.weight()`
returning exactly 1.0) was ruled by **D203 (1) Option D and D206 (3)**. So **25 are unruled**, not 26.

**S4 (OBSERVED). One audit entry is partly stale and would have been reported as open.** Hit 17's
episodic image signals are no longer hard-coded: `inarvl_adapted.py:65-88` now reads
`s.current_episode_device_scores('inar-vl')` under D201 and D205 (2). The six text signals, the
recall path's four image signals and `energy_j = 0.0` remain. Nothing in the 28 is outright false.

## The three hits singled out: two confirmed, one confirmed with a correction

**Hit 23, `arms_policy.py:790`, the 8x bandwidth double-division: CONFIRMED, and it is live, and it
reaches no reported arm.** `cstate.py:628` builds `uplink_bps = d.uplink_mbps * 1e6 / 8.0`, so the
field named `_bps` already holds **bytes** per second; `arms_policy.py:790` then does
`Link(bandwidth_bytes_s=max(uplink_bps / 8.0, 1.0))`, giving 212,500 B/s against the true 1,700,000.
`policy/state.py:29` divides the payload by it, so every predicted upload is 8x too long. Three
independent witnesses fix the intended convention: `baselines/costs.py:35` `UPLINK_BPS = 13.6e6 / 8.0`;
`policy/run_pol2.py:34` and `policy/tests/_fixtures.py:27` pass `pf.uplink_bytes_per_s()` into the same
field with **no** division; `policy/tests/test_v11_fixes.py:135` uses `bandwidth_bytes_s=1.7e6`.
`arms_policy.py:790` is the only site in the tree that divides twice. Beside it, `:639` hard-codes
`self._device(did, 13.6e6 / 8.0, 0.044)` for a device discovered through a recall query, replacing the
observation's own `NetworkState` with literals and taking the same second division. Whose arms read
it: `policy-core`, `covex-v2`, `covex-v13`, `hybrid-F6*`. **None in the reported set (S1).** It is an
implementation bug with no ambiguity about the units, and the ruling owed is narrow.

**Hit 19, `e36e_fleet.py:853`, a Step-4 negative control defined and never called: CONFIRMED, and it
needs saying plainly.** Grep census at the pinned sha: `orig_maint` occurs exactly once (the
assignment at `:851`), `_zero_maint` exactly once (the `def` at `:853`). Neither is ever used.
`_negative_control_check` (`:798`) prints an analytic argument and the literal string
`"Rules converge. Negative control PASS"`, computes nothing, and returns `True` at `:872`. The gate at
`:909-913` stops the 8,064-condition sweep only if that `ok` is False, **so check (ii) can never fail
and the gate can only ever fail on check (i)**. The code documents its own evasion at `:856-861`:
*"Since we can't easily monkey-patch, simulate manually ... Instead, just report conceptually"*.

The mechanism this control was written to detect is the same mechanism that was absent from E36, E36b
and E36c. CLAUDE.md's Step 4 exists because of that family, and in the family's own successor script
the Step-4 control does not run. An analytic argument is not a control: it cannot catch the case where
the code does something the argument does not model, which is exactly how that null arose. E36f, E36g
and E36h take all their constants from E36e per `EXPERIMENTS.md`. The honest options are to make the
control compute, or to note on the E36e row that its negative control was never executed.

**Hit 4, `hybrid/value_reader.py:115`, `send=False` for every input: CONFIRMED with one correction,
and it is dead for the reported set.** The correction matters for the record: `choose` does not return
`send=False` for every possible input. It returns `send=False` for every input **it is given**, because
the only production caller, `hybrid_arm.py:455`, passes exactly one candidate, `("RECENT",)`, with
neither `forbid_recent_for_lh` nor `is_long_horizon` overridden and both defaulting True. `reps`
empties at `:117`, `best` is None at `:124`, `send` is False at `:125`, and `stats["c3_value_sent"]`
can never increment. **No reported arm reads it:** `git grep c3_value_reader` shows it True only in the
six `hybrid-Fv` configs, no covex-v6 config sets it, `covex-v6-base` is `hybrid-F-lhreq-noc3` with C3
itself off, and **D177 (2) removed the value reader from the ladder outright**. It needs no ruling.
One live artefact remains: `hybrid_arm.py:221-223` still asserts at the point of use that flattening or
inverting the table *"MUST change decisions"*, while `v5/value_readers.py:19-26` records that all three
tables give the same digest and classifies the control as UNEXERCISED. The stale comment should go.

## The ranked list

Ranked by (live path) x (reaches a reported arm) x (placeholder at an extreme of its range).
Tier A has all three. Tier B is live and reported but the placeholder is an **absent** channel rather
than an extreme value, which is a different problem and is marked as such. Tier C is live but on an
arm outside the reported set. Tier D needs no ruling.

| # | hit | file:line | placeholder | live path | reported arm | where in the range | kind |
|---|---|---|---|---|---|---|---|
| 1 | 6 | `live/adapter.py:137-144`, used `:230,233` | `except Exception: return {}` then `.get(...,0.0)` | LIVE constant; read at `cstate.py:663` -> gates at `arms_v6cf.py:306`, `engine_actions.py:288` | **YES, all** | **MIN** (0.0 = KV empty = most permissive) | impl |
| 2 | 22 | `live2/touch_policy.py:108` | `TOUCH_PRICE_MODE` never assigned | LIVE; `:129` -> `:146` -> `coordinator.py:1161` -> budget refusal | **YES, rungs 2-4** | **ABOVE the range**, 3.6x to 9.8x, wrong shape | **method** |
| 3 | 3 | `baselines/ekya_adapted.py:89` | `+ 0.0 * self._recall_gain(...)` | LIVE; the thief loop's objective | **YES, ekya** | **MIN** of a [0,1] weight | **method** |
| 4 | 26 | `live2/engine_actions.py:399-401` | guessed engine key names | LIVE; `coordinator.py:1798` gates the `host` belief | **YES, rungs 2+** | **MAX cost**: belief falls to COLD | impl / method |
| 5 | 9 | `pensieve:47,54`, `kvflow:81,94`, `lmcache:60`, `rh8:57` | literal `11000` token default | LIVE; selects the recompute rate and the charge | **YES, 4 baselines** | **MIN** of the committed domain (11k vs 28k) | impl |
| 6 | 8 | `attentionstore_adapted.py:46,48` | `Session(sid, 0, HBM, last_access_s=0.0)` | LIVE; 1-token build at `:62`, LRU tie-break in `reconstructed/attentionstore.py:106` | **YES** | **MIN** at both sites | impl |
| 7 | 16 | `thinking_qwenvl:73` + 4 producers | `rho` constant; `RICH` in no inventory | LIVE; dead RICH branch in `ecollm:136-142` | **YES** via eco-llm, streamscout, inar-vl | MIDDLE value, **extreme in effect** (both thresholds 0.6) | **method** |
| 8 | 17 | `inarvl_adapted.py:92-94,110,113,62` | 7 of 10 fuse inputs are literals | LIVE; `fuse` -> `route` -> placement | **YES, and being rerun now** | **MIN** for the 7 zeros | **method** |
| 9 | 14 | `live2/arms.py:82` | `self._caps`, write-only | **NONE. ABSENT** (Step 2 sense) | **YES, all four D189 edge arms** | n/a, no read | impl |
| 10 | 7 | `simplestream_adapted.py:45,47-48` | `window_steps`, write-only | **NONE. ABSENT** | **YES, a D189 edge arm** | n/a, no read | impl |
| 11 | 23 | `live2/arms_policy.py:790` | `/ 8.0` on a bytes/s field | LIVE; `policy/state.py:29` | **NO** (S1) | EXTREME, 8x pessimistic | impl |
| 12 | 10 | `arms_policy.py:792`; `policy/demand.py:40,49` | frozen DEV prior, EWMA never called | LIVE -> `rollout.py:710` | **NO** (S1) | MIDDLE | impl |
| 13 | 12 | `policy/state.py:145,153` | `Device.z`, five readers, no writer | LIVE -> `closed_form`, `rollout` | **NO** (S1) | **MIN** | impl, self-documented |
| 14 | 13 | `policy/state.py:41` | `staleness_s = 0.0`, flag default off | LIVE; `CATCH_UP` never offered | **NO** (S1) | **MIN** | impl, self-documented |
| 15 | 21 | `policy/coordinator.py:704` | surviving `competing_s=0.0` | LIVE; PRIORITY unreachable on the restore path | **NO** (S1) | **MIN** | impl + a test-coverage defect |
| 16 | 4 | `live2/hybrid/value_reader.py:101-117` | `send=False` at the one call site | dead in effect | **NO**, D177 (2) | boolean extreme | no ruling |
| 17 | 19 | `e36e_fleet.py:851,853` | control defined, never called | LIVE gate that cannot fail | **NO** | **MAX**, unconditional PASS | no ruling, but say it |
| 18 | 20 | `e36b:180-188`, `e36c:164-167` | `refresh_ms` returns 0.0 | LIVE constant | **NO** | **MIN** | no ruling (NOT PERFORMED) |
| 19 | 11 | `v5/cf_objective.py:249-280` | `weight()` returns 1.0 | LIVE constant | YES | identity | **ALREADY RULED** D203/D206 |
| 20 | 5 | `live2/cstate.py:278` | `metrics` empty in dry cells | dry cells only | dry only | **MIN** in the dry regime | no ruling; notes owed |
| 21 | 27 | `live2/coordinator.py:1689-1690` | literal frame_count 1, literal `"COLD"` | dry cells only | dry only | **MAX cost** for recall | no ruling; notes owed |
| 22 | 24 | `sim/run.py:253-255` | `recall=0.0` literal | sim only | **NO** | **MIN** | impl, low |
| 23 | 25 | `sim/run.py:250` | `recall=0` misattributed | sim only | **NO** | **MIN**, wrong both ways | impl, low |
| 24 | 15 | `baselines/smoke/replay.py:102` | `device_answer_confidence=None` | smoke harness only | smoke only | **OUTSIDE** the range | impl |
| 25 | 18 | `baselines/constructed.py:101-108` | branch probability pinned at 1 | LIVE constant | **NO**, B4 superseded | n/a | no ruling |
| 26 | 28 | `baselines/profiles.py:94` | `_CAD` defined nowhere | LIVE, harmless by coincidence | in form only | NEUTRAL (equals `CADENCES_S`) | impl, lowest |

### Counts

- 28 audit hits. **3 already ruled** (1, 2, 11). **25 unruled.**
- **10 are live and reach a reported arm**: hits 6, 22, 3, 26, 9, 8, 16, 17, and hits 14 and 7 as
  **absent channels on reported arms** rather than wrong live values.
- **4 are methodological** and need a user ruling, not a fix: hits **22, 3, 16, 17**.
- 11 need no ruling at all: 4, 11, 18, 19, 20, 5, 27, and hits 1 and 2 already ruled, with 24, 25 and
  28 as optional low-priority cleanups.
- **0 false entries. 1 partly stale entry** (hit 17, already half-fixed by the D205 work).

### Absent versus a live constant, which is the distinction that matters here

Two of the top ten are **ABSENT** in CLAUDE.md Step 2's sense: written, never read. Hit 14
(`arms.py:82 _caps`) and hit 7 (`simplestream window_steps`). No decision reads a wrong number; a
capability is configured and does not exist. The practical difference is the remedy and the reading:
fixing either moves **no committed number**, because nothing reads them. What they change is what a
result can mean. `_caps` is how all four D189 edge arms would learn the GPU-KV pool size, and D189
condition (1) is a 0.25x / 0.5x / 1x capacity sweep with seeds 4 and 5 running now; **an arm that
cannot observe the capacity gives a flat response across capacity levels that is UNEXERCISED under
Rule 2, not a finding about the arm.** `window_steps` is the fitted parameter that
`arms_published.py:233-236` cites as the reason SimpleStream ports at all, and it is not applied.

Everything else in the top ten is a **live constant**: a real read, of a real value, that is wrong.

### Blast radius: what a fix would invalidate

- **Hit 22** is the one that would invalidate a committed comparison the way `delivered_scores` did.
  It moves every rung-2-and-above decision digest, including the rung-3 digest `12e4f73ce0ebd865`
  that `-rr` s5 to s7 are judged against. Its place is the **final ladder rerun (D190 (6))**, beside
  the `id(obs)` fix and `-rr` joining rung 3 and the rung-3 `deficit_feed` read that D206 (2) already
  deferred there.
- **Hit 6**'s blast radius is **unknown by construction, and that is the finding**. Nothing counts the
  swallowed exceptions, so no committed live cell can be cleared or condemned from the record as it
  stands. The first step is not a fix but a counter.
- **Hit 26** needs one probe of a real usage block, not a sweep. If a key matches on the live engine,
  every committed rung-2+ tier belief is wrong in the expensive direction and RELOAD was UNEXERCISED.
- **Hits 3, 8, 9** move only their own baselines' cells and leaderboard rows.
- **Hit 17** lands inside the inar-vl rerun D205 (1) already ordered. Fixing it there costs nothing
  extra; fixing it afterwards costs that rerun twice.
- **Hits 11, 12, 13, 21, 23, 10** move no reported comparison.

### Alternative explanations, stated rather than assumed

Each hit's JSON entry carries one. The three that would most change a ruling: hit 6 may never have
fired in any committed cell and nothing distinguishes that from a silent substitution; hit 3's
starvation has nothing to starve if the background pool is empty in the committed traces, which a
per-cell count settles; hit 26's "host never" may simply be true for this engine configuration, which
only a probe can tell from a wrong key name.

### Proxies declared

- The 0-of-15,914 host-belief census for hit 26 is taken from `reports/study_engine_actions.md:124-126`
  (committed) and was **not** re-run here. CONSTRUCTED.
- "Reaches a reported arm" is an **import-and-config census**, not a decision-log diff. It is the right
  proxy for a dead import and a weaker one for a live but rarely-taken path. For hit 23, the load-bearing
  case, the census is three independent facts (no `policy` import in `v5/` or `arms_v6*`; C6 False in
  `hybrid-F`; covex-v6-base is the `-noc3` config), which is why I state it as OBSERVED. It is still a
  census, and a decision-log diff of one rung-2 cell would settle it outright for one cell's cost.
- `reads_device_answer`, `OUT_OF_CARD_SCOPE` and the D130 / D205 exclusion lists are taken from the
  code and the design log as written; I did not re-derive which arms the paper will finally print.

### What I did not do

No fix, no cell, no proof script, no judgment escalated into a decision. Hit 23's ruling, hit 19's
record, and the four methodological hits (22, 3, 16, 17) are the user's. Where a hit is genuinely
ambiguous I said so rather than resolving it: hit 5 and hit 27 may be nothing at all, and hit 26 cannot
be settled from the code in either direction.
