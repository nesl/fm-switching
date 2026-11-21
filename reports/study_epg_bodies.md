# StudyEPG-bodies: the EP-G dashcam bodies wired into live2 (D153)

Flash, CPU only. NO GPU, NO server, NO model, NO new frame encoded, NO measurement.
Artifacts: `results/orchestration/live2/epg/epg_proofs.json`,
`experiments/orchestration/live2/epg_bodies_proof.py`.

## What was asked and what was done

D153 fixes the dashcam format BY THE TASK: every dashcam query, device and cloud, carries the
append-only episode context of D148, which is EP-G as StudySH-EP ran it, and never one frame per
call. Today's live contract was the opposite (`bodies.py` RAISED on a monitor body with more than
one frame, and `coordinator.py` built exactly one frame), so this is a real change to the contract
every arm sends.

What landed, behind a switch that is OFF by default:

* `bodies.py` takes `dashcam_format` ("oneframe" default, "epg"). Under "epg" the monitoring body
  is the episode's frames oldest first with the COUNT-FREE multi-frame header, StudyD3's question
  and StudyD3's generation parameters. The multi-frame header literal is READ out of the committed
  `sh_ep_manifest.HEADER_MULTI` rather than retyped, as `SH_QUERY` and `SH_GEN` already are. A
  ONE-frame body still carries StudyD3's committed one-frame literal, and under "oneframe" the
  builder still REFUSES more than one frame, so the committed contract cannot be left by accident.
* `fleet/trace.py` emits the episode frame list per `monitor_opportunity`
  (`episode_id`, `episode_index`, `frame_refs`, `episode_frames`), deterministically and
  independently of any arm's decisions, and drops the sub-floor instants.
* `coordinator.py` copies the episode off the wire and DERIVES NOTHING; already-sent frames go as
  uuid-only references and only the new frame carries bytes.
* `fleet/emulator.py` forwards the four fields, exactly as the trace wrote them and only if it
  wrote them. `schema.py` and `fleet/fleet/events.py` carry them as OPTIONAL fields, the pattern
  `category` already set.
* `run_live2_real.py` takes `--dashcam-format epg` and `--dashcam-min-frames N`; the format is a
  property of the TRACE, so it gets its own trace directory and its own fairness digest.

Per-device `cache_salt` is unchanged (D84).

## The refresh: PROVISIONAL, the literal reading of D153

D153 says "fresh context after N s with no carry-over", which is NOT StudySH-EP's sliding cap:
SH-EP capped EP-G at the last 21 frames and its cap bound exactly at its last instant, so SH-EP
never exercised a refresh at all and cannot settle this. Implemented as **a fresh context every
21 frames with no carry-over**, N = 21 frames = 10.5 s at the 0.5 s cadence, matching SH-EP's cap.
Marked PROVISIONAL in `trace.EPG_REFRESH_NOTE`, in `trace_meta.json` of every EP-G trace, and
here. A ruling for the sliding cap changes one function, `trace._epg_episode`.

The minimum-frame floor is ONE named constant, `trace.EPG_MIN_FRAMES = 3`, and a parameter
(`dashcam_min_frames`), so raising it to 6 is a flag and not an edit.

## THE PARITY CHECK (the H100 asked for this in the proof artefact)

StudySH-EP's committed 32B EP-G records obey `prompt_tokens = 42 + 338 x n_frames`, re-derived
here from the records rather than assumed:

| quantity | this run | committed source | agree |
|---|---|---|---|
| records scored | 3,898 | `results/dashcam/study_sh_ep/h100/sh_ep_requests_32BI_shep2-EP-G.jsonl.gz` | - |
| deviation from the law | 3,895 at 0, 3 at -2 | same | yes |
| tokens per frame, SOLVED from the data | 338 | code constant 338 | yes |
| text tokens, SOLVED from the data | 42 | code constant 42 | yes |
| `prompt_tokens` at n = 21 | 7,140, the only value, 287 records | `epg_prompt_tokens(21)` = 7,140 | yes |

The solve uses the MODAL `prompt_tokens` per frame count: anchored on one of the three outlying
records it returns 338.1 per frame and reports a disagreement that is really three records.

Stronger than the law: one of this builder's bodies was compared PART FOR PART against
`sh_ep_runner.build_body`'s on the same committed EP-G manifest row (`00005_EP-G_t0014.75`,
9 frames), with `--header-mode constant` as the committed EP-G run used. The two normalise to the
same object: same header literal, same ordered image parts with the same bytes-versus-reference
status, same question, same `temperature` / `max_tokens` / `seed` / `logprobs` / `top_logprobs`.
Declared exemptions, all pre-existing: the served model name, `cache_salt` (D84), the uuid values
(D84; their ORDER and their bytes-versus-reference status ARE compared), and
`stream` / `stream_options`, which live2 needs in order to time the first token.

## The four proofs (D153)

Proof cell: seed 0, 8 devices, 50:50, 300 s, mode A, four arms
(`always-cloud-fcfs`, `edf`, `eco-llm`, `warm-all-lru`). Headline cell for proof (d): seed 4,
16 devices, 40:40:20, 1200 s.

### (a) cached tokens rise frame by frame within an episode and RESET at refresh

PASS on the constructed bodies: 1,871 monitoring requests, 1,757 rises, 110 resets, 0 violations.
The traced unit, `dash000`'s first two episodes:

| t | frames | bytes | references | shared prefix with the previous request | prompt tokens |
|---|---|---|---|---|---|
| 29.6 | 3 | 3 | 0 | 0 (first of episode) | 1,056 |
| 30.0 | 4 | 1 | 3 | 3 | 1,394 |
| 30.5 | 5 | 1 | 4 | 4 | 1,732 |
| ... | ... | 1 | ... | ... | ... |
| 38.5 | 21 | 1 | 20 | 20 | 7,140 |
| 40.1 | 3 | 3 | 0 | **0, the refresh** | 1,056 |

Every request's own `est_tokens` equals `42 + 338 n` exactly, and the test asserts the prefix grows
by EXACTLY one frame or resets to zero, never anything in between.

**What this is and is not.** No GPU was used, so what is shown is the only thing that drives
cached tokens: which frames carry bytes, which carry a uuid-only reference, and how long the
prompt prefix the next request shares with this one is. The count-free header makes that prefix
reusable and the question sits AFTER the images, so the shared prefix is the header plus the
shared frames. **The engine-side confirmation - vLLM's own `cached_tokens` rising and resetting -
is the H100's run and is NOT claimed here.** The expected cached tokens are also a LOWER bound:
the engine rounds to block boundaries.

This proof found a real fault in its own first version. Run without a frames root, every frame
went as a uuid-only reference (`coordinator._path` returns None for a frame it cannot find, and
`bodies.image_part` then emits the reference form), so the first run showed a perfect rise with
ZERO frames carrying bytes, which proves nothing. The proof now builds a placeholder store and
`preflight.check` confirms 2,966 of 2,966 refs resolve. The instrumentation also counts references
off the frames actually built rather than off the sent-set, and records `n_unresolved` so a
reference claimed for bytes that were never uploaded is visible rather than silent.

### (b) the request digest is identical across arms

PASS. All four arms released all 1,871 decision instants they were offered, and on all 1,864
shared opportunities the body digest is IDENTICAL across every pair (`always-cloud-fcfs` against
each of `eco-llm`, `edf`, `warm-all-lru`: 0 differing). `body_digest` is sha256 over the wire body
with the internal block removed, so it covers the header, every image part, the question, the
generation parameters and the `cache_salt`.

Taken over the dashcam BODIES, not over whole decision logs, on the coordinator's instruction and
for a reason: since PATCH 1 `warm-all-lru` legitimately issues prefill decisions it previously did
not, so the logs now differ by arm for reasons that have nothing to do with EP-G. The property
holds BY CONSTRUCTION rather than by discipline, because the episode frame list is the trace
generator's and is a function of the capture index alone.

### (c) device and cloud bodies carry the same frames and the same prompt

PASS on the bodies: over 40 instants, the device-side and cloud-side bodies built from the same
episode frame list differ in exactly one top-level key, `model`, and their message content is
byte-identical (same header, same ordered frames, same question).

**The limitation, stated rather than papered over.** live2's device does not build a body at all:
its answer is a committed pre-computed score from `fleet/data_sources.orin_dense_scores`, and
those are StudyORIN1-dense **N = 1 one-frame** scores. So a run made tonight has EP-G cloud bodies
against one-frame device answers. StudySH-EP measured the 4B device proxy under EP-G
(`sh_ep_requests_4BI_shep1.jsonl`), and wiring those scores needs `fleet/data_sources.py` and the
scorer, which this session does not own. **This is an open gap for whoever owns those files, and it
bears on any quality comparison between device and cloud under EP-G.**

### (d) the excluded-instant count per run, at floor 3 and at floor 6

| cell | captured instants | episodes | decision instants (floor 3) | excluded at floor 3 | excluded at floor 6 | decision instants (floor 6) |
|---|---|---|---|---|---|---|
| proof, seed 0, 8 dev, 300 s | 2,104 | 115 | 1,874 | 230 (10.93 %) | 572 (27.19 %) | 1,532 |
| headline, seed 4, 16 dev, 1200 s | 13,193 | 715 | 11,764 | 1,429 (10.83 %) | 3,564 (27.01 %) | 9,629 |

Both floors are counted in every run whichever one is applied, so the cost of raising the floor to
6 is readable off a run made at 3; the floor-6 count derived from a floor-3 run agrees exactly with
a run actually made at floor 6, in both cells. Excluded instants are excluded identically for
every arm because they are **not emitted as opportunities at all**, so no arm can see them. Their
frames are still CAPTURED and still enter the episode context, and their uplink bytes are charged
to the first decision instant that carries them (191,694 bytes at the floor instant, 63,898 after),
so no byte is lost and the uplink total is arm-independent.

## Step 2b: the switch reaches a decision

Run BEFORE anything was scored, one cell, `edf`, same seed and fleet, the two formats:

* decisions: 1,884 (epg) against 2,117 (oneframe); differing decisions 2,117; the first difference
  is at index 0, `release_monitor` at t = 8.7 against t = 7.6.
* bodies on the 1,864 shared opportunities: 1,864 differ.
* frames per request: 3 to 21 (epg) against 1 (oneframe).

## Negative control

With `dashcam_format` left at its default the mechanism vanishes completely: no episode field on
any `monitor_opportunity`, every EP-G counter zero, the run reports `dashcam_format="oneframe"`
with no EP-G summary at all, all 2,103 monitoring requests carry exactly ONE frame, and the only
header seen is StudyD3's committed one-frame literal. The builder also still refuses a multi-frame
monitoring body unless EP-G is asked for ("the committed SH body is one frame per call, got 2;
D153's episode body needs dashcam_format='epg'").

## THE COST-ACCOUNTING DECISION I HAD TO MAKE, which was not specified

An EP-G request's PROMPT is the whole episode; its PREFILL is only the frames the engine has not
seen. These are different numbers and the budget needs the second one.

* `est_tokens` carries the whole episode prompt (the parity law), because that is what the engine
  will report and what the request log and token accounting must show.
* the GPU budget is charged the NEW tokens, `42 + 338 x (frames carrying bytes)`.

Why: charging the whole prompt every turn prices an append-only episode as a cold rebuild and
denies the mechanism D148 exists to exercise. It is also not what live2 does anywhere else -
`_advance_build` charges a history append `recall_gpu_s(piece)` for the PIECE, not for the
cumulative prompt. **The difference is not academic.** Under the whole-prompt charge the proof
cell's run exhausts its 300 GPU-s budget after 429 of 1,874 decision instants (the whole-prompt
charge would be 1,294 GPU-s), so the arms would have been compared on budget rationing rather than
on scheduling. Under the new-tokens charge all four arms spend 152 to 161 GPU-s, take 0 budget
refusals and release every instant. The charge is conservative by the header's own text tokens,
which ARE in the shared prefix and are charged again, because StudySH-EP measured the 42 text
tokens together and splitting them would be an invented number.

`costs.episodic_gpu_s` is used for neither: it reads a committed `PROMPT_TOK` table keyed by the
three measured frame counts {1, 3, 9} and has no entry for an episode of 10 to 21 frames.
`experiments/orchestration/baselines/costs.py` was NOT touched.

## Results consistency check

1. **Cross-check against committed measurements.**

| quantity | this run | prior | source of prior | ratio | agree |
|---|---|---|---|---|---|
| monitor instants, seed 4 / 16 dev / 1200 s | 13,193 | 13,193 | flash session's own pre-measurement | 1.000 | agree |
| dashcam plays | 189 | 189 | same | 1.000 | agree |
| excluded at floor 3 | 1,429 | 1,429 | same | 1.000 | agree |
| EP-G tokens per frame | 338 | 338 | StudySH-EP 32B EP-G records | 1.000 | agree |
| `prompt_tokens` at n = 21 | 7,140 | 7,140 | same | 1.000 | agree |
| EP-G cap frames | 21 | 21 | `sh_ep_manifest.EP_G_CAP_FRAMES` | 1.000 | agree |
| cadence | 0.5 s | 0.5 s | `sh_ep_manifest.FPS_STEP` | 1.000 | agree |
| prompt tokens per run | 45,476,142 | 46,260,494 | flash session's own pre-measurement | 0.983 | **reconciled, see below** |

The one disagreement is 1.7 % and is explained exactly, not chosen between: the prior figure
counts a request at EVERY captured instant, including the 1,429 the floor excludes. Those 1,429
instants would carry 2,143 frames (one at each cycle's first instant, two at its second), and
`46,260,494 - 42 x 1,429 - 338 x 2,143 = 45,476,142`, which is this run's figure to the token.

2. **Physical plausibility.** No latency, throughput or size is measured here. The one derived
rate is the budget charge, `new tokens / 5,600 tok/s`, which is the committed 32B prefill rate
`costs.PREFILL_TOK_S` unchanged; nothing here is faster than a committed curve because nothing here
is timed.

3. **Distribution sanity.** Frames per request are reported as a distribution, not a median
alone: 3 to 21, median 11, mean 11.31, and the full histogram is in the trace stats (712 requests
at 3 frames down to 527 at 21). Reset events are counted separately (110) from rises (1,757), and
the by-episode-index table shows references rising 0, 81, 108, 135, ... rather than a single
summary. **The first version of proof (a) produced exactly the shape CLAUDE.md warns about** - a
credible rise derived from a quantity that could not mean what the column said, because no frame
carried bytes - and it is recorded above rather than quietly fixed.

4. **Definition audit.** EP-G: 21-frame cap, 0.5 s cadence, count-free header, StudyD3 question
and generation parameters, taken from `sh_ep_manifest` and `d3_infer_vllm` by AST read, all four
asserted equal in the proof JSON. Two definitions DIFFER from StudySH-EP's and both are named:
(i) **no pre-roll.** SH-EP's EP-G started 4.0 s before the first evaluated instant and so carried
nine frames at its first instant in 287 of 300 clips. That pre-roll needs 165 frames that are not
in the committed D91 store, and live2's decision grid starts at `NEXAR_GRID_T0_S = 3.0`, so in
live2 **every episode starts at one frame**. No frame was invented and none was encoded.
(ii) **refresh, not sliding cap**, as above. "Episode" = one play (`play_id`), which is the clip
play and the natural episode boundary; "refresh cycle" = 21 captured frames within a play;
"decision instant" = a captured instant at or above the floor. `dashcam_instants` keeps its
committed meaning and counts DECISION instants; captured instants are a new counter beside it.

5. **Claim linkage.** This row bears on no claim yet: it is plumbing for D153, and the only
numbers it produces are counts of what the bodies contain. The quality and latency claims it
enables (Context Inertia's semantic component under a warm append-only episode) are the H100's to
measure. Nothing measured here is scoped out by FORMULATION.md: no KV moves between tiers, and the
episode's KV is a single-tier prefix on one server.

6. **Proxy validity.** Two proxies, both labelled in the JSON. (i) `expected_cached_tokens` is
derived from the WIRE FORM and is not an engine measurement; it may not be used as a headline and
the engine-side confirmation is the H100's. (ii) the proof's frame store holds PLACEHOLDER bytes,
not JPEGs, which is valid for a wire-form proof and for nothing else; no score is computed from
them. Frame BYTES remain StudyE10a committed medians unless a Part-2 manifest is passed, unchanged
by this work.

7. **Validate the control, not only the result.** The control arm is the oneframe condition and it
was checked on its own numbers before the comparison was read: 2,103 monitoring requests, every
one at exactly one frame, the committed one-frame header, no EP-G counter non-zero. The positive
control is the committed `test_live2_fix2` suite, whose byte-identity test asserts the live
one-frame monitoring body against StudyD3's own `body()` function: it still PASSES, so the check is
not broken and the one-frame body is still the committed one.

## Tests

| suite | result |
|---|---|
| `tests/test_live2_coord.py` | 26 OK |
| `tests/test_live2_d114.py` | 16 OK |
| `tests/test_live2_d118.py` | 26 OK |
| `tests/test_live2_fakeserver.py` | 4 OK |
| `tests/test_live2_fix.py` | 16 OK |
| `tests/test_live2_fix2.py` | 22 OK |
| `tests/test_live2_harness.py` | 33 OK |
| `tests/test_live2_history_size.py` | OK |
| `fleet/tests/test_live2_fleet.py` | 234/234 checks |

`import hybrid`, `import arms` and `import coordinator` all succeed with ONLY `live2/` on
`sys.path`, which is how the harness imports them.

**One committed test failed mid-work and was a real signal.**
`test_live2_fix2.test_the_nexar_frame_ref_is_the_one_the_trace_puts_on_the_wire` asserts the
SOURCE LITERAL `f"{clip}|t{t_local:07.2f}"` appears in `fleet/trace.py`, because the trace's
frame_ref must match the D91 encoder's naming rule. My refactor had moved that expression into a
comprehension over `u`. The behaviour was unchanged, but **the test was right and the change was
wrong to touch that spelling**: a source-literal guard is only a guard if the literal is there.
The expression now spells the loop variable `t_local` again and the suite passes. Nothing in a test
file was edited.

`test_live2_fix2.test_one_frame_per_call_is_enforced` still PASSES, by design: the one-frame
refusal is kept and EP-G has to be asked for explicitly. That is why the contract change needed no
test edit.

## Mechanism verification

This row builds a format and proves the plumbing; it tests no causal claim and reports no policy
result, so Steps 1 to 5 are recorded in the register that applies.

* **Step 0, what would invalidate this run, asked first.** The comparator was about to change
  under me (the coordinator session's PATCH 1 and PATCH 2 landed on origin mid-task), so the
  worktree was moved to the new `origin/main` BEFORE any edit rather than rebased after; both of
  their changes are present and verified in the pushed file. A run with no frame store would make
  proof (a) vacuous, which is exactly what the first attempt did.
* **Step 1, the causal chain.** Not a causal experiment. The chain this enables, for the H100:
  if a dashcam episode is append-only KV (FORMULATION.md warm-state continuity, D148), then a
  monitoring request at instant k shares the header plus k-1 frames with the request at k-1, so
  the engine prefills one frame instead of the whole context, so the per-instant accelerator cost
  falls to about a ninth of the episode's prompt, and at a fixed budget more instants are served.
  Every link in THAT chain is measured on an engine, not here.
* **Step 2, instantiated.** Episode frame list: non-zero and varies 3 to 21, read at
  `coordinator._serve_monitor` to choose which frames carry bytes. Bytes-versus-reference: varies
  3 then 1 per request, read by `bodies.image_part`. Header: two literals, chosen by frame count,
  read at `bodies.monitor_header`. New-token charge: 1,056 down to 380 GPU-token charges, read by
  `Budget.can_spend`. No link is write-only.
* **Step 2b, done, above, before anything was scored.**
* **Step 3, one traced unit,** above, with every cost and the per-request outcome.
* **Step 4, negative control,** above: the mechanism switched off collapses to the committed
  one-frame body exactly.
* **Step 5, alternative explanation.** A reader could take proof (a)'s rise as evidence the engine
  WILL serve the prefix from cache. It is not: the same rise would appear in a body whose prefix
  the engine refuses to reuse, for instance if `cache_salt` differed per request or if the header
  carried the frame count. What distinguishes them is the header being count-free and the salt
  being per device and constant within an episode, both checked here; what settles it is the
  engine's own `cached_tokens`, which is the H100's.

## For the H100

`--dashcam-format epg` is the whole handshake; the floor defaults to 3. The exact argument string
is in the hand-back note, and `runs/EPG_ARGS` is the coordinator session's to commit.
