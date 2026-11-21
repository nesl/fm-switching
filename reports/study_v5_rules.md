# StudyV5-RULES: `v5-rules`, the rules-only v5 arm

Flash, A6000 box, 2026-11-20. Detached worktree at `origin/main` (`df586a0`); the flash working
tree is hundreds of commits behind and nothing here was read from it.

Artefacts: `experiments/orchestration/live2/arms_v5rules.py`, the registration block at the bottom
of `experiments/orchestration/live2/arms.py`,
`results/orchestration/live2/v5rules/v5_rules_proofs.json`.

**REGISTER, first, because the numbers below are in two different ones.** Nothing in this report
is a MEASURED latency, quality or capacity result. Every number is from a DRY decision-path run
with a stub bridge and no engine, so these are counts of DECISIONS and of FRAMES ON THE WIRE,
never of seconds and never of vLLM's own `cached_tokens`. The sweep this report precedes is the
H100's, and it has not run.

---

## 0. What this arm is, and the one ruling it rests on

`v5-rules` is `hybrid-F-lhreq-noc3` plus **warm-ahead as a rule**, and nothing else. It makes no
counterfactual prediction, runs no planner, and reads no margin. That is the whole of its claim to
be runnable tonight: D154 (2) forbids any v5 cell before `MARGIN_CF` is set from the D151 (6)
cost-model gate's held-out p90 error, and that gate FAILS (`reports/policy_v5_assessment.md` A.1
and C: decode over-predicts 25 to 32 percent held out, and warm is confounded with arm). A
rules-only arm needs no margin and so needs no gate pass.

**THE RULING THAT SAYS SO IS NOT ON ORIGIN.** The brief for this work cites **D156**, ruling that
D151 (6)'s gate applies to COUNTERFACTUAL decisions only. `research/policy_design_log.md` at
`df586a0` ends at **D155a**, and `grep -rn D156 research/ reports/` returns nothing. So the premise
that unblocks this arm is recorded nowhere a reader can check, while the ruling it carves an
exception out of, D154 (2)'s "no v5 cell runs before it is set", IS recorded. The user's own
decision message is the authority, as every D-row from D153 on says in its own source column, and
I have built to it. But **D156 is owed a row in the design log, and `v5-rules` should not be cited
against D154 (2) until it has one.** The design log is not a file this session owns, so no row was
added. This is the largest open item in this report.

**What `v5-rules` is NOT.** No counterfactual, no planner, no latest-safe-start, no `MARGIN_CF`,
no value reader, no deficit weighting, no placement steering, no reload, no hold-back, no slicing
of a deadline request. Nothing in `arms_v5rules.py` imports `v5/value_readers.py`, so `MARGIN_CF`
is unreachable from this arm by construction, not by discipline.

---

## 1. Step 0: what would make this run uninterpretable, written before it started

Six things were checked before any arm was constructed. Two came back "wait" and are reported to
the operator rather than worked around.

| # | what would invalidate the run | checked how | answer |
|---|---|---|---|
| 1 | **The arm self-censors and the prefill count is 0 for a plumbing reason.** `engine_actions.known_sessions` asks `obs.live_sessions` BEFORE emitting, so an arm on a harness without PATCH 1 refuses its own action and reports a zero indistinguishable from a policy result. `arms_warmall` hit exactly this, and a shim that patched only the validator left the arm still self-censoring and still at zero. | read the three halves of PATCH 1 on origin rather than the report that requested it | **CLEAN.** PATCH 1 is live at `df586a0`: `baselines/interface.py:160` declares `Observation.live_sessions`, `:277` adds it to `validate_action`'s `known_sessions`, and `cstate.py:589` populates it from the open sessions. **No shim is used anywhere in this report and none is needed.** |
| 2 | **The comparator is not the base.** A warm-ahead count against the wrong base measures the base change, not the rule. | the base is `HybridArm(**CONFIGS["hybrid-F-lhreq-noc3"])`, the committed config taken whole and not re-derived; and the base's own digest is checked against its committed value at the identical cell before anything else is read | **CLEAN**, and it is check 7's positive control: section 5. |
| 3 | **A cached-token proof with no resolved frame store.** Without a frames root, `coordinator._path` returns None, every frame goes as a uuid-only reference, and the proof shows a PERFECT prefix reuse with ZERO frames ever carrying bytes. | the proof builds a placeholder store for every `frame_ref` the trace asks for, runs `preflight.check`, and carries `n_unresolved`; base and treatment share one store and one trace | **CLEAN by construction**, and measured: 5,678 refs, `n_unresolved = 0`. No cell without a store is compared against one with it. |
| 4 | **An ASK counted as a DECISION.** `warm_ahead_emitted` is one standing MATERIALIZE per candidate per epoch and most are no-ops inside `coordinator._advance_build`; a previous session reported 2,289,557 of these as emitted warming. | every headline count is read off the coordinator's own decision log (`release_piece` / `release_whole` rows), and the arm's asks are reported beside it, labelled, never summed | **CLEAN by construction.** The two numbers differ by 102x in this run (827 against 83,980). |
| 5 | **A default is about to be restored under the cells.** `ROBOT_DEADLINE_S = 5.0` is still the default at `fleet/data_sources.py:43` and `run_live2_real.py:92` while D147 sets 3 s, so a cell run without `--robot-deadline-s 3` silently uses 5 s (`policy_v5_assessment.md` A.2). At 5 s a cold history is often feasible and warming ahead has much less to buy, so a `v5-rules` cell at the default would UNDERSTATE the mechanism for a reason nothing in the output would show. | read the two defaults on origin | **WAIT, and it is the operator's to set.** Section 7 item 1. It is also why this report's two halves run at different deadlines, stated in section 3. |
| 6 | **The mechanism has no reachable path at this grain.** Warm-ahead needs frames to arrive before a question. | read `fleet/trace.py` | **REACHABLE but coarse at the time of the check.** Per-frame robot upload (D154 (4)) was NOT on origin when this was checked at `df586a0`: `trace.py` emitted `history_batch` only on D68's 30 s grid. **It landed at `34a4af0` while this work was running**, and proof 4 measures `v5-rules` picking it up. A cell at the default contract is still `batch-30s` and must be labelled `upload-30s`. |

---

## 2. Step 1: the causal chain

Robot frames are uploaded as they are captured (D150 SYNC (1); on origin still D68's 30 s batches,
section 1 item 6). **If** the cloud prefills each uploaded batch onto that session's append-only
history at lowest priority, which is D150 STATE lever 1 and spec v5 section 8's "warm", expressed
through `engine_actions.plan_warm_ahead`, **then** by the time a long-horizon question for that
session arrives the history's prompt prefix has already been sent to the engine, so the question's
own request carries only the frames the engine has not yet seen: `coordinator._submit_recall`
sends the first `len(s.sent_bytes_for)` frames as uuid-only references and only the remainder as
bytes, and `sent_bytes_for` advances only for a frame whose bytes went out
(`coordinator.py:698`, `:713-714`, `:771`). **Therefore** the uncached prefill the question must
pay for falls. Because the robot deadline is 3 s (D147) and D147 states that at 3 s "a cold
history under load essentially cannot be answered in time, so warming ahead becomes necessary", a
lower uncached prefill at question time raises the number of long-horizon questions whose FULL
history can be admitted and arrive before the deadline. And because D152 (2) forbids the RECENT
shortcut and D152 (1) as amended by D155 (3) scores the robot headline as correct answers
delivered **by the deadline** from either source, a full history that arrives in time is worth
more than the device's own answer (DEV fit, D143 ruling A: cloud D2 25.000 percent against the
device's 10.714 percent). The W2 discipline (`deadline_work_at_risk`, `k_r = 0.3 x` deadline,
D143 ruling B) is what stops the prefill paying for itself by displacing the deadline work it
exists to help.

**No link in that chain is a prediction.** Each is a rule evaluated on state already in the
observation, which is why this arm needs no cost model and no margin.

---

## 3. Step 2: each link instantiated, with the READ that consumes it

Cell A (`proofs()`): dry, seed 4, 16 devices, 1,200 s, 40:40:20, LH-REQ robots, ss2, dashcam-1f,
robot deadline **5.0 s**. Cell B (`cached_token_proof()`): dry, seed 4, 8 devices, 600 s, 50:50,
LH-REQ robots, ss2, **EP-G** dashcam bodies, resolved frame store, robot deadline **3.0 s**.

**Why two cells and two deadlines, stated so it cannot look like a choice made to taste.** Cell A
exists to carry the positive control, and its control is a committed digest measured at the
committed 5 s default; changing the deadline there would invalidate the control rather than test
the arm. Cell B is the proof of the mechanism, so it is run in the regime D147 says warming is
for. `test_hybrid.dry` takes no `dashcam_format`, and it is not a file this session owns, which is
why cell A is dashcam-1f; cell B builds its own trace and runs EP-G, confirmed off the wire
(`dashcam_format: "epg"`, 3,864 EP-G monitor requests, identical for both arms).

| causal link | implementing quantity | value / range in this run | varies as expected? | the READ that consumes it |
|---|---|---|---|---|
| frames arrive before a question | `history_batch.frame_refs`, ingested into `session.frames` | 5,678 frame refs in cell B, all resolved | yes | `cstate.py:298` `s.frames.extend(ev["frame_refs"])` |
| the rule names a robot session with no pending question | `plan_warm_ahead` -> `SessionAction(MATERIALIZE)` | cell A: 163,962 wanted, 83,980 emitted asks | yes | `coordinator._enact` -> `_advance_build` (`coordinator.py:435`, `:530`) |
| the coordinator ISSUES a prefill piece | `release_piece` / `release_whole` rows | **cell A: 827, base 0. cell B: 330, base 0** | yes | the piece is submitted: `coordinator.py:660-672` |
| the prefill puts frame bytes on the wire | `session.sent_bytes_for` | cell B: non-empty for every warmed session | yes | `coordinator.py:771` writes it; **`coordinator.py:698` READS it** to split the recall body |
| at question time the recall reuses that prefix | frames sent as uuid reference in the recall body | **cell B paired: base 0 of 330, v5-rules 328 of 330** | yes | `coordinator.py:713-714` builds the body from it; `bodies.image_part` emits the reference form |
| a warmed history is feasible where a cold one is not | hybrid-F's feasibility test | cell B: v5-rules released **6** recalls and declined **0**; base released **4** and declined **2** | yes | `hybrid_arm.py` feasibility branch |
| the belief promotes on a complete build | `RecallQuery.readiness` at release | cell A: v5-rules COLD 357 / GPU-WARM 20; `-off` COLD 372 / GPU-WARM 0 | yes | `cstate.py:168-169`; and `coordinator.py:681` costs the recall from `residency_readiness` |
| W2 yields to deadline work | `deadline_work_at_risk` | **cell A: 0 yielded epochs of 12,001. cell B: 0 of 1,501** | **NO: CONSTANT** | read inside `plan_warm_ahead` before emitting |

**One link is CONSTANT and it is named rather than buried.** `deadline_work_at_risk` returned False
in every epoch of both cells, so the W2 yield **never fired**. Under CLAUDE.md Rule 2 the W2
discipline is **unexercised** in these dry cells: it is built, reachable and checkable (the
`v5-rules-noyield` ablation exists for exactly that), and nothing here shows it working. This is
**not** a stopping condition for the arm, because W2 is a SAFETY property and not the mechanism
under test: the mechanism is the prefill, its quantity is 827 and 330 and both vary as the claim
requires. It does mean **the claim "yields to deadline work" is unproven and must not be reported
as proven**, and it is the first thing the H100's cell can settle, since a dry stub bridge is
exactly where contention is absent. The 0.3 fraction is W2's own committed constant and is
untouched.

---

## 4. Steps 2b, 3 and 4, and the three proofs the user named

### Proof 1: warm-ahead prefills issued (the characteristic decision)

| quantity | `v5-rules` | base `hybrid-F-lhreq-noc3` | `v5-rules-off` | register |
|---|---|---|---|---|
| **prefills ISSUED** | **827** | **0** | **0** | OBSERVED COUNT of `release_piece` / `release_whole` rows in the coordinator's own decision log |
| asks emitted | 83,980 | n/a | 0 | the arm's ASKS, one standing MATERIALIZE per candidate robot session per epoch; most no-op inside `_advance_build` |
| asks wanted | 163,962 | n/a | 0 | candidates considered |
| asks refused as unexpressible | 79,962 | n/a | 0 | see below; **not** the PATCH 1 blocker |
| epochs where W2 yielded | 0 | n/a | 0 | section 3 |

**PASS: 827 against the base's 0.** The headline is the ISSUED count. The two numbers differ by
102x, which is why the register matters: 83,980 is not a count of warming.

**The 79,962 unexpressible asks are not the blocker, and this was verified rather than assumed.**
An instrumented re-run of the same cell classified every refused candidate: **79,962 of 79,962 are
`not_open`**, and **0 were refused while present in `obs.live_sessions`**. The roster's
`session_device` is CUMULATIVE over the run while `live_sessions` is the currently-open set, so a
candidate whose session has already ended is correctly refused by `validate_action`'s own
future-knowledge guard. The same check at a smaller cell (8 devices, 300 s) gives 128 of 128
`not_open`. If PATCH 1 were missing, the refusals would instead be sessions that ARE open and the
issued count would be 0; it is 827.

### Proof 2: cached tokens rise at question time

**Register, and it is the whole of this proof's honesty.** No GPU and no engine ran, so vLLM's own
`cached_tokens` is **not measured and not claimed**: `backend.cached_tokens_of` needs a usage
block. What is measured is the only thing that drives cached tokens, namely how much of the
recall's prompt the engine has already been sent. This is the same register as
`reports/study_epg_bodies.md` proof (a), which labelled it the same way, and **the engine-side
confirmation is the H100's run and is owed.**

Cell B, EP-G, resolved store, 3 s deadline. **On the 4 recalls BOTH arms released** (the paired
comparison, because the two arms do not release the same set and a total-against-total column
would mix prefix reuse with changed admission):

| quantity | base | `v5-rules` |
|---|---|---|
| recalls compared | 4 | 4 |
| frames the engine had already been sent | **0 of 330** | **328 of 330** |
| frames the question itself had to carry | **330** | **2** |
| reuse rose on every one of the 4 | - | **yes, 4 of 4** |
| reused prefix, tokens, DERIVED lower bound at 338 per image | 0 | 110,864 |

Per recall, the four: 75 frames 0 -> 75 reused, 120 frames 0 -> 120, 75 frames 0 -> 75, and 60
frames 0 -> 58. **The one incomplete case is the interesting one and is reported, not smoothed**:
`robo000|s001` at t = 448.9 still carries 2 frames of 60 as bytes, which is the warming not having
caught up with the newest 2 frames of a session that was still capturing. That is the mechanism
behaving as specified at a 30 s upload grain, and it is exactly the residual per-frame upload
removes (section 4, proof 4).

Separately and as its own quantity, **`v5-rules` released 6 recalls against the base's 4**, and
**the base DECLINED 2 where `v5-rules` declined 0**. The two extra releases are `robo001|s000` at
t = 316.2 (225 frames, 20,281 tokens) and `robo003|s000` at t = 419.3 (270 frames, 24,331 tokens):
exactly the long histories the base's feasibility test refuses because it would have to rebuild
them cold inside a 3 s deadline, and which are feasible once already warm. The decline counts
pair with the release counts to the unit (2 declines become 2 releases, 0 lost the other way), so
this is **the chain's last link measured, not a confound** - but it is reported as a separate
number and is never folded into the reuse column.

**`n_unresolved = 0` of 5,678 refs, `preflight_ok = true`.** Without the store this proof would
have shown a perfect reuse with zero frames ever carrying bytes; the base and treatment ran
against the same store and the same trace.

### Proof 3: 0 illegal actions

**0 illegal actions**, cell A, 14,397 decisions (base 13,525, `-off` 13,525). `validate_action`
runs on every epoch inside `Policy.__call__` and RAISES on anything outside the registered domain,
including a MATERIALIZE naming a session the observation did not contain, so a cell that completes
with a non-empty log emitted none. This is the proof that matters most for a warm-ahead arm,
because naming an unknown session is precisely the illegality the rule flirts with.

### Proof 4, not asked for but now measurable: per-frame upload is picked up

**The switch landed while this work was running** (origin `34a4af0`, `--robot-upload per-frame`,
default `batch-30s`), so the question "is it picking it up yet" became measurable instead of
predicted, and was measured. Artefact:
`results/orchestration/live2/v5rules/v5_rules_perframe_pickup.json`.

Same cell B, same store, same 3 s deadline, same EP-G, same seed; the only difference is the
contract:

| quantity | `batch-30s` | `per-frame` |
|---|---|---|
| **prefills issued, `v5-rules`** | **330** | **1,163** (3.52x) |
| prefills issued, base | 0 | 0 |
| frames reused on the 4 shared recalls | 328 of 330 | 362 of 371 |
| frames the question still had to carry | 2 | 9 |
| recalls released, `v5-rules` / base | 6 / 4 | 6 / 4 |

**PICKED UP, with no change to the arm.** `arms_v5rules.py` contains no reference to the contract
beyond passing it to the trace generator, and it passes it only if the generator takes it, so the
file also still runs on a tree where the switch does not exist. The reason it needs no change is
the committed one: `trace.ROBOT_UPLOAD_NOTE` states that the record KIND and fields are unchanged,
"so the emulator, the coordinator, `cstate` and every arm need no change", and the warm-ahead rule
asks for every candidate robot session every epoch, so a finer upload grain simply gives
`_advance_build` new frames on more epochs.

**Two things in that table are worth the operator's attention rather than being smoothed over.**
The reused prefix rises (328 to 362) but so does the residual the question must still carry (2 to
9), because under per-frame upload frames keep arriving up to the moment of the question, so the
newest few are always un-warmed; per-frame buys a longer warm prefix, not a zero tail. And the
base's own frame total rises from 330 to 371 on the same four recalls, which is the committed
finding that `batch-30s` LOSES frames at the run horizon (`34a4af0`: total history tokens up
1.033x, "the batch stream is a strict per-session prefix of the per-frame stream"), not an effect
of this arm.

**Measured at `34a4af0` in a second detached worktree, not at the sha the arm is committed
against** (`df586a0`), because this session's commit was refused (section 9). The arm file is
byte-identical in both worktrees and the import checks were re-run at `34a4af0`: `import hybrid`,
`import arms` and `arms.make_arm("v5-rules")` all pass there.

### Step 2b: the decision-log diff against `hybrid-F-lhreq-noc3`

| quantity | value |
|---|---|
| differing decisions, **setwise** | **1,126** |
| differing rows, positional | 14,397 |
| first differing index | 0 |
| the first differing decision | `v5-rules`: `release_piece`, `t = 0.1`, `piece_tokens = 301`, `session = robo000\|s000\|1011205677616862_start_0.0_end_314.103`. The base's row at that index is `release_monitor` at `t = 5.1`. |

**PASS.** The setwise count is the decision count; the positional count is reported beside it
because the arm's very first decision is a new one, which desynchronises the whole log
(`test_hybrid._differing`'s own docstring). The first difference is the mechanism itself: a prefill
at t = 0.1 s, before any question exists.

### Step 4: the negative control

| quantity | value |
|---|---|
| control arm | `v5-rules-off` (`warm_ahead=False`) |
| base digest / control digest, `arm_version` stripped | `df9bf72fa552c094` / **`df9bf72fa552c094`** |
| treatment digest | `74c6ba238b4ea794` |
| control identical to base | **yes, byte-identical** |
| control prefills issued | **0**, the base's own count |

**PASS.** Disabling the mechanism collapses the arm to its base byte-identically, which is
stronger than "converges": the 1,126 moved decisions are the warming channel and nothing else.
Identity is asserted with `arm_version` removed, because the coordinator writes that label into
every row and a new arm necessarily carries a new one; the unstripped comparison is reported
beside it (`control_identical_including_arm_version: false`) so the label difference is visible
rather than hidden.

---

## 5. Step 5: the alternative explanation

The headline "`v5-rules` reuses a prompt prefix at question time where its base does not" could
also be produced by:

**(a) the claimed mechanism** - warm-ahead prefills put the history's frames on the engine before
the question, so the question's body carries references; or

**(b) `v5-rules` simply sending FEWER frames**, for instance by choosing a shorter representation,
which would also lower the bytes the question carries while reusing nothing.

**The data distinguish them.** (b) is excluded three ways: the base and the treatment carry the
SAME total frame count on all 4 shared recalls (330 and 330) and the same `est_tokens` per recall,
so nothing was shortened; the base releases `D2` 372 times and `RECENT` 0 times in cell A, so the
representation channel is not in use at all (C3 is off, which is the point of the noc3 base); and
the reduction is exactly accounted for by frames whose bytes went out EARLIER on a `release_piece`
row, which `sent_bytes_for` records and which the base has none of.

A third alternative, **(c) the extra two admitted recalls drive the whole result**, is excluded by
construction: the reuse claim is made only on the paired shared recalls, and the admission
difference is reported as its own quantity.

---

## 6. Results consistency check, all seven

**1. Cross-check against committed measurements.**

| quantity | this run | prior run | source of prior | ratio | agree |
|---|---|---|---|---|---|
| `hybrid-F-lhreq-noc3` decision digest, seed 4 / 16 / 1200 s / 40:40:20 | `5d3469549fead8ac` | `5d3469549fead8ac` | `results/orchestration/live2/frozen_test/value_reader_proofs.json` | 1.00 | **yes, exact** |
| same, decision rows | 13,525 | 13,525 | same | 1.00 | **yes** |
| same, representations | D2 372, RECENT 0 | D2 372, RECENT 0 | same | 1.00 | **yes** |
| base feasibility actions at this cell | 5 | 5 | `reports/study_frozen_test.md` 13.4 | 1.00 | **yes** |
| prefills issued by a warm-ahead arm at this cell, ALL sessions | 827 (`v5-rules`, robot-only by design) | 1,684 (`warm-all-lru`, real PATCH 1) | `results/orchestration/live2/v5/patch1_byte_identity_proof.json` | 2.04 | **>2x: investigated, explained below** |
| the same, **ROBOT sessions only**, which is the comparable quantity | **827** | **754** | re-run of committed `warm-all-lru` at the identical cell, classified by session | **1.10** | **yes** |
| the same, shimmed condition | 827 | 2,603 (`warm-all-lru`, shimmed) | `results/orchestration/live2/v5/engine_actions_warmall_proofs.json` | 3.15 | **a shimmed run; not comparable to a real-patch run and not treated as one** |
| `warm-all-lru` total prefills at this cell | 1,684 (re-run) | 1,684 | `patch1_byte_identity_proof.json` | 1.00 | **yes, exact: the re-run used to explain the gap reproduces the committed arm first** |
| the RATIO per-frame / batch-30s in prefill pieces | 3.52 (`v5-rules`, 8 devices, 600 s) | 3.27 (`warm-all-lru`, 8 devices, 300 s) | `reports/study_perframe_upload.md`, commit `34a4af0` | 1.08 | **yes, and it is an independent arm, cell length and author** |

**The 2.04x is investigated and explained, and the explanation is measured rather than argued.**
It is not the same quantity measured twice: `warm-all-lru` offers EVERY session as a candidate,
`v5-rules` offers robot sessions only (section 0), so the two arms ask for different things by
design. Re-running the committed `warm-all-lru` at the identical cell and classifying its own
prefill rows by session gives **1,684 = 754 robot + 930 single-shot + 0 dashcam**. So:

- the re-run reproduces `warm-all-lru`'s committed 1,684 exactly, which is the positive control on
  this explanation rather than on the arm;
- **the whole of the gap is the 930 single-shot prefills `v5-rules` deliberately does not make**,
  and it confirms the design reason given in section 0 from the other side: a single-shot session's
  one image is captured at question time, so `warm-all-lru` warms it in the ~2 s between its batch
  and its question, which is warming a session that is about to ask, not warming ahead of a
  history;
- on the comparable robot half the two agree at **1.10x** (827 against 754), the residual being
  the different base (`b7-edf-feasibility`, 13,570 decisions, against `hybrid-F-lhreq-noc3`,
  13,525) and nothing else.

**No committed value is superseded or recomputed by this run.**

**2. Physical plausibility.** No latency, throughput or size is measured, so there is no implied
rate to compare against `results/cost/cost_matrix.csv`. The one derived quantity, the reused
prefix in tokens, uses `bodies.epg_prompt_tokens`' own committed 338 tokens per image and is
reported as a LOWER bound because the engine rounds reuse to block boundaries. The committed
EP-G law `prompt_tokens = 42 + 338 n` is re-derived in `study_epg_bodies.md` from 3,898 committed
32B records and is taken from there, not re-measured.

**3. Distribution sanity.** Per-recall values are reported individually, not as a median, in
`cached_token_proof.paired_on_shared_recalls.per_recall` and `base/v5_rules.per_recall`. The
recalls vary as their inputs do: 60, 75, 75, 120, 225 and 270 frames, `est_tokens` 5,431 to
24,331, so no constant appears where a distribution is expected. **The one place a constant DOES
appear is flagged in section 3**: `deadline_work_at_risk` is False in 12,001 of 12,001 epochs, and
it is classified unexercised rather than reported as a working discipline. The two arms' EP-G
dashcam counts are identical (4,332 bytes / 39,351 references / 3,864 requests for both), which is
expected and is itself proof (b) of `study_epg_bodies.md` holding here: the dashcam channel is
untouched by this arm.

**4. Definition audit.**

| object | definition used in this run | matches prior? |
|---|---|---|
| a warm-ahead **prefill** | one `release_piece` / `release_whole` row in `decision.jsonl` | yes: `arms_warmall.proofs` proof 3 uses the identical predicate |
| a warm-ahead **ask** | one `SessionAction(MATERIALIZE)` emitted, per candidate per epoch | yes, and kept in a separate column with its own name |
| the **base** | `HybridArm(**CONFIGS["hybrid-F-lhreq-noc3"])` | yes: reproduces its committed digest exactly |
| a **differing decision** | `test_hybrid._differing_setwise` | yes, the committed helper, with the positional count beside it |
| **EP-G** | `dashcam_format="epg"`, append-only, fresh context every 21 frames, floor 3 | yes: `trace.EPG_MIN_FRAMES = 3`, and D153's refresh is PROVISIONAL as `trace.EPG_REFRESH_NOTE` already records |
| **robot deadline** | 5.0 s in cell A, 3.0 s in cell B, each labelled | the 5 s is the committed default (`data_sources.py:43`), the 3 s is D147's ruling; the two are never mixed in one comparison |

**5. Claim linkage.** The three proofs bear on D150 STATE lever 1 and spec v5 section 8 ("warm", a
prefill that puts a history on the GPU) and on D152 (3) ("in v2, warming ahead makes full history
the normal path at question time"). Proof 2 **supports** D152 (3) in the dry register: the full
history is the normal path and it arrives as a reused prefix. The admission difference **supports**
D147's stated reason for the 3 s deadline, that warming ahead becomes necessary. Nothing here
bears on the D151 (6) gate, on `MARGIN_CF`, or on any counterfactual claim, because this arm makes
none - which is the point. **Nothing measured here is scoped out by FORMULATION.md**: no KV is
moved between tiers (the arm emits no placement action at all) and no cross-architecture KV
transfer is involved.

**6. Proxy validity.** One proxy is used and it is the headline of proof 2. **Stated:** frames sent
as uuid-only references in the recall body are used as a proxy for the engine's cached tokens.
**What it actually measures:** how much of the request's prompt prefix the engine has already been
sent on an earlier request. **Validity:** it is a necessary condition for a cache hit and not a
sufficient one, and it is a LOWER bound because the engine rounds to blocks; it also cannot see a
block the engine has since evicted, which is exactly what vLLM's LRU may do and what no dry run
can observe. **So it is valid for the claim "the warmed history's prompt was already sent", which
is what is claimed, and it is NOT valid for "the engine served it from cache", which is not
claimed.** The engine-side confirmation is owed by the H100's cell, and until it lands the
cached-token proof is marked **unvalidated on the engine axis** and must not be cited as a
measurement of cached tokens.

**7. Validate the control, not only the result.** Two controls, both audited before the comparison
was read:

- **Positive control (a known-good committed arm must pass the check being applied):** the base
  reproduces its committed digest `5d3469549fead8ac`, 13,525 rows, D2 372 / RECENT 0, and 5
  feasibility actions. It passes exactly. Had it failed, **the check would be broken and not the
  arm**, and nothing in this report could be read.
- **Negative / `-off` control:** byte-identical to the base with 0 prefills, section 4.
- **A register trap found and fixed while checking the control.** The first run reported the
  base's release-readiness split as an EMPTY DICT, which reads as "the base released nothing
  warm". It means "the base was never counted": the base is a plain `HybridArm` and does not carry
  that counter at all. The comparator is now `v5-rules-off`, which is byte-identical to the base
  AND carries the counter, and the "not instrumented" fact is reported as its own field. This is
  the shape CLAUDE.md check 7 names: a side of the comparison that was never audited.

---

## 7. For the operator, before the cells run

1. **Pass `--robot-deadline-s 3`.** The committed default is 5.0 (`fleet/data_sources.py:43`,
   `run_live2_real.py:92`) while D147 rules 3 s. A `v5-rules` cell at the default silently measures
   the arm in the regime where warming has least to buy, and nothing in the output says so.
2. **Pass `--dashcam-format epg`.** The arm needs no flag for EP-G and takes it off the wire, but
   the trace does.
3. **Decide the upload contract explicitly and label the cell with it.** Per-frame upload landed at
   `34a4af0` behind `--robot-upload per-frame`, default `batch-30s`, and `v5-rules` picks it up
   with no change (proof 4). A `v5-rules` cell run at the default is a `batch-30s` cell and must
   be labelled `upload-30s` per D154 (4), which also means it is **not** the contract D154 (4)
   asks for. Note what the choice costs: `v5-rules` issues 3.52x the prefills under per-frame, so
   the accelerator load of this arm is contract-dependent, and `34a4af0` names exactly this arm
   as the one to watch at 32 devices.
4. **The registered arm name is `v5-rules`**, and `arms.make_arm("v5-rules")` builds it with only
   the harness's own path set up (verified after the final rebase). `v5-rules-off` and
   `v5-rules-noyield` are also constructible; **`-noyield` is in no run plan**, per
   `study_engine_actions.md` section 1 point 4. None of the three is in `ARM_NAMES`.
5. **W2's yield is unexercised in dry runs** (section 3). The H100's cell is where it can first be
   observed; report `warm_ahead_yielded_epochs` from the live run.
6. **The engine-side cached-token confirmation is owed** (check 6). `cache_path` and
   `cached_tokens` from the live run are what close proof 2 on the engine axis.
7. **D156 is owed a design-log row** (section 0).
8. **A forward risk the cells will not show tonight, recorded now.** Because warming makes a long
   history feasible, `v5-rules` ADMITS histories its base declines: in cell B the two extra
   recalls carry 20,281 and 24,331 tokens, against a 32,768 context. That is comfortably inside it
   at seeds 4 and 5, which is what the H100 runs. It will not be at **seed 0**, where D144 (3)
   records LH-REQ session 1848337166005249 at 33,839 tokens and rules the over-context request a
   per-question MISS for whichever arm sends it. So `v5-rules` is the arm most likely to send it,
   by design rather than by accident, and a seed-0 cell should expect that miss and charge it
   rather than treat it as a fault.

---

## 8. NOT COMMITTED: the permission classifier refused it, twice

**The work is finished and staged; it is not on origin.** `git commit` was refused by the Claude
Code auto-mode permission classifier on two attempts, the second in the plainest possible form
(message from a file, no config overrides, four staged paths, `git diff --cached | grep "^-[^-]"`
empty, so the commit deletes nothing). I stopped there rather than looking for a way around it,
which is what `34a4af0`'s own message records the three previous sessions tonight doing: "Third
session tonight to be refused and to stop rather than work around it; all three were right."

**State left for the user**, in the detached worktree at `/tmp/claude-1001/v5rules` (HEAD
`df586a0`):

- the four paths are **staged**, so one `git commit` finishes it;
- the proposed message is committed-ready at
  `results/orchestration/live2/v5rules/commit_message_draft.txt`, on the precedent of
  `results/orchestration/live2/covex_harden/EXPERIMENTS_row_draft.md`;
- **origin has since moved to `34a4af0`**, so the sequence owed is: fetch, rebase, **re-run the
  three import checks after the rebase** (they pass at `34a4af0`, verified in a second worktree),
  then push `HEAD:main`.

The post-rebase import checks and proof 4 were run in a second detached worktree at `34a4af0`,
holding a byte-identical copy of the arm. **That worktree has been removed** (`git worktree
remove`), because the disk is at 99 percent with 63 GB free and a worktree left pinned is what
filled it to 100 percent before; its 2.8 GB is back. Its results are saved in
`results/orchestration/live2/v5rules/v5_rules_perframe_pickup.json`, labelled with the sha they
were measured at, and `perframe_pickup()` reproduces them in any tree at `34a4af0` or later.
`/tmp/claude-1001/v5rules` is still pinned and holds the staged work; it should be removed after
the push.

---

## 9. Rule 2 classification

There is no null here to classify: all three proofs and both protocol steps passed, with the
mechanism present, non-zero and varying as the claim requires, and with the negative control
changing the result. **The one quantity that is constant, W2's yield, is classified
`unexercised`** and is reported as such rather than as a working discipline. Nothing in this report
is a settled finding about whether `v5-rules` beats its base on any outcome: no outcome was
scored, and scoring is the H100's.
