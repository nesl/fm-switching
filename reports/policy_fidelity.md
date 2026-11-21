# Policy fidelity: what the decisions D56 and D145 to D163 specify, and what is actually built

Session D (flash / A6000), 2026-11-21 ~13:00. Read-only audit of committed source. No run.

**Why this exists.** Results have been reported from `v5-rules`, `v5-rules-2` and the WARM-ALL
family as though they measured the policy those decisions describe. This audit asks, per decision,
whether the mechanism exists, whether it is READ (CLAUDE.md Step 2: a quantity written and never
read is ABSENT), and which committed result families ran without it. **The user's prior is
confirmed on the two biggest items: the host tier and per-type state management were designed and
were never built.**

## Method, and the register of this document

- **The authoritative decision text for D154 to D163 is NOT in this repository.** It lives in the
  user's design log. `research/DECISIONS.md` contains no D-numbers; `research/policy_spec_v5.md`
  carries D143 to D153. So for the later decisions my reading comes from the user's verbatim
  messages and from the code's own citations. Where a verdict depends on my reading of a decision
  rather than on code, it is marked **READING**.
- Everything marked IMPLEMENTED, PARTIAL or MISSING is a statement about **code**, with
  `file:line`, and is checkable without the decision text.
- "PARTIAL" is used in one specific sense throughout: **the mechanism exists and is reachable, but
  the thing the decision asked it to affect is not affected.**

## 1. The headline: the host tier is MODELLED, never ACTUATED

| | |
|---|---|
| decision | **D56**, which makes the tier a policy decision |
| verdict | **PARTIAL. Believed and modelled; never actuated against the engine.** |

`cstate.enact_placement` (`cstate.py:429-512`) is the one shared steering path. Every statement in
it writes the coordinator's own `SessionRec` fields: `set_tier` (`:471`, `:506`), `last_touch_s`
(`:479`), and a sorted eviction order (`:506`). **There is no call to the engine anywhere in it.**
Its own docstring says so at `cstate.py:432`:

> "Residency cannot be COMMANDED in vLLM (D44), so this STEERS: an offload request moves the KV
> down, a keep-warm request protects a session in eviction order and refreshes its touch time...
> **Nothing here pins a session on the GPU.**"

So when an arm emits `OFFLOAD_TO_HOST` or `KEEP_GPU_WARM`, the session's KV does not move. What
changes is the coordinator's model of where it is, which then changes that model's own future
beliefs and its own eviction ordering. The engine's real prefix cache does whatever its LRU does,
independently.

**The only real actuator in the whole system is sending a request.** That is why warm-ahead works
at all and why `KEEP_GPU_WARM` does not: a prefill actually touches the engine, a tier marking does
not.

**`desired_tier` in full**, since CLAUDE.md names it as the motivating write-only failure and the
situation has changed since: declared at `schema.py:348` and `cstate.py:122`, written at
`coordinator.py:500` and `:502`, and READ at `cstate.py:471`, `:474` and `:506` inside
`enact_placement` and nowhere else. So it is **no longer write-only** (D133 Part A fixed that), but
every one of its reads is inside the model, so the fix made it steer a simulation.

## 2. Per-decision verdicts

| decision | subject | verdict | evidence |
|---|---|---|---|
| **D56** | tier as a policy decision | **PARTIAL** | modelled only, section 1 |
| D145 | scored bodies / delivery | IMPLEMENTED | `bodies.py:65-70`, committed-script reads |
| D146 | delivery and rescore | IMPLEMENTED | `completion_delivery_rescore.py`, `frozen_headline.py` |
| D147 | warm-state contention | IMPLEMENTED | `warm_state_contention.py`, `arms_v5rules.py:15` |
| D148 | episode context | IMPLEMENTED | `bodies.py` EP-G constants, `coordinator.py` |
| **D149 (1)** | value reader / deficit weighting | **PARTIAL** | sections 3 and 4 |
| **D150 STATE** | state levers | **PARTIAL** | lever 1 only, section 5 |
| **D150 SYNC (1)** | upload contract | IMPLEMENTED | `schema.py:35`, `run_live2_real.py:122`, per-frame |
| **D151 (3)** | counterfactual REQUEST decisions | **BUILT, WIRED TODAY** | `cf_planner.py:339`, called from `arms_v5full.py` |
| **D151 (3)** | counterfactual STATE decisions | **MISSING from every arm** | section 6 |
| **D151 (3)** | counterfactual SYNC decisions | **MISSING from every arm** | section 6 |
| **D151 (4)** | deficit weighting in the objective | **PARTIAL, functionally inert** | section 4 |
| D151 (5) | decision-latency instrument | IMPLEMENTED | `cf_instrument.py:62-147`, p99 and distribution |
| D151 (6) | cost-model gate | IMPLEMENTED, FAILS | `cost_model_gate_d156*.py`, verdict FAIL |
| D152 (1) | harm to other devices | IMPLEMENTED | `cf_objective.py:195` `option_value` |
| **D152 (3)** | per-frame prefill | **WITHDRAWN by D160 (1)** | superseded, not a gap |
| D153 | EP-G dashcam format | IMPLEMENTED | `schema.py`, `bodies.py`, `fleet/trace.py` |
| D154 (1) | robot deadline 3.0 s | IMPLEMENTED | `data_sources.py` `ROBOT_DEADLINE_S = 3.0`, at `f1d32c7` |
| D154 (4) | per-frame upload | IMPLEMENTED | `fleet/trace.py`, `_rq`/`_perframe` tags |
| D155 | measured warm device latency | IMPLEMENTED | `scorer/score.py:241-258`, refuses rather than guesses |
| D156 (4) | gate fit/test split | IMPLEMENTED, FAILS | `v5/cost_model_gate_d156.py` |
| D157 (2) | MARGIN_CF units | IMPLEMENTED, unset | `cf_margin.py:81-93`, raises `MarginUnset` |
| D158 | race fix | IMPLEMENTED | `coordinator.py`, `racefix_proofs.py`, 4,244 to 0 |
| D159 (A) | yield diagnosis | IMPLEMENTED | `engine_actions.py:141`, UNEXERCISED, 0 of 12,001 |
| D159 (C) | re-ask trace | IMPLEMENTED | `fleet/trace.py`, `--robot-reask-mean-s` |
| D159 (D) | SS2 confidences | IMPLEMENTED | `cstate.py:540-575` |
| D159 (E) | pre-race-fix audit | IMPLEMENTED | `v5/race_fix_cell_audit.py` |
| D160 (1) | chunked warming | IMPLEMENTED | `arms_v5rules2.py`, count 19.3x down |
| D160 (2) | saturation guard | IMPLEMENTED | `arms_v5rules2.py` `guard_state` |
| D161 | re-ask rulings | IMPLEMENTED | `v5/reask_device_join.py`, 4 seeds |
| D162 | gate scope | **PRE-REGISTERED, NOT YET RUN** | `research/prereg_cost_model_gate_d162.md` |
| **D163** | unknown | **NO TEXT AND NO CODE** | **zero citations anywhere in the tree** |

**D163 has zero occurrences in any file.** Either it has not been issued to me or it has not been
implemented; I cannot tell which and have not guessed. **READING.**

## 3. The value reader is built and OFF in every v5 arm

`c3_value_reader` defaults to **`False`** (`hybrid/hybrid_arm.py:149`) and the table is only
constructed when it is true (`:275-276`). Neither committed config sets it:

| config | `c3_value_reader` |
|---|---|
| `hybrid-F-lhreq` | **not set, so False** |
| `hybrid-F-lhreq-noc3` (the base of v5-rules, v5-rules-2 and full v5) | **not set, so False** |

So **every v5-family result was produced with the D149 value reader disabled.** It is not missing
code; it is unexercised configuration.

## 4. The deficit counters are never fed

`cf_objective.DeficitCounters` exists (`cf_objective.py:126`) with an `observe()` method documented
as "updated from the REALISED on-time outcome of each opportunity" (`:127`). **The only calls to
`observe()` in the entire tree are at `cf_objective.py:294` and `:296`, inside that module's own
`__main__` demonstration.** No arm, no coordinator path and no scorer calls it.

Consequence: in any run, every device's deficit stays at its initial value, so the deficit
**weight** is a constant across devices, and D151 (4)'s weighting cannot change any decision.
**This is the write-only-field failure in a new place**: the mechanism is built, instrumentable and
non-zero, and the thing it exists to influence is not influenced. Under CLAUDE.md Step 2 the link
is **ABSENT**.

## 5. D150's state levers: one of four

| lever | built? | actuated against the engine? |
|---|---|---|
| warm-ahead prefill | **yes**, `engine_actions.py:156` | **yes**, it sends a real request |
| `KEEP_GPU_WARM` | dispatched, counted, handled | **no**, model only |
| `OFFLOAD_TO_HOST` | dispatched, counted, handled | **no**, model only |
| `EVICT` | dispatched, counted, handled | **no**, model only |
| `RELOAD` | offered only at HOST-WARM | **never reached**, CLAUDE.md's own Rule 2 example |

`arms_v5rules.py:18` states the position plainly for its own arm: "no value reader, no deficit
weighting, no KEEP_GPU_WARM, no OFFLOAD_TO_HOST, no EVICT, no...". That is accurate and it is also
the whole v5 family.

**Per-type state management is not built.** There is no policy that treats robot history, dashcam
episode and single-shot state differently as a *state* decision. What exists is warm-ahead applied
to robot sessions only (`arms_v5rules2._candidates`), which is a candidate filter, not a per-type
state policy.

## 6. The counterfactual: one of three decision kinds is wired

`cf_planner` implements all three (`plan_request:339`, `plan_state:491`, `plan_sync:619`). Callers:

| | called from |
|---|---|
| `plan_request` | `cf_planner.py:331` dispatch, `cf_proofs.py`, **and `arms_v5full.py` as of today** |
| `plan_state` | `cf_planner.py:331` dispatch and `cf_proofs.py:596-604` **only** |
| `plan_sync` | `cf_planner.py:333` dispatch and `cf_proofs.py:611` **only** |

**No arm has ever called `plan_state` or `plan_sync`, including the one I wrote today.** My
`arms_v5full.decide` calls `plan_request` and nothing else, so full v5 as it currently stands
implements one third of D151 (3). I am recording that against my own component-2 report, which
claimed the arm covers "robot request, state and sync decisions": **the describe block lists three
kinds and the code plans one.** That is my error and it is the same shape as the proofs that
measured the wrong quantity.

## 7. What each committed result family ran without

| | hybrid-F / noc3 | WARM-ALL family | v5-rules | v5-rules-2 | full v5 (unrun) |
|---|---|---|---|---|---|
| host tier actuated | **no** | **no** | **no** | **no** | **no** |
| `KEEP_GPU_WARM` / `OFFLOAD_TO_HOST` / `EVICT` effective | **no** | **no** | **no** | **no** | **no** |
| `RELOAD` ever reached | **no** | **no** | **no** | **no** | **no** |
| per-type state policy | **no** | **no** | **no** | **no** | **no** |
| value reader (D149) | **off** | **off** | **off** | **off** | **off** |
| deficit weighting fed (D151 (4)) | n/a | n/a | n/a | n/a | **no, never fed** |
| warm-ahead | no | **yes** | **yes** | **yes, chunked** | yes |
| saturation guard (D160 (2)) | no | no | no | **yes** | yes |
| counterfactual REQUEST | no | no | no | no | **yes** |
| counterfactual STATE / SYNC | no | no | no | no | **no** |
| cost model / MARGIN_CF | n/a | n/a | n/a | n/a | **gate FAILS, margin unset** |

## 8. What this means for results already reported

**It does not invalidate the measurements; it narrows what they are measurements OF.** Every number
in `reports/study_v5_rules.md`, `study_v5rules2_live.md` and the frozen-test table is a real
measurement of a real run. What they are not is a measurement of the policy D56 and D150 describe,
because the tier actions in that policy do not reach the engine.

Specifically, and these should be read as corrections to how I have been reporting:

1. **"v5-rules-2 beats noc3 by-deadline 0.485 against 0.470" is a comparison of two arms that
   differ only in warm-ahead and the guard**, not of a full state policy against a baseline. Every
   other state lever is inert in both.
2. **The warm-ahead findings are the most robust things here**, because warm-ahead is the one lever
   that actuates. The chunking result, the prefix-cache-miss result and the guard behaviour are
   all about real engine traffic.
3. **"Warm" in every report means the engine's own prefix cache**, not a managed host tier. There
   is no host tier in any run. Where a report says a history was "host-warm", that is a belief.
4. **The cascade and deficit conclusions rest on channels that were off**, and the D159 (D) wiring
   fixed one of them two hours ago.

## Register

- Every verdict above is a statement about code with `file:line`, except the four marked READING.
- The decision text for D154 to D163 is **not in the repo**; my reading of those comes from the
  user's messages and the code's citations.
- **Nothing here was run.** This is a source audit.
