# StudyPERFRAME-upload: robot frames upload per frame as captured, for all arms (D154 (4))

Flash, CPU only. NO GPU, NO server, NO model, NO frame encoded, NO measurement.
Artifacts: `results/orchestration/live2/perframe/perframe_proofs.json`,
`experiments/orchestration/live2/perframe_upload_proof.py`.

Sections 1 to 3 (mechanism verification Steps 0 to 2) were written and checked BEFORE the proof
script was run, as CLAUDE.md requires; the numbered results below them were filled in after.

---

## 1. Step 0 — what would make this run uninterpretable, asked before it started

| asked before the run | answer | cost |
|---|---|---|
| Is the comparator about to change under me? | YES, partly. `fleet/data_sources.py` is being edited by another session right now (`ROBOT_DEADLINE_S`), and `HISTORY_BATCH_S` lives in the same file. **I added no constant there and edited nothing there**; the new contract's constants live in `fleet/trace.py` (`ROBOT_UPLOADS`, `ROBOT_UPLOAD_NOTE`) and the per-frame branch reads `DS.D2_STRIDE_S` and `DS.d2_batch_tokens`, which that session is not touching. A change to `ROBOT_DEADLINE_S` moves robot deadlines in BOTH modes equally, so it cannot turn this comparison. | one grep |
| Is a default about to be restored? | No. `batch-30s` IS the default and this change keeps it; the negative control below proves the default trace is byte-identical to the one `origin/main`'s own generator writes. | included in the control |
| Does a run I depend on key into my analysis? | No. Nothing here consumes another cell's output. The one external number I must reconcile against is the committed `d2_batch_tokens` accounting (`fleet/data_sources.py:149`). | - |
| Does the mechanism have a reachable path at this size and in this regime? | Checked before the sweep: at the proof cell the robots upload 41 batch records carrying 580 frames; per-frame makes 599 records. Both are far from zero and the counts differ by 14.6x, so there is something to see. Had the cell held no robot device the run would have been vacuous. | one trace generation |
| Could the proof be vacuous for the StudyEPG-bodies reason (no frame store)? | Yes, so the proof builds a resolvable placeholder store, runs `preflight.check` over it and records `n_unresolved`. Lesson 1 of StudyEPG-bodies, reused rather than rediscovered. | included |

One more, which is this row's own trap: **a proof taken over the trace FILE alone would be
circular.** The upload schedule is written by the trace generator, so of course it does not
differ by arm in the file. The cross-arm digest below is therefore taken over the uploads **as
the coordinator received them through the emulator**, which is where an arm could in principle
perturb them (uplink queueing is shared per device, and in mode B an arm's pulls occupy the same
uplink).

## 2. Step 1 — the causal chain

This row changes a CONTRACT and makes no policy claim, so the chain below is the one it enables
rather than one it tests; it is written out because every link has to be alive for the contract
change to mean anything downstream.

If robot frames reach the cloud AS CAPTURED rather than in 30-s batches (D150 SYNC (1), D154
(4)), then a session's believed history grows on the D2 2-s stride instead of in 15-frame steps
(`cstate.history_append`, FORMULATION.md warm-state continuity: the cloud's holding is what a
warm state can be built from), so at any decision epoch the cloud holds up to 30 s more of a
session's history than it did; a policy that warms or rebuilds reads that holding
(`coordinator._advance_build`'s `s.frames` and `s.est_tokens`) and therefore has a different,
larger and more current prefix available to prefill, and the reconstruction cost a question pays
(FORMULATION.md: the physical component of Context Inertia, which grows with context length) is
charged against a holding that is no longer up to 30 s stale. The price is paid on the uplink and
in request count: the same bytes arrive in 14.6x as many transfers.

The contract is also a FAIRNESS object, and that is the part this row must prove: the schedule is
a property of the trace, consulted by no arm, so no arm can gain or lose by it.

## 3. Step 2 — each link instantiated

| causal link | implementing quantity | value / range in this run | varies as expected? | evidence (the READ, not the write) |
|---|---|---|---|---|
| frames upload as captured | `history_batch` records emitted by `fleet/trace.py` robot loop | 599 records, 1 frame each, against 41 records of 1 to 15 frames | yes, 14.6x more records | read by `fleet/emulator.py:458` (`_upload`, charges the uplink) and `:476` (forwards as `history_append`) |
| the cloud's holding grows per frame | `cstate.history_append` → `s.frames`, `s.est_tokens` (`cstate.py:305-307`) | per-frame: +1 frame / +90 tok every 2 s; batch: +15 frames / +1,350 tok every 30 s | yes | read at `coordinator.py:652` (`s.frames[already:already + n_new]` chooses which frames a MATERIALIZE sends) and `coordinator.py:645` (`s.est_tokens` sets the build target) |
| the holding changes a warm/keep decision | `s.built_tokens < s.est_tokens` candidacy | varies per epoch and per session | yes | read at `coordinator.py:531` (warm candidacy) and `cstate.py:555` / `:595` (occupancy and capacity) |
| a recall's cost follows the holding | `tokens_for_representation` → `recall_gpu_s` | varies with `est_tokens` | yes | read at `coordinator.py:680-681` |
| the uplink pays for the extra requests | `links.UplinkQueue.send` occupancy and `queue_s` | 599 vs 41 transfers, 63,898 vs up to 958,470 bytes each | yes | read at `fleet/emulator.py:458-462` (arrival time) and reported in `run_meta.uplink` |
| no arm can see the schedule | the trace's upload records | identical across 6 arms (section 5) | **CONSTANT BY DESIGN, and that is the claim** | the schedule is written before any arm exists; no arm reads it |

Nothing here is write-only: every quantity above is read at a named line that changes either the
payload of a request, the target of a build, the cost charged, or the arrival time.

The last row is the one place a CONSTANT is the intended finding rather than a stopping
condition, and it is marked as such: the experiment in that row is the fairness proof, whose
hypothesis is equality.

---

## 4. The switch, and the exact flag for the H100

`--robot-upload per-frame`, with `batch-30s` the default. It is a property of the TRACE, so,
following the `--dashcam-format epg` precedent exactly:

* it reaches `trace.generate_trace(..., robot_upload=...)` and nothing else reads it;
* a per-frame cell gets **its own trace directory** (`..._A_perframe`) and its own fairness
  digest, so it can never reuse a committed `upload-30s` trace;
* it is appended to the **run tag** (`live2perframe<hash>` instead of `live2<hash>`), so a
  per-frame cell shares no engine-side cache entry and no per-device `cache_salt` with a
  committed cell;
* it is appended to the **cell label** (`... [robot-upload=per-frame]`), so every artefact that
  carries a label announces the contract;
* `header.json` carries `robot_upload` and `robot_upload_rule`, and `cell.json` carries
  `robot_upload`;
* `trace_meta.json` carries `robot_upload`, `robot_upload_rule`, and `history_batch_s = null`,
  because the 30-s period is a property of the other contract and a number that does not apply
  is worse than no number.

The exact argument string for the H100 is in section 12.

Files changed: `fleet/trace.py`, `run_live2_real.py`, `schema.py`, `fleet/events.py`, and the new
`perframe_upload_proof.py`. **`fleet/data_sources.py` was NOT touched** (another session owns it
tonight): no new constant was added there and `HISTORY_BATCH_S` is unchanged. `coordinator.py`,
`cstate.py`, `fleet/emulator.py` and every arm are UNCHANGED, because per-frame upload reuses the
committed record kind with its committed fields - the same rule that made D136's assistive class
need no new branch in the shared path.

---

## 5. THE CROSS-ARM DIGEST PROOF (the proof the user named explicitly)

**PASS, on six arms that differ in policy, taken over the UPLOAD records as the COORDINATOR
RECEIVED THEM through the emulator**, not over the trace file and not over whole decision logs.

Proof cell: seed 0, 8 devices (4 dashcam, 4 robot), 50:50, 300 s, mode A, no server, dry run.
Arms: `always-cloud-fcfs`, `edf`, `eco-llm`, `warm-all-lru`, `llf`, `mooncake`.

Each upload's row is `device_id | session_id | batch_id | t_arrive | ordered frame_refs |
cum_tokens`, digested in the order received, so the digest covers which device sent what, when it
ARRIVED over the emulated uplink, which frames it carried in which order, and the cumulative
history tokens it declares.

| mode | uploads per arm | upload digest | all six equal | pairwise differing rows vs `always-cloud-fcfs` |
|---|---|---|---|---|
| per-frame | 599, 599, 599, 599, 599, 599 | `65d09dec...91abbc` | **yes** | 0, 0, 0, 0, 0 |
| batch-30s | 41, 41, 41, 41, 41, 41 | `3a68b9d2...f2bb2e` | yes | 0, 0, 0, 0, 0 |

The committed fairness digest agrees arm by arm as well (`2dfc2301...` for all six in per-frame),
and every arm's run reports `digests_equal = true`, meaning the emulator presented the trace's own
event stream.

**Why this is not a tautology, stated three ways, because a digest comparison that cannot fail
proves nothing.**

1. **The arms demonstrably did different things on the same uploads.** Decision kinds, per arm,
   per-frame mode: `always-cloud-fcfs` 2,103 release_monitor + 8 release_recall; `edf` 2,103 +
   18 release_whole + 2 defer; `warm-all-lru` 2,103 + 588 release_piece + 8 release_recall;
   `llf` 2,103 + 10 release_whole + 8 decline + 1 defer; `mooncake` 2,103 + 8 state_action + 7
   release_recall + 1 decline. Engine-side requests per arm range 2,107 to 2,694. So the
   equality above is the equality of the INPUT across six arms that behaved differently, not the
   equality of six identical runs.
2. **Positive control (consistency check 7).** One row of one arm's stream was perturbed by ONE
   token (`est_tokens` + 1, row 299 of 599) and the comparison detected it: the digest changed
   and exactly 1 differing row was reported. The check can fail, so its passing means something.
3. **It holds by construction, not by discipline.** The upload schedule is written by
   `fleet/trace.py` from the session's own D2 capture grid before any arm exists, and no arm
   reads it. The same argument StudyEPG-bodies made for the episode frame list.

**Mode B (D69) has no exposure here** (lesson 3 of StudyEPG-bodies, checked rather than
assumed). `traces.pull_responder`, the function that silently dropped an EP-G episode to one
frame, rebuilds `monitor_frame` records only, and it belongs to the synthetic `run_live2_cell.py`
path, not the fleet grid. Robot history uploads are never pulled: they are pushed on the device's
uplink in both modes. Checked directly - the same cell generated and run in mode B gives 599
uploads whose `(batch_id, t_arrive, frame_refs, est_tokens)` tuples are **identical to mode A's**,
and `digests_equal` holds in both. Nothing was made to raise, because nothing degrades.

## 6. Step 2b — the switch reaches a decision

Run BEFORE anything was scored, one cell, the two modes.

* **upload records: 41 (batch-30s) against 599 (per-frame); differing rows 599; first difference
  at index 0** - batch-30s has `robo000 ... |b004` at t = 13.113704 carrying 7 frames for 630
  tokens, where per-frame has `robo003 ... |u00000` at t = 0.175166 carrying 1 frame for 90
  tokens. The two streams differ from their very first record.
* **the switch arrives with its declared type and value**, not merely passed:
  `trace_meta.robot_upload == "per-frame"` (a string from the declared choice set, validated
  against `ROBOT_UPLOADS` with a raise), `trace_meta.history_batch_s == null`, and
  `stats.robot_upload == "per-frame"`.
* **it reaches a DECISION, not only the trace.** The decision mix changes for four of the six
  arms: `edf` release_whole 5 -> 18 and release_recall 8 -> 0, `warm-all-lru` release_piece
  180 -> 588, `llf` decline 2 -> 8 and release_recall 6 -> 0, `mooncake` release_recall 8 -> 7
  with 1 decline. This is the ABSENT-LINK test passing: the contract is not merely instrumented,
  it moves what the coordinator does.

## 7. Step 3 — one traced unit, by hand

One robot session, `robo000|s000|1076761904546143_start_0.0_end_372.705`, joined part-way at
`join_offset_s = 106.886296` so t0 = -106.886296 on the run clock (D101). Its first ten uploads
under per-frame, every number read out of the trace and checkable by hand from
`d2_batch_tokens` (90 tok/image, 31-tok header once) and `E10A_SEMBER_Q88_D2_MEDIAN_B` = 24,570 B.

| upload | frame captured at (session clock) | offered at (run clock) | arrived at | frames | bytes | est_tokens | cum_tokens | budget charged |
|---|---|---|---|---|---|---|---|---|
| `history_preload` | 2.00 to 106.00 | 0.0 | 0.0 | 53 | 0 (D101) | 4,801 | 4,801 | none (no uplink, no GPU) |
| `|u00000` | 108.00 | 1.113704 | 1.150157 | 1 | 24,570 | 90 | 4,891 | none |
| `|u00001` | 110.00 | 3.113704 | 3.150157 | 1 | 24,570 | 90 | 4,981 | none |
| `|u00002` | 112.00 | 5.113704 | 5.150157 | 1 | 24,570 | 90 | 5,071 | none |
| `|u00003` | 114.00 | 7.113704 | 7.150157 | 1 | 24,570 | 90 | 5,161 | none |
| `|u00004` | 116.00 | 9.113704 | 9.150157 | 1 | 24,570 | 90 | 5,251 | none |
| `|u00005` | 118.00 | 11.113704 | 11.150157 | 1 | 24,570 | 90 | 5,341 | none |
| `|u00006` | 120.00 | 13.113704 | 13.150157 | 1 | 24,570 | 90 | 5,431 | none |
| `|u00007` | 122.00 | 15.113704 | 15.150157 | 1 | 24,570 | 90 | 5,521 | none |
| `|u00008` | 124.00 | 17.113704 | 17.150157 | 1 | 24,570 | 90 | 5,611 | none |
| `|u00009` | 126.00 | 19.113704 | 19.150157 | 1 | 24,570 | 90 | 5,701 | none |

Arithmetic, by hand: 53 x 90 + 31 = 4,801, the D2 header charged ONCE on the session's first
holding, which for a joined session is the preload (D101); every later upload is 1 x 90 with no
second header, so cum_tokens rises 4,801, 4,891, 4,981, ... in steps of exactly 90. The offer time
is the capture time on the run clock: t0 + 108.00 = 108.00 - 106.886296 = 1.113704, and it matches
to the microsecond for 599 of 599 records. The arrival is the offer plus the uplink serialisation
of 24,570 B plus RTT/2 = 0.036453 s, the same addend for every frame because every frame is the
same size.

**The same session under batch-30s**, which is the comparison that shows what the contract does:

| upload | offered at | frames | bytes | est_tokens | cum_tokens |
|---|---|---|---|---|---|
| `history_preload` | 0.0 | 53 | 0 | 4,801 | 4,801 |
| `|b004` | 13.113704 | 7 (f108 to f120) | 171,990 | 630 | 5,431 |
| `|b005` | 43.113704 | 15 | 368,550 | 1,350 | 6,781 |
| `|b006` | 73.113704 | 15 | 368,550 | 1,350 | 8,131 |

So at run time t = 12.0 the cloud has been told it holds **4,801 tokens** under batch-30s and
**5,431** under per-frame; at t = 42.0, 5,431 against 6,781. The frames are the same frames, in
the same order, with the same ids and the same bytes: 7 x 24,570 = 171,990 and 7 x 90 = 630, and
the cum_tokens of `|b004` and of `|u00006` are the SAME 5,431, which is the invariant the two
contracts must share.

**Which budget bound the decision: NEITHER.** An upload charges no accelerator time and no KV. It
charges the device's UPLINK (24,570 B, 0.036453 s, no queue ahead of it on this device) and it
moves the coordinator's believed holding, which is what the accelerator is later charged against
at `coordinator.py:645` and `:680`. The per-unit outcome of an upload is not both_met /
latency_miss / quality_miss, because an upload is not an opportunity: the outcomes on this cell
belong to the 8 robot questions and the 2,103 monitoring instants, and they are reported per arm
in section 5.

## 8. The cost change (requirement 4), on the declared cell

| quantity | batch-30s (before) | per-frame (after) | ratio |
|---|---|---|---|
| upload requests per run | 41 | 599 | **14.6x** |
| frames per request | 6 to 15 | 1 to 1 | - |
| tokens per request | 540 to 1,381 (mean 1,275.4) | 90 to 121 (mean 90.2) | 0.071x |
| total history tokens uploaded | 52,293 | 54,034 | 1.033x |
| uplink bytes per request | 147,420 to 368,550 | 24,570 (exactly, all 599) | 0.067x |
| total uplink bytes | 14,250,600 | 14,717,430 | 1.033x |
| total recall prompt tokens (trace side) | 95,828 | 95,828 | **1.000x, unchanged** |
| frame delivery delay, capture to arrival | p50 14.24 s, max 28.24 s, mean 13.82 s | **0.036453 s, every frame** | 390x faster at the median |
| uplink queue p99, worst device | 0.0 s | 0.014453 s | - |
| holding gap at a question (section 9) | 270 to 1,260 tok, 8 of 8 questions | 0 tok, 0 of 8 questions | - |
| engine requests, `warm-all-lru` | 2,288 (180 release_piece) | 2,694 (**588 release_piece**) | 1.18x total, **3.27x on prefill pieces** |
| engine requests, range over six arms | 2,108 to 2,288 | 2,107 to 2,694 | - |

**The 3.3 percent rise in total tokens and bytes is not noise and is explained to the token.**
It is 19 frames and one D2 header: 19 x 90 + 31 = 1,741 = 54,034 - 52,293 exactly, and
19 x 24,570 = 466,830 = 14,717,430 - 14,250,600 exactly. The 19 frames are the ones **batch-30s
loses at the run horizon**: it drops a window whose END falls after `run_s`, and with it the
frames that window had already captured before the horizon. Four sessions are affected (+2, +7,
+6, +4) and one of them, `robo001|s001`, receives NO upload at all under batch-30s and seven
under per-frame, which is where the one extra header comes from. Per session the batch-30s frame
stream is a strict PREFIX of the per-frame stream, checked for all sessions: no frame is
reordered, renamed or lost, and none is duplicated.

**YES, THE REQUEST COUNT RISES ENOUGH TO CHANGE WHAT THE ENGINE IS DOING, and that is a finding
about the contract rather than a detail.** Two distinct effects, which should not be conflated:

1. *On the uplink* the change is benign and slightly favourable. The same bytes move in 14.6x as
   many transfers, but each is 1/15 the size and they are spread over the capture grid instead of
   arriving in 30-s bursts, so total occupancy is unchanged and measurable queueing appears only
   at the millisecond scale (worst device p99 0.0 s -> 0.0145 s). D150's "about 1 percent of the
   link" survives.
2. *On the accelerator* it is NOT benign, because the believed holding now grows every 2 s
   instead of every 30 s, and an arm that materialises INCREMENTALLY finds work on far more
   epochs. `warm-all-lru` goes from 180 to 588 prefill pieces on this cell, a 3.27x rise in
   prefill requests for the same frames. At 32 devices this is the number to watch, and the H100
   should expect a per-frame cell to issue materially more, smaller prefill requests than its
   `upload-30s` namesake. Whether that helps or hurts is a policy result and is NOT claimed here.

## 9. The finding I did not expect, and did not specify for me

**Under batch-30s the coordinator is charged for a history up to 30 s staler than the one the
question's own record says the cloud holds.** `recall_question.history_tokens` is computed from
every D2 frame up to `t_ask` (`fleet/trace.py`, the `nfr` / `hist_tok` lines), while the
coordinator's belief is the `cum_tokens` of the last upload it has RECEIVED. On this cell the two
disagree on **8 of 8 robot questions under batch-30s, by 270 to 1,260 tokens (median 990)**, and
on **0 of 8 under per-frame, by 0 tokens**. Per-frame upload closes that gap to the uplink's own
latency.

This matters beyond bookkeeping, because `_submit_recall` costs a recall from the BELIEF
(`s.tokens_for_representation` -> `s.est_tokens`, `coordinator.py:680-681`). So every committed
`upload-30s` cell charged its recalls for up to 1,260 tokens LESS history than the trace says the
cloud held, and a feasibility test run on the honest number can come out differently: `llf`
declines 2 questions under batch-30s and 8 of 8 under per-frame on this cell. **This is not a
defect I introduced and I have changed nothing about it; it is the pre-existing inconsistency
that per-frame upload removes.** It is also a reason a per-frame cell must never be compared
against a committed `upload-30s` cell, which is why the contract is in the trace directory, the
run tag and the cell label.

Not a measurement: this cell ran with no server and `dry_run`, so the per-arm counts above
indicate direction and order of magnitude, not a result.

## 10. Step 4 — the negative control

With the switch at its default the mechanism vanishes completely, checked against a generator
read **out of git** rather than out of my own working tree
(`git show origin/main:experiments/orchestration/live2/fleet/trace.py`). Origin moved three
times while this row was being written, so the control was re-run against each of `df586a0`,
`6d42a59` and `25d55b9` and passed on all three:

| check | result |
|---|---|
| records byte-identical to origin/main's generator, same cell | **true**, 2,177 records |
| device_answers byte-identical | **true** |
| trace digest | `65602e0a...7ef6679` both sides |
| fairness digest (mode A) | `25bb1171...9a57ea3` both sides |
| `robot_upload` under the default | `"batch-30s"` |
| `history_batch_s` under the default | 30.0 (unchanged) |
| keys ADDED to stats | `robot_upload`, `robot_history_uploads`, `robot_history_frames`, `robot_history_tokens` |
| keys ADDED to meta | `robot_upload`, `robot_upload_rule` |
| upload records under the default | 41, carrying 580 frames, exactly as before |

So the committed trace is reproduced to the byte and the new counters are additive. The control
also confirms the two modes are not accidentally the same code path: `batch_stream_is_a_prefix`
is true and the two traces have different sha256 (`65602e0a...` against `79c357e8...`).

## 11. Step 5 — the alternative explanation

The headline here is an EQUALITY (the cross-arm digest), so the alternative to rule out is not a
rival mechanism but a vacuous proof. Three candidates and what distinguishes them:

* **(a) the upload stream is identical because it is a property of the trace** [the claimed
  mechanism]. Distinguished by: the arms demonstrably differ on the same input (section 5, item
  1), and the digest detects a one-token perturbation (item 2).
* **(b) the digest is identical because it is computed off the trace file for every arm, so the
  emulator and coordinator were never in the loop** [the circularity]. Distinguished by: the
  digest is taken over the events `cstate.history_append` actually received, including the
  emulator's own `t_arrive`, and the value differs from the trace-file digest
  (`65d09dec...` against `928bd6cb...`) precisely because the file carries offer times and the
  coordinator receives arrival times.
* **(c) the digest is identical because no arm was offered anything to differ about - a run in
  which nothing happened** [the unexercised case]. Distinguished by: 2,107 to 2,694 engine
  requests per arm, 2,111 to 2,699 decisions, and four of six arms changing their decision mix
  between the modes.

Nothing distinguishes (a) from "the uplink was never contended", and it does not need to: under
per-frame the worst device's uplink queue p99 is 14.5 ms and non-zero, so the uplink WAS
contended and the arrival times still agreed arm for arm.

## 12. Results consistency check

**1. Cross-check against committed measurements.**

| quantity | this run | prior run | source of prior | ratio | agree |
|---|---|---|---|---|---|
| D2 tokens per 352x256 image | 90 | 90 | `fleet/data_sources.py:149` / `:48` (StudyRH4) | 1.000 | agree |
| D2 header tokens, once per session | 31 | 31 | same | 1.000 | agree |
| per-frame `est_tokens` | 90, and 121 on a session's first holding | 90 / 121 by the committed law | `d2_batch_tokens(1, first)` | 1.000 | agree |
| every history record obeys `d2_batch_tokens` | 603 of 603 | the law itself | same | 1.000 | agree |
| `cum_tokens` equals the session's running total | 603 of 603 | CONTRACT.md "history size" | `emulator._cumulative_tokens` | 1.000 | agree |
| D2 stride | 2.0 s | 2.0 s | `data_sources.D2_STRIDE_S` (StudyRH4) | 1.000 | agree |
| history frame bytes | 24,570 B, all 599 | 24,570 B | `E10A_SEMBER_Q88_D2_MEDIAN_B` | 1.000 | agree |
| total history tokens, batch-30s | 52,293 | 52,293 | this run's own pre-measurement before the switch existed | 1.000 | agree |
| total history tokens, per-frame | 54,034 | 52,293 + 19 x 90 + 31 = 54,034 | derived from the committed law | 1.000 | **reconciled exactly, section 8** |
| total uplink bytes, per-frame | 14,717,430 | 14,250,600 + 19 x 24,570 = 14,717,430 | same | 1.000 | **reconciled exactly** |
| trace default byte-identity | identical | `origin/main` `df586a0`, `6d42a59`, `25d55b9` | git | 1.000 | agree |

No quantity disagrees by more than 1.033x, and that one is explained to the token rather than
chosen between. **The 2x stop condition was not reached.**

**2. Physical plausibility.** The one implied rate is the uplink. A 24,570-byte frame arrives
0.036453 s after capture, of which the RTT/2 is a fixed addend; 24,570 B in the serialisation
`links.serialise_s` at the committed per-device uplink gives exactly the 0.036453 s every frame
shows, and a batch of 15 frames (368,550 B) takes 15x the serialisation, which is why its p50
delivery is 14.24 s rather than 0.036 s. Nothing here is faster than a committed curve because
nothing here is timed on hardware: no GPU ran, no server ran, and the only "latency" is the
emulator's own arithmetic. For the same reason no result can be a caching artefact.

**3. Distribution sanity.** Spreads are reported beside every median above. Two CONSTANTS appear
where a reader might expect a distribution, and both are checked rather than trusted:
- `frame_bytes` is 24,570 for all 599 records. That is correct and not short-circuiting: every
  D2 frame is the same committed median size, and the batch mode's own records are integer
  multiples of it (147,420 = 6 x 24,570 up to 368,550 = 15 x 24,570).
- the per-frame arrival delay is 0.036453 s for all 599 frames, to six decimals. Same cause: an
  identical payload on an identical link with no queueing ahead of it. The DISTRIBUTION it
  replaces is reported beside it (batch-30s: min 0.123, p50 14.239, max 28.239, mean 13.824), and
  the batch-mode spread of 28 s across 580 frames is what shows the constant is a real collapse
  and not a lost variable.
- the artefact-spread shape is checked too: `tokens_per_request_mean` 90.207 is not a spread at
  all, it is 90 with four sessions' 31-token headers averaged in over 599 records
  (599 x 90 + 4 x 31 = 54,034), so the column cannot be read as per-frame variation.
- the averaged-out shape: the 1.033x token rise is a population figure that conceals a stratum
  where the effect is total. On `robo001|s001` the change is 0 frames to 7, i.e. the whole
  session's history, and that stratum is reported beside the mean rather than inside it.

**4. Definition audit.**

| object | definition in this run | prior committed definition | matches |
|---|---|---|---|
| "upload" / `history_batch` record | one `history_batch` record; batch-30s packages a 30-s window, per-frame packages ONE frame | D68: a 30-s window | **same name, two packagings, declared**: the record kind and all its fields are unchanged, `trace_meta.robot_upload` says which contract, and the two never share a trace directory |
| `est_tokens` on the wire | the session's CUMULATIVE history tokens after this upload | CONTRACT.md "history size", the 2026-11-18 fix | same |
| `batch_id` | the upload's unique id: `<play>|b<nnn>` under batch-30s, `<play>|u<nnnnn>` under per-frame | unique upload id | same role, distinct spelling so the two can never collide in a joined analysis |
| `robot_history_batches` (stat) | the number of upload RECORDS, which is 14.6x larger under per-frame | number of upload records | same definition, different value: **`fleet/eligibility.py:94` reads this stat for the D97 entry points, so a per-frame cell's entry table must be recomputed and must not be compared with a committed one.** Flagged, not changed: `eligibility.py` is not mine. |
| a "frame" | one D2 capture on the 2-s stride, 90 tokens, 24,570 B | StudyRH4 | same |
| `history_batch_s` (meta) | `null` under per-frame, 30.0 under batch-30s | 30.0 | deliberately narrowed; no reader consumes it (checked by grep: one producer, no consumer) |

No name is used with two different token counts; the one name that carries two packagings is
declared in the meta of every trace.

**5. Claim linkage.** This row bears on no CLAIMS.md claim and produces no policy result. It is
the contract D154 (4) orders, and the quantities it produces are counts and times of what the
fleet uploads. It bears on FORMULATION.md's physical component of Context Inertia only as an
enabler: the holding a warm state is built from is now current to 36 ms rather than to 30 s.
Nothing measured here is scoped out: no KV moves between tiers, and no cross-architecture
transfer is involved. The one result that touches a policy axis - section 9's decline counts - is
labelled as a dry-run indication and explicitly NOT offered as a finding about `llf`.

**6. Proxy validity.** Three proxies, all labelled.
(i) The frame store holds **PLACEHOLDER bytes**, not JPEGs: valid for a wire-form proof and for
nothing else, and no score is computed from them. `preflight.check` resolved 2,968 of 2,968
(batch) and 2,987 of 2,987 (per-frame) references with `n_unresolved = 0` and `n_empty = 0`, so
lesson 1's failure mode (every frame a uuid-only reference, a perfect proof of nothing) is
excluded by measurement rather than by assumption.
(ii) Uplink times are the emulator's `links.serialise_s` arithmetic, not a measured network: a
model, labelled, and identical across arms by construction, which is all the fairness proof
needs.
(iii) The per-arm request and decision counts come from a **dry run with no server**, so they
proxy "what the coordinator decided" and not "what an engine did". Used only to show the switch
reaches a decision and to size the prefill-request rise; not used for any headline.

**7. Validate the control, not only the result.** The control arm here is the `batch-30s`
condition, and it was checked on its own numbers BEFORE the comparison was read: 41 upload
records carrying 580 frames for 52,293 tokens, byte-identical to what `origin/main`'s own
generator writes on the same cell, with the same trace digest and the same fairness digest. A
"before" condition that did not reproduce the committed trace would not be a before condition.
The positive control is twofold: the committed test suites below still pass (so the checks are
not broken), and the digest comparison itself was shown to detect a one-token perturbation (so
the equality is not an impossible success).

## 13. Tests

| suite | result |
|---|---|
| `tests/test_live2_coord.py` | 26 OK |
| `tests/test_live2_d114.py` | 16 OK |
| `tests/test_live2_d118.py` | 26 OK |
| `tests/test_live2_fakeserver.py` | 4 OK |
| `tests/test_live2_fix.py` | 16 OK |
| `tests/test_live2_fix2.py` | 22 OK |
| `tests/test_live2_harness.py` | 33 OK |
| `tests/test_live2_history_size.py` | 9 OK |
| `fleet/tests/test_live2_fleet.py` | 234/234 checks |

**No committed test failed**, and none was edited. Lesson 4 of StudyEPG-bodies was the reason to
check specifically:
`test_live2_fix2.test_the_nexar_frame_ref_is_the_one_the_trace_puts_on_the_wire` asserts the
SOURCE LITERALS `f"{clip}|t{t_local:07.2f}"` and `f"{sid}|f{x:08.2f}"` appear in
`fleet/trace.py`. The per-frame branch spells the frame ref with the SAME literal
`f"{sid}|f{x:08.2f}"` rather than reusing a comprehension or a helper, deliberately, so the
source-literal guard still guards. The committed 30-s branch was not reformatted at all: it is
left at its own indentation under an `else:` with a comment saying why, so the diff shows no
reflow of a committed code path.

Beyond the committed suites: `count_only` stats are IDENTICAL to the full build under per-frame on
three cells (seed 0 / 8 / 50:50, seed 3 / 16 / 40:40:20, seed 4 / 12 / 25:75), which is check (h)
of the fleet suite applied to the new branch - the per-frame path is a SKIP of record building,
not a second implementation.

**End-to-end runner smoke test**, the flag through the real runner rather than through the proof
script: `--arm edf --seed 0 --n-devices 8 --ratio 50:50 --run-s 120 --mode A --robot-upload
per-frame --no-split --no-score`, no server. It produced the trace directory
`seed0_n8_120s_A_perframe`, `header.label = "StudyLIVE2 real-server cell
[robot-upload=per-frame]"`, `header.robot_upload = "per-frame"` with its rule text,
`cell.json.robot_upload = "per-frame"`, `run_valid = true`, `digests_equal = true`, 782 requests,
0 errors, and emulator scheduling lateness p99 0.2472 ms against the 50 ms guard. So the 14.6x
rise in upload events did NOT cost the emulator its clock at this size.

Import paths, run the way the harness imports them (lesson 5), BEFORE and AFTER the rebase onto
`origin/main`: `import hybrid`, `import arms`, `import coordinator`, `import schema`,
`import run_live2_real` with only `live2/` on `sys.path`, and `import trace`, `import events`
with only `live2/fleet/` - all succeed.

## 14. For the H100

**The whole handshake is one flag:**

```
--robot-upload per-frame
```

appended to the cell's existing argument string, for example

```
python3 experiments/orchestration/live2/run_live2_real.py \
  --arm <arm> --seed <seed> --n-devices <n> --ratio 40:40:20 --run-s 1200 --mode A \
  --robot-upload per-frame \
  --frames-root <store> --server <url> --calibration <cal> --out <run dir>
```

The default is `batch-30s`, so an argument string without the flag runs the committed contract
unchanged. What to expect, and what to check on the first cell:

* a NEW trace directory, `seed<seed>_n<n>_<run_s>s_A_perframe` (plus the ratio / question-set
  suffixes as before), and a new fairness digest. It will NOT reuse a committed trace.
* a NEW run tag, `live2perframe<hash>` instead of `live2<hash>`, so no engine-side cache entry
  and no per-device `cache_salt` is shared with a committed cell. The cell label gains
  ` [robot-upload=per-frame]`.
* `header.json` carries `robot_upload` and `robot_upload_rule`; `cell.json` carries
  `robot_upload`.
* **about 14.6x as many robot upload events**, each 1/15 the size. At 32 devices expect the
  robot upload event count to scale with it; the emulator's own scheduling lateness is the thing
  to watch, since the number of heap events per run rises accordingly (`run_valid` and
  `lateness.p99_ms <= 50` are the existing guards and they are the right ones).
* **materially more, smaller prefill requests from incrementally-materialising arms**
  (`warm-all-lru` 180 -> 588 pieces on the 8-device 300 s cell). If the engine's queueing changes
  shape, that is the contract and not a bug.
* `fleet/eligibility.py` reads `robot_history_batches` for the D97 entry points, so a per-frame
  cell's entry table must be RECOMPUTED; do not read a committed one.

## 15. What I decided that was not specified

1. **The record KIND is unchanged.** A per-frame upload is a `history_batch` record carrying one
   frame, not a new kind. This is why `coordinator.py`, `cstate.py`, `fleet/emulator.py`,
   `bodies.py`, `hybrid/*` and every arm are untouched, and why the proof has no new branch in
   the shared path to worry about. It follows D136's rule for the assistive class and it is what
   keeps the byte-identity gate strong. The cost is that the name `history_batch` now covers two
   packagings, which section 12 check 4 declares.
2. **`batch_id` is spelled `|u<nnnnn>` under per-frame** rather than `|b<nnn>`, so an id from one
   contract can never be mistaken for or collide with an id from the other in a joined analysis.
3. **No constant was added to `fleet/data_sources.py`**, which another session owns tonight. The
   period is not needed at all under per-frame (the schedule is the D2 capture grid, i.e.
   `D2_STRIDE_S`, which is already committed there), so nothing had to be added anywhere.
   `HISTORY_BATCH_S` is untouched and still drives `DEFAULT_STAGGER_S`, so the device start
   stagger is IDENTICAL in both modes and is not silently coupled to the upload contract.
4. **`history_batch_s` in the meta is `null` under per-frame** rather than 30.0. A number that
   does not apply is worse than no number; checked by grep that nothing reads it.
5. **The 19 extra frames at the run horizon were kept, not trimmed.** Per-frame delivers every
   frame captured before `run_s`; batch-30s drops a whole window whose end falls past the
   horizon. Trimming per-frame to match would have made the two modes agree on a count by
   reintroducing the very truncation the contract exists to remove. It is reported, reconciled to
   the token, and labelled an intended difference in `ROBOT_UPLOAD_NOTE`.
6. **Six arms, not four**, for the digest proof, including `mooncake` (a D155 (5) proactive arm)
   and `llf`, so the proof covers an arm that issues state actions and one that declines.
7. **The uplink-arrival time is inside the digest.** It would have been easier to digest the
   trace's offer times; including `t_arrive` is what makes the proof cover the emulator rather
   than just the file, and it is what makes the mode-B check meaningful.

## 16. Mechanism verification summary

Steps 0, 1, 2 in sections 1 to 3 (written before the run); Step 2b in section 6; Step 3 in
section 7; Step 4 in section 10; Step 5 in section 11. No link is ABSENT or CONSTANT except the
one whose constancy IS the claim, and that one is marked. **This row reports no null**, so Rule 2's
classification does not apply; the one equality it reports is a fairness property proved by
construction, with a positive control showing the check can fail.
