# live2 shared interface contract

StudyLIVE2. Definitive machine-readable form: `experiments/orchestration/live2/schema.py`
(`SCHEMA_VERSION = "live2-schema-1"`). This document says what the fields mean; where the two
disagree, `schema.py` is the record and this file must be corrected.

Authority: `research/policy_design_log.md` (D56, D63, D69, D70, D81, D83, D84),
`research/policy_spec_v4.md`.

## Clock and identifiers

- All times are SECONDS, floating point, on ONE run clock with `t = 0` at run start. No wall
  clock anywhere on the wire. Wall-clock fields exist only inside the coordinator's own logs
  and are excluded from determinism comparisons.
- `device_id` is stable for the run, e.g. `dash007`, `rob012`.
- `session_id` is unique per (device, session play): a robot device chains sessions (D83), and
  each play is a new task whose history starts from zero, so `session_id` carries the play
  index, e.g. `rob012/s3/play0`.
- `instant_id`, `question_id`, `batch_id` are unique within a device.
- `opportunity_id` (D96) is UNIQUE WITHIN THE RUN and is ASSIGNED BY THE TRACE GENERATOR. It is
  present on `monitor_offer`, `monitor_frame` and `recall_question`, and is echoed UNCHANGED
  into `cloud_answer`, into the decision log's `opportunity_ids`, and into the request log. THE
  COORDINATOR NEVER CONSTRUCTS, DERIVES OR PARSES ONE: a bare `instant_id` or `question_id` is
  ambiguous once D84 allows a clip or a session to be replayed on more than one device, or twice
  on one device once the session pool is exhausted. `instant_id` and `question_id` travel
  alongside it because they are what the device and the recordings call the same thing.
- `frame_ref` is a path to a stored JPEG (D70, D91), not image bytes. The coordinator reads the
  file; the wire carries the reference and `frame_bytes` (the on-disk JPEG size, used for the
  uplink model).

## Fleet to coordinator

| event | fields | when |
|---|---|---|
| `device_register` | `device_id, type, uplink_mbps, rtt_ms, start_t` | once per device, before any of its other events. `type` in `dashcam`, `robot`. |
| `session_start` | `device_id, session_id, t` | robots (D83), when a session play begins. |
| `session_end` | `device_id, session_id, t` | robots, when a session play ends. |
| `monitor_offer` | `device_id, opportunity_id, instant_id, t_capture, deadline_s, frame_bytes` | mode B only (D69): the device announces a decision instant and waits for a pull. |
| `monitor_frame` | `device_id, opportunity_id, instant_id, t_capture, t_arrive, deadline_s, frame_ref, frame_bytes` | mode A: pushed for every instant. Mode B: sent after a `pull_request`. |
| `history_preload` | `device_id, session_id, frame_refs, est_tokens, t` | once per robot session that is JOINED PART-WAY (D101), at `t = 0`: the frames the cloud ALREADY HOLDS as cold history at run start. `est_tokens` is CUMULATIVE, see "History size". |
| `history_append` | `device_id, session_id, batch_id, t_arrive, frame_refs, est_tokens` | every 30 s per robot session (D68); pushed in BOTH upload modes. `est_tokens` is the session's CUMULATIVE total after this batch, see "History size". |
| `recall_question` | `device_id, opportunity_id, session_id, question_id, t_ask, t_arrive, deadline_s, question, options` | at the question's real time (D68). |

`t_capture` is when the device captured the frame; `t_arrive` is when the payload finished
arriving at the coordinator, i.e. the fleet has already charged the uplink and RTT/2 (D30). The
coordinator never recomputes uplink time for data already marked arrived.

`deadline_s` is the per-opportunity latency bound measured from `t_capture` (monitoring) or
`t_ask` (recall): dashcam 1.0 s, robot 5.0 s (D71, D82). It is on the wire so that an arm that
only reads events still sees the bound.

### HISTORY SIZE: `est_tokens` IS CUMULATIVE (fixed 2026-11-18)

**On the wire, `est_tokens` is the session's CUMULATIVE history tokens AFTER this event, not the
increment this event adds.** The coordinator's belief for a session is therefore the LATEST value
it received, not a sum and not a maximum. One rule covers all three producers:

| producer | what it sends |
|---|---|
| `history_append` | the session's running total after this batch (`trace.py`'s `cum_tokens`, which resets at `session_start` per D83 and already includes the preload) |
| `history_preload` (D101) | the same quantity; the preload is the session's first holding, so for it the increment and the total coincide |
| `traces.py::synthetic` (the dry-run fixtures) | already cumulative (`D2_HEADER_TOK + frames_so_far * D2_TOK_PER_IMG`), which is why the fixtures never exposed the defect below |

A record that carries no `cum_tokens` is REFUSED by `emulator._cumulative_tokens` rather than read
as an increment, because that silent reading is the defect this rule closes.

THE DEFECT THIS REPLACES, recorded so it cannot come back. `fleet/emulator.py` forwarded the
PER-BATCH increment and discarded the `cum_tokens` the trace carries beside it, and `cstate.py`
then kept `max(batch, so_far)`, which on a stream of increments leaves the belief at the LARGEST
SINGLE BATCH. On the seed-10 12-device trace robo002's second session was believed at 1,381
tokens against a true 17,581, and every session in that trace was understated by 2.0x to 12.7x.
Because `coordinator._advance_build` derives the FRAME COUNT from the token budget
(`n_new = round(piece / D2_TOK_PER_IMG)`), the understatement also sent a fraction of the frames,
which is how a 24,838-token history went out as a 2,171-token prompt.

`est_tokens` is the fleet's token estimate, used for planning only. The actual prompt token count
is whatever the engine reports.

`history_preload` (D101) carries NO `batch_id` and NO `t_arrive`, because it is not a batch that
arrived during the run: its frames were on cloud-side disk before the clock started. **No uplink
time is charged for a preload**, and the coordinator must never recompute one. It stores the
frames as COLD history exactly as it stores an ingested batch (D56: frames on disk, NO KV), so
the first question on a joined-into session still pays a cold rebuild of the joined prefix; that
cold-rebuild pressure is the reason D101 exists. `t` is the run-clock instant at which the
holding is declared, 0.0 for a join-point preload. Only questions after the join point are on
the wire at all, so the coordinator needs no join-point field: the trace already omits them.

## Coordinator to fleet

| event | fields | meaning |
|---|---|---|
| `pull_request` | `device_id, instant_id, t_sent` | mode B only: send me this instant's frame. The pull message and the subsequent upload both count toward delivered delay (D69). |
| `cloud_answer` | `device_id, opportunity_id, t_done, payload` | the cloud's answer. `t_done` is when it was delivered to the device. |

DEVICE ANSWERS NEVER PASS THROUGH THE COORDINATOR. Every opportunity is answered locally by the
device (spec v4 section 1.2); the device answer is scored offline from recordings (D87). The
coordinator only ever adds a cloud answer that may upgrade it.

A `session_end` means the session will receive no more questions, so its KV may be released. Its
FRAMES STAY ON DISK: evidence that reached the cloud is never discarded (D56), and `cold` means
rebuild from frames, not deleted.

## Coordinator log streams (JSONL, one file per stream per run)

`decision.jsonl`

```
{t, arm, arm_version, decision_id, kind, opportunity_ids[], piece_tokens,
 predicted {ttft_s, completion_s, imposed_delay_s_by_request{request_id: seconds}},
 cost_model_id, mu, H,
 belief {gpu_tokens_by_session{}, host_tokens_by_session{}, cold_tokens_by_session{}},
 decision_latency_ms, traffic_mix{}, defer_s, note}
```

`kind` is one of `admit`, `decline`, `defer`, `release_piece`, `release_whole`,
`release_monitor`, `release_recall`, `pull`, `state_action`, `no_action`.
`predicted` is filled only by arms that predict (the policy); baselines leave it empty unless
they have their own estimate (D63). `traffic_mix` is the mix in flight at submit time:
`{monitor, piece, whole, recall}` counts.

`request.jsonl`

```
{request_id, decision_id, device_id, t_submit, t_first_token, t_done, prompt_tokens,
 cached_tokens, cache_path, cached_fraction, output_tokens, http_status, cache_salt,
 session_id, opportunity_id, mm_uuids[], traffic_mix{}}
```

`cache_path` is `WARM` if `cached_tokens > 0` else `COLD`, with `cached_fraction =
cached_tokens / prompt_tokens` alongside (D81). Both come from the engine's own per-request
usage report, never from the coordinator's belief.

`residency.jsonl`

```
{t, session_id, believed_tier, telemetry_cached_tokens, device_id, believed_dist{}}
```

`believed_tier` is the argmax of the belief distribution over `gpu`, `host`, `cold`;
`believed_dist` is the distribution itself (spec v4 section 7.6: belief is a distribution and
ambiguous evidence moves mass to the colder tier).

## The fairness digest (D96 part 2)

The CANONICAL fairness digest is the fleet's definition: an ORDER-INDEPENDENT sha256 over SORTED
event tuples, reported as the full 64 hex characters, never a prefix taken in iteration order.
It is recorded as `fairness_digest` in every run header and is what the fairness test compares
across arms. The StudyLIVE1-port digest may appear ONLY under the name `live1_trace_digest`, and
a run header must never present one as the other.

COVERAGE: `device_register`, `session_start`, `session_end`, `history_preload`,
`history_append`, `recall_question`, and `monitor_offer` in PULL mode (B) or `monitor_frame` in
PUSH mode (A). In pull mode the frames are EXCLUDED, because which frames exist depends on the
arm's own pulls and so cannot be a fairness invariant. `history_preload` is covered (D96 list
plus `history_preload`) because the D101 join point decides which questions count, so two
streams with different preloads are different experiments and must not share a digest.

ROW SHAPE, one row per covered event, exactly the fleet's canonical six-field tuple
`fleet/trace.py::_digest_tuple` -> `(device_id, wire_kind, t, key, extra, deadline)`, with every
time formatted to six decimals and every field a string, joined with `|` and a trailing newline,
the rows sorted before hashing:

| kind | row |
|---|---|
| `device_register` | `device_id, "device_register", start_t, "", "", ""` |
| `session_start` / `session_end` | `device_id, kind, t, session_id, "", ""` |
| `history_preload` | `device_id, "history_preload", t, session_id, est_tokens, ""` |
| `history_append` | `device_id, "history_append", t_arrive, batch_id, est_tokens, ""` |

**The digest's `est_tokens` is the TRACE RECORD's field, which is the PER-BATCH INCREMENT, and it
is deliberately not the cumulative value the wire carries.** The digest is computed over
`FleetEmulator.presented`, which holds the trace's own records, so it is a property of the TRACE
and not of what any coordinator was told. Changing it to the cumulative value would change every
committed fairness digest for no gain, so the two fields keep their own meanings: `cum_tokens` on
the wire and in the belief, `est_tokens` of the record in the digest. The 2026-11-18 history-size
fix deliberately left every digest byte-identical.
| `recall_question` | `device_id, "recall_question", t_ask, opportunity_id, session_id, deadline_s` |
| `monitor_offer` / `monitor_frame` | `device_id, kind, t_capture, opportunity_id, "", deadline_s` |

D96 fixes the rule and the coverage; the per-kind row above is the FLEET's, which is canonical,
and `traces.py::_fairness_row` reproduces it field for field. A test asserts byte equality
between `traces.fairness_digest` and `fleet/trace.py::fairness_digest` on one stream in both
modes, so a change on either side fails loudly instead of letting two digests diverge. The
`history_preload` row has no `batch_id`, so the SESSION is its key and the holding's
`est_tokens` is its extra field.

## Run header (`header.json`)

`git_commit, arm, arm_version, flags, gpu_kv_tokens, host_tier_gib, host_tier_tokens,
cost_model_id, cost_model_hash, calibration_file, calibration_label, fairness_digest,
trace_label, seed, targets, upload_mode, mu_mode, mu_value, H, tick_s, decision_period_s,
gpu_budget_s, memory_setting, ratio, mode, server_url, server_kind, model, live1_trace_digest,
placeholders, schema_version, is_measurement, note`.

`decision_period_s` (D99 (1)) is the ONE decision period every arm decides on, 100 ms in round
1, with that period's events batched. It is NOT H: `H` is the rollout horizon only, and an arm
without a horizon carries `H: null`. `tick_s` is the same number as `decision_period_s` under
its old name.

`gpu_budget_s` (D102) is the GPU budget INPUT, identical for every arm; the default is one GPU's
time over the run (`window_s` x 1.0), which is the physical capacity and so never binds
artificially (D58).

`memory_setting`, `ratio` and `mode` (D103 (f)) are what the SCORER reads to label a comparison
PRIMARY rather than EXPLORATORY, and a missing one silently degrades every block-1 comparison:
`memory_setting` is D76's `tight` or `roomy` LABEL (derived from `host_tier_gib`, so the two
cannot disagree), `ratio` is the dashcam : robot mix as a string such as `50:50` (from the fleet
trace's own meta, or from the device counts), and `mode` is `A` or `B` (the same value as
`upload_mode`, under the name the scorer expects).

`server_kind` is `fake` or `vllm`. A run against the fake server is NEVER a measurement:
`is_measurement` is false and the report must say so. `calibration_label` carries the
calibration map's own label; the coordinator REFUSES to start a non-stub run with a map labelled
`INTERIM` (D86).

## Capacities and targets

`gpu_kv_tokens` and `host_tier_gib` are command-line INPUTS passed to every arm that uses them
(D56, D76). Nothing is hard-coded. Targets are passed to all arms identically and are never
changed per arm (D71, D82): dashcam `L = 1.0 s, p = 0.25` per device; robot `L = 5.0 s,
p = 0.90` POOLED over robot devices.

## How an arm's action is enacted

Every arm is an `interface.Policy` and returns an `interface.Action`, so all eight share one
action space and every action passes `interface.validate_action`. The coordinator enacts it as
follows, identically for every arm:

| action | enactment |
|---|---|
| `StreamAction(mode="cloud")` | serve that dashcam's earliest arrived, undecided instant inside its deadline. In mode B, if the frame has not arrived, send `pull_request` instead and serve it when it does. |
| `StreamAction(mode="local")` | nothing: the instant stands as the device's own answer (D62: an instant not served uses the device's answer). |
| `RecallAction("CLOUD")` | submit the answer request for that question; if a MATERIALIZE for its session is in the same action, the answer follows the build. |
| `RecallAction("DEVICE" / "REJECT")` | decline; the device's answer stands. |
| `RecallAction("DEFER", defer_s)` | withhold the question until `defer_s` has elapsed, then re-decide (amendment 2, D90). HONOURED FOR EVERY ARM. |
| `SessionAction("MATERIALIZE", target_tokens, slice_tokens)` | advance that session's build by ONE piece of `slice_tokens`, or, with `slice_tokens = None`, build the remainder in one request. |
| `SessionAction("EVICT")` | demote to cold: the believed tier becomes cold and the built tokens are dropped. THE FRAMES STAY ON DISK (D56). |
| `SessionAction("KEEP_GPU_WARM" / "OFFLOAD_TO_HOST")` | record the DESIRED tier. Residency is steered, never commanded (spec 7.2), and the TOUCH action is conditional and OFF (D66). |

A PARTIALLY BUILT HISTORY IS NOT WARM: the believed tier becomes `gpu` only when the whole
history is built, because the interface's `readiness` has no partial value, and that is what
keeps a chaining arm issuing the next piece.

CATCH UP IS IMPLICIT IN THE ANSWER REQUEST. Frames that arrived after the build are sent with
their bytes in the recall answer's own request, alongside uuid references for the built prefix,
so an answer is never stale even if no arm asked for a catch-up. An arm that wants an explicit
CATCH UP (spec 7.3) expresses it as a MATERIALIZE with a larger `target_tokens`; pi_0 does not.

ONE MATERIALIZE ADVANCES THE BUILD BY ONE PIECE. StudyLIVE1's adapter issued a whole prefix
chain on a single MATERIALIZE; live2 advances one piece per action, so each piece is a separate
decision and a separate request an arm can hold or re-order. The rule is the same for every arm.

The budget (`interface.Budget`) is `window_s x 1.0` GPU-seconds, identical for every arm, as in
StudyLIVE1's adapter. Round 1 has no fixed budget (D58), but the ratio-based arms need a finite
one; the value is a harness constant and should become an explicit input before a measured run.

## Cache isolation (D84)

Every request carries a per-device cache salt and one multimodal UUID per (device, frame), so
two devices replaying the same clip share no KV and no image encoding, while a device's own
history still hits its own cache. The salt is a function of (run seed, device_id); the UUID is a
function of (device_id, frame_ref) and is therefore STABLE across re-sends of the same frame by
the same device.
