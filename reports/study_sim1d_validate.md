# StudySIM1d-validate

**Pre-registered 2026-11-13 in `research/EXPERIMENTS.md` before any Part A, B or C computation.**
Offline simulation and analysis over committed measurements. CPU only on the flash host: no GPU,
no model server, no inference. No INVALID result is used. Our scheduler is not in this study and
no arm is declared best.

Three questions, answered in order.

| part | question | verdict |
|---|---|---|
| A | why do several StudySIM1c-scoped arms look degenerate? | **every symptom is explained and none is random.** Of 17 arms audited, 5 are FAITHFUL, 7 are ADAPTER BUGS and 6 are SCOPE INTERACTIONS (streamscout is both). **8 proposed changes, affecting 12 arms, are listed and NOT applied**, because each changes what an arm decides - the pre-registered stopping condition |
| B | is StudySIM1b's overlap cost real, and does modelling it fix the gate? | **the cost is real, mode-independent and BLOCKING**, fitted on cells in no gate cell. **The gate still fails**: 18/29 and 10/16 OFF, 19/29 and 11/16 with it on. The N = 3 over-queueing is diagnosed, not fixed |
| C | does the simulator reproduce StudySLICE1 Part B, which it has never seen? | **FAIL in all three configurations**, 15/19 against an 80 % bar and the C1a ordering wrong. The failing policy, condition and mechanism are named and the study stops there |

---

## 1. Part A - the arm audit

One representative cell, fixed before any run: **balanced mix, F = 4, deadline 5 s, seed 0**
(trace digest `990f7113de23a2eb`, 2,664.75 s, 4 episodic streams, 4 recall sessions). Every arm
is replayed on it through a transparent proxy that records every action by request class and, for
the first five episodic and first five recall decisions, the inputs the arm read, the rule it
computed, the action and why the alternative lost. The traces are in
`results/orchestration/sim1d/sim1d_part_a.json`.

The specification's cell is at deadline 5 s, where four of the reported symptoms do not appear.
The committed StudySIM1c sweep says where they do, and one symptom-bearing cell (the same mix and
fleet at **deadline 2 s**) is traced as well, so every mechanism below is shown and not inferred.

### 1.1 The audit table

| arm | symptom | class | evidence | fix or proposed change |
|---|---|---|---|---|
| **B9-noHost** | mAP exactly 0.4776, 0 episodic cloud calls | **(2) ADAPTER BUG** in component (ii) | the R3 readiness gate PASSES (mean 2.96 of 4 streams, mean rho 0.96 against a 0.35 threshold), and component (ii)'s MaxMin allocation still returns `local` for every stream in all 27 probes | PROPOSED, not applied: see 1.2 |
| **videostorm/maxmin** | mAP exactly 0.4776 | **(2) ADAPTER BUG** | utility(local) = **+0.01043**, utility(cloud) = **-10.234** at every epoch; capacity R = 264 GPU-s/s is never binding | PROPOSED, not applied |
| **videostorm/maxsum** | mAP exactly 0.4776 | **(2) ADAPTER BUG** | identical numbers; the objective is not what decides | PROPOSED, not applied |
| **covstream** | mAP exactly 0.4776 | **(2) ADAPTER BUG** | the adapter emits `StreamAction(sid, "local")` unconditionally; nothing is computed from the observation | PROPOSED, not applied |
| **simplestream** | mAP exactly 0.4776 | **(2) ADAPTER BUG** | same literal; its own docstring says "episodic streams take the documented default", and `DEFAULTS["episodic_mode"]` is `"cloud"` | PROPOSED, not applied |
| **streamscout** | mAP exactly 0.4776, and all 83 recall queries answered on the DEVICE | **(2) ADAPTER BUG** + **(3) SCOPE** | same literal for streams; for recall, `device_answer_confidence` is always `None`, so the cascade's stage-0 branch `if stage == 0 and conf is None` fires and the query never reaches the cloud | PROPOSED, not applied |
| **hybrid-llm** | mAP exactly 0.4776 | **(1) FAITHFUL** | the router's p_w is **0.679 to 0.846** over the whole run against its 0.5 threshold, so "keep local" is the rule's own answer everywhere | none; a declared limitation instead |
| **B7-edf-feasibility** | recall timely accuracy 0.000, starvation 1.000 | **(1) FAITHFUL**, with a self-fulfilling dynamic | at deadline 2 s: predicted service **2.4556 s** against slack **2.000 s** -> DEFER, then REJECT. 84 DEFERs and 84 REJECTs, 0 CLOUD | none; the dynamic is reported |
| **thinking-qwenvl-atdm** | timely accuracy 0.000 in **all 45** committed cells | **(3) SCOPE INTERACTION** / CONSTANT link | rho = \|distinct representations in the inventory\| / 3, and the harness builds every inventory from two `EvidenceItem`s that **both** carry representation `D2`, so rho = **0.3333 in every query of every cell** against a 0.6 threshold. 101,553 DEFERs, 0 answers | PROPOSED, not applied |
| **kvflow** | timely 0.0006 at deadline 2 s | **(3) SCOPE INTERACTION** | it emits `OFFLOAD_TO_HOST`, which the scope flag maps to `EVICT`, so no session is ever GPU-warm and **all 83 recall requests are COLD** (against 4 cold + 79 escalations for B9) | PROPOSED, not applied |
| **preble** | timely 0.0006 at deadline 2 s | **(3) SCOPE INTERACTION** | same eviction path; separately, its admission branch never fires: load pressure is **0.0046 mean, 0.125 max** against a 0.9 threshold | PROPOSED, not applied |
| **rh8-demand-aware-causal** | timely 0.0006 at deadline 2 s | **(3) SCOPE INTERACTION** | same eviction path; and `k = round(0.25 x n_sessions)` is **0** whenever a cell has fewer than 2 sessions, so nothing is kept warm by construction | PROPOSED, not applied |
| **B10-blocking-aware-admission** | agrees with always-cloud-fcfs to 4 decimals | **(3) SCOPE INTERACTION** | **0 DEFERs in 83 decisions.** `affected = [s for s in on_cloud if s.cadence_s <= T]` is empty whenever T < 0.5 s, and `_tolerable_hold_s` raises `KeyError` for `32BI_N1` and returns `inf`: **`n_d_star_finite` is 0 in all 27 probes**, so `T >= worst` is never true | PROPOSED, not applied |
| **B11-naive-slicing** | agrees to 4 decimals | **(2) ADAPTER BUG** in the harness ordering | it emits 4 sliced MATERIALIZEs, but the engine records **`slice_steps` = 0**: `run.py` applies recall actions BEFORE session actions, so the CLOUD recall has already called `eng.place(session, "gpu")` and the MATERIALIZE finds the session resident and submits nothing | PROPOSED, not applied |
| **B3-best-static** | agrees to 4 decimals | **(1) FAITHFUL** | 9,215 cloud and 1,445 local stream actions; the static choice is the cloud one almost everywhere | none |
| **tuned-engine** | agrees to 4 decimals | **(1) FAITHFUL** | all-cloud by design | none |
| **always-cloud-fcfs** | the reference | **(1) FAITHFUL** | all-cloud by definition | none |

### 1.2 B9-noHost first: the component and the precedence step, with numbers

The specification asks which component routes every episodic call to the device. It is **not
component (iv)**, the host-offload one the scope flag disables. It is **component (ii)**, the
VideoStorm MaxMin rate allocation, at the **first** precedence step - "(ii) decides the rate, (i)
may only DOWNGRADE it".

The R3-Streaming readiness gate in front of it passes: over 27 probes spread across the run,
`n_passed_readiness_gate` averages **2.96 of 4** streams and mean rho is **0.963** against the
0.35 threshold. What never passes is the allocation behind it:

| quantity | value, constant across all 27 probes |
|---|---|
| `n_cloud_after_component_ii` | **0** of 4 |
| `n_cloud_after_component_i` | 0 of 4 |
| `n_cloud_final` | 0 of 4 |
| utility of the `local` configuration | **+0.010432** |
| utility of `cloud/32BI_N1@0.5` at allocation 0 | **-10.234** |
| predicted lag of that cloud configuration | **10.75 s** against `lag_max_s` = 0.5 |
| quality gap, cloud minus local | **+0.0057** |

The arithmetic, from Equations 1 and 2 of the paper as `reconstructed/videostorm.py` implements
them:

```
U = u_base + alpha_q * max(Q - Q_min, 0) - alpha_l * max(L - L_max, 0)
L_cloud(a = 0) = lag_s + horizon_s - 0   = 0.75 + 10.0 = 10.75 s      (Eq. 2, demand > 0)
L_local        = max(lag_s - horizon_s, 0) = 0                        (Eq. 2, demand <= 0)
U_cloud = 1.0 * 0.01613 - 1.0 * (10.75 - 0.5) = -10.234
U_local = 1.0 * 0.01043 - 1.0 * 0           = +0.01043
```

With `alpha_q = alpha_l = 1.0`, the **lag penalty is 1,800 times the quality gap**. MaxMin then
stops after a handful of steps: `_best_config` returns `local` at every allocation, so the greedy
loop's own "no further improvement available" break (`if u <= cur and alloc > 0: break`) fires
with `a_k = 0.01` and the configuration still local. Capacity never enters it - R is 264
GPU-seconds per wall second against a demand of 0.135.

**The cause is a units mismatch the card already flags.** `cards/videostorm.md` records that the
paper's L is a queue BACKLOG while ours is the tier's delivery HOLD SHIFT, a constant 0.0-0.75 s
property of the configuration. Equation 2 is a backlog recursion: it adds the whole horizon each
period and subtracts what the allocation drains. Feeding a hold shift into it makes every cloud
configuration look 10 s behind.

The same code is component (ii) of B9, which is why the two arms fail identically.

### 1.3 B10 holds nothing and B11 slices nothing

The specification asks for a traced cold recall showing that B11 actually emits slices and B10
actually holds. **Neither does**, and the counts say so:

| arm | policy-level | engine-level |
|---|---|---|
| B10 | 83 CLOUD, **0 DEFER**, 4 MATERIALIZE (monolithic) | `slice_steps` 0, 9,115 steps, 1,302.82 GPU-s |
| B11 | 83 CLOUD, **4 MATERIALIZE with `slice_tokens = 2048`** | **`slice_steps` 0**, 9,121 steps, 1,302.88 GPU-s |
| always-cloud-fcfs | 83 CLOUD | `slice_steps` 0, **9,115 steps, 1,302.82 GPU-s** |

B10 and always-cloud-fcfs are **bit-identical** in engine work. B11 differs by six steps and
0.06 GPU-seconds.

B10's rule cannot fire for two independent reasons, both visible in the probes: `T` (the
predicted non-preemptive engine time) averages 0.014 s and peaks at 0.383 s, so `affected`, which
requires `s.cadence_s <= T` against a 0.5 s cadence, is almost always empty; and when it is not,
`profiles.d_star_s("32BI_N1", 0.5, ...)` raises `KeyError` and `_tolerable_hold_s` returns
infinity, so `n_d_star_finite` is **0 in all 27 probes**.

B11's slices are lost to an ordering in the harness, not to anything in the arm: `run.py` applies
recall actions before session actions, and the CLOUD recall decision already calls
`eng.place(session, tokens, "gpu")`, so by the time `MATERIALIZE(slice_tokens = 2048)` is
processed the session is resident and the `if xa.session_id not in eng.gpu` guard skips the
submit. The arm declares 4 sliced materializations; the engine executes none.

### 1.4 Why the five arms agree to four decimals

They agree because the recall traffic they differ over is a rounding error against the episodic
traffic that dominates challenge mAP:

| quantity | value in the representative cell |
|---|---|
| episodic requests completed | **18,127** |
| recall-class requests completed | **83** (4 cold + 79 warm escalations) |
| episodic requests whose engine window overlaps any recall-class request | **239** |
| fraction of episodic requests affected | **1.32 %** |
| wall time the recall class occupies | 29.0 s of a 2,664.75 s run (1.09 %) |

An admission rule can only move the 1.32 %, and only by a fraction of their TTFT. In the
committed StudySIM1c sweep the five arms agree to four decimals in **18 of 45 cells**, with a
maximum mAP spread of **0.0246** and a maximum timely-accuracy spread of **0.220** - so the
agreement is real but not universal, and it is widest where recall load is highest.

### 1.5 STOP AND ASK - the 8 proposed changes, affecting 12 arms, not applied

Every finding above that is not FAITHFUL would require a change to **what an arm decides**, not to
how a decision is computed. The pre-registered stopping condition therefore fired and **nothing
was changed**. The proposals, for the user to accept or reject:

| # | arm(s) | proposed change | what it would alter |
|---|---|---|---|
| 1 | videostorm/maxmin, videostorm/maxsum, B9-noHost component (ii) | pass the configuration's own hold shift as the PREDICTED lag instead of running a constant through Eq. 2's backlog recursion, or set `alpha_l` so the lag term is commensurate with the quality term | all three arms would put streams on the cloud |
| 2 | covstream, simplestream, streamscout | make the stream action follow `DEFAULTS["episodic_mode"]` as their docstrings say, instead of a literal `"local"` | three arms move off the device-only value |
| 3 | streamscout | supply `device_answer_confidence`, or change the stage-0 `conf is None` branch | its recall decisions move from DEVICE to CLOUD |
| 4 | thinking-qwenvl-atdm | give the evidence inventory more than one representation, or compute rho from the evidence TIERS rather than the representation names | its recall decisions become non-degenerate |
| 5 | kvflow, preble, rh8-demand-aware-causal | in the scoped world, map `OFFLOAD_TO_HOST` to `KEEP_GPU_WARM` rather than `EVICT` for arms whose intent is "retain elsewhere" | their recalls stop being universally cold |
| 6 | rh8-demand-aware-causal | use `ceil` rather than `round` for the HIGH_FRAC warm slot count | at least one session stays warm in small cells |
| 7 | B10 | register a `d_star_s` entry for `32BI_N1` / `32BI_N3`, and read `affected` from streams due within T rather than from `cadence_s <= T` | B10 would start deferring |
| 8 | B11 | apply session actions before recall actions in `run.py`, or let MATERIALIZE pre-empt a resident placement | B11 would start slicing |

Items 1-8 cover 12 distinct arms. **Do not read any StudySIM1c number for those arms as a
statement about the published method**; read it as a statement about this adaptation in this
scoped world.

---

## 2. Part B - the mode-independent overlap cost

### 2.1 Which committed cells are in StudySIM1's gate

A committed cell is **in the gate** iff its `(kv mode, k, r)` is one of `calibrate.CONDITIONS`'
eight conditions AND it was measured at vLLM 0.31.0 defaults - StudyE10c's E0, StudyE10e's P0, and
every StudyE10b cell. The rule is deliberately conservative: it marks a cell in-gate on the
condition alone, without checking whether a capacity ladder actually reached that level.

| | count |
|---|---|
| committed cells in StudyE10b / E10c / E10e | 155 |
| **in StudySIM1's gate** | **58** |
| **held out** | **97** |
| gate references | 29 p99 cells, 16 capacity ladders, 8 p50 cells |

The gate's eight conditions are C0, C1-r05, C1-r10, KVGPU-k4, KVGPU-k8, KVHOST-k8, KVHOST-k16 and
C4, each at N = 1 and N = 3, over the ladders (10, 20, 25, 30, 40, 50) % at N = 1 and
(10, 20, 25, 35, 50) % at N = 3. The full inventory, cell by cell with its reason, is in
`sim1d_part_b_fit.json`.

### 2.2 What was used for the fit

Only held-out cells with k > 0, since a cell with no warm session has no overlap to measure:
**29 usable cells, 21,035 episodic requests**, exactly the candidates the specification named.

- StudyE10b **KV-GPU k = 2** (N1 L25, N3 L50) - k = 2 is not one of the eight conditions.
- StudyE10b KV-GPU k = 16 and KV-GPU k = 8 r = 0.1 - neither combination is a condition.
- StudyE10c **KV-HOST C2 / C3 / C4 at engine configurations E1, E2 and E4** (24 cells) and
  StudyE10e's **P1 / P2 / P3** C4 cells - configurations the gate never reproduces.

StudySIM1b's own labelling is reused unchanged: an episodic request is OVERLAP if its
`[submit, submit + ttft]` intersects a warm recall request's interval, and requests overlapping a
COLD recall are excluded, because that hold is already modelled.

### 2.3 The form, pre-registered before the fit

Two candidates were written down before any number was computed:

- **(a) blocking**, a per-step cost added to every engine step containing a warm recall's
  prefill, charged to all requests in that step. It is engine time, so queueing AMPLIFIES it and
  the OVERLAP-minus-CLEAR difference must GROW with load.
- **(b) non-blocking**, a fixed added delay per episodic request per concurrent in-flight warm
  request. Queueing does not amplify it, so the difference must be FLAT or FALL with load.

The decision rule, StudySIM1b's own: regress the per-cell difference on the cell's load fraction
across the held-out cells; a bootstrap CI on the slope that excludes zero from above selects (a).

| load | per-cell OVERLAP-minus-CLEAR median difference, s |
|---|---|
| 10 % | 0.0316, 0.0353, 0.0396, 0.0422, 0.0477, 0.0478, 0.0484, 0.0506, 0.0563, 0.0574, 0.0620, 0.0621 |
| 20 % | 0.0509, 0.0518, 0.0540, 0.0613, 0.0623, 0.0666 |
| 25 % | 0.0472, 0.0500, 0.0526, 0.0597 |
| 30 % | 0.0580, 0.0581, 0.0594 |
| 40 % | 0.0631, 0.0646, 0.0663 |
| 50 % | 0.0883 |

**Slope +0.0656 s per unit load, bootstrap CI [+0.0329, +0.0921], excluding zero.**
**Form (a), BLOCKING, is selected.** This is the one place StudySIM1d disagrees with
StudySIM1b's reading of the same effect: SIM1b judged the HOST-minus-GPU MODE cost non-blocking
because it vanished at 75-90 % load, and that finding stands. The OVERLAP cost is a different
quantity and behaves the opposite way.

### 2.4 It is mode-independent

| KV mode | held-out cells | median difference | range |
|---|---|---|---|
| KV-GPU (StudyE10b k = 2) | 2 | **0.0740 s** | 0.0597 to 0.0883 |
| KV-HOST (StudyE10c E1/E2/E4, StudyE10e P1/P2/P3) | 27 | **0.0540 s** | 0.0316 to 0.0666 |

The two modes differ by less than the spread within either, which is what StudySIM1b found on a
different (in-gate) cell set: +0.0526 s in KV-HOST against +0.0574 s in its cell-matched KV-GPU
control. **The GPU side rests on two cells only**, and that is a declared weakness: StudyE10b ran
only two KV-GPU k = 2 cells, and every other KV-GPU k > 0 cell either is in the gate or collapses.

### 2.5 The magnitude, and a pre-registered estimator that does not survive contact

The decision rule named the OLS coefficient on the number of concurrent in-flight warm requests.
Run as written over all 21,035 held-out requests it returns:

| coefficient | beta | CI |
|---|---|---|
| intercept | -1.365 | [-2.201, -0.552] |
| **n_concurrent** | **+0.8465** | [+0.825, +0.868] |
| load_fraction | +5.254 | [+2.097, +8.430] |

R2 = 0.813, n = 21,035. **This value is reported and is NOT used.** The held-out set contains
StudyE10b's KV-GPU k = 16 cells, where a warm miss re-prefills the WHOLE history; those
re-prefills are long and concurrent at the same time, so the coefficient absorbs StudyE10b's
collapse chain, which the model already has. It returns 0.85 s per concurrent request against a
measured OVERLAP-minus-CLEAR difference of 0.032-0.088 s - two orders out. Dropping the 1,193
requests above 5 s (3 collapse cells: `E10B_KVGPU_k16_r0_N1_L25`, `..._N3_L25`, `..._N3_L50`)
gives `n_concurrent` = **+0.0398 s**, which is in range.

The estimator is also the wrong SHAPE: form (a) is a per-STEP cost, and a per-request coefficient
cannot be read into it. The registered value is therefore taken the way a per-step cost must be -
at the **lowest load on the ladder, where queueing amplification is smallest**:

> **`OVERLAP_STEP_COST_S = 0.0481 s`**, the median of the **12 held-out cells at 10 % load**
> listed in 2.3. No gate cell was used. No other constant was touched.

It is added to `engine.py` as an option that **defaults to 0.0**, charged in `Engine.step()` once
on any step in which a request of kind `append` or `escalation` computed tokens.

### 2.6 The gate, run once per configuration

Same 29 p99 cells, 16 ladders, 8 p50 cells, same 5 arrival seeds, same +/-25 % and 80 % bars,
same collapse rule.

| configuration | p99 cells | capacity ladders | gate |
|---|---|---|---|
| **off** (reproduces StudySIM1) | 18/29 (62 %) | 10/16 (62 %) | FAIL |
| **host mode cost only** (StudySIM1b) | 20/29 (69 %) | 11/16 (69 %) | FAIL |
| **overlap cost only** (new) | **19/29 (66 %)** | **11/16 (69 %)** | **FAIL** |
| **both** | **19/29 (66 %)** | **11/16 (69 %)** | **FAIL** |

**Modelling the overlap cost does not fix the gate, and on p99 it is slightly worse than the host
mode cost alone.** The reason is visible cell by cell, and it is not noise: the cost helps every
cell the model UNDER-predicts and hurts every cell it OVER-predicts.

| cell | measured | off | mode only | overlap only | both |
|---|---|---|---|---|---|
| KVGPU-k4 N1 25 % | 0.536 | 0.339 (0.63) | 0.339 (0.63) | **0.368 (0.69)** | 0.368 (0.69) |
| KVHOST-k16 N1 10 % | 0.440 | 0.309 (0.70) | **agrees** | **agrees** | agrees |
| KVHOST-k16 N1 20 % | 0.478 | 0.351 (0.73) | **agrees** | **agrees** | agrees |
| KVHOST-k8 N1 25 % | 0.339 | agrees | agrees | **0.427 (1.26) broken** | **0.466 (1.37) broken** |
| KVHOST-k8 N3 25 % | 0.516 | 0.685 (1.33) | 0.724 (1.40) | 0.785 (1.52) | **0.824 (1.60)** |
| KVHOST-k16 N3 25 % | 0.594 | 0.795 (1.34) | 0.833 (1.40) | 0.845 (1.42) | **0.883 (1.49)** |

Four of the five remaining ladder disagreements and three of the nine remaining cell
disagreements are the N = 3 over-queueing, which section 2.8 diagnoses. The rest are C4 at 10 and
25 % (the model does not saturate where the measurement does) and C1-r05 N1 10 %.

### 2.7 Negative controls

| control | rule | result |
|---|---|---|
| 1a | with the overlap cost at 0 the gate must reproduce StudySIM1b's OFF run cell for cell | **PASS, 0 mismatches of 29, bit-exact** |
| 1b | with only the host mode cost on it must reproduce StudySIM1b's ON run | **PASS, 0 mismatches of 29, bit-exact** |
| 2 | the cost is charged only on a step carrying a WARM recall prefill, so every k = 0 cell (C0, C1-r05, C1-r10) must be bit-identical with the option ON | **PASS, 0 of 17 cells changed** |

Control 1 is also the pre-registered SIM1 reproduction check, and it passed, so that stopping
condition did not fire.

### 2.8 Why N = 3 over-queues - diagnosis, not a fix

The N = 3 disagreements are all **over-prediction**: C0 N3 10 % ratio 1.27, C1-r05 N3 25 % 1.26,
KVHOST-k16 N3 25 % 1.49, KVHOST-k8 N3 25 % 1.60. C0 N3 10 % matters most: it has no recall, no
warm session and the lowest load on the ladder, so whatever is wrong is in the **episodic service
model at N = 3**, not in any recall mechanism.

It is not the queue. It is the **queueing quantum**. The median is right at both N; only the tail
is wrong, and only in seconds:

| cell | quantum = prompt / 5,708 tok/s | sim p50 | sim p99 | measured p99 | **sim tail in quanta** | **measured tail in quanta** |
|---|---|---|---|---|---|---|
| C0 N1 10 % | 0.0662 s | 0.144 | 0.217 | 0.216 | 1.10 | 1.09 |
| **C0 N3 10 %** | **0.1861 s** | 0.264 | 0.437 | 0.360 | **0.93** | **0.52** |
| C0 N1 25 % | 0.0662 s | 0.144 | 0.286 | 0.271 | 2.15 | 1.92 |
| **C0 N3 25 %** | 0.1861 s | 0.264 | 0.611 | 0.510 | **1.87** | **1.32** |
| C0 N1 40 % | 0.0662 s | 0.144 | 0.418 | 0.383 | 4.14 | 3.61 |
| C0 N1 50 % | 0.0662 s | 0.166 | 0.479 | 0.452 | 4.73 | 4.32 |
| C0 N3 50 % | 0.1861 s | 0.264 | 0.912 | 1.058 | 3.48 | **4.27** |

A request that is not admitted at the start of a step waits for the WHOLE step, and a step's
duration is the serial sum of the compute of everything in it. The wait is therefore one quantum
of `prompt_tokens / 5,708 tok/s`: 0.066 s at N = 1 and **0.186 s at N = 3, 2.8 times more**.

At C0 N3 10 % the simulator records **no step sharing at all** (0.000 of requests finish in a
shared step) and its tail above the median is still 0.93 of a quantum, while the measurement's
tail above the same median is **0.52**. A waiting request on the real engine is released part way
through the running prefill - which is exactly what vLLM's V1 scheduler does: with an 8,192-token
step budget it admits up to 7 requests of 1,062 tokens into ONE forward pass, and that pass is
**sub-linear** in its tokens because a single 1,062-token prefill does not saturate the GPU.

The model has no sub-linear batching term, so it over-charges every concurrent prefill by the
sharer's own compute time. At N = 1 that error is 0.066 s and stays inside +/-25 % of a 0.45 s
budget; at N = 3 it is 0.186 s against a budget only 2.7x larger, so the N = 3 cells fall outside.

This is an **ABSENT link** in the sense of CLAUDE.md Step 2 rather than a mis-set constant:
StudyD7 and StudyD7b measured PER-REQUEST peaks (15.10 req/s at 378 tokens, 5.38 req/s at 1,062),
and nothing committed measures BATCHED prefill throughput at either N.

**Two things this does not explain, stated rather than hidden.** The same over-charge is present
at N = 1 (simulated tails 1.10 / 2.15 / 4.14 / 4.73 quanta against measured 1.09 / 1.92 / 3.61 /
4.32), so the model is 1-15 % long there too and only the seconds differ. And the sign **reverses**
at C0 N3 50 %, where the simulated tail is 3.48 quanta against a measured 4.27. A single missing
sub-linear term cannot produce a sign reversal, so at least one further effect operates at high
N = 3 load and is not identified here.

**What would fix it:** a committed measurement of prefill wall time against batch token count on
the same server - StudyE10c's E0 driven at a fixed concurrency of 1, 2, 4 and 8 simultaneous
N = 1 and N = 3 prefills - which would give the engine a measured step-time curve instead of a
linear one. Nothing is changed here.

---

## 3. Part C - out-of-sample validation against StudySLICE1 Part B

StudySLICE1 Part B was measured **live on the H100** across 28 cells and 503 scored cold recalls.
The simulator has never seen it. **No parameter anywhere in the simulator was fitted or changed
using any Part B number.** Every cold-recall constant comes from StudySLICE1 **Part A** (the gate),
which StudySIM1c already used.

### 3.1 What was mirrored, and from where

`experiments/orchestration/sim/sim1d_slice.py` mirrors `experiments/cost/study_slice1_live.py`:

| rule | mirrored from |
|---|---|
| P0 pass-through | l. 204 (no admission lock), l. 221; docstring l. 22 |
| P1 EDF admission, one cold request in the engine | l. 204-205, 231-232; l. 267 (`asyncio.Lock` is FIFO = EDF for equal relative deadlines); docstring l. 23-24 |
| P2 blocking-aware guard | l. 211-213 calling `wait_gap`, l. 164-176; docstring l. 25-26 |
| P3_n slice alignment | l. 214-215 calling `align_after_due`, l. 179-186; docstring l. 27-30 |
| P4 = P3(2048) + per-slice slack guard | l. 216-218 (`rem` = the remaining parts' predicted times); docstring l. 31-33 |
| slice construction and the predicted-time formula | l. 118-135 (`k = max(1, n // 90)`, the question rides the last slice, per-part predicted time = new tokens / the session's Part A monolithic rate) |
| constants | l. 68 LADDER, l. 70 COND, l. 71 DEADLINES, l. 72 EP_DEADLINE = 0.45, l. 73 ALIGN = 0.005, l. 74 P4_N = 2048, l. 79 LAT_FACTOR, l. 80 SLACK_MARGIN |
| answer time | l. 236 (last part's send time + its TTFT, minus the scheduled arrival) |
| window and budget | `study_e10b_mixed.py` l. 74, l. 76 |

The workload profile, entirely from Part A's 20 ~11k sessions: **11,075 prompt tokens, 121
frames, 5,375 tok/s monolithic rate, 2.062 s monolithic engine time, 0.612 s non-engine
remainder**; chains of **11 slices at 1,024** (engine ratio 1.108, 0.089 s non-engine per slice)
and **6 slices at 2,048** (ratio 1.000, 0.120 s per slice). The reconstructed chains reproduce
Part B's own medians without having seen them: predicted total 2.032 s against Part B's measured
2.037 s, and 6 and 11 slices against Part B's 6 and 11.

### 3.2 Mechanism verification (CLAUDE.md Steps 1-5), recorded before the sweep

**Step 1 - the causal chain.** `research/FORMULATION.md` scopes Context Inertia as a physical cost
that grows with context length, and StudyE10c section 6 / StudyE10d located its mechanism: a cold
history prefill is one non-preemptive unit, so an episodic request arriving during it is not
scheduled until the step that produces the cold request's first token. The chain is: (1) splitting
the materialization into prefix-chained slices shortens the longest non-preemptive unit (Part A
measured 2.06 s -> 0.39 s at 2,048 tokens); (2) a shorter unit means an episodic request waits at
most one slice; (3) dispatching slices only into gaps shortens the wait again; (4) so episodic p99
stays inside 0.45 s at a higher arrival rate, which is capacity.

**Step 2 - each link instantiated.**

| link | implementing quantity | value in this run | varies? | evidence |
|---|---|---|---|---|
| (1) slicing shortens the unit | per-part `compute_tokens` | 11,075 tokens in one request (monolithic) vs 6 parts of <= 2,011 at n = 2,048 and 11 parts at n = 1,024 | **YES**, by policy | `build_parts`, Part A's chain geometry |
| (2) the episodic wait falls | episodic TTFT p99 | **P1 2.865 s vs P3_2048 0.349 s** at C1a 25 % | **YES** | Step 4 control |
| (3) gap dispatch helps further | p99 with the guard on | P3_2048 0.349 s vs **P4 0.400 s** | **YES, but the WRONG WAY** | the `released_by` counters |
| (4) capacity rises | highest level meeting 0.45 s | section 3.3 | measured against Part B | per-configuration tables |
| the recall still answers | time to answer, fraction within 10 s | P1 3.61 s / 1.00; P4 5.88 s / 1.00 | **YES** | the same cells |

No link is ABSENT or CONSTANT, so the protocol permitted the sweep. Link (3) moving the wrong way
is itself a result and is reported, not smoothed.

**Step 3 - one traced cold recall under P4**, slice by slice, from
`sim1d_part_c.json -> mechanism_verification.step3_traced_cold_recall`. Recall `cold1` at C1a
25 %, arrival 41.5149 s, deadline 51.5149 s, answered at **+5.0536 s**:

| slice | released | at | next episodic due | pred | slack start | engine window | episodic overlapped |
|---|---|---|---|---|---|---|---|
| 0 | gap | 41.8304 | 42.4118 (gap 0.581 > 0.374) | 0.3741 | 48.4753 | 41.9507 - 42.4263 | 1 (`ep142`) |
| 1 | gap | 43.0628 | 43.6887 (0.626 > 0.368) | 0.3684 | 48.9890 | 43.1830 - 43.6518 | 1 |
| 2 | gap | 43.9600 | 44.9115 (0.951 > 0.368) | 0.3684 | 49.4948 | 44.0803 - 44.5491 | 1 |
| 3 | gap | 45.0555 | 46.0285 (0.973 > 0.368) | 0.3684 | 50.0005 | 45.1757 - 45.6258 | **0** |
| 4 | gap | 45.6258 | 46.0285 (0.403 > 0.368) | 0.3684 | 50.5063 | 45.7460 - 46.1961 | 2 |
| 5 | gap | 46.1961 | 46.6649 (0.469 > 0.184) | 0.1842 | 51.0120 | 46.3163 - 46.5685 | 2 |

Hand-checkable: every slice released `gap` has `next_episodic_due - now > pred`, and none reached
its slack start (the earliest is 48.4753, the last release is 46.1961).

**Step 4 - negative control.** Slicing is the mechanism, so P1 - the same admission queue with one
monolithic unit - is the disabled arm. At C1a 25 %: **p99 2.865 s with slicing disabled against
0.349 s with it enabled, a factor of 8.2.** The mechanism is present and drives the result.

**Step 5 - the alternative explanation.** "P4 restores capacity" could also be produced by P4
simply DELAYING the cold recall until the episodic traffic drains, which any sufficiently patient
admission policy would do. P2 is exactly that policy - monolithic, held until its slack runs out -
and in the measurement it does NOT restore capacity (< 10 % at C1a) while its answers slide to a
9.8 s median. A second alternative, that the chain is simply cheaper, is excluded by Part A:
chain / monolithic engine time is 0.990-1.093. The simulator reproduces P2's signature exactly
(see 3.4), so the two explanations remain distinguishable in it.

### 3.3 Capacity against Part B - the pre-registered verdict

| condition | policy | **measured (Part B, live H100)** | **simulated** | within one level? |
|---|---|---|---|---|
| C1a | P0 | < 10 % | < 10 % | yes |
| C1a | P1 | < 10 % | < 10 % | yes |
| C1a | P2 | < 10 % | < 10 % | yes |
| C1a | P3_1024 | 10 % | **30 %** | **NO** |
| C1a | P3_2048 | < 10 % | **30 %** | **NO** |
| C1a | **P4** | **30 %** | **25 %** | yes |
| C1b | P0 | < 10 % | < 10 % | yes |
| C1b | P1 | < 10 % | < 10 % | yes |
| C1b | P2 | < 10 % | < 10 % | yes |
| C1b | P3_1024 | 10 % | 10 % | yes (exact) |
| C1b | P3_2048 | < 10 % | **30 %** | **NO** |
| C1b | **P4** | **20 %** | **< 10 %** | **NO** |
| C4 | P0 ... P4 (all six) | < 10 % | < 10 % | yes (exact, 6/6) |
| C0 | P0 | 40 % | 40 % | yes (exact) |

| check | bar | result |
|---|---|---|
| capacity within one ladder level | >= 80 % of pairs | **15/19 = 79 %** - FAIL by one pair |
| C1a ordering: P4 highest | - | **FAIL**: simulated C1a indices are P0 0, P1 0, P2 0, P3_1024 4, P3_2048 4, **P4 3** |
| C1a ordering: P3_1024 above P0, P1, P2 | - | PASS |
| P4's C1a capacity within one level of 30 % | - | PASS (25 %) |
| **overall** | all four | **FAIL** |

**Identical in all three simulator configurations.** Turning on the host mode cost, or the host
mode cost plus the new overlap cost, changes not one capacity level in Part C - the options are
small against the quantities that decide these cells, and StudySIM1b's cost applies only in
KV-HOST, which here is C4 alone, where every policy already fails at the ladder's bottom.

### 3.4 Per-cell detail, reported without a pass bar

Episodic p99, simulated against measured, over the 25 cells where both exist: **median ratio
0.991**, range 0.49 to 1.90, **19 of 25 within +/-25 %**.

| condition | policy | level | sim p99 | measured p99 | ratio |
|---|---|---|---|---|---|
| C0 | P0 | 25 % | 0.301 | 0.272 | 1.10 |
| C0 | P0 | 40 % | 0.400 | 0.391 | 1.02 |
| C1a | P0 | 10 % | 3.176 | 3.049 | 1.04 |
| C1a | P1 | 10 % | 2.563 | 2.809 | 0.91 |
| C1a | P2 | 10 % | 2.458 | 2.501 | 0.98 |
| C1a | P3_1024 | 10 % | 0.422 | 0.397 | 1.06 |
| C1a | P3_1024 | 20 % | 0.425 | 0.460 | 0.93 |
| **C1a** | **P3_2048** | **10 %** | **0.273** | **0.555** | **0.49** |
| C1a | P4 | 10 % | 0.273 | 0.244 | 1.12 |
| C1a | P4 | 20 % | 0.350 | 0.397 | 0.88 |
| C1a | P4 | 25 % | 0.400 | 0.341 | 1.17 |
| **C1a** | **P4** | **30 %** | **0.679** | **0.357** | **1.90** |
| C1b | P0 | 10 % | 4.112 | 4.328 | 0.95 |
| C1b | P1 | 10 % | 2.665 | 2.847 | 0.94 |
| C1b | P2 | 10 % | 2.610 | 2.772 | 0.94 |
| C1b | P3_1024 | 10 % | 0.429 | 0.424 | 1.01 |
| C1b | P3_1024 | 20 % | 0.477 | 0.473 | 1.01 |
| **C1b** | **P3_2048** | **10 %** | **0.306** | **0.583** | **0.52** |
| **C1b** | **P4** | **10 %** | **0.473** | **0.263** | **1.80** |
| C4 | P0 | 10 % | 5.208 | 4.458 | 1.17 |
| C4 | P1 | 10 % | 2.823 | 3.179 | 0.89 |
| C4 | P2 | 10 % | 2.734 | 3.021 | 0.90 |
| C4 | P3_1024 | 10 % | 0.483 | 0.487 | 0.99 |
| C4 | P3_2048 | 10 % | 0.537 | 0.644 | 0.83 |
| C4 | P4 | 10 % | 0.682 | 0.531 | 1.28 |

Recall answer time and the fraction answered in time, at each condition's lowest level:

| condition | policy | sim p50 / p90 (s) | measured p50 / p90 (s) | sim frac 10 s / 5 s | measured frac 10 s / 5 s |
|---|---|---|---|---|---|
| C1a | P0 | 3.32 / 4.56 | 2.97 / 3.77 | 1.00 / 0.89 | 1.00 / 1.00 |
| C1a | P1 | 3.32 / 5.14 | 2.92 / 4.59 | 1.00 / 0.89 | 1.00 / 1.00 |
| C1a | **P2** | **10.26** / 10.98 | **9.83** / 9.96 | 0.37 / 0.07 | 0.91 / 0.36 |
| C1a | P3_1024 | 4.40 / 7.25 | 4.09 / 4.62 | 1.00 / 0.77 | 1.00 / 0.90 |
| C1a | P3_2048 | 4.17 / 6.81 | 3.40 / 5.45 | 1.00 / 0.74 | 1.00 / 0.82 |
| C1a | P4 | 4.17 / 6.81 | 6.14 / 9.46 | 1.00 / 0.74 | 0.94 / 0.37 |
| C1b | P0 | 3.36 / 5.87 | 2.89 / 3.93 | 1.00 / 0.80 | 1.00 / 0.96 |
| C1b | P2 | 10.32 / 12.52 | 9.95 / 10.84 | 0.25 / 0.10 | 0.73 / 0.12 |
| C1b | P4 | 4.31 / 10.68 | 5.72 / 10.39 | 0.86 / 0.57 | 0.84 / 0.42 |
| C4 | P0 | 3.55 / 6.61 | 3.02 / 4.11 | 1.00 / 0.78 | 1.00 / 0.92 |
| C4 | P2 | 10.50 / 12.81 | 10.02 / 11.21 | 0.22 / 0.07 | 0.46 / 0.12 |
| C4 | P4 | 4.50 / 11.03 | 4.42 / 7.73 | 0.82 / 0.59 | 1.00 / 0.65 |

P2's signature - a monolithic recall held to the edge of its 10-s deadline - is reproduced almost
exactly (10.26 s against 9.83 s at C1a, 10.32 against 9.95 at C1b, 10.50 against 10.02 at C4).
The simulator is systematically **optimistic on the p90 of the fraction answered** and pessimistic
on the p90 of the answer time itself, by roughly one slice.

### 3.5 Which policy, which condition, which mechanism

The four misses are two pairs, and they fail in **opposite directions from the same cause**.

**P3_2048 is too good, by a factor of two** (C1a 10 %: 0.273 against 0.555; C1b 10 %: 0.306
against 0.583). StudySLICE1 Part B's own finding is that "2,048 slices fail at 10 % (one slice
~0.4-0.55 s)" - an episodic request that arrives while a 2,048-token slice is in flight is held
behind it. The simulator does not hold it: `Engine.step()` schedules the running slice (2,011
tokens) and the newly arrived episodic request (378 tokens) into the SAME step, because the
8,192-token budget has room, and charges the episodic request only the summed compute. With
alignment pushing each slice to just after an episodic dispatch, few requests are caught at all,
and the p99 never sees the 0.4-0.55 s unit the measurement sees.

**P4 is too bad, by a factor of 1.8-1.9** (C1b 10 %: 0.473 against 0.263; C1a 30 %: 0.679 against
0.357). P4's slack guard releases the remaining chain back-to-back once `now >= deadline -
(remaining predicted x 1.373 + 0.25)`. At r = 0.1 the single-cold-request admission queue makes
that happen often - **26 of 168 slice releases at C1b 10 % are slack-driven, against 142 gap-driven**
- and when it does, the simulator charges the resulting burst at its serial-sum price, which is
the harshest possible reading of several prefills in flight.

Both are the same defect seen from two sides: **the simulator prices a slice sharing a step with
other work by summing compute, with no head-of-line hold and no sub-linear batching.** That is the
same ABSENT link as section 2.8's N = 3 diagnosis, and it is the reason the gate and this
out-of-sample test fail together. **A single corrective direction is NOT identified here**: one
side needs the model to charge MORE (hold the episodic request behind a running slice), the other
needs it to charge LESS (a burst of prefills is cheaper than their serial sum). Both would be
settled by the same missing measurement named in 2.8.

Per the pre-registered rule, the study **stops here**: nothing was tuned to improve Part C, and no
Part B number was used to set any parameter.

A declared sensitivity, on the one workload constant where two committed measurements disagree -
StudyRH5 Part A's 4,500 tok/s cold re-prefill at 11k (the simulator's own constant, primary) and
StudySLICE1 Part A's 5,375 tok/s on this server. Both are held-in. **It changes nothing**: at
C1a, P3_1024 moves from 30 % to 40 % and every other policy is unchanged, so the verdict is not an
artefact of that choice.

### 3.6 The entry point for StudySLICE1 Part C (P5), not implemented

P5 (warm appends deferred and coalesced, escalations gap-aligned) is running on the H100 now and
is **deliberately not implemented**, because implementing it before its ground truth exists would
make it an in-sample arm. When it lands: add `"P5"` to `sim1d_slice.POLICIES`, give `build_parts`
a P5 branch and `_release_time` a P5 case. Nothing else changes - `run_cell`, `cell_median` and
`capacity` are policy-agnostic and `part_c()` iterates `S.POLICIES`.

---

## 4. Results consistency check (CLAUDE.md, six checks)

Run on Parts B and C before any conclusion above was written.

**1. Cross-check against committed measurements.**

| quantity | this run | prior run | source of prior | ratio | agree |
|---|---|---|---|---|---|
| OVERLAP-minus-CLEAR episodic TTFT difference | 0.0481 s (12 held-out cells at 10 %) | 0.0704 s pooled KV-HOST | StudySIM1b step 2 | 0.68 | yes |
| the same, KV-GPU | 0.0740 s (2 held-out cells) | 0.0574 s cell-matched control | StudySIM1b step 2 | 1.29 | yes |
| gate with all options off | 18/29, 10/16 | 18/29, 10/16 | StudySIM1b gate, OFF | 1.00 | **bit-exact** |
| gate with the host mode cost on | 20/29, 11/16 | 20/29, 11/16 | StudySIM1b gate, ON | 1.00 | **bit-exact** |
| cold recall prompt tokens | 11,075 (Part A median) | 11,096 (Part B median) | StudySLICE1 Part B | 1.002 | yes |
| predicted chain time | 2.032 s | 2.037 s | StudySLICE1 Part B | 1.002 | yes |
| slices per chain, n = 2,048 / 1,024 | 6 / 11 | 6 / 11 | StudySLICE1 Part A | 1.00 | exact |
| C0 capacity | 40 % | 40 % | StudySLICE1 Part B, StudyE10c / E10e | 1.00 | exact |

No disagreement exceeds 2x.

**2. Physical plausibility.** Cold prefill 11,075 tokens at 4,500 tok/s = 2.46 s; episodic 378
tokens at 5,708 tok/s = 0.066 s. Both are the committed curves themselves, so nothing here runs
faster than a committed rate. The simulated cold answer times (3.3-4.5 s medians) sit **above**
the measured ones (2.9-3.6 s), i.e. on the conservative side; the measured H100 rate (5,375
tok/s, StudySLICE1 Part A) is 1.19x the simulator's StudyRH5 constant, and that is the direction
of the gap. The overlap step cost of 0.0481 s against an 8,192-token step is a 27 % addition to a
0.18 s step, which is large but is what the held-out cells measure.

**3. Distribution sanity.** Every gate cell is reported as the median over 5 arrival seeds with
its min and max (`sim1d_part_b_gate.json`), and every Part C cell likewise (`p99_seeds`,
`p99_min`, `p99_max`). The 12 held-out cells behind the registered value are listed individually
in section 2.3 and span 0.0316 to 0.0621 s - a real distribution, not a constant. No quantity
agrees to more precision than its inputs vary, with one deliberate exception: the Part B negative
controls agree **bit-exactly**, which is the point of a reproduction check.

**4. Definition audit.**

| object | definition used here | matches |
|---|---|---|
| capacity | highest ladder level whose episodic p99 meets the budget, bottom-up, stopping at the first failure | StudyD7 / E10b / E10c and StudySLICE1 Part B, identical |
| episodic p99 | TTFT from the SCHEDULED arrival, nearest-rank with unfinished counted infinite | StudyE10b, identical |
| OVERLAP | an episodic request whose [submit, submit + ttft] intersects a warm recall's interval, cold-recall overlaps excluded | StudySIM1b, identical code path |
| slice | `max(1, n // 90)` frames, the question on the last slice | StudySLICE1 Part A and `study_slice1_live.py` l. 123-131 |
| recall deadline | arrival + 10 s | `study_slice1_live.py` l. 201 |
| budget | p99 <= 0.45 s at N = 1 | `study_e10b_mixed.py` l. 74 |

No name is used with two definitions.

**5. Claim linkage.** Part B bears on `research/FORMULATION.md`'s PHYSICAL component of Context
Inertia, through the engine model that every orchestration claim rests on: it **weakens** the
claim that the current engine model is calibrated, since modelling a genuine measured effect does
not repair the gate. Part C bears on the claim that representation-aware placement and timing can
beat decomposed policies under a quality SLO: it **does not yet speak to it**, because the
simulator fails the out-of-sample check, and that is the finding. Nothing here measures an object
FORMULATION.md scopes out.

**6. Proxy validity.** Three proxies, all declared. (a) The per-step overlap cost is a proxy for
batched-prefill interference; it is validated only in the sense that it is measured on held-out
cells, and section 2.6 shows it does not generalise to the gate, so it is **not used for any
headline conclusion** beyond "the effect is real, blocking and mode-independent". (b) The cold
recall's non-engine time is Part A's measured `mono_ttft - mono_engine` remainder, used as a proxy
for client plus upload time; it is a Part A measurement on the same server and the same bodies.
(c) `n_concurrent` in the pre-registered regression is a proxy for warm work in flight; section
2.5 shows it is contaminated by StudyE10b's collapse cells and it is **reported but not used**.

---

## 5. What this implies for re-running the StudySIM1c sweep

**The StudySIM1c sweep was not re-run in this study and is not proposed to be re-run yet.** Three
things must land first, in this order.

1. **The 8 Part A proposals need a decision.** Twelve of the 37 arms in the committed sweep are
   decided by an adapter artefact rather than by their published rule. Re-running before that is
   settled would reproduce the same artefacts at 20 seeds.
2. **The batching measurement of section 2.8.** Until the engine has a measured step-time curve,
   every capacity number at N = 3 carries a 1.26-1.60x over-prediction and the sliced policies
   carry the 0.49-1.90x error of section 3.5.
3. **StudySLICE1 Part C (P5)** gives a second held-out check at no extra simulator cost.

When those land, the design the current sweep most needs is a **finer ladder where the answer
actually sits**. StudySIM1c found that one replica supports 2 cloud episodic streams at the dual
target and that 27 of 37 arms fall below the device-only value at 16 streams, so the whole
transition happens between F = 2 and F = 8 and the committed ladder (2, 4, 8, 16, 32) has three
points in it.

**Proposed, not run:**

- **Fleet ladder** F in {2, 3, 4, 5, 6, 8} for all three mixes, keeping 16 and 32 as two anchor
  points so the existing curves remain comparable. That is 8 points against the present 5.
- **Multi-replica design.** Fairness rule 2 pins the suite to ONE replica and the action space has
  no instance dimension, so a multi-replica study is a NEW row, not a parameter of this one. The
  minimal honest form: R in {1, 2, 4} replicas with the fleet scaled proportionally (F = 2R, 4R,
  8R), each replica an independent `Engine`, and a stated placement rule - sticky by session, so
  a session's warm state lives on one replica and cross-replica KV movement never arises (which
  `FORMULATION.md` scopes out anyway). The question it answers is whether capacity per replica is
  flat in R, which is the only claim a single-replica study cannot make. Three of the suite's arms
  (Preble, Clockwork, PerLLM) were multi-instance in their papers and would be the ones to label
  `multi_instance_adapted = False` again there.
- **Cost.** The committed sweep was 37,800 runs in 8,300 s on 12 workers. The finer ladder is
  8/5 of it; the multi-replica design multiplies by 3 and by roughly R in engine work, so about
  10-12 hours on flash. Both stay inside the 12-hour rule only if run as two rows, not one.

---

## 6. Limitations

- **The gate still fails.** Nothing in this study should be read as a statement that the engine
  model is calibrated. It is not, at 19/29 and 11/16 against an 80 % bar.
- **Part C failed**, so the simulator has not earned an out-of-sample licence for the slicing
  mechanism. StudySLICE1 Part B's own live measurements remain the only evidence about P0-P4.
- The KV-GPU side of the mode-independence finding (2.4) **rests on two cells**.
- The registered overlap value comes from the lowest load on the ladder; a different reading of a
  per-step cost would give a different number between 0.048 and 0.088 s.
- Part A traces **one cell per arm** at deadline 5 s plus one symptom cell at 2 s, not the full
  sweep. The committed StudySIM1c cells locate every symptom, but the traced mechanism is shown
  at two points.
- Every Part C number inherits StudySIM1c's declared limitations, including the N = 3 gap, which
  does not apply here (Part B is N = 1 throughout).
- This study makes **no claim about which baseline is best**, and our scheduler is not in it.

---

## 7. Files

| file | what |
|---|---|
| `experiments/orchestration/sim/sim1d_validate.py` | Parts A, B and C: the tracer, the fit, the gate, the mechanism verification |
| `experiments/orchestration/sim/sim1d_slice.py` | P0-P4 mirrored from `study_slice1_live.py`, and the Part B cell |
| `experiments/orchestration/sim/engine.py` | **modified**: `overlap_step_cost_s`, default 0.0 (OFF) |
| `experiments/orchestration/sim/calibrate.py` | **modified**: the option plumbed through `run_cell` |
| `results/orchestration/sim1d/sim1d_part_a.json` | every arm's traced decisions, probes and overlap counts |
| `results/orchestration/sim1d/sim1d_part_b_fit.json` | the gate inventory, the held-out cells, the form test, the fit |
| `results/orchestration/sim1d/sim1d_part_b_gate.json` | four gate runs, three controls, the N = 3 diagnosis |
| `results/orchestration/sim1d/sim1d_part_c.json` | mechanism verification, three configurations, the sensitivity |
| `results/orchestration/sim1d/sim1d_part_a_arms.csv` | the Part A audit table |
| `results/orchestration/sim1d/sim1d_part_c_cells.csv` | every Part C cell, simulated against measured |
