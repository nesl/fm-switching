# CONFORMANCE MATRIX (D225): decisions must be what the code does

**Standing rule and FREEZE GATE.** D225 (6): no freeze and no held-out seeds 1 to 3 until every row
here is built-and-live or ruled-out with evidence. This table checks CODE AGAINST DECISIONS. It does
not check whether a decision is right; that is the user's call (D225, closing sentence).

Built under D225 (1) to (4) and D200 (4). Verification is a separate session's job (D225 (5)): this
file was written by a session that did not write the policy code, and every row is meant to be
reproducible from the file:line and cell name it gives, without asking its author.

## 0. PROVENANCE, AND THE TREE THAT WAS WALKED

| what | value |
|---|---|
| code read at | `2e5cd9a592f703507cbb8cb561c487294470e2a8`, re-run at `a4eaf9bc`, re-pinned at **`c5e7bb4926a23c68e12d22c3f337462897408d51`** |
| switch state resolved at | `a4eaf9bcde60a0aeb5cd6a3431950ece8577b189`, by constructing the five arms |
| every file:line below re-read at | `c5e7bb49`, with `git show c5e7bb49:<path>`, never from a shared worktree |
| committed cells read from | `results/orchestration/live2/frozen_test/runs/`, 286 cells carrying `coordinator_result.json` |
| design log | `research/policy_design_log.md`, **229 rows**: D1 to D227 plus D155a and D156a |
| spec | `research/policy_spec_v6.md`, 263 lines |

**THE POLICY CODE IS BYTE-IDENTICAL ACROSS ALL THREE SHAS, AND THIS IS PROVED BY TREE HASH RATHER
THAN BY A DIFF THAT RETURNED NOTHING.** `git rev-parse <sha>:experiments/orchestration/live2` is
`23233f43ced179e7e57218814fc88a5ca2e4dde9` at `2e5cd9a5`, at `a4eaf9bc` AND at `c5e7bb49`; likewise
`experiments/orchestration/baselines` is `e1717290`, `experiments/orchestration/policy` is
`64f7a284` and `experiments/lib` is `46a6bf61` at all three. A tree hash settles this in a way an
empty diff cannot: an empty diff is also what a mistyped pathspec returns. The six intervening
commits changed figure data, a handoff file, `d223_context_limit_offered.json`, two cells, and the
design log (D227). **So every switch state and every file:line below holds at `c5e7bb49`.**

**THE SWITCH COLUMNS WERE NOT READ FROM A SHARED WORKTREE.** The repo's own working tree is
**1,795 commits behind origin** (`git rev-list --count <shared HEAD>..origin/main`, HEAD
`17bdf159`) and carries one uncommitted edit to `coordinator.py`, so reading switch state there
would mix three trees. Be exact about which file: `git status --porcelain` on that tree shows
`M experiments/orchestration/live2/coordinator.py` and **`arms.py` is NOT modified**. Most other
live2 files show there as `??` untracked, which is the staleness itself and not a local edit. Every file:line here was read with
`git show <sha>:<path>` against a pinned sha, or from a private sparse worktree checked out at one.
Note the correct test for a live edit, because getting it wrong once is easy: a live edit differs
from origin AND from the stale HEAD. "Differs from the stale HEAD" alone is also true of a file
that simply matches origin.

**TWO ROWS BELOW ARE MOVING TARGETS AND ARE DATED, NOT SETTLED.** E1 (the `/metrics` scrape) is
being wired by another session as this file is written, and rung-4 pass 1 is mid-build. Those rows
say "absent at sha X" and name the read that was looked for, rather than asserting a settled state.

**WHY THE TREE IS NAMED IN EVERY ROW.** `/home/pragya/Desktop/FM-switching` is 1,795 commits
behind origin (the same measured number as above, stated once so the document cannot quote two
figures for one quantity) and holds 35 of origin's 418 `coordinator_result.json`, 8.4 percent. A `grep -r` or
`find` there returns nothing for files that exist, and files committed today show as untracked. That
has produced a confident false negative in two independent sessions. Nothing here was read from it.
Every census states the tree it walked and how many files it opened out of how many exist, because
a sample size quoted beside a negative makes the negative sound measured.

## 1. REGISTERS. EVERY CELL IN THIS FILE CARRIES ONE

D225 (1) asks for switch state read from code and live evidence observed from a committed cell.
Those are different registers and a number in the wrong one survives every arithmetic check, so each
is marked:

| register | means | how to reproduce |
|---|---|---|
| **CODE** | read from source, or resolved by constructing the arm in this process | the file:line given, at the sha in section 0 |
| **OBSERVED** | a counter read out of a named committed cell | open that cell's `coordinator_result.json` -> `arm_stats` |
| **ABSENT** | a read was looked for and not found | the grep given, with its rc and its full occurrence count |
| **ORDERED** | a D-row requires it and the code does not do it yet | the D-row, and the site that still has the old behaviour |

Three register traps in this repo specifically, all of them already paid for:

1. **`arm_stats` is SPARSE.** A counter that never increments is absent from the JSON. So in the live
   evidence column **ABSENT means "never fired in this cell", NOT "not built"**. Proof that the
   distinction is real: `c5_decrease` at rung 4 reads s4=1, s5=3, s6=absent, s7=5. Switch state can
   therefore only come from code, never from counter presence.
2. **`header.json`'s `flags` is `{}` in all 20 ladder cells.** Committed headers record no switch
   state at all, so the switch columns cannot be corroborated from cells, only from code.
3. **`is_measurement` is `False` on EVERY cell** (`coordinator.py:2218` hardcodes it) and
   `scheduling_policy` is `'fcfs'` for all five rungs including rung 4. Neither is a discriminator
   and neither may be cited as evidence about a particular cell or arm. `arm_version` is a fourth:
   rung 3 and rung 4 BOTH report `covex-v6-fair-feed-1.0`, so it cannot tell rung 4 from rung 3.

## 2. THE FIVE RUNG ARMS, AND THE COMPOSITION CHAIN THAT MAKES THIS MATRIX CORRECT

Resolved by constructing each arm (register CODE, sha `a4eaf9bc`):

| rung | arm name | class | factory | composition chain |
|---|---|---|---|---|
| 0 | `covex-v6-base` | `HybridArm` | `arm_names_v6.register` alias of `hybrid-F-lhreq-noc3` + `over_limit_infeasible=True` | `arm -> arm._b7` |
| 1 | `covex-v6-rules` | `V5Rules2Arm` | alias of `v5-rules-2` + `over_limit_infeasible=True` | `arm -> arm._base -> arm._b7` |
| 2 | `covex-v6-state-final` | `V6StateFinal` | `arms_final_ladder.make_rung2` | `arm -> arm._rules -> arm._rules._base` |
| 3 | `covex-v6-fair-final` | `V6FairFinalWired` | `arms_final_ladder.make_rung3` | `arm -> arm._rules -> arm._feed -> arm._rules._base` |
| 4 | `covex-v6-final` | `V6Final` | `arms_final_ladder.make_rung4` | `arm -> arm._rules -> arm._feed -> arm._rules._base` |

`covex-v6-base` IS `hybrid-F-lhreq-noc3`: one arm under two names (`arm_names_v6.py:39-41` and the
`OLD_TO_RUNG` entry at `:71`). The string `covex-v6-base` occurs nowhere else in the tree, so there
is no separate factory behind the name, and they must not be counted as two arms.

**THE ONE FACT A READER OF THIS MATRIX MUST HAVE.** The ladder is NOT a class hierarchy. `V6StateArm`
has MRO `[V6StateArm, object]` and does not subclass the rung-1 arm; it COMPOSES one at
`self._rules` (`arms_v6state.py:152`), `V5Rules2Arm` composes the rung-0 arm at `self._base`
(`arms_v5rules2.py:148-149`), and `HybridArm` composes a `B7EdfFeasibilityArm` at `self._b7`
(`hybrid/hybrid_arm.py:303-304`). Attribute access reaches them through `__getattr__`
(`arms_v6state.py:218-219`).

Consequence, and it is the trap this matrix exists to avoid: a diff that reads only the arm's own
`vars()` and class MRO finds `warm_ahead`, `just_in_time`, `chunk_tokens`, `guard`, `guard_backlog`,
`guard_lag_s`, `slice_tokens`, `over_limit_infeasible`, `k_r`, `c3_always`, `cap` and nine more
PRESENT at rungs 0 and 1 and ABSENT at rungs 2 to 4, and reports twenty inheritance breaks that do
not exist. That exact false reading was produced while this matrix was being built, by a walker that
skipped `_rules` because these arm classes define `__call__`, so `callable(_rules)` was true. The
switches are all there, at identical values, one and two objects down. **A switch resolved through
the chain is marked `dlg` in the tables below, and `dlg` is not inheritance.**

## 3. D-ROW CLASSIFICATION: 229 ROWS, WHAT HAPPENED TO EACH

D225 (1) asks for one row per POLICY-RELEVANT D-row. Classifying which rows those are is itself a
judgement, so the classification is stated and counted rather than assumed.

| class | count | gets a matrix row | why |
|---|---|---|---|
| **M** policy mechanism in code | 140 | yes, section 4 | names something the policy code must do or be able to do |
| **P** process, run order, autonomy, git, naming, priorities | 48 | no, listed in 3.2 | binds sessions and machines, not the policy's behaviour |
| **E** evaluation, metric, scoring, figures, baseline set | 31 | no, listed in 3.2 | scored offline from committed cells; changes no arm decision |
| **W** workload, dataset, trace, device measurement | 14 | no, listed in 3.2 | identical for every arm by construction (fairness digest, D96) |
| sum of the four | 233 | | |
| **minus 4 rows counted twice** | -4 | | **D84, D190, D209, D213**: different clauses of one row fall in different classes, so each is listed under both. Named rather than silently dropped from one side |
| distinct rows | **229** | | D1 to D227 plus D155a and D156a |

**THIS PARTITION IS CHECKABLE AND WAS CHECKED.** Taking the four lists as sets: their union is all
229 rows with nothing missing and no string that is not a real row, and the only pairwise overlaps
are the four named above (`M&P = {D190}`, `M&E = {D209, D213}`, `M&W = {D84}`, and `P&E`, `P&W`,
`E&W` all empty). A classification that does not add up is the first place a reader should lose
confidence in a matrix, so the arithmetic is shown rather than asserted.

The M set, in full, so the complement is checkable: D2, D3, D5, D9, D10, D11, D12, D14, D15, D16,
D17, D19, D23, D24, D25, D26, D28, D29, D30, D32, D34, D39, D40, D43, D44, D45, D46, D47, D48, D51,
D52, D53, D54, D55, D56, D57, D62, D63, D66, D71, D81, D84, D96, D98, D99, D100, D102, D104, D107,
D108, D109, D112, D114, D117, D118, D119, D120, D121, D122, D125, D126, D128, D132, D133, D134,
D137, D140, D142, D143, D146, D147, D148, D149, D150, D151, D152, D153, D154, D155, D156, D156a,
D157, D158, D159, D160, D162, D164, D165, D166, D167, D168, D169, D170, D171, D172, D173, D174,
D175, D177, D178, D179, D180, D181, D182, D183, D184, D185, D186, D188, D190, D191, D192, D193,
D195, D198, D200, D201, D202, D203, D205, D206, D207, D208, D209, D211, D213, D215, D216, D218,
D219, D220, D221, D222, D223, D224, D225, D226, **D227**. Plus D72 and D139, which the mu row and the
LH-REQ row of section 4 cover: 139 in all.

**Four rows are counted once and listed twice**, because one clause of each is a mechanism and
another is not: D84 (the cache-salt rule is code; the repeated-plays scoring rule is workload),
D190 (rung 4's definition is a mechanism; its priority and role clauses are process), D209 (the
placeholder-triage fixes are mechanisms; the parity and roles clauses are evaluation and process),
D213 (the D211 sequencing clause is a mechanism; the paper baseline set is evaluation).

**Borderline calls, declared rather than buried.** D5, D71, D133, D146, D147, D178 (1) and D192 fix
targets, deadlines and the delivery rule. They are scored offline, which would make them E, but the
policy's own feasibility tests and deficit feed READ the same deadlines and targets, so a change to
them changes decisions. They are classified M for that reason. D213's baseline set is E; its
embedded D211 sequencing clause is M and appears in section 4.

### 3.2 The rows that get no mechanism row, with the reason

93 rows are listed below (48 + 31 + 14). Four of them (D84, D190, D209, D213) also carry an M
clause and so also appear in section 4, which leaves **89 rows that get no mechanism row at all**.

- **P (48):** D1, D4, D6, D7, D8, D13, D18, D20, D21, D22, D27, D31, D33, D35, D36, D37, D38, D41,
  D42, D49, D50, D59, D60, D61, D73, D74, D77, D78, D79, D92, D93, D95, D106, D110, D113, D116,
  D123, D124, D129, D131, D135, D138, D163, D187, D190(2), D196, D210, D212. Framing, scope statements,
  superseded spec issues, pilot and run-matrix design, overnight autonomy, git identity, priorities.
  D1, D4, D36, D37, D38, D41, D49, D50 are the formulation's framing: they constrain what the
  objective MEANS and are checked in section 5 against spec v6 section 1, not against a switch.
- **E (31):** D58, D64, D65, D69, D82, D85, D86, D88, D89, D90, D97, D103, D105, D111, D115, D127,
  D130, D136, D141, D144, D161, D176, D189, D194, D197, D199, D204, D209(2 partly), D213, D214,
  D217. Metrics, headline definitions, figure plans, baseline sets, rescoring rules,
  dataset gates.
- **W (14):** D67, D68, D70, D75, D76, D80, D83, D84(partly), D87, D91, D94, D101, D145, D155a.
  Workload composition, links, memory settings as run inputs, JPEG encoding, device measurement.

## 4. THE MATRIX

Column meanings. **rung** = where the mechanism ENTERS; every higher rung carries it unless a D-row
removing it is cited (D225 (2)). **switch per rung** reads `-` absent, `dlg` resolved through the
composition chain to an inner object at the same value, a value, or `n/a` for a mechanism with no
arm-scoped switch. All switch columns are register CODE at sha `a4eaf9bc`.

### 4.1 Rung 0, the base rules (`covex-v6-base` = `hybrid-F-lhreq-noc3`)

| D-row | decision, one line | file:line and switch | R0/R1/R2/R3/R4 | live evidence (OBSERVED) | status |
|---|---|---|---|---|---|
| D140 (1),(3) | C1 deadline-ordered release index | `hybrid/hybrid_arm.py:188` `sw[c1]`; read `:399,:483,:486` sort keys | True/dlg/dlg/dlg/dlg | ordering is the sort key on every release; no separate counter | built and live |
| D140 (1),(3), D143 (B) | C2 laxity at-risk test, k_r = 0.3 x deadline, dashcam throttle with floor 2 | `sw[c2]` `:188`; `k_r` `:176`=1.5, `k_r_frac` `:177`=0.3, `throttle_floor` `:177`=2 | True/dlg/dlg/dlg/dlg | `c2_throttle_periods`, `c2_throttled_dash` at R0; **no C2/C5 keys at R1**, see 10.5 | built and live |
| D140 (2), D175 (2), D179 (5) | C5 alert-only in-flight cap, AIMD 4 to 8, halves on a 0.8 s trip | `sw[c5]` `:188` | True/dlg/dlg/dlg/dlg | `c5_dash_held` 50,589 at R0 s4; 57,938 at R2 s4 | built and live; replaced as the rung-2 admission rule by c5attr (D184 (1)) |
| D152 (2), D154 (3) | C3 degrade-to-RECENT is OFF: no recent-frames shortcut for recall | `sw[c3]` `:188`; `c3_always` `:177` | False/dlg/dlg/dlg/dlg | the `-noc3` in the arm name; C3 branch never taken | **built and off by ruling D152 (2)**, imposed as a user rule (D155 (4)) |
| D141 | C4 inert, emits no session action | `sw[c4]` `:188` | False/dlg/dlg/dlg/dlg | none | built and off, recorded inert |
| D143 (C), D144 (4) | C6 per-candidate simulation, robot-only | `sw[c6]` `:188` | False/dlg/dlg/dlg/dlg | none on the ladder; `hybrid-F6-lhreq` cells only | built and off; not on the final ladder |
| D132, D142 (3) | b7 feasibility: admit only if deliverable by the deadline | `hybrid/feasible_on_time.py`; inner arm `arm._b7` | n/a, always on | the release path; `release_infeasible*` at R3 | built and live |
| D170, D144 (3), D175 (2) | a recall whose predicted prompt exceeds 32,768 is INFEASIBLE, device answers | `hybrid/hybrid_arm.py:157` `CONTEXT_LIMIT_TOKENS=32768`, read `:411`; switch `over_limit_infeasible` `:173,:187` | True/True/dlg True/dlg True/dlg True | `over_limit_infeasible`, `over_limit_tokens_max` | built and live at EVERY rung incl. base, as D175 (2) requires |
| D139 (1), D142 (1) | LH-REQ robot workload | `hybrid_arm.py:177` `workload='lh_req'` | lh_req/dlg/dlg/dlg/dlg | every ladder cell is `_L3_epg_rq30` | built and live |
| D143 (A), D6 | quality table fitted on the DEV split only | `hybrid_arm.py:178` `quality_fit='lh_req_dev'` | lh_req_dev/dlg/dlg/dlg/dlg | reporting only since D177 (2) | built and live, reporting only |
| D149 (4), D177 (2) | the value reader is REMOVED | `hybrid_arm.py:180` `c3_value_reader`; `value_transform` `:180` | False/dlg/dlg/dlg/dlg | flat or inverted table moved zero decisions (D149 (4) finding) | **ruled out D177 (2)**; OFF everywhere, which is conformant |
| D140 (2) | reserved robot slot ablation | `hybrid_arm.py:176` `reserve` | False/dlg/dlg/dlg/dlg | none | built and off, ablation only (D210) |
| D149 (3) | episode continuity: an admitted episode's frames come before a new episode | spec v6 section 5 line 84 | n/a | not separately counted | built and live, no switch |
| D153 | minimum 3 frames: earlier instants are not decision instants for ANY arm | `fleet/trace.py` `EPG_MIN_FRAMES` | harness, all arms | excluded-instant count per run | built and live |
| D148, D153 | alert evidence is the append-only EP-G episode, 21-frame cap | `fleet/trace.py` `EPG_CAP_FRAMES`; `bodies.py` | harness, all arms | `epg_cap_frames`=21 in all 20 ladder headers | built and live |
| D154 (1) | alert deadline 1.0 s, no longer provisional | `hybrid/hybrid_arm.py:59` `DASH_DEADLINE_S=1.0` | all rungs | `targets` L=1.0 p=0.25 in all 20 headers | built and live; **citation missing in code, see section 8** |
| D147 | recall deadline 3 s, assistance 2 s | harness; `robot_deadline_s`=3.0 in headers | all rungs | all 20 ladder headers | built and live |
| D14, D49 | representations: RECENT device-only, RICH cloud | `hybrid_arm.py:70` `RECENT_TOKENS=467` | all rungs | the `-noc3` path never sends RECENT | built and live |
| D84 | devices never share cache entries: per-device salt, per-(device,frame) UUID | `cachekeys.py`; `mm_uuid_check.json` per cell | harness, all arms | `mm_uuid_check.json` in 334 cell dirs | built and live |
| D96 | opportunity_id assigned by the trace generator; order-independent fairness digest | `fleet/trace.py`; `fairness_digest` in header | harness, all arms | `fairness_digest` VARIES across 4 seeds, equal across arms | built and live |
| D99 (1) | every arm decides on the same 100 ms period | coordinator loop; `cf_protect_defer.DECISION_PERIOD_S=0.1` | harness, all arms | per-decision logs | built and live |
| D107 | answers forwarded at first content token; every request stamped at the wire | `asyncbackend.py` `on_first` | harness, all arms | `first_line_to_first_content_ms` in `metrics()` | built and live |
| D146 | delivery at COMPLETION for recall and assistance; alert may stay at first token | `scorer/score.py` via `LIVE2_DELIVERY` | scorer, all arms | re-scored cells | built and live |
| D175 (1), D178 (4) | a REFUSED cloud request never replaces the device answer | `score.refused_request_ids` | scorer, all arms | first non-zero case kvflow-prefetch s4 (D175 amendment) | built and live; see 10.8 on its input |
| D102, D173 (1),(2), D174 (1) | budget charged as engine WORK, uncached tokens only, no intercept, no queue term | `d162_price.py:149-150` `RULED_CHARGE_MODE='uncached-only'`, read `:157`; arm switch `live2_charge_mode` | -/-/uncached-only/uncached-only/uncached-only | `budget_refusal` = 0 in every committed v5-rules/v5-rules-2 cell (D174 census) | built and live at every rung, as D173 (2) requires |
| D30, D75, D219 | per-device link emulation, uniform 13.6 Mbit/s and 44 ms RTT | `fleet/links.py` | harness, all arms | network header | built and live |
| D155, D161 (3), D171 (3) | device latency from the measured Orin WARM tables, never the 0.567 s proxy | `fleet/data_sources.py`; read `coordinator.py::_device_wait_s` | harness, all arms | D167: 132 of 132 scored from the WARM table | built and live |
| D167 | the trace's own `device_latency_s` carries the superseded D87 interpolation and must NOT be read live by any arm | written `fleet/trace.py:777`; 42 occurrences tree-wide (rc=0) | no arm reads it | every READ is in the scorer (`scorer/score.py:241,259,322,839`) or `frozen_headline.py:226`, which uses `SC.device_latency_s` and says in a comment at `:224` that reading the trace field would report the superseded D87 value. No `arms_*` or `hybrid_arm` file appears among the 42. | **built and off by ruling, VERIFIED**: the rule holds |

### 4.2 Rung 1, chunked just-in-time warming and the saturation guard (`covex-v6-rules`)

| D-row | decision, one line | file:line and switch | R0/R1/R2/R3/R4 | live evidence (OBSERVED) | status |
|---|---|---|---|---|---|
| D156 (2), D159 (A), D160 (1) | warm-ahead as a RULE: prefill a recall session's unwarmed tail, yielding to deadline work | `arms_v5rules2.py:99,:114` `warm_ahead`; read **`:280`** `if not self.warm_ahead:` | -/True/dlg/dlg/dlg | `warm_ahead_*` counters at R1 to R4; `warm_ahead_yielded_epochs` R4 s4=2, s7=1 | built and live |
| D160 (1) | warming happens in CHUNKS, triggered at a 2,048-token tail, not per uploaded frame | `arms_v5rules2.py:66` `CHUNK_TOKENS_DEFAULT=2048`, `:100,:115`; read **`:249`** | -/2048/dlg/dlg/dlg | `chunk_*` counters at R1 to R4 | built and live |
| D160 (1) | just-in-time: warm early when a question is expected within the horizon | `arms_v5rules2.py:105,:119` `just_in_time`; read **`:253`** | -/True/dlg/dlg/dlg | `jit_*` counters at R1 to R4 | built and live |
| D11, D48, D160 (1) | the question-expectation estimate is CAUSAL: EWMA over questions already seen, never the trace's future | `arms_v5rules2.py:132` | -/live/dlg/dlg/dlg | `_gap_ewma`, `_last_q_t` read at `arms_v6state.py:366-367` | built and live |
| D160 (1) | per-epoch warm slice 1,024 tokens | `engine_actions.py:96` `WARM_AHEAD_SLICE_TOKENS=1024`, `arms_v5rules2.py:106,:120`; read **`:301`** | -/1024/dlg/dlg/dlg | MATERIALIZE actions | built and live; **citation missing, section 8** |
| D160 (2) | SATURATION GUARD: keep the engine out of collapse on LIVE signals, shedding background warming first | `arms_v5rules2.py:104,:118` `guard`; read **`:199`** | -/True/dlg/dlg/dlg | `guard_by_lag` R1 s4-s7 = 4027/3675/3508/4565; R4 = 80/32/117/22 | built and live |
| D160 (2), D178 (3) | guard entry leg 1: first-token lag threshold | `arms_v5rules2.py:81` `GUARD_LAG_S_DEFAULT=2.0`; read **`:196`** | -/2.0/dlg/dlg/dlg | `guard_by_lag` carries 100 percent of activations | built and live, BUT see the next row and 10.3 |
| D178 (3) | guard entry leg 2: queued deadline work exceeds 100 | `arms_v5rules2.py:83` `GUARD_BACKLOG_DEFAULT=100`; read **`:197`** | -/100/dlg/dlg/dlg | **`guard_by_backlog` = 0 in all 16 cells where present** | **built, PRESENT AND ZERO EVERYWHERE.** Rule 2: **unexercised**. Freeze-gate row, 10.10 |
| D178 (3) | guard thresholds are PER TYPE: 80 percent of each type's deadline (0.8 / 1.6 / 2.4 s) | spec v6 section 5 line 83 states the per-type rule | ONE threshold, 2.0 s, for all types | - | **ORDERED, NOT BUILT.** The code has a single `guard_lag_s=2.0`. Freeze-gate row, 10.7 |
| D165, D166 (3) | guard EXIT hysteresis: both signals below 0.5x entry for 2 s | spec v6 line 218 records it as not built | - | - | **ORDERED, NOT BUILT** (D166 (3) is the decision that it should exist). Freeze-gate row |
| D154 (4), D150 SYNC (1), D160 (1) | robot frames upload per frame as captured, for ALL arms, decoupled from warming | `fleet/trace.py` | harness, all arms | all ladder cells are `upload-pf` | built and live |
| D158 (2) | submission race: a frame's bytes count as sent only when its request returns 200 | `arms_v5rules2`/coordinator send path | harness, all arms | `n_errors=0` on the ladder cells | built and live |
| D162 | cost model: NNLS, non-negative, healthy-regime only, first_token ~ b0 + b1 uncached + b2 uncached-queued-ahead | `d162_price.py`; `cost_model_gate_d162.py` | input to R2 to R4 | gate PASSED at 68a2b47, ratio_p50 1.052 overall, 1.070 warm (D168) | built and live; spec section 12 still says PARTIAL, see 9 |

### 4.3 Rung 2, per-type state management (`covex-v6-state-final`)

| D-row | decision, one line | file:line and switch | R0/R1/R2/R3/R4 | live evidence (OBSERVED) | status |
|---|---|---|---|---|---|
| D172 rung 2 | the rung-2 state planner as a whole | `arms_v6state.py:137,:158` `plan_state`; gates the four `_d(...)` switches at `:160-165` | -/-/True/True/True | `state_*` counter family from R2 up | built and live |
| D26, D150 STATE | state candidates per recall history: warm, touch, reload, hold, let go cold | `v5/cf_planner.plan_state`, reached `arms_v6state.py:430` | -/-/live/live/live | R2 s4 `state_chosen_TOUCH` 2399, s5 ABSENT, s6 408, s7 2201; `state_chosen_WARM` 4/-/-/3; `state_chosen_HOLD_BACK` 2/4/6/- | built and live, but **class differs by seed**: TOUCH is unexercised at s5, where the planner chose KEEP 64,846 times and emitted no touch. 10.6 |
| D167, D150 | per-type host retention: alert and single-shot skip host retention (`max_offload_tokens=0`), recall histories retained | rule `offload_policy.py:30-52`, reader `:72`; switch `live2_offload_controls` `arms_v6state.py:162`; enacted **`coordinator.py:1529`** `kv_transfer_params=OP.params_for(...)` | -/-/True/True/True | **`offloaded` = 0 in 20 of 20 ladder cells**; `over_cap`=0, KV peak 40-53k of 62,944 | **built, enactment path works (`kept_warm` 173-4300), eviction branch NEVER REACHED at 1x.** Rule 2: **unexercised**. Freeze-gate row, 10.8 |
| D150, D59, D209 (2) hit 22 | TOUCH: a minimal request reusing a warm prefix to keep a history ahead of LRU | `coordinator.py:698` `_submit_touch`, dispatched `:513`, switch `live2_touch_requests` `arms_v6state.py:163`, enacted **`coordinator.py:833`**; rule `touch_policy.py:49-77` | -/-/True/True/True | `state_chosen_TOUCH` above; 0 of 2,267 touches refused (D216) | built and live |
| D209 (2) hit 22 | touch price mode is assigned, not a placeholder (was never assigned, overcharging 105x to 154x) | `touch_policy.py:126` `TOUCH_PRICE_MODE='d174-uncached-only'`, validated `:179-181`, branched `:182,:184` | module-global | D216: the fix does not move R3 or R4 (overcharge unexercised at 1x) | **built and live, hit 22 CLOSED** |
| D173 (2) | state-based pricing of decisions in the planner | switch `live2_state_priced_costs` `arms_v6state.py:164`, reader `touch_policy.py:247`, enacted **`coordinator.py:1237`** | -/-/True/True/True | `cf_planner_*` counters from R2 | built and live |
| D44, D47, D150, D211 | residency belief corrected from engine telemetry | switch `live2_belief_apply` `arms_v6state.py:165`, read **`coordinator.py:364-365`**; env `BELIEF_CORRECTION` `coordinator.py:141` default `observe` | -/-/True/True/True | `last_telemetry_cached_tokens` written `engine_actions.py:365`, read `coordinator.py:788`, `:1337`, `arms_v6cfr3.py:173` | built and live. **D150's "dead `telemetry_cached_tokens` read" is FIXED at this sha** |
| D134 (1) | memory placement must change execution, not just set a field | `desired_tier` declared `cstate.py:136`, written `coordinator.py:830,:832`; **reads `cstate.py:527`, `:530`, `:562`** | enacted where `placement_enacted=True` (`cstate.py:471`) | the `:527`/`:530` reads are LIVE | **built and live. REFUTES the standing "write-only `desired_tier`" note.** But `:562` (eviction-order sort key) is INERT: `kv_capacity_enforced=False` (`cstate.py:472`). Miscited in code as "D133 Part A", see 9 |
| D181 (2), D184 (1), D186 | c5attr: C5's trip is attributed, so a dashcam cap does not halve on lateness caused by robot prefills | `hybrid/hybrid_arm.py:292` default; set `arms_v6c5.py:57,:65`; read **`hybrid/hybrid_arm.py:583`, `:727`** | False/dlg False/**True**/True/True | `c5_attr_trip_without_slow_evidence` R2 4/3/8/1, R3 -/2/-/-, R4 none | built and live; adopted as rung 2 by the D184 (1) logged override after shares failed D179 (6)(b) at all four seeds |
| D188 (2), D216 (1), D208 (2) | the `id(obs)` cache-key fix: key on `(epoch, now_s)`, which cannot alias a memory address | name `arms_v6state.py:94`; set `arms_final_ladder.py:106` with read-back; **used `arms_v6state.py:297-301`** | -/-/**True**/True/True | the final ladder IS the rerun D188 (2) held it for | built and live |
| D162, D173 (1), D174 (1) | D162 work pricing on our arms, arm-scoped | `arms_v6state.py:178`, `arms_v6c5.py:53`; reader `d162_price.py:178`; prerequisite checked `coordinator.py:317` | -/-/True/True/True | `submitted_*`, `gain_*` from R2 | built and live. Note: default is **False** when `None`, deliberately not via `_d` |
| D179 (1),(2),(3), D180, D181, D182 | share-based admission: resource W, derived per-type floors, flexible split, borrowing | `share_admission.py::allowed`, `share_capacity.py:61,:65` `W_MAX_TOKENS=4323.3`, floors 1622.1/655.8/242.8; switch `live2_share_admission` `share_admission.py:254` | **ABSENT on all five arms** | `covex-v6-state-shares*` cells exist and are not on the ladder | **RULED OUT D224** (and D186: check (b) failed at all four seeds; retention 0.30/0.56/0.33/0.28 against a 0.90 bar). Floors parked by D188 (1). Correctly absent |
| D218 (2) | the partial-prefix survival predictor (M5 step function) is NOT built | `grep -rni 'p_loss|survival'` over live2 excluding proof/probe/diagnosis/test files: **rc=1, no match**; all 9 occurrences are in `d216_survival_predictor_readsites.py` and a `touch_proofs.py:25` comment | absent | - | **RULED OUT D218 (2)**, recorded as a limitation. Conformant |
| D211, D213 | host residency must be OBSERVED or declared unobserved; ships gated off | `host_counters_d211.log` in 47 cell dirs | gated off | D216 (3): signal (a) not computable, `gpu_tokens_by_session` empty | **built and off by ruling D211 fallback**; the paper must state host reload is native but unobserved |
| D216 (3) | record the belief's predicted GPU-resident prefix per request so D211 signal (a) is computable | `schema.py:316`; written `coordinator.py:2186-2188` on live cells only | written | **sole consumer is the offline `d211_signal_a_available.py:78`; feeds no decision** | built, offline only; conformant with D211's sequencing |
| D56, D29 | memory capacities are INPUTS, passed to the policy | `gpu_kv_tokens`=62944, `host_tier_gib`=27.0 in all 20 ladder headers; `arms_v6cf.py:170` -> read `:315` | configure-time | constant and correct by design | built and live |

### 4.4 Rung 3, the per-device deficit feed and the alert release re-check (`covex-v6-fair-final`)

| D-row | decision, one line | file:line and switch | R0/R1/R2/R3/R4 | live evidence (OBSERVED) | status |
|---|---|---|---|---|---|
| D2, D3, D41, D122 (B), D185 (1) | deficit counters are PER DEVICE, fed from the realised on-time outcome, cloud answers only | `deficit_feed.py`; switch `live2_deficit_feed` `arms_v6fairfeed.py:76`, set `:143,:145`, reader `:102-111`, `_feed_on` `:147` | -/-/-/**True**/True | `deficit_feed` nested dict in R3 and R4 cells; per-device weights **VARY**: dash000 1.1352, dash001 1.131579, dash002 1.14196; robo/asst at the 1.0 floor | built and live. The varying-weight evidence D200 (3) asks for |
| D185 (2), D178 (2) | normalised weight `w_d = 1 + 2.0 x (shortfall_d / target_d)`, floored at 1, range [1,3] | `arms_v6fairfeed.py:131`; `deficit_gain_d178.py:96` `GAIN=2.0`; read **`deficit_feed.py:314`** | -/-/-/2.0/2.0 | `deficit_feed.gain` = 2.0 in R3/R4 cells | built and live. The raw `1 + gain x shortfall` form is NOT run, per D185 (2) |
| D178 (1) | targets: alert 25 percent per episode (19 instants), recall 90 percent, assistance 90 percent | `deficit_feed.py:96` TARGETS {0.25, 0.90, 0.90}; `:149,:152,:160` | -/-/-/live/live | R3/R4 cells carry 0.25/0.9/0.9 and 19 instants per episode | built and live |
| D185 (3)(a) | consumer (a), ORDERING: deadline requests ordered by w_d descending, then deadline | `arms_v6fairfeed.py:135` `_feed_ordering`, gate `:174`, override bound `:191`; consumed as LEADING SORT KEY **`hybrid/hybrid_arm.py:399,:483,:486`** | -/-/-/True/True | the deficit-ordering override path; `covex-v6-fair-c5attr-gain0` is its matched control | built and live |
| D185 (3)(b) | consumer (b), flexible split by max w_d over a type's pending devices | `arms_v6fairfeed.py:136` `_feed_split`, gate `:225` `live2_share_weights()`; consumer `coordinator.py:1626-1631` | -/-/-/True/True | **UNREACHABLE: `coordinator.py:1615` returns True before the `SA.allowed(weights_by_type=)` call, because `_share_admission` is False on all five arms** | **built, switch ON, consumer ABSENT BY CONSTRUCTION.** Rule 2: **unexpressible**. Ruled by D224 (flexible split went with shares); self-documented at `arms_final_ladder.py:48`. Not a defect, but the ON switch is misleading: 10.11 |
| D179 (4), D198 (2)(b), D208 (1) | ALERT RELEASE RE-CHECK: b7 feasibility re-checked at wire time; skips the QUESTION, never the frame | name `release_recheck.py:65`, set `arms_final_ladder.py:181,:249` with read-back; enacted **`coordinator.py:1008`** and **`:1354-1358`** | -/-/-/**True**/True | `release_infeasible` R3 2028/2046/2073/1746; **identical to `release_infeasible_alert` in every cell** | built and live. D208 (1): passed all three D179 checks at all four seeds (alert attainment 0.441->0.626, 0.427->0.637, 0.436->0.640, 0.475->0.653; late alerts -84 to -86 percent) |
| D179 (4) | which types are re-checked | `release_recheck.py:170`, const `arms_v6rr.py:80`; read **`coordinator.py:1008,:1358`** | -/-/-/`('alert',)`/`('alert',)` | the two counters being equal confirms alerts only | built and live |
| D206 (2), D200 (2) | the STATE PLANNER reads the same live feed (one deficit source) | `_PlannerFeedMixin._cf_engine` `arms_final_ladder.py:168` -> `planner_deficit_weights.wire_planner`; checked `:198,:268`; raises if the declared constant survived | -/-/-/True/True | D206 (2) measured 687 of 60,473 dry s4 state decisions change; 63,242 weight reads, 0 unresolved, 53,597 above the floor | built and live. Applied at the final-ladder rerun exactly as D206 (2) sequenced |
| D203 (1), D206 (3) | rungs 2 and 3 use an EXPLICIT constant weight 1 in the state planner; `DeficitCounters` kept but labelled superseded with no live path | `cf_objective.NoPlannerDeficitFeed`; `DeficitCounters` `cf_objective.py:344,:348` | R2 constant 1; R3/R4 read the feed | `d206_guard_proofs.py:176` asserts no registered arm constructs `DeficitCounters` | built and off by ruling D206 (3). **Two miscitations live inside this dead limb, see 9** |
| D200 (3) | fail loud: a weight or score source that is never fed RAISES instead of returning a neutral default | `coordinator.py:691` marks the channel unusable; the three strict readers in `arms_final_ladder.py` | all rungs | the readers raise on a truthy CLASS attribute | built and live |
| D165 (A), D2 | LEXICOGRAPHIC objective: across types compare only by deficit-weighted, window-normalised attainment | spec v6 line 240 marks it MISSING; `arm_names_v6.py` rung 3 carries `"missing": ["the D165 lexicographic objective is not built"]` **in the code itself** | not built | - | **ORDERED, NOT BUILT, NO D-ROW REMOVES IT.** Freeze-gate row, 10.12 |
| D177 | currency is on-time cloud answers; the quality table becomes reporting only | `deficit_feed.py` and `arms_v6fairfeed.py` converted | R3/R4 | `device_on_time` counted beside and never added | built and live on the rung-3 side; the rung-4 harm side is 10.9 |
| D201, D205 | baselines reading a literal-0.0 `delivered_scores` are fixed; real scores delivered | `coordinator.py:695` writes the committed per-instant device score via `fleet/emulator.device_score_of`; `:691` appends `None` with fail-loud; `:1974` cloud upgrade; `cstate.py:648` builds the list | all arms | of D205's seven value readers, **none reads values directly at this sha**; `inarvl_adapted.py:68` and `hybrid_llm_adapted.py:39` carry past-tense comments | **built and live, the D201/D205 fix HAS LANDED.** REFUTES the standing "four writers of a literal 0.0" note |

### 4.5 Rung 4, the counterfactual (`covex-v6-final`)

**READ THIS BEFORE ANY ROW IN 4.5. RUNG-4 PASS 1 IS BLOCKED ON FOUR USER RULINGS, SO NO ROW HERE IS
BUILT-AND-LIVE FOR FREEZE PURPOSES.** The switch columns below are accurate: those switches are ON
and their gates are reached, and the counters prove the legs fire. But "the switch is ON and the leg
fires" is a weaker claim than "the mechanism is built and live", and the difference is section 4.7:
both rung-4 legs price service from a cost model whose own status string says it FAILS, in units
247x away from the ruled ones. A row marked "built and live" in the last column of 4.5 means **the
code path is live at `c5e7bb49`**, not that the mechanism is cleared for the freeze. Every 4.5 row
is carried into the freeze-gate list in section 10 for that reason.


| D-row | decision, one line | file:line and switch | R0/R1/R2/R3/R4 | live evidence (OBSERVED) | status |
|---|---|---|---|---|---|
| D151 (1), D132 | base policy executed by default; deviate only when predicted gain beats the base by MARGIN_CF | `v5/cf_planner.py` | -/-/-/-/live | `pd_decisions` 302/299/293/259; `rd_decisions` 157/152/146/106 | built and live |
| D165 (D), D184 (2), D190 (3), D191 (1) | compound PROTECT AND DEFER: warm/touch H and defer the cold rebuild R that would evict it | switch `live2_cf_protect_defer` `cf_protect_defer.py:118`; gate **`arms_v6cf.py:420`**; enacted **`arms_v6cf.py:494`** `ra.decision="DEFER"` | -/-/-/-/**True** | s4 and s7: `pd_harm_over_bar` 2, `pd_request_crossed_bar_unexpressible` 2, `pd_gate_wanted_to_act_but_a_request_has_no_slice_channel` 2. s5 and s6: nothing crossed the bar | built and live, **and its Rule 2 class DIFFERS BY SEED: unexpressible at s4 and s7, unexercised at s5 and s6.** No blanket class is correct. Reported by D198 (1) as reach-limited at 1x |
| D191 (1), D151 (3) | QUESTION DEFERRAL to the latest safe start when an alert episode is active | switch `live2_cf_request_defer` `cf_request_defer.py:149`, set `arms_final_ladder.py:255`; gate **`arms_v6cfr3.py:256`**; enacted **`arms_v6cfr3.py:297`** | -/-/-/-/**True** | `rd_question_defers` **29/37/29/25**, non-zero at all four seeds; `rd_gate_defer_to_latest_safe_start` same | **REMOVED FROM RUNG 4 BY D232 (2)** (2026-11-24), ruled out on its own live evidence. It was built and live and it fired at every seed (D225 port rule satisfied); it is removed because it did not help. About 54 live firings across the two scored cells, **0 rescues**; at 1x s4 `_rerun` 22 deferrals pair to 0 rescues / 1 on-time loss / 21 no change, and alert on-time inside the deferral windows is **-11.9 pp**. **Rule 2: FIRED AND DID NOT HELP**, and NOT a settled negative (no Step 4 control). Full record and provenance in **10.19** |
| D191 (2), D171 (1), D178 (5) | deviation units: gain and harm are COUNTS of expected on-time cloud answers, each weighted by the device's own w_d; deviate iff weighted gain minus weighted harm exceeds w_d x MARGIN_CF | `_pd_bar_reading='decider'`; bar `cf_protect_defer.py:205`; `effective_margin` in `v5/cf_planner.py` | -/-/-/-/decider | `rd_reached_harm` 98/106/97/73; `rd_gate_saving_does_not_exceed_margin` 69/69/68/48 | built and live. The wrong reading is reachable only as a labelled arm (`...-barmaxharmed`) |
| D177 (3), D154 (2), D157 (2), D158 (1), D169 | MARGIN_CF set once, frozen, never swept: 0.6582 in on-time units | `v5/margin_cf_d169.py`; P_hat `cf_ontime_model_d162.json` | -/-/-/-/0.6582 | D171: n=476, warm 271 | built and live |
| D200 (1),(2), D171 (1) | the counterfactual reads per-device w_d from `live2/deficit_feed.py`, one deficit source | `_pd_w_source=W_SOURCE_LIVE`, set `arms_final_ladder.py:272-277` with a construction probe | -/-/-/-/LIVE | D203 (1) measured 17 distinct values over 22 decisions, w in [1.148, 3.0] | built and live. D200 (5)'s "deficit-blind" label applies PER LIMB (D203 (2)), not as a blanket |
| D193 (2), D186 | price `u_request` with the engine-reported cached prefix, trusted only while the session is not believed COLD | **`arms_v6cfr3.py:173`** `tel = int(inp.get("telemetry_cached_tokens", 0) or 0)` | -/-/-/-/live | `rd_u_telemetry_won` 114/120/109/83; `rd_u_built_won` 42/32/36/23; `rd_u_differs_from_built_only` present | built and live. Fixes the 15.6x recall overpricing D193 (2) names |
| D160 (2) | the counterfactual acts only in the HEALTHY regime and defers to the guard | `v5/cf_ontime_d162.py` | -/-/-/-/live | `state_deferred_to_guard_epochs` | built and live |
| CLAUDE.md Step 4, D218 (1) | Step 4 negative controls: harm-zero and margin-huge collapse the branch to BASE | `arms_v6cf.py:130,:131`; read **`arms_v6cf.py:359,:361`** and **`arms_v6cfr3.py:211,:213`**; `MARGIN_CONTROL_SCALE=1e9` | -/-/-/-/False, False | one control arm disables both legs, so a control is one cell | built and OFF by design; controls exist and are reachable |
| D203 (3), D206 (1), D222 (1) item 4 | Gate A replaced: report EXPOSURE (fraction of sent recall whose observed/predicted ratio exceeds the per-request q90) and the overrun magnitude | `cf_request_defer.py:137` `SAFETY_FACTOR` from `d190_measured_safety`, which RAISES rather than defaulting | -/-/-/-/measured | D206 (1): 46 of 463, 9.94 percent, q90 1.863404, worst overrun 1.5035x | built and live. The would-have-missed count is retired (it was an algebraic identity) |
| D218 (1), D221 | third request candidate DEVICE_ANSWERS: leave the question to the device, enacted as `ra.decision = DEVICE` | **`cf_request_defer.py:177` `ACTIONS = ("BASE","DEFER_TO_LATEST_SAFE_START")`, two actions only.** `cf_protect_defer.py:530` says in its own gate string that DEVICE_ANSWERS "is not built here". The only `ra.decision` writes in the tree are `"DEFER"` at `arms_v6cf.py:494` and `arms_v6cfr3.py:297`; the coordinator channel exists unwritten at `coordinator.py:865` | **absent at R4** | no `rd_*`/`pd_*` counter for it in any committed cell | **ORDERED, NOT BUILT.** Freeze-gate row, 10.1. The four committed `covex-v6-final` cells are the ones D221 declares SUPERSEDED |
| D222 (1) item 1 | the latest-safe-start service prediction must pass the REAL queued-ahead work | **`arms_v6cfr3.py:198-199` `pred = CC.predict(cf.model, int(u_request), 0, 0, 0)`** against `v5/cf_cost.py:148-151 predict(model, tokens, cached_tokens=0, overlap_ft=0, overlap_decode=0)`. The first `0` is correct by construction (`u_request` is already uncached, computed `:173-192`); the defect is `overlap_ft`/`overlap_decode` hard zero, the queue term | not applied | - | **ORDERED, NOT APPLIED, AND NOW MOOT FOR RUNG 4** under D232 (2): the only read of this prediction is the question-deferral leg, which is removed from the arm. This is the quantity `reports/study_rung4_s5_failure.md` attributes 12 of 14 s5 losses to, which is part of why the leg is removed rather than repaired. Still live as a code defect if the leg is ever re-admitted. Freeze-gate row 10.2, see 10.19 |
| D222 (1) item 2 | debit one 100 ms decision period from the deferral | `v5/cf_cost.py:281 deferral_s=max(lss - now_s, 0.0)`; `cf_request_defer.py:175 MIN_DEFERRAL_S = PD.DECISION_PERIOD_S` is used only as a FLOOR at `:267` | not applied | - | **ORDERED, NOT APPLIED, AND NOW MOOT FOR RUNG 4** under D232 (2): there is no deferral left at rung 4 to debit a period from. A floor that rejects sub-period deferrals is not a debit that shortens every deferral, so the order was never satisfied and is now withdrawn by removal rather than met. Freeze-gate row 10.3, see 10.19 |
| D222 (1) item 5 | commit the per-decision `rd_decisions` log beside `decision.jsonl` | accumulated in memory capped at 4,000 (`arms_v6cfr3.py:234-235`), dumped by `cfr3_one_cell.py:78` | not committed | **`find -name '*rd_decision*'` over all 334 cell dirs returns 0** | **ORDERED, NOT SATISFIED in the committed set.** Freeze-gate row. **Touched by D232 (2):** this log records the removed leg's own decisions, so no future rung-4 cell will produce one, but it remains the only per-decision audit trail for the two pass-1 cells the removal rests on. Not declared closed here; the user's call, see 10.19 |
| D220 (1) | harm is the displacement loss weighted by the ACCURACY GAIN (cloud minus device for the displaced type); the device-discounted form is rejected | **`v5/cf_objective.py:712` computes `w_o x (p_before - p_after)` only**, and its docstring `:728-739` states the accuracy factor is deliberately gone under D177 (1). `cf_protect_defer.py:380-395` computes `harm_device_discounted` too but only reports it; `HARM_FORM_DEFAULT` `:336` is a LABEL with no branch anywhere (grep returns only definition, dict string and describe block, rc=0) | not applied | `pd_harms`, `pd_harm_distribution` | **ORDERED, NOT APPLIED, AND IT IS A GENUINE TENSION, NOT A BUG.** D177 removes accuracy because within a type the gap is a constant; D220 (1) reinstates a gain because harm sums ACROSS types, where it is not. The user's call. Freeze-gate row, 10.6 |
| D165 (D) | compound KEEP-READY SET: touch the top-k histories by expected value of their next question | spec v6 line 245: not built | absent | - | **ORDERED, NOT BUILT, no D-row removes it.** Freeze-gate row |
| D165 (D) | compound ADMIT WITH PROTECTED VICTIM: admit q now and touch the history its rebuild would evict | spec v6 line 245: not built | absent | - | **ORDERED, NOT BUILT, no D-row removes it.** Freeze-gate row |
| D151, D54, D150 SYNC (3) | counterfactual SYNC decisions: backlog order after reconnect, question-first vs wait vs device | `v5/cf_planner.py:619 plan_sync` is defined; **its only caller is `v5/cf_proofs.py`** | no production caller | - | **built, NO PRODUCTION CALLER.** Deferred with the network by D219 and D226 (1); D226 (1) puts network cells after the freeze and the code behind switches defaulting OFF. Freeze-gate row pending that reading |
| D150 SYNC (3), D226 (1)(c) | outage handling: device buffers, reconnect upload, type-aware backlog | `NetworkState.connected` has **25 read sites** (22 in `baselines/`, 3 in `arms_policy.py:633,:634,:817`) and ONE production write, hard-coded `True` at **`cstate.py:662`** | **no rung arm reads it**; the three live2 reads are in `arms_policy.py`, off the covex chain | - | **ABSENT in our arms**, not merely inert. Ruled post-freeze by D226 (1). D191 (3) cites `cstate.py:595`; the line has drifted to `:662` |
| D192 (3), D194 (3), D202, D204, D207 | episode EARLY EXIT and the cloud-context lever | spec v6 lines 251-255 record them MISSING | absent | StudyEXIT2 verdict NOT NET POSITIVE; StudyCTX1 NOT BUILD-READY | **RULED OUT with evidence**: D194 (3) excludes it from rung 4, D202 (1) forbids a build before the investigation, D204 and D207 are the investigations and both came back negative. Conformant |
| D216 (2) | scrape `/metrics` so `gpu_kv_fraction` is real; hit-6 fail-loud | `scrape_metrics` defined **`asyncbackend.py:175` with ZERO callers**; `metrics()` `:190-210` returns no `vllm:` key and does not call it; `METRICS_SCRAPE_DEFAULT=False` `:161` read only inside the two uncalled methods; `metrics_health` `:182` callers are proof scripts only; nothing in production sets `metrics_scrape`. Write `cstate.py:697` reads `vllm:gpu_cache_usage_perc` from a dict that never has a `vllm:` key. Decision reads **`arms_v6cf.py:319`** and **`engine_actions.py:288`** | absent | **`pd_kv_bound_by_engine_metric` absent in all four R4 cells; `pd_kv_bound_by_belief` EQUALS `pd_decisions` at every seed: 302/302, 299/299, 293/293, 259/259 = 1,153 of 1,153** | **ORDERED, NOT BUILT at this sha.** Another session is wiring it (D216 (2) / D222 (1) item g); state recorded as observed at `a4eaf9bc`. Freeze-gate row, 10.9 |
| D218 (3) | `vllm:num_requests_waiting` stays unpublished; only mooncake reads it | one read, **`cstate.py:691`**, with an in-flight fallback that always wins | - | 0 lines in the 4 R4 `metrics_snapshots.log` (rc=1) | **RULED OUT D218 (3)**, recorded as a known gap. Conformant |
| D223 (2) | replace the hard-coded 32,768 with the server's configured max-model-len read at run start, before any 0.5x policy cell | **`hybrid/hybrid_arm.py:157`, `arms_v6cf.py:86`, `arms_v6fair.py:90`, `d170_overlimit.py:33` all still literal 32768.** `grep -rn 'max_model_len|max-model-len'` over live2 finds only report prose and `confirm_engine_actions_32b.py`'s own hard-coded constant; **nothing on the live path reads the server's limit** (rc=0, full output inspected) | not applied | committed `kv0.5`/`kv0.5r` cells exist for base and rules; all have `n_errors = 0` | **ORDERED, NOT APPLIED.** Blocks the 0.5x policy cells D223 (1) makes the paper's only pressure level. **Checked for harm to a posted number: none**, see 10.17 |
| D224 | shares and its r1/r2 variants are out of the paper | correctly absent from all five arms | absent | `covex-v6-state-shares*` cells kept for provenance | **RULED OUT D224.** Conformant |
| D219, D226 (1) | network held as used so far; network code behind switches defaulting OFF, cells after the freeze | `fleet/links.py`; no Tier 1 `link_by_device` plumbing | absent | - | **RULED OUT for now by D226 (1)**: post-freeze, secondary axis. Conformant |

### 4.6 Mechanism D-rows that are SUPERSEDED or RULED OUT, with the row that removes them

These are policy mechanisms the log decided and a later row retired. D225 (2) needs them because the
inheritance check must be able to cite a removal rather than find a gap. Each is "ruled out D-x", and
the evidence is that the mechanism is absent from all five rung arms (register CODE).

| D-row | mechanism | removed or superseded by | absent from the ladder? |
|---|---|---|---|
| D9, D17, D45, D55 | background work as a first-class action; rollout-chosen piece size; job-level continuation value; partial-prefix survival in the rollout | D125 (job plans), then the v6 ladder; survival predictor **D218 (2)** | yes; warming is a rule (D156 (2)) and slicing is `slice_tokens` only |
| D19 (SH part), D20, D22, D52 (monitoring part) | device-side escalation trigger and controller signals | **D62**: SH is capacity-based, no trigger is part of the contribution | yes; every instant is a candidate |
| D21, D24 (merging), D27, D28, D34, D66 | phase assignment, call merging, cloud-32B summaries, escalation price from mu, predictive batched upload | **D66** turns all conditional mechanisms off; D154 (4) replaces batched upload with per-frame | yes |
| D23 (calendar), D25, D43, D46 | one coordinator with a calendar; planning horizon H; counterfactual over a horizon; pi_0 = EDF | reshaped by **D117** (pi_0 work-conserving), **D151**, **D160 (2)**; H is no longer an arm switch | the mechanisms survive in changed form; `H` is `None` in all 20 ladder headers |
| D35, D40, D89, D149, D177 | normalisation by SLO gap; bounded task utility with omega class weights; the value reader | **D35 superseded by D40**; **D40/D89/D149 superseded by D177** (currency is on-time cloud answers) | yes; `c3_value_reader=False` on all five arms |
| D51, D39 | unified escalation basis Ghat | **D177**: the accuracy gap is a within-type constant and never changes a decision | yes |
| D53 | task-type posterior from keyword and temporal rules | the workload has typed devices (D67, D136, D142), so type is given | **unexercised by construction**; no classifier on the live path |
| D54 | question-first exception path for RC | **D157 (3)** defers it to the outage scenarios; **D226 (1)** puts network after the freeze | present only in `plan_sync`, which has no production caller |
| D72, D88, D131 | mu backlog price: zero, two fixed values, EWMA | **D131**: v1.3-fast ran at mu = 0 and was not run live; **D129** replaced EWMA mu with a scarcity price, itself superseded by the D162 model | yes; `mu_mode` is `None` in all 20 ladder headers |
| D98, D100, D104 | SH value per instant; information-parity hook; the LIVE2-coord rulings | folded into the v6 base rules and the harness; D104 item 5 records SH Episode objects inert (**P15**) | folded in; not separable switches |
| D108, D109, D119, D120, D121 | decision-preserving speed-ups: Option 0 memo, exact pruning, parallel evaluation; Option B built off | **D109** closes Option B ("switch default rollout, never enabled"); **D112** closes Option A; D121 (3) excludes approximate screening | Option B present and never enabled; approximate screening absent |
| D112 | Option A, deadline-order prefix admission | **D112** closes it on its offline study (loses 25/79/84 percent of SH DeltaJ) | yes, never implemented |
| D114, D117, D118, D128 | EDF work-conserving, C_inflight, llf and vllm-priority baselines | baseline-side; **D128** sets C_inflight 8 | these are baselines, not covex arms; off the chain by design |
| D122, D125, D126 | v1.1 honest deferral and A3 promotion; v1.2 two-timescale job plans; F5a/F5b/F5c | superseded by **D132** (rollout over the strongest baseline) and the v6 ladder | yes; the job-plan machinery is not on the ladder |
| D133 | robot capacity over FEASIBLE questions, p = 0.90 | **D147** moves the deadline to 3 s and D152 (1)/D155 (3) move the headline to correct-by-deadline; D178 (1) sets the target per device | the target lives in `deficit_feed.py:96`; the feasible-question column is a reporting cut |
| D134 (2), (3) | port the missed streaming baselines; fix b10 | **D213** stops fidelity work outside the paper baseline set | baseline-side |
| D137 (1) | default representation for an arm that chooses none | `interface.py:236-237`; our arms always choose | not a covex switch |
| D142, D143 (C), D144 (4) | hybrid-F and hybrid-F6/F6r freeze | **D154 (3)** makes `hybrid-F-lhreq-noc3` the base; F6 is not on the final ladder | `sw[c6]=False` on all five arms |
| D156a | EP-G budget true-up at completion from engine-reported cached_tokens | **ASSESSED AND DEFERRED, PROVISIONAL**, under the user's own escape clause, for three stated reasons (`Budget.spend` raises; mid-sweep comparability; it needs its own labelled cells) | deferred; the D174 (1) uncached-only charge is what runs |
| D157 (1), D183 | M2 second break; the `long_prefill_token_threshold` engine flag | **D183** closes the engine flag on evidence (it does nothing at either rung) | yes, not a candidate fix |
| D179 (1)-(3), D180, D181 (1), D182 | share admission, W_max, derived floors | **D224** (out of the paper), **D186** (failed check (b) at all four seeds), **D188 (1)** (floors parked) | yes, see 4.3 |
| D186 (closing note), D188 (2) | the `arms_v6state.py:236` `id(obs)` cache key | **D188 (2)** holds the fix off until the final rung-2 rerun; this ladder IS that rerun and sets it ON | fixed and ON, see 4.3 |
| D190 (3), D194 (1), D198 (1) | rung 4's BETTER-than-rung-3 gate at 1x | **D222 (2)** amends it: at 1x the bar is NO WORSE than rung 3; the better-than test moves to reduced memory | the gate, not a code switch |
| D195 (2) | the D177 currency flip lands atomically across `cf_objective` and `cf_planner` | done; `cf_objective.py:728-739` documents the conversion | built and live |
| D202, D204, D207, D192 (3) | episode early exit; cloud dashcam context lever | ruled out with measured evidence, see 4.5 | yes |
| D209 (2) | placeholder triage hits 6, 7, 8, 9, 14, 16, 17, 22, 26 | hit 22 CLOSED (4.3); hit 6 is D216 (2), still open (4.5); hits 14/7/9/8/16/17 are baseline-side under D213 | mixed; the covex-side ones are rows above |
| D213 (closing) | D211 host-warm pricing ships gated off, validated on the first final-ladder cells, on only if the bar is met | gated off, see 4.3 | conformant |
| D215, D219, D226 (1) | network: static 5G links, outages capped at 30 s | **D226 (1)**: network cells after the freeze; code behind switches defaulting OFF | absent, see 4.5 |
| D220 (2) | the FAIR oracle and the share-of-achievable-gain reporting | Orin, offline from committed traces | evaluation-side, no arm switch |
| D220 (3), D223 (1) | memory sweep levels | **D223 (1)**: 1x and 0.5x only, NO 0.25x for any arm; committed 0.25x cells kept for provenance, not reported | the 0.25x `covex-v6-base`/`-rules` cells exist and must not be reported. **Consequence for 4.5: protect-and-defer's only positive evidence (D198 (1): 23 characteristic decisions at 0.25x) sits at a level D223 (1) makes unreportable.** See 10.17 |
| D225 | this matrix | - | this file |

### 4.7 Two rows added after the first draft, both of them decision-versus-code mismatches

#### 4.7.1 THE RUNG-4 SERVICE PREDICTION IS COMPUTED FROM THE FAILED-GATE MODEL, IN THE WRONG UNITS

This is the largest single conformance break in this matrix and it is worth stating as a chain,
because every link is checkable with one `git show` at `c5e7bb49`.

1. Both rung-4 legs import the same cost module: `arms_v6cfr3.py:99` and `arms_v6cf.py:74` are both
   `import cf_cost as CC`.
2. `cf_cost.py:63` points at **`results/orchestration/live2/frozen_test/cost_model_gate.json`**, and
   `cf_cost.py:67` records that model's own status in the code:
   `GATE_STATUS = "FAILS (spec v5 section 12): decode over-predicts by 25 to 32 percent in every
   held-out class, and warm is confounded with arm, so the warm regime is unidentified out of arm
   (G10). D154 (2) cannot set MARGIN_CF until it passes."` `load_gate_model` attaches that string to
   the model it returns, at `:121`.
3. That model's queueing feature is `overlap_ft`, declared `overlap_ft: int` at `cf_cost.py:135` and
   consumed at **`cf_cost.py:156`** as `float(f["per_overlap"]) * max(int(overlap_ft), 0)`. So it is
   a **COUNT OF OVERLAPPING REQUESTS**, priced at `per_overlap = 0.038004811772727576` s per request
   (the `by_arm` split, which is the one `GATE_SPLIT` selects at `cf_cost.py:66`).
4. **D162's queueing term is a different quantity in a different file under a different key.**
   `d162_price.py:37` reads `cost_model_gate_d162.json`, and `:48` is
   `PER_QUEUE_S = 0.0001535807289338535`, sourced at `:49` as
   `"cost_model_gate_d162.json :: model.first_token (gate commit 68a2b47)"`. It multiplies
   `queue_uncached_ahead`, a **TOKEN COUNT** (`cost_model_gate_d162.py:187`).
5. **The unit gap is 0.038004811772727576 / 0.0001535807289338535 = 247.46x**, and it is a UNIT
   difference (seconds per request against seconds per uncached token), not a calibration
   disagreement. The two numbers are not comparable and neither is wrong in its own file.
6. **D168 is the row that says the D162 gate PASSES** (ratio_p50 1.052 overall, 1.070 warm,
   sensitivity 12 of 12, at `68a2b47`). So the model the rung-4 legs use is the one whose own string
   says it fails, and the model that passed is the one they do not use.

| D-row | decision | code at `c5e7bb49` | registers | status |
|---|---|---|---|---|
| D151 (6), D162, D168 | service and first-token time are predicted by the D162 model, which is the model that passed the gate | **CODE**: both rung-4 legs predict through `cf_cost.predict` off `cost_model_gate.json`, whose `GATE_STATUS` string says FAILS; the D162 model lives in a separate file read only by `d162_price.py` and `cost_model_gate_d162.py` | the FAILS string is **CODE at `c5e7bb49`** (`cf_cost.py:67`); the 247.46x is **ARITHMETIC** on two committed coefficients; that the legs reach it is **CODE** (`arms_v6cfr3.py:199`, `arms_v6cf.py` via `CC.predict`) | **CONFORMANCE BREAK. Not built-and-live, not ruled out.** Freeze-gate row, 10.16 |
| D222 (1) item 1 | pass the REAL queued-ahead work into the service prediction instead of the hard-coded zero | `arms_v6cfr3.py:198-199` `pred = CC.predict(cf.model, int(u_request), 0, 0, 0)` | CODE | **ORDERED, NOT APPLIED, AND THE ORDER IS AMBIGUOUS AS WRITTEN.** D222 (1) item 1 says "real queued-ahead work". `overlap_ft` wants a REQUEST COUNT; D162's `queue_uncached_ahead` is a TOKEN COUNT. Putting a token count into `overlap_ft` would overcharge by 247x; putting a request count in keeps the failed-gate model. **Both readings are defensible from the row's text, so this needs the user's ruling, not a fix.** 10.16 |

The hard zero at `arms_v6cfr3.py:199` has one accidental mercy worth recording so nobody "fixes" it
in the wrong direction: while `overlap_ft` is 0, the failed gate's queueing coefficient contributes
nothing, and the prediction reduces to `intercept + per_uncached_token x u_request`. The 247x unit
error is therefore **latent, not active**, in every committed rung-4 cell. It becomes active on the
first commit that honours D222 (1) item 1 without resolving the unit question.

#### 4.7.2 D227, the row that makes a failed scrape visible instead of silently zero

| D-row | decision | code at `c5e7bb49` | live evidence | status |
|---|---|---|---|---|
| D227 | E3 approved as part of E1: every `cell.json` carries a one-line `metrics_health` field (scrape count, failures, last-success time, metric names found), and a cell whose scrape failed or never ran is FLAGGED with its engine-metric quantities unusable | `metrics_health` is DEFINED at `asyncbackend.py:182`; at this sha its only callers are proof scripts (`d209_unit_proofs.py:97`, `d213_*`). No `cell.json` writer reaches it | **OBSERVED at `c5e7bb49`**: no committed `cell.json` carries `metrics_health`; the 4 rung-4 `metrics_snapshots.log` files hold exactly 5 distinct metric names and `vllm:kv_cache_usage_perc` is not among them (0 lines, rc=1) | **ORDERED 2026-11-24, BEING BUILT NOW by the E1 session. Dated, not settled.** This is the rule that converts 4.5's `gpu_kv_fraction` row from a silent zero into a flagged cell, so it is the right fix for 10.9 and the two rows should be read together |

D227 matters to this matrix beyond its own row. The `gpu_kv_fraction` failure in 10.9 is exactly the
shape D227 exists to catch: a quantity that reads 0.0 forever because the dict it is read from never
had the key, with nothing in the cell recording that the scrape never happened. **1,153 of 1,153
rung-4 protect-and-defer decisions were bounded by belief rather than by the engine metric, and no
committed artefact says so.** Once D227 lands, that condition is a flag on the cell instead of an
inference someone has to make from a counter's absence.

## 5. SPEC v6 MECHANISMS, AND WHERE THE SPEC DISAGREES WITH A LATER D-ROW

D225 (1) asks for a row per spec v6 mechanism as well as per D-row. The spec's mechanisms are
covered by section 4 wherever a D-row carries them. What follows is what the spec adds or contradicts.

**THE SINGLE LARGEST FINDING ABOUT THE SPEC, measured not impressionistic:** `policy_spec_v6.md`
**cites no D-row above D182.** `grep -o 'D2[0-9][0-9]'` returns nothing (rc=1, no match); the highest
cited row is D182. So **D183 to D226, 44 rows, are unapplied to the spec**, including every row that
defines the thing now being frozen. Corroborating literal counts on that one file:

| string | count | consequence |
|---|---|---|
| `c5attr` | 0 | the spec never records that rung 2 is c5attr (D184 (1), D186) |
| `final` as a ladder name | 0 | **the D208 (2) FINAL LADDER, the ladder with committed cells, is absent from the spec** |
| `DEVICE_ANSWERS` in section 7's status | 0 | D218 (1) / D221 unrecorded |
| `max-model-len` | 0 | D223 (2) unapplied |
| alert release re-check in section 5 | 0 | **D208 (2) explicitly ORDERS "Spec v6 section 5 is corrected: the alert release re-check enters at rung 3 in the final ladder". That correction was never made** |

The spec's own rule, worth quoting because it is the rule this matrix generalises (line 202): "a row
is IMPLEMENTED only where the quantity is READ by code that changes a decision; a definition with no
production caller is MISSING, however complete it looks."

| # | spec says (line) | contradicted by | kind |
|---|---|---|---|
| C1 | section 5 (75-84) lists the base rules and never mentions the alert release re-check | **D208 (2)** orders that correction | HIGH, documentation. The mechanism behind rung 3's headline is missing from the section defining where it enters |
| C2 | the ladder table (175-187) makes rungs 2/3/4 `covex-v6-state`/`-fair`/`covex-v6`, implemented by "none yet"/"none yet"/`v5-full` | **D208 (2)** defines the `-final` ladder that actually ran | HIGH, documentation. The spec's ladder is not the ladder that ran |
| C3 | line 258 presents share admission as "IMPLEMENTED AND REACHED", the rung-2 design | **D224**, **D186**, **D184 (1)** | HIGH, documentation |
| C4 | line 241 gives the device-discounted harm form | **D220 (1)** rejects that form; **D177** removes accuracy | HIGH, and the code implements neither exactly: see 10.6 |
| C5 | lines 189/244/250: memory sweep includes 0.25x, and protect-and-defer's only live evidence is at 0.25x | **D223 (1)**: no 0.25x cells for any arm, committed ones not reported | HIGH, see 10.17 |
| C6 | lines 232/262: `CONTEXT_LIMIT_TOKENS = 32768` hard-coded | **D223 (2)** | MEDIUM-HIGH, see 10.5 |
| C7 | line 119 lists three request candidates and line 246 calls request "enacted IMPLEMENTED" | **D218 (1)**: the third "was specified and never built" | HIGH, see 10.1 (and C16) |
| C8 | line 196 scopes out contexts beyond 32k citing D152 (3) | **D170** WITHDRAWS that sentence | MEDIUM |
| C9 | line 166 sweeps outages 10/30/60/120 s | **D226 (1)**, **D215** Tier 3 cap outages at 30 s | MEDIUM, post-freeze |
| C10 | line 172's baseline list includes R3-Streaming | **D213** keeps it out; **D205 (1)** supersedes its cells | MEDIUM |
| C11 | line 211 calls the cost model PARTIAL, refit pending | **D168**: the D162 gate PASSES (68a2b47) | MEDIUM, stale status |
| C12 | line 206 says targets MISSING and gain is the module default 1.0 | **D185 (2)** rules the normalised form, gain 2.0, per device | MEDIUM. The LIVE limb is correct (`deficit_feed.py:96`, `deficit_gain_d178.GAIN=2.0`); only the spec and the dead limb are stale |
| C13 | line 208 and `arm_names_v6.py` rung 3 both still say "+ value reader on" | **D177 (2)** removes it | MEDIUM, and the code comment is the worse half: `arm_names_v6.py` V6_LADDER rung 3 `adds` reads "deficit feed (observe() called by the coordinator) + value reader on" |
| C14 | lines 55 vs 212 give PATCH 2 as "mutate mode" and "still observe-mode" in one document | internally contradictory; **D211**, **D216 (3)** | MEDIUM-HIGH. Resolved by code: `BELIEF_CORRECTION` defaults `observe`, arm switch `live2_belief_apply=True` from rung 2, and the telemetry read IS live (4.3) |
| C15 | line 134 gives MARGIN_CF as 0.6582 and line 252 as 0.16456, both "set once" | **D177 (3)** rules 0.6582 | LOW-MEDIUM. Two numbers for one named constant in one document |
| C16 | line 247 calls the latest safe start IMPLEMENTED with two caveats | **D222 (1)** items 1, 2, 4; **D203 (3)**/**D206 (1)** retire Gate A | HIGH, see 4.5 and 10.2 |
| C17 | line 207 gives the guard ONE 2.0 s threshold while line 83 states the per-type rule | **D178 (3)** | MEDIUM-HIGH, see 10.7 |
| C18 | lines 249/236/250 record the `id(obs)` key and dry `gpu_kv_fraction` as open defects | **D188 (2)**, **D208 (2)**, **D216 (1)**, **D216 (2)** rule them | MEDIUM, stale status; rulings exist |
| C19 | lines 251/253/255 record episode rule, episode-end threshold and per-episode target as MISSING pending build | **D194 (3)**, **D202 (1)**, **D204**, **D207** | RESOLVES rather than contradicts: these are ruled out with evidence |
| C20 | line 240 records the lexicographic objective as MISSING, not built | **no later D-row removes it** | **HIGH, the cleanest freeze-gate blocker in the spec.** See 10.12 |

Spec mechanisms not built and with no ruling-out row, beyond C20: **reload from host** as an explicit
action (line 221, D150/M3: "no explicit reload action exists"); **counterfactual sync** (line 239,
`plan_sync` with no production caller); **keep-ready set** and **admit with protected victim** (line
245); **guard exit hysteresis** (line 218, D166 (3)). All are in section 10.

## 6. INHERITANCE CHECK PER RUNG (D225 (2), generalising D200 (4))

The rule: every mechanism of the rung below is shown live in the rung above, or the D-row removing it
is cited. Two halves, because the mechanical half can pass while the substantive half fails.

### 6.1 Mechanical half: switch monotonicity. PASSES.

Register CODE, by construction at sha `a4eaf9bc`. **No switch is ON at a lower rung and OFF or
absent at a higher one. 0 breaks.** Checked over the full resolved switch surface of all five arms
(58, 65, 75, 85, 95 switches respectively), after resolving the composition chain described in
section 2. The C1 to C6 switch set is identical at all five rungs:
`sw[c1]=True, sw[c2]=True, sw[c3]=False, sw[c4]=False, sw[c5]=True, sw[c6]=False` at rungs 0, 1, 2, 3
and 4 alike, which is the read-from-code inheritance proof for rung 0's whole mechanism set.

Counter families corroborate the entry rungs from the OBSERVED side: warming, chunking and guard
counters first appear at rung 1 and persist upward; `state_*`, `submitted_*`, `gain_*`, `c5_attr_*`
and `cf_planner_*` at rung 2; deficit feed and `release_infeasible*` at rung 3; `pd_*` and `rd_*` at
rung 4. `arm_stats` sizes grow 8, 12, 78, 81, 128 at s4.

### 6.2 Substantive half: is each inherited mechanism LIVE above its entry rung?

| inherited mechanism | entry rung | live at every higher rung? | evidence or break |
|---|---|---|---|
| C1, C3, C4, C6, b7, over-limit rule, workload, quality fit, value reader off | 0 | yes | identical switch values at all five rungs (6.1) |
| C2 and C5 | 0 | **CANNOT BE SHOWN AT RUNG 1 FROM CELLS** | `v5-rules-2` emits **zero** `c2_*` / `c5_*` keys in `arm_stats` or `counts` in all four cells, while rung 0 emits them (`c5_dash_held` 50,589 at s4) and rungs 2 to 4 emit them (57,938 at rung 2 s4). The switches are ON by delegation (register CODE). Counter absence cannot distinguish "not live" from "not reported", so this is an INSTRUMENTATION gap, not a demonstrated break. See 10.15 |
| warm-ahead, chunking, JIT, guard, slice | 1 | yes | `warm_ahead_*`, `chunk_*`, `jit_*`, `guard_by_lag` present at rungs 2, 3 and 4 |
| state planner, TOUCH, offload controls, state pricing, belief apply, c5attr, qcache fix | 2 | yes | `state_*`, `c5_attr_*` present at rungs 3 and 4; switches True at 3 and 4 |
| deficit feed, ordering consumer, planner limb, alert release re-check | 3 | yes | present and True at rung 4; `release_infeasible` 1746-2073 per cell |
| protect-and-defer, question deferral | 4 | n/a, top rung | `rd_question_defers` 29/37/29/25 |

### 6.3 Mechanisms that enter a rung and are NOT live anywhere, with the D-row

Each of these is the inheritance check's real output: a mechanism whose rung is defined and whose
live evidence is absent. All are in section 10.

| mechanism | rung | class (Rule 2) | removing D-row? |
|---|---|---|---|
| flexible split by w_d | 3 | **unexpressible** (consumer unreachable: `coordinator.py:1615` returns first) | D224 covers the gap |
| per-type host retention / offload | 2 | **unexercised** at 1x (`offloaded`=0 in 20 of 20; `over_cap`=0) | none; and no reduced-memory cell exists for rungs 2 to 4 |
| guard backlog leg | 1 | **unexercised** (present and zero in all 16 cells) | none |
| engine-metric KV bound | 4 | **ABSENT** (binds 0 of 1,153) | none; D216 (2) orders the fix |
| DEVICE_ANSWERS | 4 | not built | none; D218 (1)/D221 order it |
| counterfactual sync | 4 | no production caller | D226 (1) post-freeze |

## 7. SWITCH DIFF BETWEEN ADJACENT RUNGS (D225 (3))

Script: `experiments/orchestration/live2/d225_switch_diff.py`. Run it from a real checkout:

    python3 -I experiments/orchestration/live2/d225_switch_diff.py \
        --live2 experiments/orchestration/live2 \
        --design-log research/policy_design_log.md --json out.json

It constructs the five rung arms, resolves every switch through the composition chain, diffs the four
adjacent pairs, and joins each difference against its own `ATTRIBUTION` table. **An unattributed
difference is printed as a DEFECT and makes the exit status non-zero**, which is D225 (3) made
mechanical. It refuses to print a bare "unknown" sha: if `git rev-parse` fails it says so loudly,
because a row whose provenance is the word "unknown" is a row nobody can reproduce.

Result at `a4eaf9bcde60a0aeb5cd6a3431950ece8577b189`: **56 switch differences across 4 adjacent
pairs, 0 unattributed, exit 0.** The same result holds at `c5e7bb49`, and that is asserted from the
tree hash in section 0, not from a re-run: the `live2` tree object is the same `23233f43` at both, so
the script would be reading identical bytes. (A re-run was attempted and `git checkout` died with a
glibc double-free on a sparse-checkout pattern set; the tree-hash identity makes the re-run
unnecessary rather than merely unavailable.)

| pair | differences | the mechanism switches among them |
|---|---|---|
| rung0 -> rung1 | 10 | `warm_ahead`, `just_in_time`, `chunk_tokens` 2048, `slice_tokens` 1024, `guard`, `guard_lag_s` 2.0, `guard_backlog` 100 (+3 naming) |
| rung1 -> rung2 | 16 | `plan_state`, `live2_offload_controls`, `live2_touch_requests`, `live2_state_priced_costs`, `live2_belief_apply`, `live2_d162_pricing`, `live2_charge_mode`, `live2_qcache_key_fix`, `c5_attr_self_released` (+naming, + 2 configure-time fields) |
| rung2 -> rung3 | 17 | `live2_deficit_feed`, `_feed_on/_feed_gain/_feed_ordering/_feed_split`, `gain` 2.0, `live2_release_recheck`, `live2_release_recheck_types`, the planner-limb reader (+naming, +2 counters) |
| rung3 -> rung4 | 13 | `live2_cf_protect_defer`, `live2_cf_request_defer`, `_pd_w_source`, `_pd_bar_reading`, the two Step 4 controls and `MARGIN_CONTROL_SCALE` (+ configure-time `_pd_gpu_kv_tokens`) |

Three design points in the script a verifier should check rather than take on trust:

1. **It walks `arm -> _rules -> _base -> _feed -> _b7`**, not just the arm. Without that it reports
   twenty false inheritance breaks (section 2).
2. **It expands `sw`, a DICT of switches**, into `sw[c1]` and so on. A scalar-only walk skips the
   dict and reports rung 0 as having no switches at all, which is exactly backwards: C1 to C6 are
   rung 0's whole mechanism set.
3. **Internal twins are attributed through an explicit `INTERNAL_OF` indirection, not suppressed.**
   `_feed_gain` inherits `live2_deficit_feed`'s D-row and the row still prints, marked "via
   live2_deficit_feed", so a verifier can check that the two really are one switch. Likewise the
   declared readers (`release_recheck.arm_enables` and friends) inherit their public switch's row.
   Everything exempted as bookkeeping (`_pd_rows_key`, `_q_cache`, the counter lists) is named in
   `NOT_SWITCHES` with its read site, so the exemptions are checkable one by one.

**What 0 unattributed does and does not mean.** It means every switch that CHANGES between adjacent
rungs has a D-row. It does NOT mean every mechanism is live: a switch can be ON, attributed, and
reach no decision. That is section 6.3 and section 10, and the two must be read together.

## 8. MECHANISMS IN THE CODE WITH NO D-ROW (D225 (4))

Scope: the covex policy chain only, 32 files, excluding proof, probe, diagnosis and test scripts.
Method: for every behaviour-changing constant, switch and named decision branch, grep the
surrounding lines and the module docstring for a `D<number>` citation. D225 (4): the user rules on
each, or it is switched off.

| mechanism | file:line | what it does | value | live in | note |
|---|---|---|---|---|---|
| `DASH_DEADLINE_S` | `hybrid/hybrid_arm.py:59` | alert deadline inside the arm's feasibility test | 1.0 | rungs 0 to 4 | **uncited, not unruled**: it is exactly D154 (1)'s value. Fix is a citation |
| `GUARD_BACKLOG_DEFAULT` | `arms_v5rules2.py:83` | guard entry on queued deadline work | 100 | rungs 1 to 4 | **uncited, not unruled**: exactly D178 (3)'s value. Fix is a citation. The leg is also never exercised, 10.3 |
| `RECENT_TOKENS` | `hybrid/hybrid_arm.py:70` | tokens charged for the RECENT representation | 467 | rungs 0 to 4 | no D-row names the number. With C3 off the RECENT path is not taken, so it is inert on the ladder |
| `WARM_AHEAD_SLICE_TOKENS` | `engine_actions.py:96` | per-epoch MATERIALIZE slice for background warming | 1024 | rungs 1 to 4 | no D-row names 1024. **Not a contradiction with D160 (1)'s 2048**: 2048 is the chunk TRIGGER tail (`arms_v5rules2.py:66`, read `:249`), 1024 is the per-epoch slice. Two quantities at two layers |
| `WARM_AHEAD_TARGET` | `engine_actions.py:97` | nominal warm target, clamped to `est_tokens` by `_advance_build` | 10**9 | rungs 1 to 4 | effectively "no target"; worth a one-line ruling that it is meant to be inert |
| `BASE_DEFER_S` | `v5/cf_planner.py:141` | the base-policy surrogate's defer window inside the counterfactual | 0.5 | rung 4 | cites the committed `B7EDFFeasibility.__init__(defer_s=0.5)` rather than a D-row |
| `HARM_FORM_DEFAULT` | `cf_protect_defer.py:336` | names the harm form | label only | rung 4 | **declaration-only: there is NO branch on it anywhere** (grep returns the definition, the dict string and the describe block; rc=0). Must be recorded as one live form with no switch, not a switch with two states |

A citation trap worth recording: `WARM_AHEAD_SLICE_TOKENS` and `WARM_AHEAD_TARGET` sit one and two
lines below `W2_LAXITY_FRACTION = 0.3  # D143 ruling B`, so a 15-line citation probe reports "D143"
for them. That citation belongs to the neighbour. A proximity grep is not an attribution.

## 9. MISCITED D-ROWS (the code cites a row that does not say that)

A miscitation is not a wrong computation and survives every arithmetic check, so these are listed
separately from the no-D-row set. The first has propagated into two reports.

| code site | cites | what the cited row actually says | governing row | consequence |
|---|---|---|---|---|
| `cstate.py:138,:468,:486`, and `reports/policy_fidelity.md:52`, `reports/study_engine_actions.md:129` | "D133 Part A" for making `desired_tier` read and enacted | D133 is ROBOT CAPACITY OVER FEASIBLE QUESTIONS and says nothing about placement | **D134 (1)** | mechanism is LIVE and correctly ruled; the citation sends a verifier to an unrelated row, and it is now in two committed reports |
| `v5/cf_objective.py:220-221` `ON_TIME_TARGET = {robot 0.90, dashcam 0.90, single_shot 0.90}` | D133 | D133 sets the ROBOT target at 0.90 and sets no dashcam or single-shot target | **D178 (1)** (alert 25 percent per episode) | a robot ruling extended to all three types with no row authorising it. **INERT**: read only at `:250` in `DeviceDeficit.shortfall`, reachable only through `DeficitCounters`, which D206 (3) keeps labelled superseded with no live path. Matrix status: built and off by ruling D206 (3) |
| `v5/cf_objective.py:225` `DEFICIT_GAIN = 1.0`, "DECLARED, never swept" | - | contradicts D185 (2)'s normalised `1 + 2.0 x shortfall/target` | **D185 (2)** | same dead limb. The LIVE limb is correct: `deficit_feed.py:96` and `deficit_gain_d178.GAIN = 2.0` |
| `arms_v5rules2.py:81` `GUARD_LAG_S_DEFAULT = 2.0` | D160 | D160 (2) rules that the guard exists; the 2 s exit hold is not in it | **D166 (3)** / **D178 (3)** | minor: right family, wrong item |

## 10. THE FREEZE GATE (D225 (6)): rows NOT built-and-live and NOT ruled-out

**D225 (6): no freeze and no held-out seeds 1 to 3 until every row below is built-and-live or
ruled-out with evidence.** 16 rows, in five groups. Each says what would close it. None of them is a claim that a
posted number is wrong; where that was a possibility it was checked, and 10.17 records the two
checks.

### Group A: ORDERED BY A D-ROW AND NOT IN THE CODE (7 rows)

**10.1 DEVICE_ANSWERS, rung 4's third request candidate. D218 (1), D221.**
`cf_request_defer.py:177` `ACTIONS = ("BASE", "DEFER_TO_LATEST_SAFE_START")` has two actions.
`cf_protect_defer.py:530` says in its own gate string that DEVICE_ANSWERS "is not built here". The
only `ra.decision` writes in the tree are `"DEFER"` at `arms_v6cf.py:494` and `arms_v6cfr3.py:297`;
the coordinator channel sits unwritten at `coordinator.py:865`. The candidate exists only in the v5
planner limb (`v5/cf_planner.py:167,:344,:549`), which the final ladder does not reach: `plan_request`
has exactly one non-proof caller, `arms_v5full.py:223`. `d218_prereg.json`, which D221 names as the
pre-registration record, is not present in `experiments/orchestration/live2/`.
**Closes when:** built per D221's rule, with the D218 (1) proofs. The four committed `covex-v6-final`
cells are already SUPERSEDED by D221, so no posted number depends on this.

**10.2 D222 (1) item 1, the hard-coded zero queued-ahead. MOOT FOR RUNG 4 under D232 (2), see 10.19.**
`arms_v6cfr3.py:198-199` `pred = CC.predict(cf.model, int(u_request), 0, 0, 0)`. Be precise about
which zero: the first (`cached_tokens`) is correct by construction because `u_request` is already the
uncached count (computed `:173-192`); the defect is `overlap_ft` and `overlap_decode` hard zero, the
queue term. **Closes when:** the real queued-ahead work is passed. This is the quantity
`reports/study_rung4_s5_failure.md` attributes 12 of 14 s5 losses to.

**10.3 D222 (1) item 2, debit one decision period from the deferral. MOOT FOR RUNG 4 under D232 (2), see 10.19.**
`v5/cf_cost.py:281` `deferral_s = max(lss - now_s, 0.0)`; `cf_request_defer.py:175`
`MIN_DEFERRAL_S = PD.DECISION_PERIOD_S` is used only as a FLOOR at `:267`. A floor that rejects
sub-period deferrals is not a debit that shortens every deferral. Checked inside `LatestSafeStart`
too, so this is not a false negative from reading one layer.

**10.4 D222 (1) item 5, the committed `rd_decisions` log.**
Accumulated in memory capped at 4,000 (`arms_v6cfr3.py:234-235`), dumped by `cfr3_one_cell.py:78`.
`find -name '*rd_decision*'` over all 334 cell dirs returns **0**.

**10.5 D223 (2), read max-model-len instead of the hard-coded 32,768.**
All four sites still literal: `hybrid/hybrid_arm.py:157`, `arms_v6cf.py:86`, `arms_v6fair.py:90`,
`d170_overlimit.py:33`. `grep -rn 'max_model_len|max-model-len'` over live2 finds only report prose
and `confirm_engine_actions_32b.py`'s own hard-coded constant: **nothing on the live path reads the
server's limit** (rc=0, full output inspected, not truncated). D223 (2) requires this "before any
0.5x policy cell", and D223 (1) makes 0.5x the paper's only pressure level. See 10.10 for the harm
check.

**10.6 D220 (1), harm weighted by the accuracy gain. AND IT IS A TENSION FOR THE USER, NOT A BUG.**
`v5/cf_objective.py:712` computes `w_o x (p_before - p_after)` and its docstring `:728-739` states
the accuracy factor was deliberately removed under D177 (1). D220 (1) rules harm = P(would have been
served on time) x (cloud accuracy - device accuracy for its type) and says the gain weighting is to
be added if absent. It is absent. **The two rows pull opposite ways on purpose:** D177 removes
accuracy because WITHIN a type the gap is a positive constant that cannot change a decision; D220 (1)
reinstates a gain because harm is summed ACROSS types, where the gap is not constant. Which is right
is the user's call (D225's closing sentence). **Closes when:** the user rules, and the code matches.

**10.7 D178 (3), per-type guard thresholds.** The code has ONE `guard_lag_s = 2.0`
(`arms_v5rules2.py:81`, read `:196`) for all three types. D178 (3) rules a per-type threshold at 80
percent of each type's deadline: alert 0.8 s, assistance 1.6 s, recall 2.4 s. Spec v6 section 5 line
83 states the per-type rule as if it holds, so a reader of the spec alone gets a false picture
(contradiction C17). **Also in this row:** D166 (3) guard EXIT hysteresis (both signals below 0.5x
entry for 2 s) is not built; spec line 218 records it as such.

### Group B: BUILT, SWITCH ON, BUT NO LIVE EVIDENCE IT REACHES A DECISION (4 rows)

Each carries its Rule 2 class. These are the rows the consistency protocol cannot catch, because a
quantity that is correctly and consistently zero passes every consistency check.

**10.8 Per-type host retention / offload, rung 2's headline mechanism. UNEXERCISED at 1x.**
Switch ON at rungs 2 to 4 (`live2_offload_controls`), rule and enactment path both present
(`offload_policy.py:30-52,:72` -> `coordinator.py:1529`), and the path demonstrably works:
`kept_warm` is 173 to 4,300 across the ladder cells. But **`offloaded` = 0 in 20 of 20 ladder
cells**, `over_cap` = 0, and the KV peak is 40,178 to 52,829 of 62,944, so the eviction and offload
branch is never REACHED. The channel is not broken: `attentionstore-prefetch` at kv0.5 shows
`offloaded` 35 and 33, `evicted` 6, host peak 449k to 647k. **And no reduced-memory cell exists for
rungs 2, 3 or 4 anywhere in the tree** (only `covex-v6-base` and `covex-v6-rules` have kv0.25, kv0.5
and kv0.5r). So rung 2's headline mechanism currently has no cell in which it could fire.
**Do not pool the zeros:** rung 0's instrument is wholly inert because it has no state layer, which
is correct by the ladder; rung 1 tracks residency and evicted once at s7; rungs 2 to 4 are
unexercised. Three different causes behind one shared number.
**Closes when:** a 0.5x cell for rungs 2 to 4 (which needs 10.5 first), or a D-row recording that
offload is unexercised at the reported memory levels.

**10.9 Engine-metric KV bound. ABSENT. D216 (2), D209 (2) hit 6.**
`scrape_metrics` is defined at `asyncbackend.py:175` with **zero callers**; `metrics()` `:190-210`
returns no `vllm:` key and does not call it; `METRICS_SCRAPE_DEFAULT = False` at `:161` is read only
inside the two uncalled methods; nothing in production sets `metrics_scrape`. So `cstate.py:697`
reads `vllm:gpu_cache_usage_perc` from a dict that never carries a `vllm:` key, and
`cloud.gpu_kv_fraction` is 0.0 everywhere. Decision reads are `arms_v6cf.py:319` and
`engine_actions.py:288`. OBSERVED consequence: `pd_kv_bound_by_engine_metric` is **absent in all
four rung-4 cells** while `pd_kv_bound_by_belief` EQUALS `pd_decisions` at every seed (302/302,
299/299, 293/293, 259/259), so the belief determines the bound on **1,153 of 1,153 decisions**.
A nuance that sharpens rather than softens this: a scrape DOES exist in the cells.
`metrics_snapshots.log` has 118 lines at about 10 s cadence with real `vllm:` keys, but the complete
set of distinct names is exactly five (`request_success_total`, `mm_cache_queries_total`,
`mm_cache_hits_total`, `prefix_cache_hits_total`, `prefix_cache_queries_total`).
`vllm:kv_cache_usage_perc`, the metric D216 (2) names, has **0 lines** in all four (rc=1, no match).
So the scrape exists, the needed key does not, and it reaches no decision.
**Another session is wiring this now** (D216 (2) / D222 (1) item g); this is the state at
`a4eaf9bc`. The counter-variation check passes the other way, so this zero is specific to the engine
channel and not a dead instrument: `pd_free_kv_min` is 14,993 / 16,017 / 21,258 / 10,115 against a
max of 62,944.

**10.10 Guard backlog leg. UNEXERCISED. D178 (3).**
`guard_by_backlog` is **present and zero in all 16 cells where it appears**, while `guard_by_lag`
carries 100 percent of activations (rung 1: 4,027 / 3,675 / 3,508 / 4,565; rung 4: 80 / 32 / 117 /
22). It is the only counter present and zero everywhere. **Closes when:** a condition reaches it, or
a D-row records the leg as unexercised at this fleet size.

**10.11 Flexible split by w_d. UNEXPRESSIBLE. D185 (3)(b), gap recorded by D224.**
`_feed_split` is True at rungs 3 and 4 and `live2_share_weights()` is wired, but
`coordinator.py:1615` returns True before the `SA.allowed(weights_by_type=)` call at `:1630`, because
`_share_admission` is False on all five arms. The weight is computed and never consumed. D224 records
the gap ("at rung 3 deficit weights set ORDER only, not capacity per type"), and
`arms_final_ladder.py:48` documents it. **Not a defect**, but the ON switch is misleading to a reader
and should either be set False on these arms or carry the class at its definition.

### Group C: SPECIFIED, NOT BUILT, NO D-ROW REMOVING IT (3 rows)

**10.12 The lexicographic objective. D165 (A).** Spec v6 line 240 marks it MISSING, and
`arm_names_v6.py` V6_LADDER rung 3 carries `"missing": ["the D165 lexicographic objective is not
built"]` in the code itself. No later row removes it; D177 reframes the currency but line 24 of the
spec still asserts the structure. This is the cleanest gate blocker in the spec.
**Closes when:** built, or a D-row rules it out.

**10.13 The two unbuilt compounds. D165 (D).** KEEP-READY SET and ADMIT WITH PROTECTED VICTIM, spec
line 245: "not built; addendum 9 item B2 covered protect-and-defer only". Spec line 130 says a
rollout represents "single deviations against the base continuation, the named compounds and greedy
sequential composition", and two of the three named compounds do not exist.

**10.14 Reload from host as an explicit action, and counterfactual sync.** Spec line 221: "no
explicit reload action exists" (D150, M3), and D211's "native but unobserved" describes the engine,
not the missing action. Spec line 239: `plan_sync` is defined at `v5/cf_planner.py:619` and its only
caller is `v5/cf_proofs.py`. D226 (1) puts network cells after the freeze with the code behind
switches defaulting OFF, which is close to a ruling for sync but does not say the sync counterfactual
is unneeded for the freeze. **Closes when:** the user rules whether D226 (1) covers it.

### 10.15 Group D: BUILT AND ON BY DELEGATION, BUT NOT SHOWABLE LIVE (1 row)

**C2 and C5 at rung 1. D179 (5).** D179 (5) rules that `covex-v6-base` and `covex-v6-rules` "keep C5
as committed". Register CODE agrees: `sw[c2]` and `sw[c5]` are True at rung 1, resolved through the
composition chain to the inner `HybridArm`. But register OBSERVED cannot confirm it: **`v5-rules-2`
emits zero `c2_*` and `c5_*` keys in `arm_stats` or `counts` in all four of its cells**, while rung 0
emits them (`c5_dash_held` 50,589 at s4) and rungs 2 to 4 emit them (57,938 at rung 2 s4).

This is stated as an instrumentation gap and NOT classified, deliberately. Because `arm_stats` is
sparse (section 1), counter absence cannot distinguish "the mechanism did not fire" from "the
mechanism fired and the counter is not reported at this rung". Those have different remedies and only
one of them is a finding about the policy, so naming a Rule 2 class here would be exactly the blanket
classification section 4.5 warns against.
**Closes when:** someone reads the rung-1 counter-merge path (`coordinator._arm_stats` merges every
Counter in `_rules` / `_base` / `_scorer`, per spec line 234) and says which of the two it is. Cheap:
it is one code read, not a cell.

### Group E: BUILT, ON, REACHED, BUT PRICED FROM A MODEL THAT FAILS ITS OWN GATE (1 row)

**10.16 The rung-4 service prediction is computed from the failed-gate model, in units 247x away
from the ruled ones. D151 (6), D162, D168, D222 (1) item 1.**
Full chain with every link checkable in 4.7.1. In short: both rung-4 legs `import cf_cost as CC`
(`arms_v6cfr3.py:99`, `arms_v6cf.py:74`); `cf_cost.py:63` reads `cost_model_gate.json`;
`cf_cost.py:67` carries that model's own `GATE_STATUS = "FAILS (spec v5 section 12) ..."`; its
queueing feature `overlap_ft` is a COUNT OF REQUESTS at `per_overlap = 0.038004811772727576` s each
(`cf_cost.py:135,:156`), whereas D162's ruled term is `PER_QUEUE_S = 0.0001535807289338535` s per
UNCACHED TOKEN in a different file under a different key (`d162_price.py:37,:48`). The ratio is
**247.46x** and it is a unit difference, not a calibration disagreement. D168 is the row recording
that the D162 gate PASSES.

This is a different failure from the rest of this section, which is why it gets its own group: the
switch is ON, the gate is reached, and the counters fire (`rd_question_defers` 29/37/29/25), so every
check in groups A to D passes for it. What is wrong is the **register of the number being predicted**,
and that survives every arithmetic and consistency check because each coefficient is correct in its
own file.
**One accidental mercy, recorded so nobody fixes it in the wrong direction:** while `overlap_ft` is
the hard-coded `0` of 10.2, the failed gate's queueing coefficient contributes nothing and the
prediction reduces to `intercept + per_uncached_token x u_request`. **The 247x error is LATENT, not
active, in every committed rung-4 cell.** It becomes active on the first commit that honours
D222 (1) item 1 without first resolving which unit `overlap_ft` should receive.
**Closes when:** the user rules (a) whether the rung-4 legs should predict from
`cost_model_gate_d162.json` instead, and (b) which quantity D222 (1) item 1's "real queued-ahead
work" denotes, a request count or an uncached-token count. Both readings are defensible from the
row's text, so this is a ruling and not a fix.

### 10.17 Two checks run specifically to see whether a POSTED result is affected. Both clear.

**D223 (2) against the existing 0.5x cells.** Committed `kv0.5r` cells exist for `covex-v6-base` and
`covex-v6-rules`, where the server's max prompt is 31,472 while the arms test against 32,768: a
1,296-token window in which an arm calls feasible a prompt the server will reject. **It did not bite
any posted result.** Every covex 0.5x cell has `n_errors = 0`; only seeds 4 and 5 exist at 0.5x; and
D170 records seeds 4 to 6 staying below 27k while the 52,861-token seed-7 session exceeds both limits
and is already caught by the 32,768 rule. So 10.5 is a genuine open gap blocking future 0.5x policy
cells, not a corrupted number.

**Protect-and-defer's evidence against D223 (1).** D198 (1) reports protect-and-defer firing under
memory pressure with 23 characteristic decisions at 0.25x (5 rebuild defers, 2 chunks, 16 question
defers), and spec line 250 records that as its live evidence. **D223 (1) rules that no 0.25x cell is
reported for any arm.** So the compound's only positive evidence sits at a level the paper cannot
cite, while at 1x it is unexpressible at s4 and s7 and unexercised at s5 and s6 (4.5). This does not
corrupt a posted number either, because D222 (2) already moved rung 4's better-than-rung-3 test to
reduced memory and set the 1x bar to no-worse. It does mean **the evidence that protect-and-defer
does anything is currently unreportable**, and that belongs in front of the user before the freeze.

### 10.18 Rows this matrix explicitly certifies as CLOSED, against the standing notes

Four mechanisms carried in the project's working notes as write-only or absent are FIXED at this sha.
Recorded here so nobody re-reports them, and because a stale hazard note costs the same time as a
stale result:

| claim in the standing notes | state at `a4eaf9bc` |
|---|---|
| `desired_tier` has two writes and NO read | **REFUTED.** Three reads change a decision: `cstate.py:527`, `:530` (live, `placement_enacted=True`) and `:562` (inert, `kv_capacity_enforced=False`). D134 (1) satisfied; miscited in code as "D133 Part A" |
| `EpisodicStream.delivered_scores` has four writers of a literal 0.0 | **REFUTED.** `coordinator.py:695` writes the committed per-instant device score; `:691` marks the channel unusable with D200 (3) fail-loud; `:1974` is the cloud upgrade writer. Of D205's seven readers, none reads values directly |
| `telemetry_cached_tokens` is a dead read (D150) | **FIXED.** Written `engine_actions.py:365`, read at `coordinator.py:788`, `:1337` and `arms_v6cfr3.py:173` |
| `TOUCH_PRICE_MODE` is never assigned (D209 hit 22) | **FIXED.** `touch_policy.py:126`, validated `:179-181`, branched `:182,:184`. D216 adds that the fix moves neither rung 3 nor rung 4 |

And one correction to the briefed path rather than the claim: `_caps` is written at **`live2/arms.py:82`**,
not `baselines/arms.py` (which does not exist, rc=2, an error and not a no-match). It has exactly one
read in the tree, `arms_published.py:209`, where mooncake sizes warm slots to the pool. So it is
write-only WITHIN the covex chain and read by exactly one baseline.

### 10.19 QUESTION DEFERRAL IS REMOVED FROM RUNG 4. D232 (2), 2026-11-24. Rule 2: FIRED AND DID NOT HELP

This is the one row in this section that closes by **removal of the mechanism**, not by building it or
by ruling it unexercised. D232 (2) (`research/policy_design_log.md`, read at origin `1a092abd`) rules
that question deferral is removed from rung 4, which becomes rung 3 plus protect-and-defer plus
DEVICE_ANSWERS plus the deficit-fed state planner, built as `covex-v6-final-nqd`. D232 (3) adds that
the pass-1 1x cell is not rerun after the E1 fix because it carries the removed leg.

**The evidence, with the cell named for every number** (the hazard being a number that is right about a
cell nobody meant):

| quantity | value | cell directory / file |
|---|---|---|
| live firings, 1x | `rd_question_defers` = 22 | `covex-v6-final_n16_s4_1200s_h27_3t_L3_epg_rq30_rerun` |
| live firings, 0.5x | `rd_question_defers` = 32, all 32 `rd_defer_would_miss_at_measured_worst_bias` | `covex-v6-final_n16_s4_1200s_h27_3t_kv0.5r_L3_epg_rq30_ms` |
| total | about 54 firings, **0 rescues** | the two cells above |
| 1x pairing | 22 deferrals -> **0 rescues, 1 on-time loss, 21 no change**, keyed on `(device_id, opportunity_id)`, 22 of 22 one-to-one with every defer row consumed exactly once | `results/orchestration/live2/d222_pass1/d222_1x_s4_verdict.json`, committed `b0767b46` |
| the loss | `robo006 / opp0003132`: a **1.9455 s** deferral on a question with **0.95 s** of slack, latency 2.052 s in rung 3 against **3.1737 s** in rung 4 on a 3.0 s deadline | same verdict file |
| the stratum | on the **227** alert instants inside the deferral windows, rung 4 alert on-time **33.9 percent** against rung 3's **45.8**, **-11.9 pp**, against **-0.9 pp** outside, mixing weight **1.93 percent** | same verdict file |
| 0.5x robot on-time | **110 of 132** cloud answers standing by deadline (D232's own text says "about 111 / 132") against rung 3's **122** | `..._kv0.5r_..._ms/cell.json` `score.score.robot_value.n_cloud_standing`; rung 3's 122 from D232 |
| 1x alert attainment | 0.609181 against same-code rung 3's 0.619234 on an identical 712-episode key universe, FAIL | the verdict file, deliverable 1 |

**The stratum's limitation, carried and not dropped.** The 227 instants are selected by rung 4's OWN
deferral windows, and the gate only fires when an alert episode is active, so the stratum is selected
on alert congestion. The cross-arm comparison is on the SAME instants with an identical key universe,
so **-11.9 pp is a real difference on those instants and is NOT a causal estimate** of deferring:
rung 3 has no deferrals and so no comparable window set of its own.

**The 0.5x comparator is PROVISIONAL.** Rung 3's
`covex-v6-fair-final_n16_s4_1200s_h27_3t_kv0.5r_L3_epg_rq30` carries
`score.ok = false`, `ScoringRefused` under the D226 guard (1 delivered cloud answer with a request id
absent from the 10,174-row request log, `r10175`), so it has no scored rows; the Orin is rescoring it
outcome-keyed. The **122** is therefore a provisional bar and must not be read as settled. Likewise
the robot denominator moves between seeds (132 at 1x s4 against 127 / 121 / 105 at kv0.5r s5 / s6 /
s7), so bare fractions are not comparable across seeds.

**THE THING THAT WOULD HAVE HIDDEN THIS, recorded because a reader of the headline reaches the
opposite conclusion.** The 1x headline is robot on-time **127 of 132 against rung 3's 126**, a net
**+1**. That +1 is **+2** from `robo006 / opp0003111` and `robo006 / opp0009518`, **both of which were
never deferred**, **minus 1** from the single deferred question that moved, which moved the wrong way;
129 of 132 opportunities did not flip. Scored on the deferred set alone the leg is 0 rescues against 1
loss. **"Robot on-time did not fall overall" is true and is not evidence that the leg helped.** The
second correctness loss in the pairing (`robo002 / opp0008560`) was on time in BOTH arms and is a
decode difference (cloud letter D against B, gold B), so it is not charged to the deferral.

**Rule 2 class: FIRED AND DID NOT HELP.** Not `unexercised`: it fired about 54 times live. Not
`unexpressible`: the gate had its channel, enacted at `arms_v6cfr3.py:297`, and all 22 deferrals at 1x
were paired to a scored question with none unpaired. Not `cancelled by geometry`: the deferral changes
one arm's latencies and does not cancel between the compared branches. Not `unscorable`: the objective
is on-time cloud answers and the leg moved one of them, plus 11.9 pp on its own stratum. **This is the
only inconclusive class that is evidence about the policy** (CLAUDE.md Rule 2), and by that same rule
it is **NOT a settled negative**, because the **Step 4 control has NOT been run** on either cell: no
run disables the leg and shows the result collapse. `reports/study_rung4_s5_failure.md` reports a
negative control that changes the result (121 against 107) on the **s5** cells, which is a different
pair and does not discharge Step 4 for these two. Record it as ruled out by decision on the evidence
above, not as a measured settled negative.

**What the removal does to this section.** 10.2 and 10.3 were BUILD items for a mechanism that no
longer exists in the arm, and both become **MOOT for rung 4**: 10.2's hard-coded `overlap_ft` /
`overlap_decode` zero has its only read in `arms_v6cfr3.py:198-199`, the removed leg's latest-safe-start
prediction, and 10.3's missing one-period debit has nothing left to debit. Say it plainly: the
verification's recommendation to **build** 10.2 is overtaken for rung 4 by the removal of its only
consumer, and neither row can close by being built now. They remain real code defects if the leg is
ever re-admitted, which is why they are marked MOOT rather than deleted. 10.4 (the `rd_decisions` log)
is also implicated and is deliberately NOT closed here: no future rung-4 cell will emit one, but the
log is the audit trail for the two cells this removal rests on. 10.16 survives the removal with half
its surface gone: its 247x unit error applies to both rung-4 legs, and protect-and-defer still prices
through `cf_cost.predict` at `arms_v6cf.py`; the accidental mercy recorded there (the 247x is LATENT
because `overlap_ft` is the hard zero of 10.2) is unchanged. The freeze-gate counts stated in section
10 and in the verification's section 10 are stale by this row and are not rewritten here.

**Agreement with the independent verification** (`research/conformance_matrix_verification.md`,
committed `b7970806`). This row touches three rows that verification examined, and in no case does it
contradict it. `rd_question_defers` 29 / 37 / 29 / 25 is CONFIRMED there as exact, and that number is
the reason the leg satisfied the D225 port rule; the removal does not dispute the count, it disputes
the count's value to the arm. 10.2 is CONFIRMED there, with the added note that D228 (1) removed its
ambiguity and made it an ordinary build item; that recommendation is what the removal overtakes. 10.3
is CONFIRMED there as a floor and not a debit, unchanged by this row and now moot. The two documents
should be read together on these three rows.

## 11. WHAT THIS MATRIX DOES NOT COVER, SAID HERE RATHER THAN DISCOVERED LATER

- **The baselines.** D225 (1) scopes the matrix to policy-relevant D-rows and spec v6 mechanisms.
  Baseline fidelity is D209 (2), D213 and D217's business.
- **`v5/cf_objective.py` and `v5/cf_planner.py` internal constants** (17 and 20 module constants).
  Only what the five rung arms reach through `_cf_engine` and `wire_planner` is enumerated. That limb
  is where the DEVICE_ANSWERS string lives and is the largest unexamined surface.
- **`engine_actions.py`'s other 11 module constants**, beyond `WARM_AHEAD_SLICE_TOKENS` and
  `WARM_AHEAD_TARGET`.
- **C5's AIMD internals** (trip 0.8 s, halve per trip, +1 per 5 s): runtime state on the inner
  `HybridArm`, not switches, so not given rows.
- **Module-global constants have no per-arm state.** `TOUCH_PRICE_MODE`, `CHARGE_MODE`,
  `W_MAX_TOKENS` and the share floors are process-global, so "state in each rung arm" is not well
  defined for them and five identical cells were not invented. `arms_v6state.py:166-178` records that
  checking these MODE literals instead of the arm attribute that actually gates the charge once cost
  a cell; read it before treating them as the switch.
- **No final rung has a committed decision log.** Across all 334 cell dirs: `decision.jsonl` in 39,
  `request.jsonl` in 16, `outcomes.jsonl` in 9, `coordinator_result.json` in 286; and **zero decision
  logs for `covex-v6-state-final`, `covex-v6-fair-final` or `covex-v6-final`**. This is D174 (3)
  working as ruled (oversized logs off git), but it means the live-evidence column for rungs 2 to 4
  is satisfiable only from `arm_stats`. Any row whose only observable is a decision-log row has no
  in-repo reproducible evidence, which is itself a freeze-gate consideration.
- **30 of 286 cells are stubs** carrying only five wire-level keys with no `arm`, `arm_stats` or
  `counts` (key genuinely absent; the parent key list was printed to confirm). All 20 ladder cells are
  complete. Every stub is a baseline, and they include **both 1x `L3_epg_rq30` s4 and s5 cells of
  `b7-edf-feasibility`**, which is in the D213 paper set and is rung 0's feasibility source. Evidence
  about those arms must come from `outcomes.jsonl.gz`.
- **Verification is a separate session's job** (D225 (5)). This file was written by a session that did
  not write the policy code; it has not been independently verified.
