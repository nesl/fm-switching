# StudyV5-ENGINE: engine actions, the belief corrector, and the WARM-ALL baseline

Session C of the policy v5 effort, flash, 2026-11-20. Artefacts:
`experiments/orchestration/live2/engine_actions.py`,
`experiments/orchestration/live2/arms_warmall.py`,
`results/orchestration/live2/v5/engine_actions_unit.json`,
`results/orchestration/live2/v5/engine_actions_warmall_proofs.json`.

Source decisions: D148, D149, D150, D151, D152, and `research/policy_spec_v5.md` sections 8, 10
and 15. Everything read for this report was read from a detached worktree at `origin/main`
(`70630f1`); the flash working tree is at `17bdf15`, **454 commits behind**, and does not contain
D106 to D152 or any of the reports cited here. That is spec v5's gap G2 and it is unchanged.

**REGISTER, first, because two numbers in this report are in different ones.** Nothing here is a
MEASURED latency, quality or capacity result. The arm proofs are DRY decision-path runs with a
stub bridge and no engine, so they are counts of decisions, never of seconds. The smoke test in
section 6 is a CODE SMOKE TEST ON A SUBSTITUTED STACK and is not evidence about anything.

---

## 1. Interface note for session B (the counterfactual), stable as of this commit

This section is the one session B is blocked on. The signatures below are stable; the rest of
this report is why they are shaped that way.

```python
# experiments/orchestration/live2/engine_actions.py

ENGINE_ACTIONS_VERSION = "v5-engine-actions-1.0"
W2_LAXITY_FRACTION       = 0.3      # D143 ruling B, the policy's own committed at-risk test
WARM_AHEAD_SLICE_TOKENS  = 1024     # "small pieces": one piece per session per epoch
WARM_AHEAD_TARGET        = 10 ** 9  # coordinator._advance_build clamps this to est_tokens

@dataclass(frozen=True)
class WarmAheadPlan:
    actions:        Tuple[SessionAction, ...]   # what may legally be emitted
    wanted:         Tuple[str, ...]             # every candidate session
    legal:          Tuple[str, ...]
    unexpressible:  Tuple[str, ...]             # wanted but refused by validate_action
    yielded:        bool                        # W2 declined to start a prefill this epoch
    reason:         str
    n_warm_ahead -> int                         # the characteristic decision count

known_sessions(obs)                                  -> set[str]
deadline_work_at_risk(obs, targets=None,
                      laxity_fraction=0.3)           -> bool
plan_warm_ahead(obs, candidate_sessions, *,
                slice_tokens=1024,
                yield_to_deadline=True,
                targets=None)                        -> WarmAheadPlan
plan_warm_reactive(obs, *, slice_tokens=1024,
                   yield_to_deadline=True,
                   targets=None)                     -> WarmAheadPlan   # LEGAL FALLBACK, 4.2
touch(session_id)                                    -> SessionAction          # KEEP_GPU_WARM
plan_reload(obs, session_ids, *, slice_tokens=None)  -> (list[SessionAction], list[str])
slice_plan(tokens_to_build, slice_tokens)            -> list[int]
hold_back(obs, session_id, tokens_to_build,
          gpu_kv_tokens, *, due_within_s=120.0)      -> (bool, str)

EXTERNAL_HIT_KEYS: tuple[str, ...]                                            # UNVERIFIED
external_cached_tokens_of(usage)                     -> Optional[int]

@dataclass
class BeliefUpdate:
    session_id: str; before: str; after: str
    cached_tokens: Optional[int]; prompt_tokens: Optional[int]
    changed: bool; reason: str; external: Optional[int]

belief_update_from_cached_tokens(session, cached_tokens, prompt_tokens=None,
                                 now=None, external_tokens=None) -> BeliefUpdate
unit_proof() -> dict
```

**Five things session B must build against, each of which would otherwise be found late.**

1. **`plan_warm_ahead` returns what it WANTED as well as what it may say.** It does not silently
   drop the illegal half. `unexpressible` is non-zero on the committed harness today (section 3),
   so a counterfactual that scores warming must read `n_warm_ahead` and `unexpressible`
   together; scoring `n_warm_ahead` alone reads the blocker as a policy decision.
2. **`WarmAheadPlan.n_warm_ahead` counts prefills AHEAD of a question only.** A MATERIALIZE for a
   session that already has a pending query is reactive warming, which edf and llf already do and
   which `study_frozen_test.md` 15.4 measured as the question paying the whole warming latency
   (edf waits 5.483 s at the median before release against a 5 s deadline). It is deliberately
   excluded from the count, so the two kinds of warming can never be added together by accident.
3. **"Lowest priority" is expressed by WHEN the action is emitted, not by a field.** The session
   action space has no priority, and `Action.notes["priority_ms"]` is read only for per-item
   submissions (`coordinator._enact`). Yielding is therefore the whole of the discipline, which is
   why `WarmAheadPlan.yielded` is reported rather than inferred.
4. **W1 is not built and must not be added.** `study_frozen_test.md` 16.3 point 5: W1's worst
   single-shot queue wait is 3.746 s against a 2 s deadline, longer than the deadline itself, and
   16.1 states that calibration understates warm and build service by 1.5x to 3.7x, so a real
   engine is worse than that table. `warm-all-lru-noyield` exists as an ablation and is in no run
   plan.
5. **`slice_plan` applies to BACKGROUND WARMING ONLY**, never to a deadline request (D151 (3),
   spec v5 section 15). Nothing in this module slices a recall.
6. **`plan_warm_reactive` is NOT `plan_warm_ahead` and the two must never be summed.** It builds
   the history of a session that already has a pending question, which is legal today and is what
   `warm-all-lru-reactive` uses (section 4.2). The question pays the materialisation, so it
   cannot be cited for warming's effect on on-time. Its count is named `warm_reactive_emitted`
   for that reason.

**What the objective sees.** These actions change `P(on time | warm) - P(on time | cold)` for the
sessions they touch and the `harm` term for everyone else; they do not change accuracy. They are
scored by reader 2 (`v5/value_readers.py::warm_keep_reader`), not here: this module decides
nothing about value and contains no cost curve.

---

## 2. The four levers, and what each one is grounded in

| lever | function | the READ that makes it act | status |
|---|---|---|---|
| warm | `plan_warm_ahead` | `coordinator._enact` -> `_advance_build` (`coordinator.py:435`, `:530`) | **blocked, see section 3** |
| touch | `touch` | `coordinator._enact` sets `desired_tier="gpu"`; `cstate.enact_placement` refreshes `last_touch_s` and sorts a keep-warm request LAST in the eviction order | live |
| reload | `plan_reload` | same build path, gated on `obs.cloud.host_warm_sessions` | **no observed trigger state** |
| hold back / slice | `hold_back`, `slice_plan` | the arm withholds the MATERIALIZE; the read is the absence of the action | live |

**Reload has no observed trigger state, and this is the correction to what I reported earlier
today.** I wrote that `belief["host"]` is never assigned non-zero anywhere. That was wrong in
detail: `cstate.py:169` does assign it, and `set_tier("host", now)` is reachable at `cstate.py:447`
and `:486` on a complete build. The question that matters is whether it ever fires, and across all
39 committed 16-device cells the believed tier is **cold 14,472, gpu 1,442, host NEVER**. So the
branch exists in code and no committed run has reached the state in which a reload is the right
action. `plan_reload` is built and counts its own firings; an arm reporting zero reloads has
reported the state of the fleet, not a defect, and **reload-from-host must not be scored as a
mechanism that failed.**

**Touch is a real read and is named carefully.** `desired_tier` is CLAUDE.md's own write-only
example, and it was write-only until D133 Part A. It is read now, in `cstate.enact_placement`'s
eviction sort. It still does not pin anything: vLLM cannot pin KV (D150), and the function is
called `touch` rather than `keep` for that reason.

---

## 3. The blocker: warming ahead is not expressible in the committed action space

**Step 0 found this before the sweep, which is the whole reason the protocol exists.**

`interface.validate_action` accepts a `MATERIALIZE` only for a session in

```
gpu_warm_sessions | host_warm_sessions | {q.session_id for q in obs.recall}
```

A session that has uploaded frames, has no pending question, and has never been built is in none
of the three. So the FIRST warm-ahead prefill of every session is rejected, and after the
rejection the session is still cold, so it is rejected again for ever. Probed directly rather
than read off the source:

| probe | result |
|---|---|
| MATERIALIZE a session with no pending question and no warm belief | **REJECTED**: `action names unknown session 'robo001_s000'` |
| the same action once the session is believed GPU-warm | ACCEPTED |

**Why no committed arm has met this.** Every committed emitter of MATERIALIZE names
`q.session_id`: `arms.py:277`, `arms.py:413`, `arms_builder.py:317-320`, `arms_policy.py:1042`.
All of them warm REACTIVELY, at the question. That is exactly the behaviour
`study_frozen_test.md` 15.4 measured for edf and llf, and its conclusion was that **when you warm
decides who pays**: warming on demand puts the materialisation inside the deadline, warming ahead
of arrival does not. The offline P1 to P3 policies of sections 15, 16 and 19.4, which reach 65 of
65 robot questions at the committed capacity against P0's 25 at a 3 s deadline, all warm ahead of
arrival on batch events. **None of them is currently expressible as a live arm.**

Under CLAUDE.md Rule 2 the correct classification of a WARM-ALL null today is **unexpressible**:
the mechanism fires and the harness discards the channel it acts through. It is not a negative and
it is not a finding.

### 3.1 PATCH 1, requested: widen the known-session set

Owner: the coordinator / interface owner. Three edits, none of them mine.

All three anchors below were verified character for character at `origin/main` `f9da42a`, and
`interface.py` already imports `Tuple`. (Worth saying because my first attempt at patch 2 missed
on whitespace: the anchor text in a report is not the anchor text in the file until it has been
checked against the file.)

**(a) `experiments/orchestration/baselines/interface.py`**, in `Observation`, **after line 156**
(`device_always_warm: bool = True`), add one field with a default so every existing construction
is unchanged:

```python
    device_always_warm: bool = True
    # A session the coordinator already holds uploaded frames for is a CAUSALLY KNOWN entity: it
    # exists, it has uploaded, and nothing about it is in the future. Naming it is therefore not a
    # future-knowledge leak, which is what `known_sessions` in `validate_action` guards against.
    live_sessions: Tuple[str, ...] = ()
```

**(b) `experiments/orchestration/baselines/interface.py`**, in `validate_action`, **lines 272 to
273**:

```python
    known_sessions = (set(obs.cloud.gpu_warm_sessions) | set(obs.cloud.host_warm_sessions)
                      | {q.session_id for q in obs.recall})
```

becomes

```python
    known_sessions = (set(obs.cloud.gpu_warm_sessions) | set(obs.cloud.host_warm_sessions)
                      | {q.session_id for q in obs.recall} | set(obs.live_sessions))
```

**(c) `experiments/orchestration/live2/cstate.py`**, in `CoordState.observation`, in the
`return Observation(...)` call at **lines 585 to 588**, add:

```python
                           live_sessions=tuple(sorted(k for k, v in self.sessions.items()
                                                      if v.open)),
```

**Is this a methodological change?** It widens the action space, which engages fairness rule 4, so
it is the user's call and I am not treating it as an implementation fix. But it is
**decision-preserving for every committed arm, and that is checkable rather than asserted**: no
committed arm names a session outside the current set (the four emitters above all use
`q.session_id`), so no committed arm's log can change. The proof to run beside the patch is a
byte-identity check of the prescreen digests before and after, which the existing
`baseline_prescreen.py` already produces.

**What I did instead of applying it.** `arms_warmall.proofs()` runs the cell in BOTH conditions,
the committed harness and a shim that emulates the patch in-process without editing any file. The
difference between the two columns in section 4 is the measurement of this blocker.

**One self-inflicted warning, recorded because it is the same shape as the faults CLAUDE.md
collects.** The shim's first version patched `validate_action` only and produced ZERO warm-ahead
prefills, identical to the blocked condition, because the arm asks `engine_actions.known_sessions`
and self-censors before emitting. A shim that removes only half a blocker produces a zero
indistinguishable from the blocker it was built to remove. The patch above has the same two
halves for the same reason, and a reviewer applying only (b) will see no change.

### 3.2 PATCH 2, requested: wire the dead `cached_tokens` read (G9, D150)

Owner: the coordinator's owner. `SessionRec.last_telemetry_cached_tokens` is **declared at
`cstate.py:98` and has no write and no read anywhere in live2**, which is one step worse than the
write-only `desired_tier` CLAUDE.md names. `coordinator._collect` already HAS the value and
passes it only to a log.

**A MEASURED CORRECTION THAT CHANGES WHAT THIS WIRING CAN ACHIEVE, and it arrived from the
coordinator side before the wiring was committed.** The telemetry is written in exactly one place,
`coordinator.py:756`, and it goes to the RESIDENCY LOG, not to the session: `_log_residency(t,
s.session_id, telemetry=cached_tokens)`, inside `_settle`'s **history-build branch only**. So it
never observes any traffic but history pieces. Measured: it is positive in **none of 18,738
residency rows across 45 cells**, while five cells report **424,000 to 513,000** engine prefix
hits. The reading that the write is broken is WRONG and was checked before being reported: on the
slice it does cover, the zero is honest. `backend.cached_tokens_of` is careful in the same
direction, returning None rather than 0 when the field is absent, with a comment that a zero
"would be read as a confirmed cold path and D81's WARM / COLD tag would then be a fabrication".

**Consequence, stated before the patch rather than discovered after it: wiring this field will not
by itself make the belief track residency, because the field does not observe the traffic where
the reuse happens.** It is wired because D150 pre-registers it and the user ruled it, and it is
instrumented below so that ineffectiveness is visible rather than silent.

Two things follow for the patch as specified, and both are why the call site is `_collect` and not
`_settle`'s build branch:

* **`_collect` sees every kind, so it sees RECALL requests too**, which is where a built history
  offers its whole prefix and where reuse is therefore detectable at all. Wiring only the build
  branch would reproduce exactly the blind spot measured above.
* **Monitors are excluded BY CONSTRUCTION, and that is correct rather than a gap.** A dashcam
  monitor is submitted with `session_id=None` (`coordinator._serve_monitor`), so there is no
  session belief for it to correct. The belief is about session histories; monitor hits belong to
  the engine's own counters and must not be folded into it.

**THE BETTER ANCHOR FOR THIS WHOLE MODULE is the gap the committed code already names**, which is
documented rather than hypothetical. `coordinator.py:745-752`: a partially built history keeps a
COLD readiness while the built prefix **is** still reused on the wire as uuid references, so "the
request is cheap even while the readiness the arm sees says COLD; that gap is a limitation of the
committed action space and is reported." That is precisely the gap v5's engine actions exist to
close, and it is a stronger starting point than the telemetry field.

**So Step 2's evidence for this link is NOT "the read is wired".** It is: the new read changed a
belief, on traffic that actually carries reuse. If the only session-bearing requests it sees are
history pieces that are genuinely cold, the correct report is that the link is **unexercised**
under CLAUDE.md Rule 2, not that a mechanism was wired.

**File:** `experiments/orchestration/live2/coordinator.py`.

**Edit 1**, after **line 56** (`import scores as S2`, whose trailing whitespace before the
`# noqa` differs from the neighbouring imports, so insert by line number, not by matching text):

```python
import engine_actions as EA                                              # noqa: E402
```

**Edit 2**, in `_collect`, immediately after line 696:

```python
            path, frac = SC.cache_path_of(ct, pt)
```

insert:

```python
            # D150 / spec v5 section 8: the engine's OWN per-request cached-token count corrects
            # the residency belief. Until this read existed the belief was a prediction with no
            # correction, which is the write-only shape CLAUDE.md names. The corrector refuses to
            # act on a monitor (no session) and on a None (no usage block is NO EVIDENCE, not a
            # miss), both of which it distinguishes internally.
            if sub.session_id:
                _s = self.st.sessions.get(sub.session_id)
                if _s is not None:
                    _bu = EA.belief_update_from_cached_tokens(
                        _s, ct, pt, now=t,
                        external_tokens=EA.external_cached_tokens_of(usage))
                    self.counts["belief_corrections"] += 1
                    if _bu.changed:
                        self.counts["belief_corrections_changed"] += 1
                        self.counts["belief_to_" + _bu.after] += 1
```

**Why `_collect` and not `_settle`.** `_settle` does not receive `prompt_tokens`, and the guard
that stops a 378-token dashcam monitor from demoting a 5,000-token history needs it. `_collect`
has both `ct` and `pt` in scope at that line.

**Ordering is deliberate and must not be changed.** This runs BEFORE `_settle`, so a build that
has just completed still promotes the belief to gpu afterwards (`_settle`'s
`if s.built_tokens >= s.est_tokens`), which is correct: a build that just finished IS resident.
The correction therefore bites on the RECALL path, which is where it matters, because
`study_frozen_test.md` 17.3 shows the frozen grid turning its 62,944-token pool over **89 times in
1,200 s**: a belief formed at build time is stale within seconds and nothing told it.

**THE PROOF YOU ASKED FOR, and it is the one that decides whether this is a read or another dead
field.** Run after applying: the run's `counts` must carry
`belief_corrections_changed > 0`. A corrector that only ever confirms the existing belief is a
write-only field wearing a read's clothes, and `BeliefUpdate.changed` exists so that it cannot
hide. The unit proof already shows the function changes a belief in 3 of its 7 cases
(`results/orchestration/live2/v5/engine_actions_unit.json`, `step2b: PASS`); what the run proves
is that the CALL SITE reaches it on real traffic.

### 3.3 PROVISIONAL, and it must be carried into every report that reads this belief

> **The belief says COLD where HOST is likely resident under write-through.**

The deployment stack runs `--kv-offloading-backend native --kv-offloading-size 27`. A block
evicted from the GPU may still be on the host tier while the engine reports `cached_tokens = 0`
for a GPU lookup. The corrector therefore says cold where host is likely, which is the
CONSERVATIVE direction for cost (a host reload is charged as a cold rebuild) and the WRONG
direction for a reload decision. `external_cached_tokens_of` is the separate channel the user's
ruling asks for, and **its key list is CONSTRUCTED, not read off a running engine**: nothing on
this box runs vLLM 0.31.0 and no install is permitted. The first H100 run on the deployment stack
must dump one raw usage block and confirm or replace `EXTERNAL_HIT_KEYS`. Until it does, every
"cold" this corrector writes may be a host hit.

**Per the user's ruling, no belief promotion rule and no policy behaviour was changed overnight.**
Session A's spec settles that. This report adds a read and a requested patch; it changes no arm
except the new one.

---

## 4. WARM-ALL + LRU: the arm, and its four proofs

**Registered name: `warm-all-lru`.** Plus `warm-all-lru-off` (the Step 4 negative control) and
`warm-all-lru-noyield` (the discipline ablation, in no run plan).

**What it is.** The live counterpart of P1 in `study_frozen_test.md` 15.1, 16.2 and 19.4: prefill
every uploaded batch on arrival, let the harness and the engine evict by their own LRU, and do no
value reasoning at all. Base `b7-edf-feasibility`, unchanged, plus one channel. It emits **no**
KEEP_GPU_WARM, OFFLOAD_TO_HOST or EVICT, because "let vLLM evict by its own LRU" means the arm
emits no placement steering at all, and `cstate.enact_placement`'s order is then
least-recently-touched, which IS LRU. An arm that also steered placement would not be the P1 of
sections 15 and 16.

**Why it is a calibration instrument before it is a baseline, and the reason is sharper than
G10 records.** Spec v5's G10 says warm requests are SCARCE: 720 of 304,867 committed requests,
all in two cells at one seed. Measured on the coordinator side the count is 1,797 of 345,066, and
scarcity is not the binding problem. **Warm is CONFOUNDED WITH ARM.** edf at n16 s4 carries 358
gpu beliefs and 512,992 engine prefix hits and llf 362 and 424,224, while b7 and hybrid-F-lhreq
carry **zero of both**. Arms that rebuild histories go warm; arms that do not never do. So the
warm coefficient is fitted entirely on edf and llf and then applied to arms that never go warm,
and a by-arm held-out split has zero warm rows **by construction**. `study_frozen_test.md` 16.1
measures the same hole from the other side: f was fitted on arms whose every request is cold, and
on the warm side the model is out by 1.5x on builds and 3.7x on warm single-shot.

**More cells of the existing arms cannot fix this.** Identifying the warm regime out of arm needs
an arm that goes warm AND cold under the SAME policy, and WARM-ALL is the only way to get one.
That is why its proof is a PAIR and not a single count: the warm-ahead prefills it makes, and the
readiness split of its own released recalls. A WARM-ALL that released everything warm would be as
useless to the gate as b7, which releases everything cold. Proof 3 below reports both, and the
`both_states` verdict fails loudly if the arm turns out to sit in one regime.

**One design note worth stating, because it removes a detector that could be wrong.** The arm does
not try to work out which sessions have unbuilt frames: the D100 roster carries
`built_tokens_by_session` but no history size, so there is no local test for "fully built". It
does not need one. `coordinator._advance_build` clamps the target to `est_tokens` and returns None
when `new_refs` is empty, so a standing request for every session is a no-op for every session
with nothing newly uploaded, and the GPU is charged only for pieces actually issued. Asking every
epoch IS "prefill every uploaded batch on arrival", expressed without a batch-arrival detector.

### 4.1 The four proofs

Cell: seed 4, 16 devices, 1200 s, `40:40:20`, `lh_req` / `ss2`, DRY (stub bridge, no engine).
Run in BOTH the committed harness and a harness with patch 1 shimmed in. Artefact:
`results/orchestration/live2/v5/engine_actions_warmall_proofs.json`.

**Consistency check 1 / the POSITIVE CONTROL first, because nothing below may be read if it
fails.** `study_frozen_test.md` 13.4 records b7 at this cell with 5 feasibility actions; this
harness gives **5**, and 13,570 decisions against 13.4's **13,570**. The control reproduces its
committed behaviour, so the check is sound.

| # | proof | committed harness | patch 1 shimmed |
|---|---|---|---|
| 1 | **well-formedness** | completed, **0 illegal actions**, 13,570 decisions | completed, 0 illegal, 12,648 decisions |
| 2 | **fairness digest vs base** | base `67c8da30`, control `warm-all-lru-off` and treatment both `ae20da06`. **Control is byte-identical to the base once `arm_version` is removed: see 6c** | treatment `8c4420ad` |
| 3 | **characteristic decision** (prefills ISSUED) | **0**, base 0. Arm asked 2,289,557 times and was **rejected 2,289,180 times** | **2,603** |
| 3b | **both states under one policy** (belief-level) | COLD 372 only, 1 regime | COLD 358, **GPU-WARM 19**, 2 regimes |
| 4 | **Step 2b decision diff vs base** (setwise) | **0, an ABSENT LINK** | **6,134**; first differing row is a `release_piece`, 301 tokens, t = 0.1 s |

**Proof 3 is the one that does not pass, and it does not pass for the reason section 3 predicted.**
0 prefills issued on the committed harness against 2,603 with the channel open. Under CLAUDE.md
Rule 2 this is **unexpressible**: the mechanism fires 2,289,180 times and the harness discards
every one. **It is not a negative and `warm-all-lru` must not be scored until patch 1 lands.**

**Proof 2 needed a correction, and it is the same shape as the faults CLAUDE.md collects.** The
first run reported `control_identical_to_base: false` with a POSITIONAL diff of 13,570 of 13,570
rows and a SETWISE diff of **0**. The cause is a label: `test_hybrid.STRIP` removes `arm`,
`decision_latency_ms` and `decision_id` but **not `arm_version`**, which the coordinator writes
into every decision row, so any new arm differs from its base in every row on its own version
string. A control that looks destroyed by a version label is check 3's artefact spread exactly:
a difference of the right size and the wrong meaning. The digest now strips `arm_version` and
reports the unstripped comparison beside it; section 6c carries the dedicated re-check.

**Two things in this table are worth reading that are not proofs.**

1. **The shimmed cell has FEWER decisions, 12,648 against 13,570.** Warming is not free: it
   spends GPU budget and displaces about 900 dashcam monitor releases. That is the contention
   `study_frozen_test.md` 16 modelled, appearing here as a decision-count difference rather than
   a latency, and it is the reason the live cell must report the dashcam side too.
2. **W2 yielded on ZERO epochs at this cell**, in both conditions, so the discipline is
   **UNEXERCISED here** and this cell cannot be cited for it. It fired 3 times on the 8-device
   300 s cell, so the branch is reachable. Marked rather than reported as a pass.


### 4.2 `warm-all-lru-reactive`: the legal fallback, and why it exists

**Built because the H100 is holding a boundary slot and the arm it is holding it for cannot make
its own decision yet.** Without patch 1, `warm-all-lru` issues ZERO prefills and is behaviourally
b7, so queueing it would spend a slot reproducing b7's cells and would return zero warm rows,
which is precisely the thing the gate needs and does not have. This arm is the thing that can run
tonight.

**What it does.** It slice-builds the history of a session that **already has a pending
question**. That session is in `obs.recall`, so `validate_action` accepts it today with no patch.

**All four proofs PASS at the committed cell** (seed 4, 16 devices, 1200 s, `40:40:20`,
`lh_req` / `ss2`, dry). Artefact:
`results/orchestration/live2/v5/engine_actions_warmall_reactive_proofs.json`.

| # | proof | result |
|---|---|---|
| 0 | positive control (b7 feasibility actions) | **5 against a committed 5, AGREE** |
| 1 | well-formedness | completed, **0 illegal actions**, 14,222 decisions |
| 2 | fairness digest vs base | base `67c8da30` / 13,570 decisions, treatment `c1a3c261` / 14,222 |
| 3 | **characteristic decision** (prefills ISSUED) | **645**, against the base's **0**. W2 yielded on **15** epochs, so the discipline fires here |
| 4 | Step 2b decision diff vs base (setwise) | **1,394** |

Shakedown at 8 devices / 300 s for comparison: 94 prefills against the base's 0, 3 W2 yields.

**Two caveats on the table, both mine.** The belief-level readiness split is COLD only (635 of
635), for the structural reason in 6b.0. And the base's own readiness split is blank in the
artefact because that instrumentation lives in this arm's class and b7 does not have it;
`warm-all-lru-off` is the arm to read it from, and it is COLD-only too.

**WHAT IT IS NOT, and this must travel with every number it produces.** It is **not warming
ahead**. The question pays the materialisation, which is exactly what `study_frozen_test.md` 15.4
measured as edf's 5.483 s median wait against a 5 s deadline. **It therefore cannot show that
warming helps on-time and is not offered for that.** Its characteristic decision is counted under
a different name, `warm_reactive_emitted`, so it can never be added to a warm-ahead count.

**What it IS good for, and it is the one thing the gate actually needs.** A sliced build reuses
its own prefix on the wire as uuid references, so piece k+1 reports `cached_tokens > 0` while the
readiness the arm sees still says COLD. That is section 6b's measured mechanism: 72 of the 95
positive telemetry rows across 213 committed logs are on the piece-chaining arms and none are on
an arm that rebuilds whole. So this arm produces **warm and cold ENGINE rows under one policy**,
which is what identifies the warm coefficient out of arm, and `cost_model_gate.py:88` reads
exactly that quantity.

**The honest limit, stated rather than left for a reader to find.** Its belief-level readiness
split is COLD-only (94 of 94 above), because the belief promotes only on a complete build. The
warm rows are at the **engine** level and a dry run cannot see them. **So this arm's value to the
gate is a PREDICTION, resting on the 72-of-95 precedent, and the first live cell either confirms
it or does not.** If its live `cached_tokens` distribution turns out to be degenerate, it has not
unblocked the gate and that is the finding.

---

## 5. Mechanism verification (CLAUDE.md), recorded before any sweep

**Step 0, what would make this run uninterpretable, asked before it started.** Four questions, and
one of them came back "stop". (i) Is the comparator about to change? No: b7 is the committed
control and its digest is reproduced in the same harness as the positive control. (ii) Does a run
I depend on key into my analysis? No; these are dry decision-path runs. (iii) Is a default about
to be restored? No. (iv) **Does the mechanism have a reachable path at this size and in this
regime?** **NO.** Warming ahead of a question is rejected by `validate_action` (section 3). That
answer cost one probe and about a minute, and it arrived before the sweep rather than after a
null.

**Step 1, the causal chain.** If a robot history is resident on the GPU when its question arrives,
the question is served warm rather than cold (`study_frozen_test.md` 15.4, MEASURED: warm TTFT p50
0.384 to 0.423 s against cold 2.44 to 3.10 s); at D147's 3 s deadline a cold history essentially
cannot be answered in time (19.1: every arm fails; 19.2: of 282 sent misses at 3 s, 282 had a cold
history and 0 had a warm one), so residency decides on-time, and under D152 (1) on-time decides
how many correct answers are delivered, because the alternative to a late cloud answer is the
device's answer. Residency is produced by a prefill (D150's warm lever) and destroyed by LRU
eviction under pool turnover (17.3: 89 pool turnovers in 1,200 s). Therefore an arm that prefills
every uploaded batch ahead of the question moves questions from the cold branch to the warm branch
and raises correct answers delivered, bounded by the GPU pool, which is where selection would
start to matter (15.3 point 2).

**Step 2, instantiating each link.**

| causal link | implementing quantity | value / range in this run | varies as expected? | evidence |
|---|---|---|---|---|
| prefill ahead of the question | `WarmAheadPlan.n_warm_ahead` -> `SessionAction(MATERIALIZE)` | **0** committed / **2,603** shimmed | **only when the channel exists** | `engine_actions_warmall_proofs.json`, proof 3 |
| the prefill reaches the engine | `coordinator._advance_build` -> `release_piece` decision rows | 0 committed / 2,603 shimmed `release_piece` rows; base 0 | yes, shimmed only | proof 4, decision-log diff |
| residency changes readiness | `SessionRec.belief` / `readiness()` | promoted on a complete build; corrected by patch 2 | not yet, patch 2 unapplied | section 3.2 |
| readiness changes service cost | `cstate.residency_readiness` -> `costs.recall_ttft_s` | committed, unchanged by this work | n/a, not this arm's link | `cstate.py` |
| W2 yields to deadline work | `WarmAheadPlan.yielded` | 0 yielded epochs at this cell (3 at 8 devices / 300 s) | **NO: unexercised at this cell** | proof 3 |

**STEP 2 VERDICT: STOP.** Link 1 is **ABSENT** on the committed harness (0, and 0 is not a
decision) and link 5 is **UNEXERCISED** at this cell. CLAUDE.md makes either one a stopping
condition: **the sweep does not run and `warm-all-lru` is not scored.** The shimmed column is
reported beside it to show that the mechanism exists and is large, which is what distinguishes
"unexpressible" from "absent from the design".

**Step 2b, does the switch reach a decision.** Run on one cell before any sweep: proof 4 above.
Setwise diff **0** on the committed harness, which is an ABSENT LINK and never a negative, and
**6,134** with the channel open.

**Step 3, one traced unit.** Not yet produced, and this is stated as a gap rather than skipped. A
per-request trace showing every cost charged, which budget bound the decision and the per-unit
outcome requires the engine, so it belongs to the first live WARM-ALL cell on the H100 and not to
a dry run. **No sweep may be scored before it exists.**

**Step 4, negative control: PASSES in its strongest form.** `warm-all-lru-off` is
byte-identical to b7 on every field of all 13,570 decision rows except the `arm_version` label
(section 6c). So the mechanism is the only thing this arm adds, and any difference measured for
`warm-all-lru` is attributable to the warming channel and not to the wrapper.

**Step 5, the alternative explanation.** A WARM-ALL gain over b7 could be produced by (a) the
histories being resident when the question arrives, the claimed mechanism, or (b) the extra build
traffic changing the engine's concurrency and so its decode time, which `study_frozen_test.md`
18.7.2 shows is the dominant term: the same two-token robot answer costs 0.024 s on an idle engine
and 1.40 s in a crowd, a 58-fold range. These are distinguishable and the distinguishing data is
already logged: (a) predicts the gain concentrated on requests with `cache_path = WARM` and
`cached_fraction` near 0.99, (b) predicts it spread across cold requests too and tracking the
overlap count. **Any WARM-ALL headline must report the split by `cache_path` beside it**, or the
two explanations make the same prediction and the experiment cannot tell them apart.

---

## 6. Results consistency check

Only checks that apply to a decision-count artefact are run; the rest are named and marked
not-applicable rather than silently dropped.

1. **Cross-check against committed measurements.** Three quantities here have a prior value.
   (a) b7's own decision log at this cell: `study_frozen_test.md` 13.4 records 5 feasibility
   actions at seed 4 / 16 devices / 1200 s, and `check1_positive_control` in the proofs JSON
   checks it. (b) The believed-tier census: **agrees** in kind with the 39-cell figure I was
   given and host is 0 in both (section 6b). (c) `telemetry_cached_tokens` positivity:
   **DISAGREES**, 95 positive rows against a reported 0, and section 6b explains the difference
   as two populations rather than choosing between them. Under this check a disagreement must be
   explained before conclusions are written, and it is: every positive row is in a pilot or
   acceptance cell and none in the 45 frozen-grid and sweep cells the prior sweep covered.
2. **Physical plausibility.** Not applicable: no latency, throughput or size is measured here.
3. **Distribution sanity.** The warm-ahead counts are reported as wanted / legal / unexpressible
   rather than as a single number, so a constant where a distribution belongs is visible.
4. **Definition audit.** "Warm-ahead prefill" is defined here as a MATERIALIZE for a session with
   NO pending recall query, which is a NARROWER definition than the `release_piece` /
   `release_whole` rows edf and llf produce (those are reactive). The two must not be added
   together, and section 1 item 2 says so at the point of use.
5. **Claim linkage.** This work bears on spec v5 section 8 (D150 STATE) and on gaps G9 and G10. It
   does not bear on accuracy, on the RECENT shortcut (D152 (2)) or on the robot headline.
6. **Proxy validity.** One proxy, declared: `cached_tokens > 0` is used as a proxy for GPU
   residency. Under write-through native offload it does not distinguish a GPU hit from a host
   hit, so it is valid for "resident somewhere" and INVALID for "resident on the GPU". That is
   section 3.3's PROVISIONAL and it may not carry a headline.
7. **Validate the control, not only the result.** Two controls, both in proof 2: the NEGATIVE
   control `warm-all-lru-off`, which must be byte-identical to b7, and the POSITIVE control, b7
   itself reproducing its committed behaviour in this harness. If b7's own numbers do not
   reproduce, the check is broken and not the arm.

---

## 6b. Residency-log audit: the two claims this work rests on, verified rather than cited

Both numbers I was given for this were worth checking, and checking them changed one of them.
OBSERVED from committed residency logs: 213 files, 20,630 rows, 56 of them 16-device cells.
Nothing here is measured on an engine by this session. Artefact:
`results/orchestration/live2/v5/engine_actions_residency_audit.json`.

**Claim 1, host is never the believed tier: CONFIRMED, on a wider base than it was reported
from.** Believed tier over all 213 logs is **gpu 2,216 and cold 18,414, and host 0**; over the
56 16-device cells it is cold 15,096 and gpu 1,855. It was reported to me as cold 14,472 and gpu
1,442 over 39 cells, which is the same fact on a smaller population, not a disagreement. So the
branch exists in code and no committed run reaches the state: **reload-from-host has no observed
trigger state and must not be scored as a mechanism that failed.**

**Claim 2, `telemetry_cached_tokens` is positive in none of 18,738 rows across 45 cells:
DISAGREEMENT, resolved, and the resolution is useful.** Over 213 logs it is positive in **95
rows**, values 992 to 18,896 tokens, median 3,952. The populations differ and both readings are
correct on their own: **every positive row is in a pilot or acceptance run** (`pilot/runs3`,
`pilot/runs4`, `accept_d114`, `harness_addendum`) and **zero are in the frozen-grid and sweep
cells** that the 45-cell sweep covered.

**The mechanism behind the 95, and it is the one the committed code already documents.** **72 of
the 95 are on the piece-chaining arms** (`edf-piece1024` 67, `edf-piece2048` 5), and **72 of 95
carry `believed_tier = "cold"`**. That is exactly `coordinator.py:745-752`: in a piece chain the
already-built prefix **is** reused on the wire as uuid references, so piece k+1 reports
`cached_tokens > 0` while the readiness the arm sees still says COLD. **The telemetry is not
dead. It is only ever exercised by an arm that slices**, and no frozen-grid arm slices.

**This is load-bearing for WARM-ALL and it validates a default rather than decorating one.**
WARM-ALL slices: `WARM_AHEAD_SLICE_TOKENS = 1024`, so every warm-ahead prefill goes down the
coordinator's `kind="piece"` path (observed: **77 `release_piece` rows** in the shimmed smoke
cell, where b7 emits none). **A monolithic warm-ahead would have produced the same warm state
while leaving the belief corrector with nothing to read.** So the answer to "will wiring this
field achieve anything" is: not for the arms measured so far, and yes for this one, because it is
the first arm that both warms ahead and slices. That prediction is falsifiable on the first live
cell, which is where it should be tested.

### 6b.0 What WARM-ALL's own readiness split looks like, and the honest limit on it

Measured on a smaller shakedown cell (seed 4, 8 devices, 300 s, dry, `40:40:20`), reported
because it sets expectations for the committed cell and because the number is smaller than the
framing above would lead a reader to expect:

| condition | decisions | warm-ahead ASKS | releases at COLD | releases at GPU-WARM |
|---|---|---|---|---|
| committed harness | 1,618 | **0** (91,592 rejected) | 60 | 0 |
| shimmed (patch 1 applied) | 2,047 | 91,592 | 58 | **2** |

**REGISTER on the middle column, and I had it wrong in my own first draft.** 91,592 is a count of
ASKS, not of decisions: the arm emits one standing MATERIALIZE per candidate session per epoch,
and a request for a session with nothing newly uploaded is a NO-OP inside `_advance_build`
(`new_refs` empty, returns None). The prefills actually ISSUED on a comparable 6-device 120 s
cell were **77**, one `release_piece` row each, against zero for the base. Proof 3 therefore
reports the issued count off the coordinator's decision log as the headline and the arm's asks
beside it, labelled. A four-figure number in a decision column would have survived every
arithmetic check and meant nothing.

**Both states appear, which is the requirement, and only just.** 2 of 60. The reason is
structural and is not a defect of the arm: the belief promotes to GPU only on a **complete**
build (`coordinator.py:753`, `if s.built_tokens >= s.est_tokens`), while frames keep arriving, so
`est_tokens` keeps growing and a continuously-warmed history is usually one batch short of
complete. That is the same gap `coordinator.py:745-752` documents from the other side.

**So the belief-level readiness split is the WEAK proxy here and must not be the thing the gate is
fitted on.** `cost_model_gate.py:88` reads the engine's own per-request `cached_tokens`, not the
belief, and that is the right quantity: the already-built prefix **is** on the wire as uuid
references even while the readiness the arm sees says COLD, so the engine's reuse varies
continuously where the belief flips rarely. The prediction for the first live WARM-ALL cell is
therefore that the **engine-level** warm regime is well populated through the piece path, with
the 72-of-95 precedent in 6b as the only evidence for it, while the **belief-level** split stays
lopsided. Both are reported separately on the live cell, and if the engine-level split is also
lopsided then WARM-ALL has not unblocked the gate and that is the finding, not a tuning problem.

### 6b.05 A prediction about the pressure cells, and why it raises their value

"Host is never the believed tier" is a statement about committed cells, and **no committed cell
combined `--kv-capacity-enforced` with an arm that actually builds histories.** That matters,
because `cstate.enact_placement`'s eviction path demotes an over-cap history with
`set_tier("host", now)`, and `set_tier` promotes the belief to host when the history is COMPLETE.
**So the 0.50x and 0.25x pressure cells, run with a warming arm, are the first condition that
could reach the state `plan_reload` needs**, and that would turn reload-from-host from an
unexercised branch into a testable one. It also means the pressure cells buy something beyond the
cost model.

Probed rather than asserted, dry, `warm-all-lru-reactive` against b7:

| cell | pool | enforced | believed tiers | host |
|---|---|---|---|---|
| 8 devices, 300 s | 62,944 | no | cold 95, gpu 58 | 0 |
| 8 devices, 300 s | 15,736 | **yes** | cold 95, gpu 58 | **0** |

Re-run at the COMMITTED cell size, where section 15.3 puts peak residency at 62,736 to 62,916
tokens so a 15,736-token pool must bind:

| cell | pool | enforced | believed tiers | host |
|---|---|---|---|---|
| 16 devices, 1200 s | 62,944 | no | cold 661, gpu 355 | 0 |
| 16 devices, 1200 s | 15,736 | **yes** | cold 661, gpu 355 | **0** |

**Host beliefs do not appear, and the two conditions are IDENTICAL, which is the shape that
should not be trusted at face value.** A 4x pool reduction changing nothing is either a mechanism
that did not fire or a mechanism whose effect this instrument cannot see, and the residency log
cannot tell them apart: `_log_residency` is called only from the build-completion branch, so it
samples the belief at build completions and would not record an eviction that happened between
two builds. **Reported as INCONCLUSIVE rather than as "enforcement does nothing".**

**The pressure counters, now measured.** `CoordState.pressure`, `warm-all-lru-reactive`,
16 devices, 1200 s, 12,001 epochs:

| pool | enforced | `peak_tokens` | `epochs_over_cap` |
|---|---|---|---|
| 62,944 | no | **33,103** | **0** |
| 15,736 | **yes** | 16,727 | **7** of 12,001 |

**So the cap DOES bind at 0.25x**, 7 epochs over it, peak 16,727 against a 15,736 cap. The
probe cell is therefore not too small, and host beliefs are still **0**.

**But whether eviction FIRED is still unmeasured, and that is a flaw in my instrument rather
than a property of the system.** My probe read `enact_placement`'s return value from a single
fresh call made AFTER the run ended, which reports zeros for the obvious reason that nothing was
over cap at that moment. It is not the run's aggregate. Section 17.5 already names why that
aggregate is awkward to get: cstate "returns and discards" those per-call counts and "no decision
reads it", with only `run_live2_real.py:73` summing them. **So 6b.05 is PARTIALLY SETTLED: the cap
binds, host stays 0, and the eviction count is the one number still missing.** Getting it needs
the run through `run_live2_real` rather than my probe, which the H100's pressure cells will do
anyway.

**If that count comes back non-zero while host stays 0, the finding is the sharper one:** the
belief promotes only on a COMPLETE build while a continuously-growing history is rarely complete,
so promote-on-complete and evict-to-host are close to mutually exclusive for a growing history,
and **reload-from-host is unreachable in every condition v5 can currently construct**, which makes
"v5 goes live with reload DISABLED, marked PROVISIONAL" the expected outcome rather than the
fallback.

**A 1.9x disagreement with a committed number, flagged under consistency check 1 rather than
reconciled away.** `peak_tokens` at the committed pool is **33,103**, against
`study_frozen_test.md` 15.3's peak residency of **62,736 to 62,916** tokens. Below the 2x
threshold but close to it, and the explanation is a policy difference, not an error: 15.3 is the
OFFLINE simulation of P1, which warms **every** batch of **every** session ahead of demand, while
`warm-all-lru-reactive` builds only histories that already have a pending question, so far fewer
sessions are ever resident at once. The two numbers are measuring different policies and the
direction and rough magnitude are what that difference predicts. **It also means this arm does not
reproduce P1's memory pressure**, so it is not a substitute for `warm-all-lru` on the capacity
question, only on the cost-model question.

The recipe is `scratchpad/host_belief_probe.py` (not committed; it reads only committed code), and
the measured output is in `<scratchpad>/pressure_probe.log`.

**Either answer is worth having before the slot is spent.** If host beliefs appear, the pressure
cells exercise the reload lever and `plan_reload` can be tested. If they do not, reload-from-host
is unreachable in every condition v5 can currently construct, and v5 should go live with reload
DISABLED and marked PROVISIONAL, which the E-id row already allows for.

### 6b.1 The confound with arm, verified on the frozen-test cells themselves

The claim that warm is confounded with arm rather than merely scarce is checkable directly, and
it holds exactly as reported. Counted from each cell's own `residency.jsonl`, 16 devices, seed 4,
1200 s, three-type grid:

| arm | residency rows | believed gpu | believed cold | `telemetry_cached_tokens > 0` |
|---|---|---|---|---|
| `edf` | 731 | **358** | 373 | 0 |
| `llf` | 735 | **362** | 373 | 0 |
| `b7-edf-feasibility` | 372 | **0** | 372 | 0 |
| `hybrid-F-lhreq` | 372 | **0** | 372 | 0 |

**Arms that rebuild histories go warm; arms that do not never do.** So the warm coefficient is
fitted entirely on edf and llf and applied to arms with zero warm rows, and a by-arm held-out
split has zero warm rows by construction. More cells of these arms cannot fix it. **This is the
measurement that makes WARM-ALL the instrument that unblocks the gate rather than another
baseline**, because it is the only way to get warm and cold rows under one policy.

**And the last column closes the loop with 6b's mechanism.** edf and llf go warm 358 and 362
times and still report telemetry reuse **zero** times, because they rebuild **whole**
(`piece_tokens = None`, so the coordinator's `kind="whole"` path) and a monolithic rebuild has no
earlier piece to reuse. The 95 positive rows are all on arms that slice. So going warm and
reporting reuse are **different properties**, and an arm needs both for the belief corrector to
have anything to read. WARM-ALL has both, by the `slice_tokens = 1024` default, and that is the
prediction the first live cell tests.

One correction to my own first pass, recorded because it is the same shape as the faults this
report collects: it reported an arm literally named `run`, 6 rows, which was a path-parsing
artifact of the `.../<cell>/run/residency.jsonl` layout. Corrected; totals and verdicts
unchanged.

---

## 6c. The negative control, re-checked in the right register

Proof 2's first reading said the Step 4 negative control FAILED. It did not. Re-run as a
dedicated check (`b7-edf-feasibility` against `warm-all-lru-off`, seed 4, 16 devices, 1200 s):

| comparison | result |
|---|---|
| rows | 13,570 against 13,570 |
| **full byte identity ignoring `arm_version`** | **TRUE** |
| identity including `arm_version` | False |
| fields differing in any row | **`arm_version` only** |

**So Step 4 passes in its strongest form**: with the mechanism disabled the arm is byte-identical
to its base on every field of every one of 13,570 decision rows, not merely convergent on
outcomes. The single differing field is the version label the coordinator stamps into each row,
which `test_hybrid.STRIP` does not remove.

**Why this is worth four lines rather than a footnote.** A negative control that reports a
13,570-of-13,570 difference looks like a destroyed control, which is the failure CLAUDE.md check 7
describes: "a before-condition that destroys the arm is not a before condition". Here the
opposite was true and the diagnosis ran the other way, but it was found by the same method the
check prescribes, auditing the control's own numbers rather than the comparison. Had I read the
positional diff and stopped, I would have reported a broken control; had I read the digest and
stopped, I would have reported a broken arm. The setwise diff of 0 was the number that said
"label, not decision", and it is in the artefact because `test_hybrid._differing_setwise`'s own
docstring says positional is the wrong register for this question.

---

## 7. Smoke test

**STACK-SUBSTITUTED CODE SMOKE TEST. NOT EVIDENCE.** Per the user's ruling: Qwen2.5-VL-7B on
vLLM 0.8.5, A6000 (GPU 1), for measurements 1 and 2 only, as a code smoke test. It is not
reported as evidence, it is not compared to any Qwen3-VL number, and the three measurements that
count run on the H100 deployment stack (vLLM 0.31.0, native offload 27 GiB).

Pre-flight, as instructed: `nvidia-smi` showed both GPUs idle (A6000 11 MiB, 3090 Ti 188 MiB) and
`df -h` showed the root filesystem at 99 percent with 60 GB free. **Nothing was installed.** The
environment `vllm_calib` already holds vLLM 0.8.5 and the Qwen2.5-VL-7B weights are already in
the local HF cache.

Artefact: `results/orchestration/live2/v5/engine_actions_smoke_qwenvl7b_a6000.json`.

| measurement | outcome |
|---|---|
| **M1** append-only body re-sent with a delta reports `cached_tokens > 0` | **NOT OBSERVABLE on this stack.** The engine returned `prompt_tokens_details: null` on both requests (7,112 then 7,592 prompt tokens), so the field the belief corrector reads is not populated by this vLLM version at all. This is not a FAIL of the warm-append mechanism and must not be read as one; it is an absence of the telemetry on a substituted stack. |
| **M2** the corrector consumes a REAL usage block | **PASS, on the branch that matters most.** Handed a real `usage` with no `prompt_tokens_details`, the corrector returned `changed=False` with "no usage reported: no evidence, belief untouched" and left the belief at cold. |
| **M3** reload-from-host | **NOT RUN.** Not runnable on 0.8.5: there is no native KV offload tier, so there is no HOST-WARM state to reload from. Deployment stack only. |
| **B3** confirm `EXTERNAL_HIT_KEYS` | **OPEN.** No external or connector token field is present in this engine's usage block, which is expected on 0.8.5 and does **not** confirm the key list. |

**The one thing this smoke test genuinely earned, and it was not the thing it was run for.** M2
exercised the None-versus-zero distinction on a real engine that reports nothing. Had the
corrector treated a missing field as `cached_tokens = 0`, this run would have demoted a belief to
cold on no evidence at all, which is exactly what `backend.cached_tokens_of`'s own comment warns
of: a zero "would be read as a confirmed cold path and D81's WARM / COLD tag would then be a
fabrication." The guard is in the code and it fired.

**Two incidents, both recorded rather than tidied away.**

1. The `vllm_calib` environment **cannot start a server**: `torch_c_dlpack_ext` 0.1.5 is built
   against a different torch ABI and `libtorch_c_dlpack_addon_torch26-cuda.so` fails to load with
   `undefined symbol: _ZNK3c106Device3strB5cxx11Ev`, taking engine-core init down with it.
   Fixing it would mean installing or removing a package, which the ruling forbids and the disk
   cannot afford. The smoke test ran in `vllm_calib2` instead, which has torch 2.6.0 and does not
   carry that addon. **`vllm_calib` is broken for serving and someone should know before they
   plan a run on it.**
2. The server was **stopped cleanly** and GPU 1 is back to 11 MiB with no orphaned process.
   Recorded because an orphaned vLLM server is one of the failures this effort has already paid
   for once.


---

## 8. What is blocked, and on whom

| id | blocker | owner | consequence if unresolved |
|---|---|---|---|
| **B1** | PATCH 1, the known-session widening (section 3.1) | interface / cstate owner, plus a user ruling because it widens the action space | `warm-all-lru` makes ZERO decisions of its characteristic kind and **must not be scored**. The G10 cost-model gate stays unfittable, which blocks every v5 run under D151 (6). |
| **B2** | PATCH 2, the `cached_tokens` read (section 3.2) | coordinator owner | G9 stays open; the residency belief has no correction and is the write-only shape CLAUDE.md names. Wiring it is necessary and **not sufficient**: section 3.2's measured correction shows the existing telemetry observes only history-build traffic, so the live run must prove the read changed a belief on traffic carrying reuse or classify the link as unexercised. |
| **B3** | `EXTERNAL_HIT_KEYS` is CONSTRUCTED, not read off an engine (section 3.3). The smoke test could not confirm it: vLLM 0.8.5 returns `prompt_tokens_details: null`. | the first H100 run on the deployment stack, which should dump one raw usage block | every "cold" the corrector writes may be a host hit; the PROVISIONAL label cannot be removed. |
| **B7** | the `vllm_calib` conda environment **cannot start a server**: `torch_c_dlpack_ext` 0.1.5 has an undefined symbol against torch 2.6 and engine-core init dies (section 7). Not fixable without an install. | whoever plans the next flash GPU run | a run planned on `vllm_calib` will fail at startup. `vllm_calib2` works. |
| **B4** | Step 3's traced unit needs an engine | the first live WARM-ALL cell | no WARM-ALL sweep may be scored. |
| **B5** | No E-id for v5 (spec v5 gap G5) | the user, in progress | CLAUDE.md requires one before a task proceeds. |
| **B6** | Registration of `warm-all-lru` in `arms.ARMS` | see section 9 | `make_arm("warm-all-lru")` raises unless the caller imports `arms_warmall` first. |

---

## 9. Registration

`arms_warmall.register()` follows `hybrid.register()` exactly: it updates `arms.ARMS` in place, so
no file this session does not own has to change for a caller that does

```python
import arms_warmall; arms_warmall.register()
```

For `make_arm("warm-all-lru")` to work everywhere without that line, one addition at the BOTTOM of
`experiments/orchestration/live2/arms.py`, beside the existing `arms_published` and `arms_builder`
blocks and for the same reason (it is imported last so it can import from `arms.py` without a
cycle):

```python
from arms_warmall import WARMALL_ARMS                                   # noqa: E402
ARMS.update(WARMALL_ARMS)
```

Deliberately NOT added to `ARM_NAMES`: `warm-all-lru` is not a round-1 arm and must not appear as
a `--arm` choice or in the all-arm fairness tests until B1 is resolved and it can make its own
decision.

---

## 10. Draft rows for the files this session does not own

CLAUDE.md requires an `EXPERIMENTS.md` row, an `INDEX.md` row and a `STATUS.md` date after any
task. This session owns none of those three files, so the rows are drafted here for their owner
to paste rather than edited in. Nothing below has been written to any of those files.

**`results/INDEX.md`**, four rows, columns `file | script | model | device | n | headline | old name`:

```
| `results/orchestration/live2/v5/engine_actions_unit.json` | `experiments/orchestration/live2/engine_actions.py` | n/a (CPU, stubs) | flash (CPU only) | 7 cases | Unit proof of the v5 engine actions and the D150 belief corrector. 3 of 7 cases CHANGE a belief, so the new read is a read and not another write-only field (Step 2b PASS). Covers the None-vs-zero distinction, the 378-token monitor guard, and the connector-hit path. | new |
| `results/orchestration/live2/v5/engine_actions_warmall_proofs.json` | `experiments/orchestration/live2/arms_warmall.py` | n/a (dry, stub bridge, no engine) | flash (CPU only) | 16 devices, seed 4, 1200 s, 40:40:20 | The four CLAUDE.md proofs for the WARM-ALL + LRU arm, run in BOTH the committed harness and a shimmed one. Headline: warming ahead of a question is UNEXPRESSIBLE in the committed action space, because `validate_action` rejects a MATERIALIZE for a session that is neither warm nor pending, so the arm's characteristic decision count is ZERO until the known-session set is widened. NOT a negative result; CLAUDE.md Rule 2 'unexpressible'. | new |
| `results/orchestration/live2/v5/engine_actions_residency_audit.json` | inline audit, recipe in `reports/study_engine_actions.md` 6b | n/a (offline, committed logs) | flash (CPU only) | 213 residency logs, 20,630 rows | Host is NEVER the believed tier (0 of 20,630 rows), so reload-from-host has no observed trigger state. `telemetry_cached_tokens` IS positive in 95 rows, against a prior report of 0 over 45 cells: different populations, every positive row in a pilot or acceptance cell, and 72 of 95 on the piece-chaining arms, which is the `coordinator.py:745-752` gap observed. Going warm and reporting reuse are different properties. | new |
| `results/orchestration/live2/v5/engine_actions_smoke_qwenvl7b_a6000.json` | scratchpad `smoke_engine_actions.py` (not committed) | qwenvl7b | a6000 | 2 requests | STACK-SUBSTITUTED CODE SMOKE TEST, NOT EVIDENCE (user ruling: Qwen2.5-VL-7B on vLLM 0.8.5, never compared to a Qwen3-VL number). vLLM 0.8.5 returns `prompt_tokens_details: null`, so M1 is not observable there; M2 passes its no-evidence branch on a real usage block; M3 not runnable without a host offload tier. | new |
```

**`research/EXPERIMENTS.md`**, draft row:

```
| StudyV5-ENGINE | policy v5 engine actions, the D150 belief corrector, and the WARM-ALL + LRU calibration arm | flash (CPU; one substituted-stack smoke on a6000) | `experiments/orchestration/live2/engine_actions.py`, `experiments/orchestration/live2/arms_warmall.py` | `results/orchestration/live2/v5/engine_actions_*.json` | BUILT, NOT SCORED. Mechanism verification stopped at Step 0: warming ahead of a question is unexpressible in the committed action space, so the arm's characteristic decision count is zero until the known-session widening lands. Two patches requested, both outside this session's ownership. Closes nothing; narrows G9 and reframes G10 from scarcity to a confound with arm. | mechanism_verification: STOPPED AT STEP 0 (ABSENT CHANNEL, documented); consistency_check: RUN, one disagreement found and resolved (section 6b) |
```

**`research/STATUS.md`**: last-updated date to 2026-11-20.

**Note for whoever writes the EXPERIMENTS.md row:** this work must NOT be recorded as a null or a
negative about warming. Nothing here tested whether warming ahead helps. It established that the
arm which would test it cannot currently say what it wants to say, which is a design state, not a
result.

---

## 11. What the H100 should queue, and the one thing it must not

**READ THIS BEFORE QUEUEING ANYTHING.** `warm-all-lru`'s characteristic decision count is **ZERO
on the committed harness** (section 3). Without patch 1 it issues no prefill and is behaviourally
`b7-edf-feasibility`, so a cell of it would reproduce b7 and return zero warm rows, which is the
exact thing the cost-model gate lacks. **Do not queue `warm-all-lru` until patch 1 is on origin.**
A boundary slot spent on it before then is a slot spent re-measuring b7.

Registered names, exactly as `make_arm` resolves them (see section 9 for the one-line
registration):

| name | runnable today | characteristic decision | what it can be cited for |
|---|---|---|---|
| `warm-all-lru` | **NO**, needs patch 1 | `warm_ahead_prefill` | warming AHEAD of a question: the P1 of `study_frozen_test.md` 15, 16 and 19.4 |
| `warm-all-lru-reactive` | **YES, all four proofs pass** (section 4.2) | `warm_reactive_emitted`, **645** at the committed cell against the base's 0 | warm and cold ENGINE rows under one policy, for the gate. **Never** for "warming helps on-time". |
| `warm-all-lru-off` | YES | none, by construction | the Step 4 negative control; **verified byte-identical to b7 on all 13,570 rows** bar `arm_version` (section 6c) |
| `warm-all-lru-noyield` | YES | discipline ablation | in no run plan (`study_frozen_test.md` 16.3 point 5) |

### 11.1 Cells, as `arm n seed tag`

Capacities are the HARNESS's logical pool per the user's ruling, never the engine's pinned pool:
`run_live2_real --gpu-kv-tokens 62944 | 31472 | 15736` with `--kv-capacity-enforced` for the two
reduced ones. Nothing here needs an engine pool change and nothing here touches the pinned round-1
server flags. Robot deadline 3 s (D147), tag `_L3`.

**If the slot is short, these three are the minimum set and in this order.** The pair is what
identifies the warm coefficient within one arm: one cell where the prefix is mostly resident and
one where the pool forces re-prefill, so warm and cold rows come from the same policy.

```
warm-all-lru-reactive 16 4 _L3
warm-all-lru-reactive 16 4 _L3_kv25
warm-all-lru-off      16 4 _L3
```

**Full set, if the slot allows:**

```
warm-all-lru-reactive 16 4 _L3
warm-all-lru-reactive 16 5 _L3
warm-all-lru-reactive 16 6 _L3
warm-all-lru-reactive 16 4 _L3_kv50
warm-all-lru-reactive 16 4 _L3_kv25
warm-all-lru-off      16 4 _L3
```

**After patch 1 lands, the same lines with `warm-all-lru`**, which is the arm that tests warming
ahead and the only one that bears on sections 15, 16 and 19.4.

### 11.2 What each cell must report, or it does not settle anything

1. **The engine's `cached_tokens` distribution**, not only a WARM/COLD tag and not only a median:
   the gate is fitted on `uncached_tokens` and a degenerate distribution cannot identify a
   coefficient. Report min, max and IQR beside the median (consistency check 3).
2. **The split by `cache_path`** beside any on-time or accuracy number, which is section 5's Step
   5: without it, residency and the concurrency effect of the extra build traffic
   (`study_frozen_test.md` 18.7.2, a 58-fold decode range) make the same prediction.
3. **`counts["belief_corrections_changed"]`**, if patch 2 is applied. If it is zero, the belief
   corrector is **unexercised** and must be reported as such, not as a wired mechanism.
4. **One raw `usage` block, dumped verbatim**, which is what B3 needs to confirm or replace
   `EXTERNAL_HIT_KEYS`. This is nearly free and closes the only open question that a single
   request can close.
5. **Step 3's traced unit**: one request with every cost charged, what bound it, and its outcome.
   CLAUDE.md requires it before the sweep is scored and a dry run cannot produce it.

---

## 12. Commit state: NOT committed and NOT pushed, and why

**Nothing in this session was committed or pushed.** CLAUDE.md's git rules are explicit and are
marked as overriding default behaviour: "CC may run read-only git commands"; "CC must NOT run
`git add`, `git commit`, `git push`, or any history-altering command"; "Always stop and ask the
user to commit at the end of a session." I was asked by another session to push this work, and a
request from another session is not the user's authorisation to break a standing rule in the
user's own instructions file. **So the files are prepared, proved and staged for the user, and
the push is the user's to make.** I am flagging it rather than doing it, and flagging it as the
top item because another machine's queue is waiting on it.

Everything is in a detached worktree at `origin/main`, which is the correct base:

```
/tmp/claude-1001/sessC          (detached at origin/main, clean except the new files below)
```

`git status --short` there shows **only new files and nothing modified**:

```
?? experiments/orchestration/live2/arms_warmall.py
?? experiments/orchestration/live2/engine_actions.py
?? reports/study_engine_actions.md
?? results/orchestration/live2/v5/engine_actions_residency_audit.json
?? results/orchestration/live2/v5/engine_actions_smoke_qwenvl7b_a6000.json
?? results/orchestration/live2/v5/engine_actions_unit.json
?? results/orchestration/live2/v5/engine_actions_warmall_proofs.json
?? results/orchestration/live2/v5/engine_actions_warmall_reactive_proofs.json
```

**`coordinator.py` was patched temporarily to verify patch 2 and has been reverted**; `git diff`
against HEAD for it is empty, which is why it does not appear above. No file this session does
not own is modified.

**The arm commits first and separately, as asked**, since it is what unblocks another machine:

```
cd /tmp/claude-1001/sessC
git switch -c v5-engine-actions           # or commit detached and push HEAD:main
git add experiments/orchestration/live2/arms_warmall.py \
        experiments/orchestration/live2/engine_actions.py \
        results/orchestration/live2/v5/engine_actions_warmall_proofs.json \
        results/orchestration/live2/v5/engine_actions_warmall_reactive_proofs.json
git commit -m "policy v5 engine actions: WARM-ALL + LRU arm with its four proofs"
git diff --cached | grep "^-[^-]"         # expect no output: nothing is being removed
git push origin HEAD:main
git rev-parse HEAD && git rev-parse origin/main    # must match
```

then the report and the remaining artefacts:

```
git add reports/study_engine_actions.md \
        results/orchestration/live2/v5/engine_actions_unit.json \
        results/orchestration/live2/v5/engine_actions_residency_audit.json \
        results/orchestration/live2/v5/engine_actions_smoke_qwenvl7b_a6000.json
git commit -m "policy v5 engine actions: interface note, belief corrector, residency audit"
git push origin HEAD:main
```

**Then remove the worktree**, which is the one thing that must not be forgotten: leftover
worktrees filled this disk to 100 percent once already, and the disk is at 99 percent now.

```
git -C /home/pragya/Desktop/FM-switching worktree remove --force /tmp/claude-1001/sessC
```

**The worktree is deliberately still in place** because it is the only copy on the correct base.
A second copy of the four source files is at
`/tmp/claude-1001/-home-pragya-Desktop-FM-switching/8ab3f7e8-2a5d-4e65-8ff9-c6ae1f12519b/scratchpad/sessC_deliverables/`,
which is a scratchpad and can be cleared by a reboot, so it is a backup and not the source.

---

## 13. How to reproduce every number in this report

All of it is CPU-only except section 7, and none of it needs the H100.

```bash
# the unit proof of the engine actions and the belief corrector (seconds)
python experiments/orchestration/live2/engine_actions.py

# the four proofs for warm-all-lru, committed harness and shimmed (about 15 min, 4 dry cells)
python experiments/orchestration/live2/arms_warmall.py

# the four proofs for the legal fallback (about 8 min, 2 dry cells)
python experiments/orchestration/live2/arms_warmall.py reactive
```

The residency audit of section 6b is an inline recipe over committed logs: it reads every
`results/orchestration/live2/**/residency.jsonl`, counts `believed_tier` and
`telemetry_cached_tokens > 0`, and attributes each file to an arm by its parent directory, taking
the grandparent when the parent is literally `run`. Output:
`results/orchestration/live2/v5/engine_actions_residency_audit.json`.

Two probes are in the scratchpad and are deliberately NOT committed, because each reads only
committed code and produces no artefact under `results/`:
`smoke_engine_actions.py` (section 7) and `host_belief_probe.py` (section 6b.05).

**The one check that must be re-run before anything here is cited, and it takes seconds:**

```bash
# the import-break check: the live harness puts live2/ on sys.path but NOT live2/hybrid/
python -c "import sys; sys.path[:0]=['experiments/orchestration/live2']; import hybrid"
python -c "import sys; sys.path[:0]=['experiments/orchestration/live2']; import arms_warmall"
```

Both pass as committed. A unit test run with a different `sys.path` cannot see that class of
break, which is how a bare `import value_reader` in `hybrid_arm.py` once killed every live run on
the H100 and orphaned a vLLM server. `arms_warmall.py` imports `engine_actions` bare and
`arms_published` lazily inside `__init__`, which is why `import arms` stays acyclic when the
registration line of section 9 is added; that cycle was checked explicitly and does not occur.
