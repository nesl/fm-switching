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

---

# Addendum, 2026-11-20 after the D154 ruling and StudyORIN-REC part 1

## G. The measured device entry breaks the tie that D152 (2) rested on

**StudyORIN-REC part 1 landed (`bd1401c`) and its gate passed**: 1 request, 0 errors, header
`D2 history`, `RECALL_GEN` temperature 0.0 / max_tokens 512 / seed 42, store `/dev/shm/sember_d2_q88`,
Qwen3-VL-4B on the Orin under vLLM with the ACC2 mm-processor kwargs. 97 questions, RECENT, paired on
`question_id`.

| split | measured device | Wilson 95% | superseded D87 proxy |
|---|---|---|---|
| **DEV (the fit split)** | **2/28 = 0.071429** | **[0.019812, 0.226454]** | 3/28 = 0.107143 |
| EVAL (reference only) | 11/69 = 0.159420 | [0.091418, 0.263345] | 0.246377 |

Installed in `lh_req_quality.json`, with the D87 entry kept beside it as
`device_4B_RECENT_D87_SUPERSEDED` so the change is auditable rather than silent. **G7 closes** for
the STACK substitution; the representation caveat stands, because the measured entry is also RECENT
and no device-on-D2 result exists.

### G.1 What it does to the reader, recomputed as ruled

Under D87 the device scored **exactly** what cloud RECENT scored, 0.107143, and ties go to the
device, so RECENT was never sent and **D152 (2)'s rule fell out of the reader arithmetically**. The
measured entry is lower, so that tie is gone:

| | RECENT strictly beats the device? | RECENT sent when | D2 sent when |
|---|---|---|---|
| D87 proxy (0.107143) | **no**, exact tie | never | `P(on time) > 0.4286` |
| **measured (0.071429)** | **yes** | **`P(on time) > 0.6667`** | `P(on time) > 0.2857` |

Decision grid, rows `P(on time | D2)`, columns `P(on time | RECENT)`. **7 of 20 cells flip**, all in
the direction of sending more:

| p_D2 \ p_RECENT | 0.0 | 0.5 | 0.6 | 0.7 | 1.0 |
|---|---|---|---|---|---|
| 0.0 | withhold | withhold | withhold | **SEND RECENT** | **SEND RECENT** |
| 0.3 | **SEND D2** | **SEND D2** | **SEND D2** | **SEND RECENT** | **SEND RECENT** |
| 0.5 | SEND D2 | SEND D2 | SEND D2 | SEND D2 | SEND D2 |
| 1.0 | SEND D2 | SEND D2 | SEND D2 | SEND D2 | SEND D2 |

(Under D87 the whole `p_D2 = 0.0` and `0.3` rows were `withhold`.)

**Consequence, reported and not acted on: D152 (2)'s rule no longer falls out of the value reader.**
It said the RECENT shortcut must not be used for long-horizon questions, and the reader derived that
from the tie. With the device measured, the reader now sends RECENT whenever it is more than about
two-thirds likely to arrive. The rule must therefore be **imposed explicitly or abandoned**, and
that is a user decision, not one the reader can be left to make. **Not statistically settled
either**: the DEV device interval [0.019812, 0.226454] CONTAINS cloud RECENT's 0.107143, so on 28
questions "RECENT beats the device" is one plausible reading of a wide interval, not a fact.

## H. RETRACTED IN PART: the measured latencies are the COLD re-send path, an API artifact

**D155 (1) corrects this section and I am marking the retraction at the point of use rather than
quietly editing the numbers.** I reported the StudyORIN-REC part 1 latencies as the device baseline
and drew three conclusions from them. They are the **COLD RE-SEND path**, which D61 (b) already
classifies as an API ARTIFACT and not the device baseline. **Consequences (1) and (2) below do not
stand**, nothing was wired anywhere, and the cascade arms keep their `proxy-0.567` label until the
Orin's WARM per-question latencies land.

What survives is narrower. Consequence (3) was a real gap and the user has since amended D152 (1):
the robot headline is now correct answers delivered BY THE DEADLINE from either source, with
correct-at-any-time beside it. **Re-scored offline (section 23 of `study_frozen_test.md`, commit
`8e1dbbb`): the two columns are equal integer for integer on all 89 questions, all five arms, all
four cells, and no ranking changes anywhere.** Classified under Rule 2 as INCONCLUSIVE, sub-case
**unexercised**: the rule is live and reachable (Step 2b moves 9 of 20 decisions with an injected
9.999 s device latency, and 0 of 20 on the committed source), and nothing in these runs reaches it.
The reason is headroom: the scorer's device latency is D87's in-process 0.146 to 0.225 s against a
5 s deadline, **22.2x**, so no device answer is late in any committed cell. The honest sentence is
"the deadline rule makes no difference AT 0.146 to 0.225 s", and that clause must travel with it.
Where a ranking change would come from once a warm latency lands: b7 and mooncake lean on the
device fallback on roughly half their questions against hybrid-F's 4 of 89, so a device latency
above the deadline would hit the baselines far harder than hybrid-F.

The superseded reading follows, kept so the retraction is auditable.

### H.0 SUPERSEDED: what I originally wrote


| quantity | measured (n = 97) | committed proxy |
|---|---|---|
| device TTFT | median **3.296 s** (p90 3.324, max 3.416) | n/a |
| device completion | median 3.354 s | n/a |
| **device end to end** | median **6.651 s** (min 6.542, max 6.891) | `DEVICE_WAIT_RULE_S = 0.567 s` |

**The proxy is wrong by 11.73x, and all 97 of 97 questions exceed it.** Every cell of the five
cascade arms run against `0.567 s` is therefore labelled `proxy-0.567` and queued for rerun per
D154 (5).

**Three consequences that go beyond the cascade arms.**

1. **At D147's 3 s robot deadline the device's own answer is NEVER deliverable.** 6.651 s end to end
   is more than twice the deadline. D149 and D152 both rest on "the device answers when the full
   history cannot arrive in time"; on this stack, at this deadline, it does not arrive either.
2. **Capping the answer would not rescue it.** TTFT alone is 3.296 s, already past 3 s, so P20's
   answer cap (which would cut the 3.354 s completion) leaves the request late on prefill alone.
   P20 is still worth doing, and it cannot fix this.
3. **D152 (1)'s headline counts the device's answer whenever the cloud's does not arrive.** If the
   device answer is itself late, `correct_answers_delivered` is crediting an answer that misses the
   deadline. This needs a ruling: either the headline counts the device answer regardless of its
   latency (in which case it is not a delivery metric), or it does not (in which case the 3 s
   headline numbers already reported must be recomputed).

**The spread is tight (IQR 6.634 to 6.678) and that is expected, not a caching artefact**: all 97
part-1 requests are RECENT at exactly 60 frames, so the input is constant and a near-constant
latency is what should follow. Flagged under consistency check 3 because a constant where a
distribution is expected is normally a warning; here the constancy of the INPUT is the explanation
and it is stated rather than assumed.

## I. Baselines whose published mechanism includes proactive prefetch or warming

Listed as ruled, with **no behaviour changed tonight**. Each needs a ruling on whether its adapter
should now use the warm-ahead action that PATCH 1 makes expressible.

| baseline | published mechanism includes proactive warming? | what its adapter does today | should it use warm-ahead per its card? |
|---|---|---|---|
| mooncake | **yes**, KVCache-centric disaggregated prefill with a prediction-based early-rejection and cache-aware scheduling | reactive only; 0 gpu beliefs, 0 engine prefix hits in its committed cells | **probably yes**, needs a ruling. Its card's cache-centric scheduling is the closest published analogue to warm-ahead |
| preble | **yes**, prefix-aware scheduling that places requests to maximise reuse | reactive | arguable: its reuse is placement, not prefetch. Ruling needed |
| kvflow | **yes**, flow-based KV management with eviction and reload | reactive | likely yes for reload, which is unreachable today (belief never host) |
| attentionstore | **yes**, a hierarchical KV cache with explicit prefetch from slower tiers | reactive | **yes on its card**, and it is the baseline most disadvantaged by the current action space |
| lmcache | **yes**, cross-request KV reuse with offload and load | reactive | likely yes. Note the H100 declined an LMCache install for a torch-version reason (`study_rh5` line 105) |
| pensieve | **yes**, multi-turn KV retention across turns | reactive | likely yes for retention, which is what `touch` expresses |
| b7-edf-feasibility, edf, llf, always-cloud-fcfs | no, these are schedulers | reactive | no |
| eco-llm, r3-streaming, thinking-qwenvl-atdm, confidence-cascade, cascade-routing, streamscout | no proactive warming in their cards | reactive | no |

**This is the fairness question PATCH 1 opens, stated plainly: six of the KV-cache family publish a
proactive mechanism, and until tonight none of them could express it, because warming ahead was
rejected by the validator. Every committed comparison against them was therefore a comparison
against an adapter that could not do what its paper says it does.** That is not a flaw in the
adapters; it is the action space. It does not change any committed number, and it does change what
those numbers mean. Ruling requested before any v5-versus-baseline headline is written.
