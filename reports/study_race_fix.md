# StudyRACE-fix - the submission race, fixed under D158 (2)

**Scope.** `coordinator.py` marked a frame's bytes sent at SUBMISSION. A later request on the same
session then sent that frame as a uuid-only reference (`bodies.image_part` with `path=None`)
before the engine had registered the piece carrying its bytes, and the engine answered HTTP 400.
Once one request failed, every later reference on that session pointed at bytes the engine never
received, so it cascaded.

**The ruling implemented (D158 (2)).** Mark a frame's bytes as sent only when the request carrying
them returns 200. Until then, later requests carry the bytes again. For every arm. Pieces are NOT
serialised; the user excluded that explicitly because it would change timing and decisions rather
than only wire bodies.

**Base.** Both sides of every comparison are detached worktrees at `origin/main` `cc22429`.

**Register, stated once and applying to every number below.** Every cell in this report is a DRY
cell or a RECONSTRUCTION from a committed log. Nothing here is a latency, a quality or a capacity
result for any arm. Proof 3 is a replay of the two rules over the CAL1F request log, not a
re-execution of the coordinator and not a server round trip.

---

## The change

`sent_bytes_for` was doing two jobs and only one of them may wait for a 200. The set is split, as
D158's own implementation note requires.

| quantity | advances at | job | read at |
|---|---|---|---|
| `SessionRec.sent_bytes_for` | submission (unchanged) | **build progress** | `coordinator.py:_advance_build`, `already = len(s.sent_bytes_for)` |
| `SessionRec.confirmed_bytes_for` | HTTP 200 | **reference eligibility** | `_advance_build` prefix body, `_submit_recall` body |
| `coordinator._mon_sent` | submission (unchanged) | **the EP-G charge** (`n_new` → `cost`) | `_submit_monitor`, EP-G branch |
| `coordinator._mon_confirmed` | HTTP 200 | **reference eligibility**, dashcam side | `_submit_monitor`, EP-G branch body |

The dashcam side is split for the same reason and with the same shape. It is not an extra: the
saturated held-out cell had **1,113 dashcam 400s against 397 robot ones**, so the dashcam path is
the larger half of this bug.

**The prefix invariant is removed rather than asserted.** The old recall release computed
`sent = len(s.sent_bytes_for)` and sliced `refs[idx0:sent]` - a COUNT used as an INDEX, which is
sound only while the bytes-sent set is a prefix of the frame list. Neither set is a prefix in
general: a `whole` recall sends bytes for the tail as well, and a 200 can arrive out of submission
order. The body is now built by SET MEMBERSHIP, which needs no such invariant. The one invariant
the promoter does rely on - `confirmed_bytes_for` is a subset of `sent_bytes_for` - is maintained
by construction (the promotion is intersected with the submitted set) and then asserted.

**Promotion runs before `_settle`**, on purpose: `_settle` can release a chained recall in the same
completion, and promoting first lets that recall reference what this 200 just confirmed instead of
re-sending its bytes.

---

## Mechanism verification

### Step 0 - what would make this run uninterpretable, asked before it started

| asked | answer | consequence |
|---|---|---|
| Is the comparator about to change? | Yes. `origin/main` moved from `9615bca` to `cc22429` mid-setup (four commits, including D158 itself). | Both worktrees re-pointed at `cc22429` before any proof ran. Had the before side stayed at `9615bca`, proof 1 would have compared two different bases. |
| Does the mechanism have a reachable path in the cell proof 1 uses? | **No.** `test_hybrid.dry` passes no `frames_root`, so `_path` returns None for every frame, nothing is ever added to `sent_bytes_for`, and every image part is already a uuid-only reference. | Proof 1 as D158 names it would have passed **vacuously**. A second, store-backed cell was added as proof 1b. This is the single most important thing Step 0 bought and it is the same false-proof shape the gate report records for proof (a): "with no store, the authoring session's first version of proof (a) showed a perfect cached-token rise with ZERO frames carrying bytes." |
| Can the dry harness confirm anything at all? | No. `_DryFuture.result` returns `http_status=None`, so nothing is ever promoted. | That is the conservative direction and changes no decision, but it is also the MAXIMAL-change condition. A `--confirm200` condition was added so confirmation advances on the dry timeline and the realistic cost can be measured. Both conditions are reported. |
| Is a committed diagnostic about to drift from the quantity it describes? | Yes. `epg_requests.new_tokens_charged` was re-derived from the body (`len(frames) - n_ref`), which after the fix no longer equals the charge. | Changed to read the charge's own basis (`n_new`). The two were equal by construction before the fix, so nothing moves on committed runs. |

### Step 1 - the causal chain

If a uuid-only reference is resolvable by the engine only once the request that carried that
frame's bytes has been registered, then marking bytes sent at submission (the pre-fix
`sent_bytes_for`) lets the next request on the same session reference bytes the engine has not yet
received; the engine rejects that request with HTTP 400; a rejected request never registers its
own bytes, so every later reference on that session is also unresolvable and the session cascades.
Deferring **reference eligibility** to a 200, while leaving **build progress** at submission,
removes the first link without touching any decision: the frames a piece builds are chosen by the
submission-time quantity exactly as before, and only the wire form of the already-built prefix
changes.

This chain is a HARNESS-CORRECTNESS chain, not a policy chain. It is grounded in D158 (2) and in
`bodies.image_part`'s two wire forms, not in a FORMULATION claim - see consistency check 5.

### Step 2 - each link instantiated

| causal link | implementing quantity | value / range in this run | varies as expected? | evidence |
|---|---|---|---|---|
| bytes put on the wire | `SessionRec.sent_bytes_for` | 2,205 frames (`warm-all-lru`), 1,922 (`edf`); **identical before and after** | yes, and identity is the requirement | `proof12_confirm200.json` → `mechanism_exercised.frames_sent_before/after` |
| build progress reads it | `already = len(s.sent_bytes_for)` | read at `coordinator.py` `_advance_build` | unchanged by design | decision digests identical, Step 2b below |
| engine acknowledges bytes | `http_status == 200` → `confirmed_bytes_for` | 2,190 of 2,205 confirmed (`warm-all-lru`); 1,922 of 1,922 (`edf`) | yes - non-zero, and 15 frames remain unconfirmed at window end | `mechanism_exercised.frames_confirmed_after`; `counts.racefix_bytes_confirmed_session` 6,824 and 1,922 |
| reference eligibility reads it | `r in s.confirmed_bytes_for` in `_advance_build` and `_submit_recall` | 4,739 parts flipped reference→bytes (`warm-all-lru`), 0 (`edf`) | yes, and the zero on `edf` is the discrimination, not a miss | `parts_reference_to_bytes`; `counts.racefix_bytes_resent` |
| dashcam side, same split | `_mon_sent` / `_mon_confirmed` | 6,485 monitor frames confirmed in both arms | yes | `counts.racefix_bytes_confirmed_monitor` |
| the fault itself | dangerous references in the CAL1F log | old rule 30,464 parts over 747 of 1,191 requests; new rule **0** | yes | `cal1f_replay.json` |

**No link is ABSENT, CONSTANT or write-only.** Every quantity above is named with the code that
READS it to change something, not merely the place it is set, because a write-only field satisfies
Step 2 as written while implementing no causal link at all. Enumerated:

| field | reads that CHANGE a wire body | other reads |
|---|---|---|
| `SessionRec.confirmed_bytes_for` | `coordinator.py:712` (`_advance_build`, the built prefix), `coordinator.py:774` (`_submit_recall`, the non-whole body) | `:1298` (`_n_resent`, the cost counter), `:904` (the subset assertion) |
| `coordinator._mon_confirmed` | `:606`/`:613` (EP-G monitor body) | `:660` (`n_unresolved`) |

Two reads each that decide what goes on the wire, so neither field is write-only. `desired_tier`,
the motivating failure, had one declaration and two writes and no read; these have four and three
references respectively, of which two apiece are reads that change a body.

### Step 2b - the switch reaches a decision, and the decision it reaches is the BODY

The thing under test here is a wire form, not a policy, so Step 2b is run in both directions and
both answers matter.

| condition | decisions differing | bodies differing | reading |
|---|---|---|---|
| `warm-all-lru`, `--confirm200` | **0 of 7,060** (digest `bc461056712a8978` both sides) | **439 of 7,060** | the switch reaches the body and NOT the decision log, which is exactly the claim |
| `edf`, `--confirm200` | **0 of 6,909** (digest `6877544d4bc76a81` both sides) | **0 of 6,531** | see below |
| `warm-all-lru`, no status | 0 of 7,060 | 559 of 7,060 | |
| `edf`, no status | 0 of 6,909 | 31 of 6,531 | |

**`edf`'s zero is a result, not an unexercised link, and the two conditions prove it.** Under
`--confirm200` `edf` changes no body at all, because its requests complete before the next request
on the same session is submitted: there is no race to fix, so the fix costs it nothing. Under the
no-status condition, where nothing can ever be confirmed, the same arm changes 31 bodies and
re-sends 3,392 parts. So the channel is live for `edf` and the zero is the absence of the
condition, not the absence of the mechanism. Reported this way because a bare "0 bodies changed"
on a committed arm is indistinguishable from a dead switch.

Each switch arrived with its declared type and value: `confirmed_bytes_for` is a `set` of
`frame_ref` strings taken from `sub.meta["bytes_frame_refs"]`, which is recorded at submission from
the frames that actually carried a path rather than reconstructed from `mm_uuids` (those are the
body builder's composite cache keys, not frame refs). 0 stale-record drops in every cell
(`racefix_confirm_dropped_stale`).

### Step 3 - one traced unit

One `piece` request on the declared cell (`warm-all-lru`, seed 10, 12 devices, 600 s, mode A,
dry, real-JPEG store, `--confirm200`). This is the **median changed body by flip count**, taken
from the proof's own records and not constructed: `request_id` `r1940`, chosen as
`changed[len(changed)//2]` after sorting by flips.

```
request            r1940    kind piece    device robo000
session            robo000|s000|637875586009287_start_0.0_end_406.396
INPUTS
  est_tokens       16,231                 (identical before and after)
  image parts      175                    (identical before and after)
  frame_refs       175, same list and same order before and after
  mm_uuids         175, IDENTICAL before and after  <- the engine's cache keys do not move
COSTS CHARGED TO EACH BUDGET
  accelerator      recall_gpu_s(piece, COLD)   IDENTICAL: every pre-existing counter in
                                               co.counts is equal on both sides (table below)
  KV bytes         unchanged; no admission or eviction decision differs
  budget refusals  0 before, 0 after
WHICH BUDGET BOUND THE DECISION
  neither. this release was not refused on either side, and the decision log digest is
  identical over all 7,060 decisions, so no release anywhere in the cell was rebound
WIRE BODY
  BEFORE           174 parts image_url=None (uuid-only)  +   1 part carrying bytes   = 175
  AFTER            165 parts image_url=None (uuid-only)  +  10 parts carrying bytes  = 175
                   9 parts flipped reference -> bytes
                   = already(174) - confirmed-at-submission(165)
  wire bytes       74,311  ->  536,852      (+462,541 for 9 frames = 51,393 B each)
OUTCOME
  decision         byte-identical; both sides' full decision digest bc461056712a8978
  body             body_sha256 differs, and differs ONLY by the 9 flipped parts
```

The arithmetic a reader can check by hand: `n_parts` is unchanged at 175; the flip count is
174 - 165 = 9; and 462,541 / 9 = 51,393 B per re-sent frame, which is the base64 expansion
(× 4/3) of a 38,545 B JPEG - inside the measured `nexar_q90` range of 16,570 to 117,890 B. The
per-frame figure varies body to body with the frame drawn from the pool; the aggregate over all
4,739 flips is 86,571 B, which is check 2's test against the pool MEAN.

**Every pre-existing counter is equal and the only new keys are the fix's own**, which is the
cheapest available evidence that nothing but the wire moved:

| counter | before | after |
|---|---|---|
| `submitted_monitor` | 6,489 | 6,489 |
| `submitted_piece` | 542 | 542 |
| `submitted_recall` | 29 | 29 |
| `budget_refusal` | absent (0) | absent (0) |
| *every other pre-existing key* | n/a | **identical** |
| `racefix_bytes_confirmed_session` | n/a | 6,824 |
| `racefix_bytes_confirmed_monitor` | n/a | 6,485 |
| `racefix_bytes_resent` | n/a | 4,739 |
| `racefix_confirm_dropped_stale` | n/a | **0** |

`racefix_bytes_confirmed_session` (6,824) exceeds the 2,190 DISTINCT frames confirmed because it
counts confirmation EVENTS: a frame whose bytes ride several requests is promoted once per 200.
The two are different objects and are reported as such.

### Step 4 - negative control

The mechanism under test is "reference eligibility waits for a 200". It is disabled by making the
wait unsatisfiable or vacuous, and both directions were run on the same cell:

| control | how | result | reading |
|---|---|---|---|
| **nothing can ever be confirmed** | the real dry harness: `_DryFuture.result` reports `http_status=None`, so `confirmed_bytes_for` stays empty | every bare reference becomes bytes: `warm-all-lru` 74,225 parts re-sent, wire ×9.75; `edf` 3,392 parts, wire ×1.42 | the mechanism is driving the body, and its effect saturates at "all references" when confirmation is removed |
| **everything is confirmed immediately** | `edf` under `--confirm200`, where no request is ever in flight when the next is submitted | 0 bodies change, wire ×1.000 | with the race absent the fix collapses to the identity, which is the null it must collapse to |
| **decisions, both controls** | both of the above, both arms | 0 differing decisions in all four cells | the fix cannot move a decision under any confirmation regime, which is proof 1's claim re-derived from the control side |

Cell documented: seed 10, 12 devices, 600 s, mode A, dry, real-JPEG frame store, arms
`warm-all-lru` and `edf`.

### Step 5 - the alternative explanation

The headline is "the fix removes the condition present in all 226 CAL1F 400s". Two mechanisms
would produce that:

- **(a) the claimed mechanism:** the 400s are caused by references to bytes the engine has not yet
  registered, and deferring eligibility to a 200 removes them.
- **(b) the alternative:** the 400s are caused by something else that happens to correlate with a
  long unconfirmed prefix - engine queue depth itself, a body-size limit, or a multimodal cache
  eviction - and the fix changes the bodies without removing the cause.

**What distinguishes them in the data, and it does not fully distinguish them.** For (a): all 226
400s carry a dangerous reference under the old rule, zero under the new, and the H100's own
diagnosis records that none of the 226 had a previous request on the same session that had
completed 200 (192 were still in flight, median gap 0.12 s). Against (a) being the whole story: the
**517 of 957 successful requests that also carried a dangerous reference** under the same strict
test. A dangerous reference is therefore NECESSARY for the 400 in this log and NOT SUFFICIENT - the
engine evidently registers some images before the carrying request returns. So (b) is not excluded
as a contributing cause, and the saturated held-out cell's own evidence (a ~100 s queue at the
moment of first failure) points at queue depth as the thing that widens the window.

**A NATURAL CONTROL that landed on origin while this work was running, and it discriminates.**
`bdc9638` and `c284721` add the two held-out cells the gate report predicted would be clean,
`warm-all-lru-off` and `warm-all-lru-reactive`, on the SAME EP-G workload at the same 16 devices,
seed 4, 1,200 s and the same deadline as the saturated `warm-all-lru` cell:

| cell | requests | non-200 | HTTP 400 |
|---|---|---|---|
| `warm-all-lru_..._L3_epg` (committed, saturated) | 6,262 | 1,524 (24%) | 1,510 |
| `warm-all-lru-reactive_..._L3_epg` (new) | 12,523 | **0** | **0** |
| `warm-all-lru-off_..._L3_epg` (new) | 12,126 | **0** | **0** |

This is a pre-registered prediction confirmed (the gate report: "Cells 2 and 3, `-reactive` and
`-off`, should be clean") and it **weakens alternative (b)**. A body-size limit or a generic
queue-depth fault would not spare two arms running the same workload on the same engine at twice
the request count; `-reactive` in particular reached a 33,103-token peak, so it is not simply a
lighter load. What separates the failing arm from these two is that it warms every open session and
chains pieces, which is exactly what creates an in-flight reference to its own prefix. That is
mechanism (a). It is corroboration from a cell I did not run and did not choose.

It also matches this report's own `edf` result from the other direction: an arm with no in-flight
overlap has no race, pays nothing for the fix, and had nothing to fix.

**The honest statement of what proof 3 establishes:** the fix makes the condition present in 100
percent of the observed failures structurally impossible, and it is strictly conservative (it only
ever adds bytes). It does **not** establish that 226 of 226 requests would now return 200, because
the live engine's registration point is earlier than the 200 and is not observable in this log.
That can only be settled by re-running the cell, which is D158 (3)'s plan anyway.

---

## The three proofs D158 (2) names

### Proof 1 - dry decisions byte-identical on every committed arm

`baseline_prescreen.one` over `arms.ARM_NAMES` (50 arms), pooled at 6, in a clean worktree at
`cc22429` and again in the patched tree, comparing `decisions`, `digest` and `digest_setwise`.
Template: `results/orchestration/live2/v5/patch1_byte_identity_proof.json`. Reproduce with
`racefix_proofs.py prescreen` in each tree, then `prescreen-compare`.

| | result |
|---|---|
| arms checked | **50** |
| arms whose `decisions`, `digest` and `digest_setwise` are all identical | **50 of 50** |
| arms differing on any field | **0** |
| arms erroring on either side | **0** |
| base commit, both sides | `cc22429` |
| wall, before / after | 1,772.3 s / 1,646.3 s |

**PASS. `byte_identical: true` over all 50 committed arms.**
`results/orchestration/live2/racefix/proof1_byte_identity.json`.

The two recorded HEADs are both `cc22429` because the after side is the same base with the patch
applied as uncommitted working-tree changes. That is the intended comparison; the JSON says so in
`_commit_note` so a later reader does not read it as a mistake.

**This proof is NECESSARY AND NOT SUFFICIENT, and the reason is in Step 0.** The prescreen cell
runs with no `frames_root`, so `_path` returns None for every frame, `sent_bytes_for` never grows,
and every image part is already a uuid-only reference. The patched code paths are reached but the
quantity they branch on is empty. A pass here proves the change cannot move a decision **in a
regime where no frame carries bytes**. Proof 1b is the one that tests it where it acts.

### Proof 1b - the same claim on a cell where frames really carry bytes

Declared cell: seed 10, 12 devices, 600 s, mode A, dry, arms `warm-all-lru` and `edf`, frame store
backed by the committed `nexar_q90` JPEGs so bodies have real sizes.

| arm | condition | decisions | digest before | digest after | identical | frames sent before/after |
|---|---|---|---|---|---|---|
| `warm-all-lru` | `--confirm200` | 7,060 | `bc461056712a8978` | `bc461056712a8978` | **yes** | 2,205 / 2,205 |
| `edf` | `--confirm200` | 6,909 | `6877544d4bc76a81` | `6877544d4bc76a81` | **yes** | 1,922 / 1,922 |
| `warm-all-lru` | no status | 7,060 | `bc461056712a8978` | `bc461056712a8978` | **yes** | 2,205 / 2,205 |
| `edf` | no status | 6,909 | `6877544d4bc76a81` | `6877544d4bc76a81` | **yes** | 1,922 / 1,922 |

`frames sent before/after` is the load-bearing column beside the digest: it is the submission-time
quantity that drives build progress, it is non-zero, and it is **identical**, which is the
mechanical reason the digests match. **PASS.**

### Proof 2 - only the bodies of requests that previously referenced unregistered uuids change

Body-level diff, request by request, matched on `request_id`. A body may change only by one or more
parts flipping from uuid-only reference to bytes, with `frame_refs`, `mm_uuids`, `n_parts`, `kind`,
`est_tokens`, `session_id` and `decision_id` all unchanged. Any other change is a failure.

| arm | condition | bodies compared | changed | **changed for another reason** | **changed with no bare reference** | parts reference→bytes |
|---|---|---|---|---|---|---|
| `warm-all-lru` | `--confirm200` | 7,060 | 439 | **0** | **0** | 4,739 |
| `edf` | `--confirm200` | 6,531 | 0 | **0** | **0** | 0 |
| `warm-all-lru` | no status | 7,060 | 559 | **0** | **0** | 74,225 |
| `edf` | no status | 6,531 | 31 | **0** | **0** | 3,392 |

No request exists on one side only in any cell. **PASS.**

Two details that make the pass meaningful rather than vacuous:

- **120 unchanged bodies still carried bare references** in the `warm-all-lru --confirm200` cell.
  Those references were already confirmed, so the fix correctly left them as references. The fix is
  selective, not a blanket "send everything".
- the 439 changed bodies are **437 `piece` and 2 `recall`**, which matches where the race lives:
  piece-chaining re-references its own prefix every few hundred ms.

### Proof 3 - the CAL1F failing sequence shows zero such 400s

`results/orchestration/live2/frozen_test/runs/warm-all-lru_n16_s4_1200s_h27_3t_L3_cal1f/request.jsonl.gz`,
1,191 session requests over 12 sessions: 957 × 200, 226 × 400, 8 transport. Replayed under both
rules, with the SAME test applied to each: a uuid-only reference is dangerous unless some earlier
request that carried that frame's bytes came back 200 before this request was submitted.

| | old rule | new rule |
|---|---|---|
| requests with a dangerous reference | 747 of 1,191 | **0** |
| dangerous reference parts | 30,464 | **0** |
| **of the 226 HTTP 400s: with a dangerous reference** | **226 of 226 (100%)** | **0 of 226** |
| of the 957 HTTP 200s: with a dangerous reference | 517 of 957 (54%) | 0 of 957 |
| image parts carrying bytes | 4,323 | 34,535 |

**PASS on the proof as written** (zero dangerous references, on a sequence that had 226 400s), with
the Step 5 caveat stated at the point of use: the new rule's zero is true **by construction**, so
the number carrying the proof is the old rule's 226 of 226, and the 517 of 957 control shows the
condition is necessary but not sufficient. See Step 5.

---

## The cost, reported rather than hidden

The fix re-sends bytes for frames whose carrying request has not yet returned, so **uplink bytes
rise**. Measured on the declared cell (seed 10, 12 devices, 600 s, mode A, dry, real `nexar_q90`
JPEG store), `--confirm200`, which is the realistic condition:

| arm | image parts as bytes before → after | parts re-sent | wire bytes before → after | delta | ratio |
|---|---|---|---|---|---|
| `warm-all-lru` | 8,694 → 13,433 | +4,739 | 737.4 MB → 1,147.6 MB | **+410.3 MB** | **×1.556** |
| `edf` | 8,411 → 8,411 | 0 | 700.7 MB → 700.7 MB | 0 | ×1.000 |

**Spread, not just the total** (check 3): across the 439 changed `warm-all-lru` bodies the flip
count is min 1, p25 5, median 9, p75 12, max 88; the per-body byte delta is min 41.8 KB, median
702.0 KB, max 8.47 MB; and all 12 sessions are touched (4 to 74 changed bodies each). This is a
distribution, not a constant.

**On the CAL1F sequence the cost is much larger: 4,323 → 34,535 image parts carrying bytes, ×7.99.**
That cell is 16 devices at 1,200 s with long robot histories (mean ~78 image parts per request),
and its requests were queueing behind a saturating engine, so almost nothing was confirmed in time.
**This x7.99 is the number the user should weigh**, and it is an over-estimate of the bytes the
engine strictly needs, because the 517-of-957 control shows the engine registers some images before
the carrying request returns, i.e. the 200 is a later moment than the one that actually matters.

**In bytes, with its proxy flagged:** 30,212 extra image parts over a 1,200 s cell at the
86.6 KB per part measured on the declared cell is about **2.6 GB extra uplink, or ~2.2 MB/s
(~17 Mbit/s) aggregate across 16 devices.** That figure uses dashcam `nexar_q90` sizes for robot
frames, which is the questionable proxy in check 6 and the reason the part count (+30,212) is the
register to quote. If robot D2 frames are materially smaller or larger than 60.7 KB the byte
figure moves proportionally; the part count does not.

**Prompt tokens: measured position, stated honestly.** A re-sent frame keeps the SAME `mm_uuid`
(the body builder's composite cache key is unchanged - only `image_url` goes from `None` to a data
URL), so the engine's multimodal cache key is unchanged and the prompt should contain the same
image tokens either way. `est_tokens` is unchanged in every cell above, and `prompt_tokens` is an
engine-reported field that a dry cell cannot produce. **So I did not measure a prompt-token rise
and I am not claiming one.** Whether the engine re-prefills a re-sent image or serves it from its
multimodal cache is an engine question that needs a live cell to settle; it is flagged under check 6
as unvalidated and is the one cost this report leaves open.

**Bounds this does not cross.** The extra bytes are uplink and request-body size only. No budget
charge, no `est_tokens`, no GPU-second spend and no decision changes in any cell (proofs 1 and 1b).

---

## Results consistency check

**1. Cross-check against committed measurements.**

| quantity | this run | prior run | source of prior | ratio | agree |
|---|---|---|---|---|---|
| CAL1F `warm-all-lru` HTTP 400s | 226 | 226 | `study_policy_v2_gate.md`, held-out section; task brief | 1.00 | agree |
| CAL1F 400s with no completed 200 on the same session | 226 of 226 (replay) | 0 of 226 had one (H100 log analysis) | task brief, from the H100's request logs | identical statement | agree |
| held-out cell 1 dashcam vs robot 400s | not re-measured; used to scope the dashcam split | 1,113 dashcam / 397 robot / 18 transport | `study_policy_v2_gate.md` | n/a | consistent |
| `warm-all-lru` releases with / without a frame store | 2,205 frames sent with a store; 0 without | 421 with a store / 412 without (releases, not frames) | `study_policy_v2_gate.md`, train/test confound section | different unit, not comparable | **flagged, not reconciled** - the prior figure counts RELEASES on a 16-device 1,200 s cell, this one counts FRAMES on a 12-device 600 s cell. Same name, different objects. No conclusion rests on either. |
| prescreen digests, all 50 arms, BEFORE side vs the committed PATCH 1 proof | 22 of 50 agree exactly | n/a | `results/orchestration/live2/v5/patch1_byte_identity_proof.json` (committed) | n/a | **28 of 50 DISAGREE - investigated and explained below** |
| `always-cloud-fcfs` digest / setwise / decisions | `d2f69d4eb94625b4` / `4569644595e1bc3c` / 13,570 | identical | same | 1.00 | agree, exactly |
| `b10-blocking-aware` decisions | 57,629 | 57,795 | same | 1.003 | disagree, explained below |
| mean committed `nexar_q90` frame size | 60,670 B (n=6,237) | n/a | measured here from `~/data/live2/jpeg/nexar_q90/frames` | n/a | first measurement |

No disagreement greater than 2x on any quantity a conclusion rests on.

**The 28 disagreements, investigated before any conclusion was written, as the protocol requires.**
They are NOT a fault in this run and they are NOT caused by this change. The committed PATCH 1
proof ran at `e04a7c0`; this run's base is `cc22429`, and **13 commits touched
`experiments/orchestration/live2/` in between**, several of which legitimately move decisions:
`eeea7e0` (EP-G dashcam bodies), `34a4af0` (per-frame upload, "and a charge error it exposes"),
`f1d32c7` (measured warm device latency, re-score), `88f4710` (v5-rules), `ea103f5` and `1e021f5`
(the v5 counterfactual engine and its frozen model), plus the RECENT-send fix and `e924005`. The 22
arms that still agree are the ones none of those touched. Decision COUNTS agree on 49 of 50; only
`b10-blocking-aware` moved (57,795 → 57,629, 1.003×, far inside the 2× line).

**So the committed PATCH 1 digests are NOT a usable positive control for this base, and I am not
quoting them as one.** This matters: quoting the single arm that happened to match
(`always-cloud-fcfs`) as "the committed value reproduces" would have been a true sentence standing
for a false claim - 28 of 50 do not reproduce, for good reasons. The control that IS valid is
proof 1 itself: both sides run at the SAME commit `cc22429`, in two worktrees, with the before side
unmodified (`git status` clean). See check 7 for the positive control that does hold.

**2. Physical plausibility.** The implied per-re-sent-frame wire cost is 410,260,275 / 4,739 =
**86,571 B**. A base64 data URL of a 60,670 B JPEG is 60,670 × 4/3 = 80,893 B, plus the JSON part
wrapper and escaping. The implied rate is **1.070× the base64 floor**, which is the right side of 1
and nowhere near 2×. The no-status condition gives 6,455,394,533 / 74,225 = 86,973 B, agreeing to
0.5 percent on a 15× larger part count. Nothing here is faster than its own floor, so there is no
caching artefact in the byte accounting.

**3. Distribution sanity.** Reported above: flips 1 / 5 / 9 / 12 / 88 (min / p25 / median / p75 /
max) over 439 bodies, per-body bytes 41.8 KB / 702.0 KB / 8.47 MB, all 12 sessions touched with 4
to 74 changed bodies each. **No constant appears where a distribution is expected.** Checked for
the other two shapes the protocol names: the spread is not an artefact spread (the values are
base64 image payload sizes, which is exactly what the column claims and is confirmed against the
measured JPEG distribution in check 2), and no effect is averaged into undetectability - the
`edf` zero is reported as its own stratum beside `warm-all-lru`'s 439 rather than pooled into a
mean over arms, because pooling them would read as a small effect everywhere when it is a large
effect on piece-chaining arms and exactly zero elsewhere.

**4. Definition audit.**

| object | definition used here | matches prior? |
|---|---|---|
| "bytes sent" | a frame for which `bodies.image_part` received a non-None `path`, so the body carries a base64 data URL | same as the pre-fix `sent_bytes_for` membership test; unchanged |
| "confirmed" | NEW object. The carrying request returned `http_status == 200`. Not first token, not `t_done` alone | no prior definition; named here |
| "uuid-only reference" | `{"type": "image_url", "image_url": None, "uuid": ...}` per `bodies.image_part` | unchanged |
| "dangerous reference" | NEW object, proof 3 only. A uuid-only reference for which no earlier request that carried that frame's bytes returned 200 before this request's `t_submit` | no prior definition; named here |
| frame identity in proof 3 | the `mm_uuid`, because that is what the engine resolves | the committed logs carry `mm_uuids` and not frame refs, so this is the only available identity; stated as a proxy under check 6 |
| `n_unresolved` (`epg_requests`) | broadened: any part carrying no bytes whose frame is not confirmed. Pre-fix it counted only frames unresolvable on disk | **the two agree exactly before the fix**, where `confirmed` and `sent` are the same set, so no committed value moves |
| `new_tokens_charged` (`epg_requests`) | `epg_prompt_tokens(n_new)`, the charge's own basis | pre-fix it was re-derived from the body and equal by construction; no committed value moves |
| the declared cell | seed 10, 12 devices, 600 s, mode A, dry, real-JPEG store | the trace generator and cell shape are `test_live2_history_size.py`'s committed fixture; the frame store is REAL JPEGs where the fixture writes 1-byte files, and that difference is the point (see check 6) |

**Two counters change value on EP-G runs and are named rather than left to drift:**
`epg_frames_sent_as_reference` falls and `epg_frames_sent_as_bytes` rises by the new
`epg_frames_bytes_resent_unconfirmed`. They count the wire, which is what their names claim, so
their post-fix values are correct and their pre-fix values are not comparable across the fix.

**Measured, on D153's own committed EP-G proof** (`epg_bodies_proof.py`, re-run on both trees):

| counter | before | after |
|---|---|---|
| `epg_frames_sent_as_reference` | 19,103 | **0** |
| `epg_frames_sent_as_bytes` | 2,099 | 21,202 |
| `epg_frames_bytes_resent_unconfirmed` | n/a | 19,103 |

**All six of that script's named proofs still pass on the patched tree** - `parity_law`,
`parity_body_vs_sh_ep`, `proof_a_cached_tokens_rise_and_reset`,
`proof_b_request_digest_identical_across_arms`, `proof_c_device_and_cloud` and its
`negative_control`, all `true` on both sides - so D153's release conditions are not broken by this
change. But the reference count going to **exactly zero** is the no-status condition again, not a
live result: `epg_bodies_proof.py` is a CPU-only dry builder, so it can never confirm anything and
every reference becomes bytes. **A dry EP-G body count is therefore not comparable across this
fix, and the zero must not be read as "EP-G no longer references".** On a live cell 200s arrive and
references resume; only the in-flight tail re-sends. Any EP-G cell quoting these counters must say
which side of the fix it is on and whether it was dry.

**5. Claim linkage.** This work bears on **no claim in `research/CLAIMS.md` or
`research/FORMULATION.md`**, and that is the correct answer rather than a gap. It is a
harness-correctness fix ruled as an implementation bug under D158 (2). It is INSTRUMENTAL to C5
(joint representation × placement × timing beats decomposed policies under a quality SLO) only in
that C5's evidence comes from live2 cells, and 24 percent of the held-out cell's requests were
non-200. Nothing here measures an object `FORMULATION.md §Scoping` scopes out: no KV moves between
tiers, and no cross-architecture KV portability is involved - the bytes in question are JPEG image
payloads in a request body.

**6. Proxy validity.** Four proxies, stated explicitly:

| proxy | what it actually measures | valid for the claim? |
|---|---|---|
| `mm_uuid` as frame identity in proof 3 | the engine's multimodal cache key, one per image part | **valid, and arguably better than the frame_ref** - the proof is about what the engine can resolve, and the uuid is what it resolves |
| HTTP 200 as "the engine has registered these bytes" | the moment the whole request completed | **conservative but not tight.** The engine registers an image earlier than its response; the 517-of-957 control measures that directly. Valid for correctness (it can only over-send), NOT valid for claiming the cost is minimal |
| a dry cell as the vehicle for proofs 1, 1b and 2 | the decision path and the body builder, with no engine | **valid for the decision and body claims**, which is all these proofs make. Invalid for any 400-rate claim, which is why proof 3 uses a real log |
| `nexar_q90` dashcam JPEGs as the byte size of ROBOT history frames | dashcam frame sizes, mean 60,670 B | **QUESTIONABLE and marked unvalidated.** The declared cell's byte totals use these for all frames including robot ones. Robot (D2) frames were not available on this box. The ×1.556 ratio is insensitive to this (it is a ratio of the same substitution on both sides), but the ABSOLUTE +410.3 MB is not, and is reported as an estimate |

The one headline that rests on a questionable proxy is the absolute megabyte figure; the ratios and
the part counts do not, and the part counts (+4,739, ×7.99 on CAL1F) are the register in which the
cost should be quoted.

**7. Validate the control, not only the result.**

- **Positive control.** `edf` is a committed arm whose decision digest must be unchanged by a
  wire-form fix. It is `6877544d4bc76a81` on both sides in both conditions, and its body diff under
  `--confirm200` is exactly 0 of 6,531. A known-good arm passes the check being applied, so the
  check is not broken. The 50-arm prescreen is the same control at scale: every one of the 50
  committed arms must be unchanged, and the pass is over all 50, not over a chosen subset.
- **A control that was TRIED AND REJECTED.** The committed PATCH 1 proof's digests looked like a
  ready-made positive control and are not one: 28 of 50 disagree because 13 live2 commits landed
  between its base and this one (check 1). It is recorded as rejected rather than quietly dropped,
  because the one arm that did match would have made a convincing-looking control out of a
  coincidence.
- **The control arm's own numbers.** `edf` 6,909 decisions and `warm-all-lru` 7,060 decisions are
  identical on the before side and the after side, and the before side ran in a separate worktree
  whose `coordinator.py` and `cstate.py` are verified byte-identical to `cc22429`
  (`git diff --exit-code` on both files, clean).
- **An impossible success was looked for and found.** `edf`'s 0-of-6,531 body diff under
  `--confirm200` is the shape that should raise an eyebrow: a fix that changes nothing on an arm
  that sends 3,392 reference parts could mean a dead switch. The no-status condition answers it (31
  bodies, 3,392 parts), so the zero is the absence of the race and not the absence of the fix. This
  is recorded because a reviewer watching only for implausible results would have read that zero as
  a pass.
- **Proof 3's own control.** The 517 of 957 successful requests carrying a dangerous reference is
  the unexamined side of that comparison, and it changes the reading: it turns "the mechanism
  explains the 400s" into "the mechanism is necessary for the 400s and is not sufficient". Had only
  the 226 been examined, the proof would have looked stronger than it is.

---

## Null classification

No null is reported. The one zero that could be read as a null - `edf`'s unchanged bodies - is
classified **unexercised, and demonstrated to be so**: the mechanism is reachable for that arm (31
bodies change when confirmation is removed) and no condition in the `--confirm200` cell reaches it,
because that arm never has a request in flight when the next one on the same session is submitted.
It is not a finding about the fix.

---

## What is owed and NOT done

- `research/EXPERIMENTS.md` has **no E-id row** for this work, and none was created. D158 (2) frames
  it as an implementation bug fix rather than an experiment, and `research/EXPERIMENTS.md`,
  `results/INDEX.md` and `research/STATUS.md` are outside the file ownership this session was given
  while five other sessions are editing them tonight. **The E-id row, the INDEX row and the STATUS
  date are owed and are the user's to place.**
- The ×7.99 CAL1F cost figure is a replay estimate. The real number comes from the re-run D158 (3)
  already schedules.
- Whether a re-sent image costs prompt tokens or is served from the engine's multimodal cache is
  **unmeasured**. It is the one open cost.

---

## Committed live2 test suites

Run on the clean tree at `cc22429` and on the patched tree. `experiments/orchestration/live2/tests/`:

| suite | baseline | patched |
|---|---|---|
| `test_live2_coord.py` | 26 OK | 26 OK |
| `test_live2_d114.py` | 16 OK | 16 OK |
| `test_live2_d118.py` | 26 OK | 26 OK |
| `test_live2_fakeserver.py` | 4 OK | 4 OK |
| `test_live2_fix.py` | 16 OK | 16 OK |
| `test_live2_fix2.py` | 22 OK | 22 OK |
| `test_live2_harness.py` | 33 OK | 33 OK |
| `test_live2_history_size.py` | 9 OK | 9 OK |
| **total** | **152 pass, 0 fail** | **152 pass, 0 fail** |

No committed test asserts a source literal that this change breaks, so none was edited.
`test_live2_fakeserver.py` is the one suite that puts requests through a real HTTP endpoint that
returns 200, so it is the only committed suite that exercises the promoter on a real status rather
than a dry one, and it passes.

`epg_bodies_proof.py` (D153's four release proofs plus the parity check and its own negative
control) passes on both trees: six of six `true`. Its counter movement is in check 4.

Import checks from the repo root, patched tree: `import hybrid`, `import arms`,
`import coordinator`, `import cstate` all OK.

---

## Outputs

| file | what |
|---|---|
| `results/orchestration/live2/racefix/proof1_byte_identity.json` | proof 1, 50 arms, before vs after |
| `results/orchestration/live2/racefix/proof12_confirm200.json` | proofs 1b and 2 and the cost, realistic condition |
| `results/orchestration/live2/racefix/proof12_nostatus.json` | proofs 1b and 2, negative control condition |
| `results/orchestration/live2/racefix/cal1f_replay.json` | proof 3 |
| `experiments/orchestration/live2/racefix_proofs.py` | the proof harness: `prescreen`, `prescreen-compare`, `side`, `compare`, `replay` |

Reproduce, from the repo root in each of two worktrees at the same base:

```
# proof 1 (about 30 min per side, pooled at 6)
python3 experiments/orchestration/live2/racefix_proofs.py prescreen <side>.json 6
python3 experiments/orchestration/live2/racefix_proofs.py prescreen-compare before.json after.json \
        results/orchestration/live2/racefix/proof1_byte_identity.json
# proofs 1b and 2 and the cost (about 2 min per side per condition)
python3 experiments/orchestration/live2/racefix_proofs.py side <side>.json --confirm200 \
        --arms warm-all-lru,edf
python3 experiments/orchestration/live2/racefix_proofs.py compare before.json after.json \
        results/orchestration/live2/racefix/proof12_confirm200.json
# proof 3 (seconds, no server)
python3 experiments/orchestration/live2/racefix_proofs.py replay \
        results/orchestration/live2/frozen_test/runs/warm-all-lru_n16_s4_1200s_h27_3t_L3_cal1f \
        results/orchestration/live2/racefix/cal1f_replay.json
```

`side` needs the committed `nexar_q90` JPEGs at `~/data/live2/jpeg/nexar_q90/frames` and refuses
to run without them rather than producing meaningless byte totals from a 1-byte fixture store.
