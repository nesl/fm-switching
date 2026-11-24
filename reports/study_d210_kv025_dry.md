# StudyD210-KV025: the 0.25x dry report for rung 4, and a capacity-blindness finding in our own arms

Session D, flash, 2026-11-23. Under D209 (3), D209 (4) and D210.

Deliverables directory: `results/orchestration/live2/d210_rung4_kv025/`.
Scripts: `experiments/orchestration/live2/d210_kv025_one_cell.py`,
`d210_kv025_driver.py`, `d210_inheritance_counters.py`, `d210_kv025_report.py`, and the
parameterised `d200_gatea_safety.py`.

---

## 0. Register, stated before any number

Every number produced by this study is one of three things, and the report says which at the
point of use.

| register | what it means here |
|---|---|
| **DRY / LOGICAL** | `--kv-scale` multiplies `test_live2_coord.GPU_KV` (62,944), the **coordinator's logical pool**. 0.25x = 15,736 logical tokens. There is no engine, no `--num-gpu-blocks-override`, no `--max-model-len`, no vLLM allocator and no real eviction cost. |
| **REAL-ENGINE** | the posted live 0.25x cells run `--num-gpu-blocks-override 985 --max-model-len 15744` (that order), engine pool of record **15,760 = 985 x 16 confirmed on hardware**, logical 15,736, tag `_kv0.25`. **No cell in this study is in this register.** |
| **COMMITTED** | a value read out of a committed result file, cited by path. |

This distinction is not pedantry in this project: `d189_kv05_logical_only.json` settled that the
committed `_kv0.5` cells were **logical-only** and had been read as memory pressure before that,
and `d187_cfpd_c5attr_proofs.json` carries the same caveat. Decision latency here is **flash CPU
wall clock** inside the arm's `decide` (`coordinator.py:2127`), measured under the host load the
manifest records per cell; it is not an H100 number.

**UPDATED AFTER THE RUN, in the direction that makes this report stronger: the digests here are
NOT provisional on the touch-price fix.** I was briefed that `TOUCH_PRICE_MODE` would move rung 3's
and rung 4's digests. D216 (landed while these cells ran) records the measurement: the fix **does
not move rung 3 or rung 4** - the overcharge was 105.5x to 154.5x but is **unexercised at 1x, 0 of
2,267 touches refused** - and byte identity passed on 29 arms. So the `-rr` verdicts stand and so do
the digests below. **Every digest here is still dated to the commit it was measured at**; what
remains genuinely provisional is listed in section 7, and what is *not* provisional at all is the
structure, the counters by kind, and whether a mechanism is reachable.

---

## 1. THE FINDING THAT CAME FIRST: our own arms cannot observe GPU-KV capacity

This was a scepticism check on the 0.25x setting and it became the headline. The user's ruling
("if our own arms also cannot observe GPU-KV capacity, report it as a fidelity gap for our policy
too") is answered here, verified on the covex-v6 arms rather than inherited from the triage.

### 1.1 The delegation chain, traced at runtime

`live2_configure(gpu_kv_tokens=...)` reaches a covex-v6 arm along exactly one chain. Traced by
construction and probe, not by reading:

```
covex-v6-cf-c5attr (V6CfRung4C5Attr)
  -> _ProtectDeferMixin.live2_configure      arms_v6cf.py:166   CAPTURES gpu_kv_tokens
  -> V5Rules2Arm.live2_configure             arms_v5rules2.py:164   forwards only
  -> HybridArm.live2_configure               hybrid/hybrid_arm.py:318   forwards only
  -> Live2ArmMixin.live2_configure           arms.py:79   WRITES self._caps
```

After the call, 62,944 is present in exactly two places:

| object | field | file:line of the write |
|---|---|---|
| `V6CfRung4C5Attr` (rung 4 only) | `_pd_gpu_kv_tokens = 62944.0` | `arms_v6cf.py:170` |
| `B7EdfFeasibilityArm` (every covex-v6 arm) | `_caps["gpu_kv_tokens"] = 62944` | `arms.py:82` |

### 1.2 `_caps` is write-only, repo-wide

`grep -rn "_caps\b"` over `experiments/`, `simulator/` and `plots/` returns **one** occurrence of
`self._caps`: the write at `arms.py:82`. There is no read anywhere in the tree. Under CLAUDE.md
Step 2 a quantity written and never read is **ABSENT**, and this is the same shape as
`desired_tier` and the pre-`e924005` `RecallAction.representation`.

Two neighbouring fields are worth separating, because they are not all the same defect:

- `_targets`, written on the same line pair, **is** read (`arms_v5rules.py:176`). Only `_caps` is dead.
- `needs_capacities` (`arms.py:77` declaration, `arms_policy.py:324` the only write `True`) has
  **no read either** - a second write-only field in the same file, already catalogued as absent in
  `reports/study_covex_hardening.md`.

### 1.3 Which of our arms are blind, and which is not

| arm | capacity lands in | a READ that changes a decision | verdict |
|---|---|---|---|
| `covex-v6-base` (rung 0) | `_caps` only | none | **BLIND** |
| `covex-v6-rules` (rung 1) | `_caps` only | none | **BLIND** |
| `covex-v6-state-uo-c5attr` (rung 2) | `_caps` only | none | **BLIND** |
| `covex-v6-fair-c5attr` (rung 3) | `_caps` only | none | **BLIND** |
| `covex-v6-fair-c5attr-rr` (rung 3 + rr) | `_caps` only | none | **BLIND** |
| `covex-v6-cf-c5attr` (rung 4) | `_caps` **and** `_pd_gpu_kv_tokens` | `arms_v6cf.py:302` `_pd_free_kv`, consumed as `PD.decide(free_kv_tokens=...)` | **NOT blind, in the protect-and-defer leg only** |
| `policy-core` (not on the v6 ladder) | `_caps` **and** `params.gpu_kv_capacity_tokens` | `policy/rollout.py:411`, `policy/coordinator.py:569` | not blind |

Rung 4's **question-deferral** leg is capacity-independent **by construction**: `cf_request_defer`
has six gates (`cf_request_defer.py:201`) and not one of them reads a pool. So within rung 4 the
0.25x setting can reach only one of the two legs.

### 1.4 A committed claim this contradicts, and the part of it that stands

`results/INDEX.md` (row `kv025_runnability_probe.json`) states:

> for the two covex arms it IS read on a decision path (`policy/rollout.py:411`,
> `policy/coordinator.py:569`) and still moved no dry decision at seed 4

**That attribution is wrong for `covex-v6-base` and `covex-v6-rules`.** Those two reads belong to
`arms_policy` / `policy-core`, which is reached from a covex-v6 arm only through `HybridArm`'s C6
scorer (`hybrid/hybrid_arm.py:320`), and `sw["c6"]` is **False** on every covex-v6 arm - measured
on all six arms above. D209 (6) then carried the error forward when it exempted those two arms
from hit 14 ("covex-v6-base / covex-v6-rules 0.25x cells are not affected by hit 14 (they read no
capacity field)" - the conclusion is right, the stated reason is the opposite of the probe's).

What **does** stand from that row, and is a different channel entirely: enforcement. With
`CoordState.kv_capacity_enforced` on, `cstate.py:520` evicts over a bounded list regardless of
what the arm can see, and the probe measured that firing (`llf` 0 to 8 epochs over cap). That
channel is **arm-independent** and is why a live 0.25x cell of a blind arm is still not
automatically a null. The two channels are separated by cells in section 3.

### 1.5 Why this matters, and it is not an implementation detail

If an arm cannot see capacity, a flat 0.25x-versus-1x result from it was **never evidence about
the policy**. It is Rule 2 **unexercised**. Stated at full strength:

- Rungs 0 to 3 of our own ladder are in exactly the position of the four edge-arm cells that
  D209 (6) **superseded** for hit 14. The fidelity gap is **ours**, not only the baselines'.
- The rung-4-over-rung-3 comparison at 0.25x is **asymmetric**: rung 4 can see the pool and rung 3
  cannot. Any gain rung 4 shows at 0.25x therefore has an alternative explanation of the first
  order - "rung 4 is the only arm in the comparison that can see the pool" - which is the Step 5
  entry in section 6 and the shape CLAUDE.md's closing bullet warns about (a side of the
  comparison that is never audited).

### 1.6 The fix, and why I have NOT applied it

I was given ownership of `arms.py` and told to fix it. **I have not, and I am escalating instead,
for one reason: there is no implementation-level fix here.** The distinction the brief itself drew
is the one that decides it - a value *read but wrong* is an implementation fix; a value *never
read* needs a **consumer**, and choosing which decision consumes capacity is policy design.

- Giving `_caps` a getter changes nothing. A getter nobody calls is another write-only field, and
  adding one to "close" a write-only-field finding would be cargo cult.
- Making rungs 2 and 3 capacity-**aware** means adding a capacity term to the state layer.
  There is no half-built read to repair: `arms_v6state.py`, `offload_policy.py` and
  `touch_policy.py` contain no capacity quantity at all.
- The mechanism that *is* specified and *is* implemented is `tier_assignment` under bounded GPU
  and host capacity (D26, D56), live at `policy/coordinator.py:569` off
  `params.gpu_kv_capacity_tokens`. Routing the v6 state layer to it is not inventing a mechanism -
  but it **is** a methodological change under CLAUDE.md, it changes rungs 2 and 3, and under
  D209 (1) it makes every committed cell of every rung SUPERSEDED and due a rerun. That is not a
  session's call, and D208 (2) has the final ladder being built and run **once**.

**Escalation, needing one line from the user.** Options, with their cost:

| option | what it does | cost |
|---|---|---|
| **A** | leave the ladder blind; label every 0.25x result for rungs 0 to 3 Rule 2 **unexercised**, and report rung 4's memory result as the only capacity-aware arm, with the asymmetry stated | no reruns; the memory claim narrows to rung 4's PD leg plus the arm-independent eviction channel |
| **B** | route the v6 state layer's tier/touch decisions to `params.gpu_kv_capacity_tokens` (the D26/D56 mechanism, already implemented) | rungs 2 and 3 change; under D209 (1) every committed ladder cell is superseded and rerun; collides with D208 (2)'s build-once |
| **C** | add capacity only to the final ladder (D208 (2)), where rungs are rebuilt anyway | no retroactive supersession of rung 2/3 cells beyond what D208 already plans; the committed 1x grid and the final grid then differ in one more mechanism |

My recommendation is **C**, because D208 (2) already rebuilds and reruns all three rungs together
on one commit, so it is the one moment where the change costs no extra cells. Until a ruling
lands, section 3's verdicts are stated in Rule 2's vocabulary and not as findings about the policy.

**THE WINDOW FOR OPTION C IS CLOSING NOW, AND THAT IS TIME-CRITICAL.** While these cells were
running, origin moved to `1235b070` ("StudyLADDER-FINAL pre-registered and frozen") and
`experiments/orchestration/live2/arms_final_ladder.py` landed with the ruled names
`covex-v6-state-final`, `covex-v6-fair-final`, `covex-v6-final`. I checked it:
**the final ladder adds no capacity read either** - `grep` for `gpu_kv`, `capacity`, `_caps` and
`live2_configure` over that module returns nothing, and its rungs compose
`arms_v6state`, `arms_v6fairfeed`, `arms_v6rr`, `arms_v6cf` and `arms_v6cfr3` unchanged. So the
blindness in section 1.3 carries **into the final ladder**, and the final rung 4 (`covex-v6-final`)
will be the only arm in the final comparison that can see the pool. The ladder is pre-registered
and frozen, so option C has to be decided before it runs, not after.

### 1.7 What blindness does NOT mean, because the distinction decides which cells are nulls

The H100's correction to the morning probe is right and must not be lost here: under the **real**
engine, fewer vLLM blocks means more preemption and less concurrency for **every** arm, so the
pool binds all of them **at the engine** whether or not an arm can observe it. Blindness therefore
means a precise and narrower thing:

- a blind arm **is** subject to 0.25x pressure, and a real-engine 0.25x cell of one is **not**
  automatically a null;
- a blind arm **cannot manage** that pressure - it cannot trade a rebuild against an eviction,
  because it does not know a cap exists;
- so for a blind arm, 0.25x is a **load condition**, not a **decision** condition, and a flat
  *decision* response is Rule 2 **unexercised**, while its *outcome* response is real and comes
  from the engine and the coordinator, not from the policy.

That is the distinction a DRY cell is good for and a live cell is not: dry has no engine, so for a
blind arm it isolates exactly the channel that is absent. It is also why section 3 reports the
enforcement-off and enforcement-on pairs separately rather than one 0.25x number.

**Section 3.3 then sharpens this paragraph against itself, and the sharper version is the one to
quote.** Measured, the eviction channel moves 47.6k tokens to host and changes **zero** dry
decisions, because eviction changes a session's *tier* and live2 does not read tier for decisions.
So what makes a live 0.25x cell of a blind arm non-null is a **re-prefill cost** the dry simulation
cannot price - not a decision. A blind arm's memory result can therefore only ever be an
**outcome** claim, never a policy claim.

Separately and **not** conflated with the above: `gpu_kv_fraction` is 0.0 in every live cell
because `cstate.py:663` reads `vllm:gpu_cache_usage_perc` while the engine emits
`vllm:kv_cache_usage_perc` (0.7215 at capture). That is Session A's. It is a **second, independent**
reason capacity may never have reached a decision, and it bites rung 4 specifically: `_pd_free_kv`
takes `max(occ_metric, occ_belief)`, so with the metric stuck at 0.0 the gate runs on the
**belief** term alone. **D216 (2), landed while these cells ran, makes that cause deeper than the
briefing did: `AsyncLive2Backend` never scrapes `/metrics` at all**, so the field is 0.0 "because
nothing reads it" - an absent scrape under a wrong key name. Section 3.4 measures the consequence.
The two defects are independent: fixing the metrics path does not fix `_caps`, and fixing `_caps`
does not fix the metrics path.

---

## 2. Mechanism verification (CLAUDE.md), recorded before the sweep

### Step 0 - what would make this run uninterpretable, asked before starting it

| asked | answer | cost |
|---|---|---|
| Is the comparator about to change? | **Yes, twice.** `TOUCH_PRICE_MODE` (Session A) will move rung 3's and rung 4's digests, and D208 (2) rebuilds all three rungs on one commit under the now-ruled `-final` names. So no digest here is a bar for a later cell. | recorded, not blocking: the counters by kind and the reachability verdicts do not depend on the digest value |
| Does the mechanism have a reachable path at this size and in this regime? | **This is the question that changed the study.** It does for rung 4's PD leg (`arms_v6cf.py:302`), it does not for rung 3 (section 1), and it does not for rung 4's question-deferral leg (no pool read). | about forty minutes of grepping and one runtime probe; it found the capacity-blindness finding before any cell ran |
| Does a run I depend on key into my analysis? | Gate A's safety factor is derived from the committed rung-3 cells, which D208 (1) has just widened to include `-rr`. So Gate A has to be re-derived when the final rung 3 exists. | section 4 reports both inputs |
| Is a default about to be restored? | `CoordState.kv_capacity_enforced` defaults **False** and `test_hybrid.dry` never sets it, while every posted `_kv0.25` cell sets it **True**. A plain dry cell is therefore the wrong regime. | one extra flag (`--enforce-kv`) and one extra cell pair, which is cheap against a verdict given in the wrong regime |

### Step 1 - the causal chain

If the GPU KV pool is a configured input (FORMULATION §memory capacities / D56), then at 0.25x of
the committed pool a cold rebuild that would fit at 1x no longer fits without evicting a warm
history; the arm that **reads** the pool (`arms_v6cf.py:302`, free KV = pool minus the larger of
the engine-metric and residency-belief occupancies) therefore reaches protect-and-defer's eviction
gate instead of stopping at it; the compound then values the harm the eviction would do to other
devices' pending deadline requests in counts of expected on-time cloud answers, each weighted by
its per-device `w_d` from the live deficit feed (D185), and defers or chunks the rebuild when that
harm exceeds `w_R x MARGIN_CF`; fewer warm histories are lost, so fewer questions arrive cold, so
more of them meet the latency SLO. **Separately and through no pool read at all**, the
question-deferral leg defers a cloud-admitted recall question to its latest safe start while an
alert episode is active, which is where rung 4's 1x contribution came from entirely.

The link that is **not** in this chain, and whose absence is section 1: nothing in rungs 2 and 3
reads the pool, so "memory pressure changes a rung-3 decision" has no path at all.

### Step 2 - instantiating each link

| causal link | implementing quantity | the READ that consumes it | value / range | varies as claimed? |
|---|---|---|---|---|
| pool is a configured input | `test_live2_coord.GPU_KV` -> `live2_configure(gpu_kv_tokens=)` | `arms_v6cf.py:170` write, `arms_v6cf.py:302` read | 62,944 at 1x; 15,736 at 0.25x | yes (set per cell) |
| free KV estimate | `_pd_free_kv` = pool - max(metric, belief) | `arms_v6cf.py:336` `PD.decide(free_kv_tokens=...)` | section 3's `pd_free_kv_min/max` | **to be read off the cells** |
| engine-metric half of that estimate | `obs.cloud.gpu_kv_fraction` | `arms_v6cf.py:306` | **identically 0.0 dry, and 0.0 LIVE too** (`cstate.py:663` key-name defect) | **CONSTANT - declared, not discovered** |
| eviction gate reached | `pd_gate_rebuild_fits_without_evicting` vs the gates past it | `cf_protect_defer.decide` | section 3 gate mix | to be read off the cells |
| harm in on-time answers | `pd_harm_*`, `harm_distribution` | the inequality in `cf_protect_defer.decide` | section 3 | to be read off the cells |
| per-device weight live in the bar | `w_of = feed.weight_device` | `arms_v6cfr3.py:565`, read back and asserted at `:572` | `W_WIRED_PROOF`; bar distribution in `rd_report()["bar"]` | to be read off the cells |
| rung-3 decisions respond to the pool | **none exists** | - | - | **ABSENT** (section 1) |
| question deferral | `rd_question_defers` | `cf_request_defer.decide` gates, `cf_request_defer.py:201` | section 3 | to be read off the cells |

Two entries are already marked before any cell runs, and both are stopping conditions for the
claims they belong to and for nothing else:

- the **engine-metric half** of the free-KV estimate is CONSTANT at zero, dry *and* live. The
  component's own docstring declares this dry; the live half is new (Session A's `cstate.py:663`).
  So the gate runs on the residency **belief** alone. A claim of the form "rung 4 responds to real
  engine KV occupancy" is **unexercised** on this build. A claim of the form "rung 4 responds to
  the configured pool and its own residency belief" is testable and is what section 3 tests.
- the **rung-3 capacity link is ABSENT**, so no 0.25x-versus-1x result for rungs 0 to 3 may be
  reported as a finding about the policy.

### Step 2b - the switch reaching a decision

Run **before** any scoring, on one cell per condition, each leg separately (addendum 12 item 5: a
combined count that cannot be attributed is not a pass), at the memory setting the cells run at
*and* in both enforcement regimes. The pairs and their counts are section 3. The comparator is
`covex-v6-cf-c5attr-off` at the **same** memory setting and the **same** enforcement setting,
never the 1x off arm, because a cross-setting comparator confounds the switch with the condition.

### Step 3 - one traced unit

`cf_pd_one_cell` keeps `traced_decision`, `traced_bar_crossing` and `pd_trace_lines`, and the rung-4
wrapper keeps `rd_report()["traced_decision"]`; both are human-readable arithmetic traces. They are
reproduced in section 3.4.

### Step 4 - negative control

`covex-v6-cf-c5attr-harm0` (harm zeroed at source on **both** legs, every hook and counter still
live) must collapse to the off arm's digest at 0.25x. It is a **named arm**, so the control is a
cell and not a code edit. Note which control is *not* used: scaling the deficit **weight** is the
broken control `cf_protect_defer.bar` records, because every harm row carries the same weight so
harm and bar scale together.

### Step 5 - alternative explanations

1. **Rung 4 is the only arm in the comparison that can see the pool** (section 1.5). Distinguished
   by: the enforcement-on/off cell pairs, which separate the arm's own read from the
   arm-independent eviction channel, and by rung 3's own 1x-vs-0.25x pair being flat.
2. **The question-deferral leg carries everything and protect-and-defer is decoration.** This was
   true at 1x (D190: PD moved zero decisions, `-rqonly` was byte-identical to the full arm).
   Distinguished by the `-pdonly` and `-rqonly` cells at 0.25x.
3. **The 0.25x movement is host-load noise, not the pool.** Distinguished by the off arm at the
   same setting: it sees the same host load and reads no pool.
4. **The deferral helps only because the safety factor is slack.** Distinguished by Gate A's
   exposure and overrun magnitude (section 4), and it is not fully excluded: every deferral retains
   zero margin by construction.

---

## 3. THE 0.25x DRY REPORT

Cell conditions, identical for every cell: `covex-v6-cf-c5attr` family, **dry**, **seed 4**,
16 devices, 1,200 s, posted knobs (ratio 40:40:20, lh_req, ss2, dashcam epg, robot per-frame,
reask 30.0 s), planner wall-clock cutoff **patched off**, **one cell per process**, cells run
**strictly sequentially at concurrency 1 from this session**. The host was shared: twenty-plus
foreign processes at 100 % CPU on 24 cores for most of the window, and the 1-minute load average
at each cell's start is recorded in `cells/manifest.json` beside its digest. Single seed, because
D196 fixes fail-fast s4 first; a one-seed result is not a four-seed result and is not reported as
one.

### 3.0 A BROKEN IDENTITY FOUND BY THE FIRST COMPARATOR CELL, before anything was scored

`covex-v6-cf-c5attr-off` at 1x on the committed recipe gives **`dc686e63f9a313ec` / 14,523 rows**.
The module that defines it declares (`arms_v6cfr3.py:67`): *"THE OFF ARM IS THE RUNG-3 ARM ...
CLAUDE.md Step 4 requires it to be byte-identical to the COMMITTED `covex-v6-fair-c5attr`."* The
committed rung-3 bar on that recipe is `12e4f73ce0ebd865` / 13,812
(`frozen_test/d190_rung4_r3_proofs.json` proof 3; re-measured IDENTICAL by StudyD200-WEIGHT's F3
cell). **The off arm is 711 rows away from the bar it declares for itself.**

I did not read that as a null, a host-load artefact or a stale bar. I traced it, and the cause is
in the code, not in the measurement:

- `arms_v6cfr3._Rung4Mixin._cf_engine` (`arms_v6cfr3.py:320-348`) swaps the state planner's weight
  source from the base's declared constant (`cf_objective.NoPlannerDeficitFeed`, set at
  `arms_v6state.py:208`) to the live `PlannerDeficitWeights`, and it does so
  **unconditionally** - it reads neither `protect_defer` nor `request_defer`. So with **both
  compounds off**, the off arm is still rung 3 **plus** a deficit-weighted state planner.
- The size matches: D206 (2) measured that rung 3's state planner reading `deficit_feed` changes
  **687 of 60,473** state decisions, and deferred that change to the final-ladder rerun
  ("applied at the FINAL LADDER RERUN ..., not now"), with its c3 proof recording that rung 3's
  planner was left untouched. It was left untouched **in rung 3**; it is live in every arm of the
  rung-4 family, the `-off` arm included.
- D195 (1) independently recorded the pair `12e4f73ce0ebd865 -> dc686e63f9a313ec, +711 rows` and
  closed it as a **recipe mismatch** (a cutoff-live digest compared against a cutoff-off bar). My
  cell is cutoff-off, and the positive control in the same run (`covex-v6-state-uo` reproducing
  `9a4be873eb3c5fba` / 14,218 exactly) shows the recipe is right. So the same number has now
  arisen from a **second, different** cause, and the D195 explanation does not cover this one.

**What this does and does not invalidate.**

| | status |
|---|---|
| Step 2b pairs in 3.1 (`covex-v6-cf-c5attr` vs `-off`, at matched memory and matched enforcement) | **VALID.** Both sides carry the deficit-weighted planner, so the difference isolates the two compounds, which is what Step 2b asks. |
| the Step 4 negative control (`-harm0` vs `-off`) | **VALID**, same reason. |
| "the off arm reproduces the committed rung-3 digest" as a positive control | **INVALID at this commit.** It is not a check that failed; it is a bar that stopped applying. |
| any reading of the off arm as "rung 3" | **INVALID.** It is rung 3 + the D206 (2) planner weight, a mechanism D206 explicitly deferred out of rung 3. |
| `arms_v6cfr3.py:67`'s self-declared identity requirement | **FALSE as written.** Reported, not edited: the module is Session B's. |

So an extra cell was added to the run - `covex-v6-fair-c5attr` at 1x, rung 3 **by its own name** -
because without it there is no uncontaminated rung-3 bar on this commit, and the off-vs-rung-3
delta is the size of the contamination. Its result is in 3.1.

**WHY THIS CANNOT BE MY INSTRUMENT, AND THE CONTROL STRUCTURE THAT SETTLES IT.** Two committed
bars are reproduced EXACTLY in the same run, by the same runner, on the same checkout, at the same
recipe:

| cell | measured | committed bar | source of the bar | verdict |
|---|---|---|---|---|
| `covex-v6-state-uo` 1x | `9a4be873eb3c5fba` / 14,218 | `9a4be873eb3c5fba` / 14,218 | `frozen_test/c5attr_digest_proofs.json` P1 | agreed exactly, **withdrawn as a bar** under D216 (1) - see 3.11 |
| `covex-v6-cf-c5attr` 1x (**rung 4 itself**) | `f5b627392839527c` / 14,470 | `f5b627392839527c` / 14,470 | StudyD200-WEIGHT F4, pushed `0ca54444` | **PASS, exact** |
| `covex-v6-cf-c5attr-off` 1x | `dc686e63f9a313ec` / 14,523 | *declared* `12e4f73ce0ebd865` / 13,812 | `arms_v6cfr3.py:67`, `d190_rung4_r3_proofs.json` proof 3 | **the BAR does not apply** |

The second row is the load-bearing one, and it is the one D216 (1) leaves standing. **The arm under
test reproduces its own committed digest to the character**, so the checkout, the recipe, the
`--cutoff-off` patch and the latency-keeping wrapper are all right. Section 3.5 then adds a third,
rung-3 bar, also exact. An instrument that reproduces the committed digests of **rung 4 and rung 3
exactly** and then disagrees with the off arm's declared bar by 711 rows is not a broken instrument;
that bar is a bar that stopped applying. That is CLAUDE.md check 7 in both directions at once - an impossible success beside an
impossible failure - and it is the only reason this can be reported as a finding about the code
rather than as a suspicion about the run.


### 3.1 DOES 0.25x BIND? The control arm answers first, and it answers flatly

The cleanest result in this study, and it needs no interpretation. `covex-v6-cf-c5attr-off` -
rung 3 plus the D206 planner weight, an arm with **no pool read anywhere** - was run at both
memory settings, same commit, same seed, same recipe, enforcement off:

| | 1x | 0.25x |
|---|---|---|
| cap handed to the coordinator (`st.gpu_kv_tokens`, read back off the object) | **62,944** | **15,736** |
| **decision digest** | `dc686e63f9a313ec` | **`dc686e63f9a313ec`** |
| rows | 14,523 | **14,523** |
| peak GPU residency reached | 58,281 tokens | **58,281 tokens** |
| epochs over cap | **0** of 12,001 | **10,934** of 12,001 (91.1 %) |
| over-cap intervals | none | two, of 3,971 and 6,117 epochs |
| sessions evicted | 0 (enforcement off) | 0 (enforcement off) |

**The condition is real and it is severe. It changes nothing.** The pool arrived - 15,736 read
back off `CoordState`, not merely passed - and the workload overshoots it by **3.7x at the peak**
for **91 % of the run**. The decision log is **byte-identical** to 1x, and the residency peak is
identical to the token, which is the strongest form of the statement: not merely the same
decisions, the same trajectory.

**VERDICT, in Rule 2's own vocabulary: INCONCLUSIVE - UNEXERCISED.** The mechanism "GPU-KV capacity
constrains a decision" is reachable in the simulation only through a read, and this arm has none
(section 1). It is **not** an equivalence, it is **not** "0.25x does not matter", and it is **not**
a finding about the policy. It is the same category as `RELOAD` offered only at HOST-WARM with no
recall reaching HOST-WARM, and as E36/E36b/E36c.

Two things this does **not** say, kept separate on purpose:

- It does not say a **live** 0.25x cell of a blind arm is a null. Live, the engine has fewer blocks
  and `cstate.py:520` evicts under `--kv-capacity-enforced`; both bite regardless of what the arm
  can see (section 1.7). What is unexercised is the **decision** channel, not the condition.
- It does not say the 0.25x **instrument** is broken. The instrument demonstrably works: the cap
  reached the coordinator and the pressure counters moved from 0 to 10,934 epochs over cap. The
  arm is what cannot see it.

This is also the control that licenses reading rung 4's own 0.25x result: the off arm saw the same
host load, the same foreign processes and the same scheduler and came back bit-identical, so a
difference in the rung-4 arm at 0.25x cannot be host-load noise.

### 3.2 CHARACTERISTIC DECISIONS BY KIND at 0.25x, and ONE KIND IS ZERO

`covex-v6-cf-c5attr`, dry, 0.25x, enforcement off, against its own off arm at the same setting.
**The arm moves**: `cde9545ac1d383f3` / 14,445 against the off arm's `dc686e63f9a313ec` / 14,523,
while the off arm itself is bit-identical between 1x and 0.25x (3.1). So the movement is
attributable to the one thing that differs - rung 4's own read of the pool at `arms_v6cf.py:302`.

| characteristic decision kind | 1x | **0.25x** | counter |
|---|---|---|---|
| protect-and-defer: state **deferrals** | 0 | **5** | `pd_state_defers` |
| protect-and-defer: **chunk** decisions | 0 | **2** | `pd_state_chunks` |
| protect-and-defer: **protects** | 0 | **19** | `pd_protects` |
| protect-and-defer: **request deferrals** | 0 | **16** | `pd_request_defers` |
| **question deferrals** | 6 | **0** | `rd_question_defers` |
| **TOTAL** | **6** | **42** | |

**PORT RULE: PASS on the arm, with an explicit ZERO on one kind.** The arm makes its own
characteristic decision 42 times, so it is not being scored for doing nothing. But
`rd_question_defers = 0` is a kind that fired 6 times at 1x and fires **not once** at 0.25x, and
per the brief a zero is a stopping condition and not a number to report in passing.

**Why it is zero, traced through the gate mix rather than guessed.** The question-deferral leg was
offered fewer decisions and lost them earlier:

| | 1x | 0.25x |
|---|---|---|
| `rd_decisions` offered | 88 | 82 |
| `rd_skipped_already_deferred` | 4 | **20** |
| `rd_reached_harm` | 22 | 11 |
| `rd_gate_no_active_alert_episode` | 20 | 22 |
| `rd_gate_must_start_now_no_slack` | 46 | 49 |
| `rd_gate_saving_does_not_exceed_margin` | 16 | 11 |
| `rd_gate_defer_to_latest_safe_start` (the firing gate) | **6** | **0** |

`rd_skipped_already_deferred` went 4 to 20, and protect-and-defer made **16** request deferrals at
0.25x against 0 at 1x. 4 + 16 = 20. **The two legs compete for the same requests, and under
memory pressure the protect-and-defer leg takes them first.** This is a LEG INTERACTION inside
rung 4, not a property of the question-deferral mechanism, and it is exactly why addendum 12 item 5
requires each leg to be runnable alone: the `-rqonly` cell at 0.25x distinguishes "crowded out by
the other leg" from "0.25x kills this leg", and is reported in 3.3.

**Provisional classification, pending 3.3:** `rd_question_defers = 0` at 0.25x reads as Rule 2
**unexercised** *for that leg in the compound* - the mechanism is reachable and fired at 1x, and no
condition in the 0.25x compound run reaches it because another leg consumed its candidates first.
It is NOT "fired and did not help", and it is NOT evidence that question deferral fails under
memory pressure.

**A real memory-pressure effect, and it is on the outcome side.** The pressure counters are the
first measurement in this project of our policy doing something about memory pressure, and the
comparison is against the off arm at the **same** setting:

| at 0.25x | off arm | **rung 4** |
|---|---|---|
| peak GPU residency | 58,281 tokens | **53,071 tokens** (−5,210) |
| epochs over cap | 10,934 of 12,001 | **10,845** of 12,001 (−89) |
| free KV seen by the gate, min / max | n/a (no read) | 0 / 15,736 |
| which bound the free-KV estimate | n/a | **belief 261 of 261**, engine metric 0 of 261 |

Protect-and-defer **lowered peak KV occupancy by 5,210 tokens** and cut 89 over-cap epochs. Both
are small and both are dry, so they are a statement about the simulated residency trajectory and
not about engine cost - a dry cell has no engine and cannot price an eviction. The last row is the
Step 2 CONSTANT declared in section 2: every one of the 261 free-KV estimates was bound by the
residency **belief**, and the engine metric contributed to none, because it is identically 0.0.

**The deciding bar is a distribution, not a constant.** `rd_report()["bar"]`: n = 11, min 0.99955,
median 1.66127, max 1.97472, **9 distinct values**, all 11 strictly above the w = 1 floor of
0.65824. So the live per-device `w_d` is in the inequality and is not cancelled by geometry.

### 3.3 THE SECOND CHANNEL: enforcement fires hard and changes nothing either

`CoordState.kv_capacity_enforced` is the only consumer of the pool that can evict
(`cstate.py:520`), it is **off** by default in `test_hybrid.dry`, and it is **on** in every posted
`_kv0.25` cell. So it is the second of the two paths the pool has to a decision, and it is
arm-independent. The off arm was run at 0.25x with it on.

**The switch arrived, proved rather than assumed** (section 2's Step 2b requirement that a switch
reach the object under test with its declared type and value): `kv_capacity_enforced` read back off
`CoordState` as `True`, type `bool`, with `gpu_kv_tokens` 15,736 on the same object. It had to be
applied on the **instance** - see the fault in `d210_kv025_one_cell.py`'s docstring, where the
first version set the dataclass's class attribute and never reached `__init__`'s baked-in default.

**And it fired about as hard as it could:**

| `covex-v6-cf-c5attr-off` at 0.25x | enforcement OFF | enforcement ON |
|---|---|---|
| epochs over cap | 10,934 of 12,001 | **14** of 12,001 |
| over-cap intervals | 3,971 and 6,117 epochs | fourteen intervals of **1** epoch each |
| peak GPU residency | 58,281 tokens | **16,747** tokens (the cap is 15,736) |
| peak **host** residency | 0 tokens | **47,588** tokens |
| **decision digest** | `dc686e63f9a313ec` / 14,523 | **`dc686e63f9a313ec` / 14,523** |

**47,588 tokens of history were evicted to the host tier and the decision log did not change by a
single row.** The coordinator held the cap - 10,934 over-cap epochs became 14, each one epoch long
- and the arm decided identically to its own 1x run.

**This corrects, in the direction that weakens my own earlier framing, what section 1.7 said about
this channel.** I wrote that the eviction channel is "real and arm-independent", and physically it
is. But in the **decision** register it is as dead as the `_caps` channel: eviction changes a
session's **tier**, and live2 is documented not to read tier for decisions
(`desired_tier` written twice and never read - the D124-D134 catalogue's "live2 models KV
OCCUPANCY but not KV PLACEMENT"), while `built_tokens` - which readiness *is* computed from -
survives the eviction. So in a dry cell **both** of the pool's paths to a decision are
**unexercised**, and the honest decomposition is:

| channel | physically active at 0.25x? | changes a DRY decision? | changes a LIVE outcome? |
|---|---|---|---|
| arm's own pool read (`_caps`) | n/a, there is no read | **no** - ABSENT | no |
| coordinator eviction (`cstate.py:520`) | **yes, 47.6k tokens moved** | **no** - tier is not read | **yes, but only as COST**: the engine must re-prefill an evicted prefix, and a dry cell has no engine to price it |

So the thing that makes a live 0.25x cell of a blind arm non-null is a **cost** the dry simulation
cannot represent, not a decision. That is a sharper and more useful statement than "the pool binds
at the engine", and it means the memory claim for a blind arm can only ever be an **outcome**
claim, never a policy claim.

### 3.4 AND NOT EVEN RUNG 4 SEES THE EVICTION: the free-KV estimate is size-sensitive, occupancy-blind

Rung 4 reads the pool, so enforcement should have reached it: evicting a history ought to shrink
the believed-GPU set, raise free KV, and make the eviction gate fire less. It did not.

| `covex-v6-cf-c5attr` at 0.25x | enforcement OFF | enforcement ON |
|---|---|---|
| **decision digest** | `cde9545ac1d383f3` / 14,445 | **`cde9545ac1d383f3` / 14,445** |
| `pd_free_kv_sum` over 261 estimates | 1,230,553 | **1,230,553** |
| `pd_free_kv_min` / `max` | 0 / 15,736 | **0 / 15,736** |
| bound by residency belief | 261 of 261 | **261 of 261** |
| `pd_protects` / `pd_request_defers` / `pd_state_defers` / `pd_state_chunks` | 19 / 16 / 5 / 2 | **19 / 16 / 5 / 2** |
| epochs over cap | 10,845 of 12,001 | **12** of 12,001 |
| peak GPU residency | 53,071 | **16,626** |
| peak **host** residency | 0 | **39,396** |

**39,396 tokens were evicted and the free-KV estimate did not move by one token.** Every one of
the 261 estimates stayed belief-bound, so this is not a tie-break or a rounding effect.

**The code-level explanation, with its condition named.** `_pd_free_kv` takes
`pool - max(occ_metric, occ_belief)`. Its two inputs are:

- `occ_metric` = `obs.cloud.gpu_kv_fraction x pool`, and that fraction is **identically 0.0**
  (0.0 dry for want of a server, and 0.0 live too). Contributes nothing, as section 2 declared
  before the run. **The live cause is deeper than the one I was briefed on**: I was told
  `cstate.py:663` reads `vllm:gpu_cache_usage_perc` while the engine emits
  `vllm:kv_cache_usage_perc`. **D216 (2)** records that `AsyncLive2Backend` **never scrapes
  `/metrics` at all**, so the field is 0.0 "because nothing reads it" - a wrong key on top of an
  absent scrape. Session A is adding the scrape with this build's real metric names and hit-6
  fail-loud semantics **before any 0.25x policy cell**, and D216 (2) states that of all arms
  **only `covex-v6-final`'s gate changes** - an independent confirmation of section 1.3's finding
  that rung 4 is the only arm on the ladder that reads capacity.
- `occ_belief` = the `built_tokens` of the sessions in `obs.cloud.gpu_warm_sessions`, which is the
  **believed**-GPU set (`cstate.py:653`, the argmax of each session's belief). Eviction goes through
  `SessionRec.set_tier`, which moves `measured_tier` unconditionally but moves the **belief** only
  when the build is COMPLETE (`cstate.py:207`: `built_tokens >= est_tokens and est_tokens > 0`).
  Under the posted per-frame robot upload a history is partial for most of its life, so the belief
  does not follow the eviction and the believed-GPU set does not shrink.

That explanation is **corroborated twice over, and not only by reading the code.** First, a
committed census: across 39 committed 16-device cells the residency census is cold 14,472 /
gpu 1,442 / **host never** - no committed cell has ever observed a host-warm session, which is also
why `arms_v6state` records RELOAD as permanently unexercised. If the belief never reaches host,
`occ_belief` cannot fall when a history is evicted to host, and rung 4's gate cannot see it.

Second, and reached independently from the opposite end, **D211** (landed while these cells ran):
the H100 probe found the engine folds host-cache hits into `cached_tokens`, so "the policy's
residency belief never sees 'host' and its state-based prices cannot tell host-warm from cold;
reload happens natively but is unobserved by the policy (**structurally unexercised in its
decisions**)". D211 reaches that from the engine's telemetry; this section reaches it from the
coordinator's eviction. **Two independent routes, one conclusion** - and D211's own words for it
are Rule 2's.

**So rung 4's capacity gate is sensitive to the pool's SIZE and blind to its OCCUPANCY.** Its
entire 0.25x response - the 42 characteristic decisions of 3.2 - is driven by the configured
constant 15,736 against predicted rebuild sizes, not by any observation of how full the pool
actually is. That is a true and testable mechanism, and it is a weaker mechanism than the
component's own docstring implies when it calls the belief term "the only way the gate is
reachable at all". It is reachable; it is just not *responsive*.

**Consequence for the memory claim, stated plainly.** Rung 4's 0.25x result is a response to a
**declared capacity**, not to **measured pressure**. Two things would make it responsive, neither
is mine, and both are now **ruled** rather than merely recommended: Session A's `/metrics` scrape
with this build's real metric names (**D216 (2)**, explicitly "lands before any 0.25x policy
cell"), and host residency becoming observable so the belief can carry host-warm (**D211**, "fix
inside the final ladder ... before any 0.25x policy cell"). Until both land, the 0.25x policy
result must be worded "the policy reacts to a smaller configured pool", **not** "the policy reacts
to memory pressure". That wording distinction is the whole of what this section buys, and it is
worth more than the 42 decisions it qualifies.

### 3.5 THE BLINDNESS, CONFIRMED AGAINST A COMMITTED BAR, AND THE CONTAMINATION PINNED AT 711 ROWS

The strongest single cell in the study. `covex-v6-fair-c5attr` - **rung 3 by its own name**, the arm
the paper labels - run at **0.25x**:

> `12e4f73ce0ebd865` / **13,812 rows**

That is the **committed rung-3 digest, measured at 1x**
(`frozen_test/d190_rung4_r3_proofs.json` proof 3; re-measured IDENTICAL by StudyD200-WEIGHT's F3
cell at `1f5cf80e`). So rung 3 at a **quarter of the KV pool** decides **byte-identically to its
own committed full-pool bar**. The blindness is no longer an inference from a `grep`, nor a
within-run control: it is a disagreement-free match against a number committed before this session
existed.

This one cell settles three things at once:

| | |
|---|---|
| **1. Rung 3 is blind to GPU-KV capacity.** | 0.25x vs the committed 1x bar: **0 rows of difference.** Rule 2 **INCONCLUSIVE - UNEXERCISED**, not an equivalence. |
| **2. The off arm is not rung 3 at this commit.** | rung 3 `12e4f73ce0ebd865` / 13,812 against the off arm's `dc686e63f9a313ec` / 14,523, **same commit, same recipe, same run, same seed**: the contamination from `_cf_engine`'s unconditional planner-weight swap (section 3.0) is exactly **+711 rows**, and it matches D206 (2)'s own 687-of-60,473 state-decision measurement in size. |
| **3. The instrument is sound, and on an admissible bar.** | a committed bar reproduced exactly at the *non-default* memory setting, which also shows `--kv-scale` does not perturb an arm that does not read the pool. Unlike the rung-2 control this one is **not** disallowed by D216 (1). |

And a load-sensitivity datum falls out of it for free: this cell started at host load **2.27**
while the rung-2 cell started at **12.54**, and **both** reproduced their committed digests
exactly. So under `--cutoff-off` the host-load sensitivity that
`d190_rung4_r3_proofs.host_load_hazard_measured` recorded at concurrency 3 did not appear here.
Section 3.11 gives the full table - twelve digest agreements across a 6.6x load range - and states
what it is: a measurement on this recipe, not a licence to ignore D216 (1)'s alone rule.

### 3.6 LEG ATTRIBUTION: the two compounds swap places, and they are NOT additive

Addendum 12 item 5 requires each leg to be runnable alone, because a combined count that cannot be
attributed is not a pass. Each leg alone, at 0.25x, against the full arm and against 1x:

| arm | memory | digest | rows | `pd_*` characteristic | `rd_question_defers` |
|---|---|---|---|---|---|
| `covex-v6-cf-c5attr` (full) | 1x | `f5b627392839527c` | 14,470 | 0 | **6** |
| `covex-v6-cf-c5attr-rqonly` | **0.25x** | **`f5b627392839527c`** | **14,470** | - (off) | **6** |
| `covex-v6-cf-c5attr` (full) | 0.25x | `cde9545ac1d383f3` | 14,445 | **42** | **0** |
| `covex-v6-cf-c5attr-pdonly` | 0.25x | **`cde9545ac1d383f3`** | **14,445** | **42** | - (off) |

Four exact identities, and together they say something sharper than "rung 4 responds to memory":

**1. The question-deferral leg is byte-identically insensitive to memory.** `-rqonly` at 0.25x
equals the full arm at 1x to the character, and every one of its counters matches
(`rd_decisions` 88, `rd_reached_harm` 22, `rd_question_defers` 6,
`rd_skipped_already_deferred` 4, and all four harm micro-sums). That is the measured confirmation
of the structural claim in section 1.3: `cf_request_defer`'s six gates
(`cf_request_defer.py:201`) contain **no pool read**, so the leg cannot respond to the pool, and it
does not. Rule 2: for this leg, memory pressure is **unexercised by construction**, and it always
will be.

**2. The two legs swap places between the two settings, and each is the whole arm at one of them.**

- at **1x**: full == `-rqonly`. Protect-and-defer contributes **nothing** (3 bar crossings, all
  unexpressible; D190 measured the same).
- at **0.25x**: full == `-pdonly`. Question deferral contributes **nothing**.

Rung 4 is therefore never really two compounds at once on this workload: it is one compound at a
time, and **which** one is decided by the memory setting.

**3. THEY ARE NOT ADDITIVE, AND THE COMPOUND LOSES THE SIX DEFERRALS.** Run alone at 0.25x the
question-deferral leg makes **6** deferrals. Run inside the full arm at 0.25x it makes **0**, and
the full arm is byte-identical to protect-and-defer alone. The gate mix says exactly where they
went: `rd_skipped_already_deferred` goes 4 to 20, and 4 + 16 = 20 against protect-and-defer's
**16** request deferrals. **Protect-and-defer strictly pre-empts question deferral at 0.25x**, on
the same requests.

**So the 3.2 classification is CONFIRMED, not merely provisional.** `rd_question_defers = 0` in the
compound at 0.25x is Rule 2 **INCONCLUSIVE - UNEXERCISED for that leg in that compound**: the
mechanism is live, reachable and fires 6 times when the other leg is not competing with it, and no
condition in the compound run reaches it because its candidates were consumed first. It is **not**
"fired and did not help", and it is **not** evidence that question deferral fails under memory
pressure.

**What this costs the rung-4 claim, said plainly.** Whether trading 6 question deferrals for 42
protect-and-defer decisions is a *gain* is a scoring question - alert attainment per episode and
robot on-time retention, the D190 (3) frontier test - and **a dry cell cannot answer it**. What the
dry cell establishes is that the trade is happening and is not a free addition, so the rung-4 gate
must be judged on a scored cell and the pre-registered frontier test cannot be inferred from these
counters. It also means the two legs should be reported separately in any 0.25x result, because the
compound's number is one leg's number at each setting.

### 3.7 STEP 4 NEGATIVE CONTROL: the mechanism is what drives the 0.25x difference

`covex-v6-cf-c5attr-harm0` at 0.25x - harm zeroed **at its source on both legs**, every hook,
gate and counter still live, as a **named arm** so the control is a cell and not a code edit:

| | digest | rows | characteristic decisions |
|---|---|---|---|
| `-harm0` at 0.25x | `dc686e63f9a313ec` | 14,523 | 0 / 0 / 0 / 0 / 0 |
| the off arm at 0.25x (the bar) | `dc686e63f9a313ec` | 14,523 | - |

**PASS: it collapses to the off arm exactly.** Disabling the mechanism at its source removes the
entire 0.25x difference - 14,445 rows become 14,523, `cde9545ac1d383f3` becomes
`dc686e63f9a313ec` - and all five characteristic counters go to zero. So the difference in 3.2 is
driven by the harm-versus-bar inequality and not by something incidental, such as the arm
coincidentally picking a different candidate order.

This is the control that upgrades 3.2 from "the digest moved" to "the mechanism moved it", and it
is the one CLAUDE.md Step 4 asks for. Note which control is deliberately **not** used: scaling the
deficit **weight** is the broken control `cf_protect_defer.bar`'s docstring records, because every
harm row carries that same weight, so harm and bar scale together, the ratio is unchanged, and the
control reproduces the treatment.

### 3.8 DECISION LATENCY against the 20 ms budget, with the distribution

Register first: **flash CPU wall clock** inside the arm's `decide` (`coordinator.py:2127`), in a
**dry** cell with no engine in the loop, on a host shared with other sessions. It is a **floor**
for the live number, not the live number, and it is not an H100 number.

All eleven cells, in milliseconds, nearest-rank quantiles:

| cell | n | min | p25 | median | p75 | **IQR** | p90 | **p99** | max | distinct | **> 20 ms** |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `P1_state_uo_1x` | 14,218 | 0.164 | 0.829 | 0.971 | 1.396 | 0.567 | 1.618 | **3.409** | 11.535 | 5,476 | **0** |
| `R4off_1x` | 14,523 | 0.182 | 0.950 | 1.525 | 1.667 | 0.718 | 1.772 | **4.345** | 13.917 | 5,044 | **0** |
| `R4_full_1x` | 14,470 | 0.202 | 1.054 | 1.236 | 1.603 | 0.549 | 1.719 | **2.992** | 11.624 | 5,115 | **0** |
| `R4off_kv025` | 14,523 | 0.118 | 0.999 | 1.076 | 1.583 | 0.584 | 1.672 | **2.571** | 10.336 | 5,033 | **0** |
| `R4_full_kv025` | 14,445 | 0.195 | 0.889 | 1.010 | 1.052 | 0.162 | 1.486 | **2.493** | 9.113 | 4,117 | **0** |
| `R4off_kv025_enf` | 14,523 | 0.109 | 0.796 | 0.921 | 0.975 | 0.179 | 1.005 | **1.968** | 4.318 | 3,683 | **0** |
| `R4_full_kv025_enf` | 14,445 | 0.115 | 0.799 | 0.924 | 0.987 | 0.188 | 1.015 | **2.072** | 4.656 | 3,714 | **0** |
| `R3_rung3_kv025` | 13,812 | 0.103 | 0.755 | 0.893 | 0.940 | 0.185 | 0.965 | **1.952** | 3.956 | 3,568 | **0** |
| `R4_pdonly_kv025` | 14,445 | 0.114 | 0.807 | 0.926 | 0.976 | 0.169 | 1.004 | **2.077** | 4.688 | 3,626 | **0** |
| `R4_rqonly_kv025` | 14,470 | 0.111 | 0.800 | 0.920 | 0.983 | 0.184 | 1.010 | **1.990** | 4.411 | 3,739 | **0** |
| `N1_harm0_kv025` | 14,523 | 0.117 | 0.806 | 0.937 | 0.979 | 0.173 | 1.006 | **2.087** | 4.822 | 3,652 | **0** |

**VERDICT: the 20 ms budget is met with room, at 16 devices, dry.** Worst p99 across all eleven
cells is **4.345 ms** (4.6x headroom) and worst single decision is **13.917 ms** (1.4x headroom).
**Zero** of **158,117** decisions exceeded 20 ms. The committed declaration this bears on is
`arms_v5full.py:8`'s "p99 < 20 ms at 32 devices"; these cells are at **16** devices, so they
support it under a weaker condition and do not establish it at 32.

Per-kind, where it is worth knowing which decision is expensive (`P1_state_uo_1x`, the only cell
with a rung-2 per-kind breakdown worth quoting): `release_piece` has median 2.699 ms and
p99 11.535 ms over 162 decisions, `state_action` median 1.397 / max 7.668 over 2,267, and
`release_monitor` median 0.925 over 11,296. So the tail is the piece releases and the state
actions, not the monitor stream.

**Check 3, distribution sanity.** No cell is a constant where a distribution is expected: 3,568 to
5,476 distinct values per cell over 13,812 to 14,523 decisions. The IQRs are 0.16 to 0.72 ms, so
the spread is real and comparable to the median.

**AND AN ARTEFACT SPREAD, FLAGGED RATHER THAN QUOTED.** The p99 column varies 1.95 to 4.35 ms
across cells, which looks like a policy-cost ranking and is not one. The off arm appears three
times - `R4off_1x`, `R4off_kv025`, `R4off_kv025_enf` - with **byte-identical decision logs**
(`dc686e63f9a313ec` / 14,523 all three) and p99 of **4.345, 2.571 and 1.968 ms**, a 2.2x spread
over *the same decisions*. The cells ran as the host emptied: the manifest records the 1-minute
load average at each cell's start falling from 12.5 to about 2. So **the between-cell latency
differences measure host contention, not policy work**, and under CLAUDE.md check 3 this column may
not be used to rank arms. The only claim it supports is the one made above - the budget is met,
with the worst case measured under the *worst* contention, which is the conservative direction.



### 3.9 DEFERRED-AND-EXPOSED, and the factor the arm actually plans with is NOT the gate's

**The observed count is NOT MEASURABLE in a dry cell, and no number is invented for it.** A
deferral is "exposed" when its realised first token overruns the safety factor, and that needs an
observed first token. A dry cell has no engine; `cf_request_defer` records predictions only, and
its records carry no post-hoc outcome. So:

> **observed deferred-and-exposed at 0.25x: NOT MEASURABLE (no engine, no observed first token).**
> **observed deferred-and-exposed in the compound at 0.25x: trivially 0, because there are 0
> deferrals (3.2, 3.6).**

What **is** computable is a constructed bound, and it is simple because the mechanism is: a
deferral is placed **at** the latest safe start, so it retains **zero** margin by construction and
its miss threshold is the safety factor itself. Every one of the six deferrals (the `-rqonly` cell
at 0.25x, which is byte-identical to the full arm at 1x) carries its own predicted service, so the
worst-case overrun in seconds is exact:

| # | t (s) | deferral used (s) | predicted total service (s) | miss threshold (ratio) | estimated exposure | **worst-case overrun (s)** |
|---|---|---|---|---|---|---|
| 1 | 542.9 | 1.006723 | 1.001163 | 1.8721 | 9.72 % | **1.497** |
| 2 | 677.4 | 1.067657 | 0.991049 | 1.8721 | 9.72 % | **1.482** |
| 3 | 743.5 | 0.439147 | 1.326239 | 1.8721 | 9.72 % | **1.983** |
| 4 | 747.1 | 0.375290 | 1.358747 | 1.8721 | 9.72 % | **2.031** |
| 5 | 935.0 | 0.601225 | 1.234857 | 1.8721 | 9.72 % | **1.846** |
| 6 | 935.5 | 0.610225 | 1.234857 | 1.8721 | 9.72 % | **1.846** |

Register: the exposure column is a **CONSTRUCTED BOUND** from the committed rung-3 ratio population
(n = 463 sent robot requests, seeds 4 to 7), **not an observed count**. Expected number exposed =
6 x 0.0972 = **0.58 deferrals**. The overrun column is the worst committed ratio minus the factor,
times that deferral's own predicted service: 1.48 to 2.03 **seconds**, against a 5.0 s robot
deadline, on requests that were deferred by 0.38 to 1.07 s. Slack used is a genuine distribution -
six distinct values, median 0.606 s, min 0.375, max 1.068 - not a constant.

**AND A DEFECT FOUND BY BUILDING THIS TABLE: THE ARM PLANS AT A DIFFERENT SAFETY FACTOR THAN THE
GATE AUDITS.** Every deferral records `safety_factor_used = 1.8721`. That is the **old, degenerate**
n = 5 factor - the one D206 (1) retired because its nearest-rank q90 **was** the maximum. The
replacement, 1.863404 on n = 463, exists only in `d200_gatea_safety.json`; the arm reads
`cf_request_defer.py:137` -> `d190_measured_safety.SAFETY_FACTOR` -> `INFO["safety_factor"]`, which
is still the old value. **D206 replaced the gate's input and never fed it back to the arm.**

This is CLAUDE.md's closing shape exactly - a comparator planning at one price while charged
another - so it is reported with its magnitude rather than as an alarm:

| threshold | exposure on the committed rung-3 population | worst overrun |
|---|---|---|
| 1.863404, the gate's q90 (what D206 reports) | 46 of 463 = **9.9352 %** | 1.503537x |
| **1.8721, what the arm actually plans with** | **45 of 463 = 9.7192 %** | 1.494841x |

**The magnitude is one request in 463 and 0.47 % on the factor, so nothing in the rung-4 result
turns on it, and the arm is the *more* conservative of the two.** But the direction of the fix
matters and is cheap: feed the n = 463 factor into `d190_measured_safety` so the arm plans at the
factor the gate audits. And it yields the way to make the exposure number informative, which
section 4 flags as a near-identity: evaluated at the population's **own** q90 the fraction is
pinned at 1 - 0.90 by construction, but evaluated at the factor **the arm uses** it is a real
measurement - on the `-rr` population against 1.8721 it is **36 of 463 = 7.7754 %**, not 9.9352 %.
**Report exposure at the arm's factor, not at the population's q90.**

### 3.10 STEP 2b: how many decisions changed, and the first one

Diffs computed with the **committed** `test_hybrid._differing_setwise` and `_differing`, imported
rather than restated. Rows are normalised to the digest row set first (`decision_latency_ms`
dropped, since it is wall clock and differs between runs of identical decisions), so a 0 here means
what it means in `d190_rung4_r3_proofs.json`.

| comparison | setwise | positional | first difference |
|---|---|---|---|
| **Step 2b, rung 4 vs its off arm, 1x** | **2,105** | 9,173 | index 5,350, t = 542.9 s: rung 4 emits `defer` where the off arm emits `release_recall` |
| **Step 2b, rung 4 vs its off arm, 0.25x** | **1,756** | 10,192 | index 4,331, t = 443.3 s: rung 4 emits `state_action` where the off arm emits `release_recall` |
| **Step 2b, rung 4 vs its off arm, 0.25x ENFORCED** | **1,756** | 10,192 | identical to the unenforced pair, index 4,331, t = 443.3 s |
| **BINDING: rung 4 at 1x vs 0.25x** | **1,051** | 9,602 | index 4,331, t = 443.3 s |
| **BINDING: rung 3 at 1x vs 0.25x** | **0** | **0** | **none - byte-identical** |
| rung 3 by name vs the off arm, both 0.25x | 1,741 | 9,009 | index 5,514, t = 559.4 s (the 711-row planner-weight contamination, 3.0 / 3.5) |
| enforcement channel, rung 3 (0.25x off vs on) | **0** | **0** | **none** |
| enforcement channel, rung 4 (0.25x off vs on) | **0** | **0** | **none** |
| leg: `-pdonly` vs off, 0.25x | 1,756 | 10,192 | index 4,331 - **identical to the full arm's pair** |
| leg: `-rqonly` vs off, 0.25x | 2,105 | 9,173 | index 5,350 - **identical to the full arm's pair at 1x** |
| **Step 4 control: `-harm0` vs off, 0.25x** | **0** | **0** | **none - collapses** |

Read down the table and the whole study is in it: **the switch moves decisions (2,105 at 1x, 1,756
at 0.25x), the memory setting moves them for rung 4 (1,051) and not at all for rung 3 (0),
enforcement moves nothing for either (0, 0), each leg alone reproduces the full arm's pair at one
of the two settings, and disabling the mechanism collapses to the bar (0).**

The first differences are also the right *kind* in each case, which is the check that the count is
not a reordering artefact: at 1x the first divergence is a `defer` replacing a `release_recall`
(the question-deferral leg), and at 0.25x it is a `state_action` replacing a `release_recall`
(protect-and-defer touching a victim instead of releasing). Those are the two mechanisms' own
signatures, in the setting each one owns.


### 3.11 D216 (1) LANDED MID-RUN AND DISALLOWS ONE OF MY BARS. The study does not depend on it.

D216 (1), committed while these cells were running, makes two rules standing on every box:

> any dry cell whose digest is used as a proof bar or a Step 2b baseline runs **ALONE** on its
> machine (no concurrent dry cells or proof chains), with loadavg recorded as a magnitude; an
> **unfixed rung-2 digest (qcache fix off) is never used as a bar** (a comment-only edit moved it
> by 85 decisions through `id(obs)` allocation).

**Rule two disallows my first positive control.** `P1_state_uo_1x` is `covex-v6-state-uo` with the
qcache fix off, used as a bar. Under D216 (1) that bar is no longer admissible - **even though it
passed exactly** (`9a4be873eb3c5fba` / 14,218, at host load 12.54). I am not keeping it as a pass.
It is **withdrawn as a bar** and retained only as a reproduction datum.

**The study does not depend on it**, which is why the control structure was built with five bars and
not one. The four that remain are **not** rung-2 digests:

| bar | result | is it a rung-2 digest? |
|---|---|---|
| `covex-v6-cf-c5attr` 1x = `f5b627392839527c` / 14,470 | PASS, exact | no - rung 4 |
| `covex-v6-fair-c5attr` = `12e4f73ce0ebd865` / 13,812, at **both** 1x and 0.25x | PASS, exact | no - rung 3 |
| the Gate A JSON reproduced byte-for-byte | PASS | no - not a cell |
| the 1x question-deferral counters 6 / 22 / 17 | PASS, exact | no - rung 4 counters |
| ~~`covex-v6-state-uo` 1x~~ | ~~PASS~~ **WITHDRAWN under D216 (1)** | **yes** |

**And rule two's hazard is wider than rung 2, which is worth saying plainly.** The `id(obs)`
allocation defect lives in `arms_v6state.V6StateArm._queued_behind`, and **rungs 3 and 4 inherit
it** - the final ladder's own `QCACHE_KEY_FIX_SWITCH` is off in every committed rung for exactly
that reason (D190 (6), D208 (2)). So if a comment-only edit can move a rung-2 digest by 85
decisions, rung 3's and rung 4's digests carry the same fragility, and D216 (1)'s prohibition is
arguably under-scoped as written. What I can offer against that is **evidence, not reassurance**:

| digest | runs agreeing | host load at start | concurrency |
|---|---|---|---|
| `12e4f73ce0ebd865` / 13,812 (rung 3) | **3** - committed bar, my 1x cell, my 0.25x cell | 2.27 and 1.88 | 1 and 2 |
| `f5b627392839527c` / 14,470 (rung 4) | **2** - committed bar, my 1x cell | about 12 | 1 |
| `dc686e63f9a313ec` / 14,523 (off arm) | **4** - my 1x, 0.25x, 0.25x-enforced, and `-harm0` | 12.5 down to about 2 | 1 |
| `cde9545ac1d383f3` / 14,445 (rung 4 at 0.25x) | **3** - full, full-enforced, `-pdonly` | about 2 | 1 |

Twelve agreements across a 6.6x range of host load. Under `--cutoff-off` these digests were stable
here; that is a measurement on this recipe and not a licence to ignore the rule.

**Rule one caught one cell of mine, and I re-ran it.** `R3_rung3_1x` - the uncontaminated rung-3 1x
bar added mid-run for section 3.0 - was launched before D216 landed and ran **concurrently** with
the counter-census cells of section 5.4. Its digest *is* used as a proof bar, so it violated rule
one as written. A bar that breaks the rule is not a bar, so it was discarded as a bar and re-run
**genuinely alone**, after the census and after a settling pause, with the load recorded at the
cell's start:

| run | host load at start | concurrency | digest | rows |
|---|---|---|---|---|
| `R3_rung3_1x` (first, non-compliant) | 1.88 | 2 (census running) | `12e4f73ce0ebd865` | 13,812 |
| **`R3_rung3_1x_ALONE` (compliant)** | **0.60** | **1, nothing else on the box** | **`12e4f73ce0ebd865`** | **13,812** |
| the committed bar | n/a | n/a | `12e4f73ce0ebd865` | 13,812 |

**Identical.** So nothing in this report changes, and the D216 (1)-compliant cell is the one cited
as the bar; the first run is kept in the manifest as the non-compliant attempt rather than deleted,
because a reader should be able to see that the rule was broken and what it cost (nothing, here).
A third attempt was started and **killed before it finished** when I noticed it had been gated on a
sentinel that fired early and was itself running beside two census cells; it produced no output and
is not in the manifest.

---

## 4. GATE A for the final rung, as exposure plus overrun magnitude (D206 (1))

Per D206 (1) the would-have-missed **count is retired** and is kept only as a labelled identity
column. The gate quantities are the **exposure** and the **overrun magnitude**.

Positive control on my own edit first: `d200_gatea_safety.py` was parameterised (`--cell-template`,
`--out`) and run with no flags reproduces the committed
`results/orchestration/live2/frozen_test/d200_gatea_safety.json` **byte-for-byte** (verified by
normalised JSON comparison). So the parameterisation is behaviour-neutral on the default path.

| quantity | committed rung 3 (`covex-v6-fair-c5attr`, seeds 4-7) | rung 3 + `-rr` (`covex-v6-fair-c5attr-rr`, seeds 4-7) | register |
|---|---|---|---|
| population | 463 sent robot requests, healthy window, 132/123/121/87 by seed, 0 non-healthy | **463**, identical per-seed split | COMMITTED cells |
| observed/predicted first token, min | 0.167154 | 0.514125 | measurement |
| median | 1.314313 | 1.251591 | measurement |
| **q90 = safety factor** | **1.863404** | **1.792192** | measurement, nearest rank, k = 417 |
| max | 3.366941 | 4.134563 | measurement |
| n distinct | 463 of 463 | 463 of 463 | distribution, not a constant |
| fraction above 1.0 | 0.835853 | 0.833693 | measurement |
| **EXPOSURE** | **46 of 463 = 9.9352 %** | **46 of 463 = 9.9352 %** | see the caveat below |
| **OVERRUN MAGNITUDE, worst** | **1.503537 x predicted service** | **2.342371 x predicted service** | measurement |
| would-have-missed count, at median bias | 0 of 1 | 0 of 1 | **IDENTITY COLUMN, retired** |
| would-have-missed count, at the q90 bias | 0 of 1 | 0 of 1 | **IDENTITY BY DESIGN** (bias = factor, overrun identically 0) |
| would-have-missed count, at max bias | 1 of 1 | 1 of 1 | **IDENTITY of the opposite sign** |

Why the identity column is kept rather than deleted: `overrun = (b - SAFETY_FACTOR) x service`
has the sign of `(b - SAFETY_FACTOR)` alone because service is positive, so the count is 0 below
the factor, 0 **at** it and N above it, for any N. The old committed "0 of 6" was an identity
because the n = 5 nearest-rank q90 **equalled** the maximum. A reader who sees only that the
column went cannot tell that from a measurement that happened to be zero.

**A SECOND, SOFTER IDENTITY, WHICH I AM FLAGGING BECAUSE IT IS NOT MARKED IN THE COMMITTED FILE.**
The **exposure fraction** is 9.9352 % in *both* columns, to four decimal places, and it is the same
in both because it is **near-identity by construction**: the exposure counts rows strictly above
the *q90 of the same population*, so it is pinned at 1 - 0.90 by the nearest-rank rule
(463 - 417 = 46). It is a measurement in exactly one respect, and that respect is worth the gate:
it establishes the quantile is **non-degenerate**, where the old n = 5 input gave 0 rows above its
own q90. The quantity that carries risk information across the two inputs is the **overrun
magnitude**, and it is the one that moved - and moved **the wrong way**, 1.5035x to 2.3424x, when
`-rr` joined rung 3 under D208 (1). The informative column is the magnitude; read the fraction as
a non-degeneracy check, not as a risk estimate that distinguishes the two arms.

**AND THE GATE AUDITS A THRESHOLD THE ARM DOES NOT USE.** Found by building section 3.9's
per-deferral table: every deferral records `safety_factor_used = 1.8721`, the **retired** n = 5
factor, because the arm reads `cf_request_defer.py:137` -> `d190_measured_safety.SAFETY_FACTOR` and
D206 (1) replaced the gate's input without feeding it back there. Magnitude, so the finding is not
inflated: **one request in 463** and 0.47 % on the factor, and the arm is the *more* conservative
side, so no rung-4 result turns on it. Both columns, for the record:

| threshold | exposure on the committed rung-3 population | worst overrun |
|---|---|---|
| 1.863404 - the gate's q90, what D206 reports | 46 of 463 = 9.9352 % | 1.503537x |
| **1.8721 - what the arm actually plans with** | **45 of 463 = 9.7192 %** | 1.494841x |

This also shows how to make the exposure number informative rather than near-identical: evaluated
at the population's **own** q90 it is pinned at 1 - 0.90 by the nearest-rank rule, but evaluated at
the factor the **arm** uses it is a genuine measurement - on the `-rr` population against 1.8721 it
is **36 of 463 = 7.7754 %** with worst overrun 2.262463x, not 9.9352 %. **Recommendation: report
exposure at the arm's factor, and feed the n = 463 factor into `d190_measured_safety` so the two
are the same number.**

**GATE A FOR THE FINAL RUNG IS NOT COMPUTABLE AND IS NOT REPORTED AS IF IT WERE.** The final rungs
are now named (`covex-v6-state-final`, `covex-v6-fair-final`, `covex-v6-final`) and have **no
cells**, so the input population does not exist. The `-rr` column above is the nearest committed
ancestor of the final rung 3 and is offered as that, not as the final rung's gate. When the final
rung 3's cells land, re-run:

```
d200_gatea_safety.py --cell-template "covex-v6-fair-final_n16_s%d_1200s_h27_3t_L3_epg_rq30" \
                     --out results/orchestration/live2/<dir>/gatea_final.json
```

and note that the factor **will** move again, because `TOUCH_PRICE_MODE` changes the queueing the
ratios are measured through.

---

## 5. The inheritance table (D200 (4)), against the CURRENTLY COMMITTED rung 3

D200 (4): every rung is built on the rung below and must inherit every mechanism that rung
adopted; each build lists the lower rung's adopted mechanisms and shows each is live in the new
rung. The brief adds: a **file:line** *and* a **NON-ZERO DRY COUNTER** for each, and report
anything missing rather than silently adding it.

**What this table is built against, and why.** The final rungs are named
(`covex-v6-state-final`, `covex-v6-fair-final`, `covex-v6-final`) but **not built**, so the table
below is built against the **currently committed rung 3**, `covex-v6-fair-c5attr` plus `-rr`.
The "re-point" column marks every row that must be re-pointed at the final rung once it exists;
rows marked **RE-POINT** are the ones where the final rung 3 differs from the committed one, per
D208 (2).

### 5.1 Mechanisms rung 4 inherits, with the read site

| # | mechanism (rung it was adopted at) | declared by | **the READ that changes a decision** | dry counter | re-point? |
|---|---|---|---|---|---|
| M1 | hybrid-F rules base (rung 0) | `covex-v6-base` = `hybrid-F-lhreq-noc3` | `hybrid/hybrid_arm.py` decide path | `decisions` | no |
| M2 | chunked just-in-time warming + saturation guard (rung 1) | `V5Rules2Arm` | `arms_v5rules2.py` decide path | `pieces` / `state_skipped_rules_acting` | no |
| M3 | per-type host retention, `max_offload_tokens = 0` for alert and single-shot (rung 2) | `live2_offload_controls` | `coordinator.py:267` reads the switch, `coordinator.py:1517` sets `kv_transfer_params` from it | **see 5.2: effect is an ENGINE request parameter, so a DRY cell cannot show it changing an outcome** | no |
| M4 | TOUCH chosen by `plan_state`, not by a rule (rung 2) | `live2_touch_requests` | `touch_policy.py:151` arm gate, `coordinator.py:1161` `TP.should_touch(...)` | `state_touch_emitted` | no |
| M5 | residency belief corrected from engine telemetry incl. host hits (rung 2) | `live2_belief_apply` | `coordinator.py:365` | residency log / belief counters | no |
| M6 | state-based D162 pricing (rung 2) | `live2_state_priced_costs`, `live2_d162_pricing` | `touch_policy.py:192`, `d162_price.py:178` | `harm_warm_priced`, `harm_warm_nonzero` | **RE-POINT - `TOUCH_PRICE_MODE` (Session A) changes this price** |
| M7 | uncached-only budget charge mode (rung 2, D174 (1)) | `live2_charge_mode = "uo"` | `d162_price.py:170` | budget charge totals | no |
| M8 | `plan_state` as the state decision (rung 2) | `V6StateArm` | `arms_v6state.py:433` records it; the candidate chosen alters the emitted action | `state_decisions`, `state_deviations` | **RE-POINT - D206 (2): the state planner reads `deficit_feed` in the final ladder** |
| M9 | C5 attribution rule (rung 2, the `-c5attr` suffix) | `c5_attr_self_released = True`, `arms_v6c5.py:57` | `hybrid/hybrid_arm.py:727` `_attr_suppresses()` gating the AIMD decrease | `c5_attr_suppressed_decrease`, `c5_attr_slow_mixed`, `c5_dash_held` | no |
| M10 | D170 / D175 over-limit rule, on at every covex-v6 rung incl. the base | `over_limit_infeasible=True` | `arms_v6state.py:148` / `:153` constructor, rule in the rules arm | `over_limit_infeasible` | no |
| M11 | per-device deficit feed, ORDERING consumer (rung 3, D178 (2) / D182) | `live2_deficit_feed` | `hybrid/hybrid_arm.py:399, 483, 486` - the LEADING sort key, bound on the core instance at `arms_v6fairfeed.py:191` | `deficit_feed`, `deficit_feed_completions` | **RE-POINT - final rung 3 adds the state-planner consumer (D206 (2))** |
| M12 | deficit feed, FLEXIBLE-SPLIT consumer (rung 3) | `live2_share_weights()` | wired: `coordinator.py:1616` reads the accessor and `:1620` passes `weights_by_type` - but `coordinator.py:1602` returns from `_share_ok` first on this base | - | **UNEXPRESSIBLE on the c5attr base, not missing** |
| M13 | alert release re-check (joins rung 3 under D208 (1)) | `live2_release_recheck`, `release_recheck.py:65` | `release_recheck.decide` via the arm; `coordinator.py:317` requires `live2_d162_pricing` with it | release-recheck counters | **RE-POINT - in the committed rung-3 arm this is `-rr` only; D208 (1) puts it IN rung 3** |
| M14 | `id(obs)` cache-key fix | - | `arms_v6state.V6StateArm._queued_behind` | - | **MISSING from the committed rungs by design (D190 (6)): applied at the final-ladder rerun** |

### 5.2 The three entries that are NOT a clean pass, said here rather than left to be found

- **M12 is `unexpressible`, and the reason is NOT the one the code's own docstring still gives.**
  `arms_v6fairfeed.py:57` says the coordinator "calls `SA.allowed(...)` WITHOUT `weights_by_type`"
  and that "until that line lands, this feed is Rule 2's UNEXPRESSIBLE". **That line has landed.**
  `coordinator.py:1616` reads `live2_share_weights` and `:1620` passes `weights_by_type=_wbt`,
  with its own comment recording that the argument used to be the absent link. The feed's
  flexible-split consumer is nevertheless still unreachable on this base, for a **different**
  reason one level up: `_share_ok` returns `True` at `coordinator.py:1602` when the arm declares no
  share admission, and the c5attr rung-2 base declares none, so the whole gate - the weights read
  included - is skipped. `arms_final_ladder.py`'s docstring states this correctly ("ABSENT BY
  CONSTRUCTION on this base"), so the stale sentence is in `arms_v6fairfeed.py` alone.
  **Reported, not fixed:** `arms_v6fairfeed.py` is not mine, and the defect is a docstring that
  names a retired cause, which would make a future reader add a line that is already there.
  Rung 3's contribution on this base is the **ordering** consumer alone (M11), which does fire.
- **M3 has a read but no dry evidence.** `coordinator.py:1517` genuinely consumes the switch, but
  what it sets is `kv_transfer_params` on the **engine request body**. A dry cell has no engine, so
  the honest dry statement is "the parameter is set", not "the retention changed an outcome". Its
  non-zero evidence has to come from a live cell, and I am not claiming a dry counter for it.
- **M14 is deliberately absent** from every committed rung (D190 (6)) and is scheduled for the
  final-ladder rerun. Flagged because it is a known decision-affecting defect
  (`obs.epoch` is a string, so the cache key is a reused memory address), not because it is new.

### 5.3 What the final rung 3 will differ by, so the re-point is mechanical

Per D208 (2), final rung 3 = final rung 2 (`covex-v6-state-final`, = rung 2 + the `id(obs)` fix)
+ per-device deficit feed with D185 ordering + **state planner reading `deficit_feed`** (D206 (2))
+ **alert release re-check**. So rows **M6, M8, M11, M13, M14** are the re-point set, and
`covex-v6-final` must show each of them live with its own non-zero counter. The counters in 5.1
come from the committed arms and are **not** transferable to the final rung: they must be
re-measured on the final commit.


### 5.4 THE DRY COUNTERS, MEASURED - and two inherited mechanisms have NONE

A full counter census was run (`d210_inheritance_counters.py`, one dry cell per process, no digest
claim) because `cf_pd_one_cell` reports a fixed 22-key subset and leaves most of rung 2's and
rung 3's own counters unreported. On `covex-v6-cf-c5attr` at 0.25x, 103 counter keys, 60,941 state
decisions:

| # | mechanism | dry counter | value | verdict |
|---|---|---|---|---|
| M1 | hybrid-F rules base | `submitted_monitor` / `_piece` / `_recall` | 10,831 / 158 / 460 | **LIVE** |
| M2 | chunked JIT warming + guard | `state_skipped_rules_acting`, `submitted_piece` | 158 pieces; `state_deferred_to_guard_epochs` 1,043 | **LIVE** |
| M3 | per-type host retention | - | **no counter exists** | **read is live (`coordinator.py:267` -> `:1517`) but its effect is an ENGINE request parameter; a dry cell cannot evidence it.** Reported, not claimed |
| M4 | TOUCH chosen by `plan_state` | `state_touch_emitted`, `state_chosen_TOUCH` | **2,928 / 2,928** | **LIVE** |
| M5 | belief corrected from telemetry | - | **no counter, and no telemetry dry** | **unexercised dry by construction**; D211 is the live-side finding |
| M6 | state-based D162 pricing | `harm_warm_priced`, `harm_warm_nonzero`, `harm_warm_capped` | **2,404 / 1,696 / 2** | **LIVE** (and D216 says the touch-price fix does not move it) |
| M7 | uncached-only charge mode | `cf_budget_ms` 20.0, budget totals | present | **LIVE** |
| M8 | `plan_state` state decision | `state_decisions`, `state_deviations`, `state_chosen_*` | **60,941 / 2,934**; KEEP 58,007 TOUCH 2,928 WARM 6 | **LIVE** |
| M9 | **C5 attribution rule (the `-c5attr` suffix)** | `c5_attr_*`, `c5_dash_held` | **ALL ABSENT = 0** | **ZERO. See below.** |
| M10 | D170 / D175 over-limit rule | `over_limit_infeasible` | **ABSENT = 0** | **ZERO, and EXPECTED at this seed** - the 18 over-32k questions are all at s7 (D176 (3)), so seed 4 cannot exercise it |
| M11 | deficit feed, ORDERING consumer | `deficit_feed_completions`, `order_key_resolved`, per-device weights | **11,441 completions, 12,046 offers, 71,805 order keys resolved; weights 1.000 to 2.704 across 16 devices** | **LIVE, and non-constant** |
| M12 | deficit feed, FLEXIBLE-SPLIT consumer | `weights_by_type_pending` | **`None`** | **UNEXPRESSIBLE on this base** (5.2) |
| M13 | alert release re-check | `release_infeasible_alert` | **1,869** on the `-rr` census cell (absent on rung 3 and on rung 4, as expected: `-rr` is a separate committed arm) | **LIVE on `-rr`**, which is the arm D208 (1) folds into rung 3 |
| M14 | `id(obs)` cache-key fix | - | off by design | **absent by design** (D190 (6)), applied at the final-ladder rerun |

**M9 IS THE ONE THAT MATTERS, AND IT IS AN ESCALATION.** `-c5attr` is the suffix that **names
rung 2**, the whole ladder is built on `covex-v6-state-uo-c5attr`, and on this cell its counters are
**all zero**: no `c5_attr_suppressed_decrease`, no `c5_attr_slow_mixed`, no
`c5_attr_trip_without_slow_evidence`, and `c5_dash_held` absent too, so C5's holding path never
executed either. The switch is **on** - the arm's own describe reports `c5: true`, and
`arms_v6c5.py:57` sets `c5_attr_self_released = True` - so this is a live, declared, reachable
mechanism that **no condition in this cell reaches**: Rule 2 **unexercised**.

**It is independently corroborated by a committed digest collision I noticed before running the
census**, which is why I believe it rather than suspect an instrumentation gap: StudyD200-WEIGHT's
F3 cells record `covex-v6-state-uo` and `covex-v6-state-uo-c5attr` with **the same digest**,
`9a4be873eb3c5fba` / 14,218. If the c5attr rule changed a decision at seed 4, those two could not
be byte-identical. **The rung-2 base and the rung-2 base plus c5attr are the same arm on this
cell.** Two routes, one conclusion, as in 3.4.

That does not make rung 2 wrong - the c5attr rule was adopted on evidence from other seeds and
other conditions, and D184/D179 own that decision. What it does mean is narrower and should be
stated wherever a seed-4 ladder comparison is quoted: **at seed 4, the `-c5attr` in the rung-2 name
contributes nothing**, so a seed-4 rung-2-versus-rung-1 comparison does not test it, and the
ladder's seed-4 numbers cannot be used to attribute anything to C5 attribution. Per D200 (4) I am
**reporting this rather than adding or changing anything**.

**M3, M5, M10 and M14 have no non-zero dry counter either, and each is reported with its own
reason** rather than lumped with M9: M3's effect is an engine parameter a dry cell cannot see,
M5 needs telemetry that does not exist dry, M10's triggering condition is absent at seed 4 by
D176 (3), and M14 is off by design until the final-ladder rerun. **Only M9 is a mechanism that
could have fired at this seed and did not.** M9's zero is also consistent across all three census
arms - rung 3, rung 3 + `-rr` and rung 4 - so it is a property of the cell, not of one arm.

**AND THE CENSUS CONFIRMS THE 711-ROW CONTAMINATION AT THE MECHANISM LEVEL, which is the last thing
section 3.0 needed.** The three census cells put rung 3 and rung 4 side by side on the state
planner:

| | rung 3 (`covex-v6-fair-c5attr`) | rung 4 (`covex-v6-cf-c5attr`) | delta |
|---|---|---|---|
| `state_decisions` | 60,934 | 60,941 | +7 |
| `state_deviations` | **2,272** | **2,934** | **+662** |
| `state_touch_emitted` | **2,267** | **2,928** | **+661** |

The rung-4 family's unconditional planner-weight swap (`arms_v6cfr3.py:320-348`) raises the state
planner's deviations by **662** and its emitted touches by **661**, against the **+711 decision
rows** the off arm carries over rung 3. The two numbers are the same effect counted two ways - a
deviation that emits a TOUCH adds a decision row - so the contamination is not merely the right
*size*, it is the right *mechanism*, and it is a deficit-weighted state planner producing more
touches. That closes the loop opened in 3.0 without needing a fourth comparison.

---

## 6. Results consistency check (CLAUDE.md), recorded before the conclusions

### Check 1 - cross-check against committed measurements

| quantity | this run | prior committed | source of prior | ratio | verdict |
|---|---|---|---|---|---|
| `covex-v6-state-uo` dry digest / rows, 1x | `9a4be873eb3c5fba` / 14,218 | `9a4be873eb3c5fba` / 14,218 | `frozen_test/c5attr_digest_proofs.json` P1 | 1.000 | agreed exactly, but **WITHDRAWN AS A BAR** under D216 (1): an unfixed rung-2 digest is never a bar. Kept as a reproduction datum only (3.11) |
| Gate A safety factor q90 | 1.863404 | 1.863404 | `frozen_test/d200_gatea_safety.json` | 1.000 | **AGREE, exact** (byte-identical file reproduced) |
| Gate A exposure | 46 of 463 | 46 of 463 | same | 1.000 | **AGREE, exact** |
| question-deferral leg at 1x: deferrals / harm-reached / distinct bar values | 6 / 22 / 17 | 6 / 22 / 17 | `d190_rung4_r3_proofs.json` Gate A item 1 and `is_the_deficit_weight_live` | 1.000 | **AGREE, exact** - so D206's digest movement is in the PLANNER LIMB, not in the legs |
| rung-4 digest at 1x | **`f5b627392839527c` / 14,470 - exact** | `f5b627392839527c` / 14,470 at `0ca54444` (post-D206); `048ec39ecc144321` / 13,773 as previously committed | D206 handoff / `d190_rung4_r3_proofs.json` | 1.000 | **AGREE, exact** against the post-D206 bar. Still **PROVISIONAL** forward: `TOUCH_PRICE_MODE` will move it (D209 (1)) |
| rung-3 digest, committed at 1x vs **this run at 0.25x** | **`12e4f73ce0ebd865` / 13,812 - exact** | `12e4f73ce0ebd865` / 13,812 (at `ec2d6a83` and re-measured at `1f5cf80e`) | `d190_rung4_r3_proofs.json` proof 3; StudyD200-WEIGHT F3 | 1.000 | **AGREE, exact** - and it is the blindness result (3.5): a quarter pool, zero rows of difference |
| protect-and-defer characteristic decisions at 0.25x | *(3.1)* | 5 state defers, 2 chunks, 16 request defers (pre-D206, `-pdonly`) | `d190_rung4_r3_proofs.json` `port_rule_characteristic_decisions` | *(3.1)* | the D206 deficit-weight fix is **expected** to move these; a difference is the fix, not a disagreement |

The load-bearing rows are the **rung-4** and **rung-3** reproductions, not the rung-2 one. Both
passed exactly, which establishes that the clean checkout is right and that the latency-keeping
patch in `d210_kv025_one_cell.py` is **digest-neutral** - the thing it had to prove before any of
its latency numbers could be read. The rung-2 control also passed, at host load 12.54, but D216 (1)
landed mid-run and disallows an unfixed rung-2 digest as a bar, so it is withdrawn rather than
counted; section 3.11 records that and shows the study does not rest on it.

### Check 4 - definition audit

| object | definition used in this run | matches prior? |
|---|---|---|
| the 0.25x memory setting | `test_live2_coord.GPU_KV` x 0.25 = **15,736 logical tokens**, applied identically to both sides of every comparison | yes: 62,944 / 4 exactly, the same number the frozen-grid driver maps `_kv0.25` to (`study_frozen_grid_driver_v28.sh:85`) and `kv025_runnability_probe.json` uses |
| a "cell" | one dry run, one process, seed 4, 16 devices, 1,200 s, posted knobs (40:40:20, lh_req, ss2, epg, per-frame, reask 30 s), planner wall-clock cutoff patched off | yes, read **from** `cf_pd_one_cell.POSTED` rather than restated |
| the digest | `sha256(json.dumps(rows without arm_version, sort_keys=True, separators=(',',':'), default=float))[:16]` over `test_hybrid.dry`'s rows | yes, and proved by the positive control rather than asserted |
| a "characteristic decision" | `pd_state_defers` + `pd_state_chunks` + `pd_request_defers` + `pd_protects` + `rd_question_defers` | yes, the same five counters `d190_rung4_r3_proofs.port_rule_characteristic_decisions` sums |
| "exposure" | fraction of **sent** recall requests whose observed/predicted first token exceeds the q90 safety factor | yes, `d200_gatea_safety.py`, unchanged |
| decision latency | `coordinator.py:2127`, flash CPU wall clock per decision row | **new to a dry cell**: `test_hybrid.STRIP` normally discards it, so no prior dry value exists to compare against |

### Check 5 - claim linkage

| headline | claim it bears on | supports / weakens / silent |
|---|---|---|
| rungs 0 to 3 cannot observe GPU-KV capacity | D56 (capacities are inputs), D26 (tier assignment under bounded capacity), and the memory-pressure arm of the D209 (4) run order | **weakens** the readability of any 0.25x result for those rungs; it does not weaken the policy claim, because the mechanism was never tested |
| rung 4's protect-and-defer reaches its gate only at 0.25x | D190 (3) / D191 (1): protect-and-defer is a **memory-pressure** finding if it fires only there | **supports**, conditional on section 3's counts |
| Gate A exposure 9.94 % and worst overrun 1.5035x | D206 (1), and the latest-safe-start arithmetic in `cf_request_defer` | **supports** that the deferral carries measurable risk; the exposure **fraction** is near-identity and only the magnitude discriminates |
| decision latency p99 against 20 ms | D151 (5) / `arms_v5full.py:8`'s declared "p99 < 20 ms at 32 devices" | **supports** at 16 devices, dry, on flash CPU - a weaker condition than the declaration, and labelled as such |

Nothing measured here maps to a FORMULATION §Scoping exclusion: the 0.25x setting is spec v6
section 10's **pre-registered** memory sweep (1x, 0.5x, 0.25x), not an invented instrument, and no
KV is moved between tiers running different-sized models.

### Check 6 - proxy validity

| signal | used as a proxy for | what it actually measures | valid for the claim? |
|---|---|---|---|
| `obs.cloud.gpu_kv_fraction` | engine KV occupancy | **nothing on this build**: 0.0 dry (no server) and 0.0 live (`cstate.py:663` key-name defect) | **NO.** Marked CONSTANT in Step 2; the free-KV gate runs on the residency belief alone, and that is what section 3's result is about |
| residency belief x `built_tokens_by_session` | GPU KV occupancy | the coordinator's believed-GPU set times how much of each history was built - and it **omits alert episode contexts**, which occupy the same pool | **partially**: understated by construction, declared in `arms_v6cf._pd_free_kv`'s own docstring. It is the pessimistic direction for *letting a rebuild through*, which is the safe direction for this gate |
| `decision_latency_ms` in a **dry** cell | the live decision budget | flash CPU wall clock with no engine in the loop and under foreign host load | **as a floor only.** A live decision does strictly more work; this is reported as a dry floor, not as the live p99 |
| the committed rung-3 ratio population | a deferral's realised overrun | observed/predicted first token on **sent** requests of a different arm's cells | **constructed, not observed** - section 3.5 labels the deferred-and-exposed estimate accordingly |

### Check 7 - validate the control, not only the result

Two positive controls and one negative control, none of them arm-versus-arm:

1. **`covex-v6-state-uo` at 1x must reproduce its committed digest.** It did, exactly. A failure
   would have meant the **check** was broken, not the arm.
2. **`d200_gatea_safety.py` with no flags must reproduce the committed JSON byte-for-byte.** It
   did. This audits my own edit to the gate rather than the gate's result.
3. **`covex-v6-cf-c5attr-harm0` at 0.25x must collapse to the off arm at 0.25x** (section 3.6).
   The **comparator** in every Step 2b pair is the off arm at the **same** memory and **same**
   enforcement setting, so neither side of any comparison is left unaudited.

---

## 7. The commit these cells were measured at, and what transfers

**Measured at `2856152b`** (`origin/main` when the clean `git archive` export was taken), on a
clean export and not in the shared worktree. The local worktree was 1,300 commits behind
`origin/main` at session start and was not used for any measurement.

**Origin moved under this run, twice, and one of the moves touched rung 4's own module.** At
`1235b070`, `arms_v6cfr3.py` lost 97 lines: `PlannerDeficitWeights` and `DeficitSourceNeverFed`
**moved** to the new `planner_deficit_weights.py` and are re-exported under their original names.
I diffed the class body across the two commits: the only differences are **docstrings and
exception message text**, the executable logic is identical, and the new `wire_planner` helper
has **no caller in `arms_v6cfr3`** (checked). So `covex-v6-cf-c5attr` decides identically at
`2856152b` and `1235b070`, and the cells below are valid at both. Recorded rather than assumed,
because a refactor of the module under test during the run is exactly the Step 0 hazard.

### What transfers to the final ladder, and what does not

| | transfers to `covex-v6-final`? |
|---|---|
| the capacity-blindness finding (section 1) | **YES, and it gets worse**: the final ladder adds no capacity read, so final rungs 2 and 3 are blind too |
| the channel analysis - arm observation vs coordinator eviction | **YES**, it is structural |
| the register distinction logical vs real-engine | **YES** |
| Gate A's method and the identity columns | **YES**; the **input** must be re-derived from the final rung-3 cells |
| the inheritance table's structure and file:line citations | **YES**, with the re-point set of section 5.3 |
| **the counts, digests and latency numbers of section 3** | **NO.** `covex-v6-final` differs from `covex-v6-cf-c5attr` by the `id(obs)` cache-key fix, the state planner reading the deficit feed, and the alert release re-check - all three change decisions. **The 0.25x dry proof must be re-run on `covex-v6-final` before any 0.25x cell of the final rung is posted.** This report proves the committed rung 4, which is what it was asked to prove; it does not pre-clear the final rung. |

### Status check on every result cited here (CLAUDE.md "Citing results")

- `research/EXPERIMENTS.md` at `1235b070` grepped for `INVALID`: the two hits are
  "INVALID AS A TAIL COST" (StudyLIVE2-coord, a different sense of the word) and an instruction
  ("check INVALID/HOLDOUT cells", StudyTABLE1). **No row marks `covex-v6-cf-c5attr`,
  `covex-v6-fair-c5attr`, `covex-v6-fair-c5attr-rr`, `covex-v6-state-uo`,
  `covex-v6-state-uo-c5attr` or `covex-v6-base` INVALID.**
- `d201_superseded_cells.json` (the D205 step-1 supersession of seven score-reading arms) parsed
  rather than grepped: it contains **four** occurrences of "covex" and all four are the
  `covex_harden` directory and `study_covex_hardening.md`. **No covex arm cell is on that list.**
  The seven superseded arms (`inar-vl`, `hybrid-llm`, `routellm`, `confidence-cascade`,
  `thinking-qwenvl-atdm`, `uniscale`, `B4-query-type-routing`) are none of the arms here.
- Every arm-versus-arm comparison in this report is the **same input, same stack, same decoding**:
  one commit, one workload, one seed, one recipe, and the only declared differences are the switch
  under test and the memory or enforcement setting, each named per pair.

---

## 8. Proposed row text (research/*.md is the user's; nothing below is applied)

### 8.1 Proposed `research/policy_design_log.md` row

> **D211 | 2026-11-23 | OUR OWN LADDER IS BLIND TO GPU-KV CAPACITY, AND THE FINAL LADDER INHERITS
> IT.** (1) Verified by Session D on a runtime trace of the delegation chain, not inherited from
> the triage: `live2_configure(gpu_kv_tokens=...)` reaches every covex-v6 arm only as
> `B7EdfFeasibilityArm._caps` (`arms.py:82`), which has exactly ONE occurrence repo-wide and it is
> the write. `covex-v6-base`, `covex-v6-rules`, rung 2 and rung 3 (with and without `-rr`) are
> therefore BLIND, in CLAUDE.md Step 2's ABSENT sense. `arms_final_ladder.py` adds no capacity read,
> so `covex-v6-state-final` and `covex-v6-fair-final` are blind too. The ONE exception is rung 4's
> protect-and-defer leg, which reads the pool at `arms_v6cf.py:302` and consumes it at `:336`;
> rung 4's question-deferral leg is capacity-independent by construction (`cf_request_defer` has no
> pool gate). (2) CONSEQUENCE: a flat 0.25x-versus-1x DECISION response from rungs 0 to 3 is Rule 2
> `unexercised` and not a finding about the policy; their OUTCOME response at the real engine is
> real but comes from the engine and from `cstate.py:520` enforcement, not from the policy. So the
> rung-4-over-rung-3 comparison at 0.25x is ASYMMETRIC and carries a first-order alternative
> explanation. (3) The INDEX row for `kv025_runnability_probe.json` is CORRECTED: it attributes a
> decision-path capacity read to `covex-v6-base` and `covex-v6-rules` via `policy/rollout.py:411`
> and `policy/coordinator.py:569`; those belong to `policy-core`, and `sw["c6"]` is False on every
> covex-v6 arm. D209 (6)'s exemption of those two arms from hit 14 reaches the right conclusion by
> the opposite reason. (4) NO FIX APPLIED: a never-read field needs a consumer, and choosing the
> consuming decision is policy design, not plumbing. Three options are costed in
> `reports/study_d210_kv025_dry.md` section 1.6 and a ruling is owed BEFORE the frozen final ladder
> runs, because option C (add capacity at the final ladder, where the rungs are rebuilt anyway) is
> the only one that costs no extra cells and its window closes when StudyLADDER-FINAL runs.
> (5) `arms_v6fairfeed.py:57`'s docstring names a RETIRED cause for the flexible-split consumer
> being unexpressible (the `weights_by_type` argument landed; `coordinator.py:1616`/`:1620`); the
> live reason is `_share_ok` returning at `coordinator.py:1602` on a base with no share admission.

### 8.2 Proposed `research/EXPERIMENTS.md` row

The live2 policy series uses Study-ids in the first column (`StudyD200-WEIGHT`, `StudyLADDER-FINAL`,
...), not E-ids, and those rows carry "E-id PROPOSED, NOT YET CONFIRMED" in their verdict. **There
is no E-id for this series and I have not minted one**; I propose the row below in the same shape
and leave the id to the user.

> **StudyD210-KV025 | orchestration | The 0.25x dry report for the committed rung 4
> (`covex-v6-cf-c5attr`) under D209 (4) / D210, and the capacity-blindness audit the user ordered
> mid-task. | `experiments/orchestration/live2/d210_kv025_one_cell.py`, `d210_kv025_driver.py`,
> `d210_inheritance_counters.py`, `d210_kv025_report.py`, and `d200_gatea_safety.py`
> (parameterised, default path proved byte-identical) | clean `git archive` of `2856152b`, fmtk,
> posted knobs, cutoff patched off, one dry cell per process, concurrency 1 from this session |
> `results/orchestration/live2/d210_rung4_kv025/` (12 cells, `manifest.json`,
> `d210_kv025_report.json`, `gatea_default_reproduction.json`, `gatea_rr_addendum.json`,
> `inherit_*.json`); `reports/study_d210_kv025_dry.md` | flash (CPU only, dry; no engine, no
> server) | 12 dry cells at 16 devices, seed 4, 1,200 s; 158,117 decisions | **PASS on the arm,
> with four defects reported and none fixed.** FIVE committed bars reproduced EXACTLY as positive
> controls (`covex-v6-state-uo` 9a4be873eb3c5fba/14,218; **rung 4 itself** f5b627392839527c/14,470;
> **rung 3 at 0.25x** 12e4f73ce0ebd865/13,812; the Gate A JSON byte-identical; the 1x
> question-deferral counters 6/22/17), at host loads from 2.3 to 12.5, so the recipe is
> load-insensitive and no digest carries a load caveat. **0.25x BINDS FOR RUNG 4 AND FOR NOTHING
> BELOW IT**: rung 4 moves 1,051 decisions between 1x and 0.25x with 42 characteristic decisions
> (19 protects, 16 request deferrals, 5 state deferrals, 2 chunks) and Step 4 collapsing all of it
> to the bar; rung 3 at 0.25x is BYTE-IDENTICAL to its committed 1x digest, 0 of 13,812 rows,
> because `arms.py:82 self._caps` is write-only repo-wide and NO covex-v6 arm below rung 4 reads
> capacity - Rule 2 UNEXERCISED, not an equivalence, and the FINAL ladder adds no read either.
> Enforcement moved 39-48k tokens to host and cut over-cap epochs 10,934 -> 14 while changing ZERO
> decisions for BOTH arms, so both of the pool's paths to a dry decision are absent and what makes
> a live cell non-null is a re-prefill COST the dry sim cannot price. Rung 4's free-KV estimate is
> SIZE-sensitive and OCCUPANCY-blind (261 of 261 estimates belief-bound; byte-identical with and
> without enforcement). THE LEGS SWAP AND ARE NOT ADDITIVE: at 1x full == `-rqonly` (PD contributes
> 0), at 0.25x full == `-pdonly` and the six question deferrals are LOST to PD's 16 request
> deferrals. Decision latency p99 worst 4.345 ms, max 13.917 ms, 0 of 158,117 over the 20 ms budget,
> no constants (3,568-5,476 distinct per cell); the between-cell spread is host contention and may
> not rank arms. GATE A as D206 (1): exposure 46 of 463 = 9.94 %, worst overrun 1.5035x, with the
> retired count kept as a labelled identity column, plus an `-rr` addendum (q90 1.792192, worst
> overrun 2.3424x). FOUR DEFECTS REPORTED, NOT FIXED: `_caps` write-only for OUR ladder;
> `covex-v6-cf-c5attr-off` is NOT the rung-3 bar its own module requires (contamination pinned at
> exactly +711 rows from `_cf_engine`'s unconditional planner-weight swap); `arms_v6fairfeed.py:57`
> names a retired cause; and the arm plans at the RETIRED safety factor 1.8721 while Gate A audits
> 1.863404 (one request in 463). | E-id PROPOSED, NOT YET CONFIRMED. Pushed as the commit that adds this report (`git log --oneline -1 -- reports/study_d210_kv025_dry.md`). Counts do NOT
> transfer to `covex-v6-final`; re-run before any final-rung 0.25x cell. | Five committed bars at
> two load regimes are the check-7 instrument: an instrument that reproduces five and disagrees with
> a sixth by 711 rows is not broken, the sixth bar stopped applying. | Step 2b run before scoring,
> each leg separately, at both memory AND both enforcement settings; Step 4 control collapses to 0;
> the `--enforce-kv` switch is read back off `CoordState` because the first version set a dataclass
> class attribute and never reached the instance. | PROVISIONAL on Session A's `TOUCH_PRICE_MODE`
> (will move rungs 3 and 4) and `cstate.py:663` (would give the capacity gate its first live
> occupancy signal). Measured at `2856152b`; `arms_v6cfr3.py`'s move to
> `planner_deficit_weights.py` at `1235b070` is behaviour-preserving (docstrings and message text
> only; `wire_planner` has no caller there), so these cells are valid at both.

### 8.3 Proposed `results/INDEX.md` rows

Appended by this session (the only `research/*.md`-adjacent file in my ownership); the design-log
and EXPERIMENTS rows above are the user's to apply.


---

## 9. Conclusions, with every null classified (CLAUDE.md Rule 2)

### 9.1 The three escalations, in the brief's own terms

**(a) A CHARACTERISTIC DECISION COUNT IS ZERO.** `rd_question_defers = 0` in the full rung-4 arm at
0.25x, against 6 at 1x. Classified **INCONCLUSIVE - UNEXERCISED for that leg in that compound**,
and the classification is measured, not argued: the leg makes 6 deferrals when run alone at 0.25x
(`-rqonly`, byte-identical to the full arm at 1x), and the compound's gate mix accounts for every
lost candidate (`rd_skipped_already_deferred` 4 -> 20 against protect-and-defer's 16 request
deferrals, 4 + 16 = 20). It is **not** "fired and did not help" and it is **not** evidence about
question deferral under memory pressure. **The arm as a whole PASSES the port rule** with 42
characteristic decisions.

**(b) 0.25x DOES NOT BIND - for rungs 0 to 3, and only in the decision register.** Classified
**INCONCLUSIVE - UNEXERCISED**. Rung 3 at 0.25x reproduces its committed 1x digest exactly
(`12e4f73ce0ebd865` / 13,812, 0 differing decisions), because no covex-v6 arm below rung 4 reads
the pool. **It DOES bind for rung 4** - 1,051 decisions move between 1x and 0.25x, 42 characteristic
decisions appear, and the Step 4 control collapses the whole difference - but it binds through the
pool's **declared size** only, not through observed occupancy (3.4).

**(c) AN INHERITED MECHANISM IS MISSING / MIS-DECLARED / UNEXERCISED.** Five, all reported and
none fixed:

1. the `_caps` capacity channel - write-only for our whole ladder (section 1);
2. the off arm's broken self-declared identity with rung 3, contamination pinned at exactly
   **+711 rows** (section 3.0 / 3.5);
3. **M9: the C5 attribution rule that NAMES rung 2 has zero dry counters at seed 4**, corroborated
   by `covex-v6-state-uo` and `covex-v6-state-uo-c5attr` carrying the **same committed digest**
   (section 5.4) - Rule 2 **unexercised**, so no seed-4 ladder number may be attributed to it;
4. `arms_v6fairfeed.py:57`'s stale reason for the flexible-split consumer being unexpressible - the
   line it says is missing has landed (section 5.2);
5. the arm plans at the **retired** safety factor 1.8721 while Gate A audits 1.863404, one request
   in 463 (section 3.9).

### 9.2 Classification of every null in this study

| null | classification | why |
|---|---|---|
| rung 3 flat between 1x and 0.25x | **INCONCLUSIVE - unexercised** | no read exists; `_caps` is write-only (1.2) |
| rungs 0 to 2, and both lower final rungs, flat | **INCONCLUSIVE - unexercised** | same chain, same absence; the final ladder adds no read |
| enforcement on vs off, either arm, 0 decisions | **INCONCLUSIVE - unexercised** | eviction moves `measured_tier`; tier is not read for decisions. Physically it moved 39-48k tokens (3.3) |
| rung 4's free-KV estimate unchanged by eviction | **INCONCLUSIVE - unexercised** | the engine-metric input is identically 0.0, and the belief follows eviction only on a COMPLETE build (3.4) |
| `rd_question_defers = 0` in the compound at 0.25x | **INCONCLUSIVE - unexercised in the compound** | pre-empted by the other leg; fires 6 times alone (3.6) |
| protect-and-defer 0 characteristic decisions at 1x | **INCONCLUSIVE - unexercised** | the pool has room; 198 of 251 decisions stop at "rebuild fits without evicting". Matches D190 |
| `-harm0` collapsing to the off arm | **not a null** - it is the Step 4 **control passing** | the mechanism disabled at source removes the entire difference |

**Nothing in this study is classified as a REAL NEGATIVE, and nothing is classified as "fired and
did not help".** Every null here is an absent or pre-empted channel. Under Rule 1 none of them may
be reported as a finding about the policy, and none is.

### 9.3 What the 0.25x rung-4 result IS, stated at the width the evidence supports

- The memory setting **reaches a rung-4 decision** and the mechanism **is** what moves it: 42
  characteristic decisions, 1,051 decisions moved against 1x, Step 2b 1,756 against the matched
  comparator, Step 4 collapsing to 0, and a deciding bar with 9 distinct values all above the w = 1
  floor. **Gate A's dry items are therefore satisfied for rung 4 at 0.25x where they were not at
  1x**, and the arm is scorable.
- It is a response to a **declared pool size**, not to **measured pressure** (3.4), so the result
  should be worded "the policy reacts to a smaller configured pool".
- It is **one leg at a time**: at 0.25x the compound is protect-and-defer alone and gives up all six
  question deferrals (3.6). The legs must be reported separately.
- It shows a small **outcome** effect in the dry residency trajectory - peak GPU residency 58,281
  -> 53,071 tokens and 89 fewer over-cap epochs against the matched comparator - which is dry and
  therefore a statement about the simulated trajectory, not about engine cost.
- **One seed (4) only**, per D196's fail-fast order. Not a four-seed verdict and not reported as one.
- Decision latency p99 **4.345 ms worst case** against the 20 ms budget, 0 of 158,117 decisions over
  it; between-cell differences are host contention and may not rank arms (3.8).

### 9.4 What must happen before a 0.25x POLICY CELL runs

1. **A ruling on section 1.6** (options A / B / C). Under option A the 0.25x comparison is rung 4
   against arms that cannot see the pool, and the report must say so at every use.
2. **Re-run this dry proof on `covex-v6-final`**, not on `covex-v6-cf-c5attr`. The final rung 4
   differs by the `id(obs)` fix, the planner-on-feed at rung 3, and the alert release re-check, all
   of which change decisions. The structure and the channel analysis transfer; the counts do not
   (section 7).
3. **Session A's `cstate.py:663` metric-key fix** is the single highest-value change for this claim:
   without it rung 4's capacity gate has no live occupancy signal at all (3.4).
4. Optional and cheap: feed the n = 463 safety factor into `d190_measured_safety` so the arm plans
   at the factor Gate A audits (3.9).

---

## 10. The INDEX.md rows appended by this session

Two rows, both appended to `results/INDEX.md` by this session's commit (the design-log and
EXPERIMENTS rows in section 8 are the user's to apply):

1. `results/orchestration/live2/d210_rung4_kv025/` - the twelve dry cells, the manifest, the
   assembled report JSON, the two Gate A JSONs and the three counter-census JSONs.
2. `reports/study_d210_kv025_dry.md` - this report.

Both rows carry, verbatim: the register (DRY and LOGICAL, 15,736 logical tokens, no engine and no
`--num-gpu-blocks-override`); the five committed bars and which one D216 (1) withdrew; the binding
verdict in Rule 2's vocabulary; and the statement that the counts do **not** transfer to
`covex-v6-final`.

**Files deliberately NOT committed:** the eleven `*.rows.json` intermediates, 8 to 9 MB each and
over the 5 MB limit. They are regenerable from `d210_kv025_driver.py` and
`results/orchestration/live2/d210_rung4_kv025/cells/NOT_COMMITTED.txt` says so in the directory.
What the commit keeps is every cell summary, every latency report with its enforcement proof, the
`rd`/`pd` per-decision dumps, the manifest and the assembled report.
