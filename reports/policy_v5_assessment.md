# Policy v5: full assessment

**A6000 (session D), 2026-11-20, pre-21:00. Facts with sources. No code changed for this
assessment beyond the D154 items.** Origin at the time of writing: `255c532`.

Status vocabulary, used strictly: **designed** (a D-row or spec section exists, no code) /
**built** (code exists on origin) / **unit-tested** / **dry-proved** (Step 2b or equivalent on a dry
cell) / **live-validated** (measured on the deployment stack, vLLM 0.31.0 on the H100).

**Headline: of the 27 elements in section A, 1 is dry-proved, 4 are built, 22 are designed only, and
0 are live-validated.** The two largest subsystems, the counterfactual engine and the engine
actions, have no code on origin at all.

---

## A. The policy, element by element

### A.1 Inputs

| element | what I believe it does | D-row(s) | file:line | status | proof artefact | difference from the D-row |
|---|---|---|---|---|---|---|
| deficit counters | per-device counters that weight the objective so a device repeatedly missed is favoured | D151 (4), spec 7.7 | `arms_policy.py:276` (spec 3.3 counters, **DEFAULT OFF** per D122 v1.1 fix B1) | built, not wired to v5 | none | **v5 has no deficit-weighted objective in code.** The existing counters are a v1 artefact behind a default-off switch, and they steer on ON-TIME while the D152 headline is CORRECTNESS (spec gap G14) |
| profiles / cost model | predicts first-token and decode time from uncached tokens and overlap, so the planner can test feasibility | D151 (6) | `cost_model_gate.py` | built, **FAILS its own gate** | `results/orchestration/live2/frozen_test/cost_model_gate.json` | decode over-predicts 25 to 32 percent held out; warm is confounded with arm, so the warm coefficient is fitted on edf and llf alone and applied to arms that never go warm |
| residency belief | per-session distribution over GPU / host / cold that the policy reads as readiness | D150 | `cstate.py:95` (declaration), `:111` (`believed_tier`), `:168-169` (promotion on complete build), `coordinator.py:429`, `:754` | built | 18,738 residency rows over 45 cells | **belief is only ever `cold` (14,472) or `gpu` (1,442), NEVER `host`**, so `believed_tier()=="host"` and its three consumers (`cstate.py:323`, `:331`, `:352`) are unreached. Recorded PROVISIONAL per the user's ruling |
| engine telemetry into the belief | per-request `cached_tokens` corrects the belief | D150 | extracted `backend.py:143`, logged `coordinator.py:931`, call site `coordinator.py:756` | built but **log-only; the read into the belief does not exist** | residency rows: positive in **0 of 18,738** | the field is written on the history-build path ONLY, so it never observes the dashcam traffic where reuse happens. Wiring it will not by itself make the belief track residency |
| link / outage state | per-device link quality driving sync decisions | D150 SYNC | not located in live2 | designed | none | no implementation found |

### A.2 Base rules

**v5 base policy = `hybrid-F-lhreq-noc3` (C3 off), per D152 (2) and D154 (3).**

| element | what I believe it does | D-row(s) | file:line | status | proof artefact | difference |
|---|---|---|---|---|---|---|
| C1 ordering | orders released work by a value index | D143 | `hybrid/hybrid_arm.py:381` | built, **decision-inert** | `policy_f_proofs.json` | the value and quality tables are read in exactly one place and a Step 4 control moves ZERO decisions of 16,361 under a flat table, a 100x skew and a 10,000x inversion. Classified CANCELLED BY GEOMETRY |
| C2 at-risk | flags an item at risk when slack falls below `k_r = 0.3 x` its own deadline | D143 | `hybrid_arm.py:302`, `:316`, `:320` | built, dry-proved | `policy_f_proofs.json` | the SS at-risk flag is **constant at never**, 0 of 356 to 717 SS requests per cell (D143 ruling B's 0.6 s against a 2 s deadline) |
| C3 RECENT fallback | **OFF in v5.** Previously degraded to RECENT on infeasibility | D152 (2), D154 (3) | `hybrid_arm.py:341`, `:345` | built, **off by decision** | `value_reader_proofs.json` | removing it is exactly what the value reader arrives at independently (identical digest `5d3469549fead8ac`) |
| C5 | dashcam throttle floor | D143 | `hybrid_arm.py:386` | built | `policy_f_proofs.json` | none found |
| C6 cross-tier escalation | mirrors the policy core each period for an escalation path | D143 | `hybrid_arm.py:268`, `:310` | built, dry-proved | `policy_f_proofs.json` | was DEAD in every `-lhreq` cell until D143 ruling A; now fires 254 times and moves 3 decisions. Two PROVISIONAL substitutions both understate the gain |
| feasibility | predicts whether a representation can arrive before the deadline | D151 (3) | `hybrid_arm.py` (feasibility branch), `data_sources.py:43` | built | `deadline_sweep.json` | **`ROBOT_DEADLINE_S = 5.0` is still the default** (`data_sources.py:43`, `run_live2_real.py:92`) while D147 sets 3 s. A cell run without `--robot-deadline-s 3` silently uses 5 s |
| episode continuity | keeps an episode's context across turns rather than rebuilding | D148, D149 (3) | **not implemented** | designed | none | no code |

### A.3 Value readers

| element | what I believe it does | D-row(s) | file:line | status | proof artefact | difference |
|---|---|---|---|---|---|---|
| representation by value | sends a representation only if `P(on time) x accuracy` beats the device's own answer | D149, D152 (2) | `hybrid/value_reader.py` (`ValueTable`, `choose`), wired `hybrid_arm.py` behind `c3_value_reader`, **DEFAULT OFF** | **dry-proved** | `results/orchestration/live2/frozen_test/value_reader_proofs.json` | **D149 (4)'s value-inversion acceptance test DOES NOT DISCRIMINATE in C3's slot**: flat and inverted tables leave the digest unchanged, because that slot only ever offers RECENT. Recorded as a FAILED TEST, classified UNEXERCISED. It discriminates only once the reader sits at ADMISSION |
| tier by value | chooses GPU / host / cold by value | D149 | `v5/value_readers.py` | built (offline), not wired | `v5/value_readers_checks.json` | not reachable from any arm |
| warm / keep by value | decides what to warm and keep | D149 | `v5/value_readers.py` | built (offline), not wired | `v5/value_readers_checks.json` | no engine action exists for it to drive |
| shed / backlog order | sheds and orders a backlog by value | D149, D150 | `v5/value_readers.py` | built (offline), not wired | `v5/value_readers_checks.json` | none |
| deficit weighting | weights value by per-device deficit | D151 (4) | **not implemented** | designed | none | see A.1 |
| history-length bands | accuracy fitted by history-length band | D149 | **deliberately not fitted** | designed, blocked | spec 7.9 | 28 DEV questions, cloud RECENT Wilson [0.037, 0.272] width 0.235; three bands would hold about nine each. Needs P19 |

### A.4 The counterfactual

| element | what I believe it does | D-row(s) | file:line | status | proof artefact | difference |
|---|---|---|---|---|---|---|
| candidates per decision kind | request / state / sync, each with its own candidate set | D151 (2) | **no `v5/cf_*.py` on origin** | designed | none | **not built.** Session B has not started, by my decision: it needs session C's interface note for what warm / touch / reload guarantee |
| per-decision horizons | each decision kind looks ahead its own horizon | D151 (3) | not built | designed | none | not built |
| two-level fidelity | coarse then fine evaluation of candidates | D151 (4) | not built | designed | none | not built |
| latest-safe-start deferral | defers until the latest start that still meets the deadline | D151 (3) | not built | designed | none | not built |
| objective incl. harm to others | expected correct on-time answers, counting harm to other devices | D151 (4), D152 (1) | not built | designed | none | not built |
| fixed margin `MARGIN_CF` | deviate from base only beyond a fixed margin, never tuned | D151 (1), **D154 (2)** | placeholder `0.05` in spec only | designed | none | **D154 (2) now defines it as the gate's held-out p90 absolute prediction error in objective units, set ONCE when the gate passes. The gate does NOT pass, so MARGIN_CF cannot be set, so no v5 cell may run** |

### A.5 Engine actions

| element | what I believe it does | D-row(s) | file:line | status | proof artefact | difference |
|---|---|---|---|---|---|---|
| warm-ahead prefill | prefills uploaded frames onto the append-only history, prefill-only, lowest priority | D148, D150 | **`engine_actions.py` does not exist on origin** | designed | none | not built; session C in progress |
| touch | sets recency without recomputing | D150 | not built | designed | none | not built. vLLM cannot pin KV, so "warm" is a probability, not a promise |
| reload-from-host | reloads a history from the host tier | D150 | not built | designed | none | not built, **and its only trigger state is unreachable**: the belief is never `host` in 39 committed cells |
| hold back / slice background warming | restricts what enters the GPU | D150 | not built | designed | none | not built |
| WARM-ALL + LRU baseline | prefills every batch on arrival, lets vLLM evict | D150 | **`arms_warmall.py` does not exist on origin** | designed | none | not built. **It is the only way to identify the warm regime out of arm**, so the cost-model gate depends on it |

### A.6 Sync

| element | what I believe it does | D-row(s) | file:line | status | proof artefact | difference |
|---|---|---|---|---|---|---|
| per-frame robot upload | uploads each robot frame as captured | D150 SYNC (1), **D154 (4)** | `trace.py:513-514`, `DS.HISTORY_BATCH_S = 30.0` (`data_sources.py:51`) | **built as 30 s BATCHES, contrary to the D-row** | none | **D68's 30 s batch is still what the contract sends.** D154 (4) replaces it with per-frame upload for ALL arms; earlier cells to be labelled `upload-30s`. Not yet done; queued after the EP-G bodies |
| question-time delta | sends the delta between the last upload and the question | D150 SYNC | partially via `history_append` | built | none | not audited against the D-row |
| outage handling | synthetic outage model | D150 SYNC | not located | designed | none | no implementation found |
| backlog order | orders a post-outage backlog by value | D150 SYNC | not built | designed | none | not built |

### A.7 Dashcam episode context

| element | what I believe it does | D-row(s) | file:line | status | proof artefact | difference |
|---|---|---|---|---|---|---|
| EP-G episode context | every dashcam query, device and cloud, carries the append-only episode | **D153** | `bodies.py:148` **raises** on more than one frame; `coordinator.py:524` sends exactly one | designed | none | **the live contract is ONE FRAME PER CALL, the opposite of D153.** `bodies.build_body` refuses a multi-frame monitor body by construction |
| refresh period N | fresh context after N s with no carry-over | D153, D148 | SH-EP used `EP_G_CAP_FRAMES = 21` (`sh_ep_manifest.py:57`), about 10 s at 2 fps | designed, **N not fixed** | measured both ways, see F.1 | SH-EP's cap bound exactly at its last instant, so the study never exercised a refresh. "Fresh with no carry-over" and "sliding cap" differ by 3.8x in excluded instants and 1.7x in prompt tokens |
| 3-frame floor | instants before an episode's 3rd frame are not decision instants for any arm | D153 | not implemented | designed | measured: see F.1 | in SH-EP the floor was nearly free (0.15 percent) because the manifest built a 4 s pre-roll from **165 frames that are NOT in the committed D91 store**. In live2 the grid starts at `NEXAR_GRID_T0_S = 3.0` with no pre-roll, so every episode starts at 1 frame |
| discard when idle | episode context dropped when the device goes idle | D153, D148 | not implemented | designed | none | not built |

### A.8 Decision trigger

| element | what I believe it does | D-row(s) | file:line | status | proof artefact | difference |
|---|---|---|---|---|---|---|
| 100 ms decision period | one decision period for every arm, events batched | D99 (1) | `coordinator.py:61`, `DECISION_PERIOD_S = 0.1` (`:65`) | built, live-validated for the BASE policy | committed cells | none. F6 breached the period in 2.7 percent of periods (`study_policy_f.md`) |
| event-gated triggers | the counterfactual runs on events within the period, not every period | D151 (5) | not built | designed | none | not built |
| p99 < 20 ms at 32 devices | planner wall-clock budget | D151 (5) | not built, no instrument | designed | none | **no per-decision wall-clock instrument emitting a distribution exists**, so the budget cannot be checked even if the planner existed |

---

## B. Deviations from the design log

| # | what the log says | what is there now | who fixes | changes baseline cells too? |
|---|---|---|---|---|
| B1 | D153: every dashcam query uses EP-G episode context, never one frame | `bodies.py:148` RAISES on a multi-frame monitor body; `coordinator.py:524` sends one frame | me (session D), in progress, TOP PRIORITY | **YES.** Every arm's dashcam workload changes. The H100 is labelling all current cells `dashcam-1f`, sensitivity only, and has armed `runs/EPG_ARGS` to switch |
| B2 | D154 (4) / D150 SYNC (1): robot frames upload per frame as captured | 30 s batches, `HISTORY_BATCH_S = 30.0` (`data_sources.py:51`), D68 | me, queued after B1 | **YES.** All arms; earlier cells to be labelled `upload-30s` |
| B3 | D147: robot deadline 3 s | default is still `5.0` in `data_sources.py:43` and `run_live2_real.py:92`; 3 s only if `--robot-deadline-s 3` is passed | me | yes for any cell run without the flag |
| B4 | D154 (2): MARGIN_CF set from the gate's held-out p90 error | placeholder `0.05` in the spec; gate fails so it cannot be set | blocked on the gate | no, but **blocks every v5 cell** |
| B5 | D151 (4): deficit-weighted objective | the only deficit counters are a v1 artefact, DEFAULT OFF (`arms_policy.py:276`), steering on on-time not correctness | session A (spec), then whoever builds the objective | no |
| B6 | D150: engine telemetry corrects the residency belief | logged only; no read into the belief; the field observes the wrong traffic | session C | no |
| B7 | D150: reload-from-host | belief is never `host` in 39 cells, so the action's trigger cannot occur | session A's spec settles promotion; NOT changed overnight per D106/D116 | no |
| B8 | D151 (2) to (5): the counterfactual engine | no code on origin | session B, not started (blocked on C's interface note) | no |
| B9 | D150: warm-ahead, touch, reload, hold-back; WARM-ALL + LRU | no code on origin | session C, in progress | WARM-ALL adds a new arm only |
| B10 | D149 (4): the value-inversion acceptance test must discriminate | it does not, in C3's slot | me / session A, by moving the reader to admission | no |
| B11 | D154 (5): cascade arms use measured device latency | `DEVICE_WAIT_RULE_S = 0.567` proxy (`data_sources.py:191`) | me, label now; rerun after StudyORIN-REC | yes for the five cascade arms |

---

## C. Dependencies on other machines

| element | needs | current state | ETA | if it does not land tonight |
|---|---|---|---|---|
| cost-model gate | H100 WARM-ALL calibration cells **on the EP-G workload** (D153) | WARM-ALL not built; EP-G bodies not built. H100 has armed `runs/WARMALL_CELLS` and `runs/EPG_ARGS` and runs them at the next boundary once committed | depends on sessions C and D tonight | **v5 NOT LIVE.** Gate fails, so MARGIN_CF cannot be set, so D154 (2) forbids any v5 cell |
| MARGIN_CF | the gate passing | gate FAILS (decode 1.30 to 1.32 held out; warm confounded with arm) | not before WARM-ALL on EP-G | v5 NOT LIVE |
| engine actions | H100 32B confirmation break, all three measurements on the deployment stack | not requested; nothing to run yet | after session C commits | element skipped; if only reload fails, v5 may still go live with reload disabled, PROVISIONAL |
| value readers (bands) | Orin P19 full S-EMBER sweep | not started; P19 is pinned behind the LH-REQ run | not tonight | bands stay unfitted; history length enters only through `P(on time)`, flagged non-neutral |
| device answers / latencies | Orin **StudyORIN-REC** | **unblocked tonight**: frame store verified complete (234 of 234 videos, 52,031 files, 1.4 GB, sha256 manifest); parity gate pre-registered at 5,476 to 5,682 prompt tokens | Orin running it first | cascade arms stay on the 0.567 s proxy, labelled `proxy-0.567`, rerun queued (D154 (5)) |
| single-shot confidence | Orin SS2 re-record with logprobs | queued after ORIN-REC | tonight if ORIN-REC finishes | the five cascade arms keep declared-but-unmeasured confidence |
| dashcam re-record | Orin StudyD14b-FULL | **ON HOLD by me**: its refit inputs were written for one-frame C1 and D153 voids them | after the EP-G bodies settle | no device-tier dashcam calibration; not on v5's critical path |
| A6000 (this box) | EP-G bodies, per-frame upload, integration proofs | in progress | tonight | B1 and B2 remain; H100 keeps running `dashcam-1f` sensitivity cells |

---

## D. Critical path to "policy-v5 ready"

1. **EP-G dashcam bodies** in `bodies.py` and the trace generator, with D153 proofs (a) to (d), plus `runs/EPG_ARGS`. Me. Tonight. **Blocks everything downstream, because D153 requires the gate and WARM-ALL to use the EP-G workload.**
2. **WARM-ALL + LRU arm** with its four proofs including a non-zero characteristic-decision count. Session C. H100 holds a boundary slot.
3. **H100 WARM-ALL calibration cells on EP-G.** Needs 1 and 2 on origin. H100, at a boundary.
4. **Refit the cost-model gate** on those cells. Me. **The gate must PASS.**
5. **Set MARGIN_CF** from the gate's held-out p90 absolute error, per D154 (2). Once, frozen.
6. **Engine actions** built and dry-proved. Session C.
7. **Counterfactual engine** built and dry-proved. Session B, **not started**.
8. **Integration and dry proofs**: Step 2b per component, the value-inversion test AT ADMISSION, decision latency p99 < 20 ms at 32 devices (needs an instrument that does not exist).
9. **32B confirmation break** on the H100 for all three engine-action measurements.
10. **Then** "policy-v5 ready".

**Can this complete before 06:00? No.** Steps 7 and 8 alone are the counterfactual engine plus an instrument that does not exist, and step 7 has not begun. Step 4 requires the gate to pass, which requires steps 1 to 3 to land and new cells to run. The realistic outcome by 06:00 is steps 1, 2 and possibly 3, with the gate refitted at best. **v5 will not be live by 06:00 and I will report that rather than relax the gate.**

---

## E. Placeholders and hard-coded numbers

| constant | value | source | fixed by a D-row? |
|---|---|---|---|
| `MARGIN_CF` | 0.05 | **PLACEHOLDER** | D154 (2): set once from the gate's held-out p90 error. Not yet settable |
| `NEXAR_DEADLINE_S` | 1.0 s | use case | **D71, D154 (1), no longer provisional** |
| `ROBOT_DEADLINE_S` | 5.0 default, 3.0 by flag | use case | D147 sets 3 s; the DEFAULT is a deviation (B3) |
| single-shot deadline | 2.0 s | use case | D147 |
| `DECISION_PERIOD_S` | 0.1 s | design constant | D99 (1) |
| planner budget | p99 < 20 ms at 32 devices | design constant | D151 (5); no instrument exists |
| `HISTORY_BATCH_S` | 30.0 s | design constant | D68, **replaced by D154 (4)**; still in force (B2) |
| `DEVICE_WAIT_RULE_S` | 0.567 s | **PROXY** | D154 (5): label `proxy-0.567`, rerun with measured latency |
| `k_r_frac` | 0.3 of each type's own deadline | design constant | D143 |
| cloud D2 accuracy | 0.250 | profiled, DEV fit (`lh_req_quality.json`) | D6, D149 |
| cloud RECENT accuracy | 0.107143 | profiled, DEV fit | D6, D149 |
| device accuracy | 0.107143 | profiled, DEV fit; **a D87 substitution** | D149; StudyORIN-REC replaces it |
| `D2_TOK_PER_IMG` | 90 tokens | profiled (StudyRH4) | committed |
| dashcam tokens per frame | 338, plus about 42 text | profiled (StudySH-EP) | verified: `3,084 + 338 x (n - 9)` matches 3,895 of 3,898 instants at deviation 0, exactly 7,140 at 21 frames |
| `EP_G_BACK` | 4.0 s pre-roll | design constant (StudySH-EP) | **not available in live2**: needs 165 frames absent from the D91 store, present for only 32 of 300 clips |
| `EP_G_CAP_FRAMES` | 21 frames, about 10 s | design constant | D153 calls it "N"; not fixed (F.1) |
| `ORIN_CALIB_A` / `B` | 0.114932 / 1.174287 | profiled (StudyORIN2-stack) | committed |
| `DEVICE_RECALL_N` / `CORRECT` | 845 / 277 | profiled | D87 |
| `q_min`, episode floor | 3 frames (user may raise to 6) | design constant | D153 |

---

## F. Questions, each with my default

**F.1 The dashcam refresh, and it is the largest open number in v5.** D153 says "fresh context after N s
with **no carry-over**", which is not the same as SH-EP's 21-frame sliding cap. SH-EP never exercised
a refresh: its cap bound exactly at its last instant. Measured on the committed trace (seed 4, 16
devices, 1,200 s, 40:40:20, 13,193 monitor instants, 189 plays):

| | frames per request (median) | floor-3 excluded | floor-6 excluded | total prompt tokens per run |
|---|---|---|---|---|
| sliding cap 21, carry-over kept | 21 | 378 (2.87%) | 945 (7.16%) | 80,794,968 |
| **fresh every 21 frames, no carry-over (D153 literal)** | 10 | **1,429 (10.83%)** | 3,564 (27.01%) | 46,260,494 |

**My default: implement D153 literally, fresh context with no carry-over at N = 21 frames (10.5 s),
matching SH-EP's cap, and report the excluded-instant count per run as proof (d). Marked
PROVISIONAL.** It is what the D-row says, and it halves the prompt-token load, which matters at 32
devices. I flag that it triples the floor's cost and that 10.83 percent of instants excluded is
large enough to need stating in every headline.

**F.2 The 3-frame floor in live2 cannot be made nearly free, unlike in SH-EP.** In SH-EP the floor cost
0.15 percent because the manifest built a 4 s pre-roll; that pre-roll needed 165 frames that are
**not in the committed D91 store** and exist for only 32 of 300 clips. live2's grid starts at
`NEXAR_GRID_T0_S = 3.0` with no pre-roll, so every episode starts at 1 frame. **My default: accept
the floor at 2 instants per episode (or per refresh cycle under F.1) and count them, rather than
encode new pre-roll frames**, since new frames would be a methodological change and the overnight
rule forbids one.

**F.3 Does the episode accumulate frames an arm did not act on?** D153 says each frame is prefilled as
captured, which implies yes and which is also what makes proof (b) hold by construction. **My
default: the trace generator emits the episode frame list deterministically, independent of any
arm's release decisions, so the request digest is identical across arms by construction rather than
by coordinator discipline.**

**F.4 Session B has not started.** I held it back because the counterfactual engine needs session C's
interface note for what warm / touch / reload actually guarantee, and starting it blind would have
it inventing a contract C is about to define. **My default: start B as soon as C posts the interface
note; if C does not post it tonight, start B anyway against the vLLM no-pin constraint alone and
mark its interface assumptions PROVISIONAL.**

**F.5 The value-inversion test cannot pass where the reader currently sits.** **My default: move the
reader to ADMISSION as part of v5 (where D151 (3) puts the robot decision anyway) and run D149 (4)
there, rather than weaken the test.** Not done tonight; it is step 8 work.
