# StudyC5-ATTR: two candidate fixes and one diagnostic for rung 1's dashcam loss

Session C5-B, flash, 2026-11-22. User ruling of 2026-11-22 (addendum). **Everything here is a
CANDIDATE, DEFAULT OFF. Nothing is adopted, no winner is declared, and that choice is the user's.**

Artefacts:

| what | where |
|---|---|
| the candidate arm | `experiments/orchestration/live2/arms_v6c5.py` (`covex-v6-state-uo-c5attr`) |
| the attribution rule | `experiments/orchestration/live2/hybrid/hybrid_arm.py` (`_attr_suppresses`, read in `_aimd`) |
| the overlap test | `experiments/orchestration/live2/coordinator.py` (`_self_released_overlap`) |
| Step 2b on the live traces | `results/orchestration/live2/frozen_test/c5attr_replay_proofs.json` |
| digest / Step 2b / controls, dry | `results/orchestration/live2/frozen_test/c5attr_digest_proofs.json` |
| name resolution through the harness | `results/orchestration/live2/frozen_test/v6_harness_name_proof.json` |
| engine-flag pre-registration | `research/prereg_c5_engine_flag.md` |
| the posted cells | `results/orchestration/live2/frozen_test/runs/C5DIAG_CELLS` |

---

## 1. Mechanism verification

### Step 0: what would make this run uninterpretable, asked before it ran

- **Is the comparator about to change?** `covex-v6-state-uo` is posted in `V6STATE_CELLS` and owned
  by another session. Checked: its file `arms_v6state.py` is NOT touched, and the candidate
  subclasses it from a new module. The digest proof P1 re-checks the comparator itself.
- **Is a default about to be restored or moved?** The switch is an INSTANCE attribute on the
  HybridArm that owns `self.cap`. Not a class attribute (which left a "negative control"
  un-collapsed in this project before) and not a module global (one that defaulted ON once cost a
  whole live cell). Grep after writing: the only writes are in `arms_v6c5.py` and the
  `--force-flag` proof path.
- **Does the mechanism have a reachable path in this regime?** Asked before the sweep and the
  answer was **"only partly"**: a dry cell CANNOT reach C5's trip at all, because the dry monitor
  service time is the committed curve's constant 0.3950 s against a 0.8 s trip. That is why the
  primary Step 2b is a replay of the committed LIVE traces and why the dry proof needs a declared
  instrument. Finding this before the runs is the whole value of the step.
- **Does a run I depend on key into my analysis?** The replay reads committed cells only, and its
  control is those cells' own `c5_increase` / `c5_decrease` counters.

### Step 1: the causal chain

If C5's AIMD cap halves on monitor lateness that our own released work caused (the measured
dominant bucket: cap shut AND a robot prefill in flight, 37.5 to 43.0 percent of all opportunities
at rung 1 against 3.7 to 7.9 at the base, `c5_loss_split.json`), then attributing that lateness to
our own scheduling rather than to engine overload keeps the cap higher; a higher cap means a larger
per-epoch dashcam release budget (`budget = cap - episodic_in_flight`, `_cap_dashcam_only`); a
larger budget means fewer monitor opportunities never submitted (52 to 58 percent at rung 1); and a
submitted monitor can be delivered before its 1.0 s deadline, which a never-submitted one cannot.
The links are grounded in C5 as specified in `hybrid/hybrid_arm.py` lines 20 to 21 and in the
loss split's own measured buckets.

### Step 2: each link instantiated

| causal link | implementing quantity | value / range in this run | varies as expected? | evidence (the READ, not the write) |
|---|---|---|---|---|
| our own released work overlaps a monitor's wait | `coordinator._self_released_overlap`, reported as `self_released_prefill_overlap` | True for the majority of slow monitors on the live traces; on the dry instrumented cell 221 of 312 trips had all-self-released evidence | yes | READ at `hybrid_arm.py` `live2_completed` -> `_attr_mon`, consumed by `_attr_suppresses` |
| the rule suppresses a halving | `stats["c5_attr_suppressed_decrease"]` | **4,153 to 4,899 suppression EVENTS per rung-1 live cell, which is 436 to 514 halvings PREVENTED (see the register note below); 221 events on the dry instrumented cell** | yes | `_aimd` returns before `self.cap = max(4, self.cap // 2)` |
| the cap is higher | the cap series | epochs at the floor **7,544 to 8,428 -> 3,324 to 4,877** of 12,000 (replay, rung 1) | yes | `_cap_dashcam_only` reads `self.cap` at `hybrid_arm.py:536` |
| a higher cap releases more dashcam work | `budget = cap - epi`, `c5_dash_held` | **NOT MEASURABLE OFF A SERVER.** Dry: 0 differing decisions (see Step 2b) | **UNEXERCISED dry** | the live cells of `C5DIAG_CELLS` are the only path |
| more releases means more on-time alerts | scorer dashcam on-time | not measured here | **UNEXERCISED dry** | as above |

The first three links are present, non-zero and vary. The last two are **UNEXERCISED in every
offline register**, by construction, and the posted live cells exist for exactly them. No outcome
claim is made from this work.

### Step 2b: the switch reaches a decision

**Primary, on the committed live traces** (`c5attr_replay_proofs.json`, read-only, both arms x
seeds 4 to 7):

| rung-1 cell | suppression events | halvings prevented | cap decreases committed -> candidate | epochs at the floor | epochs with a different cap |
|---|---|---|---|---|---|
| v5-rules-2 s4 | 4,899 | 514 | 599 -> 85 | 8,428 -> 3,415 | 6,528 |
| v5-rules-2 s5 | 4,153 | 436 | 548 -> 112 | 7,945 -> 4,877 | 4,529 |
| v5-rules-2 s6 | 4,283 | 448 | 548 -> 100 | 7,712 -> 3,996 | 5,135 |
| v5-rules-2 s7 | 4,318 | 450 | 539 -> 89 | 7,544 -> 3,324 | 5,182 |
| base noc3 s4 to s7 | 595 to 1,091 | 62 to 126 | 92 to 154 -> 20 to 30 | 1,844 to 2,989 -> 686 to 1,161 | 2,799 to 4,806 |

**REGISTER NOTE, and it is a correction to my own first wording.** `c5_attr_suppressed_decrease`
counts suppression EVENTS, not distinct halvings: a suppression deliberately does not advance C5's
one-second cooldown, so while the trip persists the rule re-evaluates every 0.1 s epoch and counts
again. The number of HALVINGS PREVENTED is the difference in cap decreases (436 to 514 per rung-1
cell), and that is the number to quote. A reader given 4,899 against 599 committed halvings would
read an impossible count.

**Secondary, in the code, dry, one cell per process** (`c5attr_digest_proofs.json` P2): the cap
series digest differs and the first halving moves from t = 7.1 s to t = 11.0 s, with halvings
suppressed (count in the JSON; 221 on the 120 s exploratory cell and the same mechanism at 1,200
s). **The number of differing DECISIONS is ZERO**, at 300 s and at the full 1,200 s, at seeds 4 and
5 (the two row files are byte-identical, 7,809 rows), and that is reported rather than hidden.
The reason is structural and measured, in two parts. (a) Reaching the trip in a dry cell requires
raising the monitor service time, and the dry stand-in's latency is a CONSTANT, so once it is above
the trip the cap falls to its floor in both arms within seconds and stays there; the dry harness has
no regime in which the EWMA oscillates around the trip, which is the regime the live traces are in
(monitor TTFT p50 0.436 to 0.448 s with a tail above 0.8 s). (b) Even where the caps differ, the dry
cell never has more than 4 monitor releases in one epoch (p50 2, max 4 over 2,663 epochs), so a
budget of 3 and a budget of 7 admit the same set; in the live cells the cap plainly binds, since 52
to 58 percent of opportunities are never submitted. **Classification of the dry decision-level null:
INCONCLUSIVE, UNEXERCISED.** It is not a negative about the rule.

A second, more surgical instrument was tried and is recorded because it fails informatively:
scaling only the EWMA the arm reads makes the trip reachable while leaving occupancy committed,
but the per-monitor first-token times stay fast, so there is no slow monitor to attribute and the
rule correctly declines to suppress (`c5_attr_trip_without_slow_evidence` = 294, suppressed 0).

### Step 3: one traced unit

A real instrumented trace, every AIMD evaluation of the candidate arm between t = 10.0 s and
t = 12.1 s on one dry cell (seed 4, 16 devices, posted knobs, `--trip-s 0.9`). `budget = cap - epi`
is the per-epoch dashcam release budget `_cap_dashcam_only` computes; `evidence` is the monitor
completions since the last cap adjustment and `slow` those above the 0.8 s trip.

```
t=  10.0  epi=1  cap=8  budget=7  ewma=0.900  evidence=7 slow=7 all_self=True   -> SUPPRESS cap=8
t=  10.5  epi=1  cap=8  budget=7  ewma=0.900  evidence=8 slow=8 all_self=True   -> SUPPRESS cap=8
t=  10.9  epi=2  cap=8  budget=6  ewma=0.900  evidence=8 slow=8 all_self=True   -> SUPPRESS cap=8
t=  11.0  epi=1  cap=8  budget=7  ewma=0.900  evidence=9 slow=9 all_self=False  -> halve  cap=4
t=  11.1  epi=1  cap=4  budget=3  ewma=0.900  evidence=0 slow=0 all_self=False  -> hold   cap=4
t=  11.5  epi=1  cap=4  budget=3  ewma=0.900  evidence=1 slow=1 all_self=False  -> hold   cap=4
```

The comparator arm halves at t = 7.1 s on the same cell; the candidate holds until t = 11.0 s, when
the ninth monitor completion did NOT overlap a released prefill and the evidence became mixed, at
which point the rule correctly stops suppressing and the cap halves. The `hold` rows after it are
C5's own one-second cooldown, not suppressions. Nothing is charged by the rule: it moves no
request and spends no budget, it only withholds a back-off.

**Why the cap difference does not reach a decision IN THIS CELL, measured rather than asserted.**
In the same dry cell the number of monitor releases in any one epoch is at most 4 (p50 2, p90 2,
max 4, over 2,663 epochs with a release), so a budget of 3 and a budget of 7 admit the SAME set and
the cap cannot bind. In the committed live cells it plainly does bind: 52 to 58 percent of monitor
opportunities are never submitted. `c5_dash_held` does differ between the two arms (16,099 against
a lower count), and that is worth naming: it counts streams held that had no opportunity due, so it
is a counter that moves while no decision moves. It is NOT evidence that the rule reached a
decision, and it is not used as such.

### Step 4: negative controls (two, both pass)

- **The arm's own switch forced off** (`--force-flag off`): byte-identical to `covex-v6-state-uo`,
  same decision digest and same cap series digest (P4). So the P2 difference is the rule and not
  the wrapper, the subclass or the coordinator's new keys.
- **The rule present but unable to fire** (replay, NEVER-SUPPRESS: the uncached threshold raised
  past any observed value): reproduces the committed cap trajectory EXACTLY on all eight cells.

### Step 4b: positive controls (the check can see a difference)

- **ALWAYS-SUPPRESS** in the replay moves the trajectory on every cell (non-zero
  `epochs_with_a_different_cap` on 8 of 8).
- **The reconstruction control**: the committed replay reproduces the base arms' own
  `c5_increase` / `c5_decrease` counters within one count, and reproduces `c5_loss_split.json`'s
  own committed reconstruction for the rung-1 cells **exactly** (599 / 548 / 548 / 539 decreases
  and 8,428 / 7,945 / 7,712 / 7,544 floor epochs).

### Step 5: the alternative explanation

A higher cap would also follow from (b) simply raising C5's floor or its trip, which is not an
attribution rule at all and needs no overlap information. On the cap trajectory alone, (b) and the
claimed mechanism are **not distinguishable**: both keep the cap high. What distinguishes them is
the conditioning, and it is observable: under the claimed mechanism, suppression happens only in
epochs where a self-released prefill overlapped the slow monitor, so `c5_attr_slow_mixed` must be
non-zero and halvings must still occur when the lateness is NOT ours. It is: on the dry
instrumented cell 91 halvings still fired as mixed-evidence trips, and in the replay 85 to 112
decreases survive per rung-1 cell. A floor raise would show zero surviving decreases of that kind.
**A reader comparing the candidate against rung 1 on outcome alone cannot tell the two apart, so
if the user wants that separated, the comparator to run is a floor-raise arm, which is NOT built
here and was not asked for.** Stated rather than quietly left open.

### The port rule

The arm's characteristic decision is a **suppressed halving**. In the replay it fires **4,153 to
4,899 times per rung-1 live cell** (suppression events) and prevents **436 to 514 halvings**; on
the dry instrumented cell it fires 221 times. It is **not inert**. On the live cells themselves the count will be recorded as
`arm_stats.c5_attr_suppressed_decrease`, and if it is zero there the cells prove nothing and must
be reported that way.

---

## 2. Results consistency check

1. **Cross-check against committed measurements.**

| quantity | this run | prior committed | source of prior | ratio | agree |
|---|---|---|---|---|---|
| rung-1 reconstructed cap decreases (s4/s5/s6/s7) | 599 / 548 / 548 / 539 | 599 / 548 / 548 / 539 | `c5_loss_split.json` | 1.000 | agree |
| rung-1 epochs at the cap floor | 8,428 / 7,945 / 7,712 / 7,544 | same | `c5_loss_split.json` | 1.000 | agree |
| base-arm reconstruction against the arm's own counters | 154/97, 112/106, 118/97, 92/77 | 154/97, 111/106, 117/97, 92/77 | the cells' `arm_stats` | within 1 count | agree |
| server `max_num_batched_tokens` | 8192 (assumed for the live server) | 8192 | `results/cost/study_e10/e10e_run_meta_h100nvl.json` | 1.000 | agree |
| `--long-prefill-token-threshold` values ever measured here | 2048 (new, pre-registered) | 1024 (P1), 512 (P2) | `baselines/tuned_engine.py`, StudyE10e | n/a | new value, declared |
| committed arms' dry decision digests | unchanged | the same digests from git at `f2d617fa` | P1 of `c5attr_digest_proofs.json` | 1.000 | agree |

2. **Physical plausibility.** No latency is measured or claimed by this work. The two latency-like
numbers quoted are (a) the dry stand-in's constant monitor service time 0.3950 s, which is
`costs.episodic_cloud_latency_s('32BI', 1, 25)` by construction, and (b) committed live monitor
TTFT p50 0.436 to 0.448 s from `c5_loss_split.json`. The engine-flag arithmetic implies no rate: it
counts scheduler steps against a token budget read from the source.

3. **Distribution sanity.** The replay reports per-cell values, not a median: suppressions 4,153 to
4,899 at rung 1 and 595 to 1,091 at the base, floors 3,324 to 4,877, differing epochs 4,529 to
6,528. The spread across seeds is wide and seed-ordered, as the committed loss split's own spread
is. The one CONSTANT in this work is deliberately flagged: the dry monitor service time, which is
constant because the stand-in is a single committed number, and that constant is exactly what makes
the dry decision-level register unexercised. A monitor prompt-token "about 1,056" turned out to be
a **minimum, not a typical value** (1,056 min, 3,760 p50, 7,140 max), which changed the engine-flag
derivation; that is the "plausible number in the wrong register" shape and is recorded in the
pre-registration.

4. **Definition audit.** `robot prefill` = a build, touch or recall the coordinator released with
uncached >= 200 tokens, identical to `c5_loss_split.json`'s ruling. `uncached` = `prompt_tokens -
cached_tokens` in the replay (the engine's own, as the loss split uses) and = the count the
coordinator CHARGED at release in the live arm (its own prediction); the two are the same quantity
measured either side of the release and the difference is declared in both files. `overlap` = the
monitor's `[t_submit, t_first_token]` intersects the prefill's `[release, finish]`, with an
unfinished prefill treated as still in flight. `slow monitor` = first-token time > 0.8 x the 1.0 s
dashcam deadline, C5's own trip. `cap floor` 4, `ceiling` 8, step +1 per 5 s, halving at most once
per second: all unchanged from `hybrid_arm.py`.

5. **Claim linkage.** This work bears on the live policy's dashcam channel, i.e. the orchestration
side of Context Inertia's physical component (`FORMULATION.md`, the contention between
reconstruction work and latency-critical traffic). It is **not** a fidelity claim and it does not
speak to any representation-quality claim. Nothing here measures an object the formulation scopes
out: the engine flag changes scheduling inside one server and moves no KV between tiers.

6. **Proxy validity.** One proxy, declared: the live arm's overlap test uses the coordinator's
PREDICTED uncached count at release rather than the engine's later `prompt - cached`. It is valid
for the rule's purpose, which is "did WE release heavy work that overlapped this wait", because the
prediction is what the coordinator knows at release time and is the only thing causally available
when the attribution is needed. It is NOT used for any headline, and the replay (which uses the
engine's own numbers) and the live arm agree on the bucket definition the ruling fixed.

7. **Validate the control, not only the result.** The comparator side was audited first: the
committed arms' own dry digests were taken from git at `f2d617fa` and compared against this tree
(P1, four arms); the replay's committed side was checked against the arms' own counters and against
`c5_loss_split.json`'s committed reconstruction before any candidate number was read. A positive
control (ALWAYS-SUPPRESS) confirms the check can see a difference, and a negative control
(NEVER-SUPPRESS, and the arm's switch forced off) confirms it collapses.

---

## 2b. Which slow monitors trip the cap, and what bounds the candidate

Asked for by the user ruling of 2026-11-22 (second addendum).
`results/orchestration/live2/frozen_test/c5attr_trip_attribution.json`, read-only, classifies every
slow monitor (first-token time above C5's 0.8 s trip) counted as the evidence of a halving by what
its wait overlapped among requests THE COORDINATOR RELEASED with uncached >= 200 tokens, using each
overlapping request's own decision kind from the cell's decision log.

| rung-1 cell | slow monitors at a halving | recall | warm build | several | **NONE** |
|---|---|---|---|---|---|
| v5-rules-2 s4 | 1,114 | 607 (54.5%) | 92 (8.3%) | 280 (25.1%) | **135 (12.1%)** |
| v5-rules-2 s5 | 1,118 | 518 (46.3%) | 86 (7.7%) | 328 (29.3%) | **186 (16.6%)** |
| v5-rules-2 s6 | 1,024 | 501 (48.9%) | 73 (7.1%) | 293 (28.6%) | **157 (15.3%)** |
| v5-rules-2 s7 | 1,002 | 532 (53.1%) | 42 (4.2%) | 315 (31.4%) | **113 (11.3%)** |
| base noc3 s4 to s7 | 267 to 376 | 79 to 90% | 0 | 0 | **9.8 to 20.5%** |

**What bounds the candidate, stated plainly.** Classifying the committed halvings by the evidence
they fired on:

| rung-1 cell | halvings | all evidence ours | mixed | all evidence NONE-overlapping | no slow evidence at all |
|---|---|---|---|---|---|
| s4 | 599 | 321 (53.6%) | 31 | 35 | **212 (35.4%)** |
| s5 | 548 | 300 (54.7%) | 41 | 40 | **167 (30.5%)** |
| s6 | 548 | 278 (50.7%) | 30 | 34 | **206 (37.6%)** |
| s7 | 539 | 295 (54.7%) | 34 | 21 | **189 (35.1%)** |

So **only about half of rung 1's halvings fire on evidence the rule can attribute to our own
released work (50.7 to 54.7 percent)**. The rest are mixed, are monitors that overlapped nothing of
ours (3.9 to 7.3 percent), or, the largest remainder, are trips where the EWMA is above 0.8 s while
no individual pending monitor was (30.5 to 37.6 percent): the cap reacting to its own queueing and
to the memory of past lateness. **The attribution rule does not suppress any of those, by design.**

The static share (about 54 percent) and the replay's dynamic effect (436 to 514 of 539 to 599
halvings prevented) are both correct and are different registers: once the first halvings are
suppressed the cap stays at 8, which changes the later trajectory, the evidence sets and the
subsequent trips. The static share is the honest answer to "how much of the committed behaviour can
this rule even see"; the replay is the answer to "what does the trajectory look like under it".

**Cross-check against the user's own measurement** (their numbers, measured independently from the
covex-v6-state-uo s4 logs, against mine from the rung-1 and base cells): release delay
`t_submit - t_opportunity` base p50 0.30 s / p90 0.89 s with 37 percent over 0.5 s, mine 0.201 to
0.362 / 0.829 to 0.902 with 26.5 to 42.7 percent; rung-1 p50 0.759 to 0.816 / p90 0.960 to 0.985
with 71.0 to 86.8 percent over 0.5 s, against their rung-2 0.74 / 0.97 and 72 percent; dashcam
uncached per request base 374, rung 1 376 to 378, against their 374 and 376. **The quantities agree
and the direction is theirs: lateness is release delay inside the coordinator, not engine time.**
The rung-2 (`covex-v6-state-uo`) cells themselves were not on disk in this worktree when the
breakdown ran; the row is present and marked MISSING, and the script runs unchanged once they are.

## 3. The engine-flag diagnostic

Pre-registered in `research/prereg_c5_engine_flag.md`, committed in or below the commit that posts
the cell list, with the arithmetic, the 0.31.0 source facts (file and line), the measured monitor
prompt distribution, the measured prefill-phase concurrency, the cost to a long prefill, and the
conditional re-derivation if the launched server's resolved `max_num_batched_tokens` is not 8192.
**N = 2048.** `--max-num-partial-prefills` is not used: it does not exist in vLLM 0.31.0.

The flag is SERVER-WIDE. Its cells are labelled `_L3_epg_rq30_lpt2048` and may not be compared with
any committed cell of the same arm. Adoption would mean rerunning every arm, which is why it is a
diagnostic.

---

## 4. What was not done, and what is not established

- **No winner, no adoption, no default changed.** Both candidates are off unless a cell list names
  them.
- **No outcome.** Nothing here shows that either candidate improves alert on-time delivery. The
  replay is a cap trajectory on a fixed trace, and it says so in its own `_register` field.
- **The dry decision-level register is unexercised** for this rule, with the reason stated above.
- **The alternative explanation in Step 5 (a floor raise) is not separated by outcome**, and the arm
  that would separate it is not built.
- **The suppression policy is a choice**: on suppression the cap is HELD rather than stepped up. The
  more aggressive variant (treat a suppressed trip as evidence of health and allow the +1 recovery)
  is NOT built, because it would grant the cap something the AIMD rule would not have granted it.
