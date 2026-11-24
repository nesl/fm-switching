# StudyD216-KV025: does the reactive residency path work, what does the survival predictor use, and the 0.25x dry cells on the final ladder

Session: flash, 2026-11-23. Builds on `reports/study_d210_kv025_dry.md` (Session D, pushed at
`3fa41f51`), whose structure, channel analysis and blindness finding are reused rather than
re-derived. Measured at `87ca3503` (`origin/main` when the clean `git archive` export was taken).

---

## 0. Register, stated before any number

| what | register |
|---|---|
| check 1's correction counts | **OBSERVED.** Counters written by `coordinator.py:1799-1806` into committed LIVE cells, read out of git objects at `87ca3503`. 159 cells. |
| check 1's read sites | **OBSERVED** in the source at that sha, by file and line, at the point of **use**, not of assignment. |
| check 2's answer | **OBSERVED** over the source: signatures by `inspect`, belief writers by a line census, prices by evaluating the committed functions on literals. |
| check 2's costing | **CONSTRUCTED.** An estimate of work, not a measurement. It is labelled as one everywhere it appears. |
| check 3's cells | **DRY and LOGICAL.** `--kv-scale` scales `test_live2_coord.GPU_KV`, the coordinator's own logical pool. No engine, no `--num-gpu-blocks-override`, no real KV allocator. |
| check 3's decision latency | **OBSERVED but a FLOOR**: flash CPU wall-clock inside the arm's `decide` (`coordinator.py:2127`), at the loadavg the manifest records per cell. Not an H100 number. |

**What the ruling of 2026-11-23 asks, and what this report is for.** Rungs 2 and 3 do not make
memory trade-offs by design; trade-offs are rung 4's counterfactual (D151, D163). Their
capacity-blindness **for decisions** is therefore not a defect, is not fixed, and no cell is re-run
for it. The sentence that replaces the defect reading is: *rungs 2 and 3 adapt to memory pressure
only reactively, through engine telemetry; rung 4 adapts proactively.* That sentence is only
writable if the reactive path reaches a decision. Check 1 is the measurement of whether it does.

---

## 1. CHECK 1: the residency belief IS corrected per request, and for rungs 2 and 3 the correction reaches a decision

Artifact: `results/orchestration/live2/d216_final_kv025/belief_correction_census.json`
(`experiments/orchestration/live2/d216_belief_correction_census.py`, read-only, sha-pinned).

### 1.1 The path, with the write, the gate and the reads named separately

**WRITE.** `engine_actions.belief_update_from_cached_tokens` (`engine_actions.py:315`) turns the
engine's own per-request `prompt_tokens_details.cached_tokens` into a one-hot `SessionRec.belief`
(`engine_actions.py:387-388`). `ct > 0` promotes to `gpu`; `ct == 0` on a request that offered a
built prefix demotes to `cold`; `ct is None` is **no evidence** and the belief is untouched, which
is why a dry cell cannot exercise this path at all.

**THE PRIOR THE BRIEF SAID TO TEST RATHER THAN INHERIT, and it does not apply to this writer.**
Session D measured that eviction moves `measured_tier` while the belief follows only on a complete
build. That gate is in `cstate.SessionRec.set_tier` (`cstate.py:207`: `if self.built_tokens >=
self.est_tokens and self.est_tokens > 0`), and it governs the **placement / enforcement** path, not
the telemetry corrector. The corrector writes `session.belief` **directly**, bypassing `set_tier`,
so it carries **no** complete-build condition and can move the belief on a partial prefix. The
plausible outcome the brief named - a correction that fires only on complete builds - is therefore
**not** what is there.

**GATE, and this is where the answer splits.** `coordinator._collect` (`coordinator.py:1796`) calls
the corrector on every completed request, counts it, and then **restores the snapshot** unless
`self._belief_apply` (`coordinator.py:364-365`), which is true only if
`LIVE2_BELIEF_CORRECTION=apply` is in the environment (default `observe`, `coordinator.py:141`) or
the **arm** declares `live2_belief_apply`. Only `V6StateArm` and its descendants declare it
(`arms_v6state.py:165`, defaulting to `plan_state`). So rungs 2, 3 and 4 apply the correction, and
rung 0, rung 1 and every one of the paper baselines - `b7-edf-feasibility` included - compute it,
count it, and throw it away (`coordinator.py:1803-1806`).

**THE READS, at the point of use.**

| consumer | read site | what the value changes |
|---|---|---|
| rung 2 / 3 touch | `coordinator.py:1161` `TP.should_touch(belief=dict(s.belief))` | refuses the touch on a `cold` belief (`touch_refused_guard`) or prices it from the predicted tier |
| rung 2 / 3 warm build | `coordinator.py:1238` `TP.build_price_gpu_s(piece, built, s.belief, C)` | the GPU-second charge handed to `budget.can_spend`; a refusal is `budget_refusal_build` |
| recall charge | `coordinator.py:1294` `C.recall_gpu_s(tokens, s.residency_readiness())` | the accelerator charge for the recall |
| rung 3 release re-check | `coordinator.py:1331` `_uncached = tokens if s.residency_readiness() == "COLD" else ...` | the D179 (4) wire-time feasibility test that releases or skips the recall |
| rung 2 / 3 state planner | `arms_v6state.py:416` `host_warm` from `roster["belief_by_session"]` (`coordinator.py:757`) | gates the RELOAD candidate inside `plan_state` |
| **b7 feasibility** | `cstate.py:636` `ready = s.readiness()` -> `cstate.py:648` `RecallQuery.readiness` -> `baselines/constructed.py:184` `est = C.recall_ttft_s(q.readiness_tokens, q.readiness)` | `est <= slack` admits CLOUD, `est <= slack + defer_s` DEFERS, otherwise **REJECT** |

Every row is a read that changes a decision, not a place the value is set.

### 1.2 The counts, per cell

Rung 2 (`covex-v6-state` and its ablations) and rung 3 (`covex-v6-fair-c5attr` and its variants),
every committed live cell, 16 devices, 1,200 s:

| cell | arm | offered | changed | reverted | ->gpu | ->cold | ->host |
|---|---|---|---|---|---|---|---|
| `covex-v6-state_n16_s4_..._rerun` | rung 2 | 1,723 | 7 | 0 | 7 | 0 | 0 |
| `covex-v6-state_n16_s5_...` | rung 2 | 802 | 13 | 0 | 11 | 2 | 0 |
| `covex-v6-state_n16_s6_...` | rung 2 | 131 | 8 | 0 | 8 | 0 | 0 |
| `covex-v6-state-uo_n16_s4_...` | rung 2 | 3,100 | 13 | 0 | 10 | 3 | 0 |
| `covex-v6-state-uo_n16_s5_...` | rung 2 | 795 | 14 | 0 | 12 | 2 | 0 |
| `covex-v6-state-uo_n16_s5_..._lpt2048` | rung 2 | 800 | 13 | 0 | 11 | 2 | 0 |
| `covex-v6-state-uo_n16_s6_...` | rung 2 | 1,033 | 13 | 0 | 12 | 1 | 0 |
| `covex-v6-state-uo_n16_s7_...` | rung 2 | 2,801 | 11 | 0 | 11 | 0 | 0 |
| `covex-v6-state-uo-c5attr_n16_s4_...` | rung 2 | 3,018 | 14 | 0 | 11 | 3 | 0 |
| `covex-v6-state-uo-c5attr_n16_s5_...` | rung 2 | 625 | 14 | 0 | 12 | 2 | 0 |
| `covex-v6-state-uo-c5attr_n16_s6_...` | rung 2 | 1,096 | 12 | 0 | 11 | 1 | 0 |
| `covex-v6-state-uo-c5attr_n16_s7_...` | rung 2 | 2,780 | 11 | 0 | 11 | 0 | 0 |
| `covex-v6-fair-c5attr_n16_s4_...` | rung 3 | 3,119 | 12 | 0 | 10 | 2 | 0 |
| `covex-v6-fair-c5attr_n16_s5_...` | rung 3 | 799 | 13 | 0 | 11 | 2 | 0 |
| `covex-v6-fair-c5attr_n16_s6_...` | rung 3 | 1,032 | 12 | 0 | 11 | 1 | 0 |
| `covex-v6-fair-c5attr_n16_s7_...` | rung 3 | 2,796 | 11 | 0 | 11 | 0 | 0 |
| `covex-v6-fair-c5attr-rr_n16_s4..s7` | rung 3 + rr | 3,298 / 800 / 1,037 / 2,811 | 13 / 13 / 12 / 11 | 0 | 10 / 11 / 11 / 11 | 3 / 2 / 1 / 0 | 0 |
| `covex-v6-fair-c5attr-gain0_n16_s4..s7` | rung 3 ablation | 3,065 / 624 / 1,017 / 2,799 | 14 / 13 / 12 / 11 | 0 | 11 / 11 / 11 / 11 | 3 / 2 / 1 / 0 | 0 |

The three cells of `covex-v6-state-shares`, four of `-shares-r1` and three of `-shares-r2` are in
the artifact and follow the same shape (6 to 11 changes per cell, 0 to 2 of them to `cold`).

Rolled up: **35 cells on arms that apply the correction, 53,673 corrections offered, 383 changed
the belief, 0 reverted, 346 to `gpu` and 37 to `cold`, 0 to `host`.**

And the other side of the same table, which is the part that decides what may be said about the
baselines: **124 cells on arms that do not apply it, 79,482 corrections offered, 7,525 changed, all
7,525 reverted, 0 applied.** `b7-edf-feasibility` alone: 5 live cells, 1,818 offered, 26 changed
(17 at s6 and 9 at s7), **all 26 reverted**.

### 1.3 Which of the three cases holds - and it is a different one per arm family

- **Rungs 2, 3 and 4: FIRES AND VARIES.** The correction is applied, it reaches two destinations
  and both are non-zero, and the reads above consume it. An eviction detected by the engine's own
  `cached_tokens` **does** reach rung-2 and rung-3 pricing. The reframing sentence is writable for
  these rungs.
- **Rung 0, rung 1 and every paper baseline, `b7-edf-feasibility` included: ABSENT IN THE DECISION
  REGISTER.** The corrector fires, varies and is instrumented, and the harness discards the channel
  it acts through. In Rule 2's vocabulary that is **unexpressible**, not a negative. It is also not
  a defect to fix: the gate exists because enabling the mutation mid-sweep would make the cells
  before and after incomparable for every arm that reads residency (`coordinator.py:1788-1795`),
  and a published baseline does not come with a telemetry corrector. It must simply not be
  described as adapting reactively.
- **`host`, on every arm: CONSTANT in the sense that matters.** `belief_to_host` is 0 in all 159
  cells. The `host` branch (`engine_actions.py:381-383`) requires `external_tokens`, and D209 (4)
  measured that vLLM 0.31.0's per-request usage schema has no field separating a host hit from a
  GPU hit - 26 percent of prompt tokens came from the host tier and all of them fold into
  `cached_tokens`. So this corrector can say `gpu` or `cold` and **never** `host`. That is D211's
  finding reached independently from the counter side, and it is why `plan_state`'s RELOAD
  candidate (`arms_v6state.py:416`) is structurally unexercised rather than merely unused.

### 1.4 THE LIMIT ON THE SENTENCE, and it is the thing to carry forward

**Not one committed reduced-pool live cell is on an arm that applies the correction.** Of the 23
committed live cells whose name carries a `_kv0.25` or `_kv0.5` suffix, **0 of 23** apply it: they
are `always-cloud-fcfs`, `attentionstore-prefetch`, `b7-edf-feasibility`, `covex-v6-base`,
`covex-v6-rules`, `eco-llm`, `edf`, `llf`, `mooncake`, `querystream-proactive`, `simplestream` and
`warm-all-lru`, every one of them belief-apply OFF. Rung 2, rung 3 and rung 4 have live cells at 1x
only.

So the reactive path is **alive and measured at 1x** and has **never been exercised live at a
reduced pool**. The honest form of the sentence is therefore:

> Rungs 2 and 3 do not plan against capacity; they adapt to it reactively, through the engine's own
> per-request cached-token count, which corrects the residency belief that their touch, warm-build,
> recall-charge and release-recheck prices all read. Measured at the full pool over 35 live cells,
> that correction changed the belief 383 times, 37 of them to `cold`, and it can never say
> host-warm on this engine, so a host-resident history is priced as a cold rebuild. At a reduced
> pool the path has not been measured: no live cell at 0.25x or 0.5x runs an arm that applies it.

**The magnitude belongs in the sentence.** 383 applied corrections over 53,673 offered is 0.7
percent, and the demotions that are the eviction signal are 37 in 35 cells - about one per cell.
The path works; it is thin. Reporting the verdict without the magnitude would overstate it in
exactly the direction the ruling is relying on.

**A second reactive channel exists and is not engine telemetry, so it must not be folded in.** The
coordinator's own capacity enforcement (`cstate.py:520-535`) evicts by the **configured** pool when
`kv_capacity_enforced`, and that path moves the belief through `set_tier`, which **does** carry the
complete-build gate at `cstate.py:207`. It is simulated bookkeeping, not an engine observation, and
it is what makes `measured_tier` move while the belief does not on a partial prefix.

---

## 2. CHECK 2: NO. The predicted cache state does not consult the GPU-KV pool size

Artifact: `results/orchestration/live2/d216_final_kv025/survival_predictor_readsites.json`
(`experiments/orchestration/live2/d216_survival_predictor_readsites.py`).

**ANSWER: NO**, for state-based pricing and for b7, proved three ways that fail differently.

**By signature.** The functions that compute the predicted state and price from it are given a
belief and a token count and nothing else - no pool size, no occupancy, no free-block count, no
elapsed time:

| function | file:line | parameters |
|---|---|---|
| `predicted_tier` | `touch_policy.py:39` | `belief` |
| `mixed_touch_guard` | `touch_policy.py:47` | `belief` |
| `touch_price_gpu_s` | `touch_policy.py:63` | `prefix_tokens, belief, costs` |
| `price_for_touch` | `touch_policy.py:172` | `prefix_tokens, belief, costs` |
| `build_price_gpu_s` | `touch_policy.py:210` | `piece_tokens, prefix_tokens, belief, costs` |
| `should_touch` | `touch_policy.py:189` | `belief, prefix_tokens, costs, budget_ok` |
| `costs.recall_ttft_s` | `costs.py:106` | `tokens, readiness` |
| `costs.recall_gpu_s` | `costs.py:127` | `tokens, readiness` |
| `B7EDFFeasibility.decide` | `baselines/constructed.py:181` | `obs` only; reads `q.readiness` at `:184` |

A function that is not given a quantity cannot consult it.

**By the belief's own shape, and this is the finding inside the finding.** All 7 writers of
`SessionRec.belief` in the tree set a **one-hot** dict (`cstate.py:207-208`, `:312`, `:332`;
`coordinator.py:827`, `:1915`; `engine_actions.py:387-388`, `:509-510`). So `predicted_tier` always
returns mass 1.0, and `PURE_TIER_MIN_BELIEF = 0.95` can **never** refuse. The one piece of
machinery that could express a partially surviving prefix - the M6 / StudyRES1 R3 straddling guard,
which is exactly what a capacity-aware predictor would produce - is present, documented, and
unreachable. The only refusal path that ever fires is the `cold` one. A guard that cannot refuse is
the CONSTANT shape wearing a safeguard's clothes.

**What the predictor uses instead, named plainly.** Not time, not a constant, not the pool: the
**last observed or enacted tier**, carried forward unchanged until something observes again. It is
a stale observation standing in for a prediction. So the M5 question does not resolve as "it
predicts on the wrong variable" - **there is no survival model in the live path at all**. M5 /
StudyENG1b measured survival as a step function of KV allocated before resume (full below 1.0x of
the free pool, tail-first partial 1.0 to 1.25x, total above 1.25x) and D150 names that model as the
one the counterfactual predicts survival from; **no module in live2 implements it.**

**The one site that does read a pool, so the two are never conflated.** `arms_v6cf._pd_free_kv`
(`arms_v6cf.py:277`) reads the **declared** pool off `self._pd_gpu_kv_tokens`, the occupancy
fraction off `obs.cloud.gpu_kv_fraction` and a belief-based occupancy estimate off the roster, and
feeds `PD.decide(free_kv_tokens=...)`. That is rung 4's capacity gate on a rebuild - a trade-off,
and rung 4's by design - not the belief's survival prediction. Session D already recorded that it
is sensitive to the pool's SIZE and blind to its OCCUPANCY, and D216 (2) records why: nothing
scraped `/metrics`, so `gpu_kv_fraction` was 0.0 in every live2 cell.

### 2.1 THE COSTING, and it is NOT BUILT: this needs a ruling

Respecting the distinction the user drew: predicting survival more accurately is **accuracy**;
choosing what to evict or defer because of capacity is a **trade-off** and belongs to rung 4. What
follows is the accuracy fix only. **CONSTRUCTED estimate, not a measurement.**

**It splits into two options and only the first is affordable.**

**(a) ARM-SIDE ONLY - price from a predicted survival, rungs 2 to 4, behind an arm-declared
switch.**

| item | cost |
|---|---|
| new `survival_predictor.py` implementing M5's step function plus its unit proof | ~120 lines plus ~80 lines of proof; the step boundaries are committed (ENG1b / ENG1c), so nothing is fitted |
| re-point 2 coordinator read sites (`coordinator.py:1161`, `:1238`) behind a new capability flag, in the shape `live2_state_priced_costs` already has | small, but it is in `coordinator.py`, which **I do not own** |
| the input the predictor needs: KV allocated between the build and the next question | dry: derivable from `built_tokens_by_session` against the logical pool. **Live: it needs the D216 (2) `/metrics` scrape, which is built and NOT yet on origin.** So (a) is BLOCKED on that landing. |
| byte-identity prescreen on every arm that does not declare the flag | 1 proof, the committed 50-arm prescreen pattern |
| re-bars for the rungs that do declare it | rungs 2, 3, 4 at 1x and at 0.25x = **6 dry cells** at ~250 s each alone, plus the live cells those bars feed |
| **total** | ~1 working session of code and proofs, 6 dry cells, and a live re-bar of rungs 2 to 4. Blocked on the scrape. |

**(b) OBSERVATION-SIDE - so b7 and the baselines see it too.** This means changing
`RecallQuery.readiness` at `cstate.py:636`, which is the input of **every** arm. Every committed
digest in the frozen grid moves, so it costs a full re-bar of the paper's 16-arm baseline matrix -
and it is also **wrong on fidelity grounds**: a published baseline does not carry an M5 survival
model, and giving it one would stop it being the baseline. **Recommendation: do not do (b).**

**What is NOT in either option, deliberately.** Nothing here chooses what to evict, what to hold
back or what to defer on account of capacity. That is rung 4's and it already exists
(`_pd_free_kv` -> `PD.decide`).

**No ruling, no build.** Nothing above has been implemented.

---

## 3. CHECK 3: the 0.25x dry cells on `covex-v6-final`

Artifacts: `results/orchestration/live2/d216_final_kv025/cells/` (14 cells) and
`results/orchestration/live2/d216_final_kv025/d216_final_kv025_report.json`.

### 3.0 Preconditions, checked before starting

**The final rungs exist and build, and they are NOT registered by any runner.**
`arms_final_ladder.py` is on origin and defines `covex-v6-state-final`, `covex-v6-fair-final` and
`covex-v6-final` (`arms_final_ladder.py:75-77`), with `register()` at `:306` carrying D208's
collision check against the committed names. **`register()` has no caller in the tree** other than
`d208_ladder_name_proof`, so `covex-v6-final` does not resolve inside `cf_pd_one_cell` without an
explicit registration. That is what `d216_final_kv025_one_cell.py` adds, in the shape
`cfr3_one_cell._register_capturing` already uses; verified by construction
(`covex-v6-fair-final` -> `V6FairFinalWired`, `covex-v6-final` -> `V6Final`, both with a live, non
-constant planner weight source, and both committed factories left untouched).

**The ablation names did not exist and are registered in this process only.**
`FINAL_LADDER_ARMS` has one key per rung, so the off-switch identity bar and the Step 4 controls
had no name to run under. `covex-v6-final-off`, `-pdonly`, `-rqonly`, `-harm0` and `-margin-huge`
are added by the wrapper, each a `make_rung4` call with exactly the keyword the committed family
uses for the same ablation. No file the final ladder owns is touched.

**The alone rule is enforced by the driver, not timed by hand (D216 (1)).** Before each cell the
driver polls until no other live2 process is running, runs, then re-checks that nothing started
during it; its own child is identified by the `D216_CELL_MARKER` environment variable, never by a
cmdline pattern. loadavg is recorded as a magnitude at start and at end of every cell, and a cell
that was not alone end to end is recorded `alone=False` and is not cited as a bar.

### 3.1 The cells, with aloneness and loadavg as a magnitude

Seed 4, 16 devices, 1,200 s, posted knobs, planner wall-clock cutoff off, one cell per process,
`sys.executable` inside `conda run -n fmtk python`. All fourteen returned 0.

| tag | arm | kv | enf | wall s | load1 start -> end | alone | waited s | digest / rows |
|---|---|---|---|---|---|---|---|---|
| F0a_base_1x | covex-v6-base | 1.00 | off | 209.2 | 1.92 -> 2.47 | **False** | 0.0 | `af8befb9420ad86a` / 12,085 |
| F0_state_uo_1x | covex-v6-state-uo | 1.00 | off | 180.6 | 1.32 -> 1.16 | True | 420.4 | `9a4be873eb3c5fba` / 14,218 |
| F1_r3_final_1x | covex-v6-fair-final | 1.00 | off | 187.1 | 1.16 -> 1.46 | True | 0.0 | `5a03c2807da3681a` / 14,539 |
| F2_r4_final_1x | covex-v6-final | 1.00 | off | 187.3 | 1.46 -> 1.08 | True | 0.0 | `57bed6ace2eb07d1` / 14,509 |
| F3_r4_off_1x | covex-v6-final-off | 1.00 | off | 186.5 | 1.08 -> 1.07 | True | 0.0 | `5a03c2807da3681a` / 14,539 |
| F4_r3_final_kv025 | covex-v6-fair-final | 0.25 | off | 183.6 | 1.07 -> 1.35 | True | 0.0 | `5a03c2807da3681a` / 14,539 |
| F5_r4_final_kv025 | covex-v6-final | 0.25 | off | 187.0 | 1.35 -> 1.15 | True | 0.0 | `278da529349ff8c2` / 14,306 |
| F6_r4_off_kv025 | covex-v6-final-off | 0.25 | off | 185.7 | 1.15 -> 1.08 | True | 0.0 | `5a03c2807da3681a` / 14,539 |
| F7_r4_final_kv025_enf | covex-v6-final | 0.25 | **on** | 184.6 | 1.08 -> 1.01 | True | 0.0 | `278da529349ff8c2` / 14,306 |
| F8_r3_final_kv025_enf | covex-v6-fair-final | 0.25 | **on** | 185.7 | 1.01 -> 1.22 | True | 0.0 | `5a03c2807da3681a` / 14,539 |
| F9_r4_pdonly_kv025 | covex-v6-final-pdonly | 0.25 | off | 191.2 | 1.22 -> 1.27 | True | 0.0 | `278da529349ff8c2` / 14,306 |
| F10_r4_rqonly_kv025 | covex-v6-final-rqonly | 0.25 | off | 188.8 | 1.27 -> 1.33 | True | 0.0 | `57bed6ace2eb07d1` / 14,509 |
| F11_harm0_kv025 | covex-v6-final-harm0 | 0.25 | off | 188.3 | 1.33 -> 1.09 | True | 0.0 | `5a03c2807da3681a` / 14,539 |
| F12_marginhuge_kv025 | covex-v6-final-margin-huge | 0.25 | off | 189.3 | 1.09 -> 1.25 | True | 0.0 | `5a03c2807da3681a` / 14,539 |

**13 of 14 cells ran alone**, at loadavg 1.0 to 1.5 throughout. The one exception is `F0a_base_1x`:
the guard found a window, started it, and two foreign `cf_pd_one_cell.py` cells started during it.
It is recorded `alone=False`. It reproduced its committed digest exactly anyway, which is a datum
about load-insensitivity and not a licence - it is reported as a reproduction, not as a bar.

### 3.2 Positive controls: both PASS, and only one of them is admissible as a bar

| cell | arm | expected | measured | verdict |
|---|---|---|---|---|
| F0a_base_1x | covex-v6-base | `af8befb9420ad86a` / 12,085 | identical | **PASS**, and rung 0, so D216 (1) does not disqualify it - but `alone=False`, so it is a reproduction datum here too |
| F0_state_uo_1x | covex-v6-state-uo | `9a4be873eb3c5fba` / 14,218 | identical | **PASS**, alone at load 1.32. D216 (1) disallows it as a *bar* (unfixed rung-2 digest, `id(obs)` cache-key fix off), so it is a **reproduction datum** |

Both committed arms reproduce byte-identically through the new registration wrapper, so the
wrapper is **digest-neutral** and the check is not broken (CLAUDE.md check 7). Neither control is
cited as a bar in what follows: the bars this study uses are the ones it creates, F1 and F2, each
measured alone.

### 3.3 THE OFF-SWITCH IDENTITY, which the committed family failed by 711 rows, now HOLDS

| pair | differing setwise | differing positional | digests equal |
|---|---|---|---|
| F3 (`covex-v6-final-off`, 1x) vs F1 (`covex-v6-fair-final`, 1x) | **0** | **0** | yes |
| F6 (off, 0.25x) vs F4 (rung 3 final, 0.25x) | **0** | **0** | yes |

`5a03c2807da3681a` / 14,539 in all four cells. **Session D's section 3.0 escalation is closed for
the final ladder.** The cause it identified was real and is still in the code -
`arms_v6cfr3._Rung4Mixin._cf_engine` swaps the planner's deficit weight source unconditionally,
reading neither compound switch - but it no longer produces a difference, because final rung 3
wires the same source itself through `arms_final_ladder._PlannerFeedMixin`. The two use **different
wired-flags** (`_planner_deficit_wired` against `_rung4_planner_wired`), so rung 4 still re-swaps a
source that is already live; the second swap builds an equivalent `PlannerDeficitWeights` over the
same arm and the same feed, so it is a redundant construction and not a decision difference. That
is a verified result, not an inference: the cells were run precisely because the equivalence could
not be assumed from the code.

**Register note.** This is an **observed identity on one seed**, not a proof of equivalence for all
inputs. The redundant double-swap remains a latent hazard: anything that makes the two sources
non-equivalent would reopen the 711-row defect silently. It is reported, not fixed - `arms_v6cfr3`
is not mine.

### 3.4 DOES 0.25x BIND? Rung 4 yes, rung 3 no, and the coordinator-eviction channel no for either

| pair | what it isolates | setwise | positional | verdict |
|---|---|---|---|---|
| F2 vs F5 (rung 4, 1x vs 0.25x) | the binding test for rung 4 | **1,397** | 10,013 | **the pool binds** |
| F1 vs F4 (rung 3 final, 1x vs 0.25x) | the binding test for rung 3 | **0** | **0** | **does not bind** |
| F5 vs F7 (rung 4, eviction off vs on) | the coordinator-eviction channel | **0** | **0** | changes nothing |
| F4 vs F8 (rung 3, eviction off vs on) | the same channel, on a rung that reads no pool | **0** | **0** | changes nothing |
| F2 vs F3 (Step 2b at 1x) | does the switch reach a decision | **942** | 7,852 | **yes** |
| F5 vs F6 (Step 2b at 0.25x) | the same at the setting under test | **1,691** | 9,863 | **yes** |

**Rung 3 at 0.25x reproduces its own 1x digest with zero rows of difference.** Under the ruling of
2026-11-23 that is **capacity-blindness by design**, not a defect, and it is reported in Rule 2's
vocabulary as **INCONCLUSIVE - UNEXERCISED** for the proposition "the pool reaches a rung-3
decision", never as an equivalence and never as a finding about the policy. Section 1 is what makes
that reading legitimate rather than a cover: the reactive path is alive on this rung.

**And the enforcement channel fires hard and changes nothing, on both rungs.** The switch provably
arrived - read back off the coordinator instance as `True`, type `bool`, pool 15,736 - and
enforcement did real work:

| cell | epochs over cap | peak tokens | cap | tokens evicted to host (peak) | decisions changed |
|---|---|---|---|---|---|
| F7 (rung 4) | 12 of 12,001 | 16,747 | 15,736 | **43,613** | **0** |
| F8 (rung 3) | 14 of 12,001 | 16,747 | 15,736 | **47,588** | **0** |

Over 43,000 tokens of history were evicted to the host tier in each cell and not one decision
moved. This reproduces Session D's section 3.3 on the final ladder, and F8's 47,588 is the same
magnitude Session D measured. The reason is section 2's: the eviction moves `measured_tier`, the
belief follows only on a complete build (`cstate.py:207`), and the prices read a predicted tier
that no capacity signal reaches. Rule 2: **INCONCLUSIVE - UNEXERCISED**, and the diagnostic is
section 2's missing survival predictor, not a policy result.

### 3.5 Characteristic decisions by kind, with explicit zeros

| cell | pd_state_defers | pd_state_chunks | pd_request_defers | pd_protects | rd_question_defers | total | port rule |
|---|---|---|---|---|---|---|---|
| F2 rung 4 @ 1x | **0** | **0** | **0** | **0** | 4 | 4 | PASS |
| F5 rung 4 @ 0.25x | 6 | 3 | 15 | 19 | **0** | 43 | PASS |
| F7 rung 4 @ 0.25x enf | 6 | 3 | 15 | 19 | **0** | 43 | PASS |
| F9 pd-only @ 0.25x | 6 | 3 | 15 | 19 | **0** | 43 | PASS |
| F10 rq-only @ 0.25x | **0** | **0** | **0** | **0** | 4 | 4 | PASS |
| F11 harm0 @ 0.25x | **0** | **0** | **0** | **0** | **0** | **0** | see below |
| F12 margin-huge @ 0.25x | **0** | **0** | **0** | **0** | **0** | **0** | see below |

**The port rule passes on every scored arm**, and the explicit zeros are the finding. At 1x only
the question-deferral leg fires (4 decisions) and all four protect-and-defer kinds are **zero**; at
0.25x all four protect-and-defer kinds fire (43 decisions) and the question-deferral leg is
**zero**. The two legs change places with the memory setting, exactly as Session D measured, and
the leg table proves the mechanism:

| pair | setwise | reading |
|---|---|---|
| F9 (pd-only @ 0.25x) vs F6 (off) | 1,691 | protect-and-defer alone **is the whole arm** at 0.25x |
| F10 (rq-only @ 0.25x) vs F6 (off) | 942 | question-deferral alone is worth the same 942 the whole arm is worth at 1x |
| F5 (compound @ 0.25x) vs F9 (pd-only @ 0.25x) | **0** | **NOT ADDITIVE**: the compound at 0.25x is byte-identically pd-only, so the question-deferral leg contributes **nothing** there |
| F10 (rq-only @ 0.25x) vs F2 (compound @ 1x) | 0 (same digest `57bed6ace2eb07d1`) | and the compound at 1x is byte-identically rq-only |

So `rd_question_defers = 0` in the compound at 0.25x is **Rule 2 UNEXERCISED for that leg**:
protect-and-defer strictly pre-empts it (`rd_skipped_already_deferred = 19`, which is exactly
`pd_protects = 19`). It is not a negative about question deferral, which fires 4 times at 1x in the
same arm.

**The zeros in F11 and F12 are the controls working, and the assembler's flag must not be
misread.** `characteristic()` labels a zero total a stopping condition because that is the right
rule for an arm being **scored**. F11 and F12 are **negative controls** whose entire purpose is to
produce zero, and both collapse to the off arm byte-identically. The flag is noise on those two
rows and is left in the artifact rather than suppressed.

**AND THE LARGEST SINGLE LOSS IN THE RUNG-4 CHANNEL IS A DISCARDED DECISION, which grows with
memory pressure.** `pd_request_crossed_bar_unexpressible` is **2 at 1x and 27 at 0.25x** - a 13.5x
increase. The mechanism decided, crossed its own bar, and the harness had no channel to express it
in, against 15 request deferrals that were expressible. Rule 2: **unexpressible**, and under
pressure it is the dominant outcome of that leg rather than a rounding error. Also
`pd_protect_unexpressible_session_busy = 1`. Reported, not fixed.

**And the free-KV estimate does vary, and is never bound by the engine.**

| cell | pd_free_kv min | max | bound by belief | bound by engine metric |
|---|---|---|---|---|
| F2 @ 1x | 8,759 | 62,944 | 249 of 249 | **0** |
| F5 / F7 / F9 @ 0.25x | **0** | 15,736 | 260 of 260 | **0** |

The estimate is a live, varying quantity on both settings - not Session D's dry constant - because
the belief-side estimate is what carries it. The engine metric bound **zero** decisions in every
cell, which is D216 (2): nothing scraped `/metrics`, so `gpu_kv_fraction` is 0.0. Session D's
"sensitive to the pool's SIZE and blind to its OCCUPANCY" therefore still stands for the engine
channel, and the correct wording for rung 4 remains **"reacts to a smaller configured pool"**,
never "reacts to memory pressure".

### 3.6 Step 4 negative controls: both collapse to the off arm exactly

| control | what it disables | vs F6 (off @ 0.25x) | verdict |
|---|---|---|---|
| F11 `covex-v6-final-harm0` | harm zeroed at source on both legs | 0 setwise, 0 positional, same digest | **PASS** |
| F12 `covex-v6-final-margin-huge` | the bar alone scaled by 1e9 | 0 setwise, 0 positional, same digest | **PASS** |

Disabling the mechanism at its source removes the whole 1,691-decision difference, from both
directions independently. The 0.25x difference **is** the protect-and-defer mechanism and not a
side effect of the arm's construction.

### 3.7 Decision latency against the 20 ms budget, with the distribution - and ONE honest exception

Register: **flash CPU wall-clock inside the arm's `decide`** (`coordinator.py:2127`), on a dry cell
at loadavg 1.0 to 1.5. It is a **floor** on the live cost, not the live cost.

| cell | n | min | median | IQR | p90 | p99 | max | distinct | over 20 ms |
|---|---|---|---|---|---|---|---|---|---|
| F0a_base_1x | 12,085 | 0.0837 | 0.488 | 0.0247 | 0.5081 | 0.537 | 1.0372 | 1,182 | 0 |
| F0_state_uo_1x | 14,218 | 0.0926 | 0.8088 | 0.1367 | 0.8661 | 1.7772 | 3.649 | 3,161 | 0 |
| F1_r3_final_1x | 14,539 | 0.1069 | 0.8911 | 0.1824 | 0.9651 | 1.8776 | 3.8911 | 3,601 | 0 |
| F2_r4_final_1x | 14,509 | 0.1148 | 0.9037 | 0.1622 | 0.9718 | 1.9474 | 4.108 | 3,564 | 0 |
| F3_r4_off_1x | 14,539 | 0.1065 | 0.8949 | 0.1786 | 0.9626 | 1.8872 | **30.4152** | 3,531 | **2** |
| F4_r3_final_kv025 | 14,539 | 0.1116 | 0.8986 | 0.1821 | 0.9666 | 1.8852 | 3.8684 | 3,541 | 0 |
| F5_r4_final_kv025 | 14,306 | 0.1158 | 0.9051 | 0.1737 | 0.9803 | 1.9933 | 4.3761 | 3,660 | 0 |
| F6_r4_off_kv025 | 14,539 | 0.1036 | 0.8979 | 0.1673 | 0.9627 | 1.8853 | **30.3755** | 3,527 | **2** |
| F7_r4_final_kv025_enf | 14,306 | 0.1088 | 0.8894 | 0.1812 | 0.9612 | 1.9846 | 4.3553 | 3,487 | 0 |
| F8_r3_final_kv025_enf | 14,539 | 0.1042 | 0.8822 | 0.1855 | 0.9589 | 1.8828 | 3.7915 | 3,615 | 0 |
| F9_r4_pdonly_kv025 | 14,306 | 0.1148 | 0.9008 | 0.1823 | 0.9791 | 2.0035 | 4.4548 | 3,657 | 0 |
| F10_r4_rqonly_kv025 | 14,509 | 0.1064 | 0.8953 | 0.1825 | 0.9722 | 1.8916 | 3.9825 | 3,680 | 0 |
| F11_harm0_kv025 | 14,539 | 0.1145 | 0.8941 | 0.1783 | 0.9706 | 2.0009 | 4.2466 | 3,659 | 0 |
| F12_marginhuge_kv025 | 14,539 | 0.1106 | 0.8986 | 0.1812 | 0.9731 | 1.995 | 4.4223 | 3,616 | 0 |

**VERDICT: the 20 ms budget is met, with the worst p99 at 2.0035 ms, a factor of 10 inside it.**
**4 of 199,992 decisions** exceeded 20 ms, all four in two cells.

**And those four are a wall-clock artefact, which is provable here rather than arguable.** F3 and
F6 are the off arm; their decision rows are **byte-identical** to F1, F4 and F8 (all five are
`5a03c2807da3681a` / 14,539, 0 differing decisions). The same decision set has a 30.4 ms max in two
cells and a 3.8 to 3.9 ms max in the other three. An identical computation cannot have two
different costs for a policy reason, so the 30 ms tail is the shared CPU (scheduling or GC), not
the arm. Under CLAUDE.md check 7 this is the **control arm's own number being audited**, and the
audit says the spread is in the instrument. It is reported rather than dropped.

**Distribution sanity (check 3).** No cell is a constant where a distribution is expected: 1,182 to
3,680 distinct values per cell, IQR 0.025 to 0.186 ms. The one cell with a much tighter spread,
F0a_base_1x (IQR 0.0247, 1,182 distinct), is rung 0, which makes fewer kinds of decision - a real
difference in the arm, not a short circuit.

### 3.8 Gate A: NOT COMPUTABLE from these cells, and no number is invented for it

Gate A (D206 (1)) is **exposure** plus **overrun magnitude**, and exposure is the fraction of sent
recall requests whose **observed** over predicted first-token ratio exceeds the per-request q90
safety factor. A dry cell has no engine, so there is **no observed first token**, and the quantity
is not measurable here. Session D reached the same conclusion for the final rungs and this run does
not change it: the final rungs still have **no live cells**.

What is quotable is the committed rung-3 figure, labelled as that arm's and not the final rung's
(`results/orchestration/live2/d210_rung4_kv025/gatea_default_reproduction.json`): safety factor q90
**1.863404**, exposure **46 of 463 = 9.9352 percent** of sent recall requests, overrun magnitude
worst **1.503537x** of predicted service, quantile non-degenerate. **Gate A for `covex-v6-final` is
pending its first live cell.**

---

## 4. Results consistency check (CLAUDE.md), recorded before the conclusions

**1. Cross-check against committed measurements.**

| quantity | this run | prior run | source of prior | ratio | agree |
|---|---|---|---|---|---|
| `covex-v6-base` dry digest, s4, 1x | `af8befb9420ad86a` / 12,085 | same | `frozen_test/c5attr_digest_proofs.json` P1 | 1.00 | **agree** |
| `covex-v6-state-uo` dry digest, s4, 1x | `9a4be873eb3c5fba` / 14,218 | same | same | 1.00 | **agree** |
| committed rung-3 dry digest | **not reproduced, and not expected to be** | `12e4f73ce0ebd865` / 13,812 | `frozen_test/d190_rung4_r3_proofs.json` | 14,539 / 13,812 = 1.053 | **differ by design** |
| host tokens evicted at 0.25x enforced, rung 3 | 47,588 | 47,588 | Session D section 3.3 | 1.00 | **agree** |
| Gate A exposure | not measurable (dry) | 46 of 463 | `gatea_default_reproduction.json` | n/a | n/a |

The one disagreement is the rung-3 digest, and it is **below the 2x investigation threshold and
fully accounted for**: `covex-v6-fair-final` is not `covex-v6-fair-c5attr`. It adds the D188 (2)
`id(obs)` cache-key fix, the state planner on the deficit feed (D206 (2) measured that one change
as 687 of 60,473 state decisions) and the alert release re-check, all three decision-changing and
all three ruled into the final ladder. +727 rows is the size those three changes should produce.
**These cells create the final rung-3 bar; they do not re-measure the committed one.**

**2. Physical plausibility.** No latency, throughput or size measurement here is compared to a cost
curve: every number is a decision count, a digest, a token count from the coordinator's own
bookkeeping, or CPU wall-clock in `decide`. The one rate-like quantity, decision latency, is a
**floor** and is 10x inside its budget, so it cannot be a too-fast artefact of the kind check 2
exists to catch. The eviction magnitudes (16,747 peak against a 15,736 cap; 43,613 and 47,588 host
tokens) are internally consistent with the logical pool and match Session D.

**3. Distribution sanity.** Done in 3.7: 1,182 to 3,680 distinct latency values per cell, no
constant where a distribution is expected. The **artefact spread** is flagged at 3.7 rather than
quoted: a 30.4 ms max on a decision set that is byte-identical to three cells whose max is 3.9 ms
cannot mean what a max column implies, so it is named as instrument noise. The **averaged-out
effect** direction is handled by reporting the characteristic decisions **by kind with explicit
zeros** rather than only their total of 43, which is what shows that the two legs swap rather than
both working a little.

**4. Definition audit.** `kv 0.25` is `--kv-scale 0.25` scaling `test_live2_coord.GPU_KV`, giving a
**logical** pool of 15,736 tokens, read back off the coordinator instance; it is the same
definition `d210_kv025_one_cell` uses and is **not** the live engine condition (985 blocks x 16 =
15,760 engine, 15,744 max-model-len). `enforced` is `CoordState.kv_capacity_enforced` set on the
**instance** after construction, proved by read-back, the same way `run_live2_real.py:489` does it.
A `decision` is a row of the committed digest recipe in `cf_pd_one_cell`, with
`decision_latency_ms` stripped before any diff so the row set is exactly what the committed recipe
hashes. `rung 3` and `rung 4` here mean `covex-v6-fair-final` and `covex-v6-final`, **not** the
committed `covex-v6-fair-c5attr` and `covex-v6-cf-c5attr`; the two pairs have different digests and
are never compared as if they were the same object.

**5. Claim linkage.** Check 1 bears on D150 (the engine's per-request cached-token count corrects
the residency belief) and on D44 / D47 (residency cannot be commanded, it is verified from
telemetry): it **supports** them for rungs 2 and above and **weakens** any reading that extends
them to the baselines. It bears on D211 (host residency must be observed, not only native) and
**supports** its finding independently, from the counter side: `belief_to_host = 0` in 159 cells.
Check 2 bears on D55 and D150's survival prediction and **weakens** them: the model D150 names is
not implemented. Check 3 bears on D151 / D163 (the counterfactual's gain must concentrate on
decisions whose consequences land beyond the current period) and **supports** them at 0.25x, where
the whole 1,691-decision difference is protect-and-defer. Nothing measured here is scoped out by
`FORMULATION.md` - no KV is moved between tiers running different-sized models, and no cross-
architecture transfer is measured.

**6. Proxy validity.** One proxy is used and it is named: the **logical** `GPU_KV` pool stands for
the engine's KV pool. It actually measures the coordinator's own bookkeeping cap, not vLLM's
allocator. It is **valid for the decision question** (does a smaller configured pool reach a
decision) and **invalid for any physical claim** about eviction timing or reload cost, so no such
claim is made. A second, weaker proxy is flagged rather than used: the belief-side occupancy
estimate inside `_pd_free_kv` stands in for real occupancy, and it is the only thing that bound any
decision (260 of 260) because the engine metric was 0.0 throughout (D216 (2)). Every rung-4
magnitude here therefore rests on the belief estimate, which is **unvalidated against a real
occupancy reading** until the `/metrics` scrape lands.

**7. Validate the control, not only the result.** Three controls were audited before the
comparison, not after. (a) Two **positive controls** on committed arms both reproduced exactly, so
the registration wrapper is digest-neutral and the check is not broken. (b) The **off arm** - the
side of every Step 2b comparison that would otherwise go unexamined - was checked against its own
declared bar first, which is how 3.3 became an answer rather than an assumption; it is also the
control whose latency tail 3.7 caught. (c) The two **Step 4 controls** collapse to the off arm
byte-identically, from both directions. The shape Session D warns about - a comparator planning at
one price while charged another, or a broken control - was looked for on the control side and not
found.

---

## 5. Conclusions, with every null classified (CLAUDE.md Rule 2)

**(1) The reframing sentence is WRITABLE for rungs 2 and 3, and only at the full pool.** The
residency belief **is** corrected per request from engine-reported `cached_tokens`, the correction
is applied on rungs 2 and above, it varies (346 to `gpu`, 37 to `cold` over 35 cells), and six
named reads consume it in rung-2 and rung-3 pricing. **FIRES AND VARIES.** The limit that must
travel with the sentence: 0 of 23 committed reduced-pool live cells run an arm that applies it, so
at a reduced pool the path is **unmeasured**, and 383 applied corrections out of 53,673 offered is a
thin channel, about one demotion per cell.

**(2) For rung 0, rung 1 and every paper baseline including b7, the sentence is FALSE and must not
be written.** 7,525 corrections changed a belief and all 7,525 were reverted by the observe-only
gate. Rule 2: **INCONCLUSIVE - UNEXPRESSIBLE.** This is a labelling obligation, not a defect to
fix: the gate exists so that cells before and after it stay comparable, and a published baseline
does not ship a telemetry corrector.

**(3) ESCALATION: the correction can never say `host`.** `belief_to_host = 0` in all 159 live cells,
because the `host` branch needs a per-request signal that D209 (4) measured does not exist on this
engine. **CONSTANT in the sense that matters.** Consequence: a host-resident history is priced as a
cold rebuild (conservative for cost, wrong for a reload decision), and `plan_state`'s RELOAD
candidate is structurally unexercised. This is D211 confirmed from a second direction.

**(4) ESCALATION: there is no survival predictor.** Check 2's answer is **NO** with file and line.
The predicted cache state is the argmax of a one-hot belief holding the **last observed tier**; it
consults no pool size, no occupancy and no time. M5's step function, which D150 names as the model
to predict survival from, **is not implemented anywhere in live2** - so the honest statement is not
"it predicts on the wrong variable" but "it does not predict". The M6 straddling guard that could
express a partial prefix is present and **unreachable**, because every belief writer is one-hot.
The accuracy fix is costed in 2.1 at roughly one session plus 6 dry cells and a rung-2-to-4 re-bar,
**blocked on the D216 (2) `/metrics` scrape**, and is **NOT BUILT**: it needs a ruling.

**(5) Session D's 711-row contamination is CURED in the final ladder.** The off arm is byte-
identically final rung 3 at both memory settings, 0 differing decisions. The redundant double-swap
that made it safe is a latent hazard and is reported, not fixed.

**(6) Rung 4 binds at 0.25x; rung 3 does not; the coordinator-eviction channel binds for neither.**
1,397 decisions move for rung 4 between 1x and 0.25x, and the Step 4 controls show that difference
**is** the mechanism. Rung 3 reproduces its 1x digest exactly: **INCONCLUSIVE - UNEXERCISED**, which
the ruling makes by-design rather than a defect. Enforcement evicted 43,613 and 47,588 host tokens
and changed **0** decisions: also **INCONCLUSIVE - UNEXERCISED**, and its diagnostic is conclusion
(4), the missing predictor.

**(7) The two legs swap places and are NOT additive.** At 1x the compound is byte-identically
question-deferral alone (4 deferrals, all four protect-and-defer kinds zero); at 0.25x it is byte-
identically protect-and-defer alone (43 decisions, question deferral zero, pre-empted 19 times).
`rd_question_defers = 0` at 0.25x is **UNEXERCISED for that leg**, not a negative.

**(8) The 20 ms budget is met with a factor of 10 to spare, and the 4 exceedances are instrument
noise, shown rather than asserted.** Worst p99 2.0035 ms; 4 of 199,992 decisions over 20 ms, all in
two cells whose decision rows are byte-identical to three cells with a 3.9 ms max.

**(9) Gate A for `covex-v6-final` is NOT COMPUTABLE from dry cells and no number is invented.**

**(10) `pd_request_crossed_bar_unexpressible` grows 2 -> 27 from 1x to 0.25x**, so under memory
pressure the dominant outcome of the request-deferral leg is a decision the harness cannot express.
Rule 2 **unexpressible**, reported, not fixed.

---

## 6. Proposed row text (research/*.md and results/INDEX.md are the user's; nothing below is applied)

### 6.1 Proposed `research/policy_design_log.md` row

| D217 | 2026-11-23 | THE REACTIVE RESIDENCY PATH IS REAL ON RUNGS 2 AND 3, ABSENT ON THE BASELINES, AND THERE IS NO SURVIVAL PREDICTOR. (1) The belief IS corrected per request from engine `cached_tokens` and the correction REACHES rung-2 and rung-3 pricing: over 35 committed live cells, 53,673 corrections offered, 383 applied, 346 to gpu and 37 to cold, consumed at coordinator.py:1161, :1238, :1294, :1331 and arms_v6state.py:416. So "rungs 2 and 3 adapt to memory pressure only reactively, through engine telemetry" is WRITABLE for those rungs, with two limits that travel with it: the channel is thin (about one demotion per cell) and 0 of 23 committed reduced-pool live cells run an arm that applies it, so at a reduced pool it is UNMEASURED. (2) For rung 0, rung 1 and every paper baseline including b7-edf-feasibility the sentence is FALSE: 7,525 corrections changed a belief and all 7,525 were reverted by the observe-only gate (coordinator.py:1803). Rule 2 unexpressible; a labelling obligation, not a defect. (3) belief_to_host = 0 in all 159 live cells: the corrector can say gpu or cold and never host (D209 (4) - no per-request host signal exists), so host-warm is priced as cold and RELOAD is structurally unexercised. D211 confirmed from the counter side. (4) CHECK 2 IS NO: the predicted cache state used in state pricing (touch_policy.py:39, :63, :210) and in b7 (baselines/constructed.py:184) consults no pool size, no occupancy and no time - it is the argmax of a one-hot belief holding the last observed tier. M5's step function is NOT IMPLEMENTED anywhere in live2, so this is an absent predictor rather than a wrong variable; the M6 straddling guard is present and unreachable because every belief writer is one-hot. Accuracy fix costed at about one session plus 6 dry cells and a rung-2-to-4 re-bar, blocked on the D216 (2) metrics scrape, NOT BUILT pending a ruling. (5) The final ladder CURES Session D's 711-row contamination: covex-v6-final-off is byte-identically covex-v6-fair-final at 1x and at 0.25x (5a03c2807da3681a / 14,539, 0 differing decisions), because final rung 3 wires the planner feed itself; the redundant double-swap remains a latent hazard. (6) FINAL-LADDER 0.25x: rung 4 binds (1,397 decisions between 1x and 0.25x, Step 4 controls both collapse to the off arm exactly), rung 3 does not (0 rows, Rule 2 unexercised, by design under the 2026-11-23 ruling), and coordinator eviction binds for neither despite 43,613 and 47,588 host tokens evicted (Rule 2 unexercised, diagnostic = item 4). The two legs swap places and are not additive. Decision latency worst p99 2.0035 ms, 4 of 199,992 over 20 ms and all four shown to be instrument noise. Gate A for covex-v6-final not computable from dry cells. | Flash Session, 13 of 14 cells ALONE under D216 (1), measured at 87ca3503. |

### 6.2 Proposed `research/EXPERIMENTS.md` row

| E-id | StudyD216-KV025 |
|---|---|
| question | Does an eviction reach rung-2 / rung-3 pricing and b7 through the residency belief; does the survival prediction consult the GPU-KV pool; and do the final rungs respond to a 0.25x pool? |
| scripts | `experiments/orchestration/live2/d216_belief_correction_census.py`, `d216_survival_predictor_readsites.py`, `d216_final_kv025_one_cell.py`, `d216_final_kv025_driver.py`, `d216_final_kv025_report.py` |
| output | `results/orchestration/live2/d216_final_kv025/` (census, read-site proof, 14 cells, assembled report) |
| verdict | Check 1 FIRES AND VARIES on rungs 2+ / UNEXPRESSIBLE on rung 0, rung 1 and all baselines / CONSTANT for host everywhere. Check 2 NO, and the predictor is absent rather than wrong. Check 3: off-switch identity holds, rung 4 binds at 0.25x, rung 3 does not (unexercised, by design), eviction channel unexercised, Step 4 both controls pass, 20 ms budget met. |
| status | COMPLETE (dry); Gate A and the reduced-pool reactive path pending live cells |
| consistency_check | PASS, 7 of 7 recorded in report section 4 |
| mechanism_verification | Step 2b run before scoring (both off-switch identities and both Step 2b pairs); Step 4 run as two named-arm controls, both collapse; characteristic decisions reported by kind with explicit zeros |

### 6.3 Proposed `results/INDEX.md` rows

| file | script | model | device | n | headline |
|---|---|---|---|---|---|
| `results/orchestration/live2/d216_final_kv025/belief_correction_census.json` | `d216_belief_correction_census.py` | n/a (counter census) | n/a | 159 live cells | The belief correction from engine `cached_tokens` is APPLIED on rungs 2+ (383 of 53,673, 37 to cold) and REVERTED on rung 0, rung 1 and all 14 paper baselines (7,525 of 7,525); `belief_to_host` = 0 everywhere |
| `results/orchestration/live2/d216_final_kv025/survival_predictor_readsites.json` | `d216_survival_predictor_readsites.py` | n/a (source census) | n/a | 10 functions, 7 belief writers | The predicted cache state consults no pool size, occupancy or time; M5's step function is not implemented; the M6 straddling guard is unreachable because every belief writer is one-hot |
| `results/orchestration/live2/d216_final_kv025/d216_final_kv025_report.json` | `d216_final_kv025_report.py` | n/a (dry, logical pool) | flash CPU | 14 cells, seed 4, n=16, 1,200 s | Final-ladder off-switch identity holds at both settings (0 rows); rung 4 binds at 0.25x (1,397), rung 3 does not (0); eviction of 43,613 / 47,588 host tokens changes 0 decisions; Step 4 both controls collapse; worst p99 2.0035 ms |

### 6.4 Proposed `research/STATUS.md` edit

Last-updated date to 2026-11-23, and one line: the reactive residency path is verified live on
rungs 2 and 3 at the full pool and unmeasured at a reduced one; the survival predictor is absent
and a ruling is pending on the costed accuracy fix.

---

## 7. What is left undone, named plainly

1. **The check-2 accuracy fix is NOT BUILT.** It needs a ruling, and it is blocked on the D216 (2)
   `/metrics` scrape landing on origin.
2. **No reduced-pool LIVE cell exists on any arm that applies the belief correction.** Until one
   runs, the reactive path is verified at 1x only. This is the single biggest gap behind the
   reframing sentence.
3. **Gate A for `covex-v6-final`** is pending its first live cell.
4. **One cell, `F0a_base_1x`, was not alone** and is reported as a reproduction datum rather than a
   bar.
5. **Single seed (s4).** A one-seed result is not a four-seed result and is not reported as one.
6. **Three things found and deliberately not fixed, because the files are not mine:** the redundant
   planner double-swap in `arms_v6cfr3` (latent, would silently reopen the 711-row defect),
   `pd_request_crossed_bar_unexpressible` growing to 27 at 0.25x, and the unreachable
   `PURE_TIER_MIN_BELIEF` guard in `touch_policy`.
7. **The `.rows.json` intermediates** (about 7 MB each) were moved out of the results tree after the
   report was assembled and are not committed.
