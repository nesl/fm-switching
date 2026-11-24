# D225 (5): INDEPENDENT VERIFICATION OF THE CONFORMANCE MATRIX

**Written by a session that did not build `research/conformance_matrix.md` and did not write
`experiments/orchestration/live2/d225_switch_diff.py`.** That is the point of this file (D225 (5)).
It verifies the matrix as published at `4a73e125`, re-derives what can be re-derived, and marks every
claim CONFIRMED, REFUTED or NOT CHECKABLE with the evidence beside it.

Nothing here was read from a working tree. Every byte was read with `git show <literal-sha>:<path>`
or `git grep <literal-sha>`. No cell was run (D216: the rung-4 pass-1 build owns the box). The one
thing this file adds that is not a verification is the settlement of freeze-gate row 10.15, which the
matrix itself says closes on "one code read, not a cell"; that read is in section 6.

## 0. PROVENANCE OF THIS VERIFICATION

| what | value |
|---|---|
| matrix verified | `research/conformance_matrix.md`, blob `ea82715dc32f5b6ecba66d59a378483977ea440d`, byte-identical at `4a73e125` and at origin tip |
| matrix's own code pin | `c5e7bb4926a23c68e12d22c3f337462897408d51` (called `c5e7bb49` below) |
| switch state re-resolved at | `4a73e125`, by constructing the five arms in `fmtk` |
| origin tip at the start of this work | `7fdd058270db943ee91fd8565c49f2a289e38ccb` |
| origin tip re-resolved during it | `566e1485259b946699546a86ee99a7709bb6b609` (nine further commits; `live2` tree moved twice) |
| committed cells read | 21 (the 20 ladder cells plus the new rung-3 `kv0.5r` cell), by `git show <sha>:<path>` |
| box state | no Python interpreter had a cwd under the repo or a scratchpad tree; `nvidia-smi` listed no compute apps. No live2 harness was running, so nothing was yielded to |

**THE CRITICAL PROVENANCE FACT, AND IT IS NOT A DETAIL.** The matrix is pinned to a tree that has
since moved. `experiments/orchestration/live2` is `23233f43` at all three shas the matrix names, but
`2f7bc712` at `7fdd0582` and `9e237bb4` at `566e1485`. Three of the matrix's freeze-gate rows are
settled by commits that landed after it, and one by a design-log row that did not exist when it was
written. Every row below therefore carries its verdict **at the matrix's pin** and, where they
differ, **at origin tip**.

## 1. TALLY

| verdict | count |
|---|---|
| **CONFIRMED** | 41 |
| **REFUTED** | 11 |
| **NOT CHECKABLE** (from what the row gives, or needs a cell) | 5 |
| **CONFIRMED at the pin, STALE at origin tip** | 5 |

Counting convention, stated because a count in the wrong register survives every check: a claim is
one checkable assertion, not one table row. The 41 confirmations include 12 structural claims
re-derived by construction, 18 OBSERVED counter values re-read from committed cells, and 11 code
reads walked to the decision that consumes them. **No finding changes a posted result.** Two findings
change what the freeze gate contains.

**A previous session's verification was not lost.** It is committed as
`reports/study_d225_verification.md` (466 lines, `31462233`, 2026-11-24 09:57). It reports 26
CONFIRMED / 6 REFUTED / 4 NOT CHECKABLE. I did my own work before reading it; section 8 reconciles
the two and records which of its six refutations I reproduced independently.

## 2. THE SWITCH DIFF, RE-RUN HERE

`d225_switch_diff.py` does not exist at any of the three shas section 0 of the matrix pins. It was
added by `4a73e125`, the matrix's own commit. So §7's argument that the `a4eaf9bc` result "holds at
`c5e7bb49` ... from the tree hash" is sound about the *arms* it reads and unsound as stated about the
script, which is not in that tree. **REFUTED as a provenance statement, immaterial to the result.**

Re-run at `4a73e125`, in `fmtk`, from a `git archive` export plus the committed result JSONs the
fail-loud loaders require:

    python3 -I experiments/orchestration/live2/d225_switch_diff.py \
        --live2 experiments/orchestration/live2 \
        --design-log research/policy_design_log.md --json out.json

| claim | this run | verdict |
|---|---|---|
| exit status 0 | **0** | CONFIRMED |
| switch differences | **56** | CONFIRMED |
| per-pair counts | **10 / 16 / 17 / 13** (rung0->1, 1->2, 2->3, 3->4) | CONFIRMED |
| unattributed differences (defects) | **0**, `defects: []` | CONFIRMED |
| attribution D-rows all present in the design log | "none" missing | CONFIRMED |
| resolved switch surfaces | **58 / 65 / 75 / 85 / 95** | CONFIRMED |
| C1 to C6 identical at all five rungs | `c1=True c2=True c3=False c4=False c5=True c6=False` at every rung | CONFIRMED |
| switch monotonicity, 0 breaks | **0** switches ON at a lower rung and OFF or absent at a higher one, over the full 95-name union | CONFIRMED |
| it refuses to print a bare "unknown" sha | it printed `sha = "UNRESOLVED (git ... rev-parse HEAD exited 128). Every switch value below is therefore UNATTRIBUTABLE TO A COMMIT ..."` | CONFIRMED, and the refusal is loud enough to be useful |

**The script needs committed result JSONs to import at all.** Six fail-loud loaders raise rather than
default (`d190_measured_safety`, `cf_cost.load_residuals`, `profiles`, the LH-REQ definition and
quality files). This is D200 (3) working, and it is why "run it from a real checkout" in §7 is correct
guidance rather than boilerplate.

## 3. THE COMPOSITION CHAIN. WALKED, NOT INFERRED FROM AN MRO

The matrix's central framing claim is in its §2: the ladder "is NOT a class hierarchy", `V6StateArm`
has MRO `[V6StateArm, object]`, and a walker that reads only `vars()` and the MRO reports twenty false
inheritance breaks. **The warning is right and the framing is half wrong, and the half that is wrong
matters to anyone who takes the warning as a rule.** Resolved by constructing the arms:

| rung | class | MRO depth | chain the diff walked |
|---|---|---|---|
| 0 | `HybridArm` | 2 | `arm -> arm._b7` |
| 1 | `V5Rules2Arm` | 2 | `arm -> arm._base -> arm._base._b7` |
| 2 | `V6StateFinal` | **4** (`V6StateFinal, V6StateUoC5AttrArm, V6StateArm, object`) | `arm -> arm._rules -> arm._rules._base -> arm._rules._base._b7` |
| 3 | `V6FairFinalWired` | **10** | `arm -> arm._rules -> arm._feed -> arm._rules._base -> arm._rules._base._b7` |
| 4 | `V6Final` | **13** | same as rung 3 |

`V6FairFinalWired` subclasses `V6StateFinal`; `V6Final` subclasses `V6FairFinalWired`. **So rungs 2,
3 and 4 ARE a class hierarchy, and the composition caveat applies to the rung 0 / rung 1 / rung 2
boundaries, where the inner arm is held at `_b7`, `_base` and `_rules`.** The correct statement is
that the ladder is composition ACROSS those three boundaries and inheritance from rung 2 upward, and
that neither walk alone is sufficient. **REFUTED as written; the hazard it warns about is real.**

### 3.1 The read I looked for, and the path I walked, for the row the warning is built on

Claim (matrix §4.1, D170 row): `over_limit_infeasible` is live at every rung including the base.

**Read looked for:** a use of `self.over_limit_infeasible` that changes a `RecallAction`.
**Path walked:** `V5Rules2Arm.__init__` constructs a real `HybridArm` at `arms_v5rules2.py:107` and
sets the flag on **both** objects at `:111` (`self._base.over_limit_infeasible`) and `:112`
(`self.over_limit_infeasible`), with an in-code comment saying why leaving one unset is how a switch
reads as live and decides nothing. `V5Rules2Arm.decide` calls `self._base.decide(obs)` at `:278`.
`V6StateArm.decide` calls `self._rules.decide(obs)` at `arms_v6state.py:379`. Attribute access falls
through `__getattr__` at `arms_v5rules2.py:148-149`, `arms_v6state.py:218-219` and
`hybrid/hybrid_arm.py:303-304`.
**Read found:** `hybrid/hybrid_arm.py:410-411`, inside `HybridArm.decide`:

    over_limit = (self.over_limit_infeasible
                  and int(getattr(q, "readiness_tokens", 0) or 0) > CONTEXT_LIMIT_TOKENS)

and `:412` branches to `RecallAction(q.query_id, "REJECT")`. **CONFIRMED.** The matrix cites `:411`
and is correct at its pin. (The briefing for this session cited `:421-422`, which is a different
tree; the line is `:410-411` at `c5e7bb49`.)

### 3.2 Two composition citations point at the delegation, not the composition

| matrix says | at `c5e7bb49` the cited line is | where the composition actually is | verdict |
|---|---|---|---|
| "`V5Rules2Arm` composes the rung-0 arm at `self._base` (`arms_v5rules2.py:148-149`)" | `def __getattr__(self, k): return getattr(self.__dict__["_base"], k)` | `:107` | **REFUTED** (citation) |
| "`HybridArm` composes a `B7EdfFeasibilityArm` at `self._b7` (`hybrid/hybrid_arm.py:303-304`)" | `def __getattr__(self, k): return getattr(self.__dict__["_b7"], k)` | not at `:303-304` | **REFUTED** (citation) |
| "`self._rules` (`arms_v6state.py:152`)" | `self._rules = V2.V5Rules2Arm(name=name,` | `:152` | CONFIRMED |
| "`__getattr__` (`arms_v6state.py:218-219`)" | `def __getattr__` | `:218` | CONFIRMED |

Both sites are load-bearing for the chain, so neither citation is useless; the prose says "composes
at" and points at the delegation. A verifier who follows it lands one hop from the fact.

## 4. FILE:LINE AUDIT OF THE MECHANISM ROWS

48 file:line-plus-content claims from §4.1 to §4.5 were checked mechanically against
`git show c5e7bb49:<path>`. **38 matched on the exact line. 10 did not.** Classified:

| kind | count | detail |
|---|---|---|
| exact | 38 | every SET-site and every READ-site citation I checked is exact, including all nine rung-1 read sites (`:196, :197, :199, :249, :253, :280, :301`) |
| off by five, parameter declarations only | 5 | `warm_ahead` cited `:99`, actually `:94`; `just_in_time` cited `:105`, actually `:99`; `guard` cited `:104`, actually `:98`; `slice_tokens` cited `:106`, actually `:100`; `guard` family likewise. The whole `__init__` signature block is `arms_v5rules2.py:93-101` |
| wrong register | 1 | D139's "workload" is cited at `hybrid_arm.py:177`, which is the signature default `workload: str = "mixed"`. The arm's actual `lh_req` comes from `CONFIGS`, read at `:99-100`. The value is right; the line shows the opposite value |
| within a 3-line window | 4 | `k_r_frac`, the three sort keys, the EWMA row |

**Verdict: CONFIRMED with a precision defect.** The switch VALUES are all correct; five of the
parameter-declaration line numbers in §4.2 are off by five and one points at a contradicting default.
This is the kind of error that costs a verifier ten minutes per row and changes no conclusion.

## 5. OBSERVED COUNTERS, RE-READ FROM COMMITTED CELLS

Every ladder cell carries **`run_s = 1200.0`** in its `header.json` (21 of 21, including the new
rung-3 `kv0.5r` cell). `gpu_kv_tokens` is 62,944 at 1x and 31,472 at `kv0.5r`. **Every "did not fire"
statement below is therefore a statement about a 1,200 s window at 16 devices**, and must not be read
as a statement about the mechanism in general.

| matrix claim | re-read value | verdict |
|---|---|---|
| `header.json` `flags` is `{}` in all 20 ladder cells | `{}` in 21 of 21 | CONFIRMED |
| `c5_dash_held` 50,589 at R0 s4 | 50,589 | CONFIRMED |
| `c5_dash_held` 57,938 at R2 s4 | 57,938 | CONFIRMED |
| `state_chosen_TOUCH` R2 2399 / ABSENT / 408 / 2201 | 2399 / absent / 408 / 2201 | CONFIRMED |
| `guard_by_lag` R1 4027 / 3675 / 3508 / 4565 | exact | CONFIRMED |
| `guard_by_lag` R4 80 / 32 / 117 / 22 | exact | CONFIRMED |
| `guard_by_backlog` = 0 in all 16 cells where present | 0 in all 16 at the pin (17 at origin tip, the new cell also 0) | CONFIRMED |
| `release_infeasible` R3 2028 / 2046 / 2073 / 1746 | exact | CONFIRMED |
| `release_infeasible` identical to `release_infeasible_alert` in every cell | identical in 9 of 9 R3/R4 cells | CONFIRMED |
| `pd_decisions` 302 / 299 / 293 / 259 | exact | CONFIRMED |
| `rd_decisions` 157 / 152 / 146 / 106 | exact | CONFIRMED |
| `pd_kv_bound_by_belief` EQUALS `pd_decisions`, 1,153 of 1,153 | 302/302, 299/299, 293/293, 259/259 | CONFIRMED |
| `pd_kv_bound_by_engine_metric` absent in all four R4 cells | absent in 4 of 4 | CONFIRMED |
| `rd_question_defers` 29 / 37 / 29 / 25, non-zero at all four seeds | exact | CONFIRMED |
| `pd_free_kv_min` 14,993 / 16,017 / 21,258 / 10,115 | exact | CONFIRMED |
| `pd_harm_over_bar` 2 at s4 and s7, nothing at s5 and s6 | 2, absent, absent, 2 | CONFIRMED |
| `pd_request_crossed_bar_unexpressible` 2 at s4 and s7 | 2, absent, absent, 2 | CONFIRMED |
| deficit feed `gain` = 2.0, targets alert 0.25 / recall 0.90 / assistance 0.90 | exact | CONFIRMED |
| zero `c2_*` and `c5_*` keys at rung 1 | 0 and 0 in all four `v5-rules-2` cells; rung 0 has 3 and 3; rungs 2 to 4 have 3 and 6 or 7 | CONFIRMED |
| `arm_stats` sizes 8 / 12 / 78 / 81 / 128 at s4 | 8 / 12 / 78 / 81 / 128 | CONFIRMED |

### 5.1 REFUTED: the OBSERVED reproduction recipe is wrong for the whole offload family

Matrix §1 gives the reproduction for register OBSERVED as "open that cell's
`coordinator_result.json` -> `arm_stats`". **`offloaded`, `evicted`, `kept_warm`, `over_cap` and
`host_epochs_over_cap` are NOT in `arm_stats` in any cell.** They live at

    /memory_pressure/enact_placement_totals/{offloaded,evicted,kept_warm}
    /memory_pressure/pressure/{epochs_over_cap,host_epochs_over_cap}

A verifier who follows §1's recipe finds the keys absent and, following §1's own trap 1 ("ABSENT means
never fired in this cell"), concludes the counters never incremented. They did: `kept_warm` is 4,300
at rung 3 s4. **REFUTED, and this is the trap the matrix built §1 to prevent, in the matrix.**

### 5.2 REFUTED: 10.8's `over_cap = 0` and its `kept_warm` range, and the cell that now exists

Full family across the 21 cells, every one a 1,200 s window:

| cell (1,200 s, n16) | offloaded | evicted | kept_warm | epochs_over_cap |
|---|---|---|---|---|
| rung 0, s4 to s7 | 0 | 0 | 0 | 0 |
| rung 1, s4, s5, s6 | 0 | 0 | 0 | 0 |
| rung 1, **s7** | 0 | **1** | 0 | **1** |
| rung 2, s4 / s5 / s6 / s7 | 0 | 0 | 3650 / **0** / 1828 / 2435 | 0 |
| rung 3, s4 / s5 / s6 / s7 | 0 | 0 | 4300 / 175 / 1835 / 2434 | 0 |
| rung 4, s4 / s5 / s6 / s7 | 0 | 0 | 4111 / 173 / 1829 / 2441 | 0 |
| **rung 3, s4, `kv0.5r`** (new, after the matrix) | 0 | **6** | 3653 | **5** |

1. "`over_cap` = 0": **REFUTED**, and by the matrix's own body text, which says rung 1 "evicted once at
   s7". The headline in 10.8 and the detail three lines below it disagree.
2. "`kept_warm` is 173 to 4,300 across the ladder cells": **REFUTED**. `covex-v6-state-final` s5 is
   **0**, and that is a rung-2 ladder cell, the rung whose headline mechanism this is. The stated
   range excludes the one cell that would have made the row stronger.
3. "**no reduced-memory cell exists for rungs 2, 3 or 4 anywhere in the tree**": **REFUTED at origin
   tip.** `covex-v6-fair-final_n16_s4_1200s_h27_3t_kv0.5r_L3_epg_rq30` exists (`7d2ebaae`), and it
   answers 10.8's own closing question: **under 0.5x the eviction branch IS reached (6 evictions, 5
   epochs over cap in 1,200 s) and offload is STILL zero.** So the row's diagnosis splits in two:
   eviction was unexercised at 1x and is now exercised; offload is unexercised at both levels.

## 6. FREEZE-GATE ROW 10.15, SETTLED BY THE ONE CODE READ IT ASKS FOR

10.15 says it "closes when someone reads the rung-1 counter-merge path and says which of the two it
is. Cheap: it is one code read, not a cell." I did that read.

**Read looked for:** the merge that builds `arm_stats`, and whether its walk reaches the inner
`HybridArm` where `c2_*` and `c5_*` are counted.
**Path walked:** `coordinator.py:2244` `arm_stats=_arm_stats(self.arm)` -> `_arm_stats`, defined at
`coordinator.py:167`. It breadth-walks `("_rules", "_base", "_scorer")` and merges every `stats`
Counter it finds, prefixing collisions by holder class.
**What the code says in its own docstring, verbatim:**

> every committed v5-rules-2 cell carries `warm_ahead_emitted` and `guard_active_epochs` and carries
> NO `c2_throttle_periods`, `c2_throttled_dash` or `c5_dash_held`, **although the base counts all three
> on every period**.

**The walk reaches `_base`.** So a rung-1 cell run today would carry the keys. The committed ones do
not because they predate the merge:

| artefact | date | content |
|---|---|---|
| `v5-rules-2_n16_s4` cell (`08a7ee19`) | **2026-11-21** | 12 keys, all the wrapper's own (`warm_ahead_*`, `chunk_*`, `jit_*`, `guard_*`, `epochs`), zero base keys |
| `_arm_stats` lands (`9803dca0`, D175) | **2026-11-22** | the merge |
| `covex-v6-state-final_n16_s4` cell (`cf099141`) | **2026-11-23** | 78 keys, wrapper AND base families merged, `c2_*` and `c5_*` present |

`08a7ee19` is an ancestor of `9803dca0` (`merge-base --is-ancestor`, rc=0).

**VERDICT: 10.15 is resolved, and it is NOT a Rule 2 class about the policy.** It is a cell-vintage
instrumentation artefact: the mechanism fired and the counter was not written to the file, because the
file was written by the pre-merge code path. The matrix was right to refuse to classify it and right
that one read settles it. **Recommended action: rule out** (record the vintage), optionally re-running
one rung-1 cell if the keys are wanted as published evidence. Note the prior verification
(`reports/study_d225_verification.md:442`) recommends specifically NOT relaxing 10.15; that
recommendation was made without this read.

## 7. THE FREEZE GATE: HOW MANY ROWS, AND EACH ROW'S STATE

### 7.1 The count. The matrix is right and 15 is wrong

**16 numbered rows in five groups:** Group A 10.1 to 10.7 (7), Group B 10.8 to 10.11 (4), Group C
10.12 to 10.14 (3), Group D 10.15 (1), Group E 10.16 (1). 7+4+3+1+1 = 16. I counted the rows.

**By distinct mechanism it is 19**, because three rows bundle two each: 10.7 carries per-type guard
thresholds (D178 (3)) **and** guard exit hysteresis (D166 (3)); 10.13 carries KEEP-READY SET **and**
ADMIT WITH PROTECTED VICTIM; 10.14 carries reload-from-host as an explicit action **and** the
counterfactual sync. **Report 16 rows / 19 mechanisms. 15 is not reachable by either count.**

One internal inconsistency worth fixing: §4.5's preamble says "Every 4.5 row is carried into the
freeze-gate list in section 10". It is not; §4.5 rows such as D151 (1), D191 (1) question deferral and
D193 (2) have no section 10 row. The sentence overstates by about eight rows.

### 7.2 Per-row state, with evidence

Verdicts are at the matrix's pin `c5e7bb49` unless a row says otherwise. Every "did not fire" carries
its window.

**10.1 DEVICE_ANSWERS (D218 (1), D221). Matrix says ORDERED, NOT BUILT. REFUTED.**
*Read looked for:* a write of `ra.decision = "DEVICE"` on the import path.
*Path walked:* `cf_request_defer.py:177` `ACTIONS = ("BASE", "DEFER_TO_LATEST_SAFE_START")`, two
actions, unchanged at origin tip. The only `ra.decision` writes on the import path are `"DEFER"` at
`arms_v6cf.py:494` (`:504` at tip) and `arms_v6cfr3.py:297`. The coordinator channel exists unwritten
at `coordinator.py:865` (`:884` at tip). `cf_protect_defer.py:530` says in its own gate string that
DEVICE_ANSWERS "is not built here". All of that is CONFIRMED.
*What the matrix missed:* **the implementation exists.** `experiments/orchestration/live2/held/d218_device_answers/`
holds eleven files including `arms_v6cf.py.patch` with `+ ra.decision = "DEVICE"`, under a README
titled "HELD AND NOT APPLIED. DO NOT WIRE THIS." It was built, proved dry and reported
(`reports/study_d218_device_answers.md`, 671 lines, `4f317e1f`, 2026-11-23), and it **stopped on its
own pre-registered condition**: the dry 1x `pd_request_crossed_bar_unexpressible` count is 1, not 0.
`4f317e1f` is an ancestor of `4a73e125`, so this was available to the matrix's author.
Also: "`d218_prereg.json` is not present in `experiments/orchestration/live2/`" is literally true and
misleading. It is at `results/orchestration/live2/d218_device_answers/d218_prereg.json`, with an
addendum beside it.
*Correct status:* BUILT, PROVED DRY, HELD OFF THE IMPORT PATH PENDING A USER RULING. Not "not built".

**10.2 D222 (1) item 1, the hard-coded zero queued-ahead. CONFIRMED, and now RULED.**
`arms_v6cfr3.py:198-199` `pred = CC.predict(cf.model, int(u_request), 0, 0, 0)`, byte-identical at
origin tip. The matrix is right that the first zero is correct by construction and the defect is
`overlap_ft` / `overlap_decode`. The matrix says the order is ambiguous and needs a ruling.
**That ruling now exists: D228 (1), 2026-11-24, which did not exist when the matrix was written.**

**10.3 D222 (1) item 2, debit one decision period. CONFIRMED.**
`v5/cf_cost.py:281` `deferral_s=max(lss - float(now_s), 0.0)`, no debit. `MIN_DEFERRAL_S` has exactly
two occurrences in live2: the definition at `cf_request_defer.py:175` and one use at `:267`,
`if defer_s < MIN_DEFERRAL_S: out["gate"] = "must_start_now_no_slack"`. A floor, not a debit.

**10.4 D222 (1) item 5, the committed `rd_decisions` log. CONFIRMED.**
Accumulated in memory capped at 4,000 (`arms_v6cfr3.py:234-235`). A tree-wide listing of the committed
runs directory at origin tip matches `rd_decision` **0 times** (rc=1, no match, distinguished from
error). Not satisfied in the committed set.

**10.5 D223 (2), read max-model-len. CONFIRMED at the pin, CLOSED at origin tip.**
At `c5e7bb49` all four sites are literal: `hybrid/hybrid_arm.py:157`, `arms_v6cf.py:86`,
`arms_v6fair.py:90`, `d170_overlimit.py:33`. At origin tip, `experiments/orchestration/live2/context_limit.py`
(223 lines, new) reads the limit from the server's own argv at run start, last-occurrence-wins, and
RAISES rather than defaulting to 32,768. The three live-path sites no longer carry the literal; only
`d170_overlimit.py:33` does, and that is a diagnosis script. `max_model_len` references in live2 went
from 3 to 9. **10.5 should be removed from the gate.**

**10.6 D220 (1), harm weighted by the accuracy gain. CONFIRMED as a code reading, RULED OUT at origin tip.**
`v5/cf_objective.py:712` computes `w_o x (p_before - p_after)` only; `HARM_FORM_DEFAULT`
(`cf_protect_defer.py:336`) has exactly three occurrences, the definition, a dict string at `:387` and
a describe block at `:639`, and **no branch anywhere** (CONFIRMED). The matrix calls this a genuine
tension and the user's call. **D228 (2) makes that call: D220 (1)'s gain weighting is WITHDRAWN as a
planner error, because weighting by each type's cloud-minus-device gap is the cross-type exchange rate
D149 (1) and D177 forbid, and no per-type gain table exists.** Harm stays in D177 units, which is
exactly what `cf_objective.py:712` computes. **The code is already conformant. Remove the row.**

**10.7 D178 (3) per-type guard thresholds, and D166 (3) exit hysteresis. CONFIRMED, two mechanisms.**
`arms_v5rules2.py:81` `GUARD_LAG_S_DEFAULT = 2.0`, read at `:196`, one threshold for all three types
against the ruled 0.8 / 1.6 / 2.4 s. Exit hysteresis: no code. Both unchanged at origin tip.

**10.8 Per-type host retention / offload. CONFIRMED as unexercised for offload, REFUTED in three sub-claims.** See 5.2.
Switch ON at rungs 2 to 4, rule at `offload_policy.py:30-52,:72`, enactment at `coordinator.py:1529`.
`offloaded` = 0 in 21 of 21 cells, every one a 1,200 s window. `over_cap` is NOT 0 (1 at rung 1 s7, 5
at the new rung-3 `kv0.5r`); `kept_warm` is 0 to 4,300, not 173 to 4,300; and a reduced-memory rung-3
cell now exists and reaches eviction.

**10.9 Engine-metric KV bound. CONFIRMED at the pin, and STILL OPEN at origin tip for a different reason.**
*Read looked for:* a production caller of `scrape_metrics`, and a production setter of `metrics_scrape`.
At `c5e7bb49`: `scrape_metrics` defined at `asyncbackend.py:175` with **zero callers** (CONFIRMED by
full-tree grep). OBSERVED: `pd_kv_bound_by_engine_metric` absent in 4 of 4 rung-4 cells while
`pd_kv_bound_by_belief` equals `pd_decisions`, 1,153 of 1,153, each cell a 1,200 s window (CONFIRMED
exactly).
At origin tip the chain IS wired (`metrics()` at `asyncbackend.py:296` -> `published_engine_metrics()`
at `:262` -> `scrape_metrics()` at `:252`, behind an allow-list `PUBLISHED_ENGINE_KEYS` that
deliberately withholds `vllm:num_requests_waiting` per D218 (3)). **But `METRICS_SCRAPE_DEFAULT` is
still `False` at `:161`, and `metrics_scrape` has NO production setter**: a grep over
`run_live2_real.py` returns rc=1 (no match, not an error), and repo-wide the only non-proof matches are
`asyncbackend`'s own `getattr` defaults and prose. `scrape_metrics()` returns `{}` unless something
sets it. `research/STATUS.md:62` states the same conclusion independently. **The paperwork landed and
the enabling switch did not.** Row stays open.

**10.10 Guard backlog leg. CONFIRMED, unexercised.**
`guard_by_backlog` present and **0** in all 16 cells where it appears at the pin, 17 at origin tip,
each a **1,200 s** window at n16, while `guard_by_lag` carries 100 percent of activations. The only
counter present and zero everywhere. `GUARD_BACKLOG_DEFAULT = 100` at `arms_v5rules2.py:83`, read at
`:197`, so the read exists.

**10.11 Flexible split by w_d. CONFIRMED, unexpressible.**
*Read looked for:* the consumption of `weights_by_type` in an admission decision.
*Path walked:* `arms_v6fairfeed.py:136` `_feed_split` -> gate `:225` `live2_share_weights()` ->
`coordinator.py:1626-1631` `SA.allowed(..., weights_by_type=_wbt)`. **`coordinator.py:1615` is
`if not self._share_admission or qtype is None: return True`**, and `_share_admission` is False on all
five arms, so the call at `:1630` is unreachable. CONFIRMED exactly at the cited line. The weight is
computed and never consumed.

**10.12 The lexicographic objective (D165 (A)). CONFIRMED.**
`arm_names_v6.py:59`, inside the rung-3 `V6_LADDER` entry:
`"missing": ["the D165 lexicographic objective is not built"]`. In the code itself, as the matrix says.
No later D-row removes it, including D228.

**10.13 KEEP-READY SET and ADMIT WITH PROTECTED VICTIM (D165 (D)). CONFIRMED, two mechanisms.**
`arms_v6cf.py:540` and `cf_protect_defer.py:628` both carry
`not_built=["keep-ready set", "admit with protected victim", "plan_sync"]` as declared data.

**10.14 Reload-from-host as an explicit action, and counterfactual sync. CONFIRMED, with two citation corrections.**
*Read looked for:* a production caller of `plan_sync`.
*Path walked:* `plan_sync` is defined at **`v5/cf_planner.py:776`**, not `:619` as the matrix says. It
has an intermediate caller the matrix does not mention: the dispatcher `plan()` at
`v5/cf_planner.py:429-440`, `if kind == "sync": return self.plan_sync(**kw)`. I walked that one hop
further: `.plan(` has exactly two call sites in live2, `v5/cf_proofs.py:622` and `:627`. **So the
matrix's conclusion holds (no production caller) and its "its only caller is cf_proofs.py" is one hop
short of the truth.** D226 (1) puts network after the freeze.

**10.15 C2 and C5 at rung 1. RESOLVED. See section 6.** Not a Rule 2 class; a cell-vintage artefact.

**10.16 The rung-4 service prediction from the failed-gate model. CONFIRMED in every link, and now RULED.**
Every link re-derived at `c5e7bb49`:

| link | verified |
|---|---|
| both legs import the same cost module | `arms_v6cfr3.py:99`, `arms_v6cf.py:74` |
| which model it reads | `cf_cost.py:63` `GATE_JSON = .../cost_model_gate.json`; `:66` `GATE_SPLIT = "by_arm"` |
| that model's own status, in code | `cf_cost.py:67` `GATE_STATUS = ("FAILS (spec v5 section 12): decode over-predicts by 25 to 32 percent in every held-out class, and warm is confounded with arm ...")`, verbatim |
| the queueing feature is a REQUEST COUNT | `cf_cost.py:135` `overlap_ft: int`; `:156` `float(f["per_overlap"]) * max(int(overlap_ft), 0)` |
| its coefficient | `cost_model_gate.json` `splits[by_arm].model.first_token.per_overlap = 0.038004811772727576` |
| D162's ruled term is seconds per UNCACHED TOKEN | `d162_price.py:37` reads `cost_model_gate_d162.json`; `:48` `PER_QUEUE_S = 0.0001535807289338535`; `:49` names its source |
| the ratio | **0.038004811772727576 / 0.0001535807289338535 = 247.4582067460825**, matrix says 247.46x |

**CONFIRMED exactly, including the arithmetic.** The matrix's "accidental mercy" also holds: while
`overlap_ft` is the hard zero of 10.2, the failed gate's queueing coefficient contributes nothing, so
the 247x unit error is LATENT in every committed rung-4 cell. **And the ruling the matrix asks for
exists: D228 (1) sets reading (B)**: the prediction moves to the D162 model, the one that passed
(D168), with uncached tokens queued ahead. That resolves both halves of the matrix's question at once.
The code at origin tip is unchanged, so the row is now ORDERED AND NOT APPLIED rather than awaiting a
ruling.

### 7.3 The design-log row that changes the gate

**The matrix says the design log has 229 rows, D1 to D227 plus D155a and D156a. CONFIRMED at
`4a73e125` (229 rows, highest D227). At origin tip there are 230 and the highest is D228**
(`8d29e86b`, 2026-11-24 10:12, which postdates both the matrix and the prior verification). D228 is
the only unclassified row against the matrix's partition. It rules on three gate rows: 10.6
(withdrawn), 10.2 and 10.16 (reading B), and states in (3) that "D221 is built as specified", which
bears on 10.1.

## 8. OTHER SECTIONS CHECKED

**§3, the partition. CONFIRMED EXACTLY, by set arithmetic on the matrix's own four lists.**
M 140, P 48, E 31, W 14, sum 233; union 229; pairwise overlaps `M&P = {D190}`, `M&E = {D209, D213}`,
`M&W = {D84}`, and `P&E`, `P&W`, `E&W` all empty. Against the design log at `4a73e125`: 229 rows, 0
unclassified, 0 classified strings that are not real rows. One prose defect: the M-set paragraph ends
"139 in all" where the list is 140 and the table says 140. **REFUTED** as a number, immaterial.

**§5, the spec. CONFIRMED.** `policy_spec_v6.md` is 263 lines; the highest D-row it cites is **D182**;
`D2[0-9][0-9]` has no match; and the five literal counts are all **0** (`c5attr`, `DEVICE_ANSWERS`,
`max-model-len`, the `-final` ladder name, the alert release re-check in section 5). So D183 to D228,
45 rows at origin tip, are unapplied to the spec.

**§8, mechanisms with no D-row. CONFIRMED on the one I spot-checked in full.**
`HARM_FORM_DEFAULT` is declaration-only: three occurrences, no branch.

**§9, miscitations. CONFIRMED.** `cstate.py:138`, `:468` and `:486` all cite "D133 Part A" for making
`desired_tier` read and enacted; D133 is robot capacity over feasible questions. Governing row is
D134 (1), as the matrix says.

**§10.18, the four standing notes. CONFIRMED on `desired_tier`.** Three reads exist:
`cstate.py:527` and `:530` (live; `placement_enacted: bool = True` at `:473`) and `:562`, the
eviction-order sort key (inert; `kv_capacity_enforced: bool = False` at `:474`). The "write-only
`desired_tier`" note is REFUTED, as the matrix says. The matrix cites those two flags at `:471`/`:472`;
they are at `:473`/`:474`.

### 8.1 A COMPLETENESS GAP: the code's own ladder table is stale and gets no row

The matrix treats the non-final ladder and the "value reader on" string as **spec** contradictions
(C2, C13). They are also in **code**, and §8's scope ("every behaviour-changing constant, switch and
named decision branch") does not catch them because they are neither. `arm_names_v6.py:38-65`
`V6_LADDER` names rungs 2, 3 and 4 as `covex-v6-state` / `covex-v6-fair` / `covex-v6`,
`implemented_by` `covex-v6-state` / `covex-v6-fair` / `v5-full`, with `committed_as: []` for rungs 2
and 3; and rung 3's `adds` reads "deficit feed (observe() called by the coordinator) **+ value reader
on**", which D177 (2) removed. This is the registry a reader consults to learn what the ladder is, it
disagrees with the ladder that ran (D208 (2)), and the factory raises against its `missing` list, so
it is not inert documentation. **Recommended: give it a row in §8 or §9.**

### 8.2 Reconciliation with `reports/study_d225_verification.md`

| its finding | my position |
|---|---|
| R1, `d218_prereg.json` exists under `results/` | **Reproduced independently**, and extended: the whole implementation exists under `held/` and was proved dry (7.2, 10.1) |
| R2, 18 of 19 `NOT_SWITCHES` exemptions name no read site | **Not independently checked.** I verified the exemption list exists and is named; I did not audit each entry |
| R3, `dry` and `dry_margin` are switches, not bookkeeping | **Not independently checked** |
| R4, the cell census is pinned to `2e5cd9a5`, not `c5e7bb49` | **Not independently checked.** I read 291 `coordinator_result.json` at origin tip against the matrix's 286 at its pin, which is consistent with cells having landed since and does not settle the pin |
| R5, 10.8's `kept_warm` range excludes a zero | **Reproduced independently**: `covex-v6-state-final` s5 is 0 (5.2) |
| R6, 10.5 is closed for every site D223 (2) names | **Reproduced independently** (7.2, 10.5) |
| N1, the OBSERVED reproduction path is wrong for three Group B rows | **Reproduced independently** (5.1) |
| it is 16 rows in five groups, not 15 in four | **Agreed**, and I add the 19-mechanism count (7.1) |

**What this verification adds beyond it**, all of it postdating `31462233` or outside its scope:
D228 and its effect on 10.2, 10.6 and 10.16; the held DEVICE_ANSWERS build; the new rung-3 `kv0.5r`
cell and its 6 evictions; the settlement of 10.15 by the counter-merge read; the inheritance-versus-
composition correction in section 3; the two composition citations in 3.2; the `plan_sync` dispatcher
hop; the off-by-five signature citations; and the `V6_LADDER` completeness gap.

## 9. WHAT THIS VERIFICATION DOES NOT COVER

- **No cell was run.** Rows whose only remaining question is "does it fire under pressure" are named
  as such and not answered. The one place that mattered, 10.8 at 0.5x, was answered from a cell
  someone else had already committed.
- **`v5/cf_objective.py` and `v5/cf_planner.py` internal constants** beyond the ones a gate row cites.
  The matrix declares this gap in its §11 and I did not close it.
- **The baselines**, out of scope by D225 (1).
- **R2, R3 and R4** of the prior verification, listed in 8.2.
- **The 286-cell census** at the matrix's pin. I read cells at origin tip.
- The 10 of 48 file:line claims in section 4 were audited for line accuracy, not re-walked to a
  decision one by one; the 11 reads I walked to a decision are the ones a gate row depends on.

## 10. RECOMMENDED CHANGES TO THE GATE

| row | action |
|---|---|
| 10.1 | **status correction, then the user's adoption ruling.** It is built and held, not unbuilt |
| 10.2, 10.16 | **build.** D228 (1) reading (B) removes the ambiguity; these are now ordinary work items |
| 10.5 | **remove.** Built at origin tip |
| 10.6 | **remove.** D228 (2) withdrew the order; the code already matches |
| 10.15 | **rule out.** Cell vintage, settled in section 6 |
| 10.8 | **split.** Eviction is now exercised at 0.5x rung 3; offload is unexercised at both levels and needs a D-row or a cell that reaches it |
| 10.9 | **build.** The chain landed; the enabling switch did not |
| 10.3, 10.4, 10.7, 10.10, 10.11, 10.12, 10.13, 10.14 | unchanged |
| new | a row for `arm_names_v6.V6_LADDER` (8.1) |

Counted explicitly, because a count is the thing a freeze turns on: 16 rows minus the three removals
(10.5, 10.6, 10.15) is 13, plus the new `V6_LADDER` row is **14 numbered rows**: 10.1, 10.2, 10.3,
10.4, 10.7, 10.8, 10.9, 10.10, 10.11, 10.12, 10.13, 10.14, 10.16 and `V6_LADDER`. Of those, 10.2 and
10.16 are now ordinary build items with no ruling outstanding. **Rows still
needing a USER RULING rather than work: 10.1 (adopt DEVICE_ANSWERS or keep it separate), 10.12
(build the lexicographic objective or rule it out), 10.13, 10.14.**
